# Kiểm thử template với dữ liệu đầy đủ và thiếu

## 1. Vì sao phải kiểm thử template email bằng nhiều bộ dữ liệu?

Trong **Spring Framework Mail**, ứng dụng thường tách phần dựng nội dung email khỏi phần gửi qua SMTP. Một template HTML có thể hiển thị đúng với một bộ dữ liệu mẫu nhưng lại lỗi khi gặp dữ liệu thực tế: tên khách hàng bị trống, danh sách sản phẩm rỗng, địa chỉ giao hàng không tồn tại, mã đơn hàng quá dài hoặc một trường chứa ký tự đặc biệt.

Ví dụ template xác nhận đơn hàng:

~~~html
<h1>Xin chào, <span th:text="${customerName}">bạn</span>!</h1>
<p>Mã đơn hàng: <strong th:text="${orderNumber}">ORD-001</strong></p>
<p>Địa chỉ giao hàng: <span th:text="${deliveryAddress}">...</span></p>
<ul>
  <li th:each="item : ${items}">
    <span th:text="${item.name}">Tên sản phẩm</span>
  </li>
</ul>
~~~

Nếu test chỉ cung cấp customerName, orderNumber, deliveryAddress và items đầy đủ, template có thể chạy tốt. Nhưng ngoài production, có thể gặp:

- customerName là null, chuỗi rỗng hoặc chỉ chứa khoảng trắng.
- deliveryAddress không có vì khách hàng chọn nhận tại cửa hàng.
- items là danh sách rỗng hoặc null do dữ liệu nguồn chưa được chuẩn bị.
- Một dòng sản phẩm thiếu tên hoặc giá hiển thị.
- URL theo dõi đơn hàng chưa được tạo.
- Tên khách hàng chứa ký tự <, &, dấu nháy hoặc Unicode.
- Một biến bắt buộc bị quên khi render, khiến email có chỗ trống hoặc lỗi template.

**Kiểm thử template với dữ liệu đầy đủ và thiếu** giúp xác định hợp đồng dữ liệu của template, hành vi khi trường tùy chọn không có và phản ứng khi dữ liệu bắt buộc không hợp lệ. Mục tiêu không chỉ là “render không ném exception”, mà là nội dung sinh ra đúng, không gây hiểu nhầm, không làm lộ dữ liệu và vẫn dễ đọc trong các tình huống thực tế.

## 2. Phân biệt template rendering với gửi email

Một hệ thống gửi email thường có các bước:

~~~text
Business data
    |
    v
Application service
    |
    v
Email model / DTO
    |
    v
Template renderer
    |
    +--> Subject
    |
    +--> text/plain body
    |
    +--> text/html body
              |
              v
         MimeMessageHelper
              |
              v
         JavaMailSender
              |
              v
          SMTP server
~~~

Mỗi bước có một phạm vi kiểm thử riêng:

| Thành phần | Cần kiểm tra | Có cần SMTP không? |
|---|---|---|
| Chuẩn bị dữ liệu nghiệp vụ | Đúng dữ liệu, đúng quyền, đúng quy tắc | Không |
| Model truyền cho template | Trường bắt buộc/tùy chọn, giá trị mặc định | Không |
| Template renderer | Nội dung, điều kiện, vòng lặp, escaping, locale | Không |
| Ghép MIME message | Subject, charset, text/html, attachment | Không cần server SMTP; có thể kiểm tra bằng Jakarta Mail |
| SMTP adapter | Gọi JavaMailSender đúng message, xử lý lỗi transport | Có thể mock sender |
| SMTP integration | Giao thức, phản hồi, TLS/AUTH theo môi trường | Cần SMTP test server |

**Kiểm thử template không nên phụ thuộc SMTP thật.** Một template sai phải được phát hiện bằng test nhanh, lặp lại được và không cần credential. Nếu test render template phải kết nối provider, ranh giới giữa trình bày nội dung và transport đã bị trộn.

Một template có thể được render đúng nhưng SMTP gửi thất bại; ngược lại, SMTP có thể chấp nhận email có template sai. Hai kết quả này phải được quan sát độc lập.

## 3. Xác định hợp đồng dữ liệu trước khi viết test

Trước khi tạo test case, hãy phân loại mỗi biến mà template sử dụng:

| Nhóm | Ví dụ | Khi thiếu thì làm gì? |
|---|---|---|
| **Bắt buộc** | Mã đơn hàng, email người nhận, tổng tiền cần xác nhận | Validate và từ chối render hoặc từ chối tạo yêu cầu gửi |
| **Tùy chọn** | Địa chỉ giao hàng, mã khuyến mãi, URL theo dõi | Ẩn phần tương ứng hoặc hiển thị thông điệp thay thế |
| **Có mặc định** | Tên hiển thị, lời chào chung, nhãn phụ | Dùng fallback đã được quy định |
| **Danh sách có thể rỗng** | Sản phẩm, dòng hóa đơn, lịch sử thay đổi | Hiển thị empty state hoặc ẩn khối danh sách |
| **Dữ liệu định dạng** | Ngày giờ, số tiền, số lượng | Chuẩn hóa trước khi render hoặc định dạng theo locale |
| **Dữ liệu nhạy cảm** | Token, mã xác thực, thông tin cá nhân | Chỉ đưa vào khi cần và theo chính sách bảo vệ |

Phân loại này ngăn hai lỗi trái ngược:

- **Thiếu dữ liệu bắt buộc nhưng vẫn gửi email:** người nhận nhận một thông báo không thể sử dụng, ví dụ “Mã đơn hàng: null”.
- **Thiếu dữ liệu tùy chọn làm cả email thất bại:** khách hàng không có địa chỉ giao hàng nhưng vẫn nhận được email xác nhận đơn hàng hợp lệ.

Template không nên tự quyết định mọi quy tắc nghiệp vụ. Ví dụ, đơn hàng bắt buộc có mã đơn là quy tắc của application/domain layer; template chỉ hiển thị mã đó. Ngược lại, ẩn dòng địa chỉ khi không có địa chỉ là quy tắc trình bày, có thể được biểu diễn bằng điều kiện trong template.

### Ví dụ model rõ ràng

~~~java
import java.util.List;

public record OrderConfirmationModel(
        String orderNumber,
        String customerName,
        String deliveryAddress,
        List<OrderLineModel> items,
        String trackingUrl,
        String placedAtText,
        String totalText) {
}

public record OrderLineModel(
        String name,
        String quantityText,
        String lineTotalText) {
}
~~~

placedAtText và totalText ở đây đã được định dạng trước theo locale mong muốn. Cách này giúp template không phải tự thực hiện logic tiền tệ hoặc chuyển đổi thời gian phức tạp. Nếu muốn template tự định dạng ngày/tiền, cần khai báo rõ locale và test kết quả ở nhiều locale.

## 4. Thiết kế template có xử lý trường thiếu

