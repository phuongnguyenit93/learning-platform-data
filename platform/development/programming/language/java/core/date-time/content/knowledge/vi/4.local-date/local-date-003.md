# Đọc năm, tháng, ngày, thứ và ngày thứ bao nhiêu trong năm với `LocalDate`

`java.time.LocalDate` biểu diễn **một ngày trong lịch ISO-8601** gồm năm, tháng và ngày, **không chứa giờ trong ngày, UTC offset hoặc múi giờ**. Khi đã có `LocalDate`, Java cho phép đọc các thành phần năm–tháng–ngày, xác định thứ trong tuần và số thứ tự ngày trong năm mà không phải tự tách chuỗi hoặc tính ngày theo lịch thủ công.

Bài này trả lời trực tiếp sáu câu hỏi: một `LocalDate` có năm nào, tháng nào, ngày mấy, thứ mấy, là ngày thứ mấy kể từ đầu năm và cách hiểu các kết quả đó khi gặp năm nhuận.

## 1. Tạo giá trị `LocalDate` để đọc

```java
import java.time.LocalDate;

LocalDate date = LocalDate.of(2024, 2, 29);
LocalDate parsed = LocalDate.parse("2024-02-29");

System.out.println(date);                 // 2024-02-29
System.out.println(date.equals(parsed));  // true
```

`LocalDate.of(year, month, dayOfMonth)` nhận **tháng số từ 1 đến 12**. `LocalDate.parse(...)` mặc định hiểu định dạng ISO `uuuu-MM-dd` như `2024-02-29`, không tự hiểu `29/02/2024`. Cả hai cách đều xác thực ngày: `LocalDate.of(2025, 2, 29)` ném `DateTimeException` vì năm 2025 không có ngày 29/2.

Các phương thức đọc dưới đây không làm thay đổi `date`: `LocalDate` là immutable. Nếu muốn một ngày khác, tạo kết quả mới bằng `plusDays`, `withDayOfMonth`, `withDayOfYear`... và giữ giá trị được trả về.

## 2. Đọc năm, tháng và ngày trong tháng

| Mục đích | Phương thức | Kết quả với `2024-02-29` | Kiểu trả về |
| --- | --- | --- | --- |
| Năm theo lịch ISO | `getYear()` | `2024` | `int` |
| Tháng dưới dạng số | `getMonthValue()` | `2` | `int` |
| Tháng dưới dạng enum | `getMonth()` | `FEBRUARY` | `Month` |
| Ngày trong tháng | `getDayOfMonth()` | `29` | `int` |

```java
LocalDate date = LocalDate.of(2024, 2, 29);

int year = date.getYear();              // 2024
int monthNumber = date.getMonthValue(); // 2
Month month = date.getMonth();          // FEBRUARY
int dayOfMonth = date.getDayOfMonth();  // 29
```

Đoạn minh họa dùng thêm `import java.time.Month;` khi đặt trong chương trình Java.

**Tháng số và `Month` phục vụ hai mục đích khác nhau.** `getMonthValue()` hữu ích cho biểu mẫu, API, phép so sánh với tháng cụ thể và dữ liệu số; `getMonth()` hữu ích khi cần một giá trị enum có ý nghĩa rõ ràng, ví dụ `date.getMonth() == Month.FEBRUARY`.

`Month` có 12 hằng từ `JANUARY` đến `DECEMBER`; `Month.FEBRUARY.getValue()` trả `2`. Không dùng `month.ordinal()` làm số tháng: `ordinal()` là chỉ số enum bắt đầu từ **0**, còn tháng ISO bắt đầu từ **1**.

`getDayOfMonth()` trả từ 1 đến độ dài của tháng tương ứng. Ví dụ tháng 2/2024 có 29 ngày, tháng 2/2025 có 28 ngày, tháng 4 có 30 ngày và tháng 12 có 31 ngày. Tránh giả định tất cả các tháng có 30 ngày.

### Thể hiện tháng thành tên cho người đọc

Tên enum `FEBRUARY` dành cho mã nguồn, không phải lúc nào phù hợp giao diện. Để hiển thị, có thể dùng:

