# Cộng trừ ngày, tuần, tháng và năm bằng LocalDate trong Java

`LocalDate` trong gói `java.time` đại diện cho một **ngày lịch ISO-8601** gồm năm, tháng, ngày, chẳng hạn `2024-02-29`. Nó phù hợp để xử lý hạn nộp, ngày hẹn, ngày kỷ niệm, kỳ thanh toán hoặc ngày ghi nhận giao dịch. Java cung cấp các phép cộng trừ trực tiếp, không cần quy đổi ngày lịch thành mili giây.

**Ý chính:** Cộng/trừ **ngày và tuần** đi theo số ngày lịch; cộng/trừ **tháng và năm** phải xét ngày có tồn tại trong tháng/năm đích hay không. Các phương thức luôn trả về `LocalDate` mới vì lớp này **bất biến**. Những trường hợp cuối tháng và năm nhuận cần được hiểu kỹ, nhất là khi tính các kỳ lặp.

## 1. LocalDate biểu diễn điều gì?

Ví dụ:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
~~~

Đây là **đoạn mã minh họa**, cần import `java.time.LocalDate` và đặt vào class/phương thức phù hợp. Giá trị chứa ngày 29/02/2024 nhưng **không chứa giờ, offset hay múi giờ**. Một ngày lịch không phải một `Instant` duy nhất trên dòng thời gian.

Những phép cộng trừ dưới đây mang ý nghĩa **lịch**, theo quy tắc ISO:

| Đơn vị | Cộng | Trừ | Ý nghĩa |
|---|---|---|---|
| Ngày | `plusDays(n)` | `minusDays(n)` | Tiến hoặc lùi `n` ngày lịch. |
| Tuần | `plusWeeks(n)` | `minusWeeks(n)` | Tiến hoặc lùi `7 × n` ngày lịch. |
| Tháng | `plusMonths(n)` | `minusMonths(n)` | Đổi tháng/năm, điều chỉnh ngày khi tháng đích ngắn. |
| Năm | `plusYears(n)` | `minusYears(n)` | Đổi năm, điều chỉnh ngày 29/02 nếu cần. |

Mỗi tham số `n` có kiểu `long`. `plusDays(0)` giữ nguyên giá trị ngày; có thể truyền số âm như `plusDays(-3)` để lùi ba ngày (tương đương `minusDays(3)` trong phạm vi hợp lệ). Khi diễn đạt ý định, nên dùng `plus` cho “sau” và `minus` cho “trước”.

Không tự cho rằng `LocalDate.plusDays(1)` đồng nghĩa “đúng 24 giờ thực” sau một thời điểm: độ dài khoảng từ đầu hai ngày lịch liên tiếp trong một số vùng có chuyển đổi DST có thể khác 24 giờ. Với yêu cầu cộng một thời lượng tuyệt đối, xem `Instant`/`Duration` sau khi xác định mốc thời gian có vùng.

## 2. Cộng và trừ ngày: tự đi qua ranh giới lịch

`plusDays` và `minusDays` tự xử lý số ngày mỗi tháng, năm nhuận và đổi năm:

| Biểu thức | Kết quả |
|---|---|
| `LocalDate.of(2024, 2, 28).plusDays(1)` | `2024-02-29` |
| `LocalDate.of(2024, 2, 29).plusDays(1)` | `2024-03-01` |
| `LocalDate.of(2023, 2, 28).plusDays(1)` | `2023-03-01` |
| `LocalDate.of(2024, 1, 1).minusDays(1)` | `2023-12-31` |
| `LocalDate.of(2024, 12, 31).plusDays(1)` | `2025-01-01` |

Không cần tự viết câu lệnh “nếu tháng 2 thì cộng ngày theo 28 hoặc 29”. `LocalDate` dùng hệ lịch ISO và biết độ dài từng tháng.

