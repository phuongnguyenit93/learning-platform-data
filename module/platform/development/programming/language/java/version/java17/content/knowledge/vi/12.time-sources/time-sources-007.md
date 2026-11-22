# Tính Duration và xử lý mốc thời gian ở biên

## 1. Bài toán thời gian: một mốc, một khoảng hay một ngày theo lịch?

Trong Java, nhiều lỗi liên quan đến thời gian xuất hiện vì chương trình dùng cùng một kiểu dữ liệu cho những khái niệm khác nhau:

- **Mốc thời gian (timestamp/instant):** một điểm xác định trên dòng thời gian, ví dụ thời điểm một đơn hàng được tạo.
- **Thời lượng (duration):** khoảng thời gian đã trôi qua giữa hai mốc, ví dụ một request mất 350 mili giây.
- **Ngày theo lịch (calendar date):** ngày 15/11/2026 tại một múi giờ cụ thể.
- **Giờ địa phương:** 09:30 theo đồng hồ của một vùng, có thể cần múi giờ để xác định nó tương ứng với mốc UTC nào.
- **Khoảng thời gian nghiệp vụ:** ví dụ tất cả giao dịch thuộc ngày hôm nay tại Việt Nam, hoặc thời hạn từ 09:00 đến 17:00.

Java 17 có Java Time API trong gói `java.time`, được giới thiệu từ Java 8. Các kiểu thường dùng:

| Kiểu | Diễn đạt | Có chứa múi giờ/vị trí trên timeline? |
|---|---|---|
| `Instant` | Một mốc thời gian | Có ý nghĩa mốc toàn cầu, chuẩn hóa theo UTC |
| `Duration` | Khoảng thời gian theo giây và nano giây | Không |
| `Period` | Khoảng thời gian theo năm, tháng, ngày lịch | Không |
| `LocalDate` | Một ngày lịch | Không |
| `LocalTime` | Một giờ trong ngày | Không |
| `LocalDateTime` | Ngày và giờ địa phương | Không |
| `OffsetDateTime` | Ngày giờ cùng UTC offset | Có offset, không nhất thiết có quy tắc vùng |
| `ZonedDateTime` | Ngày giờ theo vùng múi giờ | Có `ZoneId` và quy tắc múi giờ |
| `Clock` | Nguồn cung cấp thời gian hiện tại | Có cách lấy mốc và zone được cấu hình |

Chủ đề này tập trung vào **tính Duration và xử lý mốc thời gian ở biên**: tính thời gian đã trôi qua, xác định đầu/cuối một khoảng, xử lý ngày theo múi giờ, và tránh lỗi do DST hoặc độ chính xác của timestamp.

Một nguyên tắc quan trọng:

> Dùng `Instant` cho mốc trên timeline, `Duration` cho thời lượng thực đã trôi qua, `Period` và `LocalDate` cho khái niệm lịch, rồi chuyển qua `ZoneId` tại ranh giới nghiệp vụ.

## 2. Instant: biểu diễn một mốc thời gian độc lập với múi giờ hiển thị

### 2.1. Tạo và đọc Instant

`Instant` biểu diễn một điểm trên timeline, thường được dùng để lưu thời điểm tạo bản ghi, nhận sự kiện, gửi request hoặc hoàn tất tác vụ.

~~~java
import java.time.Instant;

public class InstantExample {
    public static void main(String[] args) {
        Instant now = Instant.now();
        Instant event = Instant.parse("2026-11-15T14:00:00Z");

        System.out.println("Now: " + now);
        System.out.println("Event: " + event);
        System.out.println("Epoch seconds: " + event.getEpochSecond());
        System.out.println("Nano adjustment: " + event.getNano());
    }
}
~~~

Chuỗi ISO-8601 `2026-11-15T14:00:00Z` có hậu tố `Z`, nghĩa là UTC. Một `Instant` không mang tên múi giờ như `Asia/Ho_Chi_Minh`; nó biểu diễn mốc đã xác định.

`Instant` có độ phân giải đến nano giây trong API, nhưng độ chính xác thực tế của clock, hệ điều hành, JVM và nguồn thời gian có thể thấp hơn. Không giả định rằng gọi `Instant.now()` liên tiếp luôn tạo ra hai giá trị cách nhau đúng một nano giây.

### 2.2. So sánh và dịch chuyển mốc

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Instant end = start.plusSeconds(90);

System.out.println(start.isBefore(end)); // true
System.out.println(end.isAfter(start));  // true
System.out.println(start.equals(end));   // false
~~~

Các phép toán thường dùng:

- `plus(Duration)`, `minus(Duration)`: dịch chuyển một mốc theo thời lượng.
- `isBefore`, `isAfter`, `equals`: so sánh hai mốc.
- `getEpochSecond()`, `getNano()`: đọc thành phần thời gian.
- `toEpochMilli()`: chuyển sang epoch milliseconds, có thể mất phần nano và có thể ném `ArithmeticException` nếu ngoài phạm vi `long`.

`Instant` không có khái niệm “đầu ngày theo giờ Việt Nam” cho đến khi ta kết hợp nó với một `ZoneId`.

## 3. Duration: tính khoảng thời gian đã trôi qua

### 3.1. Tạo Duration bằng `between`

`Duration` biểu diễn khoảng thời gian theo giây và phần nano giây. Cách phổ biến nhất để tính là:

~~~java
import java.time.Duration;
import java.time.Instant;

Instant startedAt = Instant.parse("2026-11-15T10:00:00Z");
Instant finishedAt = Instant.parse("2026-11-15T10:02:35.500Z");

Duration elapsed = Duration.between(startedAt, finishedAt);

System.out.println(elapsed);            // PT2M35.5S
System.out.println(elapsed.toSeconds()); // 155
System.out.println(elapsed.toMillis());  // 155500
~~~

`Duration.between(start, end)` tính khoảng thời gian từ `start` đến `end`. Nếu `end` sớm hơn `start`, Duration trả về là **âm**.

~~~java
Duration positive = Duration.between(
        Instant.parse("2026-11-15T10:00:00Z"),
        Instant.parse("2026-11-15T10:00:05Z")
);

Duration negative = Duration.between(
        Instant.parse("2026-11-15T10:00:05Z"),
        Instant.parse("2026-11-15T10:00:00Z")
);

