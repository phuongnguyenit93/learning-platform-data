# Azure Digital Twins và mô hình hóa môi trường thực

Một khuôn viên có ba tòa nhà, mỗi tòa nhà có nhiều tầng, phòng họp, máy điều hòa, cảm biến nhiệt độ và đồng hồ điện. Dữ liệu IoT liên tục thay đổi: nhiệt độ phòng 101 tăng từ 25°C lên 29°C, thiết bị HVAC có cảnh báo, hoặc một phòng vừa chuyển từ trạng thái trống sang có người. Nếu chỉ lưu hàng triệu thông điệp cảm biến, hệ thống có thể biết **giá trị đo** nhưng khó trả lời những câu hỏi về **ngữ cảnh vật lý**: cảm biến này đang giám sát phòng nào, phòng đó thuộc tầng nào, máy lạnh nào phục vụ khu vực ấy và những phòng lân cận có ảnh hưởng hay không?

**Azure Digital Twins (ADT)** giúp tạo một **đồ thị biểu diễn môi trường thực** bằng các đối tượng số (digital twins), mô hình (models) và quan hệ (relationships). Đồ thị này liên kết dữ liệu cảm biến với vị trí, thiết bị và cấu trúc không gian để phục vụ giám sát, phân tích, tự động hóa hoặc mô phỏng ở tầng ứng dụng.

```text
MÔI TRƯỜNG VẬT LÝ                    MÔ HÌNH SỐ TRÊN AZURE

Tòa nhà A                            Twin bldg-a
   |                                      |
   +-- Phòng 101                         +-- contains --> Twin room-101
   |     |                                                   |
   |     +-- Cảm biến nhiệt độ                               +-- monitoredBy --> sensor-temp-01
   |     +-- Máy lạnh                                         +-- servedBy ----> hvac-01
   |
   +-- Phòng 102                         +-- contains --> Twin room-102

IoT telemetry (29°C) --> IoT Hub / xử lý sự kiện --> cập nhật thuộc tính room-101
                                                   --> ứng dụng phân tích trạng thái
```

Mô hình số **không tự xuất hiện khi cắm cảm biến**. Bạn phải định nghĩa loại đối tượng bằng **Digital Twins Definition Language (DTDL)**, tạo các twin instances, tạo các cạnh quan hệ và xây luồng đồng bộ trạng thái từ nguồn dữ liệu. ADT không mặc nhiên thay thế **Azure IoT Hub**, cơ sở dữ liệu chuỗi thời gian hay phần mềm BIM/GIS/CAD.

Bài thuộc chương **IoT và xử lý tại biên**, trong module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, dịch vụ tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và quản lý chi phí. Từ góc nhìn ấy, bài tập trung vào **mô hình hóa môi trường thực** và kết nối ADT với IoT Hub, Functions, Event Grid, Event Hubs, dữ liệu lịch sử, hệ thống điều khiển và các yêu cầu vận hành an toàn.

> Ví dụ sử dụng **DTDL v2** và Azure Digital Twins data-plane SDK/REST theo cú pháp minh họa. Những tính năng, giới hạn, API version, tích hợp lịch sử, quota, region, SKU và giá có thể thay đổi. Trước khi vận hành Production, kiểm tra tài liệu sản phẩm và khả năng thực tế của instance. Không điều khiển thiết bị vật lý quan trọng chỉ vì một twin property hoặc truy vấn AI đề xuất hành động; mọi lệnh điều khiển cần tầng bảo vệ độc lập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **physical asset, digital twin, model, relationship, component, property và telemetry**.
2. Giải thích Azure Digital Twins là **đồ thị ngữ nghĩa của môi trường thực**, không phải chỉ một bảng dữ liệu cảm biến.
3. Viết mô hình DTDL v2 cho Building, Room và Sensor với ID, properties, telemetry và relationships.
4. Phân biệt **model schema** với **twin instance** và dữ liệu được cập nhật theo thời gian.
5. Thiết kế danh tính, tên và version models/twins/relationships cho campus hoặc nhà máy.
6. Tạo và truy vấn twins/relationships bằng SDK trong môi trường được cấp quyền.
7. Thiết kế luồng **IoT device → IoT Hub → Functions/worker → ADT**, kết hợp Event Grid/Event Hubs và nơi lưu lịch sử.
8. Giải thích vì sao **telemetry event không tự động biến thành twin property** và vì sao ADT không phải time-series database mặc định.
9. Thiết kế graph query để tìm các phòng và thiết bị liên quan.
10. Phân biệt **topology state, latest known state, history và desired control state**.
11. Áp dụng Microsoft Entra ID/managed identity, Azure RBAC/data-plane roles và mạng riêng khi được hỗ trợ.
12. Xử lý **stale data, late/out-of-order events, idempotency, concurrency, drift và schema evolution**.
13. Thiết lập quan sát, bảo mật dữ liệu vị trí, giám sát chi phí và quy trình xử lý sự cố.
14. Thiết kế một lab mini xây dựng mô hình tòa nhà và kiểm chứng đồ thị.

## 2. Digital twin là gì và không phải là gì?

**Digital twin** là một đại diện số của đối tượng, quá trình hoặc môi trường trong thế giới thực, được liên kết với dữ liệu và quan hệ để hỗ trợ hiểu trạng thái, phân tích hoặc ra quyết định. Khả năng của một hệ thống digital twin tùy mức độ cập nhật và tích hợp nghiệp vụ.

Ví dụ một phòng họp ngoài đời có:

- Tên phòng, loại sử dụng, diện tích.
- Tầng và tòa nhà chứa nó.
- Cảm biến nhiệt độ, độ ẩm, mức CO₂.
- Máy điều hòa cấp khí.
- Nhiệt độ hiện tại, số người ước tính.
- Lịch sử các lần vượt ngưỡng.
- Quy tắc cảnh báo/điều phối bảo trì.

Trong ADT, ta có thể biểu diễn phòng thành một **twin** có thuộc tính và các cạnh liên kết đến twin khác.

**Không nên nhầm:**

| Khái niệm | Đại diện cho | Không mặc định cung cấp |
|---|---|---|
| **Azure Digital Twins** | Models, twins, graph relationships, trạng thái và truy vấn ngữ cảnh. | Device connectivity protocol, kho telemetry dài hạn, trình mô phỏng vật lý hoàn chỉnh. |
| **Azure IoT Hub** | Kết nối, định danh và trao đổi thông điệp với thiết bị theo các khả năng IoT Hub. | Đồ thị tòa nhà/phòng/quan hệ nghiệp vụ. |
| **Azure IoT Edge / edge compute** | Thu thập/tiền xử lý tại vị trí thiết bị, xử lý khi mạng hạn chế. | Model graph tự đồng bộ với ADT. |
| **Azure Data Explorer/Analytics** | Dữ liệu sự kiện/chuỗi thời gian lớn và phân tích lịch sử. | Mô hình twin/relationship và topology semantics như ADT. |
| **BIM/GIS/CAD** | Mô hình thiết kế công trình/hình học/bản đồ. | Live operational twin graph nếu không tích hợp. |
| **CMDB/ERP/Asset register** | Nguồn quản trị tài sản, chủ sở hữu, bảo trì. | Dữ liệu cảm biến realtime mặc định. |

**ADT là một phần của giải pháp**, không thay thế tất cả các hệ thống trên.

## 3. Tại sao cần đồ thị thay vì một bảng thiết bị?

Một bảng telemetry:

```text
deviceId          timestamp             temperature
sensor-temp-01    2026-11-20T09:00Z      25.1
sensor-temp-01    2026-11-20T09:01Z      28.5
sensor-temp-02    2026-11-20T09:01Z      23.4
```

Nó không tự giải đáp:

- Sensor-temp-01 ở phòng nào?
- Phòng ấy có chung HVAC với các phòng khác không?
- Những máy nào cùng thuộc tòa nhà A?
- Công suất/thiết bị điều khiển nào ảnh hưởng một vùng nóng?
- Phòng ấy thuộc tenant hoặc bộ phận nào?

Một **graph** bổ sung ngữ cảnh:

```text
[bldg-a] --contains--> [floor-01] --contains--> [room-101]
                                                  |
                                                  +--monitoredBy--> [sensor-temp-01]
                                                  |
                                                  +--servedBy----> [hvac-01]
                                                  |
                                                  +--adjacentTo--> [room-102]
```

Giờ ứng dụng có thể **truy vấn quan hệ** để xác định các assets liên quan đến tình huống nhiệt độ vượt ngưỡng, sau đó lấy dữ liệu lịch sử từ hệ thống phân tích và quyết định có cần cảnh báo hay không.

## 4. Các khái niệm cốt lõi của Azure Digital Twins

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **ADT instance** | Tài nguyên Azure chứa models, twins và graph. | `adt-campus-lab` |
| **Model / Interface** | Kiểu dữ liệu và cấu trúc được định nghĩa bằng DTDL. | `dtmi:example:Room;1` |
| **Twin instance** | Một đối tượng thực thể được tạo theo model. | `room-101` |
| **Twin ID** | ID của instance trong graph. | `room-101`, không phải model ID. |
| **Property** | Trạng thái/thuộc tính được lưu trên twin theo schema. | `temperature=28.5` |
| **Telemetry** | Khai báo loại dữ liệu/sự kiện đo; xử lý sự kiện theo API/integration. | `temperatureReading` |
| **Relationship** | Cạnh có hướng từ twin nguồn tới twin đích. | `bldg-a --contains--> room-101` |
| **Relationship property** | Metadata trên cạnh khi model có khai báo. | `installedAt`, `priority` |
| **Component** | Thành phần có cấu trúc bên trong một model/twin. | `thermostat` trong thiết bị HVAC. |
| **DTDL** | Ngôn ngữ JSON-LD mô tả models, tính chất và quan hệ. | Interface Room version 1. |
| **Event route** | Định tuyến các sự kiện ADT phát ra tới endpoint được cấu hình. | Event Grid/Event Hubs/Service Bus theo hỗ trợ. |
| **Data history pipeline** | Tích hợp đẩy biến đổi/sự kiện ra hệ thống lưu/phân tích lịch sử. | Azure Data Explorer qua cấu hình hỗ trợ. |

