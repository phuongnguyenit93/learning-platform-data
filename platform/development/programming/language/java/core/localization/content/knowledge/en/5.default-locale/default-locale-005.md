# Truyền locale tường minh tới từng thao tác định dạng trong Java

## 1. Vấn đề cần giải quyết

Một chương trình Java có thể chạy trên máy chủ ở Việt Nam, xử lý dữ liệu của khách hàng Đức và hiển thị kết quả cho người dùng Mỹ. Nếu gọi các API định dạng mà **không chỉ định `Locale`**, kết quả có thể phụ thuộc **locale mặc định của JVM**. Điều này khiến cùng một dữ liệu có cách hiển thị khác nhau khi chạy trên máy phát triển, môi trường kiểm thử hoặc production.

Hãy xem cùng giá trị số `1234.5`:

| Locale định dạng | Cách hiển thị số thường gặp | Ý nghĩa dấu phân tách |
| --- | --- | --- |
| `Locale.US` (`en-US`) | `1,234.50` | Dấu phẩy nhóm hàng nghìn, dấu chấm phần thập phân |
| `Locale.GERMANY` (`de-DE`) | `1.234,50` | Dấu chấm nhóm hàng nghìn, dấu phẩy phần thập phân |
| `Locale.FRANCE` (`fr-FR`) | `1 234,50` | Dấu nhóm thường là khoảng trắng hẹp không ngắt trong dữ liệu CLDR hiện đại |

Giá trị số **không đổi**; chỉ có chuỗi trình bày thay đổi. Dấu nhóm của một locale có thể khác theo phiên bản JDK, provider và dữ liệu CLDR, nên không nên tự viết logic thay thế `,` thành `.` hoặc giả định mọi dấu cách đều là ASCII.

**Nguyên tắc của bài:** Khi biết đối tượng nhận kết quả và quy ước cần dùng, hãy **truyền `Locale` tường minh cho từng thao tác định dạng hoặc phân tích dữ liệu**, thay vì dựa vào locale mặc định mang tính toàn cục.

Ví dụ:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.GERMANY);
DateTimeFormatter date = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.US);
String summary = String.format(Locale.US, "Total: %.2f", 1234.5);
~~~

