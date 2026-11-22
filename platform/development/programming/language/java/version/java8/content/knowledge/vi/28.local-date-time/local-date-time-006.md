# Đọc trường và kiểm tra giá trị hợp lệ — Ngày giờ cục bộ trong Java

`LocalDate`, `LocalTime` và `LocalDateTime` thuộc API `java.time` của Java 8, tiếp tục được sử dụng trong các JDK hiện đại. Chúng mô hình hóa **ngày theo lịch ISO**, **giờ trong một ngày** và **ngày + giờ theo đồng hồ địa phương**. Việc chọn đúng kiểu sẽ khiến những trường có thể đọc và kiểm tra khác nhau một cách rõ ràng.

Chủ đề này tập trung vào: đọc thành phần ngày/giờ; dùng getter chuyên biệt và `ChronoField`; xác định ngày nhuận, số ngày trong tháng; phân biệt miền số hợp lệ với tổ hợp ngày hợp lệ; dùng factory `of` và parse `STRICT`; kiểm tra điều kiện nghiệp vụ như “ngày hẹn trong 30 ngày tới”; và nhận biết ngoại lệ từ đầu vào không hợp lệ. Các đoạn chương trình đầy đủ dùng Java 17+, còn phần lớn API cốt lõi đã có từ Java 8.

## 1. Ba mức độ hợp lệ: cú pháp, lịch/giờ, nghiệp vụ

Một dữ liệu ngày giờ không chỉ cần khớp định dạng mà còn cần có ý nghĩa:

1. **Hợp lệ về cú pháp**: ví dụ chuỗi `"29/02/2024"` tuân theo mẫu `dd/MM/uuuu`.
2. **Hợp lệ theo lịch và đồng hồ**: tháng 2 có ngày 29 **chỉ ở năm nhuận**; tháng 4 không có ngày 31; `LocalTime.of(24,0)` không hợp lệ vì `LocalTime` dùng giờ 0–23.
3. **Hợp lệ theo nghiệp vụ**: một ngày đã tồn tại trên lịch vẫn có thể nằm ngoài thời hạn đăng ký hoặc vào ngày hệ thống không phục vụ.

Ví dụ:

| Giá trị nhập | Đúng miền riêng từng trường? | Tạo `LocalDate`/`LocalTime` thành công? | Vì sao? |
| --- | --- | --- | --- |
| 29/02/2024 | Có | Có | Năm 2024 là năm nhuận |
| 29/02/2023 | Có đối với tháng 2 và ngày 29 nhìn riêng | **Không** | Năm 2023 không nhuận |
| 31/04/2024 | Có đối với tháng 4 và ngày 31 nhìn riêng | **Không** | Tháng 4 chỉ có 30 ngày |
| 23:59:59 | Có | Có | Giờ/phút/giây trong miền |
| 24:00 | **Không** theo `LocalTime.of` | **Không** | Giờ 24 nằm ngoài 0–23 |
| 10:60 | **Không** | **Không** | Phút 60 nằm ngoài 0–59 |

`LocalDate.of`/`LocalTime.of` kiểm tra cấu trúc giá trị, còn các quy tắc kiểu “chỉ đặt lịch từ ngày hôm nay” là trách nhiệm của service ứng dụng. **Đừng trộn lỗi lịch với lỗi nghiệp vụ** thành một lý do không rõ ràng.

## 2. Các getter thông dụng theo kiểu

| Trường | `LocalDate` | `LocalTime` | `LocalDateTime` |
| --- | --- | --- | --- |
| Năm | `getYear()` | Không | `getYear()` |
| Tháng dạng enum | `getMonth()` | Không | `getMonth()` |
| Tháng dạng số | `getMonthValue()` | Không | `getMonthValue()` |
| Ngày trong tháng | `getDayOfMonth()` | Không | `getDayOfMonth()` |
| Ngày trong năm | `getDayOfYear()` | Không | `getDayOfYear()` |
| Thứ trong tuần | `getDayOfWeek()` | Không | `getDayOfWeek()` |
| Giờ | Không | `getHour()` | `getHour()` |
| Phút | Không | `getMinute()` | `getMinute()` |
| Giây | Không | `getSecond()` | `getSecond()` |
| Nanosecond trong giây | Không | `getNano()` | `getNano()` |
| Lấy riêng phần ngày hoặc giờ | Chính nó | Chính nó | `toLocalDate()` / `toLocalTime()` |

**`getMonth()` khác `getMonthValue()`:** phương thức đầu trả enum `Month` như `FEBRUARY`; phương thức sau trả int `2`.

**`getDayOfWeek()` trả enum `DayOfWeek`**, không phải số từ lớp `Calendar`. `getDayOfWeek().getValue()` theo chuẩn ISO: **Monday = 1, Sunday = 7**. Không suy ra mọi API khác đều có cùng quy ước số thứ.

Cả ba kiểu là **immutable, thread-safe, value-based**. Phương thức `plusDays`/`plusHours`/`withMonth` tạo giá trị mới, không sửa biến đang giữ giá trị ban đầu. Dùng `equals` để so giá trị, không dựa vào so sánh identity `==`.

## 3. Đọc trường ngày bằng `LocalDate`

Tạo một ngày ISO theo năm/tháng/ngày:

```java
LocalDate date = LocalDate.of(2024, 2, 29);

int year = date.getYear();             // 2024
Month month = date.getMonth();         // FEBRUARY
int monthNumber = date.getMonthValue();// 2
int day = date.getDayOfMonth();        // 29
int dayOfYear = date.getDayOfYear();   // 60
DayOfWeek weekday = date.getDayOfWeek();// THURSDAY
```

Đây là đoạn mã **đặt trong phương thức**, giả định đã import `java.time.*`. Thứ trong tuần là `THURSDAY`, ngày thứ 60 trong năm nhuận 2024.

`LocalDate` còn có các method:
- `lengthOfMonth()`: số ngày của **tháng và năm đang lưu**.
- `lengthOfYear()`: `365` hoặc `366`.
- `isLeapYear()`: năm của ngày hiện tại là năm nhuận hay không.
- `toEpochDay()`: số **ngày lịch** tính từ ngày ISO `1970-01-01`. Đây **không phải** epoch seconds/milliseconds của một `Instant`.
- `getDayOfWeek()`: dùng trực tiếp cho logic cuối tuần hoặc lịch định kỳ.