**Twin ID**, **model ID** và **device ID** không phải một giá trị bắt buộc giống nhau. Một cảm biến vật lý được nhận dạng trong IoT Hub có thể tương ứng với một Sensor twin và được liên kết bằng bảng mapping đáng tin cậy.

## 5. Phân biệt model và twin instance

Mô hình `Room` mô tả **một loại phòng**:

```text
Room model:
  name: string
  temperature: double
  occupancy: integer
  relationship monitoredBy -> Sensor
```

Những **twin instances** hiện thực model:

```text
room-101:
  name = "Phòng 101"
  temperature = 28.5
  occupancy = 7

room-102:
  name = "Phòng 102"
  temperature = 24.0
  occupancy = 0
```

Tương tự **class** và **object** trong lập trình hướng đối tượng, nhưng không nên coi DTDL là ngôn ngữ lập trình với hành vi thực thi. Model chủ yếu mô tả schema/ngữ nghĩa, còn dịch vụ và ứng dụng thực hiện cập nhật, truy vấn và xử lý sự kiện.

### Chọn model version

Dòng:

```text
dtmi:example:Room;1
```

là **Digital Twin Model Identifier (DTMI)** với version 1. Khi cấu trúc thay đổi không tương thích, thông lệ là xuất bản một model ID/version mới, ví dụ `dtmi:example:Room;2`, rồi lập kế hoạch nâng cấp các twins và đường dữ liệu liên quan.

**Không đổi tên model trên giấy rồi giả định các twins cũ đã tuân theo schema mới.** Trong ADT, mô hình đã được nạp có các quy tắc quản lý/immutability; cần versioning và migration có kiểm soát.

## 6. Digital Twins Definition Language (DTDL)

**DTDL** là ngôn ngữ định nghĩa models, thường được biểu diễn bằng JSON-LD. Một model Interface có các trường chủ yếu:

- `@id`: DTMI toàn cục, có version.
- `@type`: loại thực thể DTDL, ví dụ `Interface`.
- `@context`: ngữ cảnh/ngữ pháp, ví dụ `dtmi:dtdl:context;2` cho DTDL v2.
- `displayName` / `description`: metadata giúp con người hiểu.
- `contents`: Properties, Telemetries, Relationships, Components và các thành phần được hỗ trợ.

Ví dụ khung:

```json
{
  "@id": "dtmi:example:SimpleRoom;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Simple Room",
  "contents": [
    {
      "@type": "Property",
      "name": "temperature",
      "schema": "double"
    }
  ]
}
```

**Model này chưa tạo phòng nào.** Nó chỉ cho phép dịch vụ và ứng dụng hiểu các instances tương ứng phải có cấu trúc ra sao.

### DTDL v2 và các version khác

Azure Digital Twins có các điều kiện hỗ trợ model languages/versions theo thời điểm. Bài dùng **DTDL v2** để nhất quán các snippets. Trước khi nạp DTDL v3 hoặc extensions, xác minh ADT instance/API/SDK hỗ trợ và không trộn cú pháp khác phiên bản.

## 7. Mẫu DTDL: Building

Ta xây mô hình tòa nhà có tên và quan hệ `contains` tới một phòng.

```json
{
  "@id": "dtmi:example:campus:Building;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": {
    "en": "Building",
    "vi": "Tòa nhà"
  },
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Relationship",
      "name": "contains",
      "target": "dtmi:example:campus:Room;1"
    }
  ]
}
```

Các ý:

1. `@id` là ID của **model**, khác twin ID `bldg-a`.
2. `contains` là quan hệ có **hướng** từ Building đến Room.
3. `target` thể hiện model đích mong muốn.
4. `name` là property string của Building.
5. `writable` mô tả một đặc tính trong schema, **không phải quyền RBAC của người dùng**.
6. DTDL không tự tạo danh sách rooms hay lấy tên từ hệ thống quản lý tòa nhà.

### Sơ đồ

```text
Model: Building;1
    ├── name: string
    └── contains ──> Model: Room;1
```

Một tòa nhà chứa nhiều phòng được thể hiện bằng **nhiều relationship instances** có cùng tên loại `contains` nhưng ID quan hệ khác nhau.

## 8. Mẫu DTDL: Room

Room có properties để biểu diễn trạng thái mới nhất và các quan hệ tới Sensor/HVAC.

```json
{
  "@id": "dtmi:example:campus:Room;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Room",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "temperature",
      "schema": "double",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "occupancy",
      "schema": "integer",
      "writable": true
    },
    {
      "@type": "Telemetry",
      "name": "temperatureReading",
      "schema": "double"
    },
    {
      "@type": "Relationship",
      "name": "monitoredBy",
      "target": "dtmi:example:campus:Sensor;1"
    },
    {
      "@type": "Relationship",
      "name": "servedBy",
      "target": "dtmi:example:campus:HVAC;1"
    }
  ]
}
```

Lưu ý:

- `temperature` kiểu **Property** mô tả trạng thái đang được lưu và có thể query.
- `temperatureReading` kiểu **Telemetry** mô tả dữ liệu đo như sự kiện; **không tự lưu mỗi lần phát thành property `temperature`**.
- `monitoredBy` và `servedBy` thể hiện các liên hệ vật lý/hạ tầng.
- Nếu chưa có model Sensor/HVAC cùng ID target trong instance, cần nạp đúng các dependent models và đáp ứng validation trước khi tạo graph.

### Temperature không phải lúc nào cũng bằng sensor reading cuối

Ứng dụng có thể lấy trung bình của nhiều sensors, lọc outliers hoặc kiểm tra sensor health rồi mới cập nhật trạng thái của phòng. Vì thế quyết định **quy tắc tính property** thuộc tầng xử lý nghiệp vụ, không tự suy từ tên telemetry.

## 9. Mẫu DTDL: Sensor và HVAC

Hai model đơn giản:

**Sensor:**

```json
{
  "@id": "dtmi:example:campus:Sensor;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Temperature Sensor",
  "contents": [
    {
      "@type": "Property",
      "name": "deviceId",
      "schema": "string"
    },
    {
      "@type": "Property",
      "name": "health",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Telemetry",
      "name": "temperatureReading",
      "schema": "double"
    }
  ]
}
```

**HVAC:**

```json
{
  "@id": "dtmi:example:campus:HVAC;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "HVAC Unit",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string"
    },
    {
      "@type": "Property",
      "name": "operationalState",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "powerKw",
      "schema": "double",
      "writable": true
    }
  ]
}
```

Những model trên là **schema học tập**, không có quy tắc tự động như “health=Failed thì tắt máy lạnh”. Muốn thực thi, cần processor, rules và hệ thống điều khiển an toàn riêng.

### Model ID có version

Có thể đặt namespace theo tổ chức:

```text
dtmi:example:campus:Room;1
dtmi:example:campus:Sensor;1
dtmi:example:campus:HVAC;1
```

Giữ nguyên ID/version để code và deployment scripts có thể kiểm tra chính xác. Đừng gán model ID khác chỉ vì display name thay đổi.

## 10. Property, telemetry, component và relationship

| Loại | Bản chất | Ví dụ | Khi nào chọn |
|---|---|---|---|
| **Property** | Giá trị/trạng thái của twin theo schema. | `temperature`, `health`, `name`. | Query latest known state của đối tượng. |
| **Telemetry** | Dòng dữ liệu/measurement xảy ra theo thời gian. | `temperatureReading`. | Xử lý sự kiện, streaming hoặc history pipeline. |
| **Component** | Thành phần con có cấu trúc **bên trong cùng twin/model**. | Bộ `thermostat` với properties của nó. | Bộ phận gắn chặt, không cần identity/graph cạnh độc lập. |
| **Relationship** | Cạnh có hướng giữa **hai twins độc lập**. | `room-101 --monitoredBy--> sensor-01`. | Cần truy vấn traversal, tái sử dụng asset, vòng đời riêng. |

### Quy tắc thực tiễn: component hay twin riêng?

Một bộ điều khiển nhỏ chỉ mang thông số của HVAC có thể là **Component**. Một cảm biến thật có serial number, bảo hành, đổi vị trí giữa các phòng và cần quan hệ nhiều bên thường phù hợp hơn làm **Sensor twin độc lập**.

Không có cách mô hình duy nhất cho mọi tổ chức. Chọn theo **lifecycle, identity, query patterns và mức độc lập của asset**.

## 11. DTDL Component: biểu diễn phần bên trong

Giả sử có model Thermostat:

```json
{
  "@id": "dtmi:example:campus:Thermostat;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "contents": [
    {
      "@type": "Property",
      "name": "setpoint",
      "schema": "double",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "mode",
      "schema": "string",
      "writable": true
    }
  ]
}
```

Một model khác có thể chứa component:

```json
{
  "@id": "dtmi:example:campus:HVACWithThermostat;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string"
    },
    {
      "@type": "Component",
      "name": "thermostat",
      "schema": "dtmi:example:campus:Thermostat;1"
    }
  ]
}
```

Component được khai báo **trong model của twin chứa nó**. Nó không tự động tạo relationship giữa hai twin IDs.

### Lưu ý

- Với DTDL components, JSON instance và update path có cấu trúc theo API; nên dùng SDK/model-aware helper và kiểm tra sample của phiên bản.
- Component schema phải được nạp/resolve đúng.
- Không xem component là replacement cho toàn bộ tài sản có asset ID riêng.
- Không dùng field components để nhét hàng nghìn readings lịch sử.

## 12. DTDL relationship: cạnh có hướng và ý nghĩa

Mô hình Building khai báo `contains` hướng Building → Room, nên instance:

```text
bldg-a --contains--> room-101
```

Không có nghĩa một cạnh ngược `room-101 --inside--> bldg-a` được tạo tự động. Nếu ứng dụng cần truy vấn hướng ngược, dùng graph query phù hợp hoặc mô hình hóa quan hệ ngược có chủ đích.

Một relationship có **ID riêng**, tên loại và hai endpoints:

```json
{
  "$relationshipId": "bldg-a-contains-room-101",
  "$sourceId": "bldg-a",
  "$relationshipName": "contains",
  "$targetId": "room-101"
}
```

