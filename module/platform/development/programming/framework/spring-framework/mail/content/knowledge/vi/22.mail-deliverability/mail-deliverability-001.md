# Envelope sender và địa chỉ nhận bounce

## 1. Envelope sender là gì và vì sao ảnh hưởng đến deliverability?

Khi xây dựng chức năng gửi email bằng **Spring Framework Mail**, chúng ta thường bắt đầu bằng cách gọi **MimeMessageHelper.setFrom(...)**, đặt **To**, **Subject**, nội dung text hoặc HTML rồi gọi **JavaMailSender.send(...)**. Tuy nhiên, địa chỉ **From** hiển thị trong email không nhất thiết là địa chỉ mà hệ thống mail dùng để trả lại thông báo không chuyển phát được.

SMTP có hai lớp thông tin cần phân biệt:

- **SMTP envelope**: dữ liệu giao tiếp giữa các SMTP server, bao gồm địa chỉ gửi ở lệnh **MAIL FROM** (còn gọi là **reverse-path**, **envelope sender**) và các địa chỉ nhận ở lệnh **RCPT TO**.
- **Message headers**: các header bên trong nội dung email theo định dạng thông điệp, gồm **From**, **Sender**, **Reply-To**, **To**, **Cc**, **Subject** và những header khác.

**Envelope sender** chủ yếu chỉ định nơi nhận thông báo về lỗi chuyển phát sau khi email đã được server tiếp nhận. Địa chỉ đó thường được dùng làm **địa chỉ nhận bounce**, giúp hệ thống phát hiện recipient không tồn tại, mailbox đầy, domain nhận không phản hồi hoặc những lỗi chuyển phát khác.

Ví dụ:

~~~text
Ứng dụng Spring
  |
  | SMTP envelope:
  |   MAIL FROM:<bounce+order-981@bounces.example.com>
  |   RCPT TO:<customer@recipient.example>
  |
  | Nội dung email:
  |   From: Example Shop <notifications@example.com>
  |   Reply-To: support@example.com
  |   To: customer@recipient.example
  |   Subject: Đơn hàng đã được gửi đi
  v
SMTP provider -> mạng email -> mailbox
  |
  +-- Thành công: thư tiếp tục được chuyển phát
  |
  +-- Không chuyển phát được:
           |
           v
      Bounce / DSN gửi về
      bounce+order-981@bounces.example.com
~~~

Ở đây, **notifications@example.com** là địa chỉ người nhận nhìn thấy trong From, còn **bounce+order-981@bounces.example.com** là địa chỉ kỹ thuật trong SMTP envelope.

Một hệ thống gửi mail đáng tin cậy không chỉ quan tâm việc nộp thư thành công. Nó còn cần quản lý địa chỉ nhận bounce, phản hồi bất đồng bộ và các yếu tố xác thực domain để duy trì chất lượng danh sách recipient.

## 2. Các địa chỉ dễ bị nhầm với nhau

Một thông điệp email có thể chứa nhiều loại địa chỉ khác nhau, mỗi loại phục vụ mục đích riêng:

| Thành phần | Nằm ở đâu? | Vai trò |
|---|---|---|
| **SMTP MAIL FROM** | SMTP envelope | Reverse-path; đích nhận thông báo lỗi chuyển phát về sau |
| **SMTP RCPT TO** | SMTP envelope | Recipient mà SMTP server được yêu cầu chuyển phát tới |
| **From** | Header trong MIME message | Địa chỉ tác giả/người gửi mà email client hiển thị |
| **Sender** | Header trong MIME message | Tác nhân gửi thay mặt tác giả, khi cần phân biệt |
| **Reply-To** | Header trong MIME message | Địa chỉ nhận phản hồi do người dùng bấm Reply |
| **Return-Path** | Header thường được thêm khi giao thư | Ghi lại reverse-path SMTP tại một điểm giao thư |
| **To / Cc** | Header trong MIME message | Danh sách người nhận được trình bày trong email |
| **Bcc** | Địa chỉ người nhận của ứng dụng/SMTP, không lộ như To/Cc | Gửi kín cho người nhận bổ sung |

Phân biệt ba câu hỏi:

1. **Ai là người gửi được hiển thị?** — xem header **From**.
2. **Người nhận bấm Reply sẽ trả lời về đâu?** — xem **Reply-To** khi có, nếu không thường là From.
3. **Thông báo lỗi chuyển phát sẽ quay về đâu?** — xem **SMTP MAIL FROM** của chặng gửi, thường được phản ánh ở **Return-Path** của email đã giao.

Đừng dùng Reply-To như một cơ chế thu bounce. Mailbox nhận phản hồi của con người và nơi xử lý lỗi chuyển phát tự động thường có trách nhiệm rất khác nhau.

## 3. Ví dụ SMTP conversation: envelope không nằm trong body

Một phiên SMTP được giản lược có dạng:

~~~smtp
S: 220 smtp.provider.example ESMTP ready
C: EHLO application.example.com
S: 250-smtp.provider.example
S: 250 SIZE 52428800
C: MAIL FROM:<bounce+evt-789@bounces.example.com>
S: 250 2.1.0 Sender OK
C: RCPT TO:<person@recipient.example>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: Example Shop <notifications@example.com>
C: To: person@recipient.example
C: Reply-To: support@example.com
C: Subject: Xác nhận đặt hàng
C:
C: Đơn hàng của bạn đã được ghi nhận.
C: .
S: 250 2.0.0 Message accepted for delivery
~~~

Phần trên chỉ minh họa trình tự giao thức. Khi gửi thực tế, kết nối cần TLS và MIME header không ASCII phải được encode phù hợp. **MAIL FROM** và **RCPT TO** là lệnh SMTP, không phải dòng tiêu đề thông thường trong nội dung DATA.

Một điểm rất quan trọng:

**SMTP trả 250 cho DATA không có nghĩa email đã được giao vào Inbox.** Phản hồi đó thường chỉ có nghĩa server hiện tại đã tiếp nhận trách nhiệm xử lý tiếp. Nếu các chặng sau không chuyển phát được, có thể xuất hiện thông báo lỗi bất đồng bộ gửi tới reverse-path.

## 4. Envelope sender và RFC 5322 From là hai danh tính khác nhau

Tên **MAIL FROM** khá dễ gây hiểu nhầm vì nó trông giống header **From**. Tuy nhiên:

- **RFC 5321 MAIL FROM**: thuộc giao thức SMTP và đường trả lại lỗi chuyển phát. Thuật ngữ thường dùng là **RFC5321.MailFrom**.
- **RFC 5322 From**: thuộc nội dung thông điệp và biểu thị tác giả của email. Thuật ngữ thường dùng là **RFC5322.From**.

Ví dụ:

~~~text
RFC5321.MailFrom:
  bounce+abc123@bounces.example.com

RFC5322.From:
  Example Shop <receipts@example.com>

RFC5322.Reply-To:
  customer-care@example.com
~~~

Đây là một cấu hình hợp lý: người dùng nhìn thấy **Example Shop**, trả lời về bộ phận chăm sóc khách hàng, còn thông báo lỗi chuyển phát được hệ thống xử lý tại một subdomain dành cho bounce.

Không nên yêu cầu người mua trả lời địa chỉ **bounce+abc123@...**. Những địa chỉ bounce thường được xử lý bằng phần mềm hoặc bởi dịch vụ SMTP provider, không phải hộp thư có nhân viên đọc.

## 5. Return-Path: dấu vết của envelope sender

Khi một email được chuyển phát đến mailbox, bạn có thể thấy header như:

~~~text
Return-Path: <bounce+abc123@bounces.example.com>
From: Example Shop <receipts@example.com>
Reply-To: support@example.com
To: customer@recipient.example
~~~

**Return-Path** là header được dùng để ghi lại reverse-path của thông điệp khi giao thư theo quy tắc SMTP. Thông thường, **mail server ở giai đoạn giao thư cuối** sẽ thêm Return-Path dựa trên SMTP envelope mà nó nhận.

Điều đó dẫn tới hai hệ quả:

1. Return-Path có thể giúp người vận hành quan sát envelope sender của một chặng gửi, nhưng trong hệ thống có relay hoặc forwarding, giá trị nhìn thấy có thể phản ánh các thay đổi trên đường đi.
2. **Tự gán một header Return-Path trong MimeMessage không phải cách đáng tin cậy để điều khiển SMTP MAIL FROM.** Header có thể bị bỏ qua, thay thế hoặc xử lý khác bởi transport/server.

