# Month và DayOfWeek là enum có ý nghĩa lịch

## 1. Tại sao không chỉ dùng số hoặc chuỗi?

`Month.MARCH` nói rõ “tháng Ba”; `DayOfWeek.MONDAY` nói rõ “thứ Hai”. Trong một lời gọi như `LocalDate.of(2024, Month.MARCH, 15)`, kiểu enum giúp người đọc hiểu vai trò dữ liệu ngay tại chỗ và tránh truyền nhầm một số không có tên.

Đây không chỉ là hai danh sách hằng. Chúng biết giá trị lịch ISO, cách dịch chuyển theo chu kỳ, cách lấy tên hiển thị và cách điều chỉnh một ngày. Tuy nhiên, mỗi enum vẫn chỉ biểu diễn **một phần của ngày**, không phải ngày đầy đủ.

| Kiểu | Biểu diễn | Những gì chưa có |
| --- | --- | --- |
| `Month` | Một trong 12 tháng | Năm và ngày trong tháng |
| `DayOfWeek` | Một trong 7 thứ | Tuần nào, tháng nào, năm nào |
| `LocalDate` | Ngày cụ thể trong lịch ISO | Giờ và múi giờ |

Ví dụ `Month.FEBRUARY` chưa thể trả lời tháng Hai có 28 hay 29 ngày nếu chưa biết năm nhuận hay không. `DayOfWeek.FRIDAY` cũng chưa phải lịch hẹn “thứ Sáu tuần tới”.

## 2. Giá trị ISO khác ordinal

`Month.getValue()` trả 1 đến 12, với tháng Một là 1. `DayOfWeek.getValue()` trả 1 đến 7, với thứ Hai là 1 và Chủ nhật là 7.

```java
Month month = Month.of(3);                   // MARCH
int monthNumber = Month.MARCH.getValue();    // 3
DayOfWeek day = DayOfWeek.of(1);             // MONDAY
int sundayNumber = DayOfWeek.SUNDAY.getValue(); // 7
```

Đoạn trên là mã minh họa trong một phương thức, cần import `java.time.Month` và `java.time.DayOfWeek`.

`ordinal()` là vị trí khai báo enum bắt đầu từ 0, không phải số lịch. `Month.JANUARY.ordinal()` bằng 0, trong khi số tháng đúng là 1. Dùng `getValue()` cho biểu diễn số theo hợp đồng lịch, và `of(number)` để chuyển ngược có kiểm tra miền. [Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html)

`Month.of(0)`, `Month.of(13)` hoặc `DayOfWeek.of(0)` không hợp lệ và ném `DateTimeException`. Không dùng `values()[number]` làm phép chuyển đổi số lịch: cách đó vừa sai gốc chỉ số vừa đưa ra loại lỗi không thể hiện đúng miền dữ liệu.

Khi tích hợp API cũ, cần ánh xạ rõ ràng: `Calendar` dùng tháng bắt đầu từ 0 và quy ước số thứ khác `DayOfWeek`. Không truyền thẳng các số đó vào API `java.time` mà chưa kiểm tra hợp đồng nguồn.

## 3. Chuyển từ ngày, so sánh và định danh

Từ `LocalDate`, lấy các enum qua `getMonth()` và `getDayOfWeek()`. Có thể dùng `Month.from(date)` hoặc `DayOfWeek.from(date)` khi nhận một nguồn thời gian tổng quát đủ thông tin.

Enum có thể so sánh bằng `==`, dùng trong `switch`, làm khóa `EnumMap` hoặc phần tử `EnumSet`. Ví dụ tập ngày đóng cửa không cần là tập số 6, 7 khó đọc.

`valueOf("MARCH")` phân tích **tên hằng chính xác**, có phân biệt hoa/thường; nó không hiểu `"March"`, `"tháng 3"` hoặc `"03"`. Chuỗi không khớp tên hằng gây `IllegalArgumentException`, khác với số ngoài miền đưa vào `of`.

`name()` và `toString()` biểu diễn tên hằng như `MONDAY`; chúng không phải tên đã dịch cho giao diện người dùng. Nếu lưu tên hằng trong dữ liệu trao đổi, hãy công bố rõ quy ước đó và kiểm tra đầu vào.

## 4. Phép cộng/trừ trên enum quay vòng

`Month.DECEMBER.plus(2)` cho `FEBRUARY`; `DayOfWeek.SUNDAY.plus(1)` cho `MONDAY`. Các phép `plus(long)`/`minus(long)` làm việc theo chu kỳ 12 tháng hoặc 7 ngày, chấp nhận cả lượng âm.

