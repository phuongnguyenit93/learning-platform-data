# LocalTime: tạo giờ với độ chính xác tới nano giây

## 1. `LocalTime` biểu diễn điều gì?

`java.time.LocalTime` là kiểu ngày giờ bất biến (*immutable*) của Java 8+ dùng để lưu **giờ trong ngày**, gồm giờ, phút, giây và phần lẻ của giây với độ phân giải tới **1 nano giây (1 ns = 10⁻⁹ giây)**. Nó không chứa ngày, offset UTC, múi giờ hoặc thời điểm tuyệt đối.

Ví dụ `09:05:07.123456789` có nghĩa là 9 giờ, 5 phút, 7 giây và **123.456.789 nano giây** trong giây đó. Bạn có thể tạo giá trị này mà không cần biết hôm nay là ngày nào hoặc máy chủ đang ở múi giờ nào.

Điểm cần phân biệt ngay từ đầu:

- **Độ phân giải biểu diễn:** kiểu `LocalTime` lưu được từng mức 1 ns.
- **Độ chính xác của nguồn đồng hồ:** `LocalTime.now()` không được bảo đảm đo thời gian thực chính xác tới 1 ns. Nền tảng có thể chỉ cung cấp bước micro/milli giây hoặc độ chính xác thấp hơn.
- **Độ chính xác khi trao đổi/lưu trữ:** định dạng chuỗi, API, CSDL hoặc driver có thể chỉ giữ 3 hay 6 chữ số phần giây, làm mất thông tin nano.

Bài này tập trung vào cách **tạo một giờ đã biết, đúng tới trường nano**, rồi kiểm tra tính hợp lệ, đọc, chuyển đổi, format và thao tác trên giá trị. Khi cần ngày hoặc múi giờ, phải phối hợp thêm các kiểu thời gian phù hợp.

## 2. Bốn thành phần và phạm vi hợp lệ

| Thành phần | Phạm vi | Getter | Ví dụ |
|---|---:|---|---:|
| Giờ | 0–23 | `getHour()` | 9 |
| Phút | 0–59 | `getMinute()` | 5 |
| Giây | 0–59 | `getSecond()` | 7 |
| Nano trong giây | 0–999.999.999 | `getNano()` | 123.456.789 |

Các giá trị đặc biệt có sẵn:

- `LocalTime.MIN` = `00:00`.
- `LocalTime.MIDNIGHT` = `00:00`.
- `LocalTime.NOON` = `12:00`.
- `LocalTime.MAX` = `23:59:59.999999999`.

`LocalTime` không nhận `24:00`, giờ 24, phút 60, giây 60 hay nano bằng 1.000.000.000. Factory sẽ ném `DateTimeException` nếu thành phần vượt phạm vi. Với ngày/giờ yêu cầu giây nhuận hoặc bản ghi lịch sử đặc thù, cần mô hình chuyên biệt; không đưa 60 vào trường giây của `LocalTime`.

### 2.1. Phân biệt nano, micro và milli

| Một đơn vị | Số nano |
|---|---:|
| 1 giây (s) | 1.000.000.000 |
| 1 milli giây (ms) | 1.000.000 |
| 1 micro giây (µs) | 1.000 |
| 1 nano giây (ns) | 1 |

Vì vậy:

~~~java
LocalTime nano123 = LocalTime.of(9, 5, 7, 123);
LocalTime milli123 = LocalTime.of(9, 5, 7, 123_000_000);
LocalTime micro123 = LocalTime.of(9, 5, 7, 123_000);
~~~

Kết quả `toString()` lần lượt là:

~~~text
09:05:07.000000123
09:05:07.123
09:05:07.000123
~~~

**Tham số cuối của `of(hour, minute, second, nanoOfSecond)` luôn có đơn vị nano**, dù biến nguồn nghiệp vụ ban đầu đang lưu milli hay micro giây. Dấu `_` giữa các chữ số trong Java chỉ tăng khả năng đọc, không làm đổi giá trị.

## 3. Factory `of(...)`: cách tạo trực tiếp

Các overload phổ biến:

~~~java
LocalTime onlyHourMinute = LocalTime.of(9, 5);
LocalTime withSecond = LocalTime.of(9, 5, 7);
LocalTime withNanos = LocalTime.of(9, 5, 7, 123_456_789);
~~~

| Cách gọi | Các thành phần được cung cấp | Giá trị `toString()` |
|---|---|---|
| `of(9, 5)` | Giờ, phút; giây và nano mặc định 0 | `09:05` |
| `of(9, 5, 7)` | Giờ, phút, giây; nano mặc định 0 | `09:05:07` |
| `of(9, 5, 7, 123_456_789)` | Đầy đủ bốn thành phần | `09:05:07.123456789` |

Nếu muốn đặt 250 milli giây ở 08:15:30 thì gọi:

~~~java
LocalTime meeting = LocalTime.of(8, 15, 30, 250_000_000);
// 08:15:30.250
~~~

Nếu một trường đầu vào ghi `nanos=1_000_000_000`, giá trị đó đã bằng một giây và **không thể** truyền làm `nanoOfSecond`. Cần chuẩn hóa thành phần giây ở logic đầu vào hoặc dùng phép cộng trên một `LocalTime` hợp lệ.

**Kiểm tra lỗi:** `LocalTime.of(23, 59, 59, 999_999_999)` hợp lệ; `LocalTime.of(23, 59, 59, 1_000_000_000)` ném `DateTimeException`. `LocalTime.of(24, 0)` và `LocalTime.of(12, 0, 60)` cũng không hợp lệ.

## 4. Tạo từ đầu ngày bằng `ofSecondOfDay()` và `ofNanoOfDay()`

Đôi khi nguồn dữ liệu cung cấp một con số duy nhất: số giây hoặc nano giây kể từ `00:00`. `LocalTime` có hai factory tương ứng:

~~~java
LocalTime fromSeconds = LocalTime.ofSecondOfDay(3_661L);
LocalTime fromNanos = LocalTime.ofNanoOfDay(32_707_123_456_789L);
~~~

- `fromSeconds` = `01:01:01` vì 3.661 giây = 1 giờ + 1 phút + 1 giây.
- `fromNanos` = `09:05:07.123456789`.

Các giới hạn:

| Factory | Giá trị nhỏ nhất | Giá trị lớn nhất | Đơn vị |
|---|---:|---:|---|
| `ofSecondOfDay(long)` | 0 | 86.399 | giây |
| `ofNanoOfDay(long)` | 0 | 86.399.999.999.999 | nano giây |

Một ngày chuẩn có `24 × 60 × 60 = 86.400` giây, tức `86.400.000.000.000` nano giây. Số nano lớn nhất hợp lệ phải **nhỏ hơn** toàn bộ thời lượng một ngày; bằng đúng số đó là nửa đêm ngày kế tiếp, không nằm trong miền giờ của một ngày `LocalTime`.

Hai phương thức ngược:

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
long nanosFromMidnight = time.toNanoOfDay();
int nanosWithinSecond = time.getNano();
~~~

Giá trị:

~~~text
nanosFromMidnight = 32707123456789
nanosWithinSecond = 123456789
~~~

Công thức:

~~~text
secondOfDay = hour * 3600 + minute * 60 + second
             = 9 * 3600 + 5 * 60 + 7 = 32707

nanoOfDay = secondOfDay * 1_000_000_000 + nanoOfSecond
          = 32707 * 1_000_000_000 + 123456789
          = 32707123456789
~~~

**Sử dụng `long` khi tính tổng nano:** giá trị lớn nhất vượt giới hạn `int` 32 bit. `getNano()` trả `int` vì nó chỉ chứa nano *trong một giây*; `toNanoOfDay()` trả `long` vì chứa nano *trong cả ngày*. Nếu đọc qua `ChronoField.NANO_OF_DAY`, sử dụng `getLong(ChronoField.NANO_OF_DAY)`.

Một phép round-trip quan trọng:

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
LocalTime restored = LocalTime.ofNanoOfDay(time.toNanoOfDay());
boolean same = restored.equals(time); // true
~~~

