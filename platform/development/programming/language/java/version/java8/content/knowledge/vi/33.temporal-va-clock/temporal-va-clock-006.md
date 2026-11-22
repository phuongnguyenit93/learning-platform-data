# WeekFields, IsoFields và quy tắc tuần trong Java 8

Một ngày có thể thuộc **năm dương lịch 2021** nhưng lại thuộc **năm tính tuần 2020**. Điều này không mâu thuẫn: ngày `2021-01-01` là ngày 1 tháng 1 năm 2021, đồng thời là **thứ Sáu của tuần ISO 53 năm 2020**. Nếu một hệ thống chấm công, tính KPI, thanh toán theo tuần hoặc xuất báo cáo dùng nhầm năm dương lịch cho năm tính tuần, dữ liệu tại ranh giới năm sẽ bị nhóm sai, thiếu hoặc lặp.

Trong Java 8, `java.time.temporal.WeekFields` mô tả **quy tắc xác định tuần**: tuần bắt đầu vào thứ mấy và tuần đầu tiên của năm/tháng phải có ít nhất bao nhiêu ngày. `java.time.temporal.IsoFields` cung cấp các trường và đơn vị thời gian **theo ISO-8601**, gồm số tuần trong năm tính tuần, năm tính tuần và các trường quý. Hai API đều là phần hiện còn sử dụng của `java.time`, phù hợp các ứng dụng Java hiện đại.

Bài này đi từ khái niệm **tuần ISO**, cấu hình tuần theo locale hoặc quy định doanh nghiệp, `TemporalField`/`TemporalUnit`, sự khác nhau giữa `weekOfYear` và `weekOfWeekBasedYear`, tuần 53, format/parse week-date, tới cách dựng khoảng truy vấn theo tuần. Sáu ví dụ Java 8 đầy đủ đã được biên dịch và chạy, với stdout minh họa đúng kết quả.

**Nguyên tắc nền tảng:** trước khi tính “tuần số mấy”, phải biết **tuần theo quy tắc nào**. Tuần ISO, tuần theo `Locale.US` và tuần kế toán nội bộ có thể khác nhau ngay cả với **cùng một LocalDate**.

## 1. Tuần không chỉ là “7 ngày liên tục”

Một tuần gồm bảy ngày, nhưng việc chia một năm thành các tuần cần ít nhất hai lựa chọn:

1. **Ngày bắt đầu tuần:** Thứ Hai, Chủ Nhật hoặc một ngày khác.
2. **Số ngày tối thiểu trong tuần đầu tiên:** một tuần chỉ có 1 ngày thuộc năm mới đã là tuần 1 hay phải có ít nhất 4 ngày, v.v.?

Ví dụ cùng ngày `2021-01-01`:

- Theo **ISO-8601**, tuần bắt đầu **Thứ Hai**, tuần 1 phải có **ít nhất bốn ngày** trong năm mới. Ngày này thuộc **2020-W53**.
- Theo quy ước **US** thường dùng trong Java, tuần bắt đầu **Chủ Nhật**, tuần 1 chỉ cần **một ngày** trong năm mới. Ngày này thuộc **2021-W01**.
- Theo một quy định công ty tự đặt, có thể dùng tuần bắt đầu Thứ Bảy và quy tắc tối thiểu riêng. Khi đó kết quả có thể khác cả hai lựa chọn trên.

Nếu ứng dụng chỉ lưu số `week=1` mà không lưu **năm tính tuần** và **quy tắc tuần**, dữ liệu không đủ để xác định khoảng ngày được nói đến.

### Ba giá trị không thể hoán đổi

| Giá trị | Câu hỏi trả lời |
| --- | --- |
| `LocalDate.getYear()` | Ngày đang nằm trong **năm dương lịch** nào? |
| `date.get(WeekFields.ISO.weekBasedYear())` | Ngày thuộc **năm tính tuần ISO** nào? |
| `date.get(WeekFields.ISO.weekOfWeekBasedYear())` | Ngày thuộc **tuần ISO số mấy** trong năm tính tuần đó? |

Với `2021-01-01`, ba giá trị lần lượt là **2021, 2020 và 53**.

## 2. Quy tắc tuần ISO-8601

ISO-8601 quy định:

- Tuần bắt đầu vào **Thứ Hai**.
- Tuần 1 là tuần có **ít nhất bốn ngày của năm dương lịch** tương ứng.
- Tương đương: tuần 1 là tuần chứa **ngày 4 tháng 1** hoặc **Thứ Năm đầu tiên của năm**.
- Các ngày trong tuần ISO có số từ **1 (Thứ Hai)** đến **7 (Chủ Nhật)**.
- Năm tính tuần thường có **52 tuần**, một số năm có **53 tuần**.
- Một tuần ISO không bị chia đôi tại ranh giới 31/12–01/01: cả bảy ngày của cùng một tuần có cùng **week-based-year** và số tuần.

Ví dụ:

```text
Thứ Hai     2020-12-28   ISO 2020-W53-1
Thứ Ba      2020-12-29   ISO 2020-W53-2
Thứ Tư      2020-12-30   ISO 2020-W53-3
Thứ Năm     2020-12-31   ISO 2020-W53-4
Thứ Sáu     2021-01-01   ISO 2020-W53-5
Thứ Bảy     2021-01-02   ISO 2020-W53-6
Chủ Nhật    2021-01-03   ISO 2020-W53-7

Thứ Hai     2021-01-04   ISO 2021-W01-1
```

Ngày đầu năm dương lịch không nhất thiết là ngày đầu năm tính tuần. Ngược lại, **2020-W53** trải dài qua hai năm dương lịch.

### Hệ quả cho báo cáo

Một hệ thống group dữ liệu theo `(date.getYear(), weekNumber)` sẽ nhóm các ngày 1–3/1/2021 vào **năm sai** nếu `weekNumber` là số tuần ISO. Phải group theo cặp:

```text
(weekBasedYear, weekOfWeekBasedYear)
```

và giữ quy tắc ISO nhất quán trong toàn pipeline.

## 3. IsoFields: các trường tuần và quý theo ISO

`IsoFields` nằm trong gói `java.time.temporal`. Các trường quan trọng:

| Thành viên | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `IsoFields.WEEK_BASED_YEAR` | `TemporalField` | Năm tính tuần ISO |
| `IsoFields.WEEK_OF_WEEK_BASED_YEAR` | `TemporalField` | Tuần ISO số 1–52 hoặc 53 |
| `IsoFields.QUARTER_OF_YEAR` | `TemporalField` | Quý ISO của năm: 1–4 |
| `IsoFields.DAY_OF_QUARTER` | `TemporalField` | Ngày thứ mấy trong quý |

Ngoài ra còn có hai đơn vị thời gian:

| Thành viên | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `IsoFields.WEEK_BASED_YEARS` | `TemporalUnit` | Cộng/trừ theo năm tính tuần ISO |
| `IsoFields.QUARTER_YEARS` | `TemporalUnit` | Cộng/trừ theo quý ISO |

Các trường này có thể được sử dụng cùng phương thức của đối tượng triển khai `TemporalAccessor` hoặc `Temporal` như `LocalDate`:

```java
// Minh họa trong phương thức đã import java.time.* và
// java.time.temporal.*.
LocalDate date = LocalDate.of(2021, 1, 1);

int calendarYear = date.getYear(); // 2021
int weekYear = date.get(IsoFields.WEEK_BASED_YEAR); // 2020
int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR); // 53
```

**Không nhầm `IsoFields.WEEK_BASED_YEAR` với `ChronoField.YEAR`.** Chúng cùng có dạng một con số năm, nhưng khác định nghĩa quanh ranh giới năm.