Đây là các **mảnh lệnh minh họa**; đặt trong mã có import `java.text.NumberFormat`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle` và `java.util.Locale`. Cần phân biệt: `Locale` quyết định quy ước ngôn ngữ/vùng, còn múi giờ, đơn vị tiền tệ, chronology và dữ liệu nghiệp vụ có thể cần chỉ định riêng.

## 2. Locale mặc định và locale tường minh

### Locale mặc định hoạt động như thế nào?

Một số factory hoặc hàm Java không nhận tham số `Locale` sẽ dựa vào locale mặc định của quá trình JVM, ví dụ:

~~~java
NumberFormat implicit = NumberFormat.getNumberInstance();
String text = String.format("%,.2f", 1234.5);
~~~

Nếu không chủ động truyền locale, đầu ra chịu ảnh hưởng của `Locale.getDefault()` hoặc mặc định cho danh mục `Locale.Category.FORMAT` theo từng API. Máy chủ hoặc tiến trình có thể dùng locale khác dự kiến. Java còn có `Locale.Category.DISPLAY` phục vụ tên hiển thị, khác với danh mục `FORMAT` dùng cho nhiều API định dạng.

Một thao tác như `Locale.setDefault(Locale.GERMANY)` thay đổi trạng thái dùng chung của JVM. Nếu ứng dụng phục vụ nhiều request đồng thời, thay đổi mặc định để định dạng một request rồi đổi lại có thể làm request khác nhận nhầm quy ước. Vì vậy **không gọi `Locale.setDefault` cho từng người dùng, từng request hoặc từng thao tác**.

### Locale tường minh đem lại điều gì?

~~~java
NumberFormat germanNumber =
        NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat usNumber =
        NumberFormat.getNumberInstance(Locale.US);
~~~

Hai formatter dùng hai quy ước độc lập về locale. Chúng có thể được dùng trong cùng chương trình mà không cần sửa mặc định JVM. Cách này:

- Làm yêu cầu định dạng hiển thị ngay tại nơi gọi API.
- Hạn chế phụ thuộc vào cấu hình máy hoặc thứ tự chạy test.
- Phục vụ nhiều người dùng có locale khác nhau trong cùng tiến trình.
- Giúp kiểm tra đầu ra và đường xử lý lỗi theo từng locale.
- Giữ lựa chọn locale gần dữ liệu hoặc ngữ cảnh giao diện cần định dạng.

`Locale` là đối tượng bất biến, có thể chia sẻ an toàn. **Nhưng không suy ra mọi formatter đều bất biến**: các lớp `NumberFormat`, `DecimalFormat`, `DateFormat` và `MessageFormat` có trạng thái thay đổi; đừng chia sẻ một instance mutable giữa nhiều luồng mà không có thiết kế đồng bộ phù hợp. `DateTimeFormatter` của `java.time` là bất biến và an toàn để tái sử dụng giữa các luồng.

## 3. Ví dụ đầy đủ: định dạng số, ngày và chuỗi cho từng locale

Ví dụ dưới đây dùng ngày và số cố định để tránh phụ thuộc thời điểm hiện tại. Lưu vào tệp `ExplicitLocaleDemo.java`:

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitLocaleDemo {
    public static void main(String[] args) {
        double amount = 1234.5;
        LocalDate day = LocalDate.of(2025, 7, 14);

        Locale us = Locale.US;
        Locale germany = Locale.GERMANY;

        NumberFormat usNumbers = NumberFormat.getNumberInstance(us);
        NumberFormat deNumbers = NumberFormat.getNumberInstance(germany);

        usNumbers.setMinimumFractionDigits(2);
        usNumbers.setMaximumFractionDigits(2);
        deNumbers.setMinimumFractionDigits(2);
        deNumbers.setMaximumFractionDigits(2);

        DateTimeFormatter usDate =
                DateTimeFormatter.ofPattern("d MMMM uuuu", us);
        DateTimeFormatter deDate =
                DateTimeFormatter.ofPattern("d MMMM uuuu", germany);

        System.out.println("US number: " + usNumbers.format(amount));
        System.out.println("DE number: " + deNumbers.format(amount));
        System.out.println("US date: " + day.format(usDate));
        System.out.println("DE date: " + day.format(deDate));
        System.out.println("US printf: "
                + String.format(us, "%.2f", amount));
        System.out.println("DE printf: "
                + String.format(germany, "%.2f", amount));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ExplicitLocaleDemo.java
java ExplicitLocaleDemo
~~~

Với dữ liệu locale CLDR thông dụng của JDK, đầu ra là:

~~~text
US number: 1,234.50
DE number: 1.234,50
US date: 14 July 2025
DE date: 14 Juli 2025
US printf: 1234.50
DE printf: 1234,50
~~~

Giải thích:

1. Cùng một `amount` và `day` được đưa qua hai bộ định dạng. Không cần thay đổi dữ liệu hay default locale.
2. `NumberFormat.getNumberInstance(locale)` dùng quy ước phân nhóm và dấu thập phân của locale. Ở đây đặt rõ hai chữ số phần thập phân để kết quả minh họa dễ đối chiếu.
3. `DateTimeFormatter.ofPattern(pattern, locale)` truyền locale ngay lúc tạo formatter, do đó tên tháng bằng tiếng Anh hoặc tiếng Đức. `uuuu` biểu thị năm theo hệ năm proleptic của ISO date trong ví dụ này.
4. `String.format(locale, ...)` chuyển cùng giá trị số theo locale. Mẫu `%.2f` làm tròn để hiển thị hai chữ số phần thập phân nhưng **không** tự thêm dấu nhóm; muốn nhóm chữ số có thể dùng `%,.2f`.
5. Trong ví dụ có pattern và format riêng của `NumberFormat`/`String.format`; không được mong `String.format` và `NumberFormat` luôn tạo cùng mẫu chuỗi nếu cấu hình khác nhau.

Tên tháng và ký hiệu phân tách có thể bị ảnh hưởng bởi provider/JDK hoặc phiên bản dữ liệu locale. Nếu sản phẩm cần cố định chính xác cách trình bày trên nhiều nền tảng, cần kiểm tra cấu hình provider và kiểm thử ở môi trường triển khai. **Không nên dùng chuỗi số/ngày đã bản địa hóa làm khóa giao tiếp giữa các hệ thống.**

## 4. Truyền locale cho từng API định dạng thường dùng

### 4.1. Số thường, phần trăm, tiền tệ

`java.text.NumberFormat` cung cấp các factory tường minh:

~~~java
Locale userLocale = Locale.forLanguageTag("vi-VN");

NumberFormat decimal = NumberFormat.getNumberInstance(userLocale);
NumberFormat integer = NumberFormat.getIntegerInstance(userLocale);
NumberFormat percent = NumberFormat.getPercentInstance(userLocale);
NumberFormat money = NumberFormat.getCurrencyInstance(userLocale);

String a = decimal.format(1234.5);
String b = integer.format(1234);
String c = percent.format(0.125);
String d = money.format(1234.5);
~~~

Đây là mã minh họa đặt trong method với import `java.text.NumberFormat` và `java.util.Locale`. Mỗi factory chọn quy ước phù hợp với loại dữ liệu cần trình bày:

| Factory | Ý nghĩa đầu vào | Điểm dễ nhầm |
| --- | --- | --- |
| `getNumberInstance(locale)` | Số thông thường | Số chữ số thập phân mặc định và việc làm tròn cần được thiết kế rõ |
| `getIntegerInstance(locale)` | Hiển thị/phân tích theo kiểu số nguyên | Không sử dụng để bảo toàn phần thập phân |
| `getPercentInstance(locale)` | Tỷ lệ, ví dụ `0.125` biểu thị 12,5% tùy quy tắc | Không đưa `12.5` nếu nghĩa nghiệp vụ là 12,5% |
| `getCurrencyInstance(locale)` | Giá trị tiền có ký hiệu/định dạng địa phương | Locale không nhất thiết xác định **đồng tiền giao dịch** |

**Tiền tệ cần hai thông tin tách biệt:** locale người đọc và `Currency` thực tế của số tiền. Ví dụ một khách hàng tại Đức có thể xem số tiền tính bằng USD:

~~~java
Locale viewer = Locale.GERMANY;
NumberFormat usd = NumberFormat.getCurrencyInstance(viewer);
usd.setCurrency(java.util.Currency.getInstance("USD"));

String displayed = usd.format(1234.50);
~~~

Không giả định `Locale.GERMANY` đồng nghĩa mọi số tiền đều bằng EUR. Mẫu hiển thị vẫn tùy locale/provider. Với tiền trong nghiệp vụ, ưu tiên `BigDecimal` cho tính toán chính xác và quy tắc làm tròn được xác định, rồi mới định dạng để hiển thị. Dùng `double` như trong ví dụ đơn giản là để minh họa API định dạng.

### 4.2. Ngày giờ với `java.time`

Có hai cách truyền locale tường minh:

~~~java
Locale language = Locale.forLanguageTag("fr-FR");

DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(language);

DateTimeFormatter custom = DateTimeFormatter
        .ofPattern("d MMMM uuuu", language);

String first = LocalDate.of(2025, 7, 14).format(localized);
String second = LocalDate.of(2025, 7, 14).format(custom);
~~~

Đây là đoạn minh họa trong method, cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle` và `java.util.Locale`.

