# TemporalAdjuster, TemporalAdjusters và điều chỉnh lịch trong Java

## 1. Bài toán và mục tiêu

Trong ứng dụng thực tế, rất nhiều quy tắc thời gian không phải “cộng đúng N ngày”: lấy **ngày cuối tháng**, **thứ Hai tiếp theo**, **thứ Sáu cuối cùng của tháng**, **ngày làm việc đầu tiên sau một ngày nghỉ**, hoặc **thời điểm cuộc họp theo lịch địa phương**. Đây là những thao tác có ý nghĩa lịch (calendar), không đơn giản là đo một số giây trên dòng thời gian.

Từ Java 8, gói **java.time.temporal** cung cấp cơ chế **TemporalAdjuster** và tập factory **TemporalAdjusters** để đóng gói quy tắc điều chỉnh ngày giờ. Các API này **vẫn còn được hỗ trợ hiện nay** trong JDK hiện đại, thích hợp thay cho logic cộng/trừ ngày thủ công dễ sai khi qua tháng, năm nhuận hoặc ngày đổi giờ.

Sau bài học, bạn có thể:

1. Phân biệt **Temporal**, **TemporalAccessor**, **TemporalAdjuster** và **TemporalAdjusters**.
2. Hiểu lời gọi **temporal.with(adjuster)** và hợp đồng của **adjustInto(Temporal)**.
3. Sử dụng các adjuster chuẩn: **firstDayOfMonth**, **lastDayOfMonth**, **firstDayOfNextMonth**, **firstDayOfYear**, **lastDayOfYear**, **firstDayOfNextYear**.
4. Dùng **next**, **nextOrSame**, **previous**, **previousOrSame**, **firstInMonth**, **lastInMonth**, **dayOfWeekInMonth** đúng trường hợp.
5. Nhận ra khác biệt giữa điều chỉnh theo ngày lịch và cộng thời lượng **Duration**.
6. Viết adjuster riêng bằng **TemporalAdjusters.ofDateAdjuster** hoặc triển khai trực tiếp interface **TemporalAdjuster**.
7. Thiết kế “ngày làm việc” gồm cuối tuần, ngày nghỉ được cấu hình và quy tắc **strictly next** so với **or same**.
8. Xử lý điều chỉnh lịch trên LocalDate, LocalDateTime, ZonedDateTime; hiểu giới hạn kiểu không có trường ngày như LocalTime và Instant.
9. Tránh sai lệch do **DST gap/overlap**, múi giờ hệ thống và lịch lặp trong nhiều khu vực.
10. Kiểm tra các quy tắc lịch bằng **Clock.fixed** và những chương trình Java 17 có stdout xác định.

**Lưu ý phiên bản / Special Note:** Những API TemporalAdjuster, TemporalAdjusters, LocalDate, LocalDateTime, ZonedDateTime, Clock, ZoneId và ChronoField đều là API Java Time còn áp dụng; không dùng cách tiếp cận thời gian đã legacy. Bảy ví dụ độc lập dưới đây biên dịch và chạy với **JDK 17+**.

## 2. Tại sao điều chỉnh lịch khác cộng ngày?

Xem hai yêu cầu:

- “Sau 7 ngày” có thể dùng LocalDate.plusDays(7) khi ý nghĩa là **7 ngày lịch**.
- “Thứ Hai kế tiếp” cần tìm ngày có **DayOfWeek.MONDAY**, không phải một số ngày cố định từ mọi ngày xuất phát.
- “Ngày cuối tháng” phải biết độ dài tháng: tháng Hai năm 2024 có 29 ngày, năm không nhuận có 28.
- “Ngày làm việc tiếp theo” cần quy tắc cuối tuần và lịch nghỉ lễ của doanh nghiệp; cộng một ngày không đủ nếu hiện tại là thứ Sáu.
- “24 giờ thực sau thời điểm hiện tại” là việc cộng **Duration** trên một Instant; không nên biểu diễn như đổi ngày lịch trong một ZoneId có DST.

TemporalAdjuster biểu diễn **chiến lược biến đổi một temporal object theo quy tắc lịch**. Nó giúp tách quy tắc khỏi code gọi, đặt tên được cho hành vi, tái sử dụng và kiểm thử trên các ngày biên.

~~~java
// Mảnh mã, cần import java.time.* và java.time.temporal.*.
LocalDate date = LocalDate.of(2024, 2, 15);
LocalDate last = date.with(TemporalAdjusters.lastDayOfMonth());
// last = 2024-02-29; date vẫn là 2024-02-15.
~~~

Ở đây phương thức **with(adjuster)** không sửa date gốc. LocalDate là immutable; kết quả là đối tượng ngày mới.

## 3. Bốn khái niệm: TemporalAccessor, Temporal, TemporalAdjuster, TemporalAdjusters

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **TemporalAccessor** | Cho phép truy vấn field thời gian, chẳng hạn ngày trong tháng; bản thân không cam kết sửa field | LocalDate, Instant, MonthDay |
| **Temporal** | Mở rộng khả năng truy vấn để điều chỉnh field hoặc cộng/trừ temporal unit | LocalDate, LocalDateTime, ZonedDateTime, LocalTime, Instant |
| **TemporalAdjuster** | Interface chiến lược: nhận một Temporal và trả Temporal đã được điều chỉnh | Lambda hợp lệ hoặc class tự triển khai |
| **TemporalAdjusters** | Utility class cung cấp các factory tạo adjuster tiêu chuẩn | lastDayOfMonth(), next(MONDAY) |

Điểm cần phân biệt: **TemporalAdjuster** là một *interface*, còn **TemporalAdjusters** (có chữ s cuối) là lớp chứa các factory static. Không có phương thức gọi trên class TemporalAdjusters để biến đổi trực tiếp ngày mà không tạo adjuster hoặc sử dụng kết quả nó trả về.

~~~java
// Mảnh mã, cần import java.time.temporal.TemporalAdjuster.
TemporalAdjuster endOfMonth = TemporalAdjusters.lastDayOfMonth();
LocalDate adjusted = date.with(endOfMonth);
~~~

Mặc dù LocalDate và một số kiểu Java Time cũng có thể triển khai TemporalAdjuster, trong bài này cách dùng phổ biến là **đưa một quy tắc adjuster vào phương thức with của Temporal**.

### Cú pháp khuyến nghị

JavaDoc TemporalAdjuster mô tả hai cách tương đương về ý nghĩa:

~~~java
// Mảnh mã, temporal là Temporal và adjuster là TemporalAdjuster.
Temporal result1 = adjuster.adjustInto(temporal);
Temporal result2 = temporal.with(adjuster);
~~~

**temporal.with(adjuster)** thường được khuyến nghị vì diễn đạt dễ đọc: “lấy temporal và áp dụng quy tắc này”. Khi biến có kiểu LocalDate, LocalDateTime hoặc ZonedDateTime, phương thức with tương ứng thường trả lại **cùng kiểu tĩnh** của object đó, tiện để dùng tiếp.

### Hợp đồng quan trọng của adjustInto

Một TemporalAdjuster đúng hợp đồng phải:

1. Nhận một Temporal không null và thực hiện đúng quy tắc đã document.
2. **Không sửa trực tiếp input**; trả về một kết quả đã điều chỉnh.
3. Trả một Temporal có **cùng observable type** với input.
4. Có thể được gọi đồng thời từ nhiều thread; logic phải thread-safe.
5. Nêu rõ phạm vi hỗ trợ: có adjuster chỉ hợp với các kiểu có trường ngày (ví dụ LocalDate), không phải mọi Temporal.
6. Xử lý DateTimeException nếu không thể điều chỉnh và ArithmeticException khi tính toán vượt phạm vi.

Các adjuster chuẩn từ TemporalAdjusters là **immutable** theo JavaDoc. Với adjuster tự viết, dùng state bất biến và tránh mutable shared state hoặc thao tác I/O không cần thiết trong phép tính ngày.

## 4. Những factory chuẩn dùng thường xuyên

