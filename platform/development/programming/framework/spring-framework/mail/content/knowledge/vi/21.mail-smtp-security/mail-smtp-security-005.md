# Xác thực username, password và token trong Spring Framework Mail

Khi một ứng dụng Spring gửi email qua SMTP relay, máy chủ có thể yêu cầu ứng dụng chứng minh quyền truy cập tài khoản gửi. Thông tin xác thực có thể là **username/password**, **app password**, **SMTP credential do provider cấp**, hoặc **OAuth 2.0 access token**. Việc chọn đúng loại credential, cơ chế SMTP AUTH và cấu hình TLS quyết định khả năng gửi email an toàn, ổn định.

Spring Framework Mail cung cấp `JavaMailSender` để làm việc với SMTP thông qua Jakarta Mail/Angus Mail. Spring Boot có thể tự cấu hình sender bằng `spring.mail.*`, nhưng không tự xin OAuth token, quyết định provider-specific permissions hoặc làm mới token cho mọi dịch vụ. Các phần đó thuộc thiết kế hạ tầng và bảo mật của ứng dụng.

Bài học giải thích các cơ chế SMTP AUTH, cách cấu hình username/password, app password và OAuth2/XOAUTH2, cách bảo vệ secret, xử lý token expiry, chẩn đoán authentication failures và kiểm thử an toàn.

## 1. SMTP AUTH là gì?

SMTP là giao thức gửi và chuyển tiếp email. Ứng dụng tạo kết nối tới SMTP submission server, có thể nâng cấp kết nối bằng TLS, xác thực với máy chủ, rồi truyền envelope và nội dung email.

SMTP server có thể cho phép một số trường hợp relay không yêu cầu AUTH trong mạng nội bộ có chính sách chặt chẽ. Nhưng với authenticated submission của ứng dụng, SMTP AUTH thường được dùng để ngăn người lạ gửi qua tài khoản hoặc relay.

~~~text
Ứng dụng Spring
      |
      v
Kết nối SMTP
      |
      +--> TLS
      |
      +--> SMTP AUTH
      |       |
      |       +--> Username + password
      |       +--> Username + app password
      |       +--> Username + OAuth access token
      |
      +--> MAIL FROM / RCPT TO / DATA
      |
      v
SMTP server nhận hoặc từ chối message
~~~

Xác thực trả lời câu hỏi: **client có quyền sử dụng dịch vụ SMTP dưới danh tính được khai báo hay không?**

Nó không tự chứng minh:

- Bất kỳ địa chỉ From nào cũng được phép gửi.
- Domain có SPF/DKIM/DMARC đúng.
- Message đã được chấp nhận sau DATA.
- Message đã tới Inbox người nhận.
- Nội dung được mã hóa end-to-end.

Cần phân biệt **authentication**, **transport encryption**, **sender authorization**, **submission** và **delivery**.

## 2. Các thành phần cần phân biệt

| Thành phần | Vai trò | Ví dụ minh họa |
| --- | --- | --- |
| SMTP host | Máy chủ ứng dụng kết nối | `smtp.example.com` |
| SMTP port | Cổng và chế độ kết nối | `587` / `465` |
| Username | Định danh dùng với SMTP AUTH | `notifier@example.com` |
| Password | Secret cho password-based AUTH | Lưu trong vault |
| App password | Secret riêng cho ứng dụng nếu provider hỗ trợ | Lưu trong vault |
| SMTP API key | Một số provider cấp secret dùng như password | Theo tài liệu provider |
| OAuth access token | Token có scope/audience và hạn sử dụng | Truyền qua XOAUTH2 nếu được hỗ trợ |
| OAuth refresh token | Dùng xin access token mới từ token endpoint | Không gửi vào SMTP AUTH |
| AUTH mechanism | Cách client chứng minh credential | PLAIN, LOGIN, XOAUTH2 |
| Envelope sender | Địa chỉ `MAIL FROM` ở SMTP | `bounce@example.com` |
| MIME From | Địa chỉ hiển thị trong email | `Notifier <notifier@example.com>` |

Username không nhất thiết là email address. Một số provider dùng service account hoặc username được sinh riêng. Tương tự, từ “API key” không tự động có nghĩa là OAuth access token.

Không được đưa `password` hoặc `refresh token` vào DTO của use case chỉ vì một email cần gửi. Credential nên được chọn và lấy tại lớp hạ tầng.

## 3. SMTP AUTH nằm ở bước nào?

Một phiên SMTP dùng STARTTLS và AUTH có thể trông như sau:

~~~text
Client                                    SMTP server
  |                                            |
  |<------ 220 Service ready ------------------|
  |------- EHLO app.example.com -------------->|
  |<------ 250-STARTTLS -----------------------|
  |------- STARTTLS -------------------------->|
  |<------ 220 Ready for TLS ------------------|
  |======= TLS handshake ======================|
  |------- EHLO app.example.com -------------->|
  |<------ 250-AUTH PLAIN LOGIN XOAUTH2 -------|
  |------- AUTH [selected mechanism] --------->|
  |<------ 235 Authentication successful ------|
  |------- MAIL FROM:<sender@example.com> ---->|
  |<------ 250 OK -----------------------------|
  |------- RCPT TO:<user@example.net> -------->|
  |<------ 250 OK -----------------------------|
  |------- DATA ------------------------------>|
  |<------ 354 Continue -----------------------|
  |------- MIME message + DATA terminator ---->|
  |<------ 250 Accepted -----------------------|
~~~

