# HTTPS, chứng thư TLS và giới hạn của bảo vệ trên đường truyền

> **Ý chính:** HTTPS dùng TLS để bảo vệ dữ liệu **trên đường truyền giữa hai đầu kết nối TLS** và giúp client kiểm chứng danh tính máy chủ qua chứng thư số. HTTPS **không tự xác thực người dùng, phân quyền nghiệp vụ, bảo vệ dữ liệu sau khi giải mã hoặc làm cho một ứng dụng dễ bị lỗi trở nên an toàn**. Trong ứng dụng Spring Security, TLS là nền tảng bắt buộc cho việc vận chuyển cookie, session, password, authorization header và token một cách phù hợp.

## 1. Học xong cần hiểu và làm được gì?

- Phân biệt HTTP, HTTPS, TLS, “SSL certificate” và chứng thư X.509; hiểu ba mục tiêu chính: **bí mật, toàn vẹn và xác thực máy chủ**.
- Diễn giải ở mức khái niệm một TLS handshake, cách kiểm tra hostname, chuỗi chứng thư và trust store; biết vì sao chỉ thấy biểu tượng ổ khóa chưa đủ để kết luận website đáng tin về nội dung.
- Nhận diện ranh giới TLS khi ứng dụng đứng sau load balancer/CDN/reverse proxy, khi proxy giải mã rồi chuyển tiếp HTTP, và khi có nhiều dịch vụ nội bộ.
- Cấu hình Spring Boot chạy HTTPS cục bộ với chứng thư tự ký, xác minh chứng thư bằng `curl`, phân biệt kiểm thử có xác minh với `-k` bỏ xác minh.
- Hiểu HTTPS không giải quyết IDOR, XSS, SQL injection, CSRF, lộ token ở log, mã độc trên endpoint, website lừa đảo có chứng thư hợp lệ hoặc việc lộ dữ liệu ở nơi TLS đã kết thúc.

## 2. HTTP và HTTPS khác nhau ở đâu?

HTTP định nghĩa phương thức, URL, header, body, status code và ngữ nghĩa trao đổi request/response. Khi dùng HTTP thuần trên mạng không đáng tin cậy, đối tượng có quyền quan sát hoặc chỉnh sửa đường truyền có thể đọc nội dung và can thiệp gói tin.

HTTPS = **HTTP chạy trên một kênh được TLS bảo vệ**, thường dùng cổng 443. Với HTTP/1.1 và HTTP/2, TLS thường chạy trên TCP; HTTP/3 tích hợp TLS 1.3 với QUIC/UDP. “HTTPS” không đồng nghĩa tất cả traffic đều dùng TCP.

| Khả năng | HTTP không có TLS | HTTPS với TLS được cấu hình và kiểm chứng đúng |
| --- | --- | --- |
| Che nội dung request/response trên đường truyền | Không | Có, giữa hai TLS endpoint |
| Phát hiện sửa đổi dữ liệu truyền đi | Không có bảo vệ mã hóa ở HTTP | Có, qua kiểm tra toàn vẹn/bản ghi TLS |
| Kiểm chứng máy chủ là chủ thể của tên miền đã kết nối | Không | Có, **nếu** client xác minh chứng thư, chuỗi tin cậy và hostname |
| Tự biết user đăng nhập là ai | Không | Không; cần session, OAuth2/OIDC, Basic, mTLS hoặc cơ chế phù hợp |
| Tự bảo đảm user có quyền xem hồ sơ | Không | Không; cần authorization trên server |
| Tự chặn SQL injection, XSS, CSRF, SSRF | Không | Không; cần xử lý ở tầng ứng dụng |
| Mã hóa dữ liệu sau khi server giải mã | Không | Không; cần chính sách lưu trữ/xử lý riêng |

Ví dụ:

```http
GET /account/balance HTTP/1.1
Host: bank.example
Cookie: SESSION=example-session-id
```

Với kết nối HTTPS hợp lệ, đường dẫn, header và body HTTP được TLS bảo vệ khi truyền giữa client và TLS endpoint. Điều đó ngăn một người chỉ nghe trộm mạng Wi-Fi đọc trực tiếp cookie hoặc số dư. Tuy nhiên, trình duyệt vẫn biết URL đầy đủ; server/proxy nhận và giải mã request vẫn thấy nó; mã độc trong trình duyệt, log ứng dụng hoặc lỗ hổng XSS có thể làm lộ dữ liệu ở những điểm khác.

**Quan trọng:** Một URL bắt đầu bằng `https://` chỉ thể hiện **ý định dùng TLS**. An toàn thực tế còn phụ thuộc vào việc kết nối đã thương lượng thành công, chứng thư được xác minh, hostname khớp, endpoint có đáng tin và các bên xử lý dữ liệu an toàn.

## 3. TLS bảo vệ những gì?

### 3.1. Tính bí mật (confidentiality)