| Phương thức TemporalAdjusters | Kết quả theo ISO date | Tình huống |
|---|---|---|
| **firstDayOfMonth()** | Ngày 1 của tháng hiện tại | Kỳ báo cáo tháng |
| **lastDayOfMonth()** | Ngày cuối tháng hiện tại | Chốt tháng, hạn tháng |
| **firstDayOfNextMonth()** | Ngày 1 của tháng sau | Ranh giới kỳ mới |
| **firstDayOfYear()** | Ngày 1/1 của năm hiện tại | Bắt đầu năm |
| **lastDayOfYear()** | Ngày 31/12 của năm hiện tại | Kết thúc năm |
| **firstDayOfNextYear()** | Ngày 1/1 của năm sau | Chu kỳ tiếp theo |
| **firstInMonth(day)** | Lần xuất hiện đầu tiên của thứ đó trong tháng | Thứ Hai đầu tháng |
| **lastInMonth(day)** | Lần xuất hiện cuối của thứ đó trong tháng | Thứ Sáu cuối tháng |
| **dayOfWeekInMonth(n, day)** | Lần xuất hiện thứ n theo quy tắc ordinal | Thứ Ba thứ hai của tháng |
| **next(day)** | Lần xuất hiện kế tiếp, **sau** ngày gốc | Thứ Hai tiếp theo |
| **nextOrSame(day)** | Ngày gốc nếu trùng thứ; nếu không, lần kế tiếp | Không lùi deadline đã đúng thứ |
| **previous(day)** | Lần xuất hiện gần nhất, **trước** ngày gốc | Thứ Sáu trước đó |
| **previousOrSame(day)** | Ngày gốc nếu trùng; nếu không, lần trước | Ngày trong tuần không muộn hơn |
| **ofDateAdjuster(operator)** | Dùng UnaryOperator<LocalDate> để tạo adjuster | Quy tắc ngày làm việc tùy chỉnh |

Đối số DayOfWeek là enum **MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY** của java.time. Không phải số thứ theo Locale. Quy tắc DayOfWeek trong ISO đặt Monday=1, Sunday=7; khi cần tuần theo thị trường, không tự gán “Chủ nhật luôn là ngày nghỉ” cho mọi doanh nghiệp.

### Các factory theo đầu và cuối tháng/năm

Đối với LocalDate **2024-02-15**:

~~~text
firstDayOfMonth       -> 2024-02-01
lastDayOfMonth        -> 2024-02-29
firstDayOfNextMonth   -> 2024-03-01
firstDayOfYear        -> 2024-01-01
lastDayOfYear         -> 2024-12-31
firstDayOfNextYear    -> 2025-01-01
~~~

Các factory đúng nhờ dựa vào quy tắc độ dài tháng/năm của chronology được hỗ trợ; không phải cộng trừ cố định 28, 30 hoặc 365 ngày.

## 5. Ví dụ hoàn chỉnh 1 — ngày đầu/cuối tháng và năm

Tạo file **BuiltInAdjustersDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.TemporalAdjusters;

