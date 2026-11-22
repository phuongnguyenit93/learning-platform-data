# Đọc dữ liệu bằng get...() và kiểm tra bằng is...() trong java.time

Khi làm việc với Java Date-Time API (`java.time`), ta thường có hai nhu cầu: **lấy thông tin bên trong một đối tượng ngày giờ** và **kiểm tra một điều kiện về ngày giờ**. Nhiều phương thức được đặt tên theo hai họ dễ nhận biết:

- `get...()`: trả về một thuộc tính hoặc thành phần, chẳng hạn năm, tháng, giờ, nano giây, độ lệch UTC.
- `is...()`: thường trả về `boolean`, dùng để trả lời một câu hỏi đúng/sai, chẳng hạn “có phải năm nhuận?”, “ngày này có trước ngày kia?”, “kiểu ngày giờ này có hỗ trợ trường đang hỏi?”.

Đây là **quy ước đặt tên thường gặp**, không phải luật áp dụng cho mọi lớp. Mỗi kiểu trong `java.time` mô hình hóa một loại dữ liệu khác nhau, nên phương thức có thể xuất hiện ở lớp này nhưng không có ở lớp khác. Chẳng hạn, `LocalDate` biết ngày tháng nhưng không có giờ; `Instant` mô tả thời điểm trên trục thời gian nhưng không tự mang múi giờ để cung cấp “giờ địa phương”.

## 1. Đọc đúng kiểu dữ liệu, đúng thành phần

### Những kiểu thường gặp trong `java.time`

| Kiểu | Biểu diễn | Ví dụ phương thức đọc |
|---|---|---|
| `LocalDate` | Ngày theo lịch ISO, không có giờ/múi giờ | `getYear()`, `getMonth()`, `getDayOfMonth()` |
| `LocalTime` | Giờ trong ngày, không có ngày/múi giờ | `getHour()`, `getMinute()`, `getSecond()`, `getNano()` |
| `LocalDateTime` | Ngày và giờ địa phương, chưa xác định múi giờ | Các getter của ngày và giờ |
| `OffsetDateTime` | Ngày giờ kèm độ lệch cố định so với UTC | `getOffset()` và các getter ngày giờ |
| `ZonedDateTime` | Ngày giờ kèm vùng múi giờ và quy tắc offset | `getZone()`, `getOffset()`, getter ngày giờ |
| `Instant` | Một thời điểm trên timeline | `getEpochSecond()`, `getNano()` |
| `YearMonth` | Năm và tháng | `getYear()`, `getMonth()` |
| `MonthDay` | Tháng và ngày trong tháng | `getMonth()`, `getDayOfMonth()` |

Ví dụ tạo ba đối tượng:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
LocalDateTime dateTime = LocalDateTime.of(date, time);
~~~

`LocalDate.of(...)` nhận năm, tháng dạng số, ngày; `LocalTime.of(...)` nhận giờ, phút, giây và nano giây trong giây. Đối tượng được tạo chỉ khi giá trị đầu vào hợp lệ: `LocalDate.of(2023, 2, 29)` sẽ ném `DateTimeException` vì 2023 không có ngày 29/02.

### Đọc thành phần ngày bằng `LocalDate`

| Phương thức | Giá trị cho `2024-02-29` | Ý nghĩa |
|---|---|---|
| `getYear()` | `2024` | Năm |
| `getMonth()` | `Month.FEBRUARY` | Enum `Month` |
| `getMonthValue()` | `2` | Tháng dạng số, 1–12 |
| `getDayOfMonth()` | `29` | Ngày trong tháng |
| `getDayOfWeek()` | `DayOfWeek.THURSDAY` | Enum ngày trong tuần |
| `getDayOfYear()` | `60` | Ngày thứ 60 của năm nhuận 2024 |

