# Template không tìm thấy và lỗi render trong Spring Framework Mail

Khi ứng dụng Spring gửi email bằng template, lỗi có thể xuất hiện trước cả khi SMTP được gọi. Một template có thể không được tìm thấy, resource có thể không đọc được, cú pháp template có thể sai, hoặc dữ liệu truyền vào không đủ để render nội dung. Những lỗi này thường được gọi chung là **template error**, nhưng chúng có nguyên nhân và cách xử lý khác nhau.

Trong Spring Framework Mail, một luồng gửi email dùng template thường gồm:

1. Chọn template theo loại thông báo và ngôn ngữ.
2. Template resolver tìm resource trong classpath hoặc filesystem.
3. Template engine đọc và phân tích cú pháp template.
4. Engine đánh giá biểu thức và thay dữ liệu vào các vị trí tương ứng.
5. Ứng dụng nhận chuỗi HTML/text đã render.
6. Ứng dụng tạo MIME message và gửi bằng JavaMailSender.

Nếu bước 2, 3 hoặc 4 thất bại, ứng dụng chưa có nội dung email hợp lệ để gửi. **Không nên coi mọi lỗi template là lỗi SMTP**, cũng không nên gửi nguyên file template chưa render chỉ để tránh lỗi. Cần xác định lỗi xảy ra ở bước nào, lưu đủ thông tin để chẩn đoán và áp dụng chính sách fallback hoặc retry phù hợp.

## 1. Phân biệt các nhóm lỗi

Một thông báo “không gửi được email” có thể che giấu nhiều lỗi khác nhau:

| Nhóm lỗi | Ví dụ | Thời điểm phát sinh | Hướng xử lý chính |
| --- | --- | --- | --- |
| **Template not found** | Không có file order-ready.html trong classpath | Khi resolver tìm template | Kiểm tra tên, prefix/suffix, package resource và artifact |
| **Resource read failure** | File ngoài ứng dụng không tồn tại hoặc thiếu quyền đọc | Khi mở resource | Kiểm tra nguồn, quyền filesystem, volume và I/O |
| **Template parse failure** | HTML template có cú pháp Thymeleaf sai | Khi engine phân tích template | Sửa template, cú pháp hoặc fragment |
| **Expression/render failure** | Biểu thức tham chiếu thuộc tính không có trong context | Khi engine đánh giá biểu thức | Kiểm tra view model và tên biến |
| **Template logic failure** | Điều kiện hoặc vòng lặp dùng dữ liệu sai kiểu | Trong quá trình render | Kiểm tra kiểu dữ liệu và logic template |
| **Encoding failure** | Tiếng Việt bị lỗi hoặc resource không giải mã được | Khi đọc hoặc render | Đồng nhất charset, ưu tiên UTF-8 |
| **MIME construction failure** | Nội dung/attachment không thể đóng gói | Sau render, trước SMTP | Kiểm tra MimeMessage và resource đính kèm |
| **SMTP submission failure** | Server từ chối AUTH, MAIL FROM hoặc DATA | Khi gửi | Kiểm tra SMTP transport và phản hồi server |

Phân biệt này giúp tránh xử lý sai. Ví dụ, tăng timeout SMTP không sửa được template bị thiếu; retry liên tục không sửa được lỗi cú pháp cố định; đổi template không khắc phục được credential SMTP bị từ chối.

### Luồng xử lý và điểm có thể thất bại

~~~mermaid
flowchart TD
    A["Sự kiện nghiệp vụ"] --> B["Chọn template key và locale"]
    B --> C["Template resolver"]
    C --> D{"Tìm thấy resource?"}
    D -- "Không" --> E["Template not found"]
    D -- "Có" --> F["Đọc và parse template"]
    F --> G{"Cú pháp hợp lệ?"}
    G -- "Không" --> H["Parse error"]
    G -- "Có" --> I["Render với context"]
    I --> J{"Render thành công?"}
    J -- "Không" --> K["Expression / data error"]
    J -- "Có" --> L["Tạo MimeMessage"]
    L --> M["JavaMailSender"]
    M --> N{"SMTP chấp nhận?"}
    N -- "Không" --> O["Mail transport error"]
    N -- "Có" --> P["Submitted"]
~~~

Mỗi nhánh cần một loại log, trạng thái công việc và quyết định retry riêng. Đặc biệt, **template render nên hoàn tất trước khi gọi JavaMailSender**, để lỗi template không bị trộn vào lỗi giao vận.

## 2. Template resolver tìm file như thế nào?

Template engine không tự đoán vị trí file. Nó nhận một **template name**, sau đó một hoặc nhiều resolver xác định resource tương ứng.

Ví dụ cấu trúc resource:

~~~text
src/main/resources/
└── templates/
    └── mail/
        ├── order-ready.html
        ├── order-ready.txt
        ├── payment-received.html
        └── password-reset.html
~~~

