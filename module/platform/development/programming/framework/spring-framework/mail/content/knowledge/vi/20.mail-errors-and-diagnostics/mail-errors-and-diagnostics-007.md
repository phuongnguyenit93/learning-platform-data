# Lỗi TLS, chứng chỉ và handshake

Khi gửi email bằng **Spring Framework Mail**, một lời gọi `JavaMailSender.send(...)` có thể thất bại dù địa chỉ SMTP, tên đăng nhập và mật khẩu đều có vẻ đúng. Những thông báo như `SSLHandshakeException`, `PKIX path building failed`, `No subject alternative DNS name matching`, `Unsupported or unrecognized SSL message` hoặc `STARTTLS is required but host does not support STARTTLS` thường liên quan đến **cách thiết lập kênh TLS**, **xác thực chứng chỉ**, **phiên bản giao thức**, hoặc **đường kết nối đến SMTP relay**.

Đây không phải một nhóm lỗi nên sửa bằng cách tắt kiểm tra chứng chỉ. TLS giúp ứng dụng xác minh danh tính server SMTP và mã hóa lưu lượng trên đường kết nối đó. Nếu xử lý sai, ứng dụng có thể gửi thông tin đăng nhập và nội dung email tới endpoint không đáng tin cậy, chấp nhận chứng chỉ giả hoặc âm thầm hạ cấp xuống kết nối không mã hóa.

Bài học giải thích sự khác nhau giữa **STARTTLS** và **implicit TLS**, cách Jakarta Mail tương tác với Java JSSE/truststore, những nguyên nhân phổ biến của handshake failure, quy trình chẩn đoán có thể lặp lại, cấu hình Spring Boot an toàn và các tình huống kiểm thử thường gặp.

## 1. Đặt đúng vị trí của lỗi trong luồng gửi mail

Khi ứng dụng Spring Boot gửi mail qua SMTP, có nhiều giai đoạn trước khi người nhận thấy email:

```text
Spring service
     |
     v
JavaMailSender / MimeMessage
     |
     v
DNS / TCP connection
     |
     v
SMTP greeting / EHLO
     |
     +------------------------------+
     | STARTTLS mode                | Implicit TLS mode
     | EHLO -> STARTTLS -> TLS      | TLS ngay sau TCP connect
     +------------------------------+
     |
     v
TLS certificate validation / handshake
     |
     v
SMTP AUTH (nếu cần)
     |
     v
MAIL FROM -> RCPT TO -> DATA
     |
     v
SMTP server accepts submission
     |
     v
Provider delivery toward recipient
```

**Handshake lỗi ở đâu?** Nếu SSL/TLS handshake thất bại, kết nối bảo mật chưa sẵn sàng, vì vậy phiên gửi có thể dừng trước khi hoàn tất SMTP AUTH hoặc DATA. Những lỗi như “sai mật khẩu” hoặc “địa chỉ nhận không tồn tại” thuộc các bước khác và không nên bị gộp với lỗi chứng chỉ.

Một lời gọi `send(...)` thành công thường chỉ biểu thị SMTP server chấp nhận submission; nó **không chứng minh người nhận đã nhận thư vào Inbox hoặc mở email**. Bài học này tập trung vào **transport security của kết nối từ ứng dụng đến SMTP relay/provider**, không phải bảo mật end-to-end của nội dung trong mailbox.

### 1.1. Phân biệt ba lớp để khoanh vùng

| Lớp | Ví dụ lỗi | Cần kiểm tra |
|---|---|---|
| **Network / TCP** | Connection refused, DNS failure, timeout | Host, port, firewall, proxy, DNS, route. |
| **TLS / certificate** | SSLHandshakeException, PKIX, hostname mismatch | STARTTLS/implicit TLS, certificate chain, truststore, SNI, protocol/cipher. |
| **SMTP / authentication** | 535 Authentication failed, 550 recipient rejected | Username, app password/OAuth2, AUTH mechanism, relay policy, recipient. |

Một `MailSendException` của Spring có thể bọc exception sâu hơn. Cần tìm **root cause** trước khi chọn cách xử lý.

## 2. STARTTLS và implicit TLS: không được nhầm

Hai cách phổ biến để bảo vệ kết nối SMTP submission là:

1. **STARTTLS**: TCP ban đầu thiết lập kết nối SMTP chưa mã hóa, client gửi EHLO và lệnh STARTTLS để chuyển sang TLS trước khi AUTH/gửi nội dung.
2. **Implicit TLS** (thường được gọi SMTPS): TLS handshake bắt đầu ngay sau khi tạo kết nối TCP, trước lời chào SMTP nằm bên trong kênh mã hóa.

### 2.1. So sánh các cổng thông dụng

| Cổng | Cách dùng phổ biến | Cấu hình chính | Điều cần nhớ |
|---|---|---|---|
| **587** | Message submission với STARTTLS | `mail.smtp.starttls.enable=true` và thường `required=true` | Không bật implicit TLS cùng lúc nếu server yêu cầu STARTTLS. |
| **465** | Message submission qua implicit TLS | `mail.smtp.ssl.enable=true` | Kết nối bắt đầu bằng TLS ngay. |
| **25** | Chuyển tiếp giữa MTA hoặc relay nội bộ theo policy | Phụ thuộc hạ tầng | Không mặc định là cổng ứng dụng được phép submission; nhiều mạng chặn port 25. |

Port 587/465 là quy ước phổ biến, **không thay thế cấu hình chính thức của SMTP provider**. Một hệ thống nội bộ có thể dùng port khác. Chọn chính xác host, port và TLS mode mà đơn vị cung cấp SMTP công bố.

### 2.2. STARTTLS hoạt động ra sao?

Ví dụ luồng minh họa:

```text
Client                         SMTP server :587
  |-------- TCP connect ------------>|
  |<------- 220 greeting ------------|
  |-------- EHLO app.example -------->|
  |<------- 250-STARTTLS ------------|
  |-------- STARTTLS ---------------->|
  |<------- 220 Ready to start TLS --|
  |=========== TLS handshake ========|
  |    certificate validation        |
  |-------- EHLO app.example ------->|  (bên trong TLS)
  |<------- 250-AUTH ... ------------|
  |-------- AUTH ... ---------------->|
  |-------- MAIL FROM ... ----------->|
  |-------- RCPT TO ... ------------->|
  |-------- DATA ... ---------------->|
  |<------- 250 queued --------------|
```

