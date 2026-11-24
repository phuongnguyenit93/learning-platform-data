# ResourceBundle, đa ngôn ngữ và dữ liệu locale

Một ứng dụng Spring Boot có thể hiển thị thông báo bằng nhiều ngôn ngữ, định dạng ngày tháng và số theo vùng, hoặc chọn nội dung dựa trên locale của người dùng. Java cung cấp **ResourceBundle** để tra cứu thông điệp theo ngôn ngữ; Spring cung cấp **MessageSource** để tích hợp thông điệp vào application context. Khi biên dịch ứng dụng thành GraalVM Native Image, cần hiểu rõ hai nhóm dữ liệu khác nhau: **resource bundle chứa nội dung ứng dụng** và **locale data của JDK chứa quy tắc định dạng theo vùng**.

Bài này giải thích cách tổ chức các file properties đa ngôn ngữ, cơ chế fallback của ResourceBundle, tích hợp với Spring Boot, đăng ký resource bundle hints và bổ sung locale data cho native executable. Mục tiêu là bảo đảm cùng một binary có thể phục vụ đúng thông điệp và định dạng cho các locale mà ứng dụng cam kết hỗ trợ.

## 1. Locale và ResourceBundle giải quyết hai việc khác nhau

**Locale** mô tả quy ước ngôn ngữ và khu vực, thường gồm language, country/region và có thể có script hoặc variant. Ví dụ:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi");
Locale vietnameseVietnam = Locale.forLanguageTag("vi-VN");
Locale englishUnitedStates = Locale.forLanguageTag("en-US");
Locale japaneseJapan = Locale.forLanguageTag("ja-JP");
~~~

Locale không tự chứa nội dung dịch. Nó là thông tin để ứng dụng hoặc thư viện chọn thông điệp và quy tắc định dạng phù hợp.

**ResourceBundle** là cơ chế tra cứu một nhóm tài nguyên theo base name và locale. Với bundle dạng properties, mỗi locale có thể có một file riêng:

~~~text
src/main/resources/
└── i18n/
    ├── messages.properties
    ├── messages_en.properties
    ├── messages_en_US.properties
    ├── messages_vi.properties
    ├── messages_vi_VN.properties
    └── messages_ja.properties
~~~

Tên bundle gốc trong Java là `i18n.messages`, tương ứng đường dẫn tài nguyên `i18n/messages.properties`. Khi yêu cầu locale `vi-VN`, Java tìm bundle phù hợp theo các biến thể locale rồi sử dụng bundle gốc khi cần.

Phân biệt:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Locale | Người dùng đang dùng ngôn ngữ/khu vực nào? | `vi-VN` |
| ResourceBundle | Nội dung thông điệp cho locale đó là gì? | `greeting=Xin chào, {0}!` |
| Locale data của JDK | Ngày, số, tiền tệ được định dạng theo quy ước nào? | `23/11/2026` hoặc `1.234,56` |
| MessageSource | Ứng dụng Spring lấy thông điệp theo code và locale như thế nào? | `messageSource.getMessage(...)` |

**Điểm quan trọng với Native Image:** đăng ký bundle thông điệp không đồng nghĩa đã bao gồm toàn bộ locale data của JDK; và thêm locale data của JDK cũng không tự đóng gói các file dịch do ứng dụng cung cấp.

## 2. Tổ chức ResourceBundle bằng properties

Mỗi file properties chứa các key ổn định và nội dung theo một ngôn ngữ. Ví dụ:

**`src/main/resources/i18n/messages.properties`** — bundle gốc:

~~~properties
greeting=Hello, {0}!
order.created=Order {0} has been created.
validation.required=This field is required.
~~~

**`messages_en.properties`**:

~~~properties
greeting=Hello, {0}!
order.created=Order {0} has been created.
validation.required=This field is required.
~~~

**`messages_vi.properties`**:

~~~properties
greeting=Xin chào, {0}!
order.created=Đơn hàng {0} đã được tạo.
validation.required=Trường này là bắt buộc.
~~~

