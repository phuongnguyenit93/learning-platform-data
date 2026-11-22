# Period và khoảng theo năm, tháng, ngày trong Java 8+

## 1. Vì sao cần Period?

Khi nói "hợp đồng có thời hạn **1 năm 2 tháng 3 ngày**", "khách hàng được gia hạn sau **một tháng lịch**" hoặc "người này đã sống **bao nhiêu năm, tháng, ngày**", ta đang nói về **khoảng thời gian theo lịch**, không phải một lượng giây cố định.

**java.time.Period** (có từ Java 8 và vẫn được hỗ trợ) biểu diễn một khoảng theo hệ lịch ISO-8601 bằng ba phần **years**, **months**, **days**.

~~~java
Period term = Period.of(1, 2, 3);
// P1Y2M3D
~~~

Period **không lưu ngày bắt đầu**, giờ, phút, giây, offset hoặc ZoneId. Lượng thời gian thực mà Period tương ứng có thể phụ thuộc **ngày được áp dụng**. Một tháng đi từ 31/01 không có độ dài giống một tháng đi từ 01/04.

| Bài toán | Chọn kiểu |
| --- | --- |
| Thời hạn hợp đồng tính năm/tháng/ngày | **Period** |
| Chênh lệch giữa hai ngày dân sự | **Period.between(LocalDate, LocalDate)** |
| Một tháng lịch sau ngày bắt đầu | **LocalDate.plusMonths** hoặc **plus(Period.ofMonths(1))** |
| Thời lượng chính xác 36 giờ, 90 phút | **Duration** |
| Tổng ngày giữa hai LocalDate | **ChronoUnit.DAYS.between** |
| Một thời điểm tuyệt đối | **Instant** |
| Ngày giờ theo vùng có DST | **ZonedDateTime** và ZoneId |

Mục tiêu bài: hiểu Period, factory/parse, tính chênh lệch, đọc trường, chuẩn hóa, so sánh, cộng trừ, giá trị âm, ngày cuối tháng, DST, tuổi, lịch gia hạn và kiểm thử code. Các ví dụ chạy độc lập đã được biên dịch và kiểm tra stdout thực tế.

## 2. Period so với Duration

**Period** diễn tả lượng theo lịch: năm, tháng và ngày. **Duration** diễn tả lượng theo đồng hồ: giây và nano giây.

~~~java
Period oneMonth = Period.ofMonths(1);
Period oneCalendarDay = Period.ofDays(1);

Duration exactDay = Duration.ofDays(1);
Duration ninetyMinutes = Duration.ofMinutes(90);
~~~

**Period.ofMonths(1)** không bằng 30 ngày ở mọi tình huống. **Period.ofDays(1)** khi áp vào ZonedDateTime qua DST có thể dẫn tới một Instant chỉ cách mốc ban đầu 23 hoặc 25 giờ; **Duration.ofDays(1)** luôn là 24 giờ elapsed.

**Period không có phương thức ofHours hoặc ofMinutes.** Nếu người dùng yêu cầu "chờ 90 phút" hay "hoàn tất trong 36 giờ", dùng Duration. Nếu yêu cầu "ngày 31 tháng sau" hay "gia hạn một năm", dùng các phép lịch cùng quy tắc nghiệp vụ.

**Một thời hạn và một mốc khác nhau:** Period chỉ là lượng; muốn có ngày đến hạn cần biết ngày bắt đầu LocalDate. Muốn có một Instant chính xác ở cuối kỳ còn cần biết giờ và zone.

## 3. Tạo Period với factory

~~~java
Period twoYears = Period.ofYears(2);     // P2Y
Period fifteenMonths = Period.ofMonths(15); // P15M
Period twoWeeks = Period.ofWeeks(2);     // P14D
Period tenDays = Period.ofDays(10);      // P10D
Period combined = Period.of(1, 2, 3);   // P1Y2M3D
Period zero = Period.ZERO;              // P0D
~~~

**Period.ofWeeks(2)** đổi tuần sang **14 ngày**, không lưu một thành phần weeks riêng. Ba trường của Period luôn là **years, months, days** (mỗi trường có thể là 0 hoặc âm).

**Period.ofMonths(15)** giữ **15 tháng**; không tự chuẩn hóa thành một năm ba tháng. Phép **normalized()** thực hiện việc chuẩn hóa khi cần.

~~~java
Period backward = Period.of(0, -2, 5);
// P-2M5D
~~~