Đi từ `LocalTime` sang tổng nano ngày rồi quay lại **không làm mất phần giây lẻ**. Trái lại, đi qua `toSecondOfDay()` sẽ bỏ phần nano vì kết quả chỉ chứa giây nguyên.

### 4.1. Chương trình Java 17+ đầy đủ

Lưu mã vào **`LocalTimeNanoDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class LocalTimeNanoDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(9, 5, 7, 123_456_789);
        long nanoOfDay = time.toNanoOfDay();
        LocalTime restored = LocalTime.ofNanoOfDay(nanoOfDay);

        System.out.println("Time: " + time);
        System.out.println("Nano in second: " + time.getNano());
        System.out.println("Nano of day: " + nanoOfDay);
        System.out.println("Round trip: " + restored.equals(time));
        System.out.println("From seconds: "
                + LocalTime.ofSecondOfDay(3_661));
        System.out.println("Plus one nano: " + time.plusNanos(1));
        System.out.println("Truncated to millis: "
                + time.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("Nine digits: " + time.format(
                DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocalTimeNanoDemo.java
java LocalTimeNanoDemo
~~~

Stdout xác định:

~~~text
Time: 09:05:07.123456789
Nano in second: 123456789
Nano of day: 32707123456789
Round trip: true
From seconds: 01:01:01
Plus one nano: 09:05:07.123456790
Truncated to millis: 09:05:07.123
Nine digits: 09:05:07.123456789
~~~

Lệnh không phụ thuộc đồng hồ hiện tại, múi giờ máy hay dữ liệu bên ngoài. Các giá trị `LocalTime` được tạo trực tiếp nên đây là một phép kiểm chứng tốt cho việc lưu nano giây và chuyển đổi `toNanoOfDay()`.

## 5. `parse()`: tạo giờ từ chuỗi có phần nano

`LocalTime.parse(String)` chấp nhận dạng ISO local time, chẳng hạn:

~~~java
LocalTime a = LocalTime.parse("09:05");
LocalTime b = LocalTime.parse("09:05:07");
LocalTime c = LocalTime.parse("09:05:07.1");
LocalTime d = LocalTime.parse("09:05:07.123");
LocalTime e = LocalTime.parse("09:05:07.123456");
LocalTime f = LocalTime.parse("09:05:07.123456789");
~~~

Ý nghĩa phần lẻ sau dấu chấm:

| Chuỗi | `getNano()` | Giải thích |
|---|---:|---|
| `09:05:07` | 0 | Không có phần lẻ |
| `09:05:07.1` | 100.000.000 | 0,1 giây |
| `09:05:07.123` | 123.000.000 | 123 milli giây |
| `09:05:07.123456` | 123.456.000 | 123.456 micro giây |
| `09:05:07.123456789` | 123.456.789 | Chín chữ số nano |

**`.1` sau phần giây nghĩa là 0,1 giây, không phải 1 ns.** Parser quy đổi giá trị phân số đó về nano giây. Nếu muốn 1 ns, chuỗi là `09:05:07.000000001`.

Giá trị không hợp lệ như `25:05:07`, `09:61:00` hoặc phần giây có hơn 9 chữ số thường gây `DateTimeParseException` với formatter ISO của `LocalTime`.

### 5.1. `toString()` và số chữ số phần giây

`LocalTime.toString()` in số chữ số cần thiết: có thể bỏ giây nếu giây và nano đều bằng 0, hoặc dùng nhóm 3, 6, 9 chữ số phần giây theo giá trị. Ví dụ:

~~~java
System.out.println(LocalTime.of(9, 5));                    // 09:05
System.out.println(LocalTime.of(9, 5, 7));                 // 09:05:07
System.out.println(LocalTime.of(9, 5, 7, 123_000_000));   // 09:05:07.123
System.out.println(LocalTime.of(9, 5, 7, 123_400_000));   // 09:05:07.123400
System.out.println(LocalTime.of(9, 5, 7, 123_456_789));   // 09:05:07.123456789
~~~

Do đó, một chuỗi ban đầu có `.123000000` vẫn có thể in lại thành `.123`; **giá trị nano không mất**, chỉ biểu diễn văn bản được rút gọn.

### 5.2. Định dạng cố định tới chín chữ số

Khi hệ thống khác yêu cầu đúng định dạng `HH:mm:ss.SSSSSSSSS` với **chín chữ số sau dấu chấm**, dùng `DateTimeFormatter`:

~~~java
DateTimeFormatter fullNanos =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
String text = time.format(fullNanos);
// text = "09:05:07.123000000"
~~~

Bảng ký tự pattern thường gặp:

| Pattern | Ý nghĩa |
|---|---|
| `HH` | Giờ 24h (`00..23`) |
| `hh` | Giờ 12h (`01..12`), cần ngữ cảnh AM/PM |
| `mm` | Phút |
| `ss` | Giây |
| `SSS` | Ba chữ số đầu của phần giây |
| `SSSSSS` | Sáu chữ số đầu của phần giây |
| `SSSSSSSSS` | Chín chữ số của phần giây |

Chữ `S` biểu diễn **fraction-of-second**; ba chữ số tương ứng mức milli giây, sáu chữ số micro giây, chín chữ số nano giây. Số lượng `S` quyết định độ rộng khi format. Nó không biến một giá trị ít chính xác thành phép đo có độ chính xác thực tế tốt hơn.

Để parse chuỗi ISO có phần giây tùy chọn từ 0 tới 9 chữ số, `DateTimeFormatter.ISO_LOCAL_TIME` phù hợp hơn một pattern bắt buộc chín chữ số. Nếu cần định dạng đầu vào đặc thù, có thể dùng `DateTimeFormatterBuilder.appendFraction(ChronoField.NANO_OF_SECOND, minWidth, maxWidth, true)` và khai báo rõ độ rộng được nhận.

### 5.3. Ví dụ parse/format chạy độc lập

Lưu thành **`ParseNanoDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class ParseNanoDemo {
    public static void main(String[] args) {
        LocalTime a = LocalTime.parse("09:05:07.123456789");
        LocalTime b = LocalTime.parse("09:05:07.123");
        DateTimeFormatter nine =
                DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

        System.out.println("Nano of a: " + a.getNano());
        System.out.println("Nano of b: " + b.getNano());
        System.out.println("Fixed width: " + b.format(nine));

        try {
            LocalTime.parse("25:05:07.123456789");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid hour rejected");
        }
    }
}
~~~