public class BuiltInAdjustersDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 15);
        System.out.println("base=" + date);
        System.out.println("firstMonth=" + date.with(TemporalAdjusters.firstDayOfMonth()));
        System.out.println("lastMonth=" + date.with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("firstNextMonth=" + date.with(TemporalAdjusters.firstDayOfNextMonth()));
        System.out.println("firstYear=" + date.with(TemporalAdjusters.firstDayOfYear()));
        System.out.println("lastYear=" + date.with(TemporalAdjusters.lastDayOfYear()));
        System.out.println("firstNextYear=" + date.with(TemporalAdjusters.firstDayOfNextYear()));
        LocalDateTime meeting = LocalDateTime.of(2024, 2, 15, 16, 45);
        System.out.println("dateTimeLastMonth="
                + meeting.with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("original=" + date);
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~text
javac --release 17 BuiltInAdjustersDemo.java
java BuiltInAdjustersDemo
~~~

Stdout chính xác:

~~~text
base=2024-02-15
firstMonth=2024-02-01
lastMonth=2024-02-29
firstNextMonth=2024-03-01
firstYear=2024-01-01
lastYear=2024-12-31
firstNextYear=2025-01-01
dateTimeLastMonth=2024-02-29T16:45
original=2024-02-15
~~~

**Phân tích:**

- Năm 2024 nhuận nên cuối tháng Hai là ngày 29.
- firstDayOfNextMonth chuyển đúng sang 01/03, không cần tự xác định số ngày của tháng.
- lastDayOfYear trả 31/12, còn firstDayOfNextYear trả 01/01/2025.
- Khi áp dụng lastDayOfMonth trên LocalDateTime, phần **16:45 được giữ**, chỉ các trường ngày thay đổi theo quy tắc.
- LocalDate ban đầu vẫn là 15/02 do immutable; việc bỏ kết quả của with sẽ không cập nhật date.

### So sánh với with(field, value)

Có trường hợp thao tác trực tiếp vẫn hợp lý:

~~~java
// Mảnh mã, LocalDate date đã có.
LocalDate first = date.withDayOfMonth(1);
LocalDate last = date.with(TemporalAdjusters.lastDayOfMonth());
~~~

first có thể viết gọn bằng withDayOfMonth(1), nhưng lastDayOfMonth giúp thể hiện ý định và tự tôn trọng độ dài tháng. Đừng viết withDayOfMonth(31) với mọi tháng, vì tháng ngắn sẽ phát sinh DateTimeException hoặc không hợp lệ.

## 6. next so với nextOrSame: sai một tuần vì chữ OrSame

Bốn factory điều chỉnh ngày trong tuần có một sự khác biệt rất quan trọng:

- **next(day)** luôn tìm ngày khớp **sau** ngày gốc. Nếu ngày gốc đã là thứ cần tìm, nó tiến **7 ngày**.
- **nextOrSame(day)** cho phép giữ nguyên ngày gốc nếu đã khớp; nếu chưa khớp, mới tiến về lần kế tiếp.
- **previous(day)** luôn tìm ngày khớp **trước** ngày gốc. Nếu đã khớp, nó lùi **7 ngày**.
- **previousOrSame(day)** cho phép giữ nguyên nếu khớp; nếu không thì lùi về lần trước.

Ví dụ từ thứ Sáu **17/05/2024**, tìm FRIDAY:

~~~text
next(FRIDAY)           -> 2024-05-24
nextOrSame(FRIDAY)     -> 2024-05-17
previous(FRIDAY)       -> 2024-05-10
previousOrSame(FRIDAY) -> 2024-05-17
~~~

Câu hỏi nghiệp vụ phải phân biệt “**thứ Sáu kế tiếp sau ngày này**” với “**thứ Sáu gần nhất không trước ngày này**”. Dùng nhầm sẽ làm lịch gửi báo cáo bị lùi một tuần hoặc thanh toán bị thực hiện muộn.

### DayOfWeek tự nó là một TemporalAdjuster, nhưng khác next

~~~java
// Mảnh mã.
LocalDate friday = LocalDate.of(2024, 5, 17);
LocalDate sameWeekMonday = friday.with(DayOfWeek.MONDAY);
LocalDate nextMonday = friday.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
~~~

sameWeekMonday là **13/05**, còn nextMonday là **20/05**. Lời gọi with(DayOfWeek.MONDAY) về bản chất đặt trường ngày trong tuần vào MONDAY trong cùng tuần ISO tương ứng, **không** tìm thứ Hai tiếp theo. Đọc đúng phương thức giúp tránh điều chỉnh sai hướng.

## 7. Ví dụ hoàn chỉnh 2 — điều chỉnh thứ trong tuần

Tạo file **WeekdayAdjustersDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import static java.time.DayOfWeek.*;

public class WeekdayAdjustersDemo {
    public static void main(String[] args) {
        LocalDate friday = LocalDate.of(2024, 5, 17);
        System.out.println("base=" + friday);
        System.out.println("nextFri=" + friday.with(TemporalAdjusters.next(FRIDAY)));
        System.out.println("nextOrSameFri="
                + friday.with(TemporalAdjusters.nextOrSame(FRIDAY)));
        System.out.println("previousFri="
                + friday.with(TemporalAdjusters.previous(FRIDAY)));
        System.out.println("previousOrSameFri="
                + friday.with(TemporalAdjusters.previousOrSame(FRIDAY)));
        System.out.println("nextMon=" + friday.with(TemporalAdjusters.next(MONDAY)));
        System.out.println("setMonday=" + friday.with(MONDAY));
        System.out.println("firstMondayMay="
                + friday.with(TemporalAdjusters.firstInMonth(MONDAY)));
        System.out.println("lastMondayMay="
                + friday.with(TemporalAdjusters.lastInMonth(MONDAY)));
    }
}
~~~

Chạy:

~~~text
javac --release 17 WeekdayAdjustersDemo.java
java WeekdayAdjustersDemo
~~~

Stdout:

~~~text
base=2024-05-17
nextFri=2024-05-24
nextOrSameFri=2024-05-17
previousFri=2024-05-10
previousOrSameFri=2024-05-17
nextMon=2024-05-20
setMonday=2024-05-13
firstMondayMay=2024-05-06
lastMondayMay=2024-05-27
~~~

**Ứng dụng:**

- Lịch họp **sau hôm nay**, không được chạy cùng ngày: next.
- Deadline vào thứ Sáu **hôm nay hoặc sau**, nếu hôm nay là thứ Sáu thì không dời: nextOrSame.
- Lấy một thứ trong **cùng tuần ISO**: dùng DayOfWeek trực tiếp nếu đó thật sự là ý nghĩa muốn biểu diễn.
- Thứ Hai đầu/cuối một tháng: firstInMonth/lastInMonth chứ không dùng next vì next phụ thuộc ngày xuất phát.

## 8. firstInMonth, lastInMonth và dayOfWeekInMonth

Nhiều quy định nghiệp vụ có dạng “thứ Ba thứ hai của tháng” hoặc “thứ Sáu cuối cùng của tháng”. TemporalAdjusters có ba công cụ chính:

- **firstInMonth(day)**: lần xuất hiện đầu tiên trong tháng của thứ đó.
- **lastInMonth(day)**: lần xuất hiện cuối cùng trong tháng của thứ đó.
- **dayOfWeekInMonth(ordinal, day)**: lần xuất hiện theo vị trí ordinal.

Với **dayOfWeekInMonth**:

| ordinal | Ý nghĩa cơ bản |
|---:|---|
| 1 | Lần thứ nhất kể từ đầu tháng |
| 2 | Lần thứ hai kể từ đầu tháng |
| 3 | Lần thứ ba kể từ đầu tháng |
| 4 | Lần thứ tư kể từ đầu tháng |
| -1 | Lần cuối cùng của thứ đó trong tháng |
| -2 | Lần áp chót |
| 0 | Trường hợp đặc biệt: lần cuối của thứ đó ở **tháng trước** |
| 5 hoặc một số dương lớn | Có thể **vượt sang tháng tiếp theo** nếu tháng không đủ lần xuất hiện |
| Số âm có độ lớn quá lớn | Có thể **lùi sang tháng trước** |

**Đặc biệt:** dayOfWeekInMonth không bắt buộc mọi kết quả nằm trong **tháng gốc**. JavaDoc cho phép ordinal 0 và ordinal vượt số lần xuất hiện; nó không phải một validator “ngày thứ N phải thuộc tháng hiện tại”.

Ví dụ tháng 05/2024 có bốn ngày thứ Ba: **07, 14, 21, 28**. Khi gọi dayOfWeekInMonth(5,TUESDAY), kết quả là **04/06/2024**, không phải exception. Nếu nghiệp vụ đòi “thứ Ba thứ năm *trong* tháng, nếu không có thì lỗi”, phải **kiểm tra tháng** sau khi điều chỉnh.

### firstInMonth và lastInMonth khác next

Từ ngày 15/05, next(TUESDAY) có thể là 21/05, nhưng firstInMonth(TUESDAY) là 07/05. firstInMonth không yêu cầu ngày trả về sau ngày gốc; nó tìm vị trí trong **tháng của ngày gốc**. Tên hàm phản ánh hệ quy chiếu được dùng.

## 9. Ví dụ hoàn chỉnh 3 — thứ N trong tháng

Tạo file **OrdinalWeekdayDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import static java.time.DayOfWeek.*;

public class OrdinalWeekdayDemo {
    public static void main(String[] args) {
        LocalDate base = LocalDate.of(2024, 5, 15);
        System.out.println("firstTue="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(1, TUESDAY)));
        System.out.println("secondTue="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(2, TUESDAY)));
        System.out.println("lastTue="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(-1, TUESDAY)));
        System.out.println("previousMonthTue="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(0, TUESDAY)));
        System.out.println("fifthTue="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(5, TUESDAY)));
        System.out.println("lastFri="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(-1, FRIDAY)));
        System.out.println("secondLastFri="
                + base.with(TemporalAdjusters.dayOfWeekInMonth(-2, FRIDAY)));
    }
}
~~~

Chạy:

~~~text
javac --release 17 OrdinalWeekdayDemo.java
java OrdinalWeekdayDemo
~~~

Stdout:

~~~text
firstTue=2024-05-07
secondTue=2024-05-14
lastTue=2024-05-28
previousMonthTue=2024-04-30
fifthTue=2024-06-04
lastFri=2024-05-31
secondLastFri=2024-05-24
~~~

Điểm dễ sai nhất là **ordinal=0** và **ordinal=5**. Theo API, cả hai là các phép tính có kết quả hợp lệ, nhưng có thể đi ra ngoài tháng gốc. Nếu người dùng chọn “lần thứ N **trong tháng này**”, phải bổ sung điều kiện:

~~~java
// Mảnh mã, tham số month, ordinal, weekday được xác định bởi nghiệp vụ.
LocalDate candidate = month.atDay(1).with(
        TemporalAdjusters.dayOfWeekInMonth(ordinal, weekday));
if (!YearMonth.from(candidate).equals(month)) {
    throw new IllegalArgumentException("Thứ N không nằm trong tháng");
}
~~~

Điều kiện này giúp chuyển quy tắc **toán học của adjuster** thành quy tắc nghiệp vụ **không được vượt tháng**.

## 10. TemporalAdjusters.ofDateAdjuster — mở rộng bằng UnaryOperator<LocalDate>

Các adjuster chuẩn không có sẵn quy tắc “bỏ thứ Bảy, Chủ nhật và các ngày nghỉ do doanh nghiệp chỉ định”. Để đóng gói một phép biến đổi ngày, dùng:

~~~java
// Mảnh mã:
TemporalAdjuster rule =
        TemporalAdjusters.ofDateAdjuster(date -> date.plusDays(1));
~~~

Factory nhận một **UnaryOperator<LocalDate>**, tức hàm nhận một LocalDate và trả một LocalDate. Nó dùng LocalDate làm miền logic, sau đó điều chỉnh temporal input thông qua cơ chế tương ứng. Vì vậy có thể thuận tiện áp dụng với LocalDate và LocalDateTime; phần thời gian trong ngày có thể được giữ khi chỉ sửa ngày.

### Xác định đúng ngữ nghĩa “ngày làm việc”

Cần quyết định:

- Tuần làm việc của công ty là thứ Hai–thứ Sáu hay lịch ca khác?
- Có ngày nghỉ theo quốc gia, tỉnh/thành phố, tổ chức hoặc nhóm nhân viên không?
- Một ngày nghỉ có thể thay đổi hoặc dời lịch không?
- **next business day** là ngày làm việc **sau** ngày hiện tại hay có thể là **chính ngày hiện tại**?
- Khi ngày gốc là thứ Sáu và thứ Hai nghỉ, hệ thống phải chọn thứ Ba hay giữ thứ Hai?
- Có thời gian cut-off theo giờ trong ngày, ví dụ đặt hàng sau 16:00 thì không xử lý ngay?
- Ngày làm việc theo múi giờ nào và có các ca qua nửa đêm không?

