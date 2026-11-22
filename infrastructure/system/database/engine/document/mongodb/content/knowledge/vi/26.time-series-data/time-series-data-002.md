# Thiết kế timeField, metaField và granularity trong MongoDB Time Series

## 1. Bài toán và mục tiêu học tập

Dữ liệu chuỗi thời gian (*time series*) là tập các phép đo hoặc sự kiện được gắn với thời gian: nhiệt độ mỗi 5 phút, mức sử dụng CPU mỗi giây, lượng điện tiêu thụ mỗi giờ, giá giao dịch, số request của API hoặc dữ liệu định vị thiết bị.

Một phép đo thường có ba thành phần:

- **Thời điểm đo:** thời gian sự kiện thực sự xảy ra.
- **Nguồn đo:** cảm biến, thiết bị, tenant, khu vực hoặc metric type.
- **Giá trị:** nhiệt độ, độ ẩm, mức điện năng, latency, request count.

MongoDB time series collections tối ưu việc lưu trữ theo **buckets**, phù hợp những phép đo được chèn liên tiếp và truy vấn theo series + khoảng thời gian.

Bài học thuộc chương **Chuỗi thời gian** của module **Database Engine Document MongoDB**, tập trung vào **Thiết kế timeField, metaField và granularity**.

Sau bài này, bạn có thể:

1. Chọn `timeField` có kiểu BSON Date và đúng ý nghĩa thời gian nghiệp vụ.
2. Phân biệt event time và ingestion time, xử lý UTC, late events và clock skew.
3. Thiết kế `metaField` ổn định để nhận diện series và tối ưu khả năng bucketing.
4. Hiểu cardinality metadata, bucket fragmentation, field order và metadata dạng object.
5. Chọn `granularity` theo khoảng đo của **từng series**, không theo tổng insert rate.
6. Phân biệt bucket span với việc làm tròn timestamp và các aggregation time bins.
7. Biết custom bucketing `bucketMaxSpanSeconds`/`bucketRoundingSeconds` từ MongoDB 6.3.
8. Tạo time series collection, insert, filter, aggregate, kiểm tra metadata và index.
9. Hiểu giới hạn TTL, unique indexes, update, sharding và transaction.
10. Viết ví dụ MongoDB Java Sync Driver và xây dựng checklist thực tế.

**Ý chính:** `timeField` xác định trục thời gian, `metaField` xác định phép đo thuộc chuỗi nào, `granularity` định hướng khoảng thời gian một bucket có thể bao phủ. Ba lựa chọn cần xuất phát từ nhịp đo, cấu trúc metadata và truy vấn thực tế.

## 2. Cấu trúc document time series

Một document đo nhiệt độ:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: {
    tenantId: "tenant-A",
    sensorId: "sensor-001",
    siteId: "warehouse-HCM",
    metricType: "temperature"
  },
  temperatureC: 27.4,
  humidityPct: 69.2,
  batteryPct: 91
}
~~~

Vai trò:

| Trường | Nhóm | Ghi chú |
|---|---|---|
| `measuredAt` | timeField | BSON Date, bắt buộc |
| `meta` | metaField | Đặc tính nhận diện nguồn đo tương đối ổn định |
| `temperatureC` | measurement | Thay đổi ở mỗi lần đo |
| `humidityPct` | measurement | Thay đổi ở mỗi lần đo |
| `batteryPct` | measurement | Có thể biến động; không nên đặt vào meta mặc định |
| `receivedAt` nếu có | metadata của event/measurement | Thời điểm server nhận, khác event time |
| `eventId` nếu có | định danh sự kiện | Dùng cho dedup ở tầng ingest; time series không có unique indexes |

Tạo collection:

~~~javascript
db.createCollection("sensorMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

`timeField` và `metaField` là **tên option**, còn `measuredAt` và `meta` là **tên field** của document.

## 3. Cơ chế bucket của MongoDB

Thay vì lưu dữ liệu time series theo cách phân tán ngẫu nhiên, MongoDB nhóm các measurements vào các **buckets** theo metadata chung và thời gian gần nhau.

~~~text
Document ingest
      |
      +--> meta = sensor-001
      |        |
      |        +--> bucket cho khoảng thời gian A
      |        |
      |        +--> bucket cho khoảng thời gian B
      |
      +--> meta = sensor-002
               |
               +--> bucket cho khoảng thời gian A
~~~

Hai measurements chỉ có cơ hội vào cùng bucket nếu:

- Có giá trị metaField tương đương theo quy tắc bucketing.
- Timestamps nằm trong khoảng thời gian bucket cho phép.
- Bucket chưa chạm giới hạn số lượng/bytes.
- Bucket còn phù hợp với trạng thái bộ đệm và hoạt động của server.

Ví dụ:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.0
}

{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}

{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S2" },
  temperatureC: 24.0
}
~~~

Hai document S1 có metadata giống nhau, thời gian gần nhau, nên **có thể** được nhóm trong một bucket. S2 có metadata khác nên thuộc một nhóm buckets khác.

### 3.1. Giới hạn vật lý của bucket

Theo tài liệu MongoDB, một bucket có tối đa khoảng **1.000 measurements hoặc 125 KB**, tùy giới hạn nào đến trước. Server cũng có thể đóng bucket sớm hơn vì bộ nhớ, cache hoặc những điều kiện khác.

Do đó:

- `granularity:"hours"` không có nghĩa tất cả phép đo trong 30 ngày đều nằm một bucket.
- Không thể suy ra chính xác số buckets bằng công thức “số giờ chia cho granularity”.
- Series có rất nhiều measurements có thể tạo nhiều buckets trong cùng khoảng thời gian.
- Series chỉ có một vài measurements có thể tạo nhiều bucket rất thưa.

### 3.2. Vì sao bucketing giúp nén dữ liệu?

Nhiều measurements cùng series thường lặp lại tên field, metadata và kiểu dữ liệu. Gom các điểm đo vào buckets giúp MongoDB tối ưu lưu trữ, index và nén.

Compression tốt khi:

- Metadata ít thay đổi.
- Các phép đo cùng series đến thường xuyên.
- Field names/field types tương đối ổn định.
- Dữ liệu đến gần theo thứ tự thời gian.

Compression kém khi:

- Metadata thay đổi theo từng request.
- Có rất nhiều series nhưng mỗi series chỉ phát một measurement.
- Dữ liệu đến rất trễ hoặc ngoài thứ tự nhiều.
- Measurement documents có kích thước và schema biến động mạnh.

### 3.3. Đừng sửa namespace system.buckets trực tiếp

Collection time series là interface người dùng. MongoDB lưu buckets trong các namespace nội bộ liên quan. Ứng dụng nên insert/find/aggregate trên **collection time series**, không ghi trực tiếp vào `system.buckets.*`.

## 4. timeField bắt buộc và kiểu BSON Date

`timeField` xác định field cấp cao nhất chứa thời điểm đo. Mỗi document phải có giá trị **BSON Date** hợp lệ ở field này.

Tạo collection:

~~~javascript
db.createCollection("voltageSamples", {
  timeseries: {
    timeField: "observedAt",
    metaField: "source",
    granularity: "seconds"
  }
});
~~~

Document hợp lệ:

~~~javascript
db.voltageSamples.insertOne({
  observedAt: ISODate("2026-11-14T08:30:00Z"),
  source: { deviceId: "D1" },
  voltage: 220.5
});
~~~

Các kiểu dữ liệu **không** nên sử dụng:

~~~javascript
// Không phải BSON Date.
{
  observedAt: "2026-11-14T08:30:00Z",
  source: { deviceId: "D1" },
  voltage: 220.5
}

