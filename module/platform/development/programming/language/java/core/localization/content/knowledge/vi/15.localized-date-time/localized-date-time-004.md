# DateTimeFormatter.ofPattern và khác biệt với mẫu ngày giờ được chọn theo locale

## 1. Vấn đề cần hiểu

Trong Java, cùng một ngày **28 tháng 10 năm 2026** có thể được hiển thị dưới nhiều cấu trúc tùy ngôn ngữ và khu vực:

- Ở giao diện tiếng Việt: ngày thường được đặt trước tháng.
- Ở giao diện tiếng Anh tại Hoa Kỳ: tháng thường được đặt trước ngày trong các kiểu viết ngày phổ biến.
- Ở một số khu vực khác: năm có thể đứng trước hoặc dấu phân cách có thể khác.
- Tên thứ, tên tháng, chữ chỉ buổi và một số ký hiệu cũng có thể đổi theo locale.

Khi dùng `java.time.format.DateTimeFormatter`, có hai hướng quan trọng:

1. **`DateTimeFormatter.ofPattern(pattern, locale)`:** người lập trình **tự viết cấu trúc** `pattern`, ví dụ `"dd/MM/uuuu"`. Locale ảnh hưởng các phần phụ thuộc ngôn ngữ như tên tháng hoặc thứ, nhưng **không tự đảo trật tự `dd/MM/uuuu` thành `MM/dd/uuuu`**.
2. **`DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)`**, `ofLocalizedTime(...)`, `ofLocalizedDateTime(...)`: Java chọn **mẫu hiển thị ngày/giờ phù hợp locale và `FormatStyle`**. Thứ tự các trường, dấu phân cách, tên tháng và mức độ chi tiết có thể khác giữa các locale.

**Đây là điểm cốt lõi của bài:** chọn `Locale` cho một pattern tự viết không đồng nghĩa yêu cầu Java tự tìm mẫu ngày giờ quy ước của vùng đó. Một pattern do người viết chỉ định và một localized pattern được hệ thống chọn là **hai cơ chế khác nhau**.

Bài dùng Java 17+, API `java.time` hiện đại; không trộn cú pháp `DateTimeFormatter` với `java.text.SimpleDateFormat` nếu chưa kiểm tra khác biệt.

## 2. Bốn thành phần cần phân biệt

| Thành phần | Ví dụ | Quyết định điều gì? |
| --- | --- | --- |
| Giá trị ngày/giờ | `LocalDate.of(2026, 10, 28)` | Ngày nghiệp vụ thực sự |
| Pattern tự viết | `"dd/MM/uuuu"` | **Thứ tự trường và dấu phân cách cố định** do developer chọn |
| Locale | `Locale.forLanguageTag("vi-VN")` | Ngôn ngữ tên tháng/thứ và lựa chọn localized pattern |
| FormatStyle | `SHORT`, `MEDIUM`, `LONG`, `FULL` | Mức chi tiết khi Java tìm mẫu theo locale |

Múi giờ lại là tham số **độc lập**:

- `Locale` mô tả ngôn ngữ và quy ước trình bày.
- `ZoneId` xác định cách một `Instant` được chuyển thành giờ địa phương.
- `DateTimeFormatter` quyết định cách viết giờ địa phương ra ký tự.

Ví dụ người dùng chọn tiếng Việt nhưng đang ở Tokyo: thông điệp có thể bằng tiếng Việt, date pattern theo `vi-VN`, còn giờ sự kiện theo `Asia/Tokyo`. Không suy tự động `ZoneId.of("Asia/Ho_Chi_Minh")` chỉ từ `Locale.forLanguageTag("vi-VN")`.

## 3. `ofPattern`: cấu trúc do developer nắm quyền

API phổ biến:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu",
        Locale.forLanguageTag("vi-VN"));