System.out.println(positive); // PT5S
System.out.println(negative); // PT-5S
System.out.println(negative.isNegative()); // true
~~~

Một Duration âm không phải lỗi của API. Nó có thể biểu diễn một deadline đã qua, hai mốc được truyền ngược thứ tự hoặc một độ lệch có dấu. Nếu nghiệp vụ yêu cầu thời lượng không âm, hãy kiểm tra thứ tự mốc thay vì âm thầm lấy trị tuyệt đối.

### 3.2. Tạo Duration từ đơn vị

~~~java
Duration zero = Duration.ZERO;
Duration oneSecond = Duration.ofSeconds(1);
Duration halfSecond = Duration.ofMillis(500);
Duration tenMillis = Duration.ofNanos(10_000_000);
Duration oneHour = Duration.ofHours(1);
Duration oneDay = Duration.ofDays(1);
~~~

Các factory phổ biến:

| Factory | Thời lượng |
|---|---|
| `Duration.ofNanos(n)` | `n` nano giây |
| `Duration.ofMillis(n)` | `n` mili giây |
| `Duration.ofSeconds(n)` | `n` giây |
| `Duration.ofMinutes(n)` | `n` phút |
| `Duration.ofHours(n)` | `n` giờ |
| `Duration.ofDays(n)` | `n × 24` giờ |
| `Duration.parse(text)` | Parse chuỗi theo định dạng Duration ISO-8601 |

Điểm quan trọng: `Duration.ofDays(1)` là **chính xác 86.400 giây**, không phải “một ngày trên lịch địa phương”. Một ngày lịch có thể dài 23 hoặc 25 giờ khi đồng hồ chuyển đổi DST.

### 3.3. Parse và định dạng Duration

~~~java
Duration timeout = Duration.parse("PT30S");
Duration retryDelay = Duration.parse("PT1M15S");
Duration workTime = Duration.parse("PT2H30M");

System.out.println(timeout);    // PT30S
System.out.println(retryDelay); // PT1M15S
System.out.println(workTime);   // PT2H30M
~~~

Duration dùng dạng ISO-8601 với tiền tố `P`, phần thời gian sau `T`; ví dụ `PT1H` là một giờ, `P2D` là hai ngày (hai khoảng 24 giờ). Chuỗi không đúng định dạng sẽ gây `DateTimeParseException`.

### 3.4. Các phương thức đọc thành phần và giới hạn chuyển đổi

~~~java
Duration duration = Duration.ofHours(27).plusMinutes(12).plusSeconds(5);

System.out.println(duration.toDays());       // 1: số ngày 24 giờ đầy đủ
System.out.println(duration.toHours());      // 27: tổng số giờ
System.out.println(duration.toMinutes());    // 1632: tổng số phút
System.out.println(duration.toSeconds());    // 97925: tổng số giây
System.out.println(duration.toMillis());     // 97925000
System.out.println(duration.toHoursPart());  // 3: phần giờ còn lại sau ngày
System.out.println(duration.toMinutesPart());// 12
System.out.println(duration.toSecondsPart());// 5
~~~

Phân biệt:

- `toHours()` là tổng số giờ đầy đủ của toàn duration.
- `toHoursPart()` chỉ là phần giờ còn lại sau khi tách ngày.
- `toDays()` đếm các khối 24 giờ đầy đủ, không đếm ngày lịch.

Các phép chuyển sang đơn vị nhỏ hơn như `toMillis()` hoặc `toNanos()` có thể làm mất phần nhỏ hơn đơn vị đích (ví dụ nano khi chuyển sang milli) và có thể ném `ArithmeticException` nếu kết quả không biểu diễn được bằng `long`.

Không nên giả định Duration cực lớn luôn chuyển được sang nano giây:

~~~java
Duration huge = Duration.ofDays(1_000_000_000L);
// long nanos = huge.toNanos(); // có thể ném ArithmeticException do overflow
~~~

Khi API nhận duration từ cấu hình, cần giới hạn miền hợp lệ trước khi chuyển sang đơn vị mà thư viện timeout hoặc scheduler yêu cầu.

## 4. Duration khác Period như thế nào?

### 4.1. Duration là thời lượng, Period là khoảng lịch

Hai kiểu dễ bị nhầm:

- `Duration`: đo khoảng thời gian theo giây và nano giây.
- `Period`: đo khoảng lịch theo năm, tháng và ngày.

~~~java
import java.time.Duration;
import java.time.Period;

Duration twoDays = Duration.ofDays(2);
Period calendarTwoDays = Period.ofDays(2);
Period oneMonth = Period.ofMonths(1);
Period oneYear = Period.ofYears(1);
~~~

Ví dụ:

| Yêu cầu | Kiểu phù hợp |
|---|---|
| Request chạy trong 500 ms | `Duration` |
| Cache hết hạn sau 15 phút thực tế | `Duration` |
| Một ngày sau theo lịch địa phương | `Period.ofDays(1)` kết hợp ngày/múi giờ |
| Ngày kỷ niệm năm sau | `Period.ofYears(1)` hoặc quy tắc ngày lịch |
| Hạn thanh toán sau 30 ngày lịch | `Period.ofDays(30)` kết hợp ngày nghiệp vụ |
| Tác vụ cần chạy sau đúng 24 giờ | `Duration.ofHours(24)` |

### 4.2. Một ngày lịch không phải lúc nào cũng là 24 giờ

Ở những vùng có DST, đồng hồ địa phương có thể nhảy tiến hoặc lùi. Khi chuyển sang giờ mùa hè, một ngày có thể chỉ có 23 giờ thực; khi trở lại giờ chuẩn, một ngày có thể có 25 giờ thực.

Ví dụ dùng một vùng có DST:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate date = LocalDate.of(2026, 3, 29);

ZonedDateTime start = date.atStartOfDay(zone);
ZonedDateTime nextStart = date.plusDays(1).atStartOfDay(zone);

Duration elapsed = Duration.between(start, nextStart);

System.out.println(start);
System.out.println(nextStart);
System.out.println(elapsed.toHours()); // ngày chuyển sang DST có thể chỉ 23 giờ
~~~

Kết quả chính xác phụ thuộc bộ dữ liệu quy tắc múi giờ của JDK tại thời điểm chạy, nhưng với quy tắc DST của Paris vào ngày chuyển sang giờ mùa hè, khoảng giữa hai đầu ngày là 23 giờ.

