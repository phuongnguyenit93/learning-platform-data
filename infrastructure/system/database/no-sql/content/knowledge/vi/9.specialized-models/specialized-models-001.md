# Chuỗi thời gian: thời điểm, nhãn và truy vấn theo cửa sổ

Dữ liệu **chuỗi thời gian (time series)** là các phép đo hoặc sự kiện được ghi nhận theo thời gian: nhiệt độ từ cảm biến, mức sử dụng CPU, số lượt gọi API, giá giao dịch hay số lượng đơn phát sinh mỗi phút. Điểm khác biệt so với một document thông thường không chỉ là có trường thời gian. Ứng dụng thường cần **đọc một khoảng thời gian**, **lọc theo nhóm nguồn phát sinh**, **tính giá trị tổng hợp trên từng cửa sổ** và **theo dõi sự thay đổi của một đại lượng**.

Ví dụ, một câu hỏi nghiệp vụ có thể là:

> Trong 15 phút vừa qua, nhiệt độ trung bình của cảm biến **sensor-01** ở nhà máy **factory-a** thay đổi thế nào theo từng khoảng 5 phút? Nếu một khoảng không có dữ liệu thì cần hiển thị ra sao?

Để trả lời đúng, ta phải biết thời điểm nào là thời điểm đo, nhãn nào định danh chuỗi, giá trị nào là phép đo, cửa sổ bắt đầu và kết thúc ở đâu, và hệ thống xử lý sự kiện đến muộn thế nào. Nếu chỉ lưu mọi bản ghi vào một collection và lấy **AVG** trên toàn bộ tập, ta sẽ làm mất diễn biến theo thời gian mà người dùng muốn quan sát.

Bài học dùng ví dụ cảm biến và **MongoDB time-series collection** để minh họa mô hình NoSQL có khả năng lưu chuỗi thời gian. Bài cũng đối chiếu với **InfluxDB line protocol** và **Prometheus/PromQL** để làm rõ khái niệm measurement, tag/label, field và truy vấn theo khoảng. Mỗi sản phẩm có API và ngữ nghĩa riêng; không thể lấy cú pháp của hệ này áp dụng nguyên sang hệ khác.

## 1. Một điểm dữ liệu chuỗi thời gian gồm những gì?

Ở mức khái niệm, một phép đo có thể biểu diễn bằng:

\[
\text{Point}=(\text{timestamp},\ \text{series identity},\ \text{value/fields})
\]

Ví dụ:

~~~text
Thời điểm đo:      2026-11-14T09:03:10Z
Tổ chức:           factory-a
Thiết bị:          sensor-01
Đại lượng:         temperature
Giá trị:           23.0
Đơn vị:            °C
~~~

Ba phần quan trọng nhất:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Timestamp** | Thời điểm phép đo/sự kiện có ý nghĩa trong nghiệp vụ | 2026-11-14T09:03:10Z |
| **Tag/label/metadata** | Thuộc tính giúp nhận diện, chọn và nhóm các chuỗi | factory-a, sensor-01, temperature |
| **Field/value** | Đại lượng được đo hoặc dữ liệu thay đổi theo từng điểm | temperatureC = 23.0 |

Khái niệm **series** thường là tập những điểm có cùng định danh đo/nhóm nhãn và thay đổi theo thời gian. Từng hệ có quy tắc khác nhau về trường nào tham gia vào danh tính series. Không nên xem mọi field đều là nhãn hoặc mọi nhãn đều là giá trị đo.

Ví dụ, hai cảm biến có thể cùng đo nhiệt độ:

~~~text
Series A: tenant=factory-a, device=sensor-01, metric=temperature
  09:00:10 -> 20.0 °C
  09:01:10 -> 21.0 °C
  09:03:10 -> 23.0 °C

Series B: tenant=factory-a, device=sensor-02, metric=temperature
  09:02:10 -> 30.0 °C
  09:06:10 -> 32.0 °C
~~~

Các điểm của hai cảm biến thuộc hai chuỗi khác nhau. Nếu không lọc **device** hoặc không nhóm đúng theo chuỗi, kết quả trung bình có thể trộn dữ liệu của hai cảm biến và không còn phản ánh câu hỏi ban đầu.

## 2. Ba loại thời gian thường cùng tồn tại

**Thời điểm đo (event time / observed time)** là lúc thiết bị thật sự ghi nhận nhiệt độ. **Thời điểm tiếp nhận (ingestion time)** là lúc server nhận được dữ liệu. **Thời điểm xử lý (processing time)** là lúc một job hoặc query tiêu thụ bản ghi.

~~~mermaid
flowchart LR
    A["Thiết bị đo lúc 09:03:10"] -->|"Mất mạng 2 phút"| B["Server nhận lúc 09:05:10"]
    B -->|"Queue xử lý 20 giây"| C["Job xử lý lúc 09:05:30"]
    C --> D["Truy vấn cửa sổ 09:00–09:05 theo event time"]
~~~

Ba mốc trong ví dụ:

| Trường | Giá trị | Dùng cho |
|---|---|---|
| **observedAt** | 09:03:10 UTC | Xác định nhiệt độ thực sự thuộc cửa sổ nào |
| **ingestedAt** | 09:05:10 UTC | Đo độ trễ truyền dữ liệu và phát hiện thiết bị offline |
| **processedAt** | 09:05:30 UTC | Đo độ trễ của pipeline xử lý |

Nếu yêu cầu là “nhiệt độ trung bình từ **09:00 đến trước 09:05**”, điểm đo lúc **09:03:10** thuộc cửa sổ này dù đến server sau 09:05. Nếu vô tình nhóm theo **ingestedAt**, phép đo bị đẩy sang cửa sổ khác và kết quả có thể sai.

Trong giám sát hệ thống, đôi khi thời điểm nhận tại server chính là thời gian có ý nghĩa nhất vì nguồn không cung cấp timestamp đáng tin cậy. Vì vậy **cột thời gian nào là nguồn sự thật phải được chốt theo nghiệp vụ**, không suy ra từ tên trường.

### UTC, múi giờ và độ chính xác

Thời điểm tuyệt đối nên được lưu dưới dạng timestamp có quy ước rõ, thường là **UTC**. Khi hiển thị hoặc nhóm theo ngày làm việc tại một địa phương, ứng dụng chuyển đổi theo múi giờ nghiệp vụ.

- **09:00 UTC** là một thời điểm tuyệt đối; **09:00 theo giờ địa phương** chưa đủ định danh nếu thiếu múi giờ và ngày.
- Cửa sổ “từ 09:00 đến 10:00” cần biết đang xét UTC hay múi giờ của nhà máy.
- Một “ngày địa phương” khi có chuyển giờ mùa hè có thể không dài đúng 24 giờ; không nên tự tính tất cả ngày lịch bằng cách cộng cố định 86.400 giây.
- Thiết bị có đồng hồ lệch có thể gửi dữ liệu ở tương lai hoặc quá khứ; cần chính sách kiểm tra, đánh dấu hoặc hiệu chỉnh, không âm thầm chấp nhận mọi timestamp.
- Độ chính xác milli/micro/nano giây phụ thuộc thiết bị, giao thức và database; khi chuyển đổi phải tránh làm tròn gây đổi cửa sổ.

## 3. Nhãn (tag/label) dùng để chọn chuỗi, không phải chứa mọi dữ liệu

Một điểm đo có thể có các nhãn:

