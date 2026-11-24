# Bổ sung template, resource bundle và tài nguyên đọc qua ClassLoader

Một ứng dụng Spring Boot có thể chạy bình thường trên JVM nhưng gặp lỗi khi chuyển sang GraalVM Native Image: trang Thymeleaf không tìm thấy template, thông báo tiếng Việt rơi về message mặc định, hoặc một file cấu hình đọc bằng `ClassLoader.getResourceAsStream()` trả về `null`. Nguyên nhân thường nằm ở cách native executable đóng gói tài nguyên.

Native Image phân tích ứng dụng tại build time. Các file trên classpath không mặc nhiên được đưa hết vào executable; những tài nguyên được truy cập qua tên động hoặc cơ chế lookup mà compiler không suy ra được cần được khai báo bằng **runtime hints**. Bài thực hành này ghép ba tình huống trong một ứng dụng Spring Boot: render template, tra cứu resource bundle theo locale và đọc file theo đường dẫn được tạo lúc chạy.

Bài học thuộc chương **Thực hành tổng hợp** của module **`SPRING_BOOT_NATIVE_IMAGE`**. Module hướng dẫn biên dịch Spring Boot thành GraalVM Native Image bằng Spring AOT để đánh giá startup và memory, thực hành Maven/Gradle, cấu hình reflection/resource, kiểm thử tương thích, đóng gói container và vận hành bản native.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Đặt template, message bundle và dữ liệu classpath vào đúng vị trí trong `src/main/resources`.
- Cấu hình Thymeleaf và Spring Boot `MessageSource` cho nhiều ngôn ngữ.
- Dùng `ClassLoader.getResourceAsStream()` để đọc tài nguyên có tên được tạo từ locale.
- Phân biệt resource pattern với resource bundle hint.
- Đăng ký tài nguyên bằng `RuntimeHintsRegistrar` và `@ImportRuntimeHints`.
- Kiểm thử các hint bằng `RuntimeHintsPredicates`.
- Build và chạy native executable để xác nhận tài nguyên thực sự có mặt trong sản phẩm.

## 2. Bài toán thực hành

Ta xây dựng endpoint hiển thị biên nhận đơn hàng:

`GET /orders/{orderId}/receipt`

Khi nhận request, ứng dụng:

1. Chọn template `orders/receipt.html` để render HTML.
2. Lấy tiêu đề và chân trang từ resource bundle `messages`, theo locale của request.
3. Đọc chính sách giao hàng từ file `catalog/vi/shipping-policy.txt` hoặc `catalog/en/shipping-policy.txt` qua `ClassLoader`.

Trong JVM, classpath thường chứa các file tài nguyên nên việc lookup có thể hoạt động mà không cần cấu hình bổ sung. Khi build native, ta khai báo những tài nguyên mà ba luồng trên cần.

## 3. Cấu trúc tài nguyên của project

Ví dụ dùng Spring MVC và Thymeleaf. Thêm `spring-boot-starter-web` và `spring-boot-starter-thymeleaf` vào project; dependency test dùng `spring-boot-starter-test`.

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/orders/
    │       ├── OrdersApplication.java
    │       ├── ReceiptController.java
    │       ├── ReceiptView.java
    │       ├── ReceiptLabelService.java
    │       ├── ShippingPolicyReader.java
    │       └── OrderResourceHints.java
    └── resources/
        ├── application.properties
        ├── messages.properties
        ├── messages_vi.properties
        ├── templates/
        │   └── orders/
        │       └── receipt.html
        └── catalog/
            ├── en/
            │   └── shipping-policy.txt
            └── vi/
                └── shipping-policy.txt
~~~

Spring Boot tự tìm template của các engine được hỗ trợ trong `src/main/resources/templates` khi dùng cấu hình mặc định. Với Thymeleaf, view name `orders/receipt` thường được ánh xạ tới `classpath:/templates/orders/receipt.html`.

Không đặt các file cần đóng gói vào `src/main/webapp` cho ứng dụng executable JAR. Hãy đặt template và dữ liệu classpath trong `src/main/resources`.

