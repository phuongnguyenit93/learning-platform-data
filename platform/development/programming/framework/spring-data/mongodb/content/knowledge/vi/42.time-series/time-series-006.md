# Truy vấn khoảng thời gian và aggregation báo cáo

> **Chương:** Time series  
> **Module:** `SPRING_DATA_MONGODB`  
> **Ngôn ngữ:** Tiếng Việt

Hãy tưởng tượng một dịch vụ IoT lưu nhiệt độ do hàng nghìn cảm biến gửi mỗi phút. Người dùng cần xem “nhiệt độ trung bình của thiết bị S-01 trong giờ 09:00–10:00”, “giá trị thấp nhất, cao nhất theo mỗi 15 phút”, hoặc “số bản ghi đo theo ngày tại một chi nhánh”. Những câu hỏi này là sự kết hợp giữa **truy vấn khoảng thời gian** và **aggregation báo cáo** trên dữ liệu time series.

Trong MongoDB, **time-series collection** cung cấp cách tổ chức và tối ưu việc lưu nhiều phép đo có timestamp và metadata. Trong Spring Data MongoDB, ta vẫn có thể thao tác qua `MongoTemplate`, repository và aggregation pipeline; tuy nhiên phải hiểu sự khác nhau giữa **thời gian đo**, **thời gian nhận**, **múi giờ trình bày**, **cửa sổ thời gian** và **bucket lưu trữ nội bộ**. Lỗi chỉ lệch một dấu `<=` so với `<`, hoặc lấy trung bình các giá trị trung bình mà không xét số mẫu, có thể làm báo cáo sai dù code chạy thành công.

Bài này thuộc module `SPRING_DATA_MONGODB`: kết nối và ánh xạ document, dùng `MongoTemplate` hoặc repository để truy vấn, aggregation, index, transaction, reactive access, kiểm thử và phân tích hiệu năng. Chủ đề trực tiếp là **lọc theo khoảng thời gian và thiết kế báo cáo aggregation đúng ngữ nghĩa**; phần tạo collection và vận hành chỉ phục vụ chủ đề đó.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô hình hóa phép đo với `timeField` kiểu BSON Date, `metaField` và các trường số liệu.
2. Dùng `Instant`/`Date` trong Java, phân biệt múi giờ của người dùng với thời điểm UTC được lưu.
3. Viết bộ lọc khoảng **nửa mở** `[startInclusive, endExclusive)` kết hợp tenant/device/quality.
4. Tránh lỗi đếm trùng khi ghép các khoảng ngày/giờ liền nhau và lỗi “mất ngày cuối”.
5. Xây pipeline `$match` → `$group` với `$dateTrunc` → `$sort` → `$project` để tính `count`, `sum`, `avg`, `min`, `max`.
6. Dùng `MongoTemplate.aggregate(...)` với `Aggregation`/`Criteria` và các stages BSON khi DSL chưa bộc lộ đầy đủ operator của server.
7. Phân biệt storage buckets (MongoDB quản lý) với **reporting buckets** (ví dụ 15 phút do `$dateTrunc` tạo).
8. Tính average đúng khi tổng hợp nhiều bucket, xử lý khoảng trống, phép đo null, late arrivals và duplicate.
9. Thiết kế báo cáo theo múi giờ địa phương, kể cả thay đổi daylight saving time (DST).
10. Kiểm thử bằng MongoDB thật: BSON `Date`, boundary, tenant isolation, expected numbers và thứ tự buckets.
11. Phân tích explain/index/retention, đo hiệu năng và quyết định khi nào cần rollup/pre-aggregation.

## 2. Time-series collection lưu những gì?

Ví dụ một phép đo:

```javascript
{
  _id: ObjectId("..."),
  measuredAt: ISODate("2026-11-20T09:02:00Z"),
  meta: {
    tenantId: "TENANT-A",
    deviceId: "S-01",
    sensorType: "temperature",
    unit: "C"
  },
  value: 20.0,
  quality: "OK"
}
```

Các thành phần:

| Field | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `measuredAt` | **Thời điểm đo** / event time | Phải là BSON Date, không phải chuỗi ngày giờ |
| `meta` | Metadata mô tả chuỗi đo | Các phép đo cùng thiết bị/thuộc tính ổn định thường dùng chung metadata |
| `meta.tenantId` | Phân vùng dữ liệu nghiệp vụ | Cần filter/authorization ngay ở query |
| `meta.deviceId` | Định danh nguồn đo | Dùng để lọc hoặc group theo thiết bị |
| `value` | Giá trị đo | Nên có numeric type/đơn vị thống nhất |
| `quality` | Chất lượng quan sát | Có thể lọc `OK` trước khi tính báo cáo |
| `_id` | Định danh phép đo | Không được tự coi là event-time hoặc thứ tự đo chuẩn |

### 2.1. Time field khác thời gian hệ thống nhận dữ liệu

Một cảm biến mất mạng có thể đo lúc 09:02 nhưng chỉ gửi về server lúc 11:30:

```text
Sensor measuredAt: 2026-11-20T09:02:00Z
Server receivedAt: 2026-11-20T11:30:00Z
```

Nếu báo cáo hỏi **nhiệt độ lúc 09:00–10:00**, cần lọc `measuredAt`. Nếu hỏi “bao nhiêu sự kiện được nhận trong giờ qua”, cần trường `receivedAt` riêng và một câu truy vấn khác. Đừng đổi field vì `receivedAt` gần với server clock hơn.

### 2.2. metaField giúp diễn đạt chuỗi và lọc nguồn

Trong time-series collection, metadata có thể là một object. Ví dụ dùng `meta` để chứa `tenantId`, `deviceId` và `sensorType`. Những field này nên tương đối **ổn định trong chuỗi phép đo**, vì thay metadata liên tục có thể giảm hiệu quả tổ chức dữ liệu theo bucket.

**Không đưa timestamp từng lần đo hay request ID ngẫu nhiên vào metaField** chỉ để “cho đầy đủ thông tin”: metadata có cardinality cực cao và thay đổi ở mỗi sample có thể phá lợi ích bucket hóa.

Nếu đơn vị đo thực sự thay đổi từ °C sang °F, đừng trộn hai đơn vị trong cùng phép `$avg`. Nên chuẩn hóa đơn vị khi ingest hoặc tách nhóm theo unit trước khi tính toán.

### 2.3. Storage bucket khác reporting bucket

```text
Logical time-series collection: sensor_measurements
   |
   +-- Document measuredAt=09:02, value=20
   +-- Document measuredAt=09:07, value=22
   +-- Document measuredAt=09:14, value=24
   +-- Document measuredAt=09:16, value=26
   |
   v
MongoDB manages internal compressed storage buckets
   (implementation detail)

Aggregation report:
   [09:00,09:15): 20,22,24 => count 3, avg 22
   [09:15,09:30): 26,... => another reporting bucket
```

**Storage buckets** do MongoDB quản lý dựa vào cấu hình và thuật toán lưu trữ; không ứng dụng nào nên truy vấn trực tiếp `system.buckets.<collection>` để dựng dashboard thông thường. **Reporting buckets** là nhóm thời gian nghiệp vụ (5 phút/15 phút/1 giờ/1 ngày), được tạo bởi aggregation trên **logical collection**.

## 3. Tạo collection thử nghiệm đúng cấu trúc

Trên MongoDB hỗ trợ time-series collections (MongoDB 5.0 trở lên; tập tính năng và giới hạn thay đổi theo phiên bản), có thể tạo:

```javascript
// Chỉ chạy trên database TEST hoặc theo migration có phê duyệt.
db.createCollection("sensor_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  }
})
```

Đây là cách tạo **logical time-series collection** với các field do ứng dụng định nghĩa. MongoDB xử lý cách lưu dữ liệu bên trong; `granularity:"seconds"` là gợi ý tổ chức lưu trữ, **không** có nghĩa mọi phép đo sẽ bị làm tròn đến giây, hoặc báo cáo mặc định group theo giây.

### 3.1. Kiểm tra collection options

```javascript
db.getCollectionInfos({ name: "sensor_measurements" })
```

Hãy xác minh `type`/`options.timeseries` của collection được tạo; không chỉ dựa vào tên collection hoặc annotation trên class Java. Một collection thường có cùng tên và schema bên ngoài vẫn có thể không phải time-series collection.

### 3.2. Tạo bằng Spring Data / MongoDB Java code

Với Spring Data MongoDB, có API `CollectionOptions` cho time series ở các phiên bản tương ứng. Nếu project phải quản lý cấu hình chính xác giữa nhiều major versions, có thể dùng lệnh BSON server **một lần khi migration**:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

// Ví dụ migration/admin code, không gọi mỗi HTTP request.
Document command = new Document("create", "sensor_measurements")
    .append("timeseries",
        new Document("timeField", "measuredAt")
            .append("metaField", "meta")
            .append("granularity", "seconds"));

mongoTemplate.getDb().runCommand(command);
```

`mongoTemplate` là bean `MongoTemplate` đã inject; lệnh sẽ lỗi nếu collection đã tồn tại hoặc tài khoản thiếu quyền. Trong production nên có **migration idempotent** kiểm tra options/đối chiếu schema, không nuốt lỗi rồi giả định collection đúng.

### 3.3. Index và tính năng hỗ trợ theo phiên bản

MongoDB hỗ trợ những kiểu index và cơ chế tối ưu riêng cho time-series collections, thay đổi qua các phiên bản. Đừng bê mọi lệnh quản lý index/unique constraint từ collection thường sang mà không kiểm tra version. Trong bài này, **nền tảng** là truy vấn qua logical collection với `timeField` và `metaField`; hiệu năng/index sẽ bàn ở phần sau.

## 4. Bộ dữ liệu có kết quả tính được bằng tay

Để tránh tạo một báo cáo mà không thể kiểm chứng, dùng một fixture cố định:

```javascript
const metaA = {
  tenantId: "TENANT-A",
  deviceId: "S-01",
  sensorType: "temperature",
  unit: "C"
};
const metaOtherDevice = {
  tenantId: "TENANT-A",
  deviceId: "S-02",
  sensorType: "temperature",
  unit: "C"
};
const metaOtherTenant = {
  tenantId: "TENANT-B",
  deviceId: "S-01",
  sensorType: "temperature",
  unit: "C"
};

db.sensor_measurements.insertMany([
  { measuredAt: ISODate("2026-11-20T09:02:00Z"),
    meta: metaA, value: 20.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:07:00Z"),
    meta: metaA, value: 22.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:14:00Z"),
    meta: metaA, value: 24.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:16:00Z"),
    meta: metaA, value: 26.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:26:00Z"),
    meta: metaA, value: 28.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:32:00Z"),
    meta: metaA, value: 30.0, quality: "OK" },
  { measuredAt: ISODate("2026-11-20T09:46:00Z"),
    meta: metaA, value: 32.0, quality: "OK" },
  // Đúng 10:00 — phải bị loại khỏi [09:00, 10:00).
  { measuredAt: ISODate("2026-11-20T10:00:00Z"),
    meta: metaA, value: 100.0, quality: "OK" },
  // Thiết bị khác cùng tenant — phải bị loại.
  { measuredAt: ISODate("2026-11-20T09:04:00Z"),
    meta: metaOtherDevice, value: 99.0, quality: "OK" },
  // Tenant khác cùng deviceId — phải bị loại.
  { measuredAt: ISODate("2026-11-20T09:08:00Z"),
    meta: metaOtherTenant, value: 888.0, quality: "OK" }
])
```

**Bài toán:** báo cáo device `S-01` thuộc `TENANT-A`, chỉ phép đo `quality="OK"`, từ 09:00 đến **trước** 10:00 UTC ngày 20/11/2026.

Kỳ vọng sau lọc: **7 phép đo**, tổng `182`, trung bình `26.0`. Con số 100 của mốc 10:00, 99 của thiết bị khác và 888 của tenant khác đều **không được** vào báo cáo.

### 4.1. Bảng tính thủ công theo 15 phút

| Reporting bucket UTC | Giá trị | count | sum | avg | min | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `09:00–09:15` | 20, 22, 24 | 3 | 66 | 22 | 20 | 24 |
| `09:15–09:30` | 26, 28 | 2 | 54 | 27 | 26 | 28 |
| `09:30–09:45` | 30 | 1 | 30 | 30 | 30 | 30 |
| `09:45–10:00` | 32 | 1 | 32 | 32 | 32 | 32 |
| **Toàn khoảng** | 7 mẫu | **7** | **182** | **26** | **20** | **32** |

Chúng ta sẽ dùng bảng này để đối chiếu cả mongosh pipeline lẫn Java integration test. Dữ liệu mẫu nhỏ để dễ kiểm tra; cách thiết kế query, group và giới hạn tải phải vẫn hợp lệ với collection lớn.

## 5. Truy vấn khoảng thời gian nửa mở [start, end)

Với time-series report, **nên chuẩn hóa mọi khoảng truy vấn theo quy ước**:

```text
startInclusive <= measuredAt < endExclusive
          [09:00, 10:00)
```

MongoDB:

```javascript
db.sensor_measurements.find({
  "meta.tenantId": "TENANT-A",
  "meta.deviceId": "S-01",
  quality: "OK",
  measuredAt: {
    $gte: ISODate("2026-11-20T09:00:00Z"),
    $lt: ISODate("2026-11-20T10:00:00Z")
  }
})
```

`$gte` nhận cả mẫu tại 09:00:00.000, `$lt` **loại** mẫu đúng 10:00:00.000. Khoảng tiếp theo `[10:00, 11:00)` sẽ nhận mẫu đó. Các khoảng liền nhau **không đếm trùng** cùng một sample ở mốc ranh giới.

### 5.1. Vì sao tránh $lte ở điểm cuối?

Ví dụ ghép hai báo cáo:

```javascript
// Rủi ro đếm trùng sample ở đúng 10:00:00:
{ measuredAt: {
    $gte: ISODate("2026-11-20T09:00:00Z"),
    $lte: ISODate("2026-11-20T10:00:00Z")
}}

