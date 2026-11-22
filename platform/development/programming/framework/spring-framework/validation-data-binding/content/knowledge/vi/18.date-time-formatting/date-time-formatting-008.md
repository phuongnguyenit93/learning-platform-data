# Ảnh hưởng của phiên bản JDK tới mẫu định dạng theo Locale

> **Phạm vi:** Định dạng và phân tích ngày/giờ theo `Locale` trong Java và Spring Framework, đặc biệt khi nâng cấp JDK. Trọng tâm là `@DateTimeFormat`, `DateTimeFormatter`, dữ liệu locale (CLDR), tính tương thích của dữ liệu nhập và chiến lược kiểm thử. Ví dụ Java chạy từ JDK 17 trở lên.

## 1. Vì sao cùng `Locale` nhưng nâng JDK lại thay đổi ngày/giờ hiển thị?

`Locale` (chẳng hạn `en-US`, `vi-VN`, `fr-FR`) biểu thị ngôn ngữ và quy ước vùng; nó **không tự chứa một mẫu ngày/giờ cố định**. Khi dùng định dạng theo *style* như `SHORT`, `MEDIUM`, `LONG` hoặc `FULL`, thư viện thời gian của JDK tra cứu dữ liệu locale sẵn có tại **runtime đang chạy** để quyết định mẫu và ký hiệu cụ thể.

Ví dụ, hai bản JDK cùng nhận:

- Giá trị `LocalTime.of(13, 45)`.
- `Locale.US`.
- `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)`.

Chúng **có thể** tạo chuỗi khác nhau vì phiên bản dữ liệu locale khác nhau. Sự khác biệt có thể nằm ở thứ tự thành phần, độ dài năm, dấu câu, cách viết tên tháng, biểu tượng AM/PM, khoảng trắng, ký hiệu giờ hoặc hệ lịch. Không phải mọi locale và mọi style đều thay đổi trong mỗi bản JDK.

Đường đi khi Spring MVC nhận/hiển thị trường thời gian:

```text
HTTP query/form field (String)         Java value (LocalDate/LocalTime/...)
           │                                       ▲
           ▼                                       │
   WebDataBinder + ConversionService + Formatter
           │
           └── @DateTimeFormat(style = "...") --> mẫu locale từ JDK đang chạy
                                                   │
                                            Locale của request
                                                   │
                                            Dữ liệu CLDR/JDK
```

- **Parsing:** chuyển chuỗi form/query thành đối tượng ngày/giờ.
- **Printing:** tạo chuỗi trình bày từ đối tượng ngày/giờ, ví dụ để hiển thị lại form.
- **Hậu quả khi thay JDK:** nếu server cũ render chuỗi theo một mẫu và server mới parse theo mẫu khác, round-trip qua những runtime khác nhau có thể thất bại, ngay cả khi `Locale` không đổi.

Đây là hành vi của formatter theo locale; không nên đồng nhất với thay đổi múi giờ, DST hay serialization JSON. Những yếu tố đó có thể ảnh hưởng dữ liệu thời gian nhưng thuộc các ranh giới kỹ thuật khác.

## 2. Cơ chế bên dưới: JDK, CLDR và locale provider

**CLDR** (*Unicode Common Locale Data Repository*) là bộ dữ liệu quốc tế hóa cung cấp quy ước ngôn ngữ/vùng: mẫu ngày giờ, tên tháng/thứ, AM/PM, dấu cách, v.v. Các JDK tích hợp phiên bản dữ liệu CLDR phù hợp với từng lần phát hành. `java.time.format.DateTimeFormatter` và một số API `java.text` sử dụng dữ liệu locale thông qua cơ chế provider của JDK.

| Giai đoạn JDK | Thay đổi quan trọng | Tác động khi xử lý ngày/giờ |
| --- | --- | --- |
| **JDK 8** | Dữ liệu legacy `JRE` được ưu tiên mặc định; CLDR có thể được chọn qua cấu hình | Kết quả format theo style có thể khác JDK mới dù cùng locale |
| **JDK 9–19** | Theo JEP 252, `CLDR` được ưu tiên mặc định từ JDK 9; bản cập nhật JDK có thể cập nhật dữ liệu locale | Dữ liệu hiển thị/phân tích có thể khác JDK 8 hoặc giữa các bản |
| **JDK 20–22** | JDK 20 tích hợp CLDR 42 với một số thay đổi đáng chú ý, bao gồm ký tự trước AM/PM | Một số chuỗi ngày/giờ đã lưu hoặc gửi qua form có thể parse khác dự kiến |
| **JDK 23 trở lên** | Dữ liệu locale legacy `JRE`/`COMPAT` đã bị loại bỏ từ JDK 23 | Không thể dựa vào `COMPAT` để khôi phục kết quả locale kiểu cũ |

