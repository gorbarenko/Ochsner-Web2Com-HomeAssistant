# Ochsner Web2Com — Home Assistant HACS v1.9.0

This version is based on the supplied v1.8.0 ZIP. It retains the existing
`web2com` integration domain, all original sensor entity unique IDs, and the
heater mode selector.

## What changed in 1.9.0
- Shared sensor DataUpdateCoordinator rather than one coordinator per sensor.
- Validates HTTP status from `ochsner_web2com.Service.get_value()`; erroneous
  `(401, 0.0)` and `(0, 0.0)` are **no longer treated as valid zero readings**.
- Default sensors are polled every 60 seconds. 10 disabled-by-default
  diagnostic sensor OIDs are round-robin polled on each cycle.
- Exact duplicate OIDs and duplicate keys are not registered twice.
- Setup connection validation requires HTTP status 200.
- Keeps the existing heater mode selector write logic from 1.8.0 unchanged.
  **Switching that selector writes to the heating system.**

## Not yet implemented
This is a staged v1.9.0 build, **not** the full promised rewrite:
automatic SOAP tree discovery, automatic bounds/step metadata, bulk SOAP
requests, and numeric heating-curve controls have **not** been added. The
included 67 OIDs are taken from the supplied archive, rather than discovered.

## Install
1. Back up your existing `/config/custom_components/web2com` directory and
   HA configuration before installing.
2. Stop or restart HA in a maintenance window. Replace
   `/config/custom_components/web2com` with this directory.
3. Restart Home Assistant, check **Settings > Devices & services** and logs.
4. Connect through config flow using Room Terminal IP, username, password,
   and Digest (or Basic if your gateway requires it).
5. Validate temperatures against the physical terminal before enabling any
   additional diagnostic entities or changing the heater mode.

The additional diagnostic entities may initially show unavailable and become
available gradually as the coordinator cycles through them. Offline OIDs stay
unavailable instead of showing fictitious zero readings.

## Safety
Reading OIDs is non-mutating. The existing select entity still writes the
electric booster heater mode; never use it without verifying its effects on
your installation.

## Експериментальні можливості 1.9.0 (розширена збірка)

- `soap_client.py`: обмежений `listDpRequest` для пошуку OID та `getDpRequest` для групових значень.
- `sensor.py`: спочатку спроба групового читання лише 2–8 параметрів однієї гілки, а при невідомому форматі SOAP — окремі перевірені читання. Жодні пропущені значення не підставляються нулями.
- Опція `auto_discover` (за замовчуванням **вимкнена**): один обмежений пошук доступних для читання параметрів у гілках `/1/2/2`, `/1/2/4`, `/1/2/5` під час запуску інтеграції. Нові сенсори вимкнені за замовчуванням і позначені як діагностичні.
- `number.py`: каркас керування 12 параметрами опалювальних кривих. **Керування не активується**, доки не надано перевірених меж `verified_curve_bounds` і явно не ввімкнено сутності. У стандартному налаштуванні не виконується жодного запису кривих.

### Перевірка

Цей ZIP перевірено на Python-синтаксис та структуру; не протестовано на реальному Room Terminal чи Home Assistant. Перед оновленням збережіть резервну копію папки `web2com`. Після перезапуску перевірте журнал Home Assistant. За проблем із пошуком OID вимкніть `auto_discover` в параметрах інтеграції.

### Примітка щодо меж кривих

Межі та кроки кривих не можна безпечно вивести зі звичайних значень OID. Наша інтеграція поки не має підтвердженого автоматичного парсера метаданих допустимих значень саме для цього контролера. У майбутньому розширимо клієнт після перевірки сирих SOAP-відповідей.