{ measuredAt: {
    $gte: ISODate("2026-11-20T10:00:00Z"),
    $lte: ISODate("2026-11-20T11:00:00Z")
}}
```

Khi dùng `$lte`, sample tại 10:00 xuất hiện **hai lần** trong hai cửa sổ. Khi ghép các báo cáo nhiều giờ/ngày, lỗi đếm trùng càng khó phát hiện.

**Quy tắc:** start inclusive, end exclusive cho filter thời gian; với API user nhập “đến hết ngày 20/11”, hãy chuyển thành **đầu ngày 21/11 theo múi giờ đã chọn**, không cố lấy `23:59:59.999` bằng cách trừ millisecond.

### 5.2. Tránh phép so sánh string ngày giờ

Phản ví dụ:

```javascript
// SAI với schema timeField BSON Date:
{ measuredAt: { $gte: "2026-11-20T09:00:00Z" } }
```

Chuỗi có thể được MongoDB so sánh theo **BSON type/string semantics**, không tương đương một `Date`. Với `timeField`, truyền BSON Date thật: `ISODate(...)` trong mongosh, `java.util.Date`/`Instant` được Spring converter xử lý trong Java.

### 5.3. Một số quy ước thời gian cần thống nhất

| Khái niệm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Event time | `measuredAt` | Dùng để lọc/nhóm số liệu theo lúc đo |
| Ingest time | `receivedAt` | Dùng cho độ trễ/lưu lượng nhận |
| UTC instant | `2026-11-20T09:00:00Z` | Chuẩn trao đổi với MongoDB |
| Local wall-clock | `2026-11-20 16:00` ở Việt Nam | Phải có múi giờ để đổi thành instant |
| Reporting range | `[start,end)` | Tránh trùng biên |
| Reporting bucket | `[09:00,09:15)` | Tạo qua `$dateTrunc` |
| Storage bucket | Do MongoDB tự quản lý | Không phải group báo cáo |

### 5.4. Truy vấn không trả dữ liệu

Khi `find` trả danh sách rỗng:

- Có thể thật sự không có phép đo trong khoảng.
- Có thể filter tenant, device, quality không khớp.
- Có thể timestamp nguồn bị lệch múi giờ hoặc không đồng bộ.
- Có thể retention/TTL đã xóa dữ liệu cũ.
- Có thể dữ liệu đến muộn chưa được ingest.
- Có thể đã nhập sai `start/end`.

Không luôn chuyển kết quả rỗng thành “giá trị trung bình = 0”. **Không có mẫu** và **một mẫu bằng 0** là hai tình trạng khác nhau.

## 6. Java: Instant, Date, LocalDate và múi giờ

Trong Java, ưu tiên `Instant` cho một **thời điểm tuyệt đối** và `ZoneId`/`LocalDate` cho lựa chọn ngày theo múi giờ người dùng.

```java
import java.time.Instant;
import java.util.Date;

Instant start = Instant.parse("2026-11-20T09:00:00Z");
Instant end = Instant.parse("2026-11-20T10:00:00Z");

Date bsonStart = Date.from(start);
Date bsonEnd = Date.from(end);
```

`Date.from(Instant)` làm rõ giá trị dùng trong `Criteria` raw. Spring Data cũng có converter cho những Java time types được hỗ trợ; dùng `Instant` trong domain model, nhưng cần kiểm tra serialization với cấu hình converter/version thực tế.

### 6.1. Model Java cho phép đo

File `SensorMeasurement.java`:

```java
package com.example.timeseries;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sensor_measurements")
public record SensorMeasurement(
    @Id String id,
    Instant measuredAt,
    SensorMeta meta,
    double value,
    String quality
) {
    public record SensorMeta(
        String tenantId,
        String deviceId,
        String sensorType,
        String unit
    ) {}
}
```

Kiểu record trên phù hợp khi **một phép đo là immutable fact**. Nếu nguồn có thể gửi một giá trị thiếu/không hợp lệ, đừng ép nó thành `double 0.0` rồi tính average. Dùng chiến lược validation và một nullable type như `Double` khi nghiệp vụ cần phân biệt “không có đo” với “đã đo được 0”.

### 6.2. Query bằng MongoTemplate

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class MeasurementRangeReader {

    private final MongoTemplate template;

    public MeasurementRangeReader(MongoTemplate template) {
        this.template = template;
    }

    public List<SensorMeasurement> read(
            String permittedTenantId,
            String deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu tenant hoặc device");
        }
        if (startInclusive == null || endExclusive == null
                || !startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                "Khoảng thời gian không hợp lệ");
        }

        Criteria predicate = Criteria
            .where("meta.tenantId").is(permittedTenantId)
            .and("meta.deviceId").is(deviceId)
            .and("quality").is("OK")
            .and("measuredAt")
                .gte(Date.from(startInclusive))
                .lt(Date.from(endExclusive));

        return template.find(
            new Query(predicate),
            SensorMeasurement.class);
    }
}
```

Trong production nên bổ sung **giới hạn độ rộng khoảng thời gian**, giới hạn số kết quả, pagination/streaming cho truy vấn lấy raw samples và authorization từ security context. Hàm minh họa cách biểu diễn filter đúng, không khuyến khích trả hàng triệu phép đo thành một `List` trên HTTP.

### 6.3. Query bằng repository

Trong trường hợp tên method vẫn rõ nghĩa:

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SensorMeasurementRepository
        extends MongoRepository<SensorMeasurement, String> {

    List<SensorMeasurement>
        findByMetaTenantIdAndMetaDeviceIdAndMeasuredAtGreaterThanEqualAndMeasuredAtLessThan(
            String tenantId,
            String deviceId,
            Instant start,
            Instant end);
}
```

Đây là **derived query** với property path `meta.tenantId`/`meta.deviceId` và hai ranh giới. Nếu business query còn có `quality`, sensorType, permission, projection và nhiều khoảng lựa chọn, một custom repository/template thường **dễ kiểm soát và review hơn** tên method quá dài. Derived method ở trên cũng chưa lọc `quality="OK"`, nên **không tương đương hoàn toàn** với `MeasurementRangeReader.read` ở mục trước.

### 6.4. Không lạm dụng LocalDateTime cho event time

`LocalDateTime` **không chứa timezone/offset**. Ví dụ `2026-11-20T09:00` không tự biết là 09:00 UTC hay 09:00 giờ Hồ Chí Minh. Nếu dùng làm boundary mà không gắn `ZoneId`, code có thể truy vấn sai 7 giờ hoặc sai vào kỳ DST.

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate localDay = LocalDate.of(2026, 11, 20);

Instant startUtc = localDay
    .atStartOfDay(vietnam)
    .toInstant();
Instant endUtc = localDay.plusDays(1)
    .atStartOfDay(vietnam)
    .toInstant();
```

Ngày 20/11/2026 ở múi giờ Việt Nam bắt đầu tại **2026-11-19T17:00:00Z** và kết thúc ngay trước **2026-11-20T17:00:00Z**. Khoảng local day này **không** giống `[2026-11-20T00:00Z, 2026-11-21T00:00Z)`.

### 6.5. Ngày DST có thể dài 23 hoặc 25 giờ

Với múi giờ có daylight saving time, một ngày địa phương không luôn dài đúng 24 giờ. Đừng tính:

```java
// PHẢN VÍ DỤ khi yêu cầu một ngày local có DST.
Instant end = start.plus(24, ChronoUnit.HOURS);
```

Thay bằng `localDay.plusDays(1).atStartOfDay(zone).toInstant()` để end đúng với lịch địa phương. Đồng thời khi group theo ngày dùng chính `timezone` trong `$dateTrunc` để bucket boundaries thống nhất với phạm vi query.

## 7. Aggregation: từ range query đến bảng báo cáo

Một pipeline tốt cho mục tiêu “theo 15 phút”:

```text
sensor_measurements (logical time-series collection)
           |
           v
$match  meta.tenantId, meta.deviceId, quality, measuredAt range
           |
           v
$group  _id = $dateTrunc(measuredAt, minute, binSize=15, UTC)
        count = $sum(1)
        sumValue = $sum(value)
        avgValue = $avg(value)
        minValue = $min(value)
        maxValue = $max(value)
           |
           v
$sort   _id ascending
           |
           v
$project bucketStart, count, sum, avg, min, max
           |
           v
4 rows for the hour
```

**Thứ tự stages có ý nghĩa**: lọc tenant/device/time sớm để giảm số phép đo đi vào group; group trước rồi sort các nhóm; project chỉ field cần thiết. Tránh sort hàng triệu raw documents khi báo cáo chỉ cần sort vài chục reporting buckets.

### 7.1. $match đứng sớm

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    "meta.deviceId": "S-01",
    quality: "OK",
    measuredAt: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  }
}
```

Nó giúp server có cơ hội dùng metadata/time predicates để chọn buckets cần đọc. Đừng biến predicate đơn giản thành `$expr` phức tạp rồi mong query planner chắc chắn đẩy nó xuống tầng bucket.

### 7.2. $dateTrunc tạo bucket 15 phút

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
```

Với `09:02`, `09:07` và `09:14`, kết quả đều là `09:00`; `09:16` và `09:26` thành `09:15`. `$dateTrunc` tạo mốc **đầu reporting bucket** dưới dạng BSON Date, không biến `measuredAt` của từng sample trong collection.

`$dateTrunc` có từ MongoDB 5.0. Nếu backend dùng phiên bản cũ hơn, phải có cách group khác phù hợp hoặc nâng server; không copy pipeline rồi kỳ vọng DB 4.4 hiểu operator này.

### 7.3. $group và accumulator

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$measuredAt",
        unit: "minute",
        binSize: 15,
        timezone: "UTC"
      }
    },
    samples: { $sum: 1 },
    sumValue: { $sum: "$value" },
    avgValue: { $avg: "$value" },
    minValue: { $min: "$value" },
    maxValue: { $max: "$value" }
  }
}
```

`$sum:1` đếm **documents thỏa `$match`**. Nếu `value` là null/missing/non-numeric, `$avg` và `$sum:"$value"` có quy tắc riêng khi xử lý; số mẫu đếm document không nhất thiết bằng số giá trị số hợp lệ. Nếu muốn `count` là số phép đo hợp lệ, hãy lọc/chuẩn hóa dữ liệu **trước** group hoặc tính một accumulator riêng.

Trong fixture, mọi `value` đều là số và mọi record chọn đều `quality="OK"`, nên `samples=7` cũng là số phép đo hợp lệ.

### 7.4. $sort sau group

```javascript
{ $sort: { _id: 1 } }
```

`$group` không bảo đảm thứ tự phát ra của các buckets. Nếu biểu đồ cần 09:00, 09:15, 09:30, 09:45, phải dùng `$sort` theo bucket timestamp. Không dựa vào thứ tự tự nhiên hay thứ tự BSON insertion.

### 7.5. $project tạo tên dễ hiểu

```javascript
{
  $project: {
    _id: 0,
    bucketStart: "$_id",
    samples: 1,
    sumValue: 1,
    avgValue: 1,
    minValue: 1,
    maxValue: 1
  }
}
```

Giữ bucket timestamp kiểu `Date`. Chỉ khi trình bày frontend mới định dạng thành `"09:00"`. Nếu biến thời gian thành chuỗi quá sớm, có thể mất timezone context hoặc làm việc sort/compare về sau khó hơn.

## 8. Pipeline hoàn chỉnh trong mongosh

Ghép các stages:

```javascript
db.sensor_measurements.aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      quality: "OK",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      avgValue: { $avg: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      bucketStart: "$_id",
      samples: 1,
      sumValue: 1,
      avgValue: 1,
      minValue: 1,
      maxValue: 1
    }
  }
])
```

Kỳ vọng từ fixture:

```javascript
[
  {
    bucketStart: ISODate("2026-11-20T09:00:00Z"),
    samples: 3, sumValue: 66, avgValue: 22,
    minValue: 20, maxValue: 24
  },
  {
    bucketStart: ISODate("2026-11-20T09:15:00Z"),
    samples: 2, sumValue: 54, avgValue: 27,
    minValue: 26, maxValue: 28
  },
  {
    bucketStart: ISODate("2026-11-20T09:30:00Z"),
    samples: 1, sumValue: 30, avgValue: 30,
    minValue: 30, maxValue: 30
  },
  {
    bucketStart: ISODate("2026-11-20T09:45:00Z"),
    samples: 1, sumValue: 32, avgValue: 32,
    minValue: 32, maxValue: 32
  }
]
```

Đây là **expected result** theo dữ liệu mẫu, không phải output được chạy trực tiếp trong phiên viết bài. Tùy server, số nguyên/`double`/`Decimal128` trong BSON có thể hiển thị khác cách viết trên, nhưng **giá trị và bucket boundaries** phải đúng.

### 8.1. Không tự thêm $limit trước group

Sai mục đích báo cáo:

```javascript
[
  { $match: { /* time + tenant filter */ } },
  { $limit: 100 },
  { $group: { _id: "...", avgValue: { $avg: "$value" } } }
]
```

`$limit:100` trước `$group` chỉ tổng hợp tối đa 100 **sample đầu tiên của pipeline**; nó không còn là thống kê toàn khoảng. Nếu UI chỉ muốn 20 reporting buckets, dùng `$limit` **sau** group/sort và ghi rõ các trang/buckets được hiển thị. Khi giới hạn trả về bằng API, phải phân biệt **giảm tải kết quả trả về** với **thay đổi tập dữ liệu được tính**.

### 8.2. Không lấy average của một subset mà đặt tên “toàn giờ”

Nếu có filter `quality:"OK"`, average phản ánh **các phép đo có chất lượng OK**, không phải toàn bộ raw events. Nếu hệ thống cũng lưu `quality:"INVALID"` hoặc `value:null`, báo cáo phải nêu rõ mẫu nào bị loại và mẫu nào tham gia accumulator.

### 8.3. Giải thích tại sao 09:14 thuộc bucket 09:00

Với `unit:"minute"`, `binSize:15`, các khoảng:

```text
[09:00:00.000, 09:15:00.000)
[09:15:00.000, 09:30:00.000)
[09:30:00.000, 09:45:00.000)
[09:45:00.000, 10:00:00.000)
```

Mẫu 09:14:59.999 thuộc bucket 09:00. Mẫu 09:15:00.000 thuộc bucket 09:15. Quy tắc nhất quán giữa filter `$gte/$lt` và `$dateTrunc` giúp ghép báo cáo mà không đếm trùng.

## 9. Java Spring Data: Aggregation với MongoTemplate

Spring Data có DSL `Aggregation`, `Aggregation.match(...)` và các phép toán grouping/projection. Với biểu thức BSON hiện đại như `$dateTrunc`, có thể tạo một `AggregationOperation` bằng lambda trả về `Document`: cách này thường giảm phụ thuộc vào việc version hiện tại có DSL wrapper cho từng operator hay không.

### 9.1. DTO kết quả

File `TemperatureBucket.java`:

```java
package com.example.timeseries;

