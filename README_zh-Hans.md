# 中华电力 (香港) Home Assistant 能源统计自定义集成组件

[English](README.md) | [繁體中文](README_zh-Hant.md) | [简体中文](README_zh-Hans.md)

本集成组件可将香港中华电力（CLP）的账单、当期用电估算、各阶梯电价与实时用量，以及每小时智能电表用电数据无缝同步至 Home Assistant，并支持直接接入 Home Assistant 官方能源仪表盘（Energy Dashboard）。

---

## 🌟 核心功能特性

* **⚡ 能源仪表盘原生无缝接入**：深度集成 Home Assistant 长期统计系统（Long-Term Statistics），彻底解决中电官方数据天然延迟 3 小时导致的图表错位问题，历史用电量精确对齐到真实整点。
* **📊 官方阶梯电价全动态拉取**：每月自动从中华电力官方计费 API 获取最新各阶梯单价、燃料调整费（Fuel Clause Adjustment）与特别燃料回扣，自适应官方未来任意层级的阶梯调整。
* **🔄 自适应 N 阶梯与自定义电价**：
  * 支持自定义任意 $N$ 阶梯数量（如 1 档单一固定价、3 档、5 档或中电标准 7 档）。
  * 内置智能协调算法（`reconcile_tariff_tiers`），自动平滑对齐单价与分界限额，完美兼容中文全角逗号与英文半角逗号。
  * 支持锁定自定义固定电价、自定义燃料调整费、每期政府电费补贴（Subsidy）扣减，以及关联外部实体动态电价。
* **🔍 专属诊断信息实体（Diagnostic Entities）**：
  * **各阶梯用电量 (`sensor.clp_tier_consumption`)**：清晰显示当前所处用电阶梯，并在属性中提供每一阶梯的已用电量、额度上限、剩余额度、用电比例及当期预估用量分布。
  * **各阶梯电价明细 (`sensor.clp_tier_rates`)**：显示当前生效的基础单价，并在属性中输出各档阶梯单价表与用电分界。
* **🌱 支持可再生能源（上网电价计划 FiT）**：完美支持民间太阳能/风能上网电价（Feed-in Tariff）账户的发电设备发电量与账单统计。
* **💰 官方节能回扣机制精准还原**：完全遵循中电双月用电总额不多于 400 度的官方阶梯回扣规则（1~200 度回扣 17.2 仙/度，201~300 度回扣 16.2 仙/度，301~400 度回扣 15.2 仙/度）。
* **🛡️ 智能 Token 自动续期与原生重新认证**：
  * 周期性平滑刷新 Access Token，无需重复手动登录。
  * Token 失效时自动在 HA 前端触发原生「重新认证（Reauth）」卡片，一键粘贴即可秒级恢复。
* **⏱️ 分级轮询与流控保护**：每小时数据（60m）、每日统计（12h）、账户/账单/预估（5m 节流），保护您的账户免受中电接口速率限制。

