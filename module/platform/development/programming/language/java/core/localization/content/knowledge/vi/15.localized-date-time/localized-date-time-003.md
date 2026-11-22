# FormatStyle: FULL, LONG, MEDIUM và SHORT trong Java

## 1. Vì sao cùng một ngày giờ có nhiều cách trình bày?

Cùng một thời điểm, ứng dụng có thể cần hiện ngày đầy đủ trong email, ngày ngắn trên danh sách, hoặc giờ có múi giờ trong lịch hẹn. Chẳng hạn một ngày được biểu diễn ngắn theo Mỹ là `10/28/26`, còn định dạng đầy đủ theo Mỹ là `Wednesday, October 28, 2026`. Quy tắc trình bày còn thay đổi theo ngôn ngữ, vùng, dữ liệu locale của JDK và loại giá trị ngày giờ.

Java hiện đại dùng `java.time.format.DateTimeFormatter` kết hợp `java.time.format.FormatStyle` để yêu cầu **mức độ chi tiết** thay vì cố định một pattern thủ công cho mọi ngôn ngữ. Bốn mức gồm:

- `FormatStyle.FULL` — mức biểu diễn đầy đủ nhất, thường có tên thứ/ngày/tháng, và thông tin múi giờ khi định dạng thời gian.
- `FormatStyle.LONG` — dài, nhiều thông tin nhưng thường bớt một số chi tiết so với FULL.
- `FormatStyle.MEDIUM` — trung bình, thích hợp cho nhiều vị trí hiển thị thường ngày.
- `FormatStyle.SHORT` — gọn, thường dùng dạng số và lược bỏ giây trong thành phần giờ.

**Điểm then chốt:** `FormatStyle` chỉ mô tả mức độ trình bày; **không phải** pattern cố định như `"dd/MM/yyyy"`, không phải `Locale`, không phải `ZoneId` và cũng không tự biến một ngày giờ không gắn múi giờ thành thời điểm toàn cầu.

Mục tiêu bài học: hiểu bốn mức style, cách sử dụng với date/time/date-time, chọn đúng kiểu dữ liệu `LocalDate`/`LocalTime`/`LocalDateTime`/`ZonedDateTime`, phân biệt locale với time zone, đọc/parse theo style, kiểm thử và tránh những lỗi do kỳ vọng một chuỗi output bất biến trên mọi JDK.

## 2. FormatStyle là enum gì?

`FormatStyle` là enum trong `java.time.format`:

```java
import java.time.format.FormatStyle;

FormatStyle full = FormatStyle.FULL;
FormatStyle longStyle = FormatStyle.LONG;
FormatStyle medium = FormatStyle.MEDIUM;
FormatStyle shortStyle = FormatStyle.SHORT;
```

Tên bốn hằng biểu thị **độ dài tương đối** của biểu diễn đã bản địa hóa. Ý nghĩa cụ thể do dữ liệu locale quyết định. Ví dụ:

| Style | Ngày theo `en-US`, minh họa | Ý nghĩa |
| --- | --- | --- |
| `FULL` | `Wednesday, October 28, 2026` | Có tên thứ và tên tháng đầy đủ |
| `LONG` | `October 28, 2026` | Tên tháng đầy đủ, không nhất thiết có thứ |
| `MEDIUM` | `Oct 28, 2026` | Rút gọn tên tháng |
| `SHORT` | `10/28/26` | Dùng dạng số gọn |

Đây là **ví dụ dựa trên dữ liệu locale en-US ở JDK hiện đại**, không phải bốn chuỗi cố định do enum quy định. Với `vi-VN`, `de-DE`, `ja-JP`… thứ tự ngày/tháng/năm, dấu phân cách, tên thứ, định dạng 12/24 giờ và từ nối có thể khác. JDK có thể cập nhật dữ liệu CLDR theo phiên bản nên việc dấu câu/viết tắt thay đổi không đồng nghĩa code sai.

