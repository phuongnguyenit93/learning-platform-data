# Hiển thị cùng dữ liệu số, tiền tệ, ngày giờ ở nhiều locale — Thực hành tổng hợp Java 17+

Một bản ghi kinh doanh có thể được xem đồng thời bởi người dùng Việt Nam, Hoa Kỳ, Đức, Pháp và Nhật Bản. Dữ liệu gốc **không đổi**, nhưng cách viết dấu thập phân, dấu nhóm, ký hiệu tiền, thứ tự ngày–tháng–năm, tên tháng và giờ địa phương có thể khác. Nếu ứng dụng lưu luôn chuỗi “1.234,50 €” hoặc “28/10/2026” thay vì giá trị có kiểu, việc hiển thị trên các vùng khác sẽ dễ sai, thậm chí có thể khiến phần mềm tính toán sai số tiền.

Bài thực hành này sử dụng **Java 17+** để hiển thị **cùng một bộ dữ liệu** qua nhiều **Locale**, so sánh **NumberFormat**, **Currency**, **DateTimeFormatter**, **ZoneId** và **ResourceBundle** ở mức tích hợp. Bài phân biệt rõ những giá trị bất biến có thể kiểm tra bằng stdout chính xác với những mẫu chữ/số phụ thuộc dữ liệu địa phương hóa **CLDR/JDK**. Trọng tâm không chỉ là tạo vài chuỗi đẹp mắt, mà là xây quy trình **dữ liệu gốc → ngữ cảnh người xem → formatter → nội dung hiển thị → kiểm thử**.

## 1. Mục tiêu sau bài học

Sau khi hoàn thành, bạn có thể:

1. Lưu một số thập phân bằng **BigDecimal** và một đơn vị tiền bằng **Currency**, không để chúng phụ thuộc locale.
2. Tạo một dãy người xem bằng **Locale.forLanguageTag** mà không sửa **Locale.setDefault**.
3. Hiển thị cùng **BigDecimal** dưới nhiều quy tắc nhóm và thập phân bằng **NumberFormat**.
4. Hiển thị cùng số tiền EUR dưới nhiều locale bằng **NumberFormat.getCurrencyInstance** và **setCurrency**.
5. Dùng **LocalDate** cho ngày thuần, **Instant** cho thời điểm tuyệt đối và **ZoneId** cho giờ địa phương.
6. Dùng **DateTimeFormatter.ofLocalizedDate/DateTime** với **FormatStyle** phù hợp.
7. Hiểu vì sao cùng một **Instant** có thể rơi vào **hai ngày lịch khác nhau** khi đổi múi giờ.
8. Nhận biết NBSP/NNBSP, dấu RTL/bidi và chữ số bản địa thay vì so chuỗi bằng mắt.
9. Kiểm thử kết quả **theo ngữ nghĩa** mà không hardcode mọi dấu/cách viết có thể đổi theo dữ liệu JDK.
10. Tách **giá trị nghiệp vụ** khỏi **chuỗi trình bày** và tránh các lỗi parse, rounding, currency conversion.

## 2. Dữ liệu đầu vào dùng chung

Giả sử một đơn hàng lưu:

| Trường | Giá trị gốc | Kiểu Java | Ý nghĩa |
| --- | --- | --- | --- |
| orderId | ORD-2026-1028 | String | Định danh kỹ thuật, không dịch |
| units | 1234567.89 | BigDecimal | Một giá trị số để minh họa nhóm/thập phân |
| subtotal | 1234.50 | BigDecimal | Số tiền gốc theo EUR |
| currency | EUR | Currency | Đơn vị tiền thực của đơn |
| taxRatio | 0.125 | BigDecimal | Tỷ lệ 12,5%, không phải số 12,5 |
| scheduledDate | 2026-10-28 | LocalDate | Ngày lịch thuần, không có timezone |
| eventTime | 2026-10-28T02:30:00Z | Instant | Một thời điểm tuyệt đối trên trục UTC |

**Tất cả người xem đọc đúng cùng giá trị này.** Locale chỉ quyết định cách biểu diễn, không tự đổi lượng hàng, số tiền hoặc tỷ lệ thuế. Đơn vị EUR phải giữ nguyên trừ khi nghiệp vụ chủ động thực hiện quy đổi ngoại tệ với tỷ giá được cung cấp.

Dùng **new BigDecimal("1234.50")** thay vì **new BigDecimal(1234.50)** để tránh đưa xấp xỉ nhị phân của một giá trị double vào số tiền. Dùng **Currency.getInstance("EUR")** để mang mã tiền tệ ISO 4217; ký hiệu EUR hiển thị có thể khác theo locale.

**Một LocalDate và một Instant phục vụ hai nhu cầu khác nhau:** ngày hẹn 2026-10-28 là một ngày thuần; eventTime là một thời điểm cố định cần ZoneId để biết ngày/giờ của người xem.

## 3. Quy trình hiển thị đúng

~~~text
                   DỮ LIỆU GỐC
        BigDecimal / Currency / LocalDate / Instant
                          |
                          v
                CHỌN NGỮ CẢNH
         UI language, format Locale, ZoneId
                          |
                +---------+---------+
                |                   |
                v                   v
           NUMBER/MONEY        DATE/TIME
          NumberFormat       DateTimeFormatter
                |                   |
                +---------+---------+
                          |
                          v
                CÂU HIỂN THỊ
          ResourceBundle / MessageFormat
                          |
                          v
                 UI / Email / PDF
~~~

**Không đảo luồng** bằng cách format ngay trong domain, lưu kết quả rồi buộc các màn hình khác parse ngược. Giá trị có kiểu nên được lưu/truyền nguyên vẹn trong JSON, database hoặc sự kiện; chỉ tới tầng view/presenter mới chuyển sang chữ địa phương.

Một ứng dụng có thể có **uiLocale** (chọn câu đã dịch), **formatLocale** (chọn cách viết giá trị), **ZoneId** (chọn giờ địa phương) và **Currency** (dữ liệu đơn hàng) khác nhau. Đừng tạo một biến **locale** rồi cố suy ra tất cả các thuộc tính còn lại.

## 4. Chọn các locale để so sánh

Trong bài này dùng sáu tag:

| Tag | Mục đích quan sát |
| --- | --- |
| **vi-VN** | Tiếng Việt và quy ước vùng Việt Nam |
| **en-US** | Tiếng Anh Hoa Kỳ, ví dụ nhóm/thập phân quen thuộc |
| **de-DE** | Tiếng Đức ở Đức, quy tắc chữ/số khác |
| **fr-FR** | Tiếng Pháp tại Pháp, chú ý khoảng trắng khi nhóm hoặc viết tiền |
| **ja-JP** | Tiếng Nhật, đơn vị và thứ tự thành phần theo locale |
| **ar-EG** | Tiếng Ả Rập tại Ai Cập, chú ý ký tự RTL/chữ số/dấu cách |

Các tag là **đầu vào được chọn cho thực hành**, không phải kết luận rằng tất cả locale có cùng độ phủ dữ liệu ở mọi phiên bản JDK. Runtime có thể dùng CLDR/provider và fallback; ứng dụng thực tế nên chọn những locale đã được đội ngũ sản phẩm hỗ trợ và kiểm thử.

Trong Java:

~~~java
Locale[] locales = {
    Locale.forLanguageTag("vi-VN"),
    Locale.US,
    Locale.GERMANY,
    Locale.FRANCE,
    Locale.JAPAN,
    Locale.forLanguageTag("ar-EG")
};
~~~

Đoạn minh họa cần import **java.util.Locale** và đặt trong phương thức. **Locale.US** tương đương ý định tag en-US, còn **Locale.GERMANY** dùng de-DE. Không dùng **Locale.setDefault(...)** để “đổi ngôn ngữ” mỗi lượt lặp: trạng thái mặc định thuộc JVM và có thể làm request khác bị ảnh hưởng.

## 5. Bài chạy chính: một bản ghi, nhiều cách hiển thị

**File MultiLocaleDisplayLab.java**

Chương trình dưới đây chỉ dùng Java 17 Standard Library. Nó in dữ liệu gốc một lần, sau đó format cùng dữ liệu theo sáu locale, giữ EUR cố định. Từng dòng đã địa phương hóa có thể khác chút ít giữa các phiên bản JDK/CLDR; vì thế có thêm phần kiểm chứng giá trị bất biến ở cuối.

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class MultiLocaleDisplayLab {
    record OrderData(
            String id,
            BigDecimal quantity,
            BigDecimal subtotal,
            BigDecimal taxRatio,
            Currency currency,
            LocalDate scheduledDate,
            Instant createdAt) {}

    private static String decimal(
            BigDecimal value, Locale locale) {
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        format.setGroupingUsed(true);
        return format.format(value);
    }

    private static String money(
            BigDecimal amount,
            Currency currency,
            Locale locale) {
        NumberFormat format =
                NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(currency);

        int fraction = currency.getDefaultFractionDigits();
        if (fraction >= 0) {
            format.setMinimumFractionDigits(fraction);
            format.setMaximumFractionDigits(fraction);
        }

        return format.format(amount);
    }

    private static String percent(
            BigDecimal ratio, Locale locale) {
        NumberFormat format =
                NumberFormat.getPercentInstance(locale);
        format.setMinimumFractionDigits(1);
        format.setMaximumFractionDigits(1);
        return format.format(ratio);
    }

    private static String date(
            LocalDate value, Locale locale) {
        return DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale)
                .format(value);
    }

    private static String dateTime(
            Instant value,
            Locale locale,
            ZoneId zone) {
        return DateTimeFormatter
                .ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(locale)
                .format(value.atZone(zone));
    }

    private static void display(
            OrderData order,
            Locale locale,
            ZoneId zone) {
        System.out.println("locale="
                + locale.toLanguageTag());
        System.out.println("  quantity="
                + decimal(order.quantity(), locale));
        System.out.println("  subtotal="
                + money(order.subtotal(),
                        order.currency(), locale));
        System.out.println("  tax="
                + percent(order.taxRatio(), locale));
        System.out.println("  scheduled="
                + date(order.scheduledDate(), locale));
        System.out.println("  event@"
                + zone.getId() + "="
                + dateTime(order.createdAt(), locale, zone));
    }

    public static void main(String[] args) {
        OrderData order = new OrderData(
                "ORD-2026-1028",
                new BigDecimal("1234567.89"),
                new BigDecimal("1234.50"),
                new BigDecimal("0.125"),
                Currency.getInstance("EUR"),
                LocalDate.of(2026, 10, 28),
                Instant.parse("2026-10-28T02:30:00Z"));

        Locale[] locales = {
                Locale.forLanguageTag("vi-VN"),
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.JAPAN,
                Locale.forLanguageTag("ar-EG")
        };

        ZoneId fixedZone =
                ZoneId.of("Asia/Ho_Chi_Minh");

        for (Locale locale : locales) {
            display(order, locale, fixedZone);
        }

        System.out.println("CHECK");
        System.out.println("id=" + order.id());
        System.out.println("quantity="
                + order.quantity().toPlainString());
        System.out.println("subtotal="
                + order.subtotal().toPlainString());
        System.out.println("currency="
                + order.currency().getCurrencyCode());
        System.out.println("ratio="
                + order.taxRatio().toPlainString());
        System.out.println("date="
                + order.scheduledDate());
        System.out.println("instant="
                + order.createdAt());
        System.out.println("localeCount=" + locales.length);
    }
}
~~~

Lưu bằng UTF-8 và chạy:

~~~bash
javac -encoding UTF-8 MultiLocaleDisplayLab.java
java MultiLocaleDisplayLab
~~~

### 5.1. Cách đọc output

Mỗi locale tạo một khối có nhãn:

~~~text
locale=vi-VN
  quantity=...
  subtotal=...
  tax=...
  scheduled=...
  event@Asia/Ho_Chi_Minh=...

locale=en-US
  quantity=...
  subtotal=...
  tax=...
  scheduled=...
  event@Asia/Ho_Chi_Minh=...
~~~

Đây là **sơ đồ cấu trúc**, không phải stdout đầy đủ: dấu ba chấm chỉ đại diện cho kết quả do formatter của JDK thực sự sinh ra. Các khối de-DE, fr-FR, ja-JP và ar-EG có cùng nhãn kỹ thuật, nhưng phần giá trị thay đổi theo locale/runtime.

Với **vi-VN/en-US/de-DE/fr-FR**, thường quan sát được dấu phân nhóm, dấu thập phân, cách đặt tiền EUR và các khoảng trắng khác nhau; **ja-JP** có thể cho cách viết ngày theo chữ Nhật; **ar-EG** có thể có chữ số địa phương hoặc ký tự bidi. **Không chép các ví dụ trông giống nhau thành một mẫu cứng**: hãy đọc kết quả của JDK mục tiêu.

### 5.2. Phần stdout có thể khẳng định chính xác

