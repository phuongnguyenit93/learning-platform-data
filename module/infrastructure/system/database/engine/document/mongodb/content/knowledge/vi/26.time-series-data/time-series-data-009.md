# Đánh giá time series collection cho dữ liệu cảm biến và quan sát hệ thống trong MongoDB

Một hệ thống IoT có thể nhận nhiệt độ từ hàng nghìn cảm biến mỗi phút. Một nền tảng vận hành có thể ghi CPU, bộ nhớ, độ trễ request, số lần lỗi và chỉ số tải của nhiều dịch vụ theo từng khoảng thời gian. Những bản ghi này có điểm chung: **giá trị được đo liên tục theo thời gian, đa số được thêm mới thay vì sửa lại, và thường được đọc theo một khoảng thời gian**.

Trong MongoDB, **time series collection** là loại collection được tối ưu cho kiểu workload đó. MongoDB nhóm những phép đo phù hợp vào các **bucket nội bộ**, giúp tổ chức, nén và truy xuất dữ liệu chuỗi thời gian hiệu quả hơn so với việc coi mọi phép đo như một document độc lập theo cách thông thường.

Tuy nhiên, “dữ liệu có timestamp” **không tự động** là lý do để chọn time series collection. Một hệ thống ghi log toàn văn, một bảng trạng thái thiết bị được cập nhật liên tục hoặc một kho giao dịch cần sửa/xóa từng bản ghi có thể có yêu cầu khác hẳn dữ liệu cảm biến. Bài học thuộc chương **Chuỗi thời gian** của module **Database Engine Document MongoDB**, tập trung vào việc **đánh giá khả năng phù hợp**, thiết kế schema, chọn cấu hình, vận hành và so sánh có căn cứ với collection thường.

## 1. Khi nào bài toán thực sự là time series?

Một **measurement** là một phép đo tại một thời điểm:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    tenantId: "tenant-01",
    deviceId: "sensor-01",
    siteId: "factory-a",
    metric: "temperature_c"
  },
  value: 24.5,
  quality: "ok"
}
```

Ở đây:

- `measuredAt`: **thời điểm đo**.
- `meta`: thông tin định danh **nguồn chuỗi dữ liệu**, tương đối ổn định.
- `value`: **giá trị đo**, thay đổi theo thời gian.
- `quality`: thuộc tính của **một phép đo cụ thể**, có thể thay đổi giữa hai phép đo.

Những câu hỏi thường gặp là:

1. Nhiệt độ sensor-01 trong 30 phút gần nhất biến động thế nào?
2. Trung bình và cực đại theo từng phút, giờ hoặc ngày là bao nhiêu?
3. Có khoảng thời gian nào cảm biến ngừng phát tín hiệu?
4. Dịch vụ API nào tăng CPU hoặc tăng tỷ lệ lỗi sau khi triển khai?
5. Dữ liệu thô cần giữ 7, 30 hay 90 ngày; dữ liệu tổng hợp phải giữ bao lâu?

Nếu phần lớn truy vấn thuộc loại **filter theo nguồn + khoảng thời gian + aggregate theo cửa sổ**, time series collection là ứng viên đáng đánh giá.

### Không phải mọi dữ liệu có ngày tháng đều là time series

| Dữ liệu | Đặc điểm | Mức phù hợp ban đầu |
| --- | --- | --- |
| Nhiệt độ, độ ẩm, áp suất theo phút | Append-oriented, filter theo sensor/time, tổng hợp theo cửa sổ | **Rất đáng thử** |
| CPU, RAM, request count theo chu kỳ | Nhiều điểm đo có cùng cấu trúc, truy vấn theo host/service/time | **Rất đáng thử** |
| Dữ liệu điện năng tiêu thụ mỗi 5 phút | Nhiều measurement cho một thiết bị, phân tích theo giờ/ngày | **Đáng thử** |
| Trạng thái hiện tại của thiết bị | Một document bị `update` liên tục để giữ giá trị mới nhất | **Collection thường** thường tự nhiên hơn |
| Hồ sơ khách hàng có `createdAt` | CRUD, tìm theo ID, cập nhật hồ sơ, không chủ yếu phân tích dãy đo | **Không đủ lý do** để dùng time series |
| Audit ledger cần sửa/xóa theo quy tắc riêng và ràng buộc duy nhất | Lịch sử sự kiện nhưng đòi nhiều quy tắc giao dịch/index | **Cần đánh giá kỹ giới hạn** |
| Log text và stack trace dung lượng lớn | Tìm kiếm toàn văn, truy vấn chuỗi/nhãn, retention ngắn | Phụ thuộc query; có thể phù hợp hệ log chuyên dụng hơn |
| Distributed traces với nhiều span/attribute biến động | Metadata cực nhiều chiều, truy vấn theo trace/span ID | **Cần benchmark và so giải pháp chuyên dụng** |

Đây là bảng định hướng, **không phải một benchmark**. Quyết định cuối cùng phụ thuộc số thiết bị, nhịp gửi, query shape, giới hạn phiên bản MongoDB, chi phí index, yêu cầu cập nhật/xóa và SLA.

## 2. Time series collection khác collection thường ở đâu?

Với collection thường, một phép đo là một document BSON được lưu và index theo các index đã khai báo. Với time series collection, ứng dụng vẫn thấy và thao tác trên **các measurement document logic**, nhưng MongoDB có thể **tổ chức nhiều measurement liên quan vào một bucket nội bộ**.

```text
               ỨNG DỤNG
                  |
         insertOne / insertMany
                  |
                  v
       time series collection
         (giao diện logic)
                  |
          MongoDB tự bucket
             /     |     \
            v      v      v
         Bucket 1 Bucket 2 Bucket 3
            |      |      |
          nhiều measurement
          gần nhau theo thời gian
          và metadata tương ứng
                  |
          nén / quản lý nội bộ
                  |
                  v
            KẾT QUẢ QUERY
            ở dạng measurement
```

Điều này tạo cơ hội:

- **Giảm chi phí lưu trữ** nhờ nén những chuỗi giá trị cùng kiểu/có cấu trúc tương tự.
- **Đọc hiệu quả hơn** khi điều kiện truy vấn thu hẹp theo metadata và thời gian, giúp loại bỏ bucket không cần xét.
- **Giảm overhead của từng measurement** so với lưu tách biệt hoàn toàn trong một số workload.
- **Quản lý retention** của dữ liệu đo qua cấu hình time series collection.

Tuy nhiên, bucket có mặt trái: nếu truy vấn đụng một bucket, server có thể phải xử lý dữ liệu bên trong bucket; nếu metadata quá phân mảnh hoặc ingest quá thưa, bucket có thể chưa tận dụng tốt. Kết quả nén và tốc độ đọc/ghi **không được bảo đảm bằng một tỷ lệ cố định**.

### Collection logic và bucket nội bộ

Người dùng làm việc với:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
})
```

MongoDB quản lý cấu trúc bucket nội bộ tương ứng. Không nên đọc/ghi trực tiếp vào `system.buckets.sensorReadings` như một API nghiệp vụ. Dữ liệu bucket là **chi tiết triển khai**, có thể thay đổi theo phiên bản.

## 3. Ba thành phần cấu hình cốt lõi

Khi tạo time series collection, hai field và một tùy chọn đặc biệt quan trọng:

| Thành phần | Vai trò | Cách chọn |
| --- | --- | --- |
| **`timeField`** | Field chứa thời điểm của measurement, kiểu BSON Date | Chọn timestamp sự kiện/quan sát phù hợp; chuẩn hóa UTC và độ chính xác |
| **`metaField`** | Field chứa thông tin nhận diện chuỗi, tùy chọn | Dùng những thuộc tính ổn định theo nhiều measurement |
| **`granularity`** | Gợi ý cho MongoDB về độ hạt thời gian của measurement | `"seconds"`, `"minutes"`, `"hours"` theo nhịp và phân bố dữ liệu |

**`timeField` là bắt buộc** khi tạo time series collection. `metaField` không bắt buộc về mặt cú pháp, nhưng thường rất quan trọng khi có nhiều nguồn sensor/service cần gom và truy vấn riêng.

### 3.1. Chọn `timeField`: thời gian đo hay thời gian nhận?

Thiết bị có thể đo lúc 08:00:00 nhưng chỉ gửi lên gateway lúc 08:00:12.

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  receivedAt: ISODate("2026-11-14T08:00:12Z"),
  meta: { deviceId: "sensor-01" },
  value: 24.5
}
```

Nếu báo cáo cần biết **nhiệt độ tại thời điểm thiết bị đo**, thường chọn `measuredAt` làm `timeField`. Nếu bài toán là thời gian các message đến một điểm thu thập và thiết bị không có clock tin cậy, `receivedAt` có thể là lựa chọn hợp lý hơn.

Phải định nghĩa rõ:

- **Event time:** thời điểm phép đo hoặc sự kiện thực sự xảy ra.
- **Ingestion time:** thời điểm server/gateway nhận dữ liệu.
- **Processing time:** thời điểm ứng dụng xử lý event và ghi nó vào sink.

Không chọn ngẫu nhiên một field `createdAt` nếu nó không phản ánh ý nghĩa thời gian mà dashboard muốn hiển thị.

### 3.2. Chọn `metaField`: thông tin ổn định

Ví dụ tốt:

```javascript
meta: {
  tenantId: "tenant-01",
  siteId: "factory-a",
  deviceId: "sensor-01",
  metric: "temperature_c"
}
```

Các giá trị này thường giữ nguyên qua nhiều phép đo liên tiếp. Chúng giúp MongoDB nhóm và lọc theo những chuỗi tương ứng.

Ví dụ cần cân nhắc:

```javascript
meta: {
  deviceId: "sensor-01",
  batteryPct: 87,
  currentTemperature: 24.5,
  requestId: "req-unique-every-time"
}
```

Các thuộc tính như `batteryPct`, `currentTemperature` hoặc `requestId` thay đổi qua từng measurement. Đưa chúng vào metadata có thể làm xuất hiện quá nhiều nhóm metadata khác nhau, giảm khả năng gom measurement có ý nghĩa và làm tăng chi phí bucket.

Hướng phù hợp hơn:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    deviceId: "sensor-01",
    siteId: "factory-a",
    metric: "temperature_c"
  },
  value: 24.5,
  batteryPct: 87,
  requestId: "req-001"
}
```

