# Bài toán time series và khác biệt với collection thông thường trong MongoDB

Một hệ thống quản lý tòa nhà nhận nhiệt độ của hàng nghìn cảm biến mỗi phút. Một nền tảng thương mại điện tử ghi nhận độ trễ API theo thời gian. Một công ty năng lượng thu thập số điện tiêu thụ mỗi 15 phút. Các dữ liệu này khác với hồ sơ khách hàng hay đơn hàng thông thường: **mỗi bản ghi là một phép đo hoặc sự kiện gắn với thời điểm**, liên tục được bổ sung, thường được truy vấn theo khoảng thời gian, rồi được tổng hợp thành biểu đồ hoặc báo cáo.

MongoDB có **time series collection** được tối ưu cho kiểu dữ liệu này. Ở góc nhìn của ứng dụng, ta vẫn `insertMany()`, `find()` và `aggregate()` trên những document đo lường. Nhưng bên trong, MongoDB tổ chức phép đo thành các **bucket** theo thời gian và metadata, có cơ chế nén/lưu trữ và tối ưu truy vấn khác với collection thông thường.

Điều quan trọng: **time series collection không chỉ là một regular collection có index trên ngày giờ**. Ngược lại, không phải dữ liệu nào có trường `createdAt` cũng nên đưa vào time series collection. Một đơn hàng có trạng thái thường xuyên thay đổi, cần unique business key và transaction cập nhật nhiều document có các yêu cầu khác hẳn chuỗi phép đo gần như append-only.

Bài thuộc chương **Chuỗi thời gian** của module *Database Engine Document MongoDB*. Các ví dụ dùng **mongosh** với database `time_series_lab`. Những tính năng liên quan cập nhật/xóa, indexing, sharding, cấu hình buckets, TTL và hỗ trợ một số thao tác đặc biệt có thay đổi giữa các phiên bản MongoDB. Những ví dụ ở đây chủ yếu sử dụng các khả năng cốt lõi; khi triển khai hãy kiểm tra **MongoDB server version, Feature Compatibility Version, driver và dịch vụ managed** thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện workload time series: phép đo có timestamp, metadata ổn định, ghi liên tục, truy vấn theo cửa sổ và tổng hợp.
2. Phân biệt **event time**, **ingestion time**, timestamp hợp lệ và trường hợp dữ liệu đến trễ.
3. Thiết kế document measurement với `timeField` bắt buộc và `metaField` tùy chọn.
4. Tạo time series collection bằng `createCollection()` và lựa chọn `granularity` phù hợp.
5. Hiểu cơ chế bucket nội bộ, nén dữ liệu và nguyên nhân meta cardinality ảnh hưởng hiệu quả nén.
6. So sánh time series với regular collection về lưu trữ, index, query, cập nhật, xóa, TTL và ràng buộc.
7. Viết truy vấn time range, lấy điểm đo gần nhất và aggregation theo phút/giờ/ngày.
8. Biết dùng `$dateTrunc`, `$group`, `$setWindowFields`, `$densify` và `$fill` cho các bài toán có hỗ trợ.
9. Thiết kế index cho truy vấn theo metadata và thời gian, không mặc định index thường áp dụng nguyên vẹn.
10. Chọn retention policy, hiểu TTL xóa theo bucket chứ không chính xác tới từng measurement ngay tức thời.
11. Phát hiện dữ liệu sai thời gian, missing/null, duplicate, out-of-order và sai đơn vị đo.
12. Quyết định khi nào giữ regular collection, khi nào dùng time series, hoặc kết hợp cả hai.
13. Lập kế hoạch nhập dữ liệu, migration, vận hành, backup và giám sát cho hệ thống đo lường.

## 2. Time series là loại bài toán gì?

Một **time series** là chuỗi giá trị hoặc sự kiện được sắp theo thời gian, thường gồm nhiều **series** được phân biệt bởi một hoặc nhiều thuộc tính.

Ví dụ:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:00:00Z"),
  meta: {
    sensorId: "sensor-01",
    buildingId: "building-A",
    metric: "temperature"
  },
  value: 25.6,
  unit: "C"
}
~~~

Ở đây:

- `observedAt` là **thời điểm quan sát**.
- `sensorId` và `metric` xác định series.
- `buildingId` mô tả một chiều phân tích/nhóm cảm biến.
- `value` là phép đo.
- `unit` giúp hiểu đúng ý nghĩa giá trị.

Mỗi phút thêm một document mới của cùng sensor, thay vì liên tục update một document chứa mảng tất cả điểm đo.

### 2.1. Các ví dụ phù hợp

| Bài toán | Thời điểm | Metadata tương đối ổn định | Giá trị thay đổi theo thời gian |
|---|---|---|---|
| Nhiệt độ phòng | Thời điểm cảm biến ghi | Sensor, tòa nhà, loại phép đo | Nhiệt độ, độ ẩm |
| CPU của máy chủ | Thời điểm scrape | Host, cluster, metric | CPU %, load average |
| Giá cổ phiếu | Thời điểm tick | Mã chứng khoán, thị trường | Giá, khối lượng |
| Điện năng | Kỳ chốt công tơ | Meter, khách hàng, loại đo | kWh |
| GPS tracker | Thời điểm thiết bị báo | Device, loại xe | Vĩ độ, kinh độ, tốc độ |
| Chất lượng không khí | Thời điểm mẫu | Trạm, khu vực, loại cảm biến | PM2.5, CO₂ |
| Event telemetry | Thời điểm event | Service, loại event | Latency, kích thước request |

### 2.2. Các bài toán chỉ “có ngày giờ” nhưng chưa chắc là time series

~~~javascript
{
  _id: "order-123",
  customerId: "c-01",
  createdAt: ISODate("2026-10-01T08:00:00Z"),
  status: "CREATED",
  total: NumberDecimal("150.00")
}
~~~

Đơn hàng có `createdAt`, nhưng record còn:

- Được cập nhật nhiều lần: CREATED → PAID → SHIPPED.
- Cần unique order ID, foreign references và kiểm soát consistency.
- Có thể tham gia transaction giữ hàng/thanh toán.
- Được tra cứu chủ yếu theo `orderId` hoặc customer, không chỉ theo time window.

Đây thường là trường hợp **regular collection**. Nếu muốn theo dõi trạng thái theo thời gian, bạn có thể giữ `orders` là regular collection và ghi thêm **append-only order events** vào một collection phù hợp (time series nếu đặc điểm event và giới hạn tính năng cho phép).

### 2.3. Quy tắc nhận diện nhanh

Hãy hỏi:

1. Mỗi document là **một observation/event mới** hay một **thực thể cần sửa liên tục**?
2. Query chủ yếu là “đoạn từ T1 đến T2 của device X”, “trung bình mỗi giờ”, “biểu đồ 30 ngày”?
3. Có ghi đều đặn từ nhiều nguồn với schema gần giống nhau không?
4. Dữ liệu cũ thường chỉ đọc/tổng hợp hoặc xóa theo retention, ít chỉnh sửa riêng từng điểm?
5. Metadata xác định series có ổn định đủ lâu để các phép đo được bucket hiệu quả không?

Nếu phần lớn câu trả lời là có, time series collection đáng cân nhắc. Nếu nghiệp vụ cần sửa/xóa tùy ý, unique constraints phức tạp hoặc transaction trên từng record, phải cân nhắc regular collection.

## 3. Khái niệm measurement, series và cửa sổ thời gian

Giả sử ba cảm biến ghi:

~~~text
sensor-01: 08:00 25.2°C -> 08:15 25.6°C -> 08:30 26.0°C
sensor-02: 08:00 24.1°C -> 08:15 24.4°C -> 08:30 24.8°C
sensor-03: 08:00 28.0°C -> 08:15 27.8°C -> 08:30 27.5°C
~~~

Mỗi sensor là một **series**. Một phép đo (measurement) là một document có timestamp và giá trị. Một báo cáo có thể:

- Lấy raw measurements cho sensor-01 trong 24 giờ.
- Tính nhiệt độ trung bình mỗi giờ cho mỗi tòa nhà.
- Lấy min/max trong ngày.
- Tìm sensor mất tín hiệu quá 30 phút.
- Cảnh báo khi nhiệt độ vượt ngưỡng.
- Tổng hợp từ dữ liệu 1 phút thành 15 phút hoặc 1 giờ để lưu dài hạn.

### 3.1. Raw vs aggregated

~~~mermaid
flowchart LR
    S["Cảm biến gửi điểm đo mỗi phút"] --> Raw["Raw measurements"]
    Raw --> Agg["Aggregation theo 15 phút / giờ"]
    Agg --> Dash["Dashboard / cảnh báo"]
    Raw --> Ret["TTL / retention"]
    Agg --> Hist["Lưu summary dài hạn"]
~~~

**Không nhất thiết phải truy vấn hàng trăm triệu raw points** cho mọi dashboard. Có thể duy trì bảng tổng hợp theo thời gian để cải thiện latency và kiểm soát chi phí.

### 3.2. Trục thời gian có ý nghĩa nghiệp vụ

Một ngày ở múi giờ Việt Nam không tương đương một ngày UTC. Khi báo cáo “ngày 01/10 tại Việt Nam”, phải xác định khoảng UTC tương ứng hoặc dùng timezone trong toán tử thời gian. Không nhóm theo chuỗi `"YYYY-MM-DD"` tùy tiện nếu dữ liệu toàn cầu có nhiều timezone.

## 4. Event time và ingestion time: hai trường khác nhau

Một thiết bị đo lúc 08:00 nhưng mất mạng, tới 08:20 mới gửi dữ liệu.

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:20:00Z"),
  meta: { sensorId: "sensor-01" },
  temperatureC: 25.2
}
~~~

Trong đó:

- **Event time (`observedAt`):** thời điểm phép đo thực sự xảy ra.
- **Ingestion/processing time (`receivedAt`):** thời điểm hệ thống nhận hoặc xử lý phép đo.

Nếu yêu cầu là biểu đồ nhiệt độ theo thời điểm cảm biến đo, `observedAt` thường nên là `timeField`. Nếu yêu cầu là số request API nhận được mỗi giây ở backend, thời điểm backend nhận có thể là timeField thích hợp.

### 4.1. Hậu quả khi dùng sai trường thời gian

Nếu dùng `receivedAt` cho báo cáo cảm biến, các điểm bị gửi muộn sẽ bị đặt vào 08:20 thay vì 08:00. Biểu đồ nhiệt độ “theo thời điểm đo” sẽ méo, và tính min/max theo cửa sổ thời gian có thể sai.

### 4.2. Đồng hồ thiết bị không luôn đáng tin

Một sensor có clock lệch 12 giờ có thể tạo:

~~~javascript
observedAt: ISODate("2026-10-01T20:00:00Z")
receivedAt: ISODate("2026-10-01T08:00:03Z")
~~~

Cần kiểm tra:

- Timestamp có nằm trong tương lai xa bất thường không?
- Độ trễ nhận dữ liệu có vượt ngưỡng được chấp nhận không?
- Thiết bị có đồng bộ NTP/clock không?
- Có cần lưu thêm `clockQuality`, `firmwareVersion` hoặc nguồn timestamp?

Time series collection tối ưu lưu trữ, **không tự xác minh chất lượng đồng hồ**.

### 4.3. BSON Date

`timeField` của time series collection phải chứa giá trị kiểu **BSON Date** hợp lệ. Một chuỗi:

~~~javascript
observedAt: "2026-10-01T08:00:00Z"
~~~

không thay thế cho:

~~~javascript
observedAt: ISODate("2026-10-01T08:00:00Z")
~~~

Ứng dụng cần parse và validate timezone/format trước khi ghi. Trong mongosh, `ISODate()` tạo BSON Date; driver ngôn ngữ khác có kiểu Date/Instant tương ứng.

## 5. Time series collection được khai báo như thế nào?

Khi tạo collection, dùng tùy chọn `timeseries`:

~~~javascript
use time_series_lab

db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})
~~~

Ba trường quan trọng:

