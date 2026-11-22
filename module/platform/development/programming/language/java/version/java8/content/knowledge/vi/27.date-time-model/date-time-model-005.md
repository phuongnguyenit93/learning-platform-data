# Factory `of`, `parse` và `now` trong mô hình ngày giờ Java 8+

> **Ngữ cảnh:** `Mô hình ngày giờ` — API `java.time` được đưa vào Java 8 và vẫn là lựa chọn tiêu chuẩn trên JDK hiện đại. Bài này phân biệt ba nhóm static factory quan trọng: **`of(...)` tạo giá trị từ thành phần đã biết**, **`parse(...)` chuyển văn bản thành giá trị ngày giờ**, và **`now(...)` lấy giá trị theo đồng hồ**. Trọng tâm là chọn đúng kiểu dữ liệu, xác định múi giờ, tránh lỗi ngày không hợp lệ và viết mã có thể kiểm thử bằng `Clock`. Ví dụ hoàn chỉnh tương thích Java 8, chạy trên JDK 17+.

## 1. Ba câu hỏi dẫn đến ba factory

Khi tạo giá trị thời gian, hãy xác định dữ liệu đến từ đâu:

| Đầu vào / yêu cầu | Factory thích hợp | Ví dụ |
| --- | --- | --- |
| Có sẵn năm, tháng, ngày | `of(...)` | `LocalDate.of(2024, 2, 29)` |
| Có sẵn giờ, phút, giây | `of(...)` | `LocalTime.of(9, 45, 30)` |
| Có văn bản ISO hoặc định dạng quy định | `parse(...)` | `LocalDate.parse("2024-02-29")` |
| Muốn ngày hiện tại theo một múi giờ | `now(ZoneId)` hoặc `now(Clock)` | `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` |
| Muốn thời điểm hiện tại trên timeline | `Instant.now(Clock)` / `Instant.now()` | `Instant.now()` |
| Muốn kết quả **cố định để test** | `now(Clock.fixed(...))` | `LocalDateTime.now(fixedClock)` |

Ba họ method đều **tạo một giá trị mới**; chúng không tự thay đổi ngày giờ đã tồn tại. Đa số các kiểu giá trị `java.time` phổ biến là **immutable**, nên các phương thức như `plusDays` hoặc `withMonth` cũng trả giá trị mới.

Một ví dụ tóm tắt:

```java
LocalDate configured = LocalDate.of(2024, 2, 29);
LocalDate fromText = LocalDate.parse("2024-02-29");
LocalDate observed = LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"));
```

- `configured` phụ thuộc các tham số số nguyên.
- `fromText` phụ thuộc chuỗi cần phân tích và cú pháp ISO.
- `observed` phụ thuộc **thời điểm chạy**, đồng hồ máy và múi giờ được chọn. Không ghi một ngày cụ thể làm “stdout chắc chắn” cho lời gọi `now` dùng đồng hồ thật.

## 2. Chọn đúng kiểu trước khi chọn factory

Java 8 bổ sung nhiều kiểu thời gian có ý nghĩa khác nhau. Không nên chỉ chọn kiểu nào “có đủ field” rồi tự đoán offset.

| Kiểu | Biểu diễn | Có múi giờ/offset không? | Factory tiêu biểu |
| --- | --- | --- | --- |
| `LocalDate` | Ngày trên lịch | Không | `of`, `parse`, `now` |
| `LocalTime` | Giờ trong ngày | Không | `of`, `parse`, `now` |
| `LocalDateTime` | Ngày + giờ địa phương | Không | `of`, `parse`, `now` |
| `Instant` | Một thời điểm trên UTC timeline | Không lưu ZoneId, nhưng là thời điểm tuyệt đối | `ofEpochSecond`, `ofEpochMilli`, `parse`, `now` |
| `OffsetDateTime` | LocalDateTime + UTC offset cố định của bản ghi | Có `ZoneOffset` | `of`, `parse`, `now` |
| `ZonedDateTime` | Ngày giờ với region time zone và quy tắc vùng | Có `ZoneId` và offset hiện hành | `of`, `parse`, `now` |
| `YearMonth` / `MonthDay` | Một phần ngày trên lịch | Không | `of`, `parse` |
| `Duration` / `Period` | Khoảng thời gian theo duration hoặc lượng lịch | Không phải mốc thời gian | `ofMinutes` / `ofDays` v.v. |

**Hai khái niệm dễ lẫn:**

- `LocalDateTime` như `2024-02-29T09:45:30` **không biết** đó là giờ tại Hà Nội, Tokyo hay London. Không thể suy ra một `Instant` duy nhất nếu thiếu offset hoặc zone.
- `Instant` như `2024-02-29T02:45:30Z` biểu diễn một **thời điểm duy nhất**. Cùng Instant đó có thể hiển thị là `09:45:30` tại Việt Nam, với offset `+07:00`.

Giữ phân tách này từ đầu sẽ giúp tránh các lỗi do giả định giờ địa phương là UTC.

### 2.1. `ZoneId` khác `ZoneOffset`

`ZoneOffset.ofHours(7)` mang ý nghĩa **UTC+07:00 cố định**. `ZoneId.of("Asia/Ho_Chi_Minh")` là **mã vùng thời gian**, nơi hệ thống tra quy tắc offset của vùng theo ngày giờ. Với các vùng có daylight-saving time, offset có thể thay đổi theo mùa hoặc lịch sử.

Ví dụ:

