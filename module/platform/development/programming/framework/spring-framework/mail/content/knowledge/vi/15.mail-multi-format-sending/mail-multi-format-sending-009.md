# Xử lý client chỉ đọc plain text

Email không phải lúc nào cũng được mở bằng ứng dụng có thể hiển thị HTML. Một số gateway chỉ trích xuất văn bản thuần, một số người dùng tắt HTML vì lý do bảo mật hoặc trợ năng, và một số mail client/thiết bị chỉ trình bày phần **plain text**. Nếu ứng dụng Spring Mail chỉ tạo HTML, người nhận có thể thấy email trống, thiếu đường dẫn quan trọng hoặc không biết phải thực hiện hành động gì.

Trong **Spring Framework Mail**, cách phổ biến để hỗ trợ cả hai nhóm client là gửi email theo định dạng MIME **`multipart/alternative`**, gồm một phần `text/plain` và một phần `text/html` diễn đạt cùng một thông điệp. Với `MimeMessageHelper`, tạo hai phiên bản bằng `helper.setText(plainText, htmlText)`. Mail client có thể chọn bản HTML nếu hỗ trợ; client chỉ đọc plain text có thể dùng bản văn bản thuần.

Plain text phải là **một phiên bản nội dung hoàn chỉnh**, không chỉ là câu “Hãy bật HTML để xem email”. Người nhận vẫn cần biết thông tin chính, đường dẫn, thời hạn, cách liên hệ và hành động tiếp theo ngay cả khi toàn bộ HTML bị bỏ qua.

## 1. Vì sao cần hỗ trợ plain-text client?

Có nhiều lý do khiến HTML không được hiển thị:

- Mail client hoặc gateway chỉ trích xuất `text/plain`.
- Người nhận chọn chế độ xem văn bản thuần.
- Chính sách bảo mật của tổ chức loại bỏ HTML hoặc nội dung chủ động.
- Thiết bị/ứng dụng email có khả năng hiển thị hạn chế.
- Công cụ đọc thư, lưu trữ, tìm kiếm hoặc hệ thống ticket chỉ xử lý plain text.
- Người dùng cần trình đọc màn hình hoặc giao diện đơn giản, không muốn phụ thuộc vào bố cục HTML.
- HTML bị chặn do lỗi định dạng, sanitizer hoặc policy của mail client.

Một email chỉ có HTML có thể hiển thị đẹp trên một số ứng dụng nhưng mất thông tin ở các môi trường còn lại. Nếu CTA chỉ là một nút HTML và URL không xuất hiện trong text, người nhận plain-text sẽ không thể truy cập hành động đó.

**Plain text là một phần của nội dung sản phẩm**, không chỉ là phương án dự phòng kỹ thuật. Nội dung này phải được viết và kiểm tra cùng với HTML.

## 2. MIME multipart/alternative hoạt động như thế nào?

MIME cho phép một email chứa nhiều phần nội dung. Với `multipart/alternative`, các phần là những cách trình bày thay thế cho **cùng một thông điệp**.

Ví dụ cấu trúc khái niệm:

```text
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-001"

--alt-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin chào An,

Đơn hàng ORD-2026-001 đã được xác nhận.
Xem đơn hàng: https://shop.example.com/orders/ORD-2026-001

--alt-001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html>
  <body>
    <h1>Xin chào An!</h1>
    <p>Đơn hàng <strong>ORD-2026-001</strong> đã được xác nhận.</p>
    <a href="https://shop.example.com/orders/ORD-2026-001">
      Xem đơn hàng
    </a>
  </body>
</html>

--alt-001--
```

Đây là ví dụ minh họa đã rút gọn; boundary và encoding thực tế do thư viện MIME tạo.

Các điểm cần nhớ:

- Mỗi part có `Content-Type` riêng.
- `text/plain` chứa nội dung văn bản thuần.
- `text/html` chứa markup HTML.
- Hai part biểu đạt cùng một thông điệp và không nên mâu thuẫn.
- `multipart/alternative` báo cho client rằng các part là những lựa chọn thay thế.
- Theo quy ước MIME, phần có mức độ phong phú cao hơn thường được đặt sau; vì vậy plain text thường đứng trước HTML.

Mail client tự chọn phiên bản phù hợp với khả năng và thiết lập của nó. Ứng dụng gửi không thể ép mọi client phải hiển thị HTML.

### 2.1. Khác nhau giữa alternative, mixed và related