| Tùy chọn | Bắt buộc? | Ý nghĩa |
|---|---|---|
| `timeField` | Có | Tên trường chứa BSON Date của phép đo |
| `metaField` | Không | Tên trường chứa metadata dùng để tổ chức các series/buckets |
| `granularity` | Tùy chọn | Gợi ý đặc điểm khoảng cách thời gian giữa phép đo, ảnh hưởng bucket organization |

### 5.1. `timeField`

`observedAt` là một field thực của document do ứng dụng ghi. MongoDB sử dụng nó để tổ chức measurements theo thời gian. Không chọn một field thay đổi liên tục với ý nghĩa “lastUpdatedAt” khi yêu cầu là thời điểm quan sát cố định.

### 5.2. `metaField`

`meta` có thể là một object:

~~~javascript
meta: {
  tenantId: "t-01",
  buildingId: "building-A",
  sensorId: "sensor-01"
}
~~~

Các field này mô tả nguồn measurement và thường không đổi giữa các lần đo. MongoDB dùng giá trị metaField để phân nhóm buckets; vì vậy nên đặt **series identity và thuộc tính tương đối ổn định** vào đây.

### 5.3. `granularity`

Các lựa chọn điển hình gồm `"seconds"`, `"minutes"`, `"hours"`. Đây là cách mô tả tần suất/khoảng cách đo dự kiến để MongoDB tổ chức buckets hợp lý; **không có nghĩa server chỉ chấp nhận timestamp đúng tròn phút/giờ**.

Ví dụ:

- Đo vài giây/lần: cân nhắc `seconds`.
- Đo khoảng vài phút/lần: cân nhắc `minutes`.
- Đo cách nhau nhiều giờ: cân nhắc `hours`.

Việc chọn phụ thuộc tần suất thực, phân phối event và khoảng truy vấn. Không phải `granularity="hours"` sẽ tự động tổng hợp dữ liệu thành một document mỗi giờ.

### 5.4. Các tùy chọn bucket tùy chỉnh

Ở các phiên bản hỗ trợ, MongoDB còn cung cấp những tùy chọn như `bucketMaxSpanSeconds` và `bucketRoundingSeconds` để kiểm soát độ rộng khoảng thời gian/bucket theo quy tắc tương ứng. Chúng có thể hữu ích cho workload đặc thù, nhưng đi kèm ràng buộc giá trị và không dùng tùy tiện cùng cách chỉ định granularity truyền thống. Trước tiên hãy dùng `granularity` dễ quản lý; chỉ tối ưu bucket custom sau khi có metrics về độ đầy buckets và query latency.

### 5.5. Tạo regular collection tương đương để so sánh

~~~javascript
db.createCollection("sensorReadingsRegular")

db.sensorReadingsRegular.createIndex(
  { "meta.sensorId": 1, observedAt: -1 },
  { name: "idx_regular_sensor_time" }
)
~~~

Hai collection có thể chứa **cùng schema measurement**. Sự khác biệt chính không phải ứng dụng viết document kiểu khác, mà là **cách MongoDB tổ chức/lưu trữ/index và giới hạn thao tác**.

## 6. Bộ dữ liệu lab: ba cảm biến, hai tòa nhà

Dữ liệu mẫu được thiết kế đủ nhỏ để tính kết quả bằng tay. Mỗi sensor gửi nhiệt độ và độ ẩm theo mốc 15 phút; một vài khoảng có phép đo đến trễ ở thời gian nhận.