**Không thể gọi `LocalDate.getHour()`.** Một giá trị `LocalDate` không chứa giờ, không có ý nghĩa “giờ mặc định 0” để đọc. Nếu cần giờ, tạo `LocalTime` riêng hoặc ghép thành `LocalDateTime`.

### Lịch ISO và năm nhuận

Năm nhuận thông thường chia hết cho 4, trừ những năm tròn thế kỷ không chia hết cho 400. Không cần tự lập lại thuật toán trong từng service: dùng `Year.isLeap` hoặc `LocalDate.isLeapYear`. Các factory `LocalDate.of` đã hiểu cấu trúc lịch ISO, vì vậy tránh tự ghép năm/tháng/ngày bằng phép cộng giây hoặc mảng ngày cố định.

## 4. Chương trình Java: đọc trường và tính ngày nhuận

Tạo tệp `DateFieldsDemo.java`:

```java
import java.time.LocalDate;

public class DateFieldsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        System.out.println("date = " + date);
        System.out.println("year = " + date.getYear());
        System.out.println("month = " + date.getMonth());
        System.out.println("month value = " + date.getMonthValue());
        System.out.println("day = " + date.getDayOfMonth());
        System.out.println("day of year = " + date.getDayOfYear());
        System.out.println("day of week = " + date.getDayOfWeek());
        System.out.println("month length = " + date.lengthOfMonth());
        System.out.println("year length = " + date.lengthOfYear());
        System.out.println("leap year = " + date.isLeapYear());
        System.out.println("next day = " + date.plusDays(1));
        System.out.println("original = " + date);
    }
}
```

```bash
javac -encoding UTF-8 DateFieldsDemo.java
java DateFieldsDemo
```

```text
date = 2024-02-29
year = 2024
month = FEBRUARY
month value = 2
day = 29
day of year = 60
day of week = THURSDAY
month length = 29
year length = 366
leap year = true
next day = 2024-03-01
original = 2024-02-29
```

`next day` đã sang 1/3/2024, nhưng `original` vẫn là 29/2. `LocalDate` bất biến; quên gán kết quả `date = date.plusDays(1)` khi muốn thay biến là một lỗi lập trình thường gặp.

## 5. Đọc `LocalTime` và ý nghĩa nanosecond

`LocalTime` chứa giờ trong ngày không gắn ngày hoặc múi giờ. Nó hỗ trợ các trường:

| Thành phần | Miền tạo bằng `LocalTime.of` |
| --- | --- |
| `hour` | `0..23` |
| `minute` | `0..59` |
| `second` | `0..59` |
| `nanoOfSecond` | `0..999_999_999` |

Ví dụ:

```java
LocalTime time = LocalTime.of(23, 59, 58, 123_000_000);

time.getHour();       // 23
time.getMinute();     // 59
time.getSecond();     // 58
time.getNano();       // 123000000
time.toSecondOfDay(); // 86398
time.toNanoOfDay();   // 86398123000000L
```

`getNano()` trả **nano trong giây hiện tại**. `toNanoOfDay()` trả **tổng nano từ đầu ngày** nên dùng `long`. `toSecondOfDay()` là tổng giây từ `00:00:00`, không tính phần nano. Giá trị `123_000_000` nano tương đương 123 milli giây, nên cách in ISO của LocalTime ở đây là `23:59:58.123`.

`LocalTime.MIN` là `00:00`; `LocalTime.MAX` là `23:59:59.999999999`. Không tự gọi `LocalTime.of(24,0)` với ý nghĩa “cuối ngày”: factory sẽ ném `DateTimeException`. Nếu một giao thức riêng cho phép chuỗi `24:00`, ứng dụng phải quy định rõ việc chuyển thành **00:00 ngày kế tiếp** thay vì dùng `LocalTime.of(24,0)`.

Độ chính xác **kiểu dữ liệu** tới nanosecond không chứng minh đồng hồ vật lý của máy có độ chính xác một nanosecond. Đây là hai khái niệm khác nhau.

## 6. `LocalDateTime`: kết hợp trường ngày và giờ, không có timezone

`LocalDateTime` có thể tạo từ hai giá trị hợp lệ:

```java
LocalDate day = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(23, 59, 58, 123_000_000);
LocalDateTime dt = LocalDateTime.of(day, time);

dt.toLocalDate(); // 2024-02-29
dt.toLocalTime(); // 23:59:58.123
dt.getYear();     // 2024
dt.getHour();     // 23
```

Đoạn mã minh họa trong phương thức có import `java.time.*`.

Cần phân biệt:
- `LocalDateTime` có **ngày và giờ theo mặt đồng hồ**, nhưng **không có offset** và **không có ZoneId**.
- Không thể suy ra một `Instant` duy nhất chỉ từ một `LocalDateTime` nếu không chọn offset/zone và chính sách giải quyết DST.
- `LocalDateTime.of(2024,3,10,2,30)` hợp lệ về lịch và cấu trúc giờ, dù tại một số múi giờ có DST (ví dụ New York) giờ địa phương 02:30 ngày đó không xảy ra.
- Nếu cần lưu thời điểm sự kiện trên timeline, thường dùng `Instant` hoặc giá trị có offset/zone rõ ràng, thay vì xem `LocalDateTime` mặc nhiên là UTC.

## 7. Chương trình Java: LocalTime và LocalDateTime