Trước khi STARTTLS hoàn tất, không gửi username/password hoặc nội dung nhạy cảm. Để tránh gửi plaintext khi relay không hỗ trợ/nếu có downgrade, nên đặt `mail.smtp.starttls.required=true` cho provider được yêu cầu hỗ trợ STARTTLS.

Chỉ đặt `starttls.enable=true` có thể cho phép tiếp tục không TLS trong một số trường hợp nếu server không quảng cáo STARTTLS; `required=true` buộc kết nối phải sử dụng STARTTLS hoặc thất bại.

### 2.3. Implicit TLS hoạt động ra sao?

```text
Client                        SMTP server :465
  |-------- TCP connect ------------>|
  |=========== TLS handshake ========|
  |    certificate validation        |
  |<------- 220 greeting ------------|  (bên trong TLS)
  |-------- EHLO -------------------->|
  |-------- AUTH ... ---------------->|
  |-------- MAIL FROM ... ----------->|
  |-------- RCPT TO ... ------------->|
  |-------- DATA ... ---------------->|
```

Nếu client dùng implicit TLS trên port chỉ chờ SMTP greeting plaintext, hoặc chờ SMTP greeting plaintext trên port đang đợi TLS ClientHello, hai đầu sẽ không hiểu nhau. Điều đó có thể dẫn đến `Unsupported or unrecognized SSL message`, `wrong version number`, timeout hoặc connection reset.

## 3. Cấu hình Spring Boot đúng cho từng TLS mode

Spring Boot có thể tự cấu hình `JavaMailSender` khi ứng dụng có mail starter và thuộc tính SMTP thích hợp. Các ví dụ dưới đây dùng SMTP có xác thực bằng username/password; một số provider yêu cầu OAuth2 hoặc cơ chế AUTH khác.

### 3.1. Port 587: STARTTLS bắt buộc

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
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
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Giải thích:
- `auth=true`: sử dụng SMTP AUTH nếu provider yêu cầu.
- `starttls.enable=true`: yêu cầu nâng cấp kết nối bằng STARTTLS khi server hỗ trợ.
- `starttls.required=true`: không tiếp tục phiên nếu STARTTLS không có hoặc thất bại.
- `ssl.checkserveridentity=true`: yêu cầu kiểm tra hostname của chứng chỉ TLS.
- Các timeout hạn chế thời gian chờ kết nối, đọc và ghi, tính bằng mili giây theo property Jakarta Mail.

Không bật `mail.smtp.ssl.enable=true` cho ví dụ port 587 nếu provider chỉ hỗ trợ STARTTLS ở cổng này.

### 3.2. Port 465: implicit TLS

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

`ssl.enable=true` khiến SMTP transport của Jakarta Mail thiết lập TLS ngay khi kết nối. Không cần gửi lệnh STARTTLS trên cổng implicit TLS.

**Không cấu hình đồng thời cả hai mode theo thói quen**. Xác nhận mode được provider hỗ trợ rồi cấu hình đúng một cách bắt đầu TLS.

### 3.3. Thiết lập phiên bản TLS khi hạ tầng yêu cầu

Trong một số hệ thống, cần giới hạn protocol theo chính sách:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          ssl:
            protocols: TLSv1.2 TLSv1.3
```

Property `mail.smtp.ssl.protocols` là danh sách các tên protocol cách nhau bởi khoảng trắng và sẽ phụ thuộc khả năng thực tế của JDK/server. Không ép `TLSv1.3` khi server/JVM không hỗ trợ, và không hạ cấp sang TLS 1.0/1.1 chỉ để “cho chạy được”.

Các JDK mới có thể đã mặc định vô hiệu hóa nhiều thuật toán/cipher yếu. Nếu cần tương thích với relay cũ, ưu tiên nâng cấp relay hoặc dùng proxy SMTP bảo mật do tổ chức kiểm soát, không nới lỏng toàn bộ chính sách mã hóa của JVM một cách tùy tiện.

### 3.4. Chọn đúng host

`spring.mail.host` phải là tên mà provider công bố, ví dụ `smtp.example.com`. Tránh:
- kết nối trực tiếp tới IP nếu chứng chỉ chỉ có DNS name;
- dùng alias/CNAME nội bộ không được liệt kê trong certificate SAN;
- nhầm web host của provider với SMTP host;
- nhầm host relay nội bộ với host public;
- dùng một hostname nhưng bị DNS/router chuyển tới proxy TLS có chứng chỉ khác.

Tên server được dùng cho việc kiểm tra certificate identity và thường liên quan tới SNI; cấu hình sai host có thể gây handshake lỗi dù IP và port có thể kết nối được.

## 4. TLS handshake kiểm tra những gì?

TLS handshake không chỉ đơn giản là “bật mã hóa”. Client và server phải:
1. Thống nhất protocol version và cipher suite phù hợp.
2. Trao đổi dữ liệu để thiết lập khóa phiên.
3. Server cung cấp chứng chỉ cùng certificate chain khi cần.
4. Client xác nhận chứng chỉ được cấp bởi tổ chức phát hành được tin cậy.
5. Client kiểm tra chứng chỉ còn hiệu lực, phù hợp mục đích server authentication và tên host.
6. Hai bên hoàn tất các bước xác thực/cryptographic verification.

Một số triển khai còn sử dụng **mTLS**, nghĩa là server SMTP yêu cầu client cung cấp chứng chỉ. Điều này không phổ biến với mọi SMTP submission provider, nhưng có thể có ở relay doanh nghiệp.

### 4.1. Certificate chain

Ví dụ:

```text
Root CA (trusted by client)
  |
  v
Intermediate CA
  |
  v
Server certificate
  Subject Alternative Name: DNS:smtp.example.com
  Extended Key Usage: TLS Web Server Authentication (nếu có)
```

Server thường gửi certificate leaf và các intermediate cần thiết. Java truststore chứa những trust anchor mà JVM tin cậy. Nếu thiếu intermediate, thiếu CA phù hợp, chain sai hoặc certificate bị thu hồi theo chính sách kiểm tra đang áp dụng, việc xây dựng/kiểm tra chain có thể thất bại.

**Không nên chỉ chép certificate bất kỳ vào truststore cho đến khi hết lỗi.** Phải xác minh danh tính server, tổ chức phát hành, nguồn cung cấp chứng chỉ và chính sách CA của tổ chức.

### 4.2. Tên host và Subject Alternative Name

Giả sử client kết nối `smtp.example.com` nhưng chứng chỉ chỉ có:

```text
Subject Alternative Name:
  DNS:mail.other-example.net
