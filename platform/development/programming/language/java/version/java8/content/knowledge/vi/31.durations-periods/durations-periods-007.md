# Định dạng ISO-8601 cho khoảng thời gian trong Java

**Chủ đề:** Java 8 → Khoảng thời gian → Định dạng ISO-8601.

**ISO-8601** là hệ quy ước để biểu diễn ngày, giờ, thời điểm, lượng thời gian và khoảng giữa các mốc bằng văn bản có cấu trúc. Trong Java hiện đại, hai lớp trung tâm của phần **lượng thời gian** là:

- **java.time.Period:** lượng thời gian theo **năm, tháng, ngày lịch**.
- **java.time.Duration:** lượng thời gian theo **giây và nano**, thích hợp cho timeout, elapsed time và tính toán trên timeline.

Hai chuỗi rất dễ nhầm:

~~~text
P1M   = 1 tháng lịch   (Period)
PT1M  = 1 phút         (Duration)
~~~

Chỉ một chữ **T** đã đổi ý nghĩa của **M**. Tương tự, **P1D** được Java chấp nhận bởi cả **Period.parse** và **Duration.parse**, nhưng một bên dùng **ngày lịch**, còn bên kia diễn giải thành **24 giờ cố định**. Hai cách tính có thể cho kết quả khác nhau khi áp qua ngày chuyển giờ mùa hè (DST).

Những API được đề cập vẫn được sử dụng trong Java hiện đại. Ví dụ độc lập chạy được trên **Java 17+**, trong khi các API cốt lõi **Period**, **Duration**, **LocalDate**, **Instant**, **ZonedDateTime** và **DateTimeFormatter** đều có từ Java 8.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc cấu trúc **P...T...**, nhận diện các đơn vị **Y, M, W, D, H, M, S**.
2. Phân biệt **P1M**, **PT1M**, **P1D**, **PT24H**, và ý nghĩa lịch so với thời lượng.
3. Parse và format bằng **Period.parse**, **Duration.parse**, **toString()**.
4. Biết ranh giới hỗ trợ của parser Java so với mọi biểu diễn ISO-8601 nói chung.
5. Giải thích vì sao toString có thể thay **P2W** thành **P14D**, hoặc **P2D** thành **PT48H**.
6. Tính ngày kết thúc một kỳ lịch và thời điểm hết hạn một Duration.
7. Tránh sai số khi làm việc với tháng khác độ dài, ngày nhuận và DST.
8. Phân biệt một **lượng thời gian** với một **interval có hai ranh giới**.
9. Kiểm tra và xử lý chuỗi không hợp lệ hoặc nằm ngoài miền giá trị.
10. Thiết kế hợp đồng API rõ ràng khi truyền lượng thời gian giữa các hệ thống.

## 2. ISO date, date-time, duration và interval là bốn loại dữ liệu khác nhau

| Loại thông tin | Ví dụ | Ý nghĩa |
|---|---|---|
| **Date** | **2026-01-02** | Một ngày theo lịch ISO |
| **Local date-time** | **2026-01-02T09:30:00** | Ngày và giờ, chưa có offset hoặc zone |
| **Offset date-time** | **2026-01-02T09:30:00+07:00** | Ngày giờ kèm offset, đủ xác định Instant |
| **Instant** | **2026-01-02T02:30:00Z** | Một điểm trên timeline |
| **Temporal amount** | **P1M**, **PT15M**, **P2DT3H** | Một lượng thời gian |
| **Interval** | **2026-01-01/2026-02-01** | Một đoạn có các ranh giới |

**P1M** không cho biết kỳ bắt đầu lúc nào. Chỉ từ đó không thể suy ra một timestamp kết thúc hoặc số giây thật. Nếu bắt đầu từ 31/1/2024, cộng một tháng lịch sẽ tới 29/2/2024; nếu bắt đầu từ 31/1/2025, kết quả là 28/2/2025.

**PT15M** cũng không mang mốc bắt đầu, nhưng có độ dài cố định là **900 giây**. Khi đã có Instant bắt đầu, việc cộng Duration vào Instant cho ra một Instant kết thúc.

**Interval** là khái niệm khác: nó có ranh giới start/end. Java không cung cấp một lớp Interval tổng quát trong java.time chuẩn tự đọc mọi cú pháp interval ISO; ứng dụng thường mô hình hóa start và end bằng LocalDate, Instant hoặc kiểu phù hợp.

## 3. Cấu trúc ký hiệu P...T...

Dạng tổng quát thường dùng để mô tả lượng thời gian theo ISO-8601:

~~~text
P[n]Y[n]M[n]W[n]DT[n]H[n]M[n]S
│   │   │   │   │  │   │   │   │
│   │   │   │   │  │   │   │   └── Giây
│   │   │   │   │  │   │   └────── Phút
│   │   │   │   │  │   └────────── Giờ
│   │   │   │   │  └────────────── Phần thời gian bắt đầu sau T
│   │   │   │   └───────────────── Ngày
│   │   │   └───────────────────── Tuần
│   │   └───────────────────────── Tháng
│   └───────────────────────────── Năm
└───────────────────────────────── P: bắt đầu lượng thời gian
~~~

Đây là **sơ đồ giúp đọc đơn vị**, không phải lời hứa rằng mọi tổ hợp đều hợp lệ theo mọi biến thể của ISO-8601 hoặc đều được Java parse. Đặc biệt, cách biểu diễn theo **tuần** có quy tắc riêng trong ISO-8601 và không được tùy ý trộn với các đơn vị khác khi bên nhận đòi chuẩn nghiêm ngặt.

| Ký hiệu | Vị trí | Ý nghĩa |
|---|---|---|
| **P** | Đầu chuỗi | Bắt đầu lượng thời gian |
| **Y** | Trước T | Years — năm lịch |
| **M** | Trước T | Months — tháng lịch |
| **W** | Trước T | Weeks — tuần |
| **D** | Trước T | Days — ngày |
| **T** | Giữa các phần | Bắt đầu phần giờ/phút/giây |
| **H** | Sau T | Hours — giờ |
| **M** | Sau T | Minutes — phút |
| **S** | Sau T | Seconds — giây |
| **.** | Trong phần giây | Dấu thập phân, như PT0.125S |