Ví dụ file **templates/mail/order-confirmation.html**:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body>
  <h1>Đơn hàng đã được xác nhận</h1>

  <p>
    Xin chào,
    <strong th:text="${customerName} ?: 'bạn'">bạn</strong>!
  </p>

  <p>
    Mã đơn hàng:
    <strong th:text="${orderNumber}">ORD-001</strong>
  </p>

  <p th:if="${placedAtText != null and !#strings.isEmpty(placedAtText)}">
    Thời gian đặt:
    <span th:text="${placedAtText}">12/11/2026</span>
  </p>

  <section th:if="${deliveryAddress != null and !#strings.isEmpty(deliveryAddress)}">
    <h2>Địa chỉ giao hàng</h2>
    <p th:text="${deliveryAddress}">Địa chỉ mẫu</p>
  </section>

  <section>
    <h2>Sản phẩm</h2>
    <ul th:if="${items != null and !#lists.isEmpty(items)}">
      <li th:each="item : ${items}">
        <span th:text="${item.name}">Sản phẩm</span>
        <span> — </span>
        <span th:text="${item.quantityText}">1</span>
        <span> — </span>
        <span th:text="${item.lineTotalText}">100.000 đ</span>
      </li>
    </ul>
    <p th:unless="${items != null and !#lists.isEmpty(items)}">
      Chi tiết sản phẩm sẽ được cập nhật trong đơn hàng của bạn.
    </p>
  </section>

  <p>
    Tổng cộng:
    <strong th:text="${totalText}">100.000 đ</strong>
  </p>

  <p th:if="${trackingUrl != null and !#strings.isEmpty(trackingUrl)}">
    <a th:href="${trackingUrl}">Theo dõi đơn hàng</a>
  </p>
</body>
</html>
~~~

Template trên minh họa các hành vi:

- Tên khách hàng có fallback “bạn” nếu biến không có giá trị.
- Địa chỉ và thời gian đặt chỉ xuất hiện khi có nội dung.
- Danh sách sản phẩm được lặp khi không null và không rỗng.
- Khi không có sản phẩm, email hiển thị một câu thay thế.
- Link theo dõi chỉ xuất hiện khi có URL.
- Các giá trị hiển thị dùng **th:text**, giúp escape nội dung HTML thay vì đưa dữ liệu động vào markup thô.

**Mã đơn hàng và tổng tiền là dữ liệu bắt buộc** trong ví dụ. Không nên dùng fallback giả như ORD-001 hoặc 100.000 đ trong email thực tế nếu dữ liệu nguồn bị thiếu. Các giá trị nằm giữa thẻ chỉ là nội dung mẫu khi preview/template engine không xử lý thuộc tính Thymeleaf; renderer phải validate trường bắt buộc trước khi gửi.

th:href nhận giá trị URL động. Nếu URL có thể xuất phát từ người dùng hoặc nguồn không tin cậy, cần xác thực scheme/host theo chính sách ứng dụng trước khi truyền vào template. HTML escaping không tự bảo đảm URL an toàn.

## 5. Cấu hình Thymeleaf renderer dùng UTF-8

Spring Framework Mail không bắt buộc dùng một template engine cụ thể. Có thể dùng Thymeleaf, FreeMarker, Mustache hoặc renderer riêng. Ví dụ dưới đây chọn **Thymeleaf** để minh họa cách truyền model và kiểm thử các nhánh điều kiện.

Một template resolver cần biết vị trí resource, phần mở rộng, template mode và charset:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;
import org.thymeleaf.templatemode.TemplateMode;

@Configuration
public class MailTemplateConfiguration {

    @Bean
    ClassLoaderTemplateResolver mailTemplateResolver() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);
        resolver.setCheckExistence(true);
        return resolver;
    }

    @Bean
    SpringTemplateEngine mailTemplateEngine(
            ClassLoaderTemplateResolver mailTemplateResolver) {
        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(mailTemplateResolver);
        return engine;
    }
}
~~~