~~~text
tenantId     = factory-a
deviceId     = sensor-01
metric       = temperature
building     = A
floor        = 2
~~~

Những nhãn này giúp trả lời “nhiệt độ của các cảm biến tầng 2”, “so sánh hai nhà máy” hoặc “truy vấn một thiết bị”.

Giá trị **temperatureC** là field/value vì nó thường thay đổi ở mỗi điểm và được dùng để tính trung bình, nhỏ nhất, lớn nhất hoặc phát hiện ngưỡng.

| Thông tin | Thường nên là | Lý do |
|---|---|---|
| tenantId | Nhãn/metadata | Cần lọc phạm vi tổ chức và phân quyền |
| deviceId | Nhãn/metadata | Cần chọn đúng chuỗi thiết bị |
| metric | Tên phép đo hoặc nhãn | Phân biệt nhiệt độ, độ ẩm, áp suất |
| temperatureC | Field/value | Dùng tính toán số học, thay đổi liên tục |
| observedAt | Timestamp | Dùng truy vấn thời gian và sắp cửa sổ |
| requestId duy nhất mỗi lần đo | Thường là field hoặc định danh sự kiện, không mặc định là label | Nếu tham gia danh tính series sẽ làm cardinality tăng mạnh |
| firmwareVersion | Metadata tùy truy vấn | Chỉ nên làm nhãn nếu cần lọc/nhóm và hiểu tác động khi giá trị thay đổi |

**Nhãn không tự tạo chỉ mục truy vấn miễn phí**. Mỗi sản phẩm quyết định cách lưu, index và đánh đổi của việc sử dụng nhãn. Đặc biệt trong một số TSDB, mỗi tổ hợp nhãn khác nhau tạo một series riêng, làm tăng chi phí lưu index hoặc bộ nhớ.

### Cardinality: nhiều nhãn có thể tạo rất nhiều chuỗi

**Cardinality** là số lượng tổ hợp chuỗi/nhãn khác nhau cần quản lý. Giả sử một hệ thống có:

- 20 tenant.
- Mỗi tenant có 5.000 thiết bị.
- Mỗi thiết bị ghi 3 loại phép đo.

Số chuỗi tối đa theo các chiều đó, khi mọi tổ hợp đều tồn tại:

\[
20 \times 5000 \times 3 = 300\,000\ \text{series}
\]

Nếu thêm một nhãn có **4 giá trị region** độc lập trên mỗi chuỗi, giới hạn lý thuyết có thể tăng thành **1.200.000** tổ hợp. Trong thực tế mỗi thiết bị thường chỉ thuộc một region tại một thời điểm, nên không thể cứ nhân số loại nhãn rồi khẳng định đó là số series thật; phải đo **tổ hợp thực sự tồn tại**.

Nếu đặt **requestId** duy nhất của từng phép đo thành nhãn tạo danh tính series, số series có thể tăng gần theo số điểm ghi. Đó là sai lầm phổ biến với hệ tối ưu cho tập chuỗi ổn định.

Ngược lại, **deviceId** cũng có cardinality cao nhưng vẫn là nhãn cần thiết nếu đường truy vấn cốt lõi luôn hỏi theo thiết bị. Không phải “nhãn nhiều giá trị luôn sai”; cần xét lợi ích truy vấn, số chuỗi, retention và giới hạn của hệ triển khai.

## 4. Từ yêu cầu nghiệp vụ thành hợp đồng truy vấn

Giả sử một dashboard cần:

> Hiển thị nhiệt độ trung bình của **sensor-01** thuộc **factory-a**, trong khoảng **09:00 đến trước 09:15 UTC**, chia thành các cửa sổ cố định **5 phút**. Mỗi cửa sổ phải có số mẫu, trung bình, giá trị nhỏ nhất và lớn nhất. Nếu không có dữ liệu, giao diện phải phân biệt “chưa có mẫu” với “nhiệt độ bằng 0”.

Ta có hợp đồng:

~~~yaml
# Hợp đồng minh họa, không phải cấu hình tự động của database
tenantId: factory-a
deviceId: sensor-01
metric: temperature
timeField: observedAt
startInclusive: 2026-11-14T09:00:00Z
endExclusive: 2026-11-14T09:15:00Z
windowType: tumbling
windowSize: 5m
timezone: UTC
aggregations: [count, avg, min, max]
emptyWindow: no_data
~~~

Hai dấu mốc **startInclusive** và **endExclusive** cố ý tạo khoảng nửa kín:

\[
[09{:}00,\ 09{:}15)
\]

Một bản ghi đúng **09:15:00** không nằm trong khoảng này. Cách dùng **[start, end)** giúp nối các cửa sổ liên tiếp không trùng ở ranh giới:

~~~text
W1 = [09:00, 09:05)
W2 = [09:05, 09:10)
W3 = [09:10, 09:15)
~~~

Điểm lúc **09:05:00** chỉ thuộc **W2**, không thuộc W1. Điều này đặc biệt quan trọng khi tổng hợp số sự kiện hoặc tổng tiền, nơi việc đếm trùng làm thay đổi kết quả nghiệp vụ.

## 5. Dữ liệu mẫu: có khoảng trống và điểm nằm đúng ranh giới

Để quan sát kết quả bằng mắt, ta dùng các mẫu giả lập:

| ID | Tenant | Device | observedAt (UTC) | temperatureC |
|---|---|---|---|---:|
| t01 | factory-a | sensor-01 | 09:00:10 | 20 |
| t02 | factory-a | sensor-01 | 09:01:10 | 21 |
| t03 | factory-a | sensor-01 | 09:03:10 | 23 |
| t04 | factory-a | sensor-01 | 09:05:10 | 22 |
| t05 | factory-a | sensor-01 | 09:08:10 | 26 |
| t06 | factory-a | sensor-01 | 09:10:10 | 24 |
| t07 | factory-a | sensor-01 | 09:12:10 | 25 |
| t08 | factory-a | sensor-01 | 09:15:00 | 27 |
| other01 | factory-a | sensor-02 | 09:02:10 | 30 |
| other02 | factory-a | sensor-02 | 09:06:10 | 32 |
| other03 | factory-b | sensor-01 | 09:01:10 | 99 |

Với câu hỏi đang xét, chỉ các điểm **t01 đến t07** thuộc tập truy vấn. **t08** bị loại vì bằng ranh giới kết thúc; các điểm **other** bị loại do khác cảm biến hoặc tổ chức.

Các mẫu không cách đều nhau: từ 09:01:10 đến 09:03:10 là 2 phút, trong khi những điểm khác cách 1–3 phút. Vì vậy, trung bình cộng của **các mẫu nhận được** chưa chắc bằng **trung bình nhiệt độ được tính theo thời lượng**. Cách diễn giải trung bình phải được xác định theo nhu cầu đo.

## 6. Mô hình hóa trong MongoDB time-series collection

MongoDB hỗ trợ **time-series collection** với **timeField** và tùy chọn **metaField**. Ta chọn:

- **observedAt**: thời gian diễn ra phép đo.
- **meta**: thuộc tính nhận diện nguồn/loại phép đo, tương đối ổn định cho các điểm của một chuỗi.
- **temperatureC**: giá trị đo thay đổi theo thời gian.
- **ingestedAt**: thời điểm hệ thống tiếp nhận để quan sát độ trễ.
- **eventId**: định danh sự kiện ổn định phục vụ xử lý retry và phát hiện trùng theo thiết kế ingestion.

