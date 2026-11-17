# 中華電力 (香港) Home Assistant 能源統計自訂整合組件

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

本整合組件可將香港中華電力（CLP）的帳單、估算以及每小時智慧電表用電數據無縫同步至 Home Assistant，並支援直接接入 Home Assistant 官方能源儀表板（Energy Dashboard）。

## 目錄

- [安裝方法](#安裝方法)
  - [先決條件](#先決條件)
  - [新增至 HACS](#新增至-hacs)
  - [手動安裝](#手動安裝)
- [配置與身份驗證](#配置與身份驗證)
  - [配置流程](#配置流程)
  - [獲取中電 Token 憑證](#獲取中電-token-憑證)
  - [一鍵貼上與支援格式](#一鍵貼上與支援格式)
- [能源儀表板整合 (解決 3 小時延遲錯位)](#能源儀表板整合-解決-3-小時延遲錯位)
- [Home Assistant 感測器配置參數](#home-assistant-感測器配置參數)
- [重新登入與重新認證](#重新登入與重新認證)
  - [手動重新登入](#手動重新登入)
  - [自動重新整理與原生重新認證](#自動重新整理與原生重新認證)
- [常見問題與除錯](#常見問題與除錯)

---

## 安裝方法

### 先決條件

- 中電（CLP）登記客戶
- 中電官網網上帳戶登入憑證
- 已安裝中電智慧電表（用於獲取 `HOURLY` 每小時用電數據）

### 新增至 HACS

1. 確保已安裝 [HACS](https://hacs.xyz/docs/setup/prerequisites)
2. 在 Home Assistant 側邊欄點選 **HACS** ➔ **Integrations（整合）**
3. 點選右上角選單按鈕（三個點） ➔ 選擇 **Custom repositories（自訂儲存庫）**
4. 類別選擇 `Integration`，填入儲存庫網址 `https://github.com/kanshurichard/home-assistant-clp` 並點擊 **新增**
5. 在整合列表中找到 **CLPHK**，點擊右下角 **下載**
6. 重新啟動 Home Assistant

### 手動安裝

1. 下載本專案源代碼
2. 將 `custom_components/clphk` 資料夾複製至您的 Home Assistant 配置目錄中的 `custom_components/` 資料夾內
3. 重新啟動 Home Assistant

---

## 配置與身份驗證

### 配置流程

1. 前往 **設定** ➔ **裝置與服務** ➔ 點擊右下角 **新增整合**
2. 搜尋並選擇 **CLPHK**
3. **第一步（指引）**：閱讀獲取憑證指引，點擊「下一步」
4. **第二步（憑證）**：將複製的 Token 整段貼入「一鍵貼上完整 Token 內容」框中
5. **第三步（選項）**：配置感測器名稱、資料更新項目（如啟用每小時用電）

---

### 獲取中電 Token 憑證

1. 開啟 Chrome 或 Edge 瀏覽器的 **無痕視窗**（`Ctrl+Shift+N` 或 `Cmd+Shift+N`）
2. 前往 [中電官網登入頁面](https://www.clp.com.hk/services/en/login) 並登入帳戶
3. 按 **F12**（或在網頁任意位置按右鍵選擇「檢查」）打開開發人員工具
4. 切換至 **Console（主控台）** 標籤頁，貼上並執行以下代碼：
   ```javascript
   console.log("Access Token:\n" + localStorage.getItem("act") + "\n\nRefresh Token:\n" + localStorage.getItem("rct"));
   ```
5. 複製主控台輸出的全部文字內容。
6. **直接關閉無痕瀏覽器視窗**（**切勿點擊「登出 / Sign Out」**）。
7. 返回 Home Assistant，將複製的文字直接貼入 **「一鍵貼上完整 Token 內容」** 文本框。

> ⚠️ **重要警告**：獲取憑證後，**切勿點擊中電網站上的「登出 / Sign Out」按鈕**！登出操作會立即使 Refresh Token 失效，導致整合無法繼續自動更新。獲取後直接關閉瀏覽器分頁或視窗即可。

*(備用手動方式：您亦可在開發人員工具的 `Application` ➔ `Storage` ➔ `Local Storage` ➔ `https://www.clp.com.hk` 中分別複製 `act` 與 `rct` 鍵值)*

---

### 一鍵貼上與支援格式

在配置或重新認證對話框中，只需將複製的文字直接貼入 **「一鍵貼上完整 Token 內容」** 欄位，系統內建智慧解析器會自動識別並提取：
- 包含 `Access Token:` 與 `Refresh Token:` 的控制台輸出整段文字
- 包含 `act`/`rct` 或 `access_token`/`refresh_token` 的單一 JSON 物件
- 兩個分別包含 `"data"` 的 JSON 物件 `{"data":"...","time":...,"expire":"..."}`
- 兩行獨立的 Base64 憑證字串

如果選擇分開填寫下方的獨立欄位，`Access Token` 和 `Refresh Token` 均支援以下格式：
1. 完整 JSON 物件：`{"data":"<base64-token>","time":...,"expire":"..."}`
2. JSON 字串值：`"<base64-token>"`
3. 純 Base64 字串：`<base64-token>`

---

## 能源儀表板整合 (解決 3 小時延遲錯位)

由於中電官方系統的每小時用電數據天然延遲約 3 小時，傳統外掛程式若在「採集時刻」寫入狀態，會導致 Home Assistant 能源圖表整體向後偏移 3 個小時。

本整合深度整合了 Home Assistant 官方的 **長期統計系統（Long-Term Statistics，`async_add_external_statistics`）**：
- 自動讀取每筆數據的真實歷史整點時間（`startDate`，頂整點 UTC 時間戳）；
- 精確將用電量寫入對應的歷史時間段（例如 17:00-18:00 的用量準確記錄在 17:00，而非採集時的 20:00）；
- 自動在系統中生成外部統計實體：`clphk:main_hourly_energy`（名稱：`CLP Hourly Energy`）。

### 如何在能源儀表板中使用：
1. 前往 Home Assistant **設定** ➔ **資訊主頁** ➔ **能源**。
2. 在 **電網（Electricity Grid）** 區塊點擊 **新增消耗（Add Consumption）**。
3. 統計指標選擇 **CLP Hourly Energy** (`clphk:main_hourly_energy`)。
4. 儲存後，您的電網每小時消耗圖表將與實際用電時段完全吻合！

---

## Home Assistant 感測器配置參數

| 參數鍵名 | 類型 | 必填 | 預設值 | 說明 |
| :--- | :--- | :---: | :--- | :--- |
| `combined_tokens` | string | | ` ` | 一鍵貼上完整 Token（可直接貼入整段輸出，自動解析 ACT 與 RCT） |
| `access_token` | string | | ` ` | 中電存取憑證（若已在上框貼上則可留空） |
| `refresh_token` | string | | ` ` | 中電更新憑證（若已在上框貼上則可留空） |
| `name` | string | | `CLP` | 主感測器名稱 |
| `timeout` | int | | `30` | API 請求超時時間（秒） |
| `type` | string | | ` ` | 實體狀態顯示的資料類型（可選 `HOURLY` / `DAILY` / `BIMONTHLY`） |
| `get_account` | boolean | | `False` | 是否獲取帳戶摘要資訊 |
| `get_bill` | boolean | | `False` | 是否獲取帳單記錄 |
| `get_estimation` | boolean | | `False` | 是否獲取用電估算 |
| `get_bimonthly` | boolean | | `False` | 是否獲取雙月用電資料 |
| `get_daily` | boolean | | `False` | 是否獲取每日用電資料 |
| `get_hourly` | boolean | | `False` | 是否獲取每小時用電資料（**能源儀表板必備**） |
| `get_hourly_days` | int | | `1` | 獲取每小時用電資料的天數（`1` 或 `2` 天） |
| `renewable_energy_sensor_enable` | boolean | | `False` | 是否啟用可再生能源感測器（民間上網電價計劃 FiT） |
| `renewable_energy_sensor_name` | string | | `CLP Renewable Energy` | 可再生能源感測器名稱 |
| `renewable_energy_sensor_type` | string | | ` ` | 可再生能源狀態顯示類型（可選 `HOURLY` / `DAILY` / `BIMONTHLY`） |
| `renewable_energy_sensor_get_bill` | boolean | | `False` | 獲取可再生能源帳單資訊 |
| `renewable_energy_sensor_get_daily` | boolean | | `False` | 獲取可再生能源每日發電量 |
| `renewable_energy_sensor_get_hourly` | boolean | | `False` | 獲取可再生能源每小時發電量 |
| `renewable_energy_sensor_get_hourly_days` | int | | `1` | 可再生能源每小時資料天數（`1` 或 `2` 天） |

---

## 重新登入與重新認證

本整合組件使用 `access_token` + `refresh_token` 機制維護登入狀態。

### 手動重新登入
1. 前往 **設定** ➔ **裝置與服務**
2. 找到 **CLP HK**，點擊 **設定**
3. 閱讀指引後點擊「下一步」，將新獲取的 Token 貼入一鍵輸入框
4. 點擊 **提交**

### 自動重新整理與原生重新認證
- 正常運作期間，外掛程式會在 Access Token 即將過期時自動使用 Refresh Token 進行無感續期。
- 若中電伺服器拒絕更新或憑證徹底過期（返回 401/403 等）：
  - 系統會自動在 Home Assistant 介面觸發 **原生「重新認證（Re-authentication）」卡片**；
  - 點擊卡片上的「重新設定」，直接貼入最新 Token 即可一鍵恢復同步，無需刪除重新新增整合。

---

## 常見問題與除錯

- **多帳戶問題**：若您的中電登入帳號下掛有多個供電帳戶，目前僅會報告第一個處於使用中的帳戶（會在日誌中記錄警告）。
- **Akamai 網路攔截**：若中電 Akamai 網路安全防護暫時攔截了請求，外掛程式已透過現代瀏覽器指紋模擬進行防護；若依然偶發攔截，系統會自動在下一個排程週期重試。
- **開啟 Debug 除錯日誌**：在 `configuration.yaml` 中新增以下設定並重新啟動 Home Assistant：
  ```yaml
  logger:
    default: info
    logs:
      custom_components.clphk: debug
  ```