TLS đàm phán khóa phiên và dùng mã hóa đối xứng cho dữ liệu ứng dụng. Với cấu hình hiện đại, đối tượng chỉ thu được các gói tin mã hóa thường không thể đọc nội dung HTTP. TLS 1.3 sử dụng các bộ mã hóa có xác thực (AEAD); lựa chọn thuật toán và phiên bản phải do server/client được cấu hình đúng.

Bảo vệ này **kết thúc ở mỗi TLS endpoint**. Nếu browser kết nối HTTPS với CDN, còn CDN gửi HTTP thuần đến backend, người kiểm soát đoạn CDN → backend có thể thấy nội dung đã giải mã. Muốn bảo vệ cả đoạn đó cần TLS tiếp theo hoặc kênh mạng được quản lý với mô hình rủi ro thích hợp.

### 3.2. Tính toàn vẹn (integrity)

TLS phát hiện việc sửa đổi bản ghi mã hóa trên đường truyền. Kẻ trung gian không thể tự ý sửa `amount=100` thành `amount=100000` trong phiên đã xác thực mà vẫn qua kiểm tra toàn vẹn. Tuy nhiên, **client hợp lệ** vẫn có thể tự gửi amount trái phép. Máy chủ phải kiểm tra giá trị, chủ sở hữu, trạng thái và luật nghiệp vụ.

### 3.3. Xác thực máy chủ (server authentication)

Client kiểm tra chứng thư X.509 do server cung cấp để xác minh rằng server mà mình kết nối có quyền sử dụng tên miền được yêu cầu trong phạm vi hệ thống PKI mà client tin cậy. Trong một kết nối HTTPS web thông thường, phía **client không tự động cung cấp chứng thư**; mTLS là cấu hình bổ sung. HTTPS bảo vệ password/token khi truyền, nhưng không thay bước xác thực user và phân quyền.

### 3.4. Những thông tin có thể còn quan sát được

TLS không bảo đảm ẩn tất cả metadata: địa chỉ IP đích, số lượng/thời điểm/độ lớn bản ghi, thông tin từ DNS thông thường và trong nhiều cấu hình cả hostname từ SNI có thể bị quan sát. Cơ chế như DNS mã hóa và Encrypted ClientHello (ECH) có thể giảm lộ một số dữ liệu tùy mức hỗ trợ và cấu hình; HTTPS đơn thuần **không có nghĩa mọi dấu vết truy cập bị ẩn**. Nội dung cụ thể của URL path/query được mã hóa trong HTTP trao đổi, nhưng dịch vụ DNS, người quản lý endpoint hoặc proxy giải mã có thể quan sát dữ liệu thuộc phạm vi của họ.

## 4. TLS handshake và chứng thư số hoạt động như thế nào?

### 4.1. Dòng chảy cơ bản với TLS 1.3

```text
Client / Browser                                  Server / HTTPS endpoint
     |  ClientHello: supported versions, groups,  |
     |  key share, SNI, ALPN...                    |
     |-------------------------------------------->|
     |               ServerHello: params, key share|
     |<--------------------------------------------|
     |   [EncryptedExtensions, Certificate,       |
     |    CertificateVerify, Finished ...]         |
     |<--------------------------------------------|
     |  Kiểm chứng hostname, chuỗi tin cậy, chữ ký |
     |  Finished, thiết lập khóa phiên             |
     |-------------------------------------------->|
     |          HTTP request (encrypted)          |
     |-------------------------------------------->|
     |          HTTP response (encrypted)         |
     |<--------------------------------------------|
```

Đây là lược đồ khái niệm cho một full handshake TLS 1.3. TLS 1.2, session resumption và HTTP/3 có chi tiết khác. Trong thực tế, thông điệp bắt tay có thể được đóng gói và gửi theo các chuyến/record khác nhau.

1. **ClientHello** thông báo các phiên bản, nhóm khóa, phương án mã hóa và thường cả SNI (tên host server cần phục vụ). ALPN có thể được dùng để thương lượng giao thức như `h2` hoặc `http/1.1`.
2. **ServerHello** chọn thông số và trao đổi thông tin để hai phía tạo khóa phiên. Các cơ chế trao đổi khóa tạm thời (như ECDHE) ở TLS hiện đại hỗ trợ **forward secrecy**: lộ khóa chứng thư về sau không tự giải mã được mọi phiên đã ghi lại trước đó.
3. Server trình chứng thư và chứng minh sở hữu khóa riêng tương ứng. Client kiểm tra chứng thư và chain với trust store, đối chiếu danh tính host yêu cầu, hạn hiệu lực và các ràng buộc liên quan.
4. Hai phía kiểm tra thông điệp `Finished` để xác nhận handshake không bị thay đổi và có cùng khóa; sau đó truyền HTTP qua kênh TLS.
5. Có thể tái sử dụng phiên để giảm số lượt bắt tay. Với TLS 1.3, **0-RTT early data nếu được bật** có nguy cơ replay; thao tác nhạy cảm/không idempotent cần tránh cho phép 0-RTT hoặc có kiểm soát replay riêng. Ví dụ bên dưới không bật tính năng này.

