# Giới hạn cập nhật, giao dịch, sharding theo phiên bản hỗ trợ

**Time series collections** trong MongoDB được tối ưu cho chuỗi các **measurements** theo thời gian: dữ liệu cảm biến IoT, metrics máy chủ, giá thị trường, số liệu hiệu năng, các sự kiện telemetry có timestamp. Từ góc nhìn ứng dụng, bạn vẫn `insertOne()`, `find()` hoặc `aggregate()` các document; nhưng phía dưới, MongoDB tổ chức nhiều measurements có metadata giống nhau và timestamp gần nhau vào **buckets** để nén và truy vấn hiệu quả.

Chính tối ưu đó tạo ra những **giới hạn khác collection thông thường**, đặc biệt ở ba điểm mà bài học này tập trung:

1. **Cập nhật và xóa:** Trong các dòng server phổ biến, không thể sửa tùy ý `temperature`, `observedAt` hay một measurement riêng bằng `updateOne()` như đối với collection thường. Cập nhật time-series bị giới hạn rất cụ thể; giới hạn **xóa** cũng thay đổi đáng kể từ MongoDB 7.0.
2. **Giao dịch:** MongoDB **không cho ghi vào time series collection trong multi-document transaction** theo Database Manual; **đọc** từ time-series trong transaction được hỗ trợ, với lưu ý về snapshot và thay đổi namespace.
3. **Sharding:** Time-series chỉ cho những field shard key nhất định; `timeField` là thành phần rủi ro và bị **deprecated trong shard key từ MongoDB 8.0**. **Resharding** time-series có thay đổi quan trọng ở **8.0.10**; không thể áp dụng mọi thao tác quản trị sharding của collection thường.

Vì vậy, câu hỏi “time series có hỗ trợ update, delete, transaction, shard không?” **không thể trả lời chỉ bằng có/không**. Phải biết **server version, feature compatibility version (FCV), topology, loại thao tác, filter, field được sửa** và yêu cầu nghiệp vụ.

Bài thuộc chương **Chuỗi thời gian** của module *Database Engine Document MongoDB*. Các ví dụ sử dụng `mongosh` và MongoDB Java Sync Driver; những lệnh DDL/sharding có nhãn minh họa chỉ nên chạy trong **cluster lab**, không thực thi trên production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích `timeField`, `metaField`, `granularity` và buckets ảnh hưởng tới giới hạn ghi.
- Đọc bảng tương thích **5.0 → 5.1 → 6.0/6.3 → 7.0 → 8.0/8.0.10 → các dòng mới hơn** mà không nhầm update với delete.
- Viết đúng `updateMany()` **chỉ lọc và sửa `metaField`**; nhận biết những câu `updateOne()`, `upsert`, update measurement/timeField hoặc replacement update bị từ chối.
- Phân biệt xóa time-series **5.1–6.x** với hành vi nới rộng **từ 7.0**, đồng thời hiểu TTL bucket-based.
- Nêu chính xác lý do **không dùng transaction ghi** vào time-series và thiết kế workflow thay thế khi cần correction/atomicity qua collections.
- Chọn shard key từ `metaField`/subfield và xử lý nguy cơ monotonic `timeField`; biết giới hạn **zone sharding** và điều kiện **reshard**.
- Chẩn đoán tính tương thích dựa trên `buildInfo`, `getParameter`/FCV, `listCollections` và tài liệu của phiên bản tương ứng.
- Tổ chức ingestion, corrections, retention, analytics/read models và bảo vệ tính nhất quán ở tầng ứng dụng.

> **Nguồn chân lý:** Bài tham chiếu MongoDB Database Manual và release notes chính thức. Tính năng có thể thay đổi theo **patch release**, nhánh version và **FCV**, nhất là trên cluster đang rolling upgrade. Đừng dựa vào việc driver có method `updateOne` hay `startTransaction` để suy rằng server hỗ trợ method đó với time-series. Các link tra cứu phiên bản nằm ở phần cuối.

## 1. Time-series document và cấu trúc buckets

Một measurement có thể là:

~~~javascript
{
  observedAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    deviceId: "sensor-01",
    site: "HCM",
    kind: "temperature"
  },
  temperatureC: 28.4,
  humidityPct: 73,
  quality: "raw"
}
~~~

Phân biệt:

| Thành phần | Mục đích | Cập nhật có được không? |
|---|---|---|
| `observedAt` (timeField) | **BSON Date** của measurement; hỗ trợ grouping/sort/range. | Không sửa bằng các time-series update thông thường theo giới hạn Manual. |
| `meta` (metaField) | Nhãn nhận diện chuỗi: thiết bị, vị trí, loại nguồn; thường ổn định. | Có thể update **metadata** bằng `updateMany` với các ràng buộc cụ thể từ 5.1. |
| `temperatureC`, `humidityPct` | Giá trị đo thay đổi theo timestamp. | Không update bằng `updateMany` theo giới hạn metadata-only. |
| `quality` | Dữ liệu đo/phân loại trạng thái mỗi measurement nếu không thuộc metaField. | Không update trực tiếp theo quy tắc metadata-only. |
| `_id` (nếu có) | ID ở logical measurement. | Không có index `_id` mặc định như collection thông thường; không coi nó là unique key được DB bảo đảm toàn collection. |

### 1.1. Dữ liệu được tối ưu như thế nào?

~~~text
Ứng dụng thấy:
  measurement 1: meta={deviceId:S1}, 08:00, temp=28.4
  measurement 2: meta={deviceId:S1}, 08:01, temp=28.6
  measurement 3: meta={deviceId:S1}, 08:02, temp=28.7

MongoDB lưu trữ tối ưu:
  bucket cho S1 + khoảng thời gian gần nhau
     metadata chung
     timestamps được gom
     các giá trị được nén theo cột/bucket
~~~

MongoDB nhóm những measurements có `metaField` giống nhau và thời gian gần nhau. Dữ liệu được tối ưu theo **insert nhiều, đọc theo nguồn/thời gian, sửa hiếm**; vì thế những phép cập nhật từng measurement không có semantics giống normal collection. Xem [About Time Series Data](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/).

### 1.2. Tên collection logic khác namespace bucket nội bộ

Ứng dụng đọc/ghi qua collection được khai báo `timeseries`, ví dụ `db.telemetry`. Đừng tự đọc/sửa trực tiếp `system.buckets.telemetry` để “vượt” giới hạn update — bucket layout là implementation detail, thay đổi theo version và có rủi ro làm hỏng dữ liệu/nén/metadata.

Từ **MongoDB 9.0**, tài liệu mô tả cách tổ chức namespace time-series khác với những phiên bản dùng cặp view + bucket collection; đó là lý do càng **không hard-code đường dẫn storage nội bộ**. Luôn dùng API dành cho collection time-series và đối chiếu server version.

### 1.3. Time-series không phải event store có khả năng sửa vô hạn

Các yêu cầu nghiệp vụ:

- Mỗi 10 giây ghi một giá trị nhiệt độ mới → phù hợp time-series.
- Thi thoảng sửa label `meta.site` cho một nhóm thiết bị → có khả năng dùng metadata update.
- Chỉnh lại hàng nghìn giá trị `temperatureC` đã ghi hoặc thay `observedAt` vì nhập sai timezone → **không** là thao tác update thông thường được hỗ trợ trong các dòng Manual đang xét.
- Hai measurements và một billing record phải cùng commit hoặc cùng rollback → **không** gói time-series writes vào MongoDB multi-document transaction.

Nếu ứng dụng phải sửa sâu từng measurement thường xuyên, cần đánh giá lại **data model**, chứ không cố dùng time-series collection như một table OLTP đầy đủ.

## 2. Tạo collection và dữ liệu lab

Ví dụ tự chạy trên database riêng `ts288_lab` của một MongoDB **5.1+** (để các ví dụ metadata update có thể dùng). Phần tạo/insert cũng phù hợp với **MongoDB 5.0** nếu bỏ những thao tác 5.1+.

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// Chỉ chạy một lần trên môi trường thực hành chưa có collection.
lab.createCollection("telemetry", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

lab.telemetry.insertMany([
  {
    observedAt: ISODate("2026-11-14T08:00:00Z"),
    meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
    temperatureC: 28.4, humidityPct: 73, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:01:00Z"),
    meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
    temperatureC: 28.7, humidityPct: 72, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:02:00Z"),
    meta: { deviceId: "sensor-02", site: "HN", kind: "temperature" },
    temperatureC: 23.1, humidityPct: 68, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:03:00Z"),
    meta: { deviceId: "sensor-02", site: "HN", kind: "temperature" },
    temperatureC: 23.4, humidityPct: 66, quality: "raw"
  },
  {
    observedAt: ISODate("2026-11-14T08:04:00Z"),
    meta: { deviceId: "sensor-03", site: "HCM", kind: "humidity" },
    humidityPct: 76, quality: "raw"
  }
])
~~~

**Lưu ý thực hành:** Chạy lại `createCollection` hoặc `insertMany` không phải thao tác idempotent; sẽ gặp lỗi collection đã tồn tại hoặc dữ liệu trùng. Nếu cần thử lại, tạo database/collection lab mới hoặc có quy trình reset **chỉ trên lab**, không copy lệnh `drop()` vào production. Timestamp trong fixture là điểm đo cố định; không đặt TTL ngắn trên collection này vì dữ liệu sẽ tự hết hạn tùy thời điểm chạy bài.

### 2.1. Truy vấn theo nguồn và khoảng thời gian

~~~javascript
lab.telemetry.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:05:00Z")
  }
}).sort({ observedAt: 1 })
~~~

Trong fixture, sensor-01 có **hai** measurements. Dùng meta + time range là query pattern phù hợp với tổ chức bucket; nên ưu tiên metadata ổn định và time filters có giới hạn thay vì quét toàn bộ thời gian.

### 2.2. Tổng hợp dữ liệu theo thời gian

~~~javascript
lab.telemetry.aggregate([
  { $match: {
      "meta.deviceId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:05:00Z")
      }
  } },
  { $group: {
      _id: "$meta.deviceId",
      samples: { $sum: 1 },
      avgTemperatureC: { $avg: "$temperatureC" }
  } }
])
~~~

Giá trị trung bình là **28.55 °C** (từ 28.4 và 28.7), `samples:2`. Pipeline đọc này không yêu cầu transaction và không sửa time-series.

## 3. Bảng tương thích theo phiên bản: các mốc cần nhớ

| MongoDB Server | Time-series và cập nhật/xóa | Transaction | Sharding và tính năng liên quan |
|---|---|---|---|
| **5.0** | **Ra mắt** time-series. Chủ yếu insert/read; **không manual update/delete** theo các giới hạn ban đầu. | Không ghi time-series trong multi-document transaction. | Chưa hỗ trợ sharded time-series collection. |
| **5.1** | Hỗ trợ **metadata-only multi-update** và **delete có giới hạn**: filter chỉ trên metaField; delete nhiều docs. | Không ghi time-series trong transaction. | **Bắt đầu hỗ trợ sharded time-series**. |
| **5.2** | Các giới hạn update/delete 5.1 tiếp tục. | Không ghi time-series trong transaction. | Bổ sung **column compression** cho time-series. |
| **6.0** | Update metadata-only, delete còn giới hạn kiểu 5.1–6.x. | Không ghi time-series trong transaction. | Hỗ trợ **secondary indexes trên measurement fields** và thao tác quản trị liên quan theo version. |
| **6.3** | Các giới hạn metadata update chưa biến thành update measurements tùy ý. | Không ghi time-series trong transaction. | Time-series mới được tạo có **default compound index metaField + timeField**; hỗ trợ cấu hình bucket span tùy chỉnh. |
| **7.0** | **Delete được nới rộng đáng kể**: có thể dùng `deleteOne`/`deleteMany` với filter linh hoạt ngoài transaction; **update vẫn metadata-only multi-update**. | Vẫn không ghi time-series trong transaction; có thể đọc. | **Partial TTL index theo metaField** được hỗ trợ, vẫn có hạn chế shard key, không reshard trong 7.0. |
| **8.0** | Không nên suy ra update measurements trở thành hợp lệ chỉ vì delete được nới; xem mục Update của Manual. | Không ghi time-series trong transaction. | **Shard key có `timeField` bị deprecated**, nên ưu tiên metadata-based key. |
| **8.0.10+** | Tiếp tục tuân thủ giới hạn update của branch tương ứng. | Không ghi time-series trong transaction. | **Có thể reshard time-series**, yêu cầu **tất cả shards chạy ít nhất 8.0.10**. |
| **8.3/9.x và mới hơn** | Kiểm tra docs cụ thể vì namespace storage, indexes và cách thực thi có thể thay đổi. | Không dự đoán write transaction trở nên hợp lệ nếu Manual chưa nêu. | Đọc release notes/FCV và trang Limitations đúng branch thay vì chỉ dựa vào một ví dụ cũ. |

Các mốc có thể kiểm tra ở [Release Notes 7.0](https://www.mongodb.com/docs/v7.0/release-notes/7.0/), [Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/), [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/), [Shard a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/).

### 3.1. Phân biệt ba phiên bản có thể khác nhau

Một ứng dụng có thể sử dụng:

- **Server binary version:** ví dụ `8.0.10` trên `mongod`.
- **FCV:** trạng thái compatibility được bật cho feature set khi vừa nâng cấp/rolling upgrade.
- **Driver version:** ví dụ Java Sync Driver dòng 5.x; driver cung cấp API chung nhưng không tự làm server 5.0 hỗ trợ tính năng 7.0.

Với sharded cluster, còn có **`mongos`, config server và mỗi shard replica set**; khi yêu cầu là “**tất cả shards ≥ 8.0.10**”, chỉ đọc version của một router chưa đủ.

### 3.2. Đừng lẫn manual “current” với server đang chạy

Nếu bạn đang chạy MongoDB 6.0 và đọc trang **Database Manual hiện hành**, có thể thấy `deleteOne()` với điều kiện measurement là ví dụ hợp lệ ở 7.0+; áp dụng vào 6.0 sẽ lỗi. Ngược lại, nếu đọc tài liệu 7.0 và kết luận time-series **không bao giờ reshard được**, điều đó đã không còn đúng từ 8.0.10.

**Hãy gắn mọi câu trả lời về khả năng hỗ trợ với phiên bản cụ thể.**

## 4. Giới hạn update: chỉ lọc và sửa `metaField`, chỉ dùng multi-update

Với time-series collections từ **MongoDB 5.1** theo các giới hạn của Database Manual đang xét, một câu update phải **đồng thời** đáp ứng:

1. **Filter** chỉ chứa điều kiện trên giá trị `metaField` (bao gồm các subfields của metadata nếu phù hợp).
2. **Update** chỉ thay đổi **giá trị `metaField`**; không sửa trực tiếp `timeField` hay các measurement fields như `temperatureC`.
3. **Update document** chỉ dùng các **update operators** (ví dụ `$set`, `$unset` phù hợp), không dùng replacement document hoặc aggregation pipeline update.
4. Không được giới hạn số measurements cập nhật: dùng `updateMany()` hoặc lệnh `update` với `multi:true`.
5. **Không dùng `upsert:true`.**

Chỉ cần vi phạm một trong năm điểm là một câu update vốn hợp lệ trên collection thường **có thể bị từ chối** trên time-series.

### 4.1. Ví dụ cập nhật metadata hợp lệ

Fixture `telemetry` có hai measurements từ sensor-01 tại site HCM. Nếu tên site cần chuẩn hóa, có thể cập nhật metadata của **tất cả measurements khớp**:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

const result = lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)

printjson(result)
~~~

Câu lệnh dùng filter theo `meta` và chỉ sửa `meta.site`; thuộc dạng metadata-only multi-update được hỗ trợ từ 5.1. Sau khi thành công, hai measurements của sensor-01 có thể hiển thị `meta.site:"SGN"`.

**Không nhầm đây là một update trên document thông thường.** Time-series được tổ chức thành buckets theo metadata; thay đổi meta có thể ảnh hưởng grouping/bucket processing và gây chi phí đáng kể. Metadata **nên ít thay đổi** theo thiết kế.

### 4.2. Thực chất `updateMany` đã chọn bao nhiêu measurements?

Nếu filter khớp 2 measurements, `updateMany()` có thể thay metadata của cả 2. Nhưng `matchedCount` và `modifiedCount` phải đọc **từ kết quả server thực**, không tự cho rằng lệnh đã làm đúng chỉ vì driver không ném exception.

Nếu có nhiều sensors cùng site HCM, cập nhật:

~~~javascript
lab.telemetry.updateMany(
  { "meta.site": "HCM" },
  { $set: { "meta.region": "SOUTH" } }
)
~~~