~~~javascript
const samples = [
  // sensor-01: building-A, room-101
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 25.0, humidityPct: 55, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 25.4, humidityPct: 56, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.0, humidityPct: 55, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T09:07:00Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.6, humidityPct: 54, quality: "LATE" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 27.0, humidityPct: 53, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-01" }, temperatureC: 26.4, humidityPct: 54, quality: "OK" },

  // sensor-02: building-A, room-102
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.0, humidityPct: 61, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:04Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.2, humidityPct: 60, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.4, humidityPct: 60, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T08:45:03Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.6, humidityPct: 59, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:04Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 24.8, humidityPct: 58, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:02Z"), meta: { tenantId: "t-01", buildingId: "building-A", sensorId: "sensor-02" }, temperatureC: 25.0, humidityPct: 58, quality: "OK" },

  // sensor-03: building-B
  { observedAt: ISODate("2026-10-01T08:00:00Z"), receivedAt: ISODate("2026-10-01T08:00:05Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 28.0, humidityPct: 48, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:15:00Z"), receivedAt: ISODate("2026-10-01T08:15:04Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.7, humidityPct: 49, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:30:00Z"), receivedAt: ISODate("2026-10-01T08:30:05Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.5, humidityPct: 49, quality: "OK" },
  { observedAt: ISODate("2026-10-01T08:45:00Z"), receivedAt: ISODate("2026-10-01T08:45:04Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.3, humidityPct: 50, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:00:00Z"), receivedAt: ISODate("2026-10-01T09:00:03Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.1, humidityPct: 51, quality: "OK" },
  { observedAt: ISODate("2026-10-01T09:15:00Z"), receivedAt: ISODate("2026-10-01T09:15:03Z"), meta: { tenantId: "t-01", buildingId: "building-B", sensorId: "sensor-03" }, temperatureC: 27.0, humidityPct: 51, quality: "OK" }
]

db.sensorReadings.insertMany(samples)
db.sensorReadingsRegular.insertMany(samples)
~~~

Lưu ý:

- Chạy trên hai collection lab **rỗng**; chạy lại sẽ tạo phép đo trùng, vì không có unique constraint cho logical measurement được minh họa ở đây.
- Timestamp đều UTC (ký hiệu `Z`), dễ so sánh theo khoảng.
- `sensor-01` có phép đo lúc 08:45 được nhận muộn 22 phút, nhưng `observedAt` vẫn đúng.
- Schema của regular và time series giống nhau ở **góc nhìn ứng dụng**.
- Cả ba sensors cùng tenant t-01; lab không chứng minh kiểm soát phân quyền. Trong thực tế, tenantId phải lấy từ xác thực.

### 6.1. Kiểm tra số lượng

~~~javascript
db.sensorReadings.countDocuments({})        // 18
db.sensorReadingsRegular.countDocuments({}) // 18
~~~

Số phép đo theo sensor:

| Sensor | Building | Điểm đo | Nhiệt độ thấp nhất | Cao nhất |
|---|---|---:|---:|---:|
| `sensor-01` | A | 6 | 25.0 | 27.0 |
| `sensor-02` | A | 6 | 24.0 | 25.0 |
| `sensor-03` | B | 6 | 27.0 | 28.0 |

Là dữ liệu rất nhỏ, bài lab dùng để hiểu **semantics**. Không thể suy ra tỷ lệ nén, throughput hay query latency production từ 18 measurements.

## 7. Ứng dụng thấy document, MongoDB lưu buckets

Đối với regular collection, một document measurement tương ứng với một document lưu theo mô hình thông thường và các indexes tương ứng.

Đối với time series collection, MongoDB tổ chức nhiều measurements thành **bucket documents nội bộ** dựa trên metadata và khoảng thời gian. Bucket lưu thông tin như metadata, min/max thời gian và giá trị các field theo một cấu trúc thuận lợi cho nén và scan phân tích. Người dùng vẫn query logical measurements.

~~~mermaid
flowchart TD
    App["Ứng dụng insert phép đo"] --> TS["Time series collection: sensorReadings"]
    TS --> Group{"Nhóm theo meta + khoảng thời gian"}
    Group --> B1["Bucket sensor-01 / time window"]
    Group --> B2["Bucket sensor-02 / time window"]
    Group --> B3["Bucket sensor-03 / time window"]
    B1 --> Compress["Lưu trữ/nén column-oriented bên trong buckets"]
    B2 --> Compress
    B3 --> Compress
    Compress --> Query["find / aggregate trả logical measurements"]
~~~

### 7.1. Tại sao tổ chức kiểu bucket có ích?

Nhiều phép đo của cùng sensor thường:

- Có metadata giống nhau.
- Có các field giá trị giống nhau (`temperatureC`, `humidityPct`).
- Có timestamps gần nhau.
- Có numeric values thay đổi theo biên độ tương đối nhỏ.

Đây là điều kiện thuận lợi để nén dữ liệu theo cột/trình tự trong bucket, đồng thời giảm overhead lặp lại metadata so với lưu mỗi measurement độc lập bằng regular document.

### 7.2. Không truy vấn trực tiếp `system.buckets` như API nghiệp vụ

MongoDB duy trì storage nội bộ cho time series, thường có namespace liên quan `system.buckets.<collectionName>`. Nhưng ứng dụng **không nên trực tiếp đọc/ghi/chỉnh sửa các bucket documents** để thay thế `db.sensorReadings.find()`. Cấu trúc/biểu diễn nội bộ có thể thay đổi theo phiên bản, và thao tác sai có thể gây hỏng dữ liệu.

Hãy query thông qua **logical time series collection**; dùng các lệnh thống kê/explain được hỗ trợ để quan sát storage.

### 7.3. Buckets không có nghĩa một document cho mỗi giờ

Chọn `granularity:"minutes"` không tạo một bucket mới vào mọi đầu phút, cũng không bảo đảm mỗi sensor đúng một bucket mỗi giờ. Hệ thống quyết định bucket placement dựa trên metadata, thời gian, kích thước/số measurement và chính sách engine. Vì vậy:

> `granularity` giúp tổ chức buckets; `$dateTrunc`/`$group` mới là cách ứng dụng tạo một **giá trị tổng hợp mỗi giờ**.

### 7.4. Bucket pruning

Một truy vấn theo `meta.sensorId` và khoảng `observedAt` có thể cho optimizer bỏ qua nhiều buckets không liên quan nhờ metadata và thông tin thời gian/min-max. Đây là một lý do time series có thể đọc hiệu quả trên workload phù hợp. Hiệu quả thực còn phụ thuộc indexes, kích thước buckets, độ chọn lọc và query shape.

### 7.5. Truy vấn cần “unpack” phép đo

Khi trả raw measurements, engine có thể phải giải nén/“unpack” dữ liệu logical từ bucket. Một số kế hoạch có internal stage liên quan unpacking. Với báo cáo chỉ cần summary được tối ưu ở mức bucket trong một số trường hợp, engine có thể hạn chế số measurement phải materialize; nhưng không được giả định mọi phép tính đều bỏ qua unpack.

## 8. Cơ chế nén: time series khác regular collection thế nào?

Giả sử mỗi measurement chứa:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  meta: {
    tenantId: "t-01",
    buildingId: "building-A",
    sensorId: "sensor-01"
  },
  temperatureC: 25.4,
  humidityPct: 56
}
~~~

Trong regular collection, metadata được lặp lại trong mỗi document ở mô hình document storage bình thường. Có thể bật **collection compression** và tạo indexes, nên regular không đồng nghĩa “không nén”. Tuy nhiên, time series dùng **bucket-oriented/columnar compression** đặc biệt phù hợp chuỗi measurements lặp schema và metadata.

### 8.1. Các lợi thế có thể có

- Giảm dung lượng disk cho raw measurements lặp lại nhiều.
- Ít overhead lặp metadata ở storage.
- Cơ hội đọc những khoảng/nhóm measurements hiệu quả hơn.
- Truy vấn aggregation theo time range có thể được tối ưu dựa trên buckets.
- Retention theo thời gian được tích hợp vào time series collection.

### 8.2. Không có một tỷ lệ nén cố định

Đừng nói “time series luôn tiết kiệm 90%” hoặc “luôn nhanh gấp 10 lần”. Kết quả thay đổi theo:

- Số measurements trên bucket.
- Cardinality và độ ổn định của metadata.
- Schema/các field có lặp đều không.
- Kiểu giá trị và biên độ thay đổi.
- Khoảng cách thời gian của events.
- Late/out-of-order measurements.
- MongoDB version, compressor và workload.

Một tập dữ liệu với mỗi meta value chỉ có **một measurement** có thể không tận dụng được phần lớn lợi ích bucket compression.

### 8.3. Ví dụ ước lượng kích thước

Giả sử một sensor gửi 1 điểm/phút:

~~~text
60 điểm / giờ
1.440 điểm / ngày
525.600 điểm / 365 ngày
~~~

Với 10.000 sensors:

~~~text
5.256.000.000 measurements / 365 ngày (nếu gửi đều, không mất điểm)
~~~

Đây là quy mô rất lớn, khiến dung lượng, số lượng index entries, chi phí TTL và các báo cáo raw-history trở thành vấn đề. Các số chỉ tính theo nhịp ghi, **không phải dung lượng thực tế**; phải benchmark byte/measurement trên schema của bạn.

## 9. Thiết kế `metaField`: một trong những quyết định quan trọng nhất

MetaField mô tả **nguồn** hoặc **nhóm đo**. Ví dụ:

~~~javascript
meta: {
  tenantId: "t-01",
  buildingId: "building-A",
  sensorId: "sensor-01"
}
~~~

Các measurements của cùng sensor theo thời gian có thể được đưa vào buckets có metadata giống nhau.

### 9.1. Metadata nên ổn định

Ứng viên tốt:

- `tenantId`.
- `sensorId`/`deviceId`.
- `siteId`/`buildingId` nếu quan hệ tương đối ổn định.
- `metricType` nếu có nhiều loại series khác nhau và schema phù hợp.

Các giá trị nên được chuẩn hóa kiểu dữ liệu và naming.

### 9.2. Metadata thay đổi mỗi phép đo có thể phá hiệu quả bucket

Không nên:

~~~javascript
meta: {
  sensorId: "sensor-01",
  requestId: "req-unique-for-every-reading",
  receivedAt: ISODate("2026-10-01T08:15:03Z")
}
~~~

Nếu `requestId` và `receivedAt` thay đổi ở mỗi lần ghi, mỗi measurement có thể tạo một metadata value mới, khiến bucket grouping phân mảnh, nhiều buckets ít measurements và giảm compression/ingestion efficiency.

Đặt chúng ở field measurement thông thường:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  receivedAt: ISODate("2026-10-01T08:15:03Z"),
  eventId: "req-123",
  meta: { sensorId: "sensor-01" },
  temperatureC: 25.4
}
~~~

### 9.3. High cardinality không tự đồng nghĩa sai

Nếu có **một triệu sensors** và mỗi sensor ghi hàng nghìn điểm, `sensorId` vẫn là một series identity hợp lý mặc dù cardinality rất cao: mỗi sensor có nhiều measurements theo thời gian.

Vấn đề là **số measurements trên mỗi meta value/bucket và phân phối tốc độ gửi**, không phải chỉ nhìn số lượng distinct sensorIds.

### 9.4. Không gộp metadata khác nguồn chỉ để nén

Nếu bỏ `sensorId` khỏi meta để tất cả sensors trong cùng tòa nhà gom chung, query “sensor-01 trong 7 ngày” có thể phải lọc nhiều phép đo của những sensors khác trong cùng buckets. Có thể giảm cardinality nhưng tăng đọc và khiến dữ liệu khó quản lý.

Mục tiêu là sự cân bằng giữa **series identity, query predicates và độ đầy buckets**, không phải tối thiểu hóa số meta values bằng mọi giá.

### 9.5. Meta thay đổi theo thời gian thì sao?

Sensor có thể được chuyển phòng từ building-A sang building-B. Cần định nghĩa:

- Metadata trên measurement mô tả **vị trí tại thời điểm đo** hay **vị trí hiện tại**?
- Nếu dùng `buildingId` trong meta, những measurements mới sau khi chuyển có meta khác, tự nhiên thuộc series grouping khác.
- Nếu cần tra cứu thông tin thiết bị hiện tại, có thể lưu bảng `devices` riêng (regular collection) và join/application lookup.

Không bulk-update toàn bộ lịch sử chỉ để thay metadata thành vị trí hiện tại nếu yêu cầu phân tích lịch sử đòi đúng bối cảnh cũ.

## 10. Time series không tự định nghĩa uniqueness của logical measurement

Một phép đo có thể có business identity:

~~~text
(tenantId, sensorId, observedAt, metricType)
~~~

Nếu thiết bị retry cùng packet, database có thể nhận hai measurements tương đương:

~~~javascript
{
  observedAt: ISODate("2026-10-01T08:15:00Z"),
  meta: { tenantId: "t-01", sensorId: "sensor-01" },
  temperatureC: 25.4,
  eventId: "evt-001"
}
~~~

Time series collection tối ưu append, **không mặc định đảm bảo đúng một measurement cho cùng business key**. Các ràng buộc unique index của time series có những hạn chế nghiêm ngặt khác regular collection; không thiết kế ingestion dựa trên việc có thể tạo arbitrary unique index giống collection thường.

### 10.1. Retry an toàn ở tầng ingestion

Có thể dùng một regular collection `ingestLedger` với unique index trên `tenantId + eventId` để theo dõi packet đã xử lý, hoặc cơ chế dedupe ở broker/stream processor. Nhưng phải hiểu **rủi ro crash giữa ghi ledger và ghi measurement**, giới hạn transaction đối với time series theo phiên bản, và hợp đồng at-least-once/exactly-once thực tế.

Một thiết kế thường gặp:

~~~text
Sensor event có eventId cố định
  -> Queue/stream ingestion
  -> Dedupe theo eventId với storage phù hợp
  -> Insert measurement vào time series
  -> Checkpoint/reconciliation
~~~

Nếu workload yêu cầu **strict uniqueness + multi-document atomicity** cho từng điểm, regular collection hoặc data model/ingestion protocol chuyên biệt có thể dễ bảo đảm correctness hơn.

### 10.2. Không dùng `_id` như câu trả lời duy nhất

Đừng mặc định `_id` uniqueness, unique indexes và upsert của time series có cùng semantics như regular collection trong mọi phiên bản. Khi cần exactly-once effect ở cấp business event, phải xác định rõ ràng lớp dedupe nào thực sự enforce uniqueness và cách phục hồi khi retry.

## 11. Truy vấn raw measurements theo sensor và khoảng thời gian

Truy vấn phổ biến:

~~~javascript
db.sensorReadings.find(
  {
    "meta.tenantId": "t-01",
    "meta.sensorId": "sensor-01",
    observedAt: {
      $gte: ISODate("2026-10-01T08:00:00Z"),
      $lt: ISODate("2026-10-01T09:00:00Z")
    }
  },
  {
    _id: 0,
    observedAt: 1,
    temperatureC: 1,
    humidityPct: 1
  }
).sort({ observedAt: 1 })
~~~

Với lab, truy vấn trả các mốc 08:00, 08:15, 08:30, 08:45 của `sensor-01`. Phép đo 08:45 có `receivedAt=09:07` **vẫn được trả** vì filter dùng event time.

### 11.1. Dùng cửa sổ nửa mở

Thường viết:

~~~javascript
observedAt: { $gte: start, $lt: end }
~~~

thay vì `$lte:end` để tránh đếm trùng measurement nằm đúng ranh giới khi ghép nhiều cửa sổ liên tiếp:

~~~text
[08:00, 09:00)
[09:00, 10:00)
~~~

Điểm 09:00 chỉ thuộc cửa sổ thứ hai.

### 11.2. Lọc meta sớm

Nếu collection có hàng triệu sensors, chỉ filter theo thời gian có thể đọc nhiều buckets của sensors không liên quan. Filter theo `meta.sensorId` và `observedAt` giúp thu hẹp both **series** và **time window**.

### 11.3. Projection

Nếu API chỉ cần biểu đồ nhiệt độ, không trả toàn bộ document bao gồm payload kỹ thuật, chữ ký, raw JSON từ thiết bị. Projection giảm byte qua mạng, nhưng không mặc định mọi truy vấn trở thành covered query; phải xem plan thực tế.

### 11.4. Pagination và streaming

Một API vẽ biểu đồ không nên trả một lần 20 triệu measurements. Sử dụng:

- Time range có giới hạn.
- Cursor hoặc phân trang theo timestamp + khóa tie-breaker khi cần.
- Downsampling/aggregation theo độ phân giải màn hình.
- Giới hạn số points trả cho mỗi biểu đồ.

`$skip` sâu trên một chuỗi rất dài có thể tốn kém; keyset pagination với khóa ổn định phù hợp hơn khi cần đọc tuần tự.

## 12. Lấy điểm đo mới nhất của một sensor

Một truy vấn:

~~~javascript
db.sensorReadings.find(
  {
    "meta.tenantId": "t-01",
    "meta.sensorId": "sensor-01"
  },
  {
    _id: 0,
    observedAt: 1,
    temperatureC: 1,
    humidityPct: 1
  }
).sort({ observedAt: -1 }).limit(1)
~~~

Với lab, điểm đo mới nhất theo `observedAt` là **09:15, 26.4°C**.

### 12.1. “Mới nhất” có hai nghĩa

Nếu query sort theo `receivedAt`, điểm nhận muộn 08:45 (receivedAt 09:07) có thể đứng ở vị trí khác so với sort theo `observedAt`. Trong lab, bản ghi mới nhất theo cả hai tại 09:15, nhưng tình huống thực tế có dữ liệu đến trễ sau nhiều giờ có thể khác.

Hãy định nghĩa:

- **Latest observed:** phép đo có event time lớn nhất.
- **Latest received:** packet backend nhận gần nhất.

Không để API trả một loại khi người dùng kỳ vọng loại kia.

### 12.2. Latest state cache là bài toán khác

Nếu mỗi giây dashboard phải hiển thị trạng thái hiện tại của 100.000 sensors, truy vấn time series raw theo từng sensor có thể tạo workload đọc lớn. Có thể duy trì một **regular collection `sensorLatest`** lưu một document mỗi sensor, được cập nhật khi event mới nhất đến:

~~~javascript
{
  _id: "t-01:sensor-01",
  observedAt: ISODate("2026-10-01T09:15:00Z"),
  temperatureC: 26.4,
  humidityPct: 54
}
~~~

Collection raw history phục vụ phân tích theo thời gian; collection latest state phục vụ lookup hiện tại với latency thấp. Cần xử lý late arrivals để bản ghi cũ **không ghi đè current state**.

## 13. Aggregation theo cửa sổ: trung bình nhiệt độ mỗi giờ

Một báo cáo điển hình:

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      avgC: { $avg: "$temperatureC" },
      minC: { $min: "$temperatureC" },
      maxC: { $max: "$temperatureC" }
    }
  },
  { $sort: { "_id.hour": 1 } }
])
~~~

### 13.1. Kết quả từ lab

Đối với sensor-01:

~~~text
08:00–08:59:
  25.0, 25.4, 26.0, 26.6
  count = 4
  avg   = 25.75°C
  min   = 25.0°C
  max   = 26.6°C

09:00–09:59:
  27.0, 26.4
  count = 2
  avg   = 26.7°C
  min   = 26.4°C
  max   = 27.0°C
~~~

### 13.2. Timezone trong `$dateTrunc`

Nếu nhóm theo “giờ tại Việt Nam”, có thể chỉ định:

~~~javascript
{
  $dateTrunc: {
    date: "$observedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Lưu timestamps dưới dạng UTC Date nhưng nhóm/hiển thị theo timezone đúng nhu cầu. Đây là cách tránh sai lệch báo cáo ngày/tháng khi dữ liệu quốc tế.

### 13.3. Nhóm theo sensor và thời gian

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      avgC: { $avg: "$temperatureC" },
      measurements: { $sum: 1 }
    }
  },
  { $sort: { "_id.sensorId": 1, "_id.hour": 1 } }
])
~~~

Một query có thể tạo summary cho cả ba sensors. Với millions of series, số nhóm có thể rất lớn; hãy filter time range, phân vùng phù hợp và cân nhắc pre-aggregation.

## 14. Tính toán `$dateTrunc` khác lưu time series bucket

Hai khái niệm dễ bị nhầm:

| Khái niệm | Được dùng ở đâu? | Công dụng |
|---|---|---|
| Storage bucket nội bộ | MongoDB time series engine | Gom/nén measurements theo metadata và thời gian |
| `$dateTrunc` | Aggregation pipeline | Chuẩn hóa thời điểm về đầu phút/giờ/ngày |
| `$group` theo kết quả `$dateTrunc` | Aggregation | Tạo summary một dòng/cửa sổ |
| Materialized hourly summary | Collection khác | Lưu kết quả tổng hợp để đọc nhanh về sau |