```

Với một `LocalDate` như `2026-10-28`, formatter trên tạo chuỗi `28/10/2026`. Đây là pattern số có ngày/tháng/năm cố định; nếu đổi locale thành `Locale.US` mà **không đổi pattern**, kết quả cấu trúc vẫn là `28/10/2026` với bộ ký tự số mặc định.

`DateTimeFormatter.ofPattern("dd/MM/uuuu")` (không truyền `Locale`) sử dụng locale mặc định của category `Locale.Category.FORMAT` khi tạo formatter. Trong ứng dụng đa người dùng nên **truyền locale tường minh**, tránh kết quả bị phụ thuộc cấu hình JVM.

### 3.1. Một số pattern letter quan trọng

| Ký tự | Ý nghĩa với `DateTimeFormatter` | Ví dụ / chú ý |
| --- | --- | --- |
| `u`, `uuuu` | Năm theo lịch proleptic | `2026`, hữu ích với strict parse ISO |
| `y`, `yyyy` | Year-of-era | Cần để ý resolver và era trong parse nghiêm ngặt |
| `M`, `MM` | Tháng dạng số | `10`, dùng `MM` cho đủ 2 chữ số |
| `MMM`, `MMMM` | Tên tháng dạng text | `Oct` hoặc `October` theo locale |
| `L` | Tháng dạng độc lập/stand-alone | Có thể khác dạng sử dụng trong câu ở một số ngôn ngữ |
| `d`, `dd` | Ngày trong tháng | `28` |
| `D` | Ngày trong năm | **Không** phải ngày trong tháng |
| `E`, `EEEE` | Tên thứ trong tuần | `Wed` hoặc `Wednesday` theo locale |
| `e`/`c` | Thứ theo đánh số/tên bản địa | Phụ thuộc locale và độ dài pattern |
| `H`, `HH` | Giờ 0–23 | `14`, không cần AM/PM |
| `h`, `hh` | Giờ 1–12 | Thường đi kèm `a` |
| `m`, `mm` | **Phút** | `05`; rất dễ nhầm với `M` tháng |
| `s`, `ss` | Giây | `09` |
| `S`, `SSS` | Chữ số của phần giây | `123` mili-giây trong ví dụ 3 chữ số |
| `a` | AM/PM | Văn bản theo locale |
| `X`, `XXX` | Offset ISO-8601 | Ví dụ `+07:00` với `XXX` |
| `V`, `VV` | Zone ID | Ví dụ `Asia/Ho_Chi_Minh` với `VV` |
| `z` | Tên múi giờ theo locale | Cần có zone và dữ liệu tên vùng |
| `Y` | Week-based-year | **Không thay** `u` hoặc `y` cho ngày lịch thông thường |

Cú pháp dạng `"dd/MM/uuuu HH:mm"` ghép ngày và giờ; dấu `/`, dấu cách, dấu `:` trong pattern là các ký tự literal. Nếu locale khác thường dùng thứ tự hoặc dấu khác, `ofPattern` **không tự sửa chúng**.

Đặc biệt nguy hiểm:

- `"MM/dd/uuuu"` và `"dd/MM/uuuu"` có thể cho hai ý nghĩa khác nhau khi parse `03/04/2026`.
- `"YYYY-MM-dd"` dùng week-based-year, có thể tạo năm **khác** gần đầu/cuối năm. Dùng `"uuuu-MM-dd"` cho lịch ISO khi cần năm thực của ngày.
- `"mm"` là phút, `"MM"` mới là tháng.
- `"DD"` là ngày thứ bao nhiêu trong năm, `"dd"` mới là ngày trong tháng.
- Pattern `"hh:mm"` không chỉ rõ AM/PM, khiến giờ có thể mơ hồ; thêm `a` nếu dùng 12 giờ.

### 3.2. Locale tác động đến những phần nào của pattern tùy chỉnh?

Ví dụ:

```java
DateTimeFormatter us =
        DateTimeFormatter.ofPattern("EEEE, dd MMMM uuuu", Locale.US);
DateTimeFormatter vi =
        DateTimeFormatter.ofPattern(
                "EEEE, dd MMMM uuuu", Locale.forLanguageTag("vi-VN"));
```

Hai formatter đều giữ **thứ tự: thứ → ngày → tháng → năm**, kèm dấu phẩy và dấu cách theo pattern. Tên thứ và tháng có thể là tiếng Anh hoặc tiếng Việt, tùy locale và dữ liệu được hỗ trợ. Vì tên tháng phụ thuộc dữ liệu CLDR/JDK, không nên cố định mọi chuỗi tháng viết tắt/viết hoa trong unit test chạy đa nền tảng.

**`Locale` không tự làm cho pattern cố định trở thành quy ước ngày tháng bản địa.** Việc dùng `Locale.US` với `"dd/MM/uuuu"` vẫn giữ ngày đứng trước tháng, dù đó không phải dạng ngắn thông dụng của Hoa Kỳ.

## 4. `ofLocalizedDate`: Java chọn mẫu thay developer

Khi muốn theo quy ước địa phương, dùng các factory localized:

```java
DateTimeFormatter dateFormat =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(locale);

DateTimeFormatter timeFormat =
        DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                .withLocale(locale);

