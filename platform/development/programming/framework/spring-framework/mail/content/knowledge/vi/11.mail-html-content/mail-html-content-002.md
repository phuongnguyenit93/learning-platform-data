# Mẫu HTML và dữ liệu được chèn từ ứng dụng

Trong **Spring Framework Mail**, một email có thể chứa nội dung HTML để trình bày thông báo đơn hàng, xác nhận đăng ký, hóa đơn hoặc cập nhật dịch vụ. Khác với thư văn bản thuần, nội dung HTML thường có bố cục, màu sắc, nút liên kết, bảng thông tin và hình ảnh. Tuy nhiên, việc viết một chuỗi HTML cố định trong Java không phù hợp khi mỗi người nhận có **tên, mã đơn hàng, số tiền và liên kết khác nhau**.

Giải pháp phổ biến là tách **mẫu HTML (template)** khỏi **dữ liệu nghiệp vụ (data)**. Ứng dụng thu thập và kiểm tra dữ liệu, một template engine tạo ra HTML hoàn chỉnh, rồi `JavaMailSender` gửi HTML đó bên trong một thông điệp MIME.

~~~text
Order / Account / Notification service
              |
              v
  Dữ liệu dành cho email (DTO)
              |
              v
  Template engine + HTML template
              |
              v
     Chuỗi HTML đã render
              |
              v
   MimeMessage + MimeMessageHelper
              |
              v
    JavaMailSender -> SMTP provider
~~~

Trong bài này, ta sử dụng **Thymeleaf** làm ví dụ về template engine trong Spring Boot. Đây không phải lựa chọn bắt buộc: FreeMarker, Mustache hoặc một công cụ dựng HTML khác cũng có thể dùng nếu ứng dụng tích hợp phù hợp. Phần quan trọng là hiểu ranh giới giữa **nội dung mẫu**, **dữ liệu được chèn vào mẫu** và **cơ chế gửi thư**.

## 1. Vì sao nên tách HTML khỏi Java?

Một phương thức gửi mail có thể bắt đầu bằng cách nối chuỗi:

~~~java
String html = "<html><body>"
        + "<h1>Xin chào " + customerName + "</h1>"
        + "<p>Đơn hàng " + orderId + " đã được xác nhận.</p>"
        + "</body></html>";
~~~

Cách này có vẻ nhanh nhưng gây nhiều vấn đề:

- **Khó bảo trì:** sửa bố cục HTML/CSS đòi hỏi sửa Java và dễ bỏ sót dấu nháy, thẻ đóng hoặc ký tự escape.
- **Khó tái sử dụng:** email cho nhiều ngôn ngữ, thương hiệu hoặc loại giao dịch thường có các đoạn giao diện chung.
- **Khó kiểm tra:** phần trình bày xen với logic nghiệp vụ, khiến việc xem trước một email khó khăn.
- **Rủi ro bảo mật:** dữ liệu người dùng được nối thẳng vào HTML có thể chứa dấu `<`, `>`, dấu nháy hoặc markup không được phép.
- **Khó cung cấp bản text:** email HTML vẫn nên có một phiên bản plain text thay thế cho email client không hiển thị HTML.

Thay vì tạo HTML bằng cách ghép nhiều chuỗi, ứng dụng có thể dùng template:

~~~html
<h1>Xin chào <span th:text="${customerName}">Khách hàng</span></h1>
<p>
  Đơn hàng
  <strong th:text="${orderId}">A123</strong>
  đã được xác nhận.
</p>
~~~

Ở đây:

- **HTML và bố cục** do file template định nghĩa.
- **`customerName` và `orderId`** là dữ liệu ứng dụng truyền vào lúc render.
- **`th:text`** cho Thymeleaf thay phần text của element bằng giá trị tương ứng, đồng thời escape ký tự đặc biệt phù hợp với ngữ cảnh HTML.
- **Giá trị mặc định** giữa các thẻ giúp người viết template nhận biết vị trí dữ liệu, và sẽ bị thay thế khi template được xử lý.

Template engine tạo một chuỗi HTML hoàn chỉnh; **nó không gửi email**. Việc gửi được thực hiện riêng bởi Spring Mail.

## 2. Ba lớp trách nhiệm cần phân biệt

| Lớp | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Dữ liệu nghiệp vụ** | Nội dung nào cần truyền tải? | Khách hàng, đơn hàng, số tiền, trạng thái |
| **Trình bày/template** | Thể hiện thông tin bằng HTML ra sao? | File `order-confirmation.html`, CSS, logo, bảng |
| **Gửi email** | Chuyển thông điệp tới SMTP provider thế nào? | `JavaMailSender`, `MimeMessageHelper`, cấu hình `spring.mail.*` |

Một ranh giới hợp lý:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["OrderMailData"]
    B --> C["Thymeleaf Renderer"]
    D["order-confirmation.html"] --> C
    C --> E["Rendered HTML"]
    B --> F["Plain-text Renderer"]
    E --> G["MimeMessageHelper"]
    F --> G
    G --> H["JavaMailSender"]
    H --> I["SMTP provider"]
~~~

**OrderService** không cần biết nội dung HTML được chia thành bảng mấy cột. **Template engine** không cần biết tài khoản SMTP, mật khẩu hay retry policy. **Mail sender** không nên truy vấn đơn hàng hoặc chỉnh lại dữ liệu theo logic nghiệp vụ. Cách tách này giúp thay đổi bố cục email mà ít ảnh hưởng tới xử lý đơn hàng.

### 2.1. Phần nào là dữ liệu động?

Giả sử mẫu xác nhận đơn hàng cần các thành phần:

| Thành phần trong email | Nguồn dữ liệu | Gợi ý xử lý |
| --- | --- | --- |
| Tên khách hàng | Hồ sơ người dùng | Escape như văn bản khi chèn vào HTML |
| Mã đơn hàng | Order service | Chọn giá trị đã kiểm tra và không chứa thông tin bí mật |
| Danh sách sản phẩm | Chi tiết đơn hàng | Chuyển thành DTO phù hợp để lặp trong template |
| Tổng tiền | Logic tính tiền của ứng dụng | Format theo tiền tệ/locale **trước khi** đưa vào template hoặc dùng formatter rõ ràng |
| Đường dẫn xem đơn | Ứng dụng sinh link từ domain tin cậy | Kiểm tra scheme/host và tham số; không tin URL tùy ý |
| Logo và màu sắc | Bộ nhận diện thương hiệu | Template/resource tĩnh được kiểm soát |
| Địa chỉ hỗ trợ | Cấu hình ứng dụng | Không cần đưa SMTP password vào model |

