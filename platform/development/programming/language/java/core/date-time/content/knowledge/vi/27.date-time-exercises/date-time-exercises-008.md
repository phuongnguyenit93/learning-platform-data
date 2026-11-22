# Di chuyển đoạn mã Date, Calendar, SimpleDateFormat sang java.time

## 1. Mục tiêu là giữ đúng ý nghĩa, không chỉ thay tên lớp

`java.util.Date` biểu diễn một thời điểm với độ chính xác mili giây; `Calendar` gắn thời điểm với các trường lịch và vùng; `SimpleDateFormat` đọc/ghi chuỗi theo cấu hình. Một đoạn mã cũ có thể đang dùng chúng cho ngày sinh, thời điểm sự kiện hoặc lịch địa phương.

Trước khi sửa, xác định dữ liệu thật sự là gì và ghi lại hành vi cần giữ: múi giờ, locale, định dạng, mức độ nghiêm ngặt khi đọc, phép cộng lịch và độ chính xác. Không đổi mọi biến `Date` thành `LocalDateTime` một cách máy móc.

| Ý nghĩa sau khi xác định | Kiểu java.time thường dùng |
| --- | --- |
| Thời điểm đã xảy ra | `Instant` |
| Ngày lịch thuần túy | `LocalDate` |
| Ngày giờ địa phương chưa gắn vùng | `LocalDateTime` |
| Ngày giờ theo quy tắc một địa điểm | `ZonedDateTime` hoặc ngày giờ + `ZoneId` |
| Định dạng/phân tích chuỗi | `DateTimeFormatter` |

## 2. Cầu nối ở ranh giới API cũ

Đối với `java.util.Date` thông thường:

```java
Instant instant = legacyDate.toInstant();
java.util.Date legacyAgain = java.util.Date.from(instant);

Instant fromMillis = Instant.ofEpochMilli(epochMillis);
long millisAgain = instant.toEpochMilli();
```

Đây là đoạn minh họa trong một phương thức. `epochMillis` có đơn vị mili giây; không truyền thẳng vào `Instant.ofEpochSecond`, vì như vậy giá trị sẽ lệch theo hệ số 1.000.

`Date` không lưu một `ZoneId`; chuỗi `Date.toString()` có thể hiển thị theo vùng mặc định mà không làm đổi thời điểm chứa trong nó. Muốn lấy ngày từ `Date`, chọn vùng rồi mới dùng `date.toInstant().atZone(zone).toLocalDate()`.

`Instant` có thể giữ nano giây, còn `java.util.Date` chỉ giữ mili giây. Khi đi từ một `Instant` có phần lẻ nhỏ hơn mili giây qua `Date`, thông tin đó bị mất; không hứa mọi vòng chuyển đổi đều khôi phục nguyên vẹn. [java.util.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html)

