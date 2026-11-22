# Tổ chức dịch vụ lấy thông điệp và định dạng trong ứng dụng Java

Một ứng dụng Java đa ngôn ngữ cần giải quyết hai bài toán liên quan nhưng khác nhau: **lấy câu thông điệp theo ngôn ngữ** và **định dạng giá trị theo quy ước địa phương**. Ví dụ một màn hình đơn hàng cần hiển thị câu tiếng Việt hoặc tiếng Anh, nhưng giá tiền phải giữ đúng Currency của giao dịch, ngày hẹn phải được hiển thị theo vùng giờ người nhận, và dấu thập phân phải tuân thủ lựa chọn định dạng của người xem.

Nếu controller nào cũng tự tìm **ResourceBundle**, nối câu bằng dấu cộng, rồi trực tiếp dùng **NumberFormat**, **SimpleDateFormat** hoặc **DateTimeFormatter**, ứng dụng dễ lặp mã, thiếu key, trộn ngôn ngữ, sai ngày giờ và không an toàn khi chia sẻ formatter mutable giữa các request. Cách thiết kế bền vững là tách **LocaleResolver**, **MessageService**, **FormattingService** và một **Presenter/Composer** để phối hợp kết quả.

Bài học này trình bày các trách nhiệm, API Java 17+, cấu trúc file bản dịch, hợp đồng interface, ví dụ chạy được, fallback, cache, thread safety, kiểm thử và lỗi thường gặp khi xây dựng kiến trúc localization.

## 1. Dịch thông điệp và định dạng khác nhau thế nào?

Giả sử một đơn hàng có:

- **Tên khách:** Lan.
- **Mã đơn hàng:** DH-2026-07.
- **Amount:** BigDecimal("1234.50").
- **Currency:** EUR.
- **Thời điểm đặt hàng:** Instant.parse("2026-10-28T02:30:00Z").
- **Ngôn ngữ UI:** vi-VN.
- **Locale định dạng:** vi-VN.
- **ZoneId:** Asia/Ho_Chi_Minh.

Ứng dụng có thể cần tạo một câu gần với: “Chào Lan, đơn DH-2026-07 có tổng ... vào ngày ...”.

| Thành phần | Quyết định | API liên quan |
| --- | --- | --- |
| **Ngôn ngữ câu** | Chào, Hello, vị trí từ và dấu câu | ResourceBundle, MessageFormat |
| **Số tiền** | Dấu nhóm, dấu thập phân, ký hiệu và vị trí tiền | NumberFormat, Currency |
| **Ngày** | Ngày/tháng/năm theo ngôn ngữ và vùng | DateTimeFormatter, Locale |
| **Múi giờ** | Ngày địa phương mà một Instant rơi vào | Instant, ZoneId |
| **Chính sách của sản phẩm** | Locale UI hỗ trợ, fallback, số chữ số tiền | LocaleResolver, cấu hình và domain |

**Nguyên tắc:** lưu dữ liệu nghiệp vụ ở dạng có kiểu; chỉ format tại ranh giới đưa dữ liệu tới người xem. Chuỗi “1.234,50 €” là biểu diễn, không thay thế BigDecimal và Currency.

### 1.1. Tách uiLocale và formatLocale

Ngôn ngữ giao diện và vùng định dạng có thể khác nhau. Một người thích giao diện tiếng Anh nhưng muốn xem ngày/số theo quy ước Việt Nam. Vì vậy nên đặt tên rõ **uiLocale** và **formatLocale** thay vì nhét mọi sở thích vào một biến locale duy nhất.

Tương tự, **ZoneId** không được suy từ Locale. Người dùng chọn tiếng Việt có thể đang sống ở Berlin; số tiền được thanh toán bằng EUR không tự chuyển sang VND khi hiển thị vi-VN.

## 2. Kiến trúc tổng quan

~~~text
Controller / API / Notification use case
                 |
                 v
            LocaleResolver
          /       |       \
         v        v        v
    uiLocale  formatLocale  ZoneId
         |        |
         v        v
 MessageService  FormattingService
         |        |
         v        v
  ResourceBundle  NumberFormat
   MessageFormat  DateTimeFormatter
          \       /
           \     /
            v   v
       Presenter/Composer
              |
              v
       UI / Email / PDF
~~~

Các trách nhiệm nên được tách như sau:

1. **LocaleResolver:** chọn ngôn ngữ UI được ứng dụng công bố hỗ trợ và quy tắc fallback.
2. **MessageService:** lấy mẫu văn bản theo key/locale và điền các tham số.
3. **FormattingService:** định dạng số, tiền, phần trăm, ngày và thời gian theo dữ liệu có kiểu.
4. **Presenter/Composer:** phối hợp chuỗi giá trị đã định dạng với mẫu câu đã dịch, không thực hiện nghiệp vụ.
5. **Domain:** giữ BigDecimal, Currency, LocalDate, Instant, mã đơn hàng, trạng thái và các phép tính.
6. **Observability và test:** phát hiện thiếu key, fallback bất thường, sai mẫu, khác biệt do JDK/CLDR.

Không nhất thiết phải có một framework lớn. Một ứng dụng nhỏ có thể dùng vài class, nhưng **ranh giới trách nhiệm phải rõ** để tránh mỗi màn hình tự phát minh cách quốc tế hóa.

## 3. Thiết kế MessageService

Hợp đồng cơ bản:

~~~java
interface MessageService {
    String render(
            Locale locale, String key, Object... values);
}
~~~