// Epoch milliseconds dạng Number, không phải BSON Date.
{
  observedAt: 1794645000000,
  source: { deviceId: "D1" },
  voltage: 220.5
}

// Thiếu timeField.
{
  source: { deviceId: "D1" },
  voltage: 220.5
}
~~~

**Không nhầm BSON Timestamp với BSON Date.** Kiểu `Timestamp(...)` có mục đích riêng như replication; timeField cần BSON Date.

### 4.1. Event time và ingestion time

Một cảm biến gửi dữ liệu muộn có thể tạo document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  receivedAt: ISODate("2026-11-14T08:07:12Z"),
  meta: { sensorId: "S1" },
  temperatureC: 27.1
}
~~~

- `measuredAt`: khi sensor **thực sự đo**.
- `receivedAt`: khi server **nhận thông điệp**.

Nếu người dùng cần biểu đồ nhiệt độ theo thời điểm thực tế, chọn `measuredAt` làm timeField. Nếu phân tích SLA thời gian xử lý thông điệp, có thể chọn `receivedAt` cho collection hoặc workload khác.

**Không thay event time bằng ingestion time chỉ để tránh late events** nếu điều đó làm sai dữ liệu nghiệp vụ.

### 4.2. Out-of-order và backfill

Một gateway mất mạng 15 phút rồi gửi các measurements cũ có thể khiến bucket đã đóng hoặc không còn phù hợp. MongoDB vẫn có cơ chế chèn dữ liệu thời gian trong quá khứ khi hợp lệ, nhưng có thể tạo nhiều buckets hơn hoặc tăng chi phí ghi.

Để xử lý:

1. Lưu đúng event time.
2. Lưu thêm receivedAt nếu cần đo độ trễ.
3. Phân biệt delayed measurements với timestamp lỗi.
4. Khi có batch data, sắp xếp theo series/thời gian nếu không làm sai SLA.
5. Theo dõi hiệu quả nén và bucket density với dữ liệu đến trễ thực tế.

### 4.3. UTC và timezone

BSON Date lưu thời điểm tuyệt đối. Trong mongosh có thể biểu diễn bằng ISO UTC:

~~~javascript
ISODate("2026-11-14T08:30:00Z")
~~~

Nó tương đương **15:30** ngày 14/11/2026 tại Việt Nam (UTC+7).

Không cộng thêm 7 giờ rồi lưu lại như UTC; đó là lỗi chuyển timezone hai lần.

Nếu báo cáo theo ngày ở Việt Nam:

~~~javascript
db.sensorMeasurements.aggregate([
  {
    $project: {
      localDay: {
        $dateToString: {
          date: "$measuredAt",
          timezone: "Asia/Ho_Chi_Minh",
          format: "%Y-%m-%d"
        }
      },
      temperatureC: 1
    }
  }
]);
~~~

Timezone hiển thị hoặc nhóm báo cáo khác việc chọn timeField. Một collection có thể lưu UTC nhưng phân tích theo timezone của từng site.

### 4.4. Độ chính xác

BSON Date lưu đến **mili giây**. Nếu nguồn tạo dữ liệu microseconds/nanoseconds, cần thêm field precision hoặc sequence phù hợp, không tự biến timeField thành Number.

### 4.5. Clock skew

Sensor có đồng hồ sai có thể gửi timestamp nằm quá xa tương lai hoặc quá xa quá khứ. Hậu quả:

- Dữ liệu xuất hiện ở các khoảng thời gian không mong muốn.
- TTL có thể hoạt động không theo kỳ vọng.
- Các nhóm buckets bị phân tán.
- Báo cáo sai thứ tự thời gian.

Nên có validation tại ingest về khoảng thời gian hợp lệ, có cơ chế quarantine cho dữ liệu lỗi và có trường receivedAt để đối soát.

## 5. Chọn tên timeField và vị trí field

Tên rõ nghĩa thường là:

~~~text
measuredAt
observedAt
eventTime
recordedAt
~~~

Không dùng `date` mơ hồ khi một document có nhiều mốc thời gian.

Cấu trúc phù hợp:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}
~~~

Filter:

~~~javascript
db.sensorMeasurements.find({
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
});
~~~

### 5.1. Không thể đổi tên timeField sau khi tạo

`timeField` được chọn khi tạo collection. Không đổi được `measuredAt` thành `receivedAt` qua một `collMod` thông thường.

Nếu cần chuyển:

1. Tạo time series collection mới có cấu hình đúng.
2. Copy/backfill dữ liệu với phép biến đổi timestamp chính xác.
3. Tạo indexes và cấu hình retention cho collection mới.
4. Đối chiếu counts, time ranges, sample checks.
5. Chuyển ứng dụng đọc/ghi bằng runbook an toàn.
6. Chỉ xóa dữ liệu cũ khi đã hoàn tất kiểm chứng và có rollback plan.

## 6. metaField: nguồn đo và các thông tin ổn định

`metaField` là tùy chọn nhưng rất quan trọng với hiệu quả bucketing.

~~~javascript
db.createCollection("weatherMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

Document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  meta: {
    tenantId: "tenant-A",
    sensorId: "S1",
    siteId: "plant-01",
    metricType: "temperature"
  },
  value: 26.4
}
~~~

Metadata mô tả **series nào**, không mô tả giá trị đo ở từng thời điểm.

### 6.1. Nên đặt gì trong meta?

- `sensorId`, `deviceId`, `meterId`.
- `tenantId` trong hệ thống đa tenant.
- `siteId` hay `plantId` nếu ít đổi và thường được filter.
- `metricType` nếu collection chứa nhiều loại metric.
- Một số nhãn ổn định liên quan cách truy vấn.

Ví dụ hợp lý:

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

### 6.2. Không nên đặt gì trong meta?

- `temperatureC`, `humidityPct`, `voltage`.
- `batteryPct`, `signalRssi` thay đổi thường xuyên.
- `measuredAt` hoặc `receivedAt`.
- `requestId`, `eventId` hoặc traceId duy nhất từng lần gửi.
- Sequence number tăng theo measurement.
- Status thay đổi liên tục.

Ví dụ không phù hợp:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    sensorId: "S1",
    requestId: "req-000001",
    batteryPct: 91
  },
  temperatureC: 26.0
}
~~~

Ở phép đo tiếp theo, requestId hoặc batteryPct khác là một metadata combination khác. MongoDB có thể không tận dụng bucket đã mở cho S1 dù chuỗi đo thực tế vẫn là một sensor.

### 6.3. Tại sao metadata ổn định giúp giảm bucket fragmentation?

Giả sử 100 sensors, mỗi sensor ghi 100 measurements:

~~~text
Metadata = {sensorId}
   => khoảng 100 series, mỗi series có nhiều measurements.

Metadata = {sensorId, requestId}
   => gần 10.000 metadata combinations, nhiều bucket thưa.
~~~

Các con số bucket thực tế còn tùy phiên bản/server/giới hạn vật lý, nhưng xu hướng thiết kế là rõ: dynamic metadata làm số nhóm tăng nhanh.

### 6.4. MetaField có thể là object

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1"
}
~~~

Nó có thể chứa các subfields, không cần chỉ là string.

### 6.5. metaField không được là _id hoặc trùng timeField

Không hợp lệ:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "measuredAt"
}
~~~

hoặc:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "_id"
}
~~~

### 6.6. MetaField có thể bỏ trống

~~~javascript
db.createCollection("systemWideReadings", {
  timeseries: {
    timeField: "measuredAt",
    granularity: "seconds"
  }
});
~~~

Không có metaField thì bucketing dựa trên thời gian. Cách này có thể phù hợp một chuỗi toàn cục, nhưng thường không tối ưu nếu có hàng nghìn sources cần truy vấn riêng.

