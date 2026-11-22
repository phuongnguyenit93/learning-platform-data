# STARTTLS và SMTPS

## 1. Vai trò của TLS khi gửi email bằng Spring Framework Mail

Trong ứng dụng Java sử dụng **Spring Framework Mail**, **JavaMailSender** thường gửi email tới một SMTP server hoặc email service provider (ESP). Trước khi server chấp nhận email, ứng dụng có thể phải trao đổi các thông tin quan trọng: tên đăng nhập, thông tin xác thực, địa chỉ người gửi/người nhận, subject và nội dung MIME. Nếu phiên kết nối không được bảo vệ, dữ liệu có nguy cơ bị quan sát hoặc can thiệp trên đường truyền.

**TLS (Transport Layer Security)** giúp bảo vệ phiên kết nối giữa **ứng dụng Spring** và **SMTP server đang kết nối** bằng mã hóa và cơ chế xác thực máy chủ thông qua chứng chỉ. Trong SMTP, hai cách thiết lập TLS phổ biến là:

- **STARTTLS (explicit TLS):** mở kết nối SMTP ban đầu, yêu cầu nâng cấp phiên hiện tại lên TLS, rồi tiếp tục giao tiếp SMTP bên trong kết nối đã mã hóa.
- **SMTPS / implicit TLS:** thiết lập TLS ngay khi kết nối TCP được mở, trước khi trao đổi các lệnh SMTP thông thường.

Hai cách đều có thể bảo vệ việc gửi mail nếu được cấu hình đúng. Khác biệt chính nằm ở **thời điểm bắt đầu TLS và quá trình bắt tay (handshake)**, không phải STARTTLS sử dụng một thuật toán yếu hơn SMTPS.

Trong Spring Mail, lựa chọn chế độ TLS là cấu hình của **Jakarta Mail SMTP transport** mà **JavaMailSenderImpl** sử dụng. Nó không thay đổi cách viết subject, HTML hay attachment.

## 2. Phạm vi bảo vệ: TLS giữa ứng dụng và SMTP relay

Hãy phân biệt bảo vệ phiên SMTP submission với việc bảo vệ email xuyên suốt hành trình:

~~~text
Spring application
        |
        |  STARTTLS hoặc implicit TLS
        |  (kết nối mà ứng dụng kiểm soát)
        v
Submission SMTP server / ESP
        |
        |  Một hoặc nhiều lần chuyển tiếp SMTP
        |  TLS phụ thuộc vào từng chặng và chính sách
        v
Receiving SMTP server
        |
        v
Recipient mailbox / mail client
~~~

STARTTLS hoặc SMTPS ở ứng dụng bảo vệ **chặng từ Spring tới server SMTP được cấu hình**. Chúng **không tự biến email thành thông điệp mã hóa đầu cuối (end-to-end)**. Sau khi nhận, SMTP provider có thể xử lý nội dung và chuyển tiếp qua những máy chủ khác theo cơ chế của hệ thống email.

Nếu cần bảo mật nội dung từ người gửi tới người nhận, cần cân nhắc giải pháp riêng như **S/MIME**, **OpenPGP** hoặc cung cấp nội dung nhạy cảm qua một trang đích được xác thực. TLS cho SMTP submission không thay thế các biện pháp đó.

## 3. STARTTLS hoạt động như thế nào?

Với **STARTTLS**, ứng dụng kết nối tới một SMTP endpoint hỗ trợ nâng cấp TLS. Quy trình điển hình trên port 587:

~~~text
Spring / Jakarta Mail                 SMTP server
       |                                   |
       | -------- TCP connect ----------> |
       | <-------- 220 greeting ---------- |
       | -------- EHLO ------------------> |
       | <----- 250-STARTTLS ... --------- |
       | -------- STARTTLS --------------> |
       | <-------- 220 Ready ------------ |
       | ======== TLS handshake ======== |
       | ======== Encrypted SMTP ======= |
       | -------- EHLO (again) ---------> |
       | <----- ESMTP capabilities ------ |
       | -------- AUTH (if required) ---> |
       | -------- MAIL FROM / RCPT TO --> |
       | -------- DATA -----------------> |
       | <-------- SMTP response -------- |
       |                                   |
~~~

Các bước chính:

1. **Mở TCP:** client kết nối tới host và port SMTP.
2. **Nhận greeting:** server thường gửi mã SMTP 220.
3. **EHLO:** client tìm hiểu các khả năng mà server quảng bá, trong đó có STARTTLS nếu được hỗ trợ.
4. **STARTTLS:** client yêu cầu nâng cấp; server chấp nhận bằng phản hồi 220.
5. **TLS handshake:** hai phía đàm phán thông số TLS, server trình chứng chỉ và client xác minh theo cấu hình.
6. **EHLO lại:** sau khi TLS được thiết lập, client gửi EHLO để nhận các khả năng áp dụng cho phiên bảo mật.
7. **AUTH và nội dung:** client xác thực nếu yêu cầu, rồi gửi SMTP envelope và MIME message.

**Điểm quan trọng:** trước lệnh STARTTLS, phần greeting và EHLO đầu tiên chưa được mã hóa. Sau khi nâng cấp thành công, AUTH và nội dung thư phải được trao đổi trên kênh TLS nếu ứng dụng yêu cầu bảo mật submission.

### Vì sao phải gửi EHLO lại?

Sau khi TLS được bật, khả năng của server có thể thay đổi. Ví dụ cơ chế AUTH chỉ được quảng bá sau khi kết nối được mã hóa. Đây là lý do client SMTP thường thực hiện lại EHLO, thay vì tiếp tục dùng thông tin capability từ trước STARTTLS.

## 4. SMTPS (implicit TLS) hoạt động như thế nào?

Với **SMTPS**, thường dùng port 465 cho mail submission qua TLS ngầm định. Client và server thiết lập TLS **trước** khi trao đổi SMTP greeting và các lệnh:

~~~text
Spring / Jakarta Mail                 SMTP server
       |                                   |
       | -------- TCP connect ----------> |
       | ======== TLS handshake ======== |
       | ======== Encrypted channel ===== |
       | <-------- 220 greeting ---------- |
       | -------- EHLO ------------------> |
       | <----- ESMTP capabilities ------ |
       | -------- AUTH (if required) ---> |
       | -------- MAIL FROM / RCPT TO --> |
       | -------- DATA -----------------> |
       | <-------- SMTP response -------- |
       |                                   |
~~~

Không có lệnh **STARTTLS** để nâng cấp vì TLS đã hoạt động từ đầu. Client đòi hỏi server nói TLS ngay sau khi TCP connect.

Tên **SMTPS** thường được dùng trong giao tiếp vận hành. Đối với SMTP submission hiện đại, cách gọi chính xác là **implicit TLS**: SMTP chạy bên trong một kết nối TLS được thiết lập ngay lập tức.