**Các giá trị**:

- `$sourceId`: ID twin nguồn.
- `$targetId`: ID twin đích.
- `$relationshipName`: tên quan hệ khai báo trên model nguồn.
- `$relationshipId`: ID duy nhất cho quan hệ xuất phát từ twin nguồn theo hợp đồng API.

Nếu cần metadata như `installedAt` trên một cạnh, phải khai báo relationship properties theo DTDL và kiểm tra dữ liệu truyền vào. Không tự đặt property lạ rồi kỳ vọng hệ thống chấp nhận theo schema.

## 13. Tạo twin instance từ model

Sau khi model `dtmi:example:campus:Room;1` được nạp, tạo instance `room-101`:

```json
{
  "$dtId": "room-101",
  "$metadata": {
    "$model": "dtmi:example:campus:Room;1"
  },
  "name": "Phòng 101",
  "temperature": 25.1,
  "occupancy": 0
}
```

Một instance Building:

```json
{
  "$dtId": "bldg-a",
  "$metadata": {
    "$model": "dtmi:example:campus:Building;1"
  },
  "name": "Tòa nhà A"
}
```

Một instance Sensor:

```json
{
  "$dtId": "sensor-temp-01",
  "$metadata": {
    "$model": "dtmi:example:campus:Sensor;1"
  },
  "deviceId": "iot-sensor-01",
  "health": "Healthy"
}
```

Những object trên là **digital twin payloads**, không phải model DTDL. Không trộn `@id` của model với `$dtId` của instance.

### Không cần một cảm biến cho mỗi twin

Một phòng hoặc dây chuyền có thể có twin dù không có cảm biến trực tiếp. Giá trị của twin có thể đến từ ERP, BMS, operator input, analytics hoặc mô hình tính toán. Mối liên hệ với môi trường thực cần được **xác thực và ghi nguồn gốc**.

## 14. Xây graph từ những twin instances

Từ các objects:

```text
bldg-a
room-101
room-102
sensor-temp-01
hvac-01
```

Ta tạo relationships:

```text
bldg-a --contains--> room-101
bldg-a --contains--> room-102
room-101 --monitoredBy--> sensor-temp-01
room-101 --servedBy--> hvac-01
```

Graph giúp truy vấn:

- Những rooms nào nằm trong tòa nhà A?
- Những sensors giám sát Room 101?
- Những rooms đang do cùng HVAC phục vụ?
- Khi HVAC lỗi, những rooms có thể chịu tác động?

**Relationship không chứng minh hiệu ứng vật lý**. Một phòng được đánh dấu `servedBy` không đảm bảo HVAC đang cấp khí đúng. Các ràng buộc và bất biến như “mỗi phòng chỉ có một main HVAC” phải được kiểm soát bởi ứng dụng và dữ liệu nguồn, nếu không có tính năng enforce tương ứng.

## 15. Dữ liệu thời gian thực đi vào graph thế nào?

ADT không tự mở kết nối MQTT tới thiết bị IoT rồi đo nhiệt độ. Một luồng phổ biến:

```text
Sensor ngoài đời
      |
      | MQTT/AMQP/HTTPS (theo IoT Hub device protocols)
      v
Azure IoT Hub
      |
      | Route telemetry/event
      v
Azure Functions / event-processing worker
      |
      +-- xác thực deviceId và message schema
      +-- map deviceId → twinId
      +-- kiểm tra timestamp/sequence/idempotency
      +-- chuyển đổi đơn vị °F → °C nếu cần
      |
      v
Azure Digital Twins data-plane API
      |
      +-- Update property temperature
      +-- (optional) Publish telemetry event
      |
      v
ADT event routes → Event Grid / Event Hubs / Service Bus
                       |
                       v
              Azure Data Explorer / analytics / alerting
```

Điểm cần nhớ:

1. Device thường gửi dữ liệu đến **IoT Hub**, không phải trực tiếp vào ADT.
2. Function/worker làm **adapter** giữa device IDs, schema và twin IDs.
3. Cập nhật property là một **hành động ghi** rõ ràng vào ADT.
4. Phát event sang downstream cần **event route/endpoint** phù hợp.
5. Lưu lịch sử dài hạn ở **dịch vụ phân tích** tương ứng.
6. Các retry/duplicate/out-of-order phải được kiểm soát tại ingestion.

## 16. Thiết kế message hợp đồng giữa thiết bị và worker

Một message IoT giả lập:

```json
{
  "deviceId": "iot-sensor-01",
  "eventId": "evt-sensor-01-20261120-0901",
  "sequence": 12804,
  "observedAtUtc": "2026-11-20T09:01:00Z",
  "temperatureC": 28.5,
  "quality": "ok"
}
```

Ứng dụng adapter nên:

- **Xác thực nguồn** thông qua IoT Hub identity/messaging boundary; không chỉ tin field `deviceId` trong body.
- Kiểm tra schema, units, range và timestamp.
- Dùng mapping do backend quản lý: `iot-sensor-01 → sensor-temp-01 → room-101`.
- Ngăn ghi dữ liệu từ sensor tenant A sang twin tenant B.
- Dedupe bằng `eventId` hoặc sequence trong cửa sổ phù hợp.
- So `observedAtUtc` với timestamp hiện có để chống out-of-order overwrite.
- Lưu source event ở analytics/event store khi cần audit.
- Báo lỗi và quarantine message sai định dạng.
- Có retry/backoff khi ADT 429/5xx.
- Không vô điều kiện ghi `temperature=28.5` khi sensor health=Failed.

### Hai loại thời gian

- **Event/observation time:** khi cảm biến thực sự đo được giá trị.
- **Processing/update time:** khi worker nhận, tính toán và cập nhật twin.

Nếu chỉ lưu processing time, hệ thống có thể hiểu sai sự kiện muộn. Khi nghiệp vụ cần, theo dõi cả hai và tính độ trễ nguồn.

## 17. Property là trạng thái, telemetry là sự kiện

Một kiến trúc đúng cần phân biệt:

```text
Sensor gửi tại 09:00: 24.0°C
Sensor gửi tại 09:01: 24.5°C
Sensor gửi tại 09:02: 29.0°C

Azure Digital Twins:
  room-101.temperature = 29.0 (latest accepted state)

Time-series store:
  (09:00, 24.0)
  (09:01, 24.5)
  (09:02, 29.0)
```

Nếu bạn chỉ update property:

- Có thể truy vấn **nhiệt độ hiện tại/giá trị được chấp nhận cuối cùng**.
- **Không tự có toàn bộ lịch sử** từng phút chỉ vì property đã thay đổi.
- Nếu cần biểu đồ tuần/tháng, phải có luồng lưu historical events ở nơi phù hợp.
- Hệ thống cần ghi rõ **freshness/last observation time** để tránh hiển thị giá trị cũ như mới.

Nếu chỉ publish telemetry:

- Không tự cập nhật property.
- Một query `room.temperature` có thể vẫn là giá trị cũ.
- Phải có processor cập nhật state nếu cần.

**Không dùng ADT làm kho lưu hàng tỷ measurements** mà không có thiết kế về history, scale và chi phí.

## 18. Data history và phân tích chuỗi thời gian

Một hệ thống campus cần trả lời:

- Nhiệt độ phòng 101 trung bình 7 ngày qua?
- HVAC nào dùng điện nhiều nhất trong tháng?
- Sự cố cảm biến diễn ra trước hay sau khi occupancy tăng?
- Những phòng nào thường xuyên nóng hơn 28°C trên 15 phút?

Đây là các truy vấn lịch sử/tổng hợp, phù hợp với dịch vụ time-series analytics như **Azure Data Explorer** và các pipeline streaming liên quan, theo tính năng hỗ trợ.

```text
Azure Digital Twins
    |
    | Digital Twin updates / telemetry events / routes
    v
Event Hubs / supported history integration
    |
    v
Azure Data Explorer
    |
    +-- time-window aggregation
    +-- anomaly detection
    +-- historical visualization
    |
    v
Grafana / dashboards / analytical services
```

ADT có những tính năng tích hợp **data history** với Azure Data Explorer trong phạm vi hỗ trợ, nhưng **không phải cứ tạo ADT instance là history tự hoạt động**. Phải cấu hình event routes/integration, event schema, authorization, time retention và chi phí từng thành phần.

### Phân biệt ba loại dữ liệu

| Dữ liệu | Lưu ở đâu phù hợp? |
|---|---|
| **Topology**: Building chứa Room, Room phục vụ bởi HVAC nào. | ADT graph/relationships. |
| **Latest known operational state**: room temperature, HVAC health. | ADT twin properties hoặc state store theo thiết kế. |
| **Historical measurements**: một triệu readings qua 12 tháng. | Azure Data Explorer/ADLS/analytics storage. |

## 19. Query graph bằng Azure Digital Twins Query Language

ADT có ngôn ngữ truy vấn graph riêng. Nó **không phải SQL Database/T-SQL toàn năng**, dù cú pháp có những phần trông giống SQL.

### Tìm mọi twins theo model

```sql
SELECT *
FROM DIGITALTWINS T
WHERE IS_OF_MODEL(T, 'dtmi:example:campus:Room;1')
```

### Tìm rooms có nhiệt độ lớn hơn 27°C

```sql
SELECT room
FROM DIGITALTWINS room
WHERE IS_OF_MODEL(room, 'dtmi:example:campus:Room;1')
  AND room.temperature > 27
```

### Duyệt quan hệ Building → Room

```sql
SELECT room
FROM DIGITALTWINS building
JOIN room RELATED building.contains
WHERE building.$dtId = 'bldg-a'
```

Các truy vấn trên minh họa **ADT graph query**, không dùng y nguyên trong Azure SQL Database. Khi đưa vào ứng dụng, cần kiểm tra syntax/alias/cú pháp được phiên bản query engine hỗ trợ.

### Hạn chế cần nhớ

