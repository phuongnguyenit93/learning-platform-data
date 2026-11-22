# Phân tích và biểu diễn Instant bằng chuỗi ISO-8601

`Instant` của `java.time` biểu diễn **một thời điểm xác định trên trục thời gian UTC**, độc lập với múi giờ hiển thị của người dùng. Trong ứng dụng Java, hai thao tác rất phổ biến là **phân tích (parse)** một timestamp ISO-8601 thành `Instant`, và **biểu diễn (format/serialize)** `Instant` thành chuỗi để ghi log, truyền qua REST API hoặc lưu dữ liệu.

Ví dụ:

~~~java
Instant instant = Instant.parse("2025-04-09T14:30:45.123456789Z");
String text = instant.toString();
// text = "2025-04-09T14:30:45.123456789Z"
~~~

Đây là đoạn mã minh họa bên trong phương thức có `import java.time.Instant;`. Trong chuỗi ISO-8601 này, ký hiệu `T` ngăn cách ngày và giờ, dấu `.` bắt đầu phần lẻ của giây và hậu tố `Z` thể hiện **UTC offset bằng 0**. Bài học tập trung vào cách parse/format `Instant`, các trường hợp offset, phần lẻ của giây và những lỗi có thể làm sai thời điểm.

## 1. Instant là thời điểm, không phải giờ trên một đồng hồ địa phương

`Instant` là một điểm trên trục thời gian, thường được mô hình hóa dưới dạng **số giây kể từ epoch 1970-01-01T00:00:00Z và phần nanosecond trong giây**. Một `Instant` có thể được hiển thị thành nhiều giá trị giờ địa phương nhưng vẫn là cùng một thời điểm thực tế.

| Giá trị | Ý nghĩa |
| --- | --- |
| `2025-04-09T14:30:45Z` | Thời điểm được viết theo UTC |
| `2025-04-09T21:30:45+07:00` | Cùng thời điểm với dòng trên, hiển thị ở UTC+07:00 |
| `2025-04-09T10:30:45-04:00` | Cùng thời điểm với dòng trên, hiển thị ở UTC-04:00 |
| `2025-04-09T14:30:45` | Chỉ có ngày–giờ địa phương, **chưa đủ thông tin để xác định một `Instant`** |

`Instant` không lưu tên vùng `Asia/Ho_Chi_Minh`, `Europe/London` hoặc độ lệch `+07:00` ban đầu. Các thông tin đó có thể được dùng để **xác định** hoặc **hiển thị** thời điểm, nhưng sau khi chuyển thành `Instant`, giá trị chỉ biểu diễn điểm trên trục thời gian. Nếu nghiệp vụ cần bảo toàn offset gốc hoặc tên múi giờ mà bên gửi đã cung cấp, cần lưu thông tin đó riêng hoặc chọn kiểu như `OffsetDateTime`/`ZonedDateTime` phù hợp.

`Instant` thích hợp cho thời điểm tạo bản ghi, log, thời gian phát sinh giao dịch, mốc hết hạn cụ thể và dữ liệu gửi giữa các hệ thống. Nó không thay thế `LocalDate` cho một ngày sinh chỉ có ngày, cũng không thay thế `LocalTime` cho giờ mở cửa hằng ngày.

## 2. Đọc cấu trúc của chuỗi ISO-8601

Một timestamp thông dụng theo dạng ISO-8601, cũng gần với biểu diễn ngày giờ của RFC 3339, có cấu trúc:

~~~text
2025-04-09T14:30:45.123456789Z
|  ngày  |T|  giờ   |.  phần lẻ |Z
~~~

| Phần | Ví dụ | Nghĩa |
| --- | --- | --- |
| `2025-04-09` | `uuuu-MM-dd` | Ngày năm-tháng-ngày theo lịch ISO |
| `T` | `T` | Dấu phân cách ngày và giờ |
| `14:30:45` | `HH:mm:ss` | Giờ, phút, giây |
| `.123456789` | Tối đa 9 chữ số phần lẻ thông dụng trong `Instant` | 0,123456789 giây |
| `Z` | `+00:00` | Offset bằng 0 so với UTC |

