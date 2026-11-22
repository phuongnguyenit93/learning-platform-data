# Đường đi nhiều chặng và các điểm có thể phát sinh lỗi

## 1. Một email không đi thẳng từ Spring vào Inbox

Khi ứng dụng gọi **JavaMailSender.send(...)**, nó mới thực hiện thao tác nộp thông điệp cho hệ thống gửi thư. Từ đó email thường phải qua nhiều máy chủ, hàng đợi và bộ lọc trước khi xuất hiện trong hộp thư của người nhận. Mỗi chặng có trách nhiệm, tín hiệu thành công và cơ chế xử lý lỗi khác nhau.

Trong **Spring Framework Mail**, **MailSender** và **JavaMailSender** cung cấp hợp đồng gửi email cho mã ứng dụng; **JavaMailSenderImpl** thường dùng **Jakarta Mail** để giao tiếp với máy chủ SMTP. Những interface này không thay thế SMTP relay, DNS, máy chủ nhận, bộ lọc spam hay dịch vụ lưu hộp thư.

Để xử lý sự cố đúng, cần phân biệt ba câu hỏi:

1. **Thông điệp đang ở chặng nào?** Mới được tạo, SMTP relay đã nhận, máy chủ đích đã chấp nhận, hay đã xuất hiện trong mailbox?
2. **Ai đang chịu trách nhiệm chuyển tiếp?** Ứng dụng Spring, nhà cung cấp SMTP, mail server của người nhận hay hệ thống lưu thư?
3. **Điều kiện nào cho phép gửi lại?** Lỗi tạm thời, lỗi vĩnh viễn và trường hợp không biết thư đã được chấp nhận hay chưa phải có cách xử lý khác nhau.

## 2. Sơ đồ đường đi nhiều chặng

~~~text
 [1] Nghiệp vụ (đăng ký tài khoản, đơn hàng, thông báo)
      |
      v
 [2] Spring application / EmailService
      |   Dựng người nhận, subject, text/HTML, attachment
      v
 [3] MailSender / JavaMailSender
      |   JavaMailSenderImpl -> Jakarta Mail -> SMTP
      v
 [4] SMTP submission server / Email Service Provider (ESP)
      |   Xác thực, nhận hoặc từ chối thư, có thể đưa vào queue
      v
 [5] Một hay nhiều Mail Transfer Agent (MTA)
      |   Tra cứu DNS/MX, định tuyến, chuyển tiếp qua SMTP
      v
 [6] Mail server của miền người nhận
      |   Policy, SPF/DKIM/DMARC, spam, virus, quota
      v
 [7] Mail Delivery Agent / mailbox storage
      |   Inbox, Junk/Spam, quarantine hoặc thư mục khác
      v
 [8] Người nhận đọc qua webmail, IMAP hoặc ứng dụng email
~~~

Đây là sơ đồ khái quát, không phải một tuyến cố định. Hạ tầng thực tế có thể thêm relay, gateway kiểm tra bảo mật, dịch vụ định tuyến nội bộ, máy chủ chuyển tiếp hoặc hệ thống lọc sau khi đã chấp nhận SMTP. Một số bước có thể hợp nhất trong cùng một dịch vụ.

### Thuật ngữ nền tảng

| Khái niệm | Vai trò trong đường đi |
|---|---|
| **MUA (Mail User Agent)** | Ứng dụng tạo/đọc email; ở phía tự động gửi, Spring service đóng vai trò tạo thông điệp. |
| **MSA (Mail Submission Agent)** | Nhận thư từ ứng dụng hoặc email client, thường qua cổng SMTP submission. |
| **MTA (Mail Transfer Agent)** | Chuyển thư giữa các hệ thống email, thường qua SMTP. |
| **MDA (Mail Delivery Agent)** | Đưa thông điệp vào hộp thư lưu trữ của người nhận. |
| **MX record** | Bản ghi DNS cho biết máy chủ được chỉ định nhận thư của một miền. |
| **ESP (Email Service Provider)** | Nhà cung cấp dịch vụ gửi email, thường có SMTP relay hoặc API riêng, hàng đợi và báo cáo trạng thái. |
| **IMAP/POP3** | Giao thức truy cập thư đã lưu, không phải cách Spring Mail nộp thông điệp để gửi. |

