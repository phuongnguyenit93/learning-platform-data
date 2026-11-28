# ResourceBundle, Locale và định dạng theo vùng trong Java 27

Ứng dụng phục vụ người dùng ở nhiều quốc gia thường phải thay đổi **ngôn ngữ hiển thị**, **cách viết số**, **tiền tệ**, **ngày giờ** và một số quy tắc xử lý văn bản. Trong Java 27, ba nhóm API quan trọng giúp giải quyết các yêu cầu này là:

- `java.util.Locale`: biểu diễn lựa chọn ngôn ngữ, chữ viết và vùng của người dùng.
- `java.util.ResourceBundle`: truy xuất thông điệp, nhãn và tài nguyên đã được dịch theo `Locale`.
- Các API định dạng như `java.text.MessageFormat`, `java.text.NumberFormat` và `java.time.format.DateTimeFormatter`: tạo văn bản, số và ngày giờ theo quy ước của từng locale.

Bài học tập trung vào cách dùng các API hiện hành của Java SE 27, cách tổ chức bản dịch UTF-8, cơ chế fallback và những lưu ý khi triển khai ứng dụng thực tế.

## 1. Quốc tế hóa và bản địa hóa

**Quốc tế hóa (internationalization, i18n)** là thiết kế ứng dụng sao cho có thể thích nghi với nhiều ngôn ngữ và vùng mà không phải sửa logic nghiệp vụ cho từng thị trường.

**Bản địa hóa (localization, l10n)** là cung cấp bản dịch và các quy tắc trình bày cụ thể cho một ngôn ngữ hoặc vùng.

Ví dụ, một ứng dụng đặt hàng có cùng dữ liệu:

~~~text
Tên người dùng: An
Số đơn hàng: 1250
Ngày giao dự kiến: 2026-12-02
Giá trị thanh toán: 1250000 VND
~~~

Nhưng có thể hiển thị bằng tiếng Việt hoặc tiếng Anh, với cách viết số và ngày tương ứng. **Giá trị dữ liệu không đổi**, còn biểu diễn cho người dùng thay đổi theo locale.

Cần phân biệt ba vấn đề:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Ngôn ngữ | Người dùng đọc thông điệp bằng tiếng gì? | Tiếng Việt, tiếng Anh |
| Vùng và quy ước hiển thị | Số, ngày và ký hiệu được trình bày thế nào? | `vi-VN`, `en-US` |
| Múi giờ | Một thời điểm xảy ra lúc mấy giờ tại nơi quan sát? | `Asia/Ho_Chi_Minh`, `Europe/Paris` |

`Locale` không tự dịch văn bản do ứng dụng viết và cũng không tự xác định múi giờ. Cần cung cấp bản dịch bằng `ResourceBundle` và chọn `ZoneId` khi bài toán liên quan đến thời điểm tuyệt đối.

## 2. Locale: ngôn ngữ, vùng và BCP 47

`Locale` thuộc gói `java.util`. Đối tượng này mô tả sở thích ngôn ngữ và vùng, thường dựa trên **thẻ ngôn ngữ BCP 47** (language tag).

Một số ví dụ:

| Language tag | Ý nghĩa thông thường |
|---|---|
| `vi` | Tiếng Việt, chưa chỉ định vùng |
| `vi-VN` | Tiếng Việt tại Việt Nam |
| `en-US` | Tiếng Anh tại Hoa Kỳ |
| `en-GB` | Tiếng Anh tại Vương quốc Anh |
| `fr-FR` | Tiếng Pháp tại Pháp |
| `zh-Hant-TW` | Tiếng Trung, chữ phồn thể, tại Đài Loan |

Trong language tag, các thành phần thường được nối bằng dấu gạch ngang (`-`). Mã ngôn ngữ thường viết thường, mã vùng thường viết hoa và mã chữ viết sử dụng cách viết như `Hant` hoặc `Latn`.

### 2.1. Tạo và đọc Locale

Với Java 27, cách đơn giản là `Locale.forLanguageTag(...)`:

~~~java
import java.util.Locale;

public class LocaleExample {
    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale britishEnglish = Locale.forLanguageTag("en-GB");

        System.out.println(vietnam.getLanguage());      // vi
        System.out.println(vietnam.getCountry());       // VN
        System.out.println(vietnam.toLanguageTag());    // vi-VN
        System.out.println(britishEnglish.toLanguageTag()); // en-GB
    }
}
~~~

Bạn cũng có thể dùng `Locale.of("vi", "VN")` nếu đã có riêng mã ngôn ngữ và mã vùng. Với dữ liệu đầu vào là language tag, `forLanguageTag` thể hiện rõ ý định và giữ các thành phần BCP 47 phù hợp.

`Locale.ROOT` là locale trung lập về ngôn ngữ và vùng. Nó hữu ích cho một số thao tác cần kết quả độc lập với ngôn ngữ người dùng; đây không phải lựa chọn để dịch hoặc trình bày nội dung cho người dùng.