### Khi nào sử dụng IsoFields?

Khi hợp đồng đã nói **tuần ISO**, chọn `IsoFields` hoặc `WeekFields.ISO`. Khi hợp đồng nói **tuần địa phương/doanh nghiệp**, cần chọn `WeekFields` theo quy tắc tương ứng, không dùng IsoFields rồi điều chỉnh kết quả bằng một phép cộng trừ tùy ý.

## 4. Ví dụ hoàn chỉnh 1 — ISO week-year qua ranh giới năm

Tệp **`IsoWeekBoundaryDemo.java`**:

```java
import java.time.*;
import java.time.temporal.*;

public class IsoWeekBoundaryDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static void show(LocalDate date) {
        int weekYear = date.get(IsoFields.WEEK_BASED_YEAR);
        int week = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);
        int day = date.getDayOfWeek().getValue();
        System.out.printf("%s -> ISO %d-W%02d-%d%n",
                          date, weekYear, week, day);
    }

    public static void main(String[] args) {
        LocalDate dec31 = LocalDate.of(2020, 12, 31);
        LocalDate jan1 = LocalDate.of(2021, 1, 1);
        LocalDate jan4 = LocalDate.of(2021, 1, 4);

        check(dec31.get(IsoFields.WEEK_BASED_YEAR) == 2020,
              "end of year 2020");
        check(jan1.getYear() == 2021, "calendar year");
        check(jan1.get(IsoFields.WEEK_BASED_YEAR) == 2020,
              "week based year differs");
        check(jan1.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR) == 53,
              "week 53");
        check(jan4.get(IsoFields.WEEK_BASED_YEAR) == 2021
            && jan4.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR) == 1,
              "first week 2021");

        show(dec31);
        show(jan1);
        show(jan4);
        System.out.println("PASS");
    }
}
```

Chạy bằng JDK 8 trở lên:

```bash
javac -encoding UTF-8 IsoWeekBoundaryDemo.java
java IsoWeekBoundaryDemo
```

Nếu sử dụng JDK mới và muốn kiểm mã chỉ gọi API Java 8:

```bash
javac --release 8 -encoding UTF-8 IsoWeekBoundaryDemo.java
java IsoWeekBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
2020-12-31 -> ISO 2020-W53-4
2021-01-01 -> ISO 2020-W53-5
2021-01-04 -> ISO 2021-W01-1
PASS
```

Giải thích:

- Thứ Năm 31/12/2020 và Thứ Sáu 01/01/2021 đều thuộc tuần ISO **2020-W53**.
- Thứ Hai 04/01/2021 mở tuần ISO **2021-W01**.
- `getYear()` của 01/01 là 2021, trong khi `get(IsoFields.WEEK_BASED_YEAR)` là 2020.
- Các assertion bắt lỗi nếu nhà phát triển vô tình dùng năm dương lịch thay năm tính tuần.
- `getDayOfWeek().getValue()` dùng thứ ISO: Monday=1, ... Sunday=7; không phải chỉ số thứ trong tuần của mọi locale.

## 5. WeekFields: cấu hình cách một vùng/doanh nghiệp tính tuần

`WeekFields` mô tả quy ước tuần bằng hai tham số:

```java
// Mã minh họa.
WeekFields iso = WeekFields.ISO;
WeekFields sunday = WeekFields.SUNDAY_START;

WeekFields custom =
    WeekFields.of(DayOfWeek.MONDAY, 4);

WeekFields userRules =
    WeekFields.of(Locale.US);
```

- `WeekFields.ISO` tương ứng **Thứ Hai + tối thiểu 4 ngày**.
- `WeekFields.SUNDAY_START` tương ứng **Chủ Nhật + tối thiểu 1 ngày**.
- `WeekFields.of(firstDayOfWeek, minimalDaysInFirstWeek)` tạo quy tắc **tường minh**. Giá trị minimalDays hợp lệ từ 1 đến 7.
- `WeekFields.of(locale)` lấy quy tắc tuần theo dữ liệu locale của runtime. Cách này hữu ích cho **hiển thị theo quy ước người dùng**, nhưng không nên sử dụng vô điều kiện làm quy tắc báo cáo doanh nghiệp.

Đọc hai tham số:

```java
DayOfWeek first = rules.getFirstDayOfWeek();
int minimal = rules.getMinimalDaysInFirstWeek();
```

**Đặc biệt:** `Locale` quy định ngôn ngữ và quy ước vùng, còn `ZoneId` quy định múi giờ. `WeekFields.of(Locale.US)` không biến LocalDate thành ngày theo giờ Mỹ; nó chỉ quyết định **ranh giới và cách đánh số tuần** theo locale data.

### WeekFields.of(locale) hay cấu hình tường minh?

Với **giao diện lịch** dùng quy ước địa phương của người dùng, `WeekFields.of(locale)` thường hợp lý. Với báo cáo tài chính, hạn hợp đồng, ca làm hoặc KPI đòi số liệu **nhất quán bất kể người mở báo cáo**, nên dùng một WeekFields cố định do nghiệp vụ chọn. Nếu cùng dữ liệu được group theo locale riêng của từng người xem, tổng hợp “tuần 1” có thể mang nghĩa khác nhau ở các màn hình.

## 6. Các trường của WeekFields

Một đối tượng `WeekFields` cung cấp các `TemporalField` sau:

| Phương thức | Ý nghĩa |
| --- | --- |
| `dayOfWeek()` | Thứ trong tuần **đánh số theo quy ước đã chọn**, ngày đầu tuần là 1 |
| `weekOfMonth()` | Tuần thứ mấy **trong tháng**, có thể là **0** |
| `weekOfYear()` | Tuần thứ mấy **trong năm dương lịch**, có thể là **0** |
| `weekOfWeekBasedYear()` | Tuần thứ mấy của **năm tính tuần** |
| `weekBasedYear()` | Năm tính tuần theo quy tắc WeekFields đó |

Đừng đánh đồng `weekOfYear()` với `weekOfWeekBasedYear()`. Ví dụ ở ranh giới:

- Theo ISO, `2021-01-01` thuộc **2020-W53**, nhưng `WeekFields.ISO.weekOfYear()` của nó là **0**: tuần chứa ngày đó chưa đủ điều kiện là tuần 1 **trong năm dương lịch 2021**.
- `WeekFields.ISO.weekOfMonth()` của `2021-01-01` cũng có thể là **0**, do tuần đầu của tháng chưa có đủ 4 ngày của tháng.
- `weekOfWeekBasedYear()` của cùng ngày **53**, và `weekBasedYear()` là **2020**.

**Tuần 0 không phải lỗi:** đó là một cách biểu diễn hợp lệ của `weekOfYear`/`weekOfMonth` theo quy tắc minimalDays. Nhưng cặp `(weekBasedYear, weekOfWeekBasedYear)` có ngữ nghĩa khác: các ngày thuộc tuần tính của năm trước vẫn mang tuần số hợp lệ trong **năm tính tuần trước**.

### Số ngày trong tuần theo địa phương

`WeekFields.dayOfWeek()` là số **1 cho ngày đầu tuần**, và tiếp tục tới 7. Với ISO, thứ Hai là 1. Với US Sunday-start, Chủ Nhật là 1, Thứ Hai là 2, và Thứ Sáu là 6. Trong khi đó `DayOfWeek.FRIDAY.getValue()` vẫn luôn là 5 theo ISO.

Khi hiển thị lịch tuần, nhớ phân biệt **số thứ ISO cố định** với **vị trí trong tuần cục bộ**.

## 7. Ví dụ hoàn chỉnh 2 — US, France và tuần 0

