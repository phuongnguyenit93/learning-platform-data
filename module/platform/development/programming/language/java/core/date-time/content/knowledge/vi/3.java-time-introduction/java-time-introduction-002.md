# Tạo giá trị `java.time` bằng `of()`, `now()`, `parse()` và `from()`

## 1. Bốn nhóm factory giải quyết bốn bài toán khác nhau

Các kiểu trong `java.time` (Java 8+, ví dụ bài này chạy với **Java 17+**) thường là **đối tượng bất biến** (*immutable*). Thay vì sửa trạng thái của một đối tượng sau khi khởi tạo, ta tạo giá trị mới qua các phương thức **static factory** rồi dùng kết quả đó. Bốn tên phương thức xuất hiện thường xuyên nhất:

| Phương thức | Nguồn dữ liệu | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|---|
| `of(...)` | Các thành phần đã biết | “Tôi có năm, tháng, ngày, giờ…; làm sao tạo giá trị?” | `LocalDate.of(2024, 2, 29)` |
| `now(...)` | Đồng hồ hệ thống hoặc `Clock` | “Giá trị ngày/giờ tại thời điểm thực thi là gì?” | `LocalDate.now(clock)` |
| `parse(...)` | Chuỗi văn bản theo định dạng xác định | “Chuỗi này biểu diễn ngày/giờ nào?” | `LocalDate.parse("2024-02-29")` |
| `from(...)` | `TemporalAccessor` hoặc đối tượng thời gian tương thích | “Tôi muốn trích xuất các trường thời gian phù hợp từ giá trị đã có” | `LocalDate.from(dateTime)` |

**Không phải mọi kiểu đều cung cấp cả bốn tên.** Chẳng hạn `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` đều có các factory phù hợp, còn `Instant` tạo từ epoch bằng `ofEpochSecond(...)` hoặc `ofEpochMilli(...)`, và từ chuỗi bằng `parse(...)`. `Year`, `YearMonth`, `MonthDay` cũng có những factory riêng. Hãy đọc chữ ký API của kiểu đích thay vì suy đoán mọi kiểu đều có cùng danh sách overload.

Bài học phân biệt **chọn kiểu dữ liệu**, **chọn nguồn đầu vào**, **độ chính xác của giá trị**, và **ngữ cảnh múi giờ**. Khi hiểu bốn điểm đó, việc chọn factory sẽ đơn giản hơn nhiều.

## 2. Chọn đúng kiểu trước khi tạo

`java.time` không có một kiểu duy nhất đại diện cho tất cả thông tin thời gian:

| Kiểu | Chứa thông tin | Không tự chứa | Factory thường dùng |
|---|---|---|---|
| `LocalDate` | Năm–tháng–ngày theo lịch ISO | Giờ, offset, múi giờ | `of`, `now`, `parse`, `from` |
| `LocalTime` | Giờ–phút–giây–nano | Ngày, offset, múi giờ | `of`, `now`, `parse`, `from` |
| `LocalDateTime` | Ngày và giờ địa phương | Offset và `ZoneId` | `of`, `now`, `parse`, `from` |
| `OffsetDateTime` | Ngày–giờ + độ lệch cố định UTC | Quy tắc múi giờ vùng | `of`, `now`, `parse`, `from` |
| `ZonedDateTime` | Ngày–giờ + `ZoneId` và offset đã xác định | Không phải tên thay thế cho `Instant` | `of`, `now`, `parse`, `from` |
| `Instant` | Thời điểm tuyệt đối trên dòng thời gian | Ngày/giờ địa phương khi chưa gắn zone | `now`, `parse`, `from`, `ofEpochSecond` |
| `YearMonth` | Năm và tháng | Ngày cụ thể | `of`, `now`, `parse`, `from` |
| `MonthDay` | Tháng và ngày, chưa có năm | Năm cụ thể | `of`, `now`, `parse`, `from` |

Ví dụ, **ngày sinh** thường dùng `LocalDate`; **giờ cửa hàng mở** dùng `LocalTime`; **thời điểm log sự kiện** dùng `Instant`; **cuộc hẹn gắn với thành phố** dùng `ZonedDateTime` và zone phù hợp. Không cần thêm offset cho ngày sinh chỉ để có thể tạo bằng `now()`.

Trong mô hình ISO của Java, `LocalDate` sử dụng lịch Gregorian mở rộng về quá khứ (*proleptic Gregorian*). Các factory có kiểm tra tính hợp lệ: `LocalDate.of(2023, 2, 29)` bị từ chối vì năm 2023 không nhuận.

## 3. `of()`: tạo từ thành phần đã biết