### Lỗi phổ biến do dùng sai chế độ

- Client bật implicit TLS trên một endpoint chỉ chấp nhận SMTP rồi STARTTLS: TLS handshake có thể lỗi hoặc timeout.
- Client chờ greeting plaintext trên một endpoint đòi hỏi implicit TLS: hai phía có thể chờ nhau cho tới khi timeout.
- Client bật STARTTLS nhưng server không quảng bá tính năng và cấu hình không bắt buộc TLS: thư có nguy cơ được gửi qua kết nối không mã hóa.

Không sửa các lỗi đó bằng cách tắt xác minh chứng chỉ hoặc tăng timeout vô hạn; cần cấu hình đúng **host, port và TLS mode**.

## 5. STARTTLS và SMTPS khác nhau ở điểm nào?

| Tiêu chí | STARTTLS | SMTPS / implicit TLS |
|---|---|---|
| Thời điểm TLS bắt đầu | Sau greeting, EHLO và lệnh STARTTLS | Ngay sau TCP connect |
| Port submission thường gặp | **587** | **465** |
| Lệnh STARTTLS | Có | Không cần |
| Greeting SMTP ban đầu | Trước TLS | Sau TLS |
| Cấu hình Jakarta Mail chủ yếu | **mail.smtp.starttls.enable** | **mail.smtp.ssl.enable** |
| Cơ chế đòi hỏi bảo mật | Bật **starttls.required** | TLS phải handshake được trước khi nói SMTP |
| Xác thực chứng chỉ | Cần có | Cần có |
| Khả năng mã hóa nội dung/AUTH | Có, sau nâng cấp thành công | Có, ngay từ đầu phiên SMTP |
| Vấn đề cấu hình thường gặp | Opportunistic fallback nếu không bắt buộc TLS | Sai port hoặc sai chế độ TLS |

Hai phương án đều dùng TLS để bảo vệ phiên nếu handshake và xác minh máy chủ thành công. **Không có quy tắc tổng quát rằng SMTP over port 465 luôn an toàn hơn port 587 hoặc ngược lại.** Chính sách TLS, xác thực máy chủ, thuật toán được phép và cấu hình server mới quyết định mức bảo vệ thực tế.

## 6. Những port SMTP thường gặp

| Port | Mục đích thường gặp | Lưu ý |
|---|---|---|
| **587** | Message submission | Thường dùng SMTP + STARTTLS |
| **465** | Message submission với implicit TLS | TLS ngay sau TCP connect |
| **25** | Chuyển tiếp giữa các MTA / SMTP relay | Có thể hỗ trợ STARTTLS; hay bị hạn chế outbound trong một số cloud |
| **2525** | Port thay thế của một số ESP | Chế độ TLS phụ thuộc nhà cung cấp |

Chỉ chọn port mà nhà cung cấp SMTP thực sự công bố. Đừng suy luận rằng bất kỳ host nào cũng mở cả 465 và 587.

### Khi nào chọn 587 hay 465?

Nếu provider hỗ trợ cả hai, có thể chọn dựa trên chính sách tổ chức và môi trường triển khai. Khi dùng 587, hãy **yêu cầu STARTTLS** nếu email submission phải được mã hóa; khi dùng 465, hãy bật **implicit TLS**. Nếu port bị chặn, hãy kiểm tra firewall/egress policy hoặc hướng dẫn provider thay vì tùy tiện đổi chế độ.

## 7. Cấu hình STARTTLS bằng Spring Boot

Khi dùng **spring-boot-starter-mail**, Spring Boot có thể cấu hình **JavaMailSender** từ các thuộc tính **spring.mail**.

Dependency Gradle minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Ví dụ **application.yml** cho SMTP submission qua STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Ý nghĩa quan trọng:

- **host / port:** SMTP endpoint của provider.
- **username / password:** thông tin xác thực; nên lấy từ environment variables hoặc secret manager.
- **auth: true:** yêu cầu SMTP authentication khi provider cần.
- **starttls.enable: true:** cho Jakarta Mail thử nâng cấp TLS qua STARTTLS.
- **starttls.required: true:** không tiếp tục gửi nếu STARTTLS không được hỗ trợ hoặc không thiết lập được.
- **ssl.checkserveridentity: true:** yêu cầu kiểm tra tên máy chủ theo chứng chỉ TLS.
- **connectiontimeout / timeout / writetimeout:** giới hạn thời gian kết nối, đọc và ghi (mili giây).

Host, username và password là giá trị minh họa; không sử dụng **smtp.example.com** như endpoint thật. Các credential không được commit vào repository.

### Vì sao nên đặt cả enable và required?

Đây là hai property khác nhau:

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
~~~

**enable** cho phép quá trình nâng cấp. **required** yêu cầu việc nâng cấp phải thành công. Nếu chỉ bật enable, tùy tình huống và hành vi server/client, ứng dụng có thể tiếp tục mà không có STARTTLS khi server không hỗ trợ. Với ứng dụng cần bảo vệ thông tin xác thực và nội dung submission, cấu hình **required=true** là nguyên tắc an toàn hơn.

## 8. Cấu hình SMTPS (implicit TLS) bằng Spring Boot

Ví dụ **application.yml** cho port 465:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Điểm quyết định là:

~~~properties
mail.smtp.ssl.enable=true
~~~

Với **JavaMailSenderImpl** sử dụng SMTP transport mặc định, thuộc tính này yêu cầu TLS ngầm định. Thông thường **không cần đổi protocol sang “smtps”** chỉ để có TLS trên port 465 khi đã cấu hình **mail.smtp.ssl.enable=true**.

Trong cấu hình implicit TLS này, không cần bật STARTTLS vì phiên đã được mã hóa trước SMTP greeting. Nếu dùng nhiều profile, hãy bảo đảm cấu hình cho 465 không vô tình giữ những property STARTTLS có ý nghĩa khác với mục tiêu.

### Các thuộc tính cần nhớ

| Thuộc tính | STARTTLS, thường trên 587 | Implicit TLS, thường trên 465 |
|---|---|---|
| mail.smtp.auth | true nếu server yêu cầu | true nếu server yêu cầu |
| mail.smtp.starttls.enable | true | Không cần |
| mail.smtp.starttls.required | true khi yêu cầu TLS | Không cần |
| mail.smtp.ssl.enable | Không bật cho STARTTLS thông thường | true |
| mail.smtp.ssl.checkserveridentity | true | true |
| mail.smtp.connectiontimeout | Nên đặt giới hạn | Nên đặt giới hạn |
| mail.smtp.timeout | Nên đặt giới hạn | Nên đặt giới hạn |
| mail.smtp.writetimeout | Nên đặt giới hạn | Nên đặt giới hạn |

## 9. Cấu hình JavaMailSenderImpl khi không dùng auto-configuration