import java.time.Instant;

public record TemperatureBucket(
    Instant bucketStart,
    long samples,
    double sumValue,
    double avgValue,
    double minValue,
    double maxValue
) {}
```

Một `TemperatureBucket` đại diện cho **báo cáo trong một bucket 15 phút**, không phải một document phép đo nguồn. Nó cố ý không mang `_id` MongoDB của raw sample.

### 9.2. Service xây aggregation

File `TemperatureReportService.java`:

```java
package com.example.timeseries;

import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

public final class TemperatureReportService {

    private final MongoTemplate template;

    public TemperatureReportService(MongoTemplate template) {
        this.template = template;
    }

    public List<TemperatureBucket> report15Minutes(
            String permittedTenantId,
            String deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        validate(
            permittedTenantId, deviceId,
            startInclusive, endExclusive);

        Criteria match = Criteria
            .where("meta.tenantId").is(permittedTenantId)
            .and("meta.deviceId").is(deviceId)
            .and("meta.sensorType").is("temperature")
            .and("meta.unit").is("C")
            .and("quality").is("OK")
            .and("measuredAt")
                .gte(Date.from(startInclusive))
                .lt(Date.from(endExclusive));

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(match),
            context -> groupBy15MinuteUtc(),
            context -> new Document("$sort",
                new Document("_id", 1)),
            context -> new Document("$project",
                new Document("_id", 0)
                    .append("bucketStart", "$_id")
                    .append("samples", 1)
                    .append("sumValue", 1)
                    .append("avgValue", 1)
                    .append("minValue", 1)
                    .append("maxValue", 1))
        );

        AggregationResults<Document> rows =
            template.aggregate(
                pipeline,
                "sensor_measurements",
                Document.class);

        return rows.getMappedResults().stream()
            .map(row -> new TemperatureBucket(
                row.getDate("bucketStart").toInstant(),
                asNumber(row, "samples").longValue(),
                asNumber(row, "sumValue").doubleValue(),
                asNumber(row, "avgValue").doubleValue(),
                asNumber(row, "minValue").doubleValue(),
                asNumber(row, "maxValue").doubleValue()))
            .toList();
    }

    private static Document groupBy15MinuteUtc() {
        Document truncate = new Document("$dateTrunc",
            new Document("date", "$measuredAt")
                .append("unit", "minute")
                .append("binSize", 15)
                .append("timezone", "UTC"));

        return new Document("$group",
            new Document("_id", truncate)
                .append("samples", new Document("$sum", 1))
                .append("sumValue",
                    new Document("$sum", "$value"))
                .append("avgValue",
                    new Document("$avg", "$value"))
                .append("minValue",
                    new Document("$min", "$value"))
                .append("maxValue",
                    new Document("$max", "$value")));
    }

    private static Number asNumber(
            Document document, String name) {
        Object raw = document.get(name);
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                "Aggregation field không phải số: " + name);
        }
        return number;
    }

    private static void validate(
            String tenantId,
            String deviceId,
            Instant from,
            Instant to) {
        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant và device bắt buộc");
        }
        if (from == null || to == null
                || !from.isBefore(to)) {
            throw new IllegalArgumentException(
                "Khoảng [from, to) không hợp lệ");
        }
        if (Duration.between(from, to)
                .compareTo(Duration.ofDays(31)) > 0) {
            throw new IllegalArgumentException(
                "Khoảng truy vấn vượt giới hạn 31 ngày");
        }
    }
}
```

**Các điểm cần chú ý:**

- `Aggregation.match(match)` dùng `Criteria`, nên metadata/quality/range được đưa vào pipeline ngay từ đầu.
- `groupBy15MinuteUtc()` trả BSON `Document` mà MongoDB hiểu là một stage `$group`. Vì dùng raw stage, **tên field BSON phải chính xác**: `measuredAt`, `meta.tenantId`, `value`. Nếu Java dùng `@Field` đổi tên field, phải cập nhật raw BSON tương ứng.
- `$dateTrunc` do **MongoDB server** xử lý; không phải lệnh Java tính từng timestamp ở client.
- Mapping từ `Document` sang `TemperatureBucket` là chuyển đổi có kiểm tra Number, tránh giả định `samples` luôn là kiểu `Integer` còn `avgValue` luôn là `Double`.
- Giới hạn 31 ngày là **policy của API minh họa**, không phải giới hạn cố định của MongoDB.
- `permittedTenantId` phải đến từ security/authorization; service không tin một tenant bất kỳ do client tự gửi.
- Với kết quả lớn, đừng `getMappedResults()` toàn bộ rồi trả về nếu không có giới hạn; cân nhắc cursor/streaming API và số buckets được phép.

### 9.3. Vì sao lại dùng raw Document cho $dateTrunc?

Các Spring Data versions có thể cung cấp DSL operators khác nhau. Khi dùng raw `Document`:

```java
context -> new Document("$group",
    new Document("_id",
        new Document("$dateTrunc",
            new Document("date", "$measuredAt")
                .append("unit", "minute")
                .append("binSize", 15))))
```

reviewer nhìn trực tiếp BSON gửi lên MongoDB, nhưng **mất sự bảo vệ từ mapping DSL**. Khi sử dụng raw stages, cần integration test chống lỗi gõ tên field hoặc thay annotation mapping. Nếu phiên bản Spring Data đang dùng có DSL `DateOperators.DateTrunc` tương thích với yêu cầu, có thể chuyển sang DSL để tận dụng type/property mapping; không bắt buộc làm thế chỉ vì tránh mọi `Document`.

### 9.4. Kiểm tra khoảng trống

Service trả **những bucket có ít nhất một phép đo**. Nếu từ 09:15 đến 09:30 không có sample, pipeline `$group` **không tự phát một hàng count 0** cho bucket đó. UI muốn biểu đồ có tất cả bốn mốc thì phải chọn một **missing-data policy** trước khi lấp khoảng.

## 10. Báo cáo đa thiết bị: group khóa kép

Đối với dashboard nhiều thiết bị cùng tenant, cần group cả device và bucket:

```javascript
db.sensor_measurements.aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      },
      quality: "OK"
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        bucketStart: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            binSize: 15,
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      avgValue: { $avg: "$value" }
    }
  },
  {
    $sort: {
      "_id.deviceId": 1,
      "_id.bucketStart": 1
    }
  },
  {
    $project: {
      _id: 0,
      deviceId: "$_id.deviceId",
      bucketStart: "$_id.bucketStart",
      samples: 1,
      sumValue: 1,
      avgValue: 1
    }
  }
])
```

Như vậy S-01 và S-02 không bị gom chung. Nếu group chỉ theo timestamp mà không giữ dimension thiết bị, báo cáo “nhiệt độ trung bình của tất cả thiết bị” có thể có ý nghĩa, nhưng **không còn là mỗi thiết bị**; cần đặt tên đúng theo hợp đồng API.

### 10.1. Vì sao cần có tenant trong filter?

Giả sử cả `TENANT-A` và `TENANT-B` có `deviceId="S-01"`. Nếu chỉ group theo `deviceId` và bucket nhưng không match tenant, pipeline có thể gộp 20°C và 888°C thành số trung bình vô nghĩa, đồng thời làm lộ dữ liệu xuyên tenant. **Tenant filtering phải diễn ra ở MongoDB**, không chỉ lọc các rows đã aggregate về Java.

### 10.2. Không gộp khác đơn vị

Nếu S-01 báo độ C còn S-02 báo độ F, tính `$avg:"$value"` trên hai thiết bị không biểu diễn “nhiệt độ trung bình” đúng. Có hai cách an toàn:

1. Chuẩn hóa về cùng đơn vị trước ingest, ghi rõ unit vào metadata.
2. Filter một unit hoặc group thêm `unit`, convert trước khi tổng hợp cross-unit.

Tương tự, không lấy trung bình nhiệt độ và độ ẩm chỉ vì hai field đều là số.

## 11. Báo cáo theo ngày và múi giờ địa phương

“Báo cáo ngày 20/11” là một yêu cầu **có múi giờ**, không chỉ là thay `unit:"minute"` thành `unit:"day"`.

Nếu dashboard của một chi nhánh dùng múi giờ `Asia/Ho_Chi_Minh`, thời điểm đầu ngày 20/11/2026 tại đây là `2026-11-19T17:00:00Z`. Khi tạo bộ lọc, dùng:

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    measuredAt: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  }
}
```