Không có một khái niệm **business day** duy nhất nằm trong core Java Time. TemporalAdjusters.ofDateAdjuster cho phép thực thi quy tắc **do ứng dụng định nghĩa**; bản thân JDK không cung cấp lịch ngày nghỉ của từng doanh nghiệp.

### Logic thuần, không đọc thời gian hệ thống ngầm

Một adjuster tốt nên tính ngày từ **date đầu vào và cấu hình immutable**. Nếu lambda tự gọi LocalDate.now() hoặc truy cập dữ liệu mutable không đồng bộ, test khó tái lập và quy tắc có thể thay đổi giữa hai lần gọi. Đưa Clock hoặc lịch nghỉ vào constructor của service/cấu hình tại ranh giới hệ thống, rồi dùng dữ liệu đó để tạo quy tắc rõ ràng.

## 11. Ví dụ hoàn chỉnh 4 — ngày làm việc tiếp theo với ngày nghỉ

Trong chương trình sau, **02/09/2024** được khai báo là ngày nghỉ **minh họa trong cấu hình**. Đây là dữ liệu đầu vào của ví dụ, không phải lời khẳng định mọi tổ chức đều nghỉ vào ngày đó.

Tạo file **NextBusinessDayDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.*;
import java.util.Set;

public class NextBusinessDayDemo {
    private static final Set<LocalDate> HOLIDAYS =
            Set.of(LocalDate.of(2024, 9, 2));

    private static boolean isNonWorkingDay(LocalDate date) {
        DayOfWeek day = date.getDayOfWeek();
        return day == DayOfWeek.SATURDAY
                || day == DayOfWeek.SUNDAY
                || HOLIDAYS.contains(date);
    }

    public static void main(String[] args) {
        TemporalAdjuster nextBusinessDay = TemporalAdjusters.ofDateAdjuster(
                date -> {
                    LocalDate candidate = date.plusDays(1);
                    while (isNonWorkingDay(candidate)) {
                        candidate = candidate.plusDays(1);
                    }
                    return candidate;
                });
        TemporalAdjuster businessDayOrSame = TemporalAdjusters.ofDateAdjuster(
                date -> {
                    LocalDate candidate = date;
                    while (isNonWorkingDay(candidate)) {
                        candidate = candidate.plusDays(1);
                    }
                    return candidate;
                });

        LocalDate friday = LocalDate.of(2024, 8, 30);
        LocalDate saturday = LocalDate.of(2024, 8, 31);
        LocalDate tuesday = LocalDate.of(2024, 9, 3);
        LocalDateTime deadline = friday.atTime(17, 30);

        System.out.println("friday.next=" + friday.with(nextBusinessDay));
        System.out.println("saturday.next=" + saturday.with(nextBusinessDay));
        System.out.println("friday.orSame=" + friday.with(businessDayOrSame));
        System.out.println("tuesday.orSame=" + tuesday.with(businessDayOrSame));
        System.out.println("deadline.next="
                + deadline.with(nextBusinessDay));
        System.out.println("original=" + friday);
    }
}
~~~

Chạy:

~~~text
javac --release 17 NextBusinessDayDemo.java
java NextBusinessDayDemo
~~~

Stdout:

~~~text
friday.next=2024-09-03
saturday.next=2024-09-03
friday.orSame=2024-08-30
tuesday.orSame=2024-09-03
deadline.next=2024-09-03T17:30
original=2024-08-30
~~~

**Diễn giải:**

1. Từ thứ Sáu 30/08, quy tắc strictly next thử thứ Bảy, bỏ thứ Bảy và Chủ nhật, bỏ ngày nghỉ được cấu hình 02/09, rồi lấy thứ Ba 03/09.
2. Từ thứ Bảy 31/08, kết quả strictly next cũng là 03/09.
3. OrSame giữ nguyên thứ Sáu nếu đó là ngày làm việc và không có trong tập ngày nghỉ.
4. OrSame cũng giữ 03/09 vì ngày đó là ngày làm việc.
5. LocalDateTime 17:30 vẫn là 17:30 sau khi đổi ngày qua adjuster. **Đổi ngày và đổi giờ là hai thao tác nghiệp vụ riêng**.
6. LocalDate đầu vào không bị sửa.

**Cảnh báo production:** Tập nghỉ trong ví dụ là **một Set cố định**, dùng để minh họa. Hệ thống thực phải tra lịch ngày nghỉ chính thức theo khu vực/thị trường và có chính sách với ngày nghỉ bù, lịch ca, ngày làm việc đặc biệt, timezone, dữ liệu bị thiếu, hiệu lực thay đổi và giới hạn vòng lặp. Không được mặc định thứ Bảy/Chủ nhật luôn là ngày nghỉ của mọi doanh nghiệp.

## 12. Tự triển khai interface TemporalAdjuster khi cần kiểm soát sâu hơn

TemporalAdjusters.ofDateAdjuster là lựa chọn tốt cho quy tắc đơn giản trên LocalDate. Trong trường hợp cần một class có tên miền nghiệp vụ, constructor nhận cấu hình và hợp đồng riêng, bạn có thể **implements TemporalAdjuster**:

~~~java
// Mảnh mã minh họa, cần import java.time.temporal.Temporal.
class MyAdjuster implements TemporalAdjuster {
    @Override
    public Temporal adjustInto(Temporal input) {
        // Trả Temporal cùng observable type, không sửa input.
        return input;
    }
}
~~~

Với điều chỉnh dựa trên ngày ISO, một cách triển khai là:

1. Lấy ngày qua **LocalDate.from(input)**.
2. Tính ngày mới bằng các phương thức LocalDate và TemporalAdjusters chuẩn.
3. Áp dụng ngày mới bằng **input.with(ChronoField.EPOCH_DAY, candidate.toEpochDay())**.
4. Trả kết quả đó; không mutate input.

Điều này bảo toàn phần thời gian trong ngày đối với những loại temporal có thể cập nhật EPOCH_DAY, chẳng hạn LocalDateTime; tuy nhiên **không phải mọi Temporal đều hỗ trợ EPOCH_DAY**. Nếu nhận LocalTime hoặc Instant trực tiếp, có thể xuất hiện DateTimeException/UnsupportedTemporalTypeException. Phải ghi rõ miền kiểu đầu vào của adjuster, hoặc cung cấp API chỉ nhận LocalDate nếu đó là domain thực.

### Observable type, tính bất biến và thread-safety

Một TemporalAdjuster phải trả object có **cùng observable type** với input theo contract. Trả LocalDate khi đầu vào là LocalDateTime sẽ vi phạm hợp đồng; trả input.with(EPOCH_DAY,...) thường giữ kiểu đó ở các loại hỗ trợ trường.

Các class mutable do ứng dụng tự tạo có thể là Temporal, nhưng adjuster vẫn phải tuân thủ contract **không sửa input**. Đừng lấy state của adjuster ra sửa trong các lần chạy; một adjuster có thể được chia sẻ giữa nhiều thread.

## 13. Ví dụ hoàn chỉnh 5 — class adjuster tìm ngày thứ Hai–thứ Sáu cuối tháng

Đây là ví dụ **last weekday of month**, chỉ loại thứ Bảy và Chủ nhật, **không tự tra ngày nghỉ lễ**. Nếu nghiệp vụ cần last *business* day với ngày nghỉ, phải cộng thêm lịch nghỉ vào quy tắc.

Tạo file **LastBusinessDayDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.*;

public class LastBusinessDayDemo {
    private static boolean weekend(LocalDate d) {
        return d.getDayOfWeek() == DayOfWeek.SATURDAY
                || d.getDayOfWeek() == DayOfWeek.SUNDAY;
    }

    static final class LastWeekdayOfMonth implements TemporalAdjuster {
        @Override
        public Temporal adjustInto(Temporal input) {
            LocalDate date = LocalDate.from(input);
            LocalDate candidate = date.with(TemporalAdjusters.lastDayOfMonth());
            while (weekend(candidate)) {
                candidate = candidate.minusDays(1);
            }
            return input.with(ChronoField.EPOCH_DAY, candidate.toEpochDay());
        }
    }