Cần phân biệt `getMonth()` với `getMonthValue()`: cách thứ nhất trả về **enum** để code dễ diễn đạt, cách thứ hai trả về **số nguyên** để xuất dữ liệu hoặc tính toán. Tương tự, `getDayOfWeek()` trả về `DayOfWeek`, không trả trực tiếp chữ tiếng Việt hay con số.

~~~java
Month month = date.getMonth(); // FEBRUARY
int monthNumber = month.getValue(); // 2
DayOfWeek dayOfWeek = date.getDayOfWeek(); // THURSDAY
int isoDayNumber = dayOfWeek.getValue(); // 4
~~~

Theo `DayOfWeek.getValue()` của ISO, **thứ Hai = 1** và **Chủ nhật = 7**. Không mặc nhiên dùng chỉ số 0–6 hoặc 1–7 kiểu Chủ nhật đầu tuần của thư viện khác. Muốn **hiển thị tên theo ngôn ngữ**, hãy dùng các API định dạng/language locale; tên enum tiếng Anh là giá trị máy đọc được.

### Đọc thành phần giờ bằng `LocalTime`

| Phương thức | Giá trị từ `14:05:06.123` | Miền giá trị |
|---|---:|---|
| `getHour()` | `14` | 0–23 |
| `getMinute()` | `5` | 0–59 |
| `getSecond()` | `6` | 0–59 |
| `getNano()` | `123_000_000` | 0–999.999.999 |

`getNano()` là số **nano giây nằm bên trong giây hiện tại**, không phải tổng nano giây kể từ mốc epoch. `123_000_000` ns tương đương `123` mili giây. `LocalDateTime` có getter ngày và getter giờ, nhưng **không có thời điểm UTC duy nhất** nếu chưa gắn độ lệch hay múi giờ.

### Múi giờ và timestamp

~~~java
Instant instant = Instant.parse("2024-02-29T12:00:00Z");
long epochSeconds = instant.getEpochSecond(); // 1709208000
int nanoOfSecond = instant.getNano(); // 0

ZonedDateTime inHcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
int hour = inHcm.getHour(); // 19
ZoneId zone = inHcm.getZone(); // Asia/Ho_Chi_Minh
ZoneOffset offset = inHcm.getOffset(); // +07:00
~~~

Một `Instant` và nhiều `ZonedDateTime` có thể chỉ **cùng một thời điểm**, nhưng getter giờ/ngày địa phương khác nhau. `getZone()` lấy định danh vùng múi giờ, còn `getOffset()` lấy độ lệch UTC **đang áp dụng tại thời điểm đó**. Offset có thể thay đổi theo lịch sử hoặc giờ mùa hè tại các vùng áp dụng quy tắc đó.

## 2. Kiểm tra điều kiện với `is...()`

### So sánh ngày hoặc thời điểm

| Phương thức | Câu hỏi được trả lời | Lưu ý |
|---|---|---|
| `a.isBefore(b)` | `a` có sớm hơn `b`? | `false` nếu bằng nhau |
| `a.isAfter(b)` | `a` có muộn hơn `b`? | `false` nếu bằng nhau |
| `a.isEqual(b)` | `a` có cùng ngày/thời điểm theo hợp đồng kiểu? | Có ở một số kiểu; xem riêng `ZonedDateTime`/`LocalDate` |
| `a.equals(b)` | Hai đối tượng có bằng nhau theo định nghĩa của lớp? | Có thể xét nhiều thuộc tính hơn chỉ thời điểm thực |

~~~java
LocalDate examDate = LocalDate.of(2024, 2, 29);
LocalDate deadline = LocalDate.of(2024, 3, 1);

boolean early = examDate.isBefore(deadline); // true
boolean late = examDate.isAfter(deadline); // false
boolean sameDay = examDate.isEqual(deadline); // false
~~~

