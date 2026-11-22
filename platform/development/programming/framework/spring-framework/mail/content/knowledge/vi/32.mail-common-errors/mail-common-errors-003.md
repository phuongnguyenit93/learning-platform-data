# Tắt TLS verification để né lỗi chứng chỉ

Khi tích hợp gửi email bằng **Spring Framework Mail**, ứng dụng thường kết nối đến SMTP relay qua TLS. Trong lúc cấu hình, rất nhiều lập trình viên gặp lỗi như `PKIX path building failed`, `SSLHandshakeException`, `No subject alternative DNS name matching` hoặc `Could not convert socket to TLS`. Một giải pháp được truyền miệng là đặt `mail.smtp.ssl.trust=*`, tắt kiểm tra hostname hoặc dùng một `TrustManager` “chấp nhận tất cả”.

Giải pháp đó có thể khiến thao tác gửi email chạy lại, nhưng **không chứng minh ứng dụng đã kết nối đến máy chủ SMTP thật và đáng tin**. Nếu kết nối đi đến máy chủ giả mạo hoặc qua một thiết bị trung gian không được phép, dữ liệu người nhận, nội dung email và thông tin đăng nhập SMTP có thể bị lộ. Đặc biệt, email thường chứa OTP, đường dẫn đặt lại mật khẩu, thông tin hóa đơn hoặc các dữ liệu nghiệp vụ nhạy cảm.

**Thông điệp quan trọng:** Không nên tắt TLS certificate validation hay hostname verification để “né” lỗi trên production. Hãy xác định nguyên nhân thực: hostname sai, cổng/kiểu TLS sai, chứng chỉ hết hạn, chuỗi CA thiếu intermediate, truststore của JVM chưa có CA phù hợp, proxy can thiệp, đồng hồ hệ thống sai hoặc TLS protocol không tương thích.

Bài này giải thích các cơ chế bảo mật cần giữ, những cấu hình Spring Mail nguy hiểm, cách cấu hình STARTTLS/implicit TLS đúng và quy trình khắc phục lỗi có thể áp dụng cho Spring Boot, `JavaMailSenderImpl`, Jakarta Mail và SMTP provider.

## 1. TLS bảo vệ điều gì khi Spring gửi email?

Một kết nối gửi email đi qua nhiều lớp:

~~~text
Business service / Mail worker
            |
            v
JavaMailSender / Jakarta Mail
            |
            | SMTP submission
            | TLS (STARTTLS hoặc implicit TLS)
            v
SMTP relay / email provider
            |
            v
Những mail server tiếp theo và mailbox của người nhận
~~~

TLS trong đoạn kết nối **Spring application → SMTP relay** cần giải quyết ba vấn đề:

1. **Confidentiality (bảo mật truyền tải):** giảm khả năng bên thứ ba đọc trộm credential, email và nội dung message khi đang truyền.
2. **Integrity (toàn vẹn):** giảm khả năng dữ liệu truyền bị thay đổi không phát hiện.
3. **Server authentication (xác thực máy chủ):** giúp client kiểm chứng đối tác TLS đúng với hostname đã định và thuộc chuỗi chứng chỉ được tin cậy.

### 1.1. Mã hóa không đồng nghĩa xác thực máy chủ

Giả sử ứng dụng kết nối tới `smtp.provider.example` qua một mạng không đáng tin:

~~~text
Spring application
       |
       | TLS nhưng client trust mọi certificate
       v
Máy chủ giả mạo
       |
       | Có thể ghi nhận credential / message
       v
SMTP provider thật (nếu attacker chuyển tiếp)
~~~

Nếu ứng dụng chấp nhận **bất kỳ chứng chỉ** nào, kẻ tấn công có thể thiết lập kết nối TLS được mã hóa **với chính họ**. Dữ liệu vẫn được mã hóa trên đường truyền, nhưng không còn được bảo vệ trước đối tác giả mạo như mong đợi.

| Cơ chế | Mục đích | Nếu bị bỏ qua |
| --- | --- | --- |
| TLS encryption | Bảo vệ dữ liệu trên đường truyền | Có thể gửi plaintext |
| Certificate chain verification | Chứng chỉ nối tới trust anchor hợp lệ | Có thể chấp nhận chứng chỉ do bất kỳ bên nào cấp |
| Hostname verification | Chứng chỉ dành cho máy chủ đang kết nối | Chấp nhận certificate của host khác |
| STARTTLS required | Không tiếp tục nếu không nâng cấp TLS | Có thể downgrade xuống plaintext |
| SMTP AUTH | Xác thực tài khoản có quyền gửi | Không thay thế được xác thực server |

### 1.2. SMTP AUTH không thay thế TLS identity

`mail.smtp.auth=true` chỉ yêu cầu client dùng một cơ chế SMTP authentication phù hợp. Nó không đảm bảo certificate của máy chủ hợp lệ. Nếu ứng dụng bỏ xác thực server, credential hoặc token có thể bị trình bày trước endpoint không đáng tin, tùy giao thức/auth mechanism.

Trình tự an toàn về mặt logic:

~~~text
1. Kết nối đúng hostname / port.
2. Bắt đầu hoặc nâng cấp TLS theo chính sách.
3. Xác minh chain + hostname của server.
4. Thực hiện SMTP authentication nếu cần.
5. Gửi MAIL FROM, RCPT TO, DATA.
6. Ghi nhận kết quả submission.
~~~

Không dùng một lần AUTH thành công để chứng minh các bước trước đó đã an toàn.

### 1.3. TLS ở đoạn đầu không bảo đảm toàn bộ đường đi của email

Spring kết nối SMTP relay bằng TLS đúng chỉ chứng minh lớp transport ở **đoạn Spring → relay** được bảo vệ theo chính sách. Message có thể tiếp tục qua nhiều SMTP hop; việc email đến Inbox, được ký DKIM hoặc được đọc là những vấn đề riêng.

Không coi `JavaMailSender.send(...)` trả về thành công là bằng chứng message đã được giao tới Inbox. Nó thường chỉ cho biết SMTP submission hoàn tất theo contract của transport adapter.

## 2. Ba lớp thường bị đánh đồng

### 2.1. Certificate chain validation

SMTP server trình bày một chain như:

~~~text
Trusted Root CA
      |
      v
Intermediate CA
      |
      v
Leaf certificate: smtp.provider.example
~~~

Client cần xác minh chữ ký, điều kiện sử dụng, thời hạn và tìm được đường tin cậy tới CA thuộc truststore phù hợp. Nếu không xây được chuỗi tin cậy, Java có thể báo:

~~~text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed

Caused by:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
~~~

**Lỗi PKIX không có nghĩa cần tắt TLS.** Nó thường yêu cầu kiểm tra certificate chain, CA và truststore.

### 2.2. Hostname verification

Chứng chỉ được CA tin cậy ký vẫn có thể thuộc về **một host khác**.

~~~text
App connects:
    smtp-b.provider.example

Certificate SAN:
    DNS:smtp-a.provider.example

Chain valid: YES
Hostname match: NO
=> Phải từ chối kết nối.
~~~