Period là một lượng có hướng (directed amount), không tự cấm thành phần âm. Với hợp đồng phải có thời hạn dương, chính ứng dụng cần đặt giới hạn và kiểm tra dữ liệu.

## 4. Chuỗi P1Y2M3D và parse

**Period.parse** nhận chuỗi theo dạng Period của API:

~~~java
Period p = Period.parse("P1Y2M3D");

System.out.println(p.getYears());  // 1
System.out.println(p.getMonths()); // 2
System.out.println(p.getDays());   // 3
~~~

Ký tự **P** đánh dấu phần period, **Y** là năm, **M** là tháng và **D** là ngày.

| Input | toString | Ý nghĩa |
| --- | --- | --- |
| P2Y | P2Y | Hai năm |
| P3M | P3M | Ba tháng |
| P5D | P5D | Năm ngày |
| P2W | P14D | Hai tuần đổi thành 14 ngày |
| P1Y2M3D | P1Y2M3D | Năm/tháng/ngày |
| P-1Y2M | P-1Y2M | Âm năm, dương tháng |
| -P1Y2M | P-1Y-2M | Dấu âm ở đầu áp cho cả hai trường |

**P1M là một tháng. PT1M là một phút**, thuộc cú pháp Duration, không phải Period.

~~~java
Period month = Period.parse("P1M");
Duration minute = Duration.parse("PT1M");
~~~

Period.parse không có nhiệm vụ đọc chuỗi tiếng Việt tự do hoặc định dạng ngày dd/MM/yyyy. Khi parse input từ API, cần xác thực định dạng, giới hạn số, quy tắc cho phép âm/zero và xử lý **DateTimeParseException**.

## 5. getYears, getMonths, getDays không phải tổng độ dài

~~~java
Period p = Period.of(1, 2, 10);

int years = p.getYears();   // 1
int months = p.getMonths(); // 2
int days = p.getDays();     // 10
~~~

**getDays() = 10** là trường **days**, không phải tổng số ngày của một năm hai tháng mười ngày. **getMonths() = 2** không phải tổng phần tháng của một năm hai tháng.

~~~java
long totalMonths = Period.of(1, 2, 10).toTotalMonths();
// 14; bỏ qua 10 ngày.
~~~

**toTotalMonths() = years*12 + months** trả long, không quy đổi days. Nếu cần tổng ngày chính xác từ một Period có tháng/năm, hãy chọn ngày gốc và tính:

~~~java
LocalDate start = LocalDate.of(2025, 1, 31);
LocalDate end = start.plus(Period.ofMonths(1));

long days = ChronoUnit.DAYS.between(start, end);
// 28
~~~

Đoạn minh họa cần import java.time.* và java.time.temporal.ChronoUnit.

Không dùng công thức years*365 + months*30 + days cho ngày hợp đồng nếu không có một quy ước ước lượng đã được xác định rõ. Độ dài tháng thay đổi, năm có thể nhuận.

## 6. Period.between giữa hai LocalDate

~~~java
LocalDate start = LocalDate.of(2010, 1, 15);
LocalDate end = LocalDate.of(2011, 3, 18);

Period between = Period.between(start, end);
System.out.println(between); // P1Y2M3D
~~~

Ý nghĩa: từ 15/01/2010 tới 15/01/2011 là một năm; tới 15/03/2011 thêm hai tháng; tới 18/03/2011 thêm ba ngày.

API nhận **startDateInclusive** và **endDateExclusive**. Nó tính tháng hoàn chỉnh rồi phần ngày còn lại, sau đó đổi tháng thành năm/tháng theo mốc 12 tháng/năm. Đây là phép chênh lệch **theo lịch**, không phải khoảng giây.

Nếu end trước start, kết quả có thể âm:

~~~java
Period backward = Period.between(
        LocalDate.of(2025, 5, 1),
        LocalDate.of(2025, 4, 20));

System.out.println(backward); // P-11D
~~~

Giá trị âm không nhất thiết là lỗi. Nhưng nếu nghiệp vụ yêu cầu thời hạn không âm, bạn phải xác thực ngày đầu/cuối trước khi tính.

**Biên end exclusive** mô tả phép tính hai mốc. Nếu một hợp đồng tính cả ngày kết thúc trong số ngày sử dụng, đó là chính sách đếm ngày **inclusive** riêng; không tự thêm một ngày vào mọi kết quả Period.between.