**Phân biệt số ngày đã cộng với cách đếm bao gồm hai đầu.** Ví dụ từ `2024-05-01` cộng 5 ngày sẽ tới `2024-05-06`; nhưng nếu người dùng gọi 01/05 là “ngày thứ nhất” thì “ngày thứ năm” là 05/05. Đây là lựa chọn nghiệp vụ, không phải khác biệt cú pháp.

Các khoảng thời gian lịch thường nên biểu diễn dạng **nửa mở** `[from, until)` để ranh giới nối tiếp không trùng lặp. Nếu bắt đầu ngày 01/05 và kết thúc trước ngày 06/05 thì có đúng năm ngày lịch.

## 3. Cộng và trừ tuần: bảy ngày lịch, không phải bảy ngày làm việc

Một tuần trong phép toán của `LocalDate` là bảy ngày:

~~~text
2024-05-15 + 1 tuần = 2024-05-22
2024-05-15 - 2 tuần = 2024-05-01
2024-12-29 + 1 tuần = 2025-01-05
~~~

`plusWeeks(1)` giữ nguyên thứ trong tuần. Nếu ban đầu là thứ Tư thì kết quả là thứ Tư tuần sau, **không tự đưa tới thứ Hai đầu tuần**. Để tìm thứ Hai gần nhất không nằm sau ngày đã cho, dùng `TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY)`.

Một tuần cũng không phải “5 ngày làm việc”. Cuối tuần và ngày nghỉ lễ phải được tính theo lịch tổ chức và khu vực; `LocalDate` không tự biết hệ thống ngày nghỉ.

## 4. Cộng và trừ tháng: quy tắc ngày cuối tháng

Các tháng có 28, 29, 30 hoặc 31 ngày. Khi gọi `plusMonths(n)` hoặc `minusMonths(n)`, Java:

1. Tính **năm và tháng đích** sau khi dịch tháng.
2. Giữ **số ngày trong tháng** của ngày ban đầu nếu tháng đích có ngày đó.
3. Nếu tháng đích không có số ngày đó, chọn **ngày hợp lệ cuối cùng** của tháng đích.

Ví dụ:

| Ngày ban đầu | Phép toán | Kết quả | Giải thích |
|---|---|---|---|
| `2023-01-31` | `plusMonths(1)` | `2023-02-28` | Tháng 2/2023 có 28 ngày. |
| `2024-01-31` | `plusMonths(1)` | `2024-02-29` | Tháng 2/2024 có 29 ngày. |
| `2024-03-31` | `minusMonths(1)` | `2024-02-29` | Lùi một tháng vào tháng 2 năm nhuận. |
| `2024-05-31` | `plusMonths(1)` | `2024-06-30` | Tháng 6 chỉ có 30 ngày. |
| `2024-12-31` | `plusMonths(2)` | `2025-02-28` | Đi qua năm mới và co ngày. |
| `2024-08-30` | `minusMonths(6)` | `2024-02-29` | Ngày 30 không tồn tại trong tháng đích. |

Về mặt ý tưởng, một lần gọi `plusMonths(n)` thực hiện:

~~~text
targetYearMonth = yearMonth ban đầu + n tháng
targetDay       = min(originalDay, lengthOfMonth(targetYearMonth))
result          = ngày targetDay trong targetYearMonth
~~~

Quy tắc **co về cuối tháng** này áp dụng cho phép cộng/trừ tháng, không phải mọi phương thức sửa ngày. Chẳng hạn `LocalDate.of(2023, 2, 1).withDayOfMonth(31)` sẽ ném `DateTimeException` vì giá trị 31/02 không hợp lệ.

**Không thay `plusMonths(1)` bằng `plusDays(30)`:** tháng 1 có 31 ngày, tháng 2 có 28/29 và những tháng khác có 30/31 ngày. Hai phép toán thể hiện hai yêu cầu khác nhau.

## 5. Cộng và trừ năm: chú ý ngày 29/02

