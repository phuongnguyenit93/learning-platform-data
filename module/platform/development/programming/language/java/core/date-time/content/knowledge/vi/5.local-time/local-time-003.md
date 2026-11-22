# Đọc giờ, phút, giây và phần lẻ của giây với LocalTime

Trong Java, `java.time.LocalTime` biểu diễn **giờ trong một ngày** theo đồng hồ 24 giờ, không chứa ngày, múi giờ hay offset UTC. Với một giá trị như `09:07:05.123456789`, bạn có thể đọc riêng **giờ** (`09`), **phút** (`07`), **giây** (`05`) và **phần lẻ của giây** (`123456789` nanosecond). Hiểu chính xác phần lẻ đặc biệt hữu ích khi xử lý log, dữ liệu giao thức, biểu mẫu giờ và các phép so sánh thời gian có độ phân giải dưới một giây.

## 1. LocalTime lưu những gì?

Một `LocalTime` có bốn thành phần quan trọng:

| Thành phần | Getter | Miền giá trị | Trong `09:07:05.123456789` |
| --- | --- | --- | --- |
| Giờ | `getHour()` | 0–23 | `9` |
| Phút | `getMinute()` | 0–59 | `7` |
| Giây | `getSecond()` | 0–59 | `5` |
| Nano giây trong giây hiện tại | `getNano()` | 0–999.999.999 | `123456789` |

**Chú ý:** `getNano()` không trả tổng số nano giây kể từ đầu ngày. Đây là **phần lẻ của một giây**, trong khoảng từ 0 đến 999.999.999. Ví dụ, với `09:07:05.123456789`, hàm trả `123456789` chứ không phải `32825123456789`. Muốn lấy tổng nano giây kể từ `00:00`, dùng `toNanoOfDay()`; muốn lấy tổng giây kể từ đầu ngày, dùng `toSecondOfDay()`.

Độ phân giải dữ liệu của `LocalTime` là **nanosecond (10⁻⁹ giây)**. Điều này mô tả khả năng biểu diễn, **không bảo đảm** rằng đồng hồ phần cứng hoặc giá trị nhận được từ nguồn bên ngoài thực sự chính xác đến một nanosecond.

Kiểu này chỉ mô tả một giờ trên đồng hồ. Nó không phân biệt `09:00` hôm nay với `09:00` ngày mai, không cho biết `09:00` ở Hà Nội hay London và không tự chuyển đổi sang một `Instant`. Khi cần kết hợp ngày, sử dụng `LocalDateTime`; khi cần vùng giờ, sử dụng `ZonedDateTime` hoặc `OffsetTime` tùy yêu cầu.

## 2. Tạo giá trị giờ và đọc từng thành phần

Tạo một `LocalTime` bằng `of`:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);
int hour = time.getHour();     // 9
int minute = time.getMinute(); // 7
int second = time.getSecond(); // 5
int nano = time.getNano();     // 123456789
~~~

Các dấu gạch dưới trong số nguyên Java chỉ giúp con người đọc dễ hơn, nên `123_456_789` giống `123456789`. Giá trị `nanoOfSecond` phải nằm trong miền 0–999.999.999.

Các overload thông dụng:

~~~java
LocalTime.of(9, 7);                   // 09:07
LocalTime.of(9, 7, 5);                // 09:07:05
LocalTime.of(9, 7, 5, 123_000_000);   // 09:07:05.123
LocalTime.MIDNIGHT;                   // 00:00
LocalTime.NOON;                       // 12:00
LocalTime.MAX;                        // 23:59:59.999999999
~~~

Nếu không truyền giây/nano giây, Java dùng giá trị **0** cho những thành phần thiếu. Chẳng hạn `LocalTime.of(9, 7).getSecond()` bằng `0`. Tuy nhiên, cách `toString()` hiển thị mặc định có thể bỏ những thành phần bằng 0; đừng nhầm “không được in ra” với “không tồn tại trong đối tượng”.

