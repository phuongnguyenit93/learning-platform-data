# TemporalField, TemporalUnit và kiểm tra khả năng hỗ trợ trong Java

**`TemporalField`** và **`TemporalUnit`** là hai interface của `java.time.temporal`, giúp chương trình Java trả lời hai câu hỏi khác nhau: **“Giá trị ngày giờ có trường nào?”** và **“Ta có thể tính toán với đơn vị nào?”**. Các interface được đưa vào cùng JSR 310 ở **Java 8** và vẫn là API chính thức hiện hành.

Ví dụ cùng là “thời gian” nhưng:
- `LocalDate` có **YEAR**, **MONTH_OF_YEAR**, **DAY_OF_MONTH**; không có **HOUR_OF_DAY**.
- `LocalTime` có **HOUR_OF_DAY**, **MINUTE_OF_HOUR**, **NANO_OF_DAY**; không có **DAY_OF_MONTH**.
- `LocalDateTime` có trường ngày và giờ, nhưng **không có INSTANT_SECONDS** vì chưa chọn múi giờ/offset.
- `Instant` có **INSTANT_SECONDS**, **NANO_OF_SECOND**, nhưng không tự chứa **YEAR** hay giờ địa phương khi chưa chọn `ZoneId`.
- `LocalDate` hỗ trợ cộng **DAYS**, **MONTHS**, **YEARS**, nhưng **không hỗ trợ HOURS**; `LocalTime` thì ngược lại.

Bài học cung cấp mô hình type, API đọc/điều chỉnh/đo khoảng, cách kiểm tra khả năng hỗ trợ trước khi thao tác, ngoại lệ, các trường mở rộng `IsoFields`/`WeekFields`, quan hệ với `Clock` và các ví dụ **Java 17+ độc lập đã chạy kiểm thử**. Hầu hết API cốt lõi vẫn tương thích Java 8; các ví dụ không dùng kiến thức lỗi thời. Khi API nào có ngữ nghĩa đặc biệt hoặc phụ thuộc type, bài học nêu rõ thay vì suy diễn từ tên phương thức.

## 1. Phân biệt field, unit và amount

Đây là ba khái niệm rất dễ bị gộp:

| Khái niệm | Câu hỏi được trả lời | Interface / kiểu thường dùng | Ví dụ |
| --- | --- | --- | --- |
| **Field** | Thành phần nào nằm trong giá trị? | `TemporalField` / `ChronoField` | `DAY_OF_MONTH`, `HOUR_OF_DAY` |
| **Unit** | Đơn vị nào dùng để cộng/trừ/đếm? | `TemporalUnit` / `ChronoUnit` | `DAYS`, `HOURS`, `MONTHS` |
| **Amount** | Có **bao nhiêu** đơn vị? | `TemporalAmount`, `Duration`, `Period` | `Duration.ofMinutes(90)`, `Period.ofMonths(2)` |

`ChronoField.DAY_OF_MONTH` và `ChronoUnit.DAYS` **không cùng một thứ**. Field trả giá trị như **ngày 29 trong tháng**; unit DAYS cho phép **thêm 2 ngày** hoặc **đếm số ngày giữa hai date**.

Ví dụ (**đoạn mã bên trong một phương thức, đã import `java.time.*` và `java.time.temporal.*`**):

```java
LocalDate date = LocalDate.of(2024, 2, 29);

int day = date.get(ChronoField.DAY_OF_MONTH);   // 29
LocalDate later = date.plus(2, ChronoUnit.DAYS); // 2024-03-02
long days = ChronoUnit.DAYS.between(
        date, later);                           // 2
```

Không dùng `ChronoField.DAY_OF_MONTH` ở nơi API yêu cầu `TemporalUnit`, hay dùng `ChronoUnit.DAYS` ở nơi API yêu cầu `TemporalField`: chúng mô tả hai chiều khác nhau của mô hình ngày giờ.

## 2. `TemporalAccessor` và `Temporal`: đọc hay điều chỉnh?

Hai interface nền:

- **`TemporalAccessor`** cho phép **truy vấn** một giá trị ngày giờ: `isSupported(TemporalField)`, `range(TemporalField)`, `get(TemporalField)`, `getLong(TemporalField)` và `query(TemporalQuery)`.
- **`Temporal`** **mở rộng `TemporalAccessor`**, bổ sung thao tác điều chỉnh và tính toán: `isSupported(TemporalUnit)`, `with(field,value)`, `plus(amount,unit)`, `minus(...)`, `until(end,unit)`.

Các kiểu quen thuộc như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime` triển khai `Temporal`. Một số kiểu chuyên biệt chỉ có những hợp đồng cần thiết: ví dụ `MonthDay` có thể đọc field nhưng không tự là một ngày hoàn chỉnh để cộng mọi unit.

Vì sao cần phân biệt?
- Hàm chỉ cần đọc **một trường** có thể nhận `TemporalAccessor`, tránh yêu cầu khả năng sửa đổi không cần thiết.
- Hàm cần `plus(1, ChronoUnit.DAYS)` phải nhận `Temporal` và **kiểm tra unit được hỗ trợ**.
- Một `Temporal` có nhiều method nhưng **không có nghĩa mọi field và unit đều được hỗ trợ**.
- Các lớp java.time chuẩn được thiết kế **immutable**: lời gọi `with`/`plus` tạo bản sao theo hợp đồng của type, không thay đổi giá trị gốc.

Ví dụ `LocalDate` là Temporal nhưng không có giờ; việc triển khai interface không biến nó thành “ngày + giờ đầy đủ”.

## 3. `ChronoField`: tập trường tiêu chuẩn

`ChronoField` là enum triển khai `TemporalField`, gồm nhiều trường của lịch ISO và trục thời gian. Một số nhóm quan trọng:

| Nhóm | Trường | Ý nghĩa |
| --- | --- | --- |
| Lịch | `YEAR` | Năm theo proleptic calendar |
| Lịch | `YEAR_OF_ERA`, `ERA` | Năm theo niên đại và era |
| Lịch | `MONTH_OF_YEAR` | Tháng 1–12 |
| Lịch | `DAY_OF_MONTH` | Ngày trong tháng đang xét |
| Lịch | `DAY_OF_YEAR` | Ngày trong năm |
| Lịch | `DAY_OF_WEEK` | Thứ 1–7 theo quy ước ISO |
| Lịch | `EPOCH_DAY` | Số **ngày ISO** từ 1970-01-01 |
| Giờ | `HOUR_OF_DAY` | Giờ 0–23 |
| Giờ | `MINUTE_OF_HOUR` | Phút trong giờ |
| Giờ | `SECOND_OF_MINUTE` | Giây trong phút |
| Giờ | `SECOND_OF_DAY` | Số giây từ đầu ngày |
| Giờ | `NANO_OF_SECOND` | Nano nằm trong giây |
| Giờ | `NANO_OF_DAY` | Tổng nano từ đầu ngày |
| Timeline | `INSTANT_SECONDS` | Epoch seconds của một instant |
| Zone | `OFFSET_SECONDS` | Offset UTC ở đơn vị giây |

**Không phải kiểu nào cũng có tất cả trường.** `LocalDateTime` có thể đọc `HOUR_OF_DAY` nhưng không thể tự đọc `INSTANT_SECONDS` vì thiếu zone/offset. Một `Instant` có epoch seconds nhưng chưa có “ngày trong tháng” độc lập với khu vực được chọn.

Nên ưu tiên getter chuyên biệt khi biết type, ví dụ `date.getYear()` rõ hơn `date.get(ChronoField.YEAR)`. Cách truy cập qua `ChronoField` hữu ích khi viết **thư viện/utility xử lý các TemporalAccessor khác nhau** hoặc cần chọn field động.

## 4. Kiểm tra hỗ trợ field bằng `isSupported(TemporalField)`

Trước khi đọc field chưa chắc tồn tại:

```java
TemporalAccessor value = LocalDate.of(2024, 2, 29);