Ví dụ này tạo một resolver cho mail template nằm trong **classpath:/templates/**. setCacheable(false) thuận tiện khi phát triển và test để template được đọc lại; production có thể bật cache tùy cách triển khai và cập nhật tài nguyên. Nếu ứng dụng đã dùng Thymeleaf auto-configuration, cần tránh đăng ký resolver chồng lấp hoặc làm thay đổi resolver của template web ngoài ý muốn. Có thể dùng một cấu hình engine/resolver riêng cho mail hoặc cấu hình resolver order rõ ràng.

Đường dẫn **mail/order-confirmation** khi gọi process(...) sẽ được resolver nối prefix và suffix để tìm **templates/mail/order-confirmation.html**.

### Renderer tạo Context từ model

~~~java
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Component
public class OrderConfirmationTemplateRenderer {
    private final SpringTemplateEngine templateEngine;

    public OrderConfirmationTemplateRenderer(
            SpringTemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String render(
            OrderConfirmationModel model,
            Locale locale) {
        validateRequiredFields(model);

        Context context = new Context(locale);
        context.setVariable("orderNumber", model.orderNumber());
        context.setVariable("customerName", model.customerName());
        context.setVariable("deliveryAddress", model.deliveryAddress());
        context.setVariable("items", model.items());
        context.setVariable("trackingUrl", model.trackingUrl());
        context.setVariable("placedAtText", model.placedAtText());
        context.setVariable("totalText", model.totalText());

        return templateEngine.process(
                "mail/order-confirmation", context);
    }

    private static void validateRequiredFields(
            OrderConfirmationModel model) {
        if (model == null) {
            throw new IllegalArgumentException(
                    "Order confirmation model is required");
        }
        if (model.orderNumber() == null
                || model.orderNumber().isBlank()) {
            throw new IllegalArgumentException(
                    "Order number is required");
        }
        if (model.totalText() == null || model.totalText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order total is required");
        }
    }
}
~~~

Ở đây orderNumber và totalText là bắt buộc; customerName, deliveryAddress, items, trackingUrl và placedAtText được template xử lý theo quy tắc tùy chọn. Nếu hợp đồng nghiệp vụ khác, hãy sửa validator và template cùng nhau. Không nên để một trường vừa được xem là bắt buộc ở service nhưng lại âm thầm có fallback giả trong template.

Nếu dự án dùng **Thymeleaf 3.1 + Spring 6**, org.thymeleaf.spring6.SpringTemplateEngine là adapter Spring 6. Với Spring 5, package integration và dependency tương ứng khác; dùng phiên bản Thymeleaf phù hợp với phiên bản Spring thực tế.
## 6. Viết test cho trường hợp dữ liệu đầy đủ

Test dữ liệu đầy đủ chứng minh template có thể hiển thị toàn bộ nội dung quan trọng khi mọi trường cần thiết đều có giá trị. Bộ dữ liệu nên gần với tình huống thật, không chỉ là các chuỗi ngắn “A”, “B”, “C”.

Ví dụ fixture:

~~~java
import java.util.List;

final class OrderMailFixtures {
    private OrderMailFixtures() {
    }

    static OrderConfirmationModel completeOrder() {
        return new OrderConfirmationModel(
                "ORD-2026-00125",
                "Nguyễn Minh Anh",
                "12 Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh",
                List.of(
                        new OrderLineModel(
                                "Bàn phím cơ màu trắng",
                                "1",
                                "1.250.000 ₫"),
                        new OrderLineModel(
                                "Chuột không dây",
                                "2",
                                "980.000 ₫")),
                "https://shop.example.test/orders/ORD-2026-00125",
                "12/11/2026 09:30",
                "2.230.000 ₫");
    }
}
~~~

Dữ liệu fixture có tiếng Việt, dấu câu, tiền tệ, nhiều sản phẩm và URL. Nó giúp phát hiện lỗi encoding, lặp danh sách và việc hiển thị các trường dài hơn những placeholder đơn giản.

Một test với **JUnit Jupiter** và **AssertJ**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationTemplateRendererTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);

        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rendersCompleteOrderData() {
        String html = renderer.render(
                OrderMailFixtures.completeOrder(),
                Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("Nguyễn Minh Anh")
                .contains("ORD-2026-00125")
                .contains("12 Nguyễn Huệ")
                .contains("Bàn phím cơ màu trắng")
                .contains("Chuột không dây")
                .contains("1.250.000 ₫")
                .contains("2.230.000 ₫")
                .contains("12/11/2026 09:30")
                .contains("Theo dõi đơn hàng")
                .contains("https://shop.example.test/orders/ORD-2026-00125");
    }
}
~~~

Test giả định file template được đóng gói trên test classpath tại **src/main/resources/templates/mail/order-confirmation.html**. Resolver trong test dùng prefix và suffix tương ứng. Nếu template nằm trong src/test/resources hoặc có tên khác, cần điều chỉnh resolver/resource path cho đúng.

Test này chỉ dựng SpringTemplateEngine và renderer; **không khởi động SMTP, không cần JavaMailSender và không gửi email thật**. Đây là unit test cho rendering. Khi dùng Spring Boot auto-configuration của Thymeleaf, có thể inject engine đã cấu hình, nhưng cần chắc chắn test đang dùng đúng resolver dành cho mail.

### Kiểm tra các vùng nội dung theo ý nghĩa

Thay vì chỉ assert toàn bộ HTML không rỗng, nên xác nhận:

- Mã đơn xuất hiện chính xác một hoặc số lần theo thiết kế.
- Từng dòng sản phẩm xuất hiện, đúng thứ tự nếu thứ tự là yêu cầu.
- Tổng tiền và ngày giờ đã được định dạng.
- Link có đúng URL đã được chuẩn bị.
- Tên khách hàng được chèn vào vị trí lời chào.
- Không xuất hiện placeholder mẫu như “ORD-001” nếu nội dung thực phải dùng dữ liệu model.

Có thể kiểm tra một vài nội dung cụ thể:

~~~java
assertThat(html).contains("Bàn phím cơ màu trắng");
assertThat(html).contains("Chuột không dây");
assertThat(html).doesNotContain("Tên sản phẩm");
~~~

Không cần assert từng khoảng trắng hoặc newline của HTML nếu chúng không phải hợp đồng của template. Assertion nên tập trung vào nội dung và cấu trúc có ý nghĩa.

## 7. Test khi trường tùy chọn bị thiếu

Đây là nhóm test quan trọng vì dữ liệu thực tế thường không đầy đủ như fixture lý tưởng. Ví dụ model có mã đơn và tổng tiền hợp lệ nhưng không có tên khách hàng, địa chỉ, thời gian đặt, tracking URL hoặc danh sách sản phẩm.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationMissingDataTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rendersFallbackAndHidesOptionalSections() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-00999",
                null,
                null,
                List.of(),
                null,
                null,
                "450.000 ₫");

        String html = renderer.render(
                model, Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("Xin chào")
                .contains(">bạn</strong>")
                .contains("ORD-2026-00999")
                .contains("450.000 ₫")
                .contains("Chi tiết sản phẩm sẽ được cập nhật")
                .doesNotContain("Địa chỉ giao hàng")
                .doesNotContain("Thời gian đặt:")
                .doesNotContain("Theo dõi đơn hàng")
                .doesNotContain("null");
    }
}
~~~

Kết quả mong muốn:

- Lời chào dùng fallback “bạn”.
- Địa chỉ giao hàng không xuất hiện.
- Thời gian đặt không xuất hiện.
- Danh sách sản phẩm rỗng được thay bằng thông báo phù hợp.
- Không xuất hiện chuỗi “null” trong nội dung người nhận.
- Mã đơn và tổng tiền vẫn hiển thị vì chúng là trường bắt buộc.

### Kiểm tra danh sách null và danh sách rỗng

**null** và **empty list** là hai trạng thái khác nhau trong Java. Template cần được thiết kế theo hợp đồng rõ ràng. Nếu cả hai đều có nghĩa “không có dòng sản phẩm để hiển thị”, hãy test cả hai:

~~~java
@Test
void handlesNullItemList() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-01000",
            "Khách hàng",
            null,
            null,
            null,
            null,
            "0 ₫");

    String html = renderer.render(model, Locale.forLanguageTag("vi-VN"));

    assertThat(html)
            .contains("Chi tiết sản phẩm sẽ được cập nhật")
            .doesNotContain("Tên sản phẩm");
}
~~~

Nếu items null là trạng thái dữ liệu bất hợp lệ theo domain, hãy **validate và từ chối** thay vì coi nó giống empty list. Quyết định này thuộc hợp đồng của model, không nên để test tự suy đoán.

### Kiểm tra chuỗi rỗng và chỉ có khoảng trắng

Template dùng **#strings.isEmpty(...)** có thể phân biệt chuỗi rỗng theo quy tắc của thư viện, nhưng chuỗi chỉ chứa khoảng trắng có thể vẫn được coi là có nội dung. Nếu yêu cầu coi blank là thiếu, hãy chuẩn hóa dữ liệu ở application layer:

~~~java
private static String optionalText(String value) {
    if (value == null || value.isBlank()) {
        return null;
    }
    return value.trim();
}
~~~

Sau đó truyền giá trị đã chuẩn hóa cho template. Test riêng các trường hợp **null**, chuỗi rỗng, chỉ khoảng trắng và chuỗi có nội dung giúp tránh việc email hiển thị một section chỉ chứa khoảng trắng.

## 8. Test dữ liệu bắt buộc bị thiếu hoặc không hợp lệ

Với trường bắt buộc, hành vi đúng thường là **dừng trước khi render**, thay vì để template tự hiển thị null, chuỗi rỗng hoặc placeholder giả.

Ví dụ kiểm tra order number:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderConfirmationRequiredDataTest {
    private OrderConfirmationTemplateRenderer renderer;

    @BeforeEach
    void setUp() {
        ClassLoaderTemplateResolver resolver =
                new ClassLoaderTemplateResolver();
        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);
        renderer = new OrderConfirmationTemplateRenderer(engine);
    }

    @Test
    void rejectsMissingOrderNumber() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                null,
                "Nguyễn An",
                null,
                List.of(),
                null,
                null,
                "100.000 ₫");

        assertThatThrownBy(() ->
                renderer.render(model, Locale.forLanguageTag("vi-VN")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Order number is required");
    }

    @Test
    void rejectsBlankTotal() {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-001",
                "Nguyễn An",
                null,
                List.of(),
                null,
                null,
                "   ");

        assertThatThrownBy(() ->
                renderer.render(model, Locale.forLanguageTag("vi-VN")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Order total is required");
    }
}
~~~

Test cần chứng minh lỗi xảy ra **trước khi gửi SMTP**. Nếu renderer chỉ tạo chuỗi HTML, việc ném IllegalArgumentException phù hợp với ví dụ. Một hệ thống có thể dùng Bean Validation và exception chuyên biệt khác; điều quan trọng là không gửi email không đủ dữ liệu.

Các trường có thể là bắt buộc trong một loại email nhưng tùy chọn trong loại khác. Không nên tạo một validator dùng chung quá rộng rồi áp đặt cùng quy tắc cho mọi template. Hãy định nghĩa model và validation theo từng email use case.
## 9. Test HTML escaping với dữ liệu không tin cậy

Template email thường chèn tên khách hàng, tên sản phẩm hoặc ghi chú do người dùng nhập. Nếu dùng **th:text**, Thymeleaf escape nội dung để ký tự đặc biệt được hiển thị như văn bản. Nếu dùng **th:utext**, nội dung được đưa vào HTML như markup và có thể tạo lỗ hổng nếu dữ liệu không được kiểm soát.

Ví dụ test với tên khách hàng chứa HTML:

~~~java
@Test
void escapesCustomerNameInsteadOfRenderingMarkup() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-02000",
            "<img src=x onerror=alert(1)> & khách",
            null,
            List.of(),
            null,
            null,
            "100.000 ₫");

    String html = renderer.render(model, Locale.forLanguageTag("vi-VN"));

    assertThat(html)
            .contains("&lt;img")
            .contains("&amp; khách")
            .doesNotContain("<img src=x");
}
~~~

Test này chứng minh dữ liệu được hiển thị như text trong HTML. Không nên chỉ kiểm tra chuỗi gốc có xuất hiện hay không, vì output đã escape nên nội dung có thể được biểu diễn bằng entity như **&lt;** và **&amp;**.

### Không dùng th:utext cho dữ liệu người dùng tùy tiện

~~~html
<!-- An toàn hơn cho text thông thường: -->
<span th:text="${customerName}">Khách hàng</span>

<!-- Chỉ dùng khi giá trị là HTML đã được tin cậy và kiểm soát: -->
<div th:utext="${trustedHtmlFragment}"></div>
~~~

**th:utext** không escape markup. Chỉ dùng khi nội dung HTML được tạo bởi nguồn tin cậy hoặc đã qua sanitizer phù hợp với ngữ cảnh. Việc dữ liệu có UTF-8 hợp lệ không làm nó an toàn khi đưa vào HTML.

### URL cần chính sách riêng

Escape HTML attribute không đồng nghĩa xác thực URL. Nếu trackingUrl có thể bị người dùng kiểm soát, cần kiểm tra scheme/host cho phép, chẳng hạn chỉ chấp nhận HTTPS và domain của hệ thống. Test nên bao gồm:

- URL HTTPS thuộc domain hợp lệ được hiển thị.
- URL null hoặc rỗng làm ẩn link.
- Scheme không được phép như javascript: bị từ chối trước khi render hoặc trước khi tạo mail.
- URL có ký tự query đặc biệt được encode đúng.

Không nên chỉ assert template không ném exception khi nhận URL bất kỳ.

## 10. Test danh sách có phần tử đầy đủ và thiếu thuộc tính

Một danh sách không rỗng chưa chắc mọi phần tử đều hợp lệ. Ví dụ một dòng sản phẩm có tên nhưng thiếu số lượng, hoặc có số lượng nhưng thiếu giá dòng. Nếu những trường đó là bắt buộc để người nhận hiểu đơn hàng, cần validate từng phần tử trước khi render.

Có thể bổ sung validation cho danh sách:

~~~java
private static void validateItems(
        java.util.List<OrderLineModel> items) {
    if (items == null) {
        return; // Chỉ hợp lệ nếu null có nghĩa là không có danh sách.
    }

    for (int index = 0; index < items.size(); index++) {
        OrderLineModel item = items.get(index);
        if (item == null) {
            throw new IllegalArgumentException(
                    "Order item at index " + index + " is required");
        }
        if (item.name() == null || item.name().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item name is required at index " + index);
        }
        if (item.quantityText() == null
                || item.quantityText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item quantity is required at index " + index);
        }
        if (item.lineTotalText() == null
                || item.lineTotalText().isBlank()) {
            throw new IllegalArgumentException(
                    "Order item total is required at index " + index);
        }
    }
}
~~~

Sau đó gọi validateItems trong bước kiểm tra model trước khi render. Quy tắc trên là ví dụ cho email xác nhận đơn hàng; nếu nghiệp vụ cho phép một số giá trị vắng mặt, hãy điều chỉnh hợp đồng thay vì áp dụng validation cứng.

Test phần tử thiếu tên:

~~~java
@Test
void rejectsAnItemWithoutName() {
    OrderConfirmationModel model = new OrderConfirmationModel(
            "ORD-2026-02001",
            "Nguyễn An",
            null,
            List.of(new OrderLineModel(null, "1", "50.000 ₫")),
            null,
            null,
            "50.000 ₫");

    assertThatThrownBy(() ->
            renderer.render(model, Locale.forLanguageTag("vi-VN")))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Order item name is required");
}
~~~

Nếu template được thiết kế để hiển thị các dòng thiếu một trường bằng placeholder như “Đang cập nhật”, test cần assert chính xác hành vi đó. Không để trường hợp này vô tình biến thành chuỗi “null” hoặc một dòng trống khó hiểu.

### Kiểm tra số lượng phần tử

Với một đơn hàng có nhiều dòng, có thể xác nhận số item đã render:

~~~java
long renderedItems = java.util.regex.Pattern
        .compile("<li>")
        .matcher(html)
        .results()
        .count();

assertThat(renderedItems).isEqualTo(2);
~~~

Đếm thẻ HTML bằng regex chỉ phù hợp với template đơn giản có markup ổn định. Nếu cấu trúc HTML phức tạp hoặc có thẻ li lồng nhau, dùng HTML parser để truy vấn DOM theo selector và đếm đúng phần tử thuộc danh sách sản phẩm.

## 11. Test locale, ngày giờ và tiền tệ

Template email có thể gửi cho người dùng ở nhiều ngôn ngữ. Việc render cùng model với locale khác nhau có thể thay đổi:

- Subject và các nhãn như “Mã đơn hàng”, “Order number”.
- Cách hiển thị ngày giờ.
- Dấu phân cách hàng nghìn/thập phân.
- Ký hiệu và vị trí tiền tệ.
- Cách hiển thị số nhiều hoặc lời chào.

**Không nên dựa vào locale mặc định của JVM** vì môi trường developer, CI và production có thể khác nhau. Hãy truyền Locale tường minh cho renderer và kiểm tra kết quả của từng locale được hỗ trợ.

Ví dụ định dạng số tiền trước khi truyền vào template:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public final class MoneyTextFormatter {
    private MoneyTextFormatter() {
    }

    public static String formatVnd(BigDecimal amount, Locale locale) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(java.util.Currency.getInstance("VND"));
        return formatter.format(amount);
    }
}
~~~

Kết quả hiển thị cụ thể phụ thuộc locale provider/JDK và quy ước tiền tệ. Với hệ thống cần format ổn định tuyệt đối, có thể quy định rõ scale, dấu phân cách và ký hiệu tiền tệ theo chính sách sản phẩm thay vì phụ thuộc môi trường.

Test có thể xác nhận các locale được hỗ trợ:

~~~java
@Test
void rendersVietnameseAndEnglishLabels() {
    OrderConfirmationModel model = OrderMailFixtures.completeOrder();

    String vietnamese = renderer.render(
            model, Locale.forLanguageTag("vi-VN"));
    String english = renderer.render(
            model, Locale.forLanguageTag("en-US"));

    assertThat(vietnamese).contains("Mã đơn hàng");
    assertThat(english).contains("Order number");
}
~~~

Đoạn test này giả định template dùng message bundle cho nhãn thay vì hard-code tiếng Việt như template minh họa ở trên. Khi triển khai i18n, nên tách template message key khỏi nội dung cố định và cung cấp các file resource tương ứng.

### Dùng MessageSource cho subject và nhãn

Subject thường được tạo riêng với body HTML. Có thể dùng Spring **MessageSource** để lấy subject theo locale:

~~~properties
# messages_vi.properties
mail.order-confirmation.subject=Xác nhận đơn hàng {0}
~~~

~~~properties
# messages_en.properties
mail.order-confirmation.subject=Order confirmation {0}
~~~

~~~java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Component;

@Component
public class MailSubjectFactory {
    private final MessageSource messageSource;

    public MailSubjectFactory(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String orderConfirmation(String orderNumber, Locale locale) {
        return messageSource.getMessage(
                "mail.order-confirmation.subject",
                new Object[] {orderNumber},
                locale);
    }
}
~~~

Test subject factory riêng để bảo đảm message key có đủ bản dịch, placeholder được thay đúng và fallback locale theo chính sách. Khi ghép vào MimeMessage, truyền chuỗi Unicode cho setSubject; Jakarta Mail xử lý MIME header encoding.

## 12. Kiểm tra subject, body text và body HTML cùng nhau

Một email hoàn chỉnh có thể chứa:

- Subject được tạo bởi MessageSource hoặc subject factory.
- Body text/plain cho client không render HTML.
- Body text/html cho client có hỗ trợ HTML.
- Attachment hoặc inline resource nếu cần.

Không nên chỉ test HTML template rồi giả định subject và text/plain tự động đúng. Hãy kiểm tra từng phần ở ranh giới tương ứng.

Ví dụ tạo MIME message từ subject và nội dung đã render:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderConfirmationMailComposer {
    private final JavaMailSender sender;
    private final OrderConfirmationTemplateRenderer renderer;
    private final MailSubjectFactory subjects;

    public OrderConfirmationMailComposer(
            JavaMailSender sender,
            OrderConfirmationTemplateRenderer renderer,
            MailSubjectFactory subjects) {
        this.sender = sender;
        this.renderer = renderer;
        this.subjects = subjects;
    }

    public MimeMessage compose(
            OrderConfirmationModel model,
            String recipient,
            Locale locale) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject(subjects.orderConfirmation(
                model.orderNumber(), locale));

        String plain = "Đơn hàng " + model.orderNumber()
                + " đã được xác nhận.";
        String html = renderer.render(model, locale);
        helper.setText(plain, html);
        return message;
    }
}
~~~

Đây là composer minh họa. Trong ứng dụng thật, plain text nên được tạo từ một template riêng hoặc cùng một model/template abstraction để tránh nội dung text và HTML lệch nhau. Hàm compose **chỉ tạo MimeMessage**, không gửi SMTP; phần gọi sender.send(message) có thể nằm ở adapter riêng.

Với multipart/alternative, test có thể parse message sau serialize và xác nhận cả hai part:

~~~java
MimeMessage message = composer.compose(
        OrderMailFixtures.completeOrder(),
        "alice@example.test",
        Locale.forLanguageTag("vi-VN"));

message.saveChanges();
Object content = message.getContent();

// Với multipart/alternative, duyệt các BodyPart và kiểm tra
// text/plain cùng text/html sau khi Jakarta Mail decode.
~~~

Vì cấu trúc MIME có thể lồng nhiều multipart, test nên tìm part theo **Content-Type** thay vì giả định luôn có một vị trí index cố định.
## 13. Trường hợp biến không được truyền vào Context

Có hai tình huống dễ bị gộp chung:

1. Model có property nhưng giá trị của nó là **null**.
2. Template renderer **không đặt biến đó** vào Context.

Tùy template engine và cách biểu thức được viết, biến không tồn tại có thể được coi như null, trả về chuỗi rỗng hoặc gây lỗi khi truy cập thuộc tính con. Không nên dựa vào hành vi ngầm định này để bảo vệ dữ liệu bắt buộc.

Ví dụ với Thymeleaf:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("orderNumber", "ORD-001");
// Cố ý không đặt customerName.

String html = templateEngine.process(
        "mail/order-confirmation", context);
~~~

Template có thể render với tên khách hàng rỗng hoặc fallback tùy biểu thức. Nếu trường là bắt buộc, **validate model trước khi gọi process(...)**. Nếu trường tùy chọn, template phải thể hiện rõ cách ẩn/fallback và test hành vi đó.

### Không dùng lỗi template để thay thế validation

Một cách viết như:

~~~html
<span th:text="${order.customer.name}"></span>
~~~

có thể gặp vấn đề nếu order hoặc customer không tồn tại. Nếu đây là dữ liệu bắt buộc, application service nên tạo model hợp lệ hoặc báo lỗi nghiệp vụ cụ thể trước khi render. Nếu customer là tùy chọn, nên kiểm tra rõ:

~~~html
<span th:if="${order != null and order.customer != null}"
      th:text="${order.customer.name}">Khách hàng</span>
~~~

Trong thiết kế tốt hơn, template không nhận một object domain sâu với nhiều quan hệ có thể null. Hãy tạo **view model phẳng** chỉ chứa các trường cần hiển thị, giảm nguy cơ truy cập lazy property hoặc phụ thuộc cấu trúc entity.

## 14. Bộ dữ liệu kiểm thử nên bao phủ những trường hợp nào?

Một ma trận thực tế có thể được tổ chức theo nhóm:

| Bộ dữ liệu | Ví dụ | Kỳ vọng |
|---|---|---|
| **Đầy đủ** | Tên, địa chỉ, items, URL, thời gian, tổng tiền đều có | Tất cả section được render đúng |
| **Thiếu optional** | Tên null, không địa chỉ, URL null | Fallback/ẩn section theo thiết kế |
| **Empty collection** | items là danh sách rỗng | Empty state xuất hiện, không có item row |
| **Null collection** | items null | Theo hợp đồng: empty state hoặc validation error |
| **Blank text** | địa chỉ là chuỗi khoảng trắng | Chuẩn hóa thành null hoặc ẩn section |
| **Thiếu required** | orderNumber null/blank, total null | Render bị từ chối trước khi tạo email |
| **Phần tử không hợp lệ** | item null hoặc thiếu tên/số lượng | Validation lỗi hoặc placeholder đã quy định |
| **Unicode** | Tên tiếng Việt, ký tự có dấu, emoji | Nội dung được giữ đúng sau render |
| **HTML special characters** | Tên chứa <, >, &, dấu nháy | Được escape trong text node |
| **URL không hợp lệ** | Scheme không được phép | Bị từ chối trước khi render hoặc gửi |
| **Giá trị biên** | Tên rất dài, danh sách lớn, mã có dấu gạch | Không vỡ layout hoặc vượt giới hạn đã định |
| **Nhiều locale** | vi-VN và en-US | Nhãn, subject, ngày/tiền đúng locale |

Không nhất thiết phải tạo một test riêng cho mọi tổ hợp của mọi field. Hãy ưu tiên các trường có nhánh điều kiện, quy tắc validation hoặc tác động trực tiếp đến thông tin người nhận. Các tổ hợp có thể được tổ chức bằng **parameterized tests** nếu chúng dùng chung một kỳ vọng.
### Parameterized test cho chuỗi tùy chọn

Ví dụ kiểm tra địa chỉ null, rỗng và blank đều được ẩn sau khi chuẩn hóa:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class OptionalAddressTemplateTest {
    static Stream<String> missingAddresses() {
        return Stream.of(null, "", "   ");
    }

    @ParameterizedTest
    @MethodSource("missingAddresses")
    void hidesAddressWhenItIsMissing(String address) {
        OrderConfirmationModel model = new OrderConfirmationModel(
                "ORD-2026-03000",
                "Nguyễn An",
                optionalText(address),
                List.of(),
                null,
                null,
                "200.000 ₫");

        String html = renderer.render(
                model, Locale.forLanguageTag("vi-VN"));

        assertThat(html).doesNotContain("Địa chỉ giao hàng");
    }
}
~~~

Trong ví dụ, **renderer** là instance đã được cấu hình trong setup của test class và **optionalText** là hàm chuẩn hóa ở phần trước. Stream cung cấp các tình huống thiếu dữ liệu để cùng một assertion được thực hiện. Nếu không muốn chuẩn hóa trước, hãy viết template condition kiểm tra blank phù hợp với template engine và test trực tiếp hành vi đó.

## 15. Kiểm thử template trong Spring test context

Nếu template engine được cấu hình bằng Spring bean và renderer có dependency injection, có thể dùng **@SpringBootTest** để xác minh wiring và resource resolution:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MailTemplateSpringContextTest {
    @Autowired
    private OrderConfirmationTemplateRenderer renderer;

    @Test
    void rendersTemplateFromApplicationClasspath() {
        String html = renderer.render(
                OrderMailFixtures.completeOrder(),
                Locale.forLanguageTag("vi-VN"));

        assertThat(html)
                .contains("ORD-2026-00125")
                .contains("Nguyễn Minh Anh");
    }
}
~~~

Test này kiểm tra **Spring wiring, template resolver và resource được đóng gói trong application classpath**. Nếu ứng dụng còn auto-configure JavaMailSender và điều kiện tạo bean mail được bật, context có thể cần cấu hình SMTP host phù hợp hoặc mock sender. Nhưng renderer test không nên gọi send().

Nếu mục tiêu chỉ là render template, **không cần @SpringBootTest**. Dựng engine/resolver trực tiếp như các test trước thường nhanh hơn và cô lập hơn. Dùng Spring context khi muốn kiểm tra chính cấu hình resolver/bean thực tế được ứng dụng sử dụng.

### Test slice và mock sender

Một test MVC không cần khởi tạo SMTP để kiểm tra controller gọi application service. Một test application service có thể mock **MailPort**. Một test renderer có thể dựng Thymeleaf độc lập. Việc mock **JavaMailSender** chỉ có ý nghĩa khi test thành phần thực sự gọi sender.

Không thêm SMTP credential thật vào test properties. Không để profile test vô tình kế thừa host production từ cấu hình máy developer hoặc CI. Nếu test cần SMTP protocol, hãy dùng SMTP test server riêng và dữ liệu giả.

## 16. Phân biệt template lỗi với lỗi gửi mail

Template renderer và JavaMailSender có thể phát sinh lỗi ở các thời điểm khác nhau:

| Lỗi | Giai đoạn | Cách xử lý |
|---|---|---|
| Template không tồn tại | Resolve template | Kiểm tra tên, prefix/suffix và resource packaging |
| Thiếu biến bắt buộc | Validate model hoặc render | Bổ sung dữ liệu hoặc từ chối yêu cầu |
| Lỗi expression/loop | Render template | Kiểm tra property path và kiểu dữ liệu |
| Lỗi encoding/template resource | Đọc template hoặc tạo MIME | Kiểm tra charset của file và resolver |
| MIME preparation error | Tạo MimeMessage | Kiểm tra subject, body, attachment, địa chỉ |
| SMTP AUTH/connectivity error | Transport send | Kiểm tra host, port, TLS, credential và mạng |
| SMTP từ chối message | Giao dịch SMTP | Đọc response code, quota, kích thước và recipient policy |

Một cách tổ chức kết quả:

~~~text
PENDING
  |
  v
MODEL_VALIDATED
  |
  v
TEMPLATE_RENDERED
  |
  v
MIME_COMPOSED
  |
  v
SMTP_SUBMITTING
  |
  +--> SMTP_ACCEPTED
  |
  +--> SUBMISSION_FAILED
  |
  +--> SUBMISSION_UNKNOWN
~~~

Tên trạng thái là gợi ý nghiệp vụ, không phải enum có sẵn của Spring. Việc tách trạng thái giúp log và retry đúng nơi. Nếu template render thất bại, retry SMTP không giải quyết được. Nếu SMTP timeout sau khi gửi DATA, render lại không giải quyết sự không chắc chắn rằng server đã chấp nhận thư hay chưa.

### Đừng bắt exception rồi gửi email thiếu nội dung

Không nên làm:

~~~java
String html;
try {
    html = renderer.render(model, locale);
} catch (Exception ex) {
    html = "<p>Hello</p>"; // Fallback chung có thể che lỗi dữ liệu.
}
mailSender.send(buildMessage(html));
~~~

Cách này có thể biến lỗi template thành email thiếu thông tin, khiến người nhận hiểu nhầm. Nếu có fallback, fallback phải là **một template đã được thiết kế và kiểm thử riêng**, không phải một chuỗi HTML tùy tiện trong catch block. Với email quan trọng, thường nên dừng, ghi nhận lỗi rendering và chuyển yêu cầu sang trạng thái cần xử lý.
## 17. Kiểm tra subject và các template text riêng

Subject thường không nằm trong file HTML body. Nếu dùng **MessageSource**, subject là một phần nội dung cần test riêng theo locale và dữ liệu thay thế.

Ví dụ với subject tiếng Việt:

~~~properties
# messages_vi.properties
mail.order-confirmation.subject=Xác nhận đơn hàng {0}
~~~

Test subject factory:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.ResourceBundleMessageSource;

class MailSubjectFactoryTest {
    @Test
    void resolvesVietnameseSubject() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");

        MailSubjectFactory factory = new MailSubjectFactory(source);
        String subject = factory.orderConfirmation(
                "ORD-2026-00125", Locale.forLanguageTag("vi"));

        assertThat(subject)
                .isEqualTo("Xác nhận đơn hàng ORD-2026-00125");
    }
}
~~~

Ví dụ giả định file **messages_vi.properties** nằm ở root classpath và có đúng message key. Trong ứng dụng Spring Boot, MessageSource có thể được auto-configure; test trực tiếp ResourceBundleMessageSource giúp cô lập việc tra cứu bundle. Cần thống nhất basename và tên file theo cấu hình thực tế.

Nếu subject có dữ liệu người dùng, không nên nối trực tiếp nội dung không kiểm soát vào header. Validate độ dài, loại bỏ CR/LF theo chính sách và truyền chuỗi Unicode qua API setSubject để Jakarta Mail xử lý MIME header encoding.

### Nếu body có cả template text và HTML

Một số ứng dụng dùng hai file riêng:

~~~text
templates/mail/order-confirmation.txt
templates/mail/order-confirmation.html
~~~

Nên kiểm thử hai renderer riêng hoặc một **EmailContentRenderer** trả về cặp text/html. Test phải bảo đảm cả hai phiên bản chứa cùng các dữ liệu nghiệp vụ quan trọng: mã đơn, tổng tiền và thông tin hỗ trợ. Không nhất thiết hai bản phải có cùng câu chữ, nhưng không được mâu thuẫn.

## 18. Kiểm tra MIME sau khi render template

Sau khi template đã render, ứng dụng thường đưa HTML vào **MimeMessageHelper**. Có thể kiểm tra bước ghép MIME riêng mà không mở SMTP connection:

1. Tạo một MimeMessage bằng Jakarta Mail Session trong test.
2. Đặt Subject, text/plain và HTML body.
3. Gọi saveChanges() rồi serialize bằng writeTo(...).
4. Parse lại message từ byte.
5. Đọc các MIME part theo Content-Type và assert nội dung đã decode.

Ví dụ tạo message:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.springframework.mail.javamail.MimeMessageHelper;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, StandardCharsets.UTF_8.name());

helper.setSubject("Xác nhận đơn hàng ORD-001");
helper.setText(
        "Đơn hàng ORD-001 đã được xác nhận.",
        "<html lang=\"vi\"><body><p>Đơn hàng "
                + "<strong>ORD-001</strong> đã được xác nhận.</p>"
                + "</body></html>");

message.saveChanges();
~~~

Test MIME có thể kiểm tra:

- Subject sau khi parse lại vẫn là chuỗi Unicode đúng.
- Message là multipart khi cần text/plain và text/html.
- Có part text/plain và part text/html.
- Body sau decode chứa mã đơn, tên khách hàng và nội dung mong đợi.
- Charset của part văn bản phù hợp với UTF-8.

Nếu message chứa attachment hoặc inline image, MIME có thể lồng nhiều lớp. Hãy duyệt cây multipart đệ quy và tìm part theo media type, không giả định HTML luôn ở vị trí đầu hoặc cuối.

**Test MIME không gửi thư.** Chỉ khi cần xác minh SMTP handshake, AUTH, STARTTLS hoặc phản hồi server mới cần SMTP test server. Cách tách này giúp tìm lỗi ở đúng lớp và tránh làm test template phụ thuộc mạng.

## 19. Những anti-pattern khi kiểm thử template

### Chỉ test với dữ liệu hoàn hảo

Nếu chỉ có một fixture đầy đủ, test không phát hiện được section rỗng, fallback không đúng hoặc lỗi khi danh sách không có phần tử. Hãy có ít nhất một trường hợp **đầy đủ**, một trường hợp **thiếu optional**, và các trường hợp **required invalid**.

### Dùng placeholder giả làm dữ liệu production

Nếu template để sẵn “ORD-001”, “Tên khách hàng” hoặc “100.000 đ” rồi quên thay bằng biến, email có thể chứa nội dung mẫu. Test nên assert dữ liệu thật xuất hiện và placeholder mẫu không còn xuất hiện ở những vị trí động.

### Chỉ assert HTML không rỗng

Một template có thể render ra hàng nghìn ký tự nhưng thiếu mã đơn, sai tên người nhận hoặc không có sản phẩm. Hãy assert nội dung quan trọng và điều kiện hiển thị.

### Chỉ kiểm tra một chuỗi null

Không xuất hiện chữ “null” là cần thiết nhưng chưa đủ. Một section có thể vẫn tồn tại với nội dung rỗng, dấu phân cách thừa hoặc lời chào không tự nhiên. Hãy kiểm tra cả **nội dung** và **sự có mặt/vắng mặt của section**.

### So sánh toàn bộ HTML dạng snapshot quá cứng

Snapshot đầy đủ có thể hữu ích khi template là giao diện cần kiểm soát markup, nhưng dễ vỡ khi chỉ thay đổi khoảng trắng, thứ tự thuộc tính hoặc formatting không ảnh hưởng nội dung. Với email template thông thường, ưu tiên kiểm tra DOM/selector hoặc nội dung có ý nghĩa. Dùng snapshot khi team thực sự muốn duyệt toàn bộ thay đổi template.

### Chỉ kiểm tra nội dung mà bỏ qua escaping

Tên người dùng có thể chứa HTML hoặc ký tự đặc biệt. Test dữ liệu bình thường không phát hiện được việc dùng th:utext không an toàn. Thêm trường hợp chứa <, >, & và xác nhận output được escape.

### Dùng SMTP production trong test

Test có thể gửi email thật đến người dùng, bị quota, thất bại khi mạng chập chờn hoặc thay đổi trạng thái hệ thống bên ngoài. Template test nên chạy độc lập. Integration test SMTP sử dụng test server/sandbox và dữ liệu giả.

### Dùng chung fixture mutable

Nếu test thay đổi List hoặc model dùng chung giữa các test, thứ tự chạy có thể làm kết quả khác nhau. Dùng factory tạo model mới cho mỗi test; collection nên bất biến hoặc không bị sửa sau khi dựng.

### Bỏ qua dữ liệu nested thiếu trường

Một danh sách có hai phần tử không có nghĩa hai phần tử đều hợp lệ. Test cần bao phủ phần tử null, tên rỗng, số lượng thiếu và các trường quan trọng theo nghiệp vụ.

### Không kiểm tra locale

Test chỉ chạy trên locale mặc định của máy developer có thể pass nhưng production hiển thị ngày/tiền khác. Truyền Locale tường minh và test các locale được hỗ trợ.

## 20. Quy trình xây dựng test suite cho một email template

Một quy trình dễ duy trì:

1. **Định nghĩa model**: liệt kê trường bắt buộc, tùy chọn, mặc định, collection và dữ liệu nhạy cảm.
2. **Chuẩn hóa dữ liệu**: trim chuỗi, định dạng ngày/tiền và validate URL/recipient ở lớp thích hợp.
3. **Viết template**: dùng điều kiện cho optional fields, empty state cho collection, fallback có ý nghĩa và escaping mặc định cho text.
4. **Test full fixture**: xác nhận toàn bộ dữ liệu và các dòng lặp xuất hiện.
5. **Test thiếu optional**: null, empty, blank và collection rỗng/null theo hợp đồng.
6. **Test thiếu required**: renderer hoặc application service từ chối trước khi tạo email.
7. **Test dữ liệu đặc biệt**: Unicode, ký tự HTML, URL, giá trị dài và locale.
8. **Test subject/text/html**: xác nhận các phần của email cùng mô tả một sự kiện nghiệp vụ.
9. **Test MIME composition**: kiểm tra Content-Type, charset và body sau khi parse lại nếu cần.
10. **SMTP integration test**: chỉ thực hiện khi cần kiểm tra giao thức/transport, bằng server thử nghiệm.

Ma trận test có thể được lưu như tài liệu cạnh template:

| Case ID | Bộ dữ liệu | Kết quả mong đợi |
|---|---|---|
| TC-01 | Full order | Đầy đủ tên, địa chỉ, items, URL và tổng tiền |
| TC-02 | Customer name null | Dùng lời chào mặc định |
| TC-03 | Address null/blank | Ẩn section địa chỉ |
| TC-04 | Items empty | Hiển thị empty state |
| TC-05 | Items null | Theo hợp đồng đã chọn: empty state hoặc validation error |
| TC-06 | Order number blank | Từ chối render |
| TC-07 | Total missing | Từ chối render |
| TC-08 | Customer name chứa HTML | Escape thành text, không render markup |
| TC-09 | Tracking URL sai scheme | Từ chối trước khi gửi |
| TC-10 | Locale vi/en | Nhãn và định dạng phù hợp |
| TC-11 | Subject/body MIME | Nội dung Unicode được giữ sau round-trip |

Không phải mọi email đều cần đúng mười một test case. Bảng là một mẫu để xác định rủi ro và chọn trường hợp phù hợp với hợp đồng dữ liệu của từng template.

## 21. Tích hợp với service gửi mail mà không trộn trách nhiệm

Sau khi template được render và test độc lập, mail service có thể phối hợp renderer và sender:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailService {
    private final JavaMailSender sender;
    private final OrderConfirmationTemplateRenderer renderer;
    private final MailSubjectFactory subjectFactory;

    public OrderConfirmationMailService(
            JavaMailSender sender,
            OrderConfirmationTemplateRenderer renderer,
            MailSubjectFactory subjectFactory) {
        this.sender = sender;
        this.renderer = renderer;
        this.subjectFactory = subjectFactory;
    }

    public void send(
            OrderConfirmationModel model,
            String recipient,
            Locale locale) throws MessagingException {

        String html = renderer.render(model, locale);
        String subject = subjectFactory.orderConfirmation(
                model.orderNumber(), locale);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(html, true);

        sender.send(message);
    }
}
~~~

Đây là ví dụ gửi HTML đồng bộ. Trong hệ thống cần cả text/plain, có thể render hai template và gọi overload setText(plain, html). Nếu gửi sau transaction hoặc qua outbox, worker sẽ gọi service/adapter này sau khi job được claim. Dù cách dispatch nào, **renderer vẫn có thể test độc lập mà không gọi JavaMailSender**.

Một lưu ý về lỗi: nếu render thất bại, chưa có SMTP submission nào diễn ra. Nếu tạo MIME thất bại, chưa có message hợp lệ để gửi. Nếu send thất bại, cần phân loại lỗi transport và trạng thái SMTP; không gộp tất cả thành “template error”.

## 22. Nguyên tắc cần nhớ

**Dữ liệu đầy đủ** kiểm tra template có thể hiển thị toàn bộ thông tin. **Dữ liệu thiếu** kiểm tra email có giữ được ý nghĩa khi một phần thông tin tùy chọn vắng mặt. **Dữ liệu bắt buộc không hợp lệ** phải bị từ chối trước khi tạo email. Đây là ba nhóm khác nhau và cần được test rõ ràng.

Với Spring Framework Mail, có thể dùng Thymeleaf hoặc template engine khác để render HTML, sau đó truyền kết quả cho MimeMessageHelper và JavaMailSender. Hãy test renderer bằng dữ liệu fixture, không phụ thuộc SMTP; kiểm tra MIME riêng khi cần; và chỉ dùng SMTP test server cho bài test giao thức.

Một template đáng tin cậy là template có **hợp đồng dữ liệu rõ ràng**, xử lý null/empty/blank có chủ đích, escape dữ liệu không tin cậy, hiển thị empty state hợp lý và được kiểm tra bằng cả trường hợp đầy đủ lẫn thiếu. Điều đó giúp email vẫn chính xác và dễ hiểu khi dữ liệu thực tế khác với bộ mẫu lý tưởng.