Không có giá trị `FormatStyle.DEFAULT` và không thể truyền tên chuỗi `"FULL"` thay cho một enum mà không chuyển đổi tường minh. Trong code ứng dụng, ưu tiên dùng hằng `FormatStyle.FULL`, `LONG`, `MEDIUM`, `SHORT`.

## 3. Ba factory chính của DateTimeFormatter

`DateTimeFormatter` cung cấp các factory chuyên dụng:

| Factory | Dữ liệu trình bày | Ví dụ |
| --- | --- | --- |
| `ofLocalizedDate(style)` | Chỉ ngày | `DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)` |
| `ofLocalizedTime(style)` | Chỉ thời gian trong ngày, có thể kèm múi giờ tùy style | `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)` |
| `ofLocalizedDateTime(style)` | Cả ngày và giờ với cùng style | `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)` |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | Cả ngày và giờ, được chọn style riêng | `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)` |

**Locale được truyền bằng `withLocale(...)`**, không phải đối số trong bốn factory trên:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 10, 28);
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.FULL)
        .withLocale(Locale.US);

String display = date.format(formatter);
```

Đây là snippet đặt trong một phương thức. Kết quả điển hình với `Locale.US` là `Wednesday, October 28, 2026`.

`DateTimeFormatter` là **immutable và thread-safe**. `withLocale(locale)` tạo một formatter được cấu hình theo locale, không sửa formatter gốc. Không cần gọi `Locale.setDefault(...)` cho từng request, vì đó là trạng thái JVM có thể ảnh hưởng các request đồng thời.

### Chọn kiểu thời gian đầu vào phù hợp

| Kiểu đầu vào | Chứa thông tin gì? | Phù hợp |
| --- | --- | --- |
| `LocalDate` | Năm/tháng/ngày, không có giờ và zone | `ofLocalizedDate(...)` |
| `LocalTime` | Giờ/phút/giây, không có ngày/zone | `ofLocalizedTime(SHORT/MEDIUM)` khi pattern không yêu cầu zone |
| `LocalDateTime` | Ngày và giờ địa phương, **không chứa zone/offset** | Ngày/giờ với style không cần zone, tùy dữ liệu locale |
| `OffsetDateTime` | Ngày giờ và UTC offset | Định dạng cần offset; tên múi giờ đầy đủ có thể yêu cầu `ZoneId` |
| `ZonedDateTime` | Ngày giờ cùng `ZoneId`/offset | An toàn cho ví dụ FULL/LONG có thể in thông tin zone |
| `Instant` | Một thời điểm trên UTC timeline | Chuyển qua `atZone(zone)` để có ngày giờ địa phương trước khi format |

**Không được giả định rằng mọi style sẽ định dạng thành công với mọi `TemporalAccessor`.** Ví dụ `LocalDate` không có field của giờ, `LocalTime` không có field ngày; FULL/LONG time có thể yêu cầu tên zone, trong khi `LocalTime` và `LocalDateTime` không có thông tin này. Nếu thiếu field mà pattern yêu cầu, Java có thể ném `DateTimeException`, thường là `UnsupportedTemporalTypeException`.

## 4. Minh họa Java 17+: xem cả bốn style trên cùng một ngày giờ

Tạo file **`FormatStyleDemo.java`** (một lớp Java độc lập):

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatStyleDemo {
    public static void main(String[] args) {
        ZonedDateTime moment = ZonedDateTime.of(
                2026, 10, 28, 14, 35, 6, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));
        Locale locale = Locale.US;

        for (FormatStyle style : FormatStyle.values()) {
            DateTimeFormatter date = DateTimeFormatter
                    .ofLocalizedDate(style).withLocale(locale);
            DateTimeFormatter time = DateTimeFormatter
                    .ofLocalizedTime(style).withLocale(locale);
            DateTimeFormatter dateTime = DateTimeFormatter
                    .ofLocalizedDateTime(style).withLocale(locale);

            System.out.println("Style: " + style);
            System.out.println("Date: " + date.format(moment));
            System.out.println("Time: " + time.format(moment));
            System.out.println("DateTime: " + dateTime.format(moment));
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 FormatStyleDemo.java
java FormatStyleDemo
```