Đây là chữ ký minh họa cần import java.util.Locale khi đặt vào file Java. **Locale** luôn được truyền tường minh, **key** là tên kỹ thuật ổn định, còn **values** là các giá trị cần chèn vào mẫu câu.

Các key tốt:

~~~text
order.title
order.summary
order.status.pending
validation.date.invalid
payment.refund.confirmed
~~~

Chúng mô tả **ý nghĩa nội dung** thay vì dùng nguyên câu tiếng Anh làm khóa. Nhờ vậy người dịch có thể thay chữ mà Java không cần thay key.

Không cho người dùng nhập key tùy ý để đọc tài nguyên nội bộ. Key thường do code ứng dụng chọn từ use case; nếu phải chấp nhận key từ API, cần một danh sách cho phép và phân quyền tương ứng.

### 3.1. Để người dịch đổi trật tự câu

Một câu tiếng Anh và một câu tiếng Việt không cần cùng thứ tự từ. Tham số có đánh số cho phép:

~~~text
English: Hello {0}, order {1} totals {2} on {3}.
Vietnamese: Chào {0}, đơn {1} có tổng {2} vào ngày {3}.
~~~

Người dịch có thể đặt lại thứ tự **{0}, {1}, {2}, {3}** nếu ngôn ngữ đòi hỏi. Ngược lại, nối cố định **prefix + name + amount + suffix** dễ tạo câu vụng, sai giới từ hoặc sai dấu câu.

**Mẫu thông điệp không nên chứa dữ liệu người dùng hay số tiền cố định.** Dữ liệu phải đi qua arguments, không được ghi cứng vào tệp dịch.

## 4. ResourceBundle và cấu trúc bản dịch

ResourceBundle tìm tài nguyên dựa trên **base name** và Locale. Dự án có thể bố trí:

~~~text
src/main/java/LocalizedServicesDemo.java
src/main/resources/messages_en.properties
src/main/resources/messages_vi.properties
~~~

Với ví dụ chạy trực tiếp bằng javac/java, đặt các tệp properties bên cạnh file Java/class để classpath mặc định tìm thấy chúng.

**File messages_en.properties**

~~~properties
order.title=Order details
order.summary=Hello {0}, order {1} totals {2} on {3}.
order.status.pending=Payment pending
~~~

**File messages_vi.properties**

~~~properties
order.title=Chi tiết đơn hàng
order.summary=Chào {0}, đơn {1} có tổng {2} vào ngày {3}.
order.status.pending=Đang chờ thanh toán
~~~

Các tệp này do **ứng dụng sở hữu**, không được JDK tự tạo. Java 17 hỗ trợ UTF-8 cho ResourceBundle properties với quy tắc tương thích encoding đã được định nghĩa; hãy lưu và kiểm tra bản dịch bằng UTF-8 để giữ dấu tiếng Việt.

Ví dụ gọi:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);
String heading = bundle.getString("order.title");
~~~

Đoạn minh họa cần import ResourceBundle, Locale và biến locale. Không viết **messages_vi.properties** làm base name; Java tự tìm các ứng viên từ base **messages** theo locale.

### 4.1. Fallback có thể khiến bản dịch bị pha trộn

Nếu request fr-CA nhưng dự án không có bản tiếng Pháp, cơ chế tìm bundle có thể dùng tài nguyên base hoặc default Locale tùy cấu hình. Đó không chứng minh app thực sự hỗ trợ fr-CA.

Nếu bản tiếng Việt thiếu một key và có bản base chứa key đó, ứng dụng có thể hiện một câu bằng ngôn ngữ khác. Vì vậy phải phân biệt:

- **Missing bundle:** không tìm được nguồn tài nguyên phù hợp.
- **Missing key:** có bundle nhưng không có key ở chuỗi kế thừa.
- **Partial translation:** một số key vẫn đang được fallback.
- **Invalid pattern:** key tồn tại nhưng cú pháp MessageFormat sai.
- **Unsupported UI locale:** sản phẩm chưa cam kết dịch ngôn ngữ yêu cầu.

Khi phát triển và chạy CI, nên phát hiện các trường hợp này trước khi phát hành. Khi production cần fallback để giữ giao diện dùng được, phải có chính sách được công bố và ghi metric.

## 5. MessageFormat và placeholders

**java.text.MessageFormat** xử lý các placeholders đánh số:

~~~java
String template =
        "Hello {0}, order {1} totals {2} on {3}.";
MessageFormat format =
        new MessageFormat(template, Locale.US);

String sentence = format.format(new Object[] {
        "Lan", "DH-2026-07",
        "EUR 1,234.50", "October 28, 2026"
});
~~~

Đây là đoạn code trong phương thức, cần import MessageFormat và Locale. Tham số tiền/ngày ở đây đã được định dạng thành String. Cách này giúp thay đổi UI locale và format locale độc lập.

### 5.1. Cú pháp dấu nháy đơn

MessageFormat có cơ chế quote đặc biệt. Muốn in một dấu nháy đơn trong pattern, thường cần viết **hai dấu nháy đơn liên tiếp**. Nếu người dịch vô ý thay đổi chúng, placeholders có thể không được xử lý như mong đợi.