Ở đây `batteryPct` và `requestId` là **measurement fields**, không phải metadata dùng để nhóm chuỗi.

**Không mặc định cứ ít field trong `meta` là tốt.** Nếu mọi query đều giới hạn tenant/site/device, đưa các dimension **ổn định** này vào metadata có thể rất hữu ích. Cần lựa chọn dựa trên **tần suất thay đổi của metadata, số lượng tổ hợp giá trị và pattern truy vấn**, không chỉ số field.

### 3.3. Chọn `granularity`

MongoDB cho phép các giá trị granularity thường gặp:

```text
seconds   -> luồng đo dày, tần suất theo giây hoặc dày hơn
minutes   -> giá trị thay đổi theo khoảng vài phút
hours     -> dữ liệu thưa hơn, quan sát theo giờ
```

Đây là **gợi ý tổ chức bucket**, không phải yêu cầu timestamp của mỗi record phải đúng ranh giới phút/giờ. Một measurement lúc 08:00:17 vẫn có thể được chèn vào collection có granularity `"minutes"`.

Granularity ảnh hưởng cách MongoDB quản lý khoảng thời gian và khả năng nén/đọc bucket. Granularity quá rộng đối với nhịp đo thực tế có thể tăng lượng dữ liệu không cần thiết được xử lý khi truy vấn khoảng ngắn; quá hẹp có thể khiến bucket chưa hiệu quả cho dữ liệu thưa.

Một số phiên bản MongoDB cho phép điều chỉnh giới hạn khoảng bucket bằng các tùy chọn như `bucketMaxSpanSeconds` và `bucketRoundingSeconds`. **Tập tùy chọn, ràng buộc và khả năng thay đổi sau tạo collection phụ thuộc phiên bản**; không kết hợp tùy tiện các option này với `granularity` nếu server không hỗ trợ.

## 4. Tạo collection cảm biến bằng `mongosh`

Trên database thực hành riêng:

```javascript
use mongo_time_series_lab

db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 2592000
})
```

Ý nghĩa:

- `sensorReadings` là **time series collection** logic.
- `measuredAt` chứa BSON Date của từng measurement.
- `meta` phân biệt những nhóm nguồn đo.
- `"seconds"` là granularity lựa chọn cho demo có số liệu theo chục giây.
- `expireAfterSeconds: 2592000` yêu cầu retention khoảng **30 ngày** đối với dữ liệu thô. Cách xóa thực tế theo bucket và tiến trình TTL không phải “đúng 30 ngày đến từng mili giây”.

**Lưu ý:** chỉ chạy ví dụ trên collection lab **chưa tồn tại**. Nếu collection đã có, `createCollection()` có thể báo lỗi. Không xóa collection thật rồi tạo lại chỉ để đổi loại collection hoặc TTL.

### Kiểm tra loại collection sau tạo

```javascript
db.getCollectionInfos({ name: "sensorReadings" })
```

Thông tin collection có thể hiển thị options chứa `timeseries`, `expireAfterSeconds` và các thông số liên quan. Trong môi trường thực, hãy đối chiếu với MongoDB server version và chính sách retention đang có.

### Không thể biến collection thường thành time series chỉ bằng đổi tên

Time series collection có cách lưu trữ và quy tắc thao tác riêng. Nếu dữ liệu đang ở một collection thường, cần **lập kế hoạch migration**: tạo time series collection mới, nạp dữ liệu đã chuẩn hóa, chuyển query/writer, đối soát và thực hiện cutover.

Việc đổi tên collection hoặc thêm index vào collection thường **không tự chuyển** nó thành time series collection.

## 5. Nạp bộ dữ liệu mẫu và đọc lại

Chèn tám phép đo nhiệt độ của hai sensor. Dùng timestamp UTC; các giá trị `value` cùng đơn vị Celsius.

```javascript
db.sensorReadings.insertMany([
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 24.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:20Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 25.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:40Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 26.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:00Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 27.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:20Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-01", metric: "temperature_c"
    },
    value: 28.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:10Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 19.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:00:30Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 20.0, quality: "ok"
  },
  {
    measuredAt: ISODate("2026-11-14T08:01:10Z"),
    meta: {
      tenantId: "tenant-01", siteId: "factory-a",
      deviceId: "sensor-02", metric: "temperature_c"
    },
    value: 21.0, quality: "ok"
  }
])
```

Một time series collection vẫn hỗ trợ những phép đọc logic quen thuộc:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
}).sort({ measuredAt: 1 })
```

Kết quả logic có năm measurement của `sensor-01` với giá trị `24, 25, 26, 27, 28`, theo thứ tự thời gian tăng dần. Người dùng không cần giải nén bucket thủ công.

**Không phụ thuộc thứ tự chèn để hiển thị thời gian đúng.** Với dữ liệu thực, các sự kiện có thể đến muộn hoặc đến sai thứ tự; mọi báo cáo cần thứ tự rõ nên sử dụng `sort({measuredAt: ...})` hoặc aggregate có trình tự phù hợp.

## 6. Truy vấn đúng mẫu: metadata + time range

Một truy vấn điển hình lấy nhiệt độ một thiết bị trong một khoảng nửa mở **[start, end)**:

```javascript
db.sensorReadings.find({
  "meta.tenantId": "tenant-01",
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:01:00Z")
  }
}, {
  _id: 0,
  measuredAt: 1,
  value: 1
}).sort({ measuredAt: 1 })
```

Với dữ liệu mẫu, kết quả gồm ba điểm:

```text
08:00:00Z   24.0
08:00:20Z   25.0
08:00:40Z   26.0
```

Khoảng **[start, end)** có ưu điểm: khi tiếp tục query phút kế tiếp bằng `$gte` start mới và `$lt` end mới, điểm nằm đúng ranh giới không bị đếm hai lần.

### Một số query shape cần đánh giá

| Câu hỏi | Predicate | Gợi ý |
| --- | --- | --- |
| Một sensor trong 10 phút | `meta.deviceId` + `measuredAt` range | Rất phù hợp với mô hình |
| Toàn bộ sensor trong một site | `meta.siteId` + time range | Có thể đọc nhiều chuỗi, đánh giá index và volume |
| Nhiệt độ vượt ngưỡng trong 24 giờ | time range + `value > threshold` | Có thể cần lọc nhiều measurement |
| Giá trị mới nhất của một sensor | `meta.deviceId` + sort time descending + limit | Index và cách tổ chức dữ liệu quan trọng |
| Tất cả lỗi trong một tháng | `quality:"bad"` + time range | Nếu lỗi hiếm, đánh giá index hoặc summary/alert riêng |
| Tính phần trăm request lỗi của một service | service identity + time window + aggregate | Hợp cho monitoring nếu schema metric đúng |

**Nếu biết tenant ID từ context xác thực, luôn giữ điều kiện tenant trong truy vấn.** Tối ưu hiệu năng không thay thế kiểm tra phân quyền giữa tenant.

## 7. Index: bucket optimization không có nghĩa bỏ mọi index

Time series collection có tổ chức bucket và khả năng tối ưu theo thời gian/metadata, nhưng những truy vấn thường xuyên vẫn có thể cần secondary index phù hợp.

Ví dụ một query hay dùng:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({ measuredAt: -1 }).limit(100)
```

Trên phiên bản MongoDB hỗ trợ index tương ứng cho time series, có thể xem xét:

```javascript
db.sensorReadings.createIndex(
  { "meta.deviceId": 1, measuredAt: -1 },
  { name: "idx_device_time_desc" }
)
```

Index giúp tìm theo thiết bị và đọc theo thời gian mong muốn, nhưng **không cam kết** mọi query đều được phục vụ hoàn toàn từ index. MongoDB vẫn có thể phải unpack bucket và đọc measurement.

### Không mặc nhiên tạo đủ mọi index

Index có chi phí:

- Dung lượng lưu trữ.
- CPU/I/O trong quá trình ingest.
- Bộ nhớ dành cho các cấu trúc được truy cập thường xuyên.
- Chi phí bảo trì index khi dữ liệu retention hết hạn.

Nếu ứng dụng chủ yếu truy vấn theo `tenantId + deviceId + time`, cần đánh giá một index phản ánh **toàn bộ prefix filter** thay vì tạo index riêng lẻ cho mỗi field. Với multi-tenant, cùng `deviceId` có thể xuất hiện trong nhiều tenant; index và filter phải theo đúng khóa định danh.

### Tùy phiên bản, hệ thống có thể có index mặc định

Các phiên bản MongoDB khác nhau có thể tạo hoặc hỗ trợ những index time-series khác nhau, bao gồm index liên quan đến `metaField` và `timeField`. **Hãy xem `getIndexes()` trên môi trường thực trước khi tạo trùng**:

```javascript
db.sensorReadings.getIndexes()
```

