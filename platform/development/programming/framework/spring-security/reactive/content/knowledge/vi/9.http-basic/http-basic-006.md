# Yêu cầu HTTPS và nguy cơ lộ thông tin qua log, proxy hoặc lịch sử công cụ

## 1. Vấn đề cốt lõi khi dùng HTTP Basic

Trong Spring Security reactive (Spring WebFlux), HTTP Basic xác thực bằng tên đăng nhập và mật khẩu mà client gửi trong HTTP header `Authorization`. Đây là giao thức đơn giản, được nhiều HTTP client hỗ trợ, nhưng bản thân Basic **không có cơ chế mã hóa credential**. Phần sau chữ `Basic` là Base64 của chuỗi `username:password`; bất kỳ ai đọc được header đều có thể giải mã nó.

Vì vậy, dùng Basic một cách có trách nhiệm phải đồng thời kiểm soát:

1. **Đường truyền:** bắt đầu bằng HTTPS, kiểm tra chứng chỉ và hostname; không gửi credential qua HTTP.
2. **Điểm kết thúc TLS:** proxy/gateway và ứng dụng có thể nhìn thấy header sau giải mã; phải bảo vệ mọi chặng liên quan.
3. **Logging/observability:** không ghi password, Basic token, Authorization header hay secret tương tự vào access log, application log, trace và APM.
4. **Công cụ vận hành:** không đưa mật khẩu vào URL, shell command, browser history, API client collection, file test và CI output.
5. **Vòng đời credential:** giới hạn quyền, bảo vệ nơi lưu, rotate và xử lý sự cố lộ secret.

HTTPS giải quyết **bảo mật kênh truyền**, còn kiểm soát log/proxy/tool history giải quyết **nguy cơ sau khi credential được giải mã hoặc nhập vào công cụ**. Bật HTTPS mà vẫn log nguyên header chưa an toàn.

Mục tiêu: hiểu RFC 7617, cấu hình HTTPS trực tiếp cho Spring Boot WebFlux với PKCS12, thực hành `curl` có xác minh certificate, phân biệt HTTPS redirect/HSTS/TLS termination, thực hiện logging redaction và kiểm thử các đường lộ thường gặp. Ví dụ hướng đến **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**, dùng tài khoản thử không có giá trị ngoài localhost.

## 2. Basic header thực chất chứa gì?

Mẫu từ RFC 7617:

```http
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

Đây là **credential minh họa công khai**, không phải một mật khẩu thật. Chuỗi Base64 này giải mã ra:

```text
Aladdin:open sesame
```

Luồng giao thức:

```text
Client có username/password
         |
         v
Ghép username + ":" + password
         |
         v
Base64 encode chuỗi byte
         |
         v
Authorization: Basic <giá-trị-Base64>
         |
         v
Gửi request HTTP đến server
         |
         v
Server giải mã -> tra user -> xác minh mật khẩu
```

Base64 chỉ đổi cách biểu diễn, **không cần khóa giải mã**. Có HTTPS thì phần HTTP header được mã hóa **trên kết nối TLS**, không phải Basic token tự biến thành ciphertext. Khi HTTP Basic được gửi qua kết nối HTTP không mã hóa, kẻ quan sát được packet có thể lấy username và password rồi replay ở request khác.

Các điểm dễ hiểu sai:

- `WWW-Authenticate: Basic ...` là challenge thường được server trả cùng `401 Unauthorized`; challenge không mã hóa thông tin đăng nhập.
- Client thường gửi lại `Authorization` trên những request cần xác thực trong scope Basic; không coi đây là credential sử dụng một lần.
- `401` thường là chưa có thông tin xác thực hợp lệ; `403` là user đã được xác thực nhưng không đủ quyền (hoặc gặp chính sách chặn khác như CSRF).
- Username/password ở phía client là **credential rõ trước khi gửi**; server thường chỉ giữ password hash trong `UserDetails` và dùng `PasswordEncoder.matches(...)`. Hashing trên server **không thay thế** yêu cầu HTTPS trên đường truyền.
- Không log “Basic token” với lý do nó đã Base64; token đó tương đương một bản chứa password có thể khôi phục.

### HTTP và HTTPS: phân biệt cơ bản

```text
HTTP:
Client -- request rõ gồm Authorization --> Server
        (trung gian có thể đọc/chỉnh sửa)

HTTPS:
Client -- phiên TLS được xác minh --> Server
        (dữ liệu HTTP được bảo vệ trên kết nối đó)
```

HTTPS/TLS phù hợp tạo tính bí mật, toàn vẹn và xác thực server **khi client kiểm tra certificate và hostname đúng**. Nếu client tắt kiểm tra certificate, kẻ giả mạo server có thể giải mã request ở đầu kết nối giả mạo dù URL trông như HTTPS.

## 3. Mã hóa đoạn truyền nào? Threat model

### 3.1. Spring Boot tự kết thúc TLS

```text
Browser/curl -- HTTPS/TLS --> Spring Boot WebFlux/Netty
                             (TLS kết thúc tại ứng dụng)
