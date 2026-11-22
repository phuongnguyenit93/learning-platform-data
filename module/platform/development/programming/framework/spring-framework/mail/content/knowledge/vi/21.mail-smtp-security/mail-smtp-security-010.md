# Tách tài khoản gửi theo môi trường hoặc chức năng

Khi một ứng dụng Spring bắt đầu gửi email, cấu hình thường rất đơn giản: một SMTP host, một username, một password và một địa chỉ `From`. Nhưng khi ứng dụng có môi trường development, staging, production, đồng thời gửi email xác minh tài khoản, hóa đơn, cảnh báo bảo mật và marketing, **dùng chung một tài khoản SMTP cho mọi luồng** có thể tạo rủi ro lớn.

Ví dụ, nếu máy phát triển dùng nhầm credential production, một lần chạy test có thể gửi thư thật tới khách hàng. Nếu tài khoản SMTP phục vụ newsletter bị lộ, kẻ tấn công có thể lợi dụng cùng quyền đó để gửi thư giả danh thông báo bảo mật. Nếu một luồng marketing bị provider giới hạn tốc độ, các email reset mật khẩu quan trọng có thể bị ảnh hưởng.

Vì vậy, trong **Spring Framework Mail**, cần cân nhắc tách **SMTP account/credential**, cấu hình server, sender identity, domain và chính sách gửi theo **môi trường** hoặc **chức năng nghiệp vụ**. Tách tài khoản không chỉ là thay chuỗi địa chỉ hiển thị: nó liên quan tới quyền xác thực với provider, phạm vi sử dụng credential, quota, nhật ký, chính sách recipient và cách ứng dụng chọn `JavaMailSender`.

Bài học này trình bày lý do, mức độ phân tách, mô hình cấu hình Spring Boot, ví dụ nhiều `JavaMailSenderImpl`, cơ chế routing có kiểm soát, bảo vệ secret, STARTTLS/implicit TLS, quản trị domain, test và giám sát vận hành.

## 1. Một tài khoản SMTP thực sự đại diện điều gì?

Để gửi thư qua SMTP relay, ứng dụng thường cần:

- **SMTP endpoint**: host và port của server nhận yêu cầu gửi.
- **Credential**: username/password, token SMTP hoặc phương thức xác thực được provider hỗ trợ.
- **Transport security**: STARTTLS, implicit TLS và chính sách xác minh chứng chỉ.
- **Sender identity**: địa chỉ `From`, có thể kèm tên hiển thị.
- **Envelope sender**: địa chỉ dùng trong lệnh `MAIL FROM`, thường liên quan đến bounce và chính sách provider.
- **Quyền của tài khoản**: domain/địa chỉ được xác minh, tốc độ gửi, quota và khả năng dùng sender identity nào.
- **Policy nội bộ**: môi trường, mục đích email và người nhận được phép.

Không nên nhầm các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| SMTP username | Xác thực tài khoản hoặc danh tính ứng dụng với relay |
| SMTP password/token | Bí mật cho phép relay chấp nhận thao tác gửi |
| Header `From` | Địa chỉ người gửi mà người nhận nhìn thấy |
| `Reply-To` | Địa chỉ gợi ý để người nhận trả lời |
| Envelope `MAIL FROM` | Địa chỉ phục vụ routing/bounce ở cấp SMTP |
| `To` / `Cc` / `Bcc` | Những địa chỉ được nhận email |
| `Message-ID` | Định danh message phục vụ threading/tracing |

Một SMTP account có thể được nhà cung cấp cho phép dùng nhiều địa chỉ `From` khác nhau, hoặc chỉ một số domain đã xác minh. **Đổi `helper.setFrom(...)` không đồng nghĩa đã đổi SMTP account**. Ngược lại, dùng hai credential nhưng cùng `From` vẫn là hai principal xác thực khác nhau, và cần kiểm tra chính sách domain tương ứng.

### Ví dụ lỗi nhận thức

~~~java
helper.setFrom("security@example.org");
mailSender.send(message);
~~~

Nếu `mailSender` vẫn được cấu hình bằng credential marketing, email có thể bị provider từ chối, bị gửi bằng danh tính không đúng, hoặc làm luồng bảo mật phụ thuộc cùng quota và quyền của marketing. Quyết định routing phải chọn đúng **transport/account**, không chỉ thay header.

## 2. Tại sao cần tách tài khoản gửi?

Các mục tiêu chính:

1. **Giảm blast radius khi lộ credential:** một bí mật bị lộ không nên tự động cho phép dùng mọi chức năng/môi trường.
2. **Ngăn gửi thư thật từ môi trường thử nghiệm:** development/staging không nên có mặc định khả năng gửi cho khách hàng production.
3. **Giới hạn quyền theo mục đích:** tài khoản marketing không nên có cùng quyền hoặc chính sách với email reset password.
4. **Cách ly quota và uy tín gửi:** lưu lượng lớn hoặc lỗi của một loại thư không nên làm toàn bộ hệ thống bị throttling.
5. **Dễ audit và truy vết:** biết job nào dùng account nào, gửi theo mục đích gì và đã xảy ra lỗi ở đâu.
6. **Độc lập trong rotation và incident response:** thu hồi credential cho một luồng mà không nhất thiết dừng các luồng còn lại.
7. **Áp dụng đúng chính sách provider:** domain verification, sender identity, bounce, complaint và suppression có thể được quản lý riêng.
8. **Ngăn sai sót cấu hình:** cấu hình tường minh giúp giảm khả năng vô tình dùng production SMTP trong local test.

Tách tài khoản không thay thế recipient validation, quyền truy cập hay DMARC. Đây là **một lớp trong defense in depth**. Một ứng dụng vẫn có thể gửi sai người nếu nó có credential hợp lệ nhưng chọn recipient sai.

## 3. Hai chiều phân tách: môi trường và chức năng

Có hai chiều thường gặp.

**Theo môi trường:** development, test/CI, staging và production.

**Theo chức năng:** security/account, transactional/business, marketing/bulk và operational/monitoring.

Một ma trận chính sách minh họa:

| Môi trường | Security email | Transactional email | Marketing email |
| --- | --- | --- | --- |
| Local development | Mail catcher hoặc sandbox | Mail catcher | Tắt hoặc sandbox |
| Automated tests | Fake sender/SMTP test server | Fake sender | Fake sender |
| Staging | Account sandbox riêng + allowlist người nhận | Account sandbox riêng | Tắt hoặc tập người nhận thử |
| Production | Credential security riêng | Credential transactional riêng | Credential marketing riêng |

Không nhất thiết phải có mười hai account ngay từ đầu. Quan trọng là các môi trường **không chia sẻ credential nhạy cảm một cách vô ý**, còn các chức năng có rủi ro/quota khác nhau được cách ly ở mức phù hợp.

### Có nên tách bằng account, subaccount hay provider?

Tùy tính năng của nhà cung cấp, một mức phân tách có thể là:

- SMTP user/credential riêng dưới một tài khoản provider.
- Provider subaccount hoặc project riêng.
- Tenant/provider account độc lập.
- Domain/subdomain gửi khác nhau.
- SMTP endpoint hoàn toàn khác.
- Namespace policy trong ứng dụng.

