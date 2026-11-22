# Mô hình dữ liệu cho một email template

Trong **Spring Framework Mail**, một email template thường nhận dữ liệu từ ứng dụng rồi tạo ra nội dung HTML hoặc plain text để gửi cho người nhận. Chẳng hạn, template xác nhận đơn hàng cần tên khách hàng, mã đơn, danh sách sản phẩm, tổng tiền, thời gian đặt và đường dẫn xem chi tiết. Nếu đưa thẳng entity database vào template hoặc để template tự truy vấn dữ liệu, phần trình bày sẽ bị phụ thuộc vào cấu trúc lưu trữ và dễ làm lộ những thông tin không cần thiết.

Một **mô hình dữ liệu cho email template** (template data model hoặc mail view model) là tập hợp những giá trị đã được chọn lọc, đặt tên rõ nghĩa và chuẩn bị sẵn để template hiển thị. Mô hình này đóng vai trò hợp đồng giữa **tầng nghiệp vụ** và **tầng trình bày email**:

~~~text
Database / Domain model
          |
          v
Application service + mapper
          |
          v
Email template data model
          |
          +--------------------+
          |                    |
          v                    v
HTML template             Plain-text template
          |                    |
          +---------+----------+
                    |
                    v
             Rendered content
                    |
                    v
       MimeMessage / MimeMessageHelper
                    |
                    v
             JavaMailSender
~~~

Mô hình dữ liệu tốt giúp email dễ bảo trì, kiểm thử, cá nhân hóa và gửi bất đồng bộ. Nó cũng tạo một ranh giới an toàn: template chỉ nhận dữ liệu cần hiển thị, không có quyền tùy ý truy cập entity, secret SMTP hoặc các trường nội bộ của hệ thống.

## 1. Vì sao cần một model riêng cho email?

Giả sử ứng dụng có entity đơn hàng:

~~~java
class OrderEntity {
    Long id;
    UserEntity customer;
    List<OrderLineEntity> lines;
    BigDecimal total;
    String paymentProviderReference;
    String internalNote;
    String fraudReviewStatus;
    // nhiều quan hệ và trường nội bộ khác
}
~~~

Nếu truyền nguyên entity vào template:

~~~java
context.setVariable("order", orderEntity);
~~~

template có thể truy cập quá nhiều thuộc tính, phụ thuộc vào cấu trúc ORM và vô tình hiển thị dữ liệu không dành cho khách hàng. Một quan hệ lazy có thể còn gây truy vấn ngoài ý muốn trong lúc render; thay đổi schema hoặc mapping cũng có thể làm template hỏng.

Thay vào đó, tầng ứng dụng tạo một model riêng:

~~~java
public record OrderConfirmationMailModel(
        String customerName,
        String orderNumber,
        String totalText,
        List<OrderLineMailModel> lines,
        String orderUrl) {
}
~~~

Model chỉ có những gì email cần hiển thị. Template không cần biết đơn hàng được lưu trong bảng nào, khách hàng có bao nhiêu quan hệ ORM hoặc hệ thống thanh toán dùng nhà cung cấp nào.

### 1.1. Lợi ích chính

| Lợi ích | Ý nghĩa thực tế |
| --- | --- |
| **Tách biệt nghiệp vụ và trình bày** | Có thể đổi HTML/CSS mà không sửa logic đơn hàng |
| **Giới hạn dữ liệu** | Chỉ trường đã chọn mới có thể xuất hiện trong email |
| **Ổn định hợp đồng** | Template dùng tên biến rõ ràng, không phụ thuộc entity/database |
| **Dễ kiểm thử** | Tạo model mẫu trực tiếp, không cần dựng toàn bộ database |
| **Dễ đa ngôn ngữ** | Có thể định dạng dữ liệu theo locale trước khi render |
| **Dễ gửi bất đồng bộ** | Model có thể được chụp thành payload bất biến cho queue |
| **Dễ tái sử dụng** | HTML và plain text có thể dùng chung một bộ dữ liệu |

## 2. Phân biệt email envelope, template model và template context

Trong code gửi email, ba khái niệm này thường bị gộp làm một, nhưng chúng có mục đích khác nhau.

| Thành phần | Chứa gì? | Ví dụ |
| --- | --- | --- |
| **Mail envelope/message metadata** | Người gửi, người nhận, Cc/Bcc, Reply-To, Subject | `from`, `to`, `subject` |
| **Template data model** | Dữ liệu nghiệp vụ dùng để trình bày | `customerName`, `orderNumber`, `totalText` |
| **Template context** | Cách truyền các biến vào một lần render của template engine | Thymeleaf `Context` với `setVariable(...)` |

Ví dụ:

~~~java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng A123");

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", "Nguyễn An");
context.setVariable("orderNumber", "A123");
context.setVariable("totalText", "220.000 ₫");
~~~

`customerName` và `orderNumber` là dữ liệu trình bày. `To` và `Subject` là metadata của email. Không phải biến nào được đặt trong context cũng nên xuất hiện trong template; hãy truyền đúng model cần thiết.

Một thiết kế rõ ràng thường có một đối tượng envelope riêng và một model nội dung riêng. Điều đó cho phép thay người nhận hoặc subject theo chính sách gửi mà không làm model trình bày phải chứa các chi tiết SMTP.

## 3. Nguyên tắc thiết kế một email data model

### 3.1. Chỉ chứa dữ liệu cần hiển thị

Hãy bắt đầu từ template và hỏi: **người nhận cần nhìn thấy thông tin nào?** Mỗi biến trong template nên có lý do nghiệp vụ.

Ví dụ email xác nhận đơn hàng có thể cần:

- tên người nhận;
- mã đơn hàng;
- ngày giờ đặt hàng đã định dạng;
- danh sách sản phẩm;
- số lượng và thành tiền từng dòng;
- tổng tiền và loại tiền;
- địa chỉ giao hàng ở mức được phép hiển thị;
- đường dẫn xem đơn hàng;
- địa chỉ hoặc hướng dẫn liên hệ hỗ trợ.