## 4. Cấu hình Spring Boot message source

Trong `application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
spring.thymeleaf.encoding=UTF-8
~~~

Spring Boot mặc định tìm resource bundle có base name `messages` ở classpath root. File mặc định `messages.properties` rất quan trọng: nếu chỉ có các file theo ngôn ngữ như `messages_vi.properties` mà thiếu file mặc định, auto-configuration có thể không tạo `MessageSource`.

Tạo `messages.properties` làm bản fallback:

~~~properties
receipt.title=Order receipt
receipt.footer=Thank you for your order.
~~~

Tạo `messages_vi.properties`:

~~~properties
receipt.title=Phiếu xác nhận đơn hàng
receipt.footer=Cảm ơn bạn đã mua hàng.
~~~

Spring Boot phân giải message theo locale và basename đã cấu hình. `fallback-to-system-locale=false` giúp `MessageSource` không tự rơi về locale của máy chạy khi không tìm thấy bản dịch; file `messages.properties` vẫn là fallback mặc định.

Nếu có thêm bundle khác, có thể liệt kê nhiều basename:

~~~properties
spring.messages.basename=messages,config.i18n.labels
~~~

## 5. Tạo template Thymeleaf

File `src/main/resources/templates/orders/receipt.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{receipt.title}">Order receipt</title>
</head>
<body>
    <main>
        <h1 th:text="#{receipt.title}">Order receipt</h1>
        <p>
            Order:
            <strong th:text="${receipt.orderId}">ORD-100</strong>
        </p>
        <section>
            <h2>Shipping policy</h2>
            <p th:text="${receipt.shippingPolicy}">
                Shipping policy text
            </p>
        </section>
        <footer th:text="${footer}">Thank you for your order.</footer>
    </main>
</body>
</html>
~~~

Các biểu thức `#{...}` lấy message từ Spring `MessageSource`; ${...} đọc thuộc tính trong model. Template được chọn bằng view name từ controller, còn nội dung HTML được template engine đọc khi render.

Một template được tham chiếu bằng chuỗi view name có thể không được compiler suy ra như lời gọi `Class.getResourceAsStream()` với đường dẫn hằng. Nếu ứng dụng tự quản lý template path hoặc template được chọn động, hãy đăng ký pattern tương ứng và kiểm tra trên native executable.

## 6. Đọc message bằng ResourceBundle

Spring `MessageSource` phù hợp với bean/controller và biểu thức message trong Thymeleaf. Nếu một thư viện hoặc đoạn code Java cần dùng trực tiếp `java.util.ResourceBundle`, có thể đọc cùng base name:

~~~java
package com.example.orders;

import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.stereotype.Component;

@Component
public class ReceiptLabelService {

    public String footer(Locale locale) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", locale, getClass().getClassLoader());
        return bundle.getString("receipt.footer");
    }
}
~~~

Base name là `messages`, không có phần mở rộng `.properties` và không kèm hậu tố `_vi`. JDK tự tìm file phù hợp với locale, chẳng hạn `messages_vi.properties`, rồi áp dụng quy tắc fallback của `ResourceBundle`.

Thuộc tính `spring.messages.fallback-to-system-locale` chỉ điều khiển Spring Boot `MessageSource`. Lời gọi Java trực tiếp `ResourceBundle.getBundle()` vẫn tuân theo quy tắc fallback của JDK; nếu cần kiểm soát fallback đồng nhất trong toàn ứng dụng, ưu tiên inject và dùng `MessageSource` thay vì trộn hai cơ chế.

Native Image cần biết trước những bundle mà ứng dụng sẽ tra cứu. Đăng ký bundle bằng `registerResourceBundle("messages")`; chỉ đăng ký một pattern file `.properties` không thay thế cho resource bundle hint.

