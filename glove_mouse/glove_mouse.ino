/*
 * Glove Mouse — BLE HID 鼠标固件
 * 硬件：ESP32C6
 *
 * 接线：
 *   MPU-6050  SDA → GPIO 6  |  SCL → GPIO 7
 *   Flex  DO  → GPIO 4        (拇指弯曲 → 传输模式)
 *   FSR 左DO  → GPIO 2        (左键)
 *   FSR 右DO  → GPIO 3        (右键)
 *
 * 依赖库（Arduino IDE 库管理器安装）：
 *   · NimBLE-Arduino  by h2zero      ≥ 1.4.0
 *   · MPU6050         by Electronic Cats
 *
 * 使用方法：
 *   1. 上传固件，打开串口监视器 (115200 baud)
 *   2. 主机蓝牙搜索并配对 "Glove Mouse"
 *   3. 弯曲拇指 → 传输模式 (光标跟随手腕移动，FSR 触发点击)
 *   4. 松开拇指 → 休眠模式 (停止所有输入)
 *
 * 调参说明：
 *   MAX_MOVE     最大每帧像素（满速时输出，调大更灵敏）
 *   MAX_DPS      对应满速的陀螺仪角速度阈值
 *   DEADZONE     °/s 死区（调大抗手抖，调小响应快）
 *   CURVE_EXP    曲线指数：1.0=线性，>1=低速精准/高速快
 *   EMA_ALPHA    平滑系数：0.1=极平滑，0.4=响应快
 */

#include <Wire.h>
#include <MPU6050.h>
#include <NimBLEDevice.h>
#include <NimBLEServer.h>
#include <NimBLEHIDDevice.h>
#include <HIDTypes.h>

// ── 引脚定义（Seeed XIAO ESP32C6）────────────────────────────
#define SDA_PIN          6
#define SCL_PIN          7
#define PIN_FLEX_DO      17
#define PIN_FSR_LEFT_DO  23
#define PIN_FSR_RIGHT_DO 16

// ── 陀螺仪参数 ────────────────────────────────────────────────
#define GYRO_LSB      131.0f   // ±250°/s 量程对应 LSB 系数
#define DEADZONE      3.0f     // °/s 死区（低于此值=静止）
#define MAX_DPS       80.0f   // °/s，Y轴（俯仰）满速阈值
#define MAX_DPS_X     80.0f   // °/s，X轴（偏航）满速阈值
#define MAX_MOVE      32       // 满速时每帧最大像素位移（X轴）
#define MAX_MOVE_Y    18       // Y轴（上下）满速像素
#define RIGHT_BOOST   1.6f     // X轴向右的额外增益（>1 = 更容易向右）
#define CURVE_EXP     1.4f     // 曲线指数，必须 >1：低速精准/高速快速
                               //   >1 = 凹曲线：10%速→6%输出（精准）
                               //   <1 = 凸曲线：10%速→40%输出（抖动）
#define EMA_ALPHA     0.20f    // EMA 平滑系数（0~1，越小越平滑）

// ── 防抖参数 ──────────────────────────────────────────────────
#define DEBOUNCE_MS   40       // 与传感器测试保持一致