Rồi group theo **ngày địa phương**:

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$measuredAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    samples: { $sum: 1 },
    averageValue: { $avg: "$value" }
  }
}
```

`$dateTrunc` vẫn trả **BSON Date là một instant UTC** tương ứng với mốc đầu ngày ở timezone đã chọn. Không lấy kết quả `_id` rồi in thẳng thành `YYYY-MM-DD` theo UTC mà bảo đó là ngày Việt Nam; cần định dạng lại theo đúng `ZoneId` của báo cáo.

### 11.1. Cặp query range và timezone phải cùng hợp đồng

| Cách làm | Kết quả |
| --- | --- |
| Filter ngày Việt Nam + `$dateTrunc` timezone Việt Nam | Đúng hợp đồng |
| Filter `00:00Z–00:00Z` + group ngày Việt Nam | Bỏ/nhận sai một phần ngày local |
| Filter ngày Việt Nam + group ngày UTC | Có thể chia một local day thành hai buckets |
| Dùng `Instant.now()` trên từng server để suy local day | Rủi ro clock/timezone lệch và không tái lập |

Một API nên nhận `LocalDate` và một zone policy đáng tin cậy (ví dụ zone của site theo cấu hình), chuyển thành `Instant from/to` một lần ở boundary, rồi truyền zone đó vào aggregation. Tránh mỗi layer tự suy múi giờ.

### 11.2. Mã Java tạo ngày báo cáo

```java
package com.example.timeseries;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public record DailyRange(
    Instant startInclusive,
    Instant endExclusive,
    String timezone
) {
    public static DailyRange of(
            LocalDate day,
            ZoneId reportingZone) {

        if (day == null || reportingZone == null) {
            throw new IllegalArgumentException(
                "Thiếu ngày hoặc timezone");
        }

        return new DailyRange(
            day.atStartOfDay(reportingZone).toInstant(),
            day.plusDays(1)
                .atStartOfDay(reportingZone).toInstant(),
            reportingZone.getId());
    }
}
```

`endExclusive` của ngày hôm sau luôn được tính theo cùng timezone, nên tự giải quyết trường hợp ngày local có 23/25 giờ do DST.

### 11.3. Tuần, tháng và các mốc phân nhóm

`$dateTrunc` còn hỗ trợ `unit:"hour"`, `"week"`, `"month"`, v.v. với những tuỳ chọn tương ứng. Với tuần, `startOfWeek` ảnh hưởng ngày mở đầu tuần; không dựa vào mặc định nếu báo cáo doanh nghiệp bắt đầu từ thứ Hai. Với tháng, dùng **đầu tháng kế tiếp** làm end exclusive; không dùng “ngày thứ 30” hoặc trừ một mili-giây để tìm cuối tháng.

Ví dụ tuần theo thứ Hai:

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

Khi sản phẩm có kỳ tài chính 4-4-5 hoặc kỳ chốt ngoài lịch dương, `$dateTrunc` thông thường có thể không đủ. Cần một **calendar table/configuration** của nghiệp vụ hoặc phép ánh xạ period riêng, không mặc định week/month chuẩn là fiscal period.

### 11.4. Giờ lặp hoặc giờ bị nhảy do DST

Ở múi giờ có DST, một “giờ 01:00” có thể xuất hiện hai lần khi đồng hồ quay lùi, hoặc một giờ local có thể không tồn tại khi đồng hồ tiến. Để tránh biểu đồ gộp nhầm, giữ **bucketStart instant UTC** cùng `timezone`, rồi chuyển sang nhãn local khi hiển thị. Nếu hai buckets có nhãn local giống nhau, phân biệt bằng offset/timezone hoặc ISO timestamp đầy đủ.

Không dùng một chuỗi `"01:00"` duy nhất làm ID bucket trên ngày DST.

## 12. Tính trung bình đúng khi tổng hợp nhiều bucket

Đây là lỗi thống kê quan trọng của báo cáo phân cấp.

Từ fixture:

| Bucket | Số mẫu | Trung bình |
| --- | ---: | ---: |
| `09:00` | 3 | 22 |
| `09:15` | 2 | 27 |
| `09:30` | 1 | 30 |
| `09:45` | 1 | 32 |

Nếu một backend lấy **trung bình của bốn trung bình**:

\[
\frac{22+27+30+32}{4}=27.75
\]

Kết quả **27,75** không phải average của bảy phép đo. Average đúng:

\[
\frac{3\cdot22+2\cdot27+1\cdot30+1\cdot32}{3+2+1+1}
=\frac{182}{7}=26
\]

Muốn roll up từ dữ liệu 15 phút thành số liệu 1 giờ, cần lưu **`sumValue` và `samples`**, rồi tính:

```text
hourSum     = sum(bucket.sumValue)
hourSamples = sum(bucket.samples)
hourAverage = hourSum / hourSamples
```

**Không lấy `avg(bucket.avgValue)`** nếu các buckets có số samples khác nhau.

### 12.1. MongoDB pipeline rollup hai tầng

Nếu báo cáo đầu ra chỉ cần toàn giờ từ raw samples, cách đơn giản nhất là group **trực tiếp** trên dữ liệu nguồn theo giờ. Nhưng khi đã có collection rollup 15 phút, có thể group những rows đó:

```javascript
db.temperature_rollups_15m.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      deviceId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$bucketStart",
          unit: "hour",
          timezone: "UTC"
        }
      },
      samples: { $sum: "$samples" },
      sumValue: { $sum: "$sumValue" },
      minValue: { $min: "$minValue" },
      maxValue: { $max: "$maxValue" }
    }
  },
  {
    $project: {
      _id: 0,
      hourStart: "$_id",
      samples: 1,
      sumValue: 1,
      avgValue: {
        $cond: [
          { $gt: ["$samples", 0] },
          { $divide: ["$sumValue", "$samples"] },
          null
        ]
      },
      minValue: 1,
      maxValue: 1
    }
  }
])
```

Giá trị `$min` và `$max` của các rollups còn giữ được extremum toàn khoảng nếu chúng được tính từ **cùng quần thể mẫu**, nhưng các thống kê khác như percentile, median hoặc standard deviation không thể luôn ghép đơn giản từ một con số aggregate ở mỗi bucket.

### 12.2. Average mẫu khác average theo thời gian

`$avg:"$value"` gán **trọng số bằng nhau cho mỗi sample**. Nếu cảm biến đo lúc 09:00, 09:01 rồi 09:59, average mẫu có thể khác **trung bình theo thời gian** của tín hiệu.

Muốn time-weighted average, cần xác định semantics như:

- Giả định giá trị giữ nguyên từ lần đo trước tới lần đo sau (step function), hay nội suy tuyến tính?
- Khoảng trống bao lâu thì coi là dữ liệu không còn đáng tin?
- Cắt tích phân tại `start/end` thế nào?
- Dữ liệu đến muộn và ngoài thứ tự được xử lý ra sao?

Đừng đổi nhãn `$avg` thành “time-weighted temperature” nếu chưa tích hợp thời lượng. Với telemetries có nhịp lấy mẫu đều và độ trễ nhỏ, sample average có thể xấp xỉ hữu ích; nếu nhịp đo bất thường, phải nêu rõ hạn chế.

### 12.3. Tổng của tốc độ không đồng nghĩa tổng sản lượng

Nếu `value` là lưu lượng `liters/second`, `$sum:"$value"` không tự là tổng liters. Phải nhân với **thời gian hiệu lực** từng sample hoặc dùng đại lượng được ingest là volume per interval. Đơn vị đo phải đi cùng công thức:

```text
Sum of °C samples       -> tổng các giá trị số (không phải năng lượng)
Average °C              -> nhiệt độ trung bình theo mẫu
Sum of liters           -> thể tích nếu mỗi value đã là lượng
Integral of liters/sec  -> thể tích khi có thời lượng tương ứng
```

## 13. Khi không có mẫu: bucket trống và missing-data policy

Một aggregation `$group` thông thường **chỉ tạo bucket có dữ liệu**. Ví dụ nếu S-01 không gửi gì trong `[09:30,09:45)`:

```text
09:00 -> 3 samples
09:15 -> 2 samples
09:30 -> (no row returned)
09:45 -> 1 sample
```

Đừng tự động vẽ một điểm `09:30 = 0°C` rồi tính average; đó là **thông tin không được quan sát**, không phải nhiệt độ bằng 0.

### 13.1. Những chính sách thường gặp

| Policy | Diễn giải | Khi nào hợp lý |
| --- | --- | --- |
| **Null / gap** | Không biết giá trị | Mặc định tốt cho nhiệt độ, telemetry thiếu |
| **Zero fill** | Giả định không có sự kiện tương đương bằng 0 | Chỉ khi số liệu là số lượng sự kiện và định nghĩa nghiệp vụ cho phép |
| **LOCF** | Lấy giá trị gần nhất trước đó | Tín hiệu ổn định ngắn hạn, có giới hạn freshness |
| **Linear interpolation** | Nội suy giữa hai sample | Khi miền dữ liệu cho phép và khoảng trống đủ ngắn |
| **Drop bucket** | Không trả mốc thời gian đó | API trả dữ liệu sparse, frontend tự xử lý |

Điều quan trọng là **ghi metadata về chất lượng**: giá trị đo thật hay giá trị suy diễn, số mẫu, thời gian trống, độ tin cậy. Đừng làm dữ liệu được nội suy trông giống dữ liệu đo thật trong audit hoặc báo cáo quyết định lớn.

### 13.2. $densify và $fill

MongoDB có aggregation stages `$densify` và `$fill` ở các phiên bản hỗ trợ để tạo những mốc thiếu và điền giá trị. Ví dụ ý tưởng:

```text
$match(...range/tenant...)
    -> $group(by bucketStart, avgValue, samples)
    -> $project(bucketStart, avgValue, samples)
    -> $densify(field=bucketStart, step=15 minute, bounds=...)
    -> $fill(avgValue using chosen method)
    -> $sort(bucketStart)
```

Không tự động dùng một stage `$fill` để điền 0 cho mọi thống kê. Tên các field, vị trí `$densify`, cách chọn bounds, partition và phiên bản server phải được kiểm chứng bằng integration test. Nếu chỉ có 96 buckets/ngày theo mỗi thiết bị, ứng dụng cũng có thể sinh một timeline có giới hạn và merge với kết quả sparse, miễn giữ đúng **múi giờ, quyền tenant và missing-data semantics**.

### 13.3. Phân biệt samples=0 với avgValue=null

Một bucket được ứng dụng sinh ra để đủ timeline có thể có:

```json
{
  "bucketStart": "2026-11-20T09:30:00Z",
  "samples": 0,
  "avgValue": null,
  "valueStatus": "NO_DATA"
}
```

Không gán `samples:0, avgValue:0` nếu nhiệt độ 0°C là một giá trị đo hợp lệ. Có thể dùng `observedSamples` và `estimatedValue` riêng khi dashboard cần vừa thấy dữ liệu thực vừa thấy đường nội suy.

## 14. Kiểu dữ liệu số, null và tính nhất quán thống kê

MongoDB aggregation có những quy tắc khi xử lý `int`, `long`, `double`, `Decimal128` và field không phải số. Trước khi tính báo cáo:

1. Quy định `value` là số với đơn vị nhất quán.
2. Dùng validation khi ingest, tránh string `"23.5"` hay boolean `true` trong field đo.
3. Phân biệt null/missing với zero.
4. Quy định cách xử lý `NaN`/`Infinity` trong ứng dụng/driver nếu nguồn bên ngoài có thể tạo chúng.
5. Kiểm tra độ chính xác số học cho lĩnh vực tài chính/đếm năng lượng.

### 14.1. Đếm documents và đếm numeric values

Ví dụ nguồn có:

```javascript
[
  { measuredAt: ISODate("2026-11-20T09:00:00Z"),
    value: 12.5 },
  { measuredAt: ISODate("2026-11-20T09:01:00Z"),
    value: null },
  { measuredAt: ISODate("2026-11-20T09:02:00Z"),
    quality: "INVALID" }
]
```

Nếu `$group` có `count:{$sum:1}`, `avg:{$avg:"$value"}`, count có thể là 3 nhưng average dựa trên ít mẫu numeric hơn. Nếu báo cáo cần tỷ lệ missing, nên tính các chỉ số riêng:

```javascript
{
  $group: {
    _id: "$meta.deviceId",
    documents: { $sum: 1 },
    numericSamples: {
      $sum: {
        $cond: [{ $isNumber: "$value" }, 1, 0]
      }
    },
    avgNumericValue: { $avg: "$value" }
  }
}
```

`$isNumber` là operator MongoDB; cần kiểm tra version server đang dùng. Có thể lọc `quality:"OK"` và numeric validation trước group khi contract yêu cầu báo cáo chỉ những mẫu hợp lệ.

### 14.2. Khi cần độ chính xác số thập phân cao

Với doanh thu/chi phí, dùng **minor units dạng integer/long** hoặc `Decimal128` theo policy, thay vì `double` khi giá trị cần chính xác tuyệt đối. Trong Java, `BigDecimal` và converter tương ứng cần được test round-trip. Với nhiệt độ/telemetry, `double` thường có thể chấp nhận nhưng assert ở test cần **tolerance**, không so chuỗi số floating point quá nhiều chữ số.

### 14.3. AVG có thể null khi không có mẫu hợp lệ

Khi không có numeric sample trong nhóm, `$avg` có thể trả null. Do đó một mapper Java dùng `row.get("avgValue", Number.class)` phải xử lý null theo đúng hợp đồng; đừng gọi `doubleValue()` không kiểm tra với pipeline có thể nhận dữ liệu thiếu.

Service `TemperatureReportService` ở mục 9 được viết cho **fixture đã validated numeric `value` và quality OK**. Nếu áp dụng lên nguồn legacy không sạch, hãy bổ sung field validation/filters và DTO nullable trước khi dùng trên production.

## 15. Tối ưu truy vấn time series: metaField, timeField và index

Time-series collection lưu nội bộ theo dạng bucket nhằm giảm chi phí cho workload phù hợp, nhưng không có nghĩa mọi query tự nhiên sẽ nhanh. Các truy vấn tốt thường có:

- **Khoảng `measuredAt` hữu hạn**.
- **Predicate trên metadata ổn định**, ví dụ tenant/device/sensorType.
- Một số field/numeric accumulators được tính ở server thay vì tải toàn bộ raw samples về Java.
- Projection và reporting bucket resolution tương ứng với nhu cầu hiển thị.

### 15.1. $match có thể giúp pruning buckets

Ví dụ:

```javascript
{
  $match: {
    "meta.tenantId": "TENANT-A",
    "meta.deviceId": "S-01",
    measuredAt: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  }
}
```

MongoDB có thể tận dụng thông tin thời gian và metadata để giới hạn bucket phải đọc. Không chắc tất cả optimizer versions đều push down giống nhau: hãy dùng `explain` và dữ liệu đại diện để kiểm tra.

### 15.2. Index cho filter theo metadata và thời gian

Ứng viên cần đánh giá trên version MongoDB đang dùng:

```javascript
db.sensor_measurements.createIndex(
  {
    "meta.tenantId": 1,
    "meta.deviceId": 1,
    measuredAt: 1
  },
  { name: "idx_tenant_device_measured_at" }
)
```

Index này có ý định hỗ trợ equality predicates trên metadata và range trên `measuredAt`. Tuy nhiên:

1. Time-series collections có **quy tắc index riêng và thay đổi theo MongoDB version**, một số index types/options không được hỗ trợ hoặc có hạn chế.
2. Không tự cho rằng index vừa tạo là index được chọn trong planner.
3. Nếu query chủ yếu theo toàn tenant và thời gian mà không có deviceId, thứ tự trường index có thể cần khác.
4. Index tăng chi phí ghi/storage; chọn theo workload thực.
5. MongoDB một số phiên bản tạo index mặc định liên quan tới meta/time; kiểm tra `getIndexes()` để tránh tạo trùng không cần thiết.

**Không tuyên bố hỗ trợ unique index trên time-series collection giống collection thường.** Nếu cần bảo đảm eventId không trùng, hãy kiểm tra các ràng buộc version cụ thể và cân nhắc dedupe/inbox ở nguồn khác phù hợp.

### 15.3. Explain bằng truy vấn thật

```javascript
db.sensor_measurements.explain("executionStats").aggregate([
  {
    $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 }
    }
  }
])
```

Các tín hiệu cần so sánh:

| Tín hiệu | Đánh giá |
| --- | --- |
| `totalKeysExamined` | Lượng index keys truy cập |
| `totalDocsExamined` | Chi phí đọc document/buckets theo cách server trình bày |
| `executionTimeMillis` | Thời gian thực thi ước tính trong explain |
| Index được chọn | Có đúng workload/filter không? |
| Bucket unpack/optimizer stages | Có phải unpack quá nhiều measurements không? |
| Sort/group memory | Có vượt memory thresholds hoặc spill ra disk không? |
| Query range/radius thời gian | 1 giờ, 1 ngày, 90 ngày có chênh khác thế nào? |

Tên/định dạng stage trong `explain()` có thể thay đổi theo phiên bản MongoDB và query execution engine. Không viết một test chỉ grep một stage name cố định rồi coi đó là xác minh hiệu năng qua các upgrades.

### 15.4. Tránh lấy toàn bộ raw data về ứng dụng chỉ để tính AVG

Phản ví dụ:

```java
List<SensorMeasurement> all =
    template.find(new Query(), SensorMeasurement.class);

