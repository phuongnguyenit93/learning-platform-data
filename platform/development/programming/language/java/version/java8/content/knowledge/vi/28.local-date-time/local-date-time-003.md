# LocalDateTime và thời gian cục bộ trong Java

> **Module:** Java 8 — Ngày giờ cục bộ. **Trọng tâm:** `java.time.LocalDateTime` biểu diễn ngày và giờ theo lịch địa phương, **không kèm múi giờ hoặc UTC offset**. Đây là API ra mắt từ Java 8 và vẫn là lựa chọn hiện hành cho thời gian lịch không gắn một thời điểm tuyệt đối.

## 1. LocalDateTime thực sự biểu diễn điều gì?

Một `LocalDateTime` gồm hai thành phần:

- **`LocalDate`:** năm, tháng, ngày trong hệ lịch ISO-8601.
- **`LocalTime`:** giờ, phút, giây và phần nano giây trong ngày.

Ví dụ:

~~~java
LocalDateTime appointment = LocalDateTime.of(2025, 7, 2, 16, 5);
System.out.println(appointment); // 2025-07-02T16:05
~~~

Đây là **đoạn minh họa**, cần import `java.time.LocalDateTime`.

`2025-07-02T16:05` chỉ cho biết **ngày 2/7/2025 lúc 16:05 theo đồng hồ địa phương**, chưa nói đồng hồ đó ở đâu. Nếu cùng chuỗi này được hiểu ở Thành phố Hồ Chí Minh hoặc New York, chúng có thể chỉ **hai thời điểm thực tế hoàn toàn khác nhau**.

Đặc điểm quan trọng nhất:

> **`LocalDateTime` không chứa `ZoneId`, không chứa `ZoneOffset`, không tự xác định một `Instant` và không thể được chuyển chính xác thành thời điểm UTC nếu thiếu thông tin múi giờ hoặc offset.**

Có thể dùng `LocalDateTime` để biểu diễn:

- Giờ bắt đầu một buổi họp **trên lịch địa phương** khi múi giờ được lưu/quy định riêng.
- Ngày giờ người dùng nhập trong một form, **trước khi** quyết định áp dụng múi giờ.
- Mốc thời gian trong cơ sở dữ liệu được định nghĩa rõ là **local wall-clock time**, không phải instant.
- Thời điểm mở cửa hoặc lịch hẹn có ngày cụ thể theo múi giờ của cơ sở; khi cần thực thi thì phải kết hợp với `ZoneId` và xử lý DST.

Không nên dùng một `LocalDateTime` **đứng một mình** làm “thời điểm sự kiện đã xảy ra trên toàn cầu”. Với audit log, message timestamp, thời điểm nhận thanh toán và dữ liệu đa múi giờ, thường cần `Instant`, `OffsetDateTime` hoặc `ZonedDateTime` tùy yêu cầu.

### 1.1. "Cục bộ" không đồng nghĩa "múi giờ hệ thống"

Tên "Local" nghĩa kiểu dữ liệu chỉ **ngày/giờ theo lịch**, chứ không có nghĩa nó *luôn gắn cứng với múi giờ của máy đang chạy*. Chỉ những factory như `LocalDateTime.now()` mới đọc múi giờ từ clock mặc định để tạo **giá trị local**. Sau khi đã tạo, object `LocalDateTime` **không mang theo** múi giờ đã được dùng ở lúc tạo.

Ví dụ:

~~~java
LocalDateTime schedule = LocalDateTime.of(2025, 7, 2, 9, 30);
~~~

Giá trị này độc lập với việc chạy trên máy ở Hà Nội, London hay New York. Chính phần ứng dụng quyết định nó là 09:30 **của khu vực nào** khi cần chuyển sang một thời điểm thực.

## 2. Phân biệt các kiểu java.time quan trọng

| Kiểu | Chứa gì? | Có chỉ ra thời điểm tuyệt đối? | Dùng khi nào? |
| --- | --- | --- | --- |
| `LocalDate` | Năm–tháng–ngày, không có giờ | **Không** | Ngày sinh, ngày nghỉ, ngày đến hạn theo lịch |
| `LocalTime` | Giờ–phút–giây–nano, không có ngày | **Không** | Giờ mở cửa hằng ngày, thời gian trên đồng hồ |
| **`LocalDateTime`** | Ngày + giờ, không có zone/offset | **Không** | Giờ hẹn địa phương, dữ liệu local của form |
| `Instant` | Một thời điểm trên timeline UTC | **Có** | Audit log, timestamp sự kiện, trao đổi hệ thống |
| `OffsetDateTime` | Ngày/giờ + offset như `+07:00` | **Có** | Dữ liệu cần ghi offset cụ thể, trao đổi ISO-8601 |
| `ZonedDateTime` | Ngày/giờ + `ZoneId` với quy tắc vùng | **Có** | Lịch theo múi giờ vùng, xử lý chuyển đổi DST |

**`+07:00` là offset**, còn `Asia/Ho_Chi_Minh` là **zone ID** có bộ quy tắc lịch sử và có thể được cập nhật. Zone ID không được đồng nhất với một offset cố định cho mọi thời điểm lịch sử/tương lai.

Một `LocalDateTime` là “09:00” của lịch địa phương, còn `Instant` là “mốc nào trên dòng thời gian”. Khi hỏi *“còn bao nhiêu giây thực tới hạn?”*, cần làm rõ zone/offset trước khi tính.

### 2.1. Ví dụ về hai vùng khác nhau

~~~java
LocalDateTime local = LocalDateTime.of(2025, 7, 2, 16, 5);

ZonedDateTime vietnam = local.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime newYork = local.atZone(
        ZoneId.of("America/New_York"));
~~~

Đây là **đoạn minh họa**, cần import `LocalDateTime`, `ZonedDateTime` và `ZoneId`. Hai biến mang cùng mặt đồng hồ 16:05 nhưng có thể chỉ **hai Instant khác nhau**. Không thể thay việc chọn zone bằng cách tự thêm một chuỗi `"Z"` vào cuối `LocalDateTime.toString()`.

## 3. Tạo LocalDateTime một cách chính xác

### 3.1. of(...): biết ngày và giờ từ đầu

~~~java
LocalDateTime meeting = LocalDateTime.of(
        2025, 7, 2, 16, 5);

LocalDateTime precise = LocalDateTime.of(
        2025, 7, 2, 16, 5, 30, 123_456_789);
~~~

Đây là **đoạn minh họa**. Dạng thứ nhất có giây và nano bằng 0; dạng thứ hai có giây `30` và nano `123456789`. Kiểu có độ phân giải tới **nano giây** về mặt biểu diễn nhưng **không hứa** clock hệ thống đo được thời gian với độ chính xác nano giây.

Các overload còn có dạng nhận `LocalDate` và `LocalTime`:

~~~java
LocalDate date = LocalDate.of(2025, 7, 2);
LocalTime time = LocalTime.of(16, 5);
LocalDateTime combined = LocalDateTime.of(date, time);
~~~

Đây là đoạn minh họa. Kết hợp này hữu ích khi người dùng nhập ngày và giờ ở hai trường riêng biệt.

**Giá trị không hợp lệ** như ngày 31/02, giờ 25, phút 60 sẽ dẫn đến `DateTimeException`; Java không âm thầm làm tròn ngày sai khi tạo bằng `of`.

### 3.2. now(): thời gian hiện tại **theo clock**

~~~java
LocalDateTime currentLocal = LocalDateTime.now();
LocalDateTime localInZone =
        LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là **đoạn minh họa**. Hai lời gọi có thể cho giá trị khác nhau:

- `now()` dùng clock và múi giờ mặc định của hệ thống.
- `now(ZoneId)` tạo **giá trị local** tính theo vùng chỉ định tại thời điểm đọc clock.
- Cả hai trả về **LocalDateTime không giữ ZoneId** sau khi tạo.
- Đầu ra của `now(...)` thay đổi theo thời gian; không nên viết expected stdout cố định cho lời gọi này.

Nếu ứng dụng có nhiều máy/container với cấu hình timezone khác nhau, việc gọi `now()` rải rác có thể khiến một số hệ thống biểu diễn giờ địa phương khác nhau. **Đừng dựa vào timezone mặc định một cách ngầm định** khi nghiệp vụ yêu cầu một vùng xác định.

### 3.3. Clock: thiết kế dễ kiểm thử

Java 8 cung cấp `java.time.Clock` để chủ động nguồn thời gian. Phương thức `LocalDateTime.now(Clock)` cho phép test dùng thời gian cố định:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2025-07-01T10:15:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDateTime value = LocalDateTime.now(fixed);
// 2025-07-01T17:15:30
~~~

Đây là **đoạn minh họa**, cần import `Clock`, `Instant`, `ZoneId`, `LocalDateTime`. `Clock.fixed` bảo đảm cùng giá trị trong test, không bị phụ thuộc thời gian thực khi chạy.

Trong ứng dụng, có thể **inject Clock** vào service thay vì gọi `LocalDateTime.now()` sâu trong logic:

~~~java
final class BookingService {
    private final Clock clock;

    BookingService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    LocalDateTime currentLocalTime() {
        return LocalDateTime.now(clock);
    }
}
~~~

Đây là **mã minh họa**, cần import `Clock`, `LocalDateTime`, `Objects`. Production có thể truyền `Clock.system(zone)`; test truyền `Clock.fixed(...)`. Điều này không đổi ý nghĩa của `LocalDateTime` thành Instant; nó chỉ giúp chọn nguồn thời gian dự đoán được.

### 3.4. ofInstant(Instant, ZoneId): từ mốc UTC sang thời gian cục bộ

~~~java
Instant instant = Instant.parse("2025-07-02T09:05:00Z");
LocalDateTime inVietnam = LocalDateTime.ofInstant(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));
// 2025-07-02T16:05
~~~

Đây là **đoạn minh họa**. Khi đã có một `Instant`, phải biết **zone** để hiển thị ra ngày/giờ địa phương. Việc chuyển theo một vùng khác có thể đổi cả ngày, tháng hoặc năm.

## 4. LocalDateTime là immutable và thread-safe

`LocalDateTime` là một **value-based class** bất biến. Các method như `plusDays`, `minusHours`, `withMonth` hay `truncatedTo` **trả về object mới biểu diễn giá trị đã thay đổi**, không chỉnh object gốc.

~~~java
LocalDateTime original = LocalDateTime.of(2025, 7, 2, 16, 5);

original.plusDays(1); // Bỏ qua kết quả; original KHÔNG đổi.

LocalDateTime nextDay = original.plusDays(1);
~~~

Đây là **đoạn minh họa**. `original` vẫn là ngày 2/7; `nextDay` là ngày 3/7 cùng giờ.

Khi một giá trị `LocalDateTime` được chia sẻ giữa thread, bản thân nó không bị mutate. Tuy nhiên, điều đó **không** tự làm thread-safe một List/Map chứa nó, một biến tham chiếu có thể được thay đồng thời, hoặc logic đăng ký lịch yêu cầu kiểm soát giao dịch.

### 4.1. Không dùng identity để so LocalDateTime

Với value-based class, dùng `equals` để so giá trị:

~~~java
LocalDateTime a = LocalDateTime.of(2025, 7, 2, 16, 5);
LocalDateTime b = LocalDateTime.of(2025, 7, 2, 16, 5);

System.out.println(a.equals(b)); // true
~~~

Không dùng `a == b` để xác định cùng mốc local, cũng không đồng bộ bằng `synchronized(a)` vì `LocalDateTime` được đặc tả là value-based. Những thao tác dựa vào identity của một value-based class nên tránh.

## 5. Truy xuất thành phần ngày, giờ và độ chính xác

Các method thường gặp:

| Method | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getYear()` | `int` | Năm |
| `getMonth()` | `Month` | Enum tháng |
| `getMonthValue()` | `int` | Tháng từ 1 đến 12 |
| `getDayOfMonth()` | `int` | Ngày trong tháng |
| `getDayOfWeek()` | `DayOfWeek` | Thứ theo ISO, Monday → Sunday |
| `getDayOfYear()` | `int` | Ngày thứ bao nhiêu của năm |
| `getHour()` | `int` | Giờ 0–23 |
| `getMinute()` | `int` | Phút 0–59 |
| `getSecond()` | `int` | Giây 0–59 |
| `getNano()` | `int` | Nano giây 0–999999999 |
| `toLocalDate()` | `LocalDate` | Chỉ lấy phần ngày |
| `toLocalTime()` | `LocalTime` | Chỉ lấy phần giờ |

Ví dụ:

~~~java
LocalDateTime value = LocalDateTime.of(2025, 7, 2, 16, 5);

System.out.println(value.getDayOfWeek()); // WEDNESDAY
System.out.println(value.toLocalDate());  // 2025-07-02
System.out.println(value.toLocalTime());  // 16:05
~~~

Đây là **đoạn minh họa**. Phương thức `toLocalDate()` và `toLocalTime()` tạo các giá trị không chứa múi giờ — chúng cũng không được tự coi là timestamp UTC.

### 5.1. Thay đúng một trường với with...

~~~java
LocalDateTime base = LocalDateTime.of(2025, 7, 2, 16, 5);
LocalDateTime changed = base.withHour(9).withMinute(30);
// 2025-07-02T09:30
~~~

Đây là đoạn minh họa. `withHour(9)` thay giờ, không trừ `7` giờ theo ý nghĩa một khoảng thời gian đã trôi qua. `withDayOfMonth`, `withMonth`, `withYear` cũng có quy tắc điều chỉnh ngày cuối tháng trong những trường hợp cần thiết theo API.

### 5.2. Bỏ phần giây/nano để chuẩn hóa độ hạt

~~~java
LocalDateTime precise =
        LocalDateTime.of(2025, 7, 2, 16, 5, 34, 987_654_321);

LocalDateTime atMinute =
        precise.truncatedTo(ChronoUnit.MINUTES);
// 2025-07-02T16:05
~~~

Đây là **đoạn minh họa**, cần import `java.time.temporal.ChronoUnit`.

`truncatedTo` đặt các thành phần nhỏ hơn đơn vị chỉ định về 0; đây là **truncation**, không phải làm tròn lên theo giá trị trung bình. Không nhầm với quy tắc rounding của báo cáo tài chính.

## 6. Cộng/trừ ngày giờ: phép lịch khác với thời gian thực

Các phép tính có từ Java 8:

~~~java
LocalDateTime base = LocalDateTime.of(2025, 7, 2, 16, 5);

LocalDateTime tomorrow = base.plusDays(1);
LocalDateTime later = base.plusHours(2).plusMinutes(15);
LocalDateTime earlier = base.minusWeeks(1);
LocalDateTime nextMonth = base.plusMonths(1);
~~~

Đây là các **đoạn minh họa**. Các kết quả vẫn là LocalDateTime không có zone.

### 6.1. Cộng tháng/năm ở cuối tháng

Số ngày trong tháng không bằng nhau. Java xử lý ngày cuối tháng theo quy tắc lịch ISO:

~~~java
LocalDateTime jan31 =
        LocalDateTime.of(2025, 1, 31, 10, 20);
LocalDateTime feb =
        jan31.plusMonths(1);
// 2025-02-28T10:20
~~~

Ngày 31/02 không tồn tại; `plusMonths(1)` điều chỉnh về ngày hợp lệ cuối cùng của tháng đích. Tương tự, `2024-02-29.plusYears(1)` về ngày 28/02/2025.

**Không dùng `plusDays(30)` để thay thế quy tắc “thêm một tháng”.** Hai phép có thể cho kết quả khác nhau. Chọn theo nghiệp vụ: thêm số ngày cố định hay đổi tháng trên lịch.

### 6.2. LocalDateTime không tự xử lý DST khi cộng giờ

Giả sử một ngày ở một vùng có chuyển đổi giờ mùa hè (daylight saving time, DST). `LocalDateTime.plusHours(24)` chỉ thay các trường theo lịch/giờ local; nó **không biết** vùng có một giờ bị bỏ qua hoặc lặp lại.

Do vậy:

- **“Ngày mai lúc 09:00 địa phương”** là bài toán lịch: lưu ngày+giờ local và `ZoneId` của khu vực.
- **“Sau đúng 24 giờ thực”** là bài toán timeline: tính bằng `Instant`/`Duration` hoặc một kiểu đã gắn zone với ngữ nghĩa duration rõ ràng.
- Hai yêu cầu này có thể cho các mốc khác nhau khi qua ngày đổi DST.

**Một `LocalDateTime` không thể tự trả lời chính xác khoảng thời gian thực đã trôi qua** giữa hai mốc ở vùng chuyển DST nếu chưa gắn quy tắc vùng cho cả hai.

### 6.3. Period và Duration khác nhau

- `Period` biểu diễn lượng thời gian theo **năm/tháng/ngày lịch**; thích hợp cho những khái niệm lịch.
- `Duration` biểu diễn lượng thời gian theo **giây/nano giây**; thích hợp cho elapsed time.
- `ChronoUnit` cho phép đo chênh lệch theo đơn vị xác định.

Với ngày giờ local, có thể đo **chênh lệch trên dòng thời gian local giả định**, nhưng kết quả chưa chắc là elapsed time thực sau khi áp quy tắc zone.

~~~java
LocalDateTime start = LocalDateTime.of(2025, 7, 2, 9, 0);
LocalDateTime end = start.plusMinutes(90);

long localMinutes = Duration.between(start, end).toMinutes();
// 90

Period calendarDays = Period.between(
        start.toLocalDate(),
        end.toLocalDate());
// P0D (cùng một ngày)
~~~

Đây là đoạn minh họa. `Duration.between(LocalDateTime,LocalDateTime)` tính chênh lệch dựa trên **giá trị local**; với giờ có DST, muốn biết elapsed time thực hãy chuyển các mốc hợp lệ thành `Instant` trước.

## 7. So sánh LocalDateTime

Các API:

- `isBefore(other)` — đứng trước theo lịch local.
- `isAfter(other)` — đứng sau theo lịch local.
- `isEqual(other)` — cùng giá trị local.
- `compareTo(other)` — có thứ tự tăng dần theo ngày giờ local.
- `equals(other)` — cùng dữ liệu ngày và giờ tương ứng; không yêu cầu hai object cùng tham chiếu.

~~~java
LocalDateTime a = LocalDateTime.of(2025, 7, 2, 9, 0);
LocalDateTime b = LocalDateTime.of(2025, 7, 2, 10, 0);

System.out.println(a.isBefore(b)); // true
System.out.println(b.isAfter(a));  // true
System.out.println(a.equals(b));   // false
~~~

Đây là đoạn minh họa.

**Chú ý:** `a.isBefore(b)` là phép so sánh thứ tự của hai giá trị local, **không** chứng minh `a` đã xảy ra trước `b` trên timeline nếu chúng được dùng ở hai vùng khác nhau. Muốn so sánh chính xác thời điểm sự kiện đa múi giờ, cần đổi về Instant.

### 7.1. Sắp xếp danh sách giờ hẹn

~~~java
List<LocalDateTime> meetings = Arrays.asList(
        LocalDateTime.of(2025, 7, 2, 16, 0),
        LocalDateTime.of(2025, 7, 2, 9, 0));

meetings.sort(Comparator.naturalOrder());
// 09:00 đứng trước 16:00 cùng ngày.
~~~

Đây là **đoạn minh họa**, cần import `List`, `Arrays`, `Comparator`. `LocalDateTime` có natural order đúng theo thành phần local. Nhưng nếu lịch từ nhiều timezone khác nhau, phải chuyển về cùng **Instant** hoặc cùng vùng để sắp theo thứ tự thực.

### 7.2. Chú ý biên khoảng [start, end)

Khi lọc theo khoảng thời gian địa phương, thực tế hay dùng biên **đầu bao gồm, cuối loại trừ**:

~~~java
boolean inside = !value.isBefore(start)
        && value.isBefore(end);
~~~

Đây là đoạn minh họa, giả định có `LocalDateTime value/start/end` không null. Quy tắc này tiện ghép các khoảng liên tiếp mà không lặp mốc biên, nhưng vẫn **chỉ là điều kiện theo local date-time**. Đối với hệ thống log đa vùng, hãy dùng phạm vi `Instant` hoặc giá trị đã được chuẩn hóa.

## 8. Định dạng và phân tích chuỗi bằng DateTimeFormatter

### 8.1. Dạng ISO-8601 mặc định

`LocalDateTime.parse(CharSequence)` mong một chuỗi tương thích với `DateTimeFormatter.ISO_LOCAL_DATE_TIME`, chẳng hạn:

~~~java
LocalDateTime value =
        LocalDateTime.parse("2025-07-02T16:05:30");

System.out.println(value);
// 2025-07-02T16:05:30
~~~

Đây là đoạn minh họa. Ký tự `T` nối ngày và giờ theo định dạng ISO. Chuỗi `2025-07-02T16:05` cũng hợp lệ; giây mặc định bằng 0.

`LocalDateTime.toString()` tạo dạng ISO local có **chi tiết hiển thị linh hoạt theo độ chính xác**: ví dụ có thể không in giây nếu chúng bằng 0. Không giả định nó luôn có độ dài hay mẫu cố định để xuất CSV/API theo hợp đồng bên ngoài.

### 8.2. Format theo nhu cầu hiển thị

~~~java
DateTimeFormatter display = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm",
        Locale.ROOT);

LocalDateTime value =
        LocalDateTime.of(2025, 7, 2, 16, 5);

String output = value.format(display);
// "02/07/2025 16:05"
~~~

Đây là **đoạn minh họa**, cần import `DateTimeFormatter` và `Locale`.

Một số ký hiệu pattern hữu ích:

| Pattern | Ý nghĩa |
| --- | --- |
| `uuuu` | Proleptic year, phù hợp khi parse strict |
| `MM` | Tháng 2 chữ số |
| `dd` | Ngày trong tháng 2 chữ số |
| `HH` | Giờ 24h (00–23) |
| `mm` | Phút |
| `ss` | Giây |
| `SSS` | Ba chữ số phần giây (millisecond precision khi hiển thị) |
| `XXX` | Offset dạng `+07:00` khi temporal có offset — **không áp dụng trực tiếp cho LocalDateTime** |
| `VV` | Region zone ID khi temporal có zone — **không áp dụng trực tiếp cho LocalDateTime** |

Không dùng chữ `MM` cho phút (`mm` mới là phút); không dùng `hh` nếu muốn 24h (`HH`). Dùng `uuuu` thay vì `yyyy` trong ví dụ strict parsing để tránh các vấn đề Year-of-Era thiếu era khi resolver strict.

### 8.3. Parse từ chuỗi custom và xác thực chặt

~~~java
DateTimeFormatter parser = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDateTime value =
        LocalDateTime.parse("02/07/2025 16:05", parser);
// 2025-07-02T16:05
~~~

Đây là đoạn minh họa, cần `java.time.format.ResolverStyle`. Nếu chuỗi là `31/02/2025 16:05` hoặc `02/07/2025 25:05`, parse strict từ chối bằng `DateTimeParseException`.

**Không nên tự tách chuỗi theo `"/"` hoặc `":"` rồi bỏ qua kiểm tra ngày hợp lệ** khi JDK đã có parser rõ ràng, hỗ trợ locale/pattern và validation.

### 8.4. DateTimeFormatter là immutable

`DateTimeFormatter` được thiết kế immutable và thread-safe, có thể tái sử dụng ở một field `static final` nếu cấu hình cố định:

~~~java
private static final DateTimeFormatter DISPLAY =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.ROOT);
~~~

Đây là **đoạn khai báo field minh họa trong lớp**, không phải file Java chạy độc lập.

Không cần tự tạo formatter mới ở mỗi lần gọi nếu mẫu và locale giống nhau. Tuy nhiên, nếu mỗi người dùng có locale hoặc timezone riêng, chọn formatter/zone dựa trên ngữ cảnh một cách có kiểm soát.

### 8.5. Không thể parse offset timestamp tùy ý thành LocalDateTime mà không quyết định semantics

Ví dụ `"2025-07-02T09:05:00Z"` chứa ký hiệu UTC `Z`; đây là thông tin về **Instant**, không còn đơn thuần là local date-time.

Nếu đầu vào là timestamp UTC, thường nên:

~~~java
Instant instant =
        Instant.parse("2025-07-02T09:05:00Z");

LocalDateTime local =
        LocalDateTime.ofInstant(
                instant, ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là minh họa. Kết quả local là 16:05 theo quy tắc của zone đã chọn. Không nên xóa `Z` rồi parse LocalDateTime vì làm mất ý nghĩa về thời điểm thực.

## 9. Gắn ZoneId: chuyển LocalDateTime thành thời điểm có nghĩa

### 9.1. LocalDateTime.atZone(zone)

Khi lịch địa phương đã xác định vùng, dùng:

~~~java
LocalDateTime local =
        LocalDateTime.of(2025, 7, 2, 16, 5);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(zone);

Instant instant = zoned.toInstant();
// 2025-07-02T09:05:00Z
~~~

Đây là **đoạn minh họa**. Với ngày 2/7/2025 ở `Asia/Ho_Chi_Minh`, offset là `+07:00`, nên 16:05 địa phương tương ứng 09:05 UTC.

**Chỉ gọi `toInstant()` sau khi có đủ thông tin offset/zone hoặc quyết định chuyển đổi rõ ràng.** `LocalDateTime` **không có** method `toInstant()` không tham số.

### 9.2. atOffset(offset) không giống atZone(zone)

~~~java
LocalDateTime local =
        LocalDateTime.of(2025, 7, 2, 16, 5);

OffsetDateTime fixedOffset =
        local.atOffset(ZoneOffset.ofHours(7));

ZonedDateTime regionBased =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây là **đoạn minh họa**. `atOffset` áp một offset **cố định** mà caller cung cấp. `atZone` sử dụng quy tắc của **vùng**. Với cùng ngày cụ thể trong ví dụ, hai biểu diễn cùng Instant; không suy ra `+07:00` luôn tương đương `Asia/Ho_Chi_Minh` trong mọi lịch sử và tương lai.

### 9.3. withZoneSameInstant khác withZoneSameLocal

Giả sử đã có `ZonedDateTime`:

~~~java
ZonedDateTime inVietnam =
        LocalDateTime.of(2025, 7, 2, 16, 5)
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime inNewYork =
        inVietnam.withZoneSameInstant(
                ZoneId.of("America/New_York"));
~~~

Đây là **đoạn minh họa**. `withZoneSameInstant` giữ **cùng thời điểm thực**, thay cách hiển thị ngày/giờ local theo vùng khác.

Trái lại, `withZoneSameLocal(zone)` cố giữ **mặt đồng hồ địa phương** rồi diễn giải lại nó theo zone mới (có thể phải xử lý DST). Hai phương thức phục vụ hai ý định khác nhau; nhầm lẫn có thể làm cuộc hẹn bị lệch hàng giờ.

## 10. DST: giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần

Một zone như `America/New_York` có quy tắc daylight saving time trong nhiều giai đoạn. Vì `LocalDateTime` không chứa zone, nó có thể biểu diễn cả những mặt đồng hồ **không tồn tại** khi áp vào vùng cụ thể.

### 10.1. Gap — giờ bị nhảy qua

Theo quy tắc của `America/New_York` ngày **10/03/2024**, đồng hồ chuyển từ gần 02:00 sang 03:00. Do đó local `2024-03-10T02:30` không tồn tại trong vùng đó.

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime missing =
        LocalDateTime.of(2024, 3, 10, 2, 30);

int possibleOffsets =
        newYork.getRules().getValidOffsets(missing).size();
// 0, theo dữ liệu quy tắc của vùng trong ví dụ.
~~~

Đây là **đoạn minh họa**. `ZoneRules.getValidOffsets(local)` trả danh sách offset hợp lệ cho giờ local:

- **0 offset:** gap, không có thời điểm tương ứng.
- **1 offset:** trường hợp bình thường.
- **2 offset:** overlap, cùng mặt đồng hồ xảy ra hai lần.

Mặc định `missing.atZone(newYork)` thường **điều chỉnh giờ local tiến qua gap** theo thời lượng khoảng chuyển (với ví dụ này thành 03:30); nó không mặc định ném lỗi chỉ vì local hour nằm trong gap. Nếu nghiệp vụ **không cho phép chỉnh giờ tự động**, cần kiểm tra `getValidOffsets` trước khi resolve.

### 10.2. Overlap — mặt đồng hồ lặp lại

Ngày **03/11/2024** trong `America/New_York`, local `01:30` xảy ra hai lần với hai offset khác nhau:

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime ambiguous =
        LocalDateTime.of(2024, 11, 3, 1, 30);

List<ZoneOffset> valid =
        newYork.getRules().getValidOffsets(ambiguous);
// Hai offset hợp lệ theo quy tắc vùng trong ví dụ.
~~~

Đây là **đoạn minh họa**, cần import `java.util.List` và `java.time.ZoneOffset`.

`atZone` sẽ chọn một offset theo quy tắc mặc định (khi overlap, mặc định là offset sớm hơn thường tương ứng phía mùa hè nếu không có offset ưu tiên). Nếu muốn dùng mốc thực thuộc lần xuất hiện **thứ hai**, phải quyết định offset cụ thể, ví dụ bằng `ZonedDateTime.withLaterOffsetAtOverlap()`.

**Đối với giao dịch tài chính, lịch vận chuyển hoặc lịch hẹn có hậu quả quan trọng**, đừng âm thầm giả định mặt đồng hồ lặp lại chỉ một lần. Hãy lưu/thể hiện zone và quy tắc chọn offset khi cần.

### 10.3. Duration qua ngày đổi DST

Giả sử tại New York ngày 10/03/2024:

~~~java
LocalDateTime a = LocalDateTime.of(2024, 3, 10, 1, 30);
LocalDateTime b = LocalDateTime.of(2024, 3, 10, 3, 30);

long localHours = Duration.between(a, b).toHours();
// 2 theo các trường local.

ZoneId zone = ZoneId.of("America/New_York");
long elapsedHours = Duration.between(
        a.atZone(zone).toInstant(),
        b.atZone(zone).toInstant()).toHours();
// 1 theo các Instant thực tế trong ngày DST này.
~~~

Đây là **đoạn minh họa** với quy tắc vùng của thời điểm nói trên. Hai phép khác nhau vì `LocalDateTime` không tự biết bước nhảy DST.

**Bài học:** dùng `LocalDateTime` cho ý định “ngày/giờ trên lịch”; dùng `Instant` hoặc datetime có zone/offset khi tính sự kiện theo trục thời gian thực.

## 11. Chương trình Java 8 hoàn chỉnh với stdout xác định

Lưu toàn bộ chương trình sau thành **LocalDateTimeDemo.java**. Chương trình dùng các giá trị cố định, formatter có quy tắc rõ và `Clock.fixed` để không phụ thuộc vào thời điểm chạy hoặc timezone mặc định của máy.

~~~java
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.util.Locale;

public class LocalDateTimeDemo {
    private static final DateTimeFormatter DISPLAY =
            DateTimeFormatter.ofPattern(
                    "dd/MM/uuuu HH:mm", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        LocalDateTime meeting =
                LocalDateTime.of(2025, 7, 2, 16, 5);

        System.out.println("meeting = "
                + meeting.format(DISPLAY));

        LocalDateTime parsed = LocalDateTime.parse(
                "02/07/2025 16:05", DISPLAY);
        System.out.println("parsed equal = "
                + meeting.equals(parsed));

        System.out.println("date = " + meeting.toLocalDate());
        System.out.println("time = " + meeting.toLocalTime());
        System.out.println("day of week = "
                + meeting.getDayOfWeek());

        System.out.println("tomorrow = "
                + meeting.plusDays(1).format(DISPLAY));
        System.out.println("set hour = "
                + meeting.withHour(9).format(DISPLAY));
        System.out.println("original unchanged = "
                + meeting.format(DISPLAY));

        LocalDateTime monthEnd =
                LocalDateTime.of(2025, 1, 31, 10, 20);
        System.out.println("plus one month = "
                + monthEnd.plusMonths(1).format(DISPLAY));

        LocalDateTime leapDay =
                LocalDateTime.of(2024, 2, 29, 8, 0);
        System.out.println("leap plus one year = "
                + leapDay.plusYears(1).format(DISPLAY));

        System.out.println("next Monday = "
                + meeting.with(
                        TemporalAdjusters.next(DayOfWeek.MONDAY))
                        .format(DISPLAY));

        System.out.println("local minutes = "
                + Duration.between(
                        meeting, meeting.plusMinutes(95)).toMinutes());
        System.out.println("local days = "
                + ChronoUnit.DAYS.between(
                        meeting, meeting.plusDays(3)));

        LocalDateTime precise =
                LocalDateTime.of(2025, 7, 2, 16, 5, 34, 987_000_000);
        System.out.println("truncated to hour = "
                + precise.truncatedTo(ChronoUnit.HOURS)
                        .format(DISPLAY));

        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = meeting.atZone(hcm);
        DateTimeFormatter withOffset =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.ROOT);
        System.out.println("with zone offset = "
                + zoned.format(withOffset));
        System.out.println("instant = "
                + zoned.toInstant());

        LocalDateTime utcLocal =
                LocalDateTime.ofInstant(
                        zoned.toInstant(), ZoneOffset.UTC);
        System.out.println("utc local view = "
                + utcLocal.format(DISPLAY));

        Clock fixed = Clock.fixed(
                Instant.parse("2025-07-01T10:15:30Z"),
                hcm);
        System.out.println("fixed clock local = "
                + LocalDateTime.now(fixed).format(DISPLAY));

        System.out.println("before next day = "
                + meeting.isBefore(meeting.plusDays(1)));
    }
}
~~~

Biên dịch với JDK 17+ nhưng yêu cầu cú pháp/API tương thích Java 8:

~~~bash
javac --release 8 LocalDateTimeDemo.java
java LocalDateTimeDemo
~~~

**Stdout kỳ vọng:**

~~~text
meeting = 02/07/2025 16:05
parsed equal = true
date = 2025-07-02
time = 16:05
day of week = WEDNESDAY
tomorrow = 03/07/2025 16:05
set hour = 02/07/2025 09:05
original unchanged = 02/07/2025 16:05
plus one month = 28/02/2025 10:20
leap plus one year = 28/02/2025 08:00
next Monday = 07/07/2025 16:05
local minutes = 95
local days = 3
truncated to hour = 02/07/2025 16:00
with zone offset = 2025-07-02 16:05 +07:00
instant = 2025-07-02T09:05:00Z
utc local view = 02/07/2025 09:05
fixed clock local = 01/07/2025 17:15
before next day = true
~~~

### 11.1. Giải thích kết quả

1. `LocalDateTime.of` tạo ngày/giờ local chính xác; formatter kiểm soát cách hiển thị. `parse` với cùng formatter tái lập giá trị, nên `parsed equal = true`.
2. `toLocalDate` và `toLocalTime` chia thành phần ngày và giờ. Ngày 02/07/2025 là thứ Tư nên `getDayOfWeek()` trả `WEDNESDAY`.
3. `plusDays(1)` và `withHour(9)` trả giá trị mới; `meeting` giữ nguyên.
4. `31/01/2025 + 1 tháng` điều chỉnh thành `28/02/2025`; `29/02/2024 + 1 năm` cũng điều chỉnh về `28/02/2025`.
5. Thứ Hai kế tiếp sau ngày 02/07/2025 là 07/07/2025, `TemporalAdjusters.next` giữ nguyên giờ local.
6. `Duration.between` trả chênh lệch 95 phút của các giá trị local; `ChronoUnit.DAYS.between` trả 3 ngày giữa hai giá trị đúng cách nhau ba ngày lịch cùng giờ.
7. `truncatedTo(HOURS)` đặt phút, giây và nano về 0; formatter cho `16:00`.
8. `meeting.atZone(Asia/Ho_Chi_Minh)` sử dụng offset `+07:00` cho ngày đang xét, nên mốc UTC tương ứng `09:05Z`. Phép chuyển sang `LocalDateTime` nhìn theo UTC cho ngày/giờ `09:05`, nhưng object mới vẫn **không giữ timezone**.
9. `Clock.fixed` tạo mốc UTC `10:15:30Z`, theo zone Hồ Chí Minh thành `17:15:30`; formatter chỉ in giờ/phút nên output là `17:15`.
10. `isBefore` chỉ so giá trị local và đúng khi đối chiếu ngày 2 với ngày 3 cùng giờ.

**Không cần kết nối mạng, không dùng thời gian hiện tại và không đọc timezone mặc định** trong chương trình; stdout đã được xác định từ dữ liệu cố định.

## 12. LocalDateTime trong cơ sở dữ liệu, JSON và API

### 12.1. Phân biệt loại dữ liệu trước khi lưu

Hãy hỏi nghiệp vụ: trường dữ liệu là **giờ theo đồng hồ địa phương** hay **mốc xảy ra thực tế**?

| Nghiệp vụ | Kiểu Java thường phù hợp | Cần lưu thêm gì? |
| --- | --- | --- |
| Ngày hẹn cụ thể theo lịch địa phương | `LocalDateTime` | `ZoneId` nếu phải quy ra Instant thực tế |
| Giờ mở cửa lặp lại hằng ngày | `LocalTime` | Vùng và quy tắc lịch khi áp vào một ngày |
| Thời điểm giao dịch/log xảy ra | `Instant` hoặc `OffsetDateTime` | Quy ước lưu/hiển thị UTC hoặc offset |
| Lịch xuyên qua thay đổi DST | `ZonedDateTime` / local fields + region ZoneId | Cách xử lý gap/overlap nếu nghiệp vụ cần |
| Ngày chỉ có năm–tháng–ngày | `LocalDate` | Không tự phát minh giờ 00:00 nếu không có ý nghĩa |

Một cột SQL `TIMESTAMP WITHOUT TIME ZONE` hoặc kiểu tương tự có thể phù hợp với **local wall-clock time**, nhưng **không biến nó thành Instant**. Đặc tả và cách chuyển đổi của driver/database/framework phải được kiểm tra riêng: đừng mặc định mọi cơ sở dữ liệu xử lý `TIMESTAMP WITH TIME ZONE` theo cách giống nhau.

JDBC 4.2 hỗ trợ làm việc với các kiểu trong `java.time` ở nhiều môi trường và driver phù hợp; cần kiểm tra phiên bản driver và mapping thực tế. Ưu tiên giữ nghĩa rõ ràng của dữ liệu thay vì tự nối/loại bỏ offset trong chuỗi.

### 12.2. Chuỗi ISO-8601 không tự giải quyết timezone

Ví dụ hai chuỗi:

~~~text
2025-07-02T16:05
2025-07-02T09:05:00Z
~~~

Chuỗi đầu là local date-time, **không xác định Instant**. Chuỗi thứ hai có `Z`, mô tả thời điểm UTC. Nếu API bên ngoài yêu cầu thời điểm cụ thể, gửi `Instant` hoặc một giá trị có offset thay vì local string không kèm ngữ cảnh.

Khi trao đổi giờ hẹn địa phương giữa các vùng, một payload có thể chứa tường minh:

~~~json
{
  "localDateTime": "2025-07-02T16:05:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Đây là **dữ liệu JSON minh họa**, không phải lớp Java. Với lịch quan trọng, có thể cần lưu cả chính sách giải quyết gap/overlap và/hoặc mốc Instant đã chốt tại thời điểm đặt lịch.

### 12.3. Cách đặt tên trường hỗ trợ tránh nhầm

- `scheduledLocalDateTime`: giờ hẹn theo lịch.
- `scheduledZoneId`: vùng để diễn giải giờ hẹn.
- `createdAtInstant`: thời điểm tạo bản ghi thực tế.
- `opensAtLocalTime`: giờ mở cửa trong ngày.

Tên trường kiểu `time`, `dateTime`, `timestamp` mà không nói rõ semantics có thể dẫn đến bug đa múi giờ dù code dùng đúng `LocalDateTime`.

## 13. Lỗi phổ biến và cách phòng tránh

### Lỗi 1 — Coi LocalDateTime luôn là giờ UTC

**Sai:** lưu `LocalDateTime.now()` rồi luôn đọc lại như `UTC`.  
**Đúng:** `now()` đã áp timezone mặc định để lấy *ngày giờ local*, nhưng object không chứa thông tin đó. Nếu cần UTC instant, lấy `Instant.now(clock)` hoặc một kiểu mang mốc trên timeline.

### Lỗi 2 — Thêm "Z" vào local string

~~~java
String incorrect =
        LocalDateTime.of(2025, 7, 2, 16, 5) + "Z";
~~~

Đây là **đoạn phản ví dụ**. Nó tạo một chuỗi trông như UTC nhưng không có phép chuyển đổi múi giờ nào xảy ra. Đúng: quyết định zone, chuyển sang `ZonedDateTime` và `Instant` rồi mới định dạng.

### Lỗi 3 — Dùng now() trong test và chờ kết quả cố định

`LocalDateTime.now()` thay đổi theo thời gian, timezone và clock máy. **Sửa:** inject `Clock` và dùng `Clock.fixed` trong test.

### Lỗi 4 — Cộng 24 giờ local và cho là đã qua đúng 24 giờ thực

`LocalDateTime` không có DST. **Sửa:** nếu cần elapsed time, làm việc trên `Instant`/`Duration`; nếu cần giờ trên lịch, làm việc với local date-time + zone.

### Lỗi 5 — Parse "31/02" mà không thiết lập chính sách

`DateTimeFormatter.ofPattern` mặc định có resolver style riêng (SMART). Nếu nghiệp vụ yêu cầu **từ chối triệt để ngày không tồn tại**, dùng `ResolverStyle.STRICT` và pattern `uuuu` phù hợp.

### Lỗi 6 — Dùng "mm" cho tháng

Trong pattern `MM` là tháng, `mm` là phút. **Sửa:** xem bảng token trước khi khai báo parser/formatter dùng lâu dài.

### Lỗi 7 — Xem ngày giờ local là có thể so thứ tự thực giữa hai zone

`LocalDateTime.isBefore` chỉ so trường local. **Sửa:** chuyển từng mốc thành Instant từ dữ liệu zone/offset trước khi so sánh nếu cần đúng thứ tự timeline.

### Lỗi 8 — Không xử lý gap/overlap

Mặt đồng hồ có thể không tồn tại hoặc lặp lại trong vùng có DST. **Sửa:** dùng `ZoneRules.getValidOffsets(local)` và chính sách điều chỉnh hoặc offset ưu tiên khi cần quyết định chính xác.

### Lỗi 9 — Dùng atOffset với một số giờ cố định để thay zone cho lịch nhiều năm

`atOffset(+07:00)` không lưu quy tắc vùng. **Sửa:** lưu `ZoneId` nếu cuộc hẹn thuộc một địa phương cần xét quy tắc timezone thay đổi.

### Lỗi 10 — Bỏ qua giá trị trả về của plusDays/withHour

`LocalDateTime` immutable, thao tác không thay object cũ. **Sửa:** gán kết quả trở lại biến hoặc dùng biến mới.

### Lỗi 11 — Dùng == để so hai LocalDateTime

`==` là identity giữa reference. **Sửa:** dùng `equals` hoặc `isEqual` theo ý nghĩa, không dựa vào việc JVM có tái sử dụng instance hay không.

### Lỗi 12 — Tin độ chính xác nano giây của clock hệ thống

`LocalDateTime` có trường nanosecond không đồng nghĩa phần cứng/OS sinh timestamp chính xác tới từng nano. **Sửa:** chọn độ phân giải/kiểu lưu phù hợp và đo giới hạn hệ thống, không dùng timestamp làm ID duy nhất.

### Lỗi 13 — Dùng LocalDateTime để tạo TTL, timeout hoặc đo latency

Timeout cần trục thời gian thực, không phải mặt đồng hồ địa phương có thể thay đổi bởi timezone hay đồng bộ hệ thống. **Sửa:** dùng deadline từ `Instant` khi cần thời điểm tuyệt đối; để đo **khoảng thời gian đã trôi qua** trong một tiến trình, ưu tiên đồng hồ đơn điệu phù hợp như `System.nanoTime()` (đọc chênh lệch, không đổi thành mốc UTC). Không dùng `LocalDateTime.now()` để so hiệu năng.

### Lỗi 14 — Nhầm format và chuyển zone

`value.format(pattern)` chỉ tạo chuỗi từ các trường sẵn có, không chuyển từ giờ Việt Nam sang giờ New York. **Sửa:** chuyển `ZonedDateTime.withZoneSameInstant(newZone)` trước, rồi format.

### Lỗi 15 — Dựa vào zone mặc định ở mọi server

Ứng dụng đa môi trường có thể chạy với timezone hệ thống khác nhau. **Sửa:** zone là cấu hình/đầu vào nghiệp vụ rõ ràng và `Clock` được inject; không lấy mặc định rồi âm thầm giả định kết quả.

### Lỗi 16 — Đổi kiểu LocalDateTime thành Instant bằng ép kiểu

`LocalDateTime` và `Instant` không có quan hệ “ép kiểu” để ra cùng một thời điểm. **Sửa:** chọn `ZoneId`/`ZoneOffset`, resolve rồi gọi `toInstant()` trên temporal đã đủ thông tin.

### Lỗi 17 — Không cân nhắc cách resolver khi ngày/giờ đến từ người dùng

Ngay cả khi chuỗi đúng định dạng, việc gắn vào zone có thể gặp gap/overlap. **Sửa:** tách hai bước xác thực: **(1)** ngày giờ có hợp lệ theo lịch ISO? **(2)** có mốc thực duy nhất/hợp lệ tại zone cần dùng không?

## 14. Hướng dẫn lựa chọn theo tình huống

| Bạn cần | Thực hiện |
| --- | --- |
| Nhập “ngày 2/7/2025 lúc 16:05” trên lịch | `LocalDateTime.parse` với formatter phù hợp |
| Lấy thời điểm hiện tại để hiển thị theo Việt Nam | `LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"))` |
| Lấy giờ hiện tại nhưng dễ test | `LocalDateTime.now(clock)` với clock có zone rõ |
| Kết hợp ngày và giờ từ form | `LocalDateTime.of(localDate, localTime)` |
| Cộng một tháng trên lịch | `plusMonths(1)`, hiểu quy tắc ngày cuối tháng |
| Chuyển local giờ hẹn ở zone cụ thể thành Instant | `local.atZone(zone).toInstant()`, xét gap/overlap nếu cần |
| Chuyển Instant thành ngày giờ để hiển thị trong vùng | `LocalDateTime.ofInstant(instant, zone)` |
| Hiển thị ngày/giờ theo mẫu | `format(DateTimeFormatter)` |
| Kiểm tra chuỗi ngày giờ hợp lệ chặt | `parse(text, formatter.withResolverStyle(STRICT))` |
| So sánh hai giá trị ngày giờ **cùng semantics local** | `isBefore`/`isAfter`/`equals` |
| So sánh thời điểm thực toàn cầu | Chuyển về `Instant` và so sánh |
| Lịch lặp hằng ngày “mở lúc 09:00” | `LocalTime` + zone/quy tắc ngày |
| Sự kiện audit/log, expiry, deadline tuyệt đối | `Instant` hoặc kiểu có offset/zone |
| Khác biệt giữa hai mốc thực | `Duration.between(instant1, instant2)` |
| Quy tắc lịch như cộng tháng, năm, ngày | `LocalDateTime.plusMonths`/`plusYears`, `Period` khi thích hợp |