Tạo collection:

~~~javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  }
});
~~~

**granularity: "seconds"** là gợi ý về độ phân giải của dữ liệu và cách tối ưu bucket nội bộ, không có nghĩa database tự làm tròn timestamp về giây hoặc mỗi giây chỉ có một điểm. Các khả năng và quy tắc thay đổi granularity phụ thuộc phiên bản MongoDB.

Thêm dữ liệu cho một cảm biến:

~~~javascript
const sensor = {
  tenantId: "factory-a",
  deviceId: "sensor-01",
  metric: "temperature"
};

const readings = [
  ["t01", "2026-11-14T09:00:10Z", 20],
  ["t02", "2026-11-14T09:01:10Z", 21],
  ["t03", "2026-11-14T09:03:10Z", 23],
  ["t04", "2026-11-14T09:05:10Z", 22],
  ["t05", "2026-11-14T09:08:10Z", 26],
  ["t06", "2026-11-14T09:10:10Z", 24],
  ["t07", "2026-11-14T09:12:10Z", 25],
  ["t08", "2026-11-14T09:15:00Z", 27]
];

db.sensorReadings.insertMany(
  readings.map(([eventId, time, temperatureC]) => ({
    eventId,
    meta: sensor,
    observedAt: ISODate(time),
    ingestedAt: ISODate("2026-11-14T09:20:00Z"),
    temperatureC
  }))
);

db.sensorReadings.insertMany([
  {
    eventId: "other01",
    meta: { tenantId: "factory-a", deviceId: "sensor-02", metric: "temperature" },
    observedAt: ISODate("2026-11-14T09:02:10Z"),
    ingestedAt: ISODate("2026-11-14T09:20:00Z"),
    temperatureC: 30
  },
  {
    eventId: "other02",
    meta: { tenantId: "factory-a", deviceId: "sensor-02", metric: "temperature" },
    observedAt: ISODate("2026-11-14T09:06:10Z"),
    ingestedAt: ISODate("2026-11-14T09:20:00Z"),
    temperatureC: 32
  },
  {
    eventId: "other03",
    meta: { tenantId: "factory-b", deviceId: "sensor-01", metric: "temperature" },
    observedAt: ISODate("2026-11-14T09:01:10Z"),
    ingestedAt: ISODate("2026-11-14T09:20:00Z"),
    temperatureC: 99
  }
]);
~~~

Ở đây, **ingestedAt = 09:20** cho mọi bản ghi là một tình huống minh họa gửi theo batch muộn; không phản ánh dữ liệu đến đúng lúc. Nhờ lưu cả hai thời điểm, dashboard vẫn có thể nhóm theo thời điểm đo, còn hệ thống vận hành quan sát được khoảng trễ tiếp nhận.

**Lưu ý về tính duy nhất:** trường **eventId** trong ví dụ là một định danh nghiệp vụ, không tự biến time-series collection thành kho chống ghi trùng. MongoDB time-series collection có những hạn chế riêng đối với unique indexes; nếu giao thức ingestion có retry, cần chiến lược deduplication/idempotency phù hợp, chẳng hạn quản lý event ID ở tầng tiếp nhận hoặc một kho khóa riêng. Không nên mặc định insert lại cùng eventId sẽ bị từ chối.

## 7. Truy vấn thô theo thời gian và nhãn

Để lấy các mẫu của một cảm biến trong cửa sổ 15 phút:

~~~javascript
db.sensorReadings.find(
  {
    "meta.tenantId": "factory-a",
    "meta.deviceId": "sensor-01",
    "meta.metric": "temperature",
    observedAt: {
      $gte: ISODate("2026-11-14T09:00:00Z"),
      $lt: ISODate("2026-11-14T09:15:00Z")
    }
  },
  {
    _id: 0,
    eventId: 1,
    observedAt: 1,
    temperatureC: 1
  }
).sort({ observedAt: 1, eventId: 1 });
~~~

Kết quả có **7 điểm t01–t07**, theo thứ tự thời gian tăng dần.

Điểm quan trọng trong truy vấn:

1. **Nhãn xác định chuỗi**: tenant, device và metric.
2. **Time range giới hạn số điểm cần đọc**: chỉ từ 09:00 đến trước 09:15.
3. **Projection giới hạn dữ liệu trả về**: không cần tải toàn bộ metadata khi chỉ vẽ biểu đồ.
4. **Sort xác định thứ tự**: thời điểm đo và eventId làm khóa phụ khi timestamp trùng.

Tùy workload và phiên bản MongoDB, có thể cân nhắc index trên các trường meta cùng timeField:

~~~javascript
db.sensorReadings.createIndex({
  "meta.tenantId": 1,
  "meta.deviceId": 1,
  "meta.metric": 1,
  observedAt: 1
});
~~~

Việc có cần tạo index này hay không phụ thuộc index mặc định của phiên bản, truy vấn thực tế, kích thước dữ liệu và kế hoạch thực thi. Index tốn dung lượng và chi phí ghi; không nên tạo nhiều index chỉ vì một trường xuất hiện trong ví dụ.

Nếu màn hình chỉ cần tổng hợp theo 5 phút, tải toàn bộ hàng triệu điểm về ứng dụng để tính trung bình là thiết kế không hiệu quả. Khi database hỗ trợ, ta để phép nhóm theo cửa sổ được thực hiện gần dữ liệu hơn.

## 8. Cửa sổ cố định (tumbling window) và phép tổng hợp

**Tumbling window** chia trục thời gian thành các khoảng **không chồng lấn**:

~~~text
09:00                     09:05                     09:10                     09:15
 |--------------------------|--------------------------|--------------------------|
          W1                           W2                         W3
 [09:00,09:05)                [09:05,09:10)                [09:10,09:15)
 t01 t02   t03                 t04      t05                 t06   t07
~~~

Với giá trị của **sensor-01**:

| Cửa sổ | Giá trị nằm trong cửa sổ | Số mẫu | Min | Max | Trung bình mẫu |
|---|---|---:|---:|---:|---:|
| [09:00, 09:05) | 20, 21, 23 | 3 | 20 | 23 | 21,333… |
| [09:05, 09:10) | 22, 26 | 2 | 22 | 26 | 24 |
| [09:10, 09:15) | 24, 25 | 2 | 24 | 25 | 24,5 |

Trung bình của W1 là \((20+21+23)/3 = 21{,}333\ldots\). Dữ liệu từ sensor-02 hoặc factory-b không được trộn vào kết quả. Điểm t08 ở đúng 09:15 không thuộc W3.

MongoDB aggregation dùng **$dateTrunc** để xác định mốc bắt đầu của từng cửa sổ 5 phút:

~~~javascript
db.sensorReadings.aggregate([
  {
    $match: {
      "meta.tenantId": "factory-a",
      "meta.deviceId": "sensor-01",
      "meta.metric": "temperature",
      observedAt: {
        $gte: ISODate("2026-11-14T09:00:00Z"),
        $lt: ISODate("2026-11-14T09:15:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$observedAt",
          unit: "minute",
          binSize: 5,
          timezone: "UTC"
        }
      },
      sampleCount: { $sum: 1 },
      averageC: { $avg: "$temperatureC" },
      minC: { $min: "$temperatureC" },
      maxC: { $max: "$temperatureC" }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      windowStart: "$_id",
      sampleCount: 1,
      averageC: 1,
      minC: 1,
      maxC: 1
    }
  }
]);
~~~

