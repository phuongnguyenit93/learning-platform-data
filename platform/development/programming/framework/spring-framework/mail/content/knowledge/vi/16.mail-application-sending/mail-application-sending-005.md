# Map dữ liệu nghiệp vụ sang mail model

## 1. Vì sao cần một mail model riêng?

Trong ứng dụng dùng **Spring Framework Mail**, dữ liệu để gửi email thường đến từ nhiều nơi: đơn hàng, tài khoản người dùng, hóa đơn, lịch hẹn, giao dịch hoặc kết quả xử lý nghiệp vụ. Các đối tượng này được thiết kế để phục vụ nghiệp vụ và lưu trữ; cấu trúc của chúng không nhất thiết phù hợp với nội dung một email.

Ví dụ, một entity đơn hàng có thể chứa:

- ID nội bộ và quan hệ tới khách hàng.
- Các dòng sản phẩm dưới dạng collection lazy-loaded.
- Trạng thái thanh toán, thông tin vận chuyển và dữ liệu kiểm toán.
- Tham chiếu tới entity người dùng, địa chỉ và phương thức thanh toán.
- Trường nội bộ không cần hiển thị cho người nhận.

Nếu truyền nguyên entity đó vào template, email template sẽ phụ thuộc vào cấu trúc persistence và có thể vô tình truy cập dữ liệu không cần thiết. Thay đổi entity hoặc quan hệ JPA cũng có thể làm hỏng template.

Một cách tổ chức rõ ràng hơn là chuyển dữ liệu nghiệp vụ thành **mail model** (mô hình dữ liệu dành riêng cho email):

~~~text
Domain / application data
          |
          v
   Mail model mapper
          |
          v
    Mail model (DTO)
          |
          v
    Template renderer
          |
          +--> HTML body
          |
          +--> Plain-text body
          |
          v
    MimeMessageHelper
          |
          v
    JavaMailSender
~~~

Mail model chỉ chứa những giá trị mà email cần trình bày hoặc sử dụng. Nhờ đó:

- Template không cần biết entity được lưu trong database như thế nào.
- Dữ liệu được chọn, định dạng và kiểm tra trước khi render.
- Một mail model có thể dùng cho cả HTML và plain text.
- Có thể kiểm thử việc mapping mà không kết nối SMTP.
- Thay đổi giao diện email ít ảnh hưởng tới domain model.

> **Nguyên tắc:** Hãy chuyển dữ liệu nghiệp vụ thành một cấu trúc nhỏ, rõ nghĩa và ổn định trước khi render email. Template nhận dữ liệu đã chuẩn bị cho việc trình bày, không phải toàn bộ object graph của ứng dụng.

## 2. Phân biệt domain model, mail model và template context

Ba khái niệm có liên quan nhưng phục vụ những mục đích khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Domain model** | Biểu diễn quy tắc và trạng thái nghiệp vụ | `Order`, `Customer`, `Invoice` |
| **Mail model** | Chứa dữ liệu cần để dựng một loại email cụ thể | `OrderConfirmationMailModel` |
| **Template context/model** | Cung cấp biến cho template engine | Thymeleaf `Context` với biến `mail` |
| **Rendered content** | Nội dung sau khi template được xử lý | Chuỗi HTML và plain text |
| **MIME message** | Đóng gói nội dung và header để gửi | `MimeMessage` |

Ví dụ:

~~~java
// Dữ liệu nghiệp vụ (rút gọn).
public record OrderSummary(
        String orderNumber,
        String customerName,
        BigDecimal totalAmount,
        String currencyCode,
        Instant createdAt) {
}

// Dữ liệu chỉ dành cho email.
public record OrderConfirmationMailModel(
        String recipientName,
        String orderNumber,
        String orderDate,
        String totalAmount,
        String detailsUrl) {
}
~~~

`OrderSummary` mô tả kết quả nghiệp vụ. `OrderConfirmationMailModel` đã có các chuỗi được chuẩn bị để trình bày, như ngày và tiền tệ. Template không phải tự tìm thông tin khách hàng, tính tổng tiền hay tạo URL.

### 2.1. Mail model không phải bản sao của entity

Không nên tạo một DTO email chỉ bằng cách sao chép toàn bộ trường từ entity:

~~~java
// Không nên: model email phơi bày quá nhiều dữ liệu persistence.
public class OrderMailModel {
    private Long id;
    private CustomerEntity customer;
    private List<OrderLineEntity> lines;
    private PaymentEntity payment;
    private String internalNote;
    private String databaseStatus;
    // ...
}
~~~

Template không cần biết entity thanh toán hoặc quan hệ JPA. Nó thường chỉ cần:

~~~java
public record OrderMailModel(
        String orderNumber,
        String customerDisplayName,
        String paymentStatusLabel,
        String totalDisplay,
        List<OrderLineMailModel> items) {
}
~~~

Mail model nên phản ánh **những gì người nhận cần biết**, không phản ánh cách database lưu dữ liệu.

### 2.2. Một loại email nên có một model có ý nghĩa

Không nên dùng một `Map<String, Object>` khổng lồ cho mọi loại email với nhiều key tùy chọn:

~~~java
Map<String, Object> model = new HashMap<>();
model.put("name", name);
model.put("order", order);
model.put("invoice", invoice);
model.put("resetToken", token);
model.put("appointment", appointment);
~~~

Các template khác nhau có thể dùng những key khác nhau; lỗi chính tả hoặc thiếu key thường chỉ lộ ra lúc render. Thay vào đó, tạo model theo từng mục đích:

- `OrderConfirmationMailModel`
- `PasswordResetMailModel`
- `InvoiceReadyMailModel`
- `AppointmentReminderMailModel`

Tên kiểu dữ liệu cho biết template đang nhận loại thông tin nào và giúp compiler hỗ trợ khi mapping.

## 3. Xác định dữ liệu cần có trước khi viết mapper

Trước khi viết code, hãy mô tả email cần hiển thị. Ví dụ email xác nhận đơn hàng:

| Nội dung trong email | Nguồn dữ liệu nghiệp vụ | Mail model nên chứa |
| --- | --- | --- |
| Tên người nhận | Customer profile | `recipientName` |
| Mã đơn hàng | Order | `orderNumber` |
| Ngày đặt hàng | Order timestamp | `orderDate` đã format |
| Các dòng hàng | Order lines | Danh sách `OrderLineMailModel` |
| Tổng tiền | Giá trị tổng đã tính trong nghiệp vụ | `totalAmount` đã format |
| Địa chỉ giao hàng | Shipping address | `shippingAddressLines` |
| Link xem đơn | Base URL tin cậy + public order ID | `detailsUrl` đã xây dựng |
| Ngôn ngữ | Preference của người nhận | `Locale` hoặc mã locale |

