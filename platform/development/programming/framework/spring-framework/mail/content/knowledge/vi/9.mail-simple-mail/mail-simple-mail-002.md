# Đặt From, To, Cc, Bcc và Subject

Khi gửi một email văn bản đơn giản bằng **Spring Framework Mail**, trước khi quan tâm đến nội dung, ứng dụng phải xác định **ai đứng tên gửi**, **ai nhận thư**, **ai nhận bản sao**, **ai nhận bản sao kín**, và **người nhận sẽ nhìn thấy tiêu đề gì**. Trong Spring, những thông tin này thường được đặt qua các phương thức `setFrom(...)`, `setTo(...)`, `setCc(...)`, `setBcc(...)` và `setSubject(...)` của `SimpleMailMessage`.

Ví dụ:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.com");
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Xác nhận đơn hàng A123");
mail.setText("Đơn hàng A123 của bạn đã được ghi nhận.");

mailSender.send(mail);
~~~

Email trên chỉ có nội dung **plain text**. Tuy nhiên, các địa chỉ và tiêu đề vẫn có ý nghĩa vận hành: `Cc` có thể làm lộ địa chỉ cho những người khác, `Bcc` ảnh hưởng cách người nhận nhìn thấy danh sách phân phối, còn `From` có thể bị nhà cung cấp từ chối nếu ứng dụng không được phép sử dụng địa chỉ đó.

## 1. Hiểu năm trường trước khi viết code

| Trường | Câu hỏi cần trả lời | Hiển thị ở email client | API Spring Mail |
| --- | --- | --- | --- |
| **From** | Thư đứng tên ai? | Thường được hiển thị rõ ràng | `setFrom(String)` |
| **To** | Ai là người nhận chính? | Thường hiển thị cho người nhận | `setTo(String...)` |
| **Cc** | Ai cần biết thông tin qua bản sao? | Thường hiển thị cho các người nhận khác | `setCc(String...)` |
| **Bcc** | Ai cần nhận bản sao kín? | Thông thường không hiển thị với các người nhận khác | `setBcc(String...)` |
| **Subject** | Bức thư nói về việc gì? | Hiển thị trong danh sách thư và khi mở thư | `setSubject(String)` |

Các trường này thuộc **thông điệp email**, không phải API quản lý người dùng hoặc hệ thống phân quyền. Đặt `Cc` không cấp quyền xem đơn hàng; đặt `Bcc` không mã hóa email; đặt `From` không tự chứng minh doanh nghiệp sở hữu tên miền gửi thư.

Trong lớp `SimpleMailMessage`, giá trị của các trường được lưu trong một đối tượng Java. Lời gọi `mailSender.send(...)` mới yêu cầu ứng dụng thực hiện việc nộp thư cho hệ thống vận chuyển được cấu hình.

## 2. From: địa chỉ đứng tên gửi

`From` trả lời câu hỏi **“Ai là tác giả/người đứng tên email này?”**. Với mail tự động, đây thường là địa chỉ chung của ứng dụng hoặc một bộ phận:

~~~java
mail.setFrom("no-reply@example.com");
~~~

Hoặc:

~~~java
mail.setFrom("billing@example.com");
~~~

Trong hộp thư, người nhận thường thấy `From` trước khi mở email. Vì vậy, địa chỉ nên giúp họ nhận biết đúng nguồn thông báo.

### 2.1. From không nhất thiết bằng tài khoản dùng đăng nhập SMTP

Ví dụ ứng dụng có:

~~~yaml
spring:
  mail:
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Và mã Java:

~~~java
mail.setFrom("billing@example.com");
~~~

`spring.mail.username` là tài khoản **xác thực với SMTP provider**, còn `From` là địa chỉ hiển thị trong **header của email**. Chúng có thể trùng hoặc khác nhau, tùy chính sách nhà cung cấp. Một tài khoản kỹ thuật có thể được phép gửi từ nhiều địa chỉ đã xác minh trong cùng một domain; nhà cung cấp khác có thể chỉ cho phép đúng địa chỉ của tài khoản.

Không nên tự đặt `From: ceo@another-company.example` rồi kỳ vọng hệ thống gửi thành công. SMTP provider có thể từ chối, thay địa chỉ hoặc đánh dấu thư không phù hợp chính sách. Những cơ chế như SPF, DKIM và DMARC cũng ảnh hưởng đến xác thực và độ tin cậy của thư.

### 2.2. From khác địa chỉ nhận lỗi phát thư

Trong SMTP, ứng dụng hoặc provider có thể dùng **envelope sender** (`MAIL FROM`) để nhận thông báo phát thư không thành công (bounce). Đây là thông tin vận chuyển, có thể khác header `From` mà người dùng nhìn thấy.

~~~text
SMTP envelope:
  MAIL FROM:<bounce-814@mailer.example.com>
  RCPT TO:<customer@example.net>