Mười dòng cuối của chương trình **không dựa vào NumberFormat/DateTimeFormatter địa phương hóa**. Chúng được tạo từ dữ liệu có kiểu và cách in ổn định:

~~~text
CHECK
id=ORD-2026-1028
quantity=1234567.89
subtotal=1234.50
currency=EUR
ratio=0.125
date=2026-10-28
instant=2026-10-28T02:30:00Z
localeCount=6
~~~

Vì thế, dù các khối localized output trông rất khác nhau, **quantity, subtotal, currency, ratio, ngày lịch và instant không đổi**. Đây là điểm cốt lõi: **presentation changes, business data does not**.

### 5.3. Vì sao chương trình không gọi toString() trên các formatter?

**NumberFormat.format** và **DateTimeFormatter.format** tạo chuỗi theo cấu hình. Việc in **NumberFormat.toString()** chỉ hiển thị thông tin về đối tượng, không phải format số. Trong code, mỗi formatter được tạo với locale cụ thể và format đúng giá trị được truyền.

**OrderData** là một Java 17 record. Record giúp nhóm dữ liệu bất biến về tham chiếu; BigDecimal, Currency, LocalDate và Instant đều có ngữ nghĩa giá trị phù hợp để trình bày. Không cần thay đổi OrderData khi đổi locale hiển thị.

## 6. Khác biệt giữa số và tiền tệ

Cùng một BigDecimal có thể được dùng trong hai ngữ cảnh:

- **Số lượng/giá trị số:** chỉ cần group separator, decimal separator và chữ số.
- **Số tiền:** ngoài cách viết số còn có **Currency**, ký hiệu/mã tiền, vị trí ký hiệu, khoảng cách và mặc định fraction digits.

**NumberFormat.getNumberInstance(locale)** không tự thêm đơn vị tiền, còn **NumberFormat.getCurrencyInstance(locale)** tạo một currency formatter theo quy tắc locale.

~~~java
NumberFormat number =
        NumberFormat.getNumberInstance(locale);

NumberFormat money =
        NumberFormat.getCurrencyInstance(locale);
money.setCurrency(Currency.getInstance("EUR"));
~~~

Đoạn này là minh họa bên trong phương thức, cần imports **NumberFormat**, **Currency**, **Locale**.

**setCurrency không đổi tiền theo tỷ giá.** Nếu subtotal=1234.50 là **1234,50 EUR**, việc thay Currency thành USD mà không tính toán nghiệp vụ sẽ **đổi nhãn đơn vị**, không hề đổi lượng. Vì vậy mô hình tiền tệ phải đi cùng Currency từ nguồn dữ liệu và formatter chỉ chịu trách nhiệm trình bày.

### 6.1. Số chữ số thập phân không phải toàn bộ chính sách tiền

Currency có **getDefaultFractionDigits()**. EUR thường có 2, JPY thường có 0 theo định nghĩa currency của runtime. Dùng mặc định giúp định dạng thông thường, nhưng nghiệp vụ thanh toán có thể yêu cầu:

1. Số chữ số trong hệ thống lưu sổ.
2. Số chữ số khi tính thuế.
3. Quy tắc làm tròn cho hóa đơn.
4. Làm tròn tiền mặt khác với làm tròn điện tử.
5. Cách hiển thị con số đã được tính chính xác.

**Không dùng NumberFormat như nguồn chân lý để quyết định phép tính tiền.** Mức rounding phải được xác định trong domain, còn formatter thể hiện kết quả theo hợp đồng UI.

### 6.2. Không dùng double cho phép tính tài chính

~~~java
BigDecimal amount = new BigDecimal("1234.50");
~~~

Cách này giữ giá trị thập phân mong muốn. Nếu dùng **new BigDecimal(0.1)**, ta nhận giá trị nhị phân xấp xỉ của double dưới dạng BigDecimal, không phải đúng chuỗi thập phân **0.1**. Với những phép tính tiền, dùng BigDecimal từ chuỗi hoặc **BigDecimal.valueOf(double)** khi hợp đồng đầu vào vốn là double và hiểu giới hạn của nó.

## 7. Dấu thập phân, dấu nhóm và không gian Unicode

Dữ liệu số có thể hiển thị bằng dấu phân nhóm khác nhau:

| Dữ liệu gốc | Dạng hiển thị minh họa | Ghi chú |
| --- | --- | --- |
| BigDecimal("1234567.89") | **1,234,567.89** | Kiểu quen thuộc trong en-US |
| Cùng giá trị | **1.234.567,89** | Kiểu quen thuộc trong de-DE |
| Cùng giá trị | **1 234 567,89** | Có thể dùng narrow no-break space cho nhóm |
| Cùng giá trị | Các glyph chữ số khác | Có thể gặp khi chọn numbering system khác |

Đây là **ví dụ về các kiểu thường gặp**, không phải cam kết một chuỗi chính xác cho mọi phiên bản Java/CLDR, đặc biệt với khoảng trắng và digits của từng locale.

**Phân biệt các khoảng trắng:**

- **U+0020 SPACE**: dấu cách thông thường.
- **U+00A0 NO-BREAK SPACE (NBSP)**: dấu cách không cho ngắt dòng.
- **U+202F NARROW NO-BREAK SPACE (NNBSP)**: dấu cách hẹp không cho ngắt dòng.

Hai đầu ra có thể **trông y hệt** nhưng khác UTF-16 và **String.equals**. Vì vậy test chính xác các dấu nhóm cần kiểm tra code point, không chỉ nhìn kết quả terminal.

### 7.1. Chương trình soi Unicode code point

**File InspectFormattedCodePoints.java**

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;
import java.util.stream.Collectors;

public class InspectFormattedCodePoints {
    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp ->
                        String.format(Locale.ROOT,
                                "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234567.89");

        Locale locale = Locale.FRANCE;
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);

        String shown = format.format(value);
        System.out.println("locale="
                + locale.toLanguageTag());
        System.out.println("utf16Length="
                + shown.length());
        System.out.println("codePoints="
                + codePoints(shown));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InspectFormattedCodePoints.java
java InspectFormattedCodePoints
~~~

Dòng đầu là **locale=fr-FR**; hai dòng còn lại cho độ dài và danh sách code point của formatter thực tế. **Không gắn cứng một danh sách code point** nếu mục tiêu là chạy được trên nhiều JDK/provider. Khi cần một output exact trong hệ thống sản xuất, hãy cố định runtime/locale data, sau đó viết regression test của chính sản phẩm.