`LocalTime` kiểm tra miền giá trị và báo lỗi nếu không hợp lệ. `LocalTime.of(24, 0)`, `LocalTime.of(9, 60)` và `LocalTime.of(9, 7, 60)` đều ném `DateTimeException`. Nó không có biểu diễn `24:00` hay “giây 60” để mô hình hóa leap second. Một ngày trên đồng hồ `LocalTime` chạy từ `00:00` đến `23:59:59.999999999`.

## 3. Phần lẻ của giây: nano, micro và milli

Giây có thể chia thành những đơn vị:

| Đơn vị | Quy đổi | Giá trị với `.123456789` |
| --- | --- | --- |
| Giây | 1 giây | Phần nguyên là `5`, phần lẻ `0.123456789` |
| Mili giây (ms) | 1 ms = 1.000.000 ns | `123` ms nguyên |
| Micro giây (µs) | 1 µs = 1.000 ns | `123456` µs nguyên |
| Nano giây (ns) | 1 ns = 10⁻⁹ giây | `123456789` ns |

Các phương thức đọc:

~~~java
LocalTime time = LocalTime.parse("09:07:05.123456789");

int nano = time.getNano();                           // 123456789
int milli = time.get(ChronoField.MILLI_OF_SECOND);   // 123
int micro = time.get(ChronoField.MICRO_OF_SECOND);   // 123456
~~~

Các getter `MILLI_OF_SECOND` và `MICRO_OF_SECOND` **lấy phần nguyên tương ứng**, không làm tròn lên. Ví dụ, `123456789` ns tương ứng `123.456789` ms; trường `MILLI_OF_SECOND` trả `123`.

Tính thủ công từ `getNano()` nếu cần:

~~~java
int millis = time.getNano() / 1_000_000; // 123
int micros = time.getNano() / 1_000;     // 123456
int nanoRemainderAfterMillis =
        time.getNano() % 1_000_000;       // 456789
~~~

Không nhầm `getNano()` với số giây `getSecond()`, hoặc `ChronoField.NANO_OF_SECOND` với `ChronoField.NANO_OF_DAY`. Khi đọc tổng nano giây của ngày, `LocalTime.toNanoOfDay()` trả `long` vì giá trị có thể lớn hơn phạm vi `int`.

## 4. Ví dụ Java 17+ hoàn chỉnh và đầu ra

Lưu chương trình sau trong `LocalTimePartsDemo.java`:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class LocalTimePartsDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

        System.out.println("time=" + time);
        System.out.println("hour=" + time.getHour());
        System.out.println("minute=" + time.getMinute());
        System.out.println("second=" + time.getSecond());
        System.out.println("nano=" + time.getNano());

        System.out.println("milli="
                + time.get(ChronoField.MILLI_OF_SECOND));
        System.out.println("micro="
                + time.get(ChronoField.MICRO_OF_SECOND));

        LocalTime onlyHourMinute = LocalTime.parse("09:07");
        System.out.println("onlyMinute=" + onlyHourMinute);
        System.out.println("onlyMinuteSecond="
                + onlyHourMinute.getSecond());

        System.out.println("frac3="
                + LocalTime.parse("09:07:05.123").getNano());
        System.out.println("frac2="
                + LocalTime.parse("09:07:05.12").getNano());

        DateTimeFormatter threeDigits =
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSS", Locale.ROOT);
        DateTimeFormatter nineDigits =
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSSSSSSSS", Locale.ROOT);

        System.out.println("format3=" + time.format(threeDigits));
        System.out.println("format9=" + time.format(nineDigits));
        System.out.println("rollover=" + LocalTime.MAX.plusNanos(1));
        System.out.println("dayNano=" + time.toNanoOfDay());
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac LocalTimePartsDemo.java
java LocalTimePartsDemo
~~~

Đầu ra:

~~~text
time=09:07:05.123456789
hour=9
minute=7
second=5
nano=123456789
milli=123
micro=123456
onlyMinute=09:07
onlyMinuteSecond=0
frac3=123000000
frac2=120000000
format3=09:07:05.123
format9=09:07:05.123456789
rollover=00:00
dayNano=32825123456789
~~~