Một biến template tốt đại diện cho **ý nghĩa** như `customerName`, `orderLines` hay `orderUrl`, không nên mang cấu trúc HTML do client cung cấp như `customerNameHtml`.

## 3. Cần những dependency nào trong Spring Boot?

Nếu dùng Thymeleaf và Spring Mail, trong Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Trong Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
~~~

Các ví dụ giả định dự án đã có Spring Boot parent/BOM hoặc cách quản lý version tương ứng. Đừng tự pin phiên bản khác nhau cho từng thư viện chỉ để ghép ví dụ nếu chưa xem phiên bản Spring Boot mà dự án đang dùng.

**Vai trò:**

- `spring-boot-starter-mail`: Spring Mail, Jakarta Mail và những dependency cần để tạo/gửi thông điệp SMTP.
- `spring-boot-starter-thymeleaf`: template engine cùng phần tích hợp Spring Boot để nạp và xử lý mẫu.

**Không bắt buộc thêm web starter** chỉ để render HTML cho email. Worker gửi mail trong background cũng có thể dùng template engine mà không có controller HTTP. Nếu project đã dùng Thymeleaf cho trang web, có thể tái sử dụng engine và hạ tầng templates trong chừng mực cách tổ chức template và context phù hợp.

## 4. Tổ chức các file template

Với cấu hình mặc định thường gặp của Spring Boot + Thymeleaf, template được tìm trong `classpath:/templates/` với hậu tố `.html`:

~~~text
src/
  main/
    java/
      com/example/mail/
        application/
          OrderMailService.java
          OrderMailData.java
        config/
          MailConfiguration.java
    resources/
      templates/
        mail/
          order-confirmation.html
          order-confirmation.txt
          account-welcome.html
      application.yml
~~~

Trong ví dụ, `templates/mail/order-confirmation.html` có thể được render bằng tên logic `"mail/order-confirmation"`. File `order-confirmation.txt` là minh họa nơi lưu template plain text nếu có cấu hình resolver dành cho text; **Thymeleaf auto-configuration mặc định dành cho HTML không có nghĩa nó sẽ tự render mọi file `.txt`**. Có thể dùng renderer riêng hoặc khai báo resolver có template mode TEXT.

Lợi ích của thư mục `mail/`:

- Tách mẫu email khỏi mẫu trang web.
- Đặt tên theo **hành động nghiệp vụ** chứ không theo một người nhận cụ thể.
- Dễ bổ sung locale, phiên bản và thành phần dùng chung khi hệ thống phát triển.
- Cho phép preview email trong môi trường phát triển với dữ liệu mẫu không nhạy cảm.

### 4.1. Template có phải do người dùng nhập không?

Trong kiến trúc thường gặp, **template là tài nguyên tin cậy do đội phát triển/quản trị nội dung kiểm soát**, còn biến truyền vào là dữ liệu nghiệp vụ có thể chứa input không tin cậy. Không nên cho người dùng công khai tự gửi đoạn HTML/Thymeleaf expression rồi yêu cầu server render như template của hệ thống. Template engine có ngôn ngữ biểu thức và có thể có nhiều quyền truy cập hơn một trình hiển thị text thuần.

Nếu sản phẩm cho phép người dùng quản lý template riêng, cần mô hình phân quyền, giới hạn biểu thức, validation, sandbox hoặc cơ chế render khác được thiết kế riêng; không mặc định đưa chuỗi template không tin cậy vào `SpringTemplateEngine.process(...)`.

## 5. Tạo một mẫu email HTML

