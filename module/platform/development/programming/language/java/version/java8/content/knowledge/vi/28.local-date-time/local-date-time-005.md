# Month, DayOfWeek và enum liên quan trong java.time (Java 8+)

**Chủ đề cha:** Ngày giờ cục bộ. **Mục tiêu:** hiểu `java.time.Month`, `java.time.DayOfWeek` và các enum hỗ trợ như `IsoEra`, `TextStyle`, `FormatStyle`, `ChronoField`, `ChronoUnit`; áp dụng đúng vào `LocalDate`, `MonthDay`, `YearMonth`, `WeekFields`, `TemporalAdjusters`; kiểm tra dữ liệu ngày nhuận, đầu/ cuối tuần, tuần giao năm, locale và lịch nghiệp vụ.

Các enum `Month` và `DayOfWeek` có từ Java 8, **vẫn là API hiện hành**. Các chương trình hoàn chỉnh minh họa bằng Java 17+ với ngày cố định, không dựa vào thời gian hiện tại hoặc múi giờ của máy.

> **Ý chính:** `Month.JANUARY.getValue() == 1`; `DayOfWeek.MONDAY.getValue() == 1`, `DayOfWeek.SUNDAY.getValue() == 7`. Đây là giá trị chuẩn ISO, **không phải** `ordinal()`. Enum cho biết **tháng** hoặc **thứ** chứ chưa phải một ngày cụ thể, không tự xác định ngày lễ hay “thứ Hai kế tiếp”.

## 1. Month và DayOfWeek giải quyết vấn đề gì?

Trong ứng dụng, một con số `2` không tự cho biết nó là tháng 2 hay thứ Ba; một chuỗi `"Friday"` dễ bị gõ sai hoặc phụ thuộc ngôn ngữ. Enum cho kiểu dữ liệu có tập hằng hữu hạn:

```java
Month month = Month.FEBRUARY;
DayOfWeek day = DayOfWeek.FRIDAY;
```

Đây là **đoạn trong phương thức**, cần import `java.time.Month` và `java.time.DayOfWeek`. Hai enum này bất biến và an toàn khi chia sẻ giữa các thread; có thể dùng trong `switch`, `EnumSet`, `EnumMap`, hoặc truyền cho các API thời gian khác.

**Chú ý ba cấp độ dữ liệu:**

- `Month`: tháng trong năm, không có năm hay ngày. Ví dụ `Month.FEBRUARY`.
- `DayOfWeek`: thứ trong tuần, không mang một ngày lịch cụ thể. Ví dụ `DayOfWeek.MONDAY`.
- `LocalDate`: **một ngày đầy đủ** theo lịch ISO, gồm năm–tháng–ngày. Ví dụ `LocalDate.of(2024, 2, 29)`.

`LocalDate`, `LocalTime` và `LocalDateTime` là các class bất biến, **không phải enum**. `LocalDateTime` còn không chứa zone/offset, nên không đủ để tự biểu diễn một instant toàn cầu.

### 1.1. Số tháng và số thứ theo ISO

| Month | Giá trị | Month | Giá trị |
| --- | ---: | --- | ---: |
| `JANUARY` | 1 | `JULY` | 7 |
| `FEBRUARY` | 2 | `AUGUST` | 8 |
| `MARCH` | 3 | `SEPTEMBER` | 9 |
| `APRIL` | 4 | `OCTOBER` | 10 |
| `MAY` | 5 | `NOVEMBER` | 11 |
| `JUNE` | 6 | `DECEMBER` | 12 |

| DayOfWeek | Giá trị ISO |
| --- | ---: |
| `MONDAY` | 1 |
| `TUESDAY` | 2 |
| `WEDNESDAY` | 3 |
| `THURSDAY` | 4 |
| `FRIDAY` | 5 |
| `SATURDAY` | 6 |
| `SUNDAY` | 7 |

Đây là thứ tự ISO-8601: **thứ Hai = 1**, **Chủ nhật = 7**. Quy tắc đó không thay đổi khi bạn đổi locale hiển thị. Một số hệ thống khác, chẳng hạn các hằng của `java.util.Calendar`, đánh số Chủ nhật là 1; **không được chuyển số thẳng** nếu chưa xác nhận quy tắc của nguồn.

## 2. Khởi tạo, chuyển đổi và kiểm tra enum

Các phương thức thông dụng của Month:

```java
Month january = Month.of(1);               // JANUARY
Month february = Month.valueOf("FEBRUARY"); // FEBRUARY
int number = Month.DECEMBER.getValue();    // 12
Month fromDate = Month.from(
        LocalDate.of(2024, 2, 29));         // FEBRUARY
```

Đây là **đoạn trong phương thức**, import `java.time.Month` và `LocalDate`. `Month.of(int)` nhận 1–12, còn `Month.valueOf(String)` nhận **tên hằng chính xác**, phân biệt chữ hoa/chữ thường. `Month.valueOf("february")` không tự đổi thành FEBRUARY; nó ném `IllegalArgumentException`.

DayOfWeek có cách dùng tương tự:

```java
DayOfWeek monday = DayOfWeek.of(1); // MONDAY
DayOfWeek sunday = DayOfWeek.of(7); // SUNDAY
DayOfWeek fromDate = DayOfWeek.from(
        LocalDate.of(2024, 2, 29)); // THURSDAY
```

Đây là đoạn mã trong phương thức. `DayOfWeek.of(0)` hoặc `of(8)` ném `DateTimeException`; `Month.of(0)`, `Month.of(13)` cũng ném `DateTimeException`. `of` **không** cuộn giá trị ngoài khoảng; các phương thức `plus`/`minus` mới diễn đạt phép dịch tuần hoàn.

**Đừng dùng `ordinal()` làm số ISO.** `JANUARY.ordinal() == 0` trong khi `JANUARY.getValue() == 1`; `MONDAY.ordinal() == 0` trong khi `MONDAY.getValue() == 1`. `ordinal()` thuộc cơ chế của Enum và phản ánh chỉ số khai báo từ 0; `getValue()` là hợp đồng số tháng/thứ.