Riêng `java.sql.Date` không phải cùng hợp đồng: dùng `toLocalDate()` cho ngày SQL; `toInstant()` của nó luôn ném `UnsupportedOperationException`. Nếu một API khai báo `java.util.Date` nhưng thực tế trả lớp con JDBC, cần kiểm tra kiểu/ngữ nghĩa tại ranh giới. [java.sql.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html#toInstant())

## 3. Calendar: từ sửa trạng thái sang nhận giá trị mới

Mã cũ có thể sửa trực tiếp một đối tượng:

```java
calendar.add(Calendar.DAY_OF_MONTH, 1);
```

Với kiểu bất biến, giữ kết quả:

```java
ZonedDateTime next = current.plusDays(1);
```

`current.plusDays(1)` mà bỏ giá trị trả về không làm `current` thay đổi. Kiểm tra những nơi mã cũ dựa vào việc truyền một `Calendar` rồi sửa nó thông qua tham chiếu dùng chung.

Một số khác biệt cần đối chiếu:

- `Calendar.MONTH` thường dùng tháng 0–11; `Month.getValue()` và `getMonthValue()` dùng 1–12.
- `Calendar.DAY_OF_WEEK` có cách đánh số khác `DayOfWeek` ISO; không truyền thẳng số giữa hai API.
- `Calendar.HOUR` là giờ trong chu kỳ 12 giờ, khác `HOUR_OF_DAY`; không đổi nhầm thành giờ 24 giờ mà bỏ AM/PM.
- `add` và `roll` không đồng nghĩa; không thay mọi `roll` bằng `plus` vì quy tắc đổi trường lớn hơn khác nhau.
- Cộng một ngày lịch trên vùng không luôn tương đương cộng 86.400.000 mili giây.

`Calendar` có thể hoạt động ở chế độ lenient và chuẩn hóa giá trị ngoài miền. Nếu cần giữ hành vi đó hoặc muốn chủ động thay đổi, phải ghi rõ và kiểm tra riêng. [Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html)

## 4. SimpleDateFormat: xem lại mẫu và chính sách parse

`DateTimeFormatter` bất biến và an toàn luồng, phù hợp làm hằng dùng chung. `SimpleDateFormat` có trạng thái thay đổi và không an toàn khi nhiều luồng dùng cùng một đối tượng mà không đồng bộ.

Không sao chép mọi ký tự mẫu mà bỏ qua ý nghĩa:

| Vấn đề | Khi di chuyển cần làm gì? |
| --- | --- |
| Năm thông thường | Thường chọn `uuuu` cho năm ISO khi parse nghiêm ngặt |
| `yyyy` | Là năm trong niên đại trong formatter mới; phải xét thông tin niên đại |
| `YYYY` | Là năm theo tuần, không phải năm lịch viết hoa |
| `u` | Ở `SimpleDateFormat` là số thứ; ở `DateTimeFormatter` là năm |
| `S` | API cũ diễn tả mili giây; formatter mới dùng phần lẻ giây, độ rộng có ý nghĩa |
| Múi giờ/độ lệch | Đối chiếu ký tự mẫu và dữ liệu đầu vào thay vì đoán tương đương |

`DateTimeFormatter.ofPattern` mặc định phân giải `SMART`; `setLenient(false)` của mã cũ không tự được chuyển sang cấu hình mới. Nếu yêu cầu từ chối ngày không tồn tại, dùng `withResolverStyle(ResolverStyle.STRICT)` và mẫu phù hợp.

Parse toàn bộ chuỗi cũng cần kiểm tra: mã cũ dùng `ParsePosition` có thể phải xác nhận đã tiêu thụ hết đầu vào; `LocalDateTime.parse` với formatter đọc toàn chuỗi. Những khác biệt về độ rộng trường hoặc ký tự dư có thể làm bộ nhập mới từ chối dữ liệu mà mã cũ từng nhận. [SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 5. Chương trình so sánh trước và sau

Ví dụ xử lý chuỗi ngày giờ tại Việt Nam, cộng một ngày lịch rồi định dạng lại. Cả hai nhánh chọn vùng, locale và kiểm tra ngày rõ ràng; dữ liệu mẫu không nằm trong khoảng thiếu/trùng giờ.

Lưu thành `LegacyTimeMigrationDemo.java`:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyTimeMigrationDemo {
    static Date parseLegacy(String text, SimpleDateFormat format) {
        ParsePosition position = new ParsePosition(0);
        Date value = format.parse(text, position);
        if (value == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid legacy input");
        }
        return value;
    }

    public static void main(String[] args) {
        String input = "2024-02-29 23:30:00";
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        TimeZone legacyZone = TimeZone.getTimeZone(zone);

        SimpleDateFormat oldFormat =
                new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT);
        oldFormat.setLenient(false);
        oldFormat.setTimeZone(legacyZone);
        Date oldParsed = parseLegacy(input, oldFormat);
        Calendar oldCalendar = new GregorianCalendar(legacyZone, Locale.ROOT);
        oldCalendar.setLenient(false);
        oldCalendar.setTime(oldParsed);
        oldCalendar.add(Calendar.DAY_OF_MONTH, 1);
        Instant oldResult = oldCalendar.toInstant();

        DateTimeFormatter newFormat =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        LocalDateTime local = LocalDateTime.parse(input, newFormat);
        ZonedDateTime current = local.atZone(zone);
        ZonedDateTime next = current.plusDays(1);
        Instant newResult = next.toInstant();

        System.out.println("oldInstant=" + oldResult);
        System.out.println("newInstant=" + newResult);
        System.out.println("sameInstant=" + oldResult.equals(newResult));
        System.out.println("oldText=" + oldFormat.format(oldCalendar.getTime()));
        System.out.println("newText=" + newFormat.withZone(zone).format(newResult));
        System.out.println("legacyMonthIndex=" + oldCalendar.get(Calendar.MONTH));
        System.out.println("modernMonthValue=" + next.getMonthValue());
        System.out.println("currentUnchanged=" + current.toLocalDateTime());

        Date boundary = Date.from(newResult);
        System.out.println("millisecondRoundTrip="
                + newResult.equals(boundary.toInstant()));
        Instant precise = Instant.parse("2024-02-29T16:30:00.123456789Z");
        System.out.println("afterLegacyPrecision=" + Date.from(precise).toInstant());

        try {
            parseLegacy("2023-02-29 23:30:00", oldFormat);
        } catch (IllegalArgumentException ex) {
            System.out.println("legacyRejectsInvalidDate");
        }
        try {
            LocalDateTime.parse("2023-02-29 23:30:00", newFormat);
        } catch (DateTimeParseException ex) {
            System.out.println("modernRejectsInvalidDate");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 LegacyTimeMigrationDemo.java
java LegacyTimeMigrationDemo
```

Stdout chính xác với quy tắc vùng Việt Nam cho các ngày trong ví dụ:

```text
oldInstant=2024-03-01T16:30:00Z
newInstant=2024-03-01T16:30:00Z
sameInstant=true
oldText=2024-03-01 23:30:00
newText=2024-03-01 23:30:00
legacyMonthIndex=2
modernMonthValue=3
currentUnchanged=2024-02-29T23:30
millisecondRoundTrip=true
afterLegacyPrecision=2024-02-29T16:30:00.123Z
legacyRejectsInvalidDate
modernRejectsInvalidDate
```

`millisecondRoundTrip` đúng vì `newResult` không có độ chính xác nhỏ hơn mili giây. Dòng kế tiếp chứng minh không được tổng quát kết quả đó cho mọi `Instant`.

## 6. Không giấu thay đổi múi giờ hoặc DST trong một lần đổi API

Đối với dữ liệu giờ địa phương, `local.atZone(zone)` có hành vi mặc định khi gặp giờ không tồn tại hoặc trùng. Mã cũ cũng có các cách phân giải riêng, nên không mặc định cả hai nhánh chọn cùng thời điểm cho mọi trường hợp DST.

Hãy kiểm tra các đầu vào ở gap/overlap, giữ độ lệch đã chọn nếu cần và quyết định rõ khi nào báo lỗi. Nếu thay đổi chính sách, xem đó là thay đổi nghiệp vụ cần được mô tả, không phải một chi tiết vô hình của việc di chuyển.

Nếu mã cũ dùng `TimeZone.getDefault()`, cần xác định vùng thực sự mong muốn trước khi thay bằng một `ZoneId`. Giữ hoặc loại bỏ phụ thuộc mặc định phải là quyết định có chủ đích.

## 7. Giữ cầu nối hẹp và kiểm tra hành vi có ý nghĩa

Trong quá trình chuyển dần, có thể giữ `Date` ở chữ ký của một thư viện cũ, chuyển sang `Instant` ngay khi đi vào phần mã mới và chuyển ngược ở lối ra. Không cần rải chuyển đổi qua lại ở mọi phép toán.

Đối với `GregorianCalendar`, `toZonedDateTime()` là một cầu nối hữu ích. Tuy nhiên, lịch Gregorian cũ có thể dùng điểm chuyển Julian/Gregorian, trong khi các kiểu ISO của `java.time` áp dụng quy tắc Gregorian kéo dài. Dữ liệu lịch sử hoặc hệ lịch khác cần kiểm tra riêng, không suy từ ví dụ năm 2024. [GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html)

Những kiểm tra có giá trị khi di chuyển gồm:

- Cùng thời điểm trước/sau khi chuyển qua cầu nối được hỗ trợ.
- Cùng nhãn hiển thị khi vùng, locale và hợp đồng định dạng phải giữ nguyên.
- Ngày cuối tháng, năm nhuận, mốc cuối năm và số tuần.
- Ngày/giờ không hợp lệ, phần chuỗi dư và dữ liệu từng được parse lenient.
- DST và độ chính xác bị mất khi qua API cũ.
- Mã dùng chung formatter giữa nhiều luồng và mã từng dựa vào trạng thái thay đổi.

Không chỉ so sánh `toString()` của các đối tượng khác kiểu: chúng có thể biểu diễn cùng thời điểm theo cách khác. So sánh `Instant`, ngày lịch hoặc chuỗi định dạng tường minh tùy thuộc điều cần bảo toàn.

## 8. Bài mở rộng

1. Di chuyển một ngày sinh từ `Date` sang `LocalDate`, nêu rõ vùng dùng để diễn giải dữ liệu cũ.
2. Thay phép cộng ngày bằng cộng 24 giờ trong một thí nghiệm qua DST và quan sát khác biệt.
3. Thêm đầu vào có ký tự dư để xác nhận hai nhánh đều từ chối theo hợp đồng đã chọn.
4. Thử phần lẻ nano giây rồi xác nhận đâu là ranh giới còn giữ mili giây.

Kết quả cần đạt là mã mới có kiểu dữ liệu đúng ý nghĩa và hành vi đã kiểm chứng; các thay đổi về parse, lịch hoặc múi giờ phải được nhận diện rõ.