    public static void main(String[] args) {
        TemporalAdjuster adjuster = new LastWeekdayOfMonth();

        LocalDate march = LocalDate.of(2024, 3, 12);
        LocalDate april = LocalDate.of(2024, 4, 12);
        LocalDate feb = LocalDate.of(2024, 2, 12);
        LocalDateTime meeting = march.atTime(9, 45);

        System.out.println("march=" + march.with(adjuster));
        System.out.println("april=" + april.with(adjuster));
        System.out.println("leapFeb=" + feb.with(adjuster));
        System.out.println("meeting=" + meeting.with(adjuster));
    }
}
~~~

Chạy:

~~~text
javac --release 17 LastBusinessDayDemo.java
java LastBusinessDayDemo
~~~

Stdout:

~~~text
march=2024-03-29
april=2024-04-30
leapFeb=2024-02-29
meeting=2024-03-29T09:45
~~~

**Giải thích theo từng tháng:**

- Tháng 03/2024 kết thúc vào Chủ nhật 31/03, nên last weekday là thứ Sáu 29/03.
- Tháng 04/2024 kết thúc vào thứ Ba 30/04, nên không cần dịch lùi.
- Tháng 02/2024 kết thúc vào thứ Năm 29/02 do năm nhuận.
- LocalDateTime chuyển từ 12/03 09:45 thành 29/03 09:45, giữ phần giờ.

Đây là ví dụ tự triển khai **TemporalAdjuster.adjustInto**, trả kết quả với EPOCH_DAY trên chính Temporal đầu vào. Những loại Temporal không hỗ trợ field ngày bị loại khỏi phạm vi; không sử dụng class này trực tiếp trên Instant, LocalTime hoặc một chronology khác mà chưa xác nhận contract.

### Có cần tự viết class thay cho ofDateAdjuster không?

Không phải lúc nào cũng cần. Có thể dùng TemporalAdjusters.ofDateAdjuster cho một logic tương đương, nhất là khi chỉ điều chỉnh LocalDate. Class riêng hữu ích khi bạn muốn nêu rõ tên quy tắc, nhận CalendarPolicy/holidays qua constructor, kiểm tra input, viết unit test và DI. Chọn cách dễ hiểu nhất, không lập class chỉ để thay một lambda ngắn.

## 14. Điều chỉnh trên LocalDateTime và ZonedDateTime

Các adjuster như lastDayOfMonth hoặc next(MONDAY) chủ yếu điều chỉnh **trường ngày**, nên trên LocalDateTime chúng có thể giữ **giờ/phút/giây/nano**. Ví dụ:

~~~java
// Mảnh mã:
LocalDateTime local = LocalDateTime.of(2024, 2, 15, 9, 30);
LocalDateTime monthEnd = local.with(
        TemporalAdjusters.lastDayOfMonth());
// 2024-02-29T09:30
~~~

Nhưng trên ZonedDateTime, **giữ cùng số giờ địa phương** không nhất thiết giữ cùng khoảng thời gian thực. Khi đổi ngày qua đêm chuyển DST, offset có thể thay đổi và một LocalDateTime có thể **không tồn tại** hoặc **xuất hiện hai lần** theo quy tắc ZoneId.

### Vì sao một ngày lịch không nhất thiết là 24 giờ?

Paris có chuyển DST vào 31/03/2024:

~~~text
2024-03-30 12:00 +01:00   -> 2024-03-30T11:00:00Z
2024-03-31 12:00 +02:00   -> 2024-03-31T10:00:00Z

Đổi một ngày trên đồng hồ địa phương:
elapsed time = 23 giờ, không phải 24 giờ.
~~~

Nếu bạn gọi **ZonedDateTime.with(TemporalAdjusters.next(SUNDAY))** từ trưa thứ Bảy 30/03, nó chuyển sang trưa Chủ nhật 31/03, nhưng khoảng cách giữa hai Instant là **23 giờ**. Đây là phép điều chỉnh calendar, khác **instant.plus(Duration.ofHours(24))**.

### DST gap: giờ địa phương không tồn tại

Ở Europe/Paris ngày 31/03/2024, đồng hồ nhảy từ gần 02:00 lên 03:00. **2024-03-31T02:30** là LocalDateTime có các trường hợp lệ, nhưng không có offset hợp lệ trong ZoneId đó. Khi dùng atZone, Java mặc định điều chỉnh lên **03:30+02:00**. Với lịch hẹn quan trọng, đừng tự động dời mà không có chính sách; dùng ZoneRules.getValidOffsets và quyết định từ chối, hỏi người dùng hoặc dời theo quy định.

### DST overlap: giờ địa phương có hai lần

Khi đồng hồ lùi lại, một local time có thể gắn với hai offset/Instant. Một adjuster chuyển **ngày** không tự giải quyết mọi yêu cầu nghiệp vụ về lần đầu/lần sau của cuộc hẹn. Với overlap, có thể dùng earlier/later offset theo quy tắc, hoặc API strict để validate.

**Nguyên tắc tổng quát:** Nếu nghiệp vụ cần “ngày thứ Hai lúc 09:00 ở Paris”, hãy tính **LocalDate** theo calendar trước, kết hợp LocalTime rồi gắn ZoneId, có xử lý DST. Nếu nghiệp vụ cần “đúng 24 giờ nữa”, hãy dùng **Instant + Duration**.

## 15. Clock chỉ hỗ trợ chọn ngày hiện tại, adjuster không thay Clock

TemporalAdjusters cung cấp **logic chuyển ngày theo quy tắc**; nó không tự quyết định **hôm nay** là ngày nào trong múi giờ nào. Khi cần bắt đầu từ ngày hiện tại, hãy lấy ngày từ **Clock** và **ZoneId** được truyền tường minh:

~~~java
// Mảnh mã:
Clock fixed = Clock.fixed(
        Instant.parse("2024-03-30T10:00:00Z"),
        ZoneId.of("Europe/Paris"));
LocalDate today = LocalDate.now(fixed);
LocalDate nextMonday = today.with(
        TemporalAdjusters.next(DayOfWeek.MONDAY));
~~~

Clock.fixed giúp test deterministic, khác Clock.systemUTC chỉ chọn UTC nhưng vẫn theo thời gian thực. Khi chạy production, inject Clock và business ZoneId để không phụ thuộc timezone của máy chủ. Sau đó dùng adjuster trên LocalDate; việc lập lịch thực tế còn cần **giờ trong ngày**, **ZoneRules**, lịch nghỉ và quy tắc giao dịch.

## 16. Ví dụ hoàn chỉnh 6 — Clock, DST gap và lịch tuần

Tạo file **CalendarDstAndClockDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.TemporalAdjusters;

public class CalendarDstAndClockDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        Clock clock = Clock.fixed(
                Instant.parse("2024-03-30T10:00:00Z"), paris);
        LocalDate today = LocalDate.now(clock);
        LocalDate sunday = today.with(
                TemporalAdjusters.next(DayOfWeek.SUNDAY));
        LocalDate monday = today.with(
                TemporalAdjusters.next(DayOfWeek.MONDAY));

        LocalDateTime nonexistentLocal = sunday.atTime(2, 30);
        ZonedDateTime resolved = nonexistentLocal.atZone(paris);
        ZonedDateTime mondayMeeting = monday.atTime(9, 0).atZone(paris);

        ZonedDateTime saturdayNoon =
                today.atTime(12, 0).atZone(paris);
        ZonedDateTime sundayNoon = saturdayNoon.with(
                TemporalAdjusters.next(DayOfWeek.SUNDAY));

        System.out.println("today=" + today);
        System.out.println("nextSunday=" + sunday);
        System.out.println("gapOffsets="
                + paris.getRules().getValidOffsets(nonexistentLocal));
        System.out.println("gapResolved=" + resolved);
        System.out.println("nextMondayMeeting=" + mondayMeeting);
        System.out.println("nextMondayInstant=" + mondayMeeting.toInstant());
        System.out.println("calendarDayHours="
                + Duration.between(
                        saturdayNoon.toInstant(),
                        sundayNoon.toInstant()).toHours());
    }
}
~~~

