# date, time, timestamp, duration và kiểu thời gian Java

Trong **Spring Data Cassandra**, dữ liệu thời gian là một trong những nơi dễ xuất hiện lỗi âm thầm: bản ghi vẫn được ghi thành công nhưng bị lệch ngày, mất độ chính xác, hoặc truy vấn không trả về kết quả như mong đợi. Nguyên nhân thường là dùng lẫn lộn bốn khái niệm **ngày lịch**, **giờ trong ngày**, **thời điểm tuyệt đối** và **khoảng thời gian**.

Apache Cassandra có các kiểu CQL `date`, `time`, `timestamp` và `duration`. Java có `LocalDate`, `LocalTime`, `Instant`, `LocalDateTime`, `ZonedDateTime`, `Duration` và `Period`. Chúng không có quan hệ một-một trong mọi trường hợp. Chọn kiểu phù hợp là bước đầu tiên trước khi định nghĩa `@Table`, tạo `CassandraRepository`, viết truy vấn qua `CassandraTemplate` hoặc thực thi CQL trực tiếp.

Bài học thuộc chương **Kiểu dữ liệu**, sử dụng API Java Time và Java Driver 4 (namespace `com.datastax.oss.driver.api`) làm cơ sở minh họa. Tên API và những chuyển đổi bổ sung cần được đối chiếu với phiên bản Spring Data Cassandra/driver thực tế của dự án.

## 1. Chọn kiểu dữ liệu từ ngữ nghĩa nghiệp vụ

| CQL | Lưu trữ ý nghĩa gì? | Kiểu Java phù hợp với Driver 4 | Có thông tin múi giờ? | Ví dụ nghiệp vụ |
| --- | --- | --- | --- | --- |
| `date` | Một ngày trên lịch, không có giờ | `java.time.LocalDate` | Không | Ngày sinh, ngày báo cáo, bucket theo ngày |
| `time` | Thời gian trong ngày, không có ngày | `java.time.LocalTime` | Không | Khung giờ mở cửa, giờ hẹn theo lịch địa phương |
| `timestamp` | Một thời điểm trên trục thời gian, lưu theo epoch millisecond | `java.time.Instant` | Không lưu zone hoặc offset ban đầu | Thời điểm sự kiện xảy ra, thời điểm cập nhật |
| `duration` | Khoảng thời gian gồm tháng, ngày và nano-giây | `com.datastax.oss.driver.api.core.data.CqlDuration` | Không | Thời lượng theo quy tắc lịch, ví dụ 1 tháng 2 ngày |

Một phép tự kiểm tra trước khi chọn kiểu:

- “Ngày 25/11/2026” không cần giờ hay vị trí địa lý → `date`/`LocalDate`.
- “09:30 mỗi ngày theo giờ Việt Nam” → `time`/`LocalTime` **và** quy tắc múi giờ riêng nếu cần suy ra thời điểm thực.
- “Hệ thống nhận sự kiện lúc 02:15 UTC ngày 25/11/2026” → `timestamp`/`Instant`.
- “Gia hạn thêm một tháng theo lịch” → `duration` CQL hoặc `Period` trong mô hình miền nghiệp vụ; không mặc định là 30 × 24 giờ.

Không có kiểu thời gian nào tự quyết định **partition key**, **clustering order** hay **consistency level**. Ví dụ, dùng `timestamp` để lưu thời điểm sự kiện không có nghĩa Cassandra tự biết cách truy vấn tất cả sự kiện của một ngày khi bảng không được thiết kế theo truy vấn đó.

## 2. `date` ↔ `LocalDate`: ngày lịch không có múi giờ

`date` chỉ biểu diễn một ngày, không chứa giờ/phút/giây và không gắn với time zone. Với Spring Data Cassandra dùng Java Driver 4, dạng Java thích hợp là `LocalDate`:

```java
import java.time.LocalDate;

LocalDate reportDay = LocalDate.of(2026, 11, 25);
```