```java
String monthName = date.getMonth()
        .getDisplayName(TextStyle.FULL, Locale.ENGLISH);
System.out.println(monthName); // February
```

Cần `import java.time.format.TextStyle;` và `import java.util.Locale;`. Dùng `Locale.forLanguageTag("vi-VN")` khi cần tên tháng bằng tiếng Việt; hình thức hiển thị có thể phụ thuộc dữ liệu locale của môi trường Java. Không so sánh tên hiển thị để quyết định logic: so sánh `Month` hoặc số tháng.

## 3. Đọc thứ trong tuần: `getDayOfWeek()`

`LocalDate.getDayOfWeek()` trả một `DayOfWeek`, là enum từ `MONDAY` đến `SUNDAY`. Theo quy ước ISO-8601, **thứ Hai là 1, thứ Ba là 2, …, Chủ nhật là 7**.

```java
LocalDate date = LocalDate.of(2024, 2, 29);

DayOfWeek day = date.getDayOfWeek(); // THURSDAY
int isoDayNumber = day.getValue();   // 4
```

Đoạn minh họa cần `import java.time.DayOfWeek;`.

| Thứ | `DayOfWeek` | `getValue()` theo ISO |
| --- | --- | ---: |
| Thứ Hai | `MONDAY` | 1 |
| Thứ Ba | `TUESDAY` | 2 |
| Thứ Tư | `WEDNESDAY` | 3 |
| Thứ Năm | `THURSDAY` | 4 |
| Thứ Sáu | `FRIDAY` | 5 |
| Thứ Bảy | `SATURDAY` | 6 |
| Chủ nhật | `SUNDAY` | 7 |

Dùng enum trực tiếp để thể hiện quy tắc nghiệp vụ:

```java
DayOfWeek dow = date.getDayOfWeek();

boolean weekend = dow == DayOfWeek.SATURDAY
               || dow == DayOfWeek.SUNDAY;
```

Đây là định nghĩa **cuối tuần theo quy tắc thứ Bảy/Chủ nhật**; lịch làm việc của một tổ chức hoặc quốc gia có thể khác. `DayOfWeek` chỉ trả **thứ**, không tự xác định ngày nghỉ lễ.

Cần tách biệt hai ý:

- **Thứ trong tuần:** `getDayOfWeek()` luôn theo enum ISO và `DayOfWeek.getValue()` luôn quy định thứ Hai = 1.
- **Tuần bắt đầu vào ngày nào khi vẽ lịch hoặc tính số tuần:** có thể phụ thuộc quốc gia/locale và dùng `WeekFields`; thiết lập locale để định dạng không đổi giá trị enum của `getDayOfWeek()`.

Để hiển thị tên thứ thay vì `THURSDAY`:

```java
String englishDay = date.getDayOfWeek()
        .getDisplayName(TextStyle.FULL, Locale.ENGLISH);
System.out.println(englishDay); // Thursday
```

Nếu cần tiếng Việt, dùng `Locale.forLanguageTag("vi-VN")` và `TextStyle.FULL` hoặc `SHORT`. Đừng tự cắt tên `THURSDAY` hay dựa vào `ordinal()` để ra số thứ.

## 4. Đọc ngày thứ bao nhiêu trong năm: `getDayOfYear()`

`getDayOfYear()` trả **số thứ tự ngày tính từ 1/1 của cùng năm**, bắt đầu bằng **1**, không phải 0.

```java
LocalDate jan1 = LocalDate.of(2024, 1, 1);
LocalDate feb29 = LocalDate.of(2024, 2, 29);
LocalDate dec31 = LocalDate.of(2024, 12, 31);

System.out.println(jan1.getDayOfYear());  // 1
System.out.println(feb29.getDayOfYear()); // 60
System.out.println(dec31.getDayOfYear()); // 366
```

Trong **năm thường**, `getDayOfYear()` chạy từ **1 đến 365**; trong **năm nhuận**, từ **1 đến 366**. Số thứ tự bị chi phối bởi ngày 29/2:

| Ngày | Năm | `getDayOfYear()` | Giải thích |
| --- | ---: | ---: | --- |
| 01/01/2024 | Nhuận | 1 | Ngày đầu năm |
| 28/02/2024 | Nhuận | 59 | Trước ngày nhuận |
| 29/02/2024 | Nhuận | 60 | Ngày nhuận |
| 01/03/2024 | Nhuận | 61 | Sau ngày nhuận |
| 28/02/2025 | Thường | 59 | Không có ngày 29/2 |
| 01/03/2025 | Thường | 60 | Một ngày ít hơn so với năm nhuận |
| 31/12/2024 | Nhuận | 366 | Ngày cuối năm |
| 31/12/2025 | Thường | 365 | Ngày cuối năm |

Hai ngày có cùng số thứ tự trong năm **không nhất thiết cùng tháng/ngày**. Ngày thứ 60 của năm 2024 là **29/2**, còn của năm 2025 là **1/3**. Khi lưu dữ liệu theo số ngày trong năm, cần giữ **năm** đi kèm; số thứ tự một mình không định danh một ngày tuyệt đối.

**`getDayOfYear()` không phải `getDayOfMonth()`**: ngày 29/2/2024 có `getDayOfMonth() == 29` nhưng `getDayOfYear() == 60`.

### Tạo ngày từ số thứ tự trong năm

Cách ngược với `getDayOfYear()` là `LocalDate.ofYearDay(year, dayOfYear)`:

```java
LocalDate a = LocalDate.ofYearDay(2024, 60); // 2024-02-29
LocalDate b = LocalDate.ofYearDay(2025, 60); // 2025-03-01
```

`LocalDate.ofYearDay(2025, 366)` không hợp lệ và ném `DateTimeException`. Với ngày hiện có, `date.withDayOfYear(1)` trả ngày 1/1 **cùng năm** mà không sửa `date`.

Đừng đánh đồng “ngày thứ mấy trong năm” với “tuần thứ mấy trong năm” hoặc “ngày làm việc thứ mấy trong năm”. Ngày nghỉ, cuối tuần, lịch tài chính và định nghĩa tuần là các quy tắc khác, không được `getDayOfYear()` tự loại trừ/tính hộ.

## 5. Kiểm tra năm nhuận và độ dài tháng/năm

Để biết miền giá trị của ngày, dùng chính API:

```java
LocalDate leap = LocalDate.of(2024, 2, 29);
LocalDate normal = LocalDate.of(2025, 2, 28);

System.out.println(leap.isLeapYear());   // true
System.out.println(leap.lengthOfYear()); // 366
System.out.println(leap.lengthOfMonth());// 29

System.out.println(normal.isLeapYear());   // false
System.out.println(normal.lengthOfYear()); // 365
System.out.println(normal.lengthOfMonth());// 28
```

Trong lịch Gregory/ISO mà `LocalDate` sử dụng, năm chia hết cho 4 thường là nhuận, **trừ** năm chia hết cho 100 nhưng **không** chia hết cho 400. Ví dụ năm 2000 nhuận, năm 1900 không nhuận, năm 2024 nhuận, năm 2025 không nhuận. Hãy ưu tiên `isLeapYear()` thay vì tự viết lại quy tắc khi dữ liệu đã có kiểu `LocalDate`.

Với một tháng bất kỳ, `lengthOfMonth()` phản ánh tháng đó trong năm cụ thể. Để lấy ngày cuối tháng:

```java
LocalDate lastDay = date.withDayOfMonth(date.lengthOfMonth());
```

Điều này an toàn cho tháng 2 dù năm nhuận hay năm thường; không dùng hằng số 28/29/30/31 cố định cho tất cả tháng.

## 6. Đọc trường qua `ChronoField` khi cần API tổng quát

Các getter trực tiếp là lựa chọn dễ đọc nhất cho bài toán thường ngày. Nhưng `LocalDate` còn cung cấp API chung `TemporalAccessor.get(TemporalField)`:

| Getter trực tiếp | API trường tương ứng |
| --- | --- |
| `getYear()` | `get(ChronoField.YEAR)` |
| `getMonthValue()` | `get(ChronoField.MONTH_OF_YEAR)` |
| `getDayOfMonth()` | `get(ChronoField.DAY_OF_MONTH)` |
| `getDayOfWeek().getValue()` | `get(ChronoField.DAY_OF_WEEK)` |
| `getDayOfYear()` | `get(ChronoField.DAY_OF_YEAR)` |