Nếu resolver được cấu hình prefix là **templates/mail/** và suffix là **.html**, tên template **order-ready** sẽ được ánh xạ thành:

~~~text
templates/mail/order-ready.html
~~~

Vì vậy, khi gặp lỗi template not found, cần kiểm tra toàn bộ phép ánh xạ:

| Thành phần | Giá trị ví dụ | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| Template name | order-ready | Code có truyền đúng key không? |
| Prefix | templates/mail/ | Có đúng thư mục trong classpath không? |
| Suffix | .html | File thực tế có đúng đuôi không? |
| Resource location | templates/mail/order-ready.html | File có được đóng gói không? |
| Classloader | Application classloader | Resource có nằm trên classpath của runtime không? |
| Locale | vi hoặc en | Có chọn nhầm thư mục locale không? |

### Cấu hình Thymeleaf resolver cho email

Với Spring 6 và Thymeleaf Spring 6, có thể dùng resolver dựa trên classloader:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

@Configuration
public class MailTemplateConfiguration {

    @Bean("mailHtmlTemplateEngine")
    public SpringTemplateEngine mailHtmlTemplateEngine() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/mail/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCheckExistence(true);
        resolver.setCacheable(true);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        return engine;
    }
}
~~~

Resolver này tìm template trong classpath. Các thiết lập có ý nghĩa:

- **prefix** là thư mục gốc của template.
- **suffix** được thêm vào tên template khi resolver tìm file.
- **TemplateMode.HTML** yêu cầu engine phân tích cú pháp HTML/Thymeleaf.
- **characterEncoding** xác định charset khi đọc resource.
- **checkExistence** cho phép resolver kiểm tra resource tồn tại khi phân giải, hữu ích khi có nhiều resolver theo thứ tự.
- **cacheable** cho phép cache template đã phân tích, phù hợp với template đóng gói ổn định trong production.

Ví dụ trên chỉ tạo engine HTML. Nếu có bản text riêng, có thể cấu hình resolver và engine text với suffix **.txt** và TemplateMode.TEXT. Không nên dùng một resolver HTML rồi kỳ vọng engine tự tìm mọi định dạng.

### Tên template thường không bao gồm suffix

Với prefix/suffix như trên, cách gọi:

~~~java
String html = mailHtmlTemplateEngine.process(
        "order-ready", context);
~~~

sẽ tìm file order-ready.html. Nếu code truyền **order-ready.html** trong khi resolver vẫn tự thêm suffix, đường dẫn có thể thành order-ready.html.html. Hãy thống nhất một quy ước: template name là key không có phần mở rộng, còn resolver quản lý prefix/suffix.

## 3. Template not found: nguyên nhân và cách chẩn đoán

Lỗi không tìm thấy template thường đến từ một trong các nguyên nhân sau.

### 3.1. Sai tên hoặc sai chữ hoa/chữ thường

Ví dụ file thật là:

~~~text
templates/mail/order-ready.html
~~~

nhưng code gọi:

~~~java
mailHtmlTemplateEngine.process("Order-Ready", context);
~~~

Trên một số filesystem Windows, khác biệt chữ hoa/chữ thường có thể không bộc lộ khi chạy local. Khi triển khai trên Linux hoặc trong môi trường có quy tắc phân biệt case, tên không khớp có thể khiến resolver không tìm thấy file.

Giữ tên template nhất quán, dùng key ổn định và kiểm tra file trong artifact. Không dựa vào việc môi trường phát triển “vẫn chạy được”.

### 3.2. Prefix hoặc suffix sai

Giả sử resource nằm trong **templates/mail/** nhưng resolver lại đặt prefix **mail/templates/**. Resolver sẽ tìm sai vị trí dù file đã có trong JAR.

Kiểm tra cả ba giá trị:

~~~text
Template name: order-ready
Prefix:        templates/mail/
Suffix:        .html
Resolved path: templates/mail/order-ready.html
~~~

Nên ghi template key và resolver configuration vào log chẩn đoán ở mức an toàn. Không ghi toàn bộ nội dung template hoặc dữ liệu cá nhân đã render.

### 3.3. Resource không được đóng gói vào JAR

File có thể tồn tại trong repository nhưng bị thiếu trong artifact do:

- Đặt nhầm dưới thư mục không được build tool coi là resource.
- Cấu hình Gradle/Maven loại file khỏi resource processing.
- Sai tên hoặc sai đường dẫn trong source tree.
- Resource nằm trong module khác nhưng module đó không có trên runtime classpath.
- Artifact triển khai không phải phiên bản vừa build.

Đường dẫn source:

~~~text
src/main/resources/templates/mail/order-ready.html
~~~

Đường dẫn runtime:

~~~text
templates/mail/order-ready.html
~~~

Khi chạy từ executable JAR, resource thường nằm trong vùng classpath của JAR. Không dùng đường dẫn source tree như **src/main/resources/...** để nạp file tại runtime.

### 3.4. Dùng filesystem path thay cho classpath path

Code sau phụ thuộc thư mục làm việc của process:

~~~java
new File("src/main/resources/templates/mail/order-ready.html");
~~~

Đường dẫn này thường không tồn tại khi ứng dụng được triển khai. Với resource đóng gói cùng ứng dụng, dùng ClassPathResource, ResourceLoader hoặc template resolver hỗ trợ classpath.

### 3.5. Dùng getFile() với resource nằm trong JAR

Resource classpath trong executable JAR có thể không phải file độc lập trên filesystem. Vì vậy, **Resource.getFile()** có thể thất bại dù resource thực sự tồn tại.

Đọc qua stream:

~~~java
Resource resource = new ClassPathResource(
        "templates/mail/order-ready.html");

try (InputStream input = resource.getInputStream()) {
    String source = StreamUtils.copyToString(
            input, StandardCharsets.UTF_8);
}
~~~

Nếu dùng template engine, thường không cần tự đọc file; chỉ cần cấu hình resolver đúng và gọi process theo template name.

### 3.6. Locale chọn đến một thư mục không tồn tại

Giả sử ứng dụng chọn:

~~~text
templates/mail/fr/order-ready.html
~~~

nhưng chỉ có thư mục **vi/** và **en/**. Template mặc định có thể tồn tại nhưng code không có fallback locale.

Hãy định nghĩa rõ quy tắc:

1. Tìm cặp template theo locale chính xác.
2. Nếu không có, thử locale đã được rút gọn theo quy tắc của ứng dụng (ví dụ vi-VN sang vi).
3. Nếu vẫn không có, dùng locale mặc định đã được phê duyệt.
4. Nếu template bắt buộc vẫn không tồn tại, đánh dấu lỗi cấu hình và không gửi nội dung sai.

Không nên tự ghép locale do người dùng gửi vào đường dẫn filesystem. Dùng allowlist locale và template key.

## 4. Nạp resource trực tiếp để xác định lỗi nằm ở đâu

Nếu nghi resource bị thiếu, có thể kiểm tra bằng Spring Resource API trước khi render:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource template = new ClassPathResource(
        "templates/mail/order-ready.html");

if (!template.exists() || !template.isReadable()) {
    throw new IllegalStateException(
            "Required mail template is missing or unreadable");
}
~~~

Kiểm tra này giúp phân biệt **resource không có/không đọc được** với lỗi cú pháp hoặc lỗi biểu thức trong template. Tuy nhiên, nếu template engine dùng resolver riêng, resource check cần dùng đúng location và nguồn tương ứng với resolver đó.

Với template ở filesystem:

~~~java
Resource template = resourceLoader.getResource(
        "file:/etc/myapp/mail/order-ready.html");
~~~

Cần kiểm tra quyền đọc của process, volume mount, đường dẫn và tính sẵn sàng của filesystem. Nếu file được thay đổi khi ứng dụng đang chạy, còn phải xét đến cache của template engine.

**Không lấy resource location tùy ý từ request.** Chọn template bằng một key trong allowlist rồi ánh xạ sang location cố định để tránh path traversal hoặc truy cập file/URL ngoài dự kiến.

## 5. Parse error: tìm thấy file nhưng cú pháp không hợp lệ

Một template có thể tồn tại và đọc được nhưng không thể phân tích. Với Thymeleaf, các lỗi thường gặp gồm:

- Đóng/mở thẻ HTML hoặc fragment không đúng cấu trúc mà engine yêu cầu.
- Biểu thức Thymeleaf sai cú pháp.
- Attribute processor viết sai tên hoặc vị trí.
- Fragment được tham chiếu nhưng không tồn tại.
- Template text dùng cú pháp của HTML mode hoặc ngược lại.
- Template chứa ký tự/encoding bất thường khiến parser không đọc được.

Ví dụ:

~~~html
<p th:text="${customerName">Tên khách hàng</p>
~~~

Biểu thức thiếu dấu đóng cú pháp. Khi engine parse hoặc xử lý attribute, nó có thể ném exception thay vì tạo nội dung như mong đợi.

Ví dụ đúng:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>
~~~

### HTML hợp lệ không đồng nghĩa template hợp lệ

Một file có thể mở được trong trình duyệt nhưng không render được qua Thymeleaf nếu biểu thức template sai. Ngược lại, một template render được không bảo đảm mọi email client hiển thị CSS/HTML giống nhau. Đây là hai vấn đề riêng:

| Kiểm tra | Điều được xác nhận |
| --- | --- |
| HTML parser/browser | Cấu trúc HTML có thể được trình duyệt phân tích |
| Template engine | Cú pháp và biểu thức template có thể được render |
| Email client | Nội dung được hiển thị như thế nào trong môi trường đọc thư |
| Accessibility review | Người nhận có thể đọc và thực hiện hành động với nội dung hay không |

Khi gặp parse error, xem tên template, vị trí dòng/cột nếu exception cung cấp, fragment liên quan và phiên bản template đang chạy. Không chỉ nhìn file local nếu production đang chạy một artifact cũ.

## 6. Render error: template tồn tại nhưng dữ liệu không phù hợp

Sau khi parse, engine cần đánh giá biểu thức và lấy dữ liệu từ context. Ví dụ template:

~~~html
<p>Xin chào <span th:text="${customer.name}">Tên</span></p>
<p>Mã đơn: <span th:text="${order.id}">ORD-000</span></p>
~~~

Context cần có các biến tương ứng:

~~~java
Context context = new Context(locale);
context.setVariable("customer", customerView);
context.setVariable("order", orderView);
~~~

Nếu code chỉ truyền **customerName** và **orderId**, template không thể truy cập **customer.name** hoặc **order.id** theo cấu trúc trên. Engine có thể render giá trị rỗng, bỏ qua phần tử hoặc ném lỗi tùy biểu thức, cấu hình và kiểu truy cập.

### Các nguyên nhân phổ biến

| Nguyên nhân | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Thiếu biến | Template dùng customerName nhưng context không có | Đồng bộ tên biến giữa renderer và template |
| Sai cấu trúc object | Template dùng customer.name nhưng truyền String | Truyền view model đúng kiểu hoặc đổi biểu thức |
| Giá trị null | order.customer là null | Validation/fallback trước render hoặc xử lý điều kiện |
| Sai kiểu dữ liệu | Vòng lặp mong đợi List nhưng nhận String | Chuẩn hóa kiểu dữ liệu trong view model |
| Fragment thiếu tham số | Fragment yêu cầu order nhưng caller không truyền | Kiểm tra fragment signature và lời gọi |
| Biểu thức gọi method không hợp lệ | Gọi getter/method không tồn tại hoặc bị giới hạn | Dùng property được cung cấp rõ trong view model |
| Dữ liệu tùy chọn bị bỏ qua | Template giả định địa chỉ luôn có | Định nghĩa trường bắt buộc/tùy chọn |

### Truyền view model rõ ràng

Thay vì truyền toàn bộ entity JPA, tạo một model chuyên dùng cho email:

~~~java
public record OrderReadyMailModel(
        String customerName,
        String orderId,
        String pickupLocation,
        String pickupDeadline,
        String orderUrl
) {
}
~~~

Sau đó đưa các biến có tên ổn định vào context:

~~~java
Context context = new Context(locale);
context.setVariable("customerName", model.customerName());
context.setVariable("orderId", model.orderId());
context.setVariable("pickupLocation", model.pickupLocation());
context.setVariable("pickupDeadline", model.pickupDeadline());
context.setVariable("orderUrl", model.orderUrl());
~~~

Template:

~~~html
<h1>Đơn hàng đã sẵn sàng</h1>
<p>Xin chào <span th:text="${customerName}">Khách hàng</span></p>
<p>Mã đơn: <span th:text="${orderId}">ORD-000</span></p>
<p>Địa điểm: <span th:text="${pickupLocation}">Địa điểm</span></p>
<p>Hạn nhận: <span th:text="${pickupDeadline}">Thời gian</span></p>
<a th:href="${orderUrl}">Xem đơn hàng</a>
~~~

View model làm rõ hợp đồng giữa Java và template. Khi đổi cấu trúc database, template không phải phụ thuộc vào entity hoặc quan hệ lazy-loading. Khi thêm trường bắt buộc, có thể cập nhật model, renderer và test cùng nhau.

### Kiểm tra trường bắt buộc trước khi render

Không nên chờ template engine phát hiện mọi lỗi dữ liệu. Có thể kiểm tra trước:

~~~java
private static void validate(OrderReadyMailModel model) {
    Objects.requireNonNull(model, "model");
    requireText(model.customerName(), "customerName");
    requireText(model.orderId(), "orderId");
    requireText(model.pickupLocation(), "pickupLocation");
    requireText(model.pickupDeadline(), "pickupDeadline");
    requireText(model.orderUrl(), "orderUrl");
}

private static void requireText(String value, String field) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "Required mail field is missing: " + field);
    }
}
~~~

Đây là ví dụ validation cơ bản. Trong ứng dụng thật, kiểm tra còn cần áp dụng schema, độ dài, quyền truy cập dữ liệu, URL/host cho phép, locale và các quy tắc nghiệp vụ.

## 7. Ví dụ renderer Thymeleaf và phân loại lỗi

Một renderer có thể tập trung việc chọn template, chuẩn bị context và gọi engine:

~~~java
package com.example.mail;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.exceptions.TemplateEngineException;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class MailTemplateRenderer {

    private final SpringTemplateEngine htmlEngine;

    public MailTemplateRenderer(
            @Qualifier("mailHtmlTemplateEngine")
            SpringTemplateEngine htmlEngine) {
        this.htmlEngine = htmlEngine;
    }

    public String renderOrderReady(
            OrderReadyMailModel model,
            Locale locale) {
        validate(model);

        Context context = new Context(locale);
        context.setVariable("customerName", model.customerName());
        context.setVariable("orderId", model.orderId());
        context.setVariable("pickupLocation", model.pickupLocation());
        context.setVariable("pickupDeadline", model.pickupDeadline());
        context.setVariable("orderUrl", model.orderUrl());

        try {
            return htmlEngine.process("order-ready", context);
        } catch (TemplateEngineException exception) {
            throw new MailTemplateRenderException(
                    "Cannot render mail template: order-ready",
                    exception);
        }
    }

    private static void validate(OrderReadyMailModel model) {
        if (model == null
                || model.customerName() == null
                || model.orderId() == null
                || model.pickupLocation() == null
                || model.pickupDeadline() == null
                || model.orderUrl() == null) {
            throw new IllegalArgumentException(
                    "Order-ready mail data is incomplete");
        }
    }
}
~~~

Exception riêng của ứng dụng:

~~~java
public class MailTemplateRenderException extends RuntimeException {

    public MailTemplateRenderException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Ví dụ minh họa bắt lỗi thuộc nhóm Thymeleaf TemplateEngineException. Trong ứng dụng thực tế, exception cụ thể có thể là một subclass như TemplateInputException hoặc TemplateProcessingException; cần giữ cause để điều tra. Lỗi validation dữ liệu được ném trước khối render và không nên bị phân loại nhầm thành lỗi cú pháp template.

Không nên bắt mọi RuntimeException rồi trả về chuỗi rỗng. Cách đó làm email vẫn được tạo với nội dung thiếu, che mất nguyên nhân và có thể gây hậu quả nghiệp vụ.

## 8. Tách lỗi render khỏi lỗi gửi SMTP

Renderer nên hoàn tất trước khi service gọi JavaMailSender:

~~~java
public void sendOrderReady(
        OrderReadyMailModel model,
        Locale locale) throws MessagingException {

    String html = renderer.renderOrderReady(model, locale);
    String plain = plainTextRenderer.renderOrderReady(model, locale);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom(fromAddress);
    helper.setTo(recipientAddress);
    helper.setSubject("Đơn hàng " + model.orderId() + " đã sẵn sàng");
    helper.setText(plain, html);

    mailSender.send(message);
}
~~~

Ví dụ này giả định sender, renderer và địa chỉ đã được inject; bản text được render bởi một renderer tương ứng. Tách bước giúp phân biệt:

- **Lỗi trước send:** dữ liệu, template name, resource, parse hoặc render.
- **Lỗi khi send:** tạo MIME, kết nối, TLS, SMTP AUTH, MAIL FROM, RCPT TO hoặc DATA.
- **Lỗi sau send:** relay đã nhận nhưng phát đến mailbox đích bị trì hoãn hoặc bounce.

Nếu bắt exception ở cùng một lớp, vẫn nên phân loại theo giai đoạn và giữ nguyên nguyên nhân gốc. Đừng chuyển mọi lỗi thành thông báo “SMTP server không khả dụng”.

## 9. Resolver nhiều template và thứ tự tìm kiếm

Một ứng dụng có thể dùng nhiều resolver, ví dụ template mặc định nằm trong classpath, template riêng theo tenant nằm trong filesystem, template HTML và text dùng suffix khác nhau, hoặc template theo locale có thư mục riêng.

Khi nhiều resolver tham gia, **thứ tự và điều kiện kiểm tra tồn tại** ảnh hưởng đến kết quả. Một resolver đầu tiên có thể nhận template name dù resource không phù hợp, hoặc một resolver có thể báo không tìm thấy và cho resolver tiếp theo cơ hội xử lý, tùy cấu hình.

Với Thymeleaf, có thể cấu hình resolver theo thứ tự và dùng checkExistence để hỗ trợ lựa chọn:

~~~java
ClassLoaderTemplateResolver classpathResolver =
        new ClassLoaderTemplateResolver();
classpathResolver.setPrefix("templates/mail/");
classpathResolver.setSuffix(".html");
classpathResolver.setTemplateMode(TemplateMode.HTML);
classpathResolver.setOrder(2);
classpathResolver.setCheckExistence(true);

// Một resolver khác có thể được thêm trước/sau theo thiết kế.
~~~

Đây là đoạn cấu hình một resolver, chưa phải cấu hình hoàn chỉnh nhiều nguồn. Khi có nhiều resolver, cần thiết lập order, prefix/suffix, pattern, cache và hành vi fallback cho từng resolver, sau đó kiểm thử trường hợp template có mặt ở nhiều nơi.

### Tránh fallback ngầm sang template không đúng loại

Giả sử template cho email xác nhận thanh toán không tìm thấy. Nếu resolver rơi về một template chung chỉ có nội dung “Xin chào”, ứng dụng có thể gửi email thiếu thông tin quan trọng nhưng vẫn coi là thành công.

Fallback phải là **một quyết định nghiệp vụ có chủ đích**, không phải kết quả tình cờ do resolver thứ hai trả về. Template mặc định chỉ nên được dùng khi nó thực sự phù hợp với loại thông báo và chứa đầy đủ thông tin bắt buộc.

## 10. Chính sách fallback khi template không tìm thấy

Không phải mọi template đều có cùng mức độ quan trọng. Có thể chia:

| Loại nội dung | Ví dụ | Hành vi phù hợp |
| --- | --- | --- |
| Template bắt buộc | OTP, xác nhận giao dịch, thông báo pháp lý | Không gửi nội dung sai; báo lỗi cấu hình và xử lý theo chính sách an toàn |
| Template có fallback đã phê duyệt | Thông báo đơn giản có bản text chuẩn | Có thể dùng bản fallback đã được kiểm soát nếu vẫn đủ thông tin |
| Thành phần trang trí tùy chọn | Logo hoặc banner | Có thể bỏ phần trang trí nếu nội dung chính vẫn đầy đủ |
| Block marketing tùy chọn | Khuyến nghị sản phẩm | Có thể bỏ block nếu không ảnh hưởng thông tin giao dịch |

### Không dùng source template thô làm fallback

Giả sử file có:

~~~text
Xin chào {{customerName}},
Đơn hàng {{orderId}} đã sẵn sàng.
~~~

Nếu render thất bại, không gửi nguyên chuỗi này cho khách. Người nhận sẽ thấy placeholder chưa thay, và thông điệp không còn là một email hoàn chỉnh.

Fallback phải là một template khác đã được kiểm soát và render thành công, một nội dung plain text tối giản được xây dựng rõ ràng từ dữ liệu đã validate, hoặc không gửi và đánh dấu lỗi để xử lý vận hành.

### Fallback từ HTML sang plain text

Nếu HTML template lỗi nhưng plain text template vẫn render được, hệ thống có thể gửi text-only **khi nghiệp vụ cho phép**. Ví dụ email thông báo trạng thái đơn hàng đơn giản có thể có một mẫu text đã phê duyệt.

Không áp dụng tự động cho email mà HTML chứa thông tin bắt buộc không có trong text, hoặc template HTML và text không được version cùng nhau. Nếu lỗi render xuất phát từ dữ liệu thiếu, bản text cũng có thể sai.

Một chính sách an toàn:

1. Render text và HTML từ cùng view model.
2. Nếu HTML render lỗi, ghi nhận lỗi với template key/version.
3. Chỉ dùng text-only khi mẫu text đã render thành công và được đánh dấu là fallback hợp lệ cho loại thông báo đó.
4. Nếu text cũng lỗi hoặc dữ liệu không hợp lệ, không submit email.

## 11. Retry hay không retry?

Retry chỉ hữu ích khi nguyên nhân có khả năng tự biến mất. Nhiều lỗi template là lỗi cố định cho đến khi file hoặc dữ liệu được sửa.

| Lỗi | Retry tự động ngay? | Lý do |
| --- | --- | --- |
| Sai tên template | Không | Tên cấu hình không tự đúng sau vài giây |
| Thiếu file trong artifact | Không | Cần build/deploy artifact đúng |
| Sai cú pháp template | Không | Cần sửa nội dung và phát hành lại |
| Thiếu biến bắt buộc trong context | Không theo kiểu retry mù | Cần sửa mapping hoặc dữ liệu nghiệp vụ |
| File ngoài tạm thời chưa mount | Có thể retry có giới hạn | Chỉ khi xác định đây là lỗi hạ tầng tạm thời |
| Storage template tạm thời không truy cập được | Có thể retry có backoff | Phụ thuộc nguồn và khả năng phục hồi |
| SMTP server tạm từ chối | Có thể retry theo mã lỗi | Đây là lỗi giao vận, tách khỏi render |
| SMTP AUTH credential sai | Không retry liên tục | Cần sửa secret/quyền đăng nhập |

### Phân loại job

~~~text
PENDING
  |
  +-- Template missing / parse error --> TEMPLATE_CONFIG_ERROR
  |
  +-- Required data invalid ----------> INVALID_NOTIFICATION_DATA
  |
  +-- Render successful --------------> READY_TO_SEND
                                           |
                                           +--> SMTP accepted --> SUBMITTED
                                           |
                                           +--> Temporary error --> RETRY_SCHEDULED
                                           |
                                           +--> Permanent error --> SEND_FAILED
~~~

Đây là mô hình trạng thái minh họa. Lỗi template cấu hình thường nên được đưa vào hàng đợi xử lý lỗi/dead-letter hoặc trạng thái cần can thiệp, thay vì liên tục thử render cùng một template lỗi.

Nếu template file ngoài ứng dụng có thể được sửa mà không deploy, một job có thể thử lại sau khi template version thay đổi. Tuy nhiên cần xác định rõ job sẽ dùng **phiên bản template lúc phát sinh sự kiện** hay **phiên bản mới nhất tại lúc retry**. Hai lựa chọn có thể tạo ra nội dung khác nhau cho cùng một notification.

## 12. Log và quan sát lỗi template

Log tốt giúp xác định lỗi xảy ra ở resolver, parser, expression hay SMTP mà không làm lộ dữ liệu người nhận.

Một log sự kiện có thể lưu:

~~~json
{
  "event": "mail_template_render_failed",
  "notificationId": "order-ready-ORD-184-v1",
  "templateKey": "order-ready",
  "locale": "vi-VN",
  "templateVersion": "2026.11.12-2",
  "stage": "RENDER",
  "exceptionType": "TemplateProcessingException",
  "retryable": false
}
~~~

Đây là JSON minh họa cho log nội bộ, không phải output mặc định của Thymeleaf. Không đưa body email, password SMTP, access token hoặc dữ liệu cá nhân đầy đủ vào log. Khi cần đối chiếu recipient, có thể dùng notification ID hoặc một định danh đã được kiểm soát.

### Những chỉ số hữu ích

| Metric | Điều nó cho biết |
| --- | --- |
| Số lần template not found theo template key | Template nào đang thiếu hoặc sai cấu hình |
| Số lỗi parse/render theo phiên bản | Bản phát hành template nào gây sự cố |
| Tỷ lệ render thành công theo locale | Locale nào thiếu cặp template hoặc dữ liệu |
| Thời gian render | Template quá phức tạp hoặc nguồn resource chậm |
| Tỷ lệ fallback | Chất lượng và độ ổn định của template chính |
| Tỷ lệ lỗi SMTP sau render | Tách biệt chất lượng template khỏi giao vận |

Có thể đặt alert khi một template bắt buộc có lỗi đầu tiên hoặc tỷ lệ lỗi vượt ngưỡng. Với template giao dịch quan trọng, **một lỗi missing template sau deploy** có thể là dấu hiệu artifact thiếu resource và nên được phát hiện sớm.

### Không log toàn bộ exception theo cách làm lộ dữ liệu

Stack trace hữu ích cho lập trình viên, nhưng exception message đôi khi chứa biểu thức, path, tên biến hoặc dữ liệu từ context. Log cần tuân theo chính sách dữ liệu của hệ thống. Có thể giữ exception cause trong log được kiểm soát và đưa ra thông báo vận hành ngắn, có correlation ID.

## 13. Kiểm thử template trước khi phát hành

Template là một phần của sản phẩm gửi email. Cần kiểm tra nó trước khi deploy, không đợi đến khi khách hàng nhận thư lỗi.

Các lớp kiểm tra có thể gồm:

1. **Resource presence:** file có nằm trong classpath hoặc nguồn được cấu hình không?
2. **Parse:** template engine có phân tích cú pháp thành công không?
3. **Render:** với dữ liệu mẫu đầy đủ, engine có tạo được output không?
4. **Required content:** output có mã đơn hàng, thời hạn, URL và thông tin bắt buộc không?
5. **Escaping:** dữ liệu có ký tự đặc biệt không thể tạo markup ngoài ý muốn?
6. **Locale coverage:** mỗi locale được hỗ trợ có đủ HTML/text template không?
7. **MIME composition:** HTML/text được đưa vào đúng part không?
8. **Artifact packaging:** resource vẫn đọc được khi chạy từ JAR?

### Unit test render template

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.thymeleaf.context.Context;

class MailTemplateRenderTest {

    @Test
    void rendersOrderReadyTemplate() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", "An");
        context.setVariable("orderId", "ORD-184");
        context.setVariable("pickupLocation", "Quầy nhận hàng Quận 1");
        context.setVariable("pickupDeadline", "17:00 ngày 15/11/2026");
        context.setVariable(
                "orderUrl",
                "https://shop.example/orders/ORD-184");

        String html = mailHtmlTemplateEngine.process(
                "order-ready", context);

        assertTrue(html.contains("ORD-184"));
        assertTrue(html.contains("Quầy nhận hàng Quận 1"));
        assertTrue(html.contains("17:00 ngày 15/11/2026"));
    }
}
~~~

Ví dụ giả định test có thể truy cập bean **mailHtmlTemplateEngine**. Nó kiểm tra các trường nghiệp vụ quan trọng trong kết quả, không chỉ kiểm tra rằng method không ném exception.

### Test template không tồn tại

Có thể kiểm tra engine ném lỗi khi gọi một key không có trong classpath:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.thymeleaf.exceptions.TemplateEngineException;

class MissingMailTemplateTest {

    @Test
    void missingTemplateIsReported() {
        Context context = new Context();

        assertThrows(
                TemplateEngineException.class,
                () -> mailHtmlTemplateEngine.process(
                        "template-does-not-exist", context));
    }
}
~~~

Kiểu exception cụ thể phụ thuộc resolver và phiên bản Thymeleaf; trong test của dự án, nên xác nhận subclass thực tế nếu muốn kiểm tra chặt hơn. Mục tiêu là bảo đảm lỗi không bị nuốt và không trả về một email rỗng như thể render thành công.

### Kiểm tra tất cả template theo danh mục

Nếu có nhiều template, có thể duy trì một danh sách key được hỗ trợ:

~~~java
List<String> requiredTemplates = List.of(
        "order-ready",
        "order-cancelled",
        "payment-received",
        "password-reset");

for (String templateName : requiredTemplates) {
    mailHtmlTemplateEngine.process(templateName, sampleContext);
}
~~~

Đoạn code minh họa việc render các template với context mẫu. Mỗi template có thể yêu cầu biến khác nhau, nên test suite nên định nghĩa **context riêng cho từng template**, không dùng một context chung thiếu dữ liệu rồi kết luận toàn bộ catalog hợp lệ.

### Kiểm tra artifact sau khi build

Một test chạy trong IDE có thể tìm resource từ thư mục classes, trong khi executable JAR triển khai bị thiếu resource. Cần xác nhận template được đóng gói trong artifact, prefix/suffix khớp đường dẫn runtime, tên file khớp chính xác chữ hoa/chữ thường, resource được đọc qua classpath stream và engine có thể render khi chạy theo cách triển khai thực tế.

Không phụ thuộc vào thư mục source trong runtime. Nếu template ở filesystem ngoài JAR, kiểm tra volume, quyền đọc và version được mount trong môi trường tương ứng.

## 14. Cache và lỗi sau khi cập nhật template

Template engine thường cache nội dung hoặc cấu trúc template đã parse. Điều này giúp giảm chi phí I/O và parse khi gửi nhiều email, nhưng có thể tạo hiện tượng:

- Sửa file ngoài filesystem nhưng email vẫn dùng nội dung cũ.
- Một instance dùng template version mới, instance khác vẫn dùng bản cũ.
- Template lỗi được cache và tiếp tục gây lỗi cho nhiều notification.
- Sau deploy, một số instance chưa được restart hoặc chưa tải version mới.

Với template đóng gói trong JAR, cách triển khai thường là build artifact mới rồi rollout instance mới. Với template ngoài ứng dụng, cần xác định cache TTL, cơ chế invalidate/reload, atomic update và rollback.

### Gắn version template vào notification

Nếu notification được lưu lâu và retry sau nhiều giờ, cần quyết định dùng version nào:

| Chính sách | Ý nghĩa |
| --- | --- |
| Render bằng version hiện tại | Nội dung có thể thay đổi sau khi job được tạo |
| Ghi version lúc tạo job | Retry dùng cùng phiên bản đã được xác định |
| Lưu snapshot nội dung đã render | Retry có thể gửi cùng nội dung, nhưng cần bảo vệ dữ liệu và quản lý retention |

Với thông báo pháp lý hoặc giao dịch quan trọng, versioning có thể cần thiết để biết chính xác người nhận đã được gửi nội dung nào. Với thông báo đơn giản, dùng version hiện tại có thể đủ. Quyết định thuộc chính sách nghiệp vụ và kiểm toán của hệ thống.

## 15. Bảo mật khi xử lý template error

Template có thể đọc file, đánh giá biểu thức và đưa dữ liệu vào HTML. Vì vậy, nguồn template và dữ liệu context đều cần được kiểm soát.

### Chỉ dùng template tin cậy

Không nhận nội dung template tùy ý từ người dùng rồi đưa thẳng vào template engine với toàn bộ khả năng expression. Template có thể gọi biểu thức, truy cập thuộc tính hoặc fragment tùy engine/cấu hình. Nếu sản phẩm cho phép người dùng tùy chỉnh email, cần thiết kế một ngôn ngữ template giới hạn hoặc cơ chế allowlist, phân quyền và sandbox phù hợp.

### Escape dữ liệu HTML

Trong Thymeleaf, dùng **th:text** cho nội dung văn bản:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>
~~~

Không dùng **th:utext** cho dữ liệu không tin cậy nếu không có quy trình sanitize HTML phù hợp. Với URL trong **th:href**, phải kiểm tra scheme/host và quyền truy cập trước khi render; HTML escaping không thay thế validation URL.

### Không để fallback làm lộ dữ liệu

Nếu template chính lỗi, không nên gửi debug output, stack trace, tên biến nội bộ, SQL, đường dẫn filesystem hoặc exception message cho người nhận. Fallback cần là nội dung đã được phê duyệt, không phải exception text.

### Không ghi dữ liệu nhạy cảm trong log

Log template key, locale, version, notification ID và loại exception là thường đủ để bắt đầu điều tra. Hạn chế ghi email đầy đủ, body, URL có token, mã đặt lại mật khẩu hoặc dữ liệu tài khoản.

## 16. Quy trình xử lý sự cố đề xuất

Khi có thông báo “email template failed”, có thể đi theo thứ tự:

1. **Xác định notification ID và template key.** Biết loại email nào đang lỗi.
2. **Xác định giai đoạn.** Resolver, đọc resource, parse, render, tạo MIME hay SMTP.
3. **Kiểm tra template name/prefix/suffix.** Đối chiếu với đường dẫn resource runtime.
4. **Kiểm tra artifact hoặc nguồn file.** Resource có mặt và process có quyền đọc không?
5. **Kiểm tra locale và resolver order.** Có chọn nhầm thư mục hoặc resolver không?
6. **Kiểm tra exception gốc và vị trí lỗi.** Parse error hay biểu thức/dữ liệu?
7. **Kiểm tra context.** Các biến bắt buộc có đúng tên, kiểu và giá trị không?
8. **Render với dữ liệu mẫu trong môi trường kiểm soát.** Không dùng dữ liệu khách hàng thật để debug công khai.
9. **Quyết định fallback/retry.** Lỗi cố định cần sửa cấu hình/template; lỗi hạ tầng tạm thời có thể retry có giới hạn.
10. **Kiểm tra SMTP riêng sau khi render thành công.** Nếu template đã tạo nội dung hợp lệ, mới điều tra lỗi submit.

### Bảng khoanh vùng nhanh

| Triệu chứng | Kiểm tra đầu tiên |
| --- | --- |
| Chỉ một template bị lỗi | Template key, file, suffix và cú pháp của mẫu đó |
| Mọi template đều not found | Prefix, classpath, artifact hoặc resolver bean |
| Chỉ một locale bị lỗi | Cặp template theo locale và fallback |
| Chạy local được, production lỗi | Nội dung JAR, chữ hoa/chữ thường, volume và path |
| Template parse được nhưng render lỗi | Context variables, kiểu dữ liệu, null và biểu thức |
| Render thành công nhưng email không gửi | MIME construction và SMTP transport |
| Sửa template nhưng vẫn thấy lỗi cũ | Cache, instance chưa rollout hoặc version |
| Một số worker lỗi, một số không | Artifact/configuration khác nhau giữa instance |

## 17. Các câu hỏi tự kiểm tra

**1. Template not found có phải lỗi SMTP không?**

Không. Đây là lỗi ở bước resolver tìm resource, xảy ra trước khi ứng dụng submit email.

**2. File có trong repository nhưng production không tìm thấy, nguyên nhân có thể là gì?**

Resource có thể chưa được đóng gói, sai prefix/suffix, sai chữ hoa/chữ thường, thiếu module trên runtime classpath hoặc artifact triển khai không đúng phiên bản.

**3. Vì sao không dùng getFile() cho mọi ClassPathResource?**

Vì resource trong executable JAR có thể không tồn tại dưới dạng file độc lập. Đọc bằng getInputStream() hoặc để template resolver xử lý resource.

**4. Template parse error khác render error như thế nào?**

Parse error liên quan cú pháp hoặc cấu trúc template; render error thường liên quan biểu thức, biến, kiểu dữ liệu hoặc thao tác trong quá trình đánh giá.

**5. Thiếu biến trong context luôn ném exception không?**

Không nhất thiết. Hành vi phụ thuộc biểu thức, engine và cấu hình; có trường hợp hiển thị rỗng hoặc bỏ qua phần tử. Vì vậy nên kiểm tra dữ liệu bắt buộc trước render và test output.

**6. Có nên gửi source template thô nếu render thất bại?**

Không. Người nhận có thể thấy placeholder chưa thay hoặc nội dung kỹ thuật. Dùng fallback đã được phê duyệt hoặc không gửi.

**7. Có nên retry template parse error liên tục?**

Không. Lỗi cú pháp là lỗi cố định cho đến khi template được sửa; retry mù chỉ làm tăng tải và lặp lỗi.

**8. Có thể fallback từ HTML sang plain text không?**

Có thể khi bản text là fallback hợp lệ, đã render thành công và chứa đủ thông tin cần thiết cho loại email đó. Không tự động làm vậy khi dữ liệu hoặc template text cũng lỗi.

**9. Tại sao phải kiểm tra template trong executable JAR?**

Vì resource có thể hoạt động trong IDE nhưng thiếu hoặc không đọc được trong artifact triển khai. Kiểm tra đúng cách chạy production giúp phát hiện lỗi đóng gói.

**10. Template engine cache có thể gây lỗi sau deploy không?**

Có. Instance có thể giữ template cũ hoặc không đồng bộ version. Cần quản lý cache, rollout và version template.

**11. Làm thế nào tránh nhầm lỗi render với lỗi gửi?**

Render HTML/text trước khi gọi JavaMailSender, ghi nhận stage riêng và chỉ điều tra SMTP sau khi đã có nội dung hợp lệ.

**12. Log nào hữu ích mà không cần ghi body email?**

Notification ID, template key, locale, template version, stage, exception type và retryability thường đủ để bắt đầu khoanh vùng.

## Kết luận

**Template không tìm thấy và lỗi render là các lỗi ở giai đoạn tạo nội dung email**, trước khi Spring Mail giao thông điệp cho SMTP. Template not found thường liên quan đến template name, resolver prefix/suffix, classpath hoặc resource không được đóng gói; parse error liên quan cú pháp template; render error thường liên quan context, biến, kiểu dữ liệu hoặc biểu thức. Hãy tách bước render khỏi bước gửi, dùng view model có hợp đồng rõ ràng, kiểm tra resource và template trong artifact thực tế, giữ exception gốc và log theo template key/version. Chỉ dùng fallback đã được phê duyệt, không gửi source template chưa render, và chỉ retry khi nguyên nhân có khả năng phục hồi. **Phân loại đúng giai đoạn giúp sửa lỗi nhanh hơn và tránh gửi email thiếu hoặc sai nội dung cho người nhận.**