```

Khi hostname verification được bật, server không chứng minh được danh tính `smtp.example.com` và kết nối phải thất bại.

Đừng tắt kiểm tra hostname. Thay vào đó:
- kết nối đúng hostname được provider hỗ trợ;
- cấu hình chứng chỉ mới với SAN thích hợp nếu bạn quản lý relay;
- sửa DNS/cấu hình proxy;
- tránh kết nối IP trực tiếp trừ khi cert có IP SAN và hạ tầng hỗ trợ.

Việc hai hostname cùng trỏ về một IP **không tự làm chứng chỉ hợp lệ cho cả hai hostname**.

### 4.3. Thời gian có ảnh hưởng đến certificate validity

Chứng chỉ có trường `notBefore` và `notAfter`. Nếu server/client lệch thời gian đáng kể hoặc chứng chỉ đã hết hạn, Java có thể báo `CertificateExpiredException` hoặc `CertificateNotYetValidException`.

Kiểm tra NTP/clock của host, VM/container và thời hạn chứng chỉ. Sửa thời gian hoặc thay chứng chỉ đúng cách; không sửa đồng hồ giả hoặc tắt kiểm tra thời hạn để vượt qua lỗi.

## 5. Truststore của Java và khác biệt với trình duyệt

Kết nối của Jakarta Mail thường dùng Java JSSE. Trust anchor được lấy từ **truststore mà JVM thực tế đang dùng**, không nhất thiết là kho chứng chỉ mà browser hoặc lệnh OpenSSL trên máy sử dụng.

Một tình huống phổ biến:
- Trình duyệt truy cập dịch vụ của provider không báo lỗi.
- `openssl s_client` trên laptop xác minh thành công.
- Ứng dụng Java trong container vẫn báo `PKIX path building failed`.

Có thể vì:
- Browser/OS dùng truststore khác JDK.
- JDK trong container có CA bundle cũ.
- JVM được cấu hình `javax.net.ssl.trustStore` trỏ tới file khác.
- Server gửi chain thiếu intermediate mà công cụ khác tự tìm/bù được.
- Proxy doanh nghiệp thay chứng chỉ bằng CA nội bộ chưa được JVM tin cậy.
- Container dùng khác JDK so với môi trường development.

**Luôn xác minh truststore và JDK của tiến trình ứng dụng đang chạy**, không chỉ của máy phát triển.

### 5.1. Truststore mặc định

Java thường dùng tập CA được đóng gói trong các truststore như `cacerts`, nhưng chi tiết phụ thuộc bản phân phối JDK, cấu hình security và các system property.

Các thuộc tính JSSE thường gặp:

```text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

Nếu có cấu hình `trustStore` tùy biến, hãy xác nhận file tồn tại, loại keystore đúng và có trust anchor phù hợp. Một đường dẫn không tồn tại hoặc mật khẩu sai có thể khiến kết nối thất bại khác với nguyên nhân ban đầu.

### 5.2. Tạo dedicated truststore cho CA nội bộ

Nếu tổ chức dùng SMTP relay với certificate do **CA nội bộ được phê duyệt** ký, có thể tạo truststore riêng:

```bash
keytool -importcert \
  -alias approved-mail-root-ca \
  -file /secure/certs/approved-mail-root-ca.pem \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Sau đó xác nhận nội dung bằng:

```bash
keytool -list \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Lệnh có thể hỏi mật khẩu tương tác. **Chỉ import CA/certificate đã được bộ phận quản lý hạ tầng hoặc PKI xác minh**; không import leaf certificate không rõ nguồn chỉ vì hệ thống đang lỗi.

Khi triển khai JVM, có thể cấu hình:

```text
-Djavax.net.ssl.trustStore=/secure/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Truststore password phải được cung cấp qua cơ chế secret/launch configuration được kiểm soát. Tránh đưa mật khẩu plaintext vào script hoặc command line có thể bị người khác xem. Lưu ý các thuộc tính JSSE này có thể ảnh hưởng **nhiều kết nối TLS trong cùng JVM**, không riêng Spring Mail. Với ứng dụng phức tạp, nên cân nhắc cách cấu hình SSLContext/transport riêng phù hợp chính sách nội bộ.

Một truststore riêng chỉ chứa CA nội bộ cũng có thể làm mất các public CA cần cho những kết nối khác trong JVM. Phải đánh giá trust anchors đầy đủ thay vì thay thế `cacerts` một cách vô ý.

### 5.3. Những “cách sửa” không an toàn

Không nên áp dụng trong production:
- `mail.smtp.ssl.trust=*` để tin mọi server.
- Custom `TrustManager` chấp nhận mọi chứng chỉ.
- Tắt `mail.smtp.ssl.checkserveridentity` nhằm tránh hostname mismatch.
- Bỏ `starttls.required` để fallback sang plaintext sau lỗi.
- Buộc TLS 1.0/1.1 hoặc bật cipher yếu không có đánh giá bảo mật.
- Cài một chứng chỉ không được xác minh nguồn gốc vào truststore.
- Ghi mật khẩu, certificate private key hoặc toàn bộ SMTP debug log ra log tập trung.

Một số lựa chọn có thể làm thử kết nối thành công nhưng đồng thời **loại bỏ chính bảo đảm an toàn mà TLS được thiết kế để cung cấp**.

## 6. Các lỗi TLS và certificate thường gặp

Đọc chuỗi lỗi từ exception ngoài vào **root cause**. Cùng một `MailSendException` có thể do nhiều nguyên nhân.

| Thông báo / exception | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | JVM không xây được trust chain từ server tới CA tin cậy | Certificate chain, intermediate, JVM truststore, proxy MITM hợp pháp. |
| `SSLHandshakeException: No subject alternative DNS name matching ...` | Host đang kết nối không khớp SAN trên cert | Hostname, IP/CNAME, certificate SAN, proxy endpoint. |
| `CertificateExpiredException` | Cert hết hạn | Thời hạn leaf/intermediate, quy trình renewal. |
| `CertificateNotYetValidException` | Cert chưa tới ngày hiệu lực hoặc đồng hồ lệch | NTP/timezone hệ thống và validity. |
| `Received fatal alert: handshake_failure` | Hai bên không thống nhất cipher/protocol hoặc chính sách chứng chỉ | TLS versions/cipher, mTLS, server logs, JDK. |
| `Received fatal alert: protocol_version` | Một bên không hỗ trợ protocol version được đề xuất | JVM/relay TLS configuration. |
| `no cipher suites in common` | Cipher suites không có tập chung | JDK disabled algorithms, server policy. |
| `Unsupported or unrecognized SSL message` | Client mong TLS nhưng server đang nói plaintext | Port và TLS mode, proxy/gateway. |
| `wrong version number` | Thường là nhầm implicit TLS và plaintext endpoint | Port, STARTTLS vs SSL enable, TLS terminator. |
| `Connection reset` / `EOFException` giữa handshake | Server/proxy đóng kết nối, protocol mismatch, policy hạ tầng | Network path, server logs, SNI, thời gian chờ. |
| `STARTTLS is required but host does not support STARTTLS` | Server không quảng cáo hoặc không thực hiện STARTTLS | EHLO capabilities, host/port, proxy stripping. |
| `530 Must issue a STARTTLS command first` | Client cố AUTH/MAIL trước khi nâng cấp TLS theo yêu cầu server | `starttls.enable`, `required`, port. |
| `handshake timed out` / `SocketTimeoutException` | Relay/network chậm, proxy treo hoặc handshake không hoàn tất | Network, timeout, server load và logs. |
| `bad_certificate` / `certificate_required` | Server yêu cầu hoặc từ chối client cert trong mTLS | Client key/cert, trust of client CA, relay policy. |
| `MailAuthenticationException` sau khi TLS thành công | Sai credential hoặc AUTH mechanism, không nhất thiết lỗi handshake | Auth provider, app password/OAuth2, server response. |

Đây là những **gợi ý khoanh vùng**, không phải quy tắc kết luận tự động. Cùng thông báo có thể phát sinh ở nhiều cấu hình. Cần đọc nguyên nhân lồng nhau, thời điểm lỗi và log từ cả hai phía.

### 6.1. PKIX path building failed

Một stack trace minh họa:

```text
org.springframework.mail.MailSendException: Mail server connection failed
Caused by: jakarta.mail.MessagingException: Could not convert socket to TLS
Caused by: javax.net.ssl.SSLHandshakeException:
    PKIX path building failed