Đây là transcript rút gọn. Không phải server nào cũng hỗ trợ tất cả những mechanism trong ví dụ.

`EHLO` cho biết server quảng bá các extension và cơ chế AUTH nào. Sau khi STARTTLS hoàn tất, client cần xem lại capability trên kênh TLS. Provider có thể yêu cầu TLS trước khi quảng bá hoặc chấp nhận AUTH.

`235` xác nhận authentication, **không** chứng minh mail đã được chấp nhận. Một SMTP response thành công sau bước DATA mới là bằng chứng submission ở hop hiện tại.

### Không ghi dữ liệu AUTH vào log

Ví dụ log an toàn nên che credential:

~~~text
C: AUTH PLAIN <redacted>
S: 235 Authentication successful
~~~

Không sao chép giá trị AUTH Base64 vào ticket: Base64 chỉ là encoding, không phải encryption.

## 4. AUTH PLAIN, AUTH LOGIN và password

`AUTH PLAIN` và `AUTH LOGIN` là hai cách xác thực username/password thường được SMTP server hỗ trợ. Chúng khác nhau về định dạng/challenge-response, nhưng đều dựa vào một secret tương đương password.

Trong quá trình trao đổi, dữ liệu có thể được encode Base64. Base64 không giữ bí mật; bất kỳ ai nhận được chuỗi đều có thể decode lại. Vì vậy:

1. Chỉ truyền password qua kết nối TLS đáng tin cậy.
2. Xác minh server certificate và hostname.
3. Không fallback về plaintext nếu policy yêu cầu mã hóa.
4. Không debug raw AUTH transcript trên production.
5. Không lưu password trong code, payload hàng đợi hoặc telemetry.

Bảng phân biệt:

| Công nghệ | Giải quyết vấn đề |
| --- | --- |
| SMTP AUTH | Client được phép dùng SMTP relay không |
| STARTTLS | Nâng SMTP connection lên TLS |
| Implicit TLS | TLS ngay từ lúc mở kết nối |
| Base64 | Biểu diễn dữ liệu dạng ASCII; không bảo mật |
| OAuth2 | Cấp token và quyền sử dụng dịch vụ |
| SPF/DKIM/DMARC | Một phần hệ sinh thái xác thực domain và chống giả mạo |

Đừng nhầm AUTH với mã hóa đường truyền.

## 5. Cấu hình username/password qua Spring Boot

Ứng dụng có dependency `spring-boot-starter-mail` có thể cấu hình `JavaMailSender` bằng YAML:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Giải thích:

| Thuộc tính | Tác dụng |
| --- | --- |
| `spring.mail.host` | Địa chỉ SMTP server |
| `spring.mail.port` | SMTP port |
| `spring.mail.username` | Danh tính AUTH |
| `spring.mail.password` | Secret của cơ chế AUTH |
| `mail.smtp.auth` | Cho phép SMTP authentication |
| `mail.smtp.starttls.enable` | Sử dụng STARTTLS khi hỗ trợ |
| `mail.smtp.starttls.required` | Bắt buộc STARTTLS thành công |
| `mail.smtp.ssl.checkserveridentity` | Kiểm tra hostname của server certificate |
| `mail.smtp.connectiontimeout` | Timeout mở kết nối |
| `mail.smtp.timeout` | Timeout đọc |
| `mail.smtp.writetimeout` | Timeout ghi |

Cú pháp `"[mail.smtp.auth]"` giúp giữ nguyên dấu chấm trong key khi bind map từ YAML. Trong `application.properties` có thể dùng tên dotted properties trực tiếp.

Giá trị `SMTP_PASSWORD` phải được runtime cung cấp từ môi trường được kiểm soát hoặc secret manager; không commit secret thật vào repository.

### Ví dụ gửi email đơn giản

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationService {

    private final JavaMailSender mailSender;

    public AccountNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(recipient);
        message.setSubject("Thông báo tài khoản");
        message.setText("Tài khoản của bạn đã được cập nhật.");

        mailSender.send(message);
    }
}
~~~

Service không nhận password làm tham số. `JavaMailSender` đã được cấu hình ở hạ tầng; application chỉ yêu cầu gửi thông điệp.

Nếu cần HTML, attachment hoặc inline resource, dùng `MimeMessage` và `MimeMessageHelper` nhưng không thay đổi nguyên tắc lưu credential.

## 6. Cấu hình TLS: STARTTLS và implicit TLS

Hai chế độ submission thường gặp:

| Chế độ | Port phổ biến | Trình tự |
| --- | ---: | --- |
| STARTTLS | 587 | Kết nối SMTP rồi nâng lên TLS |
| Implicit TLS | 465 | TLS handshake ngay khi kết nối |
| SMTP relay giữa mail servers | 25 | Phụ thuộc chính sách relay, không mặc định dành cho authenticated app submission |

Provider có thể dùng cổng riêng, do đó phải kiểm tra tài liệu dịch vụ đang sử dụng.

### STARTTLS trên port 587

~~~properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

`starttls.enable` cho phép STARTTLS; `starttls.required` yêu cầu kết nối phải nâng cấp thành công thay vì tiếp tục trên plaintext nếu server không hỗ trợ.

### Implicit TLS trên port 465

~~~properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

Ở chế độ này, TLS bắt đầu ngay từ kết nối. Thông thường không bật STARTTLS trên cùng connection implicit TLS.

### Không bỏ qua xác minh certificate

Không dùng `mail.smtp.ssl.trust=*` hoặc tắt hostname validation để chữa lỗi TLS trên production. Cách đó mở ra rủi ro kết nối tới endpoint giả mạo.