**`messages_vi_VN.properties`**:

~~~properties
greeting=Xin chào {0}!
order.created=Đơn hàng {0} đã được tạo tại Việt Nam.
validation.required=Vui lòng nhập trường này.
~~~

**`messages_ja.properties`**:

~~~properties
greeting=こんにちは、{0}さん！
order.created=注文 {0} を作成しました。
validation.required=この項目は必須です。
~~~

Trong ví dụ, `messages.properties` là bundle gốc để làm fallback khi không có bản dịch cụ thể. `messages_vi.properties` áp dụng cho tiếng Việt nói chung; `messages_vi_VN.properties` có thể ghi đè nội dung dành riêng cho Việt Nam.

### Key nên ổn định, nội dung mới thay đổi theo locale

Không dùng cả câu tiếng Anh làm key rồi tìm cách ghép chuỗi dịch. Thay vào đó, dùng key mang ý nghĩa nghiệp vụ:

- `greeting`
- `order.created`
- `validation.required`
- `payment.declined`

Giữ cùng một tập key giữa các file locale giúp tránh lỗi thiếu bản dịch. Với ứng dụng lớn, có thể duy trì bảng kiểm tra key bằng test hoặc bước validation trong CI.

### Encoding

Với Java 9 trở lên, properties được dùng bởi `PropertyResourceBundle` mặc định đọc UTF-8 theo cơ chế chuẩn của JDK. Spring Boot cũng cho phép cấu hình encoding của message source. Nên lưu các file dưới dạng UTF-8 và khai báo rõ:

~~~properties
spring.messages.encoding=UTF-8
~~~

Nếu hỗ trợ JDK cũ hoặc công cụ xử lý properties khác, hãy kiểm tra encoding end-to-end; không chuyển nội dung tiếng Việt thành dạng escape chỉ để né lỗi encoding của editor.

## 3. Cách ResourceBundle tìm bundle và fallback locale

Gọi:

~~~java
ResourceBundle bundle = ResourceBundle.getBundle(
        "i18n.messages",
        Locale.forLanguageTag("vi-VN")
);

String greeting = bundle.getString("greeting");
System.out.println(greeting);
~~~

Java dùng base name `i18n.messages` và locale yêu cầu để tìm bundle phù hợp. Với properties files trong ví dụ, thứ tự candidate điển hình cho `vi-VN` là:

~~~text
i18n/messages_vi_VN.properties
i18n/messages_vi.properties
i18n/messages.properties
~~~

Nếu không tìm thấy bundle theo locale yêu cầu, cơ chế `ResourceBundle` còn có thể thử fallback theo **default locale của JVM** trước khi quay về bundle gốc. Hành vi này có thể khiến kết quả phụ thuộc vào cấu hình máy/container nếu ứng dụng không chủ động xác định locale và fallback policy.

Ví dụ, nếu máy chạy native được cấu hình default locale là `en-US` còn máy kiểm thử là `vi-VN`, một key thiếu ở bundle tiếng Việt có thể nhận nội dung khác tùy default locale và các bundle có mặt.

### Quy tắc fallback cần thiết kế rõ

- Cung cấp bundle gốc `messages.properties` để có fallback cuối cùng.
- Chỉ thêm bundle theo locale mà sản phẩm thật sự hỗ trợ.
- Kiểm tra các key quan trọng có trong mọi bundle cần thiết.
- Không dựa vào default locale của host để chọn ngôn ngữ người dùng.
- Nếu cần hành vi nhất quán, cấu hình chính sách fallback của Spring MessageSource hoặc dùng cách gọi ResourceBundle phù hợp với yêu cầu.

Trong Spring Boot, có thể đặt:

~~~properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

`fallback-to-system-locale=false` tránh việc Spring message source thử ngôn ngữ mặc định của hệ điều hành như một bước fallback ngoài locale được yêu cầu và bundle gốc. Hãy kiểm tra đúng tên property theo phiên bản Spring Boot của dự án.