`Z` là ký hiệu “Zulu” thường dùng cho UTC, **không phải tên múi giờ IANA**. Chuỗi có thể sử dụng offset số như `+07:00` hoặc `-04:00` nếu parser hỗ trợ; trong Java, `Instant.parse` có thể đọc định dạng offset ISO hợp lệ và **quy đổi về cùng một thời điểm**.

Ba chuỗi sau là các cách viết của cùng một instant:

~~~text
2025-04-09T14:30:45.123456789Z
2025-04-09T14:30:45.123456789+00:00
2025-04-09T21:30:45.123456789+07:00
~~~

Không được đọc `+07:00` là “cộng bảy giờ vào thời điểm”. Đây là **offset của giờ hiển thị**: 21:30 tại offset +7 tương ứng 14:30 UTC.

Nếu chuỗi chỉ có `2025-04-09T21:30:45` mà không có `Z`/offset, bản thân nó là một `LocalDateTime`. Chưa thể biết đó có phải 14:30 UTC hay một thời điểm khác, trừ khi nghiệp vụ còn cung cấp `ZoneId` hoặc offset đúng.

## 3. Phân tích chuỗi thành Instant bằng Instant.parse()

Phương thức trực tiếp nhất:

~~~java
import java.time.Instant;

Instant createdAt =
        Instant.parse("2025-04-09T14:30:45.123456789Z");
~~~

`Instant.parse(CharSequence)` phân tích một chuỗi ngày-giờ có đủ thông tin để xác định thời điểm, sử dụng formatter ISO dành cho instant của `java.time`. Parser xác định ngày, giờ và offset; kết quả là `Instant`. Hàm có thể ném `DateTimeParseException` nếu cú pháp không hợp lệ hoặc thiếu thành phần bắt buộc.

Một vài trường hợp:

~~~java
Instant utc = Instant.parse("2025-04-09T14:30:45Z");
Instant numericZero =
        Instant.parse("2025-04-09T14:30:45+00:00");
Instant fromPlusSeven =
        Instant.parse("2025-04-09T21:30:45+07:00");

boolean same = utc.equals(numericZero)
        && utc.equals(fromPlusSeven); // true
~~~

Ở đây `equals` so sánh **giá trị thời điểm**, không so sánh từng ký tự của chuỗi đầu vào. Việc `fromPlusSeven.toString()` cho giờ 14:30 và hậu tố `Z` là đúng vì `Instant` được biểu diễn theo UTC.

Ngược lại:

~~~java
Instant.parse("2025-04-09T14:30:45");
// DateTimeParseException: chuỗi không có offset/UTC
~~~

Hãy dùng `LocalDateTime.parse(...)` cho chuỗi chỉ có ngày–giờ địa phương, sau đó **áp quy tắc múi giờ từ nghiệp vụ** nếu thật sự cần chuyển thành `Instant`. Không được mặc định mọi chuỗi không có hậu tố đều là UTC.

### Các trường hợp thường gặp

| Chuỗi đầu vào | Với `Instant.parse` | Giải thích |
| --- | --- | --- |
| `2025-04-09T14:30:45Z` | Hợp lệ | Giờ UTC |
| `2025-04-09T14:30:45+00:00` | Hợp lệ | Offset bằng 0 |
| `2025-04-09T21:30:45+07:00` | Hợp lệ | Đổi về UTC |
| `2025-04-09T14:30:45.12Z` | Hợp lệ | Phần lẻ là 0,12 giây |
| `2025-04-09T14:30:45` | Không hợp lệ | Thiếu offset |
| `2025-04-09` | Không hợp lệ | Chỉ có ngày |
| `09/04/2025 14:30:45` | Không đúng định dạng mặc định | Không có cấu trúc ISO instant và offset |

Bảng tập trung vào cú pháp ISO thông dụng và không thay thế việc kiểm tra contract đầu vào của API. Khi tạo giao diện nhập giờ theo locale, có thể cần formatter khác hoặc bước chuẩn hóa trước khi chuyển thành instant.