Chúng **không lưu số vòng đã đi qua**: cộng hai tháng vào enum tháng Mười Hai không tạo ra năm mới; cộng 7 vào một thứ trả lại đúng thứ đó. Muốn tiến ngày thực tế và giữ năm/tháng, thực hiện trên `LocalDate`.

Tương tự, thứ tự tự nhiên của enum theo tháng Một đến tháng Mười Hai hoặc thứ Hai đến Chủ nhật không cho biết lần xuất hiện tiếp theo gần nhất từ hôm nay. Chủ nhật có số lớn hơn thứ Hai, nhưng thứ Hai kế tiếp có thể chỉ cách Chủ nhật một ngày. [DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html)

## 5. Month cung cấp thông tin tháng nhưng cần ngữ cảnh năm

| Phương thức | Công dụng |
| --- | --- |
| `length(leapYear)` | Số ngày của tháng khi đã biết năm nhuận hay không |
| `minLength()` / `maxLength()` | Cận số ngày của tháng |
| `firstDayOfYear(leapYear)` | Số thứ tự của ngày đầu tháng trong năm |
| `firstMonthOfQuarter()` | Tháng đầu quý chứa tháng hiện tại |

Với tháng Hai, `length(false)` bằng 28, `length(true)` bằng 29. Cờ `leapYear` là thông tin do mã gọi cung cấp; `Month` không tự biết năm. Với một ngày có sẵn, `date.lengthOfMonth()` hoặc `YearMonth.lengthOfMonth()` thường diễn đạt ý định rõ hơn.

Đoạn minh họa trong một phương thức:

```java
int year = 2024;
int days = Month.FEBRUARY.length(java.time.Year.isLeap(year)); // 29.
Month firstInQuarter = Month.AUGUST.firstMonthOfQuarter();   // JULY.
```

## 6. Điều chỉnh một ngày khác với tìm ngày kế tiếp

Hai enum triển khai `TemporalAdjuster`, nên có thể truyền cho `LocalDate.with(...)`. Đối tượng ngày ban đầu không bị sửa.

- `date.with(Month.FEBRUARY)` đặt tháng thành tháng Hai, giữ năm và điều chỉnh ngày cuối tháng khi cần.
- `date.with(DayOfWeek.MONDAY)` đặt thứ Hai trong cùng tuần ISO của ngày đó; kết quả có thể lùi về quá khứ.
- `date.with(TemporalAdjusters.next(MONDAY))` tìm thứ Hai tiếp theo, luôn sau ngày hiện tại.
- `date.with(TemporalAdjusters.nextOrSame(MONDAY))` giữ ngày hiện tại nếu đã là thứ Hai; nếu không thì tìm lần tiếp theo.

Không thay `next` bằng `with(dayOfWeek)` khi viết lịch nhắc. Muốn thứ Sáu đầu tiên hoặc cuối cùng của tháng, dùng các quy tắc như `firstInMonth(FRIDAY)` hoặc `lastInMonth(FRIDAY)`. [TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)

## 7. Chương trình chạy được

Lưu thành `CalendarEnumsDemo.java`. Hàm `isClosed` dưới đây minh họa một lịch đóng cửa thứ Bảy/Chủ nhật được chọn riêng cho ví dụ.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.temporal.TemporalAdjusters;
import java.util.EnumSet;
import java.util.Set;