Hãy chỉ đưa vào model các trường thật sự được dùng. Nếu template không cần ID database, token nội bộ, ghi chú vận hành hoặc thông tin thanh toán nhạy cảm thì không thêm các trường đó.

### 3.1. Dữ liệu hiển thị và dữ liệu tính toán

Template nên trình bày kết quả đã được tính ở tầng nghiệp vụ. Ví dụ, tổng tiền đơn hàng cần được tính theo quy tắc thuế, giảm giá, làm tròn và tiền tệ của domain/service; mapper chỉ định dạng kết quả.

Không nên để template tự tính:

~~~html
<!-- Không nên để template chịu trách nhiệm tính tổng nghiệp vụ -->
<span th:text="${order.unitPrice * order.quantity}"></span>
~~~

Thay vào đó, domain/application service tính giá trị chính xác, sau đó mapper tạo model:

~~~java
new OrderLineMailModel(
        line.productName(),
        line.quantityLabel(),
        line.lineTotalDisplay());
~~~

Việc này tránh lặp lại quy tắc tính tiền trong template và làm cho cùng một giá trị được dùng nhất quán giữa email, trang web và báo cáo.

## 4. Thiết kế mail model bằng Java record

Với Java hiện đại, `record` phù hợp cho DTO chỉ mang dữ liệu. Ví dụ:

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Locale;

public record OrderConfirmationMailModel(
        String recipientName,
        String orderNumber,
        String orderDate,
        List<OrderLineMailModel> items,
        String totalAmount,
        String shippingAddress,
        String detailsUrl,
        Locale locale) {

    public OrderConfirmationMailModel {
        items = List.copyOf(items);
    }
}
~~~

Một dòng hàng:

~~~java
package com.example.mail.model;

public record OrderLineMailModel(
        String productName,
        String quantity,
        String lineTotal) {
}
~~~

Những đặc điểm đáng chú ý:

- Trường là final theo ngữ nghĩa record, phù hợp với model bất biến.
- `List.copyOf(...)` tạo danh sách không thể thay đổi từ bên ngoài sau khi model được dựng.
- Tên trường có ý nghĩa trình bày, không phụ thuộc tên cột database.
- `detailsUrl` là link đã được chuẩn bị, không phải entity hoặc URL được template tự nối.
- `locale` cho biết ngôn ngữ của email và có thể dùng khi render message.

Nếu ứng dụng đang dùng Java version chưa hỗ trợ record, có thể tạo một class DTO với constructor và getter bất biến tương đương.

### 4.1. Khi nào nên giữ kiểu dữ liệu gốc?

Không phải mọi trường đều nên đổi thành chuỗi. Có thể giữ kiểu gốc nếu template hoặc bước render cần sử dụng hợp lý:

| Dữ liệu | Lựa chọn thường phù hợp |
| --- | --- |
| Mã đơn hàng | `String` |
| Tên hiển thị | `String` |
| Số lượng | `int` hoặc chuỗi đã format tùy template |
| Tổng tiền | `BigDecimal` cùng currency code, hoặc chuỗi đã format |
| Thời điểm | `Instant`/`ZonedDateTime` hoặc chuỗi đã format |
| Danh sách dòng hàng | `List<OrderLineMailModel>` |
| URL hoàn chỉnh | `URI` hoặc `String` đã được kiểm tra |
| Locale | `Locale` hoặc locale tag |

Nếu template chỉ hiển thị ngày và tiền tệ, chuỗi đã format giúp template đơn giản. Nếu template cần hiển thị giá trị ở nhiều định dạng hoặc dùng cùng model cho nhiều kênh, giữ `BigDecimal`, `Currency` và thời điểm gốc có thể hữu ích. Điều quan trọng là **không để template tự thực hiện quy tắc nghiệp vụ phức tạp**.

## 5. Mapper: chuyển dữ liệu nghiệp vụ sang mail model

Mapper là thành phần chuyển đổi có chủ đích. Nó nhận dữ liệu đã được lấy từ domain/application layer, chọn các trường cần thiết, định dạng chúng và trả về mail model.

Ví dụ dữ liệu đầu vào cho mapper:

~~~java
package com.example.order;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderMailData(
        String publicOrderId,
        String orderNumber,
        Instant createdAt,
        BigDecimal totalAmount,
        String currencyCode,
        List<OrderLineMailData> lines,
        String shippingAddress) {
}

public record OrderLineMailData(
        String productName,
        int quantity,
        BigDecimal lineTotal) {
}

public record RecipientMailPreferences(
        String displayName,
        String localeTag,
        String zoneId) {
}
~~~

Đây là projection/data snapshot đã được chuẩn bị cho tác vụ email, không phải entity JPA. Nếu lấy dữ liệu từ repository, application service có thể tạo các record này trong transaction và chuyển cho mapper sau khi đã nạp đủ dữ liệu cần thiết.

### 5.1. Mapper đầy đủ

~~~java
package com.example.mail.mapper;

import java.math.BigDecimal;
import java.net.URI;
import java.text.NumberFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.model.OrderLineMailModel;
import com.example.order.OrderMailData;
import com.example.order.OrderLineMailData;
import com.example.order.RecipientMailPreferences;

@Component
public class OrderConfirmationMailMapper {

    private final String publicBaseUrl;

    public OrderConfirmationMailMapper(
            @Value("${app.public-base-url}") String publicBaseUrl) {
        this.publicBaseUrl = publicBaseUrl;
    }

    public OrderConfirmationMailModel map(
            OrderMailData order,
            RecipientMailPreferences recipient) {

        Locale locale = Locale.forLanguageTag(recipient.localeTag());
        ZoneId zone = ZoneId.of(recipient.zoneId());

        String orderDate = formatDate(order.createdAt(), zone, locale);
        String totalAmount = formatMoney(
                order.totalAmount(), order.currencyCode(), locale);

        List<OrderLineMailModel> items = order.lines().stream()
                .map(line -> mapLine(line, order.currencyCode(), locale))
                .toList();

        String detailsUrl = buildDetailsUrl(order.publicOrderId());

        return new OrderConfirmationMailModel(
                recipient.displayName(),
                order.orderNumber(),
                orderDate,
                items,
                totalAmount,
                order.shippingAddress(),
                detailsUrl,
                locale);
    }