Khi gặp TLS handshake error, kiểm tra hostname/port, certificate chain, CA, trust store, thời hạn certificate, TLS version và proxy/firewall. Cần sửa trust configuration đúng thay vì bỏ qua kiểm tra.

TLS bảo vệ dữ liệu khi truyền tới SMTP hop mà ứng dụng kết nối; nó không mã hóa email end-to-end ở mọi hop.

## 7. App password khác password đăng nhập thường

Một số provider cho phép tạo **app password** dành riêng cho ứng dụng hoặc thiết bị, thay vì đưa password đăng nhập chính vào SMTP client.

Ưu điểm có thể có:

- Có thể thu hồi riêng mà không thay đổi password chính.
- Dễ theo dõi một credential của workload.
- Hỗ trợ client không có interactive MFA.
- Hạn chế tác động nếu chỉ một ứng dụng bị lộ secret.

Nhưng không phải provider nào cũng hỗ trợ app password. Chính sách tổ chức có thể cấm app password và yêu cầu OAuth. App password vẫn là một secret nhạy cảm và phải bảo vệ như mật khẩu.

| Tiêu chí | App password | OAuth access token |
| --- | --- | --- |
| Dạng | Secret kiểu password | Token cấp quyền |
| Cơ chế thường gặp | PLAIN/LOGIN qua TLS | XOAUTH2 nếu SMTP hỗ trợ |
| Thời hạn | Theo provider và policy | Thường ngắn hạn |
| Scope | Theo chính sách account/provider | Scope/audience/permission được cấp |
| Rotation | Thay/thu hồi credential | Xin token mới hoặc revoke grant |
| Refresh | Không theo OAuth refresh flow | Qua token provider/OAuth grant |

Không dùng app password làm XOAUTH2 token. Cơ chế xác thực phải khớp loại credential.

## 8. API key hoặc generated SMTP credential

Một số Email Service Provider cấp SMTP username và một secret có tên API key, SMTP key hoặc generated password. Provider có thể yêu cầu truyền secret đó như password của `AUTH PLAIN/LOGIN`.

Ví dụ:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${PROVIDER_SMTP_USERNAME}
    password: ${PROVIDER_SMTP_SECRET}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

Tên “API key” **không có nghĩa tự động dùng XOAUTH2**. Một HTTP API key, SMTP secret và OAuth access token có cách sử dụng khác nhau. Chỉ định auth mechanism theo tài liệu provider.

Nếu được, cấp secret có quyền SMTP/send tối thiểu thay vì dùng credential quản trị toàn bộ account.

## 9. OAuth 2.0 và XOAUTH2

OAuth2 cho phép ứng dụng lấy **access token** từ authorization server. Một số SMTP service hỗ trợ cơ chế `XOAUTH2` để dùng token thay password dài hạn.

~~~text
Application
     |
     +---> OAuth authorization/token service
     |          |
     |          +--> grant / permission check
     |          +--> access token
     |
     +---> SMTP submission server
                |
                +--> TLS
                +--> AUTH XOAUTH2
                        |
                        +--> mailbox identity
                        +--> OAuth access token
                |
                +--> MAIL FROM / RCPT TO / DATA
~~~

Để hoạt động, cần đồng thời:

- SMTP server và JavaMail implementation hỗ trợ XOAUTH2.
- Token được cấp cho đúng resource/audience.
- Token có scope/permission SMTP thích hợp.
- Mailbox identity phù hợp với quyền token.
- Provider/tenant cho phép SMTP AUTH và flow OAuth đã chọn.
- TLS bảo vệ token trên đường truyền.

Không phải mọi provider đều hỗ trợ cùng OAuth grant. Có nơi yêu cầu delegated user consent, nơi khác có application permission hoặc service principal cùng điều kiện admin configuration. Việc có client ID và client secret không tự chứng minh client-credentials grant được phép gửi SMTP cho mailbox đó.

**Refresh token, nếu flow có cấp, không phải credential đưa vào SMTP.** Nó chỉ dùng để xin access token mới tại token endpoint.

## 10. Chọn auth mechanism XOAUTH2 trong Jakarta Mail

Với Jakarta Mail/Angus Mail có hỗ trợ XOAUTH2, có thể dùng:

~~~properties
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

Trong API SMTP client tương ứng, username thường là mailbox identity; access token được truyền ở vị trí password parameter khi mechanism là XOAUTH2.

