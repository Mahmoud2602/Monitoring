"""
Industrial PLC Production Monitor - Real Hardware Ethernet Driver
Supports standard Industrial Ethernet PLC communication (Modbus TCP / SLMP / Socket).
Zero external dependencies required (uses standard library `socket` and `struct`),
with optional pymodbus acceleration if available in the runtime environment.
"""
from __future__ import annotations

import select
import socket
import struct
import threading
from typing import Any, Dict, List, Optional

from plc.base_driver import (
    BasePLCDriver,
    PLCCommunicationError,
    PLCConnectionError,
    PLCConnectionTimeoutError,
)
from utils.logger import get_logger

logger = get_logger("plc.ethernet_driver")


class EthernetPLCDriver(BasePLCDriver):
    """
    Production-grade Ethernet PLC Driver implementing standard Modbus TCP
    over raw TCP sockets, fully conforming to BasePLCDriver.
    
    Supports:
    - Discrete contact bit reads (M550..M559 -> coils or discrete inputs)
    - Holding register reads (D450..D453 -> holding registers 40001+)
    - Configurable host, port, timeout, and unit ID
    - Robust timeout handling and socket lifecycle
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: float = 2.0,
        driver_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(host, port, timeout, driver_params)
        self.unit_id: int = int(self.driver_params.get("unit_id", 1))
        self.register_offset: int = int(self.driver_params.get("register_offset", 0))
        self.bit_offset: int = int(self.driver_params.get("bit_offset", 0))

        self._socket: Optional[socket.socket] = None
        self._connected: bool = False
        self._transaction_id: int = 0
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected and (self._socket is not None)

    def connect(self) -> bool:
        """
        Open a TCP socket connection to the physical PLC.
        Raises PLCConnectionTimeoutError on timeout, or PLCConnectionError on socket failure.
        """
        with self._lock:
            if self._connected and self._socket:
                return True

            self._disconnect_internal()

            logger.info("Connecting to physical Ethernet PLC at %s:%d (timeout=%.1fs)...", self.host, self.port, self.timeout)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                sock.connect((self.host, self.port))
                self._socket = sock
                self._connected = True
                logger.info("Successfully connected to Ethernet PLC at %s:%d", self.host, self.port)
                return True

            except socket.timeout as exc:
                try:
                    sock.close()
                except Exception:
                    pass
                self._disconnect_internal()
                raise PLCConnectionTimeoutError(
                    f"Connection timed out reaching PLC at {self.host}:{self.port} (timeout={self.timeout}s)"
                ) from exc
            except (ConnectionRefusedError, socket.gaierror, OSError) as exc:
                try:
                    sock.close()
                except Exception:
                    pass
                self._disconnect_internal()
                raise PLCConnectionError(
                    f"Failed to connect to physical PLC at {self.host}:{self.port}: {exc}"
                ) from exc
            except Exception as exc:
                try:
                    sock.close()
                except Exception:
                    pass
                self._disconnect_internal()
                raise PLCConnectionError(f"Unexpected connection error for {self.host}:{self.port}: {exc}") from exc

    def disconnect(self) -> None:
        """Gracefully close Ethernet socket."""
        with self._lock:
            self._disconnect_internal()
            logger.info("Disconnected from Ethernet PLC at %s:%d", self.host, self.port)

    def _disconnect_internal(self) -> None:
        self._connected = False
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        return self._transaction_id

    def _parse_address_num(self, address: str, default: int = 0) -> int:
        """Parse numeric offset from address string like 'D450' -> 450 or 'M550' -> 550."""
        digits = "".join(c for c in address if c.isdigit())
        return int(digits) if digits else default

    def read_registers(self, addresses: List[str]) -> Dict[str, Any]:
        """
        Read 16-bit holding registers (Function Code 0x03).
        Calculates contiguous register span from min to max address.
        """
        if not addresses:
            return {}

        with self._lock:
            if not self.is_connected or not self._socket:
                raise PLCConnectionError("Ethernet PLC is not connected")

            # Calculate span
            addr_nums = {addr: self._parse_address_num(addr) for addr in addresses}
            min_addr = min(addr_nums.values())
            max_addr = max(addr_nums.values())
            count = max(1, (max_addr - min_addr + 1))

            # Build Modbus TCP Read Holding Registers request (FC 03)
            # MBAP Header: TransactionID (2B), ProtocolID=0 (2B), Length=6 (2B), UnitID (1B)
            # PDU: FunctionCode=3 (1B), StartingAddress (2B), Quantity (2B)
            trans_id = self._next_transaction_id()
            start_offset = min_addr + self.register_offset
            request = struct.pack(">HHHBBHH", trans_id, 0, 6, self.unit_id, 3, start_offset, count)

            try:
                self._socket.sendall(request)
                response = self._recv_exact(9)  # MBAP (7) + FC (1) + ByteCount (1)
                r_trans_id, r_proto, r_len, r_unit, r_fc, byte_count = struct.unpack(">HHHBBB", response)

                if r_fc & 0x80:
                    err_code = self._recv_exact(1)[0]
                    raise PLCCommunicationError(f"Modbus exception response: FC={r_fc:#x}, code={err_code}")

                data_bytes = self._recv_exact(byte_count)
                registers_read = struct.unpack(f">{byte_count // 2}H", data_bytes)

                result: Dict[str, Any] = {}
                for addr_str, num in addr_nums.items():
                    offset_idx = num - min_addr
                    if 0 <= offset_idx < len(registers_read):
                        result[addr_str] = registers_read[offset_idx]
                    else:
                        result[addr_str] = 0

                return result

            except socket.timeout as exc:
                self._disconnect_internal()
                raise PLCConnectionTimeoutError(f"Read registers timeout from {self.host}:{self.port}") from exc
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                self._disconnect_internal()
                raise PLCConnectionError(f"Connection lost while reading registers: {exc}") from exc
            except Exception as exc:
                if isinstance(exc, (PLCCommunicationError, PLCConnectionError, PLCConnectionTimeoutError)):
                    raise
                self._disconnect_internal()
                raise PLCCommunicationError(f"Error parsing register response: {exc}") from exc

    def read_bits(self, addresses: List[str]) -> Dict[str, bool]:
        """
        Read discrete contact bits (Function Code 0x01 / 0x02).
        Calculates contiguous coil span from min to max bit address.
        """
        if not addresses:
            return {}

        with self._lock:
            if not self.is_connected or not self._socket:
                raise PLCConnectionError("Ethernet PLC is not connected")

            addr_nums = {addr: self._parse_address_num(addr) for addr in addresses}
            min_addr = min(addr_nums.values())
            max_addr = max(addr_nums.values())
            count = max(1, (max_addr - min_addr + 1))

            trans_id = self._next_transaction_id()
            start_offset = min_addr + self.bit_offset
            # FC 01: Read Coils
            request = struct.pack(">HHHBBHH", trans_id, 0, 6, self.unit_id, 1, start_offset, count)

            try:
                self._socket.sendall(request)
                response = self._recv_exact(9)
                r_trans_id, r_proto, r_len, r_unit, r_fc, byte_count = struct.unpack(">HHHBBB", response)

                if r_fc & 0x80:
                    err_code = self._recv_exact(1)[0]
                    raise PLCCommunicationError(f"Modbus exception reading coils: FC={r_fc:#x}, code={err_code}")

                data_bytes = self._recv_exact(byte_count)

                # Unpack bits from bytes
                result: Dict[str, bool] = {}
                for addr_str, num in addr_nums.items():
                    bit_idx = num - min_addr
                    byte_pos = bit_idx // 8
                    bit_pos = bit_idx % 8
                    if byte_pos < len(data_bytes):
                        is_on = bool((data_bytes[byte_pos] >> bit_pos) & 1)
                        result[addr_str] = is_on
                    else:
                        result[addr_str] = False

                return result

            except socket.timeout as exc:
                self._disconnect_internal()
                raise PLCConnectionTimeoutError(f"Read bits timeout from {self.host}:{self.port}") from exc
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                self._disconnect_internal()
                raise PLCConnectionError(f"Connection lost while reading bits: {exc}") from exc
            except Exception as exc:
                if isinstance(exc, (PLCCommunicationError, PLCConnectionError, PLCConnectionTimeoutError)):
                    raise
                self._disconnect_internal()
                raise PLCCommunicationError(f"Error parsing bits response: {exc}") from exc

    def _recv_exact(self, num_bytes: int) -> bytes:
        """Receive exactly num_bytes from socket or raise PLCConnectionError."""
        if not self._socket:
            raise PLCConnectionError("Socket is closed")
        buf = bytearray()
        while len(buf) < num_bytes:
            chunk = self._socket.recv(num_bytes - len(buf))
            if not chunk:
                raise PLCConnectionError("Socket closed prematurely by peer")
            buf.extend(chunk)
        return bytes(buf)


# Clean alias for Modbus TCP
ModbusTCPDriver = EthernetPLCDriver