### 2.2. Language tag hợp lệ khác với bản dịch được hỗ trợ

`Locale.forLanguageTag("fr-FR")` tạo ra một đối tượng `Locale`; điều đó **không có nghĩa** ứng dụng đã có bản dịch tiếng Pháp.

Tương tự, runtime có thể có dữ liệu định dạng cho một locale, nhưng ứng dụng vẫn cần tự cung cấp nhãn, nội dung và thông điệp phù hợp.

`Locale.forLanguageTag` có cách xử lý linh hoạt đối với một số thẻ không đúng cú pháp. Khi đầu vào là chuỗi do người dùng gửi, hãy xác thực và kiểm tra danh sách locale thực sự được ứng dụng hỗ trợ. Nếu cần kiểm tra nghiêm ngặt cú pháp BCP 47, có thể dùng `Locale.Builder`:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;

static Locale parseStrictly(String tag) {
    try {
        return new Locale.Builder()
                .setLanguageTag(tag)
                .build();
    } catch (IllformedLocaleException ex) {
        throw new IllegalArgumentException(
                "Language tag không hợp lệ: " + tag, ex
        );
    }
}
~~~

Kiểm tra cú pháp chỉ là một bước; ứng dụng còn phải quyết định có hỗ trợ locale đó hay không.

### 2.3. Default Locale và Locale.Category

JVM có locale mặc định. Có thể đọc bằng:

~~~java
Locale current = Locale.getDefault();

Locale forFormatting =
        Locale.getDefault(Locale.Category.FORMAT);

Locale forDisplay =
        Locale.getDefault(Locale.Category.DISPLAY);
~~~

Hai category có ý nghĩa khác nhau: `FORMAT` dành cho quy ước định dạng, còn `DISPLAY` liên quan đến tên hiển thị của ngôn ngữ và vùng.

Trong ứng dụng có nhiều người dùng hoặc nhiều yêu cầu xử lý đồng thời, nên **truyền Locale tường minh** vào API cần sử dụng:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat format = NumberFormat.getNumberInstance(locale);
~~~

`Locale.setDefault(...)` thay đổi cài đặt chung trong JVM, có thể ảnh hưởng tới các thành phần khác. Vì thế, không nên thay đổi locale mặc định toàn ứng dụng mỗi khi một người dùng chuyển ngôn ngữ.

## 3. ResourceBundle là gì?

`ResourceBundle` là API dùng để tra cứu tài nguyên theo **khóa (key)** và locale. Một bộ tài nguyên thường chứa các nhãn, tiêu đề, thông báo và mẫu câu của ứng dụng.

Ví dụ, thay vì viết trực tiếp:

~~~java
System.out.println("Chào mừng bạn quay lại!");
~~~

ứng dụng có thể tra cứu:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("i18n.messages", locale);

System.out.println(bundle.getString("welcome.back"));
~~~

Lời gọi trên tìm giá trị của khóa `welcome.back` trong bộ tài nguyên thích hợp với `locale`. Văn bản tiếng Việt hay tiếng Anh nằm trong các file tài nguyên, còn mã nghiệp vụ chỉ quan tâm đến khóa.

Ưu điểm:

- Tách bản dịch khỏi mã Java.
- Giữ các khóa dùng chung giữa các ngôn ngữ.
- Hỗ trợ chọn bản dịch theo ngôn ngữ và vùng.
- Có cơ chế tìm tài nguyên ở locale cha khi khóa hoặc bundle cụ thể không có.
- Cho phép đưa thêm ngôn ngữ mà không phải sao chép logic nghiệp vụ.

**ResourceBundle không phải hệ thống dịch tự động.** Nội dung của mỗi khóa phải do ứng dụng hoặc quy trình dịch thuật cung cấp.

## 4. Tổ chức bundle bằng file .properties

Đối với bản dịch chuỗi đơn giản, cách triển khai phổ biến là file `.properties` được Java nạp thông qua `PropertyResourceBundle`.

Ví dụ cấu trúc dự án:

~~~text
locale-demo/
├── src/
│   └── I18nDemo.java
├── resources/
│   └── i18n/
│       ├── messages.properties
│       ├── messages_vi.properties
│       ├── messages_vi_VN.properties
│       └── messages_en.properties
└── out/
~~~

Các file thuộc cùng một họ (bundle family) với **base name** là `i18n.messages`.

| File | Trường hợp áp dụng |
|---|---|
| `messages.properties` | Bundle gốc, dùng làm tài nguyên dự phòng |
| `messages_vi.properties` | Bản dịch tiếng Việt nói chung |
| `messages_vi_VN.properties` | Điều chỉnh riêng cho tiếng Việt tại Việt Nam |
| `messages_en.properties` | Bản dịch tiếng Anh |

Lưu ý sự khác biệt: language tag dùng dấu gạch ngang (`vi-VN`), trong khi tên file bundle dùng dấu gạch dưới (`messages_vi_VN.properties`). Dấu chấm trong base name `i18n.messages` tương ứng với thư mục `i18n/messages...`.