DateTimeFormatter dateTimeFormat =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(locale);
```

Chúng lấy **mẫu định dạng tương ứng với `FormatStyle` và locale**, chứ không phải chỉ đổi tên tháng trên một cấu trúc đã viết sẵn. Theo tài liệu Java 17, localized pattern được tra cứu khi formatter thực sự sử dụng, dựa trên locale và chronology.

Các style:

| `FormatStyle` | Ý tưởng | Ghi chú |
| --- | --- | --- |
| `SHORT` | Ngắn, thường có số và ít trường | Phù hợp bảng/hộp nhỏ; có thể mơ hồ nếu không có ngữ cảnh |
| `MEDIUM` | Mức chi tiết trung bình | Dễ đọc hơn SHORT trong nhiều locale |
| `LONG` | Tương đối đầy đủ | Có thể đưa tên tháng, tên vùng khi định dạng giờ |
| `FULL` | Đầy đủ nhất | Có thể bao gồm thứ và tên múi giờ |

**Không có pattern duy nhất cho mọi locale.** `FormatStyle.SHORT` không có nghĩa bắt buộc là `"dd/MM/yy"`; dữ liệu mỗi locale quyết định thứ tự và dấu phân cách. `FULL` cũng không được định nghĩa là một chuỗi literal cụ thể dùng chung mọi phiên bản JDK.

Đối với định dạng **time-only** và **date-time**, kiểu `FULL` hoặc `LONG` có thể yêu cầu thông tin zone. Nếu dùng `LocalDateTime` (không chứa zone) với style cần tên múi giờ, có thể gặp `DateTimeException`. Dùng `ZonedDateTime` hoặc cung cấp `withZone(zone)` khi phù hợp ngữ nghĩa.

### 4.1. Bảng so sánh trực tiếp

| Tiêu chí | `ofPattern("dd/MM/uuuu", locale)` | `ofLocalizedDate(SHORT).withLocale(locale)` |
| --- | --- | --- |
| Ai chọn thứ tự ngày/tháng/năm? | Developer | Dữ liệu locale/JDK |
| Ai chọn dấu phân cách? | Developer trong pattern | Mẫu bản địa |
| Đổi locale có tự đảo vị trí trường? | **Không** | **Có thể**, theo locale |
| Tên tháng/thứ có thể được bản địa hóa? | Có, nếu pattern chứa `MMM/MMMM/EEEE` | Có, theo localized pattern |
| Kiểm soát từng ký tự hiển thị? | Rất cao | Ít hơn; dựa trên quy ước locale |
| Phù hợp | Chuẩn input đặc thù, định dạng thiết kế cố định, file export có contract | Giao diện cho người dùng đa khu vực |
| Rủi ro | Áp đặt cấu trúc của một nước cho tất cả | Output thay đổi khi dữ liệu locale/JDK thay đổi |

Nếu sản phẩm muốn **ngày luôn `dd/MM/uuuu` ở mọi thị trường**, hãy chủ động dùng `ofPattern`. Nếu muốn **ngày theo chuẩn người dùng quen đọc**, ưu tiên `ofLocalizedDate` và chọn locale theo user preference.

## 5. Chương trình Java 17 đầu tiên: cùng pattern, hai locale

Tạo tệp `PatternVsLocalizedDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class PatternVsLocalizedDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);
        Locale us = Locale.US;
        Locale vi = Locale.forLanguageTag("vi-VN");

        DateTimeFormatter customUS =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", us);
        DateTimeFormatter customVI =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", vi);

        String fixedUS = date.format(customUS);
        String fixedVI = date.format(customVI);

        System.out.println("ISO=" + date);
        System.out.println("customUS=" + fixedUS);
        System.out.println("customVI=" + fixedVI);
        System.out.println("sameCustom=" + fixedUS.equals(fixedVI));

        DateTimeFormatter localizedUS =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(us);
        DateTimeFormatter localizedVI =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(vi);

        // Dạng SHORT do dữ liệu locale của JDK quyết định:
        System.out.println("localizedUS=" +
                date.format(localizedUS));
        System.out.println("localizedVI=" +
                date.format(localizedVI));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 PatternVsLocalizedDemo.java
java PatternVsLocalizedDemo
```

**Bốn dòng đầu có thể xác định chính xác:**

```text
ISO=2026-10-28
customUS=28/10/2026
customVI=28/10/2026
sameCustom=true
```

Hai dòng `localizedUS=...` và `localizedVI=...` luôn được in tiếp theo, nhưng **phần giá trị sau dấu `=` phụ thuộc dữ liệu locale/provider của JDK**. Vì thế không đưa ra một stdout literal duy nhất cho các dòng này. Hãy chạy để quan sát cách mẫu SHORT khác nhau theo cấu hình runtime.

Kết luận từ code: **đổi locale của một pattern số tự viết không tự đổi `dd/MM/uuuu` thành `MM/dd/uuuu`**; factory localized được dùng khi cần Java quyết định thứ tự/dấu theo locale.

## 6. `withLocale` không có tác dụng giống nhau trên hai kiểu formatter

`DateTimeFormatter` là immutable. `withLocale(locale)` trả về **một formatter mới** có locale mới, không sửa instance hiện tại.

Tình huống A — formatter **tự viết pattern**:

```java
DateTimeFormatter fixed =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US);
DateTimeFormatter fixedVi =
        fixed.withLocale(Locale.forLanguageTag("vi-VN"));
```

`fixedVi` vẫn giữ thứ tự và dấu `dd/MM/uuuu`. Nếu pattern có `MMMM`/`EEEE`, locale mới có thể làm tên tháng/thứ khác; pattern dạng số không có cấu trúc bản địa tự chọn.

Tình huống B — formatter **được tạo theo style**:

```java
DateTimeFormatter localized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.US);

DateTimeFormatter localizedVi =
        localized.withLocale(Locale.forLanguageTag("vi-VN"));