Certificate hiện đại dùng **Subject Alternative Name (SAN)** để liệt kê DNS names hoặc IP addresses hợp lệ. Đối chiếu hostname phải tuân theo quy tắc identity checking của TLS. Khi kết nối theo địa chỉ IP, không thể mặc định certificate chỉ có DNS SAN là đủ.

### 2.3. TLS mode và chính sách downgrade

Với SMTP submission trên port 587, STARTTLS thường bắt đầu bằng giao thức SMTP chưa mã hóa rồi mới nâng cấp. Nếu ứng dụng cho phép tiếp tục khi STARTTLS không được server quảng bá, kẻ tấn công hoặc proxy lỗi có thể khiến client không dùng TLS theo chính sách mong muốn.

Do đó cần phân biệt:

- `mail.smtp.starttls.enable=true`: bật khả năng nâng cấp bằng STARTTLS.
- `mail.smtp.starttls.required=true`: **yêu cầu** nâng cấp; không tiếp tục nếu không thể dùng TLS.

Khi cần bảo vệ credential và email bắt buộc, nên dùng cả hai trên một submission endpoint hỗ trợ STARTTLS.

## 3. Những cấu hình “sửa nhanh” nguy hiểm

| Cách làm | Tác động | Lý do không dùng để sửa sự cố |
| --- | --- | --- |
| `mail.smtp.ssl.trust=*` | Cấu hình SMTP provider tin tất cả host theo cơ chế SSL socket factory tương ứng | Bỏ qua rào chắn kiểm tra chuỗi tin cậy thông thường |
| `mail.smtp.ssl.trust=smtp.example` | Trust host chỉ định qua cơ chế đặc biệt | Vẫn có thể là bypass CA validation, không phải chứng minh chain hợp lệ |
| `mail.smtp.ssl.checkserveridentity=false` | Không yêu cầu kiểm tra tên certificate theo JavaMail property | Hostname mismatch có thể bị bỏ qua |
| Trust-all `X509TrustManager` | Chấp nhận mọi leaf/issuer | Certificate giả, hết hạn, tự ký có thể được chấp nhận |
| Hostname verifier luôn trả `true` | Tắt kiểm tra identity | Không biết server có đúng host đã chọn |
| `starttls.required=false` khi policy yêu cầu TLS | Cho phép sử dụng STARTTLS theo kiểu cơ hội | Có nguy cơ tiếp tục trên kết nối không được nâng cấp |
| Retry plaintext sau handshake error | Thay đổi chính sách bảo mật khi có sự cố | Một lỗi TLS không phải lý do gửi dữ liệu ít an toàn hơn |

### 3.1. Anti-pattern: trust mọi SMTP host

**Ví dụ cấu hình không an toàn — chỉ để nhận diện, không triển khai:**

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.ssl.trust]": "*"
~~~

Nếu lỗi `PKIX` biến mất sau thay đổi này, điều đó chỉ cho thấy một phần kiểm tra đã bị bỏ qua. Nó **không chứng minh certificate thật, tên server đúng hoặc giao tiếp an toàn**.

### 3.2. Anti-pattern: tắt kiểm tra hostname

**Ví dụ không nên làm:**

~~~properties
spring.mail.properties.mail.smtp.ssl.checkserveridentity=false
~~~

Khi certificate SAN không khớp, sửa **`spring.mail.host`, DNS/alias hoặc chứng chỉ phía server**. Nếu phía server chỉ cung cấp certificate cho hostname chính thức của provider, hãy kết nối bằng hostname đó thay vì một alias tùy ý.

### 3.3. Anti-pattern: tự viết trust-all socket factory

Một số dự án tự truyền `SSLSocketFactory`/`SSLContext` tạo từ `X509TrustManager` luôn chấp nhận chain. Đây là cách che các lỗi cấu hình và làm việc audit TLS trở nên khó khăn.

Ưu tiên **JSSE mặc định với truststore được quản trị**, hoặc một TLS context chuyên biệt đã được review nhưng vẫn kiểm tra chain **và** hostname. Không biến một workaround test thành hành vi của production.

### 3.4. “Chỉ tắt trên CI” có được không?

Điều đó phụ thuộc **mục tiêu kiểm thử**:

- Unit test render MIME hoặc gửi tới SMTP giả lập loopback không nhằm kiểm tra TLS có thể dùng server test plaintext và test profile cô lập, không dùng credential/email thật.
- Integration test **đang xác minh TLS** phải giữ certificate chain và hostname verification, với test CA/test certificates đúng.

Không thể tuyên bố TLS test đã pass nếu nó chỉ pass sau khi bật `ssl.trust=*`.

## 4. Chọn đúng SMTP port và TLS mode

Hai cơ chế thường gặp:

| Port thường dùng | Cơ chế | Trình tự |
| --- | --- | --- |
| **587** | SMTP submission + STARTTLS | TCP → SMTP greeting/EHLO → STARTTLS → TLS handshake → AUTH |
| **465** | SMTP submission + implicit TLS | TCP → TLS handshake ngay → SMTP greeting/EHLO qua TLS → AUTH |
| **25** | SMTP relay/server-to-server | Phụ thuộc server, routing và policy; không mặc định là port submission phù hợp |

Port thực tế phải theo tài liệu SMTP provider. Một số doanh nghiệp sử dụng endpoint/port riêng.

### 4.1. STARTTLS trên 587

~~~text
Client                          SMTP server
  |-------- TCP -------------------->|
  |<------- 220 greeting -----------|
  |-------- EHLO ------------------>|
  |<------- STARTTLS offered -------|
  |-------- STARTTLS -------------->|
  |<------- 220 Ready -------------|
  |========== TLS handshake ========|
  |-------- EHLO over TLS --------->|
  |-------- AUTH over TLS --------->|
  |-------- MAIL/RCPT/DATA -------->|
~~~

Nếu dùng `mail.smtp.ssl.enable=true` trên một endpoint **đang chờ SMTP greeting plaintext**, client có thể gửi TLS ClientHello sai thời điểm và nhận lỗi handshake, timeout hoặc `Unsupported or unrecognized SSL message`. Không phải cứ có chữ SSL trong lỗi là certificate trust bị sai.

### 4.2. Implicit TLS trên 465

~~~text
Client                          SMTP server
  |-------- TCP -------------------->|
  |========== TLS handshake ========|
  |<------- 220 greeting over TLS --|
  |-------- EHLO/AUTH/DATA -------->|
~~~

Nếu cố bắt đầu plaintext/STARTTLS tới endpoint chờ TLS ngay từ byte đầu, kết nối cũng có thể thất bại. Sửa protocol mode, **không tắt verification**.

### 4.3. Không suy từ port rằng TLS chắc chắn đã được dùng

Cấu hình port đúng vẫn phải kiểm tra negotiation, certificate chain và hostname. Không cho phép cơ chế fallback sang plaintext trái policy. Khi đổi provider hoặc relay, xác minh endpoint mới thực sự hỗ trợ chế độ mong muốn.

## 5. Cấu hình Spring Boot an toàn cho STARTTLS 587

Ví dụ `application.yml`:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Giải thích:

- `spring.mail.host` phải trùng hostname hợp lệ của dịch vụ SMTP, phù hợp certificate SAN.
- `port=587` cần khớp cơ chế STARTTLS do provider công bố.
- `mail.smtp.auth=true` bật yêu cầu SMTP AUTH khi dùng credential.
- `starttls.enable=true` cho phép nâng cấp giao thức.
- `starttls.required=true` từ chối tiếp tục khi không nâng cấp được TLS.
- `ssl.checkserveridentity=true` yêu cầu kiểm tra danh tính hostname trong Jakarta Mail SMTP provider.
- Các timeout giúp worker không chờ mạng vô thời hạn.
- `SMTP_USERNAME` và `SMTP_PASSWORD` được inject từ secret manager/environment an toàn, không commit secret vào mã nguồn.

**Không có `mail.smtp.ssl.trust=*` và không có custom trust-all manager.** JVM cần có trust anchors hợp lệ cho chain mà SMTP provider trình bày.

### 5.1. Vì sao dùng cú pháp dấu ngoặc vuông?

Jakarta Mail nhận property keys như `mail.smtp.starttls.required`. Trong YAML của Spring Boot, dùng:

~~~yaml
properties:
  "[mail.smtp.starttls.required]": "true"
~~~

giúp giữ nguyên key có dấu chấm khi bind vào `Map` properties. Dạng tương đương trong `application.properties`:

~~~properties
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

Nếu ứng dụng tự tạo nhiều `JavaMailSender` bean, cần kiểm tra properties thật sự được gán cho **đúng** sender. Đừng chỉ sửa YAML mặc định trong khi code đang dùng một sender custom không nhận các thuộc tính đó.

### 5.2. Nếu không thấy STARTTLS từ server

Khi `required=true`, ứng dụng nên thất bại thay vì âm thầm gửi plaintext. Điều tra:

- hostname/port có đúng endpoint submission không;
- provider có quảng bá STARTTLS không;
- proxy/firewall/TLS inspection có thay đổi phiên SMTP hay không;
- load balancer trỏ tới node cấu hình khác;
- account/region/provider policy có yêu cầu port khác không.

Không đổi `required=false` chỉ để giúp tác vụ gửi “thành công”.

## 6. Cấu hình Spring Boot an toàn cho implicit TLS 465

Nếu provider công bố SMTP submission qua TLS ngay từ đầu:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 465
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

`mail.smtp.ssl.enable=true` tạo kết nối TLS ngay khi mở socket. Không dùng STARTTLS để nâng cấp một kết nối đã có implicit TLS.

Một số dự án JavaMail cũ dùng protocol `smtps` cùng prefix `mail.smtps.*`. Với `JavaMailSenderImpl` dùng protocol `smtp` và `mail.smtp.ssl.enable=true` như ví dụ, properties bắt đầu bằng `mail.smtp.*`. **Không pha lẫn prefix tùy tiện**; xác minh giao thức/phiên bản SMTP provider thực tế.

## 7. Tạo JavaMailSenderImpl thủ công