### 4.1. Khai báo nội dung cho từng bundle

Nội dung `resources/i18n/messages.properties`:

~~~properties
app.title=Localization example
welcome=Hello, {0}!
order.count=You have {0,number,integer} orders.
delivery.date=Expected delivery date:
~~~

Nội dung `resources/i18n/messages_vi.properties`:

~~~properties
app.title=Ví dụ bản địa hóa
welcome=Xin chào, {0}!
order.count=Bạn có {0,number,integer} đơn hàng.
delivery.date=Ngày giao hàng dự kiến:
~~~

Nội dung `resources/i18n/messages_vi_VN.properties`:

~~~properties
app.title=Ví dụ bản địa hóa tại Việt Nam
~~~

Nội dung `resources/i18n/messages_en.properties`:

~~~properties
app.title=Localization example
welcome=Hello, {0}!
order.count=You have {0,number,integer} orders.
delivery.date=Expected delivery date:
~~~

File `messages_vi_VN.properties` chỉ ghi đè khóa `app.title`. Các khóa khác có thể được tìm trong bundle cha `messages_vi.properties` rồi đến bundle gốc.

### 4.2. UTF-8 trong Java 27

File `.properties` chứa tiếng Việt nên được lưu bằng **UTF-8**. `PropertyResourceBundle` trong Java hiện đại hỗ trợ đọc UTF-8 theo mặc định khi được nạp từ luồng byte; có cơ chế thử đọc lại với ISO-8859-1 nếu phát hiện dữ liệu UTF-8 không hợp lệ trong chế độ mặc định.

Với dự án mới, nên chuẩn hóa toàn bộ file bản dịch thành UTF-8 để có thể đọc và chỉnh sửa trực tiếp:

~~~properties
account.created=Tài khoản đã được tạo thành công.
~~~

Không cần chuyển mọi chữ tiếng Việt sang chuỗi escape Unicode kiểu cũ. Tuy nhiên, **các ký tự cú pháp của file properties vẫn có ý nghĩa riêng**, chẳng hạn `=`, `:`, `#`, `!` hoặc dấu gạch chéo ngược. Nếu cần chúng ở vị trí đặc biệt trong khóa hoặc giá trị, phải áp dụng quy tắc escaping của định dạng properties.

## 5. Ví dụ hoàn chỉnh: nạp ResourceBundle theo Locale

Tạo file `src/I18nDemo.java`:

~~~java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class I18nDemo {
    public static void main(String[] args) {
        String languageTag = args.length > 0 ? args[0] : "vi-VN";
        Locale locale = Locale.forLanguageTag(languageTag);

        ResourceBundle bundle =
                ResourceBundle.getBundle("i18n.messages", locale);

        String greeting = new MessageFormat(
                bundle.getString("welcome"), locale
        ).format(new Object[] {"An"});

        String orders = new MessageFormat(
                bundle.getString("order.count"), locale
        ).format(new Object[] {1234});

        String number = NumberFormat.getNumberInstance(locale)
                .format(1234567.89);

        String delivery = LocalDate.of(2026, 12, 2).format(
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale)
        );

        System.out.println(bundle.getString("app.title"));
        System.out.println(greeting);
        System.out.println(orders);
        System.out.println(number);
        System.out.println(
                bundle.getString("delivery.date") + " " + delivery
        );
    }
}
~~~

Chương trình nhận language tag qua đối số dòng lệnh, dùng cùng locale cho cả bản dịch thông điệp và định dạng dữ liệu.

Từ thư mục gốc dự án, biên dịch:

~~~shell
javac -encoding UTF-8 -d out src/I18nDemo.java
~~~

Chạy trên **Windows**:

~~~powershell
java -cp "out;resources" I18nDemo vi-VN
java -cp "out;resources" I18nDemo en-US
~~~

Chạy trên **Linux/macOS**:

~~~shell
java -cp "out:resources" I18nDemo vi-VN
java -cp "out:resources" I18nDemo en-US
~~~

Thư mục `resources` cần có trên class path để JVM tìm thấy `i18n/messages.properties`. Lệnh `javac` biên dịch mã Java; nó **không tự sao chép các file .properties** vào thư mục `out`.

Khi chạy bằng `vi-VN`, chương trình sẽ chọn tiêu đề của `messages_vi_VN.properties`, kế thừa các thông điệp khác từ bundle tiếng Việt, rồi định dạng số và ngày theo dữ liệu locale tương ứng. Với `en-US`, chương trình dùng bundle tiếng Anh và các quy ước định dạng tiếng Anh tại Hoa Kỳ.

Dấu phân cách hàng nghìn, cách viết tháng và một số chi tiết trình bày có thể thay đổi theo dữ liệu locale đi kèm JDK. Do đó, không nên lấy một chuỗi kết quả đã in trên máy A làm hợp đồng bắt buộc cho mọi bản JDK hoặc mọi hệ điều hành.