**Đừng đồng nhất TLS với “chỉ mã hóa bằng public key”:** public/private key trong chứng thư chủ yếu tham gia xác thực/chữ ký, trong khi lưu lượng HTTP được bảo vệ bằng **khóa đối xứng của phiên**, có hiệu năng tốt hơn.

### 4.2. Chứng thư X.509 gồm những gì?

Một chứng thư TLS dành cho máy chủ thường chứa:

- **Subject Alternative Name (SAN):** danh sách DNS name/IP mà chứng thư có thể đại diện. Việc so khớp hostname hiện đại dựa trên SAN; không nên dựa vào mỗi `CN`.
- **Public key** của server, thuật toán chữ ký, issuer, serial number, thời điểm `Not Before` và `Not After`.
- Các extension thể hiện mục đích sử dụng (ví dụ server authentication) và các ràng buộc theo chuẩn X.509.

**Private key** tương ứng nằm ở phía máy chủ hoặc hệ thống quản lý khóa; **không** xuất hiện trong chứng thư public. Giữ bí mật private key quan trọng hơn che nội dung chứng thư. File certificate dạng PEM có thể công khai; private key và file keystore chứa private key phải được bảo vệ.

### 4.3. Chuỗi tin cậy và xác minh hostname

```text
Trust store của client
  Root CA đáng tin
       |
       +-- Intermediate CA
                |
                +-- Certificate của api.example.com (SAN: api.example.com)
                                   |
                           Client gọi https://api.example.com
                           + xác minh chữ ký/chain/hạn/usage
                           + hostname khớp SAN
```

Một server có thể gửi chứng thư server (leaf) và các intermediate. Client xây dựng chuỗi đến một trust anchor mà **client** tin tưởng; root không nhất thiết được server gửi. Ngoài chuỗi chữ ký, kiểm tra cần đáp ứng hostname, thời hạn và các ràng buộc sử dụng khóa/phần mở rộng. Kiểm tra thu hồi (OCSP/CRL) có mức độ hỗ trợ khác nhau giữa client/chính sách, nên không giả định **mọi** client luôn từ chối chứng thư đã bị thu hồi ngay lập tức.

Ví dụ rủi ro:

- Chứng thư hợp lệ cho `shop.example.com` **không** hợp lệ cho `payment.example.net` nếu SAN không chứa tên đó, dù cả hai cùng một nhà vận hành.
- Trình duyệt báo “certificate expired” hoặc “hostname mismatch” là lỗi ranh giới tin cậy, không phải lỗi giao diện có thể bỏ qua tùy ý.
- Chứng thư **tự ký** không mặc nhiên sai về mặt mật mã, nhưng client phải thiết lập tin cậy một cách có chủ đích; production thường sử dụng CA được client mục tiêu tin cậy hoặc PKI nội bộ được quản lý.
- Việc một trang có chứng thư hợp lệ chỉ chứng minh quyền kiểm soát định danh theo cơ chế cấp chứng thư, **không xác nhận trang đó là ngân hàng thật, doanh nghiệp uy tín hoặc nội dung vô hại**. Trang phishing vẫn có thể dùng HTTPS.

### 4.4. “SSL certificate” và vòng đời chứng thư

“SSL certificate” là cách gọi phổ biến, nhưng giao thức dùng trong triển khai mới là **TLS**. Các phiên bản SSL cũ đã lỗi thời; nên ưu tiên TLS 1.3 và TLS 1.2 với cấu hình mạnh tương thích nhu cầu. Không mở lại SSLv3/TLS 1.0/1.1 để “chữa” một client quá cũ mà không đánh giá rủi ro.

Quy trình vận hành không kết thúc sau khi mua hoặc tạo chứng thư: cần quản lý private key, kiểm tra tên miền và chain, tự động cấp/gia hạn, theo dõi ngày hết hạn, cập nhật cấu hình khi thay proxy, thu hồi/thay khóa bị lộ và tránh đưa private key/keystore có mật khẩu thật vào Git, image hoặc log.

## 5. TLS kết thúc ở đâu trong kiến trúc Spring Boot?

### 5.1. TLS trực tiếp trong ứng dụng

```text
Browser  -- HTTPS/TLS -->  Spring Boot embedded server
                            (TLS private key ở server)
                            |
                            +--> Spring Security filter chain
                            +--> Controller / Service / Database
```

Ứng dụng tự có chứng thư/keystore và cổng HTTPS. Đây là mô hình dễ học và phù hợp một số triển khai, nhưng production thường sử dụng gateway/ingress chịu trách nhiệm TLS certificate lifecycle.

### 5.2. TLS termination tại proxy hoặc CDN

```text
Browser --HTTPS--> Load balancer / CDN / reverse proxy
                     | Giải mã TLS, thấy HTTP path/header/body
                     |
                     +--HTTP nội bộ--> Spring Boot
                            hoặc
                     +--HTTPS/TLS----> Spring Boot
```

