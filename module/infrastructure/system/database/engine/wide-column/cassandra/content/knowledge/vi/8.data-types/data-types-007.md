# timestamp, date, time và độ chính xác thời gian trong Apache Cassandra

Khi một hệ thống Java ghi dữ liệu vào **Apache Cassandra**, câu hỏi “giá trị này là thời gian nào?” quan trọng không kém câu hỏi “giá trị này chính xác đến đâu?”. Một **thời điểm xảy ra sự kiện**, một **ngày theo lịch** và một **giờ trong ngày** là ba loại dữ liệu khác nhau. Cassandra cung cấp ba kiểu CQL chính tương ứng: `timestamp`, `date` và `time`.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trong kiến trúc wide-column phân tán, dữ liệu thường được chia theo **partition key** và sắp xếp trong phân vùng theo **clustering columns**. Chọn đúng kiểu thời gian giúp ứng dụng Java giữ được ý nghĩa của dữ liệu; chọn đúng bucket, khóa và truy vấn giúp đọc/ghi hiệu quả. Replication, consistency, compaction và repair không tự sửa được một thời điểm đã bị chuyển sai múi giờ hoặc mất độ chính xác khi mã hóa.

## 1. Nhận diện ba kiểu trước khi viết CQL

| Kiểu CQL | Giá trị biểu diễn | Độ phân giải / cách lưu | Java Driver 4.x | Ví dụ nghiệp vụ |
|---|---|---|---|---|
| **`timestamp`** | Một **thời điểm tuyệt đối** trên trục thời gian | Số mili giây có dấu tính từ Unix epoch | `Instant` | `created_at`, `paid_at`, `occurred_at` |
| **`date`** | Một **ngày lịch**, không chứa giờ/múi giờ | Số ngày theo lịch, không có thành phần giờ | `LocalDate` | Ngày sinh, ngày hạch toán, `event_day` bucket |
| **`time`** | Một **giờ trong ngày**, không chứa ngày/múi giờ | Nano giây tính từ 00:00:00, trong một ngày | `LocalTime` | Giờ mở cửa, giờ bắt đầu ca, khung giờ hằng ngày |

Ba câu hỏi mẫu:

- “Khách đặt hàng lúc **2026-11-21 09:00:00 UTC**”: cần **`timestamp`** vì đó là một điểm duy nhất trên trục thời gian.
- “Ngày sinh là **2001-05-20**”: cần **`date`** vì không có ý nghĩa về múi giờ hay giờ sinh.
- “Cửa hàng mở cửa lúc **08:30:00** mỗi ngày”: cần **`time`**, thường đi cùng thông tin **múi giờ của cửa hàng** ở cấp mô hình.

`time` có đơn vị mã hóa đến nano giây **không có nghĩa** Cassandra ghi nhận thời điểm thực với độ chính xác nano giây. Nó chỉ cho phép biểu diễn một *giờ trong ngày* có đến 9 chữ số phần giây. Ngược lại, `timestamp` biểu diễn thời điểm thực nhưng chỉ có độ phân giải **mili giây**. Cả ba kiểu đều không lưu trực tiếp tên múi giờ gốc như `Asia/Ho_Chi_Minh`.

## 2. timestamp: một thời điểm tuyệt đối, chính xác đến mili giây

### 2.1. Unix epoch và timestamp CQL

CQL `timestamp` lưu **số nguyên 64 bit có dấu** biểu diễn số **mili giây** kể từ **1970-01-01T00:00:00Z** (Unix epoch). Giá trị dương nằm sau epoch; giá trị âm nằm trước epoch. Cassandra diễn giải `timestamp` như một thời điểm độc lập với cách hiển thị của máy khách.

Ví dụ các cách viết cùng một thời điểm:

~~~text
2026-11-21T08:00:00Z
2026-11-21T15:00:00+07:00
~~~

Hai chuỗi trên cùng trỏ đến một thời điểm: 08:00 UTC, tương ứng 15:00 ở UTC+07:00. Sau khi parse thành `timestamp`, Cassandra **không giữ lại** việc người dùng đã nhập `Z` hay `+07:00`.

Nếu bắt buộc nhớ **múi giờ người dùng chọn**, hãy lưu thêm `zone_id text`, ví dụ `Asia/Ho_Chi_Minh`. Offset `+07:00` là mức lệch thời gian tại một thời điểm, **không thay thế** tên vùng múi giờ có quy tắc lịch sử và giờ mùa hè.

### 2.2. Tại sao timestamp chỉ giữ mili giây?

Một giây có các cấp nhỏ:

| Đơn vị | Giá trị trong một giây | Số chữ số phần giây |
|---|---:|---:|
| Mili giây (ms) | 1.000 | 3 |
| Micro giây (µs) | 1.000.000 | 6 |
| Nano giây (ns) | 1.000.000.000 | 9 |