Ví dụ `src/main/resources/templates/mail/order-confirmation.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xác nhận đơn hàng</title>
</head>
<body style="margin:0; padding:24px; background:#f4f6f8; font-family:Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0"
         style="max-width:600px; width:100%; margin:auto; background:#ffffff;">
    <tr>
      <td style="padding:28px; color:#263238;">
        <h1 style="font-size:22px; margin:0 0 18px;">Đơn hàng đã được xác nhận</h1>

        <p>
          Xin chào
          <strong th:text="${customerName}">Khách hàng</strong>,
        </p>

        <p>
          Đơn hàng
          <strong th:text="${orderId}">A123</strong>
          đã được ghi nhận.
        </p>

        <table role="presentation" cellpadding="8" cellspacing="0"
               style="width:100%; border-collapse:collapse;">
          <tr>
            <th align="left">Sản phẩm</th>
            <th align="right">SL</th>
            <th align="right">Thành tiền</th>
          </tr>
          <tr th:each="line : ${orderLines}">
            <td th:text="${line.name}">Tên sản phẩm</td>
            <td align="right" th:text="${line.quantity}">1</td>
            <td align="right" th:text="${line.priceText}">100.000 ₫</td>
          </tr>
        </table>

        <p>
          <strong>Tổng cộng:</strong>
          <span th:text="${totalText}">100.000 ₫</span>
        </p>

        <p style="margin:24px 0;">
          <a th:href="${orderUrl}" href="https://example.com/orders"
             style="display:inline-block; padding:12px 20px; background:#1769aa; color:white; text-decoration:none;">
            Xem đơn hàng
          </a>
        </p>

        <p th:if="${showSupport}">
          Nếu cần trợ giúp, vui lòng trả lời email này.
        </p>
        <p style="color:#607d8b; font-size:12px;">
          Đây là thông báo tự động từ dịch vụ của chúng tôi.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

Đây là **một mẫu HTML cho email**, không phải một trang web được render trực tiếp trong trình duyệt của ứng dụng. Các thuộc tính `th:*` chỉ được xử lý khi Thymeleaf render template ở phía server. Sau render, người nhận nhìn thấy HTML thông thường; họ không cần Thymeleaf.

### 5.1. Các biểu thức Thymeleaf đã dùng

| Cú pháp | Chức năng | Ví dụ |
| --- | --- | --- |
| `th:text="${customerName}"` | Đưa dữ liệu vào nội dung text của phần tử, có escape HTML | Tên khách hàng |
| `th:href="${orderUrl}"` | Đưa giá trị vào thuộc tính href, được xử lý phù hợp với HTML attribute | Liên kết xem đơn |
| `th:each="line : ${orderLines}"` | Lặp một phần tử cho từng mục của danh sách | Các dòng sản phẩm |
| `th:if="${showSupport}"` | Chỉ đưa phần tử vào kết quả khi điều kiện phù hợp | Phần hướng dẫn liên hệ |
| `${orderId}` | Truy xuất một biến từ context | Mã đơn hàng |

Khi render, Thymeleaf thay thế những phần cần thiết bằng giá trị từ `Context`. Template không tự tải danh sách đơn hàng từ database; dữ liệu phải được ứng dụng cấp vào.

### 5.2. Tại sao email HTML hay dùng bảng và inline CSS?

Email client không hoạt động giống trình duyệt web hiện đại:

- Nhiều client hạn chế hoặc loại bỏ JavaScript, form, external CSS và một số selector.
- Một số client có cách xử lý CSS layout, margin, font hoặc dark mode khác nhau.
- Hình ảnh từ URL ngoài có thể bị chặn để bảo vệ quyền riêng tư.
- Kích thước màn hình, phông chữ và chế độ xem thư rất đa dạng.

Bởi vậy, email HTML thực tế thường dùng **bảng cho bố cục cơ bản**, **CSS inline** và cấu trúc đơn giản. Không nên đưa các phụ thuộc như React runtime, JavaScript event handler, form đăng nhập hay CSS phức tạp vào thư rồi kỳ vọng tất cả client xử lý giống trình duyệt.

Thư nên có nội dung có thể hiểu ngay cả khi ảnh không tải, màu sắc thay đổi hoặc CSS bị lược bỏ.

## 6. Thiết kế dữ liệu riêng cho email

Không nên truyền thẳng entity JPA vào template và cho template tùy ý truy cập toàn bộ quan hệ dữ liệu. Một **DTO chuyên dùng để dựng email** giúp:

- xác định chính xác những gì được phép xuất hiện trong thư;
- tránh truy cập lazy relationship ngoài transaction;
- giảm rò rỉ thông tin không liên quan;
- dễ kiểm thử dữ liệu mẫu và các trường hợp null;
- cho phép định dạng số tiền/ngày tháng trước khi render.

Ví dụ Java record:

~~~java
package com.example.mail.application;

import java.net.URI;
import java.util.List;

public record OrderLineMailData(
        String name,
        int quantity,
        String priceText) {
}

public record OrderMailData(
        String recipient,
        String customerName,
        String orderId,
        String totalText,
        URI orderUrl,
        List<OrderLineMailData> orderLines,
        boolean showSupport) {
    public OrderMailData {
        orderLines = List.copyOf(orderLines);
    }
}
~~~

Trong một dự án Java, hai `public record` trên nên được đặt trong **hai file riêng** trùng với tên kiểu tương ứng. Ví dụ được đặt cùng nhau ở đây chỉ để thấy cấu trúc dữ liệu. `List.copyOf` tránh giữ thay đổi về sau của danh sách nguồn; vì phần tử là record với các trường value-like, mô hình có ích cho yêu cầu gửi qua queue hoặc kiểm thử.

`priceText` và `totalText` là giá trị **đã định dạng** để hiển thị. Phần tính tiền chính xác vẫn thuộc nghiệp vụ, nên dùng `BigDecimal` và quy tắc tiền tệ phù hợp, không tính lại bằng JavaScript trong email hay dùng số thực dấu phẩy động ở template.

### 6.1. Đừng cho template quyết định nghiệp vụ

Ví dụ, template có thể chọn ẩn/hiện đoạn hướng dẫn hỗ trợ qua `showSupport`. Nhưng template không nên tự quyết định khách hàng **có được phép xem đơn hàng** hay không. Quyền truy cập phải được kiểm soát ở backend khi tạo link và khi người dùng mở link; việc ẩn một nút trên email không phải cơ chế phân quyền.

Nếu đơn hàng có dữ liệu nhạy cảm, chỉ đưa lượng thông tin tối thiểu vào email. Link có thể dẫn tới trang cần đăng nhập thay vì đặt toàn bộ chi tiết thanh toán vào HTML.

## 7. Render HTML bằng Thymeleaf rồi gửi với JavaMailSender

Trong Spring Boot có starter Thymeleaf, ứng dụng thường có thể inject `SpringTemplateEngine` được cấu hình cùng resolver cho templates.

~~~java
package com.example.mail.application;

import java.util.Locale;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Service
public class OrderMailService {
    private final JavaMailSender sender;
    private final SpringTemplateEngine templateEngine;
    private final String from;
    private final String replyTo;

    public OrderMailService(
            JavaMailSender sender,
            SpringTemplateEngine templateEngine,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.sender = sender;
        this.templateEngine = templateEngine;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendConfirmation(OrderMailData data)
            throws MessagingException {
        // DTO phải được tạo và xác thực ở tầng nghiệp vụ trước đó.
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderId", data.orderId());
        context.setVariable("orderLines", data.orderLines());
        context.setVariable("totalText", data.totalText());
        context.setVariable("orderUrl", data.orderUrl().toString());
        context.setVariable("showSupport", data.showSupport());

        String html = templateEngine.process(
                "mail/order-confirmation",
                context);

        String plainText = """
                Xin chào %s,

                Đơn hàng %s đã được ghi nhận.
                Tổng cộng: %s
                Xem đơn hàng: %s
                """.formatted(
                data.customerName(),
                data.orderId(),
                data.totalText(),
                data.orderUrl());

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(from);
        helper.setReplyTo(replyTo);
        helper.setTo(data.recipient());
        helper.setSubject("Xác nhận đơn hàng " + data.orderId());
        helper.setText(plainText, html);

        sender.send(mime);
    }
}
~~~

Giải thích các bước:

1. **Tạo `Context`:** mỗi lần gửi có một context riêng cho nội dung và locale.
2. **Đưa các biến vào context:** tên biến phải khớp với biểu thức trong file HTML.
3. **Render:** `templateEngine.process("mail/order-confirmation", context)` đọc template và tạo chuỗi HTML cuối cùng.
4. **Tạo MIME message:** `JavaMailSender.createMimeMessage()` tạo đối tượng mail.
5. **Chỉ định charset:** `MimeMessageHelper(..., "UTF-8")` giúp xử lý ký tự tiếng Việt đúng trong thông điệp.
6. **Gắn text và HTML:** `setText(plainText, html)` cho phép email client chọn phiên bản thích hợp.
7. **Gửi:** `sender.send(mime)` nộp email cho transport đã cấu hình.

Đối với **Spring Boot 3.x / Spring Framework 6**, các import Jakarta Mail dùng `jakarta.mail.*` và Thymeleaf tích hợp Spring 6 có `org.thymeleaf.spring6.SpringTemplateEngine`. Trong dự án dùng Spring Boot/Spring Framework thế hệ cũ, package có thể khác; không trộn các namespace `javax.mail` cũ với `jakarta.mail` mới.

### 7.1. Tại sao không dùng SimpleMailMessage?

`SimpleMailMessage` dành cho **plain text**; đặt một chuỗi HTML vào `setText(...)` không khiến email client render các thẻ:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setText("<h1>Xin chào</h1>"); // Vẫn là văn bản thuần.
~~~

Để gửi HTML, ta cần `MimeMessage` và `MimeMessageHelper` (hoặc trực tiếp API Jakarta Mail), với phần body được khai báo kiểu `text/html`.

### 7.2. Có cần bật multipart không?

Trong ví dụ trên, helper được tạo với tham số `true`, bật hỗ trợ multipart:

~~~java
new MimeMessageHelper(mime, true, "UTF-8");
~~~

Điều này thuận tiện khi có **plain text + HTML**, và mở rộng thêm attachment hoặc ảnh nội tuyến. Với một email chỉ có HTML không attachment, có thể dùng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mime, false, "UTF-8");
helper.setText(html, true);
~~~

`setText(html, true)` cho biết đây là nội dung HTML. Với overload `setText(plainText, htmlText)`, Spring Mail tạo các cách biểu diễn thay thế để client lựa chọn. Cấu trúc MIME chi tiết có thể khác tùy multipart mode và thư viện.

Không nên đánh đồng “đã render HTML bằng Thymeleaf” với “đã gửi MIME HTML”: Thymeleaf chỉ tạo chuỗi. Lúc dựng `MimeMessage` phải khai báo nội dung phù hợp.

## 8. Cấu hình mail sender và thông tin ứng dụng

Ví dụ `application.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@company.example}
    reply-to: ${MAIL_REPLY_TO:support@company.example}