CQL có thể lưu ngày này bằng cú pháp:

```sql
-- Ví dụ phần giá trị cho cột kiểu date.
INSERT INTO daily_reports (tenant_id, report_day, title)
VALUES ('tenant-a', '2026-11-25', 'Báo cáo ngày');
```

Câu INSERT trên giả định đã có bảng `daily_reports` với đúng các cột tương ứng; nó chỉ minh họa cách truyền literal `date`, không phải script tạo schema hoàn chỉnh. Trong mã ứng dụng, ưu tiên **bind `LocalDate`** thay cho việc nối chuỗi ngày vào CQL.

### 2.1. Chọn ngày theo UTC hay theo người dùng?

Một `Instant` có thể thuộc **hai ngày khác nhau** khi hiển thị ở hai múi giờ:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

Instant eventTime = Instant.parse("2026-11-24T18:30:00Z");
LocalDate utcDay = eventTime.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate vnDay = eventTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                           .toLocalDate();

// utcDay = 2026-11-24
// vnDay  = 2026-11-25
```

Nếu `event_day` là thành phần của partition key, writer và reader phải dùng **cùng quy tắc phân bucket**. Việc writer dùng ngày UTC nhưng reader suy ra ngày theo Việt Nam sẽ khiến ứng dụng đọc sai partition. Thường nên định nghĩa rõ tên/ngữ nghĩa `event_day_utc` hoặc có tài liệu hợp đồng rằng `event_day` được tính theo UTC.

Trong nghiệp vụ lịch làm việc/báo cáo theo địa phương, `LocalDate` có thể mang nghĩa ngày theo múi giờ của cơ sở hoặc người dùng; khi đó **múi giờ là dữ kiện nghiệp vụ cần lưu hoặc cấu hình riêng**.

## 3. `time` ↔ `LocalTime`: giờ trong ngày không phải thời điểm

`time` biểu diễn số nano-giây tính từ đầu ngày trong CQL, và Driver 4 làm việc với `LocalTime`. Nó không có thông tin về **ngày**, **múi giờ**, hoặc **UTC offset**:

```java
import java.time.LocalTime;

LocalTime openingTime = LocalTime.of(9, 30);
LocalTime preciseTime = LocalTime.of(9, 30, 15, 123_456_789);
```

`time` có khả năng biểu diễn độ chính xác đến **nano-giây**, nhưng điều đó không chứng minh hệ thống ghi nhận thời gian thực với độ chính xác nano-giây: độ phân giải của đồng hồ, nguồn sự kiện và logic ứng dụng vẫn có thể thấp hơn.

Ví dụ một lịch hàng ngày:

```sql
CREATE TABLE business_hours_by_branch (
    branch_id    text,
    day_of_week  int,
    opens_at     time,
    closes_at    time,
    zone_id      text,
    PRIMARY KEY (branch_id, day_of_week)
);
```

`zone_id` là cột `text`, chẳng hạn `Asia/Ho_Chi_Minh`, giúp diễn giải `opens_at` và `closes_at` tại địa điểm thực tế. Nếu khung giờ vượt qua nửa đêm, cách đọc “đóng cửa sau mở cửa” cần được định nghĩa trong nghiệp vụ, không thể suy ra chỉ từ phép so sánh hai `LocalTime`.

Để biến một giờ địa phương thành thời điểm cụ thể, phải biết **ngày và zone**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

LocalDate day = LocalDate.of(2026, 11, 25);
LocalTime opensAt = LocalTime.of(9, 30);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant opensInstant = day.atTime(opensAt)
        .atZone(businessZone)
        .toInstant();
```

Tại những vùng có **giờ mùa hè (DST)**, một `LocalDateTime` có thể không tồn tại hoặc xuất hiện hai lần khi đồng hồ dịch chuyển. `atZone()` có quy tắc mặc định để giải quyết trường hợp đó, nhưng ứng dụng đặt lịch quan trọng có thể cần chính sách tường minh cho các thời điểm bị thiếu hoặc trùng.