Nếu thay bằng:

~~~java
ZonedDateTime nextBy24Hours = start.plus(Duration.ofHours(24));
~~~

thì đây là mốc sau **24 giờ thực**, có thể không trùng với đầu ngày lịch kế tiếp.

### 4.3. Duration.between trên LocalDateTime có giới hạn ngữ nghĩa

`LocalDateTime` không chứa zone hoặc offset. Do đó:

~~~java
LocalDateTime localStart =
        LocalDateTime.of(2026, 3, 28, 12, 0);
LocalDateTime localEnd =
        LocalDateTime.of(2026, 3, 29, 12, 0);

Duration wallClockDifference =
        Duration.between(localStart, localEnd);
~~~

Kết quả là 24 giờ trên **trục ngày giờ địa phương không gắn múi giờ**. Nó không thể biết giữa hai mốc ấy ở một vùng cụ thể có DST hay không.

Nếu muốn tính thời lượng thực giữa hai thời điểm trong một vùng:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime zonedStart = localStart.atZone(zone);
ZonedDateTime zonedEnd = localEnd.atZone(zone);

Duration actualElapsed = Duration.between(zonedStart, zonedEnd);
~~~

Với hai `ZonedDateTime`, phép tính Duration phản ánh khoảng cách giữa hai mốc trên timeline. Đây là khác biệt cốt lõi khi tính SLA, thời gian chạy hoặc thời lượng thực.

### 4.4. Không dùng Duration cho tháng/năm lịch

`Duration.ofDays(30)` không có nghĩa “một tháng”. Tháng có thể có 28, 29, 30 hoặc 31 ngày. Năm có thể có 365 hoặc 366 ngày.

Nếu nghiệp vụ nói “gia hạn một tháng kể từ ngày đăng ký”, thường phải thao tác trên ngày/mốc có múi giờ bằng `Period.ofMonths(1)`, rồi xác định quy tắc cho ngày cuối tháng:

~~~java
import java.time.LocalDate;
import java.time.Period;

LocalDate registered = LocalDate.of(2026, 1, 31);
LocalDate nextMonth = registered.plus(Period.ofMonths(1));

System.out.println(nextMonth); // 2026-02-28
~~~

Java điều chỉnh ngày không tồn tại về ngày cuối cùng hợp lệ của tháng đích trong phép cộng này. Quy tắc này thường hữu ích, nhưng vẫn phải xác nhận có đúng chính sách gia hạn của sản phẩm hay không.

## 5. Xử lý biên thời gian: dùng khoảng nửa mở [start, end)

### 5.1. Khoảng nửa mở là gì?

Một khoảng nửa mở có:

- Đầu khoảng **được bao gồm** (inclusive).
- Cuối khoảng **không được bao gồm** (exclusive).

Ký hiệu:

\[
[start, end)
\]

Một mốc `t` thuộc khoảng khi:

\[
start \leq t < end
\]

Trong Java:

~~~java
static boolean contains(
        Instant startInclusive,
        Instant endExclusive,
        Instant value
) {
    return !value.isBefore(startInclusive)
            && value.isBefore(endExclusive);
}
~~~

Ví dụ:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Instant end = Instant.parse("2026-11-15T11:00:00Z");

System.out.println(contains(start, end, start)); // true
System.out.println(contains(start, end, end));   // false
~~~

### 5.2. Vì sao không nên dùng cả hai đầu inclusive?

Giả sử có hai khoảng liền nhau:

~~~text
Khoảng A: [10:00, 11:00)
Khoảng B: [11:00, 12:00)
                         ^
                         11:00 thuộc B, không thuộc A
~~~

Không có khoảng trống và cũng không có mốc 11:00 bị tính hai lần. Nếu cả hai đầu đều inclusive, một sự kiện đúng 11:00 có thể thuộc cả A và B. Nếu cả hai đầu đều exclusive, mốc biên có thể không thuộc khoảng nào.

Khoảng nửa mở giúp:

- Ghép các khoảng liên tiếp.
- Tránh đếm trùng sự kiện đúng thời điểm chuyển ngày/chuyển ca.
- Truy vấn database dễ biểu đạt.
- Không cần giả định độ chính xác timestamp là mili giây hay nano giây.

### 5.3. Kiểm tra khoảng hợp lệ

Một range có thể được định nghĩa bằng record:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

record InstantRange(Instant startInclusive, Instant endExclusive) {
    InstantRange {
        Objects.requireNonNull(startInclusive, "startInclusive");
        Objects.requireNonNull(endExclusive, "endExclusive");

        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                    "start phải trước end"
            );
        }
    }

    boolean contains(Instant value) {
        return value != null
                && !value.isBefore(startInclusive)
                && value.isBefore(endExclusive);
    }

    Duration duration() {
        return Duration.between(startInclusive, endExclusive);
    }

    boolean overlaps(InstantRange other) {
        Objects.requireNonNull(other, "other");
        return startInclusive.isBefore(other.endExclusive)
                && other.startInclusive.isBefore(endExclusive);
    }
}
~~~

Điều kiện hai khoảng nửa mở chồng lấn:

\[
A_{start} < B_{end} \quad \text{và} \quad B_{start} < A_{end}
\]

Nếu A kết thúc đúng lúc B bắt đầu, hai khoảng **không overlap**. Đây thường là điều mong muốn cho lịch làm việc hoặc các bucket thời gian liền nhau.

## 6. Xác định đầu và cuối ngày theo múi giờ

### 6.1. Không dùng 00:00 đến 23:59:59.999

Một cách làm dễ gây lỗi:

~~~java
// Không nên dùng cách giả định precision này:
LocalDateTime start = date.atStartOfDay();
LocalDateTime end = date.atTime(23, 59, 59, 999_000_000);
~~~

Giải pháp này giả định độ chính xác đến mili giây. Nhưng timestamp có thể chứa nano giây, database có thể lưu micro giây hoặc mili giây, và các hệ thống khác có precision khác nhau. Một sự kiện ở `23:59:59.999500` có thể bị bỏ sót nếu giới hạn cuối là `23:59:59.999000`.

Hãy dùng đầu ngày kế tiếp làm mốc cuối **exclusive**.

### 6.2. Khoảng một ngày địa phương

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

