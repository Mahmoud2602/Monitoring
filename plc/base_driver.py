"""
Industrial PLC Production Monitor - Protocol Driver Abstraction

Defines the abstract interface for industrial PLC communication drivers.
Allows plugging in Ethernet protocols (Modbus TCP, Mitsubishi MC Protocol,
Siemens S7, Rockwell Ethernet/IP) without altering business logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class PLCError(Exception):
    """Base exception for all PLC communication issues."""
    pass


class PLCConnectionError(PLCError):
    """Raised when establishing or maintaining a transport connection fails."""
    pass


class PLCConnectionTimeoutError(PLCConnectionError):
    """Raised when a connection attempt or read cycle exceeds the configured timeout."""
    pass


class PLCCommunicationError(PLCError):
    """Raised when an error occurs during frame transmission or register parsing."""
    pass


class BasePLCDriver(ABC):
    """
    Abstract Base Class for Industrial Ethernet PLC communication drivers.
    Concrete implementations provide transport and protocol framing.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 2.0,
        driver_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.driver_params = driver_params or {}

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the underlying socket/channel is currently connected."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the industrial PLC.
        Returns True if successful, or raises PLCConnectionError/PLCConnectionTimeoutError.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully terminate connection to the PLC."""
        pass

    @abstractmethod
    def read_bits(self, addresses: List[str]) -> Dict[str, bool]:
        """
        Read status of discrete contact bits (e.g. M550..M559, coils, inputs).
        Returns a dictionary mapping physical address string -> boolean status.
        """
        pass

    @abstractmethod
    def read_registers(self, addresses: List[str]) -> Dict[str, Any]:
        """
        Read values of word/data registers (e.g. D450..D453, holding registers).
        Returns a dictionary mapping physical address string -> register value.
        """
        pass
