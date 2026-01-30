from typing import Any, Dict

from .const import CONF_DEVICE_TYPE
from .InitialDeviceConfig import InitialDeviceConfig
from .OptionalDeviceConfig import OptionalDeviceConfig


class FullDeviceConfig:
    def __init__(
        self,
        initial: InitialDeviceConfig,
        optional: OptionalDeviceConfig,
    ):
        self.address = initial.address
        self.name = initial.name
        self.dev_type = initial.dev_type
        self.use_encryption = initial.use_encryption
        self.polling_interval = optional.polling_interval
        self.polling_timeout = optional.polling_timeout
        self.max_retries = optional.max_retries

    @staticmethod
    def from_dict(raw: Dict[str, Any]):
        initial = InitialDeviceConfig.from_dict(raw)

        if initial is None:
            return None

        # 🔥 Manual override wins
        if CONF_DEVICE_TYPE in raw:
            initial.dev_type = raw[CONF_DEVICE_TYPE]

        return FullDeviceConfig(
            initial,
            OptionalDeviceConfig.from_dict(raw),
        )