```

`localizedVi` vẫn là formatter theo style `LONG` nhưng **mẫu LONG sẽ được tra cứu theo locale mới**. Thứ tự trường và ngôn ngữ có thể thay đổi, không phải chỉ thay nhãn tháng.

### 6.1. `withLocale`, `localizedBy` và `DecimalStyle`

Đừng giả định chỉ cần gọi `withLocale` thì mọi số năm/tháng/ngày sẽ chuyển sang hệ chữ số riêng của locale. Theo Java 17:

- `withLocale(locale)` thay locale dùng cho phần cần tra cứu ngôn ngữ và localized pattern.
- `withDecimalStyle(DecimalStyle.of(locale))` áp dụng ký hiệu thập phân, dấu âm và chữ số bản địa hóa khi cần.
- `localizedBy(locale)` (Java 10+) có thể áp dụng thêm những thiết lập được chỉ định bởi Unicode locale extensions như numbering system, calendar, region override và timezone, tùy trường hợp.

Đây là những cơ chế khác nhau. Không tự động coi `withLocale` có nghĩa “đã đổi chronology và timezone”. Đối với dữ liệu API có định dạng chuẩn ISO, nhiều trường hợp nên dùng các formatter ISO cố định thay vì định dạng theo ngôn ngữ.

## 7. Khi muốn biết localized pattern thực tế là gì?

Java 17 có phương thức:

```java
String pattern = DateTimeFormatterBuilder.getLocalizedDateTimePattern(
        FormatStyle.SHORT,
        null,
        IsoChronology.INSTANCE,
        Locale.US);
```

Nó trả **pattern cho phần date** với style, chronology và locale đã chọn. Với time-only, truyền `null` ở date style và một time style; với date-time, truyền cả hai. Không được để **cả date style lẫn time style đều null**.

### Ví dụ độc lập: in mẫu SHORT của ba locale

Tệp `LocalizedPatternInspection.java`:

```java
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedPatternInspection {
    public static void main(String[] args) {
        for (String tag : new String[]{"en-US", "vi-VN", "fr-FR"}) {
            Locale locale = Locale.forLanguageTag(tag);
            String datePattern =
                    DateTimeFormatterBuilder.getLocalizedDateTimePattern(
                            FormatStyle.SHORT,
                            null,
                            IsoChronology.INSTANCE,
                            locale);

            System.out.println(tag + " -> " + datePattern);
        }
    }
}
```

```bash
javac -encoding UTF-8 LocalizedPatternInspection.java
java LocalizedPatternInspection
```

Chương trình in **ba dòng** theo thứ tự `en-US`, `vi-VN`, `fr-FR`, mỗi dòng chứa pattern dùng theo dữ liệu locale. Nội dung của pattern có thể khác giữa các phiên bản JDK/CLDR và provider; không nên xem một snapshot như quy tắc vĩnh viễn.

**Khi nào hữu ích?** Để chẩn đoán vì sao localized formatter in tháng trước ngày ở locale này nhưng ngày trước tháng ở locale kia, hoặc để viết test theo runtime được cố định. Phương thức này là **công cụ xem mẫu**; không cần phải lấy chuỗi rồi gọi `ofPattern` trong mọi lượt format. Thông thường `ofLocalizedDate(FormatStyle.SHORT).withLocale(locale)` đã là cách rõ nghĩa và phù hợp hơn.

### 7.1. Không “đóng băng” localized pattern một cách vô ý

Nếu tại lúc khởi động bạn lấy pattern SHORT của `Locale.US` rồi sử dụng:

```java
String usPattern =
        DateTimeFormatterBuilder.getLocalizedDateTimePattern(
                FormatStyle.SHORT, null,
                IsoChronology.INSTANCE, Locale.US);

DateTimeFormatter fixedFromUS =
        DateTimeFormatter.ofPattern(usPattern, Locale.US);