Những ví dụ phổ biến:

~~~text
P3Y            3 năm lịch
P2M            2 tháng lịch
P2W            2 tuần
P10D           10 ngày
PT3H           3 giờ
PT15M          15 phút
PT45S          45 giây
PT1H30M        1 giờ 30 phút
PT0.125S       0,125 giây
P2DT3H4M       2 ngày + 3 giờ + 4 phút
P1Y2M3D        1 năm + 2 tháng + 3 ngày
~~~

### 3.1. Một chữ M, hai ý nghĩa

~~~text
P1M        M đứng trước T → MONTH
PT1M       M đứng sau T   → MINUTE
P1Y2M      1 năm 2 tháng
PT1H2M     1 giờ 2 phút
~~~

Không sử dụng điều kiện kiểu **text.endsWith("M")** để xác định đơn vị. Parser phải hiểu cả vị trí và cấu trúc của ký hiệu.

### 3.2. Không có T thì không có phần giờ/phút/giây

Trong cú pháp lượng thời gian, **T** không phải ký hiệu timezone. Nó phân cách đơn vị theo lịch với đơn vị thời gian. Khi có giờ/phút/giây, phần sau T phải có nội dung.

~~~text
PT15M    hợp lệ: 15 phút
PT       không đủ nội dung
P        không đủ nội dung
~~~

**T trong date-time** như **2026-01-02T09:30** có vai trò khác: phân tách ngày với giờ. Không được nhầm date-time đó với một lượng thời gian.

## 4. Period: năm, tháng, ngày theo lịch

**java.time.Period** là kiểu **date-based** có ba field:

~~~java
Period calendar = Period.parse("P1Y2M3D");

int years = calendar.getYears();
int months = calendar.getMonths();
int days = calendar.getDays();
~~~

Đây là đoạn minh họa; cần import **java.time.Period**.

Kết quả có years=1, months=2, days=3. **Period không lưu giờ/phút/giây**. Những phương thức phổ biến:

- **Period.ofYears(n)**, **ofMonths(n)**, **ofDays(n)**, **ofWeeks(n)**.
- **Period.of(years, months, days)**.
- **Period.parse(text)** và **toString()**.
- **Period.between(LocalDate start, LocalDate end)**.
- **plus(...)**, **minus(...)**, **multipliedBy(...)**, **negated()**.
- **normalized()** và **toTotalMonths()**.

**Period là immutable và thread-safe**. Các phép tính trả một Period mới; không sửa đối tượng cũ.

### 4.1. Một tháng lịch không có số giây cố định

~~~java
LocalDate date = LocalDate.of(2024, 1, 31);
LocalDate next = date.plus(Period.parse("P1M"));

// next == 2024-02-29
~~~

Đây là đoạn minh họa cần import LocalDate/Period. Nếu dùng năm 2025, kết quả sẽ là **2025-02-28**.

**P1M không thể chuyển tổng quát thành PT720H**. Tháng có thể dài 28, 29, 30 hoặc 31 ngày; khi có múi giờ vùng, số giây từ một ngày-giờ sang cùng giờ ở tháng sau có thể còn chịu ảnh hưởng của DST.

### 4.2. Tuần trong Period

~~~java
Period weeks = Period.parse("P2W");

// weeks.toString() == "P14D"
// weeks.getDays() == 14
~~~

Java **quy đổi tuần thành ngày theo tỷ lệ bảy ngày/tuần** khi parse. Period không lưu trường weeks riêng. Do đó **toString không giữ nguyên chữ W**.

**Phân biệt chuẩn ISO và parser Java:** Java Period.parse có thể chấp nhận cả những kết hợp có tuần cùng năm/tháng/ngày mà một số biến thể ISO-8601 nghiêm ngặt không chấp nhận. Nếu API bên nhận yêu cầu đúng chuẩn ISO thuần, phải có giới hạn cú pháp rõ ràng.

### 4.3. Normalization của Period

~~~java
Period raw = Period.ofMonths(15);
Period normalized = raw.normalized();

// raw.toString()        == "P15M"
// normalized.toString() == "P1Y3M"
// raw.equals(normalized) == false
// raw.toTotalMonths()   == 15
~~~

**normalized() chỉ biến phần tháng thành năm/tháng**. Nó không đổi ngày thành tháng bởi số ngày của tháng không cố định. **toTotalMonths()** tính years×12 + months và **không tính phần days**.

**Period.equals so sánh các field**, không tự normalize trước, nên P15M và P1Y3M không bằng nhau ở cấp đối tượng mặc dù cùng tổng tháng.

## 5. Chương trình hoàn chỉnh: Period.parse và toString

Lưu thành **IsoPeriodDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.Period;