`plusYears(n)` và `minusYears(n)` cố giữ tháng và ngày trong năm mới. Nếu không tồn tại thì áp dụng quy tắc co về cuối tháng, điển hình là ngày nhuận:

~~~text
2024-02-29 + 1 năm = 2025-02-28
2024-02-29 - 1 năm = 2023-02-28
2024-02-29 + 4 năm = 2028-02-29
2024-06-15 + 1 năm = 2025-06-15
~~~

Trong lịch ISO/Gregory mở rộng, năm nhuận chia hết cho 4, ngoại trừ năm chia hết cho 100 mà không chia hết cho 400. Vì vậy 2000 là năm nhuận, 1900 và 2100 không nhuận.

Có thể dùng `date.isLeapYear()`, `date.lengthOfMonth()`, `date.lengthOfYear()` để xác định năm nhuận và số ngày phù hợp. “Một năm lịch” không luôn là 365 ngày và “một tháng lịch” không luôn là 30 ngày.

**Quy tắc kỷ niệm 29/02 là chính sách nghiệp vụ.** Java chọn `28/02` khi cộng một năm vào 29/02 của năm nhuận, nhưng hợp đồng/tổ chức có thể chọn 01/03 cho năm không nhuận. Khi đó phải mã hóa chính sách riêng.

## 6. Ví dụ Java 17+ độc lập: cộng trừ mọi đơn vị

Lưu tệp `LocalDateMathDemo.java`:

~~~java
import java.time.LocalDate;

public class LocalDateMathDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2023, 1, 31);

        System.out.println("Original: " + start);
        System.out.println("+1 day:   " + start.plusDays(1));
        System.out.println("-2 days:  " + start.minusDays(2));
        System.out.println("+1 week:  " + start.plusWeeks(1));
        System.out.println("-2 weeks: " + start.minusWeeks(2));
        System.out.println("+1 month: " + start.plusMonths(1));
        System.out.println("-1 month: " + start.minusMonths(1));
        System.out.println("+1 year:  " + start.plusYears(1));
        System.out.println("-1 year:  " + start.minusYears(1));
        System.out.println("Still:    " + start);

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("Leap +1y: " + leapDay.plusYears(1));
        System.out.println("Leap +4y: " + leapDay.plusYears(4));
        System.out.println("March -1m: "
                + LocalDate.of(2024, 3, 31).minusMonths(1));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac LocalDateMathDemo.java
java LocalDateMathDemo
~~~

Stdout xác định:

~~~text
Original: 2023-01-31
+1 day:   2023-02-01
-2 days:  2023-01-29
+1 week:  2023-02-07
-2 weeks: 2023-01-17
+1 month: 2023-02-28
-1 month: 2022-12-31
+1 year:  2024-01-31
-1 year:  2022-01-31
Still:    2023-01-31
Leap +1y: 2025-02-28
Leap +4y: 2028-02-29
March -1m: 2024-02-29
~~~

`start` vẫn là `2023-01-31` vì `LocalDate` **bất biến**. Lệnh `start.plusDays(1)` chỉ tạo kết quả mới; nó không cập nhật biến `start`. Nếu muốn lưu ngày mới, phải gán:

~~~java
LocalDate dueDate = LocalDate.of(2024, 5, 15);
dueDate = dueDate.plusWeeks(2); // dueDate = 2024-05-29
~~~

Hai dòng trên là **mã minh họa** để đặt trong phương thức/class, không phải chương trình độc lập. `LocalDate` còn là kiểu an toàn cho chia sẻ giữa các luồng vì trạng thái đối tượng không bị sửa đổi.

## 7. Cộng theo từng tháng có thể khác cộng nhiều tháng cùng lúc

Quy tắc co ngày ở cuối tháng dẫn đến khác biệt quan trọng:

~~~text
2023-01-31
 + 1 tháng = 2023-02-28
 + 1 tháng = 2023-03-28

2023-01-31 + 2 tháng trực tiếp = 2023-03-31
~~~