---

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
- [完整实体与传感器列表](#完整实体与传感器列表)
  - [常规传感器](#常规传感器)
  - [诊断信息实体 (Diagnostic)](#诊断信息实体-diagnostic)
- [Home Assistant 传感器配置参数详解](#home-assistant-传感器配置参数详解)
- [阶梯电价与自定义计费机制说明](#阶梯电价与自定义计费机制说明)
- [重新登录与重新认证](#重新登录与重新认证)
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
4. 类别选择 `Integration`，填入存储库网址 `https://github.com/thematrixdev/home-assistant-clp` 并点击 **添加**
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
5. **第三步（选项）**：配置传感器名称、用电阶梯与数据更新首选项

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

> ⚠️ **重要警告**：获取凭证后，**切勿点击中电网站上的「登出 / Sign Out」按钮**！登出操作会立即使 Refresh Token 失效，导致集成无法继续自动续期。获取后直接关闭浏览器标签页或窗口即可。

*(备用手动方式：您亦可在开发者工具的 `Application` ➔ `Storage` ➔ `Local Storage` ➔ `https://www.clp.com.hk` 中分别复制 `act` 与 `rct` 键值)*

---

### 一键粘贴与支持格式

在配置或重新认证对话框中，只需将复制的文本直接粘贴入 **「一键粘贴完整 Token 内容」** 字段，系统内置智能解析器会自动识别并提取：
- 包含 `Access Token:` 与 `Refresh Token:` 的控制台输出整段文本
- 包含 `act`/`rct` 或 `access_token`/`refresh_token` 的单一 JSON 对象
- 两个分别包含 `"data"` 的 JSON 对象 `{"data":"...","time":...,"expire":"..."}`
- 两行独立的 Base64 凭证字符串

---

## 能源仪表盘集成 (解决 3 小时延迟错位)

由于中电官方系统的每小时用电数据天然延迟约 3 小时，传统插件若在「采集时刻」写入状态，会导致 Home Assistant 能源图表整体向后偏移 3 个小时。

本集成深度整合了 Home Assistant 官方的 **长期统计系统（Long-Term Statistics，`async_add_external_statistics`）**：
- 自动读取每笔数据的真实历史整点时间（`startDate`，对齐到整点 UTC 时间戳）；
- 精确将用电量与电费写入对应的真实历史时间段（例如 17:00-18:00 的用量准确记录在 17:00，而非采集时的 20:00）；
- 自动在系统中生成外部统计实体：`clphk:main_hourly_energy`（名称：`CLP Hourly Energy`）。

### 如何在能源仪表盘中使用：
1. 前往 Home Assistant **设置** ➔ **仪表盘** ➔ **能源**。
2. 在 **电网（Electricity Grid）** 区域点击 **添加消耗（Add Consumption）**。
3. 统计指标选择 **CLP Hourly Energy** (`clphk:main_hourly_energy`)。
4. 电费计价方式可选择关联本集成提供的 **Projected Effective Tariff Rate** (`sensor.clp_projected_effective_tariff_rate`) 实体以动态追踪单价。
5. 保存后，您的电网每小时消耗图表将与实际用电时段完全吻合！

---

## 完整实体与传感器列表

集成安装后将自动为您注册以下核心传感器及诊断实体：

### 常规传感器
| 实体 ID (推荐/默认) | 实体名称 | 单位 | 描述 |
| :--- | :--- | :---: | :--- |
| `sensor.dian_li` | 主电量传感器 | `kWh` | 中电主读数实体（可根据选项配置为小时、日或双月状态） |
| `sensor.clp_projected_cost` | Projected Cost | `HKD` | 中电官方/公式综合预估当期账单总费用 |
| `sensor.clp_current_period_consumption` | Current Period Consumption | `kWh` | 本计费账期至今已消耗的实际总电量 |
| `sensor.clp_projected_consumption` | Projected Consumption | `kWh` | 中电官方结合历史用电预测的本期总消耗电量 |
| `sensor.clp_last_bill_amount` | Last Bill Amount | `HKD` | 最近一期已出正式账单的总应缴应收款金额 |
| `sensor.clp_outstanding_amount` | Outstanding Amount | `HKD` | 账户当前未结清余额/欠费金额 |
| `sensor.clp_base_tariff_rate` | Base Tariff Rate | `HKD/kWh` | 基础阶梯电价（默认第 1 阶梯基础单价，属性含完整阶梯） |
| `sensor.clp_fuel_clause_adjustment` | Fuel Clause Adjustment | `HKD/kWh` | 当月最新燃料调整费（由中电每月依燃料成本调整公布） |
| `sensor.clp_projected_effective_tariff_rate` | Projected Effective Tariff Rate | `HKD/kWh` | **预估有效综合单价**（预估总费用 / 预估总用量，推荐填入能源面板计费） |

### 诊断信息实体 (Diagnostic)
位于设备页面「诊断信息」区域，用于深入洞察电量阶梯分布：
| 实体 ID | 实体名称 | 主状态 | 核心属性说明 |
| :--- | :--- | :---: | :--- |
| `sensor.dian_li_tier_consumption` | Tier Consumption | `Tier X` (如 `Tier 1`) | **各阶梯用量剖析**：`current_tier_used_kwh`（当前档已用）、`current_tier_remaining_kwh`（当前档剩余）、各档用电 `tier_1_used_kwh` ~ `tier_N_used_kwh`、用量字典 `tier_consumption_breakdown`、预估用量分布 `projected_tier_breakdown` |
| `sensor.dian_li_tier_rates` | Tier Rates | 当前档单价 (如 `0.945`) | **各阶梯费率明细**：`current_tier_rate_hkd`、各档单价 `tier_1_rate_hkd` ~ `tier_N_rate_hkd`、分界限额 `tier_1_limit_kwh` ~ `tier_N_limit_kwh`、单价字典 `tier_rates_breakdown` |

---

## Home Assistant 传感器配置参数详解

| 参数键名 | 类型 | 默认值 | 说明 |
| :--- | :---: | :---: | :--- |
| `combined_tokens` | string | ` ` | 一键粘贴完整 Token 内容（自动解析 ACT 与 RCT） |
| `access_token` | string | ` ` | 中电访问凭证（若已在上方一键框粘贴则可留空） |
| `refresh_token` | string | ` ` | 中电刷新凭证（若已在上方一键框粘贴则可留空） |
| `name` | string | `电力` | 集成/设备名称（将作为各子传感器命名前缀） |
| `timeout` | int | `30` | 网络连接与 API 超时时间（秒） |
| `custom_fixed_rate` | float | `0.0` | **自定义固定电价（港币/度）**：填 0 时自动采用中电动态阶梯计费；若填入数值（如 1.25）则强制按固定电价核算。 |
| `custom_fuel_cents` | float | `0.0` | **自定义燃料调整费（分/度）**：填 0 时每月自动同步中电官方最新公布的燃料费；填入具体数值可手动锁定。 |
| `custom_subsidy` | float | `0.0` | **每期电费补贴/资助（港币）**：填入政府电费补贴或节能资助金额，账单预估费用将自动予以扣减。 |
| `custom_rate_entity` | string | ` ` | **动态电价实体 ID**：可选填入外部实体（如 `input_number.clp_rate`），实现由外部动态控制电价。 |
| `custom_tier_rates` | string | ` ` | **自定义各阶梯电价（港币/度）**：逗号分隔的各阶梯单价（如 `0.945, 1.079, 1.237...` 或 `1.0, 1.5, 2.0`），自适应任意阶梯数量。 |
| `custom_tier_limits` | string | ` ` | **自定义各阶梯限额（度/双月）**：逗号分隔的前 N-1 档限额（如 `400, 600, 800...` 或 `200, 300`），最后一档自动作为无上限封顶阶梯。 |
| `get_hourly` | boolean | `True` | 是否同步每小时用电（**能源仪表盘必备**） |
| `get_hourly_days` | int | `2` | 历史每小时数据回溯天数（推荐 2 天，确保整点数据连续无断档） |
| `get_daily` | boolean | `True` | 是否获取每日用电量及费用（与官方每日日结完全一致） |
| `get_estimation` | boolean | `True` | 是否获取当期用电预估与电费 |
| `get_bill` | boolean | `True` | 是否获取过去 14 个月已出账单记录 |
| `renewable_energy_sensor_enable` | boolean | `False` | 是否启用中电[可再生能源民间上网电价计划 (FiT)](https://www.clp.com.hk/zh/business/low-carbon-solutions/renewable-energy/feed-in-tariff-business/application) 传感器 |
| `renewable_energy_sensor_name` | string | `电力 Renewable Energy` | 可再生能源传感器名称 |
| `renewable_energy_sensor_get_bill` | boolean | `True` | 是否同步可再生能源发电账单收益 |
| `renewable_energy_sensor_get_daily` | boolean | `True` | 是否同步可再生能源每日发电量 |
| `renewable_energy_sensor_get_hourly` | boolean | `True` | 是否同步可再生能源每小时发电量 |
| `renewable_energy_sensor_get_hourly_days` | int | `2` | 可再生能源每小时数据天数 |

---

## 阶梯电价与自定义计费机制说明

### 1. 中电官方标准双月阶梯（默认自动同步）
中电住宅用电通常按双月（约 60 天）账期累进计费：
- **第 1 阶梯**：首 400 度，单价 HK$0.945 / 度
- **第 2 阶梯**：次 600 度（401~1000 度），单价 HK$1.079 / 度
- **第 3 阶梯**：次 800 度（1001~1800 度），单价 HK$1.237 / 度
- **第 4 阶梯**：次 800 度（1801~2600 度），单价 HK$1.545 / 度
- **第 5 阶梯**：次 800 度（2601~3400 度），单价 HK$1.774 / 度
- **第 6 阶梯**：次 800 度（3401~4200 度），单价 HK$1.878 / 度
- **第 7 阶梯**：4200 度以上全部用量，单价 HK$1.890 / 度

### 2. 中电官方节能回扣（Energy Saving Rebate）
针对双月总用电量不多于 400 度的家庭，中电给予节能回扣：
- **1 至 200 度**：用电总量每度回扣 17.2 仙（HK$0.172 / 度）
- **201 至 300 度**：用电总量每度回扣 16.2 仙（HK$0.162 / 度）
- **301 至 400 度**：用电总量每度回扣 15.2 仙（HK$0.152 / 度）
- **超过 400 度**：无节能回扣。

### 3. 计费天数比例缩放
当双月抄表账期实际天数少于 55 天或多于 65 天时，各阶梯用电限额将按 `实际天数 / 60` 自动进行等比例线性缩放，保证与中电账单算法精确一致。

---

## 重新登录与重新认证

本集成使用 `access_token` + `refresh_token` 机制。

### 自动刷新
- 系统后台会在 Access Token 临近失效时自动调用中电接口无感刷新，无需人工干预。

### 原生重新认证 (Re-authentication)
- 若中电账号在别处被登出导致 Refresh Token 失效，集成不会破坏系统运行；
- Home Assistant 将在「设备与服务」页面自动浮现 **「需要重新配置（Reconfigure）」** 警告卡片；
- 点击卡片后，重新粘贴最新获取的 Token，所有传感器与历史统计即可瞬间无缝恢复。

---

## 常见问题与调试

- **多账户问题**：若您的中电账号下绑定了多个电表或物业，目前集成默认报告第一个活跃供电账户。
- **开启 Debug 调试日志**：
  若遇到异常排查，可在 Home Assistant 的 `configuration.yaml` 中添加以下内容并重启：
  ```yaml
  logger:
    default: info
    logs:
      custom_components.clphk: debug
  ```

---

## 社区与非官方交流群

- **Telegram 交流群**：https://t.me/smarthomehk

---

## 测试环境

- Home Assistant Container 2026.11+
- Python 3.13 / 3.14
- Linux aarch64 & x86_64

---

## 作者与维护者

* **原作者与主要维护者**：[@thematrixdev](https://github.com/thematrixdev)
* **贡献者与共同维护者**：[@kanshurichard](https://github.com/kanshurichard)