Điểm cần hiểu rõ:

1. **`Locale.US` không phải “khóa version” của pattern.** Nó chỉ là đầu vào để runtime tra cứu quy ước định dạng.
2. **`FormatStyle.SHORT` cũng không đảm bảo một chuỗi byte cố định.** API giữ ý nghĩa ngắn/gọn, còn pattern cụ thể thuộc dữ liệu locale.
3. **`java.locale.providers` chọn thứ tự nguồn dữ liệu**, không đưa ứng dụng trở lại đúng version CLDR bất kỳ. Trên JDK 9–22 có thể ưu tiên `JRE`/`COMPAT` để hỗ trợ chuyển đổi; trên JDK 23+ tùy chọn legacy đó không còn tác dụng.
4. **JDK vendor, bản vá, runtime image và locale data đi kèm** có thể làm môi trường chạy khác nhau. Không nên hard-code một output của một JDK rồi coi là chuẩn bắt buộc cho mọi JDK.
5. `Locale` và `ZoneId` là khái niệm khác: locale định hình cách diễn đạt; zone/offset và luật chuyển giờ có thể thay đổi thời điểm hiển thị.

### Thay đổi đặc biệt của JDK 20: khoảng trắng trước AM/PM

Spring Framework có ghi chú riêng về JDK 20+: CLDR 42 thay ký tự dấu cách đứng trước nhãn `AM`/`PM` trong một số kết quả định dạng từ **space thông thường** `U+0020` sang **narrow no-break space** `U+202F` (khoảng trắng hẹp không ngắt dòng).

Hai chuỗi minh họa có thể trông gần giống:

```text
"1:45 PM"        -> giữa 45 và PM là U+0020
"1:45\u202FPM"  -> giữa 45 và PM là U+202F (biểu diễn escape)
```

Trong tài liệu trên, `\u202F` là cách viết *escape* để nhìn rõ mã ký tự. Trong chuỗi thực tế, đó là **một ký tự Unicode**, không phải sáu ký tự dấu gạch chéo/nguyên âm/chữ số. Người dùng có thể không nhìn thấy sự khác biệt, nhưng hai chuỗi không bằng nhau khi so sánh ký tự. Nếu parser đòi đúng literal của pattern, việc đổi một ký tự khoảng trắng có thể dẫn đến lỗi binding.

**Không kết luận rằng mọi output của JDK 20+ đều chứa `U+202F`.** Kết quả phụ thuộc locale, style, loại dữ liệu, phiên bản runtime và provider. Cần kiểm tra giá trị thực tế bằng *Unicode code point* thay vì nhìn bằng mắt.

## 3. Java 17+ chạy được: quan sát pattern theo runtime

Ví dụ này dùng cùng dữ liệu và locale, in pattern được JDK tra cứu, kết quả hiển thị, từng Unicode code point, rồi đối chiếu với một định dạng ISO/mẫu tự chọn. Chạy cùng chương trình bằng các JDK khác nhau để so sánh.

Lưu đoạn sau thành **`LocaleJdkProbe.java`**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.stream.Collectors;

public class LocaleJdkProbe {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        LocalDate date = LocalDate.of(2026, 11, 5);
        LocalTime time = LocalTime.of(13, 45);

        DateTimeFormatter dateFormatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                                 .withLocale(locale);
        DateTimeFormatter timeFormatter =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                                 .withLocale(locale);

        String datePattern = DateTimeFormatterBuilder
                .getLocalizedDateTimePattern(
                        FormatStyle.SHORT, null,
                        IsoChronology.INSTANCE, locale);

        String timePattern = DateTimeFormatterBuilder
                .getLocalizedDateTimePattern(
                        null, FormatStyle.SHORT,
                        IsoChronology.INSTANCE, locale);

        System.out.println("JDK feature=" + Runtime.version().feature());
        System.out.println("Locale=" + locale.toLanguageTag());

        show("date.pattern", datePattern);
        show("date.value", dateFormatter.format(date));
        show("time.pattern", timePattern);
        show("time.value", timeFormatter.format(time));

