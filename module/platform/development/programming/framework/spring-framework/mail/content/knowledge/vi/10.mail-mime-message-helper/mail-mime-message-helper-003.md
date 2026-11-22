# Đặt From, To, Cc, Bcc và Reply-To bằng MimeMessageHelper trong Spring Framework Mail

Khi ứng dụng gửi email, phần thân có thể chỉ là vài dòng văn bản, HTML có định dạng, hoặc một thư MIME chứa file đính kèm. Dù nội dung thuộc dạng nào, ứng dụng vẫn cần xác định **ai là người gửi, ai được nhận thư, ai được nhận bản sao và các phản hồi nên chuyển về đâu**. Với Spring Framework Mail, `MimeMessageHelper` cung cấp các phương thức rõ ràng để đặt những thông tin đó lên `MimeMessage`.

Các trường thường dùng gồm:

- **From**: địa chỉ và tên người gửi mà người nhận thấy.
- **To**: người nhận chính của thông điệp.
- **Cc** (*carbon copy*): người nhận bản sao công khai.
- **Bcc** (*blind carbon copy*): người nhận bản sao kín.
- **Reply-To**: địa chỉ được đề xuất khi người nhận chọn trả lời.

Năm trường này có vai trò khác nhau. Đặc biệt, **`From` không tự quyết định tài khoản SMTP đăng nhập; `Reply-To` không phải địa chỉ nhận bounce; `Bcc` cần được xử lý đúng để không lộ người nhận**. Hiểu những ranh giới đó quan trọng không kém việc nhớ tên setter.

## 1. Các địa chỉ nằm ở đâu trong một email?

Một email có hai lớp thông tin: **message headers** nằm trong chính thư, và **SMTP envelope** phục vụ vận chuyển thư đến các mailbox đích.

Ví dụ minh họa về message headers:

```text
From: "Cửa hàng Example" <orders@example.com>
To: "Khách hàng" <customer@example.net>
Cc: "Chăm sóc khách hàng" <support@example.com>
Reply-To: "Bộ phận hỗ trợ" <helpdesk@example.com>
Subject: Xác nhận đơn hàng
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Đơn hàng của bạn đã được tiếp nhận.
```

Phần body ở dưới dòng trống đầu tiên. Trong email gửi thực tế, header có tên tiếng Việt sẽ được mã hóa theo chuẩn MIME khi cần thiết; ví dụ trên thể hiện ý nghĩa dễ đọc, không nhằm mô phỏng chính xác bytes truyền qua SMTP.

Cùng thông điệp có thể được gửi qua SMTP envelope như sau:

```text
MAIL FROM:<bounces@mailer.example.com>
RCPT TO:<customer@example.net>
RCPT TO:<support@example.com>
RCPT TO:<audit@example.com>
```

Ở đây `audit@example.com` có thể là người nhận Bcc. Người nhận qua SMTP envelope không nhất thiết xuất hiện trong `To` hay `Cc` của nội dung message. Địa chỉ ở `MAIL FROM` có thể thuộc hệ thống xử lý bounce và khác địa chỉ `From` hiển thị.

Bảng phân biệt:

| Thông tin | Tầng | Công dụng |
| --- | --- | --- |
| `From` | Header của email | Danh tính người tạo/gửi thư được trình bày cho người nhận |
| `To` | Header của email | Danh sách người nhận chính, thường hiện công khai |
| `Cc` | Header của email | Danh sách người nhận bản sao, thường hiện công khai |
| `Bcc` | Người nhận ẩn; được xử lý theo MIME/SMTP | Giao thư đến người nhận kín mà không công khai họ với người khác |
| `Reply-To` | Header của email | Địa chỉ gợi ý cho hành động Reply |
| `MAIL FROM` | SMTP envelope | Địa chỉ reverse-path cho xử lý thông báo không phát được |
| `RCPT TO` | SMTP envelope | Địa chỉ đích mà SMTP server nhận lệnh giao thư |
| `Return-Path` | Header thường do hệ thống giao thư cuối thêm | Ghi lại reverse-path ở chặng giao, không thay thế lệnh `MAIL FROM` |

`MimeMessageHelper` giúp đặt các **message headers và recipient fields** trên `MimeMessage`. Spring/Jakarta Mail và SMTP provider xử lý việc truyền thư qua SMTP. Không nên tưởng rằng `setFrom(...)` hay `setReplyTo(...)` đã cấu hình xong SMTP envelope hoặc chính sách bounce.

## 2. Chuẩn bị JavaMailSender và MimeMessageHelper

Trong Spring Boot dùng Maven, dependency thông dụng là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Với Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Spring Boot thường tự cấu hình `JavaMailSender` khi dependency và cấu hình mail đáp ứng các điều kiện tương ứng. Ví dụ `application.properties`:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Host, port và TLS mode là ví dụ; cấu hình thực tế cần theo SMTP provider. Username/password nên lấy từ biến môi trường hoặc secret manager, tránh commit credential vào repository.

Trong service, ta tạo message mới bằng sender và dùng helper để đặt các trường:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo");
helper.setText("Yêu cầu của bạn đã được tiếp nhận.", false);

