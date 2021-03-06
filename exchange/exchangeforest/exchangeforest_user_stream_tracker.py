#!/usr/bin/env python

import asyncio
import logging
from typing import (
    Optional
)
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.user_stream_tracker import UserStreamTracker
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
    safe_gather,
)
from .exchangeforest_api_user_stream_data_source import ExchangeforestAPIUserStreamDataSource
from exchangeforest.client import Client as ExchangeforestClient


class ExchangeforestUserStreamTracker(UserStreamTracker):
    _bust_logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._bust_logger is None:
            cls._bust_logger = logging.getLogger(__name__)
        return cls._bust_logger

    def __init__(self, exchangeforest_client: Optional[ExchangeforestClient] = None, domain: str = "com"):
        super().__init__()
        self._exchangeforest_client: ExchangeforestClient = exchangeforest_client
        self._ev_loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()
        self._data_source: Optional[UserStreamTrackerDataSource] = None
        self._user_stream_tracking_task: Optional[asyncio.Task] = None
        self._domain = domain

    @property
    def data_source(self) -> UserStreamTrackerDataSource:
        if not self._data_source:
            self._data_source = ExchangeforestAPIUserStreamDataSource(exchangeforest_client=self._exchangeforest_client, domain=self._domain)
        return self._data_source

    @property
    def exchange_name(self) -> str:
        if self._domain == "com":
            return "exchangeforest"
        else:
            return f"exchangeforest_{self._domain}"

    async def start(self):
        self._user_stream_tracking_task = safe_ensure_future(
            self.data_source.listen_for_user_stream(self._ev_loop, self._user_stream)
        )
        await safe_gather(self._user_stream_tracking_task)
