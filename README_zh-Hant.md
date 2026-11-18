# 中華電力 (香港) Home Assistant 能源統計自訂整合組件

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

本整合組件可將香港中華電力（CLP）的帳單、當期用電估算、各階梯電價與即時用量，以及每小時智慧電表用電數據無縫同步至 Home Assistant，並支援直接接入 Home Assistant 官方能源儀表板（Energy Dashboard）。

---

## 🌟 核心功能特性

* **⚡ 能源儀表板原生無縫接入**：深度整合 Home Assistant 長期統計系統（Long-Term Statistics），徹底解決中電官方數據天然延遲 3 小時導致的圖表錯位問題，歷史用電量精確對齊到真實整點。
* **📊 官方階梯電價全動態拉取**：每月自動從中華電力官方計費 API 獲取最新各階梯單價、燃料調整費（Fuel Clause Adjustment）與特別燃料回扣，自適應官方未來任意層級的階梯調整。
* **🔄 自適應 N 階梯與自訂電價**：
  * 支援自訂任意 $N$ 階梯數量（如 1 檔單一固定價、3 檔、5 檔或中電標準 7 檔）。
  * 內建智慧協調演算法（`reconcile_tariff_tiers`），自動平滑對齊單價與分界限額，完美相容中文全形逗號與英文半形逗號。
  * 支援鎖定自訂固定電價、自訂燃料調整費、每期政府電費補貼（Subsidy）扣減，以及關聯外部實體動態電價。
* **🔍 專屬診斷資訊實體（Diagnostic Entities）**：
  * **各階梯用電量 (`sensor.clp_tier_consumption`)**：清晰顯示當前所處用電階梯，並在屬性中提供每一階梯的已用電量、額度上限、剩餘額度、用電比例及當期預估用量分佈。
  * **各階梯電價明細 (`sensor.clp_tier_rates`)**：顯示當前生效的基礎單價，並在屬性中輸出各檔階梯單價表與用電分界。
* **🌱 支援可再生能源（上網電價計劃 FiT）**：完美支援民間太陽能/風能上網電價（Feed-in Tariff）帳戶的發電設備發電量與帳單統計。
* **💰 官方節能回扣機制精準還原**：完全遵循中電雙月用電總額不多於 400 度的官方階梯回扣規則（1~200 度回扣 17.2 仙/度，201~300 度回扣 16.2 仙/度，301~400 度回扣 15.2 仙/度）。
* **🛡️ 智慧 Token 自動續期與原生重新認證**：
  * 週期性平滑刷新 Access Token，無需重複手動登入。
  * Token 失效時自動在 HA 前端觸發原生「重新認證（Reauth）」卡片，一鍵貼上即可秒級恢復。
* **⏱️ 分級輪詢與流控保護**：每小時數據（60m）、每日統計（12h）、帳戶/帳單/預估（5m 節流），保護您的帳戶免受中電介面速率限制。

---

## 目錄

