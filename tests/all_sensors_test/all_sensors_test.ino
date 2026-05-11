/*
 * 三传感器综合测试草图
 *
 * 在不连接蓝牙主机的情况下，验证所有传感器读数和状态逻辑正确。
 * 所有引脚、极性、防抖逻辑与主程序 glove_mouse.ino 完全同步。
 *
 * 接线汇总（与主程序一致）：
 *   MPU-6050  SDA → GPIO 0  |  SCL → GPIO 1
 *   Flex DO   → GPIO 17
 *   FSR 左DO  → GPIO 23  |  FSR 右DO → GPIO 16
 *
 * 依赖库：MPU6050 by Electronic Cats
 *
 * Serial Monitor 输出示例：
 *   [传输] 左:[按下] 右:[----] | dX:  12 dY:  -3  (EMA X: 8.2  Y:-2.1)
 *   [休眠] 左:[----] 右:[----] | 静止
 */

#include <Wire.h>
#include <MPU6050.h>

// ── 引脚定义（与主程序完全一致） ──────────────────────────────
#define SDA_PIN          0
#define SCL_PIN          1
#define PIN_FLEX_DO      17
#define PIN_FSR_LEFT_DO  23
#define PIN_FSR_RIGHT_DO 16

// ── 陀螺仪参数（与主程序完全一致） ────────────────────────────
#define GYRO_LSB    131.0f
#define DEADZONE    3.0f
#define MAX_DPS     80.0f
#define MAX_DPS_X   80.0f
#define MAX_MOVE    32
#define MAX_MOVE_Y  18
#define RIGHT_BOOST 1.6f
#define CURVE_EXP   1.4f
#define EMA_ALPHA   0.20f

// ── 防抖参数（与主程序完全一致） ──────────────────────────────
#define FLEX_DEBOUNCE_MS  40    // Flex 模式切换防抖
#define LEFT_RELEASE_MS   25    // 左键松开防抖（非对称）
#define BTN_DEBOUNCE_MS   1     // 右键双向防抖

MPU6050 mpu;

// ── Flex 防抖状态 ─────────────────────────────────────────────
bool     last_flex   = false;
bool     flex_active = false;
uint32_t flex_ts     = 0;

// ── 左键非对称防抖状态 ────────────────────────────────────────
bool     deb_left        = false;
uint32_t left_release_ts = 0;

// ── 右键双向防抖状态 ──────────────────────────────────────────
bool     last_raw_right = false;
bool     deb_right      = false;
uint32_t right_db_ts    = 0;

// ── EMA 状态 ──────────────────────────────────────────────────
float ema_x = 0.0f, ema_y = 0.0f;
bool  prev_flex = false;

// ── 通用防抖（Flex 使用） ─────────────────────────────────────
bool debounce(bool raw, bool& last, bool& confirmed, uint32_t& ts) {
    if (raw != last) { last = raw; ts = millis(); }
    if ((millis() - ts) >= FLEX_DEBOUNCE_MS && raw != confirmed) {
        confirmed = raw;
        return true;
    }
    return false;
}

// ── 与主程序完全相同的曲线映射 ───────────────────────────────
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

void setup() {
    Serial.begin(115200);
    delay(500);

    // INPUT_PULLUP：比较器/Flex DO 为开漏，不上拉会浮空误触
    pinMode(PIN_FLEX_DO,      INPUT_PULLUP);
    pinMode(PIN_FSR_LEFT_DO,  INPUT_PULLUP);
    pinMode(PIN_FSR_RIGHT_DO, INPUT_PULLUP);

    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(400000);   // 400kHz，与主程序一致

    mpu.initialize();
    if (!mpu.testConnection()) {
        Serial.println("[ERR] MPU-6050 连接失败！检查 SDA->GPIO0 / SCL->GPIO1 接线后重启。");
        while (true) delay(1000);
    }

    Serial.println("=== 综合传感器测试（与主程序逻辑完全一致）===");
    Serial.println("弯曲拇指(GPIO17 LOW) → 传输模式 | 左键(GPIO23 LOW) | 右键(GPIO16 LOW)");
    Serial.println("---");
}

void loop() {
    uint32_t now = millis();

    // ── 1. 读取原始状态（LOW = 触发，与主程序一致） ───────────
    bool raw_flex  = (digitalRead(PIN_FLEX_DO)      == LOW);
    bool raw_left  = (digitalRead(PIN_FSR_LEFT_DO)  == LOW);
    bool raw_right = (digitalRead(PIN_FSR_RIGHT_DO) == LOW);

    // ── 2. Flex 防抖（40ms） ──────────────────────────────────
    debounce(raw_flex, last_flex, flex_active, flex_ts);

    // ── 3. 左键非对称防抖（按下立即，松开稳定 25ms） ─────────
    if (raw_left) {
        deb_left        = true;
        left_release_ts = 0;
    } else if (deb_left) {
        if (left_release_ts == 0) left_release_ts = now;
        if (now - left_release_ts >= LEFT_RELEASE_MS) deb_left = false;
    }

    // ── 4. 右键双向防抖（1ms） ────────────────────────────────
    if (raw_right != last_raw_right) { last_raw_right = raw_right; right_db_ts = now; }
    if ((now - right_db_ts) >= BTN_DEBOUNCE_MS) deb_right = raw_right;

    // ── 5. 陀螺仪 + 光标仿真（传输模式才计算） ───────────────
    int8_t mx = 0, my = 0;
    float  cur_ema_x = 0, cur_ema_y = 0;

    if (flex_active) {
        if (!prev_flex) { ema_x = 0.0f; ema_y = 0.0f; }  // 入场重置

        int16_t ax, ay, az, gx, gy, gz;
        mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

        // 与主程序完全相同的轴融合
        float combined_x = (gy - gz) / GYRO_LSB;
        float gx_dps     = gx / GYRO_LSB;

        ema_x = EMA_ALPHA * combined_x + (1.0f - EMA_ALPHA) * ema_x;
        ema_y = EMA_ALPHA * gx_dps     + (1.0f - EMA_ALPHA) * ema_y;

        mx = curveMap(-ema_x, MAX_MOVE,   MAX_DPS_X, RIGHT_BOOST);
        my = curveMap(-ema_y, MAX_MOVE_Y, MAX_DPS);

        cur_ema_x = ema_x;
        cur_ema_y = ema_y;
    }

    prev_flex = flex_active;

    // ── 6. 输出 ───────────────────────────────────────────────
    Serial.print(flex_active ? "[传输] " : "[休眠] ");

    Serial.print("左:");
    Serial.print(deb_left  ? "[按下]" : "[----]");
    Serial.print("(原始:");
    Serial.print(raw_left  ? "LOW" : "HI ");
    Serial.print(")  右:");
    Serial.print(deb_right ? "[按下]" : "[----]");
    Serial.print("(原始:");
    Serial.print(raw_right ? "LOW" : "HI ");
    Serial.print(")");

    if (flex_active) {
        Serial.print("  |  dX:");
        if (mx >= 0) Serial.print(" ");
        Serial.print((int)mx);
        Serial.print(" dY:");
        if (my >= 0) Serial.print(" ");
        Serial.print((int)my);
        Serial.print("  (EMA X:");
        Serial.print(cur_ema_x, 1);
        Serial.print(" Y:");
        Serial.print(cur_ema_y, 1);
        Serial.print(")");
    } else {
        Serial.print("  |  静止（弯曲拇指进入传输模式）");
    }

    Serial.println();
    delay(50);
}