## 3. Chặng 1: Nghiệp vụ và việc tạo thông điệp

Một sự kiện như đăng ký tài khoản, đặt lại mật khẩu hoặc xác nhận thanh toán làm phát sinh ý định gửi email. Ứng dụng cần xác định người nhận, tiêu đề, nội dung, ngôn ngữ, địa chỉ người gửi và các tệp đính kèm. Với Spring Mail, thư văn bản đơn giản có thể dùng **SimpleMailMessage**, còn thư HTML hoặc MIME thường dùng **MimeMessage** và **MimeMessageHelper**.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText(
                "Đơn hàng " + orderCode + " đã được ghi nhận.",
                false
        );

        mailSender.send(message);
    }
}
~~~

Đoạn mã giả định ứng dụng đã cấu hình bean **JavaMailSender** và tài khoản gửi hợp lệ. Đây là email plain text dùng API MIME để minh họa điểm bắt đầu của luồng gửi.

**Những lỗi có thể xảy ra trước cả kết nối SMTP:**

- **Dữ liệu không hợp lệ:** thiếu địa chỉ, địa chỉ sai cú pháp, truyền nhầm người nhận hoặc tạo sai biến trong template.
- **Không tạo được MIME:** exception khi xây dựng thông điệp, encoding sai, dữ liệu HTML không hợp lệ theo xử lý của ứng dụng.
- **Tệp đính kèm lỗi:** không tồn tại, không đọc được, quá lớn hoặc bị chặn bởi quy tắc của ứng dụng.
- **Không tìm thấy bean gửi thư:** dependency hoặc cấu hình Spring/Boot chưa phù hợp.
- **Địa chỉ người gửi không phù hợp:** đôi khi được phát hiện ngay trong ứng dụng, đôi khi chỉ bị chặn ở SMTP server.

Với lỗi dữ liệu hoặc cấu hình, retry lại chính payload chưa sửa thường không có ích. Chặng này cũng là nơi cần kiểm tra quyền gửi, chống lộ dữ liệu người dùng và gắn mã theo dõi nghiệp vụ.

## 4. Chặng 2: Từ JavaMailSender đến SMTP submission server

Khi gọi **send()**, triển khai **JavaMailSenderImpl** thông thường nhờ Jakarta Mail trao đổi với SMTP server theo trình tự:

1. Phân giải tên máy chủ SMTP bằng DNS.
2. Mở kết nối TCP tới cổng đã cấu hình.
3. Thiết lập mã hóa TLS, nếu chính sách yêu cầu.
4. Trao đổi SMTP greeting, EHLO và thông tin khả năng của server.
5. Xác thực bằng cơ chế được máy chủ hỗ trợ, nếu cần.
6. Gửi **MAIL FROM**, một hoặc nhiều **RCPT TO**, sau đó **DATA** chứa thông điệp.
7. Đọc các phản hồi SMTP để biết lệnh hiện tại đã được chấp nhận hay bị từ chối.

Các cổng thường gặp:

| Cổng | Công dụng thông dụng | Lưu ý |
|---|---|---|
| **587** | SMTP submission từ client/ứng dụng | Thường dùng STARTTLS theo cấu hình nhà cung cấp. |
| **465** | SMTP submission với TLS ngay khi kết nối | Cần cấu hình implicit TLS tương ứng. |
| **25** | Giao tiếp/relay giữa các mail server | Có thể bị giới hạn bởi môi trường cloud hoặc nhà cung cấp mạng. |

**Lỗi thường gặp:** hostname SMTP sai; không phân giải DNS; timeout; firewall chặn cổng; cấu hình TLS/STARTTLS không khớp; chứng chỉ TLS không hợp lệ; username/password/token sai; tài khoản bị cấm SMTP AUTH; server không cho relay; vượt giới hạn gửi; kích thước thư vượt hạn mức; người nhận hoặc địa chỉ gửi không được phép.