**File MessageFormatQuoteDemo.java**

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatQuoteDemo {
    public static void main(String[] args) {
        MessageFormat fmt = new MessageFormat(
                "User {0}: it''s ready; value {1,number,integer}",
                Locale.US);

        System.out.println(fmt.format(
                new Object[] {"Lan", 42}));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MessageFormatQuoteDemo.java
java MessageFormatQuoteDemo
~~~

Stdout:

~~~text
User Lan: it's ready; value 42
~~~

Dấu ngoặc nhọn cũng có cú pháp đặc biệt. Nếu phải in một dấu **{** hoặc **}** thực sự, hãy quote theo quy tắc MessageFormat và kiểm thử. Đừng dùng một regex đơn giản để đánh giá hoàn chỉnh mọi pattern, vì mẫu có thể chứa dấu quote và định dạng lồng nhau.

### 5.2. Built-in number/date và Java Time

MessageFormat hỗ trợ các format tích hợp như **{0,number}** hoặc **{0,date}** dựa trên các API java.text. Tuy nhiên, các đối tượng **LocalDate**, **LocalTime**, **Instant** thuộc java.time không tự được hiểu như java.util.Date trong mọi trường hợp.

Khi dùng Java 17+, một thiết kế dễ hiểu là:

1. FormattingService định dạng LocalDate bằng DateTimeFormatter.
2. FormattingService định dạng BigDecimal/Currency bằng NumberFormat.
3. MessageService nhận các chuỗi đã định dạng và chèn theo cú pháp thông điệp.

Nếu hệ thống cần các tham số có kiểu và định dạng lồng trực tiếp trong message, phải có một adapter rõ hoặc thư viện i18n tương ứng. **Không coi MessageFormat Java Core là bộ pluralization/gender của CLDR đầy đủ**.

## 6. FormattingService: số, tiền và ngày giờ

Hợp đồng:

~~~java
interface FormattingService {
    String money(
            BigDecimal amount, Currency currency, Locale locale);
    String date(
            LocalDate date, Locale locale);
}
~~~

Đây là chữ ký minh họa, cần import BigDecimal, Currency, Locale, LocalDate.

**money** phải nhận **Currency** từ giao dịch, không suy USD từ Locale.US hay VND từ vi-VN. **date** nên nhận LocalDate cho ngày thuần. Một phương thức riêng cho Instant cần thêm ZoneId vì cùng thời điểm có thể là ngày khác nhau ở hai vùng giờ.

Số tiền là dữ liệu có kiểu, không phải chuỗi dịch:

~~~java
record Money(BigDecimal amount, Currency currency) {}
~~~

Đây là một record Java 17 hợp lệ khi đặt trong file có imports. Currency chỉ nêu đơn vị tiền; NumberFormat không đổi tỷ giá. Quy tắc rounding/thuế cũng không nên bị giấu trong MessageService.

### 6.1. NumberFormat mutable

**NumberFormat.getCurrencyInstance(locale)** tạo formatter theo locale. Sau đó có thể gọi **setCurrency(currency)** để chọn đơn vị tiền thực tế. Nhưng **NumberFormat là mutable**, nên không chia sẻ một singleton rồi đổi Currency hoặc fraction digits theo từng request thiếu cách ly.

Ngược lại, **DateTimeFormatter** là immutable và thread-safe sau khi cấu hình, nên có thể dùng lại hoặc cache theo locale/format style.

## 7. Ví dụ Java 17+ tích hợp hoàn chỉnh

Ví dụ gồm ba file: **LocalizedServicesDemo.java**, **messages_en.properties**, **messages_vi.properties** đã được khai báo trong mục 4. Đây là chương trình Java Core, không cần framework.

**File LocalizedServicesDemo.java**

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.Set;

public class LocalizedServicesDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private static final Set<Locale> SUPPORTED =
            Set.of(VI, Locale.US);

    record RequestContext(
            Locale uiLocale,
            Locale formatLocale,
            ZoneId zoneId,
            Currency currency) {}

    interface MessageService {
        String render(
                Locale locale, String key, Object... arguments);
    }

    static final class BundleMessageService
            implements MessageService {

        @Override
        public String render(
                Locale locale, String key, Object... arguments) {

            ResourceBundle.Control control =
                    ResourceBundle.Control
                            .getNoFallbackControl(
                                    ResourceBundle.Control
                                            .FORMAT_PROPERTIES);

            ResourceBundle bundle =
                    ResourceBundle.getBundle(
                            "messages", locale, control);

            MessageFormat formatter =
                    new MessageFormat(
                            bundle.getString(key), locale);

            return formatter.format(arguments);
        }
    }

    interface FormattingService {
        String money(
                BigDecimal amount, Currency currency, Locale locale);
        String date(LocalDate day, Locale locale);
    }

    static final class JdkFormattingService
            implements FormattingService {

        @Override
        public String money(
                BigDecimal amount, Currency currency, Locale locale) {

            NumberFormat fmt =
                    NumberFormat.getCurrencyInstance(locale);
            fmt.setCurrency(currency);

            int digits = currency.getDefaultFractionDigits();
            if (digits >= 0) {
                fmt.setMinimumFractionDigits(digits);
                fmt.setMaximumFractionDigits(digits);
            }

            return fmt.format(amount);
        }

        @Override
        public String date(LocalDate day, Locale locale) {
            DateTimeFormatter fmt =
                    DateTimeFormatter
                            .ofLocalizedDate(FormatStyle.LONG)
                            .withLocale(locale);
            return fmt.format(day);
        }
    }

    private static Locale chooseUiLocale(Locale requested) {
        if (SUPPORTED.contains(requested)) {
            return requested;
        }
        if ("vi".equals(requested.getLanguage())) {
            return VI;
        }
        return Locale.US;
    }

    public static void main(String[] args) {
        Locale ui = chooseUiLocale(
                Locale.forLanguageTag("vi-VN"));

        RequestContext context = new RequestContext(
                ui,
                ui,
                ZoneId.of("Asia/Ho_Chi_Minh"),
                Currency.getInstance("EUR"));

        MessageService messages =
                new BundleMessageService();
        FormattingService formats =
                new JdkFormattingService();

        BigDecimal amount = new BigDecimal("1234.50");
        Instant created =
                Instant.parse("2026-10-28T02:30:00Z");

        LocalDate localDate =
                created.atZone(context.zoneId()).toLocalDate();

        String amountText = formats.money(
                amount, context.currency(),
                context.formatLocale());

        String dateText = formats.date(
                localDate, context.formatLocale());

        System.out.println(messages.render(
                context.uiLocale(), "order.title"));

        System.out.println(messages.render(
                context.uiLocale(),
                "order.summary",
                "Lan",
                "DH-2026-07",
                amountText,
                dateText));
    }
}
~~~

Trong thư mục chứa các tệp, biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocalizedServicesDemo.java
java LocalizedServicesDemo
~~~

Dòng đầu của stdout chính xác vì lấy trực tiếp từ messages_vi.properties:

~~~text
Chi tiết đơn hàng
~~~

Dòng thứ hai chứa thông điệp tiếng Việt có **Lan**, mã **DH-2026-07**, amount EUR và ngày địa phương 28/10/2026 được formatter hiển thị theo vi-VN. Không ấn định toàn bộ stdout dòng thứ hai cho mọi JDK 17+ vì dữ liệu CLDR/provider có thể khác ở cách viết ngày, dấu nhóm, ký hiệu tiền và dấu cách Unicode.

### 7.1. Điểm đúng của cấu trúc ví dụ

- **SUPPORTED** là tập locale sản phẩm công bố, không lấy nguyên Locale.getAvailableLocales.
- **RequestContext** là record immutable giữ uiLocale, formatLocale, ZoneId và Currency.
- **BundleMessageService** xử lý tài nguyên và MessageFormat.
- **JdkFormattingService** chỉ định dạng dữ liệu có kiểu.
- **chooseUiLocale** minh họa fallback ứng dụng, không thay Locale.default JVM.
- **NumberFormat** được tạo mới mỗi lần gọi, tránh rò rỉ cấu hình giữa các request.
- **DateTimeFormatter** được tạo với locale tường minh.
- **Instant** được chuyển theo ZoneId trước khi lấy LocalDate.
- Chuỗi giá trị đã format được đưa vào message qua placeholders.
- ResourceBundle.Control chỉ định phương thức không fallback qua locale mặc định JVM cho lần tra cứu.

### 7.2. Hiểu đúng getNoFallbackControl

**ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)** ngăn bước **fallback đến locale mặc định JVM** trong quá trình tìm tài nguyên. Nó **không cấm** mọi dạng ứng viên ngôn ngữ cha hoặc **root bundle**. Nếu request vi-VN mà chỉ có messages_vi.properties, tài nguyên ngôn ngữ vi vẫn được tìm thấy.