## 6. Cơ chế tìm kiếm và fallback của ResourceBundle

Lời gọi:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle =
        ResourceBundle.getBundle("i18n.messages", locale);
~~~

thường tìm các ứng viên theo thứ tự cụ thể nhất đến tổng quát hơn:

~~~text
i18n/messages_vi_VN.properties
             |
             v
i18n/messages_vi.properties
             |
             v
i18n/messages.properties
~~~

Nếu bundle `vi_VN` tồn tại nhưng không chứa khóa `welcome`, Java có thể tìm khóa đó ở bundle cha `vi`. Nếu các file của ngôn ngữ được yêu cầu không có, thuật toán tải bundle mặc định còn có thể xét **locale mặc định của JVM** trước khi dùng bundle gốc. Vì vậy, không nên hiểu fallback là một phép ánh xạ luôn luôn đi thẳng từ locale không hỗ trợ đến tiếng Anh.

### 6.1. Kiểm tra locale thực tế của bundle

~~~java
Locale requested = Locale.forLanguageTag("vi-VN");

ResourceBundle bundle =
        ResourceBundle.getBundle("i18n.messages", requested);

System.out.println("Yêu cầu: " + requested.toLanguageTag());
System.out.println("Bundle: " + bundle.getLocale().toLanguageTag());
~~~

`getLocale()` cho biết locale của **bundle thực tế được chọn**, có thể khác locale yêu cầu khi fallback. Đối với bundle gốc, locale trả về có thể là `Locale.ROOT`.

Phương thức này hữu ích khi chẩn đoán bản dịch bị thiếu. Tuy nhiên, nó không cho biết một khóa riêng lẻ được lấy từ bundle hiện tại hay một bundle cha.

### 6.2. Điều gì xảy ra khi không tìm được bundle hoặc khóa?

Nếu không tìm thấy bất kỳ bundle nào phù hợp với base name, `ResourceBundle.getBundle` ném `MissingResourceException`.

Nếu tìm thấy bundle nhưng một khóa không tồn tại trong bundle và toàn bộ chuỗi cha, `bundle.getString(key)` cũng ném `MissingResourceException`.

~~~java
import java.util.MissingResourceException;
import java.util.ResourceBundle;

try {
    String label = bundle.getString("menu.settings");
    System.out.println(label);
} catch (MissingResourceException ex) {
    System.err.println("Thiếu khóa bản dịch: menu.settings");
}
~~~

Trong mã ví dụ, `bundle` được hiểu là đối tượng đã tải ở bước trước. Ở ứng dụng thực tế, nên kiểm tra thiếu khóa trong kiểm thử và quy trình phát hành. Bắt ngoại lệ để hiển thị văn bản tạm thời chỉ nên là lựa chọn đã được thiết kế rõ ràng, không phải cách bỏ qua lỗi dịch thuật một cách âm thầm.

### 6.3. Kiểm soát chính sách fallback

Đối với sản phẩm chỉ hỗ trợ một tập ngôn ngữ xác định, nên chọn locale ứng dụng hỗ trợ **trước khi** gọi `getBundle`:

~~~java
import java.util.Locale;
import java.util.Set;

static Locale selectSupportedLocale(String input) {
    Set<String> supported = Set.of("vi-VN", "en-US");

    if (!supported.contains(input)) {
        return Locale.forLanguageTag("vi-VN");
    }

    return Locale.forLanguageTag(input);
}
~~~

Đây là ví dụ whitelist đơn giản; sản phẩm thực tế có thể cần chuẩn hóa các language tag hợp lệ và cho phép lựa chọn ngôn ngữ theo sở thích người dùng.

Nếu cần chính sách fallback đặc biệt cho ứng dụng không dùng module đặt tên, `ResourceBundle.Control` có thể tùy chỉnh quá trình tìm bundle. **Trong named module, các overload của `getBundle` nhận `ResourceBundle.Control` không được hỗ trợ.** Với thiết kế module hiện đại cần provider riêng, hãy tìm hiểu cơ chế `ResourceBundleProvider`.

Cách đơn giản nhất với nhiều ứng dụng vẫn là tổ chức đầy đủ file bundle, chỉ hỗ trợ locale đã kiểm thử và có bundle gốc hợp lệ.

## 7. Thông điệp có tham số bằng MessageFormat

Đối với thông báo chứa tên người dùng, số lượng hoặc dữ liệu động, không nên ghép chuỗi theo trật tự cố định trong mã Java:

~~~java
// Khó dịch khi mỗi ngôn ngữ có trật tự từ khác nhau
String message = "Xin chào, " + name + "!";
~~~

Hãy định nghĩa cả câu trong file tài nguyên và chèn dữ liệu thông qua placeholder.

Ví dụ `messages_vi.properties`:

~~~properties
greeting=Xin chào, {0}!
payment=Đơn {0} có {1,number,integer} sản phẩm.
~~~