Tương tự, cộng rồi trừ không đảm bảo lấy lại giá trị cũ:

~~~text
2023-01-31 + 1 tháng = 2023-02-28
2023-02-28 - 1 tháng = 2023-01-28
~~~

Thứ tự của hai loại phép toán cũng có thể làm kết quả thay đổi:

~~~text
2023-01-30 + 1 tháng + 2 ngày = 2023-03-02
2023-01-30 + 2 ngày + 1 tháng = 2023-03-01
~~~

Cách chọn **mốc gốc** đặc biệt quan trọng cho kỳ thanh toán định kỳ. Nếu mỗi tháng cập nhật `current = current.plusMonths(1)`, một mốc ban đầu là ngày 31 có thể dần bị “trôi” về ngày 28/29. Nếu hợp đồng yêu cầu “ngày 31 nếu có, nếu không ngày cuối tháng”, hãy giữ `anchor` ban đầu rồi tính kỳ `n` bằng `anchor.plusMonths(n)`.

### Ví dụ: anchor và cuối tháng

Tệp `MonthPolicyDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.YearMonth;

public class MonthPolicyDemo {
    public static void main(String[] args) {
        LocalDate anchor = LocalDate.of(2023, 1, 31);

        LocalDate chained = anchor.plusMonths(1).plusMonths(1);
        LocalDate direct = anchor.plusMonths(2);
        LocalDate roundTrip = anchor.plusMonths(1).minusMonths(1);
        LocalDate monthEnd = YearMonth.from(anchor)
                .plusMonths(1)
                .atEndOfMonth();

        LocalDate orderA = LocalDate.of(2023, 1, 30)
                .plusMonths(1).plusDays(2);
        LocalDate orderB = LocalDate.of(2023, 1, 30)
                .plusDays(2).plusMonths(1);

        System.out.println("Chained: " + chained);
        System.out.println("Direct: " + direct);
        System.out.println("Round-trip: " + roundTrip);
        System.out.println("Next month end: " + monthEnd);
        System.out.println("Month then days: " + orderA);
        System.out.println("Days then month: " + orderB);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac MonthPolicyDemo.java
java MonthPolicyDemo
~~~

Kết quả:

~~~text
Chained: 2023-03-28
Direct: 2023-03-31
Round-trip: 2023-01-28
Next month end: 2023-02-28
Month then days: 2023-03-02
Days then month: 2023-03-01
~~~

**Quy tắc chọn phép tính:**

- Nếu cần cộng một tháng kể từ **ngày hiện tại đã điều chỉnh**, dùng `current.plusMonths(1)`.
- Nếu cần “kỳ thứ `n` tính từ **ngày ký hợp đồng**”, dùng `anchor.plusMonths(n)` và giữ anchor không đổi.
- Nếu cần **cuối mỗi tháng**, dùng `YearMonth.from(anchor).plusMonths(n).atEndOfMonth()`; ví dụ các kỳ tiếp theo của tháng 1/2023 là 28/02, 31/03, 30/04.
- Nếu hợp đồng yêu cầu chuyển ngày 31 sang **ngày 1 tháng sau**, hoặc bỏ kỳ không tồn tại, đó là chính sách riêng và phải triển khai tường minh. `plusMonths` không tự biết quy tắc ấy.

## 8. Period, ChronoUnit và cách đo chênh lệch

Không phải bài toán nào cũng là “cộng một số nguyên đơn vị”.

`Period` biểu diễn **khoảng theo lịch** gồm năm, tháng, ngày. `Period.of(1, 2, 3)` có 1 năm, 2 tháng, 3 ngày; `Period.ofWeeks(2)` được lưu thành 14 ngày và in ra `P14D`. Có thể cộng một `Period` với `LocalDate` qua `date.plus(period)` hoặc trừ bằng `date.minus(period)`.

`ChronoUnit` cung cấp đơn vị chung:

- `date.plus(3, ChronoUnit.MONTHS)` tương đương cộng ba tháng.
- `ChronoUnit.DAYS.between(a, b)` tính số ngày lịch có dấu giữa hai ngày; âm khi `b` trước `a`.
- `ChronoUnit.WEEKS.between(a, b)` đếm số tuần đầy đủ theo khoảng ngày.
- `ChronoUnit.MONTHS.between(a, b)` đếm số **tháng hoàn chỉnh**, không nhất thiết bằng số tháng mà một phép `plusMonths` có thể đi tới do quy tắc co ngày.

Tệp `CalendarDifferenceDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class CalendarDifferenceDemo {
    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 1, 31);
        LocalDate to = LocalDate.of(2024, 3, 1);
        Period calendarDifference = Period.between(from, to);

        System.out.println("Period: " + calendarDifference);
        System.out.println("Days: " + ChronoUnit.DAYS.between(from, to));
        System.out.println("After Period: " + from.plus(calendarDifference));
        System.out.println("Full months to Feb 29: "
                + ChronoUnit.MONTHS.between(
                        from, LocalDate.of(2024, 2, 29)));
        System.out.println("Two weeks: " + Period.ofWeeks(2));
        System.out.println("+3 months: "
                + from.plus(3, ChronoUnit.MONTHS));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CalendarDifferenceDemo.java