Tạo tệp `TimeFieldsDemo.java`:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class TimeFieldsDemo {
    public static void main(String[] args) {
        LocalTime time =
                LocalTime.of(23, 59, 58, 123_000_000);
        LocalDateTime dt = LocalDateTime.of(
                LocalDate.of(2024, 2, 29), time);

        System.out.println("time = " + time);
        System.out.println("hour = " + time.getHour());
        System.out.println("minute = " + time.getMinute());
        System.out.println("second = " + time.getSecond());
        System.out.println("nano = " + time.getNano());
        System.out.println("second of day = " + time.toSecondOfDay());
        System.out.println("nano of day = " + time.toNanoOfDay());
        System.out.println("date-time = " + dt);
        System.out.println("date part = " + dt.toLocalDate());
        System.out.println("time part = " + dt.toLocalTime());
        System.out.println("date-time year = " + dt.getYear());
        System.out.println("date-time hour = " + dt.getHour());
    }
}
```

```bash
javac -encoding UTF-8 TimeFieldsDemo.java
java TimeFieldsDemo
```

```text
time = 23:59:58.123
hour = 23
minute = 59
second = 58
nano = 123000000
second of day = 86398
nano of day = 86398123000000
date-time = 2024-02-29T23:59:58.123
date part = 2024-02-29
time part = 23:59:58.123
date-time year = 2024
date-time hour = 23
```

Đây là ví dụ có đầu vào cố định, không dùng `now()` hoặc múi giờ mặc định, vì vậy stdout không thay đổi theo thời điểm thực thi.

## 8. Truy cập động bằng `ChronoField` và `TemporalAccessor`

Getter chuyên biệt thường dễ đọc nhất. Nhưng khi viết thành phần tổng quát nhận `TemporalAccessor`, có thể dùng các field trong `java.time.temporal.ChronoField`:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(23, 59, 58, 123_000_000);

date.get(ChronoField.DAY_OF_YEAR);       // 60
date.get(ChronoField.MONTH_OF_YEAR);     // 2
time.get(ChronoField.SECOND_OF_DAY);     // 86398
time.getLong(ChronoField.NANO_OF_DAY);   // 86398123000000L
date.getLong(ChronoField.EPOCH_DAY);     // 19782L
```

Đoạn minh họa giả định import `java.time.*` và `java.time.temporal.ChronoField`. Các method chính:

- `isSupported(field)` trả lời **kiểu temporal này có hỗ trợ field hay không**.
- `get(field)` trả `int` nếu field hợp lệ và giá trị có thể biểu diễn qua API `get`.
- `getLong(field)` trả `long`, cần dùng cho field có giá trị lớn như `NANO_OF_DAY`.
- `range(field)` trả `ValueRange` — miền hợp lệ của field với ngữ cảnh temporal hiện tại.

| `ChronoField` | LocalDate | LocalTime | LocalDateTime |
| --- | --- | --- | --- |
| `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH` | Hỗ trợ | Không | Hỗ trợ |
| `DAY_OF_YEAR`, `EPOCH_DAY` | Hỗ trợ | Không | Hỗ trợ |
| `HOUR_OF_DAY`, `MINUTE_OF_HOUR` | Không | Hỗ trợ | Hỗ trợ |
| `SECOND_OF_DAY`, `NANO_OF_DAY` | Không | Hỗ trợ | Hỗ trợ |
| `INSTANT_SECONDS` | Không | Không | **Không** |
| `OFFSET_SECONDS` | Không | Không | Không |

`INSTANT_SECONDS` cần biết một thời điểm trên timeline. `LocalDateTime` chỉ có thông tin cục bộ nên `dt.isSupported(ChronoField.INSTANT_SECONDS)` trả false và nếu vẫn yêu cầu field thì ném `UnsupportedTemporalTypeException`.

### `get` không thay thế `getLong`

`ChronoField.NANO_OF_DAY` có miền tới gần 86.400 tỷ nano, vượt quá miền của `int`. Vì vậy `LocalTime.get(ChronoField.NANO_OF_DAY)` không phải phương thức đúng; dùng `getLong` hoặc `toNanoOfDay`. Lỗi này không được sửa bằng cách cast `long` xuống `int`, bởi cast sẽ làm mất phần thông tin.

`ChronoField.EPOCH_DAY` tính **số ngày ISO kể từ ngày 1970-01-01**. Nó không phải timestamp tính bằng giây hoặc milli giây. Một `LocalDate` không biết timezone để tự trở thành `Instant`.

## 9. Range tổng quát và range theo ngữ cảnh

`ChronoField.DAY_OF_MONTH.range()` cho miền **tổng quát** của ngày trong tháng. Tháng ngắn nhất có 28 ngày và tháng dài nhất có 31, nên nó biểu diễn dạng `1 - 28/31`.

Trong khi đó:
- `LocalDate.of(2024,2,29).range(ChronoField.DAY_OF_MONTH)` trả `1 - 29`.
- `LocalDate.of(2023,2,28).range(ChronoField.DAY_OF_MONTH)` trả `1 - 28`.
- `LocalDate.of(2024,4,30).range(ChronoField.DAY_OF_MONTH)` trả `1 - 30`.

`ValueRange` có `isValidValue(long)` và `checkValidValue(long, TemporalField)`, nhưng **range lấy từ đâu** mới quyết định câu hỏi được trả lời.

**Không dùng** `ChronoField.DAY_OF_MONTH.range().isValidValue(31)` để kết luận ngày 31/2 hợp lệ. Range tổng quát chỉ nói `31` có thể là ngày của **một số tháng**, không phải tháng 2.

Nếu mục tiêu là “Ngày `d` có hợp lệ trong tháng `m` năm `y` không?”, `YearMonth.of(y,m).isValidDay(d)` là API thích hợp và rõ hơn việc tự phân tích `ValueRange`.

### Bảo vệ field không hỗ trợ

Trong một utility nhận `TemporalAccessor temporal`:

```java
if (temporal.isSupported(ChronoField.HOUR_OF_DAY)) {
    int hour = temporal.get(ChronoField.HOUR_OF_DAY);
    // Sử dụng hour.
} else {
    // Không có trường giờ cho type hiện tại.
}
```

Đây là đoạn minh họa, giả định biến `temporal` đã có. Tránh yêu cầu một field không có nghĩa với type, ví dụ `LocalDate` không có `HOUR_OF_DAY`. Nếu luôn xử lý `LocalDateTime`, getter chuyên biệt `getHour()` thường đơn giản và dễ kiểm soát hơn.

## 10. Chương trình Java: ChronoField, range và ngoại lệ

Tạo tệp `TemporalFieldDemo.java`:

```java
import java.time.*;
import java.time.temporal.ChronoField;
import java.time.temporal.UnsupportedTemporalTypeException;

public class TemporalFieldDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time =
                LocalTime.of(23, 59, 58, 123_000_000);
        LocalDateTime dt = LocalDateTime.of(date, time);

        System.out.println("date DAY_OF_YEAR = " +
                date.get(ChronoField.DAY_OF_YEAR));
        System.out.println("date MONTH_OF_YEAR = " +
                date.get(ChronoField.MONTH_OF_YEAR));
        System.out.println("time SECOND_OF_DAY = " +
                time.get(ChronoField.SECOND_OF_DAY));
        System.out.println("time NANO_OF_DAY (long) = " +
                time.getLong(ChronoField.NANO_OF_DAY));
        System.out.println("date EPOCH_DAY (long) = " +
                date.getLong(ChronoField.EPOCH_DAY));
        System.out.println("date range DAY_OF_MONTH = " +
                date.range(ChronoField.DAY_OF_MONTH));
        System.out.println("generic range DAY_OF_MONTH = " +
                ChronoField.DAY_OF_MONTH.range());
        System.out.println("date supports HOUR_OF_DAY = " +
                date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("dt supports INSTANT_SECONDS = " +
                dt.isSupported(ChronoField.INSTANT_SECONDS));

        try {
            dt.getLong(ChronoField.INSTANT_SECONDS);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println(
                    "instant field = UnsupportedTemporalTypeException");
        }

        try {
            time.get(ChronoField.NANO_OF_DAY);
        } catch (DateTimeException ex) {
            System.out.println("get nano-of-day = DateTimeException");
        }
    }
}
```

```bash
javac -encoding UTF-8 TemporalFieldDemo.java
java TemporalFieldDemo
```

```text
date DAY_OF_YEAR = 60
date MONTH_OF_YEAR = 2
time SECOND_OF_DAY = 86398
time NANO_OF_DAY (long) = 86398123000000
date EPOCH_DAY (long) = 19782
date range DAY_OF_MONTH = 1 - 29
generic range DAY_OF_MONTH = 1 - 28/31
date supports HOUR_OF_DAY = false
dt supports INSTANT_SECONDS = false
instant field = UnsupportedTemporalTypeException
get nano-of-day = DateTimeException
```

Hai lần catch trình bày hai vấn đề khác nhau. `INSTANT_SECONDS` không thuộc `LocalDateTime` vì thiếu timezone/offset, còn `NANO_OF_DAY` có thể đọc được ở `LocalTime` nhưng **phải dùng `getLong`**. `UnsupportedTemporalTypeException` là một subtype của `DateTimeException`.

## 11. Kiểm tra năm nhuận bằng `Year`, `YearMonth` và `MonthDay`

Để kiểm tra quy tắc calendar mà không cần tự viết thuật toán:

```java
Year.isLeap(2024);    // true
Year.isLeap(2023);    // false

YearMonth.of(2024, 2).lengthOfMonth(); // 29
YearMonth.of(2023, 2).lengthOfMonth(); // 28

YearMonth.of(2024, 2).isValidDay(29); // true
YearMonth.of(2023, 2).isValidDay(29); // false

MonthDay.of(2, 29).isValidYear(2024); // true
MonthDay.of(2, 29).isValidYear(2023); // false
```

Đoạn minh họa trong phương thức sau khi import `java.time.*`.

`YearMonth` là kiểu đại diện **một tháng trong một năm cụ thể**. `isValidDay(day)` trả lời ngày `day` có tồn tại trong tháng/năm ấy không. Nhưng `YearMonth.of(2024,13)` tự ném `DateTimeException`, vì **tháng 13 không tồn tại**; phải xử lý lỗi tạo YearMonth nếu tháng người dùng nhập chưa hợp lệ.

`MonthDay` lưu **ngày và tháng nhưng không có năm**. `MonthDay.of(2,29)` hợp lệ vì 29/2 có xảy ra ở một số năm; gọi `isValidYear(2023)` mới trả lời nó có hợp lệ ở năm cụ thể đó không.

`LocalDate.isLeapYear()` dùng khi đã có LocalDate. `Year.isLeap(year)` dùng khi chỉ có year. Không lấy `day>=1 && day<=31` làm quy tắc xác thực duy nhất; miền tháng và năm nhuận mới quyết định ngày thực sự tồn tại.

## 12. `of(...)` kiểm tra cấu trúc và ném `DateTimeException`

Các factory `LocalDate.of`, `LocalTime.of`, `LocalDateTime.of` kiểm tra giá trị và **không trả Optional.empty() hoặc null** khi sai lịch. Chúng ném `DateTimeException`:

| Lời gọi | Kết quả |
| --- | --- |
| `LocalDate.of(2024,2,29)` | Tạo ngày hợp lệ |
| `LocalDate.of(2023,2,29)` | `DateTimeException` |
| `LocalDate.of(2024,4,31)` | `DateTimeException` |
| `YearMonth.of(2024,13)` | `DateTimeException` |
| `LocalTime.of(23,59,59,999_999_999)` | Tạo giờ hợp lệ |
| `LocalTime.of(24,0)` | `DateTimeException` |
| `LocalTime.of(10,60)` | `DateTimeException` |
| `LocalDateTime.of(2024,2,29,10,30)` | Tạo ngày giờ hợp lệ |
| `LocalDateTime.of(2024,2,29,10,60)` | `DateTimeException` |

Nếu API nhận các số từ biểu mẫu, có thể dùng `try/catch DateTimeException` tại **biên vào dữ liệu**, rồi đổi thành thông báo validation. Không nên `catch (Exception)` để giấu mọi lỗi logic hoặc lỗi hạ tầng. Nếu muốn hiển thị lỗi chi tiết cho một trường cụ thể, có thể kiểm tra miền trước rồi **vẫn gọi factory** làm bước tạo giá trị cuối.

Với input từ text, `DateTimeParseException` là loại chuyên biệt hơn và là subclass của `DateTimeException`.

## 13. Tạo ngày sai khác với điều chỉnh một ngày đã tồn tại

Hai trường hợp sau có hành vi khác nhau:

```java
LocalDate.of(2023, 2, 29); // Ném DateTimeException.
```

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate feb = jan31.withMonth(2);
// feb là 2024-02-29

LocalDate leapDay = LocalDate.of(2024, 2, 29);
LocalDate nextYear = leapDay.withYear(2023);
// nextYear là 2023-02-28
```

Đây là những đoạn minh họa được đặt trong phương thức đã import `LocalDate`. `LocalDate.of` yêu cầu một **tổ hợp ngày/tháng/năm phải tồn tại**. Trong khi đó `withMonth`/`withYear` nhận một ngày đang hợp lệ và cần điều chỉnh **day-of-month** về ngày cuối tháng của tháng/năm mới nếu cần thiết.

Ngược lại, `LocalDate.of(2024,2,29).withDayOfMonth(30)` ném `DateTimeException`, vì nó yêu cầu cụ thể **ngày 30 của tháng 2**.

**Không dùng `withYear` hay `withMonth` như validator của đầu vào người dùng**: việc chúng có thể tự điều chỉnh thành 28/2 hoặc 29/2 không có nghĩa người dùng đã nhập ngày đó. Nếu yêu cầu nghiêm ngặt, phải từ chối dữ liệu không hợp lệ thay vì âm thầm sửa.

## 14. Chương trình Java: validate năm nhuận và ngoại lệ

Tạo tệp `ValidationDemo.java`:

```java
import java.time.*;