mailSender.send(message);
```

Ví dụ dùng các import của Spring Framework 6+/Spring Boot 3+ với `jakarta.mail.*`. Ở ứng dụng dùng thế hệ cũ hơn, package JavaMail có thể là `javax.mail.*`; không trộn hai thế hệ trong một module.

Ở đây:

- `mailSender.createMimeMessage()` tạo một thông điệp mới.
- `new MimeMessageHelper(message, "UTF-8")` cho phép đặt header/địa chỉ và định dạng charset.
- `setText(text, false)` xác định phần thân plain text; muốn HTML có thể dùng `setText(html, true)`.
- `mailSender.send(message)` thực hiện SMTP submission.

**Đặt From/To/Cc/Bcc/Reply-To không yêu cầu riêng một chế độ multipart.** Chỉ bật multipart khi nội dung cần alternate body, hình inline, attachment hay cấu trúc MIME tương tự.

## 3. Đặt From: người gửi hiển thị

`From` là header thể hiện tác giả/người gửi của thông điệp trong nhiều email client. `MimeMessageHelper` có các dạng setter thường dùng:

```java
helper.setFrom("orders@example.com");
```

Khi muốn hiện tên dễ nhận biết:

```java
helper.setFrom("orders@example.com", "Cửa hàng Example");
```

Email client có thể hiển thị:

```text
Cửa hàng Example <orders@example.com>
```

Tên hiển thị giúp người nhận hiểu nguồn email, nhưng **không thay thế địa chỉ email**, không xác minh quyền gửi domain và không bảo đảm mailbox nhận đánh giá thư đáng tin.

### Vì sao nên dùng overload có tên hiển thị?

Đừng tự nối tên và địa chỉ bằng một chuỗi tùy ý từ người dùng:

```java
// Không nên tự dựng header thô khi tên chứa dữ liệu không tin cậy.
String from = displayName + " <orders@example.com>";
helper.setFrom(from);
```

Tên có thể chứa dấu tiếng Việt, dấu nháy, dấu phẩy hoặc ký tự có ý nghĩa cú pháp trong header. Dùng overload `setFrom(address, personalName)` để thư viện mã hóa và biểu diễn tên theo quy tắc địa chỉ email:

```java
helper.setFrom("orders@example.com", "Dịch vụ Đặt hàng");
```

Overload nhận tên hiển thị có thể khai báo thêm `UnsupportedEncodingException` bên cạnh lỗi Jakarta Mail. Có thể khai báo ở chữ ký phương thức:

```java
import jakarta.mail.MessagingException;
import java.io.UnsupportedEncodingException;

public void sendMail() throws MessagingException, UnsupportedEncodingException {
    // ...
}
```

Với charset `UTF-8` được hỗ trợ rộng rãi, lỗi encoding ít gặp, nhưng chữ ký exception vẫn cần tuân thủ API đang dùng.

### From khác tài khoản SMTP

Ví dụ:

```properties
spring.mail.username=mailer-account@example.net
```

nhưng thông điệp có:

```java
helper.setFrom("orders@shop.example.com", "Shop Example");
```

Điều này có thể hợp lệ nếu tài khoản SMTP được phép gửi thay mặt `orders@shop.example.com` hoặc domain `shop.example.com` đã được xác minh. Nếu chưa có quyền, ESP có thể từ chối, thay `From` hoặc khiến quá trình xác thực SPF/DKIM/DMARC không đáp ứng chính sách phía nhận.

Đặt `From` bằng helper chỉ xác định header của message; quyền sử dụng địa chỉ gửi cần cấu hình với nhà cung cấp SMTP.

## 4. Đặt To: người nhận chính

`To` là danh sách người nhận chính của email. Với một người nhận:

```java
helper.setTo("customer@example.net");
```

Với nhiều người nhận:

```java
helper.setTo(
    "customer@example.net",
    "account-manager@example.net"
);
```

Khi đã có mảng địa chỉ:

```java
String[] recipients = {
    "customer@example.net",
    "account-manager@example.net"
};

helper.setTo(recipients);
```

Các overload của `MimeMessageHelper` cũng hỗ trợ `InternetAddress` của Jakarta Mail khi ứng dụng đã có đối tượng địa chỉ được parse/kiểm tra:

```java
import jakarta.mail.internet.InternetAddress;

InternetAddress recipient =
        new InternetAddress("customer@example.net", "Khách hàng", "UTF-8");