Không cần đưa vào model các trường như mật khẩu, token nội bộ, trạng thái đánh giá gian lận, ghi chú nhân viên, ID kết nối database hoặc toàn bộ đối tượng khách hàng.

### 3.2. Đặt tên theo ý nghĩa, không theo vị trí trong database

Tên biến nên thể hiện **ý nghĩa đối với người đọc template**:

| Tên khó hiểu | Tên rõ nghĩa hơn |
| --- | --- |
| `u` | `customerName` |
| `ordNo` | `orderNumber` |
| `amt` | `totalAmountText` |
| `dt` | `orderedAtText` |
| `lst` | `orderLines` |
| `flag1` | `showSupportInformation` |

Không nên đặt tên template theo cột database như `c_name`, `col_17` hoặc tên viết tắt chỉ người viết mapper mới hiểu. Template là hợp đồng được đọc bởi cả lập trình viên backend lẫn người phụ trách nội dung.

### 3.3. Phân biệt trường bắt buộc và tùy chọn

Ví dụ:

| Trường | Bắt buộc? | Cách xử lý nếu thiếu |
| --- | --- | --- |
| `orderNumber` | Có | Không tạo email xác nhận nếu thiếu mã đơn |
| `customerName` | Có hoặc có giá trị thay thế theo nghiệp vụ | Dùng lời chào chung nếu cho phép |
| `orderLines` | Có | Dùng danh sách rỗng hoặc từ chối tạo model tùy loại thư |
| `deliveryAddress` | Tùy email | Ẩn phần địa chỉ nếu không áp dụng |
| `supportUrl` | Tùy loại thư | Bỏ CTA hoặc dùng kênh hỗ trợ mặc định |
| `promotionText` | Không | Không render đoạn khuyến mãi khi không có |

Không nên để template tự đoán cách xử lý mọi trường `null`. Quy tắc mặc định cần được quyết định ở tầng ứng dụng hoặc được mô tả rõ trong template.

### 3.4. Dùng kiểu dữ liệu phù hợp

Không biến mọi thứ thành `String` quá sớm. Có thể giữ kiểu có ý nghĩa ở tầng model rồi format tại mapper:

- `UUID` cho ID công việc hoặc ID định danh;
- `BigDecimal` cho tiền;
- `Currency` hoặc mã tiền tệ cho đơn vị tiền;
- `Instant`, `LocalDate`, `OffsetDateTime` cho thời điểm/ngày;
- `URI` cho liên kết đã được tạo và kiểm soát;
- `List<...>` cho các dòng lặp;
- `boolean` cho điều kiện hiển thị.

Nếu template chỉ cần hiển thị chuỗi, việc format trong mapper thành `totalText` hoặc `orderedAtText` có thể giúp template đơn giản hơn. Chọn một cách nhất quán theo độ phức tạp của mẫu; đừng để mỗi template tự tính toán tiền hoặc timezone theo một quy tắc khác nhau.

## 4. Ví dụ model cho email xác nhận đơn hàng

Giả sử email cần tên khách, mã đơn, ngày đặt, danh sách sản phẩm, tổng tiền và liên kết xem đơn.

### 4.1. Model lồng nhau bằng Java record

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Objects;

