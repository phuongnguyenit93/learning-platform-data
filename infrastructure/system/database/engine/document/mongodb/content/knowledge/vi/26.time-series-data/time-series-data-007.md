# Chính sách hết hạn dữ liệu và cơ chế TTL trong MongoDB Time Series

Hệ thống đo nhiệt độ, theo dõi thiết bị IoT, lưu metric máy chủ hay thu thập dữ liệu vận hành thường tạo ra **dòng sự kiện có timestamp tăng liên tục**. Sau một khoảng thời gian, phần lớn dữ liệu gốc không còn cần thiết cho truy vấn hằng ngày, nhưng vẫn chiếm dung lượng đĩa, index và tài nguyên sao lưu.

Ví dụ một hệ thống thu thập:

~~~text
10.000 cảm biến
  × 1 phép đo mỗi 10 giây
  × 86.400 giây/ngày
  ÷ 10 giây/phép đo
  = 86.400.000 phép đo mỗi ngày
~~~

Nếu mọi phép đo được giữ mãi, lượng dữ liệu tích lũy tăng rất nhanh. Một chính sách **retention** hợp lý có thể yêu cầu:

- Giữ **dữ liệu gốc** trong 7 ngày để điều tra sự cố.
- Giữ **tổng hợp theo giờ** trong 90 ngày để phân tích xu hướng.
- Giữ **báo cáo theo ngày** trong một năm.
- Xóa dữ liệu đã hết thời hạn nếu không có yêu cầu lưu giữ bổ sung.

MongoDB hỗ trợ tự động loại bỏ dữ liệu quá hạn bằng **TTL – Time To Live**. Với **time series collection**, TTL có những đặc điểm khác collection thông thường: MongoDB tổ chức phép đo trong **bucket**, và việc loại bỏ thường dựa trên **toàn bộ bucket đã hết hạn**, không phải từng phép đo biến mất chính xác vào giây mà nó đạt ngưỡng.

Bài học này tập trung vào **chính sách hết hạn dữ liệu và cơ chế TTL trong ngữ cảnh chuỗi thời gian**, bao gồm:

1. Phân biệt TTL, retention, archive, downsampling và truy vấn theo cửa sổ thời gian.
2. Tạo time series collection với **expireAfterSeconds** và chọn timeField/metaField.
3. Hiểu mốc hết hạn theo timestamp, bucket, granularity và TTL monitor.
4. Bật, tăng, giảm hoặc tắt TTL trên collection hiện có bằng **collMod**.
5. Áp dụng **partial TTL index theo metaField** ở phiên bản hỗ trợ.
6. Xử lý dữ liệu trễ, timestamp sai, TTL backlog, việc xóa hàng loạt và bảo toàn báo cáo.
7. Thiết kế lưu trữ nhiều tầng, quan sát vận hành, lập trình Java/Spring Data MongoDB và bài tập thực hành.

Những lệnh ghi/xóa/collMod trong bài chỉ áp dụng cho **database thử nghiệm**. Với dữ liệu production, phải xác nhận retention policy, khả năng mất dữ liệu không thể khôi phục và phương án sao lưu trước khi thay đổi TTL.

## 1. Chính sách retention và TTL không phải cùng một thứ

**Retention policy** là **quy tắc nghiệp vụ** trả lời: loại dữ liệu nào được giữ bao lâu, khi nào được xóa, có ngoại lệ nào và ai phê duyệt việc xóa.

**TTL** là một **cơ chế kỹ thuật** giúp MongoDB tự dọn các document/bucket quá tuổi theo timestamp và số giây cấu hình.

Ví dụ một chính sách:

| Loại dữ liệu | Mức chi tiết | Thời gian giữ | Hướng triển khai |
|---|---|---:|---|
| Raw sensor readings | Mỗi 10 giây | 7 ngày | Time series collection có TTL 7 ngày |
| Hourly aggregates | Mỗi 1 giờ | 90 ngày | Collection tổng hợp riêng, TTL 90 ngày |
| Daily aggregates | Mỗi 1 ngày | 365 ngày | Collection tổng hợp riêng, TTL 365 ngày |
| Audit hoặc hồ sơ đặc biệt | Theo yêu cầu pháp lý | Theo chính sách riêng | Không xóa chỉ bằng TTL raw mặc định |

TTL chỉ thực thi **một phần** của chính sách. Nó không tự tạo dữ liệu tổng hợp, không tự chuyển dữ liệu sang lưu trữ lạnh, không tự thực hiện quy trình legal hold và không tự bảo đảm mọi bản sao lưu được xóa cùng thời điểm.

### 1.1. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| TTL | Cơ chế tự xóa dữ liệu khi đủ điều kiện hết hạn | Xóa raw reading sau 604800 giây |
| Retention | Quy tắc tổ chức về thời gian và lý do giữ dữ liệu | Raw giữ 7 ngày, aggregate giữ 90 ngày |
| Expiration threshold | Mốc thời gian mà dữ liệu bắt đầu đủ điều kiện xóa | timestamp + 7 ngày |
| Physical deletion | Thời điểm cơ chế nền thực sự xóa dữ liệu | Có thể sau thời điểm hết hạn |
| Archiving | Chuyển dữ liệu sang kho lưu trữ khác | Object storage hoặc kho lưu trữ lâu dài |
| Downsampling | Giảm độ phân giải của dữ liệu theo thời gian | Trung bình nhiệt độ mỗi 1 giờ |
| Aggregation | Tính toán thống kê từ dữ liệu | Min/max/avg/count theo sensor |
| Legal hold | Ngoại lệ ngăn xóa theo quy định/hợp đồng | Một vụ điều tra yêu cầu giữ bản ghi |

### 1.2. Tại sao cần xác định chính sách trước khi bật TTL?

Giả sử dữ liệu gốc chứa nhiệt độ tăng đột biến trong một giờ. Nếu bạn bật TTL 24 giờ nhưng báo cáo mỗi ngày được tạo một lần và batch báo cáo bị trì hoãn, dữ liệu đầu vào có thể bị xóa **trước khi job tổng hợp kịp đọc**.

Do đó, một chính sách an toàn cần xét:

- Khoảng trễ lớn nhất từ **event time** đến lúc dữ liệu được ghi vào MongoDB.
- Độ trễ của **pipeline tổng hợp**.
- Khả năng job phải **chạy lại sau lỗi**.
- Thời gian cần cho **kiểm toán, support, điều tra sự cố**.
- Thời gian **backup/restore** và phương án khôi phục báo cáo.
- Mức dung lượng đĩa tối đa chấp nhận được.

**Không nên chọn TTL chỉ dựa trên “muốn dùng ít ổ đĩa hơn”.** Một giá trị quá ngắn có thể làm mất dữ liệu trước khi workflow phụ thuộc vào nó hoàn tất.

## 2. Time series collection lưu dữ liệu như thế nào?

MongoDB time series collection là loại collection chuyên dụng cho các bản ghi có **thời điểm đo** và thường có **metadata của nguồn phát sinh**.

Ví dụ một phép đo:

~~~javascript
{
  timestamp: ISODate("2026-11-14T06:05:00.000Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01",
    retentionClass: "STANDARD"
  },
  temperatureC: 28.4,
  humidityPct: 76.2
}
~~~

Các trường:

- **timestamp**: BSON Date xác định thời điểm phép đo.
- **sensor**: metadata của cảm biến và nhóm đo, được khai báo làm **metaField**.
- **temperatureC**, **humidityPct**: các giá trị đo.

### 2.1. timeField, metaField và granularity

Khi tạo collection:

~~~javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});
~~~

**timeField** là trường bắt buộc, chứa giá trị thời gian kiểu Date hợp lệ theo quy tắc time series. **metaField** là trường tùy chọn dùng để nhóm các phép đo cùng nguồn/metadata. **granularity** mô tả độ chi tiết thời gian điển hình của dữ liệu để MongoDB tối ưu bucketing.

Không nên hiểu **granularity: "seconds"** là MongoDB bắt buộc timestamp chỉ có đơn vị giây, hoặc mỗi bucket chứa đúng một giây dữ liệu. Granularity là gợi ý cấu trúc khoảng bucket cho time series.

### 2.2. MongoDB gom các phép đo vào bucket

Ở mức logic người dùng nhìn thấy:

~~~text
sensorReadings

S-101  06:00:00  temperature=28.0
S-101  06:00:10  temperature=28.1
S-101  06:00:20  temperature=28.3
S-101  06:00:30  temperature=28.2
S-102  06:00:05  temperature=27.8
~~~

Ở tầng lưu trữ nội bộ, MongoDB có thể tổ chức các phép đo có **metaField giống nhau** và timestamp gần nhau thành bucket:

~~~text
Bucket A: sensor S-101
   06:00:00
   06:00:10
   06:00:20
   06:00:30

Bucket B: sensor S-102
   06:00:05
~~~

Sơ đồ chỉ minh họa nguyên tắc. Số phép đo, giới hạn dung lượng, việc bucket đóng/mở và cách MongoDB chọn bucket phụ thuộc phiên bản và tải thực tế; không giả định bốn phép đo trên chắc chắn được lưu chung một bucket vật lý.

### 2.3. Tại sao bucket quan trọng với TTL?

Một document đo lúc 06:00 có thể đã đủ tuổi xóa trong khi bucket chứa nó cũng có phép đo lúc 06:50 chưa đủ tuổi. Time series TTL **không nhất thiết xóa riêng phép đo 06:00 ngay**.

MongoDB có thể phải chờ đến khi **toàn bộ các phép đo thuộc bucket đủ điều kiện hết hạn**, rồi cơ chế TTL nền mới xóa bucket.

Đây là khác biệt trọng tâm với TTL trên một collection thường, nơi TTL index trực tiếp xét document theo field Date được index.

## 3. Tạo time series collection có TTL ngay từ đầu

Giả sử cần giữ dữ liệu gốc của sensor **7 ngày**.

### 3.1. Chuyển ngày sang số giây

~~~text
7 ngày × 24 giờ/ngày × 60 phút/giờ × 60 giây/phút
= 604800 giây
~~~

Các giá trị thường dùng:

| Retention | expireAfterSeconds |
|---|---:|
| 15 phút | 900 |
| 1 giờ | 3600 |
| 24 giờ | 86400 |
| 7 ngày | 604800 |
| 30 ngày cố định | 2592000 |
| 90 ngày cố định | 7776000 |
| 365 ngày cố định | 31536000 |

Lưu ý: **30 ngày cố định không đồng nghĩa một tháng lịch**; 365 ngày cũng không phải mọi năm dương lịch. TTL dùng **số giây thời gian thực**, không tự hiểu “hết cuối tháng theo giờ địa phương”.

### 3.2. Câu lệnh tạo collection

~~~javascript
use timeseries_ttl_lab

db.createCollection("sensorReadings7d", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

Lệnh này tạo một **time series collection** và thiết lập cơ chế tự hết hạn theo tuổi dữ liệu.

Ý nghĩa của **expireAfterSeconds: 604800**:

> Một phép đo có timestamp T được coi là quá hạn khi khoảng thời gian từ T đến thời điểm xét đã đạt 604800 giây; việc xóa thực tế còn phụ thuộc bucket và TTL monitor.

TTL không tự suy từ **thời gian insert** nếu timeField lưu thời điểm đo cũ; nó dựa trên giá trị thời gian được chỉ định trong **timestamp**.

### 3.3. Dữ liệu mẫu

~~~javascript
const now = new Date();
const minute = 60 * 1000;
const hour = 60 * minute;
const day = 24 * hour;

db.sensorReadings7d.insertMany([
  {
    timestamp: new Date(now.getTime() - 1 * hour),
    sensor: {
      sensorId: "S-101",
      site: "HCM-01",
      retentionClass: "STANDARD"
    },
    temperatureC: 28.4
  },
  {
    timestamp: new Date(now.getTime() - 3 * day),
    sensor: {
      sensorId: "S-101",
      site: "HCM-01",
      retentionClass: "STANDARD"
    },
    temperatureC: 29.1
  },
  {
    timestamp: new Date(now.getTime() - 8 * day),
    sensor: {
      sensorId: "S-102",
      site: "HCM-02",
      retentionClass: "STANDARD"
    },
    temperatureC: 30.2
  }
]);
~~~

Phép đo **8 ngày trước** đã quá ngưỡng 7 ngày ngay từ lúc insert, nhưng không nên kỳ vọng nó biến mất đồng bộ trước khi insertMany trả về. Nó có thể tồn tại tạm thời cho tới khi các điều kiện xóa bucket được đáp ứng và TTL monitor xử lý.

### 3.4. Đọc dữ liệu bình thường

~~~javascript
db.sensorReadings7d.find(
  {
    "sensor.sensorId": "S-101",
    timestamp: {
      $gte: new Date(Date.now() - 7 * 24 * 3600 * 1000)
    }
  },
  {
    _id: 0,
    timestamp: 1,
    sensor: 1,
    temperatureC: 1
  }
).sort({ timestamp: 1 });
~~~

Lệnh find này chủ động lọc dữ liệu trong **cửa sổ 7 ngày tính tại lúc truy vấn**. Điều kiện query là một cơ chế khác TTL: nó kiểm soát dữ liệu mà **truy vấn trả về**, trong khi TTL kiểm soát dữ liệu được MongoDB tự xóa **không đồng bộ**.

Nếu API cần bảo đảm **không hiển thị phép đo quá 7 ngày** ngay tại thời điểm request, nên dùng filter timestamp như trên, không dựa vào việc TTL monitor đã xóa hết dữ liệu đến đúng giây đó.

## 4. Cách tính thời điểm hết hạn

Đặt:

- \(t_m\): thời điểm phép đo trong timeField.
- \(R\): retention tính bằng giây.
- \(t_e\): thời điểm phép đo **bắt đầu đủ điều kiện** hết hạn.

Ta có:

\[
t_e = t_m + R
\]

Ví dụ retention 24 giờ:

~~~text
Measurement timestamp: 2026-11-14T10:15:00Z
Retention:             86400 giây
Eligible timestamp:    2026-11-15T10:15:00Z
~~~

**Eligible timestamp không phải cam kết MongoDB xóa document đúng 10:15:00Z ngày hôm sau**. Với time series, bucket vẫn có thể chứa phép đo mới hơn, và quá trình dọn nền có thể chạy sau.

### 4.1. TTL tính từ event time hay ingest time?

Time series TTL sử dụng **timeField được khai báo**, ví dụ timestamp. Nếu một sensor phát sinh dữ liệu lúc 10:00 nhưng kết nối mạng bị ngắt và ứng dụng chỉ insert lúc 16:00, hai mốc khác nhau:

~~~text
eventTime:  10:00
ingestedAt: 16:00
~~~

Nếu timeField là **eventTime**, retention 24 giờ tính từ **10:00**, không phải 16:00.

Nếu nghiệp vụ muốn giữ dữ liệu **ít nhất 24 giờ sau khi hệ thống nhận**, phải thiết kế khác, chẳng hạn chọn timeField theo ingest time trong một collection phù hợp hoặc sử dụng quy trình lưu trữ khác. Quyết định này ảnh hưởng thứ tự thời gian của phép đo, bucketing và ý nghĩa thống kê.

### 4.2. Không thay thế timestamp Date bằng String

Sai cho timeField:

~~~javascript
{
  timestamp: "2026-11-14T10:15:00Z",
  temperatureC: 28.4
}
~~~

Đây là **String**, không phải BSON Date. Khi timeField được MongoDB yêu cầu là Date, thao tác sẽ không đáp ứng schema của time series collection.

Đúng:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:15:00Z"),
  temperatureC: 28.4
}
~~~