Hỗ trợ index cho measurement field, partial/TTL index, unique index và một số cấu trúc đặc biệt có **ràng buộc riêng theo phiên bản**. Không sao chép danh sách index của collection thường sang time series mà không kiểm tra tài liệu/version.

## 8. Đọc `explain()`: truy cập bucket và measurement

Chạy:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
}).explain("executionStats")
```

Một explain của time series có thể cho thấy những bước xử lý bucket/unpack. Tên stage cụ thể tùy phiên bản và query engine; có thể gặp các cấu trúc liên quan đến **unpack bucket**, filter theo metadata/time và các stage query plan.

Các câu hỏi quan trọng:

1. Server có thể **loại các bucket ngoài khoảng thời gian** cần đọc không?
2. Query có dùng index phù hợp theo `meta.deviceId` và `measuredAt` không?
3. Có phải unpack quá nhiều measurement không liên quan không?
4. Dữ liệu từ nhiều sensor có khiến query phải đọc nhiều buckets hơn dự kiến không?
5. Sort/aggregation có làm thêm công việc đáng kể sau unpack không?

**Không so sánh trực tiếp `totalDocsExamined` của explain time series với số measurement của collection thường mà không hiểu metric đang đếm gì.** Ở các kế hoạch khác nhau, một phần số liệu có thể liên quan đến **bucket document nội bộ** chứ không phải số measurement logic trả về. Nên xem toàn bộ plan, số measurement trả, số bucket xử lý và latency thực tế.

### Ví dụ đọc kết quả một cách đúng đắn

Giả sử explain cho hai query:

```text
Query A:
  deviceId = sensor-01
  time range = 2 phút
  ít bucket, ít measurement, sort nhỏ

Query B:
  mọi device
  time range = 30 ngày
  rất nhiều bucket và measurement
```

Việc A nhanh hơn B là điều có thể kỳ vọng vì khối lượng cần đọc khác biệt, không phải bằng chứng time series bị lỗi. Benchmark công bằng cần cùng **khối lượng dữ liệu logic**, cùng query shape và yêu cầu nghiệp vụ.

## 9. Aggregation theo cửa sổ thời gian

Một ưu điểm tự nhiên của time series là tính trung bình, cực tiểu, cực đại hoặc số mẫu theo khoảng thời gian.

### 9.1. Trung bình theo phút với `$dateTrunc`

```javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "tenant-01",
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:02:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        minute: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgValue: { $avg: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  { $sort: { "_id.deviceId": 1, "_id.minute": 1 } }
])
```

Với dữ liệu lab:

| Device | Phút UTC | Mẫu | Trung bình | Min | Max |
| --- | --- | ---: | ---: | ---: | ---: |
| sensor-01 | 08:00 | 3 | 25.0 | 24 | 26 |
| sensor-01 | 08:01 | 2 | 27.5 | 27 | 28 |
| sensor-02 | 08:00 | 2 | 19.5 | 19 | 20 |
| sensor-02 | 08:01 | 1 | 21.0 | 21 | 21 |

`$dateTrunc` tạo ranh giới thời gian; `$group` gom các measurement trong cùng device và cùng phút. Field `sampleCount` cho biết có bao nhiêu phép đo, quan trọng khi một sensor bị mất mẫu.

### 9.2. Đừng nhầm trung bình phép đo với trung bình có trọng số thời gian

Nếu sensor gửi mẫu lúc 08:00, 08:01 và 08:50, dùng `$avg` sẽ tính trung bình ba phép đo với trọng số bằng nhau. Nó **không tự tính nhiệt độ trung bình theo thời lượng** trong 50 phút.

Đối với phép đo có khoảng cách không đều:

- **Sample mean:** trung bình số học trên các mẫu đã nhận.
- **Time-weighted mean:** trung bình theo khoảng thời gian mỗi giá trị đại diện.
- **Integral/area under curve:** tích lũy theo thời gian, phù hợp với một số loại công suất/điện năng.

Muốn kết quả vật lý có ý nghĩa, phải chọn phép tổng hợp theo **loại cảm biến** và quy tắc lấy mẫu, không mặc định `$avg` là đúng cho mọi metric.

### 9.3. Phân biệt counter và gauge

Trong observability:

- **Gauge:** giá trị có thể tăng hoặc giảm, ví dụ CPU usage %, nhiệt độ, memory usage.
- **Counter:** số tích lũy thường tăng, ví dụ tổng request, tổng bytes; có thể reset khi tiến trình khởi động lại.
- **Histogram/summary:** cấu trúc phân bố độ trễ; không được cộng/trung bình như một scalar tùy ý.

Ví dụ: nếu lưu `http_requests_total` dạng counter, dùng `$avg` của các điểm counter để kết luận “requests/s” là **sai về ngữ nghĩa**. Muốn throughput phải xét **chênh lệch theo thời gian và counter reset**, có thể cần pipeline/window logic phù hợp hoặc lưu sẵn các delta/rate được xác định đúng.

## 10. Truy vấn gần đây và phát hiện khoảng trống

### Lấy 10 phép đo gần nhất

```javascript
db.sensorReadings.find({
  "meta.tenantId": "tenant-01",
  "meta.deviceId": "sensor-01"
}, {
  _id: 0, measuredAt: 1, value: 1
}).sort({ measuredAt: -1 }).limit(10)
```

Nếu hai event có cùng `measuredAt`, chỉ sort theo thời gian **không xác định thứ tự tuyệt đối giữa chúng**. Với ứng dụng cần thứ tự tổng, hãy có thêm sequence/measurement ID đáng tin cậy và sắp xếp theo quy tắc nghiệp vụ. Không tự dựa vào thứ tự vật lý của bucket.

### Sensor không gửi dữ liệu

Một báo cáo lấy `max(measuredAt)` cho từng device có thể cho biết lần đo cuối. Nhưng nó chỉ kiểm tra những device **đã từng xuất hiện trong collection và còn dữ liệu retention**.

Nếu cần phát hiện sensor chưa bao giờ gửi dữ liệu hoặc mất kết nối từ trước cửa sổ retention, cần danh mục thiết bị riêng:

```text
devices (collection thường):
  deviceId, expectedInterval, active, site

sensorReadings (time series):
  meta.deviceId, measuredAt, value

Monitoring service:
  so sánh expectedInterval của devices
  với lastSeen hoặc measurement mới nhất
```

Time series collection lưu lịch sử phép đo; **thiết bị không gửi gì** thì không tạo document để truy vấn lịch sử. Đây là lý do giữ **master data** của thiết bị trong collection thường và tách khỏi measurement data.

### Missing sample không phải giá trị zero

Giả sử sensor gửi ở 08:00 và 08:02 nhưng thiếu 08:01. Đừng tự nội suy rằng giá trị 08:01 bằng 0; có thể thiết bị bị lỗi, mất mạng hoặc ngừng gửi. Nếu dashboard cần đường liên tục, quy tắc fill/interpolation phải được định nghĩa rõ và phân biệt **giá trị thật**, **giá trị suy diễn** và **dữ liệu thiếu**.

MongoDB có một số toán tử/pipeline hỗ trợ chuỗi thời gian và cửa sổ theo phiên bản; việc lấp gap vẫn phải dựa trên yêu cầu nghiệp vụ.

## 11. Metadata cardinality và chi phí bucket

**Cardinality** của metadata là số tổ hợp giá trị khác nhau mà hệ thống cần quản lý. Với sensor:

```text
10.000 device
       x 1 metric
       = 10.000 chuỗi metadata

10.000 device
       x 20 metric
       = 200.000 chuỗi metadata
```

Đây chỉ là số tổ hợp logic. Số bucket đang mở/được tạo còn phụ thuộc nhịp đo, time ranges, phân bố và cách MongoDB tổ chức dữ liệu.

### Metadata ổn định nhưng nhiều giá trị

`meta.deviceId` có cardinality cao (mỗi device một giá trị) **không tự là sai**. Nó có thể cần thiết để tách các chuỗi và hỗ trợ query theo sensor. Vấn đề xuất hiện khi số chuỗi và nhịp tạo dữ liệu khiến:

- Nhiều bucket mở/đóng liên tục.
- Bộ nhớ quản lý bucket lớn.
- Dữ liệu mỗi bucket ít, nén kém.
- Index nhiều entries và metadata chiếm dung lượng.
- Truy vấn thường xuyên phải đọc nhiều series không liên quan.

### Metadata thay đổi mỗi event nguy hiểm hơn

Đưa `requestId` hoặc timestamp mới vào `meta` khiến mỗi measurement có gần như một metadata khác nhau. Khi đó cơ hội gom những measurement cùng chuỗi thành bucket hiệu quả giảm mạnh.

**Một quy tắc hữu ích:** metadata nên nhận diện **chuỗi đo**, còn những giá trị thay đổi **trong chuỗi** nên đặt ở measurement fields. Quy tắc này cần được cân đối với thực tế label của môi trường observability.

### Cẩn thận với nhãn quá linh hoạt trong monitoring

Ví dụ một record CPU metric:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    service: "checkout",
    host: "node-03",
    environment: "prod",
    metric: "cpu_percent"
  },
  value: 68.2
}
```

Khác với:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    service: "checkout",
    host: "node-03",
    metric: "cpu_percent",
    requestId: "random-unique-1234",
    pathWithUserId: "/users/983473/orders"
  },
  value: 68.2
}
```

`requestId` và đường dẫn chứa ID người dùng làm tổ hợp metadata gần như duy nhất. Bên cạnh chi phí, việc biến mọi attribute của trace/log thành metadata còn có thể tạo các vấn đề về privacy, tính nhất quán schema và kích thước lưu trữ. Chọn **low-entropy/stable dimensions** cho series identity, lưu thuộc tính per-event ở chỗ phù hợp.

## 12. Event time, độ trễ thiết bị và measurement đến muộn

Thiết bị có thể mất mạng hai giờ rồi gửi dữ liệu tồn đọng:

```text
08:00 thiết bị đo 24.5 °C
08:01 thiết bị đo 24.8 °C
      mất mạng