public class CalendarEnumsDemo {
    private static final Set<DayOfWeek> CLOSED_DAYS =
            EnumSet.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY);

    static boolean isClosed(LocalDate date) {
        return CLOSED_DAYS.contains(date.getDayOfWeek());
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, Month.JUNE, 19);
        LocalDate endOfJanuary = LocalDate.of(2024, Month.JANUARY, 31);

        System.out.println("month=" + date.getMonth());
        System.out.println("dayOfWeek=" + date.getDayOfWeek());
        System.out.println("marchValue=" + Month.MARCH.getValue());
        System.out.println("sundayValue=" + DayOfWeek.SUNDAY.getValue());
        System.out.println("monthWrap=" + Month.DECEMBER.plus(2));
        System.out.println("dayWrap=" + DayOfWeek.SUNDAY.plus(1));
        System.out.println("februaryCommon=" + Month.FEBRUARY.length(false));
        System.out.println("februaryLeap=" + Month.FEBRUARY.length(true));
        System.out.println("quarterStart=" + Month.AUGUST.firstMonthOfQuarter());

        System.out.println("setFebruary=" + endOfJanuary.with(Month.FEBRUARY));
        System.out.println("sameWeekMonday=" + date.with(DayOfWeek.MONDAY));
        System.out.println("nextMonday="
                + date.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("nextWednesday="
                + date.with(TemporalAdjusters.next(DayOfWeek.WEDNESDAY)));
        System.out.println("sameWednesday="
                + date.with(TemporalAdjusters.nextOrSame(DayOfWeek.WEDNESDAY)));
        System.out.println("firstFriday="
                + date.with(TemporalAdjusters.firstInMonth(DayOfWeek.FRIDAY)));
        System.out.println("sundayClosed="
                + isClosed(LocalDate.of(2024, Month.JUNE, 23)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 CalendarEnumsDemo.java
java CalendarEnumsDemo
```

Stdout chính xác:

```text
month=JUNE
dayOfWeek=WEDNESDAY
marchValue=3
sundayValue=7
monthWrap=FEBRUARY
dayWrap=MONDAY
februaryCommon=28
februaryLeap=29
quarterStart=JULY
setFebruary=2024-02-29
sameWeekMonday=2024-06-17
nextMonday=2024-06-24
nextWednesday=2024-06-26
sameWednesday=2024-06-19
firstFriday=2024-06-07
sundayClosed=true
```

`sameWeekMonday` lùi từ thứ Tư 19/6 về thứ Hai 17/6; `nextMonday` tiến đến 24/6. `firstFriday` là thứ Sáu đầu **tháng đang có**, nên cũng có thể nằm trước ngày gốc.

## 8. Tên hiển thị và quy tắc tuần theo địa phương

Để hiển thị tiếng Việt, chọn `Locale` và `TextStyle` rõ ràng:

```java
java.util.Locale vi = java.util.Locale.forLanguageTag("vi-VN");
String monthLabel = Month.MARCH.getDisplayName(
        java.time.format.TextStyle.FULL, vi);
String dayLabel = DayOfWeek.MONDAY.getDisplayName(
        java.time.format.TextStyle.FULL, vi);
```

Đây là đoạn minh họa; dạng viết hoa và cách rút gọn cụ thể có thể phụ thuộc dữ liệu ngôn ngữ của JDK. Dùng nhãn để hiển thị, giữ enum/số theo hợp đồng để xử lý hoặc lưu dữ liệu. Không phân tích ngược nhãn giao diện bằng `valueOf`.

Thay `Locale` của tên hiển thị không đổi `DayOfWeek.SUNDAY.getValue()` thành 1. Giá trị enum luôn theo ISO. Nếu giao diện cần tuần bắt đầu từ Chủ nhật hoặc tính số tuần theo quy ước địa phương, dùng `WeekFields` phù hợp. Ví dụ `WeekFields.SUNDAY_START.dayOfWeek()` cho trường đánh số Chủ nhật là 1, nhưng không đổi định nghĩa enum.

Khái niệm ngày đầu tuần và số ngày tối thiểu của tuần đầu năm là hai tham số của quy tắc tuần. Chúng cũng không xác định ngày nghỉ của doanh nghiệp. [WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)

## 9. Giới hạn nghiệp vụ cần giữ rõ

`DayOfWeek` không tự biết ngày nghỉ lễ, lịch làm việc theo ca hoặc cuối tuần của từng quốc gia. Tập `CLOSED_DAYS` trong ví dụ là cấu hình minh họa, không phải quy tắc toàn cầu. Một lịch làm việc thực tế còn cần ngày lễ và ngoại lệ theo ngày.

Cả hai enum triển khai `TemporalAccessor` để cung cấp trường thích hợp và `TemporalAdjuster` để điều chỉnh đối tượng khác; chúng không triển khai `Temporal`. Các phương thức `plus`/`minus` riêng của enum không đồng nghĩa có thể dùng chúng như ngày đầy đủ cho mọi phép tính.

Giữ ba câu hỏi tách biệt khi chọn API: “đang là tháng/thứ nào?”, “muốn đổi thành tháng/thứ nào?”, và “muốn tìm ngày xuất hiện tiếp theo nào?”. Mỗi câu dẫn đến thao tác khác nhau.

## 10. Tự thực hành

1. Chuyển số 12 thành `Month`, rồi cộng một tháng trên enum; so sánh với cộng một tháng trên `LocalDate.of(2024, 12, 15)`.
2. Với ngày thứ Hai, so sánh `next(MONDAY)` và `nextOrSame(MONDAY)`.
3. Tạo lịch đóng cửa riêng gồm thứ Sáu và thứ Bảy bằng `EnumSet`.
4. Giải thích vì sao `DayOfWeek.SUNDAY.ordinal()` không phải số Chủ nhật theo ISO.

Đối chiếu: (1) enum ra `JANUARY` không có năm; ngày đầy đủ ra `2025-01-15`; (2) lần lượt sau 7 ngày và giữ nguyên hôm nay; (3) dùng đúng hai hằng enum; (4) `ordinal` bắt đầu từ 0, còn số ISO phải lấy bằng `getValue()`.