# Ghi dữ liệu đến muộn, sai thứ tự và vấn đề trùng phép đo trong MongoDB

## 1. Bài toán và mục tiêu

Dữ liệu chuỗi thời gian (*time series*) xuất hiện trong cảm biến IoT, telemetry, metric ứng dụng, giao dịch thị trường, log thiết bị và hệ thống công nghiệp. Mỗi bản ghi phản ánh một phép đo tại một thời điểm. Nhưng **thứ tự dữ liệu được đo không nhất thiết giống thứ tự dữ liệu được nhận**:

- Thiết bị mất kết nối rồi gửi lại số đo của 10 phút trước.
- Hai gateway đẩy message qua các queue partition với độ trễ khác nhau.
- Client timeout rồi gửi lại chính message đã xử lý.
- Một nguồn phát hành correction cho một measurement cũ.
- Một thiết bị reboot và tái sử dụng sequence number.
- Job backfill nhập dữ liệu lịch sử trong lúc hệ thống vẫn nhận dữ liệu thời gian thực.
- Đồng hồ thiết bị chạy sai, khiến timestamp nằm trong quá khứ hoặc tương lai.

MongoDB **time series collection** tối ưu việc lưu và đọc phép đo thông qua `timeField`, `metaField` và các bucket nội bộ. Tuy nhiên, nó **không tự cung cấp** chính sách nhận dữ liệu muộn, watermark, xác định danh tính phép đo hay chống duplicate như một khóa unique thông thường.

Sau bài học, bạn có thể:

1. Phân biệt **event time**, **ingestion time** và **processing time**.
2. Hiểu cách MongoDB xử lý timestamp đến sai thứ tự và ảnh hưởng tới bucket.
3. Phân biệt bản **retry trùng event**, một **logical measurement** và **revision/correction**.
4. Phát hiện duplicate, tính kết quả canonical và tính lại cửa sổ thời gian.
5. Hiểu giới hạn của time series collection đối với `unique index`, `_id`, `upsert`, `$merge` và transactions.
6. Thiết kế lớp tiếp nhận riêng có unique index, cùng kế hoạch phục hồi khi dual-write không atomic.
7. Đặt **allowed lateness**, watermark, trạng thái provisional/final/revised và chiến lược backfill.
8. Theo dõi độ trễ, hiệu suất bucketing, TTL và dữ liệu bị lặp.

**Nguyên tắc cốt lõi:** Việc MongoDB lưu được một bản ghi không có nghĩa bản ghi đó là phép đo mới, đúng thứ tự hay phải được tính thêm một lần vào báo cáo.

## 2. Ba mốc thời gian của một phép đo

Một event thường cần tách riêng các timestamp:

| Trường | Ý nghĩa | Do ai gán? | Mục đích |
| --- | --- | --- | --- |
| `observedAt` | **Event time** — lúc đo | Thiết bị hoặc nguồn nghiệp vụ | Nhóm cửa sổ, thứ tự thời gian, phân tích |
| `receivedAt` | **Ingestion time** — lúc nhận | Gateway hoặc backend | Đo late arrival, audit |
| `processedAt` | **Processing time** — lúc xử lý | Worker/processor | Đo latency pipeline, retry |
| `sentAt` (tùy chọn) | Lúc nguồn phát thông điệp | Thiết bị | Tách network delay khỏi device buffering |

Ví dụ:

```javascript
{
  eventId: "sensor-A:boot-7:seq-104",
  sampleId: "sensor-A:boot-7:sample-104",
  revision: 1,
  meta: {
    tenantId: "factory-1",
    deviceId: "sensor-A",
    metric: "temperature"
  },
  observedAt: ISODate("2026-11-14T09:00:00Z"),
  receivedAt: ISODate("2026-11-14T09:04:30Z"),
  value: 21.5,
  unit: "C"
}
```

Phép đo xảy ra lúc **09:00 UTC** nhưng backend nhận lúc **09:04:30 UTC**; độ trễ tiếp nhận là 270 giây nếu hai đồng hồ đáng tin cậy.

Không thay `observedAt` bằng `receivedAt` chỉ để “dữ liệu tăng dần theo giờ”: khi đó báo cáo của phút 09:00 sẽ bị chuyển nhầm sang 09:04.

### 2.1. Hai thứ tự khác nhau

```text
Thứ tự PHÁT SINH phép đo:
08:59     09:00     09:01     09:02
 M0        M1        M2        M3

Thứ tự hệ thống NHẬN:
09:00:05  09:02:02  09:03:00  09:03:10
 M1        M3        M0        M2
```

- **Out-of-order:** phép đo M2 đến sau M3 dù `observedAt(M2)` sớm hơn.
- **Late:** phép đo đến sau một *hạn* xử lý do nghiệp vụ định nghĩa, ví dụ cửa sổ đã final hoặc quá 2 phút so với event time.

Một phép đo có timestamp cũ hơn lần nhận trước **không nhất thiết không hợp lệ**. Nó có thể nằm trong khoảng lateness được cho phép.

### 2.2. Đồng hồ thiết bị là một nguồn lỗi

Khi tính `receivedAt - observedAt`, cần kiểm tra:

- NTP hoặc cơ chế đồng bộ thời gian của thiết bị.
- Timestamp có timezone rõ ràng hay không.
- Clock có reset sau reboot không.
- Event “đến từ tương lai” có phải do thiết bị chạy nhanh không.
- `receivedAt` được gán tại ingress đầu tiên hay sau queue delay.
- Retry có giữ nguyên timestamp nguồn hay tự gán timestamp mới.

BSON Date dùng thời điểm UTC. Ở đầu vào, cần chuẩn hóa timezone và từ chối/quarantine những timestamp bất hợp lệ theo quy tắc nguồn.

## 3. MongoDB bucket dữ liệu ra sao?

Time series collection nhóm measurements theo **giá trị `metaField` giống nhau** và timestamp `timeField` đủ gần nhau. Các bucket có giới hạn thời gian, số measurement, kích thước và cache.

```text
meta = {deviceId: "A", metric: "temperature"}

Bucket phù hợp khoảng cũ: 08:59
Bucket phù hợp khoảng mới: 09:00, 09:01, 09:02
```

Sơ đồ trên chỉ mang tính khái niệm, không cam kết mỗi giờ chỉ có một bucket. Các tình huống mở bucket mới gồm:

- Không có bucket active phù hợp `metaField`.
- Timestamp nằm ngoài time span của những bucket active.
- Bucket đạt giới hạn measurement hoặc kích thước.
- Bucket bị đóng do tài nguyên, restart hoặc hoạt động xung đột.

