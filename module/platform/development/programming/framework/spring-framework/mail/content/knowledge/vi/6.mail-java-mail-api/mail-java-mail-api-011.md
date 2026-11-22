# MailException và các lỗi Spring thường gặp

Trong **Spring Framework Mail**, việc gọi **JavaMailSender.send(...)** trông giống một lời gọi phương thức Java thông thường, nhưng phía sau có nhiều bước có thể thất bại: tạo địa chỉ, dựng MIME message, đọc attachment, thiết lập kết nối, xác thực SMTP, trao đổi lệnh với mail server và chuyển thông điệp tới hệ thống nhận. Spring gom nhiều lỗi của quá trình này vào họ ngoại lệ **MailException** để ứng dụng có thể xử lý ở một ranh giới thống nhất.

Điều khó nằm ở cách **diễn giải** ngoại lệ. Một lỗi đăng nhập SMTP cần cách khắc phục khác với một địa chỉ người nhận sai; timeout mạng cũng khác việc nhà cung cấp từ chối thông điệp vì chính sách. Đặc biệt, **một exception khi gửi email không luôn chứng minh thông điệp chưa được máy chủ từ xa tiếp nhận**. Vì vậy, chỉ viết một khối **catch (Exception)** rồi thử gửi lại toàn bộ là không đủ cho ứng dụng đáng tin cậy.

Bài học thuộc phần **API Java Mail** của Spring Framework Mail, làm rõ phân cấp **MailException**, nguyên nhân bên dưới từ Jakarta Mail/SMTP, cách quan sát thông tin lỗi và cách quyết định nên báo lỗi, sửa cấu hình hay thử lại.

## 1. MailException nằm ở lớp nào của quá trình gửi?

Khi dùng Spring Mail, ứng dụng thường tương tác với một trong hai API:

- **MailSender** gửi các thông điệp văn bản đơn giản, thường qua **SimpleMailMessage**.
- **JavaMailSender** mở rộng khả năng gửi bằng **MimeMessage**, hỗ trợ HTML, charset, multipart, attachment và **MimeMessagePreparator**.

Một luồng gửi có thể hình dung:

~~~text
Ứng dụng gọi JavaMailSender.send(...)
             |
             v
Chuẩn bị dữ liệu: recipient, subject, nội dung
             |
             v
Tạo SimpleMailMessage hoặc MimeMessage
             |
             v
Spring Mail + Jakarta Mail transport
             |
             +-- Đọc cấu hình SMTP và attachment
             +-- Kết nối TCP / TLS
             +-- Xác thực (nếu cần)
             +-- MAIL FROM / RCPT TO / DATA
             |
             v
SMTP server tiếp nhận hoặc báo lỗi
             |
             v
Hạ tầng email tiếp tục chuyển phát (nếu đã tiếp nhận)
~~~

Lỗi ở nhiều bước sẽ được Spring biểu diễn bằng một ngoại lệ thuộc họ **org.springframework.mail.MailException**. Tuy nhiên, tùy chỗ phát sinh lỗi và phiên bản thư viện, Spring có thể bọc một ngoại lệ thấp hơn như **jakarta.mail.MessagingException**, **jakarta.mail.AuthenticationFailedException**, lỗi socket hoặc lỗi từ SMTP provider. Vì vậy, **loại MailException** và **chuỗi nguyên nhân (cause)** cần được xem cùng nhau.

### MailException là unchecked exception

**MailException** là lớp gốc trừu tượng cho các lỗi Spring Mail và là một **runtime exception**; code gọi **send(...)** không bắt buộc phải khai báo **throws MailException** hay viết **try/catch** để biên dịch được.

Ví dụ:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class PlainMailSender {
    private final JavaMailSender mailSender;

    public PlainMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo(recipient);
        message.setSubject("Thông báo");
        message.setText("Nội dung thông báo.");

        // Có thể phát sinh MailException ở runtime.
        mailSender.send(message);
    }
}
~~~

Không cần khai báo **throws MailException**, nhưng ở ranh giới nghiệp vụ hoặc worker gửi mail vẫn cần có cách xử lý lỗi có chủ đích. Nếu ngoại lệ lan ra từ một HTTP controller mà không được chuyển thành phản hồi phù hợp, người dùng có thể chỉ thấy lỗi 500; nếu nó lan ra từ một background job mà không được ghi nhận, công việc có thể bị mất hoặc bị lặp lại không kiểm soát.

**Phân biệt:** các phương thức của **MimeMessageHelper** có thể ném **MessagingException** hoặc những checked exception khác khi đang tạo nội dung MIME; còn **JavaMailSender.send(...)** dùng hợp đồng lỗi Spring Mail. Cùng một thư có thể gặp lỗi ở bước chuẩn bị rồi được Spring bọc thành **MailPreparationException**, tùy cách sử dụng API.

## 2. Phân cấp ngoại lệ Spring Mail

Những loại thường gặp trong Spring Framework Mail:

~~~text
RuntimeException
    |
    +-- NestedRuntimeException (Spring)
           |
           +-- MailException  (abstract)
                  |
                  +-- MailAuthenticationException
                  +-- MailParseException
                  +-- MailPreparationException
                  +-- MailSendException
~~~

Các lớp con này giúp mô tả **giai đoạn hoặc bản chất lỗi ở mức Spring**, chứ không tạo một ánh xạ một-một cho mọi mã phản hồi SMTP.

| Ngoại lệ | Ý nghĩa điển hình | Hướng xử lý đầu tiên |
| --- | --- | --- |
| **MailAuthenticationException** | Không xác thực được với mail server/provider | Kiểm tra credentials, cơ chế auth, tài khoản, TLS/chính sách provider |
| **MailParseException** | Không phân tích/biến đổi thông điệp thành cấu trúc gửi hợp lệ | Kiểm tra dữ liệu địa chỉ, cú pháp hoặc nội dung thông điệp |
| **MailPreparationException** | Không chuẩn bị được MimeMessage qua preparator | Kiểm tra logic dựng nội dung, attachment, MIME headers và cause |
| **MailSendException** | Có lỗi trong thao tác gửi qua transport; có thể liên quan nhiều message | Kiểm tra SMTP/network response, failed messages, cause và kết quả gửi một phần |
| **MailException** | Lớp gốc chung, có thể bắt để bao phủ các dạng lỗi Spring Mail | Ghi nhận lỗi và áp dụng chính sách fallback phù hợp |