### Header và SMTP envelope không phải một thứ

Một email có **header** như **From**, **To**, **Subject**, **Reply-To** mà người đọc có thể thấy. Trong khi đó, SMTP vận chuyển thư theo **envelope** thông qua **MAIL FROM** và **RCPT TO**. Envelope sender có thể là nơi nhận bounce; Bcc có thể trở thành một người nhận ở envelope nhưng không được liệt kê trong header thư được chuyển đi.

Sự khác biệt này quan trọng khi điều tra lỗi vì SMTP relay có thể chấp nhận cú pháp header nhưng từ chối envelope sender hoặc recipient; các cơ chế xác thực miền cũng không chỉ nhìn vào một địa chỉ duy nhất.

## 5. Chặng 3: SMTP relay nhận thư và xếp hàng

Trong giao tiếp SMTP, phản hồi thành công sau **DATA** (thường là mã **250**) có nghĩa server mà client vừa nói chuyện đã **chấp nhận thông điệp ở chặng đó để xử lý tiếp**. Đây chưa phải bằng chứng email đã được lưu trong Inbox của người nhận.

Sau khi tiếp nhận, SMTP relay hoặc ESP có thể:

- Đặt email vào queue.
- Thử chuyển đến đích theo thứ tự ưu tiên và trạng thái server.
- Tạm trì hoãn khi phía nhận quá tải hoặc giới hạn tốc độ.
- Thử lại trong một khoảng thời gian do hạ tầng gửi quy định.
- Trả bounce nếu sau đó biết chắc không thể phát thư.

### Hiểu đúng phản hồi SMTP

| Nhóm | Ý nghĩa tổng quát | Cách xử lý |
|---|---|---|
| **2xx** | Lệnh SMTP ở chặng hiện tại thành công | Ghi nhận máy chủ hiện tại đã chấp nhận hành động, tiếp tục theo dõi chặng sau nếu có khả năng. |
| **4xx** | Thất bại tạm thời | Có thể retry với giới hạn và backoff, đồng thời giữ nguyên thông tin lỗi. |
| **5xx** | Thất bại lâu dài với yêu cầu hiện tại | Thường cần sửa địa chỉ, policy, cấu hình hoặc nội dung trước khi gửi lại. |

Chẳng hạn **421** có thể biểu thị dịch vụ tạm thời không sẵn có; **450/451** thường liên quan đến tình huống tạm thời; **550** có thể biểu thị từ chối địa chỉ hoặc policy. Đừng kết luận chỉ từ ba chữ số: hãy đọc toàn bộ câu trả lời SMTP và **enhanced status code** như **4.x.x** hoặc **5.x.x** nếu có. Ý nghĩa cụ thể phụ thuộc giai đoạn trao đổi và chính sách của server.

### Tình huống nguy hiểm: gửi xong nhưng không nhận được xác nhận

~~~text
Ứng dụng Spring                    SMTP relay
     | -------- DATA -------------> |
     |                              | Đã nhận và lưu thư
     | <----- 250 accepted ----X    | Kết nối bị ngắt
     |
     +-- Ứng dụng có thể thấy timeout,
         dù server đã chấp nhận email.
~~~

Nếu ứng dụng thấy lỗi rồi gửi lại ngay, người nhận **có thể nhận hai bản**. Việc gửi qua SMTP không tạo một giao dịch nguyên tử giữa database của ứng dụng, ứng dụng Spring và SMTP server. Trạng thái kết quả cần có khả năng là **không xác định (UNKNOWN)**, thay vì mọi timeout đều được coi là “chưa gửi”.

## 6. Chặng 4: DNS, MX và các máy chủ chuyển tiếp

Khi email được gửi đến địa chỉ như **person@company.example**, hạ tầng chuyển phát cần xác định nơi nhận thư cho miền **company.example**. Thông thường nó tra cứu DNS **MX record** và cố gắng liên lạc với các mail server được công bố.