static InstantRange rangeOfDate(LocalDate date, ZoneId zone) {
    ZonedDateTime start = date.atStartOfDay(zone);
    ZonedDateTime end = date.plusDays(1).atStartOfDay(zone);

    return new InstantRange(
            start.toInstant(),
            end.toInstant()
    );
}
~~~

Ví dụ với ngày tại Việt Nam:

~~~java
LocalDate date = LocalDate.of(2026, 11, 15);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

InstantRange range = rangeOfDate(date, vietnam);

System.out.println(range.startInclusive());
System.out.println(range.endExclusive());
System.out.println(range.duration());
~~~

Ở vùng không chuyển DST như `Asia/Ho_Chi_Minh`, ngày địa phương thông thường dài 24 giờ. Với vùng có DST, `Duration` của range có thể là 23 hoặc 25 giờ. Thuật toán không cần hardcode các trường hợp đó vì `atStartOfDay(zone)` và dữ liệu `ZoneId` xác định các biên theo quy tắc vùng.

### 6.3. Khoảng nhiều ngày với ngày cuối inclusive

Giao diện người dùng thường nhập “từ ngày A đến ngày B”, với ý nghĩa cả A và B đều được chọn. Khi chuyển sang khoảng timestamp nửa mở:

~~~java
static InstantRange rangeOfInclusiveDates(
        LocalDate fromDate,
        LocalDate toDate,
        ZoneId zone
) {
    if (toDate.isBefore(fromDate)) {
        throw new IllegalArgumentException("Ngày kết thúc trước ngày bắt đầu");
    }

    Instant start = fromDate.atStartOfDay(zone).toInstant();
    Instant endExclusive = toDate.plusDays(1)
            .atStartOfDay(zone)
            .toInstant();

    return new InstantRange(start, endExclusive);
}
~~~

Ví dụ:

~~~java
InstantRange november = rangeOfInclusiveDates(
        LocalDate.of(2026, 11, 1),
        LocalDate.of(2026, 11, 30),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Range này bao gồm toàn bộ ngày 1 đến ngày 30 theo lịch của vùng đã chọn. Không cần tạo “23:59:59.999999999” ở ngày cuối.

Trong ứng dụng cần xử lý ngày cực đại của `LocalDate`, phép `toDate.plusDays(1)` có thể tràn phạm vi và ném `DateTimeException`. Nếu domain có thể nhận ngày biên tối đa, hãy xác định chính sách giới hạn rõ ràng.

### 6.4. Vì sao phải truyền ZoneId từ nghiệp vụ?

“Hôm nay” không phải khái niệm toàn cầu. Cùng một Instant có thể là:

- 15/11 theo giờ Việt Nam.
- 14/11 theo một vùng ở phía tây.
- Một ngày khác tùy vị trí và thời điểm.

Nếu báo cáo doanh thu theo ngày kinh doanh Việt Nam, hãy dùng `Asia/Ho_Chi_Minh`; nếu báo cáo theo vùng của khách hàng, dùng zone được xác định bởi hồ sơ hoặc chính sách sản phẩm.

Không nên dùng `ZoneId.systemDefault()` cho mọi nghiệp vụ chỉ vì nó tiện. Server có thể chạy trong UTC, container có thể cấu hình zone khác, và một request có thể thuộc vùng khác với máy chủ.

## 7. DST, giờ bị thiếu và giờ bị lặp

### 7.1. DST có thể làm local time không ánh xạ một-một tới Instant

Ở vùng có daylight saving time:

- Khi đồng hồ nhảy tiến, một đoạn giờ địa phương có thể **không tồn tại**.
- Khi đồng hồ nhảy lùi, một đoạn giờ địa phương có thể **xuất hiện hai lần**.

Vì vậy, `LocalDateTime` không luôn xác định được một mốc duy nhất. Cần một `ZoneId` và có thể cần chính sách xử lý gap/overlap.

### 7.2. Dùng `atZone` có quy tắc tự giải quyết

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);

ZonedDateTime zoned = local.atZone(zone);
System.out.println(zoned);
~~~

Khi local time rơi vào DST overlap (giờ xuất hiện hai lần), `atZone` mặc định chọn offset sớm hơn theo quy tắc của API. Có thể yêu cầu offset muộn hơn:

~~~java
ZonedDateTime laterOccurrence = zoned.withLaterOffsetAtOverlap();
~~~

Khi local time rơi vào DST gap (giờ không tồn tại), `atZone` điều chỉnh về thời điểm hợp lệ sau khoảng gap. Đây là hành vi thuận tiện nhưng không phải lúc nào cũng đúng nghiệp vụ.

### 7.3. Kiểm tra rõ gap/overlap bằng ZoneRules

Nếu ứng dụng cần yêu cầu người dùng chọn một trong hai thời điểm trùng nhau, hoặc từ chối giờ không tồn tại, có thể kiểm tra:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneRules rules = zone.getRules();

List<java.time.ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    System.out.println("Local time nằm trong DST gap, không tồn tại");
} else if (offsets.size() == 1) {
    System.out.println("Một mốc hợp lệ: " + offsets.get(0));
} else {
    System.out.println("Local time bị lặp, cần chọn offset: " + offsets);
}
~~~

Quy tắc:

- Không có offset hợp lệ: local time nằm trong gap.
- Có một offset: local time ánh xạ tới một instant.
- Có hai offset: local time nằm trong overlap, có hai instant có thể chọn.

Trong hệ thống đặt lịch, lịch bay, tài chính hoặc deadline theo giờ địa phương, cần xác định rõ chính sách gap/overlap thay vì để mặc định của `atZone` quyết định thay người dùng.

## 8. Tính Duration từ các kiểu thời gian khác nhau

### 8.1. Instant đến Instant

Đây là trường hợp rõ ràng nhất để đo thời lượng thực:

~~~java
Duration elapsed = Duration.between(
        Instant.parse("2026-11-15T09:00:00Z"),
        Instant.parse("2026-11-15T09:45:30Z")
);
~~~

Hai mốc đã nằm trên cùng timeline, không cần zone để tính khoảng cách.

### 8.2. ZonedDateTime đến ZonedDateTime

~~~java
ZonedDateTime start = ZonedDateTime.parse(
        "2026-03-28T12:00:00+01:00[Europe/Paris]"
);
ZonedDateTime end = ZonedDateTime.parse(
        "2026-03-29T12:00:00+02:00[Europe/Paris]"
);

Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toHours()); // 23
~~~