```

Trên đoạn truyền này, các thiết bị chỉ quan sát network traffic không đọc được HTTP header nếu TLS được triển khai đúng. Sau khi Netty giải mã request, ứng dụng vẫn có quyền truy cập `Authorization` và các thông tin khác để xử lý authentication.

### 3.2. TLS termination tại reverse proxy

```text
Client -- TLS 1 --> Reverse proxy -- TLS 2 --> WebFlux
                     |                         |
               TLS giải mã                   App giải mã
                     |
               Access log / WAF / tracing
```

Đây là mô hình có TLS cho cả hai chặng. Nếu proxy nhận HTTPS rồi chuyển tiếp **HTTP** đến backend:

```text
Client -- TLS --> Proxy -- HTTP nội bộ --> App
```

thì `Authorization` ở dạng rõ trên chặng backend. Không thể mặc định gọi đó là TLS end-to-end. Hệ thống cần kiểm tra ranh giới tin cậy, quyền capture mạng, network segmentation, sidecars, policies và yêu cầu tuân thủ; với tài khoản nhạy cảm, thường ưu tiên mã hóa chặng backend hoặc kênh được bảo vệ tương đương.

### 3.3. HTTPS không bảo vệ những gì?

TLS **không tự ngăn**:
- Reverse proxy, gateway, WAF hoặc load balancer đọc header sau khi giải mã.
- Ứng dụng WebFlux, WebFilter, exception handler hoặc HTTP library log toàn bộ headers.
- APM agent/exporter lưu `Authorization` vào span attributes hay error reports.
- IDE/API client lưu request history, collection/environment export.
- Shell history, terminal scrollback, process arguments, CI runner hoặc script output giữ password đã gõ.
- Người dùng đưa credential vào query/path/URL userinfo để nó xuất hiện trong log hoặc browser history.

Điểm quan trọng: HTTP header `Authorization` **thường không nằm trong browser URL history bình thường**; rủi ro lịch sử phát sinh khi bạn **đặt mật khẩu trong URL**, command history, network trace/HAR hoặc lịch sử request của công cụ.

### 3.4. Bảng nguy cơ theo vị trí

| Vị trí | Hành vi gây lộ | Hướng khắc phục |
| --- | --- | --- |
| HTTP không TLS | Nghe lén được Basic header | HTTPS-first, chứng chỉ được tin và hostname đúng |
| Client `curl -k` | Bỏ qua xác thực máy chủ | Dùng CA/certificate phù hợp, không tắt verify |
| Proxy terminate TLS | Log nguyên `Authorization` | Log allowlist, loại header nhạy cảm tại nguồn |
| Chặng proxy → backend | HTTP rõ trong vùng không bảo vệ | Bật TLS/mTLS hoặc bảo vệ chặng theo threat model |
| Spring WebFilter | `log.debug("headers={}", headers)` | Không log toàn bộ request/headers |
| APM/tracing | Bản ghi span chứa token | Redact/drop attribute trước export |
| Terminal/curl | `-u user:password` trong câu lệnh | `--user user` để curl hỏi password |
| Browser/API URL | `user:pass@host` hoặc `?password=...` | Không đặt credentials vào URL |
| API client/collection | Export workspace chứa secret | Private variables/secret store và review export |
| CI/CD | `set -x`, echoed env, build artifact | Mask secret, tắt xtrace, hạn chế quyền và retention |
| Log aggregator | Log ứng dụng đã bị thu và chia sẻ rộng | Chặn từ nguồn, RBAC, rotation và xử lý incident |

## 4. Quy tắc HTTPS cần nhớ

Một triển khai HTTPS phù hợp có các lớp:

1. **Server certificate hợp lệ và được tin cậy.** Tên miền truy cập phải xuất hiện trong certificate SAN; chain CA phù hợp, thời hạn và cấu hình TLS đúng.
2. **Client kiểm tra chứng chỉ.** Không dùng trust-all client, `--insecure` hoặc bỏ hostname verification để che lỗi.
3. **Dùng HTTPS ngay từ request đầu.** HTTP redirect có thể đến quá muộn nếu request HTTP đầu tiên đã mang Basic header.
4. **Bảo vệ mọi chặng.** Xác định proxy nào kết thúc TLS, metadata nào được tin, và chặng backend có mã hóa hay bảo vệ tương đương không.
5. **Bảo vệ secret tại nơi dùng.** `Authorization` có thể lộ sau TLS termination nếu log/trace sai.
6. **Bổ sung HSTS cho browser** khi phù hợp; HSTS không thay thế HTTPS, certificate validation hoặc thiết lập cho API client máy–máy.
7. **Cấu hình logging và retention an toàn.** Không nên thu credential rồi chỉ che trên dashboard; ưu tiên loại bỏ trước khi log/export.

Không đồng nhất các tính năng: mã hóa mật khẩu bằng BCrypt bảo vệ **password at rest**; HTTPS bảo vệ **HTTP in transit**; redaction bảo vệ **observability/logs**. Một lớp không thay thế hai lớp còn lại.

## 5. Ví dụ hoàn chỉnh: Spring Boot WebFlux phục vụ HTTP Basic qua TLS

Dự án demo sau sử dụng Spring Boot **3.3.5** với Gradle và Java 17+. Trên máy local, server lắng nghe HTTPS port **8443** bằng keystore PKCS12. Password người dùng mẫu và password keystore được lấy từ biến môi trường runtime. Mọi secret trong ví dụ đều **chỉ dành cho học tập**; trong production phải dùng secret manager và certificate được quản trị đúng.

Cấu trúc:

```text
basic-https-demo/
├── settings.gradle
├── build.gradle
├── .gitignore
├── local-tls.p12                 # Tạo cục bộ, không commit
├── localhost.crt                 # Certificate public để curl kiểm tra
└── src/
    ├── main/
    │   ├── java/dev/example/basichttps/
    │   │   ├── BasicHttpsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/dev/example/basichttps/
        └── BasicSecurityTests.java