Ví dụ `messages_en.properties`:

~~~properties
greeting=Hello, {0}!
payment=Order {0} has {1,number,integer} items.
~~~

Mã Java:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

static String translate(
        ResourceBundle bundle,
        Locale locale,
        String key,
        Object... args) {

    MessageFormat format =
            new MessageFormat(bundle.getString(key), locale);

    return format.format(args);
}
~~~

Gọi phương thức:

~~~java
String message = translate(
        bundle,
        locale,
        "payment",
        "A1024",
        1250
);
~~~

Các placeholder quan trọng:

| Mẫu | Ý nghĩa |
|---|---|
| `{0}` | Đối số thứ nhất |
| `{1}` | Đối số thứ hai |
| `{1,number}` | Đối số thứ hai, định dạng số theo locale |
| `{1,number,integer}` | Đối số thứ hai, định dạng như số nguyên |
| `{1,number,percent}` | Đối số thứ hai, định dạng tỷ lệ phần trăm |

Người dịch có thể đổi thứ tự `{0}` và `{1}` theo ngữ pháp của ngôn ngữ đích mà không thay đổi mã Java.

### 7.1. Dấu nháy đơn trong MessageFormat

`MessageFormat` sử dụng dấu nháy đơn `'` để đánh dấu đoạn văn bản không phân tích placeholder. Vì vậy, muốn hiển thị một dấu nháy đơn trong mẫu, cần viết hai dấu nháy liên tiếp.

Ví dụ:

~~~properties
# messages_en.properties
message=You''re viewing {0}.
~~~

Khi truyền `"Java"`, thông điệp hiển thị là `You're viewing Java.`.

Nếu người dịch viết sai quy tắc escaping, placeholder có thể không được thay thế như mong đợi. Hãy kiểm tra tất cả message pattern trong quá trình kiểm thử bản địa hóa.

### 7.2. Giới hạn khi xử lý số nhiều và ngữ pháp phức tạp

Không phải mọi ngôn ngữ đều tạo câu số nhiều bằng cách thêm một hậu tố. `MessageFormat` chuẩn của Java hỗ trợ các kiểu định dạng và điều kiện nhất định, nhưng việc xử lý đầy đủ các quy tắc plural/gender đặc thù của từng ngôn ngữ cần được thiết kế cẩn thận.

Với sản phẩm có yêu cầu pluralization phức tạp, hãy chọn giải pháp có hỗ trợ quy tắc của các locale mục tiêu và kiểm thử với người dịch. Không nên tự ghép thêm "s" hoặc sao chép cấu trúc số nhiều của tiếng Anh cho tất cả các ngôn ngữ.

## 8. Định dạng số, tỷ lệ và tiền tệ

`NumberFormat` nằm trong `java.text`, cung cấp các định dạng số phụ thuộc locale. Ví dụ:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class NumberLocaleExample {
    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale unitedStates = Locale.forLanguageTag("en-US");

        double amount = 1234567.89;
        double ratio = 0.125;

        System.out.println(
                NumberFormat.getNumberInstance(vietnam).format(amount)
        );
        System.out.println(
                NumberFormat.getNumberInstance(unitedStates).format(amount)
        );

        System.out.println(
                NumberFormat.getPercentInstance(vietnam).format(ratio)
        );
        System.out.println(
                NumberFormat.getPercentInstance(unitedStates).format(ratio)
        );
    }
}
~~~

`getNumberInstance(locale)` chọn cách viết chữ số, dấu nhóm và dấu thập phân theo locale. `getPercentInstance(locale)` nhận một tỷ lệ, ví dụ `0.125` tương ứng với 12,5% về mặt toán học; cách hiển thị và làm tròn tùy quy tắc định dạng.

Không nên lưu dữ liệu nghiệp vụ hoặc truyền dữ liệu qua API bằng chuỗi số đã định dạng cho người dùng. Trong tính toán hãy giữ kiểu số phù hợp, còn bản địa hóa chỉ áp dụng ở lớp trình bày.

### 8.1. Tiền tệ phụ thuộc cả locale và đơn vị tiền

`NumberFormat.getCurrencyInstance(locale)` thường dùng đơn vị tiền mặc định gắn với locale. Tuy nhiên, **đồng tiền của giao dịch** là dữ liệu nghiệp vụ riêng biệt.

Ví dụ: một khách hàng ở Hoa Kỳ có thể đang xem giá sản phẩm bằng VND. Để định dạng số tiền với locale của người đọc và mã tiền tệ cụ thể, kết hợp `NumberFormat` và `Currency`:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyExample {
    public static void main(String[] args) {
        Locale displayLocale = Locale.forLanguageTag("en-US");
        Currency currency = Currency.getInstance("VND");
        BigDecimal amount = new BigDecimal("1250000");

        NumberFormat format =
                NumberFormat.getCurrencyInstance(displayLocale);

        format.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            format.setMinimumFractionDigits(digits);
            format.setMaximumFractionDigits(digits);
        }

        System.out.println(format.format(amount));
    }
}
~~~