Lưu ý quan trọng: **tên ngoại lệ không đủ để tự quyết định retry**. Ví dụ **MailSendException** có thể do mất kết nối tạm thời, mailbox bị từ chối vĩnh viễn hoặc một tình huống mà trạng thái gửi không rõ ràng. Bên dưới cùng một loại ngoại lệ có thể là các nguyên nhân khác nhau.

### Quan hệ với ngoại lệ Jakarta Mail

Spring Mail dựa vào Jakarta Mail để chuẩn bị và vận chuyển MIME message. Trong luồng gửi hiện đại, ta có thể gặp:

- **jakarta.mail.MessagingException**: lớp lỗi ở tầng Jakarta Mail.
- **jakarta.mail.AuthenticationFailedException**: liên quan tới xác thực.
- **jakarta.mail.SendFailedException**: liên quan thao tác gửi; có thể mang thông tin nhóm địa chỉ hợp lệ/không hợp lệ.
- **jakarta.mail.internet.AddressException**: lỗi cú pháp/diễn giải địa chỉ.
- Các ngoại lệ mạng và TLS như **ConnectException**, **SocketTimeoutException**, **UnknownHostException**, **SSLException** ở sâu trong chuỗi nguyên nhân, tùy tình huống.

Với dự án Spring cũ, các import JavaMail thường bắt đầu bằng **javax.mail** thay vì **jakarta.mail**. Bản chất của luồng xử lý tương tự, nhưng **không trộn hai namespace** trong cùng cấu hình phụ thuộc.

## 3. MailAuthenticationException: đăng nhập SMTP thất bại

Một ứng dụng có thể gửi mail qua máy chủ SMTP yêu cầu xác thực. Nếu thông tin đăng nhập hoặc cơ chế được chọn không được chấp nhận, Spring có thể ném **MailAuthenticationException**.

Những nguyên nhân thường gặp:

1. Sai username/password hoặc credential đã hết hiệu lực.
2. Provider yêu cầu **app password**, OAuth2 hoặc cơ chế xác thực khác nhưng ứng dụng dùng mật khẩu đăng nhập thông thường.
3. Tài khoản SMTP bị vô hiệu hóa, khóa hoặc chưa được cấp quyền gửi.
4. SMTP server không chấp nhận cơ chế **AUTH** mà client đang đề nghị.
5. Cấu hình TLS/STARTTLS không đáp ứng chính sách của provider; tùy điểm lỗi, Spring có thể báo một loại ngoại lệ khác, không nhất thiết là MailAuthenticationException.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: smtp-user
    password: your-secret-from-environment
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

Đây là ví dụ cấu trúc cấu hình; trong ứng dụng thật cần lấy bí mật từ biến môi trường hoặc secret manager. Các tham số host, port, SSL/STARTTLS, AUTH phải theo hướng dẫn của nhà cung cấp cụ thể.

Một phản hồi SMTP kiểu:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

có thể chỉ ra lỗi xác thực, nhưng **nội dung và mã chi tiết của provider không luôn giống nhau**. Ngoại lệ ở tầng Java là một tín hiệu, còn log server/provider mới giúp xác định nguyên nhân cụ thể.

**Cách xử lý:** không retry liên tục với cùng mật khẩu sai. Trước tiên kiểm tra cấu hình và quyền tài khoản, tạo cảnh báo vận hành nếu lỗi xuất hiện ở nhiều công việc gửi. Không ghi mật khẩu hoặc access token vào log. Nếu token hết hạn và ứng dụng có cơ chế làm mới token được hỗ trợ, việc làm mới phải được xử lý ở tầng xác thực thay vì gửi lại vô hạn.

## 4. MailParseException: không tạo được cấu trúc thư hợp lệ

**MailParseException** thường liên quan quá trình Spring chuyển một thông điệp đơn giản hoặc dữ liệu nội dung thành cấu trúc mà tầng mail có thể sử dụng.

Ví dụ dữ liệu:

~~~text
To: lan@@example.test
Subject: Tài liệu
Body: Xin chào
~~~

Địa chỉ không phù hợp cú pháp có thể khiến parser báo lỗi trước khi kết nối SMTP. Tùy đường gọi **SimpleMailMessage**, **MimeMessageHelper**, **MimeMessagePreparator** và chỗ xử lý địa chỉ, ngoại lệ cuối có thể là **MailParseException**, **MailPreparationException**, hoặc checked **AddressException/MessagingException** tại lúc xây message.

Do đó không nên viết logic như:

~~~java
// Không chính xác:
// "Hễ địa chỉ người nhận sai thì chắc chắn có MailParseException."
~~~

Thay vào đó, **xác thực dữ liệu người nhận trước khi gọi send(...)**, rồi coi MailParseException là một lớp bảo vệ ở biên tích hợp, phục vụ việc quan sát lỗi bất thường.

**Cách xử lý:** xem lại địa chỉ, From/To/Cc/Bcc, các header tùy chỉnh và cách xây thông điệp. Với dữ liệu do người dùng nhập, trả lỗi hợp đồng API như **INVALID_RECIPIENT** trước khi gửi. Với lỗi đến từ dữ liệu hệ thống, giữ lại công việc để sửa hoặc đánh dấu lỗi không cần retry mà không gửi lại cùng dữ liệu sai.

## 5. MailPreparationException: tạo MIME message bị lỗi

Khi dùng **JavaMailSender.send(MimeMessagePreparator)**, ứng dụng giao cho Spring một callback để chuẩn bị MIME message. Nếu callback thất bại, Spring có thể chuyển lỗi thành **MailPreparationException**.

Các nguyên nhân có thể gồm:

- Thiết lập MIME headers hoặc địa chỉ bị lỗi.
- Đọc file đính kèm không thành công.
- Xây multipart hoặc cấu trúc nội dung không hợp lệ.
- Lỗi từ mã ứng dụng trong callback chuẩn bị.
- Dữ liệu cần có bị thiếu hoặc nguồn dữ liệu đã bị xóa trước lúc chuẩn bị.