```java
ZoneId region = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneOffset fixedOffset = ZoneOffset.ofHours(7);
```

Đối với một thời điểm tại Việt Nam trong ví dụ, hai cách có thể cho cùng offset nhưng **không đồng nghĩa về hợp đồng**. Nếu ứng dụng cần quy tắc múi giờ theo địa danh, ưu tiên `ZoneId` IANA; nếu dữ liệu chỉ cung cấp offset cụ thể, biểu diễn bằng `OffsetDateTime`.

## 3. Factory `of(...)`: tạo từ các thành phần đã biết

Các factory `of` phục vụ dữ liệu **đã được tách thành trường** và phải kiểm tra tính hợp lệ của tổ hợp. Chúng không phải hàm phân tích text.

### 3.1. `LocalDate.of`

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
LocalDate christmas = LocalDate.of(2024, 12, 25);
LocalDate firstOfMonth = LocalDate.of(2024, Month.FEBRUARY, 1);
```

Kết quả `leapDay.toString()` là `2024-02-29`; năm 2024 nhuận nên ngày 29/2 hợp lệ. Nếu thử:

```java
// Không hợp lệ: 2023 không phải năm nhuận.
// LocalDate invalid = LocalDate.of(2023, 2, 29);
```

Lời gọi thực tế sẽ ném `DateTimeException` do tổ hợp ngày-tháng-năm không hợp lệ. Không có cơ chế “âm thầm chuyển 29/2 thành 1/3” trong `LocalDate.of`.

Tháng có thể truyền số `1..12` hoặc enum `Month`. Các tham số là **năm, tháng, ngày**, không phải tháng zero-based. Không cộng/trừ 1 như một số API cũ.

### 3.2. `LocalTime.of`

```java
LocalTime opening = LocalTime.of(9, 0);
LocalTime meeting = LocalTime.of(9, 45, 30);
LocalTime precise = LocalTime.of(9, 45, 30, 123_000_000);
```

Phần nano-of-second có phạm vi `0..999_999_999`; giây và phút là `0..59`, giờ là `0..23`. `LocalTime.of(24, 0)` là không hợp lệ theo mô hình một giờ trong ngày (dù một số biểu diễn text ISO có quy tắc khác khi xử lý đặc biệt). Hãy dùng `plusDays` trên ngày tương ứng nếu cần “ngày hôm sau lúc 00:00”.

### 3.3. `LocalDateTime.of`

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(9, 45, 30);

LocalDateTime combined = LocalDateTime.of(date, time);
LocalDateTime direct = LocalDateTime.of(2024, 2, 29, 9, 45, 30);
// Hai giá trị là cùng một LocalDateTime.
```

Không thêm hậu tố `Z` cho `LocalDateTime` trong suy luận của chương trình: chữ `Z` là dấu UTC offset zero ở những định dạng có offset. Để xác định một mốc thực trên timeline, phải kết hợp với zone/offset thích hợp.

### 3.4. `ZonedDateTime.of` và `OffsetDateTime.of`

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime local = LocalDateTime.of(2024, 2, 29, 9, 45, 30);

ZonedDateTime zoned = ZonedDateTime.of(local, vietnam);
OffsetDateTime offset = OffsetDateTime.of(local, ZoneOffset.ofHours(7));

Instant a = zoned.toInstant();
Instant b = offset.toInstant();
// Cả a và b bằng 2024-02-29T02:45:30Z trong ví dụ.
```

Trong các vùng có daylight-saving time, `ZonedDateTime.of(local, zone)` có thể phải **giải quyết giờ không tồn tại** hoặc **giờ xuất hiện hai lần**; không luôn giữ nguyên các thành phần local được truyền vào. Xem phần DST bên dưới.

### 3.5. `Instant.ofEpochSecond` và `Instant.ofEpochMilli`

```java
Instant epoch = Instant.ofEpochSecond(0);
// 1970-01-01T00:00:00Z.

Instant oneSecond = Instant.ofEpochSecond(1);
Instant oneThousandMillis = Instant.ofEpochMilli(1000);
// oneSecond.equals(oneThousandMillis) == true.
```

Cần đọc rõ đơn vị của dữ liệu: **seconds** và **milliseconds** khác nhau 1000 lần. Đừng dùng `ofEpochSecond` cho số nhận từ API quy định epoch milliseconds. Một số hệ thống còn gửi microseconds/nanoseconds, cần chuyển đổi có kiểm tra.

### 3.6. Các factory `of` cùng họ

`YearMonth.of(2024, 2)` tạo năm/tháng, có `atEndOfMonth()` trả `2024-02-29`. `MonthDay.of(2, 29)` biểu diễn tháng/ngày không có năm. `Period.ofDays(7)` mô tả **7 ngày theo lịch**, trong khi `Duration.ofHours(24)` mô tả **24 giờ thời gian vật lý**; quanh thời điểm chuyển DST hai khái niệm có thể khác nhau khi cộng vào thời điểm có zone.

**Lựa chọn phụ thuộc nghĩa dữ liệu:** ngày sinh dùng `LocalDate`; lịch hẹn địa phương cùng region zone dùng `ZonedDateTime` hoặc cặp local + zone được xác nhận; timestamp event dùng `Instant`.

## 4. Factory `parse(...)`: chuyển từ văn bản sang kiểu thời gian

`parse` không tự đọc đồng hồ. Nó dựa vào **nội dung chuỗi đầu vào** và format/parser đang dùng.

### 4.1. ISO-8601 mặc định

```java
LocalDate d = LocalDate.parse("2024-02-29");
LocalTime t = LocalTime.parse("09:45:30");
LocalDateTime ldt = LocalDateTime.parse("2024-02-29T09:45:30");
Instant instant = Instant.parse("2024-02-29T02:45:30Z");
OffsetDateTime odt = OffsetDateTime.parse("2024-02-29T09:45:30+07:00");
ZonedDateTime zdt = ZonedDateTime.parse(
        "2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]");