Trong Java, có thể truyền **java.util.Date**, hoặc cấu hình codec phù hợp cho **java.time.Instant**. Không coi ISO string tự được MongoDB chuyển thành Date.

### 4.3. UTC và múi giờ

BSON Date biểu diễn một **thời điểm UTC**. Nếu sensor báo “14/11 lúc 17:00 ở Việt Nam” (UTC+07), thời điểm tương ứng là **2026-11-14T10:00:00Z**.

TTL theo số giây là khoảng cách thời gian thực, **không phụ thuộc ngày đổi giờ địa phương**. Nếu nhu cầu là “xóa sau đúng 7 ngày × 24 giờ”, phép tính 604800 giây là rõ ràng. Nếu quy tắc là “xóa khi hết tháng kế tiếp ở timezone của cơ sở”, hãy tính chính sách riêng thay vì giả định expireAfterSeconds diễn đạt được lịch địa phương.

## 5. Time series TTL xóa theo bucket, không đúng thời điểm từng measurement

Đây là phần quan trọng nhất của cơ chế TTL dành cho time series collection.

MongoDB nhóm những phép đo có metaField phù hợp và timestamp gần nhau vào các **bucket**. Một bucket có thể chứa cả phép đo cũ đã vượt ngưỡng TTL lẫn phép đo mới vẫn còn trong retention window.

Vì MongoDB dọn **bucket đã hết hạn**, một measurement không nhất thiết bị loại bỏ ngay khi tuổi của riêng nó đạt R giây. **Bucket chỉ đủ điều kiện xóa khi mọi measurement bên trong đã quá hạn theo chính sách.**

### 5.1. Ví dụ một bucket với ba phép đo

Giả sử:

~~~text
TTL: 1 giờ = 3600 giây
Bucket A gồm phép đo cùng sensor:

A1: 10:00:00
A2: 10:20:00
A3: 10:50:00
~~~

Về mặt điều kiện tuổi riêng:

~~~text
A1: eligible từ 11:00:00
A2: eligible từ 11:20:00
A3: eligible từ 11:50:00
~~~

Ở thời điểm **11:30:00**:

- A1 đã đủ 1 giờ 30 phút tuổi.
- A2 đã đủ 1 giờ 10 phút tuổi.
- A3 mới 40 phút tuổi.

Do A3 chưa hết hạn, bucket A **chưa đủ điều kiện xóa toàn bộ**. A1 và A2 có thể vẫn thấy trong collection dù tuổi riêng của chúng vượt retention.

Sau **11:50:00**, mọi phép đo trong ví dụ đều đã vượt ngưỡng 1 giờ. Bucket bắt đầu có thể được TTL xử lý ở vòng dọn nền tiếp theo, tùy metadata bucket và cơ chế nội bộ.

**Đây là ví dụ khái niệm**, không cam kết MongoDB luôn đặt ba timestamp này vào chung một bucket vật lý. Mục đích là minh họa vì sao expiration theo bucket có thể trễ hơn expiration theo từng measurement.

### 5.2. Mốc trên của bucket

Ở mức khái niệm:

~~~text
bucket.minTime = 10:00
bucket.maxTime = 10:50
TTL = 1 giờ

Bucket chưa thể hết hạn trước khi measurement mới nhất
trong bucket đã vượt TTL.
~~~

MongoDB có thể dùng metadata về **giới hạn thời gian của bucket** để quyết định khả năng hết hạn; các chi tiết về upper boundary và thời gian giữ thêm phụ thuộc granularity/cấu hình bucket của phiên bản.

Một công thức trực giác:

\[
 t_{\text{bucket eligible}} \gtrsim t_{\text{latest measurement}} + R
\]

Dấu ở đây nhấn mạnh mốc xét thực tế có thể phụ thuộc **giới hạn thời gian của bucket**, không phải chỉ lấy trực tiếp max(timestamp) của một document do ứng dụng nhìn thấy rồi dự đoán lịch dọn chính xác đến giây.

### 5.3. TTL monitor chạy nền

MongoDB có **TTL monitor** (background task) để xử lý dữ liệu quá hạn. Tài liệu MongoDB mô tả chu kỳ kiểm tra thông thường **khoảng 60 giây**, nhưng:

- Đây **không phải** một lịch hẹn xóa đúng từng document tại giây thứ 60.
- Nếu TTL monitor đang xử lý lượng dữ liệu lớn, nó có thể cần nhiều lượt.
- Nếu node bận hoặc hệ thống đang failover, độ trễ xóa có thể lớn hơn.
- Với time series, measurement còn phải chờ bucket đủ điều kiện.

Timeline minh họa:

~~~text
Measurement cuối bucket đủ tuổi
           |
           v
Bucket bắt đầu đủ điều kiện hết hạn
           |
           v
TTL monitor chọn bucket ở vòng làm việc
           |
           v
MongoDB xóa bucket theo cơ chế nội bộ
           |
           v
Query không còn trả các phép đo trong bucket
~~~

Điều kiện đủ tuổi và thời điểm xóa thực tế là **hai mốc khác nhau**.

### 5.4. Vì sao query nên lọc thời gian ngay cả khi đã bật TTL?

Nếu API yêu cầu “lấy dữ liệu của 24 giờ vừa qua”, dùng:

~~~javascript
const since = new Date(Date.now() - 24 * 3600 * 1000);

db.sensorReadings7d.find({
  timestamp: { $gte: since }
});
~~~

Query xác định khoảng thời gian theo **yêu cầu hiển thị**. TTL quản lý **dung lượng lưu trữ và vòng đời dữ liệu**. Dữ liệu lớn tuổi hơn R vẫn có thể tồn tại trong một khoảng sau khi đạt ngưỡng, nên không thể coi TTL là điều kiện lọc chính xác ở mọi thời điểm.

### 5.5. TTL không phải lịch chạy báo cáo

Không nên dùng “bucket bị TTL xóa” làm tín hiệu chắc chắn rằng:

- Một ngày lịch vừa kết thúc.
- Toàn bộ sensor đã gửi đủ dữ liệu.
- Báo cáo ngày đã hoàn tất.
- Có thể bỏ qua việc kiểm tra dữ liệu đến trễ.

Tạo báo cáo cần quy trình riêng với **event-time windows, watermark, độ trễ chấp nhận được, job status và khả năng chạy lại**.

## 6. Granularity ảnh hưởng khoảng bucket và thời gian dọn

Khi tạo time series collection, tùy chọn **granularity** ảnh hưởng đến cách MongoDB tổ chức phép đo vào các bucket thời gian.

Theo mô hình granularity phổ biến của MongoDB:

| granularity | Khoảng thời gian tối đa một bucket có thể bao phủ theo cấu hình chuẩn |
|---|---|
| **seconds** (mặc định) | Khoảng **1 giờ** |
| **minutes** | Khoảng **24 giờ** |
| **hours** | Khoảng **30 ngày** |

Đây là **giới hạn phạm vi bucket theo cấu hình chuẩn**, không phải nghĩa rằng mọi bucket luôn có kích thước thời gian đúng bằng khoảng đó. MongoDB có thể đóng bucket sớm hơn vì những điều kiện khác như kích thước hoặc metadata.

### 6.1. Vì sao granularity lớn có thể khiến xóa trễ hơn?

Giả sử collection có TTL 24 giờ:

~~~text
granularity = "seconds"
  các measurement trong một bucket có phạm vi thời gian hẹp hơn

granularity = "hours"
  một bucket có thể bao phủ phạm vi thời gian dài hơn
~~~

Nếu bucket có dữ liệu ở đầu và cuối một dải rất dài, phép đo cũ cần chờ phép đo mới trong cùng bucket hết hạn. Vì thế, **retention nhìn thấy từ query có thể lớn hơn mức TTL riêng của measurement** khi bucket span lớn.

Không nên chọn **granularity: "hours"** chỉ vì muốn index nhỏ hơn rồi mặc định dữ liệu sẽ biến mất chính xác 24 giờ sau mỗi phép đo. Granularity cần phù hợp **tần suất lấy mẫu, query pattern, kích thước bucket và SLA xóa**.

### 6.2. Granularity không phải retention period

Hai giá trị này độc lập:

~~~javascript
db.createCollection("granularityDemo", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "minutes"
  },
  expireAfterSeconds: 604800
});
~~~

Trong ví dụ:

- **granularity: "minutes"** định hướng cấu trúc bucket.
- **expireAfterSeconds: 604800** đặt retention 7 ngày.

Không có nghĩa granularity minutes khiến dữ liệu tự hết hạn sau một phút.

### 6.3. Thay đổi granularity sau khi đã có dữ liệu

Một số phiên bản MongoDB cho phép **tăng** granularity theo hướng khoảng bucket dài hơn bằng **collMod**:

~~~javascript
db.runCommand({
  collMod: "granularityDemo",
  timeseries: {
    granularity: "hours"
  }
});
~~~

Không nên coi đây là một tùy chọn có thể tăng/giảm tùy ý như TTL. Các giới hạn thay đổi granularity và bucket settings phụ thuộc phiên bản; trong nhiều trường hợp **không thể giảm granularity** chỉ bằng một collMod ngược lại.

Trước khi thay đổi, cần hiểu hậu quả lên bucketing, vận hành và độ trễ hết hạn của dữ liệu. **Đây là thay đổi cấu trúc collection**, không phải cách ngắn gọn để sửa chính sách retention.

### 6.4. Custom bucket span và cấu hình phiên bản mới

Trong những phiên bản hỗ trợ custom bucketing, time series collection có thể sử dụng:

- **bucketMaxSpanSeconds**
- **bucketRoundingSeconds**

thay cho granularity mặc định, theo các ràng buộc và giá trị hợp lệ của phiên bản.

Ví dụ một cấu hình minh họa trên server có hỗ trợ:

~~~javascript
db.createCollection("customBucketReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    bucketMaxSpanSeconds: 3600,
    bucketRoundingSeconds: 3600
  },
  expireAfterSeconds: 86400
});
~~~

Ở đây khoảng bucket được cấu hình tường minh thay vì dùng **granularity**. Một số phiên bản yêu cầu hai giá trị custom span/rounding thỏa điều kiện bằng nhau và giới hạn nhất định.

**Không khai báo đồng thời granularity và custom bucketing** nếu phiên bản không hỗ trợ tổ hợp ấy. Trước khi sử dụng trên production, xác nhận phiên bản MongoDB và feature compatibility tương ứng.

### 6.5. Cần SLA xóa chính xác thì sao?

Nếu ứng dụng có ràng buộc “dữ liệu không được phép truy xuất sau chính xác 24 giờ”:

- TTL time series **không nên là hàng rào truy cập duy nhất**.
- Cần filter timestamp cho các truy vấn phục vụ dữ liệu.
- Nếu cần xóa vật lý nghiêm ngặt theo deadline, phải thiết kế và kiểm chứng quy trình riêng đáp ứng SLA; TTL nền theo bucket không cung cấp lời hứa xóa đúng từng giây.
- Cần quản lý cả backup, replica, export và retention của những hệ thống liên quan.

Một hạn xóa theo pháp lý có thể cần tiêu chuẩn khác với “TTL 24h để tiết kiệm ổ đĩa”. Đừng dùng cùng một tiêu chí nghiệm thu cho hai mục đích.

## 7. TTL của time series khác TTL index trên collection thường

MongoDB hỗ trợ TTL cho **collection thông thường** thông qua **TTL index** trên field Date phù hợp:

~~~javascript
db.normalEvents.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

Với time series collection, cách phổ biến là thiết lập **expireAfterSeconds ở tùy chọn collection**:

~~~javascript
db.createCollection("readings24h", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 86400
});
~~~

### 7.1. Bảng so sánh

| Tiêu chí | Collection thường với TTL index | Time series với retention |
|---|---|---|
| Cách cấu hình phổ biến | createIndex trên field Date | expireAfterSeconds khi createCollection/collMod |
| Dữ liệu hết hạn | Document có field Date đạt ngưỡng | Measurement theo timeField; bucket đủ điều kiện mới bị xóa |
| Lựa chọn thời điểm riêng mỗi record | Có thể dùng Date cụ thể và expireAfterSeconds: 0 | Collection-level policy dùng một khoảng TTL áp lên timeField |
| Độ trễ xóa | TTL monitor nền; không tức thì | TTL monitor nền **và** chờ bucket hết hạn |
| Mục tiêu tối ưu | Nhiều loại document | Phép đo theo chuỗi thời gian |
| Chỉ một nhóm dữ liệu có TTL khác | Partial TTL index theo điều kiện hỗ trợ | Partial TTL theo metaField ở phiên bản hỗ trợ |
| Xóa khối lượng lớn | Tùy lượng document và index | Có thể xóa theo bucket, nhưng vẫn phải tính backlog/tài nguyên |

### 7.2. Không tạo compound TTL index tùy ý

TTL index thông thường có những hạn chế về **kiểu index và field**. Không nên viết:

~~~javascript
// Không phải cách hợp lệ để định nghĩa TTL cho hai field:
db.normalEvents.createIndex(
  { sensorId: 1, createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

Đối với cơ chế TTL index MongoDB, **TTL dùng index một field**, không phải compound TTL index tùy ý. Nếu cần lọc theo metadata và time, hãy phân biệt **index truy vấn** với **TTL policy/index**, hoặc dùng partial TTL hợp lệ trong phiên bản hỗ trợ.

### 7.3. TTL index không thay schema validation

Nếu field Date của collection thường bị lưu thành String, việc TTL index không thể thực hiện xóa theo ý định như với BSON Date. Time series collection cũng cần **timeField đúng kiểu**.

Giải pháp là kiểm soát kiểu dữ liệu từ lúc ghi, thống nhất timezone và có các quy tắc validation/migration. TTL không tự sửa timestamp sai hoặc chuyển String thành Date.

## 8. Bật TTL cho time series collection đã tồn tại

Một time series collection có thể ban đầu được tạo **không có expiration policy**:

~~~javascript
use timeseries_ttl_lab

db.createCollection("sensorReadingsNoTTL", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});
~~~

Nếu sau đó doanh nghiệp quyết định chỉ giữ raw measurements 30 ngày, có thể sử dụng **collMod**:

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 2592000
});
~~~

Trong lệnh:

- **collMod** xác định collection cần đổi thuộc database đang chọn.
- **expireAfterSeconds** là số giây retention.
- Chính sách áp dụng cho **timeField** của time series collection.

### 8.1. CollMod trên collection khác việc sửa TTL index

Đối với time series **collection-level TTL**, dùng:

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 2592000
});
~~~

Đối với TTL index trên collection thường, thay đổi expireAfterSeconds của **index** sử dụng tham số **index** trong collMod:

~~~javascript
db.runCommand({
  collMod: "normalEvents",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 7200
  }
});
~~~

Hai cú pháp này phục vụ **hai loại cấu hình khác nhau**. Không nên dùng cú pháp sửa index để thay retention toàn collection time series và mặc định nó sẽ điều chỉnh đúng tùy chọn mong muốn.

### 8.2. Kích hoạt TTL không xóa đồng bộ toàn bộ lịch sử

Nếu collection đã có dữ liệu hai năm và bạn bật retention 30 ngày:

~~~text
Dữ liệu trước 30 ngày: có thể bắt đầu đủ điều kiện xóa
Bucket chứa cả dữ liệu mới: có thể chưa đủ điều kiện
TTL monitor: xóa dần những bucket đủ điều kiện
~~~

Lệnh collMod thành công **không có nghĩa mọi dữ liệu quá hạn đã được xóa ngay trước khi command trả về**.

Với dữ liệu lớn, đột ngột bật retention ngắn có thể tạo **TTL backlog**, làm tăng I/O và tạo ảnh hưởng đến query latency. Cần có phương án rollout, quan sát tốc độ dọn và xác nhận trước khi áp dụng lên hệ thống thực.

### 8.3. Thời gian dùng để xét vẫn là timeField gốc

Ví dụ record được insert hôm nay nhưng timestamp của nó là ba tháng trước:

~~~javascript
db.sensorReadingsNoTTL.insertOne({
  timestamp: new Date(Date.now() - 90 * 24 * 3600 * 1000),
  sensor: {
    sensorId: "S-OLD",
    retentionClass: "STANDARD"
  },
  temperatureC: 25.0
});
~~~

Nếu retention mới là 30 ngày, measurement này đã quá tuổi theo **event timestamp**. Không có “30 ngày giữ thêm” tự động tính từ lúc bản ghi được import.

Nếu nghiệp vụ cần backfill dữ liệu lịch sử để chạy báo cáo, nên có chiến lược import/archive phù hợp chứ không tạm kỳ vọng TTL ngừng hoạt động chỉ vì dữ liệu vừa được insert.

## 9. Thay đổi thời gian giữ bằng collMod

Chính sách dữ liệu có thể thay đổi khi dung lượng tăng, nhu cầu phân tích đổi hoặc quy định lưu trữ được cập nhật.

### 9.1. Tăng TTL từ 7 ngày lên 30 ngày

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: 2592000
});
~~~

**Tăng TTL chỉ ảnh hưởng dữ liệu còn tồn tại**. Nó **không khôi phục** các bucket đã bị xóa theo retention 7 ngày trước đó. Nếu cần dữ liệu cũ, bạn phải có nguồn sao lưu/archival hợp lệ.

### 9.2. Giảm TTL từ 30 ngày xuống 7 ngày

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 604800
});
~~~

Đây có thể là thay đổi có tác động lớn hơn nhiều:

~~~text
Trước thay đổi:
  30 ngày dữ liệu đang được giữ

Sau thay đổi:
  chỉ 7 ngày thuộc retention mong muốn

Hệ quả:
  lượng bucket chứa dữ liệu từ ngày 8 đến ngày 30
  có thể trở thành ứng viên hết hạn trong thời gian ngắn
~~~

Khi làm trên production:

1. Xác nhận đã hết yêu cầu giữ dữ liệu cũ.
2. Hoàn thành/archive/downsample dữ liệu cần thiết.
3. Đo lượng dữ liệu sẽ đủ điều kiện hết hạn.
4. Chọn thời điểm thay đổi ít ảnh hưởng workload.
5. Quan sát TTL monitor, I/O, disk usage, replication lag và query latency.
6. Có kế hoạch phục hồi từ backup trong phạm vi chính sách.

Không nên coi việc đổi expireAfterSeconds chỉ là một tùy chỉnh nhỏ như thay timeout của request API.

### 9.3. Tắt automatic expiration

Trong các phiên bản MongoDB hỗ trợ, có thể tắt TTL ở cấp time series collection bằng:

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: "off"
});
~~~

Đây là **chuỗi đặc biệt "off"**, khác với số 0.

**expireAfterSeconds: 0** có ý nghĩa dữ liệu đủ điều kiện hết hạn khi thời điểm timeField đã đến hoặc đã qua, chứ **không phải tắt TTL**.

Sau khi tắt, dữ liệu chưa bị xóa do chính sách collection-level TTL sẽ được giữ lại, nhưng **bucket đã bị xóa trước đó không tự khôi phục**. Nếu collection còn một **partial TTL index** có chính sách riêng, cần xem xét index đó: tắt collection-level TTL không đương nhiên tắt những TTL indexes khác.

### 9.4. Bật lại sau khi tắt

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: 604800
});
~~~

Nếu đã tắt TTL trong thời gian dài, bật lại có thể tạo một đợt xóa lớn. Cần lập kế hoạch tương tự trường hợp giảm retention.

### 9.5. Kiểm tra chính sách đang có

Một cách đọc metadata collection:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: {
    name: "sensorReadings7d"
  }
});
~~~

Trong output, quan sát:

~~~javascript
{
  name: "sensorReadings7d",
  type: "timeseries",
  options: {
    timeseries: {
      timeField: "timestamp",
      metaField: "sensor",
      granularity: "seconds"
    },
    expireAfterSeconds: 604800
  }
}
~~~

Đây là hình thức **rút gọn phần tử của kết quả**, không phải mọi field mà listCollections phải trả ở mọi phiên bản. Khi TTL đã tắt, cách hiển thị tùy chọn có thể thể hiện **"off"** hoặc khác theo metadata của phiên bản.

### 9.6. Truy vấn getCollectionInfos()

Trong mongosh còn có thể dùng:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

Kết quả là danh sách metadata các collection phù hợp. Xem **options.expireAfterSeconds** và **options.timeseries**, không suy ra TTL từ một document bất kỳ.

### 9.7. Không chỉnh sửa system.buckets để thay TTL

Time series collection có cấu trúc lưu trữ nội bộ thường được thể hiện qua namespace dạng **system.buckets.<collection>**. Không nên tự:

~~~javascript
// KHÔNG làm trên dữ liệu thực:
db.getCollection("system.buckets.sensorReadings7d")
  .deleteMany({});
~~~

Việc can thiệp thủ công vào bucket internals có thể phá vỡ giả định của cơ chế time series. Quản lý retention qua **API được hỗ trợ** trên **collection logic**, không tự sửa/xóa các bucket nội bộ để “làm TTL chạy nhanh”.

## 10. Partial TTL index: giữ thời gian khác nhau theo metadata

Một yêu cầu thường gặp:

~~~text
Mọi sensor:
  raw readings giữ 7 ngày

Nhóm sensor TEST:
  raw readings chỉ giữ 1 ngày
~~~

Ở MongoDB **7.0 trở lên** và những phiên bản hỗ trợ tính năng tương ứng, có thể tạo **partial TTL index** trên time series collection để áp dụng TTL ngắn hơn cho **những measurement khớp điều kiện metaField**.

### 10.1. Vì sao cần partial TTL?

Giả sử tạo collection:

~~~javascript
db.createCollection("readingsByClass", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

Collection-level TTL: **mọi measurement** có retention cơ sở **7 ngày**.

Muốn sensor thuộc retentionClass **SHORT** hết hạn sớm hơn, ta thêm partial TTL index:

~~~javascript
db.readingsByClass.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_short_class_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "sensor.retentionClass": "SHORT"
    }
  }
);
~~~

Điểm quan trọng:

- Key của TTL index là **timeField: timestamp**.
- **expireAfterSeconds: 86400** xác định TTL 1 ngày cho subset.
- **partialFilterExpression** chỉ tham chiếu **metaField hoặc các subfield hợp lệ của nó**.
- Collection-level TTL 7 ngày vẫn áp dụng cho những measurement khác.

### 10.2. Dữ liệu minh họa

~~~javascript
db.readingsByClass.insertMany([
  {
    timestamp: new Date(),
    sensor: {
      sensorId: "S-TEST",
      site: "LAB",
      retentionClass: "SHORT"
    },
    temperatureC: 22.5
  },
  {
    timestamp: new Date(),
    sensor: {
      sensorId: "S-PROD",
      site: "HCM",
      retentionClass: "STANDARD"
    },
    temperatureC: 28.5
  }
]);
~~~

Về chính sách:

| Measurement | Giá trị metadata | TTL hiệu lực theo cấu hình |
|---|---|---|
| S-TEST | retentionClass = SHORT | 1 ngày |
| S-PROD | retentionClass = STANDARD | 7 ngày |

Lưu ý đây là **ngưỡng đủ điều kiện**, không cam kết measurement S-TEST bị xóa chính xác sau một ngày nếu bucket chứa nó còn measurement chưa hết hạn theo quy tắc tương ứng.

### 10.3. Partial TTL không cho phép giữ dài hơn TTL toàn collection

Giả sử collection-level TTL = 7 ngày, nhưng partial TTL index cho nhóm **PREMIUM** dùng 30 ngày:

~~~javascript
// Cấu hình không mang lại 30 ngày retention nếu
// collection-level TTL vẫn xóa sau 7 ngày.
db.readingsByClass.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_premium_30d",
    expireAfterSeconds: 2592000,
    partialFilterExpression: {
      "sensor.retentionClass": "PREMIUM"
    }
  }
);
~~~

**Không thể dùng TTL dài hơn trong partial index để vượt qua collection-level TTL ngắn hơn**. Collection-level 7 ngày vẫn làm các bucket phù hợp đủ điều kiện xóa trước khi đạt 30 ngày.

Muốn có policy:

~~~text
SHORT    -> 1 ngày
STANDARD -> 7 ngày
PREMIUM  -> 30 ngày
~~~

hãy thiết kế:

- Collection-level TTL = **30 ngày**, partial TTL ngắn hơn cho SHORT và STANDARD nếu phiên bản/index hỗ trợ, hoặc
- Tách thành các collection riêng với TTL khác nhau.

Không chọn collection-level TTL ngắn nhất rồi kỳ vọng các partial index làm một phần dữ liệu sống lâu hơn.

### 10.4. Partial TTL có thể dùng khi collection chưa có TTL toàn cục

Một time series collection không bật expireAfterSeconds vẫn có thể dùng partial TTL index theo metadata trên các phiên bản được hỗ trợ:

~~~javascript
db.createCollection("mixedRetention", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});

db.mixedRetention.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_test_sensors_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "sensor.retentionClass": "SHORT"
    }
  }
);
~~~

Trong ví dụ, measurement khớp SHORT mới thuộc chính sách TTL của partial index; các measurement khác **không có collection-level expiration được khai báo**.

Điều này có thể phù hợp nếu chỉ một nhóm dữ liệu thử nghiệm cần tự hết hạn, còn dữ liệu khác phải được quản lý bằng một chính sách riêng.

### 10.5. Tại sao filter chỉ dựa trên metaField?

Partial TTL trên time series có ràng buộc: filter phải dựa trên **metaField**. Không thể tùy ý tạo TTL theo measurement field:

~~~javascript
// KHÔNG phải partial TTL hợp lệ để diễn đạt
// một chính sách dựa trên giá trị đo:
partialFilterExpression: {
  temperatureC: { $gt: 40 }
}
~~~

Nhiệt độ là **measurement field**, không phải metadata của series. Nếu cần retention theo loại dữ liệu, hãy gắn **phân loại ổn định vào metaField** từ lúc ghi hoặc tách collection.

Không nên sửa metaField chỉ để né giới hạn nếu điều đó làm thay đổi ý nghĩa series hoặc gây tăng cardinality/kích thước bucket.

### 10.6. Cẩn thận khi dùng nhiều partial TTL indexes

Nếu một measurement khớp nhiều chính sách TTL, cơ chế hết hạn ngắn hơn có thể khiến dữ liệu bị xóa trước khi chính sách dài hơn có ý nghĩa. Hãy tránh thiết kế filter chồng lấn không chủ ý:

~~~text
Policy A: sensor.site = LAB -> 1 ngày
Policy B: sensor.retentionClass = STANDARD -> 7 ngày

Một sensor ở LAB nhưng retentionClass STANDARD
khớp cả hai chính sách.
~~~

Nên xác định rõ **thứ tự ưu tiên** và tổ hợp metadata hợp lệ, hoặc tách collection để retention không mơ hồ. Trước khi thay đổi partial TTL, xem lại những indexes đã tồn tại cùng key pattern và điều kiện version.

## 11. Khi nào nên tách thành nhiều time series collections?

Không phải mọi hệ thống đều nên quản lý retention đa tầng bằng một collection và nhiều partial TTL indexes.

Giả sử ba loại sensor:

| Nhóm | Retention | Tần suất đo | Nhu cầu |
|---|---:|---|---|
| TEST | 1 ngày | 1 giây/lần | Debug ngắn hạn |
| PRODUCTION | 30 ngày | 10 giây/lần | Vận hành hiện tại |
| REGULATED | 365 ngày | 1 phút/lần | Lưu giữ theo chính sách |