## 7. Cardinality và trade-off của metaField

**Cardinality** là số giá trị metadata khác nhau.

Cần xét hai yếu tố:

- Số series khác nhau **tổng cộng**.
- Số series **hoạt động đồng thời**.

Ví dụ có 50.000 sensors nhưng chỉ 500 đang gửi dữ liệu liên tục sẽ có đặc điểm bucket khác trường hợp cả 50.000 sensors cùng gửi.

### 7.1. Meta quá chi tiết

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  sampleId: "unique-every-time"
}
~~~

Tạo series mới với mỗi sample, gây nhiều buckets thưa và hiệu quả compression kém.

### 7.2. Meta quá thô

~~~javascript
meta: {
  tenantId: "tenant-A"
},
sensorId: "S1"
~~~

Tất cả sensors của tenant-A có cùng meta. Nếu dashboard liên tục query một sensor, server có thể xét nhiều measurements không thuộc sensor đó trong các buckets.

### 7.3. Meta cân bằng

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

Vừa nhận diện nguồn, vừa phù hợp query theo tenant/sensor/loại đo.

### 7.4. Location có nên là meta?

Nếu sensor luôn ở một room, `roomId` có thể thuộc metadata.

Nếu sensor được di chuyển liên tục:

- Đưa roomId vào meta sẽ chia series theo lịch sử vị trí.
- Để roomId ở measurement có thể giữ series liên tục theo sensor, nhưng query theo room phải xử lý khác.
- Lưu lịch sử chuyển phòng trong device registry là một lựa chọn khác.

Quyết định dựa vào ý nghĩa series và truy vấn sản phẩm, không có đáp án chung cho mọi ứng dụng.

### 7.5. Không dùng các field nhạy cảm không cần thiết

Đừng lặp lại access tokens, passwords hay PII không cần thiết trong metadata của hàng triệu measurements. Metadata nên gồm những identifier/nhãn phục vụ phân nhóm, filter và an toàn dữ liệu.

## 8. Object metadata, field order và consistency

Một metadata object:

~~~javascript
meta: {
  tenantId: "tenant-A",
  sensorId: "S1",
  metricType: "temperature"
}
~~~

nên có cấu trúc và kiểu ổn định giữa các writer.

### 8.1. Kiểu dữ liệu quan trọng

Hai ví dụ:

~~~javascript
meta: { sensorId: 101 }
~~~

và:

~~~javascript
meta: { sensorId: "101" }
~~~

khác kiểu BSON, có thể tạo hai giá trị metadata khác nhau.

### 8.2. Truy vấn subfields thay vì cả object

Mặc dù MongoDB có cơ chế chuẩn hóa metadata khi bucketing, equality của BSON objects trong query có thể phụ thuộc thứ tự field.

Thay vì:

~~~javascript
db.weatherMeasurements.find({
  meta: {
    sensorId: "S1",
    tenantId: "tenant-A"
  }
});
~~~

nên:

~~~javascript
db.weatherMeasurements.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1"
});
~~~

Cách này không bị ràng buộc vào thứ tự và số lượng subfields trong object, đồng thời dễ xây index theo query.

### 8.3. Hạn chế array trong metadata

~~~javascript
meta: {
  tags: ["warehouse", "hot"]
}
~~~

và:

~~~javascript
meta: {
  tags: ["hot", "warehouse"]
}
~~~

là hai arrays có thứ tự khác. Đưa array tags biến động vào meta có thể tạo những nhóm series bất ngờ.

### 8.4. Có thể thêm subfield nhưng không đổi tên metaField

Sau khi tạo collection với `metaField:"meta"`, bạn có thể quyết định những documents mới chứa thêm `meta.floor` theo schema phù hợp. Nhưng không thể đổi option collection sang `metaField:"labels"`.

Nếu thay đổi schema metadata căn bản, cần kế hoạch migration.

## 9. granularity: seconds, minutes và hours

`granularity` mô tả nhịp dữ liệu và giúp MongoDB chọn bucket interval.

Các giá trị hợp lệ:

~~~text
seconds
minutes
hours
~~~

Mặc định là `seconds`.

| granularity | Khoảng thời gian bucket tối đa | Workload minh họa |
|---|---:|---|
| `seconds` | **1 giờ** | Nhiều điểm đo mỗi giây hoặc vài giây |
| `minutes` | **24 giờ** | Một điểm đo vài phút một lần |
| `hours` | **30 ngày** | Một điểm đo mỗi giờ hoặc thưa hơn |

**Không được nhầm:** `granularity:"minutes"` không làm tròn mọi timestamp tới đầu phút. Nó cho biết **khung thời gian bucketing**, không làm mất precision của Date.

### 9.1. Nhịp của mỗi series, không phải tổng ingestion

Giả sử 10.000 sensors, mỗi sensor gửi một measurement sau 5 phút. Tổng tốc độ insert vào collection khá lớn, nhưng khoảng cách hai điểm của cùng `sensorId` vẫn là 5 phút.

`granularity:"minutes"` thường phù hợp hơn việc chọn `seconds` chỉ vì thấy tổng insert rate cao.

### 9.2. Nhịp mỗi giây

~~~text
S1: 08:00:00, 08:00:01, 08:00:02, ...
~~~

Chọn `seconds`. Bucket có span tối đa 1 giờ, nhưng trong workload rất dày nó có thể đạt giới hạn số measurements/bytes sớm hơn.

### 9.3. Nhịp mỗi 5 phút

~~~text
S1: 08:00, 08:05, 08:10, 08:15, ...
~~~

Chọn `minutes`. Bucket có span tối đa 24 giờ và có thể đóng sớm.

### 9.4. Nhịp mỗi 6 giờ

~~~text
S1: 00:00, 06:00, 12:00, 18:00, ...
~~~

Có thể chọn `hours`, đặc biệt khi query thường lấy cả tuần/tháng.

### 9.5. Không chỉ xem tần suất ghi

Cần xem đồng thời:

- Khoảng cách giữa các measurements **cùng meta**.
- Truy vấn chủ yếu lấy 10 phút, 1 ngày hay 1 tháng.
- Kích thước một measurement.
- Số series hoạt động.
- Dữ liệu đến trễ/out-of-order.
- TTL/retention cần chính xác mức nào.
- Chi phí cache, index, storage và query latency.

## 10. Granularity ảnh hưởng hiệu quả query như thế nào?

Truy vấn dashboard chỉ lấy 5 phút:

~~~javascript
db.weatherMeasurements.find({
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:05:00Z")
  }
});
~~~

Nếu buckets bao phủ khoảng quá rộng, server có thể phải xét bucket chứa rất nhiều measurements ngoài 5 phút này rồi lọc.

Ngược lại, một báo cáo lấy 30 ngày với buckets quá ngắn có thể cần duyệt rất nhiều buckets.

~~~text
Query trong khoảng 30 ngày

Bucket span nhỏ:
[ ][ ][ ][ ][ ][ ][ ] ... nhiều bucket ranges

Bucket span phù hợp:
[=====][=====][=====] ... ít bucket ranges hơn

Bucket span quá rộng:
[==============================]
có thể đọc thừa cho nhiều query ngắn
~~~

**Granularity là một trade-off**, không có một giá trị luôn tốt nhất.

### 10.1. Granularity không tạo sẵn báo cáo theo giờ

Chọn `hours` không có nghĩa MongoDB tự tính average từng giờ. Muốn nhóm measurements thành time bins, dùng aggregation operators như `$dateTrunc` và `$group`.

### 10.2. Granularity không bảo đảm mỗi bucket chứa đủ một interval