Trong pipeline:

- **$match** lọc chuỗi và phạm vi thời gian trước khi nhóm.
- **$dateTrunc** đưa các timestamp về đầu khoảng 5 phút theo UTC.
- **$group** tính count, avg, min, max cho từng cửa sổ.
- **$sort** sắp các cửa sổ theo thời điểm tăng dần.
- **$project** trả hình dạng phù hợp cho dashboard.

Nếu ứng dụng cần lấy kết quả nhiều thiết bị cùng lúc, chỉ nhóm theo **windowStart** sẽ trộn nhiều chuỗi. Khi đó phải nhóm theo cả danh tính chuỗi, ví dụ:

~~~javascript
{
  $group: {
    _id: {
      tenant: "$meta.tenantId",
      device: "$meta.deviceId",
      metric: "$meta.metric",
      windowStart: {
        $dateTrunc: { date: "$observedAt", unit: "minute", binSize: 5 }
      }
    },
    sampleCount: { $sum: 1 },
    averageValue: { $avg: "$temperatureC" }
  }
}
~~~

Lỗi bỏ quên nhóm theo nhãn thường tạo biểu đồ có giá trị “đúng về toán học” nhưng sai hoàn toàn về ý nghĩa nghiệp vụ.

## 9. Cửa sổ trượt (sliding window) khác cửa sổ cố định thế nào?

**Sliding window** có một khoảng thời gian dài **W**, nhưng kết quả được tính lại theo bước **S**. Nếu **S nhỏ hơn W**, các cửa sổ chồng lên nhau và một điểm có thể xuất hiện trong nhiều kết quả.

Ví dụ cửa sổ **10 phút**, trượt mỗi **5 phút**:

~~~text
W1 = [09:00, 09:10)
W2 = [09:05, 09:15)
W3 = [09:10, 09:20)

Trục thời gian:
09:00    09:05    09:10    09:15    09:20
  |--------- W1 ---------|
           |--------- W2 ---------|
                    |--------- W3 ---------|
~~~

Từ bộ dữ liệu sensor-01:

| Cửa sổ | Mẫu thuộc cửa sổ | Count | Trung bình mẫu |
|---|---|---:|---:|
| [09:00, 09:10) | 20, 21, 23, 22, 26 | 5 | 22,4 |
| [09:05, 09:15) | 22, 26, 24, 25 | 4 | 24,25 |
| [09:10, 09:20) | 24, 25, 27 | 3 | 25,333… |

Lưu ý: W3 có điểm **t08 lúc 09:15** vì cửa sổ W3 kéo dài đến trước 09:20. Nếu API vẫn giữ điều kiện **endExclusive = 09:15**, sẽ không thể tính đủ W3; phải thống nhất phạm vi dữ liệu nguồn với các cửa sổ cần xuất.

**Sliding window không thể thực hiện chỉ bằng cách đổi binSize của $dateTrunc.** $dateTrunc chia điểm vào các bucket cố định, còn cửa sổ trượt cần tính trên nhiều bucket chồng lấn. Có thể thực hiện bằng window function, pipeline chuyên dụng, công cụ stream processing hoặc xử lý ứng dụng, tùy hệ và quy mô.

Ví dụ giám sát **“trung bình 10 phút gần nhất, cập nhật mỗi phút”** là một cửa sổ trượt với W = 10 phút và S = 1 phút. Nó mượt hơn biểu đồ bucket không chồng lấn nhưng đòi hỏi xử lý nhiều kết quả hơn và phải quy định cách đối phó với điểm đến muộn.

## 10. Session window và cửa sổ theo lịch

Không phải mọi nghiệp vụ đều phù hợp với khoảng cố định 5 hay 10 phút.

**Session window** nhóm những sự kiện gần nhau, chia session khi khoảng im lặng vượt ngưỡng. Chẳng hạn, phiên hoạt động của một người dùng được định nghĩa là các sự kiện liên tiếp cách nhau **không quá 30 phút**. Một sự kiện đến muộn có thể nối hai session trước đó, khiến kết quả nhóm thay đổi; vì thế session window cần quy tắc về thời điểm chốt và độ trễ chấp nhận.

**Calendar window** nhóm theo lịch: giờ, ngày làm việc, tuần hoặc tháng của một múi giờ nghiệp vụ. Khái niệm “ngày” ở đây khác cửa sổ có độ dài vật lý cố định:

~~~text
Một cửa sổ 24 giờ:
  [2026-11-14T00:00Z, 2026-11-15T00:00Z)

Một ngày lịch theo múi giờ:
  Từ 00:00 địa phương ngày X đến trước 00:00 địa phương ngày X+1
  Khoảng UTC tương ứng phụ thuộc múi giờ và ngày cụ thể.
~~~

| Loại cửa sổ | Đặc điểm | Ví dụ |
|---|---|---|
| Tumbling | Không chồng lấn; mỗi điểm thuộc một bucket theo cách chia đã định | Tổng yêu cầu mỗi 5 phút |
| Sliding/hopping | Chồng lấn nếu bước trượt nhỏ hơn kích thước cửa sổ | Trung bình 10 phút, cập nhật mỗi phút |
| Session | Ranh giới phụ thuộc khoảng im lặng giữa sự kiện | Phiên truy cập website |
| Calendar | Ranh giới theo lịch và múi giờ | Doanh thu theo ngày địa phương |

Chọn cửa sổ là một phần của **hợp đồng báo cáo**, không chỉ là lựa chọn hiển thị. Hai nhóm cùng nói “tổng số đơn theo ngày” nhưng dùng UTC và giờ Việt Nam có thể thu được kết quả khác nhau quanh nửa đêm.

## 11. Không có mẫu, mẫu bằng 0 và dữ liệu đến muộn

Một nguyên tắc quan trọng: **“không có dữ liệu” không đồng nghĩa “giá trị bằng 0”**.

Giả sử thiết bị không gửi phép đo trong khoảng [09:20, 09:25). Có ít nhất ba cách biểu diễn:

| Cách thể hiện | Ý nghĩa | Khi nào phù hợp |
|---|---|---|
| **Không có điểm** | Chưa quan sát được phép đo cho bucket này | Giữ nguyên tính trung thực của dữ liệu |
| **NULL / no_data** | Hiển thị chủ động rằng bucket thiếu dữ liệu | Dashboard, cảnh báo sensor mất kết nối |
| **Điền 0** | Xem bucket trống là giá trị 0 | Chỉ khi nghiệp vụ thật sự định nghĩa không có sự kiện là 0, ví dụ một số loại đếm |
| **Giữ giá trị gần nhất** | Ước lượng tín hiệu không đổi cho tới mẫu tiếp theo | Một số loại gauge, nếu chấp nhận nội suy kiểu bậc thang |
| **Nội suy tuyến tính** | Ước lượng giá trị giữa hai điểm | Dữ liệu liên tục có giả định nội suy phù hợp |

Một biểu đồ nhiệt độ tự điền 0 °C khi sensor mất kết nối có thể tạo cảnh báo sai. Trái lại, một bucket đếm **số lần nhấp chuột** không có sự kiện có thể được biểu diễn là 0 nếu hệ thống chắc chắn đã thu thập đủ và nghiệp vụ muốn đếm như vậy.