`setCurrency` thay đổi đơn vị tiền của formatter nhưng **không tự bảo đảm cập nhật số chữ số thập phân**. Vì vậy, đoạn mã trên áp dụng số chữ số thập phân mặc định của đồng tiền khi giá trị này được xác định.

Trong hệ thống tài chính, quy tắc làm tròn, số chữ số và cách biểu diễn có thể phải tuân theo nghiệp vụ riêng. `Locale` chỉ giải quyết quy ước trình bày.

### 8.2. Định dạng không đồng nghĩa xác thực đầu vào

`NumberFormat` cũng có thể đọc một chuỗi số theo locale bằng `parse(...)`. Tuy nhiên, việc parse có thể chấp nhận một phần của chuỗi tùy chế độ và cấu hình.

Đối với form nhập liệu, cần kiểm tra việc toàn bộ chuỗi đã được phân tích và xác thực các quy tắc nghiệp vụ. Đừng tự ý xóa mọi dấu phẩy hoặc dấu chấm trước khi parse, vì các ký tự đó có thể mang ý nghĩa khác nhau ở từng locale.

## 9. Định dạng ngày giờ bằng java.time

Với Java 27, `java.time` và `DateTimeFormatter` là lựa chọn phù hợp để làm việc với ngày giờ. API này hỗ trợ định dạng theo locale, đồng thời tách rõ ngày giờ, thời điểm và múi giờ.

Ví dụ định dạng ngày:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class DateLocaleExample {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 12, 2);

        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale englishUS = Locale.forLanguageTag("en-US");

        DateTimeFormatter vietnamese =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(vietnam);

        DateTimeFormatter american =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(englishUS);

        System.out.println(date.format(vietnamese));
        System.out.println(date.format(american));
    }
}
~~~

`FormatStyle` có các mức như `SHORT`, `MEDIUM`, `LONG` và `FULL`. Tùy locale và loại ngày giờ, mức này ảnh hưởng cách hiển thị tên tháng, thứ, thứ tự thành phần và độ dài biểu diễn.

Không nên dùng cùng một pattern cố định cho mọi ngôn ngữ khi muốn hiển thị theo quy ước vùng.

### 9.1. Locale không phải múi giờ

Một `Instant` biểu diễn một thời điểm trên dòng thời gian. Để hiển thị thời điểm đó cho người dùng, phải xác định múi giờ.

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ZonedDateExample {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-11-27T08:30:00Z");

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Locale locale = Locale.forLanguageTag("vi-VN");

        ZonedDateTime localTime = instant.atZone(zone);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG)
                        .withLocale(locale);

        System.out.println(localTime.format(formatter));
    }
}
~~~

Ở đây, `Asia/Ho_Chi_Minh` quyết định giờ địa phương, còn `vi-VN` quyết định cách diễn đạt ngày giờ. Hai lựa chọn có thể độc lập: người dùng chọn tiếng Anh vẫn có thể muốn xem giờ tại Việt Nam.

Đối với dữ liệu trao đổi giữa các hệ thống, nên dùng định dạng thời gian chuẩn hóa phù hợp như ISO 8601 hoặc một instant xác định. Dạng hiển thị theo locale dành cho giao diện người dùng.

### 9.2. DateTimeFormatter và khả năng dùng đồng thời

`DateTimeFormatter` là một đối tượng không thay đổi sau khi tạo (immutable) và có thể được tái sử dụng an toàn giữa các luồng.

Ngược lại, các formatter như `NumberFormat` và `MessageFormat` nhìn chung không được đồng bộ hóa để dùng chung khi có nhiều luồng cùng thao tác. Nên tạo formatter riêng cho từng xử lý hoặc bảo vệ việc truy cập đồng thời theo thiết kế ứng dụng.

## 10. Sắp xếp chuỗi và chuyển chữ hoa, chữ thường

Bản địa hóa còn ảnh hưởng cách xử lý văn bản. Thứ tự sắp xếp theo ngôn ngữ không nhất thiết trùng với thứ tự mã Unicode của `String.compareTo`.

### 10.1. Dùng Collator cho thứ tự theo ngôn ngữ

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class CollationExample {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Collator collator = Collator.getInstance(locale);

        List<String> names =
                new ArrayList<>(List.of("Bình", "Ánh", "An", "Đức"));

        names.sort(collator);
        System.out.println(names);
    }
}
~~~

`Collator` áp dụng quy tắc đối chiếu văn bản theo locale khi dữ liệu runtime hỗ trợ. Có thể điều chỉnh mức độ phân biệt chữ hoa, chữ thường hoặc dấu theo yêu cầu; đừng giả định thứ tự kết quả luôn giống nhau giữa mọi bộ dữ liệu locale.