| MIME type | Mục đích | Ví dụ |
|---|---|---|
| `multipart/alternative` | Nhiều cách trình bày cùng một nội dung | Plain text và HTML. |
| `multipart/mixed` | Gộp nội dung chính với các phần độc lập | Email kèm PDF. |
| `multipart/related` | Gắn tài nguyên liên quan tới một phần nội dung | HTML tham chiếu ảnh qua CID. |

Một email có thể kết hợp nhiều loại multipart. Ví dụ email có plain text, HTML, ảnh inline và PDF có thể có cấu trúc lồng nhau:

```text
multipart/mixed
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html (references cid:brand-logo)
    └── image/png (Content-ID: <brand-logo>)
└── application/pdf (attachment)
```

Cấu trúc cụ thể phụ thuộc cách tạo MIME và chế độ của `MimeMessageHelper`. Không tự ghép boundary bằng chuỗi; hãy để Jakarta Mail và Spring xây dựng MIME parts.

## 3. Tạo cả plain text và HTML bằng MimeMessageHelper

### 3.1. Dependency và cấu hình cơ bản

Với Spring Boot, có thể dùng starter mail:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Ví dụ cấu hình SMTP qua `application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Credential cần được cấp từ môi trường hoặc secret store; không commit mật khẩu thật vào repository. Cổng và cơ chế TLS phải khớp với hướng dẫn của SMTP provider.

### 3.2. Dùng overload setText(plainText, htmlText)

Đây là phần quan trọng nhất:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng ORD-2026-001");

String plainText = """
    Xin chào An,

    Đơn hàng ORD-2026-001 của bạn đã được xác nhận.

    Tổng tiền: 450.000 ₫
    Dự kiến giao: 15/11/2026

    Xem chi tiết đơn hàng:
    https://shop.example.com/orders/ORD-2026-001

    Nếu cần hỗ trợ, hãy trả lời email này.
    """;

String htmlText = """
    <!DOCTYPE html>
    <html lang="vi">
      <body>
        <h1>Xin chào An!</h1>
        <p>Đơn hàng <strong>ORD-2026-001</strong>
           của bạn đã được xác nhận.</p>
        <p><strong>Tổng tiền:</strong> 450.000 ₫</p>
        <p><strong>Dự kiến giao:</strong> 15/11/2026</p>
        <p>
          <a href="https://shop.example.com/orders/ORD-2026-001">
            Xem chi tiết đơn hàng
          </a>
        </p>
        <p>Nếu cần hỗ trợ, hãy trả lời email này.</p>
      </body>
    </html>
    """;

// Tạo hai phiên bản thay thế của cùng nội dung.
helper.setText(plainText, htmlText);

mailSender.send(message);
```

Overload này cho phép Spring tạo nội dung plain và HTML trong cấu trúc multipart phù hợp. Tham số thứ nhất là bản plain text; tham số thứ hai là HTML.

**Không dùng `setText(htmlText, true)` nếu mục tiêu là hỗ trợ client chỉ đọc plain text.** Cách đó chỉ khai báo nội dung HTML; nó không tự sinh một bản plain text đầy đủ.

### 3.3. Không gửi plain text và HTML thành hai email riêng

Không cần gửi hai thông điệp SMTP riêng, một thông điệp text và một thông điệp HTML. Làm như vậy có thể khiến người nhận nhận hai email giống nhau, gây trùng thông báo và làm phức tạp việc theo dõi.

Hãy gửi **một MimeMessage** có nhiều MIME part thay thế. Mail client lựa chọn part thích hợp.

## 4. Plain text phải chứa cùng thông tin quan trọng

Một bản plain text tốt cần giữ các thông tin nghiệp vụ có trong HTML:

- Lời chào và ngữ cảnh.
- Mã giao dịch/đơn hàng hoặc định danh cần thiết.
- Trạng thái và thông tin quan trọng.
- Số tiền, ngày giờ và múi giờ khi có.
- Đường dẫn hành động đầy đủ.
- Thời hạn hoặc điều kiện áp dụng.
- Kênh hỗ trợ và cách liên hệ.
- Thông tin unsubscribe khi email marketing yêu cầu.

Ví dụ HTML có một nút:

```html
<a href="https://accounts.example.com/verify?token=abc123">
  Xác minh tài khoản
</a>
```

Plain text cần thể hiện cả nhãn và URL:

```text
Xác minh tài khoản:
https://accounts.example.com/verify?token=abc123
```