Không có bảo đảm **mỗi storage bucket** trùng một giờ lịch, và không nên truy cập storage buckets trực tiếp để tạo biểu đồ. Dùng aggregate theo **ngữ nghĩa thời gian của nghiệp vụ**.

## 15. Cửa sổ trượt với `$setWindowFields`

Đôi khi cần smoothing/rolling average: ví dụ giá trị trung bình của **ba measurements liên tiếp**.

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: { observedAt: 1 },
      output: {
        movingAvg3: {
          $avg: "$temperatureC",
          window: {
            documents: [-2, "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      observedAt: 1,
      temperatureC: 1,
      movingAvg3: 1
    }
  }
])
~~~

Với sensor-01:

~~~text
08:00: avg(25.0)                   = 25.0
08:15: avg(25.0,25.4)              = 25.2
08:30: avg(25.0,25.4,26.0)         = 25.466...
08:45: avg(25.4,26.0,26.6)         = 26.0
09:00: avg(26.0,26.6,27.0)         = 26.533...
09:15: avg(26.6,27.0,26.4)         = 26.666...
~~~

### 15.1. Document window khác time window

`documents:[-2,"current"]` lấy tối đa hai **measurement documents trước** và điểm hiện tại, không nhất thiết là đúng 30 phút. Nếu sensor mất tín hiệu cả giờ, ba điểm gần nhất có thể cách nhau rất xa.

Nếu nghiệp vụ yêu cầu **trung bình của 30 phút gần nhất theo event time**, cần chọn kiểu window theo khoảng thời gian với cú pháp và dữ liệu phù hợp; không lẫn “ba record” với “ba khoảng 15 phút”.

### 15.2. Duplicate timestamps

Nếu cùng sensor có hai measurements cùng `observedAt`, sort theo thời gian chưa tạo thứ tự duy nhất. Với window functions dựa trên document positions, cần chính sách tie-breaker/measurement identity để kết quả xác định. Time series không tự giải quyết duplicate hoặc ordering ambiguity.

## 16. Dữ liệu thiếu và khoảng không có phép đo

Time series không đảm bảo mỗi phút luôn có một document. Cảm biến có thể bị mất mạng, bảo trì hoặc bị loại do validation.

Ví dụ:

~~~text
10:00 -> 25.0
10:15 -> 25.5
10:30 -> [mất điểm]
10:45 -> 26.2
~~~

Nếu vẽ biểu đồ, ứng dụng phải quyết định:

- Để **khoảng trống** thay vì tự suy ra giá trị.
- Điền bằng giá trị gần nhất trước đó (LOCF).
- Nội suy tuyến tính.
- Gắn cờ “estimated/imputed” để không nhầm phép đo thực.

### 16.1. `$densify` tạo các mốc còn thiếu