// ── HID 报表描述符（3 按键鼠标 + 相对 X/Y） ──────────────────
// Report ID 1: buttons(1B) + x(1B) + y(1B) = 3 字节
static const uint8_t reportMap[] = {
    USAGE_PAGE(1),       0x01,  // Generic Desktop
    USAGE(1),            0x02,  // Mouse
    COLLECTION(1),       0x01,  // Application
      REPORT_ID(1),      0x01,  //   Report ID = 1
      USAGE(1),          0x01,  //   Pointer
      COLLECTION(1),     0x00,  //   Physical

        // ── 按键：3 位有效 + 5 位填充 ────────────────
        USAGE_PAGE(1),   0x09,  //     Button Page
        USAGE_MINIMUM(1),0x01,  //     Button 1 (左键)
        USAGE_MAXIMUM(1),0x03,  //     Button 3 (中键)
        LOGICAL_MINIMUM(1),0x00,
        LOGICAL_MAXIMUM(1),0x01,
        REPORT_COUNT(1), 0x03,  //     3 按键位
        REPORT_SIZE(1),  0x01,
        HIDINPUT(1),     0x02,  //     Data, Var, Abs
        REPORT_COUNT(1), 0x01,  //     5 位填充
        REPORT_SIZE(1),  0x05,
        HIDINPUT(1),     0x03,  //     Const

        // ── X / Y 相对移动 ────────────────────────────
        USAGE_PAGE(1),   0x01,  //     Generic Desktop
        USAGE(1),        0x30,  //     X
        USAGE(1),        0x31,  //     Y
        LOGICAL_MINIMUM(1),0x81,// -127
        LOGICAL_MAXIMUM(1),0x7F,//  127
        REPORT_SIZE(1),  0x08,
        REPORT_COUNT(1), 0x02,
        HIDINPUT(1),     0x06,  //     Data, Var, Rel

      END_COLLECTION(0),
    END_COLLECTION(0)
};

// ── 全局对象 ──────────────────────────────────────────────────
MPU6050                mpu;
NimBLEServer*          bleServer    = nullptr;
NimBLEHIDDevice*       hidDevice    = nullptr;
NimBLECharacteristic*  inputReport  = nullptr;
volatile bool          bleConnected = false;

// ── Flex 防抖状态（40ms，模式切换用） ────────────────────────
bool     last_flex  = false;
uint32_t flex_ts    = 0;
bool     flex_active = false;
bool     prev_flex_active = false;

// ── 按键状态 ──────────────────────────────────────────────────
// 非对称防抖：按下立即响应，松开需稳定 LEFT_RELEASE_MS 才确认
// 解决 FSR 持续按压时信号抖动导致长按被误判为多次单击的问题
#define LEFT_RELEASE_MS  2   // 左键松开防抖（ms）；短于此的"抬起"视为抖动忽略
#define BTN_DEBOUNCE_MS  1    // 右键双向防抖时间
bool     last_raw_right = false;
uint32_t left_release_ts = 0,  right_db_ts = 0;
bool     deb_left   = false, deb_right  = false;
uint8_t  last_sent_buttons = 0;
bool     btn_dirty  = false;  // 按键状态已变，等待随下一帧发出

// ── EMA 平滑状态（进入传输模式时重置） ──────────────────────
float    ema_x = 0.0f, ema_y = 0.0f;

// ── 发送限速 ─────────────────────────────────────────────────
#define REPORT_INTERVAL_MS  16   // 移动报告 ~60Hz；与 20ms 连接间隔匹配，不积压队列
#define SERIAL_INTERVAL_MS  150  // 串口调试每 150ms 一次
uint32_t last_report_ms = 0;
uint32_t last_serial_ms = 0;

// ─────────────────────────────────────────────────────────────
//  BLE 连接回调
// ─────────────────────────────────────────────────────────────
class MyServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo) override {
        bleConnected = true;
        // 请求 20-30ms 连接间隔（16-24×1.25ms）
        // 不要请求 7.5ms：Windows 会在 30-60s 后强制重协商 → 重协商期间断流积压 → 卡顿
        // 20ms 是 Windows HID 电源策略的舒适区，不会触发重协商
        server->updateConnParams(connInfo.getConnHandle(), 16, 24, 0, 300);
        Serial.println("[BLE] 已连接！");
    }
    void onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason) override {
        bleConnected = false;
        Serial.println("[BLE] 连接断开，重新广播...");
        server->startAdvertising();
    }
};

// ─────────────────────────────────────────────────────────────
//  工具函数
// ─────────────────────────────────────────────────────────────