Ví dụ factory dựng cấu hình sender cho một token:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class OAuthSmtpSenderFactory {

    public JavaMailSenderImpl create(
            String host,
            int port,
            String mailbox,
            String accessToken) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(mailbox);
        sender.setPassword(accessToken);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.auth.mechanisms", "XOAUTH2");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

Factory nhận **access token hợp lệ đã được cấp**, không tự thực hiện OAuth flow. Nó dành cho port 587/STARTTLS theo ví dụ; nếu provider yêu cầu 465/implicit TLS, cần cấu hình transport tương ứng.

Nếu chọn XOAUTH2 nhưng đưa app password vào `setPassword`, server có thể từ chối. Ngược lại, đặt access token vào password nhưng client chỉ chọn PLAIN/LOGIN cũng không đảm bảo server chấp nhận. Token type, mechanism và provider policy phải khớp.

## 11. Tách token provider khỏi SMTP transport

Trong môi trường thật, OAuth access token có thể hết hạn và cần làm mới. Không nên lấy token đúng một lần khi khởi động ứng dụng rồi dùng mãi. Nên thiết kế riêng:

1. **Mail access token provider**: trả về một token hợp lệ cho account, audience và permission cần thiết.
2. **SMTP adapter**: chọn XOAUTH2, cấu hình kết nối TLS và submit message.
3. **Application use case**: chỉ ra yêu cầu gửi email, không nhận raw token hoặc SMTP secret.

Contract:

~~~java
public interface MailAccessTokenProvider {

    /**
     * Implementation lấy token thích hợp cho SMTP mailbox.
     * Có thể cache và refresh theo OAuth flow đã được provider cho phép.
     */
    String getValidAccessToken(String mailbox);
}
~~~

Một adapter minh họa:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OAuth2SmtpMailAdapter {

    private final MailAccessTokenProvider tokenProvider;
    private final OAuthSmtpSenderFactory senderFactory;
    private final String host;
    private final int port;
    private final String mailbox;

    public OAuth2SmtpMailAdapter(
            MailAccessTokenProvider tokenProvider,
            OAuthSmtpSenderFactory senderFactory,
            String host,
            int port,
            String mailbox) {

        this.tokenProvider = tokenProvider;
        this.senderFactory = senderFactory;
        this.host = host;
        this.port = port;
        this.mailbox = mailbox;
    }

    public void send(
            String recipient,
            String subject,
            String body) throws MessagingException {

        String accessToken =
            tokenProvider.getValidAccessToken(mailbox);

        JavaMailSenderImpl sender = senderFactory.create(
            host,
            port,
            mailbox,
            accessToken
        );

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(mailbox);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        sender.send(message);
    }
}
~~~

Ví dụ chỉ mô tả luồng hợp tác giữa token provider và transport. Chưa triển khai OAuth client, token endpoint, credential store, retry hoặc permission check. Các phần đó phải dựa trên provider được chọn và thư viện OAuth phù hợp.

### Vì sao không đổi password trên sender dùng chung?

Không nên làm:

~~~java
sharedSender.setUsername(tenantA);
sharedSender.setPassword(tokenForTenantA);
sharedSender.send(messageA);

// Một thread khác có thể thay đổi username/password
// trước khi thread A dùng xong cấu hình.
~~~

Trong môi trường có nhiều worker/tenant, mutate credential trên một instance dùng chung có thể tạo race condition, lỗi đăng nhập ngẫu nhiên hoặc gửi bằng sai account.

Factory trong ví dụ tạo sender configuration riêng cho từng attempt, tránh chia sẻ mutable credential. Ở hệ thống lớn, có thể tối ưu transport pooling, nhưng phải quản lý session/account/token state theo cách thread-safe.

## 12. Token expiry, refresh và clock skew

Access token thường mang thông tin thời hạn như `expires_in` hoặc `expires_at`. Khi token hết hạn, SMTP provider có thể từ chối AUTH ngay cả khi cấu hình host, username và TLS hoàn toàn đúng.

Token provider nên chịu trách nhiệm:

- Cache access token theo đúng account, audience và permission.
- Lưu thời điểm hết hạn từ OAuth response.
- Làm mới sớm trước khi token thực sự hết hạn.
- Bù một khoảng clock skew phù hợp.
- Giới hạn số request cùng xin token cho một account.
- Phân biệt lỗi token endpoint tạm thời với permission bị từ chối.
- Không log raw access token.
- Kiểm soát việc revoke/rotate credential gốc.

Luồng:

~~~text
Mail worker cần gửi
       |
       v
Token provider
       |
       v
Token cache có token còn đủ hạn?
       |
    +--+--+
    |     |
   Có    Không
    |     |
    |     v
    |   Xin token mới bằng OAuth flow thích hợp
    |     |
    +--+--+
       |
       v
SMTP AUTH XOAUTH2 trên TLS
       |
       v
Gửi MIME message
~~~

Nếu token chỉ còn vài giây, kết nối hoặc AUTH có thể bắt đầu sau khi token hết hạn. Nên đặt safety margin theo độ trễ thực tế và provider policy.

### Refresh token không phải SMTP password

Nếu OAuth flow cấp refresh token, token đó chỉ được gửi tới **OAuth token endpoint** khi xin access token mới. Không cấu hình:

~~~properties
spring.mail.password=<refresh-token>
~~~

rồi kỳ vọng XOAUTH2 hoạt động. Một số flow như client credentials có thể xin access token mới mà không dùng refresh token; không phải mọi hệ thống đều có refresh token.

### Tránh refresh stampede

Khi 100 worker phát hiện token gần hết hạn, nếu cả 100 cùng gọi token endpoint, ứng dụng có thể bị rate limit hoặc tăng lỗi. Token provider có thể dùng lock/single-flight cho cùng account và token audience.

Khi nhiều instance cần token, có thể cân nhắc cơ chế cache/quản lý token phù hợp. Nhưng shared cache phải có kiểm soát truy cập và mã hóa; không lưu token plaintext ở nơi mọi service đều đọc được.

## 13. Xử lý access token hết hạn trong lúc gửi

Token có thể hết hạn hoặc bị thu hồi giữa lúc lấy và lúc SMTP thực hiện AUTH. Trong trường hợp đó, adapter có thể nhận authentication failure.

Cần phân biệt:

- Token hết hạn và có thể xin token mới.
- Token thiếu scope/audience đúng.
- OAuth grant không được SMTP provider hỗ trợ.
- SMTP AUTH bị tắt cho account/tenant.
- Mailbox identity không đúng với quyền token.
- Permission/admin consent đã bị thu hồi.
- Token endpoint hoặc identity provider đang gặp sự cố.

Một chiến lược thận trọng:

1. Xác nhận lỗi xảy ra ở **AUTH**, trước MAIL FROM/DATA.
2. Kiểm tra token cache, expiry và error code.
3. Nếu token có thể stale, invalidate cache.
4. Xin một access token mới theo chính sách.
5. Thử lại một lần có giới hạn nếu phù hợp.
6. Nếu vẫn thất bại, dừng retry dày đặc và cảnh báo để xử lý permission/policy.

Không catch mọi `MailAuthenticationException` rồi refresh token vô hạn. Nếu lỗi do thiếu scope hoặc provider cấm SMTP, xin thêm token giống hệt sẽ không giúp.

Một lỗi AUTH rõ ràng xảy ra trước DATA thường chưa tạo submission trong attempt đó. Tuy nhiên, không áp dụng quy tắc “retry an toàn” cho timeout sau DATA, vì server có thể đã nhận message.

## 14. Authentication và sender authorization khác nhau

Một account có thể xác thực thành công nhưng không được phép gửi từ mọi địa chỉ.

Ví dụ SMTP username:

~~~text
notifications@example.com
~~~

nhưng message đặt:

~~~java
helper.setFrom("finance@example.com");
~~~

Provider có thể yêu cầu:

- Header From phải khớp mailbox đăng nhập.
- From thuộc verified domain.
- Alias đã được xác minh.
- Account được cấp quyền gửi thay mặt một mailbox khác.
- Envelope sender tuân theo policy của relay.

Khi nhận lỗi như “sender not permitted”, cần phân biệt lỗi AUTH và lỗi sender authorization.

### MAIL FROM và MIME From

- `MAIL FROM` là địa chỉ SMTP envelope/return path trong phiên giao tiếp.
- `From` trong MIME header là địa chỉ hiển thị cho người nhận.

Hai địa chỉ có thể khác nhau theo chính sách gửi, bounce processing và email provider. Xác thực thành công không tự cho phép sử dụng bất kỳ giá trị nào ở cả hai trường.

Ngoài ra, SPF/DKIM/DMARC là những lớp xác thực/đánh giá domain khác, không được thay thế bởi việc đăng nhập SMTP thành công.

## 15. Quản lý password và token bằng secret store

Không hard-code credential:

~~~java
sender.setUsername("notifications@example.com");
sender.setPassword("hardcoded-secret");
~~~

Nếu secret bị commit lên Git, đưa vào artifact build hoặc log, việc thu hồi rất khó và có thể ảnh hưởng nhiều môi trường.

Các cách quản lý phù hợp hơn:

- Secret manager hoặc vault.
- Environment variable được runtime/orchestrator inject.
- Encrypted deployment secret với quyền truy cập giới hạn.
- Workload identity khi provider hỗ trợ.
- Token provider quản lý OAuth grant, client secret/certificate và rotation.

Ví dụ `application.yml` chỉ giữ reference:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

**Environment variable không tự động an toàn tuyệt đối.** Có thể bị lộ qua quyền xem cấu hình container, process inspection, crash dump hoặc pipeline log nếu không bảo vệ. Cần áp dụng nguyên tắc least privilege cho người dùng và workload.

### Không lưu token vào outbox

Mail outbox chứa yêu cầu gửi và metadata nghiệp vụ; không nên chứa SMTP password, app password, access token hoặc refresh token. Worker lấy credential vào thời điểm thực hiện gửi.

Nếu một job chờ vài giờ trong outbox, access token gắn vào payload từ lúc enqueue gần như chắc chắn không còn thích hợp. Token provider giải quyết chính xác vấn đề này.

### Không log credential

Tránh:

~~~java
log.info("SMTP password: {}", password);
log.debug("OAuth access token: {}", token);
~~~

Nếu cần chẩn đoán, log credential **source identifier**, tenant ID, provider ID, expiry timestamp hoặc token status, không log raw token/password và cũng không log AUTH Base64 string.

## 16. Rotation và thu hồi credential

Credential phải có vòng đời quản lý. Một ứng dụng có thể hoạt động nhiều tháng, còn password, app password và client secret có thể phải thay đổi định kỳ hoặc khi nghi ngờ lộ.

### Với password/app password

1. Tạo secret mới với quyền phù hợp.
2. Lưu secret mới trong secret manager.
3. Cập nhật deployment/secret reference của ứng dụng.
4. Kiểm thử một email với account test hoặc đường gửi kiểm soát.
5. Quan sát auth failures và queue backlog.
6. Thu hồi secret cũ khi mọi instance đã chuyển sang secret mới.
7. Ghi audit mà không lưu secret trong log.

Nếu provider hỗ trợ hai secret hợp lệ trong giai đoạn chuyển đổi, có thể áp dụng thời gian overlap để giảm downtime. Nếu không, cần có kế hoạch chuyển đổi hoặc tạm dừng gửi an toàn.

### Với OAuth client secret hoặc certificate

Client secret dùng để xin access token là credential khác với access token dùng tại SMTP. Rotation client secret/certificate cần cập nhật token provider và có thể không lập tức vô hiệu hóa mọi access token đang hoạt động. Cách revoke phụ thuộc provider.

Một token bị thu hồi hoặc permission bị gỡ phải khiến worker dừng thử vô ích và đưa job vào trạng thái cần xử lý, thay vì tiếp tục gửi với cùng token đã lỗi.

## 17. Chọn password, app password, generated key hay OAuth

| Nhu cầu | Cơ chế thường phù hợp | Cần xác minh |
| --- | --- | --- |
| SMTP relay nội bộ cấp username/password | Password-based AUTH qua TLS | Permission, rotation |
| ESP cấp SMTP key riêng | Generated SMTP credential | Username và cách đặt secret |
| Provider cho phép app password | App password qua TLS | Chính sách account/tenant |
| Provider yêu cầu modern authentication | OAuth access token + XOAUTH2 | SMTP capability, audience, scope, grant |
| Provider chỉ cung cấp HTTP send API | HTTP mail adapter | Không ép API secret vào SMTP |
| Nhiều tenant/account | Credential resolver theo tenant | Isolation và concurrency |
| Số lượng gửi lớn | Credential/service account riêng | Quota, rate limit, audit |

Không chọn OAuth chỉ vì nó mới hơn nếu provider không hỗ trợ SMTP XOAUTH2 cho loại account đó. Ngược lại, không tiếp tục dùng username/password truyền thống khi provider/tenant đã ngừng cho phép.

## 18. Những mã lỗi xác thực thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `530 Authentication required` | Chưa AUTH hoặc security flow chưa đạt yêu cầu | Kiểm tra SMTP AUTH và TLS |
| `535 Authentication credentials invalid` | Credential bị từ chối hoặc policy không cho phép | Secret, mechanism, account status, permission |
| `534` liên quan authentication policy | Cơ chế hiện tại không được chấp nhận | Provider guidance/enhanced code |
| `454 Temporary authentication failure` | Dịch vụ AUTH tạm lỗi | Backoff/retry có giới hạn |
| `503 Bad sequence of commands` | Thứ tự SMTP commands sai | Transcript và transport config |
| `AuthenticationFailedException` | Jakarta Mail báo AUTH thất bại | Nested exception và response |
| `MailAuthenticationException` | Spring wrapper cho lỗi xác thực | SMTP response, cause |
| TLS handshake failure | Chưa thiết lập TLS hợp lệ | Port, certificate, trust store |
| AUTH timeout | Network/server chậm | Phase, timeout, provider outage |
| Sender not authorized sau AUTH | Không được dùng địa chỉ gửi | Send-as, verified domain, envelope |

Một mã như `535` không phải lúc nào cũng đơn thuần là password gõ sai. Có thể do account bị khóa, SMTP AUTH bị tắt, app password hết hiệu lực, OAuth token thiếu quyền hoặc provider policy mới.

### Đọc lỗi theo SMTP phase

~~~text
S: 235 Authentication successful
C: MAIL FROM:<different@example.com>
S: 550 Sender not permitted
~~~

Ở đây AUTH đã thành công. Đổi password không giải quyết được chính sách sender.

Nếu lỗi xảy ra trước DATA, chưa có bằng chứng server nhận message. Nếu client timeout sau khi gửi DATA, kết quả submission có thể mơ hồ; không quy mọi timeout về lỗi AUTH.

## 19. Retry lỗi xác thực cần giới hạn

| Tình huống | Retry? | Lý do |
| --- | --- | --- |
| Password sai chắc chắn | Không retry liên tục | Có thể dẫn đến lockout |
| SMTP AUTH bị tắt bằng policy | Không | Cần sửa cấu hình/permission |
| Token hết hạn và refresh được | Có thể refresh rồi retry một lần | Sửa credential trước khi gửi |
| Token thiếu scope/audience | Không retry nguyên trạng | Xin đúng quyền |
| SMTP AUTH service trả lỗi tạm thời | Có thể dùng exponential backoff | Provider có thể phục hồi |
| TLS certificate sai | Không bỏ qua certificate | Cần sửa trust/endpoint |
| Connection timeout trước AUTH | Có thể retry nếu transient | Chưa submit trong attempt đó |
| Timeout sau DATA | Không xem như auth failure | Có nguy cơ duplicate |

Lỗi xác thực lặp lại có thể kích hoạt cảnh báo bảo mật, khóa account hoặc bị provider throttling. Vì vậy, nếu có 100 email đang chờ, không để 100 worker liên tục thử cùng credential sai.

Một cơ chế cooldown/circuit breaker theo account/provider sẽ giúp giảm lỗi hàng loạt. Sau khi sửa credential, worker có thể tiếp tục xử lý outbox theo rate và deadline policy.

## 20. Multi-tenant và concurrency

Một ứng dụng có thể gửi từ nhiều mailbox hoặc nhiều tenant. Nếu các thread cùng mutate một `JavaMailSenderImpl` singleton:

~~~text
Thread A: setUsername(tenant A)
Thread B: setUsername(tenant B)
Thread A: send(message A)   -> có thể dùng sai account
~~~

Đây là vấn đề state sharing. Không dùng một mutable sender global rồi đổi username/password trước từng email.

Thiết kế nên có:

1. Use case cung cấp tenant ID hoặc sender account ID.
2. Credential resolver trả về cấu hình hợp lệ cho account đó.
3. OAuth token provider dùng đúng mailbox/audience/permission.
4. SMTP adapter tạo hoặc chọn transport configuration an toàn cho concurrency.
5. Rate limiter áp dụng theo account/provider.
6. Audit lưu account ID, không lưu secret.

Nếu tenant được phép khai báo SMTP host riêng, cần validate endpoint và kiểm soát network access để tránh SSRF hoặc truy cập service nội bộ không được phép. Không lấy raw SMTP URL từ HTTP request rồi kết nối tùy ý.

## 21. Authentication trong mail worker và outbox

Một email giao dịch quan trọng có thể được gửi sau khi transaction nghiệp vụ commit, qua outbox worker:

~~~text
Business use case
       |
       v
Save outbox job
       |
       v
Worker claim job
       |
       +--> Resolve account
       +--> Fetch secret/access token
       +--> TLS + SMTP AUTH
       +--> Submit message
       |
       +--> SUBMITTED / RETRY_WAIT / FAILED
~~~

Điểm cần nhớ:

- Outbox job không chứa credential.
- Worker lấy token mới nếu token cũ đã hết hạn.
- Secret rotation không buộc phải thay payload cũ.
- Worker không giữ database transaction trong lúc chờ OAuth token endpoint hoặc SMTP server.
- Authentication failure có thể ảnh hưởng nhiều job cùng account; áp dụng cooldown/alert thay vì retry nóng.
- SMTP AUTH success không đồng nghĩa email đã được server chấp nhận sau DATA.
- Nếu lỗi kết nối xảy ra sau DATA, có thể có kết quả submission AMBIGUOUS; phải cân nhắc duplicate.

Thông báo `SUBMITTED` chỉ phản ánh transport acceptance theo bằng chứng API/provider. `DELIVERED` là bước tiếp theo, cần sự kiện giao thư riêng nếu provider hỗ trợ.

## 22. Kiểm thử không cần password production

### Unit test

Có thể mock `MailAccessTokenProvider` và delivery adapter để kiểm tra:

- Lấy token theo đúng mailbox/tenant.
- Token provider báo lỗi thì không gửi.
- Không reuse token đã hết hạn.
- Auth failure được phân loại đúng.
- Các request đồng thời không bị trộn credential.
- Không log password hoặc access token.

### SMTP integration test

Sử dụng SMTP test server phù hợp để kiểm tra:

- AUTH PLAIN/LOGIN với credential giả.
- STARTTLS/implicit TLS với test certificate.
- Authentication failure response.
- Message được submit sau khi AUTH thành công.
- Client không tiếp tục gửi nếu STARTTLS required nhưng server không hỗ trợ.

Không phải SMTP test server nào cũng hỗ trợ XOAUTH2. Kiểm thử XOAUTH2 có thể cần stub hỗ trợ đúng mechanism hoặc sandbox của provider.

### Provider sandbox

Đối với provider thực tế, kiểm tra:

- SMTP AUTH capability được quảng bá.
- TLS mode/hostname verification.
- OAuth token scope/audience/grant.
- Send-as permission và verified domain.
- Token expired/revoked behavior.
- Quota và throttling.
- Provider message acceptance sau DATA.

Dùng tài khoản và recipient test; không đưa dữ liệu production vào test.

## 23. SMTP debug log và bảo mật

Jakarta Mail có cơ chế protocol debug. Trong môi trường kiểm thử có kiểm soát, có thể bật:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Không bật lâu dài trên production nếu chưa kiểm soát dữ liệu nhạy cảm: tùy phiên bản và configuration, transcript có thể chứa envelope, địa chỉ người nhận, header, AUTH metadata hoặc secret.

Trình tự điều tra:

1. Kiểm tra host, port, DNS và network.
2. Xác nhận STARTTLS hoặc implicit TLS đúng.
3. Kiểm tra server certificate và hostname.
4. Xem EHLO capabilities và AUTH mechanisms.
5. Kiểm tra client chọn đúng PLAIN/LOGIN/XOAUTH2.
6. Đọc response của AUTH mà không lộ credential.
7. Sau `235`, kiểm tra sender permission nếu bị từ chối.
8. Sau đó kiểm tra RCPT TO, DATA và final submission response.
9. Tắt debug và xử lý retention/redaction.

Nếu server không quảng bá `XOAUTH2`, việc đưa token vào password không khiến cơ chế tự hoạt động. Nếu server quảng bá XOAUTH2 nhưng token sai audience/permission, AUTH cũng có thể thất bại.

## 24. Runbook khắc phục SMTP authentication failure

**Bước 1 — Khoanh vùng**

- Lỗi ở tất cả tenant hay chỉ một account?
- Có vừa rotate secret hoặc deploy phiên bản mới?
- Có provider policy change hoặc account lockout?
- Lỗi bắt đầu ở TLS, AUTH hay MAIL FROM?

**Bước 2 — Kiểm tra credential**

- Secret reference có tồn tại?
- Workload có quyền đọc secret?
- Username/mailbox có đúng?
- Password/app password có bị thu hồi?
- Access token có hết hạn?
- Token có đúng audience/scope/permission?
- SMTP AUTH có bị tắt theo tenant policy?

**Bước 3 — Kiểm tra transport**

- Host/port và TLS mode khớp tài liệu.
- Certificate chain/hostname hợp lệ.
- AUTH mechanism đúng với credential type.
- Không bật fallback plaintext.

**Bước 4 — Khôi phục**

- Rotate/update secret nếu sai hoặc bị lộ.
- Refresh token theo grant hợp lệ.
- Xin permission/admin consent nếu bị thiếu.
- Giảm tốc độ/cooldown nếu provider tạm lỗi.
- Cân nhắc chuyển provider-approved auth flow hoặc HTTP mail API nếu SMTP AUTH hiện tại không được hỗ trợ.

**Bước 5 — Xác minh**

- Gửi một message test có correlation ID.
- Xác nhận SMTP AUTH thành công.
- Xác nhận server chấp nhận DATA theo response cuối.
- Theo dõi outbox backlog.
- Theo dõi delivery event/bounce nếu provider có.

Không xóa job lỗi để làm queue trống; cần giữ trạng thái và xử lý đúng theo retry/dead-letter policy.

## 25. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách thay thế |
| --- | --- | --- |
| Hard-code password | Secret lộ qua Git/artifact | Vault/environment injection |
| Dùng personal account password cho service | Quyền rộng, khó rotation | Service account hoặc credential riêng |
| AUTH qua plaintext | Lộ credential trên đường truyền | Require TLS |
| STARTTLS enable nhưng cho fallback plaintext | Có thể không mã hóa | STARTTLS required |
| Tắt hostname verification | Dễ kết nối nhầm SMTP server | Validate certificate/hostname |
| Dùng `ssl.trust=*` để bypass TLS lỗi | Phá trust boundary | Sửa CA/trust store |
| Dùng XOAUTH2 với app password | Sai loại credential | Chọn mechanism đúng |
| Đưa refresh token vào SMTP password | Sai flow, lộ secret dài hạn | Chỉ dùng access token |
| Cache token vô thời hạn | Auth lỗi khi hết hạn | Refresh và clock skew |
| Đổi credential trên shared sender | Race condition giữa worker | Per-account/thread-safe adapter |
| Retry vô hạn password sai | Lockout và overload | Fail fast/cooldown/alert |
| Lưu token trong outbox | Secret lộ, token hết hạn | Fetch tại lúc gửi |
| In SMTP AUTH transcript | Lộ secret và PII | Redaction/debug giới hạn |
| Nhầm AUTH success với delivered | Báo sai trạng thái mail | Theo dõi DATA/delivery riêng |
| Nhầm HTTP API key với OAuth token | Cấu hình sai mechanism | Theo đúng provider contract |
| Bỏ qua send-as permission | AUTH thành công nhưng gửi bị chặn | Verify sender identity |

## 26. Quy trình triển khai

Một luồng triển khai rõ ràng:

1. **Xác định SMTP provider/account policy** và auth mechanisms được hỗ trợ.
2. **Chọn credential**: SMTP password, app password, generated secret hoặc OAuth access token.
3. **Thiết lập TLS bắt buộc** với hostname/certificate validation.
4. **Lưu secret an toàn** trong vault hoặc runtime secret injection.
5. **Với password-based AUTH**, cấu hình `spring.mail.username/password`.
6. **Với OAuth**, triển khai token provider, XOAUTH2 và quyền SMTP phù hợp.
7. **Tách mail adapter khỏi use case**; không truyền credential qua nghiệp vụ.
8. **Quản lý rotation/expiry** và tránh token refresh stampede.
9. **Phân loại AUTH/TLS/sender-policy failures** thay vì retry mọi lỗi.
10. **Với email quan trọng**, lưu outbox và lấy credential ở worker khi thực thi.
11. **Kiểm thử** với fake/test SMTP và provider sandbox.
12. **Giám sát** auth failure, token refresh error, queue backlog và credential expiry.

~~~text
Use case cần gửi mail
       |
       v
MailDeliveryPort
       |
       v
SMTP adapter
       |
       +--> Resolve provider / sender account
       |
       +--> Resolve credential
       |       |
       |       +--> SMTP password/app key từ vault
       |       +--> Access token từ token provider
       |
       +--> TLS connection
       |
       +--> AUTH PLAIN/LOGIN/XOAUTH2
       |       |
       |       +--> 235 success
       |       +--> 4xx/5xx failure
       |
       +--> MAIL FROM / RCPT TO / DATA
       |
       v
Submission outcome
       |
       +--> SUBMITTED
       +--> RETRY_WAIT / FAILED / AMBIGUOUS
~~~

## 27. Ghi nhớ

- SMTP AUTH chứng minh quyền sử dụng relay, không phải email đã delivered.
- Username có thể là mailbox hoặc service account, tùy provider.
- Password, app password, SMTP-generated secret và OAuth token là các loại credential khác nhau.
- AUTH PLAIN/LOGIN dựa trên password-like credential; Base64 không phải encryption.
- XOAUTH2 dùng **access token** phù hợp, không dùng refresh token.
- Bảo vệ credential bằng STARTTLS required hoặc implicit TLS cùng certificate/hostname validation.
- Spring Boot có `spring.mail.username/password` và JavaMail properties; không tự động xin/refresh mọi OAuth token.
- Token phải có đúng scope/audience/permission và được provider cho phép với SMTP.
- Token provider cần cache/refresh/clock skew/cooldown và không log raw token.
- Tránh sửa username/password trên `JavaMailSenderImpl` shared khi có nhiều request.
- AUTH thành công không tự cho phép gửi từ mọi From address.
- Secret không thuộc entity nghiệp vụ hoặc mail outbox payload.
- Rotation và least privilege phải được thiết kế từ đầu.
- Auth errors phải được phân loại; không retry vô hạn credential bị từ chối.
- Test TLS, authentication, sender permission và token expiry ở môi trường phù hợp.

**Nguyên tắc cốt lõi:** chọn đúng cơ chế xác thực theo SMTP provider, bảo vệ credential trong secret store và trên kênh TLS, dùng access token còn hạn khi chọn OAuth/XOAUTH2, và tách lớp xác thực khỏi use case gửi mail. Cách tổ chức này giúp ứng dụng Spring Framework Mail vận hành và rotate credential an toàn, đồng thời xử lý lỗi rõ ràng mà không làm lộ secret.

