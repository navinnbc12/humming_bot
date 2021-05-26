from hummingbot.connector.in_flight_order_base cimport InFlightOrderBase

cdef class ExchangeforestInFlightOrder(InFlightOrderBase):
    cdef:
        public object trade_id_set