public class ValidationDemo {
    static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " = accepted");
        } catch (DateTimeException ex) {
            System.out.println(label + " = " +
                    ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("2024 leap = " + Year.isLeap(2024));
        System.out.println("2023 leap = " + Year.isLeap(2023));
        System.out.println("Feb 2024 has 29 = " +
                YearMonth.of(2024, 2).isValidDay(29));
        System.out.println("Feb 2023 has 29 = " +
                YearMonth.of(2023, 2).isValidDay(29));
        System.out.println("Feb 29 valid 2024 = " +
                MonthDay.of(2, 29).isValidYear(2024));
        System.out.println("Feb 29 valid 2023 = " +
                MonthDay.of(2, 29).isValidYear(2023));

        attempt("invalid date",
                () -> LocalDate.of(2023, 2, 29));
        attempt("invalid month",
                () -> YearMonth.of(2024, 13));
        attempt("invalid time",
                () -> LocalTime.of(24, 0));
        attempt("invalid hour minute",
                () -> LocalDateTime.of(2024, 2, 29, 10, 60));

        System.out.println("month adjusted = " +
                LocalDate.of(2024, 1, 31).withMonth(2));
        System.out.println("year adjusted = " +
                LocalDate.of(2024, 2, 29).withYear(2023));

        attempt("invalid with day",
                () -> LocalDate.of(2024, 2, 29)
                        .withDayOfMonth(30));
    }
}
```

```bash
javac -encoding UTF-8 ValidationDemo.java
java ValidationDemo
```

```text
2024 leap = true
2023 leap = false
Feb 2024 has 29 = true
Feb 2023 has 29 = false
Feb 29 valid 2024 = true
Feb 29 valid 2023 = false
invalid date = DateTimeException
invalid month = DateTimeException
invalid time = DateTimeException
invalid hour minute = DateTimeException
month adjusted = 2024-02-29
year adjusted = 2023-02-28
invalid with day = DateTimeException
```

`attempt` bắt `DateTimeException` chỉ quanh các thao tác ngày giờ đang kiểm tra và in **tên lớp**, thay vì phụ thuộc thông báo exception cụ thể. Kết quả xác nhận rõ `of` từ chối ngày sai, còn `withMonth`/`withYear` điều chỉnh ngày cuối tháng.

## 15. Parse văn bản: `ResolverStyle.SMART` khác `STRICT`

Khi nhận chuỗi từ form, CSV hoặc API, ngoài lịch hợp lệ còn cần quyết định cách parse. `DateTimeFormatter` có ba resolver style:

- `ResolverStyle.STRICT`: từ chối tổ hợp ngày không hợp lệ.
- `ResolverStyle.SMART`: với một số tổ hợp có thể **điều chỉnh** ngày về ngày cuối tháng hợp lệ. Đây là resolver style mặc định của `DateTimeFormatter.ofPattern(...)`.
- `ResolverStyle.LENIENT`: cho phép chuẩn hóa trường vượt miền theo quy tắc cộng/trừ trong nhiều trường hợp, không thích hợp làm mặc định nếu yêu cầu từ chối ngày sai.

Ví dụ **rất dễ bỏ sót khi review code**:

```java
DateTimeFormatter smart =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

LocalDate.parse("2023-02-29", smart);
// Trả 2023-02-28 vì SMART điều chỉnh.

DateTimeFormatter strict =
        smart.withResolverStyle(ResolverStyle.STRICT);

// LocalDate.parse("2023-02-29", strict);
// Ném DateTimeParseException.
```

Đây là đoạn minh họa có import `LocalDate` và `java.time.format.*`. Quan trọng: `LocalDate.parse("2023-02-29")` **không giống** formatter `ofPattern` mặc định trên: overload không truyền formatter dùng `DateTimeFormatter.ISO_LOCAL_DATE`, được cấu hình giải quyết nghiêm ngặt và sẽ từ chối ngày sai.

### Chọn ký hiệu pattern đúng

| Pattern | Nghĩa | Cạm bẫy |
| --- | --- | --- |
| `uuuu` | Proleptic year | Phù hợp strict ISO parsing |
| `yyyy` | Year-of-era | STRICT có thể cần thông tin era để giải quyết ngày |
| `YYYY` | Week-based-year | **Không phải năm lịch**, có thể lệch quanh cuối năm |
| `MM` | Tháng | Khác `mm` là phút |
| `dd` | Ngày trong tháng | Khác `DD` là ngày trong năm |
| `HH` | Giờ 0–23 | Khác `hh` là giờ 1–12, cần AM/PM khi dùng |
| `SSS` | Fraction-of-second ở độ dài 3 | Thường hiển thị milli giây |

Dùng `DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT).withResolverStyle(ResolverStyle.STRICT)` khi form công bố dạng ngày/tháng/năm này và phải từ chối ngày không tồn tại.

**Regex chỉ biết cấu trúc chuỗi**, không biết năm nhuận hay tháng có bao nhiêu ngày. Không dùng regex đơn lẻ để xác nhận một `LocalDate`.

## 16. Chương trình Java: SMART, STRICT và ISO parse

Tạo tệp `ParseStrictDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ParseStrictDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd", Locale.ROOT);
        DateTimeFormatter strict =
                smart.withResolverStyle(ResolverStyle.STRICT);

        System.out.println("ISO leap parse = " +
                LocalDate.parse("2024-02-29"));
        System.out.println("SMART invalid day = " +
                LocalDate.parse("2023-02-29", smart));
        System.out.println("STRICT valid = " +
                LocalDate.parse("2024-02-29", strict));

        try {
            LocalDate.parse("2023-02-29", strict);
        } catch (DateTimeParseException ex) {
            System.out.println(
                    "STRICT invalid = DateTimeParseException");
        }

        try {
            LocalDate.parse("2023-02-29");
        } catch (DateTimeParseException ex) {
            System.out.println("ISO invalid = DateTimeParseException");
        }

        DateTimeFormatter vn =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("VN valid = " +
                LocalDate.parse("29/02/2024", vn));
        System.out.println("format = " +
                LocalDate.of(2024, 2, 29).format(vn));
    }
}
```

```bash
javac -encoding UTF-8 ParseStrictDemo.java
java ParseStrictDemo
```

```text
ISO leap parse = 2024-02-29
SMART invalid day = 2023-02-28
STRICT valid = 2024-02-29
STRICT invalid = DateTimeParseException
ISO invalid = DateTimeParseException
VN valid = 2024-02-29
format = 29/02/2024
```

**Giá trị quan trọng:** cùng chuỗi `2023-02-29`, SMART **chuyển** thành 28/2/2023, còn STRICT **từ chối**. Khi đang xây API nhận ngày sinh hoặc ngày hẹn được người dùng nhập, thường cần STRICT để không âm thầm biến một ngày sai thành ngày khác.

`DateTimeFormatter` immutable và thread-safe, nên có thể định nghĩa một formatter dùng lại. `DateTimeParseException` là subclass của `DateTimeException`; chuyển loại lỗi này thành phản hồi form ở ranh giới input, không che các lỗi không liên quan bằng catch `Exception` rộng.

## 17. “Hợp lệ theo nghiệp vụ” là bước sau khi có LocalDate

Ngay cả một `LocalDate` đã đúng lịch cũng có thể không hợp lệ cho một tác vụ. Ví dụ chính sách chỉ cho phép đặt hẹn **từ hôm nay đến tối đa 30 ngày lịch sau hôm nay**, bao gồm hai đầu mút:

```java
boolean within =
        !requestedDate.isBefore(today)
        && !requestedDate.isAfter(today.plusDays(30));