~~~bash
javac ParseNanoDemo.java
java ParseNanoDemo
~~~

Stdout:

~~~text
Nano of a: 123456789
Nano of b: 123000000
Fixed width: 09:05:07.123000000
Invalid hour rejected
~~~

Hãy chọn formatter tương thích định dạng dữ liệu ở ranh giới API, CSV hoặc CSDL. Không tự cắt chuỗi tùy tiện để sửa một giờ không hợp lệ rồi tiếp tục với dữ liệu sai.

## 6. Thao tác với nano giây

`LocalTime` bất biến: `plusNanos`, `minusNanos`, `withNano` và `truncatedTo` luôn trả một `LocalTime` kết quả; đối tượng ban đầu không bị sửa đổi.

~~~java
LocalTime source = LocalTime.of(9, 5, 7, 123_456_789);
LocalTime next = source.plusNanos(1);
LocalTime previous = source.minusNanos(1);
LocalTime withZeroNanos = source.withNano(0);
LocalTime millis = source.truncatedTo(ChronoUnit.MILLIS);
LocalTime micros = source.truncatedTo(ChronoUnit.MICROS);
~~~

Tương ứng:

| Biểu thức | Kết quả |
|---|---|
| `source` | `09:05:07.123456789` |
| `next` | `09:05:07.123456790` |
| `previous` | `09:05:07.123456788` |
| `withZeroNanos` | `09:05:07` |
| `millis` | `09:05:07.123` |
| `micros` | `09:05:07.123456` |

**Cắt bớt khác làm tròn:** `truncatedTo(ChronoUnit.MILLIS)` bỏ phần nhỏ hơn milli giây. Với `123_999_999` ns, cắt tới milli cho `123_000_000` ns, **không phải** `124_000_000` ns. Nếu hệ thống yêu cầu làm tròn, phải định nghĩa quy tắc làm tròn và xử lý riêng trường hợp tràn giây/ngày.