`Month.values()` trả một mảng chứa đủ 12 hằng theo thứ tự khai báo; `DayOfWeek.values()` trả đủ bảy thứ. Hai phương thức hữu ích cho liệt kê, test và cấu hình, nhưng không thể tự kiểm tra một ngày cụ thể có hợp lệ trong năm hay không.

## 3. Cộng/trừ tháng và thứ: Phải phân biệt enum với ngày thật

`Month.plus(long)` và `minus(long)` lặp lại theo chu kỳ 12 tháng; `DayOfWeek.plus(long)` và `minus(long)` lặp theo 7 ngày:

```java
Month m = Month.DECEMBER.plus(2);          // FEBRUARY
Month before = Month.JANUARY.minus(1);     // DECEMBER
DayOfWeek next = DayOfWeek.SUNDAY.plus(1); // MONDAY
DayOfWeek prev = DayOfWeek.MONDAY.minus(1); // SUNDAY
```

Đây là đoạn trong phương thức. `Month.DECEMBER.plus(2)` **không cho biết năm mới là năm nào**; `DayOfWeek.SUNDAY.plus(1)` **không trả về LocalDate của ngày mai**. Enum chỉ chuyển hằng trong một vòng.

Muốn cộng **tháng lên một ngày**, sử dụng `LocalDate.plusMonths`, vì phép tính còn phải xử lý ngày cuối tháng và chuyển năm:

```java
LocalDate result = LocalDate.of(2024, 1, 31)
        .plusMonths(1); // 2024-02-29
```

Đoạn trên đặt trong một phương thức. Ngày 31 tháng 1 cộng một tháng chuyển thành 29 tháng 2 năm nhuận 2024 theo quy tắc điều chỉnh ngày hợp lệ. Trong năm thường 2023, kết quả tương ứng là 28/02/2023. `Month.JANUARY.plus(1)` không thể tự đưa ra kết quả này vì nó không chứa năm và ngày.

## 4. Month: Số ngày, năm nhuận, ngày đầu năm và quý

`Month` cung cấp các phương thức sau:

| Phương thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `length(boolean leapYear)` | Số ngày tháng theo cờ nhuận | `FEBRUARY.length(true) == 29` |
| `minLength()` | Độ dài ngắn nhất của tháng | `FEBRUARY.minLength() == 28` |
| `maxLength()` | Độ dài dài nhất của tháng | `FEBRUARY.maxLength() == 29` |
| `firstDayOfYear(boolean leapYear)` | Số thứ tự ngày đầu tháng tính từ 1/1 | `MARCH.firstDayOfYear(true) == 61` |
| `firstMonthOfQuarter()` | Tháng bắt đầu quý lịch của tháng hiện tại | `MAY.firstMonthOfQuarter() == APRIL` |

**Cờ leapYear phải do bạn cung cấp chính xác.** `Month.FEBRUARY.length(true)` không tự biết năm hiện hành; nó chỉ trả 29 cho cờ true. Có thể dùng `Year.isLeap(year)` hoặc `Year.of(year).isLeap()` để xác định nhuận theo hệ lịch ISO.

Quy tắc năm nhuận Gregorian: chia hết 4, **trừ** chia hết 100 nếu không đồng thời chia hết 400. Ví dụ: **2024 và 2000 nhuận; 2023 và 1900 không nhuận**.

Khi có một **năm cụ thể**, thường nên dùng `YearMonth`:

```java
YearMonth february = YearMonth.of(2024, Month.FEBRUARY);
int days = february.lengthOfMonth();     // 29
LocalDate last = february.atEndOfMonth(); // 2024-02-29
```

`YearMonth` là **class**, không phải enum. Nó giữ cả tháng lẫn năm, phù hợp với hóa đơn tháng, kỳ báo cáo, khóa sổ hoặc tính ngày cuối tháng. Nếu chỉ dùng `Month.FEBRUARY` trong một hóa đơn của năm 2024, bạn đã làm mất thông tin năm.

Quý lịch thường gồm ba tháng: JANUARY–MARCH, APRIL–JUNE, JULY–SEPTEMBER và OCTOBER–DECEMBER. `Month.firstMonthOfQuarter()` trả tháng đầu quý; một `LocalDate` có thể lấy số quý qua `date.get(IsoFields.QUARTER_OF_YEAR)`. `IsoFields` là **class chứa các trường**, không phải enum Quarter. **Năm tài chính** của công ty có thể có quy tắc khác quý lịch, nên không coi hàm này là đủ cho mọi nghiệp vụ kế toán.

## 5. Java 17+ chạy được: Month và DayOfWeek cơ bản

Tạo file **`MonthAndDayOfWeekDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.Year;
import java.time.YearMonth;

public class MonthAndDayOfWeekDemo {
    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);

        System.out.println("Date: " + leap);
        System.out.println("Month: " + leap.getMonth()
                + " / " + leap.getMonthValue());
        System.out.println("Weekday: " + leap.getDayOfWeek()
                + " / " + leap.getDayOfWeek().getValue());

        System.out.println("February leap/common: "
                + Month.FEBRUARY.length(true) + "/"
                + Month.FEBRUARY.length(false));
        System.out.println("February min/max: "
                + Month.FEBRUARY.minLength() + "/"
                + Month.FEBRUARY.maxLength());
        System.out.println("March first day in leap year: "
                + Month.MARCH.firstDayOfYear(Year.isLeap(2024)));
        System.out.println("May quarter start: "
                + Month.MAY.firstMonthOfQuarter());

        System.out.println("December plus 2: "
                + Month.DECEMBER.plus(2));
        System.out.println("Sunday plus 1: "
                + DayOfWeek.SUNDAY.plus(1));
        System.out.println("Monday minus 1: "
                + DayOfWeek.MONDAY.minus(1));

        MonthDay anniversary = MonthDay.of(Month.FEBRUARY, 29);
        System.out.println("Leap Feb 29 valid: "
                + anniversary.isValidYear(2024));
        System.out.println("Common Feb 29 valid: "
                + anniversary.isValidYear(2023));
        System.out.println("YearMonth February days: "
                + YearMonth.of(2024, Month.FEBRUARY)
                        .lengthOfMonth());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MonthAndDayOfWeekDemo.java
java MonthAndDayOfWeekDemo
```

**Stdout:**