Không lưu `LocalTime` để đại diện trực tiếp cho “thời điểm tạo bản ghi”; thiếu ngày và zone sẽ làm mất thông tin không thể khôi phục chính xác.

## 4. `timestamp` ↔ `Instant`: thời điểm tuyệt đối

Kiểu CQL `timestamp` lưu một giá trị biểu diễn **số millisecond kể từ Unix epoch** (`1970-01-01T00:00:00Z`). Đây là một thời điểm tuyệt đối trên trục thời gian; Cassandra **không lưu lại chuỗi múi giờ hoặc offset** mà người dùng nhập.

```java
import java.time.Instant;

Instant createdAt = Instant.parse("2026-11-25T07:30:00Z");
long epochMillis = createdAt.toEpochMilli();
```

Ví dụ `2026-11-25T07:30:00Z` và `2026-11-25T14:30:00+07:00` biểu diễn **cùng một thời điểm**. Khi lưu dưới dạng `timestamp`, chúng tương ứng cùng giá trị epoch millisecond.

### 4.1. Dùng `Instant` thay vì tự suy múi giờ của máy

Đối với dữ liệu như `created_at`, `updated_at` hoặc `occurred_at`, một lựa chọn rõ ràng là:

```java
Instant occurredAt = Instant.now();
```

Khi cần hiển thị theo vùng:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime viewInHcm = occurredAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Ngược lại, `LocalDateTime` **không chứa múi giờ/offset**, nên không tự xác định duy nhất một `Instant`. Nếu nhận thời gian địa phương từ form, hãy biết `ZoneId` của người dùng/cơ sở rồi chuyển đổi ở biên hệ thống. Đừng gắn mặc định múi giờ máy chủ hoặc gọi `LocalDateTime.toInstant(ZoneOffset.UTC)` trừ khi hợp đồng dữ liệu nói rõ input là giờ UTC.

### 4.2. Lưu ý mất độ chính xác

`Instant` trong Java hỗ trợ nano-giây, nhưng CQL `timestamp` chỉ lưu **millisecond**. Khi ghi một `Instant` có phần lẻ nhỏ hơn millisecond, dữ liệu đọc lại không thể bảo toàn đầy đủ độ chính xác ban đầu.

```java
Instant input = Instant.parse("2026-11-25T07:30:00.123456789Z");
Instant storedPrecision = Instant.ofEpochMilli(input.toEpochMilli());

// storedPrecision = 2026-11-25T07:30:00.123Z
```

Nếu dùng `timestamp` làm **clustering column** cho bảng sự kiện, nhiều sự kiện có thể xảy ra trong cùng một millisecond. Để giữ từng hàng riêng và sắp xếp ổn định, có thể thêm `event_id` làm clustering column thứ hai hoặc cân nhắc `timeuuid` nếu đúng với yêu cầu của sự kiện. Đừng giả định `Instant.now()` luôn trả về giá trị duy nhất.

### 4.3. Cảnh giác với literal timestamp không có offset

Một chuỗi ngày giờ không kèm zone có thể được diễn giải khác nhau theo cấu hình client/phiên bản thư viện. Trong ứng dụng, ưu tiên bind giá trị `Instant` qua driver thay vì viết CQL bằng cách nối chuỗi.

Nếu cần chuyển chuỗi theo định dạng địa phương, dùng `DateTimeFormatter` và `ZoneId` đã xác định rõ. Khi so sánh hai thời điểm, so sánh `Instant`; khi hiển thị, mới chọn múi giờ cho người dùng.

## 5. `duration` ↔ `CqlDuration`: độ dài có thành phần lịch

Kiểu CQL `duration` không chỉ là một số millisecond hoặc second. Nó lưu **ba thành phần**:

1. **Months** – số tháng theo lịch.
2. **Days** – số ngày theo lịch.
3. **Nanoseconds** – phần thời lượng nhỏ hơn/khác ngày biểu diễn bằng nano-giây.