// 软件防抖（40ms 稳定确认，与 all_sensors_test 完全一致）
bool debounce(bool raw, bool& last, bool& confirmed, uint32_t& ts) {
    if (raw != last) { last = raw; ts = millis(); }
    if ((millis() - ts) >= DEBOUNCE_MS && raw != confirmed) {
        confirmed = raw;
        return true;
    }
    return false;
}

// 非线性曲线映射：死区→幂次曲线→截断
//   rightBoost：仅对正方向（向右）额外乘以增益，默认 1.0（不增益）
int8_t curveMap(float dps, float maxOut = MAX_MOVE, float maxDps = MAX_DPS,
                float rightBoost = 1.0f) {
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

// 发送 HID 鼠标报告（3 字节：按键 + dX + dY）
// notify(data, len) 直接发送：队列满时丢弃当前帧而非阻塞 loop()
void sendMouseReport(uint8_t buttons, int8_t dx, int8_t dy) {
    if (!bleConnected || inputReport == nullptr) return;
    uint8_t report[3] = { buttons, (uint8_t)dx, (uint8_t)dy };
    inputReport->notify(report, sizeof(report));
}

// ─────────────────────────────────────────────────────────────
//  BLE HID 初始化
// ─────────────────────────────────────────────────────────────
void initBLE() {
    NimBLEDevice::init("Glove Mouse");
    NimBLEDevice::setSecurityAuth(true, true, true);
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);

    bleServer = NimBLEDevice::createServer();
    bleServer->setCallbacks(new MyServerCallbacks());

    hidDevice   = new NimBLEHIDDevice(bleServer);
    inputReport = hidDevice->getInputReport(1);        // Report ID = 1

    hidDevice->setManufacturer("ESP32C6-Glove");
    hidDevice->setHidInfo(0x00, 0x01);                 // Country=0, Flags=NormallyConnectable

    hidDevice->setReportMap((uint8_t*)reportMap, sizeof(reportMap));
    hidDevice->startServices();

    NimBLEAdvertising* adv = bleServer->getAdvertising();
    adv->setAppearance(HID_MOUSE);
    adv->addServiceUUID(hidDevice->getHidService()->getUUID());
    adv->start();

    Serial.println("[BLE] 广播中... 请在主机蓝牙中搜索 \"Glove Mouse\"");
}

// ─────────────────────────────────────────────────────────────
//  setup
// ─────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    // GPIO 初始化
    // FSR/Flex 比较器 DO 为开漏输出：按下主动拉低，不按时高阻抗
    // 必须启用内部上拉，否则拔掉 USB 后引脚浮空，随机触发按键
    pinMode(PIN_FLEX_DO,      INPUT_PULLUP);
    pinMode(PIN_FSR_LEFT_DO,  INPUT_PULLUP);
    pinMode(PIN_FSR_RIGHT_DO, INPUT_PULLUP);

    // MPU-6050 初始化（400kHz 快速模式，减少 I2C 阻塞时间）
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(400000);
    mpu.initialize();
    if (!mpu.testConnection()) {
        Serial.println("[ERR] MPU-6050 连接失败！检查 SDA/SCL 接线后重启。");
        while (true) delay(1000);
    }
    Serial.println("[OK]  MPU-6050 就绪");

    // BLE HID 初始化
    initBLE();

    Serial.println("=== Glove Mouse 固件就绪 ===");
    Serial.println("弯曲拇指 → 传输模式 | 松开拇指 → 休眠模式");
    Serial.println("---");
}