Có thể thấy `getNano()` trả giá trị nano trong giây; `09:07:05.123` được chuẩn hóa thành `123000000` ns và `09:07:05.12` thành `120000000` ns. Các phương thức `format` chỉ điều khiển **chuỗi hiển thị**, không làm thay đổi đối tượng `time`. Dòng `rollover` nhắc rằng `LocalTime` không chứa ngày để ghi lại việc vượt qua nửa đêm.

## 5. Parse chuỗi giờ: thiếu giây, có phần lẻ, độ chính xác

`LocalTime.parse(text)` mặc định dùng `DateTimeFormatter.ISO_LOCAL_TIME`. Ví dụ:

| Chuỗi | `getHour()` | `getMinute()` | `getSecond()` | `getNano()` |
| --- | ---: | ---: | ---: | ---: |
| `09:07` | 9 | 7 | 0 | 0 |
| `09:07:05` | 9 | 7 | 5 | 0 |
| `09:07:05.1` | 9 | 7 | 5 | 100000000 |
| `09:07:05.12` | 9 | 7 | 5 | 120000000 |
| `09:07:05.123` | 9 | 7 | 5 | 123000000 |
| `09:07:05.123456` | 9 | 7 | 5 | 123456000 |
| `09:07:05.123456789` | 9 | 7 | 5 | 123456789 |

**Giải thích:** Dấu chấm bắt đầu phần lẻ thập phân của **giây**. `.1` nghĩa là **một phần mười giây** = 100 triệu ns; `.12` nghĩa là 120 triệu ns. Dãy sau dấu chấm **không** phải “số nano giây” viết trực tiếp. Java chuẩn hóa phần lẻ thành một số nguyên 9 chữ số nanosecond.

`LocalTime.parse("09:07")` hợp lệ và tự đặt giây, nano giây bằng 0. Ngược lại, những chuỗi như `9:7` hoặc `09:07:05.1234567890` không phù hợp dạng ISO mặc định; số chữ số phần lẻ vượt quá 9 hoặc thành phần ngoài miền hợp lệ sẽ gây lỗi `DateTimeParseException`. Với đầu vào do người dùng nhập, hãy kiểm tra định dạng và xử lý ngoại lệ ở ranh giới hệ thống.

**Chú ý về chuỗi đầu ra:** `LocalTime.toString()` có thể lược bỏ giây bằng 0 và hiển thị phần lẻ bằng 3, 6 hoặc 9 chữ số cần thiết tùy độ chính xác. Vì vậy, parse xong rồi `toString()` không bảo đảm trả lại **đúng số chữ số** hay hình thức đầu vào ban đầu, dù giá trị giờ vẫn tương đương. Nếu cần đúng số chữ số theo hợp đồng API, chỉ định `DateTimeFormatter`.

## 6. Format cố định giờ, phút, giây và phần lẻ

`DateTimeFormatter` hỗ trợ mẫu:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `HH` | Giờ 00–23, luôn hai chữ số | `09` |
| `mm` | Phút, luôn hai chữ số | `07` |
| `ss` | Giây, luôn hai chữ số | `05` |
| `S` | Một chữ số phần lẻ của giây | `1` |
| `SSS` | Ba chữ số phần lẻ (mili giây) | `123` |
| `SSSSSS` | Sáu chữ số phần lẻ (micro giây) | `123456` |
| `SSSSSSSSS` | Chín chữ số phần lẻ (nano giây) | `123456789` |
| `hh` và `a` | Giờ 01–12 và ký hiệu AM/PM theo locale | `09 AM` |

Ví dụ:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

String milliPrecision = time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS")); // 09:07:05.123

String nanoPrecision = time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS"));
// 09:07:05.123456789
~~~

`S` là chữ **hoa** biểu thị phần lẻ giây; `s` chữ thường biểu thị giây nguyên. `m` chữ thường là **phút**; `M` chữ hoa là **tháng** trong formatter ngày tháng. Nhầm `MM` với `mm` là lỗi rất dễ gặp.

Mẫu `SSS` chỉ in ba chữ số đầu của phần lẻ; nó **không tự làm tròn** giá trị đến mili giây. Với `.123456789`, kết quả là `.123`, không phải `.124`. Nếu nghiệp vụ cần làm tròn theo quy tắc xác định, hãy làm tròn/tính toán riêng, đồng thời xử lý khả năng chuyển sang giây hoặc ngày kế tiếp.