Bucket có giới hạn measurements và bytes. Với tốc độ ghi rất cao, nhiều buckets có thể được tạo trong cùng một giờ dù granularity là seconds.

## 11. Custom bucketing từ MongoDB 6.3

Từ MongoDB 6.3, có thể thay `granularity` bằng hai parameters:

- `bucketMaxSpanSeconds`: khoảng thời gian tối đa giữa các timestamps được nhóm trong bucket.
- `bucketRoundingSeconds`: kích thước bước dùng để làm tròn **mốc bắt đầu bucket** khi tạo bucket.

Phải đặt **cả hai bằng nhau** và không được dùng chung với `granularity`.

### 11.1. Bucket 4 giờ

~~~javascript
db.createCollection("weather4h", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    bucketMaxSpanSeconds: 14400,
    bucketRoundingSeconds: 14400
  }
});
~~~

14.400 giây = 4 giờ. Khi cần tạo bucket mới cho:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T10:24:35Z"),
  meta: { sensorId: "S1" },
  temperatureC: 27
}
~~~

mốc bắt đầu bucket có thể được làm tròn xuống **08:00 UTC**, theo khung 4 giờ. Document vẫn giữ `measuredAt:10:24:35Z`; việc rounding **không sửa timestamp người dùng**.

### 11.2. Custom window 5 phút

~~~javascript
db.createCollection("fiveMinuteMeasurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    bucketMaxSpanSeconds: 300,
    bucketRoundingSeconds: 300
  }
});
~~~

300 giây = 5 phút. Phù hợp để thử khi hệ thống query những block 5 phút cố định. Cần đo so với granularity minutes để biết có lợi thực tế hay không.

### 11.3. Không trộn hai cơ chế

Không hợp lệ:

~~~javascript
db.createCollection("invalidCombined", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes",
    bucketMaxSpanSeconds: 300,
    bucketRoundingSeconds: 300
  }
});
~~~

### 11.4. Giới hạn tham số

Theo tài liệu MongoDB, `bucketMaxSpanSeconds` cho phép giá trị từ **1 đến 31.536.000 giây**; `bucketRoundingSeconds` phải bằng cùng giá trị. Kiểm tra phiên bản server/FCV vì hai parameters này chưa có trên bản cũ.

## 12. Có thể sửa granularity về sau không?

Tên `timeField` và `metaField` không thể đổi sau khi tạo collection. Với granularity, MongoDB cho phép **tăng bucket span**, nhưng không giảm, thông qua `collMod` ở những phiên bản được hỗ trợ.

Ví dụ tăng từ minutes lên hours:

~~~javascript
db.runCommand({
  collMod: "sensorMeasurements",
  timeseries: {
    granularity: "hours"
  }
});
~~~

Không được giảm từ `hours` xuống `minutes` hoặc `minutes` xuống `seconds` theo cơ chế này.

### 12.1. Tăng cặp custom parameters

~~~javascript
db.runCommand({
  collMod: "weather4h",
  timeseries: {
    bucketMaxSpanSeconds: 28800,
    bucketRoundingSeconds: 28800
  }
});
~~~

Ví dụ tăng từ 4 giờ lên 8 giờ. Phải gửi cả hai parameters và cùng giá trị.

### 12.2. Không tự tái tổ chức toàn bộ buckets cũ

Thay granularity ảnh hưởng định nghĩa/chiến lược bucketing; không mặc định mọi bucket lịch sử sẽ được viết lại như một collection mới. Nếu cần đánh giá thiết kế mới trên toàn dữ liệu, tạo collection thử nghiệm rồi backfill và so sánh.

### 12.3. Version constraints

- Thay granularity sau tạo yêu cầu MongoDB hỗ trợ, từ 5.0.1 trở lên theo hướng dẫn.
- Chỉnh granularity với **sharded** time series collection yêu cầu version phù hợp (MongoDB 6.0+ theo tài liệu).
- Custom bucketing từ MongoDB 6.3 có lưu ý downgrade/FCV.

Nếu sai thiết kế meta/time, phải tạo collection mới và migration; `collMod` không phải công tắc sửa mọi lỗi schema.

## 13. Tạo dữ liệu thực hành

Dùng database riêng:

~~~javascript
use time_series_design_lab
~~~

Tạo collection trong môi trường mới:

~~~javascript
db.createCollection("roomReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

Tạo 8 document mẫu:

~~~javascript
const samples = [
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.0,
    humidityPct: 61
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.4,
    humidityPct: 60
  },
  {
    measuredAt: ISODate("2026-11-14T08:10:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 26.8,
    humidityPct: 60
  },
  {
    measuredAt: ISODate("2026-11-14T08:15:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S1", roomId: "101" },
    temperatureC: 27.1,
    humidityPct: 59
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 24.0,
    humidityPct: 66
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 24.5,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:10:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 25.0,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:15:00Z"),
    meta: { tenantId: "tenant-A", sensorId: "S2", roomId: "102" },
    temperatureC: 25.5,
    humidityPct: 64
  }
];

db.roomReadings.insertMany(samples);
~~~

Khi collection mới/rỗng:

- Có **8 measurements**.
- S1 có 4 điểm, cách nhau 5 phút.
- S2 có 4 điểm, cũng cách nhau 5 phút.
- Mỗi sensor có metadata ổn định.
- Mỗi điểm đo mang cả nhiệt độ và độ ẩm.

**Lưu ý:** Không có unique index chống chèn trùng timestamp. Chạy lại `insertMany(samples)` sẽ thêm dữ liệu trùng nội dung (theo ID mới), nên chỉ chạy một lần trong database thực hành hoặc tạo database mẫu mới cho lượt thử lại.

### 13.1. Đọc các measurement của S1

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1"
}).sort({ measuredAt: 1 });
~~~

Kết quả mong đợi là 08:00, 08:05, 08:10, 08:15 UTC.

### 13.2. Đọc trong khoảng nửa mở

~~~javascript
db.roomReadings.find({
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:05:00Z"),
    $lt: ISODate("2026-11-14T08:15:00Z")
  }
}).sort({ measuredAt: 1 });
~~~

Kết quả chỉ có 08:05 và 08:10. `$lt` loại bỏ ranh giới trên 08:15, giúp tránh double count khi chia khoảng liên tiếp.

### 13.3. Query không có meta filter

~~~javascript
db.roomReadings.find({
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:10:00Z")
  }
});
~~~

Lệnh này có thể lấy điểm đo từ cả S1 lẫn S2. Trong workload lớn, filter thiếu metadata có thể phải xét nhiều buckets/series hơn.

## 14. Đọc thông tin cấu hình đã được tạo

~~~javascript
db.getCollectionInfos({
  name: "roomReadings"
});
~~~

Một output minh họa:

~~~javascript
[
  {
    name: "roomReadings",
    type: "timeseries",
    options: {
      timeseries: {
        timeField: "measuredAt",
        metaField: "meta",
        granularity: "minutes"
      }
    }
  }
]
~~~

Thực tế có thể có fields khác hoặc parameters do server thêm vào.

Cũng có thể dùng:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: { name: "roomReadings" }
});
~~~

Điểm cần kiểm tra:

- `type` có phải `"timeseries"`?
- `options.timeseries.timeField` có đúng?
- `options.timeseries.metaField` có đúng?
- Granularity hoặc cặp custom có đúng?
- `expireAfterSeconds` nếu có, là bao nhiêu?

Không suy luận loại collection chỉ qua tên field `measuredAt` trong document; ordinary collection cũng có thể chứa Date.

## 15. Index cho query theo meta và time

Pattern thường gặp:

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
}).sort({ measuredAt: 1 });
~~~