```text
Date: 2024-02-29
Month: FEBRUARY / 2
Weekday: THURSDAY / 4
February leap/common: 29/28
February min/max: 28/29
March first day in leap year: 61
May quarter start: APRIL
December plus 2: FEBRUARY
Sunday plus 1: MONDAY
Monday minus 1: SUNDAY
Leap Feb 29 valid: true
Common Feb 29 valid: false
YearMonth February days: 29
```

Giải thích: năm 2024 nhuận, nên ngày `2024-02-29` hợp lệ và rơi vào THURSDAY (giá trị ISO 4). `Month.MARCH.firstDayOfYear(true)` = 61 vì hai tháng đầu năm có 31 + 29 ngày. `DECEMBER.plus(2)` vòng về FEBRUARY nhưng không tự cộng năm. `MonthDay` lưu tháng–ngày không có năm, nên phải dùng `isValidYear` khi áp dụng vào một năm cụ thể.

## 6. Tính ngày cụ thể: TemporalAdjusters khác phép plus của enum

Khi người dùng hỏi “**Thứ Hai tới** là ngày nào?”, `DayOfWeek.MONDAY` chưa đủ; bạn cần một ngày bắt đầu và quy tắc chọn ngày tiếp theo.

Các bộ điều chỉnh được dùng phổ biến:

- `TemporalAdjusters.next(DayOfWeek.MONDAY)`: tìm **thứ Hai sau ngày hiện tại**, không nhận chính ngày đang xét.
- `TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY)`: nhận **chính hôm nay nếu hôm nay là thứ Hai**, ngược lại tìm thứ Hai sau.
- `TemporalAdjusters.previous(...)` và `previousOrSame(...)`: các biến thể theo chiều ngược lại.
- `TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY)`: thứ Hai đầu tiên trong tháng.
- `TemporalAdjusters.lastInMonth(DayOfWeek.FRIDAY)`: thứ Sáu cuối cùng của tháng.
- `TemporalAdjusters.firstDayOfNextMonth()`: ngày 1 của tháng kế tiếp.
- `TemporalAdjusters.lastDayOfMonth()`: ngày cuối tháng hiện tại.

**Khác biệt cực quan trọng:**

```java
LocalDate friday = LocalDate.of(2026, 11, 6);

LocalDate mondayInSameIsoWeek =
        friday.with(DayOfWeek.MONDAY); // 2026-11-02

LocalDate nextMonday =
        friday.with(
                TemporalAdjusters.next(DayOfWeek.MONDAY));
        // 2026-11-09
```

Đây là đoạn trong phương thức. `DayOfWeek` cũng triển khai `TemporalAdjuster`; dùng trực tiếp `with(DayOfWeek.MONDAY)` sẽ đặt ngày vào **thứ Hai trong cùng tuần ISO**, chứ không nhất thiết là “thứ Hai sắp tới”. Dùng `next`/`nextOrSame` khi hợp đồng là tìm lần xuất hiện sau hôm nay.

Trong logic lịch doanh nghiệp, phải phân biệt **lần xuất hiện sắp tới có cho phép hôm nay hay không**. Sự khác nhau giữa `next` và `nextOrSame` có thể làm chênh một tuần nếu ngày nguồn trùng thứ cần tìm.

## 7. Ngày làm việc không được mã hóa sẵn trong DayOfWeek

`DayOfWeek` không có phương thức chuẩn `isWeekend()`. Ngày nghỉ tùy quốc gia, tổ chức, lịch ca, ngày lễ và sự kiện ngoại lệ. Một doanh nghiệp có thể xem `SATURDAY` và `SUNDAY` là hai ngày nghỉ, nhưng **không nên suy rộng đó là luật toàn cầu**.

Với lịch làm việc **thứ Hai đến thứ Sáu**, có thể dùng `EnumSet`:

```java
EnumSet<DayOfWeek> workdays =
        EnumSet.range(DayOfWeek.MONDAY, DayOfWeek.FRIDAY);
boolean working = workdays.contains(date.getDayOfWeek());
```

Đây là đoạn trong phương thức, import `java.util.EnumSet`, `java.time.DayOfWeek`; biến `date` là một `LocalDate`. Tập `EnumSet` được xây **từ chính sách**; nếu lịch tổ chức khác, dùng `EnumSet.of(...)` theo ngày được cấu hình.

**Cần phân biệt:** `EnumSet<DayOfWeek>` biểu diễn lịch *lặp lại mỗi tuần*, **không tự chứa dữ liệu ngày lễ theo từng năm**. Muốn tìm một ngày làm việc có xét nghỉ lễ, cần thêm nguồn holiday calendar, lịch doanh nghiệp và một cách xử lý ngoại lệ ngày/giờ rõ ràng.

## 8. Ví dụ Java 17+: Lịch làm việc và thứ Hai tiếp theo

Tạo file **`WeekScheduleDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.WeekFields;
import java.util.EnumSet;

public class WeekScheduleDemo {
    static LocalDate nextWorkingDay(
            LocalDate date, EnumSet<DayOfWeek> workingDays
    ) {
        if (workingDays.isEmpty()) {
            throw new IllegalArgumentException("empty working days");
        }

        LocalDate candidate = date.plusDays(1);
        for (int i = 0; i < 7; i++) {
            if (workingDays.contains(candidate.getDayOfWeek())) {
                return candidate;
            }
            candidate = candidate.plusDays(1);
        }
        throw new IllegalStateException("no working day found");
    }

    public static void main(String[] args) {
        LocalDate friday = LocalDate.of(2026, 11, 6);
        EnumSet<DayOfWeek> workdays =
                EnumSet.range(DayOfWeek.MONDAY, DayOfWeek.FRIDAY);

        System.out.println("Today: " + friday + " "
                + friday.getDayOfWeek());
        System.out.println("Next working day: "
                + nextWorkingDay(friday, workdays));
        System.out.println("Next Monday: " + friday.with(
                TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("Next or same Friday: " + friday.with(
                TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY)));
        System.out.println("With Monday: "
                + friday.with(DayOfWeek.MONDAY));
        System.out.println("End month: " + friday.with(
                TemporalAdjusters.lastDayOfMonth()));

        System.out.println("Weekdays: " + workdays);
        System.out.println("Sunday ISO: "
                + DayOfWeek.SUNDAY.getValue());
        System.out.println("Sunday Sunday-start: "
                + LocalDate.of(2026, 11, 8).get(
                        WeekFields.SUNDAY_START.dayOfWeek()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 WeekScheduleDemo.java
java WeekScheduleDemo
```