```java
LocalDate date = LocalDate.of(2024, 2, 29);
int ordinal = date.get(ChronoField.DAY_OF_YEAR); // 60
```

(Cần `import java.time.temporal.ChronoField;`.)

`ChronoField` phù hợp với hàm xử lý trường thời gian động, nhưng không phải mọi `TemporalAccessor` đều hỗ trợ mọi trường. Chẳng hạn `LocalTime` không mang trường `YEAR`; khi viết hàm tổng quát nên kiểm tra `isSupported(field)` hoặc xử lý `UnsupportedTemporalTypeException`.

Số thứ trong tuần theo `ChronoField.DAY_OF_WEEK` vẫn là thứ Hai = 1, Chủ nhật = 7. Nếu cần **số thứ trong tuần theo một locale cụ thể**, bạn có thể dùng `WeekFields.of(locale).dayOfWeek()`, với kết quả phụ thuộc ngày đầu tuần trong locale. Đây là trường có ngữ nghĩa khác `ChronoField.DAY_OF_WEEK`; không âm thầm hoán đổi hai giá trị.

## 7. Đọc từ một ngày xác định khác với đọc “hôm nay”

`LocalDate.of(2024, 2, 29)` là một giá trị cố định và các getter luôn cho cùng kết quả. `LocalDate.now()` lại lấy ngày theo **múi giờ mặc định của JVM** và đồng hồ máy tại lúc gọi. Nếu hệ thống chạy trên máy có timezone khác, tại cùng thời điểm UTC có thể cho ngày lịch khác.

Ví dụ, tại `2024-02-29T18:30:00Z`:

- Theo UTC: vẫn là **29/02/2024**.
- Theo `Asia/Ho_Chi_Minh` (UTC+07 tại thời điểm này): đã là **01/03/2024**.

```java
Instant instant = Instant.parse("2024-02-29T18:30:00Z");

LocalDate utcDate = LocalDate.ofInstant(instant, ZoneOffset.UTC);
LocalDate vietnamDate = LocalDate.ofInstant(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utcDate);     // 2024-02-29
System.out.println(vietnamDate); // 2024-03-01
```

Cần `import java.time.Instant;`, `import java.time.ZoneOffset;` và `import java.time.ZoneId;`. `LocalDate.ofInstant` có từ Java 9 nên sử dụng được với Java 17+. Nó chuyển **một instant sang ngày lịch ở một vùng**; bản thân `LocalDate` kết quả vẫn không lưu múi giờ.