Hai local time cách nhau một ngày trên lịch, nhưng offset thay đổi từ +01:00 sang +02:00, nên thời lượng thực là 23 giờ.

### 8.3. OffsetDateTime đến OffsetDateTime

`OffsetDateTime` có offset UTC cụ thể, nên có thể xác định instant:

~~~java
OffsetDateTime a = OffsetDateTime.parse("2026-11-15T09:00:00+07:00");
OffsetDateTime b = OffsetDateTime.parse("2026-11-15T04:00:00Z");

Duration difference = Duration.between(a, b);
System.out.println(difference); // PT0S
~~~

Hai cách biểu diễn khác offset nhưng cùng một instant. Nếu nghiệp vụ cần vùng múi giờ với quy tắc lịch sử/DST, `OffsetDateTime` không thay thế hoàn toàn `ZonedDateTime`.

### 8.4. LocalDateTime đến LocalDateTime

~~~java
LocalDateTime a = LocalDateTime.of(2026, 11, 15, 9, 0);
LocalDateTime b = LocalDateTime.of(2026, 11, 15, 10, 30);

Duration difference = Duration.between(a, b);
System.out.println(difference); // PT1H30M
~~~

Kết quả là độ chênh giữa hai giá trị local trên trục ngày giờ không có zone. Nếu đây là thời gian thực đã trôi qua của một quy trình tại vùng có DST, hãy gắn zone/offset trước.

### 8.5. LocalDate không thể dùng trực tiếp với Duration

~~~java
LocalDate first = LocalDate.of(2026, 11, 1);
LocalDate second = LocalDate.of(2026, 11, 15);

// Duration.between(first, second) không phù hợp:
// LocalDate không có đơn vị giây để tạo Duration.

long days = java.time.temporal.ChronoUnit.DAYS.between(first, second);
Period period = Period.between(first, second);
~~~

Với hai ngày lịch, dùng `Period` hoặc `ChronoUnit.DAYS.between`. Không ép `LocalDate` thành `Duration` nếu chưa xác định múi giờ và đầu ngày.

## 9. Clock: kiểm soát nguồn thời gian và viết code có thể kiểm thử

### 9.1. Vì sao không nên gọi `Instant.now()` rải rác?

Code nghiệp vụ thường có nhu cầu “thời điểm hiện tại”:

~~~java
Instant createdAt = Instant.now();
Instant expiresAt = Instant.now().plus(Duration.ofHours(1));
~~~

Hai lời gọi có thể trả hai mốc hơi khác nhau. Khó hơn nữa, test phụ thuộc thời gian thật có thể không tái lập. Java cung cấp `Clock` để trừu tượng hóa nguồn thời gian:

~~~java
Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
~~~

Các factory thường dùng:

| Factory | Ý nghĩa |
|---|---|
| `Clock.systemUTC()` | Clock hệ thống với zone UTC |
| `Clock.system(zone)` | Clock hệ thống gắn zone được chỉ định |
| `Clock.fixed(instant, zone)` | Clock luôn trả cùng một instant, rất hữu ích trong test |
| `Clock.offset(baseClock, duration)` | Clock có thời gian dịch so với clock gốc |
| `Clock.tick(baseClock, duration)` | Clock làm tròn/tick theo khoảng được chọn |

### 9.2. Inject Clock vào service

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

class ExpirationService {
    private final Clock clock;

    ExpirationService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    Instant createExpiration() {
        return Instant.now(clock).plus(Duration.ofHours(1));
    }
}
~~~

Production:

~~~java
ExpirationService service =
        new ExpirationService(Clock.systemUTC());
~~~

Test:

~~~java
Instant fixedNow = Instant.parse("2026-11-15T10:00:00Z");
Clock fixedClock = Clock.fixed(fixedNow, ZoneOffset.UTC);

ExpirationService service = new ExpirationService(fixedClock);

System.out.println(service.createExpiration());
// 2026-11-15T11:00:00Z
~~~

Test không phải chờ đồng hồ thật và không phụ thuộc thời điểm chạy. Có thể tạo `Clock.offset(fixedClock, Duration.ofMinutes(10))` để mô phỏng thời gian tiến/lùi theo kịch bản.

### 9.3. Clock là wall-clock, không phải monotonic timer

`Clock.systemUTC()` lấy thời gian lịch từ hệ thống. Đồng hồ hệ điều hành có thể được đồng bộ hoặc điều chỉnh, nên hai lần đọc có thể không phản ánh chính xác thời gian trôi qua theo đơn điệu.

Điều này dẫn đến hai nhu cầu khác nhau:

- **Ghi nhận mốc thời gian:** dùng `Instant`/`Clock`.
- **Đo thời gian thực thi, timeout, latency:** dùng `System.nanoTime()` để đo elapsed time.

Không dùng `Instant.now()` trừ nhau làm timer chính xác cho benchmark hoặc timeout ngắn nếu yêu cầu cần đồng hồ monotonic.

## 10. Đo thời gian chạy bằng System.nanoTime()

### 10.1. nanoTime đo khoảng thời gian, không phải timestamp

`System.nanoTime()` trả giá trị từ nguồn thời gian đơn điệu có độ phân giải nano giây để đo thời lượng. Giá trị gốc có thể âm, tùy ý và không có ý nghĩa là epoch timestamp.

~~~java
long start = System.nanoTime();

doWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println("Elapsed: " + elapsed.toMillis() + " ms");
~~~

Điểm cần nhớ:

- Chỉ quan tâm **hiệu giữa hai lần gọi**.
- Không chuyển `nanoTime()` thành ngày giờ hoặc lưu như timestamp.
- Phép trừ `end - start` là cách dùng đúng để tính elapsed time, kể cả khi bộ đếm wrap quanh, miễn thời lượng đo nhỏ hơn khoảng biểu diễn có dấu thích hợp.
- Độ phân giải API không đồng nghĩa độ chính xác vật lý của phép đo.

### 10.2. Tạo deadline timeout

Một cách kiểm tra timeout:

~~~java
import java.time.Duration;