**Ví dụ output theo dữ liệu en-US của JDK 24** (ký tự khoảng trắng trước `PM` có thể là narrow no-break space, không nhất thiết là space ASCII):

```text
Style: FULL
Date: Wednesday, October 28, 2026
Time: 2:35:06 PM Indochina Time
DateTime: Wednesday, October 28, 2026, 2:35:06 PM Indochina Time
Style: LONG
Date: October 28, 2026
Time: 2:35:06 PM GMT+07:00
DateTime: October 28, 2026, 2:35:06 PM GMT+07:00
Style: MEDIUM
Date: Oct 28, 2026
Time: 2:35:06 PM
DateTime: Oct 28, 2026, 2:35:06 PM
Style: SHORT
Date: 10/28/26
Time: 2:35 PM
DateTime: 10/28/26, 2:35 PM
```

**Không viết automated test so sánh nguyên văn bảng output này trên mọi JDK.** Dữ liệu CLDR và locale provider có thể làm thay đổi chữ, dấu câu, tên zone hoặc loại dấu cách. Điều bền vững là: cùng một ngày giờ được biểu diễn bằng các mức độ chi tiết khác nhau; FULL thường đầy đủ hơn SHORT, còn giá trị ngày giờ gốc không thay đổi.

Giải thích từng thành phần:

1. `ZonedDateTime.of(...)` tạo ngày 28/10/2026 lúc 14:35:06 tại múi giờ `Asia/Ho_Chi_Minh`. Bằng cách truyền đối tượng **có zone**, cả FULL và LONG time đều có đủ dữ liệu nếu pattern cần tên/offset của zone.
2. `withLocale(Locale.US)` chọn quy tắc trình bày tiếng Anh Mỹ. Không đổi thời gian hay timezone của `moment`.
3. `ofLocalizedDate(style)` bỏ giờ khỏi chuỗi, `ofLocalizedTime(style)` bỏ ngày, và `ofLocalizedDateTime(style)` hiển thị cả hai.
4. `SHORT` có thể bỏ giây và dùng năm hai chữ số; điều này **không có nghĩa** thời gian bị làm tròn hoặc dữ liệu năm bị rút ngắn trong đối tượng `ZonedDateTime`.
5. Những chữ như `Indochina Time` và `GMT+07:00` là dữ liệu liên quan múi giờ/cách hiển thị, không được rút ra từ `Locale.US`.

## 5. So sánh FULL, LONG, MEDIUM, SHORT theo mục đích UI

### FULL: ưu tiên đầy đủ, người đọc dễ hiểu

`FULL` thích hợp khi cần đọc nguyên tên thứ/tháng và trong một số ngôn ngữ có thông tin vùng múi giờ rõ ràng. Với một lịch hẹn quan trọng hoặc email xác nhận, dạng dài có thể giảm mơ hồ so với `10/28/26`. Tuy nhiên FULL chiếm nhiều chỗ và còn phụ thuộc ngôn ngữ được chọn.

### LONG: vẫn rõ ngữ cảnh nhưng gọn hơn FULL

`LONG` thường giữ tên tháng đầy đủ, và với thời gian có thể có thông tin zone/offset. Đây là lựa chọn phù hợp với nội dung giải thích dài, trang chi tiết hoặc báo cáo, nhưng không nên mặc định LONG luôn giống FULL trừ tên thứ; cấu trúc pattern là dữ liệu locale.

### MEDIUM: thỏa hiệp giữa rõ nghĩa và diện tích