Tệp **`LocaleWeekRulesDemo.java`**:

```java
import java.time.*;
import java.time.temporal.*;
import java.util.*;

public class LocaleWeekRulesDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields fr = WeekFields.of(Locale.FRANCE);
        WeekFields explicitIso = WeekFields.of(DayOfWeek.MONDAY, 4);
        LocalDate date = LocalDate.of(2021, 1, 1);

        check(us.getFirstDayOfWeek() == DayOfWeek.SUNDAY
              && us.getMinimalDaysInFirstWeek() == 1,
              "US rules");
        check(fr.getFirstDayOfWeek() == DayOfWeek.MONDAY
              && fr.getMinimalDaysInFirstWeek() == 4,
              "France rules");
        check(explicitIso.equals(WeekFields.ISO), "explicit ISO");
        check(date.get(us.weekBasedYear()) == 2021
              && date.get(us.weekOfWeekBasedYear()) == 1,
              "US week");
        check(date.get(fr.weekBasedYear()) == 2020
              && date.get(fr.weekOfWeekBasedYear()) == 53,
              "FR week");
        check(date.get(fr.weekOfYear()) == 0
              && date.get(fr.weekOfMonth()) == 0,
              "partial week 0");

        System.out.println("usFirst=" + us.getFirstDayOfWeek());
        System.out.println("usMinimal=" + us.getMinimalDaysInFirstWeek());
        System.out.println("usWeekBasedYear=" + date.get(us.weekBasedYear()));
        System.out.println("usWeek=" + date.get(us.weekOfWeekBasedYear()));
        System.out.println("frFirst=" + fr.getFirstDayOfWeek());
        System.out.println("frMinimal=" + fr.getMinimalDaysInFirstWeek());
        System.out.println("frWeekBasedYear=" + date.get(fr.weekBasedYear()));
        System.out.println("frWeek=" + date.get(fr.weekOfWeekBasedYear()));
        System.out.println("frWeekOfYear=" + date.get(fr.weekOfYear()));
        System.out.println("frWeekOfMonth=" + date.get(fr.weekOfMonth()));
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 LocaleWeekRulesDemo.java
java LocaleWeekRulesDemo
```

**Stdout đã kiểm chứng trên JDK của ví dụ:**

```text
usFirst=SUNDAY
usMinimal=1
usWeekBasedYear=2021
usWeek=1
frFirst=MONDAY
frMinimal=4
frWeekBasedYear=2020
frWeek=53
frWeekOfYear=0
frWeekOfMonth=0
PASS
```

Các quy tắc locale trên phù hợp môi trường đã chạy và các quy ước phổ biến. Khi phát triển ứng dụng cần số liệu ổn định giữa nhiều bản JDK hoặc locale provider, **không sử dụng kết quả WeekFields.of(locale) như một quy tắc nghiệp vụ bất biến**; thay vào đó dùng cấu hình rõ, ví dụ `WeekFields.of(DayOfWeek.MONDAY,4)`.

### Một lỗi dễ gặp: nhóm dữ liệu theo weekOfYear()

Nếu yêu cầu là **ISO week-year**, group theo:

```java
int keyYear = date.get(WeekFields.ISO.weekBasedYear());
int keyWeek = date.get(WeekFields.ISO.weekOfWeekBasedYear());
```

Không group theo `date.getYear()` và `date.get(WeekFields.ISO.weekOfYear())`, vì tuần 0 của ngày đầu năm có thể khiến báo cáo tạo một “tuần 0” ngoài mong đợi. Dùng thứ tự tuần được chọn đúng với định nghĩa nhóm dữ liệu.

## 8. IsoFields và WeekFields.ISO có quan hệ như thế nào?

Với ngày ISO bình thường, các trường tuần tương ứng cho cùng kết quả:

```java
// Minh họa.
int isoYearA = date.get(IsoFields.WEEK_BASED_YEAR);
int isoWeekA = date.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR);

int isoYearB = date.get(WeekFields.ISO.weekBasedYear());
int isoWeekB = date.get(WeekFields.ISO.weekOfWeekBasedYear());
```

Đối với `LocalDate`, các cặp A và B mô tả cùng quy tắc ISO. Vậy chọn cái nào?

- Chọn **`IsoFields`** khi domain đã cố định **ISO-8601** và muốn nói rõ “week-based-year ISO” ngay tại chỗ dùng field.
- Chọn **`WeekFields.ISO`** khi một thuật toán chung nhận WeekFields và trong trường hợp này dùng cấu hình ISO.
- Chọn **`WeekFields.of(...)`** khi cần quy tắc không phải ISO.
- Đừng dùng `WeekFields.of(Locale.US)` rồi giả định nó giống `IsoFields`.

**Lưu ý phạm vi:** `IsoFields` có hợp đồng theo lịch ISO và các temporal hỗ trợ trường tương ứng. `LocalDate` là đối tượng minh họa phù hợp nhất. Không giả định một trường ISO hỗ trợ mọi kiểu temporal, ví dụ `LocalTime` không có ngày nên không thể lấy tuần của năm.

## 9. Tuần 53 có tồn tại, nhưng không phải năm nào cũng có

Không nên validate tất cả số tuần bằng điều kiện 1–52. Theo ISO:

- Một số năm có **52 tuần**.
- Một số năm có **53 tuần**.
- Năm ISO 2020 có tuần **2020-W53**.
- Năm ISO 2021 không có tuần 53.

Ví dụ giá trị `2020-W53-5` là **01/01/2021**. Trong khi `2021-W53-5` là một ISO week-date **không hợp lệ** và nên bị từ chối khi parser dùng ISO_WEEK_DATE.

Nếu một API nhận `year=2021, week=53`, đừng tự map sang tuần 1 năm sau hoặc âm thầm điều chỉnh theo một phép cộng tuần không có kiểm tra. Xác thực week number theo **năm tính tuần đã chọn**, không chỉ kiểm 1–53.

### Cách kiểm tuần 53 tồn tại

Có thể lấy tuần của những ngày cuối ISO week-based-year, hoặc dùng parser nghiêm ngặt. Với một hệ thống nhận ISO week-date, `DateTimeFormatter.ISO_WEEK_DATE` là công cụ chuẩn và hiện hành, không cần tự xây parser từ chuỗi con.

## 10. DateTimeFormatter.ISO_WEEK_DATE: format/parse tuần ISO

`DateTimeFormatter.ISO_WEEK_DATE` định dạng một ngày theo cấu trúc:

```text
YYYY-Www-d

Ví dụ ISO week-date:
2020-W53-5
^^^^    ^^ ^
năm tuần / tuần / thứ ISO
```

Trong đó `2020-W53-5` nghĩa là **Thứ Sáu, tuần ISO 53 của năm tính tuần 2020**, tương ứng `2021-01-01` theo lịch.

**Phân biệt format ISO week-date với format yyyy-MM-dd thông thường.** ISO week-date dành cho các hệ thống cần biểu diễn **tuần và thứ trong tuần**, không thay thế bắt buộc cho ngày lịch ở mọi API.

Đối với ngày trong API thông thường, `DateTimeFormatter.ISO_LOCAL_DATE` và LocalDate như `2021-01-01` vẫn là lựa chọn dễ hiểu hơn khi nghiệp vụ không cần week-based-year.

## 11. Ví dụ hoàn chỉnh 3 — round-trip ISO week-date và từ chối tuần 53 sai

Tệp **`IsoWeekDateRoundTripDemo.java`**:

```java
import java.time.*;
import java.time.format.*;

public class IsoWeekDateRoundTripDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        String weekDate = date.format(DateTimeFormatter.ISO_WEEK_DATE);
        LocalDate roundTrip = LocalDate.parse(
            weekDate, DateTimeFormatter.ISO_WEEK_DATE);

        boolean invalidWeekRejected = false;
        try {
            LocalDate.parse("2021-W53-5",
                            DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException expected) {
            invalidWeekRejected = true;
        }

        check("2020-W53-5".equals(weekDate), "ISO week date");
        check(date.equals(roundTrip), "round trip");
        check(invalidWeekRejected, "week 53 invalid in ISO 2021");

        System.out.println("date=" + date);
        System.out.println("isoWeekDate=" + weekDate);
        System.out.println("roundTrip=" + roundTrip);
        System.out.println("invalidWeekRejected=" + invalidWeekRejected);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 IsoWeekDateRoundTripDemo.java
java IsoWeekDateRoundTripDemo
```

**Stdout đã kiểm chứng:**

```text
date=2021-01-01
isoWeekDate=2020-W53-5
roundTrip=2021-01-01
invalidWeekRejected=true
PASS
```

**Bài học:**

1. Calendar date và week-date là hai biểu diễn khác của cùng một ngày.
2. Parser ISO week-date kiểm việc tuần 53 có thực sự tồn tại trong năm ISO được chỉ định hay không.
3. Round-trip về `LocalDate` giúp tách phần hiển thị week-date khỏi dữ liệu ngày chính.
4. Không dùng “năm hiện tại” làm year của week-date nếu người dùng đã chọn một ngày đầu tháng 1 có thể thuộc week-based-year trước đó.

## 12. Bẫy định dạng: YYYY, yyyy và uuuu không giống nhau

Đây là lỗi phổ biến trong Java: dùng `YYYY` thay cho năm dương lịch khi format chuỗi giống ngày.

Trong `DateTimeFormatter.ofPattern`:

| Pattern | Ý nghĩa |
| --- | --- |
| `u`, `uuuu` | Năm proleptic của lịch (calendar year) |
| `y`, `yyyy` | Year-of-era (năm trong era) |
| `Y`, `YYYY` | **Week-based-year** theo các quy tắc tuần của locale |
| `w`, `ww` | Tuần trong week-based-year theo locale |
| `e` | Ngày trong tuần theo quy tắc địa phương |
| `M`, `MM` | Tháng số |
| `d`, `dd` | Ngày trong tháng |

Nếu muốn chuỗi ngày lịch `2021-01-01`, hãy dùng `uuuu-MM-dd` (hoặc formatter ISO). Đừng dùng `YYYY-MM-dd`.

**Vì sao?** Ngày `2021-01-01` theo ISO thuộc week-based-year 2020, nên pattern `YYYY-MM-dd` với locale tuần kiểu France có thể in thành **2020-01-01**, gây ra chuỗi trông như ngày lịch hợp lệ nhưng **sai năm**.

### Week-year trong pattern có thể phụ thuộc Locale

Pattern `YYYY-'W'ww-e` không phải tự động là ISO trong mọi Locale. Với US, ví dụ 01/01/2021 có thể là `2021-W01-6`; với France, là `2020-W53-5`. Nếu hợp đồng trao đổi dữ liệu yêu cầu **ISO bất kể locale người dùng**, hãy dùng `DateTimeFormatter.ISO_WEEK_DATE`.

**Tránh nhầm `Y` và `y` trong code review.** Đây là lỗi rất khó thấy vì phần lớn ngày giữa năm cho cùng con số, chỉ bộc lộ ở ranh giới năm.

## 13. Ví dụ hoàn chỉnh 4 — bẫy uppercase Y và locale

Tệp **`PatternWeekYearTrapDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class PatternWeekYearTrapDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        DateTimeFormatter usWeek =
            DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.US);
        DateTimeFormatter frWeek =
            DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.FRANCE);
        DateTimeFormatter calendar =
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
        String badCalendar =
            date.format(DateTimeFormatter.ofPattern(
                "YYYY-MM-dd", Locale.FRANCE));

        String us = date.format(usWeek);
        String fr = date.format(frWeek);
        String iso = date.format(DateTimeFormatter.ISO_WEEK_DATE);

        check("2021-W01-6".equals(us), "US week fields");
        check("2020-W53-5".equals(fr), "France week fields");
        check("2020-W53-5".equals(iso), "ISO week date");
        check("2021-01-01".equals(date.format(calendar)),
              "calendar year");
        check("2020-01-01".equals(badCalendar),
              "Y is week-based year");

        System.out.println("usLocalizedWeek=" + us);
        System.out.println("frLocalizedWeek=" + fr);
        System.out.println("isoWeekDate=" + iso);
        System.out.println("calendarDate=" + date.format(calendar));
        System.out.println("wrongMixOfYearFields=" + badCalendar);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 PatternWeekYearTrapDemo.java
java PatternWeekYearTrapDemo
```

**Stdout đã kiểm chứng:**

```text
usLocalizedWeek=2021-W01-6
frLocalizedWeek=2020-W53-5
isoWeekDate=2020-W53-5
calendarDate=2021-01-01
wrongMixOfYearFields=2020-01-01
PASS
```

Dòng cuối là **đầu ra cố ý sai về nghĩa ngày lịch**, nhằm chứng minh việc ghép `YYYY` (năm tính tuần) với `MM-dd` (tháng-ngày lịch) có thể tạo kết quả gây hiểu nhầm. Không dùng pattern này cho API date. Đối với dữ liệu máy cần ngày lịch, ưu tiên `DateTimeFormatter.ISO_LOCAL_DATE`; khi cần ISO week-date, ưu tiên `DateTimeFormatter.ISO_WEEK_DATE`.

## 14. WeekFields.weekOfYear và weekOfMonth: hiểu tuần số 0

Hai trường `weekOfYear` và `weekOfMonth` hoạt động trong **năm dương lịch** hoặc **tháng hiện tại**, không hoàn toàn giống cặp week-based-year. Vì quy tắc minimalDays, các ngày đầu tháng/năm chưa đủ điều kiện thành tuần đầu có thể được gán **tuần 0**.

Ví dụ `2021-01-01` theo quy tắc ISO:

```text
Calendar year:           2021
WeekFields.ISO.weekOfYear:   0
WeekFields.ISO.weekOfMonth:  0

Week-based-year:         2020
Week of week-based-year:   53
```

Tại sao các giá trị không mâu thuẫn?

- `weekOfYear=0` nói rằng đoạn tuần chứa ngày 1/1 chưa phải tuần 1 **của năm lịch 2021**.
- `weekOfWeekBasedYear=53` nói rằng tuần đầy đủ đó vẫn thuộc **năm tính tuần ISO 2020**.
- `weekOfMonth=0` nói rằng đoạn tuần bắt đầu của tháng 1 chưa đạt số ngày tối thiểu của **tuần đầu tháng**.

Vì vậy:

- Nếu nghiệp vụ đòi báo cáo **theo năm tính tuần**, dùng `weekBasedYear` + `weekOfWeekBasedYear`.
- Nếu nghiệp vụ đòi đánh số **tuần bên trong từng tháng/năm lịch**, có thể dùng `weekOfMonth`/`weekOfYear`, **nhưng phải cho phép tuần 0** nếu quy tắc tuần tạo ra nó.
- Không lấy trường tuần 0 rồi tự biến thành tuần 1 vì “số tuần phải từ 1” mà không có yêu cầu nghiệp vụ.

## 15. Tuần theo locale và tuần báo cáo: dữ liệu cần bền vững

Một sản phẩm có ba cấp quy tắc:

1. **Quy tắc hiển thị lịch cá nhân:** có thể theo `WeekFields.of(userLocale)`.
2. **Quy tắc vận hành nội bộ:** có thể là WeekFields định nghĩa bởi công ty.
3. **Quy tắc tài chính hoặc chuẩn báo cáo:** có thể bắt buộc ISO bất kể Locale.

Nếu tất cả các lớp đều tự gọi `WeekFields.of(Locale.getDefault())`, số tuần trong dashboard có thể khác giữa máy chủ, worker, batch job và trình duyệt. Hãy đưa quy tắc tuần vào **cấu hình nghiệp vụ** và giữ nhất quán khi nhóm, truy vấn, export hoặc phân trang.

### Trường hợp phải lưu khóa kỳ

Giả sử lưu kết quả tổng hợp theo tuần. Khóa nên có ít nhất:

```text
weekRuleId + weekBasedYear + weekNumber
```

Nếu mọi dữ liệu luôn theo ISO, `weekRuleId` có thể là hằng cố định được tài liệu hóa ở schema. Nếu cho nhiều loại tuần, không nên coi cặp `(2021,1)` của US và ISO là **cùng tuần**.

Cũng cần xác định **ZoneId** nếu dữ liệu gốc là event có timestamp: một event lúc 23:30 UTC có thể rơi vào **ngày địa phương hôm sau** của chi nhánh, và từ đó thuộc tuần địa phương khác. `WeekFields` không tự đổi Instant sang ngày địa phương, nó chỉ áp quy tắc tuần lên ngày mà bạn cung cấp.

## 16. IsoFields.QUARTER_OF_YEAR và DAY_OF_QUARTER

`IsoFields` không chỉ có tuần. Nó còn có các trường quý ISO:

- `QUARTER_OF_YEAR` cho quý từ **1 đến 4**.
- `DAY_OF_QUARTER` cho số thứ tự ngày trong quý.
- `QUARTER_YEARS` cho đơn vị cộng/trừ theo quý.

Với ngày `2026-11-06`:

```text
Quý:             Q4 (tháng 10–12)
Ngày của quý:     37 (31 ngày tháng 10 + 6 ngày tháng 11)
Đầu quý:          2026-10-01
Cộng 1 quý:       2027-02-06
```

Với ngày `2024-02-29`, đó là ngày thứ **60** của quý 1 do năm nhuận.

**Giới hạn:** quý ISO chia năm dương lịch thành các khối ba tháng bắt đầu ở tháng 1, 4, 7, 10. Một doanh nghiệp có **năm tài chính bắt đầu tháng 4** có thể có quy tắc quý riêng. Đừng dùng `IsoFields.QUARTER_OF_YEAR` như quý tài chính nếu quy tắc báo cáo không khớp quý ISO.

### Phép cộng quý và phép cộng tuần-năm khác nhau

`date.plus(1, IsoFields.QUARTER_YEARS)` cộng một quý ISO, tương đương bước ba tháng theo logic ngày. Nó khác với việc cộng “91 ngày”, vì độ dài các quý có thể khác nhau.

`date.plus(1, IsoFields.WEEK_BASED_YEARS)` thay đổi **năm tính tuần**, cố giữ số tuần và ngày trong tuần theo quy tắc. Nếu năm đích không có tuần 53, số tuần có thể được điều chỉnh xuống tuần 52. Không coi phép này là `plusYears(1)` của năm dương lịch.

## 17. Ví dụ hoàn chỉnh 5 — quý, ngày của quý và WEEK_BASED_YEARS

Tệp **`IsoQuarterAndWeekYearDemo.java`**:

```java
import java.time.*;
import java.time.temporal.*;

public class IsoQuarterAndWeekYearDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 6);
        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        LocalDate week53 = LocalDate.of(2020, 12, 31);

        int quarter = date.get(IsoFields.QUARTER_OF_YEAR);
        int dayOfQuarter = date.get(IsoFields.DAY_OF_QUARTER);
        LocalDate quarterStart = date.with(
            IsoFields.DAY_OF_QUARTER, 1);
        LocalDate nextQuarterSameDay = date.plus(
            1, IsoFields.QUARTER_YEARS);
        LocalDate nextWeekBasedYear = week53.plus(
            1, IsoFields.WEEK_BASED_YEARS);

        check(quarter == 4 && dayOfQuarter == 37, "Q4 day 37");
        check(quarterStart.equals(LocalDate.of(2026, 10, 1)),
              "quarter start");
        check(nextQuarterSameDay.equals(LocalDate.of(2027, 2, 6)),
              "next quarter");
        check(leapDay.get(IsoFields.DAY_OF_QUARTER) == 60,
              "leap year quarter day");
        check(nextWeekBasedYear.equals(LocalDate.of(2021, 12, 30)),
              "week 53 clamped in 52-week year");

        System.out.println("quarter=" + quarter);
        System.out.println("dayOfQuarter=" + dayOfQuarter);
        System.out.println("quarterStart=" + quarterStart);
        System.out.println("plusOneQuarter=" + nextQuarterSameDay);
        System.out.println("leapDayOfQuarter=" +
            leapDay.get(IsoFields.DAY_OF_QUARTER));
        System.out.println("plusOneWeekBasedYear=" + nextWeekBasedYear);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 IsoQuarterAndWeekYearDemo.java
java IsoQuarterAndWeekYearDemo
```

**Stdout đã kiểm chứng:**

```text
quarter=4
dayOfQuarter=37
quarterStart=2026-10-01
plusOneQuarter=2027-02-06
leapDayOfQuarter=60
plusOneWeekBasedYear=2021-12-30
PASS
```

**Giải thích chi tiết phép cộng tuần-năm:**

- `2020-12-31` là thứ Năm trong **ISO 2020-W53**.
- Cộng một `WEEK_BASED_YEARS` nhắm tới năm tính tuần **2021**, nhưng ISO 2021 chỉ có 52 tuần.
- Vì vậy kết quả được điều chỉnh về tuần 52, giữ thứ Năm, tức **2021-12-30**.
- Nếu một hợp đồng muốn ngày “31/12 của năm sau” thì `WEEK_BASED_YEARS` không phù hợp; hãy sử dụng phép năm lịch tương ứng.
- Nếu một báo cáo quý dùng lịch tài chính đặc biệt, `IsoFields.QUARTER_YEARS` cũng chưa chắc biểu diễn đúng quy tắc đó.

## 18. Dựng khoảng một tuần theo WeekFields

Nhiều hệ thống cần khoảng ngày của một tuần để lọc hoặc tổng hợp dữ liệu. Một cách rõ ràng là:

1. Chọn `WeekFields` theo hợp đồng (ISO hoặc quy tắc vùng).
2. Với `LocalDate date`, lấy thứ trong tuần theo quy tắc bằng `date.get(rules.dayOfWeek())` (1..7).
3. Lùi `localizedDow-1` ngày để được **ngày đầu tuần**.
4. Lấy `start.plusWeeks(1)` làm **ngày bắt đầu tuần kế tiếp**, dùng như end-exclusive.

Ví dụ:

```java
// Đoạn minh họa, rules là WeekFields.
int localizedDow = date.get(rules.dayOfWeek());
LocalDate start = date.minusDays(localizedDow - 1);
LocalDate endExclusive = start.plusWeeks(1);
```

Dùng khoảng ngày nửa mở **`[start,endExclusive)`** để tránh đếm trùng tại ranh giới hai tuần.

**Đừng mặc định ngày bắt đầu tuần luôn là Thứ Hai**, vì WeekFields có thể cấu hình Sunday-start hoặc quy tắc khác. Đừng chỉ dùng `date.with(DayOfWeek.MONDAY)` cho mọi locale nếu hợp đồng tuần không phải ISO.