Java `Instant` có thể mang phần giây tới nano giây, nhưng **CQL `timestamp` chỉ có độ phân giải mili giây**. Nếu ứng dụng gửi:

~~~text
2026-11-21T08:30:15.123456789Z
~~~

thì giá trị `timestamp` lưu được thời điểm ở mức:

~~~text
2026-11-21T08:30:15.123Z
~~~

Phần nhỏ hơn mili giây **không thể được bảo toàn** bằng kiểu `timestamp`. Khi truy vấn hoặc tính toán cần phân biệt các sự kiện chỉ cách nhau vài micro giây, hai sự kiện có thể nhận **cùng một timestamp lưu trữ**.

Ví dụ Java:

~~~java
import java.time.Instant;

Instant source = Instant.parse("2026-11-21T08:30:15.123456789Z");

long epochMillis = source.toEpochMilli();  // mili giây
Instant storedPrecision = Instant.ofEpochMilli(epochMillis);

System.out.println(source);          // 2026-11-21T08:30:15.123456789Z
System.out.println(storedPrecision); // 2026-11-21T08:30:15.123Z
~~~

Đoạn mã cho thấy phép chuyển sang mili giây theo API Java. Java Driver ánh xạ `Instant` sang độ phân giải của CQL `timestamp`; kiểm tra vòng ghi/đọc của phiên bản driver và tránh giả định nano giây sẽ được giữ lại.

**Không nhầm độ phân giải lưu trữ với độ chính xác của đồng hồ.** Dù giá trị có phần `.123` ms, đồng hồ host có thể lệch vài giây, client có thể nhận dữ liệu muộn, và sự kiện nguồn có thể được lấy mẫu mỗi phút.

### 2.3. Luôn ghi rõ múi giờ khi nhập literal

CQL có thể nhận literal thời gian theo chuỗi, ví dụ:

~~~cql
CREATE TABLE events_by_id (
    event_id uuid PRIMARY KEY,
    occurred_at timestamp,
    message text
);

INSERT INTO events_by_id (event_id, occurred_at, message)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T08:30:15.123Z',
    'Sự kiện được ghi theo UTC'
);

SELECT occurred_at, message
FROM events_by_id
WHERE event_id = 11111111-1111-4111-8111-111111111111;
~~~

Ưu tiên literal có **`Z` hoặc offset tường minh**. Một chuỗi như `'2026-11-21 08:30:15'` không kèm offset có thể bị diễn giải theo cấu hình/môi trường parse hoặc công cụ truy cập. Bỏ offset trong một hệ thống có nhiều service, region hoặc người vận hành là nguồn lỗi khó phát hiện.

Giá trị trả về có thể được công cụ hiển thị ở UTC hoặc một timezone cục bộ; **cách hiển thị không phải bằng chứng Cassandra đã đổi thời điểm lưu**. Hãy chuyển thành UTC/zone nghiệp vụ có chủ đích khi trình bày trên UI.

## 3. date: ngày theo lịch, không có thời điểm tuyệt đối

CQL `date` biểu diễn một ngày như `2026-11-21` và không chứa giờ, offset hoặc múi giờ. Ở Java, nó tương ứng **`LocalDate`**.

~~~cql
CREATE TABLE people_by_id (
    person_id uuid PRIMARY KEY,
    full_name text,
    birth_date date
);

INSERT INTO people_by_id (person_id, full_name, birth_date)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'Nguyễn Minh Anh',
    '2001-05-20'
);
~~~

Ngày sinh theo lịch `2001-05-20` không nên lưu dưới dạng “nửa đêm UTC” chỉ vì Java dễ tạo một `Instant`: một ứng dụng ở timezone khác có thể hiển thị thành **ngày hôm trước**, làm thay đổi ý nghĩa của ngày sinh.

Các trường hợp phù hợp cho `date`: ngày sinh, ngày nghỉ lễ, ngày khóa sổ theo hợp đồng, ngày hiệu lực của chính sách, **khóa bucket ngày** phục vụ đọc chuỗi sự kiện.

### 3.1. date làm bucket cho dữ liệu phân tán

Trong Cassandra, một bảng theo luồng sự kiện thường có partition key `(device_id, event_day)`. Cột `event_day date` trong ví dụ dưới đây **không** là thời điểm sự kiện; nó là nhãn phân vùng của các sự kiện thuộc một ngày.

Cần định nghĩa ngày nào:

- **Ngày UTC:** `occurredAt.atZone(ZoneOffset.UTC).toLocalDate()`.
- **Ngày địa phương của chi nhánh:** `occurredAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate()`.
- **Ngày hạch toán:** có thể chịu quy tắc nghiệp vụ khác với hai cách trên, ví dụ ngày đóng sổ thay đổi sau giờ cutoff.