Khi cần một thứ tự ổn định cho khóa máy hoặc giao thức, hãy xác định quy tắc riêng; thứ tự theo locale thường phù hợp cho danh sách hiển thị cho người dùng.

### 10.2. Chuyển chữ hoa và chữ thường theo Locale

~~~java
String input = "Istanbul";

String forDisplay =
        input.toLowerCase(Locale.forLanguageTag("tr-TR"));

String forMachine =
        input.toLowerCase(Locale.ROOT);
~~~

Một số ngôn ngữ có quy tắc chuyển chữ khác tiếng Anh. Vì vậy, khi chuyển chữ cho nội dung hiển thị hoặc tìm kiếm theo ngôn ngữ người dùng, hãy xem xét locale cụ thể.

`Locale.ROOT` hữu ích khi muốn giảm phụ thuộc vào locale mặc định trong thao tác trên các định danh kỹ thuật. Tuy nhiên, chuyển chữ thường không phải phép chuẩn hóa đủ cho mọi loại mã định danh hay mọi bài toán so khớp Unicode.

## 11. Tổ chức tài nguyên khi đóng gói ứng dụng

Trong ví dụ chạy từ dòng lệnh, chúng ta thêm cả thư mục `out` và `resources` vào class path. Khi dùng Maven, Gradle hoặc một công cụ build khác, hãy cấu hình để file tài nguyên được **đóng gói vào vị trí tương ứng trên runtime class path hoặc bên trong module**.

Ví dụ, trong JAR thông thường:

~~~text
app.jar
├── I18nDemo.class
└── i18n/
    ├── messages.properties
    ├── messages_vi.properties
    ├── messages_vi_VN.properties
    └── messages_en.properties
~~~

Khi đó, `ResourceBundle.getBundle("i18n.messages", locale)` có thể tìm tài nguyên tương ứng.

Với ứng dụng dùng Java Platform Module System, việc nạp tài nguyên còn chịu các quy tắc đóng gói và khả năng truy cập tài nguyên của module. Tài nguyên nằm trong module đang gọi có thể được nạp theo cách thích hợp; khi phân phối bundle qua các provider module riêng, cần dùng các cơ chế module và `ResourceBundleProvider` tương ứng.

`ResourceBundle` cũng có cơ chế cache. Việc thay đổi file `.properties` trong lúc ứng dụng đang chạy không bảo đảm các lần gọi tiếp theo sẽ lập tức thấy bản dịch mới. Nếu sản phẩm cần nạp lại bản dịch lúc runtime, phải thiết kế rõ cơ chế reload và vòng đời cache.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `MissingResourceException` khi gọi `getBundle` | Không tìm thấy bộ tài nguyên phù hợp với base name | Kiểm tra tên package, đường dẫn tài nguyên, class path hoặc cấu hình module |
| `MissingResourceException` khi gọi `getString` | Khóa không có trong bundle và các bundle cha | So sánh bộ khóa giữa các file, thêm khóa bị thiếu hoặc xây dựng fallback có chủ đích |
| Bản dịch không đúng ngôn ngữ yêu cầu | Xảy ra fallback sang locale mặc định hoặc bundle gốc | Kiểm tra `bundle.getLocale()` và danh sách ngôn ngữ đã hỗ trợ |
| Tiếng Việt bị lỗi ký tự | File không phải UTF-8 hoặc xử lý encoding sai | Lưu resources bằng UTF-8 và kiểm tra quá trình đóng gói |
| Placeholder `{0}` không được thay | Chưa gọi `MessageFormat` hoặc mẫu có lỗi dấu nháy | Kiểm tra pattern và quy tắc escaping dấu `'` |
| Số và ngày có định dạng không nhất quán | Dùng locale mặc định ở một vài nhánh xử lý | Truyền cùng `Locale` tường minh đến các formatter |
| Tiền tệ hiển thị sai đơn vị | Lấy đơn vị tiền mặc định của locale thay vì từ giao dịch | Lưu ISO currency code và chọn `Currency` theo nghiệp vụ |
| Giờ hiển thị sai | Chỉ đổi locale mà không xác định `ZoneId` | Chuyển `Instant` sang múi giờ mong muốn trước khi định dạng |
| Thứ tự danh sách tên không đúng kỳ vọng | Sắp xếp bằng `String.compareTo` theo mã ký tự | Cân nhắc `Collator` ứng với ngôn ngữ người dùng |
| Thay file dịch mà ứng dụng vẫn hiển thị bản cũ | Bundle được cache hoặc file chưa được đóng gói lại | Thiết kế quy trình triển khai/reload và kiểm tra nội dung gói chạy |

### 12.1. Đừng dùng kết quả hiển thị để kiểm tra chính xác dữ liệu

Dấu nhóm hàng nghìn, dấu thập phân, cách viết tháng và tên tiền tệ là phần **trình bày**. Tại tầng dữ liệu và logic nghiệp vụ, dùng kiểu phù hợp như `BigDecimal`, `LocalDate`, `Instant` và mã tiền tệ ISO.