Message header:
  From: billing@example.com
  To: customer@example.net
  Subject: Hóa đơn tháng 11
~~~

`SimpleMailMessage.setFrom(...)` đặt thông tin From của thư; không nên coi nó là API điều khiển toàn bộ reverse-path hay quản lý bounce của provider. Nếu cần kiểm soát bounce, ứng dụng phải xem cách cấu hình SMTP envelope, provider và sự kiện DSN/webhook tương ứng.

### 2.3. From và tên hiển thị

Một email có thể hiển thị:

~~~text
From: "Customer Support" <support@example.com>
~~~

Với **địa chỉ đơn giản**, `SimpleMailMessage.setFrom("support@example.com")` là lựa chọn rõ ràng. Nếu cần tên hiển thị có dấu tiếng Việt, quản lý chi tiết header và encoding, nên dùng `MimeMessageHelper.setFrom(address, personalName)` của Spring Mail:

~~~java
MimeMessage mime = javaMailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");
helper.setFrom("support@example.com", "Bộ phận hỗ trợ");
~~~

Lớp `SimpleMailMessage` chỉ cung cấp setter nhận chuỗi địa chỉ, không có API riêng để truyền tên hiển thị và charset như helper MIME. Việc chuyển sang MIME là hợp lý khi header có yêu cầu trình bày phức tạp.

## 3. To: những người nhận chính

`To` xác định một hoặc nhiều địa chỉ nhận chính của email.

Gửi cho một người:

~~~java
mail.setTo("customer@example.net");
~~~

Gửi cho nhiều người:

~~~java
mail.setTo(
    "alice@example.net",
    "bob@example.net"
);
~~~

Hoặc khi ứng dụng đã có mảng:

~~~java
String[] recipients = {
    "alice@example.net",
    "bob@example.net"
};
mail.setTo(recipients);
~~~

`setTo(...)` nhận nhiều giá trị thông qua Java varargs. Điều này có nghĩa một thư có thể được gửi tới nhiều người nhận chính mà không cần tạo một `SimpleMailMessage` riêng cho mỗi địa chỉ.

### 3.1. Nhiều To có phải nhiều email riêng không?

Nếu đặt:

~~~java
mail.setTo("alice@example.net", "bob@example.net");
mail.setText("Chào tất cả các bạn.");
~~~

thì ứng dụng đang mô tả **một thông điệp có nhiều người nhận**. Về cơ bản, hai người nhận cùng nội dung và có thể nhìn thấy địa chỉ của nhau trong header `To`. Đây không phải cách phù hợp nếu nội dung có dữ liệu cá nhân riêng cho từng người.

Ngược lại:

~~~java
SimpleMailMessage forAlice = new SimpleMailMessage();
forAlice.setTo("alice@example.net");
forAlice.setText("Xin chào Alice.");

SimpleMailMessage forBob = new SimpleMailMessage();
forBob.setTo("bob@example.net");
forBob.setText("Xin chào Bob.");
~~~

đây là **hai thông điệp riêng**, có thể quản lý trạng thái gửi và nội dung độc lập. Trong hệ thống gửi xác nhận giao dịch, hóa đơn hoặc thông báo liên quan tài khoản, mô hình riêng từng người nhận thường hợp lý hơn.

### 3.2. Địa chỉ trong To không chứng minh người dùng tồn tại

Một chuỗi như `unknown@example.net` có thể trông hợp lệ về cú pháp nhưng mailbox thực tế không tồn tại, bị khóa hoặc server đích không nhận thư. Khi gửi, SMTP server có thể từ chối ngay hoặc nhận thư rồi phát sinh bounce sau đó.

Nếu người dùng nhập địa chỉ qua form, ứng dụng cần kiểm tra dữ liệu và quy tắc nghiệp vụ. Đối với địa chỉ liên quan tài khoản, quy trình xác nhận quyền sở hữu email có thể cần thiết; chỉ kiểm tra có ký tự `@` là chưa đủ.

## 4. Cc: gửi bản sao và để mọi người cùng biết

**Cc** viết tắt của *Carbon Copy*. Một người trong `Cc` được nhận bản sao email, thường với ý nghĩa **được cập nhật thông tin** thay vì chịu trách nhiệm chính.

Ví dụ khách hàng nhận thông báo, nhân viên phụ trách nhận bản sao:

~~~java
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
~~~

Người nhận trong `To` thường nhìn thấy rằng `account-manager@example.com` đã được Cc, và người nhận Cc thường cũng nhìn thấy các địa chỉ To/Cc khác. Việc này có thể hữu ích trong trao đổi nội bộ nhưng cần cân nhắc khi giao tiếp với khách hàng.

### 4.1. Khi nào nên dùng Cc?

Một số trường hợp hợp lý:

- Gửi email cho người phụ trách chính và Cc quản lý dự án.
- Gửi kết quả xử lý cho nhóm liên quan cần cùng thấy danh sách người nhận.
- Lưu những người tham gia một cuộc trao đổi doanh nghiệp trong cùng chuỗi hội thoại.

Một số trường hợp **không nên dùng Cc**:

- Gửi thông báo cá nhân cho hàng trăm người dùng không liên quan.
- Gửi dữ liệu đơn hàng hoặc tài khoản mà người nhận này không được phép xem.
- Cc người ngoài chỉ để “lưu một bản” khi không có lý do nghiệp vụ rõ ràng.

**Cc không chỉ là một lựa chọn kỹ thuật:** nó còn là quyết định chia sẻ địa chỉ và nội dung email cho các bên khác.

### 4.2. Cc và Reply All

Nếu email có:

~~~text
From: sender@example.com
To: alice@example.net
Cc: bob@example.net
~~~

khi Alice bấm **Reply All**, Bob thường có thể được thêm vào danh sách người nhận của email trả lời. Cách chọn người nhận chính xác phụ thuộc email client. Do đó, đặt người vào Cc có thể kéo họ vào các trao đổi tiếp theo, kể cả khi mục đích ban đầu chỉ là nhận thông báo.

## 5. Bcc: gửi bản sao kín

**Bcc** viết tắt của *Blind Carbon Copy*. Người có địa chỉ trong `Bcc` được đưa vào danh sách nhận thư, nhưng thông tin về họ **không được hiển thị cho những người nhận khác trong bản email được phát** theo cách gửi thông thường.

~~~java
mail.setTo("customer@example.net");
mail.setBcc("archive@example.com");
~~~

Trong ví dụ, hệ thống gửi email cho khách hàng và thêm một người nhận bản sao kín. Khách hàng thông thường không thấy `archive@example.com` trong header của bản thư được phát tới họ.

### 5.1. Bcc không phải mã hóa và không bảo đảm bí mật tuyệt đối

Bcc là **cơ chế phân phối và hiển thị địa chỉ**, không mã hóa nội dung email. Người nhận Bcc vẫn có thể:

- đọc toàn bộ nội dung mà họ đã nhận;
- chuyển tiếp thư hoặc tự tiết lộ mình được nhận thư;
- vô tình trả lời theo cách làm lộ việc tham gia cuộc trao đổi;
- xuất hiện trong log/metadata của hệ thống gửi, provider hoặc nơi họ nhận thư.

Các máy chủ và email client có thể xử lý header Bcc theo nhiều cách phù hợp chuẩn, chẳng hạn loại bỏ header đó khỏi bản thư phát đi. Vì vậy, **không dựa vào việc đọc header `Bcc` trong hộp thư của người nhận để xác minh toàn bộ danh sách Bcc ban đầu**.

Nếu mục tiêu là kiểm soát truy cập nội dung, phải thực hiện phân quyền và chính sách dữ liệu ở tầng ứng dụng. Bcc không ngăn người nhận chuyển tiếp nội dung đã được gửi cho họ.

### 5.2. Bcc có phù hợp để gửi thông báo hàng loạt?

Một mẫu có thể thấy:

~~~java
mail.setFrom("events@example.com");
mail.setTo("events@example.com");
mail.setBcc(
    "participant1@example.net",
    "participant2@example.net",
    "participant3@example.net"
);
mail.setSubject("Lịch sự kiện tháng tới");
~~~

Với thông điệp chung, một số hệ thống dùng Bcc để không lộ danh sách người nhận. Tuy nhiên, **Bcc không thay thế nền tảng bulk mail hoặc cơ chế gửi hàng loạt được kiểm soát**: còn phải cân nhắc chính sách provider, quota, giới hạn số người nhận, chống spam, unsubscribe nếu liên quan và khả năng ghi nhận trạng thái theo từng địa chỉ.

Khi cần cá nhân hóa, xử lý bounce/retry riêng, giới hạn tốc độ hoặc tránh lộ dữ liệu, nên tạo **một thư riêng cho mỗi người nhận** qua job/queue hoặc công cụ gửi thích hợp.

### 5.3. Ví dụ Cc và Bcc trong cùng thông điệp

~~~java
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.com");
mail.setBcc("audit@example.com");
~~~

Kết quả về mặt ý định:

| Địa chỉ | Nhận nội dung? | Có thể xuất hiện với các người nhận khác? |
| --- | --- | --- |
| `customer@example.net` | Có, người nhận To | Có, thông qua To |
| `account-manager@example.com` | Có, người nhận Cc | Có, thông qua Cc |
| `audit@example.com` | Có, người nhận Bcc | Thông thường không được lộ trong bản giao cho người nhận khác |

Về giao thức, SMTP phải chuyển phát tới các địa chỉ đích tương ứng, kể cả địa chỉ được gắn Bcc. **Header hiển thị và danh sách đích trong SMTP envelope là hai lớp khác nhau.**