Từ **MongoDB 6.3**, những time series collections mới có metaField được server tạo compound index mặc định liên quan metaField và timeField.

Với query cụ thể, có thể bổ sung index:

~~~javascript
db.roomReadings.createIndex(
  {
    "meta.tenantId": 1,
    "meta.sensorId": 1,
    measuredAt: 1
  },
  {
    name: "idx_tenant_sensor_time"
  }
);
~~~

### 15.1. Equality trên meta, range trên time

Các trường meta equality thu hẹp series. Sau đó range trên time chọn khoảng đo cần thiết. Đây là một pattern thường hữu ích.

### 15.2. explain và getIndexes

~~~javascript
db.roomReadings.getIndexes();
~~~

~~~javascript
db.roomReadings.explain("executionStats").find({
  "meta.tenantId": "tenant-A",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
});
~~~

Kế hoạch query có thể hiển thị các thành phần bucket scan/index scan/unpack theo phiên bản và query engine. Khi triển khai thật, xem số document/bucket được xét, latency và khả năng index được sử dụng.

### 15.3. Không mặc định index nào cũng cần

Index có chi phí storage/write. Chỉ tạo index bổ sung khi query patterns và explain chứng minh lợi ích. Một default meta+time index có thể đã đủ với những truy vấn đơn giản.

## 16. Aggregation time bin khác bucket lưu trữ

Để tổng hợp trung bình nhiệt độ theo sensor:

~~~javascript
db.roomReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "tenant-A",
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T09:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$meta.sensorId",
      n: { $sum: 1 },
      avgTemp: { $avg: "$temperatureC" },
      minTemp: { $min: "$temperatureC" },
      maxTemp: { $max: "$temperatureC" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Trên dữ liệu mẫu:

| Sensor | n | Trung bình | Min | Max |
|---|---:|---:|---:|---:|
| S1 | 4 | 26.575 | 26.0 | 27.1 |
| S2 | 4 | 24.75 | 24.0 | 25.5 |

### 16.1. Nhóm theo khung 5 phút

~~~javascript
db.roomReadings.aggregate([
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        fiveMinutes: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            binSize: 5,
            timezone: "UTC"
          }
        }
      },
      averageC: { $avg: "$temperatureC" },
      n: { $sum: 1 }
    }
  },
  { $sort: { "_id.sensorId": 1, "_id.fiveMinutes": 1 } }
]);
~~~

`$dateTrunc` tạo **bins của báo cáo**, không thay `granularity` hoặc tạo các physical buckets nội bộ mới.

### 16.2. Báo cáo theo ngày giờ Việt Nam

~~~javascript
db.roomReadings.aggregate([
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        day: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        }
      },
      avgTemp: { $avg: "$temperatureC" }
    }
  }
]);
~~~

Dữ liệu gốc vẫn lưu theo UTC; grouping có thể dùng timezone doanh nghiệp.

## 17. TTL: tự xóa dữ liệu time series

Một collection có thể có retention:

~~~javascript
db.createCollection("sevenDayReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 604800
});
~~~

604.800 giây là 7 ngày.

### 17.1. TTL theo bucket, không xóa đúng từng giây

MongoDB có thể xóa dữ liệu time series theo **bucket** khi tất cả measurements trong bucket đủ điều kiện hết hạn. Việc xóa là background process và có độ trễ.

Vì vậy, một document có `measuredAt + expireAfterSeconds` đã qua vẫn có thể còn tồn tại cho tới khi bucket đủ điều kiện xóa.

### 17.2. Granularity ảnh hưởng retention

Nếu bucket span quá rộng so với thời hạn retention, những phép đo cũ có thể bị giữ lâu hơn mong muốn.

Ví dụ workload báo cáo vài giờ, retention 7 ngày, nhưng chọn `granularity:"hours"` (span tối đa 30 ngày) cần được đánh giá vì bucket rộng có thể trì hoãn xóa.

### 17.3. TTL không thay quy định xóa dữ liệu

Nếu phải xóa chính xác theo yêu cầu pháp lý, cần kiểm chứng cách TTL hoạt động và bổ sung quy trình retention được chấp thuận; không tuyên bố TTL sẽ xóa mỗi measurement đúng giây hết hạn.

### 17.4. Partial TTL theo metadata

Từ MongoDB 7.0, có hỗ trợ partial TTL index dựa trên `metaField` cho một số kịch bản có retention riêng theo nhóm metadata. Điều kiện cụ thể phụ thuộc version và phải kiểm tra docs trước khi áp dụng.

## 18. Những giới hạn khác với ordinary collection

| Khía cạnh | Đặc điểm time series |
|---|---|
| timeField | Bắt buộc, phải là BSON Date |
| metaField | Optional, tên cấu hình cố định sau tạo |
| Granularity | Có thể tăng span; không giảm |
| Unique indexes | Không hỗ trợ |
| _id index mặc định | Không được tự động tạo như ordinary collection |
| Document size | Tài liệu time series có giới hạn riêng (4 MB theo Manual hiện hành) |
| Updates | Hạn chế, chủ yếu match/modify metaField theo điều kiện hỗ trợ |
| Transaction writes | Không hỗ trợ ghi vào time series collection trong multi-document transaction |
| Collection type | Không chuyển trực tiếp ordinary collection thành time series |
| Schema validation | Có các tính năng validation không được hỗ trợ |
| Change streams | Không hỗ trợ trên time series collection theo Manual hiện hành |
| Capped | Không tạo time series collection dạng capped |

Cần kiểm tra chính sách/version hiện hành trước khi ứng dụng sử dụng các chức năng nâng cao.

### 18.1. Vì sao không có unique index (sensor,time)?

Time series collection không hỗ trợ unique indexes. Nếu một phép đo được gửi hai lần, không thể dựa vào:

~~~javascript
// Không được hỗ trợ trên time series collection.
db.roomReadings.createIndex(
  { "meta.sensorId": 1, measuredAt: 1 },
  { unique: true }
);
~~~

Để chống duplicate:

- Tạo một idempotency registry bằng ordinary collection có unique key.
- Deduplicate upstream theo event ID trong hệ thống ingest.
- Thiết kế protocol retry đảm bảo cùng request ID.
- Hoặc định nghĩa aggregation có khả năng xử lý trùng nếu nghiệp vụ cho phép.

**Đừng suy luận rằng default _id đã là unique**, vì time series collections không có default unique `_id_` index như ordinary collections.

### 18.2. Không dùng time series cho dữ liệu cập nhật liên tục

Nếu document đại diện trạng thái hiện tại và thường xuyên thay đổi, ordinary collection có thể hợp lý hơn. Time series phù hợp lịch sử measurements chủ yếu được append.

### 18.3. Tách danh mục thiết bị

Một mô hình gồm:

~~~text
devices (ordinary collection)
  _id, tenantId, model, owner, currentStatus

roomReadings (time series)
  measuredAt, meta, temperatureC, humidityPct
~~~

Thông tin trạng thái hiện tại nằm ở collection thiết bị; phép đo lịch sử nằm ở time series.

## 19. Time series và hệ thống đa tenant

Một metadata hợp lý:

~~~javascript
meta: {
  tenantId: "tenant-A",
  plantId: "plant-01",
  sensorId: "S1"
}
~~~

Query:

~~~javascript
db.roomReadings.find({
  "meta.tenantId": "tenant-A",
  "meta.plantId": "plant-01",
  "meta.sensorId": "S1",
  measuredAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});
~~~

### 19.1. Metadata không tự thực hiện authorization

Tầng ứng dụng phải lấy tenantId từ session/token đã xác thực và thêm filter. Unique/index hoặc grouping không tự ngăn truy cập dữ liệu của tenant khác.