**Chỉ đoạn browser → proxy được bảo vệ bởi TLS thứ nhất.** Nếu proxy → app chạy HTTP, dữ liệu trên đoạn đó ở dạng plaintext; cần đánh giá mạng nội bộ, khả năng nghe lén, yêu cầu tuân thủ và tính nhạy cảm để quyết định dùng HTTPS tiếp hoặc mTLS. Kết nối backend dùng HTTPS cũng cần kiểm chứng đúng danh tính backend, tránh chỉ “bật mã hóa nhưng không xác thực”.

Khi proxy kết thúc TLS, Spring Boot có thể nhìn thấy kết nối đến nó là HTTP và coi `request.isSecure()` là `false`. Các header `Forwarded`/`X-Forwarded-Proto` giúp ứng dụng biết scheme gốc **chỉ khi chúng được một proxy đáng tin cậy thiết lập/ghi đè đúng cách**. Nếu server Internet cho client tự đưa `X-Forwarded-Proto: https` rồi tin nó, attacker có thể ảnh hưởng vào redirect, absolute URL, cookie policy hoặc cơ chế bảo vệ phụ thuộc “secure request”.

Với Spring Boot, property `server.forward-headers-strategy` có thể được dùng theo hạ tầng (`native`/`framework`) để xử lý forwarded headers, nhưng chỉ bật sau khi ingress đã chuẩn hóa header, backend không bị truy cập trực tiếp trái phép và danh sách proxy tin cậy đã được xác định. Đừng mặc định header gửi từ client là bằng chứng kết nối TLS đã an toàn.

### 5.3. TLS và mTLS

- HTTPS thông thường xác thực server tới client. Người dùng vẫn phải đăng nhập bằng session, OAuth2/OIDC, token hay cơ chế thích hợp.
- **mTLS** bổ sung bước client đưa chứng thư để server xác thực danh tính client tại ranh giới TLS. Nó hữu ích cho service-to-service hoặc thiết bị được quản lý.
- Chứng thư client không tự mang nghĩa “được phép xem hóa đơn này”; vẫn cần map danh tính chứng thư sang principal và kiểm tra permission/owner/tenant ở service.
- Nếu mTLS kết thúc ở proxy, backend phải nhận thông tin client qua kênh được tin cậy và không được chấp nhận header giả mạo từ Internet. Mọi quyết định tin chứng thư phải gắn với ranh giới mạng thực tế.

## 6. Ví dụ chạy được: Spring Boot HTTPS và xác minh chứng thư

Ví dụ này minh họa đồng thời:

1. Máy chủ Spring Boot lắng nghe HTTPS trực tiếp trên cổng `8443`.
2. Một chứng thư tự ký dùng **chỉ trong máy học** với SAN cho `localhost` và `127.0.0.1`.
3. Client kiểm tra chứng thư/hostname bằng `curl --cacert`; nếu không được tin cậy, kết nối thất bại trước khi HTTP request hợp lệ được trao đổi.
4. Spring Security yêu cầu đăng nhập cho endpoint private. TLS xác thực server, Basic Auth xác thực user, còn authorization quyết định endpoint được gọi.

**Phiên bản minh họa:** Java 17, Spring Boot **3.3.13** (một bản phát hành thật, nhưng nhánh 3.3.x đã kết thúc hỗ trợ mã nguồn mở vào 19/06/2025). Bản cố định này giúp tái hiện bài học; dự án sản xuất phải chọn dòng Spring Boot đang được hỗ trợ và bản vá hiện hành. Mật khẩu `changeit` và `demo-pass` chỉ dành cho ví dụ local.

### 6.1. Cấu trúc dự án

```text
tls-demo/
├── pom.xml
├── localhost.crt                       # public certificate để curl tin cậy local
└── src/main/
    ├── java/demo/tls/HttpsDemoApplication.java
    └── resources/
        ├── application.properties
        └── tls/local-keystore.p12       # chứa PRIVATE KEY, chỉ dùng local
```

### 6.2. Maven dependencies

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>tls-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. Tạo chứng thư tự ký cho local

Trước khi chạy, tạo thư mục `src/main/resources/tls` bằng IDE hoặc terminal; mở terminal tại thư mục `tls-demo`. Chạy lệnh JDK `keytool` sau trên **một dòng** (dùng được với PowerShell hoặc Bash):

```bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 3072 -validity 30 -storetype PKCS12 -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Lệnh này tạo private key và chứng thư public có SAN. Để xuất **chỉ chứng thư public** cho client:

```bash
keytool -exportcert -rfc -alias localdev -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit -file localhost.crt
```

Kiểm tra thông tin chứng thư:

```bash
keytool -list -v -alias localdev -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit
```

Khi được in ra, thông tin cần thấy gồm `Owner: CN=localhost`, `Issuer: CN=localhost` (self-signed), SAN có DNS `localhost` và IP `127.0.0.1`, cùng hạn hiệu lực khoảng 30 ngày từ lúc tạo. Dạng chữ hiển thị tùy phiên bản JDK.

**Ranh giới bảo mật:** file `.p12` chứa private key; `localhost.crt` chỉ chứa public certificate. Trong dự án thật, private key/keystore phải được bảo vệ bằng quyền truy cập thích hợp, secret manager hoặc key store của hạ tầng; không commit vào repository. Chứng thư local tự ký không phù hợp để triển khai công khai và tuyệt đối không dùng mật khẩu minh họa trong production.

### 6.4. Cấu hình HTTPS trong Spring Boot

Tạo `src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:tls/local-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=changeit
server.ssl.key-alias=localdev
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
```

`server.ssl.*` là cấu hình **server connector** của Spring Boot/embedded servlet container. Chúng thiết lập TLS ở cổng 8443; không tạo một HTTP listener ở cổng 8080 và **không tự tạo HTTP → HTTPS redirect**. Chuyển hướng từ HTTP port 80 sang 443 cần được cấu hình ở proxy/ingress hoặc qua connector HTTP riêng nếu có lý do vận hành.

### 6.5. Mã Java đầy đủ

Tạo `src/main/java/demo/tls/HttpsDemoApplication.java`:

```java
package demo.tls;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/status").permitAll()
                .requestMatchers("/private").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}