double average = all.stream()
    .mapToDouble(SensorMeasurement::value)
    .average().orElse(Double.NaN);
```

Đây là anti-pattern cho collection time series lớn: không filter, tải toàn bộ data, chiếm heap và truyền mạng. Hãy đẩy filter/group vào MongoDB; nếu cần raw samples thật, phải giới hạn range/records, pagination/streaming hoặc async job.

### 15.5. Nhiều reporting buckets vẫn có thể quá lớn

Một ngày group theo giây = 86.400 buckets **trên mỗi device**. Với 10.000 devices, số nhóm có thể tăng rất lớn. Không mặc định “aggregation chỉ trả group nhỏ”:

- Chọn resolution theo UI: 1 phút, 15 phút, 1 giờ, 1 ngày.
- Giới hạn số thiết bị và khoảng thời gian.
- Dùng rollup/pre-aggregation khi dashboard đọc cùng một giai đoạn lặp lại.
- Giới hạn số nhóm/trang và phân loại query realtime vs batch.
- Theo dõi spill/memory, CPU, latency theo kích thước phạm vi.

## 16. Báo cáo tuần/tháng: khi nào dùng rollup (pre-aggregation)?

Nếu người dùng xem dashboard 15 phút mỗi vài giây nhưng raw collection có hàng tỷ phép đo, chạy cùng một pipeline mỗi lần có thể tốn nhiều CPU/I/O.

Một cách là tạo một collection **rollup thường** chứa:

```javascript
{
  tenantId: "TENANT-A",
  deviceId: "S-01",
  bucketStart: ISODate("2026-11-20T09:00:00Z"),
  granularityMinutes: 15,
  samples: NumberLong(3),
  sumValue: 66.0,
  minValue: 20.0,
  maxValue: 24.0,
  computedAt: ISODate("2026-11-20T10:05:00Z")
}
```

Sau đó, dashboard đọc rollups 15 phút thay vì luôn quét raw samples.

### 16.1. Giữ count/sum thay vì chỉ avg

Mỗi rollup cần ít nhất:

- `samples`: số mẫu hợp lệ theo policy.
- `sumValue`: tổng để tái tính weighted average.
- `minValue`/`maxValue` nếu cần extreme.
- `bucketStart`, `tenantId`, `deviceId`, unit, resolution.
- Metadata `computedAt`/`sourceRange`/data freshness khi cần.

Nếu chỉ lưu `avgValue` mà mất `samples`, không thể tổng hợp đúng giờ/ngày khi các buckets có nhiều số lượng mẫu khác nhau.

### 16.2. Dùng $merge vào collection rollup thường

Khi tính ra một tập bucket có identity rõ, có thể thiết kế pipeline kết thúc bằng `$merge` sang **một collection thường** dành cho báo cáo:

```javascript
// Minimized example: stages computing a 15-minute rollup
db.sensor_measurements.aggregate([
  { $match: {
      "meta.tenantId": "TENANT-A",
      "meta.deviceId": "S-01",
      "meta.sensorType": "temperature",
      "meta.unit": "C",
      quality: "OK",
      measuredAt: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
  }},
  { $group: {
      _id: {
        bucketStart: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute", binSize: 15, timezone: "UTC"
          }
        },
        tenantId: "$meta.tenantId",
        deviceId: "$meta.deviceId"
      },
      samples: { $sum: 1 },
      sumValue: { $sum: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
  }},
  { $project: {
      _id: 0,
      tenantId: "$_id.tenantId",
      deviceId: "$_id.deviceId",
      bucketStart: "$_id.bucketStart",
      samples: 1,
      sumValue: 1,
      minValue: 1,
      maxValue: 1
  }},
  { $merge: {
      into: "temperature_rollups_15m",
      on: ["tenantId", "deviceId", "bucketStart"],
      whenMatched: "replace",
      whenNotMatched: "insert"
  }}
])
```

Để dùng `$merge.on` với các field không phải `_id`, collection **đích** phải có **unique index phù hợp** theo yêu cầu của MongoDB và các điều kiện hỗ trợ tương ứng. Tạo index trên **collection rollup thường** và dùng cùng định dạng `Date`/keys trước khi chạy pipeline.

```javascript
db.temperature_rollups_15m.createIndex(
  { tenantId: 1, deviceId: 1, bucketStart: 1 },
  { unique: true, name: "uq_rollup_identity" }
)
```

**Cảnh báo:** `$merge` là một **write stage**, không phải chỉ đọc/trả kết quả báo cáo. Cần quyền ghi và review tác động; không cho client gọi một aggregation có `$merge` tùy ý. Không dùng cùng một pipeline `$merge` khi backend đang chỉ mong trả `List<TemperatureBucket>` ở API đọc.

### 16.3. Một rollup có thể bị stale

Sensor đo lúc 09:03 nhưng mất mạng và đến lúc 11:00 mới gửi phép đo. Nếu job rollup 09:00 chạy lúc 10:05 rồi không bao giờ chạy lại, `samples`/`sumValue` của bucket đó bị **thiếu**.

Cần có một chiến lược:

1. **Allowed lateness:** chờ N phút/giờ trước khi chốt bucket.
2. **Recompute overlap:** mỗi lần job chạy tính lại cửa sổ gần đây, ví dụ 24 giờ.
3. **Correction event:** khi late data ảnh hưởng bucket đã công bố, phát update tới read model/cache.
4. **Backfill:** khi dữ liệu đến rất muộn, thực hiện batch job có tracking và kiểm chứng.
5. **Freshness metadata:** công khai báo cáo đã chốt hay còn có thể điều chỉnh.

Thời gian lateness là policy nghiệp vụ/dữ liệu nguồn, không phải tham số thời gian bucket mà MongoDB tự quyết định.

### 16.4. Idempotent rollup không có nghĩa idempotent ingestion

`whenMatched:"replace"` giúp job tính lại cùng một bucket mà không tự tạo nhiều bản rollup với cùng key, **nếu** unique identity được bảo vệ đúng. Nhưng nếu raw collection đã có **duplicate samples**, phép `$group` vẫn đếm duplicate. Cần cơ chế dedupe theo eventId/unique business key ở pipeline ingest hoặc nguồn thích hợp.

Đừng đồng nhất “chạy lại aggregation không làm tăng số rollup rows” với “mọi giá trị báo cáo đều đúng”.

## 17. Late arrivals, out-of-order events và duplicate

Time-series collection thường nhận phép đo theo thời gian, nhưng không có nghĩa tất cả dữ liệu luôn đến theo thứ tự `measuredAt`. Một nhà máy có gateway offline, gửi lại batch cũ trong khi các thiết bị khác tiếp tục gửi realtime.

### 17.1. Timestamp phải là event time đáng tin cậy

Một timestamp không hợp lệ do thiết bị chạy sai đồng hồ có thể đẩy sample sang ngày khác. Khi ingest cần:

- Xác minh timestamp nằm trong khoảng chấp nhận được so với server receipt.
- Ghi `receivedAt`/`clockSkewEstimate` khi cần.
- Từ chối, cách ly hoặc gắn cờ những thời điểm “tương lai xa”/quá cũ.
- Cho phép dữ liệu hợp lệ đến muộn nhưng có chính sách cập nhật báo cáo.

Không tự thay mọi `measuredAt` bằng `Instant.now()` chỉ để dữ liệu “đẹp”: nó làm mất thông tin thời điểm đo thật.

### 17.2. Duplicate theo nguồn đo

Một thiết bị retry HTTP có thể gửi cùng sample hai lần. Nếu mỗi request tạo một MongoDB document mới, báo cáo:

```text
value 20 at 09:02 (original)
value 20 at 09:02 (retry duplicate)
```

sẽ đếm thành hai samples. Nếu cần dedupe, mỗi measurement phải có **eventId/sequence ổn định từ nguồn** và một cơ chế kiểm soát duplicate phù hợp với hạn chế time-series collection/version. Một `_id` mới cho mỗi retry không giúp nhận diện cùng một phép đo.

### 17.3. Out-of-order không giống duplicate

```text
received 10:03 -> measuredAt 10:00, event A
received 10:04 -> measuredAt 09:55, event B
```

Hai mẫu không trùng, chỉ đến không theo event time. Nếu cả hai hợp lệ, aggregation theo `measuredAt` sẽ đưa B về bucket 09:45–10:00 và A về 10:00–10:15. Nhưng rollup đã tính trước 10:04 phải được refresh để nhìn thấy B.

### 17.4. TTL/retention làm thay đổi độ đầy đủ của báo cáo

Time-series collections có thể cấu hình thời hạn hết hạn dữ liệu, ví dụ `expireAfterSeconds`, với các quy tắc cleanup dựa trên thời gian/bucket. Xóa do TTL là quá trình **không tức thì** và không phải đồng hồ chính xác đến từng millisecond. Nếu báo cáo hỏi dữ liệu 90 ngày nhưng retention chỉ 30 ngày, kết quả có thể thiếu hoặc rỗng.

Không xem `count=0` của một khoảng cũ là bằng chứng thiết bị không hoạt động nếu raw data đã hết hạn. Cần định nghĩa:

```text
rawRetention = 30 days
rollupRetention = 12 months
businessReportCoverage = measured and published separately
```

Nếu còn rollups sau khi raw expire, job không còn có thể recompute chính xác các giai đoạn đã quá hạn trừ khi có archive/durable source khác.

## 18. Kiểm thử tích hợp bằng time-series collection thật

Unit test mock `MongoTemplate.aggregate(...)` không chứng minh:

- Collection thực sự có `timeseries.timeField` và `metaField` đúng.
- `Instant` được convert thành BSON `Date`.
- `$dateTrunc` nhóm đúng mốc 15 phút.
- `$gte/$lt` loại mẫu ngay tại mốc kết thúc.
- Lọc tenant/device/quality không làm lộ dữ liệu khác.
- `$avg`/`$sum` thực sự trả kết quả đúng kiểu dữ liệu.
- Index/optimizer có làm việc tốt trên MongoDB version triển khai không.

Vì vậy cần integration test với **MongoDB hỗ trợ time-series collection và `$dateTrunc`**. Bài không yêu cầu replica set riêng chỉ để kiểm tra phép **đọc aggregation** này; nếu project còn test transactions/change streams thì áp dụng topology requirements riêng cho các tính năng đó.

### 18.1. Bộ tình huống tối thiểu

| Test | Input | Expected |
| --- | --- | --- |
| Cấu trúc collection | Tạo với `timeField=measuredAt`, `metaField=meta` | Collection có cấu hình time series |
| BSON thời gian | Insert `Date`/`Instant` | Raw document có BSON Date |
| Half-open range | `[09:00,10:00)` | Mẫu tại 10:00 không lọt |
| Tenant isolation | `TENANT-A` + `TENANT-B` | Không tính 888 của B |
| Device isolation | S-01 + S-02 | Không tính 99 của S-02 |
| Group 15 phút | 09:02,09:07,09:14,09:16,... | 4 reporting buckets |
| Số liệu | Fixture 7 mẫu | `count=7`, `sum=182`, avg 26 |
| Bucket boundary | 09:14 và 09:16 | Vào hai buckets liền nhau |
| Không có mẫu | Khoảng khác | Không trả bucket, không tự tạo `avg=0` |
| Validation | End ≤ start hoặc vượt policy | Từ chối trước MongoDB query |
| Múi giờ | Local day VN | UTC boundaries là `17:00Z` |
| Hiệu năng | Explain trên dữ liệu đủ lớn | Kiểm tra index/scan, không khẳng định từ fixture nhỏ |

### 18.2. Cấu hình test database riêng

Ví dụ Spring Boot 3.x, JUnit 5 và AssertJ:

```java
@DataMongoTest
@TestPropertySource(properties =
    "spring.data.mongodb.database=ts_lesson_test_worker9")
class TemperatureReportIntegrationTest {
    // ...
}
```

**Cảnh báo:** annotation property là cấu hình mẫu cho Spring Boot 3.x; driver/Boot major version khác có thể thay đổi. Không chỉ tin tên property: test nên kiểm tra **tên database thực tế từ MongoTemplate** trước khi tạo/drop collection. MongoDB time-series test không được chạy trên production hoặc database dùng chung.

### 18.3. Integration test hoàn chỉnh với dữ liệu mong đợi

File `TemperatureReportIntegrationTest.java`:

```java
package com.example.timeseries;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

@DataMongoTest
@TestPropertySource(properties =
    "spring.data.mongodb.database=ts_lesson_test_worker9")
class TemperatureReportIntegrationTest {

    private static final String COLLECTION =
        "sensor_measurements";

    @Autowired
    MongoTemplate template;

    private boolean createdByTest;