```

Sau đó chỉ gọi `fixedFromUS.withLocale(viLocale)`, formatter mới **không tự lấy pattern SHORT của `vi-VN`**. Pattern `usPattern` đã được chọn và gắn cố định từ lúc tạo `ofPattern`.

Đoạn mã trên là minh họa **trong một method** có biến `viLocale` và import tương ứng. Nếu thực sự cần tự tùy chỉnh mẫu cho nhiều locale, phải quản lý **một pattern rõ cho mỗi locale** và version; còn nếu không cần tùy chỉnh, dùng localized factory.

## 8. Tự viết pattern cho từng locale: có hợp lý không?

Có. Một sản phẩm có thể cố tình chọn mẫu riêng cho từng ngôn ngữ thay vì dùng mẫu của JDK, chẳng hạn:

| Locale | Pattern do sản phẩm định nghĩa |
| --- | --- |
| `vi-VN` | `"dd/MM/uuuu"` |
| `en-US` | `"MM/dd/uuuu"` |
| `ja-JP` | `"uuuu/MM/dd"` |

Lúc đó lựa chọn locale vẫn quyết định **pattern nào được lấy**, nhưng đây là **logic riêng của sản phẩm**, không phải `ofPattern` tự động biến đổi một pattern duy nhất.

Ví dụ minh họa:

```java
String pattern = switch (locale.toLanguageTag()) {
    case "vi-VN" -> "dd/MM/uuuu";
    case "en-US" -> "MM/dd/uuuu";
    case "ja-JP" -> "uuuu/MM/dd";
    default -> "uuuu-MM-dd";
};

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(pattern, locale);
```

Đây là code nằm **trong method** với `locale` đã xác định; Java 17 hỗ trợ switch expression. Pattern mapping này phải được duy trì thủ công, có test, chính sách fallback và có thể không phản ánh toàn bộ quy ước CLDR (chẳng hạn số nhiều, lịch khác ISO, tên thời đại). Một giải pháp dùng `ResourceBundle` lưu mẫu theo locale cũng là lựa chọn có chủ đích, nhưng phải kiểm tra cú pháp tất cả pattern và xử lý fallback đúng.

**Khuyến nghị chọn hướng:**

- **Pattern máy/API cố định:** ưu tiên formatter ISO chuẩn hoặc `ofPattern` có contract rõ ràng.
- **Ngày giờ tự nhiên theo người dùng:** `ofLocalizedDate/Time/DateTime(FormatStyle)` với locale tường minh.
- **Thiết kế UI đòi pattern riêng từng khu vực:** mapping/config/custom pattern do sản phẩm quản lý, vẫn dùng `ofPattern` để biên dịch pattern.
- **Kịch bản chỉ đổi ngôn ngữ tên tháng/thứ, không đổi layout:** `ofPattern(..., locale)` là phù hợp.

## 9. Ngày, thời gian và múi giờ: chọn đúng dữ liệu đầu vào

`LocalDate`, `LocalDateTime`, `Instant` và `ZonedDateTime` có ý nghĩa khác nhau:

- `LocalDate` là ngày trong lịch, không có giờ hay múi giờ; dùng cho ngày sinh, ngày hạn theo lịch.
- `LocalTime` là giờ trong ngày, không có ngày hoặc múi giờ.
- `LocalDateTime` có cả ngày/giờ nhưng **chưa chứa vùng hoặc offset**; không xác định duy nhất một thời điểm toàn cầu.
- `Instant` biểu diễn thời điểm tuyệt đối.
- `ZonedDateTime` chứa ngày/giờ theo vùng, cho phép dùng pattern có zone và offset.

Một pattern có `HH:mm` cần dữ liệu có thời gian; định dạng `LocalDate` bằng pattern cần giờ có thể ném `UnsupportedTemporalTypeException`. Một pattern có `XXX` cần offset hoặc một temporal mà formatter có thể cung cấp offset qua zone; không tự đoán từ `LocalDateTime`.

### 9.1. `withZone` đổi góc nhìn thời gian, không đổi locale

Để format một `Instant` thành giờ Việt Nam:

```java
Instant instant = Instant.parse("2026-10-28T07:30:00Z");

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm VV", Locale.US)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String result = formatter.format(instant);
```

Kết quả `result` là `2026-10-28 14:30 Asia/Ho_Chi_Minh`. Đây là code minh họa trong method với các import `java.time.Instant`, `ZoneId`, `java.time.format.DateTimeFormatter` và `java.util.Locale`.

Chuyển từ `ZoneId.of("Asia/Ho_Chi_Minh")` sang `ZoneId.of("Europe/Paris")` làm giờ địa phương thay đổi theo quy tắc múi giờ, không làm `Locale.US` tự biến thành tiếng Pháp. Muốn tiếng Pháp, vẫn phải truyền `Locale.FRANCE` cho formatter hoặc chọn `ofLocalizedDateTime` với locale tương ứng.

### Ví dụ độc lập Java 17: cùng instant, vùng hiển thị khác nhau

Tệp `InstantZonePatternDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class InstantZonePatternDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2026-10-28T07:30:00Z");

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm VV", Locale.US);

        DateTimeFormatter hcm =
                base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        DateTimeFormatter tokyo =
                base.withZone(ZoneId.of("Asia/Tokyo"));

        System.out.println("instant=" + event);
        System.out.println("hcm=" + hcm.format(event));
        System.out.println("tokyo=" + tokyo.format(event));
        System.out.println("sameLocale=" +
                hcm.getLocale().equals(tokyo.getLocale()));
    }
}
```

```bash
javac -encoding UTF-8 InstantZonePatternDemo.java
java InstantZonePatternDemo
```

Stdout xác định:

```text
instant=2026-10-28T07:30:00Z
hcm=2026-10-28 14:30 Asia/Ho_Chi_Minh
tokyo=2026-10-28 16:30 Asia/Tokyo
sameLocale=true
```

Một instant duy nhất được thể hiện ở hai múi giờ khác nhau. `base` không thay đổi do `DateTimeFormatter` immutable; `withZone` trả một formatter mới.

## 10. Parsing: `ofPattern` không tự nhận dạng mọi cách ghi ngày

Một người dùng nhập `03/04/2026`. Không có thêm thông tin, chuỗi này có thể được hiểu là 3 tháng 4 hoặc 4 tháng 3. Chọn `Locale.US` trong `ofPattern("dd/MM/uuuu", Locale.US)` **không** làm Java tự nhận ra cách nhập Hoa Kỳ; pattern vẫn là ngày/tháng/năm do developer quy định.

Ví dụ:

```java
DateTimeFormatter custom =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US);
LocalDate date = LocalDate.parse("03/04/2026", custom);
```

`date` là ngày **3 tháng 4 năm 2026**, dù locale là `Locale.US`. Trong code này, **pattern thắng về thứ tự trường**.

Để parse input UI đúng, cần:

1. Quy định hoặc công bố locale/pattern của biểu mẫu.
2. Parse bằng formatter tương ứng với chính pattern đó (hoặc `ofLocalizedDate(style).withLocale(locale)` khi client và backend cùng có contract).
3. Xác minh toàn bộ text/kiểu temporal hợp lệ, xử lý ngày không tồn tại.
4. Chuyển thành `LocalDate`, `LocalTime`, `ZonedDateTime` hoặc kiểu nghiệp vụ phù hợp.
5. Khi gửi dữ liệu giữa hệ thống, dùng một format máy rõ như `ISO_LOCAL_DATE` thay vì phụ thuộc locale tự do.

### 10.1. ResolverStyle.STRICT và `uuuu`

Mặc định, `DateTimeFormatter` tạo bởi `ofPattern` thường dùng `ResolverStyle.SMART`. SMART có thể điều chỉnh một số ngày ở cuối tháng theo quy tắc giải quyết trường. Nếu sản phẩm cần từ chối ngày sai, dùng `ResolverStyle.STRICT` cùng pattern có năm proleptic `uuuu`:

Tệp `StrictParsingDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictParsingDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu",
                        Locale.forLanguageTag("vi-VN"))
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDate valid =
                LocalDate.parse("28/10/2026", strict);
        System.out.println("valid=" + valid);

        try {
            LocalDate.parse("31/02/2026", strict);
            System.out.println("unexpected");
        } catch (DateTimeParseException ex) {
            System.out.println("invalid-date=rejected");
        }

        System.out.println("iso=" +
                LocalDate.parse("2026-10-28",
                        DateTimeFormatter.ISO_LOCAL_DATE));
    }
}
```

```bash
javac -encoding UTF-8 StrictParsingDemo.java
java StrictParsingDemo
```

Stdout:

```text
valid=2026-10-28
invalid-date=rejected
iso=2026-10-28
```

Với STRICT, `31/02/2026` là ngày không tồn tại và phải bị từ chối. Pattern dùng `uuuu` giúp giải quyết năm theo proleptic year; nếu dùng `yyyy` (year-of-era) khi parse STRICT mà không có era, có thể không tạo được `LocalDate` như mong đợi. Đừng thay đổi `uuuu` thành `yyyy` mà không hiểu resolver.

### 10.2. `ofLocalizedDate` có parse được không?

Có. Formatter localized của Java có thể dùng để parse text theo cấu trúc mà nó chọn cho locale và style. Nhưng nếu client tạo text trên một JDK/CLDR khác backend, cú pháp thực tế có thể khác. Với API công khai, hãy sử dụng hợp đồng ngày ISO chuẩn hoặc một pattern được ghi rõ, và parse nghiêm ngặt; đừng coi chuỗi UI là giao thức trao đổi dữ liệu bền vững.

## 11. Literal, dấu nháy đơn và text trong pattern

Với `DateTimeFormatter.ofPattern`, chữ cái Latin trong pattern thường có ý nghĩa token, vì vậy muốn thêm văn bản nguyên dạng phải quote bằng dấu nháy đơn. Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "'Ngày' dd/MM/uuuu 'lúc' HH:mm",
                Locale.forLanguageTag("vi-VN"));
```

