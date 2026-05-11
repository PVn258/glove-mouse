# Glove Mouse

A wearable BLE HID mouse built on the **XIAO ESP32-C6**, controlled by wrist movement (MPU-6050 gyroscope) and finger sensors (flex + FSR pressure).

---

## Hardware

| Component | Role |
|-----------|------|
| XIAO ESP32-C6 | Main MCU + BLE |
| MPU-6050 | Gyroscope / accelerometer → cursor movement |
| Flex sensor | Thumb bend → toggle transmission mode |
| FSR (×2) | Left / right click |
| MT3608 boost | Battery → ~4.6 V rail for VIN |
| LM339 (×2) | Analog comparators for flex & FSR digital output |

### Wiring

```
MPU-6050   SDA → GPIO 6   |   SCL → GPIO 7
Flex  DO       → GPIO 4     (thumb bend = transmit mode)
FSR Left  DO   → GPIO 2     (left click)
FSR Right DO   → GPIO 3     (right click)
```

---

## Firmware

### Dependencies (install via Arduino IDE Library Manager)

- **NimBLE-Arduino** by h2zero `≥ 1.4.0`
- **MPU6050** by Electronic Cats

### Board setup

1. Add ESP32 board package URL in Arduino IDE preferences:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
2. Install **esp32** by Espressif Systems
3. Select board: **XIAO ESP32C6**

### Usage

1. Flash `glove_mouse/glove_mouse.ino`
2. Open Serial Monitor at **115200 baud**
3. Pair with **"Glove Mouse"** from your host's Bluetooth settings
4. **Bend thumb** → transmission mode (cursor follows wrist, FSR triggers clicks)
5. **Release thumb** → sleep mode (all input paused)

### Tuning parameters

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_MOVE` | 20 | Max pixels per frame (higher = more sensitive) |
| `MAX_DPS` | 200 | Gyro threshold for full speed (°/s) |
| `DEADZONE` | 5 | Dead zone in °/s (higher = less jitter) |
| `CURVE_EXP` | 1.5 | Speed curve exponent (1.0 = linear, >1 = precise low / fast high) |
| `EMA_ALPHA` | 0.25 | Smoothing factor (0.1 = very smooth, 0.4 = responsive) |

---

## Repository Structure

```
glove_mouse/
└── glove_mouse.ino          Main BLE HID firmware

tests/
├── all_sensors_test/        All sensors combined diagnostic
├── flex_sensor_test/        Flex sensor digital output test
├── mpu6050_test/            MPU-6050 I2C + gyro/accel readout
└── pressure_sensor_test/    FSR pressure sensor test
```

---

## Running the Tests

Each folder under `tests/` is a standalone Arduino sketch.  
Open the `.ino` file in Arduino IDE, select **XIAO ESP32C6**, upload, then open Serial Monitor at **115200 baud**.

| Sketch | What it prints |
|--------|---------------|
| `mpu6050_test` | Accel XYZ + Gyro XYZ raw values |
| `flex_sensor_test` | Digital output of flex comparator (0/1) |
| `pressure_sensor_test` | Digital output of left & right FSR (0/1) |
| `all_sensors_test` | All of the above combined |

---

## License

MIT