```

Hai file TLS chỉ có sau bước tạo certificate bằng `keytool` ở phần 6. `local-tls.p12` chứa **private key**, không chia sẻ hoặc commit vào Git.

`settings.gradle`:

```groovy
rootProject.name = 'basic-https-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` vào demo WebFlux thuần, bởi khi cả hai starter có mặt Spring Boot thường chọn Servlet/MVC.

`.gitignore`:

```gitignore
.gradle/
build/
local-tls.p12
*.key
.env
```

Trong ứng dụng thật, bảo vệ thêm file secret khác, truststore riêng, config local và artifacts theo tổ chức. Public certificate không phải secret, nhưng không nhầm `localhost.crt` với file `local-tls.p12` có private key.

### 5.1. Class khởi động

`src/main/java/dev/example/basichttps/BasicHttpsApplication.java`:

```java
package dev.example.basichttps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicHttpsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicHttpsApplication.class, args);
    }
}
```

### 5.2. HTTP Basic, user mẫu và authorization

`src/main/java/dev/example/basichttps/SecurityConfig.java`:

```java
package dev.example.basichttps;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String demoPassword) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/me").hasRole("READER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

`MapReactiveUserDetailsService` giữ `UserDetails` trong bộ nhớ. `PasswordEncoder` tạo hash BCrypt từ mật khẩu thử khi khởi động; khi Basic gửi credential, Spring Security xác minh raw password với hash. `SecurityWebFilterChain` quyết định `/public` được truy cập công khai, `/me` yêu cầu role READER, các URL khác bị từ chối.

**Lưu ý:** `SecurityWebFilterChain` **không tự bật TLS**. TLS được cấu hình ở tầng embedded server bằng `server.ssl.*`. Ngược lại, bật TLS không tự bảo vệ một endpoint nếu authorization rule sai.

### 5.3. WebFlux controller

`src/main/java/dev/example/basichttps/DemoController.java`:

```java
package dev.example.basichttps;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<String> currentUser(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }
}
```

Controller trả `Mono<String>`, không `block()` và không `subscribe()`. Không trả ra password, password hash, `Authorization` hoặc `UserDetails` nguyên bản.

### 5.4. Cấu hình keystore và runtime secrets

`src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./local-tls.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-alias=localhost
server.ssl.key-store-password=${HTTPS_KEYSTORE_PASSWORD}

demo.user.password=${DEMO_PASSWORD}

logging.level.org.springframework.security=INFO
```

Giải thích:
- `server.port=8443`: lắng nghe HTTPS trực tiếp.
- `server.ssl.key-store=file:./local-tls.p12`: file keystore ở working directory của tiến trình; chạy demo từ thư mục gốc.
- `server.ssl.key-store-type=PKCS12` và `key-alias=localhost` phải khớp với `keytool`.
- Hai secret được inject từ môi trường. Không viết password rõ vào source control.
- Spring Security logging ở INFO giúp tránh debug tràn lan nhưng **không đảm bảo** log ở proxy, custom filter hoặc APM đã được redact.
- Cấu hình SSL trong Spring Boot **không tự mở một HTTP listener 8080** song song. Chỉ có cổng HTTPS 8443; `http://localhost:8443` không phải HTTP connector hợp lệ.

Trong production, dùng certificate CA hợp lệ/SSL bundle hoặc TLS termination ở gateway; không đóng gói private key local vào public JAR.

## 6. Tạo chứng chỉ local và khởi động demo

### 6.1. Tạo PKCS12 với `keytool`

Dùng `keytool` từ JDK 17+, ở thư mục `basic-https-demo`:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore local-tls.p12 \
  -dname "CN=localhost, OU=Learning, O=Demo, L=Local, ST=Local, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Không truyền `-storepass ...` để `keytool` **hỏi password tương tác**. Điều này tránh đưa giá trị đó vào history/process arguments. Chọn mật khẩu thử riêng cho keystore local. Certificate có SAN cho localhost, nên client có thể kiểm tra hostname. Chứng chỉ **self-signed** không được public CA tin sẵn, phù hợp trong môi trường thử có kiểm soát.

Xuất chứng chỉ public để truyền cho curl:

```bash
keytool -exportcert \
  -rfc \
  -alias localhost \
  -storetype PKCS12 \
  -keystore local-tls.p12 \
  -file localhost.crt
```

`localhost.crt` là chứng chỉ public; `local-tls.p12` chứa private key. Không gửi `local-tls.p12` trong email/chat hoặc commit. Trên PowerShell Windows, `\` không phải cú pháp xuống dòng Bash: dùng mỗi lệnh `keytool` trên một dòng hoặc ngắt dòng theo cú pháp PowerShell.

### 6.2. Nhập password mà không gõ rõ trên dòng lệnh

Với Bash:

```bash
read -r -s -p "Keystore password: " HTTPS_KEYSTORE_PASSWORD
printf '\n'
export HTTPS_KEYSTORE_PASSWORD