Nếu plain text chỉ ghi “Nhấn nút màu xanh để xác minh”, người dùng không có nút để nhấn. Nếu chỉ ghi “Xác minh tài khoản” mà không có URL, hành động có thể không thực hiện được.

Với URL có token, không log hoặc chia sẻ giá trị thật. Trong email thực tế, token phải được tạo đúng quyền và thời hạn, dùng HTTPS và có chính sách bảo vệ phù hợp.

### 4.1. Tránh nội dung mâu thuẫn

HTML có thể ghi tổng tiền 450.000 ₫ nhưng plain text lại ghi 405.000 ₫ nếu hai bản được dựng từ hai nguồn dữ liệu khác nhau. Đây là lỗi nội dung nghiêm trọng.

Hãy tạo cả hai phiên bản từ **cùng một view model đã chuẩn hóa**:

```text
Order data
    |
    v
Validated email view model
    |
    +--> Render plain text
    |
    +--> Render HTML
    |
    v
MimeMessageHelper.setText(plain, html)
```

Không tính lại giá, trạng thái, ngày giao hoặc link ở hai nơi độc lập. Những giá trị dùng chung nên được chuẩn bị một lần rồi truyền cho cả hai template.

## 5. Tổ chức renderer riêng cho plain text và HTML

Với email phức tạp, nên tách việc tạo nội dung khỏi việc gửi thư. Một renderer có thể trả về hai chuỗi:

```java
package com.example.mail;

public record RenderedEmail(
    String plainText,
    String htmlText
) {}
```

Một renderer dùng chung dữ liệu nghiệp vụ:

```java
package com.example.mail;

import java.text.NumberFormat;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

import org.springframework.stereotype.Component;

@Component
public class OrderEmailRenderer {

    public RenderedEmail render(OrderMailData data) {
        String customerName =
            data.customerName() == null
                || data.customerName().isBlank()
                ? "bạn"
                : data.customerName().strip();

        NumberFormat currency =
            NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("vi-VN")
            );

        String amount = currency.format(data.total());

        String deliveryDate = DateTimeFormatter
            .ofPattern("dd/MM/yyyy HH:mm", Locale.forLanguageTag("vi-VN"))
            .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .format(data.estimatedDelivery());

        String orderUrl =
            "https://shop.example.com/orders/" + data.orderId();

        String plain = """
            Xin chào %s,

            Đơn hàng %s của bạn đã được xác nhận.

            Tổng tiền: %s
            Dự kiến giao: %s

            Xem chi tiết đơn hàng:
            %s

            Nếu cần hỗ trợ, hãy trả lời email này.
            """.formatted(
                customerName,
                data.orderId(),
                amount,
                deliveryDate,
                orderUrl
            );

        // Dùng template engine để escape dữ liệu trong HTML.
        String html = renderHtml(
            customerName,
            data.orderId(),
            amount,
            deliveryDate,
            orderUrl
        );

        return new RenderedEmail(plain, html);
    }

    private String renderHtml(
            String customerName,
            String orderId,
            String amount,
            String deliveryDate,
            String orderUrl) {
        // Minh họa: trong ứng dụng thực tế, dùng Thymeleaf/FreeMarker
        // để escape dữ liệu text và thuộc tính HTML.
        throw new UnsupportedOperationException(
            "Hãy triển khai bằng template engine"
        );
    }
}
```

`OrderMailData` là model nghiệp vụ do ứng dụng định nghĩa. Ví dụ này tập trung vào việc chuẩn bị dữ liệu chung; phần HTML được giao cho template engine thay vì nối chuỗi với dữ liệu người dùng.

### 5.1. Vì sao nên có template plain riêng?

Một bản text thuần không phải lúc nào cũng là HTML bị bỏ thẻ. Nó có thể cần cách trình bày khác:
- Dùng tiêu đề và dấu phân cách.
- Đặt URL ở dòng riêng.
- Biểu diễn bảng thành các dòng có nhãn.
- Thay ảnh bằng mô tả.
- Rút gọn các chi tiết trang trí.
- Sắp xếp nội dung sao cho đọc tuyến tính.

Ví dụ bảng HTML:

```html
<table>
  <tr><th>Sản phẩm</th><th>Số lượng</th><th>Giá</th></tr>
  <tr><td>Cà phê</td><td>2</td><td>180.000 ₫</td></tr>
  <tr><td>Trà</td><td>1</td><td>90.000 ₫</td></tr>
</table>
```

Plain text có thể biểu diễn:

```text
Chi tiết đơn hàng
-----------------
- Cà phê
  Số lượng: 2
  Giá: 180.000 ₫

- Trà
  Số lượng: 1
  Giá: 90.000 ₫

Tổng tiền: 450.000 ₫
```

Nếu chỉ xóa tag HTML, nội dung có thể thành một chuỗi khó đọc như “Sản phẩmSố lượngGiáCà phê2180.000 ₫”. Hãy thiết kế text layout có chủ đích.

## 6. Dùng Thymeleaf cho cả HTML và plain text

Có thể giữ hai template trong resources:

```text
src/main/resources/templates/mail/
├── order-confirmation.html
└── order-confirmation.txt
```

### 6.1. HTML template

`order-confirmation.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Xin chào, <span th:text="${customerName}">bạn</span>!</h1>

  <p>
    Đơn hàng <strong th:text="${orderId}">ORD-001</strong>
    đã được xác nhận.
  </p>

  <p>
    <strong>Tổng tiền:</strong>
    <span th:text="${totalText}">0 ₫</span>
  </p>

  <p>
    <strong>Dự kiến giao:</strong>
    <span th:text="${deliveryText}">15/11/2026</span>
  </p>

  <p>
    <a th:href="${orderUrl}">Xem chi tiết đơn hàng</a>
  </p>
</body>
</html>
```

### 6.2. Plain-text template

`order-confirmation.txt`:

```text
[# th:mode="TEXT"]
Xin chào, [(${customerName})]!

Đơn hàng [(${orderId})] đã được xác nhận.

Tổng tiền: [(${totalText})]
Dự kiến giao: [(${deliveryText})]

Xem chi tiết đơn hàng:
[(${orderUrl})]
[/]
```

Với Thymeleaf, cú pháp inline text mode cần được khai báo đúng. Cần dùng escaping phù hợp với phiên bản/cấu hình Thymeleaf đang triển khai; không bật chế độ unescaped cho dữ liệu không tin cậy. Nếu template engine hoặc dialect không được cấu hình cho text mode, hãy tạo plain text bằng renderer Java hoặc một template engine text được hỗ trợ.

### 6.3. Render hai template với cùng context

Ví dụ:

```java
Context context = new Context(Locale.forLanguageTag("vi"));
context.setVariable("customerName", customerName);
context.setVariable("orderId", orderId);
context.setVariable("totalText", totalText);
context.setVariable("deliveryText", deliveryText);
context.setVariable("orderUrl", orderUrl);

String html = templateEngine.process(
    "mail/order-confirmation.html", context
);

String plain = templateEngine.process(
    "mail/order-confirmation.txt", context
);

RenderedEmail rendered = new RenderedEmail(plain, html);
```

Đường dẫn template và cấu hình resolver phải phù hợp với dự án. Điểm chính là **cùng một context** được sử dụng cho hai template.

## 7. Gửi email HTML và plain text bằng Spring Mail

Một service gửi có thể nhận kết quả render:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;
    private final OrderEmailRenderer renderer;

    public OrderMailService(
            JavaMailSender mailSender,
            OrderEmailRenderer renderer) {
        this.mailSender = mailSender;
        this.renderer = renderer;
    }

    public void send(
            String recipient,
            OrderMailData data) throws MessagingException {

        RenderedEmail rendered = renderer.render(data);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + data.orderId());

        helper.setText(
            rendered.plainText(),
            rendered.htmlText()
        );

        mailSender.send(message);
    }
}
```

Khi mail client chỉ đọc plain text, nó sẽ dùng phần `text/plain`. Khi client hỗ trợ HTML và lựa chọn phiên bản đó, nó dùng phần `text/html`.

Không dùng `SimpleMailMessage` cho ví dụ này vì cần MIME multipart/alternative. `SimpleMailMessage` phù hợp với email text thuần đơn giản, không phải thông điệp có hai representation trong cùng một MIME message.

## 8. Plain text với ảnh inline và attachment

### 8.1. Ảnh inline không có mặt trong plain text

HTML có thể dùng:

```html
<img src="cid:brand-logo" alt="Logo thương hiệu">
```

Plain text không thể hiển thị ảnh qua CID. Hãy thay ảnh bằng mô tả hoặc tên tổ chức:

```text
[Logo thương hiệu]