Có hai hướng triển khai:

### 11.1. Một collection, nhiều chính sách

~~~text
sensorReadings
  collection TTL: 365 ngày
  partial TTL TEST: 1 ngày
  partial TTL PRODUCTION: 30 ngày
  REGULATED: áp dụng 365 ngày
~~~

Ưu điểm:

- Query và mô hình dữ liệu tập trung.
- Một namespace để quản lý việc đọc.
- Dễ viết aggregation cho nhiều nhóm nếu đủ metadata.

Nhược điểm:

- Partial TTL phải được phiên bản hỗ trợ.
- Policy chỉ theo những điều kiện metaField được phép.
- Index và bucket organization có thể phức tạp.
- Rủi ro cấu hình filter chồng lấn hoặc thay đổi metadata.

### 11.2. Nhiều collection theo retention class

~~~text
testReadings1d          -> TTL 1 ngày
productionReadings30d   -> TTL 30 ngày
regulatedReadings365d   -> TTL 365 ngày
~~~

Ưu điểm:

- Chính sách retention của từng collection dễ đọc từ metadata.
- Giảm nhu cầu partial TTL phức tạp.
- Dễ bố trí tài nguyên và quy trình vận hành riêng cho các nhóm.

Nhược điểm:

- Ứng dụng phải chọn đúng namespace khi ghi.
- Query phân tích toàn bộ nhóm có thể cần gom dữ liệu nhiều collection.
- Cần quản lý schema, index và migration nhất quán.

Lựa chọn phụ thuộc **query pattern**, số retention classes, phiên bản MongoDB, mục tiêu dung lượng và yêu cầu cô lập. Đừng chuyển sang nhiều collection chỉ vì nghĩ TTL không thể dùng một collection, nhưng cũng không ép mọi chính sách phức tạp vào một partial index khó vận hành.

### 11.3. Retention theo từng measurement bất kỳ có phù hợp time series TTL?

Nếu mỗi measurement cần một **expireAt riêng**:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  expireAt: ISODate("2026-11-17T12:34:56Z")
}
~~~

thì collection-level TTL theo timestamp **không tự đọc expireAt** để chọn ngày xóa của từng phép đo.

Nếu nghiệp vụ cần thời hạn tùy ý theo từng bản ghi, hãy xem xét:

- Dùng **collection thường với TTL index trên expireAt**, nếu phù hợp khối lượng/kiểu truy vấn.
- Chia nhiều time series collection theo retention policy.
- Dùng **quy trình xóa riêng** với kiểm soát quyền và lịch phù hợp.
- Đưa retention class vào metaField khi chính sách hữu hạn và ổn định.

Không gán một Date expireAt vào measurement rồi mặc định time series TTL sẽ tự hiểu nó, trừ khi cơ chế hỗ trợ đã được cấu hình chính xác cho field đó.

## 12. Dữ liệu đến trễ (late arrival) và backfill

Hệ thống đo đạc không luôn gửi dữ liệu đúng lúc:

~~~text
10:00 Sensor ghi phép đo
10:01 Sensor mất kết nối
16:00 Sensor kết nối lại và gửi batch có timestamp 10:00
~~~

Nếu collection có TTL 4 giờ dựa trên **event timestamp**, phép đo 10:00 đã quá tuổi khi được insert lúc 16:00.

### 12.1. Ví dụ backfill dữ liệu cũ

~~~javascript
const now = new Date();
const eventTime = new Date(now.getTime() - 10 * 24 * 3600 * 1000);

db.sensorReadings7d.insertOne({
  timestamp: eventTime,
  sensor: {
    sensorId: "S-OFFLINE",
    site: "HCM-03",
    retentionClass: "STANDARD"
  },
  temperatureC: 31.5,
  receivedAt: now
});
~~~

Ở thời điểm insert, eventTime đã cũ hơn retention 7 ngày. Dữ liệu này có thể nhanh chóng trở thành ứng viên xóa khi bucket liên quan đủ điều kiện và TTL monitor xử lý.

**receivedAt mới không kéo dài TTL**, vì timeField đã được khai báo là timestamp. receivedAt chỉ là một measurement/field bổ sung trừ khi thiết kế collection khác.

### 12.2. Hai cách hiểu retention khác nhau

| Chính sách | Mốc bắt đầu | Ý nghĩa |
|---|---|---|
| Event-time retention | timestamp của phép đo | Giữ dữ liệu thuộc 7 ngày sự kiện gần nhất |
| Ingest-time retention | thời điểm server nhận | Giữ tối thiểu 7 ngày kể từ lúc nhận dữ liệu |

Hai cách có thể cho kết quả khác nhau khi dữ liệu đến trễ.

**Event-time retention** phù hợp nhiều truy vấn thống kê theo thời gian đo, nhưng có thể xóa ngay những bản ghi backfill quá cũ. **Ingest-time retention** giữ dữ liệu vừa nhập lâu hơn, nhưng thời gian trên trục time series khi đó phản ánh lúc nhận, không nhất thiết lúc sensor đo.

Không nên đổi định nghĩa timeField giữa chừng mà không xem lại toàn bộ truy vấn và phép tính thời gian.

### 12.3. Thiết kế cho batch import lịch sử

Nếu cần import sáu tháng dữ liệu gốc để tính một báo cáo nhưng collection raw giữ bảy ngày, có thể:

1. Import vào **collection staging riêng không có TTL ngắn**.
2. Chạy aggregation/downsampling từ staging.
3. Ghi output vào collection tổng hợp với retention riêng.
4. Đối chiếu số lượng và độ bao phủ dữ liệu.
5. Xóa staging theo lịch được phê duyệt.

Phương án này tránh cuộc đua giữa **backfill** và **TTL monitor** trên collection raw.

### 12.4. Dữ liệu đến sớm hoặc timestamp trong tương lai

Một thiết bị có clock bị lệch có thể gửi:

~~~javascript
{
  timestamp: ISODate("2035-01-01T00:00:00Z"),
  sensor: { sensorId: "S-BADCLOCK" },
  temperatureC: 28.0
}
~~~

Nếu timestamp vượt xa thời điểm thực, measurement có thể không đủ điều kiện hết hạn theo TTL trong một thời gian rất dài; nó cũng có thể làm lệch bucket organization và query theo thời gian.

**Không tin tuyệt đối clock của thiết bị** khi retention có yêu cầu vận hành nghiêm ngặt. Cần:

- Kiểm tra timestamp nằm trong miền hợp lệ so với server time.
- Xác định mức sai lệch tối đa chấp nhận được.
- Ghi nhận receivedAt để chẩn đoán.
- Có quy trình xử lý thiết bị clock bị lỗi.
- Xác định rõ trường hợp dữ liệu tương lai có bị từ chối hay chuyển vào quarantine.

### 12.5. Timestamp quá cũ hoặc quá xa miền hỗ trợ

Một số phiên bản MongoDB có giới hạn/đặc điểm TTL riêng cho time series khi timestamp nằm ngoài khoảng thời gian được hỗ trợ bởi cơ chế bucket/TTL của phiên bản. Không nên mặc định mọi giá trị Date trong quá khứ rất xa hoặc tương lai cực xa sẽ được TTL xử lý giống giá trị ngày giờ hiện tại.

Thiết kế dữ liệu sensor nên có **miền timestamp thực tế** và xác minh tương thích phiên bản khi nhập dữ liệu lịch sử đặc biệt.

### 12.6. Chênh lệch đồng hồ server

TTL monitor cần mốc thời gian để xét expiration, còn sensor cung cấp event time. Nếu đồng hồ node/backend/thiết bị lệch lớn, nhiều measurement có thể bị xóa quá sớm hoặc giữ quá lâu so với ý định.

Nên đồng bộ thời gian hạ tầng và giám sát clock skew; không tự điều chỉnh bằng cách cộng thêm một khoảng ngẫu nhiên vào timestamp mà không có chính sách rõ ràng.

## 13. Các nhầm lẫn về “24 giờ” và “ngày lịch”

TTL theo giây là thời lượng tuyệt đối. Nhưng nhiều yêu cầu phân tích báo cáo sử dụng **ngày địa phương**.

### 13.1. TTL 86400 không nhất thiết là “hết ngày mai”

Ví dụ một measurement lúc:

~~~text
2026-11-14T10:15:00Z
~~~

Với TTL 86400, nó bắt đầu đủ điều kiện sau đúng **24 giờ**:

~~~text
2026-11-15T10:15:00Z
~~~

Nó không đợi đến **23:59:59 ngày 15/11 theo Asia/Ho_Chi_Minh**, cũng không gắn với ngày đóng báo cáo của từng site.

### 13.2. Một ngày địa phương có thể dài 23 hoặc 25 giờ

Các vùng có DST, chẳng hạn America/New_York, có ngày chỉ dài **23 giờ** hoặc **25 giờ** khi chuyển giờ mùa hè. Một chính sách “giữ đúng 48 giờ” là khác với “giữ cho tới cùng giờ địa phương sau hai ngày lịch”.

Nếu cần retention theo **ngày lịch tại địa điểm kinh doanh**, TTL đơn giản theo expireAfterSeconds có thể không đủ để diễn đạt chính sách; cần tính khoảng ngày và quản lý dữ liệu theo thiết kế thích hợp.

### 13.3. Báo cáo theo ngày và TTL theo giờ cùng tồn tại được

Có thể:

- Query raw readings theo **[startOfLocalDay, nextLocalDay)** đã đổi ra UTC.
- Tổng hợp một ngày local vào collection hourly/daily.
- Đặt TTL raw theo số giây để dọn lưu trữ.

Hai công việc không mâu thuẫn, miễn **retention raw đủ dài** để các báo cáo theo ngày và job chạy lại hoàn tất.

### 13.4. Không thay thời gian của sensor bằng giờ địa phương dạng String

Thay vì:

~~~javascript
{ timestamp: "14/11/2026 17:00" }
~~~

nên lưu BSON Date tương ứng với thời điểm UTC và giữ timezone của sensor/site ở metadata nếu cần hiển thị hoặc thống kê theo ngày địa phương:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  sensor: {
    sensorId: "S-101",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Việc này giúp TTL tính tuổi từ một thời điểm rõ ràng, đồng thời report có đủ thông tin để xác định ranh giới ngày địa phương.

## 14. TTL không phải hệ thống archive hoặc downsampling

Một quan niệm sai:

> Bật TTL 7 ngày thì MongoDB tự chuyển dữ liệu gốc thành bản tổng hợp 7 ngày, rồi xóa raw.

MongoDB TTL **chỉ chịu trách nhiệm hết hạn/xóa**, không tự sinh bản tổng hợp như min/max/avg hoặc chuyển dữ liệu sang kho archive.

### 14.1. Kiến trúc lưu dữ liệu nhiều tầng

~~~text
Sensor / Metrics SDK
         |
         v
Raw time series collection
  TTL 7 ngày
         |
         +----------> Real-time dashboard (7 ngày gần nhất)
         |
         v
Aggregation pipeline / job theo lịch
         |
         v
Hourly aggregates collection
  TTL 90 ngày
         |
         v
Daily aggregates / object storage
  Retention dài hạn theo chính sách
~~~

Đây là một kiến trúc tham khảo. Không phải mọi tổ chức cần đủ ba tầng, nhưng nếu có các nhu cầu truy vấn ngắn/trung/dài hạn, tách cấp độ dữ liệu thường giúp cân bằng lưu trữ và hiệu năng.

### 14.2. Một pipeline tổng hợp theo giờ

Giả sử collection raw chứa:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:05:00Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01"
  },
  temperatureC: 28.4
}
~~~

Một aggregation tính trung bình/min/max/count theo sensor và giờ UTC:

~~~javascript
db.sensorReadings7d.aggregate([
  {
    $match: {
      timestamp: {
        $gte: ISODate("2026-11-14T00:00:00Z"),
        $lt: ISODate("2026-11-15T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensor.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$timestamp",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      minTemperatureC: { $min: "$temperatureC" },
      maxTemperatureC: { $max: "$temperatureC" },
      avgTemperatureC: { $avg: "$temperatureC" }
    }
  },
  {
    $sort: {
      "_id.sensorId": 1,
      "_id.hourStart": 1
    }
  }
]);
~~~

Pipeline này chỉ **trả kết quả tổng hợp**; nó chưa tự lưu hourly aggregates. Để lưu bền vững có thể sử dụng **$merge**, ứng dụng ghi kết quả vào collection khác hoặc workflow chuyên dụng, với điều kiện vận hành và unique business key phù hợp.

### 14.3. Tại sao không tổng hợp sau khi TTL đã xóa?

Nếu job chỉ chạy khi dữ liệu gốc đã bị TTL loại bỏ, không thể tái dựng min/max/avg đầy đủ từ collection raw nữa.

Vì vậy cần:

- Chạy tổng hợp **trước thời hạn xóa raw**.
- Cho phép buffer cho data latency và job retry.
- Theo dõi watermark hoặc ngày/giờ đã xử lý đầy đủ.
- Lưu thông tin **đã tổng hợp thành công**.
- Có nguồn khôi phục nếu muốn chạy lại sau khi raw hết hạn.

### 14.4. Cần idempotency cho job tổng hợp

Nếu job hourly chạy lại vì timeout, nó không nên append kết quả giờ đó thành một document mới ngoài ý muốn.

Một khóa logic phù hợp:

~~~text
(sensorId, hourStart)
~~~

Có thể sử dụng **upsert/merge có khóa rõ** hoặc unique index trong collection tổng hợp thông thường. Nếu dữ liệu tổng hợp lưu trong time series collection, cần xem các hạn chế index/unique của time series thay vì mặc định có thể tạo mọi unique index.

### 14.5. Archive và backup khác nhau

**Archive** thường là dữ liệu được giữ để truy vấn/khôi phục theo retention đã định; **backup** là bản sao giúp khôi phục sau sự cố. TTL xóa dữ liệu khỏi collection đang chạy **không đồng nghĩa xóa mọi byte của dữ liệu khỏi mọi backup**.

Khi chính sách yêu cầu xóa dữ liệu vĩnh viễn theo thời hạn, cần kiểm soát **backup retention, snapshots, exports, analytical copies và log** riêng. Không trình bày TTL database như một giải pháp legal erasure hoàn chỉnh.

## 15. Quan sát TTL monitor và dữ liệu quá hạn

Vì TTL chạy không đồng bộ, không nên chỉ xem **giá trị expireAfterSeconds** rồi kết luận hệ thống đang dọn dữ liệu đúng tốc độ. Cần theo dõi **backlog, số bucket/measurement còn quá tuổi, tài nguyên đĩa và trạng thái node**.

### 15.1. Xem các metric TTL của MongoDB

Với quyền phù hợp, trong mongosh:

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Tùy phiên bản, trường **metrics.ttl** có thể chứa:

- **deletedDocuments**: số document bị cơ chế TTL xóa theo thống kê server.
- **passes**: số vòng xử lý TTL đã hoàn tất.
- **subPasses**: số vòng con xử lý TTL.
- Các trường bổ sung phản ánh thời gian, examined documents hoặc keys, tùy phiên bản.

Các bộ đếm này thường là **cumulative counters theo node và thời gian hoạt động**, không phải số measurement còn lại trong một collection cụ thể. Với time series, phép xóa có thể thao tác trên bucket storage, nên **không lấy deletedDocuments làm số lượng cảm biến reading đã bị xóa trong một ngày** nếu chưa hiểu định nghĩa metric ở phiên bản đang chạy.

### 15.2. Không đồng nhất passes tăng với mọi dữ liệu đã sạch

Giả sử TTL monitor có pass mới, nhưng một sensor bucket vẫn chứa reading chưa hết hạn:

~~~text
TTL monitor active: yes
Bucket has expired + unexpired measurements: yes
Eligible for whole-bucket deletion: no
~~~

Khi đó đọc thấy measurement cũ **chưa chắc là lỗi TTL monitor**. Cần phân biệt **dữ liệu cũ do bucket chưa đủ điều kiện** và **dữ liệu đủ điều kiện nhưng monitor chưa xử lý**.

### 15.3. Ước lượng số measurement quá ngưỡng tuổi

Ví dụ kiểm tra quá 7 ngày:

~~~javascript
const cutoff = new Date(
  Date.now() - 7 * 24 * 3600 * 1000
);

db.sensorReadings7d.countDocuments({
  timestamp: { $lt: cutoff }
});
~~~

Nếu kết quả lớn hơn 0, có các measurement trên collection logic đã quá ngưỡng tuổi riêng. Nhưng điều đó **không chứng minh chúng đủ điều kiện xóa theo bucket** tại thời điểm đó.

Với collection rất lớn, việc đếm toàn bộ dữ liệu quá tuổi có thể tốn tài nguyên. Trên production có thể dùng sampling, các metric theo vùng/series hoặc một query đã được đánh giá hiệu năng, thay vì quét lớn thường xuyên chỉ để tạo dashboard.

### 15.4. Xem timestamp cũ nhất hiện còn

~~~javascript
db.sensorReadings7d.find(
  {},
  { _id: 0, timestamp: 1, sensor: 1 }
).sort({ timestamp: 1 }).limit(10);
~~~

Kết quả có thể hữu ích khi điều tra thiết bị còn giữ dữ liệu rất cũ, nhưng hiệu năng phụ thuộc index, query planner, shard layout và kích thước collection.

Không dùng giá trị **oldest timestamp** của toàn collection làm chỉ báo duy nhất cho TTL backlog: một cảm biến gửi dữ liệu trễ, một timestamp sai hoặc một bucket đặc biệt cũng có thể kéo cực trị xuống.

### 15.5. Phân biệt TTL lag và replication lag

Đây là hai khái niệm khác nhau:

| Chỉ số | Diễn tả |
|---|---|
| TTL expiration delay | Khoảng từ lúc dữ liệu/bucket đủ điều kiện hết hạn đến khi bị xóa |
| Replication lag | Khoảng chậm trễ secondary áp dụng thao tác từ primary |
| Ingestion lag | Khoảng từ lúc sensor phát sinh event đến lúc MongoDB nhận |
| Aggregation lag | Khoảng từ lúc dữ liệu đầu vào sẵn có đến lúc báo cáo/tổng hợp được cập nhật |

Một measurement có thể đã bị TTL dọn trên primary nhưng secondary chưa áp dụng thao tác xóa vì replication lag; hoặc ngược lại raw đã đến rất trễ và TTL đã coi nó cũ ngay khi insert.

Khi xem metric cần xác định đang đo **khoảng trễ nào**, tránh lấy một dashboard duy nhất để giải thích mọi loại trễ.

### 15.6. Kiểm tra cấu hình retention là gì?

Một runbook quan sát nên lấy:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

và đối chiếu:

- Collection type có thực là time series không?
- **timeField** đang là gì?
- **metaField** đang là gì?
- **granularity** hoặc custom bucket settings là gì?
- **expireAfterSeconds** đang là giá trị nào hoặc đã tắt?
- Có **partial TTL indexes** nào khác?

Không chỉ xem source code ứng dụng. Collection có thể đã bị một migration hoặc lệnh quản trị khác thay đổi TTL từ trước.

### 15.7. Liệt kê index

~~~javascript
db.sensorReadings7d.getIndexes();
~~~

Với time series collection, cấu trúc index hiển thị có thể khác collection thường theo phiên bản và cách ánh xạ chỉ mục bucket. Cần phân biệt:

- Index phục vụ query theo metaField/timeField.
- **Partial TTL index** có expireAfterSeconds và partialFilterExpression.
- Collection-level TTL ở **options.expireAfterSeconds**.

Không nên kết luận collection **không có TTL** chỉ vì không nhìn thấy một index tên “ttl_timestamp” tùy ý trong getIndexes().

## 16. TTL và ảnh hưởng lên replication, sharding và dung lượng

Time series TTL được MongoDB thực hiện bằng cơ chế server. Trong replica set, các thao tác xóa phù hợp được thực hiện qua mô hình primary và phản ánh tới các secondary theo replication.

### 16.1. Không nên kỳ vọng TTL chạy độc lập trên mọi secondary

Đối với replica set bình thường, cơ chế xóa TTL thực tế được điều phối ở **primary** theo quy tắc của MongoDB; secondary không tự tạo một chính sách xóa nghiệp vụ độc lập khác với primary để “đuổi kịp TTL” theo đồng hồ riêng.

Điều này quan trọng khi quan sát:

~~~text
Primary:   bucket quá hạn đã được xóa
Secondary: có thể chưa áp dụng thao tác xóa
~~~

Nếu đọc theo readPreference secondary ngay sau thời điểm xóa, có thể gặp bản dữ liệu khác với primary trong khoảng replication lag. Thiết kế API không nên xem TTL như một bộ lọc truy vấn real-time tuyệt đối.

### 16.2. TTL có tác động write I/O

Khi TTL xóa dữ liệu, MongoDB vẫn phải:

- Thực hiện thay đổi lưu trữ.
- Cập nhật các cấu trúc index liên quan.
- Ghi nhận thay đổi và nhân bản qua replication khi phù hợp.
- Quản lý tài nguyên bộ nhớ, đĩa và công việc nền.

Nếu thay TTL từ 365 ngày xuống 7 ngày trên một collection lớn, lượng bucket cần dọn có thể rất cao. Việc dọn đó không “miễn phí” chỉ vì được thực hiện tự động.

### 16.3. TTL và sharded time series

Trong sharded deployment có hỗ trợ time series collection, dữ liệu được phân bố trên nhiều shard theo shard key/metadata. Cơ chế TTL và các thao tác dọn diễn ra theo những phần dữ liệu do các shard quản lý.

Điều cần quan sát:

- Dữ liệu quá hạn phân bố trên những shard nào.
- Shard nào có TTL backlog lớn.
- TTL I/O có ảnh hưởng query latency theo vùng không.
- Có migration hoặc rebalance đồng thời gây áp lực không.
- Read preference có khiến API đọc một secondary chưa áp dụng xóa không.

Không nên coi **một chỉ số TTL trên một node** là cái nhìn đầy đủ về tất cả shard của cluster.

### 16.4. Dung lượng đĩa không luôn giảm ngay sau xóa

Sau khi TTL xóa nhiều bucket, hệ thống có thể có **không gian trống được storage engine tái sử dụng** mà kích thước file dữ liệu trên filesystem chưa giảm tương ứng.

Vì thế:

~~~text
Measurement count giảm
          |
          v
MongoDB có thể tái sử dụng dung lượng nội bộ
          |
          v
File data trên disk không nhất thiết co ngay
~~~

Không nên kết luận TTL không hoạt động chỉ vì biểu đồ “dung lượng file” chưa giảm tức thì. Cần phân biệt **logical data size, storage size, free/reusable storage** và cách storage engine quản lý file.

### 16.5. Xóa dữ liệu lớn có thể gây áp lực đến backup

Việc xóa hàng loạt cũng có thể ảnh hưởng:

- Tăng hoạt động oplog/replication.
- Lượng thay đổi mà backup liên tục cần theo dõi.
- Khả năng restore ở các mốc khác nhau.
- I/O trong khoảng cửa sổ bảo trì.

Một kế hoạch thay đổi retention lớn cần có đại diện vận hành/backup xem xét, không chỉ team backend.

### 16.6. TTL không thay partitioning/archive độc lập

Nếu doanh nghiệp muốn:

~~~text
Dữ liệu nóng 7 ngày trên storage nhanh
Dữ liệu 7–180 ngày trên storage rẻ
Sau 180 ngày mới xóa
~~~

thì TTL 7 ngày ở raw collection chỉ **xóa dữ liệu khỏi collection ấy**. Nó không chuyển tự động dữ liệu sang một tầng storage khác như một giải pháp archival hoàn chỉnh.

Cần thêm pipeline/export/collection tổng hợp và các SLA/kiểm soát riêng.

## 17. Thay đổi retention an toàn trên production

Một thay đổi TTL có thể gây mất dữ liệu không thể phục hồi từ collection online. Một quy trình quản trị nên nêu rõ **retention cũ, retention mới, dữ liệu bị ảnh hưởng và bằng chứng được phép xóa**.

### 17.1. Trước khi thay đổi

Thu thập:

1. **Namespace** và loại collection.
2. **timeField, metaField, granularity** đang dùng.
3. Retention hiện tại và các partial TTL indexes.
4. Data volume hiện có và tỷ lệ measurement cũ.
5. Query/report nào còn cần dữ liệu lớn tuổi.
6. Backup/archival được phê duyệt và khả năng khôi phục.
7. Mức tăng tải I/O chấp nhận được.
8. Thời gian quan sát sau khi áp dụng.

### 17.2. Phân loại thay đổi

| Thay đổi | Hệ quả chính |
|---|---|
| Không TTL → 7 ngày | Nhiều bucket lịch sử có thể đủ điều kiện xóa |
| 30 ngày → 7 ngày | Nguy cơ TTL backlog và mất raw history nhanh |
| 7 ngày → 30 ngày | Dữ liệu đang tồn tại giữ lâu hơn; dữ liệu đã xóa không trở lại |
| 7 ngày → "off" | Tắt collection-level expiration; storage tiếp tục tăng |
| "off" → 7 ngày | Có thể dọn lượng lịch sử lớn |
| Thêm partial TTL 1 ngày | Một nhóm metadata có thể bị xóa nhanh hơn |
| Đổi granularity | Ảnh hưởng bucketing/TTL delay, chịu giới hạn phiên bản |

### 17.3. Cẩn thận khi “rollback” TTL

Một thay đổi:

~~~text
30 ngày -> 7 ngày -> 30 ngày
~~~

**không phải một phép rollback dữ liệu hoàn chỉnh**. Trong khoảng TTL 7 ngày, một số bucket chứa dữ liệu 8–30 ngày có thể đã bị xóa. Sau khi đổi lại 30 ngày, MongoDB không tự tạo lại bucket đã mất.

Rollback metadata khác với **khôi phục dữ liệu**.

### 17.4. Không dọn bucket nội bộ bằng tay

Khi muốn đẩy nhanh việc xóa một lượng dữ liệu lớn, không tự thao tác trên **system.buckets**. Cần kiểm tra những lệnh delete hợp lệ của time series ở phiên bản đang dùng, giới hạn field được phép, và cân nhắc migration/staging riêng hoặc hỗ trợ vận hành phù hợp.

Thao tác xóa thử trên collection raw production có thể không thể đảo ngược; không thực hiện một script “delete tất cả timestamp cũ” nếu chưa hiểu các giới hạn time series và đã có quy trình.

### 17.5. Theo dõi sau triển khai

Một checklist vận hành có thể gồm:

- Tùy chọn collection đã đổi đúng TTL.
- Partial TTL index không xung đột policy mong muốn.
- TTL monitor hoạt động và metric có tiến triển.
- Mức quá tuổi trong query giảm dần theo dự kiến.
- CPU/I/O/replication lag ở giới hạn chấp nhận.
- Aggregation/downsampling không mất đầu vào.
- Backup và khả năng khôi phục vẫn theo chính sách.

Việc kiểm tra này thuộc **runbook vận hành của hệ thống thực**, không phải một lệnh mongosh đơn lẻ tự xác nhận mọi điều kiện.

## 18. Java MongoDB Sync Driver: tạo collection time series có TTL

Trong ứng dụng Java, **MongoDB Sync Driver** có thể tạo một time series collection bằng những option tương ứng với mongosh.

### 18.1. Kết nối và tạo collection

Ví dụ project đã có dependency **mongodb-driver-sync** tương thích với server. Biến môi trường **MONGODB_URI** trỏ tới MongoDB thử nghiệm mà người dùng có quyền tạo collection.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;

import java.util.concurrent.TimeUnit;

public class CreateSensorTimeSeries {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("timeseries_ttl_lab");

            TimeSeriesOptions timeSeriesOptions =
                    new TimeSeriesOptions("timestamp")
                            .metaField("sensor")
                            .granularity(TimeSeriesGranularity.SECONDS);

            CreateCollectionOptions options =
                    new CreateCollectionOptions()
                            .timeSeriesOptions(timeSeriesOptions)
                            .expireAfter(7, TimeUnit.DAYS);

            database.createCollection(
                    "sensorReadingsFromJava",
                    options
            );

            System.out.println("Created time series with TTL 7 days");
        }
    }
}
~~~

Với phiên bản Java Driver hỗ trợ những builder trên, việc tạo collection biểu diễn:

~~~javascript
{
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
}
~~~

Tên enum/method cần được đối chiếu với phiên bản **mongodb-driver-sync** đang sử dụng. Nếu đã có collection cùng tên, createCollection không đơn giản sửa TTL của nó; cần dùng **collMod** hoặc migration quản trị.

### 18.2. Không chạy createCollection với mỗi request