Trong nghiệp vụ “hôm nay theo thị trường Việt Nam”, hãy thể hiện vùng rõ ràng, chẳng hạn `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))`. Nếu muốn kiểm thử không phụ thuộc thời gian thật, truyền `Clock` cố định:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-02-29T18:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate today = LocalDate.now(clock); // 2024-03-01
```

Lưu ý `LocalDate.now()` không cho biết giờ/phút; đọc `getDayOfWeek()` hoặc `getDayOfYear()` từ một ngày đã chọn luôn phản ánh **ngày lịch**, không phải thời lượng từ đầu năm tính bằng giây. Nếu dữ liệu đầu vào là `Instant` hoặc `ZonedDateTime`, phải quyết định timezone nghiệp vụ **trước** khi lấy `LocalDate`.

## 8. Ví dụ hoàn chỉnh Java 17+

Tạo tệp **`LocalDateFieldsDemo.java`**:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Month;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.TextStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class LocalDateFieldsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        System.out.println("date = " + date);
        System.out.println("year = " + date.getYear());
        System.out.println("month value = " + date.getMonthValue());
        System.out.println("month enum = " + date.getMonth());
        System.out.println("day of month = " + date.getDayOfMonth());
        System.out.println("day of week = " + date.getDayOfWeek());
        System.out.println("ISO weekday number = "
                + date.getDayOfWeek().getValue());
        System.out.println("day of year = " + date.getDayOfYear());
        System.out.println("ChronoField ordinal = "
                + date.get(ChronoField.DAY_OF_YEAR));
        System.out.println("leap year = " + date.isLeapYear());
        System.out.println("days in month = " + date.lengthOfMonth());
        System.out.println("days in year = " + date.lengthOfYear());

        System.out.println("month in English = "
                + date.getMonth().getDisplayName(
                        TextStyle.FULL, Locale.ENGLISH));
        System.out.println("weekday in English = "
                + date.getDayOfWeek().getDisplayName(
                        TextStyle.FULL, Locale.ENGLISH));

        LocalDate day60Leap = LocalDate.ofYearDay(2024, 60);
        LocalDate day60Normal = LocalDate.ofYearDay(2025, 60);
        System.out.println("2024 day 60 = " + day60Leap);
        System.out.println("2025 day 60 = " + day60Normal);

        boolean invalidDay366 = false;
        try {
            LocalDate.ofYearDay(2025, 366);
        } catch (DateTimeException ex) {
            invalidDay366 = true;
        }
        System.out.println("2025 day 366 invalid = " + invalidDay366);

        DayOfWeek weekday = date.getDayOfWeek();
        boolean weekend = weekday == DayOfWeek.SATURDAY
                || weekday == DayOfWeek.SUNDAY;
        System.out.println("weekend by Sat/Sun rule = " + weekend);
        System.out.println("month enum comparison = "
                + (date.getMonth() == Month.FEBRUARY));

        Instant instant = Instant.parse("2024-02-29T18:30:00Z");
        System.out.println("UTC date = "
                + LocalDate.ofInstant(instant, ZoneOffset.UTC));
        System.out.println("Vietnam date = "
                + LocalDate.ofInstant(
                        instant, ZoneId.of("Asia/Ho_Chi_Minh")));

        Clock fixedClock = Clock.fixed(
                instant, ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("fixed today = " + LocalDate.now(fixedClock));
        System.out.println("original unchanged = " + date);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LocalDateFieldsDemo.java
java LocalDateFieldsDemo
```

Đầu ra dự kiến trên JDK có dữ liệu locale chuẩn:

```text
date = 2024-02-29
year = 2024
month value = 2
month enum = FEBRUARY
day of month = 29
day of week = THURSDAY
ISO weekday number = 4
day of year = 60
ChronoField ordinal = 60
leap year = true
days in month = 29
days in year = 366
month in English = February
weekday in English = Thursday
2024 day 60 = 2024-02-29
2025 day 60 = 2025-03-01
2025 day 366 invalid = true
weekend by Sat/Sun rule = false
month enum comparison = true
UTC date = 2024-02-29
Vietnam date = 2024-03-01
fixed today = 2024-03-01
original unchanged = 2024-02-29
```

Ví dụ minh họa cả getter trực tiếp và `ChronoField`, sự khác biệt số thứ tự ngày ở năm nhuận/năm thường, xử lý ngày không hợp lệ và ảnh hưởng của timezone khi chuyển một `Instant` thành ngày lịch. `LocalDate` đầu vào luôn bất biến; các thao tác chỉ đọc không thể thay đổi nó.

## 9. Lỗi phổ biến và cách xử lý

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `getMonth().ordinal()` để lấy số tháng | Tháng 1 thành 0, tháng 12 thành 11 | Dùng `getMonthValue()` hoặc `getMonth().getValue()` |
| Tưởng `getDayOfWeek().getValue()` trả Chủ nhật = 1 | Lệch lịch theo quy ước ISO | ISO: thứ Hai = 1, Chủ nhật = 7 |
| Đếm `getDayOfYear()` từ 0 | Sai một đơn vị từ ngày 1/1 | Ngày 1/1 có ordinal = 1 |
| Nhầm `getDayOfMonth()` và `getDayOfYear()` | Ngày 29/2 bị hiểu là ngày thứ 29 của năm | Chọn getter theo đơn vị muốn đọc |
| Cho rằng 1/3 luôn là ngày thứ 60 | Năm nhuận có ngày 29/2 | Kiểm tra `isLeapYear()` và `getDayOfYear()` |
| Gọi `ofYearDay(year, 366)` cho mọi năm | Năm thường ném exception | Kiểm tra `lengthOfYear()` hoặc xử lý `DateTimeException` |
| Đọc “hôm nay” bằng timezone mặc định trong hệ thống đa vùng | Có thể khác ngày nghiệp vụ | Chỉ định `ZoneId` hoặc truyền `Clock` |
| Dùng tên thứ/tháng đã dịch để viết logic | Dễ sai theo locale, chữ viết, cách rút gọn | Dùng enum `DayOfWeek`/`Month` |
| Cho rằng `LocalDate` chứa giờ/offset | Không thể xác định instant từ một ngày thuần | Giữ vùng/giờ ở tầng nghiệp vụ khác khi cần |
| Tự tách `"2024-02-29"` để tính thứ hoặc thứ tự ngày | Phải xử lý năm nhuận và lịch dễ sai | Parse thành `LocalDate` rồi dùng API chuyên biệt |

