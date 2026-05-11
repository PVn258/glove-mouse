/*
 * FSR402 压力传感器调试草图（双路）
 *
 * 接线（与主程序一致）：
 *   左键 FSR  DO → GPIO 23  |  右键 FSR  DO → GPIO 16
 *   AO 引脚按实际接线填写（仅用于标定，主程序不使用 AO）
 *
 * 触发逻辑（与主程序一致）：
 *   按压 → DO 输出 LOW  → 按键触发
 *   释放 → DO 输出 HIGH → 按键释放
 *   若方向相反，调节模块蓝色电位器
 *
 * 防抖逻辑（与主程序一致）：
 *   左键：非对称——按下立即确认，松开稳定 LEFT_RELEASE_MS 才确认
 *   右键：双向 1ms 防抖
 *
 * 模式切换（修改 PLOTTER_MODE）：
 *   false → Serial Monitor：DO 状态 + AO 数值
 *   true  → Serial Plotter：左右 AO 双曲线
 */

#define PIN_LEFT_DO       23     // 左键，与主程序 PIN_FSR_LEFT_DO 一致
#define PIN_RIGHT_DO      16     // 右键，与主程序 PIN_FSR_RIGHT_DO 一致
#define PIN_LEFT_AO       A1     // 左键 AO：按实际接线修改（仅标定用）
#define PIN_RIGHT_AO      A2     // 右键 AO：按实际接线修改（仅标定用）

#define LEFT_RELEASE_MS   25     // 左键松开防抖（与主程序一致）
#define BTN_DEBOUNCE_MS   1      // 右键双向防抖（与主程序一致）

#define PLOTTER_MODE      false

// ── 左键非对称防抖状态 ────────────────────────────────────────
bool     deb_left        = false;
uint32_t left_release_ts = 0;

// ── 右键双向防抖状态 ──────────────────────────────────────────
bool     last_raw_right = false;
bool     deb_right      = false;
uint32_t right_db_ts    = 0;

// ADC 均值（8次采样）
int readADCAvg(uint8_t pin) {
    int sum = 0;
    for (int i = 0; i < 8; i++) {
        sum += analogRead(pin);
        delayMicroseconds(200);
    }
    return sum / 8;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    // INPUT_PULLUP：比较器 DO 为开漏，不上拉会浮空误触（与主程序一致）
    pinMode(PIN_LEFT_DO,  INPUT_PULLUP);
    pinMode(PIN_RIGHT_DO, INPUT_PULLUP);

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    if (!PLOTTER_MODE) {
        Serial.println("=== FSR402 压力传感器调试 ===");
        Serial.println("按压传感器 → DO=LOW → 触发  |  释放 → DO=HIGH → 释放");
        Serial.println("若 DO 不响应：顺时针旋转模块蓝色电位器（增大灵敏度）");
        Serial.println("---");
    } else {
        Serial.println("Left_AO,Right_AO");
    }
}

void loop() {
    uint32_t now = millis();

    // 读取原始状态（LOW = 按压，与主程序一致）
    bool raw_left  = (digitalRead(PIN_LEFT_DO)  == LOW);
    bool raw_right = (digitalRead(PIN_RIGHT_DO) == LOW);

    // ── 左键非对称防抖（按下立即，松开稳定 LEFT_RELEASE_MS） ──
    if (raw_left) {
        deb_left         = true;
        left_release_ts  = 0;
    } else if (deb_left) {
        if (left_release_ts == 0) left_release_ts = now;
        if (now - left_release_ts >= LEFT_RELEASE_MS) deb_left = false;
    }

    // ── 右键双向防抖 ──────────────────────────────────────────
    if (raw_right != last_raw_right) { last_raw_right = raw_right; right_db_ts = now; }
    if ((now - right_db_ts) >= BTN_DEBOUNCE_MS) deb_right = raw_right;

    // ── AO 读取 ───────────────────────────────────────────────
    int   left_ao   = readADCAvg(PIN_LEFT_AO);
    int   right_ao  = readADCAvg(PIN_RIGHT_AO);
    float left_v    = left_ao  * 3.3f / 4095.0f;
    float right_v   = right_ao * 3.3f / 4095.0f;

    if (PLOTTER_MODE) {
        Serial.print(left_ao);
        Serial.print(",");
        Serial.println(right_ao);
    } else {
        Serial.print("左键 DO:");
        Serial.print(raw_left  ? "LOW(按)" : "HI(放)");
        Serial.print(" 防抖后:");
        Serial.print(deb_left  ? "[按下]  " : "[释放]  ");
        Serial.print("AO:");
        Serial.print(left_ao);
        Serial.print("(");
        Serial.print(left_v, 2);
        Serial.print("V)");

        Serial.print("  |  右键 DO:");
        Serial.print(raw_right ? "LOW(按)" : "HI(放)");
        Serial.print(" 防抖后:");
        Serial.print(deb_right ? "[按下]  " : "[释放]  ");
        Serial.print("AO:");
        Serial.print(right_ao);
        Serial.print("(");
        Serial.print(right_v, 2);
        Serial.println("V)");
    }

    delay(80);
}