Java Driver 4 cung cấp `CqlDuration`:

```java
import com.datastax.oss.driver.api.core.data.CqlDuration;

CqlDuration window = CqlDuration.from("1mo2d3h");

int months = window.getMonths();
int days = window.getDays();
long nanos = window.getNanoseconds();

// months = 1; days = 2; nanos tương đương 3 giờ.
```

Trong Cassandra, `1mo` **không đồng nhất** với một số giây cố định vì tháng có số ngày khác nhau. `1d` theo lịch cũng không nhất thiết bằng 24 giờ trên đồng hồ ở khu vực có chuyển đổi DST. Do đó không thể chuyển mọi giá trị `CqlDuration` sang `java.time.Duration` theo một quy tắc bảo toàn ý nghĩa.

| Kiểu Java | Thành phần | Khi phù hợp |
| --- | --- | --- |
| `Duration` | Thời lượng theo giây và nano-giây, không có tháng theo lịch | Timeout, elapsed time, TTL tính bằng giây cố định |
| `Period` | Năm, tháng và ngày theo lịch, không chứa giờ/phút/giây | Gia hạn thêm 1 tháng; lịch lặp theo ngày |
| `CqlDuration` | Tháng, ngày, nano-giây của CQL | Lưu hoặc đọc nguyên vẹn kiểu `duration` Cassandra |

### 5.1. Vì sao `Period.ofDays(1)` khác `Duration.ofDays(1)`?

Ví dụ khu vực `America/New_York` chuyển sang DST vào tháng 3/2026:

```java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0, zone);

ZonedDateTime calendarDayLater = start.plus(Period.ofDays(1));
ZonedDateTime exactly24HoursLater = start.plus(Duration.ofDays(1));

// calendarDayLater:   2026-03-08 12:00, UTC-04:00
// exactly24HoursLater: 2026-03-08 13:00, UTC-04:00
```

Khác biệt này quan trọng với tính hạn dùng, lịch hẹn, thuê bao và báo cáo theo ngày địa phương. Khi nghiệp vụ nói “1 ngày” hoặc “1 tháng”, cần xác định đó là **khoảng thời gian tuyệt đối** hay **bước nhảy theo lịch**.

### 5.2. Giới hạn thực tế của `duration`

Do những thành phần như tháng và ngày không có tổng số nano-giây bất biến, `duration` không có thứ tự so sánh tuyệt đối giống một con số. Cassandra không cho dùng `duration` làm thành phần **primary key** và không nên thiết kế các truy vấn range/sort đòi hỏi so sánh `duration` như `timestamp`.

Nếu cần tìm “tất cả job có thời gian thực thi dài hơn 5 giây”, nên lưu **độ dài đo được bằng một số đơn vị cố định**, ví dụ `elapsed_millis bigint`, để truy vấn và phân tích. Một `duration` kiểu “1 tháng 2 ngày” phục vụ ý nghĩa lịch, khác với thời gian chạy job.

### 5.3. Duration không phải TTL

Trong Cassandra, TTL của cell/bản ghi thường được khai báo bằng **số giây** (ví dụ `USING TTL 86400`), không phải trực tiếp bằng kiểu CQL `duration`:

```sql
-- Minh họa TTL: 86400 giây = 24 giờ cố định.
UPDATE telemetry_by_tenant_day USING TTL 86400
SET payload = ?
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
```

TTL 86.400 giây khác với việc tính “hết hạn vào cuối ngày địa phương” khi ngày có 23 hoặc 25 giờ. Đối với retention/expiry quan trọng, cần thống nhất semantics và giới hạn TTL của phiên bản Cassandra trước khi phát hành.

## 6. Ví dụ CQL đầy đủ với bốn kiểu thời gian

Giả sử ứng dụng nhận telemetry của nhiều tenant. Cần đọc các sự kiện theo tenant, ngày UTC và khoảng thời gian để theo dõi thứ tự phát sinh:

```sql
CREATE TABLE telemetry_by_tenant_day (
    tenant_id         text,
    event_day         date,
    occurred_at       timestamp,
    event_id          uuid,
    time_of_day       time,
    processing_window duration,
    payload           text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Ở đây:

- `event_day date` là **ngày UTC** suy ra từ `occurred_at`, không phải ngày trên giao diện tùy múi giờ người dùng. Nó kết hợp `tenant_id` thành partition key.
- `occurred_at timestamp` biểu diễn **thời điểm phát sinh**, đồng thời là clustering column dùng cho truy vấn theo thời gian.
- `event_id uuid` là khóa phụ để các sự kiện cùng millisecond không ghi đè nhau và kết quả có thứ tự ổn định.
- `time_of_day time` chỉ lưu giờ trong ngày của sự kiện theo một **quy tắc đã chốt**; trong ví dụ này là giờ UTC. Nó không mang thông tin zone riêng.
- `processing_window duration` chứa một khoảng thời gian theo semantics CQL; đó là cột thường, không nằm trong primary key.

CQL đọc một partition:

```sql
SELECT tenant_id, event_day, occurred_at, event_id,
       time_of_day, processing_window, payload
FROM telemetry_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 50;
```

CQL đọc trong một khoảng của **cùng partition**:

```sql
SELECT * FROM telemetry_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 50;
```

Cần cung cấp **đủ partition key**, tức `tenant_id` và `event_day`, rồi mới lọc khoảng của clustering column `occurred_at`. Không thể chỉ thêm một phương thức `findByOccurredAtBetween(...)` để Cassandra quét hiệu quả mọi tenant/ngày. Nếu khoảng truy vấn đi qua nhiều ngày UTC, service cần chủ động đọc các partition theo ngày tương ứng, kiểm soát fan-out và merge kết quả.

## 7. Entity mapping trong Spring Data Cassandra

Entity Java thể hiện đầy đủ bốn kiểu, với khóa ghép tương ứng CQL.

```java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class TelemetryKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private UUID eventId;

    public TelemetryKey() {}

    // Bổ sung constructor, getters/setters, equals() và hashCode()
    // với ngữ nghĩa giá trị để dùng an toàn làm khóa entity.
}
```

```java
import java.time.LocalTime;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("telemetry_by_tenant_day")
public class TelemetryRecord {

    @PrimaryKey
    private TelemetryKey key;

    @Column("time_of_day")
    private LocalTime timeOfDay;

    @Column("processing_window")
    private CqlDuration processingWindow;

    @Column("payload")
    private String payload;

    public TelemetryRecord() {}

    // Bổ sung constructor và getters/setters, bao gồm getKey().
}
```

Đây là **khung mapping** có chủ đích, chưa phải hai class Java có thể dùng ngay: cần bổ sung những phương thức được ghi chú. `CqlDuration` ở đây là kiểu native của Java Driver 4; nếu nghiệp vụ muốn dùng `Duration` hoặc `Period`, cần kiểm soát chuyển đổi rõ ràng, có thể qua custom converter, thay vì mặc định hai kiểu tương đương.

Ví dụ tạo khóa từ sự kiện, sử dụng UTC để tính cả ngày và giờ:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.util.UUID;

Instant occurredAt = Instant.now();
LocalDate eventDay = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
LocalTime timeOfDay = occurredAt.atOffset(ZoneOffset.UTC).toLocalTime();
UUID eventId = UUID.randomUUID();

// Tạo TelemetryKey(tenantId, eventDay, occurredAt, eventId)
// và TelemetryRecord(..., timeOfDay, processingWindow, payload)
// bằng constructor khi đã hoàn thiện trong dự án.
```

Vì `timestamp` lưu millisecond, `timeOfDay` được suy từ `occurredAt` nên để round-trip nhất quán hãy cân nhắc chuẩn hóa `occurredAt` về millisecond **trước** khi suy `timeOfDay` và tạo key. Nếu để `time` lưu nanosecond còn `timestamp` mất phần nhỏ hơn millisecond, hai cột có thể khác độ chính xác dù cùng chỉ đến một sự kiện.