**Hai credential thuộc cùng provider account không chắc chắn có quota, uy tín IP hoặc quyền hoàn toàn độc lập.** Cần xem provider thật sự phân tách ở cấp nào. Nếu mục tiêu là cách ly quota hoặc reputation, một user phụ có thể chưa đủ.

## 4. Phân tách theo môi trường: dev, test, staging, prod

### 4.1. Development

Máy phát triển nên dùng SMTP catcher hoặc sandbox. Mục tiêu là quan sát nội dung MIME, subject, attachment mà **không chuyển email thật tới Internet**.

Ví dụ cấu hình local với SMTP catcher:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: localhost
    port: 1025
~~~

Cấu hình này chỉ minh họa một local mail catcher đang lắng nghe port `1025`; dịch vụ đó phải được chạy riêng. Không được dùng credential production trong file `application-local.yml`.

Có thể dùng fake `JavaMailSender` cho unit test để hoàn toàn không tạo kết nối mạng. Đối với integration test cần quan sát SMTP/MIME, dùng test server riêng và không trỏ sang provider thật.

### 4.2. CI/test

Automated tests không nên phụ thuộc quota provider production hoặc email thật. Dùng test double hoặc SMTP test server và đưa mọi người nhận tới địa chỉ kiểm thử được kiểm soát.

Không đưa secret SMTP production vào CI chỉ để chạy một bài test nội dung. Khi test cần provider sandbox thực, cấp một credential sandbox riêng với quyền tối thiểu và rotation phù hợp.

### 4.3. Staging

Staging có thể cần kiểm tra TLS, template, provider integration và callback. Dù vậy, staging phải có account/credential **riêng**. Nên hạn chế người nhận bằng allowlist/sink domain và không dùng dữ liệu khách hàng production trừ khi đã có chính sách kiểm soát.

Một cơ chế bảo vệ bổ sung là **recipient guard ở application layer**, ví dụ chỉ cho phép các địa chỉ thuộc miền nội bộ đã đăng ký. Chỉ đổi SMTP host sang sandbox chưa chắc đủ nếu một biến môi trường bị cấu hình sai trong triển khai.

### 4.4. Production

Production sử dụng credential riêng, lưu qua secret manager hoặc secret deployment mechanism được kiểm soát. Quyền truy cập thuộc identity của workload, không phải tài khoản cá nhân của developer.

Các account production nên có alert riêng khi:

- Credential bị dùng từ host/IP bất thường.
- Lưu lượng tăng đột biến.
- Tỷ lệ bounce/complaint tăng.
- Quota gần cạn.
- Provider báo khóa hoặc từ chối xác thực.
- Sender identity không còn được xác minh.

## 5. Tách account theo chức năng nghiệp vụ

Một ứng dụng có thể có các luồng:

| Chức năng | Ví dụ | Đặc tính |
| --- | --- | --- |
| Security | Reset password, xác minh tài khoản, cảnh báo đăng nhập | Nhạy cảm, cần đúng người nhận, ưu tiên độ tin cậy |
| Transactional | Xác nhận đơn hàng, hóa đơn, vận chuyển | Có dữ liệu giao dịch, cần trace theo event |
| Marketing | Newsletter, ưu đãi, chiến dịch | Lưu lượng lớn, consent/unsubscribe nghiêm ngặt |
| Operations | Cảnh báo hệ thống tới nhóm vận hành | Người nhận nội bộ, yêu cầu uptime và phân quyền riêng |

Dùng một account cho tất cả khiến hành vi marketing có thể ảnh hưởng security: quota chung, complaint gây giảm uy tín gửi, hoặc credential lộ từ module ít được bảo vệ hơn.

### 5.1. Security/account mail

Email reset password và xác minh tài khoản thường chứa token hoặc đường dẫn nhạy cảm. Account này nên chỉ phục vụ các workflow account/security đã được ủy quyền, không dùng từ endpoint gửi mail HTML tùy ý.

Recipient thường được lấy từ tài khoản hoặc yêu cầu xác minh đã hợp lệ, không chỉ từ một chuỗi người gọi tự truyền. Token cần có thời hạn, phạm vi và chính sách sử dụng một lần khi phù hợp.

### 5.2. Transactional mail

Hóa đơn, trạng thái đơn hàng hoặc lịch hẹn nên gắn với event nghiệp vụ, có idempotency key và trạng thái gửi. Account transactional có thể cần quota riêng để tránh chậm các thông báo quan trọng khi có một campaign marketing lớn.

### 5.3. Marketing mail

Marketing cần consent, unsubscribe, suppression và giới hạn tốc độ. Account marketing thường được giám sát reputation/bounce/complaint riêng. Không nên mặc định fallback sang credential security để vượt throttle marketing.

### 5.4. Operations/internal mail

Cảnh báo vận hành có thể gửi tới danh sách nội bộ. Nếu account này dùng cùng provider với luồng khách hàng, cần cân nhắc rủi ro sự cố provider cùng lúc. Với cảnh báo sự cố SMTP, có thể cần **kênh cảnh báo độc lập** (monitoring/paging), không chỉ email qua cùng SMTP relay đang gặp sự cố.

## 6. Tách credential không đồng nghĩa tách địa chỉ From

Có ba kiểu phân tách khác nhau:

~~~text
A. Một credential, nhiều From:
   smtp-user-X → orders@example.org
               → security@example.org

B. Nhiều credential, cùng From:
   smtp-user-S → notice@example.org
   smtp-user-T → notice@example.org

C. Nhiều credential và sender identity:
   smtp-user-S → security@example.org
   smtp-user-T → orders@example.org
   smtp-user-M → news@example.org
~~~

Phương án C dễ mô tả ranh giới theo chức năng hơn, nhưng chỉ có giá trị bảo mật thực khi provider **giới hạn quyền và tài nguyên** của từng account.

Chọn address và domain phải phối hợp với DNS authentication. Không nên tự ý gắn `From` của domain mà provider chưa xác minh.

### Sender policy khác recipient policy

- **Sender policy:** workflow nào được dùng account/From/domain nào?
- **Recipient policy:** người nhận nào được phép nhận nội dung cụ thể?
- **Content/template policy:** loại thông báo nào được render và chứa dữ liệu nào?
- **Rate policy:** số lượng/tốc độ/ưu tiên của luồng gửi.

Một thiết kế an toàn cần cả bốn. Nếu chỉ có một router chọn account nhưng mọi caller được truyền HTML, recipient và From tùy ý, nguy cơ lạm dụng vẫn cao.

## 7. SPF, DKIM, DMARC khi chia tài khoản hoặc domain

Tách account có thể kéo theo tách domain/subdomain, ví dụ:

~~~text
security.example.org
tx.example.org
news.example.org
~~~

Đây chỉ là ví dụ kiến trúc, không bắt buộc mọi ứng dụng phải tách subdomain. Mỗi sender domain cần đáp ứng các yêu cầu xác thực của mail provider và chính sách của tổ chức.

Các khái niệm:

| Cơ chế | Vai trò |
| --- | --- |
| SPF | Xác nhận IP/relay được phép gửi theo envelope sender domain |
| DKIM | Chữ ký xác thực gắn với domain trong tham số `d=` |
| DMARC | Kiểm tra alignment của domain header From với SPF hoặc DKIM theo chính sách |
| Domain verification | Provider xác minh quyền cấu hình sender/domain |
| Bounce/Return-Path domain | Liên quan đến envelope và xử lý phản hồi gửi thất bại |

Nếu một account security gửi thư từ `security.example.org` nhưng DKIM/SPF được cấu hình sai, email có thể bị đánh dấu đáng ngờ. Dùng credential khác **không tự làm DMARC pass**.

### Alignment không đơn thuần là “SPF có record”

Một thư có thể có SPF pass theo envelope sender domain nhưng vẫn không thỏa DMARC nếu domain đó không alignment với header From theo chính sách. DKIM cũng cần chữ ký hợp lệ và domain ký phù hợp.

Khi thêm subdomain, hãy kiểm tra:

1. Domain/địa chỉ From được provider cho phép.
2. SPF/DKIM/DMARC được cấu hình theo chính sách DNS của tổ chức.
3. DKIM selector và key được quản lý, rotation.
4. Bounce, return-path và webhook được route đúng account.
5. Môi trường staging không vô tình phát thư có vẻ như thư production.

Tùy provider, một số bản ghi DNS là CNAME hoặc TXT do nhà cung cấp hướng dẫn; không tự đoán record trong một tài liệu cấu hình chung.

## 8. Spring Boot thường cấu hình một JavaMailSender mặc định

Với trường hợp đơn giản:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

Spring Boot có thể auto-configure một `JavaMailSender` từ `spring.mail.*` khi điều kiện auto-configuration phù hợp. Đây là mô hình **một sender cấu hình mặc định**.

Nếu ứng dụng có ba SMTP account, đổi `helper.setFrom` không đủ. Cần các `JavaMailSenderImpl` độc lập, mỗi sender có host, port, username, password và TLS config riêng, rồi chọn sender qua lớp routing phù hợp.

### Tránh trộn hai cách cấu hình mà không có chủ đích

Khi tự định nghĩa `@Bean` kiểu `JavaMailSender`, Spring Boot mail auto-configuration có thể back off theo điều kiện bean. Không nên kỳ vọng một `spring.mail.*` luôn tạo thêm sender thứ tư trong khi ứng dụng đã có custom beans.

Nên chọn một kiến trúc rõ:

- **Một sender:** dùng `spring.mail.*` và Boot auto-config khi phù hợp.
- **Nhiều sender:** dùng namespace riêng, ví dụ `app.mail.accounts.*`, tự tạo bean sender và routing; chỉ duy trì `spring.mail.*` nếu có một mục đích rõ ràng.
- **Dynamic/tenant sender:** dùng registry/factory có cache giới hạn, secret management và tenant authorization.

## 9. Mô hình cấu hình nhiều account theo purpose

Ví dụ một ứng dụng production có ba account:

~~~yaml
app:
  mail:
    accounts:
      security:
        host: ${SMTP_SECURITY_HOST}
        port: 587
        username: ${SMTP_SECURITY_USER}
        password: ${SMTP_SECURITY_PASSWORD}
        from: security@example.org
        implicit-tls: false

      transactional:
        host: ${SMTP_TX_HOST}
        port: 587
        username: ${SMTP_TX_USER}
        password: ${SMTP_TX_PASSWORD}
        from: orders@example.org
        implicit-tls: false

      marketing:
        host: ${SMTP_MARKETING_HOST}
        port: 465
        username: ${SMTP_MARKETING_USER}
        password: ${SMTP_MARKETING_PASSWORD}
        from: news@example.org
        implicit-tls: true
~~~

Đây là **mẫu cú pháp**, không phải credential dùng được thực tế. Các biến môi trường phải được cấp qua cơ chế secret/deployment phù hợp. Không commit password trong repository hoặc chia sẻ file cấu hình chứa secret thật.

Phần này chọn biến `implicit-tls` để minh họa hai chế độ TLS:

- `false`: kết nối SMTP rồi nâng cấp bằng STARTTLS, thường trên port 587.
- `true`: kết nối được bọc TLS ngay từ đầu, thường trên port 465.

Các port chỉ là giá trị thường gặp. Phải dùng host/port/TLS mode đúng theo hợp đồng provider, không suy ra từ port một cách máy móc.

### Có cần file YAML khác cho từng môi trường?

Có thể dùng Spring profiles hoặc externalized configuration:

~~~text
application.yml
application-local.yml
application-staging.yml
application-prod.yml
~~~

Không lưu production password vào file profile. File profile có thể chỉ mô tả **chính sách không nhạy cảm**, còn secret được inject bằng hệ thống deployment.

Ví dụ `application-staging.yml` có thể override tài khoản thành sandbox và bật recipient allowlist. Cần kiểm soát profile active ở runtime và có safeguard để tránh staging lấy nhầm biến secret của production.

## 10. Đọc cấu hình bằng @ConfigurationProperties

Có thể định nghĩa kiểu cấu hình:

~~~java
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAccountsProperties(
        Map<String, SmtpProfile> accounts) {

    public SmtpProfile require(String name) {
        if (accounts == null) {
            throw new IllegalStateException(
                    "Chưa cấu hình app.mail.accounts"
            );
        }

        SmtpProfile profile = accounts.get(name);

        if (profile == null) {
            throw new IllegalStateException(
                    "Thiếu SMTP profile: " + name
            );
        }

        return profile;
    }

    public record SmtpProfile(
            String host,
            int port,
            String username,
            String password,
            String from,
            boolean implicitTls) {
    }
}
~~~

Record này chỉ mang dữ liệu cấu hình. Trong production nên thêm validation rõ ràng cho host, port, username, password, From và điều kiện TLS, ví dụ kết hợp Bean Validation hoặc constructor invariant; không để ứng dụng chạy tới lúc gửi mới phát hiện thiếu secret.

Nếu Spring Boot version có cách binding hoặc annotation validation khác nhau, cần cấu hình tương ứng trong project. Ví dụ trên nhấn mạnh **tách profile và đọc externalized configuration**, không yêu cầu một thư viện mail routing đặc biệt.

### Đừng log đối tượng chứa password

Java record có `toString()` tự sinh, có thể in ra tất cả component, bao gồm `password`. **Không log nguyên `SmtpProfile` hoặc properties object**.

Có thể thiết kế secret wrapper có `toString()` che giá trị, hoặc đặt credential trong một thành phần chuyên trách không được xuất vào log, trace, actuator hoặc error response. Với cấu hình dynamic, không trả nội dung secret qua endpoint quản trị.

## 11. Tạo các JavaMailSenderImpl độc lập