```

Đây là **snippet** dùng các loại được import từ `java.time`; trong chương trình hoàn chỉnh phía dưới có ví dụ đầy đủ.

Các ký hiệu quan trọng:

- `2024-02-29` là ngày, không chỉ ra giờ.
- `09:45:30` là giờ địa phương trong ngày, không có ngày.
- Chữ `T` phân cách ngày và giờ trong dạng ISO local date-time.
- Chữ `Z` trên `Instant` nghĩa là offset UTC+00:00.
- `+07:00` là **offset**, không phải tên region time zone.
- Dấu ngoặc vuông `[Asia/Ho_Chi_Minh]` trong dạng ZonedDateTime nêu ZoneId của vùng.

Không chỉ vì chuỗi chứa ngày và giờ mà có thể parse nó sang bất kỳ kiểu nào: `LocalDate.parse("2024-02-29T09:45:30")` không nhận chuỗi đầy đủ này theo formatter mặc định. Chọn **loại kết quả** và **formatter** tương ứng với cấu trúc đầu vào.

### 4.2. Parse không tự đoán múi giờ

```java
LocalDateTime local =
        LocalDateTime.parse("2024-02-29T09:45:30");

// Thiếu thông tin để xác định một Instant duy nhất.
// Cần biết thời gian này thuộc múi giờ hoặc offset nào.
Instant result = local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

Việc gắn một `ZoneId` cho LocalDateTime là **quyết định ứng dụng**: nguồn dữ liệu phải quy định vùng đó. Nếu text thực chất mô tả một timestamp có offset, tốt hơn parse trực tiếp bằng `OffsetDateTime.parse` rồi chuyển sang `Instant` khi cần.

### 4.3. Dùng `DateTimeFormatter` cho định dạng riêng

```java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate d = LocalDate.parse("29/02/2024", f);
// d == 2024-02-29.
```

Các thành phần:

- `dd`: ngày hai chữ số.
- `MM`: tháng hai chữ số.
- `uuuu`: proleptic year (năm theo ISO), phù hợp cho parsing strict.
- `Locale.ROOT`: dùng locale trung tính khi pattern chỉ chứa chữ số/ký hiệu (cũng có thể chỉ định locale cụ thể khi có tên tháng).
- `ResolverStyle.STRICT`: yêu cầu tổ hợp field tạo ngày hợp lệ, không tự chỉnh ngày sai theo chính sách lenient hoặc SMART.

### 4.4. Vì sao `uuuu` được ưu tiên khi parse strict?

Pattern `yyyy` là **year-of-era**, còn `uuuu` là **proleptic year**. Khi dùng `ResolverStyle.STRICT`, pattern `dd/MM/yyyy` có thể cần thêm thông tin era để tạo `LocalDate`, trong khi `dd/MM/uuuu` biểu diễn trực tiếp một năm của hệ thống ISO.

**Lưu ý khác:** `YYYY` viết hoa là **week-based year**, không phải năm lịch theo nghĩa thông thường. Gần ranh giới năm, nó có thể cho kết quả khác `uuuu`. Đừng dùng `YYYY-MM-dd` cho ngày lịch chỉ vì nhìn nó giống `yyyy-MM-dd`.

### 4.5. Default formatter không đồng nghĩa luôn strict

`DateTimeFormatter.ofPattern(...)` mặc định dùng **ResolverStyle.SMART**, không phải STRICT. Một số tổ hợp ngày sai có thể được chuẩn hóa theo quy tắc của SMART. Nếu bài toán yêu cầu dữ liệu đầu vào phải hợp lệ **đúng như khai báo**, đặt `withResolverStyle(ResolverStyle.STRICT)` và test tình huống biên (ngày 29/2 năm không nhuận, 31/4, tháng 13).

Ví dụ:

```java
DateTimeFormatter strict =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

try {
    LocalDate.parse("29/02/2023", strict);
    throw new AssertionError("Must reject invalid date");
} catch (DateTimeParseException expected) {
    // Đầu vào không hợp lệ, đúng kỳ vọng.
}
```

Đừng viết ứng dụng bắt tất cả `RuntimeException` rồi âm thầm thay ngày bằng hôm nay; việc đó có thể làm sai tính toàn vẹn dữ liệu.

### 4.6. Formatter có locale khi chứa chữ

```java
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("d MMM uuuu", Locale.ENGLISH);

LocalDate date = LocalDate.parse("29 Feb 2024", english);
// 2024-02-29.
```

Tên tháng, thứ, AM/PM phụ thuộc locale. Khi làm việc với dữ liệu machine-to-machine, ưu tiên **ISO-8601 ổn định**; chỉ dùng định dạng địa phương khi input/output thực sự quy định như vậy.

### 4.7. Parse exception

`LocalDate.parse` và các hàm parse cụ thể ném `DateTimeParseException` khi chuỗi không khớp định dạng hoặc giá trị không thể giải thành kiểu yêu cầu. `DateTimeParseException` là một subtype của `DateTimeException`. Khi nhận input từ người dùng hoặc API:

1. Xác định định dạng được chấp nhận.
2. Parse bằng formatter đúng (ưu tiên strict nếu cần validation).
3. Bắt `DateTimeParseException` ở ranh giới nhập liệu.
4. Trả thông báo có ý nghĩa hoặc ghi nhận lỗi dữ liệu, không thay đổi âm thầm.
5. Không dùng exception như cách chọn giữa hàng chục định dạng thiếu thiết kế; tốt hơn có hợp đồng rõ.

Ví dụ xử lý ở boundary:

```java
static LocalDate parseBusinessDate(String raw, DateTimeFormatter f) {
    try {
        return LocalDate.parse(raw, f);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Ngày phải có định dạng dd/MM/uuuu và hợp lệ", ex);
    }
}
```

*Đây là snippet cho một method nằm trong class, chưa phải chương trình Java độc lập.*

## 5. Factory `now(...)`: lấy thời điểm từ đồng hồ

Khác với `of` và `parse`, `now` tham chiếu **một đồng hồ** (clock), do đó giá trị phụ thuộc thời gian thực thi.

### 5.1. `now()` — dùng system clock và mặc định của loại

```java
LocalDate today = LocalDate.now();
LocalTime time = LocalTime.now();
LocalDateTime localNow = LocalDateTime.now();
Instant instantNow = Instant.now();
ZonedDateTime zonedNow = ZonedDateTime.now();
```

- `LocalDate.now()` và `LocalDateTime.now()` dùng system clock tại **system default zone**.
- `Instant.now()` là thời điểm tuyệt đối; đối tượng `Instant` không giữ timezone hiển thị.
- `ZonedDateTime.now()` chứa region zone tương ứng system default zone và offset áp dụng tại thời điểm đó.

**Không hardcode stdout cho `now()` trong tài liệu:** kết quả thực tế khác nhau theo lúc chạy, múi giờ hệ điều hành và cấu hình clock. Dùng `now()` trong logic chính của ứng dụng khi cần thời điểm hệ thống thật và yêu cầu đã rõ; trong test nên dùng Clock được tiêm vào.

### 5.2. `now(ZoneId)` — chỉ định vùng

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate vietnamToday = LocalDate.now(vietnam);
LocalDateTime vietnamLocalNow = LocalDateTime.now(vietnam);
ZonedDateTime vietnamZonedNow = ZonedDateTime.now(vietnam);
```

Chọn `now(zone)` khi **ngày địa phương** là dữ liệu nghiệp vụ: ngày chốt đơn theo chi nhánh, lịch làm việc của văn phòng, ngày giao hàng theo khu vực. Tránh phụ thuộc `ZoneId.systemDefault()` vô tình khác nhau giữa laptop dev, container, CI và production.

`now(zone)` không truyền một clock giả lập; nó sử dụng system clock với vùng được chỉ định. Nếu code cần test ổn định, hãy dùng overload `now(Clock)` thay vì cố mock static method.

### 5.3. `now(Clock)` — lựa chọn quan trọng nhất cho test

Các kiểu `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime` và `Instant` có overload dùng `Clock` phù hợp.

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant base = Instant.parse("2024-02-29T02:45:30Z");
Clock fixed = Clock.fixed(base, zone);

LocalDate date = LocalDate.now(fixed);
LocalTime time = LocalTime.now(fixed);
LocalDateTime local = LocalDateTime.now(fixed);
Instant instant = Instant.now(fixed);
ZonedDateTime zoned = ZonedDateTime.now(fixed);
```

Ở đây dữ liệu cố định để kiểm thử:

```text
LocalDate      2024-02-29
LocalTime      09:45:30
LocalDateTime  2024-02-29T09:45:30
Instant        2024-02-29T02:45:30Z
ZonedDateTime  2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]
```

Các dòng này không phụ thuộc thời gian thật; chúng xuất phát từ cùng một `Clock.fixed` và cùng ZoneId.

### 5.4. Đưa Clock vào service thay vì gọi `now()` rải rác

```java
final class ExpiryPolicy {
    private final Clock clock;

    ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
```

Lợi ích:

- Test điều kiện trước/đúng/sau hạn bằng `Clock.fixed` mà không đợi thực tế.
- Một quy trình dùng cùng chính sách clock, dễ kiểm soát timezone.
- Giảm phụ thuộc toàn cục vào máy đang chạy.
- Không cần thay đổi toàn bộ chương trình chỉ để mock static `now()`.

Ở composition root, có thể cấp `Clock.systemUTC()` hoặc `Clock.system(ZoneId.of(...))`. Trong test, cấp `Clock.fixed(instant, zone)`. `Clock` là abstraction của **wall clock** để lấy mốc thời gian; không phải công cụ tốt nhất để đo khoảng chạy benchmark. Để đo elapsed time nội bộ ngắn trên JVM, cân nhắc `System.nanoTime()` vì mục đích monotonic measurement (nó không đại diện cho timestamp lịch).

## 6. Chương trình đầy đủ: `of`, `parse`, `now(Clock)`

Bài demo tạo các giá trị ngày giờ từ thành phần, phân tích ISO, phân tích text theo formatter strict, cố tình kiểm tra ngày không hợp lệ, lấy `now` với clock cố định và kiểm tra DST gap. Mọi kết quả cần so sánh đều **có thể lặp lại**.