```

Đoạn minh họa giả định `requestedDate` và `today` đều là `LocalDate` hợp lệ. `isBefore` và `isAfter` so sánh ngày cục bộ; không cần ép thành milliseconds.

### Định nghĩa ranh giới trước khi code

- Khoảng đóng `[start,end]`: gồm ngày đầu và ngày cuối.
- Khoảng nửa mở `[start,end)`: gồm ngày đầu, **không** gồm ngày cuối; thường hữu ích khi lọc timestamp theo một ngày vì tránh phải tự tạo `23:59:59.999999999`.
- Đối với ngày không có giờ, chọn khoảng theo **ngày lịch**.
- Đối với thời điểm thực, chọn `Instant` và zone/offset phù hợp trước khi định nghĩa ranh giới.

`LocalTime.isBefore/isAfter` chỉ so giờ trong ngày, không biết ngày; `LocalDateTime.isBefore/isAfter` so ngày + giờ cục bộ, không thể tự xác định hai instant nằm ở hai múi giờ khác nhau.

### Dùng `Clock` thay vì phụ thuộc server timezone

`LocalDate.now()` phụ thuộc đồng hồ/zone mặc định của máy. Backend có thể chạy UTC trong khi người dùng dùng `Asia/Ho_Chi_Minh`, dẫn đến “hôm nay” khác nhau quanh nửa đêm. Dùng `Clock` từ service được cấu hình theo domain và inject vào validator:

```java
LocalDate today = LocalDate.now(clock);
```

Trong test, `Clock.fixed(instant, zone)` làm kết quả lặp lại được. `Clock` có từ Java 8 và vẫn là API chuẩn. Không hardcode múi giờ mặc định của server để quyết định hạn cuối cho mọi người dùng.

## 18. Chương trình Java: kiểm tra ngày theo Clock cố định

Tạo tệp `BusinessRuleDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class BusinessRuleDemo {
    static boolean bookable(LocalDate date, Clock clock) {
        LocalDate today = LocalDate.now(clock);
        return !date.isBefore(today)
                && !date.isAfter(today.plusDays(30));
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2024-06-15T03:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("today = " + LocalDate.now(fixed));
        System.out.println("yesterday valid = " +
                bookable(LocalDate.of(2024, 6, 14), fixed));
        System.out.println("today valid = " +
                bookable(LocalDate.of(2024, 6, 15), fixed));
        System.out.println("30 days valid = " +
                bookable(LocalDate.of(2024, 7, 15), fixed));
        System.out.println("31 days valid = " +
                bookable(LocalDate.of(2024, 7, 16), fixed));
    }
}
```

```bash
javac -encoding UTF-8 BusinessRuleDemo.java
java BusinessRuleDemo
```

```text
today = 2024-06-15
yesterday valid = false
today valid = true
30 days valid = true
31 days valid = false
```

Ở đây “hôm nay” theo `Clock` là 15/6/2024 tại Việt Nam; hai ngày hợp lệ về nghiệp vụ là 15/6 và 15/7. Các ngày còn lại vẫn **tồn tại trên lịch**, nhưng không đạt chính sách của ví dụ.

Trong ứng dụng thật cần xác nhận “30 ngày lịch” hay “720 giờ thật”, có cho phép ngày nghỉ hay không. Đó không phải nhiệm vụ của `LocalDate.of`.

## 19. Validation của LocalDateTime chưa bao gồm tính hợp lệ tại một ZoneId

`LocalDateTime.of(2024,3,10,2,30)` là giá trị **hợp lệ về cấu trúc**: ngày, tháng, năm và giờ đều trong miền. Nhưng tại `America/New_York`, 02:30 ngày 10/3/2024 thuộc **DST gap**, nên giờ địa phương ấy không ứng với một instant thật tại vùng đó.

Ngược lại, 01:30 ngày 3/11/2024 ở vùng ấy nằm trong **DST overlap**, có thể ứng với **hai offset** và hai instant khác nhau.

Nếu lịch hẹn bắt buộc gắn vùng, xác thực sau bước LocalDateTime:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local =
        LocalDateTime.of(2024, 3, 10, 2, 30);

int count = zone.getRules().getValidOffsets(local).size();
// 0 = gap; 1 = bình thường; 2 = overlap.
```

Đoạn minh họa trong phương thức với import `java.time.*`. Không tự đồng nhất “LocalDateTime hợp lệ” với “thời điểm đặt lịch hợp lệ trong mọi múi giờ”. `atZone(zone)` có cơ chế giải quyết mặc định cho gap/overlap; nếu nghiệp vụ đòi **từ chối** giờ không xảy ra hoặc bắt người dùng chọn offset khi đồng hồ quay lùi, phải đưa ra quy tắc riêng.