static void runWithBudget(Duration budget) {
    if (budget == null || budget.isNegative() || budget.isZero()) {
        throw new IllegalArgumentException("Budget phải dương");
    }

    final long budgetNanos;
    try {
        budgetNanos = budget.toNanos();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Budget vượt phạm vi đo nanoTime",
                ex
        );
    }

    long started = System.nanoTime();

    while (true) {
        doOneUnitOfWork();

        long elapsed = System.nanoTime() - started;
        if (elapsed >= budgetNanos) {
            throw new RuntimeException("Hết thời gian xử lý");
        }
    }
}
~~~

Đây là minh họa cho phép đo budget, không phải framework timeout hoàn chỉnh. Trong ứng dụng thực tế, cần thêm cơ chế dừng công việc, interrupt, cleanup và phân biệt timeout với lỗi nghiệp vụ.

Nếu Duration quá lớn, `toNanos()` có thể overflow; phải giới hạn hoặc chuyển sang cách so sánh khác. Không so sánh trực tiếp hai giá trị tuyệt đối của `nanoTime()` theo kiểu `System.nanoTime() >= deadline` vì bộ đếm có thể wrap và origin không có ý nghĩa.

### 10.3. Vì sao timeout nên dựa trên monotonic clock?

Giả sử ứng dụng tính:

~~~java
Instant deadline = Instant.now().plusSeconds(10);
~~~

Rồi liên tục so sánh `Instant.now()` với deadline. Nếu đồng hồ hệ thống bị điều chỉnh lùi, timeout có thể kéo dài hơn dự kiến; nếu bị điều chỉnh tiến, timeout có thể hết sớm.

Đối với timeout nội bộ trong một tiến trình, đo elapsed bằng `System.nanoTime()` ổn định hơn trước thay đổi wall-clock. Đối với deadline được gửi giữa các hệ thống hoặc lưu vào database, dùng mốc `Instant` là cần thiết, sau đó quy đổi sang budget monotonic khi bắt đầu chờ.

## 11. Xử lý biên thời gian trong database

### 11.1. Truy vấn theo ngày: dùng start inclusive và next-day exclusive

Giả sử bảng `orders` có cột timestamp đại diện thời điểm tạo đơn. Người dùng chọn ngày 15/11/2026 theo múi giờ Việt Nam.

Tính biên:

~~~java
LocalDate date = LocalDate.of(2026, 11, 15);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

SQL:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE created_at >= :fromInclusive
  AND created_at <  :untilExclusive
ORDER BY created_at;
~~~

Truy vấn này bao gồm mọi timestamp trong ngày địa phương đã chọn mà không phải đoán precision cuối ngày.

### 11.2. Vì sao không dùng BETWEEN với hai đầu inclusive?

SQL `BETWEEN a AND b` thường tương đương `>= a AND <= b`. Nếu `:to` được đặt là đầu ngày tiếp theo, record đúng lúc 00:00 của ngày tiếp theo sẽ bị tính vào ngày trước.

~~~sql
-- Dễ sai khi :to là đầu ngày kế tiếp:
WHERE created_at BETWEEN :fromInclusive AND :nextDayStart
~~~

Nên viết:

~~~sql
WHERE created_at >= :fromInclusive
  AND created_at < :nextDayStart
~~~

Với hai khoảng liền nhau, mốc đúng đầu ngày mới chỉ thuộc ngày mới, không bị tính hai lần.

### 11.3. Độ chính xác timestamp của database

Java `Instant` có độ phân giải nano giây, nhưng database/driver có thể lưu với độ chính xác khác nhau, ví dụ mili giây hoặc micro giây. Nếu code dựng end boundary là `23:59:59.999999999`, dữ liệu được làm tròn hoặc truncate ở database có thể tạo ra các tình huống khó đoán.

Khoảng nửa mở không cần biết timestamp được lưu đến mili, micro hay nano giây. Nó chỉ cần hai mốc được tính nhất quán.

### 11.4. Chọn kiểu lưu trữ theo ý nghĩa dữ liệu

- Sự kiện trên timeline: thường lưu UTC instant hoặc kiểu timestamp có quy ước timezone rõ ràng.
- Ngày sinh, ngày kế toán, ngày nghỉ: lưu `LocalDate` hoặc kiểu SQL DATE, không gán UTC nếu không có ý nghĩa.
- Giờ mở cửa hằng ngày: có thể lưu `LocalTime` kèm `ZoneId` của cơ sở.
- Lịch hẹn theo vùng: lưu instant đã xác định và/hoặc local date-time + zone/offset theo nhu cầu tái hiện lịch.

Không lưu `LocalDateTime` rồi giả định nó là UTC nếu schema không quy định như vậy. Khi đọc dữ liệu cũ, cần xác định timezone lịch sử trước khi chuyển sang `Instant`.

## 12. Mốc thời gian, zone và dữ liệu người dùng

### 12.1. Parse một timestamp có offset

~~~java
OffsetDateTime input =
        OffsetDateTime.parse("2026-11-15T21:00:00+07:00");

Instant instant = input.toInstant();
~~~

Offset `+07:00` xác định mốc tương ứng trên timeline. Nếu chuỗi đầu vào không có offset:

~~~text
2026-11-15T21:00:00
~~~

thì đó chỉ là `LocalDateTime`, chưa xác định được instant. Cần biết zone hoặc offset theo hợp đồng API.

### 12.2. ZoneId và ZoneOffset không giống nhau

- `ZoneOffset` là độ lệch cố định so với UTC, ví dụ `+07:00`.
- `ZoneId` có thể là tên vùng như `Asia/Ho_Chi_Minh`, với quy tắc lịch sử và DST nếu có.

Vùng địa lý có thể thay đổi quy tắc theo quyết định pháp lý. Dùng `ZoneId` khi nghiệp vụ nói đến giờ địa phương của một vùng, và dùng `ZoneOffset` khi hợp đồng chỉ cung cấp offset cụ thể.

### 12.3. Hiển thị một Instant theo vùng

~~~java
Instant instant = Instant.parse("2026-11-15T14:00:00Z");

ZonedDateTime vietnamTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
ZonedDateTime parisTime = instant.atZone(
        ZoneId.of("Europe/Paris")
);

System.out.println(vietnamTime);
System.out.println(parisTime);
~~~

Hai kết quả biểu diễn **cùng một instant**, nhưng giờ lịch khác nhau. Đây là lý do nên lưu mốc thời gian toàn cầu và chỉ chuyển sang zone tại lớp hiển thị/nghiệp vụ phù hợp.

## 13. Các bài toán biên thường gặp

### 13.1. Kiểm tra một deadline đã qua chưa