### Ví dụ một ngày thuộc hai khoảng khác nhau theo quy tắc

Với `2021-01-01`:

| Quy tắc | Start inclusive | End exclusive |
| --- | --- | --- |
| ISO (Monday-start) | `2020-12-28` | `2021-01-04` |
| US (Sunday-start) | `2020-12-27` | `2021-01-03` |

Hai khoảng đều chứa ngày 1/1, nhưng **ranh giới tuần khác nhau**. Dữ liệu nhóm theo tuần cũng vì thế có thể khác.

## 19. Ví dụ hoàn chỉnh 6 — khoảng tuần ISO và US

Tệp **`IsoWeekRangeDemo.java`**:

```java
import java.time.*;
import java.time.temporal.*;
import java.util.*;

public class IsoWeekRangeDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static LocalDate startOfWeek(LocalDate date, WeekFields rules) {
        int localizedDow = date.get(rules.dayOfWeek());
        return date.minusDays(localizedDow - 1);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        LocalDate isoStart = startOfWeek(date, WeekFields.ISO);
        LocalDate isoEndExclusive = isoStart.plusWeeks(1);
        WeekFields usRules = WeekFields.of(Locale.US);
        LocalDate usStart = startOfWeek(date, usRules);
        LocalDate usEndExclusive = usStart.plusWeeks(1);

        check(isoStart.equals(LocalDate.of(2020, 12, 28)),
              "ISO Monday");
        check(isoEndExclusive.equals(LocalDate.of(2021, 1, 4)),
              "ISO next Monday");
        check(usStart.equals(LocalDate.of(2020, 12, 27)),
              "US Sunday");
        check(usEndExclusive.equals(LocalDate.of(2021, 1, 3)),
              "US next Sunday");

        System.out.println("isoStart=" + isoStart);
        System.out.println("isoEndExclusive=" + isoEndExclusive);
        System.out.println("usStart=" + usStart);
        System.out.println("usEndExclusive=" + usEndExclusive);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 IsoWeekRangeDemo.java
java IsoWeekRangeDemo
```

**Stdout đã kiểm chứng:**

```text
isoStart=2020-12-28
isoEndExclusive=2021-01-04
usStart=2020-12-27
usEndExclusive=2021-01-03
PASS
```

Mã dùng `WeekFields.dayOfWeek()` để tính vị trí thứ trong **tuần được chọn**, nên không phải viết riêng một nhánh cho Monday-start và một nhánh cho Sunday-start. Kết quả còn cho thấy cùng `LocalDate` có thể nằm trong những khoảng tuần khác nhau khi quy tắc nhóm khác nhau.

### Chuyển khoảng ngày thành khoảng Instant để truy vấn timestamp

Nếu dữ liệu gốc là **event có Instant** và báo cáo định nghĩa ngày/tuần theo giờ một chi nhánh, cần có **ZoneId của chi nhánh**:

```java
// Đoạn minh họa, start/endExclusive là LocalDate của tuần,
// zone là ZoneId nghiệp vụ đã chọn.
Instant from = start.atStartOfDay(zone).toInstant();
Instant until = endExclusive.atStartOfDay(zone).toInstant();

// Truy vấn event theo [from, until).
```

Cách này không tự giả định một tuần địa phương luôn dài đúng **7 × 24 giờ**, vì nếu tuần đi qua DST thì độ dài thực có thể khác. WeekFields chia **ngày lịch thành các tuần**; nó không tự giải quyết múi giờ hoặc đổi giờ mùa hè.

## 20. WeekFields không phải ZoneId và không phải Clock

Trong nhóm kiến thức **Temporal và Clock**, cần phân biệt:

- `WeekFields`: định nghĩa **ranh giới và cách đánh số tuần**.
- `IsoFields`: các trường/đơn vị theo tuần/quý **ISO**.
- `ZoneId`: quy tắc múi giờ để xác định **ngày địa phương từ Instant**.
- `Clock`: nguồn thời gian để lấy “bây giờ/hôm nay” có thể kiểm thử.
- `LocalDate`: một ngày lịch cụ thể, có thể áp WeekFields mà không cần Clock.

Ví dụ xử lý một event vừa được nhận:

```java
// Đoạn minh họa.
Clock clock = Clock.systemUTC();
Instant receivedAt = Instant.now(clock);
ZoneId branchZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate branchDate = receivedAt.atZone(branchZone).toLocalDate();
WeekFields businessWeeks = WeekFields.ISO;

int weekYear = branchDate.get(businessWeeks.weekBasedYear());
int week = branchDate.get(businessWeeks.weekOfWeekBasedYear());
```

**Đúng thứ tự ngữ nghĩa:** xác định thời điểm → chọn ZoneId để lấy ngày địa phương → áp quy tắc tuần cho ngày đó. Không lấy tuần từ UTC date rồi coi như kết quả tuần theo ngày địa phương của mọi chi nhánh.

Trong unit test, có thể truyền `Clock.fixed(Instant.parse(...), ZoneId.of(...))` để cố định “hôm nay” và kiểm thử ngày gần nửa đêm, ngày 31/12/01/01. `Clock` không thay thế WeekFields, và WeekFields cũng không phải timezone.

## 21. Thiết kế báo cáo và dữ liệu lưu trữ theo tuần

Một mô hình nhóm dữ liệu theo tuần có thể dùng:

```text
ruleId = "ISO"
weekBasedYear = 2020
weekNumber = 53
startDateInclusive = 2020-12-28
endDateExclusive = 2021-01-04
```

Những thông tin này đủ để truyền nghĩa tuần cho các hệ thống khác nếu quy tắc `ISO` được ghi rõ.

### Tại sao không chỉ lưu startDate?

Nếu chỉ lưu startDate, với một số bài toán vẫn có thể xác định tuần từ khoảng 7 ngày. Nhưng nếu báo cáo cần nhãn “W53/2020”, hệ thống phải biết WeekFields. Lưu hoặc mô tả **ruleId** giúp tránh tính lại bằng quy tắc của người xem.

### Tại sao không chỉ lưu weekNumber?

Tuần 1 lặp lại hằng năm và có thể bắt đầu ở ngày khác theo quy tắc khác. Một khóa như `week=1` không xác định duy nhất một khoảng ngày.

### Nếu cần ngày đầu tuần của một năm tính tuần?

Đừng đơn giản lấy 01/01 rồi cộng `(weekNumber-1)×7`. Theo ISO, tuần 1 có thể bắt đầu **trong tháng 12 năm trước**. Dùng formatter ISO week-date, công cụ TemporalField hoặc xây start từ ngày 4/1 cộng/lùi theo quy tắc; và validate tuần 53.

### Nếu báo cáo có tuần tài chính riêng?

Một doanh nghiệp có lịch tài chính **4-4-5**, năm 52/53 tuần hoặc kỳ tính tuần không trùng calendar ISO. `WeekFields` chỉ mô tả **firstDayOfWeek và minimalDaysInFirstWeek** theo lịch ISO thông thường. Nó **không phải** công cụ mô hình hóa đầy đủ mọi loại lịch tài chính 4-4-5. Nếu quy tắc fiscal có tuần bổ sung, năm bắt đầu tại ngày kinh doanh đặc biệt, hoặc kỳ 4/4/5, cần định nghĩa domain calendar/lookup table riêng và kiểm từng ranh giới.

## 22. Phân trang, truy vấn và sort dữ liệu theo tuần

Nếu một API trả tổng hợp theo tuần, nên quyết định rõ:

- Sort theo **weekBasedYear rồi weekNumber**, không trộn calendarYear với ISO week number.
- Khi cùng báo cáo có nhiều week rules, sort/partition theo **ruleId** trước khi so week key.
- Truy vấn event theo khoảng nửa mở ngày/Instant để tránh biên bị đếm hai lần.
- Dữ liệu lưu UTC Instant có thể chuyển sang **ngày địa phương theo ZoneId nghiệp vụ** trước khi group theo tuần.
- Nếu tuần được tính theo **timezone của người xem**, kết quả có thể thay đổi khi người dùng đổi vùng; cần nói rõ đây là presentation/report view chứ không phải khóa lưu trữ toàn cục.

Một bảng tổng hợp có thể đặt khóa kép:

```text
PRIMARY KEY (rule_id, week_based_year, week_number)
```

Đây chỉ là mẫu mô hình hóa; schema thật cần thêm entity dimensions như chi nhánh, loại báo cáo, kỳ hiệu lực nếu có. Quy tắc quan trọng là một tuần phải xác định bởi **cả năm tuần lẫn số tuần trong một quy tắc rõ**.

### Không dùng String làm thứ tự chính

Chuỗi `"2020-W53"` có thể hữu ích làm nhãn, nhưng logic group/sort nên hoạt động với **số năm, số tuần và rule** hoặc khoảng ngày đã được xác thực. Nếu nhận chuỗi từ bên ngoài, parse chặt chẽ thay vì cắt ký tự theo vị trí mà không kiểm tuần 53.

## 23. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Dùng `date.getYear()` làm ISO week-year | Ngày đầu/cuối năm có thể thuộc năm tuần khác | `IsoFields.WEEK_BASED_YEAR` |
| Dùng `WeekFields.ISO.weekOfYear()` thay weekOfWeekBasedYear | Có thể trả **tuần 0** | Chọn đúng trường theo nghĩa nhóm |
| Dùng `YYYY-MM-dd` cho ngày lịch | YYYY là week-based-year | `uuuu-MM-dd` hoặc ISO_LOCAL_DATE |
| Giả định `YYYY-'W'ww-e` luôn ISO | Pattern tuần theo locale | ISO_WEEK_DATE nếu cần ISO ổn định |
| Chấp nhận mọi năm có tuần 53 | Không phải ISO năm nào cũng có 53 tuần | Validate theo năm tính tuần |
| Chỉ lưu `weekNumber` | Trùng giữa nhiều năm/tuần rules | Lưu weekBasedYear + rule |
| Lấy tuần đầu bằng 01/01 | Tuần 1 ISO có thể bắt đầu tháng 12 trước | Dùng ISO rule/WeekFields |
| Dùng `WeekFields.of(Locale.getDefault())` cho báo cáo chuẩn | Server locale thay đổi số liệu | Dùng WeekFields nghiệp vụ cố định |
| Nghĩ `Locale.US` nghĩa là timezone Mỹ | Locale không phải ZoneId | Tách zone và quy tắc tuần |
| Nghĩ WeekFields quy đổi Instant sang ngày | WeekFields chỉ thao tác trên ngày/Temporal | Xác định LocalDate ở ZoneId trước |
| Coi mọi tuần có đúng 168 giờ | Qua DST tuần địa phương có thể ngắn/dài khác | Lọc Instant bằng startOfDay(zone) |
| Dùng `DayOfWeek.getValue()` làm localized day number | ISO Monday=1 không phải mọi locale | `rules.dayOfWeek()` |
| Nghĩ `weekOfMonth()` luôn từ 1 | Có thể trả 0 | Hiểu minimalDays |
| Cộng `WEEK_BASED_YEARS` như calendar years | Quy tắc khác, tuần 53 có thể bị chỉnh | Chọn TemporalUnit đúng nghĩa |
| Dùng `IsoFields.QUARTER_OF_YEAR` cho mọi fiscal quarter | Năm tài chính có thể lệch | Mô hình lịch tài chính riêng |
| Group dữ liệu theo rule của từng người xem rồi dùng chung một khóa | Cùng nhãn W01 khác khoảng ngày | Gắn ruleId, giữ nhất quán |
| Không test 31/12 và 01/01 | Lỗi chỉ lộ ra tại biên | Test week-year boundary |
| Format/parse chuỗi tuần không strict | Có thể nhận tuần 53 không hợp lệ | ISO_WEEK_DATE hoặc validation tương đương |
| Test output locale giữa mọi JDK phải từng ký tự | Locale provider có thể khác | Test semantic, cố định provider khi cần |
| Sửa số tuần “lệch một” bằng plusWeeks tùy tiện | Giấu lỗi định nghĩa tuần | Xác định đúng firstDay/minimalDays |

## 24. Ma trận kiểm thử nên có

| Test | Kỳ vọng |
| --- | --- |
| Ngày giữa năm như 2026-11-06 | IsoFields tuần và WeekFields.ISO thống nhất |
| 2020-12-31 | ISO 2020-W53-4 |
| 2021-01-01 | ISO 2020-W53-5 |
| 2021-01-04 | ISO 2021-W01-1 |
| ISO year 2020 | Có tuần 53 |
| ISO year 2021 | Tuần 53 bị từ chối khi parse |
| DateTimeFormatter.ISO_WEEK_DATE round-trip | Về đúng LocalDate ban đầu |
| Pattern yyyy/uuuu so YYYY | Calendar year khác week-based-year tại biên |
| Locale.US và Locale.FRANCE | Có thể khác first-day/minimalDays |
| Locale tuần theo môi trường | Test hoặc cấu hình JDK/provider rõ |
| WeekFields.ISO.weekOfYear ở 2021-01-01 | 0 |
| WeekFields.ISO.weekOfWeekBasedYear cùng ngày | 53 |
| WeekFields.ISO.weekOfMonth ở đầu tháng | Có thể 0 |
| weekOfWeekBasedYear + weekBasedYear | Cặp khóa đúng của kỳ |
| WeekFields.dayOfWeek US | Chủ Nhật=1, Thứ Sáu=6 |
| WeekFields.dayOfWeek ISO | Thứ Hai=1, Thứ Sáu=5 |
| Week range ISO | [2020-12-28, 2021-01-04) |
| Week range US | [2020-12-27, 2021-01-03) |
| Quý 2026-11-06 | Q4, ngày thứ 37 của quý |
| 2024-02-29 | Ngày thứ 60 quý 1 |
| Cộng một ISO QUARTER_YEARS | Tương đương ba tháng theo quy tắc ngày |
| Cộng WEEK_BASED_YEARS từ 2020-W53 | Có thể phải điều chỉnh xuống tuần 52 |
| Timestamp sát nửa đêm UTC | Ngày và tuần địa phương có thể khác UTC |
| Lọc tuần có DST | Khoảng ngày chuyển sang Instant theo ZoneId, không assume 168 giờ |
| Fiscal 4-4-5 | Không dùng WeekFields như full fiscal calendar |
| Báo cáo dùng nhiều locale | Quy tắc tuần được xác định trước, không phụ thuộc người xem |

Các test quanh ngày 1/1 đặc biệt quan trọng. Hầu hết ngày giữa năm cho giá trị calendar year trùng week-based-year nên lỗi `YYYY`/`yyyy` rất dễ tồn tại lâu mà không được phát hiện.

## 25. Bài tập thực hành với đáp án

**Bài 1 — ngày đầu năm:** ngày `2021-01-01` có year 2021. Theo ISO, năm tính tuần và tuần là gì?

**Đáp án:** năm tính tuần **2020**, tuần **53**, ngày thứ **5** trong tuần ISO. Giá trị ISO week-date là `2020-W53-5`.

