# ResourceHints cho tệp, mẫu đường dẫn và resource bundle

## 1. Vì sao Native Image cần resource hints?

Ứng dụng Spring Boot thường đọc tài nguyên ngoài bytecode: file JSON/YAML, template HTML, schema, file cấu hình mặc định, ảnh, chứng chỉ, message bundle và dữ liệu đi kèm thư viện. Khi chạy trên JVM, ứng dụng có thể tìm chúng qua classpath hoặc filesystem tại runtime. Nhưng **GraalVM Native Image phân tích khả năng truy cập tại build time**; một tệp được chọn bằng chuỗi hoặc pattern động có thể không được đưa vào executable nếu trình phân tích không nhận ra đường truy cập đó.

Spring AOT và Runtime Hints cung cấp cách mô tả các resource mà ứng dụng cần. Trong nhóm hints, **ResourceHints** giúp khai báo:

- Một hoặc nhiều **classpath resource** cần có trong native executable.
- **Mẫu đường dẫn** để bao gồm một nhóm resource được chọn theo quy tắc.
- **Resource bundle** chứa các chuỗi thông điệp theo ngôn ngữ/locale.

Bài này thuộc chương **Runtime hints** của module **SPRING_BOOT_NATIVE_IMAGE**. Mục tiêu là xác định đúng loại resource, đăng ký hint ở đúng nơi, kiểm thử metadata và xác minh ứng dụng đọc được tài nguyên trên chính native executable.

> Resource hint áp dụng cho resource được đóng gói trong classpath/image. Nó không tự copy file cấu hình bên ngoài, file mount từ volume hay dữ liệu runtime vào container.

## 2. Phân biệt classpath resource và file hệ thống

Hai loại resource có vòng đời khác nhau và cần cách xử lý khác nhau.

| Loại | Ví dụ | Cách truy cập thường gặp | Cách bảo đảm có dữ liệu khi chạy |
| --- | --- | --- | --- |
| Classpath resource trong ứng dụng | `src/main/resources/rules/pricing.json` | `ClassPathResource`, `ClassLoader.getResourceAsStream` | Đóng gói vào JAR và đăng ký resource hint nếu Native Image cần |
| Classpath resource trong dependency | `META-INF/library/defaults.json` | Thư viện đọc qua classloader | Kiểm tra metadata của dependency; bổ sung hint nếu thiếu |
| Resource bundle | `messages.properties`, `messages_vi.properties` | `ResourceBundle`, `MessageSource` | Đăng ký bundle theo base name và kiểm tra locale |
| File ngoài container | `/etc/myapp/application.yml` | `Files`, `FileSystemResource`, `file:` | Mount/copy file vào runtime filesystem và cấp quyền đọc |
| Secret/config từ nền tảng | Kubernetes Secret/ConfigMap, secret store | Environment, volume, API của nền tảng | Cấp tại runtime theo chính sách vận hành |

Ví dụ một classpath resource:

```text
src/main/resources/
  rules/
    pricing.json
  templates/
    invoice.html
  i18n/
    messages.properties
    messages_vi.properties
    messages_en.properties
```

Sau khi build JAR, các resource trong `src/main/resources` thường được đóng gói ở đường dẫn tương ứng bên trong JAR. Native Image có quy trình phân tích và đóng gói riêng; **không suy luận rằng resource có trong JAR thì chắc chắn có thể đọc từ native executable**.

### 2.1. Đọc classpath resource

Với Spring, có thể dùng `ClassPathResource`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;

public class PricingRuleReader {