MongoDB aggregation **$group** chỉ sinh bucket có dữ liệu phù hợp. Nếu dashboard muốn trục X liên tục, có thể tạo timeline các mốc thời gian ở ứng dụng hoặc dùng khả năng densify/fill của hệ đang triển khai khi phù hợp. Dù tạo đủ mốc, cần giữ ngữ nghĩa **no_data** thay vì tự biến thành số 0.

### Sự kiện đến muộn (late arrival)

Một điểm đo lúc **09:03:10** có thể tới pipeline lúc **09:20**. Nếu hệ thống đã công bố kết quả “W1 = 21 °C” khi mới nhận hai điểm 20 và 21, khi điểm 23 đến muộn thì trung bình mới phải là **21,333… °C** nếu chính sách cho phép cập nhật dữ liệu quá khứ.

Những lựa chọn có thể có:

1. **Cho phép cập nhật kết quả cửa sổ đã xuất** trong một khoảng trễ nhất định; dashboard có thể hiển thị lại.
2. **Chờ một thời gian trước khi chốt cửa sổ**, giảm số lần sửa kết quả nhưng tăng độ trễ người dùng thấy số liệu.
3. **Ghi nhận dữ liệu quá muộn vào luồng kiểm toán/backfill**, nếu không thể cập nhật trực tiếp báo cáo đã chốt.
4. **Loại bỏ hoặc đánh dấu không hợp lệ** theo quy tắc nghiệp vụ, khi nguồn timestamp không đáng tin hoặc dữ liệu đã quá hạn.

Trong xử lý luồng, **watermark** là một khái niệm dùng để ước lượng tiến độ event time và quyết định cửa sổ nào có thể được xem là đủ dữ liệu theo chính sách. Watermark **không chứng minh tuyệt đối** sẽ không còn sự kiện đến muộn; nó thể hiện một cam kết vận hành về độ trễ được chấp nhận.

## 12. Hai loại đại lượng phổ biến: gauge và counter

Không phải phép đo nào cũng có thể dùng AVG hoặc SUM trực tiếp.

**Gauge** là giá trị tại một thời điểm, có thể tăng hoặc giảm: nhiệt độ, bộ nhớ đang sử dụng, độ dài hàng đợi. Với gauge, **min**, **max**, **avg** theo thời gian thường có ý nghĩa nếu quy tắc lấy mẫu được hiểu đúng.

**Counter** thường tích lũy số sự kiện từ lúc bắt đầu hoặc từ lần reset gần nhất: tổng số HTTP request đã xử lý, tổng số byte truyền, số job đã hoàn tất. Counter có thể **reset về 0** khi tiến trình khởi động lại.

Ví dụ:

~~~text
Time    http_requests_total
09:00   1000
09:01   1060
09:02   1120
09:03     10   <- process restart / reset
09:04     70
~~~

Lấy **AVG** trên 1000, 1060, 1120, 10, 70 không trả “số request trung bình mỗi phút” theo nghĩa nghiệp vụ. Lấy **1120 - 1000** cũng chỉ nói về tăng trong khoảng 09:00–09:02 và bỏ qua reset sau đó.

Đối với counter, thường quan tâm:

- **Increase**: tăng bao nhiêu sự kiện trong khoảng, có xét reset theo quy tắc của hệ.
- **Rate**: tốc độ tăng trên một đơn vị thời gian.
- **Error ratio**: tỷ lệ giữa tốc độ lỗi và tốc độ tổng request, cần đảm bảo cùng khoảng và nhãn nhóm.

Prometheus/PromQL minh họa cách lấy tốc độ request trong cửa sổ 5 phút:

~~~promql
rate(http_requests_total{service="checkout"}[5m])
~~~

Biểu thức trả tốc độ **trên giây** cho từng chuỗi counter phù hợp, dựa trên các mẫu trong khoảng và có xử lý trường hợp counter reset theo ngữ nghĩa PromQL. Nếu muốn tổng theo service sau khi tính rate từng chuỗi:

~~~promql
sum by (service) (
  rate(http_requests_total{service="checkout"}[5m])
)
~~~

Đây là ví dụ PromQL, **không phải cú pháp MongoDB**. Biểu thức **[5m]** chọn một dải mẫu trước thời điểm đánh giá và khác với pipeline nhóm cửa sổ 5 phút cố định. Kết quả còn phụ thuộc chu kỳ thu thập mẫu, khoảng thiếu dữ liệu và quy tắc đánh giá của Prometheus.

### Trung bình mẫu khác trung bình theo thời lượng

Giả sử nhiệt độ có hai mẫu:

~~~text
09:00 -> 20 °C
09:09 -> 30 °C
~~~

Trung bình mẫu là **25 °C**, nhưng chưa thể kết luận nhiệt độ trung bình của cả 10 phút là 25 °C nếu không biết diễn biến giữa hai lần đo. Nếu coi nhiệt độ giữ nguyên từ mỗi mẫu đến mẫu kế tiếp (sample-and-hold), khoảng gần 9 phút đầu có thể được xem là 20 °C; còn nếu nội suy tuyến tính, kết quả sẽ khác. Cần chốt rõ mô hình nội suy hoặc tỷ lệ thời gian đại diện của từng mẫu.

## 13. Downsampling: giữ xu hướng khi dữ liệu lớn lên

Dữ liệu chuỗi thời gian thường được ghi liên tục. Giả sử **1.000 thiết bị**, mỗi thiết bị gửi **1 mẫu/10 giây**:

\[
1000 \times \frac{86\,400}{10}
= 8\,640\,000\ \text{mẫu/ngày}
\]

Nếu payload dữ liệu trung bình **60 byte/mẫu** trước index, metadata, replication và compression:

\[
8\,640\,000 \times 60
= 518\,400\,000\ \text{byte/ngày}
\approx 518{,}4\ \text{MB/ngày}
\]

Giữ 90 ngày thô ở tốc độ đó tương đương khoảng **46,656 GB dữ liệu payload thô**, chưa tính overhead và các bản sao.

Một chiến lược phổ biến:

| Lớp lưu trữ | Ví dụ retention | Dữ liệu giữ lại |
|---|---|---|
| Raw, độ phân giải cao | 7 ngày | Mỗi điểm 10 giây |
| Tổng hợp 1 phút | 90 ngày | Count, sum, min, max và metadata cần thiết |
| Tổng hợp 1 giờ | 1 năm | Tóm lược xu hướng để xem dài hạn |

Các thời hạn trên chỉ là **giả định học tập**. Retention thực tế phụ thuộc nhu cầu điều tra, báo cáo, chính sách và chi phí.

**Downsampling** là giảm độ phân giải bằng cách tạo điểm đại diện theo khoảng. Đổi lại, ta mất khả năng xem chính xác diễn biến của từng điểm gốc sau khi raw data đã bị xóa.

### Cạm bẫy khi tổng hợp nhiều cấp

Nếu một bucket có 2 mẫu với trung bình 10, bucket khác có 8 mẫu với trung bình 20, thì trung bình thật của 10 mẫu là:

\[
\frac{2 \times 10 + 8 \times 20}{2+8}=18
\]

Lấy trung bình đơn giản của hai trung bình bucket:

\[
\frac{10+20}{2}=15
\]

cho kết quả sai. Vì thế, một aggregate phục vụ tổng hợp lại nên giữ **sum** và **count**, hoặc cặp **avg + count**, thay vì chỉ giữ avg.

Tương tự:

- **Min của nhiều bucket** có thể tính từ min từng bucket.
- **Max** có thể tính từ max từng bucket.
- **Sum** có thể cộng các sum nếu các cửa sổ không chồng lấn và nghiệp vụ dùng phép cộng.
- **Count** có thể cộng các count nếu tránh trùng điểm.
- **Percentile/median** thường không thể gộp chính xác chỉ từ percentile của các bucket; cần dữ liệu gốc hoặc cấu trúc tóm tắt đặc biệt như histogram/sketch có tính chất gộp phù hợp.

Downsampling phải ghi rõ **độ phân giải, số mẫu, quy tắc xử lý điểm trùng, điểm muộn và khoảng trống**, để biểu đồ lịch sử không tạo cảm giác chính xác hơn dữ liệu thực tế.

## 14. Retention và TTL trong dữ liệu chuỗi thời gian

Chính sách lưu dữ liệu chuỗi thời gian cần phân biệt:

- **Hot retention**: giữ dữ liệu raw để truy vấn tương tác với độ phân giải cao.
- **Archive/rollup retention**: giữ dữ liệu tổng hợp hoặc bản lưu dài hạn.
- **Deletion policy**: thời điểm và phạm vi loại bỏ dữ liệu hết hạn.
- **Yêu cầu xóa theo chủ thể**: nếu dữ liệu gắn định danh cá nhân, cần xem cách xóa khỏi raw, rollup, cache, archive và backup theo chính sách.

MongoDB time-series collection có thể thiết lập cơ chế tự động hết hạn thông qua **expireAfterSeconds**, với ngữ nghĩa dọn dữ liệu theo thời gian và bucket nội bộ. Ví dụ cho một collection mới:

~~~javascript
db.createCollection("ephemeralReadings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800  // 7 ngày
});
~~~

**TTL là thao tác dọn nền, không bảo đảm bản ghi biến mất đúng tại giây hết hạn**. Với time-series collection, cơ chế xóa thực tế chịu ảnh hưởng của các bucket chứa nhiều điểm và thời điểm đủ điều kiện dọn bucket. Nếu ứng dụng có yêu cầu không trả dữ liệu quá hạn ngay lập tức, vẫn cần ràng buộc **time range** ở đường đọc.

Nếu trước khi xóa raw phải tạo rollup hoặc archive, không nên chỉ bật TTL mà không có cơ chế bảo đảm pipeline tổng hợp đã xử lý đủ dữ liệu. Tác vụ tạo rollup cần checkpoint, idempotency, khả năng backfill và kiểm chứng số lượng/tính toàn vẹn phù hợp.

## 15. Dữ liệu đến không đều, trùng lặp và chất lượng đo

Chuỗi thời gian thực tế thường không hoàn hảo:

| Hiện tượng | Ví dụ | Điều cần xác định |
|---|---|---|
| **Out-of-order** | Điểm 09:03 tới sau điểm 09:05 | Sắp xếp theo event time, cập nhật window cũ thế nào? |
| **Duplicate** | Thiết bị retry cùng eventId | Tính trung bình/count có được tính hai lần không? |
| **Missing samples** | Sensor mất mạng 15 phút | Hiển thị no_data, nội suy hay cảnh báo? |
| **Clock skew** | Đồng hồ sensor nhanh hơn 7 phút | Tin timestamp nguồn tới mức nào? |
| **Outlier** | Nhiệt độ nhảy lên 999 °C | Phép đo hợp lệ hay lỗi cảm biến? Có giữ bản gốc không? |
| **Unit mismatch** | Thiết bị gửi °F thay vì °C | Chuẩn hóa và ghi nhận đơn vị như thế nào? |
| **Schema evolution** | Firmware mới thêm độ ẩm | Dữ liệu cũ không có trường đó được đọc ra sao? |
| **Counter reset** | Bộ đếm HTTP về 0 sau restart | Hàm rate/increase có xử lý reset không? |

Ví dụ hai bản ghi cùng **eventId** nhưng khác **ingestedAt**:

~~~text
eventId=t03, observedAt=09:03:10, temperatureC=23, ingestedAt=09:05:10
eventId=t03, observedAt=09:03:10, temperatureC=23, ingestedAt=09:06:00
~~~

Nếu ghi cả hai thành hai điểm độc lập, **sampleCount** từ MongoDB aggregation có thể tăng sai và **avg** bị lệch khi dữ liệu trùng có giá trị khác các điểm còn lại. Do đó, chiến lược ingestion cần xác định danh tính bản ghi và chính sách retry:

1. Chấp nhận **at-least-once delivery** nhưng khử trùng trước khi ghi chuỗi.
2. Dùng định danh ổn định/khóa idempotency ở nguồn hoặc tầng tiếp nhận.
3. Nếu đã có dữ liệu trùng trong raw store, quy định cách xử lý khi truy vấn hoặc chạy job sửa dữ liệu.
4. Khi áp dụng sửa dữ liệu, đánh dấu phiên bản kết quả/rollup để không giữ những tổng hợp cũ sai lệch.

Cũng cần phân biệt **giá trị không hợp lệ** với giá trị hợp lệ bằng 0. Một điểm nhiệt độ không parse được, ví dụ **"unknown"**, không nên lén thay thành số 0 rồi đưa vào AVG.

## 16. Dữ liệu cửa sổ trong batch và streaming

Truy vấn lịch sử thường theo kiểu **batch**: cơ sở dữ liệu đã chứa điểm đo, sau đó người dùng yêu cầu lấy khoảng quá khứ và nhóm theo cửa sổ. Pipeline MongoDB với **$match → $group → $dateTrunc** là một ví dụ.

Trong hệ thống **streaming**, dữ liệu đến liên tục và phải cập nhật kết quả cửa sổ gần thời gian thực. Cần thêm khái niệm:

- **Window assignment**: một event thuộc cửa sổ nào dựa trên event time hoặc processing time?
- **Trigger**: khi nào hệ thống phát ra kết quả trung gian?
- **Watermark / allowed lateness**: khi nào cửa sổ được coi là đủ dữ liệu để chốt?
- **State**: hệ thống giữ count/sum/min/max của những cửa sổ đang mở ở đâu và bao lâu?
- **Correction/retraction**: nếu một điểm đến muộn làm thay đổi kết quả đã phát, cập nhật bản cũ ra sao?
- **Checkpoint/recovery**: khi job crash, kết quả có bị nhân đôi, mất điểm hoặc đếm sai không?

~~~mermaid
flowchart TD
    A["Thiết bị phát sinh sự kiện"] --> B["Ingestion / message queue"]
    B --> C["Kiểm tra timestamp, nhãn, ID và đơn vị"]
    C --> D["Raw time-series store"]
    C --> E["Window processor"]
    E --> F["Rollup 5 phút"]
    F --> G["Dashboard/alert"]
    D --> H["Query lịch sử hoặc backfill"]
    H --> F
~~~

Các nhánh xử lý cần cùng quy tắc sự kiện trùng, cửa sổ và độ trễ. Nếu pipeline trực tuyến nhóm theo giờ hệ thống mà job backfill nhóm theo UTC event time, hai bản tổng hợp có thể mâu thuẫn dù cùng một bộ raw data.

### Khi nào cần lưu cả raw và rollup?

Nếu báo cáo cần hiển thị nhanh dữ liệu một năm, rollup theo giờ tiết kiệm số điểm phải đọc. Nếu điều tra bất thường cần xem một cú spike 2 giây, raw data là cần thiết. Quyết định giữ cả hai phụ thuộc **độ phân giải nghiệp vụ cần khôi phục**, không phải chỉ dung lượng.