Chạy:

~~~text
javac --release 17 CalendarDstAndClockDemo.java
java CalendarDstAndClockDemo
~~~

Stdout:

~~~text
today=2024-03-30
nextSunday=2024-03-31
gapOffsets=[]
gapResolved=2024-03-31T03:30+02:00[Europe/Paris]
nextMondayMeeting=2024-04-01T09:00+02:00[Europe/Paris]
nextMondayInstant=2024-04-01T07:00:00Z
calendarDayHours=23
~~~

**Đọc kết quả:**

1. Clock.fixed đặt thời điểm 30/03/2024 theo zone Paris, nên LocalDate.now(clock) là 30/03/2024.
2. TemporalAdjusters.next(SUNDAY) chọn 31/03/2024.
3. 02:30 của ngày đó nằm trong DST gap, getValidOffsets rỗng; atZone mặc định dịch sang 03:30.
4. Thứ Hai tiếp theo là 01/04, cuộc hẹn 09:00 Paris có Instant **07:00Z**.
5. Trưa thứ Bảy sang trưa Chủ nhật là một ngày theo calendar nhưng chỉ **23 giờ thực**.

**Chú ý:** Demo dùng quy tắc lịch sử Europe/Paris năm 2024; luật DST của tương lai có thể thay đổi khi tzdb/JDK được cập nhật. Không hardcode offset +01/+02 cho mọi năm.

## 17. Không phải Temporal nào cũng hỗ trợ adjuster ngày lịch

Tên interface **Temporal** không cam kết mọi field đều tồn tại. Ví dụ:

- **LocalDate** có các trường ngày, tháng, năm; phù hợp lastDayOfMonth.
- **LocalDateTime** có trường ngày và giờ; lastDayOfMonth thay ngày và giữ giờ.
- **ZonedDateTime** có ngày/giờ địa phương cùng offset/zone; khi điều chỉnh có thể vướng DST.
- **LocalTime** chỉ có giờ/phút/giây; không có DAY_OF_MONTH.
- **Instant** là mốc timeline; không chứa ngày trong tháng theo một khu vực để áp dụng lastDayOfMonth một cách trực tiếp.

Một số adjuster sẽ ném DateTimeException hoặc UnsupportedTemporalTypeException khi temporal thiếu trường nó cần. **UnsupportedTemporalTypeException** là một dạng DateTimeException.

Nếu bắt đầu với Instant và muốn cuối tháng theo một thị trường:

~~~java
// Mảnh mã:
Instant event = Instant.parse("2024-02-15T10:00:00Z");
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant result = event.atZone(businessZone)
        .with(TemporalAdjusters.lastDayOfMonth())
        .toInstant();
~~~

Đây là việc điều chỉnh **ngày địa phương** theo businessZone rồi chuyển lại thành Instant. Nó **khác** đổi Instant thành cuối tháng bằng một phép cộng số giây cố định. Nếu cần deadline cuối ngày, ngoài date adjuster còn phải chọn **giờ cutoff** và giải quyết DST theo chính sách.

### Không được cast kết quả bừa

Phương thức interface **TemporalAdjuster.adjustInto** trả Temporal; một adjuster đúng phải trả **cùng observable type** với input. Trên class tự triển khai, không cast LocalDate sang LocalDateTime chỉ vì nghĩ “có ngày là đủ”. Hãy áp dụng điều chỉnh qua input.with(...), trả đúng kiểu, và test những temporal mà adjuster công bố hỗ trợ.

## 18. Ví dụ hoàn chỉnh 7 — kiểu temporal được hỗ trợ

Tạo file **TypeSafetyDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.*;

public class TypeSafetyDemo {
    public static void main(String[] args) {
        LocalDateTime input = LocalDateTime.of(2024, 2, 15, 14, 25);
        TemporalAdjuster monthEnd = TemporalAdjusters.lastDayOfMonth();

        System.out.println("dateTime=" + input.with(monthEnd));
        System.out.println("sameLocalTime="
                + input.toLocalTime().equals(input.with(monthEnd).toLocalTime()));

        try {
            LocalTime.of(10, 0).with(monthEnd);
        } catch (DateTimeException expected) {
            System.out.println("localTime=DateTimeException");
        }

        Instant instant = Instant.parse("2024-02-15T10:00:00Z");
        ZonedDateTime utc = instant.atZone(ZoneOffset.UTC);
        System.out.println("instantAdjusted="
                + utc.with(monthEnd).toInstant());
        System.out.println("original=" + instant);
    }
}
~~~

Chạy:

~~~text
javac --release 17 TypeSafetyDemo.java
java TypeSafetyDemo
~~~

Stdout:

~~~text
dateTime=2024-02-29T14:25
sameLocalTime=true
localTime=DateTimeException
instantAdjusted=2024-02-29T10:00:00Z
original=2024-02-15T10:00:00Z
~~~

**Giải thích:**

- Với LocalDateTime, date được điều chỉnh sang 29/02 nhưng LocalTime 14:25 giữ nguyên.
- Với LocalTime, field ngày không được hỗ trợ và một DateTimeException xuất hiện.
- Với Instant, ví dụ không áp dụng lastDayOfMonth trực tiếp. Nó **chuyển sang ZonedDateTime UTC**, điều chỉnh ngày rồi chuyển lại thành Instant.
- Instant ban đầu không đổi, phù hợp đặc tính immutable.

## 19. Chọn API theo từng tình huống thực tế

| Yêu cầu | Cách tiếp cận |
|---|---|
| Ngày cuối tháng của một LocalDate | date.with(lastDayOfMonth()) |
| Bắt đầu kỳ báo cáo tháng sau | date.with(firstDayOfNextMonth()) |
| Thứ Hai sau ngày hiện tại | date.with(next(MONDAY)) |
| Thứ Hai hôm nay hoặc sau hôm nay | date.with(nextOrSame(MONDAY)) |
| Thứ Sáu cuối tháng | date.with(lastInMonth(FRIDAY)) |
| Thứ Ba thứ hai của tháng | date.with(dayOfWeekInMonth(2,TUESDAY)) |
| Thứ N bắt buộc nằm trong tháng | dayOfWeekInMonth rồi **validate YearMonth** |
| Ngày làm việc tiếp theo | Adjuster tùy chỉnh theo lịch làm việc và ngày nghỉ |
| Cuối tháng trên LocalDateTime | with(lastDayOfMonth()), giữ LocalTime |
| Cuối tháng theo ZoneId thị trường từ Instant | atZone -> điều chỉnh date/time -> toInstant |
| Deadline chính xác 48 giờ sau | Instant.plus(Duration.ofHours(48)), **không dùng calendar adjuster** |
| Lịch hẹn lặp mỗi tuần ở vùng có DST | Tính LocalDate theo rule -> chọn LocalTime -> resolve ZoneRules |
| Unit test lịch phát sinh từ hôm nay | Inject Clock.fixed và business ZoneId |

### Một ngày lịch có thể chứa nhiều mốc deadline

“Đến **cuối tháng**” còn chưa xác định một Instant duy nhất nếu chưa chỉ rõ:

- Cuối tháng theo **múi giờ nào**?
- Deadline là **đến hết ngày cuối** hay **đầu ngày đầu tháng sau**?
- Hệ thống xử lý theo kiểu **inclusive** hay **exclusive**?
- Có giờ cutoff và lịch làm việc/banking holiday không?

Đối với truy vấn theo khoảng thời gian, thường thuận tiện dùng **half-open interval**: từ đầu ngày đầu tháng (inclusive) đến đầu ngày đầu tháng sau (exclusive), tính ở business ZoneId rồi chuyển sang Instant. Đừng lấy “23:59:59.999” làm cuối tháng nếu database lưu nanosecond, vì có thể sót dữ liệu nằm sau .999 trong giây cuối.