Để bắt buộc bản dịch đúng từng vùng hoặc phát hiện key chưa dịch, cần thêm kiểm tra coverage riêng; không nhầm “no fallback” với “không sử dụng candidate locale nào khác”. Ngoài ra, cơ chế ResourceBundle.Control tùy loại module/runtime; ví dụ này dành cho ứng dụng Java 17 chạy trên classpath.

## 8. Tầng Presenter/Composer nên phối hợp ra sao?

Một presenter dùng MessageService và FormattingService:

~~~text
Order domain:
    amount=1234.50, currency=EUR, createdAt=Instant

LocaleResolver:
    uiLocale=vi-VN, formatLocale=vi-VN, zone=Asia/Ho_Chi_Minh

FormattingService:
    money(...) -> văn bản tiền theo vi-VN
    date(...)  -> văn bản ngày theo vi-VN

MessageService:
    order.summary + 4 arguments -> câu hoàn chỉnh

UI:
    Render câu theo font, direction và escaping của kênh.
~~~

Presenter không nên tự đổi Currency, tính thuế, quyết định tỷ giá hoặc ghi lại message đã dịch như nguồn dữ liệu chính. Nếu cần phát hành email, người nhận email có thể có Locale khác người đang thao tác hệ thống; composer nên nhận **context của người nhận**.

Đối với API máy, thường tốt hơn trả JSON có amount, currency, Instant và message key/status riêng, thay vì chỉ trả một câu đã bản địa hóa mà client phải parse ngược.

## 9. Lựa chọn locale và supportedLocales

**Locale.getAvailableLocales()** là danh sách do JDK công bố, **không chứng minh ứng dụng có bản dịch**. Một ứng dụng có thể chỉ hỗ trợ vi-VN và en-US dù JVM có dữ liệu định dạng cho nhiều locale hơn.

Nguồn quyết định uiLocale có thể là:

- Cài đặt trong hồ sơ người dùng.
- Cấu hình tổ chức.
- Ưu tiên ngôn ngữ của client.
- Fallback mặc định do sản phẩm định nghĩa.

Không dùng Locale.setDefault theo request: đây là trạng thái toàn JVM, có thể ảnh hưởng luồng khác.

### 9.1. Locale.LanguageRange và Locale.lookup

Nếu ứng dụng chấp nhận header kiểu:

~~~text
vi-VN, en-US;q=0.8
~~~

Java hỗ trợ thương lượng dựa trên danh sách ứng dụng:

**File LocaleSelectionDemo.java**

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleSelectionDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.US);

        List<Locale.LanguageRange> preferred =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8");

        Locale chosen =
                Locale.lookup(preferred, supported);

        if (chosen == null) {
            chosen = Locale.US;
        }

        System.out.println(chosen.toLanguageTag());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocaleSelectionDemo.java
java LocaleSelectionDemo
~~~

Stdout chính xác:

~~~text
vi-VN
~~~

**Locale.lookup** có thể trả null, nên phải có fallback. Header không tin cậy cần giới hạn kích thước và bắt lỗi parse. Locale được chọn là thành viên danh sách **supported**; không mở rộng sang mọi locale JDK chỉ vì chúng xuất hiện trong mảng getAvailableLocales.

### 9.2. Các loại Locale khác nhau trong một request

| Thuộc tính | Mục đích |
| --- | --- |
| requestedLocale | Người dùng/client yêu cầu |
| uiLocale | Ngôn ngữ bản dịch mà sản phẩm có |
| formatLocale | Quy tắc số/ngày dùng hiển thị |
| zoneId | Múi giờ của thời điểm/người xem |
| currency | Đơn vị tiền nghiệp vụ |
| userId / tenantId | Xác định ngữ cảnh, quyền và cấu hình |

Không nên cố định Locale.US nếu người dùng yêu cầu vi-VN và bản dịch đã có. Ngược lại, nếu formatLocale không được kiểm thử, sản phẩm phải quyết định fallback rõ ràng, không lặng lẽ trộn nhiều quy tắc ngoài dự đoán.

## 10. Fallback và missing key là vấn đề vận hành

Có thể xảy ra:

1. **Locale chưa hỗ trợ:** dùng fallback được phê duyệt.
2. **Bundle thiếu:** ResourceBundle ném MissingResourceException khi không tìm được candidate phù hợp.
3. **Key thiếu:** getString có thể ném MissingResourceException.
4. **Key chỉ tồn tại ở root bundle:** chuỗi của ngôn ngữ mặc định bị trộn vào màn hình ngôn ngữ khác.
5. **Pattern lỗi:** MessageFormat có thể ném IllegalArgumentException.
6. **Placeholder thiếu:** câu có thể còn literal hoặc được format không như người dịch mong đợi.
7. **Bản dịch sai ngữ cảnh:** tồn tại key nhưng nội dung không hợp màn hình.

**Trong CI**, kiểm tra key của mọi bundle và render các mẫu quan trọng. **Trong production**, nếu fallback để giữ UI hoạt động, nên log key/locale và tăng metric theo chính sách, tránh trả trực tiếp stack trace hoặc chuỗi bí mật.

Không catch Exception chung rồi trả key như một “thành công”; điều này có thể che lỗi code hoặc lỗi pattern. Chọn fallback message là một chính sách rõ ràng, không phải biến mọi lỗi thành nội dung người dùng.

## 11. Kiểm tra placeholders giữa các bản dịch

Khi một key có bốn tham số, người dịch có thể đổi thứ tự nhưng phải giữ đủ ý nghĩa. Ví dụ:

~~~text
order.summary: {0}=name, {1}=orderId,
               {2}=formattedMoney, {3}=formattedDate
~~~

QA nên phát hiện:

- Key thiếu.
- Mẫu rỗng.
- Chỉ số không được cung cấp như **{9}**.
- Dấu nháy đơn chưa escape.
- Sai cú pháp dấu ngoặc nhọn.
- Dùng loại formatter không tương thích giá trị.
- Bản dịch gắn cứng currency hoặc ngày.
- Nút và nhãn thiếu văn bản trợ năng.

Không dùng một regex cực đơn giản như **\{[0-9]+\}** để khẳng định mọi mẫu MessageFormat hợp lệ. MessageFormat có cú pháp quote và các định dạng phụ; cần parse/test thực sự cho tài nguyên quan trọng.

### 11.1. Pluralization và biến cách

Một số ngôn ngữ có quy tắc số ít/số nhiều hoặc hình thức từ dựa theo giới tính và ngữ cảnh phức tạp. MessageFormat Java Core có tùy chọn choice, nhưng **không phải giải pháp đầy đủ cho plural rules/gender rules của mọi locale CLDR**. Sản phẩm quốc tế lớn có thể cần thư viện i18n chuyên dụng cùng quy tắc biên dịch/kiểm tra tài nguyên.

Không tự ghép chữ **s** cho tiếng Anh rồi dùng hàm đó làm cơ chế đa ngôn ngữ. Không xây câu “{0} items” cố định khi bản dịch cần thay đổi hình thái từ theo số lượng.

## 12. Caching và thread safety

| Thành phần | Đặc tính | Khuyến nghị |
| --- | --- | --- |
| ResourceBundle | JDK có cơ chế cache bundle | Dùng cache mặc định, thiết kế reload nếu có hot update |
| MessageFormat | Mutable | Tạo mới hoặc clone/cách ly rõ |
| NumberFormat | Mutable | Tạo mới mỗi thao tác/request hoặc đồng bộ chính xác |
| DateTimeFormatter | Immutable và thread-safe | Có thể cache theo locale/pattern |
| Chuỗi message đã chèn arguments | Chứa dữ liệu người dùng | Không cache chung theo key đơn lẻ |
| Localizer context | Phụ thuộc người nhận | Dùng object immutable hoặc request scope |

**Anti-pattern:**

~~~java
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance();