Trong một REST API, việc tạo collection và cấu hình TTL là một phần của **migration/bootstrap schema**, không phải một bước trong mỗi request cảm biến:

~~~text
Deploy / migration
  -> đảm bảo time series collection tồn tại và TTL hợp lệ

Runtime ingest service
  -> chỉ insert measurements
~~~

Nếu mọi instance API tự tạo hoặc sửa TTL khi startup, chúng có thể tranh nhau hoặc vô tình điều chỉnh chính sách retention đang được vận hành.

### 18.3. Ghi measurement bằng BSON Date

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public class SensorMeasurementWriter {
    public static void write(
            MongoCollection<Document> collection,
            String sensorId,
            double temperatureC,
            Instant measuredAt) {

        Document sensor = new Document("sensorId", sensorId)
                .append("retentionClass", "STANDARD");

        Document measurement = new Document(
                "timestamp",
                Date.from(measuredAt)
        )
                .append("sensor", sensor)
                .append("temperatureC", temperatureC);

        collection.insertOne(measurement);
    }
}
~~~

**Date.from(measuredAt)** đảm bảo timestamp được ghi thành BSON Date qua codec mặc định phù hợp. Nếu bạn lưu measuredAt.toString() thì đó là String; nó không tự có cùng ngữ nghĩa với BSON Date.

### 18.4. Quyết định event time từ đâu

Nếu thiết bị gửi measuredAt:

~~~java
Instant measuredAt = Instant.parse(
        "2026-11-14T10:15:00Z"
);
~~~

ứng dụng nên xác minh measuredAt có nằm trong khoảng hợp lý:

~~~java
Instant receivedAt = Instant.now();

boolean tooOld = measuredAt.isBefore(
        receivedAt.minusSeconds(7 * 24 * 3600L)
);

boolean tooFarInFuture = measuredAt.isAfter(
        receivedAt.plusSeconds(5 * 60L)
);

if (tooOld || tooFarInFuture) {
    throw new IllegalArgumentException(
            "Measurement timestamp outside allowed ingestion window");
}
~~~

Đây là **chính sách kiểm tra ứng dụng minh họa**, không phải luật MongoDB. Trong hệ thống cần backfill dữ liệu lịch sử, điều kiện quá cũ phải được thay bằng một quy trình staging/import có kiểm soát, thay vì từ chối mọi dữ liệu hợp lệ.

### 18.5. Java Driver không thay đổi tính không đồng bộ của TTL

Ngay cả khi Java insert thành công, một measurement đã quá hạn vẫn có thể tạm thời nhìn thấy qua find. Driver không chờ TTL monitor xóa bucket để trả kết quả insert.

Nếu API muốn giới hạn dữ liệu trả về trong 7 ngày, Java query cũng cần filter thời gian độc lập.

### 18.6. Filter theo khoảng thời gian từ Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;

public class SensorWindowReader {
    public static void readLastSevenDays(
            MongoCollection<Document> collection,
            String sensorId) {

        Instant now = Instant.now();
        Date from = Date.from(
                now.minusSeconds(7L * 24 * 3600)
        );
        Date to = Date.from(now);

        Bson filter = Filters.and(
                Filters.eq("sensor.sensorId", sensorId),
                Filters.gte("timestamp", from),
                Filters.lt("timestamp", to)
        );

        try (MongoCursor<Document> cursor = collection
                .find(filter)
                .sort(Sorts.ascending("timestamp"))
                .iterator()) {

            while (cursor.hasNext()) {
                System.out.println(cursor.next().toJson());
            }
        }
    }
}
~~~

Mẫu **[from, to)** giúp query được xác định rõ. Query này không khẳng định mọi measurement quá bảy ngày đã bị xóa khỏi storage; nó chỉ yêu cầu MongoDB **không trả chúng** trong kết quả.

## 19. Java Driver: thay đổi TTL và đọc collection metadata

Ngoài mongosh, có thể dùng MongoDB Java Sync Driver gửi **collMod** để thay retention của time series collection.

### 19.1. Thay collection-level TTL

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class UpdateTimeSeriesTTL {
    public static Document setRetentionToThirtyDays(
            MongoDatabase database) {

        Document command = new Document(
                "collMod",
                "sensorReadingsFromJava"
        ).append(
                "expireAfterSeconds",
                30 * 24 * 3600
        );

        return database.runCommand(command);
    }
}
~~~

**Lưu ý:** method trên là thao tác **quản trị collection**. Trong thực tế nên gọi qua migration đã được duyệt, không chạy tự động khi một request API muốn insert measurement.

### 19.2. Tắt TTL bằng "off"

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class DisableTimeSeriesTTL {
    public static void disable(
            MongoDatabase database) {

        database.runCommand(
                new Document(
                        "collMod",
                        "sensorReadingsFromJava"
                ).append(
                        "expireAfterSeconds",
                        "off"
                )
        );
    }
}
~~~

**"off" không tương đương 0**. Trên phiên bản hỗ trợ, "off" tắt expiration ở cấp collection; 0 là một thời hạn rất ngắn theo mốc timeField.

### 19.3. Lấy metadata bằng listCollections

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ShowCollectionRetention {
    public static Document listInfo(
            MongoDatabase database) {

        Document command = new Document(
                "listCollections",
                1
        ).append(
                "filter",
                new Document("name", "sensorReadingsFromJava")
        );

        return database.runCommand(command);
    }
}
~~~

Kết quả trả về dạng command result, thường chứa cursor/firstBatch với metadata của collection. Khi xây công cụ quản trị, cần parse đúng cấu trúc và xử lý trường hợp collection không tồn tại.

### 19.4. Quản lý cấu hình retention như một versioned migration

Một tổ chức có thể lưu thông tin phiên bản cấu hình trong repository:

~~~text
Schema migration V001:
  Create sensorReadingsFromJava
  timeField: timestamp
  metaField: sensor
  expireAfterSeconds: 604800

Schema migration V007:
  Change collection TTL to 2592000
  Reason: extend raw window before hourly aggregation
  Approval: data platform
~~~

Đây là thông tin nên được quản lý **ngoài MongoDB collection data**, có changelog và quy trình rollback dữ liệu. Việc lưu cấu hình trong code giúp người vận hành biết chính sách đã được phê duyệt, nhưng phải đối chiếu metadata thực tế để phát hiện drift.

## 20. Spring Data MongoDB: tạo và dùng time series collection có retention

Spring Data MongoDB cung cấp **MongoTemplate** và các API mapping/collection management. Cú pháp builder cụ thể cho time series và TTL có thể khác giữa các phiên bản Spring Data, nên một cách rõ ràng để minh họa là dùng **MongoTemplate.executeCommand** với BSON command do MongoDB định nghĩa.