### 19.2. Sensor chuyển tenant hoặc site

Nếu một sensor chuyển từ tenant-A sang tenant-B vào ngày 14, dữ liệu trước đó có thể cần giữ meta tenant-A để bảo toàn lịch sử ownership.

Không cập nhật toàn bộ historical measurements theo owner hiện tại nếu điều đó làm sai báo cáo quá khứ.

### 19.3. Global sensor ID hay tenant-scoped sensor ID?

Nếu sensorId chỉ unique trong tenant, `meta:{tenantId,sensorId}` là một series ID hợp lý. Nếu sensorId global, có thể dùng `sensorId` làm series ID và giữ tenantId cho authorization, nhưng vẫn cần đánh giá chi phí query/bucket cardinality.

## 20. Sharding time series collections

Time series collections có thể sharded theo giới hạn của server/version.

Shard key thường được chọn từ:

- `metaField`.
- Subfields của `metaField`.
- `timeField` theo ràng buộc version, nhưng từ MongoDB 8.0 việc dùng timeField trong shard key time series đã **deprecated**.

Ví dụ thiết kế metadata-based:

~~~javascript
{ "meta.sensorId": "hashed" }
~~~

hoặc:

~~~javascript
{ "meta.tenantId": 1, "meta.sensorId": 1 }
~~~

### 20.1. Vì sao không shard chỉ theo timeField?

Timestamp thường tăng tuần tự. Một range shard key chỉ có timeField có thể dồn các writes mới về một chunk/shard, gây hotspot.

### 20.2. Meta có cardinality quá thấp

Sharding theo tenantId nhưng chỉ có hai tenants, một tenant rất lớn, có thể làm phân bố không cân bằng. Cần cân nhắc subfields như sensorId và pattern truy vấn.

### 20.3. Sharding không sửa metaField sai

Nếu meta chứa requestId mới ở mỗi insert, thêm shards không làm series trở nên ổn định. Vấn đề bucket fragmentation vẫn tồn tại.

### 20.4. Resharding có điều kiện version

MongoDB 8.0.10+ bổ sung khả năng reshard time series collections trong những điều kiện nhất định; không tự áp dụng runbook ordinary collections cho mọi version.

## 21. Ba kịch bản thiết kế thực tế

### Kịch bản A — Nhiệt độ mỗi giây

- Mỗi sensor gửi 1 measurement/giây.
- Dashboard truy vấn 15 phút gần nhất.
- Meta có tenantId, sensorId, metricType ổn định.

Gợi ý:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "meta",
  granularity: "seconds"
}
~~~

### Kịch bản B — Công tơ điện mỗi 5 phút

- Mỗi meter gửi 1 measurement/5 phút.
- Báo cáo theo giờ/ngày.
- Meta có tenantId và meterId.

Gợi ý:

~~~javascript
timeseries: {
  timeField: "measuredAt",
  metaField: "meter",
  granularity: "minutes"
}
~~~

Từ MongoDB 6.3, có thể thử custom `300/300` nếu cần bucket windows 5 phút và workload thực sự được lợi.

### Kịch bản C — KPI mỗi 6 giờ

- Một service/metric tạo 1 measurement mỗi 6 giờ.
- Báo cáo theo tuần/quý.
- Có thể chọn `hours` nếu không gặp vấn đề TTL/query ranges.

Không chọn `hours` nếu retention rất ngắn và cần xóa dữ liệu với độ trễ nhỏ mà chưa xét TTL bucket semantics.

### 21.1. Có nên đặt tất cả metrics vào một collection?

Nếu các metrics có nhịp ghi, retention, schema và query pattern rất khác nhau, việc tách collections có thể dễ tối ưu hơn một cấu hình granularity chung.

## 22. Out-of-order và data backfill

~~~text
S1 measuredAt = 08:00 -> ingest 08:00
S1 measuredAt = 08:10 -> ingest 08:10
S1 measuredAt = 08:05 -> ingest 08:30 (đến trễ)
~~~

Late event vẫn nên giữ `measuredAt=08:05` nếu đó là event time đúng.

### 22.1. Lưu receivedAt để quan sát độ trễ

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:05:00Z"),
  receivedAt: ISODate("2026-11-14T08:30:00Z"),
  meta: { sensorId: "S1" },
  temperatureC: 26.4
}
~~~

Độ trễ:

~~~javascript
db.roomReadings.aggregate([
  { $match: { receivedAt: { $type: "date" } } },
  {
    $project: {
      sensorId: "$meta.sensorId",
      lagMs: {
        $subtract: ["$receivedAt", "$measuredAt"]
      }
    }
  }
]);
~~~

Bộ dữ liệu mẫu mục 13 không có receivedAt; chỉ sử dụng pipeline này khi đã có dữ liệu chứa field đó.

### 22.2. Backfill có thể tốn thêm buckets

Nếu nạp lịch sử theo thứ tự ngẫu nhiên, có thể tăng chi phí bucketing. Trên tập dữ liệu lớn, đánh giá việc sắp xếp theo series/time trước khi bulk insert, miễn không ảnh hưởng yêu cầu latency.

## 23. Đo performance, compression và bucket density

Không thể chọn granularity hoàn toàn bằng lý thuyết. Hãy thử các cấu hình trên workload đại diện.

### 23.1. Các số liệu cần đo

- Tổng số measurements.
- Số unique meta values.
- Số active series đồng thời.
- Số measurements/series/giờ.
- Kích thước trung bình một measurement.
- Tỷ lệ late events.
- Tổng storage và index size.
- Query p50/p95/p99 latency.
- Insert throughput và độ trễ ingest.
- CPU/RAM/I/O và WiredTiger cache pressure.
- Hiệu quả TTL và tính đúng của retention.

### 23.2. Thử với các cấu hình khác nhau

Ví dụ tạo ba collections test giống nhau ngoại trừ bucket policy:

~~~text
roomReadingsSeconds
roomReadingsMinutes
roomReadingsCustom300
~~~

Nạp cùng dataset đại diện vào từng collection, tạo index tương đương, rồi so:

- Query 15 phút theo sensor.
- Query 1 ngày theo sensor.
- Query 30 ngày theo tenant.
- Query average theo metricType.
- Dữ liệu đến trễ 1 giờ.
- Dữ liệu meta cardinality cao.

### 23.3. Không chỉ nhìn tổng document count

Hai hệ thống mỗi hệ 10 triệu measurements:

~~~text
Hệ A: 100 sensors, mỗi sensor 100.000 measurements.
Hệ B: 10 triệu sensor IDs, mỗi sensor 1 measurement.
~~~

Bucket density rất khác nhau. A thường thuận lợi cho compression, còn B có rất nhiều metadata values và buckets thưa.

### 23.4. Đo theo phiên bản server

MongoDB thay đổi bucketing, compression, optimizer và defaults giữa releases. Kết quả tối ưu trên MongoDB 6.x không mặc nhiên giống MongoDB 8.x/9.x.

## 24. Java Sync Driver: tạo time series collection

MongoDB Java Sync Driver có `TimeSeriesOptions` và `CreateCollectionOptions`.

Ví dụ giả định `client` là `MongoClient` đã kết nối:

~~~java
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;

MongoDatabase database =
    client.getDatabase("time_series_design_lab");

TimeSeriesOptions tsOptions =
    new TimeSeriesOptions("measuredAt")
        .metaField("meta")
        .granularity(TimeSeriesGranularity.MINUTES);

CreateCollectionOptions options =
    new CreateCollectionOptions()
        .timeSeriesOptions(tsOptions);

