/*
 * MPU-6050 陀螺仪/加速度计调试草图
 *
 * 接线（与主程序一致）：
 *   SDA → GPIO 0  |  SCL → GPIO 1  |  VCC → 3.3V  |  GND → GND  |  AD0 → GND
 *
 * 依赖库：MPU6050 by Electronic Cats
 *
 * TEST_MODE 说明（修改下方宏切换）：
 *   0 = I2C 扫描：确认 0x68 地址出现
 *   1 = 原始六轴数据（LSB，Serial Monitor）
 *   2 = Serial Plotter 六轴波形
 *   3 = 转换后 °/s 和 g（直观）
 *   4 = 光标仿真：完全还原主程序的 EMA + 死区 + 曲线映射输出
 *       → 不连蓝牙也能调参，看到实际鼠标会输出多少像素/帧
 */

#include <Wire.h>
#include <MPU6050.h>

#define SDA_PIN   0    // 与主程序一致
#define SCL_PIN   1    // 与主程序一致
#define TEST_MODE 4    // ← 修改这里切换模式

MPU6050 mpu;

// ── 模式 4 参数（与主程序完全同步） ──────────────────────────
#define GYRO_LSB    131.0f
#define DEADZONE    3.0f
#define MAX_DPS     80.0f
#define MAX_DPS_X   80.0f
#define MAX_MOVE    32
#define MAX_MOVE_Y  18
#define RIGHT_BOOST 1.6f
#define CURVE_EXP   1.4f
#define EMA_ALPHA   0.20f

float ema_x = 0.0f, ema_y = 0.0f;

// 与主程序 curveMap() 完全相同
int8_t curveMap(float dps, float maxOut, float maxDps, float rightBoost = 1.0f) {
    float abs_dps = fabsf(dps);
    if (abs_dps < DEADZONE) return 0;
    float norm = (abs_dps - DEADZONE) / (maxDps - DEADZONE);
    if (norm > 1.0f) norm = 1.0f;
    float output = powf(norm, CURVE_EXP) * maxOut;
    if (dps > 0.0f) {
        output *= rightBoost;
        if (output > 127.0f) output = 127.0f;
        return (int8_t)output;
    }
    return (int8_t)(-output);
}

// ── 模式 0：I2C 扫描 ──────────────────────────────────────────
void i2cScan() {
    Serial.println("=== I2C 设备扫描 ===");
    int found = 0;
    for (byte addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.print("发现设备，I2C 地址: 0x");
            if (addr < 16) Serial.print("0");
            Serial.print(addr, HEX);
            if (addr == 0x68) Serial.print("  <- MPU-6050 (AD0=GND)");
            if (addr == 0x69) Serial.print("  <- MPU-6050 (AD0=3.3V)");
            Serial.println();
            found++;
        }
    }
    if (found == 0) Serial.println("未发现任何设备！检查 SDA/SCL 接线和供电。");
    Serial.println("扫描完成，5秒后重新扫描...\n");
    delay(5000);
}

// ── 模式 1：原始数据 ──────────────────────────────────────────
void printRaw() {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    Serial.print("AX:"); Serial.print(ax);
    Serial.print(" AY:"); Serial.print(ay);
    Serial.print(" AZ:"); Serial.print(az);
    Serial.print(" | GX:"); Serial.print(gx);
    Serial.print(" GY:"); Serial.print(gy);
    Serial.print(" GZ:"); Serial.println(gz);
}

// ── 模式 2：Serial Plotter ────────────────────────────────────
void printPlotter() {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    Serial.print("AX:"); Serial.print(ax);
    Serial.print(",AY:"); Serial.print(ay);
    Serial.print(",AZ:"); Serial.print(az);
    Serial.print(",GX:"); Serial.print(gx);
    Serial.print(",GY:"); Serial.print(gy);
    Serial.print(",GZ:"); Serial.println(gz);
}