**Sử dụng codePoints thay vì chars** để quan sát đầy đủ Unicode. Trong Java, String.length đếm UTF-16 code units, còn codePoints xử lý các surrogate pair hợp lệ như một code point.

## 8. Ví dụ xác định hoàn toàn với DecimalFormatSymbols

Nếu bạn muốn minh họa **cơ chế** mà không phụ thuộc bản dữ liệu locale, hãy tự khai báo dấu và pattern. Ví dụ này **không còn là yêu cầu tự động locale của JDK**, mà là định dạng do chương trình định nghĩa tường minh.

**File ExplicitNumberSymbols.java**

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ExplicitNumberSymbols {
    private static String style(
            BigDecimal value,
            char grouping,
            char decimal) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        symbols.setGroupingSeparator(grouping);
        symbols.setDecimalSeparator(decimal);

        DecimalFormat format =
                new DecimalFormat("#,##0.00", symbols);
        format.setGroupingUsed(true);
        return format.format(value);
    }

    public static void main(String[] args) {
        BigDecimal value =
                new BigDecimal("1234567.89");

        System.out.println("dotDecimal="
                + style(value, ',', '.'));
        System.out.println("commaDecimal="
                + style(value, '.', ','));
        System.out.println("source="
                + value.toPlainString());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ExplicitNumberSymbols.java
java ExplicitNumberSymbols
~~~

Stdout dự kiến khi dùng **các dấu và pattern đã cấu hình tường minh**:

~~~text
dotDecimal=1,234,567.89
commaDecimal=1.234.567,89
source=1234567.89
~~~

**Điểm học:** một giá trị BigDecimal bất biến có thể được format theo nhiều kiểu ký tự. Pattern **#,##0.00** trong DecimalFormat dùng cú pháp pattern chuẩn, rồi DecimalFormatSymbols quyết định dấu được in. Đầu ra có thể có số chữ số nhóm khác nếu pattern/locale được thay đổi, nhưng ví dụ này giữ cấu hình cụ thể để kết quả xác định.

**Không lấy helper này thay thế hoàn toàn NumberFormat theo locale thực tế.** Một quốc gia có thể có quy tắc đặt dấu âm, ký hiệu tiền, cách nhóm và chữ số phức tạp hơn hai dấu phân cách được minh họa.

## 9. Một Instant, nhiều giờ địa phương

Thời điểm gốc:

~~~text
2026-10-28T02:30:00Z
~~~

là một **Instant**. Nó không có “ngôn ngữ” hoặc định dạng ngày của người dùng. Khi chuyển thành **ZonedDateTime** bằng ZoneId, ta biết thời điểm đó được nhìn như ngày và giờ địa phương nào.

Ví dụ, cùng Instant ở:

- **Asia/Ho_Chi_Minh**: ngày 28/10/2026, giờ địa phương 09:30.
- **America/Los_Angeles**: ngày 27/10/2026, giờ địa phương 19:30 theo quy tắc vùng giờ áp dụng cho ngày đó.

**Hãy phân biệt đổi timezone với đổi Locale.** Đổi Locale có thể thay chuỗi “October 28” thành cách viết ngày tiếng Việt, nhưng không tự đổi giờ. Đổi ZoneId có thể thay ngày lịch, dù Locale giữ nguyên.

### 9.1. Chương trình xác minh độc lập locale

**File SameInstantDifferentZones.java**

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class SameInstantDifferentZones {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-10-28T02:30:00Z");

        ZonedDateTime vietnam =
                event.atZone(ZoneId.of(
                        "Asia/Ho_Chi_Minh"));
        ZonedDateTime california =
                event.atZone(ZoneId.of(
                        "America/Los_Angeles"));

        System.out.println("instant=" + event);
        System.out.println("vn="
                + vietnam.format(
                        DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        System.out.println("la="
                + california.format(
                        DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        System.out.println("sameInstant="
                + vietnam.toInstant()
                        .equals(california.toInstant()));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SameInstantDifferentZones.java
java SameInstantDifferentZones
~~~

Stdout với dữ liệu múi giờ hiện hành cho ngày được dùng:

~~~text
instant=2026-10-28T02:30:00Z
vn=2026-10-28T09:30:00
la=2026-10-27T19:30:00
sameInstant=true
~~~

Đây là ví dụ **không dùng định dạng theo Locale** ở ba dòng thời gian; ISO_LOCAL_DATE_TIME tạo chuỗi kỹ thuật dễ so sánh. Dữ liệu timezone thuộc **tzdb** của runtime, nên với hệ thống yêu cầu tái lập tuyệt đối qua nhiều thập kỷ, vẫn cần kiểm soát phiên bản tzdb; đối với ngày ví dụ, các quy tắc hiện hành cho kết quả như trên.

### 9.2. Vì sao không gọi Instant.toString() để hiển thị cho người dùng?

**Instant.toString()** là biểu diễn kỹ thuật theo UTC. Nó phù hợp log/API và kiểm thử, nhưng không nên dùng làm cách viết ngày giờ duy nhất trong giao diện người dùng đa ngôn ngữ. Muốn hiển thị, chuyển qua **ZoneId** rồi dùng **DateTimeFormatter** với Locale/pattern được chọn.

**LocalDate** ngược lại đã là ngày thuần, thường không cần đổi timezone. Nếu lấy ngày đó rồi tùy tiện chuyển sang Instant tại nửa đêm UTC, một người ở múi giờ âm có thể thấy ngày trước đó: đây là lỗi mô hình hóa.

## 10. DateTimeFormatter: FormatStyle và Locale

Với java.time:

~~~java
DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.LONG).withLocale(locale);

String dateText =
        dateFormatter.format(localDate);
~~~

Đoạn này cần import **DateTimeFormatter**, **FormatStyle**, **Locale**, **LocalDate** và biến locale/localDate. Đối với thời điểm có giờ:

~~~java
ZonedDateTime localMoment =
        instant.atZone(zoneId);

DateTimeFormatter dateTimeFormatter =
        DateTimeFormatter.ofLocalizedDateTime(
                FormatStyle.MEDIUM).withLocale(locale);

String shown = dateTimeFormatter.format(localMoment);
~~~

Đoạn minh họa cần import **Instant**, **ZonedDateTime**, **ZoneId** và các lớp formatter phù hợp. Dùng **FormatStyle.SHORT/MEDIUM/LONG/FULL** tùy chi tiết và giao diện; không giả định mỗi style cho chuỗi có độ rộng cố định.

**Một số locale có cách viết số/tháng hoặc thứ tự thành phần khác.** Việc DateTimeFormatter dùng localized pattern giúp tận dụng dữ liệu vùng của JDK, nhưng output có thể thay đổi giữa các bản CLDR. Nếu API nhập/xuất máy cần ổn định, hãy dùng ISO formatter chứ không parse ngược chuỗi localized.

### 10.1. Giữ ngày nguyên bản thay vì nhét timezone

~~~java
LocalDate scheduled = LocalDate.of(2026, 10, 28);
~~~

Ngày đã có ý nghĩa lịch, không cần ZoneId để hiển thị. Dùng FormatStyle để trình bày “ngày 28 tháng 10 năm 2026” hoặc biến thể tương đương theo locale/runtime. Đổi Locale không làm thay đổi LocalDate gốc.

Đối với **ngày sinh, ngày hợp đồng hoặc ngày học**, thường nên lưu LocalDate; đối với **thời điểm tạo đơn, thanh toán và sự kiện**, lưu Instant (hoặc một kiểu có thông tin vùng theo hợp đồng), rồi chọn ZoneId khi hiển thị.

## 11. Múi giờ không đồng nghĩa locale

| Thuộc tính | Ví dụ | Câu hỏi |
| --- | --- | --- |
| Locale | vi-VN | Viết ngày và số theo quy ước nào? |
| ZoneId | Asia/Ho_Chi_Minh | Người xem đang dùng quy tắc giờ vùng nào? |
| Currency | EUR | Đơn vị tiền gốc là gì? |
| Instant | 2026-10-28T02:30:00Z | Sự kiện diễn ra khi nào? |
| LocalDate | 2026-10-28 | Ngày lịch nào được lưu? |

Một người dùng Locale.US có thể ở Nhật Bản; một người Việt Nam có thể đang làm việc tại Canada. Không nên suy ra ZoneId từ mã quốc gia của Locale, và không nên dùng **TimeZone.getDefault()** làm quy tắc ngầm của một giao dịch quan trọng.

Đối với trường giờ mùa hè (DST), chuyển **Instant → ZonedDateTime** bằng ZoneId là xác định khi tzdb đã biết. Nhưng chuyển một **LocalDateTime không có zone** sang instant có thể gặp thời gian không tồn tại hoặc thời gian lặp lại trong chuyển DST; ứng dụng cần một chính sách rõ.

## 12. Tỷ lệ phần trăm: giá trị 0.125 khác 12.5

Ví dụ thuế **taxRatio=0.125** có nghĩa **12,5%**. **NumberFormat.getPercentInstance(locale)** thường nhân tỷ lệ lên 100 để trình bày thành phần trăm. Đừng truyền **12.5** rồi mong formatter hiển thị 12,5%: nó có thể hiển thị 1.250%.

Trong chương trình:

~~~java
NumberFormat percent =
        NumberFormat.getPercentInstance(locale);
percent.setMinimumFractionDigits(1);
percent.setMaximumFractionDigits(1);

String tax = percent.format(
        new BigDecimal("0.125"));
~~~

Đây là đoạn minh họa, cần import NumberFormat, Locale, BigDecimal và biến locale. Dạng chữ số, vị trí ký hiệu phần trăm và khoảng trắng phụ thuộc locale, nhưng giá trị gốc vẫn là **0.125**.

**Không đồng nhất representation với arithmetic.** Nếu cần tính số tiền thuế, dùng BigDecimal và rounding policy trong domain. NumberFormat chỉ giúp hiển thị tỷ lệ.

## 13. Định dạng âm, dấu tiền và ký hiệu Unicode

Khi hiển thị cùng giá trị âm:

~~~java
BigDecimal negative =
        new BigDecimal("-1234.50");
~~~

các locale có thể thay đổi vị trí dấu âm, vị trí ký hiệu tiền và khoảng trắng. Một số hệ thống kế toán muốn đặt số âm trong ngoặc, nhưng đó thường là **yêu cầu format/accounting policy**, không nên giả định **getCurrencyInstance** mọi locale đều in ngoặc cho âm.

Không tự ghép kiểu:

~~~java
String wrong = "-" + currency.getSymbol() + amount;
~~~

Đây là đoạn minh họa anti-pattern, cần các biến currency và amount. Nó bỏ qua dấu âm, cách nhóm, dấu thập phân, khoảng trắng no-break và nhiều quy tắc địa phương hóa. Dùng NumberFormat với Currency được chọn và cấu hình thêm khi chính sách kế toán đòi hỏi.

**Các ký tự khó nhìn** như U+00A0, U+202F hoặc bidi marks có thể là phần hợp lệ của localized output. Nếu làm PDF/email, phải đảm bảo font và renderer giữ được chúng.

## 14. Locale tiếng Ả Rập và văn bản hai chiều

Với **ar-EG**, chữ số và ký hiệu có thể chứa các code point hoặc dấu hướng khác với en-US. Nếu bạn đưa **số tiền** vào câu LTR hoặc đưa mã đơn **ORD-2026-1028** vào một câu RTL, quy tắc **Unicode Bidirectional Algorithm** quyết định vị trí dấu câu/nhóm số trên màn hình.

Nguyên tắc:

- **Không đảo String thủ công** bằng reverse vì sẽ làm hỏng chữ số, ID và từ LTR.
- Giữ dữ liệu ở **logical order** và để renderer hỗ trợ bidi.
- Với web, dùng **dir** và vùng isolation như **bdi** khi nhúng nội dung người dùng không biết hướng.
- Không coi chỉ đổi Locale là đã tự đặt text direction cho mọi thành phần UI.
- Khi kiểm thử các định dạng tiền có dấu cách, xem cả code point và ảnh render ở môi trường thật.

Ví dụ HTML minh họa nguyên tắc UI (không phải mã Java):

~~~html
<p dir="rtl">
  <bdi dir="auto">ORD-2026-1028</bdi>
</p>
~~~

**Bidi isolation không thay thế HTML escaping.** Tham số không tin cậy vẫn phải được render bằng API an toàn theo ngữ cảnh.

## 15. Có nên format rồi parse ngược?

Dữ liệu ở giao diện thường được trình bày bằng NumberFormat hoặc DateTimeFormatter. Một lỗi là dùng chuỗi đã format để làm dữ liệu nguồn ở nơi khác.

Ví dụ:

~~~text
1234567.89  --vi-VN display-->  [chuỗi theo locale]
                                      |
                                      v
                       cố parse lại bằng Locale.US
                                      |
                                      v
                             có thể sai dữ liệu
~~~

**Khi trao đổi giữa máy**, ưu tiên dữ liệu có kiểu hoặc định dạng kỹ thuật được đặc tả: JSON number/decimal string theo hợp đồng, ISO 8601 cho Instant và LocalDate, mã Currency ISO. Với dữ liệu người dùng nhập từ form theo locale, dùng parser có cấu hình thích hợp và kiểm tra **tiêu thụ hết chuỗi**, phạm vi và rounding.

### 15.1. NumberFormat.parse có thể mất độ chính xác thập phân nếu dùng sai

Một số parser NumberFormat có thể trả **Long** hoặc **Double**, tùy kiểu/giá trị; đừng cast hoặc chuyển sang BigDecimal bằng các giả định tùy tiện khi cần tiền chính xác. Với DecimalFormat trong trường hợp cần BigDecimal, có **setParseBigDecimal(true)**.

**Code minh họa:**

~~~java
DecimalFormat format =
        (DecimalFormat) NumberFormat.getNumberInstance(
                locale);
format.setParseBigDecimal(true);

ParsePosition pos = new ParsePosition(0);
Number parsed = format.parse(text, pos);

boolean complete =
        parsed != null && pos.getIndex() == text.length();
~~~

Đây là đoạn trong phương thức, cần import DecimalFormat, NumberFormat, ParsePosition, Locale, biến locale và text; việc cast cũng cần hiểu implementation thực tế. Có thể tạo DecimalFormat trực tiếp với pattern/symbols rõ để tránh dựa vào loại formatter của một provider khác.

**Cẩn thận:** một parser lenient có thể nhận tiền tố hợp lệ rồi bỏ phần đuôi. Nếu đầu vào phải đúng hoàn toàn, kiểm tra index và cú pháp. Khi có currency symbol, cần parser/format riêng theo hợp đồng giao diện, không dùng một regex ASCII cho mọi locale.

### 15.2. DateTimeFormatter với ResolverStyle

Với ngày người dùng nhập theo pattern rõ, java.time hỗ trợ:

~~~java
DateTimeFormatter inputFormat =
        DateTimeFormatter.ofPattern(
                "dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed =
        LocalDate.parse("28/10/2026", inputFormat);
~~~

Đoạn minh họa cần imports DateTimeFormatter, ResolverStyle, LocalDate, Locale. **uuuu** là proleptic year phù hợp hơn **yyyy** trong nhiều trường hợp dùng ResolverStyle.STRICT; **yyyy** là year-of-era và có quy tắc giải quyết khác.

Đừng dùng một localized display string làm API định dạng cố định. **Input format**, **display format** và **machine/API format** cần hợp đồng riêng.

## 16. Bài tập tích hợp hai người xem

Hãy giữ nguyên OrderData của chương trình chính và tạo hai ngữ cảnh:

~~~text
Viewer A:
    uiLocale=vi-VN
    formatLocale=vi-VN
    zoneId=Asia/Ho_Chi_Minh

Viewer B:
    uiLocale=en-US
    formatLocale=en-US
    zoneId=America/Los_Angeles
~~~

Trong mỗi lần render:

1. Format quantity và subtotal bằng formatLocale.
2. Format ratio thành phần trăm.
3. Format scheduledDate bằng FormatStyle.LONG: **ngày thuần không đổi**.
4. Chuyển eventTime sang zoneId rồi format ngày giờ: **giờ và có thể cả ngày địa phương khác**.
5. Dùng ResourceBundle riêng để lấy câu theo uiLocale nếu ứng dụng có bundle.
6. Đặt cùng ID đơn hàng và Currency EUR vào câu.
7. So dữ liệu gốc trước/sau để bảo đảm không bị sửa bởi renderer.

**Không gửi chuỗi kết quả của Viewer A để Viewer B parse rồi dùng lại.** Mỗi người xem cần format từ một nguồn dữ liệu có kiểu.

## 17. Kết hợp ResourceBundle và MessageFormat

Nếu cần cả **bản dịch câu** và **số/ngày địa phương**, tổ chức các bundle:

~~~text
messages_en.properties
messages_vi.properties
~~~

**messages_en.properties:**

~~~properties
order.summary=Order {0}: total {1}; scheduled {2}.
~~~

**messages_vi.properties:**

~~~properties
order.summary=Đơn {0}: tổng {1}; lịch hẹn {2}.
~~~

Sau khi formatter riêng tạo **moneyText** và **dateText**, dùng:

~~~java
ResourceBundle messages =
        ResourceBundle.getBundle("messages", uiLocale);

MessageFormat template =
        new MessageFormat(
                messages.getString("order.summary"),
                uiLocale);

String text = template.format(new Object[] {
        orderId, moneyText, dateText
});
~~~

Đoạn minh họa trong một phương thức cần imports **ResourceBundle**, **MessageFormat**, **Locale**, cùng biến uiLocale/orderId/moneyText/dateText. Người dịch có thể đổi vị trí {0}, {1}, {2} theo ngữ pháp; code không hardcode thứ tự từ.

**Chú ý dấu nháy đơn:** MessageFormat có cú pháp quote riêng; muốn dấu nháy đơn literal trong pattern thường phải nhân đôi thành **''**. Bản dịch cần được kiểm thử key, placeholder và quote syntax.

**ResourceBundle fallback** cũng cần chính sách ứng dụng. Có bundle mặc định không đồng nghĩa đã dịch đầy đủ mọi locale JDK hỗ trợ. **Locale.getAvailableLocales()** không nên dùng thẳng làm danh sách dropdown ngôn ngữ của sản phẩm.

## 18. Thiết kế định dạng thành một dịch vụ

Trong ứng dụng thật, các controller không nên tự lặp logic NumberFormat và DateTimeFormatter. Có thể tạo một **FormattingService**:

~~~java
interface FormattingService {
    String decimal(BigDecimal value, Locale locale);

    String money(
            BigDecimal amount,
            Currency currency,
            Locale locale);

    String day(LocalDate date, Locale locale);

    String moment(
            Instant instant,
            ZoneId zoneId,
            Locale locale);
}
~~~

Đây là mô tả interface cần imports BigDecimal, Currency, Locale, LocalDate, Instant, ZoneId. Nó phân biệt ngày thuần với thời điểm và không đồng nhất Currency với Locale.

Một **LocaleResolver** chọn locale theo preferences/supported locales; một **MessageService** chọn bundle/pattern; một **Presenter** phối hợp các giá trị đã format để tạo câu. Dữ liệu nghiệp vụ không phụ thuộc dịch vụ trình bày.

**Không tạo một mutable static NumberFormat dùng chung** rồi setCurrency theo từng request. NumberFormat và DecimalFormat không thread-safe để dùng đồng thời thiếu bảo vệ. DateTimeFormatter immutable và thread-safe hơn cho việc cache theo Locale/FormatStyle. MessageFormat cũng mutable, nên tạo/cách ly instance khi chèn tham số.

## 19. Locale mặc định và độc lập môi trường

Một bài test chỉ chạy đúng trên máy dev có thể lỗi khi CI đặt Locale hoặc TimeZone mặc định khác. Để tránh:

- Gọi **NumberFormat.getNumberInstance(locale)** thay vì bỏ locale.
- Gọi **DateTimeFormatter.withLocale(locale)** tường minh.
- Truyền **ZoneId** từ chính sách ứng dụng.
- Không gọi **Locale.setDefault(...)** hoặc **TimeZone.setDefault(...)** trong mỗi request.
- Không gọi **Currency.getInstance(locale)** nếu đơn vị tiền của giao dịch đã có riêng.
- Không dùng **Date.toString()** để snapshot ngày giờ có ý nghĩa với người dùng.
- Dùng Locale.ROOT/ISO cho log kỹ thuật khi hợp đồng yêu cầu chuỗi ổn định.

Không suy rằng **vi-VN** tự đồng nghĩa **Asia/Ho_Chi_Minh** hay VND. Locale, ZoneId và Currency là ba khía cạnh khác nhau.

## 20. Kiểm thử đúng: giá trị, hành vi và Unicode

Một chiến lược gồm ba lớp.

### 20.1. Unit tests cho giá trị gốc

Assert trực tiếp:

~~~text
BigDecimal quantity: 1234567.89
BigDecimal subtotal: 1234.50
Currency code: EUR
Ratio: 0.125
LocalDate: 2026-10-28
Instant: 2026-10-28T02:30:00Z
~~~

Các giá trị này **không thay đổi khi format theo Locale**. Test không cần dựa vào dấu thập phân hoặc ký hiệu tiền của CLDR.

### 20.2. Integration tests với JDK mục tiêu

Chạy bảng sáu locale trên runtime được sản phẩm hỗ trợ, kiểm tra:

- Formatter không ném lỗi với dữ liệu và locale bắt buộc.
- Độ chính xác/fraction digits phù hợp hợp đồng.
- Currency code gốc vẫn là EUR.
- Ngày thuần không bị thay.
- Cùng Instant cho các giờ địa phương phù hợp ZoneId.
- Không rò rỉ locale hoặc Currency giữa request đồng thời.
- Giá trị Unicode được giữ khi lưu/render.
- Output thay đổi khi nâng JDK/CLDR có được xem xét.

Nếu sản phẩm yêu cầu snapshot chuỗi đầy đủ, hãy **kiểm soát phiên bản JDK/provider và dữ liệu locale**. Đừng khẳng định một chuỗi tiền cụ thể giống nhau tuyệt đối trên mọi môi trường.

### 20.3. Visual tests

Các ký tự **U+00A0**, **U+202F**, ký hiệu EUR, glyph Ả Rập và dấu RTL có thể hiển thị khác ở terminal, web, email hoặc PDF. Hãy kiểm thử trên renderer thực tế với font và hướng chữ đúng.

**Chỉ so String.equals không thay thế kiểm tra visual layout**; ngược lại, hai chuỗi trông giống nhau không chứng minh code point giống nhau. Kết hợp code-point inspection với ảnh UI khi cần.

## 21. Test mạnh hơn: giữ bất biến dù đổi locale

Một test integration có thể chạy nhiều locale rồi kiểm tra bất biến sau mỗi lượt:

~~~java
BigDecimal beforeAmount =
        order.subtotal();
Currency beforeCurrency =
        order.currency();
Instant beforeInstant =
        order.createdAt();

// Gọi display(order, locale, zone) nhiều lần.

boolean unchanged =
        beforeAmount.equals(order.subtotal())
        && beforeCurrency.equals(order.currency())
        && beforeInstant.equals(order.createdAt());
~~~

Đoạn minh họa trong class **MultiLocaleDisplayLab** cần có biến **order**, **locale**, **zone** và method **display** như mục 5. Đây là cách kiểm tra rằng tầng trình bày không làm hỏng dữ liệu nghiệp vụ.

Bên cạnh đó, kiểm tra **amount.scale()** và các quy tắc làm tròn nếu scale mang ý nghĩa trong hợp đồng của bạn. BigDecimal.equals xét cả scale, trong khi **compareTo** có thể xem 1234.5 và 1234.50 có cùng giá trị số; đừng vô tình dùng một kiểu equality khác với yêu cầu.

## 22. Lỗi phổ biến khi làm thực hành

### Lỗi 1: Tạo formatter theo Locale của server

Một app chạy trên server en-US có thể in dấu phẩy thập phân khác user fr-FR. Truyền Locale người xem tường minh.

### Lỗi 2: Dùng một String đã format làm số tiền nguồn

Chuỗi localized có thể chứa dấu nhóm và NBSP. Lưu BigDecimal + Currency, format lại cho mỗi locale.

### Lỗi 3: Đổi Locale rồi nghĩ tự đổi Currency

Locale không phải tỷ giá. setCurrency cũng không làm phép quy đổi; chỉ đổi cách gắn đơn vị hiển thị.

### Lỗi 4: Nhầm 0.125 với 12.5 khi dùng PercentInstance

NumberFormat phần trăm có hệ số 100 khi trình bày. Xác định rõ taxRatio là fraction hay percent value.

### Lỗi 5: Dùng double cho số tiền

Double có xấp xỉ nhị phân; chọn BigDecimal với nguồn dữ liệu chính xác và rounding policy rõ.

### Lỗi 6: Dùng Instant như LocalDate

Instant cần ZoneId để ra ngày địa phương. Cùng instant có thể là ngày 27 ở Los Angeles và ngày 28 ở Việt Nam.

### Lỗi 7: Gắn ZoneId từ Locale

Locale là ngôn ngữ/vùng trình bày, không chỉ ra chắc chắn timezone của người dùng.

### Lỗi 8: Hardcode dd/MM/yyyy cho tất cả ngôn ngữ

DateTimeFormatter theo FormatStyle/Locale cho quy ước từng vùng; dữ liệu API máy dùng format cố định riêng.

### Lỗi 9: So output tiền bằng mắt

NNBSP/NBSP và bidi controls có thể vô hình. Khi cần so chính xác, in Unicode code point.

### Lỗi 10: Snapshot mọi chuỗi theo CLDR mà không pin JDK

Khi runtime nâng cấp, tên tháng hoặc khoảng trắng có thể khác. Phân biệt test logic bất biến với test phiên bản dữ liệu locale.

### Lỗi 11: Chia sẻ NumberFormat mutable toàn server

Các request locale/currency khác nhau có thể gây race và in sai. Tạo formatter theo thao tác hoặc cách ly rõ.

### Lỗi 12: Dịch mã đơn hàng hoặc Currency bằng ResourceBundle

ID và mã tiền là dữ liệu kỹ thuật/miền; message bundle chỉ dịch văn bản UI, trừ khi sản phẩm có tên hiển thị địa phương được khai báo riêng.

### Lỗi 13: Tự nối ký hiệu tiền và dấu âm

Vị trí ký hiệu, dấu âm, khoảng trắng thuộc quy tắc format. Dùng NumberFormat hoặc pattern rõ theo yêu cầu.

### Lỗi 14: Parse số/ngày localized bằng Locale khác

Có thể đọc sai giá trị hoặc bỏ phần đuôi. Dùng parser đúng locale và kiểm tra toàn chuỗi; tốt nhất dùng dữ liệu có kiểu cho trao đổi giữa máy.

### Lỗi 15: Không test giao diện RTL

Locale Ả Rập có thể cần direction và isolation. Formatter không thay text layout engine.

### Lỗi 16: Không tách UI language và format locale

Một user cần tiếng Anh nhưng muốn số ngày theo Đức. Thiết kế context có hai locale thay vì buộc một.

## 23. Bài tập mở rộng

1. Giữ nguyên dữ liệu OrderData, thay **Locale.CANADA_FRENCH** hoặc **fr-CA** vào danh sách. Quan sát số tiền EUR khác gì với fr-FR.
2. Thêm **Locale.forLanguageTag("hi-IN")**; kiểm tra grouping và hệ số nhóm theo runtime, không giả định luôn giống en-US.
3. Thêm locale có Unicode extension yêu cầu một numbering system, ví dụ **en-US-u-nu-arab**, rồi kiểm tra chức năng nào hỗ trợ và output của NumberFormat.
4. Thử hiển thị **-1234.50 EUR** và so vị trí dấu âm/ký hiệu.
5. Thử một Currency khác như JPY nhưng giữ đúng nghiệp vụ **đã đổi đồng tiền đầu vào**; quan sát số chữ số mặc định.
6. Thử DateTimeFormatter FormatStyle.SHORT và FULL, so độ dài/tên tháng nhưng không fix output qua mọi JDK.
7. Thử cùng Instant ở Europe/Berlin và America/Los_Angeles; quan sát ngày, DST và giá trị epoch không đổi.
8. Dùng ResourceBundle để tạo một câu tiếng Việt và câu tiếng Anh chứa cùng số tiền EUR và ngày có kiểu.
9. Tạo unit test cho **BigDecimal("1234.50")**, Currency EUR và Instant không đổi qua sáu lượt format.
10. Tạo một trang web/email nhỏ hiển thị ar-EG, kiểm tra dấu câu, ký hiệu tiền và khả năng copy mã đơn hàng.
11. Cố tình gửi chuỗi có NBSP tới validator ASCII-only, xem vì sao thiết kế cần biết hợp đồng đầu vào và Unicode.
12. Giả lập thiếu bản dịch locale mới, thử fallback có được ứng dụng công bố rõ không.

## 24. Checklist áp dụng trong dự án

- [ ] Dữ liệu gốc giữ BigDecimal, Currency, LocalDate, Instant riêng biệt.
- [ ] Đã xác định uiLocale, formatLocale và ZoneId cho từng người xem.
- [ ] Không suy Currency từ Locale khi giao dịch đã có đơn vị tiền riêng.
- [ ] Dùng NumberFormat.getNumberInstance(locale) để hiển thị số.
- [ ] Dùng NumberFormat.getCurrencyInstance(locale) cùng setCurrency để hiển thị tiền.
- [ ] Dùng NumberFormat.getPercentInstance(locale) khi input là tỷ lệ.
- [ ] Không dùng double làm nguồn tiền chính xác khi có thể dùng BigDecimal.
- [ ] Biết fraction digits của Currency không thay thế rounding policy nghiệp vụ.
- [ ] Dùng DateTimeFormatter với FormatStyle và Locale cho LocalDate.
- [ ] Chuyển Instant qua ZoneId khi cần ngày/giờ người xem.
- [ ] Giữ ISO format cho trao đổi kỹ thuật, không parse localized output bằng locale khác.
- [ ] Không gọi Locale.setDefault trong một request có nhiều người dùng.
- [ ] Không chia sẻ NumberFormat/DecimalFormat mutable để sửa đồng thời.
- [ ] Biết ký hiệu tiền/dấu nhóm có thể chứa NBSP hoặc NNBSP.
- [ ] Khi test chính xác Unicode, dùng codePoints() và kiểm soát JDK/provider.
- [ ] Kiểm thử hiển thị RTL và font trong renderer mục tiêu.
- [ ] Dùng ResourceBundle/MessageFormat cho phần văn bản cần dịch.
- [ ] Không dùng JDK available locales làm menu ngôn ngữ của app nếu chưa có bản dịch.
- [ ] Có test bất biến dữ liệu gốc và test integration formatting đa locale.
- [ ] Có hồi quy khi nâng JDK/CLDR hoặc tzdb trong những tính năng quan trọng.

## 25. Kết luận

**Hiển thị cùng dữ liệu số, tiền tệ, ngày giờ ở nhiều locale** là bài tập về sự khác biệt giữa **giá trị** và **cách biểu diễn**. Java 17+ cung cấp **BigDecimal/Currency** để giữ số tiền, **LocalDate/Instant/ZoneId** để mô hình hóa thời gian, **NumberFormat** và **DateTimeFormatter** để trình bày theo Locale, cùng **ResourceBundle/MessageFormat** để tạo câu đã dịch.

Đổi **Locale** có thể làm thay ký hiệu tiền, vị trí dấu âm, dấu thập phân, khoảng trắng, thứ tự thành phần và tên tháng; đổi **ZoneId** có thể làm thay ngày/giờ của cùng một Instant; nhưng **không phép đổi cách hiển thị nào được làm đổi dữ liệu nghiệp vụ**. Khi tách ranh giới ấy, kiểm thử bằng dữ liệu bất biến và quan sát Unicode trên runtime thực tế, ứng dụng có thể phục vụ nhiều ngôn ngữ mà vẫn chính xác và nhất quán.