java CalendarDifferenceDemo
~~~

Stdout:

~~~text
Period: P1M1D
Days: 30
After Period: 2024-03-01
Full months to Feb 29: 0
Two weeks: P14D
+3 months: 2024-04-30
~~~

Tại sao có những kết quả tưởng như lạ?

- `2024-01-31` đến `2024-03-01` cách nhau **30 ngày lịch**; `Period.between` diễn đạt theo **1 tháng và 1 ngày**.
- `ChronoUnit.MONTHS.between(2024-01-31, 2024-02-29)` trả **0 tháng hoàn chỉnh** theo quy tắc đếm đơn vị, mặc dù `2024-01-31.plusMonths(1)` đúng là `2024-02-29`. “Dịch thêm một tháng lịch” và “đếm số tháng hoàn chỉnh giữa hai mốc” là hai phép toán khác mục đích.
- `Period.ofWeeks(2)` in `P14D` vì `Period` lưu số ngày, không duy trì trường tuần riêng.
- `plus(3, MONTHS)` từ 31/01/2024 tới `30/04/2024`, tháng đích không có ngày 31.

Khi cộng một `Period` có đủ năm/tháng/ngày, phép toán áp dụng thành phần năm và tháng trước ngày. Không quy đổi `Period.of(0, 1, 3)` thành “33 ngày” vì độ dài tháng không cố định. Khi tính deadline, cần chọn rõ ràng giữa `Period`/`ChronoUnit` và khoảng thời gian tuyệt đối `Duration`.

## 9. Các tình huống nghiệp vụ thường gặp

### 9.1. Hạn sau 14 ngày lịch

Nếu ngày nhận là `receivedDate`, ngày hạn tính theo khoảng cách 14 ngày:

~~~java
LocalDate deadline = receivedDate.plusDays(14);
~~~

Đoạn mã này **không độc lập** vì `receivedDate` do chương trình cung cấp. Nếu quy định tính ngày nhận là **ngày thứ nhất**, ngày thứ 14 có thể là `receivedDate.plusDays(13)`. Cần thống nhất điều khoản và dùng kiểm thử ranh giới.

### 9.2. Thanh toán hàng tháng hoặc hằng năm

Một hợp đồng gốc ngày 31/01, yêu cầu “cùng ngày trong tháng nếu có, còn không vào cuối tháng”, có thể tính:

~~~java
LocalDate anchor = LocalDate.of(2023, 1, 31);
LocalDate first = anchor.plusMonths(1);  // 2023-02-28
LocalDate second = anchor.plusMonths(2); // 2023-03-31
~~~