**Điểm cốt lõi:** `isBefore`/`isAfter` luôn là so sánh **nghiêm ngặt**: bằng nhau thì cả hai trả về `false`. Khi yêu cầu “trước hoặc đúng hạn”, có thể viết `!date.isAfter(deadline)` nếu `date` và `deadline` là các giá trị phù hợp để so sánh.

Với `LocalDate`, so sánh theo ngày trên lịch ISO; với `LocalTime`, theo giờ trong ngày; với `LocalDateTime`, theo ngày giờ **địa phương**. `LocalDateTime` không có ngữ cảnh vùng múi giờ nên chưa đủ để so sánh **thời điểm xảy ra toàn cầu** giữa hai địa điểm. Với `Instant`, `OffsetDateTime` và `ZonedDateTime`, so sánh thời điểm dựa trên timeline.

**`isEqual(...)` và `equals(...)` có thể khác nhau.** Hai `ZonedDateTime` ở hai vùng múi giờ khác nhau có thể cùng một `Instant`: `isEqual` trả về `true`, nhưng `equals` trả về `false` vì thông tin ngày giờ/zone của hai đối tượng khác nhau. Khi nghiệp vụ hỏi “có xảy ra cùng một lúc không?”, có thể chuyển cả hai về `Instant` hoặc dùng `isEqual` ở loại hỗ trợ.

### Kiểm tra năm nhuận và ngày hợp lệ

~~~java
LocalDate leapDate = LocalDate.of(2024, 2, 29);
boolean leap = leapDate.isLeapYear(); // true

boolean in2023 = MonthDay.of(2, 29).isValidYear(2023); // false
boolean in2024 = YearMonth.of(2024, 2).isValidDay(29); // true
~~~

- `LocalDate.isLeapYear()` cho biết năm của ngày đó có phải năm nhuận theo lịch ISO mở rộng hay không.
- `Year.isLeap(year)` kiểm tra năm nhuận theo dạng static nếu chỉ có năm.
- `MonthDay.isValidYear(year)` kiểm tra một tháng/ngày có hợp lệ với năm đang xét (rất hữu ích với 29/02).
- `YearMonth.isValidDay(day)` kiểm tra số ngày có tồn tại trong tháng và năm đó hay không.
- `YearMonth.lengthOfMonth()` và `LocalDate.lengthOfMonth()` trả về số ngày của tháng, không phải boolean.

Theo ISO, năm nhuận thường chia hết cho 4, trừ năm chia hết cho 100 nếu không chia hết cho 400; các API lịch ISO áp dụng quy tắc lịch Gregorian mở rộng sang cả các năm rất xa. Đối với dữ liệu lịch sử, quy tắc lịch thực tế từng vùng có thể khác.

Nếu đầu vào là ngày tháng rời rạc, **đừng tự tạo `LocalDate` từ dữ liệu chưa hợp lệ rồi hy vọng `isValidDay` sẽ phát hiện**. `LocalDate.of(...)` có thể ném ngoại lệ ngay trong lúc tạo; có thể dùng `YearMonth.isValidDay` trước, hoặc xử lý `DateTimeException` ở ranh giới nhận dữ liệu.

### Kiểm tra khả năng hỗ trợ trường thời gian

Đôi khi chỉ biết một đối tượng dưới dạng `TemporalAccessor`, ta cần xác minh nó có trường muốn đọc hay không:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
boolean daySupported = date.isSupported(ChronoField.DAY_OF_MONTH); // true
boolean hourSupported = date.isSupported(ChronoField.HOUR_OF_DAY); // false
~~~

`isSupported(TemporalField)` hỏi **kiểu dữ liệu này có hỗ trợ đọc trường đó hay không**. Nó không hỏi “ngày này có hợp lệ không?” và không tự kiểm tra nội dung người dùng nhập.

Với `LocalDate`, `YEAR` và `DAY_OF_MONTH` được hỗ trợ nhưng `HOUR_OF_DAY` không. Với `Instant`, `INSTANT_SECONDS` được hỗ trợ. Khi gọi getter cho trường không được hỗ trợ, phương thức thường ném `UnsupportedTemporalTypeException`.