// ── 模式 3：转换后单位 ────────────────────────────────────────
void printConverted() {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    float accel_x = ax / 16384.0f;
    float accel_y = ay / 16384.0f;
    float accel_z = az / 16384.0f;
    float gyro_x  = gx / GYRO_LSB;
    float gyro_y  = gy / GYRO_LSB;
    float gyro_z  = gz / GYRO_LSB;
    Serial.print("加速度(g)  X:");  Serial.print(accel_x, 3);
    Serial.print(" Y:");            Serial.print(accel_y, 3);
    Serial.print(" Z:");            Serial.print(accel_z, 3);
    Serial.print(" | 角速度(deg/s) X:"); Serial.print(gyro_x, 1);
    Serial.print(" Y:");                 Serial.print(gyro_y, 1);
    Serial.print(" Z:");                 Serial.println(gyro_z, 1);
    if (abs(accel_z) < 0.85f || abs(accel_z) > 1.15f)
        Serial.println("  ! AZ 不在 1g 附近，传感器未水平放置或需重新上电");
}

// ── 模式 4：光标仿真（完全还原主程序映射逻辑） ───────────────
// 输出：EMA 平滑后的 °/s、死区判断、最终 dX/dY 像素值
// 用途：不连蓝牙即可直接调 DEADZONE/CURVE_EXP/EMA_ALPHA/MAX_MOVE 等参数
void printCursorSim() {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    // 与主程序完全相同的轴融合：小臂旋转(GY) + 手腕侧弯(GZ) → X 轴
    float combined_x = (gy - gz) / GYRO_LSB;
    float gx_dps     = gx / GYRO_LSB;

    // EMA 平滑
    ema_x = EMA_ALPHA * combined_x + (1.0f - EMA_ALPHA) * ema_x;
    ema_y = EMA_ALPHA * gx_dps     + (1.0f - EMA_ALPHA) * ema_y;

    // 曲线映射（与主程序 curveMap 完全相同）
    int8_t mx = curveMap(-ema_x, MAX_MOVE,   MAX_DPS_X, RIGHT_BOOST);
    int8_t my = curveMap(-ema_y, MAX_MOVE_Y, MAX_DPS);

    Serial.print("原始(deg/s) X:");
    Serial.print(combined_x, 1);
    Serial.print(" Y:");
    Serial.print(gx_dps, 1);
    Serial.print("  |  EMA X:");
    Serial.print(ema_x, 2);
    Serial.print(" Y:");
    Serial.print(ema_y, 2);
    Serial.print("  |  输出像素 dX:");
    Serial.print((int)mx);
    Serial.print(" dY:");
    Serial.println((int)my);
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(400000);   // 400kHz，与主程序一致

    if (TEST_MODE == 0) {
        Serial.println("MPU-6050 调试 - 模式 0: I2C 扫描");
        return;
    }

    mpu.initialize();
    if (!mpu.testConnection()) {
        Serial.println("MPU-6050 连接失败！");
        Serial.println("检查：SDA->GPIO0  SCL->GPIO1  VCC->3.3V  AD0->GND");
        while (true) delay(1000);
    }

    Serial.print("MPU-6050 连接成功，模式 ");
    Serial.println(TEST_MODE);

    if (TEST_MODE == 2) Serial.println("AX,AY,AZ,GX,GY,GZ");
    if (TEST_MODE == 4) {
        Serial.println("--- 光标仿真模式：还原主程序完整映射链 ---");
        Serial.println("参数: DEADZONE=" + String(DEADZONE,1)
            + " CURVE_EXP=" + String(CURVE_EXP,1)
            + " EMA=" + String(EMA_ALPHA,2)
            + " MAX_MOVE=" + String(MAX_MOVE)
            + " RIGHT_BOOST=" + String(RIGHT_BOOST,1));
        Serial.println("---");
        ema_x = 0.0f; ema_y = 0.0f;
    }
}

void loop() {
    switch (TEST_MODE) {
        case 0: i2cScan();                      break;
        case 1: printRaw();       delay(100);   break;
        case 2: printPlotter();   delay(16);    break;  // ~60Hz，与主程序一致
        case 3: printConverted(); delay(100);   break;
        case 4: printCursorSim(); delay(16);    break;  // ~60Hz，与主程序一致
    }
}