## 8. Repository, CassandraTemplate và CqlTemplate nhìn kiểu thời gian ra sao?

### 8.1. Repository: truyền giá trị Java có kiểu

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface TelemetryRepository
        extends CassandraRepository<TelemetryRecord, TelemetryKey> {

    @Query("SELECT * FROM telemetry_by_tenant_day " +
           "WHERE tenant_id = ?0 AND event_day = ?1 " +
           "AND occurred_at >= ?2 AND occurred_at < ?3 LIMIT 50")
    List<TelemetryRecord> findInUtcWindow(
            String tenantId, LocalDate eventDay,
            Instant fromInclusive, Instant toExclusive);
}
```

`LocalDate` được bind vào cột CQL `date`, `Instant` vào `timestamp`; `TelemetryRecord` nhận `LocalTime` và `CqlDuration` qua entity mapping. Đặt tên phương thức `findInUtcWindow` nhắc rằng hai biên thời gian và bucket ngày phải thống nhất quy tắc UTC.

Trong production, validate `fromInclusive < toExclusive`, giới hạn chiều dài khoảng truy vấn và số kết quả. Đoạn ví dụ minh họa **một bucket ngày UTC**; nếu khoảng vượt qua nửa đêm UTC, không được chỉ truyền ngày của `fromInclusive` rồi kỳ vọng có đủ dữ liệu của các ngày tiếp theo.

### 8.2. CassandraTemplate: tạo `Query` từ điều kiện có kiểu

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

public List<TelemetryRecord> findWithTemplate(
        CassandraTemplate template, String tenantId, LocalDate day,
        Instant fromInclusive, Instant toExclusive) {

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("event_day").is(day))
            .and(Criteria.where("occurred_at").gte(fromInclusive))
            .and(Criteria.where("occurred_at").lt(toExclusive))
            .limit(50);

    return template.select(query, TelemetryRecord.class);
}
```

Trong ví dụ, toàn bộ partition key được cung cấp; `Query` và mapping chuyển dữ liệu theo metadata của entity. Dù dùng template, các giới hạn về **clustering order, partition key và `LIMIT`** vẫn là giới hạn của Cassandra.

### 8.3. CqlTemplate và Java Driver: đọc hàng thô

`CqlTemplate` hỗ trợ xử lý ở tầng CQL thấp hơn; Java Driver 4 cung cấp các getter có kiểu trên `Row`, chẳng hạn:

```java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;

// row là một Row đã được truy vấn bằng CqlTemplate hoặc CqlSession.
LocalDate day = row.getLocalDate("event_day");
Instant occurredAt = row.getInstant("occurred_at");
LocalTime timeOfDay = row.getLocalTime("time_of_day");
CqlDuration window = row.getCqlDuration("processing_window");
```

Ở tầng này, ứng dụng chủ động chọn các getter và ánh xạ kết quả; với Repository hoặc `CassandraTemplate`, mapping của Spring Data làm thay phần lớn công việc. Khi giá trị CQL có thể là `null`, cần kiểm tra và áp dụng quy tắc nghiệp vụ phù hợp trước khi sử dụng.

## 9. Lọc theo ngày của người dùng: đừng lấy cố định 24 giờ

Giả sử API cần “mọi sự kiện trong ngày 08/03/2026 tại New York”. Ngày địa phương đó có chuyển sang DST, nên **ngày lịch** không nhất thiết dài 24 giờ.

Cách tính hai mốc hợp lý:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("America/New_York");
LocalDate userDay = LocalDate.of(2026, 3, 8);

Instant fromInclusive = userDay.atStartOfDay(zone).toInstant();
Instant toExclusive = userDay.plusDays(1)
        .atStartOfDay(zone).toInstant();