**Bài 2 — hai locale:** dùng WeekFields theo US và France cho cùng ngày `2021-01-01`. Vì sao kết quả week-year có thể khác?

**Đáp án:** US thường Sunday-start và minimalDays=1, còn France Monday-start và minimalDays=4. Cùng ngày thuộc **US 2021-W01** nhưng **ISO/France 2020-W53** theo quy tắc thử nghiệm.

**Bài 3 — khóa nhóm:** API lưu `calendarYear=2021` và `isoWeek=53` cho 01/01/2021. Khóa nào sai?

**Đáp án:** ghép calendarYear với ISO week. Phải dùng **weekBasedYear=2020** nếu báo cáo theo ISO.

**Bài 4 — tuần 0:** `weekOfYear()` của 01/01/2021 theo ISO trả 0. Có nên tự chuyển thành 1?

**Đáp án:** không. Nếu cần tuần theo week-based-year, dùng `weekOfWeekBasedYear` cùng `weekBasedYear`. Tuần 0 có nghĩa riêng trong trường `weekOfYear`.

**Bài 5 — định dạng sai:** ngày 01/01/2021 format với `YYYY-MM-dd` theo France ra 2020-01-01. Vì sao?

**Đáp án:** `Y` là năm tính tuần, còn `M` và `d` là tháng/ngày lịch. Đây là mẫu trộn hai hệ năm; dùng `uuuu-MM-dd` hoặc ISO_LOCAL_DATE.

**Bài 6 — tuần 53:** parser nhận `2021-W53-5` theo chuẩn ISO. Có hợp lệ không?

**Đáp án:** không. ISO week-year 2021 không có tuần 53; `ISO_WEEK_DATE` strict parser từ chối.

**Bài 7 — truy vấn dữ liệu:** người dùng muốn event của tuần ISO chứa 01/01/2021 theo giờ Hà Nội. Chọn khoảng nào?

**Đáp án:** lấy khoảng ngày **[2020-12-28, 2021-01-04)**, quy đổi hai mốc đầu ngày bằng `ZoneId.of("Asia/Ho_Chi_Minh")` thành Instant rồi lọc theo khoảng nửa mở.

**Bài 8 — quý ISO:** ngày 06/11/2026 thuộc quý nào và ngày thứ mấy trong quý?

**Đáp án:** quý 4, ngày thứ **37**, ngày bắt đầu quý là **01/10/2026**.

**Bài 9 — lịch tài chính 4-4-5:** công ty yêu cầu năm tài chính gồm các kỳ 4, 4 và 5 tuần. WeekFields có tự mô hình hóa toàn bộ lịch này không?

**Đáp án:** không. WeekFields chỉ đặt ranh giới và đánh số tuần theo first-day/minimal-days; cần mô hình lịch tài chính riêng cho năm 4-4-5, tuần bổ sung và kỳ đặc thù.

**Bài 10 — Clock:** một job chạy sau nửa đêm UTC nhưng trước nửa đêm của chi nhánh. Có nên dùng LocalDate.now(Clock.systemUTC()) rồi tính tuần chi nhánh không?

**Đáp án:** không nếu báo cáo theo ngày địa phương. Cần lấy Instant rồi đổi qua ZoneId chi nhánh, sau đó áp WeekFields của doanh nghiệp.

## 26. Câu hỏi tự kiểm tra

**1. ISO week bắt đầu vào thứ mấy?**  
Thứ Hai.

**2. ISO tuần 1 yêu cầu ít nhất bao nhiêu ngày của năm mới?**  
Bốn ngày.

**3. 2021-01-01 thuộc ISO week-year nào?**  
2020, tuần 53.

**4. WeekFields.of(Locale.US) có bắt buộc trả cùng quy tắc với WeekFields.ISO không?**  
Không. Quy tắc locale có thể khác ISO.

**5. weekOfYear và weekOfWeekBasedYear có khác nhau không?**  
Có. Một trường đếm trong năm dương lịch, một trường đếm trong năm tính tuần.

**6. Vì sao weekOfYear có thể bằng 0?**  
Vì những ngày đầu năm chưa tạo một tuần 1 đủ số ngày tối thiểu theo quy tắc đang dùng.

**7. Vì sao pattern YYYY không nên dùng cho ngày lịch?**  
Vì Y biểu diễn week-based-year, có thể khác năm dương lịch quanh ranh giới.

**8. Khi nào nên dùng DateTimeFormatter.ISO_WEEK_DATE?**  
Khi giao tiếp hoặc parse **ngày theo ISO week-date** đã được định nghĩa rõ.

**9. Năm ISO nào cũng có 53 tuần không?**  
Không, đa số có 52 tuần.

**10. WeekFields có tự giải quyết DST/ZoneId cho Instant không?**  
Không. Phải chuyển Instant sang LocalDate tại ZoneId nghiệp vụ trước.

**11. IsoFields có trường gì ngoài tuần?**  
Quý trong năm, ngày của quý và đơn vị cộng theo quý.

**12. Cộng một WEEK_BASED_YEARS có luôn giống plusYears(1) không?**  
Không. Năm tuần có thể có 52/53 tuần và phép cộng giữ logic ISO week-date.

**13. Khi tạo báo cáo ISO tuần, có nên phụ thuộc Locale mặc định của server?**  
Không. Dùng WeekFields.ISO/IsoFields tường minh.

**14. Với tuần có DST, có được lấy startInstant.plus(Duration.ofHours(168)) làm end không?**  
Không nếu muốn tuần theo lịch địa phương. Dùng đầu ngày của tuần kế tiếp trong ZoneId.

## Tài liệu Java SE 8 chính thức

- [WeekFields](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/WeekFields.html): first day, minimal days, các trường ngày-tuần-tháng-năm và week-based-year.
- [IsoFields](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/IsoFields.html): tuần ISO, năm tính tuần, quý, day-of-quarter, WEEK_BASED_YEARS/QUARTER_YEARS.
- [TemporalField](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalField.html): giao diện trường ngày giờ.
- [TemporalUnit](https://docs.oracle.com/javase/8/docs/api/java/time/temporal/TemporalUnit.html): đơn vị cộng/trừ temporal.
- [LocalDate](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDate.html): get/with/plus và phép ngày lịch.
- [DayOfWeek](https://docs.oracle.com/javase/8/docs/api/java/time/DayOfWeek.html): thứ trong tuần ISO, Monday=1 đến Sunday=7.
- [DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html): ISO_WEEK_DATE, ISO_LOCAL_DATE và khác biệt Y/y/u trong pattern.
- [Clock](https://docs.oracle.com/javase/8/docs/api/java/time/Clock.html): nguồn thời gian có thể kiểm thử.
- [ZoneId](https://docs.oracle.com/javase/8/docs/api/java/time/ZoneId.html): chuyển Instant thành ngày địa phương trước khi tính tuần.
- [Locale](https://docs.oracle.com/javase/8/docs/api/java/util/Locale.html): quy tắc địa phương, không đồng nghĩa timezone.

**Ghi nhớ:** một ngày có thể thuộc **calendar year khác week-based-year**. Khi cần tuần ISO, dùng `IsoFields.WEEK_BASED_YEAR` cùng `WEEK_OF_WEEK_BASED_YEAR` hoặc `WeekFields.ISO`; khi cần tuần theo locale/doanh nghiệp, chọn `WeekFields` với **firstDayOfWeek + minimalDaysInFirstWeek** tường minh. Không trộn `getYear()` với số tuần ISO, không dùng `YYYY-MM-dd` cho ngày lịch, không mặc định mọi năm có tuần 53, và không coi một tuần địa phương luôn dài đúng 168 giờ thực tế.