Trong ứng dụng Spring Framework thuần hoặc khi cần tự tạo nhiều sender, có thể cấu hình trực tiếp **JavaMailSenderImpl**. Đây là lớp triển khai **JavaMailSender**, sử dụng Jakarta Mail phía dưới.

Ví dụ bean dùng STARTTLS:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender mailSender(MailCredentials credentials) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(credentials.host());
        sender.setPort(587);
        sender.setUsername(credentials.username());
        sender.setPassword(credentials.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

**MailCredentials** là đối tượng cấu hình do ứng dụng định nghĩa, ví dụ một record nhận dữ liệu từ secret manager hoặc **@ConfigurationProperties**. Đoạn mã giả định đối tượng này đã được đăng ký thành bean và dữ liệu hợp lệ. Không hard-code thông tin đăng nhập thật.

Để chuyển ví dụ trên sang implicit TLS:

~~~java
sender.setPort(465);

Properties props = sender.getJavaMailProperties();
props.put("mail.smtp.auth", "true");
props.put("mail.smtp.ssl.enable", "true");
props.put("mail.smtp.ssl.checkserveridentity", "true");
props.put("mail.smtp.connectiontimeout", "5000");
props.put("mail.smtp.timeout", "10000");
props.put("mail.smtp.writetimeout", "10000");
~~~

Hãy chọn **một chế độ phù hợp với endpoint**. Không sao chép đồng thời toàn bộ thuộc tính của hai mode rồi kỳ vọng Jakarta Mail tự quyết định chế độ đúng.

### Một cấu hình hay nhiều sender?

Nếu ứng dụng có sender giao dịch và sender marketing riêng, mỗi bean có thể sử dụng hostname, port và credential khác nhau:

~~~text
TransactionalMailService
           |
           v
 @Qualifier("transactionalSender")
           |
           +--> host: smtp.transactional.example, port: 587, STARTTLS

CampaignMailService
           |
           v
 @Qualifier("campaignSender")
           |
           +--> host: smtp.campaign.example, port: 465, implicit TLS
~~~

Cần kiểm tra chế độ TLS **cho từng bean**, không chỉ cấu hình **spring.mail** mặc định.

## 10. Gửi MimeMessage sau khi thiết lập sender an toàn

Ứng dụng không cần thay API tạo nội dung khi đổi giữa STARTTLS và SMTPS. Sự khác biệt thuộc tầng transport.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class AccountNotificationService {

    private final JavaMailSender sender;

    public AccountNotificationService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendSecurityNotice(String recipient)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("security@example.com");
        helper.setTo(recipient);
        helper.setSubject("Thông báo bảo mật tài khoản");
        helper.setText(
                """
                Có thay đổi bảo mật liên quan đến tài khoản của bạn.
                Xem chi tiết tại https://example.com/account/security
                """,
                """
                <html lang="vi">
                  <body>
                    <h1>Thông báo bảo mật tài khoản</h1>
                    <p>Có thay đổi bảo mật liên quan đến tài khoản của bạn.</p>
                    <p><a href="https://example.com/account/security">
                       Xem chi tiết
                    </a></p>
                  </body>
                </html>
                """
        );

        sender.send(message);
    }
}
~~~

Đoạn mã tạo plain text và HTML trong **multipart/alternative**. Nó sử dụng sender đã được cấu hình TLS ở phần trước. **MimeMessageHelper không phải nơi chọn STARTTLS hay SMTPS**: nó chuẩn bị địa chỉ, header và nội dung MIME.

Email bảo mật chỉ nên chứa lượng dữ liệu cần thiết. TLS trên SMTP submission không có nghĩa toàn bộ đường chuyển phát và mailbox nhận đều được mã hóa đầu cuối.

## 11. Mối đe dọa khi STARTTLS không bắt buộc

STARTTLS có một bước thương lượng trong phiên SMTP ban đầu. Nếu client chỉ cấu hình nâng cấp khi server quảng bá STARTTLS nhưng **không yêu cầu bắt buộc**, một phiên không được nâng cấp có thể vẫn tiếp tục.

Ví dụ đường đi rủi ro:

~~~text
Client                               Server
  | ---- EHLO ---------------------> |
  | <--- 250 capabilities --------- |
  |       không có STARTTLS          |
  |                                  |
  | ---- tiếp tục SMTP plaintext --> |  <- nguy cơ
~~~

Lý do STARTTLS không được quảng bá có thể là server không hỗ trợ, cấu hình server sai, thiết bị trung gian sửa thông tin hoặc kết nối nhầm endpoint. Không nên mặc định đó là trường hợp bình thường.

Với ứng dụng submission cần bảo mật:

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
~~~

Thiết lập **required=true** giúp ứng dụng thất bại thay vì lặng lẽ tiếp tục không được mã hóa khi không thể thiết lập STARTTLS. Đây là cơ chế chống **fallback xuống plaintext** tại chặng submission.

### STARTTLS stripping là gì?

Một kẻ can thiệp trên đường truyền trước TLS có thể cố ngăn client nhìn thấy khả năng STARTTLS. Nếu client được phép tiếp tục mà không mã hóa, thông tin gửi có thể bị lộ. Khi STARTTLS là bắt buộc, nỗ lực stripping có thể khiến lần gửi thất bại thay vì hạ cấp bảo mật âm thầm.

Yêu cầu STARTTLS không giải quyết mọi tấn công: client vẫn phải **xác minh chứng chỉ, tên máy chủ và độ tin cậy của kênh TLS**. Nếu chấp nhận bất kỳ chứng chỉ nào, kết nối “có mã hóa” chưa chắc nối tới SMTP server dự định.

## 12. Chứng chỉ TLS và xác minh danh tính máy chủ

TLS gồm hai mục tiêu thường dễ bị nhầm:

1. **Mã hóa đường truyền**, ngăn người ngoài dễ dàng đọc hoặc sửa nội dung phiên.
2. **Xác minh server**, giúp client tin rằng endpoint mình kết nối đúng với hostname được cấu hình.

Một phiên TLS chỉ có mã hóa mà không kiểm tra danh tính máy chủ có thể bị chuyển hướng tới server giả mạo.

Các kiểm tra quan trọng:

- Chuỗi chứng chỉ do một CA được tin cậy ký, hoặc được cấp từ PKI doanh nghiệp được cấu hình rõ ràng.
- Chứng chỉ chưa hết hạn và chưa đến thời điểm có hiệu lực.
- Hostname SMTP khớp với tên hợp lệ trong chứng chỉ, thường là **Subject Alternative Name (SAN)**.
- Các thuật toán và phiên bản giao thức TLS được client/server hỗ trợ và được chính sách cho phép.

Với Jakarta Mail SMTP provider, nên bật kiểm tra hostname tường minh:

~~~properties
mail.smtp.ssl.checkserveridentity=true
~~~

Thuộc tính này phù hợp cho cả đường kết nối STARTTLS và implicit TLS khi dùng **mail.smtp** transport.