Caused by: sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

Diễn giải: Java nhận chứng chỉ trong quá trình handshake nhưng không thể xây dựng đường tin cậy hợp lệ.

Cần kiểm tra:
1. Server có gửi đủ intermediate certificates?
2. Root/intermediate CA có được tin bởi JVM chạy app?
3. Java container có truststore khác môi trường phát triển?
4. Có TLS inspection proxy đang thay cert?
5. Chứng chỉ có bị cấp sai hoặc hết hạn?
6. App có đang kết nối đúng SMTP host không?

Không kết luận ngay “Java thiếu chứng chỉ” rồi import vô điều kiện. Nếu gặp endpoint giả mạo, việc tin chứng chỉ sai còn nguy hiểm hơn lỗi ban đầu.

### 6.2. Hostname mismatch

Ví dụ:

```text
No subject alternative DNS name matching smtp.example.com found
```

Vấn đề không phải độ tin cậy của CA, mà là **tên server không nằm trong danh tính mà cert chứng minh**.

Hướng xử lý hợp lệ:
- dùng hostname được cert hỗ trợ;
- yêu cầu provider cập nhật cert;
- sửa endpoint, SNI hoặc DNS;
- cấp lại cert SAN đúng cho relay tổ chức.

Không tắt hostname check. Import CA vào truststore cũng **không sửa được** một SAN mismatch.

### 6.3. Handshake failure vì protocol/cipher

Nếu server chỉ hỗ trợ TLS phiên bản cũ đã bị JDK vô hiệu hóa, client có thể báo `handshake_failure` hoặc `protocol_version`.

Kiểm tra:
- Phiên bản JDK và chính sách `jdk.tls.disabledAlgorithms`.
- Phiên bản TLS server hỗ trợ.
- Server có đúng endpoint SMTP hay không.
- Cấu hình `mail.smtp.ssl.protocols` hoặc cipher suites tùy biến.
- mTLS có đang được bật ở relay mà client chưa cấu hình cert.

Ưu tiên nâng cấp relay/server hoặc dùng cổng/provider hiện đại. Không nên “sửa” bằng cách vô hiệu hóa hệ thống bảo vệ của JDK mà không có quy trình bảo mật.

## 7. Quy trình chẩn đoán theo thứ tự

Một cách tiếp cận giảm thao tác thừa:

```text
1. Xác nhận host + port + TLS mode
                 |
                 v
2. DNS / TCP có kết nối?
                 |
                 v
3. SMTP banner / EHLO / STARTTLS capability
                 |
                 v
4. TLS handshake và certificate chain
                 |
                 v
5. SAN hostname + validity + truststore Java
                 |
                 v
6. SMTP AUTH
                 |
                 v
7. MAIL FROM / RCPT TO / DATA
                 |
                 v
8. SMTP accepted / provider delivery status
```

### Bước 1 — Chốt thông tin provider

Ghi lại:
- Hostname chính thức.
- Port.
- STARTTLS hay implicit TLS.
- Có bắt buộc authentication không.
- TLS minimum version hoặc CA riêng không.
- Có proxy/gateway/VPN/egress relay trung gian không.
- Runtime Java/JDK đang chạy trên máy nào.

Không đoán từ hostname hoặc từ một cấu hình cũ.

### Bước 2 — Kiểm tra DNS và TCP

Có thể dùng công cụ phù hợp môi trường:

```powershell
Resolve-DnsName smtp.example.com
Test-NetConnection smtp.example.com -Port 587
```

Trên Linux, dùng các công cụ tương đương như `getent hosts`, `nc` hoặc kiểm tra TCP network policy. TCP kết nối thành công chỉ chứng minh host/port có thể tới được; **không chứng minh TLS hoặc chứng chỉ hợp lệ**.

Nếu timeout/connection refused ngay từ TCP, kiểm tra firewall, security group, proxy, Kubernetes NetworkPolicy, NAT egress, port blocking của nhà mạng và trạng thái provider trước khi điều tra truststore.

### Bước 3 — Kiểm tra STARTTLS support và certificate từ đúng môi trường