Việc chuyển ngày cục bộ sang timestamp chính xác cũng đòi zone/offset, không thể gọi `getLong(ChronoField.INSTANT_SECONDS)` trực tiếp trên một `LocalDateTime`.

## 20. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tự cho phép mọi ngày 1–31 | Nhận 31/4, 31/6, 29/2 năm thường | `YearMonth.isValidDay` hoặc `LocalDate.of` |
| Tính nhuận chỉ bằng `year % 4 == 0` | Sai ở một số năm thế kỷ | `Year.isLeap(year)` |
| Lấy `MonthDay.of(2,29)` để kết luận 29/2 hợp lệ mọi năm | Thiếu năm | `MonthDay.isValidYear(year)` |
| Gọi `getHour()` trên `LocalDate` | Trường giờ không tồn tại | `LocalTime`/`LocalDateTime` |
| Dùng `time.get(NANO_OF_DAY)` | Field cần long, không thích hợp `int` | `getLong` hoặc `toNanoOfDay` |
| Lấy `ChronoField.DAY_OF_MONTH.range()` để chứng minh 31/2 | Range tổng quát, không gắn năm/tháng | `YearMonth.of(y,m).isValidDay(d)` |
| Coi `LocalDate.of` ngày sai trả null | Factory ném ngoại lệ | Catch `DateTimeException` có phạm vi |
| Dùng `withYear` để validate dữ liệu ngày nhập | Có thể tự điều chỉnh 29/2 thành 28/2 | Factory `of` hoặc parse STRICT |
| Dùng formatter `ofPattern` mặc định SMART để kiểm tra form | Có thể nhận và điều chỉnh ngày sai | `withResolverStyle(STRICT)` |
| Dùng `yyyy` thay `uuuu` trong STRICT mà không xử lý era | Năm trong era khác proleptic year | `uuuu` theo nhu cầu ISO |
| Dùng `YYYY-MM-dd` cho năm lịch | Week-based-year khác calendar year | `uuuu-MM-dd` |
| Nhầm `MM` với `mm` | Tháng khác phút | Pattern đúng |
| Gọi `getLong(INSTANT_SECONDS)` trên `LocalDateTime` | Không có zone/offset | Kết hợp `ZoneId` theo policy |
| Dùng `LocalDate.now()` trong test kỳ vọng cố định | Kết quả thay đổi theo thời gian | Inject `Clock.fixed` |
| Không phân biệt calendar valid và business valid | Nhận ngày không được phép | Tách hai tầng validation |
| Lấy “hết ngày” bằng `23:59:59` | Bỏ qua phần nanosecond cuối giây | Dùng khoảng nửa mở đúng nghĩa |
| Dùng giờ cục bộ qua DST mà không validate zone | Gap/overlap tạo giờ không tồn tại hoặc mơ hồ | `ZoneRules.getValidOffsets` |
| Quên nhận kết quả `plusDays` | Date cũ không thay đổi | Gán đối tượng mới |

**Đối với ngày giờ cục bộ, hầu hết lỗi bắt nguồn từ việc lẫn lộn kiểu dữ liệu, thiếu thông tin ngữ cảnh hoặc dùng API điều chỉnh thay cho API xác thực.**

## 21. Mẫu xử lý đầu vào thực tế

Với một form nhận ngày hẹn ở dạng `dd/MM/uuuu`:

1. Công bố rõ **format** và cho biết có được phép khoảng trắng đầu/cuối hay không.
2. Parse bằng `DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT).withResolverStyle(ResolverStyle.STRICT)`.
3. Khi chuỗi không hợp lệ, bắt `DateTimeParseException` ở ranh giới nhập liệu và trả lỗi có nội dung. Không bắt `Exception` chung cho mọi thứ.
4. Khi đã có `LocalDate`, kiểm tra **quy tắc nghiệp vụ** như nằm trong 30 ngày kể từ hôm nay theo `Clock` của vùng phù hợp.
5. Nếu form còn có giờ và địa điểm, tạo `LocalDateTime` rồi áp dụng policy `ZoneId`/DST trước khi quy đổi sang `Instant` cho lưu trữ sự kiện.
6. Viết test cho ngày nhuận, ngày cuối tháng, ranh giới khoảng được phép, chuỗi lỗi và zone khác nhau.

Một ví dụ helper (**đoạn minh họa trong class**):

```java
private static final DateTimeFormatter INPUT =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

static LocalDate parseRequiredDate(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("Date is required");
    }
    try {
        return LocalDate.parse(text, INPUT);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Expected a real dd/MM/uuuu date", ex);
    }
}
```

Giả định import `java.time.LocalDate`, `java.time.format.*` và `java.util.Locale`. `String.isBlank` có từ **Java 11**; trên Java 8 dùng `text == null || text.trim().isEmpty()` nếu tương thích chính sách khoảng trắng. Không chuyển mọi trường hợp lỗi thành `null` hay một ngày mặc định như `1970-01-01` trừ khi hợp đồng API chủ đích quy định như vậy.

## 22. Checklist kiểm thử

**Ngày và lịch:**
- Năm nhuận `2024-02-29` hợp lệ, `2023-02-29` bị từ chối.
- Tháng 4 có ngày 30 nhưng không có ngày 31.
- `getDayOfYear()` ở ngày 29/2 của năm nhuận đúng là 60.
- `getMonth()` trả enum, `getMonthValue()` trả số nguyên.
- `withMonth`/`withYear` có thể điều chỉnh ngày cuối tháng; `of` không chấp nhận ngày không tồn tại.
- `MonthDay.of(2,29).isValidYear(2023)` false.

**Giờ và field:**
- `00:00:00.000000000` và `23:59:59.999999999` trong miền.
- `24:00`, phút 60, giây 60 và nano 1_000_000_000 bị factory từ chối.
- `getNano` khác `toNanoOfDay`.
- `LocalDate.isSupported(HOUR_OF_DAY)` false.
- `LocalDateTime.isSupported(INSTANT_SECONDS)` false.
- `getLong(NANO_OF_DAY)` dùng được, `get(NANO_OF_DAY)` không phù hợp.

**Parse và nghiệp vụ:**
- `ResolverStyle.STRICT` từ chối ngày sai; formatter `ofPattern` mặc định SMART có thể điều chỉnh.
- Dùng `uuuu` thay `yyyy`/`YYYY` khi muốn năm ISO đúng ý.
- Locale, format, null/blank input theo hợp đồng.
- `Clock.fixed` giúp test “hôm nay” không biến động.
- Kiểm tra rõ ranh giới inclusive/exclusive.
- Với lịch gắn zone, kiểm tra DST gap/overlap.