### Tình huống certificate mismatch

Ví dụ ứng dụng kết nối:

~~~text
SMTP host: smtp.mail.example.com

Certificate SAN:
  DNS:mail.example.com
~~~

Nếu chứng chỉ không bao phủ **smtp.mail.example.com**, xác minh hostname phải thất bại, dù chứng chỉ có thể hợp lệ cho **mail.example.com**. Hãy dùng hostname mà nhà cung cấp SMTP công bố và có chứng chỉ phù hợp, không tắt kiểm tra để tiếp tục gửi.

## 13. Truststore của Java và chứng chỉ nội bộ

Java dùng tập chứng chỉ CA đáng tin cậy qua truststore/runtime configuration. Khi server SMTP dùng chứng chỉ public hợp lệ, thông thường JDK đã có CA cần thiết. Với SMTP relay nội bộ dùng CA doanh nghiệp, ứng dụng có thể cần một truststore được cấu hình cho CA đó.

Lỗi điển hình:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
  unable to find valid certification path to requested target
~~~

Những nguyên nhân có thể:

- Server không gửi đủ chuỗi chứng chỉ trung gian.
- Chứng chỉ được ký bởi CA mà JDK chưa tin cậy.
- Truststore của container/JDK thiếu CA nội bộ.
- Server/CA đã đổi nhưng truststore chưa cập nhật.
- Hostname hoặc chứng chỉ không phù hợp với endpoint.

Hướng khắc phục:

1. Xem certificate chain server thật sự cung cấp.
2. Xác minh CA và domain theo tài liệu hoặc quản trị viên PKI.
3. Cập nhật chain phía server khi thiếu intermediate.
4. Nếu là CA nội bộ được tổ chức phê duyệt, cấu hình truststore chứa CA phù hợp.
5. Bảo vệ truststore và cập nhật nó theo quy trình quản lý chứng chỉ.

Không tự động tải chứng chỉ từ kết nối đang lỗi rồi thêm vào trusted store mà chưa xác minh danh tính và fingerprint qua nguồn đáng tin cậy.

### Vì sao không nên dùng “trust all”?

Một cấu hình thường xuất hiện trong ví dụ thử nghiệm:

~~~properties
mail.smtp.ssl.trust=*
~~~

Chấp nhận mọi host/certificate theo cách này làm suy yếu khả năng xác thực endpoint và có thể che giấu lỗi truststore hoặc certificate thật. **Không dùng wildcard trust như một giải pháp production**. Tương tự, không tắt hostname verification để gửi thư bằng mọi giá.

## 14. TLS protocol version và cipher suites

Mức an toàn TLS còn phụ thuộc vào những phiên bản giao thức và thuật toán được cho phép. Trên các môi trường hiện đại, chính sách thường ưu tiên **TLS 1.2 và TLS 1.3**, tùy mức tương thích của JDK, server và yêu cầu tổ chức.

Jakarta Mail có thể cho phép giới hạn các phiên bản TLS bằng thuộc tính như:

~~~properties
mail.smtp.ssl.protocols=TLSv1.3 TLSv1.2
~~~

Đây là ví dụ cú pháp cho SMTP transport; nó phải được đối chiếu với phiên bản Jakarta Mail và runtime thực tế. Nếu chỉ định những phiên bản mà một trong hai phía không hỗ trợ, kết nối có thể thất bại dù host và credential đúng.

Không nên tự ý bật các phiên bản TLS đã lỗi thời chỉ để tương thích với một relay cũ. Cần nâng cấp relay hoặc thống nhất một phương án được bộ phận bảo mật phê duyệt.

### Một số lưu ý vận hành

- JDK khác nhau có thể bật/tắt các giao thức và cipher suite mặc định khác nhau.
- Thay JDK hoặc image container có thể làm một endpoint cũ bắt đầu lỗi TLS.
- Cấu hình system-wide có thể tác động tới nhiều client TLS, không chỉ SMTP.
- Nên xác nhận chính sách TLS bằng test với server thực tế và certificate chain phù hợp.

Không kết luận “STARTTLS không hoạt động” chỉ từ **SSLHandshakeException**; lỗi có thể nằm ở certificate, protocol version, truststore hoặc TLS endpoint.

## 15. SMTP AUTH phải được bảo vệ bằng TLS

Nhiều SMTP submission server yêu cầu **AUTH** để xác định ứng dụng có quyền gửi email. Một số cơ chế AUTH có thể làm lộ thông tin xác thực nếu được sử dụng trên kênh không mã hóa.

Do đó, với kết nối có username/password:

- Chọn STARTTLS bắt buộc trên endpoint phù hợp hoặc implicit TLS.
- Xác minh chứng chỉ và hostname server.
- Sử dụng phương thức authentication mà provider hỗ trợ và tổ chức cho phép.
- Không ghi credential hay AUTH conversation vào log.
- Giới hạn quyền của credential và luân chuyển secret theo quy trình.

### AUTH không thay thế TLS

**SMTP AUTH** trả lời câu hỏi “Ứng dụng này có được phép sử dụng dịch vụ gửi hay không?”. **TLS** bảo vệ kênh truyền và xác thực máy chủ. Cần cả hai khi provider yêu cầu xác thực ứng dụng trên đường truyền an toàn.

Nếu AUTH thất bại sau khi TLS đã thiết lập thành công, nguyên nhân có thể là credential, quyền, chính sách account hoặc phương thức xác thực. **Không đổi sang SMTP plaintext chỉ để tránh lỗi AUTH**.

## 16. TLS bảo vệ transport, không thay thế SPF/DKIM/DMARC

Các công nghệ bảo mật email có vai trò khác nhau:

| Cơ chế | Mục tiêu chính | Bảo vệ gì? |
|---|---|---|
| **STARTTLS / implicit TLS** | Bảo mật kết nối SMTP | Kênh truyền giữa hai SMTP peer trong phiên đó |
| **SMTP AUTH** | Xác thực client sử dụng SMTP submission | Quyền sử dụng dịch vụ gửi |
| **SPF** | Công bố server/IP được phép gửi cho domain theo cơ chế SPF | Hỗ trợ kiểm tra domain gửi qua SMTP envelope |
| **DKIM** | Ký một số header và nội dung thư | Kiểm tra chữ ký và tính toàn vẹn theo domain ký |
| **DMARC** | Chính sách và alignment liên quan SPF/DKIM với From domain | Giúp domain chủ quản kiểm soát xử lý thư giả mạo |
| **S/MIME / OpenPGP** | Mã hóa/ký nội dung ở tầng thông điệp | Bảo mật đầu-cuối khi được triển khai đúng |

Một email gửi qua TLS vẫn có thể rơi vào Spam hoặc bị từ chối nếu domain identity, SPF, DKIM, DMARC, nội dung hay reputation không phù hợp. Ngược lại, SPF/DKIM/DMARC không tự mã hóa kết nối SMTP.

