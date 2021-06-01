import asyncio
import logging
import time
from typing import Optional, Dict, AsyncIterable

import aiohttp
import ujson
import websockets
from websockets import ConnectionClosed

from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger

EXCHANGEFOREST_USER_STREAM_ENDPOINT = "/api/ListenKey"

class ExchangeforestPerpetualUserStreamDataSource(UserStreamTrackerDataSource):
    _bpusds_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._bpusds_logger is None:
            cls._bpusds_logger = logging.getLogger(__name__)
        return cls._bpusds_logger

    @property
    def last_recv_time(self) -> float:
        return self._last_recv_time

    def __init__(self, base_url: str, stream_url: str, api_key: str,secret_key:str):
        super().__init__()
        self._api_key: str = api_key
        self.secret:str = secret_key
        logging.info("%s apikey"%api_key)
        logging.info("%s secretkey" % secret_key)
        self._current_listen_key = None
        self._listen_for_user_stream_task = None
        self._last_recv_time: float = 0

        self._http_stream_url = base_url + EXCHANGEFOREST_USER_STREAM_ENDPOINT

        self._wss_stream_url = stream_url + "/ws/"

        #self.api_key = '013ec3ae-5485-4967-9d03-6e9eb10e0f95'
        #self.secret = '6339fc64-4b31-4ccf-9468-f6704ed9abd9'

    async def get_listen_key(self):
        async with aiohttp.ClientSession() as client:
            #return 'Z0NWoaVA0bzDXGpR62GHG7juUBXEk9YQjxu47pVh8M9BU9N3tgyj27M0Xs6zD1ma'  #
            logging.info('inside listenkey')
            async with client.post (self._http_stream_url,
                                   headers={"secret": self.secret,
                                            "key": self._api_key,"Content-type" :"application/json"}) as response:
                response: aiohttp.ClientResponse = response
                if response.status != 200:
                    logging.info('get_listenkey: erroro' )

                    raise IOError(f"Error fetching Exchangeforest Perpetual user stream listen key. "
                                  f"HTTP status is {response.status}.")
                data: Dict[str, str] = await response.json()
                logging.info('get_listenkey: %s'%data)
                return data["listenKey"]

    async def ping_listen_key(self, listen_key: str) -> bool:
        async with aiohttp.ClientSession() as client:
            async with client.put(self._http_stream_url,
                                  headers={"secret": self.secret,"key":self.api_key,
                                           "Content-type" :"application/json"},
                                  params={"listenKey": listen_key}) as response:
                data: [str, any] = await response.json()
                if "code" in data:
                    self.logger().warning(f"Failed to refresh the listen key {listen_key}: {data}")
                    return False
                return True

    async def ws_messages(self, client: websockets.WebSocketClientProtocol) -> AsyncIterable[str]:
        try:
            while True:
                try:
                    raw_msg: str = await asyncio.wait_for(client.recv(), timeout=50.0)
                    self._last_recv_time = time.time()
                    yield raw_msg
                except asyncio.TimeoutError:
                    try:
                        self._last_recv_time = time.time()
                        pong_waiter = await client.ping()
                        await asyncio.wait_for(pong_waiter, timeout=50.0)
                    except asyncio.TimeoutError:
                        raise
        except asyncio.TimeoutError:
            self.logger().warning("Websocket ping timed out. Going to reconnect... ")
            return
        except ConnectionClosed:
            return
        finally:
            await client.close()

    async def log_user_stream(self, output: asyncio.Queue):
        while True:
            try:
                stream_url: str = f"{self._wss_stream_url}{self._current_listen_key}"
                async with websockets.connect(stream_url) as ws:
                    ws: websockets.WebSocketClientProtocol = ws
                    async for raw_msg in self.ws_messages(ws):
                        msg_json: Dict[str, any] = ujson.loads(raw_msg)
                        output.put_nowait(msg_json)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error. Retrying after 5 seconds... ", exc_info=True)
                await asyncio.sleep(5)

    async def listen_for_user_stream(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):


        try:
            while True:
                try:
                    if self._current_listen_key is None:
                        self._current_listen_key = await self.get_listen_key()
                        self.logger().debug(f"Obtained listen key {self._current_listen_key}.")
                        if self._listen_for_user_stream_task is not None:
                            self._listen_for_user_stream_task.cancel()
                        self._listen_for_user_stream_task = safe_ensure_future(self.log_user_stream(output))
                        await self.wait_til_next_tick(seconds=3600)
                    success: bool = await self.ping_listen_key(self._current_listen_key)
                    if not success:
                        self._current_listen_key = None
                        if self._listen_for_user_stream_task is not None:
                            self._listen_for_user_stream_task.cancel()
                            self._listen_for_user_stream_task = None
                        continue
                    self.logger().debug(f"Refreshed listen key {self._current_listen_key}.")
                    await self.wait_til_next_tick(seconds=60)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger().error("Unexpected error while maintaning the user event listen key. Retrying after "
                                        "5 seconds...", exc_info=True)
                    await asyncio.sleep(5)
        finally:
            if self._listen_for_user_stream_task is not None:
                self._listen_for_user_stream_task.cancel()
                self._listen_for_user_stream_task = None
            self._current_listen_key = None

#"X-MBX-APIKEY": self._api_key}