**Stdout xác định:**

```text
Today: 2026-11-06 FRIDAY
Next working day: 2026-11-09
Next Monday: 2026-11-09
Next or same Friday: 2026-11-06
With Monday: 2026-11-02
End month: 2026-11-30
Weekdays: [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY]
Sunday ISO: 7
Sunday Sunday-start: 1
```

Đây là **lịch mẫu** với thứ Hai–thứ Sáu được coi là ngày làm việc. Hàm `nextWorkingDay` kiểm tra từ ngày *sau* tham số `date`, nên không trả lại ngày hiện tại; vòng lặp tối đa bảy ngày đủ để tìm ít nhất một ngày thuộc tập không rỗng trong một chu kỳ tuần. Nếu cần xét nghỉ lễ, phải bổ sung lịch ngoại lệ trước khi dùng logic trong sản phẩm thật.

Kết quả `With Monday: 2026-11-02` cho thấy `with(DayOfWeek.MONDAY)` **không giống** `next(MONDAY)`. Hai kết quả Chủ nhật bằng 7 và 1 cùng đúng vì một giá trị là **ISO getValue**, một giá trị là **WeekFields Sunday-start**.

## 9. WeekFields: ISO week khác tuần của locale

Số `DayOfWeek.getValue()` luôn tuân theo ISO với Monday 1 – Sunday 7. Nhưng **tuần bắt đầu ngày nào**, **tuần 1 phải có ít nhất bao nhiêu ngày trong năm**, và **số tuần** có thể phụ thuộc chính sách:

- `WeekFields.ISO`: tuần bắt đầu MONDAY và tuần đầu năm phải có **ít nhất bốn ngày** trong năm đó.
- `WeekFields.SUNDAY_START`: tuần bắt đầu SUNDAY, tuần đầu năm có **ít nhất một ngày** trong năm.
- `WeekFields.of(Locale locale)`: lấy quy tắc tương ứng dữ liệu locale được Java sử dụng.
- `WeekFields.of(DayOfWeek firstDay, int minimalDays)`: khai báo chính xác hai tham số của quy tắc tuần.

**Không đánh đồng số thứ ISO với số thứ theo WeekFields.** Ví dụ Chủ nhật 08/11/2026:

```java
LocalDate sunday = LocalDate.of(2026, 11, 8);
int iso = sunday.getDayOfWeek().getValue(); // 7
int local = sunday.get(
        WeekFields.SUNDAY_START.dayOfWeek()); // 1
```

Đây là đoạn trong phương thức. Việc chọn quy tắc Sunday-start chỉ thay đổi **trường số thứ được suy ra**, không thay đổi enum `DayOfWeek.SUNDAY` hoặc kết quả `getValue()`.

### 9.1. Tuần giao năm rất dễ sai

Ngày `2021-01-01` thuộc **năm dương lịch 2021** nhưng theo ISO là **tuần 53 của week-based-year 2020**:

```java
LocalDate boundary = LocalDate.of(2021, 1, 1);
int calendarYear = boundary.getYear(); // 2021
int isoWeekYear = boundary.get(
        IsoFields.WEEK_BASED_YEAR); // 2020
int isoWeek = boundary.get(
        IsoFields.WEEK_OF_WEEK_BASED_YEAR); // 53
```

Đây là đoạn trong phương thức với import `java.time.temporal.IsoFields`. Nếu làm báo cáo theo tuần, **không** ghép `getYear()` với `WEEK_OF_WEEK_BASED_YEAR` rồi coi đó là khóa tuần ISO. Hãy lấy **cả năm tuần và số tuần** theo cùng bộ quy tắc.

Với ứng dụng đa quốc gia hoặc theo lịch doanh nghiệp riêng, không dựa vào locale mặc định của server để tự quyết định năm–tuần; truyền locale hoặc `WeekFields` cố định theo hợp đồng. Điều này quan trọng khi dữ liệu cần tái lập giống nhau trên nhiều máy.

## 10. MonthDay và YearMonth: Chúng không phải enum

`MonthDay` giữ **tháng + ngày**, không có năm; `YearMonth` giữ **năm + tháng**, không có ngày. Hai class bất biến này bổ sung cho enum Month:

| Kiểu | Lưu dữ liệu | Tình huống phù hợp |
| --- | --- | --- |
| `Month` | Chỉ tháng | Phân nhóm dữ liệu theo 12 tháng lặp lại |
| `MonthDay` | Tháng + ngày | Sinh nhật/kỷ niệm lặp qua các năm |
| `YearMonth` | Năm + tháng | Hóa đơn theo tháng, kỳ báo cáo tháng |
| `LocalDate` | Năm + tháng + ngày | Một ngày thật trên lịch ISO |

### 10.1. Ngày 29/02 và điều chỉnh tự động

`MonthDay.of(Month.FEBRUARY, 29)` hợp lệ vì có năm nhuận, nhưng nó **không có năm**. Khi áp vào năm cụ thể:

```java
MonthDay leapDay = MonthDay.of(Month.FEBRUARY, 29);
boolean in2024 = leapDay.isValidYear(2024); // true
boolean in2023 = leapDay.isValidYear(2023); // false
LocalDate adjusted = leapDay.atYear(2023); // 2023-02-28
```

Đây là đoạn trong phương thức. **Cần lưu ý:** `MonthDay.atYear(2023)` điều chỉnh 29/02 thành 28/02 theo hợp đồng API, chứ không nhất thiết ném lỗi. Nếu nghiệp vụ quy định ngày kỷ niệm chỉ tồn tại trong năm nhuận, phải kiểm tra `isValidYear` và xử lý riêng; không âm thầm coi 28/02 là ngày thay thế.

`LocalDate.of(2023, 2, 29)` thì **khác**: đây là yêu cầu tạo một ngày không hợp lệ, nên ném `DateTimeException`. `LocalDate.of(2024, 3, 31).with(Month.FEBRUARY)` cũng là phép **điều chỉnh một ngày có sẵn**, kết quả là 29/02/2024. Đừng trộn quy tắc tạo ngày với quy tắc dịch/điều chỉnh ngày.