@RestController
class TlsController {
    @GetMapping("/status")
    Map<String, Object> status(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure()
        );
    }

    @GetMapping("/private")
    String privateMessage(Authentication auth) {
        return "Hello " + auth.getName();
    }
}
```

**Tại sao cần cả TLS và Spring Security?**

- TLS bảo vệ request/response **trên kết nối HTTPS tới server** và kiểm chứng chứng thư server phía client.
- `HttpSecurity.authorizeHttpRequests` quyết định endpoint nào công khai, endpoint nào cần authentication. Nó không tự cấp HTTPS nếu server/proxy chưa cấu hình TLS.
- `httpBasic` xác thực user. Basic Auth chỉ Base64-encode credential, **không tự mã hóa credential**; HTTPS là thiết yếu khi truyền Basic Auth. Production thường cần cơ chế xác thực phù hợp hơn, kiểm soát truy cập, rate limit và MFA khi cần.
- `Map.of` giúp quan sát scheme và trạng thái secure ở phía server. Nó có giá trị minh họa khi ứng dụng nhận TLS trực tiếp, nhưng sau reverse proxy cần xét forwarded header/trust boundary.
- Với Spring Security Servlet, security headers mặc định thường có HSTS trên response HTTPS; ứng dụng vẫn cần xác minh header ở hạ tầng triển khai thực tế, nhất là khi TLS kết thúc ở proxy.

### 6.6. Chạy và thử nghiệm

Yêu cầu **JDK 17+**, Maven 3.6.3+ và terminal tại thư mục dự án:

```bash
mvn spring-boot:run
```

Trên Linux/macOS/Git Bash dùng `curl`. Trên Windows PowerShell 5.1, dùng `curl.exe` thay vì alias `curl` của PowerShell.

**Trường hợp A — client tin chứng thư local một cách tường minh:**

```bash
curl -i --cacert localhost.crt https://localhost:8443/status
```

Khi ứng dụng đã khởi động và certificate đúng, kỳ vọng HTTP status **200** với JSON chứa `"scheme":"https"` và `"secure":true`. Thứ tự các key JSON và header có thể thay đổi; không cần khớp byte-for-byte.

**Trường hợp B — không cấu hình trust cho chứng thư tự ký:**

```bash
curl -i https://localhost:8443/status
```

Trên máy chưa tin root/certificate local, kết nối thường bị từ chối do không xác minh được chuỗi tin cậy (ví dụ curl error 60). Đó là **hành vi bảo vệ đúng**, không phải lý do để tắt xác minh chứng thư trong ứng dụng.

**Trường hợp C — hostname không khớp SAN:**

```bash
curl -i --cacert localhost.crt --resolve wrong.example.test:8443:127.0.0.1 https://wrong.example.test:8443/status
```

`--resolve` chỉ buộc client tới IP loopback, nhưng tên host TLS vẫn là `wrong.example.test`. Vì chứng thư chỉ có SAN `localhost` và `127.0.0.1`, request phải **thất bại khi kiểm tra hostname**. Nếu curl dùng proxy hệ thống, cần tắt proxy cho tên test local bằng cấu hình môi trường thích hợp.

**Trường hợp D — TLS hoạt động nhưng API vẫn yêu cầu đăng nhập:**

```bash
curl -i --cacert localhost.crt https://localhost:8443/private
curl -i --cacert localhost.crt -u alice:demo-pass https://localhost:8443/private
```

Kỳ vọng lệnh đầu nhận **401** theo HTTP Basic challenge; lệnh thứ hai nhận **200** và body `Hello alice`. Hai request đều qua TLS hợp lệ; khác nhau ở việc có credential được server chấp nhận. Việc được xem endpoint `/private` không đồng nghĩa user có quyền đọc tất cả dữ liệu nghiệp vụ trong một ứng dụng thực tế.

**Trường hợp E — HTTP thuần trên cổng chỉ nhận TLS:**

```bash
curl -v http://localhost:8443/status
```

Không nhận được JSON trả về qua HTTP thuần; server có thể đóng kết nối hoặc phản hồi lỗi giao thức vì đang yêu cầu TLS. Điều này **không phải** minh họa redirect HTTP → HTTPS. Muốn kiểm chứng redirect, kiểm tra listener/proxy HTTP riêng đã được cấu hình.

**Cảnh báo về `-k`/`--insecure`:** `curl -k` bỏ qua kiểm tra chứng thư nên có thể biến kết nối mã hóa thành kết nối tới **sai server** mà client không phát hiện được. Chỉ dùng để chẩn đoán rất hẹp trong môi trường thử nghiệm, không dùng làm “cách sửa” cho ứng dụng hoặc script production. Với self-signed local, dùng `--cacert localhost.crt` như trên.

## 7. HSTS, redirect HTTPS và cookie an toàn

### 7.1. Redirect HTTP → HTTPS

Một deployment công khai thường nhận request HTTP tại cổng 80 và chuyển sang HTTPS bằng redirect **301/308** (mã tùy thiết kế); sau đó client kết nối tới URL HTTPS mới. Redirect là quyết định ở server/proxy và tự nó **không bảo vệ request HTTP ban đầu**: nếu client gửi password/token qua HTTP trước khi redirect, chúng đã có thể bị quan sát. Nên tạo link, form action, API base URL và callback URL bằng HTTPS ngay từ đầu; tránh nhận request chứa credential qua HTTP.

### 7.2. HTTP Strict Transport Security (HSTS)

Ví dụ header:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Sau khi browser nhận HSTS hợp lệ qua HTTPS, browser được hướng dẫn tự nâng các lần truy cập tiếp theo đến host sang HTTPS trong thời gian `max-age`. Tùy chính sách, `includeSubDomains` mở rộng phạm vi tới các subdomain; `preload` liên quan quy trình đưa host vào danh sách preload của trình duyệt và có yêu cầu vận hành riêng. **Không bật includeSubDomains/preload bừa bãi** nếu có subdomain chưa hỗ trợ HTTPS.

Giới hạn của HSTS:

- HTTP header HSTS gửi qua **HTTP thuần** không được coi là tín hiệu tin cậy để kích hoạt chính sách.
- HSTS thông thường chỉ có tác dụng **sau khi browser đã học chính sách** từ một kết nối HTTPS hợp lệ. Preload có thể bảo vệ lần đầu cho domain đã được đưa vào danh sách và browser hỗ trợ.
- HSTS không biến chứng thư sai thành đúng, không bảo vệ ứng dụng trước lỗ hổng XSS/authorization và không phải cơ chế xác thực user.
- Browser và các client HTTP tự viết có thể xử lý HSTS khác nhau; `curl` không được coi là mô phỏng đầy đủ hành vi HSTS của trình duyệt.

Spring Security có hỗ trợ ghi HSTS header trên secure response (khi request được nhận diện là HTTPS), nhưng **không tự cấu hình máy chủ TLS hoặc redirect toàn bộ hạ tầng**. Trên kiến trúc có reverse proxy, kiểm tra HSTS tại response mà **trình duyệt thực sự nhận**.

### 7.3. Cookie và token

Với đăng nhập dùng session cookie, thiết lập thuộc tính phù hợp:

- `Secure`: browser chỉ gửi cookie qua kết nối an toàn theo quy tắc cookie.
- `HttpOnly`: giới hạn JavaScript trực tiếp đọc cookie; không ngăn XSS thực hiện request thay mặt user.
- `SameSite`: giúp giảm một số trường hợp cross-site cookie sending, nhưng không thay hoàn toàn CSRF protection cho mọi ứng dụng.
- Giới hạn `Domain`/`Path`, thời hạn, rotation và session fixation theo mô hình rủi ro. Dùng cookie prefix `__Host-` khi phù hợp yêu cầu về Secure, Path và không có Domain.
- Không đưa access token, password hoặc session secret vào query string vì query có thể xuất hiện trong history, access log, analytics, exception và các hệ thống quan sát sau TLS termination.

Nếu frontend giữ bearer token trong nơi JavaScript có thể đọc, HTTPS chỉ bảo vệ token khi gửi đi; mã độc/XSS trên origin vẫn có thể truy cập token. Phải đánh giá storage strategy, XSS defense và thời hạn/thu hồi token riêng.

### 7.4. Mixed content, WebSocket và liên kết ngoài

Trang tải qua HTTPS nhưng gọi script, hình ảnh, iframe hoặc API qua HTTP có thể gặp **mixed content**. Browser có thể chặn hoặc tự nâng một số loại nội dung tùy tiêu chuẩn/chính sách; không dựa vào auto-upgrade để đảm bảo mọi dependency đều an toàn. Dùng URL HTTPS cho tài nguyên; nếu dùng WebSocket từ trang HTTPS, lựa chọn `wss://` khi kết nối phải được mã hóa. Kiểm tra link tải file, webhook callback, redirects và kết nối backend riêng lẻ.