Ví dụ:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class DocumentMailService {
    private final JavaMailSender sender;

    public DocumentMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendDocumentNotice(String recipient) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mimeMessage, true, "UTF-8");
            helper.setFrom("documents@example.test");
            helper.setTo(recipient);
            helper.setSubject("Tài liệu mới");
            helper.setText("Tài liệu đã được cập nhật.", false);
        };

        sender.send(preparator);
    }
}
~~~

Đây là luồng chuẩn bị nội dung hợp lệ khi dữ liệu đầu vào và cấu hình đúng. Nếu một thao tác trong **preparator** ném checked exception hoặc lỗi runtime, Spring có thể bọc lỗi để caller thấy **MailPreparationException**. Việc bọc giúp tránh phải lan truyền hàng loạt checked exception của Jakarta Mail ra khắp service.

**Không đồng nhất MailPreparationException với “SMTP đã thử gửi nhưng thất bại”.** Trong nhiều trường hợp, SMTP chưa được gọi. Retry cùng một nội dung hỏng không giúp ích; cần xác định lỗi dữ liệu, logic template hoặc tài nguyên đính kèm.

### MailPreparationException so với MessagingException

Khi tự tạo **MimeMessage** và gọi **MimeMessageHelper** bên ngoài preparator:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");
helper.setTo(recipient); // Có thể phát sinh MessagingException.
sender.send(mime);      // Có thể phát sinh MailException.
~~~

Lỗi dựng nội dung có thể xuất hiện trực tiếp dưới dạng **MessagingException** ở dòng helper trước khi đến **send(...)**. Nếu dùng callback preparator, Spring có cơ hội bọc lỗi chuẩn bị. Vì vậy, lớp ngoại lệ cuối cùng phụ thuộc **ranh giới API nơi mã lỗi được ném ra**, không chỉ phụ thuộc “email có hợp lệ hay không”.

## 6. MailSendException: lỗi ở bước gửi và khả năng gửi một phần

**MailSendException** thường gắn với việc Spring không thể hoàn thành thao tác gửi một hoặc nhiều thông điệp như mong muốn. Các nguyên nhân thường gặp:

- DNS, TCP hoặc kết nối tới SMTP server gặp vấn đề.
- Server đóng kết nối bất ngờ, timeout hoặc TLS bị lỗi.
- SMTP từ chối một số lệnh, sender, recipient hoặc nội dung thông điệp.
- Mail server/provider áp dụng chính sách giới hạn hoặc chống spam.
- Gửi nhiều message, trong đó **có message thành công và message thất bại**.

Ví dụ gửi nhiều thư:

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("notifications@example.test");
first.setTo("lan@example.test");
first.setSubject("Thông báo A");
first.setText("Nội dung A");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("notifications@example.test");
second.setTo("minh@example.test");
second.setSubject("Thông báo B");
second.setText("Nội dung B");

mailSender.send(first, second);
~~~

Giả sử message thứ nhất được nộp thành công nhưng message thứ hai bị từ chối. Một **MailSendException** không chứng minh **cả hai** đều chưa được gửi. Với một lần gửi **nhiều message**, Spring cung cấp thông tin về các message lỗi qua **MailSendException.getFailedMessages()** khi implementation thu thập được dữ liệu tương ứng.

Ví dụ cách ghi nhận có điều kiện:

~~~java
import org.springframework.mail.MailSendException;

try {
    mailSender.send(first, second);
} catch (MailSendException ex) {
    int failedCount = ex.getFailedMessages().size();
    logger.warn(
            "Gửi mail gặp lỗi; số message được ghi nhận thất bại: {}",
            failedCount,
            ex
    );
    throw ex;
}
~~~

Trong ví dụ, **logger** giả định đã được cấu hình trong class. **failedCount** là số đối tượng message xuất hiện trong cấu trúc lỗi, không phải tổng số recipient bị từ chối, cũng không chứng minh mọi message còn lại đã tới Inbox. Ngoài bản đồ message thất bại, có thể xem **getMessageExceptions()** để tìm các ngoại lệ gắn với thao tác gửi.

### Một message có nhiều người nhận

Nếu một MimeMessage có nhiều địa chỉ **To/Cc/Bcc**, SMTP có thể chấp nhận recipient này và từ chối recipient khác. Ngoại lệ tầng Jakarta Mail, ví dụ **SendFailedException**, có thể chứa các nhóm địa chỉ như:

- **valid sent**: địa chỉ được transport xác định là đã gửi thành công theo kết quả bước gửi.
- **valid unsent**: địa chỉ hợp lệ nhưng chưa được gửi.
- **invalid**: địa chỉ bị xem là không hợp lệ trong ngữ cảnh gửi đó.

Các nhóm này phụ thuộc phản hồi và khả năng của transport; không phải mọi lỗi mạng đều cung cấp đủ thông tin. **“Valid sent” không đồng nghĩa “đã giao vào Inbox”**. Spring có thể bọc ngoại lệ thấp hơn vào **MailSendException**, vì vậy cần xem cause và thông tin provider nếu muốn biết chi tiết recipient.

Trường hợp lỗi kết nối sau khi server đã tiếp nhận thư là **trạng thái không xác định**. Không thể mặc định gửi lại mọi người nhận mà không cân nhắc nguy cơ thư trùng.

## 7. Các lỗi Spring Mail thường gặp trong thực tế

Người vận hành thường thấy một thông báo lỗi Java, trong khi nguyên nhân thực sự nằm ở cấu hình mạng, máy chủ SMTP hoặc dữ liệu người nhận. Bảng sau là **gợi ý điều tra**, không phải ánh xạ bắt buộc: cùng một triệu chứng có thể phát sinh ngoại lệ khác tùy vị trí lỗi và mail transport.