public record OrderLineMailModel(
        String productName,
        String sku,
        int quantity,
        String unitPriceText,
        String lineTotalText) {

    public OrderLineMailModel {
        Objects.requireNonNull(productName, "productName");
        Objects.requireNonNull(unitPriceText, "unitPriceText");
        Objects.requireNonNull(lineTotalText, "lineTotalText");

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
~~~

Model cấp email:

~~~java
package com.example.mail.model;

import java.util.List;
import java.util.Objects;

public record OrderConfirmationMailModel(
        String customerName,
        String orderNumber,
        String orderedAtText,
        List<OrderLineMailModel> orderLines,
        String subtotalText,
        String shippingFeeText,
        String totalText,
        String orderUrl,
        boolean showSupportInformation) {

    public OrderConfirmationMailModel {
        Objects.requireNonNull(customerName, "customerName");
        Objects.requireNonNull(orderNumber, "orderNumber");
        Objects.requireNonNull(orderedAtText, "orderedAtText");
        Objects.requireNonNull(totalText, "totalText");
        Objects.requireNonNull(orderUrl, "orderUrl");

        orderLines = List.copyOf(
                Objects.requireNonNull(orderLines, "orderLines"));
    }
}
~~~

Những điểm đáng chú ý:

- **Record** cung cấp constructor, accessor và các phương thức cơ bản, giúp model dữ liệu rõ ràng.
- Các trường `String` và `boolean` phù hợp cho thông tin trình bày đã được chuẩn bị.
- `List.copyOf(...)` tạo bản sao bất biến của danh sách, tránh việc một danh sách nguồn bị thay đổi sau khi model được tạo.
- Mỗi dòng sản phẩm có model riêng; template không phải biết cấu trúc của entity sản phẩm.
- Các trường bắt buộc được kiểm tra ngay khi tạo model. Quy tắc nghiệp vụ phức tạp hơn có thể nằm ở factory/mapper hoặc validator.

Trong dự án Java, mỗi `public record` nên nằm trong file riêng tương ứng với tên kiểu. Hai đoạn trên được trình bày liền nhau để dễ đọc.

### 4.2. Vì sao dùng model lồng nhau?

Nếu chỉ có một sản phẩm, model phẳng có thể đủ. Nhưng đơn hàng thường có danh sách nhiều dòng. Model lồng nhau:

~~~text
OrderConfirmationMailModel
  customerName
  orderNumber
  orderedAtText
  orderLines
    ├── OrderLineMailModel
    ├── OrderLineMailModel
    └── OrderLineMailModel
  subtotalText
  shippingFeeText
  totalText
  orderUrl
~~~

giúp mỗi dòng sản phẩm có cấu trúc nhất quán. Nếu thêm trường `discountText` hoặc `imageUrl` cho mỗi sản phẩm, chỉ cần mở rộng `OrderLineMailModel` và template tương ứng, không cần tạo một nhóm biến rời rạc như `product1Name`, `product2Name`.

## 5. Tạo model từ dữ liệu nghiệp vụ

Template không nên truy vấn database. Application service hoặc một mapper chuyên trách lấy dữ liệu và chuyển thành model.

Ví dụ mô hình:

~~~java
public class OrderMailModelMapper {

    public OrderConfirmationMailModel toModel(
            Order order,
            Customer customer,
            Locale locale,
            URI trustedBaseUri) {
        // Chọn dữ liệu và format trước khi giao cho template.
    }
}
~~~

Mapper cần:

1. Chọn trường được phép hiển thị.
2. Kiểm tra dữ liệu bắt buộc.
3. Format tiền, ngày giờ và locale.
4. Tạo URL từ domain đáng tin cậy.
5. Chuyển danh sách entity thành danh sách model con.
6. Áp dụng các giá trị mặc định theo nghiệp vụ.

### 5.1. Ví dụ mapper có format tiền và ngày giờ

~~~java
package com.example.mail.mapping;

import com.example.mail.model.OrderConfirmationMailModel;
import com.example.mail.model.OrderLineMailModel;
import java.math.BigDecimal;
import java.net.URI;
import java.text.NumberFormat;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import org.springframework.web.util.UriComponentsBuilder;

public class OrderMailModelMapper {

    public OrderConfirmationMailModel toModel(
            Order order,
            Customer customer,
            Locale locale,
            ZoneId displayZone,
            URI trustedBaseUri) {

        NumberFormat moneyFormat =
                NumberFormat.getCurrencyInstance(locale);
        moneyFormat.setCurrency(Currency.getInstance(order.currencyCode()));

        DateTimeFormatter dateFormat =
                DateTimeFormatter.ofPattern(
                        "dd/MM/yyyy HH:mm z",
                        locale
                ).withZone(displayZone);

        List<OrderLineMailModel> lines = order.lines().stream()
                .map(line -> new OrderLineMailModel(
                        line.productName(),
                        line.sku(),
                        line.quantity(),
                        moneyFormat.format(line.unitPrice()),
                        moneyFormat.format(line.lineTotal())
                ))
                .toList();

        URI orderUrl = UriComponentsBuilder
                .fromUri(trustedBaseUri)
                .pathSegment("orders", order.publicReference())
                .build()
                .encode()
                .toUri();

        return new OrderConfirmationMailModel(
                customer.displayName(),
                order.publicReference(),
                dateFormat.format(order.createdAt()),
                lines,
                moneyFormat.format(order.subtotal()),
                moneyFormat.format(order.shippingFee()),
                moneyFormat.format(order.total()),
                orderUrl.toString(),
                true
        );
    }
}
~~~

Đoạn mapper giả định các kiểu `Order`, `Customer` và các phương thức như `currencyCode()`, `createdAt()` đã tồn tại trong domain model. Nó là ví dụ về vị trí đặt logic chuẩn bị dữ liệu, không phải định nghĩa một entity cụ thể cho mọi dự án.

**Tiền:** dùng `BigDecimal` để tính toán trong nghiệp vụ. `NumberFormat` chỉ phục vụ hiển thị, không được dùng chuỗi đã format để tính tổng hoặc so sánh số tiền.

**Ngày giờ:** lưu thời điểm theo kiểu có timezone/instant rõ ràng; format theo timezone của người nhận hoặc quy tắc của sản phẩm. Không lấy timezone mặc định của máy chủ làm quy tắc hiển thị cho mọi khách hàng.

**URL:** `trustedBaseUri` phải đến từ cấu hình được kiểm soát. Không lấy host từ header `Host` hoặc URL tùy ý do người dùng gửi rồi đưa thẳng vào email. Nếu `publicReference` chứa ký tự đặc biệt, `pathSegment` cùng `encode()` giúp tạo URI phù hợp.

### 5.2. Không tính toán nghiệp vụ trong template

Template có thể lặp qua các dòng sản phẩm, hiển thị `totalText` và ẩn/hiện phần hỗ trợ. Nhưng không nên dùng expression trong template để:

- tự tính thuế, giảm giá hoặc tổng tiền;
- quyết định đơn hàng đã thanh toán hay chưa;
- xác định người nhận có quyền xem đơn hàng;
- truy vấn repository hoặc gọi dịch vụ bên ngoài;
- sinh token xác thực hoặc tự tạo mã bảo mật.

Những quyết định này thuộc domain/application service. Template là nơi **trình bày dữ liệu đã được quyết định**.

## 6. Truyền model vào Thymeleaf

Sau khi mapper tạo `OrderConfirmationMailModel`, application service tạo context:

~~~java
import java.util.Locale;
import org.thymeleaf.context.Context;

OrderConfirmationMailModel model = mapper.toModel(
        order,
        customer,
        Locale.forLanguageTag("vi-VN"),
        ZoneId.of("Asia/Ho_Chi_Minh"),
        URI.create("https://app.company.example")
);

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", model);

String html = templateEngine.process(
        "mail/order-confirmation",
        context
);
~~~

Thay vì đưa từng biến ở cấp root:

~~~java
context.setVariable("customerName", model.customerName());
context.setVariable("orderNumber", model.orderNumber());
context.setVariable("totalText", model.totalText());
~~~

ta có thể đưa **một đối tượng có tên rõ ràng** là `mail`. Cách này giảm số lượng biến root và giúp template thể hiện chúng thuộc cùng một hợp đồng dữ liệu.

Hai cách đều hợp lệ. Chọn một quy ước thống nhất trong dự án; nếu template có nhiều nhóm dữ liệu khác nhau, có thể dùng các tên riêng như `mail`, `branding` hoặc `footer` nhưng không nên biến context thành nơi chứa mọi service và entity của ứng dụng.

## 7. Dùng model trong HTML template

Ví dụ `src/main/resources/templates/mail/order-confirmation.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body style="margin:0;padding:24px;font-family:Arial,sans-serif;">
  <main style="max-width:600px;margin:auto;">
    <h1>Đơn hàng đã được xác nhận</h1>

    <p>
      Xin chào
      <strong th:text="${mail.customerName}">Khách hàng</strong>,
    </p>

    <p>
      Mã đơn:
      <strong th:text="${mail.orderNumber}">A123</strong>
    </p>

    <p>
      Thời gian đặt:
      <span th:text="${mail.orderedAtText}">12/11/2026</span>
    </p>

    <table role="presentation" cellpadding="8" cellspacing="0"
           style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th align="left">Sản phẩm</th>
          <th align="right">Số lượng</th>
          <th align="right">Đơn giá</th>
          <th align="right">Thành tiền</th>
        </tr>
      </thead>
      <tbody>
        <tr th:each="line : ${mail.orderLines}">
          <td th:text="${line.productName}">Tên sản phẩm</td>
          <td align="right" th:text="${line.quantity}">1</td>
          <td align="right" th:text="${line.unitPriceText}">100.000 ₫</td>
          <td align="right" th:text="${line.lineTotalText}">100.000 ₫</td>
        </tr>
      </tbody>
    </table>

    <p>
      <strong>Tổng cộng:</strong>
      <span th:text="${mail.totalText}">100.000 ₫</span>
    </p>

    <p>
      <a th:href="${mail.orderUrl}"
         href="https://app.company.example/orders/A123">
        Xem đơn hàng
      </a>
    </p>

    <p th:if="${mail.showSupportInformation}">
      Nếu cần hỗ trợ, vui lòng trả lời email này.
    </p>
  </main>
</body>
</html>
~~~

Các expression truy cập thuộc tính của model:

| Expression | Giá trị lấy ra |
| --- | --- |
| `mail.customerName` | Tên khách hàng |
| `mail.orderNumber` | Mã đơn |
| `mail.orderLines` | Danh sách dòng sản phẩm |
| `line.productName` | Tên của dòng đang lặp |
| `mail.totalText` | Tổng tiền đã format |
| `mail.orderUrl` | Link đã được ứng dụng tạo |
| `mail.showSupportInformation` | Cờ điều khiển phần hỗ trợ |

`th:text` escape nội dung theo ngữ cảnh text HTML. Dữ liệu người dùng như tên khách hàng hoặc tên sản phẩm nên được đưa vào bằng `th:text`, không dùng `th:utext` để render trực tiếp markup không tin cậy.

### 7.1. Dùng một model cho HTML và plain text

Email giao dịch quan trọng nên có cả hai dạng nội dung. Plain text có thể được dựng từ cùng model:

~~~java
public String renderPlainText(OrderConfirmationMailModel mail) {
    StringBuilder text = new StringBuilder();
    text.append("Xin chào ")
        .append(mail.customerName())
        .append("\n\n");
    text.append("Đơn hàng ")
        .append(mail.orderNumber())
        .append(" đã được xác nhận.\n");
    text.append("Thời gian đặt: ")
        .append(mail.orderedAtText())
        .append("\n\n");

    for (OrderLineMailModel line : mail.orderLines()) {
        text.append("- ")
            .append(line.productName())
            .append(" x ")
            .append(line.quantity())
            .append(": ")
            .append(line.lineTotalText())
            .append("\n");
    }

    text.append("\nTổng cộng: ")
        .append(mail.totalText())
        .append("\n");
    text.append("Xem đơn hàng: ")
        .append(mail.orderUrl())
        .append("\n");

    return text.toString();
}
~~~

Sau đó:

~~~java
helper.setText(
        renderPlainText(model),
        html
);
~~~

`setText(plainText, htmlText)` của `MimeMessageHelper` thiết lập hai cách biểu diễn thay thế của cùng nội dung email. Cả hai dùng cùng model để tránh sai lệch mã đơn, tổng tiền hoặc liên kết giữa HTML và text.

## 8. Chọn giữa dữ liệu đã format và dữ liệu có kiểu

Có hai cách phổ biến:

**Cách A — model chứa giá trị đã format:**

~~~java
public record OrderMailModel(
        String totalText,
        String orderedAtText) {
}
~~~

Ưu điểm: template đơn giản, không phải biết cách format tiền và thời gian. Nhược điểm: nếu nhiều template cần cùng dữ liệu theo locale khác nhau, mapper phải tạo model riêng cho từng locale.

**Cách B — model giữ kiểu dữ liệu:**

~~~java
public record OrderMailModel(
        BigDecimal total,
        Currency currency,
        Instant orderedAt) {
}
~~~

Ưu điểm: giữ ý nghĩa kiểu dữ liệu, có thể format theo locale ở renderer. Nhược điểm: template hoặc expression có thể phức tạp hơn và dễ phân tán quy tắc format nếu không có formatter chung.

### 8.1. Cách chọn phù hợp

| Yêu cầu | Cách thường phù hợp |
| --- | --- |
| Một locale, một định dạng cố định | Có thể format trước thành text |
| Nhiều locale, nhiều currency | Giữ kiểu dữ liệu và format qua một formatter dùng chung hoặc mapper theo locale |
| Template đơn giản, người chỉnh template không cần biết Java type | Chuỗi hiển thị đã format |
| Có nhiều phép hiển thị khác nhau từ cùng giá trị | Giữ kiểu và cung cấp các field/formatter rõ nghĩa |
| Dữ liệu cần tính toán/so sánh | Giữ kiểu gốc ở tầng nghiệp vụ; không tính bằng chuỗi đã format |

Một cách cân bằng là model chứa **giá trị nghiệp vụ có kiểu** cùng **các trường display text** cần thiết:

~~~java
public record MoneyMailModel(
        BigDecimal amount,
        String currencyCode,
        String displayText) {
}
~~~

Nhưng không nên nhân đôi mọi trường nếu template chỉ cần một chuỗi. Model cần phục vụ yêu cầu thật, không phải trở thành bản sao của toàn bộ domain object.

## 9. Null, trường tùy chọn và danh sách rỗng

Template có thể hiển thị sai hoặc ném lỗi khi một biến không có. Cần định nghĩa chính sách dữ liệu rõ ràng:

- Trường bắt buộc: không tạo model nếu thiếu.
- Trường tùy chọn: dùng `Optional` ở tầng ứng dụng nếu hữu ích, rồi chuyển thành giá trị rõ ràng cho template.
- Danh sách không có phần tử: thường dùng danh sách rỗng thay vì `null`.
- Văn bản có thể bỏ qua: dùng chuỗi rỗng hoặc cờ hiển thị tùy nghiệp vụ.

Ví dụ:

~~~java
List<OrderLineMailModel> lines =
        sourceLines == null
                ? List.of()
                : sourceLines.stream()
                    .map(this::toMailLine)
                    .toList();
~~~

Trong record, `List.copyOf` không chấp nhận `null`; vì vậy hãy chuẩn hóa null thành danh sách rỗng **trước khi** tạo model, hoặc từ chối nếu danh sách là bắt buộc.

### 9.1. Dùng cờ hiển thị thay cho logic rối trong template

Nếu phần địa chỉ giao hàng chỉ xuất hiện khi đơn có giao tận nơi:

~~~java
public record DeliveryMailModel(
        boolean showDeliveryAddress,
        String deliveryAddressText) {
}
~~~

Template:

~~~html
<section th:if="${mail.delivery.showDeliveryAddress}">
  <h2>Địa chỉ giao hàng</h2>
  <p th:text="${mail.delivery.deliveryAddressText}">Địa chỉ</p>
</section>
~~~

Một cờ boolean diễn tả quyết định đã được nghiệp vụ chuẩn bị. Tránh tạo điều kiện template dựa trên nhiều trường trạng thái nội bộ như `paymentStatus`, `fulfillmentCode`, `isPickup` rồi tự suy ra quy tắc phức tạp; hãy để mapper chuyển thành ý nghĩa rõ ràng như `showDeliveryAddress`.

## 10. Dữ liệu an toàn và quyền riêng tư

Email thường được lưu ở nhiều nơi: hộp thư người nhận, hệ thống gửi, log, bản sao backup và các công cụ preview. Do đó, template model phải tuân theo nguyên tắc **chỉ đưa dữ liệu cần thiết vào nội dung thư**.

### 10.1. Không truyền toàn bộ entity

Tránh:

~~~java
context.setVariable("user", userEntity);
context.setVariable("order", orderEntity);
context.setVariable("payment", paymentEntity);
~~~

Nên tạo DTO:

~~~java
public record AccountWelcomeMailModel(
        String displayName,
        String supportAddress,
        String signInUrl) {
}
~~~

Không đưa password, password hash, session cookie, API token, secret key, dữ liệu thẻ thanh toán đầy đủ hoặc ghi chú nội bộ vào template model. Nếu email cần một mã xác minh, hãy áp dụng token ngẫu nhiên, phạm vi và hạn dùng phù hợp; không dùng một giá trị bí mật dài hạn làm nội dung thư.

### 10.2. Escape nội dung theo đúng ngữ cảnh

Một giá trị an toàn khi hiển thị dạng text chưa chắc an toàn khi đặt vào:

- thuộc tính HTML;
- URL;
- CSS;
- JavaScript;
- tên file hoặc header email.

Hãy dùng cú pháp template engine đúng ngữ cảnh và API URI/HTML phù hợp. Với Thymeleaf, ưu tiên `th:text` và `th:href`; không đưa dữ liệu không tin cậy vào `th:utext`, `th:style` hoặc expression tùy ý.

### 10.3. URL phải được tạo từ nguồn tin cậy

Một model có `orderUrl` nên nhận link đã được ứng dụng tạo từ base URL được cấu hình. Không lấy nguyên giá trị `returnUrl` do người dùng nhập rồi đưa vào template. Template engine có thể escape thuộc tính, nhưng không biết URL đó có trỏ đến domain hợp lệ hay không.

Khi tạo link xác nhận hoặc đặt lại mật khẩu, cân nhắc:

- HTTPS;
- token ngẫu nhiên, khó đoán, giới hạn mục đích và có thời hạn;
- không log đầy đủ token;
- không dùng link làm cơ chế duy nhất thay thế xác thực/ủy quyền ở backend;
- không để template hoặc model biến một URL ngoài domain thành link được tin cậy.

### 10.4. Giới hạn dữ liệu cá nhân trong email

Không phải thông tin nào có trong database cũng nên đưa vào email. Ví dụ, hóa đơn có thể chỉ cần mã đơn, một phần địa chỉ, tổng tiền và link xem chi tiết sau đăng nhập. Dữ liệu tài khoản hoặc thanh toán nhạy cảm nên được giảm thiểu theo chính sách sản phẩm và pháp luật áp dụng.

## 11. Tính bất biến của model khi gửi qua queue

Nếu email được gửi bất đồng bộ, model có thể được đưa vào queue hoặc outbox. Một model mutable có thể bị producer sửa sau khi enqueue, làm worker render nội dung khác dự định.

Ví dụ không an toàn:

~~~java
class MutableMailModel {
    String customerName;
    List<OrderLineMailModel> orderLines;
}

queue.add(model);
model.orderLines.clear(); // Worker có thể thấy danh sách rỗng.
~~~

Với record và defensive copy:

~~~java
public record OrderMailJob(
        String customerName,
        String orderNumber,
        List<OrderLineMailModel> orderLines,
        String totalText,
        String orderUrl) {

    public OrderMailJob {
        orderLines = List.copyOf(orderLines);
    }
}
~~~

`String` và record con với trường bất biến phù hợp cho snapshot. Nếu một record chứa `byte[]`, `Date`, `Map` mutable hoặc entity mutable, bản thân record chưa đủ bất biến; cần sao chép sâu hoặc chuyển sang kiểu giá trị bất biến.

### 11.1. Chụp dữ liệu hay render HTML trước khi enqueue?

Có hai chiến lược:

| Chiến lược | Payload queue | Ưu điểm | Điều cần quản lý |
| --- | --- | --- | --- |
| Enqueue model bất biến rồi render ở worker | DTO và template version | Payload nhỏ, dễ quan sát các trường | Phải giữ template version và dữ liệu snapshot ổn định |
| Render HTML/text trước rồi enqueue | Nội dung đã render | Giữ nguyên chính xác nội dung đã tạo | Payload lớn, cần bảo vệ nội dung cá nhân trong queue |

Nếu nghiệp vụ yêu cầu retry phải gửi **đúng nội dung đã được chấp nhận**, hãy lưu HTML/text snapshot hoặc model bất biến cùng template version. Không nên chỉ lưu `orderId` rồi worker truy vấn dữ liệu mới nhất và dùng template mới nhất một cách ngẫu nhiên.

### 11.2. Model không chứa SMTP secret

Payload queue không nên có:

~~~text
smtpPassword
smtpApiKey
oauthRefreshToken
databasePassword
~~~

Worker lấy thông tin kết nối từ cấu hình runtime hoặc secret manager. Như vậy, khi rotate credentials, không phải sửa tất cả job đang chờ và không nhân bản secret vào broker, dead-letter queue hay backup.

## 12. Mô hình dữ liệu cho các loại email khác nhau

Không nên ép mọi email dùng một model khổng lồ có hàng chục trường tùy chọn. Mỗi loại email có một hợp đồng riêng:

| Loại email | Model có thể cần |
| --- | --- |
| Chào mừng tài khoản | `displayName`, `signInUrl`, `supportAddress` |
| Xác nhận đơn hàng | `customerName`, `orderNumber`, `orderLines`, `totalText`, `orderUrl` |
| Đặt lại mật khẩu | `displayName`, `resetUrl`, `expiresAtText` |
| Báo cáo định kỳ | `reportTitle`, `periodText`, `summaryRows`, `downloadUrl` |
| Thông báo ticket | `ticketNumber`, `statusText`, `latestMessagePreview`, `ticketUrl` |
| Hóa đơn | `invoiceNumber`, `issuedAtText`, `billingAddress`, `lineItems`, `grandTotalText` |

Một kiểu riêng cho mỗi loại mail giúp compiler và người đọc code hiểu dữ liệu nào cần có. Có thể dùng interface chung cho metadata thật sự dùng chung, nhưng đừng tạo abstraction chỉ để tất cả model có cùng tên trường không liên quan.

### 12.1. Phân biệt model nội dung và mail command

Một yêu cầu gửi có thể gồm:

~~~java
public record SendTemplatedMailCommand(
        String recipient,
        String templateId,
        String templateVersion,
        Locale locale,
        OrderConfirmationMailModel model) {
}
~~~

Đây là **command/job** mô tả yêu cầu gửi một template. `OrderConfirmationMailModel` là **dữ liệu nội dung**. Khi cần nhiều recipient, Cc/Bcc, sender identity, correlation ID hoặc schedule, những thông tin đó có thể thuộc envelope/job metadata chứ không cần nhồi vào model HTML.

Việc tách command và model giúp:

- một model có thể render HTML và text;
- một command có thể xác định template/locale/version;
- metadata vận chuyển có thể thay đổi theo môi trường;
- test renderer không cần tạo SMTP sender;
- worker có thể kiểm tra trạng thái job mà không phân tích nội dung HTML.

## 13. Model đa ngôn ngữ và thương hiệu

Một ứng dụng có thể gửi cùng một loại email bằng tiếng Việt hoặc tiếng Anh. Không nên để template tự đoán locale từ tên hoặc địa chỉ email người nhận.

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
OrderConfirmationMailModel model = mapper.toModel(order, customer, locale);

Context context = new Context(locale);
context.setVariable("mail", model);
~~~

Template engine có thể dùng message bundle để lấy các chuỗi tĩnh như tiêu đề bảng, nhãn “Tổng cộng” hoặc câu chào. Dữ liệu động như tên, mã đơn và số tiền vẫn đến từ model.

### 13.1. Cấu trúc thư mục theo locale

~~~text
templates/
  mail/
    vi/
      order-confirmation.html
    en/
      order-confirmation.html
~~~

Ứng dụng chọn template dựa trên locale đã xác định:

~~~java
String templateName = switch (locale.toLanguageTag()) {
    case "en", "en-US", "en-GB" -> "mail/en/order-confirmation";
    default -> "mail/vi/order-confirmation";
};
~~~

Đây chỉ là ví dụ chọn template. Với hệ thống lớn, có thể dùng locale resolver hoặc message bundles thay vì tự viết switch dài. Quan trọng là có **fallback locale được định nghĩa**, để không tạo email với một nửa nhãn tiếng Việt và một nửa tiếng Anh.

### 13.2. Branding nên tách khỏi dữ liệu giao dịch

Logo, màu chủ đạo, tên công ty và địa chỉ hỗ trợ có thể thuộc một model thương hiệu:

~~~java
public record MailBrandingModel(
        String companyName,
        String logoUrl,
        String supportEmail,
        String footerText) {
}
~~~

Khi render, truyền `mail` và `branding` riêng:

~~~java
context.setVariable("mail", orderModel);
context.setVariable("branding", brandingModel);
~~~

Như vậy, thay đổi logo hoặc footer không buộc phải thêm trường vào mọi model giao dịch. Tuy nhiên, nếu branding phải cố định theo thời điểm enqueue, cần snapshot hoặc version hóa nó giống template.

## 14. Attachment và tài nguyên ngoài model nội dung

Email có thể có file đính kèm, ảnh inline hoặc tài liệu tải về. Những dữ liệu này không nhất thiết nên đặt trực tiếp vào template model.

Một command gửi có thể phân biệt:

~~~text
Template data:
  customerName
  invoiceNumber
  totalText
  downloadUrl

Message resources:
  attachment: invoice.pdf
  inline image: company-logo
~~~

Attachment là dữ liệu MIME, có thể cần bytes, resource hoặc ID object storage. Template data chủ yếu mô tả nội dung hiển thị. Nếu template cần tham chiếu ảnh CID, hãy đồng bộ ID giữa HTML và MIME builder; nhưng không nhất thiết phải nhét toàn bộ bytes ảnh vào context.

Khi đưa tài nguyên vào queue:

- không chỉ giữ đường dẫn tới file tạm có thể bị xóa/ghi đè;
- lưu phiên bản object storage hoặc content hash nếu cần tính toàn vẹn;
- giới hạn kích thước payload và tổng dung lượng email;
- bảo vệ quyền truy cập file;
- tránh log nội dung hoặc dữ liệu nhị phân.

## 15. Kiểm thử model và template

Tách model giúp kiểm thử mà không cần SMTP thật. Có thể kiểm tra theo ba tầng:

1. **Mapper test:** dữ liệu domain được chuyển thành model đúng.
2. **Template render test:** model tạo ra HTML/text với biến đúng và escaping đúng.
3. **Mail assembly test:** HTML/text được đưa vào MIME đúng, header và recipient được đặt phù hợp.

### 15.1. Test mapper

Ví dụ ý tưởng:

~~~java
@Test
void mapsOrderToMailModel() {
    Order order = sampleOrder();
    Customer customer = sampleCustomer();

    OrderConfirmationMailModel model = mapper.toModel(
            order,
            customer,
            Locale.forLanguageTag("vi-VN"),
            ZoneId.of("Asia/Ho_Chi_Minh"),
            URI.create("https://app.company.example")
    );

    assertEquals("A123", model.orderNumber());
    assertEquals("Nguyễn An", model.customerName());
    assertFalse(model.orderLines().isEmpty());
    assertTrue(model.orderUrl().startsWith(
            "https://app.company.example/orders/"));
}
~~~

Các hàm `sampleOrder()` và `sampleCustomer()` là fixture do test cung cấp. Test cần kiểm tra cả trường hợp thiếu dữ liệu, currency khác nhau, timezone, danh sách rỗng và link có ký tự cần encode.

### 15.2. Test template với dữ liệu đặc biệt

Một model thử có tên:

~~~text
An <Admin> & Co
~~~

nên được render bằng `th:text` để HTML chứa dạng escape tương ứng, thay vì tạo thêm một element HTML ngoài ý muốn. Kiểm tra thêm:

- mã đơn có ký tự đặc biệt;
- tên sản phẩm dài;
- danh sách rỗng hoặc nhiều dòng;
- URL được tạo từ domain được phép;
- trường tùy chọn bị ẩn đúng cách;
- locale fallback hoạt động;
- tổng tiền và ngày giờ không bị sai định dạng.

### 15.3. Test mail assembly

Có thể mock `JavaMailSender` và capture `MimeMessage` được gửi để xác nhận:

- `From`, `To`, `Reply-To` và `Subject`;
- `text/plain` và `text/html` có cùng thông tin cốt lõi;
- attachment và Content-ID khớp với model/resource;
- charset là UTF-8 khi có tiếng Việt.

Với integration test, SMTP server giả lập như Mailpit hoặc GreenMail giúp xem raw message và preview. Nó xác nhận việc nộp thư tới test server, không chứng minh thư đã được giao tới Inbox production.

## 16. Version hóa model và template

Template có thể thay đổi theo thời gian: thêm trường, đổi tên biến, thay bố cục hoặc chuyển locale. Nếu có job gửi đang chờ, một template mới có thể không còn hiểu model cũ.

Ví dụ:

~~~text
Template v1:
  customerName
  orderNumber
  totalText

Template v2:
  recipient.displayName
  order.reference
  totals.grandTotalText
  actions.orderUrl
~~~

Nếu deploy template v2 trong khi queue vẫn có payload theo cấu trúc v1, worker có thể render thiếu biến hoặc thất bại.

Các lựa chọn:

- **Giữ tương thích ngược:** template mới hỗ trợ các trường cũ trong thời gian job cũ còn tồn tại.
- **Version hóa template/model:** job ghi `templateId` và `templateVersion`, worker chọn đúng phiên bản.
- **Render trước enqueue:** lưu HTML/text snapshot nếu cần đảm bảo nội dung không đổi.
- **Migration payload:** chỉ dùng khi có kế hoạch chuyển đổi dữ liệu job rõ ràng.

Không nên đổi tên field trong model và xóa template cũ ngay khi còn job chờ sử dụng phiên bản cũ. Thời gian lưu queue, dead-letter queue và lịch retry cũng cần được tính vào thời gian giữ template tương thích.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Vì sao gây vấn đề | Hướng thay thế |
| --- | --- | --- |
| Truyền toàn bộ JPA entity vào template | Lộ trường, lazy loading, phụ thuộc schema | DTO/model riêng cho email |
| Một model khổng lồ cho mọi loại mail | Nhiều field null và logic khó hiểu | Model riêng theo loại email |
| Tên biến viết tắt theo cột DB | Khó đọc, template phụ thuộc database | Tên theo ngữ nghĩa nghiệp vụ |
| Tính tổng tiền trong Thymeleaf | Trộn logic nghiệp vụ với trình bày | Tính trong domain/application service |
| Truyền raw HTML do người dùng nhập | Nguy cơ markup độc hại | Escape text hoặc sanitize allowlist có kiểm soát |
| Dùng URL tùy ý trong model | Có thể dẫn tới domain lừa đảo | Sinh URL từ base URI tin cậy |
| Dùng một chuỗi cho cả HTML và plain text | Bản text có thể hiện thẻ hoặc thiếu nội dung | Render hai dạng từ cùng model |
| Đưa SMTP password vào context | Secret xuất hiện trong template/debug payload | Secret chỉ ở runtime configuration |
| Model mutable được giữ trong queue | Producer có thể sửa nội dung sau enqueue | Record/immutable snapshot và defensive copy |
| Không version template | Job cũ không tương thích template mới | Template version hoặc snapshot nội dung |
| Model chứa dữ liệu quá nhạy cảm | Email, queue và log trở thành nơi lưu dữ liệu không cần thiết | Data minimization và retention |
| Template tự truy vấn database | Render khó kiểm thử, phụ thuộc transaction | Mapper tạo model trước khi render |

## 18. Quy trình thiết kế model cho một template mới

Khi nhận yêu cầu tạo email, có thể làm theo thứ tự:

1. **Xác định mục đích và người nhận:** email này thông báo điều gì, ai được phép xem?
2. **Phác thảo nội dung:** xác định phần tiêu đề, đoạn văn, danh sách, CTA và footer.
3. **Liệt kê biến:** tên, mã, số tiền, thời gian, URL, cờ hiển thị.
4. **Phân loại trường:** bắt buộc/tùy chọn, kiểu dữ liệu, dữ liệu nhạy cảm, locale.
5. **Tạo DTO/record:** dùng kiểu có ý nghĩa, nested model cho danh sách, defensive copy khi cần.
6. **Viết mapper:** lấy dữ liệu từ domain, format và tạo link từ nguồn tin cậy.
7. **Đưa model vào template context:** đặt một hợp đồng tên biến rõ ràng.
8. **Render HTML và plain text:** cùng model để nội dung không lệch nhau.
9. **Dựng MIME và gửi:** tách header/recipient khỏi model nội dung.
10. **Kiểm thử và version hóa:** test dữ liệu biên, locale, escaping và các job đang chờ.

### 18.1. Bảng hợp đồng dữ liệu mẫu

Trước khi viết code, có thể ghi hợp đồng cho email xác nhận đơn hàng:

| Field | Kiểu | Bắt buộc | Nguồn | Hiển thị ở đâu |
| --- | --- | --- | --- | --- |
| `customerName` | `String` | Có | Hồ sơ khách hàng | Lời chào |
| `orderNumber` | `String` | Có | Đơn hàng | Tiêu đề/nội dung |
| `orderedAtText` | `String` | Có | Thời điểm tạo + timezone | Chi tiết đơn |
| `orderLines` | `List<OrderLineMailModel>` | Có, có thể rỗng theo chính sách | Chi tiết đơn | Bảng sản phẩm |
| `totalText` | `String` | Có | Tổng tiền đã tính và format | Tổng cộng |
| `orderUrl` | `String` hoặc `URI` | Có | Base URL tin cậy + mã public | CTA |
| `showSupportInformation` | `boolean` | Không | Quy tắc sản phẩm | Đoạn hỗ trợ |

Hợp đồng này có thể được lưu cùng tài liệu template hoặc thể hiện trong Java record. Khi thêm hoặc đổi field, cần cập nhật mapper, template, fixture và test cùng lúc.

## 19. Tình huống tổng hợp: một model phục vụ nhiều cách trình bày

Giả sử hệ thống gửi xác nhận đơn hàng qua email. Một lần tạo model:

~~~java
OrderConfirmationMailModel model = new OrderConfirmationMailModel(
        "Nguyễn An",
        "A123",
        "12/11/2026 14:30 GMT+7",
        List.of(
                new OrderLineMailModel(
                        "Sách Java",
                        "JAVA-01",
                        1,
                        "200.000 ₫",
                        "200.000 ₫"),
                new OrderLineMailModel(
                        "Phí giao hàng",
                        "SHIP",
                        1,
                        "20.000 ₫",
                        "20.000 ₫")
        ),
        "200.000 ₫",
        "20.000 ₫",
        "220.000 ₫",
        "https://app.company.example/orders/A123",
        true
);
~~~

Từ cùng model:

- HTML template hiển thị bảng, tiêu đề, màu sắc và nút xem đơn hàng.
- Plain-text renderer tạo danh sách có dấu gạch đầu dòng và URL đầy đủ.
- Test mapper xác nhận mã đơn, tiền và link.
- Test template xác nhận tên có ký tự đặc biệt được escape.
- Queue có thể giữ snapshot model bất biến và template version.
- Mail assembly tạo `MimeMessage` mới, đặt header rồi gửi bằng `JavaMailSender`.

Nếu sau này thay HTML từ bố cục bảng sang bố cục thẻ, **model không nhất thiết phải đổi** vì ý nghĩa dữ liệu vẫn như cũ. Nếu nghiệp vụ thêm trường “mã vận đơn”, lúc đó mới mở rộng model và hợp đồng template tương ứng.

Đây là mục tiêu của một mô hình dữ liệu tốt: template nhận đúng dữ liệu cần trình bày, không phụ thuộc vào database, SMTP hay các chi tiết nội bộ. Khi ranh giới này rõ ràng, một ứng dụng Spring Mail có thể phát triển thêm nhiều email template, nhiều locale và nhiều kênh gửi mà vẫn kiểm soát được tính nhất quán, bảo mật và khả năng kiểm thử.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và cách tạo thông điệp.
- **Spring Boot Reference — Thymeleaf:** auto-configuration, template resolver và cấu hình template.
- **Thymeleaf Documentation — Standard Dialect:** truy cập biến, lặp danh sách, điều kiện, escaping và URL.
- **Java Language Specification / Java API:** record, immutable value types, `List.copyOf` và các kiểu ngày giờ.
- **Java API — `BigDecimal`, `Currency` và `NumberFormat`:** lưu và hiển thị tiền tệ.
- **RFC 2045–2049 — MIME:** biểu diễn nội dung plain text, HTML và multipart trong email.