- `ofLocalizedDate(FormatStyle.LONG)` dùng kiểu trình bày ngày phù hợp locale; `withLocale(locale)` chọn locale cho formatter.
- `ofPattern("d MMMM uuuu", locale)` sử dụng pattern do ứng dụng quyết định, nhưng tên tháng vẫn nhận ngôn ngữ từ locale.
- Hai lựa chọn có mục đích khác nhau: **localized style** cho quyền quyết định bố cục ngày theo quy tắc địa phương; **custom pattern** cho bố cục mà ứng dụng muốn giữ cố định.
- `LocalDate` chỉ là ngày, không chứa giờ hay múi giờ. `Locale` không tự xác định `ZoneId`.

Khi định dạng `Instant` hoặc lịch hẹn thực tế, hãy xác định múi giờ của người dùng bên cạnh locale:

~~~java
Instant instant = Instant.parse("2025-07-14T10:00:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Locale locale = Locale.forLanguageTag("vi-VN");

DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(locale)
        .withZone(zone);

String shown = formatter.format(instant);
~~~

Đoạn mã minh họa này cần import `java.time.Instant`, `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, `java.util.Locale`. Cùng locale vẫn có thể hiển thị các giờ khác nhau khi timezone khác nhau; ngược lại, cùng timezone có thể có bản dịch tên tháng, bố cục ngày và cách hiển thị khác nhau theo locale.

**Không dùng `LocalDateTime` như thể đã chứa múi giờ**; đây là kiểu ngày giờ chưa gắn zone/offset. Khi chuyển từ thời điểm tuyệt đối, chọn zone có chủ đích.

### 4.3. `String.format`, `Formatter` và `printf`

Các API này đặc biệt dễ vô tình sử dụng mặc định JVM:

~~~java
double result = 1234.5;

String usText = String.format(Locale.US, "%,.2f", result);
String deText = String.format(Locale.GERMANY, "%,.2f", result);

System.out.printf(Locale.US, "US: %,.2f%n", result);
System.out.printf(Locale.GERMANY, "DE: %,.2f%n", result);
~~~

Đặt trong method, import `java.util.Locale`. `%,.2f` yêu cầu phân nhóm và hai chữ số thập phân; dấu cụ thể theo locale. `printf(locale, ...)` cũng nhận locale tường minh; phiên bản không có locale có thể dùng mặc định `FORMAT`.

Đừng nhầm `Locale` của bộ định dạng với encoding của đầu ra. `Locale` chọn quy ước số/ngày/từ ngữ; encoding của console, stream và file quyết định cách ký tự được mã hóa. Nếu Unicode bị lỗi khi ghi file, kiểm tra `Charset` độc lập với `Locale`.

### 4.4. Thông điệp có nhiều tham số bằng `MessageFormat`

Nếu một câu hiển thị bao gồm số hoặc ngày, `MessageFormat` có thể dùng locale để định dạng các tham số:

~~~java
Locale locale = Locale.GERMANY;
MessageFormat message = new MessageFormat(
        "Gesamt: {0,number,#,##0.00}",
        locale
);
String text = message.format(new Object[]{1234.5});
~~~

Đây là đoạn mã minh họa với import `java.text.MessageFormat` và `java.util.Locale`; định dạng số dùng locale Đức. `MessageFormat` có quy tắc quoting đặc biệt với dấu nháy đơn trong pattern. Với ứng dụng dịch đa ngôn ngữ, nên lấy cả mẫu câu theo locale và dùng formatter phù hợp cho tham số; không giả định cùng một câu có thể dịch an toàn chỉ bằng thay từng từ.

`MessageFormat` có thể thay đổi trạng thái, nên tạo instance theo ngữ cảnh hoặc dùng chiến lược chia sẻ an toàn khi xử lý đồng thời. Một pattern `{0,number}` được format với locale khác có thể cho kết quả khác dù các đối số không đổi.

## 5. Truyền locale rõ ràng khi phân tích dữ liệu đầu vào

Định dạng (**formatting**) là từ số/ngày thành chuỗi; phân tích (**parsing**) là đi theo chiều ngược lại. Khi người dùng nhập `1.234,50`, phải biết locale của biểu mẫu để hiểu chính xác dấu nhóm và dấu thập phân.

Ví dụ đầy đủ dùng một số kiểu Đức và kiểm tra **đã tiêu thụ toàn bộ chuỗi**. Lưu vào `ParseLocaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseLocaleDemo {
    public static void main(String[] args) {
        Locale locale = Locale.GERMANY;
        String input = "1.234,50";

        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale)
        );
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);

        if (parsed == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid localized number: " + input);
        }

        BigDecimal amount = (BigDecimal) parsed;
        System.out.println(amount.toPlainString());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ParseLocaleDemo.java