| Triệu chứng | Nguyên nhân thường gặp | Ngoại lệ/cause có thể gặp | Hướng kiểm tra |
| --- | --- | --- | --- |
| **Authentication failed** | Sai credentials, tài khoản không được phép SMTP AUTH | **MailAuthenticationException**, **AuthenticationFailedException** | Kiểm tra user, secret, phương thức AUTH và chính sách provider |
| **Connection refused** | Host/port sai, dịch vụ SMTP không lắng nghe, firewall chặn | **MailSendException** với lỗi kết nối bên dưới | DNS, host, port, firewall, cấu hình outbound |
| **Connection timed out** | Mạng chặn hoặc server không phản hồi kịp | **MailSendException**, socket connect timeout | Kiểm tra mạng và **mail.smtp.connectiontimeout** |
| **Read timed out** | Đã kết nối nhưng chờ phản hồi SMTP quá lâu | **MailSendException**, **SocketTimeoutException** | Kiểm tra tải SMTP, proxy và **mail.smtp.timeout** |
| **Write timed out** | Ghi dữ liệu ra socket bị chặn quá lâu | **MailSendException** hoặc lỗi transport liên quan | Kiểm tra mạng, dung lượng thư và **mail.smtp.writetimeout** |
| **SSL handshake failed** | Sai chế độ TLS, certificate hoặc trust chain | Thường là lỗi mail send/transport kèm SSL cause | Kiểm tra STARTTLS/SMTPS, tên máy chủ, chứng chỉ |
| **Invalid address** | Địa chỉ sai cú pháp hoặc không phù hợp quy tắc parser | **AddressException**, **MailParseException** hoặc **MailPreparationException** | Kiểm tra đầu vào trước send, phân biệt một mailbox với danh sách |
| **Recipient rejected** | Địa chỉ không nhận thư, chính sách provider hoặc giới hạn | **MailSendException** với phản hồi SMTP phía dưới | Kiểm tra mã SMTP, người nhận cụ thể, provider event |
| **Sender rejected** | Không được phép gửi từ địa chỉ From/envelope sender | **MailSendException** hoặc lỗi transport | Kiểm tra quyền gửi, miền, chính sách sender |
| **Message too large** | Email sau MIME encoding vượt giới hạn provider | **MailSendException** kèm SMTP response | Tính cả Base64 overhead, headers và attachments |
| **MIME preparation failed** | Nguồn file, template, encoding hoặc mã dựng MIME lỗi | **MailPreparationException** hoặc checked **MessagingException** | Kiểm tra tài nguyên và phần tạo MimeMessage |
| **Temporary SMTP error** | Server đang bận, quota tạm thời, lỗi trung gian | **MailSendException** với mã SMTP **4xx** nếu có | Retry có backoff sau khi xác định phạm vi lỗi |
| **No mail sender bean** | Thiếu phụ thuộc/cấu hình hoặc bean không được tạo | Lỗi DI/config Spring, không nhất thiết là **MailException** | Kiểm tra starter mail và cấu hình auto-configuration |

Hàng cuối cho thấy không phải mọi lỗi liên quan email đều thuộc **MailException**. Ví dụ Spring không tạo được **JavaMailSender** bean ở lúc ứng dụng khởi động có thể tạo lỗi **NoSuchBeanDefinitionException**, **UnsatisfiedDependencyException** hoặc lỗi cấu hình khác. Lỗi này xảy ra **trước khi có bất kỳ lời gọi gửi mail nào**.

### DNS, TCP, TLS và SMTP là các giai đoạn khác nhau

~~~text
Xác định tên máy chủ (DNS)
        |
        +-- UnknownHostException
        v
Kết nối TCP tới host:port
        |
        +-- Connection refused / connect timeout
        v
Thiết lập TLS nếu cần
        |
        +-- SSL handshake/trust lỗi
        v
SMTP greeting / EHLO / AUTH
        |
        +-- Authentication failed / server unavailable
        v
MAIL FROM / RCPT TO / DATA
        |
        +-- Sender/recipient/message rejected
        v
SMTP server chấp nhận thông điệp
        |
        v
Các bước chuyển phát tiếp theo ngoài lời gọi Spring
~~~

Từ phía ứng dụng, nhiều lỗi bên dưới có thể được nhìn thấy dưới lớp **MailSendException**. Khi phân tích, hỏi **lỗi xuất hiện ở giai đoạn nào** thường hữu ích hơn là chỉ đếm số lần một class exception xuất hiện.

## 8. Mã phản hồi SMTP và cách hiểu thận trọng

SMTP thường có phản hồi ba chữ số; nhóm chữ số đầu giúp phân biệt phản hồi thành công, thất bại tạm thời và thất bại được báo là vĩnh viễn trong bối cảnh lệnh.

| Nhóm/mã minh họa | Ý nghĩa chung | Hành động cần cân nhắc |
| --- | --- | --- |
| **2xx** | Lệnh tương ứng đã được chấp nhận/thành công | Không đồng nghĩa thư đã tới Inbox |
| **4xx** | SMTP báo lỗi tạm thời | Có thể retry với backoff và giới hạn |
| **5xx** | SMTP báo lỗi vĩnh viễn ở bước tương ứng | Thường cần sửa dữ liệu/cấu hình hoặc điều tra chính sách |
| **421** | Dịch vụ không sẵn sàng/đóng kênh, tùy server | Kiểm tra trạng thái server, thử lại có kiểm soát |
| **450/451/452** | Một số dạng lỗi tạm thời liên quan mailbox, xử lý hoặc tài nguyên | Đọc mã mở rộng và thông tin provider |
| **535** | Thường dùng cho lỗi SMTP AUTH | Kiểm tra credentials/phương thức auth |
| **550/553** | Một số dạng từ chối mailbox, sender, recipient hoặc chính sách | Không kết luận nguyên nhân chỉ từ ba chữ số |
| **552** | Có thể liên quan giới hạn lưu trữ/kích thước theo bối cảnh | Kiểm tra phản hồi chi tiết và giới hạn provider |
| **554** | Có thể là từ chối transaction/message do chính sách | Điều tra reputation, quyền gửi, nội dung, provider policy |

Thông báo SMTP có thể có **enhanced status code** dạng **5.1.1** hoặc **4.7.0**, bổ sung thông tin về lớp nguyên nhân. Tuy nhiên cách gán mã, mô tả và chính sách cụ thể khác nhau giữa nhà cung cấp.

Ví dụ transcript rút gọn:

~~~text
C: EHLO mail-app.example.test
S: 250-smtp.example.test
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN

C: MAIL FROM:<no-reply@example.test>
S: 250 Sender accepted

C: RCPT TO:<unknown@recipient.test>
S: 550 5.1.1 User unknown
~~~