public class IsoPeriodDemo {
    public static void main(String[] args) {
        Period amount = Period.parse("P1Y2M3D");
        Period weeks = Period.parse("P2W");
        Period months = Period.ofMonths(15);

        System.out.println("period=" + amount);
        System.out.println("years=" + amount.getYears());
        System.out.println("months=" + amount.getMonths());
        System.out.println("days=" + amount.getDays());

        System.out.println("weeks=" + weeks);
        System.out.println("weekDays=" + weeks.getDays());

        System.out.println("raw=" + months);
        System.out.println("normalized=" + months.normalized());
        System.out.println("totalMonths=" + months.toTotalMonths());

        LocalDate januaryEnd = LocalDate.of(2024, 1, 31);
        LocalDate afterOneMonth =
                januaryEnd.plus(Period.parse("P1M"));

        System.out.println("afterOneMonth=" + afterOneMonth);
        System.out.println("original=" + januaryEnd);
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoPeriodDemo.java
java IsoPeriodDemo
~~~

**Stdout:**

~~~text
period=P1Y2M3D
years=1
months=2
days=3
weeks=P14D
weekDays=14
raw=P15M
normalized=P1Y3M
totalMonths=15
afterOneMonth=2024-02-29
original=2024-01-31
~~~

**Giải thích:** Period giữ các thành phần lịch. Khi cộng P1M vào ngày cuối tháng 1, Java điều chỉnh tới ngày hợp lệ cuối cùng của tháng 2. LocalDate gốc không đổi. Chuỗi P2W in lại thành P14D vì Period lưu số ngày chứ không lưu số tuần riêng.

## 6. Duration: giây và nanosecond

**java.time.Duration** là kiểu **time-based**. Nó biểu diễn một độ dài bằng hai thành phần **seconds/nanos**, thích hợp cho:

- Timeout 30 giây.
- Phiên truy cập còn hiệu lực 15 phút.
- SLA xử lý dưới hai giờ.
- Thời lượng thực giữa hai Instant.
- Phép cộng một số giờ cố định trên timeline.

Dạng parser thường nhận:

~~~text
PnDTnHnMn.nS
~~~

Ví dụ:

~~~java
Duration timeout = Duration.parse("PT15M");
Duration elapsed = Duration.parse("PT1H30M");
Duration twoDays = Duration.parse("P2D");
Duration fraction = Duration.parse("PT0.125S");
~~~

Đây là đoạn minh họa; cần import Duration.

**Đơn vị D trong Duration luôn là 24 giờ cố định**. Vì vậy P2D tương ứng đúng 48 giờ, không phải hai ngày dân sự với DST tại một vùng.

### 6.1. Duration.parse không nhận tháng/năm lịch

~~~java
Duration.parse("P1Y"); // DateTimeParseException
Duration.parse("P1M"); // DateTimeParseException
Duration.parse("P1W"); // DateTimeParseException
~~~

Các đoạn này cố ý thể hiện trường hợp lỗi:

- Năm/tháng không có số giây cố định.
- Duration.parse không hỗ trợ cú pháp tuần W của Period.parse.
- Để biểu diễn một phút, viết **PT1M**, không phải P1M.

### 6.2. Fractional seconds

~~~java
Duration fractional = Duration.parse("PT0.125S");

// fractional.getSeconds() == 0
// fractional.getNano()    == 125_000_000
~~~

Java Duration.parse hỗ trợ phần giây thập phân tới **9 chữ số** (nano resolution) và chấp nhận dấu phân cách phần thập phân là dấu chấm hoặc dấu phẩy. Khi thiết kế JSON/API, ưu tiên một biểu diễn canonical rõ ràng, thường dùng dấu **.**.

**Không nhầm khả năng biểu diễn nanosecond với độ phân giải thực tế của đồng hồ hoặc database**. Một hệ thống chỉ lưu millisecond có thể làm mất phần nano nhỏ hơn 1ms.

### 6.3. Duration.toString chuẩn hóa ngày thành giờ

~~~java
Duration.parse("P2D").toString(); // "PT48H"
Duration.parse("PT90S").toString(); // "PT1M30S"
Duration.ZERO.toString();          // "PT0S"
~~~

Duration không cần giữ số "ngày lịch" trong object; nó giữ seconds/nanos. Vì vậy in lại **P2D** thành **PT48H** là đúng theo thiết kế của Java.

## 7. Chương trình hoàn chỉnh: Duration ISO

Lưu thành **IsoDurationDemo.java**:

~~~java
import java.time.Duration;

public class IsoDurationDemo {
    public static void main(String[] args) {
        Duration mixed = Duration.parse("P2DT3H4M");
        Duration ninety = Duration.parse("PT90S");
        Duration fraction = Duration.parse("PT0.125S");

        System.out.println("mixed=" + mixed);
        System.out.println("mixedSeconds=" + mixed.getSeconds());
        System.out.println("ninety=" + ninety);
        System.out.println("fraction=" + fraction);
        System.out.println("fractionNanos=" + fraction.getNano());

        System.out.println("twoDays=" + Duration.ofDays(2));
        System.out.println("zero=" + Duration.ZERO);
        System.out.println("minute=" + Duration.parse("PT1M"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoDurationDemo.java
java IsoDurationDemo
~~~

**Stdout:**

~~~text
mixed=PT51H4M
mixedSeconds=183840
ninety=PT1M30S
fraction=PT0.125S
fractionNanos=125000000
twoDays=PT48H
zero=PT0S
minute=PT1M
~~~

**Giải thích phép tính:** P2DT3H4M = 2×86.400 + 3×3.600 + 4×60 = **183.840 giây**. Khi toString, phần ngày được gộp vào giờ: 48+3=51, nên **PT51H4M**.

**PT90S** có cùng giá trị với **PT1M30S** và được in theo dạng thứ hai. Đừng so sánh hai lượng thời gian bằng cách so thẳng raw string.

## 8. Bảng đối chiếu Period và Duration

| Tiêu chí | Period | Duration |
|---|---|---|
| Mô hình | Date-based | Time-based |
| Trường lưu | Năm, tháng, ngày | Seconds, nanoseconds |
| Chuỗi phổ biến | P1Y2M3D, P2W | PT1H30M, P2DT3H |
| Zero | P0D | PT0S |
| Parser | Period.parse(...) | Duration.parse(...) |
| Có tháng/năm lịch? | Có | Không |
| Có giờ/phút/giây? | Không | Có |
| Tuần ISO | P2W thành P14D | Không nhận W |
| Một ngày | Ngày theo lịch khi áp vào date/time | 86.400 giây |
| Dùng với | LocalDate, ZonedDateTime | Instant, ZonedDateTime |
| Bài toán | Gia hạn lịch, chu kỳ tháng | Timeout, elapsed time |
| toString | Dựa trên field lịch | Giờ/phút/giây, có thể đổi D thành giờ |

**Không ép chuyển đổi Period tháng/năm thành Duration** bằng một tỷ lệ cố định. Muốn biết Duration thật giữa hai thời điểm được tạo bằng Period, cần có **mốc bắt đầu và ZoneId** để tạo hai Instant, rồi đo Duration.between.

Ngược lại, không lấy một Duration 2.592.000 giây rồi tự gọi đó là "một tháng" nếu nghiệp vụ quy định gia hạn theo ngày tháng lịch.

## 9. Cùng P1D nhưng khác nhau khi DST

**Period.parse("P1D")** và **Duration.parse("P1D")** đều đọc được chuỗi, nhưng không có semantics giống nhau.

New York có chuyển giờ từ offset -05:00 sang -04:00 ngày **10/3/2024**. Bắt đầu từ **12:00 ngày 9/3/2024**:

- Cộng một **Period P1D**: cùng giờ đồng hồ **12:00 ngày 10/3**, chỉ cách **23 giờ thật**.
- Cộng một **Duration P1D**: tiến đúng **24 giờ**, tương ứng **13:00 ngày 10/3**.

Lưu thành **IsoDstDemo.java**:

~~~java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class IsoDstDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime before = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYork);

        ZonedDateTime byCalendar =
                before.plus(Period.parse("P1D"));

        ZonedDateTime bySeconds =
                before.plus(Duration.parse("P1D"));

        System.out.println("before=" + before);
        System.out.println("calendar=" + byCalendar);
        System.out.println("duration=" + bySeconds);

        System.out.println("calendarHours="
                + Duration.between(
                        before.toInstant(),
                        byCalendar.toInstant()).toHours());

        System.out.println("durationHours="
                + Duration.between(
                        before.toInstant(),
                        bySeconds.toInstant()).toHours());
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoDstDemo.java
java IsoDstDemo
~~~

**Stdout:**

~~~text
before=2024-03-09T12:00-05:00[America/New_York]
calendar=2024-03-10T12:00-04:00[America/New_York]
duration=2024-03-10T13:00-04:00[America/New_York]
calendarHours=23
durationHours=24
~~~

**Giải thích:** Period áp phép tính **theo ngày lịch địa phương**, còn Duration áp phép cộng chính xác seconds/nanos trên timeline. Nếu ngày đích rơi vào gap/overlap, ZonedDateTime còn phải dùng quy tắc giải quyết offset. Trong nghiệp vụ quốc tế, không thể suy ra số giây từ một ngày lịch mà không xác định ZoneId và mốc.

**Một field chứa chuỗi P1D chưa nói hết ý nghĩa.** Hợp đồng API phải quy định sẽ được xử lý như Period hay Duration.

## 10. Ngày cuối tháng và quy tắc gia hạn

Ví dụ:

~~~text
2024-01-31 + P1M = 2024-02-29
2025-01-31 + P1M = 2025-02-28
2024-02-29 + P1Y = 2025-02-28
~~~

Đây là quy tắc điều chỉnh ngày hợp lệ khi cộng **Period** trên LocalDate. Vì mỗi tháng khác độ dài, **cộng P1M hai lần** không nhất thiết giống **cộng P2M một lần**:

~~~text
2024-01-31 + P1M   = 2024-02-29
2024-02-29 + P1M   = 2024-03-29
2024-01-31 + P2M   = 2024-03-31
~~~

Nếu nghiệp vụ cần **ngày cuối cùng mỗi tháng**, hãy quản lý quy tắc đó riêng, ví dụ bằng **YearMonth.atEndOfMonth()**. **P1M tự thân không định nghĩa cách tính chu kỳ thuê bao lặp lại**, nó chỉ là một calendar amount.

## 11. Parser Java hỗ trợ tập cú pháp riêng, không phải toàn bộ ISO-8601

**Period.parse** đọc years/months/weeks/days. **Duration.parse** đọc days/hours/minutes/seconds với ngày cố định 24 giờ. Một số biểu thức có **cả năm, tháng, ngày, giờ, phút, giây** trong định dạng ISO tổng quát **không thể được giữ nguyên bằng một trong hai lớp Java**.

Ví dụ:

~~~text
P1Y2M3DT4H5M6S
~~~

Với yêu cầu cần cả calendar amount và elapsed duration, một ứng dụng có thể dùng hai field:

~~~json
{
  "calendarPeriod": "P1Y2M3D",
  "timeDuration": "PT4H5M6S"
}
~~~

Đây là **hợp đồng ứng dụng minh họa**, không phải một kiểu chung có sẵn tên ISOAmount. Cần xác định **thứ tự áp dụng** calendar Period rồi Duration hay ngược lại; ở gần DST, thứ tự có thể ảnh hưởng tới kết quả.

### 11.1. Period.parse: những trường hợp được/không được

~~~text
P1Y         Hợp lệ: một năm
P3M         Hợp lệ: ba tháng
P2W         Hợp lệ: hai tuần, Java đổi thành P14D
P1Y2M3D     Hợp lệ: năm, tháng, ngày
PT1M        Không hợp lệ: phút, không phải Period
P1.5M       Không hợp lệ trong Java Period.parse
~~~

**Java Period.parse có một số phần mở rộng ngoài biến thể ISO nghiêm ngặt**, bao gồm cú pháp dấu âm/dương theo từng thành phần và một số tổ hợp chứa tuần. Không dựa vào việc Java parser chấp nhận để khẳng định mọi sản phẩm hoặc parser ISO khác cũng chấp nhận.

### 11.2. Duration.parse: những trường hợp được/không được

~~~text
PT15M       Hợp lệ: 15 phút
PT0.125S    Hợp lệ: 0,125 giây
P2D         Hợp lệ: 48 giờ
P2DT3H4M    Hợp lệ: 51 giờ 4 phút
P1Y         Không hợp lệ trong Duration.parse
P1M         Không hợp lệ: một tháng
P1W         Không hợp lệ trong Duration.parse
~~~

Duration.parse cho phép phần giây dạng thập phân **tối đa 9 chữ số**. Cũng có các dạng dấu âm/dương mà Java hỗ trợ nhưng không thuộc mọi biểu diễn strict ISO. Nếu API công khai cần strict format, phải có kiểm tra chính sách bổ sung.

### 11.3. Tự kiểm tra bằng chương trình Java

Lưu thành **IsoValidationDemo.java**:

~~~java
import java.time.Duration;
import java.time.Period;
import java.time.format.DateTimeParseException;

public class IsoValidationDemo {
    static void period(String text) {
        try {
            System.out.println("period " + text + "="
                    + Period.parse(text));
        } catch (DateTimeParseException exception) {
            System.out.println("period " + text + "=INVALID");
        }
    }

    static void duration(String text) {
        try {
            System.out.println("duration " + text + "="
                    + Duration.parse(text));
        } catch (DateTimeParseException exception) {
            System.out.println("duration " + text + "=INVALID");
        }
    }

    public static void main(String[] args) {
        period("P1M");
        period("PT1M");
        period("P2W");
        period("P1.5M");

        duration("PT1M");
        duration("P1M");
        duration("P1D");
        duration("P1W");
        duration("P1Y");
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoValidationDemo.java
java IsoValidationDemo
~~~

**Stdout:**

~~~text
period P1M=P1M
period PT1M=INVALID
period P2W=P14D
period P1.5M=INVALID
duration PT1M=PT1M
duration P1M=INVALID
duration P1D=PT24H
duration P1W=INVALID
duration P1Y=INVALID
~~~

**Lưu ý:** DateTimeParseException là lỗi phổ biến khi chuỗi không parse được. Khi lượng số vượt phạm vi kiểu hoặc phép toán gặp overflow, các phương thức khác có thể ném ArithmeticException hay DateTimeException tùy ngữ cảnh. Xác định chính sách lỗi ở tầng API thay vì để một chuỗi sai gây lỗi không được kiểm soát.

## 12. Zero, dấu âm, precision và tính bất biến

### 12.1. Giá trị zero

~~~java
Period.ZERO.toString();   // "P0D"
Duration.ZERO.toString(); // "PT0S"
~~~

Cả hai đều bằng zero nhưng là hai loại lượng thời gian khác nhau. Một SLA có thể cần **Duration không âm**, còn một gia hạn lịch có thể quy định **Period không được bằng zero**.

### 12.2. Lượng âm

**Period** và **Duration** hỗ trợ giá trị có hướng, gồm âm:

~~~java
Duration delta = Duration.between(end, start);
boolean negative = delta.isNegative();
~~~

Đây là đoạn minh họa với start/end là Instant đã khai báo.

**Không mặc định mọi hệ thống chấp nhận cùng cú pháp số âm**. Một số dạng dấu mà Java parse chấp nhận là phần mở rộng. Nếu API yêu cầu strict ISO, chỉ cho phép tập cú pháp đã thống nhất.

### 12.3. Phần giây dưới một giây

~~~java
Duration d = Duration.parse("PT0.125S");

// d.getSeconds() == 0
// d.getNano() == 125_000_000
~~~

Khi cần giữ nanosecond, không chuyển qua **double** hoặc epoch-millis rồi mong khôi phục chính xác mọi bit. Độ phân giải lớp Java không đồng nghĩa độ chính xác của clock hoặc database.

### 12.4. Immutable và so sánh giá trị

~~~java
Duration original = Duration.parse("PT15M");
Duration next = original.plusSeconds(30);

// original vẫn là PT15M
// next là PT15M30S
~~~

Không sửa object gốc. Để kiểm tra cùng giá trị Duration/Period, dùng **equals**, không dùng **==**. Với Period, nhớ rằng equals so sánh các field và không tự normalized.

## 13. toString và round-trip không giữ nguyên văn bản đầu vào

Các phép chuyển:

~~~text
Period.parse("P2W").toString()    → P14D
Duration.parse("P2D").toString()  → PT48H
Duration.parse("PT90S").toString() → PT1M30S
Period.ofMonths(15).toString()   → P15M
Period.ofMonths(15).normalized() → P1Y3M
~~~

**Giá trị** có thể round-trip:

~~~java
Duration original = Duration.parse("PT90S");
String canonical = original.toString();

boolean sameValue =
        Duration.parse(canonical).equals(original);

// sameValue == true
~~~

Nhưng **"PT90S".equals(canonical)** là false.

Nếu hệ thống phải **audit chính xác người dùng đã nhập P2W hay P14D**, hãy lưu raw string riêng. Nếu muốn cache/deduplicate theo giá trị, làm việc trên object đã parse hoặc áp quy tắc canonical hóa đúng loại.

**Không tự normalize Period sang số giây.** normalized() chỉ điều chỉnh các field năm và tháng, không diễn giải số ngày theo một tháng cụ thể.

## 14. ISO ngày và giờ trong java.time

Ngoài khoảng thời gian, Java hỗ trợ nhiều định dạng ISO cho mốc thời gian:

| Chuỗi | Kiểu Java | Cách đọc |
|---|---|---|
| **2026-01-02** | LocalDate | LocalDate.parse |
| **09:30:00** | LocalTime | LocalTime.parse |
| **2026-01-02T09:30:00** | LocalDateTime | LocalDateTime.parse |
| **2026-01-02T09:30:00+07:00** | OffsetDateTime | OffsetDateTime.parse |
| **2026-01-02T02:30:00Z** | Instant | Instant.parse |
| **2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]** | ZonedDateTime | ZonedDateTime.parse |
| **P1M** | Period | Period.parse |
| **PT1M** | Duration | Duration.parse |

**DateTimeFormatter.ISO_LOCAL_DATE**, **ISO_LOCAL_DATE_TIME**, **ISO_OFFSET_DATE_TIME**, **ISO_ZONED_DATE_TIME** và **ISO_INSTANT** là formatter cho ngày-giờ, không thay thế parser lượng thời gian.

### 14.1. Chữ Z và offset

~~~text
2026-01-02T02:30:00Z
2026-01-02T09:30:00+07:00
~~~

Hai timestamp trên biểu diễn **cùng Instant**, vì 09:30 ở offset +07:00 tương đương 02:30 UTC.

**Z** biểu diễn zero offset ở ngữ cảnh timestamp; nó khác với chữ **P** mở đầu period/duration.

### 14.2. Region zone trong ngoặc vuông là phần mở rộng ISO-like của Java

~~~text
2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
~~~

**DateTimeFormatter.ISO_ZONED_DATE_TIME** của Java sử dụng ký pháp thêm region ZoneId trong ngoặc vuông, **không phải cú pháp ISO-8601 thuần**. Nếu trao đổi với hệ thống không dùng Java, bên nhận có thể không hỗ trợ dạng này.

Không nhầm **ZoneId vùng** với offset cố định. Region ZoneId có quy tắc thay đổi offset theo thời gian, quan trọng với lịch hẹn và DST.

### 14.3. YYYY không phải năm lịch thông thường

Khi dùng formatter tùy biến cho ngày ISO, phân biệt:

- **uuuu**: proleptic year.
- **yyyy**: year-of-era.
- **YYYY**: week-based-year, có thể lệch ở tuần đầu/cuối năm.
- **MM**: tháng; **mm**: phút.

Với parsing ngày nghiêm ngặt, dùng **DateTimeFormatter.ISO_LOCAL_DATE** hoặc mẫu thích hợp với **uuuu** và **ResolverStyle.STRICT**. Những chi tiết này là phần **ngày/giờ** của ISO, không phải parser Period/Duration.

## 15. Ví dụ chạy đầy đủ: mốc ISO và cùng Instant

Lưu thành **IsoTimestampDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class IsoTimestampDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.parse(
                "2026-01-02",
                DateTimeFormatter.ISO_LOCAL_DATE);

        Instant instant = Instant.parse(
                "2026-01-02T02:30:00Z");

        OffsetDateTime offset = OffsetDateTime.parse(
                "2026-01-02T09:30:00+07:00",
                DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        ZonedDateTime zoned = ZonedDateTime.parse(
                "2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]",
                DateTimeFormatter.ISO_ZONED_DATE_TIME);

        System.out.println("date=" + date);
        System.out.println("instant=" + instant);
        System.out.println("offsetInstant="
                + offset.toInstant());
        System.out.println("zonedInstant="
                + zoned.toInstant());
        System.out.println("sameInstant="
                + instant.equals(zoned.toInstant()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoTimestampDemo.java
java IsoTimestampDemo
~~~

**Stdout:**

~~~text
date=2026-01-02
instant=2026-01-02T02:30:00Z
offsetInstant=2026-01-02T02:30:00Z
zonedInstant=2026-01-02T02:30:00Z
sameInstant=true
~~~

**Giải thích:** Date-only chỉ là một ngày lịch; các chuỗi date-time có Z/offset cung cấp điểm trên timeline. Khi chuyển đổi múi giờ chỉ thay cách hiển thị, không làm biến đổi Instant của một sự kiện.

## 16. ISO intervals và dấu /

ISO-8601 có cú pháp interval thường dùng dấu **/** để phân tách các phần, ví dụ:

~~~text
start/end
start/duration
duration/end

2026-01-01/2026-02-01
2026-01-01/P31D
P31D/2026-02-01
~~~

**Một interval không phải một Period hoặc Duration**. Nó còn cần mốc bắt đầu/kết thúc và quy tắc diễn giải, đặc biệt nếu mốc là ngày-giờ địa phương.

Thư viện **java.time chuẩn không có một parser Interval tổng quát** tự nhận mọi biến thể kể trên và cung cấp một lớp Interval duy nhất. Khi xây API:

1. Chọn **LocalDate** nếu khoảng là các ngày lịch.
2. Chọn **Instant** nếu khoảng là các thời điểm tuyệt đối.
3. Parse/validate ranh giới.
4. Quy định **biên bắt đầu bao gồm hay không, biên kết thúc bao gồm hay không**.
5. Chỉ áp dụng **Period/Duration** khi đầu vào có lượng thời gian và cách cộng rõ ràng.

### 16.1. Quy ước [startInclusive, endExclusive)

Một cách hữu ích trong hệ thống là:

~~~text
[2026-01-01, 2026-02-01)

Bao gồm ngày 01/01/2026.
Không bao gồm ngày 01/02/2026.
Có 31 ngày lịch.
~~~

Đây là **quy ước nghiệp vụ của ứng dụng**, không phải tuyên bố rằng mọi chuỗi ISO interval tự có biên y hệt. End-exclusive giúp ghép các kỳ cạnh nhau mà không chồng biên.

### 16.2. Ví dụ đầy đủ: parse hai ranh giới ngày

Lưu thành **IsoIntervalDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

public class IsoIntervalDemo {
    static boolean contains(
            LocalDate day,
            LocalDate startInclusive,
            LocalDate endExclusive) {

        return !day.isBefore(startInclusive)
                && day.isBefore(endExclusive);
    }

    public static void main(String[] args) {
        String text = "2026-01-01/2026-02-01";

        String[] tokens = text.split("/", -1);

        if (tokens.length != 2) {
            throw new IllegalArgumentException("Invalid interval");
        }

        LocalDate start = LocalDate.parse(tokens[0]);
        LocalDate end = LocalDate.parse(tokens[1]);

        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("Invalid range");
        }

        System.out.println("start=" + start);
        System.out.println("endExclusive=" + end);
        System.out.println("days="
                + ChronoUnit.DAYS.between(start, end));

        System.out.println("jan31="
                + contains(LocalDate.of(2026, 1, 31), start, end));

        System.out.println("atEnd="
                + contains(end, start, end));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IsoIntervalDemo.java
java IsoIntervalDemo
~~~

**Stdout:**

~~~text
start=2026-01-01
endExclusive=2026-02-01
days=31
jan31=true
atEnd=false
~~~

Ví dụ chỉ giải mã dạng **start/end gồm hai LocalDate**. Nó không tự hỗ trợ **start/duration**, **duration/end** hay repeating interval. Với yêu cầu API cụ thể, giới hạn cú pháp rõ ràng là một lợi thế cho validation.

### 16.3. Repeating interval và ký hiệu R

ISO-8601 còn có biểu diễn interval lặp lại ở những biến thể phù hợp, thường có ký hiệu **R**. Điều đó không khiến **Period.parse** hoặc **Duration.parse** tự trở thành scheduler.

Một lịch lặp còn cần số lần, giờ địa phương, ZoneId, quy tắc DST (gap/overlap), ngày kết thúc, cơ chế retry và tránh chạy lặp. Không tự đưa chuỗi **R...** vào parser Period/Duration rồi mong thu được lịch trình hoàn chỉnh.

## 17. Các tình huống nghiệp vụ

### 17.1. Timeout sau 15 phút

~~~java
Instant createdAt =
        Instant.parse("2026-01-01T10:00:00Z");

Duration ttl = Duration.parse("PT15M");
Instant expiresAt = createdAt.plus(ttl);

// expiresAt == 2026-01-01T10:15:00Z
~~~

Đây là đoạn minh họa. **TTL 15 phút** có ý nghĩa độ dài cố định, phù hợp Duration. Không cần ZoneId để cộng vào Instant.

### 17.2. Gia hạn một tháng lịch

~~~java
LocalDate due = LocalDate.of(2024, 1, 31);
LocalDate next = due.plus(Period.parse("P1M"));

// next == 2024-02-29
~~~

Nếu nghiệp vụ đòi hết hạn "đầu ngày kế tiếp theo giờ Hà Nội", cần thêm **ZoneId** và quy tắc ranh giới ngày. Period không tự xác định giờ nào kỳ mới bắt đầu.

### 17.3. Đúng 24 giờ hay sang ngày mai?

| Nhu cầu | Nên dùng |
|---|---|
| "Đúng 24 giờ sau thời điểm này" | **Duration.ofHours(24)** |
| "Cùng giờ đồng hồ ngày mai tại New York" | **ZonedDateTime.plusDays(1)** |
| "Đầu ngày mai theo vùng của khách hàng" | **LocalDate.plusDays(1).atStartOfDay(zone)** |
| "Một tháng lịch sau" | **Period.ofMonths(1)** và mốc lịch |
| "Chạy mỗi ngày làm việc" | Quy tắc calendar ngày làm việc riêng, không chỉ Duration |

**Không coi ISO-8601 duration là định nghĩa đầy đủ của mọi lịch chạy lặp.**

## 18. Những lỗi thường gặp

### Lỗi 1 — Nhầm một tháng với một phút

~~~text
P1M  = 1 tháng
PT1M = 1 phút
~~~

Dấu T quyết định ý nghĩa của M. Không đoán đơn vị chỉ từ chữ cuối chuỗi.

### Lỗi 2 — Dùng Duration để parse năm/tháng lịch

~~~java
Duration.parse("P1M"); // DateTimeParseException
~~~

Dùng **Period.parse("P1M")**.

### Lỗi 3 — Dùng Period để parse phút

~~~java
Period.parse("PT1M"); // DateTimeParseException
~~~

Dùng **Duration.parse("PT1M")**.

### Lỗi 4 — Coi mọi P1D là một ngày địa phương

**Duration.parse("P1D")** là 24 giờ cố định, còn **Period.parse("P1D")** là một ngày lịch khi cộng trên loại temporal phù hợp. Qua DST hai kết quả có thể khác.

### Lỗi 5 — Tự đổi tháng thành 30 ngày

Tháng có độ dài biến đổi. Với calendar period, cần mốc bắt đầu, và đôi khi cả ZoneId, để xác định elapsed time chính xác.

### Lỗi 6 — Dựa vào toString để giữ nguyên cách người dùng nhập

Period P2W thành P14D; Duration P2D thành PT48H. Muốn audit input gốc, lưu raw string riêng.

### Lỗi 7 — Cho rằng Period.normalized() đổi ngày thành tháng

Phương thức chỉ normalize các field năm/tháng. Không thể đổi số ngày thành số tháng tổng quát.

### Lỗi 8 — Coi P1Y2M3DT4H là một Period hoàn chỉnh

Period không lưu H/M/S; Duration không lưu Y/month. Muốn kết hợp phải có kiểu dữ liệu hoặc hợp đồng có hai phần.

### Lỗi 9 — Dùng DateTimeFormatter.ISO_INSTANT để parse Duration

ISO_INSTANT dùng cho **timestamp**; lượng thời gian dùng **Duration.parse** hoặc **Period.parse**.

### Lỗi 10 — Truyền LocalDateTime thiếu offset như timestamp tuyệt đối

~~~text
2026-01-02T09:30
~~~

Chưa đủ xác định Instant; cần offset/zone. Nếu hệ thống chọn UTC, đó phải là quyết định được nêu rõ trong contract.

### Lỗi 11 — Cho rằng [Europe/Paris] là ISO thuần được mọi parser chấp nhận

Đây là extension ISO-like của Java; cần kiểm thử tích hợp bên nhận.

### Lỗi 12 — Dùng raw string equality để xác định cùng giá trị

**PT90S** và **PT1M30S** cùng lượng Duration. Parse và so giá trị.

### Lỗi 13 — Bỏ qua zero, dấu âm và overflow

Một Duration âm hoặc zero có thể parse hợp lệ nhưng không hợp lệ với SLA/TTL nghiệp vụ. Kiểm tra lượng hợp lệ và miền dữ liệu.

### Lỗi 14 — Regex đơn giản thay hết parser chuẩn

Regex tự viết dễ bỏ sót thứ tự field, precision, dấu và giới hạn giá trị. Dùng parser Java, sau đó validate chính sách strict ISO mà ứng dụng yêu cầu.

### Lỗi 15 — Dùng chuỗi interval rồi tự ngầm coi endInclusive

Quy định rõ [start,end), [start,end], hoặc quy tắc khác; không suy đoán từ dấu /.

### Lỗi 16 — Ghi số epoch mà không có đơn vị

Epoch seconds/milliseconds là timestamp số; không phải chuỗi Period/Duration. Nếu API dùng số, schema phải ghi rõ đơn vị.

### Lỗi 17 — Cho rằng một lần parse thành công nghĩa là strict ISO ở mọi hệ thống

Java parser có các phần mở rộng ngoài ISO nghiêm ngặt. API liên hệ thống phải thống nhất tập cú pháp và phiên bản.

### Lỗi 18 — Dùng Duration để đại diện quy tắc chạy hàng tháng

Chu kỳ calendar month cần Period, mốc lịch và ZoneId nếu phát sinh lịch tại một địa điểm.

## 19. Checklist kiểm thử trước khi đưa vào production

| Bài test | Giá trị hoặc kết quả cần kiểm tra |
|---|---|
| Period cơ bản | P1Y2M3D → years=1, months=2, days=3 |
| Tuần | Period.parse P2W → P14D |
| Tháng/phút | P1M khác PT1M |
| Duration seconds | PT90S → PT1M30S |
| Duration days | P2D → PT48H |
| Fractional seconds | PT0.125S → 125.000.000 nano |
| Parse lỗi | Period.parse PT1M; Duration.parse P1M |
| Normalization | P15M.normalized → P1Y3M |
| Zero | Period.ZERO = P0D, Duration.ZERO = PT0S |
| Ngày cuối tháng | 2024-01-31 + P1M → 2024-02-29 |
| DST | Period P1D = 23h vs Duration P1D = 24h trong ví dụ |
| ISO date/time | Offset +07 tương đương Z theo Instant |
| Interval date-only | [2026-01-01,2026-02-01) có 31 ngày |
| Round-trip | Parse → toString → parse giữ **giá trị**, không nhất thiết giữ raw text |
| Tương thích hệ thống khác | Week/sign/region zone có được bên nhận chấp nhận không? |
| Security/validation | Input quá dài, số quá lớn, zero/negative, format không hợp đồng |

### 19.1. Hợp đồng API nên trả lời được gì?

1. Đây là **calendarPeriod** hay **elapsedDuration**?
2. Dạng ISO nào được hỗ trợ: có Y/M/W/D hay chỉ H/M/S?
3. Có cho phép số âm và zero không?
4. Cho phép precision tới nano hay chỉ milli?
5. Có cần giữ raw string vì audit/chữ ký số không?
6. Nếu phải tính Instant từ Period, mốc start và ZoneId nào được dùng?
7. Nếu dữ liệu là interval, start/end có quy tắc bao gồm như thế nào?
8. Parser Java có thể nhận extension nhưng đối tác ISO strict có chấp nhận không?
9. Có yêu cầu chống overflow không?
10. Khi có DST và tháng cuối tháng, cách tính của nghiệp vụ là gì?

## 20. Bài tập tự kiểm tra

**Câu 1.** Trong cú pháp amount ISO, chữ P đại diện điều gì?

**Câu 2.** Chữ T có vai trò gì trong PT1H30M?

**Câu 3.** P1M và PT1M lần lượt là gì?

**Câu 4.** Java Period.parse("P2W").toString() cho kết quả gì?

**Câu 5.** Java Duration.parse("P2D").toString() cho kết quả gì?

**Câu 6.** Có thể đổi P1M thành số giây cố định đúng cho mọi tháng không?

**Câu 7.** Period.ofMonths(15).normalized() cho kết quả gì?

**Câu 8.** Duration.parse("PT0.125S").getNano() bằng bao nhiêu?

**Câu 9.** Duration.parse("P1M") có chạy thành công không?

**Câu 10.** Period.parse("PT1M") có chạy thành công không?

**Câu 11.** Duration.parse("PT90S").toString() trả gì?

**Câu 12.** Ở New York ngày chuyển DST tháng 3/2024, cộng một Period P1D khác một Duration P1D như thế nào?

**Câu 13.** Chuỗi 2026-01-02T09:30:00 đã có đủ thông tin để xác định Instant chưa?

**Câu 14.** Chuỗi 2026-01-02T09:30:00+07:00 đã xác định Instant chưa?

**Câu 15.** Chuỗi vùng [Asia/Ho_Chi_Minh] có thuộc ISO-8601 thuần không?

**Câu 16.** Java có parser Interval tích hợp đọc mọi biến thể start/end, start/duration và repeating interval không?

**Câu 17.** Trong [2026-01-01,2026-02-01), ngày 1/2 có được tính không, số ngày là bao nhiêu?

**Câu 18.** Vì sao P12M và P1Y có thể không bằng nhau theo Period.equals dù cùng tổng tháng?

**Câu 19.** Một timeout 15 phút nên là PT15M hay P15M?

**Câu 20.** Có thể gửi nguyên mọi chuỗi Java Period.parse chấp nhận cho một đối tác chỉ nhận strict ISO mà không kiểm tra thêm không?

### Đáp án

1. **Bắt đầu biểu diễn lượng thời gian**.
2. **Phân tách phần giờ/phút/giây**; M sau T là phút.
3. **Một tháng lịch** và **một phút**.
4. **P14D**.
5. **PT48H**.
6. **Không**, tháng thay đổi độ dài theo lịch.
7. **P1Y3M**.
8. **125.000.000 nanoseconds**.
9. **Không**, vì M trước T là tháng và Duration không lưu tháng.
10. **Không**, vì Period không lưu phút.
11. **PT1M30S**.
12. **Period** giữ cách cộng ngày lịch và có thể cách 23 giờ; **Duration** cộng 24 giờ cố định, giờ địa phương có thể lệch.
13. **Chưa**, thiếu offset hoặc ZoneId.
14. **Có**, offset xác định thời điểm trên timeline.
15. **Không**; cách gắn region zone trong ngoặc vuông là ISO-like extension của Java.
16. **Không** trong thư viện java.time chuẩn.
17. **Không**; có **31 ngày**.
18. **equals so các field** chứ không tự normalized.
19. **PT15M**, vì đây là 15 phút, không phải 15 tháng.
20. **Không**; phải xác nhận tập cú pháp hai bên thực sự hỗ trợ.

## 21. Tổng kết

**ISO-8601** cung cấp một cách biểu diễn có cấu trúc cho ngày, giờ, lượng thời gian và interval. Riêng với **khoảng thời gian trong Java**:

- **Period** là lượng **năm/tháng/ngày lịch**.
- **Duration** là lượng **seconds/nanos**, có ngày được hiểu là 24 giờ.
- **P1M = một tháng; PT1M = một phút**.
- **P1D dưới dạng Period** khác **P1D dưới dạng Duration** khi áp vào ZonedDateTime qua DST.
- **toString()** có thể chuẩn hóa cách viết: **P2W → P14D**, **P2D → PT48H**, **PT90S → PT1M30S**.
- Java parser chỉ hỗ trợ **các tập con và một số mở rộng** của ký pháp ISO-8601 tổng quát; không dùng nó như chứng minh rằng đối tác strict ISO sẽ hiểu mọi chuỗi.
- **Date/time string**, **temporal amount string** và **interval** là những đối tượng ngữ nghĩa khác nhau.
- Khi tích hợp, ghi rõ kiểu dữ liệu, đơn vị, precision, zone, DST, policy âm/zero và quy tắc ranh giới.

### Tài liệu chính thức còn áp dụng trong Java hiện hành

- [Period — Java SE 26: parse, normalized, calendar-based amount](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
- [Duration — Java SE 26: parse, seconds/nanos, toString và ngày cố định](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [DateTimeFormatter — Java SE 26: ISO_LOCAL_DATE, ISO_OFFSET_DATE_TIME, ISO_INSTANT, ISO_ZONED_DATE_TIME](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [LocalDate — Java SE 26: cộng Period và ngày cuối tháng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html)
- [Instant — Java SE 26: timestamp và timeline](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [ZonedDateTime — Java SE 26: phép cộng lịch so với Duration và DST](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [DateTimeParseException — Java SE 26: parse failure](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeParseException.html)