MongoDB làm tròn timestamp lúc tạo bucket theo cấu hình bucketing, hỗ trợ những timestamp **đến không đúng thứ tự trong khoảng gần nhau**. Nhưng không nên hứa rằng mọi event cũ đều được append đúng bucket cũ với chi phí bằng insert mới. Late backfill có thể tạo thêm buckets, I/O và cache pressure.

### 3.1. Chọn metaField ổn định

Tốt:

```javascript
meta: {
  tenantId: "factory-1",
  deviceId: "sensor-A",
  metric: "temperature"
}
```

Không nên đặt `receivedAt`, `requestId` hoặc `retryCount` (đổi theo mỗi lần gửi) vào `metaField`. Meta thay đổi thường xuyên tạo nhiều buckets ít measurements và làm giảm hiệu quả nén/lọc.

### 3.2. Granularity không phải chính sách “late tối đa”

`granularity` có các giá trị `seconds`, `minutes`, `hours`. Tùy phiên bản còn có `bucketMaxSpanSeconds` và `bucketRoundingSeconds`. Đây là cấu hình **bucketing** theo khoảng thời gian và tốc độ đo, **không phải** ngưỡng allowed lateness của ingestion pipeline.

Đừng đặt `granularity: "hours"` chỉ vì muốn chấp nhận sự kiện muộn hai giờ; phải benchmark tần suất đo, kích thước bucket và query.

## 4. Giới hạn đặc biệt: time series collection không phải collection thường

Các hạn chế sau ảnh hưởng trực tiếp đến cách xử lý duplicate và correction:

| Tính năng | Time series collection | Hệ quả |
| --- | --- | --- |
| **Unique index** | **Không hỗ trợ** | Không tạo unique index trên device/time/eventId trực tiếp được |
| `_id` index mặc định | **Không tạo unique `_id` index mặc định** | `_id` cố định không tự chặn duplicate |
| Update | Bị hạn chế theo `metaField`, không sửa tùy ý measurement field, không upsert | Không xử lý correction bằng update value thông thường |
| Write trong transaction | **Không hỗ trợ** | Không transaction nguyên tử insert registry và insert time series |
| `$merge` vào time series | **Không hỗ trợ** | Không dùng aggregation `$merge` để upsert vào time series |
| Schema validation rules | Không hỗ trợ như regular collection | Cần validation ở application/staging |
| Aggregation đọc | Có hỗ trợ với giới hạn phù hợp | Dùng `$sort`, `$group` để phát hiện/canonicalize |

Các quy tắc thay đổi theo MongoDB version. Khi triển khai, kiểm tra đúng **server, feature compatibility version và driver** đang dùng.

Ví dụ **không hợp lệ**:

```javascript
db.measurements.createIndex(
  { "meta.deviceId": 1, observedAt: 1 },
  { unique: true }
);
```

Ví dụ **không thiết kế** cho time series:

```javascript
db.measurements.updateOne(
  { "meta.deviceId": "sensor-A", observedAt: someTime },
  { $set: { value: 25 } },
  { upsert: true }
);
```

Lưu ý: MongoDB time series không có unique `_id` index mặc định. **Deterministic `_id` không tự mang lại idempotency** nếu không có cơ chế uniqueness được hỗ trợ.

## 5. Khởi tạo lab time-series

Các ví dụ chạy trong `mongosh`, trên MongoDB hỗ trợ time series collection. Chỉ dùng database riêng; **không chạy `drop()` trên production**.

```javascript
const lab = db.getSiblingDB("ts_late_duplicate_lab");

lab.measurements.drop();
lab.ingestKeys.drop();
lab.canonicalReadings.drop();

lab.createCollection("measurements", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  }
});
```

Thiết kế logical measurement trong lab:

```javascript
{
  eventId: "A-0901-r1",
  sampleId: "09:01",
  revision: 1,
  meta: {
    tenantId: "factory-1",
    deviceId: "sensor-A",
    metric: "temperature"
  },
  observedAt: ISODate("2026-11-14T09:01:00Z"),
  receivedAt: ISODate("2026-11-14T09:03:10Z"),
  value: 21,
  unit: "C"
}
```

- `eventId`: danh tính **một event nguồn**, có thể được gửi lại.
- `sampleId`: danh tính **một phép đo logic**, có thể có nhiều revisions.
- `revision`: số phiên bản hiệu chỉnh.
- `meta`: series identity ổn định.
- `observedAt`: thời gian nghiệp vụ làm trục của time series.

`sampleId: "09:01"` chỉ dùng cho fixture trong cùng ngày. Production phải dùng sampleId bền vững qua ngày, ví dụ source sequence + boot ID hoặc timestamp đầy đủ kèm channel.

## 6. Fixture 12 raw measurements: out-of-order + retry + correction

Dùng ba cảm biến A, B, C cùng metric nhiệt độ. Mảng dưới đây được sắp **theo thời gian nhận giả định**, trong khi một số `observedAt` không tăng đều. `receivedAt` là timestamp cố định để dễ đối chiếu; một lệnh `insertMany` không mô phỏng các khoảng chờ thực tế giữa từng event.

```javascript
const a = {
  tenantId: "factory-1",
  deviceId: "sensor-A",
  metric: "temperature"
};

const b = {
  tenantId: "factory-1",
  deviceId: "sensor-B",
  metric: "temperature"
};

const c = {
  tenantId: "factory-1",
  deviceId: "sensor-C",
  metric: "temperature"
};

lab.measurements.insertMany([
  {
    eventId: "A-0900-r1", sampleId: "09:00", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:05Z"),
    value: 20, unit: "C"
  },
  {
    eventId: "B-0900-r1", sampleId: "09:00", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:10Z"),
    value: 30, unit: "C"
  },
  {
    eventId: "C-0900-r1", sampleId: "09:00", revision: 1,
    meta: c,
    observedAt: ISODate("2026-11-14T09:00:00Z"),
    receivedAt: ISODate("2026-11-14T09:00:15Z"),
    value: 18, unit: "C"
  },
  {
    eventId: "B-0901-r1", sampleId: "09:01", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:01:10Z"),
    value: 31, unit: "C"
  },
  {
    eventId: "C-0901-r1", sampleId: "09:01", revision: 1,
    meta: c,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:01:20Z"),
    value: 20, unit: "C"
  },
  {
    eventId: "A-0902-r1", sampleId: "09:02", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:02:00Z"),
    receivedAt: ISODate("2026-11-14T09:02:02Z"),
    value: 22, unit: "C"
  },
  {
    eventId: "A-0859-r1", sampleId: "08:59", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T08:59:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:00Z"),
    value: 19, unit: "C"
  },
  {
    eventId: "B-0903-r1", sampleId: "09:03", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:03:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:05Z"),
    value: 33, unit: "C"
  },
  {
    eventId: "A-0901-r1", sampleId: "09:01", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:10Z"),
    value: 21, unit: "C"
  },
  // Retry cùng eventId, revision và payload nguồn.
  {
    eventId: "A-0901-r1", sampleId: "09:01", revision: 1,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:03:15Z"),
    value: 21, unit: "C"
  },
  // Correction: cùng logical sample, revision mới.
  {
    eventId: "A-0901-r2", sampleId: "09:01", revision: 2,
    meta: a,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:04:00Z"),
    value: 21.5, unit: "C"
  },
  // Bản retry muộn của B.
  {
    eventId: "B-0901-r1", sampleId: "09:01", revision: 1,
    meta: b,
    observedAt: ISODate("2026-11-14T09:01:00Z"),
    receivedAt: ISODate("2026-11-14T09:05:00Z"),
    value: 31, unit: "C"
  }
]);

lab.measurements.countDocuments({});
// 12
```