Đây chỉ là minh họa thứ tự lệnh, không phải phiên đầy đủ để sao chép vận hành; trong cấu hình yêu cầu TLS, client phải thực hiện STARTTLS và xác thực đúng quy trình trước khi gửi. Đặc biệt không gửi credentials trên kênh không an toàn.

### “550” có chắc là email không tồn tại?

**Không.** Một server có thể trả **550** khi mailbox không tồn tại, khi tài khoản bị từ chối bởi chính sách, domain không được phép hoặc những trường hợp khác. Muốn phân biệt “bad address” với “blocked by policy”, cần xem câu trả lời chi tiết, trạng thái nâng cao nếu có và dữ liệu provider. Không nên tự động xóa toàn bộ subscriber có mã **550** mà chưa hiểu ý nghĩa trong môi trường đó.

### SMTP trả thành công có chắc đã phát được thư?

**Không.** Lúc ứng dụng nhận thành công từ SMTP server, server có thể mới **chấp nhận trách nhiệm xử lý** thông điệp. Trong các chặng chuyển phát sau, mail có thể bị bounce, trì hoãn, chuyển tiếp hoặc lọc spam. Do đó, **SUBMITTED** và **DELIVERED** cần là hai khái niệm trạng thái khác nhau nếu hệ thống có theo dõi vòng đời email.

## 9. Bắt ngoại lệ theo nhóm để tránh che khuất nguyên nhân

Với một service gửi thư, có thể dùng phân loại ở tầng Spring như sau:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) {
        MimeMessagePreparator preparator = mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");
            helper.setFrom("welcome@example.test");
            helper.setTo(recipient);
            helper.setSubject("Chào mừng");
            helper.setText("Tài khoản của bạn đã được tạo.", false);
        };

        try {
            mailSender.send(preparator);
        } catch (MailAuthenticationException ex) {
            // Vấn đề tài khoản SMTP/config; cần báo vận hành.
            throw new MailDispatchFailure(
                    "SMTP_AUTH_FAILED", ex
            );
        } catch (MailParseException | MailPreparationException ex) {
            // Cần kiểm tra dữ liệu, template hoặc MIME.
            throw new MailDispatchFailure(
                    "MESSAGE_PREPARATION_FAILED", ex
            );
        } catch (MailSendException ex) {
            // Cần đọc SMTP/network cause trước khi quyết định retry.
            throw new MailDispatchFailure(
                    "SUBMISSION_FAILED_OR_UNKNOWN", ex
            );
        } catch (MailException ex) {
            // Dự phòng cho các lỗi Spring Mail khác.
            throw new MailDispatchFailure(
                    "MAIL_FAILED_UNCLASSIFIED", ex
            );
        }
    }

    public static class MailDispatchFailure extends RuntimeException {
        private final String code;

        public MailDispatchFailure(String code, Throwable cause) {
            super(code, cause);
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }
}
~~~

Mã minh họa có chủ đích **không tự retry**. Nó chuyển các nhóm lỗi thành mã nghiệp vụ để một thành phần bên ngoài quyết định: trả API response, giữ mail job để thử lại, hoặc phát cảnh báo. Một lỗi **MailSendException** được đặt tên **SUBMISSION_FAILED_OR_UNKNOWN** vì trạng thái phía máy chủ có thể không hoàn toàn xác định sau sự cố mạng.

Một số điểm cần lưu ý:

- Bắt lớp con **trước** lớp gốc **MailException**.
- Không dùng **catch (Exception)** để coi tất cả lỗi là “SMTP tạm lỗi”.
- Không chuyển **MailAuthenticationException** thành lỗi nhập liệu của người nhận.
- Giữ **cause** để hệ thống vận hành truy được thông tin bên dưới.
- Nếu wrapper ngoại lệ được log ở tầng controller hoặc worker, tránh log lặp lại toàn bộ stack trace ở mọi tầng.
- Không gửi nguyên stack trace hoặc phản hồi provider chứa thông tin hạ tầng cho người dùng cuối.

Nếu ứng dụng cần xử lý **MessagingException** trong quá trình tạo message ngoài preparator, hãy bắt hoặc cho nó lan ra tại vị trí phù hợp; nó chưa chắc đã được bọc thành MailException. Nên phân định rõ đoạn **prepare** và đoạn **send** để chọn chiến lược xử lý đúng.

### Khi nào nên bắt MailException chung?

Khi một tầng chỉ có trách nhiệm **đánh dấu công việc gửi không hoàn thành và chuyển lỗi lên hệ thống giám sát**, bắt **MailException** chung có thể đủ:

~~~java
try {
    mailSender.send(message);
    markSubmitted(jobId);
} catch (MailException ex) {
    markSubmissionError(jobId, ex);
    throw ex;
}
~~~

Các hàm **markSubmitted** và **markSubmissionError** ở đây là pseudocode chỉ việc cập nhật trạng thái ứng dụng. Nếu cần retry, phải phân loại nguyên nhân ở worker/job handler và có cách xử lý trường hợp **trạng thái submit chưa rõ**. Đừng mặc định **markSubmissionError** tương đương “máy chủ chắc chắn chưa nhận mail”.

### Những phần không nên để exception quyết định thay nghiệp vụ

Một email đăng ký tài khoản có thể là tác vụ phụ, trong khi email mã xác minh lại ảnh hưởng trực tiếp đến khả năng hoàn thành luồng người dùng. Cùng **MailSendException** có thể dẫn tới hai quyết định sản phẩm khác nhau:

- Gửi thư chào mừng thất bại: vẫn giữ tài khoản đã tạo và tạo lịch thử lại công việc gửi.
- Gửi mã xác minh thất bại: tài khoản vẫn có thể ở trạng thái **chưa xác minh**, người dùng có quyền yêu cầu gửi lại mã sau một khoảng thời gian.

Quyết định nào đúng phụ thuộc nghiệp vụ, không phụ thuộc riêng tên class ngoại lệ.

## 10. Chọn retry theo loại lỗi và bằng chứng thực tế

Retry là một cơ chế quan trọng, nhưng thử lại sai cách có thể gây **gửi trùng**, quá tải SMTP hoặc khóa tài khoản nhà cung cấp.