~~~java
static boolean isExpired(Instant expiresAt, Clock clock) {
    return !Instant.now(clock).isBefore(expiresAt);
}
~~~

Trong ví dụ, tại đúng `expiresAt`, kết quả đã expired. Nếu nghiệp vụ định nghĩa thời điểm cuối còn hợp lệ, điều kiện có thể khác; cần viết rõ inclusive/exclusive.

### 13.2. Tính thời gian còn lại

~~~java
static Duration remaining(Instant deadline, Clock clock) {
    return Duration.between(Instant.now(clock), deadline);
}
~~~

Duration âm nghĩa là deadline đã qua. Không nên tự động clamp về zero nếu caller cần phân biệt “đã trễ” với “còn 0 giây”.

### 13.3. Kiểm tra hai khoảng lịch có chồng lấn

Với hai khoảng nửa mở `[aStart, aEnd)` và `[bStart, bEnd)`:

~~~java
static boolean overlaps(
        Instant aStart,
        Instant aEnd,
        Instant bStart,
        Instant bEnd
) {
    return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
}
~~~

Trước khi gọi, phải bảo đảm từng range hợp lệ (`start < end`). Nếu một khoảng rỗng hoặc ngược thứ tự, hãy quyết định có từ chối hay coi là không overlap.

### 13.4. Tính thời gian từ lúc bắt đầu tới hiện tại

~~~java
Instant startedAt = Instant.now(clock);
// ... thực hiện công việc ...
Instant finishedAt = Instant.now(clock);

Duration elapsed = Duration.between(startedAt, finishedAt);
~~~

Cách này phù hợp khi hai mốc cần lưu/hiển thị. Nếu mục tiêu là đo latency nội bộ với clock monotonic, ưu tiên `System.nanoTime()`.

### 13.5. Cộng một ngày lịch vào một lịch hẹn

~~~java
ZonedDateTime appointment =
        ZonedDateTime.of(
                2026, 3, 28, 9, 0, 0, 0,
                ZoneId.of("Europe/Paris")
        );

ZonedDateTime tomorrowSameLocalTime =
        appointment.plus(Period.ofDays(1));

ZonedDateTime after24Hours =
        appointment.plus(Duration.ofHours(24));
~~~

`tomorrowSameLocalTime` hướng đến cùng giờ địa phương ngày kế tiếp, áp dụng quy tắc zone. `after24Hours` là sau đúng 24 giờ trên timeline. Hai kết quả có thể khác nhau khi đi qua DST.

## 14. Ví dụ hoàn chỉnh: báo cáo theo ngày địa phương và đo thời lượng xử lý

Lưu mã sau thành **TimeBoundaryDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class TimeBoundaryDemo {

    record InstantRange(Instant startInclusive, Instant endExclusive) {
        InstantRange {
            Objects.requireNonNull(startInclusive);
            Objects.requireNonNull(endExclusive);
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("Range không hợp lệ");
            }
        }

        boolean contains(Instant value) {
            return !value.isBefore(startInclusive)
                    && value.isBefore(endExclusive);
        }

        Duration duration() {
            return Duration.between(startInclusive, endExclusive);
        }
    }

    record OrderEvent(String id, Instant createdAt) {
    }

    static InstantRange forLocalDate(LocalDate date, ZoneId zone) {
        ZonedDateTime start = date.atStartOfDay(zone);
        ZonedDateTime end = date.plusDays(1).atStartOfDay(zone);
        return new InstantRange(start.toInstant(), end.toInstant());
    }

    static long countOrders(List<OrderEvent> events, InstantRange range) {
        return events.stream()
                .filter(event -> range.contains(event.createdAt()))
                .count();
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T14:00:00Z"),
                ZoneId.of("UTC")
        );
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));

        InstantRange range = forLocalDate(businessDate, businessZone);

        List<OrderEvent> events = List.of(
                new OrderEvent("A", range.startInclusive()),
                new OrderEvent("B", range.startInclusive().plusSeconds(60)),
                new OrderEvent("C", range.endExclusive().minusNanos(1)),
                new OrderEvent("D", range.endExclusive())
        );

        System.out.println("Business date: " + businessDate);
        System.out.println("Start: " + range.startInclusive());
        System.out.println("End exclusive: " + range.endExclusive());
        System.out.println("Elapsed hours: " + range.duration().toHours());
        System.out.println("Orders in day: " + countOrders(events, range));

        long started = System.nanoTime();
        long count = countOrders(events, range);
        Duration processing = Duration.ofNanos(
                System.nanoTime() - started
        );

        System.out.println("Count: " + count);
        System.out.println("Processing nanos: " + processing.toNanos());
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~shell
javac --release 17 TimeBoundaryDemo.java
java TimeBoundaryDemo
~~~

Kết quả có thể thấy:

- `A` nằm đúng đầu ngày và được tính.
- `B` nằm bên trong khoảng và được tính.
- `C` nằm ngay trước đầu ngày tiếp theo và được tính.
- `D` đúng bằng `endExclusive` nên không được tính vào ngày đang xét.
- `Clock.fixed` làm cho ngày nghiệp vụ trong ví dụ luôn tái lập khi chạy test.
- `System.nanoTime()` được dùng để đo đoạn xử lý, không phải lấy timestamp nghiệp vụ.