helper.setTo(recipient);
```

`InternetAddress` cho phép biểu diễn email address cùng personal name. Tuy nhiên, việc tạo đối tượng địa chỉ thành công không chứng minh mailbox tồn tại hoặc domain cho phép nhận thư.

### `setTo` và `addTo` khác nhau

Tên phương thức thể hiện mục đích:

- `setTo(...)` **đặt danh sách To**; nếu được gọi lại, giá trị To trước đó được thay bằng giá trị mới.
- `addTo(...)` **thêm một địa chỉ To** vào danh sách hiện có.

Ví dụ:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

Kết quả về mặt ý nghĩa:

```text
To: alice@example.net, bob@example.net
```

Ngược lại:

```java
helper.setTo("alice@example.net");
helper.setTo("bob@example.net");
```

Kết quả To cuối thường chỉ còn `bob@example.net` do lần `setTo` sau thay danh sách trước đó.

Điều này đặc biệt quan trọng khi một helper được truyền qua nhiều phương thức: nếu lớp tạo email đầu tiên đặt To, nhưng lớp khác tiếp tục gọi `setTo` để “bổ sung”, người nhận cũ có thể bị mất. Hãy chọn rõ giữa **set toàn bộ danh sách** và **add một phần tử**.

### Thêm To có tên hiển thị

Nếu cần lưu tên người nhận vào header:

```java
helper.setTo("customer@example.net");
helper.addTo("manager@example.net", "Quản lý tài khoản");
```

Một số overload nhận personal name và có thể phát sinh `UnsupportedEncodingException`. Với tên Unicode, dùng charset UTF-8 khi tạo helper. Không đưa display name vào địa chỉ SMTP một cách tự ghép chuỗi khi không cần thiết.

### Không dùng To để diễn đạt quyền truy cập

Danh sách To chỉ là thông tin giao thư. Việc một người nằm ở To không cấp quyền truy cập dữ liệu trong URL, file đính kèm hoặc hệ thống nghiệp vụ. Nếu email chứa đường dẫn xem đơn hàng, backend đích vẫn cần xác thực và kiểm tra quyền của người truy cập.

## 5. Đặt Cc: bản sao công khai

`Cc` (carbon copy) thường dùng để thông báo thêm cho người có liên quan. Người nhận ở To và Cc thường có thể nhìn thấy danh sách Cc trong phần header mà email client hiển thị.

Ví dụ:

```java
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
```

Nếu có nhiều người nhận Cc:

```java
helper.setCc(
    "account-manager@example.com",
    "support-lead@example.com"
);
```

Hoặc thêm sau khi đã đặt danh sách ban đầu:

```java
helper.setCc("support@example.com");
helper.addCc("teamlead@example.com");
```

Giống To, `setCc(...)` đặt lại danh sách Cc, còn `addCc(...)` thêm người nhận vào danh sách hiện tại.

### Khi nào nên dùng Cc?

Cc thích hợp khi:

- Một người nhận chính chịu trách nhiệm phản hồi, nhưng một người khác cần được biết.
- Email trao đổi nội bộ cần người quản lý nhận bản sao.
- Quá trình hỗ trợ có người phụ trách chính và người cần theo dõi tiến độ.

Cc **không phù hợp** khi các người nhận không được phép biết địa chỉ của nhau, ví dụ thông báo riêng cho nhiều khách hàng độc lập. Trong trường hợp đó, gửi từng email riêng hoặc sử dụng một cơ chế gửi hàng loạt có recipient isolation.

Một lỗi thiết kế là đưa hàng trăm địa chỉ khách hàng vào Cc chỉ vì tiện cấu hình. Tác động có thể là lộ danh sách email, tạo reply-all ngoài ý muốn và gây vấn đề về quyền riêng tư.

## 6. Đặt Bcc: bản sao kín

`Bcc` (blind carbon copy) bổ sung người nhận mà thông tin của họ **không được công bố trong bản giao cho những người nhận khác**. Ví dụ:

```java
helper.setTo("customer@example.net");
helper.setBcc("audit@example.com");
```

Hoặc:

```java
helper.setBcc(
    "audit@example.com",
    "archive@example.com"
);
```

Thêm một địa chỉ Bcc:

```java
helper.addBcc("compliance@example.com");
```

**Bcc là tính năng quản lý danh sách recipient kín, không phải một loại mã hóa nội dung.** Người nhận Bcc vẫn nhận được nội dung email; hệ thống quản trị SMTP/gateway có thể quan sát recipient ở tầng vận chuyển hoặc log, và thư được chuyển tiếp/reply-all có thể gây thêm rủi ro ngoài ý muốn.

### Bcc hoạt động thế nào?

Sơ đồ khái niệm:

```text
Ứng dụng tạo message:
    To: customer@example.net
    Cc: manager@example.com
    Bcc: audit@example.com
              |
              v
Jakarta Mail / SMTP transport:
    RCPT TO:<customer@example.net>
    RCPT TO:<manager@example.com>
    RCPT TO:<audit@example.com>
              |
              v
Bản thư giao cho người nhận thông thường:
    To: customer@example.net
    Cc: manager@example.com
    (không công khai Bcc: audit@example.com)