Một factory có thể tạo sender từ profile:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {

    private SmtpSenderFactory() {
    }

    public static JavaMailSender create(
            MailAccountsProperties.SmtpProfile p) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(p.host());
        sender.setPort(p.port());
        sender.setUsername(p.username());
        sender.setPassword(p.password());
        sender.setDefaultEncoding(
                StandardCharsets.UTF_8.name()
        );

        Properties mail = sender.getJavaMailProperties();

        mail.put("mail.transport.protocol", "smtp");
        mail.put("mail.smtp.auth", "true");

        if (p.implicitTls()) {
            // TLS từ đầu phiên SMTP.
            mail.put("mail.smtp.ssl.enable", "true");
            mail.put("mail.smtp.starttls.enable", "false");
        } else {
            // STARTTLS là bắt buộc, không silently downgrade.
            mail.put("mail.smtp.ssl.enable", "false");
            mail.put("mail.smtp.starttls.enable", "true");
            mail.put("mail.smtp.starttls.required", "true");
        }

        // Kiểm tra tên host trong certificate.
        mail.put("mail.smtp.ssl.checkserveridentity", "true");

        // Timeout ví dụ, đơn vị milliseconds.
        mail.put("mail.smtp.connectiontimeout", "5000");
        mail.put("mail.smtp.timeout", "10000");
        mail.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

Mỗi lần gọi factory tạo một `JavaMailSenderImpl` riêng. Mỗi sender giữ thông tin credential và properties của account tương ứng.

**Các điều cần tránh:**

- Không dùng `mail.smtp.ssl.trust=*` để bỏ qua xác minh TLS.
- Không để STARTTLS `enable=true` nhưng `required=false` khi yêu cầu bảo mật đòi TLS bắt buộc, vì có nguy cơ tiếp tục phiên không TLS trong một số cấu hình.
- Không trộn implicit TLS và STARTTLS theo suy đoán.
- Không chia sẻ một mutable `JavaMailSenderImpl` rồi thay `setUsername`/`setPassword` trước mỗi email; nhiều thread có thể gửi bằng credential của nhau.
- Không log `Session`, JavaMail properties hoặc exception theo cách làm lộ credential.

Ví dụ dùng `JavaMailSenderImpl` và properties Jakarta Mail. Hãy cấu hình thời gian chờ hợp lý với provider và kích thước message; những giá trị ví dụ không phải đề xuất mặc định cho mọi dịch vụ.

### Kiểm tra chứng chỉ TLS

STARTTLS hoặc implicit TLS chỉ mang ý nghĩa bảo vệ kết nối khi client **xác minh chứng chỉ và hostname** phù hợp. Nếu production dùng CA riêng hoặc truststore tùy chỉnh, phải cấu hình chain tin cậy đúng thay vì tắt xác minh.

Tài khoản tách riêng nhưng kết nối SMTP bị downgrade/MITM vẫn là rủi ro nghiêm trọng.

## 12. Đăng ký ba bean sender theo tên rõ ràng

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
@EnableConfigurationProperties(MailAccountsProperties.class)
public class MultipleMailSendersConfig {

    @Bean("securityMailSender")
    JavaMailSender securityMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("security")
        );
    }

    @Bean("transactionalMailSender")
    JavaMailSender transactionalMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("transactional")
        );
    }

    @Bean("marketingMailSender")
    JavaMailSender marketingMailSender(
            MailAccountsProperties properties) {

        return SmtpSenderFactory.create(
                properties.require("marketing")
        );
    }
}
~~~

Giờ ứng dụng có ba bean cùng type `JavaMailSender`.

### @Qualifier và @Primary

Nếu inject theo type mà không có qualifier:

~~~java
public OrderMailService(JavaMailSender sender) {
    this.sender = sender;
}
~~~

Spring có thể gặp nhiều candidate nếu không có quy ước/primary cho biết cần chọn bean nào. Đối với luồng SMTP nhạy cảm, **chọn sender tường minh** thường tốt hơn là đặt một default rồi để các service vô tình dùng nhầm.

Ví dụ:

~~~java
public SecurityMailService(
        @Qualifier("securityMailSender")
        JavaMailSender sender) {
    this.sender = sender;
}
~~~

`@Primary` có thể được dùng nếu có một default rõ ràng và mọi trường hợp khác dùng `@Qualifier`. Tuy nhiên, một default không mong muốn có thể che giấu lỗi routing. Với account security/marketing, thiết kế **không có default ngầm** là một lựa chọn an toàn hơn.

### Không tự tiêm Map theo key mà không kiểm soát policy

Spring có thể inject `Map<String, JavaMailSender>` với tên bean. Điều đó hữu ích cho registry nội bộ, nhưng không nên lấy tên bean trực tiếp từ request:

~~~java
// Không nên:
JavaMailSender sender = beanMap.get(request.getSenderName());
~~~

Request từ người dùng không nên được quyền chọn credential hay account tùy ý.

## 13. Route theo mục đích, không theo giá trị người dùng nhập

Một lớp routing trung tâm có thể chọn account từ **enum do ứng dụng kiểm soát**:

~~~java
public enum MailPurpose {
    SECURITY,
    TRANSACTIONAL,
    MARKETING
}
~~~

Kết quả của application layer:

~~~java
public record ApprovedMail(
        MailPurpose purpose,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

Tên `ApprovedMail` có nghĩa hợp đồng ứng dụng đã áp dụng recipient/content authorization trước khi tạo. Tên kiểu không tự tạo bảo đảm bảo mật; các entry point vẫn phải tuân thủ policy, module visibility và test.

### Một routing gateway

~~~java
import java.util.EnumMap;
import java.util.Map;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public final class MailRoutingGateway {

    private final Map<MailPurpose, SenderBinding> accounts;

    public MailRoutingGateway(
            @Qualifier("securityMailSender")
            JavaMailSender securitySender,

            @Qualifier("transactionalMailSender")
            JavaMailSender transactionalSender,

            @Qualifier("marketingMailSender")
            JavaMailSender marketingSender,

            MailAccountsProperties config) {

        EnumMap<MailPurpose, SenderBinding> map =
                new EnumMap<>(MailPurpose.class);

        map.put(
                MailPurpose.SECURITY,
                new SenderBinding(
                        securitySender,
                        config.require("security").from()
                )
        );

        map.put(
                MailPurpose.TRANSACTIONAL,
                new SenderBinding(
                        transactionalSender,
                        config.require("transactional").from()
                )
        );

        map.put(
                MailPurpose.MARKETING,
                new SenderBinding(
                        marketingSender,
                        config.require("marketing").from()
                )
        );

        this.accounts = Map.copyOf(map);
    }

    public void send(ApprovedMail mail)
            throws MessagingException {

        SenderBinding binding =
                accounts.get(mail.purpose());

        if (binding == null) {
            throw new IllegalArgumentException(
                    "Không có account cho mail purpose"
            );
        }

        MimeMessage message =
                binding.sender().createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message, true, "UTF-8"
                );

        // From do cấu hình account được duyệt quyết định.
        helper.setFrom(binding.from());
        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(
                mail.plainText(),
                mail.htmlText()
        );

        binding.sender().send(message);
    }

    private record SenderBinding(
            JavaMailSender sender,
            String from) {
    }
}
~~~

Trong ví dụ, `MailRoutingGateway` nhận các bean đã tách và tự chọn account theo `MailPurpose`. `From` cũng gắn với account, không lấy từ nội dung request.