- Đừng xem ADT query như data warehouse có mọi phép JOIN/GROUP BY/ORDER BY/aggregations.
- Query thường cần lập kế hoạch graph traversal và filter phù hợp.
- Không gửi user input trực tiếp vào chuỗi query mà thiếu validation/escaping.
- Thực hiện authorization ở backend và trên kết quả nếu dùng graph chung nhiều tenants.
- Phải xử lý paging/continuation cho tập kết quả lớn.
- Với phân tích hàng tháng theo thời gian, dùng kho lịch sử/analytics.

## 20. Từ truy vấn đến câu trả lời vận hành

**Câu hỏi:** “Tòa nhà A có phòng nào quá nóng?”

Thay vì lấy tất cả readings và đoán vị trí, ứng dụng:

1. Query Building twin `bldg-a`.
2. Duyệt `contains` đến rooms.
3. Lọc `temperature > 27` trên latest known state.
4. Kiểm tra `lastObservedAtUtc`/freshness (nếu model có).
5. Kiểm tra `sensor.health` của các sensors liên quan.
6. Lấy thêm đồ thị lịch sử nhiệt độ từ Azure Data Explorer.
7. Đánh giá có đủ dữ liệu tin cậy để cảnh báo.
8. Trả phòng, ngưỡng, sensor và timestamp.
9. Nếu muốn điều chỉnh HVAC, chuyển qua workflow **được phê duyệt**.

**Một room có property 30°C nhưng timestamp cách đây hai ngày** không nên bị coi là “đang nóng” với độ tin cậy như measurement vừa đến.

## 21. Azure Digital Twins SDK: kết nối an toàn bằng identity

Ví dụ Python dành cho môi trường lab đã được tạo ADT instance và cấp quyền data-plane.

Cài packages trong dự án thực hành riêng:

```bash
python -m pip install azure-digitaltwins-core azure-identity
```

Cấu hình endpoint bằng biến môi trường:

```text
ADT_ENDPOINT=https://<your-instance-hostname>
```

**Không tự xây hostname từ tên resource** nếu chưa kiểm tra giá trị hostName thực trong Azure Portal. Kết nối bằng Microsoft Entra credential/managed identity:

```python
import os
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

endpoint = os.environ["ADT_ENDPOINT"]
client = DigitalTwinsClient(
    endpoint,
    DefaultAzureCredential(),
)

# Chỉ đọc graph trong ví dụ kiểm tra quyền.
for twin in client.query_twins(
    "SELECT * FROM DIGITALTWINS T "
    "WHERE IS_OF_MODEL(T, 'dtmi:example:campus:Room;1')"
):
    print(twin.get("$dtId"))
```

Điều kiện:

- Instance host hợp lệ và reachable qua network đã cấu hình.
- Principal có quyền **Azure Digital Twins Data Reader** hoặc quyền phù hợp với thao tác.
- Network/TLS/DNS hoạt động từ runtime thực.
- Model IDs đúng với instance.
- Query results được lọc theo **quyền nghiệp vụ** trước khi trả cho end user.

**Azure subscription Contributor không tự đồng nghĩa principal có quyền thao tác data-plane graph.**

## 22. SDK: tạo models, twins và relationships trong lab

Các đoạn mã sau minh họa thứ tự thao tác trong **môi trường thử nghiệm riêng**, không chạy trên Production.

### Bước 1 — Nạp models theo dependency

Ví dụ DTDL JSON strings phải được tạo từ các models ở phần 7–9.

```python
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

endpoint = "https://<your-instance-hostname>"
client = DigitalTwinsClient(endpoint, DefaultAzureCredential())

# Thay bằng các DTDL interfaces đã được kiểm tra trong bài:
sensor_model = {
    "@id": "dtmi:example:campus:Sensor;1",
    "@type": "Interface",
    "@context": "dtmi:dtdl:context;2",
    "contents": [
        {"@type": "Property", "name": "deviceId", "schema": "string"}
    ]
}
building_model = {
    "@id": "dtmi:example:campus:Building;1",
    "@type": "Interface",
    "@context": "dtmi:dtdl:context;2",
    "contents": [
        {"@type": "Property", "name": "name", "schema": "string"}
    ]
}

# Ví dụ giới thiệu API; nếu đã nạp model cùng ID thì không tạo trùng.
client.create_models([
    sensor_model,
    building_model,
])
```

**Lưu ý:** đây là ví dụ API dùng Python dictionaries, không phải danh sách đầy đủ 4 models của graph mẫu. Các model có relationship `target` và component dependency phải được tạo theo một batch/chuỗi hợp lệ sao cho các references resolve đúng, và không ghi đè model ID đã tồn tại. Kiểm tra kiểu dữ liệu đầu vào theo SDK version thực tế. Trong lab hoàn chỉnh cần nạp chính xác DTDL cho Building, Room, Sensor và HVAC trước khi dựng graph.

### Bước 2 — Tạo twins

```python
building = {
    "$dtId": "bldg-a",
    "$metadata": {"$model": "dtmi:example:campus:Building;1"},
    "name": "Tòa nhà A"
}

sensor = {
    "$dtId": "sensor-temp-01",
    "$metadata": {"$model": "dtmi:example:campus:Sensor;1"},
    "deviceId": "iot-sensor-01"
}

# Lab only: upsert có thể tạo hoặc cập nhật tài nguyên.
client.upsert_digital_twin("bldg-a", building)
client.upsert_digital_twin("sensor-temp-01", sensor)
```

**Cẩn trọng:** `upsert` không phải chỉ đọc. Một model/schema không tương thích có thể khiến thao tác thất bại. Không chạy trên tên twin đang tồn tại của tổ chức nếu chưa có approval.

### Bước 3 — Tạo quan hệ

Giả sử đã nạp đầy đủ model Building có `contains` và tồn tại room-101:

```python
relationship = {
    "$relationshipId": "bldg-a-contains-room-101",
    "$sourceId": "bldg-a",
    "$relationshipName": "contains",
    "$targetId": "room-101"
}

client.upsert_relationship(
    "bldg-a",
    "bldg-a-contains-room-101",
    relationship,
)
```

Vì đã có `Building.contains` và `room-101` là target, dịch vụ có thể kiểm tra schema/IDs. Nếu target twin hoặc model reference chưa tồn tại/hợp lệ, thao tác có thể bị từ chối.

## 23. SDK: cập nhật property bằng JSON Patch

Khi worker đã kiểm tra telemetry và xác định giá trị được chấp nhận, có thể cập nhật một property:

```python
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient
import os

client = DigitalTwinsClient(
    os.environ["ADT_ENDPOINT"],
    DefaultAzureCredential(),
)

# Ví dụ giả lập; chỉ chạy với twin room-101 trong lab.
patch = [
    {
        "op": "replace",
        "path": "/temperature",
        "value": 28.5,
    }
]

client.update_digital_twin(
    "room-101",
    patch,
)
```

**Cần kiểm tra**:

- Twin `room-101` đã có property `temperature`; `replace` không giống `add`.
- Model schema cho phép kiểu giá trị double phù hợp.
- Worker có quyền ghi data plane.
- Không cập nhật từ message bị trễ khi newer state đã được áp dụng.
- Các writers khác có thể cạnh tranh; cần concurrency control/ETag hoặc state ownership.
- Update đã thành công tại ADT **không tự bảo đảm** mọi downstream consumers/analytics đã xử lý xong.

### Nếu property chưa tồn tại?

JSON Patch `add` có behavior khác `replace`. Thiết kế trạng thái khởi tạo và kiểm tra patch operations theo API, tránh nhận lỗi “path not found” rồi retry vô hạn.

## 24. Quản lý concurrency và out-of-order telemetry

Giả sử cảm biến gửi:

```text
Event A: observed 09:01 → 28.5°C
Event B: observed 09:02 → 29.0°C

Network:
  B đến worker trước và cập nhật 29.0
  A đến sau và ghi đè thành 28.5
```

Nếu chỉ gọi `update_digital_twin` theo thứ tự nhận, **latest known state có thể đi lùi**.

### Biện pháp

1. Mang theo event timestamp và sequence từ nguồn đáng tin.
2. Lưu `lastObservedAtUtc`/lastSequence trong state model hoặc ingestion state store.
3. Chỉ chấp nhận event mới hơn checkpoint của cùng sensor/twin theo quy tắc.
4. Khi concurrent workers cập nhật, dùng **optimistic concurrency/ETag** nếu API và SDK hỗ trợ.
5. Dedupe `eventId` để retry không tạo side effect trùng.
6. Đặt ngưỡng clock skew; timestamp từ thiết bị không luôn đáng tin.
7. Với nhiều sensors, tính aggregated room state theo window rõ ràng.
8. Gửi sự kiện quá muộn tới lịch sử nhưng không nhất thiết cập nhật current property.
9. Có telemetry freshness alert, không chỉ high-temperature alert.
10. Test reordering và duplicate trong pipeline.

**Một kiểm tra read-then-write ở hai requests riêng có thể race**. Nếu cần bảo đảm chặt, thiết kế concurrency strategy phù hợp, không chỉ so timestamp ở memory rồi update không điều kiện.

## 25. Source of truth và ownership của twin properties

Một sai lầm phổ biến là cho nhiều hệ thống cùng ghi cùng property:

```text
IoT worker      → room-101.temperature
BMS integration → room-101.temperature
Manual operator → room-101.temperature
```

Khi đó giá trị bị ghi đè ngẫu nhiên và khó giải thích. Hãy đặt **ownership matrix**:

| Property/quan hệ | Nguồn authoritative | Chu kỳ cập nhật |
|---|---|---|
| Building.name | Asset register/BIM đã duyệt. | Khi thay đổi danh mục. |
| Room.location/floor | Facility management system. | Khi thay đổi cấu trúc. |
| Room.temperature | Sensor ingestion/aggregation worker. | Theo sample/quality policy. |
| Room.occupancy | Đầu vào được phê duyệt/aggregation. | Theo nghiệp vụ và privacy policy. |
| HVAC.operationalState | BMS/đơn vị điều khiển. | Khi trạng thái thay đổi. |
| Room.servedBy | Facility engineering/asset register. | Khi tái cấu hình thiết bị. |

