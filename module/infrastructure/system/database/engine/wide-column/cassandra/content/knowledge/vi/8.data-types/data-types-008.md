# duration và giới hạn ngữ nghĩa theo thao tác hỗ trợ trong Apache Cassandra

Trong Apache Cassandra, **`duration` không đơn giản là một số giây**. Đây là kiểu CQL biểu diễn một khoảng theo ba thành phần: **tháng, ngày và nano giây**. Sự phân tách này quan trọng vì một tháng có số ngày thay đổi, còn một ngày lịch có thể dài 23 hoặc 25 giờ trong múi giờ có daylight saving time (DST). Do đó, không phải mọi khoảng thời gian đều có thể đổi thành một số mili giây cố định, so sánh lớn nhỏ hoặc dùng làm khóa sắp xếp.

Bài học thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu của module bao gồm kiến trúc phân tán và mô hình wide-column, partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, thực hành CQL, replication, compaction, repair, xử lý lỗi và Java Driver. Trong bối cảnh ấy, `duration` thích hợp để **lưu chính sách hoặc khoảng thời gian**; việc **tìm kiếm sự kiện đến hạn**, **sắp xếp** và **phân phối dữ liệu** vẫn cần những cột khóa có thể so sánh như `date`, `timestamp`, `bigint` hoặc `uuid`.

## 1. Duration khác timestamp, date, time và bigint ở đâu?

| Kiểu CQL | Mang ý nghĩa | Java Driver 4.x | Dùng khi |
|---|---|---|---|
| **`duration`** | Khoảng thời gian gồm tháng, ngày, nano giây | `CqlDuration` | Chu kỳ gia hạn 1 tháng, thời gian ân hạn 7 ngày, khoảng chờ 30 phút |
| **`timestamp`** | Một thời điểm tuyệt đối, độ phân giải mili giây | `Instant` | Thời điểm kích hoạt, hết hạn, lần thử tiếp theo |
| **`date`** | Một ngày theo lịch, không có giờ/múi giờ | `LocalDate` | Ngày hiệu lực, bucket ngày theo truy vấn |
| **`time`** | Giờ trong ngày, đến nano giây, không có ngày | `LocalTime` | Giờ mở cửa, khung giờ chạy công việc mỗi ngày |
| **`bigint`** | Số nguyên 64 bit | `long` | Thời lượng cố định tính bằng mili/nano giây, sequence hoặc lượng byte |

Ví dụ một thuê bao có chính sách “gia hạn **mỗi 1 tháng**”, đã đăng ký lúc `2026-01-31T10:00:00Z`. **`duration = 1mo`** lưu ý nghĩa “thêm một tháng theo lịch”. Giá trị này khác về ngữ nghĩa với **`30d`** và **`720h`**. Kết quả ngày đến hạn cần được tính trên một mốc ngày/giờ và quy tắc calendar cụ thể.

Một bản ghi gia hạn thực tế thường cần **hai cột khác vai trò**:

- `billing_interval duration`: chính sách “mỗi 1 tháng”.
- `next_billing_at timestamp`: thời điểm tuyệt đối đã tính ra để scheduler truy vấn và xử lý.

Không biến `duration` thành một số giây trước khi hiểu nó là “thời lượng trôi qua” hay “khoảng theo lịch”.

## 2. Ba thành phần của CQL duration

Một giá trị `duration` được mã hóa thành ba số nguyên có dấu, độ dài biến thiên:

\[
(\text{months},\ \text{days},\ \text{nanoseconds})
\]

| Thành phần | Kiểu giá trị sau giải mã | Ý nghĩa |
|---|---|---|
| **months** | `int` có dấu, 32 bit | Số tháng lịch; năm được quy về 12 tháng |
| **days** | `int` có dấu, 32 bit | Số ngày lịch; tuần được quy về 7 ngày |
| **nanoseconds** | `long` có dấu, 64 bit | Số nano giây của phần giờ/phút/giây/subsecond |

Một số ví dụ chuyển về ba thành phần:

| Duration CQL | months | days | nanoseconds |
|---|---:|---:|---:|
| `1y` | 12 | 0 | 0 |
| `2mo` | 2 | 0 | 0 |
| `3w4d` | 0 | 25 | 0 |
| `1d` | 0 | 1 | 0 |
| `24h` | 0 | 0 | 86.400.000.000.000 |
| `1h30m` | 0 | 0 | 5.400.000.000.000 |
| `1mo2d3h` | 1 | 2 | 10.800.000.000.000 |
| `250ms` | 0 | 0 | 250.000.000 |

**Quy tắc về dấu:** ba thành phần khác 0 phải **cùng dấu** (đều không âm hoặc đều không dương). Ví dụ, một duration có `months=1, days=-2` là không hợp lệ. Nếu nghiệp vụ muốn “thêm một tháng rồi bớt hai ngày”, hãy biểu diễn đó là **hai bước tính** theo quy tắc lịch hoặc tính sẵn mốc kết quả; không ép hai dấu trái nhau vào một giá trị CQL duration.