Đoạn trên cũng là **mã minh họa** cần đặt vào phương thức/class. Nếu điều khoản là “ngày cuối tháng”, ưu tiên `YearMonth.atEndOfMonth()` để bộc lộ trực tiếp ý định, kể cả khi anchor không phải ngày cuối tháng.

### 9.3. Cộng ngày làm việc

`plusDays(5)` không phải năm ngày làm việc. Với lịch chỉ nghỉ thứ Bảy/Chủ Nhật, cần kiểm tra `DayOfWeek`; với lịch tổ chức thực tế phải tính cả ngày lễ, ngày bù và lịch vùng. Tránh cài đặt mặc định hai ngày cuối tuần là nghỉ nếu hệ thống phục vụ nhiều quốc gia.

### 9.4. Tính ngày theo vùng của người dùng

`LocalDate.now()` dùng múi giờ mặc định của JVM. Nếu người dùng ở Tokyo nhưng server chạy UTC, hai phía có thể đang ở **hai ngày lịch khác nhau**.

~~~java
LocalDate todayInTokyo = LocalDate.now(
        java.time.ZoneId.of("Asia/Tokyo"));
~~~

Đây là mã minh họa và kết quả thay đổi theo thời gian thực, không có stdout cố định. Trong nghiệp vụ lớn hoặc khi unit test, nên truyền `Clock` và gọi `LocalDate.now(clock)` để kiểm soát nguồn thời gian.

`LocalDate` chỉ chứa ngày lịch; để chuyển đầu ngày thành một mốc tuyệt đối, phải cung cấp `ZoneId` (ví dụ `date.atStartOfDay(zone).toInstant()`) và chấp nhận quy tắc múi giờ tại ngày đó.

## 10. Giới hạn, trường hợp lỗi và kiểm thử

Lớp `LocalDate` hỗ trợ năm từ `-999999999` đến `+999999999` trong hệ lịch ISO/Gregory mở rộng. Các phép cộng trừ quá miền hợp lệ có thể gây `DateTimeException`; một số phép số học cực lớn có thể gây `ArithmeticException`. Hãy xác thực khoảng ngày hợp lệ của ứng dụng và số lượng đơn vị nhập vào.

Lưu ý:

- `LocalDate.of(2023, 2, 29)` không hợp lệ, ném `DateTimeException`.
- `LocalDate.of(2024, 4, 31)` không hợp lệ, ném `DateTimeException`.
- `LocalDate.MAX.plusDays(1)` vượt phạm vi hỗ trợ.
- `date.plus(1, ChronoUnit.HOURS)` không áp dụng cho ngày không có giờ và có thể ném `UnsupportedTemporalTypeException`.
- `date.withDayOfMonth(31)` không tự co ngày như `plusMonths`.

Các kiểm thử nên phủ đủ ngày thường và ranh giới:

1. 28/02 năm thường cộng một ngày → 01/03; 28/02 năm nhuận → 29/02.
2. 31/01 cộng một tháng ở năm thường → 28/02, năm nhuận → 29/02.
3. 29/02/2024 cộng một năm → 28/02/2025; cộng bốn năm → 29/02/2028.
4. 31/01 cộng hai tháng trực tiếp khác cộng lần lượt từng tháng.
5. Cộng rồi trừ tháng không nhất thiết khôi phục ngày ban đầu.
6. Đếm ngày với `ChronoUnit.DAYS.between` đúng chiều và đúng quy tắc bao gồm/loại trừ ranh giới.
7. Không làm thất lạc giá trị `LocalDate` mới do bỏ qua kết quả trả về.

## 11. Những sai lầm thường gặp