10:00 kết nối khôi phục
10:01 gateway gửi hai mẫu cũ
```

Nếu `timeField` là `measuredAt`, timestamp trong hai document vẫn là 08:00 và 08:01; ingestion time là 10:01. Truy vấn theo thời điểm quan sát sẽ sắp xếp đúng dữ liệu lịch sử.

### Điều gì có thể bị ảnh hưởng?

- **Bucket efficiency:** measurement đến muộn có thể được đưa vào bucket phù hợp nếu còn khả dụng hoặc gây thêm công việc bucket tùy trạng thái/lượng dữ liệu.
- **Dashboard gần thời gian thực:** giá trị mới nhất theo `measuredAt` không đồng nghĩa sự kiện được ingest gần nhất.
- **Rollup:** tổng hợp theo phút/giờ đã tính trước có thể cần cập nhật lại khi có late arrivals.
- **TTL:** dữ liệu quá cũ có thể gần hoặc vượt ngưỡng expiration ngay khi mới được ingest.
- **Deduplication:** thiết bị retry gửi cùng mẫu có thể tạo duplicate nếu ứng dụng không có cơ chế chống trùng.

Không tự đổi timestamp measurement sang `new Date()` chỉ để làm dữ liệu đến muộn “có vẻ mới”. Nếu cần cả hai loại thời gian, hãy lưu **`measuredAt` và `receivedAt`** với ý nghĩa rõ ràng.

### Đồng hồ cảm biến không đáng tin cậy

Một sensor có clock sai có thể gửi năm 1970 hoặc một ngày trong tương lai. Hậu quả là:

- Phép đo rơi vào bucket không như mong muốn.
- Query theo khoảng thời gian thực không thấy dữ liệu.
- Retention có thể loại bỏ dữ liệu cũ sớm hoặc giữ dữ liệu tương lai lâu bất thường.
- Dashboard tạo cảnh báo sai.

Nên có lớp validation/normalization ở ingest gateway: kiểm tra timestamp hợp lệ, độ lệch với server clock, khả năng sync NTP và cách gắn cờ dữ liệu nghi vấn. MongoDB time series collection không tự biết timestamp nào là “đúng theo thiết bị”.

## 13. Retention bằng `expireAfterSeconds`

Dữ liệu giám sát thường có chính sách nhiều tầng:

```text
Raw measurements:       giữ 7-30 ngày
Rollup 1 phút:          giữ 90 ngày
Rollup 1 giờ:           giữ 1-2 năm
Audit quan trọng:       theo chính sách riêng
```

Time series collection hỗ trợ cấu hình expiration, ví dụ:

```javascript
db.createCollection("cpuRaw", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
})
```

`604800` giây là 7 ngày. MongoDB sẽ áp dụng cơ chế TTL phù hợp với time series collection theo cấu hình và vòng đời dữ liệu.

### TTL không phải đồng hồ xóa chính xác từng document

MongoDB xử lý time series theo bucket. Một bucket có thể chứa nhiều measurement thuộc các thời điểm khác nhau; bucket chỉ đủ điều kiện loại bỏ sau khi các phép đo bên trong đã vượt ngưỡng expiration theo cơ chế server. Tiến trình TTL chạy **bất đồng bộ**, nên thời điểm document không còn nhìn thấy có thể trễ hơn mốc `timeField + expireAfterSeconds`.

Do đó:

- **Không dùng TTL như SLA xóa tức thì đến từng giây.**
- **Không dựa vào TTL làm cơ chế tuân thủ xóa dữ liệu cá nhân ngay lập tức** nếu quy định yêu cầu xóa chính xác/khẩn cấp.
- **Không đồng nhất thời gian đo với thời gian ingest** khi tính retention.
- **Không bỏ qua giới hạn xóa/sửa measurement riêng lẻ** của time series collection theo phiên bản.

Nếu cần xóa có điều kiện theo tenant, thiết bị hoặc yêu cầu pháp lý, phải kiểm tra những thao tác delete/update được hỗ trợ bởi phiên bản MongoDB, ảnh hưởng tới bucket và cách bảo vệ dữ liệu; có thể cần một kiến trúc lưu trữ khác.

### Đổi retention sau khi tạo

MongoDB có cơ chế thay đổi một số tùy chọn collection qua `collMod` trên các phiên bản hỗ trợ, trong đó có những cấu hình liên quan đến expiration/time series. **Không giả định có thể thay đổi mọi tham số hoặc giảm granularity tùy ý**; thao tác cụ thể và giới hạn phụ thuộc version.

Trước khi đổi retention của production, đánh giá lượng dữ liệu có thể trở thành expired ngay, I/O dọn dẹp, kế hoạch backup và tác động đến các rollup/report đang đọc dữ liệu thô.

## 14. Rollup và downsampling để giảm chi phí lâu dài

Nếu dashboard chủ yếu xem xu hướng 30 ngày theo giờ, việc mỗi lần phải đọc hàng triệu điểm đo thô có thể quá tốn kém. Một cách khác là lưu **bảng tổng hợp theo cửa sổ**.

```text
sensorReadings (raw time series)
      |
      | aggregate theo phút
      v
sensorMinuteRollup (summary collection)
      |
      | aggregate theo giờ
      v
sensorHourRollup
      |
      v