| Loại vấn đề | Có nên retry? | Lý do |
| --- | --- | --- |
| Credential sai, tài khoản bị khóa | **Không retry tự động cùng cấu hình** | Không thể tự phục hồi chỉ bằng gọi lại |
| Dữ liệu recipient sai cú pháp | **Không**, chờ sửa dữ liệu | Cùng đầu vào thường tạo lại lỗi |
| Template/multipart/attachment hỏng | **Thường không** trước khi sửa nguyên nhân | Retry không thay đổi dữ liệu lỗi |
| DNS/network lỗi tạm thời | **Có thể**, dùng backoff và giới hạn | Lỗi hạ tầng có thể tự phục hồi |
| SMTP **4xx** tạm thời | **Có thể**, theo chính sách provider | Server yêu cầu thử lại sau |
| SMTP **5xx** do dữ liệu/chính sách | **Thường không** trước khi xử lý nguyên nhân | Từ chối được báo là vĩnh viễn ở bước đó |
| Timeout sau khi gửi DATA | **Cần kiểm tra vì không chắc trạng thái** | SMTP có thể đã tiếp nhận thư dù app mất phản hồi |
| Provider xác nhận một số recipient đã nhận | **Không retry bừa toàn batch** | Dễ gây lặp cho người đã được submit |
| Thư đã quá thời hạn sử dụng | **Không nên tiếp tục gửi** | Nội dung có thể đã vô giá trị |

### Exponential backoff và jitter

Một thuật toán phổ biến chọn thời điểm lần thử thứ **k**:

~~~text
delay = min(maxDelay, initialDelay * 2^(k - 1))
actualDelay = delay + randomizedJitter
~~~

Ví dụ (chỉ minh họa) có thể bắt đầu ở vài giây rồi tăng dần, giới hạn số lần thử hoặc thời hạn hết hiệu lực. Thành phần **jitter** làm các worker không cùng đánh thức đúng một thời điểm và tạo thêm áp lực lên SMTP server đang quá tải.

Khi provider có **Retry-After** hoặc chỉ dẫn thời điểm thử lại hợp lệ, nên cân nhắc ưu tiên thông tin đó theo hợp đồng cụ thể. Cần bảo vệ trước retry vô hạn, và ghi lại số lần thử, nguyên nhân, thời điểm thử tiếp, trạng thái của mỗi recipient hoặc mỗi mail job.

### Lỗi không rõ trạng thái là một tình huống riêng

Giả sử:

1. Client gửi đủ nội dung thư qua SMTP.
2. Server nhận thư và chuẩn bị phản hồi thành công.
3. Kết nối bị mất trước khi client nhận được phản hồi.
4. Spring báo **MailSendException** vì lỗi mạng.

Đối với ứng dụng, ta biết có lỗi ở lần submit, **không biết chắc server đã chấp nhận thư chưa**. Retry có thể dẫn tới hai email giống nhau. Nếu hệ thống yêu cầu giảm thư trùng, có thể sử dụng:

- **Business key/idempotency key** để không tạo hai công việc gửi cho cùng một sự kiện.
- **Message-ID** và mã provider khi được hỗ trợ để tương quan log và event, nhưng Message-ID tự nó không ép toàn bộ hạ tầng email loại bản sao.
- **Một job cho từng người nhận** nếu cần trạng thái và retry riêng.
- **Dữ liệu provider, webhook/DSN** để đối chiếu kết quả khi có.

Ngay cả với job được lưu bền vững và chỉ một worker xử lý tại một thời điểm, không có giao dịch nguyên tử giữa database và SMTP. Hệ thống thường phải chấp nhận khả năng **at-least-once submission** hoặc thiết kế để hạn chế hậu quả của email trùng.

## 11. Cấu hình timeout: tránh lời gọi chờ quá lâu

Các thiết lập timeout Jakarta Mail thường được truyền qua cấu hình **spring.mail.properties** trong Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: smtp-user
    password: placeholder-use-secret-manager
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Giá trị timeout tính bằng **mili giây** trong cấu hình SMTP transport thông thường:

- **mail.smtp.connectiontimeout**: thời gian chờ thiết lập kết nối.
- **mail.smtp.timeout**: thời gian chờ đọc dữ liệu/phản hồi từ socket.
- **mail.smtp.writetimeout**: thời gian chờ ghi dữ liệu ra socket.

Các số trên chỉ là ví dụ, phải chọn theo độ trễ mạng và yêu cầu vận hành. Trong nhiều cấu hình, nếu không đặt timeout, hành vi mặc định có thể chờ rất lâu. Thiết lập timeout giúp kiểm soát tài nguyên, nhưng **không bảo đảm một lời gọi được hủy ở đúng thời điểm mong muốn trong mọi giai đoạn** và không xóa được trạng thái không rõ ràng sau khi server đã nhận mail.

Nếu ứng dụng Spring MVC gửi thư ngay bên trong HTTP request, thời gian SMTP cũng góp vào thời gian phản hồi API. Có thể cân nhắc worker nền hoặc queue để tách công việc gửi khỏi request nếu thời gian/độ tin cậy quan trọng. Chỉ chuyển **send(...)** sang **@Async** giúp giảm thời gian chờ ở request nhưng **không tự cung cấp lưu trữ bền vững hay retry sau khi tiến trình dừng**.

## 12. Ghi log và giám sát MailException đúng cách

Để giải quyết một sự cố gửi mail, chỉ thấy dòng:

~~~text
Failed to send mail
~~~

thường không đủ. Hệ thống cần biết công việc nào thất bại, ở giai đoạn nào và nguyên nhân có thể hành động được. Nhưng việc ghi nguyên địa chỉ người nhận, nội dung thư, username và password ở mọi log có thể làm lộ dữ liệu riêng tư.

### Những thông tin hữu ích

| Trường | Mục đích |
| --- | --- |
| **mailJobId** | Tương quan một yêu cầu gửi qua log, retry, provider event |
| **notificationType** | Biết thư thuộc loại đăng ký, hóa đơn hay cảnh báo |
| **attemptNumber** | Số lần đã thử nộp thông điệp |
| **failureCategory** | Phân loại ở mức ứng dụng: AUTH, PREPARATION, NETWORK, SMTP_REJECTED, UNKNOWN |
| **exceptionClass** | Biết Spring đã ném loại ngoại lệ nào |
| **smtpStatus** (nếu có) | Phản hồi 4xx/5xx hoặc enhanced status từ provider |
| **retryScheduledAt** | Thời điểm dự kiến xử lý lại |
| **recipientCount** | Thống kê số recipient mà không cần ghi toàn bộ địa chỉ |
| **providerMessageId** (nếu có) | Dùng để đối chiếu với trạng thái nhà cung cấp |