// Khoảng này dài 23 giờ ở New York ngày chuyển sang DST.
```

Khoảng dạng **`[fromInclusive, toExclusive)`** tránh lỗi ở cuối ngày vì độ chính xác của `timestamp` và ứng dụng có thể khác nhau. Nó cũng giúp nối các ngày liên tiếp mà không tạo một millisecond bị tính hai lần.

Tuy nhiên, truy vấn trên bảng `telemetry_by_tenant_day` phân vùng theo **ngày UTC**. Khoảng giờ địa phương chuyển sang UTC có thể chạm tới **hai partition `event_day` khác nhau**. Service cần xác định những ngày UTC giao với khoảng rồi truy vấn từng partition, hoặc chọn bảng đọc khác nếu đây là access pattern nóng. Không thể chỉ đưa `userDay` vào cột `event_day` khi writer đã dùng ngày UTC.

Quyết định một khoảng thời gian có đọc nhiều partition hay không là phần của **thiết kế truy vấn trước repository**; thêm annotation chuyển đổi ngày không giải quyết fan-out của Cassandra.

## 10. Những lỗi thường gặp

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Dùng `LocalDateTime` như một thời điểm tuyệt đối | Cùng dữ liệu bị lệch giờ khi chạy máy ở zone khác | Chọn `Instant` cho `timestamp`; chuyển `LocalDateTime` bằng `ZoneId` rõ ràng |
| Dùng `LocalDate` theo timezone client nhưng partition ghi theo UTC | Thiếu hoặc không tìm thấy sự kiện | Chuẩn hóa quy tắc bucket và chuyển range sang UTC trước khi xác định partition |
| Nghĩ `time` có sẵn ngày/múi giờ | Không thể tái tạo thời điểm lịch hẹn | Lưu thêm ngày và `ZoneId` khi nghiệp vụ cần |
| Giả định `timestamp` giữ được nanosecond | Mất phần lẻ sau readback hoặc hai sự kiện trùng clustering key | Chuẩn hóa millisecond, thêm khóa phụ/tie-breaker phù hợp |
| Đổi `CqlDuration` có tháng sang `Duration` bằng số giây cố định | Ngày kết thúc sai khi qua tháng hoặc DST | Giữ ngữ nghĩa lịch; dùng `Period`/`ZonedDateTime` theo quy tắc nghiệp vụ |
| Dùng `duration` làm primary key hoặc để sắp xếp | CQL bị từ chối hoặc không có thứ tự so sánh xác định | Dùng timestamp/epoch/cột số riêng cho trường cần order |
| Dùng `duration` thay TTL | Hiểu sai đơn vị và thời gian hết hạn | TTL là số giây; định nghĩa riêng semantics expiry |
| Lọc toàn bảng bằng `WHERE occurred_at BETWEEN ...` | Truy vấn không đáp ứng quy tắc partition key | Thiết kế bảng theo tenant/bucket; giới hạn và kiểm soát fan-out |
| Phân trang bằng `OFFSET` hoặc `COUNT(*)` toàn bảng | Đọc nhiều dữ liệu, độ trễ cao | Paging state/cursor theo clustering key, limit và bucket phù hợp |
| Dùng định dạng chuỗi tùy tiện cho timestamp | Khác biệt parse hoặc lệch offset giữa môi trường | Bind `Instant`; định nghĩa một định dạng trao đổi có offset rõ ràng |

## 11. Checklist trước khi đưa vào production

1. **Xác định ngữ nghĩa:** cột là ngày lịch, giờ trong ngày, thời điểm tuyệt đối hay thời lượng có thành phần lịch?
2. **Chọn kiểu Java:** ưu tiên `LocalDate`, `LocalTime`, `Instant` và `CqlDuration` đúng với CQL; chỉ dùng converter bổ sung khi có quy tắc chuyển đổi rõ ràng.
3. **Chốt múi giờ ở biên hệ thống:** lưu `ZoneId` khi cần tái hiện lịch địa phương, lưu thời điểm sự kiện dưới dạng `Instant`.
4. **Xác định độ chính xác:** timestamp Cassandra là millisecond; time có thể tới nanosecond; dùng khóa phụ cho thứ tự ổn định.
5. **Thiết kế truy vấn:** mọi `WHERE` và `ORDER BY` phải khớp partition/clustering columns; API lấy một ngày địa phương có thể cần nhiều bucket UTC.
6. **Kiểm soát retention:** TTL là số giây, cần làm rõ tính theo 24 giờ hay đến mốc lịch và tác động lên tombstone.
7. **Kiểm thử ranh giới:** nửa đêm, năm mới, ngày nhuận, thời điểm DST, cùng millisecond và thời gian ở nhiều vùng.
8. **Quan sát tính nhất quán và hiệu năng:** theo dõi lỗi chuyển đổi, p95/p99, paging, fan-out và kết quả đọc so với query contract.

## 12. Bài tập tự kiểm tra

**Bài tập A.** Một hệ thống đặt lịch ở `Asia/Ho_Chi_Minh` nhận `2026-11-25` và `09:30`. Có thể ghi `09:30` vào `timestamp` luôn không?

**Đáp án gợi ý:** Chưa. Cần kết hợp `LocalDate`, `LocalTime` và `ZoneId`, xử lý quy tắc vùng rồi mới suy ra `Instant`. Nếu nghiệp vụ là lịch lặp “09:30 mỗi ngày”, cần lưu thông tin giờ địa phương và zone, không chỉ một `Instant` duy nhất.

**Bài tập B.** Một cảm biến gửi hai sự kiện lúc `07:30:00.123456Z` và `07:30:00.123789Z`, với CQL `timestamp` là clustering key duy nhất trong cùng partition. Nguy cơ là gì?

**Đáp án gợi ý:** Cả hai có thể cùng lưu thành `07:30:00.123Z` ở độ chính xác millisecond và trùng khóa hàng. Thêm `event_id` vào clustering key để giữ hai hàng riêng và có thứ tự ổn định.

**Bài tập C.** Một chính sách ghi “hạn sử dụng tăng thêm 1 tháng kể từ ngày kích hoạt”. Có nên chuyển `1mo` thành 30 × 86.400 giây rồi cộng vào `Instant`?

**Đáp án gợi ý:** Không nếu yêu cầu là theo tháng lịch. Cần quy tắc với `LocalDate`/`ZonedDateTime` và `Period` hoặc thành phần calendar tương ứng của `CqlDuration`; số ngày một tháng thay đổi.

**Bài tập D.** Bảng phân vùng theo `(tenant_id, event_day_utc)` nhưng UI lọc ngày tại New York. Một lời gọi repository chỉ truyền `event_day_utc = userDay` có chắc đủ dữ liệu không?

**Đáp án gợi ý:** Không. Tính hai mốc `Instant` của ngày địa phương, xác định các bucket UTC giao với khoảng và đọc những partition phù hợp. Với fan-out lớn phải kiểm tra thiết kế dữ liệu hoặc giới hạn truy vấn.

## Kết luận

Trong Cassandra, `date`, `time`, `timestamp` và `duration` trả lời **bốn câu hỏi khác nhau**: ngày nào, giờ nào trong ngày, thời điểm tuyệt đối nào, và khoảng thời gian theo thành phần nào. Với Spring Data Cassandra và Java Driver 4, các kiểu Java thường tương ứng là **`LocalDate`, `LocalTime`, `Instant` và `CqlDuration`**.

Khi thiết kế entity và repository, hãy chốt **múi giờ, độ chính xác, quy tắc bucket, thứ tự clustering và ý nghĩa duration** trước khi ghi dữ liệu. Các lựa chọn đó quyết định liệu truy vấn CQL có trả đúng kết quả ở ranh giới ngày/DST hay không, và liệu ứng dụng có đọc hiệu quả trên mô hình partition phân tán của Apache Cassandra.