## 11. Các enum liên quan thật sự trong Java

| Enum | Hằng ví dụ | Dùng vào việc gì? |
| --- | --- | --- |
| `IsoEra` | `BCE`, `CE` | Niên đại của ISO calendar |
| `TextStyle` | `FULL`, `SHORT`, `NARROW` và các dạng `STANDALONE` | Phong cách tên tháng/thứ địa phương hóa |
| `FormatStyle` | `FULL`, `LONG`, `MEDIUM`, `SHORT` | Phong cách định dạng ngày–giờ theo locale |
| `ChronoField` | `MONTH_OF_YEAR`, `DAY_OF_WEEK`, `YEAR_OF_ERA` | Các trường dữ liệu thời gian |
| `ChronoUnit` | `DAYS`, `WEEKS`, `MONTHS` | Các đơn vị cộng/trừ thời gian |

**Không phải enum:** `WeekFields`, `IsoFields`, `TemporalAdjusters`, `MonthDay`, `YearMonth`, `LocalDate`, `DateTimeFormatter`. Ví dụ `IsoFields.QUARTER_OF_YEAR` là một `TemporalField` từ class `IsoFields`; Java không có enum chuẩn `Quarter` trong `java.time`.

### 11.1. IsoEra: BCE và CE

`IsoEra.BCE.getValue() == 0`; `IsoEra.CE.getValue() == 1`. `LocalDate` hỗ trợ **proleptic year** với **năm 0**: ngày `LocalDate.of(0,1,1)` là năm 1 BCE. Vì vậy:

```java
LocalDate historic = LocalDate.of(0, 1, 1);

IsoEra era = historic.getEra(); // BCE
int yearOfEra = historic.get(
        ChronoField.YEAR_OF_ERA); // 1
int prolepticYear = historic.getYear(); // 0
```

Đây là đoạn trong phương thức với import `IsoEra` và `ChronoField`. Khi hệ thống xử lý ngày lịch sử, cần phân biệt **YEAR** và **YEAR_OF_ERA**; nhưng với lịch làm việc hiện đại thông thường, Month và DayOfWeek là đủ, không cần gắn niên đại tùy tiện.

### 11.2. TextStyle và tên hiển thị

`Month.FEBRUARY.name()` trả hằng Java `"FEBRUARY"`, không phải tên hiển thị theo ngôn ngữ người dùng. Để hiển thị:

```java
String monthName = Month.FEBRUARY.getDisplayName(
        TextStyle.SHORT, Locale.ENGLISH);
String dayName = DayOfWeek.THURSDAY.getDisplayName(
        TextStyle.FULL, Locale.ENGLISH);
```

Đây là đoạn trong phương thức, cần import `java.time.format.TextStyle` và `java.util.Locale`. Những tên hiển thị thường là `"Feb"` và `"Thursday"` với dữ liệu English, nhưng **dữ liệu locale** có thể khác theo runtime/provider; không nên coi chúng là ID ổn định.

`TextStyle` có các kích thước FULL/SHORT/NARROW và dạng STANDALONE. Một số ngôn ngữ dùng dạng tên tháng khác khi đứng riêng so với trong ngày đầy đủ. `NARROW` có thể không phân biệt được các tháng trùng chữ cái đầu. Không dùng tên rút gọn để làm khóa lưu trữ.

`Month.valueOf("FEBRUARY")` nhận **identifier enum** chính xác; `valueOf("February")` và các tên tháng địa phương hóa không được parse tự động. Nếu nhập ngày người dùng, dùng `DateTimeFormatter` có locale và pattern phù hợp hoặc parse ISO cho dữ liệu máy.

### 11.3. FormatStyle, ChronoField và ChronoUnit

`FormatStyle.FULL` là lựa chọn mức độ chi tiết khi tạo formatter:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                .withLocale(Locale.ENGLISH);
String display = LocalDate.of(2024, 2, 29).format(formatter);
```

Đây là đoạn trong phương thức, import `DateTimeFormatter` và `FormatStyle`. Chuỗi hiển thị phụ thuộc locale/provider. Khi truyền dữ liệu giữa hệ thống, ưu tiên định dạng được đặc tả như `DateTimeFormatter.ISO_LOCAL_DATE`.

`ChronoField` diễn đạt một trường:

```java
int monthNumber = Month.MARCH.get(
        ChronoField.MONTH_OF_YEAR); // 3
int weekdayNumber = DayOfWeek.SUNDAY.get(
        ChronoField.DAY_OF_WEEK); // 7
```

`ChronoUnit` diễn đạt **đơn vị** của phép cộng trên ngày:

```java
LocalDate nextWeek = LocalDate.of(2026, 11, 6)
        .plus(1, ChronoUnit.WEEKS); // 2026-11-13
```

Đây là các đoạn trong phương thức. Không dùng `Month.get(ChronoField.DAY_OF_WEEK)` vì chỉ có Month enum thì không thể suy ra ngày trong tuần. Chọn đúng cấp độ dữ liệu trước khi truy vấn TemporalField.

## 12. Java 17+: MonthDay, IsoEra và tuần giao năm

Tạo file **`MonthCalendarFieldsDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.YearMonth;
import java.time.chrono.IsoEra;
import java.time.temporal.ChronoField;
import java.time.temporal.IsoFields;
import java.time.temporal.WeekFields;

public class MonthCalendarFieldsDemo {
    public static void main(String[] args) {
        MonthDay leapDay = MonthDay.of(Month.FEBRUARY, 29);

        System.out.println("Leap day 2024: "
                + leapDay.isValidYear(2024));
        System.out.println("Leap day 2023: "
                + leapDay.isValidYear(2023));
        System.out.println("Adjusted non-leap: "
                + leapDay.atYear(2023));

        YearMonth february = YearMonth.of(2024, Month.FEBRUARY);
        System.out.println("YearMonth: " + february);
        System.out.println("YearMonth end: "
                + february.atEndOfMonth());

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        System.out.println("Calendar year: " + boundary.getYear());
        System.out.println("ISO week year/week: "
                + boundary.get(IsoFields.WEEK_BASED_YEAR) + "/"
                + boundary.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR));