## 6. Subject: tiêu đề thư

`Subject` cho người nhận biết nội dung chính của email và thường được hiển thị trong danh sách thư:

~~~java
mail.setSubject("Đơn hàng A123 đã được xác nhận");
~~~

Tiêu đề nên đủ cụ thể để giúp người nhận phân biệt các email tương tự, nhưng không chứa thông tin bí mật. Ví dụ:

| Chưa rõ ràng | Rõ nghĩa nghiệp vụ hơn |
| --- | --- |
| `Thông báo` | `Đơn hàng A123 đã được xác nhận` |
| `Cập nhật` | `Trạng thái yêu cầu hỗ trợ #452 đã thay đổi` |
| `Có báo cáo mới` | `Báo cáo doanh thu tháng 11 đã sẵn sàng` |
| `Quan trọng!!!` | `Cần xác nhận địa chỉ email cho tài khoản của bạn` |

Tránh đưa mật khẩu, token xác thực, mã khôi phục bí mật hoặc dữ liệu cá nhân nhạy cảm vào Subject. Tiêu đề có thể xuất hiện trong thông báo trên màn hình khóa, log và lịch sử email mà người khác nhìn thấy.

### 6.1. Subject là header, không phải HTML

Nếu đặt:

~~~java
mail.setSubject("<b>Đơn hàng đã xác nhận</b>");
~~~

thì các thẻ `<b>` là ký tự của tiêu đề, không phải chỉ dẫn để email client render chữ đậm. Subject cần là chuỗi văn bản phù hợp, còn định dạng HTML (nếu cần) thuộc phần **body MIME**, không phải header Subject.

### 6.2. Subject tiếng Việt và encoding

~~~java
mail.setSubject("Xác nhận lịch hẹn của bạn");
~~~

Trong Java, `String` biểu diễn văn bản Unicode. Khi email được xây dựng để gửi, thư viện mail đảm nhiệm mã hóa header theo các quy tắc email phù hợp. Với Spring Boot, nên khai báo rõ encoding khi gửi nội dung có dấu:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

Nếu mở “View original / Show source” của email, tiêu đề Unicode có thể được hiển thị dưới dạng `encoded-word`, ví dụ cấu trúc:

~~~text
Subject: =?UTF-8?B?<encoded-bytes>?=
~~~

Phần `<encoded-bytes>` ở đây chỉ là placeholder minh họa. Email client giải mã header để hiển thị tiếng Việt. Không nên tự chuyển chuỗi subject sang Base64 trước khi gọi `setSubject(...)`; điều đó có thể khiến thư bị mã hóa hai lần hoặc hiện chuỗi mã hóa không mong muốn.

### 6.3. Tiêu đề động từ dữ liệu nghiệp vụ

~~~java
String orderId = "A123";
mail.setSubject("Đơn hàng " + orderId + " đã được xác nhận");
~~~

Khi `orderId` hoặc thông tin tạo tiêu đề đến từ input bên ngoài, cần giới hạn độ dài, chuẩn hóa theo nghiệp vụ và ngăn ký tự xuống dòng/điều khiển không hợp lệ. Không nối các dòng header thô từ input. API cấp cao của Spring/Jakarta Mail hỗ trợ tạo header đúng định dạng, nhưng kiểm tra dữ liệu đầu vào vẫn là trách nhiệm của ứng dụng.

## 7. Ví dụ hoàn chỉnh với `SimpleMailMessage`

### 7.1. Tạo mail với đủ From, To, Cc, Bcc, Subject

~~~java
package com.example.mail.application;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationMailService {
    private final JavaMailSender mailSender;

    public OrderNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmed(String customerEmail, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();

        mail.setFrom("orders@example.com");
        mail.setTo(customerEmail);
        mail.setCc("account-manager@example.com");
        mail.setBcc("audit@example.com");
        mail.setSubject("Đơn hàng " + orderId + " đã được xác nhận");
        mail.setText("""
                Xin chào,

                Đơn hàng %s của bạn đã được xác nhận.
                Nếu cần hỗ trợ, vui lòng liên hệ bộ phận chăm sóc khách hàng.

                Trân trọng,
                Đội ngũ xử lý đơn hàng
                """.formatted(orderId));

        mailSender.send(mail);
    }
}
~~~

Đây là ví dụ minh họa API. Trên hệ thống thật, không nên tự động Cc/Bcc các địa chỉ nội bộ cho mọi đơn hàng nếu chưa có quy tắc chia sẻ dữ liệu và quyền truy cập tương ứng. Địa chỉ From cũng nên lấy từ cấu hình; phần tiếp theo trình bày cách đó.

### 7.2. Đưa địa chỉ From và Cc vào cấu hình

Ví dụ `application.yml` trong Spring Boot:

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
    order-from: ${ORDER_MAIL_FROM:orders@example.com}
    order-cc: ${ORDER_MAIL_CC:account-manager@example.com}
