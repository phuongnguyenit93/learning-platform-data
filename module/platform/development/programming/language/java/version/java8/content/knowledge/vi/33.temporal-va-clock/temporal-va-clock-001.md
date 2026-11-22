# TemporalAccessor và Temporal trong Java: Đọc, truy vấn và điều chỉnh dữ liệu thời gian

**Chủ đề cha:** Temporal và Clock. **Trọng tâm:** Hai interface cốt lõi `java.time.temporal.TemporalAccessor` và `java.time.temporal.Temporal`. Người học cần phân biệt **khả năng đọc trường thời gian** với **khả năng thay đổi giá trị theo đơn vị hoặc bộ điều chỉnh**, chọn đúng `TemporalField`, `TemporalUnit`, `TemporalQuery`, `TemporalAdjuster`, `TemporalAmount`, xử lý các trường/đơn vị không được hỗ trợ và liên hệ với `Clock` khi cần lấy “hiện tại”.

Các interface được giới thiệu từ **Java 8** và vẫn nằm trong API Java SE hiện hành. Những chương trình đầy đủ bên dưới dùng **Java 17+**, có lệnh `javac`/`java` và đầu ra xác định. API standard library sử dụng trong bài vẫn có mặt ở JDK 27; không cần lớp ngày giờ cũ để giải quyết các tác vụ này.

> **Ý chính:** `Temporal extends TemporalAccessor`. **TemporalAccessor** dành cho đọc thông tin qua `isSupported(field)`, `get/getLong`, `range`, `query`; **Temporal** thêm các phép `with`, `plus`, `minus`, `until` và `isSupported(unit)`. Tuy nhiên, một biến được khai báo kiểu `TemporalAccessor` **không thể gọi `plus`** trong Java dù object thực tế có thể là `LocalDate`; hãy chọn interface đúng theo yêu cầu phương thức. Hai interface này cũng **không phải Clock**: `Clock` là nguồn cung cấp thời điểm hiện tại, không phải một ngày–giờ để cộng trừ.

## 1. Vì sao java.time có hai interface?

Các kiểu ngày giờ không chứa cùng lượng thông tin:

- `LocalDate` chứa **năm, tháng, ngày**, nên có thể tính “tháng sau”, “cộng 10 ngày” và “ngày cuối tháng”.
- `LocalTime` chứa **giờ, phút, giây, nano**, nên có thể tính “thêm 30 phút”; không thể suy ra một năm hay ngày lịch.
- `YearMonth` chứa **năm và tháng**, có thể cộng tháng, nhưng không có ngày trong tháng cụ thể.
- `MonthDay` chỉ chứa **tháng và ngày**, không chứa năm, nên không thể quyết định một cách đầy đủ việc “cộng một tháng” qua 29/02 nếu chưa biết năm.
- `Instant` biểu diễn một **thời điểm UTC**, có thể cộng các đơn vị thời lượng thích hợp; nó không trực tiếp biết “tháng nào theo giờ địa phương” khi chưa chọn múi giờ.

Vì vậy Java cung cấp hai mức hợp đồng:

```text
java.time.temporal.TemporalAccessor
       |
       +-- java.time.temporal.Temporal
                 |
                 +-- LocalDate, LocalTime, LocalDateTime,
                     Instant, YearMonth, Year,
                     OffsetDateTime, ZonedDateTime, ...
```

Sơ đồ trên là **minh họa quan hệ interface**, không phải danh sách đầy đủ các loại triển khai. `MonthDay`, `Month` và `DayOfWeek` có thể đóng vai trò `TemporalAccessor` dù **không phải Temporal**. `DateTimeFormatter.parse(...)` có thể trả về một `TemporalAccessor` mô tả kết quả parsing, chưa chắc đó là một object cụ thể như `LocalDate`.

### 1.1. Bảng phân biệt nhanh

| Đặc điểm | `TemporalAccessor` | `Temporal` |
| --- | --- | --- |
| Có từ | Java 8 | Java 8 |
| Quan hệ kế thừa | Interface nền | `extends TemporalAccessor` |
| Đọc giá trị `ChronoField` | `get` / `getLong` | Có, kế thừa |
| Kiểm tra có field không | `isSupported(TemporalField)` | Có, kế thừa |
| Đọc giới hạn field | `range(TemporalField)` | Có, kế thừa |
| Truy vấn tùy biến | `query(TemporalQuery<R>)` | Có, kế thừa |
| Kiểm tra có cộng được unit không | Không có overload unit | `isSupported(TemporalUnit)` |
| Đặt field mới | Không | `with(TemporalField, long)` |
| Điều chỉnh theo quy tắc | Không | `with(TemporalAdjuster)` |
| Cộng/trừ khoảng | Không | `plus` / `minus` |
| Tính số đơn vị đến thời điểm khác | Không | `until(Temporal, TemporalUnit)` |
| Object ví dụ | `MonthDay`, `Month`, `DayOfWeek`, kết quả parser | `LocalDate`, `LocalTime`, `YearMonth`, `Instant` |

**Đừng suy luận “đọc được = sửa được”.** `MonthDay.of(2, 29)` cho phép đọc tháng/day, nhưng không tự biết năm nào để thực hiện một phép cộng ngày/tháng tổng quát một cách nhất quán. `TemporalAccessor` cho phép diễn đạt mô hình chỉ có thông tin đọc được.

### 1.2. “Read-only” có nghĩa mọi implementation đều immutable?

`TemporalAccessor` là **giao diện chỉ đọc**, tức hợp đồng của nó không cung cấp các phép chỉnh sửa thông qua interface. Điều đó **không biến mọi đối tượng tùy biến triển khai nó thành bất biến**. Các lớp phổ biến trong `java.time` như `LocalDate`, `YearMonth`, `MonthDay`, `Instant` được thiết kế bất biến. `Temporal` có tên “read-write access” ở cấp framework, nhưng các phương thức tiêu chuẩn trả **giá trị đã điều chỉnh** thay vì sửa object đầu vào; theo hợp đồng `Temporal`, implementation không được sửa object nguồn khi áp dụng các phép tính.

**Điểm cần ghi nhớ:** `Temporal.with/plus/minus` không phải setter in-place. Phải nhận kết quả mới:

```java
LocalDate original = LocalDate.of(2024, 1, 31);
LocalDate changed = original.plusMonths(1);
// original vẫn là 2024-01-31; changed là 2024-02-29
```

Đây là **đoạn mã bên trong phương thức**, import `java.time.LocalDate`.

## 2. TemporalAccessor: Năm phương thức nền

API của `TemporalAccessor` gồm:

```java
boolean isSupported(TemporalField field);
ValueRange range(TemporalField field);
int get(TemporalField field);
long getLong(TemporalField field);
<R> R query(TemporalQuery<R> query);
```

Đoạn trên trình bày **chữ ký phương thức interface**, không phải một chương trình Java độc lập. Các đối tượng truyền vào thường là các hằng của `ChronoField` hoặc một `TemporalQuery`.

### 2.1. `isSupported(TemporalField)`

Trả true nếu đối tượng hỗ trợ đọc trường được yêu cầu:

```java
TemporalAccessor date = LocalDate.of(2024, 2, 29);

boolean hasYear = date.isSupported(ChronoField.YEAR);       // true
boolean hasHour = date.isSupported(ChronoField.HOUR_OF_DAY); // false
```

Đây là đoạn trong phương thức, import `java.time.temporal.TemporalAccessor` và `ChronoField`. `LocalDate` không có giờ, nên không thể đọc `HOUR_OF_DAY` từ nó.

**Không nhầm với `Temporal.isSupported(TemporalUnit)`**: một overload kiểm tra **trường cần đọc** như `YEAR`, còn overload kia kiểm tra **đơn vị có thể cộng/trừ** như `DAYS`, `MONTHS` hoặc `HOURS`.

### 2.2. `get(TemporalField)`