~~~

- `spring.mail.*` là cấu hình SMTP mà Spring Boot có thể dùng để khởi tạo mail sender.
- `app.mail.*` là các thuộc tính **do ứng dụng định nghĩa**; code phải đọc và đặt header qua `MimeMessageHelper`.
- Password, API key hoặc OAuth token phải được cung cấp qua môi trường chạy/secret manager, không hardcode trong Java, HTML template hoặc commit repository.
- Ví dụ dùng **STARTTLS trên cổng thường gặp 587**; provider sử dụng TLS ngay từ đầu qua cổng khác cần cấu hình transport tương ứng.

**Template không nên biết SMTP password.** Bản chất template là văn bản hiển thị cho người nhận; không có lý do đưa secret vào context. Khi debug, tránh log toàn bộ context nếu nó chứa email, token hoặc dữ liệu khách hàng.

### 8.1. Cấu hình Thymeleaf

Trong ứng dụng Spring Boot dùng Thymeleaf starter, các thuộc tính thường gặp:

~~~yaml
spring:
  thymeleaf:
    prefix: classpath:/templates/
    suffix: .html
    mode: HTML
    encoding: UTF-8
    cache: true
~~~

Đây là một cấu hình tham khảo: các giá trị trên gần với lựa chọn mặc định thông dụng. **Cache template** thường hữu ích trong production; khi phát triển giao diện email, có thể tắt cache qua cấu hình của môi trường local để dễ xem thay đổi. Không nên sửa cache policy tùy tiện để chữa lỗi dữ liệu không cập nhật: dữ liệu được truyền qua `Context` riêng cho từng lần render, còn cache chủ yếu liên quan cách nạp/parse template.

Nếu ứng dụng còn dùng Thymeleaf cho web, hãy cân nhắc phạm vi thay đổi của `spring.thymeleaf.*` vì nó có thể ảnh hưởng cả template trang web. Khi yêu cầu mail khác biệt lớn, có thể cấu hình **template resolver riêng** cho email, thay vì đổi resolver dùng chung theo cách ngoài dự kiến.

## 9. Escaping: ranh giới quan trọng khi chèn dữ liệu

Không phải mọi dữ liệu đến từ ứng dụng đều đáng tin cậy. Tên khách hàng, ghi chú đơn hàng, tên sản phẩm hoặc chuỗi nhập qua form có thể chứa dấu HTML và cả nội dung cố gắng thay đổi giao diện email.

Giả sử:

~~~text
customerName = "An <Admin> & Co"
~~~

Khi chèn bằng:

~~~html
<span th:text="${customerName}">Tên</span>
~~~

Thymeleaf sẽ escape những ký tự cần thiết để kết quả HTML biểu diễn **văn bản**:

~~~html
<span>An &lt;Admin&gt; &amp; Co</span>
~~~

Người đọc nhìn thấy nội dung tương ứng, chứ không phải một thẻ `<Admin>` mới. Đây là lý do nên dùng `th:text` cho tên người, tên sản phẩm, mã giao dịch và những dữ liệu chỉ nhằm hiển thị text.

### 9.1. Tránh `th:utext` với dữ liệu không tin cậy

Thymeleaf có `th:utext` để chèn **unescaped text**:

~~~html
<!-- Chỉ nên dùng với HTML đã được kiểm soát và xử lý an toàn. -->
<div th:utext="${trustedHtmlFragment}"></div>
~~~

Nếu dùng `th:utext` với `customerNote` do người dùng nhập, dữ liệu có thể được coi như **HTML markup** thay vì văn bản. Email client thường lọc một số HTML nguy hiểm, nhưng **không được dựa vào bộ lọc của client để bảo đảm an toàn**. Nội dung độc hại vẫn có thể tạo liên kết lừa đảo, bố cục gây hiểu nhầm hoặc vượt những giả định bảo mật.