database.createCollection("roomReadingsJava", options);
~~~

Lệnh tạo collection yêu cầu MongoDB Server/FCV và driver tương thích; không chạy lại nếu collection đã tồn tại.

### 24.1. Insert measurement từ Java

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.Date;

MongoCollection<Document> readings =
    database.getCollection("roomReadingsJava");

Document meta = new Document("tenantId", "tenant-A")
    .append("sensorId", "S1")
    .append("roomId", "101");

Document measurement = new Document("measuredAt", new Date())
    .append("meta", meta)
    .append("temperatureC", 26.4)
    .append("humidityPct", 60);

readings.insertOne(measurement);
~~~

`java.util.Date` được serialize thành BSON Date. Nếu ứng dụng dùng `Instant`, cần codec/mapping đúng phiên bản để field được lưu thành BSON Date.

### 24.2. Query meta và khoảng thời gian

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Sorts.ascending;

import java.time.Instant;
import java.util.Date;

Date from = Date.from(
    Instant.parse("2026-11-14T08:00:00Z")
);

Date to = Date.from(
    Instant.parse("2026-11-14T09:00:00Z")
);

for (Document item : readings.find(
        and(
            eq("meta.tenantId", "tenant-A"),
            eq("meta.sensorId", "S1"),
            gte("measuredAt", from),
            lt("measuredAt", to)
        )
    ).sort(ascending("measuredAt"))) {

    System.out.println(item.toJson());
}
~~~

### 24.3. Custom bucketing API tùy driver version

Các driver/versions có thể khác nhau về methods dùng để set custom bucketing values. Nếu bản đang dùng chưa có API tương ứng, hãy dùng lệnh create collection bằng BSON Document được hỗ trợ hoặc nâng driver theo hướng dẫn chính thức, không đoán tên methods.

### 24.4. Không tạo unique index theo sensor+time

Time series không hỗ trợ unique indexes. Ứng dụng Java cần xử lý chống lặp bằng cơ chế riêng nếu yêu cầu chính xác.

## 25. MongoDB Compass

Compass có thể tạo và truy vấn time series collections, nhưng vị trí và tính sẵn có của các option khác nhau theo phiên bản.

Quy trình thực hành:

1. Kết nối tới MongoDB Server hỗ trợ time series.
2. Mở database `time_series_design_lab`.
3. Tạo collection mới và chọn loại **Time Series** nếu UI hỗ trợ.
4. Đặt timeField `measuredAt`, metaField `meta`, granularity `minutes`.
5. Nếu UI không expose đầy đủ options, dùng mongosh `db.createCollection`.
6. Xem các document và chạy filter trên `meta.sensorId`.
7. Chạy aggregation theo ngày/giờ.
8. Kiểm tra indexes và cấu hình qua mongosh.
9. Không sửa bucket storage nội bộ trực tiếp.
10. Đối chiếu UI với dữ liệu thực trên phiên bản đang chạy.

## 26. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Granularity minutes làm tròn measuredAt tới phút” | Nó ảnh hưởng bucket span, không mất timestamp precision |
| “Minutes nghĩa là bucket dài đúng 1 phút” | Khoảng tối đa là 24 giờ |
| “Hours nghĩa là tất cả measurements 30 ngày chung bucket” | Bucket vẫn có giới hạn số/byte và có thể đóng sớm |
| “Chọn granularity theo tổng insert/s” | Chọn theo nhịp **mỗi series** |
| “Metadata càng nhiều càng tốt” | Dynamic metadata tăng cardinality/bucket fragmentation |
| “batteryPct nên nằm trong meta” | Đây thường là measurement thay đổi |
| “timeField có thể là string ISO” | Phải là BSON Date |
| “Epoch millis Number là Date” | Không phải; cần tạo BSON Date |
| “Không thể ingest late events” | Có thể, nhưng ảnh hưởng bucketing/hiệu năng |
| “TimeField luôn là receivedAt” | Phải dựa theo event time nghiệp vụ |
| “Đổi metaField bằng collMod” | Không đổi tên field cấu hình sau tạo |
| “Có thể giảm granularity hours -> seconds” | Không qua collMod theo quy tắc |
| “Custom 300 thêm cùng minutes được” | Phải chọn một cơ chế |
| “TTL xóa đúng từng điểm khi hết hạn” | Xóa theo bucket/background |
| “Time series có unique _id như collection thường” | Không tạo default _id index như ordinary collection |
| “Unique sensor+timestamp index được tạo” | Unique indexes không được hỗ trợ |
| “Transaction ghi vào time series bình thường” | Write transactions không được hỗ trợ |
| “Aggregation hourly tự đến từ granularity hours” | Aggregation bins do $dateTrunc/$group |
| “Sharding theo timeField luôn tốt” | Có hotspot; deprecated với time series từ MongoDB 8.0 |
| “Không cần index vì có bucket” | Index meta/time vẫn quan trọng |
| “Tất cả metrics nên một collection” | Tùy nhịp, schema, retention, query |
| “Dữ liệu clock-skew tự được server sửa” | Cần validation/quarantine ở ingest |

## 27. Bài tập thực hành

Các bài sử dụng dữ liệu từ mục 13; không chạy lại insertMany trên collection có sẵn nếu muốn giữ kết quả kỳ vọng.

### Bài 1 — Chỉ ra ba nhóm field

Trong document:

~~~javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { tenantId: "A", sensorId: "S1" },
  temperatureC: 26.1,
  batteryPct: 87
}
~~~

Field nào là time, meta và measurement? Vì sao batteryPct không nên ở meta?

### Bài 2 — Kiểm tra kiểu Date

~~~javascript
{ measuredAt: "2026-11-14T08:00:00Z" }
{ measuredAt: ISODate("2026-11-14T08:00:00Z") }
{ measuredAt: 1794643200000 }
{ measuredAt: Timestamp(1760000000, 1) }
~~~

**Đáp án:** Chỉ giá trị BSON Date `ISODate(...)` thích hợp cho timeField.

### Bài 3 — Nhịp 5 phút của từng sensor

10.000 sensors, mỗi sensor gửi 1 measurement/5 phút. Chọn granularity dựa trên tổng insert rate hay spacing từng sensor? Gợi ý seconds, minutes hay hours?

### Bài 4 — Bucket span

Điền khoảng tối đa:

| granularity | Span |
|---|---|
| seconds | ? |
| minutes | ? |
| hours | ? |

**Đáp án:** 1 giờ, 24 giờ, 30 ngày.

### Bài 5 — Hai sensor cùng timestamp

S1 và S2 đo đúng 08:05. Nếu meta.sensorId khác nhau, hai measurements có vào cùng bucket không? Vì sao?

### Bài 6 — Dynamic metadata

~~~javascript
meta: { sensorId: "S1", requestId: "R001" }
meta: { sensorId: "S1", requestId: "R002" }
~~~

Giải thích vì sao schema này có thể làm buckets thưa; đề xuất thiết kế mới.

### Bài 7 — Query interval

Viết query của S1 từ 08:05 đến trước 08:15 UTC. **Kỳ vọng:** hai measurements 08:05 và 08:10.

### Bài 8 — Average

Viết aggregation tính average temperature theo sensor. **Kỳ vọng:** S1=26.575 và S2=24.75.

### Bài 9 — $dateTrunc

Dùng `$dateTrunc` theo khung 5 phút. Nó thay đổi physical bucket storage hay chỉ tạo bins trong báo cáo?

### Bài 10 — Custom 4 giờ

Viết createCollection dùng `bucketMaxSpanSeconds:14400` và `bucketRoundingSeconds:14400`. Một phép đo 10:24:35Z có thể tạo bucket bắt đầu từ mốc nào?