## 7. Period.between so với ChronoUnit.between

| API | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Period.between(a,b) | **Period** | Khoảng theo Y/M/D |
| a.until(b) | **Period** | Phép tính khoảng của LocalDate |
| ChronoUnit.DAYS.between(a,b) | **long** | Số ngày giữa hai LocalDate |
| ChronoUnit.MONTHS.between(a,b) | **long** | Số tháng hoàn chỉnh |
| ChronoUnit.YEARS.between(a,b) | **long** | Số năm hoàn chỉnh |

Ca biên thú vị:

~~~java
LocalDate a = LocalDate.of(2024, 1, 31);
LocalDate b = LocalDate.of(2024, 2, 29);

System.out.println(Period.between(a, b));
// P29D

System.out.println(ChronoUnit.MONTHS.between(a, b));
// 0

System.out.println(ChronoUnit.DAYS.between(a, b));
// 29
~~~

Mặc dù **a.plusMonths(1)** ra **29/02/2024** theo quy tắc ngày cuối tháng, **ChronoUnit.MONTHS.between(a,b)** trả 0 vì thuật toán tính số tháng hoàn chỉnh xét day-of-month.

**Không tự coi cộng 1 tháng và phép tính số tháng đã qua là hai phép toán nghịch đảo hoàn hảo trên mọi ngày.** Lịch gia hạn và thời hạn bảo hành cần quy tắc riêng ở ngày cuối tháng.

## 8. Period immutable, value-based và các phép toán

Period **immutable** và **thread-safe**. Các phép tính trả giá trị Period thay vì sửa instance gốc.

~~~java
Period original = Period.of(1, 2, 3);

Period plus = original.plusMonths(2);     // P1Y4M3D
Period minus = original.minusDays(1);     // P1Y2M2D
Period doubleTerm = original.multipliedBy(2); // P2Y4M6D
Period negated = original.negated();      // P-1Y-2M-3D

System.out.println(original); // P1Y2M3D
~~~

Có thể dùng **plusYears/plusMonths/plusDays**, **minusYears/minusMonths/minusDays**, **plus(TemporalAmount)**, **minus(TemporalAmount)**, **withYears/withMonths/withDays**, **multipliedBy**, **negated**.

Phân biệt **withMonths** và **plusMonths**:

~~~java
Period p = Period.of(1, 2, 3);
Period replaced = p.withMonths(5); // P1Y5M3D
Period increased = p.plusMonths(5); // P1Y7M3D
~~~

**withMonths(5)** đặt trường months thành 5, còn **plusMonths(5)** cộng thêm 5 tháng vào trường cũ.

Vì Period là **value-based class**, không dùng **==** để kiểm tra giá trị, không dựa vào caching/identityHashCode và không dùng chính Period làm monitor **synchronized**. Dùng **equals** khi cần so bằng giá trị.

Nếu phép toán làm các trường vượt miền int, có thể ném **ArithmeticException**; khi cộng Period vào một LocalDate vượt miền ngày hợp lệ, có thể ném **DateTimeException**.

## 9. normalized chỉ điều chỉnh years/months

~~~java
Period raw = Period.ofMonths(15);
Period norm = raw.normalized();

System.out.println(raw);  // P15M
System.out.println(norm); // P1Y3M
~~~

**normalized()** chuyển phần tháng sang năm để tháng có trị tuyệt đối nhỏ hơn 12, giữ nguyên days. Nó không tự đổi ngày sang tháng:

~~~java
Period fortyDays = Period.ofDays(40);

System.out.println(fortyDays.normalized());
// P40D
~~~

Vì không có tháng dài cố định, thiếu ngày bắt đầu thì không thể nói 40 ngày bằng "một tháng mười ngày" theo lịch.

Trường hợp có signs hỗn hợp:

~~~java
Period mixed = Period.of(1, -2, 3);

System.out.println(mixed);              // P1Y-2M3D
System.out.println(mixed.normalized()); // P10M3D
~~~

Phần một năm trừ hai tháng được đưa thành mười tháng; ba ngày không đổi. **normalized không biến Period thành một số giây hay số ngày thực**.

## 10. equals, isZero, isNegative

~~~java
Period oneYear = Period.ofYears(1);
Period twelveMonths = Period.ofMonths(12);

System.out.println(oneYear.equals(twelveMonths)); // false
~~~

**Period.equals** so **cả ba trường years, months, days**, không tự gọi normalized. Vì vậy **P1Y** và **P12M** khác nhau khi so trực tiếp, dù:

~~~java
boolean sameAfterNormalization =
        oneYear.normalized().equals(twelveMonths.normalized());
// true
~~~

Nếu muốn khử trùng theo quy tắc tổng years/months, phải chọn chính sách chuẩn hóa có chủ đích. Với những Period có days, không thể tự chuyển days thành tháng trọn vẹn mà không có ngày tham chiếu.

~~~java
System.out.println(Period.ZERO.isZero()); // true

Period mixed = Period.of(1, -2, 3);
System.out.println(mixed.isNegative()); // true
~~~

**isNegative()** là true **nếu bất kỳ trường nào âm**; không phải một phép kiểm tra "độ dài thực tổng thể là âm". Period có thể mang dấu khác nhau giữa các trường.

Period không có natural ordering về độ dài tuyệt đối áp dụng cho mọi ngày: **P1M** có thể dài hơn hoặc ngắn hơn **P30D** tùy ngày bắt đầu. Không dùng toString lexicographic hoặc giả định months*30 để sắp thứ tự chính xác.

## 11. Áp Period vào LocalDate

~~~java
LocalDate start = LocalDate.of(2010, 1, 15);
Period term = Period.of(1, 2, 3);

LocalDate due = start.plus(term);
System.out.println(due); // 2011-03-18
~~~

**LocalDate.plus(Period)** cộng lượng theo lịch. **LocalDate.minus(Period)** trừ lượng. Period cũng có addTo/subtractFrom theo giao diện TemporalAmount nhưng **date.plus(period)** thường trực quan hơn.

**Period không có một ngày đến hạn cố định nếu không có ngày bắt đầu.** P1M áp vào 31/01 khác áp vào 01/04 về số ngày trôi qua.

### Ngày cuối tháng

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);

System.out.println(jan31.plus(Period.ofMonths(1)));
// 2025-02-28

System.out.println(jan31.plus(Period.ofDays(30)));
// 2025-03-02
~~~

Khi ngày-of-month không tồn tại ở tháng đích, LocalDate điều chỉnh về ngày hợp lệ cuối cùng của tháng đích.

~~~java
LocalDate leap = LocalDate.of(2024, 2, 29);

System.out.println(leap.plus(Period.ofYears(1)));
// 2025-02-28
~~~

Đây là hành vi API, không tự thay thế chính sách hạn hợp đồng, ngày sinh nhật hoặc kỳ thu phí của ứng dụng.

### Cộng gộp năm/tháng khác cộng từng bước

~~~java
LocalDate leapStart = LocalDate.of(2020, 2, 29);

LocalDate grouped = leapStart.plus(Period.of(1, 1, 0));
LocalDate chained = leapStart.plusYears(1).plusMonths(1);

System.out.println(grouped); // 2021-03-29
System.out.println(chained); // 2021-03-28
~~~

Period có năm và tháng được áp theo **tổng tháng** trước khi thêm ngày; còn chuỗi plusYears trước sẽ điều chỉnh 29/02 thành 28/02/2021, rồi plusMonths đưa tới 28/03.

**Không thay hai cách biểu diễn bằng nhau theo trực giác** nếu nghiệp vụ có ranh giới ngày cuối tháng/năm nhuận. Test cần có 29/02 và ngày 28, 29, 30, 31.

## 12. Gia hạn hàng tháng: anchored khác chained

Một hợp đồng bắt đầu **31/01/2025** và gia hạn mỗi tháng.

**Anchored:** mỗi kỳ tính từ ngày đăng ký ban đầu, nghĩa là kỳ thứ n = anchor.plusMonths(n).

**Chained:** mỗi kỳ lấy ngày của kỳ trước cộng thêm một tháng.

Kết quả:

| Kỳ | Từ ngày gốc | Cộng tiếp từ kỳ trước |
| --- | --- | --- |
| 1 | 28/02/2025 | 28/02/2025 |
| 2 | 31/03/2025 | 28/03/2025 |
| 3 | 30/04/2025 | 28/04/2025 |

Mã anchored:

~~~java
LocalDate anchor = LocalDate.of(2025, 1, 31);

LocalDate first = anchor.plusMonths(1);  // 2025-02-28
LocalDate second = anchor.plusMonths(2); // 2025-03-31
LocalDate third = anchor.plusMonths(3);  // 2025-04-30
~~~

