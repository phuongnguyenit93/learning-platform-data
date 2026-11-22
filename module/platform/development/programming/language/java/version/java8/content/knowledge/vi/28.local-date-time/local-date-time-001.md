# LocalDate và ngày không gắn múi giờ trong Java

**Chủ đề:** Java 8 → Ngày giờ cục bộ → LocalDate và ngày không gắn múi giờ.

**java.time.LocalDate** biểu diễn **một ngày theo lịch ISO-8601**, gồm **năm, tháng, ngày**. Nó **không chứa giờ, phút, giây, độ lệch UTC (offset), múi giờ (ZoneId) hoặc một thời điểm tuyệt đối (Instant)**. Vì vậy, cùng một giá trị **2026-01-02** có thể là ngày sinh, ngày hẹn, ngày lập hóa đơn hoặc ngày bắt đầu một kỳ — nhưng **chưa thể suy ra một timestamp** chỉ từ giá trị này.

LocalDate được giới thiệu cùng API **java.time** từ Java 8 và vẫn là lựa chọn hiện đại cho dữ liệu **date-only**. Ví dụ trong bài dùng **Java 17+** để có thể sử dụng **List.of(...)**, **record** hoặc **Stream.toList()** khi tiện; chính **LocalDate** không đòi Java 17.

**Điều cốt lõi:** LocalDate là **ngày không gắn múi giờ**, nhưng **việc tính ngày hiện tại từ đồng hồ** hay **chuyển một thời điểm Instant sang ngày địa phương** lại **phải xét múi giờ**. Hai điều này không mâu thuẫn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa **LocalDate**, **LocalTime**, **LocalDateTime**, **ZonedDateTime**, **OffsetDateTime** và **Instant**.
2. Tạo LocalDate bằng **of(...)**, **parse(...)**, **ofEpochDay(...)** và lấy ngày hiện tại bằng **now(...)** có kiểm soát ZoneId/Clock.
3. Đọc năm, tháng, ngày trong tháng, ngày trong tuần; xử lý năm nhuận và ngày không hợp lệ.
4. Dùng **plusDays**, **minusDays**, **plusMonths**, **plusYears**, **with(...)** mà không nghĩ rằng đối tượng ban đầu bị sửa.
5. Phân biệt **số ngày giữa hai ngày** với **Period năm/tháng/ngày** và với thời lượng **Duration** trên trục thời gian.
6. Parse/format ngày theo ISO hoặc định dạng tùy biến với **DateTimeFormatter** và **ResolverStyle.STRICT**.
7. Hiểu cách kết hợp **LocalDate + giờ + ZoneId** để tạo **ZonedDateTime/Instant**, bao gồm rủi ro daylight saving time (DST).
8. Chọn LocalDate cho bài toán nghiệp vụ date-only, tránh lỗi lệch ngày khi lưu trữ, API hoặc chuyển múi giờ.

## 2. Mô hình tư duy: ngày theo lịch khác thời điểm tuyệt đối

Hãy so sánh:

~~~text
LocalDate
2026-01-02
  └── Năm / tháng / ngày theo lịch ISO
      Không có giờ, offset, zone, timestamp.

LocalDateTime
2026-01-02T09:30:00
  └── Ngày và giờ địa phương; chưa có zone/offset.

ZonedDateTime
2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
  └── Ngày, giờ, zone ID và offset được xác định theo zone rules.

OffsetDateTime
2026-01-02T09:30+07:00
  └── Ngày, giờ và offset; không mang region ZoneId.

Instant
2026-01-02T02:30:00Z
  └── Một điểm trên UTC timeline.
~~~

Các giá trị trên chỉ là **minh họa cho những kiểu khác nhau**; cùng giá trị ngày giờ cục bộ chưa thể tự suy ra offset nếu không có quy tắc zone.

| Kiểu | Chứa gì? | Dùng khi nào? |
|---|---|---|
| **LocalDate** | Năm/tháng/ngày ISO | Sinh nhật, ngày đáo hạn, ngày giao hàng, ngày hiệu lực |
| **LocalTime** | Giờ/phút/giây, không có ngày/zone | Giờ mở cửa theo đồng hồ địa phương |
| **LocalDateTime** | Ngày + giờ cục bộ, không có zone | Lịch hẹn theo giờ địa phương **khi zone được quản lý riêng** |
| **ZonedDateTime** | Ngày giờ gắn **ZoneId** và offset được giải quyết | Lịch hẹn tại một địa điểm có quy tắc múi giờ |
| **OffsetDateTime** | Ngày giờ + offset | Dữ liệu timestamp kèm UTC offset, khi không cần region rules |
| **Instant** | Thời điểm tuyệt đối trên UTC timeline | Log, audit, sự kiện, mốc bắt đầu/kết thúc chính xác |

**Ví dụ nghiệp vụ:** Một người sinh ngày **1998-07-15** — đây là LocalDate. Không nên tự thêm **00:00 UTC** vào ngày sinh rồi chuyển zone, vì khi hiển thị ở vùng có offset âm, nó có thể thành **1998-07-14**. Bản thân ngày sinh không phải một Instant.

Ngược lại, sự kiện xảy ra vào **2026-01-01T23:30:00Z** là một Instant. Ở UTC đó là ngày **2026-01-01**, nhưng tại **Asia/Ho_Chi_Minh** đã là **2026-01-02**. Nếu muốn rút ra **ngày địa phương của sự kiện**, phải chỉ định zone.

### 2.1. LocalDate dùng lịch nào?

**LocalDate** dùng **hệ lịch ISO-8601** theo mô hình **proleptic Gregorian** của Java, kể cả những năm lịch sử trước khi lịch Gregorian thực tế được áp dụng. Nó không tự đổi sang lịch âm, lịch Phật giáo hoặc lịch khác theo **Locale** của người dùng.

**Locale** có thể thay đổi cách **hiển thị** một LocalDate; **ZoneId** có thể dùng khi **xác định ngày từ một thời điểm**; còn ba trường năm/tháng/ngày đã lưu trong LocalDate vẫn là các trường của lịch ISO.

## 3. Tạo LocalDate: of, parse, ofEpochDay

Các cách thường dùng:

~~~java
LocalDate a = LocalDate.of(2024, 2, 29);
LocalDate b = LocalDate.of(2024, Month.FEBRUARY, 29);
LocalDate c = LocalDate.parse("2024-02-29");

LocalDate epochDate = LocalDate.ofEpochDay(0);
~~~

Đây là **đoạn minh họa**, cần import **java.time.LocalDate** và **java.time.Month**.

- **of(year, month, day)** yêu cầu ba thành phần hợp lệ theo lịch ISO.
- **of(year, Month, day)** cho phép dùng enum **Month** thay số nguyên tháng.
- **parse(text)** mặc định đọc dạng **ISO local date**, thường là **yyyy-MM-dd** đối với năm hiện đại như 2024 (ví dụ **2024-02-29**).
- **ofEpochDay(0)** tạo **1970-01-01** theo số **ngày lịch** tính từ mốc epoch; **không** có nghĩa đối tượng chứa một Instant.
- **LocalDate.EPOCH** là hằng ngày **1970-01-01**; có thể dùng thay **ofEpochDay(0)** khi phù hợp.

**Không viết** **LocalDate.of(2025, 2, 29)** rồi mong Java tự đổi sang 1/3/2025. Ngày 29/2/2025 không tồn tại; factory sẽ ném **DateTimeException**. Parse văn bản tương ứng sẽ ném **DateTimeParseException**.