void changeCurrency(Currency currency) {
    SHARED.setCurrency(currency);
}
~~~

Đây là ví dụ minh họa lỗi, không phải chương trình độc lập. Nếu hai request có currency/locale khác nhau cùng dùng SHARED, formatter mutable có thể tạo output lẫn cấu hình. Tương tự không chia sẻ một MessageFormat rồi gọi setFormat/format đồng thời thiếu bảo vệ.

**Cache key phải đủ thông tin.** Nếu lưu chuỗi đã format chỉ theo amount mà bỏ Currency/formatLocale, kết quả có thể sai. Nếu cache thông điệp đã chèn tên khách chỉ theo message key, có thể vô tình trả dữ liệu của người dùng khác.

ResourceBundle có cache nhưng khi muốn cập nhật bản dịch nóng, cần chính sách reload/versioning phù hợp; không gọi ResourceBundle.clearCache toàn bộ JVM tùy tiện mà không đánh giá ảnh hưởng.

## 13. Ngày thuần, Instant và ZoneId

Một ngày **LocalDate** không có timezone. Một **Instant** là một thời điểm tuyệt đối. Để hiển thị ngày của Instant trong một vùng, phải chuyển:

~~~java
Instant moment =
        Instant.parse("2026-10-28T02:30:00Z");

LocalDate inVietnam =
        moment.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDate();
~~~

Đoạn minh họa cần imports Instant, LocalDate, ZoneId. Đây là bước riêng so với chọn ngôn ngữ của tên tháng.

**Locale không phải ZoneId.** UI tiếng Việt có thể được xem từ Mỹ hoặc châu Âu. FormattingService cho một moment nên nhận cả Instant, ZoneId và Locale, hoặc nhận một ZonedDateTime đã được chuyển vùng.

### 13.1. Hướng thiết kế phương thức

~~~java
String formatDate(LocalDate date, Locale locale);

String formatMoment(
        Instant instant, ZoneId zone, Locale locale);
~~~

Đây là các chữ ký minh họa, không phải chương trình đầy đủ. Khi định dạng theo locale, DateTimeFormatter.ofLocalizedDate/DateTime thường thuận tiện hơn hardcode **dd/MM/yyyy** cho tất cả vùng. Với dữ liệu API/máy, ISO formatter phù hợp hơn chuỗi địa phương hóa không có hợp đồng parse rõ.

## 14. Lưu trữ dữ liệu và phát thông báo qua nhiều kênh

Một sự kiện “đơn hàng đã tạo” có thể cần web UI, email, push và PDF. Mỗi nơi nhận có thể dùng locale, timezone và quy định trình bày khác nhau.

**Mẫu nên giữ lại:**

~~~text
Event type: ORDER_CREATED
Order ID: DH-2026-07
Amount: 1234.50
Currency: EUR
OccurredAt: 2026-10-28T02:30:00Z
Recipient: một ID người dùng
~~~

Khi render, hệ thống lấy **ngữ cảnh của người nhận**, chọn ResourceBundle/formatter, rồi tạo nội dung cho kênh. Không lấy locale của người thao tác để gửi email cho người khác nếu họ có sở thích riêng.

Đối với log kỹ thuật, thường nên ghi **event code và dữ liệu cấu trúc** hơn là câu đã dịch: câu dịch có thể thay đổi theo ngôn ngữ, khó tìm kiếm và khác giữa các bản phần mềm.

Nếu hệ thống phải lưu bản hóa đơn đã phát hành để đối chiếu pháp lý, có thể lưu thêm **snapshot tài liệu đã render**; đó là nhu cầu audit rõ ràng, không có nghĩa bỏ dữ liệu gốc có kiểu.

## 15. Bảo mật và escaping theo kênh đầu ra

MessageFormat chỉ xây câu, **không escape HTML, SQL, URL hoặc shell**. Nếu tham số chứa nội dung người dùng, phải escape hoặc dùng API an toàn của kênh:

- **HTML:** dùng template autoescape hoặc cách chèn text an toàn.
- **SQL:** dùng prepared statements, không nối câu dịch vào truy vấn.
- **URL:** encode đúng thành phần URL.
- **Email HTML:** escape nội dung và kiểm tra bố cục.
- **PDF:** dùng font hỗ trợ ngôn ngữ và layout RTL/LTR nếu cần.
- **Log:** tránh dữ liệu nhạy cảm, cân nhắc ký tự control/Bidi trong tên người.

Bản dịch được quản lý bởi đội dự án có thể là tài nguyên tin cậy, nhưng **arguments không tự trở thành dữ liệu tin cậy** chỉ vì chúng được chèn qua MessageFormat.

Không dùng translated label làm ID nghiệp vụ hoặc quyền hạn. Một nút được dịch từ “Thanh toán” sang “Pay” vẫn phải gọi cùng action ID bất biến, không được xác định hành động từ chữ hiển thị.

## 16. Kiểm thử theo từng thành phần

**LocaleResolver:**

- Trả locale đã hỗ trợ khi người dùng chọn.
- Có fallback rõ cho tag không hỗ trợ.
- Không thay Locale.setDefault theo request.
- Xử lý Unicode extensions, region và các lựa chọn language range theo policy.

**MessageService:**

- Tất cả key bắt buộc có trong các bundle.
- Pattern hợp lệ và placeholders đúng ý nghĩa.
- Dấu nháy và dấu ngoặc nhọn được xử lý đúng.
- Fallback không lấy ngẫu nhiên default Locale.
- Cùng key cho phép người dịch thay đổi trật tự câu.