## 17. Đối chiếu các sản phẩm time-series

### InfluxDB: measurement, tag, field, timestamp

Một biểu diễn phổ biến là **InfluxDB line protocol**:

~~~text
temperature,tenant=factory-a,device=sensor-01 value=23.0 1700000000000000000
~~~

Trong ví dụ:

- **temperature** là measurement.
- **tenant** và **device** là tags.
- **value=23.0** là field số thực.
- Số cuối là Unix timestamp; **ví dụ sử dụng độ chính xác nano giây** khi client/endpoint được cấu hình tương ứng.

Timestamp này chỉ minh họa định dạng, **không phải** thời điểm 09:03:10 trong dataset MongoDB ở trên. InfluxDB có những khác biệt về engine, schema, ngôn ngữ truy vấn và hỗ trợ tính năng giữa các dòng/phiên bản; cần đọc đúng tài liệu của phiên bản đang dùng trước khi chọn cách viết query.

### Prometheus: labels và range vector

Một mẫu metric có thể được nhận diện bởi tên metric và bộ labels:

~~~text
http_requests_total{service="checkout",instance="api-1",status="500"} 1234
~~~

**http_requests_total** thường được dùng như counter; **service**, **instance**, **status** là labels định danh series. Biểu thức PromQL:

~~~promql
sum by (service) (
  rate(http_requests_total{status="500"}[5m])
)
~~~

tính tốc độ lỗi trên giây từ các chuỗi counter phù hợp trong khoảng 5 phút và cộng theo service. Đây là cách biểu diễn truy vấn khác MongoDB group theo bucket cố định. Những nhãn có số tổ hợp rất lớn, như request ID duy nhất, có thể khiến số series của Prometheus tăng quá mạnh.

### MongoDB: document và time-series collection

MongoDB lưu phép đo dưới dạng document có **timeField**, **metaField** và fields của phép đo. Ưu điểm là kết hợp linh hoạt với hệ sinh thái document và aggregation pipeline. Cần chú ý các giới hạn riêng của time-series collection, cấu hình bucket, loại index được hỗ trợ, độ trễ truy vấn và khả năng xử lý mutation/upsert theo phiên bản.

| Khía cạnh | InfluxDB | Prometheus | MongoDB time series |
|---|---|---|---|
| Biểu diễn điểm đo | Measurement, tags, fields, timestamp | Metric name, labels, sample value, timestamp | Document với timeField, metaField, value fields |
| Đường truy vấn thường gặp | Lọc tags/time, tính aggregate theo thời gian | PromQL theo labels và range | Find/aggregation theo metadata và time |
| Mối quan tâm cardinality | Tổ hợp series/tags, phụ thuộc engine | Tổ hợp labels trên mỗi metric | Số chuỗi meta, kích thước bucket và index |
| Chức năng cửa sổ | Phụ thuộc phiên bản/query language | Range vector, rate, aggregation | $dateTrunc, $group, window pipeline khi phù hợp |
| Tính chất vận hành | Phụ thuộc phiên bản và cấu hình lưu trữ | Thường dùng monitoring/metrics | Tích hợp use case time-series trong document database |

Không có một sản phẩm luôn tốt nhất: lựa chọn phụ thuộc độ trễ chấp nhận, số lượng series, mẫu truy vấn, retention, chi phí, yêu cầu xóa và hệ sinh thái hiện có.

## 18. Hiệu năng của truy vấn cửa sổ phụ thuộc cả thời gian và nhãn

Một truy vấn “tính trung bình 5 phút” có thể rất nhẹ khi đọc **một cảm biến trong 15 phút**, nhưng tốn kém khi phải tính cho **mọi thiết bị trong 2 năm**.

Các yếu tố cần định lượng:

| Yếu tố | Câu hỏi đo được |
|---|---|
| **Số series phù hợp** | Bộ lọc tag/label thu hẹp được bao nhiêu thiết bị? |
| **Độ rộng time range** | Đọc 15 phút, 7 ngày hay 1 năm? |
| **Tần suất ghi** | Mỗi series có bao nhiêu điểm/giây? |
| **Số cửa sổ** | Khoảng thời gian chia ra bao nhiêu bucket? |
| **Kích thước điểm** | Mỗi bản ghi có payload và metadata lớn không? |
| **Cardinality của nhãn** | Một tổ hợp nhãn có tạo series mới liên tục không? |
| **Missing/late/duplicate** | Kết quả phải sửa lại bao nhiêu lần? |
| **Index/bucket pruning** | Hệ có bỏ qua được vùng không khớp thời gian/nhãn không? |
| **Downsampling** | Có thể đọc rollup thay vì toàn bộ raw data không? |

Ví dụ tính số điểm cần xét:

~~~text
1000 thiết bị
1 điểm mỗi 10 giây
Truy vấn 24 giờ

1000 × (86400 / 10) = 8.640.000 điểm
~~~

Nếu dashboard chỉ cần biểu đồ 24 giờ với 1 điểm/phút/thiết bị, rollup 1 phút có thể giảm số điểm về **1.440.000** cho cùng 1.000 thiết bị trước khi tính nhóm bổ sung. Nhưng việc dùng rollup có phù hợp hay không còn phụ thuộc phép tổng hợp có thể gộp đúng, yêu cầu độ chính xác và dữ liệu đến muộn.

### Những số liệu nên quan sát

- Thời gian truy vấn ở **p50/p95/p99** theo khoảng thời gian và số series.
- Số điểm/bucket đọc so với số điểm kết quả.
- Kích thước index, số bucket nội bộ và tốc độ tăng dung lượng.
- Số series mới mỗi ngày, sự tăng bất thường do nhãn có cardinality cao.
- Lượng dữ liệu đến muộn, độ trễ ingestion, tỷ lệ bản ghi trùng hoặc lỗi parse.
- Độ trễ đồng bộ rollup và số lần sửa cửa sổ đã công bố.
- Chi phí lưu raw/rollup/archive và hiệu quả chính sách xóa.

Chạy một aggregation trên dữ liệu 11 điểm mẫu chỉ chứng minh cách tính ở ví dụ đó. Để đánh giá một hệ sản xuất, phải thử với số series, tốc độ ghi, độ trễ mạng và tần suất truy vấn tương tự thực tế.

## 19. Các sai lầm thường gặp