Các đơn vị hỗ trợ bởi `truncatedTo` cần có thời lượng chia hết vào một ngày chuẩn. Nanos, micros, millis, seconds, minutes và hours đáp ứng điều kiện này. Không giả định mọi loại `TemporalUnit` đều hợp lệ.

### 6.1. Qua nửa đêm: giá trị quay vòng

~~~java
LocalTime last = LocalTime.MAX;
LocalTime nextDayClockTime = last.plusNanos(1);

System.out.println(last);
System.out.println(nextDayClockTime);
~~~

Stdout:

~~~text
23:59:59.999999999
00:00
~~~

Đây là **quay vòng giá trị giờ theo 24 giờ**. `LocalTime` không lưu rằng đã cộng sang ngày hôm sau. Để giữ cả ngày:

~~~java
LocalDateTime lastMoment = LocalDateTime.of(
        2024, 2, 29, 23, 59, 59, 999_999_999);
LocalDateTime nextDay = lastMoment.plusNanos(1);
// 2024-03-01T00:00
~~~

Nếu quy tắc múi giờ cũng quan trọng, dùng `ZonedDateTime`/ `Instant` phù hợp nghiệp vụ; một `LocalTime` đơn lẻ không đủ xác định sự kiện có xảy ra trước hay sau sự kiện khác ở một ngày khác.

### 6.2. Tính khoảng cách giữa hai giờ

~~~java
LocalTime start = LocalTime.of(23, 59, 59);
LocalTime end = LocalTime.of(0, 0, 1);
Duration diff = Duration.between(start, end);
~~~

`diff` bằng `PT-23H-59M-58S`, chứ không tự biết rằng người dùng muốn nói **hai giây qua nửa đêm**. Nếu ca làm việc từ 23:59:59 hôm trước đến 00:00:01 hôm sau, phải bổ sung **ngày** hoặc quy tắc “giờ kết thúc nhỏ hơn nghĩa là hôm sau”, rồi tính trên giá trị có cả ngày/instant.

`ChronoUnit.NANOS.between(a, b)` cũng so khoảng cách giữa hai giờ trong miền biểu diễn của `LocalTime`; nó không thể suy ra lịch sử ngày.

## 7. `now()`, `Clock` và giới hạn độ chính xác thực tế

`LocalTime.now()` tạo giờ hiện tại theo đồng hồ và timezone mặc định của JVM; `LocalTime.now(ZoneId)` dùng zone được chọn; `LocalTime.now(Clock)` dùng clock được cung cấp.

~~~java
LocalTime system = LocalTime.now();
LocalTime inVietnam =
        LocalTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Cả hai kết quả phụ thuộc **thời điểm chạy**, nên không thể công bố một stdout cố định. Ở máy dùng UTC, `LocalTime.now()` không nhất thiết bằng giờ Việt Nam. Nếu đang xử lý nghiệp vụ theo một vùng, hãy chọn `ZoneId` rõ ràng.

Để kiểm thử, tạo `Clock.fixed(instant, zone)`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T23:30:00.987654321Z"),
        ZoneOffset.UTC);
LocalTime value = LocalTime.now(fixed);
// 23:30:00.987654321
~~~