Có một trường hợp dễ nhầm: `Instant.isSupported(ChronoField.INSTANT_SECONDS)` là `true`, nhưng **`instant.get(ChronoField.INSTANT_SECONDS)` vẫn không dùng được** vì trường này cần biểu diễn `long`, vượt phạm vi API `get(...)` kiểu `int`; dùng `instant.getLong(ChronoField.INSTANT_SECONDS)` hoặc `instant.getEpochSecond()`.

## 3. Khi nào dùng getter tên riêng, `get(field)`, và `getLong(field)`?

`java.time` cung cấp hai cách đọc giá trị:

1. **Getter tên riêng:** `date.getYear()`, `time.getHour()`, `instant.getEpochSecond()`. Dễ đọc, an toàn về kiểu giá trị và thường là lựa chọn đầu tiên.
2. **Truy vấn trường thời gian:** `temporal.get(ChronoField.YEAR)` hoặc `temporal.getLong(ChronoField.INSTANT_SECONDS)`. Hữu ích khi làm việc với `TemporalAccessor`, công cụ tổng quát hoặc trường được lựa chọn động.

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

int year = date.getYear(); // 2024
int yearFromField = date.get(ChronoField.YEAR); // 2024
long epochDay = date.getLong(ChronoField.EPOCH_DAY);
// EPOCH_DAY là số ngày tính từ 1970-01-01, KHÔNG phải epoch seconds.

Instant instant = Instant.parse("2024-02-29T12:00:00Z");
long seconds = instant.getLong(ChronoField.INSTANT_SECONDS); // 1709208000
~~~

`get(field)` trả về `int`, chỉ dùng cho những trường có thể biểu diễn hợp lệ dưới dạng `int`; `getLong(field)` trả về `long`. **Không phải mọi trường được hỗ trợ đều có thể dùng `get(field)`**, và `getLong(field)` cũng sẽ thất bại nếu bản thân kiểu không hỗ trợ trường đó.

Mẫu phòng tránh lỗi khi xử lý `TemporalAccessor` không biết kiểu cụ thể:

~~~java
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;

// Minh họa bên trong phương thức; temporal đã được truyền vào.
if (temporal.isSupported(ChronoField.YEAR)) {
    long year = temporal.getLong(ChronoField.YEAR);
    System.out.println("year = " + year);
}
~~~

Lưu ý: đối với `ChronoField.YEAR`, getter riêng `LocalDate.getYear()` phù hợp hơn khi ta biết chắc đầu vào là `LocalDate`. Việc liên tục chọn trường bằng chuỗi tên hoặc ép kiểu không cần thiết thường làm code khó hiểu.

## 4. Ví dụ Java 17 hoàn chỉnh: đọc và kiểm tra nhiều kiểu

Lưu thành **`DateTimeAccessDemo.java`**:

~~~java
import java.time.*;
import java.time.temporal.ChronoField;