        DateTimeFormatter explicit =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT);

        System.out.println("ISO date="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        System.out.println("Explicit="
                + explicit.format(LocalDateTime.of(date, time)));
    }

    private static void show(String name, String text) {
        String codePoints = text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));

        System.out.println(name + "=[" + text + "]");
        System.out.println(name + ".codePoints=" + codePoints);
    }
}
```

Biên dịch và chạy bằng JDK đang cấu hình:

```bash
javac LocaleJdkProbe.java
java LocaleJdkProbe
```

Hai dòng **ổn định cho dữ liệu mẫu** là:

```text
ISO date=2026-11-05
Explicit=2026-11-05 13:45
```

Những dòng chứa `JDK feature`, `date.pattern`, `time.pattern`, `date.value`, `time.value` và `codePoints` được in ra theo runtime thực tế, **không có một stdout duy nhất đúng cho mọi JDK**. Ví dụ, nếu thấy `U+202F` trong `time.value.codePoints` thì chuỗi hiển thị có chứa narrow no-break space. Nếu chỉ thấy `U+0020` tại vị trí ấy, đó là space thông thường. `getLocalizedDateTimePattern` dùng để *chẩn đoán mẫu được chọn*; không lấy mẫu của JDK hiện tại rồi giả định mọi JDK khác cũng sẽ dùng nó.

Chạy lại hai lệnh trên với JDK 17, JDK 21 và một JDK 23+ trên môi trường kiểm thử. Ghi rõ `java -version`, runtime vendor, locale và kết quả code point. So sánh hành vi ứng dụng, không chỉ so sánh chuỗi hiển thị.

## 4. Liên hệ trực tiếp với Spring `@DateTimeFormat`

Spring Framework cho phép khai báo cách parse/print dữ liệu ngày giờ của trường/đối số theo ba cách chính:

| Khai báo | Ý nghĩa | Độ phụ thuộc vào dữ liệu locale |
| --- | --- | --- |
| `@DateTimeFormat(style = "S-")` | Ngày kiểu SHORT; ký tự `-` bỏ phần thời gian | **Cao:** pattern do runtime và locale cung cấp |
| `@DateTimeFormat(style = "-S")` | Giờ kiểu SHORT; bỏ phần ngày | **Cao:** có thể chịu thay đổi AM/PM và Unicode space |
| `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` | Ngày ở dạng ISO, ví dụ `2026-11-05` | **Thấp:** cấu trúc trao đổi rõ ràng, không tùy style theo locale |
| `@DateTimeFormat(pattern = "dd/MM/uuuu")` | Mẫu cụ thể do ứng dụng quy định cho `java.time` | **Ít phụ thuộc hơn** về thứ tự/ký tự phân cách; trường chữ như tên tháng/AM-PM vẫn có thể phụ thuộc locale |

Cú pháp `style` có hai vị trí: ngày rồi tới thời gian. Các mã `S`/`M`/`L`/`F` lần lượt là SHORT/MEDIUM/LONG/FULL; dấu `-` bỏ phần tương ứng. Chỉ chọn **một** trong `style`, `iso`, `pattern` cho mỗi khai báo. `pattern` ưu tiên hơn `iso` và `style`; `iso` ưu tiên hơn `style` nếu khai báo đồng thời, nhưng việc kết hợp nhiều cơ chế một lúc gây khó hiểu và nên tránh.

### 4.1. Mẫu phụ thuộc locale: phù hợp khi hiển thị cho con người

Đoạn sau là ví dụ trường trong DTO Spring MVC (không phải chương trình Java độc lập):

```java
import java.time.LocalDate;
import java.time.LocalTime;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {
    @DateTimeFormat(style = "S-")
    private LocalDate bookingDate;

    @DateTimeFormat(style = "-S")
    private LocalTime bookingTime;

    public LocalDate getBookingDate() {
        return bookingDate;
    }

    public void setBookingDate(LocalDate bookingDate) {
        this.bookingDate = bookingDate;
    }

    public LocalTime getBookingTime() {
        return bookingTime;
    }

    public void setBookingTime(LocalTime bookingTime) {
        this.bookingTime = bookingTime;
    }
}
```

Khi controller nhận `@ModelAttribute BookingForm`, Spring dùng bộ formatter và locale của request để bind chuỗi query/form vào các trường. Ví dụ ở một locale/JDK, chuỗi giờ 12 tiếng có AM/PM; ở locale/JDK khác, có thể là biểu diễn 24 tiếng hoặc dấu cách Unicode khác. Vì thế, **không lưu chuỗi từ field style-based làm khóa dữ liệu dài hạn hay contract cố định giữa các hệ thống**.

### 4.2. Mẫu ổn định cho dữ liệu trao đổi, đường dẫn hoặc API

Nếu ứng dụng kiểm soát cấu trúc dữ liệu đầu vào, ưu tiên ISO cho ngày và mẫu số hóa cụ thể cho giờ:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import org.springframework.format.annotation.DateTimeFormat;

public class SearchFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    @DateTimeFormat(pattern = "HH:mm")
    private LocalTime fromTime;

    public LocalDate getFromDate() {
        return fromDate;
    }

    public void setFromDate(LocalDate fromDate) {
        this.fromDate = fromDate;
    }

    public LocalTime getFromTime() {
        return fromTime;
    }

    public void setFromTime(LocalTime fromTime) {
        this.fromTime = fromTime;
    }
}
```