### Bài 11 — Đọc cấu hình

Chạy:

~~~javascript
db.getCollectionInfos({ name: "roomReadings" });
~~~

Đọc timeField, metaField và granularity.

### Bài 12 — Có thể đổi các options?

- minutes -> hours?
- hours -> minutes?
- timeField measuredAt -> receivedAt?
- metaField meta -> source?

Giải thích lựa chọn nào có thể dùng collMod và lựa chọn nào cần collection mới.

### Bài 13 — TTL

Một collection có `expireAfterSeconds:604800`. Vì sao dữ liệu đo cũ hơn 7 ngày vẫn có thể chưa bị xóa ngay?

### Bài 14 — Event time

Sensor đo lúc 08:05 nhưng server nhận lúc 08:40. Nếu báo cáo diễn biến nhiệt độ, timeField nên chứa 08:05 hay 08:40?

### Bài 15 — Multi tenant

Thiết kế meta cho 100 tenants, mỗi tenant có 1.000 sensors. Query nên thêm những meta filters nào để vừa an toàn vừa chọn đúng series?

### Bài 16 — Unique sensor/time

Vì sao không thể tạo unique index trên `{"meta.sensorId":1,measuredAt:1}` trong time series collection? Đề xuất một cơ chế idempotency ngoài collection đó.

### Bài 17 — Sharding

Tại sao shard key chỉ gồm measuredAt có thể gây hotspot? Vì sao meta.sensorId là một ứng cử viên tốt hơn trong một số workloads?

### Bài 18 — Độ trễ ingest

Lưu cả measuredAt và receivedAt, tính chênh lệch bằng `$subtract`. Làm sao phát hiện gateway có clock skew?

### Bài 19 — Java Driver

Tạo `TimeSeriesOptions("measuredAt")`, set `metaField("meta")` và granularity MINUTES; insert một measurement với `new Date()`.

### Bài 20 — So sánh workload

Chọn schema và granularity cho:

1. API latency mỗi giây, query 15 phút.
2. Công tơ điện mỗi 5 phút, query 7 ngày.
3. KPI tổng hợp mỗi 12 giờ, query theo quý.

Giải thích thêm retention, index và metadata.

## 28. Quy trình chọn thiết kế theo từng bước

### Bước 1 — Xác định measurement là gì

Là raw event hay bản tổng hợp 5 phút? Không trộn nhiều đơn vị đo với cadence/retention rất khác nhau nếu gây khó chọn granularity.

### Bước 2 — Chọn event time

Timestamp biểu diễn khi phép đo xảy ra hay khi hệ thống nhận? Nếu cần cả hai, lưu riêng.

### Bước 3 — Định nghĩa một series

Ví dụ:

~~~text
tenantId + sensorId + metricType
~~~

Các field này nên ổn định qua nhiều measurements.

### Bước 4 — Loại dynamic fields khỏi meta

Đưa batteryPct, requestId, measured value, status biến động ra khỏi metadata.

### Bước 5 — Đo khoảng giữa các measurements cùng series

Không lấy tổng insert/s làm proxy duy nhất.

### Bước 6 — Chọn granularity và TTL

Seconds/minutes/hours hoặc custom 6.3+; cân nhắc query intervals và retention.

### Bước 7 — Thiết kế index

Meta equality + time range, kiểm tra defaults trên server version và thử explain.

### Bước 8 — Kiểm tra giới hạn collection

Nếu cần unique index/transaction writes/change streams hoặc sửa measurements thường xuyên, xem lại loại collection.

### Bước 9 — Thử dữ liệu đại diện

Đo read latency, storage, bucket density và late events trên dataset đủ lớn.

### Bước 10 — Khóa schema trước production

timeField/metaField không đổi được sau tạo, cần migration plan nếu sai.

## 29. Checklist production

### Tính đúng dữ liệu

- [ ] timeField bắt buộc và có BSON Date ở mọi measurement.
- [ ] Event time khác ingest time được phân biệt rõ.
- [ ] UTC/timezone được chuẩn hóa.
- [ ] Clock skew và future timestamps có xử lý.
- [ ] metaField đại diện đúng series.
- [ ] Không đưa requestId, batteryPct, giá trị đo vào meta.
- [ ] Kiểu và cấu trúc meta thống nhất giữa các writers.
- [ ] Không dùng object equality toàn bộ meta khi query subfields phù hợp hơn.
- [ ] Không lặp dữ liệu nhạy cảm không cần thiết trong meta.
- [ ] Query có filter tenant từ quyền người dùng.

### Granularity và vận hành

- [ ] Granularity dựa trên nhịp cùng meta, không chỉ insert rate.
- [ ] Biết bucket spans 1h/24h/30d.
- [ ] Không nhầm span với rounding Date hoặc aggregation bins.
- [ ] Cặp custom 6.3+ bằng nhau và không dùng cùng granularity.
- [ ] Hiểu chỉ tăng bucket span bằng collMod.
- [ ] Đã đánh giá TTL xóa theo buckets.
- [ ] Có index cho meta equality và time range.
- [ ] Đã đo dữ liệu out-of-order và high-cardinality.
- [ ] Có monitoring storage, CPU/RAM/I/O, latency.
- [ ] Có test trên MongoDB version/FCV tương ứng.

### Hạn chế và bảo trì

- [ ] Không dựa vào unique indexes trên time series.
- [ ] Không giả định default _id index.
- [ ] Có cơ chế dedup/idempotency khi retry ingest.
- [ ] Không viết vào time series trong transaction.
- [ ] Không sửa buckets nội bộ trực tiếp.
- [ ] Có kế hoạch migrate nếu đổi timeField/metaField.
- [ ] Sharding, nếu dùng, theo các field/version được phép.
- [ ] Đã cân nhắc tách ordinary device registry và time series history.
- [ ] Đã chạy staging load test với dữ liệu đại diện.

## 30. Tổng kết

Thiết kế time series collection không chỉ là tạo ba dòng cấu hình.

- **`timeField`** phải là BSON Date đúng thời điểm nghiệp vụ. Lưu event time nhất quán và tách ingestion time nếu cần.
- **`metaField`** là nhãn nhận diện series, nên ổn định và phù hợp filter. Dynamic metadata làm tăng số buckets thưa.
- **`granularity`** được chọn theo nhịp của **từng series**. Seconds/minutes/hours tương ứng bucket span tối đa 1 giờ, 24 giờ và 30 ngày — không phải làm tròn measurements.
- **Custom bucketing** từ MongoDB 6.3 cho phép chỉ định khoảng bucket cụ thể bằng hai parameters bằng nhau.
- **Thay đổi sau tạo** có giới hạn: không thể đổi tên timeField/metaField, chỉ tăng bucket span bằng collMod ở các version hỗ trợ.
- **Truy vấn thực tế** vẫn cần filter metadata, range thời gian, index phù hợp, và aggregation khi muốn nhóm theo khung 5 phút/giờ/ngày.
- **Vận hành** cần xem TTL xóa theo bucket, late events, cardinality và những hạn chế độc lập của time series collection.

Một schema tốt giúp phép đo có đúng trục thời gian, đúng danh tính nguồn, nhóm được dữ liệu có tương quan vào buckets hiệu quả, và giữ chi phí query/storage phù hợp khi dữ liệu tăng dài hạn.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB Manual — About Time Series Data](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/)
- [MongoDB Manual — Time Series Considerations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-considerations/)
- [MongoDB Manual — Best Practices for Time Series](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/)
- [MongoDB Manual — Set Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/)
- [MongoDB Manual — Time Series Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Java Sync Driver — Time Series Collections](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/time-series/)