Lưu một ví dụ đầy đủ thành **`ClockNanoDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ClockNanoDemo {
    public static void main(String[] args) {
        Instant point =
                Instant.parse("2024-02-29T23:30:00.987654321Z");
        Clock utc = Clock.fixed(point, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                point, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC: " + LocalTime.now(utc));
        System.out.println("HCM: " + LocalTime.now(hcm));
        System.out.println("Instant: " + Instant.now(utc));
    }
}
~~~

~~~bash
javac ClockNanoDemo.java
java ClockNanoDemo
~~~

Stdout với quy tắc `Asia/Ho_Chi_Minh` tại ngày ví dụ:

~~~text
UTC: 23:30:00.987654321
HCM: 06:30:00.987654321
Instant: 2024-02-29T23:30:00.987654321Z
~~~

Ở Việt Nam thời điểm này thuộc **2024-03-01**, nhưng `LocalTime` chỉ chứa phần giờ `06:30:00.987654321`. Để biết cả ngày, dùng `LocalDateTime.now(hcm)` hoặc `ZonedDateTime.now(hcm)`.

**Không nhầm với `System.nanoTime()`:** nó cung cấp bộ đếm tương đối để đo khoảng thời gian đã trôi qua, không phải số nano kể từ đầu ngày, không phải epoch timestamp. Không truyền trực tiếp `System.nanoTime()` vào `LocalTime.ofNanoOfDay`.

Thêm nữa, `now().getNano()` có thể có 9 chữ số nhưng không chứng minh đồng hồ hệ thống thực sự chính xác đến 1 ns. Độ phân giải hiển thị và sai số đo là hai yếu tố khác nhau; khi yêu cầu đo đạc khoa học hoặc giao dịch có quy định chặt, phải xác định nguồn đồng hồ và đặc tính đo riêng.

## 8. So sánh và bảo toàn precision trong hệ thống

`LocalTime` so sánh các trường giờ, phút, giây, nano theo thứ tự, do đó phân biệt được hai giờ chỉ cách nhau 1 ns:

~~~java
LocalTime a = LocalTime.of(9, 5, 7, 123_456_788);
LocalTime b = LocalTime.of(9, 5, 7, 123_456_789);
boolean before = a.isBefore(b);  // true
boolean after = b.isAfter(a);    // true
~~~

`equals()` so giá trị, không so chuỗi ký tự gốc:

~~~java
LocalTime.parse("09:05:07.123").equals(
        LocalTime.parse("09:05:07.123000000")); // true
~~~

Hai chuỗi trên biểu diễn cùng **123.000.000 ns** trong giây. Tuy nhiên, phép so sánh hai `LocalTime` chỉ là so **thứ tự trong ngày**, không phải thứ tự tuyệt đối của hai sự kiện nếu chúng xảy ra ở những ngày khác nhau.

Khi trao đổi hoặc lưu trữ:

- **Dữ liệu chỉ chính xác tới giây:** định dạng `HH:mm:ss` và tài liệu hóa rằng phần lẻ không có.
- **Dữ liệu milli giây:** ba chữ số phần giây (`SSS`); nếu chuyển từ nano có thể mất sáu chữ số cuối.
- **Dữ liệu micro giây:** sáu chữ số (`SSSSSS`); có thể mất ba chữ số nano cuối.
- **Dữ liệu nano giây:** cần formatter hoặc kiểu lưu giữ được chín chữ số; kiểm thử round-trip thực tế.
- **Cột SQL `TIME`:** khả năng lưu phần giây phụ thuộc hệ quản trị, độ chính xác cột, JDBC driver và mapping. Không giả định `TIME` của mọi CSDL đều lưu đủ chín chữ số.

Khi nhận nguồn ở milli/micro giây, hãy chuyển có chủ đích bằng phép nhân đơn vị trước khi gọi `LocalTime.of`. Không thể phục hồi dữ liệu nano đã bị làm tròn hoặc cắt bởi nguồn.

## 9. Lỗi phổ biến

1. **Dùng 123 làm 123 milli giây:** tham số `nanoOfSecond=123` chỉ là 123 ns. Dùng `123_000_000` cho 123 ms.
2. **Tính tổng nano bằng `int`:** số nano trong ngày vượt giới hạn `int`, dùng `long` ngay trong phép nhân.
3. **Coi `1_000_000_000` là nano hợp lệ trong một giây:** giới hạn là `999_999_999`. Một tỷ nano tương ứng đúng một giây và phải xử lý như phép cộng giây.
4. **Tưởng `toString()` luôn có đủ chín chữ số:** Java có thể lược các chữ số 0 không cần thiết. Dùng formatter khi cần độ rộng cố định.
5. **Coi `.1` trong chuỗi là một nano:** đó là một phần mười giây, tức 100.000.000 ns.
6. **Nhầm `truncatedTo` với làm tròn:** truncate bỏ phần bé hơn độ phân giải được chọn.
7. **Quên quay vòng ở 00:00:** cộng một nano vào `LocalTime.MAX` trả `00:00`, không chứa số ngày đã tăng.
8. **Lấy `Duration.between` qua nửa đêm mà không biết ngày:** kết quả có thể âm hoặc không đúng khoảng thời gian nghiệp vụ.
9. **Giả định 9 chữ số đồng nghĩa độ chính xác vật lý 1 ns:** cần xem đồng hồ và nguồn đo thực tế.
10. **Truyền `System.nanoTime()` vào `ofNanoOfDay`:** hai giá trị có mốc đo và ngữ nghĩa hoàn toàn khác nhau.
11. **Dùng `LocalTime` làm timestamp duy nhất:** thời điểm sự kiện cần ít nhất thông tin ngày và thường cả offset/zone hoặc `Instant`.
12. **Bỏ qua precision của CSDL/driver:** phải ghi và đọc lại để xác minh có bảo toàn 9 chữ số không.

## 10. Tự kiểm tra kiến thức

**Câu 1.** `LocalTime.of(12, 0, 0, 5)` in ra gì?  
**Đáp án:** `12:00:00.000000005`, vì tham số cuối là **5 nano giây**, không phải 5 milli giây.

**Câu 2.** Tạo `08:15:30.250` bằng `of` như thế nào?  
**Đáp án:** `LocalTime.of(8, 15, 30, 250_000_000)`.

**Câu 3.** `LocalTime.parse("10:20:30.123").getNano()` trả bao nhiêu?  
**Đáp án:** `123_000_000`.

**Câu 4.** `LocalTime.MAX.plusNanos(1)` cho giá trị gì?  
**Đáp án:** `00:00`. Giá trị giờ quay vòng và không chứa ngày.

**Câu 5.** Để lưu giá trị `LocalTime` đầy đủ tới nano dưới dạng số nguyên, dùng gì?  
**Đáp án:** `toNanoOfDay()` trả về `long`; tạo lại bằng `LocalTime.ofNanoOfDay(long)`.

**Câu 6.** `truncatedTo(ChronoUnit.MILLIS)` có làm tròn từ `123_999_999` ns lên 124 ms không?  
**Đáp án:** Không, nó **cắt** xuống `123_000_000` ns.

**Câu 7.** Vì sao `LocalTime.now().getNano()` không chứng minh máy có đồng hồ chính xác 1 ns?  
**Đáp án:** Vì khả năng lưu 9 chữ số của kiểu dữ liệu khác với độ phân giải và sai số của nguồn đồng hồ. Java có thể biểu diễn một giá trị chính xác tới nano mà phần cứng không đo được ở độ chính xác tương ứng.

**Câu 8.** Khi cần đồng thời ngày và giờ để biết ca làm việc qua nửa đêm, kiểu nào tốt hơn `LocalTime` đơn lẻ?  
**Đáp án:** `LocalDateTime` nếu chỉ có ngày/giờ địa phương, hoặc `ZonedDateTime`/`Instant` nếu cần quy tắc vùng hoặc khoảng thời gian tuyệt đối.

## 11. Ghi nhớ

- `LocalTime.of(hour, minute, second, nanoOfSecond)` tạo **giờ đã biết với độ phân giải nano**; tham số nano hợp lệ từ 0 đến 999.999.999.
- `ofNanoOfDay(long)` và `toNanoOfDay()` cho phép chuyển đổi bảo toàn phần nano trong cùng ngày, với `long` để chứa giá trị lớn.
- `parse()` và `DateTimeFormatter` xác định ý nghĩa phần giây lẻ và độ rộng hiển thị; `toString()` có thể rút gọn nhưng không làm mất độ chính xác của giá trị.
- `plusNanos()`, `withNano()` và `truncatedTo()` thao tác trên giá trị bất biến; giờ quay vòng khi vượt 24 giờ, **không mang ngày theo**.
- Khả năng **biểu diễn 1 ns** không đồng nghĩa đồng hồ hoặc CSDL **đo/lưu chính xác 1 ns**. Hãy xác minh từng điểm chuyển đổi dữ liệu khi yêu cầu bảo toàn nano giây.