### 3.1. `LocalDate.of(...)`, `LocalTime.of(...)`, `LocalDateTime.of(...)`

Khi các thành phần đã được xác định bởi dữ liệu nghiệp vụ, sử dụng `of(...)` để biểu diễn trực tiếp ý định:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(9, 5, 7);
LocalDateTime meeting = LocalDateTime.of(date, time);
~~~

Dòng đầu chứa **2024-02-29**; dòng thứ hai là **09:05:07**; dòng thứ ba là **2024-02-29T09:05:07**. Dạng `T` là ký tự phân cách ngày và giờ trong biểu diễn ISO. `LocalDateTime.of(2024, 2, 29, 9, 5, 7)` cũng có thể dùng nếu các thành phần nằm sẵn trong một lời gọi.

Các overload phổ biến:

- `LocalDate.of(year, month, dayOfMonth)` hoặc `LocalDate.of(year, Month.FEBRUARY, dayOfMonth)`.
- `LocalTime.of(hour, minute)`, `of(hour, minute, second)`, `of(hour, minute, second, nanoOfSecond)`.
- `LocalDateTime.of(year, month, dayOfMonth, hour, minute, ...)` hoặc `of(LocalDate, LocalTime)`.
- `YearMonth.of(2024, 2)` mô tả cả tháng; `MonthDay.of(2, 29)` mô tả ngày/tháng không gắn năm cụ thể.

Java giới hạn các thành phần theo kiểu: tháng 1–12, giờ 0–23, phút/giây thông thường 0–59, nano 0–999999999. Sai giá trị sẽ ném `DateTimeException` ngay tại lúc tạo. Không nên tự chuẩn hóa `LocalTime.of(25, 0)` thành 01:00 ngày hôm sau; muốn cộng giờ, hãy tạo thời gian hợp lệ rồi dùng phép toán như `plusHours(...)` với ngữ nghĩa thích hợp.

### 3.2. Thêm offset hoặc `ZoneId` đúng lúc