Không phải mọi ngoại lệ đều chứa **smtpStatus** hay **providerMessageId**. Hệ thống nên giữ các trường đó **optional** thay vì tự suy ra từ chuỗi message một cách thiếu chắc chắn.

Có thể định nghĩa các chỉ số vận hành:

~~~text
mail_submissions_total{result="submitted"}
mail_submissions_total{result="failed",category="auth"}
mail_submissions_total{result="failed",category="transport"}
mail_retry_pending
mail_outbox_oldest_pending_age_seconds
mail_provider_bounces_total
~~~

Đây là những tên metric minh họa. Tránh đưa **recipient email** hoặc **message ID tùy ý** vào metric labels vì chúng có thể gây cardinality cao và làm lộ dữ liệu cá nhân. Dùng log hoặc storage có kiểm soát quyền để tra cứu chi tiết khi cần.

### Có nên log cả stack trace?

Trong một sự cố không rõ nguyên nhân, stack trace có ích vì chứa thông tin lớp ngoại lệ và chuỗi cause. Tuy nhiên:

- Một lỗi nhập liệu đã được chuẩn hóa thường chỉ cần log ở mức phù hợp, không nhất thiết là stack trace đầy đủ cho từng request.
- Lỗi cấu hình SMTP trên hàng nghìn công việc có thể tạo lượng log khổng lồ; nên tổng hợp và cảnh báo theo nhóm.
- Tránh ghi lại **mật khẩu**, nội dung nhạy cảm hoặc toàn bộ raw email trong exception reporting.
- Ghi log ở **một ranh giới chịu trách nhiệm**; không để mỗi service bắt rồi log cùng một lỗi trước khi ném lại.

Một logger không thể thay thế trạng thái mail job bền vững. Nếu tiến trình bị dừng, log riêng lẻ khó bảo đảm hệ thống biết công việc nào cần retry. Nên lưu **trạng thái nghiệp vụ của công việc gửi** vào storage phù hợp.

## 13. MailException trong transaction và xử lý nền

Xét luồng “lưu đơn hàng rồi gửi email xác nhận”:

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailService.sendOrderConfirmation(order);
}
~~~

Đây là **pseudocode** để minh họa quan hệ transaction, không phải một class Java hoàn chỉnh. **@Transactional** của database không tạo giao dịch nguyên tử với SMTP. Nếu mail server đã nhận email rồi một lệnh database thất bại khiến transaction rollback, email vẫn có thể được người nhận nhận. Nếu dữ liệu đã commit nhưng SMTP lỗi, việc rollback gửi mail cũng không làm đơn hàng tự mất đi.

Để tách trách nhiệm, hệ thống có thể:

1. Lưu đơn hàng và một **outbox event** yêu cầu gửi thông báo trong **cùng database transaction**.
2. Commit transaction và trả kết quả tạo đơn hàng.
3. Worker đọc công việc **PENDING**, tạo MIME message và gọi **JavaMailSender.send(...)**.
4. Khi có kết quả, worker ghi trạng thái **SUBMITTED**, **RETRY_PENDING**, **FAILED** hoặc **UNKNOWN**, kèm cause/lịch retry theo chính sách.
5. Nếu có provider event hoặc DSN, dùng dữ liệu đó cập nhật trạng thái phát thư tương ứng.

~~~text
HTTP Request
     |
     v
Service -> Database transaction
            |-- save business record
            |-- save mail outbox event
            '-- COMMIT
     |
     v
HTTP response

Background worker
     |
     |-- load pending outbox
     |-- build MIME message
     |-- JavaMailSender.send(...)
     |      |
     |      +-- MailPreparationException -> xử lý nội dung lỗi
     |      +-- MailAuthenticationException -> báo vận hành
     |      +-- MailSendException -> phân loại cause/SMTP
     |
     '-- persist result / retry schedule
~~~

Transactional outbox giúp **ghi nhận ý định gửi** cùng nghiệp vụ và không làm mất toàn bộ công việc chỉ vì tiến trình dừng sau commit. Tuy nhiên, nó **không biến database + SMTP thành một transaction phân tán có exactly-once delivery**. Worker có thể dừng sau khi provider tiếp nhận thư nhưng trước khi lưu trạng thái, nên cần quản lý rủi ro thử lại mơ hồ.

### Khi nào cần trả lỗi HTTP?

Nếu người dùng gửi một request mà dữ liệu người nhận sai, ví dụ **lan@@example.test**, API nên phát hiện lỗi ở bước validation và trả lỗi đầu vào phù hợp, thường là **400 Bad Request**. Đừng để dữ liệu sai tiến sâu tới SMTP rồi biến thành lỗi không rõ nghĩa.

Nếu SMTP server tạm thời không sẵn sàng:

- Với API gửi thư trực tiếp theo hợp đồng đồng bộ, có thể trả lỗi dịch vụ và cung cấp mã lỗi ổn định.
- Với API chỉ **nhận yêu cầu gửi** và đã ghi outbox thành công, có thể trả **202 Accepted** hoặc trạng thái theo hợp đồng mà không chờ SMTP.
- Với API tạo một nghiệp vụ chính, nên phản ánh đúng kết quả nghiệp vụ và ghi trạng thái thông báo riêng.

Không nên trả cho người dùng một lời hứa **“email đã được giao vào Inbox”** chỉ vì **JavaMailSender.send(...)** không ném exception.

## 14. Ví dụ phân tích lỗi theo tình huống

### Tình huống A — Sai mật khẩu SMTP

Ứng dụng nhận **MailAuthenticationException** và trong cause có thông tin xác thực thất bại.

**Phân tích:** đây thường là lỗi cấu hình hoặc quyền tài khoản hệ thống. Việc retry ngay hàng trăm lần với cùng credentials có nguy cơ gây khóa tài khoản và không giúp khôi phục.

**Hành động:** kiểm tra secret, quyền SMTP AUTH, cơ chế TLS và chính sách provider; cảnh báo vận hành; chỉ tiếp tục gửi khi vấn đề được khắc phục.