Nếu nghiệp vụ thật sự cần HTML fragment từ trình biên tập nội dung, hãy dùng quy trình **sanitize theo allowlist** và phân quyền ai được tạo nội dung đó. Chỉ escape output theo ngữ cảnh và chỉ cho phép markup cần thiết; không lấy việc “đã dùng template engine” làm bằng chứng mọi chuỗi HTML đều an toàn.

### 9.2. Text escaping khác với kiểm tra URL

Template có:

~~~html
<a th:href="${orderUrl}">Xem đơn hàng</a>
~~~

Template engine giúp đặt giá trị vào thuộc tính HTML đúng cú pháp; nhưng nó **không tự bảo đảm địa chỉ URL là nơi người dùng nên đến**. Một đường dẫn do người dùng điều khiển có thể đưa người nhận sang website lừa đảo dù thuộc tính đã được escape.

Với liên kết giao dịch:

1. Sinh URL từ **base URL của ứng dụng đã cấu hình và kiểm soát**, thay vì nhận nguyên URL bất kỳ từ client.
2. Dùng **HTTPS** cho môi trường production phù hợp; kiểm tra hostname/domain cho phép.
3. Encode path segment và query parameter theo đúng vị trí khi tạo URI.
4. Tránh đưa token có giá trị dài hạn hoặc dữ liệu bí mật vào URL; liên kết xác minh/đặt lại mật khẩu cần token ngẫu nhiên, phạm vi rõ và hạn dùng ngắn.
5. Khi người dùng mở link, backend phải kiểm tra quyền truy cập; chỉ có đường dẫn hợp lệ trong email **không tự tạo quyền**.

Ví dụ sinh URL từ domain tin cậy thay vì tin input:

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

URI orderUrl = UriComponentsBuilder
        .fromUriString("https://app.company.example")
        .pathSegment("orders", orderId)
        .build()
        .encode()
        .toUri();
~~~

Ví dụ này sử dụng `UriComponentsBuilder` của Spring Web, do đó phải có dependency Spring Web phù hợp nếu ứng dụng chưa có. Nếu module mail chủ động không phụ thuộc Spring Web, có thể xây URI qua công cụ encode chuẩn hoặc nhận một URI đã được tạo và kiểm tra bởi tầng ứng dụng. Domain `app.company.example` chỉ để minh họa.

### 9.3. Tránh header injection

Giá trị dùng trong `Subject`, `From` hay `To` không được tạo bằng cách ghép raw SMTP/MIME header từ input. Hãy dùng setter của Spring/Jakarta Mail và kiểm tra chuỗi đầu vào, đặc biệt các ký tự điều khiển CR/LF, số lượng người nhận và độ dài.

Nội dung trong HTML được escape **không có nghĩa Subject hoặc các địa chỉ cũng đã được kiểm tra**. Header và body là hai bề mặt khác nhau.

## 10. Đừng để template tự truy cập database hoặc gọi dịch vụ bên ngoài

Một cách thiết kế kém là truyền toàn bộ `OrderEntity` vào context rồi để template truy cập mọi thuộc tính và quan hệ:

~~~java
// Không nên mặc định làm thế này:
context.setVariable("order", orderEntity);
~~~

Các rủi ro:

- Template có thể truy cập trường nhạy cảm ngoài nhu cầu hiển thị.
- Nếu `orderEntity` có lazy collection, việc render ngoài transaction có thể gây lỗi.
- Template có thể phụ thuộc vào ORM, làm giao diện mail khó tách khỏi database.
- Dữ liệu có thể bị thay đổi giữa các lần render mà không có chính sách snapshot rõ.

Thay vào đó, tầng nghiệp vụ tạo `OrderMailData` với những trường đã chọn, rồi truyền vào template. Trong template chỉ dùng các thuộc tính của DTO. Một template nên **định dạng và trình bày**, không phải nơi tìm giá, kiểm tra trạng thái thanh toán hoặc áp dụng chính sách phân quyền.

Nếu gửi mail qua queue, cân nhắc **snapshot dữ liệu khi enqueue** hoặc lưu một phiên bản dữ liệu/template rõ ràng. Việc worker dùng thông tin mới nhất có thể hợp lệ trong một số bài toán, nhưng không nên là hành vi ngẫu nhiên do data access xảy ra muộn.

## 11. Plain text và HTML là hai phiên bản của cùng email

Không phải mọi người nhận đều hiển thị HTML:

- Client có thể bị cấu hình chỉ xem plain text.
- Một số hệ thống lọc và email gateway xử lý nội dung khác nhau.
- HTML có thể bị cắt bớt, CSS không được hỗ trợ hoặc ảnh bị chặn.
- Người nhận có nhu cầu truy cập bằng công nghệ hỗ trợ hoặc môi trường băng thông hạn chế.

Vì vậy, một email giao dịch quan trọng nên có **bản plain text cung cấp cùng thông tin cốt lõi** với HTML.

Ví dụ:

~~~text
Xin chào Nguyễn An,

Đơn hàng A123 đã được ghi nhận.

Chi tiết:
- Sách Java x 1: 200.000 ₫
- Phí giao hàng: 20.000 ₫

Tổng cộng: 220.000 ₫

Xem đơn hàng:
https://app.company.example/orders/A123

Nếu cần trợ giúp, hãy trả lời email này.
~~~

HTML có thể có nút “Xem đơn hàng”, nhưng text nên chứa **URL đầy đủ**. Nếu HTML chứa thông tin quan trọng mà plain text không có, người xem text có thể bị thiếu dữ liệu.

Trong Spring Mail:

~~~java
helper.setText(plainText, html);
~~~

API này diễn đạt rằng **hai phần là lựa chọn thay thế** trong MIME, không phải nội dung gửi nối tiếp cho người nhận đọc hai lần. Thông thường email client sẽ chọn cách thể hiện phù hợp.

### 11.1. Template riêng cho bản text

Ở quy mô lớn, plain text cũng có thể được tạo từ một template dành cho text, ví dụ:

~~~text
Xin chào [[${customerName}]],

Đơn hàng [[${orderId}]] đã được ghi nhận.
Tổng cộng: [[${totalText}]]
Xem chi tiết: [[${orderUrl}]]
~~~

Đây là minh họa cú pháp **inlining text** của Thymeleaf khi được xử lý trong chế độ phù hợp. Không nên kỳ vọng file `.txt` tự hoạt động chỉ vì đã thêm Thymeleaf starter: cần cấu hình **TEXT template resolver/mode** và chọn đúng tên template, hoặc dùng một cách render text khác. Cũng cần dùng dữ liệu đã kiểm tra và tránh ghép phần chứa ký tự điều khiển vào nơi tạo header.