## 10. Áp dụng thực tế

### Hiển thị thông tin của một ngày lịch

Khi người dùng chọn ngày, có thể lấy số ngày/tháng/năm cho form, lấy enum thứ và dùng locale để tạo tên thứ/tháng trên giao diện. Dữ liệu nghiệp vụ nên giữ `LocalDate`, không lưu tên thứ dịch sẵn làm nguồn sự thật vì ngôn ngữ người dùng có thể thay đổi.

### Chỉ mục theo ngày thứ trong năm

Nếu báo cáo cần xác định “ngày thứ 120 của năm”, dùng `getDayOfYear()`. Khi lưu/chia nhóm, dùng khóa **(năm, ngày thứ trong năm)** hoặc ngày ISO đầy đủ. Tháng/ngày tương ứng với số thứ tự có thể khác nhau giữa năm nhuận và năm thường.

### Quy tắc kiểm tra ngày cuối tháng

Nếu lịch trả lương chạy ngày cuối tháng, dùng `date.getDayOfMonth() == date.lengthOfMonth()` thay vì `getDayOfMonth() == 31`. Cách này đúng cả tháng 2 và tháng 30 ngày.

### Lịch làm việc theo thứ

Nếu chỉ yêu cầu loại bỏ thứ Bảy/Chủ nhật, so sánh trực tiếp với `DayOfWeek.SATURDAY` và `DayOfWeek.SUNDAY`. Nếu yêu cầu nghỉ lễ, tuần làm việc đặc thù, cần thêm lịch nghiệp vụ; `LocalDate.getDayOfWeek()` không tự biết ngày nào là ngày nghỉ.

## 11. Tự kiểm tra

1. `LocalDate.of(2024, 2, 29).getDayOfMonth()` là bao nhiêu? → **29**.
2. Cùng ngày đó `getDayOfYear()` là bao nhiêu? → **60**.
3. `getDayOfWeek()` trả giá trị nào cho 29/2/2024? → `THURSDAY`, `getValue() == 4`.
4. Tại sao `LocalDate.ofYearDay(2024, 60)` khác `LocalDate.ofYearDay(2025, 60)`? → Năm 2024 nhuận nên ngày 60 là 29/2; năm 2025 thường nên là 1/3.
5. Có nên gọi `getMonth().ordinal() + 1` để lấy tháng? → Mặc dù cho 1–12 với enum hiện tại, hãy dùng **`getMonthValue()`** vì nói đúng ý nghĩa và tránh phụ thuộc chỉ số enum.
6. Tại cùng instant, vì sao ngày UTC và ngày Việt Nam có thể khác? → Một instant có thể thuộc hai ngày lịch khác nhau khi quy đổi sang múi giờ khác nhau.
7. Khi muốn biết ngày hiện tại theo vùng nghiệp vụ, dùng gì? → `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` hoặc `LocalDate.now(clock)` để dễ kiểm thử.

**Ghi nhớ:** `getYear()`, `getMonthValue()`/`getMonth()`, `getDayOfMonth()`, `getDayOfWeek()` và `getDayOfYear()` đọc **các khía cạnh khác nhau của một ngày lịch**. Thứ trong tuần theo ISO bắt đầu thứ Hai = 1; ngày thứ trong năm bắt đầu từ 1 và phụ thuộc năm nhuận. Khi xác định “hôm nay” từ một instant thực tế, hãy chọn múi giờ trước khi đọc `LocalDate`.