    private OrderLineMailModel mapLine(
            OrderLineMailData line,
            String currencyCode,
            Locale locale) {

        return new OrderLineMailModel(
                line.productName(),
                Integer.toString(line.quantity()),
                formatMoney(line.lineTotal(), currencyCode, locale));
    }

    private String formatDate(
            Instant instant,
            ZoneId zone,
            Locale locale) {

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale)
                        .withZone(zone);

        return formatter.format(instant);
    }

    private String formatMoney(
            BigDecimal amount,
            String currencyCode,
            Locale locale) {

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);
        formatter.setCurrency(Currency.getInstance(currencyCode));
        return formatter.format(amount);
    }

    private String buildDetailsUrl(String publicOrderId) {
        URI uri = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .pathSegment("orders", "{orderId}")
                .encode()
                .buildAndExpand(Map.of("orderId", publicOrderId))
                .toUri();

        return uri.toASCIIString();
    }
}
~~~

Đoạn code minh họa Java 17 trở lên vì sử dụng record và `Stream.toList()`. Các record/import cần được đặt trong những file Java riêng tương ứng. `app.public-base-url` phải là cấu hình đáng tin cậy của ứng dụng, ví dụ domain chính thức của trang khách hàng.

Mapper thực hiện các việc:

1. Chọn `Locale` và `ZoneId` theo người nhận.
2. Format thời gian theo ngôn ngữ và múi giờ.
3. Format tiền theo locale và currency code.
4. Chuyển từng dòng hàng sang DTO dành cho email.
5. Xây dựng URL từ base URL tin cậy và public ID đã được encode theo URI component.
6. Trả về một model bất biến.

### 5.2. Mapper không nên chứa quy tắc tính toán domain

Ví dụ trên nhận `totalAmount` và `lineTotal` đã được xác định từ tầng nghiệp vụ. Mapper chỉ định dạng chúng. Nếu tổng tiền cần áp dụng voucher, thuế hoặc quy tắc làm tròn, hãy để domain/application service tính trước.

Mapper cũng không nên quyết định đơn hàng nào được phép gửi, ai là người nhận hợp lệ hoặc giao dịch đã hoàn tất chưa. Những quyết định đó thuộc use case/application service.

## 6. Đưa mail model vào Thymeleaf context

Sau khi mapper trả về mail model, bước tiếp theo là cung cấp nó cho template engine. Với Thymeleaf, có thể dùng `org.thymeleaf.context.Context`:

~~~java
import org.thymeleaf.context.Context;

Context context = new Context(model.locale());
context.setVariable("mail", model);

String html = templateEngine.process(
        "mail/order-confirmation",
        context);
~~~

Template nhận một biến có tên `mail`. Các trường trong model được truy cập bằng property expression:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Đơn hàng đã được xác nhận</h1>
  <p>
    Xin chào
    <strong th:text="${mail.recipientName}">bạn</strong>,
  </p>
  <p>
    Mã đơn hàng:
    <strong th:text="${mail.orderNumber}">ORD-0001</strong>
  </p>
  <p>
    Ngày đặt:
    <span th:text="${mail.orderDate}">01 tháng 01 năm 2026</span>
  </p>
  <h2>Các sản phẩm</h2>
  <table>
    <thead>
      <tr><th>Sản phẩm</th><th>Số lượng</th><th>Thành tiền</th></tr>
    </thead>
    <tbody>
      <tr th:each="item : ${mail.items}">
        <td th:text="${item.productName}">Sản phẩm mẫu</td>
        <td th:text="${item.quantity}">1</td>
        <td th:text="${item.lineTotal}">100.000 ₫</td>
      </tr>
    </tbody>
  </table>
  <p>
    Tổng cộng:
    <strong th:text="${mail.totalAmount}">100.000 ₫</strong>
  </p>
  <p th:text="${mail.shippingAddress}">Địa chỉ giao hàng</p>
  <p><a th:href="${mail.detailsUrl}">Xem đơn hàng</a></p>
</body>
</html>
~~~

`th:text` escape dữ liệu text theo cơ chế mặc định của Thymeleaf. `th:href` đưa URL vào thuộc tính HTML; URL phải được xây dựng từ base URL tin cậy và kiểm tra theo chính sách ứng dụng trước khi đặt vào model. Không dùng `th:utext` cho tên người nhận, tên sản phẩm hoặc ghi chú không tin cậy.

### 6.1. Dùng nhiều biến hay một biến mail?

Có hai cách phổ biến:

**Một biến chứa mail model:**

~~~java
context.setVariable("mail", model);
~~~

Template truy cập `${mail.orderNumber}`, `${mail.totalAmount}`, `${mail.items}`.

**Đưa từng giá trị thành biến riêng:**

~~~java
context.setVariable("recipientName", model.recipientName());
context.setVariable("orderNumber", model.orderNumber());
context.setVariable("totalAmount", model.totalAmount());
context.setVariable("items", model.items());
~~~

Cách đầu giúp namespace gọn, thể hiện rõ template đang nhận một model xác định. Cách thứ hai hữu ích khi tích hợp một template legacy đã có hợp đồng biến riêng. Với template mới, một biến `mail` chứa DTO thường dễ bảo trì hơn.

### 6.2. Dùng Map khi API template cần các key động

`Map<String, Object>` vẫn hữu ích khi template được cấu hình linh hoạt hoặc có tập biến thay đổi. Có thể chuyển model sang map tường minh:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("recipientName", model.recipientName());
variables.put("orderNumber", model.orderNumber());
variables.put("orderDate", model.orderDate());
variables.put("totalAmount", model.totalAmount());
variables.put("items", model.items());

Context context = new Context(model.locale());
context.setVariables(variables);
~~~

Đổi lại, compiler không còn bảo đảm key có tồn tại hay đúng tên. Nếu dùng map, nên gom việc tạo map vào một mapper/renderer cụ thể, dùng hằng số cho các key quan trọng hoặc kiểm thử template để phát hiện sai tên biến.

### 6.3. Không chia sẻ Context giữa nhiều email

`Context` giữ các biến của một lần render. Không nên lưu một context mutable trong field singleton của service rồi cập nhật biến cho từng người nhận:

~~~java
// Không nên: context dùng chung giữa các request.
private final Context sharedContext = new Context();
~~~

Hai request đồng thời có thể ghi đè tên người nhận, mã đơn hàng hoặc URL của nhau. Hãy tạo context mới cho mỗi lần render:

~~~java
Context context = new Context(model.locale());
context.setVariable("mail", model);
String html = templateEngine.process(templateName, context);
~~~

`TemplateEngine` thường được cấu hình như bean dùng chung; đối tượng context và mail model nên được tạo riêng theo từng message.

## 7. Render HTML và plain text từ cùng một model

Một email có HTML nên có bản plain text tương ứng. Cả hai cần lấy dữ liệu từ **cùng một mail model** để tránh sai khác giữa các định dạng.

~~~text
              OrderConfirmationMailModel
                         |
              +----------+----------+
              |                     |
              v                     v
       Thymeleaf HTML         PlainTextRenderer
              |                     |
              v                     v
          htmlBody              plainBody
              |                     |
              +----------+----------+
                         |
                         v
          MimeMessageHelper.setText(plain, html)
~~~

Ví dụ renderer plain text:

~~~java
package com.example.mail.render;

import com.example.mail.model.OrderConfirmationMailModel;

public class OrderConfirmationPlainTextRenderer {

    public String render(OrderConfirmationMailModel mail) {
        StringBuilder text = new StringBuilder();
        text.append("Xin chào ")
                .append(mail.recipientName())
                .append(",\n\n");
        text.append("Đơn hàng ")
                .append(mail.orderNumber())
                .append(" đã được xác nhận.\n");
        text.append("Ngày đặt: ")
                .append(mail.orderDate())
                .append("\n\n");

        text.append("Các sản phẩm:\n");
        mail.items().forEach(item -> text.append("- ")
                .append(item.productName())
                .append(" | SL: ")
                .append(item.quantity())
                .append(" | ")
                .append(item.lineTotal())
                .append('\n'));

        text.append("\nTổng cộng: ")
                .append(mail.totalAmount())
                .append("\n");
        text.append("Địa chỉ giao hàng: ")
                .append(mail.shippingAddress())
                .append("\n\n");
        text.append("Xem đơn hàng: ")
                .append(mail.detailsUrl());

        return text.toString();
    }
}
~~~

Renderer plain text không cần HTML escaping. Dữ liệu được nối thành văn bản thuần; các dấu `<`, `&` hoặc dấu nháy trong tên vẫn là ký tự văn bản bình thường. URL vẫn cần được tạo và kiểm tra trước đó.

### 7.1. Gửi hai phiên bản qua MimeMessageHelper

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo(recipientEmail);
helper.setSubject("Xác nhận đơn hàng " + model.orderNumber());
helper.setText(plainBody, htmlBody);

mailSender.send(message);
~~~

`setText(plainBody, htmlBody)` tạo hai phiên bản nội dung trong `multipart/alternative` khi helper được bật multipart. Mail client có thể chọn plain text hoặc HTML tùy khả năng và cài đặt.

### 7.2. Template text có thể dùng MessageSource

Với email đa ngôn ngữ, không nhất thiết phải hard-code mọi nhãn trong template. Có thể dùng Spring `MessageSource` hoặc message expressions của Thymeleaf để lấy chuỗi theo locale:

~~~html
<h1 th:text="#{mail.order.confirmed}">
  Đơn hàng đã được xác nhận
</h1>
<span th:text="#{mail.order.number}">
  Mã đơn hàng
</span>
~~~

Context được tạo với locale của người nhận:

~~~java
Context context = new Context(model.locale());
context.setVariable("mail", model);
~~~

Các message key như `mail.order.confirmed` được dịch trong resource bundle theo locale. Dữ liệu cá nhân và dữ liệu giao dịch vẫn lấy từ mail model; message bundle chỉ cung cấp **nhãn và câu chữ tĩnh**.

## 8. Format ngày, giờ, số tiền và số lượng

Định dạng hiển thị phụ thuộc ngôn ngữ và vùng của người nhận. Cùng một thời điểm có thể cần hiển thị khác nhau:

| Locale | Ví dụ cách trình bày ngày |
| --- | --- |
| `vi-VN` | 12 tháng 11 năm 2026 |
| `en-US` | November 12, 2026 |
| `en-GB` | 12 November 2026 |

Không nên format ngày bằng cách nối chuỗi ngày/tháng/năm thủ công. Dùng `DateTimeFormatter` và locale:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale)
                .withZone(zoneId);

String displayDate = formatter.format(instant);
~~~

`Instant` biểu diễn một thời điểm toàn cục; `ZoneId` quyết định ngày/giờ địa phương của người nhận. Với một giá trị `LocalDate` vốn đã là ngày nghiệp vụ, không cần chuyển nó qua múi giờ.

### 8.1. Format tiền tệ

Dùng `BigDecimal` cho giá trị tiền, `Currency` cho mã tiền tệ và `NumberFormat` để hiển thị theo locale:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance(locale);
formatter.setCurrency(Currency.getInstance(currencyCode));
String displayAmount = formatter.format(amount);
~~~

Không chuyển `BigDecimal` sang `double` chỉ để format, vì có thể mất độ chính xác. Không mặc định mọi người nhận đều dùng cùng tiền tệ hoặc cùng cách đặt dấu phân cách hàng nghìn/thập phân.

### 8.2. Không chia sẻ NumberFormat mutable giữa các request

`NumberFormat` không phải đối tượng an toàn cho việc dùng đồng thời giữa nhiều thread. Hãy tạo formatter trong mỗi lần map/render, hoặc dùng cơ chế tạo instance theo request. Ngược lại, `DateTimeFormatter` là immutable và thread-safe nên có thể chia sẻ khi pattern/locale cố định.

### 8.3. Định dạng không thay đổi giá trị nghiệp vụ

Ví dụ số tiền gốc là `BigDecimal("1234567.50")`. Mapper có thể format thành chuỗi theo locale, nhưng không được làm tròn hoặc thay đổi số tiền nghiệp vụ chỉ để phù hợp template. Quy tắc làm tròn phải được xác định trước ở tầng nghiệp vụ; formatter chỉ quyết định cách trình bày.

## 9. Null, collection rỗng và dữ liệu không đầy đủ

Mail model cần có chính sách rõ cho dữ liệu thiếu. Nếu template nhận `null`, một số expression có thể hiển thị chuỗi "null", bỏ trống không như ý hoặc lỗi khi gọi property tiếp theo.

Ví dụ mapper nên quyết định:

- Tên người nhận thiếu: dùng cách xưng hô trung tính đã được sản phẩm chấp thuận.
- Địa chỉ phụ thiếu: không tạo một dòng địa chỉ rỗng.
- Danh sách mặt hàng rỗng: xác định đây là trường hợp hợp lệ hay dữ liệu nghiệp vụ bất thường.
- URL thiếu: không render một liên kết có `href` rỗng.
- Thời gian hoặc tiền tệ thiếu: từ chối tạo email nếu đó là dữ liệu bắt buộc.

Ví dụ:

~~~java
String recipientName = recipient.displayName();
if (recipientName == null || recipientName.isBlank()) {
    recipientName = "bạn";
}

List<OrderLineMailModel> items = order.lines() == null
        ? List.of()
        : order.lines().stream()
                .map(line -> mapLine(line, order.currencyCode(), locale))
                .toList();
~~~

Đây là chính sách fallback minh họa. Không nên mặc định mọi trường hợp null đều được thay bằng chuỗi rỗng; nếu thiếu dữ liệu bắt buộc để gửi thông báo chính xác, hãy dừng và ghi nhận lỗi nghiệp vụ.

### 9.1. Phân biệt collection null và collection rỗng

- `null` có thể có nghĩa dữ liệu chưa được tải hoặc nguồn dữ liệu không cung cấp.
- Danh sách rỗng có thể có nghĩa nghiệp vụ xác nhận không có phần tử.

Không nên âm thầm biến `null` thành danh sách rỗng nếu điều đó che giấu lỗi query hoặc lỗi mapping. Quyết định theo hợp đồng của dữ liệu đầu vào.

### 9.2. Giữ thứ tự collection ổn định

Nếu email liệt kê dòng đơn hàng, thứ tự nên được xác định từ nghiệp vụ hoặc query. Không dựa vào thứ tự tình cờ của `HashSet` hoặc quan hệ collection không có order. Một mail model ổn định giúp nội dung email có thể kiểm tra, so sánh và tái tạo nhất quán.

## 10. Lấy dữ liệu từ repository mà không đưa entity vào template

Trong ứng dụng dùng JPA, entity thường có quan hệ lazy. Nếu template truy cập `order.customer.name` hoặc lặp qua `order.lines` sau khi transaction đã đóng, ứng dụng có thể gặp `LazyInitializationException`. Ngay cả khi transaction còn mở, template có thể kích hoạt nhiều query ngoài ý muốn.

Hãy tải đúng dữ liệu cần cho email ở tầng application/repository rồi tạo một snapshot:

~~~java
public record OrderMailData(
        String publicOrderId,
        String orderNumber,
        Instant createdAt,
        BigDecimal totalAmount,
        String currencyCode,
        List<OrderLineMailData> lines,
        String shippingAddress) {
}
~~~

Repository có thể dùng projection hoặc query riêng để lấy các cột cần thiết. Application service chuyển kết quả thành DTO, rồi mapper email nhận DTO đó:

~~~text
OrderRepository / query projection
             |
             v
       OrderMailData
             |
             v
   OrderConfirmationMailMapper
             |
             v
 OrderConfirmationMailModel
~~~

### 10.1. Ví dụ application service

~~~java
package com.example.order;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMailDataService {

    private final OrderRepository orderRepository;

    public OrderMailDataService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderMailData loadForConfirmation(String orderId) {
        return orderRepository.findMailDataByPublicId(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order was not found"));
    }
}
~~~

`findMailDataByPublicId` là phương thức minh họa; repository cần triển khai projection/query tương ứng. Mục tiêu là trả về dữ liệu đã được materialize, không trả entity có quan hệ lazy để template tự truy cập.

### 10.2. Snapshot nhất quán khi gửi bất đồng bộ

Nếu email được đưa vào queue để gửi sau, không nên chỉ lưu ID rồi để worker tải entity tùy ý ở một thời điểm khác mà không xem xét trạng thái dữ liệu. Đơn hàng có thể thay đổi giữa lúc phát sinh sự kiện và lúc worker gửi mail.

Tùy nghiệp vụ, có thể:

- Lưu một **snapshot các trường cần gửi** cùng sự kiện/outbox record.
- Hoặc lưu ID và quy định rõ email phải phản ánh trạng thái mới nhất tại thời điểm gửi.
- Dùng version hoặc event payload để tránh trộn dữ liệu của hai trạng thái.
- Chỉ gửi sau khi giao dịch nghiệp vụ đã commit thành công.

Ví dụ email xác nhận thanh toán thường phải phản ánh số tiền và trạng thái đã commit. Nếu mapper lấy một phần dữ liệu trước commit và một phần sau commit, nội dung có thể không nhất quán.

## 11. Tách mail envelope khỏi nội dung template

Một email có cả thông tin định tuyến và nội dung:

| Nhóm | Ví dụ | Nơi sử dụng |
| --- | --- | --- |
| **Envelope/header** | From, To, Cc, Reply-To, Subject | `MimeMessageHelper` và API Jakarta Mail |
| **Mail model** | Tên, mã đơn, dòng hàng, ngày, tổng tiền, link | Template HTML/plain text |
| **MIME resources** | PDF, logo CID, file đính kèm | `addAttachment` / `addInline` |

Không nhất thiết phải đưa tất cả vào cùng một object template. Ví dụ địa chỉ người nhận dùng để gửi nên được truyền vào mailer:

~~~java
mailer.send(
        recipientEmail,
        subject,
        plainBody,
        htmlBody);
~~~

Template chỉ nhận các trường nó cần. Việc tách này giảm nguy cơ vô tình render địa chỉ email, thông tin định tuyến hoặc dữ liệu nhạy cảm vào nội dung thư.

### 11.1. Model cho attachment

Nếu một loại email có file đính kèm, có thể mô tả file bằng một cấu trúc riêng:

~~~java
public record MailAttachment(
        String filename,
        InputStreamSource content,
        String contentType) {
}
~~~

Mailer nhận danh sách attachment đã được kiểm tra:

~~~java
helper.setText(plainBody, htmlBody);

for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            attachment.content(),
            attachment.contentType());
}
~~~

Không đưa entity tài liệu hoặc đường dẫn file tùy ý vào template. Filename, quyền truy cập, content type và nguồn bytes phải được xác định ở tầng ứng dụng. Nguồn InputStreamSource cần có khả năng mở stream phù hợp với quá trình serialize MIME.

## 12. URL và dữ liệu nhạy cảm trong mail model

Mail model có thể chứa URL để người nhận xem đơn hàng, tải tài liệu hoặc xác minh tài khoản. URL nên được tạo từ **base URL tin cậy** trong cấu hình ứng dụng và các component được encode đúng cách.

Không nên:

~~~java
String url = request.getParameter("returnUrl");
String html = "<a href=\"" + url + "\">Mở đơn hàng</a>";
~~~

Đầu vào có thể trỏ tới domain ngoài hoặc scheme không được phép. Hãy tạo URL từ domain ứng dụng:

~~~java
String detailsUrl = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .pathSegment("orders", "{id}")
        .encode()
        .buildAndExpand(publicOrderId)
        .toUriString();
~~~

Nếu URL chứa token xác minh hoặc token reset password:

- Token phải có thời hạn và phạm vi sử dụng rõ ràng.
- Chỉ đưa token vào link của email cần nó.
- Không ghi URL đầy đủ/token vào log, metric hoặc exception message.
- Không đưa token vào các trường model không được template sử dụng.
- Dùng HTTPS và domain chính thức.
- Tránh tái sử dụng token sau khi đã xác minh hoặc hết hạn.

Mail model có thể cần chứa URL có token để render link; điều đó không có nghĩa toàn bộ model nên được serialize/log. Hãy xử lý model như dữ liệu có thể chứa thông tin nhạy cảm.

### 12.1. Không pre-escape dữ liệu trong mapper

Mapper nên trả về dữ liệu text ở dạng gốc:

~~~java
return new OrderLineMailModel(
        line.productName(),
        Integer.toString(line.quantity()),
        formattedTotal);
~~~

Để Thymeleaf `th:text` escape tên sản phẩm tại HTML text context. Không gọi `Encode.forHtml` trong mapper rồi lại truyền chuỗi đã escape vào `th:text`; điều đó có thể tạo double escaping.

Tương tự, URL cần được build và validate ở tầng URI, rồi template engine ghi nó vào thuộc tính. Đừng HTML-escape URL trong mapper trước khi đưa vào `th:href`.

## 13. Quy trình gửi email hoàn chỉnh

Một use case xác nhận đơn hàng có thể được tổ chức thành các thành phần:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import com.example.mail.mapper.OrderConfirmationMailMapper;
import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.render.OrderConfirmationPlainTextRenderer;
import com.example.order.OrderMailData;
import com.example.order.OrderMailDataService;
import com.example.order.RecipientMailPreferences;

@Service
public class OrderConfirmationMailer {

    private final OrderMailDataService dataService;
    private final OrderConfirmationMailMapper mapper;
    private final TemplateEngine templateEngine;
    private final OrderConfirmationPlainTextRenderer plainRenderer;
    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(
            OrderMailDataService dataService,
            OrderConfirmationMailMapper mapper,
            TemplateEngine templateEngine,
            OrderConfirmationPlainTextRenderer plainRenderer,
            JavaMailSender mailSender) {
        this.dataService = dataService;
        this.mapper = mapper;
        this.templateEngine = templateEngine;
        this.plainRenderer = plainRenderer;
        this.mailSender = mailSender;
    }

    public void send(
            String publicOrderId,
            String recipientEmail,
            RecipientMailPreferences preferences)
            throws MessagingException {

        OrderMailData source =
                dataService.loadForConfirmation(publicOrderId);

        OrderConfirmationMailModel model =
                mapper.map(source, preferences);

        Context context = new Context(model.locale());
        context.setVariable("mail", model);
        String htmlBody = templateEngine.process(
                "mail/order-confirmation", context);

        String plainBody = plainRenderer.render(model);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipientEmail);
        helper.setSubject("Xác nhận đơn hàng " + model.orderNumber());
        helper.setText(plainBody, htmlBody);

        mailSender.send(message);
    }
}
~~~

Đây là ví dụ ghép các thành phần ở mức application service. Các bean OrderMailDataService, mapper, renderer, TemplateEngine và JavaMailSender phải được cấu hình trong ứng dụng. recipientEmail cần được lấy từ nguồn người nhận đã được xác thực/ủy quyền. Địa chỉ From cần thuộc miền và tài khoản SMTP được phép sử dụng.

Luồng xử lý:

1. Tải snapshot dữ liệu cần cho email.
2. Chuyển snapshot thành mail model.
3. Render HTML từ template và render plain text từ cùng model.
4. Tạo MIME message.
5. Đặt envelope/header và hai phiên bản nội dung.
6. Gửi bằng JavaMailSender.

Trong hệ thống lớn, bước tải snapshot và bước gửi có thể nằm ở hai service hoặc hai tiến trình khác nhau. Điều quan trọng là hợp đồng dữ liệu giữa chúng phải rõ ràng và đủ để dựng đúng email.

## 14. Kiểm thử mapping và template mà không cần SMTP

Mapper là Java code thuần nên có thể kiểm thử độc lập:

~~~java
@Test
void mapsOrderToConfirmationMailModel() {
    OrderMailData order = new OrderMailData(
            "public-123",
            "ORD-2026-001",
            Instant.parse("2026-11-12T08:00:00Z"),
            new BigDecimal("125000.00"),
            "VND",
            List.of(new OrderLineMailData(
                    "Bàn phím", 1, new BigDecimal("125000.00"))),
            "12 Nguyễn Huệ, TP. Hồ Chí Minh");

    RecipientMailPreferences recipient =
            new RecipientMailPreferences(
                    "Lan",
                    "vi-VN",
                    "Asia/Ho_Chi_Minh");

    OrderConfirmationMailModel model =
            mapper.map(order, recipient);

    assertThat(model.recipientName()).isEqualTo("Lan");
    assertThat(model.orderNumber()).isEqualTo("ORD-2026-001");
    assertThat(model.items()).hasSize(1);
    assertThat(model.detailsUrl())
            .contains("/orders/public-123");
}
~~~

Đây là ví dụ với JUnit và AssertJ; mapper cần được khởi tạo với base URL kiểm thử. Không cần khởi tạo JavaMailSender hoặc mở kết nối SMTP để kiểm tra việc chuyển dữ liệu.

### 14.1. Các trường hợp nên có trong test mapper

- Locale vi-VN, en-US và locale mặc định của sản phẩm.
- Múi giờ khác nhau, nhất là thời điểm gần nửa đêm UTC.
- Tiền tệ có số chữ số thập phân khác nhau.
- Danh sách không có dòng hàng, một dòng và nhiều dòng.
- Tên sản phẩm chứa dấu tiếng Việt và ký tự đặc biệt.
- Giá trị thiếu theo từng chính sách fallback.
- Public ID có ký tự cần encode trong URL path.
- Currency code hoặc ZoneId không hợp lệ phải tạo lỗi rõ ràng.