## 4. Dùng ResourceBundle trực tiếp trong Java

Một service nhỏ có thể nhận locale rõ ràng và tra cứu thông điệp:

~~~java
package com.example.nativeimage;

import java.util.Locale;
import java.util.ResourceBundle;

public final class GreetingCatalog {

    public String greeting(String name, Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("i18n.messages", locale);
        return bundle.getString("greeting").replace("{0}", name);
    }
}
~~~

Để định dạng tham số phức tạp, ngày tháng hoặc số, không nên tự thay chuỗi thủ công. Có thể dùng `MessageFormat` với locale:

~~~java
package com.example.nativeimage;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class GreetingCatalog {

    public String greeting(String name, Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("i18n.messages", locale);

        String pattern = bundle.getString("greeting");
        MessageFormat formatter = new MessageFormat(pattern, locale);

        return formatter.format(new Object[] { name });
    }
}
~~~

`MessageFormat` dùng locale để diễn giải các phần định dạng trong pattern. Nếu thông điệp có ngày tháng, số hoặc tiền tệ, cần test kết quả theo locale mục tiêu và không ghép định dạng thủ công.

Trong một ứng dụng web, locale nên được xác định từ một nguồn rõ ràng, chẳng hạn `Accept-Language` header, user preference đã lưu hoặc cấu hình nghiệp vụ. Không nên nhận một chuỗi locale bất kỳ rồi mặc nhiên tin rằng nó hợp lệ hoặc được hỗ trợ; hãy parse, validate và chọn fallback policy.

## 5. Tích hợp ResourceBundle với Spring MessageSource

Spring cung cấp `MessageSource` để các bean lấy thông điệp theo message code, tham số và locale. Spring Boot có thể tự cấu hình message source khi tìm thấy bundle basename phù hợp.

Cấu hình:

~~~properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Service sử dụng `MessageSource`:

~~~java
package com.example.nativeimage;

import java.util.Locale;

import org.springframework.context.MessageSource;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final MessageSource messageSource;

    public GreetingService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String greeting(String name, Locale locale) {
        return messageSource.getMessage(
                "greeting",
                new Object[] { name },
                locale
        );
    }
}
~~~

Controller có thể nhận locale mà Spring MVC phân giải từ request:

~~~java
package com.example.nativeimage;

import java.util.Locale;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "bạn") String name,
            Locale locale) {
        return greetingService.greeting(name, locale);
    }
}
~~~

Với cấu hình MVC mặc định dựa trên header, client có thể gửi:

~~~http
GET /greeting?name=Lan HTTP/1.1
Accept-Language: vi-VN
~~~

Ứng dụng trả thông điệp theo bundle phù hợp. Cơ chế locale resolver có thể được tùy biến; nếu sản phẩm lưu ngôn ngữ trong profile người dùng hoặc cookie, hãy cấu hình resolver tương ứng và test nó riêng.

### ResourceBundleMessageSource và resource-based message source

Cần phân biệt cách Spring tải message:

- `ResourceBundleMessageSource` dùng cơ chế `java.util.ResourceBundle` và base name. Đây là trường hợp liên quan trực tiếp tới resource bundle hints.
- `ReloadableResourceBundleMessageSource` tải properties thông qua abstraction resource của Spring và có các hành vi reload/cache riêng. Với cách tải này, hãy kiểm tra resource patterns/hints cần thiết cho đường dẫn properties.
- `MessageSource` là interface mà service sử dụng; không nên giả định mọi implementation đều dùng cùng một cơ chế tải tài nguyên.

Spring Boot auto-configuration và các thư viện có thể đóng góp hints cho một số trường hợp. Hãy xác minh với phiên bản Spring Boot và message source thực tế; bổ sung hints cho bundle tùy chỉnh khi chúng chưa được framework hoặc thư viện đăng ký.

## 6. Đăng ký ResourceBundleHints cho GraalVM Native Image

GraalVM Native Image cần biết resource bundle nào phải được đóng gói. Spring cung cấp API trong `RuntimeHints`:

~~~java
hints.resources().registerResourceBundle("i18n.messages");
~~~

Tên truyền vào là **base name** của bundle, không phải tên một file properties riêng lẻ và không có đuôi `.properties`.

Có thể tạo registrar:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class MessageBundleHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerResourceBundle("i18n.messages");
    }
}
~~~

Đăng ký registrar vào Spring context:

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(MessageBundleHints.class)
public class NativeMessageConfiguration {
}
~~~

Khi Spring AOT phân tích cấu hình, registrar đóng góp hint cho bundle `i18n.messages`. Native Image có thể đưa các biến thể locale của bundle vào binary theo metadata mà build tool nhận được.

Nếu ứng dụng có nhiều base name:

~~~java
@Override
public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
    hints.resources().registerResourceBundle("i18n.messages");
    hints.resources().registerResourceBundle("i18n.validation");
    hints.resources().registerResourceBundle("i18n.notifications");
}
~~~

Hãy đăng ký đúng các base name ứng dụng thực sự dùng. Không cần tạo một hint cho từng locale file khi API nhận base name của bundle.

### Khi nào dùng registerPattern thay vì registerResourceBundle?

Hai API phục vụ các loại tài nguyên khác nhau:

| API | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `registerResourceBundle("i18n.messages")` | Bundle theo cơ chế Java ResourceBundle | `i18n/messages_vi.properties` |
| `registerPattern("templates/.*")` | Resource file được đọc theo đường dẫn | Template HTML trong classpath |
| `registerPattern("rules/.*\\.json")` | Tập file JSON tĩnh | Rule/configuration JSON |
| Reflection hints | Truy cập class/member động | DTO được gọi bằng reflection |

Đăng ký một resource pattern rộng không phải cách thay thế tốt cho resource bundle hint nếu ứng dụng đang gọi `ResourceBundle.getBundle`. Hãy chọn API theo cơ chế thực tế.

## 7. Locale data của JDK trong Native Image

Ngoài thông điệp do ứng dụng cung cấp, JDK còn chứa dữ liệu locale cho các API như:

- `NumberFormat` và `DecimalFormat` để định dạng số.
- `DateFormat`, `DateTimeFormatter` và `Calendar` để định dạng ngày/thời gian.
- `Currency` để biểu diễn tiền tệ.
- `Collator` để so sánh/sắp xếp chuỗi theo quy tắc ngôn ngữ.
- Các API liên quan tới biểu tượng, tên tháng, ngày trong tuần và quy tắc vùng.

Native Image có thể không bao gồm toàn bộ dữ liệu locale của JDK theo mặc định. Tùy phiên bản GraalVM, cần chỉ định các locale cần hỗ trợ bằng option tương ứng, thường là `-H:IncludeLocales`.

Ví dụ muốn đưa dữ liệu locale tiếng Việt và tiếng Anh vào native executable:

~~~text
-H:IncludeLocales=vi,en
~~~

Đây là ví dụ cho các phiên bản Native Image hỗ trợ option này. Cú pháp và danh sách locale được hỗ trợ phụ thuộc GraalVM release; xác minh bằng help/options của đúng toolchain trước khi đưa vào pipeline.

### Cấu hình với Maven Native Build Tools

Trong cấu hình `native-maven-plugin`, có thể truyền build argument:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:IncludeLocales=vi,en</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Nếu project đã có plugin configuration, thêm build argument vào cấu hình hiện tại thay vì khai báo plugin trùng lặp. Kiểm tra log native-image để xác nhận argument được truyền tới compiler.

### Cấu hình với Gradle Native Build Tools

Ví dụ Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:IncludeLocales=vi,en")
        }
    }
}
~~~

Tên binary và DSL có thể khác tùy phiên bản plugin; kiểm tra Gradle Native Build Tools đang dùng và log task compile. Nếu dự án dùng Kotlin DSL, chuyển cấu hình theo API typed của plugin.