Với port 587:

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -showcerts
```

Với implicit TLS port 465:

```bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -showcerts
```

Đây là các lệnh chẩn đoán, không gửi email. Nên chạy từ **cùng mạng/container/host** mà ứng dụng sử dụng nếu có thể; laptop cá nhân có thể đi đường mạng khác.

Cách đọc:
- `Certificate chain`: các cert server gửi.
- `subject`, `issuer`: danh tính và CA cấp.
- `notBefore`, `notAfter`: thời hạn cert.
- `Verify return code`: kết quả xác minh theo truststore của OpenSSL.
- `Protocol` và `Cipher`: phiên bản TLS/cipher đã thương lượng.
- Lỗi handshake trước khi thấy certificate có thể chỉ ra TLS mode, protocol hoặc network policy.

Lưu ý:
- `-servername` cung cấp SNI; `-verify_hostname` kiểm tra hostname nếu phiên bản OpenSSL hỗ trợ.
- OpenSSL có truststore riêng, nên xác minh thành công **không bảo đảm Java cũng tin chain**.
- Không nhập SMTP credential vào công cụ chẩn đoán hoặc chụp log có secret.
- Nếu công cụ OpenSSL không có sẵn trên hệ điều hành, dùng môi trường chẩn đoán được tổ chức phê duyệt; không tự cài công cụ không rõ nguồn.

### Bước 4 — So sánh chứng chỉ với tên host thực tế

Đối chiếu certificate SAN với đúng giá trị `spring.mail.host`, kể cả khi kết nối qua alias/proxy. Nếu kết nối tới IP nhưng certificate chỉ có DNS name, đổi sang hostname hợp lệ. Nếu DNS trả về nhiều endpoint, kiểm tra việc đồng nhất cert giữa các node/load balancer.

### Bước 5 — Đối chiếu truststore của tiến trình Java

Kiểm tra:
- JDK vendor/version trong runtime container/VM.
- JVM startup properties.
- File truststore được gắn vào container có tồn tại.
- Quyền đọc file của user chạy ứng dụng.
- Password/type có hợp lệ.
- Trust anchors có khớp CA được phê duyệt.
- Certificate chain có được server gửi đầy đủ.

Không chỉ nhìn truststore của laptop nếu ứng dụng chạy trong pod khác.

### Bước 6 — Chỉ sau TLS mới kiểm tra SMTP AUTH và gửi

Nếu TLS thành công nhưng lỗi xảy ra ở AUTH, xem:
- Username/secret.
- App password hoặc OAuth2 requirement.
- Provider có cho Basic Auth không.
- Account có được phép SMTP submission.
- Policy From/recipient hoặc IP allowlist.

Không lẫn lỗi `535 Authentication failed` với chứng chỉ. Thêm CA vào JVM sẽ không sửa mật khẩu sai.

## 8. Log chẩn đoán TLS và Spring Mail

### 8.1. Bật JavaMail debug có kiểm soát

Trong môi trường chẩn đoán được cô lập, có thể bật:

```yaml
spring:
  mail:
    properties:
      mail:
        debug: true
```

Debug của Jakarta Mail có thể hiện quá trình kết nối, EHLO/STARTTLS/AUTH capability và SMTP response. Tuy nhiên, **không bật mặc định ở production**, vì log có thể tiết lộ metadata hệ thống, địa chỉ email, cơ chế xác thực và tùy cấu hình có thể có dữ liệu nhạy cảm.

Không gửi nguyên debug log ra ticket công khai; cần loại bỏ host nội bộ, email, token, secret hoặc nội dung nhạy cảm.

### 8.2. Bật JSSE debug trong JVM khi cần

Ví dụ flags chẩn đoán:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

Những cờ này giúp thấy phiên bản TLS được thương lượng, luồng certificate validation và quyết định trust. Chúng có thể tạo rất nhiều log, nên chỉ bật tạm thời trong môi trường có quyền truy cập hạn chế và tắt sau khi khoanh vùng.

Điều cần quan sát:
- Client đang gửi handshake tới đúng host/port không?
- Có chứng chỉ server nào được nhận?
- Chain nào được tin hoặc từ chối?
- Protocol/cipher được chọn?
- Có fatal alert nào từ client/server?
- Handshake thất bại trước hay sau certificate verification?

### 8.3. Lấy root cause từ Spring exception

Một ví dụ ghi log phân loại **không in thông điệp có thể nhạy cảm**:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;

public class MailErrorLogger {

    private static final Logger log =
        LoggerFactory.getLogger(MailErrorLogger.class);

    public void logFailure(String messageKey, MailException ex) {
        Throwable root = ex;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }

        log.warn(
            "smtp_submission_failed messageKey={} exceptionType={} rootType={}",
            messageKey,
            ex.getClass().getSimpleName(),
            root.getClass().getSimpleName()
        );
    }
}
```

Đây là ví dụ logging tối thiểu. Trong môi trường chẩn đoán hạn chế có thể cần stack trace với quyền truy cập phù hợp; không log credential, nội dung MIME hay toàn bộ exception detail không kiểm soát.

Với `MailSendException`, thông tin failed messages hoặc nested exceptions có thể hữu ích khi gửi nhiều thông điệp. Cần phân tích theo từng message/recipient, tránh kết luận tất cả đều thất bại nếu provider đã chấp nhận một phần.

## 9. Ví dụ cấu hình JavaMailSenderImpl không dùng Boot auto-config

Nếu ứng dụng Spring Framework không sử dụng Spring Boot autoconfiguration, có thể cấu hình sender rõ ràng:

```java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

Đây là ví dụ cho STARTTLS port 587. Khi dùng port 465 implicit TLS, thay đổi theo provider và sử dụng `mail.smtp.ssl.enable=true` thay cho STARTTLS mode.

**Không hardcode password.** Trong triển khai thật, inject từ secret manager/environment configuration và cần có quy trình rotation. Hãy bảo vệ giá trị environment/secret và không dump biến môi trường vào log.

### 9.1. Ví dụ gửi MIME message và xử lý lỗi

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SecureNoticeMailService {

    private final JavaMailSender mailSender;

    public SecureNoticeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(
            String recipient,
            String subject,
            String plainText,
            String htmlText) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        // MailException là runtime exception khi submission thất bại.
        // Không retry mọi MailException ngay trong HTTP request.
        mailSender.send(message);
    }
}
```