~~~

`spring.mail.*` là nhóm cấu hình SMTP được Spring Boot hỗ trợ. `app.mail.*` là thuộc tính do **ứng dụng tự đặt tên**, cần được đọc bằng `@Value` hoặc `@ConfigurationProperties`. Mật khẩu SMTP phải do môi trường chạy/secret manager cung cấp, không lưu trực tiếp trong repository.

Đoạn service:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ConfiguredOrderMailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String ccAddress;

    public ConfiguredOrderMailService(
            JavaMailSender sender,
            @Value("${app.mail.order-from}") String fromAddress,
            @Value("${app.mail.order-cc}") String ccAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.ccAddress = ccAddress;
    }

    public void sendConfirmation(String customerEmail, String orderId) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(customerEmail);
        mail.setCc(ccAddress);
        mail.setSubject("Xác nhận đơn hàng " + orderId);
        mail.setText("Đơn hàng " + orderId + " đã được xác nhận.");
        sender.send(mail);
    }
}
~~~

Khi đổi địa chỉ gửi đã được provider xác minh hoặc thay người nhận bản sao theo bộ phận, đội vận hành có thể thay cấu hình mà không sửa code Java. Nếu không có nhu cầu Cc, nên bỏ trường đó thay vì luôn khai báo một địa chỉ không liên quan.

## 8. Một cách chọn To, Cc, Bcc theo nghiệp vụ

Xét ba tình huống:

### 8.1. Thư xác nhận tài khoản cá nhân

~~~java
mail.setFrom("no-reply@example.com");
mail.setTo(userEmail);
mail.setSubject("Tài khoản đã được tạo");
// Không tự động thêm Cc/Bcc.
~~~

Mỗi người dùng nhận một thông điệp riêng. Đây thường là cách phù hợp để tránh lộ dữ liệu và để hệ thống biết người nào đã được gửi.

### 8.2. Trao đổi công việc có người cần theo dõi

~~~java
mail.setFrom("project@example.com");
mail.setTo("task-owner@example.com");
mail.setCc("teamlead@example.com");
mail.setSubject("Cập nhật tiến độ công việc A123");
~~~

Người phụ trách chính ở To, người cần biết ở Cc. Vì Cc được hiển thị và có thể tham gia Reply All, hãy chọn đúng người có liên quan đến nội dung.

### 8.3. Gửi một bản sao kín cho quy trình được phê duyệt

~~~java
mail.setFrom("system@example.com");
mail.setTo("recipient@example.net");
mail.setBcc("archive@example.com");
mail.setSubject("Xác nhận yêu cầu");
~~~

Bcc có thể phục vụ một nhu cầu nội bộ hợp lệ như lưu bản sao trong mailbox đã được phê duyệt, nhưng không nên xem mailbox đó là nguồn trạng thái duy nhất. Nếu phải audit mọi lần gửi, một bảng log/job có ID nghiệp vụ và chính sách lưu trữ thường đáng tin cậy hơn.

## 9. Quy tắc SMTP và header: tại sao To/Cc/Bcc không phải toàn bộ câu chuyện?

Để hiểu chính xác, cần phân biệt:

- **Message headers:** `From`, `To`, `Cc`, `Subject` là nội dung header mà email client dùng để hiển thị.
- **SMTP envelope recipients:** `RCPT TO` cho server biết những mailbox cần nhận thư khi thực hiện giao thức SMTP.

Ví dụ:

~~~text
SMTP envelope:
  MAIL FROM:<bounce@example.com>
  RCPT TO:<alice@example.net>
  RCPT TO:<manager@example.com>
  RCPT TO:<audit@example.com>

Message headers:
  From: orders@example.com
  To: alice@example.net
  Cc: manager@example.com
  Subject: Xác nhận đơn hàng
~~~

Địa chỉ `audit@example.com` là một đích vận chuyển được liệt kê trong SMTP envelope, nhưng **không cần xuất hiện trong To/Cc header** ở bản thư người khác nhận. Đây là lý do Bcc hoạt động.

Trong Spring, `JavaMailSender` và Jakarta Mail provider xử lý chuyển dữ liệu người nhận từ message thành hoạt động gửi phù hợp. Ứng dụng không cần tự ghép lệnh `RCPT TO` khi dùng `SimpleMailMessage`.

### 9.1. To/Cc/Bcc có thể thành công hoặc thất bại khác nhau

Nếu một email có nhiều người nhận, SMTP provider có thể chấp nhận một số địa chỉ và từ chối địa chỉ khác. Tùy provider và cấu hình Jakarta Mail, sender có thể ném ngoại lệ, có thể phát sinh tình huống gửi thành công một phần, hoặc thông báo thất bại đến sau khi thư đã được chấp nhận.

Vì vậy, một lần gọi:

~~~java
mailSender.send(mail);
~~~