**Giới hạn lưu trữ:** dù cách mã hóa từng thành phần có độ dài biến thiên, `months` và `days` vẫn bị giới hạn ở miền số nguyên 32 bit, `nanoseconds` ở miền số nguyên 64 bit. Không thể coi một duration là vô hạn hoặc phép nhân vô giới hạn chỉ vì có nhiều đơn vị khác nhau.

### 2.1. Tại sao `1d` không giống `24h`?

`1d` có thành phần `days = 1`, còn `24h` có thành phần `nanoseconds = 86.400.000.000.000`. Hai giá trị **khác nhau ngay trong biểu diễn**.

Khi áp dụng vào lịch ở vùng có DST, điều này còn tạo khác biệt về thời điểm đích. Ví dụ tại `America/New_York`, đồng hồ chuyển sang giờ mùa hè ngày **08/03/2026**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
    2026, 3, 7, 12, 0, 0, 0, zone
);

ZonedDateTime calendarDayLater = start.plusDays(1);
ZonedDateTime elapsed24HoursLater = start.plusHours(24);

System.out.println(calendarDayLater);
// 2026-03-08T12:00-04:00[America/New_York]
System.out.println(elapsed24HoursLater);
// 2026-03-08T13:00-04:00[America/New_York]
~~~

Cùng một mốc bắt đầu nhưng “đến 12:00 ngày mai theo lịch địa phương” và “sau chính xác 24 giờ” khác nhau **1 giờ**. Nếu quy tắc nghiệp vụ là hết hạn theo giờ địa phương, cần **lưu thêm múi giờ và định nghĩa calendar**; một duration tự nó không có timezone.

### 2.2. Tại sao `1mo` không giống `30d`?

Ví dụ với Java `LocalDate`:

~~~java
import java.time.LocalDate;

LocalDate start = LocalDate.of(2026, 1, 31);

System.out.println(start.plusMonths(1)); // 2026-02-28
System.out.println(start.plusDays(30));  // 2026-03-02
~~~

Một tháng lịch kể từ ngày cuối tháng có thể đến ngày cuối tháng tiếp theo theo quy tắc cộng tháng của thư viện. Ba mươi ngày lại là 30 lần bước qua ngày lịch, và kết quả có thể khác. Hãy quy định rõ với thuê bao tháng: **nếu đăng ký ngày 31, tháng 2 phải gia hạn ngày nào?** Đây là chính sách nghiệp vụ, không phải điều CQL `duration` tự quyết định hoàn toàn.

## 3. Cú pháp duration literal trong CQL

CQL cho phép viết duration trực tiếp như `1mo2d3h`. Những hậu tố dễ nhầm nhất là **`mo`** (month) và **`m`** (minute). **`ms`** là millisecond, **`us`** hoặc **`µs`** là microsecond, **`ns`** là nanosecond.

| Hậu tố | Ý nghĩa | Quy đổi vào thành phần |
|---|---|---|
| `y` | Năm | 12 tháng |
| `mo` | Tháng | 1 tháng |
| `w` | Tuần | 7 ngày |
| `d` | Ngày | 1 ngày |
| `h` | Giờ | 3.600.000.000.000 ns |
| `m` | Phút | 60.000.000.000 ns |
| `s` | Giây | 1.000.000.000 ns |
| `ms` | Mili giây | 1.000.000 ns |
| `us`, `µs` | Micro giây | 1.000 ns |
| `ns` | Nano giây | 1 ns |

Ba dạng thường gặp được Cassandra hỗ trợ:

~~~text
CQL unit notation:        1y2mo3d4h5m6s
ISO 8601:                 P1Y2M3DT4H5M6S
ISO 8601 alternative:     P0001-02-03T04:05:06
~~~

Trong CQL, các duration literal như `1mo`, `7d`, `12h30m` được viết **không có dấu nháy**, khác literal văn bản `'1mo'` của kiểu `text`. Khi dùng prepared statement, hãy bind một đối tượng Java `CqlDuration` đúng codec.

### 3.1. CQL tạo bảng chính sách thuê bao

~~~cql
CREATE TABLE billing_policies_by_plan (
    plan_code text PRIMARY KEY,
    billing_every duration,
    grace_period duration,
    retry_after duration,
    billing_zone text,
    effective_at timestamp
);

INSERT INTO billing_policies_by_plan (
    plan_code, billing_every, grace_period,
    retry_after, billing_zone, effective_at
) VALUES (
    'MONTHLY_VN', 1mo, 5d,
    30m, 'Asia/Ho_Chi_Minh',
    '2026-11-21T00:00:00Z'
);

SELECT billing_every, grace_period, retry_after, billing_zone
FROM billing_policies_by_plan
WHERE plan_code = 'MONTHLY_VN';
~~~