Khi cần sender profile riêng hoặc không dùng Boot autoconfiguration:

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {
    private SmtpSenderFactory() {}

    public static JavaMailSenderImpl createStartTlsSender(
            String hostname,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setProtocol("smtp");
        sender.setHost(hostname);
        sender.setPort(587);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties p = sender.getJavaMailProperties();
        p.put("mail.smtp.auth", "true");
        p.put("mail.smtp.starttls.enable", "true");
        p.put("mail.smtp.starttls.required", "true");
        p.put("mail.smtp.ssl.checkserveridentity", "true");
        p.put("mail.smtp.connectiontimeout", "5000");
        p.put("mail.smtp.timeout", "10000");
        p.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

Ví dụ sử dụng:

~~~java
JavaMailSenderImpl sender =
        SmtpSenderFactory.createStartTlsSender(
                "smtp.provider.example",
                smtpUsername,
                smtpPassword);
~~~

Đây là mẫu cấu hình, chưa bao gồm routing nhiều sender, secret rotation, proxy, monitoring hoặc provider-specific OAuth2. Credential cần lấy từ nguồn bảo mật phù hợp và không được in ra log.

### 7.1. Lưu ý hostname và socket factory

Nếu dùng `smtp.internal` để kết nối đến proxy nhưng certificate chỉ có SAN `smtp.provider.example`, việc verify hostname sẽ thất bại. Cần sử dụng **endpoint identity được hạ tầng công bố và có certificate hợp lệ**, hoặc cấu hình proxy/certificate tương ứng.

Không gắn một custom `SSLSocketFactory` trust-all vào sender nhằm bỏ qua sai sót này.

## 8. Phân loại lỗi trước khi sửa

“Không gửi được email” không đủ để xác định lỗi TLS. Cần đọc nested exception từ Spring Mail và Jakarta Mail.

| Thông báo thường gặp | Khả năng liên quan | Việc cần kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Thiếu trust path, CA/intermediate, truststore | Server chain và JVM truststore |
| `unable to find valid certification path` | Không tìm trust anchor | CA, truststore, proxy |
| `No name matching ... found` | Hostname mismatch | Host cấu hình và SAN |
| `No subject alternative DNS name matching` | SAN không phù hợp | DNS/IP endpoint và certificate |
| `CertificateExpiredException` | Certificate hết hạn | Chain, rotation và đồng hồ |
| `CertificateNotYetValidException` | Chưa đến thời gian hiệu lực | Validity/clock |
| `handshake_failure` | Protocol, cipher, certificate, mTLS hoặc policy | TLS capabilities hai phía |
| `protocol_version` | TLS protocol version không tương thích | JDK/server/TLS policy |
| `Unsupported or unrecognized SSL message` | Sai implicit TLS vs STARTTLS, endpoint hoặc proxy | Host, port, mode |
| `Could not convert socket to TLS` | STARTTLS handshake lỗi | Nested cause, server EHLO và chain |
| `STARTTLS is required but host does not support STARTTLS` | Không thấy STARTTLS | Server/port/proxy |
| `MailAuthenticationException` / `535` | Username/password/OAuth/account policy | SMTP AUTH, không phải chỉ cert |
| `Connection refused` | TCP endpoint chưa chấp nhận kết nối | Firewall, host, port |
| `Connect timed out` | Network/routing hoặc service không phản hồi | Connectivity trước TLS |
| `Read timed out` | Server không phản hồi đúng lúc hoặc mode sai | Network/protocol phase |

### 8.1. Ví dụ PKIX path building failed

~~~text
org.springframework.mail.MailSendException:
  Mail server connection failed
Caused by: javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
Caused by:
  SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

Đây là tín hiệu không xây được chain tin cậy. Cần tìm hiểu liệu server thiếu intermediate, JVM thiếu CA, truststore custom bị sai hay TLS inspection đang trình bày một certificate khác.

### 8.2. Ví dụ hostname mismatch

~~~text
Connected host: mail.company.internal
Presented SAN:
  DNS:smtp.provider.example
~~~

Chain có thể hợp lệ nhưng hostname không khớp. Giải pháp là dùng đúng endpoint hoặc cấp certificate hợp lệ cho hostname nội bộ, không bỏ `checkserveridentity`.

### 8.3. Ví dụ AUTH error

~~~text
535 5.7.8 Authentication credentials invalid
~~~

Kiểm tra credential, tài khoản, OAuth scope, SMTP AUTH policy và quyền gửi. Đừng thay CA trust hoặc giảm TLS verification khi vấn đề là SMTP account.

### 8.4. Ví dụ sai TLS mode

~~~text
App: port 587 + implicit TLS ClientHello
SMTP relay: chờ plaintext SMTP greeting
=> handshake timeout / unrecognized SSL message
~~~

Sửa đúng chế độ port 587 STARTTLS hoặc endpoint 465 implicit TLS theo tài liệu provider.

## 9. Runbook chẩn đoán khi SMTP TLS thất bại

~~~mermaid
flowchart TD
    A["SMTP send error"] --> B{"TCP connect đến host/port?"}
    B -->|No| C["DNS, firewall, routing, port"]
    B -->|Yes| D{"TLS mode đúng?"}
    D -->|No| E["STARTTLS vs implicit TLS"]
    D -->|Yes| F{"Handshake + certificate verification"}
    F -->|PKIX| G["CA / chain / truststore / proxy"]
    F -->|Hostname| H["SAN / DNS / SNI / alias"]
    F -->|TLS protocol| I["JVM / TLS versions / ciphers"]
    F -->|Success| J{"SMTP AUTH?"}
    J -->|Failure| K["Credentials, token, account policy"]
    J -->|Success| L["SMTP response / job outcome"]
~~~

### Bước 1: Thu thập sự kiện

Ghi lại:

- thời điểm lỗi và sender profile bị ảnh hưởng;
- hostname/port/TLS mode dự định;
- version JDK và JavaMail/Jakarta Mail provider;
- môi trường chạy: laptop, CI, VM hay Kubernetes;
- exception class, nested cause đã loại bỏ bí mật;
- provider endpoint/region nếu có nhiều;
- các thay đổi gần đây: certificate rotation, truststore, deploy, proxy;
- số job đang chờ do lỗi.

Không thu thập nguyên email MIME/OTP/password vào ticket chỉ để debug certificate.

### Bước 2: Xác minh endpoint

Tra tài liệu SMTP provider và đối chiếu:

- hostname được công bố;
- port submission được yêu cầu;
- STARTTLS hay implicit TLS;
- certificate SAN mà server sẽ trình bày;
- có yêu cầu IP allowlist, mTLS hoặc proxy nội bộ không.

Kiểm tra DNS/CNAME và network routing. Một alias nội bộ trỏ cùng IP không tự biến certificate của hostname khác thành hợp lệ.

### Bước 3: Xác minh TCP

Trên Windows có thể dùng:

~~~powershell
Test-NetConnection smtp.provider.example -Port 587
~~~

Kết quả TCP thành công **chưa phải** handshake TLS thành công, và không xác nhận SMTP authentication. Nếu TCP không kết nối được, điều tra DNS, firewall, network policies, proxy hoặc port trước.

### Bước 4: Kiểm tra certificate và hostname độc lập

Dùng OpenSSL với đúng host, port và TLS mode như mục 10. So sánh kết quả với những gì ứng dụng Java nhìn thấy; đừng mặc định trust anchors của OpenSSL và JVM giống nhau.

### Bước 5: Kiểm tra truststore thực của Java process

Một image Docker có thể mang `cacerts` khác hệ điều hành hoặc workstation. Một custom `javax.net.ssl.trustStore` có thể thay thế tập CA mặc định. Xác nhận **đúng process** và **đúng đường dẫn** đang dùng trước khi import bất kỳ certificate nào.

### Bước 6: Sửa nguyên nhân, giữ fail-closed

| Nguyên nhân | Khắc phục chính |
| --- | --- |
| Hostname không khớp SAN | Sửa host/endpoint hoặc server certificate |
| Thiếu intermediate | Sửa full chain do server trình bày |
| Internal CA đáng tin nhưng Java chưa có | Thêm CA được xác minh vào truststore phù hợp |
| Certificate hết hạn | Rotate certificate trên server |
| Clock sai | Đồng bộ thời gian hệ thống |
| Port/TLS mode sai | Dùng đúng STARTTLS hoặc implicit TLS |
| STARTTLS bị ngăn bởi proxy | Sửa proxy/network route hoặc dùng endpoint hợp lệ |
| TLS cipher/protocol mismatch | Nâng cấp hoặc điều chỉnh theo security policy |
| AUTH sai sau TLS | Sửa account/credential/permission/token |

### Bước 7: Xác minh phục hồi

~~~text
TCP connectivity          OK
Expected TLS mode         OK
Certificate chain         TRUSTED
Hostname                  MATCHES
Required TLS              NEGOTIATED
SMTP authentication       OK
SMTP submission           ACCEPTED
~~~

Sau đó theo dõi outbox backlog, retries và delivery events. SMTP submission thành công vẫn không chứng minh thư đã đến Inbox.

## 10. Dùng OpenSSL kiểm tra STARTTLS/SMTPS

Các lệnh cần phiên bản OpenSSL hỗ trợ các tùy chọn tương ứng. Chúng chỉ kiểm tra endpoint ở môi trường chạy lệnh; JVM production có thể dùng truststore khác.

### 10.1. Port 587 — STARTTLS

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.provider.example:587 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example \
  -verify_return_error \
  -showcerts
~~~

- `-starttls smtp` thực hiện bước nâng cấp SMTP.
- `-connect` chọn host/port.
- `-servername` gửi SNI khi phù hợp.
- `-verify_hostname` đối chiếu certificate với host.
- `-verify_return_error` trả lỗi khi certificate validation thất bại.
- `-showcerts` hiển thị các chứng chỉ server cung cấp.

Không chỉ nhìn dòng `Verify return code: 0` nếu lệnh chưa kiểm tra hostname. Hostname của OpenSSL phải phù hợp `spring.mail.host` của ứng dụng.

### 10.2. Port 465 — implicit TLS

~~~bash
openssl s_client \
  -connect smtp.provider.example:465 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example \
  -verify_return_error \
  -showcerts
~~~

Không thêm `-starttls smtp` cho endpoint 465 implicit TLS, trừ khi provider công bố một mode khác.

### 10.3. SMTP relay ký bởi private CA

Nếu tổ chức dùng private CA đã được xác minh:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.internal.example:587 \
  -servername smtp.internal.example \
  -verify_hostname smtp.internal.example \
  -verify_return_error \
  -CAfile approved-internal-ca.pem \
  -showcerts
~~~

**`approved-internal-ca.pem` phải đến từ kênh PKI đáng tin**, không phải chỉ được tải trực tiếp từ endpoint đang bị nghi ngờ rồi tự động tin cậy.

### 10.4. OpenSSL OK nhưng Spring vẫn PKIX

Có thể do:

- OpenSSL dùng OS CA store, Java dùng `cacerts` riêng;
- JDK/container version cũ chưa có root CA mới;
- Java process có `javax.net.ssl.trustStore` custom;
- một truststore custom không chứa CA công khai cần thiết;
- app và công cụ kết nối khác host/port/route/proxy;
- server trả certificate khác theo SNI/load balancer backend.

Để xác minh, thực hiện từ cùng môi trường/container càng tốt và đọc thêm JSSE debug có kiểm soát.

## 11. JVM truststore và keystore

| Thành phần | Thường chứa | Vai trò |
| --- | --- | --- |
| **Truststore** | Trusted CA certificates/trust anchors | Kiểm chứng server certificate |
| **Keystore** | Certificate/private key của client | Dùng khi client certificate/mTLS cần thiết |

Đối với SMTP AUTH thông thường, Spring ứng dụng không cần xuất trình client certificate; nó cần **tin cậy đúng SMTP server** và cung cấp cơ chế AUTH mà provider yêu cầu.

### 11.1. Truststore mặc định có thể khác theo môi trường

Nhiều JDK/JRE dùng trust anchors từ `cacerts` liên quan đến `java.home`, nhưng cách đóng gói phụ thuộc vendor, distribution và các Java system properties. Không mặc định JVM trong container dùng CA certificates của máy host.

Một đường dẫn ví dụ:

~~~text
<java.home>/lib/security/cacerts
~~~

Hãy kiểm tra runtime/truststore **thật** của ứng dụng thay vì sửa một file trên workstation.

### 11.2. Kiểm tra bằng keytool

~~~bash
keytool -list -v \
  -keystore /secure/path/mail-truststore.p12 \
  -storetype PKCS12
~~~

Kiểm tra alias, Subject, Issuer, SHA-256 fingerprint, thời hạn và trust policy. Bảo vệ mật khẩu truststore; tránh đưa password vào command line/log/ticket.

### 11.3. Import CA nội bộ đã được xác minh

~~~bash
keytool -importcert \
  -alias approved-internal-smtp-ca \
  -file approved-internal-ca.pem \
  -keystore /secure/path/mail-truststore.p12 \
  -storetype PKCS12
~~~

Quy trình nên gồm:

1. Nhận certificate CA từ nguồn PKI có thẩm quyền.
2. Xác minh fingerprint và chính sách sử dụng qua kênh độc lập.
3. Xác nhận đúng CA/chain cần tin cậy.
4. Import vào truststore do đội quản trị kiểm soát.
5. Cấu hình JVM dùng truststore nếu cần.
6. Kiểm tra hostname verification vẫn được bật.
7. Kiểm thử hồi quy các kết nối TLS liên quan.
8. Ghi nhận change và quy trình certificate rotation.

**Không import leaf certificate lạ** chỉ vì nó làm hết lỗi. Trust một leaf tự thu thập qua đường mạng đang nghi ngờ không chứng minh đó là máy chủ đúng, và có thể gây outage khi provider rotate certificate.

### 11.4. Trỏ JVM tới truststore

Ví dụ Java system properties:

~~~text
-Djavax.net.ssl.trustStore=/secure/path/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Khi truststore cần password, quy trình runtime có thể yêu cầu `javax.net.ssl.trustStorePassword`, phải được cung cấp bằng cơ chế secret injection phù hợp. Không ghi password nguyên văn trong source code hoặc logs.

**Cảnh báo:** custom truststore có thể thay thế CA roots mặc định đối với cả JVM. Nếu file mới chỉ có một private CA, các kết nối HTTPS/public SMTP khác có thể bắt đầu lỗi. Cần chủ động quản lý **toàn bộ trusted roots cần thiết** hoặc dùng TLS context theo sender đã được review.

### 11.5. Vì sao không dùng một trust-all factory thay thế?

Vì nó xóa ranh giới kiểm chứng certificate, khiến việc CA rotation, hostname mismatch, tấn công mạng hoặc cấu hình sai đều trông giống “kết nối thành công”. Các lỗi này cần được quan sát và sửa thay vì che giấu.

## 12. Server thiếu intermediate certificate

Một lỗi khá phổ biến là server chỉ gửi leaf certificate:

~~~text
Server sends:
    Leaf: smtp.provider.example

Expected chain:
    Leaf -> Intermediate CA -> Trusted Root CA

Missing:
    Intermediate CA
~~~

Một số desktop/client có thể tìm intermediate từ cache hoặc AIA; Java container khác có thể không tìm được và báo `PKIX`. Giải pháp ưu tiên thường là **sửa full chain trên SMTP server/load balancer**, không import leaf certificate vào mọi client.

### 12.1. Nhiều SMTP backend có certificate khác nhau

~~~text
smtp.provider.example
       |
       +-- backend A: chain valid
       +-- backend B: intermediate missing
       +-- backend C: certificate expired
~~~

Lỗi có thể trông ngẫu nhiên do load balancer. Điều tra certificate qua những route/node liên quan và phối hợp provider. Không vội kết luận Spring Mail “không ổn định” rồi tắt verification.

### 12.2. Chain do server gửi không tự là trusted chain

`-showcerts` chỉ hiển thị những certificate server trình bày; không tự chứng minh tất cả hợp lệ. Cần validation bằng trust anchors độc lập và kiểm tra hostname.

## 13. Hostname, SAN, DNS CNAME, IP và SNI

### 13.1. Hostname chính thức của provider

~~~text
Provider submission host: smtp.provider.example
Presented SAN:            DNS:smtp.provider.example
~~~

Khi đó `spring.mail.host=smtp.provider.example` thường là lựa chọn đúng. Đừng đổi thành IP của server hoặc alias nội bộ chỉ vì muốn tránh DNS và rồi tắt `checkserveridentity`.

### 13.2. CNAME không tự làm certificate hợp lệ cho alias

~~~text
mail.company.example CNAME smtp.provider.example
~~~

Certificate chỉ có `DNS:smtp.provider.example` không tự hợp lệ khi client kết nối **`mail.company.example`**. DNS mapping và certificate identity là hai vấn đề riêng.

Lựa chọn đúng:

- dùng tên chính thức của provider;
- hoặc có certificate hợp lệ cho custom alias theo dịch vụ được hỗ trợ;
- không tắt hostname verification.

### 13.3. Dùng IP

Nếu ứng dụng kết nối `10.20.30.40`, certificate cần danh tính IP phù hợp theo quy tắc verifier. Certificate chỉ có DNS SAN không tự được chấp nhận cho IP. Nếu provider công bố hostname thì nên dùng hostname đó.

### 13.4. SNI và certificate của server khác

Một SMTP service nhiều tenant có thể chọn certificate dựa trên Server Name Indication. Nếu app và diagnostic tool dùng SNI khác nhau, kết quả có thể khác. Đối chiếu hostname, endpoint, SNI và certificate được trình bày thực tế; không dùng `ssl.trust=*` để bỏ qua certificate “nhầm tenant”.

### 13.5. Wildcard certificate

Chứng chỉ `*.example.com` có thể phù hợp `smtp.example.com` nhưng không mặc nhiên phù hợp `smtp.eu.example.com`. Đừng suy “cùng domain chính” nghĩa là hợp lệ; cần xem SAN và quy tắc wildcard matching.

## 14. Certificate hết hạn, chưa hiệu lực và đồng hồ sai

Certificate có khoảng `Not Before` và `Not After`. Nếu certificate hoặc intermediate hết hạn, validation có thể thất bại. Nếu system clock sai, một certificate hợp lệ ngoài thực tế có thể trông như chưa bắt đầu hiệu lực.

~~~text
Certificate:
  Not Before: 2026-11-01
  Not After:  2026-12-01

Application clock:
  2026-10-01

=> Có thể báo certificate not yet valid.
~~~

Hướng xử lý:

- kiểm tra NTP/time synchronization;
- xem thời gian thực của host/VM/container;
- xác minh leaf và intermediate validity;
- xác minh provider đã rotate certificate chưa;
- thực hiện rotation trước khi hết hạn.

Không dùng trust-all để “bỏ qua expired certificate”, vì những thay đổi tiếp theo của cert có thể tiếp tục làm ứng dụng nói chuyện với endpoint sai.

### 14.1. Rotation có kế hoạch

Với private CA:

1. Thêm CA mới đã được phê duyệt vào truststore ở giai đoạn overlap.
2. Deploy app/JVM image mới, xác minh client tin chain mới.
3. Rotate certificate trên SMTP server.
4. Giám sát handshake success ở mọi region/replica.
5. Thu hồi/bỏ CA cũ theo chính sách sau thời gian chuyển.

Theo dõi ngày hết hạn certificate để không phải xử lý bằng workaround trong một sự cố khẩn cấp.

## 15. Proxy doanh nghiệp và TLS inspection

Một số mạng có TLS interception appliance:

~~~text
Spring application
      |
      v
Corporate inspection proxy
      |
      v
SMTP provider
~~~

Client có thể nhìn thấy certificate do corporate CA ký thay vì chain trực tiếp của SMTP provider. Nếu đây là kiến trúc **đã được phê duyệt**, cần phối hợp nhóm bảo mật để:

- xác minh proxy và CA thực sự thuộc tổ chức;
- kiểm tra certificate SAN vẫn phù hợp hostname;
- cài đúng corporate CA vào truststore nếu policy cho phép;
- xác định việc đọc SMTP AUTH/email content qua inspection có được phép hay không.

Nếu interception không được phép đối với dữ liệu gửi thư, cần sửa route/proxy policy hoặc thiết kế bypass có kiểm soát. **Không tự tin một CA mới chỉ vì proxy đưa nó đến client**.

### 15.1. Laptop OK, container lỗi

~~~text
Laptop developer: SMTP TLS OK
CI container:      PKIX path building failed
Production pod:    SMTP TLS OK
~~~

Có thể CI dùng image/JVM cũ, thiếu corporate CA, truststore mount sai hoặc đi qua một route/proxy khác. Hãy xác minh đúng môi trường lỗi và chính sách certificate; không biến `ssl.trust=*` thành biến môi trường mặc định của CI/production.

## 16. TLS protocol/cipher mismatch

`SSLHandshakeException` không nhất thiết là lỗi CA. Server và JVM có thể không hỗ trợ cùng protocol/cipher hoặc security policy khác nhau.

~~~text
Client: TLS 1.2, TLS 1.3
Server: TLS 1.0 only
=> Không có phiên bản an toàn chung.
~~~

Hướng khắc phục:

- nâng cấp SMTP relay/provider;
- dùng JDK/Jakarta Mail/provider được hỗ trợ;
- kiểm tra TLS 1.2/1.3 theo policy;
- kiểm tra Java security disabled algorithms/cipher suites;
- kiểm tra endpoint có yêu cầu client certificate (mTLS) không;
- rà soát load balancer/proxy TLS termination.

Một property liên quan:

~~~properties
mail.smtp.ssl.protocols=TLSv1.2 TLSv1.3
~~~

Đây là ví dụ lựa chọn protocol trong trường hợp **JVM/provider thực sự hỗ trợ và policy cho phép**. Không ép TLS 1.0/1.1 chỉ để giao tiếp với server cũ; ưu tiên nâng cấp server.

### 16.1. Tắt verification không sửa được cipher mismatch

Việc bỏ chain/hostname validation không làm hai phía có thêm cipher suite chung hay đổi cơ chế TLS handshake đúng. Nếu `handshake_failure` xảy ra trước certificate validation, trust-all còn có thể che hướng điều tra thật.

## 17. Cơ chế SMTP AUTH và OAuth2

Provider có thể yêu cầu:

- username/password SMTP riêng;
- OAuth2/XOAUTH2 token;
- quyền SMTP AUTH trên mailbox/tenant;
- network allowlist;
- chính sách sender identity/Send As.

Những lỗi này cần phân loại riêng khỏi TLS. `535 5.7.x` thường liên quan authentication, không thể sửa đúng bằng cách import CA bất kỳ.

Nếu app dùng OAuth token, nó phải có scope/audience/permissions hợp lệ và được refresh đúng cách. Không đưa access token vào log/debug trace hoặc thông số hiển thị công khai.

## 18. TLS debug trong Java

Khi cần quan sát handshake, Java có các debug system properties:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Và để xem certificate path building:

~~~text
-Djava.security.debug=certpath
~~~

Đây là lựa chọn chẩn đoán **tạm thời, có kiểm soát**, không phải logging mặc định lâu dài trên production.

### 18.1. Đọc gì trong debug?

- certificate chain do server trình bày;
- issuer, signature, validity và trust path;
- hostname/SNI;
- TLS protocol và cipher được negotiate;
- thời điểm handshake thất bại;
- có STARTTLS trước handshake chưa;
- sự khác nhau giữa truststore thực tế và kỳ vọng.

Tránh in raw SMTP AUTH exchange, token, body/attachment, OTP hoặc danh sách người nhận. Nếu cần protocol debug, dùng môi trường/case đã cô lập, thời gian bật ngắn và quyền xem log hạn chế.

### 18.2. Root cause thường nằm dưới lớp Spring exception

~~~text
MailSendException
  -> MailConnectException
      -> MessagingException
          -> SSLHandshakeException
              -> CertPathBuilderException
~~~

Đường exception thực tế tùy provider/phiên bản. Chỉ nhìn tên exception lớp ngoài sẽ dễ nhầm kết nối TCP với certificate validation. Cần tìm nested cause cuối cùng có ý nghĩa để phân loại lỗi.

## 19. Phân biệt SMTP TLS với SPF, DKIM, DMARC

| Cơ chế | Ý nghĩa |
| --- | --- |
| TLS Spring → SMTP provider | Bảo vệ và xác thực kết nối gửi |
| SMTP AUTH | Xác thực tài khoản được phép gửi |
| SPF | Cho phép kiểm tra server gửi theo domain policy |
| DKIM | Chữ ký trên thông tin email gắn với domain |
| DMARC | Chính sách kết hợp SPF/DKIM alignment |

SPF/DKIM/DMARC đúng không chứng minh certificate của SMTP endpoint được kiểm chứng; TLS đúng không tự đảm bảo thư vào Inbox hoặc có DKIM. Khi điều tra `PKIX`, tập trung vào transport TLS trước, không thay đổi DNS email authentication một cách không liên quan.

## 20. Kiểm thử TLS trong Spring Mail

### 20.1. Test SMTP cục bộ không mã hóa

Unit/integration test kiểm tra MIME rendering hoặc simple submission có thể dùng server loopback như GreenMail/Mailpit chạy plaintext **trong một môi trường test tách biệt**, không dùng credential/recipient thật. Test này không chứng minh TLS production.

~~~text
JUnit -> local SMTP test server (127.0.0.1)
      -> Assert subject, recipients, MIME parts
~~~

Không nên kết luận “TLS đã được kiểm thử” vì mail xuất hiện trong test mailbox.

### 20.2. Test TLS thật

Một test TLS phù hợp nên:

1. Tạo một test CA/PKI fixture được kiểm soát.
2. Cấp server certificate có SAN đúng hostname test.
3. Cấu hình SMTP test server hỗ trợ STARTTLS hoặc implicit TLS.
4. Cấu hình JVM test truststore tin **test CA**, không tin mọi certificate.
5. Kết nối qua hostname phù hợp SAN.
6. Xác minh certificate hợp lệ được chấp nhận.
7. Xác minh certificate sai hostname hoặc CA không tin bị từ chối.
8. Xác minh STARTTLS required ngăn tiếp tục plaintext.

### 20.3. Những trường hợp nên kiểm thử

| Kịch bản | Kỳ vọng |
| --- | --- |
| Server cert hợp lệ, CA tin và SAN khớp | Handshake thành công |
| Self-signed cert chưa được trust | Handshake thất bại |
| Certificate từ CA lạ | Bị từ chối |
| SAN chỉ có host A nhưng client kết nối host B | Bị từ chối |
| Certificate expired/not yet valid | Bị từ chối |
| Server không hỗ trợ STARTTLS khi required | Fail closed |
| 587 chạy nhầm implicit TLS | Fail đúng lỗi mode/protocol |
| 465 implicit TLS cấu hình đúng | Có thể handshake thành công |
| SMTP AUTH sai nhưng TLS đúng | Lỗi auth, không thay TLS policy |
| Provider rotate sang CA mới đã trust | Kết nối vẫn hợp lệ |

Spring Mail thường bọc lỗi transport trong các subclass của `MailException`. Test có thể xác minh nhóm lỗi và nested cause, không hardcode mọi TLS exception thành một kiểu cố định cho tất cả provider.

### 20.4. Test certificate của localhost

Nếu certificate chỉ có `DNS:smtp.test.internal` nhưng app kết nối tới `127.0.0.1`, việc hostname verification thất bại là đúng. Tạo certificate có IP SAN `127.0.0.1`, hoặc cấu hình test hostname/network alias phù hợp; không cần tắt verification.

### 20.5. Cleanup

Sau test:

- dừng server/container đúng owner;
- đóng tài nguyên do test quản lý;
- dọn mailbox, job/outbox và attachment thuộc fixture;
- xóa test truststore/cert files theo lifecycle;
- không để test song song dùng chung một port/truststore mutable;
- không purge toàn bộ SMTP server nếu test khác đang dùng.

## 21. Vận hành khi SMTP TLS bị lỗi trên production

Một lỗi chứng chỉ có thể làm hàng nghìn mail jobs kẹt trong outbox. Cách phản ứng đúng là **giữ dữ liệu và sửa transport trust**, không tắt verification.

~~~text
09:00 Certificate expired hoặc truststore sai.
09:01 SMTP worker gặp SSLHandshakeException.
09:05 Retry backlog bắt đầu tăng.
09:10 On-call nhận alert.

Điều nên làm:
  - Tạm ngừng retry dồn dập cho sender lỗi.
  - Giữ durable jobs.
  - Xác minh chain/hostname/TLS mode.
  - Sửa certificate/truststore/proxy.
  - Khôi phục sender với backoff và quan sát backlog.
~~~

### 21.1. Metric gợi ý

| Metric do ứng dụng tự instrument | Mục đích |
| --- | --- |
| `mail_submission_attempts_total` | Lưu lượng transport attempts |
| `mail_tls_handshake_failures_total` | Số lỗi handshake, phân theo error class |
| `mail_sender_healthy` | Health theo sender profile |
| `mail_outbox_pending` | Số jobs chưa hoàn tất |
| `mail_outbox_oldest_pending_age_seconds` | Độ già của backlog |
| `mail_retry_scheduled_total` | Retry và backoff |
| `mail_jobs_expired_total` | Những job hết hạn trong sự cố |

Các tên này là gợi ý triển khai, **không phải metrics mặc định của mọi Spring Mail application**. Nhãn nên là enum giới hạn như `sender_profile`, `error_class=pkix|hostname|protocol|auth`, `mail_type`; không dùng raw exception message, recipient, OTP hoặc password.

### 21.2. Failover có điều kiện

Nếu có sender dự phòng đã được cấu hình và kiểm thử:

~~~text
primary SMTP -> certificate problem
backup SMTP  -> valid TLS certificate + approved account
~~~

Có thể chuyển một phần traffic sang backup theo runbook, nhưng phải kiểm tra **quyền From/Send As, quotas, deliverability và idempotency**. Những attempt trước đó có kết quả `UNKNOWN` không nên bị gửi lại mù qua backup vì có thể provider primary đã nhận.

### 21.3. Mail đến hạn và expired tokens

Một OTP dự kiến gửi trong 30 giây có thể vô nghĩa nếu TLS outage kéo dài 20 phút. Khi phục hồi:

- đánh giá `expires_at`;
- không gửi OTP/token đã hết hạn;
- ghi trạng thái expired/suppressed theo policy;
- gửi lại thông báo khác khi business workflow thực sự yêu cầu, với intent mới;
- không tự xóa các pending jobs không có audit.

### 21.4. Không dùng circuit breaker để che lỗi

Circuit breaker có thể giảm retry storm khi một sender lỗi TLS liên tục, nhưng không giải quyết certificate validation. Sau khi hạ tầng được sửa, phải **kiểm chứng handshake với verification đầy đủ**, rồi mới mở traffic dần.

## 22. Quy trình certificate rotation

Để không biến sự cố định kỳ thành cấp cứu, tổ chức cần quản lý vòng đời TLS:

1. Lập inventory SMTP host/port/provider/sender profile.
2. Theo dõi Not After và lịch rotation của server/CA.
3. Kiểm tra chain và SAN của chứng chỉ sắp dùng.
4. Khi đổi CA, triển khai trust anchors mới trước server rotation nếu cần.
5. Dùng giai đoạn overlap CA cũ/mới theo policy.
6. Rotate server certificate/full chain.
7. Kiểm tra từ container/JVM đại diện ở mọi region.
8. Theo dõi TLS failure rate và submission backlog.
9. Thu hồi trust anchors cũ sau khi hoàn tất theo chính sách.
10. Ghi audit change, owner, rollback và kết quả verification.

Một CA rotation được quản trị tốt không cần bật trust-all trên client.

## 23. Những tình huống điển hình

### Tình huống A: Laptop gửi được, Docker báo PKIX

~~~text
Laptop:
  OS/JDK CA store mới -> SMTP OK.

Docker:
  JRE image cũ, thiếu CA -> PKIX error.
~~~

Hướng xử lý: kiểm tra JRE và truststore bên trong image, cập nhật CA đáng tin hoặc dùng image phù hợp, so sánh host/port/proxy, triển khai lại và xác minh hostname. Không sửa bằng `ssl.trust=*`.

### Tình huống B: Đổi hostname sang IP

~~~text
Trước:
  smtp.provider.example
  Certificate SAN = DNS:smtp.provider.example

Sau:
  10.10.10.8
  Certificate không có IP SAN tương ứng
  => Hostname verification failed
~~~

Sửa về hostname được công bố và DNS/network route hợp lệ. Không bỏ `checkserveridentity`.

### Tình huống C: Server thiếu intermediate

~~~text
Leaf cert do Intermediate CA ký.
SMTP server chỉ gửi leaf.
JVM container không dựng được chain.
~~~

Yêu cầu operator/provider sửa full chain, xác minh với trust anchor tin cậy. Đừng tự tin certificate leaf chưa xác minh chỉ vì lỗi biến mất.

### Tình huống D: Sai mode port 587

~~~text
spring.mail.port=587
mail.smtp.ssl.enable=true
Server đợi SMTP greeting + STARTTLS
=> Handshake failure/timeout
~~~

Sửa sang `starttls.enable=true` và `starttls.required=true` theo chính sách. Không phải tắt certificate validation.

### Tình huống E: TLS inspection trong doanh nghiệp

Certificate xuất hiện do corporate CA ký. Cần làm việc với đội PKI/security để xác minh endpoint, quyền interception và CA. Nếu policy cho phép, thêm CA đã xác minh vào đúng truststore. Nếu không, sửa route/bypass inspection được phê duyệt.

### Tình huống F: SMTP AUTH 535 sau khi TLS thành công

Đây không còn là vấn đề trust chain. Kiểm tra account, password/OAuth scope, SMTP AUTH settings và sender permission. Không thay đổi TLS settings để chữa một lỗi authentication.

## 24. Checklist xử lý lỗi chứng chỉ

### Host và giao thức

- [ ] Hostname trong `spring.mail.host` đúng endpoint provider.
- [ ] Đã kiểm tra DNS/CNAME/IP/SNI và route thực tế.
- [ ] Port 587 dùng STARTTLS nếu provider quy định.
- [ ] Port 465 dùng implicit TLS nếu provider quy định.
- [ ] STARTTLS bắt buộc có `mail.smtp.starttls.required=true`.
- [ ] Không fallback plaintext trái chính sách.

### Certificate validation

- [ ] `mail.smtp.ssl.checkserveridentity=true` được bật.
- [ ] Không đặt `mail.smtp.ssl.trust=*`.
- [ ] Không có custom trust-all manager/hostname verifier.
- [ ] Leaf certificate có SAN khớp host.
- [ ] Chain có intermediate và trust anchor hợp lệ.
- [ ] Certificate còn hiệu lực, system clock chính xác.
- [ ] CA nội bộ được xác minh độc lập trước khi import.
- [ ] Truststore thực của JVM/container được xác định đúng.

### Chẩn đoán

- [ ] Đã đọc root cause dưới `MailException`.
- [ ] Đã kiểm tra TCP trước khi suy luận TLS.
- [ ] Đã dùng OpenSSL đúng STARTTLS/implicit TLS mode.
- [ ] Đã kiểm tra hostname trong OpenSSL, không chỉ chain.
- [ ] Đã phân biệt PKIX, hostname, protocol, auth và network errors.
- [ ] Debug logs không lộ credentials/OTP/body.

### Vận hành

- [ ] Có người sở hữu certificate/CA rotation.
- [ ] Có monitoring certificate expiry và TLS handshake failures.
- [ ] Outbox vẫn giữ job khi TLS lỗi.
- [ ] Retry có backoff, tránh storm.
- [ ] Job expired/suppressed được xử lý đúng.
- [ ] Failover chỉ tới sender có TLS/authorization hợp lệ.
- [ ] Test bảo mật chứng minh certificate sai **bị từ chối**.

## 25. Những điều cần nhớ

- **Tắt TLS verification để né lỗi chứng chỉ là một anti-pattern nguy hiểm trong Spring Framework Mail.**
- TLS encryption không đủ nếu client không xác thực certificate chain và hostname.
- `mail.smtp.ssl.trust=*` và trust-all manager có thể che lỗi nhưng làm mất rào chắn xác thực server.
- `mail.smtp.ssl.checkserveridentity=true` giúp yêu cầu xác minh danh tính máy chủ; khi hostname mismatch, sửa host/SAN.
- Trên port **587**, thường dùng STARTTLS và đặt `starttls.required=true` nếu chính sách bắt buộc TLS.
- Trên port **465**, thường dùng implicit TLS với `mail.smtp.ssl.enable=true`.
- `PKIX path building failed` đòi hỏi điều tra CA chain, intermediate, truststore và proxy — không phải import bất kỳ certificate nào.
- JVM/container có thể dùng truststore khác máy local hoặc OpenSSL.
- Certificate expired, sai SNI/hostname, TLS protocol mismatch và SMTP AUTH failure là những lớp lỗi khác nhau.
- Internal CA phải được xác minh qua kênh đáng tin trước khi import; cần kế hoạch rotation và cảnh báo hết hạn.
- Một integration test TLS đúng phải từ chối certificate không tin cậy hoặc không khớp hostname.
- Khi lỗi xảy ra trên production, giữ durable mail jobs, backoff retries và sửa nguyên nhân; không giảm bảo mật chỉ để tăng số mail được gửi.

**Kết luận:** một lỗi chứng chỉ là tín hiệu cần **khôi phục mối quan hệ tin cậy với SMTP server**, không phải lời mời tắt xác thực. Trong Spring Mail, giải pháp bền vững là đúng host, đúng port/TLS mode, chain CA được xác minh, truststore phù hợp với JVM thật, hostname verification được bật và quy trình vận hành certificate rotation rõ ràng. Khi sửa đúng tầng, hệ thống vừa có thể gửi email trở lại, vừa bảo vệ credential và nội dung thư theo kỳ vọng bảo mật.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `JavaMailSenderImpl` và ngoại lệ gửi mail.
- **Spring Boot Reference — Sending Email:** `spring.mail.*`, JavaMail properties và timeout.
- **Jakarta Mail / Eclipse Angus Mail SSL Notes:** `mail.smtp.ssl.trust`, `mail.smtp.ssl.checkserveridentity`, `mail.smtp.starttls.enable` và `mail.smtp.starttls.required`.
- **Java JSSE Reference Guide:** TLS handshake, trust anchors, truststore, `javax.net.ssl.*` và debug.
- **Java keytool Documentation:** `-importcert`, `-list`, `-keystore` và quản lý CA.
- **RFC 3207 — SMTP Service Extension for Secure SMTP over Transport Layer Security:** STARTTLS.
- **RFC 8314 — Cleartext Considered Obsolete:** sử dụng TLS cho email submission/access.
- **RFC 9525 — Service Identity Verification:** xác minh danh tính dịch vụ trong certificate.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transport và submission responses.
- **OpenSSL s_client Documentation:** `-starttls smtp`, `-servername`, `-verify_hostname` và `-verify_return_error`.
- **Tài liệu SMTP provider và PKI nội bộ:** endpoint, port, TLS policy, certificate rotation và authentication.