Khi viết kiểm thử, hãy tách hai nhóm:

- Kiểm thử **giá trị nghiệp vụ** không phụ thuộc locale.
- Kiểm thử **bản địa hóa** theo các locale và phiên bản dữ liệu runtime được ứng dụng hỗ trợ.

Các chuỗi đầu ra có thể chịu ảnh hưởng của phiên bản CLDR và JDK, do đó cần kiểm soát môi trường chạy khi so sánh văn bản định dạng chính xác.

### 12.2. Kiểm thử ResourceBundle theo một ma trận locale

Ví dụ ứng dụng hỗ trợ `vi-VN` và `en-US`. Có thể kiểm tra:

1. Mỗi locale được hỗ trợ tải được bundle thành công.
2. Các khóa bắt buộc như `app.title`, `welcome` và `order.count` đều tồn tại.
3. Các pattern `MessageFormat` hợp lệ và giữ đúng placeholder.
4. Một số đầu vào đại diện được định dạng đúng: `0`, số âm, số thập phân, tỷ lệ phần trăm, ngày gần ranh giới tháng/năm.
5. Nội dung tiếng Việt còn nguyên dấu sau build và đóng gói.
6. Locale không được hỗ trợ được xử lý đúng theo chính sách của ứng dụng.
7. Thời điểm được định dạng bằng múi giờ đã chọn, độc lập với ngôn ngữ.

## 13. Quy trình áp dụng trong dự án thực tế

Một cách tổ chức dễ duy trì là:

~~~text
Request / cấu hình người dùng
           |
           v
  Xác định language tag
           |
           v
  Kiểm tra locale hỗ trợ
           |
           v
    Locale của yêu cầu
       /           \
      v             v
ResourceBundle   Formatter theo locale
   (thông điệp)   (số, ngày, tiền tệ)
      \             /
       v           v
        Giao diện hiển thị
~~~

Đối với mỗi request hoặc phiên làm việc, sử dụng locale đã chọn một cách nhất quán. Khi hiển thị thời điểm, tiếp tục dùng múi giờ đã xác định. Khi hiển thị tiền tệ, dùng mã tiền của giao dịch và quy tắc làm tròn nghiệp vụ.

Một số nguyên tắc thực hành:

- Đặt tên khóa theo ý nghĩa ổn định, ví dụ `checkout.total` hoặc `account.created`.
- Dịch toàn bộ câu, không ghép các mảnh câu cố định theo ngữ pháp của một ngôn ngữ.
- Giữ thống nhất tên và kiểu placeholder giữa các bản dịch.
- Đảm bảo các file tài nguyên được đóng gói cùng ứng dụng và lưu dưới UTF-8.
- Dùng `MessageFormat` cho thông điệp tham số, `NumberFormat` cho số/tiền tệ và `DateTimeFormatter` cho ngày giờ.
- Tách locale, múi giờ và mã tiền tệ; ba khái niệm này phục vụ ba mục đích khác nhau.
- Kiểm tra fallback, khóa thiếu và bản dịch thiếu trước khi phát hành.
- Không thay đổi locale mặc định của toàn JVM theo từng người dùng.

## 14. Những điểm cần ghi nhớ

- `Locale` biểu diễn ngôn ngữ/vùng, nhưng không tự cung cấp bản dịch ứng dụng.
- `ResourceBundle` nạp tài nguyên theo base name và locale, hỗ trợ tìm khóa qua chuỗi bundle cha.
- Tên file `.properties` dùng hậu tố như `_vi_VN`, trong khi language tag BCP 47 dùng `vi-VN`.
- Java 27 hỗ trợ file `.properties` UTF-8; nên lưu tiếng Việt trực tiếp dưới UTF-8.
- `ResourceBundle` có fallback qua locale cha và có thể xét locale mặc định của JVM; cần kiểm tra chính sách fallback.
- `MessageFormat` cho phép thay đổi trật tự placeholder theo từng ngôn ngữ.
- `NumberFormat` và `DateTimeFormatter` nhận locale tường minh để trình bày dữ liệu theo vùng.
- `Currency` và `ZoneId` là dữ liệu riêng: locale không đủ để xác định tiền tệ giao dịch hoặc múi giờ.
- `Collator` phù hợp hơn phép so sánh mã ký tự khi sắp xếp văn bản cho người dùng.
- Để ứng dụng ổn định, hãy lưu dữ liệu dưới dạng có cấu trúc, bản địa hóa ở lớp hiển thị và kiểm thử các locale thực sự được hỗ trợ.

## Tài liệu tham khảo chính thức

- [Locale — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html)
- [ResourceBundle — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ResourceBundle.html)
- [PropertyResourceBundle — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [MessageFormat — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/MessageFormat.html)
- [NumberFormat — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html)
- [Currency — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Currency.html)
- [DateTimeFormatter — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Collator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Collator.html)
- [ResourceBundleProvider — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/spi/ResourceBundleProvider.html)