### Tình huống B — Người nhận bị viết sai cú pháp

Người dùng nhập **lan@@example.test**; ứng dụng nhận **AddressException** lúc tạo MIME message hoặc Spring bọc thành loại MailException phù hợp.

**Phân tích:** lỗi nằm ở dữ liệu đầu vào; SMTP có thể chưa được liên hệ.

**Hành động:** kiểm tra/chuẩn hóa theo chính sách đầu vào trước khi gửi, trả **INVALID_RECIPIENT**, không retry cùng địa chỉ sai.

### Tình huống C — File đính kèm đã bị xóa

Worker nhận job lúc 10:00, đến 10:05 mới tạo email; đường dẫn attachment không còn tồn tại. Giai đoạn chuẩn bị hoặc đọc phần MIME thất bại.

**Phân tích:** đây có thể là lỗi tài nguyên ứng dụng, xuất hiện dưới dạng MailPreparationException, MessagingException hoặc lỗi lúc serialize/gửi tùy cách đính kèm và thời điểm đọc.

**Hành động:** đảm bảo nguồn attachment được lưu bền vững cho tới khi gửi xong, hoặc chuyển nội dung tới storage có quản lý vòng đời. Retry nếu file đã bị xóa vĩnh viễn sẽ không có ích.

### Tình huống D — SMTP trả lỗi 451

Provider phản hồi mã **451** ở một lệnh gửi, nguyên nhân được mô tả là lỗi tạm thời.

**Phân tích:** có thể phù hợp với retry, nhưng cần xem thông tin provider và có thể có giới hạn tần suất.

**Hành động:** đưa job về trạng thái **RETRY_PENDING** với backoff và số lần thử tối đa, theo dõi tỷ lệ thất bại, không tạo hàng nghìn request retry tức thì.

### Tình huống E — SMTP trả lỗi 550 cho một recipient

Thông điệp có ba người nhận; server từ chối một địa chỉ với **550**, hai địa chỉ khác được chấp nhận.

**Phân tích:** kết quả có thể khác nhau theo recipient. Không được kết luận cả ba đều thất bại hoặc retry toàn bộ một cách máy móc.

**Hành động:** đối chiếu nhóm địa chỉ trong **SendFailedException** hoặc dữ liệu provider nếu có, lưu kết quả ở mức recipient, phân loại lỗi chính sách so với mailbox không tồn tại bằng thông tin cụ thể.

### Tình huống F — Timeout sau khi gửi DATA

Lời gọi Spring báo **MailSendException** với cause là timeout. Log phía provider cho thấy đã nhận thông điệp trước khi kết nối mất.

**Phân tích:** ứng dụng không nhận được phản hồi thành công nhưng thư có thể tiếp tục được phân phối. Một retry trực tiếp có thể tạo email thứ hai.

**Hành động:** tương quan job ID/message ID với log hoặc event provider, cân nhắc rủi ro gửi trùng, và dùng trạng thái **UNKNOWN** cho lần submit khi chưa có bằng chứng đủ chắc.

### Tình huống G — Không có JavaMailSender bean

Ứng dụng không khởi động vì constructor cần **JavaMailSender** nhưng không có bean phù hợp.

**Phân tích:** đây thường là lỗi dependency injection hoặc cấu hình Spring Boot, không phải MailException trong một lần gọi send.

**Hành động:** kiểm tra dependency hỗ trợ mail, cấu hình **spring.mail.host** hoặc cấu hình session và cách tạo bean. Không đi tìm lỗi ở SMTP server khi mã gửi thư còn chưa được gọi.

### Tình huống H — Thư được nộp thành công nhưng người dùng không thấy

**JavaMailSender.send(...)** trả về bình thường, nhưng khách hàng báo không thấy email.

**Phân tích:** đây có thể là vấn đề phát thư sau khi submit, lọc spam, alias, forwarding, mailbox hoặc chính sách provider. Không có MailException không có nghĩa thư đã đến Inbox.

**Hành động:** kiểm tra provider events, bounce, địa chỉ đích, SPF/DKIM/DMARC và thông tin chuyển phát mà hạ tầng cung cấp. Đừng tự ném MailSendException để biểu diễn một trạng thái “chưa phát thư” mà ứng dụng không thật sự quan sát được.

## 15. Tự trả lời trước khi xử lý một MailException

Khi nhìn thấy lỗi gửi thư trong Spring, có thể lần lượt đặt các câu hỏi:

~~~text
Exception phát sinh ở bước nào?
  |
  +-- Spring context không tạo được bean?
  |      -> Lỗi cấu hình/DI, chưa liên hệ SMTP
  |
  +-- Đang tạo SimpleMailMessage / MimeMessage?
  |      -> Kiểm tra input, charset, header, MIME, attachment
  |
  +-- Đang xác thực SMTP?
  |      -> Kiểm tra credentials, AUTH, TLS, quyền tài khoản
  |
  +-- Đang kết nối hoặc truyền dữ liệu?
  |      -> Kiểm tra DNS/TCP/TLS/timeout/cause
  |      -> Xác định trạng thái submit có rõ hay không
  |
  +-- Server từ chối sender/recipient/message?
  |      -> Đọc SMTP code và thông tin provider
  |      -> Xác định lỗi tạm thời hay cần sửa dữ liệu
  |
  +-- Server đã chấp nhận nhưng thư chưa tới người nhận?
         -> Theo dõi delivery/bounce qua provider
         -> Không tự suy ra MailException từ việc thiếu Inbox
~~~

Các quyết định quan trọng tiếp theo là: **có cần sửa input/config không, có thể retry không, retry ai, có nguy cơ gửi trùng không, và trạng thái nghiệp vụ nên được ghi nhận như thế nào**.

**MailException là ranh giới lỗi tiện dụng của Spring Framework Mail, không phải kết luận cuối cùng về hành trình chuyển phát email.** Biết phân biệt **MailAuthenticationException**, **MailParseException**, **MailPreparationException** và **MailSendException**, rồi kết hợp loại ngoại lệ với cause, SMTP response và trạng thái công việc sẽ giúp hệ thống xử lý lỗi chính xác, dễ điều tra và ít gây trùng thư hơn.