### 14.2. Kiểm thử template

Có thể render template với một model cố định:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", sampleModel);

String html = templateEngine.process(
        "mail/order-confirmation", context);

assertThat(html).contains("ORD-2026-001");
assertThat(html).contains("Xem đơn hàng");
~~~

Test này xác nhận template nhận đúng biến và render những nội dung quan trọng. Có thể thêm dữ liệu chứa `<`, `&`, dấu nháy để kiểm tra th:text escape đúng; kiểm tra URL attribute riêng để xác nhận destination được tạo theo policy.

### 14.3. Kiểm thử MIME message

Nếu cần xác nhận plain text và HTML cùng tồn tại, có thể dùng fake/mock JavaMailSender trả về MimeMessage thật được tạo từ Jakarta Mail Session, sau đó kiểm tra message sau khi service gọi send. Hoặc gửi tới SMTP sink trong integration test.

Không cần kết nối SMTP thật cho unit test mapper hoặc template. Việc tách các bước giúp xác định lỗi thuộc mapping, template hay transport.

## 15. Validation và hợp đồng của mail model

Mail model là hợp đồng giữa mapper và template. Nếu một trường bắt buộc bị thiếu, lỗi nên được phát hiện sớm trước khi tạo MIME message.

Có thể kiểm tra ở hai lớp:

- **Validation dữ liệu đầu vào**: order number, currency code, timestamp, recipient preference và URL phải hợp lệ theo nghiệp vụ.
- **Validation mail model**: các trường template bắt buộc phải có giá trị và collection phải có trạng thái được xác định.

Ví dụ với Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Locale;

public record PasswordResetMailModel(
        @NotBlank String recipientName,
        @NotBlank String resetUrl,
        @NotNull Locale locale,
        @NotNull List<String> supportContacts) {
}
~~~

Chú thích validation chỉ có tác dụng khi ứng dụng thực sự gọi validator hoặc tích hợp validation vào bước tạo model. Khai báo annotation không tự động bảo đảm mọi record được kiểm tra. Với dữ liệu không thể gửi an toàn khi thiếu, mapper nên từ chối tạo model và trả lỗi có ngữ cảnh.

### 15.1. Phân biệt dữ liệu bắt buộc và tùy chọn

| Trường | Ví dụ chính sách |
| --- | --- |
| Người nhận | Bắt buộc phải có địa chỉ hợp lệ ở envelope |
| Mã giao dịch | Bắt buộc nếu email xác nhận một giao dịch cụ thể |
| Tổng tiền/currency | Bắt buộc với email hóa đơn |
| Tên hiển thị | Có thể dùng lời chào trung tính nếu nghiệp vụ cho phép |
| Địa chỉ phụ | Có thể bỏ dòng nếu không có |
| Link xem chi tiết | Bắt buộc nếu email hướng người dùng tới trang chi tiết |
| Danh sách sản phẩm | Có thể rỗng nếu loại email cho phép, nếu không thì báo lỗi dữ liệu |

Không nên dùng cùng một fallback cho mọi trường. Chuỗi rỗng ở một trường trang trí có thể chấp nhận được; chuỗi rỗng ở số tiền hoặc link xác minh có thể khiến email sai nội dung.

### 15.2. Đừng biến lỗi mapping thành email thành công giả

Nếu mapper không thể tạo URL, không biết currency code hoặc thiếu order number, không nên gửi một email với placeholder như `null`, `0` hoặc link rỗng chỉ để luồng không ném exception. Hãy dừng ở bước tạo model và để use case ghi nhận lỗi phù hợp.

Ngược lại, một trường tùy chọn như tên hiển thị có thể có fallback đã được sản phẩm phê duyệt. Chính sách phải được viết rõ để người bảo trì hiểu vì sao một trường được thay thế và trường khác khiến tác vụ thất bại.

## 16. Mapping thủ công hay dùng MapStruct?

Với một mail model nhỏ, mapping thủ công thường dễ đọc:

~~~java
return new OrderConfirmationMailModel(
        recipient.displayName(),
        order.orderNumber(),
        formatDate(order.createdAt(), zone, locale),
        mapLines(order.lines(), locale),
        formatMoney(order.totalAmount(), order.currencyCode(), locale),
        order.shippingAddress(),
        buildDetailsUrl(order.publicOrderId()),
        locale);
~~~

Khi ứng dụng có nhiều loại email và nhiều trường tương tự, **MapStruct** có thể giảm code chuyển đổi cơ bản bằng cách sinh mapper lúc compile:

~~~java
@Mapper(componentModel = "spring")
public interface RecipientMailMapper {

    RecipientHeaderMailModel toModel(RecipientProfile source);
}
~~~

Đây chỉ là ví dụ mapper đơn giản. Những thao tác cần logic như format tiền/ngày, chọn locale, build URL, lọc thông tin nhạy cảm hoặc chuyển trạng thái nghiệp vụ vẫn nên được viết rõ trong custom mapping method hoặc lớp assembler chuyên biệt.

Không nên để công cụ tự động copy tất cả field từ entity sang email model. Mục tiêu là **chỉ đưa dữ liệu được phép và cần thiết** vào template.

## 17. Mapping nhiều email và tránh truy vấn N+1

Khi gửi thông báo cho nhiều người, việc gọi mapper không nên kéo theo một query mới cho từng dòng hàng hoặc từng người nhận nếu dữ liệu có thể được lấy theo batch.

Ví dụ luồng không hiệu quả:

~~~text
Danh sách 100 đơn hàng
   |
   +--> load customer cho order 1
   +--> load lines cho order 1
   +--> load customer cho order 2
   +--> load lines cho order 2
   ...
~~~

Nếu các quan hệ được lazy-load, số query có thể tăng nhanh. Cách tổ chức tốt hơn là dùng projection/query batch để lấy dữ liệu cần thiết cho một nhóm email, sau đó map từ snapshot đã tải:

~~~text
Batch query / projection
          |
          v
List<OrderMailData>
          |
          v
Map từng item thành mail model
          |
          v
Render và gửi theo từng người nhận
~~~

Các lưu ý:

- Chọn đúng các cột cần cho email.
- Sắp xếp collection theo thứ tự nghiệp vụ.
- Tránh truy cập repository từ template hoặc từ getter của mail model.
- Nếu gửi theo batch, giới hạn số message đồng thời và xử lý lỗi từng message theo chính sách.
- Không dùng chung một mutable Context hoặc MimeMessage giữa nhiều người nhận.

### 17.1. Model riêng cho từng người nhận