Nếu format một `LocalDateTime` với ngày `2026-10-28` và giờ `14:05`, kết quả `Ngày 28/10/2026 lúc 14:05`. Hai từ “Ngày” và “lúc” là literal, không bị parser hiểu thành pattern letter. Muốn in một apostrophe thật bên trong pattern, dùng `''` theo cú pháp formatter.

Điều này khác cú pháp `java.text.SimpleDateFormat` ở một số ký tự/tính năng; dù cả hai có nhiều pattern letter giống nhau, không tự sao chép pattern phức tạp giữa hai thư viện mà không kiểm tra tài liệu.

### Trường hợp đặc biệt của `YYYY` và tuần trong năm

`Y` là **week-based-year**, phụ thuộc quy tắc tuần của locale. Gần ranh giới cuối/đầu năm, nó có thể khác `u`. Ví dụ một ngày cuối tháng 12 có thể thuộc tuần đầu tiên của tuần-năm sau theo hệ thống tuần được dùng; không dùng `YYYY` để xuất ngày ISO mà chỉ mong nó giống `uuuu`. `ofPattern("YYYY-MM-dd", locale)` còn pha trộn week-based-year với tháng/ngày theo lịch, có thể khiến parse sai hoặc tạo chuỗi khó hiểu.

Đối với ngày lịch thông thường, `uuuu-MM-dd` hoặc `DateTimeFormatter.ISO_LOCAL_DATE` là lựa chọn rõ hơn.

## 12. Chọn formatter theo nhu cầu thực tế