**Không có một kiểu ngày giờ duy nhất đúng cho mọi bài toán.** Mục tiêu là **mô hình hóa đúng ý nghĩa dữ liệu**, không chỉ làm cho parser hay formatter chạy được.

## 15. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** `LocalDateTime.of(2025,7,2,16,5)` có biết 16:05 là giờ Việt Nam hay giờ London không?

**Đáp án:** Không. Object không chứa zone/offset, chỉ các trường ngày và giờ local.

**Câu 2.** `LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"))` có giữ `ZoneId` bên trong không?

**Đáp án:** Không. Zone chỉ được dùng để tính local value tại thời điểm lấy giờ; kết quả vẫn là `LocalDateTime` không mang zone.

**Câu 3.** `LocalDateTime.of(2025,1,31,10,20).plusMonths(1)` ra ngày nào?

**Đáp án:** `2025-02-28T10:20` theo quy tắc điều chỉnh về ngày hợp lệ cuối tháng đích.

**Câu 4.** Tại sao `LocalDateTime.plusHours(24)` không nhất thiết tương đương “24 giờ thực trôi qua”?

**Đáp án:** Vì LocalDateTime không xét DST hoặc zone. Một vùng có thể bỏ qua/lặp một giờ tại chuyển tiếp DST.

**Câu 5.** `DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm")` — `MM` và `mm` khác nhau gì?