Tạo tệp **`TimeFactoriesDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class TimeFactoriesDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        LocalTime meeting = LocalTime.of(9, 45, 30);
        LocalDateTime local = LocalDateTime.of(leapDay, meeting);
        Instant instant = Instant.parse("2024-02-29T02:45:30Z");
        OffsetDateTime offset = OffsetDateTime.of(local, ZoneOffset.ofHours(7));
        ZonedDateTime zoned = ZonedDateTime.of(local, vietnam);

        LocalDate isoDate = LocalDate.parse("2024-02-29");
        LocalDateTime isoLocal = LocalDateTime.parse("2024-02-29T09:45:30");
        OffsetDateTime isoOffset =
                OffsetDateTime.parse("2024-02-29T09:45:30+07:00");

        DateTimeFormatter strictVietnamese =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        LocalDate custom = LocalDate.parse("29/02/2024", strictVietnamese);
        boolean rejected = false;
        try {
            LocalDate.parse("29/02/2023", strictVietnamese);
        } catch (DateTimeParseException expected) {
            rejected = true;
        }

        Clock fixed = Clock.fixed(instant, vietnam);
        LocalDate clockDate = LocalDate.now(fixed);
        LocalTime clockTime = LocalTime.now(fixed);
        LocalDateTime clockLocal = LocalDateTime.now(fixed);
        ZonedDateTime clockZoned = ZonedDateTime.now(fixed);
        Instant clockInstant = Instant.now(fixed);

        ZonedDateTime parisGap = LocalDateTime.of(2024, 3, 31, 2, 30)
                .atZone(ZoneId.of("Europe/Paris"));

        System.out.println("of date: " + leapDay);
        System.out.println("of time: " + meeting);
        System.out.println("of local: " + local);
        System.out.println("parse instant: " + instant);
        System.out.println("of offset: " + offset);
        System.out.println("of zoned: " + zoned);
        System.out.println("parse ISO: " + isoDate + " | " + isoLocal);
        System.out.println("parse offset: " + isoOffset);
        System.out.println("parse custom: " + custom);
        System.out.println("invalid rejected: " + rejected);
        System.out.println("fixed now date: " + clockDate);
        System.out.println("fixed now time: " + clockTime);
        System.out.println("fixed now local: " + clockLocal);
        System.out.println("fixed now instant: " + clockInstant);
        System.out.println("fixed now zoned: " + clockZoned);
        System.out.println("Paris gap resolved: " + parisGap);

        if (!leapDay.equals(isoDate)
                || !meeting.equals(LocalTime.parse("09:45:30"))
                || !local.equals(isoLocal)
                || !instant.equals(offset.toInstant())
                || !instant.equals(zoned.toInstant())
                || !custom.equals(leapDay) || !rejected
                || !clockDate.equals(leapDay)
                || !clockTime.equals(meeting)
                || !clockLocal.equals(local)
                || !clockInstant.equals(instant)
                || !clockZoned.equals(zoned)
                || !parisGap.toString().equals(
                      "2024-03-31T03:30+02:00[Europe/Paris]")) {
            throw new AssertionError("Time factory mismatch");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ với chế độ tương thích Java 8:

```bash
javac --release 8 TimeFactoriesDemo.java
java TimeFactoriesDemo
```

**Stdout đã đối chiếu trên OpenJDK 24:**

```text
of date: 2024-02-29
of time: 09:45:30
of local: 2024-02-29T09:45:30
parse instant: 2024-02-29T02:45:30Z
of offset: 2024-02-29T09:45:30+07:00
of zoned: 2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]
parse ISO: 2024-02-29 | 2024-02-29T09:45:30
parse offset: 2024-02-29T09:45:30+07:00
parse custom: 2024-02-29
invalid rejected: true
fixed now date: 2024-02-29
fixed now time: 09:45:30
fixed now local: 2024-02-29T09:45:30
fixed now instant: 2024-02-29T02:45:30Z
fixed now zoned: 2024-02-29T09:45:30+07:00[Asia/Ho_Chi_Minh]
Paris gap resolved: 2024-03-31T03:30+02:00[Europe/Paris]
Checks passed.
```

**Diễn giải:**

- `of date` cho ngày nhuận hợp lệ.
- `of local` không có offset; nhưng `of offset` và `of zoned` thể hiện cách gắn thời gian địa phương với `+07:00` / vùng Việt Nam.
- `parse instant` và `offset.toInstant()`/`zoned.toInstant()` bằng nhau vì đều chỉ **một thời điểm**.
- `parse ISO` và `parse custom` tạo đúng kiểu LocalDate/LocalDateTime sau khi kiểm tra input.
- `invalid rejected: true` xác nhận resolver strict không cho phép ngày 29/2/2023.
- Các dòng `fixed now` xuất phát từ `Clock.fixed`, nên **cố định và có thể test**. Không cần truy cập giờ thật.
- Ví dụ `Europe/Paris` rơi vào khoảng DST gap: 02:30 không tồn tại trong ngày chuyển giờ này, nên mặc định `atZone` điều chỉnh tới 03:30 với offset `+02:00`.

**Lưu ý về ví dụ DST:** Quy tắc vùng dựa trên timezone database có trong JDK. Khi triển khai thực, vùng thời gian và lịch sử luật có thể được cập nhật theo bản vá tzdata, nên cần cập nhật runtime đúng cách và xác định tiêu chí nghiệp vụ đối với giờ mơ hồ.

## 7. Đối chiếu ba nhóm factory với cùng một dữ liệu

Cùng một cuộc họp tại Việt Nam lúc `09:45:30` ngày `29/02/2024` có thể được xác định bằng ba con đường:

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

// 1) Thành phần đã biết:
LocalDateTime fromFields = LocalDateTime.of(2024, 2, 29, 9, 45, 30);

// 2) Chuỗi được truyền từ API:
LocalDateTime fromString =
        LocalDateTime.parse("2024-02-29T09:45:30");

// 3) Đồng hồ đã được đặt đúng instant và zone cho demo/test:
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T02:45:30Z"),
        vietnam);
LocalDateTime fromClock = LocalDateTime.now(fixed);
```