Một thư có thể đi qua nhiều **MTA**. Trong một số cấu hình, email đi qua gateway bảo mật, các relay trung gian và queue trước khi đến server của miền đích. DNS, đường truyền mạng hoặc hệ thống relay của mỗi chặng đều có thể phát sinh lỗi.

| Sự cố | Biểu hiện có thể gặp | Cách xác định |
|---|---|---|
| DNS lỗi hoặc không phản hồi | Không tìm được đích, thư bị hoãn | Truy vấn DNS, log máy chủ gửi |
| MX trỏ sai hoặc máy chủ đích không khả dụng | Kết nối thất bại, timeout | MX record, IP/hostname đích, phản hồi kết nối |
| Relay không cho chuyển tiếp | SMTP từ chối | Phản hồi relay policy hoặc thông tin xác thực |
| MTA đích tạm quá tải | Deferred, retry nhiều lần | Queue/logs của bên gửi, mã SMTP 4xx |
| Hạ tầng định tuyến có vòng lặp hoặc misconfiguration | Thư di chuyển bất thường, không tới đích | Headers Received, logs chuyển tiếp |

Một miền không có MX chưa đủ để kết luận mọi email tới miền đó đều không gửi được: theo quy tắc SMTP có trường hợp fallback sang bản ghi địa chỉ A/AAAA, hoặc miền có thể công bố cơ chế từ chối nhận email. Cần xét DNS thực tế và mã lỗi nhận được.

Đây là các vấn đề nằm **sau tầng tạo thư của Spring**. Sửa template HTML hay chuyển từ **SimpleMailMessage** sang **MimeMessage** không xử lý được lỗi MX hoặc mạng liên server.

## 7. Chặng 5: Máy chủ đích kiểm tra và quyết định chấp nhận thư

Hệ thống nhận thư phải cân bằng giữa nhu cầu phát thư hợp lệ và việc chống spam, giả mạo, phishing, malware, lạm dụng dung lượng. Vì thế một server đích có thể chấp nhận, trì hoãn, từ chối hoặc cách ly thư theo chính sách của mình.

### Những lớp kiểm tra quan trọng

| Cơ chế | Mục đích | Lỗi/ảnh hưởng có thể thấy |
|---|---|---|
| **SPF** | Kiểm tra nguồn gửi có được miền liên quan đến danh tính SMTP cho phép hay không | Ảnh hưởng quyết định nhận/thư rác theo chính sách. |
| **DKIM** | Xác minh chữ ký mật mã trên thông điệp | Chữ ký không hợp lệ làm giảm tín hiệu tin cậy. |
| **DMARC** | Kiểm tra alignment giữa miền header From và SPF/DKIM phù hợp, áp dụng chính sách miền | Có thể bị quarantine/reject theo chính sách và kết quả xác thực. |
| **Reputation** | Đánh giá uy tín IP/miền, hành vi gửi, tỷ lệ khiếu nại | Thư có thể bị hạn chế tốc độ, defer hoặc chặn. |
| **Anti-spam/anti-malware** | Kiểm tra nội dung, liên kết, tệp đính kèm, dấu hiệu lừa đảo | Có thể vào Spam, quarantine hoặc bị reject. |
| **Recipient/quota policy** | Kiểm tra người nhận, dung lượng, quy tắc của tổ chức | Có thể bị từ chối lúc SMTP hoặc phát sinh bounce sau đó. |

**SMTP authentication** với tài khoản của ứng dụng và **SPF/DKIM/DMARC** là hai vấn đề khác nhau. Đăng nhập SMTP thành công không bảo đảm miền gửi được cấu hình xác thực đúng. Spring Boot mail starter cũng không tự tạo DNS records hay ký DKIM cho mọi nhà cung cấp. Nhà vận hành cần cấu hình miền, dịch vụ SMTP/ESP và chính sách DNS theo yêu cầu cụ thể.

Một email có thể được máy chủ đích **chấp nhận ở tầng SMTP** rồi bị bộ lọc phía sau đưa vào **Spam/Junk** hoặc vùng quarantine. Đây là lý do người dùng nói “không nhận được” trong khi ứng dụng vẫn ghi nhận thao tác gửi thành công.