## 8. HTTPS không bảo vệ những rủi ro nào?

| Tình huống | HTTPS có giải quyết? | Cách xử lý tương ứng |
| --- | --- | --- |
| Bên thứ ba nghe lén request giữa browser và TLS endpoint | **Có**, nếu TLS xác thực đúng | TLS mạnh, xác minh hostname/chứng thư, bảo vệ khóa |
| Attacker sửa response khi ở giữa một kết nối TLS hợp lệ | **Phát hiện/chặn** tại lớp TLS | Cấu hình phiên bản/bộ mã hóa phù hợp |
| User đăng nhập đọc tài liệu của user khác bằng cách đổi ID | **Không** | Authorization theo user/action/resource/tenant ở server |
| SQL injection qua query/form | **Không** | Prepared statement, parameter binding, validation |
| XSS trong HTML phản hồi qua HTTPS | **Không** | Output encoding theo ngữ cảnh, sanitize HTML, CSP phù hợp |
| CSRF từ trình duyệt có session cookie | **Không** | CSRF token/thiết kế cookie và kiểm tra Origin/Fetch Metadata phù hợp |
| Website giả mạo có tên miền lừa đảo và cert hợp lệ | **Không** | Xác minh domain thật, chống phishing, quản lý thương hiệu |
| Reverse proxy giải mã TLS rồi gửi plaintext đến backend | **Không bảo vệ đoạn sau proxy** | HTTPS/mTLS giữa các hop hoặc mạng tin cậy được kiểm soát |
| API key/password/token bị ghi trong log hoặc crash dump | **Không** | Masking, hạn chế log, secret management, retention |
| Private key server bị lộ | **Không thể tự sửa** | Xử lý sự cố, thay khóa/chứng thư, thu hồi theo khả năng |
| Máy client/server nhiễm mã độc | **Không** | Endpoint security, hardening, patching |
| Người có quyền cố ý lạm dụng dữ liệu sau khi giải mã | **Không** | Least privilege, audit, dữ liệu tối thiểu, giám sát |
| Replay một giao dịch nghiệp vụ hợp lệ | **Không tự đảm bảo** | Idempotency, nonce/expiry nếu cần, state machine, transaction |
| Dữ liệu nằm trong database, backup, file upload | **Không** | Encryption at rest khi cần, access control, phân quyền lưu trữ |
| Tấn công DoS/cạn tài nguyên | **Không toàn diện** | Rate limit, quota, WAF/edge capacity, timeout, circuit breaker |

Ví dụ rõ ràng: `POST https://api.example.com/transfer` đi qua TLS, không ai sửa được trong transit, nhưng kẻ đang đăng nhập hợp lệ vẫn có thể gửi số tiền âm hoặc chuyển từ tài khoản không thuộc mình nếu backend thiếu validation/authorization. **TLS đã làm đúng việc của nó; lỗi nằm ở logic nghiệp vụ.**

Tương tự, trình duyệt hiển thị ổ khóa khi vào một website lừa đảo được cấp chứng thư cho chính tên miền của kẻ tấn công. Chứng thư chứng minh “đã kết nối đúng tên miền trên thanh địa chỉ theo PKI”, **không chứng minh tên miền đó thuộc tổ chức mà người dùng nghĩ tới**.

## 9. Các lỗi triển khai thường gặp

### 9.1. Vô hiệu hóa xác minh chứng thư vì “chạy cho được”

Sai: `curl -k` trong pipeline production, HTTP client dùng trust-all manager hoặc tắt hostname verification. Việc này làm mất bảo đảm định danh máy chủ và tạo cơ hội man-in-the-middle. Đúng: cấp đúng chứng thư, gửi đủ intermediate, cấu hình trust store/CA nội bộ và SAN khớp tên kết nối. Không nhúng “trust any certificate” làm mặc định.

### 9.2. Chỉ bật HTTPS ở cửa ngoài, quên các hop sau

Phần mềm thấy `https://` ở URL bên ngoài rồi mặc định các kết nối proxy → service, service → database/message broker đều được mã hóa. Đúng: vẽ toàn bộ sơ đồ luồng dữ liệu, đánh dấu vị trí TLS termination, chỉ rõ credential, CA, mTLS/hostname verification và quyền truy cập ở **từng kết nối** cần bảo vệ.

### 9.3. Dùng header forwarded không có trust boundary

Sai: cho phép client Internet gửi `X-Forwarded-Proto: https` hoặc `X-Forwarded-Host` và cho Spring tin ngay. Đúng: ingress ghi đè/xóa header do client gửi, chặn truy cập trực tiếp backend, cấu hình trusted proxy và kiểm tra redirect/cookie/security headers bằng integration test sau proxy.

### 9.4. Để server certificate hết hạn hoặc SAN sai

Sai: chỉ kiểm tra có file `.p12`, không kiểm tra chain/hostname/expiry, hoặc gia hạn quên reload proxy. Đúng: tự động hóa cấp/gia hạn, giám sát hết hạn, kiểm chứng handshake sau deploy, kiểm tra đúng host production và quy trình rollback/rotate.