Dataset có:

- **12 raw documents**.
- **10 `eventId` khác nhau**.
- **2 extra deliveries** do retry (`A-0901-r1` và `B-0901-r1`).
- **1 revision correction** (`A-0901-r2`).
- **9 logical measurements** sau khi dedup và chọn revision.

Đây là quy ước đúng với fixture, không phải MongoDB tự phát hiện trùng.

## 7. Đọc theo event time, không tin insert order

```javascript
lab.measurements.find(
  { "meta.deviceId": "sensor-A" },
  {
    _id: 0,
    eventId: 1,
    observedAt: 1,
    receivedAt: 1,
    revision: 1,
    value: 1
  }
).sort({
  observedAt: 1,
  revision: 1,
  receivedAt: 1
}).toArray();
```

Các bản của sensor-A, theo event time:

| observedAt (UTC) | eventId | receivedAt | value |
| --- | --- | --- | ---: |
| 08:59 | A-0859-r1 | 09:03:00 | 19 |
| 09:00 | A-0900-r1 | 09:00:05 | 20 |
| 09:01 | A-0901-r1 | 09:03:10 | 21 |
| 09:01 | A-0901-r1 | 09:03:15 | 21 |
| 09:01 | A-0901-r2 | 09:04:00 | 21.5 |
| 09:02 | A-0902-r1 | 09:02:02 | 22 |

Nếu không có `.sort()`, query không có cam kết trả theo `observedAt`, `receivedAt`, `_id` hay thứ tự bucket. Khi cùng timestamp, phải định nghĩa các **tie-breakers** phù hợp, chẳng hạn revision và eventId.

## 8. Tính độ trễ từng event với $dateDiff

```javascript
lab.measurements.aggregate([
  {
    $set: {
      delaySeconds: {
        $dateDiff: {
          startDate: "$observedAt",
          endDate: "$receivedAt",
          unit: "second"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      eventId: 1,
      "meta.deviceId": 1,
      observedAt: 1,
      receivedAt: 1,
      delaySeconds: 1
    }
  },
  { $sort: { delaySeconds: -1, eventId: 1 } }
]).toArray();
```

Độ trễ một số bản ghi:

| eventId | observedAt | receivedAt | delay |
| --- | --- | --- | ---: |
| A-0859-r1 | 08:59 | 09:03:00 | 240 s |
| B-0901-r1 (retry) | 09:01 | 09:05:00 | 240 s |
| A-0901-r2 | 09:01 | 09:04:00 | 180 s |
| A-0901-r1 (retry) | 09:01 | 09:03:15 | 135 s |
| A-0901-r1 (lần đầu) | 09:01 | 09:03:10 | 130 s |

Tìm raw documents muộn trên 120 giây:

```javascript
lab.measurements.aggregate([
  {
    $set: {
      delaySeconds: {
        $dateDiff: {
          startDate: "$observedAt",
          endDate: "$receivedAt",
          unit: "second"
        }
      }
    }
  },
  { $match: { delaySeconds: { $gt: 120 } } },
  {
    $project: {
      _id: 0,
      eventId: 1,
      delaySeconds: 1
    }
  }
]).toArray();
```

Có **5 raw documents** vượt 120 giây. Nhưng **độ trễ cao không đồng nghĩa phải drop event**: event có thể là backfill hợp lệ.

Lưu ý `$dateDiff` đơn vị giây tính theo ranh giới của đơn vị; với precision sub-second hoặc clock skew, có thể cần tính toán trên milliseconds để đo đúng hơn.

## 9. Cần xác định “duplicate” ở mức nào

Các trường hợp:

| Dữ liệu nhận | Có phải duplicate? | Chính sách phù hợp |
| --- | --- | --- |
| Cùng `eventId`, payload nguồn giống nhau | Thường là **retry** | Không tính thêm measurement |
| Cùng `sampleId`, revision mới | **Correction**, không phải retry | Chọn revision mới theo quy tắc |
| Hai device cùng đo lúc 09:01 | Không | Mỗi device một series |
| Cùng device và timestamp nhưng channel khác | Không nhất thiết | Thêm metric/channel vào identity |
| Cùng giá trị đo nhưng hai `eventId` thật | Không đủ căn cứ gộp | Giữ nếu là hai phép đo hợp lệ |
| Cùng `eventId` nhưng payload khác | **Conflict** | Quarantine và đối soát |
| Sequence reset sau reboot | Có thể collision | Thêm `bootId` hoặc epoch vào key |
| Job backfill gửi lại data cũ | Có thể là retry hoặc correction | So sánh identity và revision |

Những identity đề xuất:

```text
Delivery identity:
  (tenantId, eventId)

Logical sample:
  (tenantId, deviceId, metric, sampleId)

Version:
  (tenantId, deviceId, metric, sampleId, revision)
```

Nếu chỉ dựa vào `(deviceId,observedAt)`, hai phép đo khác nhau cùng millisecond có thể bị gộp sai. `sampleId` nên được tạo bởi nguồn theo hợp đồng, không phải đoán từ timestamp nếu sampling rate không cho phép.

### 9.1. Payload fingerprint cho conflict

Tính hash của **canonical source payload** (chẳng hạn SHA-256) trước bước lưu. Khi cùng eventId được gửi lại:

- Hash giống: nhiều khả năng là retry.
- Hash khác: không im lặng bỏ qua; cần quarantine.
- `receivedAt` không nên nằm trong hash của payload nguồn vì mỗi lần retry có thể có ingestion timestamp khác.
- Nếu nguồn đã hiệu chỉnh số đo, nên phát hành **revision/eventId mới**, không tái sử dụng eventId cũ với giá trị khác.

Hash là công cụ so sánh payload có điều kiện; không tự quyết định semantics correction.