## 20. Kết hợp TemporalAdjuster với YearMonth và lịch tháng

**YearMonth** phù hợp biểu diễn một kỳ năm-tháng như 2024-02 mà chưa gắn ngày. Khi cần ngày cuối tháng, nó cung cấp **atEndOfMonth()** rất rõ nghĩa:

~~~java
// Mảnh mã:
YearMonth period = YearMonth.of(2024, 2);
LocalDate end = period.atEndOfMonth();
// 2024-02-29
~~~

Nếu đang có LocalDate, dùng date.with(lastDayOfMonth()) dễ đọc. Nếu dữ liệu nghiệp vụ chỉ có **tháng** không có ngày, bắt đầu từ YearMonth và chỉ tạo LocalDate khi cần ranh giới tránh phát sinh một ngày giả.

Bởi vì TemporalAdjuster nhận Temporal, không nên gọi with(adjuster) trên mọi kiểu TemporalAccessor không hỗ trợ phép điều chỉnh. Chọn API có **trường dữ liệu phù hợp** thay vì ép kiểu.

### Tính số ngày trong tháng và ngày nhuận

~~~java
// Mảnh mã:
LocalDate date = LocalDate.of(2024, 2, 15);
int length = date.lengthOfMonth();    // 29
LocalDate end = date.with(TemporalAdjusters.lastDayOfMonth());
~~~

lastDayOfMonth đã giải quyết năm nhuận theo chronology. Không cần ghi điều kiện if (year % 4...) tự phát, bởi quy tắc năm nhuận đầy đủ và phạm vi chronology đã được Java Time hỗ trợ.

## 21. Các lỗi phổ biến và cách khắc phục

### 21.1. Tưởng nextOrSame giống next

Nếu hôm nay đã đúng DayOfWeek mong muốn, nextOrSame trả **hôm nay**, còn next tiến **7 ngày**. Xác định rõ từ “sau” hay “hôm nay hoặc sau”.

### 21.2. Nhầm with(DayOfWeek.MONDAY) với next(MONDAY)

with(MONDAY) đặt thứ của **tuần hiện tại**, có thể lùi về quá khứ; next(MONDAY) tìm thứ Hai sau ngày gốc.

### 21.3. Cho rằng ordinal=5 luôn nằm trong tháng

dayOfWeekInMonth(5,TUESDAY) có thể vượt sang tháng sau. Validate YearMonth nếu domain giới hạn trong tháng.

### 21.4. Cho rằng ordinal=0 là ngày hợp lệ trong tháng

JavaDoc cho phép ordinal=0 và trả lần xuất hiện tương ứng **trước tháng gốc**, không phải lần thứ 0 trong cùng tháng.

### 21.5. Dùng cộng 30 ngày để tìm ngày đầu tháng sau

Tháng dài 28, 29, 30 hoặc 31 ngày. Dùng firstDayOfNextMonth hoặc YearMonth.plusMonths(1).atDay(1) tùy kiểu đầu vào.

### 21.6. Dùng lastDayOfMonth để xác định hạn hết tháng bằng Instant

lastDayOfMonth chỉ chọn **ngày**. Còn phải xác định giờ cutoff, ZoneId và quy ước inclusive/exclusive. Đừng mặc nhiên coi 23:59:59.999 là mốc cuối cho DB có độ chính xác nano.

### 21.7. Dùng business-day adjuster nhưng không có lịch nghỉ

Bỏ thứ Bảy/Chủ nhật mới chỉ là weekend adjuster. Nghỉ lễ phụ thuộc quốc gia/tổ chức/lịch bù; phải thiết kế nguồn cấu hình đúng.

### 21.8. Quên phân biệt strictly next với or same trong business day

Nếu hôm nay đã là ngày làm việc, “ngày làm việc sau hôm nay” khác “ngày làm việc hôm nay hoặc sau”. Một chữ orSame ảnh hưởng SLA và deadline.

### 21.9. Tính ngày từ múi giờ mặc định của server

LocalDate.now() dùng default zone. Server có thể ở UTC, người dùng ở Việt Nam hoặc Paris. Dùng LocalDate.now(clock) với Clock chứa ZoneId của nghiệp vụ.

### 21.10. Điều chỉnh ZonedDateTime nhưng giả sử mọi ngày dài 24 giờ

Qua DST, ngày lịch có thể dài 23 hoặc 25 giờ thực. Dùng Instant/Duration để đo khoảng thời gian tuyệt đối, calendar rules để chọn ngày.

### 21.11. Coi LocalDateTime hợp lệ là lịch hẹn luôn có Instant

Vào DST gap, một local time có thể không tồn tại; overlap có thể cho hai Instant. Kiểm tra ZoneRules và chính sách resolver khi cần lịch chính xác.

### 21.12. Dùng calendar adjuster trực tiếp trên Instant hoặc LocalTime

Instant không lưu trường ngày theo zone; LocalTime không có ngày. Chuyển sang LocalDate/ZonedDateTime phù hợp trước khi dùng adjuster.

### 21.13. Custom adjuster thay đổi input hoặc trả sai observable type

adjustInto phải không mutate input và trả Temporal cùng observable type; việc trả LocalDate từ LocalDateTime là sai contract.

### 21.14. Đặt mutable state trong adjuster dùng chung

Adjuster có thể được gọi đồng thời, cần thread-safe. Dùng state immutable, lịch nghỉ read-only hoặc snapshot theo version, không có biến đếm chia sẻ thiếu synchronization.

### 21.15. Viết logic vòng lặp không có giới hạn với calendar dữ liệu lỗi

Nếu cấu hình “không có ngày làm việc nào” hoặc lịch nghỉ không hữu hạn, vòng lặp tìm ngày tiếp theo có thể chạy vô hạn hoặc vượt phạm vi. Kiểm tra cấu hình và đặt giới hạn nghiệp vụ khi nguồn có thể đánh dấu mọi ngày là ngày nghỉ.

### 21.16. Thêm side effect không cần thiết trong adjuster

Adjuster nên là phép biến đổi có kết quả dự đoán được. Tránh gửi email, update database hay gọi mạng trong adjustInto; tách tính lịch khỏi tác vụ I/O để dễ test và tránh lặp side effect khi ứng dụng gọi lại.

### 21.17. Quên rằng thời điểm tháng sau có thể ở năm mới

firstDayOfNextMonth từ tháng 12 phải sang **01/01 năm sau**, không được đặt month=13 hoặc tự tăng day không kiểm soát.

### 21.18. Giả định chronology nào cũng là ISO mà không kiểm tra

TemporalAdjuster có thể nhận temporal thuộc chronology khác. Các adjuster chuẩn thường được thiết kế cho nhiều lịch, nhưng adjuster tự viết dùng **LocalDate.from** đang giả định một phép chiếu ISO; nếu hỗ trợ lịch khác là yêu cầu, cần document và test riêng.

## 22. Hướng dẫn thiết kế adjuster tự viết chất lượng

1. **Đặt tên quy tắc chính xác:** NextBusinessDay khác BusinessDayOrSame; LastWeekdayOfMonth khác LastBusinessDayOfMonth nếu chưa xét ngày nghỉ.
2. **Khai báo miền đầu vào:** Chỉ LocalDate hay cả LocalDateTime/ZonedDateTime? Có chronology ngoài ISO không?
3. **Định nghĩa tính bao hàm:** Ngày gốc có được phép là kết quả không?
4. **Xác định quy tắc lịch:** Những ngày nghỉ nào? Nguồn chính thức? Khi cấu hình thay đổi thì tính lại hay giữ lịch đã chốt?
5. **Xử lý biên:** Năm nhuận, 28/29/30/31 ngày, cuối năm, DST gap/overlap, ngày không làm việc liên tiếp.
6. **Giữ immutable và thread-safe:** Tránh shared mutable state; trả temporal mới, không sửa input.
7. **Test tính chất invariant:** Kết quả đúng thứ trong tuần, thỏa policy, không lùi khi cần “next”, nằm trong tháng nếu domain yêu cầu.
8. **Kiểm soát exception:** Nếu input thiếu field hoặc vượt phạm vi, để/biến đổi DateTimeException theo contract, đừng âm thầm đổi ngày sai.
9. **Không âm thầm lấy Clock.systemDefaultZone:** Nhận Clock và ZoneId qua phụ thuộc rõ khi cần “hôm nay”.
10. **Phân biệt lập lịch và thực thi:** Adjuster tính ngày; scheduler/transaction xử lý công việc thật, có retry/idempotency tương ứng.