## 17. Kiểm tra STARTTLS bằng OpenSSL

Khi cần chẩn đoán khả năng kết nối từ máy hoặc container chạy ứng dụng, có thể sử dụng **OpenSSL** nếu công cụ được cài đặt:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error
~~~

Các thành phần:

- **-starttls smtp:** thực hiện phần giao tiếp cần thiết để nâng cấp kết nối SMTP qua STARTTLS.
- **-connect:** chỉ định endpoint và port.
- **-servername:** gửi SNI để server có thể chọn chứng chỉ thích hợp khi hỗ trợ.
- **-verify_hostname:** kiểm tra chứng chỉ phù hợp hostname đích.
- **-verify_return_error:** trả lỗi khi xác minh chứng chỉ không thành công.

Một số bản OpenSSL hoặc môi trường có thể có tùy chọn khác nhau; hãy sử dụng khả năng mà phiên bản đang cài đặt hỗ trợ.

### Đọc kết quả

Kết quả có thể cho biết:

- Có mở kết nối TCP thành công hay không.
- SMTP server có hỗ trợ và chấp nhận STARTTLS hay không.
- TLS handshake có hoàn thành hay không.
- Chứng chỉ và chuỗi CA có xác minh được không.
- Hostname có phù hợp chứng chỉ không.
- Protocol/cipher nào được chọn.

Lệnh này **không tự chứng minh AUTH thành công hoặc quyền gửi email hợp lệ**. Nó chỉ kiểm tra kết nối và quá trình nâng cấp TLS trong phạm vi công cụ.

**Không nhập credential SMTP thật vào một phiên thử nghiệm thủ công không được kiểm soát.** Cần dùng môi trường thử nghiệm và tài khoản riêng khi cần kiểm tra authentication.

## 18. Kiểm tra implicit TLS trên port 465

Với SMTPS, bỏ **-starttls smtp** vì TLS phải được thiết lập ngay:

~~~bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error
~~~

Nếu lệnh STARTTLS với port 587 chạy tốt nhưng lệnh implicit TLS với port 465 lỗi, chưa chắc provider có sự cố. Có thể provider chỉ hỗ trợ một trong hai endpoint hoặc port 465 bị firewall chặn.

Ngược lại, chạy lệnh implicit TLS trên 587 thường không phải cách đúng để kiểm tra STARTTLS. Client có thể báo handshake error hoặc timeout vì server đang chờ SMTP greeting/command theo thứ tự khác.

### Kiểm tra TCP trước khi kết luận lỗi TLS

Trên Windows PowerShell:

~~~powershell
Test-NetConnection smtp.example.com -Port 587
Test-NetConnection smtp.example.com -Port 465
~~~

Trên Linux có netcat:

~~~bash
nc -vz -w 5 smtp.example.com 587
nc -vz -w 5 smtp.example.com 465
~~~

TCP connect thành công chỉ chứng minh một lớp kết nối ban đầu; nó chưa khẳng định TLS, AUTH hoặc quyền gửi thành công.

## 19. Các lỗi thường gặp khi dùng STARTTLS

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **STARTTLS is required but host does not support STARTTLS** | Endpoint không quảng bá STARTTLS; sai host/port hoặc server cấu hình sai | Kiểm tra EHLO capabilities và endpoint |
| **Could not convert socket to TLS** | Handshake, chứng chỉ, protocol hoặc thiết bị trung gian | Xem cause SSLHandshakeException và chứng chỉ |
| **PKIX path building failed** | CA không được trust hoặc chain không đầy đủ | Xem chain và truststore |
| **No subject alternative DNS name matching** | Chứng chỉ không khớp hostname | Sửa host hoặc chứng chỉ |
| **Authentication failed** | Credential, quyền hoặc cơ chế AUTH sai | Xem cấu hình auth sau TLS |
| **SocketTimeoutException** | Server/mạng phản hồi chậm; sai chế độ có thể làm chờ | Xác định pha, TCP, TLS và read timeout |
| **Connection refused** | Không có listener trên port đích hoặc bị reject | Kiểm tra host/port và network policy |
| **UnknownHostException** | SMTP hostname không phân giải được | Kiểm tra DNS và cấu hình hiệu lực |

Những tên lỗi trên là ví dụ thường gặp, không phải cam kết chuỗi exception giống nhau trên mọi phiên bản Jakarta Mail/JDK. Trong ứng dụng Spring, nguyên nhân gốc có thể bị bọc trong **MailSendException**, **MessagingException** hoặc exception liên quan.

### Ví dụ: server không quảng bá STARTTLS

~~~text
Client: EHLO application.example
Server: 250-smtp.example.com
Server: 250-SIZE 52428800
Server: 250 AUTH ...

Không thấy 250-STARTTLS / 250 STARTTLS
~~~

Nếu đang dùng port 587 và yêu cầu STARTTLS, ứng dụng nên **thất bại thay vì gửi plaintext**. Hãy xác minh đây là SMTP endpoint đúng, có thiết bị trung gian can thiệp không và server đã bật STARTTLS chưa.

### Ví dụ: certificate chain không tin cậy

~~~text
javax.net.ssl.SSLHandshakeException
  PKIX path building failed
~~~

Giải pháp không phải là **ssl.trust=***. Hãy kiểm tra endpoint, chain CA, JDK truststore và quy trình cấp chứng chỉ của provider.

## 20. Các lỗi thường gặp khi dùng implicit TLS

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| TLS handshake lỗi ngay khi kết nối | Sai port, protocol hoặc certificate | Dùng s_client chế độ implicit TLS và xem lỗi |
| Timeout khi chờ SMTP greeting | Client chưa bật implicit TLS nhưng server đang chờ TLS | Bật mail.smtp.ssl.enable=true trên port 465 |
| Server đóng kết nối ngay | Client nói plaintext trên TLS endpoint hoặc bị policy từ chối | Kiểm tra TLS mode và network |
| SMTP greeting đến nhưng AUTH thất bại | TLS đã chạy; credential/cơ chế AUTH có vấn đề | Kiểm tra quyền và credential |
| Hostname mismatch | Certificate không bao phủ host | Dùng host chính thức hoặc sửa chứng chỉ |
| Chỉ container production lỗi | Truststore/JDK/runtime hoặc outbound network khác | So sánh image, CA và egress |

Nếu chứng chỉ được xác minh thành công nhưng authentication thất bại, không nên kết luận “TLS bị hỏng”. Hãy tách hai bước trong log và runbook.

## 21. DNS, TCP, TLS và SMTP AUTH là bốn lớp khác nhau

Khi ứng dụng chỉ đưa ra lỗi tổng quát, có thể chẩn đoán theo thứ tự:

~~~text
SMTP hostname đúng?
       |
       +-- Không --> Sửa cấu hình host/profile
       |
       v