        LocalDate yearZero = LocalDate.of(0, 1, 1);
        System.out.println("Year zero era: " + yearZero.getEra());
        System.out.println("Year zero year-of-era: "
                + yearZero.get(ChronoField.YEAR_OF_ERA));
        System.out.println("BCE code: " + IsoEra.BCE.getValue());
        System.out.println("ISO first day: "
                + WeekFields.ISO.getFirstDayOfWeek());
        System.out.println("Sunday first day: "
                + WeekFields.SUNDAY_START.getFirstDayOfWeek());
    }
}
```

Chạy:

```bash
javac --release 17 MonthCalendarFieldsDemo.java
java MonthCalendarFieldsDemo
```

**Stdout:**

```text
Leap day 2024: true
Leap day 2023: false
Adjusted non-leap: 2023-02-28
YearMonth: 2024-02
YearMonth end: 2024-02-29
Calendar year: 2021
ISO week year/week: 2020/53
Year zero era: BCE
Year zero year-of-era: 1
BCE code: 0
ISO first day: MONDAY
Sunday first day: SUNDAY
```

Ví dụ này khẳng định `MonthDay.atYear(2023)` điều chỉnh ngày 29/02, `IsoFields.WEEK_BASED_YEAR` có thể khác năm dương lịch, `IsoEra.BCE` dùng giá trị 0, còn `WeekFields.ISO` và `SUNDAY_START` đưa ra quy tắc ngày đầu tuần khác nhau.

## 13. EnumSet, EnumMap và switch với Month/DayOfWeek

Vì hai kiểu này là enum, có thể dùng `EnumSet` cho một tập thứ và `EnumMap` cho dữ liệu theo enum:

```java
EnumSet<DayOfWeek> serviceDays =
        EnumSet.of(DayOfWeek.MONDAY,
                   DayOfWeek.WEDNESDAY,
                   DayOfWeek.FRIDAY);

EnumMap<DayOfWeek, String> activities =
        new EnumMap<>(DayOfWeek.class);
activities.put(DayOfWeek.MONDAY, "planning");
activities.put(DayOfWeek.FRIDAY, "review");
```

Đây là các dòng trong phương thức, import `java.util.EnumSet` và `EnumMap`. `EnumMap` lặp key theo thứ tự tự nhiên enum, phù hợp khi khóa chỉ có bảy thứ. Tuy nhiên `EnumMap` và `EnumSet` là các **collection mutable**, không mặc nhiên thread-safe; tính bất biến của enum không tự làm chúng an toàn khi nhiều thread sửa.

Trong Java 17+, `switch expression` có thể xử lý enum trực tiếp:

```java
String label = switch (day) {
    case SATURDAY, SUNDAY -> "configured-weekend";
    default -> "configured-weekday";
};
```

Đây là đoạn trong phương thức, `day` là `DayOfWeek` không null. Tên nhánh cố ý ghi `configured` để nhấn mạnh đây là **chính sách giả định**, không phải phân loại ngày nghỉ quốc tế.

Đối với một mốc tháng cụ thể như kỳ kế toán 11/2026, nên dùng `YearMonth` làm key; `Month.NOVEMBER` chỉ biểu diễn tháng 11 của **mọi năm**, vì thế không thể phân biệt dữ liệu năm 2025 và 2026.

## 14. Parse, locale và ngày “hôm nay”

| Dữ liệu đầu vào | Cách xử lý đúng |
| --- | --- |
| Số tháng ISO 1–12 | Parse/validate số rồi `Month.of(number)` |
| Identifier enum, ví dụ FEBRUARY | `Month.valueOf("FEBRUARY")` nếu giao thức quy định đúng identifier |
| Ngày ISO, ví dụ 2024-02-29 | `LocalDate.parse("2024-02-29")` |
| Ngày theo mẫu/ngôn ngữ người dùng | `DateTimeFormatter` có pattern và locale xác định |
| Số thứ 1–7 từ hệ ngoài | Phải biết quy ước Monday-first hay Sunday-first rồi chuyển rõ |
| Ngày hiện tại ở khu vực cụ thể | `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` hoặc `Clock` của ứng dụng |

Một ví dụ ngày ISO:

```java
LocalDate parsed = LocalDate.parse("2024-02-29");
String machineValue = parsed.format(
        DateTimeFormatter.ISO_LOCAL_DATE); // "2024-02-29"
```

Đây là đoạn trong phương thức, import `LocalDate` và `DateTimeFormatter`. Ngược lại, chuỗi nhập `"29/02/2024"` không được `LocalDate.parse(String)` mặc định hiểu vì không theo định dạng ISO.

Dùng ngày hiện tại có rủi ro phụ thuộc timezone:

```java
LocalDate today = LocalDate.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là đoạn trong phương thức, import `ZoneId`. **Không có stdout xác định** vì ngày phụ thuộc thời điểm chạy. Với unit test, dùng `LocalDate.of(...)` hoặc `Clock.fixed(...)`/`Clock` được truyền vào service, không dùng `LocalDate.now()` trực tiếp rồi hard-code output.

Với ứng dụng đa khu vực, dữ liệu locale có thể quyết định tên tháng/thứ và cách đếm tuần, nhưng **không** thay đổi `Month.getValue` hoặc `DayOfWeek.getValue`. Giữ riêng format hiển thị và định dạng dữ liệu máy.

## 15. Các trường hợp biên và lỗi thường gặp