- [安裝方法](#安裝方法)
  - [先決條件](#先決條件)
  - [新增至 HACS](#新增至-hacs)
  - [手動安裝](#手動安裝)
- [設定與身分驗證](#設定與身分驗證)
  - [設定流程](#設定流程)
  - [獲取中電 Token 憑證](#獲取中電-token-憑證)
  - [一鍵貼上與支援格式](#一鍵貼上與支援格式)
- [能源儀表板整合 (解決 3 小時延遲錯位)](#能源儀表板整合-解決-3-小時延遲錯位)
- [完整實體與感測器列表](#完整實體與感測器列表)
  - [常規感測器](#常規感測器)
  - [診斷資訊實體 (Diagnostic)](#診斷資訊實體-diagnostic)
- [Home Assistant 感測器設定參數詳解](#home-assistant-感測器設定參數詳解)
- [階梯電價與自訂計費機制說明](#階梯電價與自訂計費機制說明)
- [重新登入與重新認證](#重新登入與重新認證)
- [常見問題與除錯](#常見問題與除錯)

---

## 安裝方法

### 先決條件

- 中電（CLP）登記客戶
- 中電官網個人網銀/帳戶登入憑證
- 已安裝中電智慧電表（用於獲取 `HOURLY` 每小時用電數據）

### 新增至 HACS

1. 確保已安裝 [HACS](https://hacs.xyz/docs/setup/prerequisites)
2. 在 Home Assistant 側邊欄點選 **HACS** ➔ **Integrations（整合）**
3. 點選右上角選單按鈕（三個點） ➔ 選擇 **Custom repositories（自訂儲存庫）**
4. 類別選擇 `Integration`，填入儲存庫網址 `https://github.com/thematrixdev/home-assistant-clp` 並點選 **新增**
5. 在整合列表中找到 **CLPHK**，點選右下角 **下載**
6. 重啟 Home Assistant

### 手動安裝

1. 下載本倉庫原始碼
2. 將 `custom_components/clphk` 資料夾複製至您的 Home Assistant 設定目錄中的 `custom_components/` 資料夾內
3. 重啟 Home Assistant

---

## 設定與身分驗證

### 設定流程

1. 前往 **設定** ➔ **裝置與服務** ➔ 點選右下角 **新增整合**
2. 搜尋並選擇 **CLPHK**
3. **第一步（指引）**：閱讀獲取憑證指引，點選「下一步」
4. **第二步（憑證）**：將複製的 Token 整段貼上至「一鍵貼上完整 Token 內容」框中
5. **第三步（選項）**：設定感測器名稱、用電階梯與資料更新偏好

---

### 獲取中電 Token 憑證

1. 開啟 Chrome 或 Edge 瀏覽器的 **無痕視窗**（`Ctrl+Shift+N` 或 `Cmd+Shift+N`）
2. 前往 [中電官網登入頁面](https://www.clp.com.hk/services/en/login) 並登入帳戶
3. 按 **F12**（或在網頁任意位置按右鍵選擇「檢查」）開啟開發者工具
4. 切換至 **Console（主控台）** 標籤頁，貼上並執行以下程式碼：
   ```javascript
   console.log("Access Token:\n" + localStorage.getItem("act") + "\n\nRefresh Token:\n" + localStorage.getItem("rct"));
   ```
5. 複製主控台輸出的全部文字內容。
6. **直接關閉無痕瀏覽器視窗**（**切勿點選「登出 / Sign Out」**）。
7. 返回 Home Assistant，將複製的文字直接貼上至 **「一鍵貼上完整 Token 內容」** 文字框。

> ⚠️ **重要警告**：獲取憑證後，**切勿點選中電網站上的「登出 / Sign Out」按鈕**！登出操作會立即使 Refresh Token 失效，導致整合無法繼續自動續期。獲取後直接關閉瀏覽器標籤頁或視窗即可。

*(備用手動方式：您亦可在開發者工具的 `Application` ➔ `Storage` ➔ `Local Storage` ➔ `https://www.clp.com.hk` 中分別複製 `act` 與 `rct` 鍵值)*

---

### 一鍵貼上與支援格式

在設定或重新認證對話框中，只需將複製的文字直接貼上入 **「一鍵貼上完整 Token 內容」** 欄位，系統內建智慧解析器會自動識別並提取：
- 包含 `Access Token:` 與 `Refresh Token:` 的主控台輸出整段文字
- 包含 `act`/`rct` 或 `access_token`/`refresh_token` 的單一 JSON 物件
- 兩個分別包含 `"data"` 的 JSON 物件 `{"data":"...","time":...,"expire":"..."}`
- 兩行獨立的 Base64 憑證字串

---

## 能源儀表板整合 (解決 3 小時延遲錯位)

由於中電官方系統的每小時用電數據天然延遲約 3 小時，傳統外掛若在「採集時刻」寫入狀態，會導致 Home Assistant 能源圖表整體向後偏移 3 個小時。

本整合深度整合了 Home Assistant 官方的 **長期統計系統（Long-Term Statistics，`async_add_external_statistics`）**：
- 自動讀取每筆數據的真實歷史整點時間（`startDate`，對齊到整點 UTC 時間戳記）；
- 精確將用電量與電費寫入對應的真實歷史時間段（例如 17:00-18:00 的用量準確記錄在 17:00，而非採集時的 20:00）；
- 自動在系統中生成外部統計實體：`clphk:main_hourly_energy`（名稱：`CLP Hourly Energy`）。

### 如何在能源儀表板中使用：
1. 前往 Home Assistant **設定** ➔ **儀表板** ➔ **能源**。
2. 在 **電網（Electricity Grid）** 區域點選 **新增消耗（Add Consumption）**。
3. 統計指標選擇 **CLP Hourly Energy** (`clphk:main_hourly_energy`)。
4. 電費計價方式可選擇關聯本整合提供的 **Projected Effective Tariff Rate** (`sensor.clp_projected_effective_tariff_rate`) 實體以動態追蹤單價。
5. 儲存後，您的電網每小時消耗圖表將與實際用電時段完全吻合！

---

## 完整實體與感測器列表

整合安裝後將自動為您註冊以下核心感測器及診斷實體：

### 常規感測器
| 實體 ID (推薦/預設) | 實體名稱 | 單位 | 描述 |
| :--- | :--- | :---: | :--- |
| `sensor.dian_li` | 主電量感測器 | `kWh` | 中電主讀數實體（可根據選項設定為小時、日或雙月狀態） |
| `sensor.clp_projected_cost` | Projected Cost | `HKD` | 中電官方/公式綜合預估當期帳單總費用 |
| `sensor.clp_current_period_consumption` | Current Period Consumption | `kWh` | 本計費帳期至今已消耗的實際總電量 |
| `sensor.clp_projected_consumption` | Projected Consumption | `kWh` | 中電官方結合歷史用電預測的本期總消耗電量 |
| `sensor.clp_last_bill_amount` | Last Bill Amount | `HKD` | 最近一期已出正式帳單的總應繳應收款金額 |
| `sensor.clp_outstanding_amount` | Outstanding Amount | `HKD` | 帳戶當前未結清餘額/欠費金額 |
| `sensor.clp_base_tariff_rate` | Base Tariff Rate | `HKD/kWh` | 基礎階梯電價（預設第 1 階梯基礎單價，屬性含完整階梯） |
| `sensor.clp_fuel_clause_adjustment` | Fuel Clause Adjustment | `HKD/kWh` | 當月最新燃料調整費（由中電每月依燃料成本調整公布） |
| `sensor.clp_projected_effective_tariff_rate` | Projected Effective Tariff Rate | `HKD/kWh` | **預估有效綜合單價**（預估總費用 / 預估總用量，推薦填入能源面板計費） |

### 診斷資訊實體 (Diagnostic)
位於裝置頁面「診斷資訊」區域，用於深入洞悉電量階梯分佈：
| 實體 ID | 實體名稱 | 主狀態 | 核心屬性說明 |
| :--- | :--- | :---: | :--- |
| `sensor.dian_li_tier_consumption` | Tier Consumption | `Tier X` (如 `Tier 1`) | **各階梯用量剖析**：`current_tier_used_kwh`（當前檔已用）、`current_tier_remaining_kwh`（當前檔剩餘）、各檔用電 `tier_1_used_kwh` ~ `tier_N_used_kwh`、用量字典 `tier_consumption_breakdown`、預估用量分佈 `projected_tier_breakdown` |
| `sensor.dian_li_tier_rates` | Tier Rates | 當前檔單價 (如 `0.945`) | **各階梯費率明細**：`current_tier_rate_hkd`、各檔單價 `tier_1_rate_hkd` ~ `tier_N_rate_hkd`、分界限額 `tier_1_limit_kwh` ~ `tier_N_limit_kwh`、單價字典 `tier_rates_breakdown` |

---

## Home Assistant 感測器設定參數詳解

| 參數鍵名 | 類型 | 預設值 | 說明 |
| :--- | :---: | :---: | :--- |
| `combined_tokens` | string | ` ` | 一鍵貼上完整 Token 內容（自動解析 ACT 與 RCT） |
| `access_token` | string | ` ` | 中電存取憑證（若已在上方一鍵框貼上則可留空） |
| `refresh_token` | string | ` ` | 中電刷新憑證（若已在上方一鍵框貼上則可留空） |
| `name` | string | `電力` | 整合/裝置名稱（將作為各子感測器命名前綴） |
| `timeout` | int | `30` | 網路連線與 API 逾時時間（秒） |
| `custom_fixed_rate` | float | `0.0` | **自訂固定電價（港幣/度）**：填 0 時自動採用中電動態階梯計費；若填入數值（如 1.25）則強制按固定電價核算。 |
| `custom_fuel_cents` | float | `0.0` | **自訂燃料調整費（分/度）**：填 0 時每月自動同步中電官方最新公布的燃料費；填入具體數值可手動鎖定。 |
| `custom_subsidy` | float | `0.0` | **每期電費補貼/資助（港幣）**：填入政府電費補貼或節能資助金額，帳單預估費用將自動予以扣減。 |
| `custom_rate_entity` | string | ` ` | **動態電價實體 ID**：可選填入外部實體（如 `input_number.clp_rate`），實現由外部動態控制電價。 |
| `custom_tier_rates` | string | ` ` | **自訂各階梯電價（港幣/度）**：逗號分隔的各階梯單價（如 `0.945, 1.079, 1.237...` 或 `1.0, 1.5, 2.0`），自適應任意階梯數量。 |
| `custom_tier_limits` | string | ` ` | **自訂各階梯限額（度/雙月）**：逗號分隔的前 N-1 檔限額（如 `400, 600, 800...` 或 `200, 300`），最後一檔自動作為無上限封頂階梯。 |
| `get_hourly` | boolean | `True` | 是否同步每小時用電（**能源儀表板必備**） |
| `get_hourly_days` | int | `2` | 歷史每小時數據回溯天數（建議 2 天，確保整點數據連續無中斷） |
| `get_daily` | boolean | `True` | 是否獲取每日用電量及費用（與官方每日日結完全一致） |
| `get_estimation` | boolean | `True` | 是否獲取當期用電預估與電費 |
| `get_bill` | boolean | `True` | 是否獲取過去 14 個月已出帳單記錄 |
| `renewable_energy_sensor_enable` | boolean | `False` | 是否啟用中電[可再生能源民間上網電價計劃 (FiT)](https://www.clp.com.hk/zh/business/low-carbon-solutions/renewable-energy/feed-in-tariff-business/application) 感測器 |
| `renewable_energy_sensor_name` | string | `電力 Renewable Energy` | 可再生能源感測器名稱 |
| `renewable_energy_sensor_get_bill` | boolean | `True` | 是否同步可再生能源發電帳單收益 |
| `renewable_energy_sensor_get_daily` | boolean | `True` | 是否同步可再生能源每日發電量 |
| `renewable_energy_sensor_get_hourly` | boolean | `True` | 是否同步可再生能源每小時發電量 |
| `renewable_energy_sensor_get_hourly_days` | int | `2` | 可再生能源每小時數據天數 |

---

## 階梯電價與自訂計費機制說明

### 1. 中電官方標準雙月階梯（預設自動同步）
中電住宅用電通常按雙月（約 60 天）帳期累進計費：
- **第 1 階梯**：首 400 度，單價 HK$0.945 / 度
- **第 2 階梯**：次 600 度（401~1000 度），單價 HK$1.079 / 度
- **第 3 阶梯**：次 800 度（1001~1800 度），單價 HK$1.237 / 度
- **第 4 阶梯**：次 800 度（1801~2600 度），單價 HK$1.545 / 度
- **第 5 阶梯**：次 800 度（2601~3400 度），單價 HK$1.774 / 度
- **第 6 阶梯**：次 800 度（3401~4200 度），單價 HK$1.878 / 度
- **第 7 阶梯**：4200 度以上全部用量，單價 HK$1.890 / 度

### 2. 中電官方節能回扣（Energy Saving Rebate）
針對雙月總用電量不多於 400 度的家庭，中電給予節能回扣：
- **1 至 200 度**：用電總量每度回扣 17.2 仙（HK$0.172 / 度）
- **201 至 300 度**：用電總量每度回扣 16.2 仙（HK$0.162 / 度）
- **301 至 400 度**：用電總量每度回扣 15.2 仙（HK$0.152 / 度）
- **超過 400 度**：無節能回扣。

### 3. 計費天數比例縮放
當雙月抄表帳期實際天數少於 55 天或多於 65 天時，各階梯用電限額將按 `實際天數 / 60` 自動進行等比例線性縮放，保證與中電帳單演算法精確一致。

---

## 重新登入與重新認證

本整合使用 `access_token` + `refresh_token` 機制。

### 自動刷新
- 系統後台會在 Access Token 臨近失效時自動呼叫中電介面無感刷新，無需人工干預。

### 原生重新認證 (Re-authentication)
- 若中電帳號在別處被登出導致 Refresh Token 失效，整合不會破壞系統運行；
- Home Assistant 將在「裝置與服務」頁面自動浮現 **「需要重新設定（Reconfigure）」** 警告卡片；
- 點選卡片後，重新貼上最新獲取的 Token，所有感測器與歷史統計即可瞬間無縫恢復。

---

## 常見問題與除錯

- **多帳戶問題**：若您的中電帳號下綁定了多個電表或物業，目前整合預設報告第一個活躍供電帳戶。
- **開啟 Debug 除錯日誌**：
  若遇到異常排查，可在 Home Assistant 的 `configuration.yaml` 中新增以下內容並重啟：
  ```yaml
  logger:
    default: info
    logs:
      custom_components.clphk: debug
  ```

---

## 社群與非官方交流群

- **Telegram 交流群**：https://t.me/smarthomehk

---

## 測試環境

- Home Assistant Container 2026.11+
- Python 3.13 / 3.14
- Linux aarch64 & x86_64

---

## 作者與維護者

* **原作者與主要維護者**：[@thematrixdev](https://github.com/thematrixdev)
* **貢獻者與共同維護者**：[@kanshurichard](https://github.com/kanshurichard)