sẽ ảnh hưởng **mọi measurements** khớp site HCM, không chỉ một device. Trong một collection chứa hàng tỷ measurements, update metadata có phạm vi quá rộng là một thao tác đắt tiền. Nên giới hạn filter theo **deviceId hoặc metadata nhận diện series** khi nghiệp vụ cho phép.

### 4.3. Sai: sửa giá trị measurement `temperatureC`

~~~javascript
// Không hợp lệ theo giới hạn metadata-only update.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { temperatureC: 30.0 } }
)
~~~

`temperatureC` là dữ liệu đo, **không phải `metaField`**. Dùng `updateMany` không làm phép sửa measurement trở thành hợp lệ.

Một lỗi nghiệp vụ phổ biến là muốn “đổi `temperatureC` ở 08:01 từ 28.7 thành 29.0” rồi dùng:

~~~javascript
// Đồng thời vi phạm: filter measurement/timeField và update measurement.
lab.telemetry.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: ISODate("2026-11-14T08:01:00Z")
  },
  { $set: { temperatureC: 29.0 } }
)
~~~

Không nên xem đây như một upsert của collection thường. Time-series được tối ưu cho **append-only / insert-first**; cần workflow sửa dữ liệu riêng nếu phải correction, như phần 11.

### 4.4. Sai: `updateOne()`

~~~javascript
// Không hợp lệ: một update giới hạn số measurements.
lab.telemetry.updateOne(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Dù chỉ sửa meta, method `updateOne()` dùng semantics **single update**, trái giới hạn `multi:true`. Đổi sang `updateMany()`:

~~~javascript
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Không suy rằng vì filter khớp đúng một measurement trong dữ liệu hôm nay thì `updateOne()` bỗng hợp lệ; giới hạn ở **loại operation**, không ở số records tình cờ match.

### 4.5. Sai: `upsert:true`

~~~javascript
// Không hợp lệ với time-series update.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-99" },
  { $set: { "meta.site": "HCM" } },
  { upsert: true }
)
~~~

Khi cần tạo measurement mới, dùng `insertOne()`/`insertMany()` với **timeField BSON Date hợp lệ** và metadata phù hợp. `upsert` trên time-series không có semantics giống một record entity thông thường; nếu cần “tạo thiết bị nếu chưa có”, đặt hồ sơ thiết bị ở **collection thường** với unique deviceId và workflow idempotent.

### 4.6. Sai: replace toàn document hoặc update pipeline

~~~javascript
// Sai: replacement document không phải update operator expression.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  { meta: { deviceId: "sensor-01", site: "SGN" } }
)

// Sai: aggregation update pipeline không thuộc dạng update operators được phép.
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-01" },
  [
    { $set: { "meta.site": "SGN" } }
  ]
)
~~~

Nên dùng update document với `$set`/`$unset` và chỉ đụng `metaField` khi phù hợp. Một pipeline `[{$set:{...}}]` trông giống modifier `{$set:{...}}` nhưng là **kiểu update khác**, không tự được time-series update chấp nhận.

### 4.7. Filter có được thêm `observedAt` để giảm phạm vi không?

Không trong metadata-only update được mô tả:

~~~javascript
// Không hợp lệ: filter chứa timeField, ngoài metaField.
lab.telemetry.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: { $gte: ISODate("2026-11-14T08:00:00Z") }
  },
  { $set: { "meta.site": "SGN" } }
)
~~~

Đây là ranh giới rất quan trọng: một update chỉ đổi `meta.site` nhưng **filter theo timestamp** vẫn vi phạm điều kiện query chỉ trên metadata. Nếu yêu cầu là “đổi site label chỉ với các measurements trong tuần trước”, không có cách đơn giản dùng một metadata update time-series như trên; phải đánh giá một chiến lược correction/migration khác.

### 4.8. Khi metaField là một object

`metaField` có thể là object:

~~~javascript
meta: {
  deviceId: "sensor-01",
  site: "HCM",
  kind: "temperature"
}
~~~

Bạn có thể thêm subfield:

~~~javascript
lab.telemetry.updateMany(
  { "meta.deviceId": "sensor-02" },
  { $set: { "meta.ownerTeam": "observability" } }
)
~~~

Nhưng phải nhớ **nhận diện bucket** được tối ưu theo metadata: thay đổi hoặc thêm subfield có thể làm nhóm metadata đổi. Không nên dùng meta để lưu field thay đổi mỗi giây như `currentTemperature`, `lastHeartbeatAt` hoặc số lần retry — các field này làm tăng số metadata values, giảm hiệu quả bucket compression.

### 4.9. Trường meta dùng làm shard key còn có ràng buộc routing

Trong **sharded** time-series, một update sửa `meta` có thể chạm vào **thành phần shard key**. Việc sửa shard key và định tuyến writes có quy định riêng theo server version và topology. Vì thế, mẫu update `meta.site` có thể an toàn hơn khi `meta.site` không nằm trong shard key; nếu nó là shard key, hãy kiểm tra support và chi phí di chuyển/định tuyến, không áp dụng như update metadata bình thường.

**Thiết kế tốt:** dùng metadata nhận diện chuỗi **ổn định**; nếu địa điểm thiết bị thay đổi có ý nghĩa tạo series mới, cân nhắc ghi các measurements mới dưới metadata mới thay vì sửa lịch sử.

## 5. Cập nhật theo logic business: phép nào thay thế được?

| Yêu cầu | Có nên thực hiện bằng time-series `updateMany`? | Hướng phù hợp |
|---|---|---|
| Chuẩn hóa `meta.site` cho toàn bộ sensor-01 | Có, với metadata-only multi-update và giới hạn version. | `updateMany({"meta.deviceId":...},{$set:{"meta.site":...}})`. |
| Đổi tên `meta.ownerTeam` trên một nhóm devices | Có thể, khi filter chỉ metadata. | Metadata update có kiểm soát. |
| Sửa `temperatureC` ở timestamp 08:01 | Không theo hạn chế update hiện hành. | Correction workflow, delete+reinsert 7.0+ hoặc overlay. |
| Đổi `observedAt` do sai timezone | Không. | Tạo measurement đúng và quản lý bản sai theo policy. |
| Upsert measurement nếu không tồn tại | Không. | Ingest bằng insert + logical eventId/dedupe bên ngoài. |
| Đánh dấu `quality:"corrected"` nằm ngoài meta | Không. | Correction overlay hoặc record mới, không mutate measurement. |
| Xóa measurement cũ do retention | Không phải update; dùng TTL. | `expireAfterSeconds`/partial TTL theo version. |
| Ghi measurement và payment đồng thời | Không thể đặt time-series write vào MongoDB transaction. | Outbox/async ingestion hoặc đổi data model cần atomicity. |

### 5.1. Không dùng bulkWrite để “né” giới hạn

~~~javascript
// Không biến một update measurement bị cấm thành hợp lệ.
lab.telemetry.bulkWrite([
  {
    updateMany: {
      filter: { "meta.deviceId": "sensor-01" },
      update: { $set: { temperatureC: 30.0 } }
    }
  }
])
~~~

`bulkWrite` chỉ là cách gửi nhiều operations; MongoDB vẫn áp dụng **giới hạn time-series** cho operation tương ứng. Tương tự, thêm `ordered:false` hay `bypassDocumentValidation:true` không biến measurement update thành hợp lệ.

### 5.2. Không viết trực tiếp vào `system.buckets`

Bạn có thể thấy bucket collection trong metadata/tooling ở một số versions. **Không cập nhật trực tiếp bucket documents** để thay `temperatureC`: dữ liệu ở đó là định dạng nội bộ với các quy tắc nén/ordering/index/metadata; sửa bằng CRUD bình thường có thể bị chặn hoặc phá invariant storage.

Ứng dụng phải làm việc với **logical time-series collection**. Nếu correction workload thường xuyên, hãy cân nhắc collection thường hoặc append-only correction log được thiết kế rõ ràng.

### 5.3. Không phải mọi dữ liệu có timestamp đều cần time-series

Ví dụ:

- Dữ liệu cảm biến mỗi phút, đọc theo nguồn/giờ, rất ít sửa → time-series phù hợp.
- Trạng thái mới nhất của một thiết bị, cập nhật liên tục và cần CAS/version → **collection thường** `deviceState` phù hợp hơn.
- Một event cần unique `eventId` và atomic update/cancellation thường xuyên → collection thường hoặc ledger/outbox tùy invariant.
- Chuỗi measurements + annotations sửa được → time-series cho raw measurements, **collection thường** cho annotations/corrections, join/projection khi đọc.

Lợi ích nén/query time-range không nên che khuất những yêu cầu **OLTP mutation và transaction** thực tế.

## 6. Giới hạn xóa: thay đổi lớn từ MongoDB 7.0

Nhiều bài hướng dẫn cũ nói “time-series không cho xóa document”, trong khi hướng dẫn mới có thể cho `deleteOne()` với filter bất kỳ. Sự khác biệt chủ yếu đến từ **mốc phiên bản**.

### 6.1. MongoDB 5.0: không manual delete

Ở phiên bản time-series ban đầu **5.0**, các thao tác chủ yếu là **insert và read**; update và manual delete không được hỗ trợ. Nếu mục đích là giữ dữ liệu trong một thời hạn, có thể cấu hình **TTL** lúc tạo collection. Nếu muốn xóa toàn bộ dữ liệu lab, `drop()` collection là thao tác khác về semantics và phải dùng cực kỳ thận trọng.

### 6.2. MongoDB 5.1 đến 6.x: delete nhiều documents, filter theo metadata

Theo giới hạn của giai đoạn **5.1–6.x**:

- Delete predicate chỉ tham chiếu **`metaField`**.
- Không được giới hạn số documents xóa; dùng `deleteMany()` hoặc lệnh `delete` với `justOne:false`.
- Không dùng `deleteOne()` để xóa đúng một measurement.

Ví dụ trên MongoDB 6.0:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// Chỉ chạy trên lab với dữ liệu không còn cần dùng.
// Xóa tất cả measurements của sensor-03:
lab.telemetry.deleteMany({
  "meta.deviceId": "sensor-03"
})
~~~

Lệnh này khác một câu:

~~~javascript
// Không hợp lệ theo các giới hạn 5.1–6.x vì filter chứa timeField.
lab.telemetry.deleteMany({
  observedAt: {
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
})
~~~

Vì vậy, nếu một system MongoDB 6.0 cần xóa mọi measurement trước một cutoff time, **không** tự suy rằng có thể dùng `deleteMany({observedAt:{$lt:cutoff}})`. Cân nhắc TTL, thay đổi retention policy/migration hoặc nâng cấp theo kế hoạch.

### 6.3. MongoDB 7.0+: nới lỏng phần lớn hạn chế của `delete`

Release Notes MongoDB 7.0 xác nhận loại bỏ **phần lớn ràng buộc time-series** đối với các thao tác dựa trên lệnh `delete`:

- `delete`
- `deleteOne()`
- `deleteMany()`
- Các biến thể `Bulk.find.delete()`/`deleteOne()`

Trong điều kiện deployment hỗ trợ và **bên ngoài multi-document transaction**, có thể xóa theo metadata, timestamp hoặc measurement values. Ví dụ:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

// MongoDB 7.0+: xóa một measurement trùng điều kiện logic.
lab.telemetry.deleteOne({
  "meta.deviceId": "sensor-02",
  observedAt: ISODate("2026-11-14T08:02:00Z")
})

// MongoDB 7.0+: xóa các measurement trước cutoff.
lab.telemetry.deleteMany({
  observedAt: {
    $lt: ISODate("2026-11-14T08:03:00Z")
  }
})

// MongoDB 7.0+: điều kiện trên measurement.
lab.telemetry.deleteMany({
  temperatureC: { $gt: 100 }
})
~~~

**Các lệnh là ví dụ destructive**: không chạy nối tiếp khi bạn muốn giữ fixture để làm những bài khác. Chúng cần được thử trên một collection lab mới/đã sao lưu. Một `deleteOne` không bảo đảm business uniqueness nếu có hai measurements cùng sensorId/timestamp; time-series không tạo unique index mặc định cho measurement ID.

### 6.4. Điều kiện còn lại: không delete trong transaction

MongoDB 7.0+ nới lỏng delete predicate **không** đồng nghĩa hỗ trợ ghi/xóa time-series bên trong một multi-document transaction. Điều này vẫn bị cấm theo trang Time Series Collection Limitations hiện hành.

| Loại delete | 5.0 | 5.1–6.x | 7.0+ |
|---|---|---|---|
| `deleteMany({"meta.deviceId":"S1"})` | Không hỗ trợ | **Có**, theo meta filter. | Có, ngoài transaction. |
| `deleteMany({observedAt:{$lt:cutoff}})` | Không hỗ trợ | **Không**, filter timeField không hợp lệ. | **Có**, ngoài transaction. |
| `deleteMany({temperatureC:{$gt:100}})` | Không hỗ trợ | Không, filter measurement không hợp lệ. | Có, ngoài transaction. |
| `deleteOne({ ... })` | Không hỗ trợ | Không, singleton delete bị giới hạn. | Có, ngoài transaction. |
| Delete trong multi-document transaction | Không | Không | **Không**, dù delete syntax đã mở rộng. |
| TTL tự động theo thời gian | Có | Có | Có. |

**Chú ý:** Một số legacy helpers như `remove()` có hạn chế riêng trên time-series, dù `deleteOne`/`deleteMany` đã được nới ở 7.0. Dùng API hiện đại theo tài liệu của method bạn chọn. Xem [MongoDB 7.0 Release Notes — Time Series](https://www.mongodb.com/docs/v7.0/release-notes/7.0/).

### 6.5. Xóa có thể phải xử lý/repack buckets

Không nên kỳ vọng `deleteOne` trên một measurement giống chi phí delete một row trong collection thông thường. Measurement có thể nằm trong một bucket cùng nhiều samples khác. Khi delete một số samples, storage engine có thể phải tổ chức lại bucket; xóa toàn bucket theo predicate phù hợp có chi phí khác với xóa chọn lọc.

Nếu cleanup là nhu cầu định kỳ, **TTL** thường phù hợp hơn viết một job quét và xóa hàng triệu measurements liên tục. Nhưng nếu có yêu cầu **privacy deletion ngay**, phải đánh giá SLA, quyền, tuổi dữ liệu và khả năng xóa theo version cụ thể; TTL không cam kết xóa tức thì.

### 6.6. Khi các measurements được insert liên tục trong lúc xóa

`deleteMany()` không phải transaction all-or-nothing cho toàn bộ matching set; nếu writers đang insert measurements cùng điều kiện, kết quả cuối có thể thay đổi theo thời gian. Với policy “xóa sạch mọi dữ liệu của device đã bị thu hồi”:

1. Chặn hoặc điều phối **ingestion mới** của device.
2. Chạy delete với filter phù hợp cho version.
3. Xác minh số liệu sau xóa với `find/countDocuments` trên phạm vi đã định.
4. Retry idempotent tới khi không còn matching measurements, nếu nghiệp vụ yêu cầu.
5. Ghi audit/retention/authorization ở **collection thường** phù hợp.

Đừng chỉ chạy một `deleteMany` rồi kết luận không còn dữ liệu nếu ingestion tiếp tục chảy vào cùng series.

## 7. TTL và retention: thay cho phần lớn manual deletes

MongoDB time-series hỗ trợ **tự động hết hạn dữ liệu** bằng `expireAfterSeconds`. Với workload telemetry append-only, cách này thường phù hợp hơn viết một cron job `deleteMany` theo thời gian.

### 7.1. Tạo collection với TTL

Ví dụ một collection giữ dữ liệu trong **7 ngày**:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.createCollection("telemetry7d", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 7 * 24 * 60 * 60
})
~~~

MongoDB có thể tự xóa **bucket** khi các measurements trong bucket đã hết hạn. Mục tiêu logic là timestamp + retention, nhưng việc xóa vật lý **không xảy ra đúng từng giây**.

### 7.2. TTL theo bucket, không phải hẹn giờ riêng cho từng sample

~~~text
Bucket cùng device/metadata:

  10:01  sample A
  10:02  sample B
  10:59  sample C

Retention = 7 ngày

10:01 + 7d: A có thể đã quá hạn
10:02 + 7d: B có thể đã quá hạn
10:59 + 7d: cả bucket mới đủ điều kiện bị dọn
         |
         v
TTL monitor chạy định kỳ, deletion thực tế có thể trễ thêm.
~~~

MongoDB Manual mô tả background TTL task chạy định kỳ (thông thường khoảng **60 giây**) và bucket chỉ bị xóa sau khi **tất cả samples trong đó** hết hạn; latency thực còn phụ thuộc workload. Vì vậy:

- TTL không phải một **hard deadline** tuyệt đối bảo đảm không còn dữ liệu sau đúng 7 × 24 giờ.
- Nếu yêu cầu pháp lý “xóa chính xác tại thời điểm T”, phải thiết kế quy trình xóa và chứng thực khác, không dựa duy nhất vào TTL.
- Đổi `granularity`/bucket span có thể ảnh hưởng thời điểm buckets đủ điều kiện xóa.

### 7.3. Bật/đổi TTL ở collection hiện có

Theo tài liệu MongoDB, có thể dùng `collMod`:

~~~javascript
// Ví dụ thay retention cho collection time-series có thật.
const lab = db.getSiblingDB("ts288_lab")

lab.runCommand({
  collMod: "telemetry7d",
  expireAfterSeconds: 14 * 24 * 60 * 60
})
~~~

Đổi xuống retention ngắn hơn có thể khiến **nhiều buckets cùng đủ điều kiện xóa**, gây I/O và thay đổi dung lượng nhanh. Phải có kế hoạch rollout, backup/quyền truy cập và monitoring; không dùng lệnh này vô tình trên production.

### 7.4. Partial TTL theo metadata từ MongoDB 7.0

Từ **MongoDB 7.0**, có thể tạo **partial TTL index** dùng `partialFilterExpression` **chỉ dựa vào metaField**, để có retention khác nhau theo nhóm series.

~~~javascript
// Chỉ chạy trên lab MongoDB 7.0+.
// Tạo riêng collection chưa có TTL ở cấp collection:
lab.createCollection("telemetry_tiered", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

lab.telemetry_tiered.createIndex(
  { observedAt: 1 },
  {
    name: "ttl_temp_short",
    expireAfterSeconds: 7 * 24 * 60 * 60,
    partialFilterExpression: {
      "meta.kind": "temperature"
    }
  }
)
~~~

Index này đặt thời hạn hết hạn cho nhóm meta.kind temperature theo quy tắc. Nếu collection cũng có `expireAfterSeconds` cấp collection, partial TTL có thể thiết lập **retention ngắn hơn** cho nhóm matching; không dùng partial TTL để kỳ vọng kéo dài hơn TTL cấp collection đang áp dụng cho tất cả measurements.

Không đặt partial TTL filter dựa trên `temperatureC` hay `observedAt` khi giới hạn yêu cầu **chỉ metadata**. Xem [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) và [Automatic Removal (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/).

### 7.5. TTL khác deleteOne theo timestamp

| Mục tiêu | Cơ chế | Đặc điểm |
|---|---|---|
| Xóa dữ liệu cũ định kỳ | Time-series `expireAfterSeconds` | Hiệu quả theo buckets, không tức thì. |
| Nhóm device VIP giữ 30 ngày, nhóm thường 7 ngày | Policy/partial TTL theo metadata 7.0+ | Cần kiểm tra cách kết hợp TTL cấp collection và partial index. |
| Xóa ngay một sample sai | `deleteOne` từ 7.0+ | Cần target logic chính xác; có thể repack bucket, không nằm trong transaction. |
| Xóa mọi data của device bị thu hồi | `deleteMany` theo metadata | 5.1+ có điều kiện, cần chặn ingestion và verify sau xóa. |
| Xóa mọi dữ liệu trước cutoff tùy ý | 7.0+ `deleteMany` hoặc TTL/retention migration | Với 5.1–6.x filter timeField không phù hợp manual delete. |

### 7.6. Timestamp quá xa khoảng thông thường

MongoDB Manual lưu ý timestamps trước `1970-01-01` hoặc sau `2038-01-19T03:14:07Z` có những cân nhắc về index/optimization; nên tham khảo trang Limitations và thiết kế index timeField thích hợp. Đừng đưa hệ thống vào chuỗi lỗi vì timestamps sai hàng chục năm mà không kiểm tra dữ liệu nguồn và TTL behavior.

## 8. Giao dịch: được **đọc**, không được **ghi** time-series

MongoDB có multi-document transactions cho những collections thông thường trên replica set/sharded cluster hỗ trợ. Nhưng time-series collections có giới hạn **rất cụ thể**:

> **Không thể ghi vào time-series collection trong transaction. MongoDB hỗ trợ đọc từ time-series collection trong transaction.**

Quy tắc này áp dụng dù thao tác là một measurement `insertOne`, metadata `updateMany` hoặc `deleteOne` được hỗ trợ ngoài transaction. **Không có cách “thêm session” để biến lệnh ghi đang bị cấm thành hợp lệ.**

### 8.1. So sánh các tình huống

| Thao tác | Ngoài transaction | Trong multi-document transaction |
|---|---|---|
| `telemetry.insertOne(measurement)` | Hợp lệ theo format/version. | **Không hỗ trợ**. |
| `telemetry.insertMany([...])` | Hợp lệ theo format/version. | **Không hỗ trợ**. |
| `telemetry.updateMany(metaFilter,metaUpdate)` | Có giới hạn, 5.1+. | **Không hỗ trợ**. |
| `telemetry.deleteMany(metaFilter)` | Theo version: 5.1+ với filter giới hạn, 7.0+ rộng hơn. | **Không hỗ trợ**. |
| `telemetry.deleteOne(measurementFilter)` | 7.0+ ngoài transaction. | **Không hỗ trợ**. |
| `telemetry.find(...)` | Hợp lệ. | **Có thể đọc** trong transaction khi deployment hỗ trợ. |
| `telemetry.aggregate([...read stages...])` | Hợp lệ với stage restrictions. | Có thể đọc trong transaction theo hạn chế stages/read concern. |
| Ghi vào `deviceCatalog` (collection thường) | Hợp lệ. | Có thể ghi trong transaction thường nếu đủ điều kiện. |
| Ghi `deviceCatalog` và `telemetry` **cùng commit** | Hai operations độc lập. | **Không thực hiện trực tiếp được** bằng transaction chứa time-series write. |

### 8.2. Ví dụ ý định **không được hỗ trợ**

~~~javascript
// KHÔNG CHẠY NHƯ GIẢI PHÁP: đây là anti-pattern để nhận diện.
const session = db.getMongo().startSession()
const sdb = session.getDatabase("ts288_lab")

try {
  session.startTransaction()

  // Ghi vào time-series trong transaction sẽ bị từ chối.
  sdb.telemetry.insertOne({
    observedAt: new Date(),
    meta: { deviceId: "sensor-04", site: "HCM" },
    temperatureC: 29.0
  })

  // Dù có insert vào collection thường, giao dịch trên vẫn không hợp lệ.
  sdb.deviceCatalog.updateOne(
    { _id: "sensor-04" },
    { $set: { lastSeenAt: new Date() } }
  )

  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  print("Time-series write in transaction is not supported")
} finally {
  session.endSession()
}
~~~

Đây là code **minh họa trường hợp không được hỗ trợ**, không phải ví dụ cần chạy để chứng minh. Không nên cố bắt lỗi rồi tiếp tục `commitTransaction`, hoặc chạy time-series write **ngoài session giữa callback** mà vẫn quảng cáo hai writes có all-or-nothing.

### 8.3. Ví dụ **đọc time-series trong transaction**

Trên replica set/sharded deployment hỗ trợ transactions, một read-only transaction có thể đọc time-series và collection thường trong cùng phạm vi:

~~~javascript
const session = db.getMongo().startSession()
const sdb = session.getDatabase("ts288_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const samples = sdb.telemetry.find({
    "meta.deviceId": "sensor-01",
    observedAt: {
      $gte: ISODate("2026-11-14T08:00:00Z"),
      $lt: ISODate("2026-11-14T08:05:00Z")
    }
  }).sort({ observedAt: 1 }).toArray()

  printjson(samples)

  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  throw err
} finally {
  session.endSession()
}
~~~

Đây là **đọc** time-series, không thay đổi measurement. Không cần mở read-only transaction cho mọi dashboard; dùng khi business thật sự đòi snapshot consistency theo tính năng hỗ trợ.

### 8.4. Giới hạn snapshot khi drop/rename/re-create collection

Trang Limitations hiện hành lưu ý rằng reads trên time-series với read concern `"snapshot"` bảo đảm snapshot isolation **trong trường hợp không có hoạt động drop/rename concurrent** trên các collections liên quan. Re-create cùng namespace với `granularity` khác cũng có thể ảnh hưởng guarantee snapshot mong đợi.

Đừng xây quy trình “read trong transaction thật lâu trong khi job khác drop/re-create time-series collection” rồi suy ra snapshot semantics giống một tập documents không đổi. Cần phối hợp **schema migration/DDL window** và thời gian snapshot.

### 8.5. Read concern và write concern không thay đổi giới hạn transaction ghi

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

Các options trên điều khiển snapshot/acknowledgment theo semantics transaction, **không cấp thêm quyền ghi time-series trong transaction**. Tương tự, `retryWrites:true` hoặc `w:"majority"` không biến nhiều time-series inserts thành all-or-nothing.

### 8.6. Một lệnh `insertMany` ngoài transaction có atomic toàn lô không?

Không được suy rằng vì đã gửi nhiều measurements trong một `insertMany`, toàn bộ lô trở thành một transaction. Khi write có lỗi một phần (validation/duplicate ID trong collection khác, network/size, writeConcern, v.v.), cần xem **partial success, acknowledged counts và retry semantics** theo driver/server.

Time-series có bucketing nội bộ; không dùng chi tiết bucket implementation để suy ra ứng dụng có transaction toàn lô. Nếu cần một batch telemetry có business state “chưa publish cho tới khi toàn bộ đủ”, hãy dùng **batch manifest/ingest ledger** ở collection thường, rồi phát hành trạng thái sau khi đã verify dữ liệu.

## 9. Giao dịch với hệ thống nghiệp vụ: thiết kế thay thế

Một service IoT nhận sample và muốn cùng lúc:

1. Ghi measurement vào `telemetry` (time-series).
2. Cập nhật `deviceCatalog.lastSeenAt` (collection thường).
3. Ghi event để downstream xử lý.

Vì write vào time-series **không được ở trong transaction**, không thể viết một MongoDB transaction trực tiếp bao cả ba thao tác. Cần chọn một mô hình phù hợp với mức nhất quán nghiệp vụ.

### 9.1. Nếu telemetry là nguồn dữ liệu phụ, cho phép eventual consistency

~~~text
Ingest sample
    |
    +-- insert telemetry (time-series)
    |
    +-- update deviceCatalog.lastSeenAt (normal collection)
    |
    +-- publish event
         |
         +-- nếu lỗi: retry/reconcile theo stable eventId
~~~

Đây là **nhiều writes độc lập**. Chỉ hợp lý nếu sản phẩm **chấp nhận trạng thái trung gian** hoặc có worker sửa sai. Phải nói rõ failure cases: sample đã ghi nhưng catalog chưa cập nhật, hoặc catalog đã cập nhật dù sample không ghi.

### 9.2. Transactional outbox trên **collection thường**

Một hướng có kiểm soát hơn:

~~~text
1. MongoDB transaction (chỉ normal collections):
     Insert ingestLedger(eventId, payload, status="PENDING")
     Update deviceCatalog ingestStatus
     Insert outbox(eventId, type="INGEST_SAMPLE")
   Commit
         |
         v
2. Worker đọc outbox/ledger đã commit:
     Insert measurement vào time-series (ngoài transaction)
     Mark ingestLedger state="WRITTEN"
         |
         v
3. Reconcile/repair khi worker timeout hoặc duplicate
~~~

MongoDB transaction đảm bảo ledger/catalog/outbox **cùng commit**. Nhưng `telemetry` vẫn được ghi **ngoài transaction**. Vì vậy overall workflow có thể **eventually consistent** và không nên quảng cáo “đã atomically commit cả telemetry”.

### 9.3. Khó khăn: dedupe measurement trên time-series

Time-series **không hỗ trợ unique indexes** như collection thường theo Manual. Nếu worker insert measurement thành công nhưng chết trước khi đánh dấu ledger WRITTEN, retry có thể tạo **duplicate measurement**.

Một workflow cần:

- Stable `eventId` lưu cùng measurement để truy vết.
- Unique `eventId` trong **collection thường** để xử lý nhiều ingest requests lặp.
- State machine PENDING / PROCESSING / WRITTEN / FAILED, retry với lease và reconciliation.
- Khi retry outcome không rõ, có thể **tra cứu measurement theo eventId + meta/time** và quyết định skip/reconcile; nhưng điều này không phải unique constraint nguyên tử trên time-series.
- Khi cần **exactly-once** được bảo đảm cứng cho measurements, cân nhắc dùng **normal collection làm nguồn sự thật** rồi copy sang time-series cho analytics, hoặc giải pháp storage có idempotent constraints phù hợp.

**Không tuyên bố transaction của ledger bảo đảm exactly-once cho insert vào time-series** — hai bước không cùng một transaction.

### 9.4. Dữ liệu corrections nên có history/audit riêng

Một measurement sai từ thiết bị có thể cần “sửa” nhưng vẫn lưu bản gốc để audit:

~~~javascript
// Collection thường, unique logical correctionId:
{
  _id: "CORR-1001",
  eventId: "MEAS-123",
  deviceId: "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  correctedTemperatureC: 29.0,
  reason: "recalibration",
  createdAt: new Date()
}
~~~

Lưu correction trong **normal collection** giúp update/status/version/unique keys và transaction cùng business records khi cần. Reader có thể ưu tiên correction giá trị mới khi tổng hợp hoặc materialize một read model. **Không có cập nhật vật lý time-series measurement bắt buộc**.

### 9.5. Khi cần atomic business record, đổi ranh giới lưu trữ

Nếu nghiệp vụ là sổ cái tài chính, mỗi sự kiện phải có unique ID, phải atomically commit với account balance hoặc invoice, thì **time-series có thể không nên là source of truth**, dù dữ liệu có timestamp. Một normal collection với transactions/unique indexes có thể phù hợp, còn time-series phục vụ **projection để phân tích theo thời gian**.

**Chọn storage theo invariant quan trọng nhất, không chỉ vì thông số nén.**

## 10. Sharding time-series: hỗ trợ từ MongoDB 5.1, với shard key riêng

Một time-series collection có thể tăng tới hàng tỷ measurements, và một replica set không đủ throughput/dung lượng. Từ **MongoDB 5.1**, có thể **shard time-series collections** trên sharded cluster phù hợp.

Nhưng **không được chọn shard key tùy ý**. Các field được cho phép theo Manual gồm:

- **`metaField`** — ví dụ `meta`.
- **Subfields của `metaField`** — ví dụ `meta.deviceId`, `meta.site`.
- **`timeField`** — ví dụ `observedAt`, với hạn chế bắt buộc là **ranged** và **đứng cuối shard key pattern**; đồng thời **deprecated từ 8.0** nếu có trong key.

Không được shard trực tiếp theo `temperatureC`, `humidityPct`, `quality` hoặc `_id` nếu chúng không thuộc nhóm field cho phép.

### 10.1. Một số shard key hợp lệ theo danh mục field

Với collection:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta"
}
~~~

những candidates có thể là:

~~~javascript
// Metadata subfield ranged:
{ "meta.deviceId": 1 }

// Metadata subfield hashed:
{ "meta.deviceId": "hashed" }

// Compound metadata:
{ "meta.site": 1, "meta.deviceId": 1 }

// Metadata + time field trailing/ranged:
{ "meta.deviceId": 1, observedAt: 1 }
// Tuy nhiên: có timeField => deprecated từ MongoDB 8.0.
~~~

Không tự suy rằng mọi key trên đây sẽ được triển khai thành công bất kể dataset/index topology; còn yêu cầu shard key supporting index, collation, thời điểm sharding, version và balancer. Bảng trên chỉ minh họa **field eligibility**.

### 10.2. Ví dụ sai shard key

~~~javascript
// Không hợp lệ: measurement field.
{ temperatureC: 1 }

// Không hợp lệ: _id không thuộc trường được phép.
{ _id: "hashed" }

// Không hợp lệ: timeField không được hashed.
{ observedAt: "hashed" }

// Không hợp lệ: timeField đứng trước một field khác.
{ observedAt: 1, "meta.deviceId": 1 }
~~~

Với time-series, `timeField` phải là **ranged** và **trailing field** nếu được dùng. Từ 8.0, dù một số cấu hình có thể vẫn được nhận để tương thích, chúng bị đánh dấu **deprecated**, nên không đưa vào shard key mới nếu có lựa chọn metadata-based tốt hơn.

### 10.3. Kết nối qua `mongos`

Trên một sharded cluster, ứng dụng/mongosh kết nối đến **query router `mongos`**. Tùy version và cấu hình, có thể kiểm tra:

~~~javascript
db.adminCommand({ hello: 1 })
// Với mongos, response thông thường có msg: "isdbgrid".