DNS lookup được?
       |
       +-- Không --> Kiểm tra DNS/resolver/container
       |
       v
TCP host:port kết nối được?
       |
       +-- Không --> Kiểm tra firewall, route, listener, egress
       |
       v
TLS handshake và xác minh cert thành công?
       |
       +-- Không --> Kiểm tra mode 587/465, CA, hostname, TLS policy
       |
       v
SMTP AUTH thành công?
       |
       +-- Không --> Kiểm tra credential, quyền và auth mechanism
       |
       v
SMTP MAIL FROM / RCPT TO / DATA thành công?
       |
       +-- Không --> Xem SMTP reply, sender identity, recipient, size
       |
       v
Submission được chấp nhận
~~~

Thứ tự này không có nghĩa phải thực hiện mọi bước nếu đã xác định rõ lỗi. Nó giúp tránh nhầm nguyên nhân:

- **UnknownHostException** không được giải quyết bằng thay mật khẩu.
- **Connection refused** không được giải quyết bằng đổi nội dung HTML.
- **SSLHandshakeException** không được giải quyết bằng bỏ SMTP authentication.
- **SMTP 535 authentication failed** thường không được giải quyết bằng tăng timeout.
- **SMTP 550 recipient rejected** thường không phải lỗi TLS.

## 22. Timeout khi dùng STARTTLS và SMTPS

TLS yêu cầu thêm các bước mạng như handshake và xác minh chứng chỉ; SMTP submission còn có greeting, AUTH và DATA. Để tránh worker chờ vô hạn, nên cấu hình cả ba giới hạn thời gian của Jakarta Mail SMTP transport:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

| Property | Vai trò |
|---|---|
| **connectiontimeout** | Giới hạn thời gian mở kết nối socket |
| **timeout** | Giới hạn thời gian đọc/phản hồi socket |
| **writetimeout** | Giới hạn thời gian ghi socket |

Các giá trị ở trên tính theo mili giây và chỉ là ví dụ; nên đo latency thực tế trước khi chọn.

### Timeout do TLS mode sai

Nếu client chờ SMTP greeting plaintext từ endpoint implicit TLS, còn server chờ TLS ClientHello, hai phía có thể chờ cho tới khi một trong các timeout kích hoạt. Tăng timeout không giải quyết sai mode.

### Timeout sau khi nộp dữ liệu SMTP

Nếu mất phản hồi cuối khi server có thể đã nhận DATA, ứng dụng có thể **không biết email đã được chấp nhận hay chưa**. Đây là trạng thái khác với connect timeout trước khi mở kết nối.

~~~text
Connect timeout trước SMTP
   -> chưa có submission
   -> có thể retry nếu nguyên nhân tạm thời

Read timeout sau khi gửi DATA
   -> acceptance có thể đã xảy ra
   -> UNKNOWN / đối soát trước retry
~~~

Không kết luận cứ **SocketTimeoutException** là có thể gửi lại an toàn.

## 23. Tại sao “SSL enabled” không đủ để kết luận bảo mật?

Có thể xuất hiện cấu hình:

~~~properties
mail.smtp.ssl.enable=true
mail.smtp.ssl.trust=*
~~~

Kết nối có thể được mã hóa, nhưng việc tin tất cả certificate/host khiến ứng dụng khó xác minh máy chủ thực. Một đối tượng kiểm soát kết nối trung gian có thể cố dựng endpoint giả mạo.

Để có bảo vệ phù hợp, cần quan tâm:

1. **Đúng endpoint:** host/port do provider công bố.
2. **Đúng chế độ TLS:** explicit STARTTLS hoặc implicit TLS.
3. **Không fallback plaintext:** với STARTTLS, yêu cầu nâng cấp.
4. **Chuỗi CA đáng tin cậy:** dùng truststore phù hợp.
5. **Hostname verification:** server certificate phải khớp host.
6. **Protocol/cipher được phép:** không dùng giao thức yếu để “chữa lỗi”.
7. **Bảo vệ credential:** dùng secret manager, không log AUTH.

**Mã hóa và xác thực đầu bên kia là hai phần không thể tách rời trong thiết kế kết nối an toàn.**

## 24. Cấu hình theo môi trường và xử lý bí mật

Trong thực tế, development, staging và production thường có SMTP endpoint hoặc tài khoản khác nhau.

~~~text
Development
  -> SMTP sandbox nội bộ, không gửi ra Internet

Staging
  -> SMTP test account, recipient giới hạn

Production
  -> SMTP submission provider, STARTTLS/implicit TLS bắt buộc
~~~

Cấu hình có thể dùng biến môi trường:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
~~~

Ví dụ trên **giả định** endpoint được cấu hình qua biến môi trường là STARTTLS. Nếu production chuyển sang port 465, cần thay cả cấu hình TLS mode chứ không chỉ đổi **SMTP_PORT**.

Không đưa secret vào tài liệu, sample YAML commit lên repository hoặc log lỗi. Với SMTP provider hỗ trợ app password, OAuth2 hoặc token, hãy dùng phương thức được nhà cung cấp cho phép và áp dụng quyền tối thiểu.

### Nguy cơ khi cấu hình động

Nếu lấy host/port/TLS mode từ request người dùng hoặc dữ liệu không tin cậy, ứng dụng có nguy cơ gửi tới server lạ hoặc truy cập endpoint nội bộ. SMTP host và chế độ transport nên do cấu hình quản trị được kiểm soát quyết định, không từ input tùy ý.

## 25. Theo dõi kết nối TLS trong vận hành

Một hệ thống gửi thư không nên chỉ đo số lần **JavaMailSender.send(...)** trả về thành công. Cần hiểu lỗi ở đâu và tần suất ra sao.

Các metric có thể ghi:

| Metric | Ý nghĩa |
|---|---|
| **mail_connection_failure_total** | Số lần không kết nối được tới SMTP server |
| **mail_tls_handshake_failure_total** | Số lần handshake TLS thất bại |
| **mail_tls_certificate_failure_total** | Số lần chứng chỉ/hostname không hợp lệ |
| **mail_authentication_failure_total** | Số lần xác thực SMTP bị từ chối |
| **mail_submission_success_total** | Số lần SMTP submission được xác nhận |
| **mail_send_duration** | Thời gian tạo/gửi qua transport |
| **mail_timeout_total** | Số lần timeout, nên chia theo pha nếu biết |
| **mail_retry_pending_count** | Số thông báo đang chờ retry |
| **mail_unknown_outcome_total** | Số lần có kết quả gửi không rõ |

Log sự kiện nên chứa thông tin đủ để đối chiếu:

~~~text
notificationId=...
sender=transactional
smtpHost=smtp.example.com
smtpPort=587
tlsMode=STARTTLS_REQUIRED
errorCategory=TLS_CERTIFICATE_INVALID
attempt=1
~~~