### 9.5. Nghĩ rằng HTTPS đã giải quyết session và CSRF

Sai: password/token đi qua HTTPS là xong dù cookie không có flags phù hợp, token bị log, thiếu session expiry, ứng dụng có XSS hoặc endpoint POST không có CSRF protection. Đúng: giữ cơ chế bảo vệ web/app độc lập, test quyền và session, kiểm tra cookie/CSRF theo phương thức authentication.

### 9.6. Bật HSTS/preload khi subdomain chưa sẵn sàng

Sai: áp dụng `includeSubDomains` cho tổ chức có nhiều dịch vụ nội bộ chỉ chạy HTTP, dẫn đến browser không thể truy cập. Đúng: kiểm kê DNS/subdomain, chiến lược HTTPS đồng bộ, test rollout, quản lý preload như quyết định có vòng đời và khó hoàn tác tức thời.

### 9.7. Nhầm mã hóa dữ liệu với xác minh đúng máy chủ

Sai: thấy traffic được TLS mã hóa nhưng trust tất cả chứng thư; lúc đó attacker có thể tạo TLS session riêng với client và giải mã traffic của session ấy. Đúng: kiểm chứng chain, SAN, thời hạn, mục đích cert và policy trust; mã hóa và **xác thực endpoint** là hai điều kiện cần cùng lúc.

## 10. Checklist khi đưa HTTPS/Spring Security vào production

1. **Toàn bộ đường vào:** site, API, admin, tải file, WebSocket, auth callback có dùng HTTPS/WSS thực sự? Có endpoint HTTP nào nhận secret trước khi redirect không?
2. **TLS termination:** ở CDN, ingress, app hay service mesh? Mỗi hop cần TLS không? Có hostname verification và client/server trust đúng ở backend không?
3. **Chứng thư:** SAN khớp tên thật, chain đầy đủ, private key được bảo vệ, có tự động gia hạn và cảnh báo hết hạn không?
4. **Giao thức:** TLS 1.3 ưu tiên và TLS 1.2 chỉ khi cần; loại bỏ giao thức/cipher yếu; kiểm tra compatibility với client hợp lệ.
5. **Redirect/HSTS:** HTTP → HTTPS được triển khai ở đúng tầng; HSTS phù hợp cả subdomain; hiệu lực browser và readiness đã được kiểm tra?
6. **Forwarded headers:** backend chỉ tin header do ingress đáng tin chuẩn hóa; không cho bypass proxy; URL/cookie/redirect render đúng scheme?
7. **Cookie/token:** Secure, HttpOnly, SameSite, hạn sử dụng, thu hồi; không ghi credentials vào URL, log hoặc telemetry?
8. **Ứng dụng:** Spring Security authentication/authorization, CSRF khi cần, validation, chống XSS/SQL injection/IDOR vẫn có test?
9. **Tình huống thất bại:** chứng thư sai hostname, hết hạn, không được tin cậy có bị client từ chối? Có ai đưa `-k` hay trust-all vào production không?
10. **Vận hành:** có giám sát lỗi handshake, chứng thư hết hạn, thay khóa, phát hiện redirect sai, kiểm tra cấu hình sau proxy và quy trình xử lý lộ khóa?

Một test `MockMvc` thấy `isSecure() == true` khi mock request **không chứng minh** máy chủ thực tế đã mở TLS hay cert đúng. Để kiểm tra transport, dùng một **kết nối mạng thật** từ client tin CA phù hợp (curl/browser/HTTPS integration test); để kiểm tra chính sách user/resource, dùng thêm test Spring Security ở controller và service. Hai nhóm test có mục tiêu khác nhau.

## 11. Tóm tắt kiến thức cốt lõi

1. **HTTPS = HTTP qua TLS**, bảo vệ bí mật và toàn vẹn của dữ liệu đang truyền trong phạm vi **hai đầu kết nối TLS**.
2. Chứng thư X.509, trust chain, hostname SAN, thời hạn và kiểm tra chữ ký giúp client xác minh máy chủ; chỉ mã hóa nhưng tắt verify là **không đủ**.
3. Khi TLS kết thúc ở proxy/CDN, phải đánh giá **từng hop** phía sau. Forwarded headers phải được thiết lập bởi thành phần đáng tin cậy.
4. HSTS và redirect giúp trình duyệt dùng HTTPS nhất quán hơn; chúng không tự cấu hình TLS và không thay thế auth, authorization, CSRF hay xử lý code an toàn.
5. HTTPS là **lớp bảo vệ trên đường truyền**. Quyền truy cập tài nguyên, tính hợp lệ giao dịch, an toàn dữ liệu lưu trữ và bảo vệ thiết bị vẫn do ứng dụng và hạ tầng chịu trách nhiệm.

## Tài liệu tham khảo

- [Spring Security — HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Boot — Configure SSL](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.configure-ssl)
- [MDN — Transport Layer Security](https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
- [Spring Boot 3.3.13 release (19/06/2025)](https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/)