**Đáp án:** `MM` là tháng; `mm` là phút. `HH` là giờ theo hệ 24h.

**Câu 6.** Khi cần từ chối ngày “31/02/2025”, nên làm gì?

**Đáp án:** Dùng formatter và `ResolverStyle.STRICT`, với pattern year thích hợp như `uuuu`; parser ném `DateTimeParseException` cho giá trị lịch không hợp lệ.

**Câu 7.** LocalDateTime có gọi `toInstant()` trực tiếp không cần tham số được không?

**Đáp án:** Không. Muốn xác định Instant, trước tiên phải có thông tin offset/zone (ví dụ `local.atZone(zone).toInstant()`).

**Câu 8.** Một local time nằm trong DST gap có thể được `LocalDateTime.of` tạo không?

**Đáp án:** Có, vì `LocalDateTime` chỉ kiểm tra lịch ISO và giờ local; nó không biết quy tắc vùng. Việc resolve vào zone phải xử lý gap theo policy.

**Câu 9.** `ZoneRules.getValidOffsets(local)` trả 0, 1 và 2 phần tử nghĩa gì?

**Đáp án:** Lần lượt gap không có offset hợp lệ, thời điểm local bình thường, và overlap có hai offset hợp lệ.

**Câu 10.** `DateTimeFormatter` có phù hợp dùng lại giữa nhiều lời gọi/thread không?

