"""Список аудио-устройств с удобной дедупликацией по имени.

Windows показывает одно и то же устройство несколько раз (MME, DirectSound,
WASAPI). Для пользователя это шум, поэтому мы склеиваем их по имени и храним
все индексы: если WASAPI почему-то не откроется, движок попробует следующий.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Чем меньше число, тем предпочтительнее host API.
_API_RANK = {
    "Windows WASAPI": 0,
    "Windows DirectSound": 1,
    "MME": 2,
    "ASIO": 3,
    "Windows WDM-KS": 4,
}

_CABLE_HINTS = ("cable input", "cable output", "voicemeeter", "virtual cable")


@dataclass
class DeviceInfo:
    name: str
    indices: list[int] = field(default_factory=list)
    hostapis: list[str] = field(default_factory=list)
    default_samplerate: int = 48000

    @property
    def label(self) -> str:
        return self.name

    @property
    def is_cable(self) -> bool:
        low = self.name.lower()
        return any(hint in low for hint in _CABLE_HINTS)

    def __str__(self) -> str:  # для --list-devices
        apis = ", ".join(dict.fromkeys(self.hostapis))
        return f"{self.name}  [{apis}]  {self.default_samplerate} Гц"


def _add_device(
    table: dict[str, DeviceInfo],
    name: str,
    index: int,
    hostapi: str,
    samplerate: int,
) -> None:
    key = name.strip()
    info = table.get(key)
    if info is None:
        info = DeviceInfo(name=key)
        table[key] = info
    info.indices.append(index)
    info.hostapis.append(hostapi)
    info.default_samplerate = samplerate


def _sorted(table: dict[str, DeviceInfo]) -> list[DeviceInfo]:
    result = list(table.values())
    result.sort(key=lambda d: d.name.lower())
    return result


def list_devices() -> tuple[list[DeviceInfo], list[DeviceInfo]]:
    """(входные, выходные) устройства без дублей по имени."""
    import sounddevice as sd

    hostapis = sd.query_hostapis()
    inputs: dict[str, DeviceInfo] = {}
    outputs: dict[str, DeviceInfo] = {}

    for index, dev in enumerate(sd.query_devices()):
        api_index = int(dev["hostapi"])
        api_name = hostapis[api_index]["name"] if api_index < len(hostapis) else "?"
        sr = int(round(float(dev["default_samplerate"])))
        name = str(dev["name"]).strip()
        if dev["max_input_channels"] > 0:
            _add_device(inputs, name, index, api_name, sr)
        if dev["max_output_channels"] > 0:
            _add_device(outputs, name, index, api_name, sr)

    def prefer(info: DeviceInfo) -> None:
        order = sorted(
            range(len(info.indices)),
            key=lambda i: _API_RANK.get(info.hostapis[i], 9),
        )
        info.indices = [info.indices[i] for i in order]
        info.hostapis = [info.hostapis[i] for i in order]

    for group in (inputs, outputs):
        for info in group.values():
            prefer(info)

    return _sorted(inputs), _sorted(outputs)


def default_names() -> tuple[str, str]:
    """Имена устройств по умолчанию (вход, выход) — как в Windows."""
    import sounddevice as sd

    try:
        default = sd.default.device
    except Exception:
        return "", ""

    names = []
    for index in default:
        try:
            names.append(str(sd.query_devices(int(index))["name"]).strip())
        except Exception:
            names.append("")
    return names[0], names[1]


def find_by_name(devices: list[DeviceInfo], name: str | None) -> DeviceInfo | None:
    if not name:
        return None
    for info in devices:
        if info.name == name:
            return info
    low = name.strip().lower()
    for info in devices:
        if info.name.strip().lower() == low:
            return info
    return None


def find_virtual_output(devices: list[DeviceInfo]) -> DeviceInfo | None:
    for info in devices:
        if "cable input" in info.name.lower():
            return info
    for info in devices:
        if info.is_cable:
            return info
    return None