Nếu muốn **đọc lại** chuỗi tạo bằng một pattern cụ thể, hãy dùng cùng formatter khi parse:

~~~java
DateTimeFormatter fixedMillis =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
LocalTime parsed = LocalTime.parse("09:07:05.123", fixedMillis);
~~~

Mẫu có đúng ba `S` thường yêu cầu ba chữ số phần lẻ; nếu dữ liệu có số chữ số biến thiên, `ISO_LOCAL_TIME` thuận tiện hơn khi chuỗi có dạng ISO.

## 7. Đọc từ ChronoField và các cách đổi đơn vị

Ngoài getter trực tiếp, `LocalTime` hỗ trợ `ChronoField`:

~~~java
LocalTime time = LocalTime.of(9, 7, 5, 123_456_789);

int hour = time.get(ChronoField.HOUR_OF_DAY);         // 9
int minute = time.get(ChronoField.MINUTE_OF_HOUR);    // 7
int second = time.get(ChronoField.SECOND_OF_MINUTE);  // 5
int nano = time.get(ChronoField.NANO_OF_SECOND);      // 123456789
long totalNanos = time.toNanoOfDay();                // 32825123456789
int totalSeconds = time.toSecondOfDay();             // 32825
~~~

Các hàm `getHour()`, `getMinute()`, `getSecond()`, `getNano()` thường dễ đọc hơn khi đã biết dữ liệu là `LocalTime`. Sử dụng `ChronoField` khi cần viết logic tổng quát dựa trên các trường của `TemporalAccessor`.

Không dùng `get(ChronoField.NANO_OF_DAY)` để lấy giá trị lớn hơn miền `int`; nếu cần trường này, có thể dùng `getLong(ChronoField.NANO_OF_DAY)` hoặc cách tiện lợi `toNanoOfDay()`.

Các phép cộng trừ như `plusHours`, `plusMinutes`, `plusSeconds`, `plusNanos` trả về đối tượng mới, không sửa `LocalTime` ban đầu. Chúng tính **vòng trong ngày 24 giờ**: `LocalTime.MAX.plusNanos(1)` thành `00:00`. Vì `LocalTime` không có ngày, thông tin “đã sang hôm sau” bị mất nếu chỉ giữ kiểu này.

Khi so sánh hai giờ trong cùng một ngày lịch, dùng `isBefore` hoặc `isAfter`. Khi tính khoảng thời gian, `Duration.between(start, end)` không tự hiểu rằng `end` thuộc ngày kế tiếp. Ví dụ, 23:59 đến 00:01 có thể nhận Duration âm nếu chỉ dùng hai `LocalTime`; cần gắn ngày phù hợp khi nghiệp vụ trải qua nửa đêm.

## 8. Giờ hệ thống và ảnh hưởng của múi giờ lúc lấy giá trị

`LocalTime.now()` lấy giờ hiện tại theo zone mặc định của hệ thống. `LocalTime.now(ZoneId.of("Asia/Ho_Chi_Minh"))` lấy giờ theo vùng Việt Nam. **Đối tượng `LocalTime` kết quả không lưu zone**, mặc dù zone đã được sử dụng để tính giờ.

Một số ứng dụng cần giờ hiển thị theo lịch làm việc tại từng địa phương:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalTime currentBusinessTime = LocalTime.now(businessZone);
~~~

Đoạn trên dùng trong một phương thức đã import `java.time`; giá trị thay đổi theo lúc chạy, nên không có stdout cố định. Nếu viết unit test cho logic thời gian, dùng `Clock` cố định qua `LocalTime.now(clock)` để tránh lỗi kiểm thử không ổn định.

Giờ hiển thị `09:00` không tự cho biết thời điểm tuyệt đối. Muốn xây dựng một thời điểm cụ thể từ giờ công việc, cần thêm **ngày** và **vùng giờ**:

~~~java
LocalDate date = LocalDate.of(2025, 4, 9);
LocalTime time = LocalTime.of(9, 0);
ZonedDateTime meeting =
        ZonedDateTime.of(date, time,
                ZoneId.of("Asia/Ho_Chi_Minh"));
Instant meetingInstant = meeting.toInstant();
~~~

Đây là đoạn minh họa trong một phương thức có các import tương ứng. Khi vùng có DST, một giờ địa phương có thể **không tồn tại** hoặc **bị lặp** vào ngày chuyển giờ. Vì thế không thể chỉ dựa vào `LocalTime` để xác định lịch hẹn toàn cầu.

## 9. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Đọc `getNano()` là số mili giây | Nano và mili chênh nhau một triệu lần | Dùng `get(ChronoField.MILLI_OF_SECOND)` hoặc chia 1.000.000 |
| Cho rằng `.1` tương đương một nano giây | Đây là một phần mười giây | `.1` = 100.000.000 ns |
| Tưởng `09:07` không có trường giây | `LocalTime` lưu giây bằng 0; `toString()` có thể ẩn | `getSecond()` vẫn trả 0 |
| Gắn `Z` vào chuỗi `LocalTime` để biến thành UTC | Thiếu ngày và quy tắc zone/offset | Bổ sung ngày + zone, chuyển sang instant khi cần |
| Mong `plusNanos(1)` trên `LocalTime.MAX` báo ngày mai | `LocalTime` không chứa ngày và sẽ quay vòng | Dùng `LocalDateTime`/`ZonedDateTime` nếu cần cả ngày |
| Nhầm `mm` thành tháng | `mm` là phút, `MM` là tháng | Viết pattern đúng ngữ cảnh |
| Nghĩ `SSS` tự làm tròn | Formatter in phần đầu của giá trị lẻ | Xử lý làm tròn riêng nếu yêu cầu |
| Coi độ phân giải nanosecond là độ chính xác của đồng hồ | Nguồn dữ liệu có thể chỉ chính xác tới mili/micro giây | Phân biệt **độ phân giải** và **độ chính xác** |
| So sánh hai `LocalTime` để suy ra sự kiện nào xảy ra trước qua hai ngày | Không có thông tin ngày | Lưu thêm ngày hoặc instant |

## 10. Tự kiểm tra

**Câu 1.** `LocalTime.parse("08:15:30.25").getNano()` trả gì?

**Đáp án:** `250000000`, vì `.25` giây bằng 250.000.000 nano giây, tức 250 ms.

**Câu 2.** Từ `LocalTime.of(15, 20)`, `getSecond()` và `getNano()` bằng bao nhiêu?

**Đáp án:** Cả hai bằng `0`. Hai trường không được ghi trong lời gọi `of` nên dùng mặc định bằng 0.

**Câu 3.** `LocalTime.of(23, 59, 59, 999_999_999).plusNanos(1)` cho kết quả gì, và ngày có tăng không?

**Đáp án:** `00:00`; không có ngày nào được lưu trong `LocalTime` để tăng. Nếu cần theo dõi ngày tiếp theo, hãy sử dụng kiểu chứa cả ngày.

**Câu 4.** Giá trị `09:07:05.123456789` có bao nhiêu mili giây trong phần lẻ, và `getNano()` là bao nhiêu?

**Đáp án:** `get(ChronoField.MILLI_OF_SECOND)` bằng `123`; `getNano()` bằng `123456789`.

**Câu 5.** Với API yêu cầu chuỗi giờ luôn có giây và chính xác ba chữ số mili giây, nên làm gì?

**Đáp án:** Dùng formatter `HH:mm:ss.SSS` để tạo `09:07:05.123`. Không dựa vào `LocalTime.toString()` vì đầu ra mặc định có thể bỏ phần giây bằng 0 hoặc có số chữ số phần lẻ khác nhau.

**Ghi nhớ:** `LocalTime` trả lời **“mấy giờ, mấy phút, mấy giây và bao nhiêu nano giây trong ngày?”**. `getNano()` luôn đo phần lẻ **trong một giây**, không có thông tin ngày/zone. Hãy chọn đúng đơn vị và formatter khi chuyển dữ liệu giữa Java, API và giao diện người dùng.