1. **Dùng `Month.JANUARY.ordinal()` làm tháng 1:** sai vì ordinal là 0; dùng `getValue()`.
2. **Nghĩ `DayOfWeek.SUNDAY.getValue() == 1`:** sai trong ISO, giá trị là 7.
3. **Lấy số từ API ngày cũ và coi là số ISO:** các hệ có thể đánh số ngày đầu tuần khác nhau.
4. **Nghĩ `Month.of(13)` tự quay về JANUARY:** `of` ném `DateTimeException`; chỉ `plus/minus` tuần hoàn.
5. **Dùng `Month.valueOf("february")` cho chuỗi người dùng:** `valueOf` yêu cầu identifier chính xác.
6. **Coi Month là một ngày cụ thể:** Month không có năm/ngày, cần `LocalDate`.
7. **Coi `Month.FEBRUARY.length(true)` là ngày thực tế của mọi năm:** phải xác nhận năm nhuận.
8. **Nghĩ `LocalDate.of(2023,2,29)` tự điều chỉnh:** nó báo ngày không hợp lệ.
9. **Không kiểm tra `MonthDay.atYear`:** 29/02 có thể điều chỉnh về 28/02 khi năm không nhuận.
10. **Dùng `Month.plus` thay cho `LocalDate.plusMonths`:** mất thông tin năm và ngày.
11. **Nhầm `TemporalAdjusters.next` với `nextOrSame`:** next bỏ qua chính ngày nguồn.
12. **Nhầm `date.with(DayOfWeek.MONDAY)` là thứ Hai sắp tới:** nó điều chỉnh về thứ Hai của tuần ISO chứa date.
13. **Cho rằng ngày nghỉ luôn là SATURDAY/SUNDAY:** phải có chính sách tổ chức/địa phương.
14. **Dùng `EnumSet<DayOfWeek>` rồi nghĩ đã loại mọi ngày lễ:** tập thứ trong tuần không đủ cho ngày nghỉ đặc biệt.
15. **Dựa vào locale mặc định của máy để tính số tuần:** kết quả có thể thay đổi theo cấu hình, cần `WeekFields` nhất quán.
16. **Ghép năm dương lịch với số tuần ISO:** tại đầu/cuối năm có thể sai week-based-year.
17. **Nhầm `MonthDay` và `YearMonth` với enum:** chúng là class bất biến chứa những phần dữ liệu khác nhau.
18. **Nghĩ `IsoEra.BCE.getValue() == -1`:** API dùng BCE 0, CE 1.
19. **Coi năm proleptic 0 là không hợp lệ:** `LocalDate` cho phép năm 0 tương ứng năm 1 BCE.
20. **Cho rằng `TextStyle` và `FormatStyle` là cùng loại:** TextStyle là kiểu tên trường, FormatStyle là mức định dạng ngày/giờ.
21. **Lấy tên `NARROW` làm ID duy nhất:** nhiều tháng/thứ có thể trùng nhãn rút gọn.
22. **Nghĩ `WeekFields` là enum:** đó là class cấu hình tuần.
23. **Đọc DAY_OF_WEEK từ Month enum:** Month không có đủ dữ liệu để suy ra thứ.
24. **Cho rằng enum field không thể null:** biến enum là reference và vẫn có thể null; dùng validation nếu không cho phép thiếu.
25. **Nghĩ enum bất biến thì mọi Map/Set chứa enum đều thread-safe:** các collection mutable cần thiết kế đồng bộ riêng.
26. **Dùng `LocalDate.now()` không timezone cho báo cáo xuyên khu vực:** ngày phụ thuộc default zone.
27. **Dùng date formatter địa phương hóa làm định danh/khóa dữ liệu:** chuỗi hiển thị có thể khác giữa locale/providers; giao thức máy nên dùng chuẩn thống nhất.

## 16. Chương trình Java 17+ kiểm thử các giá trị biên

Tạo file **`MonthWeekBoundaryChecks.java`**:

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.MonthDay;
import java.time.YearMonth;
import java.time.temporal.IsoFields;