Đây là bảng **tra cứu chính sách theo plan_code**. Duration được dùng như **cột dữ liệu thông thường**, còn `plan_code` là khóa phân vùng. Các phần:

- `billing_every = 1mo`: chu kỳ hóa đơn theo tháng lịch.
- `grace_period = 5d`: số ngày lịch được ân hạn.
- `retry_after = 30m`: thời lượng cố định 30 phút trước khi thử lại.
- `billing_zone`: múi giờ dùng diễn giải ngày/giờ của chu kỳ.
- `effective_at timestamp`: thời điểm chính sách có hiệu lực. Đây là dữ liệu mốc tuyệt đối, không phải duration.

Một chính sách có thể cần phiên bản hoặc hiệu lực theo thời gian. Nếu thường xuyên tra “chính sách đúng tại thời điểm T”, cần thiết kế bảng lịch sử theo plan và thời điểm hiệu lực; một row `PRIMARY KEY(plan_code)` sẽ chỉ giữ phiên bản hiện có.

### 3.2. Các lỗi literal phổ biến

~~~text
1m     -> một phút, không phải một tháng.
1mo    -> một tháng.
1ms    -> một mili giây, không phải một phút.
24h    -> 24 giờ thuộc thành phần nano giây.
1d     -> một ngày thuộc thành phần ngày lịch.
1mo-2d -> cố gắng trộn dấu trái nhau; không dùng như một duration.
~~~

Hãy đặt chính sách validation tại API thay vì cho người dùng nhập duration tự do rồi truyền trực tiếp tới Cassandra. Một form chỉ cho phép lựa chọn “tháng/tuần/ngày/giờ” có thể rõ ràng hơn một chuỗi `1mo` được phép viết sai thành `1m`.

## 4. Những thao tác được và không được hỗ trợ

Chủ đề cốt lõi của kiểu `duration` là **giới hạn ngữ nghĩa của thao tác**, do nó không có thứ tự toàn phần độc lập với mốc thời gian.

| Thao tác | Hỗ trợ/cách thực hiện | Lý do và giới hạn |
|---|---|---|
| Khai báo cột `duration`, `INSERT`, `UPDATE`, `SELECT` | **Có** | Cột dữ liệu chính sách, thời lượng |
| Bind/đọc qua Java Driver `CqlDuration` | **Có** | Giữ đủ ba thành phần |
| Dùng `duration` trong `PRIMARY KEY` | **Không** | Không có thứ tự toàn phần để Cassandra tổ chức khóa |
| Dùng `duration` làm clustering key, `ORDER BY` theo duration | **Không** | Clustering key phải sắp xếp được |
| So sánh “`1mo > 30d`” mà không có mốc lịch | **Không xác định về ngữ nghĩa** | Một tháng dài 28–31 ngày |
| Range scan `WHERE interval > 7d` trên một cột duration | **Không dùng làm mẫu truy vấn** | Không có thứ tự tự nhiên và không phải cột clustering |
| Cộng/trừ duration với `date` hoặc `timestamp` bằng toán tử CQL | **Có từ Cassandra 4.0** | Kết quả là `date` hoặc `timestamp`; cần kiểm tra phiên bản |
| Cộng duration với `time` như một phép tạo timestamp | **Không dùng** | `time` thiếu ngày và timezone |
| `USING TTL 1h` thay cho số giây | **Không** | TTL nhận thời lượng sống ở **đơn vị giây**, không phải kiểu duration |
| Dùng duration để tăng `counter` | **Không** | Counter là kiểu riêng với quy tắc cập nhật số nguyên |
| Tự biến `1mo` thành một số nanosecond cố định | **Không an toàn** | Cần mốc lịch và quy tắc timezone |

Cassandra có các **toán tử số học** trên kiểu số; điều đó không có nghĩa `duration` là một số để cộng/trừ/nhân/chia tùy ý như `bigint` hoặc `decimal`. Nếu cần thực hiện chuỗi phép toán lịch phức tạp, nên thiết kế và kiểm thử ở ứng dụng, nơi có đầy đủ mốc bắt đầu, `ZoneId` và các quy tắc nghiệp vụ.

### 4.1. Vì sao duration không có thứ tự toàn phần?

Một toán tử `<` hoặc `>` cần có kết quả ổn định cho mọi cặp giá trị. Với duration:

- `1mo` có thể là 28, 29, 30 hoặc 31 ngày tùy tháng và năm.
- `1d` là bước ngày theo lịch; `24h` là 24 giờ trôi qua. Ở múi giờ có DST, chúng có thể đưa tới hai thời điểm khác nhau.
- `1y` và `365d` có thể khác ở năm nhuận.

Do vậy, không tồn tại quy tắc chung để quyết định `1mo` lớn hay nhỏ hơn `30d` mà vẫn đúng cho mọi mốc. Đây là nguyên nhân Cassandra **cấm duration trong primary key**; giới hạn mang tính mô hình dữ liệu, không đơn thuần là một tùy chọn hiệu năng.