**Không ghi password, SMTP AUTH payload, toàn bộ MIME message, OTP hoặc token** vào log. Nếu bắt buộc bật protocol debug, thực hiện trong môi trường kiểm soát, hạn chế thời gian bật và xác định rõ thông tin có thể bị ghi lại.

## 26. Debug Jakarta Mail khi kết nối gặp lỗi

Jakarta Mail có chế độ debug giúp quan sát một số trao đổi giao thức và sự kiện kết nối. Trong một môi trường thử nghiệm có thể cấu hình:

~~~yaml
spring:
  mail:
    properties:
      mail:
        debug: true
~~~

Tuy nhiên, debug SMTP cần được sử dụng thận trọng:

- Nó có thể tạo nhiều log khi lưu lượng lớn.
- Log có thể bộc lộ server, địa chỉ và metadata email.
- Không được giả định mọi giá trị xác thực luôn được che trong mọi phiên bản/cấu hình.
- Việc debug có thể làm tăng chi phí và nhiễu log production.

Ưu tiên sử dụng exception class, cause chain, SMTP reply code và metric trước. Nếu phải bật debug, nên dùng SMTP sandbox và secret thử nghiệm.

### Đọc đúng exception chain

Trong ứng dụng Spring, lỗi TLS có thể xuất hiện bên dưới **MailSendException** hoặc **MessagingException**:

~~~text
org.springframework.mail.MailSendException
  -> jakarta.mail.MessagingException
      -> javax.net.ssl.SSLHandshakeException
          -> sun.security.validator.ValidatorException
~~~

Đây chỉ là sơ đồ minh họa; class và thứ tự thực tế thay đổi theo phiên bản JDK/Jakarta Mail. Khi chẩn đoán, đọc cả **Throwable.getCause()** và khi cần, **MessagingException.getNextException()**.

Một exception bên ngoài tên **MailSendException** chưa nói được nguyên nhân là chứng chỉ, sai port, DNS hay AUTH. Không phân loại tất cả MailSendException thành retryable.

## 27. Khi nào có thể retry sau lỗi TLS?

Việc retry phụ thuộc vào nguyên nhân:

| Trường hợp | Hành động thường hợp lý |
|---|---|
| SMTP server tạm thời không khả dụng, chưa kết nối | Retry với backoff |
| DNS resolver thoáng qua thất bại | Retry có giới hạn |
| TLS handshake thất bại do mismatch chứng chỉ | Dừng, sửa endpoint/chứng chỉ |
| CA không được trust | Dừng, kiểm tra chain/truststore |
| Server chỉ cho TLS version không được phép | Sửa/upgrade server hoặc policy được phê duyệt |
| Cấu hình STARTTLS với port implicit TLS | Sửa TLS mode |
| Cấu hình implicit TLS với port STARTTLS | Sửa TLS mode |
| SMTP authentication sai | Kiểm tra credential/quyền, không retry liên tục cùng secret |
| Timeout sau DATA, không có phản hồi cuối | UNKNOWN, đối soát trước khi gửi lại |

**Lỗi handshake TLS xảy ra trước khi truyền nội dung email ở phiên SMTP được thiết lập đúng cách**, nên rủi ro gửi trùng từ chính lần handshake thất bại thường thấp. Tuy nhiên, muốn retry an toàn vẫn phải xét pha gửi đã thực sự xảy ra và dữ liệu từ transport, đặc biệt nếu code có nhiều lần gửi hoặc fallback phức tạp.

### Backoff và giới hạn

Nếu lỗi là tạm thời, một chính sách có thể dùng:

~~~text
retryDelay = min(maxDelay, initialDelay * 2^(attempt - 1)) + jitter
~~~

Ví dụ:

- Chờ 30 giây trước lần retry đầu.
- Nhân đôi khoảng chờ cho các lần tiếp theo.
- Giới hạn delay tối đa.
- Có max attempts và cảnh báo nếu lỗi kéo dài.
- Ghi trạng thái retry bền vững trong outbox nếu notification quan trọng.

Thời gian cụ thể cần dựa vào SLA và tải SMTP thực tế. **Không retry vô hạn bằng request thread** hoặc tạo hàng nghìn kết nối khi provider đang lỗi.

## 28. TLS khi gửi mail qua transaction/outbox

Spring Mail thường được gọi từ một service nghiệp vụ. Một sai lầm là giữ transaction database trong lúc kết nối SMTP, nhất là khi TLS handshake bị timeout.

Không nên:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    mailSender.send(...); // Chờ DNS, TCP, TLS, AUTH, DATA trong DB transaction
}
~~~

Nếu SMTP chậm, database lock hoặc transaction có thể bị giữ lâu. Nếu gửi thành công rồi transaction rollback, email đã nộp không thể bị “thu hồi” bằng rollback database.

Với email quan trọng, nên ghi một **notification outbox record** trong transaction nghiệp vụ, rồi để worker gửi sau commit:

~~~text
Transaction nghiệp vụ
   |
   +-- UPDATE order
   +-- INSERT notification_outbox
   |
 COMMIT
   |
   v
Worker claim outbox record
   |
 COMMIT claim
   |
   v
JavaMailSender: TCP -> TLS -> AUTH -> DATA
   |
   v
Worker cập nhật kết quả trong transaction riêng
~~~

Nhờ vậy, TLS handshake hoặc lỗi mạng không giữ transaction nghiệp vụ mở. Đồng thời outbox cho phép lưu trạng thái PENDING/RETRY/FAILED và đối soát kết quả gửi UNKNOWN.

Nhưng outbox **không tự bảo đảm exactly-once delivery**. Nếu SMTP đã nhận DATA rồi kết nối bị ngắt trước khi worker ghi kết quả, retry có thể tạo email trùng. Cần notification ID, attempt tracking, policy UNKNOWN và đối soát khi provider hỗ trợ.

## 29. Kiểm thử STARTTLS và SMTPS

Các lớp kiểm thử có mục tiêu khác nhau:

### Unit test cho service gửi mail

Có thể mock **JavaMailSender** để kiểm tra service tạo **MimeMessage** và gọi **send(...)** với recipient, subject và nội dung phù hợp.

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);

when(sender.createMimeMessage()).thenReturn(message);

AccountNotificationService service =
        new AccountNotificationService(sender);

service.sendSecurityNotice("test@example.net");

verify(sender).send(message);
~~~

Đây là ví dụ phác thảo dùng Mockito và Jakarta Mail **Session**. **Unit test bằng mock không chứng minh TLS đã được thiết lập** vì mock không mở kết nối TCP.

### Integration test với SMTP test server

Để kiểm tra transport, cần một SMTP server test hoặc sandbox phù hợp:

- Endpoint công bố STARTTLS trên port kiểm thử.
- Endpoint yêu cầu implicit TLS nếu muốn test port 465.
- Chứng chỉ test có hostname và CA được trust.
- Tài khoản test riêng, không dùng credential production.
- Có thể tạo tình huống không quảng bá STARTTLS hoặc certificate không hợp lệ.