Cassandra không tự biết `event_day` được tính theo quy tắc nào. Nếu client A dùng UTC còn client B dùng Asia/Ho_Chi_Minh, cùng một `occurred_at` có thể bị đặt ở **hai partition khác nhau**.

Ví dụ: `2026-11-20T18:30:00Z` là **2026-11-21 01:30** tại Việt Nam (UTC+07). Ngày theo UTC là 20/11, còn ngày theo Việt Nam là 21/11. Hãy thống nhất một quy tắc cho cả **ghi** và **truy vấn**.

### 3.2. Độ dài ngày địa phương có thể không phải 24 giờ

Với múi giờ có quy tắc daylight saving time (DST), một ngày theo lịch có thể chứa **23 hoặc 25 giờ thực**. Vì vậy, nếu cần khoảng `[đầu ngày địa phương, đầu ngày tiếp theo)`, nên chuyển **hai đầu mút theo ZoneId** sang `Instant` thay vì cộng cố định 24 giờ từ đầu ngày.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("America/New_York");
LocalDate businessDay = LocalDate.parse("2026-11-01");

Instant from = businessDay.atStartOfDay(zone).toInstant();
Instant until = businessDay.plusDays(1).atStartOfDay(zone).toInstant();

// Đây là khoảng trọn vẹn của ngày theo múi giờ nghiệp vụ.
~~~

Đây là cơ sở quan trọng cho truy vấn theo ngày, tính doanh thu và phân bucket. **`LocalDate` không có múi giờ**, còn việc chuyển thành khoảng `Instant` phải cung cấp múi giờ rõ ràng.

## 4. time: giờ trong ngày, độ phân giải nano giây

CQL `time` biểu diễn thời gian trong phạm vi một ngày: `00:00:00` đến trước `24:00:00`, với phần thập phân của giây có thể tới **9 chữ số**. Nó được biểu diễn bằng **số nano giây kể từ nửa đêm**, không gắn với ngày hoặc múi giờ.

Ví dụ:

~~~cql
CREATE TABLE store_hours_by_store_weekday (
    store_id uuid,
    weekday tinyint,
    open_at time,
    close_at time,
    zone_id text,
    PRIMARY KEY ((store_id), weekday)
);

INSERT INTO store_hours_by_store_weekday (
    store_id, weekday, open_at, close_at, zone_id
) VALUES (
    33333333-3333-4333-8333-333333333333,
    1,
    '08:30:00.000000000',
    '22:00:00.000000000',
    'Asia/Ho_Chi_Minh'
);
~~~

Trong ví dụ, ứng dụng tự quy định `weekday = 1` có nghĩa là **thứ Hai** theo một quy ước (ví dụ ISO 8601). Cassandra không tự liên kết `tinyint 1` với thứ Hai. `open_at` và `close_at` cũng không mang timezone; thông tin `zone_id` giúp ứng dụng quyết định chúng được hiểu theo múi giờ cửa hàng nào.

### 4.1. time không phải timestamp rút gọn

Giá trị `08:30:00` trong cột `time` **không đủ** để biết thời điểm tuyệt đối. Để chuyển thành `Instant`, cần ít nhất:

1. Ngày theo lịch (`LocalDate`).
2. Giờ trong ngày (`LocalTime`).
3. Múi giờ hoặc offset và chính sách xử lý DST.

Nếu là ca đêm từ 22:00 đến 06:00, không thể chỉ lấy `close_at - open_at` trong cùng ngày để suy ra thời lượng chính xác. Ứng dụng phải xác định giờ kết thúc thuộc **ngày sau**, rồi tính khoảng giữa các `Instant` tương ứng. Với DST, thời lượng thực có thể khác số giờ đọc trên đồng hồ.

`time` hợp với cấu hình lịch hằng ngày, nhãn giờ địa phương, khung giờ mở cửa. Nếu cần ghi thời điểm một API request được xử lý, dùng **`timestamp`**; nếu cần đo độ dài xử lý, dùng số nguyên duration theo đơn vị đã định nghĩa hoặc kiểu thích hợp chứ không lấy một `time` làm khoảng thời gian.

### 4.2. time chính xác đến nano giây nhưng giới hạn bởi nguồn

Một giá trị CQL `time` có thể lưu `'08:30:15.123456789'` và Java ánh xạ qua `LocalTime` với phần nano giây. Điều này khác với `timestamp`, chỉ giữ tới mili giây. Tuy nhiên:

- Không có thông tin ngày nên `time` không thể tự xác định “trước/sau” giữa các ngày.
- Nó không biết offset hay timezone.
- Thiết bị hoặc ứng dụng có thể chỉ đo được tới giây/mili giây; lưu thêm chữ số 0 không làm phép đo chính xác hơn.
- Định dạng hiển thị có thể bỏ các chữ số 0 cuối, nhưng giá trị giờ trong ngày vẫn như nhau.