java ParseLocaleDemo
~~~

Kết quả:

~~~text
1234.50
~~~

Vì sao không chỉ dùng `NumberFormat.parse(input)` rồi tin ngay kết quả? Một số parser có thể **chấp nhận tiền tố hợp lệ** và không tiêu thụ hết chuỗi. Kiểm tra `ParsePosition.getIndex() == input.length()` giúp phát hiện ký tự thừa; tuy nhiên parser bản địa hóa có thể vẫn dung thứ các dấu nhóm đặt không đúng vị trí. Nếu cần xác thực nghiêm ngặt biểu mẫu tài chính, thiết kế thêm quy tắc validation, kiểm tra phạm vi và dấu phân cách được chấp nhận, rồi mới dùng giá trị đã parse.

`DecimalFormat` trong ví dụ được tạo mới và cấu hình để nhận `BigDecimal`. Không chia sẻ cùng instance mutable cho các request đồng thời. Đối với input giao tiếp giữa các dịch vụ hoặc lưu trữ máy, ưu tiên định dạng có quy ước cố định được tài liệu hóa (`ISO-8601`, JSON number, hoặc định dạng giao thức đã quy định), **không** dùng giao diện người dùng như giao thức truyền dữ liệu.

### Ngày tháng cũng phải parse bằng locale thích hợp