Đây là lớp transport; việc kiểm tra người nhận và quyền vẫn phải xảy ra trước đó. Đối với ứng dụng lớn, có thể thêm `MailPolicy` hoặc factory trả về một `ApprovedMail` chỉ sau khi kiểm tra use case.

### Vì sao chọn theo enum?

Một enum cố định giúp hạn chế các lựa chọn transport. Người gọi có thể yêu cầu “gửi xác nhận đơn hàng”, nhưng application service sẽ xác định đó là `TRANSACTIONAL`. Một request công khai không nên được phép tự đổi purpose từ `MARKETING` sang `SECURITY` để vượt quota hoặc suppression.

## 14. Ranh giới giữa application service và transport

Một luồng hợp lý:

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Event"] --> B["Application service"]
    B --> C["Authorization + recipient policy"]
    C --> D["Xác định MailPurpose"]
    D --> E["Render template từ dữ liệu hợp lệ"]
    E --> F["ApprovedMail"]
    F --> G["MailRoutingGateway"]
    G --> H{"Purpose?"}
    H -->|"SECURITY"| I["securityMailSender"]
    H -->|"TRANSACTIONAL"| J["transactionalMailSender"]
    H -->|"MARKETING"| K["marketingMailSender"]
    I --> L["SMTP relay"]
    J --> L
    K --> L
~~~

Controller chỉ nhận request, tạo command và gọi use case. Nó không nên biết SMTP password, gửi qua host nào hay dùng `From` nào.

**Recipient policy** cần phân biệt:

- Security: người nhận được xác định theo workflow xác thực, tránh token leakage.
- Transactional: contact thuộc đúng giao dịch/tenant, đúng loại sự kiện.
- Marketing: consent, unsubscribe, suppression và giới hạn gửi.
- Staging: người nhận thuộc allowlist kiểm thử.
- Internal notifications: chỉ tới nhóm/địa chỉ được phê duyệt.

Chỉ vì một email có address đúng cú pháp không có nghĩa nó được phép nhận dữ liệu từ use case đó.

## 15. Tách account trong hệ thống multi-tenant

Một hệ thống nhiều tenant có thêm câu hỏi: **mỗi tenant dùng một sender/account riêng, hay dùng account chung của nền tảng?**

Các mô hình:

| Mô hình | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Account chung cho nền tảng | Dễ triển khai và vận hành | Tenant có thể chia sẻ quota/reputation |
| Account theo nhóm tenant | Cân bằng chi phí và cách ly | Quy tắc mapping phức tạp hơn |
| Account riêng mỗi tenant | Cách ly domain/credential tốt hơn nếu provider hỗ trợ | Nhiều secret, rotation và kết nối |
| Tenant dùng provider của họ | Mức sở hữu sender domain rõ | Cần onboarding, validation, xử lý credential an toàn |

Không nên suy ra rằng `tenantId` do client gửi là đủ để chọn credential. Application service phải xác minh người gọi thuộc tenant và có quyền trên tài nguyên, sau đó resolver mới chọn sender profile tương ứng.

Ví dụ:

~~~java
public record SenderSelection(
        UUID tenantId,
        MailPurpose purpose,
        String approvedAccountId) {
}
~~~

ID account phải được resolve từ cấu hình tenant có thẩm quyền; không dùng raw SMTP host/username/password trong HTTP body. Registry có thể tra secret manager bằng account ID, nhưng cần cache/TTL, concurrency control, audit và rotation.

### Tránh biến ứng dụng thành open relay

Một API cho phép client đưa **recipient + HTML + From + SMTP account ID** tùy ý có thể bị dùng để spam/phishing và lạm dụng credential. Cần giới hạn use case, loại template, recipient, quota và quyền gửi trước khi gọi gateway.

## 16. Không thay đổi credential trên một sender dùng chung

Ví dụ nguy hiểm khi cố tái sử dụng một `JavaMailSenderImpl` mutable:

~~~java
// Không an toàn khi nhiều thread gửi đồng thời:
sharedSender.setUsername(account.username());
sharedSender.setPassword(account.password());
sharedSender.send(message);
~~~

Hai thread có thể xen kẽ:

~~~text
Thread A: setUsername/security
Thread B: setUsername/marketing
Thread A: send
~~~

Khi đó message của security có thể được gửi bằng credential marketing hoặc gặp lỗi xác thực không dự đoán được. Không nên sửa host, port, password hay JavaMail properties trên singleton sender để route từng email.

Giải pháp:

- Tạo bean sender bất biến về mặt cấu hình vận hành cho từng account.
- Với account động, tạo sender riêng theo profile và giữ trong registry được kiểm soát.
- Thay reference/sender một cách có quản lý khi rotate credential, không mutate object đang dùng bởi nhiều thread.
- Cô lập credential ở nơi chỉ tầng transport có thể đọc.

Lưu ý `JavaMailSenderImpl` không phải immutable type theo thiết kế, nhưng có thể sử dụng như một **bean với cấu hình cố định sau startup**, không chỉnh setter trong luồng gửi.

## 17. Bí mật SMTP: lưu ở đâu và không nên lưu ở đâu?

SMTP password/token là credential có thể cho phép gửi thư thay mặt domain hoặc tài khoản. Cần bảo vệ tương tự các bí mật ứng dụng khác.

Không đặt secret trực tiếp trong:

- Source code Java/Kotlin.
- YAML hoặc properties được commit vào Git.
- Unit test snapshot và golden files.
- Dockerfile `ENV` lưu cứng secret.
- Log, stack trace dump, actuator config exposure hoặc error response.
- Ticket, chat, tài liệu public hoặc screenshot cấu hình.

Nên dùng:

- Secret manager hoặc secret store do platform cung cấp.
- Environment injection/volume mount theo cơ chế deployment được bảo vệ.
- IAM/service identity cho workload, hạn chế ai có quyền đọc.
- RBAC và audit secret access.
- Rotation/revocation theo account và môi trường.
- Masking/scrubbing ở logging, diagnostics và monitoring.

### Environment variable cũng không tự động an toàn tuyệt đối

Biến môi trường tốt hơn việc commit password, nhưng vẫn có thể lộ qua debug dump, công cụ quản trị process, pipeline log hoặc quyền truy cập host. Cần kiểm soát môi trường runtime và người có quyền xem deployment secrets.

### Chú ý record toString()

Nếu dùng `record SmtpProfile(..., String password, ...)`, method `toString()` do Java tạo có thể đưa password vào log. Không log nguyên object cấu hình, và cân nhắc tách secret ra một kiểu có cách biểu diễn che giá trị.

## 18. Credential rotation và thu hồi

Khi credential marketing bị lộ, tổ chức cần có thể:

1. Vô hiệu hóa credential marketing riêng.
2. Tạo credential mới với quyền cần thiết.
3. Cập nhật secret store/deployment.
4. Roll/restart hoặc thay sender instance an toàn để nạp credential mới.
5. Kiểm tra account marketing hoạt động.
6. Theo dõi lưu lượng bất thường và đánh giá các thông báo đã gửi.