public class DateTimeAccessDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
        LocalDateTime dateTime = LocalDateTime.of(date, time);

        System.out.println("year = " + date.getYear());
        System.out.println("month = " + date.getMonth());
        System.out.println("month number = " + date.getMonthValue());
        System.out.println("day = " + date.getDayOfMonth());
        System.out.println("day of week = " + date.getDayOfWeek());
        System.out.println("day of year = " + date.getDayOfYear());
        System.out.println("leap year = " + date.isLeapYear());
        System.out.println("length of month = " + date.lengthOfMonth());
        System.out.println("hour = " + time.getHour());
        System.out.println("minute = " + time.getMinute());
        System.out.println("second = " + time.getSecond());
        System.out.println("nano = " + time.getNano());
        System.out.println("dateTime hour = " + dateTime.getHour());

        System.out.println("before Mar 1 = "
                + date.isBefore(LocalDate.of(2024, 3, 1)));
        System.out.println("after Feb 28 = "
                + date.isAfter(LocalDate.of(2024, 2, 28)));
        System.out.println("same day before? = " + date.isBefore(date));
        System.out.println("supports DAY_OF_MONTH = "
                + date.isSupported(ChronoField.DAY_OF_MONTH));
        System.out.println("supports HOUR_OF_DAY = "
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("Feb 29 valid in 2023 = "
                + MonthDay.of(2, 29).isValidYear(2023));
        System.out.println("Feb 29 valid in 2024 = "
                + YearMonth.of(2024, 2).isValidDay(29));

        Instant instant = Instant.parse("2024-02-29T12:00:00Z");
        System.out.println("instant seconds = " + instant.getEpochSecond());
        System.out.println("getLong seconds = "
                + instant.getLong(ChronoField.INSTANT_SECONDS));
        System.out.println("get(INSTANT_SECONDS) supported as int = "
                + instant.isSupported(ChronoField.INSTANT_SECONDS));

        ZonedDateTime utc = instant.atZone(ZoneOffset.UTC);
        ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("UTC time = " + utc.toLocalTime());
        System.out.println("HCM time = " + hcm.toLocalTime());
        System.out.println("same instant = " + utc.isEqual(hcm));
        System.out.println("zoned objects equal = " + utc.equals(hcm));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DateTimeAccessDemo.java
java DateTimeAccessDemo
~~~

Đầu ra đã kiểm tra bằng `javac --release 17`:

~~~text
year = 2024
month = FEBRUARY
month number = 2
day = 29
day of week = THURSDAY
day of year = 60
leap year = true
length of month = 29
hour = 14
minute = 5
second = 6
nano = 123000000
dateTime hour = 14
before Mar 1 = true
after Feb 28 = true
same day before? = false
supports DAY_OF_MONTH = true
supports HOUR_OF_DAY = false
Feb 29 valid in 2023 = false
Feb 29 valid in 2024 = true
instant seconds = 1709208000
getLong seconds = 1709208000
get(INSTANT_SECONDS) supported as int = true
UTC time = 12:00
HCM time = 19:00
same instant = true
zoned objects equal = false
~~~

**Đọc kết quả:** năm 2024 nhuận nên 29/02 tồn tại và là ngày thứ 60; giờ `14:05:06.123` có phần nano bằng `123_000_000`; `LocalDate` không hỗ trợ `HOUR_OF_DAY`. Hai `ZonedDateTime` cùng chỉ thời điểm 12:00 UTC, nhưng ở TP.HCM hiển thị 19:00: `isEqual` là `true`, `equals` là `false` vì hai biểu diễn mang thông tin vùng múi giờ khác nhau.

Dòng `get(INSTANT_SECONDS) supported as int = true` chỉ là cách đặt nhãn minh họa cho kết quả của **`isSupported(...)`**. Nó không nói rằng `get(...)` thật sự đọc được trường này bằng `int`. Chính vì vậy chương trình đọc giá trị giây bằng `getLong(...)`.

## 5. Những lỗi thường gặp khi dùng `get...()` và `is...()`

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| Dùng `date.getMonth() == 2` | `getMonth()` trả về enum `Month`, không phải `int` | Dùng `date.getMonthValue() == 2` hoặc `date.getMonth() == Month.FEBRUARY` |
| Hiểu `getDayOfWeek()` là số ngày trong tháng | Nó là enum thứ trong tuần | Dùng `getDayOfMonth()` cho ngày 1–31; `getDayOfWeek()` cho thứ |
| Cho rằng `getNano()` là epoch nanoseconds | Đây là nano nằm trong một giây | Với timestamp, dùng `Instant` và hợp đồng đơn vị phù hợp |
| Gọi `LocalDate.getHour()` | Ngày không mang giờ | Dùng `LocalTime` hoặc `LocalDateTime` |
| Cho rằng `isSupported(...)` xác nhận ngày nhập đúng | Nó chỉ xác nhận một trường có thể được truy cập | Dùng `YearMonth.isValidDay(...)` hoặc xử lý `DateTimeException` |
| Gọi `get(ChronoField.INSTANT_SECONDS)` vì `isSupported` trả true | Trường có thể lớn hơn phạm vi `int` | Dùng `getLong(...)` hoặc `Instant.getEpochSecond()` |
| Coi `isBefore` bằng “trước hoặc bằng” | Đây là so sánh nghiêm ngặt | Dùng `!isAfter(...)` nếu muốn bao gồm bằng nhau |
| So sánh hai `LocalDateTime` như hai timestamp toàn cầu | Không có offset/zone để xác định cùng trục thời gian | Quy đổi sang `Instant` trong ngữ cảnh vùng múi giờ đã xác định |
| Cho rằng `ZonedDateTime.equals` chỉ xét timestamp | Nó còn xét biểu diễn ngày giờ và vùng múi giờ | So sánh cùng thời điểm bằng `isEqual(...)` hoặc `toInstant().equals(...)` |
| Nghĩ getter có thể thay đổi ngày giờ | `java.time` chủ yếu dùng đối tượng immutable | `with...()`, `plus...()`, `minus...()` tạo giá trị mới; gán biến nếu cần lưu kết quả |

Trong nghiệp vụ thật, cần đặt câu hỏi **đang kiểm tra ngày lịch, giờ trong ngày hay thời điểm thực?** Ví dụ hạn đăng ký kết thúc vào ngày 31/12 theo lịch địa phương có thể được xử lý bằng `LocalDate`; hạn giao dịch kết thúc ở một thời điểm chính xác phải được quy về `Instant`/zone có quy tắc. Lựa chọn kiểu đúng trước, sau đó mới chọn getter và phép kiểm tra.

## 6. Tự luyện tập

1. Cho `LocalDate.of(2024, 12, 31)`. Lấy năm, số tháng, enum tháng và thứ trong tuần bằng những getter nào? **`getYear()`, `getMonthValue()`, `getMonth()`, `getDayOfWeek()`**.
2. Với `LocalTime.of(8, 30, 0)`, `getHour()` và `getNano()` trả gì? **`8` và `0`**.
3. `LocalDate.of(2024, 2, 29).isBefore(LocalDate.of(2024, 2, 29))` trả gì? **`false`** vì hai ngày bằng nhau.
4. Kiểm tra 29/02 hợp lệ ở năm 2023 bằng API nào? **`MonthDay.of(2, 29).isValidYear(2023)`** trả `false`; hoặc `YearMonth.of(2023, 2).isValidDay(29)`.
5. `date.isSupported(ChronoField.HOUR_OF_DAY)` kiểm tra điều gì? **Khả năng đọc trường giờ từ đối tượng `date`**, không kiểm tra tính hợp lệ của ngày.
6. Nếu hai `ZonedDateTime` cùng `Instant` nhưng zone khác nhau, hàm nào kiểm tra cùng thời điểm? **`isEqual(...)`** hoặc **`toInstant().equals(...)`**.
7. Có thể dùng `instant.get(ChronoField.INSTANT_SECONDS)` không, khi `isSupported(...) == true`? **Không nên**: trường cần `long`; dùng `getLong(...)` hoặc `getEpochSecond()`.

**Ghi nhớ:** Getter cho biết đối tượng **chứa thông tin gì**, `is...()` giúp trả lời một **điều kiện cụ thể**. Luôn xác định đúng kiểu `java.time`, hiểu đơn vị/trường dữ liệu, và phân biệt so sánh ngày giờ địa phương với so sánh thời điểm trên trục UTC.

### Tài liệu tham khảo

- [Java SE 17 — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 17 — `LocalTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — `TemporalAccessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAccessor.html)