Dashboard dài hạn
```

Ví dụ tạo rollup theo phút từ dữ liệu đã ingest:

```javascript
db.sensorReadings.aggregate([
  {
    $match: {
      measuredAt: {
        $gte: ISODate("2026-11-14T08:00:00Z"),
        $lt: ISODate("2026-11-14T08:02:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$meta.deviceId",
        minute: {
          $dateTrunc: {
            date: "$measuredAt",
            unit: "minute",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      sumValue: { $sum: "$value" },
      minValue: { $min: "$value" },
      maxValue: { $max: "$value" }
    }
  },
  {
    $set: {
      avgValue: {
        $divide: ["$sumValue", "$sampleCount"]
      }
    }
  },
  {
    $merge: {
      into: "sensorMinuteRollup",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
```

Trong ví dụ, `sensorMinuteRollup` là **collection thường** được dùng làm nơi chứa summary. `$merge` thay thế summary có cùng `_id` khi chạy lại một cửa sổ đã tính.

**Lưu ý:** chạy lại rollup theo cửa sổ có thể cập nhật kết quả do late arrivals. Nhưng lệnh trên tính lại chỉ với dữ liệu khớp khoảng được chọn, vì vậy scheduler phải đảm bảo chạy lại **đầy đủ cửa sổ thời gian cần chỉnh**, không chỉ lấy một phần measurement mới đến rồi `replace` summary cũ.

### Tại sao giữ `sumValue` và `sampleCount`?

Nếu muốn tổng hợp dữ liệu phút thành giờ, không nên lấy trung bình đơn giản của các giá trị `avgValue` từng phút khi số mẫu mỗi phút khác nhau.

Ví dụ:

```text
Phút 08:00: 3 mẫu, avg = 25.0
Phút 08:01: 2 mẫu, avg = 27.5

Trung bình 5 mẫu = (3*25.0 + 2*27.5) / 5 = 26.0

Trung bình hai trung bình phút = (25.0 + 27.5)/2 = 26.25
                                     (khác 26.0)
```

Lưu `sumValue` và `sampleCount` cho phép tính **trung bình có trọng số theo số mẫu**. Nếu muốn trung bình theo thời lượng, vẫn phải có quy tắc trọng số thời gian riêng.

### Rollup không thể khôi phục chi tiết đã bỏ

Sau khi raw data hết TTL, minute/hour summaries có thể vẫn trả được thống kê tổng, nhưng không giúp dựng lại chính xác mọi measurement, mọi giá trị outlier hoặc trật tự các sự kiện. Vì vậy trước khi xóa dữ liệu thô, phải xác định mức độ chi tiết nào cần giữ cho báo cáo và điều tra sự cố.

## 15. Quy mô: ước lượng số measurement trước khi benchmark

Giả sử mỗi sensor tạo đúng một document mỗi phút:

```text
Measurements/ngày = số sensor × 60 phút/giờ × 24 giờ
                   = số sensor × 1.440
```

| Số sensor | Chu kỳ | Measurements/ngày | Trong 30 ngày |
| ---: | --- | ---: | ---: |
| 100 | 1 phút | 144.000 | 4.320.000 |
| 1.000 | 1 phút | 1.440.000 | 43.200.000 |
| 5.000 | 1 phút | 7.200.000 | 216.000.000 |
| 10.000 | 1 phút | 14.400.000 | 432.000.000 |

Nếu 10.000 sensor gửi **mỗi giây**, lượng measurement mỗi ngày sẽ tăng lên **864 triệu** thay vì 14,4 triệu. Đó là khác biệt lớn về ingest, index, retention, storage, network và vận hành.

Những phép tính trên là **số lượng logic**, chưa phải kích thước byte trên đĩa. Dung lượng thật phụ thuộc:

- Kích thước BSON của từng measurement.
- Metadata shape và cardinality.
- Nén/bucketing hiệu quả đến đâu.
- Secondary indexes.
- Phân bố dữ liệu theo thời gian, late arrivals và retention.
- Số bản sao replica set, oplog, backup và overhead của hệ thống.

Không lấy “số measurement × kích thước JSON nhìn thấy trên màn hình” làm dự báo chính xác dung lượng disk. BSON, compression, bucket và index đều có ảnh hưởng khác nhau.

## 16. Benchmark công bằng: time series so với collection thường

Một đánh giá kỹ thuật nên dùng **hai collection riêng** có cùng dữ liệu logic:

```text
sensorReadingsTs
  time series collection
  timeField=measuredAt, metaField=meta

sensorReadingsRegular
  collection thường
  cùng shape logical measurement
```

Nạp cùng tập dữ liệu đo vào cả hai, không chỉ vài document. Với workload thật, nên tái tạo:

- Nhịp ingest trung bình và burst.
- Số lượng series (tenant/site/device/metric combinations).
- Tỷ lệ event đến muộn và ngoài thứ tự.
- Tỷ lệ queries theo một sensor, một site hoặc tất cả sensors.
- Query time range 5 phút, 1 giờ, 1 ngày, 30 ngày.
- Truy vấn aggregate/rollup và yêu cầu latest value.
- Chính sách retention và secondary indexes tương ứng.

### Các chỉ số nên thu thập

| Nhóm | Metric | Câu hỏi |
| --- | --- | --- |
| Ingest | Documents/s, p95/p99 latency | Server có theo kịp tốc độ ghi và burst không? |
| Query | p50/p95/p99 latency | Dashboard/alert có đáp ứng SLA không? |
| Scan | Buckets/measurements examined, keys/docs examined theo plan | Có nhiều bucket bị unpack ngoài ý muốn không? |
| Storage | Data size, storage size, index size | Có tiết kiệm disk thực tế sau nén và index không? |
| Resource | CPU, RAM, I/O, cache pressure | Có lợi ở một tài nguyên nhưng quá tốn ở tài nguyên khác không? |
| Retention | Thời gian/chi phí dọn dữ liệu hết hạn | TTL có gây burst I/O hoặc cản trở query không? |
| Stability | Lỗi ingest, backlog, replication lag | Hệ thống có khỏe khi tải kéo dài không? |
| Operations | Khả năng xóa/sửa/rebuild/backup | Loại collection có hợp quy trình vận hành không? |

### Hai cách đo dễ dẫn đến kết luận sai

**Sai cách 1:** chỉ nạp vài trăm document rồi kết luận time series không nhanh hơn. Bộ dữ liệu nhỏ có thể chưa thể hiện rõ khác biệt compression/bucket và index.

**Sai cách 2:** tạo nhiều secondary indexes trên collection thường nhưng không tạo index tương ứng phục vụ query trên time series, sau đó so storage size rồi tuyên bố time series luôn tiết kiệm. Cần mô tả **toàn bộ workload và bộ index cần thiết để đạt cùng SLA**.

Không có tỷ lệ tiết kiệm dung lượng hay tốc độ “luôn nhanh gấp X lần” áp dụng cho mọi time series collection. Benchmark phải dựa trên dữ liệu đại diện.

## 17. Quan sát dung lượng và explain trong lab

Những lệnh đọc hữu ích:

```javascript
db.sensorReadings.stats()
```

```javascript
db.sensorReadings.getIndexes()
```

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:02:00Z")
  }
}).explain("executionStats")
```

Khi so dung lượng, cần xem những metric được server thực sự báo: `count`, logical size, storage/index size hoặc các chỉ số bucket/compression được cung cấp cho time series theo version. Không tự nhân một metric có tên giống nhau nếu ý nghĩa của nó khác giữa collection thường và time series.

### Query plan không đồng nghĩa latency toàn ứng dụng

Explain có thể chỉ ra index, bucket unpacking và số dữ liệu được xem xét. Nhưng latency endpoint còn bao gồm:

- Server selection và network.
- BSON decode/encode trong driver.
- Xử lý aggregation, serialize JSON và render dashboard.
- Cache của ứng dụng.
- Tải đồng thời và contention trên cluster.

Một query có plan tốt nhưng trả hàng triệu measurement vẫn có thể làm endpoint rất chậm vì lượng dữ liệu truyền qua mạng quá lớn. Cần limit/range/rollup phù hợp với màn hình đang hiển thị.

## 18. Sensor data và observability metrics: giống nhau và khác nhau

### 18.1. Điểm giống

Hai loại dữ liệu thường:

- Có **timestamp** bắt buộc.
- Được **append** theo nhịp tương đối đều hoặc theo sự kiện.
- Có **nguồn/đơn vị/nhãn tương đối ổn định**.
- Cần truy vấn theo time range và phân nhóm.
- Có chính sách retention/dowsampling.

Vì vậy, cả hai có thể hưởng lợi từ bucket/nén và truy vấn theo metadata/time.

### 18.2. Khác nhau về cấu trúc và ngữ nghĩa

| Yếu tố | Cảm biến vật lý | Monitoring/observability |
| --- | --- | --- |
| Identity | deviceId, siteId, sensorType | service, host, pod, metric name, environment |
| Đơn vị | °C, Pa, kWh, %RH | %, bytes, requests/s, ms |
| Mất mẫu | Thiết bị mất mạng/nguồn | Collector/exporter lỗi, deploy, churn |
| Timestamp | Clock của thiết bị/gateway | Clock của collector/application |
| Giá trị | Gauge, counter, trạng thái thiết bị | Gauge, counter, histogram, tracing spans |
| Metadata churn | Di chuyển thiết bị/site | Pod/container thay đổi liên tục |
| Truy vấn phổ biến | Một sensor/time range, báo cáo theo site | So sánh service, alert theo label, aggregate theo window |

### 18.3. Churn của host/pod có thể làm metadata không ổn định

Trong Kubernetes, `podUid` hoặc container instance thay đổi khi deploy. Nếu coi mỗi pod ID là một chuỗi mới, số lượng series có thể tăng nhanh qua thời gian. Có thể cần lưu cả **logical service identity** và **instance identity**, nhưng không đưa mọi label mới phát sinh vào metadata một cách tự động.

Một thiết kế thường tách:

- **Logical series:** service/metric/environment, hữu ích cho dashboard tổng.
- **Instance details:** host/pod, hữu ích khi debug, nhưng có churn cao.
- **Measurement value:** phần dữ liệu số được phân tích.

Quyết định lưu một hay nhiều series levels phụ thuộc nhu cầu query, alert và khả năng tổng hợp của hệ thống.

## 19. Thiết kế schema: một metric mỗi document hay nhiều metric?

### Cách A — một metric per measurement

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    host: "api-01",
    service: "checkout",
    metric: "cpu_percent"
  },
  value: 68.2
}
```

Ưu điểm:

- Mỗi document có một metric với đơn vị/ngữ nghĩa rõ.
- Truy vấn một metric đơn giản.
- Thêm metric mới mà không phải thêm một field mới vào schema cũ.

Hạn chế:

- Số measurement tăng theo **số metric trên mỗi nguồn**.
- `meta.metric` tăng số series.
- Cần join/pivot hoặc group nếu dashboard muốn nhiều metric ở cùng thời điểm.

### Cách B — nhiều metric trong một measurement

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00Z"),
  meta: {
    host: "api-01",
    service: "checkout"
  },
  cpuPercent: 68.2,
  memoryBytes: NumberLong("4294967296"),
  requestCount: NumberLong("123456"),
  errorCount: 7
}
```

Ưu điểm:

- Ít document hơn khi các metric **được lấy cùng thời điểm**.
- Một lần đọc có thể lấy nhiều chỉ số liên quan.
- Metadata identity có thể ít tổ hợp hơn.

Hạn chế:

- Nếu các metric lấy mẫu ở các nhịp khác nhau, có thể xuất hiện nhiều field thiếu/null hoặc timestamp không đại diện đồng nhất.
- Thêm/bớt metric làm schema linh hoạt hơn; cần rõ đơn vị và phân loại gauge/counter.
- Query từng metric hoặc aggregate chung có thể cần projection/index khác nhau.

Không có một dạng luôn tốt hơn. Hãy đo **mức đồng bộ thời gian của phép đo**, query phổ biến và tính ổn định schema. Với metrics không cùng nhịp, tách series có thể diễn đạt chính xác hơn.

## 20. Độ chính xác thời gian và kiểu dữ liệu

MongoDB BSON Date biểu diễn thời gian với độ phân giải mili giây. Khi cảm biến phát mẫu microsecond/nanosecond hoặc nhiều sample trong cùng mili giây, cần có **sequence hoặc timestamp phụ** nếu nghiệp vụ phải phân biệt thứ tự chính xác hơn.

```javascript
{
  measuredAt: ISODate("2026-11-14T08:00:00.123Z"),
  meta: { deviceId: "sensor-01" },
  sequence: NumberLong("9001"),
  value: 24.5
}
```

`sequence` là thông tin nghiệp vụ, không thay thế `timeField`. Nếu cần ordering, có thể sort theo `measuredAt` rồi `sequence`. Cách bảo đảm duy nhất/chống trùng cần được thiết kế riêng, không mặc nhiên coi time series collection cung cấp mọi unique constraint của collection thường.

### Dùng UTC để lưu, timezone để hiển thị/tổng hợp

Nên lưu timestamp theo một chuẩn thống nhất, thường là UTC:

```javascript
ISODate("2026-11-14T08:00:00Z")
```

Khi dashboard cần nhóm theo giờ địa phương:

```javascript
{
  $dateTrunc: {
    date: "$measuredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

Phân biệt **ngày theo UTC** với **ngày theo timezone nghiệp vụ**. Nếu một nhà máy hoạt động theo ngày địa phương, gom theo UTC rồi gắn nhãn ngày địa phương có thể sai ở ranh giới ngày.

### Missing/null và chất lượng dữ liệu

Không chuyển số đo lỗi thành 0 nếu 0 là một giá trị hợp lệ. Ví dụ sensor trả NaN, không có đọc hoặc timeout phải có representation rõ:

```javascript
{
  measuredAt: ISODate("2026-11-14T08:02:00Z"),
  meta: { deviceId: "sensor-01" },
  value: null,
  quality: "sensor_timeout"
}
```

Khi tính `$avg`, xử lý null và missing theo ngữ nghĩa MongoDB; nên thống kê **số sample hợp lệ và số sample lỗi** riêng, thay vì chỉ nhìn trung bình rồi cho rằng tất cả phép đo đều tốt.

## 21. Update, delete và upsert: hạn chế cần đánh giá trước

Một đặc điểm của dữ liệu chuỗi thời gian là **append-oriented**. MongoDB time series collection không phải bản sao 100% của collection thường về mọi thao tác update/delete, upsert, indexing hay transaction.

Ở các phiên bản MongoDB khác nhau, khả năng update/delete trên time series đã thay đổi và có những **ràng buộc đặc thù đối với metaField, số document và loại lệnh**. Vì vậy:

- **Không mặc định** mọi mẫu `updateOne()`, `replaceOne()`, `findOneAndUpdate()`, `upsert` hoặc update pipeline dùng trên collection thường đều chạy giống hệt trên time series.
- **Không thiết kế hệ thống cần sửa hàng triệu measurement mỗi ngày** mà chưa benchmark/kiểm tra rõ tính năng được hỗ trợ.
- **Không dùng direct writes vào bucket nội bộ** để vượt giới hạn API.
- Nếu dữ liệu đo cần chỉnh sửa do lỗi sensor, cần quy định cách version/correction hoặc thu hồi theo một đường ghi phù hợp với phiên bản.
- Nếu yêu cầu xóa ngay một số measurement riêng lẻ theo nghiệp vụ, hãy kiểm tra delete support và giới hạn retention; có thể cần một collection khác.

### Khi data correction thường xuyên

Hai chiến lược cần cân nhắc:

1. **Append correction event:** giữ measurement gốc, ghi sự kiện điều chỉnh có version và tính current effective value trong lớp tổng hợp. Phù hợp với hệ muốn giữ lịch sử sửa đổi nhưng query phức tạp hơn.
2. **Sửa/rebuild segment:** nếu server và workload hỗ trợ, sửa dữ liệu hoặc tái xây các cửa sổ bị ảnh hưởng. Cần kiểm tra giới hạn thao tác time series và impact tới rollup.

Nếu phần lớn nghiệp vụ là **tìm theo ID rồi sửa document liên tục**, collection thường có thể phù hợp hơn, ngay cả khi document chứa timestamp.

## 22. Duplicate measurements và idempotent ingestion

Một gateway gửi event `msg-001`, không nhận ACK vì timeout rồi retry:

```text
Sensor --> Gateway --> MongoDB insert measurement
              |
         ACK mất mạng
              |
              v
         Gateway gửi lại
```

Nếu không có cơ chế chống trùng, hệ thống có thể lưu hai measurement giống nhau. Aggregation `$avg`, `$sum` và `sampleCount` có thể sai.

Một measurement ID đáng tin cậy có thể dựa trên:

```text
(tenantId, deviceId, metric, deviceSequence)
```

hoặc một event ID do gateway tạo. Tuy nhiên, **không mặc định** time series collection hỗ trợ mọi loại **unique index** giống collection thường. Nên xem:

- Consumer có thể kiểm tra/dedupe ở một **ingestion ledger** hoặc queue bền vững không?
- Có thể tạo unique constraint ở một **collection thường** ghi dấu event ID trước/đồng thời với measurement không?
- Có thể chấp nhận duplicate rồi reconcile theo batch với chính sách rõ ràng không?
- Một lần retry cùng logical write có được driver hỗ trợ retryable write và session semantics phù hợp không?

Với hệ thống báo cáo tính tiền/điện năng, việc đếm duplicate có thể gây hậu quả tài chính; đánh giá idempotency là phần thiết yếu của quyết định lưu time series, không chỉ một tối ưu thêm vào sau.

## 23. Sharding và phân tán tải

Time series collection có thể được dùng trong những topology sharded cluster được hỗ trợ. Tuy nhiên, **chỉ tạo time series collection không tự động phân tán nó lên nhiều shard**, và những lựa chọn shard key có hạn chế riêng theo MongoDB version.

Những câu hỏi cần trả lời:

1. Phần lớn query có giới hạn `tenantId`, `deviceId` hoặc service không?
2. Lượng ghi của một sensor/tenant có thể tạo **hotspot** trên một shard?
3. Có một số tenant quá lớn so với các tenant khác?
4. Các phép đo của một nhóm metadata có cần được đặt gần nhau để query hiệu quả?
5. Có yêu cầu query global across sensors khiến nhiều shard phải xử lý?
6. Shard key dự kiến có thuộc các field/biểu thức **được time series hỗ trợ trên phiên bản đó**?

Một thiết kế có thể ưu tiên **định tuyến theo metadata** để workload truy vấn một thiết bị không phải scatter-gather nhiều shard. Nhưng cũng phải cân đối phân phối ghi và cân bằng dữ liệu.

### Đừng nhầm time series bucket với shard chunk

- **Bucket**: cấu trúc lưu nhiều measurement của time series.
- **Shard-key range/chunk**: đơn vị phân phối dữ liệu giữa các shard.

Hai khái niệm này phục vụ mục tiêu khác nhau. Bucketing giúp nén/đọc chuỗi thời gian; sharding giúp phân chia dữ liệu và tải trên nhiều máy chủ. Không nên suy rằng “có nhiều bucket thì tự có nhiều shard”.

### Shard key và version

Hỗ trợ shard key time series đã phát triển qua các bản MongoDB. Đặc biệt, các ràng buộc đối với trường time/metadata, hashed key và resharding có thể khác theo phiên bản. Trước khi thiết kế cluster production, cần đối chiếu chính xác **time series sharding restrictions** của server đang dùng, thay vì sao chép một mẫu sharding của collection thường.

## 24. Mã Java MongoDB Sync Driver

Trong Java, ứng dụng có thể tạo time series collection bằng `CreateCollectionOptions` và `TimeSeriesOptions`, sau đó chèn và truy vấn document bình thường.

Ví dụ minh họa với Java và MongoDB Java Sync Driver tương thích:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;

public class SensorTimeSeriesDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_time_series_lab_java");

            TimeSeriesOptions tsOptions =
                new TimeSeriesOptions("measuredAt")
                    .metaField("meta")
                    .granularity(TimeSeriesGranularity.SECONDS);

            CreateCollectionOptions createOptions =
                new CreateCollectionOptions()
                    .timeSeriesOptions(tsOptions);

            // Chạy trên database lab trống, chỉ tạo một lần.
            db.createCollection("sensorReadings", createOptions);

            MongoCollection<Document> readings =
                db.getCollection("sensorReadings");

            Document metadata = new Document(
                "tenantId", "tenant-01")
                .append("siteId", "factory-a")
                .append("deviceId", "sensor-01")
                .append("metric", "temperature_c");

            readings.insertOne(
                new Document("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T08:00:00Z")))
                    .append("meta", metadata)
                    .append("value", 24.5)
                    .append("quality", "ok")
            );

            Bson filter = Filters.and(
                Filters.eq("meta.tenantId", "tenant-01"),
                Filters.eq("meta.deviceId", "sensor-01"),
                Filters.gte("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T08:00:00Z"))),
                Filters.lt("measuredAt",
                    Date.from(Instant.parse(
                        "2026-11-14T09:00:00Z")))
            );

            for (Document measurement : readings
                    .find(filter)
                    .sort(Sorts.descending("measuredAt"))) {
                System.out.println(measurement.toJson());
            }
        }
    }
}
```

Đoạn code không hard-code mật khẩu: sử dụng biến môi trường `MONGODB_URI`. Phần `createCollection` cần quyền tạo collection, và sẽ báo lỗi khi collection cùng tên đã tồn tại. Trong service production, việc tạo schema/index/retention thường nên thực hiện bằng migration/initialization có kiểm soát, không làm ở mọi lần app startup.

### Nếu muốn retention trong Java

Tùy phiên bản MongoDB Java Sync Driver, `CreateCollectionOptions` có API tương ứng để khai báo expiration cho time series collection. Nếu API/driver đang dùng không hỗ trợ option mong muốn, có thể tạo collection qua database command phù hợp. **Đừng đoán method name theo phiên bản khác**; kiểm tra driver API đang được build.

### Java Date và dữ liệu sensor

`java.util.Date` dùng trong BSON Date và chứa thời điểm với độ phân giải mili giây. `Instant.parse(...Z)` giúp diễn đạt rõ UTC. Nếu nguồn đo có độ chính xác cao hơn mili giây, phải lưu sequence/precision bổ sung theo yêu cầu.

## 25. So sánh time series với một mô hình collection thường

Giả sử hệ thống cần lưu nhiệt độ 5.000 thiết bị trong 30 ngày, query chủ yếu lấy đồ thị 24 giờ và tổng hợp theo phút.

### Mô hình A — collection thường

```javascript
db.sensorReadingsRegular.insertOne({
  measuredAt: new Date(),
  deviceId: "sensor-01",
  value: 24.5
})
```

Có thể tạo:

```javascript
db.sensorReadingsRegular.createIndex({
  deviceId: 1,
  measuredAt: -1
})
```

Ưu điểm: CRUD/index behavior quen thuộc, có thể phù hợp những tính năng chưa hỗ trợ hoặc bị hạn chế ở time series. Hạn chế: không có cách bucketing/time-series-specific compression giống loại collection chuyên dụng, nên có thể chiếm nhiều dung lượng hoặc overhead trên workload điển hình.

### Mô hình B — time series collection

```javascript
db.createCollection("sensorReadingsTs", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  }
})
```

Ưu điểm: mô hình dữ liệu và cách lưu trữ được thiết kế cho các measurement theo thời gian. Hạn chế: cần lựa chọn metadata/granularity, hiểu bucket/retention và chấp nhận giới hạn thao tác theo server version.

### Quyết định dựa trên workload

| Tiêu chí | Collection thường | Time series collection |
| --- | --- | --- |
| Append measurement liên tục | Có thể đáp ứng | **Ứng viên nổi bật** |
| Nhiều measurement cùng metadata gần nhau theo thời gian | Không có chuyên biệt bucketing tương tự | Có cơ hội nén/tối ưu đáng kể |
| Query metadata + time range | Hỗ trợ bằng index | Hỗ trợ, có tối ưu time-series riêng |
| Update/delete một measurement thường xuyên | Mô hình CRUD thông thường | Có ràng buộc tùy version, cần xem xét |
| Index/unique constraints đa dạng | Linh hoạt hơn trong nhiều trường hợp | Có giới hạn đặc thù |
| Retention theo thời gian | Có thể dùng TTL index/phương án khác | Cấu hình time series expiration |
| Cần giữ từng sự kiện audit vĩnh viễn | Có thể thiết kế riêng | Oplog/TTL không thay event ledger, cần xem yêu cầu |
| Dữ liệu rất thưa, metadata biến đổi mỗi lần | Vẫn lưu được document | Có thể nén/bucket kém |
| Streaming query cho nhiều metric | Có thể | Có thể, cần cấu trúc chuỗi hợp lý |

**Không kết luận time series luôn tốt hơn.** Nếu ứng dụng cần thao tác theo khóa duy nhất, cập nhật field thường xuyên hoặc ràng buộc schema/index không tương thích, sự đơn giản của collection thường có thể là một lợi thế lớn.

## 26. Những điều cần kiểm chứng theo phiên bản MongoDB

Time series là mảng tính năng có nhiều cải tiến qua các phiên bản MongoDB. Khi triển khai thật, hãy tra đúng tài liệu của server và driver về:

1. Các tùy chọn `timeseries` khi tạo collection và thay đổi bằng `collMod`.
2. Khả năng tạo secondary indexes, loại index được hỗ trợ và index mặc định.
3. Quy tắc update/delete/upsert và các thao tác như `replaceOne`.
4. Khả năng hỗ trợ transaction, change streams, schema validation hoặc những operation đặc biệt.
5. Sharding: key hợp lệ, tối ưu routing, di chuyển dữ liệu và giới hạn của collection.
6. TTL/partial TTL và cách các bucket đủ điều kiện hết hạn.
7. Các operator aggregation/time-series-specific và query engine.

**Không được lấy ví dụ hoạt động trên một bản MongoDB rồi hứa nó hoạt động tương tự trên mọi bản**. Nếu tính năng cần thiết cho nghiệp vụ không được hỗ trợ ở môi trường mục tiêu, đây là lý do để chọn mô hình khác hoặc nâng cấp có kế hoạch.

### Dữ liệu cảm biến có cần Change Stream?

Một kiến trúc monitoring có thể muốn vừa lưu measurement vừa gửi event realtime. **Không mặc định** mọi khả năng Change Stream của collection thường áp dụng y hệt cho time series collection ở server version đang dùng. Nếu cần CDC để kích hoạt cảnh báo hoặc cập nhật dịch vụ khác, phải xác nhận **Change Stream support/restrictions** của time series. Trong nhiều hệ thống, phát event từ **ingestion pipeline/queue** riêng có thể đơn giản và đáng tin cậy hơn việc phụ thuộc hoàn toàn vào CDC của nơi lưu measurement.

## 27. Một kiến trúc tham khảo cho IoT và observability

```text
              Thiết bị / Agent / Exporter
                         |
                         v
                  Ingestion Gateway
                 /       |       \
          validate   dedupe     normalize UTC
                         |
                         v
                Durable Queue (nếu cần)
                         |
                         v
               MongoDB Time Series
                    raw samples
                         |
              +----------+----------+
              |                     |
              v                     v
         Alert Service         Rollup Worker
         (ngưỡng/tốc độ)       (phút/giờ/ngày)
              |                     |
              v                     v
           Alert Log           Summary Collections
              |                     |
              +----------+----------+
                         |
                         v
                    Dashboard API
```

Đây là một sơ đồ thiết kế khả dĩ, **không phải quy định phải có queue**. Với hệ nhỏ và lưu lượng thấp, gateway có thể ghi thẳng vào MongoDB. Khi lưu lượng cao hoặc sink có thể chậm, durable queue giúp tách tốc độ nhận event khỏi tốc độ ghi/aggregate.

Các thành phần nên tách:

- **Device/service catalog**: metadata hiện tại, cấu hình sensor, trạng thái hoạt động (collection thường).
- **Raw measurements**: measurement theo thời gian (ứng viên time series).
- **Rollups**: thống kê đã tổng hợp và định danh thời gian (collection summary).
- **Alerts/events**: lịch sử cảnh báo có logic nghiệp vụ và lifecycle riêng.
- **Ingestion dedupe ledger**: ghi dấu event ID khi yêu cầu chống trùng mạnh.

Sự phân tách này giúp không ép mọi yêu cầu về dữ liệu có timestamp vào cùng một time series collection.

## 28. Quy trình đánh giá trước khi chọn time series collection

Một dự án nên thực hiện theo các bước sau:

1. **Phân loại dữ liệu:** measurement thực sự hay bảng trạng thái/event log thông thường?
2. **Xác định semantics của timestamp:** event time, ingest time, timezone, precision và late arrivals.
3. **Thiết kế metadata:** những dimension nào ổn định? Có bao nhiêu series? Có label gây cardinality nổ không?
4. **Chọn granularity thử nghiệm:** seconds/minutes/hours dựa trên nhịp đo và độ rộng cửa sổ query.
5. **Định nghĩa retention:** raw giữ bao lâu, rollup giữ bao lâu, có chính sách xóa đặc biệt không?
6. **Lập danh sách query shape:** device/site/time range, global analytics, latest point, alert thresholds.
7. **Kiểm tra giới hạn tính năng/version:** indexes, update/delete, transaction, CDC, sharding và options collection.
8. **Tạo prototype:** time series và collection thường có cùng measurement payload.
9. **Chạy benchmark workload đại diện:** ingest burst, query p95/p99, compression, I/O, memory, TTL cleanup.
10. **Đánh giá vận hành:** backup/restore, rollup/rebuild, migration, quan sát lag, dedupe và rollback plan.
11. **Chốt quyết định có điều kiện:** ghi rõ tính năng nào được hưởng lợi, những giới hạn nào được chấp nhận và ngưỡng scale cần xem lại.

### Mẫu ghi quyết định kỹ thuật

```text
Use case: temperature metrics, 5.000 sensors, 1 sample/min
Data type: append-only measurement, measuredAt = UTC Date
Series identity: tenantId + siteId + deviceId + metric
Query pattern: one device / 24h; site / 1h; hourly rollup
Raw retention: 30 days
Rollup retention: 1 year
Late arrival: up to 2 hours
Duplicate handling: ingestion event ID
Version constraints: checked against target MongoDB release
Benchmark: ingest p95, query p95, storage, CPU, bucket behavior
Decision: use or reject time series based on measured results
```

Đây là mẫu **đầu vào để đánh giá**, không phải báo cáo rằng hệ thống đã đạt các chỉ số hay kết quả benchmark.

## 29. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Document có `createdAt` thì nên dùng time series” | Có thể là dữ liệu CRUD thông thường | Chọn theo append workload và query time range |
| “Time series luôn nén tốt hơn X lần” | Phụ thuộc metadata, nhịp, schema, bucket | Benchmark trên dữ liệu thật |
| “`metaField` càng nhiều thuộc tính càng tốt” | Metadata thay đổi liên tục gây nhiều series/bucket | Giữ identity ổn định và query-relevant |
| “`granularity:"hours"` làm timestamp chính xác đến giờ” | Granularity là gợi ý bucketing | Timestamp vẫn là BSON Date của measurement |
| “Đã có bucket thì không cần index” | Query theo source/time vẫn có thể cần index | Xem getIndexes/explain và workload |
| “Index và document examined có ý nghĩa y hệt collection thường” | Plan có bước bucket/unpack | Đọc explain theo cấu trúc time series |
| “`expireAfterSeconds` xóa từng sample đúng thời điểm” | Bucket TTL và TTL monitor bất đồng bộ | Retention xấp xỉ, không đồng hồ xóa chính xác |
| “Giá trị đến muộn phải đổi timestamp sang giờ ingest” | Làm sai lịch sử phép đo | Lưu event time, thêm receivedAt nếu cần |
| “Hai measurement cùng timestamp chắc chắn là duplicate” | Có thể nhiều sample trong mili giây | Cần sequence/event ID đáng tin cậy |
| “Time series tự chống ghi trùng do retry” | Không tự có exactly-once ingestion | Dedupe ở ingest/ledger theo yêu cầu |
| “`$avg` luôn là trung bình thời gian” | Trung bình theo số mẫu, không theo duration | Cần time weighting nếu bài toán đòi hỏi |
| “Counter dùng trung bình trực tiếp để tính rate” | Counter là giá trị tích lũy, có reset | Tính delta/rate đúng ngữ nghĩa |
| “Rollup theo giờ bằng trung bình các avg phút luôn đúng” | Mỗi phút có thể có số mẫu khác nhau | Dùng sum và count để tổng hợp có trọng số |
| “Mọi data có timestamp nên lưu trong cùng một collection” | CRUD, audit, telemetry có yêu cầu khác nhau | Tách measurement, catalog, alert, ledger |
| “Update/delete giống hệt collection thường” | Có giới hạn theo phiên bản time series | Kiểm tra thao tác được hỗ trợ |
| “Tạo time series là tự sharding” | Bucketing khác sharding | Thiết kế shard topology/key riêng |
| “Lấy một sensor mới nhất không cần sort” | Thứ tự chèn/physical không phải thứ tự nghiệp vụ | Query theo measuredAt và tie-break |
| “Không có sample thì sensor chắc không tồn tại” | Sensor có thể mất mạng hoặc hết dữ liệu TTL | Có device catalog riêng |
| “Collection thường chậm hơn vì không nén” | Index/workload khác có thể đảo kết quả | Đo cả ingest/query/storage/operations |

## 30. Bài tập thực hành và đáp án

### Bài 1. Chọn mô hình cho hai loại dữ liệu

Hệ thống có (A) nhiệt độ mỗi phút cho 1.000 sensor và (B) một record tình trạng pin hiện tại được cập nhật mỗi giây cho từng sensor. Nên đánh giá time series cho phần nào?

**Đáp án:** (A) là ứng viên rõ ràng vì có nhiều measurement append theo thời gian. (B) thiên về current-state document được update liên tục, thường phù hợp collection thường. Có thể vừa lưu lịch sử pin vào time series, vừa giữ trạng thái pin mới nhất trong collection thường nếu cần.

### Bài 2. Chọn `timeField`

Sensor đo lúc 08:00 nhưng gửi lúc 08:07. Dashboard cần báo cáo “nhiệt độ lúc 08:00”. Field nào nên làm timeField?

**Đáp án:** `measuredAt` (08:00) thường phù hợp; lưu thêm `receivedAt` (08:07) để theo dõi độ trễ. Không đổi thời gian đo thành 08:07 vì mất mạng.

### Bài 3. Metadata nào nên chuyển ra measurement?

```javascript
meta: {
  siteId: "factory-a",
  deviceId: "sensor-01",
  metric: "temperature_c",
  batteryPct: 87,
  requestId: "req-xyz"
}
```

**Đáp án:** `batteryPct` và `requestId` thường thay đổi theo event, nên đưa vào measurement fields. `siteId`, `deviceId` và `metric` là ứng viên metadata tương đối ổn định nếu chúng định danh chuỗi đúng nghiệp vụ.

### Bài 4. Tính số measurement

5.000 sensor phát một sample mỗi phút trong 30 ngày, không bị thiếu mẫu. Có bao nhiêu measurement logic?

**Đáp án:** `5.000 × 60 × 24 × 30 = 216.000.000` measurement. Con số này **không phải** dung lượng disk; còn nén, bucket, index và metadata.

### Bài 5. Query 60 giây không chồng biên

Viết filter lấy sample `sensor-01` từ 08:00:00Z đến trước 08:01:00Z.

**Đáp án:**

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01",
  measuredAt: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T08:01:00Z")
  }
})
```

Dùng `$lt` cho end để measurement đúng 08:01:00Z thuộc cửa sổ tiếp theo, tránh trùng biên.

### Bài 6. Tính trung bình theo phút

Sensor-01 có ba giá trị 24, 25, 26 trong phút 08:00 và hai giá trị 27, 28 trong phút 08:01. Trung bình mỗi phút?

**Đáp án:** Phút 08:00 = `25.0` (3 mẫu); phút 08:01 = `27.5` (2 mẫu). Trung bình của cả năm mẫu = `(24+25+26+27+28)/5 = 26.0`.

### Bài 7. Trung bình các trung bình

Vì sao `(25.0 + 27.5)/2 = 26.25` không phải trung bình của toàn bộ năm sample ở bài 6?

**Đáp án:** Hai phút có số mẫu khác nhau (3 và 2), nên phải dùng trung bình có trọng số theo số sample. Giá trị đúng là `(3×25 + 2×27.5)/5 = 26.0`.

### Bài 8. Tính năng nào cần kiểm tra trước khi chọn time series?

Một ứng dụng cần `replaceOne` một phép đo bất kỳ hàng nghìn lần/ngày và yêu cầu unique index phức tạp. Có thể dựa vào việc MongoDB hỗ trợ CRUD để coi time series tương thích tuyệt đối không?

**Đáp án:** Không. Update/delete/replace và unique indexes có giới hạn riêng theo version. Đây là dấu hiệu phải kiểm tra tài liệu chính thức của bản MongoDB mục tiêu và benchmark, hoặc cân nhắc collection thường.

### Bài 9. TTL có xóa đúng 12:00:00 không?

Một measurement vượt ngưỡng retention vào đúng 12:00:00. Có thể bảo đảm nó biến mất khỏi mọi query ngay lúc đó không?

**Đáp án:** Không. Time series TTL áp dụng theo bucket và tiến trình TTL bất đồng bộ; các measurement có thể còn nhìn thấy trong một khoảng thời gian sau mốc expiration.

### Bài 10. Query theo một device nhưng dashboard chậm

Query:

```javascript
db.sensorReadings.find({
  "meta.deviceId": "sensor-01"
})
```

trả về nhiều triệu sample của một năm. Vì sao có thể chậm dù metadata được thiết kế tốt?

**Đáp án:** Không có time range/limit nên query phải đọc và trả quá nhiều dữ liệu. Cần giới hạn khoảng thời gian, projection, index hợp lý và rollup khi dashboard chỉ cần xu hướng.

### Bài 11. Counter trong monitoring

Metrics `requests_total` lưu các giá trị 1.000, 1.200, 1.400 tại ba phút liên tiếp. Có thể lấy `$avg = 1.200` làm số request mỗi phút không?

**Đáp án:** Không. Đây là counter tích lũy; nếu không reset, chênh lệch giữa các mẫu là 200 request mỗi phút. Cần xử lý delta và counter reset, không dùng trung bình scalar trực tiếp.

### Bài 12. Vì sao sensor catalog tách riêng?

Dashboard cần cảnh báo sensor không có mẫu mới trong 30 phút, kể cả sensor chưa từng gửi một measurement. Chỉ query `sensorReadings` có đủ không?

**Đáp án:** Không. Sensor chưa gửi gì không có measurement. Phải có danh sách device được kỳ vọng hoạt động, ví dụ collection thường `devices`, rồi so thời gian lastSeen với nhịp gửi dự kiến.

### Bài 13. Chọn cơ chế chống duplicate

Gateway retry cùng event khi không nhận ACK; báo cáo doanh thu điện năng tính tổng các sample. Có thể chấp nhận duplicate vì dùng time series compression không?

**Đáp án:** Không. Compression không chống duplicate. Cần stable event ID/sequence và cơ chế dedupe đáng tin cậy, hoặc reconciliation phù hợp với mức chính xác của báo cáo.

### Bài 14. Khi nào collection thường vẫn hợp lý?

Một ứng dụng quản lý lịch bảo trì: mỗi máy chỉ có một document gần nhất, thường xuyên thay ngày bảo trì, người phụ trách, trạng thái, và cần unique constraints theo mã tài sản.

**Đáp án:** Đây là current-state CRUD hơn là chuỗi measurement append. Collection thường thường đơn giản và phù hợp hơn; nếu cần lịch sử sự kiện bảo trì, có thể lưu một collection event riêng.

## 31. Kết luận

**Time series collection** là lựa chọn đáng đánh giá khi hệ thống có **nhiều measurement append theo thời gian**, metadata nguồn đo tương đối ổn định, truy vấn chủ yếu theo **metadata + time range** và có nhu cầu **aggregation/retention/rollup**. Tổ chức dữ liệu theo bucket và cơ chế nén của MongoDB có thể đem lại lợi ích về lưu trữ và truy vấn, nhưng hiệu quả phụ thuộc nhịp dữ liệu, cardinality, late arrivals, index và query shape.

Ba quyết định ảnh hưởng lớn nhất là:

1. **`timeField` đúng ngữ nghĩa:** dùng thời gian phép đo hay thời gian ingest, chuẩn hóa timezone và loại timestamp không hợp lệ.
2. **`metaField` ổn định:** nhận diện series bằng tenant/site/device/metric phù hợp, tránh nhãn thay đổi từng event làm phân mảnh bucket.
3. **`granularity` và retention hợp workload:** chọn theo nhịp quan sát, đặt chính sách TTL rõ ràng và tính trước rollup khi cần lưu lịch sử dài hạn.

Để chọn đúng cho **dữ liệu cảm biến** và **quan sát hệ thống**, còn phải kiểm tra **cardinality, độ bền ingest, chống trùng, dữ liệu đến muộn, các phép tính gauge/counter, update/delete restrictions, version support, sharding và khả năng phục hồi**. Không có phép so sánh đúng chỉ dựa trên việc tên collection có chữ “time series”: hãy benchmark cùng dữ liệu logic, cùng query, cùng yêu cầu SLA, rồi chọn mô hình đem lại lợi ích rõ ràng với chi phí vận hành chấp nhận được.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB Manual — Time Series Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/)
- [MongoDB Manual — Time Series Expiration](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