### Một số bất biến (invariants) nên test

Với quy tắc next(MONDAY), hãy kiểm tra:

~~~text
result.getDayOfWeek() == MONDAY
result.isAfter(input)
1 <= DAYS.between(input, result) <= 7
~~~

Với nextOrSame(MONDAY), thay isAfter thành **không trước** (input bằng result là hợp lệ); khoảng chênh có thể từ 0 tới 6 ngày. Với lastDayOfMonth, result có cùng **YearMonth** với input, và result.getDayOfMonth() == result.lengthOfMonth() trong ISO.

Với last weekday of month, kết quả phải nằm trong tháng gốc, là MONDAY..FRIDAY, và mọi ngày sau nó cho tới cuối tháng phải là thứ Bảy/Chủ nhật. Với business day có holiday, invariant còn phải yêu cầu ngày trả về không nằm trong tập nghỉ.

## 23. Bài tập tự kiểm tra

**Câu 1.** TemporalAdjuster và TemporalAdjusters khác nhau ở đâu?

*Đáp án:* TemporalAdjuster là interface chiến lược có adjustInto; TemporalAdjusters là utility class cung cấp các factory trả adjuster.

**Câu 2.** Nên dùng temporal.with(adjuster) hay adjuster.adjustInto(temporal)?

*Đáp án:* Hai cách tương đương về ý nghĩa; JavaDoc khuyến nghị with vì dễ đọc hơn.

**Câu 3.** Từ 15/02/2024, lastDayOfMonth trả ngày nào?

*Đáp án:* 29/02/2024 vì năm nhuận.

**Câu 4.** Hôm nay là thứ Sáu, next(FRIDAY) có trả hôm nay không?

*Đáp án:* Không. Nó trả thứ Sáu sau 7 ngày; nextOrSame mới được giữ hôm nay.

**Câu 5.** Tại sao friday.with(DayOfWeek.MONDAY) khác friday.with(next(MONDAY))?

*Đáp án:* Cách đầu đặt thứ Hai trong cùng tuần ISO, có thể lùi; cách sau tìm thứ Hai tiếp theo sau ngày gốc.

**Câu 6.** dayOfWeekInMonth(5,TUESDAY) có thể trả một ngày tháng sau không?

*Đáp án:* Có. JavaDoc cho phép ordinal vượt số lần xuất hiện trong tháng; phải tự validate nếu domain không cho phép.

**Câu 7.** ordinal=0 có ý nghĩa gì?

*Đáp án:* Nó chỉ lần xuất hiện tương ứng ngay **trước đầu tháng**, chẳng hạn thứ Ba cuối tháng trước.

**Câu 8.** ofDateAdjuster nhận hàm kiểu gì?

*Đáp án:* UnaryOperator<LocalDate> nhận LocalDate và trả LocalDate.

**Câu 9.** Vì sao LocalTime.with(lastDayOfMonth()) không phù hợp?

*Đáp án:* LocalTime không chứa trường ngày trong tháng; có thể ném DateTimeException.

**Câu 10.** Có nên dùng Instant.with(lastDayOfMonth()) để lấy ngày cuối tháng theo Việt Nam?

*Đáp án:* Không trực tiếp. Cần đổi Instant sang ZonedDateTime với ZoneId nghiệp vụ, điều chỉnh ngày rồi quyết định giờ cutoff và chuyển về Instant.

**Câu 11.** Chuyển ZonedDateTime từ trưa 30/03 sang trưa 31/03/2024 ở Paris có luôn đúng 24 giờ không?

*Đáp án:* Không, năm 2024 là 23 giờ do DST.

**Câu 12.** Vì sao một Set nghỉ lễ bất biến giúp adjuster dễ test?

*Đáp án:* Logic chỉ phụ thuộc input và cấu hình đã biết; tránh race, thay đổi ngoài ý muốn và kết quả khác nhau giữa lần gọi.

**Câu 13.** firstInMonth(MONDAY) và next(MONDAY) khác nhau như thế nào?

*Đáp án:* firstInMonth lấy thứ Hai đầu **tháng của input** (có thể trước input); next lấy thứ Hai **sau input**.

**Câu 14.** Nếu người dùng yêu cầu thứ N phải nằm trong chính tháng, cần kiểm tra gì?

*Đáp án:* Sau dayOfWeekInMonth, so YearMonth của kết quả với YearMonth của input; nếu khác thì xử lý theo chính sách.

**Câu 15.** TemporalAdjuster có được thay đổi input mutable không?

*Đáp án:* Không, hợp đồng yêu cầu không thay đổi input và trả kết quả cùng observable type; adjuster còn phải thread-safe khi gọi đồng thời.

## 24. Checklist trước khi đưa vào production

- Đã xác định “next” hay “next or same” theo nghiệp vụ?
- Đã tách **điều chỉnh ngày lịch** khỏi **cộng thời lượng tuyệt đối**?
- Đã chọn đúng lastDayOfMonth, firstDayOfNextMonth, firstInMonth, lastInMonth?
- Đã xử lý ordinal 0/âm/vượt tháng nếu dùng dayOfWeekInMonth?
- Custom adjuster có trả Temporal cùng observable type và không mutate input?
- Các Temporal được hỗ trợ có đầy đủ field ngày cần thiết?
- Có cấu hình weekend/holiday/cutoff đúng thị trường, không hardcode giả định toàn cầu?
- Nếu lịch lặp liên quan DST, có validate gap/overlap và chọn ZoneId thực tế?
- Clock có được truyền tường minh cho logic “hôm nay” và kiểm thử Clock.fixed?
- Có test tháng Hai năm nhuận, tháng 30/31 ngày, cuối năm, ngày nghỉ liên tiếp?
- Nếu cần snapshot deadline cuối tháng, có chọn ranh giới [start,nextStart) và precision phù hợp?
- Có tài liệu ghi rõ kết quả inclusive/exclusive và hành vi khi không tìm thấy ngày hợp lệ?

## Tài liệu Oracle JavaDoc còn được duy trì

- Java SE 25 — **TemporalAdjuster**, hợp đồng adjustInto, same observable type và thread safety: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalAdjuster.html
- Java SE 25 — **TemporalAdjusters**, tất cả factory và xử lý ordinal của dayOfWeekInMonth: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalAdjusters.html
- Java SE 25 — **Temporal**, phương thức with(adjuster): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/Temporal.html
- Java SE 25 — **ChronoField**, trong đó có EPOCH_DAY: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoField.html
- Java SE 25 — **DayOfWeek**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/DayOfWeek.html
- Java SE 25 — **LocalDate**, cộng/trừ ngày và YearMonth: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Java SE 25 — **YearMonth**, atEndOfMonth: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/YearMonth.html
- Java SE 25 — **ZonedDateTime**, ZoneRules và DST: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- Java SE 25 — **Clock**, kiểm thử thời gian: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html

**Kết luận:** TemporalAdjuster là cách đóng gói **quy tắc điều chỉnh** một Temporal, còn TemporalAdjusters cung cấp các quy tắc chuẩn cho đầu/cuối tháng, đầu/cuối năm, thứ trong tuần và thứ N của tháng. Dùng temporal.with(adjuster) để diễn đạt ý định; khi tự viết, bảo đảm đúng observable type, immutable input và thread-safety. Hãy tính lịch bằng LocalDate/ZoneId/Clock phù hợp, không nhầm điều chỉnh calendar với Duration, và kiểm tra rõ các trường hợp ordinal vượt tháng, ngày nghỉ cũng như DST.