**Đáp án:** Có. Formatter bất biến và thread-safe, có thể dùng `static final` khi cấu hình phù hợp.

**Câu 11.** Một API trả `2025-07-02T16:05` có đủ để xác định một thời điểm toàn cầu không?

**Đáp án:** Không. Phải biết offset hoặc zone kèm chính sách xử lý DST tương ứng.

**Câu 12.** Khi cùng `Instant` được hiển thị ở Tokyo và Thành phố Hồ Chí Minh, `LocalDateTime` hiển thị có bắt buộc giống nhau không?

**Đáp án:** Không. Múi giờ khác nhau tạo ngày/giờ local khác nhau, dù mốc thực trùng nhau.

**Câu 13.** Vì sao không nên dùng `LocalDateTime.now()` để tạo identifier duy nhất?

**Đáp án:** Vì clock không bảo đảm độ chính xác/độ duy nhất cần thiết, nhiều sự kiện có thể nhận cùng timestamp, và local time có thể nhảy/lặp do quy tắc vùng/hệ thống. Dùng định danh chuyên dụng phù hợp.

**Câu 14.** Làm sao test code phụ thuộc “hiện tại” mà không bị fail theo giờ chạy?

**Đáp án:** Inject `Clock`; trong test dùng `Clock.fixed(instant,zone)` và gọi `LocalDateTime.now(clock)`. Kết quả có thể dự đoán được.