Nếu ứng dụng dùng locale data của JDK như định dạng ngày, số hoặc tiền tệ cho các locale ngoài tập mặc định, kiểm tra cấu hình locale của Native Image và cân nhắc `-H:IncludeLocales=vi,en`. Locale data của JDK và việc đăng ký resource bundle là hai phần cấu hình có liên quan nhưng khác nhau.

## 7. Đọc tài nguyên có tên động qua ClassLoader

File `src/main/resources/catalog/vi/shipping-policy.txt`:

~~~text
Đơn hàng nội thành được giao trong một đến hai ngày làm việc.
~~~

File `src/main/resources/catalog/en/shipping-policy.txt`:

~~~text
Local orders are delivered within one to two business days.
~~~

Tạo `ShippingPolicyReader`:

~~~java
package com.example.orders;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.stereotype.Component;

@Component
public class ShippingPolicyReader {

    private final ClassLoader classLoader =
            ShippingPolicyReader.class.getClassLoader();

    public String read(Locale locale) {
        String language = "vi".equals(locale.getLanguage()) ? "vi" : "en";
        String resourcePath =
                "catalog/" + language + "/shipping-policy.txt";

        try (InputStream input =
                     classLoader.getResourceAsStream(resourcePath)) {
            if (input == null) {
                throw new IllegalStateException(
                        "Classpath resource not found: " + resourcePath);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        catch (IOException ex) {
            throw new UncheckedIOException(
                    "Cannot read " + resourcePath, ex);
        }
    }
}
~~~

Đường dẫn ở đây được tạo từ locale nên static analysis không thể suy ra chính xác file nào sẽ được mở. Pattern hint `catalog/**` sẽ bao phủ hai file trong ví dụ.

Chú ý quy tắc đường dẫn:

| API | Cách truyền tên tài nguyên |
|---|---|
| `ClassLoader.getResourceAsStream("catalog/vi/shipping-policy.txt")` | Không có dấu `/` đầu chuỗi; đường dẫn tính từ classpath root |
| `SomeClass.class.getResourceAsStream("/catalog/vi/shipping-policy.txt")` | Có `/` đầu chuỗi để chỉ classpath root |
| `SomeClass.class.getResourceAsStream("shipping-policy.txt")` | Đường dẫn tương đối với package của class |

Không ghép trực tiếp chuỗi do người dùng gửi vào đường dẫn tài nguyên. Hãy ánh xạ input sang một tập giá trị được cho phép như `vi` và `en`, tránh path traversal hoặc truy cập file ngoài dự kiến.

### ClassLoader và Spring ResourceLoader

Nếu muốn dùng abstraction của Spring, có thể inject `ResourceLoader`:

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:catalog/vi/shipping-policy.txt");
try (InputStream input = resource.getInputStream()) {
    // Đọc nội dung resource
}
~~~

Khi cần lấy nhiều tài nguyên từ các JAR dependency, dùng `ResourcePatternResolver`:

~~~java
Resource[] resources =
        resourcePatternResolver.getResources("classpath*:catalog/**/*.txt");
~~~

`classpath:` chỉ một vị trí classpath được phân giải; `classpath*:` tìm các tài nguyên phù hợp trên toàn bộ classpath. Đây là cú pháp của Spring resource resolver, không phải cú pháp truyền cho `RuntimeHints.registerPattern`. Trong ví dụ trên, hint vẫn dùng đường dẫn classpath như `catalog/**`.

## 8. Đăng ký resource hints bằng RuntimeHintsRegistrar

Tạo `OrderResourceHints.java`:

~~~java
package com.example.orders;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/**");
        hints.resources().registerPattern("catalog/**");
        hints.resources().registerResourceBundle("messages");

        // Thymeleaf đọc các getter của model thông qua property access.
        hints.reflection().registerType(
                ReceiptView.class, MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
~~~

Các pattern là đường dẫn tương đối với classpath root và không bắt đầu bằng `/`:

- `templates/**` bao phủ template trong thư mục `templates` và các thư mục con.
- `catalog/**` bao phủ các file chính sách theo locale.
- `registerResourceBundle("messages")` đăng ký bundle theo base name.
- Reflection hint cho `ReceiptView` cần thiết nếu template truy cập getter của model thông qua property access và AOT không suy ra được việc gọi đó.

Tạo `ReceiptView.java`:

~~~java
package com.example.orders;

public class ReceiptView {

    private final String orderId;
    private final String shippingPolicy;

    public ReceiptView(String orderId, String shippingPolicy) {
        this.orderId = orderId;
        this.shippingPolicy = shippingPolicy;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getShippingPolicy() {
        return shippingPolicy;
    }
}
~~~

Khai báo registrar trong application:

~~~java
package com.example.orders;

import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ImportRuntimeHints(OrderResourceHints.class)
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`@ImportRuntimeHints` khiến Spring AOT gọi registrar trong quá trình xử lý build. Các hint được chuyển thành metadata mà Native Image sử dụng; không cần tự gọi `registerHints()` khi ứng dụng chạy.

Một số starter và thư viện có thể đã cung cấp reachability metadata cho phần nội bộ của chúng. Hãy kiểm tra metadata do dependency đóng góp và AOT output trước khi thêm hint trùng lặp. Những tài nguyên do ứng dụng tự quản lý, đặc biệt đường dẫn được tạo động, vẫn cần được kiểm kê và kiểm thử.

## 9. Vì sao resource pattern và resource bundle phải tách riêng?

`registerPattern` khai báo file tài nguyên thông thường. `registerResourceBundle` khai báo bundle mà `ResourceBundle.getBundle()` tra cứu theo base name và locale.

| Tài nguyên | Ví dụ | Hint |
|---|---|---|
| Thymeleaf template | `templates/orders/receipt.html` | `registerPattern("templates/**")` |
| File ClassLoader | `catalog/vi/shipping-policy.txt` | `registerPattern("catalog/**")` |
| Java resource bundle | `messages.properties`, `messages_vi.properties` | `registerResourceBundle("messages")` |
| Một bundle khác | `config/i18n/labels.properties` | `registerResourceBundle("config.i18n.labels")` |

Đăng ký `registerPattern("*.properties")` không tương đương với đăng ký bundle. Ngược lại, đăng ký bundle không tự bao phủ template hoặc file text đọc qua `ClassLoader`.

Spring `ResourceHints.registerPattern` dùng pattern theo quy tắc của Spring Framework. Dùng `*`/`**` có chủ đích và chỉ bao phủ thư mục ứng dụng cần thiết; tránh thêm toàn bộ classpath nếu không có lý do vì điều đó làm tăng kích thước executable.

## 10. Kết nối các thành phần bằng controller

`ReceiptController.java`:

~~~java
package com.example.orders;

import java.util.Locale;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class ReceiptController {

    private final ShippingPolicyReader policyReader;
    private final ReceiptLabelService labelService;

    public ReceiptController(
            ShippingPolicyReader policyReader,
            ReceiptLabelService labelService) {
        this.policyReader = policyReader;
        this.labelService = labelService;
    }

    @GetMapping("/orders/{orderId}/receipt")
    public String showReceipt(
            @PathVariable String orderId, Locale locale, Model model) {

        String policy = policyReader.read(locale);
        model.addAttribute("receipt",
                new ReceiptView(orderId, policy));
        model.addAttribute("footer", labelService.footer(locale));
        return "orders/receipt";
    }
}
~~~

Với request có `Accept-Language: vi`, Spring MVC cung cấp locale phù hợp cho controller; reader chọn file tiếng Việt, còn resource bundle trả về message tiếng Việt. Thymeleaf render template `orders/receipt`.

## 11. Kiểm thử runtime hints

Tạo unit test cho registrar:

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderResourceHintsTests {

    @Test
    void registersApplicationResources() {
        RuntimeHints hints = new RuntimeHints();
        new OrderResourceHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("templates/orders/receipt.html"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("catalog/vi/shipping-policy.txt"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forBundle("messages"))
                .accepts(hints);
    }
}
~~~

Test này xác nhận registrar đã khai báo các hint mong đợi. Nó không chứng minh template hoặc file đã được đóng gói vào native executable. Cần có thêm kiểm thử tích hợp trên chính binary native.

Có thể kiểm tra tài nguyên tồn tại trên classpath khi chạy JVM:

~~~java
@Test
void resourcesAreOnTheClasspath() {
    ClassLoader loader = getClass().getClassLoader();
    assertThat(loader.getResource(
            "catalog/vi/shipping-policy.txt")).isNotNull();
    assertThat(loader.getResource(
            "templates/orders/receipt.html")).isNotNull();
}
~~~

Kiểm thử classpath này phát hiện lỗi đặt sai thư mục hoặc tên file, nhưng vẫn chưa thay thế native smoke test.

## 12. Chạy thử trên JVM trước

Chạy unit test:

~~~bash
./mvnw test
~~~

Hoặc với Gradle:

~~~bash
./gradlew test
~~~

Khởi động ứng dụng trên JVM và gọi endpoint:

~~~bash
curl -H "Accept-Language: vi" \
  http://localhost:8080/orders/ORD-100/receipt

curl -H "Accept-Language: en" \
  http://localhost:8080/orders/ORD-100/receipt
~~~

Kiểm tra:

- Trang trả về HTTP 200.
- Tiêu đề và chân trang đổi theo locale.
- Mã đơn hàng xuất hiện trong trang.
- Nội dung chính sách giao hàng lấy đúng file theo locale.
- Không có lỗi `TemplateInputException`, `MissingResourceException` hoặc thông báo không tìm thấy classpath resource.

Nếu JVM test thất bại, sửa classpath, view name hoặc cấu hình locale trước khi build native. Native Image không sửa được resource path vốn đã sai trong ứng dụng.

## 13. Build Spring AOT và Native Image

Với Maven, dùng native profile đã cấu hình Spring Boot Maven Plugin và GraalVM Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

Với Gradle, dùng task `nativeCompile` khi plugin Native Build Tools đã được cấu hình:

~~~bash
./gradlew nativeCompile
~~~

Spring AOT xử lý application context và đóng góp runtime hints. Có thể xem các tài nguyên/hint được sinh trong output AOT của build:

- Maven: `target/spring-aot/main/resources/META-INF/native-image/`
- Gradle: `build/generated/aotResources/META-INF/native-image/`

Đường dẫn chi tiết có thể khác theo phiên bản plugin và cấu hình project. Chỉ đọc output để kiểm tra; không sửa trực tiếp file được sinh vì lần build tiếp theo có thể ghi đè. Hãy sửa `RuntimeHintsRegistrar`, metadata của dependency hoặc cấu hình build nguồn.

Sau khi build, tìm executable trong output native của project. Tên và đường dẫn phụ thuộc `artifactId`, `imageName` và cấu hình Maven/Gradle.

## 14. Kiểm thử trên native executable

Khởi chạy executable được build và gọi lại cùng endpoint:

~~~bash
./target/orders-service
~~~

Đường dẫn trên là ví dụ cho Maven project có artifact tên `orders-service`; với Gradle hoặc artifact khác, dùng đường dẫn output thực tế.

~~~bash
curl --fail -H "Accept-Language: vi" \
  http://localhost:8080/orders/ORD-100/receipt

curl --fail -H "Accept-Language: en" \
  http://localhost:8080/orders/ORD-100/receipt
~~~

Native test phải render template thật và đọc từng file locale. Chỉ kiểm tra endpoint health không đủ vì endpoint đó có thể không chạm tới template, resource bundle hoặc ClassLoader resource.

### Bảng kết quả cần ghi nhận

| Kiểm tra | JVM | Native Image |
|---|---|---|
| Render `orders/receipt.html` | PASS/FAIL | PASS/FAIL |
| Message tiếng Việt | PASS/FAIL | PASS/FAIL |
| Message tiếng Anh/fallback | PASS/FAIL | PASS/FAIL |
| Đọc `catalog/vi/shipping-policy.txt` | PASS/FAIL | PASS/FAIL |
| Đọc `catalog/en/shipping-policy.txt` | PASS/FAIL | PASS/FAIL |
| Không có lỗi resource/template | PASS/FAIL | PASS/FAIL |

Chỉ đánh dấu native test PASS khi chạy trên executable được build từ cấu hình release. JVM test và test `RuntimeHintsPredicates` là các lớp xác minh bổ sung, không thay cho kiểm thử native.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `TemplateInputException` hoặc template không tồn tại | Template nằm sai thư mục hoặc thiếu resource hint | Đặt dưới `src/main/resources/templates`, kiểm tra view name và `templates/**` |
| Template chạy trên JVM nhưng lỗi trên native | Template được resolve động hoặc dependency không cung cấp metadata cần thiết | Đăng ký pattern và render tất cả template trên native |
| `MissingResourceException` | Chưa đăng ký bundle hoặc sai base name | Dùng `registerResourceBundle("messages")`, kiểm tra tên bundle |
| Chỉ có `messages_vi.properties`, không có `messages.properties` | Thiếu bundle mặc định cho Spring Boot auto-configuration | Thêm file mặc định ở classpath root |
| `ClassLoader.getResourceAsStream()` trả về `null` | Sai đường dẫn, có dấu `/` đầu chuỗi hoặc resource chưa được đóng gói | Kiểm tra path từ classpath root và đăng ký `catalog/**` |
| JVM đọc được nhưng native không đọc được file locale | Tên file được tạo động nên không được suy ra khi build | Đăng ký pattern bao phủ các locale được hỗ trợ |
| Bundle trả về ngôn ngữ không mong muốn | Locale request, fallback hoặc default locale không như dự kiến | Kiểm tra `Accept-Language`, file mặc định và fallback policy |
| Lỗi khi dùng `URL.getFile()` | Resource trong native executable có thể có URL scheme `resource:` chứ không phải `file:` | Dùng `getResourceAsStream()`/`openStream()` |
| File có trong builder nhưng không có trong image cuối | Docker build context hoặc bước đóng gói đã bỏ resource | Kiểm tra artifact và final image; giữ resource trong classpath build |
| Thymeleaf báo lỗi truy cập thuộc tính model | Type chỉ được tham chiếu trong template nên reflection hint chưa đủ | Đăng ký member cần thiết cho model type và test lại native |

## 16. Không giả định classpath resource là file hệ thống

Trong native executable, tài nguyên được nhúng có thể được trả về dưới dạng URL với scheme `resource:`. Vì vậy, đoạn code sau không portable:

~~~java
URL url = getClass().getClassLoader().getResource("catalog/vi/shipping-policy.txt");
File file = new File(url.getFile());
~~~

Nó giả định tài nguyên luôn có đường dẫn file thực trên filesystem. Hãy đọc stream:

~~~java
try (InputStream input = getClass().getClassLoader()
        .getResourceAsStream("catalog/vi/shipping-policy.txt")) {
    // Đọc bytes hoặc text từ stream
}
~~~

Nếu API bên thứ ba bắt buộc nhận một file path, hãy copy resource ra file tạm ở runtime, kiểm soát quyền và vòng đời file đó, rồi truyền đường dẫn tạm cho API. Không cố chuyển `resource:` URL thành `File`.

## 17. Khi nào dùng tracing agent?

GraalVM tracing agent có thể ghi nhận các resource, reflection và dynamic access mà ứng dụng thực sự sử dụng khi chạy JVM. Có thể dùng agent trong integration test:

~~~bash
java -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-service.jar
~~~

Sau đó chạy các luồng có render template, tra cứu từng locale và đọc mọi loại tài nguyên cần hỗ trợ. Agent chỉ ghi nhận đường đi đã được thực thi. Nếu test không render template email hoặc không chọn locale `vi`, metadata tương ứng có thể không xuất hiện.

Dùng output của agent như bằng chứng khám phá và đối chiếu. Với ứng dụng Spring, `RuntimeHintsRegistrar` thường là nơi phù hợp để quản lý hint có chủ đích cùng code. Không chép mù toàn bộ cấu hình agent vào release mà chưa review.

## 18. Checklist hoàn thành bài thực hành

- [ ] Template nằm trong `src/main/resources/templates`.
- [ ] Có `messages.properties` mặc định và file locale cần hỗ trợ.
- [ ] Cấu hình `spring.messages.basename` và encoding phù hợp.
- [ ] Tài nguyên ClassLoader nằm trong `src/main/resources/catalog`.
- [ ] Đường dẫn động chỉ được tạo từ locale/giá trị đã allowlist.
- [ ] Có `RuntimeHintsRegistrar` đăng ký `templates/**`.
- [ ] Có pattern hint cho các file `catalog/**`.
- [ ] Có resource bundle hint cho base name `messages`.
- [ ] Có reflection hint nếu template đọc model property qua reflection và AOT không suy ra được.
- [ ] Unit test kiểm tra `RuntimeHintsPredicates`.
- [ ] JVM test render được template và đọc được mọi tài nguyên.
- [ ] Native executable render được template và đọc được mọi locale.
- [ ] Không dùng `URL.getFile()` để đọc resource nhúng.
- [ ] Kiểm tra output AOT/native metadata khi cần chẩn đoán.

## 19. Bài tập mở rộng

**Bài 1 — Thêm email template:** tạo `templates/mail/receipt-notice.html`, bổ sung luồng render email và xác minh template đó có trong native executable.

**Bài 2 — Thêm locale:** bổ sung `messages_ja.properties` và `catalog/ja/shipping-policy.txt`. Cập nhật allowlist locale, hints và test native cho tiếng Nhật.

**Bài 3 — Nhiều bundle:** tạo `config/i18n/labels.properties` cùng bản dịch locale. Đăng ký `config.i18n.labels` và đọc bằng `ResourceBundle.getBundle()`.

**Bài 4 — ResourcePatternResolver:** đặt nhiều file quy tắc trong các thư mục classpath khác nhau, dùng `classpath*:` để đọc tất cả. Đăng ký pattern bao phủ các file cần thiết và xác minh từng file trong native.

**Bài 5 — Kiểm tra reflection của template:** chuyển các thuộc tính model từ chuỗi đơn sang DTO. Quan sát lỗi native nếu thiếu hint, sau đó chỉ đăng ký public getter cần thiết và chạy lại integration test.

## 20. Tài liệu tham khảo

- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, kiểm thử custom hints và static metadata.
- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): runtime hints cho reflection, resources, resource bundles và các giới hạn AOT.
- [Spring Framework — ResourceHints API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aot/hint/ResourceHints.html): `registerPattern`, `registerResourceBundle` và `registerPatternIfPresent`.
- [Spring Framework — ResourcePatternHint API](https://docs.spring.io/spring-framework/docs/6.0.20/javadoc-api/org/springframework/aot/hint/ResourcePatternHint.html): quy tắc pattern cho resource hint.
- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): `ResourceLoader`, `ResourcePatternResolver`, `classpath:` và `classpath*:`.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html): basename mặc định `messages`, file mặc định và cấu hình locale.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): template engines và vị trí template mặc định.
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): resource metadata, resource bundles, locale và URL `resource:` trong native executable.
- [GraalVM — Include Resources in a Native Executable](https://www.graalvm.org/dev/reference-manual/native-image/guides/include-resources/): cách đưa classpath resources vào executable và kiểm tra build report.

**Ghi nhớ:** Template, resource bundle và file đọc qua ClassLoader là ba dạng tài nguyên khác nhau. Hãy đăng ký đúng pattern cho file, đúng base name cho bundle, thêm reflection hint khi template truy cập model bằng reflection, rồi kiểm thử trên chính native executable. Thành công trên JVM chỉ xác nhận classpath của JVM; native smoke test mới xác nhận tài nguyên đã được đóng gói và truy cập đúng khi vận hành.