if (value.isSupported(ChronoField.DAY_OF_MONTH)) {
    int day = value.get(ChronoField.DAY_OF_MONTH);
}

boolean hasHour =
        value.isSupported(ChronoField.HOUR_OF_DAY); // false
```

Đoạn minh họa trong phương thức có import `java.time.*` và `java.time.temporal.*`.

Một số kết quả có ý nghĩa:

| Value | Field | `isSupported(field)` |
| --- | --- | --- |
| `LocalDate.of(2024,2,29)` | `YEAR` | true |
| `LocalDate.of(2024,2,29)` | `HOUR_OF_DAY` | **false** |
| `LocalTime.of(15,30)` | `DAY_OF_MONTH` | **false** |
| `LocalDateTime.of(2024,2,29,15,30)` | `HOUR_OF_DAY` | true |
| `LocalDateTime.of(2024,2,29,15,30)` | `INSTANT_SECONDS` | **false** |
| `Instant.parse("2024-02-29T00:00:00Z")` | `INSTANT_SECONDS` | true |
| `Instant.parse("2024-02-29T00:00:00Z")` | `YEAR` | **false** |

**Field không hỗ trợ không có nghĩa giá trị bằng 0 hoặc null.** Nó có nghĩa field **không thuộc thông tin/khả năng mà type đang biểu diễn**. Nếu vẫn `get(...)` hoặc `getLong(...)`, API có thể ném `UnsupportedTemporalTypeException`.

Khi biết luôn kiểu cụ thể, hãy dùng getter trực tiếp. Dùng `isSupported` khi field đến từ đối số, metadata, plugin hay API generic, không thêm kiểm tra thừa cho mọi getter của `LocalDate`.

## 5. Chương trình Java độc lập: các field được hỗ trợ

Tạo tệp `FieldSupportDemo.java`:

```java
import java.time.*;
import java.time.temporal.ChronoField;

public class FieldSupportDemo {
    public static void main(String[] args) {
        LocalDate d = LocalDate.of(2024, 2, 29);
        LocalTime t = LocalTime.of(23, 59, 58, 123_456_789);
        LocalDateTime dt = LocalDateTime.of(d, t);
        Instant instant = Instant.parse(
                "2024-02-29T00:00:00Z");

        System.out.println("date year = " +
                d.get(ChronoField.YEAR));
        System.out.println("date day-of-year = " +
                d.get(ChronoField.DAY_OF_YEAR));
        System.out.println("date epoch day = " +
                d.getLong(ChronoField.EPOCH_DAY));
        System.out.println("date hour supported = " +
                d.isSupported(ChronoField.HOUR_OF_DAY));

        System.out.println("time date field supported = " +
                t.isSupported(ChronoField.DAY_OF_MONTH));
        System.out.println("time nano-of-day = " +
                t.getLong(ChronoField.NANO_OF_DAY));
        System.out.println("date-time hour = " +
                dt.get(ChronoField.HOUR_OF_DAY));
        System.out.println("date-time instant supported = " +
                dt.isSupported(ChronoField.INSTANT_SECONDS));

        System.out.println("instant seconds = " +
                instant.getLong(ChronoField.INSTANT_SECONDS));
        System.out.println("instant year supported = " +
                instant.isSupported(ChronoField.YEAR));
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 FieldSupportDemo.java
java FieldSupportDemo
```

Đầu ra đã được kiểm tra:

```text
date year = 2024
date day-of-year = 60
date epoch day = 19782
date hour supported = false
time date field supported = false
time nano-of-day = 86398123456789
date-time hour = 23
date-time instant supported = false
instant seconds = 1709164800
instant year supported = false
```

Lưu ý về đơn vị:
- `date epoch day = 19782` là **ngày lịch tính từ 1970-01-01**, không phải timestamp 19.782 giây.
- `time nano-of-day` là số nanoseconds trong ngày theo clock time, nên cần `long`.
- `instant seconds` là **epoch seconds** từ mốc UTC 1970-01-01T00:00:00Z.
- `LocalDateTime` thiếu `INSTANT_SECONDS` dù đã có ngày và giờ: cần zone/offset để chọn thời điểm thực.

## 6. `get(field)` hay `getLong(field)`? Không phải chỉ xét giá trị hôm nay

Hai cách đọc từ `TemporalAccessor`:

```java
int day = date.get(ChronoField.DAY_OF_MONTH);
long epochDay = date.getLong(ChronoField.EPOCH_DAY);
```

Cả hai đều đọc một `TemporalField` nhưng **không hoán đổi**:
- `get(field)` trả `int`. Một số field có **miền giá trị có thể vượt int**, vì vậy phương thức từ chối field ấy với exception, dù **giá trị hiện tại** tình cờ đang nhỏ.
- `getLong(field)` trả `long`, thích hợp với field như `EPOCH_DAY`, `NANO_OF_DAY`, `INSTANT_SECONDS`.
- Với field không được hỗ trợ, **cả hai đều không hợp lệ**. `getLong` không tự bổ sung thông tin zone/offset.

Ví dụ `date.get(ChronoField.EPOCH_DAY)` có thể ném `UnsupportedTemporalTypeException` mặc dù `date.getLong(EPOCH_DAY)` hiện chỉ trả 19782 (nằm trong miền int); nguyên nhân là **miền tổng thể của field**, không phải riêng giá trị này.

Tương tự, `time.get(ChronoField.NANO_OF_DAY)` không phải cách đọc đúng; dùng `getLong` hoặc `time.toNanoOfDay()`.

Một số API có getter chuyên biệt dễ hiểu hơn:
- `LocalDate.toEpochDay()` trả `long`.
- `LocalTime.toNanoOfDay()` trả `long`.
- `Instant.getEpochSecond()` trả `long`.
- `Instant.getNano()` trả nano bên trong giây.

Không viết ép kiểu `(int) date.getLong(EPOCH_DAY)` mà không biết miền dữ liệu có thể vượt int trong tương lai.

## 7. `range(field)` và `ValueRange`: tính hợp lệ phụ thuộc ngữ cảnh

`TemporalField.range()` cung cấp **miền tổng quát** của field. `temporal.range(field)` cung cấp miền **được tinh chỉnh theo temporal cụ thể**, nếu type hỗ trợ.

```java
ValueRange generic =
        ChronoField.DAY_OF_MONTH.range();

ValueRange feb2024 =
        LocalDate.of(2024, 2, 29)
                 .range(ChronoField.DAY_OF_MONTH);
```

Hai đối tượng có nội dung khác nhau:
- `generic` trả `1 - 28/31`: tồn tại tháng có 28, 29, 30 hoặc 31 ngày.
- `feb2024` trả `1 - 29`: tháng 2/2024 có 29 ngày.
- `generic.isValidValue(31)` là `true`, vì một số tháng có ngày 31.
- `feb2024.isValidValue(31)` là `false`, vì **tháng 2/2024 không có ngày 31**.

`ValueRange` có các phương thức `isValidValue(long)`, `isValidIntValue(long)`, `checkValidValue(long, field)`, `checkValidIntValue(long, field)`. Kết quả phụ thuộc **range bạn lấy**.

Nếu bạn chưa có một `LocalDate` mà chỉ có năm/tháng từ form, dùng:

```java
YearMonth ym = YearMonth.of(2024, 2);
boolean valid29 = ym.isValidDay(29); // true
boolean valid30 = ym.isValidDay(30); // false
```

Đoạn minh họa trong phương thức có import `java.time.YearMonth`. **Không dùng range tổng quát để xác nhận 31/2 là ngày có thật**. Nếu year/month tự không hợp lệ (ví dụ tháng 13), `YearMonth.of(...)` ném `DateTimeException`.

### `isSupported` khác `isValidValue`

`isSupported(field)` trả lời **kiểu temporal có field đó không**. `range(field).isValidValue(value)` kiểm tra **giá trị có nằm trong một miền cho field ấy không**. Hai phương thức không thay nhau được: một `LocalDate` hỗ trợ `DAY_OF_MONTH` nhưng không chấp nhận giá trị 30 nếu bản thân ngày thuộc tháng 2/2024.

## 8. Chương trình Java: range tinh chỉnh và các ngoại lệ

Tạo `RangeAndErrorDemo.java`:

```java
import java.time.*;
import java.time.temporal.*;

public class RangeAndErrorDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);