sh.status()
~~~

Không chạy `sh.shardCollection()` trên một standalone mongod rồi kết luận time-series không hỗ trợ sharding khi thực tế topology chưa đúng. **Sharding yêu cầu cluster**, trong khi time-series collection thông thường có thể tạo trên replica set hoặc standalone hỗ trợ.

### 10.4. Tạo một time-series collection rồi shard trên cluster lab

**Chỉ chạy trên sharded cluster lab** (≥ 5.1, mọi prerequisites đã đáp ứng):

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.createCollection("telemetry_sharded", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "minutes"
  }
})

// Tạo supporting index, ví dụ hashed index trên metadata deviceId.
lab.telemetry_sharded.createIndex({
  "meta.deviceId": "hashed"
})

// Lệnh quản trị thay đổi sharding cho collection lab:
sh.shardCollection(
  "ts288_lab.telemetry_sharded",
  { "meta.deviceId": "hashed" }
)
~~~

MongoDB Manual minh họa cách shard một time-series collection đã tồn tại theo metadata subfield; khi collection đã khai báo timeseries, `shardCollection()` có thể dùng option trong metadata hiện có. Để shard collection đang có dữ liệu, supporting index cần được chuẩn bị theo yêu cầu của server. Các bước trên là **DDL cho lab**, không phải lệnh người dùng cuối chạy trong mỗi request.

### 10.5. Chọn metadata có cardinality và tần suất hợp lý

Giả sử thiết bị:

~~~text
site=HCM:    90% measurements
site=HN:      7% measurements
site=DN:      3% measurements

deviceId:    200.000 giá trị khác nhau
~~~

Nếu shard key là `{"meta.site":1}`, có rất ít giá trị; mọi measurement tại HCM mang **cùng key**, dễ tạo hot range/chunk. Nếu shard theo `{"meta.deviceId":"hashed"}` và có nhiều devices đủ phân tán, writes có cơ hội trải ra nhiều shards.

**Nhưng:** nếu một sensor duy nhất gửi 80% measurements, hash(deviceId) vẫn cố định cho sensor đó. Hash không thể phân chia **một giá trị metadata duy nhất** thành nhiều shard keys. Cần phân loại **hot device**, cách tạo series, bucket cardinality hoặc phân vùng mô hình khác.

### 10.6. Vì sao sharding theo thời gian có rủi ro?

~~~text
observedAt ranges:
  Shard A: trước tháng 8
  Shard B: tháng 8 đến tháng 10
  Shard C: từ tháng 10 về sau

Mọi sample mới được gắn timestamp hiện tại:
  -> range mới nhất
  -> có thể dồn inserts vào một shard/chunk.
~~~

Thời gian của dữ liệu ingest thông thường **tăng đơn điệu**. Ranged shard key theo `observedAt` có thể khiến gần như mọi inserts mới tới cùng một range. Balancer chuyển range có thể **chuyển vị trí hotspot** nhưng không tự rải từng timestamp vào nhiều shards. Đây là nguyên nhân MongoDB khuyến cáo ưu tiên metadata-based keys và **deprecated timeField-containing shard keys từ 8.0**.

### 10.7. Compound shard key có timeField còn được xem thế nào?

~~~javascript
{ "meta.deviceId": 1, observedAt: 1 }
~~~

Trong các phiên bản cho phép, key này có thể giúp target theo device rồi theo time range, nhưng **mọi timeField-containing shard key**, kể cả compound, nằm trong cảnh báo deprecated từ MongoDB 8.0. Không chỉ key `{observedAt:1}` thuần mới bị cảnh báo.

Với hệ thống cũ đang dùng key đó, cần kiểm tra planned upgrade và phương án **reshard metadata-only** khi phiên bản cho phép, không gỡ timeField trực tiếp khỏi config catalog.

### 10.8. Targeted reads dựa trên shard key

Với shard key:

~~~javascript
{ "meta.deviceId": "hashed" }
~~~

truy vấn:

~~~javascript
lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

router có thể hash deviceId và target range/shard phù hợp. Nếu chỉ lọc `observedAt` mà bỏ deviceId, có thể phải truy vấn nhiều/tất cả shards, dù timeField index local vẫn giúp đọc từng shard.

**Index cục bộ và shard routing là hai lớp khác nhau.** Có index timeField không đồng nghĩa `mongos` biết shard đích khi shard key là metadata.

## 11. Zone sharding và balancer trên time-series

MongoDB Manual hiện hành nói **zone sharding không hỗ trợ time-series collections**. Balancer phân phối dữ liệu time-series sharded theo cơ chế của cluster, **không thể dùng zone rules của regular collection như một cách chắc chắn ép series EU sang nhóm shards EU**.

### 11.1. Một anti-pattern về data residency

~~~text
Requirement:
  sensor EU data chỉ được lưu trên EU shards.

Developer:
  Tạo time-series + zone ranges theo meta.region = EU.

Vấn đề:
  Time-series không hỗ trợ zone sharding như regular sharded collection.
~~~

Nếu data residency là ràng buộc cứng, cần thiết kế **separate clusters/regions**, routing ở ingestion, retention/replication policy tương ứng, hoặc data model/collection khác được hỗ trợ. Không dựa vào zone sharding time-series để đạt cam kết pháp lý khi Manual nói không hỗ trợ.

### 11.2. Balancer phân phối data chứ không tự chữa mọi hot series

Ngay cả với `meta.deviceId` hashed, một thiết bị cực nóng có thể làm shard chứa giá trị hash đó chịu write pressure lớn. Balancer có thể di chuyển chunks/ranges theo phân bố dữ liệu, nhưng không biến một giá trị shard key thành nhiều giá trị để chia writes.

Khi đánh giá:

- Xem data distribution và chunks, không chỉ tổng GB.
- Xem write QPS/CPU/IOPS theo shard, không chỉ balancer enabled.
- Tìm một `deviceId` hoặc nhóm metadata chiếm phần lớn ingest.
- Xem query patterns có đưa đủ metadata key để targeted không.
- Đo mức phân phối **trong giờ cao điểm**, không chỉ trung bình ngày.

### 11.3. Không thao tác `system.buckets` để cân bằng

Bucket storage có namespace/quy tắc nội bộ. Không sửa metadata hay chuyển bucket bằng direct writes vào `system.buckets.*`. Dùng những công cụ sharding/resharding được hỗ trợ cho **logical time-series collection**, đúng phiên bản, và tránh những admin commands bị giới hạn với time-series.

### 11.4. Vì sao docs nói “có sharding” nhưng “không hỗ trợ một số sharding commands”?

Hai điều không mâu thuẫn:

- **Shard collection được hỗ trợ từ 5.1** với các key hợp lệ.
- **Các thao tác quản trị cấp thấp cụ thể** có thể không được hỗ trợ trên sharded time-series, và **reshard** chỉ được hỗ trợ từ 8.0.10 theo điều kiện.

Không diễn giải câu “sharding administration commands unsupported” thành “không thể shard time-series” hoặc “8.0.10 không thể reshard”. Phải đọc lệnh cụ thể và trang Limitation của version hiện dùng.

## 12. Resharding time-series: khác biệt 7.0 với 8.0.10+

### 12.1. MongoDB 7.0: chưa thể reshard time-series

Trang **Time Series Collection Limitations v7.0** nêu: **không thể reshard một sharded time-series collection**, dù có thể **refine shard key** theo những điều kiện hỗ trợ.

Điều này rất khác regular sharded collections, vốn đã hỗ trợ `reshardCollection` từ MongoDB 5.0 trong các trường hợp phù hợp.

Ví dụ key hiện tại:

~~~javascript
{ "meta.site": 1 }
~~~

Muốn **thêm suffix**:

~~~javascript
{ "meta.site": 1, "meta.deviceId": 1 }
~~~

có thể xem xét `refineCollectionShardKey` nếu phù hợp version, index và data model; refine chỉ **thêm field cuối**, không được đổi thành `{"meta.deviceId":"hashed"}` bằng refine.

### 12.2. MongoDB 8.0.10+: hỗ trợ resharding time-series

Trang Manual hiện hành và tutorial chính thức nói **từ 8.0.10** có thể reshard time-series collection nếu **tất cả shards trong collection chạy 8.0.10 hoặc mới hơn**.

Một ví dụ minh họa ý định đổi:

~~~javascript
// Đang dùng key metadata theo site:
{ "meta.site": 1 }

// Muốn chuyển sang metadata theo thiết bị:
{ "meta.deviceId": "hashed" }
~~~

Lệnh quản trị dạng:

~~~javascript
// MẪU DDL - CHỈ DÙNG KHI CLUSTER LAB ĐÃ ĐÁP ỨNG ĐỦ ĐIỀU KIỆN.
db.adminCommand({
  reshardCollection: "ts288_lab.telemetry_sharded",
  key: { "meta.deviceId": "hashed" }
})
~~~

**Đừng chạy lệnh chỉ vì MongoDB version string của một router bắt đầu bằng 8.** Với 8.0.0–8.0.9 chưa đáp ứng mốc **8.0.10**, và quy tắc yêu cầu **all shards** đủ patch level. DDL còn phụ thuộc khả năng support hashed key, supporting indexes, shard distribution/capacity và restrictions cụ thể.

### 12.3. Đổi key có thể đổi query contract

Trước reshard:

~~~javascript
// Key { "meta.site": 1 }:
lab.telemetry_sharded.find({ "meta.site": "HCM" })
// Có cơ hội targeted theo site.
~~~

Sau reshard sang `{"meta.deviceId":"hashed"}`:

~~~javascript
lab.telemetry_sharded.find({ "meta.site": "HCM" })
// Không có deviceId -> có thể broadcast.

lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: { $gte: start, $lt: end }
})
// Có deviceId equality -> có cơ hội targeted.
~~~

Điều này là đánh đổi giữa **sensor-specific queries** và **site-wide queries**. Không reshard chỉ để chia đều writes mà bỏ qua tỷ lệ site-wide dashboards và global analytics.

### 12.4. Một runbook reshard có kiểm soát

1. Xác minh **version và FCV** trên cluster; tất cả shards đủ **8.0.10+**.
2. Lấy query shapes từ API: device+time, site+time, global time, updates/deletes theo metadata.
3. Đo metadata cardinality/frequency; tránh một device quá nóng hoặc site có quá ít values.
4. Xác minh indexes, metadata field availability, uniqueness policies và mongos targeting.
5. Ước tính **storage headroom**, I/O/network, replication lag, cơ chế cutover, tác động tới jobs.
6. Thử reshard với dữ liệu/workload đại diện trên staging; quan sát reads/writes và thời gian.
7. Chuẩn bị monitoring, maintenance strategy và **plan xử lý rollback/recovery** theo hỗ trợ của bản server.
8. Thực hiện production theo quy trình quản trị đã phê duyệt; không thao tác trực tiếp với bucket internals.
9. Đo trước/sau: ingest QPS per shard, p95/p99, range scans, storage distribution, error rates và app compatibility.

Không cho rằng reshard luôn **không có interruption**: tài liệu chính thức nêu các pha clone/catch-up/critical section có tradeoffs về tài nguyên và có thể ảnh hưởng writes tùy version.

### 12.5. Không thể đổi `timeField`/`metaField` bằng reshard

`reshardCollection` thay **shard key**, không biến cấu hình time-series:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta"
}
~~~

thành một cấu hình field khác như `timeField:"eventTime"`, `metaField:"tags"`. Hai lựa chọn `timeField`/`metaField` chỉ được xác định **lúc tạo collection**; nếu cần đổi tên hoặc ý nghĩa, hãy lập kế hoạch tạo collection mới và di chuyển/kiểm tra dữ liệu, không coi reshard là cơ chế đổi loại collection.

## 13. Kiểm tra đúng phiên bản, FCV và loại collection trước khi chạy

Một quy trình đáng tin bắt đầu bằng **inventory môi trường**, không bắt đầu bằng việc gửi `updateOne` thử trên dữ liệu thật.

### 13.1. Server version

Trong `mongosh`:

~~~javascript
db.version()

db.adminCommand({ buildInfo: 1 })
~~~

`buildInfo.version` phản ánh binary của endpoint xử lý lệnh. Trong sharded cluster, `mongos` có thể trả version riêng; muốn xác minh điều kiện **“tất cả shards ≥ 8.0.10”**, phải xem **từng shard replica set**, không chỉ một router.

### 13.2. FCV trong môi trường nâng cấp

Khi nâng cấp server, **featureCompatibilityVersion** có thể còn ở mức cũ. Trên node/endpoint và quyền hỗ trợ:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

Lệnh có thể cần kết nối/quyền phù hợp với `mongod` thay vì một `mongos` hoặc có thay đổi ở các branch; nếu môi trường không hỗ trợ command từ endpoint đó, dùng dashboard/administration API của deployment để xác minh FCV.

**Điều phải ghi lại:** server binary version từng thành phần, FCV hiện tại, đường kết nối qua mongos hay standalone/replica set, và phiên bản Java Driver. Chỉ có một dòng `db.version()` chưa chứng minh đủ yêu cầu toàn cluster.

### 13.3. Xác minh collection thật sự là time-series

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.getCollectionInfos({ name: "telemetry" })

lab.runCommand({
  listCollections: 1,
  filter: { name: "telemetry" }
})
~~~

Kết quả thường chứa `type:"timeseries"` và cấu hình `options.timeseries.timeField`, `options.timeseries.metaField`, `granularity`; nếu có TTL cấp collection thì có `expireAfterSeconds`.

Đừng chỉ nhìn tên `telemetry` rồi giả định đây là time-series; một collection thường hoàn toàn có thể chứa timestamp và metadata giống nhau. **Limitations phụ thuộc collection type**, không phụ thuộc tên field.

### 13.4. Xác minh shard key và topology

Trên cluster lab với `mongos`:

~~~javascript
db.adminCommand({ hello: 1 })
sh.status()
~~~

Lấy **shard key thật** từ metadata, không lấy nhầm secondary index:

~~~javascript
lab.telemetry_sharded.getIndexes()
~~~

`getIndexes()` cho biết indexes được định nghĩa; **index nào là shard key** phải xác minh qua sharding metadata. Một collection có index `{"meta.deviceId":"hashed"}` chưa chắc đã được shard theo nó.

### 13.5. Bảng hành động trước khi dùng tính năng

| Tính năng | Kiểm tra tối thiểu |
|---|---|
| Tạo time-series | MongoDB ≥ 5.0, `timeField` đúng BSON Date, metadata/retention. |
| Metadata `updateMany` | ≥ 5.1, filter/update chỉ metadata, không upsert, multi. |
| `deleteOne` hoặc delete theo timestamp | ≥ 7.0, operation ngoài transaction. |
| Secondary index trên measurement field | ≥ 6.0 và index loại được hỗ trợ. |
| Partial TTL theo metaField | ≥ 7.0, filter chỉ metadata, index trên timeField. |
| Shard time-series | ≥ 5.1, mongos, shard key fields hợp lệ, supporting index. |
| Shard key có timeField | Cảnh báo **deprecated từ 8.0**, tránh trong thiết kế mới. |
| Reshard time-series | **Tất cả shards ≥ 8.0.10**, kiểm tra FCV/DDL prerequisites. |
| Transaction ghi telemetry | **Không hỗ trợ** theo Manual. |
| Transaction chỉ đọc telemetry | Được hỗ trợ khi deployment phù hợp; lưu ý snapshot/DDL. |

## 14. Index và cấu hình collection cũng có mốc phiên bản

Khi thảo luận update/sharding, một lỗi thường gặp là giả định index của normal collection sẽ giống time-series. Thực tế metadata/time-series indexes có cơ chế tối ưu theo buckets và giới hạn riêng.

### 14.1. Không có index `_id` mặc định

MongoDB Manual cho biết time-series collections **không tự tạo `_id` index** như collections thông thường. Vì vậy:

- `find({_id:id})` không mặc định hưởng index `_id_`.
- Không dựa vào `_id` để thực thi **unique measurement identity**.
- Không dùng kết luận “mọi collection mặc định unique `_id`” cho time-series.
- Nếu cần dedupe cứng theo eventId, cân nhắc normal collection với unique index hoặc event ledger.

Ở MongoDB **8.3**, tài liệu còn mô tả thay đổi liên quan tên/hint `"_id_"`; nếu upgrade hoặc downgrade dùng index custom, cần xem branch-specific limitations.

### 14.2. Index measurement fields từ MongoDB 6.0

Từ **6.0**, có thể thêm **secondary index trên các field measurement** được hỗ trợ:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.telemetry.createIndex({
  temperatureC: 1
})
~~~