Nên lưu metadata nguồn/observation timestamp khi model phù hợp và không thêm PII không cần thiết. Nguồn sở hữu phải có trách nhiệm xử lý khi đồng bộ dữ liệu sai hoặc bị mất.

## 26. Model graph không phải physical simulation engine

Một graph thể hiện mối quan hệ, nhưng không tự tính được:

- Nhiệt độ lan truyền qua các phòng theo phương trình vật lý.
- Mức tiêu thụ điện của HVAC từ công suất danh định.
- Mối quan hệ nguyên nhân giữa occupancy và chất lượng không khí.
- Một lệnh điều khiển chắc chắn có hiệu lực trên thiết bị.
- Dự báo bảo trì hoặc tối ưu setpoint nếu chưa có mô hình/thuật toán.

Muốn mô phỏng/dự báo, cần kết hợp:

- Model vật lý hoặc domain logic trong compute/analytics.
- Azure Machine Learning/AI nếu có dữ liệu và evaluation phù hợp.
- Time-series history để hiệu chuẩn.
- Quy tắc kiểm soát thiết bị, thresholds và fail-safe behavior.
- Human review hoặc safety constraints cho các quyết định ảnh hưởng con người.

**ADT cung cấp ngữ cảnh/topology/state**, không tự biến một mô hình DTDL thành “bản sao mô phỏng mọi hiện tượng”.

## 27. Kết nối dữ liệu BIM, GIS, ERP và BMS

Một mô hình môi trường thực cần dữ liệu từ nhiều hệ thống:

| Nguồn | Dữ liệu | Cách dùng |
|---|---|---|
| **BIM/CAD** | Các tầng, phòng, thiết kế thiết bị. | Tạo topology ban đầu hoặc đối chiếu location. |
| **GIS** | Tọa độ/khu vực/địa chỉ. | Liên kết không gian bên ngoài tòa nhà. |
| **ERP/CMDB** | Asset ID, nhà cung cấp, bảo hành, chi phí. | Metadata authoritative của tài sản. |
| **BMS/SCADA** | Setpoint, trạng thái điều khiển, cảnh báo. | Cập nhật operational state theo policy. |
| **IoT Hub/Edge** | Measurements, online/offline, device events. | Cập nhật latest state và history. |
| **Azure Data Explorer** | Lịch sử telemetry/aggregate. | Phân tích dài hạn và dashboards. |
| **Ticketing/work orders** | Các hạng mục bảo trì. | Liên hệ twin với workflow vận hành. |

### Tránh “một bản sao chứa mọi thứ”

Không nên sao chép toàn bộ ERP records/PII vào ADT chỉ vì twin có thể chứa properties. Hãy chỉ lưu **metadata cần cho graph/use case**, dùng reference IDs/authorized APIs để tra thông tin chi tiết ở hệ thống nguồn.

## 28. Tên ID, ontology và data governance

Một dự án quy mô lớn cần **naming convention và ontology**:

```text
Model IDs:
  dtmi:company:campus:Building;1
  dtmi:company:campus:Floor;1
  dtmi:company:campus:Room;1
  dtmi:company:campus:Sensor;1

Twin IDs:
  campus-hcm-bldg-a
  campus-hcm-bldg-a-floor-01
  campus-hcm-bldg-a-room-101
  device-sensor-00081

Relationships:
  bldg-a/contains/floor-01
  floor-01/contains/room-101
  room-101/monitoredBy/device-sensor-00081
```

Ví dụ ID trên chỉ là quy ước; giới hạn ký tự/độ dài và cách escape phải tuân theo API. Đừng dùng email/số điện thoại/secret trong IDs vì chúng có thể xuất hiện trong logs, URLs và diagnostics.

### Quy định trước triển khai

- Ai sở hữu một model và được sửa định nghĩa?
- Model versions có release notes và migration plan không?
- Hai team dùng cùng từ `contains` có cùng ý nghĩa không?
- Unit là °C hay °F? kW hay W? UTC hay local time?
- Thiết bị thay thế nhưng asset ID giữ nguyên hay đổi?
- Xóa/di chuyển room thì quan hệ cũ được xử lý thế nào?
- Có ngăn orphan relationships/stale graph không?
- Có tenant scope/permission matrix không?

**Đặt đúng ontology sớm** rẻ hơn sửa hàng triệu twins hoặc đổi semantic trong mọi dashboard sau này.

## 29. Thay đổi schema/model có version

Một yêu cầu mới: Room cần thêm `relativeHumidity` và `lastObservedAtUtc`. Không nên chỉnh model trên giấy rồi coi tất cả twins cũ có dữ liệu này.

Một quy trình:

1. Xác định additive hay breaking change.
2. Viết DTDL model **version mới** nếu yêu cầu.
3. Validate model dependencies và data types.
4. Đăng ký model trong môi trường thử nghiệm.
5. Sửa ingestion mapping, query và dashboard để hỗ trợ version chuyển tiếp.
6. Tạo/điều chỉnh twin instances theo API hợp lệ.
7. Backfill properties nếu có nguồn tin cậy.
8. Kiểm thử consumers đọc cả v1/v2 trong giai đoạn chuyển đổi.
9. Quan sát lỗi model validation/query.
10. Sau khi đủ điều kiện, retire old model/twins theo quy trình và giới hạn dịch vụ.

**Không tự giả định xóa model cũ an toàn**: có thể còn twins/relationships phụ thuộc. Khả năng xóa và version migration phải theo API/support conditions hiện hành.

## 30. Event routes và xử lý downstream

Khi twin thay đổi hoặc telemetry được publish theo tính năng, ADT có thể gửi events qua **event routes** tới endpoint được hỗ trợ như Event Grid, Event Hubs hay Service Bus.

```text
ADT graph
   |
   +-- Twin lifecycle/property change events
   |
   +-- Telemetry events (nếu được publish)
   |
   v
ADT event route + filter
   |
   +-- Event Grid → Azure Functions/Logic Apps
   |
   +-- Event Hubs → streaming consumers/analytics
   |
   +-- Service Bus → downstream workflow
```

### Những điểm cần quản lý

- Một route muốn hoạt động phải có **endpoint, permissions và filter** được cấu hình.
- Sự kiện gửi đi có **schema**, cần consumer tương thích.
- Delivery có thể trễ/lặp hoặc thất bại; không coi message bus là một transaction chung với twin update.
- Consumers phải idempotent, có retries và dead-letter/quarantine.
- Có cảnh báo khi route/endpoint lỗi hoặc lag tăng.
- Không gửi nội dung nhạy cảm sang một dịch vụ/region chưa được phê duyệt.
- Tránh vòng lặp: event từ ADT → processor cập nhật cùng twin → ADT phát event → vô hạn.

Một architectural pattern cần **event-origin/correlation IDs** và quy tắc không cập nhật lại khi trạng thái đã giống nhau để ngăn loop.

## 31. ADT và Digital Twin của IoT Plug and Play

Trong hệ sinh thái Azure IoT có các khái niệm khác như **IoT Plug and Play** và **device twins của IoT Hub**. Chúng **không đồng nhất** với Azure Digital Twins.

| Khái niệm | Mục tiêu |
|---|---|
| **IoT Hub device twin** | Thông tin desired/reported properties, tags và quản lý trạng thái một thiết bị trong IoT Hub theo cơ chế riêng. |
| **IoT Plug and Play model** | Hợp đồng khả năng/telemetry/commands của device, có thể dùng DTDL tùy hệ sinh thái. |
| **Azure Digital Twins graph twin** | Đối tượng trong graph của môi trường thực, có quan hệ với rooms/assets/processes khác. |

Một IoT Hub device twin có desired state không tự làm ADT graph twin được tạo. Dù có dùng DTDL ở cả hai ngữ cảnh, **data plane, permissions, relationships và cách đồng bộ** là khác nhau.

### Lựa chọn mô hình tích hợp

Thiết kế mapping tường minh:

```text
IoT Hub deviceId = iot-sensor-01
    |
    v
Mapping service:
  deviceId → Sensor twin sensor-temp-01
  Sensor twin → Room twin room-101
    |
    v
Accepted telemetry updates Room.temperature
```

Không dùng device-reported property làm source of truth cho dữ liệu tài sản khi dữ liệu đó cần được quản trị bởi đội facility.

## 32. Azure IoT Edge và xử lý trước khi gửi lên cloud

Ở nhà máy, kết nối Internet có thể gián đoạn. Thiết bị/cổng edge có thể:

1. Nhận Modbus/OPC UA hoặc tín hiệu từ sensors theo tích hợp phù hợp.
2. Validate, lọc outliers và chuẩn hóa units.
3. Tổng hợp dữ liệu theo cửa sổ (ví dụ 30 giây).
4. Buffer events khi mạng mất.
5. Gửi lên IoT Hub khi kết nối phục hồi.
6. Kèm timestamp/sequence để cloud xử lý sự kiện muộn.

```text
Physical sensors
      |
      v
Edge gateway
  - validation
  - sampling/aggregation
  - local buffer
      |
      v
Azure IoT Hub
      |
      v
Worker → ADT latest state
       → historical stream
```

### Hạn chế thiết kế

- Buffer lâu có thể làm dữ liệu cũ tràn về khi reconnect.
- Cloud worker không nên ghi đè current property bằng các readings đến trễ.
- Device authentication/key lifecycle tại edge vẫn cần quản trị.
- AI/model inference tại edge cần kiểm tra hardware, bản quyền và latency riêng.
- Cloud model graph có thể stale khi offline; hiển thị quality/freshness cho operator.

**Edge compute và ADT bổ sung cho nhau**, không tự giải quyết toàn bộ bài toán đồng bộ.

## 33. Thiết kế đồ thị nhiều tầng và hiệu quả truy vấn

Nếu campus có Building → Floor → Room → Sensor, nên xét truy vấn nào chạy thường xuyên.

### Graph nhiều tầng

```text
campus-a
   |
   +--contains--> bldg-a
                    |
                    +--contains--> floor-01
                                      |
                                      +--contains--> room-101
                                                          |
                                                          +--monitoredBy--> sensor-01
```

Lợi ích:

- Có cấu trúc gần môi trường thực.
- Query theo campus/building/floor thuận tiện.
- Rõ ràng khi thiết bị thay vị trí hoặc tầng được tái cấu hình.

