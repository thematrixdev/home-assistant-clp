# 中华电力 (香港) Home Assistant 能源统计自定义集成组件

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

本集成组件可将香港中华电力（CLP）的账单、估算以及每小时智能电表用电数据无缝同步至 Home Assistant，并支持直接接入 Home Assistant 官方能源仪表盘（Energy Dashboard）。

## 目录

- [安装方法](#安装方法)
  - [先决条件](#先决条件)
  - [添加至 HACS](#添加至-hacs)
  - [手动安装](#手动安装)
- [配置与身份验证](#配置与身份验证)
  - [配置流程](#配置流程)
  - [获取中电 Token 凭证](#获取中电-token-凭证)
  - [一键粘贴与支持格式](#一键粘贴与支持格式)
- [能源仪表盘集成 (解决 3 小时延迟错位)](#能源仪表盘集成-解决-3-小时延迟错位)
- [Home Assistant 传感器配置参数](#home-assistant-传感器配置参数)
- [重新登录与重新认证](#重新登录与重新认证)
  - [手动重新登录](#手动重新登录)
  - [自动刷新与原生重新认证](#自动刷新与原生重新认证)
- [常见问题与调试](#常见问题与调试)

---

## 安装方法

### 先决条件

- 中电（CLP）登记客户
- 中电官网个人网银/账户登录凭证
- 已安装中电智能电表（用于获取 `HOURLY` 每小时用电数据）

### 添加至 HACS

1. 确保已安装 [HACS](https://hacs.xyz/docs/setup/prerequisites)
2. 在 Home Assistant 侧边栏点击 **HACS** ➔ **Integrations（集成）**
3. 点击右上角菜单按钮（三个点） ➔ 选择 **Custom repositories（自定义存储库）**
4. 类别选择 `Integration`，填入存储库网址 `https://github.com/kanshurichard/home-assistant-clp` 并点击 **添加**
5. 在集成列表中找到 **CLPHK**，点击右下角 **下载**
6. 重启 Home Assistant

### 手动安装

1. 下载本仓库源代码
2. 将 `custom_components/clphk` 文件夹复制至您的 Home Assistant 配置目录中的 `custom_components/` 文件夹内
3. 重启 Home Assistant

---

## 配置与身份验证

### 配置流程

1. 前往 **设置** ➔ **设备与服务** ➔ 点击右下角 **添加集成**
2. 搜索并选择 **CLPHK**
3. **第一步（指引）**：阅读获取凭证指引，点击「下一步」
4. **第二步（凭证）**：将复制的 Token 整段粘贴至「一键粘贴完整 Token 内容」框中
5. **第三步（选项）**：配置传感器名称、数据更新项目（如启用每小时用电）

---

### 获取中电 Token 凭证

1. 打开 Chrome 或 Edge 浏览器的 **无痕窗口**（`Ctrl+Shift+N` 或 `Cmd+Shift+N`）
2. 前往 [中电官网登录页面](https://www.clp.com.hk/services/en/login) 并登录账户
3. 按 **F12**（或在网页任意位置按右键选择「检查」）打开开发者工具
4. 切换至 **Console（控制台）** 标签页，粘贴并运行以下代码：
   ```javascript
   console.log("Access Token:\n" + localStorage.getItem("act") + "\n\nRefresh Token:\n" + localStorage.getItem("rct"));
   ```
5. 复制控制台输出的全部文本内容。
6. **直接关闭无痕浏览器窗口**（**切勿点击「登出 / Sign Out」**）。
7. 返回 Home Assistant，将复制的文本直接粘贴至 **「一键粘贴完整 Token 内容」** 文本框。

> ⚠️ **重要警告**：获取凭证后，**切勿点击中电网站上的「登出 / Sign Out」按钮**！登出操作会立即使 Refresh Token 失效，导致集成无法继续自动更新。获取后直接关闭浏览器标签页或窗口即可。

*(备用手动方式：您亦可在开发者工具的 `Application` ➔ `Storage` ➔ `Local Storage` ➔ `https://www.clp.com.hk` 中分别复制 `act` 与 `rct` 键值)*

---

### 一键粘贴与支持格式

在配置或重新认证对话框中，只需将复制的文本直接粘贴入 **「一键粘贴完整 Token 内容」** 字段，系统内置智能解析器会自动识别并提取：
- 包含 `Access Token:` 与 `Refresh Token:` 的控制台输出整段文本
- 包含 `act`/`rct` 或 `access_token`/`refresh_token` 的单一 JSON 对象
- 两个分别包含 `"data"` 的 JSON 对象 `{"data":"...","time":...,"expire":"..."}`
- 两行独立的 Base64 凭证字符串

如果选择分开填写下方的独立字段，`Access Token` 和 `Refresh Token` 均支持以下格式：
1. 完整 JSON 对象：`{"data":"<base64-token>","time":...,"expire":"..."}`
2. JSON 字符串值：`"<base64-token>"`
3. 纯 Base64 字符串：`<base64-token>`

---

## 能源仪表盘集成 (解决 3 小时延迟错位)

由于中电官方系统的每小时用电数据天然延迟约 3 小时，传统插件若在「采集时刻」写入状态，会导致 Home Assistant 能源图表整体向后偏移 3 个小时。

本集成深度整合了 Home Assistant 官方的 **长期统计系统（Long-Term Statistics，`async_add_external_statistics`）**：
- 自动读取每笔数据的真实历史整点时间（`startDate`，顶整点 UTC 时间戳）；
- 精确将用电量写入对应的历史时间段（例如 17:00-18:00 的用量准确记录在 17:00，而非采集时的 20:00）；
- 自动在系统中生成外部统计实体：`clphk:main_hourly_energy`（名称：`CLP Hourly Energy`）。

### 如何在能源仪表盘中使用：
1. 前往 Home Assistant **设置** ➔ **仪表盘** ➔ **能源**。
2. 在 **电网（Electricity Grid）** 区域点击 **添加消耗（Add Consumption）**。
3. 统计指标选择 **CLP Hourly Energy** (`clphk:main_hourly_energy`)。
4. 保存后，您的电网每小时消耗图表将与实际用电时段完全吻合！

---

## Home Assistant 传感器配置参数

| 参数键名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| `combined_tokens` | string | | ` ` | 一键粘贴完整 Token（可直接粘贴整段输出，自动解析 ACT 与 RCT） |
| `access_token` | string | | ` ` | 中电访问凭证（若已在上框粘贴则可留空） |
| `refresh_token` | string | | ` ` | 中电刷新凭证（若已在上框粘贴则可留空） |
| `name` | string | | `CLP` | 主传感器名称 |
| `timeout` | int | | `30` | API 请求超时时间（秒） |
| `type` | string | | ` ` | 实体状态显示的显示类型（可选 `HOURLY` / `DAILY` / `BIMONTHLY`） |
| `get_account` | boolean | | `False` | 是否获取账户摘要信息 |
| `get_bill` | boolean | | `False` | 是否获取账单记录 |
| `get_estimation` | boolean | | `False` | 是否获取用电预估 |
| `get_bimonthly` | boolean | | `False` | 是否获取双月用电数据 |
| `get_daily` | boolean | | `False` | 是否获取每日用电数据 |
| `get_hourly` | boolean | | `False` | 是否获取每小时用电数据（**能源仪表盘必备**） |
| `get_hourly_days` | int | | `1` | 获取每小时用电数据天数（`1` 或 `2` 天） |
| `renewable_energy_sensor_enable` | boolean | | `False` | 是否启用可再生能源传感器（民间上网电价计划 FiT） |
| `renewable_energy_sensor_name` | string | | `CLP Renewable Energy` | 可再生能源传感器名称 |
| `renewable_energy_sensor_type` | string | | ` ` | 可再生能源状态显示类型（可选 `HOURLY` / `DAILY` / `BIMONTHLY`） |
| `renewable_energy_sensor_get_bill` | boolean | | `False` | 获取可再生能源账单记录 |
| `renewable_energy_sensor_get_daily` | boolean | | `False` | 获取可再生能源每日发电量 |
| `renewable_energy_sensor_get_hourly` | boolean | | `False` | 获取可再生能源每小时发电量 |
| `renewable_energy_sensor_get_hourly_days` | int | | `1` | 可再生能源每小时数据天数（`1` 或 `2` 天） |

---

## 重新登录与重新认证

本集成组件使用 `access_token` + `refresh_token` 机制维护登录状态。

### 手动重新登录
1. 前往 **设置** ➔ **设备与服务**
2. 找到 **CLP HK**，点击 **配置**
3. 阅读指引后点击「下一步」，将新获取的 Token 粘贴入一键输入框
4. 点击 **提交**

### 自动刷新与原生重新认证
- 正常运行期间，插件会在 Access Token 即将过期时自动使用 Refresh Token 进行无感续期。
- 若中电服务器拒绝续期或凭证彻底过期（返回 401/403 等）：
  - 系统会自动在 Home Assistant 界面触发 **原生「重新认证（Re-authentication）」卡片**；
  - 点击卡片上的「重新配置」，直接粘贴最新 Token 即可一键恢复同步，无需删除重新添加集成。

---

## 常见问题与调试

- **多账户问题**：若您的中电登录账号下挂有多个供电账户，目前仅会报告第一个处于活跃状态的账户（会在日志中记录警告）。
- **Akamai 网络拦截**：若中电 Akamai 网络安全防护暂时拦截了请求，插件已通过现代浏览器指纹模拟进行防护；若依然偶发拦截，系统会自动在下一个计划周期重试。
- **开启 Debug 调试日志**：在 `configuration.yaml` 中添加以下设置并重启 Home Assistant：
  ```yaml
  logger:
    default: info
    logs:
      custom_components.clphk: debug
  ```

---

## 测试环境

- Home Assistant Container 2026.11.1
- Armbian 26.8 / Debian 12 / Ubuntu 24.04 (Linux aarch64 & x86_64)