## 15. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Dùng `Duration.ofDays(1)` để tìm đầu ngày kế tiếp | Một ngày lịch có thể không dài 24 giờ | Dùng `LocalDate.plusDays(1).atStartOfDay(zone)` |
| Dùng `23:59:59.999` làm cuối ngày | Giả định precision mili giây | Dùng khoảng `[start, nextDayStart)` |
| Dùng `BETWEEN` với cả hai đầu inclusive | Có thể tính record đầu ngày kế tiếp hai lần | Dùng `>= start AND < end` |
| Tính Duration từ hai `LocalDateTime` khi cần elapsed thực | Không có zone/DST trong hai giá trị | Gắn `ZoneId` hoặc dùng `Instant` |
| Dùng Duration cho tháng/năm | Tháng/năm có độ dài lịch khác nhau | Dùng `Period` với ngày/zone phù hợp |
| Dùng `LocalDateTime` như timestamp UTC | Không có offset/zone để xác định instant | Parse offset hoặc áp dụng zone theo contract |
| Dùng `ZoneId.systemDefault()` cho mọi logic | Kết quả phụ thuộc cấu hình server | Truyền zone nghiệp vụ tường minh |
| Dùng `Instant.now()` để đo timeout ngắn | Wall clock có thể bị điều chỉnh | Dùng `System.nanoTime()` |
| So sánh giá trị tuyệt đối `nanoTime()` với deadline | Origin không có nghĩa timestamp, có thể wrap | So sánh hiệu `now - start` với budget |
| Gọi `Duration.toNanos()` cho giá trị bất kỳ | Có thể overflow `long` | Validate phạm vi hoặc giữ Duration |
| Bỏ qua Duration âm | Có thể che mốc truyền sai thứ tự hoặc deadline đã qua | Xác định rõ chính sách cho giá trị âm |
| Giả định mọi LocalDateTime có một offset | DST gap/overlap phá giả định này | Dùng `ZoneRules.getValidOffsets` khi cần quyết định rõ |
| Giả định Instant luôn chính xác nano giây ngoài đời | Clock/hệ điều hành có độ chính xác thấp hơn | Phân biệt độ phân giải API và độ chính xác nguồn |

## 16. Bài tập thực hành

### Bài 1 — Tính thời lượng request

Cho:

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");
Instant end = Instant.parse("2026-11-15T08:00:02.345Z");
~~~

Tính Duration, in giây, mili giây và phần nano. Thử đảo vị trí hai mốc và giải thích vì sao Duration âm.

### Bài 2 — Phân biệt Duration và Period

Với ngày 31/01/2026, tính:

- Sau 30 ngày bằng Duration.
- Sau một tháng bằng Period.

Giải thích vì sao hai kết quả không nhất thiết trùng nhau.

### Bài 3 — Tạo range một ngày

Viết method nhận `LocalDate` và `ZoneId`, trả về `InstantRange` theo `[start, end)`. Kiểm tra các mốc:

- Đúng đầu ngày.
- Một nano giây trước cuối khoảng.
- Đúng đầu ngày tiếp theo.

Xác định mốc nào được bao gồm.

### Bài 4 — DST gap và overlap

Dùng `Europe/Paris` và các ngày chuyển DST trong một năm phù hợp với dữ liệu timezone của JDK. So sánh:

- `date.atStartOfDay(zone)` đến đầu ngày kế tiếp.
- Cộng `Duration.ofHours(24)`.
- Cộng `Period.ofDays(1)`.

Kiểm tra một LocalDateTime nằm trong gap và một LocalDateTime nằm trong overlap bằng `ZoneRules.getValidOffsets`.

### Bài 5 — Kiểm thử với Clock.fixed

Viết service xác định deadline sau 30 phút từ hiện tại. Inject `Clock`, sau đó dùng `Clock.fixed` trong test để xác minh kết quả chính xác mà không phụ thuộc giờ chạy thật.

### Bài 6 — Timeout với nanoTime

Viết method đo một công việc bằng `System.nanoTime()`, trả về Duration. Không chuyển giá trị tuyệt đối của nanoTime thành Instant. Thử giới hạn timeout và xử lý Duration quá lớn khi chuyển sang nano.

### Bài 7 — Truy vấn theo ngày

Giả sử người dùng chọn ngày 15/11/2026 theo zone `Asia/Ho_Chi_Minh`. Tính hai biên Instant và viết câu SQL dùng `created_at >= :start` và `created_at < :end`. Giải thích vì sao không cần tạo mốc `23:59:59.999999999`.

### Bài 8 — Kiểm tra overlap

Viết hàm kiểm tra hai `InstantRange` có chồng lấn không. Thử hai khoảng liền nhau và hai khoảng giao nhau. Giải thích công thức `aStart < bEnd && bStart < aEnd`.

## 17. Câu hỏi tự kiểm tra

1. Khác biệt giữa `Instant`, `Duration`, `Period` và `LocalDateTime`?
2. `Duration.between(start, end)` có thể trả giá trị âm không?
3. `Duration.ofDays(1)` có ý nghĩa chính xác bao nhiêu giây?
4. Vì sao Duration không đại diện chính xác cho một tháng lịch?
5. `toDays()` khác `toDaysPart()` thế nào?
6. Khi nào `Duration.toNanos()` có thể ném `ArithmeticException`?
7. Khoảng nửa mở `[start, end)` có lợi gì ở biên?
8. Vì sao truy vấn database theo ngày nên dùng đầu ngày kế tiếp làm end exclusive?
9. Vì sao `LocalDateTime` không đủ để tính elapsed thực qua DST?
10. `atStartOfDay(ZoneId)` giúp xử lý điều gì?
11. DST gap và overlap khác nhau thế nào?
12. Khi nào nên dùng `ZoneId` thay cho `ZoneOffset`?
13. `Clock.fixed` hỗ trợ kiểm thử ra sao?
14. Vì sao `Instant.now()` không phải monotonic timer?
15. Tại sao `System.nanoTime()` chỉ nên dùng hiệu giữa hai lần gọi?
16. Khi nào nên dùng Duration và khi nào nên dùng Period trong deadline nghiệp vụ?

## 18. Tài liệu tham khảo

- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): tạo, tính toán, so sánh và chuyển đổi thời lượng.
- [Java SE 17 API — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): khoảng thời gian theo đơn vị lịch.
- [Java SE 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): mốc thời gian trên timeline.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): nguồn thời gian có thể thay thế để kiểm thử.
- [Java SE 17 API — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): ngày giờ có vùng múi giờ, xử lý gap/overlap.
- [Java SE 17 API — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): quy tắc offset hợp lệ và chuyển đổi giờ địa phương.
- [Java SE 17 API — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời lượng bằng nguồn thời gian đơn điệu.
- [dev.java — Date Time](https://dev.java/learn/date-time/): tài liệu học Java Time API.

Khi tính thời lượng, hãy dùng `Duration` trên hai mốc có ý nghĩa rõ. Khi xử lý ngày lịch, hãy xác định `ZoneId` và dùng biên đầu ngày kế tiếp theo khoảng nửa mở. Khi đo timeout hoặc latency, hãy dùng `System.nanoTime()`. Ba lựa chọn này tách biệt mốc thời gian, quy tắc lịch và thời lượng thực, giúp code Java 17 xử lý đúng các biên ngày, DST và độ chính xác timestamp.