Cả ba tạo cùng **LocalDateTime** trong điều kiện đã cố định. Tuy nhiên, trên production với `LocalDateTime.now()` mặc định, không thể mong kết quả luôn là ngày 29/02/2024.

### 7.1. Chọn factory theo dữ liệu, không dùng `now` làm fallback bừa bãi

Ví dụ **không nên**:

```java
// Lỗi parse nhưng tự thay ngày bằng today:
// try { return LocalDate.parse(raw); }
// catch (DateTimeParseException ex) { return LocalDate.now(); }
```

Nếu người dùng nhập sai ngày thanh toán, thay bằng hôm nay có thể làm sai hạch toán. Một ứng dụng tốt thường báo lỗi có cấu trúc, giữ lại input cần sửa hoặc yêu cầu rõ quy tắc fallback.

### 7.2. `of` và `parse` là lựa chọn tốt cho dữ liệu có tính tái lập

Với một tập tham số hoặc một chuỗi hợp lệ, kết quả thường deterministic và không phụ thuộc giờ hiện tại. Tuy nhiên, `ZonedDateTime.of` gắn với **quy tắc vùng thời gian** có thể thay đổi khi timezone database được cập nhật; vì thế khi cần lưu dấu lịch sử giao dịch, ghi lại `Instant` và các metadata timezone/offset theo yêu cầu hệ thống.

## 8. DST: vì sao `ZonedDateTime.of` có thể thay đổi giờ bạn nhập?

Không phải mọi ngày-giờ địa phương đều tương ứng đúng một Instant.

- **Normal:** một local date-time có một offset hợp lệ.
- **Gap:** khi đồng hồ nhảy tới, có một khoảng local time **không tồn tại**; ví dụ Paris 02:30 trong đêm chuyển DST đầu xuân.
- **Overlap:** khi đồng hồ lùi, một khoảng local time xảy ra **hai lần** với hai offset khác nhau.

### 8.1. Gap được giải quyết thế nào?

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime nonexistent = LocalDateTime.of(2024, 3, 31, 2, 30);

ZonedDateTime resolved = nonexistent.atZone(paris);
// 2024-03-31T03:30+02:00[Europe/Paris]
```

`atZone` / `ZonedDateTime.of` với local date-time cố gắng giải quyết một Instant hợp lệ theo quy tắc zone. Trong gap, mặc định local time được đẩy tiếp theo độ dài gap. **Nếu ứng dụng không chấp nhận tự điều chỉnh giờ**, cần validation trước.

### 8.2. Overlap chọn offset nào?

Với một local date-time rơi vào overlap, `ZonedDateTime.of(local, zone)` thường chọn **offset sớm hơn** (thường tương ứng giờ mùa hè). Để có chính sách chính xác trong nghiệp vụ, bạn có thể:

- Lấy `ZoneRules.getValidOffsets(local)` để kiểm tra số offset hợp lệ.
- Xác nhận offset mong muốn với người dùng hoặc nguồn dữ liệu.
- Dùng `ZonedDateTime.ofStrict(local, selectedOffset, zone)` khi cần **không tự giải quyết** giờ không hợp lệ hoặc offset không đúng.
- Dùng `ZonedDateTime.ofInstant(instant, zone)` khi đã có **Instant chính xác**, tránh mơ hồ của local date-time.

Ví dụ chỉ để hiểu:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime ambiguous = LocalDateTime.of(2024, 10, 27, 2, 30);

// Đếm số offset hợp lệ (có thể là 2 trong overlap).
int options = paris.getRules().getValidOffsets(ambiguous).size();

// Khi đã biết offset cụ thể, giải quyết rõ ràng:
ZonedDateTime selected = ZonedDateTime.ofStrict(
        ambiguous, ZoneOffset.ofHours(1), paris);
```

Đây là snippet phù hợp cho Java 8. Một giờ local với hai offset hợp lệ có thể đại diện **hai Instant khác nhau**. Không lưu mỗi `LocalDateTime` rồi mặc định mọi người sẽ hiểu cùng một mốc lịch sử.

## 9. Giữ đúng kiểu khi truyền qua API và lưu trữ

### 9.1. Khi dữ liệu là timestamp của sự kiện

Ví dụ một sự kiện “được ghi lúc nào” nên dùng `Instant` để xác định mốc thực:

```java
Instant createdAt = Instant.now(clock);
```

Trong database/API có thể dùng dạng ISO-8601 chuẩn như `2024-02-29T02:45:30Z`, hoặc epoch với **đơn vị được định nghĩa rõ**. Để hiển thị cho người dùng ở Việt Nam:

```java
ZonedDateTime displayed = createdAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đừng lưu “09:45” như một UTC timestamp nếu chưa có ngày, zone và quy tắc chuyển đổi.

### 9.2. Khi dữ liệu là lịch dân sự

Ngày sinh, ngày nghỉ và “ngày đóng sổ tại chi nhánh” thường dùng `LocalDate`. Đây không phải một Instant; không nên lưu nó như `1970-...Z` bằng cách gắn UTC một cách tùy tiện. Ngày có thể khác nhau giữa hai zone tại cùng một thời điểm.

### 9.3. Khi dữ liệu là lịch hẹn theo vùng

Một lịch hẹn “09:30 sáng thứ Hai tại Paris” cần lưu ít nhất local date-time và region ZoneId, cùng chính sách xử lý DST nếu dùng cho tương lai. Đối với deadline đã được xác định tuyệt đối, `Instant` thường dễ so sánh hơn.

### 9.4. Phân biệt chuyển Zone với thay nhãn Zone

`withZoneSameInstant(newZone)` trên `ZonedDateTime` giữ nguyên **Instant**, thay cách hiển thị giờ địa phương. `withZoneSameLocal(newZone)` cố giữ **local date-time** và có thể đổi Instant. Hai lựa chọn không thể thay thế nhau.

```java
ZonedDateTime hcm = Instant.parse("2024-02-29T02:45:30Z")
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime london = hcm.withZoneSameInstant(
        ZoneId.of("Europe/London"));
// Cùng Instant, nhưng giờ địa phương khác nhau.
```

Phân biệt này rất quan trọng khi chuyển vùng hiển thị cho một timestamp sự kiện.

## 10. Một số bẫy cú pháp và ngữ nghĩa cần tránh

| Bẫy | Vì sao dễ sai? | Cách làm phù hợp |
| --- | --- | --- |
| `LocalDate.of(2023, 2, 29)` | Ngày không hợp lệ, sẽ ném exception | Validate hoặc xử lý `DateTimeException` |
| `LocalTime.of(24,0)` | Giờ không thuộc phạm vi 0..23 | Dùng ngày hôm sau lúc 00:00 |
| `LocalDateTime.parse(text có +07:00)` | LocalDateTime không mang offset; format mặc định không nhận offset phía sau | Dùng `OffsetDateTime.parse` nếu nguồn có offset |
| Coi `LocalDateTime` là UTC | Kiểu không có timezone/offset | Gắn zone đúng theo hợp đồng dữ liệu hoặc dùng `Instant` |
| Gọi `now()` và viết test mong ngày cố định | Phụ thuộc thời điểm chạy và máy | Inject `Clock.fixed` |
| Dùng `ZoneId.systemDefault()` không chủ đích | Mỗi môi trường có thể cấu hình khác | Xác định `ZoneId` nghiệp vụ |
| Dùng `yyyy` với STRICT mà không xét era | Year-of-era khác proleptic-year | Dùng `uuuu` cho ISO date strict phù hợp |
| Dùng `YYYY` tưởng là năm lịch | `YYYY` là week-based year | Dùng `uuuu`/`yyyy` có hiểu rõ |
| Dùng `ofPattern` mặc định rồi nghĩ luôn strict | Default là SMART | Dùng `withResolverStyle(STRICT)` nếu cần |
| Parse tháng dạng chữ mà bỏ locale | Tên tháng và AM/PM phụ thuộc locale | Chỉ định `Locale` cụ thể |
| Lẫn epoch seconds với milliseconds | Sai timestamp theo hệ số 1000 | Dùng đúng `ofEpochSecond`/`ofEpochMilli` |
| Gắn offset +07:00 cho mọi region | Nhiều vùng thay đổi offset theo DST | Lưu `ZoneId` nếu cần quy tắc vùng |
| Giả định local time nào cũng có đúng một Instant | DST gap/overlap | Dùng `ZoneRules` và chính sách xác nhận |
| Dùng `Instant.now()` cho thời gian benchmark | System wall clock có thể bị điều chỉnh | Dùng `System.nanoTime()` khi đo elapsed |
| Dùng lớp `Date`/`Calendar` cho API ngày giờ mới | API khó biểu đạt ý định ngày giờ, dễ sai timezone | Ưu tiên `java.time` cho mã mới |
| Dùng format hiển thị làm dạng lưu hệ thống | Locale có thể làm đổi text | Dùng ISO-8601 có hợp đồng rõ |

**Về API cũ:** `java.util.Date` và `java.util.Calendar` vẫn tồn tại cho tương thích với hệ thống hiện hữu, nhưng **không phải lựa chọn được khuyên dùng khi thiết kế mới** nếu `java.time` đáp ứng bài toán. Đừng cố áp đặt `SimpleDateFormat` mutable vào mã đa luồng khi đã có `DateTimeFormatter` immutable và thread-safe.

## 11. Kiểm thử đúng với `of`, `parse`, `now`

### 11.1. Factory `of`

Kiểm tra:

- Ngày bình thường: `LocalDate.of(2024, 1, 15)`.
- Ngày nhuận: `LocalDate.of(2024, 2, 29)`.
- Ngày không tồn tại: `LocalDate.of(2023, 2, 29)` phải ném `DateTimeException`.
- Giờ biên: `LocalTime.of(0,0)` hợp lệ, `LocalTime.of(23,59,59)` hợp lệ, `LocalTime.of(24,0)` không hợp lệ.
- Với zone DST: kiểm tra gap/overlap theo **quy tắc vùng và chính sách nghiệp vụ**, không chỉ theo phần ngày giờ local.

### 11.2. Factory `parse`

Kiểm tra:

- ISO hợp lệ, ví dụ `2024-02-29`.
- Thiếu số 0 đầu: format có yêu cầu bao nhiêu chữ số?
- Sai thứ tự ngày/tháng hoặc dùng dấu phân cách khác.
- Ngày tháng vượt giới hạn, `null`, chuỗi rỗng, khoảng trắng đầu/cuối nếu dữ liệu cho phép.
- Pattern có chữ năm `uuuu` hay `YYYY`? Có chuyển đổi bất thường gần năm mới?
- Thử nội dung gây `DateTimeParseException` và xác nhận thông báo có ích.

### 11.3. Factory `now`

Tạo một Clock cố định:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-02-29T02:45:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

assert LocalDate.now(clock).equals(LocalDate.of(2024, 2, 29));
assert LocalTime.now(clock).equals(LocalTime.of(9, 45, 30));
```