Thông báo từ Example Store
```

Không cần đưa chuỗi `cid:brand-logo` vào plain text vì đó là tham chiếu MIME nội bộ, không phải URL người dùng có thể mở.

### 8.2. Kết hợp setText và addInline

Khi có HTML, plain text và ảnh inline:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_RELATED,
    "UTF-8"
);

helper.setFrom("news@example.com");
helper.setTo(recipient);
helper.setSubject("Bản tin tháng");

helper.setText(plainText, htmlText);

// Nội dung body được thiết lập trước inline resource.
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

mailSender.send(message);
```

Trong plain text, nội dung chính phải đọc được mà không cần ảnh. `addInline` chỉ phục vụ HTML/MIME part có CID; nó không tạo một hình ảnh cho text-only client.

### 8.3. Kết hợp attachment độc lập

Nếu email còn có PDF:

```java
helper.setText(plainText, htmlText);

helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

helper.addAttachment(
    "invoice.pdf",
    new ClassPathResource("mail/invoice.pdf"),
    "application/pdf"
);
```

Plain text nên nói rõ file nào được đính kèm và mục đích của nó:

```text
Hóa đơn PDF được đính kèm trong email này.
Tên tệp: invoice.pdf
```

Người dùng chỉ đọc plain text vẫn có thể biết có tài liệu đi kèm, dù việc tải file còn phụ thuộc client và chính sách của họ.

## 9. Thiết kế plain text cho các loại email khác nhau

### 9.1. Email xác minh tài khoản

Plain text cần:
- lý do người nhận nhận email;
- tên dịch vụ;
- URL xác minh đầy đủ;
- thời hạn link;
- hướng xử lý nếu người nhận không yêu cầu.

Ví dụ:

```text
Xin chào An,

Bạn vừa yêu cầu tạo tài khoản tại Example.

Để xác minh địa chỉ email, mở liên kết sau:
https://accounts.example.com/verify?token=...

Liên kết có hiệu lực trong 30 phút.

Nếu bạn không yêu cầu tạo tài khoản, hãy bỏ qua email này.
```

Không chỉ ghi “Bấm nút bên dưới” vì bản text không có nút.

### 9.2. Email đặt lại mật khẩu

Plain text cần:
- nêu rõ đây là yêu cầu đặt lại mật khẩu;
- URL HTTPS đầy đủ;
- thời hạn;
- cảnh báo không chia sẻ link;
- cách xử lý nếu không phải người yêu cầu.

Không đưa mật khẩu mới hoặc secret vào email. Token trong link phải có thời hạn và phạm vi sử dụng phù hợp.

### 9.3. Email hóa đơn

Plain text nên giữ:
- mã hóa đơn;
- ngày lập;
- tổng tiền và currency;
- trạng thái thanh toán;
- link xem hóa đơn;
- tên file PDF nếu đính kèm.

Không để những thông tin tài chính chỉ nằm trong một ảnh hoặc bảng HTML.

### 9.4. Email marketing

Plain text cần:
- tên thương hiệu/người gửi;
- nội dung ưu đãi và điều kiện quan trọng;
- URL đích rõ ràng;
- thông tin liên hệ;
- hướng dẫn hủy đăng ký khi bắt buộc.

Đừng chỉ ghi một link rút gọn không thể nhận biết hoặc bỏ mất điều kiện ưu đãi trong bản text. Các header unsubscribe ở tầng email cũng cần được cấu hình theo yêu cầu của hệ thống; đoạn plain text không thay thế header hoặc endpoint unsubscribe.

### 9.5. Email cảnh báo hệ thống

Plain text nên trình bày:
- hệ thống hoặc dịch vụ gặp sự kiện gì;
- thời điểm và timezone;
- mức độ/ảnh hưởng;
- mã sự kiện để tra cứu;
- link dashboard/runbook nếu người nhận được phép truy cập;
- hành động tiếp theo.

Nếu có biểu đồ trong HTML, text nên tóm tắt số liệu chính thay vì chỉ nói “xem biểu đồ”.

## 10. Tạo plain text từ HTML có nên không?

Một cách làm là tự động loại bỏ HTML tag để tạo text. Nó có thể hữu ích với template đơn giản, nhưng **không phải giải pháp mặc định tốt nhất** cho email nghiệp vụ.

Ví dụ HTML:

```html
<p>Đơn hàng <strong>ORD-001</strong> đã xác nhận.</p>
<p><a href="https://shop.example.com/orders/ORD-001">Xem đơn hàng</a></p>
```

Nếu chỉ strip tag, kết quả có thể là:

```text
Đơn hàng ORD-001 đã xác nhận.
Xem đơn hàng
```

