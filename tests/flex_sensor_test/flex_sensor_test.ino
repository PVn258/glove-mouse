/*
 * Flex 弯曲传感器调试草图
 *
 * 接线：
 *   VCC → 3.3V  |  GND → GND
 *   DO  → GPIO 17  (数字开关量，与主程序一致)
 *   AO  → 自定义（见 PIN_FLEX_AO，仅用于标定）
 *
 * 触发逻辑（与主程序一致）：
 *   弯曲拇指 → DO 输出 LOW  → flex_active = true（传输模式）
 *   伸直拇指 → DO 输出 HIGH → flex_active = false（休眠模式）
 *   若方向相反，请调节模块蓝色电位器
 *
 * 模式切换（修改 PLOTTER_MODE）：
 *   false → Serial Monitor：DO 状态文字 + AO 数值
 *   true  → Serial Plotter：AO 波形曲线（标定用）
 */

#define PIN_FLEX_DO   17     // 与主程序 PIN_FLEX_DO 一致
#define PIN_FLEX_AO   A0     // AO 引脚：按实际接线修改，仅用于标定，主程序不使用

#define PLOTTER_MODE  false

// ── 防抖（与主程序 debounce() 完全一致，40ms） ─────────────────
const uint32_t DEBOUNCE_MS = 40;
bool     last_flex   = false;
bool     flex_active = false;
uint32_t flex_ts     = 0;

bool debounce(bool raw, bool& last, bool& confirmed, uint32_t& ts) {
    if (raw != last) { last = raw; ts = millis(); }
    if ((millis() - ts) >= DEBOUNCE_MS && raw != confirmed) {
        confirmed = raw;
        return true;
    }
    return false;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    // INPUT_PULLUP：比较器 DO 为开漏，不上拉会浮空误触
    pinMode(PIN_FLEX_DO, INPUT_PULLUP);

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);  // 量程 0-3.3V

    if (!PLOTTER_MODE) {
        Serial.println("=== Flex 弯曲传感器调试 ===");
        Serial.println("弯曲拇指 → DO=LOW → 传输模式  |  伸直 → DO=HIGH → 休眠模式");
        Serial.println("若方向相反，调节模块蓝色电位器");
        Serial.println("---");
    } else {
        Serial.println("AO_Raw");
    }
}

void loop() {
    uint32_t now = millis();

    // 读取原始状态（LOW = 弯曲触发，与主程序一致）
    bool raw_flex = (digitalRead(PIN_FLEX_DO) == LOW);
    debounce(raw_flex, last_flex, flex_active, flex_ts);

    // AO 均值（8次采样）
    int ao_sum = 0;
    for (int i = 0; i < 8; i++) ao_sum += analogRead(PIN_FLEX_AO);
    int   ao_avg     = ao_sum / 8;
    float ao_voltage = ao_avg * 3.3f / 4095.0f;

    if (PLOTTER_MODE) {
        Serial.println(ao_avg);
    } else {
        Serial.print("DO 原始: ");
        Serial.print(raw_flex   ? "LOW (弯曲)" : "HIGH(伸直)");
        Serial.print("  防抖后: ");
        Serial.print(flex_active ? "[传输模式]  " : "[休眠模式]  ");
        Serial.print("AO: ");
        Serial.print(ao_avg);
        Serial.print("/4095  (");
        Serial.print(ao_voltage, 3);
        Serial.println(" V)");
    }

    delay(100);
}