        ValueRange generic =
                ChronoField.DAY_OF_MONTH.range();
        ValueRange refined =
                date.range(ChronoField.DAY_OF_MONTH);

        System.out.println("general month-day range = " +
                generic);
        System.out.println("refined month-day range = " +
                refined);
        System.out.println("general accepts 31 = " +
                generic.isValidValue(31));
        System.out.println("refined accepts 31 = " +
                refined.isValidValue(31));

        System.out.println("Feb 2024 valid day 29 = " +
                YearMonth.of(2024, 2).isValidDay(29));
        System.out.println("Feb 2023 valid day 29 = " +
                YearMonth.of(2023, 2).isValidDay(29));

        System.out.println("day-of-month adjusted = " +
                date.with(ChronoField.DAY_OF_MONTH, 28));
        System.out.println("month changed = " +
                date.with(ChronoField.MONTH_OF_YEAR, 4));

        try {
            date.with(ChronoField.DAY_OF_MONTH, 30);
        } catch (DateTimeException ex) {
            System.out.println("invalid day = " +
                    ex.getClass().getSimpleName());
        }

        try {
            date.get(ChronoField.EPOCH_DAY);
        } catch (DateTimeException ex) {
            System.out.println("get epoch day = " +
                    ex.getClass().getSimpleName());
        }

        try {
            LocalTime.NOON.get(ChronoField.NANO_OF_DAY);
        } catch (DateTimeException ex) {
            System.out.println("get nano of day = " +
                    ex.getClass().getSimpleName());
        }

        System.out.println("range valid int = " +
                refined.isValidIntValue(29));
    }
}
```

```bash
javac -encoding UTF-8 RangeAndErrorDemo.java
java RangeAndErrorDemo
```

```text
general month-day range = 1 - 28/31
refined month-day range = 1 - 29
general accepts 31 = true
refined accepts 31 = false
Feb 2024 valid day 29 = true
Feb 2023 valid day 29 = false
day-of-month adjusted = 2024-02-28
month changed = 2024-04-29
invalid day = DateTimeException
get epoch day = UnsupportedTemporalTypeException
get nano of day = UnsupportedTemporalTypeException
range valid int = true
```

**Giải thích thêm về `with(field,value)`:** `date.with(DAY_OF_MONTH, 30)` không hợp lệ cho tháng 2/2024 nên ném exception. Nhưng `date.with(MONTH_OF_YEAR, 4)` đổi sang tháng 4 và trả ngày **29/4** (vẫn tồn tại). Một số phép điều chỉnh tháng/năm khác còn có thể điều chỉnh về ngày cuối tháng nếu day-of-month cũ vượt miền tháng mới. Đừng dùng `with` thay cho xác thực input người dùng.

## 9. `ChronoUnit`: các đơn vị cộng/trừ và đo khoảng

`ChronoUnit` là enum triển khai `TemporalUnit`. Các nhóm thường gặp:

| Nhóm | Unit | Ví dụ |
| --- | --- | --- |
| Thời gian | `NANOS` | Cộng 100 nano |
| Thời gian | `MICROS`, `MILLIS` | Cộng micro/milliseconds |
| Thời gian | `SECONDS`, `MINUTES` | Cộng giây/phút |
| Thời gian | `HOURS`, `HALF_DAYS` | Cộng giờ/nửa ngày |
| Lịch | `DAYS`, `WEEKS` | Ngày/tuần lịch |
| Lịch | `MONTHS`, `YEARS` | Tháng/năm lịch |
| Lịch | `DECADES`, `CENTURIES`, `MILLENNIA` | Khoảng lịch lớn |
| Lịch | `ERAS` | Chuyển era khi type hỗ trợ |
| Không phải một lượng cộng bình thường | `FOREVER` | Unit vô hạn, thường không được type hỗ trợ cho `plus/until` |

Không phải `ChronoUnit` nào cũng dùng được với mọi type.

**`ChronoUnit.DAYS` là một unit ngày; khi áp dụng với `LocalDate`, nó là ngày theo lịch.** Trên `Instant`, `DAYS` có nghĩa 86.400 giây vì Instant là timeline và không mang timezone. Với `ZonedDateTime`, cộng ngày dùng nghĩa lịch và có thể khác đúng 24 giờ elapsed qua DST. Vì vậy, **cùng tên unit có thể mang ý nghĩa calendar/timeline khác nhau tùy type**.

### Phân loại unit

`ChronoUnit.DAYS.isDateBased()` là true; `ChronoUnit.HOURS.isTimeBased()` là true. `isDurationEstimated()` cho biết độ dài unit là ước tính (điển hình những đơn vị date-based như tháng/năm/ngày trong bối cảnh lịch vùng), không khẳng định mỗi tháng có cùng số nanoseconds.

`ChronoUnit.MONTHS.getDuration()` trả một **khoảng ước lượng** dùng trong API unit, **không** có nghĩa mọi tháng thật đều dài bằng duration ấy. Thời gian thực của “một tháng” phụ thuộc tháng/năm và zone. Không dùng duration ước lượng của MONTHS để tính ngày kết thúc kỳ kế toán.

## 10. Kiểm tra hỗ trợ unit bằng `isSupported(TemporalUnit)`

`Temporal.isSupported(TemporalUnit)` kiểm tra **đơn vị có thể dùng để cộng/trừ với type đó**. Ví dụ:

```java
LocalDate date = LocalDate.of(2024, 2, 28);

date.isSupported(ChronoUnit.DAYS);  // true
date.isSupported(ChronoUnit.HOURS); // false

LocalTime time = LocalTime.of(11, 0);
time.isSupported(ChronoUnit.MINUTES); // true
time.isSupported(ChronoUnit.DAYS);    // false
```

Đoạn minh họa đã import `java.time.*` và `java.time.temporal.ChronoUnit`.

Bảng minh họa:

| Temporal | `DAYS` | `HOURS` | `MONTHS` |
| --- | --- | --- | --- |
| `LocalDate` | true | **false** | true |
| `LocalTime` | **false** | true | **false** |
| `LocalDateTime` | true | true | true |
| `Instant` | true (mỗi ngày = 24 giờ trên timeline) | true | **false** |
| `ZonedDateTime` | true | true | true |

`LocalDate.plus(1, ChronoUnit.HOURS)` ném `UnsupportedTemporalTypeException`. Đây là lỗi **unit không thuộc khả năng type**, không phải “trường giờ có giá trị 0”. `LocalTime.plus(2, HOURS)` có thể wrap giờ đồng hồ sang ngày khác theo giờ trong ngày nhưng không lưu số ngày đã trôi qua.

**Đừng nhầm**:
- `date.isSupported(ChronoField.DAY_OF_MONTH)` là **kiểm tra field**.
- `date.isSupported(ChronoUnit.DAYS)` là **kiểm tra unit**.

Cùng tên method, nhưng **tham số là interface khác nhau**. Biến typed `TemporalAccessor` chỉ có overload cho `TemporalField`; để gọi overload cho `TemporalUnit`, cần đối tượng `Temporal`.

## 11. Đếm unit bằng `between` và thay đổi bằng `plus`

Các cách viết có nghĩa tương đương cho unit được type hỗ trợ:

```java
LocalDate start = LocalDate.of(2024, 2, 28);
LocalDate end = start.plus(2, ChronoUnit.DAYS);