## 8. Chặng 6: Phát vào mailbox và người nhận truy cập

Sau khi được máy chủ đích nhận, email có thể được giao cho thành phần phát thư (**MDA**) để lưu vào mailbox. Người dùng sau đó mới xem thư bằng webmail, IMAP, POP3 hoặc ứng dụng trên điện thoại.

Các tình huống thường gây hiểu nhầm:

- Email nằm trong **Spam/Junk**, thư mục theo rule hoặc hộp thư phụ.
- Hệ thống quản trị doanh nghiệp đưa thư vào **quarantine**, hoặc một quy tắc nội bộ xóa/chuyển tiếp.
- Mailbox đầy, tài khoản bị tạm khóa hoặc dịch vụ lưu trữ có sự cố.
- Thư đã có trên máy chủ nhưng ứng dụng đọc thư chưa đồng bộ.
- Người nhận đã tạo rule tự động chuyển thư sang địa chỉ hoặc thư mục khác.

Trạng thái **delivered** do một ESP công bố thường có nghĩa là máy chủ đích đã chấp nhận giao thư; định nghĩa chính xác tùy nhà cung cấp. Nó **không bảo đảm** thư đã vào Inbox, hiển thị trên thiết bị, hoặc đã được người dùng mở đọc.

### Phân biệt các mốc thành công

~~~text
CREATED -> SUBMITTED -> SMTP ACCEPTED -> REMOTE ACCEPTED -> VISIBLE/READ
   |          |              |                 |              |
Đã tạo    Đã gửi yêu    Relay gửi        Hệ thống đích   Inbox/Spam và
trong app cầu đến mail  chấp nhận       chấp nhận       người dùng mở
           server        thư              thư             thư
~~~

Ứng dụng Spring không tự nhìn thấy được tất cả các mốc bên phải. Cần log của ESP, báo cáo bounce/DSN, webhook hoặc dữ liệu do bên nhận cung cấp. Nhiều lần không thể khẳng định chính xác “đã vào Inbox” từ phía hệ thống gửi.

## 9. Bảng xác định lỗi theo chặng

| Chặng | Dấu hiệu | Nguyên nhân điển hình | Nơi lấy bằng chứng |
|---|---|---|---|
| **Tạo nội dung trong ứng dụng** | Exception trước **send()** | Input/template, MIME, file đính kèm, cấu hình bean | Exception/log ứng dụng |
| **Kết nối SMTP** | Connect timeout, TLS handshake thất bại | DNS, port, firewall, TLS, chứng chỉ | Log kết nối và cấu hình SMTP |
| **Xác thực SMTP** | Authentication rejected | Credential/token sai, thiếu quyền gửi | Phản hồi AUTH, console của nhà cung cấp |
| **Submission** | Sender/recipient/DATA bị reject | Relay policy, địa chỉ, hạn mức, kích thước | SMTP reply đầy đủ ở lệnh tương ứng |
| **Queue của bên gửi** | Gửi thành công nhưng thư chậm | Throttle, tạm hoãn, server đích quá tải | ESP/MTA queue và delivery logs |
| **Tra cứu DNS/MX và relay** | Chỉ lỗi với một miền | MX sai, DNS lỗi, route/relay policy | DNS query, SMTP log ở MTA |
| **Kiểm tra tại đích** | Bounce, spam, policy reject | SPF, DKIM, DMARC, reputation, recipient | Bounce code, thông báo máy chủ đích |
| **Mailbox/client** | Được báo delivered nhưng không có Inbox | Junk/Spam, quarantine, rule, đồng bộ | Người nhận/quản trị viên mailbox |

**Định vị chặng lỗi trước, rồi mới quyết định sửa gì.** Không nên sửa Java code theo suy đoán khi bằng chứng chỉ ra server đích đang tạm hoãn hoặc chặn vì policy.

## 10. Spring Mail báo lỗi ra sao?

Spring Framework Mail sử dụng họ **MailException** cho các lỗi gửi thư ở tầng Spring. Một vài kiểu thường gặp:

| Exception | Ý nghĩa khái quát | Cách điều tra |
|---|---|---|
| **MailAuthenticationException** | Xác thực máy chủ gửi thất bại | Kiểm tra tài khoản, mật khẩu/token, quyền SMTP. |
| **MailSendException** | Thất bại khi gửi | Xem nguyên nhân gốc, server response và trạng thái giao thư. |
| **MailPreparationException** | Lỗi trong quá trình chuẩn bị thư | Kiểm tra dữ liệu/template/callback. |
| **MailParseException** | Lỗi diễn giải hoặc chuẩn bị thông điệp | Kiểm tra nội dung, cấu trúc MIME và cause. |

Với email MIME, các thao tác tạo thông điệp còn có thể ném **jakarta.mail.MessagingException** trong lúc chuẩn bị. Chỉ bắt một lớp exception rồi retry mọi trường hợp là không đủ: các lỗi khác nhau yêu cầu sửa dữ liệu, sửa cấu hình, chờ rồi thử lại hoặc điều tra trạng thái chưa xác định.

Ví dụ tách trách nhiệm lỗi trong mã Java:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MailAttempt {

    private final JavaMailSender sender;

    public MailAttempt(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message);
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Thông báo");
        helper.setText("Nội dung thư.");

        try {
            sender.send(message);
        } catch (MailAuthenticationException ex) {
            // Cần xem lại cấu hình và quyền truy cập SMTP.
            throw ex;
        } catch (MailException ex) {
            // Lưu thông tin chẩn đoán an toàn ở tầng điều phối.
            // Không tự retry nếu chưa phân loại nguyên nhân.
            throw ex;
        }
    }
}
~~~

Trong Spring Boot, cấu hình thường nằm dưới **spring.mail**; ví dụ SMTP host, port, username, password, các thuộc tính **mail.smtp.auth**, **mail.smtp.starttls.enable** và các timeout. Thông tin xác thực thật phải lấy từ biến môi trường hoặc kho bí mật, không commit vào repository hoặc ghi ra log.

## 11. Ba nhóm kết quả khi gửi email

### A. Lỗi tạm thời

Ví dụ server đang quá tải, gặp mã SMTP 4xx, mất mạng ngắn hạn hoặc bị throttle. Có thể retry theo **exponential backoff + jitter** với số lần thử tối đa, khoảng thời gian giới hạn và khả năng ghi nhận lỗi cuối. Tránh gửi hàng loạt lần retry cùng lúc làm tăng tải hoặc xấu uy tín.

### B. Lỗi vĩnh viễn đối với yêu cầu hiện tại

Ví dụ người nhận không hợp lệ, account bị khóa, sai credential, địa chỉ gửi không được phép, email vượt giới hạn hoặc server trả lời 5xx theo policy. Việc gửi lại y nguyên thường không giúp ích; cần sửa dữ liệu hoặc cấu hình. Tuy nhiên mã phản hồi phải được đọc cùng thông báo chi tiết và ngữ cảnh; không phải mọi mã 5xx đều mô tả cùng một nguyên nhân.

### C. Chưa rõ yêu cầu đã được server chấp nhận hay chưa

Ví dụ timeout ngay sau **DATA**, mất kết nối trước khi đọc phản hồi thành công, worker bị dừng khi đang gửi. Khi đó ứng dụng không thể khẳng định email chắc chắn chưa gửi, và retry có thể gây trùng. Nên ghi trạng thái **UNKNOWN**, đối chiếu với log/provider message ID nếu có, rồi quyết định cách tiếp tục.

Không có bảo đảm “exactly once” xuyên qua ứng dụng, SMTP và mailbox chỉ bằng cách gọi **JavaMailSender.send()**.

## 12. Giao dịch cơ sở dữ liệu và nguy cơ gửi trùng

Giả sử nghiệp vụ cần ghi đơn hàng vào database rồi gửi thư xác nhận. Database commit và việc SMTP chấp nhận thư **không cùng một giao dịch nguyên tử**:

- Email đã gửi, nhưng transaction database rollback: người dùng nhận xác nhận cho đơn hàng không tồn tại.
- Database commit thành công, nhưng SMTP lỗi: đơn hàng tồn tại mà thông báo chưa được gửi.
- SMTP đã chấp nhận thư, worker crash trước khi lưu trạng thái: khi chạy lại có thể gửi trùng.

Một hướng thiết kế thông dụng là **transactional outbox**:

~~~text
     Giao dịch trong database
  +-----------------------------+
  | Ghi đơn hàng                |
  | Ghi outbox "send email"     |
  +-----------------------------+
                |
              COMMIT
                |
                v
         Worker đọc outbox
                |
                v
       JavaMailSender.send()
                |
      +---------+-----------+
      |                     |
  ACCEPTED              FAILED/UNKNOWN
      |                     |
  Ghi trạng thái        Retry có điều kiện /
                        đối soát / điều tra
~~~

Outbox giữ nhất quán giữa dữ liệu nghiệp vụ và **ý định gửi thư**. Nó không tự loại bỏ được toàn bộ khả năng gửi hai lần: worker vẫn có thể chết sau khi SMTP nhận thư nhưng trước khi đánh dấu outbox đã xử lý. Cần một mã thông báo ổn định, khóa xử lý/ghi trạng thái, và idempotency của ESP nếu được hỗ trợ. Với SMTP thuần, không nên khẳng định có thể loại bỏ hoàn toàn trùng lặp.

## 13. Quan sát và chẩn đoán xuyên chặng

Để tra cứu, hệ thống nên giữ mối liên hệ giữa một thông báo nghiệp vụ và các lần nộp SMTP:

| Dữ liệu cần theo dõi | Mục đích |
|---|---|
| **Notification ID / business event ID** | Xác định sự kiện nào đã phát sinh email. |
| **Attempt ID, thời điểm và trạng thái** | Phân biệt lần gửi đầu với lần retry. |
| **MIME Message-ID** | Đối chiếu thông điệp qua mail headers, khi có dữ liệu. |
| **Provider/SMTP message ID** | Tra log, queue, bounce, delivery event của ESP/MTA. |
| **SMTP response và nguyên nhân lỗi** | Xác định bước nhận/từ chối hoặc lỗi tạm thời. |
| **Bounce, deferred, delivered, complaint** | Quan sát kết quả bất đồng bộ nếu dịch vụ gửi cung cấp. |

**Message-ID ở header và ID nội bộ của nhà cung cấp có thể khác nhau.** Khi sử dụng webhook, cần xác minh nguồn/chữ ký của sự kiện và xử lý khả năng webhook được gửi lặp hoặc đến không đúng thứ tự. Không được giả định mọi provider đều có cùng tập sự kiện hay cùng định nghĩa trạng thái delivered.

Để bảo vệ dữ liệu, tránh đưa mật khẩu SMTP, token, OTP, liên kết đặt lại mật khẩu, nội dung thư hoặc tệp đính kèm vào log thông thường. Địa chỉ email cũng là dữ liệu cá nhân; chỉ giữ lượng thông tin cần thiết cho vận hành và che bớt khi phù hợp.

### Một số tình huống thực tế

**Ứng dụng trả HTTP 200 nhưng người nhận không thấy email.** Trước hết phải biết HTTP 200 có nghĩa là đã gọi SMTP hay chỉ mới ghi một job vào queue. Tiếp theo kiểm tra SMTP/ESP đã chấp nhận chưa, có defer/bounce không, rồi kiểm tra Junk/Spam, quarantine và rule phía người nhận.

**Chỉ thư gửi đến một miền bị lỗi.** Kiểm tra DNS/MX của miền đó, SMTP response từ MTA đích và policy/reputation liên quan. Nếu các miền khác hoạt động bình thường, vấn đề có thể nằm ở mạng liên miền hoặc chính sách riêng của miền nhận.