Mục đích là cải thiện queries có filter theo value. Nó **không cấp quyền cập nhật `temperatureC`**. Index giúp đọc dữ liệu đã lưu; giới hạn update vẫn metadata-only.

MongoDB index time-series ở **bucket level**, sử dụng min/max các field đo trong trường hợp phù hợp. Vì vậy explain/index semantics có thể khác index trên từng document thường; đo query plan thật thay vì suy luận “nếu có index temp thì mỗi sample có một B-tree entry như normal collection”.

### 14.3. Default compound index từ MongoDB 6.3

Từ **6.3**, MongoDB tạo **compound index mặc định trên `metaField` và `timeField`** cho time-series collections mới nếu đủ điều kiện.

~~~javascript
lab.telemetry.getIndexes()
~~~

Hãy đọc kết quả index thực. Nếu collection được tạo ở bản cũ rồi upgrade, **không suy rằng mọi index mới mặc định đã xuất hiện trên collection cũ**. Nếu collection không khai báo metaField, cấu hình mặc định cũng khác.

### 14.4. Những index type bị giới hạn

Theo Database Manual:

- **Không hỗ trợ unique indexes** cho time-series.
- Không hỗ trợ text indexes.
- Multikey/sparse/2d index có giới hạn **gắn với metaField**; không coi mọi measurement field đều được index kiểu bất kỳ.
- Index TTL có quy tắc riêng: partial TTL theo metadata từ 7.0, retention theo timeField.

Do đó không dùng time-series để lưu data cần unique constraint mạnh trên `(deviceId,observedAt)` rồi giả sử tạo unique compound index là giải pháp giống normal collection.

### 14.5. Chọn metadata để tối ưu buckets

Một số nguyên tắc:

1. `metaField` nên là **field ít hoặc không đổi**.
2. Đặt identifiers thường dùng trong filters vào metadata nếu business semantics phù hợp.
3. Tránh metadata đổi theo mỗi sample như `lastHeartbeatAt`, `temperatureC`, `eventCounter`.
4. Tránh quá nhiều distinct metadata combinations khiến bucket rất ít measurements.
5. Nếu shard theo metadata, đánh giá distribution/hot series và query routing cùng lúc.

Đây là quyết định trước khi collection được tạo, vì **không thể đổi tên `metaField`/`timeField` sau khi tạo**.

### 14.6. Granularity và custom bucket size

`granularity` giúp MongoDB chọn khoảng thời gian gom measurements:

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "meta",
  granularity: "minutes"
}
~~~

Từ **6.3**, có option `bucketMaxSpanSeconds`/`bucketRoundingSeconds` để tùy chỉnh interval; khi dùng hai option này, chúng phải **bằng nhau**, và được dùng thay `granularity` theo quy tắc Manual.

Nếu cần đổi granularity, `collMod` có các giới hạn: có thể **tăng bucket span**, nhưng không tự do giảm span trên collection hiện tại. Đừng tạo job “đổi granularity từ hours xuống seconds” mà không xem khả năng hỗ trợ; việc cần giảm độ rộng bucket có thể đòi collection mới/migration.

### 14.7. Một loại collection đã tạo không được đổi trực tiếp

Một normal collection có documents như:

~~~javascript
{ observedAt: new Date(), meta: { deviceId: "S1" }, temperatureC: 25 }
~~~

không thể trở thành time-series chỉ bằng đổi option `timeseries` trong `collMod`. Tương tự time-series không thể chuyển thẳng sang normal collection bằng một update option. Cần **tạo collection đích đúng type**, chuyển dữ liệu và điều chỉnh client cutover.

### 14.8. Giới hạn document và bucket

Trang Limitations hiện hành nêu **kích thước tối đa document trong time-series là 4 MB** (khác 16 MiB của normal document). Với bucket, Manual mô tả giới hạn số measurements/dung lượng tối đa và cơ chế giảm kích thước nếu cardinality cao.

Đừng thiết kế **một measurement** chứa payload hàng chục MB chỉ vì “MongoDB documents cho 16 MB”. Nếu sample có ảnh/video/log raw lớn, lưu payload riêng và giữ URI/reference hoặc metrics/tags gọn trong time-series.

## 15. `$merge`, `$out` và migration/correction

Time-series không hỗ trợ mọi cách ghi output aggregation như một regular collection. Đây là nguồn lỗi khi muốn **rebuild** dữ liệu đã ingest sai.

### 15.1. `$merge` không thể ghi **vào** time-series

Theo Manual hiện hành, không thể dùng `$merge` để thêm dữ liệu từ collection khác **vào một time-series collection**:

~~~javascript
// Không phải một pipeline output hợp lệ vào time-series.
db.source.aggregate([
  { $match: { sourceType: "sensor" } },
  {
    $merge: {
      into: "telemetry",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

Một lý do nghiệp vụ: semantics `whenMatched:"replace"` dựa trên upsert/replace documents, trong khi time-series không cho update measurement tùy ý.

### 15.2. `$merge` từ time-series **ra collection thường**

Nếu cần materialize report:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.telemetry.aggregate([
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        day: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      avgTemperatureC: { $avg: "$temperatureC" }
    }
  },
  {
    $merge: {
      into: "daily_sensor_rollups",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
~~~

Output `daily_sensor_rollups` là **collection thường**, không phải time-series; nó có thể có unique identity cho mỗi `(deviceId,day)` qua `_id`. Đây là chiến lược lưu **read model** dùng cho dashboards thay vì update từng measurement.

Với hệ thống lớn, không quét lại toàn history mỗi lần: dùng incremental windows, checkpoints và nguồn ingestion phù hợp. Vì time-series **không hỗ trợ change streams** theo Manual hiện hành, không thiết kế một time-series change stream như cơ chế duy nhất đồng bộ read model.

### 15.3. `$out` vào time-series theo phiên bản hỗ trợ

Manual hiện hành mô tả `$out` có thể ghi dữ liệu **vào time-series** trong các điều kiện cụ thể, trong khi `$merge` không thể làm target. Hỗ trợ này có **mốc phiên bản**; không dùng trên 5.0/6.0 chỉ vì current docs nêu nó.

`$out` có semantics **thay thế output collection** và liên quan DDL/indexes; không dùng nó như một update từng measurement hoặc correction job production nhỏ. Khi migration, nên dùng collection mới, xác minh measurements, indexes, TTL, sharding/ownership trước cutover.

### 15.4. Kế hoạch tạo lại collection đúng cấu hình

Nếu cần thay `timeField`/`metaField`:

~~~text
1. Chọn schema/timeField/metaField mới.
2. Tạo time-series collection MỚI với options đúng.
3. Trích xuất/biến đổi dữ liệu qua công cụ batch/aggregation phù hợp.
4. Insert theo batches với kiểm tra kết quả/retention.
5. So sánh counts, min/max timestamp, samples per device, aggregates.
6. Tạo indexes/shard key/TTL thích hợp.
7. Chuyển ứng dụng đọc/ghi theo kế hoạch cutover.
8. Giữ bản cũ theo retention/rollback policy; xóa khi đủ điều kiện.
~~~

Không dùng direct writes vào bucket internals hoặc sửa metadata trong config server như đường tắt migration.

## 16. Java Sync Driver: version-aware operations

MongoDB Java Sync Driver cung cấp các methods `createCollection()`, `insertOne()`, `updateOne()`, `updateMany()`, `deleteOne()`, `deleteMany()`, `startSession()` giống khi làm việc với normal collection. **Đó là API ở client**, không phải cam kết rằng tất cả methods hợp lệ với time-series trên mọi server.

Các ví dụ dưới đây dùng Java Sync Driver dòng hiện đại và collection `ts288_lab.telemetry`. Nếu môi trường của bạn khác, kiểm tra class/package/API trong tài liệu driver version đang dùng.

### 16.1. Tạo time-series collection từ Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesOptions;
import org.bson.Document;

// mongoClient đã cấu hình tới MongoDB 5.0+.
MongoDatabase database = mongoClient.getDatabase("ts288_lab");

TimeSeriesOptions tsOptions = new TimeSeriesOptions("observedAt")
    .metaField("meta");

database.createCollection(
    "telemetry_java",
    new CreateCollectionOptions().timeSeriesOptions(tsOptions)
);

MongoCollection<Document> readings =
    database.getCollection("telemetry_java");
~~~

Đây là một lệnh **tạo collection một lần**; không gọi trong mỗi request. Nếu muốn dùng `granularity` hoặc `expireAfterSeconds`, kiểm tra API tương ứng trong driver; server vẫn quyết định collection options có được hỗ trợ theo FCV/phiên bản không.

### 16.2. Chèn measurement hợp lệ

~~~java
import java.util.Date;

Document measurement = new Document("observedAt", new Date())
    .append("meta", new Document("deviceId", "sensor-java-01")
        .append("site", "HCM")
        .append("kind", "temperature"))
    .append("temperatureC", 27.8)
    .append("humidityPct", 70);

readings.insertOne(measurement);
~~~

`observedAt` được lưu bằng BSON Date (Java `Date`) chứ không phải chuỗi ISO nguyên dạng. Chọn metadata ổn định, tránh tạo một bộ meta mới mỗi lần heartbeat nếu không cần.

### 16.3. Query theo metadata và khoảng thời gian

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import java.time.Instant;
import java.util.Date;

Date start = Date.from(Instant.parse("2026-11-14T08:00:00Z"));
Date end = Date.from(Instant.parse("2026-11-14T09:00:00Z"));

readings.find(Filters.and(
    Filters.eq("meta.deviceId", "sensor-java-01"),
    Filters.gte("observedAt", start),
    Filters.lt("observedAt", end)
))
.sort(Sorts.ascending("observedAt"))
.forEach(doc -> System.out.println(doc.toJson()));
~~~

Query này hợp lệ vì filter đo `observedAt` là giới hạn của **update metadata**, không phải giới hạn của **read**. Nhiều người nhầm “update chỉ được match meta” thành “find không được match timestamp”; đó là hai operation khác nhau.

### 16.4. Metadata-only `updateMany()` từ 5.1

~~~java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

MongoCollection<Document> telemetry =
    database.getCollection("telemetry");

UpdateResult result = telemetry.updateMany(
    Filters.eq("meta.deviceId", "sensor-01"),
    Updates.set("meta.ownerTeam", "iot-ops")
);

System.out.println("matched = " + result.getMatchedCount());
System.out.println("modified = " + result.getModifiedCount());
~~~

Đây là kiểu **multi-update metadata-only**; không đặt `upsert(true)`. Nếu filter:

~~~java
// KHÔNG hợp lệ với metadata-only update:
Filters.and(
    Filters.eq("meta.deviceId", "sensor-01"),
    Filters.gte("observedAt", start)
);
~~~

thì điều kiện timestamp làm update vi phạm giới hạn. Một `Updates.set("temperatureC",29.0)` cũng bị từ chối vì sửa measurement field.

### 16.5. `deleteOne` theo timestamp từ 7.0

~~~java
import com.mongodb.client.result.DeleteResult;

// Dùng trên MongoDB 7.0+ và chỉ trên LAB.
DeleteResult deletion = telemetry.deleteOne(
    Filters.and(
        Filters.eq("meta.deviceId", "sensor-02"),
        Filters.eq(
            "observedAt",
            Date.from(Instant.parse("2026-11-14T08:02:00Z"))
        )
    )
);

System.out.println("deleted = " + deletion.getDeletedCount());
~~~

Với 5.1–6.x, singleton delete không được hỗ trợ; với 7.0+ thao tác này còn phải **chạy ngoài transaction**. Nếu cùng deviceId/timestamp có nhiều measurements, `deleteOne` chỉ xóa **một document khớp**, không bảo đảm “xóa eventId cụ thể” nếu không có identity policy.

### 16.6. Không dùng driver transaction cho time-series writes

~~~java
import com.mongodb.client.ClientSession;

// KHÔNG PHẢI cách ghi hợp lệ:
try (ClientSession session = mongoClient.startSession()) {
    session.startTransaction();

    // Dù Java Driver có overload nhận session,
    // MongoDB server không hỗ trợ write vào time-series trong transaction.
    telemetry.insertOne(session, measurement);

    session.commitTransaction();
}
~~~

Đây là **anti-pattern minh họa**, không cần chạy. Nếu application cần transaction giữa ingestion record và một business document, chỉ ghi vào **normal collections** trong transaction; time-series insertion phải qua một workflow khác, hoặc đổi source-of-truth collection type.

### 16.7. Đọc time-series qua session

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import java.util.ArrayList;
import java.util.List;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

try (ClientSession session = mongoClient.startSession()) {
    List<Document> resultDocs = session.withTransaction(() -> {
        List<Document> docs = new ArrayList<>();
        telemetry.find(session,
            Filters.eq("meta.deviceId", "sensor-01")
        ).into(docs);
        return docs;
    }, options);

    resultDocs.forEach(doc -> System.out.println(doc.toJson()));
}
~~~

Mẫu **chỉ đọc** này dùng deployment hỗ trợ transactions và Java Driver compatible. Cần nhớ lưu ý snapshot isolation khi có **concurrent drop/rename/re-create** collection như mục 8.4. Không mở transaction chỉ để đọc một time range đơn giản khi read concern thông thường đủ yêu cầu.

### 16.8. Không tự xử lý lỗi version bằng retry mù

Nếu server trả lỗi “time-series only supports multi updates”:

- **Không** retry `updateOne` 10 lần.
- **Không** đổi `writeConcern` hay thêm `bypassDocumentValidation` để thử.
- **Không** cast collection sang một class Java khác.
- **Sửa cách ghi** thành `updateMany` hợp lệ nếu nghiệp vụ thực sự là metadata change.
- Nếu nghiệp vụ là sửa measurement, chuyển sang correction/migration workflow được hỗ trợ, không chỉ thay method.

Nếu một lệnh delete theo timestamp thất bại ở server 6.0, việc Java Driver 5.x có method `deleteMany()` cũng không làm server hỗ trợ predicate đó.

## 17. Khi dữ liệu sai: thiết kế correction theo phiên bản

Đây là bài toán thực tế: sensor-01 lúc 08:01 báo `temperatureC:28.7` nhưng sau hiệu chuẩn, giá trị đúng là `29.0`. Ứng dụng muốn thấy giá trị sửa mà vẫn bảo toàn lịch sử.

### 17.1. Cách 1 — Append-only correction overlay

Giữ raw measurement trong time-series. Tạo **normal collection** `measurementCorrections`:

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

lab.measurementCorrections.createIndex(
  { logicalEventId: 1 },
  { unique: true }
)

lab.measurementCorrections.insertOne({
  _id: "CORR-01",
  logicalEventId: "sensor-01@2026-11-14T08:01:00Z",
  deviceId: "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  correctedTemperatureC: 29.0,
  correctedAt: new Date(),
  reason: "calibration",
  status: "APPROVED"
})
~~~

Khi báo cáo, ứng dụng lấy raw measurements và overlays theo logicalEventId để chọn số đo hiệu lực. Với nhiều corrections, schema có thể dùng `version`/`revision` và chỉ một bản APPROVED hiện hành được định nghĩa bằng transaction/CAS ở **normal collection**.

**Ưu điểm:** không sửa time-series measurement, giữ audit/rollback, dùng unique indexes ở normal collection. **Nhược điểm:** reader/projection phức tạp hơn; cần consistency policy của overlay và cache invalidation.

### 17.2. Cách 2 — Delete + insert measurement đúng từ 7.0

Trên MongoDB **7.0+**, ngoài transaction, có thể xóa measurement sai rồi insert phiên bản đúng:

~~~javascript
// Chỉ mô tả ý định; không chạy trực tiếp trên production.
const target = {
  "meta.deviceId": "sensor-01",
  observedAt: ISODate("2026-11-14T08:01:00Z")
}

// Bước A: deleteOne theo filter hỗ trợ 7.0+.
lab.telemetry.deleteOne(target)

// Bước B: insert đúng.
lab.telemetry.insertOne({
  observedAt: ISODate("2026-11-14T08:01:00Z"),
  meta: { deviceId: "sensor-01", site: "HCM", kind: "temperature" },
  temperatureC: 29.0,
  humidityPct: 72,
  quality: "corrected"
})
~~~

**Cảnh báo:** Đây là **hai writes độc lập, không atomic cùng nhau**, vì time-series writes không được ở trong multi-document transaction. Nếu insert B thất bại sau delete A, sample có thể bị mất; nếu insert trước rồi delete sau, có thể có duplicates. Vì thế trong production cần staging/backup, operation ID, reconciliation, maintenance/cutover strategy hoặc ưu tiên overlay. Đừng trình bày delete+insert như một `updateOne` nguyên tử.

Ngoài ra, nếu hai measurements có cùng deviceId/timestamp, `deleteOne` có thể chọn một bản không phải bản muốn xóa. Cần business identity phân biệt hoặc thao tác có kế hoạch rõ hơn.

### 17.3. Cách 3 — Rebuild time-series collection mới

Khi hàng triệu samples bị sai timezone hoặc muốn đổi `timeField`, một workflow migration an toàn hơn:

~~~text
Source time-series, read-only snapshot/report
       |
       v
Transform & validate (UTC, meta, measurement format)
       |
       v
Destination time-series NEW
       |
       v
Validate counts/time range per device/checksums/aggregates
       |
       v
Switch app read/write with cutover plan
       |
       v
Keep source for rollback/retention; remove only when approved
~~~

Cần giải quyết **incoming writes** trong thời gian migration: dual-write, buffer/queue, pause ingestion hoặc controlled replay, với dedupe policy. Không giả định copy xong là không có sample mới được insert.

### 17.4. Khi privacy deletion là bắt buộc

Nếu phải xóa dữ liệu của device/user theo yêu cầu:

- Với **5.1–6.x**, filter metadata-only có thể xóa toàn bộ series nhưng không xóa tùy ý theo timestamp/measurement.
- Với **7.0+**, có thể lọc cụ thể hơn.
- **TTL không ngay lập tức**, chỉ phù hợp retention định kỳ.
- Phải chặn ingest mới nếu identity bị thu hồi, xóa dữ liệu dẫn xuất, indexes/read models/backups theo chính sách và ghi audit không tiết lộ PII.

Vì thời gian xóa vật lý và retention backup khác deletion ở logical collection, không tuyên bố “`deleteMany` trả success là đã xóa khỏi mọi bản sao/backup trên thế giới”.

## 18. Sharding và cập nhật metadata: điểm giao nhau dễ sai

Một time-series sharded theo:

~~~javascript
{ "meta.deviceId": "hashed" }
~~~

được định tuyến theo metadata deviceId. Nếu application chạy:

~~~javascript
lab.telemetry_sharded.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.ownerTeam": "iot-ops" } }
)
~~~

thì filter có shard key equality, và field ownerTeam không thuộc key; đây là **ý tưởng cập nhật metadata** phù hợp hơn so với việc đổi chính deviceId. Nhưng vẫn cần:

- Verify **server ≥ 5.1** và operation metadata-only `multi:true`.
- Kiểm tra shard targeting/explain/metrics, không suy rằng mọi update_many đều chạm một shard bất kể distribution.
- Ước tính số measurements matched; một series có thể chứa hàng triệu samples.
- Xem ảnh hưởng của thay đổi metadata đến bucket organization và index writes.
- Không dùng transaction để gói update metadata với `deviceCatalog`.

### 18.1. Sai: đổi shard key value như một field bình thường

~~~javascript
// Rủi ro đặc biệt vì meta.deviceId là shard key.
lab.telemetry_sharded.updateMany(
  { "meta.deviceId": "sensor-01" },
  { $set: { "meta.deviceId": "sensor-99" } }
)
~~~

Đổi series identity và shard key đồng thời có thể không được hỗ trợ hoặc yêu cầu semantics phức tạp theo version. Hơn nữa, những truy vấn cũ dựa trên deviceId sẽ thay đổi kết quả lịch sử. Không sửa ID của historical telemetry chỉ để “hợp hồ sơ mới” nếu policy đúng là giữ nguồn lúc đo.

### 18.2. Có timestamp trong query update để target chunk?

Không:

~~~javascript
// Không hợp lệ theo giới hạn update:
lab.telemetry_sharded.updateMany(
  {
    "meta.deviceId": "sensor-01",
    observedAt: { $gte: start, $lt: end }
  },
  { $set: { "meta.site": "SGN" } }
)
~~~

Đừng nhầm **read routing** với **metadata update predicate**. Với `find()`, meta + time range rất hợp lý. Với `updateMany()`, việc thêm timeField vào filter vi phạm quy định update chỉ được match metadata. Khi business cần thay metadata cho **một khoảng thời gian cụ thể**, hãy dùng correction overlay/migration, không chọn query không được hỗ trợ.

### 18.3. Truy vấn thiếu metadata shard key có thể scatter-gather

~~~javascript
lab.telemetry_sharded.find({
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

Query này tìm toàn bộ devices trong khoảng thời gian, có thể phải đọc **nhiều/all shards** vì thiếu `meta.deviceId`. Đó không nhất thiết là lỗi với global analytics, nhưng có thể rất tốn khi API chỉ muốn một device.

Muốn targeted, thêm metadata key được xác thực:

~~~javascript
lab.telemetry_sharded.find({
  "meta.deviceId": "sensor-01",
  observedAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T09:00:00Z")
  }
})
~~~

**Index theo timestamp trên từng shard không tự cấp cho router khả năng biết shard nào chứa một device** nếu metadata key không có trong filter.

## 19. Runbook kiểm tra time-series khi nâng cấp MongoDB

Một dự án nâng cấp **6.0 → 7.0 → 8.0/8.0.10+** có thể muốn bật `deleteOne`, secondary indexes, resharding hoặc đổi retention. Trước khi thay đổi, cần một quy trình kiểm chứng không làm hỏng dữ liệu.

### Bước 1 — Lập inventory tính năng

Ghi lại:

| Hạng mục | Thông tin cần lấy |
|---|---|
| Server binary versions | `mongos`, config servers, từng shard replica set, secondaries. |
| FCV | Trạng thái trước/sau rolling upgrade. |
| Time-series collections | Tên, `timeField`, `metaField`, granularity, TTL, custom bucket options. |
| Shard keys | Key pattern, hashed/ranged, có `timeField` không. |
| Query shapes | Filter theo metadata/time range, aggregate toàn cluster, singleton lookups. |
| Write shapes | Inserts, metadata updates, deletes, retry patterns, batches. |
| Indexes | Meta/time compound, measurement indexes, TTL, index types bị cấm. |
| Retention | Tuổi dữ liệu, partial TTL, privacy deletion deadlines. |
| Transactions | Có code nào cố insert/update/delete time-series trong session transaction? |
| Integrations | Outbox/queue, dashboards, rollups, correction ledger, monitoring. |

### Bước 2 — Đối chiếu bảng tương thích với version đích

Ví dụ:

~~~text
Source 6.0:
  updateMany(meta-only)   -> có
  deleteMany(meta-only)   -> có
  deleteOne(sample)       -> không
  measurement index      -> có
  sharded time-series    -> có
  reshard time-series    -> không
  write transactions     -> không

Target 7.0:
  deleteOne(sample)       -> mới có
  deleteMany(time/value)  -> được nới
  partial TTL metadata    -> có
  write transactions     -> vẫn không
  reshard time-series    -> vẫn không

Target 8.0.10+:
  reshard time-series    -> có điều kiện all shards >= 8.0.10
  timeField shard key    -> deprecated từ 8.0
  write transactions     -> vẫn không
~~~

Đây là **ma trận kiểm tra minh họa**, không thay thế release notes về patch/FCV. Nếu cluster còn mixed versions trong rolling upgrade, không bật feature mới trên live traffic trước khi topology và FCV đủ điều kiện.

### Bước 3 — Kiểm tra schema bằng `listCollections`

~~~javascript
const lab = db.getSiblingDB("ts288_lab")

const collections = lab.getCollectionInfos({ name: "telemetry" })
printjson(collections)
~~~

Xác định collection thực là time-series. Đừng chạy mẫu update metadata hoặc reshard nếu tên collection đang trỏ tới một normal collection khác/view do ứng dụng tạo.

### Bước 4 — Kiểm tra dữ liệu/time ranges

~~~javascript
lab.telemetry.aggregate([
  {
    $group: {
      _id: "$meta.deviceId",
      sampleCount: { $sum: 1 },
      firstAt: { $min: "$observedAt" },
      lastAt: { $max: "$observedAt" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Trước migration, lưu counts/min/max theo device hoặc partitions đại diện. Sau migration, dùng cùng quy tắc để so sánh. Với dữ liệu cực lớn, chạy aggregate trong maintenance window hoặc dùng sampling/rollups để tránh tạo tải quá cao.

### Bước 5 — Kiểm tra queries và indexes

~~~javascript
lab.telemetry.getIndexes()

lab.telemetry.explain("executionStats").aggregate([
  {
    $match: {
      "meta.deviceId": "sensor-01",
      observedAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T09:00:00Z")
      }
    }
  },
  { $sort: { observedAt: 1 } }
])
~~~

Đọc plan theo version, đặc biệt bucket filtering/unpack stages và indexes used. Không suy “giới hạn update” ngăn query `find` theo timestamp; đó là hai chuyện khác nhau.

### Bước 6 — Kiểm tra logic writes theo phiên bản

Trong codebase, tìm các thao tác:

~~~text
updateOne(timeSeries)
replaceOne(timeSeries)
updateMany(timeSeries with timeField filter)
upsert(timeSeries)
deleteOne(timeSeries)
deleteMany(timeSeries by value/time)
session.withTransaction(...timeSeries.insert/update/delete...)
bulkWrite(timeSeries with invalid operations)
$merge into timeSeries
~~~

Mỗi entry cần xác minh server version và data model. Nếu cùng một release ứng dụng phải hỗ trợ clusters 6.0 và 7.0, ứng dụng **không thể luôn gọi `deleteOne` time-series** rồi trông chờ 6.0 nhận được; cần feature gate, fallback workflow hoặc nâng cấp đồng bộ.

### Bước 7 — Xác minh sharding

Nếu collection được shard:

- Xác nhận shard key chỉ dùng **metaField/subfield/timeField** được phép.
- Nếu có `timeField` trong key, ghi nhận cảnh báo deprecated 8.0 và chiến lược tương lai.
- Đối với reshard, xác nhận **tất cả shards ≥ 8.0.10** và FCV/DDL support.
- Xem throughput per shard để tránh hot device/metadata key low-cardinality.
- Không dùng zones cho time-series như collection thường vì Manual nói không hỗ trợ.
- Dùng `mongos` và metadata chính thức, không kết nối trực tiếp bucket internals.

### Bước 8 — Thử failure cases trên staging

Các hành vi cần verify trong test:

- `updateMany` đúng metadata chạy được trên bản hỗ trợ.
- `updateOne` metadata-only bị từ chối.
- `updateMany` có timeField filter bị từ chối.
- `updateMany` sửa measurement field bị từ chối.
- `upsert:true` bị từ chối.
- Delete theo thời gian chỉ được bật trên 7.0+.
- Ghi time-series trong transaction bị từ chối; read-only txn được phép trên topology hỗ trợ.
- TTL xóa trễ theo bucket; không kỳ vọng xóa chính xác từng giây.
- Shard key không hợp lệ bị từ chối trong cluster lab.

Đây là **danh sách hành vi để triển khai test tại môi trường phù hợp**, không phải lệnh destructive cần chạy trong production. Bài không giả lập kết quả của cluster thực tế.

### Bước 9 — Rollout và theo dõi

Giám sát:

- Ingestion rate, failed inserts, retries, document sizes.
- Bộ nhớ bucket catalog, WiredTiger cache, IOPS, compression/storage ratio.
- Query latency p50/p95/p99 theo device + time range.
- Metadata update matched/modified counts và latency.
- Delete/TTL throughput, backlog và retention lag.
- Shard data/write distribution, balancer health, migrations nếu shard.
- Invalid timestamps, missing meta identifiers.
- Corrections và duplicate event IDs trong ledger.

Nếu lỗi tăng sau nâng cấp, so lại server version/FCV và driver behavior trước khi thay data model. Không downgrade trực tiếp mà bỏ qua **time-series compatibility constraints** giữa các branches.

## 20. Những sai lầm thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “Time-series cũng là collection nên updateOne mọi field được.” | Unsupported operation. | Metadata-only `updateMany` với điều kiện chặt từ 5.1. |
| “Chỉ sửa meta thì updateOne được.” | Singleton update vẫn bị cấm. | Dùng `updateMany`, không limit số docs. |
| “Filter timeField được nếu chỉ update meta.” | Vi phạm filter chỉ metadata. | Query update chỉ metadata, hoặc correction workflow. |
| “Có thể `$set:{temperatureC:...}` nếu dùng multi.” | Measurement update bị từ chối. | Không sửa measurement bằng time-series update. |
| “Update pipeline giống modifier `$set`.” | Kiểu update không được hỗ trợ. | Dùng update operator document theo Manual. |
| “Thêm `upsert:true` để sinh measurement mới.” | Time-series update không cho upsert. | `insertOne`/`insertMany` với timestamp hợp lệ. |
| “`bulkWrite` bỏ qua giới hạn time-series.” | Operation bên trong vẫn bị kiểm tra. | Giới hạn áp dụng cho từng write type. |
| “MongoDB 5.0 có thể xóa measurements theo thời gian.” | Manual delete không hỗ trợ. | Dùng TTL/migration theo phạm vi hoặc nâng cấp. |
| “`deleteMany({observedAt:...})` chạy ở 6.0.” | Filter ngoài metaField. | Delete theo timeField được nới từ 7.0. |
| “7.0 chỉ cho deleteMany, không deleteOne.” | Bỏ qua cải tiến 7.0. | `deleteOne` được hỗ trợ 7.0+, ngoài txn. |
| “7.0 cho delete, vậy xóa trong transaction được.” | Write transaction time-series vẫn bị cấm. | Phân biệt delete predicate và txn support. |
| “TTL xóa sample đúng lúc hết hạn.” | Không tính bucket/granularity/TTL monitor. | TTL có độ trễ, bucket chỉ xóa khi tất cả samples hết hạn. |
| “Partial TTL lọc theo temperatureC.” | Partial TTL filter phải dựa metadata. | Dùng metaField filter từ 7.0. |
| “Thời gian luôn nên là shard key.” | Monotonic insert hotspot. | Ưu tiên metadata key; `timeField` deprecated từ 8.0. |
| “Shard theo `_id` hoặc temperatureC được.” | Field shard key không hợp lệ. | Chỉ metaField/subfields/timeField. |
| “Hashed timeField giúp timestamp chia đều.” | timeField không được hashed. | Hashed key có thể dùng trên metadata. |
| “Chỉ timeField-only key bị deprecated.” | Bỏ qua compound keys. | Mọi key **chứa** timeField bị cảnh báo từ 8.0. |
| “Time-series hỗ trợ zone sharding như collection thường.” | Zone sharding không được hỗ trợ. | Thiết kế cluster/region riêng khi cần residency. |
| “Mọi 8.0 đều reshard time-series được.” | 8.0.0–8.0.9 chưa đạt mốc. | **8.0.10+ trên tất cả shards**. |
| “7.0 có refine nên cũng có reshard.” | Nhầm hai thao tác. | 7.0 không reshard time-series; 8.0.10+ mới hỗ trợ. |
| “Reshard giúp đổi tên metaField/timeField.” | Nhầm shard key và collection configuration. | Collection mới để đổi timeField/metaField. |
| “Driver mới tự mở khóa feature server cũ.” | Server từ chối dù client có API. | Gate theo server binary + FCV. |
| “Đã index temperatureC thì được update temperatureC.” | Index không đổi write constraints. | Index phục vụ read. |
| “`_id` unique như normal collection.” | Có thể tạo trùng logical measurements. | Time-series không có `_id` index mặc định/unique index support. |
| “Ghi telemetry vào transaction với deviceCatalog là atomic.” | Time-series write bị cấm trong txn. | Normal outbox/ledger + eventual ingestion. |
| “Outbox bảo đảm exactly-once time-series inserts.” | Retry sau lost response có thể tạo duplicate. | Stable eventId, reconciliation; normal source of truth nếu cần. |
| “Có change stream trực tiếp trên time-series.” | Unsupported theo Manual. | Dùng ingestion event stream/outbox hoặc normal collection. |
| “`$merge` có thể ghi time-series.” | Không được làm `$merge` target. | `$merge` ra normal collection; `$out` theo version. |
| “Sửa bucket internals để né giới hạn.” | Rủi ro storage inconsistency. | Chỉ logical API, migration/correction. |
| “Collection thường chỉ cần `collMod` thành time-series.” | Không thể đổi loại collection trực tiếp. | Tạo collection mới và migrate. |

### 20.1. Năm nhóm thao tác có quy tắc khác nhau

Một câu:

~~~javascript
lab.telemetry.find({
  observedAt: { $gte: ISODate("2026-11-14T08:00:00Z") }
})
~~~

có thể **đọc** theo `observedAt`. Nhưng nếu thay `find` thành `updateMany` và giữ filter đó, bạn đã đi vào **quy định khác** — metadata-only predicate. Tương tự, `deleteMany` theo timestamp từ 7.0 là hợp lệ ngoài transaction, nhưng `updateMany` theo timestamp vẫn không hợp lệ.

**Read / update / delete / transaction / shard DDL là năm nhóm tính năng khác nhau, có version gates khác nhau.**

### 20.2. Bốn câu hỏi review trước khi merge

1. **Đang chạy server version và FCV nào?**
2. **Operation là update, delete, read, transaction hay sharding?** Không lấy rule của nhóm này áp sang nhóm kia.
3. **Filter và fields sửa có chạm metadata, timeField hay measurement?**
4. **Nếu request lỗi/timeout, có retry/idempotency/reconciliation hợp lý mà không cần time-series transaction không?**

## 21. Bảng quyết định thiết kế theo nhu cầu thực tế

| Yêu cầu | Phiên bản tối thiểu / điều kiện | Giải pháp đề xuất |
|---|---|---|
| Ghi nhiệt độ mỗi phút | Time-series từ 5.0 | `insertOne`/`insertMany`, chọn metadata ổn định. |
| Chuẩn hóa địa điểm cho tất cả samples của một device | 5.1+, update chỉ metadata, multi, không upsert | `updateMany` theo meta deviceId. |
| Sửa đúng một sample nhiệt độ | Time-series update không hỗ trợ trực tiếp | Correction overlay hoặc delete+insert từ 7.0, **không nguyên tử**. |
| Xóa toàn bộ samples một sensor | 5.1+, meta filter, multi | `deleteMany({"meta.deviceId":...})`, chặn ingest nếu xóa vĩnh viễn. |
| Xóa một sample theo device và timestamp | 7.0+, ngoài transaction | `deleteOne` có filter đủ chọn lọc; xác minh identity. |
| Retention 7 ngày | Time-series có TTL | `expireAfterSeconds`, hiểu độ trễ theo bucket. |
| Retention khác theo loại device | 7.0+, partial TTL filter trên metaField | Partial TTL index kết hợp chính sách retention. |
| Transaction ghi raw telemetry và billing cùng commit | Không hỗ trợ trực tiếp | Đổi source of truth hoặc saga/outbox/ledger. |
| Read snapshot nhiều phép đọc time-series | Deployment txn hỗ trợ, không concurrent DDL làm thay đổi namespace | Read-only transaction/snapshot khi thật sự cần. |
| Scale sensor writes tới nhiều shards | Sharded time-series từ 5.1 | Shard theo meta/subfields có cardinality/tần suất hợp lý. |
| Shard theo measurement value | Không được | Chọn metadata key khác hoặc normal collection. |
| Shard key có timeField | Các bản cũ có thể cho; deprecated 8.0+ | Tránh thiết kế mới, chuẩn bị reshard. |
| Zone-based residency bắt buộc | Time-series zone sharding không hỗ trợ | Region-specific clusters/routing hoặc model khác. |
| Đổi shard key time-series | 8.0.10+, all shards đủ version | Reshard theo runbook. |
| Chỉ thêm suffix vào shard key | Phiên bản cho phép refine | Refine nếu các điều kiện/indexes phù hợp. |
| Đổi tên timeField/metaField | Không sửa trực tiếp sau khi tạo | Tạo collection mới/migration. |
| Dedupe bằng unique eventId | Unique index không hỗ trợ trên time-series | Normal ingest ledger/unique source of truth. |
| Stream thay đổi từng measurement sang queue | Time-series change streams unsupported | CDC từ normal source hoặc outbox ingestion event stream. |
| Tính daily aggregates | Aggregate đọc time-series; `$merge` vào normal collection | Read model/rollup, checkpoint và reconciliation. |

### 21.1. Quy trình quyết định trong 30 giây

~~~text
Bạn muốn sửa một measurement đã ghi?
  -> Không dùng updateOne(timeSeries).
  -> Chọn correction overlay, hoặc xóa/insert (7.0+) có kiểm soát.

Bạn muốn cập nhật metadata cả một nhóm?
  -> Server >= 5.1?
  -> Filter chỉ metaField? Update chỉ metaField?
  -> multi=true, không upsert? => updateMany.

Bạn muốn xóa một measurement?
  -> 7.0+ và ngoài transaction => deleteOne.
  -> 5.1–6.x => chỉ deleteMany theo metadata.
  -> Dữ liệu cũ định kỳ => TTL thường phù hợp hơn.

Bạn muốn ghi time-series cùng business document atomic?
  -> Không hỗ trợ trực tiếp.
  -> Thiết kế normal source of truth/outbox + eventual ingestion.

Bạn muốn shard hoặc reshard?
  -> Shard từ 5.1, key meta/subfield hoặc timeField theo giới hạn.
  -> timeField key deprecated từ 8.0.
  -> Reshard time-series từ 8.0.10 nếu all shards đủ điều kiện.
~~~

## 22. Bài tập thực hành và đáp án

Các bài dưới đây giả định **time-series collection** với `timeField:"observedAt"`, `metaField:"meta"` và metadata dạng `{deviceId,site,kind}`; MongoDB Server version được nêu riêng trong từng đề. Một số ví dụ mang tính destructive nên chỉ chạy trên **database lab** và độc lập với fixtures khác.

### Bài 1 — Tạo time-series từ phiên bản nào?

**Đề:** MongoDB 4.4 có thể tạo native time-series collection bằng `timeseries:{timeField:"observedAt"}` không?

**Đáp án:** Không. Time-series collections native được giới thiệu trong **MongoDB 5.0**. Trên 4.4 có thể lưu measurements vào normal collection theo timestamp, nhưng không có cùng tính năng bucketed time-series native.

### Bài 2 — Measurement hợp lệ cần gì?

**Đề:** Trong time-series với `timeField:"observedAt"`, document:

~~~javascript
{
  observedAt: "2026-11-14T08:00:00Z",
  meta: { deviceId: "S1" },
  temperatureC: 25
}
~~~

có hợp lệ không?

**Đáp án:** `observedAt` đang là **string**, không phải **BSON Date**. Cần:

~~~javascript
{
  observedAt: ISODate("2026-11-14T08:00:00Z"),
  meta: { deviceId: "S1" },
  temperatureC: 25
}
~~~

`metaField` là optional ở cấu hình time-series, nhưng `timeField` bắt buộc và mỗi inserted measurement cần timestamp hợp lệ.

### Bài 3 — Metadata update từ MongoDB 5.1

**Đề:** MongoDB 6.0, muốn đổi `meta.site` cho **mọi measurements của S1**. Viết một update hợp lệ.

**Đáp án:**

~~~javascript
db.telemetry.updateMany(
  { "meta.deviceId": "S1" },
  { $set: { "meta.site": "SGN" } }
)
~~~

Filter chỉ metadata, sửa chỉ metadata, multi=true, không upsert. Đây là phép thay đổi metadata của các matching measurements, không phải chỉ một sample.

### Bài 4 — Vì sao `updateOne` vẫn bị cấm?

**Đề:** Một sensor chỉ có đúng một measurement; dùng `updateOne({"meta.deviceId":"S1"},{$set:{"meta.site":"SGN"}})` được không?

**Đáp án:** **Không** theo ràng buộc time-series update: lệnh không được giới hạn số documents updated. Số matching measurements thực tế là 1 **không làm `updateOne` được phép**. Dùng `updateMany` đúng cấu trúc nếu business cần cập nhật series metadata.

### Bài 5 — Filter theo timeField trong update

**Đề:** Vì chỉ sửa metadata, câu sau có hợp lệ không?

~~~javascript
db.telemetry.updateMany(
  {
    "meta.deviceId": "S1",
    observedAt: { $gte: ISODate("2026-11-14T00:00:00Z") }
  },
  { $set: { "meta.site": "HN" } }
)
~~~

**Đáp án:** Không. Time-series update command chỉ được **match trên metaField**, không dùng timestamp criterion dù field được sửa là meta. Muốn thay label chỉ trong một khoảng thời gian, cần correction overlay/migration có kiểm soát.

### Bài 6 — Sửa temperatureC

**Đề:** MongoDB 8.0, `updateMany({"meta.deviceId":"S1"},{$set:{temperatureC:30}})` có hợp lệ không?

**Đáp án:** Không theo giới hạn update metadata-only trong Manual của dòng 8.0. Phiên bản mới hơn cho delete không có nghĩa update measurement được tự do. Lưu correction ở normal collection, hoặc quy trình delete+insert khi 7.0+ có các bảo vệ tương ứng.

### Bài 7 — Upsert measurement

**Đề:** MongoDB 7.0, muốn `updateMany({meta...},{$set:{...}},{upsert:true})` để thêm sample mới nếu chưa có. Có được không?

**Đáp án:** Không. Time-series update không hỗ trợ `upsert:true`. Dùng `insertOne`/`insertMany` cho measurements mới và quản lý eventId/dedupe ở tầng ingestion; không dùng upsert trên time-series như normal collection.

### Bài 8 — Update pipeline và replacement

**Đề:** Dùng pipeline `[{$set:{"meta.site":"SGN"}}]` hoặc replacement document trong `updateMany` có tương đương modifier update không?

**Đáp án:** Không. Time-series update document theo giới hạn hiện hành **chỉ chứa update operator expressions**; pipeline/replacement update không tự hợp lệ. Dùng `{$set:{"meta.site":"SGN"}}` trực tiếp làm update document.

### Bài 9 — Xóa trên MongoDB 5.0

**Đề:** Dùng `deleteMany({"meta.deviceId":"S1"})` trên time-series ở MongoDB 5.0 để xóa một series cũ được không?

**Đáp án:** Không theo giới hạn ban đầu. 5.0 tập trung insert/read; manual updates/deletes được bổ sung có giới hạn từ **5.1**. Nếu cần retention, dùng TTL; nếu cần selective delete với SLA mới, đánh giá nâng cấp/migration.

### Bài 10 — Xóa trên MongoDB 6.0

**Đề:** Một collection MongoDB 6.0 cần xóa toàn bộ S1 hoặc xóa measurements có timestamp trước 08:00. Hai lệnh nào được phép?

**Đáp án:**

~~~javascript
// Theo metadata-only filter: có thể thực hiện trên 6.0.
db.telemetry.deleteMany({ "meta.deviceId": "S1" })

// Theo timeField filter: không được phép trên 6.0.
db.telemetry.deleteMany({
  observedAt: { $lt: ISODate("2026-11-14T08:00:00Z") }
})
~~~

Với yêu cầu xóa theo thời gian, cân nhắc TTL hoặc 7.0+ với predicate linh hoạt.

### Bài 11 — `deleteOne` từ MongoDB 7.0

**Đề:** MongoDB 7.0, cần xóa một sample của S2 tại 08:02. Viết query.

**Đáp án:**

~~~javascript
db.telemetry.deleteOne({
  "meta.deviceId": "S2",
  observedAt: ISODate("2026-11-14T08:02:00Z")
})
~~~

Thực hiện **ngoài transaction**. Nếu deviceId/timestamp không đủ đảm bảo một sample duy nhất, cần logical identity/reconciliation; `deleteOne` chỉ xóa một matching measurement.

### Bài 12 — Delete trong transaction từ 7.0

**Đề:** Vì 7.0 nới quy định delete, có thể thực hiện `session.startTransaction(); ts.deleteOne(...); session.commitTransaction()` không?

**Đáp án:** Không. **Transaction writes vào time-series không được hỗ trợ**. Delete predicate được nới **ngoài transaction**, không thay đổi ranh giới transaction.

### Bài 13 — TTL và “xóa đúng 00:00”

**Đề:** Collection có `expireAfterSeconds:86400`; một sample lúc 00:00 sẽ bị xóa đúng 00:00 hôm sau phải không?

**Đáp án:** Không. MongoDB TTL time-series xét **bucket**; khi mọi sample trong bucket đủ hạn, TTL monitor mới xóa trong vòng chạy sau (có thể thêm chậm vì workload). TTL không phải hard real-time deletion deadline.

### Bài 14 — Partial TTL theo metadata

**Đề:** MongoDB 7.0 muốn nhóm `meta.kind:"heartbeat"` hết hạn sau 1 ngày trong khi nhóm khác không có expiration. Làm sao?

**Đáp án:** Dùng **partial TTL index** trên `timeField` với `partialFilterExpression` chỉ tham chiếu metadata:

~~~javascript
db.telemetry.createIndex(
  { observedAt: 1 },
  {
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "meta.kind": "heartbeat"
    }
  }
)
~~~

Áp dụng nếu collection/index setup đáp ứng conditions; trước production phải xét TTL cấp collection và trùng index hiện có.

### Bài 15 — Bảng transaction read/write

**Đề:** Trong MongoDB 8.0, đọc time-series bằng `find` trong snapshot transaction được không? Insert time-series trong cùng transaction được không?

**Đáp án:** **Read được** khi deployment hỗ trợ transaction, với caveat snapshot/concurrent drop/rename. **Write không được**, kể cả `insertOne`, `updateMany`, `deleteOne`.

### Bài 16 — Transaction với billing record

**Đề:** Một telemetry sample và một billing record phải cùng commit/abort. Developer tạo `session.withTransaction` để insert cả hai vào time-series + normal collection. Đây có phải giải pháp hợp lệ?

**Đáp án:** Không, time-series insert không thể tham gia multi-document transaction. Nếu invariant all-or-nothing là bắt buộc, cân nhắc lưu **source-of-truth events trong normal collection** với billing trong transaction, sau đó xây time-series projection không đồng bộ với kiểm tra/dedupe. Nếu business cho phép eventual consistency, dùng outbox/state machine/repair worker; không tuyên bố sample đã atomically commit cùng billing.

### Bài 17 — Dedupe bằng `_id`

**Đề:** Ingestion gán `_id = "sensor-01@2026-11-14T08:00Z"`, insert measurement hai lần. Có nên dựa vào MongoDB time-series tự tạo unique `_id_` index để ngăn mọi duplicate không?

**Đáp án:** Không. Time-series **không có index `_id` mặc định như normal collections và không hỗ trợ unique indexes** theo Manual. Cần event ledger/unique key trong normal collection hoặc source-of-truth/storage khác khi exactly-once là yêu cầu cứng.

### Bài 18 — Shard theo temperatureC

**Đề:** Có thể shard time-series theo `{temperatureC:1}` vì đọc các measurements trên 40 °C thường xuyên không?

**Đáp án:** Không. Shard key time-series chỉ có thể chứa **metaField/subfields/timeField** theo hạn chế. Có thể thêm secondary index trên measurement field từ 6.0 cho read selectivity, nhưng index đó không trở thành shard key hợp lệ.

### Bài 19 — Shard theo timeField hashed

**Đề:** `{observedAt:"hashed"}` có hợp lệ trên time-series 7.0 không?

**Đáp án:** Không. Nếu timeField nằm trong shard key, nó phải là **ranged** và nằm **cuối** key pattern. Chỉ metadata/subfields của metaField có thể hashed theo điều kiện.

### Bài 20 — Một key có timeField bị deprecated khi nào?

**Đề:** `{"meta.deviceId":1,observedAt:1}` là compound key. MongoDB 8.0 có cảnh báo deprecated không, hay chỉ `{observedAt:1}` bị?

**Đáp án:** Có cảnh báo. Từ **MongoDB 8.0**, các shard keys **chứa timeField** bị deprecated, kể cả compound với metaField ở đầu. Nên cân nhắc metadata-based key, xem khả năng reshard sau khi đủ 8.0.10.

### Bài 21 — Shard time-series được hỗ trợ từ đâu?

**Đề:** Team đang chạy MongoDB 5.0, có thể `sh.shardCollection("db.telemetry",{"meta.deviceId":"hashed"})` với native time-series không?

**Đáp án:** Không theo hỗ trợ ban đầu; **sharded time-series được hỗ trợ từ 5.1**. Cần sharded cluster và những prerequisites khác, không phải chỉ tạo index.

### Bài 22 — MongoDB 7.0 và reshard

**Đề:** Collection đã shard theo `{"meta.site":1}`, muốn đổi hoàn toàn sang `{"meta.deviceId":"hashed"}`. Server 7.0 có thể chạy `reshardCollection` trên time-series không?

**Đáp án:** Không. Tài liệu time-series v7.0 nói chưa hỗ trợ **reshard** time-series, dù có thể **refine** shard key trong điều kiện phù hợp. Đổi cấu trúc key yêu cầu kế hoạch nâng cấp đến 8.0.10+ hoặc migration khác.

### Bài 23 — 8.0.9 vs 8.0.10

**Đề:** `mongos` là 8.0.10, nhưng một shard còn 8.0.9. Có được reshard time-series ngay không?

**Đáp án:** Không đáp ứng yêu cầu **tất cả shards chạy 8.0.10+**. Hoàn tất nâng cấp các thành phần/FCV theo hướng dẫn, xác minh topology và rollback/capacity trước khi thực hiện.

### Bài 24 — Zone sharding

**Đề:** Mỗi sample có `meta.country:"DE"`; doanh nghiệp buộc giữ mọi DE data trên shards EU. Có thể dùng zone sharding time-series giống regular collection không?

**Đáp án:** MongoDB Manual nêu **time-series không hỗ trợ zone sharding**. Cần region-specific cluster/ingest routing hoặc kiến trúc khác thỏa data residency; không dựa vào zone policy không được hỗ trợ.

### Bài 25 — Hot device trên key hashed

**Đề:** Shard theo `{"meta.deviceId":"hashed"}` nhưng 70% measurements xuất phát từ đúng S1; vẫn có shard nóng. Tại sao?

**Đáp án:** Một giá trị `deviceId:"S1"` có một hash nhất quán; writes cùng value vẫn dồn về range/shard sở hữu hash đó. Hash giúp **nhiều deviceIds** phân tán, không chia một device hot thành nhiều keys. Cần phân tích workload, metadata design, partitioning/ingestion hoặc scale strategy.

### Bài 26 — Read theo time range trên sharded time-series

**Đề:** Key `{"meta.deviceId":"hashed"}`. Query `find({observedAt:{$gte:start,$lt:end}})` có target một shard không?

**Đáp án:** Không chắc, thường cần nhiều/all shards vì filter thiếu `meta.deviceId`. Thêm equality theo deviceId khi API phục vụ một thiết bị; nếu dashboard cần tất cả devices thì multi-shard read là hợp lý, cần tối ưu query/rollup theo workload.

### Bài 27 — Metadata update trên một khoảng thời gian

**Đề:** Site của sensor-01 đổi từ HCM sang DN lúc 10:00. Developer muốn `updateMany({meta.deviceId:"sensor-01",observedAt:{$lt:changeAt}},{$set:{"meta.site":"HCM"}})` trên 8.0. Được không?

**Đáp án:** Không, vì filter timeField trong metadata update không hợp lệ. Định nghĩa **site tại thời điểm đo** bằng metadata ổn định theo giai đoạn, tạo các samples mới với metadata mới, hoặc dùng correction/snapshot policy để bảo toàn lịch sử. Không sửa hàng loạt measurement/time-range bằng update thường.

### Bài 28 — Chọn chỗ lưu trạng thái thiết bị

**Đề:** Service cần liên tục sửa `device.currentStatus`, `lastHeartbeatAt` và `version` với CAS. Có nên đặt các field này vào metaField của mọi measurement để updateMany mỗi giây?

**Đáp án:** Không phù hợp. MetaField nên ít thay đổi; updateMany sẽ chạm nhiều measurements và gây churn. Lưu trạng thái hiện tại trong **normal `deviceState` collection** với `updateOne`/CAS, còn time-series lưu các measurements/history append-only.

### Bài 29 — Secondary index có cấp phép update không?

**Đề:** MongoDB 6.0 đã tạo index `{temperatureC:1}`, một developer nói giờ sửa temperatureC bằng `updateMany` được. Đúng không?

**Đáp án:** Sai. Secondary index hỗ trợ **query** measurement fields; update vẫn chỉ được lọc và sửa **metaField** theo giới hạn time-series. Index không thay đổi capability CRUD.

### Bài 30 — Chuyển normal collection sang time-series

**Đề:** Có normal collection chứa 10 triệu measurements, muốn chạy `collMod` để bật `timeseries:{...}`. Có hợp lệ không?

**Đáp án:** Không thể chuyển collection type trực tiếp. Tạo time-series collection mới với `timeField`/`metaField`/retention rồi migrate theo batches, verify counts/aggregates, kiểm soát concurrent ingestion/cutover.

### Bài 31 — Giảm granularity từ hours xuống seconds

**Đề:** Time-series đang tạo với `granularity:"hours"`. Có thể `collMod` sang `"seconds"` để giảm bucket span ngay không?

**Đáp án:** Theo Manual, bạn có thể **tăng** bucket time span trong các điều kiện cho phép nhưng **không giảm tùy ý** trên collection hiện có. Nếu cần interval nhỏ hơn, cân nhắc tạo collection mới và migrate, không gửi lệnh với kỳ vọng chắc chắn thành công.

### Bài 32 — TTL phân biệt nhóm dữ liệu

**Đề:** Team muốn retention sensor thường 7 ngày, sensor quan trọng 30 ngày. Một collection đã có `expireAfterSeconds:604800` toàn cục; có thể dùng partial TTL để kéo dài sensor quan trọng lên 30 ngày không?

**Đáp án:** Không dựa vào partial TTL như cách vượt qua TTL chung đã xóa dữ liệu sau 7 ngày. Partial TTL có thể **rút ngắn** retention cho một nhóm; muốn một nhóm giữ lâu hơn cần thiết kế TTL chung/partial TTL lại, tách collections theo tier hoặc thay data model/policy.

### Bài 33 — Read snapshot trong lúc drop/re-create

**Đề:** Một long-running read transaction đọc time-series, job khác drop rồi re-create cùng namespace với granularity khác. Có thể mặc định snapshot isolation vẫn đầy đủ không?

**Đáp án:** Không. MongoDB Manual có caveat về **concurrent drop/rename và re-create với granularity khác**. Phải phối hợp DDL/migration window, snapshots và reader lifecycle; không mở transaction rất dài rồi kỳ vọng bất biến qua namespace changes.

### Bài 34 — Dedupe worker thất bại giữa hai bước

**Đề:** Worker đã insert measurement vào time-series thành công nhưng chết trước khi set ingestLedger.state=WRITTEN. Sau restart nó retry. Normal ledger có unique eventId đã bảo đảm measurement không bị insert hai lần chưa?

**Đáp án:** Chưa. Unique eventId ở **normal ledger** chỉ bảo vệ ledger row, còn time-series insert xảy ra ngoài cùng transaction và không có unique constraint tương đương. Cần detection/reconciliation và thiết kế source of truth; nếu exactly-once cứng, ưu tiên source lưu unique event identity trong normal collection và time-series là read projection.

### Bài 35 — Một kế hoạch nâng cấp đầy đủ

**Đề:** Hệ thống MongoDB 6.0 đang dùng time-series sharded key `{"meta.site":1,observedAt:1}`. Muốn xóa measurements sai theo timestamp, tránh deprecated key 8.0, reshard sang `{"meta.deviceId":"hashed"}` và tiếp tục retention 14 ngày. Nêu các bước lớn.

**Đáp án gợi ý:**

1. Inventory server binary/FCV của **tất cả shards**, mongoS/config nodes, dữ liệu, indexes, TTL, query shapes.
2. Nâng cấp theo tài liệu qua các release hỗ trợ, tránh gọi `deleteOne`/timestamp delete trước 7.0.
3. Kiểm tra trong staging các lệnh delete mới từ 7.0, **ngoài transaction** và có backup/reconciliation.
4. Ghi nhận shard key có `timeField` bị deprecated từ 8.0.
5. Đánh giá cardinality/frequency của deviceId; kiểm tra hot devices, query targeting theo metadata/time.
6. Xác minh **mọi shard đủ 8.0.10+** và FCV/DDL prerequisites; thử reshard trên staging, ước tính I/O/capacity/cutover.
7. Kiểm tra `expireAfterSeconds=14 ngày` và TTL bucket lag, không coi đó là deadline cứng.
8. Chuyển production theo runbook, kiểm tra data counts, query latency, write distribution, error rates và backup/rollback policy.

Một đáp án đúng phải phân biệt **delete 7.0** với **reshard 8.0.10**, đồng thời nhớ **write transactions time-series vẫn không được hỗ trợ**.

## 23. Bảng tra cứu nhanh cho developer

### 23.1. Khi gặp lỗi update

| Điều bạn thấy | Kiểm tra đầu tiên |
|---|---|
| `updateOne` bị từ chối | Time-series yêu cầu **multi update**, dùng `updateMany` hợp lệ từ 5.1. |
| `updateMany` bị từ chối dù chỉ sửa metadata | Filter có vô tình chứa `observedAt`, `_id` hoặc measurement field không? |
| `updateMany` báo update không hợp lệ | Update có sửa field ngoài `metaField` hoặc là pipeline/replacement không? |
| `upsert:true` gây lỗi | Upsert không hỗ trợ cho time-series update; insert measurement theo workflow. |
| `bulkWrite` báo unsupported update | Operation bên trong vẫn chịu time-series restrictions. |
| `updateMany` chạy rất lâu | Filter metadata quá rộng, ảnh hưởng nhiều buckets/measurements? Có sharding/routing/hot meta không? |

### 23.2. Khi gặp lỗi delete

| Điều bạn thấy | Kiểm tra đầu tiên |
|---|---|
| `deleteOne` lỗi trên 6.0 | Singleton delete time-series chưa được nới trước 7.0. |
| `deleteMany` theo timestamp lỗi trên 6.0 | 5.1–6.x chỉ match metaField. |
| `deleteMany` theo meta chạy trên 6.0 | Hợp lệ nếu đáp ứng filter/multi; cần kiểm tra data scope. |
| `deleteOne` theo timestamp chạy trên 7.0 | Có hỗ trợ ngoài transaction; không mặc định uniqueness. |
| Delete trong transaction lỗi dù server 8.x | Write time-series trong transaction chưa được hỗ trợ. |
| TTL chưa xóa sample vừa hết hạn | Chờ cả bucket hết hạn và TTL monitor; đây không nhất thiết là lỗi. |

### 23.3. Khi gặp lỗi sharding

| Điều bạn thấy | Kiểm tra đầu tiên |
|---|---|
| `shardCollection` lỗi trên MongoDB 5.0 time-series | Sharded time-series hỗ trợ từ 5.1. |
| Key `{observedAt:"hashed"}` bị từ chối | timeField chỉ được ranged, đứng cuối key khi được dùng. |
| Key `{temperatureC:1}` bị từ chối | Measurement field không nằm trong danh sách shard key hợp lệ. |
| Cảnh báo deprecation trên 8.0 | Shard key có chứa timeField, kể cả compound. |
| `reshardCollection` lỗi trên 7.0 | Chưa hỗ trợ reshard time-series ở branch này. |
| Reshard lỗi với một shard 8.0.9 | Yêu cầu mọi shards trong collection ≥ 8.0.10. |
| Zone policy không hoạt động | Zone sharding không được hỗ trợ cho time-series. |
| Queries time range fan out | Shard key theo metadata; thiếu metadata predicate để target. |

### 23.4. Một mẫu kiến trúc thường hợp lý

~~~text
              IoT device
                  |
                  v
            Ingestion API
                  |
           +------+------+
           |             |
           v             v
    Normal ledger    Queue / outbox
    eventId unique        |
    ingest status         v
           |         Async worker
           |             |
           +-------------+
                         v
                 Time-series collection
                 - timeField
                 - stable metaField
                 - TTL retention
                 - shard by meta if needed
                         |
                         v
                 Aggregation/read model
                         |
                   +-----+------+
                   |            |
                Dashboard   Corrections overlay
                            (normal collection)
~~~

Đây là **một kiến trúc lựa chọn**, không phải quy định MongoDB bắt mọi ứng dụng dùng queue/ledger. Nó phù hợp khi cần tách **nguồn dữ liệu có ID/idempotency mạnh** khỏi **lớp analytics time-series**, và business chấp nhận quá trình projection eventual. Nếu ứng dụng chỉ ingest metrics có thể mất một số samples theo chính sách, kiến trúc có thể đơn giản hơn nhiều.

## 24. Tài liệu MongoDB chính thức theo phiên bản

Các tài liệu dưới đây là nơi đối chiếu cú pháp, giới hạn và thay đổi theo từng branch. Khi một link `/manual/` trỏ tới **current**, người đọc phải chọn lại version nếu đang dùng MongoDB cũ.

### Nền tảng time-series và giới hạn

1. [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — giới thiệu native time-series từ 5.0, bucketed storage và đặc trưng dữ liệu.
2. [About Time Series Data / Bucketing](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-bucketing/) — metadata grouping, buckets, giả định insert/read và compression.
3. [Time Series Collection Limitations — Manual hiện hành](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — update metadata-only, transaction, indexes, sharding, unsupported features.
4. [Time Series Collection Limitations — MongoDB 7.0](https://www.mongodb.com/docs/v7.0/core/timeseries/timeseries-limitations/) — đọc rõ hạn chế reshard trong 7.0 và transaction.
5. [Time Series Collection Limitations — MongoDB 8.0](https://www.mongodb.com/docs/v8.0/core/timeseries/timeseries-limitations/) — đối chiếu quy tắc update, shard key deprecation và điều kiện patch release.
6. [Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/) — `timeField`/`metaField`/`granularity`, examples.
7. [Time Series Collection Considerations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-considerations/) — chọn metadata ổn định và data modeling.
8. [Best Practices for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — shard by metadata và query patterns.

### CRUD, TTL, indexes và aggregation

9. [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — `updateMany` time-series từ 5.1, metadata-only restrictions.
10. [MongoDB 7.0 Release Notes — Time Series Deletes](https://www.mongodb.com/docs/v7.0/release-notes/7.0/) — nới giới hạn `delete`/`deleteOne`/`deleteMany` ở 7.0.
11. [`db.collection.deleteOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/) — semantics xóa một document và version-specific restrictions.
12. [`db.collection.deleteMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/) — semantics xóa nhiều documents.
13. [Set up Automatic Removal (TTL) for Time Series](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — retention, bucket expiry và TTL lag.
14. [Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/) — secondary indexes từ 6.0, default compound index từ 6.3, partial TTL từ 7.0.
15. [Time Series Change Streams — Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/) — unsupported change streams và related features.
16. [`$merge` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — không dùng time-series làm `$merge` target theo giới hạn.
17. [`$out` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/out/) — output collection semantics, khả năng time-series target theo version.
18. [MongoDB Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read behavior và limitations.

### Sharding, version và Java Driver

19. [Shard a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/) — shard from 5.1, supporting indexes, điều kiện reshard 8.0.10+.
20. [`shardCollection` Command](https://www.mongodb.com/docs/manual/reference/command/shardCollection/) — allowed time-series shard key fields và thời điểm deprecation.
21. [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — yêu cầu/chi phí/quy trình resharding.
22. [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — chỉ thêm suffix trong những điều kiện hỗ trợ.
23. [Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/) — routing targeted và broadcast queries.
24. [MongoDB Java Sync Driver — Time Series Collections](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/time-series/) — `TimeSeriesOptions`, `CreateCollectionOptions` và query examples.
25. [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — API `updateMany`/`UpdateResult` và update builders.
26. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession` và API transactions cho normal collections; lưu ý time-series write restriction.
27. [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — upgrade/FCV feature gates.
28. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/manual/reference/versioning/) — lựa chọn branch và kiểm tra patch-level compatibility.

## 25. Kết luận

**Time-series collection không phải normal collection với một index timestamp đặc biệt.** Nó được tối ưu bằng buckets và có ranh giới hỗ trợ riêng. Khi xây dựng ứng dụng, hãy phân biệt rõ **measurement**, **metadata** và **timestamp**, rồi kiểm tra chính xác **server version, FCV, operation type và topology**.

Ba kết luận cần ghi nhớ:

1. **Cập nhật:** Từ **5.1**, các cập nhật được hỗ trợ theo dạng **`updateMany` chỉ match và sửa `metaField`**, dùng update operators, **không upsert**. Không sửa measurement/timeField bằng `updateOne` hay `updateMany` như normal collection. **Delete** là câu chuyện khác: giai đoạn 5.1–6.x chỉ xóa nhiều documents theo metadata, còn **7.0+** nới rộng delete predicates và singleton delete.
2. **Giao dịch:** MongoDB **không hỗ trợ ghi time-series trong multi-document transaction**, dù có thể đọc trong transaction với snapshot caveats. Khi cần gắn telemetry với business state, thiết kế **normal source of truth/ledger, outbox, correction overlay và reconciliation**, không gán cho time-series một bảo đảm atomic không tồn tại.
3. **Sharding:** Từ **5.1** có thể shard time-series bằng `metaField`/subfields hoặc timeField theo giới hạn; timeField shard key **deprecated từ 8.0**, zone sharding không hỗ trợ, và **reshard time-series chỉ được hỗ trợ từ 8.0.10 khi tất cả shards đủ phiên bản**.

Trong production, điều quan trọng hơn việc tìm một “mẹo” vượt hạn chế là **chọn đúng loại collection cho invariant nghiệp vụ**, xây ingestion/correction/retention có idempotency, kiểm chứng shard key theo access patterns, và đối chiếu tài liệu **đúng phiên bản MongoDB đang thực sự vận hành**.