URL bị mất, nên người đọc không thực hiện được hành động. Một bộ chuyển đổi tốt phải xử lý:
- link: giữ cả nhãn và URL;
- bảng: giữ thứ tự cột và hàng;
- heading: tạo khoảng cách/tiêu đề;
- danh sách: dùng bullet/number;
- ảnh: lấy alt text hoặc mô tả;
- nội dung ẩn/điều kiện: không đưa nội dung không hiển thị vào bản text;
- whitespace và paragraph boundary.

Với email có thông tin quan trọng, **tạo plain template riêng** thường rõ ràng và dễ kiểm soát hơn. Chuyển đổi HTML sang text có thể là fallback hoặc tiện ích, nhưng cần kiểm thử trên các template thực tế.

## 11. Kiểm tra plain text và HTML có nhất quán không

Hai bản không cần giống hệt nhau về bố cục, nhưng phải nhất quán về sự kiện và thông tin nghiệp vụ.

| Thông tin | Plain text | HTML |
|---|---|---|
| Mã đơn hàng | Có | Có |
| Trạng thái | Có | Có |
| Tổng tiền | Có | Có |
| Ngày giao | Có | Có |
| URL hành động | Có URL đầy đủ | Có link tới cùng đích |
| Điều kiện/thời hạn | Có | Có |
| Hỗ trợ/liên hệ | Có | Có |
| Unsubscribe (nếu áp dụng) | Có hướng dẫn | Có link/hướng dẫn |

Nên tạo dữ liệu dùng chung một lần:
- ID đơn hàng;
- giá trị tiền đã định dạng;
- ngày giờ đã chuyển timezone;
- URL đã được xây và validate;
- tên hiển thị đã chuẩn hóa.

Sau đó render cả hai bản. Không nên tự tính tổng tiền riêng trong hai template hoặc tạo hai URL bằng hai logic khác nhau.

## 12. Kiểm tra MIME message trong test

Không chỉ test rằng `send(...)` được gọi. Hãy xác nhận MIME message thực sự chứa hai part.

Với `JavaMailSender` mock, có thể lấy message được truyền vào `send`:

```java
ArgumentCaptor<MimeMessage> captor =
    ArgumentCaptor.forClass(MimeMessage.class);

verify(mailSender).send(captor.capture());

MimeMessage sent = captor.getValue();
sent.saveChanges();
```

Sau đó duyệt MIME tree để tìm `text/plain` và `text/html`. Với cấu trúc multipart có lồng related/mixed, nên viết hàm đệ quy duyệt từng `Multipart` thay vì giả định cả hai part luôn là hai phần tử trực tiếp ở cấp đầu.

Pseudo-code minh họa:

```java
void collectTextParts(
        jakarta.mail.Part part,
        List<String> plainParts,
        List<String> htmlParts) throws Exception {

    if (part.isMimeType("text/plain")) {
        plainParts.add((String) part.getContent());
        return;
    }

    if (part.isMimeType("text/html")) {
        htmlParts.add((String) part.getContent());
        return;
    }

    Object content = part.getContent();
    if (content instanceof jakarta.mail.Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            collectTextParts(
                multipart.getBodyPart(i),
                plainParts,
                htmlParts
            );
        }
    }
}
```

Đây là helper kiểm tra trong test, không phải code production. MIME part có thể có content wrapper hoặc kiểu dữ liệu khác tùy provider; test nên xử lý đúng các trường hợp ứng dụng tạo ra.

### 12.1. Các assertions nên có

- Có ít nhất một part `text/plain`.
- Có part `text/html` khi template HTML được bật.
- Plain text không rỗng.
- Plain text có mã nghiệp vụ và CTA/link cần thiết.
- HTML và plain text có cùng mã giao dịch, số tiền, trạng thái.
- URL trong plain text và HTML có cùng đích.
- Plain text không chứa markup HTML thô ngoài ý muốn.
- Không có placeholder template chưa được thay.
- Charset phù hợp, thường là UTF-8.
- Khi có attachment, vẫn tồn tại cả hai body representations.
- Khi có inline image, CID part chỉ phục vụ HTML và không thay thế nội dung plain.

## 13. Ví dụ kiểm thử renderer với JUnit