// ─────────────────────────────────────────────────────────────
//  loop  (100 Hz)
// ─────────────────────────────────────────────────────────────
void loop() {
    uint32_t now = millis();

    // ── 1. 读取传感器 ────────────────────────────────────────
    bool raw_flex  = (digitalRead(PIN_FLEX_DO)      == LOW);
    bool raw_left  = (digitalRead(PIN_FSR_LEFT_DO)  == LOW);
    bool raw_right = (digitalRead(PIN_FSR_RIGHT_DO) == LOW);

    // ── 2. Flex 防抖（40ms，仅用于模式切换） ─────────────────
    debounce(raw_flex, last_flex, flex_active, flex_ts);

    // ── 3. 按键通道（与 flex 完全独立） ──────────────────────────
    // 左键：非对称防抖
    //   按下 → 立即确认（不错过点击）
    //   松开 → 需稳定 LEFT_RELEASE_MS 才确认（忽略持续按压中的短暂抖动）
    if (raw_left) {
        deb_left = true;           // 按下：立即
        left_release_ts = 0;       // 重置松开计时
    } else if (deb_left) {         // 原本是按下，现在信号消失
        if (left_release_ts == 0) left_release_ts = now;
        if (now - left_release_ts >= LEFT_RELEASE_MS) deb_left = false;
    }

    // 右键：1ms 双向防抖
    if (raw_right != last_raw_right){ last_raw_right = raw_right; right_db_ts = now; }
    if ((now - right_db_ts) >= BTN_DEBOUNCE_MS) deb_right = raw_right;

    uint8_t buttons = (deb_left ? 0x01 : 0x00) | (deb_right ? 0x02 : 0x00);
    if (buttons != last_sent_buttons) {
        last_sent_buttons = buttons;
        btn_dirty = true;   // 标记待发，不立即发——避免用 0,0 打断正在进行的移动
    }

    // ── 4. 传输模式：陀螺仪移动（独立限速） ──────────────────
    if (flex_active) {
        if (!prev_flex_active) { ema_x = 0.0f; ema_y = 0.0f; }  // 入场重置

        if (now - last_report_ms >= REPORT_INTERVAL_MS) {
            // 断流保护：若距上次发送超 80ms（重连/干扰后），重置 EMA 并跳过本帧
            // 避免积压的陈旧运动数据在恢复时一次性涌出导致主机卡顿
            if (now - last_report_ms > 80) {
                ema_x = 0.0f; ema_y = 0.0f;
                last_report_ms = now;
                prev_flex_active = flex_active;
                return;
            }
            last_report_ms = now;

            int16_t ax, ay, az, gx, gy, gz;
            mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

            float combined_x = (gy - gz) / GYRO_LSB;  // 小臂旋转 + 手腕侧弯
            float gx_dps     = gx / GYRO_LSB;

            ema_x = EMA_ALPHA * combined_x + (1.0f - EMA_ALPHA) * ema_x;
            ema_y = EMA_ALPHA * gx_dps     + (1.0f - EMA_ALPHA) * ema_y;

            int8_t mx = curveMap(-ema_x, MAX_MOVE,   MAX_DPS_X, RIGHT_BOOST);
            int8_t my = curveMap(-ema_y, MAX_MOVE_Y, MAX_DPS);

            // 有移动 或 按键状态待发 → 合并进同一帧，消除按键触发时的移动停顿
            if (mx || my || btn_dirty) {
                sendMouseReport(last_sent_buttons, mx, my);
                btn_dirty = false;
            }

            // 串口调试（Serial.printf 在此处调用，已在 BLE 发送之后，不影响发送时序）
            if (now - last_serial_ms >= SERIAL_INTERVAL_MS) {
                last_serial_ms = now;
                Serial.printf("[传输] 左:%s 右:%s | dX:%4d dY:%4d\n",
                    deb_left ? "▼" : "○", deb_right ? "▼" : "○",
                    (int)mx, (int)my);
            }
        }
    }

    // ── 5. 非传输模式下：若按键状态待发则立即发（无移动帧可搭载） ──
    if (!flex_active && btn_dirty) {
        sendMouseReport(last_sent_buttons, 0, 0);
        btn_dirty = false;
    }

    // ── 6. 模式切换：退出传输时发一次零移动确保干净 ──────────
    if (prev_flex_active && !flex_active) {
        sendMouseReport(last_sent_buttons, 0, 0);
        Serial.println("[休眠]");
    }

    prev_flex_active = flex_active;
}