    public String readRules() throws IOException {
        var resource = new ClassPathResource("rules/pricing.json");

        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Hoặc dùng classloader:

```java
try (InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("rules/pricing.json")) {

    if (input == null) {
        throw new IllegalStateException("Missing classpath resource");
    }

    // Đọc nội dung resource.
}
```

Tên resource truyền cho classloader thường là đường dẫn tương đối từ classpath root, dùng dấu `/`, không có tiền tố `classpath:` và không bắt đầu bằng `/`. Với `ClassPathResource`, đường dẫn cũng được viết tương đối theo classpath. Hãy giữ đúng chữ hoa/chữ thường: môi trường Linux phân biệt `Pricing.json` và `pricing.json`.

### 2.2. Đọc file bên ngoài

Nếu ứng dụng đọc file từ volume hoặc đường dẫn do vận hành cung cấp, ví dụ:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path configPath = Path.of("/etc/myapp/pricing.json");
String json = Files.readString(configPath);
```

thì resource này **không phải classpath resource**. Khai báo `registerPattern("etc/myapp/pricing.json")` không mount hoặc copy file vào container. Cần tạo file trong image hoặc mount volume/ConfigMap/secret vào đường dẫn đó, sau đó bảo đảm user của container có quyền đọc. Không nhúng password, token hoặc private key vào resource của native executable chỉ để tránh cấu hình runtime.

## 3. ResourceHints và registerPattern

Spring cung cấp API `RuntimeHints.resources()` để đăng ký resource. Phương thức thường dùng là:

- `registerPattern(String)`: đăng ký đường dẫn hoặc pattern của classpath resource.
- `registerResourceBundle(String)`: đăng ký resource bundle theo base name.

Ví dụ với hai tệp được biết rõ:

```java
hints.resources().registerPattern("rules/pricing.json");
hints.resources().registerPattern("templates/invoice.html");
```

Với một nhóm template có quy ước tên chung, có thể dùng pattern phù hợp với cú pháp được Spring Framework/GraalVM phiên bản dự án hỗ trợ:

```java
hints.resources().registerPattern("templates/*.html");
```

Các pattern được xử lý trong quá trình chuyển Runtime Hints thành metadata cho Native Image. Trong Spring Framework 6, ký tự đặc biệt `*` khớp resource theo đường dẫn và có thể bao gồm các thư mục con ở nhiều cấp; ví dụ `templates/*.html` bao phủ các file HTML trong `templates/` và cây thư mục bên dưới. Đây là cú pháp pattern của Spring `ResourcePatternHint`, không phải shell glob. Hãy đối chiếu tài liệu đúng phiên bản Spring/GraalVM và kiểm tra metadata được sinh. Đối với resource quan trọng, **ưu tiên đăng ký chính xác đường dẫn**; chỉ mở rộng pattern khi ứng dụng thực sự đọc nhiều file thuộc nhóm đó.

### 3.1. Đường dẫn resource phải khớp với code

Giả sử code đọc:

```java
new ClassPathResource("rules/pricing.json");
```

thì hint cần mô tả resource dưới classpath root:

```java
hints.resources().registerPattern("rules/pricing.json");
```

Các lỗi thường gặp:

- Đăng ký `src/main/resources/rules/pricing.json`: đây là đường dẫn trong source tree, không phải tên resource bên trong classpath.
- Đăng ký `classpath:rules/pricing.json` trong API nhận pattern resource: tiền tố này không phải một phần tên resource classpath.
- Dùng dấu `\` thay cho `/` trong resource path.
- Bắt đầu pattern bằng `/` dù resource nằm dưới classpath root; pattern thông thường phải là đường dẫn tương đối từ root.
- Sai chữ hoa/chữ thường hoặc sai phần mở rộng.
- Chỉ đăng ký một file mặc định trong khi code còn đọc các file theo tenant/locale khác.
- Dùng pattern quá rộng, vô tình đưa nhiều tài nguyên không cần thiết vào executable.

Khi không chắc, kiểm tra tên resource trong JAR hoặc dependency, sau đó so với chuỗi được truyền vào `ClassPathResource`, `ClassLoader` hoặc API Spring tương ứng.

## 4. Đăng ký ResourceHints bằng RuntimeHintsRegistrar

Với ứng dụng Spring Boot, có thể đóng góp resource hints thông qua `RuntimeHintsRegistrar` và liên kết registrar với cấu hình bằng `@ImportRuntimeHints`.

Ví dụ đầy đủ:

```java
package com.example.demo;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PricingResourceHints.class)
class NativeResourceConfiguration {
}

final class PricingResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("rules/pricing.json");
        hints.resources().registerPattern("templates/invoice.html");
    }
}
```

Giải thích:

1. `PricingResourceHints` triển khai `RuntimeHintsRegistrar`.
2. Spring gọi `registerHints` trong quá trình chuẩn bị AOT.
3. `hints.resources()` truy cập nhóm resource hints.
4. `registerPattern` mô tả các resource mà ứng dụng cần ở runtime.
5. `@ImportRuntimeHints` liên kết registrar với cấu hình Spring được phát hiện.

Cấu hình `NativeResourceConfiguration` phải được Spring phát hiện qua component scan hoặc được import từ một cấu hình khác. Nếu lớp registrar nằm ngoài package scan và không được import, hint có thể không được đăng ký dù code compile thành công.

Không gọi registrar thủ công ở runtime để kỳ vọng thay đổi native executable. Runtime Hints là **đầu vào build time** cho quá trình tạo metadata và phân tích native.

### 4.1. Tổ chức hint theo module/tính năng

Với ứng dụng lớn, gom hints theo tính năng giúp biết resource nào thuộc thành phần nào:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints({
    PricingResourceHints.class,
    InvoiceTemplateHints.class
})
class NativeResourceConfiguration {
}
```

Một registrar cho template hóa đơn:

```java
final class InvoiceTemplateHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("templates/invoice.html");
        hints.resources().registerPattern("templates/invoice-footer.html");
    }
}
```

Mỗi registrar chỉ nên khai báo các resource mà tính năng đó thực sự sử dụng. Nếu thư viện bên thứ ba đã cung cấp Runtime Hints hoặc GraalVM reachability metadata tương thích, tránh đăng ký lặp và duy trì một danh sách không còn đúng sau khi nâng cấp dependency.

## 5. Dùng ResourceHints cho nhóm file theo pattern

Một số ứng dụng chọn resource từ cấu hình runtime, chẳng hạn tên template theo loại hóa đơn:

```java
String templateName = "templates/" + invoiceType + ".html";
var resource = new ClassPathResource(templateName);
```

Nếu `invoiceType` có thể là `standard`, `vat` hoặc `credit-note`, các resource tương ứng phải có mặt trong image. Có hai lựa chọn:

**Lựa chọn 1: đăng ký từng file đã biết**

```java
hints.resources().registerPattern("templates/standard.html");
hints.resources().registerPattern("templates/vat.html");
hints.resources().registerPattern("templates/credit-note.html");
```

Cách này rõ ràng và giới hạn phạm vi resource.

**Lựa chọn 2: đăng ký pattern cho nhóm template**

```java
hints.resources().registerPattern("templates/*.html");
```

Cách này thuận tiện khi nhóm file thay đổi thường xuyên và mọi file trong nhóm đều là resource hợp lệ của ứng dụng. Trong Spring Framework 6, `*` có thể khớp các resource trong thư mục con ở nhiều cấp; vẫn cần kiểm tra phiên bản framework và metadata đầu ra để bảo đảm phạm vi khớp đúng với dự án.

### 5.1. Pattern rộng có chi phí gì?

Một pattern quá rộng có thể đưa file không cần thiết vào image, làm tăng kích thước artifact, mở rộng dữ liệu được phân phối tới môi trường chạy và khiến việc kiểm tra metadata khó hơn. Ví dụ, đăng ký tất cả resource trong classpath có thể kéo theo schema, template, tài liệu hoặc dữ liệu của dependency mà ứng dụng không dùng.

Quy tắc lựa chọn:

| Trường hợp | Hướng đăng ký |
| --- | --- |
| Một file cấu hình mặc định | Đường dẫn chính xác |
| Một vài template cố định | Đăng ký từng resource |
| Nhóm template có quy ước ổn định | Pattern giới hạn trong thư mục/đuôi file |
| File được chọn từ danh sách cấu hình có kiểm soát | Đăng ký tất cả file hợp lệ hoặc pattern hẹp |
| File do người dùng upload sau khi deploy | Lưu trên filesystem/object storage, không dùng classpath hint |
| File bí mật hoặc thay đổi theo môi trường | Cấp qua secret/config/volume tại runtime |

Không dùng ResourceHints như một cách nhúng dữ liệu người dùng hoặc dữ liệu môi trường vào binary.

## 6. Resource bundle và đa ngôn ngữ

Resource bundle là một nhóm resource chứa thông điệp theo locale. Java `ResourceBundle` thường tìm các file theo base name và locale. Ví dụ:

```text
src/main/resources/
  i18n/
    messages.properties
    messages_vi.properties
    messages_vi_VN.properties
    messages_en.properties
    messages_ja.properties
```

Base name trong ví dụ là `i18n.messages` nếu gọi `ResourceBundle.getBundle("i18n.messages", locale)`. **Base name không bao gồm hậu tố locale hoặc phần mở rộng `.properties`.**

Đăng ký bundle bằng:

```java
hints.resources().registerResourceBundle("i18n.messages");
```

Ví dụ sử dụng:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageProvider {

    public String title(Locale locale) {
        ResourceBundle bundle =
            ResourceBundle.getBundle("i18n.messages", locale);

        return bundle.getString("invoice.title");
    }
}
```

Với locale `vi-VN`, Java có thể xem xét các candidate tương ứng như `i18n/messages_vi_VN.properties`, `i18n/messages_vi.properties`, rồi bundle mặc định `i18n/messages.properties` theo quy tắc lookup và fallback của `ResourceBundle`. Hãy cung cấp những file cần thiết cho tất cả locale mà ứng dụng cam kết hỗ trợ.

### 6.1. Base name và tên file là hai cách biểu diễn khác nhau

| Thành phần | Ví dụ | Quy tắc |
| --- | --- | --- |
| Base name Java | `i18n.messages` | Dùng dấu chấm phân tách package/path |
| Resource path | `i18n/messages.properties` | Dùng dấu `/`, gồm phần mở rộng |
| Locale suffix | `_vi`, `_vi_VN` | Phần bổ sung theo locale |
| Resource bundle hint | `registerResourceBundle("i18n.messages")` | Đăng ký base name, không thêm `.properties` |

Lỗi thường gặp là gọi `registerResourceBundle("i18n/messages.properties")`. Đó là resource path, không phải base name của bundle. Nếu đang đăng ký một file properties đơn lẻ được đọc bằng `ClassPathResource`, hãy dùng `registerPattern` với path; nếu đọc bằng `ResourceBundle`, hãy dùng `registerResourceBundle` với base name.

### 6.2. Spring MessageSource

Ứng dụng Spring có thể dùng `MessageSource` thay vì gọi `ResourceBundle` trực tiếp. Ví dụ, Spring Boot có thể cấu hình basename qua property:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
```

Nếu cơ chế `MessageSource` dùng Java resource bundles, hãy đăng ký base name tương ứng khi metadata không được framework/dependency tự cung cấp. Nếu cấu hình dùng một implementation đọc file properties qua Spring Resource abstraction, cần xác định chính xác nó đọc **classpath resource** hay file ngoài và đăng ký resource path phù hợp. Không mặc định mọi `MessageSource` đều có cách nạp resource giống hệt nhau.

Hãy test ít nhất locale mặc định, locale tiếng Việt và một locale phụ nếu sản phẩm hỗ trợ. Kiểm tra cả fallback khi thiếu bản dịch của một key, vì lỗi chỉ có thể xuất hiện ở locale ít được dùng.

## 7. Resource trong dependency và thư mục META-INF

Resource có thể nằm trong JAR của thư viện, không chỉ trong `src/main/resources` của ứng dụng. Ví dụ thư viện cung cấp file mặc định trong `META-INF/vendor/`, template hoặc schema. Khi gặp lỗi, cần xác định:

- Resource có thật trong dependency JAR hay không.
- Thư viện đã cung cấp Spring Runtime Hints hoặc GraalVM reachability metadata chưa.
- Phiên bản metadata có tương thích với GraalVM/Spring Boot đang dùng không.
- Code đọc resource qua classloader nào và tên path chính xác là gì.

Có thể có resource đặc biệt trong `META-INF`, chẳng hạn descriptor service provider ở `META-INF/services`. Cơ chế `ServiceLoader` và metadata hỗ trợ của GraalVM/Spring có thể xử lý một số trường hợp riêng; không nên đăng ký toàn bộ `META-INF/*` theo thói quen. Xác minh dependency và đường truy cập thực tế trước khi bổ sung pattern.

Nếu ứng dụng sở hữu thư viện, nên đóng góp metadata ở chính thư viện để mọi ứng dụng tiêu thụ nhận được cấu hình tương thích. Nếu chỉ là resource đặc thù của ứng dụng, đăng ký trong registrar thuộc ứng dụng là hợp lý.

## 8. Kiểm thử Runtime Hints trước khi build native

Có thể kiểm tra việc đăng ký hint bằng `RuntimeHintsPredicates`. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.junit.jupiter.api.Assertions.assertTrue;

class PricingResourceHintsTests {

    @Test
    void registersPricingResource() {
        RuntimeHints hints = new RuntimeHints();

        new PricingResourceHints().registerHints(
            hints, getClass().getClassLoader()
        );

        assertTrue(
            RuntimeHintsPredicates.resource()
                .forResource("rules/pricing.json")
                .test(hints)
        );
    }
}
```

Với resource bundle, kiểm tra base name đã đăng ký:

```java
assertTrue(
    RuntimeHintsPredicates.resource()
        .forBundle("i18n.messages")
        .test(hints)
);
```

Những test này xác nhận registrar đã đóng góp hint vào `RuntimeHints`. Chúng **không chứng minh** file có tồn tại trong source tree, pattern khớp đúng resource hoặc binary native thực sự đọc được file. Cần test cả resource trong JAR/classpath lẫn executable native.

### 8.1. Kiểm tra resource tồn tại trong JAR

Với Maven, sau khi build JAR:

```bash
jar tf target/hello-native-0.0.1-SNAPSHOT.jar
```

Tìm các đường dẫn như `BOOT-INF/classes/rules/pricing.json` hoặc resource nằm trong dependency. Với Gradle, có thể dùng `jar tf build/libs/<artifact>.jar`. Đường dẫn trong Spring Boot executable JAR có thể nằm trong `BOOT-INF/classes` hoặc bên trong nested dependency JAR; kiểm tra đúng vị trí và classloader behavior.

### 8.2. Kiểm thử trên native executable

Sau khi chạy native build:

1. Khởi động executable trong môi trường tương thích.
2. Gọi endpoint hoặc job thực sự đọc classpath resource.
3. Xác minh nội dung, encoding, dữ liệu parse và kết quả nghiệp vụ.
4. Gọi từng nhánh chọn resource theo tên động.
5. Test mọi locale mà ứng dụng hỗ trợ và kiểm tra fallback.
6. Ghi log/exception khi resource không tồn tại; tránh chỉ trả kết quả rỗng khiến lỗi bị che.

Nếu chỉ có test `RuntimeHintsPredicates` mà chưa chạy binary, chưa thể kết luận tính tương thích native đã đạt.

## 9. Ví dụ hoàn chỉnh: đọc template và thông điệp theo locale

Giả sử ứng dụng có cấu trúc:

```text
src/main/resources/
  templates/
    invoice.html
    invoice-footer.html
  i18n/
    messages.properties
    messages_vi.properties
    messages_en.properties
```

Đăng ký hints:

```java
final class InvoiceResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("templates/invoice.html");
        hints.resources().registerPattern("templates/invoice-footer.html");
        hints.resources().registerResourceBundle("i18n.messages");
    }
}
```

Liên kết registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}
```

Đọc template qua Spring Resource abstraction:

```java
var template = new ClassPathResource("templates/invoice.html");

try (var input = template.getInputStream()) {
    String html = new String(
        input.readAllBytes(), StandardCharsets.UTF_8
    );
}
```

Đọc thông điệp theo locale:

```java
ResourceBundle bundle =
    ResourceBundle.getBundle("i18n.messages", Locale.forLanguageTag("vi-VN"));

String title = bundle.getString("invoice.title");
```

Khi build native, xác nhận registrar được Spring phát hiện, hints xuất hiện trong output AOT/metadata và cả hai đường đọc resource đều hoạt động. Nếu template được đọc bằng tên do người dùng gửi lên, không đưa trực tiếp chuỗi tùy ý vào `ClassPathResource`; hãy kiểm tra nó thuộc danh sách template được phép và chỉ đăng ký tập resource đã biết.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `getResourceAsStream` trả `null` trên native | Resource không có trong image, path sai hoặc khác chữ hoa/thường | Kiểm tra path trong JAR, đăng ký resource hint chính xác |
| `ClassPathResource` không mở được file | Nhầm classpath với filesystem hoặc path có tiền tố không phù hợp | Xác định loại resource, dùng đúng API và tên tương đối classpath |
| Resource chỉ lỗi với một tenant/loại template | Code chọn path động nhưng chỉ một file được đăng ký | Đăng ký tất cả file hợp lệ hoặc pattern giới hạn |
| `MissingResourceException` | Bundle base name sai hoặc locale file thiếu | Đăng ký đúng base name, bổ sung locale và kiểm tra fallback |
| Bundle mặc định hoạt động nhưng tiếng Việt lỗi | Thiếu `messages_vi.properties` hoặc tên bundle sai | Kiểm tra resource path và `registerResourceBundle` |
| Có file trong `src/main/resources` nhưng native không đọc được | Chưa được đóng gói/metadata không nhận ra truy cập động | Kiểm tra JAR, RuntimeHints và native executable |
| Pattern không bao gồm file lồng thư mục | Cú pháp pattern không khớp cấu trúc thật | Kiểm tra semantics pattern của phiên bản Spring/GraalVM; đăng ký chính xác để xác minh |
| Resource của dependency bị thiếu | Dependency không có metadata native hoặc metadata không tương thích | Nâng cấp/đóng góp metadata hoặc đăng ký hint ở ứng dụng |
| File cấu hình ngoài không tìm thấy | Nghĩ resource hint sẽ copy file vào container | Mount/copy file vào runtime filesystem và cấp quyền đọc |
| Native build thành công nhưng lỗi lúc request | Chưa test nhánh đọc resource hoặc locale hiếm | Thêm integration test chạy trên native binary |

Không giải quyết bằng cách đăng ký tất cả resource trên classpath nếu chưa biết nguyên nhân. Pattern quá rộng làm tăng dữ liệu đóng gói và có thể đưa những file không cần thiết vào image.

## 11. Bài thực hành: đăng ký resource và resource bundle

**Bối cảnh:** Một API Spring Boot tạo nội dung hóa đơn. Nó đọc `templates/invoice.html` và lấy tiêu đề từ resource bundle `i18n.messages`.

**Các bước:**

1. Tạo `templates/invoice.html`, `i18n/messages.properties` và `i18n/messages_vi.properties` trong `src/main/resources`.
2. Viết một service đọc template bằng `ClassPathResource` và đọc tiêu đề bằng `ResourceBundle`.
3. Tạo `RuntimeHintsRegistrar` đăng ký `templates/invoice.html` và base name `i18n.messages`.
4. Dùng `@ImportRuntimeHints` để Spring AOT phát hiện registrar.
5. Viết unit test với `RuntimeHintsPredicates` cho resource và bundle.
6. Build JAR, kiểm tra resource có trong artifact và chạy endpoint trên JVM.
7. Build GraalVM Native Image, gọi cùng endpoint trên native executable.
8. Test locale `vi-VN`, locale mặc định và một locale khác nếu được hỗ trợ; kiểm tra fallback.
9. Thử đổi tên resource sai chữ hoa/thường để hiểu cách lỗi xuất hiện, sau đó khôi phục đúng path.
10. Ghi lại kết quả native build, resource test, response và exception nếu có.

**Tiêu chí đạt:**

- Resource hint đăng ký đúng classpath path.
- Resource bundle hint dùng base name, không dùng tên file `.properties`.
- Registrar được import và chạy trong quy trình AOT.
- Unit test xác nhận hints có trong `RuntimeHints`.
- Native executable đọc đúng template và thông điệp.
- Locale/fallback đúng với phạm vi sản phẩm cam kết.
- File ngoài container được xử lý qua volume/configuration riêng, không nhầm với classpath hints.

## 12. Tổng kết

`ResourceHints` giúp Spring AOT cung cấp cho GraalVM Native Image thông tin về các tài nguyên cần giữ lại khi ứng dụng đọc resource động. Dùng `registerPattern` cho classpath file hoặc nhóm đường dẫn; dùng `registerResourceBundle` cho Java resource bundle theo base name. Đặt khai báo trong `RuntimeHintsRegistrar`, liên kết qua `@ImportRuntimeHints`, rồi kiểm tra bằng `RuntimeHintsPredicates` và trên native executable.

Hãy luôn phân biệt **resource trong classpath** với **file ngoài filesystem**. Hint không mount volume, không cấp quyền đọc file và không tự cung cấp secret. Một cấu hình resource đáng tin cậy cần path chính xác, pattern có phạm vi hẹp, locale được kiểm thử và bằng chứng rằng binary native thực sự đọc được tài nguyên trong môi trường triển khai.