| Nhận định hoặc cách làm sai | Hậu quả | Cách đúng |
|---|---|---|
| “`plusDays` sửa chính đối tượng ngày.” | Ngày gốc không đổi; kết quả bị bỏ. | Nhận giá trị trả về hoặc gán lại biến. |
| “Một tháng là 30 ngày.” | Sai cuối tháng và trong năm nhuận. | Dùng `plusMonths` cho tháng lịch. |
| “Một năm luôn là 365 ngày.” | Sai khi qua ngày nhuận. | Dùng `plusYears` và hiểu quy tắc 29/02. |
| “Cộng tháng rồi trừ tháng luôn là phép đảo.” | 31/01 → 28/02 → 28/01. | Giữ anchor để khôi phục/kỳ thanh toán. |
| “`plusMonths(1)` mỗi kỳ luôn giữ ngày 31.” | Lịch lặp bị trôi ngày sau tháng 2. | Tính kỳ `n` từ anchor hoặc `YearMonth`. |
| “`plusWeeks(1)` cho đầu tuần sau.” | Kết quả giữ thứ trong tuần. | Dùng `DayOfWeek` và `TemporalAdjusters` cho thứ mong muốn. |
| “`plusDays(1)` có nghĩa đúng 24 giờ thực.” | Nhầm ngày lịch với thời lượng qua DST. | Phân biệt `LocalDate` với `Instant`/`Duration`. |
| “`ChronoUnit.MONTHS.between` chính là phép ngược của `plusMonths`.” | Sai tại ngày cuối tháng. | Dùng đúng API theo mục tiêu tính toán. |
| “Cộng năm cho ngày 29/02 luôn tới 01/03 năm thường.” | Mặc định Java cho 28/02. | Ghi chính sách riêng nếu nghiệp vụ chọn 01/03. |
| “Cộng ngày lịch cũng là cộng ngày làm việc.” | Tính sai hạn khi có cuối tuần/ngày nghỉ. | Kết hợp lịch làm việc và ngày nghỉ. |

## 12. Câu hỏi tự kiểm tra

**1.** `LocalDate.of(2024, 1, 31).plusMonths(1)` trả gì?

**Đáp án:** `2024-02-29` vì năm 2024 nhuận.

**2.** `LocalDate.of(2023, 1, 31).plusMonths(2)` có bằng `plusMonths(1).plusMonths(1)` không?

**Đáp án:** Không. Cộng trực tiếp cho `2023-03-31`, cộng tuần tự cho `2023-03-28`.

**3.** `LocalDate.of(2024, 2, 29).plusYears(1)` trả gì?

**Đáp án:** `2025-02-28`; ngày 29/02 không tồn tại trong năm 2025.

**4.** Tại sao “sau 7 ngày lịch” không luôn là “sau đúng 168 giờ” khi nói đến giờ địa phương?

**Đáp án:** `LocalDate` chỉ xác định ngày lịch; một số vùng đổi offset (DST), khiến hai mốc cùng giờ địa phương cách nhau bảy ngày lịch có thể có thời lượng thực khác 168 giờ.

**5.** Để tính ngày cuối tháng tiếp theo nên chọn gì?

**Đáp án:** `YearMonth.from(date).plusMonths(1).atEndOfMonth()` khi chính sách thật sự là “cuối mỗi tháng”.

**6.** `Period.ofWeeks(2)` được in thành chuỗi gì?

**Đáp án:** `P14D` vì `Period` lưu 14 ngày trong trường ngày, không lưu riêng trường tuần.

## Ghi nhớ

**Ngày/tuần** di chuyển theo số ngày lịch; **tháng/năm** di chuyển theo cấu trúc lịch và **co về cuối tháng hợp lệ** khi ngày gốc không tồn tại ở tháng/năm đích. `LocalDate` bất biến và không chứa giờ hoặc múi giờ. Khi lập lịch lặp, chọn rõ anchor, chính sách cuối tháng và năm nhuận. Dùng `Period`, `ChronoUnit` hoặc `YearMonth` khi ý định nghiệp vụ tương ứng, và không đánh đồng ngày lịch với thời lượng tuyệt đối.