`MEDIUM` thường rút gọn tháng hoặc dấu phân tách ngày, vẫn hiển thị giờ/phút/giây tùy ngữ cảnh. Có thể là mặc định tiện dụng trong bảng và nội dung thường ngày nếu sản phẩm không yêu cầu một format chính xác. Nếu thông tin zone cần xuất hiện, phải bổ sung phần giải thích zone theo quy tắc UI; MEDIUM không đảm bảo luôn có zone.

### SHORT: tiết kiệm diện tích nhưng dễ mơ hồ

`SHORT` thường dùng các thành phần số, năm hai chữ số hoặc thời gian không có giây. Ví dụ `10/11/26` có thể bị hiểu là 10 tháng 11 hoặc 11 tháng 10 nếu đưa cho người dùng vùng khác. Chỉ dùng khi ngữ cảnh locale rõ và không làm người đọc nhầm, nhất là với hợp đồng, lịch hẹn giữa nhiều múi giờ và nội dung pháp lý.

| Yêu cầu giao diện | Style tham khảo | Cần cân nhắc |
| --- | --- | --- |
| Chi tiết lịch hẹn quan trọng | `FULL` hoặc `LONG` | Hiển thị múi giờ, ngày trong tuần |
| Trang thông tin đơn hàng | `LONG` hoặc `MEDIUM` | Đủ rõ ngày/tháng/năm |
| Danh sách hoặc bảng dữ liệu | `MEDIUM` hoặc `SHORT` | Kích thước cột, người xem hiểu locale nào |
| Giờ trong lịch dạng gọn | `SHORT` | Nếu cần giây/zone thì style có thể chưa đủ |
| Log ứng dụng/API | Không ưu tiên `FormatStyle` | Dùng ISO 8601 định dạng ổn định, độc lập locale |

Đây là gợi ý lựa chọn theo mức độ hiển thị, không phải quy định rằng mỗi style luôn chứa chính xác các thành phần như bảng.

## 6. Locale và múi giờ là hai khái niệm độc lập

- **`Locale`**: ngôn ngữ/vùng ưu tiên của **cách trình bày**, ví dụ `vi-VN`, `en-US`.
- **`ZoneId`**: múi giờ dùng để suy ra **giờ địa phương từ một `Instant`**, ví dụ `Asia/Ho_Chi_Minh`, `Europe/Berlin`.
- **`Instant`**: một thời điểm duy nhất trên UTC timeline, độc lập với các locale.

Một người dùng chọn giao diện tiếng Việt có thể đang ở Đức; người dùng chọn giao diện tiếng Anh có thể xem giờ tại Thành phố Hồ Chí Minh. Không được suy luận timezone chỉ từ language tag.

### Ví dụ cùng Instant, hai múi giờ

Tạo file độc lập **`TimeZoneFormatDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class TimeZoneFormatDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T07:35:06Z");

        ZonedDateTime inVietnam =
                instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ZonedDateTime inUtc = instant.atZone(ZoneOffset.UTC);

        System.out.println("Vietnam: "
                + inVietnam.toLocalDateTime() + " " + inVietnam.getOffset());
        System.out.println("UTC: "
                + inUtc.toLocalDateTime() + " " + inUtc.getOffset());

        DateTimeFormatter visible = DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
                .withLocale(Locale.US);
        System.out.println("Vietnam formatted: " + visible.format(inVietnam));
        System.out.println("UTC formatted: " + visible.format(inUtc));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TimeZoneFormatDemo.java
java TimeZoneFormatDemo
```

Hai dòng đầu **ổn định theo dữ liệu `java.time` trong ví dụ**:

```text
Vietnam: 2026-10-28T14:35:06 +07:00
UTC: 2026-10-28T07:35:06 Z
```

Hai dòng `formatted` cho `Locale.US` trên JDK 24 có dạng ví dụ:

```text
Vietnam formatted: Oct 28, 2026, 2:35 PM
UTC formatted: Oct 28, 2026, 7:35 AM
```