`get` trả một `int`. Thích hợp với các trường có phạm vi int, ví dụ `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `HOUR_OF_DAY`, `DAY_OF_WEEK`.

```java
int year = date.get(ChronoField.YEAR);          // 2024
int month = date.get(ChronoField.MONTH_OF_YEAR); // 2
int day = date.get(ChronoField.DAY_OF_MONTH);    // 29
```

Đây là đoạn trong phương thức có biến `date` kiểu `TemporalAccessor` trỏ tới `LocalDate`. Một field không được hỗ trợ có thể ném `UnsupportedTemporalTypeException` (là một `DateTimeException`).

### 2.3. `getLong(TemporalField)` — không chỉ cho con số “lớn”

`getLong` trả một `long`, dùng được khi field có thể nằm **ngoài phạm vi int** hoặc bản thân field được thiết kế chỉ truy xuất an toàn qua `getLong`.

Ví dụ: `ChronoField.EPOCH_DAY` trên `LocalDate` và `ChronoField.INSTANT_SECONDS` trên `Instant`:

```java
long epochDay = date.getLong(ChronoField.EPOCH_DAY);
long seconds = Instant.parse(
        "2024-02-29T00:00:00Z")
        .getLong(ChronoField.INSTANT_SECONDS);
```

**Bẫy quan trọng:** Ngay cả khi `date.isSupported(EPOCH_DAY) == true` và giá trị cụ thể chưa vượt int, `date.get(EPOCH_DAY)` vẫn có thể **ném exception** vì field này có **phạm vi hợp lệ vượt int**; dùng `getLong(EPOCH_DAY)`. Tương tự, đừng dùng `Instant.get(INSTANT_SECONDS)`; dùng `getLong`. Do đó, `isSupported(field) == true` **không bảo đảm `get(field)` luôn an toàn**. Với một field tổng quát, `getLong` thường là lựa chọn robust hơn.

### 2.4. `range(TemporalField)`

`range(field)` trả `ValueRange` mô tả phạm vi giá trị hợp lệ **theo chính đối tượng đó** khi API hỗ trợ. Điều này đặc biệt hữu ích khi phạm vi thay đổi theo tháng/năm:

```java
LocalDate feb = LocalDate.of(2024, 2, 15);
ValueRange range = feb.range(ChronoField.DAY_OF_MONTH);
// 1 - 29 trong tháng 2 năm nhuận 2024
```

Đây là đoạn trong phương thức, import `java.time.temporal.ValueRange` và `ChronoField`. Đối với tháng 2/2023, `LocalDate.of(2023,2,15).range(DAY_OF_MONTH)` cho 1–28. `ChronoField.DAY_OF_MONTH.range()` tổng quát hơn, có thể mô tả 1–28/29/30/31; `temporal.range(field)` xét **bối cảnh của temporal cụ thể**.

`ValueRange.isValidValue(long)` hữu ích để kiểm tra đầu vào nhưng không thay thế hoàn toàn việc tạo ngày hợp lệ: quan hệ giữa các field, lịch và nghiệp vụ có thể cần validation bổ sung.

### 2.5. `query(TemporalQuery<R>)`

`query` nhận một chiến lược truy vấn, chẳng hạn:

- `TemporalQueries.localDate()`: trích `LocalDate` nếu có thể.
- `TemporalQueries.localTime()`: trích `LocalTime` nếu có thể.
- `TemporalQueries.zone()` / `zoneId()`: tìm zone; **zoneId và zone không đồng nghĩa** nếu chỉ có offset.
- `TemporalQueries.offset()`: truy xuất `ZoneOffset` nếu có.
- `TemporalQueries.chronology()`: hỏi về hệ lịch, có thể trả `null`.
- `TemporalQueries.precision()`: độ chính xác nhỏ nhất được biểu diễn, có thể trả `null`.

Một `TemporalQuery` **có quyền trả null** khi dữ liệu không có. Ví dụ `MonthDay` không đủ thông tin năm để tạo `LocalDate`, vì vậy `MonthDay.of(2,29).query(TemporalQueries.localDate())` trả `null`. Không buộc mọi truy vấn đều trả một ngày đầy đủ.

## 3. Chương trình Java 17+: Đọc các TemporalAccessor khác nhau

Tạo file **`TemporalAccessorReadDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.MonthDay;
import java.time.temporal.ChronoField;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;