read -r -s -p "Demo reader password: " DEMO_PASSWORD
printf '\n'
export DEMO_PASSWORD

gradle bootRun
```

`read -s` không echo ký tự vào terminal và giá trị không xuất hiện trong lệnh `gradle`. Tuy nhiên secret vẫn nằm trong **environment và memory** của process; đây chỉ là giải pháp local demo, không phải secret vault.

Trên Windows PowerShell 5.1+ có thể dùng:

```powershell
$secureStore = Read-Host "Keystore password" -AsSecureString
$secureDemo = Read-Host "Demo reader password" -AsSecureString

$env:HTTPS_KEYSTORE_PASSWORD =
    [System.Net.NetworkCredential]::new("local", $secureStore).Password
$env:DEMO_PASSWORD =
    [System.Net.NetworkCredential]::new("local", $secureDemo).Password

gradle bootRun
```

Bước tạo `$env:...` chuyển secret thành chuỗi trong environment, nên giới hạn quyền đọc process và không bật debug dumps. Kết thúc demo, đóng terminal hoặc xóa environment vars tương ứng. Nếu project có Gradle Wrapper, dùng `./gradlew bootRun` (Bash) hoặc `gradlew.bat bootRun` (PowerShell/Windows).

### 6.3. Kiểm tra HTTPS mà không bỏ xác minh chứng chỉ

Với chứng chỉ đã xuất ra file `localhost.crt`:

```bash
# Public endpoint: vẫn chạy HTTPS và xác minh certificate.
curl --cacert localhost.crt -i https://localhost:8443/public

# Private endpoint chưa có credential.
curl --cacert localhost.crt -i https://localhost:8443/me

# Chỉ đưa username; curl sẽ hỏi password tương tác.
curl --cacert localhost.crt -i --user reader https://localhost:8443/me
```

`curl --user reader` (không có `:password`) hỏi password khi chạy tương tác, theo hướng dẫn curl. Nhập password đã dùng cho `DEMO_PASSWORD`. Trên PowerShell, nếu `curl` là alias `Invoke-WebRequest`, dùng `curl.exe` để gọi công cụ curl thật.

Kết quả dự kiến:

| Thử nghiệm | Kết quả dự kiến |
| --- | --- |
| `GET https://localhost:8443/public` | 200, body `public-ok` |
| `GET https://localhost:8443/me` không có Basic | 401, thông thường có `WWW-Authenticate` |
| `GET /me` với reader/đúng password | 200, body `user=reader` |
| `GET /me` với reader/sai password | 401 |
| `https://localhost:8443` khi client không trust self-signed cert | Client từ chối certificate validation |
| `http://localhost:8443` trên port chỉ nhận TLS | Không xử lý HTTP request bình thường; lỗi handshake/protocol |

Header chi tiết có thể thay đổi theo phiên bản, nhưng status/body chính có ý nghĩa như bảng. Đây là **kết quả kỳ vọng từ code**, chưa phải báo cáo đã thực thi chương trình.

**Không dùng `curl -k`, `--insecure`, HTTP client trust-all hoặc bỏ hostname validation** để coi kết nối thành công. Chúng làm hỏng mục tiêu kiểm thử TLS và có thể chấp nhận server giả mạo.

### 6.4. Quan sát HSTS trên HTTPS

```bash
curl --cacert localhost.crt -i https://localhost:8443/public
```

Trong cấu hình Spring Security WebFlux thông thường, header `Strict-Transport-Security` được thêm vào response qua HTTPS. Hãy kiểm tra response thực tế, không mặc định mọi cấu hình đều giống nhau. HSTS yêu cầu browser đã **tin và ghi nhớ** policy ưu tiên HTTPS cho host trong thời gian chỉ định; nó không mã hóa request, không bảo vệ mọi non-browser HTTP client và không cứu credential từng đi qua HTTP trước khi browser có policy.

## 7. HTTP redirect và HSTS không thay HTTPS-first

Spring Security reactive hỗ trợ:

```java
// Tùy chọn bên trong cấu hình ServerHttpSecurity:
http.redirectToHttps(Customizer.withDefaults());
```

Đây là **đoạn minh họa API**, không phải toàn bộ chương trình. `redirectToHttps` chỉ có hiệu lực với request HTTP **đến được security filters**. Ví dụ direct TLS port 8443 không có HTTP listener; thêm redirect vào chain **không tự tạo** listener 8080 hoặc 80. Trong ứng dụng sau reverse proxy, thường để ingress/gateway redirect HTTP sang HTTPS và chuyển metadata scheme đáng tin cho backend.

Vì sao redirect chưa đủ? Nếu client đã gửi:

```http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

qua HTTP rõ, header có thể bị nghe lén **trước** khi server trả redirect 301/302/307/308. Do đó:
- Client phải bắt đầu bằng `https://` trước khi gửi Basic.
- Cấu hình SDK và tài liệu dùng HTTPS endpoint; không gửi Basic đến HTTP URL để “chờ redirect”.
- HSTS giảm nhầm lẫn cho browser đã học chính sách hoặc thuộc preload phù hợp, nhưng không thay yêu cầu client HTTPS-first.
- Nếu có port HTTP, nên chỉ phục vụ redirect mà không yêu cầu/nhận credential cho chức năng nhạy cảm.
- Kiểm tra client xử lý redirect sang host khác; không giả định `Authorization` luôn được giữ hoặc luôn được xóa trong mọi công cụ.