### 20.1. Tạo collection time series bằng MongoTemplate

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class TimeSeriesCollectionSetup {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesCollectionSetup(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void createRawReadings() {
        Document command = new Document(
                "create",
                "springSensorReadings"
        ).append(
                "timeseries",
                new Document(
                        "timeField",
                        "timestamp"
                )
                        .append("metaField", "sensor")
                        .append("granularity", "seconds")
        ).append(
                "expireAfterSeconds",
                604800
        );

        // Chạy một lần trong migration/schema bootstrap.
        mongoTemplate.executeCommand(command);
    }
}
~~~

Đoạn này cần MongoTemplate đã cấu hình trỏ đến database **timeseries_ttl_lab**. Nếu collection tồn tại, lệnh create có thể trả lỗi; đừng bắt mọi lỗi rồi im lặng cho qua khi schema/TTL thực tế có thể sai.

### 20.2. Cập nhật TTL từ Spring Data

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class TimeSeriesRetentionAdmin {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesRetentionAdmin(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document setSevenDayTTL() {
        return mongoTemplate.executeCommand(
                new Document(
                        "collMod",
                        "springSensorReadings"
                ).append("expireAfterSeconds", 604800)
        );
    }
}
~~~

Trong sản phẩm thật, phương thức này cần quyền quản trị và luồng phê duyệt. Không đưa một endpoint như **POST /set-ttl?seconds=0** cho mọi người dùng tự gọi.

### 20.3. Query time window bằng Criteria

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class TimeSeriesQueryService {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesQueryService(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> getReadings(
            String sensorId,
            Instant from,
            Instant to) {

        if (!from.isBefore(to)) {
            throw new IllegalArgumentException(
                    "Invalid time range");
        }

        Query query = Query.query(
                Criteria.where("sensor.sensorId").is(sensorId)
                        .and("timestamp")
                        .gte(Date.from(from))
                        .lt(Date.from(to))
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "springSensorReadings"
        );
    }
}
~~~

Đây là truy vấn **theo metadata và khoảng thời gian**, có thể giúp MongoDB giới hạn bucket liên quan nếu index/collection phù hợp. Nó không dựa vào việc TTL monitor đã dọn xong để lọc kết quả.

### 20.4. Annotation và schema creation cần được hiểu đúng

Một class có annotation time series hoặc index trong một framework **không có nghĩa retention policy đã được áp dụng ở MongoDB** nếu ứng dụng không cấu hình auto-creation tương ứng hoặc collection đã tồn tại với option cũ.

Trong production cần xác nhận:

- Collection thực sự có type **timeseries**.
- timeField/metaField trùng với mapping của ứng dụng.
- expireAfterSeconds phù hợp policy được duyệt.
- Các index/query dự kiến tồn tại.
- Không có drift giữa môi trường staging và production.

### 20.5. Không dùng Repository.deleteByTimestamp để mô phỏng TTL

Một số developer muốn viết scheduled job:

~~~java
// Pseudocode: không phải lựa chọn mặc định tốt hơn TTL
// repository.deleteAllByTimestampBefore(cutoff);
~~~

Nhưng time series collection có những giới hạn thao tác delete/update tùy phiên bản; đồng thời job tự xóa phải xử lý load, retries, concurrency và cleanup.

Khi retention có thể biểu diễn bằng TTL được hỗ trợ, hãy ưu tiên cơ chế MongoDB. Chỉ dùng custom delete job nếu có yêu cầu khác TTL không đáp ứng và đã xác minh tính hợp lệ của thao tác trên phiên bản server.

## 21. Thiết kế TTL theo nhu cầu nghiệp vụ

### 21.1. Metric hạ tầng

Yêu cầu:

~~~text
Raw CPU samples:     3 ngày
5-minute rollups:   90 ngày
Daily rollups:     365 ngày
~~~

Đề xuất:

- Một collection time series **rawCpu3d** có TTL 259200 giây.
- Một collection **cpuFiveMinute90d** giữ dữ liệu tổng hợp 90 ngày.
- Một collection **cpuDaily365d** hoặc archive dài hạn.

Các job tổng hợp cần có watermark, retry và thời gian buffer trước khi raw bị xóa.

### 21.2. Sensor thiết bị công nghiệp

Yêu cầu:

~~~text
Sensor production: raw 30 ngày
Sensor test/lab:  raw 1 ngày
~~~

Nếu phiên bản hỗ trợ **partial TTL index trên metaField**, dùng collection-level 30 ngày và partial 1 ngày theo **sensor.retentionClass = "TEST"**. Nếu không, tách collection hoặc triển khai policy khác theo phiên bản.

### 21.3. Dữ liệu giám sát tuân thủ

Yêu cầu:

~~~text
Raw operational metrics: 7 ngày
Một nhóm dữ liệu có legal hold: không được xóa
~~~

Không để một collection-level TTL 7 ngày áp dụng cả nhóm cần legal hold, vì TTL toàn cục vẫn có thể xóa nó.

Các lựa chọn có thể gồm:

- Tách **legal-hold collection** không bật TTL tự động.
- Dùng một collection có policy TTL chỉ cho subset hợp lệ, theo khả năng partial TTL.
- Thiết kế archive/sổ cái theo chính sách khác.

Không coi một field **legalHold: true** trong measurement là cơ chế ngăn collection-level TTL nếu không có thiết kế thực thi phù hợp.

### 21.4. Dữ liệu sự kiện từ thiết bị offline

Yêu cầu:

~~~text
Sensor có thể offline 14 ngày
Raw cần giữ để xử lý 7 ngày sau khi nhận
~~~

Nếu timeField là thời điểm đo, dữ liệu gửi sau 14 ngày đã cũ hơn retention 7 ngày. Cần tính lại policy:

- Giữ raw dài hơn theo event time.
- Staging để xử lý dữ liệu offline.
- Thiết kế ingestion-time series riêng cho lifecycle.
- Lưu số liệu tổng hợp ngay khi nhận và archive raw theo chính sách.

**Chọn retention ngắn hơn độ trễ dữ liệu có thể đến hợp lệ** thường dẫn đến mất dữ liệu trước khi xử lý.

### 21.5. Dữ liệu cần xóa theo end-of-month

Yêu cầu “mọi phép đo của tháng 10 được xóa vào 00:00 ngày 01/01 theo timezone business” không phải cùng nghĩa với “giữ 60 ngày × 24 giờ từ từng timestamp”.

Có thể cần:

- Quy trình xóa theo lịch tháng đã được phê duyệt.
- Partition theo collection/tháng trong mô hình dữ liệu phù hợp.
- Archive và remove collection sau khi kết thúc kỳ.

Không mặc định expireAfterSeconds có thể diễn đạt mọi quy tắc lịch kế toán.

## 22. Sự cố thường gặp và cách điều tra

### 22.1. Cấu hình TTL 1 giờ nhưng query vẫn thấy dữ liệu 90 phút tuổi

Các nguyên nhân có thể gồm:

1. Measurement cũ đang ở một bucket có measurement mới chưa hết hạn.
2. Giới hạn thời gian của bucket khiến việc xóa bị trì hoãn.
3. TTL monitor chưa tới lượt dọn hoặc có backlog.
4. Read đi đến secondary chưa áp dụng thao tác xóa.
5. Thực tế collection không có expireAfterSeconds mong muốn.
6. Query đang đọc **collection khác** hoặc một bản dữ liệu archive/cache.

Hướng xử lý:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});

db.sensorReadings7d.getIndexes();

db.serverStatus().metrics.ttl;
~~~

Đối chiếu metadata, bucket behavior và trạng thái vận hành. Không xóa thủ công system.buckets để “sửa nhanh”.

### 22.2. TTL hoạt động nhưng ổ đĩa không giảm

Nguyên nhân có thể là **WiredTiger tái sử dụng free space bên trong các file dữ liệu**. Dữ liệu logic đã giảm nhưng kích thước file hệ điều hành chưa co tương ứng.

Nên kiểm tra số lượng/khối lượng dữ liệu theo logic, dung lượng storage và free/reusable space. Không tự chạy thao tác compact/initial sync chỉ để giảm disk nếu chưa có quy trình và đánh giá rủi ro.

### 22.3. Sau khi giảm retention, CPU và I/O tăng

Nếu từ 365 ngày đổi sang 7 ngày, rất nhiều bucket có thể đủ điều kiện xóa. TTL monitor cần xử lý nhiều thao tác nền; replication và backup cũng có thể chịu thêm tải.

Hướng xử lý phù hợp gồm giảm tốc rollout ở cấp quy trình, giám sát tài nguyên, xác định backlog và phối hợp DBA. **Không có một lệnh TTL duy nhất luôn bảo đảm “xóa hàng năm dữ liệu mà không ảnh hưởng production”.**

### 22.4. Tắt TTL nhưng dữ liệu vẫn biến mất

Cần xác định:

- Có **partial TTL index** còn hoạt động không?
- Có job manual delete hoặc data lifecycle ngoài MongoDB không?
- Có collection khác đang được query không?
- Có migration/collection drop/rebuild đã diễn ra không?
- Dữ liệu đã bị xóa **trước khi** TTL được tắt không?

**"off" ở collection-level** không tự hủy mọi hình thức xóa dữ liệu khác.

### 22.5. Partial TTL index không xóa đúng nhóm

Kiểm tra:

- Server version có hỗ trợ partial TTL trên time series không?
- Index có được tạo thành công không?
- Key là **timeField** của collection?
- Filter chỉ dùng **metaField/subfield** hợp lệ?
- Metadata thực có đúng kiểu/giá trị? Ví dụ **"SHORT"** khác **"short"**.
- Collection-level TTL có giá trị ngắn hơn làm index dài hơn vô hiệu không?
- Bucket đã đủ điều kiện xóa chưa?

Đừng kết luận index hỏng chỉ vì cùng ngày có những measurement thuộc nhóm SHORT mà vẫn còn trong bucket.

### 22.6. Dữ liệu sensor từ tương lai tồn tại mãi

Đây có thể là lỗi clock của sensor. TTL tính tuổi theo timeField, nên timestamp tương lai chưa đạt ngưỡng. Cần validate và quarantine, sửa nguồn time, đồng thời xác định cách xử lý dữ liệu đã ghi.

Không tăng/giảm TTL toàn collection để chữa một vài timestamp sai: điều đó ảnh hưởng mọi measurement.

### 22.7. Dữ liệu backfill bị dọn trước khi tạo báo cáo

Nếu backfill đã quá retention theo event time, TTL có thể xóa dữ liệu trước khi pipeline xử lý xong. Cần:

- Staging riêng.
- TTL đủ dài cho backfill.
- Pipeline tổng hợp chạy trước cleanup.
- Có checkpoint/watermark và xác nhận.

Một policy 7 ngày không biết batch được import hôm nay nếu timestamp của phép đo là 90 ngày trước.

### 22.8. Một nhóm đo cần retention 30 ngày nhưng collection-level chỉ 7 ngày

Một partial TTL index 30 ngày **không giúp nhóm ấy sống lâu hơn** collection-level TTL 7 ngày.

Đổi thiết kế: collection-level TTL bằng retention dài nhất rồi partial TTL ngắn hơn, hoặc tách collection theo nhóm.

### 22.9. TTL index tạo không thành công

Đừng mặc định một index bất kỳ có thể là TTL. MongoDB áp dụng các hạn chế:

- TTL thường là **single-field index**.
- Partial TTL time series chỉ hỗ trợ đúng mô hình **timeField key + metaField filter** trong phiên bản phù hợp.
- Không thể dùng createIndex với cùng key pattern chỉ khác TTL options để tự chuyển một index hiện có thành TTL nếu server không cho phép.
- Dữ liệu, index options hoặc phiên bản/FCV có thể gây lỗi.

Đọc thông báo lỗi thực tế và tài liệu đúng phiên bản. Không tự drop một index production quan trọng chỉ để thử lại mà chưa hiểu ảnh hưởng query.

### 22.10. Số lượng measurement xóa không khớp metrics.ttl.deletedDocuments

Time series dùng bucket storage; metric TTL là counter server về hoạt động deletion ở mức MongoDB ghi nhận, có thể không tương ứng một-một với từng measurement logic.

Không dùng chênh lệch metric này làm hóa đơn xác định “đã xóa chính xác N readings của sensor S-101”. Nếu cần audit xóa theo lớp nghiệp vụ, phải thiết kế telemetry/audit riêng.

### 22.11. Một measurement cũ vẫn xuất hiện trong read model

Dữ liệu được copy sang Elasticsearch, warehouse, Redis hay một API cache **không tự hết hạn** theo TTL của raw MongoDB collection. Cần retention/lifecycle ở từng hệ thống.

Nếu ứng dụng cần chắc chắn không trả dữ liệu quá tuổi, bổ sung filter thời gian ở đường đọc và kiểm soát downstream caches/indexes.

### 22.12. Raw data hết hạn khi job tính trung bình đang chạy

Với job dài hoặc nhiều lần retry, TTL có thể xóa input trong lúc pipeline xử lý nếu retention quá sát. Hãy đặt buffer, cố định event-time window, tạo dữ liệu tổng hợp sớm và có cơ chế xác nhận/cảnh báo.

### 22.13. Phép đo trùng nhau vì sensor retry

TTL **không phải cơ chế deduplication**. Nếu sensor gửi hai bản ghi có cùng sensorId/timestamp, TTL có thể giữ cả hai đến khi hết hạn.

Muốn loại trùng cần eventId ổn định, idempotency ở ingestion pipeline hoặc quy trình xử lý trùng; các giới hạn unique index của time series phải được xem xét. Không coi TTL là công cụ chống ghi trùng.

### 22.14. Collection vẫn lớn dù TTL đã xử lý hết dữ liệu cũ

Có thể vì tốc độ ingest nhanh:

~~~text
Ingest 86 triệu measurements/ngày
TTL giữ 7 ngày

Ước lượng dữ liệu logic đang giữ
  ~ 7 × 86 triệu = 602 triệu measurements
~~~

Hệ thống vẫn cần đủ storage cho lượng dữ liệu trong retention window, metadata/index/overhead và headroom cho vận hành. TTL làm vòng đời hữu hạn, **không biến tổng dung lượng cần thiết thành gần bằng 0**.

## 23. Quy trình chẩn đoán một collection có TTL bất thường

### Bước 1 — Xác minh loại collection

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

Quan sát type và options.timeseries.

### Bước 2 — Xác minh chính sách expiration

Xem **options.expireAfterSeconds** và các index:

~~~javascript
db.sensorReadings7d.getIndexes();
~~~

Kiểm tra có partial TTL index theo retentionClass hay không.

### Bước 3 — Xác minh timestamp

Một số record mẫu có phải BSON Date hợp lệ và có nằm trong miền kỳ vọng?

~~~javascript
db.sensorReadings7d.find(
  {},
  {
    _id: 0,
    timestamp: 1,
    sensor: 1
  }
).sort({
  timestamp: 1
}).limit(5);
~~~

Nếu có timestamp rất xa tương lai hoặc lịch sử, cần xem chính sách nhập.

### Bước 4 — Tính ngưỡng tuổi riêng

~~~javascript
const ttlSeconds = 604800;
const cutoff = new Date(
  Date.now() - ttlSeconds * 1000
);

print("Cutoff UTC:", cutoff.toISOString());
~~~

Một measurement timestamp trước cutoff đã quá tuổi theo **ngưỡng riêng**, nhưng bucket có thể chưa đủ điều kiện xóa.

### Bước 5 — Đánh giá bucket/granularity

Xem granularity hoặc custom bucket span, đặc điểm dữ liệu cùng metaField và khả năng phép đo mới hơn giữ bucket. Không suy luận exact bucket assignment chỉ từ vài timestamp mẫu nếu không có quan sát phù hợp.

### Bước 6 — Xem metric TTL monitor

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Kiểm tra các counter theo thời gian để biết monitor có tiến triển, nhưng đừng lấy số counter làm số measurement chính xác đã xóa.

### Bước 7 — Kiểm tra topology

Với replica set/sharded cluster, kiểm tra primary/secondary, replication lag và những node có TTL backlog. Không dựa vào một kết nối đọc secondary để kết luận xóa trên primary đã hoặc chưa diễn ra.

### Bước 8 — Xác định nguồn dữ liệu ứng dụng trả về

Có cache, archive, analytics read model hoặc API fallback không? Nếu có, kiểm tra retention và filter tương ứng ở các hệ thống này.

### Bước 9 — Đánh giá tác động của thay đổi TTL

Không sửa expireAfterSeconds nhiều lần chỉ để “thử xem có xóa không”. Xác định nguyên nhân rồi lên kế hoạch thay đổi có kiểm soát.

### Bước 10 — Lưu lại kết luận và bằng chứng

Ghi nhận:

- Collection và thời điểm quan sát.
- TTL/granularity/index thực tế.
- Số lượng/độ tuổi mẫu dữ liệu quá ngưỡng.
- Trạng thái TTL monitor và topology.
- Nguyên nhân được xác định hoặc còn nghi ngờ.
- Hành động sửa và điều kiện nghiệm thu.

Runbook giúp tránh lặp lại việc “thấy data cũ → vội vàng drop collection”.

## 24. Bảng quyết định nhanh

| Câu hỏi nghiệp vụ | Hướng triển khai nên xem xét |
|---|---|
| Raw time series giữ cố định N giây/ngày | Collection-level expireAfterSeconds |
| Chỉ một nhóm sensor cần TTL ngắn hơn | Partial TTL index theo metaField trên phiên bản hỗ trợ |
| Một nhóm phải giữ lâu hơn TTL toàn collection | Tăng TTL toàn collection hoặc tách collection; partial TTL dài hơn không cứu được |
| Không muốn xóa tự động nữa | collMod với expireAfterSeconds: "off" nếu phiên bản hỗ trợ |
| Muốn giảm TTL trên collection đã có lịch sử | Migration có phê duyệt, đánh giá TTL backlog và backup |
| Muốn đọc chính xác N giờ gần nhất | Query filter timestamp theo [from, to), không dựa vào cleanup |
| Muốn xóa đúng một giây sau hạn | TTL nền theo bucket không cung cấp SLA đó |
| Muốn xóa theo cuối tháng địa phương | Thiết kế lifecycle theo lịch/collection khác |
| Thiết bị có thể gửi dữ liệu trễ hơn retention | Staging hoặc tăng cửa sổ lưu/đổi chính sách |
| Cần giữ dữ liệu để tính báo cáo dài hạn | Downsampling/aggregation trước raw TTL |
| Cần lưu raw nhiều năm nhưng chỉ truy vấn gần đây | Archive hoặc tầng lưu trữ riêng |
| Cần xóa khỏi backup và hệ thống ngoài | Kiểm soát retention từng hệ thống; TTL MongoDB không đủ |
| Dữ liệu có timestamp sai tương lai | Validate/quarantine/correct clock, không tăng TTL mù |
| Muốn đo lượng measurement còn quá ngưỡng | Query/metric riêng có tính bucket delay |
| Mức disk không giảm sau TTL | Phân biệt dữ liệu logic và free space được tái sử dụng |

## 25. Bài tập thực hành về TTL trong time series

Các bài tập sử dụng **timeseries_ttl_lab** và những collection thử nghiệm đã giới thiệu. Nếu đã chạy câu lệnh tạo collection trước đó, không chạy createCollection trùng tên mà không kiểm tra. Những bài thay đổi TTL chỉ nên thử trên dữ liệu mẫu, không thao tác trên production.

### Bài 1. Tính TTL theo giây

Một collection raw có chính sách giữ **14 ngày**, còn collection hourly summary giữ **180 ngày**.

**Yêu cầu:** Tính expireAfterSeconds của mỗi collection.

**Đáp án:**

~~~text
Raw 14 ngày:
14 × 24 × 60 × 60 = 1209600 giây

Hourly 180 ngày:
180 × 24 × 60 × 60 = 15552000 giây
~~~

Hãy lưu ý đây là **14 và 180 ngày cố định**, không phải tháng lịch.

### Bài 2. Tạo một time series collection có TTL 48 giờ

Thiết kế:

- Collection: **labMetrics48h**
- timeField: **measuredAt**
- metaField: **source**
- granularity: **seconds**
- TTL: **48 giờ**

~~~javascript
db.createCollection("labMetrics48h", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "source",
    granularity: "seconds"
  },
  expireAfterSeconds: 172800
});
~~~

**Câu hỏi:** Nếu cùng document có field **createdAt** hôm nay nhưng measuredAt là ba ngày trước, TTL dựa trên field nào?

**Đáp án:** Dựa trên **measuredAt** vì đó là timeField đã khai báo, không tự chuyển sang createdAt.

### Bài 3. Xác định thời điểm bắt đầu đủ điều kiện hết hạn

Một phép đo:

~~~text
measuredAt = 2026-11-14T08:30:00Z
TTL        = 3600 giây
~~~

**Câu hỏi:** Khi nào phép đo bắt đầu quá tuổi theo TTL?

**Đáp án:** **2026-11-14T09:30:00Z**. Nhưng measurement có thể còn hiển thị sau đó vì bucket và TTL monitor chưa dọn.

### Bài 4. Bucket có phép đo mới hơn

Giả sử một bucket logic chứa:

~~~text
10:00
10:15
10:50
~~~

TTL = một giờ. Ở thời điểm 11:30, những phép đo nào đã quá tuổi riêng? Có thể xóa cả bucket chưa?

**Đáp án định hướng:** 10:00 và 10:15 đã quá một giờ; 10:50 chưa. Vì bucket còn phép đo chưa hết hạn nên **chưa đủ điều kiện xóa toàn bucket** theo mô hình TTL time series.

### Bài 5. Chọn granularity

Một sensor ghi mỗi 10 giây, sensor khác ghi mỗi 2 giờ. Bạn phải chọn granularity phù hợp và giải thích tác động lên bucketing/TTL delay.

**Định hướng:** Lựa chọn phải dựa trên khoảng cách timestamp, kiểu truy vấn và giới hạn lưu trữ. Granularity seconds và hours có phạm vi bucket tối đa khác nhau; không chọn hours cho dữ liệu rất dày chỉ với lý do “muốn xóa sau một giờ”. **Granularity không phải giá trị TTL**.