public class MonthWeekBoundaryChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        for (Month month : Month.values()) {
            check(Month.of(month.getValue()) == month,
                    "month mismatch");
        }
        System.out.println("All months: PASS");

        for (DayOfWeek day : DayOfWeek.values()) {
            check(DayOfWeek.of(day.getValue()) == day,
                    "day mismatch");
        }
        System.out.println("All weekdays: PASS");

        check(Month.DECEMBER.plus(1) == Month.JANUARY,
                "month rollover");
        check(DayOfWeek.SUNDAY.plus(1) == DayOfWeek.MONDAY,
                "weekday rollover");
        System.out.println("Rollover: PASS");

        check(Month.FEBRUARY.length(true) == 29,
                "leap February");
        check(Month.FEBRUARY.length(false) == 28,
                "common February");
        check(MonthDay.of(Month.FEBRUARY, 29)
                .isValidYear(2024), "leap 2024");
        check(!MonthDay.of(Month.FEBRUARY, 29)
                .isValidYear(2023), "common 2023");
        check(YearMonth.of(2024, 2)
                .atEndOfMonth()
                .equals(LocalDate.of(2024, 2, 29)),
                "February end");
        System.out.println("Leap years: PASS");

        LocalDate boundary = LocalDate.of(2021, 1, 1);
        check(boundary.get(IsoFields.WEEK_BASED_YEAR)
                == 2020, "week-based-year");
        check(boundary.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)
                == 53, "week number");
        System.out.println("ISO boundary week: PASS");

        boolean badMonthRejected = false;
        try {
            Month.of(13);
        } catch (DateTimeException ex) {
            badMonthRejected = true;
        }

        boolean badDayRejected = false;
        try {
            DayOfWeek.of(0);
        } catch (DateTimeException ex) {
            badDayRejected = true;
        }

        check(badMonthRejected && badDayRejected,
                "invalid input not rejected");
        System.out.println("Invalid inputs: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 MonthWeekBoundaryChecks.java
java MonthWeekBoundaryChecks
```

**Stdout:**

```text
All months: PASS
All weekdays: PASS
Rollover: PASS
Leap years: PASS
ISO boundary week: PASS
Invalid inputs: PASS
```

Kiểm thử dùng `check` chủ động ném `AssertionError` khi thất bại, nên không cần bật JVM `-ea`. Vòng lặp kiểm tra round-trip số ISO trên đủ 12 tháng và 7 thứ; các dữ liệu biên còn thử 29/02, chu kỳ ngày/tháng, tuần giao năm và giá trị enum ngoài phạm vi.

Bộ test có tính xác định nhưng **không thay thế** các test nghiệp vụ: ngày lễ, lịch ca làm việc, định dạng locale, chuyển đổi từ hệ số Sunday-first, input không hợp lệ, timezone và các quy tắc cập nhật dữ liệu.

## 17. Bảng chọn kiểu dữ liệu nhanh

| Bài toán | Giải pháp thường hợp lý |
| --- | --- |
| Có tháng mà không cần năm | `Month` |
| Có thứ mà không cần ngày cụ thể | `DayOfWeek` |
| Cần ngày đầy đủ | `LocalDate` |
| Cần năm–tháng của hóa đơn | `YearMonth` |
| Cần ngày–tháng kỷ niệm lặp lại | `MonthDay` |
| Muốn số ngày tháng 2 trong năm cụ thể | `YearMonth.lengthOfMonth` |
| Muốn tháng đầu quý lịch | `Month.firstMonthOfQuarter` |
| Muốn số quý từ ngày | `date.get(IsoFields.QUARTER_OF_YEAR)` |
| Muốn thứ Hai tiếp theo | `TemporalAdjusters.next(MONDAY)` |
| Muốn chấp nhận hôm nay nếu trùng thứ | `TemporalAdjusters.nextOrSame(...)` |
| Muốn tuần ISO và năm tuần | `IsoFields.WEEK_OF_WEEK_BASED_YEAR` + `WEEK_BASED_YEAR` |
| Muốn tuần theo chính sách locale | `WeekFields` |
| Muốn tên tháng/thứ hiển thị | `getDisplayName(TextStyle, Locale)` |
| Muốn ngày/giờ theo định dạng locale | `DateTimeFormatter` + `FormatStyle` |
| Muốn niên đại BCE/CE | `IsoEra` |
| Muốn lịch ngày làm việc của tổ chức | `EnumSet<DayOfWeek>` + lịch ngày lễ ngoại lệ |

## 18. Câu hỏi tự kiểm tra

1. `Month.JANUARY.ordinal()` và `Month.JANUARY.getValue()` là bao nhiêu? Nên dùng phương thức nào khi lưu số tháng ISO?
2. `DayOfWeek.SUNDAY.getValue()` trả mấy? Cùng ngày Chủ nhật khi đọc `WeekFields.SUNDAY_START.dayOfWeek()` thì trả mấy?
3. `Month.DECEMBER.plus(2)` trả gì? Có tự cập nhật năm không?
4. Vì sao `Month.FEBRUARY.length(true)` không tự chứng minh số ngày của tháng 2 năm 2023?
5. `LocalDate.of(2024,1,31).plusMonths(1)` trả ngày nào? Vì sao Month enum không đủ?
6. `TemporalAdjusters.next(MONDAY)` khác `nextOrSame(MONDAY)` thế nào?
7. Với thứ Sáu 2026-11-06, `date.with(DayOfWeek.MONDAY)` và `date.with(TemporalAdjusters.next(MONDAY))` trả hai ngày nào?
8. `MonthDay.of(FEBRUARY,29).atYear(2023)` có tự ném ngoại lệ không? Nếu nghiệp vụ cấm điều chỉnh ngày, phải kiểm tra gì?
9. Vì sao thứ Sáu 2021-01-01 được tính vào tuần ISO 53 của week-based-year 2020?
10. `IsoEra.BCE.getValue()` là 0 hay -1? `LocalDate.of(0,1,1)` thuộc era nào?
11. `TextStyle` có nhiệm vụ gì khác `FormatStyle`?
12. Vì sao không nên sử dụng `Month.valueOf("Tháng Hai")` để đọc tên tháng trong ngôn ngữ người dùng?
13. `EnumSet<DayOfWeek>` có tự loại ngày nghỉ lễ khỏi lịch làm việc không?
14. Cần nhập số thứ từ dịch vụ ngoài đánh số Chủ nhật bằng 1; có thể gọi `DayOfWeek.of(1)` trực tiếp để nhận Chủ nhật không?

**Đáp án gợi ý:** (1) 0 và 1, dùng getValue. (2) 7 và 1. (3) FEBRUARY, không có năm. (4) phải xác minh năm nhuận theo năm cụ thể. (5) 2024-02-29 vì điều chỉnh ngày cuối tháng. (6) next bỏ qua hôm nay, nextOrSame có thể giữ hôm nay. (7) 2026-11-02 và 2026-11-09. (8) atYear điều chỉnh về 2023-02-28, kiểm tra isValidYear. (9) tuần ISO đầu năm cần ít nhất bốn ngày thuộc năm mới. (10) 0, BCE. (11) TextStyle định kiểu tên tháng/thứ, FormatStyle định mức độ chi tiết của formatter. (12) valueOf chỉ đọc tên hằng enum. (13) không, cần holiday calendar. (14) không, theo ISO of(1) là MONDAY; phải đổi quy ước rõ ràng.

**Kết luận:** `Month` và `DayOfWeek` là kiểu enum chuẩn, rõ nghĩa và bất biến. Để tránh lỗi lịch, luôn **dùng `getValue()` thay `ordinal()`**, phân biệt chu kỳ enum với tính ngày thật, kiểm tra năm nhuận, tách tuần ISO khỏi tuần theo locale, hiểu `next` và `nextOrSame`, và đặt quy tắc ngày làm việc ở tầng nghiệp vụ. `MonthDay`, `YearMonth`, `IsoEra`, `TextStyle`, `FormatStyle`, `ChronoField` và `ChronoUnit` là những kiểu liên quan nên chọn khi đúng phạm vi dữ liệu.

## Tài liệu Java chính thức (các API còn được hỗ trợ)

- `Month` — 12 tháng, of, getValue, length, plus, firstDayOfYear: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Month.html
- `DayOfWeek` — 7 thứ, giá trị ISO, plus/minus: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/DayOfWeek.html
- `LocalDate` — ngày ISO, điều chỉnh tháng/thứ: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html
- `MonthDay` — ngày/tháng không có năm, isValidYear/atYear: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/MonthDay.html
- `YearMonth` — năm/tháng và ngày cuối tháng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/YearMonth.html
- `TemporalAdjusters` — next/nextOrSame/lastDayOfMonth: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjusters.html
- `WeekFields` — ISO và Sunday-start, quy tắc locale: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/WeekFields.html
- `IsoFields` — quý, tuần và week-based-year: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/IsoFields.html
- `IsoEra` — BCE/CE: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/IsoEra.html
- `TextStyle` — các kiểu tên ngày/tháng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/TextStyle.html
- `FormatStyle` và `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/FormatStyle.html
- `ChronoField`, `ChronoUnit`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoField.html