Giả sử `OrderEmailRenderer` trả về `RenderedEmail`. Một test có thể xác nhận cả hai phiên bản:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class OrderEmailRendererTest {

    private final OrderEmailRenderer renderer =
        new OrderEmailRenderer(/* dependencies */);

    @Test
    void rendersEquivalentPlainAndHtmlContent() {
        OrderMailData data = sampleOrder();

        RenderedEmail result = renderer.render(data);

        assertThat(result.plainText())
            .contains(data.orderId())
            .contains("450.000")
            .contains("Xem chi tiết đơn hàng")
            .contains("https://shop.example.com/orders/");

        assertThat(result.htmlText())
            .contains(data.orderId())
            .contains("450.000")
            .contains("Xem chi tiết đơn hàng");
    }
}
```

`sampleOrder()` là fixture do test định nghĩa. Trong dự án thật, inject renderer và các dependency cần thiết thay vì dùng constructor minh họa nếu renderer cần template engine.

### 13.1. Test URL xuất hiện ở plain text

```java
@Test
void plainTextContainsUsableActionUrl() {
    RenderedEmail result = renderer.render(sampleOrder());

    assertThat(result.plainText())
        .contains("https://shop.example.com/orders/ORD-2026-001");
}
```

Test này bảo đảm CTA không chỉ tồn tại dưới dạng một thẻ anchor trong HTML.

### 13.2. Test plain text không phụ thuộc ảnh

```java
@Test
void plainTextDoesNotRequireInlineCid() {
    RenderedEmail result = renderer.render(sampleOrder());

    assertThat(result.plainText())
        .doesNotContain("cid:");
    assertThat(result.plainText())
        .contains("Example Store");
}
```

Nếu template HTML có logo, bản text nên có tên thương hiệu hoặc mô tả phù hợp, không phải CID nội bộ.

## 14. Encoding và ký tự đặc biệt trong plain text

Plain text vẫn cần encoding đúng. Dùng `UTF-8` cho `MimeMessageHelper` và bảo đảm nội dung được tạo từ Java `String` đúng.

Ví dụ nội dung:

```text
Xin chào Nguyễn Thị Ánh,