### 3.1. Ví dụ đầy đủ: thông tin của một ngày

Lưu thành **LocalDateBasicsDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.Month;

public class LocalDateBasicsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, Month.FEBRUARY, 29);
        LocalDate parsed = LocalDate.parse("2024-02-29");

        System.out.println("date=" + date);
        System.out.println("same=" + date.equals(parsed));
        System.out.println("year=" + date.getYear());
        System.out.println("month=" + date.getMonth());
        System.out.println("monthValue=" + date.getMonthValue());
        System.out.println("day=" + date.getDayOfMonth());
        System.out.println("dayOfYear=" + date.getDayOfYear());
        System.out.println("dayOfWeek=" + date.getDayOfWeek());
        System.out.println("leap=" + date.isLeapYear());
        System.out.println("monthLength=" + date.lengthOfMonth());
        System.out.println("epoch=" + LocalDate.EPOCH);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocalDateBasicsDemo.java
java LocalDateBasicsDemo
~~~

**Stdout:**

~~~text
date=2024-02-29
same=true
year=2024
month=FEBRUARY
monthValue=2
day=29
dayOfYear=60
dayOfWeek=THURSDAY
leap=true
monthLength=29
epoch=1970-01-01
~~~

**Giải thích:**

- **getMonth()** trả enum **Month.FEBRUARY**, còn **getMonthValue()** trả số **2**.
- **getDayOfYear()** là ngày thứ **60** của năm 2024: 31 ngày tháng 1 + 29 ngày tháng 2.
- **getDayOfWeek()** trả enum **THURSDAY**. Theo enum Java, **getValue()** đánh số **MONDAY=1 ... SUNDAY=7**, khác với quy ước của một số thư viện/lịch khác.
- **isLeapYear()** và **lengthOfMonth()** trả dữ liệu lịch, không phụ thuộc vào zone.
- **equals(...)** so sánh giá trị LocalDate, không so danh tính tham chiếu đối tượng.

## 4. LocalDate là immutable, thread-safe và value-based

**LocalDate là immutable**: không có setter cập nhật trường năm, tháng, ngày của instance đang có. Phương thức **plusDays(...)**, **minusMonths(...)**, **withYear(...)**, **withDayOfMonth(...)**... trả **một LocalDate kết quả**, không sửa đối tượng gốc.

~~~java
LocalDate original = LocalDate.of(2026, 1, 1);

original.plusDays(1);
System.out.println(original); // 2026-01-01

LocalDate next = original.plusDays(1);
System.out.println(next);     // 2026-01-02
~~~

Đây là **đoạn minh họa**, cần import LocalDate.

**Lỗi thường gặp:**

~~~java
// SAI nếu muốn cập nhật biến:
date.plusDays(7); // Giá trị trả về bị bỏ đi.
~~~

**Đúng:**

~~~java
date = date.plusDays(7);
~~~

Giá trị ngày mới có thể được gán lại cho **biến**, nhưng **đối tượng LocalDate cũ vẫn không bị thay đổi**. Tính immutable giúp việc truyền ngày giữa các lớp, luồng và cache dễ kiểm soát hơn.

**LocalDate là value-based class.** Không dùng **==** để kiểm tra hai ngày bằng nhau; dùng **equals()** hoặc **isEqual()**. Tránh sử dụng instance LocalDate làm khóa khóa đồng bộ kiểu **synchronized(date)**; danh tính object không phải một phần hợp đồng giá trị cần dựa vào.

## 5. Lấy ngày hiện tại: now(), now(ZoneId), now(Clock)

Đây là nội dung rất quan trọng vì tiêu đề bài nói **"không gắn múi giờ"**.

### 5.1. LocalDate không có zone, nhưng "hôm nay" cần zone

Ba overload:

~~~java
LocalDate systemToday = LocalDate.now();
LocalDate todayInZone = LocalDate.now(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
LocalDate todayFromClock = LocalDate.now(clock);
~~~

Đây là **đoạn minh họa**; cần import **LocalDate/ZoneId**, và biến clock kiểu **Clock** được khai báo phù hợp.

- **now()** dùng **đồng hồ hệ thống và múi giờ mặc định của JVM**.
- **now(ZoneId)** dùng **đồng hồ hệ thống trong zone chỉ định**.
- **now(Clock)** dùng **Clock được cung cấp**, gồm cả instant và zone của clock; rất phù hợp để unit test, dependency injection.
- Kết quả của cả ba vẫn là **LocalDate không mang zone**. Zone chỉ là **tham số để xác định ngày** tại thời điểm đọc đồng hồ.

**Vì sao ngày hiện tại có thể khác nhau?** Cùng một Instant gần nửa đêm, những zone khác nhau có thể thuộc hai ngày lịch khác nhau. Nếu ứng dụng có người dùng ở nhiều nước, **LocalDate.now()** phụ thuộc zone server có thể không đáp ứng ý nghĩa "hôm nay của người dùng".

### 5.2. Clock cố định giúp test không phụ thuộc thời điểm chạy

Lưu thành **LocalDateClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class LocalDateClockDemo {
    public static void main(String[] args) {
        Instant fixedInstant =
                Instant.parse("2026-01-01T23:30:00Z");

        Clock vietnamClock = Clock.fixed(
                fixedInstant,
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        Clock utcClock = Clock.fixed(
                fixedInstant,
                ZoneOffset.UTC
        );

        System.out.println("vietnamToday="
                + LocalDate.now(vietnamClock));

        System.out.println("utcToday="
                + LocalDate.now(utcClock));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateClockDemo.java
java LocalDateClockDemo
~~~

**Stdout:**

~~~text
vietnamToday=2026-01-02
utcToday=2026-01-01
~~~

Đây là **cùng một Instant**. Khi dùng zone Việt Nam, nó đã sang ngày 2/1; khi dùng UTC, vẫn là ngày 1/1. LocalDate được trả không lưu zone, nhưng zone đã quyết định phép **Instant → calendar date**.

**Trong test**, hãy tiêm **Clock** thay vì khẳng định **LocalDate.now()** bằng một ngày cố định. Một service có thể nhận Clock qua constructor và gọi **LocalDate.now(clock)**, giúp unit test không bị lỗi khi chạy gần nửa đêm.

**Lưu ý:** **now(ZoneId)** vẫn đọc đồng hồ hệ thống thật, nên nó xác định zone nhưng **không** cung cấp tính cố định cho test. Dùng **now(Clock)** khi cần kiểm soát thời điểm.

## 6. Định dạng và parsing: ISO, DateTimeFormatter, dữ liệu không hợp lệ

### 6.1. Mặc định dùng dạng ISO

~~~java
LocalDate day = LocalDate.parse("2024-02-29");
String serialized = day.toString();
// serialized.equals("2024-02-29") là true
~~~

Đây là đoạn minh họa.

Khi lưu dữ liệu hoặc trao đổi qua API dưới dạng date-only, **chuỗi ISO local date** như **"2024-02-29"** thường rõ nghĩa vì **không kèm giờ hoặc timezone**. Tuy nhiên các năm ngoài phạm vi bốn chữ số có biểu diễn ISO mở rộng; đừng tự giả định mọi LocalDate đều có chuỗi dài đúng 10 ký tự.

**LocalDate.parse(...)** không diễn giải tùy ý văn bản như **"29/02/2024"** nếu không có formatter phù hợp. Và chuỗi **"2024-02-29T00:00:00"** là date-time, không phải định dạng ISO LocalDate mặc định.

### 6.2. Formatter tùy biến và STRICT parsing

Lưu thành **LocalDateParsingDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class LocalDateParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter format =
                DateTimeFormatter.ofPattern("dd/MM/uuuu")
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDate date = LocalDate.parse(
                "29/02/2024",
                format
        );

        System.out.println("parsed=" + date);
        System.out.println("formatted=" + date.format(format));

        try {
            LocalDate.parse("29/02/2025", format);
        } catch (DateTimeParseException exception) {
            System.out.println(
                    "invalid=DateTimeParseException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateParsingDemo.java
java LocalDateParsingDemo
~~~

**Stdout:**

~~~text
parsed=2024-02-29
formatted=29/02/2024
invalid=DateTimeParseException
~~~

**Ý nghĩa:**

- **dd** là ngày trong tháng có hai chữ số, **MM** là tháng có hai chữ số, **uuuu** là **proleptic year**.
- **ResolverStyle.STRICT** đảm bảo ngày tồn tại trong tháng/năm đã parse; **29/02/2025** bị từ chối thay vì tự đổi sang ngày khác.
- **DateTimeFormatter** là immutable và thread-safe, có thể tái sử dụng khi cấu hình cố định.
- **parse(...)** ném **DateTimeParseException** khi văn bản không hợp lệ; xử lý lỗi đầu vào tại ranh giới của API hoặc UI.

### 6.3. yyyy, uuuu và YYYY khác nhau

Trong các pattern của DateTimeFormatter:

| Mẫu | Ý nghĩa | Lưu ý |
|---|---|---|
| **uuuu** | Proleptic year | Thường dùng với parsing STRICT cho ISO LocalDate |
| **yyyy** | Year-of-era | Với STRICT parsing có thể cần era hoặc cách giải quyết bổ sung |
| **YYYY** | Week-based-year | **Không phải năm lịch thông thường**; có thể lệch ở tuần gần đầu/cuối năm |
| **MM** | Tháng bằng số | Dùng với ngày/tháng/năm |
| **mm** | Phút | **Không** thay cho MM |
| **dd** | Ngày trong tháng | Khác với ngày trong năm |

**Không dùng "YYYY-MM-dd" để định dạng ngày lịch thông thường.** Week-based-year có thể khác calendar year ở những ngày cuối hoặc đầu năm, tùy quy tắc tuần/locale. Nếu muốn ISO date, ưu tiên **DateTimeFormatter.ISO_LOCAL_DATE** hoặc **LocalDate.toString()**.

Khi hiển thị cho người dùng, có thể chọn **Locale** cụ thể để định dạng tên tháng/thứ, nhưng **Locale không tự bổ sung múi giờ** cho LocalDate.

## 7. Năm nhuận, độ dài tháng và ngày cuối tháng

**isLeapYear()** kiểm tra năm nhuận theo lịch ISO (Gregorian):

- Năm chia hết cho 4 thường là nhuận.
- Năm chia hết cho 100 không nhuận, trừ khi chia hết cho 400.
- Vì vậy **2000** là năm nhuận; **1900** không nhuận; **2024** nhuận, **2025** không nhuận.

~~~java
LocalDate leap = LocalDate.of(2024, 2, 29);

System.out.println(leap.isLeapYear());   // true
System.out.println(leap.lengthOfMonth()); // 29
System.out.println(leap.lengthOfYear());  // 366
~~~

Đây là đoạn minh họa, cần import LocalDate.

**Không hard-code tháng 2 có 28 ngày.** Dùng **lengthOfMonth()** hoặc **YearMonth.lengthOfMonth()** khi nghiệp vụ chỉ cần cấu trúc năm-tháng. Để tìm ngày cuối tháng của LocalDate:

~~~java
LocalDate lastDay = LocalDate.of(2024, 2, 10)
        .with(TemporalAdjusters.lastDayOfMonth());

// lastDay == 2024-02-29
~~~

Đoạn minh họa cần import **LocalDate** và **TemporalAdjusters**. Đây là cách rõ ý nghĩa và không đòi tự viết quy tắc tháng 2.

### 7.1. Ngày không hợp lệ là lỗi, không tự chuẩn hóa

~~~java
// Lỗi ngay khi chạy:
LocalDate invalid = LocalDate.of(2025, 2, 29);
~~~

**DateTimeException** thể hiện ngày không tồn tại. Tùy trường hợp, **plusMonths/plusYears** có thể điều chỉnh ngày cuối tháng để ra một ngày hợp lệ — đó là **quy tắc cộng lịch**, không phải việc factory chấp nhận mọi ngày đầu vào.

## 8. Cộng trừ ngày tháng: plusDays, plusMonths, plusYears

LocalDate hỗ trợ:

~~~java
LocalDate nextDay = date.plusDays(1);
LocalDate previousWeek = date.minusWeeks(1);
LocalDate nextMonth = date.plusMonths(1);
LocalDate previousYear = date.minusYears(1);
~~~

Đây là các đoạn minh họa, giả sử date là LocalDate đã khai báo.

**plusDays(1)** tiến một ngày **lịch**; nó không có ý nghĩa "tiến đúng 24 giờ theo một múi giờ". **plusWeeks(1)** tương đương tiến 7 ngày lịch. **plusMonths(1)** tiến một tháng theo lịch và có quy tắc điều chỉnh nếu ngày trong tháng không tồn tại ở tháng đích.

### 8.1. Quy tắc cuối tháng

Ví dụ:

~~~text
2024-01-31 + 1 tháng = 2024-02-29
2025-01-31 + 1 tháng = 2025-02-28
2024-02-29 + 1 năm   = 2025-02-28
~~~

**Vì sao?** Nếu tháng/năm đích không có ngày tương ứng, Java điều chỉnh về **ngày cuối cùng hợp lệ** của tháng đích. Đây là hành vi được định nghĩa, không phải lỗi.

**Cẩn thận với chuỗi thao tác:**

~~~text
2024-01-31.plusMonths(1) = 2024-02-29
2024-02-29.plusMonths(1) = 2024-03-29

Nhưng:
2024-01-31.plusMonths(2) = 2024-03-31
~~~

Tức là **cộng một tháng hai lần** không nhất thiết bằng **cộng hai tháng một lần** khi ngày cuối tháng bị điều chỉnh. Nếu nghiệp vụ muốn "ngày cuối mỗi tháng", hãy **giữ quy tắc cuối tháng rõ ràng** hoặc dùng **YearMonth.atEndOfMonth()**, thay vì lặp plusMonths từ ngày đã bị clip.

### 8.2. Ví dụ chạy đầy đủ về số học lịch

Lưu thành **LocalDateArithmeticDemo.java**:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;

public class LocalDateArithmeticDemo {
    public static void main(String[] args) {
        LocalDate januaryEnd = LocalDate.of(2024, 1, 31);
        LocalDate februaryEnd = januaryEnd.plusMonths(1);

        System.out.println("afterMonth=" + februaryEnd);
        System.out.println("afterYear="
                + LocalDate.of(2024, 2, 29).plusYears(1));

        LocalDate from = LocalDate.of(2024, 2, 28);
        LocalDate to = LocalDate.of(2024, 3, 1);

        System.out.println("days="
                + ChronoUnit.DAYS.between(from, to));
        System.out.println("period="
                + Period.between(januaryEnd, februaryEnd));

        LocalDate lastFebruary =
                LocalDate.of(2024, 2, 10).with(
                        TemporalAdjusters.lastDayOfMonth());

        LocalDate nextMonday =
                LocalDate.of(2026, 1, 2).with(
                        TemporalAdjusters.nextOrSame(
                                DayOfWeek.MONDAY));

        System.out.println("lastFebruary=" + lastFebruary);
        System.out.println("nextMonday=" + nextMonday);
        System.out.println("original=" + januaryEnd);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateArithmeticDemo.java
java LocalDateArithmeticDemo
~~~

**Stdout:**

~~~text
afterMonth=2024-02-29
afterYear=2025-02-28
days=2
period=P29D
lastFebruary=2024-02-29
nextMonday=2026-01-05
original=2024-01-31
~~~

**Phân tích:** LocalDate đầu tiên vẫn là ngày 31/1 vì immutable. **Period.between(2024-01-31, 2024-02-29)** cho kết quả **P29D**, không phải P1M, do cách Period phân tách tháng/ngày giữa hai ngày. **plusMonths(1)** và **Period.between(...)** phục vụ hai mục đích khác nhau, không nên coi chúng là phép nghịch đảo hoàn hảo trong mọi trường hợp cuối tháng.

## 9. Period và số ngày thực tế trên lịch là hai phép đo khác nhau

Cùng hai LocalDate, ta có thể đặt hai câu hỏi:

1. **Cách nhau bao nhiêu ngày lịch?** Dùng **ChronoUnit.DAYS.between(start, end)** hoặc **start.until(end, ChronoUnit.DAYS)**.
2. **Chênh lệch theo các thành phần năm/tháng/ngày là bao nhiêu?** Dùng **Period.between(start, end)**.

Ví dụ:

~~~java
LocalDate a = LocalDate.of(2024, 2, 28);
LocalDate b = LocalDate.of(2024, 3, 1);

long days = ChronoUnit.DAYS.between(a, b); // 2
Period period = Period.between(a, b);      // P2D
~~~

Đây là đoạn minh họa. Vì 2024 có ngày 29/2, từ 28/2 đến 1/3 cách **hai ngày lịch**, không phải một.

### 9.1. Period là khoảng lịch, Duration là thời lượng thời gian

| Kiểu/cách tính | Ý nghĩa | Ví dụ |
|---|---|---|
| **ChronoUnit.DAYS.between(LocalDate, LocalDate)** | Số ngày lịch giữa hai ngày | 2 |
| **Period.between(LocalDate, LocalDate)** | Khoảng dạng năm/tháng/ngày lịch | P2D |
| **Duration.between(Instant, Instant)** | Số giờ/phút/giây thực trên timeline | PT23H |
| **LocalDate.plusMonths(1)** | Quy tắc cộng tháng theo lịch | 31/1 → cuối tháng 2 nếu cần |

**Không dùng Duration để thay Period khi tính "một tháng lịch".** Tháng có 28, 29, 30 hoặc 31 ngày; Duration là độ dài thời gian, không biểu diễn tháng lịch theo cách nghiệp vụ.

**Không dùng Period để đếm chính xác số giây hoặc giờ đã trôi qua.** LocalDate không có thời điểm bắt đầu của ngày trong một zone; vì thế nó chưa thể trả lời "đã qua bao nhiêu giờ thực".

### 9.2. Khoảng ngày nên dùng [startInclusive, endExclusive)

Trong tính toán lịch, một quy ước rõ ràng là **bao gồm ngày bắt đầu, loại trừ ngày kết thúc**:

~~~text
[startInclusive, endExclusive)

[2024-02-28, 2024-03-01)

Bao gồm: 2024-02-28, 2024-02-29
Không bao gồm: 2024-03-01
Số ngày: 2
~~~

Điều kiện kiểm tra:

~~~java
boolean contains =
        !day.isBefore(startInclusive)
                && day.isBefore(endExclusive);
~~~

Đây là đoạn minh họa với ba biến LocalDate khai báo trước. Cách biểu diễn **[start,end)** giúp ghép các kỳ liền nhau không chồng biên và dễ dùng **ChronoUnit.DAYS.between(start,end)**.

Nếu nghiệp vụ dùng **endInclusive**, cần quy định rõ, không âm thầm áp dụng công thức của khoảng end-exclusive vào khoảng inclusive.

## 10. So sánh LocalDate: equals, isBefore, isAfter, isEqual

Các phép thường dùng:

~~~java
LocalDate a = LocalDate.of(2026, 1, 2);
LocalDate b = LocalDate.of(2026, 1, 5);

boolean earlier = a.isBefore(b);     // true
boolean later = a.isAfter(b);        // false
boolean same = a.isEqual(b);         // false
int order = a.compareTo(b);          // âm
~~~

Đây là đoạn minh họa.

- **isBefore/isAfter** diễn tả quan hệ trước/sau theo ngày lịch.
- **isEqual** trả true nếu hai ngày có cùng giá trị trên trục epoch-day; với **hai LocalDate ISO**, kết quả phù hợp với equals.
- **equals** là phép so sánh object theo giá trị LocalDate, nên dùng khi kiểm tra equality.
- **compareTo** trả số âm/0/dương; không dựa vào một số âm cố định như -1.
- **Không dùng ==** để kết luận hai ngày có cùng giá trị vì LocalDate là value-based object.

Một LocalDate không thể trả lời **"ngày này xảy ra trước thời điểm Instant kia hay không"** nếu chưa chọn cách quy đổi ngày thành một khoảng thời gian theo **ZoneId** và chính sách thời điểm trong ngày.

## 11. Điều chỉnh theo ngày trong tuần và ngày cuối tháng

**TemporalAdjusters** cung cấp các quy tắc lịch hay gặp:

~~~java
LocalDate date = LocalDate.of(2026, 1, 2); // thứ Sáu

LocalDate nextMonday = date.with(
        TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));

LocalDate monthEnd = date.with(
        TemporalAdjusters.lastDayOfMonth());
~~~

Đây là đoạn minh họa, cần import **DayOfWeek**, **LocalDate**, **TemporalAdjusters**.

**nextOrSame(MONDAY)** cho thứ Hai gần nhất **không trước** date. Nếu date đã là thứ Hai, kết quả chính là date đó; nếu bạn muốn **thứ Hai sau date**, dùng **TemporalAdjusters.next(MONDAY)**.

**lastDayOfMonth()** tránh phải tự kiểm tra tháng 2 năm nhuận hay số ngày mỗi tháng.

### 11.1. Dùng YearMonth khi bài toán chỉ cần tháng

Nếu bạn đang tính "ngày cuối cùng của tháng N", có thể dùng:

~~~java
YearMonth month = YearMonth.of(2024, 2);
LocalDate lastDay = month.atEndOfMonth();

// lastDay == 2024-02-29
~~~

Đoạn minh họa cần import **YearMonth** và **LocalDate**. **YearMonth** là lựa chọn thích hợp khi dữ liệu ban đầu chỉ có năm-tháng, thay vì tự đặt tạm ngày 1 rồi tính toán.

## 12. Duyệt một dải ngày theo lịch

Khi cần danh sách tất cả ngày trong một khoảng, Java có **LocalDate.datesUntil(...)** từ **Java 9**; với Java 17+ có thể dùng trực tiếp:

Lưu thành **LocalDateRangeDemo.java**:

~~~java
import java.time.LocalDate;
import java.util.List;

public class LocalDateRangeDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 2, 27);
        LocalDate endExclusive = LocalDate.of(2024, 3, 2);

        List<LocalDate> days = start
                .datesUntil(endExclusive)
                .toList();

        System.out.println("days=" + days);
        System.out.println("count=" + days.size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateRangeDemo.java
java LocalDateRangeDemo
~~~

**Stdout:**

~~~text
days=[2024-02-27, 2024-02-28, 2024-02-29, 2024-03-01]
count=4
~~~

Dãy gồm **ngày bắt đầu** nhưng **không gồm ngày kết thúc**, phù hợp với quy ước khoảng **[start,end)**.

**datesUntil** không phải API gốc của Java 8; nó được thêm từ Java 9. Nếu đang duy trì mã Java 8 thực sự, có thể sử dụng vòng lặp ngày bắt đầu rồi **plusDays(1)** cho tới khi **isBefore(endExclusive)** không còn đúng. Trên JDK hiện đại, **datesUntil** là lựa chọn rõ ràng.

**Cẩn trọng với dải ngày rất dài:** Không thu thập nhiều triệu ngày thành List chỉ vì có datesUntil; stream có thể xử lý từng ngày, hoặc bạn có thể dùng truy vấn/tính toán tối ưu hơn theo bài toán.

## 13. LocalDate và ZoneId: từ một ngày sang thời điểm

LocalDate tự thân không mang ZoneId. Muốn diễn giải một ngày thành **một thời điểm bắt đầu ngày tại một địa điểm**, cần cung cấp **zone**:

~~~java
LocalDate date = LocalDate.of(2026, 1, 2);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime start = date.atStartOfDay(zone);
Instant instant = start.toInstant();
~~~

Đây là đoạn minh họa; cần import **LocalDate**, **ZoneId**, **ZonedDateTime**, **Instant**.

**Ý nghĩa:**

1. **date** chỉ là **2026-01-02**, chưa có giờ.
2. **zone** nói quy tắc múi giờ nào được áp dụng.
3. **atStartOfDay(zone)** tìm **thời điểm đầu ngày hợp lệ sớm nhất** theo quy tắc zone, trả ZonedDateTime.
4. **toInstant()** chuyển thành một thời điểm tuyệt đối trên UTC timeline.

**Không thể gọi date.toInstant() trực tiếp** vì LocalDate không đủ thông tin để xác định một Instant.

### 13.1. atStartOfDay() và atStartOfDay(zone) khác nhau

| Lời gọi | Kiểu trả về | Ý nghĩa |
|---|---|---|
| **date.atStartOfDay()** | **LocalDateTime** | Ghép ngày với **00:00** ở cấp lịch, **không** có zone |
| **date.atStartOfDay(zone)** | **ZonedDateTime** | Thời điểm bắt đầu ngày hợp lệ sớm nhất theo **quy tắc zone** |
| **date.atTime(LocalTime.of(9,0))** | **LocalDateTime** | Ghép ngày với **09:00** nhưng vẫn **chưa** có zone |
| **date.atTime(time).atZone(zone)** | **ZonedDateTime** | Giải quyết ngày-giờ địa phương theo zone rules |

**Cẩn trọng:** **atStartOfDay(zone)** không phải lúc nào cũng là **00:00**. Với một số zone có bước nhảy DST/offset tại nửa đêm, **00:00 có thể không tồn tại**. API chọn thời điểm sớm nhất hợp lệ cho ngày theo các quy tắc hiện hành. Khi có overlap, API chọn offset sớm hơn theo hợp đồng. Với trường hợp gap, kết quả được điều chỉnh tới sau gap. Không tự ghép giờ **00:00 UTC** để đại diện cho "bắt đầu ngày của mọi người".

### 13.2. Một Instant có thể thành hai LocalDate khác nhau

Lưu thành **LocalDateZoneDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class LocalDateZoneDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-01-01T23:30:00Z");

        LocalDate utcDate = event.atZone(
                ZoneOffset.UTC).toLocalDate();

        LocalDate vietnamDate = event.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();

        System.out.println("utcDate=" + utcDate);
        System.out.println("vietnamDate=" + vietnamDate);

        LocalDate date = LocalDate.of(2026, 1, 2);

        Instant vietnamStart = date
                .atStartOfDay(
                        ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();

        System.out.println("vietnamStartUTC=" + vietnamStart);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateZoneDemo.java
java LocalDateZoneDemo
~~~

**Stdout:**

~~~text
utcDate=2026-01-01
vietnamDate=2026-01-02
vietnamStartUTC=2026-01-01T17:00:00Z
~~~

**Giải thích:** Đầu ngày 2/1/2026 tại Việt Nam (UTC+07 tại thời điểm ví dụ) tương ứng **17:00 UTC ngày 1/1/2026**. LocalDate vẫn là **2026-01-02**; mốc Instant đầu ngày lại mang ngày **2026-01-01 theo UTC**.

**Nên chọn ZoneId vùng** như **Asia/Ho_Chi_Minh** khi nghiệp vụ gắn với địa điểm, thay vì hard-code offset **+07:00** cho mọi dữ liệu lịch sử/tương lai. Region zone rules có thể có thay đổi theo thời gian và được cập nhật trong dữ liệu timezone của JDK.

## 14. Một ngày lịch không nhất thiết dài 24 giờ

Một sai lầm tinh vi là nghĩ **một ngày LocalDate luôn tương ứng Duration.ofHours(24)** khi đổi sang Instant. Tại những zone áp dụng **daylight saving time**, ngày lịch có thể dài **23 giờ** hoặc **25 giờ**.

Ví dụ tại **America/New_York** theo quy tắc DST năm 2024:

- Ngày **2024-03-10** có bước chuyển giờ mùa xuân, khoảng từ đầu ngày này tới đầu ngày sau dài **23 giờ thực**.
- Ngày **2024-11-03** có bước chuyển giờ mùa thu, khoảng từ đầu ngày này tới đầu ngày sau dài **25 giờ thực**.
- Trong cả hai trường hợp, **ChronoUnit.DAYS.between(localDate, localDate.plusDays(1)) == 1**.

Lưu thành **LocalDateDstDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;

public class LocalDateDstDemo {
    static long hoursInCalendarDay(
            LocalDate date,
            ZoneId zone) {

        return Duration.between(
                date.atStartOfDay(zone).toInstant(),
                date.plusDays(1).atStartOfDay(zone).toInstant()
        ).toHours();
    }

    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDate spring = LocalDate.of(2024, 3, 10);
        LocalDate autumn = LocalDate.of(2024, 11, 3);

        System.out.println("springHours="
                + hoursInCalendarDay(spring, newYork));

        System.out.println("autumnHours="
                + hoursInCalendarDay(autumn, newYork));

        System.out.println("calendarDays="
                + ChronoUnit.DAYS.between(
                        spring,
                        spring.plusDays(1)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateDstDemo.java
java LocalDateDstDemo
~~~

**Stdout với zone rules lịch sử New York năm 2024:**

~~~text
springHours=23
autumnHours=25
calendarDays=1
~~~

**Bài học:** Nếu một đơn hàng phải hết hạn **cuối ngày theo khu vực của người dùng**, hãy xác định **ngày kết thúc** và **ZoneId**, rồi chuyển ranh giới ngày sang Instant đúng quy tắc. Không mặc định lấy một Instant và cộng **86.400 giây** cho mọi "ngày tiếp theo" của mọi zone.

**Đặc biệt:** Offset không phải ZoneId vùng. **ZoneOffset.of("+07:00")** chỉ là độ lệch cố định, còn **ZoneId.of("America/New_York")** được liên kết với lịch sử/quy tắc DST, vì thế ngày có thể dài khác 24 giờ.

## 15. Ví dụ nghiệp vụ: khoảng ngày hiệu lực [start, end)

Giả sử một chương trình khuyến mãi có hiệu lực theo **ngày lịch**, không phải theo một timestamp chính xác: bắt đầu **28/2/2024**, kết thúc **trước ngày 2/3/2024**.

Yêu cầu:

- **28/2**, **29/2**, **1/3** được tính là đang trong kỳ.
- **2/3** không thuộc kỳ.
- Số ngày là **3** vì 2024 có ngày 29/2.
- Nếu start không trước end, không tạo khoảng rỗng/đảo ngược do nhập sai (đây là quy tắc nghiệp vụ của ví dụ).

Lưu thành **LocalDateBusinessDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class LocalDateBusinessDemo {
    record Window(
            LocalDate startInclusive,
            LocalDate endExclusive) {

        Window {
            Objects.requireNonNull(startInclusive);
            Objects.requireNonNull(endExclusive);

            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException(
                        "start must be before end");
            }
        }

        boolean contains(LocalDate date) {
            Objects.requireNonNull(date);

            return !date.isBefore(startInclusive)
                    && date.isBefore(endExclusive);
        }

        long lengthInCalendarDays() {
            return ChronoUnit.DAYS.between(
                    startInclusive,
                    endExclusive);
        }
    }

    public static void main(String[] args) {
        Window promotion = new Window(
                LocalDate.of(2024, 2, 28),
                LocalDate.of(2024, 3, 2)
        );

        System.out.println("days="
                + promotion.lengthInCalendarDays());

        System.out.println("feb28="
                + promotion.contains(LocalDate.of(2024, 2, 28)));

        System.out.println("feb29="
                + promotion.contains(LocalDate.of(2024, 2, 29)));

        System.out.println("march2="
                + promotion.contains(LocalDate.of(2024, 3, 2)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalDateBusinessDemo.java
java LocalDateBusinessDemo
~~~

**Stdout:**

~~~text
days=3
feb28=true
feb29=true
march2=false
~~~

**Giải thích:** Một **Window** lưu hai LocalDate để mô tả **quy tắc ngày lịch**, không quy định nơi người dùng đang ở hoặc giờ bắt đầu. Phương thức **contains** chỉ so sánh các ngày theo lịch ISO.

Nếu chương trình khuyến mãi có giới hạn "hết hạn đúng 00:00 theo giờ Việt Nam", khi đó hệ thống phải xác định **ZoneId.of("Asia/Ho_Chi_Minh")** và chuyển endExclusive thành **Instant** theo zone rules. **Date-only window** và **timestamp window** cần được lựa chọn theo hợp đồng nghiệp vụ, không tự động thay thế cho nhau.

### 15.1. Trường hợp ngày sinh, ngày kỷ niệm, ngày giao hàng

**Sinh nhật:** Lưu **LocalDate** của ngày sinh. Không tự gắn UTC midnight và chuyển múi giờ chỉ để hiển thị ngày.

**Ngày lập hóa đơn:** Nếu hóa đơn dùng một ngày kế toán cố định, lưu LocalDate riêng cho ngày đó. **Thời điểm tạo bản ghi** (audit) vẫn nên là một **Instant** độc lập.

**Ngày giao dự kiến:** LocalDate thể hiện ngày giao theo lịch địa điểm được thỏa thuận. Nếu cần thêm giờ giao và địa điểm, mô hình có thể dùng LocalDate + LocalTime + ZoneId hoặc ZonedDateTime.

**Hạn thanh toán:** Phải thống nhất "hạn đến hết ngày X" là **end-inclusive** hay **end-exclusive**, xét theo zone nào, và ranh giới giờ ra sao. LocalDate lưu giá trị ngày tốt, nhưng không tự quyết định chính sách "quá hạn" tại một Instant.

## 16. Lưu trữ, trao đổi API và cơ sở dữ liệu

### 16.1. JSON hoặc REST: truyền ngày đúng nghĩa date-only

Đối với một API dùng ngày theo lịch, trường đơn giản có thể là:

~~~json
{
  "birthday": "1998-07-15",
  "invoiceDate": "2026-01-02"
}
~~~

Đây là **JSON minh họa**, không đính offset hoặc ký tự Z vì các giá trị là **date-only**. Nếu API dùng một thư viện serializer, hãy cấu hình rõ kiểu **LocalDate** và định dạng ISO; hành vi tự động phụ thuộc thư viện/cấu hình, không phải tính năng mà java.time tự "đẩy" vào JSON.

**Không đổi** giá trị **"2026-01-02"** thành **"2026-01-02T00:00:00Z"** để gửi qua API như thể hai dữ liệu cùng nghĩa. Chuỗi thứ hai biểu diễn **một thời điểm cụ thể theo UTC** (nếu được parse thành Instant), có thể hiển thị là ngày khác ở một zone khác.

### 16.2. SQL DATE không đồng nghĩa với TIMESTAMP

Khi mục tiêu là cột **SQL DATE** theo nghĩa **ngày lịch** và driver hỗ trợ JDBC 4.2 mappings, có thể dùng LocalDate:

~~~java
// Đoạn minh họa; statement là PreparedStatement.
statement.setObject(1, LocalDate.of(2026, 1, 2));

// Đoạn minh họa; resultSet là ResultSet.
LocalDate date = resultSet.getObject(
        "invoice_date",
        LocalDate.class
);
~~~

Phải kiểm tra **mức hỗ trợ JDBC 4.2/driver cụ thể**, kiểu cột và cách thư viện ORM ánh xạ. Không suy ra rằng mọi database đều xử lý date/timestamp/zone giống nhau.

**Chọn kiểu dữ liệu theo ngữ nghĩa:**

| Dữ liệu | Kiểu Java thường phù hợp |
|---|---|
| Ngày sinh, ngày hiệu lực | **LocalDate** |
| Giờ trong ngày, không có ngày | **LocalTime** |
| Thời điểm tạo sự kiện trong audit | **Instant** |
| Lịch họp tại một region zone | **ZonedDateTime** hoặc lưu LocalDateTime + ZoneId theo hợp đồng |
| Ngày kế toán theo zone của tổ chức | **LocalDate** cho ngày kế toán, quản lý riêng nguồn tính ngày/zone |

**Tránh lưu date-only thành epoch milliseconds** nếu business không yêu cầu timestamp. Mốc milliseconds là thông tin của một thời điểm; không có một phép chuyển ngày sang milliseconds nào là duy nhất khi thiếu zone và giờ.

### 16.3. Dữ liệu từ hệ thống khác

Khi nhận ngày từ nơi khác, hỏi trước: trường này là **calendar date** hay **timestamp**?

- Nếu văn bản thực sự là **ISO date-only**, dùng **LocalDate.parse(...)**.
- Nếu là **Instant** có UTC hoặc offset, parse thành Instant/OffsetDateTime rồi **chọn ZoneId** để lấy LocalDate.
- Nếu là **LocalDateTime** không có zone, không tự phán đoán nó là UTC. Cần bổ sung zone theo hợp đồng.
- Nếu là ngày trong **lịch khác ISO**, cần mô hình và quy tắc chuyển đổi lịch phù hợp, không đơn giản ép về LocalDate và hy vọng đúng.

## 17. Những lỗi phổ biến khi làm việc với LocalDate

### Lỗi 1 — Coi LocalDate là timestamp

~~~java
LocalDate birthday = LocalDate.of(1998, 7, 15);
// birthday không chứa giờ hoặc Instant.
~~~

**Sửa:** dùng LocalDate cho ngày sinh; nếu cần thời điểm sự kiện, dùng Instant hoặc một kiểu ngày-giờ có zone/offset.

### Lỗi 2 — Tự áp UTC midnight cho mọi ngày

~~~java
// Chỉ đúng nếu nghiệp vụ cố ý chọn UTC đầu ngày:
Instant utcMidnight = date.atStartOfDay(
        ZoneOffset.UTC).toInstant();
~~~

Nếu ngày thuộc lịch địa phương của người dùng, phải dùng **ZoneId phù hợp** thay vì mặc định UTC. Với người ở UTC-âm, UTC midnight có thể là ngày trước đó.

### Lỗi 3 — Dùng LocalDate.now() trong server đa khu vực mà quên zone

~~~java
LocalDate today = LocalDate.now();
~~~

**now() phụ thuộc default ZoneId của JVM**. Một số môi trường production đặt zone mặc định UTC; "hôm nay" theo nghiệp vụ của người dùng có thể khác. Dùng **now(userZone)** hoặc **now(injectedClock)** theo yêu cầu.

### Lỗi 4 — Test phụ thuộc ngày giờ hiện tại

~~~java
// Test không ổn định:
assert LocalDate.now().equals(LocalDate.of(2026, 1, 2));
~~~

Dùng **Clock.fixed(...)** với Instant và ZoneId rõ ràng để tạo ngày hôm nay có thể kiểm thử.

### Lỗi 5 — Quên LocalDate immutable

~~~java
LocalDate deadline = LocalDate.of(2026, 1, 2);
deadline.plusDays(7); // deadline không đổi.
~~~

Gán giá trị được trả về: **deadline = deadline.plusDays(7)**.

### Lỗi 6 — Dùng == thay vì equals

~~~java
LocalDate a = LocalDate.parse("2024-02-29");
LocalDate b = LocalDate.of(2024, 2, 29);

// Đúng: a.equals(b)
// Không dựa vào a == b.
~~~

LocalDate là **value-based**.

### Lỗi 7 — Nhầm cộng một tháng với cộng 30 ngày

~~~java
LocalDate a = LocalDate.of(2024, 1, 31);

LocalDate oneMonth = a.plusMonths(1); // 2024-02-29
LocalDate thirtyDays = a.plusDays(30); // 2024-03-01
~~~

Câu trên dùng **30 ngày lịch** và **một tháng lịch**, là hai quy tắc khác nhau. Chính sách gia hạn cần được định nghĩa rõ.

### Lỗi 8 — Không dự liệu điều chỉnh ngày cuối tháng

**31/1 + 1 tháng** có thể thành **28/2 hoặc 29/2**, nên cộng tiếp một tháng không nhất thiết quay lại ngày 31. Với nghiệp vụ recurring end-of-month, dùng quy tắc end-of-month rõ ràng.

### Lỗi 9 — Dùng mẫu định dạng YYYY-MM-dd

**YYYY** là **week-based-year**, không phải năm lịch thông thường; có thể đổi năm ở ranh giới tuần. Dùng **uuuu-MM-dd**, formatter ISO hoặc **LocalDate.toString()**.

### Lỗi 10 — Coi Period và Duration là cùng một

**Period** biểu diễn lượng năm/tháng/ngày theo lịch; **Duration** đo thời lượng giây/nano trên trục thời gian. Ngày DST có thể dài 23 hoặc 25 giờ; LocalDate liên tiếp vẫn cách nhau một ngày lịch.

### Lỗi 11 — Tính đủ 24 giờ để ra "ngày mai"

~~~java
// Có thể sai với ngày địa phương tại zone có DST:
Instant tomorrow = todayStart.plus(
        Duration.ofHours(24));
~~~

Muốn ranh giới ngày kế tiếp theo zone, hãy tính **date.plusDays(1).atStartOfDay(zone).toInstant()**.

### Lỗi 12 — Parse ngày invalid bằng formatter quá dễ dãi

Một formatter mặc định do **ofPattern(...)** tạo có thể sử dụng **ResolverStyle.SMART**, dẫn tới xử lý một số giá trị ngày theo hướng điều chỉnh. Khi yêu cầu đầu vào phải đúng chính xác ngày trong tháng, chọn **ResolverStyle.STRICT**, kèm pattern **uuuu** phù hợp.

### Lỗi 13 — Ép "múi giờ của LocalDate"

LocalDate **không lưu múi giờ**. **date.atStartOfDay(zone)** trả **ZonedDateTime mới**; nó không cập nhật LocalDate để "gắn zone". Nếu cần lưu cả ngày giờ và vùng, phải lưu kiểu/field phù hợp.

### Lỗi 14 — Dùng ngày theo UTC cho nghiệp vụ theo giờ địa phương

Cùng một Instant, ngày UTC có thể là 1/1 nhưng ngày Việt Nam là 2/1. Nếu nghiệp vụ tính ngày giao hoặc ngày đăng ký theo địa phương, chọn ZoneId đúng **trước khi trích LocalDate**.

### Lỗi 15 — Coi tên tháng/ngày từ Locale là thay lịch

Định dạng theo Locale có thể đổi cách hiển thị tên tháng/ngày. **LocalDate vẫn là ISO calendar**, không tự biến thành một lịch khác.

### Lỗi 16 — Dùng LocalDate khi sự kiện cần thời gian chính xác

Nếu hệ thống cần "hết hạn vào 17:00 ngày 31/12 tại New York", chỉ lưu **LocalDate.of(...,12,31)** là thiếu thông tin. Cần **LocalTime và ZoneId**, cùng chính sách DST/gap/overlap nếu có.

## 18. Checklist thiết kế data model và kiểm thử

### 18.1. Trước khi chọn LocalDate

Hãy trả lời:

- Dữ liệu là **ngày theo lịch** hay **một thời điểm trên timeline**?
- Ngày này thuộc **lịch ISO** hay hệ lịch khác?
- Nếu phải tính "hôm nay", **ZoneId của ai** quyết định?
- Nếu cần convert sang Instant, **giờ nào trong ngày** và **ZoneId nào**?
- Khoảng ngày tính **bao gồm đầu/kết thúc** như thế nào?
- Quy tắc "một tháng sau" là **tháng lịch**, **30 ngày**, hay **ngày cuối tháng**?
- Đầu vào có thể có **ngày nhuận**, **ngày invalid** hoặc thiếu giá trị không?
- API/database lưu **date-only** hay timestamp?
- Test có thể dùng **Clock.fixed** để tránh phụ thuộc thời gian thật không?

### 18.2. Bộ test nên có

1. **Tạo hợp lệ:** 2024-02-29, 2025-02-28, 2000-02-29.
2. **Tạo không hợp lệ:** 2025-02-29, tháng 13, ngày 32.
3. **Cuối tháng:** 31/1 plusMonths 1 ở năm nhuận và thường.
4. **Độc lập đối tượng:** gọi plusDays mà không gán không đổi giá trị.
5. **Parse STRICT:** ngày invalid phải bị từ chối.
6. **Hai zone khác nhau:** cùng Instant gần nửa đêm có thể cho hai LocalDate khác.
7. **Clock cố định:** kết quả "hôm nay" không phụ thuộc lúc chạy test.
8. **DST:** chênh lệch hai ranh giới ngày có thể không là 24 giờ.
9. **Date range:** quy tắc [start,end), gồm đầu loại cuối, năm nhuận.
10. **Null/untrusted input:** xử lý phù hợp tại API boundary.
11. **Persistence:** không chuyển nhầm date-only sang timestamp UTC.
12. **Giới hạn miền dữ liệu:** không cộng/đổi năm vượt phạm vi LocalDate được hỗ trợ.
13. **So sánh:** isBefore/isAfter/equals cho đúng giá trị, không dùng object identity.
14. **Tái diễn hàng tháng:** quy tắc cuối tháng không bị biến mất qua mỗi lần cộng.

### 18.3. Lưu ý về miền giá trị

LocalDate hỗ trợ khoảng năm rộng hơn rất nhiều so với 0000–9999, nhưng các hệ thống ngoài Java (SQL driver, JSON schema, ứng dụng web) có thể giới hạn ngày. Nếu tích hợp, cần xác định miền giá trị hợp lệ của toàn hệ thống; đừng cho rằng vì Java tạo được ngày nào đó thì mọi nơi khác đều lưu/hiển thị được.

## 19. Bài tập tự kiểm tra

**Câu 1.** LocalDate **2026-01-02** có thể tự chuyển thành một Instant duy nhất không? Vì sao?

**Câu 2.** **LocalDate.now()** có phụ thuộc múi giờ không? Điều đó có làm LocalDate mang ZoneId sau khi tạo không?

**Câu 3.** Kết quả của **LocalDate.of(2024,1,31).plusMonths(1)** là gì?

**Câu 4.** Kết quả của **LocalDate.of(2024,2,29).plusYears(1)** là gì?

**Câu 5.** Từ **2024-02-28** đến **2024-03-01**, **ChronoUnit.DAYS.between(...)** là bao nhiêu?

**Câu 6.** Vì sao **Period.between(2024-01-31,2024-02-29)** không bắt buộc trả P1M?

**Câu 7.** Sau khi gọi **deadline.plusDays(1)** nhưng không gán kết quả, deadline có đổi không?

**Câu 8.** Chuỗi **29/02/2025** có hợp lệ với **dd/MM/uuuu** và **ResolverStyle.STRICT** không?

**Câu 9.** Cùng Instant **2026-01-01T23:30:00Z**, ngày theo UTC và theo **Asia/Ho_Chi_Minh** lần lượt là gì?

**Câu 10.** **date.atStartOfDay()** khác **date.atStartOfDay(zone)** về kiểu trả về và semantics như thế nào?

**Câu 11.** Hai LocalDate liên tiếp luôn cách nhau 24 giờ thực tại mọi zone không? Ví dụ nào phản chứng?

**Câu 12.** Để lưu **ngày sinh** cho người dùng xuyên múi giờ, nên dùng LocalDate hay tự ép ngày sinh thành UTC midnight Instant?

**Câu 13.** Nếu một chương trình hiệu lực trong **[2024-02-28, 2024-03-02)**, có ngày 2/3 không? Có bao nhiêu ngày?

**Câu 14.** Khi cần parse năm lịch theo STRICT, **uuuu** hay **YYYY** là lựa chọn đúng cho mẫu date-only ISO thông thường?

**Câu 15.** Muốn liệt kê các ngày từ đầu đến trước cuối ở Java 17, nên dùng API nào? API đó có từ Java 8 không?

### Đáp án

1. **Không.** Cần thêm **giờ và ZoneId/offset cùng quy tắc chuyển đổi** để xác định một Instant.
2. **Có**, vì now() đọc đồng hồ tại **default ZoneId của JVM**; **không**, LocalDate được tạo vẫn không mang zone.
3. **2024-02-29**, do ngày cuối tháng đích được điều chỉnh hợp lệ.
4. **2025-02-28**.
5. **2 ngày lịch**, vì 2024 là năm nhuận.
6. Vì **Period.between** biểu diễn độ lệch năm/tháng/ngày theo quy tắc phân tách của Period; với cặp này là **P29D**, trong khi plusMonths(1) có quy tắc clip cuối tháng.
7. **Không đổi**, LocalDate immutable; phải gán giá trị trả về.
8. **Không**, parse ném **DateTimeParseException**.
9. **UTC: 2026-01-01**; **Asia/Ho_Chi_Minh: 2026-01-02**.
10. Bản không tham số trả **LocalDateTime tại 00:00 không có zone**; bản có zone trả **ZonedDateTime ở đầu ngày hợp lệ theo zone rules**, có thể không đúng 00:00.
11. **Không.** Ngày DST tại New York như 2024-03-10 dài **23 giờ** hoặc 2024-11-03 dài **25 giờ**.
12. **LocalDate** để giữ đúng ngày sinh theo lịch, tránh rủi ro lệch ngày khi chuyển múi giờ.
13. **Không có ngày 2/3**; gồm **28/2, 29/2, 1/3**, tổng **3 ngày**.
14. **uuuu** (hoặc formatter **ISO_LOCAL_DATE**). **YYYY** là week-based-year, có thể khác năm lịch.
15. **LocalDate.datesUntil(endExclusive)** (và có thể thu bằng toList trên Java 17); **datesUntil được thêm từ Java 9**.

## 20. Tổng kết

**LocalDate** là kiểu chuẩn để biểu diễn một **ngày lịch ISO không có giờ và không gắn múi giờ**. Nó **immutable**, phù hợp cho ngày sinh, ngày hiệu lực, ngày hóa đơn, ngày thanh toán hoặc khoảng ngày theo lịch.

Các nguyên tắc cần nhớ:

- **LocalDate không phải Instant.** Muốn xác định thời điểm, phải có đủ giờ và ZoneId/offset theo hợp đồng nghiệp vụ.
- **now() cần một zone để xác định "hôm nay".** Chọn **now(ZoneId)** khi biết zone; dùng **now(Clock)** để test có thể lặp lại.
- **plusDays/plusMonths/plusYears trả đối tượng mới**, và cộng tháng có quy tắc điều chỉnh ngày cuối tháng.
- **DateTimeFormatter.ISO_LOCAL_DATE** phù hợp cho trao đổi date-only; với định dạng tùy biến cần xét **uuuu**, **MM** và **ResolverStyle.STRICT**.
- **ChronoUnit.DAYS** đếm ngày lịch; **Period** mô tả tháng/năm/ngày; **Duration** đo thời lượng thực trên timeline.
- **DST khiến một ngày địa phương có thể dài 23 hoặc 25 giờ**; dùng **atStartOfDay(zone)** và **date.plusDays(1)** để xây ranh giới theo lịch, không tự giả định mỗi ngày là 86.400 giây.
- **Lưu date-only như date-only**, không tự ép nó thành timestamp nếu nghiệp vụ không đòi.

### Tài liệu chính thức (còn áp dụng trong Java hiện đại)

- [LocalDate — Java SE 26: ISO date, now, parse, arithmetic, atStartOfDay và immutable semantics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html)
- [Clock — Java SE 26: fixed, system, zone và khả năng kiểm thử](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [ZoneId — Java SE 26: region IDs và zone rules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html)
- [DateTimeFormatter — Java SE 26: ISO_LOCAL_DATE, pattern và parsing](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [ResolverStyle — Java SE 26: STRICT/SMART/LENIENT](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Period — Java SE 26: date-based amount](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
- [Duration — Java SE 26: time-based amount](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [TemporalAdjusters — Java SE 26: lastDayOfMonth, nextOrSame](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)