### Bài 6. Bật TTL cho collection hiện có

Một time series collection **oldReadings** chưa có automatic expiration. Hãy bật TTL 30 ngày.

~~~javascript
db.runCommand({
  collMod: "oldReadings",
  expireAfterSeconds: 2592000
});
~~~

**Câu hỏi:** Nếu collection đã có một năm dữ liệu, lệnh trả thành công có nghĩa dữ liệu ngoài 30 ngày đã biến mất hết chưa?

**Đáp án:** Chưa. Các bucket đủ điều kiện sẽ được TTL dọn qua cơ chế nền; có thể có backlog và độ trễ.

### Bài 7. Tắt TTL

Hãy viết câu lệnh tắt collection-level expiration:

~~~javascript
db.runCommand({
  collMod: "oldReadings",
  expireAfterSeconds: "off"
});
~~~

**Câu hỏi:** Vì sao không dùng expireAfterSeconds: 0?

**Đáp án:** Số 0 không biểu thị “off”; nó tạo thời hạn không cộng thêm giây theo mốc timeField và có thể làm bucket đủ điều kiện xóa rất sớm.

### Bài 8. Không thể phục hồi bằng cách tăng TTL

Ngày thứ nhất, collection TTL 7 ngày đã xóa một số dữ liệu cũ. Ngày thứ hai, DBA tăng retention lên 30 ngày.

**Câu hỏi:** MongoDB có tự đưa dữ liệu đã bị TTL xóa trở lại không?

**Đáp án:** Không. Tăng TTL chỉ giữ lâu hơn những bucket còn tồn tại; muốn dữ liệu đã xóa phải dùng backup/archive phù hợp nếu còn giữ.

### Bài 9. Partial TTL theo metaField

Collection **classMetrics** có:

~~~javascript
{
  timeseries: {
    timeField: "measuredAt",
    metaField: "source"
  },
  expireAfterSeconds: 2592000
}
~~~

Yêu cầu nhóm source.retentionClass = **TEST** chỉ giữ 1 ngày. Viết partial TTL index trên phiên bản hỗ trợ:

~~~javascript
db.classMetrics.createIndex(
  { measuredAt: 1 },
  {
    name: "ttl_test_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "source.retentionClass": "TEST"
    }
  }
);
~~~

**Câu hỏi:** source.retentionClass nằm ở metaField hay measurement field? Vì sao điều này quan trọng?

**Đáp án:** Đây là subfield của metaField **source**, phù hợp ràng buộc của partial TTL time series. Một filter dựa trên giá trị measurement tùy ý không thay thế được quy tắc này.

### Bài 10. Partial TTL dài hơn collection-level TTL

Collection-level TTL 7 ngày; partial TTL cho nhóm VIP là 30 ngày.

**Câu hỏi:** VIP có thực sự được bảo đảm giữ 30 ngày không?

**Đáp án:** Không. Collection-level 7 ngày vẫn áp dụng, có thể khiến dữ liệu VIP bị dọn trước 30 ngày. Nếu cần VIP 30 ngày, phải đổi policy tổng thể hoặc tách collection.

### Bài 11. Dữ liệu offline

Sensor S-101 offline 12 ngày, rồi gửi lại measurement có timestamp 12 ngày trước vào raw collection TTL 7 ngày.

**Câu hỏi:** Sensor được giữ thêm 7 ngày từ lúc gửi lại không?

**Đáp án:** Không theo cấu hình timeField event time này. Measurement đã quá tuổi tại thời điểm import. Cần thiết kế staging hoặc retention phù hợp với độ trễ ingestion.

### Bài 12. Timestamp trong tương lai

Một thiết bị gửi timestamp năm 2035 dù hệ thống đang vận hành năm 2026.

**Câu hỏi:** TTL 7 ngày có sớm xóa bản ghi này không?

**Định hướng:** Không nên kỳ vọng. Timestamp tương lai khiến phép đo chưa đủ tuổi. Cần kiểm tra time skew, sửa thiết bị và xác định chính sách reject/quarantine.

### Bài 13. Phân biệt filter query và TTL

Collection có TTL 30 ngày, nhưng một API chỉ trả **24 giờ gần nhất**. Viết filter phù hợp.

~~~javascript
const now = new Date();
const from = new Date(now.getTime() - 24 * 3600 * 1000);

db.sensorReadings7d.find({
  timestamp: {
    $gte: from,
    $lt: now
  }
});
~~~

**Đáp án định hướng:** Lọc theo [from,now) là trách nhiệm của query; không cần hoặc không nên đổi TTL toàn collection thành 24 giờ chỉ để phục vụ một endpoint.

### Bài 14. Downsampling trước TTL

Raw giữ 7 ngày; hourly aggregate chạy mỗi ngày một lần. Job gặp lỗi ba ngày liền.

**Câu hỏi:** Có nguy cơ gì và nên sửa thiết kế thế nào?

**Định hướng:** Khi raw hết hạn, job có thể mất dữ liệu để tổng hợp lại. Cần buffer dài đủ cho sự cố/retry, watermark, cảnh báo, checkpoint và nguồn khôi phục.

### Bài 15. Độ trễ TTL monitor

Một measurement đã quá tuổi nhưng vẫn thấy trong collection, metric TTL passes vẫn tăng.

**Câu hỏi:** Có thể kết luận TTL monitor hỏng không?

**Đáp án:** Chưa thể. Bucket có thể chứa measurement mới hơn, hoặc việc dọn nền/backlog/replication tạo độ trễ. Cần xem policy, timeField, granularity và topology.

### Bài 16. Dung lượng sau khi xóa

Sau khi TTL xóa phần lớn dữ liệu lịch sử, lượng measurement logic giảm nhưng kích thước file trên đĩa gần như không đổi.

**Câu hỏi:** TTL có chắc là thất bại không?

**Đáp án:** Không. Storage engine có thể giữ không gian bên trong file để tái sử dụng. Cần phân biệt logical data size với physical file allocation.

### Bài 17. Metadata filter sai

Partial TTL filter:

~~~javascript
{
  "sensor.retentionClass": "SHORT"
}
~~~

Document lại chứa:

~~~javascript
{
  sensor: {
    retentionClass: "short"
  }
}
~~~

**Câu hỏi:** Document có khớp điều kiện filter với so sánh chuỗi thông thường không?

**Đáp án:** Không với so sánh mặc định phân biệt chữ hoa/thường. Cần chuẩn hóa metadata khi ghi, không kỳ vọng MongoDB tự suy luận SHORT tương đương short.

### Bài 18. Legal hold

Một nhóm reading có yêu cầu giữ 3 năm trong khi collection-level TTL là 7 ngày.

**Câu hỏi:** Thêm field legalHold=true vào measurement có đủ ngăn MongoDB TTL xóa không?

**Đáp án:** Không. TTL collection-level vẫn áp dụng theo timeField. Cần tách dữ liệu hoặc thiết kế policy hợp lệ để legal-hold data không chịu TTL ngắn.

### Bài 19. Điều tra read trên secondary

Primary đã xóa bucket qua TTL, nhưng một client đọc từ secondary còn nhìn thấy measurement cũ.

**Câu hỏi:** Sự khác biệt nhất thời này có thể do đâu?

**Định hướng:** Secondary có thể chưa áp dụng thao tác xóa do replication lag. TTL không tự tạo consistency mạnh cho các lần read từ mọi secondary.

### Bài 20. Thiết kế hệ thống metric

Bạn cần xây hệ thống có:

~~~text
Raw server metrics:       3 ngày
Hourly rollups:          90 ngày
Monthly reports:          2 năm
Cho phép sensor backfill: 24 giờ
Cho phép aggregation retry: 48 giờ
~~~

Hãy đề xuất:

1. Collection nào nên là time series?
2. TTL mỗi tầng.
3. Vì sao retention raw 3 ngày có đủ buffer cho ingestion 24 giờ và retry 48 giờ, hay cần thêm margin?
4. Làm sao bảo đảm aggregate job không ghi trùng khi retry?
5. Dashboard realtime truy vấn khoảng thời gian nào?
6. Chính sách backup/archival cần làm gì ngoài TTL?

**Định hướng:** Có thể dùng raw time series TTL 3 ngày nếu đã tính toán đủ SLA thực tế và margin, hourly collection TTL 90 ngày, reports retention 2 năm theo cấu trúc phù hợp. Có checkpoint/watermark, upsert theo khóa giờ và sensor, cùng chính sách backup riêng. Không chỉ viết ba con số TTL rồi coi toàn bộ hệ thống đã hoàn chỉnh.

## 26. Lộ trình triển khai mẫu cho hệ thống sensor

### Giai đoạn 1. Thống nhất data contract

Mỗi measurement có:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01",
    retentionClass: "STANDARD"
  },
  temperatureC: 28.5,
  receivedAt: ISODate("2026-11-14T10:00:03Z")
}
~~~

Quy định rõ:

- timeField là **timestamp** đại diện event time.
- receivedAt chỉ là thời điểm ingestion để đo độ trễ.
- sensorId/site/retentionClass là metadata ổn định.
- Những giá trị timestamp quá cũ/tương lai được xử lý theo policy.

### Giai đoạn 2. Chọn retention đủ cho downstream

Ví dụ:

~~~text
Sensor tối đa offline: 1 ngày
Aggregation job retry: 2 ngày
Buffer sự cố bổ sung: 2 ngày
Raw retention: 7 ngày
~~~

Đây là một chính sách minh họa có buffer. Nếu pipeline retry có thể vượt 7 ngày, phải điều chỉnh retention hoặc có nguồn staging/archive.

### Giai đoạn 3. Tạo collection

~~~javascript
db.createCollection("rawMetrics7d", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

### Giai đoạn 4. Tạo job downsampling

Job chạy theo giờ, lưu aggregate bằng khóa business cố định của **(sensorId, hourStart)**, theo dõi watermark và cho phép retry idempotent.

### Giai đoạn 5. Chỉ hiển thị trong cửa sổ hợp lệ

API realtime lọc:

~~~javascript
{
  timestamp: {
    $gte: from,
    $lt: to
  }
}
~~~

Không dựa vào việc TTL đã xóa đúng từng timestamp đến deadline.

### Giai đoạn 6. Theo dõi vận hành

Đo lượng measurement đang giữ, TTL monitor, query latency, I/O, replication lag, job watermark và tỷ lệ sensor clock skew.

### Giai đoạn 7. Kiểm soát thay đổi

Mọi điều chỉnh TTL hoặc partial TTL phải được version hóa, đánh giá dữ liệu sẽ bị xóa, xem backup/archival và có người phê duyệt.

## 27. Tài liệu tham khảo để đối chiếu phiên bản

Các tính năng TTL và time series có những điểm khác nhau theo **phiên bản MongoDB/feature compatibility**. Khi triển khai thật, nên đối chiếu với tài liệu chính thức của phiên bản đang chạy:

- [MongoDB Manual — Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — collMod](https://www.mongodb.com/docs/manual/reference/command/collmod/)
- [MongoDB Manual — Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)

**Lưu ý:** URL /manual thường trỏ đến tài liệu hiện hành; đối với môi trường MongoDB 6.x, 7.x hoặc 8.x, hãy chọn lại tài liệu version cụ thể để kiểm tra khả năng partial TTL, custom buckets và những giới hạn index/operation của phiên bản đó.

## 28. Kết luận

MongoDB TTL là cơ chế hữu ích để giữ **dung lượng dữ liệu time series trong một vòng đời xác định**, nhưng cách hoạt động cần được hiểu đúng:

~~~text
Measurement với BSON Date timestamp
                 |
                 v
TTL threshold = timestamp + expireAfterSeconds
                 |
                 v
Measurement bắt đầu quá tuổi
                 |
                 v
Bucket chứa nó đã đủ điều kiện hết hạn?
            /                  \
          Chưa                  Rồi
           |                     |
       Chờ phép đo               v
       mới hơn hết hạn      TTL monitor xử lý nền
                                 |
                                 v
                         Bucket được xóa
                                 |
                                 v
                        Dung lượng có thể
                        được tái sử dụng
~~~

**Những nguyên tắc cốt lõi:**

1. **TTL của time series tính theo timeField**, không tự lấy thời điểm insert hoặc một field expireAt khác.
2. **Expiration của measurement và thời điểm xóa bucket khác nhau.** TTL monitor chạy nền, không đưa ra bảo đảm xóa vật lý đúng một giây.
3. **Granularity ảnh hưởng phạm vi bucket**, không thay cho retention. Bucket span lớn có thể làm dữ liệu quá tuổi còn tồn tại lâu hơn.
4. **expireAfterSeconds ở cấp collection** có thể được tạo ban đầu hoặc thay đổi bằng collMod. Dùng **"off"** để tắt trên phiên bản hỗ trợ, không dùng số 0.
5. **Partial TTL time series** ở phiên bản phù hợp dùng filter trên metaField để cho một nhóm dữ liệu hết hạn **sớm hơn**; nó không thể giữ một nhóm lâu hơn TTL toàn collection ngắn hơn.
6. **Backfill và sensor clock skew** có thể khiến dữ liệu bị xóa sớm hoặc tồn tại lâu ngoài ý định. Phải xác định event time hay ingest time.
7. **TTL không phải query filter, archive hay downsampling job.** Mỗi trách nhiệm cần cơ chế và SLA riêng.
8. **Giảm retention có thể gây xóa dữ liệu lớn và không thể rollback bằng cách tăng TTL lại.** Trước thay đổi phải xem backup, I/O, replication và các báo cáo phụ thuộc.
9. **TTL MongoDB không tự xóa mọi bản sao trong backup/cache/warehouse.** Chính sách lưu giữ và xóa cần bao phủ toàn bộ vòng đời dữ liệu.
10. **Theo dõi TTL bằng dữ liệu thực tế và metric phù hợp**, không chỉ nhìn expireAfterSeconds hoặc kích thước file trên đĩa.

Khi thiết kế đúng timeField, retention window, bucketing, partial TTL và pipeline tổng hợp, MongoDB time series collection có thể giữ hiệu quả dữ liệu ngắn hạn mà vẫn hỗ trợ phân tích dài hạn. Điểm quan trọng nhất không phải là “dữ liệu biến mất sau bao nhiêu giây?”, mà là **“dữ liệu cần được sử dụng đến khi nào, MongoDB bắt đầu được phép loại bỏ nó lúc nào, và toàn hệ thống đã xử lý xong trước khi nó thực sự mất chưa?”**.