Không bật HSTS `includeSubDomains` hoặc preload nếu subdomains chưa hỗ trợ HTTPS đầy đủ; policy quá rộng có thể gây sự cố cho dịch vụ hợp lệ.

## 8. Reverse proxy, Forwarded headers và ranh giới tin cậy

### 8.1. TLS termination

Một gateway terminate HTTPS rồi forward đến WebFlux có thể đọc `Authorization` trong bộ nhớ và log request. Cần kiểm tra đồng thời:
- TLS client → proxy, certificate do client kiểm tra.
- Proxy → WebFlux là TLS, mTLS hay HTTP? Nếu HTTP thì mạng nào được phép quan sát và ai có quyền truy cập?
- Log formats của ingress, gateway, WAF, service mesh và load balancer.
- APM/tracing cấu hình capture headers/HTTP bodies ra sao.
- Proxy có gửi `Authorization` tới backend đúng phạm vi không; có filter/route nào forward ngoài ý định không.
- Chính sách redirect, host allowlist và request ID do proxy tạo.

### 8.2. `X-Forwarded-Proto` và `Forwarded`

Khi proxy terminate TLS, backend có thể thấy kết nối HTTP. Các header như `Forwarded` hoặc `X-Forwarded-Proto` giúp truyền thông tin về scheme ở phía client để ứng dụng xây redirect/URL đúng. Spring Boot có tùy chọn:

```properties
# Chỉ áp dụng khi proxy đáng tin cậy kiểm soát toàn bộ header.
server.forward-headers-strategy=framework
```

Chỉ bật trong kiến trúc đã đảm bảo **proxy loại bỏ header client gửi vào và tự tạo lại metadata**. Nếu client ngoài internet có thể tự gửi `X-Forwarded-Proto: https` và app tin vô điều kiện, logic HTTPS redirect hoặc security diagnostics có thể sai. Cấu hình property không tạo TLS cho đoạn proxy → backend và không bảo vệ `Authorization` trong log.

Nếu thấy redirect loop, absolute URL sai scheme hoặc HSTS không như kỳ vọng khi có proxy, kiểm tra thứ tự TLS termination, trusted proxy headers và port mapping; không sửa bằng cách tắt kiểm tra TLS.

## 9. Không để lộ Basic credential trong application log và APM

Trong WebFlux, header có thể bị ghi bởi `WebFilter`, exception handler, log middleware, tracing agent, HTTP client logging hoặc cấu hình DEBUG/TRACE.

Ví dụ **sai** (chỉ minh họa anti-pattern, không đặt vào ứng dụng):

```java
// Sai: log toàn bộ headers có thể chứa Authorization.
log.debug("headers: {}", exchange.getRequest().getHeaders());
```

`exchange` là `ServerWebExchange`, `log` là logger giả định đã khai báo trong lớp. Không log nguyên `Authentication`, `Authorization`, `HttpHeaders`, raw request, stacktrace kèm raw headers hoặc request dump.

### Cách tốt: log cho phép theo danh mục

Chỉ lưu thông tin có mục đích và được đánh giá an toàn. Ví dụ code độc lập trong một `WebFilter` đã khai báo logger:

```java
// Fragment minh họa; ở class có WebFilter và Logger.
log.info("http request method={} routeTag={}",
        exchange.getRequest().getMethod(),
        "basic-demo");
```

`routeTag` là giá trị cố định do server xác định, không phải query/path do client điền. Ngoài ra có thể lưu response status, request ID đã chuẩn hóa và elapsed time khi thực sự cần cho vận hành. Đừng tự cho rằng path an toàn nếu ứng dụng cho phép ID nhạy cảm hoặc secret xuất hiện trong path.

### Những trường cần loại khỏi logs/trace

- `Authorization` và `Proxy-Authorization`, kể cả biến thể chữ hoa/thường.
- `Cookie`/`Set-Cookie` chứa session hoặc access token.
- Custom API key headers, bearer/refresh tokens, client secrets.
- Body/query chứa password, OTP, recovery code hoặc secret dữ liệu nhạy cảm.
- Header/tracing tags có thể mang các thông tin trên sau khi được biến đổi Base64/URL encoding.

OWASP Logging Cheat Sheet khuyến nghị loại, che hoặc bảo vệ thông tin xác thực, tokens và dữ liệu cá nhân nhạy cảm. **Redact ở nơi sinh log/thu trace**, trước khi export; che trong dashboard sau khi dữ liệu đã truyền đến log collector có thể quá muộn.

### Kiểm soát nơi lưu log

- Cấp quyền đọc log/trace theo vai trò; tách production và development.
- Giới hạn retention, export, backup, quyền gửi support và audit người truy cập log.
- Cấu hình proxy/access logging độc lập với Spring Security logging.
- Chỉ lưu sự kiện `LOGIN_FAILURE`, `LOGIN_SUCCESS`, mã lỗi tổng quát, timestamp, route/trace ID và identifier đã giảm thiểu theo policy; không ghi password hay Basic token.
- Nếu cần bảo mật username tránh enumeration, không trả thông điệp phân biệt username sai với password sai cho client.