Đánh đổi:

- Truy vấn phải đi qua nhiều relationships.
- Graph lớn cần tối ưu selectivity và kiểm soát result set.
- Nếu mỗi màn hình cần một topology snapshot lớn, có thể tạo **read model/cache** riêng ở ứng dụng.
- Thao tác di chuyển phòng/sensor phải cập nhật relationships và bảo toàn consistency nghiệp vụ.

### Denormalization có chọn lọc

Một Room twin có thể lưu `buildingId` để tra nhanh, nhưng nếu đồng thời có quan hệ `bldg-a --contains--> room-101` thì **hai biểu diễn có thể lệch nhau**. Phải chọn source of truth và đồng bộ theo quy trình, không chấp nhận graph và property mâu thuẫn âm thầm.

## 34. Data quality và diễn giải giá trị đo

Một cảm biến báo 35°C có thể do:

- Phòng thật sự quá nóng.
- Sensor bị đặt ngay cạnh cửa gió nóng.
- Thiết bị đo sai độ C/độ F.
- Sensor đã lỗi nhưng vẫn gửi dữ liệu.
- Timestamp lệch nhiều giờ.
- Message của tenant khác bị map nhầm vào room.
- Một giá trị giả tạo trong luồng kiểm thử.

Các bước kiểm tra trước khi cập nhật twin:

1. Xác thực device/producer.
2. Validate payload schema và numeric ranges.
3. Chuẩn hóa units (°C/°F, W/kW, kPa/Pa).
4. Xác thực mapping thiết bị → Sensor twin → Room twin.
5. Kiểm tra quality flag và sensor health.
6. Lọc giá trị outlier theo quy tắc đã duyệt.
7. Kiểm tra timestamp/sequence/duplication.
8. Xác định model property nào thật sự được update.
9. Ghi raw event vào kho lịch sử nếu cần forensics.
10. Cảnh báo về stale/untrusted state thay vì im lặng.

### Không làm “sạch dữ liệu” bằng cách tự thay số đo

Nếu hệ thống tự sửa 35°C thành 25°C chỉ vì vượt ngưỡng thông thường, có thể che mất sự cố cháy/nóng nguy hiểm. Quy tắc smoothing và outlier filtering phải có **domain owner**, giám sát và dấu vết.

## 35. Bảo mật: identity, RBAC và least privilege

ADT data plane dùng Microsoft Entra identity/role-based access theo khả năng hỗ trợ. Phân quyền cần tách:

| Lớp | Quyền | Ai nên có? |
|---|---|---|
| Azure control plane | Tạo/sửa ADT instance, networking, endpoints, role assignments. | Platform/infra team tối thiểu. |
| ADT graph data plane read | Truy vấn models/twins/relationships. | API reader/analyst được ủy quyền. |
| ADT graph data plane write | Tạo/sửa twins, properties, relationships, models theo vai trò. | Ingestion worker/graph administrator được kiểm soát. |
| IoT Hub data plane | Nhận/gửi device telemetry, quản lý identities khi cần. | IoT services đúng scope. |
| Analytics/ADX data plane | Truy vấn lịch sử. | Reporting backend/analyst. |
| Application authorization | User được xem khu vực/tòa nhà/tenant nào. | Backend nghiệp vụ. |
| Physical control authorization | Ai được bật/tắt thiết bị/đổi setpoint. | BMS/PLC workflow có kiểm soát an toàn. |

**Một người có quyền đọc graph ở data plane không mặc nhiên có permission xem mọi dữ liệu ở web app.** Nếu một ADT instance chứa nhiều tenants, app phải áp tenant ACL/boundary đúng, không dựa vào user truyền `buildingId` tùy ý.

### Managed identity

Azure Functions, Container Apps hoặc AKS workload identity có thể gọi ADT bằng `DefaultAzureCredential`/managed identity sau khi được gán role đúng scope. Bật identity **không tự cấp quyền**; cần kiểm tra resource roles và endpoint access.

Không đưa client secret hoặc access keys vào firmware, frontend hay repo chỉ để vượt lỗi 403. Với device identities, dùng cơ chế auth của IoT Hub phù hợp.

## 36. Network, TLS và dữ liệu vị trí nhạy cảm

Các thành phần có thể cần kết nối:

```text
IoT devices / Edge
      |
      v
IoT Hub
      |
      v
Functions/Worker trong network phù hợp
      |
      +-- Azure Digital Twins endpoint
      +-- Event Grid/Event Hubs/Service Bus
      +-- Azure Data Explorer
      +-- Storage/Key Vault
```

Cần kiểm tra:

- Dịch vụ/tier hỗ trợ Private Endpoint/private link/network restrictions thế nào.
- Private DNS có phân giải đúng từ worker/VNet không.
- NSG, Azure Firewall, UDR và outbound routes.
- TLS/hostname validation.
- Entra token audience và data-plane roles.
- Event destination/handler permissions.
- Logging có lộ vị trí nhân viên, hành vi occupancy hoặc camera metadata không.
- Retention đối với location/occupancy data.
- Data residency của graph, telemetry, history và logs.
- Môi trường DR có network/identity phù hợp không.

**Location/occupancy là dữ liệu có thể nhạy cảm.** Không đưa danh tính người đang ở từng phòng vào twin properties một cách vô điều kiện. Dùng aggregation, pseudonymization và privacy policy.

## 37. Eventual consistency, graph state và nhu cầu transaction

Đừng coi một thay đổi môi trường thực được cập nhật đồng thời ở mọi hệ thống.

Ví dụ di chuyển sensor từ Room 101 sang Room 102:

```text
T0 Facility DB ghi nhận sensor đổi vị trí
T1 Integration worker xóa relationship Room101 -> Sensor
T2 Integration worker thêm relationship Room102 -> Sensor
T3 Dashboard refresh graph
T4 Telemetry adapter update mapping
```

Có thể có **trạng thái trung gian** giữa T1–T4. Các hệ thống liên quan không nằm trong một distributed ACID transaction tự động.

### Cách thiết kế an toàn

1. Có **source of truth** cho việc di chuyển thiết bị.
2. Dùng **operationId/version** ổn định.
3. Đặt trạng thái thay đổi `Pending/Applied/Verified`.
4. Cập nhật mapping và graph theo workflow có retry.
5. Chặn telemetry adapter ghi vào room cũ khi mapping đã đổi.
6. Dùng reconciliation job kiểm tra relationship consistency.
7. Không thực hiện physical control cho tới khi hệ thống xác minh location.
8. Có kế hoạch rollback/compensation.
9. Ghi event source và thời điểm cutover.
10. Hiển thị “đang đồng bộ” khi topology chưa nhất quán.

**Azure Digital Twins không biến việc sửa nhiều nodes/edges và cập nhật IoT Hub/BMS thành một global transaction**. Nghiệp vụ phải xử lý eventual consistency.

## 38. Độ sẵn sàng, backup, phục hồi và mô hình hóa lại

Một hệ thống digital twin có hai nguồn để phục hồi:

- **Schema/topology state:** DTDL models, twin instances, relationship graph, thuộc tính/metadata.
- **Raw/history/source systems:** IoT events, asset register, BIM, BMS, ERP, logs.

Đặt câu hỏi:

1. Có thể **tái tạo graph** từ IaC/scripts/asset catalog/relationship exports không?
2. Có snapshot/export/versioned definition nào phù hợp policy không?
3. Dữ liệu mới nhất được lấy lại từ nguồn nào khi instance bị lỗi?
4. Có mất các latest properties chưa được lưu ở nơi khác không?
5. Event routes và endpoints có thể tái cấu hình được không?
6. Nếu sang region khác, model IDs và twin IDs có được giữ ổn định không?
7. Ứng dụng có biết đổi endpoint và reconnect với identity mới không?
8. Có dry-run restore với dữ liệu lab không?

**Không mặc định ADT cung cấp PITR/geo-replication giống SQL Database.** Thiết kế backup/restore/DR theo tính năng chính xác của dịch vụ và khả năng tái tạo từ authoritative sources.

## 39. Giám sát Azure Digital Twins và pipeline

Một số chỉ số cần quan sát:

| Nhóm | Tín hiệu | Ý nghĩa |
|---|---|---|
| Graph/data plane | Twin/relationship create/update/query failures. | Lỗi schema, quyền, capacity. |
| Event processing | IoT Hub ingress, Function failures, retries, DLQ. | Event bị mất/chậm hoặc sai payload. |
| Freshness | Time since last valid observation per sensor/twin. | Property đã cũ nhưng UI còn hiển thị. |
| Data quality | Invalid unit, outlier, unknown deviceId, mapping misses. | Nguy cơ state sai. |
| Graph integrity | Missing targets, orphan assets, conflicting relationships. | Topology không khớp thực tế. |
| Downstream | Event route delivery errors, lag, ADX ingestion failures. | Mất quan sát lịch sử/alerting. |
| Security | 401/403, role changes, suspicious reads/cross-tenant requests. | Permission drift hoặc attack. |
| Performance | p95 query/update latency, throttling/429, operation counts. | Resource/architecture bottleneck. |
| Costs | ADT operations/messages, event transport, history storage/compute, logs. | Dự báo và tối ưu chi phí. |

**Đừng khẳng định tất cả chỉ số trên là Azure Monitor metrics built-in cùng tên**. Nhiều thứ cần application-level telemetry hoặc reconciliation jobs, ngoài các built-in metrics/diagnostic logs theo API thực tế.

### Alert quan trọng

- Sensor không có event hợp lệ trong 10 phút khi dự kiến gửi mỗi phút.
- Ingestion worker liên tục retry 429/5xx.
- Tỷ lệ unknown deviceId tăng đột biến.
- ADT event route/ADX history ingestion không hoạt động.
- Một graph query bị 403 khi identity/role thay đổi.
- Số orphan relationships/asset mapping conflicts tăng.
- Chi phí thao tác hoặc logging tăng khác thường.

Ngưỡng 10 phút chỉ là **mốc minh họa**; phải dựa vào sampling rate, mạng, SLAs và mức quan trọng của tài sản.