**không phải giao dịch bảo đảm tất cả người nhận đều đã nhận thư**. Nếu nghiệp vụ cần biết trạng thái từng khách hàng, hãy quản lý yêu cầu gửi theo từng địa chỉ và theo dõi sự kiện từ provider khi có hỗ trợ.

### 9.2. Reply-To không thay thế From

Ngoài năm trường trong bài, có thêm header `Reply-To`:

~~~java
mail.setFrom("notification@example.com");
mail.setReplyTo("support@example.com");
~~~

`From` là người đứng tên gửi; `Reply-To` gợi ý nơi nhận câu trả lời khi người dùng bấm Reply. Nó không đổi các địa chỉ To/Cc/Bcc và không thay thế envelope sender xử lý bounce.

## 10. Kiểm tra dữ liệu địa chỉ trước khi gửi

Một API gửi mail nội bộ có thể nhận email của khách hàng từ database hoặc biểu mẫu. Dù Spring cung cấp setter đơn giản, ứng dụng vẫn phải kiểm soát dữ liệu:

1. **Địa chỉ phải có nguồn đáng tin cậy:** ví dụ email của tài khoản đã xác minh hoặc người nhận được phê duyệt.
2. **Cú pháp cần hợp lệ:** kiểm tra/parse bằng công cụ phù hợp, nhưng cú pháp đúng không bảo đảm mailbox tồn tại.
3. **Không tự cho phép thay From:** endpoint không nên nhận chuỗi From tùy ý từ người dùng ngoài.
4. **Không nhận Cc/Bcc không kiểm soát:** có thể dẫn tới rò rỉ thông tin hoặc lạm dụng hệ thống làm mail relay.
5. **Không đưa đầu vào thô vào header:** giới hạn độ dài, loại bỏ ký tự điều khiển như CR/LF không hợp lệ và để thư viện mail tạo header.
6. **Hạn chế lộ thông tin trong log:** tránh ghi toàn bộ email recipients, Subject và body khi không cần thiết.

Ví dụ parse địa chỉ với Jakarta Mail trong ứng dụng Boot 3.x:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public static String parseSingleMailbox(String value)
        throws AddressException {
    InternetAddress[] parsed = InternetAddress.parse(value, true);
    if (parsed.length != 1) {
        throw new AddressException("Expected exactly one email address");
    }
    parsed[0].validate();
    return parsed[0].getAddress();
}
~~~

Đoạn này kiểm tra một số quy tắc cú pháp và yêu cầu đúng **một** địa chỉ, hữu ích khi không muốn một trường input biến thành danh sách người nhận. Nó **không** xác minh domain có MX, hộp thư có tồn tại hay người nhập có quyền sử dụng địa chỉ. Tùy yêu cầu, còn cần chuẩn hóa, ràng buộc domain, xác nhận email hoặc chính sách chống lạm dụng.

Khi xây Subject từ dữ liệu nghiệp vụ, cũng cần giới hạn ký tự và tránh đưa thông tin bí mật vào tiêu đề.

## 11. Kiểm thử việc đặt From, To, Cc, Bcc, Subject

Vì `SimpleMailMessage` là đối tượng Java, ứng dụng có thể kiểm tra các trường đã đặt mà không phải thật sự kết nối SMTP.

### 11.1. Kiểm tra các getter

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("orders@example.com");
mail.setTo("alice@example.net", "bob@example.net");
mail.setCc("manager@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Xác nhận đơn hàng A123");
mail.setText("Đơn hàng đã được ghi nhận.");

String from = mail.getFrom();
String[] to = mail.getTo();
String[] cc = mail.getCc();
String[] bcc = mail.getBcc();
String subject = mail.getSubject();
~~~

Kết quả getter cho biết trạng thái của **đối tượng Java**. Nó không chứng minh mail sender đã thực sự gửi thành công hoặc provider đã chấp nhận mọi recipient.

### 11.2. Ví dụ unit test với Mockito

Nếu service inject `JavaMailSender`, có thể bắt lại tham số truyền vào `send`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class OrderNotificationMailServiceTest {

    @Test
    void usesExpectedAddressesAndSubject() {
        JavaMailSender sender = mock(JavaMailSender.class);
        OrderNotificationMailService service =
                new OrderNotificationMailService(sender);

        service.sendOrderConfirmed("customer@example.net", "A123");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("orders@example.com", sent.getFrom());
        assertArrayEquals(
                new String[]{"customer@example.net"},
                sent.getTo());
        assertArrayEquals(
                new String[]{"account-manager@example.com"},
                sent.getCc());
        assertArrayEquals(
                new String[]{"audit@example.com"},
                sent.getBcc());
        assertEquals("Đơn hàng A123 đã được xác nhận", sent.getSubject());
    }
}
~~~