| Sai lầm | Vì sao gây sai hoặc tốn tài nguyên | Cách thiết kế phù hợp |
|---|---|---|
| Dùng ingestion time thay cho event time | Điểm đến muộn rơi vào cửa sổ sai | Chốt thời gian nghiệp vụ, lưu cả observedAt/ingestedAt khi cần |
| Dùng khoảng kết thúc **$lte** cho mọi cửa sổ | Điểm ở ranh giới có thể được đếm hai lần | Sử dụng khoảng nửa kín **[start, end)** |
| Nhóm chỉ theo thời gian khi query nhiều thiết bị | Trộn các chuỗi khác nhau | Nhóm theo cả timestamp bucket và series identity |
| Biến thiếu dữ liệu thành 0 mặc định | Tạo phép đo giả và cảnh báo sai | Phân biệt no_data, zero, nội suy |
| Gắn requestId vào label của mỗi điểm | Cardinality tăng gần theo số sự kiện | Đặt requestId vào field hoặc cơ chế truy vết phù hợp |
| Tính trung bình của các trung bình mà không có count | Kết quả rollup sai nếu bucket có số mẫu khác nhau | Giữ sum + count, quy tắc gộp rõ ràng |
| Lấy AVG trên counter tích lũy | Không phản ánh tốc độ/số sự kiện phát sinh | Dùng rate/increase có xét reset |
| Coi trung bình mẫu là trung bình thời gian | Sai khi khoảng cách mẫu không đều | Xác định phép nội suy hoặc trọng số thời gian |
| Truy vấn cả năm raw data cho biểu đồ 100 pixel | Đọc và vận chuyển quá nhiều điểm | Dùng rollup/downsampling phù hợp |
| Chỉ bật TTL mà không xét rollup/backup | Có thể xóa raw trước khi tổng hợp đủ hoặc giữ bản sao ngoài ý muốn | Quản lý retention theo từng lớp và xác nhận pipeline |
| Không xử lý duplicate/out-of-order | Count, avg, alert hoặc trạng thái cửa sổ sai | Định danh event, deduplication và chính sách lateness |
| Coi SQL, PromQL và line protocol là cùng một cách truy vấn | Nhầm ngữ nghĩa giữa các engine | Đối chiếu API, version và cách đặt cửa sổ của từng hệ |

## 20. Quy trình thiết kế từ yêu cầu đến kết quả quan sát được

~~~mermaid
flowchart TD
    A["Yêu cầu: đo đại lượng gì, cho ai?"] --> B["Chọn event time, độ chính xác, timezone"]
    B --> C["Chọn tags/labels và định danh series"]
    C --> D["Chọn fields, đơn vị và loại gauge/counter"]
    D --> E["Xác định khoảng thời gian và loại cửa sổ"]
    E --> F["Mô hình raw data, index và retention"]
    F --> G["Truy vấn/streaming aggregation"]
    G --> H["Điền khoảng trống, xử lý muộn/trùng và rollup"]
    H --> I["So kết quả với mẫu kỳ vọng và đo hiệu năng"]
    I -->|Chưa đạt| B
    I -->|Đạt| J["Giám sát khi số series và dữ liệu tăng"]
~~~

Với một yêu cầu mới, nên viết ra những câu trả lời sau trước khi chọn database:

1. **Đại lượng nào đang đo?** Nhiệt độ, CPU, counter hay sự kiện rời rạc?
2. **Một chuỗi được định danh bởi những nhãn nào?** Có nhãn nào đổi quá nhanh hoặc tạo cardinality không kiểm soát?
3. **Thời gian của bản ghi có nghĩa gì?** Device time, server ingest time hay processing time?
4. **Một cửa sổ có ranh giới nào?** Theo phút, theo ngày địa phương, không chồng lấn hay trượt?
5. **Tính gì trong cửa sổ?** Count, sum, avg, min, max, percentile, rate hoặc một hàm nghiệp vụ?
6. **Khi thiếu dữ liệu phải làm gì?** Giữ no_data, ghi 0, nội suy hay báo lỗi?
7. **Điểm đến muộn/trùng sẽ xử lý ra sao?** Kết quả đã xuất được sửa trong thời hạn nào?
8. **Giữ dữ liệu ở độ phân giải nào và bao lâu?** Có cần raw để điều tra hay chỉ cần xu hướng?
9. **Kiểm chứng thế nào?** Mẫu đầu vào, kết quả theo bucket và số liệu tải/độ trễ nào chứng minh đúng?

## 21. Bài tập áp dụng

### Bài tập 1 — Chia cửa sổ cố định

Cho các điểm của sensor-01 tại **09:00:10 (20)**, **09:01:10 (21)**, **09:03:10 (23)**, **09:05:10 (22)**, **09:08:10 (26)**, **09:10:10 (24)**, **09:12:10 (25)** và **09:15:00 (27)**. Hãy lập bảng **count, min, max, avg** cho ba cửa sổ **[09:00,09:05)**, **[09:05,09:10)**, **[09:10,09:15)** và giải thích điểm 09:15 thuộc cửa sổ nào.

### Bài tập 2 — Nhãn và cardinality

Một hệ có 200.000 thiết bị, mỗi thiết bị ghi nhiệt độ và độ ẩm. Đội phát triển đề xuất thêm **requestId** duy nhất cho mỗi mẫu vào labels của TSDB. Hãy phân tích tác động đến cardinality và đề xuất cách giữ requestId để truy vết mà vẫn truy vấn theo thiết bị thuận lợi.

### Bài tập 3 — Trượt cửa sổ

Tính trung bình của cửa sổ dài **10 phút**, trượt **5 phút**, trong các khoảng **[09:00,09:10)**, **[09:05,09:15)** và **[09:10,09:20)**. Giải thích vì sao không thể chỉ dùng phép chia dữ liệu thành bucket cố định bằng **$dateTrunc** để có đầy đủ các cửa sổ này.

### Bài tập 4 — Dữ liệu đến muộn

Dashboard đã chốt trung bình 5 phút là **20,5 °C** với hai mẫu 20 và 21. Sau 10 phút, nó nhận thêm một điểm đo **23 °C** có event time nằm trong cùng cửa sổ. Trình bày các lựa chọn cập nhật/chốt, giá trị mới nếu chấp nhận điểm muộn, và cách để người dùng biết kết quả từng được sửa.

### Bài tập 5 — Mẫu không đều

Thiết bị đo 20 °C lúc 09:00 và 30 °C lúc 09:09, không có mẫu khác. So sánh **trung bình hai mẫu** với **trung bình theo thời lượng** nếu giả định giá trị giữ nguyên từ lần đo đầu đến lần đo sau. Nêu điều kiện cần thiết trước khi diễn giải giá trị trung bình thành “nhiệt độ trung bình thực tế trong 10 phút”.

### Bài tập 6 — Counter và reset

Một service có chuỗi counter **1000 → 1060 → 1120 → 10 → 70** qua các phút. Giải thích sự khác nhau giữa tổng counter, tốc độ request, trung bình các điểm counter và phép tính rate có xử lý reset. Đề xuất PromQL để tính tổng tốc độ theo service.

### Bài tập 7 — Downsampling đúng

Một bucket 1 phút có **count = 2, sum = 20**; bucket tiếp theo có **count = 8, sum = 160**. Hãy tính trung bình chung 2 phút và giải thích vì sao lấy trung bình đơn giản của hai giá trị avg không đúng.

### Bài tập 8 — Thiết kế hệ thực tế

Một nhà máy có 10.000 cảm biến ghi mỗi 5 giây. Dashboard cần xem chi tiết 24 giờ gần nhất và xu hướng trung bình theo giờ của 2 năm trước. Hãy đề xuất:

- Time field, metadata và field đo.
- Đường đọc chi tiết so với đường đọc lịch sử.
- Kế hoạch raw retention, rollup, quy tắc gộp và lưu trữ.
- Cách xử lý thiết bị offline, retry và gửi muộn.
- Chỉ số quan sát khi số series, khối lượng ghi và thời gian truy vấn tăng.

Khi làm bài, hãy lần theo chuỗi **thời điểm → nhãn định danh chuỗi → giá trị đo → khoảng và loại cửa sổ → hàm tổng hợp → dữ liệu thiếu/trễ → kết quả kiểm chứng được**. Tư duy này giúp mô hình NoSQL chuyên cho chuỗi thời gian trả lời đúng ý nghĩa nghiệp vụ, đồng thời kiểm soát được chi phí khi dữ liệu liên tục tăng.