| Mục tiêu | Cách làm thường phù hợp | Ghi chú |
| --- | --- | --- |
| Gửi ngày qua API | `DateTimeFormatter.ISO_LOCAL_DATE` | Contract máy, `2026-10-28` |
| Hiển thị ngày cho người dùng đa vùng | `ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale)` | Thứ tự và chữ do locale chọn |
| Hiển thị giờ có time-zone theo locale | `ofLocalizedDateTime(style).withLocale(locale)` với `ZonedDateTime` | Kiểm tra style LONG/FULL cần zone |
| Export bắt buộc `dd/MM/uuuu` | `ofPattern("dd/MM/uuuu", locale)` | Fixed layout, không tự đổi theo region |
| Form có pattern do sản phẩm quy định | `ofPattern(patternForLocale, locale)` | Quản lý pattern và validation |
| Chỉ muốn tên tháng theo ngôn ngữ mới | `ofPattern("dd MMMM uuuu", locale)` | Trật tự cố định, chữ tháng bản địa |
| Cần biết mẫu runtime dùng | `DateTimeFormatterBuilder.getLocalizedDateTimePattern(...)` | Chẩn đoán, không nên hard-code lâu dài |
| Format một `Instant` | Formatter có `withZone(zone)` hoặc chuyển sang `ZonedDateTime` | Locale không tự quyết định zone |

### 12.1. Có nên lưu chuỗi localized trong database?

Thông thường **không**. Nếu hệ thống lưu `"10/28/2026"` hoặc `"28/10/2026"` mà không lưu quy tắc parse, sẽ khó tránh nhầm ngày. Hãy lưu kiểu ngày trong DB hoặc chuỗi ISO 8601 theo contract. Format theo locale ở ranh giới UI.

Với thời điểm tuyệt đối, lưu `Instant` hoặc biểu diễn timestamp có offset rõ trong API. Đừng lưu `LocalDateTime` rồi mặc định giờ đó là UTC khi chưa có ngữ nghĩa. Với lịch lặp theo giờ địa phương, phải giữ `ZoneId` và quy tắc lịch nếu nghiệp vụ cần.

### 12.2. Không sửa default locale theo từng request

`Locale.setDefault(...)` tác động cấu hình toàn JVM và có thể ảnh hưởng request khác đang chạy. Trong backend đa người dùng, nên truyền `Locale` và `ZoneId` tường minh vào formatter. `DateTimeFormatter` immutable và thread-safe; bạn có thể cache các formatter với pattern/locale cố định nếu cache được quản lý đúng, không cần mỗi request thay đổi default locale.

## 13. Các lỗi và hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| “`ofPattern("dd/MM/uuuu", Locale.US)` tự đổi sang tháng/ngày/năm.” | Không, pattern đã quyết định thứ tự |
| “`withLocale` luôn chọn pattern mới.” | Chỉ với localized formatter; custom pattern vẫn giữ layout |
| “`FormatStyle.SHORT` = `dd/MM/yy` ở mọi nơi.” | Mẫu SHORT phụ thuộc locale/CLDR |
| “`Locale` tự quyết định `ZoneId`.” | Hai thiết lập độc lập |
| “`ofLocalizedDateTime(FULL)` luôn format được `LocalDateTime`.” | Có thể cần zone; phải dùng temporal/zone phù hợp |
| “`yyyy` và `uuuu` giống nhau trong STRICT parse.” | Year-of-era khác proleptic-year, cần hiểu resolver |
| “`YYYY` là năm lịch.” | Đây là tuần-năm; có thể khác năm lịch |
| “`MM` và `mm` cùng là tháng.” | `MM` là tháng; `mm` là phút |
| “`dd` và `DD` cùng là ngày trong tháng.” | `DD` là ngày trong năm |
| “Pattern có `XXX` sẽ tự biết offset từ `LocalDateTime`.” | `LocalDateTime` không chứa offset/zone |
| “Locale khác nhau thì `ofPattern` luôn đổi chữ số.” | DecimalStyle là một cơ chế riêng |
| “Snapshot localized output có thể đúng mãi ở mọi JDK.” | Dữ liệu locale/provider có thể thay đổi |
| “Ngày đã format đủ tốt để lưu thay ngày gốc.” | Chuỗi hiển thị có thể mơ hồ và lệ thuộc locale |

## 14. Hướng kiểm thử

**Đối với pattern cố định:**

1. Dùng cùng `LocalDate` và hai locale như `vi-VN`, `en-US`; xác minh `"dd/MM/uuuu"` giữ thứ tự và dấu.
2. Dùng `MMMM`/`EEEE`, kiểm tra tên tháng/thứ phù hợp ngôn ngữ với JDK/provider được hỗ trợ.
3. Kiểm tra `uuuu`, `yyyy`, `YYYY` ở những ngày gần ranh giới năm.
4. Parse `31/02/2026` với `ResolverStyle.STRICT` và xác minh bị từ chối.
5. Đối chiếu `dd/MM/uuuu` với `MM/dd/uuuu` khi chuỗi như `03/04/2026` có thể mơ hồ.

**Đối với localized formatter:**