## 40. Chi phí: không chỉ là giá một twin

Một kiến trúc gồm:

```text
Monthly total cost ≈
  Azure Digital Twins data-plane operations and messages
+ IoT Hub/device messaging
+ Azure Functions/Container Apps/Edge compute
+ Event Grid/Event Hubs/Service Bus
+ Azure Data Explorer/Storage historical data
+ Networking/Private Endpoint
+ Monitoring/Log Analytics
+ Model/topology maintenance and support
```

### Workload drivers

- Số lượng twins và relationships.
- Tần suất cập nhật properties, truy vấn graph và event routes.
- Số cảm biến × messages mỗi phút.
- Tần suất tổng hợp tại edge và lượng events gửi tới cloud.
- Số consumers và số lần reprocessing.
- Mức retention/history và truy vấn ADX.
- Tần suất đồng bộ asset catalog.
- Retry storms hoặc cập nhật property dù giá trị không đổi.

### Ví dụ ước lượng lượng telemetry

Giả sử có 1.000 cảm biến, mỗi cảm biến gửi 1 message/phút:

```text
1.000 sensors × 1 message/min = 1.000 messages/min
                              = 60.000 messages/hour
                              = 1.440.000 messages/day
```

**1,44 triệu messages/ngày không nhất thiết bằng 1,44 triệu twin property updates**: adapter có thể aggregate/dedupe và chỉ cập nhật khi state thay đổi. Chi phí từng dịch vụ có meter khác nhau; đo workload thực và dùng Azure Pricing Calculator theo region/tier hiện hành.

**Không giảm tần suất giám sát của một hệ thống an toàn quan trọng chỉ để giảm phí mà thiếu chấp thuận từ domain owner.**

## 41. Runbook: sensor có telemetry nhưng room.temperature không đổi

**Triệu chứng:** IoT Hub nhận dữ liệu mới, nhưng dashboard ADT Room 101 vẫn hiển thị 25°C trong khi đo thực 29°C.

### Điều tra

1. Xác định device ID, eventId và timestamp đo mới nhất.
2. IoT Hub đã route event tới đúng worker chưa?
3. Worker có bị lỗi message parse/schema/range không?
4. Device → Sensor twin → Room twin mapping có đúng không?
5. Worker có quyền update ADT và đúng endpoint/tenant không?
6. JSON Patch path `/temperature` có tồn tại trong twin schema/instance không?
7. Worker có áp idempotency/out-of-order logic và bỏ event nhầm không?
8. Có 429/5xx/network/TLS/permission errors không?
9. Dashboard query có cache cũ hoặc đang đọc wrong twin ID không?
10. Nếu property đã cập nhật, kiểm tra visualization refresh và client time zone.

### Khắc phục

- Sửa route/schema/mapping theo nguyên nhân.
- Replay event hợp lệ từ nguồn còn giữ, không tạo duplicate side effects.
- Dùng timestamp/sequence chống ghi đè ngược.
- Ghi source of truth và time freshness rõ trên UI.
- Đặt alert khi telemetry ingress còn hoạt động nhưng twin latest state stale.

## 42. Runbook: model hoặc relationship không tạo được

**Triệu chứng:** upload DTDL hoặc create relationship trả lỗi.

### Kiểm tra model

1. JSON hợp lệ chưa, `@context` đúng DTDL version không?
2. `@id` có đúng DTMI syntax/version không?
3. `@type` và `contents` đúng schema không?
4. Relationship `target` có trỏ model ID có thật/được resolve không?
5. Component `schema` có interface dependency hợp lệ không?
6. Có trùng model ID đã tồn tại không?
7. Model có vượt giới hạn/unsupported capability không?
8. Principal có quyền write models không?
9. Endpoint có đúng ADT instance không?

### Kiểm tra relationship

1. Source twin và target twin có tồn tại không?
2. Model của source có `contains/monitoredBy/servedBy` đúng tên không?
3. Target model có tương thích theo định nghĩa `target` không?
4. `$sourceId/$targetId/$relationshipName` có khớp payload không?
5. Relationship ID có xung đột hoặc định dạng không hợp lệ không?
6. Có thao tác đồng thời đổi/xóa twin liên quan không?

**Không xử lý mọi lỗi 400 bằng cách xóa model cũ.** Cần sửa DTDL/schema và quản trị version; xóa model có thể ảnh hưởng rất nhiều twins.

## 43. Runbook: đồ thị có đúng dữ liệu nhưng sai khu vực

**Triệu chứng:** Room 101 bị liên kết sang Building B dù asset register ghi thuộc Building A.

### Điều tra

- Nguồn tạo relationship ban đầu là import BIM/ERP nào?
- Có thay đổi room ID hoặc model version không?
- Có double writes từ hai integrations không?
- Twin IDs có chuẩn hóa theo campus/building/tenant không?
- Có worker đã phát sinh stale relationship do retry?
- Có mapping table được duyệt không?
- Tenant authorization có bị vượt ranh giới không?
- Dashboard có cache old graph không?

### Khắc phục

1. Xác nhận authoritative topology.
2. Tạm chặn pipeline ghi sai nếu cần.
3. Sửa relationship theo change request có audit.
4. Xác minh không có cạnh mồ côi/mâu thuẫn.
5. Cập nhật mapping và kiểm thử replay/reconciliation.
6. Đảm bảo dữ liệu sensor tương lai đi đúng room.
7. Thêm integration tests cho multi-tenant/hierarchy.

**Lỗi graph có thể trở thành lỗi quyền hoặc lỗi điều khiển vật lý**, không chỉ một dòng biểu đồ hiển thị sai.

## 44. Bài thực hành: mô hình hóa một tòa nhà trên Azure Digital Twins

**Bối cảnh:** một campus lab có tòa nhà A, hai phòng, một cảm biến nhiệt độ và một máy HVAC. Tất cả ID/giá trị là dữ liệu giả lập. Chỉ sử dụng Azure subscription/resource group và ADT instance lab đã được cấp phép.

### Mục tiêu graph

```text
                 [bldg-a]
                    |
       +------------+-----------+
       |                        |
    contains                  contains
       |                        |
       v                        v
   [room-101]              [room-102]
       |
       +---monitoredBy---> [sensor-temp-01]
       |
       +---servedBy------> [hvac-01]
```

### Dữ liệu dự kiến

| Twin ID | Model | Thuộc tính mẫu |
|---|---|---|
| `bldg-a` | Building;1 | name = "Tòa nhà A". |
| `room-101` | Room;1 | name="Phòng 101", temperature=25.1, occupancy=0. |
| `room-102` | Room;1 | name="Phòng 102", temperature=24.0, occupancy=2. |
| `sensor-temp-01` | Sensor;1 | deviceId="iot-sensor-01", health="Healthy". |
| `hvac-01` | HVAC;1 | name="HVAC A-01", operationalState="Running". |

### Nhiệm vụ

1. Viết một đoạn phân biệt ADT với IoT Hub và kho lịch sử.
2. Tạo tài khoản/ADT instance lab theo budget/phê duyệt; xác minh region, endpoint và quyền.
3. Hoàn chỉnh bốn DTDL v2 models: Building, Room, Sensor, HVAC.
4. Validate JSON, IDs, targets và dependencies trước khi upload.
5. Nạp models đúng thứ tự hoặc theo batch được SDK hỗ trợ.
6. Tạo năm twin instances theo models đã nạp.
7. Tạo hai relationships Building `contains` Rooms.
8. Tạo quan hệ Room 101 `monitoredBy` Sensor.
9. Tạo quan hệ Room 101 `servedBy` HVAC.
10. Query tất cả Room twins theo model.
11. Query các rooms thuộc Building A bằng JOIN RELATED.
12. Query Room có temperature > 27°C trước và sau update.
13. Gửi message IoT giả lập qua pipeline lab, không dùng thiết bị Production.
14. Adapter kiểm tra deviceId, timestamp, temperature unit và quality.
15. Cập nhật `room-101.temperature` bằng JSON Patch sau validation.
16. Kiểm chứng query Room 101 trả 28.5°C mới nhất.
17. Mô phỏng event cũ đến sau event mới; không được ghi đè current state.
18. Vẽ route từ ADT tới analytics/history và chỉ rõ điều kiện phải cấu hình.
19. Chỉ ra vì sao không thể đọc 7 ngày history từ một property duy nhất.
20. Thử một query bằng identity thiếu quyền; kỳ vọng 403/permission denial.
21. Thử tạo relationship tới target twin không tồn tại; xác nhận bị từ chối theo API.
22. Thiết kế mô hình version 2 khi cần thêm humidity.
23. Đặt ba alerts: stale sensor state, ingestion worker errors, event route failure.
24. Viết checklist dữ liệu vị trí/occupancy và least privilege.
25. Dự báo load/cost bằng số sensors × sampling interval.
26. Chuẩn bị cách xóa/tái tạo lab đúng quyền, không xóa tài nguyên dùng chung.

### Kết quả cần chứng minh

- Các DTDL models có IDs/version rõ ràng.
- Mỗi twin instance gắn đúng `$metadata.$model`.
- Có các relationship IDs/source/target phù hợp.
- Query graph trả đúng Rooms của Building A.
- State update đi qua adapter hợp lệ, không do device tùy ý ghi trực tiếp vào mọi twins.
- Event cũ không ghi đè state mới.
- Phân biệt latest state và time-series history.
- Có identity/network/safety restrictions.
- Có logs đã làm sạch và đo request counts/latency.
- Có kế hoạch model migration và khôi phục.

### Đáp án định hướng

Một thiết kế đạt yêu cầu sẽ để **IoT Hub quản lý kết nối thiết bị**, **Function/worker xử lý chất lượng sự kiện**, **ADT quản lý đồ thị và trạng thái mới nhất**, và **Azure Data Explorer hoặc kho lịch sử phù hợp xử lý analytics theo thời gian**. DTDL models chỉ định types/relationships; data-plane identities và application authorization quyết định ai được đọc/ghi, còn **BMS/control system** quyết định khi nào một lệnh thật được phép tác động môi trường.

## 45. Checklist khi triển khai Production

**Model/graph**