Nếu nhập tên tháng theo ngôn ngữ người dùng, cấu hình `DateTimeFormatter` có locale trước khi parse:

~~~java
Locale locale = Locale.US;
DateTimeFormatter parser =
        DateTimeFormatter.ofPattern("d MMMM uuuu", locale);
LocalDate date = LocalDate.parse("14 July 2025", parser);
~~~

Đoạn minh họa cần import `java.util.Locale`, `java.time.LocalDate` và `java.time.format.DateTimeFormatter`. Nếu dùng pattern và locale Đức tương ứng, tên tháng cần khớp quy ước ngôn ngữ Đức. Với dữ liệu nội bộ, ISO-8601 như `2025-07-14` thường dễ trao đổi hơn.

## 6. Chọn locale ở đúng lớp và truyền qua lời gọi

Trong một ứng dụng server, locale có thể đến từ lựa chọn người dùng, hồ sơ, yêu cầu HTTP hoặc chính sách nội dung. Sau khi xác định, chuyển locale đó vào các lời gọi định dạng cụ thể:

~~~text
Yêu cầu người dùng / hồ sơ
              |
              v
      Xác định Locale
              |
       +------+------+
       |      |      |
       v      v      v
     Số     Ngày    Thông điệp
 NumberFormat      MessageFormat
          DateTimeFormatter
       |      |      |
       +------+------+
              |
              v
       Chuỗi hiển thị
~~~

Trong service, một cách thiết kế đơn giản là truyền tham số `Locale` tường minh:

~~~java
public static String formatAmount(
        BigDecimal amount,
        Locale locale
) {
    NumberFormat formatter =
            NumberFormat.getNumberInstance(locale);
    formatter.setMinimumFractionDigits(2);
    formatter.setMaximumFractionDigits(2);
    return formatter.format(amount);
}
~~~