Ở các phiên bản hỗ trợ `$densify` (MongoDB 5.1+), có thể sinh các mốc thời gian theo bước nhất định trong aggregation. Ví dụ dùng một series và khoảng giờ có kiểm soát:

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  { $project: { _id: 0, observedAt: 1, temperatureC: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-10-01T08:00:00Z"),
          ISODate("2026-10-01T10:00:00Z")
        ]
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

Vì lab đủ sáu điểm từ 08:00 đến 09:15 nhưng không có 09:30/09:45, có thể quan sát thêm những mốc được tổng hợp trong khoảng bounds tương ứng. Chúng không phải measurements đã lưu; chúng được **tạo trong pipeline**.

### 16.2. `$fill` điền dữ liệu theo chính sách

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.sensorId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  { $project: { _id: 0, observedAt: 1, temperatureC: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-10-01T08:00:00Z"),
          ISODate("2026-10-01T10:00:00Z")
        ]
      }
    }
  },
  {
    $fill: {
      sortBy: { observedAt: 1 },
      output: {
        temperatureC: { method: "locf" }
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

`locf` (last observation carried forward) lấy giá trị gần nhất trước đó cho điểm trống. **Đây là giả định mô hình**, không phải phép đo thực. Với nhiệt độ phòng có thể hợp lý trong ngắn hạn; với giá tài sản hay sự kiện cảnh báo, cùng quy tắc có thể làm sai phân tích.

### 16.3. Không tạo hàng triệu mốc ngoài nhu cầu

`$densify` trên vài năm dữ liệu với bước 1 giây có thể sinh lượng document rất lớn. Giới hạn:

- Khoảng thời gian.
- Số series được chọn.
- Step/độ phân giải.
- Số points tối đa trả về.

Nên tổng hợp/downsample ở mức phù hợp trước khi trả biểu đồ.

## 17. Chỉ số chất lượng dữ liệu: đừng coi missing bằng 0

Một sensor không gửi phép đo lúc 08:30. Nếu hệ thống tự thêm giá trị 0°C, trung bình sẽ giảm sai.

Trong hệ thống telemetry:

- **0** có thể là giá trị đo thực.
- **null** có thể là phép đo không hợp lệ.
- **missing document** nghĩa là không có measurement ở mốc đó.
- **estimated** là giá trị được nội suy.
- **outlier** là giá trị tồn tại nhưng đáng ngờ.

Đây là những trạng thái khác nhau.

### 17.1. Ví dụ aggregation loại measurement không đạt quality

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "t-01",
      quality: "OK",
      observedAt: {
        $gte: ISODate("2026-10-01T08:00:00Z"),
        $lt: ISODate("2026-10-01T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$meta.sensorId",
      validCount: { $sum: 1 },
      avgC: { $avg: "$temperatureC" }
    }
  }
])
~~~

Trong lab, sensor-01 có điểm 08:45 `quality:"LATE"`. Việc loại nó có đúng không phụ thuộc **policy**: đến trễ không tự đồng nghĩa đo sai. Có thể một báo cáo retrospective phải **giữ** late measurement nhưng dashboard real-time tính chỉ những điểm đã nhận tại thời điểm đó.

### 17.2. Coverage

Nếu kỳ vọng 4 điểm/giờ mà chỉ nhận 3, coverage = 75%. Có thể tính coverage dựa trên schedule của từng sensor, nhưng cần chú ý thời gian downtime/maintenance, timezone và sensors gửi không đều. Time series không tự biết expected frequency của thiết bị.

## 18. Index: time series không giống regular collection

Trên regular collection, ta có thể tạo index:

~~~javascript
db.sensorReadingsRegular.createIndex(
  { "meta.sensorId": 1, observedAt: -1 },
  { name: "idx_regular_sensor_time" }
)
~~~

Trên time series collection, MongoDB hỗ trợ nhiều kiểu secondary index ở các phiên bản hiện đại, nhưng **indexing hoạt động với storage buckets và các ràng buộc đặc thù**. Không giả định mọi kiểu index, unique index, text index hoặc index option của regular collection đều được hỗ trợ y hệt.

### 18.1. Index theo metadata và thời gian

~~~javascript
db.sensorReadings.createIndex(
  {
    "meta.sensorId": 1,
    observedAt: -1
  },
  { name: "idx_ts_sensor_time" }
)
~~~

Đây là một index ứng viên cho:

~~~javascript
db.sensorReadings.find({
  "meta.sensorId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})
~~~

Trong một số phiên bản MongoDB, hệ thống tự tạo index theo meta/time khi collection được tạo và có metaField. Kiểm tra `getIndexes()` để **tránh tạo index trùng**. Đừng coi một default index cụ thể là bảo đảm không đổi qua mọi phiên bản.

### 18.2. Index theo tenant/building/sensor

Nếu query thường lọc:

~~~javascript
{
  "meta.tenantId": "t-01",
  "meta.buildingId": "building-A",
  "meta.sensorId": "sensor-01",
  observedAt: { $gte: start, $lt: end }
}
~~~

có thể xem xét index:

~~~javascript
db.sensorReadings.createIndex(
  {
    "meta.tenantId": 1,
    "meta.buildingId": 1,
    "meta.sensorId": 1,
    observedAt: -1
  },
  { name: "idx_ts_tenant_building_sensor_time" }
)
~~~

Tuy nhiên, nên dựa trên **query frequency, selectivity, cardinality và explain**. Index dài có chi phí ghi và storage; không tạo chỉ vì schema có nhiều field.

### 18.3. Query chỉ theo time range

Một query:

~~~javascript
db.sensorReadings.find({
  observedAt: { $gte: start, $lt: end }
})
~~~

đọc nhiều sensors trong khoảng time range. Có thể vẫn hiệu quả nếu khoảng ngắn, nhưng nếu hàng triệu sensors và thời gian dài, lượng data scan lớn. Index bắt đầu bằng sensorId không phải lựa chọn tối ưu cho mọi query chỉ timeField; thiết kế indexes theo workload thật.

### 18.4. Unique indexes và logical deduplication

Time series collections có **giới hạn đáng kể đối với unique indexing** so với regular collections. Nếu nghiệp vụ cần enforce uniqueness:

~~~text
tenantId + sensorId + observedAt + metricType
~~~

đừng tự dựa vào việc tạo unique compound index tùy ý trên time series. Hãy đọc quy tắc phiên bản, và nếu không hỗ trợ constraint bắt buộc thì thiết kế ingestion dedupe/regular collection phù hợp.

### 18.5. Index không tự làm dữ liệu tốt

Một query index tốt có thể trả kết quả nhanh dù dữ liệu chứa duplicate measurements, timestamps sai timezone hoặc giá trị ngoài phạm vi vật lý. Index tối ưu **access path**, không thay schema validation/quality checks.

## 19. Đọc `explain()` và thống kê lưu trữ

So sánh query tương đương:

~~~javascript
const predicate = {
  "meta.sensorId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
}

db.sensorReadings.explain("executionStats").find(predicate)
db.sensorReadingsRegular.explain("executionStats").find(predicate)
~~~

Với time series, kế hoạch có thể phản ánh:

- Scan trên index hoặc buckets.
- Điều kiện thời gian/metadata được đẩy xuống mức buckets.
- Một stage nội bộ giải nén/unpack measurements.
- Các stage xử lý thêm trên logical documents.

Với regular collection, plan thường cho thấy `IXSCAN`, `FETCH` hoặc `COLLSCAN` trên document/index storage tương ứng.

**Tên/đường dẫn stage trong `explain` phụ thuộc phiên bản và query engine**, không nên cứng hóa kiểm tra dựa vào một tên stage duy nhất.

### 19.1. Những số liệu cần đo

| Nhóm | Chỉ số hữu ích | Câu hỏi |
|---|---|---|
| Query | `nReturned` | Trả bao nhiêu logical measurements? |
| Index | `totalKeysExamined` | Đã đọc bao nhiêu index keys? |
| Document | `totalDocsExamined` | Đã xem bao nhiêu storage documents/buckets theo plan? |
| Time | Execution duration, p95/p99 | Có đạt SLO không? |
| Storage | `storageSize` / compressed bytes | Dung lượng có giảm không? |
| Index | `totalIndexSize` | Index chiếm bao nhiêu disk? |
| Ingest | Measurements/sec, insert latency | Ghi có bền vững khi tải tăng? |
| Bucket | Số/độ đầy/độ nén buckets nếu công cụ cung cấp | Metadata/granularity có phù hợp? |

**Chú ý:** `docsExamined` của một số plan time series có thể phản ánh số **bucket documents** thay vì số logical measurements. Không lấy số này so trực tiếp 1:1 với `docsExamined` của regular collection rồi kết luận time series tốt hơn X lần. Cần giải thích đúng plan và so latency/bytes/cpu trên workload đại diện.

### 19.2. `stats()` và storage

~~~javascript
db.sensorReadings.stats()
db.sensorReadingsRegular.stats()
~~~

Hoặc command thống kê collection ở phiên bản hỗ trợ:

~~~javascript
db.runCommand({ collStats: "sensorReadings" })
~~~

Đọc thống kê storage/index và các field chuyên cho time series nếu phiên bản cung cấp. Những field như số buckets hoặc bucket compression stats không nhất thiết xuất hiện giống nhau trên mọi phiên bản.

### 19.3. Đừng benchmark bằng 18 documents

Với 18 measurements, MongoDB có thể chọn COLLSCAN vì index không mang lợi thế và bucket overhead chưa được amortize. Để đánh giá thật:

- Tạo dữ liệu với số sensors và tần suất tương tự production.
- Có cả dữ liệu đến đúng thứ tự và đến trễ.
- Chạy truy vấn theo patterns thật (per-sensor, per-building, all-sensor rollup).
- Đo ingestion và reads đồng thời.
- Đo sau khi buckets đã đủ dữ liệu, cache warm/cold và retention hoạt động.
- Tách throughput, disk bytes/measurement và p95/p99 latency.

## 20. Late arrivals và dữ liệu đến không đúng thứ tự

Một time series không mặc định nhận measurements theo `observedAt` tăng dần. Trong lab:

~~~text
09:00: nhận point observedAt=09:00
09:07: nhận point observedAt=08:45
09:15: nhận point observedAt=09:15
~~~

Đây là **out-of-order ingestion**. MongoDB có thể nhận các measurements như vậy trong giới hạn tính năng, nhưng late arrivals có thể làm tăng nhu cầu mở/tạo buckets, giảm khả năng nén hoặc ảnh hưởng hiệu năng ghi tùy engine/version và độ trễ.

### 20.1. Chọn lateness budget

Ví dụ:

~~~text
Đến trong 2 phút: bình thường
2–60 phút: late nhưng vẫn nhận
Sau 60 phút: gửi vào luồng backfill/reconciliation
Vượt 7 ngày: cần policy riêng
~~~

Đây là **ví dụ business policy**, không phải giới hạn tự động của MongoDB. Chọn theo SLA, retention và loại sensor.

### 20.2. Backfill dữ liệu lịch sử

Nếu nhập dữ liệu cách đây ba năm:

- Lập batch theo khoảng thời gian/metadata.
- Giữ timestamp gốc, không đổi thành giờ import.
- Đo nén và tốc độ insert.
- Kiểm tra retention policy: nếu TTL của collection ngắn hơn tuổi dữ liệu, các measurements cũ có thể sớm bị dọn.
- Không dùng một transaction khổng lồ để nhập toàn bộ dữ liệu lịch sử.

### 20.3. Watermark trong pipeline analytics

Một báo cáo “doanh thu cuối giờ” hoặc “nhiệt độ trung bình giờ trước” có thể không hoàn chỉnh nếu vẫn còn events tới muộn. Có thể:

1. Trễ việc chốt cửa sổ một khoảng lateness budget.
2. Cho phép correction/recompute khi late events xuất hiện.
3. Ghi version của summary.
4. Tách số liệu **provisional** và **finalized**.

MongoDB time series collection chỉ là storage/processing engine; chính sách watermark là trách nhiệm ingestion/analytics.

## 21. Retention và TTL trên time series

Dữ liệu telemetry có thể không cần giữ raw measurements mãi mãi. Ví dụ:

~~~text
Raw 15-minute readings: giữ 30 ngày
Hourly summary:        giữ 2 năm
Daily summary:         giữ 7 năm
~~~

MongoDB hỗ trợ TTL cho time series, thường qua `expireAfterSeconds` ở cấp collection:

~~~javascript
// Ví dụ tạo một time series collection có retention 30 ngày.
db.createCollection("shortLivedReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
})
~~~

`2592000 = 30 × 24 × 60 × 60` giây. Collection này là ví dụ riêng, không thay đổi `sensorReadings` đã tạo.

### 21.1. TTL của time series không xóa đúng từng document vào từng giây

Time series TTL gắn với **thời gian trong buckets**, và dữ liệu trong một bucket có thể chỉ được dọn khi toàn bộ phần liên quan của bucket đã đủ tuổi theo semantics. TTL monitor chạy nền, nên deletion không được bảo đảm ngay tại giây hết hạn.

Ví dụ:

~~~text
Policy: giữ 30 ngày
Một bucket chứa measurements từ 08:00 đến 08:59
=> Không giả định điểm 08:00 biến mất đúng từng giây khi qua 30 ngày
=> Việc dọn bucket phụ thuộc mốc thời gian bucket và TTL monitor
~~~

### 21.2. TTL không phải data security deletion SLA

Nếu có yêu cầu xóa dữ liệu cá nhân **chính xác trong N phút** hoặc “xóa ngay một sensor theo yêu cầu”, TTL time series không tự đáp ứng. Phải thiết kế quy trình purge/rewrite/correction phù hợp với giới hạn của phiên bản, backup retention và quyền truy cập.

### 21.3. TTL và timeField sai

Nếu thiết bị ghi `observedAt` sai năm (quá khứ rất xa), measurement có thể trở thành đối tượng dọn sớm. Nếu timestamp ở tương lai, dữ liệu có thể tồn tại lâu hơn mong muốn. Vì vậy validation thời gian có tác động trực tiếp đến retention.

### 21.4. Downsampling trước khi xóa raw

Khi business cần phân tích dài hạn, có thể:

~~~mermaid
flowchart LR
    Ingest["Raw readings"] --> TS["Time series raw: TTL 30 ngày"]
    TS --> Job["Aggregate mỗi giờ/ngày"]
    Job --> Summary["Hourly/Daily summary collection"]
    Summary --> BI["Dashboard lịch sử"]
~~~

Job cần bảo đảm chỉ publish summary khi cửa sổ đủ ổn định, và có thể recompute khi late events xảy ra. Không để TTL xóa raw trước khi summary cần thiết được tính/đối soát.

## 22. Cập nhật và xóa: điểm khác lớn với regular collection

Regular collection được thiết kế để sửa trạng thái của document:

~~~javascript
db.sensorReadingsRegular.updateOne(
  { _id: someId },
  { $set: { temperatureC: 26.0 } }
)
~~~

Với time series collection, **khả năng update/delete và kiểu filter/update được phép bị giới hạn**, đặc biệt ở những phiên bản cũ. Các hạn chế có thể liên quan đến:

- Field nào được sửa (metaField so với measurement fields).
- Filter phải ràng buộc metaField như thế nào.
- Được phép update một hay nhiều logical measurements.
- Có hỗ trợ upsert không.
- Có thể xóa arbitrary measurement không, và có thể dùng thao tác nào.
- Có được sử dụng trong multi-document transaction không.

Những điều kiện này **thay đổi theo MongoDB version**, nên không viết một API update/delete cho regular collection rồi mặc định áp dụng nguyên vẹn vào time series collection.

### 22.1. Khi thiết kế dữ liệu gần append-only

Trong nhiều hệ thống đo lường, **đừng sửa raw point đã được lưu**. Nếu cần hiệu chỉnh, có thể:

- Lưu correction event riêng gắn `eventId`/time.
- Gắn quality flag hoặc superseding measurement theo policy.
- Tính lại summary từ raw + correction.
- Thiết kế một correction/current-state collection thường để hỗ trợ upsert/unique constraints.

Khi chọn time series, nên chủ động định nghĩa **data correction policy**.

### 22.2. Khi nào regular collection tốt hơn?

Nếu ứng dụng phải:

~~~text
findOneAndUpdate({_id})
upsert liên tục mỗi device
deleteOne theo business ID
unique index tùy ý
transaction cập nhật nhiều entity khác nhau
~~~

thì một regular collection cho phần **mutable state** thường phù hợp hơn. Có thể giữ **history measurements** ở time series và **current device state** ở regular collection, kết nối chúng ở application/service layer.

### 22.3. Không lấy “update hỗ trợ ở phiên bản mới” làm lý do đổi mọi collection

Ngay cả khi phiên bản mới mở rộng hỗ trợ update/delete cho time series, storage và query design vẫn tối ưu cho time-ordered measurements, không phải mọi CRUD-heavy workload. Cần xem tỷ lệ update/insert, query patterns, indexes, workload latency và giới hạn chính xác theo server version.

## 23. So sánh trực diện: time series và collection thông thường

| Khía cạnh | Time series collection | Regular collection |
|---|---|---|
| Dữ liệu điển hình | Measurements/events có timestamp | Entity, business record, document bất kỳ |
| Hướng ghi | Thường append-heavy, ít sửa raw history | Insert/update/delete linh hoạt |
| Tạo collection | `timeseries:{timeField,metaField,granularity}` | `createCollection()` thông thường |
| Metadata | `metaField` giúp nhóm measurements | Field bất kỳ không mang nghĩa bucket đặc biệt |
| Storage | Buckets nội bộ với tối ưu nén time series | Document storage thông thường, có compression riêng |
| Truy vấn thường gặp | Metadata + time range, rollup/window | ID lookup, joins, state updates, tùy pattern |
| Index | Index theo time/meta hỗ trợ nhưng có giới hạn theo phiên bản | Bộ tính năng index rộng hơn |
| Unique constraints | Hạn chế đáng kể | Có unique indexes mạnh và linh hoạt |
| Cập nhật từng record | Có ràng buộc/khả năng phụ thuộc phiên bản | Hỗ trợ đa dạng update operators |
| Xóa từng record | Cần xét time series restrictions | `deleteOne`/`deleteMany` thông thường |
| TTL | Có cơ chế retention theo thời gian/buckets | TTL index theo field Date có semantics regular |
| Transaction | Hạn chế đối với time series, nhất là ghi | Hỗ trợ transaction khi topology đủ điều kiện |
| Schema evolution | Nên giữ cấu trúc measurement ổn định để nén tốt | Linh hoạt cho document model |
| Dữ liệu đến muộn | Có thể ingest nhưng có tradeoffs về buckets | Không có tổ chức bucket time series |
| “Latest value” lookup | Có thể sort/time index, nhưng cần đo chi phí nhiều series | Current-state doc/upsert thường thuận tiện |
| Compression benefit | Thường tốt với repeated schema/metadata | Tùy compressor và schema, không bị giới hạn một loại dữ liệu |
| Tối ưu query | Có thể prune/unpack buckets và tối ưu pipeline đặc thù | Index planner theo document thông thường |
| Phù hợp nhất | Telemetry, metrics, sensor history, event measurements | Orders, customer profile, mutable inventory, transaction ledger |

**Không có lựa chọn tốt tuyệt đối.** Một thiết kế tối ưu thường dùng cả hai loại để mỗi loại phục vụ đúng vai trò.

## 24. Bài toán mẫu 1: cảm biến tòa nhà

Yêu cầu:

- 20.000 sensors.
- Mỗi sensor gửi 1 measurement mỗi 15 giây.
- Dashboard cần nhiệt độ hiện tại và biểu đồ 24 giờ.
- Cần raw 30 ngày, hourly summary 2 năm.

### 24.1. Tốc độ ghi ước lượng

~~~text
20.000 sensors × (60 / 15) measurements/phút
= 80.000 measurements/phút
≈ 1.333 measurements/giây, nếu gửi đều
~~~

Đây là **throughput trung bình**, không bao gồm bursts khi nhiều thiết bị reconnect cùng lúc. Hệ thống cần test peak ingestion, không chỉ average.

### 24.2. Kiến trúc dữ liệu

~~~mermaid
flowchart LR
    Devices["20.000 sensors"] --> Queue["Ingestion API/queue"]
    Queue --> Validate["Validate timestamp/meta/value"]
    Validate --> Raw["Time series raw"]
    Validate --> Latest["Regular sensorLatest"]
    Raw --> Rollup["Hourly aggregate"]
    Rollup --> Hist["Summary history"]
    Raw --> Graph["24h chart"]
    Latest --> Live["Current state"]
~~~

### 24.3. Vì sao cần hai collection?

**Time series raw**:

- Ghi append measurements.
- Truy vấn time range.
- Nén dữ liệu.
- TTL 30 ngày.

**Regular sensorLatest**:

- Một document mỗi sensor.
- Upsert/update trạng thái gần nhất.
- Có unique business identity.
- Dễ phục vụ API dashboard đọc point lookup.

Khi late measurement đến, update `sensorLatest` phải có **conditional comparison** để không hạ timestamp hiện tại:

~~~javascript
// Mẫu ý tưởng ở regular collection.
db.sensorLatest.updateOne(
  {
    _id: "t-01:sensor-01",
    observedAt: { $lt: ISODate("2026-10-01T09:15:00Z") }
  },
  {
    $set: {
      observedAt: ISODate("2026-10-01T09:15:00Z"),
      temperatureC: 26.4
    }
  }
)
~~~

Đây chỉ là **nhánh update khi current-state doc đã tồn tại**. Nếu cần upsert record mới, phải thiết kế riêng để tránh race khi chưa có document và bảo đảm unique key. Không coi một `updateOne` có `observedAt:$lt` như mẫu upsert hoàn chỉnh.

## 25. Bài toán mẫu 2: metrics API

Ví dụ measurement:

~~~javascript
{
  observedAt: ISODate("2026-10-01T09:00:00Z"),
  meta: {
    service: "checkout",
    environment: "production",
    region: "asia"
  },
  latencyMs: 42,
  statusCode: 200
}
~~~

Cần tính:

- Requests/sec hoặc requests/minute.
- Average/max latency.
- Error rate.
- P95/P99 latency.

### 25.1. Cardinality explosion trong metadata

Không nên đặt vào meta:

~~~javascript
meta: {
  service: "checkout",
  requestId: "unique-per-http-request",
  userId: "unique-high-cardinality-user"
}
~~~

vì requestId thay đổi từng event, dễ làm bucket grouping bị phân mảnh. Có thể giữ `requestId` là measurement field nếu cần trace/debug với retention ngắn và giới hạn privacy. Tên route/path phải được chuẩn hóa: thay `/orders/123` và `/orders/456` bằng route pattern `/orders/:id` nếu mục tiêu là metrics per endpoint.

### 25.2. Percentile không phải average

Trung bình 42 ms không cho biết p99. Có thể dùng các toán tử thống kê được server version hỗ trợ (ví dụ các percentile operators trên phiên bản hiện đại) hoặc một hệ thống metrics chuyên dụng. Phải xem xét tradeoff của việc giữ raw request events cho thống kê chính xác so với histogram/aggregate với quy ước error.

### 25.3. Alerting cần độ trễ thấp

Time series lưu history tốt, nhưng nếu alert cần phản ứng trong 2 giây, có thể tính streaming counters ngay trên đường ingestion/queue, thay vì scan hàng triệu raw records cho mỗi điều kiện alert.

## 26. Bài toán mẫu 3: log/events và ranh giới time series

Application logs có timestamp, hostname, severity, message. Vậy có nên dùng time series collection không?

Phụ thuộc workload:

**Phù hợp hơn khi**:

- Logs có schema gần đồng nhất.
- Query chủ yếu theo host/service + time range.
- Ít sửa document, retention rõ.
- Không cần nhiều loại index/full-text search trên nội dung log.

**Cân nhắc regular collection hoặc search/log platform khi**:

- Cần full-text search mạnh, phân tích log bán cấu trúc rất đa dạng.
- Cần update/delete/retention per event ngoài hạn chế time series.
- Cần unique constraints, transactional business events.
- Cần truy vấn theo nhiều dimensions không nằm trong metadata.

Đừng đưa mọi log JSON vào time series chỉ vì chúng có `timestamp`. Hãy xác định access patterns, index support và nhu cầu tìm kiếm.

## 27. Chọn granularity dựa trên tần suất đo và query

Một bảng định hướng:

| Tần suất | Lựa chọn thử nghiệm | Điểm cần đo |
|---|---|---|
| Vài lần/giây | `seconds` | Bucket efficiency, peak write rate |
| Mỗi 15 giây | `seconds` | Tần suất ổn định, late arrivals |
| Mỗi 5 phút | `minutes` | Bucket span, query ranges |
| Mỗi giờ | `hours` | Bucket overhead và retention |
| Sự kiện thưa, không đều | Cần benchmark trước | Nếu mỗi series ít điểm, bucket overhead có thể cao |

### 27.1. Tại sao granularity không phải độ phân giải biểu đồ?

Một collection tạo với `granularity:"seconds"` vẫn có thể tính trung bình mỗi giờ. Tương tự, collection `granularity:"hours"` vẫn nhận phép đo ở `08:13:42`. Granularity mô tả cách engine **bucket** dữ liệu, còn độ phân giải biểu đồ là quyết định của `$dateTrunc`/`$group` và giao diện.

### 27.2. Thay đổi granularity

MongoDB cho phép một số thay đổi về granularity/bucket settings theo quy tắc phiên bản, nhưng không nên giả định có thể giảm/tăng mọi tham số tùy ý sau khi dữ liệu đã được lưu. Những thay đổi lớn có thể cần tạo collection mới và migrate. Hãy kiểm tra `collMod`/tùy chọn được hỗ trợ cho phiên bản trước khi lập kế hoạch.

### 27.3. Khi dùng bucket custom

Nếu workload rất đặc thù, custom `bucketMaxSpanSeconds`/`bucketRoundingSeconds` có thể giúp điều chỉnh bucket window. Nhưng cần:

- Chọn theo time distribution thực.
- Tính cả late/out-of-order measurements.
- Kiểm tra giới hạn giá trị.
- Đo compression ratio và read latency.
- Có phương án migration nếu cấu hình sai.

Đừng tối ưu buckets chỉ bằng trực giác.

## 28. Time series và sharding

Khi dữ liệu lớn hơn khả năng một replica set, có thể cân nhắc **sharding time series collection** trên phiên bản hỗ trợ (MongoDB 5.1+ với các cải tiến/hạn chế theo version).

### 28.1. Câu hỏi thiết kế shard key

- Query thường theo `tenantId + sensorId + observedAt`?
- Có một số sensors/tenants nóng hơn hẳn không?
- Một tenant lớn có nên trải nhiều shards?
- Dữ liệu mới đến có dồn vào một range thời gian/hot shard không?
- Shard key có phù hợp những hạn chế của time series trên phiên bản hiện hành không?

Không đặt timeField tăng dần làm khóa theo cách gây mọi insert mới dồn vào một shard chỉ vì “time series thì phải shard theo time”. Quy tắc shard key hợp lệ cho time series và việc có thể dùng hashed/meta/time fields phụ thuộc phiên bản; thiết kế và kiểm tra riêng.

### 28.2. Sharding không làm mọi aggregation nhanh

Một query per-sensor có thể được target tốt nếu shard key hỗ trợ, nhưng query “max nhiệt độ của tất cả sensors trong một năm” vẫn cần aggregate phân tán và global merge. Lượng dữ liệu/time range, index và bytes transferred vẫn quyết định hiệu năng.

### 28.3. Shard key vs metadata grouping

`metaField` dùng cho bucket grouping; **shard key** quyết định data placement giữa shards. Có liên hệ nhưng không đồng nhất. Không suy ra cùng `meta.sensorId` nghĩa là dữ liệu chắc chắn nằm trên một shard trong mọi thiết kế.

## 29. Replica set/read preference cho time series

Một workload telemetry có thể:

- Ghi vào primary của replica set.
- Đọc dashboard lịch sử từ secondary khi chấp nhận replication lag.
- Đọc current-state ngay sau write từ primary nếu yêu cầu read-your-writes.

Nhưng nếu secondary đang chạy aggregate nặng, CPU/disk cạnh tranh với replication apply và có thể tăng lag. Read preference secondary **không đảm bảo dữ liệu mới nhất**, và việc chuyển query sang secondary không thay đổi số lượng raw measurements phải scan.

### 29.1. Dữ liệu đến trễ + replication lag

Có hai độ trễ riêng:

~~~text
Thiết bị đo -> ingestion service: 5 phút trễ
Primary -> secondary:          10 giây trễ
~~~

Dashboard đọc secondary có thể chậm hơn so với event time do **cả hai lớp**. Không dùng một metric `replicationLag` duy nhất để giải thích toàn bộ end-to-end data freshness.

### 29.2. Read concern

`readConcern:"majority"` nói tới mức committed data được quan sát theo semantics của MongoDB, nhưng secondary vẫn có thể chưa áp dụng write mới nhất. Nếu dashboard cần “đọc ngay sau ghi”, cần đọc primary hoặc một cơ chế causal consistency thích hợp, không chỉ đặt majority.

## 30. Retention, schema và tính tuân thủ

Trước khi bật TTL:

1. Xác định loại dữ liệu và thời gian lưu tối thiểu theo hợp đồng/pháp lý.
2. Tách raw và summary nếu cần giữ xu hướng lâu hơn raw.
3. Xác định data access policies theo tenant.
4. Kiểm tra timestamps trong quá khứ/tương lai.
5. Thiết lập monitoring TTL/storage.
6. Xác định quy trình xóa dữ liệu theo yêu cầu ngoài TTL.
7. Tính cả retention của backups, logs và downstream analytics stores.

### 30.1. Dữ liệu cá nhân trong metaField

Không nên đặt email, số điện thoại hay dữ liệu nhạy cảm trực tiếp vào metaField nếu không thật sự cần. Meta thường lặp/được dùng cho index/routing, làm tăng phạm vi xuất hiện của PII. Ưu tiên ID ổn định ít nhạy cảm, kiểm soát truy cập và lưu metadata chi tiết trong regular collection riêng nếu cần.

### 30.2. Schema evolution

Sensor firmware mới có thể đổi field:

~~~text
temperatureC -> temp_c
humidityPct -> relativeHumidity
~~~

Nếu không chuẩn hóa, aggregation `$avg:"$temperatureC"` sẽ bỏ qua những document chỉ có `temp_c` hoặc tính thiếu dữ liệu. Có thể:

- Chuẩn hóa tại ingestion.
- Lưu `schemaVersion`.
- Dùng aggregation thích nghi có kiểm soát.
- Chạy backfill/migration khi cần.

Ưu tiên schema đo lường ổn định để query và compression predictable.

### 30.3. Đơn vị đo

Không ghi cùng field `temperature` chứa lẫn Celsius và Fahrenheit mà không lưu unit/convert. Tốt hơn, chọn một đơn vị chuẩn (ví dụ °C) ở storage, sau đó đổi đơn vị ở UI khi cần.

## 31. So sánh ingest vào hai loại collection

Để đánh giá hiệu năng thật, cần đo:

~~~text
Số measurements/giây
Average và p95 insert latency
CPU/I/O/cache của MongoDB
Total collection bytes
Index bytes
Tỷ lệ nén thực
Lag khi ghi bursts
p95 time-range query
Ảnh hưởng late arrivals
Chi phí TTL và dữ liệu bị dọn
~~~

### 31.1. Benchmark công bằng

Khi so regular và time series:

- Ghi cùng nội dung measurements với kiểu field giống nhau.
- Chọn indexes **phù hợp cho từng loại**, không ép cùng một index thiếu tối ưu.
- Tách disk usage của data và indexes.
- Test cả insert đều đặn và dữ liệu đến muộn.
- Dùng số lượng series và điểm/series đại diện.
- Chạy nhiều vòng; đo cache warm/cold.
- Theo dõi concurrent reads.
- Test query raw range, group hourly, latest measurement riêng.

### 31.2. Không dùng document count để suy ra disk savings

Ứng dụng vẫn đọc 100 triệu logical measurements dù engine lưu trong ít hơn rất nhiều internal bucket documents. So sánh số internal documents giữa hai loại collection **không có nghĩa** compression ratio bằng tỉ lệ document count.

### 31.3. Chi phí indexes

Time series có thể tiết kiệm storage của raw measurements nhưng nếu tạo quá nhiều secondary indexes, index bytes và write amplification vẫn tăng. Index design phải phục vụ workload đọc quan trọng, không phải “cứ index tất cả metadata fields”.

## 32. Migration từ regular collection sang time series

Nếu hệ thống đã có `sensorReadingsRegular`, không nên coi việc bật `timeseries` trên một collection hiện hữu là một thao tác đổi nhãn đơn giản. Một quy trình thường là **tạo collection time series mới và copy dữ liệu**.

### 32.1. Quy trình mẫu

1. Đo số documents, indexes, schema variants và queries đang chạy.
2. Chuẩn hóa `observedAt` thành BSON Date, sửa những điểm lỗi/unknown time.
3. Xác định `metaField` và `granularity`.
4. Tạo time series collection mới với cấu hình được hỗ trợ.
5. Nhập dữ liệu theo batch, theo event time/metadata khi hữu ích.
6. Kiểm tra count, sample min/max, tổng hợp và chính sách dedupe.
7. Chạy shadow queries so kết quả logic giữa old/new.
8. Xác định cách xử lý writes trong giai đoạn chuyển (dual-write, queue replay, cutoff).
9. Chuyển read traffic theo feature flag.
10. Giữ rollback window/backup rồi mới gỡ collection cũ.

### 32.2. Không dựa vào dual-write vô điều kiện

~~~text
Ứng dụng insert regular thành công
Time series insert bị timeout
=> Hai nguồn lệch nhau
~~~

Nếu cần dual-write, phải có cơ chế retry/reconciliation và stable event ID, không chỉ gọi hai `insertOne()` rồi tin rằng chúng luôn cùng thành công.

### 32.3. Copy bằng batch

Ví dụ ý tưởng (giả mã):

~~~javascript
// Pseudocode: không chạy toàn bộ collection lớn trong một vòng lặp vô hạn.
for await (const batch of readRegularByRangeWithCheckpoint()) {
  const normalized = batch.map(normalizeMeasurement)
  await writeTimeSeriesBatch(normalized)
  await storeCheckpointAfterSuccessfulWrite()
}
~~~

Chọn batch size và checkpoint theo throughput/memory/timeout; xác định duplicate handling khi retry. Không dùng một multi-document transaction khổng lồ để migrate toàn bộ lịch sử.

### 32.4. Cutover và kết quả thống kê

Vì late measurements có thể xuất hiện sau cutoff, cần policy nhận dữ liệu cũ và recompute rollups. Một bản “migrated” không tự đồng nghĩa tất cả late arrivals đã được xử lý.

## 33. Vận hành và giám sát production

Một hệ thống time series tốt cần quan sát cả database và đường ingestion.

### 33.1. Metric quan trọng

| Nhóm | Metric | Tại sao cần? |
|---|---|---|
| Ingestion | Measurements/sec, burst rate | Nhu cầu ghi và khả năng chịu tải |
| Freshness | Event-to-ingest delay p95/p99 | Độ trễ dữ liệu tại nguồn |
| Replication | Lag theo member | Độ trễ đọc secondary |
| Quality | Invalid timestamp, bad unit, null/outlier rate | Độ tin cậy dữ liệu |
| Dedupe | Duplicate event IDs, replay attempts | Tránh cộng hai lần |
| Storage | Data/index bytes, bytes/measurement | Kiểm soát chi phí |
| Buckets | Bucket count/fill/compression nếu khả dụng | Phát hiện metadata cardinality sai |
| Query | p95/p99 per-sensor range query | SLO biểu đồ |
| Aggregation | Hourly rollup latency, spill | Báo cáo có bị bottleneck? |
| Retention | Oldest event, TTL progress, backlog | Raw đã được dọn theo policy chưa? |
| Resource | CPU/disk/cache/network | Tránh ingestion làm nghẽn reads |
| App | Dashboard stale age, missing coverage | Chất lượng dữ liệu người dùng nhìn thấy |

Các tên metric là **gợi ý instrumentation**, không phải MongoDB luôn có sẵn đúng tên như bảng.

### 33.2. Theo dõi sensor không gửi dữ liệu

Nếu mục tiêu “sensor im lặng 30 phút”, cách làm không chỉ là tìm measurements trong 30 phút và tin rằng sensor có/không có:

- Cần một regular `devices` registry để biết **sensor nào đang hoạt động**.
- Dùng current-state/lastSeen để tìm sensor không có measurement mới.
- Phân biệt sensor đã tạm dừng bảo trì với sensor gặp sự cố.

Một time series raw collection không tự cung cấp danh sách sensors **đáng lẽ phải gửi** nhưng chưa từng gửi.

### 33.3. Operational alarms

Nên cảnh báo khi:

- Ingestion backlog tăng.
- p99 event-to-ingest delay vượt SLO.
- Tỷ lệ invalid timestamps tăng sau firmware deploy.
- Dung lượng/index tăng bất thường.
- Bucket compression kém đi khi metadata schema đổi.
- TTL không theo kịp tốc độ ghi hoặc dọn quá nhiều dữ liệu do timestamp sai.
- Rollup job thất bại/summary kém cập nhật.
- Query p95/p99 tăng khi thêm sensor mới.

### 33.4. Backup và khôi phục

TTL không thay backup; backup không thay archival/retention. Cần xác định:

- Backup snapshots và khả năng phục hồi thời điểm.
- Bao gồm các collections raw, summary, device registry, dedupe ledger.
- Chính sách retention của backup phù hợp compliance.
- Restore có phục hồi consistency giữa raw/summary/ledger hay phải reconcile.
- Với sharded cluster, dùng backup strategy biết sharding/metadata.

## 34. Thực hành 1: xác định loại collection

Phân loại năm tình huống:

1. Mỗi thiết bị gửi nhiệt độ mỗi phút, chỉ đọc history theo time range.
2. Một customer profile liên tục đổi tên/địa chỉ.
3. Mỗi giao dịch thanh toán có orderId duy nhất, cần cập nhật trạng thái và bảo đảm transaction.
4. Mỗi máy chủ gửi CPU usage mỗi 10 giây, cần rollup giờ.
5. Mỗi sensor có **một current-state document** được update mỗi phút.

Giải thích vì sao 1 và 4 là ứng viên time series, còn 2, 3 và 5 thường hợp regular collection hơn.

## 35. Thực hành 2: tạo và chèn measurements

Tạo một time series collection khác:

~~~javascript
db.createCollection("powerReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

db.powerReadings.insertMany([
  {
    measuredAt: ISODate("2026-10-02T08:00:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.50")
  },
  {
    measuredAt: ISODate("2026-10-02T08:15:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.65")
  },
  {
    measuredAt: ISODate("2026-10-02T08:30:00Z"),
    meta: { tenantId: "t-01", meterId: "meter-01" },
    kwh: NumberDecimal("0.55")
  }
])
~~~

Lưu ý `kwh` là **điện tiêu thụ trong khoảng 15 phút**, không phải chỉ số công tơ cộng dồn. Vì thế tổng ba điểm là `1.70 kWh`. Nếu field là cumulative meter reading, cách tính điện tiêu thụ của khoảng thời gian phải dựa trên **chênh lệch giữa hai lần đọc**, không cộng tất cả readings.

## 36. Thực hành 3: truy vấn theo time range

Dùng `sensorReadings` lab và viết query:

- Lấy sensor-02 từ 08:15 đến trước 09:00.
- Chỉ trả `observedAt, temperatureC`.
- Sort tăng dần theo thời gian.

Kết quả nhiệt độ mong đợi: **24.2, 24.4, 24.6°C**.

## 37. Thực hành 4: hourly rollup

Viết pipeline tính:

~~~text
sensorId
hour (UTC)
measurements
avgTemperatureC
minTemperatureC
maxTemperatureC
~~~

cho dữ liệu t-01 ngày 2026-10-01 trong hai giờ 08 và 09. Gợi ý dùng `$dateTrunc` và `$group`. So sánh kết quả sensor-01 với mục 13.

## 38. Thực hành 5: latest measurement và late arrival

Thực hiện hai query:

~~~javascript
db.sensorReadings.find(
  { "meta.sensorId": "sensor-01" }
).sort({ observedAt: -1 }).limit(1)

db.sensorReadings.find(
  { "meta.sensorId": "sensor-01" }
).sort({ receivedAt: -1 }).limit(1)
~~~

Trên bộ lab hiện tại cả hai có thể cùng trả điểm 09:15. Hãy mô tả trường hợp một packet `observedAt=08:30` nhưng `receivedAt=12:00` được ingest thêm: **latest observed** và **latest received** sẽ khác nhau thế nào?

## 39. Thực hành 6: metadata thiết kế sai

Một đội phát triển đặt:

~~~javascript
meta: {
  sensorId: "sensor-01",
  requestId: "random-uuid-every-point"
}
~~~

Giải thích hậu quả đối với bucket grouping và compression. Hãy đề xuất schema sửa lại mà vẫn giữ được requestId để truy vết.

## 40. Thực hành 7: TTL

Thiết kế retention:

~~~text
Raw: 14 ngày
Hourly summary: 2 năm
Daily summary: 5 năm
~~~

Xác định các collections cần có, lựa chọn TTL và chính sách late-arrival. Giải thích vì sao không được hứa rằng một measurement sẽ bị xóa đúng từng giây sau 14 ngày.

## 41. Thực hành 8: dedupe

Một sensor gửi cùng packet hai lần vì retry sau timeout:

~~~text
eventId = E123
sensorId = sensor-01
observedAt = 08:15
temperatureC = 25.4
~~~

Đề xuất một cơ chế stable ID/dedupe bên ngoài time series và cách phát hiện fingerprint khác khi cùng eventId. Tại sao không thể dùng một unique compound index tùy ý như regular collection mà chưa xác nhận version support?

## 42. Thực hành 9: explain và benchmark

Chạy:

~~~javascript
db.sensorReadings.explain("executionStats").find({
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})

db.sensorReadingsRegular.explain("executionStats").find({
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:00:00Z"),
    $lt: ISODate("2026-10-01T10:00:00Z")
  }
})
~~~

Ghi nhận plans và số liệu **thực sự xuất hiện**. Vì sao không thể khẳng định time series nhanh hơn chỉ dựa trên 18 measurements hoặc so `docsExamined` mà không hiểu bucket vs logical docs?

## 43. Thực hành 10: thiết kế kiến trúc hoàn chỉnh

Hệ thống có 50.000 sensors, mỗi sensor gửi điểm 30 giây/lần, giữ raw 60 ngày, dashboard live và daily reporting 3 năm.

Hãy đề xuất:

- Time series raw schema.
- MetaField và timeField.
- Index/query chính.
- Regular current-state collection.
- Raw TTL và summary retention.
- Dedupe packet ID.
- Quality/late event policy.
- Downsampling và dashboard API.
- Metrics cần giám sát.

Giải thích vì sao không thể chỉ tạo một time series collection rồi giải quyết mọi nhu cầu bằng `find().sort().limit(1)` và query raw history không giới hạn.

## 44. Gợi ý đáp án thực hành

### Bài 1

1 và 4 là time series workloads: measurements append theo thời gian, đọc time windows và tổng hợp. 2, 3 là mutable entities cần CRUD/constraints/transactions. 5 có thể dùng regular current-state collection, đồng thời ghi raw history vào time series nếu cần.

### Bài 2

Nếu `kwh` là lượng tiêu thụ của từng interval, tổng = `0.50 + 0.65 + 0.55 = 1.70 kWh`. Nếu chỉ số công tơ cộng dồn, phải lấy chênh lệch.

### Bài 3

Filter:

~~~javascript
{
  "meta.sensorId": "sensor-02",
  observedAt: {
    $gte: ISODate("2026-10-01T08:15:00Z"),
    $lt: ISODate("2026-10-01T09:00:00Z")
  }
}
~~~

Projection `{_id:0,observedAt:1,temperatureC:1}` và sort `{observedAt:1}` trả 24.2, 24.4, 24.6.

### Bài 4

Nhóm theo `$dateTrunc:{date:"$observedAt",unit:"hour",timezone:"UTC"}` và `$meta.sensorId`. Sensor-01: 08h average 25.75, 09h average 26.7, tương ứng 4 và 2 measurements.

### Bài 5

Late packet nhận lúc 12:00 với `observedAt=08:30` không phải latest observed nếu đã có điểm 09:15. Nhưng có thể trở thành latest received; API phải ghi rõ đang hiển thị thông tin nào.

### Bài 6

`requestId` unique mỗi point làm meta cardinality thay đổi mỗi lần, tạo nhiều buckets ít điểm và giảm hiệu quả nén. Giữ `meta:{sensorId:"sensor-01"}`, đặt `eventId`/`requestId` thành field measurement thông thường.

### Bài 7

Raw time series có TTL 14 ngày, summary collections có retention riêng 2/5 năm. TTL xóa dữ liệu theo bucket/monitor nền, không tức thời từng measurement. Late events cần watermark/correction trước khi raw bị dọn.

### Bài 8

Stable eventId, fingerprint của canonical payload và một lớp dedupe bền vững (queue state/regular unique ledger). Cần thiết kế crash recovery, không mặc định two-collection writes là atomic trên mọi phiên bản.

### Bài 9

Kết quả explain thực thay đổi theo plan/version; có thể thấy index/bucket pruning/unpack stages. Dataset nhỏ không đủ kết luận throughput/storage savings.

### Bài 10

50.000 sensors × 2 measurements/phút = 100.000/min ≈ 1.667/sec trung bình, chưa kể bursts. Time series raw với meta nguồn ổn định, TTL 60 ngày; regular latest state cho live dashboard; summary hourly/daily cho 3 năm, quality/dedupe/out-of-order policy, indexes theo sensor/time và ingest/replication/query metrics.

## 45. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Hướng xử lý |
|---|---|---|
| Thấy `createdAt` là chọn time series | Business entity có thể cần CRUD/transaction | Đánh giá access pattern và độ mutable |
| Đặt receivedAt thay event time | Biểu đồ và cửa sổ thời gian sai | Phân biệt observedAt/receivedAt |
| Lưu timestamp dạng string | Không đúng yêu cầu BSON Date cho timeField | Parse/validate thành Date |
| Đưa eventId random vào meta | Buckets phân mảnh, nén kém | Metadata ổn định, eventId là field đo |
| Dùng mỗi buildingId làm meta khi query theo sensor | Bucket lẫn nhiều series | Chọn identity theo query workload |
| Tin granularity tự tổng hợp mỗi giờ | Storage bucket không phải hourly summary | Dùng `$dateTrunc + $group` |
| Query thẳng `system.buckets` | Phụ thuộc internals, rủi ro hỏng dữ liệu | Query logical collection |
| Cho rằng time series luôn nén 90% | Phụ thuộc schema/series density | Benchmark trên dữ liệu thật |
| Copy toàn bộ index regular sang time series | Có index options/restrictions khác nhau | Kiểm tra hỗ trợ và explain |
| Tin unique business measurement tự được enforce | Duplicate do retry | Dedupe với identity ổn định và constraint phù hợp |
| Dùng time series cho mutable current state | Update/upsert restrictions, query không hợp | Regular current-state collection |
| Sửa/xóa raw điểm tùy ý | Time series có hạn chế version-specific | Policy correction riêng |
| TTL có nghĩa xóa chính xác từng document tức thời | TTL hoạt động theo buckets/monitor | Retention SLA và kiểm tra phù hợp |
| Không validate time quá khứ/tương lai | Dữ liệu bị dọn sớm hoặc giữ quá lâu | Timestamp validation |
| Coi missing measurement bằng 0 | Biểu đồ và average sai | Gap/imputation policy |
| Nội suy mà không gắn cờ | Giá trị estimated bị hiểu là đo thật | Lưu/hiển thị provenance |
| Chạy `$densify` với cửa sổ nhiều năm bước 1 giây | Số result phình cực lớn | Bound thời gian và độ phân giải |
| Tính latest theo receivedAt khi cần observedAt | Late packet ghi đè current state | So sánh event time |
| Lấy toàn bộ raw history cho chart | Tốn network/CPU/memory | Downsample/rollup |
| Chỉ đo docsExamined giữa hai storage types | Bucket docs và logical docs khác nghĩa | Đo latency, bytes và plan |
| Chọn hashed key chỉ vì dữ liệu là time series | Có thể hot shard/scatter query | Shard key theo workload |
| Đọc secondary và nghĩ luôn thấy write ngay | Replication lag | Primary/causal consistency khi cần |
| Dual-write hai collections mà không reconciliation | Dữ liệu lệch khi một ghi lỗi | Queue/checkpoint/stable eventId |

## 46. Câu hỏi ôn tập

**1. Time series collection giải quyết bài toán gì?**

Tối ưu lưu trữ và xử lý một lượng lớn measurements/events gắn timestamp, thường ghi nối tiếp và truy vấn theo metadata + khoảng thời gian.

**2. TimeField khác metaField thế nào?**

TimeField chứa BSON Date của measurement. MetaField mô tả nguồn/series và giúp tổ chức buckets theo metadata.

**3. MetaField có bắt buộc không?**

Không. Nhưng với dữ liệu nhiều series, thiết kế metaField phù hợp thường giúp query/filter và bucket organization.

**4. Vì sao không đặt requestId mới mỗi lần gửi trong metaField?**

Nó làm metadata thay đổi liên tục, phân mảnh bucket grouping và có thể giảm compression.

**5. High cardinality sensorId có luôn xấu không?**

Không. Nếu mỗi sensor có nhiều measurements, sensorId vẫn là series identity hợp lý. Quan trọng là số điểm mỗi series, cách phân bố và bucket fill.

**6. Granularity="minutes" có nghĩa chỉ được insert timestamp tròn phút?**

Không. Nó là cấu hình giúp engine tổ chức bucket theo đặc điểm nhịp đo; không ép timestamp tròn phút.

**7. Time series có phải một regular collection cộng index theo observedAt?**

Không. Time series dùng storage bucket/compression và tối ưu query riêng, có các giới hạn indexing/update/delete khác.

**8. MongoDB có tự tạo hourly summaries khi dùng time series không?**

Không. Dùng `$dateTrunc`/`$group`, window operators hoặc materialized rollup jobs.

**9. Một phép đo có thể đến muộn không?**

Có. Event time và received time khác nhau. Cần lateness policy và benchmark tác động lên bucket efficiency.

**10. TTL trên time series có xóa từng measurement đúng giây hết hạn không?**

Không. Nó liên quan bucket expiration và TTL monitor chạy nền, nên có độ trễ và granularity của bucket.

**11. Time series có phù hợp giữ customer profile không?**

Thường không nếu profile phải update/unique/index/transaction thường xuyên. Regular collection hợp lý hơn.

**12. Lấy điểm gần nhất nên sort theo field nào?**

Theo `observedAt` nếu cần measurement mới nhất về mặt thời gian quan sát; theo `receivedAt` nếu cần packet được hệ thống nhận gần nhất.

**13. Vì sao index theo meta + time hữu ích?**

Nó giúp thu hẹp series và cửa sổ, có thể tăng hiệu quả bucket selection/access path khi query phù hợp.

**14. Vì sao docsExamined không luôn so sánh trực tiếp giữa regular và time series?**

Vì ở time series storage engine có bucket documents, còn application xem logical measurements. Phải hiểu explain path.

**15. `$densify` và `$fill` làm gì?**

`$densify` tạo các mốc còn thiếu trong pipeline; `$fill` điền giá trị theo chính sách. Các giá trị điền không tự trở thành phép đo thực.

**16. Vì sao time series không tự đảm bảo exactly-once measurement?**

Retry ở tầng mạng có thể gửi lại cùng packet. Cần stable event ID và cơ chế dedupe/constraint phù hợp; unique indexing của time series khác regular.

**17. Có nên shard time series theo timestamp tăng dần không?**

Không mặc định. Cần xem hot range, query targeting, meta cardinality và quy tắc shard key của phiên bản.

**18. Đọc từ secondary có làm dữ liệu mới hơn không?**

Không. Replication bất đồng bộ nên secondary có thể stale; read concern/causal consistency phải được chọn theo yêu cầu.

**19. Có cần current-state collection riêng không?**

Không phải luôn, nhưng có thể rất hữu ích cho dashboard latest value hoặc mutable device state với nhiều point lookups.

**20. Khi nào time series có thể tệ hơn regular collection?**

Khi dữ liệu sparse ít điểm/meta, schema không đều, metadata đổi mỗi record, query theo unique business ID, cần update/delete/transaction linh hoạt hoặc index patterns không được hỗ trợ.

## 47. Bảng ghi nhớ nhanh

| Mục tiêu | Kỹ thuật |
|---|---|
| Tạo time series | `db.createCollection("x",{timeseries:{timeField:"observedAt",metaField:"meta",granularity:"minutes"}})` |
| Lọc sensor + time range | `{"meta.sensorId":"s-01",observedAt:{$gte:start,$lt:end}}` |
| Lấy latest observed | `sort({observedAt:-1}).limit(1)` |
| Nhóm theo giờ | `$dateTrunc + $group` |
| Rolling average | `$setWindowFields` |
| Sinh mốc thiếu | `$densify` |
| Điền missing values | `$fill` |
| Giới hạn retention | `expireAfterSeconds` khi tạo/cấu hình theo phiên bản |
| Xem index | `getIndexes()` |
| Xem plan | `explain("executionStats")` |
| Xem storage | `stats()` / `collStats` |
| Giữ live state | Regular `sensorLatest` collection |
| Dedupe event | Stable eventId + ledger/stream consumer |
| Lưu lịch sử lâu | Hourly/daily rollups |
| Late event | Event time + received time + watermark/recompute |
| Tối ưu storage | Meta ổn định, granularity đúng, benchmark buckets |
| Dataset rất lớn | Xem sharding, query targeting, analytics summary |

## 48. Checklist thiết kế trước khi triển khai

- [ ] Mỗi document là một measurement/event gắn timestamp, chứ không phải mutable business entity?
- [ ] Đã xác định đúng **event time** và **ingestion time**?
- [ ] TimeField là BSON Date, timestamp được chuẩn hóa về UTC?
- [ ] Có validate timestamp lệch quá khứ/tương lai và timezone?
- [ ] MetaField mang các thuộc tính ổn định xác định series?
- [ ] Không đưa unique requestId/receivedAt biến đổi mỗi record vào meta?
- [ ] Đã đánh giá cardinality và số measurements/meta value?
- [ ] Granularity/bucket options được chọn theo nhịp ghi thực?
- [ ] Query chính theo meta + time range đã có index/query plan phù hợp?
- [ ] Có chính sách dedupe cho duplicate measurements do retry?
- [ ] Có phân biệt latest observed với latest received?
- [ ] Retention TTL có tính tới bucket-level expiration và độ trễ monitor?
- [ ] Cần xóa riêng từng measurement có tương thích giới hạn phiên bản không?
- [ ] Có yêu cầu update/upsert/unique/transaction khiến regular phù hợp hơn không?
- [ ] Dashboard có giới hạn time range/points và dùng rollup khi cần?
- [ ] `$densify/$fill` có policy imputation, không nhầm với raw data?
- [ ] Có chất lượng dữ liệu, missing coverage, outlier và đơn vị đo?
- [ ] Có process backfill và late arrivals, nhất là sau khi chốt summary?
- [ ] Nếu có sharding, shard key được chọn theo query/throughput và version support?
- [ ] Có phân biệt event-to-ingest lag với replication lag?
- [ ] Có benchmark compression/latency/ingestion trên workload đại diện?
- [ ] Có kế hoạch migration/dual-write/reconciliation/cutover khi chuyển storage type?
- [ ] Có backup, compliance retention và theo dõi dữ liệu downstream?

## 49. Kết luận

**Time series collection là một mô hình lưu trữ tối ưu cho lịch sử phép đo gắn thời gian**, không phải một nhãn trang trí cho collection có field ngày giờ. MongoDB tổ chức logical measurements thành **buckets** theo timestamp và metadata, tận dụng tính lặp của schema/series để nén và cải thiện một số truy vấn time range/aggregation. Muốn có lợi thế thực tế cần chọn đúng `timeField`, `metaField`, `granularity`, query/index và retention.

Khác biệt lớn nhất so với **regular collection** nằm ở **cách tổ chức dữ liệu và mô hình thao tác**: time series thường hợp với append-heavy measurements và history rollups; regular collection linh hoạt hơn cho mutable state, unique business records và transaction workflows. Một thiết kế thực dụng có thể lưu **raw measurements trong time series**, **latest/current state trong regular collection** và **hourly/daily summaries** ở một read model riêng.

Cuối cùng, hãy coi timestamp, chất lượng dữ liệu, duplicate packets, late arrivals, TTL và compression là một phần của thiết kế hệ thống, không chỉ cấu hình database. **Thước đo quyết định** là tính đúng đắn của dữ liệu theo thời gian, dung lượng/measurement, ingestion throughput, latency truy vấn và chi phí vận hành được đo trên workload đại diện.