- [ ] Có danh mục physical assets, source of truth và ownership.
- [ ] Model IDs theo DTMI/version, DTDL schema được validate.
- [ ] Phân biệt model và twin instance, property và telemetry.
- [ ] Có naming convention, unit, timestamp và ID mapping.
- [ ] Relationships đúng hướng và có semantic nhất quán.
- [ ] Có quy trình quản lý orphan/stale graph và asset relocation.
- [ ] Có migration plan cho model version mới.
- [ ] Không nhét lịch sử lớn vào twin properties.

**Ingestion/consistency**

- [ ] IoT Hub/edge pipeline được xác thực và kiểm tra schema.
- [ ] Device IDs không được tin từ payload không xác minh.
- [ ] Mapping device → twin được quản trị và có tenant checks.
- [ ] Dedupe, retries, backoff và DLQ/quarantine được thiết kế.
- [ ] Có observedAtUtc/sequence và xử lý out-of-order.
- [ ] Freshness/quality/health hiển thị khi dữ liệu stale.
- [ ] State owner rõ ràng, tránh nhiều writers không kiểm soát.
- [ ] ADT event routes và history integration được kiểm chứng thực tế.

**Security/safety**

- [ ] Managed identity/data-plane roles đúng scope.
- [ ] Application authorization theo tenant/location.
- [ ] Private networking/DNS/TLS được kiểm tra từ runtime.
- [ ] Logs không lộ PII/vị trí nhạy cảm không cần thiết.
- [ ] Data residency/retention và consent được đánh giá.
- [ ] Control actions có rule engine, approval và fail-safe.
- [ ] Không coi một twin update là mệnh lệnh vật lý tự động.
- [ ] Có incident runbooks cho quyền, topology và data quality.

**Vận hành/chi phí**

- [ ] Metrics cho update/query failures, ingestion lag và route errors.
- [ ] Alerts khi sensors không gửi hoặc state stale.
- [ ] Có kế hoạch graph recovery/rebuild từ authoritative sources.
- [ ] Capacity/quota/429/backoff đã được kiểm thử.
- [ ] Cost model gồm ADT, IoT Hub, worker, events, history và logs.
- [ ] Có kiểm thử restore, model migration và change approval.
- [ ] Dọn dữ liệu/tài nguyên lab không ảnh hưởng Production.

## 46. Câu hỏi tự kiểm tra

**Câu 1.** Azure Digital Twins khác Azure IoT Hub ở mục tiêu nào?

**Đáp án:** ADT cung cấp mô hình đồ thị đối tượng/trạng thái/quan hệ môi trường; IoT Hub cung cấp kết nối và thông điệp thiết bị theo khả năng IoT Hub. Hai dịch vụ bổ sung, không thay thế nhau.

**Câu 2.** Model và twin instance có cùng ID không?

**Đáp án:** Không. DTDL model có DTMI như `dtmi:example:campus:Room;1`, còn instance có `$dtId` như `room-101`.

**Câu 3.** DTDL `Property` và `Telemetry` khác nhau thế nào?

**Đáp án:** Property biểu diễn dữ liệu trạng thái lưu trên twin; Telemetry khai báo sự kiện/measurement, không tự cập nhật property hoặc lưu lịch sử nếu không có pipeline.

**Câu 4.** Relationship `contains` từ Building tới Room có tự tạo cạnh ngược không?

**Đáp án:** Không. Quan hệ là cạnh có hướng; thiết kế truy vấn hoặc relationship ngược nếu cần.

**Câu 5.** Một Building có thể chứa nhiều rooms bằng một relationship instance duy nhất không?

**Đáp án:** Không theo cách đơn giản này; thường tạo nhiều relationship instances từ Building tới từng Room với IDs riêng.

**Câu 6.** `@id` của DTDL khác `$dtId` thế nào?

**Đáp án:** `@id` xác định model schema, `$dtId` xác định twin instance trong graph.

**Câu 7.** `@context` trong DTDL v2 có tác dụng gì?

**Đáp án:** Xác định ngữ cảnh/ngữ pháp DTDL; ví dụ `dtmi:dtdl:context;2`.

**Câu 8.** ADT có tự thu thập MQTT telemetry từ mọi sensor khi tạo Room twin không?

**Đáp án:** Không. Cần thiết bị/IoT Hub, ingestion worker và mapping/update logic.

**Câu 9.** Vì sao không dùng graph property nhiệt độ để vẽ biểu đồ 12 tháng?

**Đáp án:** Một property đại diện latest known state, không phải kho đầy đủ chuỗi thời gian; cần history pipeline/storage.

**Câu 10.** Azure Data Explorer và Azure Digital Twins bổ sung nhau ra sao?

**Đáp án:** ADT lưu topology/context/latest state; ADX phù hợp lưu và phân tích lịch sử sự kiện theo thời gian.

**Câu 11.** Một cảm biến gửi 29°C có nghĩa Room twin ngay lập tức thành 29°C không?

**Đáp án:** Không. Worker phải xác thực, map, validate và thực hiện cập nhật state.

**Câu 12.** Tại sao event timestamp quan trọng?

**Đáp án:** Sự kiện đến trễ có thể ghi đè giá trị mới; cần event time/sequence, idempotency và concurrency controls.

**Câu 13.** Twin instance có thể đại diện một phòng không có cảm biến riêng không?

**Đáp án:** Có. Nó vẫn là đối tượng môi trường với metadata/relationships, có thể được cập nhật từ nguồn quản lý hoặc các tính toán khác.

**Câu 14.** Component khác relationship ở đâu?

**Đáp án:** Component là phần có cấu trúc trong model/twin; relationship liên kết hai twins độc lập có IDs và lifecycle riêng.

**Câu 15.** Có thể dùng property `writable=true` để suy ra mọi user được phép ghi không?

**Đáp án:** Không. Đó là metadata schema, không phải Azure RBAC/application permission.

**Câu 16.** `IS_OF_MODEL` dùng để làm gì?

**Đáp án:** Lọc twins phù hợp model ID trong Azure Digital Twins Query Language.

**Câu 17.** ADT query có hỗ trợ mọi tính năng SQL Database không?

**Đáp án:** Không. Nó dành cho graph/twin queries; phân tích lịch sử và truy vấn tổng hợp lớn thường cần kho analytics.

**Câu 18.** Azure Contributor có tự cấp mọi data-plane quyền ADT không?

**Đáp án:** Không. Cần role data-plane phù hợp và application authorization riêng.

**Câu 19.** Managed identity được bật có nghĩa đã truy cập ADT được chưa?

**Đáp án:** Chưa. Cần role/scope, network/DNS/TLS và token audience phù hợp.

**Câu 20.** Có nên lưu tên người đang ở phòng vào mỗi twin property khi không cần cho nghiệp vụ không?

**Đáp án:** Không. Áp data minimization/privacy và chỉ lưu những gì được phép/cần thiết.

**Câu 21.** Một update property ADT thành công có nghĩa Event Hubs/ADX đã nhận xong không?

**Đáp án:** Không. Event route/downstream delivery có thể trễ hoặc thất bại; phải quan sát pipeline riêng.

**Câu 22.** Khi đổi model Room v1 sang v2, có thể sửa trực tiếp mọi model/twin một cách không ảnh hưởng ứng dụng không?

**Đáp án:** Không nên giả định. Cần versioning, migration và kiểm thử consumers/index/ingestion.

**Câu 23.** IoT Hub device twin có đồng nhất với Azure Digital Twins graph twin không?

**Đáp án:** Không. Chúng có data planes và mục tiêu khác nhau.

**Câu 24.** Azure IoT Edge giúp gì khi nhà máy mất mạng?

**Đáp án:** Có thể xử lý/buffer gần thiết bị, gửi lại khi mạng phục hồi; cloud vẫn phải xử lý sự kiện trễ/duplicate.

**Câu 25.** Một cảm biến bị di chuyển sang phòng khác cần cập nhật gì?

**Đáp án:** Nguồn mapping authoritative, graph relationship và pipeline liên quan theo quy trình, tránh hai nguồn ghi mâu thuẫn.

**Câu 26.** Graph có tự tính lan truyền nhiệt theo phương trình vật lý không?

**Đáp án:** Không. Cần simulation/domain logic/ML riêng nếu nghiệp vụ yêu cầu.

**Câu 27.** Vì sao không để AI agent tự gọi lệnh tắt HVAC chỉ vì twin báo nóng?

**Đáp án:** Twin state có thể stale/sai; điều khiển vật lý cần xác minh sensor, chính sách an toàn, authorization và fail-safe workflow.

**Câu 28.** Điều gì làm graph query multi-tenant nguy hiểm?

**Đáp án:** Nếu API chỉ lọc theo twin ID mà không kiểm tra quyền, có thể tiết lộ topology/vị trí của tenant khác.

**Câu 29.** Khi tăng số sensors, thành phần nào phát sinh chi phí?

**Đáp án:** IoT messages, ingestion compute, ADT operations/events, history storage/queries, network và monitoring.

**Câu 30.** Giá trị cốt lõi của ADT trong kiến trúc IoT/edge là gì?

**Đáp án:** Tạo **ngữ cảnh số có cấu trúc** cho các assets, không gian và mối quan hệ của chúng; liên kết dữ liệu và ứng dụng để truy vấn, phân tích và vận hành môi trường thực một cách có kiểm soát.

**Tóm lại:** **Azure Digital Twins** dùng **DTDL models** để định nghĩa các loại đối tượng, **twin instances** để biểu diễn tài sản/không gian và **relationships** để tạo đồ thị môi trường thực. IoT Hub/Edge cung cấp telemetry, Functions/worker xác minh và cập nhật trạng thái, event routes/kho lịch sử hỗ trợ downstream analytics. Thiết kế tốt phải phân biệt **latest state với telemetry history, model với instance, component với relationship và graph context với điều khiển vật lý**, đồng thời có versioning, authorization, data quality, concurrency, observability, backup/rebuild và quản lý chi phí. Một digital twin chỉ hữu ích khi **quan hệ đúng, dữ liệu đủ mới và việc sử dụng nó an toàn với thế giới thực**.