Trong Spring Mail, hãy cấu hình **envelope sender ở tầng SMTP transport/provider**. Khi kiểm tra kết quả, dùng thông tin MAIL FROM từ log SMTP/provider và Return-Path của bản email đã giao làm các tín hiệu đối chiếu.

### Ví dụ cấu hình sai về mặt ý tưởng

~~~java
// Không nên kỳ vọng lệnh sau tự thay đổi SMTP MAIL FROM.
message.setHeader(
        "Return-Path",
        "<bounces@example.com>"
);
~~~

Lời gọi trên chỉ thao tác với **message header**, không bảo đảm SMTP client dùng địa chỉ đó trong lệnh MAIL FROM.

## 6. Bounce là gì?

**Bounce** thường chỉ một thông báo cho biết email không thể được chuyển phát hoặc gặp vấn đề khi giao. Trong hệ thống SMTP, các báo cáo chuẩn thường gọi là **Delivery Status Notification (DSN)**; trong thực tế nhà cung cấp email cũng có thể cung cấp **bounce event** qua API hoặc webhook.

Các trường hợp thường gặp:

- Địa chỉ recipient không tồn tại.
- Mailbox của người nhận không thể nhận thêm thư.
- Domain nhận gặp sự cố tạm thời kéo dài.
- Email bị từ chối bởi chính sách anti-spam, authentication hoặc reputation.
- Server đích không thể nhận được thư trong thời hạn retry.
- Nội dung hoặc kích thước không phù hợp chính sách của phía nhận.

Bounce giúp người gửi quyết định có nên tiếp tục gửi cho recipient đó hay không, nhưng nó **không phải một cơ chế xác nhận delivery toàn diện**. Không nhận được bounce không chứng minh thư đã vào Inbox; không phải mọi hệ thống nhận đều phát DSN theo cùng cách.

## 7. Bounce bất đồng bộ khác lỗi SMTP ngay khi gửi

Giả sử Spring gọi:

~~~java
mailSender.send(mimeMessage);
~~~

Có ít nhất hai nhóm kết quả cần phân biệt:

### A. SMTP server từ chối khi ứng dụng đang nộp email

~~~text
Spring / SMTP client           Submission server
         |                           |
         | RCPT TO:<bad@example> --->|
         |<------- 550 rejected -----|
         |
    JavaMailSender có thể ném MailException
~~~

Lỗi này xảy ra **trong cùng phiên gửi**. Ứng dụng có thể bắt ngoại lệ Spring Mail, phân tích phản hồi SMTP hoặc trạng thái recipient nếu provider hỗ trợ.

### B. Server đã nhận email, nhưng chặng sau thất bại

~~~text
Spring application       Submission server      Receiving server
       |                         |                      |
       | DATA ------------------>|                      |
       |<----- 250 accepted -----|                      |
       |                         | ---- relay --------> |
       |                         | <---- failure -------|
       |                         |                      |
       |     DSN / bounce event  |                      |
       |<------------------------|                      |
~~~

Lần gọi **send(...)** ban đầu có thể đã thành công. Vài giây hoặc vài giờ sau mới có bounce. Vì vậy, không thể dùng **try/catch MailSendException** làm giải pháp duy nhất để thu bounce.

Một hệ thống deliverability cần cả:

- **Submission result**: kết quả ứng dụng nộp thư ở chặng đầu.
- **Asynchronous delivery feedback**: DSN, bounce event, webhook hoặc dashboard từ SMTP provider.

## 8. Hard bounce, soft bounce và các trạng thái trung gian

Nhiều ESP phân biệt:

| Nhóm thông dụng | Ví dụ | Hành động tham khảo |
|---|---|---|
| **Hard bounce** | Recipient không tồn tại, địa chỉ sai vĩnh viễn | Suppress/không gửi tiếp tới địa chỉ đó cho đến khi được sửa hoặc xác minh |
| **Soft bounce** | Mailbox đầy, server nhận tạm thời bận | Retry theo chính sách có giới hạn |
| **Policy rejection** | Chống spam, sender reputation hoặc yêu cầu authentication | Điều tra nguyên nhân trước khi tiếp tục |
| **Deferred** | Server hoãn tiếp nhận hoặc chuyển phát | Theo dõi thời gian chờ và kết quả cuối |
| **Unknown** | Không đủ dữ liệu để xác định tình trạng | Giữ trạng thái chưa rõ, không suy diễn thành delivered |

Thuật ngữ **hard** và **soft** là các nhãn vận hành, không phải lúc nào cũng ánh xạ một-một với mã SMTP:

- Mã 4xx thường báo lỗi tạm thời ở lệnh hiện tại, nhưng một email có thể bị hoãn nhiều lần rồi cuối cùng chuyển thành thất bại vĩnh viễn.
- Mã 5xx thường báo từ chối vĩnh viễn ở lệnh hiện tại, nhưng nguyên nhân có thể là chính sách, dung lượng, định tuyến hay authentication, không chỉ địa chỉ không tồn tại.
- Một provider có thể quy định loại bounce riêng bằng metadata và enhanced status code.

Phải dùng **nguồn kết quả đáng tin cậy và ngữ cảnh của từng provider** để quyết định suppression hoặc replay. Không chỉ tìm chuỗi “550” trong body rồi xóa địa chỉ người nhận.

## 9. Vì sao tách địa chỉ bounce khỏi From và Reply-To?

Có ba mục tiêu khác nhau:

**Trải nghiệm người dùng.** From nên đại diện đúng thương hiệu hoặc dịch vụ; Reply-To đưa phản hồi đến bộ phận có thể trả lời.

**Vận hành email.** Bounce cần được xử lý tự động bằng hệ thống theo dõi notification, ghi nguyên nhân và cập nhật trạng thái recipient. Nếu dồn mọi bounce vào mailbox hỗ trợ khách hàng, việc lọc và đối chiếu sẽ khó khăn.

**Bảo mật và dữ liệu.** Một địa chỉ bounce có thể chứa token hoặc identifier kỹ thuật; không nên dùng làm địa chỉ giao tiếp với khách hàng. Một domain/subdomain riêng cũng giúp quản lý DNS và quyền của provider.

Mô hình:

~~~text
Header From:
    invoices@example.com
    -> địa chỉ nhận diện thương hiệu

Header Reply-To:
    support@example.com
    -> xử lý phản hồi của con người

SMTP MAIL FROM:
    bounce+event-42@bounces.example.com
    -> hệ thống thu bounce/DSN
~~~

Tên domain ở đây chỉ là ví dụ. Thiết kế thực tế còn phụ thuộc provider có hỗ trợ cấu hình custom MAIL FROM hoặc custom bounce domain hay không.

## 10. Cấu hình envelope sender trong Spring Boot

Khi sử dụng Spring Boot với **spring-boot-starter-mail**, có thể truyền thuộc tính của Jakarta Mail SMTP transport thông qua **spring.mail.properties**.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          from: bounces@bounces.example.com
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Trong cấu hình Spring Boot này:

- **spring.mail.host / port**: server SMTP mà ứng dụng kết nối tới.
- **spring.mail.username / password**: credential do provider cấp, không nên lưu trực tiếp trong source code.
- **spring.mail.properties.mail.smtp.from**: thuộc tính SMTP transport của Jakarta Mail, dùng để chọn **envelope sender** cho các message gửi bằng session/transport tương ứng.
- **starttls.enable + starttls.required**: bật và yêu cầu nâng cấp TLS.
- **ssl.checkserveridentity**: kiểm tra chứng chỉ TLS theo tên máy chủ.
- **connectiontimeout, timeout, writetimeout**: timeout kết nối, đọc và ghi tính theo mili giây.

Khi Spring Boot ánh xạ nested YAML vào các mail properties, khóa **mail.smtp.from** là khóa cần truyền xuống transport. Đừng nhầm với:

~~~yaml
spring:
  mail:
    from: something@example.com
~~~

Thuộc tính **spring.mail.from** không phải property chuẩn để đặt SMTP envelope sender trong cấu hình Mail của Spring Boot. Tương tự, **helper.setFrom(...)** không có cùng ý nghĩa với **mail.smtp.from**.