**FormattingService:**

- Currency thực tế của giao dịch không bị thay.
- Định dạng số/ngày khác nhau theo formatLocale.
- Fraction digits/rounding đúng nghiệp vụ.
- LocalDate không bị biến thành ngày khác do timezone ngầm.
- Instant được đổi ZoneId khi cần.
- Không chia sẻ NumberFormat mutable qua nhiều luồng.

**Presenter/Composer:**

- Chọn key đúng cho use case.
- Truyền các tham số đúng thứ tự và có kiểu rõ.
- Không hardcode từ nối tiếng Anh/Vietnamese trong mã.
- Không đưa chuỗi đã dịch ngược vào tính toán nghiệp vụ.

## 17. Bộ test tích hợp tối thiểu

| Tình huống | Kiểm tra |
| --- | --- |
| uiLocale=vi-VN và formatLocale=vi-VN | Câu Việt và số/ngày địa phương |
| uiLocale=en-US và formatLocale=en-US | Câu Anh và số/ngày Hoa Kỳ |
| uiLocale=en-US và formatLocale=vi-VN | Ngôn ngữ và định dạng độc lập |
| Currency=EUR với locale Việt Nam | Không tự đổi EUR thành VND |
| Instant ở Asia/Ho_Chi_Minh và một ZoneId khác | Ngày địa phương chính xác |
| Bỏ key khỏi một bundle | Lỗi/fallback đúng policy |
| Mẫu có dấu nháy đơn | MessageFormat quote đúng |
| Mẫu có bốn placeholders | Không mất/đổi sai tham số |
| 2 request concurrent khác Currency | Không lẫn cấu hình NumberFormat |
| Phiên bản JDK/CLDR khác | Phát hiện output khác có ý nghĩa |
| Giá tiền có NBSP/NNBSP | Không làm mất Unicode spacing khi render |
| HTML/PDF/email có tiếng Việt/RTL | Font, escaping và direction đúng |
| ResourceBundle chỉ có base bundle | Không quảng bá sai locale hỗ trợ |

**Tách hai kiểu test:** test logic nội bộ với stub formatter để assert cấu trúc message, và test integration với formatter thật trên JDK mục tiêu. Không nên đóng đinh từng code point của output locale khi không kiểm soát dữ liệu CLDR/provider.

## 18. Cạm bẫy phổ biến

### Cạm bẫy 1: Controller nào cũng tự gọi ResourceBundle và NumberFormat

Tạo logic fallback khác nhau, dẫn đến thông điệp pha nhiều ngôn ngữ và ngày giờ không thống nhất. Nên có lớp dịch vụ chung.

### Cạm bẫy 2: Dùng một Locale cho ngôn ngữ, tiền và timezone

Locale không tự biết currency của đơn hàng hoặc zone người dùng. Những giá trị đó cần trường có kiểu riêng.

### Cạm bẫy 3: Ghép câu bằng dấu cộng rồi chỉ dịch prefix/suffix

Thứ tự từ không giống nhau giữa ngôn ngữ; dùng MessageFormat placeholders để người dịch sắp câu.

### Cạm bẫy 4: Không hiểu nháy đơn của MessageFormat

Apostrophe literal cần quote đúng. Đừng dùng string replacement để chữa mẫu dịch sau khi lỗi.

### Cạm bẫy 5: Dùng MessageFormat built-in date trực tiếp với LocalDate

MessageFormat Java Core không tự chuyển mọi kiểu java.time sang java.text.Date. Dùng DateTimeFormatter hoặc adapter có kiểm thử.

### Cạm bẫy 6: Cho rằng getBundle trả kết quả là locale đã được dịch

ResourceBundle có fallback; cần danh sách supportedLocales riêng và kiểm tra coverage.

### Cạm bẫy 7: Dùng NumberFormat singleton rồi sửa setCurrency theo request

Formatter mutable có thể gây race và rò rỉ cấu hình. Tạo mới hoặc cô lập.

### Cạm bẫy 8: Cache output message theo key mà không tính arguments

Có thể trả nội dung chứa tên/mã đơn của người khác. Không cache message đã cá nhân hóa theo key chung.

### Cạm bẫy 9: Cập nhật Locale.setDefault khi user đổi ngôn ngữ

Default JVM ảnh hưởng các request khác. Truyền Locale tường minh.

### Cạm bẫy 10: Coi định dạng là nghiệp vụ tiền tệ

setCurrency không tính tỷ giá; NumberFormat không kiểm chứng phép tính thuế. Giữ domain xử lý tiền riêng.

### Cạm bẫy 11: Hardcode ngày dd/MM/yyyy cho mọi locale

Một số vùng có thứ tự và tên tháng khác. Dùng DateTimeFormatter theo locale hoặc pattern đã được phê duyệt.

### Cạm bẫy 12: Không kiểm thử key và pattern dịch trong CI

Lỗi chỉ xuất hiện khi người dùng chuyển ngôn ngữ hiếm. Kiểm tra bundle coverage và render mẫu trước phát hành.

### Cạm bẫy 13: Dùng message dịch làm event code kỹ thuật

Ngôn ngữ và wording thay đổi; event ID nên ổn định, tách khỏi câu người dùng.

### Cạm bẫy 14: Quên vấn đề HTML/RTL/fonts

ResourceBundle cung cấp văn bản, không đảm bảo hiển thị đúng trên mọi kênh. Text layout và escaping vẫn phải được xử lý riêng.

## 19. Lộ trình triển khai