    @BeforeEach
    void prepareFixture() {
        String actualDb = template.getDb().getName();
        if (!"ts_lesson_test_worker9".equals(actualDb)) {
            throw new IllegalStateException(
                "Refusing to modify unexpected MongoDB: "
                    + actualDb);
        }
        if (template.collectionExists(COLLECTION)) {
            throw new IllegalStateException(
                "Test database must start with no collection "
                    + COLLECTION);
        }

        Document create = new Document("create", COLLECTION)
            .append("timeseries",
                new Document("timeField", "measuredAt")
                    .append("metaField", "meta")
                    .append("granularity", "seconds"));

        template.getDb().runCommand(create);
        createdByTest = true;

        template.getCollection(COLLECTION).insertMany(List.of(
            sample("09:02", "TENANT-A", "S-01", 20),
            sample("09:07", "TENANT-A", "S-01", 22),
            sample("09:14", "TENANT-A", "S-01", 24),
            sample("09:16", "TENANT-A", "S-01", 26),
            sample("09:26", "TENANT-A", "S-01", 28),
            sample("09:32", "TENANT-A", "S-01", 30),
            sample("09:46", "TENANT-A", "S-01", 32),
            sample("10:00", "TENANT-A", "S-01", 100),
            sample("09:04", "TENANT-A", "S-02", 99),
            sample("09:08", "TENANT-B", "S-01", 888)
        ));
    }

    private static Document sample(
            String hhmm, String tenant,
            String device, double value) {

        Document metadata = new Document("tenantId", tenant)
            .append("deviceId", device)
            .append("sensorType", "temperature")
            .append("unit", "C");

        return new Document("measuredAt",
            Date.from(Instant.parse(
                "2026-11-20T" + hhmm + ":00Z")))
            .append("meta", metadata)
            .append("value", value)
            .append("quality", "OK");
    }

    @AfterEach
    void cleanup() {
        if (createdByTest
                && "ts_lesson_test_worker9"
                    .equals(template.getDb().getName())) {
            // Database/collection của riêng test này.
            template.dropCollection(COLLECTION);
        }
    }

    private TemperatureReportService service() {
        return new TemperatureReportService(template);
    }

    @Test
    void groupsSevenSamplesIntoFourQuarterHourBuckets() {
        List<TemperatureBucket> rows =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T10:00:00Z"));

        assertThat(rows).hasSize(4);
        assertThat(rows).extracting(
            TemperatureBucket::bucketStart)
            .containsExactly(
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T09:15:00Z"),
                Instant.parse("2026-11-20T09:30:00Z"),
                Instant.parse("2026-11-20T09:45:00Z"));

        assertThat(rows.get(0).samples()).isEqualTo(3);
        assertThat(rows.get(0).sumValue()).isEqualTo(66);
        assertThat(rows.get(0).avgValue())
            .isCloseTo(22, within(0.000001));
        assertThat(rows.get(0).minValue()).isEqualTo(20);
        assertThat(rows.get(0).maxValue()).isEqualTo(24);

        assertThat(rows.get(1).samples()).isEqualTo(2);
        assertThat(rows.get(1).sumValue()).isEqualTo(54);
        assertThat(rows.get(1).avgValue())
            .isCloseTo(27, within(0.000001));

        long count = rows.stream()
            .mapToLong(TemperatureBucket::samples)
            .sum();
        double sum = rows.stream()
            .mapToDouble(TemperatureBucket::sumValue)
            .sum();

        assertThat(count).isEqualTo(7);
        assertThat(sum).isCloseTo(182, within(0.000001));
        assertThat(sum / count)
            .isCloseTo(26, within(0.000001));

        double incorrectAverageOfAverages =
            rows.stream()
                .mapToDouble(TemperatureBucket::avgValue)
                .average().orElseThrow();

        assertThat(incorrectAverageOfAverages)
            .isCloseTo(27.75, within(0.000001));
    }

    @Test
    void endBoundaryIsExclusiveAndTenantMustMatch() {
        List<TemperatureBucket> tenToEleven =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T10:00:00Z"),
                Instant.parse("2026-11-20T11:00:00Z"));

        assertThat(tenToEleven).hasSize(1);
        assertThat(tenToEleven.get(0).samples())
            .isEqualTo(1);
        assertThat(tenToEleven.get(0).sumValue())
            .isEqualTo(100);

        List<TemperatureBucket> otherTenant =
            service().report15Minutes(
                "TENANT-B", "S-01",
                Instant.parse("2026-11-20T09:00:00Z"),
                Instant.parse("2026-11-20T10:00:00Z"));