## 10. Phát hiện retry trùng eventId

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        eventId: "$eventId"
      },
      copies: { $sum: 1 },
      firstSeen: { $min: "$receivedAt" },
      lastSeen: { $max: "$receivedAt" }
    }
  },
  { $match: { copies: { $gt: 1 } } },
  { $sort: { "_id.eventId": 1 } }
]).toArray();
```

Kết quả:

| eventId | copies | extra deliveries |
| --- | ---: | ---: |
| A-0901-r1 | 2 | 1 |
| B-0901-r1 | 2 | 1 |

Đếm số event IDs duy nhất và số bản thừa:

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        eventId: "$eventId"
      },
      n: { $sum: 1 }
    }
  },
  {
    $group: {
      _id: null,
      distinctEvents: { $sum: 1 },
      extraDeliveries: {
        $sum: { $subtract: ["$n", 1] }
      }
    }
  }
]).toArray();

// distinctEvents: 10
// extraDeliveries: 2
```

Việc group theo `eventId` **không** xóa correction `A-0901-r2`, vì correction có eventId mới. Muốn một giá trị cho mỗi phép đo logic phải group theo `sampleId` và chọn revision.

## 11. Chọn canonical revision cho mỗi logical sample

Quy tắc của fixture:

1. Mỗi logical measurement được xác định bằng `tenantId`, `deviceId`, `metric`, `sampleId`.
2. Revision lớn nhất là giá trị được chọn.
3. Nếu cùng revision được gửi lại, dùng `receivedAt` và `eventId` làm tie-breaker mang tính quyết định.
4. **Nếu cùng revision nhưng payload khác** trong hệ thống thật, không nên tùy ý chọn bản mới đến; cần conflict resolution.

```javascript
const canonicalPrefix = [
  {
    $sort: {
      "meta.tenantId": 1,
      "meta.deviceId": 1,
      "meta.metric": 1,
      sampleId: 1,
      revision: -1,
      receivedAt: -1,
      eventId: -1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$meta.tenantId",
        deviceId: "$meta.deviceId",
        metric: "$meta.metric",
        sampleId: "$sampleId"
      },
      latest: { $first: "$$ROOT" },
      rawCopiesAndVersions: { $sum: 1 }
    }
  }
];

lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $project: {
      _id: 0,
      deviceId: "$_id.deviceId",
      sampleId: "$_id.sampleId",
      observedAt: "$latest.observedAt",
      revision: "$latest.revision",
      value: "$latest.value",
      eventId: "$latest.eventId",
      rawCopiesAndVersions: 1
    }
  },
  { $sort: { deviceId: 1, observedAt: 1 } }
]).toArray();
```

Kết quả canonical:

| Device | sampleId | revision | value |
| --- | --- | ---: | ---: |
| A | 08:59 | 1 | 19 |
| A | 09:00 | 1 | 20 |
| A | 09:01 | **2** | **21.5** |
| A | 09:02 | 1 | 22 |
| B | 09:00 | 1 | 30 |
| B | 09:01 | 1 | 31 |
| B | 09:03 | 1 | 33 |
| C | 09:00 | 1 | 18 |
| C | 09:01 | 1 | 20 |

Tổng **9 logical measurements**.

### 11.1. Vì sao phải $sort trước $first?

`$first` trong `$group` chỉ có ý nghĩa nghiệp vụ khi thứ tự đầu vào đã được xác định. Không có `$sort` rõ, nó không tự hiểu “revision cao nhất”.

Nếu hai event cùng revision nhưng nhận ở hai worker khác nhau, `receivedAt` là **tie-breaker**, không phải bằng chứng giá trị nào chính xác. Bảo đảm đúng cần revision monotonic hoặc source priority do nghiệp vụ cung cấp.

## 12. Duplicate làm sai các phép tổng hợp

Nếu tính trung bình trực tiếp trên raw documents:

```javascript
lab.measurements.aggregate([
  {
    $group: {
      _id: "$meta.deviceId",
      count: { $sum: 1 },
      rawAverage: { $avg: "$value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Device | Raw count | Raw average |
| --- | ---: | ---: |
| A | 6 | **20.75** |
| B | 4 | **31.25** |
| C | 2 | **19** |

Sau khi chọn canonical:

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $group: {
      _id: "$_id.deviceId",
      logicalCount: { $sum: 1 },
      canonicalAverage: { $avg: "$latest.value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Device | Logical count | Canonical average |
| --- | ---: | ---: |
| A | 4 | **20.625** |
| B | 3 | **31.333333…** |
| C | 2 | **19** |

A có 6 raw records nhưng chỉ 4 logical samples: revision 1 của 09:01 bị gửi hai lần và revision 2 là correction. B có một bản retry. C không có retry/correction.

**Chỉ loại duplicate theo eventId vẫn chưa đủ:** hai revisions khác eventId vẫn trỏ đến một logical sample. Nếu domain muốn một giá trị hiện hành, phải chọn revision.

Không phải metric nào cũng chọn revision mới nhất: số dư/counter, giao dịch tài chính hay log event có thể cần *compensating event*, không phải ghi đè. Quy tắc đến từ domain.

## 13. Window aggregation phải dựa trên event time

Một dashboard tính trung bình mỗi phút nên dùng `observedAt` khi câu hỏi là **“giá trị lúc đó”**, không phải thời điểm gateway nhận.

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $set: {
      minuteStart: {
        $dateTrunc: {
          date: "$latest.observedAt",
          unit: "minute",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: "$minuteStart",
      samples: { $sum: 1 },
      average: { $avg: "$latest.value" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Kết quả:

| Minute UTC | Logical samples | Tổng value | Average |
| --- | ---: | ---: | ---: |
| 08:59 | 1 | 19 | 19 |
| 09:00 | 3 | 68 | 22.666667 |
| 09:01 | 3 | 72.5 | 24.166667 |
| 09:02 | 1 | 22 | 22 |
| 09:03 | 1 | 33 | 33 |

### 13.1. Late arrival làm thay đổi window đã hiển thị

Giả sử lúc 09:02 dashboard tính window `[09:01,09:02)` nhưng A chưa gửi phép đo của 09:01.

Kết quả ban đầu chỉ có B và C:

```text
(31 + 20) / 2 = 25.5
```

Sau khi A gửi revision 1:

```text
(31 + 20 + 21) / 3 = 24
```

Sau khi A gửi correction revision 2:

```text
(31 + 20 + 21.5) / 3 ≈ 24.166667
```

Nếu dashboard công bố 25.5 là **final** ngay lúc 09:02 và không cho sửa, nó sẽ không phản ánh dữ liệu hợp lệ đến muộn.

Với window theo phút, dùng ranh giới dạng **`[start, end)`**: bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc. Một event tại 09:02:00 thuộc window tiếp theo, không thuộc `[09:01,09:02)`.

## 14. Allowed lateness và watermark

**Allowed lateness** là chính sách ứng dụng/stream processor cho phép kết quả cửa sổ thay đổi sau khi window nominally kết thúc.

Ví dụ:

```text
Window:          [09:01, 09:02)
Allowed lateness: 3 phút
```

Nhưng cần định nghĩa **theo loại thời gian nào**:

- Đếm từ window end theo wall-clock/processing time?
- Dựa trên tiến triển event-time watermark?
- Watermark theo từng device, partition hay toàn stream?
- Khi device ngừng gửi, watermark có tiếp tục tiến không?
- Event rất muộn bị drop, quarantine hay đưa vào backfill?

**MongoDB time series collection không tự đóng event-time windows hoặc cấp watermark.** MongoDB lưu measurements; logic finalization thuộc tầng processing.

### 14.1. Watermark minh họa

Một mô hình đơn giản:

```text
watermark = maxObservedEventTimeSeen - maxExpectedOutOfOrderDelay
```

Giả sử:

```text
Max event time đã thấy:       09:05:00
Expected out-of-order delay:  2 phút
Watermark:                    09:03:00
```

Theo chính sách processor, những window kết thúc trước hoặc tại watermark có thể được đánh dấu đã hoàn thành **với mức tin cậy đã chọn**.

Tuy nhiên event 09:01 vẫn có thể đến sau thời điểm này. Watermark là **ước lượng về tiến triển event time**, không phải lời hứa rằng không bao giờ có event cũ hơn.

Với nguồn song song, watermark có thể cần xử lý **idle partition**. Không mặc định watermark luôn bằng `receivedAt - 2 phút`.

### 14.2. Trạng thái provisional, final, revised

| Trạng thái | Ý nghĩa | Khi có event muộn |
| --- | --- | --- |
| `provisional` | Window chưa đóng theo policy | Cập nhật kết quả |
| `final` | Đã qua hạn expected lateness | Có thể giữ nguyên hoặc xét correction policy |
| `revised` | Late/corrected data làm thay đổi kết quả final | Ghi revision và phát tín hiệu downstream |

Khi materialize aggregate, nên lưu:

```javascript
{
  windowStart: ISODate("2026-11-14T09:01:00Z"),
  windowEnd: ISODate("2026-11-14T09:02:00Z"),
  revision: 2,
  status: "revised",
  average: 24.1666666667,
  sampleCount: 3,
  computedAt: new Date()
}
```

`revision` của **window aggregate** khác với revision của **mỗi phép đo**. Downstream cần biết khi một kết quả đã công bố bị thay đổi.

## 15. Ba kiến trúc xử lý trùng

| Chiến lược | Cách làm | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **A. Raw append + dedup khi đọc** | Ghi tất cả events vào time series; chọn canonical lúc query | Đơn giản, giữ audit | Tốn storage/aggregation |
| **B. Unique inbox + time series sink** | Chặn trùng eventId ở collection thường rồi append | Bảo vệ điểm tiếp nhận nhiều writer | Dual-write không atomic |
| **C. Canonical store thường + time-series projection** | Uniqueness/updates ở regular collection; time series phục vụ analytics | Nguồn đúng mạnh và version control | Materialization có lag và thêm vận hành |

Không có giải pháp chung duy nhất. Cần chọn theo độ chính xác, retention, latency, tải dữ liệu và chấp nhận eventual consistency.

## 16. Chiến lược A: raw append, dedup khi truy vấn

Điểm mạnh:

- Ghi trực tiếp `insertOne`/`insertMany` vào time series.
- Không phải cập nhật measurements đã ghi.
- Có thể xử lý correction bằng revision mới.
- Raw events có giá trị audit và có thể reprocess.

Điểm yếu:

- Retry tạo thêm raw documents.
- Aggregation canonical dùng `$sort` + `$group` tốn tài nguyên.
- Báo cáo đã materialize phải được tính lại khi late event xuất hiện.
- Nếu TTL đã xóa raw, có thể không thể rebuild lịch sử.

Trên collection lớn, hãy **lọc series và khoảng thời gian trước khi group**:

```javascript
lab.measurements.aggregate([
  {
    $match: {
      "meta.deviceId": "sensor-A",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T10:00:00Z")
      }
    }
  },
  {
    $sort: {
      sampleId: 1,
      revision: -1,
      receivedAt: -1,
      eventId: -1
    }
  },
  {
    $group: {
      _id: "$sampleId",
      newest: { $first: "$$ROOT" }
    }
  },
  { $replaceRoot: { newRoot: "$newest" } },
  { $sort: { observedAt: 1 } }
]).toArray();
```

Đoạn này chỉ group theo `sampleId` vì query đã khóa vào một device và một khoảng ngắn trong fixture. Production cần group theo **đầy đủ logical identity** nếu sampleId không unique toàn phạm vi.

## 17. Chiến lược B: unique inbox ở collection thường

Time series **không hỗ trợ unique indexes**, nhưng **collection thường** có.

```javascript
lab.ingestKeys.createIndex(
  { tenantId: 1, eventId: 1 },
  {
    unique: true,
    name: "uq_tenant_event"
  }
);
```

Thử claim một event:

```javascript
lab.ingestKeys.insertOne({
  tenantId: "factory-1",
  eventId: "A-0901-r1",
  payloadFingerprint: "sha256-of-canonical-source-payload",
  state: "pending",
  createdAt: new Date()
});
```

Nếu hai workers cố insert hai entries cùng `(tenantId,eventId)`, unique index ngăn cả hai tạo hai registry documents. Lỗi phổ biến là `E11000`.

### 17.1. Upsert áp dụng cho registry, không phải time series

```javascript
const result = lab.ingestKeys.updateOne(
  {
    tenantId: "factory-1",
    eventId: "A-0902-r1"
  },
  {
    $setOnInsert: {
      payloadFingerprint: "source-payload-hash",
      state: "pending",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(result);
```

Bộ lọc equality khớp unique key giúp chống hai registry entries cùng danh tính. Trong cạnh tranh, upsert vẫn có điều kiện để MongoDB xử lý thành update hoặc trả duplicate key; ứng dụng cần error path.

Nếu một eventId đã có, đọc registry entry rồi so sánh fingerprint; **không coi mọi E11000 là cùng payload**.

### 17.2. Crash giữa hai collection: không có atomic dual-write

Một pipeline đơn giản:

```text
1. Insert registry claim (unique)
2. Insert measurement vào time series
3. Update registry state = delivered
```

Các khoảng lỗi:

| Crash | Registry | Time series | Rủi ro |
| --- | --- | --- | --- |
| Sau bước 1, trước bước 2 | `pending` | Chưa có | Bỏ qua pending sẽ mất phép đo |
| Sau bước 2, trước bước 3 | `pending` | Đã có | Retry append có thể tạo duplicate |
| Sau bước 3 | `delivered` | Dự kiến có | Vẫn xét write concern và network ambiguity |

Không thể đặt insert time-series và insert registry vào **một MongoDB transaction ghi** vì time series collections không hỗ trợ transaction writes.

Vì vậy **unique registry chống trùng ở điểm đăng ký, không tự đảm bảo exactly-once raw append**.

### 17.3. At-most-once, at-least-once, exactly-once logical result

- **At-most-once append:** không retry một write không rõ kết quả; giảm duplicate nhưng có thể mất event.
- **At-least-once append:** retry để giảm khả năng mất dữ liệu, nhưng có thể tạo nhiều raw documents.
- **Exactly-once logical result:** cần canonical identity và dedup/revision resolution, hoặc chọn regular collection có unique constraint làm source of truth.

Nếu downstream yêu cầu không có logical duplicates, đừng lấy số raw documents như số phép đo.

## 18. Chiến lược C: canonical collection thường

Với nguồn dữ liệu cần uniqueness mạnh và corrections có kiểm soát, collection thường có thể lưu **bản canonical**.

```javascript
lab.canonicalReadings.createIndex(
  {
    tenantId: 1,
    deviceId: 1,
    metric: 1,
    sampleId: 1
  },
  {
    unique: true,
    name: "uq_canonical_sample"
  }
);
```

Regular collection hỗ trợ unique indexes và những atomic conditional update/upsert theo semantics của nó. Có thể lưu current revision và giữ lịch sử revision trong collection khác để audit.

Time series collection vẫn hữu ích làm raw compressed telemetry/analytics, nhưng đồng bộ sang nó là **materialization có thể trễ**.

### 18.1. Materialize từ time series sang collection thường

MongoDB cho phép `$merge` **từ** time series vào **regular collection**. Không dùng time series làm đích của `$merge`.

```javascript
lab.measurements.aggregate([
  ...canonicalPrefix,
  {
    $project: {
      _id: 1,
      tenantId: "$_id.tenantId",
      deviceId: "$_id.deviceId",
      metric: "$_id.metric",
      sampleId: "$_id.sampleId",
      observedAt: "$latest.observedAt",
      revision: "$latest.revision",
      value: "$latest.value",
      eventId: "$latest.eventId"
    }
  },
  {
    $merge: {
      into: "canonicalReadings",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);

lab.canonicalReadings.countDocuments({});
// 9
```

`_id` trong output là object xác định logical sample. Collection thường có unique `_id` index; `$merge` cập nhật mỗi canonical document theo khóa này.

Đây là **full batch reconciliation cho lab**. Ở production, nếu hai jobs materialize cùng dữ liệu nhưng cắt theo khoảng/khác thời điểm, job đến sau có thể ghi đè kết quả bằng revision cũ. Cần checkpoint, job serialization hoặc version-aware compare-and-set.

Ví dụ **không hợp lệ** khi time series là đích:

```javascript
db.rawInput.aggregate([
  {
    $merge: {
      into: "measurements",
      whenMatched: "replace"
    }
  }
]);
```

## 19. Correction: append revision hay cập nhật canonical?

Một correction có thể được mô hình hóa:

```text
A:09:01 revision 1 = 21.0
A:09:01 revision 2 = 21.5
```

Ba cách:

1. **Append revisions:** giữ cả hai trong time series; query chọn revision 2.
2. **Canonical mutable store:** regular collection giữ giá trị hiện hành và revision; các correction có thể được kiểm soát bằng conditional update.
3. **Compensating event:** thay vì ghi đè, phát event mới điều chỉnh effect của event cũ; thường phù hợp các domain kế toán.

Điều không nên làm là sửa `value` trực tiếp trên time-series document bằng một upsert như collection thường.

Nếu hai nguồn cùng gửi revision 2 nhưng payload khác, policy phải xác định conflict/quarantine, không mặc định "bản có receivedAt lớn hơn là đúng".

## 20. TTL có thể loại bỏ phép đo đến quá muộn

Tạo collection time-series khác có retention 24 giờ:

```javascript
lab.shortRetention.drop();

lab.createCollection("shortRetention", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 86400
});
```

TTL time series dựa trên **`timeField`**, ở đây là `observedAt`, chứ không phải giờ `receivedAt`. MongoDB dọn measurements/buckets hết hạn theo cơ chế background, không xóa chính xác ngay tại millisecond hết hạn.

Nếu thiết bị hôm nay gửi lại một event có `observedAt` từ **ba ngày trước**, event có thể được nhận nhưng đã quá thời hạn retention và có thể được dọn trong chu kỳ TTL thích hợp.

Không được hứa “mọi event được giữ 24 giờ kể từ lúc ingest” khi TTL được tính từ event time.

### 20.1. Câu hỏi khi phối hợp TTL và allowed lateness

- Retention dài hơn cửa sổ late arrivals cần xử lý không?
- Có backfill dữ liệu nhiều ngày hoặc nhiều tuần không?
- Raw events có còn để rebuild aggregation không?
- Đã có canonical source bền vững ở nơi khác chưa?
- Dữ liệu bị delete theo TTL có được đối soát với dashboard hay không?

Một số hệ thống cần raw hot retention ngắn và archive lâu dài ở kho khác để hỗ trợ backfill/compliance.

## 21. Out-of-order ảnh hưởng hiệu năng ra sao?

Các yếu tố cần đo:

- Event cũ không còn bucket active phù hợp → có thể mở bucket khác.
- Rất nhiều unique meta values → bucket catalog có nhiều buckets ít measurements.
- Backfill rộng → tăng I/O/cache và cạnh tranh với realtime ingestion.
- Retry → tăng storage và chi phí dedup.
- Correction → tăng số revision/documents của cùng sample.
- Sort/group trên toàn dataset → aggregation memory/CPU cao.
- TTL + backfill → vừa ingest vừa có thể dọn những buckets cũ.
- Secondary read có thể trễ hơn nếu replication đang chịu tải.

**Không nên** thay đổi `granularity` một cách mù quáng chỉ vì có late arrivals. Granularity phải phản ánh tần suất đo và mục tiêu bucket density. Việc điều chỉnh bucket parameters sau khi tạo có các giới hạn theo phiên bản.

Đối với query lớn, pre-filter theo `meta` và time range trước khi dedup, kiểm tra indexes phù hợp, theo dõi số keys/docs examined và tài nguyên.

## 22. Dùng buffer/sort trước khi ghi: lợi ích và giới hạn

Một pipeline có thể gom một ít events trước khi append:

```text
Devices
   |
Gateway
   |
Buffer theo device (ngắn, có giới hạn)
   |
Sort by observedAt
   |
Batch insert vào time series
```

Ưu điểm:

- Giảm out-of-order nhỏ do network.
- Có thể batch inserts và cải thiện hiệu quả.
- Có thể loại một số retries trong buffer window.

Nhược điểm:

- Tăng latency.
- Đòi memory/queue và persistence.
- Late events sau nhiều giờ vẫn đến ngoài buffer.
- Nhiều worker có thể reorder nếu không partition/coordinate.
- Buffer không thay unique registry, correction handling hay idempotency.

**Buffer là tối ưu ingestion**, không phải ràng buộc toàn cục.

## 23. Quy trình backfill an toàn

Khi nhập lại dữ liệu lịch sử, cần:

1. Xác định nguồn dữ liệu authoritative.
2. Giữ `observedAt` gốc, không gán bằng thời điểm import.
3. Giữ hoặc tạo eventId ổn định qua nhiều lần chạy import.
4. Ghi nhận logical sampleId và revision.
5. Kiểm tra TTL của time series đích.
6. Chạy theo batch có throttle, không tranh toàn bộ I/O với realtime ingestion.
7. Dùng checkpoint để có thể resume sau crash.
8. Đếm raw events, unique event IDs, corrections và conflicts.
9. Tính lại những event-time windows bị ảnh hưởng.
10. Cập nhật revision của aggregates đã materialize và phát thông tin downstream.
11. Đối chiếu data integrity với nguồn.
12. Có khả năng rollback/rebuild canonical output nếu mapping sai.

Ví dụ một event đo lúc 09:01 được backfill lúc 15:00:

```javascript
{
  observedAt: ISODate("2026-11-14T09:01:00Z"),
  receivedAt: ISODate("2026-11-14T15:00:00Z")
}
```

Báo cáo **event time** phải tính nó vào phút 09:01. Bộ chỉ số **ingestion latency** mới sử dụng 15:00 để đo độ trễ.

## 24. Kiến trúc production tham khảo

```text
Devices / Broker
       |
       v
  Ingestion API
       |
  Validate schema,
  normalize UTC / ID
       |
       v
  Regular inbox with
  UNIQUE(tenantId,eventId)
       |
  Durable queue/outbox
       |
       v
  Time series raw sink
       |
  Dedup/revision resolver
       |
  Canonical measurements
  / window aggregates
       |
  Dashboard / APIs
```

Đây là **sơ đồ logic**, không có nghĩa mọi bước cùng commit nguyên tử.

### 24.1. Validation tại ingress

- `observedAt` là Date hợp lệ, timestamp không vô lý.
- Tenant/device/metric đúng định dạng và quyền truy cập.
- Event identity không bị tái sử dụng.
- `revision` đúng quy tắc nguồn.
- Value/unit đúng kiểu/phạm vi.
- `receivedAt` được gán nhất quán.
- Check clock skew/future timestamps.
- Có chính sách quarantine khi dữ liệu mâu thuẫn.

Time series collections không hỗ trợ schema validation rules tương đương regular collection; validation phải ở tầng ingest hoặc regular staging.

### 24.2. Durable processing và reconciliation

Registry có thể lưu `pending`, `processing`, `delivered`, `failed` cùng retry count/last error/checkpoint. Cần xử lý:

- Worker chết sau claim, trước append.
- Worker chết sau append, trước đánh dấu delivered.
- Ambiguous write result khi network timeout.
- Retry trùng eventId nhưng payload khác.
- Correction đến trước bản gốc.
- Backfill sau khi window đã final.
- TTL xóa raw trước khi downstream reconcile.

Nếu không chứng minh được exactly-once raw append, thiết kế canonical/read-time dedup để bảo đảm **kết quả logic** không đếm trùng.

### 24.3. Monitoring

Nên theo dõi:

- Ingest throughput, p95/p99 write latency.
- P50/p95/p99 của `receivedAt - observedAt`.
- Tỷ lệ out-of-order theo device và source.
- Tỷ lệ late trên ngưỡng nghiệp vụ.
- Duplicate eventId rate và payload-conflict rate.
- Correction revisions per sample.
- Raw count / canonical count ratio.
- Số window aggregates bị sửa.
- Registry pending quá lâu.
- Reconciliation lag và recovery backlog.
- Bucket/storage efficiency, cache/I/O.
- TTL cleanup, backfill queue, dead-letter rate.

Chỉ đo insert success rate là không đủ để biết báo cáo đang đúng.

## 25. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng receivedAt làm timeField cho dữ liệu theo event time | Báo cáo bị lệch thời điểm | Giữ observedAt và lưu receivedAt riêng |
| Coi insert order là chronological order | Sai thứ tự hiển thị | `.sort({observedAt:1,...})` |
| Coi out-of-order là dữ liệu lỗi | Mất late readings hợp lệ | Xác định allowed lateness |
| Tạo unique index trực tiếp trên time series | Không được hỗ trợ | Regular registry/canonical collection |
| Tin rằng `_id` time series tự unique | Có thể lưu duplicate | Không dùng `_id` thay unique constraint |
| Upsert value/timeField để sửa measurement | Bị hạn chế | Append revision hoặc regular canonical |
| Dùng `$merge` để upsert vào time series | Target không được hỗ trợ | `$merge` vào regular collection |
| Ghi vào time series trong transaction | Không hỗ trợ | Thiết kế recoverable dual-write |
| Unique registry đồng nghĩa exactly-once TS append | Crash có thể gây gap/duplicate | Reconciliation + canonical dedup |
| Dedup bằng value bằng nhau | Hai phép đo khác nhau có thể cùng value | Dùng event/source ID |
| Dedup chỉ bằng timestamp | Các device/channel cùng lúc bị gộp | Identity đầy đủ |
| Bỏ mọi revision >1 vì cho là retry | Mất correction | Phân biệt eventId và sampleId |
| Chọn receivedAt mới nhất bất kể revision | Reorder có thể chọn bản sai | Source revision/priority |
| Nghĩ granularity là allowed lateness | Window đóng sai | Watermark ở processor |
| Nghĩ watermark ngăn mọi event cũ | Event có thể đến muộn hơn dự đoán | Late policy + backfill |
| Nghĩ TTL tính từ lúc nhận | Event cũ có thể bị dọn sớm | Retention theo timeField |
| Không giám sát clock skew | Late/future classification sai | NTP/normalization |
| Tính trung bình trên raw retries | Thống kê bị lệch | Dedup trước aggregation |
| Backfill quá nhanh vào realtime cluster | I/O/bucket churn tăng | Throttle, checkpoint |
| Không có window revision khi aggregate đổi | Downstream không biết dữ liệu đã sửa | Provisional/final/revised |

## 26. Bài tập thực hành

### Bài 1 — Ba timestamp

Thiết bị đo lúc 09:00, gateway nhận 09:03 và worker xử lý 09:04:30. Xác định event time, ingestion time, processing time. Báo cáo nhiệt độ 09:00 nên nhóm theo thời gian nào?

**Đáp án:** observedAt=09:00, receivedAt=09:03, processedAt=09:04:30; event-time report dùng observedAt.

### Bài 2 — Out-of-order

A-0902-r1 đến trước A-0901-r1. Có nên từ chối A-0901-r1 vì observedAt nhỏ hơn? Nêu các điều kiện để quyết định.

**Gợi ý:** Không mặc định. Xét allowed lateness, source identity, clock skew, TTL và chính sách backfill.

### Bài 3 — Truy vấn chronological

Viết `find` cho sensor-A rồi sort theo `observedAt` tăng, `revision` tăng, `receivedAt` tăng. Vì sao không dùng natural order?

### Bài 4 — Raw và unique event IDs

Sau khi chạy fixture, có bao nhiêu raw documents và event IDs khác nhau?

**Đáp án:** 12 raw, 10 distinct event IDs.

### Bài 5 — Phát hiện retry

Nhóm theo `(tenantId,eventId)` và lọc `copies > 1`. Những event IDs nào trùng và có bao nhiêu bản dư?

**Đáp án:** A-0901-r1, B-0901-r1; hai extra deliveries.

### Bài 6 — Revision mới

A-0901-r1 value=21, A-0901-r2 value=21.5. Giá trị canonical là gì?

**Đáp án:** 21.5 nếu policy chọn revision cao nhất.

### Bài 7 — Đếm logical samples

Áp dụng `canonicalPrefix`, đếm sample theo device. Kết quả?

**Đáp án:** A=4, B=3, C=2; tổng=9.

### Bài 8 — Trung bình bị ảnh hưởng

Tính raw average và canonical average của sensor A.

**Đáp án:** 20.75 và 20.625.

### Bài 9 — Window 09:01

Tính trung bình `[09:01,09:02)` khi chưa có A, sau A-r1, sau A-r2.

**Đáp án:** 25.5 → 24 → 24.166667.

### Bài 10 — Lateness

Dùng `$dateDiff` và lọc delay >120 s. Có bao nhiêu raw documents trong fixture?

**Đáp án:** 5; nếu muốn đếm unique late events phải dedup trước.

### Bài 11 — Clock chạy nhanh

Nếu `observedAt` sau `receivedAt` 6 phút, có thể suy ra điều gì và cần kiểm tra gì?

### Bài 12 — Unique index time series

Vì sao không tạo unique index trên `("meta.deviceId",observedAt)`? Nếu cần chống retry, nên tạo index ở đâu?

**Đáp án:** Time series không hỗ trợ unique indexes; dùng regular inbox/registry.

### Bài 13 — Crash giữa dual writes

Registry claim thành công nhưng time series append chưa chạy; hoặc append thành công nhưng state chưa đổi. Hai trường hợp yêu cầu recovery khác nhau thế nào?

### Bài 14 — TTL

Time series retention 24 giờ theo observedAt. Một event đến hôm nay nhưng observedAt của ba ngày trước. Vì sao không được hứa lưu 24 giờ kể từ lúc nhận?

### Bài 15 — Backfill tuần trước

Thiết kế job backfill có checkpoint, event identity, throttle, TTL policy, correction handling và recomputation của windows đã final.

### Bài 16 — Materialize canonical

Dùng `$merge` từ measurements vào regular `canonicalReadings`, đếm 9 logical samples. Vì sao không đổi `into` thành time-series collection?

### Bài 17 — Sequence reset

Một thiết bị phát `sequenceNo` tăng dần nhưng reset về 0 khi reboot. Thiết kế ID tránh trùng giữa các boot.

**Đáp án:** Kết hợp deviceId, bootId/epoch, sequence và tenant/metric nếu cần.

### Bài 18 — Window finalization

Dashboard cần kết quả dưới 10 giây, nhưng 5% events đến sau 5 phút. Đề xuất provisional/final/revised policy và cách thông báo downstream.

### Bài 19 — Monitoring

Liệt kê ít nhất tám metrics cho ingestion, late events, duplicate, conflict, correction, bucket efficiency, TTL và window revisions.

### Bài 20 — Chọn kiến trúc

So sánh append-only + query-time dedup, unique inbox + time series, và regular canonical store + TS projection cho hệ thống IoT có retry và correction. Nêu ranh giới atomicity và phương án phục hồi.

## 27. Tổng kết

Ba khái niệm phải được tách bạch:

- **Late arrival:** phép đo đến sau hạn đã chọn.
- **Out of order:** thứ tự nhận khác thứ tự event time.
- **Duplicate:** cùng event được gửi lại; phải phân biệt với correction của cùng logical sample.

Để xây pipeline time-series đúng trong MongoDB:

1. Giữ `observedAt` làm event time và lưu `receivedAt` riêng.
2. Chọn `metaField` ổn định để hỗ trợ bucketing.
3. Sort theo event time thay vì tin thứ tự insert.
4. Dùng eventId để nhận diện retry, sampleId để nhận diện logical measurement, revision để nhận diện correction.
5. Dedup trước khi tính aggregate nếu nghiệp vụ cần một giá trị mỗi logical sample.
6. Định nghĩa watermark/allowed lateness tại pipeline nghiệp vụ.
7. Không dùng unique indexes, upsert measurement hoặc transaction writes trên time series như regular collection.
8. Nếu cần uniqueness mạnh, dùng regular collection và hiểu giới hạn dual-write.
9. Kiểm tra TTL theo timeField; late data rất cũ có thể bị dọn.
10. Duy trì audit, checkpoint, reconciliation và revision của kết quả tổng hợp.
11. Theo dõi p95/p99 ingestion lag, duplicates, conflicts và số window sửa đổi.
12. Chọn kiến trúc theo mức độ đúng đắn cần thiết và chi phí vận hành.

**Raw insert thành công không đồng nghĩa báo cáo đúng.** Độ đúng xuất phát từ identity của nguồn, thứ tự event time, quy tắc correction và cơ chế đối soát có thể phục hồi.

### Tài liệu MongoDB chính thức

- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — khái niệm và tối ưu lưu trữ.
- [About Time Series Data / Bucketing](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/) — bucket theo meta/time, timestamp out of order.
- [Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/) — `timeField`, `metaField`, granularity.
- [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — unique indexes, updates, transactions, schema validation, `$merge` restrictions.
- [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — các index được hỗ trợ.
- [Time Series Best Practices](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — chọn metadata/granularity.
- [Set Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/) — bucket parameters.
- [Automatic Removal for Time Series (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — thời hạn theo timeField.
- [Aggregation $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — nhóm theo cửa sổ.
- [Aggregation $dateDiff](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateDiff/) — đo độ trễ.
- [Aggregation $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — canonicalization.
- [Aggregation $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materialize sang regular collection.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — ràng buộc ở regular collection.
- [Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — phân biệt atomic writes.