```

Jakarta Mail/SMTP transport và các relay liên quan xử lý danh sách recipient. Khi kiểm tra Bcc, cần phân biệt **đối tượng `MimeMessage` còn nằm trong ứng dụng** với **bản email cuối tại mailbox người nhận**. Một đối tượng local vẫn có thể chứa thông tin Bcc vì thư viện cần biết nơi gửi; không nên log/hiển thị raw message đó ra bên ngoài.

Nếu tự xây raw MIME/SMTP hoặc sử dụng gateway đặc biệt, phải xác nhận cơ chế Bcc của pipeline vẫn loại bỏ hoặc xử lý đúng thông tin nhận kín. Tuyệt đối tránh tự copy danh sách Bcc vào `To`, `Cc`, body hoặc custom header.

### Bcc có phù hợp để gửi hàng loạt?

Đối với thông báo đơn giản gửi cho một nhóm nhỏ có chung nội dung, Bcc có thể hữu ích. Tuy nhiên, **Bcc không tự biến một email thành một hệ thống bulk mail an toàn**.

Những hạn chế:

- Nhà cung cấp thường có giới hạn recipient/message và rate limit.
- Tất cả người nhận nhận gần như cùng một body, không có cá nhân hóa riêng.
- Việc theo dõi giao thư/bounce theo từng người nhận có thể khó hơn tùy ESP.
- Nếu nội dung có mã xác nhận, đường dẫn riêng hoặc dữ liệu cá nhân, gửi chung qua Bcc là không phù hợp.
- Một số email client hoặc mail gateway xử lý header Bcc và dấu vết gửi khác nhau.

Đối với email giao dịch cá nhân hóa, nên tạo **một delivery cho một người nhận** hoặc sử dụng API gửi hàng loạt hỗ trợ recipient isolation và metadata riêng theo người nhận.

## 7. Đặt Reply-To: phản hồi sẽ gửi đi đâu?

`Reply-To` xác định một hoặc nhiều mailbox mà chương trình đọc email có thể sử dụng khi người nhận chọn **Reply**. Với `MimeMessageHelper`, trường hợp thường gặp:

```java
helper.setFrom("no-reply@example.com");
helper.setReplyTo("support@example.com");
```

Người nhận nhìn thấy người gửi là `no-reply@example.com`, nhưng khi chọn trả lời, email client thường đề xuất `support@example.com` làm địa chỉ đích.

Nếu cần tên hiển thị:

```java
helper.setReplyTo("support@example.com", "Bộ phận hỗ trợ");
```

Phương thức có personal name cho phép thư viện biểu diễn tên theo chuẩn header email và có thể khai báo thêm ngoại lệ về encoding.

### Khi nào Reply-To hữu ích?

- Gửi thông báo bằng địa chỉ tự động nhưng muốn nhận phản hồi ở hộp thư hỗ trợ.
- Gửi hóa đơn từ `billing@example.com` nhưng người nhận nên liên hệ `accounts@example.com`.
- Gửi thư từ một nền tảng đa tenant, trong khi mỗi tenant có mailbox hỗ trợ riêng.
- Gửi chiến dịch từ địa chỉ phát hành nhưng thu hồi phản hồi về nhóm xử lý tương ứng.

Ví dụ:

```java
helper.setFrom("notifications@example.com", "Nền tảng Example");
helper.setReplyTo("helpdesk@example.com", "Đội hỗ trợ");
helper.setTo("customer@example.net");
```

Trải nghiệm dự kiến:

```text
From: Nền tảng Example <notifications@example.com>
To: customer@example.net
Reply-To: Đội hỗ trợ <helpdesk@example.com>
```

### Reply-To không phải Return-Path

Rất dễ nhầm hai khái niệm này:

- `Reply-To`: nhận phản hồi **do người dùng tạo** trong email client.
- `Return-Path`/SMTP `MAIL FROM`: tham gia xử lý **bounce hoặc thông báo không giao được** theo SMTP.

Nếu muốn bounce chuyển về địa chỉ riêng, cần xem cơ chế **envelope sender** và chính sách provider. Chỉ đặt:

```java
helper.setReplyTo("bounces@example.com");
```

không có nghĩa SMTP sẽ dùng `MAIL FROM:<bounces@example.com>`, và cũng không bảo đảm bounce được gửi về đó.

### Reply-To không bắt buộc giống From

Một số provider có chính sách kiểm tra mối quan hệ giữa sender và reply address để chống lạm dụng/phishing, nhưng về ý nghĩa giao thức hai trường có thể khác nhau. Khi đặt Reply-To sang domain khác, cần bảo đảm địa chỉ đó thực sự được tổ chức quản lý và không gây nhầm lẫn hoặc làm thư bị đánh giá đáng ngờ.

Không dùng địa chỉ Reply-To do người dùng nhập tùy ý nếu ứng dụng có thể bị lợi dụng để gửi email trông như xuất phát từ tổ chức nhưng dẫn phản hồi đến kẻ khác. Với trường hợp kiểu contact form, có thể đặt `From` là sender đã xác minh của ứng dụng và `Reply-To` là địa chỉ người dùng **sau khi xác minh/có chính sách phù hợp**, thay vì giả mạo `From` của người dùng.

## 8. Một ví dụ Spring Service đầy đủ

Giả sử hệ thống gửi email xác nhận hoàn thành đơn hàng. Người mua là To, bộ phận hỗ trợ nhận Cc, hộp thư lưu trữ nhận Bcc, và mọi phản hồi nên chuyển về helpdesk.

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailService {

    private final JavaMailSender mailSender;

    public OrderNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderCompleted(
            String customerEmail,
            String orderCode)
            throws MessagingException, UnsupportedEncodingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, StandardCharsets.UTF_8.name());

        // Người gửi được hiển thị.
        helper.setFrom("orders@example.com", "Cửa hàng Example");

        // Người nhận chính.
        helper.setTo(customerEmail);

        // Người nhận bản sao công khai.
        helper.setCc("support@example.com");

        // Người nhận bản sao kín.
        helper.setBcc("archive@example.com");

        // Hộp thư nhận phản hồi khi khách hàng chọn Reply.
        helper.setReplyTo("helpdesk@example.com", "Bộ phận hỗ trợ");

        helper.setSubject("Đơn hàng đã hoàn thành");

        String body = """
                Xin chào,

                Đơn hàng của bạn đã được hoàn thành.

                Mã đơn: %s

                Nếu cần hỗ trợ, vui lòng trả lời email này.

                Cảm ơn bạn!
                """.formatted(orderCode);

        helper.setText(body, false);
        mailSender.send(message);
    }
}
```

Cấu trúc tương đương về ý nghĩa:

```text
From: Cửa hàng Example <orders@example.com>
To: <customerEmail>
Cc: support@example.com
Reply-To: Bộ phận hỗ trợ <helpdesk@example.com>
Subject: Đơn hàng đã hoàn thành

Body: văn bản thông báo hoàn tất đơn hàng

Recipient ẩn khi giao thư: archive@example.com
```

**Đừng đặt Bcc vào chuỗi body hoặc header To để “ghi nhớ” người lưu trữ.** Khi muốn lưu dấu nghiệp vụ, dùng ID thông báo và database/log có quyền truy cập được kiểm soát.

Ví dụ này dùng plain text. Nếu doanh nghiệp muốn gửi cả HTML và bản text dự phòng, có thể thay phần tạo helper/body bằng chế độ multipart mà không cần thay ý nghĩa From/To/Cc/Bcc/Reply-To.

## 9. Thay nội dung plain text bằng HTML vẫn dùng cùng setter địa chỉ

`MimeMessageHelper` quản lý cả phần địa chỉ lẫn việc dựng MIME body. Hai nhóm chức năng có thể kết hợp độc lập.

Ví dụ gửi HTML và plain text:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    true,
    "UTF-8"
);

helper.setFrom("notifications@example.com", "Dịch vụ Example");
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
helper.setReplyTo("support@example.com");

helper.setSubject("Cập nhật tài khoản");

String plainText = """
    Hồ sơ của bạn đã được cập nhật.

    Xem chi tiết: https://example.com/account
    """;