**Hệ quả thiết kế:** nếu dashboard cần “lọc các lần chạy có thời lượng trên 500 ms”, hãy lưu một **giá trị đã đo** theo đơn vị cố định, ví dụ `elapsed_ms bigint` (và dùng bảng theo truy vấn phù hợp), thay vì dùng `duration` lịch.

### 4.2. Giới hạn khi dùng trong collection

Các collection có quy tắc riêng đối với kiểu cần so sánh/định danh phần tử. Một `duration` không có thứ tự nên **không thích hợp làm phần tử `set<duration>` hoặc khóa `map<duration, ...>`** trong CQL; các cách dùng này bị hạn chế. Có thể mô hình một danh sách khoảng nhỏ theo quy tắc collection hoặc dùng cột duration đơn lẻ, nhưng không đưa lịch sử khoảng thời gian tăng vô hạn vào một collection trong một row.

Nếu cần tra cứu danh sách chính sách theo ID, phương án dễ vận hành thường là bảng có `policy_id uuid` hoặc `policy_code text` làm khóa và `interval duration` làm **giá trị**. Một hàng cho mỗi chính sách giúp truy cập có key và kiểm soát tăng trưởng phân vùng.

## 5. Toán tử datetime với duration trong CQL 4.0+

Trong các phiên bản Cassandra hỗ trợ arithmetic date/time (từ **4.0**), CQL có thể cộng hoặc trừ một duration với `date` hoặc `timestamp`. Ví dụ:

~~~cql
CREATE TABLE daily_runs_by_day (
    run_day date PRIMARY KEY,
    completed_jobs int
);

INSERT INTO daily_runs_by_day (run_day, completed_jobs)
VALUES ('2026-11-20', 100);

-- Lấy ngày hôm trước 2026-11-21:
SELECT completed_jobs
FROM daily_runs_by_day
WHERE run_day = '2026-11-21' - 1d;
~~~

Đây là phép tính trên **literal ngày** để tạo một **giá trị ngày** truy vấn đúng primary key. Nó khác với việc đem một cột `duration` làm clustering key.

Các mẫu như sau có ý nghĩa:

~~~text
timestamp + duration -> timestamp
timestamp - duration -> timestamp
date      + duration -> date
date      - duration -> date
~~~

**Giới hạn:**

- Cần kiểm tra **phiên bản Cassandra/CQL đang chạy**; không mặc định cluster cũ hỗ trợ toán tử datetime.
- `timestamp` của Cassandra chỉ giữ **mili giây**. Nếu duration có nano giây nhỏ hơn mili giây, kết quả ghi vào timestamp không thể bảo toàn phần nhỏ đó.
- `date` không có thành phần giờ; không lấy nó làm một kết quả có thể phân biệt giờ/phút/nano giây.
- CQL không mang tên múi giờ nghiệp vụ của người dùng khi lưu timestamp. Kết quả tính trên timestamp không thay thế được một chính sách “gia hạn lúc 09:00 giờ địa phương” cần `ZoneId` và quy tắc lịch.
- Một phép cộng thời gian trong mệnh đề `WHERE` không biến các cột không thuộc khóa thành đường truy vấn tối ưu.

Với logic quyết định **lúc nào thanh toán, khóa tài khoản hoặc gửi email**, thường nên tính rõ **deadline tuyệt đối ở ứng dụng Java** rồi lưu `next_due_at timestamp`, để tránh các client hiểu khác nhau về múi giờ hay quy tắc lịch.

## 6. Java Driver 4.x: CqlDuration và cách bind

CQL `duration` được Java Driver 4.x ánh xạ sang **`com.datastax.oss.driver.api.core.data.CqlDuration`**, không trực tiếp sang `java.time.Duration`.

Các API phổ biến:

| Mục đích | Java |
|---|---|
| Tạo duration từ ba thành phần | `CqlDuration.newInstance(months, days, nanoseconds)` |
| Parse literal như `1mo2d3h` | `CqlDuration.from("1mo2d3h")` |
| Đọc các thành phần | `getMonths()`, `getDays()`, `getNanoseconds()` |
| Ghi prepared statement | `setCqlDuration(index, value)` hoặc `setCqlDuration(name, value)` |
| Đọc từ row | `getCqlDuration("billing_every")` |
| Tính trên kiểu thời gian Java | Sử dụng calendar/time-zone rules với `Period`, `Duration`, `ZonedDateTime` |

Ví dụ tạo duration:

~~~java
import com.datastax.oss.driver.api.core.data.CqlDuration;
import java.time.Duration;

CqlDuration monthly = CqlDuration.newInstance(1, 0, 0);
CqlDuration grace = CqlDuration.from("5d");
CqlDuration retry = CqlDuration.newInstance(
    0, 0, Duration.ofMinutes(30).toNanos()
);