Nếu tất cả luồng chia sẻ một credential, việc thu hồi có thể làm dừng cả security và transactional mail. Phân tách giúp giảm phạm vi ảnh hưởng.

### Không giả định thay secret là sender tự đổi ngay

Một `JavaMailSenderImpl` được tạo lúc startup thường giữ giá trị username/password được cấu hình. Khi secret store thay đổi, bean cũ **không nhất thiết tự reload**. Cần cơ chế rotation rõ: restart/rolling deployment, refresh có quản lý hoặc thay sender instance được đồng bộ hóa.

Trong quá trình rotation, tránh sửa password trên singleton đang được nhiều thread dùng. Có thể cho phép một khoảng chuyển đổi hai credential nếu provider hỗ trợ, nhưng không nên duy trì credential cũ lâu hơn cần thiết.

### Phân biệt rotation và failover

Rotation là thay credential của account. Failover là chuyển sang provider/account khác khi account hiện tại không dùng được. Failover giữa các chức năng cần kiểm tra sender identity, consent, quota và domain policy; **không tự động lấy credential security để gửi marketing**.

## 19. TLS và xác thực SMTP

Tách account có ý nghĩa ít hơn nếu credential gửi qua kết nối không được bảo vệ đúng. Phân biệt hai chế độ:

### 19.1. STARTTLS

Thông thường kết nối bắt đầu bằng SMTP rồi chuyển sang TLS:

~~~properties
mail.smtp.auth=true
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

`required=true` giúp tránh việc tiếp tục gửi trong trường hợp server không hỗ trợ nâng cấp TLS khi chính sách yêu cầu. Cần xác minh chứng chỉ và hostname đúng.

### 19.2. Implicit TLS

Kết nối TLS ngay từ đầu phiên:

~~~properties
mail.smtp.auth=true
mail.smtp.ssl.enable=true
mail.smtp.ssl.checkserveridentity=true
~~~

Không chỉ dựa vào số port để quyết định cấu hình; nhà cung cấp có thể dùng port hoặc endpoint riêng.

### 19.3. Những cấu hình không nên dùng để “sửa nhanh”

Không nên cấu hình:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.starttls.required=false
~~~

rồi cho rằng mọi kết nối đều được bảo vệ. `ssl.trust=*` nới lỏng kiểm soát certificate trust; `required=false` có thể cho phép downgrade ở những cấu hình STARTTLS. Các quyết định TLS phải được review theo threat model và hợp đồng provider.

### 19.4. Timeout

Dù có nhiều account, một kết nối SMTP treo vẫn có thể chiếm thread pool:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

Giá trị tính bằng mili giây; điều chỉnh theo độ trễ và kích thước email. Không đặt timeout vô hạn rồi hy vọng `@Async` sẽ giải quyết nghẽn tài nguyên.

## 20. Tách account và giới hạn lưu lượng

Provider có thể áp dụng quota theo nhiều cấp:

- SMTP user.
- Provider account/subaccount.
- Sending domain.
- IP pool.
- Tenant hoặc organization.
- Tổng số message/recipient trong một khoảng thời gian.

Tách user không bảo đảm tách quota nếu provider đếm ở account cha. Cần đo thực tế và xác nhận contract.

Một policy phân bổ ưu tiên:

| Luồng | Mục tiêu | Chiến lược |
| --- | --- | --- |
| Security | Độ trễ thấp, ít gián đoạn | Pool nhỏ có ưu tiên, quota dự phòng |
| Transactional | Gửi ổn định theo event | Queue/outbox, retry và idempotency |
| Marketing | Khối lượng lớn nhưng có thể trì hoãn | Rate limit, batch, suppression |
| Operations | Có thể cần hoạt động khi SMTP chính sự cố | Kênh alert riêng hoặc provider độc lập |

Nếu mọi mục đích vẫn dùng chung một `ThreadPoolTaskExecutor` hoặc hàng đợi vô hạn, account đã tách có thể vẫn tranh chấp tài nguyên JVM. Khi cần, hãy tách executor/queue, concurrency limit và retry policy theo purpose.

## 21. Retry, fallback và ranh giới account

Giả sử account marketing bị SMTP relay trả lỗi throttling. Có nên chuyển job sang account security?

**Không mặc định.** Việc này có thể phá quota isolation, sender policy, complaint handling hoặc các quy tắc consent. Cần phân biệt:

- Retry cùng account sau backoff.
- Rotate credential của cùng account theo quy trình.
- Failover tới account/provider dự phòng đã được phê duyệt cho **cùng purpose**.
- Tạm dừng campaign để không ảnh hưởng hệ thống khác.

Một policy đơn giản:

~~~java
public interface MailRoutePolicy {
    SenderAccount resolve(
            MailPurpose purpose,
            UUID tenantId);
}
~~~

Policy quyết định tuyến gửi được phép. Nếu có fallback, danh sách các tuyến dự phòng phải được cấu hình và cấp quyền trước, không dựa vào việc credential khác “còn gửi được”.

### Outbox cần nhớ purpose, không cần lưu SMTP password

Một outbox job có thể chứa:

~~~json
{
  "jobId": "mail-job-123",
  "eventId": "evt-981",
  "purpose": "TRANSACTIONAL",
  "recipientContactId": "contact-77",
  "templateCode": "ORDER_CONFIRMED",
  "status": "PENDING"
}
~~~

Worker đọc job, kiểm tra recipient policy theo purpose, rồi routing gateway lấy account. Không lưu raw SMTP password vào outbox payload.

Khi retry, **purpose và idempotency key của ý định gửi vẫn ổn định**. Nếu account được rotate, cùng purpose có thể dùng credential mới theo policy. Nếu thực sự failover sang provider khác, phải tính tới khả năng lần gửi trước đã được relay chấp nhận nhưng kết quả không chắc chắn; gửi lại có thể gây duplicate.

## 22. Staging guard không thể chỉ dựa vào SMTP account

Một cấu hình staging có thể vô tình trỏ tới account production do lỗi CI/deployment. Vì thế nên có nhiều lớp bảo vệ:

1. Credential staging riêng, không cấp production credential cho staging.
2. Sender identity staging có thể phân biệt rõ với production.
3. Recipient allowlist hoặc sink ở tầng ứng dụng.
4. Guard từ chối mọi địa chỉ ngoài phạm vi thử nghiệm.
5. Provider sandbox khi thích hợp.
6. Test cấu hình ở startup/deployment.
7. Alert nếu staging phát sinh lượng gửi bất thường.

Ví dụ policy:

~~~java
@Component
@Profile("staging")
public class StagingRecipientGuard {

    private final Set<String> allowedDomains =
            Set.of("qa.example.org", "internal.example.org");

    public void requireAllowed(String email) {
        String domain = extractValidatedDomain(email);

        if (!allowedDomains.contains(
                domain.toLowerCase(Locale.ROOT))) {

            throw new IllegalArgumentException(
                    "Staging không được gửi tới recipient này"
            );
        }
    }
}
~~~