Nếu cùng một giao dịch gửi cho nhiều người, nội dung có thể thay đổi theo ngôn ngữ hoặc quyền của từng người nhận. Hãy tạo model riêng theo recipient:

~~~java
for (RecipientMailPreferences recipient : recipients) {
    OrderConfirmationMailModel model =
            mapper.map(orderSnapshot, recipient);
    mailRenderer.renderAndSend(recipient.email(), model);
}
~~~

Đây là pseudocode minh họa; recipient email có thể được lưu trong một DTO envelope riêng. Không thay đổi một model mutable dùng chung rồi gửi nhiều message tuần tự nếu có khả năng các trường còn sót từ người nhận trước.

## 18. Những lỗi mapping thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Template hiển thị `null` | Trường bị thiếu hoặc key sai | Xác định trường bắt buộc, kiểm tra model trước render |
| Template không tìm thấy biến | Tên biến trong context không khớp template | Dùng một hợp đồng key rõ ràng và test render |
| `LazyInitializationException` | Template truy cập entity/quan hệ lazy sau transaction | Dùng projection/snapshot và mail DTO |
| Email hiển thị tiền sai | Locale/currency không đúng hoặc mapper tự tính tiền | Dùng currency code từ nghiệp vụ và formatter theo locale |
| Ngày lệch một ngày | Dùng timezone không đúng hoặc nhầm Instant với LocalDate | Chọn ZoneId người nhận hoặc giữ LocalDate nghiệp vụ |
| Link trỏ domain sai | Dùng URL từ request thay base URL tin cậy | Xây URL từ cấu hình và encode component |
| Tên người dùng hiện `&amp;lt;` | Escape trong mapper rồi template escape lần nữa | Truyền dữ liệu gốc và escape tại sink |
| Plain text khác HTML | Hai renderer lấy dữ liệu từ nguồn khác nhau | Render cả hai từ cùng mail model |
| Danh sách dòng hàng không đúng thứ tự | Collection nguồn không có order | Sắp xếp trong query/domain trước khi map |
| Email chứa thông tin nội bộ | Mail model sao chép toàn entity | Chọn allowlist trường cần thiết |
| Nội dung của hai người nhận bị trộn | Dùng chung mutable Context/model/message | Tạo đối tượng riêng cho từng lần gửi |
| Email gửi dữ liệu cũ | Worker tải entity ở thời điểm khác với sự kiện | Dùng snapshot/version theo yêu cầu nghiệp vụ |

## 19. Câu hỏi thường gặp

**“Mail model có phải là DTO không?”**  
Thường là có. Nó là DTO dành cho một loại email, chứa các trường template cần và có thể bổ sung những giá trị đã format để trình bày.

**“Có nên truyền JPA entity trực tiếp vào Thymeleaf không?”**  
Không nên. Template có thể phụ thuộc vào entity, truy cập lazy relation, kéo thêm query hoặc làm lộ trường nội bộ. Hãy map sang DTO nhỏ trước khi render.

**“Có nên dùng một Map cho tất cả email?”**  
Map hữu ích khi key thực sự động, nhưng với loại email cố định, model có kiểu riêng giúp rõ hợp đồng và giảm lỗi key. Nếu dùng Map, hãy tập trung việc tạo key ở một nơi và kiểm thử template.

**“Mapper có nên format tiền và ngày không?”**  
Có thể, nếu đó là định dạng trình bày theo locale/timezone. Quy tắc tính tổng, thuế, giảm giá và làm tròn phải thuộc tầng nghiệp vụ; mapper chỉ định dạng kết quả.

**“Có nên escape HTML trong mapper?”**  
Thông thường không. Giữ dữ liệu text ở dạng gốc và để Thymeleaf th:text hoặc encoder đúng context xử lý tại bước xuất. Tránh double escaping.

**“Mail model có nên chứa recipient email không?”**  
Không bắt buộc. Thường tách địa chỉ nhận trong envelope của mailer khỏi các biến template. Điều này giảm nguy cơ địa chỉ hoặc metadata định tuyến xuất hiện trong body ngoài ý muốn.

**“Có nên đưa file PDF hoặc Resource vào mail model?”**  
Nếu template chỉ trình bày nội dung, không cần. Attachment có thể được truyền trong một cấu trúc riêng cho mailer. Tên file, content type, quyền truy cập và nguồn bytes cần được kiểm tra trước khi gửi.

**“Có thể dùng chung mail model cho HTML và plain text không?”**  
Nên. Cùng một model giúp hai phiên bản phản ánh cùng mã giao dịch, số tiền, ngày và URL. Renderer HTML và plain text chỉ khác cách trình bày.

**“Template có nên tự format ngày và tiền?”**  
Template có thể dùng utility đơn giản nếu kiến trúc đã quy định, nhưng format tập trung trong mapper/service thường dễ kiểm thử và nhất quán hơn. Không để template thực hiện quy tắc nghiệp vụ.

**“Nếu gửi email bất đồng bộ thì mail model được tạo lúc nào?”**  
Tùy yêu cầu email phải phản ánh trạng thái tại thời điểm phát sinh sự kiện hay trạng thái mới nhất khi gửi. Nếu cần lịch sử chính xác, lưu snapshot hoặc event payload đủ dữ liệu; nếu cần trạng thái mới nhất, worker tải lại theo ID và chính sách được xác định rõ.

## 20. Ghi nhớ khi map dữ liệu nghiệp vụ sang mail model

Một luồng gửi email dễ bảo trì có thể tổ chức:

~~~text
Use case / application service
        |
        v
Load dữ liệu cần thiết (projection/snapshot)
        |
        v
Mail mapper
  - chọn trường được phép
  - format ngày/tiền theo locale
  - tạo URL từ base URL tin cậy
  - xử lý null/collection theo policy
        |
        v
Typed mail model
        |
        +--> Thymeleaf HTML renderer
        |
        +--> Plain-text renderer
        |
        v
Mail envelope + MIME resources
        |
        v
MimeMessageHelper
        |
        v
JavaMailSender
~~~

Mail model tạo một ranh giới rõ giữa dữ liệu nghiệp vụ và nội dung email. Repository/application service cung cấp snapshot cần thiết; mapper chọn và định dạng dữ liệu; template chỉ trình bày; mailer đóng gói MIME và gửi. Khi giữ đúng ranh giới này, email dễ kiểm thử, dễ dịch, ít phụ thuộc persistence và giảm nguy cơ lộ thông tin nội bộ hoặc gửi nội dung không nhất quán.