## 4. Biểu diễn Instant thành ISO-8601: toString và ISO_INSTANT

Sau khi có một `Instant`, cách đơn giản nhất để nhận chuỗi UTC là:

~~~java
Instant timestamp = Instant.parse("2025-04-09T14:30:45Z");
String iso = timestamp.toString();
// "2025-04-09T14:30:45Z"
~~~

`Instant.toString()` xuất biểu diễn ISO-8601 của instant **theo UTC**, có `T` và hậu tố `Z`. Bạn cũng có thể dùng formatter chuẩn:

~~~java
import java.time.format.DateTimeFormatter;

String iso = DateTimeFormatter.ISO_INSTANT.format(timestamp);
// "2025-04-09T14:30:45Z"
~~~

Hai cách trên phù hợp khi muốn ghi timestamp với ý nghĩa UTC nhất quán. Chúng **không phụ thuộc** múi giờ mặc định của máy và không tự biến thành `+07:00` dù chương trình đang chạy tại Việt Nam.

Tuy nhiên, **đừng yêu cầu so khớp từng ký tự với chuỗi nhập**. Parser có thể nhận `+00:00` hay `+07:00`; lúc biểu diễn dưới dạng `Instant` chuẩn, đầu ra được chuẩn hóa về `Z`:

~~~java
String output = Instant.parse(
        "2025-04-09T21:30:45+07:00").toString();
// "2025-04-09T14:30:45Z"
~~~

Nếu cần hiển thị cùng một instant trong offset +7 để người dùng đọc, hãy gắn offset vào đối tượng biểu diễn:

~~~java
String plusSeven = DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
        timestamp.atOffset(java.time.ZoneOffset.ofHours(7)));
// "2025-04-09T21:30:45+07:00"
~~~

`atOffset` và `atZone` **không làm đổi instant**, chỉ mô tả cùng thời điểm bằng giờ địa phương và offset/vùng tương ứng. Nếu muốn áp quy tắc múi giờ địa lý thay vì offset cố định, dùng `timestamp.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))`.

## 5. Phần lẻ giây và cách chuẩn hóa

`Instant` lưu nanosecond trong giây, nên chuỗi có thể mang tối đa **9 chữ số phần lẻ** với độ phân giải 1 ns. Điều quan trọng là phần lẻ của timestamp được viết theo **giá trị thập phân của giây**.

| Đầu vào | `getNano()` | Đầu ra `toString()` |
| --- | ---: | --- |
| `2025-04-09T14:30:45Z` | 0 | `2025-04-09T14:30:45Z` |
| `2025-04-09T14:30:45.1Z` | 100000000 | `2025-04-09T14:30:45.100Z` |
| `2025-04-09T14:30:45.12Z` | 120000000 | `2025-04-09T14:30:45.120Z` |
| `2025-04-09T14:30:45.1234Z` | 123400000 | `2025-04-09T14:30:45.123400Z` |
| `2025-04-09T14:30:45.123456789Z` | 123456789 | `2025-04-09T14:30:45.123456789Z` |

`Instant.toString()` chọn **0, 3, 6 hoặc 9 chữ số phần lẻ** cần thiết để biểu diễn chính xác các nanosecond, thay vì bảo toàn số chữ số đã nhập. Do đó, `.1Z` có thể được xuất thành `.100Z`, và `.1234Z` thành `.123400Z`.

Ý nghĩa vẫn giống nhau: `.1` giây = 100 mili giây = 100.000.000 nano giây. Chuỗi thay đổi hình thức nhưng **không mất giá trị thời điểm** trong các ví dụ này.

Một số API yêu cầu timestamp luôn có đúng ba chữ số mili giây, trong khi nơi khác chấp nhận phần lẻ thay đổi độ dài. Hãy ghi rõ contract, khả năng parse của phía nhận và quy tắc xử lý khi dữ liệu có nano giây. **Không tự cắt chuỗi sau dấu chấm** để đạt độ dài; việc cắt có thể làm mất độ chính xác, nhất là nếu chuỗi tiếp tục được parse rồi so sánh.