Các ca thử nên dùng những giá trị cố định, không phụ thuộc vào đồng hồ/múi giờ hệ thống. Nếu ứng dụng dùng JUnit, có thể chuyển các chương trình ví dụ thành assertions tương ứng mà không cần thay đổi semantics API.

## 23. Câu hỏi tự luyện

**Câu 1.** `LocalDate.of(2024,2,29).getDayOfYear()` trả gì?  
**Đáp án:** `60`. Năm 2024 nhuận.

**Câu 2.** `getMonth()` và `getMonthValue()` khác gì?  
**Đáp án:** Một cái trả enum `Month`, một cái trả số tháng 1–12.

**Câu 3.** Có thể đọc `HOUR_OF_DAY` từ LocalDate không?  
**Đáp án:** Không. LocalDate không có field giờ. Dùng LocalTime/LocalDateTime khi cần.

**Câu 4.** `LocalTime.of(24,0)` có hợp lệ không?  
**Đáp án:** Không. Nó ném `DateTimeException`.

**Câu 5.** `LocalTime.get(ChronoField.NANO_OF_DAY)` có phải API đúng?  
**Đáp án:** Không. Dùng `getLong` hoặc `toNanoOfDay` vì giá trị có thể vượt miền `int`.

**Câu 6.** `ChronoField.DAY_OF_MONTH.range().isValidValue(31)` có chứng minh 31/2 tồn tại không?  
**Đáp án:** Không. Đây là range tổng quát; dùng `YearMonth.of(year,month).isValidDay(day)`.

**Câu 7.** `YearMonth.of(2023,2).isValidDay(29)` là gì?  
**Đáp án:** `false`, trong khi tháng 2 năm 2024 trả `true` cho 29.

**Câu 8.** Vì sao `MonthDay.of(2,29)` tạo được nhưng `isValidYear(2023)` false?  
**Đáp án:** MonthDay chưa gắn năm; 29/2 có tồn tại trong các năm nhuận, không tồn tại trong 2023.

**Câu 9.** `LocalDate.of(2023,2,29)` và `LocalDate.of(2024,2,29).withYear(2023)` có giống nhau?  
**Đáp án:** Không. Factory ném lỗi còn `withYear` điều chỉnh thành `2023-02-28`.

**Câu 10.** `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định có luôn từ chối ngày 29/2/2023?  
**Đáp án:** Không. `SMART` có thể điều chỉnh thành 28/2/2023. Dùng `STRICT` nếu phải từ chối ngày sai.

**Câu 11.** `LocalDateTime` có `INSTANT_SECONDS` không?  
**Đáp án:** Không. Thiếu zone/offset nên chưa xác định một instant duy nhất.

**Câu 12.** Tại sao `LocalDate.now()` không thích hợp cho test kỳ vọng cố định?  
**Đáp án:** Phụ thuộc đồng hồ và zone hệ thống. Inject `Clock.fixed` để test tái lập.

**Câu 13.** Ngày hẹn hợp lệ về lịch có thể không tồn tại tại một vùng múi giờ không?  
**Đáp án:** Một **LocalDateTime** có giờ trong DST gap có thể không xảy ra tại vùng đó. Cần chọn `ZoneId` và kiểm tra offset hợp lệ.

**Câu 14.** Vì sao “hạn tới hết ngày” nên được mô hình hóa bằng ranh giới nửa mở?  
**Đáp án:** Tránh bỏ sót nanosecond khi hardcode `23:59:59`; dùng ngày kế tiếp làm mốc kết thúc (exclusive) khi quy tắc domain phù hợp.

## 24. Ghi nhớ

- **Ngày giờ cục bộ** không tự chứa múi giờ: `LocalDate` chỉ ngày, `LocalTime` chỉ giờ, `LocalDateTime` gồm cả hai.
- Các getter chuyên biệt như `getYear`, `getMonthValue`, `getDayOfMonth`, `getHour`, `getMinute`, `getSecond`, `getNano` nên được ưu tiên khi type đã rõ.
- Với xử lý generic, dùng `ChronoField`, `isSupported`, `range` và `getLong` khi field có miền lớn. Đừng yêu cầu `INSTANT_SECONDS` trên `LocalDateTime`.
- **Đúng miền 1–31 chưa đủ để ngày hợp lệ**. Dùng `Year.isLeap`, `YearMonth.isValidDay`, `MonthDay.isValidYear` và factory `of`.
- **`LocalDate.of` từ chối ngày sai; `withYear`/`withMonth` có thể tự điều chỉnh cuối tháng**. Không dùng phép điều chỉnh làm validator form.
- **Parse SMART khác STRICT**: thiết lập `ResolverStyle.STRICT` khi phải từ chối ngày không tồn tại. Dùng `uuuu` thay `YYYY` cho năm lịch ISO.
- **Hợp lệ theo lịch** là một bước, **hợp lệ theo nghiệp vụ** là bước khác. Dùng `Clock` và `ZoneId` rõ khi tính “hôm nay” hoặc chuyển LocalDateTime sang instant.
- Ưu tiên API `java.time` vẫn được duy trì từ Java 8; không cần chuyển về các kiểu ngày giờ cũ chỉ để đọc field hoặc kiểm tra năm nhuận.

### Tài liệu Java API chính thức (còn hiệu lực)

- [`LocalDate`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html): getter ngày, `isLeapYear`, `lengthOfMonth`, `range`, `withYear`.
- [`LocalTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalTime.html): getter giờ, `toSecondOfDay`, `toNanoOfDay` và miền hợp lệ.
- [`LocalDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): đọc trường ngày giờ và giới hạn không có zone.
- [`Year`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Year.html), [`YearMonth`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/YearMonth.html), [`MonthDay`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/MonthDay.html): năm nhuận và ngày hợp lệ.
- [`ChronoField`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoField.html), [`TemporalAccessor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAccessor.html), [`ValueRange`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ValueRange.html): field, range, `isSupported`, `get` và `getLong`.
- [`DateTimeFormatter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html) và [`ResolverStyle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html): parse STRICT/SMART, pattern và format.
- [`Clock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): kiểm thử điều kiện ngày/giờ độc lập môi trường.