### Phân biệt giá trị trong code và cấu hình

~~~text
MimeMessageHelper.setFrom("orders@example.com")
    -> Header From hiển thị trong thư

mail.smtp.from=bounces@bounces.example.com
    -> SMTP MAIL FROM cho transport này
~~~

**Lưu ý quan trọng:** nhà cung cấp SMTP có thể kiểm tra, hạn chế, viết lại hoặc bỏ qua envelope sender do client yêu cầu. Một số ESP quản lý MAIL FROM và bounce domain bằng cấu hình tài khoản/domain đã xác minh thay vì cho client tùy ý đặt. Vì vậy cần kiểm tra tài liệu provider, message trace và giá trị MAIL FROM thực tế sau submission.

## 11. Gửi email với From và Reply-To rõ ràng

Sau khi cấu hình envelope sender ở tầng SMTP transport, code tạo thông điệp có thể giữ nguyên các header phù hợp với người nhận:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {

    private final JavaMailSender mailSender;

    public OrderEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(
            String recipient,
            String orderCode
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject("Cập nhật đơn hàng " + orderCode);

        helper.setText(
                "Đơn hàng " + orderCode + " đã được cập nhật.",
                false
        );

        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

- **orders@example.com** xuất hiện trong header From.
- **support@example.com** nhận những phản hồi của người dùng khi họ bấm Reply.
- **bounces@bounces.example.com** từ cấu hình **mail.smtp.from** là reverse-path được transport yêu cầu.
- **recipient** là người nhận được xác định bởi quy tắc nghiệp vụ.

Ví dụ chỉ gửi plain text để dễ quan sát địa chỉ. Có thể thay bằng HTML hoặc **MimeMessageHelper.setText(plainText, htmlText)** mà không cần thay đổi nguyên tắc envelope sender.

Địa chỉ và hostname dùng trong ví dụ phải được thay bằng domain/credential đã xác minh và cho phép gửi trong môi trường thực.

## 12. Cấu hình JavaMailSenderImpl thủ công

Trong ứng dụng Spring Framework thuần hoặc khi muốn tự cấu hình sender, có thể tạo bean **JavaMailSenderImpl**:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class EmailTransportConfiguration {

    @Bean
    public JavaMailSender mailSender(MailAccountProperties config) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(config.smtpHost());
        sender.setPort(587);
        sender.setUsername(config.username());
        sender.setPassword(config.password());
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.from", "bounces@bounces.example.com");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

**MailAccountProperties** là abstraction của ứng dụng cho host và credential, không phải class mặc định của Spring. Credential cần được cấp qua cấu hình được bảo vệ hoặc secret manager. Việc cấu hình **mail.smtp.from** là yêu cầu gửi envelope sender tới SMTP transport, không phải cam kết provider chấp nhận địa chỉ đó.

### Điều gì xảy ra khi không cấu hình mail.smtp.from?

Jakarta Mail SMTP transport có cơ chế chọn MAIL FROM từ message/session và môi trường theo implementation. Trong nhiều cấu hình, nó có thể dùng địa chỉ ở header From hoặc một địa chỉ cục bộ suy ra từ session nếu không có envelope sender được chỉ định.

Không nên dựa vào giá trị suy ra nếu ứng dụng cần **bounce domain xác định, SPF alignment hoặc correlation**. Hãy cấu hình rõ ràng và kiểm tra kết quả với SMTP provider.

## 13. Envelope sender dùng chung hay riêng cho từng thông báo?

**mail.smtp.from** là property của SMTP transport/session. Nếu một **JavaMailSenderImpl** được chia sẻ, đặt property này thành một giá trị cố định sẽ khiến nhiều message dùng cùng envelope sender.

Ví dụ:

~~~text
Một JavaMailSender
  mail.smtp.from = bounces@bounces.example.com

Notification A -> MAIL FROM bounces@bounces.example.com
Notification B -> MAIL FROM bounces@bounces.example.com
Notification C -> MAIL FROM bounces@bounces.example.com
~~~

Cách này có thể đủ khi ESP cung cấp webhook chứa message ID để đối chiếu bounce, hoặc mailbox nhận bounce được parser xử lý theo thông tin có sẵn.

Nếu cần **mỗi notification một địa chỉ bounce riêng**, không nên thay đổi động một property của **JavaMailSenderImpl** singleton ngay trước mỗi lần gửi:

~~~java
// Anti-pattern khi nhiều luồng dùng cùng JavaMailSenderImpl.
sender.getJavaMailProperties().put(
        "mail.smtp.from",
        "bounce+" + notificationId + "@bounces.example.com"
);
sender.send(message);
~~~

Hai thread có thể thay property lẫn nhau và gửi với envelope sender của notification khác. Nó cũng khiến việc kiểm thử và audit khó khăn.

Các lựa chọn đúng hơn:

1. Dùng **cơ chế per-message envelope sender của SMTP provider/transport** nếu implementation hỗ trợ.
2. Dùng **API sending của ESP** với return-path/bounce identity hoặc metadata đã được provider hỗ trợ chính thức.
3. Dùng các **JavaMailSender** tách biệt cho những domain hoặc stream có envelope sender cố định.
4. Nếu cần cấp sender riêng cho mỗi job, thiết kế vòng đời session/transport rõ ràng và quản lý tài nguyên, không chia sẻ một cấu hình mutable tùy tiện.

Một số implementation SMTP của Jakarta Mail cung cấp class **SMTPMessage** hoặc API riêng để đặt envelope sender cho từng message. Đây là **API phụ thuộc implementation**, không phải phương thức chung của **MimeMessageHelper** hay **JavaMailSender**. Tên package và khả năng hỗ trợ cần xác nhận theo Jakarta Mail provider đang dùng.

## 14. Địa chỉ bounce và SPF

**SPF (Sender Policy Framework)** là một cơ chế giúp receiver kiểm tra xem IP/host đang gửi có được domain ủy quyền hay không theo chính sách SPF.

Đối với email thông thường có reverse-path không rỗng, danh tính SPF được kiểm tra dựa trên **domain của RFC5321.MailFrom**. Khi reverse-path rỗng (ví dụ DSN), cơ chế SPF có thể chuyển sang danh tính HELO/EHLO theo quy tắc SPF.

Ví dụ:

~~~text
RFC5322.From:
  receipts@example.com

RFC5321.MailFrom:
  bounces@bounces.example.com

Connecting SMTP IP:
  192.0.2.25
~~~

Receiver có thể kiểm tra SPF của **bounces.example.com** để xác định IP được phép gửi. Địa chỉ **192.0.2.25** là IP dành cho tài liệu minh họa.

### SPF phải phù hợp với domain MAIL FROM đang dùng

Nếu ESP gửi mail với envelope sender thuộc **bounces.example.com**, cần bảo đảm SPF/DNS của domain đó được cấu hình theo hướng dẫn của ESP. Ví dụ minh họa cấu trúc TXT SPF:

~~~dns
bounces.example.com. IN TXT "v=spf1 include:_spf.provider.example -all"
~~~

Giá trị **_spf.provider.example** chỉ là placeholder. Không sao chép TXT record này lên DNS thật nếu không có chỉ dẫn xác minh từ provider. Một số ESP dùng cơ chế CNAME, MX hoặc cấu hình domain riêng; hãy tuân thủ chính xác yêu cầu của hệ thống đang sử dụng.

Lưu ý: **SPF pass chỉ nói về ủy quyền của domain được kiểm tra**, không tự bảo đảm email vượt qua DMARC hoặc vào Inbox.

## 15. Envelope sender, DKIM và DMARC alignment

**DMARC** kiểm tra mối quan hệ giữa **From hiển thị** (RFC5322.From) với các danh tính đã được xác thực qua SPF và/hoặc DKIM. Một message có thể đạt DMARC khi có ít nhất một trong hai cơ chế **SPF hoặc DKIM** vừa pass vừa có domain **aligned** với From theo chế độ alignment được cấu hình.

Ví dụ:

~~~text
Header From:
  notifications@example.com

Envelope MAIL FROM:
  bounce+id@bounces.example.com

DKIM signature:
  d=example.com
~~~

Trong chế độ **relaxed alignment**, **bounces.example.com** và **example.com** thường chia sẻ cùng organizational domain, vì vậy SPF identity có thể aligned với From nếu SPF pass và các điều kiện khác được đáp ứng. Nếu DMARC được cấu hình **strict SPF alignment**, hai domain không giống hệt có thể không aligned.

DKIM với **d=example.com** có thể aligned với **From: notifications@example.com** khi chữ ký hợp lệ. Vì thế:

- Đừng nghĩ **SPF pass = DMARC pass** trong mọi trường hợp.
- Đừng nghĩ **Return-Path phải có email address giống hệt header From** mới gửi được.
- Đừng mặc định ESP đang ký DKIM bằng domain của thương hiệu; phải xác minh **d=** thực tế.
- Khi dùng nhiều domain thương hiệu hoặc tenant, cần xem alignment theo từng domain.

### Ví dụ mismatch

~~~text
Header From: invoices@example.com
MAIL FROM: bounce@provider-mail.example.net
SPF: pass cho provider-mail.example.net
DKIM: chữ ký d=provider-mail.example.net
~~~

Nếu cả SPF và DKIM chỉ được xác thực dưới **provider-mail.example.net** mà không aligned với **example.com**, DMARC có thể fail dù SPF kiểm tra IP gửi đã pass. Cách giải quyết có thể là **custom MAIL FROM domain được xác minh**, **aligned DKIM signing domain**, hoặc cả hai theo chính sách ESP.

Trong vận hành, nên xem cả **Authentication-Results**, **Return-Path** và **DKIM-Signature** từ một email thử đã giao để hiểu danh tính thực tế.

## 16. Thiết kế domain hoặc subdomain riêng cho bounce

Một kiến trúc hay gặp là dùng domain chính cho header From và một subdomain để làm reverse-path:

~~~text
Thương hiệu:
  example.com

Header From:
  notifications@example.com

Bounce domain:
  bounces.example.com

SMTP MAIL FROM:
  bounce+event123@bounces.example.com
~~~

Cách tổ chức này giúp:

- Giữ địa chỉ From rõ ràng cho người nhận.
- Tách luồng thông báo lỗi chuyển phát khỏi mailbox hỗ trợ khách hàng.
- Cấu hình DNS và quyền ESP dành riêng cho bounce.
- Có khả năng dùng mã tương quan (correlation token) trong local-part của envelope sender.
- Duy trì khả năng SPF alignment với domain From trong cấu hình DMARC relaxed nếu các điều kiện được đáp ứng.

Tuy nhiên, một subdomain mới **không tự hoạt động như nơi nhận bounce**. Cần có hạ tầng nhận email/DSN hoặc provider đứng ra xử lý.

### Những thành phần cần xác định trước

1. **SMTP provider có cho custom MAIL FROM không?** Một số provider bắt buộc dùng return-path thuộc domain riêng của họ.
2. **Provider nhận bounce thay ứng dụng hay không?** Nếu có, thường có event webhook/API hoặc dashboard.
3. **DNS nào cần cấu hình?** Có thể gồm SPF TXT, MX, CNAME hoặc bản ghi xác minh do provider quy định.
4. **Hệ thống đối chiếu bounce thế nào?** Dựa vào provider message ID, notification metadata hoặc địa chỉ VERP.
5. **Địa chỉ bounce có nhận thư được không?** Việc SPF pass không có nghĩa domain có một mailbox nhận DSN.
6. **Có bảo vệ webhook và quyền truy cập log không?** Bounce event chứa địa chỉ email và thông tin chuyển phát.

Đừng tự thêm MX record cho một server không có dịch vụ nhận thư. Ngược lại, đừng xóa MX của bounce subdomain nếu provider yêu cầu MX để tiếp nhận phản hồi. Cấu hình chính xác phụ thuộc hợp đồng dịch vụ đang dùng.

## 17. MX cho bounce và sự khác nhau giữa gửi/nhận

SPF và MX giải quyết các nhu cầu khác nhau:

| Thành phần | Vai trò |
|---|---|
| **SPF TXT trên MAIL FROM domain** | Cho phép receiver kiểm tra ủy quyền IP/host gửi |
| **MX trên bounce domain** | Xác định mail server có thể nhận thư gửi về domain bounce |
| **DKIM signing domain** | Cho phép receiver xác minh chữ ký thông điệp |
| **Webhook của ESP** | Chuyển sự kiện bounce/delivery cho ứng dụng theo giao thức API |

Một sơ đồ minh họa khi **ứng dụng tự nhận DSN qua mailbox**:

~~~text
Outbound:
  Spring -> SMTP provider
      MAIL FROM:<bounce+N100@bounces.example.com>
                   |
                   v
         Mail recipient domain

Nếu phát sinh DSN:
  Receiving MTA
      |
      | DNS MX lookup: bounces.example.com
      v
  Inbound mail server cho bounces.example.com
      |
      v
  DSN parser -> notification N100
~~~

Trong một mô hình **ESP-managed bounce**, ứng dụng có thể không nhận trực tiếp DSN vào mailbox. ESP nhận và xử lý sự kiện, sau đó gửi webhook hoặc cung cấp API để ứng dụng lấy kết quả:

~~~text
Spring -> ESP SMTP
            |
            v
       Recipient MTA
            |
         bounce event
            |
            v
          ESP
            |
          webhook
            |
            v
  Application bounce endpoint
~~~

Hai mô hình đều có thể hữu ích; hãy chọn theo khả năng ESP và yêu cầu vận hành. Không nên triển khai thêm inbound SMTP server nếu provider đã cung cấp một cơ chế bounce được xác thực và đầy đủ cho nhu cầu ứng dụng.

## 18. VERP: địa chỉ trả về có thể mang mã tương quan

**VERP (Variable Envelope Return Path)** là kỹ thuật dùng envelope sender khác nhau để giúp xác định email hoặc recipient tương ứng với một bounce.

Ví dụ thay vì tất cả thư dùng:

~~~text
bounces@bounces.example.com
~~~

Ta dùng:

~~~text
bounce+N100@bounces.example.com
bounce+N101@bounces.example.com
bounce+N102@bounces.example.com
~~~

Trong đó **N100**, **N101**, **N102** là notification ID hoặc token được ánh xạ tới notification trong database.

Khi một bounce tới:

~~~text
bounce+N101@bounces.example.com
~~~

ứng dụng có thể tra record tương ứng để biết lần gửi liên quan. Đó là nguyên tắc của VERP; nó không mặc nhiên có sẵn trong **MimeMessageHelper**.

### Điều kiện để VERP hoạt động

- SMTP sender hoặc ESP phải hỗ trợ envelope sender riêng cho từng message hoặc cung cấp một cơ chế tương đương.
- Bounce domain/inbound route phải chấp nhận những địa chỉ phát sinh.
- Parser phải xác định token từ **envelope recipient nhận DSN** hoặc metadata đáng tin cậy, không chỉ từ đoạn text tự do.
- Cần biết một thông điệp có nhiều recipient được gắn với token nào.
- Token phải có cơ chế tránh collision và không tiết lộ thông tin nhạy cảm.

**Plus addressing không phải cơ chế mà mọi máy chủ nhận đều hỗ trợ giống nhau.** Nếu dùng cú pháp **bounce+token@domain**, phải kiểm tra inbound server/ESP có route local-part đó đúng yêu cầu hay không.

### Không đưa dữ liệu cá nhân vào VERP

Tránh:

~~~text
bounce+customer-email-at-gmail.com@bounces.example.com
bounce+phone-0901234567@bounces.example.com
~~~

Các địa chỉ như vậy có thể lộ PII trong SMTP logs, header, DSN hoặc hệ thống giám sát. Nên dùng **ID ngẫu nhiên/opaque**, và nếu cần xác thực token, có thể dùng chữ ký/HMAC hoặc kiểm tra record tồn tại cùng quyền xử lý.

## 19. DSN chuẩn: thông điệp trả về trông như thế nào?

Một DSN theo định dạng MIME có thể dùng cấu trúc:

~~~text
Content-Type: multipart/report;
    report-type=delivery-status
    |
    +-- text/plain
    |      Diễn giải cho con người
    |
    +-- message/delivery-status
    |      Các trường trạng thái có cấu trúc
    |
    +-- message/rfc822-headers hoặc message/rfc822
           Thông tin bản gốc, nếu có
~~~

Trong phần **message/delivery-status**, có thể gặp những trường như:

~~~text
Reporting-MTA: dns; mx.receiver.example
Arrival-Date: Thu, 12 Nov 2026 08:00:00 +0000

Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Đây là ví dụ minh họa, không phải báo cáo thật. Một số trường là tùy chọn hoặc phụ thuộc server.

Các trường có ích:

| Trường | Ý nghĩa |
|---|---|
| **Reporting-MTA** | Hệ thống tạo báo cáo tình trạng |
| **Final-Recipient** | Recipient liên quan tới kết quả chuyển phát |
| **Original-Recipient** | Recipient gốc nếu được báo cáo |
| **Action** | Trạng thái như failed, delayed, delivered, relayed hoặc expanded |
| **Status** | Enhanced mail system status code |
| **Diagnostic-Code** | Chẩn đoán gốc, thường là phản hồi SMTP |
| **Original-Envelope-Id** | Định danh envelope nếu cơ chế DSN đã truyền và báo lại |

Không phải mọi bounce đều chứa đủ các trường. Một số ESP chuyển phản hồi thành event JSON riêng, có ý nghĩa tương đương nhưng không dùng nguyên vẹn định dạng MIME.

### Không phân loại bằng body text tự do

Ví dụ không nên dựa hoàn toàn vào:

~~~java
if (bounceText.contains("user unknown")) {
    suppressRecipient();
}
~~~

Body DSN có thể đổi ngôn ngữ, nội dung hoặc cách diễn đạt, và một email giả mạo cũng có thể chứa chuỗi đó. Hãy ưu tiên **cấu trúc DSN được parser hiểu đúng**, **mã status đáng tin** hoặc **event từ ESP đã xác minh chữ ký**.

## 20. DSN và reverse-path rỗng: MAIL FROM:<>

Một DSN chính nó cũng là email. Nếu gửi DSN tới một địa chỉ không nhận được rồi lại sinh DSN khác, hai mail server có thể tạo vòng lặp báo lỗi.

Để tránh vòng lặp, thông báo lỗi chuyển phát được gửi với **null reverse-path**:

~~~smtp
MAIL FROM:<>
RCPT TO:<bounce+N100@bounces.example.com>
~~~

Ký hiệu **<>** ở đây có nghĩa reverse-path rỗng, **không phải địa chỉ email bị thiếu do cấu hình sai**. Khi một DSN như vậy không chuyển phát được, server không nên lại tạo một DSN khác để gửi về một reverse-path mới.

Trong email DSN đã được giao, Return-Path có thể thể hiện:

~~~text
Return-Path: <>
~~~

**Không nên tự cấu hình MAIL FROM rỗng cho email thông báo giao dịch bình thường** chỉ để tránh bounce. Làm vậy có thể gây khó quản lý lỗi và không phù hợp chính sách provider. Null reverse-path có mục đích đặc biệt trong giao thức báo lỗi.

## 21. Bounce khi email đi qua forwarder

Một người nhận có thể tự động forward thư từ mailbox A sang mailbox B. Điều này làm đường chuyển phát và xác thực domain phức tạp hơn:

~~~text
Spring -> ESP -> Mailbox A -> Forwarder -> Mailbox B
~~~

Tại chặng forward, một hệ thống có thể thay đổi reverse-path bằng **SRS (Sender Rewriting Scheme)** để hỗ trợ SPF khi forward. Vì vậy:

- Envelope sender/Return-Path ở chặng sau có thể khác với giá trị ứng dụng đặt ban đầu.
- SPF pass ở chặng forward không tự bảo đảm DMARC SPF alignment với From gốc.
- DKIM hợp lệ và aligned có thể giúp DMARC qua forward, nhưng chữ ký có thể bị phá nếu nội dung/header bị chỉnh sửa.
- Bounce có thể đi qua forwarder hoặc hệ thống trung gian và cần đối chiếu với ID gốc.

Không nên khẳng định một địa chỉ envelope sender nhất định sẽ xuất hiện nguyên vẹn ở mọi hop. Khi debug, xem message trace của ESP và Received/Authentication-Results headers, không chỉ một trường Return-Path ở mailbox cuối.

## 22. Khi nào bounce không về đến địa chỉ đã cấu hình?

Một số trường hợp:

- Provider tự thay đổi MAIL FROM sang domain bounce được quản lý.
- Hệ thống nhận từ chối message trong phiên SMTP trước khi chấp nhận, nên không có DSN bất đồng bộ.
- Chặng chuyển tiếp không phát DSN dù message gặp vấn đề, do policy hoặc sự cố.
- Bounce bị chặn bởi anti-spam, quota hoặc routing của domain bounce.
- ESP ghi nhận bounce trong dashboard/webhook thay vì gửi DSN đến hộp thư của ứng dụng.
- DNS hoặc mailbox của bounce subdomain không được cấu hình đúng.
- Một forwarder/relay đã thay đổi reverse-path.
- Recipient mailbox xử lý thư vào Spam hoặc quarantine mà không phát bounce.

Vì vậy, muốn biết địa chỉ bounce thực sự hoạt động, cần **kiểm tra theo một luồng gửi/nhận thử được kiểm soát**, không chỉ kiểm tra property trong Spring.

## 23. Xây dựng dữ liệu lưu trữ cho notification và bounce

Một hệ thống theo dõi deliverability có thể lưu những trường chính sau:

| Trường | Mục đích |
|---|---|
| **notification_id** | Định danh notification của ứng dụng |
| **business_event_id** | Event nghiệp vụ tạo notification |
| **recipient_id / recipient_ref** | Tham chiếu recipient |
| **recipient_email** | Email thực tế nếu cần và được phép lưu |
| **header_from** | From hiển thị đã sử dụng |
| **envelope_from_requested** | MAIL FROM ứng dụng yêu cầu |
| **envelope_from_actual** | MAIL FROM thực tế nếu provider cung cấp |
| **provider_message_id** | ID do ESP cấp để liên kết event |
| **message_id** | Message-ID header nếu có |
| **submission_status** | PENDING, SUBMITTED, RETRY, UNKNOWN... |
| **delivery_status** | DELIVERED, BOUNCED, DEFERRED, UNKNOWN... |
| **bounce_type / reason_code** | Nhóm bounce đã được chuẩn hóa |
| **smtp_status_code** | Mã chẩn đoán SMTP/enhanced status code |
| **attempt_count** | Số lần xử lý/gửi |
| **last_event_at** | Thời điểm event mới nhất |

Trong nhiều trường hợp không biết **envelope_from_actual**, hãy lưu **null/unknown** thay vì sao chép giá trị requested rồi coi là sự thật.

### Một notification có thể có nhiều event

~~~text
Notification N100
   |
   +-- 09:00 Submitted
   +-- 09:01 Deferred
   +-- 09:04 Deferred
   +-- 09:09 Delivered
~~~

Hoặc:

~~~text
Notification N101
   |
   +-- 09:00 Submitted
   +-- 09:08 Bounced (hard)
~~~

Không nên tạo trạng thái cuối chỉ bằng cách lấy event đầu tiên và bỏ qua các event tiếp theo. Cần xử lý thứ tự, loại event và chính sách của provider.

## 24. Xử lý bounce event qua webhook của ESP

Nếu provider hỗ trợ webhook cho bounce/delivery, ứng dụng có thể tách thành hai thành phần:

~~~text
                    SMTP submission
Spring mail worker ------------------------> ESP
      |                                       |
      | lưu notificationId, providerId        |
      v                                       |
Notification database                        |
                                              |
                                     Delivery / Bounce
                                              |
                                              v
                                      Webhook HTTPS
                                              |
                                              v
                                  Validate signature / source
                                              |
                                              v
                                    Persist provider event
                                              |
                                              v
                                  Resolve notification/recipient
                                              |
                                              v
                                  Update delivery + suppression
~~~

**Webhook là thông tin từ hệ thống bên ngoài**, không nên tin nội dung chỉ vì request tới đúng URL. Khi triển khai cần:

1. **Xác minh nguồn gửi** bằng phương thức mà ESP công bố: chữ ký, HMAC, cơ chế authentication hoặc mTLS nếu được hỗ trợ.
2. Xác minh trên **raw request body** nếu chữ ký của provider yêu cầu, trước khi biến đổi JSON.
3. Kiểm tra timestamp/nonce hoặc giới hạn replay khi provider có cơ chế tương ứng.
4. Kiểm tra event ID và loại event.
5. Đối chiếu provider message ID với notification đã tồn tại, đồng thời xác nhận recipient.
6. Lưu event một cách bền vững trước khi trả HTTP thành công nếu ứng dụng yêu cầu không mất event.
7. Xử lý lặp và sai thứ tự.
8. Không đưa địa chỉ từ payload chưa được xác minh vào danh sách suppression.

### Skeleton Spring MVC cho webhook

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MailDeliveryWebhookController {

    private final MailWebhookSignatureVerifier verifier;
    private final MailDeliveryEventInbox inbox;

    public MailDeliveryWebhookController(
            MailWebhookSignatureVerifier verifier,
            MailDeliveryEventInbox inbox
    ) {
        this.verifier = verifier;
        this.inbox = inbox;
    }

    @PostMapping(
            path = "/webhooks/mail/delivery",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Void> receive(
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        if (!verifier.isValid(headers, rawBody)) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .build();
        }

        // Persist event idempotently before acknowledging.
        inbox.persistIfNew(rawBody);

        return ResponseEntity.accepted().build();
    }
}
~~~

Đây là **skeleton kiến trúc**, không phải endpoint đã tích hợp với ESP cụ thể:

- **MailWebhookSignatureVerifier** phải hiện thực đúng cách ký/xác thực của provider đang sử dụng.
- **MailDeliveryEventInbox.persistIfNew(...)** phải parse/validate payload theo schema chính thức, lưu transaction bền vững và có unique constraint cho provider event ID.
- Endpoint cần kiểm soát kích thước request, rate limit và bảo mật ở tầng web.
- Không ghi raw body vào log.
- Trả 2xx khi event đã được lưu an toàn theo hợp đồng webhook; nếu lưu thất bại, phải dựa vào cơ chế retry của provider.

Không sử dụng địa chỉ webhook bất kỳ như một nguồn sự thật cho trạng thái bounce nếu chưa xác minh provider và notification tương ứng.

## 25. Idempotency và thứ tự event khi nhận bounce

Webhook thường có khả năng gửi lại event khi không nhận được HTTP success, khi mạng lỗi hoặc khi ESP retry. Vì vậy một event có thể đến nhiều lần.

Ví dụ:

~~~text
Provider event E456 (BOUNCED)
         |
         +--> Request #1 -> timeout ở phía provider
         |
         +--> Request #2 -> cùng event E456
~~~

Ứng dụng nên ghi nhận **event E456 một lần** ở tầng inbox:

~~~sql
CREATE TABLE mail_provider_event (
    provider_event_id VARCHAR(200) PRIMARY KEY,
    provider_message_id VARCHAR(200),
    event_type VARCHAR(50) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP
);
~~~

DDL chỉ minh họa. Trong hệ thống nhiều ESP có thể cần khóa ghép **provider + provider_event_id**, phân vùng theo tenant và lưu payload đã được kiểm soát để phục vụ điều tra.

Nếu không có event ID ổn định, cần một chiến lược dedup được provider hỗ trợ hoặc khóa nghiệp vụ phù hợp; không tự suy ra rằng hai sự kiện cùng loại/timestamp là một.

### Tránh ghi đè trạng thái do event đến sai thứ tự

~~~text
09:00 SUBMITTED
09:10 BOUNCED
09:11 Webhook DELIVERED của event cũ đến muộn
~~~

Không thể chỉ lấy webhook đến sau làm trạng thái mới nhất mà không kiểm tra event time, event type và semantics của provider. Có thể cần:

- Lưu lịch sử event bất biến.
- Ánh xạ event sang state transition hợp lệ.
- Dùng provider sequence hoặc timestamp có ý nghĩa khi được cung cấp.
- Giữ những trạng thái cần đối soát khi kết quả mâu thuẫn.

Không giả định mọi provider gửi webhook theo thứ tự phát sinh hoặc chỉ gửi đúng một lần.

## 26. Phân loại bounce để quyết định suppression

**Suppression list** là danh sách địa chỉ hoặc recipient không nên tiếp tục gửi theo một hoặc nhiều chính sách. Mục tiêu là giảm tỷ lệ gửi đến địa chỉ không hợp lệ, bảo vệ reputation và tránh làm phiền người nhận.

Một chính sách ví dụ:

| Tình huống | Hành động gợi ý |
|---|---|
| User unknown được xác nhận, lỗi vĩnh viễn | Suppress địa chỉ đến khi sửa/xác minh lại |
| Mailbox đầy tạm thời | Retry hoặc hoãn với giới hạn |
| Domain nhận tạm thời không truy cập được | Backoff, theo dõi |
| Provider tạm từ chối vì rate limit | Điều tiết tốc độ, không tự động suppress recipient |
| Provider từ chối do SPF/DKIM/DMARC | Sửa xác thực domain; không coi mọi recipient đều không tồn tại |
| Spam complaint được xác thực | Xử lý theo chính sách complaint/consent, có thể suppress |
| User unsubscribe hợp lệ | Xử lý consent/marketing, không đồng nhất với hard bounce |
| Bounce không có bằng chứng rõ | Đối soát, không đánh dấu hard bounce tự động |

Một lỗi 5xx do **policy rejection** của domain nhận không phải bằng chứng rằng mọi mailbox tại domain đó đều không tồn tại. Nếu tắt toàn bộ recipient vì lỗi cấu hình SPF, ứng dụng sẽ đánh mất những người nhận hợp lệ.

### Suppression theo địa chỉ và theo loại email

Ví dụ:

~~~text
recipientId = R123
email = person@recipient.example

suppression:
  reason = HARD_BOUNCE
  scope = EMAIL_ADDRESS
  createdAt = ...
~~~

Tùy chính sách, suppression có thể áp dụng toàn hệ thống, theo tenant, theo stream hoặc theo loại thông báo. Cần phân biệt **email giao dịch bắt buộc theo nghiệp vụ** với **email marketing có consent**, và không tự ý bỏ qua yêu cầu pháp lý chỉ dựa trên một event chưa xác minh.

Nếu người dùng cập nhật email và xác minh địa chỉ mới, không nên giữ suppression của địa chỉ cũ và áp dụng mù cho địa chỉ mới.

## 27. Chống backscatter và bounce giả mạo

**Backscatter** xảy ra khi hệ thống mail gửi thông báo lỗi tới một địa chỉ đã bị giả mạo làm envelope sender của thư gốc. Kẻ tấn công có thể lợi dụng điều này khiến người vô tội nhận hàng loạt bounce không liên quan.

Nếu ứng dụng có một bounce mailbox công khai:

- Không tin mọi thông điệp đến mailbox là bounce hợp lệ của chính ứng dụng.
- Không cập nhật suppression chỉ từ địa chỉ From của bounce.
- Đối chiếu notification ID, provider ID và recipient.
- Kiểm tra định dạng DSN chuẩn khi có; vẫn xem dữ liệu nhận được là không tin cậy.
- Tránh tạo một bounce khác khi xử lý DSN lỗi.
- Có rate limit, filtering và retention.
- Không gửi tự động một email “bounce rejected” tới bất kỳ địa chỉ nào có trong thông báo.

Ngay cả khi dùng VERP, token trong địa chỉ có thể bị quan sát hoặc giả mạo nếu thiết kế dễ đoán. Dùng token opaque và xác minh correlation với record đã phát hành.

Nếu dùng ESP webhook, thực thi đúng cơ chế xác thực chữ ký và chống replay. Không xem webhook là đáng tin chỉ vì request có một header tên giống provider.

## 28. Bảo vệ dữ liệu cá nhân trong bounce

Một DSN có thể chứa:

- Recipient email.
- Header của email gốc.
- Một phần hoặc toàn bộ nội dung email gốc, tùy mail server.
- Message-ID, transaction ID hoặc URL trong nội dung.
- Chuỗi chẩn đoán từ hệ thống nhận.

Do đó, hệ thống xử lý bounce cần:

- Giảm thiểu lưu trữ raw DSN khi không cần.
- Áp dụng quyền truy cập và thời gian lưu phù hợp.
- Che/mã hóa PII trong log.
- Không ghi token đặt lại mật khẩu, OTP, nội dung hóa đơn hoặc đường dẫn chứa secret.
- Không hiển thị nguyên văn Diagnostic-Code từ bên ngoài trong UI quản trị không được kiểm soát.
- Chỉ ghi những field cần cho xử lý deliverability và truy vết.
- Bảo vệ những bảng chứa lịch sử suppression/recipient.

Bounce là dữ liệu từ bên ngoài đi vào ứng dụng. Parser phải giới hạn kích thước, tránh xử lý attachment không cần thiết và chống các vấn đề do nội dung MIME phức tạp hoặc độc hại.

## 29. Kiểm tra envelope sender thực tế sau khi gửi

Cấu hình **mail.smtp.from** mới chỉ cho biết ứng dụng **yêu cầu** dùng địa chỉ nào. Để xác nhận provider đã sử dụng địa chỉ đó, có thể kiểm tra từ những nguồn có độ tin cậy phù hợp.

### Cách 1: xem SMTP trace tại chặng submission

Nếu provider và môi trường test cho phép quan sát phiên SMTP, xác nhận lệnh:

~~~smtp
MAIL FROM:<bounces@bounces.example.com>
~~~

Đó là bằng chứng trực tiếp rằng client đã yêu cầu reverse-path này tại chặng đang quan sát. Nó chưa khẳng định server sẽ giữ nguyên khi relay qua chặng khác.

Không bật debug SMTP ở production chỉ để đọc địa chỉ nếu hệ thống log có thể làm lộ AUTH hoặc thông tin nhạy cảm. Ưu tiên SMTP test server hoặc công cụ trace của ESP.

### Cách 2: xem Return-Path của thư đã giao

Gửi một email test đến mailbox do nhóm vận hành kiểm soát, sau đó xem nguyên bản header:

~~~text
Return-Path: <bounces@bounces.example.com>
From: Example Shop <notifications@example.com>
Reply-To: support@example.com
~~~

Nếu Return-Path khác với cấu hình, cần kiểm tra provider có viết lại envelope sender, có forwarder trung gian hay không và server đã xác minh custom MAIL FROM chưa. Return-Path có thể bị ảnh hưởng bởi tuyến chuyển tiếp, nên đây là một tín hiệu quan sát, không thay thế message trace từ provider.

### Cách 3: xem Authentication-Results

Một email nhận được có thể chứa thông tin như:

~~~text
Authentication-Results: mx.receiver.example;
  spf=pass smtp.mailfrom=bounces.example.com;
  dkim=pass header.d=example.com;
  dmarc=pass header.from=example.com
~~~

Đây là ví dụ minh họa. Mỗi hệ thống nhận có thể trình bày header khác nhau, và các header do server bên ngoài cung cấp không nên được coi là bằng chứng bất biến nếu không biết trust boundary.

Thông tin này giúp kiểm tra:

- Domain thực tế được dùng trong SPF.
- DKIM signing domain.
- DMARC alignment với From.

### Cách 4: dùng provider dashboard/API

Nếu ESP hỗ trợ custom return-path, bounce domain hoặc message trace, đối chiếu:

- Domain đã được xác minh.
- Trạng thái DNS validation.
- Envelope sender mà provider báo đang dùng.
- Provider message ID và bounce routing.
- Kết quả SPF/DKIM/DMARC.

Một số provider chỉ cho phép một mẫu địa chỉ bounce do họ quản lý; khi đó nên dùng event/webhook chính thức thay vì cố đặt MAIL FROM tùy ý bằng Spring.

## 30. Kiểm thử luồng bounce trong môi trường kiểm soát

Để xác nhận cả chặng gửi và chặng nhận phản hồi, cần kiểm thử nhiều hơn việc mock **JavaMailSender**.

| Tình huống | Điều cần xác nhận |
|---|---|
| Gửi thành công qua SMTP sandbox | Header From/Reply-To đúng; SMTP MAIL FROM đúng theo cấu hình |
| Custom MAIL FROM không được provider cho phép | Có lỗi hoặc envelope sender bị viết lại; hệ thống ghi nhận đúng |
| Recipient bị từ chối ngay tại RCPT TO | Lỗi đồng bộ được phân loại, không chờ một bounce không có thật |
| Provider chấp nhận DATA rồi chuyển phát thất bại | Bounce/DSN bất đồng bộ được đối chiếu với notification |
| Bounce event gửi lặp lại | Không xử lý hai lần cùng event ID |
| Bounce event đến sai thứ tự | Trạng thái delivery không bị ghi đè tùy tiện |
| Bounce event giả mạo/không hợp lệ | Không cập nhật suppression hoặc recipient |
| Hard bounce được xác nhận | Recipient được suppress theo chính sách |
| Temporary deferral | Không tự động suppress vĩnh viễn |
| Người dùng thay email và xác minh lại | Suppression cũ không áp dụng sai sang email mới |
| Một notification có nhiều recipient | Không gán kết quả của recipient này cho recipient khác |
| ESP webhook mất kết nối | Provider có thể retry, ứng dụng xử lý idempotent |

### Cách tạo lỗi thử nghiệm

Ưu tiên **SMTP sandbox, test server hoặc địa chỉ simulator do provider công bố**. Các địa chỉ như **invalid@recipient.example** trong tài liệu chỉ mang tính minh họa, không bảo đảm bất kỳ hệ thống mail nào sẽ tạo ra bounce như mong muốn.

Không gửi hàng loạt email tới địa chỉ người lạ để “thử hard bounce”. Hành vi này có thể gây ảnh hưởng reputation, bị coi là spam hoặc vi phạm chính sách ESP.

### Test ở mức Java

**Unit test** có thể:

- Xác minh service gọi **MimeMessageHelper.setFrom(...)** và đặt Reply-To đúng.
- Xác minh renderer không dùng địa chỉ bounce làm From.
- Kiểm tra policy mapping bounce code sang retry/suppression.
- Kiểm tra webhook signature verifier được gọi trước khi xử lý event.
- Kiểm tra một event ID không cập nhật database hai lần.

Nhưng **mock JavaMailSender không mở SMTP session** nên không chứng minh **MAIL FROM** thực tế. Phần đó cần integration test với SMTP test server hoặc provider sandbox có khả năng quan sát envelope.

## 31. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng helper.setFrom để cấu hình bounce | Chỉ đổi header From; MAIL FROM có thể khác | Dùng property mail.smtp.from hoặc cấu hình ESP |
| Đặt Return-Path header thủ công | Không bảo đảm thay SMTP envelope | Quan sát MAIL FROM thực tế và để MTA xử lý Return-Path |
| Dùng Reply-To làm địa chỉ bounce | Lẫn phản hồi người dùng với DSN | Tách Reply-To và bounce routing |
| Dùng một envelope sender giả định provider luôn giữ nguyên | Bounce không đi về nơi mong muốn | Xác minh custom MAIL FROM và message trace |
| Chỉ đổi mail.smtp.from mà không cấu hình DNS | SPF/bounce routing có thể lỗi | Thiết lập domain, DNS và inbound theo yêu cầu ESP |
| Đổi property MAIL FROM trên sender singleton giữa các thread | Race condition, gửi nhầm reverse-path | Dùng per-message support chính thức hoặc sender riêng |
| SPF pass là đủ cho DMARC | Có thể không aligned với header From | Kiểm tra DMARC SPF/DKIM alignment |
| Mặc định mail.smtp.from phải trùng header From | Giới hạn thiết kế không cần thiết | Dùng bounce subdomain phù hợp và xác minh domain |
| Coi SMTP 250 là delivered | Báo cáo sai trạng thái người nhận | Tách SUBMITTED với delivery feedback |
| Bắt MailSendException là đủ để bắt mọi bounce | Bỏ sót thất bại xảy ra sau submission | Thu DSN hoặc webhook bất đồng bộ |
| Retry nguyên batch khi có một lỗi | Người nhận thành công có thể nhận trùng | Theo dõi từng notification/recipient |
| Chỉ đọc body text của DSN rồi suppress | Dễ nhầm và bị lợi dụng | Parse trường có cấu trúc, xác thực nguồn |
| Tin mọi webhook là bounce hợp lệ | Kẻ tấn công có thể suppress recipient | Xác minh chữ ký, event ID và notification |
| Coi mọi SMTP 5xx là recipient không tồn tại | Suppress nhầm do policy/authentication | Phân loại theo pha, enhanced status và provider |
| Dùng email/phone trực tiếp trong VERP | Lộ dữ liệu cá nhân trong header/log | Dùng opaque token |
| Đánh đồng null MAIL FROM với cấu hình thiếu | Dễ hiểu sai DSN và gây vòng lặp | Nhận biết MAIL FROM:<> là trường hợp đặc biệt |

## 32. Runbook xử lý lỗi không nhận được bounce

Khi có email bị từ chối ở phía nhận nhưng hệ thống không thấy bounce, nên điều tra có thứ tự:

1. **Xác định notification gốc** bằng notification ID, provider message ID và recipient.
2. **Xem submission result:** server có thực sự trả 250 sau DATA không, hay lỗi xảy ra ngay trong phiên gửi?
3. **Kiểm tra envelope sender được yêu cầu** qua mail.smtp.from hoặc cấu hình ESP.
4. **Kiểm tra envelope sender thực tế** qua provider trace và Return-Path của email test.
5. **Xác định nơi nhận bounce:** mailbox/DSN parser hay event webhook của ESP.
6. **Kiểm tra DNS bounce domain** theo hướng dẫn provider, gồm SPF, MX/CNAME và các record liên quan.
7. **Kiểm tra inbound route:** có nhận được DSN không, mail server/ESP có giữ hoặc lọc event không?
8. **Kiểm tra webhook:** chữ ký hợp lệ, event có được lưu, HTTP response có đúng hợp đồng retry không?
9. **Đối chiếu correlation:** provider message ID, recipient, VERP token có khớp record không?
10. **Kiểm tra trạng thái cuối:** có bị event đến sai thứ tự hoặc logic suppression ghi đè không?
11. **Xem khả năng thiếu báo cáo:** không phải mọi thất bại đều tạo một bounce mà ứng dụng sẽ quan sát được.
12. **Bổ sung metric/alert** cho sự cố hệ thống nhận bounce, không chỉ theo dõi tỷ lệ gửi thành công.

Một lỗi về bounce không nhất thiết nằm ở code JavaMailSender. Có thể SMTP provider đã viết lại reverse-path, DNS inbound bị sai hoặc webhook đang không nhận được event.

## 33. Theo dõi chất lượng deliverability

Ngoài số lần gọi **send(...)** thành công, nên theo dõi các metric:

| Metric | Ý nghĩa |
|---|---|
| **mail_submitted_total** | Số lần SMTP/provider chấp nhận submission |
| **mail_bounce_total** | Số event bounce đã xác thực |
| **mail_hard_bounce_total** | Số bounce được phân loại là vĩnh viễn |
| **mail_soft_bounce_total** | Số bounce được phân loại là tạm thời |
| **mail_deferred_total** | Số lần chuyển phát bị hoãn |
| **mail_suppressed_recipient_count** | Số recipient đang bị suppression |
| **mail_webhook_invalid_signature_total** | Số webhook bị từ chối vì xác thực |
| **mail_delivery_event_lag** | Độ trễ từ submission đến khi nhận event |
| **mail_bounce_unmatched_total** | Số bounce không đối chiếu được với notification |
| **mail_unknown_delivery_count** | Số notification chưa biết kết quả |

### Tỷ lệ bounce

Một công thức báo cáo tham khảo:

~~~text
Bounce rate = số notification bị bounce / số notification đã submitted
~~~

Cần định nghĩa rõ **đơn vị đếm, thời gian quan sát và mẫu số**. Một notification có nhiều event defer/bounce không nên bị tính thành nhiều notification bounce nếu mục tiêu là báo cáo tỷ lệ notification. Ngoài ra, bounce event có thể đến muộn hơn khoảng thời gian submission, nên so sánh hai khoảng thời gian khác nhau mà không chú ý độ trễ có thể gây hiểu lầm.

Nên phân tách theo:

- SMTP provider và sender account.
- Domain của header From và envelope MAIL FROM.
- Loại email: giao dịch, marketing, thông báo hệ thống.
- Domain recipient ở mức tổng hợp phù hợp.
- Thời gian, môi trường và mẫu mã lỗi.

Không ghi quá nhiều label có độ phân mảnh lớn như địa chỉ email cá nhân vào metrics. Dùng notification ID ở log/tracing đã bảo vệ nếu cần điều tra từng record.

## 34. Câu hỏi thường gặp

### Có bắt buộc envelope sender giống From không?

Không. **MAIL FROM** là reverse-path SMTP, còn **From** là tác giả hiển thị trong header. Tuy nhiên domain của chúng ảnh hưởng đến **SPF/DMARC alignment**, chính sách ESP và uy tín gửi. Hai địa chỉ khác nhau là bình thường khi được cấu hình và xác thực đúng.

### Đặt Reply-To thành bounces@example.com thì bounce có về đó không?

Không nên giả định như vậy. **Reply-To** hướng dẫn email client gửi phản hồi của người dùng; **bounce/DSN** thường sử dụng SMTP envelope sender và cơ chế của server/provider.

### Có thể tự đặt Return-Path trong MimeMessage không?

Có thể thao tác với header như một chuỗi, nhưng điều đó **không phải cơ chế chuẩn để điều khiển SMTP MAIL FROM**. Hãy dùng cấu hình transport như **mail.smtp.from** hoặc hỗ trợ custom MAIL FROM của ESP.

### Khi nào cần VERP?

VERP hữu ích nếu ứng dụng cần biết bounce thuộc notification/recipient nào và hệ thống inbound có thể xử lý địa chỉ riêng cho từng lần gửi. Nếu ESP đã cung cấp provider message ID và webhook đáng tin cậy, ứng dụng có thể không cần tự xây VERP.

### SPF pass có bảo đảm DMARC pass không?

Không. SPF phải pass và **domain SPF** phải aligned với header From theo chính sách DMARC để đóng góp vào kết quả DMARC. Một chữ ký DKIM pass và aligned cũng có thể giúp DMARC pass.

### Nếu JavaMailSender.send không ném lỗi, có cần lắng nghe bounce?

Có, nếu nghiệp vụ cần biết kết quả chuyển phát và duy trì danh sách recipient hợp lệ. **send(...) thành công không đồng nghĩa email đã đến mailbox**.

### Vì sao DSN có Return-Path: <>?

Đó là **null reverse-path**, giúp thông báo lỗi không tiếp tục tạo chuỗi thông báo lỗi vô hạn khi chính DSN không giao được.

## 35. Ghi nhớ

**Envelope sender** là địa chỉ **MAIL FROM** trong SMTP envelope, còn **From**, **Sender** và **Reply-To** là các header phục vụ ý nghĩa riêng trong nội dung email. Khi email không chuyển phát được sau khi đã được một MTA tiếp nhận, **bounce/DSN** thường được gửi theo reverse-path. **Return-Path** là dấu vết của reverse-path được ghi vào email khi giao thư, không phải header mà ứng dụng nên tự đặt để điều khiển envelope.

Trong Spring Framework Mail, có thể yêu cầu envelope sender qua property **mail.smtp.from** trên Jakarta Mail SMTP transport, hoặc dùng cơ chế custom MAIL FROM/return-path do ESP hỗ trợ. **MimeMessageHelper.setFrom(...)** chỉ đặt header From. Với hệ thống nhiều luồng, không sửa động mail.smtp.from trên sender singleton để tạo địa chỉ bounce riêng cho từng notification.

Để deliverability tốt hơn, hãy xác minh **bounce domain và DNS**, kiểm tra **SPF/DKIM/DMARC alignment**, chọn cách nhận DSN hoặc webhook đã xác thực, đối chiếu event theo notification/recipient và xử lý suppression một cách thận trọng. Tách lỗi SMTP đồng bộ khỏi bounce bất đồng bộ; không suy ra delivery chỉ từ kết quả send(...), cũng không tự suppress mọi recipient chỉ vì một phản hồi 5xx.

**Nguyên tắc cốt lõi: From là danh tính hiển thị, Reply-To phục vụ phản hồi của con người, còn MAIL FROM là đường quay về của lỗi chuyển phát.** Cấu hình, kiểm chứng và giám sát cả ba là nền tảng của một hệ thống gửi email đáng tin cậy.