Đặt `logging.level.org.springframework.security=INFO` chỉ giảm log chi tiết của framework; không tự tắt ghi header ở custom code, proxy hoặc công cụ quan sát khác.

## 10. Rủi ro từ CLI, browser và lịch sử công cụ

### 10.1. Argument và shell history

Lệnh minh họa **không nên dùng với secret thật**:

```bash
# Anti-pattern: password giả xuất hiện ngay trên command line.
curl --user reader:example-password https://service.example.test/private
```

Mật khẩu có thể nằm trong shell history, process arguments trong một khoảng thời gian, terminal transcript/screenshot, CI output và thông tin hỗ trợ lỗi. Một số phiên bản curl có cố che argument trong process list nhưng vẫn có khoảng thời gian lộ; không xem đây là bảo đảm an toàn.

Cách tốt hơn khi thao tác tương tác:

```bash
curl --cacert localhost.crt --user reader https://localhost:8443/me
```

Khi chỉ có username, curl yêu cầu nhập password qua terminal, giúp tránh lộ ở dòng lệnh. Dẫu vậy, terminal/công cụ vẫn có nguy cơ thu dữ liệu nếu hệ thống bị xâm nhập. Không bật `--verbose`, `--trace` hoặc `--trace-ascii` khi dùng credential thật vì chúng có thể lưu dữ liệu request/headers trong output.

### 10.2. URL userinfo và query

Không gửi mật khẩu qua URL:

```text
https://reader:example-password@service.example.test/me
https://service.example.test/login?user=reader&password=example-password
```

Đây là các chuỗi **mật khẩu giả** để nhận biết lỗi. URL có thể xuất hiện trong browser history, bookmark, gateway access log, Referer trong những ngữ cảnh nhất định, analytics hoặc request history của API client. Không sử dụng query string làm kênh vận chuyển credential.

### 10.3. Postman/Insomnia/IDE

Các API client có thể giữ password trong request configuration, collection/workspace, environment exports, cloud sync, history và debugging screens. Dùng private/secret variables, tách local/test/production, không xuất hoặc gửi collection chứa password thực. Với file `.http` trong IDE, không commit header `Authorization` hoặc một Basic token thực vào Git.

### 10.4. CI/CD, secrets và environment

- Không echo secret hoặc dùng `set -x` khi script chạm password/API key.
- Không truyền password thành command-line argument, Gradle `-D...password=...`, URL hoặc string được in ra console.
- Nếu secret được nạp từ môi trường, kiểm soát quyền đọc process/CI job và xóa khỏi test artifacts.
- Environment variable không phải vault: process và những người có quyền thích hợp có thể đọc, nên dùng secret manager/secret mount cho production.
- Bảo vệ lịch sử command, trace output, log retention và quyền chia sẻ screenshot.

Chỉ sửa shell history không đủ nếu Postman, CI, APM hay proxy đã lưu request headers. Cần kiểm kê **từng nơi có thể thu hoặc sao chép** secret.

## 11. Kiểm thử bằng WebTestClient: tách authentication với TLS

Có thể kiểm thử Spring Security WebFlux bằng `WebTestClient`. Tuy nhiên test dùng HTTP/Mock **chỉ xác minh hành vi authentication/authorization**, không chứng minh ứng dụng production chạy HTTPS hoặc cert đúng. Kiểm tra TLS phải dùng `curl --cacert` hay TLS client xác minh certificate như phần 6.

`src/test/java/dev/example/basichttps/BasicSecurityTests.java`:

```java
package dev.example.basichttps;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "server.ssl.enabled=false",
                "server.ssl.key-store-password=unused-test-value",
                "demo.user.password=test-only-reader-password"
        }
)
@AutoConfigureWebTestClient
class BasicSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessible() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteRequiresLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicCredentialsWork() {
        client.get().uri("/me")
                .headers(h ->
                        h.setBasicAuth("reader", "test-only-reader-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDenied() {
        client.get().uri("/unknown")
                .headers(h ->
                        h.setBasicAuth("reader", "test-only-reader-password"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** năm test thành công nếu mã và dependencies đúng như mẫu. Đây là kết quả dự kiến qua logic security, **không phải tuyên bố đã chạy Gradle**. Các chuỗi password trong test chỉ có giá trị giả, không phải credentials production.

Đặc biệt, `server.ssl.enabled=false` là **cấu hình chỉ dành cho test authentication trên cổng HTTP ngẫu nhiên**, không phải cấu hình triển khai thực. Khi kiểm thử TLS, phải chạy main app với SSL bật và dùng HTTPS client. Đừng lấy status 200 của test HTTP làm bằng chứng rằng thông tin đăng nhập ngoài đời được mã hóa.

## 12. Checklist xác nhận bảo vệ end-to-end

| Kiểm thử | Kỳ vọng | Phạm vi |
| --- | --- | --- |
| HTTPS với certificate đúng | Client xác minh và gọi được | TLS, hostname/CA |
| HTTPS với certificate không được tin | Client từ chối | Xác minh server identity |
| HTTP vào cổng chỉ TLS | Không xử lý Basic request thông thường | Không vô tình mở HTTP connector |
| `GET /me` không credential | 401 | HTTP Basic |
| `GET /me` với đúng credential | 200, chỉ trả identity cần thiết | Authentication |
| `GET /me` với sai credential | 401 | Authentication failure |
| Spring app log | Không chứa password hoặc Authorization | Log redaction |
| Proxy/gateway/WAF logs | Không capture raw secret | Gateway configuration |
| APM/tracing spans | Không có Basic token trong attributes | Observability |
| CLI history/process arguments | Không có raw password | Công cụ client |
| HSTS trên response HTTPS | Đúng policy khi có cấu hình | Browser HTTPS preference |
| Proxy → backend | TLS hoặc mạng được bảo vệ đúng chính sách | Trust boundaries |
| Forwarded headers | Chỉ tin giá trị do proxy đáng tin cấp | Redirect, scheme recognition |

**Test log bằng giá trị giả có thể thu hồi:** tạo credential dùng riêng cho thử nghiệm, gửi request qua những tuyến cần kiểm tra, xác nhận ứng dụng/proxy/APM không lưu token rồi thu hồi credential thử. Không đặt mật khẩu production vào test để "xem có lộ không".

Nếu response có HSTS, kiểm tra scope và điều kiện phát trên HTTPS thật. Không bật `includeSubDomains` hoặc preload cho domain chưa có HTTPS đầy đủ. HSTS chỉ ảnh hưởng browser hỗ trợ đã nhận/trust policy; không tự bảo vệ công cụ máy–máy.

### HTTP Basic và CSRF

Một số browser có thể gửi lại Basic credentials trong phạm vi authentication đã ghi nhớ, nên **không mặc định tắt CSRF chỉ vì dùng Basic hoặc API**. Spring Security có CSRF protection mặc định phù hợp đối với phương thức thay đổi trạng thái; đánh giá mô hình client/browser và các nguy cơ CSRF trước khi điều chỉnh. CSRF và CORS không mã hóa Authorization header và không thay thế TLS.

## 13. Ứng phó khi Basic credential đã bị ghi lộ

Nếu thấy header `Authorization`, Base64 Basic token hoặc raw password trong logs, trace, CI artifact, Git, issue hoặc history:

1. **Ngăn lặp:** sửa/tắt nơi thu header nhạy cảm, tạm hạn chế các tuyến hoặc công cụ gây lộ.
2. **Thu hồi/rotate credential:** Basic chứa password có thể replay; coi credential đã lộ là không còn đáng tin, xử lý session/token liên quan theo thiết kế.
3. **Kiểm kê nơi chứa bản sao:** app log, proxy, log shipper, APM, backup, CI history, terminal, API client, support ticket, screenshots, Git history.
4. **Đánh giá tác động:** thời gian lộ, quyền của credential, ai có thể truy cập log và dấu hiệu sử dụng trái phép.
5. **Xử lý log/artefact theo quy trình:** redact/xóa các bản sao được phép, giữ chứng cứ cần thiết theo chính sách incident response, không tùy ý xóa dấu vết audit.
6. **Thử lại bằng credential thử mới:** kiểm chứng nơi thu dữ liệu đã được sửa trước khi đưa vào production.
7. **Cải tiến quy trình:** HTTPS-first, no-secrets-in-URL/CLI, redaction, RBAC logs, secret manager và đào tạo nhóm.

Xóa password khỏi commit hiện tại **không thu hồi** các bản sao ở Git history, forks, caches hoặc artifacts. Thay secret và kiểm soát toàn bộ nơi lưu mới là hành động chính.

## 14. Những lỗi thường gặp

| Sai lầm | Hậu quả | Sửa thế nào? |
| --- | --- | --- |
| Nghĩ Base64 của Basic là encrypted | Người thấy header giải mã được password | HTTPS + không log header |
| Chỉ có TLS ở gateway | Chặng tới app có thể còn HTTP rõ | Bảo vệ từng hop theo threat model |
| Dùng `curl -k` vì self-signed | Không xác minh danh tính server | `--cacert` hoặc CA hợp lệ |
| Gửi Basic qua HTTP rồi trông cậy redirect | Header đã có thể lộ trước 3xx | Gọi HTTPS từ đầu |
| Bật `redirectToHttps` mà không có HTTP listener | Không có gì nghe HTTP để redirect | Cấu hình listener/gateway riêng |
| Cấu hình SSL rồi tưởng có 8080 HTTP | Nhầm Spring Boot chỉ mở HTTPS port | Xác minh cổng và topology |
| Log `getHeaders()` ở DEBUG | Lộ Authorization vào app log | Chọn lọc fields trước khi ghi |
| Chỉ che password trên dashboard APM | Raw header có thể đã export ra collector | Drop/redact tại nguồn |
| Gõ `curl -u user:password` | Mật khẩu trong history/process | Chỉ đưa username, nhập password khi prompt |
| Đặt password vào URL/query | Lộ qua history, access logs, analytics | Không đặt secret ở URL |
| Tin mọi `X-Forwarded-Proto` | Client có thể tự giả scheme HTTPS | Chỉ trust headers do proxy kiểm soát |
| Test auth 200 và kết luận TLS đúng | Authorization khác transport security | Test certificate và TLS riêng |
| Tin HSTS bảo vệ request đầu tiên của mọi client | HSTS phụ thuộc browser và việc đã học policy | HTTPS-first, certificate validation |
| Tắt CSRF vì dùng Basic | Browser có thể tự gửi credential | Đánh giá CSRF theo client/threat model |
| Chỉ xóa secret khỏi code hiện tại | Git/history/log backup có thể còn | Rotate và quản lý bản sao |

## 15. Câu hỏi ôn tập

**Câu 1.** `Authorization: Basic ...` đã mã hóa mật khẩu chưa?  
**Trả lời:** Chưa. Đây là Base64 encoding, có thể giải mã trực tiếp.

**Câu 2.** HTTPS bảo vệ Basic credential khỏi application log hoặc proxy đã terminate TLS không?  
**Trả lời:** Không. Header ở dạng rõ sau TLS termination và có thể bị logger/agent thu thập.

**Câu 3.** Vì sao `curl --user reader` ít lộ trong shell history hơn `curl --user reader:password`?  
**Trả lời:** Nó yêu cầu nhập password tương tác và không chứa secret trong lệnh; vẫn phải bảo vệ công cụ và endpoint.

**Câu 4.** Có nên dùng `--insecure` để test certificate self-signed không?  
**Trả lời:** Không nếu muốn kiểm tra TLS đúng nghĩa. Dùng `--cacert` với certificate tin cậy cho demo.

**Câu 5.** Proxy terminate TLS rồi dùng HTTP cho backend thì request đã mã hóa cả đường chưa?  
**Trả lời:** Chưa. Chặng proxy → backend là HTTP rõ, cần bảo vệ theo chính sách.

**Câu 6.** HTTP redirect có cứu request Basic đã gửi trước đó bằng HTTP không?  
**Trả lời:** Không, credential có thể đã đi qua HTTP ở request đầu tiên.

**Câu 7.** `server.ssl.enabled=true` có tự tạo HTTP port 8080 cho redirect không?  
**Trả lời:** Không; ví dụ chỉ lắng HTTPS 8443.

**Câu 8.** Header HSTS có thay việc kiểm tra certificate không?  
**Trả lời:** Không. HSTS giúp browser ưu tiên HTTPS sau khi học policy phù hợp, không tự xác minh danh tính server.

**Câu 9.** Ngoài Authorization, những loại dữ liệu nào cần lọc khỏi logs?  
**Trả lời:** Proxy-Authorization, session cookies, API keys, bearer/refresh tokens, raw passwords, OTP và secret trong body/query.

**Câu 10.** Vì sao không thể chỉ giảm Spring Security logging xuống INFO là xong?  
**Trả lời:** Custom filters, proxy, ingress, APM, CI và client history vẫn có hệ thống log riêng.

**Câu 11.** Có password hash BCrypt trong `UserDetails` thì cần TLS nữa không?  
**Trả lời:** Vẫn cần, vì client gửi Basic raw credential trước khi Spring Security so hash.

**Câu 12.** Cần làm gì trước nếu phát hiện Basic credential trong CI artifact?  
**Trả lời:** Ngăn lặp, thu hồi/rotate credential, xác định bản sao và xử lý theo quy trình incident response.

### Bài tập

1. Tạo chứng chỉ localhost bằng `keytool`, khởi chạy demo ở 8443 và dùng `curl --cacert` để thử route `/public` và `/me`. Chỉ ghi lại status/body không nhạy cảm.
2. Thử một certificate khác: giải thích vì sao certificate verification thất bại. Không dùng `-k` để né lỗi.
3. Đăng nhập Basic bằng curl chỉ cung cấp username; kiểm tra command history test không có password.
4. Tạo một chuỗi password *giả* làm canary và kiểm tra logging/tracing trên môi trường thử; xác nhận header không bị lưu.
5. Vẽ sơ đồ client → proxy → app, đánh dấu các chặng TLS và những nơi cần redaction.
6. Xác minh browser/HSTS và proxy-forwarded scheme ở môi trường thử có tin cậy; giải thích vì sao không được tin X-Forwarded-Proto do client tự gửi.
7. Bổ sung test cho password sai và request không đăng nhập, nhưng vẫn phải test TLS độc lập.
8. Thiết kế checklist ứng phó nếu một token đã xuất hiện trong Git history hoặc CI logs: rotation, scope, log copies và bằng chứng.

## 16. Tài liệu đáng tin cậy

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): credential dạng Base64 và yêu cầu kênh an toàn.
- [Spring Security — HTTP trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html): HTTPS redirect, HSTS và proxy.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): HTTP Basic, `ServerHttpSecurity` và WebFilter.
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): keystore và cấu hình TLS server.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): cấu hình `server.ssl.*`, logging, proxy.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi vào log.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): yêu cầu triển khai HTTPS/TLS.
- [curl man page](https://curl.se/docs/manpage.html): `--user`, `--cacert` và các cờ tracing.

**Ghi nhớ:** HTTP Basic chỉ **Base64** username/password. Để bảo vệ, phải **gọi HTTPS/TLS đã xác minh certificate ngay từ đầu**, kiểm soát **từng chặng qua proxy**, **không log Authorization hoặc tokens**, và **không để password trong URL/command-line/history**. Redaction, TLS, quản lý secrets và phân quyền truy cập logs cùng tạo nên bảo vệ thực tế.