Đối với mail đơn giản, một formatter Java tạo plain text từ DTO có thể đủ rõ ràng; với nhiều ngôn ngữ, một bộ template HTML + text theo locale thường dễ bảo trì hơn.

## 12. Hình ảnh trong email HTML: URL và CID

Có hai cách thường gặp để đưa logo vào email:

### 12.1. Ảnh lấy từ URL bên ngoài

~~~html
<img src="https://assets.company.example/logo.png"
     alt="Company logo" width="120">
~~~

Ưu điểm: email nhỏ hơn, có thể dùng CDN. Nhược điểm: client có thể chặn ảnh remote, link có thể hết hạn hoặc nguồn ảnh không còn hoạt động. URL ảnh không nên chứa secret hoặc dữ liệu người nhận không cần thiết.

### 12.2. Ảnh inline qua Content-ID

Trong template:

~~~html
<img src="cid:company-logo" alt="Company logo" width="120">
~~~

Khi dựng MIME:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("no-reply@company.example");
helper.setTo("customer@example.net");
helper.setSubject("Chào mừng");

String html = "<html><body><img src=\"cid:company-logo\" alt=\"Logo\">" +
              "<p>Chào mừng bạn!</p></body></html>";

// Đặt text trước khi thêm tài nguyên inline.
helper.setText("Chào mừng bạn!", html);
helper.addInline(
        "company-logo",
        new org.springframework.core.io.ClassPathResource("mail/logo.png"),
        "image/png"
);

sender.send(mime);
~~~

Tài nguyên `src/main/resources/mail/logo.png` phải thực sự tồn tại trong classpath. `company-logo` trong `addInline(...)` phải khớp với phần sau `cid:` ở HTML. `MimeMessageHelper` đóng gói hình ảnh thành MIME part liên quan; một số client vẫn có thể hiển thị ảnh như tệp đính kèm hoặc chặn ảnh vì chính sách bảo mật.

Logo là tài nguyên trình bày, không nên đưa thông tin bắt buộc (mã xác nhận, số tiền, hướng dẫn bảo mật) chỉ vào hình ảnh.

## 13. Đa ngôn ngữ, định dạng tiền tệ và ngày giờ

Ứng dụng có thể gửi thư cho người dùng nhiều locale. Một mẫu HTML không nên tự đoán ngôn ngữ hoặc timezone từ server:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Context context = new Context(locale);
~~~

### 13.1. Chọn đúng locale

Một quy tắc thường gặp:

1. Nếu người dùng đã chọn ngôn ngữ trong hồ sơ, dùng ngôn ngữ đó.
2. Nếu chưa có, dùng locale mặc định của sản phẩm hoặc tổ chức.
3. Ghi rõ ngôn ngữ sử dụng ở cấp nội dung email, tránh để tiếng Việt và tiếng Anh lẫn lộn tùy từng biến.

Ví dụ ở mức tổ chức:

~~~text
templates/mail/
  order-confirmation-vi.html
  order-confirmation-en.html
~~~

Ứng dụng có thể chọn template theo locale; cũng có thể dùng Thymeleaf message bundles và `#{...}` để quốc tế hóa các chuỗi tĩnh. Nên thống nhất cách tiếp cận để một bản email không trộn các cách dịch khó kiểm soát.

### 13.2. Format số tiền bằng nghiệp vụ/locale

Nếu giá trị tổng tiền là `BigDecimal`, không nên chèn thẳng dạng debug của Java:

~~~text
220000.00
~~~

Nên hiển thị theo tiền tệ phù hợp:

~~~text
220.000 ₫
~~~

Trong ứng dụng, có thể dùng `NumberFormat.getCurrencyInstance(locale)` với currency chính xác hoặc một formatter được định nghĩa riêng theo yêu cầu sản phẩm. Đừng giả định mọi locale có cùng số chữ số thập phân, dấu ngăn cách hoặc ký hiệu tiền tệ.

### 13.3. Thời gian phải có timezone rõ

Thời điểm tạo đơn có thể lưu dưới dạng `Instant` hoặc `OffsetDateTime`. Khi render email, nên định dạng theo timezone được xác định từ người nhận hoặc cấu hình nghiệp vụ:

~~~text
Ngày đặt hàng: 12/11/2026 14:30 (GMT+7)
~~~

Nếu hiển thị “14:30” mà không rõ timezone, email có thể gây hiểu nhầm trong hệ thống xuyên quốc gia. Template chỉ nên nhận chuỗi thời gian đã định dạng hoặc một giá trị cùng quy tắc format rõ ràng.

## 14. Phân tách dữ liệu nội dung và dữ liệu vận hành

Template context có thể chứa:

~~~text
customerName
orderId
orderLines
totalText
orderUrl
showSupport
~~~

Nhưng **không nên chứa**:

~~~text
smtpPassword
smtpApiKey
dbPassword
internalAccessToken
fullUserEntity
creditCardNumber
privateSigningKey
~~~

Để tạo email, template chỉ cần dữ liệu hiển thị, không cần quyền truy cập hệ thống gửi. Những giá trị bí mật thuộc secret manager và cấu hình runtime; không truyền chúng qua controller, event payload hoặc job chỉ vì “template có thể cần”.

### 14.1. Queue và nội dung đã render

Khi gửi bất đồng bộ, cần quyết định:

**Cách A — render trước khi enqueue:** producer tạo chuỗi HTML và plain text rồi lưu snapshot vào job. Khi worker chạy, nội dung đã được chốt, nhưng kích thước payload lớn và có thể chứa nhiều thông tin cá nhân cần bảo vệ trong broker/outbox.

**Cách B — enqueue dữ liệu và template version:** producer lưu DTO đã chụp cùng định danh phiên bản template; worker render vào lúc gửi. Payload nhỏ và dễ theo dõi, nhưng phải giữ dữ liệu/phiên bản template ổn định để retry không đổi nội dung ngoài ý muốn.