**Lưu ý:** `-H:IncludeLocales` bổ sung locale data của JDK; nó không thay thế `hints.resources().registerResourceBundle(...)` cho bundle thông điệp ứng dụng. Ngược lại, ResourceBundleHints không bảo đảm các API định dạng ngày/số có đủ locale data.

## 8. Định dạng số, tiền tệ và ngày theo locale

Khi ứng dụng hiển thị dữ liệu, cùng một giá trị có thể được trình bày khác nhau theo locale:

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.Locale;

public class LocaleFormattingExample {

    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale us = Locale.forLanguageTag("en-US");

        NumberFormat vietnamNumber = NumberFormat.getNumberInstance(vietnam);
        NumberFormat usNumber = NumberFormat.getNumberInstance(us);

        NumberFormat vietnamCurrency =
                NumberFormat.getCurrencyInstance(vietnam);
        vietnamCurrency.setCurrency(Currency.getInstance("VND"));

        DateTimeFormatter vietnamDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(vietnam);

        LocalDate date = LocalDate.of(2026, 11, 23);

        System.out.println("vi number=" + vietnamNumber.format(1234567.89));
        System.out.println("en number=" + usNumber.format(1234567.89));
        System.out.println("vi currency=" + vietnamCurrency.format(125000));
        System.out.println("vi date=" + vietnamDate.format(date));
    }
}
~~~

Không nên ghi cứng kết quả chuỗi định dạng vào test nếu JDK/CLDR version có thể thay đổi cách viết dấu phân cách, khoảng trắng hoặc ký hiệu tiền tệ. Thay vào đó:

- Kiểm tra locale được sử dụng đúng.
- Kiểm tra loại định dạng và currency code.
- Ghi rõ JDK/GraalVM version khi snapshot kết quả hiển thị.
- Nếu sản phẩm cần format chính xác theo hợp đồng, dùng test fixture phù hợp với version và chính sách nâng cấp.

Với native executable, hãy chạy cùng đoạn code trên binary và so sánh với JVM cùng toolchain. Nếu locale không được bao gồm, API có thể dùng fallback hoặc dữ liệu rút gọn tùy phiên bản; không suy đoán từ việc bundle thông điệp đã hiển thị đúng.

## 9. Xác định locale đầu vào và fallback ổn định

Một ứng dụng server thường phục vụ nhiều người dùng cùng lúc. Tránh thay đổi global default locale theo request bằng `Locale.setDefault(...)`; điều này có thể ảnh hưởng thread và toàn bộ tiến trình.

Nên truyền locale theo request hoặc context:

~~~java
public String messageFor(String code, Object[] args, Locale locale) {
    return messageSource.getMessage(code, args, locale);
}
~~~

Một số nguồn locale phổ biến:

| Nguồn | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- |
| `Accept-Language` | Chuẩn HTTP, client tự gửi preference | Parse header, chất lượng ưu tiên và locale không hỗ trợ |
| User profile | Giữ lựa chọn ngôn ngữ giữa các phiên | Xác thực giá trị và ưu tiên so với header |
| Cookie/session | Hữu ích cho giao diện web | Thời hạn, quyền riêng tư và fallback |
| Cấu hình server | Dùng cho tác vụ nền hoặc thông báo hệ thống | Không dùng làm locale chung cho mọi request |

Hãy xác định một thứ tự ưu tiên rõ ràng, ví dụ user preference → Accept-Language → locale mặc định của sản phẩm. Chuẩn hóa locale bằng BCP 47 language tags như `vi-VN`, `en-US`; không tự ghép chuỗi locale theo định dạng tùy ý.

### Fallback policy gợi ý

Giả sử sản phẩm hỗ trợ `vi` và `en`:

1. Nếu user chọn `vi-VN`, dùng bundle `vi_VN` nếu có.
2. Nếu không có, dùng `vi`.
3. Nếu key vẫn thiếu, dùng bundle gốc hoặc thông báo fallback đã quy định.
4. Nếu locale không được hỗ trợ, chuyển sang locale mặc định sản phẩm (ví dụ `en`).
5. Ghi nhận lỗi thiếu message key trong test/CI, không để lỗi chỉ xuất hiện ở production.