Đây là **phương thức minh họa**, chưa phải chương trình đầy đủ; import `java.math.BigDecimal`, `java.text.NumberFormat` và `java.util.Locale`. Instance formatter được tạo riêng cho lời gọi nên tránh việc nhiều luồng thay đổi cùng một formatter. Trong trường hợp xử lý khối lượng lớn, có thể tối ưu bằng cơ chế tạo/copy formatter hoặc cache cấu hình phù hợp, nhưng không chia sẻ mutable formatter một cách vô điều kiện.

**Lưu ý chính sách locale thiếu hoặc sai:** nếu locale chưa được cung cấp, ứng dụng nên có chính sách fallback tường minh; ví dụ lấy locale từ hồ sơ, sau đó ngôn ngữ yêu cầu, sau đó locale mặc định của sản phẩm. Không âm thầm sử dụng `Locale.getDefault()` ở mọi bước. Đầu vào từ người dùng phải được kiểm tra thẻ BCP 47 và các locale mà sản phẩm hỗ trợ; một thẻ hợp cú pháp chưa chắc có đủ bản dịch hoặc dữ liệu định dạng theo ý người dùng.

### Tách locale hiển thị khỏi các quyết định nghiệp vụ

| Khía cạnh | Biến/đối tượng thường cần truyền | Vì sao độc lập |
| --- | --- | --- |
| Ngôn ngữ, dấu số, tên tháng | `Locale` | Quy ước của người nhận thông tin |
| Múi giờ | `ZoneId` | Xác định giờ địa phương cho một thời điểm |
| Loại tiền | `Currency` hoặc mã ISO 4217 | Giao dịch USD vẫn là USD dù người xem ở Đức |
| Hệ lịch đặc biệt | `Chronology` / Unicode locale extension khi API hỗ trợ | Có thể khác cách biểu diễn ISO mặc định |
| Giá trị tiền | `BigDecimal` cùng quy tắc làm tròn | Đảm bảo tính toán trước khi trình bày |
| Ngôn ngữ của bản dịch | `ResourceBundle` hoặc hệ thống i18n | Dịch nội dung và định dạng số/ngày là hai phần của localization |

Locale có thể có Unicode extension như `th-TH-u-nu-thai`. Hãy giữ đầy đủ thẻ khi đây là sở thích có ý nghĩa và xác nhận API định dạng thực sự hỗ trợ; chỉ tạo `Locale` không bảo đảm mọi formatter tôn trọng mọi extension.

## 7. Kiểm thử và phòng lỗi

### Các kịch bản quan trọng

1. **Cùng giá trị, hai locale:** dùng một `BigDecimal` và một `LocalDate` cố định với `Locale.US` và `Locale.GERMANY`; bảo đảm mỗi lời gọi tạo đầu ra phù hợp, không phụ thuộc vào thứ tự gọi.
2. **Locale mặc định của JVM khác người xem:** chạy test dưới locale mặc định khác và tiếp tục truyền locale tường minh; xác nhận kết quả vẫn phù hợp locale được truyền.
3. **Định dạng và parse hai chiều:** dữ liệu người dùng Đức nhập theo định dạng Đức phải được parse bằng quy ước Đức và trả về giá trị kỳ vọng. Test cả ký tự thừa, chuỗi rỗng, giá trị ngoài phạm vi.
4. **Xử lý đồng thời:** nhiều request có locale khác nhau không được thao tác `Locale.setDefault` của JVM. Formatter mutable phải có phạm vi sống hoặc đồng bộ hợp lý.
5. **Thời gian và tiền:** test timezone và `Currency` riêng; cùng locale không bảo đảm cùng cách hiển thị giờ hoặc cùng đồng tiền.
6. **Unicode và dữ liệu CLDR:** nếu so khớp chuỗi kết quả chính xác, kiểm thử trên JDK/provider production; các dấu cách, ký tự số và tên tháng có thể thay đổi theo dữ liệu locale.
7. **Fallback:** thử locale được hỗ trợ, không được hỗ trợ và không khai báo; bảo đảm quy tắc lựa chọn được áp dụng nhất quán.

### Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách làm đúng |
| --- | --- |
| “Ứng dụng chỉ có một locale mặc định nên mọi request dùng chung cũng được.” | Request có thể đại diện người dùng khác nhau; truyền locale từ ngữ cảnh của request đến từng formatter. |
| “Đổi `Locale.setDefault` tạm thời rồi đổi lại là an toàn.” | Đây là trạng thái toàn cục, có nguy cơ race giữa các luồng. Không dùng như cơ chế chọn locale cho request. |
| “Truyền `Locale` sẽ tự đổi timezone.” | Timezone là `ZoneId`/`TimeZone` riêng. |
| “Truyền `Locale` cho formatter tiền sẽ đổi giá trị hoặc đơn vị tiền.” | Formatter chỉ trình bày; cần `Currency`/đồng tiền nghiệp vụ và chuyển đổi tiền tệ độc lập nếu có. |
| “`String.format` luôn hiển thị dấu chấm thập phân.” | Bản không truyền locale có thể theo mặc định FORMAT; bản truyền `Locale.GERMANY` có thể dùng dấu phẩy. |
| “`NumberFormat` dùng chung nhiều luồng giống `DateTimeFormatter`.” | `NumberFormat` mutable và nhìn chung không an toàn để chia sẻ tự do giữa nhiều luồng; `DateTimeFormatter` bất biến. |
| “Chuỗi `1.234,50` là số có thể parse thống nhất ở mọi locale.” | Dấu phân cách phụ thuộc locale; xác định nguồn và parse theo đúng locale rồi validate. |
| “Đầu ra UI có thể ghi trực tiếp thành dữ liệu JSON/CSV cho máy.” | Dữ liệu giao tiếp máy cần quy ước chuẩn và nhất quán, tách khỏi định dạng địa phương dành cho người đọc. |

## 8. Bài tập củng cố

1. Viết một chương trình in `1234.5` theo `Locale.US`, `Locale.GERMANY`, `Locale.FRANCE` bằng `NumberFormat.getNumberInstance(locale)`. Quan sát dấu nhóm và thập phân, ghi nhận JDK/provider đã dùng.
2. Dùng một `LocalDate` cố định để tạo hai formatter `ofPattern("d MMMM uuuu", locale)` cho tiếng Anh và tiếng Đức. Vì sao không cần gọi `Locale.setDefault`?
3. Một máy chủ ở Việt Nam trả hóa đơn USD cho người dùng Đức. Nêu các thông tin phải xử lý độc lập: locale, currency, amount và timezone nếu trên hóa đơn có thời điểm giao dịch.
4. Một biểu mẫu nhận `1.234,50abc`. Thử parse với `DecimalFormat` và `ParsePosition`; vì sao phải kiểm tra vị trí kết thúc thay vì chỉ kiểm tra `parsed != null`?
5. Nếu hệ thống dùng một `DecimalFormat` chung cho tất cả request và thay `DecimalFormatSymbols` trước mỗi lần gọi, vấn đề gì có thể xảy ra khi nhiều request chạy đồng thời?
6. Thiết kế hàm `formatReport(BigDecimal amount, LocalDate date, Locale locale)` sao cho kết quả không phụ thuộc locale mặc định của JVM.

**Ghi nhớ:** **Hãy xác định locale của người nhận và truyền nó tại từng điểm định dạng hoặc phân tích đầu vào.** `Locale.getDefault()` phù hợp làm chính sách mặc định được kiểm soát ở một số ngữ cảnh, nhưng không nên để lựa chọn ngầm này chi phối mọi thao tác của ứng dụng nhiều người dùng. Truyền locale tường minh giúp hành vi rõ ràng, dễ kiểm thử và không phải thay trạng thái toàn cục của JVM.