| Tiêu chí | Render trước enqueue | Render ở worker |
| --- | --- | --- |
| Thời điểm xác định HTML | Producer | Worker |
| Kích thước payload queue | Có thể lớn | Thường nhỏ hơn |
| Độ ổn định nội dung khi template được sửa | Cao nếu lưu HTML hoàn chỉnh | Cần ghim template version |
| Dữ liệu nhạy cảm trong queue | Có thể chứa HTML đầy đủ | Vẫn có thể chứa dữ liệu nghiệp vụ |
| Khả năng retry cùng nội dung | Dùng snapshot đã lưu | Dùng snapshot dữ liệu + template version |

Không nên chỉ enqueue `orderId`, rồi worker tự đọc “dữ liệu mới nhất” và dùng “template mới nhất” nếu nghiệp vụ yêu cầu email phải giữ nguyên thông tin như thời điểm tạo yêu cầu. Khi đơn hàng thay đổi trước lúc gửi, hành vi đó có thể tạo thư mang nội dung không đúng sự kiện gốc.

## 15. Kiểm thử template và email được tạo

Chức năng cần được kiểm tra ở **hai ranh giới** khác nhau:

1. **Render:** dữ liệu ứng dụng đã được chèn vào template thành HTML đúng ý nghĩa, có escape và xử lý trường hợp thiếu giá trị.
2. **Gửi:** thông điệp MIME được tạo từ HTML/text đúng, địa chỉ và header được đặt đúng; có thể kiểm thử với mock hoặc SMTP server thử nghiệm.

### 15.1. Kiểm thử renderer độc lập

Ví dụ khi có `SpringTemplateEngine` được cấu hình resolver thích hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

class OrderMailTemplateTest {
    private final SpringTemplateEngine engine;

    OrderMailTemplateTest(SpringTemplateEngine engine) {
        this.engine = engine;
    }

    @Test
    void escapesCustomerNameInHtml() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", "An <Admin>");
        context.setVariable("orderId", "A123");
        context.setVariable("orderLines", java.util.List.of());
        context.setVariable("totalText", "220.000 ₫");
        context.setVariable("orderUrl", "https://app.company.example/orders/A123");
        context.setVariable("showSupport", false);

        String html = engine.process("mail/order-confirmation", context);

        assertTrue(html.contains("An &lt;Admin&gt;"));
        assertFalse(html.contains("<Admin>"));
        assertTrue(html.contains("A123"));
    }
}
~~~

Đây là đoạn **minh họa thân một test** khi một `SpringTemplateEngine` đã được cung cấp; để chạy bằng JUnit Jupiter, dự án cần tạo test instance bằng Spring test context hoặc thiết lập engine trong `@BeforeEach`/constructor theo hạ tầng kiểm thử hiện có. Không nên hiểu ví dụ này là JUnit tự inject constructor chỉ vì có tham số kiểu `SpringTemplateEngine`.

Điều đáng kiểm tra là: dữ liệu trong biến không trở thành HTML markup ngoài ý muốn; danh sách rỗng/thiếu thông tin được render theo chính sách; các liên kết cuối cùng dùng đúng domain được cấp phép.

### 15.2. Kiểm thử thông điệp gửi đi

Có thể mock `JavaMailSender` để xác nhận service gọi `createMimeMessage()` và `send(...)` với một `MimeMessage` phù hợp. Vì MIME có nhiều part và encoding, các kiểm tra sâu nên xem content MIME thực sự thay vì tìm substring trong object Java chưa được serialize.

Với integration test, có thể cấu hình SMTP giả lập như **Mailpit** hoặc **GreenMail**. Quy trình:

1. Khởi động ứng dụng với SMTP test server, không dùng credentials production.
2. Tạo DTO thử với tên Unicode và một URL hợp lệ.
3. Gọi service gửi email.
4. Xem nguồn thư/`.eml`: `Content-Type`, `charset`, các phần `text/plain` và `text/html`, header `From`, `To`, `Subject`.
5. Xem giao diện email preview; kiểm tra ảnh, nút, khoảng cách, tiếng Việt và trường hợp không tải CSS/ảnh.

Kiểm tra qua SMTP giả lập **không xác nhận thư sẽ tới Inbox** khi gửi qua provider production. Đó là bài toán vận hành và theo dõi delivery riêng.

### 15.3. Bộ dữ liệu mẫu nên có

| Tình huống thử | Mục đích |
| --- | --- |
| Tên bình thường có dấu tiếng Việt | Kiểm tra UTF-8 và font hiển thị |
| Tên chứa `<`, `>`, `&` hoặc dấu nháy | Kiểm tra escaping của template |
| Danh sách sản phẩm rỗng | Xem bố cục có cần thông điệp thay thế không |
| Danh sách dài | Xem bảng có tràn trên mobile hoặc email client không |
| Tên sản phẩm rất dài | Xem xuống dòng và chiều rộng bảng |
| Tổng tiền lớn, tiền tệ khác | Kiểm tra formatter theo locale |
| Link không hợp lệ hoặc domain ngoài allowlist | Đảm bảo ứng dụng từ chối trước khi render |
| HTML không tải ảnh/CSS | Thông tin cốt lõi vẫn đọc được |
| Địa chỉ email hoặc Subject có ký tự không hợp lệ | Validation ở tầng dựng message |

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| Người nhận thấy nguyên `<h1>...` | HTML được đưa vào `SimpleMailMessage` hoặc `setText(html, false)` | Dùng `MimeMessageHelper.setText(html, true)` hoặc bản text + HTML |
| Email có `${customerName}` hoặc `th:text` chưa được thay | Template chưa được xử lý qua Thymeleaf | Gọi `templateEngine.process(...)` và gửi kết quả render |
| Template not found | Sai tên logic, prefix/suffix hoặc file không nằm trên classpath | Kiểm tra `templates/mail/...` và resolver |
| Dữ liệu là `null` hoặc không xuất hiện | Tên biến context khác template, DTO thiếu dữ liệu | Đồng bộ contract model và template, xử lý null rõ |
| Tên khách có dấu trở thành ký tự lỗi | Charset/header hoặc encoding không phù hợp | UTF-8 trong helper và template, xem raw MIME |
| HTML hiển thị khác giữa các client | CSS/layout không được hỗ trợ đồng nhất | Bố cục email đơn giản, inline CSS, test client quan trọng |
| Ảnh không hiển thị | Ảnh remote bị chặn hoặc CID/Content-ID không khớp | Dùng alt text; kiểm tra URL hoặc `addInline` |
| Link dẫn tới domain sai | Dùng URL không được kiểm soát từ input | Sinh link bằng base URL tin cậy và kiểm tra scheme/host |
| Dữ liệu người dùng trở thành HTML markup | Nối chuỗi hoặc dùng `th:utext` với input không tin cậy | Dùng `th:text`, sanitize nội dung HTML được phép |
| Body HTML đúng nhưng người chỉ xem text bị thiếu thông tin | Không tạo plain-text alternative hoặc nội dung không đồng bộ | Tạo bản text từ cùng DTO |
| Thư có HTML nhưng SMTP từ chối | Lỗi gửi, auth, chính sách, kích thước hoặc mạng | Tách lỗi render và lỗi transport; xem SMTP/provider |
| Template cũ sau deploy | Cache template hoặc ứng dụng chưa nạp bản build mới | Xem cách deploy và cache policy theo môi trường |
| Email retry có nội dung thay đổi | Worker đọc dữ liệu/template mới nhất | Chụp dữ liệu và ghim template version hoặc lưu HTML snapshot |