## 5. CQL thực hành: kết hợp date và timestamp cho bảng sự kiện

Yêu cầu: **“Lấy 100 sự kiện mới nhất của một thiết bị trong một ngày UTC; có thể lọc sự kiện xảy ra trong một khoảng giờ.”**

~~~cql
CREATE TABLE events_by_device_day (
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    local_clock_time time,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Ý nghĩa mỗi cột thời gian:

| Cột | Kiểu | Vai trò |
|---|---|---|
| `event_day` | `date` | **Partition bucket** theo ngày UTC, giúp giới hạn độ lớn phân vùng |
| `occurred_at` | `timestamp` | **Clustering column** chính để sắp thứ tự theo thời điểm tuyệt đối |
| `event_id` | `uuid` | Khóa phân biệt hai sự kiện trùng cùng mili giây |
| `local_clock_time` | `time` | Giờ trong ngày do thiết bị/bối cảnh nguồn cung cấp; không tham gia thứ tự toàn thời gian |

Với dữ liệu nguồn có độ phân giải dưới mili giây, **nhiều sự kiện có thể cùng `occurred_at`**. `event_id` là clustering column phụ để tránh ghi lên cùng primary key. Nó không có nghĩa UUID ngẫu nhiên sắp sự kiện đúng thứ tự micro giây khi timestamp bằng nhau; nếu yêu cầu đó thực sự tồn tại cần thiết kế thêm thứ tự nguồn hoặc một cột số nguyên độ phân giải cao.

~~~cql
INSERT INTO events_by_device_day (
    device_id, event_day, occurred_at, event_id,
    local_clock_time, event_type, payload
) VALUES (
    44444444-4444-4444-8444-444444444444,
    '2026-11-21',
    '2026-11-21T08:30:15.123Z',
    55555555-5555-4555-8555-555555555555,
    '15:30:15.123456789',
    'TEMPERATURE_READING',
    '{"celsius":23.5}'
);
~~~

Ở ví dụ, `occurred_at` là 08:30 UTC và `local_clock_time` là 15:30:15.123456789 theo đồng hồ nguồn ở UTC+07:00. Nhưng vì `time` **không mang timezone**, cặp giá trị chỉ có ý nghĩa khi hệ thống đã biết rõ quy tắc của nguồn; không được lấy `local_clock_time` làm một thời điểm UTC mới.

### 5.1. Đọc theo partition key và clustering range

~~~cql
SELECT occurred_at, event_id, event_type, local_clock_time
FROM events_by_device_day
WHERE device_id = 44444444-4444-4444-8444-444444444444
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Truy vấn có **đầy đủ partition key** `(device_id, event_day)` và giới hạn bằng **clustering column** `occurred_at`. Khoảng **nửa mở** `[08:00, 09:00)` giúp các khung giờ liền nhau không lấy trùng sự kiện ở đúng ranh giới.

Vì bảng sắp `occurred_at DESC`, các dòng trong phân vùng được đọc theo hướng mới đến cũ. Nếu cần lấy tất cả sự kiện của thiết bị trong **nhiều ngày**, ứng dụng phải truy vấn các phân vùng ngày liên quan rồi kết hợp/điều tiết kết quả, hoặc dùng một đường truy cập khác phù hợp.

Đổi `occurred_at` từ `timestamp` sang kiểu khác không khiến truy vấn “tất cả thiết bị của một ngày” hay “mọi sự kiện có event_type = X” tự trở nên hiệu quả. Cassandra yêu cầu thiết kế bảng theo **mẫu truy vấn**.

### 5.2. Bucket ngày và giới hạn kích thước phân vùng

Một partition `(device_id, event_day)` chứa các sự kiện của một thiết bị trong một ngày. Nếu thiết bị gửi 1 triệu sự kiện mỗi ngày, bucket ngày có thể vẫn quá lớn với khối lượng row/payload và pattern đọc. Có thể cần bucket theo giờ, theo số shard hoặc tổ chức dữ liệu khác dựa trên throughput và retention.

Chọn `date` làm khóa bucket chỉ đảm bảo **cách nhóm dữ liệu**, không tự giới hạn kích thước phân vùng. Đồng thời, `event_day` phải được tính **đúng từ thời điểm dùng làm thứ tự của hệ thống** và theo timezone đã thống nhất, kể cả khi dữ liệu đến muộn hoặc được backfill.

## 6. Java Driver 4.x: Instant, LocalDate và LocalTime

Các ánh xạ thường dùng trong Apache Cassandra Java Driver 4.x:

| CQL | Java | Bind vào `BoundStatementBuilder` | Đọc từ `Row` |
|---|---|---|---|
| `timestamp` | `Instant` | `setInstant(index, value)` | `getInstant(column)` |
| `date` | `LocalDate` | `setLocalDate(index, value)` | `getLocalDate(column)` |
| `time` | `LocalTime` | `setLocalTime(index, value)` | `getLocalTime(column)` |

### 6.1. Ghi sự kiện với UTC bucket nhất quán

Giả sử `session` là một `CqlSession` đã kết nối cluster và chọn đúng keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Được cấu hình bên ngoài ví dụ.

UUID deviceId = UUID.fromString("44444444-4444-4444-8444-444444444444");
UUID eventId = UUID.fromString("55555555-5555-4555-8555-555555555555");

Instant occurredAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
LocalTime localClock = LocalTime.parse("15:30:15.123456789");

PreparedStatement ps = session.prepare(
    "INSERT INTO events_by_device_day "
  + "(device_id, event_day, occurred_at, event_id, "
  + " local_clock_time, event_type, payload) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement statement = ps.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setLocalTime(4, localClock)
    .setString(5, "TEMPERATURE_READING")
    .setString(6, "{\"celsius\":23.5}")
    .build();

session.execute(statement);
~~~

**Vì sao chọn `Instant` thay cho `LocalDateTime`?** `Instant` xác định rõ một điểm tuyệt đối. `LocalDateTime` chỉ chứa ngày và giờ địa phương, không có zone/offset; cùng `LocalDateTime` có thể ứng với hai thời điểm trong ngày đổi DST, hoặc không ứng với thời điểm nào khi đồng hồ nhảy qua một giờ.

Nếu nguồn dữ liệu có ngày/giờ địa phương, chuyển qua `ZonedDateTime` hoặc áp dụng `ZoneId` và chính sách DST rõ ràng **trước** khi bind `Instant`.

### 6.2. Truy vấn theo khoảng thời gian bằng prepared statement

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;

Instant from = Instant.parse("2026-11-21T08:00:00Z");
Instant until = Instant.parse("2026-11-21T09:00:00Z");

PreparedStatement range = session.prepare(
    "SELECT occurred_at, event_id, local_clock_time, event_type "
  + "FROM events_by_device_day "
  + "WHERE device_id = ? AND event_day = ? "
  + "AND occurred_at >= ? AND occurred_at < ? LIMIT 100");

for (Row row : session.execute(range.bind(
        deviceId, LocalDate.parse("2026-11-21"), from, until))) {
    Instant storedAt = row.getInstant("occurred_at");
    UUID storedId = row.getUuid("event_id");

    LocalTime reportedClock = row.isNull("local_clock_time")
        ? null : row.getLocalTime("local_clock_time");
}
~~~

Prepared statement giúp bind đúng kiểu, không cần nối chuỗi định dạng thời gian thành câu lệnh CQL. Nếu có thông tin không chắc chắn, hãy kiểm tra null trước khi đọc cột. Khóa `event_day` phải được tính theo **cùng timezone quy ước với lúc ghi**; `Instant from/until` chỉ là cận của clustering range trong một partition được chọn.

### 6.3. Chuyển từ ngày/giờ địa phương sang Instant

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

LocalDate day = LocalDate.parse("2026-11-21");
LocalTime clock = LocalTime.parse("15:30:15");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant absolute = day.atTime(clock).atZone(zone).toInstant();
// 2026-11-21T08:30:15Z
~~~

Đoạn mã hợp lý cho ví dụ Việt Nam, nhưng với vùng múi giờ có DST, `atZone(zone)` có quy tắc mặc định khi gặp giờ trùng hoặc giờ không tồn tại. Với lịch hẹn, thanh toán hoặc deadline, phải quy định cách giải quyết các trường hợp này thay vì phụ thuộc không kiểm soát vào mặc định.

## 7. Phân biệt timestamp nghiệp vụ với Cassandra write timestamp

Đây là một trong những nhầm lẫn quan trọng nhất khi học Cassandra.

| Thuật ngữ | Đơn vị / biểu diễn | Được dùng để làm gì? |
|---|---|---|
| CQL **`timestamp`** trong cột `occurred_at` | **Mili giây** từ Unix epoch | Dữ liệu nghiệp vụ: sự kiện xảy ra khi nào |
| CQL **`time`** trong cột `local_clock_time` | **Nano giây từ nửa đêm** | Một giờ trong ngày |
| **Cassandra write timestamp** trong metadata cell | **Micro giây** | Phân giải phiên bản ghi/xung đột theo quy tắc last-write-wins |
| **`USING TIMESTAMP`** trong CQL | Số nguyên **micro giây** | Chỉ định write timestamp của mutation |
| Hàm **`WRITETIME(column)`** | Trả về **micro giây** | Quan sát write timestamp của cột dữ liệu |

`WRITETIME()` không nói cho bạn “sự kiện xảy ra lúc nào”. Nó cho biết **write timestamp của cell** liên quan đến cột được hỏi, và write timestamp có thể được chỉ định ở client hoặc tạo khi ghi.

Ví dụ truy vấn:

~~~cql
SELECT occurred_at,
       event_type,
       WRITETIME(event_type) AS event_type_write_us
FROM events_by_device_day
WHERE device_id = 44444444-4444-4444-8444-444444444444
  AND event_day = '2026-11-21'
LIMIT 5;
~~~

Lưu ý: `WRITETIME(event_type)` áp dụng cho **cột thường** `event_type`. Không dùng `WRITETIME(occurred_at)` ở bảng này vì `occurred_at` là **primary key/clustering column**.

Các lỗi điển hình:

- Ứng dụng nhận số mili giây rồi truyền trực tiếp vào `USING TIMESTAMP` — giá trị write timestamp sẽ sai đơn vị khoảng **1.000 lần**.
- Ứng dụng nhận write timestamp micro giây từ `WRITETIME` rồi parse như epoch milliseconds — sẽ tạo thời gian rất xa kỳ vọng hoặc lỗi miền.
- Ứng dụng dùng `USING TIMESTAMP` để “lưu giờ sự kiện”, vô tình thay đổi **thứ tự xung đột last-write-wins**, có thể khiến bản ghi mới không thắng bản ghi cũ.

Thông thường, dùng **cột `occurred_at timestamp` riêng** cho thời gian nghiệp vụ và để Cassandra/driver quản lý write timestamp theo cấu hình ghi. Chỉ dùng client-supplied write timestamps khi có lý do rõ ràng và đã hiểu tác động đến cập nhật, xóa, TTL và reconciliation.

## 8. Retry, timestamp trùng và thứ tự trong hệ phân tán

### 8.1. Timestamp có độ phân giải mili giây không phải khóa duy nhất

Nếu một thiết bị phát 10.000 sự kiện trong một giây, nhiều sự kiện có thể có cùng một giá trị `timestamp` đến mili giây. Với bảng có khóa chính chỉ gồm `((device_id, day), occurred_at)`, hai sự kiện có cùng `occurred_at` sẽ có **cùng primary key** và có thể ghi đè/cập nhật cùng dòng.

Bởi vậy, ví dụ dùng:

~~~cql
PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
~~~

Trong đó `event_id uuid` là thành phần khóa cuối để phân biệt sự kiện. ID phải được gán **một lần** cho một sự kiện và tái sử dụng trong các lần retry.

Nếu cần **thứ tự tuyệt đối đến micro/nano giây**, kết hợp `timestamp + uuid` chỉ giải quyết **độ duy nhất**, không bảo đảm thứ tự sâu hơn mili giây. Một lựa chọn là có `event_epoch_ns bigint` hoặc `sequence_no bigint` làm clustering column theo hợp đồng nguồn, kèm event ID chống trùng và kiểm tra miền/tràn. Độ chính xác của giá trị nguồn và khả năng sắp thứ tự đa writer vẫn cần được chứng minh riêng.

### 8.2. Khi nào dùng timeuuid?

`timeuuid` là UUID v1 có thành phần thời gian và có thể dùng làm clustering column cho timeline **theo thời điểm sinh ID**. Nó không thay `occurred_at timestamp` nếu hệ thống cần sắp theo **thời điểm thực sự xảy ra ở nguồn**; sự kiện đến muộn có thể mang ID lúc nhận.

Chọn mô hình theo truy vấn:

| Yêu cầu | Lựa chọn khóa khởi đầu |
|---|---|
| Timeline theo lúc server sinh ID | `timeuuid` clustering key |
| Timeline theo lúc sự kiện xảy ra, tới ms | `timestamp` + `uuid` clustering columns |
| Timeline theo số thứ tự nguồn có tính ổn định | `bigint sequence_no` + `uuid`, có hợp đồng sequence |
| Định danh sự kiện để retry không tạo dòng trùng | `uuid` ổn định, dùng lại cùng primary key |

Cassandra không cung cấp sẵn một thứ tự thực tế duy nhất giữa các sự kiện trên mọi node. Đồng hồ các host có thể lệch, dữ liệu mạng có thể đến muộn và một ID dạng thời gian không tạo ra trật tự nhân quả toàn hệ thống.

### 8.3. Lỗi timeout không xác nhận ghi thất bại

Một lệnh ghi có thể được áp dụng ở vài replica nhưng client nhận timeout trước khi có đủ xác nhận. Nếu retry mà tạo `event_id` hoặc `occurred_at` mới thì dữ liệu có thể xuất hiện dưới **khóa mới**, thành sự kiện trùng.

Giữ cố định **partition key, clustering key và giá trị nghiệp vụ** trong cùng một attempt chain. Nếu có nhiều bảng theo truy vấn, cần cơ chế bảo đảm đồng nhất/đối soát vì nhiều lệnh ghi riêng không tự trở thành giao dịch ACID qua nhiều partition. Consistency level điều chỉnh số replica phải xác nhận, **không tự sửa** timestamp nguồn hoặc chính sách retry.

## 9. Những lỗi thời gian thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Dùng `timestamp` để lưu ngày sinh | Ngày có thể đổi khi hiển thị timezone khác | Dùng `date` |
| Dùng `date` làm thời điểm thanh toán | Mất giờ, phút, giây và thứ tự giao dịch | Dùng `timestamp` |
| Dùng `time` để lưu thời điểm request | Thiếu ngày, không truy được thời điểm tuyệt đối | Dùng `timestamp` |
| Cho rằng `timestamp` giữ micro/nano giây | Các giá trị gần nhau bị giảm độ phân giải | Chọn mô hình bổ sung nếu cần |
| Parse chuỗi thời gian không offset từ nhiều vùng | Sai lệch múi giờ không nhất quán | Dùng `Instant`, ISO-8601 có `Z`/offset |
| Dùng `LocalDateTime` như một `Instant` | Giờ DST trùng/không tồn tại gây nhập nhằng | Cần `ZoneId` và chính sách DST |
| Tính `event_day` theo UTC ở ghi, theo giờ địa phương ở đọc | Không tìm thấy partition cần truy vấn | Đồng nhất quy tắc bucket |
| Cho rằng mọi ngày địa phương dài 24 giờ | Sai khoảng truy vấn khi đổi DST | Tính hai mốc đầu ngày theo `ZoneId` |
| Chỉ dùng `occurred_at` làm clustering key trong sự kiện tần suất cao | Sự kiện trùng ms ghi vào một row | Thêm ID/sequence phân biệt |
| Dùng `WRITETIME` làm thời gian sự kiện | Lấy thời điểm/version ghi cell thay vì dữ liệu nguồn | Lưu `occurred_at timestamp` |
| Truyền epoch millis vào `USING TIMESTAMP` | Sai đơn vị micro giây, phá quy tắc cập nhật | Dùng write timestamp micro giây khi thực sự cần |
| Sinh lại thời gian và UUID trong retry | Có thể tạo nhiều dòng cho một sự kiện | Giữ cùng ID và khóa trong retry |
| Truy vấn toàn cluster bằng cột `timestamp` thường | Không có đường truy cập theo partition key | Tạo bảng/chỉ mục phù hợp với workload |

## 10. Ảnh hưởng vận hành: retention, TTL, compaction và repair

Đối với bảng log/sự kiện có thời gian, tuổi dữ liệu và kích thước partition cần được thiết kế cùng truy vấn:

- **TTL** trong CQL được chỉ định theo **giây** để quyết định khi nào cell hết hạn. TTL không dùng đơn vị mili giây của `timestamp`, cũng không được tự suy ra từ một cột `expires_at timestamp` nếu không có logic ghi riêng.
- **Compaction** tổ chức SSTable và xử lý dữ liệu đã hết hạn/tombstone theo cơ chế lưu trữ. Nó không đổi mốc thời gian nghiệp vụ hoặc đưa `date` bucket sai sang partition đúng.
- **Repair** giúp đồng bộ trạng thái replica; không khôi phục phần nano giây đã mất khi mã hóa `timestamp`.
- **Replication và consistency level** quyết định cách dữ liệu được sao chép và xác nhận; không làm đồng hồ mọi client chạy chính xác như nhau hoặc bảo đảm truy vấn xuyên nhiều bucket cho ảnh chụp nhất quán tuyệt đối.
- **Retention** cần xem xét theo nhu cầu kiểm toán, chi phí, GDPR/chính sách dữ liệu và backfill. Không đặt TTL ngắn cho nhật ký cần lưu dài hạn rồi coi compaction có thể cứu dữ liệu đã hết hạn.

Nếu hệ thống truy vấn theo thời gian rất nhiều, hãy đo **rows/partition**, **bytes/partition**, **p95/p99 latency**, tombstone, throughput đọc/ghi và phân phối token. Chọn bucket ngày/giờ phù hợp tải thay vì giả định một kiểu `date` sẽ tự tối ưu hóa.

## 11. Bài tập tình huống

### Bài 1 — Chọn kiểu

Cho bốn cột: `birth_day` (ngày sinh), `payment_completed_at` (thời điểm thanh toán), `opening_time` (giờ mở cửa lặp hằng ngày) và `sensor_received_at` (thời điểm server nhận mẫu).

**Đáp án:** `birth_day date`, `payment_completed_at timestamp`, `opening_time time`, `sensor_received_at timestamp`. Nếu có giờ địa phương cần chuyển thành thời điểm tuyệt đối, lưu/biết thêm `zone_id`.

### Bài 2 — Mất độ chính xác

Một service Java tạo `Instant.parse("2026-11-21T08:00:00.123456789Z")` và lưu vào `timestamp`.

**Câu hỏi:** Truy vấn có thể phân biệt sự kiện này với một sự kiện `08:00:00.123987654Z` chỉ nhờ cột timestamp không?

**Đáp án:** không. Cả hai nằm trong cùng mili giây `.123` khi chuyển sang độ phân giải của `timestamp`. Cần cột thứ tự/ID phụ hoặc đơn vị độ phân giải cao hơn theo hợp đồng nguồn.

### Bài 3 — Bucket sai ngày

Một sự kiện `2026-11-20T18:30:00Z` được bucket theo UTC. Một client khác tính ngày theo `Asia/Ho_Chi_Minh`.

**Câu hỏi:** Hai client sẽ gửi truy vấn tới bucket nào?

**Đáp án:** UTC là `2026-11-20`; ở Việt Nam là `2026-11-21`. Cần một quy tắc bucket thống nhất, không để client tự chọn timezone.

### Bài 4 — Cửa hàng ở vùng DST

Cửa hàng mở cửa lúc 01:30 ở một vùng có đổi giờ mùa hè. Một ngày nào đó đồng hồ có thể xuất hiện 01:30 **hai lần**.

**Câu hỏi:** `time '01:30:00'` có đủ xác định lịch hẹn tuyệt đối không?

**Đáp án:** không. Cần ngày, `ZoneId` và quy tắc chọn offset trong trường hợp giờ trùng; hoặc lưu `Instant` đã được xác nhận cho cuộc hẹn cụ thể.

### Bài 5 — WRITETIME

Một dòng có `occurred_at = '2026-11-21T08:30:00Z'` nhưng được backfill vào Cassandra một tuần sau. Khi truy vấn `WRITETIME(event_type)`, nó có thể trùng `occurred_at` không?

**Đáp án:** không bắt buộc. `WRITETIME` là metadata phiên bản ghi (micro giây), còn `occurred_at` là dữ liệu nghiệp vụ (mili giây). Nếu không chỉ định client write timestamp, chúng thường đại diện hai thời điểm khác nhau khi có backfill.

## 12. Checklist trước khi triển khai kiểu thời gian

- [ ] Giá trị là **thời điểm tuyệt đối**, **ngày lịch** hay **giờ trong ngày**?
- [ ] Cột `timestamp` có cần độ phân giải dưới mili giây? Nếu có, đã thiết kế thêm ID/sequence/epoch đơn vị phù hợp?
- [ ] Java dùng `Instant` cho thời điểm, `LocalDate` cho ngày, `LocalTime` cho giờ?
- [ ] Các literal CQL thời điểm đều có `Z` hoặc offset rõ ràng?
- [ ] Nếu nghiệp vụ cần biết timezone gốc, có lưu `ZoneId`/quy tắc timezone riêng?
- [ ] Nếu chuyển `LocalDate + LocalTime` thành `Instant`, đã xử lý DST và giờ trùng/không tồn tại?
- [ ] Bucket `date` được tính nhất quán từ đúng nguồn thời gian và một timezone đã định nghĩa?
- [ ] Truy vấn theo thời gian xác định **đầy đủ partition key** và so sánh **clustering columns** hợp lệ?
- [ ] Truy vấn theo khoảng sử dụng **[start, end)** để kiểm soát ranh giới?
- [ ] Nhiều sự kiện trùng mili giây đã có `event_id` hoặc key phụ để tránh ghi đè?
- [ ] Retry giữ nguyên `event_id`, `occurred_at` và bucket thay vì sinh lại?
- [ ] Đã phân biệt **CQL timestamp (ms)** với **WRITETIME/USING TIMESTAMP (µs)**?
- [ ] Đã xem xét kích thước partition, TTL tính theo giây, retention, compaction, repair và consistency theo tải thực tế?

**Ghi nhớ:** **`timestamp`** lưu một **thời điểm** với độ phân giải **mili giây**; **`date`** lưu **ngày theo lịch**; **`time`** lưu **giờ trong ngày** có thể đến **nano giây** nhưng không mang ngày hoặc timezone. Với Cassandra, đúng kiểu thời gian mới giữ được ý nghĩa dữ liệu, còn partition bucket, clustering key và xử lý retry nhất quán mới cho phép truy vấn thời gian đúng và hiệu quả trên hệ phân tán.