Mã chained dùng một biến date nhận kết quả sau từng lần date.plus(Period.ofMonths(1)).

Không cách nào là "đúng" cho mọi hợp đồng. Nếu yêu cầu **cuối mỗi tháng**, có thể mô hình trực tiếp:

~~~java
LocalDate due =
        YearMonth.from(anchor).plusMonths(2).atEndOfMonth();
// 2025-03-31
~~~

Với ngày đăng ký là 15, đừng tự coi kỳ hạn là ngày cuối tháng. Xác định **anchor, quy tắc điều chỉnh và chính sách ngày không tồn tại** ngay trong hợp đồng/API.

## 13. Tính tuổi và người sinh 29/02

~~~java
LocalDate birth = LocalDate.of(2000, 2, 29);
LocalDate asOf = LocalDate.of(2025, 3, 1);

int yearsCompleted = Period.between(birth, asOf).getYears();
// 25
~~~

**Period.between(...).getYears()** trả phần năm theo cách tính lịch của API, rất hữu ích cho nhiều ứng dụng. Nhưng tuổi pháp lý hoặc chương trình sinh nhật có thể cần **quy tắc riêng cho ngày sinh 29/02 trong năm không nhuận**.

Ví dụ đã xác minh:

~~~java
LocalDate birth = LocalDate.of(2000, 2, 29);

System.out.println(
        Period.between(birth, LocalDate.of(2025, 2, 28)).getYears());
// 24

System.out.println(
        Period.between(birth, LocalDate.of(2025, 3, 1)).getYears());
// 25
~~~

Không khẳng định API đã quyết định hộ quy định pháp lý. Hãy lưu LocalDate ngày sinh nguyên vẹn, chọn ngày tham chiếu theo múi giờ hợp lệ, xác định chính sách ngày 29/02 và test 28/02–01/03.

**Trong unit test**, dùng ngày tham chiếu cố định hoặc Clock.fixed thay vì LocalDate.now() trực tiếp; tránh sai khác theo ngày và múi giờ của máy chạy.

## 14. Period qua DST không phải 24 giờ elapsed

**Period.ofDays(1)** cộng một ngày **theo lịch**, cố duy trì giờ địa phương của ZonedDateTime. **Duration.ofDays(1)** là đúng **24 giờ thực**.

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2025, 3, 29, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime calendarNext =
        start.plus(Period.ofDays(1));
ZonedDateTime elapsedNext =
        start.plus(Duration.ofDays(1));
~~~

Khi Paris chuyển giờ mùa hè vào ngày 30/03/2025, kết quả kiểm chứng là:

~~~text
calendar next: 2025-03-30T12:00+02:00[Europe/Paris]
elapsed next: 2025-03-30T13:00+02:00[Europe/Paris]
elapsed hours calendar: 23
~~~

Khoảng **từ 12:00 hôm trước tới 12:00 hôm sau** chỉ có 23 giờ thật vì đồng hồ nhảy về trước một giờ. Duration một ngày luôn cộng 24 giờ nên tới 13:00.

**Ứng dụng:** lịch hằng ngày địa phương nên dùng ngày lịch; thời gian chờ 24 giờ dùng Duration; số giờ làm thực lấy Instant check-in/out, Duration và chính sách chấm công. **Period không thể tự áp "một tháng" vào Instant** khi thiếu ngữ nghĩa calendar/ZoneId.

## 15. Chương trình Java độc lập: kiểm chứng các phép toán Period

Tạo tệp **PeriodCalendarDemo.java**:

~~~java
import java.time.*;
import java.time.temporal.ChronoUnit;