### 16.1. Phân biệt lỗi render với lỗi gửi

Hai loại lỗi nằm ở hai giai đoạn:

~~~text
DTO -> TemplateEngine.process(...) -> html
         |
         +-- lỗi template / biến / expression / resolver

html -> MimeMessageHelper -> JavaMailSender.send(...)
                              |
                              +-- SMTP auth / network / policy / timeout
~~~

Nếu template không tìm thấy, lỗi xảy ra **trước** khi mở kết nối SMTP. Nếu SMTP credential sai, việc render vẫn có thể thành công, nhưng gửi sẽ thất bại.

Trong ứng dụng gửi bất đồng bộ, nên ghi rõ trạng thái như `RENDER_FAILED`, `SUBMISSION_FAILED` và `SUBMITTED` nếu hệ thống cần điều phối công việc. Không nên retry vô hạn lỗi do sai cú pháp template hoặc thiếu biến bắt buộc; những lỗi đó thường cần sửa cấu hình/nội dung hoặc dữ liệu.

## 17. Quy trình triển khai một mẫu email mới

Khi có yêu cầu “gửi email xác nhận đơn hàng có bảng sản phẩm và nút xem chi tiết”, có thể thực hiện:

1. **Chốt hợp đồng dữ liệu:** email cần tên, mã đơn hàng, các dòng sản phẩm, tổng tiền và URL. Xác định trường bắt buộc, trường tùy chọn và nguồn dữ liệu.
2. **Tạo DTO riêng:** chỉ đưa dữ liệu được phép gửi; định dạng tiền/ngày theo locale.
3. **Thiết kế HTML template:** đơn giản, dễ đọc, có alt text, inline CSS và link rõ nghĩa.
4. **Đưa dữ liệu vào context:** dùng `th:text`, `th:each`, `th:if` và `th:href` đúng ngữ cảnh.
5. **Chặn dữ liệu nguy hiểm:** không dùng `th:utext` cho input tự do; kiểm tra domain URL và người nhận.
6. **Tạo bản plain text:** cùng thông tin cốt lõi, URL đầy đủ.
7. **Dựng MIME:** dùng `MimeMessageHelper` với UTF-8, đặt From/To/Reply-To/Subject và `setText(plainText, html)`.
8. **Gửi thử nội bộ:** xem HTML preview và raw email qua SMTP test server.
9. **Đưa vào quy trình gửi thật:** theo dõi nộp thư, lỗi SMTP, retry, bounce và giới hạn gửi.
10. **Quản lý thay đổi template:** versioning, review, dữ liệu mẫu và chính sách tương thích với job đang chờ.

Đây là một quy trình có thể mở rộng từ thông báo đơn giản tới một module email có nhiều template và nhiều ngôn ngữ mà không buộc logic SMTP phải biết bố cục của từng email.

## 18. Tình huống tổng hợp: xác nhận đơn hàng theo người nhận

Giả sử ứng dụng xử lý hai đơn hàng khác nhau:

~~~text
Đơn A123:
  recipient = an@example.net
  customerName = Nguyễn An
  orderId = A123
  totalText = 220.000 ₫

Đơn B456:
  recipient = binh@example.net
  customerName = Trần Bình
  orderId = B456
  totalText = 1.250.000 ₫
~~~

Không cần hai file HTML. Ứng dụng dùng **cùng một template** nhưng tạo **hai `Context` riêng biệt**:

~~~text
order-confirmation.html
    |
    +-- Context A --> Rendered HTML A --> MimeMessage A --> an@example.net
    |
    +-- Context B --> Rendered HTML B --> MimeMessage B --> binh@example.net
~~~

Với mỗi lần gửi:

- Dữ liệu A không được rò sang thông điệp B.
- `MimeMessage` và `MimeMessageHelper` được tạo mới, không chia sẻ đối tượng mutable giữa các luồng.
- Link A/B được sinh đúng đơn hàng và phải kiểm tra quyền ở ứng dụng khi người nhận mở link.
- Subject và bản plain text được dựng từ cùng DTO.
- SMTP sender có thể dùng chung như một Spring bean, nhưng các thông điệp được dựng độc lập.

Điểm then chốt của **“Mẫu HTML và dữ liệu được chèn từ ứng dụng”** không chỉ là cú pháp `th:text`. Đó là một ranh giới thiết kế: **dữ liệu được xác định và kiểm soát ở tầng nghiệp vụ; template biến dữ liệu thành nội dung hiển thị an toàn; Spring Mail đóng gói kết quả vào MIME và gửi qua SMTP**. Khi ba phần này tách bạch, email dễ bảo trì hơn, giảm rủi ro chèn markup ngoài ý muốn, dễ kiểm thử và có thể mở rộng thành nhiều mẫu/locale mà không viết lại cơ chế gửi.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessage` và `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*` và cấu hình SMTP.
- **Spring Boot Reference — Thymeleaf:** template resolver, `spring.thymeleaf.*` và cơ chế auto-configuration.
- **Thymeleaf Documentation — Standard Dialect:** `th:text`, `th:each`, `th:if`, `th:href`, escaping và text inlining.
- **RFC 2045–2049 — MIME:** `text/plain`, `text/html`, `multipart/alternative` và cơ chế biểu diễn nội dung email.