long count1 = ChronoUnit.DAYS.between(start, end);
long count2 = start.until(end, ChronoUnit.DAYS);
// count1 == count2 == 2
```

Đây là đoạn trong một phương thức với import `java.time.*` và `java.time.temporal.ChronoUnit`.

Các operation tổng quát:
- `temporal.plus(amount, unit)`: cộng một số unit, trả temporal mới theo type.
- `temporal.minus(amount, unit)`: trừ một số unit.
- `unit.addTo(temporal, amount)`: API chiều ngược (thường ưu tiên cách gọi trên temporal cho dễ đọc).
- `unit.between(start, end)`: trả số unit hoàn chỉnh giữa hai temporal hợp lệ, theo hướng start → end.
- `temporal.until(end, unit)`: biểu đạt tương ứng với `between`.

**`between` không làm tròn lên** khi thiếu một phần unit. Ví dụ từ `2024-03-01T10:00` tới `2024-03-02T09:59` chưa đủ 24 giờ nên `ChronoUnit.DAYS.between(LocalDateTime, LocalDateTime)` trả **0**, dù lịch đã sang ngày hôm sau. Nếu chỉ cần khoảng cách giữa **hai LocalDate**, hãy so `toLocalDate()` để có số ngày lịch; đừng dùng kết quả "0" mà kết luận hai timestamp có cùng ngày.

`ChronoUnit.HOURS.between(LocalDate, LocalDate)` không hợp lệ: LocalDate không có thông tin giờ. Kiểm tra `date.isSupported(ChronoUnit.HOURS)` trước khi tính nếu type có thể thay đổi.

### Unit là đơn vị hoàn chỉnh, không phải Duration/Period trả về

`ChronoUnit.DAYS.between(...)` trả `long` — số lượng đơn vị. Nó không trả `Duration` hay `Period`. `Duration.between(...)` và `Period.between(...)` là API khác với mục tiêu, phạm vi type và cách biểu diễn khác nhau. Đừng cho rằng số unit `DAYS` là một timestamp hoặc một lượng giây cố định trong mọi zone.

## 12. Chương trình Java: hỗ trợ unit, between, plus và lỗi

Tạo `UnitSupportDemo.java`:

```java
import java.time.*;
import java.time.temporal.*;