Khi lỗi TLS xảy ra, exception có thể được bọc trong `MailException` của Spring hoặc `MessagingException`/`SSLHandshakeException` ở các tầng bên dưới. Hãy để một service/worker riêng ghi nhận trạng thái và áp dụng chính sách retry theo nguyên nhân, thay vì bắt exception rồi tự gửi lặp vô hạn.

## 10. Những tình huống thực tế và cách xử lý

### 10.1. Port 587 nhưng bật implicit TLS

Cấu hình sai:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          ssl:
            enable: true
```

Nếu server ở cổng này chờ SMTP plaintext trước lệnh STARTTLS, client lại gửi TLS ClientHello ngay. Kết quả có thể là timeout hoặc protocol error.

Cách sửa: dùng `starttls.enable=true` và `starttls.required=true`, không dùng `ssl.enable=true` cho endpoint chỉ hỗ trợ STARTTLS.

### 10.2. Port 465 nhưng chỉ bật STARTTLS

Nếu server yêu cầu TLS ngay từ byte đầu tiên, client đang chờ SMTP greeting trước khi gửi STARTTLS. Hai phía chờ nhau hoặc đóng kết nối.

Cách sửa: chuyển sang `mail.smtp.ssl.enable=true` theo cấu hình implicit TLS của provider.

### 10.3. Chứng chỉ hợp lệ trên laptop nhưng lỗi trong Docker/Kubernetes

Nguyên nhân có thể:
- Image JDK chứa truststore/CA bundle khác.
- Mount truststore sai đường dẫn hoặc thiếu quyền đọc.
- Container không đồng bộ thời gian.
- Pod egress qua proxy TLS inspection khác.
- Truststore override bỏ mất CA public.
- Node/load balancer trả cert không đồng nhất.

Cách xử lý:
1. Xác nhận image JDK và giá trị JVM options của container đang chạy.
2. Kiểm tra network/DNS tới SMTP host từ đúng pod/host.
3. So sánh server cert/chain từ đường egress đó.
4. Xác nhận cấu hình truststore của tiến trình Java.
5. Khắc phục CA, intermediate hoặc proxy đúng nguồn, không thay bằng trust-all.

### 10.4. Chứng chỉ mới sau rotation gây lỗi

Một số relay đổi CA/intermediate khi gia hạn. Nếu truststore nội bộ pin riêng một leaf cert hoặc quá cũ, rotation có thể làm handshake thất bại.

Nên:
- theo dõi expiry và chain của relay;
- lên kế hoạch CA rollover;
- trust đúng CA được phê duyệt thay vì pin leaf tùy tiện;
- deploy/test trước khi chuyển certificate production;
- tránh để môi trường dev/staging dùng CA khác mà không nhận ra.

### 10.5. Proxy hoặc thiết bị kiểm tra TLS

Một doanh nghiệp có thể đặt proxy/SMTP gateway thay chứng chỉ. JVM sẽ thấy cert do CA nội bộ ký, khác với cert public của provider.

Đừng vội import cert đang thấy qua một kết nối không xác minh. Cần hỏi đội hạ tầng:
- Endpoint SMTP chính thức và đường đi egress?
- Proxy có TLS inspection hợp lệ cho kết nối này không?
- CA nội bộ nào được phê duyệt?
- Có hỗ trợ SNI và STARTTLS passthrough không?

Sau đó cấu hình trust anchors theo chính sách bảo mật.

### 10.6. STARTTLS biến mất khỏi EHLO

Nếu provider tài liệu nói hỗ trợ STARTTLS nhưng server không quảng cáo capability:
- Có thể đang dùng sai port/host.
- Relay trung gian có thể chặn hoặc thay đổi EHLO response.
- STARTTLS bị tắt trên node/backend.
- Network device có lỗi hoặc đang can thiệp.
- Một đường kết nối đã bị chuyển tới endpoint khác.

Nếu `starttls.required=true`, kết nối nên từ chối thay vì gửi credentials qua plaintext. Đây là hành vi bảo vệ cần giữ.

### 10.7. Handshake ổn nhưng Authentication failed

Sau khi sửa TLS, ứng dụng có thể đi tiếp và nhận `535 Authentication failed`. Đây là giai đoạn mới; không chứng minh việc sửa TLS sai.

Kiểm tra chính sách provider về app password/OAuth2, account SMTP AUTH, username, quyền gửi và giới hạn đăng nhập. Không tắt TLS vì muốn sửa AUTH.

### 10.8. Nhiều địa chỉ DNS, chỉ một node có cert sai

Với SMTP host trỏ tới nhiều IP hoặc load balancer, một node có thể thiếu intermediate hoặc dùng cert hết hạn. Biểu hiện là lỗi không ổn định, chỉ xuất hiện ở một số request/pod.

Hãy ghi lại thời gian, resolved address và đường kết nối theo khả năng của hạ tầng, sau đó yêu cầu provider/đội vận hành sửa cấu hình nhất quán trên các node. Không chuyển sang trust-all chỉ vì lỗi “lúc được lúc không”.

## 11. Retry khi lỗi TLS: khi nào có ích?

Không phải mọi lỗi gửi đều nên retry. Việc thử lại không thay đổi một chứng chỉ sai danh tính hoặc một truststore thiếu CA.

| Nhóm lỗi | Retry ngay? | Hành động phù hợp |
|---|---|---|
| Cert hết hạn | Không | Thay/gia hạn certificate hoặc sửa đường đi tới endpoint đúng. |
| Hostname mismatch | Không | Sửa hostname/certificate SAN. |
| PKIX do thiếu CA/intermediate | Không retry mù | Sửa chain/truststore sau khi xác minh nguồn. |
| Protocol/cipher không tương thích | Không | Sửa chính sách TLS/relay/JDK có kiểm soát. |
| Sai STARTTLS vs implicit TLS | Không | Sửa cấu hình host/port/mode. |
| TCP reset hoặc timeout tạm thời | Có thể | Retry có backoff/jitter, giới hạn attempt; vẫn cần điều tra nếu kéo dài. |
| Relay quá tải/không phản hồi | Có thể | Retry theo policy provider, rate limit/circuit breaker. |
| SMTP AUTH sai | Thường không | Sửa credential/auth mechanism. |
| Lỗi không rõ sau khi gửi DATA | Không retry ngay | Ghi `UNKNOWN` và reconcile để giảm gửi trùng. |

TLS handshake thường xảy ra **trước SMTP DATA**, nên nếu chứng minh chắc chắn handshake chưa thành công và chưa có submission, retry kết nối sau lỗi network transient ít rủi ro gửi trùng hơn. Tuy nhiên, một exception bọc chung từ `send(...)` không đủ để chứng minh bước nào đã hoàn tất. Cần log và trạng thái theo attempt.

Trong hệ thống queue/outbox, lưu `messageKey`, `attemptId`, root cause category và next retry time. Tránh lặp mọi exception với `@Retryable` mà không có giới hạn hoặc theo dõi kết quả.

## 12. Test và phòng ngừa lỗi TLS

### 12.1. Các môi trường nên được thử

- **Local**: kết nối SMTP sandbox với TLS hợp lệ.
- **CI/test integration**: dùng SMTP test server/certificate test được kiểm soát.
- **Staging**: thử đúng hostname/port/TLS mode và đường mạng gần production.
- **Production smoke check**: xác thực connection/handshake theo runbook và quyền cho phép, không phát tán email thật khi chỉ cần kiểm tra connect.

Có thể sử dụng `JavaMailSenderImpl.testConnection()` để kiểm tra khả năng kết nối của sender trong môi trường thích hợp:

```java
JavaMailSenderImpl sender = ...;
sender.testConnection();
```

Hàm này giúp phát hiện một số lỗi network/TLS/AUTH trong giai đoạn kết nối nhưng **không thay thế integration test gửi thật**, không xác nhận body/attachment hay khả năng delivery của mail server đích.

Spring Boot còn có thể có property kiểm tra kết nối lúc startup như `spring.mail.test-connection=true` tùy phiên bản và cấu hình; bật nó có thể làm ứng dụng không khởi động khi SMTP bị gián đoạn. Chỉ dùng khi đó là hành vi khởi động mong muốn, không mặc định bật cho mọi hệ thống.

### 12.2. Các ca kiểm thử nên có

| Test case | Kỳ vọng |
|---|---|
| STARTTLS port 587 được cấu hình đúng | Kết nối TLS thành công và có thể gửi test message tới sandbox. |
| Implicit TLS port 465 đúng | Kết nối TLS thành công ngay sau TCP. |
| Nhầm mode giữa 587 và 465 | Thất bại; ghi category cấu hình/TLS, không fallback plaintext. |
| Certificate CA không tin cậy | Handshake thất bại, không gửi credentials/body. |
| Hostname không nằm trong SAN | Handshake bị từ chối khi hostname check bật. |
| Certificate hết hạn | Kết nối bị từ chối và được cảnh báo. |
| Server thiếu intermediate | Kiểm tra chain/PKIX failure tương ứng. |
| TLS version/cipher không có tập chung | Handshake thất bại với log có thể khoanh vùng. |
| STARTTLS không được quảng cáo | `required=true` từ chối kết nối. |
| SMTP AUTH sai sau TLS hợp lệ | Báo lỗi authentication riêng, không gọi là PKIX. |
| Network timeout | Bounded retry theo policy và ghi attempt. |
| Provider cert rotation | Hệ thống tin CA mới theo kế hoạch, không cần trust-all. |

Test phải chạy với test server hoặc provider sandbox được phép. Không dùng tài khoản/mật khẩu thật trong source test và không chuyển thư thử tới người nhận thật ngoài ý muốn.

### 12.3. Không giả lập thành công bằng cách tắt validation

Một unit test dùng mock sender có thể xác nhận service gọi `send(...)`, nhưng **không chứng minh cấu hình TLS đúng**. Integration test cần SSL validation thật theo truststore kiểm soát và hostname có SAN phù hợp.

Không nên cấu hình `trustAll` trong test rồi suy ra production sẽ an toàn. Nếu cần CA test, tạo CA test riêng và nhập vào truststore chỉ dùng cho test.

## 13. Vận hành, giám sát và phòng lỗi tái diễn

Có thể theo dõi:
- TLS handshake failure rate theo SMTP host/port.
- Số lỗi PKIX/hostname/expired certificate.
- Tỷ lệ connection timeout và AUTH failure.
- Thời gian bắt đầu kết nối tới SMTP accepted.
- SMTP provider status và quota/rate limit.
- Certificate expiry và kế hoạch renewal.
- Khác biệt JDK/truststore giữa các môi trường.
- Số outbox item đang chờ và số retry.
- Số incident chỉ xảy ra trên một node/egress route.

Không log:
- SMTP username/password.
- OAuth2 access token hoặc app password.
- Toàn bộ MIME body, attachment, Base64.
- Full raw SMTP AUTH exchange.
- Private key, keystore password.
- URL có token.

Với mỗi lỗi, lưu **message key/correlation ID**, host alias được phép, TLS mode, error category và thời điểm. Việc này cho phép truy nguyên nhưng không cần lưu nội dung email của người nhận.

### 13.1. Runbook xử lý sự cố

Khi tỷ lệ gửi mail lỗi tăng đột ngột:

1. Tách lỗi network/TCP, TLS/certificate và SMTP AUTH.
2. Kiểm tra có thay đổi gần đây ở provider, certificate, DNS, network hoặc JDK image không.
3. Xác nhận host, port và TLS mode đang triển khai.
4. Chạy chẩn đoán TLS từ môi trường egress tương đương.
5. Kiểm tra leaf/intermediate/SAN/validity và truststore của JVM.
6. Nếu có lỗi CA, xác minh CA/chứng chỉ với đội PKI trước khi import.
7. Khôi phục cấu hình đúng, không vô hiệu hóa TLS verification.
8. Thử lại kết nối/test email theo quy trình được phép.
9. Cho worker xử lý backlog với rate limit/backoff; tránh burst và gửi trùng.
10. Ghi nhận root cause và cập nhật giám sát/rotation để ngăn tái diễn.

### 13.2. Sau khi khắc phục

Nếu trong thời gian lỗi handshake, worker đã giữ job ở `RETRY_WAIT`, có thể tiếp tục xử lý sau khi sửa cấu hình. Nếu lỗi là `UNKNOWN` ở giai đoạn submission, phải reconcile trước khi resubmit để tránh duplicate.

Đừng xóa outbox hoặc reset attempt count không kiểm soát nhằm “gửi lại tất cả”. Cần biết message nào chưa được SMTP accepted, message nào đã được provider giữ, message nào đã hard bounce.

## 14. Những ngộ nhận thường gặp

### “Port 587 luôn là SSL ngay khi connect”

Không. Port 587 thường dùng STARTTLS: SMTP greeting và EHLO xảy ra trước TLS. Implicit TLS thường dùng port 465.

### “Đặt starttls.enable=true là đủ để bắt buộc mã hóa”

Không nhất thiết. Với provider cần STARTTLS, nên đặt thêm `starttls.required=true` để không fallback nếu server không cung cấp STARTTLS.

### “PKIX path building failed nghĩa là chứng chỉ chắc chắn giả”

Không. Có thể do thiếu intermediate hoặc truststore Java thiếu CA. Tuy nhiên, phải xác minh chain/nguồn chứng chỉ trước khi thêm trust.

### “Chỉ cần import leaf certificate là giải quyết lâu dài”

Không chắc. Leaf rotation có thể làm lỗi trở lại và import certificate không tin cậy có thể nguy hiểm. Ưu tiên chain/CA đúng và quy trình PKI được phê duyệt.

### “Bật ssl.trust=* là cách sửa chuẩn”

Không. Tin mọi host bỏ qua một phần xác thực danh tính server. Đây là cách làm không phù hợp cho production.

### “OpenSSL verify OK thì Java chắc chắn verify OK”

Không. OpenSSL và Java có thể dùng truststore, protocol và chính sách certificate khác nhau.

### “SMTP AUTH lỗi tức là TLS lỗi”

Không. AUTH thường xảy ra sau khi TLS đã thiết lập. Phân loại theo response và root cause.

### “TLS bảo vệ email end-to-end”

Không. TLS giữa app và SMTP relay chỉ bảo vệ chặng truyền đó. Email có thể đi qua nhiều relay; nội dung có thể được lưu và xử lý bởi provider/recipient. Với bảo mật end-to-end cần cơ chế riêng như S/MIME/OpenPGP theo nhu cầu.

### “Đọc mỗi dòng MailSendException là đủ”

Không. Cần xem nested `MessagingException`, `SSLHandshakeException`, nguyên nhân trust validation và cả log phía server nếu có.

## 15. Bài tập thực hành

### Bài 1 — Phân biệt TLS mode

Viết hai cấu hình `application.yml` cho cùng provider: port 587 STARTTLS bắt buộc và port 465 implicit TLS. Giải thích vì sao không được hoán đổi hai cấu hình chỉ bằng cách đổi port.

### Bài 2 — Phân loại lỗi

Cho các log có `PKIX path building failed`, `No subject alternative DNS name matching`, `handshake_failure` và `535 Authentication failed`. Hãy xác định lớp lỗi và bước chẩn đoán đầu tiên cho từng loại.

### Bài 3 — Kiểm tra chứng chỉ bằng OpenSSL

Trong môi trường sandbox được phép, chạy `openssl s_client` ở STARTTLS và implicit TLS. Ghi nhận certificate chain, SAN, validity, protocol và cipher; so sánh với SMTP host của ứng dụng.

### Bài 4 — Truststore CA nội bộ

Với CA test được cấp phép, tạo truststore PKCS12 bằng `keytool` và cấu hình JVM dùng truststore đó. Giải thích khác biệt giữa tin CA đúng và tin mọi chứng chỉ.

### Bài 5 — Kiểm tra hostname

Dùng test SMTP server với certificate có SAN khác hostname kết nối. Xác nhận handshake bị từ chối khi `mail.smtp.ssl.checkserveridentity=true` và đề xuất cách sửa endpoint/certificate.

### Bài 6 — STARTTLS bị tắt

Cho server test không quảng cáo STARTTLS. Xem sự khác biệt giữa `starttls.enable=true` và cấu hình có thêm `starttls.required=true`. Giải thích hành vi fail closed.

### Bài 7 — Container khác laptop

Một ứng dụng gửi được trên laptop nhưng lỗi PKIX trong container. Liệt kê các khác biệt ở JDK, truststore, proxy, DNS và CA chain cần đối chiếu. Không đề xuất tắt certificate validation.

### Bài 8 — Exception wrapping

Viết một lớp phân loại `MailException` theo root cause type để ghi metric TLS/network/auth. Không log mật khẩu, dữ liệu MIME hoặc token.

### Bài 9 — Cert rotation

Mô phỏng provider thay leaf certificate trong cùng CA, rồi thay intermediate/CA được tổ chức phê duyệt. Thiết kế bước thử nghiệm và rollout truststore trước thời điểm rotation.

### Bài 10 — Retry sau sự cố

Trong sự cố TLS, có 500 outbox items chưa gửi và 5 items ở trạng thái `UNKNOWN`. Thiết kế cách phục hồi backlog với rate limit mà không retry mù các item không rõ submission outcome.

## 16. Tổng kết

Lỗi TLS, chứng chỉ và handshake trong Spring Framework Mail thường bắt nguồn từ **nhầm STARTTLS với implicit TLS, chọn sai host/port, certificate chain thiếu hoặc không tin cậy, hostname không khớp SAN, chứng chỉ hết hạn, giao thức/cipher không tương thích hoặc network/proxy can thiệp**.

Hướng xử lý an toàn là:
1. Xác nhận đúng **SMTP host, port và TLS mode**.
2. Với port 587 STARTTLS, dùng `mail.smtp.starttls.enable=true` và `required=true` khi provider yêu cầu TLS.
3. Với port 465 implicit TLS, dùng `mail.smtp.ssl.enable=true`.
4. Bật `mail.smtp.ssl.checkserveridentity=true` và giữ certificate validation.
5. Kiểm tra certificate chain/SAN/validity và **truststore thực sự của JVM**.
6. Chẩn đoán từ đúng mạng/runtime bằng OpenSSL, keytool và log JSSE có kiểm soát.
7. Phân biệt lỗi TLS với network, AUTH và kết quả SMTP submission.
8. Không dùng trust-all hoặc hạ cấp mã hóa để né lỗi; sửa đúng nguyên nhân và thử lại có giới hạn.

Một cấu hình TLS đúng không chỉ giúp `JavaMailSender` kết nối ổn định; nó còn bảo đảm ứng dụng đang trao đổi thông tin đăng nhập và nội dung email với **SMTP server mà ứng dụng thực sự có ý định tin cậy**.