Ví dụ input query/form tương ứng:

```text
fromDate=2026-11-05
fromTime=13:45
```

`LocalDate` và `LocalTime` trong ví dụ **không mang timezone**. Nếu nghiệp vụ quản lý một thời điểm tuyệt đối, phải chọn kiểu phù hợp như `Instant` hoặc `OffsetDateTime`, đồng thời quy định zone/offset trong contract. Chỉ đổi pattern hoặc locale không giải quyết sai lệch múi giờ.

### 4.3. `fallbackPatterns` giúp chuyển tiếp dữ liệu cũ

Spring `@DateTimeFormat` hỗ trợ `fallbackPatterns` (Spring Framework 5.3.5+). Khi cách parse bằng `pattern`, `iso` hoặc `style` chính thất bại, framework có thể thử các pattern dự phòng theo thứ tự khai báo.

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class LegacySearchForm {
    @DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"M/d/uuuu", "dd.MM.uuuu"}
    )
    private LocalDate date;

    public LocalDate getDate() {
        return date;
    }

    public void setDate(LocalDate date) {
        this.date = date;
    }
}
```

Ứng dụng ưu tiên nhận/in ngày ở dạng ISO như `2026-11-05`, nhưng có thể chấp nhận thêm các chuỗi phù hợp `M/d/uuuu` hoặc `dd.MM.uuuu` trong quá trình chuyển tiếp.

**Phải phân biệt:** `fallbackPatterns` **chỉ hỗ trợ parsing**, không làm thay đổi chuỗi được in ra. Mẫu chính (`iso` trong ví dụ) vẫn quyết định printing. Các fallback cũng không tự xử lý mọi biểu diễn lịch sử hoặc mọi ký tự Unicode; nếu người dùng thực sự có dữ liệu đầu vào không tương thích, cần test từng mẫu, từng locale và từng JDK. Tránh các pattern dự phòng dễ gây nhập nhằng như `M/d/uuuu` và `d/M/uuuu` đồng thời nếu không có quy tắc xác định ngày/tháng.

### 4.4. Giới hạn: formatter của Spring khác Jackson JSON

`@DateTimeFormat` áp dụng cho Spring field binding/printing (chẳng hạn query/form qua `@ModelAttribute`); **không mặc nhiên định dạng body JSON** được đọc/ghi bằng Jackson qua `@RequestBody`/`@ResponseBody`. Với JSON, dùng hợp đồng dữ liệu và cấu hình Jackson phù hợp; nếu dùng `@JsonFormat`, phải kiểm thử riêng đường JSON.

Nâng JDK có thể ảnh hưởng các đường đọc/ghi date-time khác nhau, nhưng không nên sửa một lỗi form binding chỉ bằng annotation Jackson, hoặc ngược lại.

## 5. Quy trình tái hiện lỗi khi nâng JDK

Giả sử sau nâng từ JDK 17 lên JDK 21, một form nhập giờ theo locale `en-US` bị báo lỗi dù chữ hiển thị nhìn giống nhau. Làm theo trình tự:

1. **Xác định đường dữ liệu:** query/form với `@DateTimeFormat` hay JSON với Jackson? Với lỗi field binding, kiểm tra `BindingResult`/field error và type mismatch.
2. **Chốt dữ liệu gốc:** lưu giá trị input thực nhận tại HTTP boundary dưới dạng UTF-8 và biểu diễn code point. Chẳng hạn phân biệt `U+0020` với `U+202F`; đừng tự động `trim()` hoặc thay thế khoảng trắng trước khi biết yêu cầu nghiệp vụ.
3. **Ghi thông tin runtime:** `java -version`, JDK vendor/build, `Locale` của request, formatter style/pattern, provider cấu hình, dữ liệu mẫu. Nếu có xử lý zone, ghi cả `ZoneId` và tzdb liên quan.
4. **Reproduce tại môi trường cũ và mới:** giữ nguyên input, locale, loại Java, endpoint và cấu hình. Thử cả *format → parse cùng runtime* lẫn *format ở runtime cũ → parse ở runtime mới*.
5. **So sánh mẫu và code point:** chạy `LocaleJdkProbe`, kiểm tra pattern resolved và Unicode thực tế. Phân biệt thay đổi dấu câu/khoảng trắng/tên tháng với lỗi timezone hoặc validation.
6. **Chọn phương án sửa lâu dài:** dữ liệu máy đọc dùng ISO/mẫu rõ ràng; biểu mẫu cho người dùng có thể tiếp tục localized formatting nhưng phải chấp nhận/migrate kiểu nhập cũ khi cần.
7. **Kiểm thử hồi quy** trước khi đổi JDK ở production, trong đó có ít nhất locale người dùng thực tế và các giá trị biên.

Ví dụ ma trận kiểm thử nên có:

| Trục kiểm thử | Giá trị gợi ý | Mục đích |
| --- | --- | --- |
| JDK | 17, 21, 23+ hoặc đúng các bản deploy | Tìm thay đổi CLDR/provider giữa runtime |
| Locale | `en-US`, `vi-VN` và locale thực tế của sản phẩm | Không giả định mọi locale dùng cùng pattern |
| Định dạng | `SHORT`, `MEDIUM`, ISO và mẫu tùy chỉnh | Tách phần do runtime quyết định khỏi contract cố định |
| Dữ liệu | Ngày 1 chữ số, năm chuyển giao, 12/24 giờ, AM/PM, `U+0020`/`U+202F` | Bắt lỗi phân tích và ký tự ẩn |
| Đường đi | Form/query, in lại form, JSON (nếu có) | Kiểm thử đúng cơ chế của Spring |

Với Spring MVC, có thể dùng `MockMvc` và chọn locale request rõ ràng (ví dụ `.locale(Locale.US)`) để kiểm thử binding trên từng JDK. Test cần kiểm tra **giá trị Java đã parse và kết quả error**; khi output là localized string, ghi nhận và xem xét độ ổn định của ký tự Unicode. Đừng khóa toàn bộ snapshot text vào một JDK nếu yêu cầu của sản phẩm không đòi chuỗi chính xác từng byte.

## 6. Cấu hình provider: giải pháp hỗ trợ chuyển đổi, không phải chiến lược dài hạn

Trên các runtime **JDK 9–22**, cấu hình khởi động sau có thể khiến provider legacy được ưu tiên:

```bash
java -Djava.locale.providers=COMPAT,CLDR -jar app.jar
```

`JRE` là tên legacy tương ứng, `COMPAT` là alias đã được dùng trong giai đoạn chuyển đổi. **JDK 21 đã cảnh báo về việc loại bỏ legacy provider; từ JDK 23, `JRE`/`COMPAT` không còn dữ liệu legacy để phục hồi**, nên thêm cờ này không bảo đảm tái tạo output cũ. Cũng cần chạy cờ từ lúc JVM khởi động, không trông đợi thay đổi tùy ý giữa các request.

Việc ghim JDK cũ hoặc chọn provider legacy chỉ giúp giảm rủi ro trong quá trình chuyển đổi được kiểm soát. Đối với một contract bền vững:

- Dùng kiểu thời gian đúng ngữ nghĩa (`LocalDate`, `LocalTime`, `Instant`, `OffsetDateTime`, ...).
- Quy định dạng trao đổi ở ranh giới hệ thống, ưu tiên ISO 8601 hoặc pattern có chủ đích, locale/zone rõ ràng khi cần.
- Tách *giá trị thời gian* khỏi *chuỗi hiển thị phụ thuộc người dùng*.
- Nếu cần chấp nhận dữ liệu nhập cũ, định nghĩa `fallbackPatterns` hoặc parser chuyển đổi minh bạch, kèm test và thời hạn ngừng hỗ trợ.
- Dùng UTF-8 từ HTTP tới log/storage khi lưu chuỗi trình bày đa ngôn ngữ; chỉ riêng mã hóa đúng không làm hai ký tự `U+0020` và `U+202F` tương đương.

## 7. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Locale là `vi-VN` nên pattern sẽ cố định mãi” | Locale chỉ chọn quy ước; dữ liệu CLDR của JDK có thể thay đổi |
| “Cùng `DateTimeFormatter.ofLocalizedTime(SHORT)` thì stdout luôn giống” | Style có ý nghĩa tương đối; literal pattern và ký tự Unicode có thể khác |
| “JDK 20 chỉ đổi giao diện” | Nếu dữ liệu nhập cũ được parser mới đọc, lỗi binding có thể xảy ra |
| “Dùng `COMPAT` là sửa vĩnh viễn” | Legacy provider đã bị loại bỏ từ JDK 23 |
| “Dùng pattern cố định nhưng có `MMM`/`a` là độc lập locale” | Tên tháng và AM/PM vẫn có thể được xác định từ dữ liệu locale |
| “`fallbackPatterns` đổi cả output về dạng cũ” | Nó chỉ được thử khi parsing; printing vẫn dùng cấu hình chính |
| “`@JsonFormat` sửa được `@ModelAttribute` parse lỗi” | Jackson JSON và Spring field formatter là hai đường xử lý khác nhau |
| “`Locale` đồng nghĩa timezone” | Locale, zone/offset, chronology và dữ liệu timezone là các yếu tố riêng |
| “Nhìn giống nhau nghĩa là hai chuỗi giống nhau” | Các khoảng trắng `U+0020` và `U+202F` trông tương tự nhưng khác code point |

Lưu ý thêm khi dùng pattern thời gian: `MM` là **tháng**, `mm` là **phút**; `HH` là giờ 0–23, `hh` là giờ 1–12 và thường cần `a`; `YYYY` biểu thị *week-based year* chứ không phải năm lịch thông thường. Trong `java.time`, `uuuu` là proleptic year, thường thích hợp cho pattern ISO-like. Một lỗi dùng ký tự pattern sai có thể bị hiểu nhầm là lỗi do nâng JDK hoặc thay CLDR.

## 8. Chọn cách làm cho từng nhu cầu

- **Form dành cho người dùng địa phương:** `@DateTimeFormat(style = ...)` có thể phù hợp nếu chấp nhận output theo locale và đã test phiên bản JDK; cần thiết thì bổ sung parser tương thích dữ liệu cũ.
- **Input query/API cần ổn định:** `@DateTimeFormat(iso = ISO.DATE)` cho `LocalDate`, hoặc `pattern = "HH:mm"` cho `LocalTime` nếu contract quy định vậy.
- **Dữ liệu lưu lâu dài và trao đổi service-to-service:** lưu kiểu thời gian/ISO hoặc timestamp có offset/zone được định nghĩa, tránh lưu chuỗi display style.
- **Đang nâng JDK và gặp parsing khác trước:** xác minh version CLDR, code point, locale request; không kết luận dựa trên hình dạng dấu cách.
- **Phải giữ một biểu diễn cũ để tương thích:** định nghĩa pattern và parser riêng có test thay vì trông chờ legacy provider còn tồn tại.

**Kết luận:** Cùng một `Locale` và cùng một style vẫn có thể sinh mẫu ngày/giờ khác khi JDK hoặc dữ liệu CLDR thay đổi. Với Spring `@DateTimeFormat`, rủi ro ảnh hưởng **cả parsing lẫn printing**. Tách định dạng hiển thị cho con người khỏi định dạng trao đổi ổn định, kiểm thử Unicode và JDK thực tế, sử dụng ISO/pattern rõ ràng cùng fallback có kiểm soát khi cần.

### Tài liệu tham khảo chính thức

- [OpenJDK JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252)
- [Oracle Java Migration Guide — Changes to Internationalization and Locale Data](https://docs.oracle.com/en/java/javase/23/migrate/preparing-migration.html)
- [Spring Framework Wiki — Date and Time Formatting with JDK 20 and Higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher)
- [Spring Framework 6.1 Javadoc — DateTimeFormat](https://www.springframework.org/spring/docs/6.1.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Java SE Javadoc — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE Javadoc — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html)