Unit test này xác nhận cấu hình các trường và lời gọi sender. Nó không kiểm chứng Bcc đã được ẩn trong bản thư phát đi hoặc Subject được encode đúng trong SMTP/MIME. Những hành vi đó cần test tích hợp ở tầng mail transport.

### 11.3. SMTP test server và raw message

Có thể dùng Mailpit hoặc GreenMail ở môi trường local/test để nhận thư thử, rồi:

- Xem header `From`, `To`, `Cc`, `Subject` trong thông điệp.
- Kiểm tra các người nhận đã được gửi qua SMTP, kể cả Bcc, nếu công cụ test cung cấp dữ liệu envelope.
- Quan sát header `Bcc` có được loại khỏi bản phát cho người nhận khác không.
- Xác nhận Subject tiếng Việt hiển thị và giải mã đúng.
- Thử email có nhiều To/Cc/Bcc để hiểu cách provider xử lý các địa chỉ hợp lệ và không hợp lệ.

Khi đánh giá riêng tư của Bcc, cần xem **bản thư được phát tới từng người nhận** hoặc hành vi SMTP server, không chỉ xem đối tượng `SimpleMailMessage` trước khi gửi.

## 12. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng / nhầm lẫn | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `From` trông hợp lệ nhưng SMTP từ chối | Địa chỉ/domain chưa được provider cấp phép | Kiểm tra sender identity, SMTP credentials và quyền gửi |
| Gửi tới nhiều To làm lộ danh sách khách hàng | Dùng một message cho nhiều người không liên quan | Gửi riêng từng người khi yêu cầu riêng tư/cá nhân hóa |
| Người nhận thấy địa chỉ nội bộ ở Cc | Cc được thiết kế để hiển thị | Chỉ Cc người thật sự cần có mặt trong cuộc trao đổi |
| Nghĩ Bcc bảo mật được nội dung | Bcc chỉ giới hạn hiển thị danh sách nhận | Kiểm soát quyền truy cập và nội dung từ nguồn |
| Không thấy Bcc trong raw message của người nhận | Đó có thể là hành vi bình thường của mail transport | Xem dữ liệu gửi/envelope khi cần kiểm chứng |
| Subject tiếng Việt hiển thị lỗi | Encoding/header bị xử lý không phù hợp | Cấu hình UTF-8 và kiểm tra raw message |
| Đưa HTML vào Subject rồi mong in đậm | Subject là text của header | Dùng tiêu đề văn bản, định dạng ở body MIME |
| `To` hợp lệ nhưng chưa có email trong Inbox | SMTP/server phía sau có thể từ chối hoặc trả lại sau | Kiểm tra kết quả provider, bounce và tình trạng giao thư |
| Cc được thêm khi Reply All | Email client thường giữ người ở Cc khi trả lời tất cả | Cân nhắc người nhận từ đầu, không dùng Cc như ghi log |
| Nhiều người nhận nhưng chỉ một số nhận thành công | SMTP có thể chấp nhận/từ chối từng địa chỉ | Theo dõi kết quả theo recipient, không giả định all-or-nothing |
| Muốn thay địa chỉ bounce bằng `setFrom` | Nhầm header From với SMTP envelope | Cấu hình reverse-path/bounce tại transport hoặc provider |
| Dùng chung một `SimpleMailMessage` trên nhiều thread | Đối tượng mutable bị ghi đè | Tạo message mới cho mỗi lần gửi |

### 12.1. Tránh dùng chung đối tượng mutable

Không nên:

~~~java
// Một instance chia sẻ giữa nhiều request có thể bị đổi To/Subject lẫn nhau.
private final SimpleMailMessage shared = new SimpleMailMessage();

public void send(String recipient, String subject) {
    shared.setTo(recipient);
    shared.setSubject(subject);
    sender.send(shared);
}
~~~

Thay vào đó:

~~~java
public void send(String recipient, String subject) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("no-reply@example.com");
    mail.setTo(recipient);
    mail.setSubject(subject);
    mail.setText("Nội dung thông báo.");
    sender.send(mail);
}
~~~

Nếu cần tái sử dụng trường chung, `SimpleMailMessage` còn hỗ trợ copy constructor: tạo một đối tượng mẫu ổn định rồi sinh **bản sao mới** cho mỗi lần gửi. Tránh thay đổi đối tượng mẫu song song với các lần sao chép.

### 12.2. Một message có nhiều recipient khác với nhiều message

~~~java
// Một message; các người nhận chính có thể thấy nhau:
mail.setTo("alice@example.net", "bob@example.net");
sender.send(mail);
~~~

So với:

~~~java
SimpleMailMessage alice = new SimpleMailMessage();
alice.setFrom("no-reply@example.com");
alice.setTo("alice@example.net");
alice.setSubject("Thông báo cho Alice");
alice.setText("Xin chào Alice.");

SimpleMailMessage bob = new SimpleMailMessage();
bob.setFrom("no-reply@example.com");
bob.setTo("bob@example.net");
bob.setSubject("Thông báo cho Bob");
bob.setText("Xin chào Bob.");