**Sau khi retry người nhận nhận hai bản.** Xem lần gửi đầu có thể đã được chấp nhận trước khi ứng dụng bị timeout hay không. Đối chiếu attempt ID với log của provider và cải tiến xử lý trạng thái UNKNOWN.

**SMTP authentication thành công nhưng thư vào Spam.** Thành công khi đăng nhập máy chủ gửi không thay thế SPF/DKIM/DMARC, reputation hoặc bộ lọc nội dung của phía nhận. Cần điều tra xác thực miền và chính sách nhận.

## 14. Quy trình điều tra một email thất bại

Khi nhận báo cáo “không gửi được email”, có thể đi theo trình tự:

1. **Có yêu cầu gửi thật không?** Tìm mã thông báo nghiệp vụ, người nhận và thời điểm phát sinh.
2. **Thông điệp tạo được không?** Kiểm tra exception về dữ liệu, MIME, tệp đính kèm và template.
3. **Kết nối SMTP thành công không?** Kiểm tra DNS của SMTP host, port, TLS, credentials và timeout.
4. **Relay của bên gửi phản hồi thế nào?** Đọc trạng thái ở MAIL FROM, RCPT TO và DATA.
5. **Thư đang ở queue, được chuyển tiếp hay bị bounce?** Xem ESP/MTA logs và provider message ID.
6. **Máy chủ đích có chấp nhận không?** Kiểm tra DNS/MX, response, SPF/DKIM/DMARC, spam policy.
7. **Thư nằm ở đâu?** Kiểm tra Inbox, Junk/Spam, quarantine, forwarding rule hoặc lỗi đồng bộ.
8. **Có an toàn để gửi lại không?** Phân biệt tạm thời, vĩnh viễn và chưa rõ kết quả; xác định nguy cơ gửi trùng.

### Mô hình trạng thái tham khảo cho ứng dụng

~~~text
PENDING -> PREPARING -> SUBMITTING
                            |
          +-----------------+------------------+
          |                 |                  |
       ACCEPTED           FAILED            UNKNOWN
          |                 |                  |
   QUEUED/DEFERRED    Phân loại lỗi       Đối soát
          |
   REMOTE_ACCEPTED
          |
  Có thể vào Inbox / Spam / quarantine
          |
  Có thể có sự kiện delivery/bounce về sau
~~~

Đây là **mô hình nghiệp vụ để thiết kế và vận hành**, không phải danh sách trạng thái được Spring Mail tự động cung cấp. SMTP thuần chỉ cho ứng dụng quan sát được một số ranh giới; các trạng thái chặng sau phụ thuộc vào khả năng theo dõi của nhà cung cấp và máy chủ đích.

## 15. Ghi nhớ khi thiết kế kiến trúc email với Spring

- **Đường đi là một chuỗi chuyển giao trách nhiệm.** Thành công tại một chặng không tự chứng minh thành công ở tất cả các chặng tiếp theo.
- **Spring Mail trừu tượng hóa việc nộp email từ ứng dụng.** SMTP relay, DNS, hệ thống nhận và lưu hộp thư có thể tiếp tục hoạt động hoặc gặp lỗi sau đó.
- **Đọc bằng chứng theo chặng.** HTTP response của ứng dụng, SMTP 250, bounce và trạng thái delivered có ý nghĩa khác nhau.
- **Retry phải có chính sách.** Phân biệt lỗi tạm thời, lỗi vĩnh viễn và kết quả không rõ, áp dụng backoff, giới hạn số lần và đối soát khi cần.
- **Thiết kế khả năng theo dõi ngay từ đầu.** Liên kết notification ID, attempt ID, message ID và phản hồi nhà cung cấp; giữ log an toàn và bảo vệ dữ liệu người nhận.

Khi nắm rõ từng chặng, câu hỏi “vì sao email không đến?” sẽ được thu hẹp thành một vấn đề cụ thể: **ứng dụng chưa tạo được thư, SMTP chưa nhận, relay chưa giao được, máy chủ đích từ chối hay mailbox không hiển thị**. Đó là nền tảng để xử lý lỗi email hiệu quả trong hệ thống sử dụng Spring Framework Mail.