Các dòng hiển thị có thể khác ký tự khoảng trắng/dấu câu trên phiên bản JDK khác, nhưng cả hai biểu diễn **cùng một `Instant`**. Phân biệt hai cấp: chuyển `Instant` sang zone để tìm thời gian địa phương, sau đó định dạng theo locale để tạo chuỗi cho người đọc.

### Tại sao không lấy FULL time với LocalTime?

`LocalTime.of(14, 35)` chỉ biết giờ/phút/giây, không biết ngày, offset hay zone. Nếu pattern cho `FormatStyle.FULL` trong locale cụ thể yêu cầu tên zone, formatter không thể suy ra nó từ `LocalTime`, dẫn đến `DateTimeException`. `LocalDateTime` cũng không mang timezone. Dùng `ZonedDateTime` cho ví dụ FULL/LONG với zone. Đừng bắt lỗi rồi áp đặt `UTC` một cách âm thầm nếu timezone thực tế của người dùng chưa được xác định.

## 7. Kết hợp hai style riêng cho phần ngày và phần giờ

Đôi khi UI cần ngày khá chi tiết nhưng giờ rất gọn. Factory hai tham số hỗ trợ điều này:

```java
DateTimeFormatter mixed = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)
        .withLocale(Locale.US);

String label = mixed.format(zonedDateTime);
```

Đây là **snippet**, biến `zonedDateTime` phải có kiểu phù hợp như `ZonedDateTime`. Khác với một tham số `ofLocalizedDateTime(FormatStyle.MEDIUM)` (ngày và giờ đều MEDIUM), bản hai tham số cho phép:

- Ngày `LONG` + giờ `SHORT`.
- Ngày `FULL` + giờ `MEDIUM`.
- Ngày `SHORT` + giờ `LONG` (có thể cần timezone).

Tuy nhiên, các style được chọn vẫn dẫn tới **pattern phụ thuộc locale**. Không được dự đoán đầu ra bằng cách tự nối `ofLocalizedDate(...).format(value) + ", " + ofLocalizedTime(...).format(value)`: kết hợp ngày giờ trong một ngôn ngữ có thể có từ nối hoặc thay đổi thứ tự thành phần. Hãy để `ofLocalizedDateTime(...)` dùng quy tắc kết hợp của locale.

Nếu sản phẩm bắt buộc một layout cố định hoặc một định dạng giao thức, dùng `DateTimeFormatter.ofPattern(pattern, locale)` hay các formatter ISO chuẩn. Không dùng các localized style cho trường dữ liệu cần so sánh byte-for-byte giữa hai hệ thống.

## 8. Phân biệt FormatStyle và custom pattern

| Chủ đề | `FormatStyle` với factory localized | `DateTimeFormatter.ofPattern(...)` |
| --- | --- | --- |
| Quy tắc thứ tự thành phần | Do locale/provider quyết định | Do người viết pattern quyết định |
| Ký hiệu ngày/tháng/giờ | Thường bản địa hóa theo locale | Điều khiển bằng các ký tự pattern, còn tên tháng/AM-PM phụ thuộc locale |
| Khả năng đổi theo JDK locale data | Có | Có đối với phần tên/bản địa hóa, nhưng cấu trúc pattern cố định |
| Dùng cho giao diện đa ngôn ngữ | Thường thuận tiện | Hữu ích khi thiết kế cần bố cục cụ thể |
| Dùng làm giao thức máy-máy | Không nên | Ưu tiên chuẩn ISO 8601 thay vì pattern locale tự tạo |
| Khả năng thể hiện giây, zone cụ thể | Theo style và provider | Có thể điều khiển tường minh bằng pattern |

Ví dụ:

```java
DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.GERMANY);

DateTimeFormatter fixedPattern = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.GERMANY);
```

`localized` tuân theo quy tắc SHORT do locale provider xác định; `fixedPattern` cố định vị trí ngày/tháng/năm và độ dài năm bốn chữ số. Vì vậy không có bảo đảm hai formatter cho cùng một chuỗi.