Giờ địa phương **không xác định một thời điểm toàn cầu** nếu chưa biết offset/múi giờ. Có thể tạo:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 2, 29, 9, 5, 7);
OffsetDateTime offset = OffsetDateTime.of(local, ZoneOffset.ofHours(7));
ZonedDateTime zoned =
        ZonedDateTime.of(local, ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Ở ngày minh họa, cả hai có offset `+07:00`, nhưng thông tin **khác nhau**: `OffsetDateTime` giữ offset cố định; `ZonedDateTime` giữ danh tính vùng và tra quy tắc vùng khi cần. Chẳng hạn, ở các múi giờ áp dụng daylight saving time, ngày/giờ trong khoảng **gap** có thể không tồn tại; `ZonedDateTime.of(local, zone)` thường điều chỉnh giờ vào sau gap. Giờ trong **overlap** có hai offset hợp lệ và API chọn theo quy tắc mặc định; với nghiệp vụ yêu cầu chính xác một lựa chọn, cần xét `ZoneRules.getValidOffsets(local)` và dùng factory/cách xử lý tường minh.

Đối với **một `Instant` đã biết**, cách chuyển sang múi giờ là `instant.atZone(zone)`, khác về ý nghĩa với gắn múi giờ vào một `LocalDateTime` chưa xác định tức thời.

### 3.3. `Instant` có nhóm `ofEpoch...`

`Instant` không nhận năm/tháng/ngày qua `of(year, month, day)`. Nó tạo một tức thời từ mốc epoch UTC:

~~~java
Instant epoch = Instant.ofEpochSecond(0);       // 1970-01-01T00:00:00Z
Instant next = Instant.ofEpochMilli(1_500);     // 1970-01-01T00:00:01.500Z
LocalDate epochDate = LocalDate.ofEpochDay(0);  // 1970-01-01
~~~

**Giây/millisecond epoch của `Instant`** khác với **ngày epoch của `LocalDate`**. Hai phép tạo dùng hai loại đơn vị khác nhau. Đừng truyền millisecond vào `ofEpochSecond`: giá trị sẽ lệch 1.000 lần. Cũng không được hiểu `LocalDate.ofEpochDay(0)` là một thời điểm lúc 00:00 ở mọi múi giờ.

### 3.4. Ví dụ chạy độc lập cho `of()`

Lưu thành **`OfDemo.java`**:

~~~java
import java.time.*;

public class OfDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(9, 5, 7);
        LocalDateTime local = LocalDateTime.of(date, time);
        OffsetDateTime offset = OffsetDateTime.of(
                local, ZoneOffset.ofHours(7));
        ZonedDateTime zoned = ZonedDateTime.of(
                local, ZoneId.of("Asia/Ho_Chi_Minh"));
        Instant epoch = Instant.ofEpochSecond(0);

        System.out.println("Date: " + date);
        System.out.println("Time: " + time);
        System.out.println("Local: " + local);
        System.out.println("Offset: " + offset);
        System.out.println("Zoned: " + zoned);
        System.out.println("Epoch: " + epoch);

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
~~~

~~~bash
javac OfDemo.java
java OfDemo
~~~

Kết quả stdout trong JDK dùng quy tắc múi giờ cho `Asia/Ho_Chi_Minh` như ở ngày ví dụ:

~~~text
Date: 2024-02-29
Time: 09:05:07
Local: 2024-02-29T09:05:07
Offset: 2024-02-29T09:05:07+07:00
Zoned: 2024-02-29T09:05:07+07:00[Asia/Ho_Chi_Minh]
Epoch: 1970-01-01T00:00:00Z
Invalid date rejected
~~~

Giá trị `ZonedDateTime` sử dụng dữ liệu quy tắc múi giờ của JDK; với một số vùng và ngày lịch sử, dữ liệu này có thể khác giữa các phiên bản tzdb. Để kiểm thử đơn vị độc lập với nguồn dữ liệu đó, chọn `ZoneOffset.UTC` hoặc một offset tĩnh khi điều đó phù hợp với yêu cầu.

## 4. `now()`: đọc đồng hồ khi chương trình chạy

`now()` không có đầu vào chính là yêu cầu lấy **thời điểm hiện tại**. Kết quả phụ thuộc đồng hồ và ngữ cảnh timezone:

~~~java
LocalDate date = LocalDate.now();
LocalTime time = LocalTime.now();
LocalDateTime local = LocalDateTime.now();
Instant instant = Instant.now();

LocalDate inTokyo = LocalDate.now(ZoneId.of("Asia/Tokyo"));
~~~

Các overload cần nhớ:

| Cách gọi | Đồng hồ/zone được dùng | Tính kiểm thử |
|---|---|---|
| `LocalDate.now()` | Đồng hồ hệ thống, timezone mặc định của JVM | Phụ thuộc môi trường và ngày chạy |
| `LocalDate.now(zone)` | Đồng hồ hệ thống, tính ngày theo `zone` | Vẫn phụ thuộc thời điểm thực |
| `LocalDate.now(clock)` | Đồng hồ và zone nằm trong `clock` | Có thể làm cố định |
| `LocalDateTime.now(clock)` | Clock đã chọn; chuyển sang local date/time theo zone clock | Có thể làm cố định |
| `Instant.now(clock)` | Thời điểm do `clock` cung cấp | Có thể làm cố định; zone không đổi chính instant |

`ZoneId.systemDefault()` là cấu hình hệ thống, **không phải luôn UTC**. Một chương trình chạy trên CI/CD, máy phát triển và máy chủ khác timezone có thể cho ngày khác nhau khi cùng gọi `LocalDate.now()`. `Instant.now()` biểu diễn tức thời; khi gọi với hai clock có **cùng instant**, kết quả `Instant` bằng nhau dù clock dùng zone khác nhau.

### 4.1. Dùng `Clock` để kiểm soát `now()` trong kiểm thử

`Clock` là cách chuẩn để tránh phụ thuộc thời gian thực. `Clock.fixed(instant, zone)` giữ nguyên một instant theo zone đã chọn. Ví dụ chạy độc lập, lưu **`NowDemo.java`**:

~~~java
import java.time.*;

public class NowDemo {
    public static void main(String[] args) {
        Instant fixedInstant = Instant.parse("2024-02-29T23:30:00Z");

        Clock utc = Clock.fixed(fixedInstant, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                fixedInstant, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC date: " + LocalDate.now(utc));
        System.out.println("HCM date: " + LocalDate.now(hcm));
        System.out.println("HCM local: " + LocalDateTime.now(hcm));
        System.out.println("Instant: " + Instant.now(hcm));
    }
}
~~~

~~~bash
javac NowDemo.java
java NowDemo
~~~

Stdout cố định cho instant và zone đã chọn:

~~~text
UTC date: 2024-02-29
HCM date: 2024-03-01
HCM local: 2024-03-01T06:30
Instant: 2024-02-29T23:30:00Z
~~~

**Tại sao UTC còn tháng 2 nhưng HCM đã tháng 3?** Vì cùng thời điểm `23:30Z` khi cộng offset `+07:00` là **06:30 ngày hôm sau**. Đây là khác biệt bản chất giữa ngày địa phương và `Instant`.

Trong code ứng dụng, có thể **tiêm `Clock` qua constructor** thay vì gọi `now()` không tham số ở khắp nơi:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public final class DateProvider {
    private final Clock clock;

    public DateProvider(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
~~~

Đoạn `DateProvider` là một lớp riêng: lưu trong **`DateProvider.java`** khi biên dịch. Production có thể truyền `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` hoặc `Clock.systemUTC()` tùy yêu cầu; test truyền `Clock.fixed(...)`. Quyết định zone là quyết định nghiệp vụ, không phải mặc định “UTC luôn đúng” cho mọi `LocalDate`.

### 4.2. Các lỗi thường gặp với `now()`

- Dùng `LocalDate.now()` để gán timestamp log: ngày không lưu được giờ/phút/giây và thứ tự chính xác; nên chọn `Instant.now(clock)` nếu cần thời điểm.
- Gọi `now()` hai lần tại hai dòng quanh ranh giới phút/ngày rồi giả định cùng một ảnh chụp thời gian: có thể lệch. Hãy lấy một `Instant` hoặc một kết quả `now(clock)` làm mốc cho lần xử lý và suy ra các giá trị liên quan.
- Dựa vào timezone máy chủ khi kiểm tra ngày hết hạn/hạn nộp: hãy chỉ rõ zone nghiệp vụ.
- Viết test kỳ vọng ngày của hôm nay cố định: dùng `Clock.fixed`, không dựa vào đồng hồ thực hoặc tùy chỉnh máy toàn cục.

## 5. `parse()`: chuyển văn bản thành giá trị thời gian

`parse()` giải mã **chuỗi có cấu trúc**. Nó không có nghĩa “thử mọi kiểu chuỗi ngày”; mỗi kiểu sử dụng formatter ISO mặc định hoặc formatter do người gọi truyền vào.

~~~java
LocalDate date = LocalDate.parse("2024-02-29");
LocalTime time = LocalTime.parse("09:05:07");
LocalDateTime local = LocalDateTime.parse("2024-02-29T09:05:07");
OffsetDateTime offset =
        OffsetDateTime.parse("2024-02-29T09:05:07+07:00");
Instant instant = Instant.parse("2024-02-29T02:05:07Z");
~~~

Những lời gọi trên có ngữ nghĩa khác nhau:

- `LocalDate.parse` tạo ngày, **không tự gắn timezone**.
- `LocalDateTime.parse` đọc phần ngày–giờ, **không mang offset**; chữ `T` trong ví dụ ISO là dấu phân cách bắt buộc của dạng tương ứng.
- `OffsetDateTime.parse` đòi hỏi offset của dữ liệu đầu vào theo formatter mặc định.
- `ZonedDateTime.parse` có thể đọc zone id và offset, ví dụ `2024-02-29T10:15:30+07:00[Asia/Ho_Chi_Minh]`; zone id có thể kèm quy tắc vùng.
- `Instant.parse` đọc một tức thời. `Z` biểu diễn UTC; dữ liệu ngày giờ địa phương thiếu thông tin để trở thành `Instant`.

**Ví dụ lỗi sai loại dữ liệu:** `LocalDateTime.parse("2024-02-29T09:05:07+07:00")` với formatter ISO mặc định của kiểu đó không biểu diễn offset như một trường thuộc `LocalDateTime`. Khi đầu vào có offset, hãy parse vào `OffsetDateTime` trước rồi chỉ chuyển `toLocalDateTime()` nếu muốn bỏ phần offset có chủ đích.

### 5.1. Parse định dạng tùy chỉnh bằng `DateTimeFormatter`

Khi người dùng nhập `29/02/2024`, formatter ISO mặc định của `LocalDate.parse(String)` không hiểu định dạng `dd/MM/uuuu`. Cần truyền formatter tường minh:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate value = LocalDate.parse("29/02/2024", formatter);
~~~

**Vì sao nên dùng `uuuu`?** Trong pattern của `DateTimeFormatter`:

| Ký tự | Nghĩa | Hệ quả |
|---|---|---|
| `u` | Proleptic year, gồm năm 0 hoặc năm âm | Phù hợp ngày ISO và strict parsing |
| `y` | Year of era | Trong `STRICT`, thiếu era có thể không đủ dữ liệu để tạo `LocalDate` |
| `Y` | Week-based-year | Dễ sai ở đầu/cuối năm nếu nhầm với năm của ngày lịch |
| `M` | Tháng trong năm | Khác phút |
| `m` | Phút trong giờ | Khác tháng |
| `d` | Ngày trong tháng | Khác ngày thứ bao nhiêu trong năm (`D`) |

`ResolverStyle.STRICT` từ chối ngày không tồn tại; `SMART` có thể điều chỉnh một số ngày cuối tháng không hợp lệ; `LENIENT` cho phép chuẩn hóa rộng hơn. Bộ formatter tạo bằng `DateTimeFormatter.ofPattern(...)` mặc định dùng chế độ giải quyết `SMART`, nên nếu nghiệp vụ yêu cầu xác nhận ngày chính xác, nên đặt `STRICT` và dùng các trường phù hợp. Formatter bất biến và có thể tái sử dụng an toàn giữa các luồng.

Ví dụ hoàn chỉnh, lưu thành **`ParseDemo.java`**:

~~~java
import java.time.*;
import java.time.format.*;

public class ParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter vn = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

        LocalDate iso = LocalDate.parse("2024-02-29");
        LocalDate custom = LocalDate.parse("29/02/2024", vn);
        OffsetDateTime offset = OffsetDateTime.parse(
                "2024-02-29T10:15:30+07:00");
        Instant instant = offset.toInstant();

        System.out.println("Same date: " + iso.equals(custom));
        System.out.println("Parsed date: " + custom);
        System.out.println("Instant: " + instant);

        try {
            LocalDate.parse("31/02/2024", vn);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid date text rejected");
        }
    }
}
~~~

~~~bash
javac ParseDemo.java
java ParseDemo
~~~

Stdout:

~~~text
Same date: true
Parsed date: 2024-02-29
Instant: 2024-02-29T03:15:30Z
Invalid date text rejected
~~~

Phần `+07:00` khiến `10:15:30` địa phương tương ứng `03:15:30Z`. `DateTimeParseException` là lớp con của `DateTimeException`, chứa thông tin liên quan dữ liệu không thể parse. Khi báo lỗi đầu vào trong API, nên trả thông điệp an toàn, hữu ích cho người dùng; không tùy tiện nuốt exception rồi thay bằng ngày hiện tại.

### 5.2. Formatter dựng sẵn và miền hỗ trợ

| Formatter | Ví dụ | Mục đích |
|---|---|---|
| `ISO_LOCAL_DATE` | `2024-02-29` | Ngày ISO không offset |
| `BASIC_ISO_DATE` | `20240229` | Ngày ISO dạng cơ bản |
| `ISO_LOCAL_DATE_TIME` | `2024-02-29T10:15:30` | Ngày giờ địa phương |
| `ISO_OFFSET_DATE_TIME` | `2024-02-29T10:15:30+07:00` | Ngày giờ có offset |
| `ISO_ZONED_DATE_TIME` | `2024-02-29T10:15:30+07:00[Asia/Ho_Chi_Minh]` | Ngày giờ có vùng |
| `ISO_INSTANT` | `2024-02-29T03:15:30Z` | Tức thời |
| `ISO_WEEK_DATE` | `2020-W53-5` | Năm tuần ISO, tuần và thứ |
| `ISO_ORDINAL_DATE` | `2024-060` | Ngày thứ bao nhiêu trong năm |

Không ghép chuỗi thủ công để thay formatter khi phải hỗ trợ năm âm, năm trên 9999, locale, offset hoặc field tùy chọn. Các formatter dựng sẵn có ý nghĩa rõ ràng và giúp tránh sai chữ hoa/thường trong pattern.

## 6. `from()`: trích xuất từ `TemporalAccessor`

`TemporalAccessor` là interface cung cấp khả năng đọc các trường thời gian (`ChronoField`) và các query phù hợp. Nhiều kiểu `java.time` triển khai interface này; `DateTimeFormatter.parse(String)` cũng trả `TemporalAccessor`.

Factory `from(TemporalAccessor)` **không parse trực tiếp từ String**. Nó cố lấy từ một đối tượng thời gian đã có các trường cần thiết và tạo kiểu đích. Điểm khác biệt với `of()`: bạn **không truyền từng thành phần**; với `parse()`: bạn **không truyền chuỗi** cho `from()`.

### 6.1. Trích xuất ngày, giờ và instant từ cùng đầu vào có offset

Lưu thành **`FromDemo.java`**:

~~~java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAccessor;

public class FromDemo {
    public static void main(String[] args) {
        TemporalAccessor parsed =
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(
                        "2024-02-29T10:15:30+07:00");

        LocalDate date = LocalDate.from(parsed);
        LocalTime time = LocalTime.from(parsed);
        OffsetDateTime dateTime = OffsetDateTime.from(parsed);
        Instant instant = Instant.from(parsed);

        System.out.println("Date: " + date);
        System.out.println("Time: " + time);
        System.out.println("Offset: " + dateTime);
        System.out.println("Instant: " + instant);

        try {
            LocalDate.from(Instant.parse("2024-02-29T03:15:30Z"));
        } catch (DateTimeException ex) {
            System.out.println("Instant has no local date by itself");
        }

        LocalDate utcDate = instant.atZone(ZoneOffset.UTC).toLocalDate();
        System.out.println("UTC date: " + utcDate);
    }
}
~~~

~~~bash
javac FromDemo.java
java FromDemo
~~~

Stdout:

~~~text
Date: 2024-02-29
Time: 10:15:30
Offset: 2024-02-29T10:15:30+07:00
Instant: 2024-02-29T03:15:30Z
Instant has no local date by itself
UTC date: 2024-02-29
~~~

Cùng một `TemporalAccessor` có offset và ngày giờ có thể tạo ra nhiều góc nhìn: `LocalDate`, `LocalTime`, `OffsetDateTime` hoặc `Instant`. Nhưng một **`Instant` thuần túy** chưa biết đang hiển thị theo múi giờ nào, nên `LocalDate.from(instant)` thất bại. Để lấy ngày, phải chọn zone rõ ràng: `instant.atZone(zone).toLocalDate()` hoặc `LocalDate.ofInstant(instant, zone)`.

### 6.2. Cách dùng `from()` trong mã tổng quát

Khi một API nhận `TemporalAccessor`, bạn có thể yêu cầu kiểu đích:

~~~java
static LocalDate extractDate(TemporalAccessor temporal) {
    return LocalDate.from(temporal);
}
~~~

Đây chỉ là **một phương thức minh họa**, cần đặt trong một lớp Java và import `java.time.LocalDate`, `java.time.temporal.TemporalAccessor` nếu muốn biên dịch. Nó hoạt động khi `temporal` có đủ thông tin ngày ISO; nếu không, `DateTimeException` là kết quả đúng.

Cách gắn converter vào formatter:

~~~java
LocalDate date = DateTimeFormatter.ISO_LOCAL_DATE
        .parse("2024-02-29", LocalDate::from);
~~~

Biểu thức `LocalDate::from` đóng vai trò `TemporalQuery<LocalDate>`. Có thể rút gọn thành `LocalDate.parse("2024-02-29")` khi nguồn đầu vào chỉ là chuỗi ISO và không cần giữ `TemporalAccessor` trung gian.

Một số phép chuyển đổi gần nhau nhưng **không hoàn toàn thay thế nhau**:

- `LocalDate.from(localDateTime)`: lấy thành phần ngày, bỏ giờ.
- `LocalTime.from(localDateTime)`: lấy thành phần giờ, bỏ ngày.
- `Instant.from(offsetDateTime)`: dùng ngày, giờ và offset để xác định thời điểm.
- `LocalDate.from(instant)`: thiếu ngữ cảnh zone nên thất bại.
- `OffsetDateTime.from(localDateTime)`: thiếu offset nên thất bại.
- `ZonedDateTime.from(zonedDateTime)`: lấy cùng thông tin zone/instant theo biểu diễn của nguồn, khi nguồn hỗ trợ.

**Không dùng `from()` như một phép ép kiểu Java** kiểu `(LocalDate) temporal`; đối tượng thực tế có thể là `OffsetDateTime` hoặc kết quả parse formatter, không phải `LocalDate`. `from()` yêu cầu trích xuất trường, còn ép kiểu chỉ kiểm tra đối tượng cùng kiểu runtime.

## 7. Bốn cách có thể tạo cùng một ngày, nhưng ý nghĩa khác nhau

Giả sử cần ngày **2024-02-29**:

~~~java
LocalDate explicit = LocalDate.of(2024, 2, 29);
LocalDate parsed = LocalDate.parse("2024-02-29");
LocalDate extracted = LocalDate.from(
        LocalDateTime.of(2024, 2, 29, 12, 0));
LocalDate fromClock = LocalDate.now(Clock.fixed(
        Instant.parse("2024-02-29T12:00:00Z"),
        ZoneOffset.UTC));
~~~

Cả bốn biến có **giá trị `LocalDate` bằng nhau**, nhưng nguồn gốc không giống nhau:

| Biến | Giá trị đến từ đâu? | Phù hợp khi |
|---|---|---|
| `explicit` | Các thành phần literal/cấu hình đã kiểm tra | Lập lịch theo ngày xác định |
| `parsed` | Chuỗi nhận qua API/file/input | Chuyển đầu vào văn bản |
| `extracted` | `LocalDateTime` sẵn có | Lấy ngày từ một đối tượng temporal |
| `fromClock` | Đồng hồ do ứng dụng cung cấp | Ngày hiện tại theo môi trường/zone có thể kiểm soát |

Trong ứng dụng thực, đừng dùng `now()` để “khôi phục” ngày lịch sử từ một chuỗi và đừng parse một chuỗi `toString()` nếu đã có sẵn một đối tượng typed temporal phù hợp để trích xuất trường.

### 7.1. Sơ đồ chọn nhanh

~~~text
Có giá trị date/time cần tạo
          |
          +-- Đã có thành phần năm/tháng/ngày/giờ? --> of(...)
          |
          +-- Cần thời gian theo đồng hồ hiện tại? --> now(clock/zone)
          |
          +-- Nguồn đầu vào là String? -------------> parse(text, formatter?)
          |
          +-- Đã có TemporalAccessor? --------------> from(temporal)
          |
          +-- Nguồn là epoch hoặc Instant? ---------> ofEpoch... / atZone(...) / ofInstant(...)
~~~

Sơ đồ là một hướng dẫn lựa chọn factory phổ biến; một số kiểu cung cấp các phương thức khác như `atStartOfDay(zone)`, `ofInstant(instant, zone)`, `atOffset(offset)`, hoặc `atZone(zone)`. Hãy ưu tiên phương thức truyền tải đúng ngữ nghĩa thay vì ép mọi phép biến đổi vào một trong bốn tên.

## 8. Sai sót phổ biến và cách sửa

### 8.1. Dùng sai múi giờ

**Sai ý định:** `LocalDate.now()` trong hệ thống tính ngày khuyến mãi theo giờ Việt Nam nhưng JVM chạy theo UTC. **Sửa:** `LocalDate.now(clock)` với clock cấu hình `Asia/Ho_Chi_Minh`, hoặc `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` cho thao tác đơn giản. Trong test, dùng `Clock.fixed`.

### 8.2. Tưởng `LocalDateTime` luôn chỉ một thời điểm

`LocalDateTime.of(2024, 2, 29, 10, 0)` **không tự xác định một `Instant`**. Nếu gắn offset `+07:00` thì khác tức thời khi gắn `Z`. Gắn `ZoneId` qua `atZone(zone)` sẽ áp dụng quy tắc vùng, gồm cả gap/overlap DST. Muốn biết tức thời, cần offset/zone đã được giải quyết.

### 8.3. Dùng formatter sai pattern hoặc thiếu strict validation

`LocalDate.parse("29/02/2024")` không tự nhận mọi thứ tự ngày tháng. Dùng `DateTimeFormatter.ofPattern("dd/MM/uuuu").withResolverStyle(ResolverStyle.STRICT)`. Đừng lẫn `MM` (tháng) với `mm` (phút), hoặc `yyyy` (year of era) với `uuuu` (proleptic year), `YYYY` (năm tuần ISO).

### 8.4. Dùng `from()` khi thiếu trường

`Instant` là thời điểm, không có sẵn ngày địa phương; `LocalDate.from(instant)` không thể tự chọn múi giờ và báo lỗi. **Sửa:** `instant.atZone(zone).toLocalDate()`. Tương tự, `OffsetDateTime.from(localDateTime)` không tự đoán offset; cần cung cấp offset hoặc `ZoneId` theo quy tắc nghiệp vụ.

### 8.5. Dùng `now()` trong test hoặc nhiều bước độc lập

Hai lời gọi `now()` có thể nằm ở hai thời điểm khác nhau. Khi xử lý một giao dịch, lấy `Instant timestamp = Instant.now(clock)` một lần rồi suy ra các biểu diễn ngày/giờ từ đó. Test dùng clock cố định giúp deterministic.

### 8.6. Nuốt ngoại lệ đầu vào không hợp lệ

`of(...)` có thể ném `DateTimeException`; `parse(...)` có thể ném `DateTimeParseException`; `from(...)` có thể ném `DateTimeException` khi nguồn thiếu thông tin. Không tự đổi lỗi thành “hôm nay” vì dễ làm hỏng dữ liệu. Xác minh input ở ranh giới hệ thống và trả lỗi có ý nghĩa.

### 8.7. Nhầm object bất biến với object tự cập nhật

`LocalDate.of(...)`, `LocalDate.now(...)` và `LocalDate.parse(...)` cho giá trị bất biến. Phép `date.plusDays(1)` **trả `LocalDate` khác**; không sửa đối tượng `date` ban đầu. `now()` cũng không làm một biến `LocalDate` tự động thay đổi theo đồng hồ sau khi đã tạo.

## 9. Áp dụng trong thiết kế code

Một API nhận **ngày lịch** nên nhận `LocalDate` sau khi đầu vào đã parse và validate, tránh truyền chuỗi ngày sâu vào tầng nghiệp vụ. Một API ghi nhận **sự kiện xảy ra khi nào** nên nhận `Instant` hoặc đồng hồ `Clock` để chủ động kiểm thử. Một API tái sử dụng **đối tượng temporal** có thể nhận `TemporalAccessor` khi thật sự cần hỗ trợ nhiều loại đầu vào, nhưng phải tài liệu hóa trường nào là bắt buộc.

Ví dụ dịch vụ tạo hạn nộp sau bảy ngày lịch từ ngày hiện tại:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public final class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate deadlineAfterDays(long days) {
        return LocalDate.now(clock).plusDays(days);
    }
}
~~~

Lưu lớp độc lập này trong **`DeadlineService.java`**. Production tiêm `Clock.system(zone)`, test tiêm `Clock.fixed(instant, zone)`. Đối với hạn nộp tính theo **ngày lịch**, `plusDays` diễn đạt đúng hơn phép cộng cứng `days * 86400` giây trên timestamp rồi tự chuyển múi giờ.

Nếu cần parse một chuỗi ngày thành hạn nộp, hãy parse tại tầng nhập dữ liệu:

~~~java
LocalDate specifiedDate =
        LocalDate.parse("2024-02-29", DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Đây là đoạn minh họa đặt trong một phương thức/lớp có import `java.time.LocalDate` và `java.time.format.DateTimeFormatter`. Không cần `from()` trong trường hợp đầu vào đã là chuỗi ngày ISO thuần.

## 10. Tự kiểm tra

**Câu 1.** Có năm, tháng, ngày được truyền riêng từ ba trường API, nên dùng `of()`, `parse()` hay `now()`?  
**Đáp án:** `LocalDate.of(year, month, day)`. Dùng `parse()` nếu nguồn là chuỗi theo formatter; dùng `now()` khi cần ngày hiện tại.

**Câu 2.** Tại sao `LocalDate.now()` có thể khác giữa máy developer và máy CI ở cùng một instant?  
**Đáp án:** Vì JVM có timezone mặc định khác nhau, dẫn đến ngày địa phương khác nhau. Dùng `Clock` hoặc `ZoneId` được chọn rõ.

**Câu 3.** Đọc `29/02/2024` bằng factory nào?  
**Đáp án:** `LocalDate.parse(text, DateTimeFormatter.ofPattern("dd/MM/uuuu").withResolverStyle(ResolverStyle.STRICT))`.

**Câu 4.** Tại sao `LocalDate.from(Instant.now())` không phải phép chuyển đổi đúng?  
**Đáp án:** `Instant` không cung cấp ngày địa phương khi chưa có zone. Dùng `instant.atZone(zone).toLocalDate()` (hoặc `LocalDate.ofInstant(instant, zone)`).

**Câu 5.** Khi có `OffsetDateTime`, làm sao lấy ngày, và làm sao lấy thời điểm tuyệt đối?  
**Đáp án:** `offsetDateTime.toLocalDate()` hoặc `LocalDate.from(offsetDateTime)` cho ngày; `offsetDateTime.toInstant()` hoặc `Instant.from(offsetDateTime)` cho instant. Hai kết quả chứa thông tin khác nhau.

**Câu 6.** Trong unit test, cần ngày hệ thống luôn là `2024-02-29` UTC, tạo bằng cách nào?  
**Đáp án:** `Clock.fixed(Instant.parse("2024-02-29T12:00:00Z"), ZoneOffset.UTC)`, sau đó `LocalDate.now(clock)`.

## 11. Ghi nhớ

- **`of()`**: tạo từ các thành phần xác định; kiểm tra phạm vi và tính hợp lệ.
- **`now()`**: lấy giá trị từ clock; phải chủ động chọn zone khi cần ngày/giờ địa phương, dùng `Clock.fixed` để test.
- **`parse()`**: chuyển chuỗi theo ISO hoặc formatter tùy chỉnh; đảm bảo đúng pattern và chế độ validation.
- **`from()`**: trích xuất các trường từ `TemporalAccessor`; chỉ thành công nếu nguồn có đủ dữ liệu cho kiểu đích.
- **Chọn kiểu đúng trước**: `LocalDate` cho ngày lịch, `LocalDateTime` cho giờ địa phương, `OffsetDateTime`/`ZonedDateTime` khi có offset/zone, `Instant` cho tức thời. Cùng một chuỗi hoặc thời điểm có thể cho biểu diễn khác nhau tùy các thông tin được cung cấp.