public class TemporalAccessorReadDemo {
    public static void main(String[] args) {
        TemporalAccessor date = LocalDate.of(2024, 2, 29);
        TemporalAccessor time = LocalTime.of(9, 30);
        TemporalAccessor monthDay = MonthDay.of(2, 29);
        TemporalAccessor instant =
                Instant.parse("2024-02-29T00:00:00Z");

        System.out.println("LocalDate year/month/day: "
                + date.get(ChronoField.YEAR) + "/"
                + date.get(ChronoField.MONTH_OF_YEAR) + "/"
                + date.get(ChronoField.DAY_OF_MONTH));

        System.out.println("LocalTime hour: "
                + time.get(ChronoField.HOUR_OF_DAY));
        System.out.println("LocalTime supports day: "
                + time.isSupported(ChronoField.DAY_OF_MONTH));
        System.out.println("MonthDay supports year: "
                + monthDay.isSupported(ChronoField.YEAR));
        System.out.println("MonthDay is Temporal: "
                + (monthDay instanceof Temporal));

        System.out.println("Instant epoch seconds: "
                + instant.getLong(ChronoField.INSTANT_SECONDS));
        System.out.println("LocalDate supports epoch day: "
                + date.isSupported(ChronoField.EPOCH_DAY));
        System.out.println("LocalDate epoch day: "
                + date.getLong(ChronoField.EPOCH_DAY));

        boolean intRejected = false;
        try {
            date.get(ChronoField.EPOCH_DAY);
        } catch (DateTimeException ex) {
            intRejected = true;
        }
        System.out.println("get(EPOCH_DAY) rejected: "
                + intRejected);

        System.out.println("Date precision: "
                + date.query(TemporalQueries.precision()));
        System.out.println("MonthDay precision: "
                + monthDay.query(TemporalQueries.precision()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TemporalAccessorReadDemo.java
java TemporalAccessorReadDemo
```

**Stdout xác định:**

```text
LocalDate year/month/day: 2024/2/29
LocalTime hour: 9
LocalTime supports day: false
MonthDay supports year: false
MonthDay is Temporal: false
Instant epoch seconds: 1709164800
LocalDate supports epoch day: true
LocalDate epoch day: 19782
get(EPOCH_DAY) rejected: true
Date precision: Days
MonthDay precision: null
```

**Điều cần hiểu:**

1. `LocalDate` hỗ trợ năm, tháng và ngày nhưng không chứa giờ.
2. `LocalTime` có giờ nhưng không chứa ngày trong tháng.
3. `MonthDay` là `TemporalAccessor`, **không** phải `Temporal` vì không có năm để giải quyết phép cộng ngày/tháng tổng quát.
4. `Instant` chứa số giây từ Unix epoch, nhưng không tự có năm/tháng theo vùng nếu chưa kết hợp với zone.
5. `isSupported(EPOCH_DAY)` là true, nhưng `get(EPOCH_DAY)` bị từ chối; `getLong(EPOCH_DAY)` đúng.
6. Kết quả truy vấn có thể là `null`; `MonthDay` không có độ chính xác theo đơn vị thời gian như một ngày/tháng/năm đầy đủ để trả qua `TemporalQueries.precision()`.

## 4. Parse vào TemporalAccessor và lấy kiểu cụ thể

`DateTimeFormatter.parse(CharSequence)` trả `TemporalAccessor`, vì một chuỗi thời gian có thể chứa **một phần hoặc nhiều trường** mà chưa biết loại Java cuối cùng cần tạo.

Ví dụ:

```java
TemporalAccessor parsed =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(
                "2024-02-29T10:15:30+07:00");
```

Đây là đoạn trong phương thức, import `java.time.format.DateTimeFormatter` và `java.time.temporal.TemporalAccessor`.

Từ đối tượng `parsed`, có thể truy vấn:

```java
LocalDate date = parsed.query(TemporalQueries.localDate());
LocalTime time = parsed.query(TemporalQueries.localTime());
ZoneOffset offset = parsed.query(TemporalQueries.offset());
```

**Quan trọng về zone:**

- `TemporalQueries.offset()` tìm offset và trả `+07:00`.
- `TemporalQueries.zoneId()` đòi một **ZoneId tường minh** có mặt trong dữ liệu parse; nếu input chỉ có offset mà không có region zone ID, thường trả `null`.
- `TemporalQueries.zone()` có thể trả **offset như một ZoneId** nếu không có region zone ID; với input trên, trả `+07:00`.

Đừng coi chuỗi `+07:00` đã cho biết lịch sử/luật tương lai của một vùng như `Asia/Ho_Chi_Minh`. Offset là độ lệch, zone vùng là tập quy tắc.

### 4.1. `LocalDate.from` và `LocalDateTime.from`

Để chuyển sang kiểu cụ thể khi input đủ thông tin, dùng factory:

```java
LocalDate date = LocalDate.from(parsed);
LocalDateTime dateTime = LocalDateTime.from(parsed);
```

Đây là đoạn trong một phương thức có biến `parsed`. Nếu `TemporalAccessor` **không đủ trường** để tạo đối tượng yêu cầu, phương thức `from` ném `DateTimeException`. Ví dụ `LocalDate.from(MonthDay.of(2,29))` không thể suy ra một năm.

**Không cast bừa `(LocalDate) parsed`.** `DateTimeFormatter.parse` có thể trả một implementation nội bộ của `TemporalAccessor`; factory `from` đọc các field để xây đúng kiểu, không cần giả định class runtime của parsed object.

## 5. Ví dụ hoàn chỉnh: Parser, TemporalQueries và dữ liệu thiếu

Tạo file **`TemporalParseQueryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;

public class TemporalParseQueryDemo {
    public static void main(String[] args) {
        TemporalAccessor parsed =
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(
                        "2024-02-29T10:15:30+07:00");

        System.out.println("Parsed date: "
                + parsed.query(TemporalQueries.localDate()));
        System.out.println("Parsed time: "
                + parsed.query(TemporalQueries.localTime()));
        System.out.println("Parsed offset: "
                + parsed.query(TemporalQueries.offset()));
        System.out.println("Parsed zoneId: "
                + parsed.query(TemporalQueries.zoneId()));
        System.out.println("Parsed zone: "
                + parsed.query(TemporalQueries.zone()));
        System.out.println("LocalDate.from: "
                + LocalDate.from(parsed));

        TemporalAccessor partial = MonthDay.of(2, 29);
        System.out.println("MonthDay localDate: "
                + partial.query(TemporalQueries.localDate()));
        System.out.println("MonthDay localTime: "
                + partial.query(TemporalQueries.localTime()));
    }
}
```

Chạy:

```bash
javac --release 17 TemporalParseQueryDemo.java
java TemporalParseQueryDemo
```

**Stdout:**

```text
Parsed date: 2024-02-29
Parsed time: 10:15:30
Parsed offset: +07:00
Parsed zoneId: null
Parsed zone: +07:00
LocalDate.from: 2024-02-29
MonthDay localDate: null
MonthDay localTime: null
```

Mã cho thấy `TemporalAccessor` là **đích trả về chung của parser**, không phải chỉ một superclass của LocalDate. Một truy vấn `localDate` trên đối tượng `MonthDay` không thể tự đoán năm; nó trả null. Nếu API của bạn không chấp nhận thiếu thông tin, hãy **validate sau parse** hoặc dùng kiểu đích với hợp đồng chặt.

### 5.1. Dùng `parse(text, query)` khi biết kiểu đích

`DateTimeFormatter` có overload:

```java
LocalDate parsedDate = DateTimeFormatter.ISO_LOCAL_DATE
        .parse("2024-02-29", LocalDate::from);
```

Đây là đoạn trong phương thức. `LocalDate::from` là `TemporalQuery<LocalDate>` theo cách sử dụng method reference; việc parse và chuyển kiểu được kết hợp một cách rõ ràng. Khi biết ngay đầu vào là ngày ISO đầy đủ, cách đơn giản nhất vẫn là `LocalDate.parse("2024-02-29")`.

## 6. Temporal: Cấp độ cho phép tính và điều chỉnh

`Temporal` kế thừa toàn bộ khả năng đọc của `TemporalAccessor` và thêm:

```java
boolean isSupported(TemporalUnit unit);
Temporal with(TemporalField field, long newValue);
Temporal with(TemporalAdjuster adjuster);
Temporal plus(long amount, TemporalUnit unit);
Temporal plus(TemporalAmount amount);
Temporal minus(long amount, TemporalUnit unit);
Temporal minus(TemporalAmount amount);
long until(Temporal endExclusive, TemporalUnit unit);
```

Đây là bảng **chữ ký API minh họa**; các overload từ interface có thể được triển khai covariant bởi kiểu cụ thể như `LocalDate`. `Temporal` có thể hoạt động trên nhiều miền thời gian, nhưng **không có nghĩa tất cả Temporal hỗ trợ mọi đơn vị hoặc field**.

### 6.1. Hai overload của `isSupported`

Với `Temporal t = LocalDate.of(2024,2,29)`:

```java
boolean hasYear = t.isSupported(ChronoField.YEAR);  // true
boolean addDays = t.isSupported(ChronoUnit.DAYS);  // true
boolean addHours = t.isSupported(ChronoUnit.HOURS); // false
```

Đây là đoạn trong phương thức với import `ChronoField`, `ChronoUnit`. `TemporalField` là **trường dữ liệu** có thể đọc, ví dụ YEAR hoặc DAY_OF_MONTH; `TemporalUnit` là **đơn vị thao tác**, ví dụ DAYS hoặc HOURS. Khi gọi generic API, kiểm tra overload đúng theo đối số.

`LocalTime` có thể cộng giờ/phút nhưng không cộng “một ngày lịch có năm” theo `ChronoUnit.DAYS`; `YearMonth` cộng tháng/năm nhưng không hỗ trợ DAYS; `Instant` cộng đơn vị thời lượng thích hợp nhưng không cộng một tháng lịch.

### 6.2. `with(field, value)`: Chỉnh một trường

`with` tạo giá trị mới có một trường được cập nhật:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalDate firstDay = date.with(
        ChronoField.DAY_OF_MONTH, 1); // 2024-02-01
```

Đây là đoạn trong phương thức. `date.with(DAY_OF_MONTH,31)` trong tháng 2 **không thể tạo ngày 31/02**; nó ném `DateTimeException` vì giá trị trực tiếp của DAY_OF_MONTH ngoài phạm vi hiện tại. Trong khi đó `date.with(MONTH_OF_YEAR,3)` là phép đổi tháng cho ngày đang có và có quy tắc điều chỉnh ngày nếu cần.

### 6.3. `with(adjuster)`: Áp dụng một quy tắc

`TemporalAdjusters.lastDayOfMonth()` tạo một `TemporalAdjuster`, có thể truyền vào `with`:

```java
LocalDate date = LocalDate.of(2024, 2, 15);
LocalDate end = date.with(
        TemporalAdjusters.lastDayOfMonth());
// 2024-02-29
```

Đây là đoạn trong phương thức. `TemporalAdjusters.next(DayOfWeek.MONDAY)` tìm thứ Hai **sau ngày đang xét** (không bao gồm hôm nay nếu đã là thứ Hai); `nextOrSame` bao gồm trường hợp ngày hiện tại khớp. Không viết logic lịch lặp trên một object thiếu ngày tháng rồi mong API tự suy ra.

### 6.4. `plus/minus`: Số lượng và đơn vị

```java
Temporal t = LocalDate.of(2024, 1, 31);

Temporal feb = t.plus(1, ChronoUnit.MONTHS);
Temporal mar = t.plus(2, ChronoUnit.MONTHS);
Temporal chained = feb.plus(1, ChronoUnit.MONTHS);
```

Đây là đoạn trong phương thức. `feb` là 2024-02-29; `mar` là 2024-03-31; `chained` là 2024-03-29. **Phép cộng tháng có điều chỉnh ngày cuối tháng**, nên cộng hai lần một tháng có thể khác cộng một lần hai tháng. Đừng tự đề ra bất biến cộng/trừ phải luôn hoàn tác chính xác.

`plus(TemporalAmount)` nhận đối tượng như `Period.ofMonths(1)` hoặc `Duration.ofHours(1)` nếu kiểu Temporal đích hỗ trợ. `TemporalAmount` là **một interface khác**, không phải Temporal; nó mô tả số lượng để cộng/trừ vào Temporal. `Period` dùng năm/tháng/ngày, `Duration` dùng giây/nano.

### 6.5. `until`: Tính khoảng theo một đơn vị

`t.until(end, ChronoUnit.DAYS)` tính số **đơn vị đầy đủ** từ t đến end với các quy tắc của kiểu Temporal. Nó có thể âm nếu end đứng trước t.

```java
LocalDate start = LocalDate.of(2024, 1, 31);
LocalDate end = LocalDate.of(2024, 2, 29);
long days = start.until(end, ChronoUnit.DAYS); // 29
```

Đây là đoạn trong phương thức. `ChronoUnit.DAYS.between(start, end)` cũng có thể diễn đạt yêu cầu này. Nếu muốn kết quả thành **năm/tháng/ngày theo lịch**, dùng `Period.between(start, end)`; nếu muốn **giây thực tế** giữa hai sự kiện, dùng `Duration.between(startInstant, endInstant)`.

**Lưu ý:** `until(end, unit)` trả **số đơn vị trọn vẹn** theo đơn vị được yêu cầu; khi đơn vị là MONTHS, không có nghĩa là “làm tròn lên một tháng nếu có một vài ngày dư”.

## 7. Chương trình Java 17+: Temporal.plus, with và until

Tạo file **`TemporalMutationDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAdjusters;

public class TemporalMutationDemo {
    public static void main(String[] args) {
        Temporal base = LocalDate.of(2024, 1, 31);
        Temporal feb = base.plus(1, ChronoUnit.MONTHS);

        System.out.println("Base: " + base);
        System.out.println("Plus one month: " + feb);
        System.out.println("Plus two months: "
                + base.plus(2, ChronoUnit.MONTHS));
        System.out.println("Chained: "
                + feb.plus(1, ChronoUnit.MONTHS));
        System.out.println("With day 1: "
                + base.with(ChronoField.DAY_OF_MONTH, 1));
        System.out.println("February last day: "
                + feb.with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("Days until leap day: "
                + base.until(LocalDate.of(2024, 2, 29),
                        ChronoUnit.DAYS));

        System.out.println("Date supports DAYS: "
                + base.isSupported(ChronoUnit.DAYS));
        System.out.println("Date supports HOURS: "
                + base.isSupported(ChronoUnit.HOURS));

        Temporal ym = YearMonth.of(2024, 2);
        System.out.println("YearMonth + MONTHS: "
                + ym.plus(1, ChronoUnit.MONTHS));
        System.out.println("YearMonth supports DAYS: "
                + ym.isSupported(ChronoUnit.DAYS));

        boolean hoursRejected = false;
        try {
            base.plus(1, ChronoUnit.HOURS);
        } catch (DateTimeException ex) {
            hoursRejected = true;
        }
        System.out.println("Date HOURS rejected: "
                + hoursRejected);
    }
}
```

Chạy:

```bash
javac --release 17 TemporalMutationDemo.java
java TemporalMutationDemo
```

**Stdout:**

```text
Base: 2024-01-31
Plus one month: 2024-02-29
Plus two months: 2024-03-31
Chained: 2024-03-29
With day 1: 2024-01-01
February last day: 2024-02-29
Days until leap day: 29
Date supports DAYS: true
Date supports HOURS: false
YearMonth + MONTHS: 2024-03
YearMonth supports DAYS: false
Date HOURS rejected: true
```

**Giải thích:** Interface `Temporal` cho phép gọi cùng một họ phương thức trên `LocalDate` và `YearMonth` nhưng tập `ChronoUnit` hỗ trợ **khác nhau**. `LocalDate` không hỗ trợ cộng giờ khi không có giờ; `YearMonth` không hỗ trợ DAYS vì không chứa ngày. Giá trị `base` không thay đổi, đúng ngữ nghĩa tạo kết quả mới của các kiểu ngày giờ standard.

## 8. Hệ sinh thái java.time.temporal: Năm interface có vai trò khác nhau

Tên các interface giống nhau nên dễ bị nhầm. Bảng sau phân tách theo **chiều tương tác**:

| Interface | Trả lời câu hỏi gì? | Ví dụ |
| --- | --- | --- |
| `TemporalAccessor` | “Đọc được field nào và giá trị bao nhiêu?” | `date.getLong(EPOCH_DAY)` |
| `Temporal` | “Có thể tính/điều chỉnh bản sao ngày giờ này không?” | `date.plus(1, DAYS)` |
| `TemporalField` | “Một trường ngày giờ được định nghĩa/đọc/đặt như thế nào?” | `ChronoField.DAY_OF_MONTH` |
| `TemporalUnit` | “Một đơn vị thời gian được cộng/trừ/đếm thế nào?” | `ChronoUnit.MONTHS` |
| `TemporalQuery<R>` | “Trích hoặc tính thông tin kiểu R từ một TemporalAccessor?” | `TemporalQueries.localDate()` |
| `TemporalAdjuster` | “Áp dụng một quy tắc điều chỉnh lên Temporal?” | `TemporalAdjusters.lastDayOfMonth()` |
| `TemporalAmount` | “Tổng lượng thời gian để cộng/trừ vào Temporal?” | `Period.ofMonths(2)`, `Duration.ofHours(3)` |

### 8.1. TemporalField và ChronoField

`ChronoField` là một **enum triển khai TemporalField**, mô tả các trường thông dụng:

- `YEAR`, `YEAR_OF_ERA`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `DAY_OF_WEEK`.
- `HOUR_OF_DAY`, `MINUTE_OF_HOUR`, `SECOND_OF_MINUTE`, `NANO_OF_SECOND`.
- `EPOCH_DAY`, `INSTANT_SECONDS`, `OFFSET_SECONDS`.

Không phải kiểu nào cũng hỗ trợ các field giống nhau. `Instant` hỗ trợ `INSTANT_SECONDS` nhưng không thể trực tiếp đọc `MONTH_OF_YEAR` theo giờ địa phương nếu chưa cung cấp zone. `LocalDate` hỗ trợ `EPOCH_DAY` nhưng không có `INSTANT_SECONDS` vì một ngày lịch chưa xác định lúc nào/múi giờ nào.

`TemporalField` còn có hành vi như `isSupportedBy(temporal)`, `rangeRefinedBy(temporal)`, `getFrom(temporal)` và `adjustInto(temporal,newValue)`. Ở mã sử dụng bình thường, thường **dễ đọc hơn** khi gọi `temporal.isSupported(field)`, `temporal.getLong(field)`, `temporal.with(field,value)`.

### 8.2. TemporalUnit và ChronoUnit

`ChronoUnit` là một **enum triển khai TemporalUnit**: NANOS, MICROS, MILLIS, SECONDS, MINUTES, HOURS, HALF_DAYS, DAYS, WEEKS, MONTHS, YEARS, DECADES, CENTURIES, MILLENNIA, ERAS, FOREVER.

Một số đơn vị là **ước lượng** về thời lượng vật lý. Ví dụ MONTHS/YEARS không có số giây cố định, và DAYS qua chuyển giờ mùa có thể là 23/25 giờ thực tế. `ChronoUnit.DAYS.getDuration()` trả 24 giờ theo ý nghĩa **thời lượng ước lượng tiêu chuẩn của đơn vị**, nhưng không phải bằng chứng mọi ngày lịch ở mọi zone có đúng 86.400 giây.

`TemporalUnit` có các hàm như `isSupportedBy(Temporal)`, `addTo(Temporal,long)`, `between(Temporal,Temporal)`. Code nghiệp vụ thường rõ hơn khi dùng `temporal.plus(n, unit)` và `start.until(end, unit)`.

### 8.3. TemporalAdjuster khác TemporalAmount

- `TemporalAdjuster` là **hàm biến đổi theo quy tắc**: “ngày cuối tháng”, “thứ Hai tiếp theo”, “ngày làm việc theo lịch tùy chỉnh”. Interface có `adjustInto(Temporal)`, thường được dùng với `temporal.with(adjuster)`.
- `TemporalAmount` là **lượng** thời gian: “2 tháng + 3 ngày”, “90 phút”. Interface có `addTo(Temporal)`, `subtractFrom(Temporal)`, `get(TemporalUnit)`, `getUnits()`.

Ví dụ hai ý định khác nhau:

```java
LocalDate date = LocalDate.of(2024, 2, 15);
LocalDate endOfMonth = date.with(
        TemporalAdjusters.lastDayOfMonth()); // 2024-02-29
LocalDate oneMonthLater = date.plus(
        Period.ofMonths(1)); // 2024-03-15
```

Đây là đoạn trong phương thức. `lastDayOfMonth()` là một **quy tắc điều chỉnh**, còn `Period.ofMonths(1)` là một **lượng theo lịch**. Dùng đúng khái niệm sẽ tránh làm code generic khó hiểu.

## 9. TemporalQuery tùy biến: Đọc được nhưng không bắt buộc đủ thông tin

Nếu một hàm chỉ cần truy vấn dữ liệu, nhận `TemporalAccessor`, không yêu cầu đối tượng có thể cộng/trừ.

Ví dụ một query xuất năm–tháng ISO nếu đủ hai trường:

```java
TemporalQuery<String> yearMonthLabel = temporal -> {
    if (!temporal.isSupported(ChronoField.YEAR)
            || !temporal.isSupported(ChronoField.MONTH_OF_YEAR)) {
        return "n/a";
    }
    return String.format(
            Locale.ROOT, "%04d-%02d",
            temporal.get(ChronoField.YEAR),
            temporal.get(ChronoField.MONTH_OF_YEAR));
};
```

Đây là đoạn trong phương thức, import `java.time.temporal.TemporalQuery`, `ChronoField` và `java.util.Locale`. `TemporalQuery<R>` là một **functional interface**, nên có thể cài bằng lambda; nó **không được giả định** mọi TemporalAccessor có cả YEAR và MONTH_OF_YEAR.

Áp dụng:

```java
String first = LocalDate.of(2024, 2, 29)
        .query(yearMonthLabel); // "2024-02"

String unknown = MonthDay.of(2, 29)
        .query(yearMonthLabel); // "n/a"
```

Đây là đoạn trong phương thức; `MonthDay` không có YEAR. Mẫu này chủ động trả chuỗi "n/a"; các `TemporalQueries` chuẩn có thể trả `null`. Nếu thiết kế API công khai, nên quyết định rõ trường hợp thiếu thông tin là **null, Optional, sentinel, hay exception**, thay vì đổi qua lại trong các nơi sử dụng.

### 9.1. Custom TemporalQuery có thể làm được gì?

Một `TemporalQuery<R>` có thể đọc nhiều `TemporalField` từ `TemporalAccessor` và tính một kết quả `R`, ví dụ:

- Trích năm–tháng hoặc mã báo cáo từ một ngày.
- Lấy quy tắc format phù hợp khi field tồn tại.
- Hỏi xem có đủ YEAR/MONTH/DAY để tính ngày hay chưa.
- Trích độ chính xác hoặc offset khi parse dữ liệu.
- Phát hiện một trạng thái hợp lệ của mô hình nhập liệu một phần.

**Không** biến query thành cách bí mật sửa object khác. Query thuộc **chiều đọc**, còn việc điều chỉnh nằm ở `Temporal`/`TemporalAdjuster`.

## 10. Chương trình hoàn chỉnh: TemporalQuery, TemporalField và OptionalInt

Tạo file **`TemporalQueryDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalField;
import java.time.temporal.TemporalQuery;
import java.util.Locale;
import java.util.OptionalInt;

public class TemporalQueryDemo {
    static OptionalInt readMonth(TemporalAccessor value) {
        TemporalField field = ChronoField.MONTH_OF_YEAR;

        if (!value.isSupported(field)) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(value.get(field));
    }

    public static void main(String[] args) {
        TemporalQuery<String> yearMonthLabel = temporal -> {
            if (!temporal.isSupported(ChronoField.YEAR)
                    || !temporal.isSupported(
                            ChronoField.MONTH_OF_YEAR)) {
                return "n/a";
            }
            return String.format(
                    Locale.ROOT, "%04d-%02d",
                    temporal.get(ChronoField.YEAR),
                    temporal.get(ChronoField.MONTH_OF_YEAR));
        };

        LocalDate date = LocalDate.of(2024, 2, 29);
        MonthDay partial = MonthDay.of(2, 29);
        Instant instant =
                Instant.parse("2024-02-29T00:00:00Z");

        System.out.println("Date label: "
                + date.query(yearMonthLabel));
        System.out.println("MonthDay label: "
                + partial.query(yearMonthLabel));
        System.out.println("Date month: "
                + readMonth(date));
        System.out.println("MonthDay month: "
                + readMonth(partial));
        System.out.println("Instant month: "
                + readMonth(instant));
    }
}
```

Chạy:

```bash
javac --release 17 TemporalQueryDemo.java
java TemporalQueryDemo
```

**Stdout:**

```text
Date label: 2024-02
MonthDay label: n/a
Date month: OptionalInt[2]
MonthDay month: OptionalInt[2]
Instant month: OptionalInt.empty
```

Cả hàm `readMonth` và query đều **chỉ yêu cầu `TemporalAccessor`** vì chúng không thực hiện phép cộng/trừ. Một `Instant` không có tháng địa phương, nên trả `OptionalInt.empty`; muốn biết tháng ở địa điểm cụ thể, trước tiên phải dùng `instant.atZone(zone)`.

**Lựa chọn `OptionalInt`:** Khi một field có thể không tồn tại, `OptionalInt.empty()` tránh nhầm “không có tháng” với một số như 0. Nhưng đừng tạo Optional cho mọi field nếu mô hình đã bảo đảm field được hỗ trợ; dùng kiểu cụ thể `LocalDate` và `getMonthValue()` sẽ đơn giản hơn.

## 11. Thiết kế API generic: Chọn TemporalAccessor hay Temporal?

### 11.1. Hàm chỉ đọc nên nhận TemporalAccessor

```java
static boolean hasDate(TemporalAccessor value) {
    return value.isSupported(ChronoField.YEAR)
            && value.isSupported(ChronoField.MONTH_OF_YEAR)
            && value.isSupported(ChronoField.DAY_OF_MONTH);
}
```

Đây là **đoạn khai báo method bên trong một class**, không phải file độc lập. Với `LocalDate` thường trả true; với `MonthDay` hoặc `LocalTime` trả false. **Không có nghĩa** ba field hiện diện tự động xác nhận mọi tổ hợp giá trị hợp lệ nếu implementation tùy biến không tuân hợp đồng; khi cần ngày ISO thật, hãy chuyển bằng `LocalDate.from(value)` và xử lý exception.

### 11.2. Hàm có tính toán cần Temporal

```java
static Temporal shift(
        Temporal input, long amount, TemporalUnit unit) {
    if (!input.isSupported(unit)) {
        throw new IllegalArgumentException(
                "unsupported unit: " + unit);
    }
    return input.plus(amount, unit);
}
```

Đây là **method bên trong class**, import `Temporal` và `TemporalUnit`. Nó có thể nhận `LocalDate` cộng DAYS hoặc `LocalTime` cộng MINUTES; nhưng `LocalDate` cộng HOURS không hợp lệ.

**Nếu method nhận `TemporalAccessor`**, lời gọi `input.plus(...)` không biên dịch được vì interface này không khai báo `plus`. Đừng ép mọi biến `TemporalAccessor` sang `Temporal` mà không kiểm tra. Một `MonthDay` có thể đọc tháng/ngày nhưng không phải Temporal; cast sang Temporal sẽ gây `ClassCastException`.

### 11.3. Trả kiểu đúng

`Temporal.plus` ở cấp interface trả về `Temporal`, vì vậy hàm generic `shift` phía trên cũng trả `Temporal`. Các implementation như `LocalDate.plus(...)` thường có **kiểu trả về cụ thể** như `LocalDate`, cho phép code rõ ràng hơn khi bạn biết loại dữ liệu.

Nếu API của ứng dụng **chỉ chấp nhận ngày**, thường nên viết:

```java
static LocalDate addDays(LocalDate date, long days) {
    return date.plusDays(days);
}
```

Đây là một method minh họa. **Không cố generic hóa** mọi thao tác chỉ để nhận Temporal nếu nghiệp vụ rõ ràng chỉ làm việc với LocalDate. Thiết kế generic hữu ích khi thật sự có nhiều kiểu ngày–giờ cùng một hợp đồng đầu vào và tập field/unit hỗ trợ.

### 11.4. Giữ đúng calendar / elapsed semantics

`Temporal` là interface tổng quát và không quyết định thay nghiệp vụ. `ChronoUnit.DAYS` trên `ZonedDateTime` tuân theo phép tính ngày lịch địa phương, còn `ChronoUnit.HOURS` có ý nghĩa thời lượng trên timeline thực qua DST. Tương tự, `Period.ofDays(1)` và `Duration.ofDays(1)` có thể khác nhau khi áp dụng vào ZonedDateTime qua đợt chuyển giờ.

Nếu code cần tính khoảng giây giữa hai sự kiện, hãy chọn `Instant` hoặc hai mốc `ZonedDateTime.toInstant()` rồi dùng `Duration.between(...)`. Nếu cần tăng tháng của một lịch hóa đơn, dùng `LocalDate.plusMonths` hoặc `YearMonth.plusMonths` theo quy tắc cuối tháng được chọn.

## 12. Temporal và các phép điều chỉnh: Các lỗi biên cần hiểu

### 12.1. Không phải mọi phép with đều giống nhau

`LocalDate.of(2024,1,31).with(ChronoField.MONTH_OF_YEAR,2)` có thể điều chỉnh ngày cho hợp lệ trong tháng mới, ra 29/02/2024. Nhưng `LocalDate.of(2024,2,29).with(ChronoField.DAY_OF_MONTH,31)` yêu cầu **ngày 31 tháng 2**, ngoài phạm vi hiện tại, nên ném `DateTimeException`. Đừng dùng cùng kỳ vọng “tự làm tròn” với mọi field.

### 12.2. Cộng một tháng liên tiếp có thể không kết hợp

`LocalDate.of(2024,1,31).plusMonths(1).plusMonths(1)` → **2024-03-29**, còn `plusMonths(2)` → **2024-03-31**. Khi xây lịch “luôn cuối tháng”, hãy dùng `YearMonth.plusMonths(i).atEndOfMonth()` từ tháng gốc thay vì cộng dồn qua ngày đã điều chỉnh.

### 12.3. Một Temporal có thể không chứa zone

`LocalDateTime` thực hiện `Temporal` nhưng **không chứa ZoneId hoặc offset**. Một local date-time trong vùng có DST gap/overlap có thể ứng với 0 hoặc 2 instant. `LocalDateTime.atZone(zone)` phải giải quyết theo luật vùng; nó không phải là một setter không ảnh hưởng dữ liệu.

### 12.4. Instant không tự có ngày/tháng theo vùng

`Instant.parse("2024-02-29T00:00:00Z").get(ChronoField.MONTH_OF_YEAR)` không hợp lệ. Muốn tháng của thời điểm này theo một vùng:

```java
Instant instant =
        Instant.parse("2024-02-29T00:00:00Z");

int month = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"))
        .getMonthValue(); // 2
```

Đây là đoạn trong phương thức. Một instant ở hai khu vực khác nhau có thể rơi vào hai **ngày/tháng** địa phương khác nhau gần nửa đêm.

### 12.5. Interface không thay thế validation

Ngay cả khi `temporal.isSupported(field)` trả true, thao tác có thể thất bại nếu:

- Field chỉ an toàn qua `getLong`, không qua `get`.
- `with(field, value)` nhận giá trị ngoài `range(field)`.
- Unit không hỗ trợ, hoặc tính toán làm tràn giới hạn loại ngày–giờ.
- Parser không có đủ field để chuyển sang `LocalDate`, `LocalDateTime` hoặc `ZonedDateTime`.
- Một zone/local nằm trong gap hoặc overlap, cần lựa chọn policy.
- Đối tượng null: các interface tham chiếu không cấm null khi biến chứa dữ liệu thiếu.

Kiểm thử các trường hợp này bằng **ngoại lệ đúng kiểu** và expected cụ thể, không dựa vào giả định gọi phương thức luôn thành công nếu có đủ tên field.

## 13. Clock trong nhóm “Temporal và Clock”: Vai trò tách biệt

`java.time.Clock` là **nguồn cung cấp hiện tại** với một zone; bản thân `Clock` **không triển khai `TemporalAccessor` hay `Temporal`**. Nó không phải ngày giờ có field.YEAR hay phương thức plus(DAYS). `Instant.now(clock)`, `LocalDate.now(clock)`, `LocalDateTime.now(clock)` và `ZonedDateTime.now(clock)` sử dụng cùng clock nhưng trả những **kiểu ngày giờ khác nhau**.

Ví dụ một clock cố định:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-28T23:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là đoạn trong phương thức. Với UTC 23:30 ngày 28/02/2024, giờ địa phương ở vùng `Asia/Ho_Chi_Minh` là **06:30 ngày 29/02/2024**.

**Giá trị sử dụng trong test:** Inject `Clock` vào service thay vì gọi `LocalDate.now()`/`Instant.now()` tùy ý ở nhiều nơi. Có thể viết unit test cố định, tái lập và không phụ thuộc ngày thực tại.

### 13.1. Java 17+ demo: Clock không phải Temporal

Tạo file **`TemporalClockDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TemporalClockDemo {
    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2024-02-28T23:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Clock zone: " + fixed.getZone());
        System.out.println("Clock instant: " + Instant.now(fixed));
        System.out.println("Clock date: " + LocalDate.now(fixed));
        System.out.println("Clock time: " + LocalTime.now(fixed));
        System.out.println("Clock dateTime: "
                + LocalDateTime.now(fixed));
        System.out.println("Clock zoned: "
                + ZonedDateTime.now(fixed));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 TemporalClockDemo.java
java TemporalClockDemo
```

**Stdout:**

```text
Clock zone: Asia/Ho_Chi_Minh
Clock instant: 2024-02-28T23:30:00Z
Clock date: 2024-02-29
Clock time: 06:30
Clock dateTime: 2024-02-29T06:30
Clock zoned: 2024-02-29T06:30+07:00[Asia/Ho_Chi_Minh]
```

**Đọc kết quả:** Clock cung cấp thời điểm 23:30Z và region zone; `Instant.now` trả UTC instant, `LocalDate.now` tính ngày tại zone, `LocalDateTime.now` chứa ngày–giờ địa phương nhưng không giữ zone, còn `ZonedDateTime.now` giữ vùng và offset được giải quyết. Clock không phải một interface chung để đọc YEAR hay cộng DAYS.

`Clock.systemDefaultZone()` và `LocalDate.now()` hợp lệ khi sản phẩm **cố ý** dùng zone mặc định, nhưng trong unit test muốn kết quả tái lập, ưu tiên `Clock.fixed` và zone nêu rõ.

## 14. Tổng quan exception và an toàn kiểu

Một nhóm lỗi phổ biến:

| Tình huống | Kết quả / cách xử lý |
| --- | --- |
| `LocalTime.get(DAY_OF_MONTH)` | `UnsupportedTemporalTypeException` |
| `LocalDate.plus(1, HOURS)` | `UnsupportedTemporalTypeException` |
| `LocalDate.get(EPOCH_DAY)` | `DateTimeException` do field không lấy được qua int; dùng `getLong` |
| `Instant.get(INSTANT_SECONDS)` | `DateTimeException`; dùng `getLong` |
| `LocalDate.of(2023,2,29)` | `DateTimeException` vì ngày không hợp lệ |
| `LocalDate.from(MonthDay.of(2,29))` | `DateTimeException` vì thiếu năm |
| `(Temporal) MonthDay.of(2,29)` | Không hợp lệ; nếu cast từ `TemporalAccessor` tại runtime, `ClassCastException` |
| `Temporal.with(DAY_OF_MONTH, 31)` trên tháng 2 | `DateTimeException` |
| Cộng vượt `LocalDate.MAX` | Có thể ném `DateTimeException` |
| Giá trị `null` được đưa vào method không nhận null | Thường `NullPointerException` |
| `TemporalQueries.localDate()` trên giá trị thiếu ngày | Có thể trả `null`, không nhất thiết ném lỗi |

`UnsupportedTemporalTypeException` **kế thừa `DateTimeException`**. Trong một ứng dụng, nên dùng các lỗi đủ chi tiết để người dùng biết đầu vào sai, field không tồn tại hay yêu cầu chuyển đổi bất khả thi. Tránh `catch (Exception)` rồi âm thầm trả ngày mặc định: việc này dễ che mất bug dữ liệu.

### 14.1. Không nên ép kiểu theo interface chỉ đọc

Đoạn sau là **phản ví dụ**, không chạy như code production:

```java
TemporalAccessor input = MonthDay.of(2, 29);
Temporal wrong = (Temporal) input; // ClassCastException lúc chạy
```

Compiler cho phép cast ở biến `TemporalAccessor` vì interface này có thể trỏ tới nhiều implementation, nhưng tại runtime `MonthDay` **không triển khai Temporal**. Nếu cần tính toán ngày–tháng, lấy thông tin năm từ **nguồn nghiệp vụ** rồi tạo `LocalDate`/`YearMonth` trước khi cộng/trừ.

### 14.2. Ngoại lệ không đồng nghĩa field không tồn tại

Khi `isSupported(field) == true` nhưng `get(field)` ném lỗi vì phạm vi int, chuyển sang `getLong`. Nếu `isSupported(field) == false`, đừng thử `getLong` và hy vọng Java tự suy ra. Hai trường hợp này khác nhau:

- **Field không được hỗ trợ** bởi temporal: thiếu thông tin hoặc không thuộc domain của loại đó.
- **Field được hỗ trợ nhưng không thể biểu diễn qua int**: dùng `getLong` theo hợp đồng.

Kiểm thử nên có **ít nhất một ví dụ cho từng trường hợp**.

## 15. Checklist kiểm thử cho TemporalAccessor/Temporal

| Trường hợp | Kiểm thử cần có |
| --- | --- |
| `LocalDate` có `YEAR/MONTH/DAY` | `isSupported == true`; get đúng |
| `LocalDate` không có giờ | `isSupported(HOUR_OF_DAY) == false` |
| `LocalTime` không có ngày | `isSupported(DAY_OF_MONTH) == false` |
| `MonthDay` chỉ chứa tháng/ngày | Không có YEAR, không phải Temporal |
| `Instant` chỉ chứa instant fields | `getLong(INSTANT_SECONDS)` |
| `EPOCH_DAY` | `isSupported == true`, nhưng `get` không thích hợp; dùng `getLong` |
| `range(DAY_OF_MONTH)` năm nhuận | Tháng 2/2024: 1–29 |
| `range(DAY_OF_MONTH)` năm thường | Tháng 2/2023: 1–28 |
| `query(localDate)` từ formatter đầy đủ | Trả LocalDate hợp lệ |
| `query(localDate)` từ MonthDay | Trả null |
| `query(zoneId)` từ text chỉ có offset | Trả null |
| `query(zone)` từ text chỉ có offset | Trả offset dạng ZoneId |
| `Temporal.isSupported(DAYS)` trên LocalDate | true |
| `Temporal.isSupported(HOURS)` trên LocalDate | false, plus HOURS bị từ chối |
| `Temporal.isSupported(MONTHS)` trên YearMonth | true |
| `Temporal.isSupported(DAYS)` trên YearMonth | false |
| `with(field,value)` ngày tháng hợp lệ/không hợp lệ | Có điều chỉnh hoặc exception theo field |
| `plus(MONTHS)` ở cuối tháng | Không giả định phép cộng nhiều bước bằng một bước |
| `until(...,DAYS)` trên LocalDate | Khoảng ngày đầy đủ đúng |
| `TemporalQuery` custom khi field thiếu | Không đọc field thiếu |
| `Clock.fixed` và zone | Output tái lập, không phụ thuộc ngày chạy |
| Ngày DST, gap/overlap | Phân biệt Period/Duration và vùng/offset |

Nếu API generic được dùng bởi nhiều class thời gian, hãy **thử mỗi class được hỗ trợ**. Một method chỉ chạy thành công với `LocalDate` nhưng được công bố là nhận mọi `Temporal` có thể thất bại khi gọi với `YearMonth`, `LocalTime` hoặc `Instant` nếu không có guard.

## 16. Java 17+: Bài kiểm thử tự động về hợp đồng interface

Tạo file **`TemporalBoundaryChecks.java`**. Chương trình không phụ thuộc cờ `-ea` vì dùng `check` để chủ động ném `AssertionError` khi phát hiện sai:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.MonthDay;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalQueries;

public class TemporalBoundaryChecks {
    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        TemporalAccessor date = LocalDate.of(2024, 2, 29);
        TemporalAccessor time = LocalTime.of(9, 30);
        TemporalAccessor partial = MonthDay.of(2, 29);

        check(date.isSupported(ChronoField.YEAR),
                "date must support YEAR");
        check(!date.isSupported(ChronoField.HOUR_OF_DAY),
                "date must not support HOUR");
        check(!time.isSupported(ChronoField.DAY_OF_MONTH),
                "time must not support DAY_OF_MONTH");
        check(!partial.isSupported(ChronoField.YEAR),
                "MonthDay must not support YEAR");
        check(!(partial instanceof Temporal),
                "MonthDay must not implement Temporal");
        System.out.println("Field support: PASS");

        check(date.getLong(ChronoField.EPOCH_DAY) == 19782,
                "wrong epoch day");
        boolean intRejected = false;
        try {
            date.get(ChronoField.EPOCH_DAY);
        } catch (DateTimeException ex) {
            intRejected = true;
        }
        check(intRejected, "get(EPOCH_DAY) should fail");
        System.out.println("getLong: PASS");

        check(date.range(ChronoField.DAY_OF_MONTH)
                .getMaximum() == 29,
                "wrong leap month range");
        check(LocalDate.of(2023, 2, 15)
                .range(ChronoField.DAY_OF_MONTH)
                .getMaximum() == 28,
                "wrong common month range");
        System.out.println("ValueRange: PASS");

        check(partial.query(TemporalQueries.localDate()) == null,
                "partial unexpectedly has LocalDate");
        check(date.query(TemporalQueries.localDate())
                .equals(LocalDate.of(2024, 2, 29)),
                "wrong local date query");
        System.out.println("Queries: PASS");

        Temporal base = LocalDate.of(2024, 1, 31);
        check(base.isSupported(ChronoUnit.DAYS),
                "LocalDate must support DAYS");
        check(!base.isSupported(ChronoUnit.HOURS),
                "LocalDate must not support HOURS");
        check(base.plus(1, ChronoUnit.MONTHS)
                .equals(LocalDate.of(2024, 2, 29)),
                "wrong month adjustment");
        check(base.until(LocalDate.of(2024, 2, 29),
                ChronoUnit.DAYS) == 29,
                "wrong day difference");
        System.out.println("Temporal arithmetic: PASS");

        Temporal ym = YearMonth.of(2024, 2);
        check(ym.isSupported(ChronoUnit.MONTHS)
                && !ym.isSupported(ChronoUnit.DAYS),
                "wrong YearMonth units");
        check(ym.plus(1, ChronoUnit.MONTHS)
                .equals(YearMonth.of(2024, 3)),
                "wrong YearMonth shift");
        System.out.println("YearMonth: PASS");

        Instant instant =
                Instant.parse("2024-02-29T00:00:00Z");
        check(instant.getLong(ChronoField.INSTANT_SECONDS)
                == 1709164800L,
                "wrong epoch seconds");
        check(!instant.isSupported(ChronoField.MONTH_OF_YEAR),
                "Instant has no local month");
        System.out.println("Instant: PASS");
        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 TemporalBoundaryChecks.java
java TemporalBoundaryChecks
```

**Stdout:**

```text
Field support: PASS
getLong: PASS
ValueRange: PASS
Queries: PASS
Temporal arithmetic: PASS
YearMonth: PASS
Instant: PASS
All checks: PASS
```

**Tại sao những test này cần thiết?** Chúng phân biệt field support với unit support, phát hiện chỗ `getLong` bắt buộc thay vì `get`, kiểm tra giới hạn ngày tháng 2 năm nhuận và năm thường, xác minh `TemporalQuery` có thể trả null, xác minh `YearMonth` không có DAYS, và ngăn lỗi đọc tháng địa phương trực tiếp từ `Instant`. Những assertion dùng dữ liệu cố định và không phụ thuộc đồng hồ thực.

## 17. Các lỗi thường gặp khi học TemporalAccessor/Temporal

1. **Tưởng `TemporalAccessor` có thể gọi `plus`:** interface chỉ đọc; chỉ Temporal có phép toán này.
2. **Tưởng mọi TemporalAccessor cũng là Temporal:** `MonthDay`, `Month`, `DayOfWeek` là phản ví dụ.
3. **Tưởng Temporal là một class cụ thể:** đây là **interface**, còn LocalDate/Instant/YearMonth là implementation với cấu trúc khác nhau.
4. **Tưởng “read-write” trong docs nghĩa object gốc bị sửa:** các phép chuẩn tạo giá trị đã điều chỉnh; nhận biến kết quả mới.
5. **Nhầm `TemporalField` với `TemporalUnit`:** YEAR là field, YEARS là unit.
6. **Nhầm hai overload `isSupported`:** một field hỗ trợ đọc khác với unit hỗ trợ cộng/trừ.
7. **Gọi `get` cho `EPOCH_DAY` hoặc `INSTANT_SECONDS`:** dù field được hỗ trợ, phạm vi vượt int; dùng `getLong`.
8. **Gọi `getLong` trên field không hỗ trợ và mong nó được suy ra:** không có thông tin thì vẫn lỗi.
9. **Đọc `MONTH_OF_YEAR` trực tiếp từ Instant:** thiếu zone, không có tháng địa phương.
10. **Đọc `YEAR` trực tiếp từ LocalTime:** chỉ có giờ, không có ngày/năm.
11. **Sử dụng `MonthDay` rồi đòi cộng tháng generic:** thiếu năm để xác nhận tháng 2 nhuận.
12. **Ép `(LocalDate) formatter.parse(...)`:** kết quả parse là TemporalAccessor, chưa chắc LocalDate; dùng `LocalDate.from` hoặc parse với query.
13. **Cho rằng `TemporalQueries.zoneId()` là `offset()`:** dữ liệu chỉ có offset không chứa vùng địa lý.
14. **Gọi `TemporalQueries.localDate()` trên dữ liệu chỉ có MonthDay và không xử lý null:** chưa đủ năm.
15. **Dùng `range(DAY_OF_MONTH)` cố định 1–31 cho mọi tháng:** tháng 2 có 28/29 ngày; dùng range theo temporal cụ thể.
16. **Cho rằng every Temporal.supports(DAYS):** YearMonth hỗ trợ MONTHS nhưng không DAYS.
17. **Dùng `LocalDate.plus(1,HOURS)`:** LocalDate không có giờ.
18. **Dùng `with(DAY_OF_MONTH,31)` trên tháng 2 và mong Java tự nhận ngày cuối tháng:** field update không hợp lệ sẽ báo lỗi.
19. **Cho rằng cộng một tháng rồi cộng thêm một tháng luôn bằng cộng thẳng hai tháng:** khác ở ngày 31/01.
20. **Trộn `Period` với `Duration`:** lịch theo ngày/tháng không đồng nghĩa số giây tuyệt đối.
21. **Dùng `until(...,MONTHS)` rồi tưởng tính số tháng làm tròn lên:** API tính số đơn vị đầy đủ theo ngữ nghĩa loại dữ liệu.
22. **Dùng một TemporalAdjuster trên mọi Temporal mà không xét field hỗ trợ:** “last day of month” không phù hợp với LocalTime.
23. **Dùng Clock như một Temporal để đọc YEAR hoặc cộng DAYS:** Clock là nguồn cung cấp now/zone, không phải ngày giờ.
24. **Trong test dùng LocalDate.now() và đòi output cố định:** nên inject Clock.fixed.
25. **Coi ZoneOffset và ZoneId vùng là giống nhau:** fixed offset không tự mang quy tắc tương lai của một quốc gia.
26. **Bỏ qua DateTimeException/UnsupportedTemporalTypeException:** field/unit không hỗ trợ là vấn đề contract, không phải chỉ sai dữ liệu.
27. **Giả định mọi ngày giờ có cùng khả năng lập lịch:** LocalDate, YearMonth, LocalTime, Instant chứa lượng thông tin khác nhau.
28. **Tạo hàm nhận Temporal để xử lý một LocalDate duy nhất:** có thể làm code khó đọc hơn mà không có lợi ích generic.
29. **Tạo query phụ thuộc side effects:** query nên đọc và trả kết quả, không sửa trạng thái ngoài.
30. **Chỉ kiểm thử ngày bình thường:** cần trường thiếu, năm nhuận, cuối tháng, các đơn vị unsupported và dữ liệu parser thiếu.

## 18. Câu hỏi tự kiểm tra

1. `TemporalAccessor` và `Temporal` khác nhau về khả năng nào?
2. `Temporal extends TemporalAccessor` hay chiều ngược lại?
3. `MonthDay.of(2,29)` có phải Temporal không? Vì sao?
4. Khi `date.isSupported(EPOCH_DAY)` true, có thể gọi `date.get(EPOCH_DAY)` không?
5. Sự khác nhau giữa `TemporalField.YEAR` và `TemporalUnit.YEARS` là gì? Hằng chuẩn cần viết chính xác thế nào?
6. `LocalDate.isSupported(ChronoUnit.HOURS)` trả gì và vì sao?
7. `YearMonth` hỗ trợ cộng MONTHS nhưng có hỗ trợ DAYS không?
8. `DateTimeFormatter.parse` trả kiểu gì? Có nên ép trực tiếp sang LocalDate không?
9. `TemporalQueries.zoneId()` có nhất thiết giống `TemporalQueries.zone()` khi chuỗi chỉ có `+07:00`?
10. Khi parse input thiếu YEAR, `TemporalQueries.localDate()` có thể trả gì?
11. `Temporal.plus(TemporalAmount)` khác `Temporal.with(TemporalAdjuster)` về ý định thế nào?
12. `LocalDate.of(2024,1,31).plusMonths(1).plusMonths(1)` là ngày nào? `plusMonths(2)` là ngày nào?
13. `Instant` có biết tháng theo giờ địa phương trước khi chọn zone không?
14. Vì sao `Clock.fixed` hữu ích với unit test?
15. Khi thực sự chỉ cần LocalDate, có nên buộc mọi method nhận Temporal tổng quát không?
16. `Temporal.until(end,DAYS)` có tự trả Period năm–tháng–ngày không?

**Gợi ý đáp án:** (1) Accessor đọc, Temporal thêm with/plus/minus/until và hỗ trợ đơn vị. (2) Temporal extends TemporalAccessor. (3) Không; nó không có năm để phép cộng tổng quát đầy đủ. (4) Không; EPOCH_DAY cần `getLong`. (5) Field là trường được đọc/đặt, Unit là đơn vị cộng/trừ; dùng `ChronoField.YEAR` và `ChronoUnit.YEARS`, không có các hằng `TemporalField.YEAR` hay `TemporalUnit.YEARS`. (6) False vì LocalDate không có giờ. (7) Không. (8) TemporalAccessor; dùng `LocalDate.from` hoặc parse với query. (9) Không; zoneId có thể null còn zone là ZoneOffset. (10) null. (11) Cộng lượng thời gian so với áp dụng quy tắc điều chỉnh. (12) 2024-03-29 và 2024-03-31. (13) Không; phải `atZone(zone)`. (14) Giữ Instant và zone cố định. (15) Không; dùng LocalDate nếu domain chỉ có ngày. (16) Không; trả long số ngày trọn; `Period.between` là API khác.

**Kết luận:** `TemporalAccessor` và `Temporal` là **hai cấp hợp đồng**, không phải hai class ngày giờ. `TemporalAccessor` cho phép đọc field, range và query từ cả những biểu diễn chưa đầy đủ như MonthDay hay kết quả formatter; `Temporal` áp dụng các phép cộng/trừ, điều chỉnh và đếm đơn vị lên những kiểu đủ thông tin như LocalDate, YearMonth, Instant. Khi xây API, hãy chọn **interface tối thiểu đúng với thao tác**, kiểm tra cả field/unit được hỗ trợ, dùng `getLong` đúng chỗ, hiểu query có thể trả null, giữ nguyên dữ liệu lịch/zone và dùng Clock riêng để lấy thời gian hiện tại. Cách này giúp logic ngày–giờ rõ ràng, an toàn kiểu và dễ kiểm thử trên Java hiện hành.

## Tài liệu chính thức Java SE — API còn áp dụng

- `TemporalAccessor` — isSupported(field), range, get/getLong và query: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalAccessor.html
- `Temporal` — extends TemporalAccessor, isSupported(unit), with, plus, minus, until: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/Temporal.html
- `TemporalField` và `ChronoField` — định nghĩa trường và các hằng thông dụng: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalField.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/ChronoField.html
- `TemporalUnit` và `ChronoUnit` — đơn vị cộng/trừ và tính khoảng: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalUnit.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/ChronoUnit.html
- `TemporalQuery` / `TemporalQueries` — truy vấn giá trị thời gian: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalQuery.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalQueries.html
- `TemporalAdjuster` / `TemporalAdjusters` — điều chỉnh theo quy tắc: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalAdjuster.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalAdjusters.html
- `TemporalAmount` / `Period` / `Duration` — khoảng theo lịch và thời lượng: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalAmount.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html
- `MonthDay` — TemporalAccessor nhưng không phải Temporal: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/MonthDay.html
- `LocalDate`, `YearMonth`, `Instant` — những kiểu temporal cụ thể: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html và https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html
- `Clock` — nguồn cung cấp now và zone cho test: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html