Đặc biệt nên kiểm tra rằng ứng dụng **không gửi email plaintext khi cấu hình STARTTLS required nhưng server không hỗ trợ STARTTLS**.

### Bảng tình huống cần kiểm tra

| Cấu hình client | Server | Kết quả mong đợi |
|---|---|---|
| STARTTLS enable + required | Có STARTTLS, chứng chỉ hợp lệ | Gửi qua TLS |
| STARTTLS enable + required | Không quảng bá STARTTLS | Thất bại, không fallback plaintext |
| STARTTLS required | Chứng chỉ sai hostname | Thất bại khi kiểm tra danh tính server |
| Implicit TLS trên 465 | Server hỗ trợ implicit TLS hợp lệ | Kết nối và giao tiếp SMTP qua TLS |
| Implicit TLS trên 587 | Server chỉ hỗ trợ STARTTLS | Handshake/connection thất bại; sửa mode |
| STARTTLS trên 465 | Server yêu cầu TLS từ đầu | Có thể timeout/handshake lỗi; sửa mode |
| Đúng TLS, sai credential | Server từ chối AUTH | Lỗi xác thực, không gán nhãn TLS |
| Đúng TLS, provider 4xx tạm thời | SMTP từ chối lệnh rõ ràng | Retry theo SMTP reply/chính sách |
| Timeout sau DATA | Không rõ server đã accepted chưa | Trạng thái UNKNOWN/đối soát |

Không cố tình thử credential sai hàng loạt trên SMTP production vì có thể bị khóa tài khoản hoặc bị đánh dấu hoạt động bất thường.

## 30. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “STARTTLS là một giao thức mã hóa yếu hơn SMTPS” | Cả hai là cách đưa TLS vào phiên SMTP; khác biệt ở thời điểm bắt đầu TLS |
| “Port 465 bị loại bỏ nên không thể dùng” | Port 465 được dùng cho implicit TLS submission trong triển khai hiện đại |
| “Port 587 luôn được mã hóa” | Cần server hỗ trợ STARTTLS và client thực sự nâng cấp |
| “Bật starttls.enable là đủ” | Với yêu cầu bảo mật nghiêm ngặt nên đặt cả starttls.required |
| “Chỉ cần TLS handshake thành công” | Phải xác minh certificate chain và hostname |
| “ssl.trust=* là cách sửa lỗi chứng chỉ” | Đây là cách làm yếu xác thực endpoint |
| “SMTP AUTH bảo vệ mật khẩu dù không có TLS” | AUTH không thay thế mã hóa đường truyền |
| “TLS ở port 465 bảo mật email tới tận Inbox” | TLS đó chỉ bảo vệ chặng kết nối hiện tại |
| “Đã bật TLS thì không cần SPF/DKIM/DMARC” | Chúng phục vụ mục tiêu khác nhau |
| “SSLHandshakeException luôn retry được” | Sai mode hoặc certificate là lỗi cấu hình ổn định |
| “Spring Boot tự suy ra TLS mode theo port” | Cần khai báo rõ property phù hợp |
| “SMTP send thành công nghĩa là delivered” | Submission được chấp nhận không đồng nghĩa đã vào mailbox |

## 31. Bảng kiểm khi triển khai production

1. **Xác định SMTP endpoint** chính thức, host và port do provider công bố.
2. **Chọn TLS mode** phù hợp: STARTTLS trên endpoint hỗ trợ nâng cấp, hoặc implicit TLS trên endpoint yêu cầu mã hóa từ đầu.
3. **STARTTLS không fallback:** thiết lập enable và required khi dữ liệu cần bảo mật.
4. **Kiểm tra hostname:** bật mail.smtp.ssl.checkserveridentity=true.
5. **CA/truststore đúng:** kiểm tra chứng chỉ server và trust chain, không trust wildcard.
6. **TLS protocol phù hợp:** tránh ép dùng phiên bản cũ không được phép.
7. **SMTP AUTH:** chỉ truyền credential qua kênh TLS đã được xác minh; bảo vệ secret.
8. **Timeout hữu hạn:** connectiontimeout, timeout và writetimeout phù hợp với SLA.
9. **Cấu hình theo môi trường:** staging và production có secret/endpoints riêng; không để profile vô tình thay mode.
10. **Kiểm tra từ chính nơi ứng dụng chạy:** DNS, TCP, OpenSSL và certificate nếu gặp lỗi.
11. **Kiểm thử không fallback:** bắt buộc fail khi STARTTLS required mà server không hỗ trợ.
12. **Log an toàn:** ghi category/phase/correlation ID, không ghi credential hay MIME nhạy cảm.
13. **Retry có phân loại:** không retry mù khi certificate mismatch, auth lỗi hoặc outcome không rõ.
14. **Dùng outbox khi cần:** lưu ý định gửi bền vững và gửi ngoài transaction nghiệp vụ.
15. **Giám sát:** theo dõi TLS handshake failures, auth errors, submission status và queue age.

Danh sách là hướng dẫn triển khai, không thay thế chính sách bảo mật và quy trình vận hành của tổ chức.

## 32. Ghi nhớ

**STARTTLS** và **SMTPS (implicit TLS)** đều dùng TLS để bảo vệ giao tiếp giữa ứng dụng Spring và SMTP server. STARTTLS bắt đầu bằng phiên SMTP rồi nâng cấp lên TLS sau lệnh STARTTLS, thường trên **port 587**. Implicit TLS thiết lập TLS ngay từ đầu, thường trên **port 465**. Hai cách khác nhau về thứ tự bắt tay, không phải loại mã hóa mạnh yếu cố định.

Trong Spring Framework Mail, với **JavaMailSenderImpl**:

- STARTTLS: đặt **mail.smtp.starttls.enable=true** và **mail.smtp.starttls.required=true**.
- Implicit TLS: đặt **mail.smtp.ssl.enable=true**.
- Cả hai: bật **mail.smtp.ssl.checkserveridentity=true**, sử dụng CA/truststore đáng tin cậy, bảo vệ credential và cấu hình timeout hữu hạn.

Nếu kết nối lỗi, chẩn đoán lần lượt **DNS, TCP, TLS handshake, certificate/hostname, SMTP AUTH và SMTP response**, thay vì tắt TLS hoặc tăng timeout bừa bãi. Lỗi mạng sau DATA có thể dẫn tới trạng thái submission chưa rõ; đừng retry vô điều kiện và tạo email trùng.

**TLS an toàn đòi hỏi đúng endpoint, đúng chế độ, xác minh server và không hạ cấp xuống plaintext.** Kết hợp những nguyên tắc này với cách quản lý sender, outbox và lỗi gửi phù hợp sẽ giúp ứng dụng Spring gửi email qua SMTP đáng tin cậy hơn.