Trong Java, `assert` chỉ có hiệu lực khi bật `-ea`, nên dự án thường dùng JUnit `assertEquals`. Chạy test dưới cả zone Việt Nam và zone UTC nếu sản phẩm có nhiều thị trường. Không cho test phụ thuộc đồng hồ thật rồi “sleep” vài giây để đoán ngày.

### 11.4. Test mốc qua ngày mới

Một mốc gần nửa đêm UTC có thể thuộc **ngày khác** ở Việt Nam:

```java
Instant moment = Instant.parse("2024-02-29T20:30:00Z");

LocalDate utcDate = moment.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate vnDate = moment.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();

// utcDate = 2024-02-29.
// vnDate = 2024-03-01.
```

Nếu có nhiều chi nhánh, tính toán ngày bán hàng/tổng hợp theo **zone nghiệp vụ** sẽ chính xác hơn việc lấy ngày UTC rồi gán cho mọi nơi.

## 12. Bài tập có đáp án

**Bài 1 — `of`:** Tạo một ngày hợp lệ 31/12/2024 và giờ 23:59 bằng `java.time`.

```java
LocalDate d = LocalDate.of(2024, 12, 31);
LocalTime t = LocalTime.of(23, 59);
LocalDateTime dt = LocalDateTime.of(d, t);
```

**Bài 2 — `parse`:** Chuỗi `"31/12/2024"`, yêu cầu parse chính xác ngày. Dùng gì?

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate d = LocalDate.parse("31/12/2024", strict);
```

**Bài 3 — `now`:** Bạn cần test service hoạt động vào đúng nửa đêm ở Việt Nam mà không phụ thuộc system clock. Dùng gì?

```java
Clock testClock = Clock.fixed(
        Instant.parse("2024-12-31T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate testDate = LocalDate.now(testClock);
// 2025-01-01.
```

**Bài 4 — mốc UTC:** `"2024-02-29T09:45:30+07:00"` là một timestamp có offset. Nên parse sang kiểu nào để chuyển sang Instant?

```java
Instant when = OffsetDateTime
        .parse("2024-02-29T09:45:30+07:00")
        .toInstant();
// 2024-02-29T02:45:30Z.
```

**Bài 5 — mơ hồ:** Vì sao `LocalDateTime.parse("2024-10-27T02:30")` chưa đủ để biết một Instant chính xác tại Paris? Vì vùng này có thể có **DST overlap** với hai offset khác nhau; cần zone, quy tắc xử lý và có thể cả offset được lựa chọn.

**Bài 6 — strict:** Vì sao `"29/02/2023"` phải bị từ chối nếu yêu cầu ngày lịch hợp lệ? Vì năm 2023 không nhuận, không có ngày 29/2. Dùng `ResolverStyle.STRICT` với pattern phù hợp.

**Bài 7 — epoch:** `Instant.ofEpochSecond(1)` có giống `Instant.ofEpochMilli(1000)` không? **Có**, đều cách Unix epoch đúng một giây.

**Bài 8 — locale:** Vì sao `LocalDate.parse("29 Feb 2024", formatter)` cần locale phù hợp? Vì `Feb` là tên tháng dạng chữ, cách viết khác nhau giữa các locale.

## 13. Tài liệu Java hiện hành

- [Oracle Java SE 26 — LocalDate](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html): các factory `of`, `parse` và `now`, giá trị calendar date.
- [Oracle Java SE 26 — LocalTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalTime.html) và [LocalDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): ngày giờ local, không có offset.
- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): UTC timeline, epoch seconds/millis và `now`.
- [Oracle Java SE 26 — OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html) và [ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): offset so với region zone, DST gap/overlap.
- [Oracle Java SE 26 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO formatters, pattern letters, resolver style và locale.
- [Oracle Java SE 26 — Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): `Clock.fixed`, `Clock.systemUTC`, inject Clock để test.
- [Oracle Java SE 8 — Package java.time](https://docs.oracle.com/javase/8/docs/api/java/time/package-summary.html): đối chiếu các API nền tảng có từ Java 8.

**Kết luận:** Dùng `of` khi đã có **trường số hợp lệ**, `parse` khi đầu vào là **văn bản theo định dạng xác định**, và `now` khi cần **thời gian từ đồng hồ**. Chọn đúng kiểu `LocalDate` / `LocalDateTime` / `Instant` / `ZonedDateTime` trước khi gọi factory; dùng `Clock.fixed` cho test và không nhầm LocalDateTime với UTC timestamp.