Đơn hàng của bạn đã được xác nhận.
Tổng tiền: 1.250.000 ₫
Địa chỉ: Đắk Lắk
```

Khi đọc MIME source, kiểm tra:
- `Content-Type: text/plain; charset=UTF-8` hoặc charset phù hợp;
- `Content-Transfer-Encoding` như quoted-printable hoặc base64;
- nội dung sau decode giữ nguyên tiếng Việt và ký tự tiền tệ.

Đừng tự mã hóa chuỗi sang Base64 rồi đặt vào body text. Thư viện MIME sẽ xử lý content-transfer-encoding. Việc encode thủ công thường làm người nhận nhìn thấy chuỗi mã hóa thay vì nội dung.

### 14.1. Line ending và xuống dòng

Plain text thường dùng dòng mới để phân chia đoạn. Java text block dùng line break theo source; Jakarta Mail sẽ chuẩn hóa khi tạo MIME theo quy tắc giao thức. Không cần tự chèn boundary MIME hoặc tự tạo header.

Hãy kiểm tra:
- giữa các đoạn có dòng trống;
- URL không bị ngắt ở vị trí làm hỏng link;
- danh sách có bullet/number;
- không có hàng trăm dòng trắng do dữ liệu rỗng;
- độ dài dòng hợp lý với các client text-only cũ nếu nhóm người nhận có dùng chúng.

## 15. Accessibility và trải nghiệm đọc tuyến tính

Plain text hỗ trợ người dùng đọc email theo trình tự. Ngay cả HTML client, nội dung plain vẫn có ích cho các hệ thống chỉ xử lý text.

Nguyên tắc:
- Viết tiêu đề email cụ thể.
- Đặt thông tin quan trọng ở đầu.
- Dùng nhãn trước giá trị, ví dụ `Mã đơn hàng: ORD-001`.
- Không truyền đạt trạng thái chỉ bằng màu sắc hoặc icon.
- Dùng URL có ngữ cảnh, không chỉ ghi “click here”.
- Với ảnh có thông tin, đưa thông tin đó thành text.
- Với bảng, chuyển thành các nhóm dòng có nhãn.
- Dùng ngôn ngữ rõ ràng, câu ngắn và đoạn văn có mục đích.

Ví dụ, thay vì:

```text
🟢
450.000
15/11
```

hãy viết:

```text
Trạng thái: Đã xác nhận
Tổng tiền: 450.000 ₫
Dự kiến giao: 15/11/2026
```

Màu sắc hoặc emoji có thể là trang trí, nhưng không nên là phương tiện duy nhất truyền đạt ý nghĩa.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client text-only nhận email trống | Chỉ gửi `text/html` | Dùng `setText(plainText, htmlText)`. |
| Plain text chỉ ghi “Bật HTML để xem” | Không thiết kế nội dung text riêng | Viết plain version có đủ thông tin và CTA. |
| Link không thể mở | HTML có anchor nhưng plain chỉ có nhãn | Đưa URL đầy đủ vào plain text. |
| Nội dung hai bản khác nhau | Hai template tự tính dữ liệu độc lập | Dùng chung view model đã chuẩn hóa. |
| Tiếng Việt lỗi | Charset không thống nhất hoặc encode thủ công | Dùng UTF-8 và để MIME library encode. |
| Bảng thành một chuỗi khó đọc | Strip HTML tag đơn giản | Tạo plain template có cấu trúc riêng. |
| Ảnh không có trong plain | Mong đợi CID hiển thị trong text | Thay bằng mô tả/alt text hoặc tên thương hiệu. |
| Attachment không được nhắc tới | Plain template bỏ qua file đính kèm | Thêm tên và mục đích tài liệu. |
| Email nhận hai lần | Gửi hai message riêng cho HTML và text | Dùng một multipart/alternative message. |
| Test chỉ xác minh send được gọi | Không kiểm tra MIME body | Duyệt MIME tree và assert cả hai part. |
| URL/token khác nhau giữa hai bản | Tạo link ở hai nơi riêng | Xây URL một lần và dùng chung cho hai renderer. |
| Plain text lộ markup | Dùng nhầm HTML string làm bản text | Render text template riêng hoặc chuyển đổi có hiểu biết. |

## 17. Bài tập thực hành

### Bài 1 — Thêm plain text vào email hiện tại

Cho một service đang dùng:

```java
helper.setText(htmlText, true);
```

Hãy tạo thêm `plainText` và đổi sang overload hai tham số. Nêu thông tin nào phải có trong bản text.

### Bài 2 — Viết bản plain cho CTA

HTML có nút “Đặt lại mật khẩu”. Hãy viết plain text chứa lý do gửi, URL HTTPS đầy đủ, thời hạn và cách xử lý nếu người nhận không yêu cầu.

### Bài 3 — Bảng HTML sang text

Một hóa đơn có bảng sản phẩm gồm tên, số lượng, đơn giá và thành tiền. Hãy chuyển thành từng nhóm dòng có nhãn để người đọc không cần bảng HTML.

### Bài 4 — So sánh nội dung hai bản

Dùng cùng một view model để render HTML/plain. Viết test khẳng định mã đơn hàng, tổng tiền, ngày giao và URL xuất hiện ở cả hai bản.

### Bài 5 — MIME tree

Tạo email có plain text, HTML và PDF attachment. Kiểm tra raw MIME để xác nhận cả `text/plain`, `text/html` và `application/pdf` tồn tại trong cấu trúc multipart.

### Bài 6 — Inline image

HTML có logo CID. Viết plain text không phụ thuộc CID và có tên thương hiệu. Xác nhận ảnh chỉ được thêm vào MIME cho HTML.

### Bài 7 — Unicode

Gửi test inbox nội dung tiếng Việt có dấu, ký hiệu ₫ và emoji. Kiểm tra `charset=UTF-8` và đọc nội dung trong client text-only.

### Bài 8 — Không tạo hai email

Một developer gửi một email HTML và một email plain cho cùng recipient. Hãy giải thích vấn đề trùng thư và thay bằng một `multipart/alternative` message.

## 18. Tổng kết

Để xử lý các client chỉ đọc plain text, hãy gửi **một MIME message có cả `text/plain` và `text/html`**. Trong Spring Framework Mail, dùng `MimeMessageHelper.setText(plainText, htmlText)` với helper ở chế độ multipart. Plain text cần chứa đầy đủ thông tin nghiệp vụ, CTA và URL có thể sử dụng, đồng thời giữ nội dung nhất quán với HTML.

Tạo hai bản từ cùng một view model hoặc dữ liệu đã chuẩn hóa; không chỉ xóa tag HTML để tạo text một cách máy móc. Khi có ảnh inline, thay ảnh bằng mô tả trong bản text; khi có attachment, nêu rõ tên và mục đích file. Cuối cùng, kiểm tra MIME tree để xác nhận cả hai representation tồn tại, rồi thử trên client text-only hoặc test inbox. **Một email tốt vẫn truyền đạt trọn vẹn thông điệp ngay cả khi phần HTML không được hiển thị.**