1. Kiểm tra `SHORT`, `MEDIUM`, `LONG` và `FULL` cho những locale được sản phẩm hỗ trợ.
2. Kiểm tra style cần zone với `ZonedDateTime` và đúng `ZoneId`.
3. Nếu test exact output, pin phiên bản JDK/CLDR/provider hoặc chấp nhận các biến thể được chính sách sản phẩm cho phép; lưu ý cả dấu cách Unicode.
4. So sánh `DateTimeFormatterBuilder.getLocalizedDateTimePattern` giữa các locale để giải thích trường hợp thứ tự ngày/tháng khác nhau.
5. Kiểm tra locale hiển thị đã chọn không bị rút từ locale của máy chủ.
6. Kiểm tra người dùng có numbering system khác bằng `withDecimalStyle` hoặc `localizedBy` khi sản phẩm hỗ trợ.

**Đối với dữ liệu và API:**

1. `LocalDate` không bị đổi ngày do “chuyển múi giờ”.
2. Hai cách format cùng `Instant` tại hai zone quy về một thời điểm gốc.
3. Round-trip qua API phải dùng contract có kiểu/format rõ, không lệ thuộc pattern UI.
4. Với form nhập theo locale, validate nghiêm ngặt và xử lý lỗi nhập đã được bản địa hóa.

## 15. Bài tập tự luyện và đáp án

**Bài 1.** Với `LocalDate.of(2026, 10, 28)` và `DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US)`, output là gì? Có tự chuyển thành `10/28/2026` không?

**Đáp án:** `28/10/2026`, không. Pattern được viết sẵn quyết định thứ tự ngày/tháng/năm, locale không tự đảo.

**Bài 2.** Muốn cùng một ứng dụng hiển thị ngày theo quy ước địa phương tại `en-US` và `vi-VN` mà không tự quản lý từng pattern thì dùng gì?

**Đáp án:** `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale)` hoặc style khác theo nhu cầu.

**Bài 3.** Vì sao `withLocale(viVN)` trên formatter được tạo bằng `ofPattern("MM/dd/uuuu", Locale.US)` không chuyển thành `dd/MM/uuuu`?

**Đáp án:** `withLocale` đổi locale dùng để tra text/những phần cần bản địa hóa, chứ không viết lại pattern tùy chỉnh. Muốn đổi layout phải chọn pattern khác, hoặc dùng localized factory.

**Bài 4.** Dùng `"YYYY-MM-dd"` để xuất ngày ISO có rủi ro gì?

**Đáp án:** `Y` là week-based-year, có thể khác năm lịch `u` ở ranh giới năm; dùng `ISO_LOCAL_DATE` hoặc `"uuuu-MM-dd"` cho ngày ISO.

**Bài 5.** `Instant.parse("2026-10-28T07:30:00Z")` format theo `Asia/Ho_Chi_Minh` thành giờ nào trong ví dụ?

**Đáp án:** `14:30` cùng ngày 28/10/2026 theo giờ Việt Nam. Locale quyết định cách viết chuỗi, `ZoneId` quyết định giờ địa phương.

**Bài 6.** `LocalDate.parse("31/02/2026", strictFormatter)` phải làm gì?

**Đáp án:** Ném `DateTimeParseException` vì ngày không hợp lệ; formatter dùng `"dd/MM/uuuu"` và `ResolverStyle.STRICT`.

**Bài 7.** Lấy pattern bằng `getLocalizedDateTimePattern(SHORT, null, IsoChronology.INSTANCE, Locale.US)` rồi tạo `ofPattern(pattern, Locale.US)`. Sau đó `withLocale(viVN)` có đủ để theo pattern SHORT của Việt Nam không?

**Đáp án:** Không. Chuỗi pattern đã được chọn cho Hoa Kỳ và cố định. Dùng `ofLocalizedDate(SHORT).withLocale(viVN)` hoặc lấy riêng pattern của Việt Nam nếu cần tùy chỉnh.

## 16. Ghi nhớ

- **`ofPattern` nhận một layout cố định do lập trình viên cung cấp.** Locale có thể đổi tên tháng, thứ và những thành phần text, nhưng không tự viết lại thứ tự trường.
- **`ofLocalizedDate/Time/DateTime` chọn layout theo locale và `FormatStyle`.** Đây là lựa chọn mặc định hợp lý cho UI đa vùng muốn theo quy ước địa phương.
- `withLocale` trên custom formatter và localized formatter có tác động khác nhau vì **nguồn pattern khác nhau**.
- `DateTimeFormatterBuilder.getLocalizedDateTimePattern` hữu ích để xem pattern mà runtime chọn; không nên biến kết quả của một locale thành pattern cố định cho mọi locale.
- **Locale không phải ZoneId.** Chọn đúng kiểu thời gian và vùng cho dữ liệu nghiệp vụ.
- Với parsing và API, ưu tiên contract rõ (ISO 8601), `ResolverStyle.STRICT` khi cần; tránh `yyyy`/`YYYY` sai mục đích.
- Test theo JDK/CLDR/provider thực tế; không giả định mọi localized output bất biến giữa môi trường.

### Tài liệu tham khảo chính thức Java 17

- [DateTimeFormatter — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [DateTimeFormatterBuilder — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
- [FormatStyle — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/FormatStyle.html)
- [ResolverStyle — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html)