1. **Mô hình hóa domain:** giữ amount, Currency, Instant, LocalDate và ID dưới dạng có kiểu.
2. **Xác định supportedLocales:** chỉ công bố những bản dịch đã được QA.
3. **Xây LocaleResolver:** quy tắc chọn ngôn ngữ, vùng và fallback.
4. **Tạo ResourceBundle:** các key có ngữ nghĩa, file UTF-8, phân chia theo module khi có ích.
5. **Tạo MessageService:** nhận uiLocale/key/args, quản lý missing key và MessageFormat.
6. **Tạo FormattingService:** nhận formatLocale cùng dữ liệu có kiểu; dùng API phù hợp.
7. **Tạo Presenter/Composer:** phối hợp dịch vụ mà không tính lại nghiệp vụ.
8. **Bảo đảm thread safety:** cache formatter immutable, tránh sửa NumberFormat/MessageFormat chia sẻ.
9. **Kiểm thử:** unit, integration và snapshot có version cho những nội dung bắt buộc.
10. **Vận hành:** log/metric fallback, missing key, lỗi mẫu, thay đổi do JDK/CLDR.

Không cần tạo quá nhiều abstraction khi dự án nhỏ. Mục tiêu là **có thể kiểm thử và thay thế từng phần** mà không sửa logic hiển thị ở hàng chục controller.

## 20. Câu hỏi tự ôn

1. Vì sao không thể lấy Locale.getAvailableLocales làm menu ngôn ngữ đã được app hỗ trợ?
2. MessageService nên nhận những tham số nào để không dựa vào default JVM?
3. Vì sao FormatterService cần Currency ngay cả khi đã có Locale?
4. DateTimeFormatter khác NumberFormat thế nào về tính mutable và thread safety?
5. Với thông điệp “It's ready”, vì sao MessageFormat cần dấu nháy đơn nhân đôi?
6. Tại sao một ResourceBundle trả kết quả không chứng minh bản dịch được hoàn thiện?
7. Khi hai user có formatLocale khác nhau, dùng NumberFormat singleton có rủi ro gì?
8. Một Instant cần thông tin gì để xác định LocalDate của người nhận?
9. Vì sao không cache câu đã render chỉ theo message key?
10. Nếu thông điệp xuất ở HTML, MessageFormat đã chống XSS chưa?

**Đáp án gợi ý:** (1) JDK có locale rộng hơn bản dịch app; (2) Locale, key, arguments; (3) Currency là dữ liệu nghiệp vụ; (4) DateTimeFormatter immutable, NumberFormat mutable; (5) quote của MessageFormat; (6) fallback; (7) race/lẫn cấu hình; (8) ZoneId; (9) arguments có dữ liệu riêng; (10) chưa, cần escape theo kênh.

## 21. Checklist hoàn thiện

- [ ] Phân biệt thông điệp đã dịch và giá trị đã định dạng.
- [ ] Có LocaleResolver, MessageService, FormattingService và composer với trách nhiệm rõ.
- [ ] Lưu domain bằng BigDecimal/Currency/LocalDate/Instant thay vì chuỗi định dạng.
- [ ] Dùng supportedLocales của sản phẩm, không công bố bừa mọi locale JDK.
- [ ] Truyền Locale tường minh vào MessageFormat/NumberFormat/DateTimeFormatter.
- [ ] Có uiLocale, formatLocale, ZoneId, Currency với ý nghĩa khác nhau.
- [ ] ResourceBundle keys ổn định, bản dịch UTF-8, placeholders nhất quán.
- [ ] Fallback và missing key được phát hiện và quản lý.
- [ ] Dấu nháy đơn và ngoặc nhọn MessageFormat được QA.
- [ ] Không tự nối câu cố định theo ngữ pháp một ngôn ngữ.
- [ ] Không dùng MessageFormat làm toàn bộ pluralization engine.
- [ ] Currency không bị đổi bằng việc đổi Locale.
- [ ] Rounding/fraction digits theo chính sách nghiệp vụ.
- [ ] Không chia sẻ formatter mutable rồi sửa đồng thời.
- [ ] Không cache message chứa dữ liệu người dùng dưới key quá chung.
- [ ] Không gọi Locale.setDefault trong mỗi request.
- [ ] Có kiểm thử thiếu key, sai pattern, concurrency và JDK/CLDR thay đổi.
- [ ] Escaping và hướng chữ được xử lý theo kênh render.
- [ ] Có metric cho fallback không mong muốn và lỗi bản dịch.

## 22. Tổng kết

**Dịch vụ lấy thông điệp** chịu trách nhiệm nội dung câu theo ngôn ngữ; **dịch vụ định dạng** chịu trách nhiệm biểu diễn số, tiền và ngày giờ; **LocaleResolver** xác định ngữ cảnh của người xem, còn **Presenter/Composer** phối hợp chúng thành đầu ra. Java 17 cung cấp **ResourceBundle**, **MessageFormat**, **NumberFormat**, **DateTimeFormatter**, **Locale** và **ZoneId** để triển khai những trách nhiệm ấy một cách rõ ràng.

Một thiết kế tốt không chỉ tránh lặp code mà còn ngăn thay đổi Locale làm đổi dữ liệu tiền, ngăn dùng sai timezone, giảm race của formatter mutable, phát hiện bản dịch thiếu và giúp kiểm thử độc lập. Hãy giữ dữ liệu miền có kiểu, truyền ngữ cảnh tường minh, quản lý fallback theo chính sách ứng dụng và chỉ format tại ranh giới hiển thị.