public class UnitSupportDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 28);
        LocalTime time = LocalTime.of(11, 0);
        LocalDateTime dateTime =
                LocalDateTime.of(2024, 2, 28, 11, 0);
        Instant instant =
                Instant.parse("2024-02-28T11:00:00Z");

        System.out.println("date supports days = " +
                date.isSupported(ChronoUnit.DAYS));
        System.out.println("date supports hours = " +
                date.isSupported(ChronoUnit.HOURS));
        System.out.println("time supports minutes = " +
                time.isSupported(ChronoUnit.MINUTES));
        System.out.println("time supports days = " +
                time.isSupported(ChronoUnit.DAYS));
        System.out.println("date-time supports hours = " +
                dateTime.isSupported(ChronoUnit.HOURS));
        System.out.println("instant supports days = " +
                instant.isSupported(ChronoUnit.DAYS));
        System.out.println("instant supports months = " +
                instant.isSupported(ChronoUnit.MONTHS));
        System.out.println("date supports forever = " +
                date.isSupported(ChronoUnit.FOREVER));

        System.out.println("DAYS date-based = " +
                ChronoUnit.DAYS.isDateBased());
        System.out.println("HOURS time-based = " +
                ChronoUnit.HOURS.isTimeBased());

        System.out.println("plus 2 days = " +
                date.plus(2, ChronoUnit.DAYS));
        System.out.println("plus 2 hours = " +
                time.plus(2, ChronoUnit.HOURS));
        System.out.println("days between = " +
                ChronoUnit.DAYS.between(
                        date, date.plusDays(2)));

        System.out.println("partial days between = " +
                ChronoUnit.DAYS.between(
                        LocalDateTime.of(2024, 3, 1, 10, 0),
                        LocalDateTime.of(2024, 3, 2, 9, 59)));

        try {
            date.plus(1, ChronoUnit.HOURS);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("unsupported date hours = " +
                    ex.getClass().getSimpleName());
        }

        try {
            ChronoUnit.HOURS.between(
                    date, date.plusDays(1));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("unsupported between hours = " +
                    ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 UnitSupportDemo.java
java UnitSupportDemo
```

```text
date supports days = true
date supports hours = false
time supports minutes = true
time supports days = false
date-time supports hours = true
instant supports days = true
instant supports months = false
date supports forever = false
DAYS date-based = true
HOURS time-based = true
plus 2 days = 2024-03-01
plus 2 hours = 13:00
days between = 2
partial days between = 0
unsupported date hours = UnsupportedTemporalTypeException
unsupported between hours = UnsupportedTemporalTypeException
```

Đây là kết quả đã chạy trên JDK. `2024-02-28` cộng 2 ngày thành `2024-03-01` vì năm 2024 có 29/2. `partial days between = 0` cho biết **chưa hoàn thành đủ một ngày** khi hai LocalDateTime cách nhau 23 giờ 59 phút, chứ không bác bỏ việc chúng thuộc hai ngày lịch khác nhau.

## 13. `TemporalField` và `TemporalUnit` cùng dùng cơ chế double dispatch

Hai interface không chỉ là enum. Khi bạn gọi:

```java
temporal.isSupported(field);
temporal.getLong(field);
temporal.with(field, newValue);
```

Nếu field là `ChronoField`, các lớp java.time thường xử lý trực tiếp. Nếu field là implementation khác (ví dụ `WeekFields.ISO.weekOfWeekBasedYear()`), API có thể ủy quyền đến `TemporalField` để hỏi `isSupportedBy`, `getFrom`, `rangeRefinedBy` hoặc `adjustInto` theo hợp đồng.

Tương tự với unit:

```java
temporal.isSupported(unit);
temporal.plus(amount, unit);
temporal.until(end, unit);
```

Nếu unit là `ChronoUnit`, type có thể xử lý trực tiếp; nếu là unit khác, các phương thức của `TemporalUnit` như `isSupportedBy`, `addTo`, `between` có thể được gọi. Đây là **cơ chế mở rộng** hợp lệ của `java.time.temporal`.

Các ví dụ trên là **mã khái niệm có biến `temporal`, `field`, `unit`, `newValue`, `amount` và `end` đã tồn tại**, không phải class độc lập. Khi dùng code generic, kiểm tra hỗ trợ là bước cần thiết, đặc biệt nếu trường/đơn vị đến từ thư viện bên ngoài.

### Một số method trên interface

`TemporalField`:
- `getBaseUnit()`: đơn vị cơ sở của field, ví dụ `DAY_OF_MONTH` thường dùng `DAYS`.
- `getRangeUnit()`: đơn vị bao lấy field, ví dụ `DAY_OF_MONTH` có phạm vi `MONTHS`.
- `isDateBased()` / `isTimeBased()`: phân loại field.
- `range()` / `rangeRefinedBy(temporal)`: miền chung và miền cụ thể.
- `isSupportedBy(temporal)` / `getFrom(temporal)`: kiểm tra/truy vấn.
- `adjustInto(temporal, value)`: tạo temporal được điều chỉnh.

`TemporalUnit`:
- `getDuration()`: duration đại diện hoặc ước lượng của unit.
- `isDurationEstimated()`, `isDateBased()`, `isTimeBased()`: mô tả đặc điểm.
- `isSupportedBy(temporal)`: khả năng áp dụng unit.
- `addTo(temporal, amount)` / `between(a,b)`: cộng và đếm.

**Nên gọi qua giá trị temporal** (ví dụ `date.isSupported(field)`, `date.getLong(field)`, `date.plus(2, unit)`) thay vì trực tiếp gọi ngược trên field/unit, trừ khi bạn đang triển khai abstraction.

## 14. Viết hàm đọc field an toàn với `TemporalAccessor`

Hàm generic nhận `TemporalAccessor` có thể mô tả giá trị mà không áp đặt rằng mỗi type có đủ ngày giờ:

```java
static String simpleSummary(TemporalAccessor value) {
    StringBuilder s = new StringBuilder();

    if (value.isSupported(ChronoField.YEAR)) {
        s.append("year=")
         .append(value.get(ChronoField.YEAR));
    }
    if (value.isSupported(ChronoField.HOUR_OF_DAY)) {
        s.append(" hour=")
         .append(value.get(ChronoField.HOUR_OF_DAY));
    }
    if (value.isSupported(ChronoField.INSTANT_SECONDS)) {
        s.append(" instantSeconds=")
         .append(value.getLong(ChronoField.INSTANT_SECONDS));
    }

    return s.toString().trim();
}
```

Đây là **method minh họa đặt trong class có import `java.time.temporal.*`**. Nó có thể được gọi với `LocalDate`, `LocalTime`, `LocalDateTime` hoặc `Instant`. Không dùng `get(ChronoField.INSTANT_SECONDS)` vì field này cần `long`.

**`isSupported(field)` là bước kiểm tra khả năng, không phải “bắt mọi lỗi”.** Các implementation custom của field có thể lỗi tính toán, overflow hoặc gặp trạng thái không hợp lệ dù hỗ trợ field. Đừng catch mọi exception rồi âm thầm dùng 0. Nếu việc thiếu field là hợp lệ, biểu diễn nó bằng kết quả tùy chọn (ví dụ `OptionalLong`) hoặc quyết định fallback theo domain.

Không nên tự gán `0` cho field không tồn tại, vì `HOUR_OF_DAY = 0` nghĩa là **giờ 00:00 thật** đối với temporal có giờ, khác hoàn toàn “không chứa thông tin giờ”.

## 15. `TemporalQuery` và `TemporalQueries.precision()`

`TemporalAccessor.query(TemporalQuery<R>)` hỗ trợ các truy vấn chung về date-time. `TemporalQueries` cung cấp truy vấn có sẵn như `precision()`, `zone()`, `offset()`, `localDate()`, `localTime()` và chronology khi type hỗ trợ.

`TemporalQueries.precision()` trả **đơn vị chính xác nhỏ nhất mà type biểu diễn theo hợp đồng**, ví dụ:
- `LocalDate` → `DAYS`.
- `LocalTime` → `NANOS`.
- `LocalDateTime` → `NANOS`.
- `Instant` → `NANOS`.
- `YearMonth` → `MONTHS`.

Điều này **không có nghĩa Clock đang chạy đo đúng từng nanosecond**. Precision ở đây là đặc tính biểu diễn của type; resolution/accuracy vật lý của đồng hồ hệ thống là câu chuyện khác.

Nếu truy vấn không có câu trả lời thích hợp, `query(...)` có thể trả `null` tùy query/type. Không coi mọi query là bắt buộc trả giá trị khác null. Khi chỉ muốn biết một field cụ thể được hỗ trợ, `isSupported(field)` rõ ràng hơn việc thử suy ra qua precision.

## 16. Chương trình Java: đọc các TemporalAccessor khác nhau

Tạo `GenericTemporalDemo.java`:

```java
import java.time.*;
import java.time.temporal.*;

public class GenericTemporalDemo {
    static String describe(TemporalAccessor value) {
        StringBuilder s = new StringBuilder(
                value.getClass().getSimpleName());

        s.append(" precision=")
                .append(value.query(
                        TemporalQueries.precision()));

        if (value.isSupported(ChronoField.YEAR)) {
            s.append(" year=")
                    .append(value.get(ChronoField.YEAR));
        }

        if (value.isSupported(ChronoField.HOUR_OF_DAY)) {
            s.append(" hour=")
                    .append(value.get(ChronoField.HOUR_OF_DAY));
        }

        if (value.isSupported(ChronoField.INSTANT_SECONDS)) {
            s.append(" epochSecond=")
                    .append(value.getLong(
                            ChronoField.INSTANT_SECONDS));
        }
        return s.toString();
    }

    public static void main(String[] args) {
        System.out.println(
                describe(LocalDate.of(2024, 2, 29)));
        System.out.println(
                describe(LocalTime.of(15, 30)));
        System.out.println(
                describe(LocalDateTime.of(2024, 2, 29, 15, 30)));
        System.out.println(
                describe(Instant.parse("2024-02-29T00:00:00Z")));

        System.out.println("Month precision = " +
                YearMonth.of(2024, 2)
                        .query(TemporalQueries.precision()));
    }
}
```

```bash
javac -encoding UTF-8 GenericTemporalDemo.java
java GenericTemporalDemo
```

```text
LocalDate precision=Days year=2024
LocalTime precision=Nanos hour=15
LocalDateTime precision=Nanos year=2024 hour=15
Instant precision=Nanos epochSecond=1709164800
Month precision = Months
```

Kết quả cho thấy utility không hỏi `YEAR` của `Instant` hay `HOUR_OF_DAY` của `LocalDate`. Các trường khác nhau được đọc **có điều kiện**. `precision=Days` không biến `LocalDate` thành `Duration`, cũng không có nghĩa ngày lịch bằng đúng 86.400 giây trong mọi zone.

## 17. Các field và unit mở rộng: `IsoFields` và `WeekFields`

Không phải mọi field là `ChronoField`. Ví dụ:
- `IsoFields.QUARTER_OF_YEAR`: quý ISO trong năm, từ 1 đến 4.
- `IsoFields.DAY_OF_QUARTER`: ngày trong quý.
- `IsoFields.WEEK_BASED_YEAR`: **năm theo tuần ISO**, khác calendar year.
- `IsoFields.WEEK_OF_WEEK_BASED_YEAR`: số tuần của week-based-year.
- `WeekFields.ISO.weekBasedYear()` và `weekOfWeekBasedYear()`: trường tuần theo quy tắc ISO.
- `IsoFields.QUARTER_YEARS`: một `TemporalUnit` cho các quý năm.

Đây là các API còn dùng được trong Java 8+ và minh họa cơ chế mở rộng field/unit. `LocalDate` có thể hỗ trợ những field/unit này thông qua tính toán dựa trên các `ChronoField` cơ sở.

**Cẩn thận `YEAR` khác `WEEK_BASED_YEAR`.** Ngày `2019-12-30` thuộc calendar year **2019** nhưng ISO week-based-year **2020**, tuần 1. Nếu formatter dùng `YYYY` (week-based-year) thay vì `uuuu` (proleptic calendar year), kết quả tại cuối tháng 12 có thể trông “sang năm mới” quá sớm.

`WeekFields.ISO` xác định tuần bắt đầu thứ Hai, tuần 1 cần ít nhất bốn ngày trong năm. Với các quốc gia hoặc quy định khác, tuần bắt đầu ngày nào và quy tắc tuần 1 có thể khác; không mặc định mọi hệ thống báo cáo dùng tuần ISO.

## 18. Chương trình Java: field tuần/quý và unit QUARTER_YEARS

Tạo `IsoWeekDemo.java`:

```java
import java.time.*;
import java.time.temporal.*;

public class IsoWeekDemo {
    public static void main(String[] args) {
        LocalDate edge = LocalDate.of(2019, 12, 30);

        TemporalField isoWeekYear =
                WeekFields.ISO.weekBasedYear();
        TemporalField isoWeek =
                WeekFields.ISO.weekOfWeekBasedYear();

        System.out.println("calendar year = " +
                edge.get(ChronoField.YEAR));
        System.out.println("ISO week-based year = " +
                edge.get(isoWeekYear));
        System.out.println("ISO week = " +
                edge.get(isoWeek));
        System.out.println("IsoFields week year = " +
                edge.get(IsoFields.WEEK_BASED_YEAR));

        System.out.println("date supports ISO week year = " +
                edge.isSupported(isoWeekYear));
        System.out.println("time supports ISO week year = " +
                LocalTime.NOON.isSupported(isoWeekYear));

        System.out.println("quarter = " +
                edge.get(IsoFields.QUARTER_OF_YEAR));

        System.out.println("quarter years add = " +
                edge.plus(1, IsoFields.QUARTER_YEARS));
        System.out.println("date supports quarter years = " +
                edge.isSupported(IsoFields.QUARTER_YEARS));
    }
}
```

```bash
javac -encoding UTF-8 IsoWeekDemo.java
java IsoWeekDemo
```

```text
calendar year = 2019
ISO week-based year = 2020
ISO week = 1
IsoFields week year = 2020
date supports ISO week year = true
time supports ISO week year = false
quarter = 4
quarter years add = 2020-03-30
date supports quarter years = true
```

`LocalTime.NOON` không biết ngày nào trong tuần/năm nên không hỗ trợ field week-based-year. `LocalDate` đủ thông tin lịch để tính được. Cộng `1 QUARTER_YEARS` từ `2019-12-30` tương ứng ba tháng lịch cho kết quả `2020-03-30`, không phải một lượng giây cố định.

Đừng dùng field tuần của ISO trong dữ liệu report có **quy tắc tuần riêng** mà không xác nhận hợp đồng; chọn `WeekFields` phù hợp.

## 19. Tình huống Unit có cùng tên nhưng semantics khác nhau theo Temporal

Đây là phần quan trọng khi xây API tổng quát:

`ChronoUnit.DAYS` trong hai biểu thức:

```java
Instant instant = Instant.parse(
        "2024-03-09T17:00:00Z");

Instant nextInstant =
        instant.plus(1, ChronoUnit.DAYS);
```

và:

```java
ZonedDateTime ny = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime nextLocalDay =
        ny.plus(1, ChronoUnit.DAYS);
```

**không có cùng ngữ nghĩa elapsed tại DST transition**:
- Với `Instant`, cộng `DAYS` tương ứng 86.400 giây trên timeline.
- Với `ZonedDateTime`, cộng `DAYS` làm phép cộng theo lịch địa phương rồi giải quyết offset; qua ngày New York đổi DST, từ trưa 09/03/2024 tới trưa 10/03/2024 chỉ trôi qua **23 giờ**.
- `ZonedDateTime.plus(24, ChronoUnit.HOURS)` cộng 24 giờ timeline và có thể ra **13:00** địa phương.

Vì vậy `isSupported(unit) == true` chỉ nói **có thể áp dụng unit**, không bảo đảm mọi type hiểu operation đó như một số giây cố định. Chọn kiểu temporal và unit phải dựa trên domain. Với timeout dùng elapsed timer/`Duration`; với chu kỳ ngày theo vùng dùng lịch/zone.

Không tự đổi `Period.ofDays(1)` thành `Duration.ofDays(1)` trong ứng dụng đặt lịch ở vùng có DST. Một period ngày lịch và một duration 24 giờ có mục tiêu khác nhau.

## 20. `Clock`: nguồn hiện tại không phải TemporalField hoặc TemporalUnit

`java.time.Clock` là abstraction cung cấp **thời điểm hiện tại cùng ZoneId**. Nó **không** phải một `TemporalField` hay `TemporalUnit` và không được hỏi `clock.isSupported(ChronoUnit.HOURS)`. Bạn phải lấy giá trị ngày giờ từ Clock rồi hỏi kiểu đó:

```java
Clock clock = Clock.fixed(
        Instant.parse("2024-06-15T18:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate today = LocalDate.now(clock);
boolean canAddDays =
        today.isSupported(ChronoUnit.DAYS); // true

Instant eventTime = Instant.now(clock);
long epochSeconds =
        eventTime.getLong(ChronoField.INSTANT_SECONDS);
```

Đoạn minh họa trong phương thức với import `java.time.*` và `java.time.temporal.*`. `Clock.fixed` hữu ích cho test tái lập; còn production có thể sử dụng `Clock.systemUTC()` hoặc `Clock.system(zone)` tùy nhu cầu. **Clock không biến LocalDate thành kiểu có giờ**, và việc lấy LocalDate từ Clock áp dụng zone của Clock.

Tại `2024-06-15T18:30Z`, giờ Việt Nam là `01:30` ngày **16/6/2024**. Chỉ lấy `LocalDate` theo UTC và giả định là ngày Việt Nam sẽ sai ở mốc này.

## 21. Chương trình Java: Clock, TemporalField và TemporalUnit

Tạo `ClockTemporalDemo.java`:

```java
import java.time.*;
import java.time.temporal.*;

public class ClockTemporalDemo {
    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2024-06-15T18:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        LocalDate localDate = LocalDate.now(fixed);
        LocalDateTime localDateTime =
                LocalDateTime.now(fixed);
        Instant now = Instant.now(fixed);

        System.out.println("fixed instant = " + now);
        System.out.println("local date = " + localDate);
        System.out.println("local date-time = " +
                localDateTime);
        System.out.println("clock zone = " +
                fixed.getZone());

        System.out.println("localDate month field = " +
                localDate.get(ChronoField.MONTH_OF_YEAR));
        System.out.println("localDate supports HOURS = " +
                localDate.isSupported(ChronoUnit.HOURS));
    }
}
```

```bash
javac -encoding UTF-8 ClockTemporalDemo.java
java ClockTemporalDemo
```

```text
fixed instant = 2024-06-15T18:30:00Z
local date = 2024-06-16
local date-time = 2024-06-16T01:30
clock zone = Asia/Ho_Chi_Minh
localDate month field = 6
localDate supports HOURS = false
```

Cùng một Clock có Instant xác định, `LocalDate.now(clock)` nhận ngày theo zone được gắn trên Clock. Sau đó khả năng đọc/cộng là của **LocalDate** chứ không phải của Clock.

Đừng dùng `Clock.fixed` như giải pháp cho `System.nanoTime()` hay để mô phỏng độ trễ CPU; nó là abstraction thời điểm hiện tại, phù hợp với kiểm thử các trường ngày giờ theo zone. Một ticker elapsed giả lập là khái niệm khác.

## 22. Exception và kiểm tra hỗ trợ: khi nào bắt lỗi, khi nào từ chối trước?

Các ngoại lệ thường gặp:
- **`UnsupportedTemporalTypeException`**: field/unit không được type hỗ trợ, ví dụ `date.get(HOUR_OF_DAY)`, `date.plus(1,HOURS)`.
- **`DateTimeException`**: họ ngoại lệ ngày giờ, ví dụ đặt ngày trong tháng không tồn tại qua `date.with(DAY_OF_MONTH, 30)` ở tháng 2.
- **`ArithmeticException`**: có thể xuất hiện nếu một phép toán temporal vượt miền số/hỗ trợ theo hợp đồng, ví dụ tính toán lớn.
- **`NullPointerException`**: có thể xảy ra khi truyền một field/unit hoặc temporal null vào API yêu cầu non-null.

Không nên code generic theo kiểu:

```java
try {
    return temporal.get(ChronoField.HOUR_OF_DAY);
} catch (Exception ignored) {
    return 0;
}
```

Đây là **phản ví dụ bên trong phương thức** có `temporal` đã xác định. Kết quả `0` vừa có thể mang nghĩa **00:00** vừa có thể che việc **không hề có giờ**, gây bug nghiệp vụ. Nếu thiếu field là điều dự kiến, kiểm tra `isSupported` và có kiểu biểu diễn trạng thái rõ ràng.

Ví dụ helper minh họa:

```java
static java.util.OptionalInt hourIfPresent(
        TemporalAccessor temporal) {
    if (!temporal.isSupported(
            ChronoField.HOUR_OF_DAY)) {
        return java.util.OptionalInt.empty();
    }
    return java.util.OptionalInt.of(
            temporal.get(ChronoField.HOUR_OF_DAY));
}
```

Đoạn trên nằm trong class đã import `java.time.temporal.*`. `OptionalInt.empty()` khác một giờ có giá trị 0. Nếu hệ thống **bắt buộc có giờ**, một lỗi validation rõ ràng có thể tốt hơn Optional; điều đó phụ thuộc hợp đồng của caller.

### Không over-check các getter đã biết type

`LocalDate date` luôn có trường năm/tháng/ngày hợp lệ theo type; không cần mỗi lần gọi `date.getYear()` lại `isSupported(YEAR)`. Với utility generic nhận `TemporalAccessor`, mức kiểm tra khác vì kiểu đầu vào có thể là LocalDate, LocalTime hoặc Instant.

### isSupported có đủ để không bao giờ ném exception không?

Không. Nó xác định khả năng type hỗ trợ field/unit; giá trị mới vẫn có thể sai miền, phép toán có thể overflow, dữ liệu custom `TemporalField` có thể có giới hạn riêng, hoặc parameter có thể không phù hợp. **isSupported ≠ validate mọi giá trị ≠ try/catch mọi lỗi**.

## 23. Sơ đồ quyết định API

| Bạn muốn làm gì? | API đúng | Điều cần kiểm tra |
| --- | --- | --- |
| Đọc ngày trong tháng từ `LocalDate` | `getDayOfMonth()` | Type rõ, không cần lookup dynamic |
| Đọc field được caller chọn | `isSupported(field)` rồi `get`/`getLong` | Field thuộc type không? Miền vượt int không? |
| Kiểm tra ngày 29/2 trong năm cụ thể | `YearMonth.isValidDay` hoặc `LocalDate.of` | Năm nhuận, tháng có hợp lệ |
| Xem field có thể nằm trong miền gì | `temporal.range(field)` | Range theo ngữ cảnh, không chỉ generic |
| Cộng 2 ngày cho LocalDate | `plusDays(2)` hoặc `plus(2,DAYS)` | Unit là ngày lịch |
| Cộng 2 giờ cho LocalTime | `plusHours(2)` hoặc `plus(2,HOURS)` | Type không lưu ngày |
| Đếm ngày giữa hai LocalDate | `ChronoUnit.DAYS.between` | Hướng start/end, đơn vị |
| Đếm giờ giữa hai Instants | `ChronoUnit.HOURS.between` / `Duration.between` | Timeline UTC |
| Đếm ngày hoàn chỉnh giữa hai LocalDateTime | `ChronoUnit.DAYS.between` | Có thể trả 0 nếu chưa tròn ngày |
| Lấy năm theo tuần ISO | `WeekFields.ISO.weekBasedYear()` | Khác calendar YEAR |
| Thêm một quý lịch | `IsoFields.QUARTER_YEARS` khi hỗ trợ | Quy tắc tháng/ngày cuối |
| Lấy ngày hiện tại theo Việt Nam | `LocalDate.now(Clock)` | Clock có ZoneId phù hợp |
| Chuyển LocalDateTime sang Instant | Chọn `ZoneId`/`ZoneOffset` trước | DST gap/overlap policy |

Nếu không cần generic, method chuyên biệt thường tốt hơn:
- `date.plusDays(2)` ngắn và dễ hiểu hơn `date.plus(2,ChronoUnit.DAYS)`.
- `instant.getEpochSecond()` rõ hơn `instant.getLong(ChronoField.INSTANT_SECONDS)`.
- `date.lengthOfMonth()` hoặc `YearMonth.isValidDay(day)` rõ hơn tự suy ra ngày hợp lệ qua generic range.

Generic temporal API hữu ích khi yêu cầu thay đổi field/unit **tại runtime** hoặc khi viết thư viện đa kiểu.

## 24. Kiểm thử tối thiểu và các bẫy thiết kế

**Trường hợp nên test cho field:**
1. `LocalDate` có YEAR nhưng không có HOUR_OF_DAY.
2. `LocalTime` có HOUR_OF_DAY nhưng không có DAY_OF_MONTH.
3. `LocalDateTime` không có INSTANT_SECONDS nếu thiếu zone.
4. `Instant` có INSTANT_SECONDS nhưng không có YEAR.
5. `getLong(EPOCH_DAY)`/`getLong(NANO_OF_DAY)` thành công; `get(...)` cho hai field này ném exception theo contract.
6. `ChronoField.DAY_OF_MONTH.range()` tổng quát khác `date.range(DAY_OF_MONTH)` khi tháng 2.
7. `YearMonth.isValidDay(29)` đúng/sai theo năm nhuận.
8. Các field mở rộng `IsoFields`, `WeekFields` cho ngày gần ranh giới năm.

**Trường hợp nên test cho unit:**
1. LocalDate hỗ trợ DAYS, không hỗ trợ HOURS.
2. LocalTime hỗ trợ MINUTES/HOURS, không hỗ trợ DAYS.
3. Instant hỗ trợ DAYS nhưng không hỗ trợ MONTHS vì không có lịch tháng.
4. `ChronoUnit.FOREVER` không phải một phép cộng hữu hạn vào LocalDate.
5. `between` theo hướng âm/dương và số đơn vị hoàn chỉnh.
6. `plus(1, DAYS)` cho ZonedDateTime qua DST có thể khác `plus(24,HOURS)`.
7. Cộng lượng thời gian rất lớn có thể vượt miền type dù unit được hỗ trợ.

**Các bẫy khi thiết kế:**
- Gọi `isSupported(ChronoField.HOUR_OF_DAY)` rồi lấy `getLong(ChronoField.INSTANT_SECONDS)`: bạn kiểm tra **field khác** với field đọc, không bảo đảm gì.
- Chỉ kiểm tra `ChronoField.DAY_OF_MONTH.range()` rồi cho phép ngày 31/2: range tổng quát **không biết năm/tháng**.
- Tự coi `EPOCH_DAY` là milliseconds: sai unit ngay cả khi cả hai được lưu trong long.
- Dùng `getLong` cho một field không được hỗ trợ rồi catch rộng: không giải quyết vấn đề dữ liệu thiếu field.
- Lấy `Duration.ofDays(1)` thay cho chu kỳ **ngày lịch tại một vùng có DST**: có thể lệch giờ địa phương.
- Dùng `ChronoUnit.MONTHS.getDuration()` để suy mọi tháng có cùng số giây: tháng có độ dài khác nhau.
- Coi `TemporalQueries.precision()==NANOS` là đồng hồ vật lý chính xác từng nanosecond: precision type và resolution clock khác nhau.
- Cho rằng `ChronoField` là toàn bộ danh sách field: `IsoFields`, `WeekFields` và custom implementations còn mở rộng.
- Tự triển khai `TemporalField`/`TemporalUnit` khi built-in đã đáp ứng: tăng rủi ro vi phạm contract; chỉ làm khi thật sự cần domain-specific semantics.

## 25. Bài tập tự kiểm tra

**Câu 1.** `ChronoField.DAY_OF_MONTH` và `ChronoUnit.DAYS` khác gì?  
**Đáp án:** Một cái là field trả **ngày trong tháng**, một cái là unit cho phép cộng/trừ/đếm **số ngày**.

**Câu 2.** `TemporalAccessor` có method `plus(amount,unit)` không?  
**Đáp án:** Không. Interface đó cho truy vấn; `Temporal` mở rộng để hỗ trợ thao tác cộng/trừ và điều chỉnh.

**Câu 3.** `LocalDate.isSupported(ChronoField.HOUR_OF_DAY)` là gì?  
**Đáp án:** false. LocalDate không lưu giờ.

**Câu 4.** `LocalDate.isSupported(ChronoUnit.HOURS)` là gì?  
**Đáp án:** false. Không thể cộng đơn vị giờ vào một LocalDate như thể nó có giờ.

**Câu 5.** `LocalDateTime.isSupported(ChronoField.INSTANT_SECONDS)` có true không?  
**Đáp án:** Không. Thiếu offset/zone để xác định một instant.

**Câu 6.** `Instant.isSupported(ChronoUnit.MONTHS)` có true không?  
**Đáp án:** Không. Instant không có khái niệm tháng lịch khi chưa chọn zone/calendar.

**Câu 7.** Tại sao `date.get(ChronoField.EPOCH_DAY)` có thể ném exception dù epoch day hiện tại nhỏ hơn Integer.MAX_VALUE?  
**Đáp án:** Miền **tổng thể** của field có thể vượt int; sử dụng `getLong(EPOCH_DAY)`.

**Câu 8.** `ChronoField.DAY_OF_MONTH.range().isValidValue(31)` có xác nhận ngày 31 tháng 2 hợp lệ không?  
**Đáp án:** Không. Range tổng quát chưa biết tháng/năm; dùng `YearMonth.isValidDay`.

**Câu 9.** `ChronoUnit.DAYS.between(2024-03-01T10:00, 2024-03-02T09:59)` là bao nhiêu với hai LocalDateTime?  
**Đáp án:** 0, vì chưa đủ một ngày hoàn chỉnh, dù hai giá trị nằm ở hai ngày lịch.

**Câu 10.** `2019-12-30` có `YEAR` và week-based-year bằng bao nhiêu?  
**Đáp án:** Calendar YEAR = 2019; ISO week-based-year = 2020, tuần ISO 1.

**Câu 11.** `IsoFields.QUARTER_YEARS` thuộc interface nào?  
**Đáp án:** `TemporalUnit`; còn `IsoFields.QUARTER_OF_YEAR` là `TemporalField`.

**Câu 12.** `TemporalQueries.precision()` cho `LocalDate` trả gì?  
**Đáp án:** `ChronoUnit.DAYS`, phản ánh độ chi tiết mà type biểu diễn.

**Câu 13.** Một Clock cố định cho `2024-06-15T18:30:00Z` với `Asia/Ho_Chi_Minh` cho `LocalDate.now(clock)` ngày nào?  
**Đáp án:** `2024-06-16`, vì đã sang ngày mới ở Việt Nam.

**Câu 14.** `isSupported(unit) == true` có chứng minh cộng một ngày luôn bằng 24 giờ elapsed?  
**Đáp án:** Không. Cần xét semantics của temporal; ZonedDateTime qua DST có thể khác 24 giờ.

**Câu 15.** Nếu utility cần đọc giờ nhưng TemporalAccessor có thể chỉ là LocalDate, nên làm gì?  
**Đáp án:** Kiểm tra `isSupported(HOUR_OF_DAY)` rồi trả giá trị hoặc trạng thái thiếu field rõ ràng (ví dụ OptionalInt), không mặc định giờ bằng 0.

## 26. Tổng kết

- **`TemporalField` và `TemporalUnit` là hai chiều khác nhau:** field đọc/điều chỉnh **thành phần**, unit cộng/trừ/đo **khoảng**.
- **`TemporalAccessor`** phục vụ đọc field; **`Temporal`** mở rộng để cộng/trừ và tính khoảng với unit.
- Với field chưa biết, **`isSupported(field)` trước `get`/`getLong`**. Với unit chưa biết, **`isSupported(unit)` trước `plus`/`until`**.
- **`getLong` cần thiết** với field như EPOCH_DAY, NANO_OF_DAY, INSTANT_SECONDS; `get` có thể từ chối vì miền tổng thể vượt int.
- **`range(field)` theo ngữ cảnh** khác `field.range()` tổng quát; kiểm tra ngày tồn tại bằng `YearMonth.isValidDay`/factory khi cần.
- **`ChronoUnit` không đồng nghĩa Duration:** DAYS, MONTHS, HOURS có semantics tương ứng type, đặc biệt với vùng có DST.
- **`IsoFields` và `WeekFields`** là phần mở rộng đang còn dùng, giải quyết quý, tuần ISO và năm theo tuần.
- **`Clock`** tạo một temporal tại thời điểm/zone xác định; Clock không phải field hoặc unit. Kiểm thử bằng Clock.fixed khi bài toán cần thời gian “hiện tại”.
- Dùng các API chính thức `java.time` đã tồn tại từ Java 8 và vẫn được duy trì, không cần dùng cách làm lỗi thời.

### Tài liệu Oracle Java SE 26 (đang áp dụng)

- [`TemporalField`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalField.html): hợp đồng field, `isSupportedBy`, `rangeRefinedBy` và `adjustInto`.
- [`TemporalUnit`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalUnit.html): hợp đồng unit, `isSupportedBy`, `addTo`, `between`.
- [`ChronoField`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoField.html): tập trường chuẩn và range.
- [`ChronoUnit`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html): tập đơn vị chuẩn, `isDateBased`/`isTimeBased`/`getDuration`.
- [`TemporalAccessor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAccessor.html) và [`Temporal`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/Temporal.html): đọc/điều chỉnh và hỗ trợ field/unit.
- [`ValueRange`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ValueRange.html): kiểm tra giá trị hợp lệ trong range.
- [`TemporalQueries`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalQueries.html): precision, zone, date/time query.
- [`IsoFields`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/IsoFields.html) và [`WeekFields`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/WeekFields.html): field/unit tuần, quý.
- [`LocalDate`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html), [`LocalTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalTime.html), [`Instant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html), [`ZonedDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html), [`Clock`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html).