Không dùng ngôn ngữ của máy build làm fallback cho người dùng. Locale mặc định nên là quyết định sản phẩm có thể kiểm thử, không phải hệ quả ngẫu nhiên của container image.

## 10. Kiểm thử ResourceBundle và locale trên Native Image

Một test JVM thành công chỉ chứng minh classpath/runtime JVM hiện tại đọc được bundle. Cần kiểm tra native executable sau khi AOT và Native Image compilation hoàn tất.

### Kiểm thử ResourceBundle trực tiếp

~~~java
@Test
void loadsVietnameseBundle() {
    Locale locale = Locale.forLanguageTag("vi-VN");

    ResourceBundle bundle =
            ResourceBundle.getBundle("i18n.messages", locale);

    assertEquals("Xin chào, Lan!", 
            new MessageFormat(bundle.getString("greeting"), locale)
                    .format(new Object[] { "Lan" }));
}
~~~

Test giả định bundle `messages_vi.properties` có pattern `Xin chào, {0}!`. Nếu `messages_vi_VN.properties` có key này, nó sẽ được ưu tiên. Hãy kiểm tra kết quả theo file bundle và fallback policy thật của project.

### Kiểm thử Spring MessageSource

~~~java
@SpringBootTest
class GreetingMessageTests {

    @Autowired
    MessageSource messageSource;

    @Test
    void resolvesVietnameseMessage() {
        String message = messageSource.getMessage(
                "greeting",
                new Object[] { "Lan" },
                Locale.forLanguageTag("vi-VN")
        );

        assertEquals("Xin chào, Lan!", message);
    }
}
~~~

Test này kiểm tra tích hợp Spring message source, basename và locale. Nếu bundle gốc có nội dung khác, hãy dùng expected value phù hợp với fixture đã chọn.

### Kiểm thử trên native executable

Tối thiểu nên có các kịch bản:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Bundle gốc | Native tìm thấy base bundle |
| Locale `vi` | Nội dung tiếng Việt được chọn |
| Locale `vi-VN` | Bundle khu vực được ưu tiên nếu có |
| Locale `en-US` | Nội dung tiếng Anh đúng |
| Thiếu key | Fallback đúng chính sách |
| Locale không hỗ trợ | Chuyển về default locale đã quy định |
| MessageFormat | Tham số được thay thế đúng |
| Number/date formatting | JDK locale data có trong native image |
| HTTP Accept-Language | Locale resolver chuyển locale đúng cho MessageSource |

Đưa các test quan trọng vào native integration test hoặc khởi chạy executable rồi gọi endpoint. Chỉ test JVM không chứng minh resource bundle đã được đóng gói vào native image.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JVM tìm thấy bundle nhưng native báo thiếu bundle | Thiếu resource bundle metadata hoặc hint không được AOT phát hiện | Kiểm tra base name và registrar, xác minh native build nhận hints |
| Luôn trả nội dung bundle gốc | Không có file locale phù hợp, sai tên file hoặc locale đầu vào không đúng | Kiểm tra messages_vi.properties, base name và locale tag |
| Chạy trên máy dev ra tiếng Việt, container lại ra tiếng Anh | Default locale/fallback phụ thuộc môi trường | Truyền locale rõ ràng và cấu hình fallback-to-system-locale |
| Thông điệp hiển thị đúng nhưng ngày/số sai locale | Bundle có mặt nhưng JDK locale data chưa được đưa vào native | Kiểm tra -H:IncludeLocales và GraalVM version |
| Resource pattern không giải quyết được bundle | Đăng ký nhầm loại metadata | Dùng registerResourceBundle cho ResourceBundle; dùng pattern cho resource path |
| Spring MessageSource không tìm thấy message | Basename sai, thiếu bundle gốc hoặc key không tồn tại | Kiểm tra spring.messages.basename, file và message code |
| Tiếng Việt lỗi dấu | Encoding không đồng nhất | Lưu properties UTF-8 và kiểm tra encoding ở build/runtime |
| Native build báo locale option không hợp lệ | Option khác theo GraalVM version hoặc locale không hỗ trợ | Kiểm tra native-image help và release notes của toolchain |
| Test JVM pass nhưng native fail | Chưa chạy test trên native hoặc hints chưa được đưa vào binary | Thêm native integration test, build lại sau khi sửa hints |