`extractValidatedDomain` là utility/parser do ứng dụng tự cài đặt; ví dụ chỉ thể hiện nơi áp dụng chính sách. Trong production, cần email parser phù hợp và không chỉ dùng `endsWith("example.org")` vì địa chỉ như `evil-example.org` có thể vượt kiểm tra chuỗi sơ sài.

**Quan trọng:** Recipient guard phải được gọi bởi application boundary chung mà mọi luồng gửi đều đi qua. Một component chỉ được khai báo nhưng không được gọi không tạo ra bảo vệ.

### Không sử dụng `@Profile` như một biện pháp bảo mật duy nhất

Profile là lựa chọn cấu hình runtime; nó có thể được kích hoạt sai. Credential segmentation, secret access policy và guard recipient cần cùng tồn tại để giảm rủi ro.

## 23. Audit, log và monitoring theo account

Tách account tạo điều kiện cho quan sát tốt hơn nếu mỗi lần gửi được gắn metadata:

~~~text
mail_request_id: req-789
business_event_id: evt-981
purpose: SECURITY
environment: production
sender_profile: security
recipient_contact_id: contact-77
smtp_result: ACCEPTED
duration_ms: 842
attempt: 1
~~~

Không log username/password, token reset hoặc toàn bộ email HTML. Cũng không nhất thiết log địa chỉ người nhận đầy đủ; dùng contact ID hoặc masking theo chính sách.

Các chỉ số nên theo dõi riêng:

- SMTP AUTH failure theo account.
- TLS handshake/certificate failures.
- SMTP latency và timeout.
- Provider throttling, quota và rejection.
- Bounce/complaint/unsubscribe theo purpose.
- Số email gửi theo account và môi trường.
- Số lần fallback và lý do.
- Outbox backlog, số retry và thời gian chờ.
- Bất thường sender identity hoặc domain verification.

### Trạng thái “sent” không phải “delivered”

`JavaMailSender.send(...)` trả về bình thường thường biểu thị thao tác gửi tới mail transport thành công theo API, không chứng minh người nhận đã nhận inbox. Provider có thể bounce hoặc trì hoãn sau đó. Nếu cần trạng thái delivered, phải tích hợp provider feedback/webhook hoặc cơ chế theo dõi tương ứng.

Tách account giúp truy vết provider feedback chính xác hơn, nhưng không tự bổ sung delivery confirmation.

## 24. Kiểm thử routing và bảo vệ môi trường

Nên kiểm thử các ranh giới thay vì chỉ kiểm tra HTML render đẹp.

### 24.1. Unit test chọn đúng sender

Với ba fake `JavaMailSender`, xác nhận:

- `SECURITY` gọi đúng security sender, không gọi marketing sender.
- `TRANSACTIONAL` gọi đúng transactional sender.
- `MARKETING` gọi đúng marketing sender.
- `From` được gắn từ cấu hình account đúng.
- Purpose không được cấu hình phải fail closed, không fallback sang sender bất kỳ.

Ví dụ khung kiểm thử:

~~~java
@Test
void securityMailUsesSecuritySender() {
    ApprovedMail mail = new ApprovedMail(
            MailPurpose.SECURITY,
            "tester@example.org",
            "Xác minh tài khoản",
            "Mã xác minh...",
            "<p>Mã xác minh...</p>"
    );

    gateway.send(mail);

    // Assert securitySender được gọi.
    // Assert transactionalSender/marketingSender không được gọi.
}
~~~

Đây là test skeleton minh họa. Trong test thực, có thể capture `MimeMessage` hoặc dùng fake sender để kiểm tra message và số lần send.

### 24.2. Test local/staging không gửi ra production

- Active profile đúng.
- Không đọc được production secret ở runtime staging.
- Recipient ngoài allowlist bị từ chối.
- SMTP endpoint staging trỏ vào sandbox/test catcher.
- Credential staging không được quyền dùng sender domain production nếu policy không cho.
- Test dùng fake/sandbox sender, không gửi email tới người dùng thật.

### 24.3. Test cấu hình nhiều bean

- Các bean `securityMailSender`, `transactionalMailSender`, `marketingMailSender` có mặt.
- Không có dependency injection ambiguity ở service quan trọng.
- Mỗi bean có host, port, TLS mode và account đúng.
- Thiếu profile/secret bắt buộc khiến startup fail theo chính sách, thay vì vô tình dùng sender mặc định.
- Không có bean debug test được bật ngoài môi trường dự kiến.

### 24.4. Integration test với SMTP test server

Một SMTP test server cho phép quan sát:

- Envelope và header sender.
- `From`, `Reply-To`, `To`, `Cc`, `Bcc`.
- MIME body plain/HTML và attachment.
- TLS/SMTP AUTH khi test server hỗ trợ.
- Lỗi timeout, AUTH rejection và provider throttling giả lập.

Tránh dùng credential production trong automated tests. Nếu kiểm thử trực tiếp với provider, dùng sandbox account và người nhận được kiểm soát.

## 25. Những lỗi cấu hình thường gặp

### 25.1. Chỉ thay From, không thay account

Gửi email security với `From=security@example.org` nhưng vẫn sử dụng username/password marketing. Cần chọn `JavaMailSender` phù hợp và xác minh provider cho phép From đó.

### 25.2. Dùng chung production credential trong staging

Staging có thể gửi thư thật hoặc lộ secret qua log/debug. Tạo credential sandbox riêng và không cấp secret production cho workload staging.

### 25.3. Cho request chọn SMTP profile tùy ý

Request ngoài không được quyền chuyển mục đích marketing thành security hoặc chọn account quyền cao. Route dựa trên use case đã được xác thực và policy nội bộ.

### 25.4. Dùng một mutable sender rồi đổi password trước mỗi lần gửi

Gửi song song có thể race và dùng sai credential. Tạo sender riêng hoặc registry an toàn với cấu hình cố định.

### 25.5. Dùng @Primary để che thiếu route

Một service quên `@Qualifier` có thể tự dùng default sender sai chức năng. Khi account có ranh giới bảo mật khác nhau, ưu tiên routing tường minh.

### 25.6. Tách credential nhưng quota vẫn chung

Provider có thể áp quota/reputation ở account cha. Kiểm tra ranh giới quota thực thay vì giả định nhiều username đồng nghĩa cách ly.

### 25.7. Bỏ qua SPF/DKIM/DMARC khi đổi From/subdomain

Credential đúng vẫn có thể dẫn tới email bị từ chối hoặc đánh dấu spam vì domain alignment không phù hợp.

### 25.8. Tắt xác minh TLS để kết nối thành công

`ssl.trust=*` hoặc STARTTLS không bắt buộc có thể làm mất bảo vệ kết nối. Cần cấu hình truststore/chứng chỉ đúng.

### 25.9. Log nguyên ConfigurationProperties

Record có password trong `toString()` có thể làm lộ credential. Che secret và tránh dump properties.

### 25.10. Đổi secret store nhưng không reload sender

Credential đã rotate nhưng singleton sender vẫn giữ password cũ. Cần rolling restart hoặc thay instance có quản lý.

### 25.11. Tự động failover marketing sang security

Có thể vượt restriction hoặc chiếm quota của email bảo mật. Chỉ failover tới account đã được phê duyệt cho cùng purpose.