        assertThat(otherTenant).hasSize(1);
        assertThat(otherTenant.get(0).sumValue())
            .isEqualTo(888);
    }

    @Test
    void noDataIsEmptyNotZero() {
        List<TemperatureBucket> rows =
            service().report15Minutes(
                "TENANT-A", "S-01",
                Instant.parse("2026-11-20T11:00:00Z"),
                Instant.parse("2026-11-20T12:00:00Z"));

        assertThat(rows).isEmpty();
    }

    @Test
    void timeFieldIsStoredAsBsonDate() {
        Document first = template.getCollection(COLLECTION)
            .find(new Document(
                "meta.deviceId", "S-01"))
            .first();

        assertThat(first).isNotNull();
        assertThat(first.get("measuredAt"))
            .isInstanceOf(Date.class);
        assertThat(first.get("meta"))
            .isInstanceOf(Document.class);
    }

    @Test
    void invalidRangeDoesNotReachMongoDb() {
        Instant same =
            Instant.parse("2026-11-20T09:00:00Z");

        assertThatThrownBy(() ->
            service().report15Minutes(
                "TENANT-A", "S-01", same, same))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Giới hạn quan trọng của test fixture này:**

- Nó chỉ phù hợp khi **cả test runner lẫn MongoDB database đều cô lập**; không chạy đồng thời hai bản test dùng cùng tên database/collection. Trong CI nên cấp database/container riêng cho mỗi job.
- Nếu collection đã tồn tại, test **từ chối ghi**; `createdByTest` chỉ cho phép drop collection do chính fixture đã tạo.
- MongoDB server/driver phải hỗ trợ time-series collection và `$dateTrunc`.
- Test không dùng `deleteMany` trên time-series collection để cleanup từng document; quy tắc delete/update của time-series collections thay đổi theo version. Nó chỉ drop collection trong database riêng khi chắc chắn là fixture tạo.
- Không có bảo đảm test code được chạy trong giai đoạn soạn tài liệu; bước này chỉ cung cấp **mã kiểm thử để dự án thực thi**.

### 18.4. Test ngày địa phương và DST bằng unit test

Ngay cả khi không có MongoDB, có thể kiểm tra range:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

@Test
void vietnameseLocalDayUsesCorrectUtcBoundaries() {
    DailyRange range = DailyRange.of(
        LocalDate.of(2026, 11, 20),
        ZoneId.of("Asia/Ho_Chi_Minh"));

    assertThat(range.startInclusive()).isEqualTo(
        Instant.parse("2026-11-19T17:00:00Z"));
    assertThat(range.endExclusive()).isEqualTo(
        Instant.parse("2026-11-20T17:00:00Z"));
}
```

Đây là method thuộc một JUnit test class có imports như trên. Với timezone có DST, thêm test local day quanh ngày đồng hồ đổi giờ, khẳng định end được lấy từ `day.plusDays(1).atStartOfDay(zone)`, không thêm đúng 24h.

### 18.5. Test query count không bằng average count khi dữ liệu bẩn

Trong một database test **khác** hoặc fixture mới, seed cả `value:null` và `quality:"INVALID"`, rồi so sánh:

- Số documents matched sau `$match`.
- Số giá trị numeric hợp lệ thực sự được `$avg` dùng.
- Số samples bị loại do `quality`.

Không áp một test với dữ liệu bẩn vào service `TemperatureReportService` trước khi mở rộng policy validation và DTO nullable; nếu không, bạn chỉ tạo test thất bại do assumption được tài liệu ghi rõ.

## 19. Reactive access: không tự làm aggregation ở client

Spring Data MongoDB có `ReactiveMongoTemplate` và các API aggregation reactive để lấy dữ liệu khi ứng dụng sử dụng WebFlux/Project Reactor.

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<Document> rows = reactiveTemplate.aggregate(
    pipeline,
    "sensor_measurements",
    Document.class);
```

`reactiveTemplate` và `pipeline` được cấu hình ở service tương ứng. `Flux` là Publisher; MongoDB query chỉ thực thi khi subscribe, và consumer phải quan sát errors/cancellation/backpressure. Không dùng:

```java
// PHẢN VÍ DỤ trong event-loop code:
List<Document> all = rows.collectList().block();
```

trên WebFlux request thread. Nếu chỉ cần một số buckets giới hạn để vẽ chart, vẫn nên **filter, group và sort ở MongoDB**, trả một `Flux<DTO>` hoặc `Mono<List<DTO>>` có giới hạn tùy hợp đồng API.

### 19.1. Reactor không biến group thành stream từng sample

`Flux<Document>` trong ví dụ phát **các rows sau aggregation**. Các phép `$group` có thể phải xử lý nhiều raw samples trên server trước khi một row có thể được phát ra. Tính reactive giảm nhu cầu blocking threads ở client, **không làm chi phí MongoDB aggregation tự biến mất**.

### 19.2. Backpressure và giới hạn đầu ra

Nếu reporter truy vấn 10.000 devices × 96 buckets/ngày, số rows có thể rất lớn. Chọn scope và resolution trước khi mở stream. `rows.take(10)` chỉ giới hạn số item **client nhận**, không đảm bảo server không làm phần group tốn kém. Dùng filter server-side, aggregation logic, `$limit` đặt đúng chỗ và workload limits.

### 19.3. Đừng trộn blocking MongoTemplate vào reactive chain

Một service reactive không nên gọi `MongoTemplate.aggregate(...)` trực tiếp trên event loop rồi bọc kết quả bằng `Mono.just(...)`. Đó vẫn là blocking I/O. Chọn `ReactiveMongoTemplate` hoặc cách chuyển thread có kiểm soát khi bắt buộc tương tác với driver blocking; với báo cáo time series dài, cân nhắc batch job thay vì giữ HTTP request treo lâu.

### 19.4. Kiểm thử reactive aggregation bằng StepVerifier

Khi đã có test fixture và `Aggregation pipeline` giống mục 9, có thể xác nhận các rows không cần `block()`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import static org.assertj.core.api.Assertions.assertThat;

Flux<Document> rows = reactiveTemplate.aggregate(
    pipeline, "sensor_measurements", Document.class);

StepVerifier.create(rows)
    .assertNext(first -> {
        assertThat(first.getDate("bucketStart")
                .toInstant())
            .isEqualTo(Instant.parse(
                "2026-11-20T09:00:00Z"));
        assertThat(((Number) first.get("samples"))
                .longValue()).isEqualTo(3L);
        assertThat(((Number) first.get("avgValue"))
                .doubleValue()).isEqualTo(22.0);
    })
    .expectNextCount(3)
    .verifyComplete();
```

Đây là **đoạn trong integration test**, nơi `reactiveTemplate`, `pipeline`, `Instant` và fixture đã được tạo. `verifyComplete()` đảm bảo stream kết thúc bình thường với đúng bốn rows; `expectNextCount(3)` chưa kiểm tra chi tiết ba buckets sau, nên test correctness production vẫn phải assert các mốc, count/sum và tenant isolation như bộ imperative ở mục 18. Khi test với dữ liệu không ổn định hoặc lỗi, cần xử lý `onError`, cancellation và timeout một cách minh bạch thay vì bọc `onErrorResume` trả list rỗng.

## 20. Thiết kế API báo cáo có giới hạn rõ ràng

Không nên mở một API cho phép user tự chọn `from=1900-01-01` đến hiện tại, `resolution=1 second` và `deviceIds=*` mà không có policy. Nó có thể kích hoạt aggregation khổng lồ, kể cả khi index tốt.

Một request DTO:

```java
package com.example.timeseries;

import java.time.Instant;

public record TemperatureReportRequest(
    String deviceId,
    Instant startInclusive,
    Instant endExclusive,
    int bucketMinutes
) {}
```

`tenantId` không cần lấy từ request body khi đã có authentication; service nhận `permittedTenantId` từ security context. Với request có bucket resolution, có thể đặt allowlist:

```java
if (bucketMinutes != 1
        && bucketMinutes != 5
        && bucketMinutes != 15
        && bucketMinutes != 60) {
    throw new IllegalArgumentException(
        "Độ phân giải không được hỗ trợ");
}
```

### 20.1. Giới hạn số reporting buckets dự kiến

```text
requestedTimeRange = 7 days
bucketResolution   = 1 minute
expectedBuckets    = 7 * 24 * 60 = 10080 per device
```

Với 500 devices, lên đến hơn 5 triệu bucket rows nếu mọi thiết bị đều có dữ liệu đầy đủ. Vì vậy ngoài giới hạn raw range còn phải giới hạn **số thiết bị × số buckets**, dùng pagination/batch/rollups tùy UX.

### 20.2. Tránh tin timezone do client gửi mà không kiểm tra

`timezone` là một chuỗi ảnh hưởng `$dateTrunc`. Chỉ nhận một IANA Zone ID hợp lệ như `"Asia/Ho_Chi_Minh"` và thuộc danh sách/zone policy cho tenant/site. Nếu chỉ cho phép tùy biến hiển thị, nên dùng timezone cấu hình của site; đừng để client nhập tùy ý một expression BSON thành pipeline.

`ZoneId.of(value)` có thể báo lỗi khi ID không hợp lệ; controller nên trả response lỗi rõ. Không đưa chuỗi JSON từ client vào raw `Document` dưới dạng một stage tùy ý, tránh query/pipeline injection ở tầng ứng dụng.

### 20.3. Response contract nên nói rõ độ đầy đủ

Ví dụ response:

```json
{
  "deviceId": "S-01",
  "timezone": "UTC",
  "fromInclusive": "2026-11-20T09:00:00Z",
  "toExclusive": "2026-11-20T10:00:00Z",
  "bucketMinutes": 15,
  "unit": "C",
  "dataCompleteness": "PROVISIONAL",
  "buckets": [
    {
      "start": "2026-11-20T09:00:00Z",
      "samples": 3,
      "average": 22.0,
      "minimum": 20.0,
      "maximum": 24.0
    }
  ]
}
```

Đây là format **minh họa**; một response thực sẽ trả đủ buckets phù hợp hoặc phân trang. `dataCompleteness` có thể là `PROVISIONAL` khi dữ liệu đến muộn còn khả năng làm thay đổi báo cáo, `FINAL` khi đã chốt theo nghiệp vụ và `PARTIAL_RETENTION` khi raw data hết hạn. Không tự tuyên bố “FINAL” chỉ vì MongoDB query đã complete.

### 20.4. Caching phải tính đến late arrivals

Nếu cache key chỉ có `deviceId+range` mà bỏ `tenantId`, nguy cơ rò rỉ dữ liệu đa tenant. Nếu key có đủ tenant/zone/resolution nhưng cache TTL một ngày, phép đo đến muộn có thể không xuất hiện trong dashboard.

Chiến lược:

- Cache key chứa tenant, device, time range, zone, resolution, quality policy và phiên bản thuật toán.
- Bucket mới có TTL ngắn; bucket đã chốt có TTL dài hơn theo policy.
- Late data có invalidation/recompute cho những bucket liên quan.
- Nếu query từ rollup, gắn `computedAt`/data freshness trong response.

## 21. Consistency giữa raw measurements, rollup và dashboard

Time-series queries đọc từ logical collection tại thời điểm thực hiện; một request báo cáo kéo dài có thể giao với những phép đo mới đến, batch insert hoặc rollup đang cập nhật. **Truy vấn aggregation hoàn thành không phải cam kết báo cáo sẽ không thay đổi**.

### 21.1. Tình huống đọc “cùng ngày” hai lần khác nhau

```text
09:30  Dashboard reads 09:00–10:00
       raw measurements available: 09:02,09:07,09:14
       avg=22

09:35  Gateway uploads late measurement measuredAt=09:16
       avg for 09:00–10:00 now changes

09:40  Dashboard reads same range again
       avg based on 4 samples, not 3
```

Đó có thể là **hành vi đúng** theo event-time semantics. Nếu sản phẩm cần số đã chốt không đổi, hãy đặt quy trình **cutoff/watermark** rõ ràng và không dùng một truy vấn raw “latest” làm tài liệu kế toán final.

### 21.2. Tách dữ liệu sơ bộ và dữ liệu đã chốt

Gợi ý hai tầng:

```text
Raw time series:
  measuredAt, receivedAt, eventId, metadata, value
        |
        v
Background aggregation with allowed lateness
        |
        v
Rollup:
  bucketStart, samples, sum, min, max,
  computedAt, revision, completenessStatus
        |
        v
Dashboard and exported reports
```

Lúc còn dữ liệu đến muộn, một bucket có thể tăng revision từ 3 lên 4. Nếu client cần audit thay đổi, lưu revision/change log ở collection thường và có schema rõ. Đừng cố biến TTL của MongoDB time-series collection thành watermark nghiệp vụ.

### 21.3. Không mặc định transaction trên toàn báo cáo khổng lồ

Một aggregation dài đọc rất nhiều data có chi phí và quy tắc consistency riêng. Không tự đặt mọi job báo cáo time series vào một multi-document transaction dài; tính năng thời gian, resource limits, server topology và write stages có thể có ràng buộc. Chọn read concern/snapshot policy theo mức nhất quán thực sự cần, đo tải và dùng rollup/snapshot version khi cần công bố số liệu ổn định.

## 22. Chẩn đoán kết quả sai

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Report đếm 8 thay vì 7 mẫu | Dùng `$lte` ở end, nên nhận sample 10:00 | Đổi sang `$lt`; test boundary |
| Average bị tăng bất thường thay vì 26 | Quên filter tenant hoặc S-02 | Match `meta.tenantId` + `meta.deviceId` tại DB |
| Group có 2 giờ thay vì 1 ngày | Filter UTC nhưng group timezone địa phương | Tạo UTC bounds từ `LocalDate+ZoneId` đồng nhất |
| Báo cáo ngày lệch 7 giờ | Dùng `LocalDateTime` không có timezone | Dùng `Instant` và `ZoneId` |
| Báo cáo mùa DST thiếu/lặp giờ | Cộng 24h cố định cho local day | Dùng đầu ngày kế tiếp theo zone |
| Không có row cho 09:30 | Không có raw samples | Chọn missing-data policy; không tự coi bằng 0 |
| Average 27.75 thay vì 26 | Tính avg của các bucket averages | Tổng `sumValue`/tổng `samples` |
| Count lớn hơn numeric samples | `$sum:1` đếm cả document value null | Lọc numeric hoặc đếm riêng `$isNumber` |
| Thống kê độ C quá cao | Trộn °C/°F hoặc humidity | Filter unit/sensorType/convert trước group |
| Một bucket nhảy sau vài giờ | Late arrival thay event-time aggregate | Recompute overlap/rollup revision/freshness |
| Nhiều mẫu giống hệt | Source retry tạo duplicates | Event ID/idempotent ingestion/dedupe |
| Query trả rỗng cho dữ liệu cũ | TTL đã dọn raw buckets | Check retention/rollup/archive |
| Query trên chuỗi ngày giờ chạy sai | `measuredAt` lưu String, không BSON Date | Kiểm tra raw BSON, migrate dữ liệu |
| `$dateTrunc` không được nhận diện | MongoDB version quá cũ | Kiểm tra server version; nâng cấp/đổi operator |
| `@Document` trỏ collection không đúng | Sai tên collection | Kiểm tra namespace và mapping |
| Raw Java aggregation không nhận số | BSON field bị `@Field` đổi tên | Inspect BSON, sửa raw `Document` stages |
| Sắp xếp bucket không đúng | Không có `$sort` sau `$group` | `$sort:{"_id":1}` |
| Query chậm theo ngày, nhanh theo giờ | Range quá rộng, unpack nhiều buckets | Explain, index, rollup |
| Dashboard stale dù raw đã có mẫu mới | Cache/rollup chưa refresh | Invalidation, freshness, recompute |
| Ghi `$merge` thất bại | Thiếu unique index trên rollup target, thiếu quyền | Tạo index đúng target, kiểm tra merge version |
| Không dùng được index định tạo | Time-series index restrictions/version/planner | Inspect `getIndexes()` và `explain()` |
| Không kết thúc truy vấn API | Lấy hàng triệu rows, không giới hạn | Range cap, resolution cap, batch/export job |
| Dữ liệu tenant khác lộ qua cache | Cache key/query thiếu tenant | Bảo vệ tại query + cache key + auth |
| Kết quả floating-point lệch rất nhỏ | Precision `double` | Assert tolerance, chọn numeric policy |

### 22.1. Điều tra bằng raw BSON trước tiên

Khi báo cáo sai timezone hoặc metadata, trước hết xem một sample thật trong logical collection:

```javascript
db.sensor_measurements.find(
  { "meta.tenantId": "TENANT-A" },
  { measuredAt: 1, meta: 1, value: 1, quality: 1 }
).limit(3)
```

Kiểm tra kiểu `Date`, cấu trúc `meta` và unit. Nếu chỉ nhìn Java DTO, converter có thể khiến việc phân biệt BSON String/Date/Decimal128 không rõ ràng.

### 22.2. Chạy từng stage để định vị sai lệch

Một cách debug có hệ thống:

1. Chạy `$match` rồi `$count`; kết quả fixture phải là 7.
2. Chạy `$match` + `$project` mốc `$dateTrunc` để xem mỗi sample vào bucket nào.
3. Thêm `$group`, so từng `samples` và `sumValue` với bảng thủ công.
4. Thêm `$sort` và `$project`, kiểm tra DTO mapping.
5. Nếu số liệu sai khi chạy rollup, so raw vs rollup và revision/late arrivals.

Không bắt đầu từ frontend chart formatting nếu ngay `$match` trên MongoDB đã chọn sai tập dữ liệu.

### 22.3. Không sửa lỗi timezone bằng cách cộng/trừ 7 giờ trong mọi query

Phản ví dụ:

```java
Instant fixed = inputInstant.plusSeconds(7 * 3600);
```

Đây không phải một chuyển đổi múi giờ tổng quát. `Instant` đã là thời điểm UTC tuyệt đối; khi muốn một ngày/giờ địa phương, dùng `ZonedDateTime`/`ZoneId` để xác định bounds. Với DST, offset không cố định; cộng 7 giờ có thể làm sai cả báo cáo Việt Nam nếu client input đã là instant đúng.

## 23. Checklist trước khi đưa báo cáo time series vào production

1. **Đúng collection:** xác minh `timeField`/`metaField` và namespace thật.
2. **Đúng kiểu BSON:** timestamp là Date, numeric values có unit và quality.
3. **Event time vs ingest time:** đã xác định câu hỏi dùng timestamp nào?
4. **Khoảng nửa mở:** `$gte start` + `$lt end`, không dùng `$lte` ghép hai khoảng.
5. **Timezone:** start/end do `LocalDate` + `ZoneId` tạo; group dùng cùng timezone.
6. **Tenant scoped:** filter tenant tại database và authorize từ user/session context.
7. **Metadata stable:** không đưa dữ liệu biến động mỗi sample vào metaField nếu không cần.
8. **Quality policy:** số mẫu invalid/missing được lọc và báo cáo minh bạch.
9. **$match sớm:** filter metadata/time trước group lớn.
10. **Bucket resolution:** giới hạn số nhóm = device count × time buckets.
11. **$dateTrunc đúng:** unit/binSize/timezone và version MongoDB hỗ trợ.
12. **Group keys đủ dimension:** không trộn devices, tenant, unit, sensorType sai ngữ nghĩa.
13. **Sort output:** `$sort` theo bucket timestamp sau `$group`.
14. **No data policy:** phân biệt null/gap với zero.
15. **Weighted rollup:** giữ sum/count, không average-of-averages.
16. **Late data:** có allowed lateness/recompute/rollup revision.
17. **Duplicate:** có event identity và dedupe policy.
18. **Retention:** raw/rollup/archive đáp ứng thời gian báo cáo.
19. **Index:** đánh giá meta+time index theo version bằng `getIndexes()`/`explain()`.
20. **Error handling:** không biến lỗi database thành báo cáo rỗng.
21. **Reactivity:** không `block()` trong WebFlux; server aggregation vẫn tốn tài nguyên.
22. **Rollup security:** `$merge` chỉ trong controlled jobs, target index và quyền ghi rõ.
23. **Integration tests:** mốc biên, tenant/device, numeric types, missing-data và timezone.
24. **Monitoring:** latency, scan, memory/spill, ingestion lag, rollup freshness, errors.

## 24. Các lỗi thiết kế cần tránh

### 24.1. Làm tròn thời gian ở Java rồi query theo chuỗi

Thay vì lấy hàng triệu measurements về JVM, chuyển `measuredAt` thành `String yyyy-MM-dd HH:mm` rồi group bằng `Collectors.groupingBy`, hãy dùng `$dateTrunc` và `$group` của MongoDB. Chỉ dùng client aggregation cho một tập dữ liệu nhỏ đã được giới hạn và có lý do.

### 24.2. Bật TTL rồi kỳ vọng báo cáo lịch sử luôn đầy đủ

TTL phù hợp cho chính sách retention, không thay thế báo cáo lưu trữ lịch sử. Nếu báo cáo 1 năm phải xem được, cần rollups/archive tương ứng; đừng đợi raw expire rồi tìm cách “kéo lại” từ chính collection đã mất dữ liệu.

### 24.3. Thêm $sort raw sample trước $group một cách máy móc

`$sort` trước `$group` không cần thiết cho `sum/avg/min/max/count` theo bucket, vì các accumulators đó không phụ thuộc thứ tự. Nó có thể tăng CPU/memory đáng kể. Chỉ sort trước khi dùng các order-dependent accumulators như `$first`/`$last`, hoặc khi business thật sự yêu cầu một thứ tự theo thời gian.

### 24.4. Tính “mức thay đổi so với phép đo trước” bằng $first không sort

Nếu muốn tìm sample đầu/cuối trong mỗi bucket, `$first`/`$last` phụ thuộc thứ tự input. Phải xác định sort theo `measuredAt`, tie-breaker nếu timestamps trùng, và xét tối ưu/performance. Không dùng kết quả order ngầm của time-series storage để suy luận phép đo đầu tiên/cuối cùng của bucket.

### 24.5. Trộn dữ liệu trong cùng bucket vì tên field giống nhau

Một metadata dimension mới (`firmwareVersion`, calibration version, unit) có thể làm giá trị đo thay đổi cách hiểu. Khi aggregation cần so sánh qua calibration change, phải xác định cách normalize/chia nhóm và lưu audit của thay đổi. Không chỉ nhìn `deviceId` mà bỏ những biến có ý nghĩa khoa học hoặc nghiệp vụ.

## 25. Bài tập thực hành

Một hệ thống năng lượng có các đồng hồ điện theo thời gian thực. Collection `power_measurements` có:

```javascript
{
  measuredAt: ISODate("2026-11-20T09:02:00Z"),
  meta: {
    tenantId: "TENANT-ENERGY",
    meterId: "M-001",
    unit: "kW"
  },
  value: 12.5,
  quality: "OK"
}
```

Mục tiêu ban đầu là báo cáo **công suất trung bình theo mẫu** trong giờ làm việc; sau đó mở rộng thành lượng điện tiêu thụ và báo cáo ngày.

### Bài tập 1 — Mô hình hóa collection

Viết `db.createCollection("power_measurements", {timeseries:{...}})`, chọn:

- `timeField = measuredAt`.
- `metaField = meta`.
- Granularity phù hợp với phép đo vài giây/một phút.

Giải thích vì sao `measuredAt` không nằm trong `meta`, và vì sao `unit="kW"` là dimension quan trọng khi aggregate nhiều đồng hồ. Kiểm tra options thật bằng `getCollectionInfos`.

### Bài tập 2 — Khoảng thời gian nửa mở

User chọn `09:00–10:00 UTC`. Viết `Criteria`:

```java
Criteria criteria = Criteria
    .where("meta.tenantId").is("TENANT-ENERGY")
    .and("meta.meterId").is("M-001")
    .and("measuredAt")
        .gte(Date.from(start))
        .lt(Date.from(end));
```

Với hai mẫu `09:59:59.999` và `10:00:00.000`, mẫu nào được nhận? Nếu truy vấn tiếp `[10:00,11:00)`, tại sao không đếm trùng?

### Bài tập 3 — $dateTrunc theo 5 phút

Viết pipeline:

```javascript
[
  { $match: { /* time range, meterId, tenant, quality */ } },
  { $group: {
      _id: {
        $dateTrunc: {
          date: "$measuredAt",
          unit: "minute",
          binSize: 5,
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      averageKw: { $avg: "$value" },
      minimumKw: { $min: "$value" },
      maximumKw: { $max: "$value" }
  }},
  { $sort: { _id: 1 } }
]
```

Giải thích vì sao timestamp 09:04 thuộc bucket 09:00, còn 09:05 thuộc bucket 09:05.

### Bài tập 4 — Dữ liệu kiểm chứng bằng tay

Quay lại fixture nhiệt độ:

```text
09:02 -> 20
09:07 -> 22
09:14 -> 24
09:16 -> 26
09:26 -> 28
09:32 -> 30
09:46 -> 32
```

Tính cho mỗi 15 phút:

- Số mẫu.
- Tổng giá trị.
- Trung bình.
- Min và max.

Sau đó so với kết quả expected ở mục 4.1. Chạy pipeline MongoDB thật và giải thích vì sao `$group` cần `$sort` phía sau.

### Bài tập 5 — Trung bình có trọng số

Các bucket có `count=[3,2,1,1]` và `avg=[22,27,30,32]`.

1. Tính trung bình trực tiếp của bốn `avg`.
2. Tính trung bình đúng của bảy mẫu.
3. Chứng minh `sum(sumValue)/sum(samples)` là cách roll up hợp lý.
4. Nếu có bucket `samples=0`, công thức phải xử lý mẫu số bằng 0 như thế nào?

**Đáp số kiểm tra:** 27,75 là average-of-averages **sai cho bảy mẫu**; 26 là average của cả bảy.

### Bài tập 6 — Ngày địa phương

API nhận:

```text
day = 2026-11-20
timezone = Asia/Ho_Chi_Minh
```

Hãy tạo `DailyRange` bằng `LocalDate` và `ZoneId` rồi assert:

```text
startInclusive = 2026-11-19T17:00:00Z
endExclusive   = 2026-11-20T17:00:00Z
```

Nếu chỉ dùng UTC midnight cho cả query và group, những measurement cuối ngày Việt Nam có thể bị xếp vào ngày nào? Thêm test với múi giờ có DST để chứng minh không được cộng cố định 24 giờ.

### Bài tập 7 — Báo cáo đa thiết bị

Một tenant có M-001 và M-002, cả hai đo lúc 09:05. Tạo group key:

```javascript
_id: {
  meterId: "$meta.meterId",
  bucketStart: {
    $dateTrunc: {
      date: "$measuredAt",
      unit: "hour",
      timezone: "UTC"
    }
  }
}
```

Nếu không thêm `meterId` vào group key, số liệu thay đổi ngữ nghĩa thế nào? Nếu một meter dùng kW còn meter khác dùng W, có thể lấy average trực tiếp không?

### Bài tập 8 — Bucket trống

Không có mẫu trong `09:30–09:45`. Thiết kế hai response:

1. **Sparse:** trả các buckets có dữ liệu, bỏ mốc 09:30.
2. **Dense:** trả đủ các mốc, tại 09:30 dùng `samples=0`, `average=null`, `status="NO_DATA"`.

Trình bày khi nào có thể dùng `$densify`/`$fill`, khi nào tạo timeline có giới hạn ở client, và tại sao không tự điền 0°C/kW cho mọi loại dữ liệu.

### Bài tập 9 — Late measurement

Job tạo rollup 09:00 lúc 10:10. Đến 11:00, gateway gửi thêm sample có `measuredAt=09:07`.

Hãy thiết kế:

- Allowed lateness.
- Cửa sổ recompute chồng lấp.
- Revision của rollup.
- Cách invalidation cache.
- Cách đánh dấu báo cáo còn tạm thời hay đã chốt.

Giải thích vì sao việc “tính đúng khi job chạy” không có nghĩa báo cáo sẽ mãi đầy đủ.

### Bài tập 10 — Duplicate và quality

Nguồn gửi trùng một sample `value=20` vì retry. Lúc này `$sum:1` tăng như thế nào? Đề xuất một `eventId` ổn định từ producer, chiến lược dedupe phù hợp với hạn chế time-series collection và cách kiểm chứng bằng integration test.

Thêm một sample `quality="INVALID"` và một sample `value:null`. So sánh:

- Document count.
- Numeric count.
- Average của những giá trị numeric hợp lệ.

Không được coi “null” là nhiệt độ 0 nếu không có nghiệp vụ cho phép.

### Bài tập 11 — Rollup và $merge

Tạo collection thường `power_rollups_15m` với unique identity gồm tenant, meter và bucketStart. Viết pipeline:

```text
raw measurements
  -> $match (tenant, meter, time, quality)
  -> $group (15-minute start, count, sum, min, max)
  -> $project (rollup fields)
  -> $merge into regular collection
```

Chạy lại cùng khoảng hai lần và kiểm tra không có hai rollup rows cho cùng một key. Đánh giá vì sao còn có thể double count nếu raw source chứa duplicate measurements và vì sao `whenMatched:"replace"` không tự khắc phục lỗi ingest.

### Bài tập 12 — Performance

So sánh `explain("executionStats")` của:

1. Query theo một thiết bị trong 1 giờ.
2. Query theo một thiết bị trong 30 ngày.
3. Query toàn tenant trong 30 ngày.
4. Query lấy rollups trong 30 ngày.

Ghi nhận latency, docs/buckets examined, index selection, memory/spill và số rows. Đề xuất giới hạn API theo khoảng thời gian/resolution, kế hoạch pre-aggregation và cache invalidation. Không dùng fixture 10 documents để kết luận index production “đủ nhanh”.

### Bài tập 13 — Mức tiêu thụ năng lượng

Giá trị `powerKw` là công suất tức thời, không phải sản lượng kWh. Nếu measurements có nhịp 5 phút, giả định nguồn giữ công suất không đổi cho tới lần đo kế tiếp, hãy thiết kế phép tính năng lượng ước lượng:

```text
energyKWh ≈ sum(powerKw_i * elapsedHours_i)
```

Đặt câu hỏi:

- Nếu có khoảng trống 2 giờ, có nên tự kéo giá trị gần nhất qua toàn bộ khoảng?
- Nếu device gửi muộn, năng lượng bucket nào cần được tính lại?
- Nếu có measurement trong khoảng nhưng không phải đúng mốc đầu/ cuối, sẽ cắt tích phân tại boundary ra sao?
- Vì sao `$sum:"$powerKw"` là sai nếu đặt tên output `energyKWh`?

Đây là bài về **định nghĩa số liệu**: operator MongoDB đúng cú pháp không tự làm công thức vật lý trở nên đúng.

### Bài tập 14 — Kiểm thử và isolation

Viết `@DataMongoTest` trên database riêng:

1. Tạo một **time-series collection** bằng options được kiểm tra.
2. Insert fixture 7 mẫu cộng ba mẫu đối chứng.
3. Assert `count=7`, `sum=182`, `avg=26`.
4. Assert sample tại đúng 10:00 chỉ nằm trong khoảng sau.
5. Assert tenant B và S-02 không bị lẫn.
6. Assert BSON `measuredAt` là `Date`.
7. Assert report ngày Việt Nam có bounds đúng.
8. Assert khi không có sample kết quả rỗng, không tự trả `avg=0`.
9. Chỉ cleanup collection do test tạo trong database đã xác minh, không drop dữ liệu dùng chung.

## 26. Câu hỏi tự kiểm tra

| Câu hỏi | Gợi ý đáp án |
| --- | --- |
| `timeField` chứa kiểu BSON nào? | Date |
| `metaField` thường dùng cho gì? | Metadata ổn định phân nhóm/nguồn đo |
| Time-series storage bucket có phải reporting bucket không? | Không |
| Vì sao dùng `[start,end)`? | Ghép khoảng liền nhau không đếm trùng |
| End-bound dùng `$lt` hay `$lte`? | `$lt` |
| `Instant` khác `LocalDateTime` thế nào? | Instant là mốc tuyệt đối, LocalDateTime thiếu zone |
| Ngày Việt Nam 20/11/2026 bắt đầu lúc nào UTC? | 19/11/2026 lúc 17:00Z |
| Nhóm 15 phút với operator nào? | `$dateTrunc` trong `$group` |
| Group có bảo đảm thứ tự không? | Không, cần `$sort` |
| Báo cáo fixture có bao nhiêu mẫu? | 7 |
| Tổng và trung bình fixture? | 182 và 26 |
| Vì sao avg-of-avgs 27,75 sai? | Bucket counts khác nhau |
| Một bucket không có mẫu có phải bằng 0? | Không |
| TTL có xóa ngay đúng giây hết hạn không? | Không, cleanup có độ trễ |
| Late arrival ảnh hưởng gì? | Có thể thay kết quả các bucket đã tính |
| `$merge` làm gì? | Ghi kết quả aggregation vào collection đích |
| Pre-aggregation có loại duplicate raw tự động không? | Không |
| Khi nào cần explain? | Khi tối ưu index/scan và chẩn đoán tải |
| Có thể group devices khác unit vào một AVG không? | Không nếu chưa chuẩn hóa |
| ReactiveMongoTemplate giúp gì? | Truy vấn không blocking client, server vẫn phải aggregate |
| `$avg` có phải time-weighted average không? | Không mặc định, là average các giá trị numeric tham gia |
| Báo cáo ngày DST có luôn 24 giờ? | Không |
| Vì sao filter tenant phải ở server? | Correctness, bảo mật và hiệu năng |

## 27. Tài liệu tham khảo

- MongoDB Manual — [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): mô hình và các giới hạn của time-series collection.
- MongoDB Manual — [Create Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/): cấu hình `timeField`, `metaField`, `granularity`.
- MongoDB Manual — [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/): khả năng index và các giới hạn theo phiên bản.
- MongoDB Manual — [Time Series Querying](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-querying/): truy vấn theo metadata/thời gian.
- MongoDB Manual — [`$dateTrunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/): `unit`, `binSize`, `timezone` và `startOfWeek`.
- MongoDB Manual — [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): accumulators `$sum`, `$avg`, `$min`, `$max`.
- MongoDB Manual — [`$match`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/): lọc trước aggregation.
- MongoDB Manual — [`$densify`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/): tạo các điểm thiếu theo range trong phiên bản hỗ trợ.
- MongoDB Manual — [`$fill`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/): điều khiển cách điền giá trị thiếu.
- MongoDB Manual — [`$merge`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/): ghi kết quả rollup và yêu cầu unique index trên target.
- MongoDB Manual — [Time Series TTL](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/): retention và loại bỏ dữ liệu hết hạn.
- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `MongoTemplate`, `Query`, `Criteria`.
- Spring Data MongoDB — [Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `Aggregation`, mapping input/output, các stages.
- Spring Data MongoDB — [Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `ReactiveMongoTemplate` và Publisher.
- Java SE — [Java Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `LocalDate`, `ZoneId` và thời gian địa phương.

## Ghi nhớ

**Báo cáo time series đúng bắt đầu từ định nghĩa thời gian và dữ liệu**, không phải từ `$group`. Hãy lưu `measuredAt` dưới dạng BSON Date, lọc tenant/device/unit/quality **ngay trong MongoDB**, sử dụng khoảng nửa mở `[startInclusive,endExclusive)` để không đếm trùng, và group theo reporting buckets bằng `$dateTrunc` với `binSize`/`timezone` phù hợp. `$group` tính `count/sum/avg/min/max` nhưng không tự tạo bucket trống; `$sort` xác định thứ tự biểu đồ. Khi tổng hợp nhiều buckets, dùng **tổng sum/tổng count**, không lấy trung bình của các trung bình nếu số mẫu khác nhau. Đối với báo cáo ngày địa phương, đổi `LocalDate+ZoneId` sang UTC bounds và dùng cùng timezone khi group, kể cả ngày DST. Late arrivals, duplicate measurements, TTL và pre-aggregation đều có thể làm báo cáo đổi hoặc thiếu; cần policies về freshness, deduplication, retention, rollup và integration tests kiểm tra BSON/boundaries/tenant/giá trị thật trước khi vận hành.