### Quy trình điều tra

1. Xác định code đang dùng `ResourceBundle` trực tiếp hay Spring `MessageSource`.
2. Xác định base name, locale tag và chính xác file bundle được kỳ vọng.
3. Kiểm tra bundle gốc và các file locale có trong resources của build.
4. Kiểm tra `registerResourceBundle` đã được đăng ký và registrar được Spring AOT phát hiện.
5. Nếu lỗi thuộc định dạng ngày/số, kiểm tra locale data và build argument riêng.
6. Build lại native executable rồi chạy cùng payload/locale gây lỗi.
7. Kiểm tra fallback policy để loại trừ ảnh hưởng từ default locale của host.

## 12. Bài thực hành: hỗ trợ tiếng Việt và tiếng Anh trong native executable

Tạo ứng dụng Spring Boot có một endpoint `GET /greeting` trả thông điệp theo `Accept-Language`. Chuẩn bị:

- `i18n/messages.properties`: bundle gốc.
- `i18n/messages_vi.properties`: tiếng Việt.
- `i18n/messages_en.properties`: tiếng Anh.
- Một service dùng `MessageSource`.
- Một configuration đăng ký `RuntimeHintsRegistrar` cho base name `i18n.messages`.
- Cấu hình native build để đưa locale data `vi,en` vào binary nếu ứng dụng dùng các API format ngày/số tương ứng.

Thực hiện:

1. Chạy ứng dụng trên JVM và gửi request với `Accept-Language: vi-VN`, `en-US`.
2. Kiểm tra message code, tham số và fallback khi key thiếu.
3. Build native executable bằng Maven hoặc Gradle đã cấu hình Spring AOT.
4. Gửi cùng request vào bản native, so sánh nội dung và HTTP status.
5. Gọi thêm một endpoint thử định dạng số/ngày bằng `NumberFormat` và `DateTimeFormatter`.
6. Thử chạy container có default locale khác máy dev; xác minh kết quả vẫn theo locale request.
7. Tắt hoặc bỏ hint trong một nhánh thử nghiệm để hiểu cách lỗi resource bundle xuất hiện; sau đó khôi phục cấu hình đúng và build lại.
8. Ghi lại Spring Boot, GraalVM version, locale list, bundle base names và kết quả native test.

### Câu hỏi tự kiểm tra

1. Locale khác ResourceBundle ở điểm nào?
2. Vì sao cần bundle gốc `messages.properties`?
3. `ResourceBundleHints` khác resource pattern hints như thế nào?
4. Vì sao đăng ký `i18n.messages` không bảo đảm `NumberFormat` có đủ dữ liệu tiếng Việt?
5. `-H:IncludeLocales=vi,en` giải quyết vấn đề nào?
6. Tại sao không nên dùng default locale của container làm ngôn ngữ người dùng?
7. Nếu ứng dụng chỉ dùng Spring MessageSource, vì sao cần xác định implementation message source trước khi chọn hints?
8. Làm thế nào chứng minh bundle và locale data thực sự hoạt động trong native executable?

**Tiêu chí đạt:** tổ chức được ResourceBundle theo base name và locale; giải thích được candidate lookup/fallback; tích hợp MessageSource với Spring Boot; đăng ký resource bundle bằng RuntimeHints; phân biệt bundle messages với JDK locale data; cấu hình locale cần thiết cho Native Image; và kiểm thử được đa ngôn ngữ, định dạng ngày/số trên chính native executable.