## 16. Tổng kết

- **`LocalDateTime` = `LocalDate` + `LocalTime`**, **không** có múi giờ, offset hay Instant.
- Dùng nó để mô hình hóa **ngày và giờ theo lịch địa phương**; dùng `Instant`/`OffsetDateTime`/`ZonedDateTime` khi cần thời điểm thực và timezone.
- **`of`, `parse`, `ofInstant`, `now`, `plus/minus`, `with`, `truncatedTo`** đều là API hiện hành có từ Java 8.
- `LocalDateTime` là value-based, bất biến và thread-safe; mọi thao tác điều chỉnh trả về một giá trị mới.
- **`DateTimeFormatter`** dùng để format/parse; `ResolverStyle.STRICT` hữu ích khi cần xác thực nghiêm ngặt.
- **Không nhầm 24 giờ local với 24 giờ thực qua DST**; gắn `ZoneId` và xét gap/overlap khi chuyển giờ hẹn thành mốc thực.
- `Clock` giúp định nghĩa rõ nguồn thời gian và test deterministic.
- Dữ liệu từ API/DB phải nói rõ **local wall-clock time hay instant timestamp**. Một chuỗi không có zone/offset không tự trở thành UTC.
- Tất cả kiến thức trọng tâm ở đây vẫn áp dụng trong Java hiện đại; không cần các cách xử lý ngày giờ cũ thay thế cho `java.time`.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — LocalDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDateTime.html)
- [Oracle Java SE 25 — LocalDateTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html)
- [Oracle Java SE 25 — ZonedDateTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html)
- [Oracle Java SE 25 — Instant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html)
- [Oracle Java SE 25 — Clock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html)
- [Oracle Java SE 25 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 25 — ZoneRules](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Oracle Java SE 25 — Duration và Period](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html)