public class PeriodCalendarDemo {
    public static void main(String[] args) {
        Period custom = Period.of(1, 2, 3);
        Period parsed = Period.parse("P1Y2M3D");
        System.out.println("created: " + custom);
        System.out.println("parsed equal: " + custom.equals(parsed));
        System.out.println("weeks: " + Period.ofWeeks(2));
        System.out.println("parsed weeks: " + Period.parse("P2W"));

        LocalDate start = LocalDate.of(2010, 1, 15);
        LocalDate end = LocalDate.of(2011, 3, 18);
        Period between = Period.between(start, end);
        System.out.println("between: " + between);
        System.out.println("start plus between: " + start.plus(between));
        System.out.println("fields: " + between.getYears()
                + "y " + between.getMonths() + "m " + between.getDays() + "d");

        Period raw = Period.ofMonths(15);
        Period normalized = raw.normalized();
        System.out.println("raw and normalized: " + raw + " / " + normalized);
        System.out.println("raw equals normalized: " + raw.equals(normalized));
        System.out.println("year equals twelve months: "
                + Period.ofYears(1).equals(Period.ofMonths(12)));
        System.out.println("total months: " + raw.toTotalMonths());
        System.out.println("days excluded from months: "
                + Period.of(1, 2, 10).toTotalMonths());

        Period mixed = Period.of(1, -2, 3);
        System.out.println("mixed negative: " + mixed.isNegative());
        System.out.println("mixed normalized: " + mixed.normalized());
        System.out.println("zero: " + Period.ZERO + " / " + Period.ZERO.isZero());
        System.out.println("backward: "
                + Period.between(LocalDate.of(2025, 5, 1),
                                 LocalDate.of(2025, 4, 20)));
        System.out.println("signed parse: " + Period.parse("P-1Y2M")
                + " / " + Period.parse("-P1Y2M"));

        LocalDate lastJan = LocalDate.of(2025, 1, 31);
        System.out.println("jan31 plus month: "
                + lastJan.plus(Period.ofMonths(1)));
        System.out.println("jan31 plus 30d: "
                + lastJan.plus(Period.ofDays(30)));

        LocalDate leap = LocalDate.of(2024, 2, 29);
        System.out.println("leap plus year: "
                + leap.plus(Period.ofYears(1)));

        LocalDate leapStart = LocalDate.of(2020, 2, 29);
        System.out.println("grouped year+month: "
                + leapStart.plus(Period.of(1, 1, 0)));
        System.out.println("separate year then month: "
                + leapStart.plusYears(1).plusMonths(1));

        LocalDate jan31Leap = LocalDate.of(2024, 1, 31);
        LocalDate feb29Leap = LocalDate.of(2024, 2, 29);
        System.out.println("jan31 to feb29 period: "
                + Period.between(jan31Leap, feb29Leap));
        System.out.println("complete months: "
                + ChronoUnit.MONTHS.between(jan31Leap, feb29Leap));
        System.out.println("days between: "
                + ChronoUnit.DAYS.between(jan31Leap, feb29Leap));

        LocalDate birth = LocalDate.of(2000, 2, 29);
        LocalDate feb28 = LocalDate.of(2025, 2, 28);
        LocalDate march1 = LocalDate.of(2025, 3, 1);
        System.out.println("age Feb28: "
                + Period.between(birth, feb28).getYears());
        System.out.println("age Mar01: "
                + Period.between(birth, march1).getYears());

        ZonedDateTime paris = ZonedDateTime.of(
                2025, 3, 29, 12, 0, 0, 0,
                ZoneId.of("Europe/Paris"));
        ZonedDateTime calendarNext = paris.plus(Period.ofDays(1));
        ZonedDateTime elapsedNext = paris.plus(Duration.ofDays(1));
        System.out.println("calendar next: " + calendarNext);
        System.out.println("elapsed next: " + elapsedNext);
        System.out.println("elapsed hours calendar: "
                + Duration.between(paris, calendarNext).toHours());

        System.out.println("period with days: "
                + Period.of(1, 2, 10));
        System.out.println("double period: "
                + Period.of(1, 2, 3).multipliedBy(2));
        System.out.println("negated: "
                + Period.of(1, 2, 3).negated());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac PeriodCalendarDemo.java
java PeriodCalendarDemo
~~~

**Stdout chính xác đã biên dịch và chạy:**

~~~text
created: P1Y2M3D
parsed equal: true
weeks: P14D
parsed weeks: P14D
between: P1Y2M3D
start plus between: 2011-03-18
fields: 1y 2m 3d
raw and normalized: P15M / P1Y3M
raw equals normalized: false
year equals twelve months: false
total months: 15
days excluded from months: 14
mixed negative: true
mixed normalized: P10M3D
zero: P0D / true
backward: P-11D
signed parse: P-1Y2M / P-1Y-2M
jan31 plus month: 2025-02-28
jan31 plus 30d: 2025-03-02
leap plus year: 2025-02-28
grouped year+month: 2021-03-29
separate year then month: 2021-03-28
jan31 to feb29 period: P29D
complete months: 0
days between: 29
age Feb28: 24
age Mar01: 25
calendar next: 2025-03-30T12:00+02:00[Europe/Paris]
elapsed next: 2025-03-30T13:00+02:00[Europe/Paris]
elapsed hours calendar: 23
period with days: P1Y2M10D
double period: P2Y4M6D
negated: P-1Y-2M-3D
~~~

**Mẫu dùng toàn bộ API có từ Java 8** (được chạy với compiler tương thích Java 17). Mọi ngày đầu vào cố định; dòng DST dùng quy tắc Europe/Paris năm 2025 trong dữ liệu timezone của JDK. Với lịch tương lai, cần sử dụng tzdb được cập nhật phù hợp.

## 16. Chương trình Java 8 độc lập: các kỳ gia hạn và tuổi

Tạo tệp **PeriodRenewalDemo.java**:

~~~java
import java.time.*;

public class PeriodRenewalDemo {
    public static void main(String[] args) {
        LocalDate anchor = LocalDate.of(2025, 1, 31);
        LocalDate chained = anchor;

        for (int month = 1; month <= 3; month++) {
            chained = chained.plus(Period.ofMonths(1));
            LocalDate anchored = anchor.plusMonths(month);
            System.out.println("month " + month + ": anchored=" + anchored
                    + ", chained=" + chained);
        }

        LocalDate birth = LocalDate.of(2000, 2, 29);
        for (LocalDate asOf : new LocalDate[] {
                LocalDate.of(2025, 2, 28),
                LocalDate.of(2025, 3, 1)}) {
            int completedYears = Period.between(birth, asOf).getYears();
            System.out.println("age on " + asOf + ": " + completedYears);
        }
    }
}
~~~

Chạy với JDK 8+:

~~~bash
javac PeriodRenewalDemo.java
java PeriodRenewalDemo
~~~

**Stdout đã xác minh bằng javac --release 8:**

~~~text
month 1: anchored=2025-02-28, chained=2025-02-28
month 2: anchored=2025-03-31, chained=2025-03-28
month 3: anchored=2025-04-30, chained=2025-04-28
age on 2025-02-28: 24
age on 2025-03-01: 25
~~~

Điều quan trọng ở đây không phải hai lịch có số lần gia hạn khác nhau, mà là **cách chọn ngày gốc cho mỗi phép cộng**. Lịch từ ngày neo giữ tháng 3 tại ngày 31 nếu tồn tại, trong khi lịch cộng tiếp sau 28/02 theo ngày 28.

## 17. Các lỗi phổ biến

- **Nhầm một tháng là 30 ngày hoặc một năm là 365 ngày:** không đúng cho tất cả ngày tháng.
- **Dùng getDays làm tổng ngày:** getDays chỉ là một trường.
- **Mong normalized chuyển P40D thành tháng:** chỉ năm/tháng được chuẩn hóa.
- **Mong P1Y.equals(P12M) là true:** equals kiểm tra các trường, không tự chuẩn hóa.
- **Cho rằng isNegative nói một độ dài scalar âm:** chỉ cần một thành phần âm là true.
- **Dùng PT1M như một Period một tháng:** PT1M là một phút thuộc Duration.
- **Cộng năm/tháng qua nhiều bước rồi mặc nhiên thay bằng một Period:** khác nhau ở ngày điều chỉnh trung gian, đặc biệt 29/02.
- **Tính gia hạn chained khi yêu cầu anchored:** có thể trôi ngày.
- **Dùng Period.ofDays(1) để biểu diễn đúng 24 giờ thực:** sai qua DST.
- **Dùng Period.ofDays(10) cho 10 ngày làm việc:** Period là ngày lịch; muốn ngày làm việc cần holiday calendar.
- **Bỏ qua người sinh 29/02:** cần policy ngày kỷ niệm hoặc tuổi pháp lý riêng.
- **Dùng identity (==) để so Period:** đối tượng là value-based; dùng equals.
- **Lưu kỳ hạn chỉ bằng timestamp đến hạn:** mất quy tắc nếu không lưu ngày gốc và Period/policy.
- **Không bắt lỗi parse hoặc tràn số:** input ngoài có thể gây DateTimeParseException, ArithmeticException hay DateTimeException.

## 18. Checklist khi đưa vào ứng dụng

**Dữ liệu:** Year/month/day có nghĩa rõ? Có cho giá trị âm hay zero? Có chuẩn hóa years/months trước khi lưu? Có validate số lớn và input parse?

**Bài toán:** cần đúng một lượng lịch, đúng một số giờ elapsed hay một Instant cụ thể? Có biết ngày gốc? Ngày cuối có được tính inclusive theo contract?

**Ranh giới:** thử 28/29/30/31, tháng 2 năm nhuận, ngày 29/02, kỳ qua cuối năm. Với kỳ lặp, anchored hay chained? Nếu ngày đến hạn không phải ngày làm việc, có rule dời ngày?

**Múi giờ:** nếu có giờ địa phương, có ZoneId? Nếu yêu cầu đúng thời lượng thực, đã dùng Duration và kiểm thử DST?

**Kiểm thử:** dùng ngày cố định và Clock.fixed khi cần "hôm nay"; đừng để test thay đổi theo giờ server. So sánh kết quả với yêu cầu nghiệp vụ, không chỉ kiểm tra phép parse thành công.

**Lưu trữ/API:** có thể dùng chuỗi P1Y2M3D hoặc ba trường số với contract rõ. Không chuyển tháng thành milliseconds. Nếu database có loại INTERVAL, phải kiểm tra hợp đồng và mapping của driver, không giả định mọi DB xử lý giống nhau.

## 19. Bài tập với đáp án

**1. Period.ofWeeks(2) sẽ in gì?** P14D; weeks được quy thành days.

**2. P15M và P1Y3M có equals không?** Không khi so trực tiếp; có thể normalized trước khi so phần năm/tháng.

**3. normalized có đổi 40 ngày thành 1 tháng 10 ngày?** Không; days giữ nguyên.

**4. Cộng một tháng từ 31/01/2025 được ngày nào?** 28/02/2025; cộng 30 ngày ra 02/03/2025.

**5. Period.between(31/01/2024,29/02/2024) là gì?** P29D, còn MONTHS.between là 0 và DAYS.between là 29.

**6. Tại sao cộng P1Y1M từ 29/02/2020 khác plusYears rồi plusMonths?** Cộng gộp ra 29/03/2021, cộng từng bước ra 28/03/2021 do ngày 29/02 bị điều chỉnh trong bước đầu.

**7. Từ 31/01, kỳ gia hạn thứ hai anchored/chained khác nhau thế nào?** Anchored 31/03, chained 28/03, cần chọn chính sách.

**8. Dùng getDays để lấy tổng ngày của P1Y2M3D?** Không; cần ngày gốc và tính end, rồi dùng DAYS.between.

**9. isNegative của P1Y-2M3D là gì?** True, vì một trường âm.

**10. Period một ngày qua DST có phải luôn 24 giờ?** Không; ví dụ Paris cho 23 giờ elapsed trong ngày chuyển mùa.

**11. Tính thời hạn 90 phút với Period?** Dùng Duration.ofMinutes(90).

**12. Có thể dùng kết quả Period.getYears để kết luận mọi quy định tuổi pháp lý?** Không; nhất là với người sinh 29/02 cần xác định policy.

## 20. Tóm tắt và tài liệu chính thức

1. **Period** là lượng năm/tháng/ngày của lịch ISO, hiện hành từ Java 8.
2. **Period khác Duration**: tháng và năm không có số giây cố định.
3. **Period.between** trả Y/M/D; các getter chỉ đọc từng thành phần.
4. **toTotalMonths** bỏ qua days; **normalized** chỉ điều chỉnh years/months.
5. **Period.ofWeeks** lưu theo days; **P1M** là tháng, **PT1M** là phút trong Duration.
6. **Period.equals** so cả ba trường; P12M không equals P1Y khi chưa chuẩn hóa.
7. **LocalDate.plus(period)** xử lý tháng ngắn, năm nhuận; cộng gộp khác cộng từng bước.
8. **Gia hạn hàng tháng** cần chọn anchored/chained rõ ràng.
9. **Period.ofDays(1)** qua DST có thể khác 24 giờ elapsed.
10. **Tuổi, ngày làm việc và ranh giới hợp đồng** cần quy tắc nghiệp vụ bổ sung.

**Tài liệu chính thức Oracle Java SE 25 còn áp dụng:**

- Period: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html
- LocalDate: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Duration: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html
- ZonedDateTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- ChronoUnit: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/ChronoUnit.html
- YearMonth: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/YearMonth.html
- Package java.time: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html

**Phiên bản:** toàn bộ API được dùng trong hai chương trình đều đã có từ Java 8 và vẫn được hỗ trợ; chương trình gia hạn được biên dịch bằng mục tiêu Java 8, chương trình tổng hợp được chạy thành công trên JDK hiện đại.