sender.send(alice, bob);
~~~

Lời gọi gửi nhiều `SimpleMailMessage` là một tiện ích API, **không phải transaction** đảm bảo hai thư cùng thành công hoặc cùng thất bại. Hệ thống quan trọng phải quản lý kết quả và retry theo từng yêu cầu.

## 13. Khi nào cần chuyển sang `MimeMessageHelper`?

`SimpleMailMessage` cung cấp trực tiếp năm trường đang học và nội dung text. Tuy nhiên, nếu cần **tên hiển thị với encoding tùy chọn**, nội dung HTML, file đính kèm, hình ảnh hoặc header phức tạp, hãy dùng `MimeMessage` với `MimeMessageHelper`.

Ví dụ tương đương cho thư HTML:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");

helper.setFrom("orders@example.com", "Bộ phận đơn hàng");
helper.setTo("customer@example.net");
helper.setCc("account-manager@example.com");
helper.setBcc("audit@example.com");
helper.setSubject("Đơn hàng A123 đã được xác nhận");
helper.setText(
    "<html><body><h1>Xác nhận đơn hàng</h1></body></html>",
    true
);

mailSender.send(mime);
~~~

`MimeMessageHelper` vẫn có các thao tác đặt From/To/Cc/Bcc/Subject tương tự, nhưng làm việc với thông điệp MIME của Jakarta Mail. Ví dụ trên có thể phát sinh `MessagingException` hoặc ngoại lệ encoding từ các phương thức liên quan; code thực tế cần khai báo/giải quyết theo chữ ký API và chính sách xử lý lỗi của ứng dụng.

Với thư đơn giản chỉ có text, không cần thay đổi sang MIME chỉ vì có Cc hoặc Bcc. `SimpleMailMessage` đã hỗ trợ hai trường này.

## 14. Tình huống tổng hợp: chọn đúng người nhận cho một thông báo

Giả sử một doanh nghiệp có ứng dụng gửi **thông báo xác nhận đặt dịch vụ**. Người cần nhận gồm khách hàng, nhân viên phụ trách hồ sơ và một nhóm lưu trữ nội bộ.

Mẫu mong muốn:

~~~text
From: bookings@example.com
To: customer@example.net
Cc: account-manager@example.com
Subject: Xác nhận lịch đặt BK-2048

Xin chào,

Lịch đặt BK-2048 đã được xác nhận.
Vui lòng liên hệ bộ phận hỗ trợ nếu cần thay đổi.
~~~

Một bản sao kín có thể được gửi tới `archive@example.com` nếu có yêu cầu nghiệp vụ được phê duyệt; địa chỉ này không cần xuất hiện ở To/Cc header mà khách nhìn thấy.

Ứng dụng có thể thực hiện:

1. **Lấy người nhận** từ thông tin đặt dịch vụ, bảo đảm địa chỉ thuộc đúng khách hàng.
2. **Chọn From** từ cấu hình domain đã được phép gửi qua provider.
3. **Chọn Cc** cho nhân viên thực sự cần tham gia trao đổi; nếu không có, không đặt.
4. **Chỉ thêm Bcc** khi có quy định rõ về mục đích và quyền truy cập.
5. **Tạo Subject** chứa mã đặt dịch vụ không nhạy cảm, rõ ràng với người nhận.
6. **Tạo `SimpleMailMessage` mới**, đặt nội dung text và gửi qua `JavaMailSender`.
7. **Ghi nhận thao tác nộp thư** và theo dõi trạng thái riêng nếu cần xác minh giao thư hoặc xử lý thất bại.

Điểm quan trọng của bài không chỉ là nhớ tên các setter. Khi dùng đúng `From`, `To`, `Cc`, `Bcc` và `Subject`, bạn đang mô tả **danh tính thư, phạm vi chia sẻ và ngữ cảnh người nhận**. Chọn trường chính xác giúp module gửi mail dễ dùng hơn, giảm lộ địa chỉ không cần thiết và làm rõ trách nhiệm của từng người tham gia trao đổi.

### Tài liệu tra cứu

- **Spring Framework API — `SimpleMailMessage`:** `setFrom`, `setTo`, `setCc`, `setBcc`, `setSubject`, `setText` và các getter tương ứng.
- **Spring Framework API — `MailSender` và `JavaMailSender`:** gửi đối tượng email từ application service.
- **Spring Framework API — `MimeMessageHelper`:** tạo MIME message có header, tên hiển thị, HTML và attachment.
- **RFC 5322 — Internet Message Format:** vai trò các trường header như `From`, `To`, `Cc`, `Bcc` và `Subject`.
- **RFC 5321 — Simple Mail Transfer Protocol:** phân biệt message header với SMTP envelope và người nhận thực tế khi vận chuyển.