### 25.12. Không có recipient guard ở non-production

Ngay cả account sandbox hoặc profile đúng vẫn có thể được cấu hình sai. Dùng allowlist và policy ở application boundary để giảm rủi ro.

### 25.13. Giả định account khác nghĩa IP reputation hoàn toàn khác

Các account cùng provider có thể dùng shared IP pool hoặc chính sách reputation chung. Xác minh cơ chế tách thực tế khi đây là yêu cầu.

### 25.14. Coi SMTP credential là bằng chứng quyền gửi nội dung

Account có thể xác thực thành công nhưng ứng dụng vẫn phải kiểm tra quyền trên tài nguyên, consent, recipient, tenant và template.

### 25.15. Không giới hạn tốc độ theo chức năng

Tách credential nhưng dùng một queue và pool vô hạn vẫn có thể gây nghẽn hoặc bị provider throttling. Bổ sung bounded queues, rate limit và prioritization phù hợp.

## 26. Câu hỏi thực hành

**Câu 1.** Có hai địa chỉ `security@example.org` và `news@example.org` nhưng cùng một SMTP username/password. Đã tách account chưa?

Chưa. Đây chỉ là hai sender identity nếu credential không đổi; account principal, quota và quyền có thể vẫn dùng chung.

**Câu 2.** Có thể chỉ đặt `helper.setFrom("security@example.org")` để chọn account bảo mật không?

Không. `setFrom` đặt header; phải chọn `JavaMailSender` với credential đúng và xác minh provider cho phép sender identity đó.

**Câu 3.** Staging có nên dùng production credential vì đã có `@Profile("staging")` không?

Không nên. Profile có thể cấu hình sai và không hạn chế quyền credential. Dùng secret staging riêng, provider sandbox và recipient guard.

**Câu 4.** Vì sao marketing và security nên được cách ly?

Vì khác rủi ro, consent, quota, uy tín gửi và yêu cầu độ tin cậy. Một sự cố marketing không nên tự động ảnh hưởng luồng reset password.

**Câu 5.** Dùng hai SMTP user dưới cùng provider account có bảo đảm quota độc lập không?

Không. Cần kiểm tra provider áp quota và reputation ở cấp nào.

**Câu 6.** Có thể cho client truyền `smtpAccountName` vào endpoint gửi thư không?

Không nên. Client phải được kiểm tra quyền và thực hiện use case; application policy quyết định account.

**Câu 7.** `@Primary` có luôn là lựa chọn tốt khi có ba `JavaMailSender` không?

Không. Một sender mặc định có thể che các vị trí quên chỉ định account. Với các luồng nhạy cảm, explicit router hoặc `@Qualifier` rõ ràng thường an toàn hơn.

**Câu 8.** Vì sao không nên mutate `JavaMailSenderImpl` singleton trong lúc gửi nhiều email?

Vì các thread có thể xen kẽ sửa username/password/host, làm thư đi nhầm account hoặc gặp lỗi khó dự đoán.

**Câu 9.** Credential marketing bị lộ. Phân tách giúp gì?

Cho phép thu hồi/rotate credential marketing, giảm khả năng ảnh hưởng đến credential security và transactional, nếu provider thật sự giới hạn quyền riêng.

**Câu 10.** STARTTLS `enable=true` có luôn bảo đảm mail không gửi qua kết nối plaintext không?

Không nếu cấu hình/policy không bắt buộc TLS. Khi yêu cầu TLS, dùng `required=true` và xác minh chứng chỉ/hostname.

**Câu 11.** Một email gửi được bằng SMTP có chứng minh SPF/DKIM/DMARC hợp lệ không?

Không. Transport submission và domain authentication/deliverability là các tầng khác nhau.

**Câu 12.** Job outbox lưu `MailPurpose.TRANSACTIONAL`. Khi retry có nên tự đổi sang account marketing đang rảnh không?

Không mặc định. Retry phải giữ mục đích nghiệp vụ và tuân thủ policy account/failover đã được phê duyệt.

**Câu 13.** Vì sao nên tách account staging và production ngay cả khi dùng cùng template?

Vì khác môi trường, dữ liệu, người nhận và mức độ ảnh hưởng của sai sót. Template giống nhau không làm credential production an toàn để sử dụng trong staging.

**Câu 14.** Nếu dùng account riêng nhưng chung thread pool, các luồng đã hoàn toàn cách ly chưa?

Chưa. Vẫn có thể tranh chấp thread, queue, memory và quota provider. Cách ly vận hành có thể cần executor, queue và rate policy riêng.

## 27. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Request / Event"] --> B["Application use case"]
    B --> C["Authorization + recipient policy"]
    C --> D["Mail purpose được xác định nội bộ"]
    D --> E["Routing gateway"]
    E --> F{"Chức năng?"}
    F -->|"SECURITY"| G["Security SMTP account"]
    F -->|"TRANSACTIONAL"| H["Transactional SMTP account"]
    F -->|"MARKETING"| I["Marketing SMTP account"]
    G --> J["SMTP provider"]
    H --> J
    I --> J
    K["Local/Staging/Prod policies"] --> E
    L["Secret manager + TLS + domain policy"] --> E
~~~

Hãy ghi nhớ:

1. **Tách account là tách principal/credential và quyền**, không chỉ thay địa chỉ `From`.
2. **Tách theo môi trường** để dev/staging không thể vô tình gửi bằng production secret.
3. **Tách theo chức năng** khi security, transactional và marketing có quyền, quota, consent hoặc rủi ro khác nhau.
4. **Kiểm tra mức độ cách ly thực tế của provider**; nhiều SMTP user không chắc có quota/reputation độc lập.
5. **Mỗi SMTP account có cấu hình transport riêng**, gồm host, port, username, password và TLS mode.
6. **Spring Boot `spring.mail.*` thường mô tả một sender**, còn nhiều account cần nhiều bean hoặc registry do ứng dụng quản lý.
7. **Route tường minh theo MailPurpose và policy nội bộ**, không theo raw account name/From do client truyền.
8. **Giữ sender configuration cố định trong lúc gửi**, tránh mutate singleton giữa nhiều thread.
9. **Quản lý secret, rotation, revocation và log masking** ở runtime; không commit credential.
10. **STARTTLS/implicit TLS cần xác minh chứng chỉ**, và sender domain cần được thiết lập SPF/DKIM/DMARC theo provider.
11. **Tách account không thay thế recipient authorization, consent, suppression hay idempotency**.
12. **Kiểm thử môi trường, routing, negative cases và giám sát quota/rejection** trước khi vận hành production.

Trong Spring Framework Mail, `JavaMailSenderImpl` đại diện cho cấu hình SMTP transport cụ thể; `MimeMessageHelper` dựng message; application service và routing gateway quyết định **account nào được phép dùng cho loại thông báo nào**. Khi tách account theo môi trường và chức năng đúng mức, ứng dụng giảm phạm vi thiệt hại nếu credential bị lộ, hạn chế gửi nhầm email thật từ môi trường thử nghiệm và vận hành các luồng thông báo quan trọng độc lập, dễ kiểm soát hơn.