System.out.println(monthly.getMonths());      // 1
System.out.println(grace.getDays());          // 5
System.out.println(retry.getNanoseconds());   // 1800000000000
~~~

`Duration.ofMinutes(30).toNanos()` chỉ hợp lý vì đây là **30 phút trôi qua**. Không chuyển `1mo` thành một số `nanoseconds` bằng cách gán tháng = 30 ngày.

### 6.1. INSERT và SELECT bằng prepared statement

Giả sử `session` là một `CqlSession` đã được cấu hình contact points, local datacenter, keyspace và credentials của ứng dụng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import java.time.Instant;

// CqlSession session = ...;  // Khởi tạo và quản lý vòng đời bên ngoài.

PreparedStatement insert = session.prepare(
    "INSERT INTO billing_policies_by_plan "
  + "(plan_code, billing_every, grace_period, "
  + " retry_after, billing_zone, effective_at) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

CqlDuration interval = CqlDuration.from("1mo");
CqlDuration grace = CqlDuration.from("5d");
CqlDuration retry = CqlDuration.from("30m");

BoundStatement statement = insert.boundStatementBuilder()
    .setString(0, "MONTHLY_VN")
    .setCqlDuration(1, interval)
    .setCqlDuration(2, grace)
    .setCqlDuration(3, retry)
    .setString(4, "Asia/Ho_Chi_Minh")
    .setInstant(5, Instant.parse("2026-11-21T00:00:00Z"))
    .build();

session.execute(statement);

PreparedStatement find = session.prepare(
    "SELECT billing_every, grace_period, retry_after, billing_zone "
  + "FROM billing_policies_by_plan WHERE plan_code = ?");

Row row = session.execute(find.bind("MONTHLY_VN")).one();

if (row != null) {
    CqlDuration stored = row.getCqlDuration("billing_every");
    if (stored != null) {
        int months = stored.getMonths();
        int days = stored.getDays();
        long nanos = stored.getNanoseconds();
    }
}
~~~

**Prepared statement** bind đúng kiểu, giúp tránh nhập nhằng `m`/ `mo` khi tự nối CQL và không cần escape dữ liệu người dùng bằng tay. Vẫn cần validation ở biên API trước khi tạo `CqlDuration`: một chuỗi sai cú pháp, giá trị quá lớn hoặc thành phần trái dấu phải bị từ chối theo hợp đồng.

### 6.2. So sánh với java.time.Duration và java.time.Period

Hai kiểu Java chuẩn cũng có vai trò riêng:

| Kiểu Java | Biểu diễn | Tình huống |
|---|---|---|
| `Duration` | Số giây + nano giây, thời lượng trôi qua | Timeout 30 giây, độ trễ 250 ms |
| `Period` | Năm + tháng + ngày lịch | Gia hạn 1 tháng, thêm 7 ngày lịch |
| `CqlDuration` | Tháng + ngày + nano giây | Ánh xạ đúng giá trị CQL duration gồm cả lịch và thời lượng |

Không chuyển `CqlDuration` sang `java.time.Duration` nếu `getMonths()` hoặc `getDays()` khác 0 mà chưa có mốc lịch và quy tắc múi giờ. Có thể dùng `CqlDuration` như một `TemporalAmount`, nhưng phải xem **loại đối tượng thời gian** và quy tắc ngày/giờ mà nó được áp dụng. Không phải mọi `Temporal` đều hỗ trợ cùng tập đơn vị thời gian.

### 6.3. Chuyển một chu kỳ lịch thành thời điểm đến hạn

Nếu hợp đồng của plan là “gia hạn cùng giờ địa phương vào tháng sau”, một cách tính có kiểm soát:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId billingZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant activatedAt = Instant.parse("2026-01-31T03:00:00Z");
// 10:00 giờ Việt Nam ngày 31/01/2026.

ZonedDateTime localActivation = activatedAt.atZone(billingZone);
ZonedDateTime localNext = localActivation.plusMonths(1);
Instant nextBillingAt = localNext.toInstant();

System.out.println(localNext);
// 2026-02-28T10:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(nextBillingAt);
// 2026-02-28T03:00:00Z
~~~

Ở đây quy tắc **ngày cuối tháng** là hành vi của `plusMonths`; ứng dụng phải xác nhận nó đúng với chính sách thanh toán. Nếu quy định “ngày 31 luôn được giữ làm ngày gốc, các tháng ngắn hơn lấy ngày cuối tháng”, không nên chỉ lấy deadline tháng trước rồi cộng tháng liên tục mà không theo dõi **ngày gốc của chu kỳ**, bởi có thể bị trôi ngày.

Nếu vùng có DST, còn cần quy tắc giờ không tồn tại/trùng nhau. CQL duration chỉ lưu khoảng; **quyết định diễn giải** thuộc lớp calendar của ứng dụng.

## 7. Cần tìm công việc đến hạn thì thiết kế bảng ra sao?

Một scheduler thường yêu cầu: **“Lấy các lần gia hạn đến hạn trong ngày, theo thời gian tăng dần, xử lý theo từng shard.”** Dùng `duration` làm clustering key là không hợp lệ; thay vào đó, **tính trước một timestamp tuyệt đối** rồi đưa timestamp vào khóa theo truy vấn.

Ví dụ:

~~~cql
CREATE TABLE renewal_tasks_by_day_shard (
    due_day date,
    shard smallint,
    due_at timestamp,
    subscription_id uuid,
    customer_id uuid,
    plan_code text,
    PRIMARY KEY ((due_day, shard), due_at, subscription_id)
) WITH CLUSTERING ORDER BY (due_at ASC, subscription_id ASC);
~~~

- `(due_day, shard)` là **partition key**, cho phép phân chia tải xử lý theo ngày và shard.
- `due_at timestamp` là **clustering column** theo deadline tuyệt đối.
- `subscription_id uuid` phân biệt các công việc cùng `due_at` mili giây.
- `plan_code` liên kết đến bảng chính sách có `billing_every duration`, nhưng duration **không phải khóa sắp xếp** của hàng công việc.

Ví dụ một truy vấn cho shard số 3:

~~~cql
SELECT due_at, subscription_id, customer_id, plan_code
FROM renewal_tasks_by_day_shard
WHERE due_day = '2026-11-21'
  AND shard = 3
  AND due_at <= '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Truy vấn có đầy đủ partition key và giới hạn trên clustering column. Nếu hệ thống có 32 shard, worker phải biết shard nào nó chịu trách nhiệm hoặc duyệt các shard phù hợp; không có câu truy vấn rẻ nào tự hợp nhất toàn bộ partition theo thời gian chung.

Vì **deadline là clustering key**, nếu một công việc được hoãn từ 09:00 sang 09:30 thì thực chất khóa của nó **thay đổi**: hệ thống cần tạo hàng mới và xử lý/xóa hàng cũ theo quy trình idempotent, tránh để cả hai được chạy. Cassandra không tự hỗ trợ `UPDATE` thay đổi primary key của cùng hàng.

### 7.1. Duration không thay thế TTL

Giả sử chính sách “giữ dữ liệu 1 tháng”. Cassandra `USING TTL` nhận **số giây**, không nhận duration lịch `1mo`.

~~~cql
-- TTL theo giây: ví dụ giữ khoảng 7*24 giờ.
INSERT INTO some_events_by_id (event_id, event_type)
VALUES (11111111-1111-4111-8111-111111111111, 'LOGIN')
USING TTL 604800;
~~~

Câu lệnh này chỉ minh họa cách dùng TTL; bảng `some_events_by_id` được giả định tồn tại với cột `event_id`, `event_type`. TTL không phải một “ngày hết hạn” hiển thị theo calendar của người dùng. Nếu nghiệp vụ yêu cầu hết hạn **sau một tháng lịch** hoặc theo giờ địa phương cụ thể, hãy tính **mốc `expires_at`** bằng quy tắc calendar ở ứng dụng, rồi quyết định cơ chế xóa và TTL phù hợp.

**Đừng lấy 1 tháng = 30 ngày để thiết lập TTL** trừ khi đó đúng là quy định nghiệp vụ. Nếu có TTL, hãy lưu ý trạng thái hết hạn, tombstone và chính sách compaction/repair, không coi TTL như bộ hẹn giờ công việc chính xác tại từng giây.

### 7.2. Duration không phải counter

Các thao tác như:

~~~cql
-- Không phải cú pháp tăng duration được hỗ trợ như counter:
-- UPDATE billing_policies_by_plan
-- SET billing_every = billing_every + 1mo
-- WHERE plan_code = 'MONTHLY_VN';
~~~

không phải mô hình cập nhật gia tăng phù hợp. Nếu cần chỉnh chính sách từ 1 tháng lên 2 tháng, ghi **toàn bộ giá trị duration mới** bằng prepared statement, đồng thời xác định từ thời điểm nào thay đổi có hiệu lực. Với những thay đổi cần kiểm soát cạnh tranh, phải cân nhắc LWT hoặc cơ chế phiên bản phù hợp; Cassandra không tự cộng dồn duration như bộ đếm.

## 8. Retry và consistency: duration là chính sách, timestamp là kết quả tính

Giả sử một worker đọc `billing_every = 1mo`, tính `next_billing_at`, rồi ghi lịch sử và hàng tác vụ. Nếu worker timeout, có thể một số replica hoặc một phần thao tác đã nhận dữ liệu.

Để xử lý chắc chắn:

1. Dùng **`subscription_id` và `billing_cycle_id` ổn định** làm định danh nghiệp vụ; retry cùng chu kỳ phải dùng cùng khóa.
2. Ghi rõ **phiên bản chính sách**, `ZoneId`, mốc gốc và quy tắc ngày cuối tháng/DST dùng để tính deadline.
3. Lưu **`next_billing_at timestamp` đã tính** để mọi worker nhìn thấy cùng mốc; không để mỗi worker tự đọc duration và suy ngày đến hạn bằng múi giờ riêng.
4. Khi ghi sang nhiều bảng theo truy vấn, cần cơ chế khôi phục/đối soát; không giả định tính nguyên tử của một chuỗi INSERT xuyên nhiều partition.
5. Khi retry, giữ nguyên dữ liệu chính của một yêu cầu đã chốt. Nếu cố gắng “tính lại ngày đến hạn” từ `now()` ở mỗi retry, deadline có thể trôi.

Consistency level (ví dụ `LOCAL_QUORUM`) ảnh hưởng số replica xác nhận đọc/ghi. Nó **không giải quyết** khác biệt `1mo` và `30d`, cũng không biến nhiều lệnh ghi độc lập thành một giao dịch lịch biểu toàn cluster.

## 9. Tác động tới replication, compaction và repair

**Replication** sao chép các giá trị CQL đã ghi, gồm ba thành phần của duration. Các replica không biến duration thành một “số giây chuẩn” để so sánh. **Repair** giúp replica hội tụ dữ liệu, nhưng không sửa chính sách ngày cuối tháng nếu ứng dụng tính sai. **Compaction** gộp SSTable, xử lý dữ liệu cũ/tombstone theo quy tắc; nó không tự tính lịch gia hạn từ cột `duration`.

Trong vận hành:

- Định nghĩa **retention** cho chính sách và lịch sử thay đổi, tránh mất dữ liệu cần phục vụ đối soát.
- Nếu cập nhật chính sách thường xuyên, cân nhắc **versioning** và lưu các mốc hiệu lực `timestamp`; kiểu duration chỉ là một thuộc tính của từng phiên bản.
- Nếu hàng scheduler bị di chuyển giữa các due bucket, phải quản lý dữ liệu cũ và tombstone theo tải thực tế.
- Đo **kích thước partition**, số hàng mỗi ngày/shard, độ trễ đọc/ghi, hàng đến hạn và số lần xử lý lại; chỉ tối ưu sau khi có mẫu tải thực tế.
- Nếu ngày deadline tính ở ứng dụng, theo dõi timezone database và đồng hồ hệ thống; clock skew giữa node không biến duration thành sai byte, nhưng có thể làm scheduler xử lý sớm/muộn.

## 10. Lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Dùng `1m` để lưu chu kỳ một tháng | Thực tế là **1 phút** | Dùng `1mo` và kiểm tra đầu vào |
| Xem `1mo = 30d = 720h` | Sai tháng ngắn/dài và DST | Chọn rõ khoảng lịch hay khoảng trôi qua |
| Dùng `duration` làm `PRIMARY KEY` | Schema không hợp lệ | Dùng cột có thứ tự như `timestamp`, `bigint`, `date` |
| Query `WHERE policy_duration > 7d` để lấy mọi chính sách dài | Không có thứ tự duration toàn cục | Chuẩn hóa sang metric/mốc có ngữ nghĩa rõ và thiết kế query |
| Đưa `duration` vào `USING TTL` | TTL không nhận kiểu lịch | TTL bằng giây, riêng deadline theo lịch |
| Gộp `months=1` và `days=-2` | Trái quy tắc dấu duration | Tách thành hai phép lịch hoặc tính sẵn kết quả |
| Chuyển `CqlDuration` sang `java.time.Duration` bằng ngày/tháng giả định | Làm mất semantics calendar | Dùng `Period`, `ZonedDateTime`, `ZoneId` và policy |
| Cộng 1 tháng liên tiếp từ ngày cuối tháng mà không giữ ngày gốc | Có thể trôi ngày gia hạn | Định nghĩa quy tắc chu kỳ và anchor ổn định |
| Tính deadline theo timezone mỗi worker tự chọn | Hai worker tạo deadline khác nhau | Lưu `billing_zone`, phiên bản policy, deadline đã tính |
| Coi `date` hoặc `timestamp` là giữ được mọi nano giây duration | Mất độ phân giải khi chuyển | Chọn kiểu/đơn vị lưu phù hợp trước |
| Ghi lại task với ID mới sau timeout | Có thể chạy cùng chu kỳ hai lần | Giữ ID và khóa idempotent, đối soát |
| Thay đổi duration nhưng không phiên bản chính sách | Không tái dựng được lịch sử tính toán | Lưu version/effective_at, chính sách đã áp dụng |

## 11. Bài tập thực hành

### Bài 1 — Chọn kiểu

Một hệ thống có bốn yêu cầu:

- Chu kỳ thanh toán **mỗi 1 tháng**.
- Retry HTTP sau **150 mili giây**.
- Lấy **ngày hết hạn đã tính** dưới dạng một thời điểm tuyệt đối.
- Đo latency API **đến nano giây**.

**Gợi ý:** chu kỳ một tháng dùng `duration = 1mo`; retry 150 ms có thể dùng duration `150ms` làm cấu hình, nhưng code runtime thường dùng `java.time.Duration`; deadline tuyệt đối dùng `timestamp`; latency đo chính xác đến nano giây nên lưu `bigint elapsed_ns` hoặc kiểu phù hợp với phép đo, **không** dựa vào `timestamp` chỉ có độ phân giải mili giây.

### Bài 2 — Ngày cuối tháng

Khách hàng đăng ký ngày 31/01/2026, chu kỳ `1mo`.

**Câu hỏi:** Ngày cộng một tháng theo `LocalDate.plusMonths(1)` là ngày nào? Có giống `plusDays(30)`?

**Đáp án:** `2026-02-28`, còn `plusDays(30)` là `2026-03-02`. Chính sách gia hạn phải xác định có dùng quy tắc ngày cuối tháng hay một cách khác.

### Bài 3 — DST

Ở New York, một lịch lặp “12:00 ngày mai” bắt đầu 12:00 ngày 07/03/2026. So với “sau 24 giờ”, hai thời điểm có giống nhau không?

**Đáp án:** không. `plusDays(1)` đến 12:00 ngày 08/03; `plusHours(24)` đến 13:00 ngày 08/03 vì chuyển DST.

### Bài 4 — Schema hợp lệ không?

~~~cql
-- Sai: duration không được làm clustering key.
CREATE TABLE wrong_jobs (
    tenant_id uuid,
    delay duration,
    job_id uuid,
    PRIMARY KEY ((tenant_id), delay, job_id)
);
~~~

**Câu hỏi:** Nên đổi như thế nào nếu muốn lấy các job đến hạn?

**Gợi ý:** tính `due_at timestamp` và dùng clustering theo deadline, có `job_id uuid` phân biệt trùng thời điểm; giữ `delay duration` làm cột dữ liệu của chính sách hoặc job.

### Bài 5 — Java Driver

~~~java
CqlDuration policy = CqlDuration.from("1mo2d3h");
~~~

**Câu hỏi:** `getMonths()`, `getDays()` và `getNanoseconds()` trả về gì? Có thể so sánh nó với `33d3h` mà không biết ngày bắt đầu không?

**Đáp án:** tháng = 1, ngày = 2, nano giây = `10_800_000_000_000L`; không có thứ tự lớn/nhỏ được xác định cho mọi mốc lịch so với `33d3h`.

## 12. Checklist trước khi dùng duration

- [ ] Đã phân biệt **khoảng theo lịch** (tháng/ngày) với **thời lượng trôi qua** (giờ/phút/giây/nano giây)?
- [ ] Đã dùng đúng đơn vị `mo` cho tháng, `m` cho phút, `ms` cho mili giây?
- [ ] Ba thành phần months/days/nanoseconds có cùng dấu và nằm trong miền `int/int/long`?
- [ ] Có cần `ZoneId`, quy tắc ngày cuối tháng, DST hoặc ngày bắt đầu để diễn giải deadline?
- [ ] Có dùng duration **chỉ làm cột dữ liệu**, không trong `PRIMARY KEY` hoặc key so sánh?
- [ ] Các truy vấn range/order đã dùng `timestamp`, `date`, `bigint` hoặc khóa khác phù hợp?
- [ ] Nếu dùng số học `date/timestamp ± duration`, cluster có hỗ trợ toán tử ở phiên bản đang chạy?
- [ ] Đã phân biệt `CqlDuration`, `java.time.Duration` và `java.time.Period`?
- [ ] Java Driver bind/read với `setCqlDuration`/`getCqlDuration` và prepared statement?
- [ ] Không dùng duration trực tiếp làm TTL; TTL đã được xác định theo **giây**?
- [ ] Khi scheduler cần làm việc, đã lưu **deadline tuyệt đối**, bucket và khóa chống trùng?
- [ ] Retry, versioning chính sách, consistency và đồng bộ nhiều bảng được xử lý theo yêu cầu nghiệp vụ?
- [ ] Đã đo partition size, tombstone/compaction, retention và điều kiện repair khi vận hành?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types, phần Duration](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — Arithmetic Operators, Datetime Arithmetic](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/operators.html).
- [Apache Cassandra Java Driver 4.x — CqlDuration](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/data/CqlDuration.html).

**Ghi nhớ:** `duration` là **một khoảng thời gian có ngữ nghĩa lịch**, được lưu thành **months + days + nanoseconds**. Vì tháng/ngày không tương ứng một thời lượng cố định ở mọi mốc, Cassandra **không sắp xếp duration** và **không cho duration làm primary key**. Hãy dùng nó cho **chính sách**, tính thời điểm đến hạn theo một calendar và timezone rõ ràng, rồi lưu **`timestamp`/khóa truy vấn** để xử lý hiệu quả trong Cassandra phân tán.