## 6. Ví dụ Java 17+ chạy độc lập

Lưu thành tệp `InstantIsoDemo.java`:

~~~java
import java.time.Instant;
import java.time.DateTimeException;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class InstantIsoDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse(
                "2025-04-09T14:30:45.123456789Z");
        Instant sameInstant = Instant.parse(
                "2025-04-09T21:30:45.123456789+07:00");

        System.out.println("same=" + instant.equals(sameInstant));
        System.out.println("parse=" + instant);
        System.out.println("format="
                + DateTimeFormatter.ISO_INSTANT.format(instant));
        System.out.println("plus7="
                + DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
                        instant.atOffset(ZoneOffset.ofHours(7))));

        System.out.println("epochSec=" + instant.getEpochSecond());
        System.out.println("nano=" + instant.getNano());

        System.out.println("zero="
                + Instant.parse("2025-04-09T14:30:45+00:00"));
        System.out.println("fracOne="
                + Instant.parse("2025-04-09T14:30:45.1Z"));
        System.out.println("fracFour="
                + Instant.parse("2025-04-09T14:30:45.1234Z"));
        System.out.println("fracNine="
                + Instant.parse("2025-04-09T14:30:45.123456789Z"));

        System.out.println("localDateTime="
                + instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toLocalDateTime());

        try {
            Instant.parse("2025-04-09T14:30:45");
        } catch (DateTimeException ex) {
            System.out.println("missingOffset="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InstantIsoDemo.java
java InstantIsoDemo
~~~

Đầu ra với các giá trị cố định:

~~~text
same=true
parse=2025-04-09T14:30:45.123456789Z
format=2025-04-09T14:30:45.123456789Z
plus7=2025-04-09T21:30:45.123456789+07:00
epochSec=1744209045
nano=123456789
zero=2025-04-09T14:30:45Z
fracOne=2025-04-09T14:30:45.100Z
fracFour=2025-04-09T14:30:45.123400Z
fracNine=2025-04-09T14:30:45.123456789Z
localDateTime=2025-04-09T21:30:45.123456789
missingOffset=DateTimeParseException
~~~

`same=true` cho thấy hai chuỗi với offset khác nhau cùng biểu diễn một instant. `epochSec` là số giây tính từ mốc epoch; `nano` là phần nanosecond **trong giây hiện tại**. `DateTimeFormatter.ISO_OFFSET_DATE_TIME` chỉ được dùng trên giá trị đã gắn offset bằng `atOffset(...)`, còn `ISO_INSTANT` được dùng trực tiếp với `Instant`.

Ví dụ bắt `DateTimeException` (lớp cha) để trình bày loại lỗi; trong code production ở biên nhận chuỗi, bạn có thể bắt cụ thể `DateTimeParseException`, gắn thông tin về trường đầu vào và trả lỗi validation phù hợp mà không làm lộ stack trace cho người dùng.

## 7. Instant, epoch seconds và milliseconds không phải cùng định dạng

`Instant` biểu diễn thời điểm với **giây epoch và phần nanosecond**. Ngược lại, một số giao thức trao đổi timestamp dưới dạng số mili giây kể từ epoch. Có thể đổi qua các API:

~~~java
Instant instant =
        Instant.parse("2025-04-09T14:30:45.123456789Z");

long seconds = instant.getEpochSecond();
int nanos = instant.getNano();
long millis = instant.toEpochMilli();

Instant fromMillis = Instant.ofEpochMilli(millis);
Instant fromParts = Instant.ofEpochSecond(seconds, nanos);
~~~

Cần phân biệt:

- `getEpochSecond()` cho số giây nguyên trên trục epoch, không phải tổng mili giây.
- `getNano()` cho phần nano giây của **giây đó**, không phải tổng nano giây kể từ epoch.
- `toEpochMilli()` đổi sang **mili giây** nguyên, nên phần chính xác hơn mili giây có thể bị mất.
- `ofEpochMilli(millis)` chỉ khôi phục đúng thời điểm ở độ phân giải mili giây.
- `ofEpochSecond(seconds, nanos)` có thể khôi phục đầy đủ phần nanosecond nếu bạn còn giữ cả hai thành phần gốc.

Với timestamp `.123456789Z`, quy đổi sang số mili giây rồi trở lại có thể chỉ còn `.123Z`, mất `456789` nanosecond còn lại. Hãy chọn định dạng truyền dữ liệu theo yêu cầu chính xác của nghiệp vụ: chuỗi ISO-8601 UTC hoặc cặp giây/nanosecond nếu cần giữ đầy đủ.

**Không mặc định** rằng số nguyên `1744209045` là “mili giây”; nếu hiểu sai đơn vị, thời điểm nhận được sẽ lệch rất xa. Với dữ liệu từ API, phải ghi rõ đó là seconds, milliseconds, microseconds hay nanoseconds kể từ mốc nào.

## 8. Khi chuỗi ISO không chứa offset: xác định vùng trước khi tạo Instant

Trong hệ thống, chuỗi như `2025-04-09T21:30:45` chỉ biểu diễn ngày giờ địa phương. Không thể suy ra `Instant` chính xác khi chưa biết vùng giờ/offset mà ứng dụng định sử dụng.

Nếu hợp đồng nêu rõ đó là giờ Việt Nam:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.parse(
        "2025-04-09T21:30:45");

Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
// 2025-04-09T14:30:45Z
~~~

Đây là đoạn mã minh họa dùng trong một phương thức có các import tương ứng. `local` chưa là instant; `atZone(...)` diễn giải ngày giờ đó theo quy tắc vùng Việt Nam, rồi `toInstant()` xác định điểm trên trục UTC.

Nếu input đã có offset rõ ràng, có thể parse trực tiếp bằng `Instant.parse`; hoặc parse thành `OffsetDateTime` rồi gọi `toInstant()` nếu nghiệp vụ cần truy cập offset ban đầu.

~~~java
OffsetDateTime supplied = OffsetDateTime.parse(
        "2025-04-09T21:30:45+07:00");

Instant instant = supplied.toInstant();
~~~

Đoạn này cần `import java.time.OffsetDateTime;` và `import java.time.Instant;`.

Khi làm việc với những vùng có daylight saving time, một `LocalDateTime` có thể không tồn tại hoặc xảy ra hai lần tại ngày đổi giờ. Đổi từ timestamp đã có `Z`/offset thành `Instant` không gặp sự mơ hồ này vì đã có thông tin xác định thời điểm; mơ hồ xảy ra khi bạn **bắt đầu từ ngày–giờ địa phương không có offset**, sau đó mới gắn một vùng địa lý. Với lịch hẹn quan trọng, phải chọn chính sách giải quyết DST rõ ràng.

## 9. Lựa chọn đúng formatter và độ chính xác

Các API thường gặp:

| Mục tiêu | Cách làm | Kết quả |
| --- | --- | --- |
| Đọc chuỗi instant ISO | `Instant.parse(text)` | `Instant` |
| Xuất chuỗi UTC ISO | `instant.toString()` | Chuỗi ISO có hậu tố `Z` |
| Xuất UTC bằng formatter | `DateTimeFormatter.ISO_INSTANT.format(instant)` | Chuỗi ISO instant |
| Giữ offset khi đọc input | `OffsetDateTime.parse(text)` | `OffsetDateTime` có offset của chuỗi |
| Xuất cùng instant theo offset khác | `instant.atOffset(offset).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)` | Chuỗi ISO với offset |
| Xuất theo múi giờ địa lý | `instant.atZone(zone).format(DateTimeFormatter.ISO_ZONED_DATE_TIME)` | Chuỗi có thông tin vùng khi cần |
| Lấy ngày giờ ở vùng cụ thể | `instant.atZone(zone).toLocalDateTime()` | `LocalDateTime` tương ứng với vùng đó |

Không nên dùng `DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss'Z'")` để **định dạng một giá trị giờ địa phương rồi giả vờ là UTC**. `'Z'` trong dấu nháy đơn là **ký tự literal**: nó sẽ được in ra bất kể dữ liệu thực sự mang offset nào, thậm chí khi dữ liệu chưa hề có offset. Đối với `Instant`, hãy ưu tiên `toString()`/`ISO_INSTANT` để tránh việc tự xử lý zone.

Nếu API yêu cầu giữ tối đa nanosecond, chuỗi do `Instant.toString()` tạo ra đủ thông tin để tái tạo instant bằng `Instant.parse(...)` trong miền giá trị hợp lệ. Nhưng nếu một giao thức chỉ hỗ trợ giây hoặc mili giây, hãy quyết định rõ **cách giảm độ chính xác** (cắt bớt hay làm tròn theo quy tắc nghiệp vụ); không kỳ vọng formatter khôi phục nanosecond mà dữ liệu đầu vào không có.

Một thao tác kiểm tra dữ liệu phổ biến:

~~~java
Instant original =
        Instant.parse("2025-04-09T14:30:45.123456789Z");
Instant restored = Instant.parse(original.toString());
boolean equal = original.equals(restored); // true
~~~

Đây là phép **round-trip theo giá trị thời điểm**, không phải khẳng định chuỗi giữ nguyên số chữ số phần lẻ hay offset của đầu vào trước đó.

## 10. Lưu trữ và giao tiếp qua API, JSON, log

**API JSON:** Trường thời điểm có thể dùng chuỗi ISO-8601 với thông tin UTC/offset, ví dụ:

~~~json
{
  "createdAt": "2025-04-09T14:30:45.123456789Z",
  "expiresAt": "2025-04-10T00:00:00Z"
}
~~~

Hãy mô tả rõ cho consumer rằng hai trường là **các instant**, không phải những giá trị `LocalDateTime` thiếu offset. Khi Java nhận vào, parse theo định dạng đã thống nhất và trả lỗi rõ ràng nếu thiếu `Z`/offset, cú pháp không hợp lệ hoặc ngày giờ không hợp lệ. Nếu dùng thư viện JSON có hỗ trợ `java.time`, vẫn cần kiểm tra cấu hình serializer: có cấu hình xuất ngày giờ bằng số epoch thay vì chuỗi ISO, và các lựa chọn đơn vị có thể khác nhau.

**Log và audit:** Ghi timestamp của sự kiện bằng `Instant` hoặc biểu diễn UTC có `Z` để dễ sắp xếp, so sánh giữa các dịch vụ. Nếu log cần hiển thị giờ địa phương cho người vận hành, đổi `Instant` sang `ZoneId` tại lớp hiển thị; không thay đổi instant gốc.

**Database:** Nếu cột dùng để lưu thời điểm tuyệt đối, phải kiểm tra ngữ nghĩa kiểu cột, driver JDBC/ORM, timezone session và mapping sang `Instant`. Tên kiểu `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE` không đảm bảo mọi cơ sở dữ liệu có cùng chính sách lưu trữ; đừng suy luận từ tên cột mà bỏ qua cấu hình thực tế.

**Test:** Dùng timestamp cố định như `Instant.parse("2025-04-09T14:30:45Z")` thay cho `Instant.now()` nếu kỳ vọng kết quả ổn định. Có thể cấp `Clock.fixed(...)` vào service để kiểm thử logic “hiện tại” mà không phụ thuộc đồng hồ thật.

## 11. Lỗi thường gặp

| Nhầm lẫn | Tác hại | Cách đúng |
| --- | --- | --- |
| Parse `2025-04-09T14:30:45` bằng `Instant.parse` | Thiếu offset, parse lỗi | Dùng `LocalDateTime` rồi áp zone/offset đã biết |
| Coi `2025-04-09T21:30:45+07:00` khác instant với `2025-04-09T14:30:45Z` | So sánh sai sự kiện | Parse cả hai thành `Instant` rồi so sánh |
| Nghĩ `Z` là mã vùng của London | London có thể dùng offset khác 0 theo mùa | `Z` nghĩa là UTC offset 0 |
| Mong `Instant.toString()` giữ nguyên `+07:00` input | Offset gốc đã mất khi chuẩn hóa | Lưu `OffsetDateTime`/offset riêng nếu cần |
| So sánh chuỗi input để quyết định instant bằng nhau | Cùng instant có nhiều cách biểu diễn | So sánh `Instant.equals` hoặc thứ tự trên trục thời gian |
| Nhầm `.1` giây là 1 nanosecond | Sai số 100 triệu lần | `.1` = 100.000.000 ns |
| Cho rằng `toString()` giữ nguyên số chữ số phần lẻ | Đầu ra được chuẩn hóa 0/3/6/9 chữ số | Đối chiếu theo `Instant` hoặc contract |
| Lưu ISO bằng chuỗi local kèm literal `'Z'` | Gắn sai UTC cho dữ liệu chưa chuyển đổi | Dùng `ISO_INSTANT`/`Instant.toString()` |
| Nhầm epoch seconds với epoch milliseconds | Lệch thời điểm rất lớn | Nêu rõ đơn vị của số epoch |
| Đổi qua mili giây và tưởng vẫn giữ nanosecond | Mất phần lẻ nhỏ hơn 1 ms | Giữ ISO full precision hoặc giây + nano |
| Coi độ phân giải nanosecond là độ chính xác của đồng hồ | Đánh giá sai tính chính xác của sự kiện | Phân biệt khả năng biểu diễn và độ chính xác nguồn |

## 12. Bài tập tự kiểm tra

**Câu 1.** `Instant.parse("2025-04-09T21:30:45+07:00").toString()` trả gì?

**Đáp án:** `2025-04-09T14:30:45Z`. UTC+7 đi trước UTC bảy giờ, nên 21:30 địa phương tương ứng 14:30 UTC.

**Câu 2.** `Instant.parse("2025-04-09T14:30:45.12Z").getNano()` trả bao nhiêu?

**Đáp án:** `120000000` vì `.12` giây = 120.000.000 ns. `toString()` sẽ chuẩn hóa phần lẻ thành `.120Z`.

**Câu 3.** Vì sao `Instant.parse("2025-04-09T14:30:45")` không phù hợp?

**Đáp án:** Chuỗi không cho biết offset hay UTC; chỉ có ngày giờ địa phương nên chưa xác định duy nhất một instant. Phải có thêm `ZoneId` hoặc offset theo nguồn dữ liệu.

**Câu 4.** Muốn hiển thị instant `2025-04-09T14:30:45Z` thành `2025-04-09T21:30:45+07:00` nhưng vẫn giữ đúng thời điểm, nên dùng gì?

**Đáp án:** `instant.atOffset(ZoneOffset.ofHours(7))`, rồi format bằng `ISO_OFFSET_DATE_TIME`. Giá trị local và offset thay đổi cách hiển thị, không làm thay đổi instant.

**Câu 5.** Hai chuỗi có phần lẻ `.1Z` và `.100Z` có biểu diễn cùng instant nếu toàn bộ ngày/giờ còn lại giống nhau không?

**Đáp án:** Có. Cả hai tương đương 100 mili giây trong phần lẻ của giây. `Instant.parse` chuyển chúng thành cùng giá trị nanosecond.

**Câu 6.** Vì sao không nên gọi `toEpochMilli()` rồi `ofEpochMilli()` nếu cần khôi phục đủ 9 chữ số phần lẻ?

**Đáp án:** Chuyển sang mili giây làm mất độ chính xác dưới 1 ms; cách khôi phục từ số mili giây không thể tái tạo phần nanosecond đã mất. Hãy giữ chuỗi ISO đủ độ chính xác hoặc cặp giây và nano.

**Ghi nhớ:** `Instant.parse(...)` nhận **timestamp ISO có thông tin UTC/offset** rồi tạo một điểm trên trục thời gian. `Instant.toString()` và `DateTimeFormatter.ISO_INSTANT` biểu diễn điểm đó ở **UTC với hậu tố `Z`**, có thể chuẩn hóa số chữ số phần lẻ. Offset/vùng hiển thị là một lớp ý nghĩa riêng; thời điểm thật không đổi khi đổi cách biểu diễn.