String htmlText = """
    <html lang="vi">
      <body>
        <h1>Hồ sơ đã được cập nhật</h1>
        <p>Xem chi tiết tại
          <a href="https://example.com/account">tài khoản của bạn</a>.
        </p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
mailSender.send(message);
```

Trong trường hợp này, constructor có `multipart=true` giúp dùng `setText(plainText, htmlText)`, tạo hai phiên bản nội dung trong một email. Những setter địa chỉ vẫn là `setFrom`, `setTo`, `setCc` và `setReplyTo` như khi gửi text.

Nếu muốn thêm PDF, chọn chế độ MIME multipart phù hợp rồi dùng `helper.addAttachment(...)`. Đừng hiểu Cc/Bcc là “part” của body: chúng thuộc thông tin recipient, không liên quan đến `multipart/alternative` hoặc `multipart/mixed`.

## 10. Dùng set hay add cho To, Cc và Bcc?

Khi có danh sách người nhận từ nhiều nguồn (khách hàng, người quản lý, hệ thống lưu trữ), nên phân biệt **thiết lập toàn bộ** và **bổ sung từng địa chỉ**.

| Nhóm | Đặt danh sách | Thêm một địa chỉ | Lưu ý |
| --- | --- | --- | --- |
| To | `setTo(...)` | `addTo(...)` | Thường ít nhất một người nhận nghiệp vụ |
| Cc | `setCc(...)` | `addCc(...)` | Công khai đối với người nhận |
| Bcc | `setBcc(...)` | `addBcc(...)` | Không đưa vào To/Cc hoặc body |
| From | `setFrom(...)` | Không xử lý như danh sách To | Thường một mailbox đại diện rõ ràng |
| Reply-To | `setReplyTo(...)` | Không xem như add recipient | Địa chỉ dùng để trả lời |

Ví dụ gộp hai bộ phận nhận thông báo:

```java
helper.setTo("owner@example.net");
helper.addTo("delegate@example.net");

helper.setCc("support@example.com");
helper.addCc("supervisor@example.com");

helper.setBcc("archive@example.com");
helper.addBcc("audit@example.com");
```

Ví dụ lỗi:

```java
helper.setTo("owner@example.net");
helper.setTo("delegate@example.net"); // Ghi đè danh sách To trước đó.
```

Nếu đang có mảng người nhận đầy đủ, nên gọi `setTo(recipients)` **một lần**, hoặc nếu cần xây từng người nhận thì dùng `addTo`. Không để hai tầng service cùng tùy tiện ghi đè To mà không có quy tắc sở hữu.

### Gửi nhiều email không giống thêm nhiều To

```java
helper.setTo("alice@example.net", "bob@example.net");
```

đặt hai người nhận cho **cùng một message**. Ngược lại, khi cần hai email với nội dung cá nhân hóa riêng:

```text
Email A:
  To: alice@example.net
  Body: Xin chào Alice, mã xác minh của bạn là...

Email B:
  To: bob@example.net
  Body: Xin chào Bob, mã xác minh của bạn là...
```

phải tạo **hai `MimeMessage` riêng biệt** hoặc dùng cơ chế personalized bulk send của provider. Không tạo một message chung có hai To và một mã OTP của Alice, vì Bob sẽ nhìn thấy dữ liệu không thuộc về mình.

## 11. Kiểm tra địa chỉ: đúng cú pháp không có nghĩa gửi được

`MimeMessageHelper` có tùy chọn `setValidateAddresses(true)` để yêu cầu validate các địa chỉ được đặt qua helper theo cơ chế `InternetAddress.validate()` của Jakarta Mail:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

// Bật kiểm tra cú pháp địa chỉ khi dùng các setter.
helper.setValidateAddresses(true);

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.com");
```

Việc bật tùy chọn này có thể giúp phát hiện một số địa chỉ sai cú pháp sớm khi tạo message. Tuy nhiên, **nó không kiểm tra DNS/MX, không truy vấn sự tồn tại của mailbox, không chứng minh người dùng sở hữu địa chỉ và không đảm bảo thư được SMTP server chấp nhận**.

### Các lớp kiểm tra khác nhau

| Kiểm tra | Ai thực hiện | Trả lời câu hỏi |
| --- | --- | --- |
| Cú pháp cơ bản | `InternetAddress`/helper, lớp validation của ứng dụng | Chuỗi có dạng địa chỉ thư phù hợp không? |
| Quy tắc nghiệp vụ | Service/application | Domain hoặc recipient này có được phép nhận loại thư này không? |
| DNS/SMTP policy | Hệ thống gửi/provider | Có thể chuyển thư tới domain/recipient không? |
| Giao nhận | SMTP relay/MX phía nhận | Server phía nhận có tiếp nhận thông điệp không? |
| Xác minh sở hữu | Luồng xác nhận token của ứng dụng | Người dùng có quyền điều khiển mailbox này không? |

Đối với form đăng ký, cần kiểm tra địa chỉ đầu vào, nhưng quyết định “người dùng đã sở hữu email” phải dựa trên luồng xác minh có token, hạn sử dụng và hành động xác nhận được backend kiểm soát.

### Tránh header injection và các giá trị bất thường

Các trường như `From`, `To`, `Reply-To` là dữ liệu cấu trúc. Không nên xây raw header bằng cách nối chuỗi từ request:

```java
// Không nên lấy nguyên chuỗi không tin cậy để tạo header thủ công.
String unsafeHeader =
    "To: " + userInput + "\r\nSubject: " + subject;
```

Nếu dữ liệu chứa CR/LF và phần tên header khác, việc tự ghép có nguy cơ gây header injection hoặc lỗi cú pháp. Dùng các setter được thiết kế cho địa chỉ; đồng thời, ở tầng ứng dụng nên từ chối ký tự điều khiển không cần thiết, đặt giới hạn độ dài và số lượng người nhận, kiểm soát domain/địa chỉ được phép theo trường hợp sử dụng.

Không nên dựa tuyệt đối vào một regex đơn giản để “xác thực mọi email hợp lệ”: chuẩn địa chỉ email có nhiều trường hợp đặc biệt; việc chấp nhận một địa chỉ theo cú pháp cũng khác việc provider có thể giao thành công. Có thể dùng `InternetAddress` và validation theo trường hợp sử dụng, bổ sung bước xác minh sở hữu khi nghiệp vụ yêu cầu.

## 12. Tiếng Việt, tên hiển thị và địa chỉ quốc tế hóa

Email có thể chứa ba loại dữ liệu dễ bị nhầm về encoding:

1. **Nội dung body**: tiếng Việt trong plain text hoặc HTML.
2. **Display name**: “Bộ phận hỗ trợ”, “Nguyễn Văn An” nằm trong phần tên của `From`/`To`/`Reply-To`.
3. **Email address**: local part và domain trong `user@example.com`.

Với body và display name, dùng `UTF-8` là lựa chọn phổ biến:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("support@example.com", "Trung tâm hỗ trợ");
helper.setTo("customer@example.net");
helper.setReplyTo("helpdesk@example.com", "Nhóm chăm sóc khách hàng");
helper.setSubject("Xác nhận yêu cầu");
helper.setText("Chúng tôi đã tiếp nhận yêu cầu của bạn.", false);
```

Jakarta Mail sẽ xử lý encoding các header khi cần. Không tự dùng chuỗi kiểu `=?UTF-8?...?=` rồi ghép vào `setFrom` nếu không hiểu rõ API encoding của thư viện; việc mã hóa lặp hoặc sai chuẩn có thể tạo tên hiển thị lỗi.

### Domain quốc tế và địa chỉ SMTPUTF8

Một địa chỉ có domain dùng ký tự ngoài ASCII có thể cần biểu diễn domain dưới dạng **IDNA/Punycode** trong những ngữ cảnh truyền email cụ thể. Ví dụ Java có `java.net.IDN` cho phần domain. Nhưng phần **local part không ASCII** (trước dấu @) có yêu cầu riêng về SMTPUTF8 và hỗ trợ ở các hệ thống chuyển tiếp; không thể “sửa” bằng cách mã hóa mỗi display name.

Vì vậy, nếu ứng dụng dự kiến hỗ trợ địa chỉ email quốc tế hóa, cần kiểm tra khả năng của Jakarta Mail, SMTP provider và hệ thống đích đối với `SMTPUTF8`, cùng chính sách xác thực/validation. Một helper dùng `UTF-8` cho personal name **không đủ** để bảo đảm địa chỉ có local part Unicode sẽ được giao.

## 13. From, Reply-To, Sender và Return-Path trong chính sách nhà cung cấp

Khi debug việc gửi mail, năm địa chỉ hiển thị/recipient không phải là toàn bộ câu chuyện.

Giả sử:

```text
SMTP account:   smtp-transactional@mailer.example.net
MAIL FROM:      bounce@mailer.example.net

Message:
From:          "Shop Example" <orders@shop.example.com>
To:            customer@example.net
Reply-To:      support@shop.example.com
```

Trong tình huống này:

- Tài khoản SMTP cung cấp quyền kết nối và gửi qua relay.
- `MAIL FROM` phục vụ SMTP reverse-path/bounce.
- `From` thể hiện sender danh nghĩa ở tầng header.
- `Reply-To` định tuyến phản hồi thủ công của người nhận.
- `To` nằm trong header, còn `RCPT TO` quyết định các recipient vận chuyển.

Các cơ chế xác thực và chống spoofing (như SPF, DKIM, DMARC) sử dụng những danh tính ở các lớp khác nhau. `DMARC` liên quan chặt với domain của `From` và alignment của SPF/DKIM. Vì vậy có thể xảy ra trường hợp SMTP login thành công nhưng thư không được đánh giá hợp lệ với `From` mà ứng dụng đặt.

`Sender` cũng là một header khác `From`, dùng trong những tình huống tác nhân thực sự truyền/gửi thay cho tác giả message theo ngữ nghĩa định dạng email. Trong phần lớn email giao dịch có một sender rõ ràng, chỉ cần đặt `From` phù hợp và để provider xử lý các header khác theo chính sách. Nếu nghiệp vụ cần `Sender` riêng, phải hiểu quy tắc RFC và chính sách ESP thay vì tùy ý thêm qua `setHeader`.

Không tự gán raw `Return-Path` để thay đổi bounce address. Một số cấu hình Jakarta Mail SMTP transport dùng thuộc tính `mail.smtp.from` để đặt envelope sender, nhưng ESP có thể yêu cầu bounce domain riêng hoặc viết lại `MAIL FROM`. Việc cấu hình envelope sender là nhiệm vụ của tầng SMTP/provider, khác với lời gọi `MimeMessageHelper#setFrom(...)`.

## 14. Kiểm soát quyền riêng tư khi gửi cho nhiều người

To, Cc và Bcc dễ bị xem như các kiểu phân loại người nhận đơn giản, nhưng lựa chọn sai có thể làm lộ dữ liệu:

- **To/Cc**: nhiều địa chỉ có thể được hiển thị cho nhau; việc dùng chung email phải có căn cứ nghiệp vụ.
- **Bcc**: che giấu người nhận kín khỏi header được phát hành cho những người nhận khác; vẫn cần bảo vệ dữ liệu từ log và hệ thống quản trị.
- **Một email mỗi người**: thích hợp khi nội dung, liên kết, tracking token, quyền truy cập hoặc dữ liệu cá nhân khác nhau.
- **Danh sách email lớn**: cần quản lý suppression, giới hạn recipient/rate, unsubscribe và bounce theo chính sách loại thư; các setter không tự cung cấp những chức năng đó.

Ví dụ sai về riêng tư:

```java
// Email xác minh tài khoản không được dùng một token chung
// cho nhiều người nhận khác nhau.
helper.setTo("alice@example.net", "bob@example.net");
helper.setText("Mã xác minh của Alice: 123456", false);
```

Một thiết kế tốt hơn:

```text
delivery #1: To alice@example.net, token riêng Alice
delivery #2: To bob@example.net, token riêng Bob
```

Trong mỗi delivery, application service tạo message mới, gắn correlation ID riêng và lưu trạng thái gửi. Khi có webhook của ESP, kết quả delivered/bounced có thể khác nhau giữa các người nhận, dù ban đầu họ cùng nằm trong một message.

### Bcc không nên dùng làm hệ thống lưu trữ mặc định

Một số ứng dụng đặt `audit@example.com` ở Bcc để lưu bản sao tất cả email. Cách này có thể phù hợp trong chính sách hạn chế, nhưng cần cân nhắc dung lượng, dữ liệu cá nhân, quyền truy cập archive, quy định lưu trữ và nguy cơ vô tình chứa OTP hoặc nội dung nhạy cảm. Khi chỉ cần lịch sử gửi, lưu **delivery metadata** trong database thường kiểm soát được tốt hơn gửi bản sao nội dung nhạy cảm đến một mailbox khác.

## 15. Xử lý nhiều request đồng thời

`JavaMailSender` thường được dùng như một bean singleton trong Spring. Điều đó giúp các service chia sẻ cấu hình SMTP. Nhưng `MimeMessage` và `MimeMessageHelper` là **đối tượng mutable chứa trạng thái của một lần gửi**; không nên tạo một instance rồi sửa To/Bcc/Reply-To trong nhiều request đồng thời.

**Không nên:**

```java
@Service
public class UnsafeMailer {
    private final JavaMailSender sender;
    private final MimeMessage sharedMessage;

    public UnsafeMailer(JavaMailSender sender) {
        this.sender = sender;
        this.sharedMessage = sender.createMimeMessage();
    }

    public void send(String recipient) throws Exception {
        MimeMessageHelper helper =
            new MimeMessageHelper(sharedMessage, "UTF-8");
        helper.setTo(recipient);
        helper.setFrom("no-reply@example.com");
        helper.setText("Nội dung");

        sender.send(sharedMessage);
    }
}
```

Nếu request A đặt `To: alice@example.net` rồi request B thay bằng `bob@example.net` trước khi A gửi xong, có thể xảy ra gửi nhầm. Thông tin Bcc và body cũng có thể bị lẫn.

**Nên:** tạo `MimeMessage` và helper mới trong từng phương thức xử lý một delivery:

```java
public void send(String recipient) throws Exception {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setText("Nội dung");

    sender.send(message);
}
```

Một sender cấu hình ổn định có thể được dùng từ nhiều service. Không đổi host, username, password hoặc các properties của `JavaMailSenderImpl` theo từng request đang chạy song song. Nếu ứng dụng đa tenant có nhiều SMTP account, tạo sender profile/bean riêng hoặc một cơ chế quản lý transport theo tenant thay vì sửa một singleton dùng chung.

## 16. Kiểm thử các địa chỉ mà không cần gửi SMTP thật

Phần logic đặt From, To, Cc, Bcc và Reply-To có thể được kiểm tra ở mức đối tượng MIME, không cần mạng. Dưới đây là ví dụ kiểm tra **message cục bộ** bằng Jakarta Mail và `MimeMessageHelper`:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class AddressHeaderTest {

    @Test
    void setsRecipientsAndReplyTo() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper =
                new MimeMessageHelper(message, "UTF-8");

        helper.setFrom("orders@example.com", "Cửa hàng Example");
        helper.setTo("customer@example.net");
        helper.setCc("support@example.com");
        helper.setBcc("archive@example.com");
        helper.setReplyTo("helpdesk@example.com");

        // Không gọi send(): chỉ quan sát message local.
        InternetAddress from =
                (InternetAddress) message.getFrom()[0];
        InternetAddress to =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.TO)[0];
        InternetAddress cc =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.CC)[0];
        InternetAddress bcc =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.BCC)[0];
        InternetAddress replyTo =
                (InternetAddress) message.getReplyTo()[0];

        assertEquals("orders@example.com", from.getAddress());
        assertEquals("Cửa hàng Example", from.getPersonal());
        assertEquals("customer@example.net", to.getAddress());
        assertEquals("support@example.com", cc.getAddress());
        assertEquals("archive@example.com", bcc.getAddress());
        assertEquals("helpdesk@example.com", replyTo.getAddress());
    }
}
```

Test local này xác minh các trường được đặt trên `MimeMessage`. Nó **không chứng minh Bcc sẽ bị ẩn trong mọi gateway**, không kiểm tra SMTP envelope thực tế và không xác nhận địa chỉ người nhận tồn tại. Những yêu cầu đó cần integration test với SMTP test server và/hoặc kiểm tra thư sau khi qua ESP.

Một service production có thể được unit test bằng mock/fake `JavaMailSender` và một phương thức tách riêng dựng message. Khi kiểm tra tên hiển thị tiếng Việt, nên xem giá trị đã decode qua `InternetAddress#getPersonal()` thay vì so sánh trực tiếp raw bytes của MIME-encoded header.

### Một số trường hợp nên đưa vào kịch bản kiểm thử

- Chỉ có một người nhận To.
- Nhiều To và Cc dùng `set...` hoặc `add...`.
- Bcc xuất hiện trong message local để gửi, nhưng không lộ ở raw email phía nhận.
- Reply-To khác From và đúng địa chỉ mong muốn.
- Display name chứa tiếng Việt, dấu phẩy hoặc ký tự cần mã hóa.
- Địa chỉ không hợp lệ bị chặn bởi validation nghiệp vụ.
- Hai lần gửi đồng thời không trộn To/Body.
- Đổi provider không làm mất hành vi To/Cc/Bcc/Reply-To đã thiết kế.

## 17. Các lỗi và hiểu nhầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Người nhận phản hồi về địa chỉ `no-reply` | Chưa đặt hoặc đặt sai `Reply-To` | Dùng `helper.setReplyTo(...)` và kiểm tra email phía nhận |
| To trước đó bị mất sau khi bổ sung người nhận | Gọi `setTo` lần thứ hai | Dùng `addTo` hoặc đặt một mảng To một lần |
| Bcc vô tình lộ cho người nhận | Tự chèn Bcc vào To/Cc/body, log raw message hoặc gateway xử lý sai | Dùng API riêng, kiểm tra pipeline giao thư và log |
| Không gửi được dù From nhìn hợp lệ | Domain/địa chỉ From chưa được ESP xác minh | Kiểm tra sender policy, quyền SMTP và SPF/DKIM/DMARC |
| Tên hiển thị tiếng Việt lỗi dấu | Mã hóa header không nhất quán | Dùng helper với UTF-8, overload có personal name |
| Thư bị từ chối vì địa chỉ recipient | Sai cú pháp, domain không nhận, mailbox không tồn tại hoặc policy server | Validate đầu vào, xem SMTP reply và ESP events |
| Bật `setValidateAddresses(true)` nhưng thư vẫn bounce | Kiểm tra cú pháp không xác minh mailbox | Phân biệt syntax validation với delivery verification |
| Muốn bounce về Reply-To nhưng không nhận | Nhầm Reply-To với envelope `MAIL FROM` | Cấu hình bounce domain/envelope sender của provider |
| Nhiều khách hàng thấy email của nhau | Đưa tất cả vào To/Cc | Gửi riêng từng người hoặc dùng bulk API an toàn |
| Một số recipient nhận được, một số không | Mỗi người nhận có kết quả SMTP/delivery khác nhau | Theo dõi kết quả theo recipient, tránh đánh dấu cả batch thành công |
| Email bị gửi nhầm người khi concurrent | Tái sử dụng `MimeMessage` hoặc helper mutable | Tạo mới cho từng delivery |
| `setReplyTo` không làm thay đổi header From | Hai trường có chức năng khác nhau | Đặt từng trường theo mục đích |
| Chỉ đặt From mà tưởng đã chọn tài khoản SMTP | Nhầm header với SMTP authentication | Cấu hình `JavaMailSender`/ESP riêng |
| SMTP accepted nhưng email không đến inbox | Lọc spam, bounce trễ, hạn chế nhận hoặc policy khác | Theo dõi webhook và xác thực domain; không suy từ `send()` |

### Ngoại lệ khi tạo hoặc gửi

Các setter trên helper có thể ném `MessagingException` khi thao tác với `MimeMessage`, và overload có personal name có thể ném `UnsupportedEncodingException`. Khi gửi, Spring có thể ném `MailException`, ví dụ `MailSendException` hoặc lỗi xác thực từ tầng SMTP.

Không nên xử lý mọi lỗi bằng cách retry ngay lập tức. Địa chỉ không hợp lệ, sender chưa được phép hay cấu hình xác thực sai thường cần sửa dữ liệu/cấu hình. Timeout sau khi client đã truyền xong nội dung nhưng chưa nhận `250` có thể là **kết quả không chắc chắn**; retry không có đối soát có thể gây gửi trùng.

## 18. Chọn người nhận theo chính sách nghiệp vụ

Giả sử hệ thống hỗ trợ có ba loại email:

**A. Thông báo khách hàng về ticket mới**

```text
From: Support Team <support@example.com>
To: customer@example.net
Reply-To: helpdesk@example.com
Cc: (không cần)
Bcc: (không cần)
```

Dùng khi người nhận cần phản hồi trực tiếp vào helpdesk, không có lý do công khai địa chỉ của người khác.

**B. Cập nhật ticket cho một nhóm nội bộ**

```text
From: Workflow Bot <workflow@example.com>
To: owner@example.com
Cc: manager@example.com
Reply-To: team-inbox@example.com
Bcc: (chỉ nếu có chính sách lưu trữ phù hợp)
```

Cc giúp manager biết cùng thông điệp. Người nhận được công khai theo quy tắc cộng tác nội bộ.

**C. Gửi thông báo cá nhân đến nhiều khách hàng**

```text
Email 1:
  To: customer-a@example.net
  Body: mã yêu cầu riêng của A

Email 2:
  To: customer-b@example.net
  Body: mã yêu cầu riêng của B
```

Không dùng một `MimeMessage` chung cho hai người với dữ liệu khác nhau. Việc tách delivery cũng giúp theo dõi bounce/retry và audit từng người nhận chính xác hơn.

Một quy tắc tốt cho hệ thống gửi email là **lớp nghiệp vụ quyết định danh sách To/Cc/Bcc/Reply-To**, còn lớp hạ tầng sử dụng `MimeMessageHelper` để chuyển quyết định đó thành message đúng cấu trúc. Nhờ vậy, quy tắc người được nhận và được phản hồi không bị rải rác trong nhiều đoạn code tạo MIME.

## 19. Ghi nhớ khi dùng MimeMessageHelper

Các thao tác cốt lõi:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("no-reply@example.com", "Hệ thống Example");
helper.setTo("customer@example.net");
helper.addTo("delegate@example.net");

helper.setCc("support@example.com");
helper.addCc("manager@example.com");

helper.setBcc("archive@example.com");

helper.setReplyTo("helpdesk@example.com", "Bộ phận hỗ trợ");
helper.setSubject("Thông báo");
helper.setText("Nội dung thư.", false);

mailSender.send(message);
```

Khi phát triển một tính năng mail, cần trả lời rõ:

1. **From**: người nhận nên nhận diện ai là người gửi, và sender domain đã được provider cho phép chưa?
2. **To**: ai là người nhận chính, họ có được phép nhìn thấy nhau không?
3. **Cc**: ai cần biết thông tin một cách công khai?
4. **Bcc**: có thật sự cần bản sao kín, có chính sách quyền riêng tư/lưu trữ phù hợp không?
5. **Reply-To**: phản hồi của người dùng nên đến mailbox nào?
6. **SMTP envelope**: bounce và routing được cấu hình ở đâu, có đang nhầm với header hiển thị không?
7. **Validation và concurrency**: địa chỉ có được kiểm tra phù hợp, message có được tạo riêng mỗi lần gửi không?

Trong Spring Framework Mail, `MimeMessageHelper` giúp tạo các header địa chỉ đúng cách và kết hợp chúng với nội dung plain text, HTML hay MIME phức tạp. Giá trị của nó nằm ở việc **diễn đạt rõ vai trò của từng địa chỉ**, để thư được gửi đúng người, phản hồi đến đúng nơi và quyền riêng tư của các recipient được giữ vững qua toàn bộ quá trình gửi email.