Một điểm dễ lẫn: `MM` là **tháng**, `mm` là **phút**; `HH` là giờ 24 tiếng, `hh` là giờ theo đồng hồ 12 tiếng (thường cần `a` cho AM/PM). Không nên sao chép pattern từ ví dụ tiếng Anh mà bỏ qua cách đọc của người dùng địa phương. Với năm, `uuuu` là proleptic year; `yyyy` là year-of-era. Chọn theo mô hình dữ liệu và quy tắc hệ thống.

## 9. Parse với localized FormatStyle và những giới hạn

`DateTimeFormatter` không chỉ có `format` mà còn hỗ trợ `parse`. Có thể dùng cùng style/locale để phân tích một chuỗi ngày:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

DateTimeFormatter parser = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(Locale.US);

String input = "10/28/26";
LocalDate parsed = LocalDate.parse(input, parser);
```

Ví dụ trên tương ứng cách hiển thị en-US SHORT phổ biến và là **snippet**; kết quả mong đợi là `2026-10-28` trong môi trường áp dụng pattern đó. Nhưng pattern SHORT có thể dùng năm hai chữ số, nên việc parse chịu **quy tắc xử lý năm rút gọn**; nếu input là dữ liệu pháp lý hoặc sinh từ hệ thống máy, nên tránh năm hai chữ số và tránh phụ thuộc locale ngầm.

Cần lưu ý:

1. **Locale phải khớp** với chuỗi đã nhập: `10/28/26` theo Mỹ không nên được hiểu tùy tiện bằng một formatter `vi-VN` hoặc `de-DE`.
2. **Khi parse FULL/LONG có tên tháng/thứ**, ngôn ngữ và dạng chữ phải được provider hỗ trợ đúng. Một thứ trong tuần không khớp ngày có thể khiến parse thất bại.
3. **Không dùng localized text làm định dạng lưu trữ**: nó phụ thuộc cấu hình JDK, ký hiệu văn hóa và có thể mơ hồ.
4. `DateTimeFormatter` mặc định có resolver style và quy tắc chuyển trường về `LocalDate`/`LocalTime`; nếu cần kiểm tra nghiêm ngặt, xem xét `withResolverStyle(ResolverStyle.STRICT)` và kiểm thử theo trường đã chọn.
5. Một formatter time FULL/LONG có thể yêu cầu zone khi parse; cần mô hình temporal phù hợp.
6. **Không giả định format → parse có thể round-trip đầy đủ**: SHORT có thể bỏ giây hoặc năm đủ bốn chữ số, còn formatter chỉ ngày sẽ không lưu giờ.

Đối với API và dữ liệu giữa các dịch vụ, nên dùng những biểu diễn chuẩn như `Instant.toString()`/`Instant.parse(...)` hoặc `DateTimeFormatter.ISO_OFFSET_DATE_TIME`, tùy hợp đồng của dữ liệu. Localized style được thiết kế cho **giao tiếp với con người**.

## 10. Kiểm thử đúng đối với FormatStyle

Test tốt không chỉ so sánh một chuỗi hardcode. Cần kiểm thử:

| Trường hợp | Kiểm tra |
| --- | --- |
| Bốn `FormatStyle` | Tất cả factory trả formatter hợp lệ và format được với temporal thích hợp |
| Ngày đủ ngày/tháng/năm | Đúng ngày lịch, không lệch do đổi timezone ngoài ý muốn |
| Time FULL/LONG | Temporal có zone nếu locale yêu cầu zone |
| `LocalDate` với `ofLocalizedTime` | Nhận lỗi do thiếu trường giờ; không lặng lẽ gán 00:00 |
| `LocalTime` với `ofLocalizedDate` | Nhận lỗi do thiếu ngày |
| Locale en-US và vi-VN | Quan sát thứ tự ngày/tháng, chữ và quy ước 12/24 giờ |
| Múi giờ khác nhau | Cùng `Instant` hiển thị giờ địa phương khác nhưng không đổi instant |
| Ngày chuyển năm hoặc DST | Thời điểm gần ranh giới có thể rơi vào ngày khác theo zone |
| Parse SHORT | Cẩn thận năm hai chữ số và chuỗi nhập mơ hồ |
| Thay JDK/CLDR | Chấp nhận thay đổi trình bày hợp lệ, chỉ đặt snapshot tests có phạm vi/phiên bản rõ |

### Tránh snapshot test phụ thuộc dữ liệu locale quá chặt

Một snapshot kiểu “FULL luôn là `Wednesday, October 28, 2026 at ...`” sẽ dễ hỏng khi provider thay dấu câu, chữ nối, spacing hoặc tên zone. Nếu mục tiêu test là nghiệp vụ, hãy kiểm tra thời điểm và locale đầu vào đúng, còn output snapshot chỉ dùng trong môi trường CI có JDK/provider được ghim. Với sản phẩm cần chữ hiển thị chính xác như thiết kế, cân nhắc pattern tùy chỉnh hoặc nội dung được quản lý bằng resource.

### Khi tính năng cần tương thích ngược

`java.time` và `FormatStyle` phù hợp với Java 8+; không phải chỉ có từ Java 17. Với hệ thống dùng `java.text.DateFormat`, có các mức `DateFormat.FULL`/`LONG`/`MEDIUM`/`SHORT` tương tự về mục đích, nhưng đó là **API khác và các formatter cũ là mutable/not generally thread-safe**. Không nhập nhằng hằng của hai API hoặc giả định một `DateFormat` và một `DateTimeFormatter` luôn cho output byte-for-byte giống nhau.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Xem `FULL`/`LONG` là pattern toàn cầu cố định | Sai khi đổi locale hoặc JDK | Hiểu đây là mức hiển thị, không phải mẫu cố định |
| Format `LocalTime` bằng FULL rồi gặp lỗi | Thiếu zone trong temporal cho pattern time | Dùng `ZonedDateTime` hoặc chọn style phù hợp |
| Chọn `Locale.US` rồi nghĩ giờ đã tự chuyển sang Mỹ | Locale chỉ ảnh hưởng ngôn ngữ/cách trình bày | Chuyển `Instant` bằng `ZoneId` riêng |
| Dùng `LocalDateTime` để diễn tả thời điểm UTC | Không có offset/zone nên không định danh instant | Dùng `Instant`/`OffsetDateTime`/`ZonedDateTime` |
| Dùng `SHORT` khi cần giây và đầy đủ múi giờ | Có thể bị lược bỏ thông tin quan trọng | Chọn style khác hoặc pattern có yêu cầu rõ |
| Hardcode `10/28/26` cho mọi người dùng | Người ở vùng khác đọc sai ngày/tháng | Chọn locale phù hợp, hoặc biểu diễn không mơ hồ |
| Dùng localized formatter làm chuẩn serialization | Chuỗi thay đổi khi JDK/locale thay đổi | Dùng ISO 8601 và một hợp đồng thời gian có zone/offset |
| Nối tay chuỗi date + time | Sai thứ tự/cấu trúc tiếng của một locale | Dùng `ofLocalizedDateTime(...)` |
| Dùng `withLocale` rồi mong thay đổi đối tượng gốc | Formatter immutable | Giữ và sử dụng đối tượng formatter được trả về |
| Parse SHORT hai chữ số năm không kiểm tra | Có thể hiểu năm khác mong muốn | Dùng year bốn chữ số theo hợp đồng nhập liệu |
| Thay đổi `Locale.setDefault` cho mỗi request | Ảnh hưởng nhiều luồng trong JVM | Truyền locale tường minh cho formatter |
| So sánh exact output của nhiều phiên bản CLDR | Test giòn, báo lỗi giả | Ghim môi trường test hoặc kiểm thử theo semantic |
| Nhầm `FormatStyle` với hằng `DateFormat` | Sử dụng sai API hoặc kiểu tham số | Dùng import `java.time.format.FormatStyle` đúng |

## 12. Câu hỏi ôn tập

**Câu 1.** `FormatStyle.FULL` luôn chứa tên thứ và tên múi giờ trong mọi formatter?

**Đáp án:** Không. Nội dung phụ thuộc `Locale` và factory date/time/date-time. Date-only không có thông tin múi giờ; time FULL trong nhiều locale có thể cần zone để in tên múi giờ.

**Câu 2.** Muốn hiển thị ngày LONG nhưng giờ SHORT, cần API nào?

**Đáp án:** `DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT).withLocale(locale)`. Cách này dùng quy tắc ghép ngày/giờ của locale.

**Câu 3.** Chỉ có `LocalDate.of(2026, 10, 28)`, có thể dùng `ofLocalizedTime(SHORT)` để tự lấy 00:00?

**Đáp án:** Không. `LocalDate` không có field giờ. Java có thể ném `DateTimeException` vì temporal thiếu thông tin; nếu muốn hiển thị 00:00, phải xác định thời gian tường minh.

**Câu 4.** Hai người dùng xem cùng một `Instant` nhưng khác `ZoneId`. Có phải dữ liệu sự kiện đã đổi?

**Đáp án:** Không. `Instant` không đổi; chỉ ngày giờ địa phương và cách hiển thị thay đổi.

**Câu 5.** `FormatStyle.SHORT` có nên dùng làm định dạng database cho ngày?

**Đáp án:** Không. Đây là chuỗi bản địa hóa dành cho người đọc, có thể mơ hồ và thay đổi theo JDK/provider. Dữ liệu máy nên lưu `LocalDate` hoặc chuẩn ISO 8601 theo thiết kế.

**Câu 6.** Vì sao gọi `withLocale(Locale.forLanguageTag("vi-VN"))` chưa đảm bảo giờ hiện tại là giờ Việt Nam?

**Đáp án:** Locale chỉ chọn quy tắc hiển thị; cần `ZoneId.of("Asia/Ho_Chi_Minh")` hoặc zone thực tế của người dùng để chuyển `Instant`.

**Câu 7.** Vì sao hai JDK có thể cho dấu câu/khoảng trắng khác nhau ở DATE FULL dù cùng input?

**Đáp án:** Cách thể hiện do dữ liệu locale (thường từ CLDR) và provider của mỗi JDK cung cấp; các bản cập nhật có thể đổi pattern, tên tháng hoặc punctuation.

## 13. Ghi nhớ

- `FormatStyle` có bốn giá trị **FULL, LONG, MEDIUM, SHORT**, mô tả mức độ chi tiết **theo locale**, không phải pattern cố định.
- Dùng `DateTimeFormatter.ofLocalizedDate`, `ofLocalizedTime`, `ofLocalizedDateTime`; có thể đặt **hai style độc lập** cho ngày/giờ.
- Luôn chọn đúng temporal chứa đủ các trường formatter cần. Đặc biệt, time FULL/LONG có thể đòi hỏi thông tin zone.
- **`Locale` điều khiển cách thể hiện; `ZoneId` điều khiển giờ địa phương**. Cùng một `Instant` không bị thay đổi khi hiển thị theo vùng khác.
- Dùng localized style cho **UI**; dữ liệu/API nên dùng định dạng ISO và hợp đồng thời gian rõ ràng. Không so sánh output bản địa hóa như một chuỗi bất biến trên mọi JDK.

Tài liệu chính thức:

- [Java SE 21 — FormatStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/FormatStyle.html)
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)
- [Unicode CLDR — Date/Time patterns](https://cldr.unicode.org/translation/date-time/date-time-patterns)
