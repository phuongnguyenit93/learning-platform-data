# HSTS và yêu cầu triển khai HTTPS đúng cách

> **Chủ đề:** Spring Security – fundamentals → **Bảo vệ trình duyệt**. Bài học dành cho Java 17+, Spring Boot 3.x và Spring Security 6.x, tập trung vào **HTTP Strict Transport Security (HSTS)**, cách browser học và thực thi HTTPS-only, khác biệt với redirect HTTP → HTTPS, cấu hình Spring MVC/WebFlux, triển khai TLS sau reverse proxy, rủi ro `includeSubDomains`/`preload`, quy trình rollout và các phép kiểm thử thực tế.

## 1. HSTS bảo vệ vấn đề gì?

**HSTS** là cơ chế cho một host thông báo với trình duyệt: *“Trong một khoảng thời gian, mọi kết nối đến host này phải sử dụng HTTPS; nếu user mở HTTP URL, hãy nâng cấp sang HTTPS trước khi gửi request trên mạng.”*

Server gửi một HTTP response header trên kết nối **HTTPS đáng tin cậy**:

```http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Type: text/html; charset=utf-8
```

Sau khi nhận và chấp nhận header, browser ghi nhớ policy của host trong **31536000 giây** (365 ngày). Khi truy cập `http://app.example.com` mà host này đang thuộc policy, browser tự đổi thành `https://app.example.com`. Nếu có `includeSubDomains` trên một parent domain, policy còn áp cho những subdomain của parent.

**Ba điểm phải nhớ:**

1. HSTS là **chính sách hành vi browser**, không phải cấu hình TLS server. HSTS không phát hành certificate, không mã hóa request và không tạo HTTPS listener.
2. Header HSTS được browser tin cậy **khi nhận qua HTTPS với certificate hợp lệ**; gửi header trên HTTP không tạo policy được chấp nhận.
3. HSTS thường bảo vệ **các lần truy cập sau** khi browser đã học policy. Muốn có policy ngay từ lần đầu mà browser chưa truy cập host, cần một cơ chế như **HSTS preload**, nhưng preload có rủi ro vận hành và không nên bật tùy tiện.

Bật HSTS không có nghĩa ứng dụng đã triển khai HTTPS đúng. Chính sách có thể biến lỗi certificate, DNS hoặc một subdomain HTTP-only thành tình trạng browser **không truy cập được** cho tới khi HTTPS được sửa.

## 2. Vì sao HTTP → HTTPS redirect một mình chưa đủ?

Giả sử người dùng gõ `bank.example`, click một link `http://bank.example` hoặc browser/client thử HTTP. Nếu máy chủ trả:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://bank.example/
```

thì redirect có ích, nhưng **HTTP request và response đầu tiên** có thể bị kẻ tấn công trên đường truyền đọc hoặc sửa. Một attacker trên Wi-Fi không đáng tin có thể cố chặn redirect, giữ user trên HTTP hoặc chuyển họ tới một tên miền giả.

Một host đã được HSTS bảo vệ sẽ khiến browser **nâng cấp URL trước khi phát HTTP request**, giảm nguy cơ protocol downgrade/SSL stripping.

```text
CHƯA BIẾT HSTS:

Browser -> http://bank.example
          |   Request đầu có thể đi qua HTTP
          v
Server HTTP -> 308 Location: https://bank.example/
          |
          v
Browser -> HTTPS handshake + certificate check
          |
          v
Server HTTPS -> Strict-Transport-Security
          |
          v
Browser ghi nhớ policy cho các request sau

ĐÃ BIẾT HSTS:

User mở http://bank.example
          |
          v
Browser tự nâng cấp thành https://bank.example
          |
          v
HTTPS handshake + certificate check
          |
          v
HTTPS request tới host (không phát HTTP request đầu)
```

**Không nhầm:** HSTS không bảo vệ ngược thời gian request đầu tiên đã đi qua HTTP. Preload hoặc cơ chế browser HTTPS-first có thể giúp ở lần đầu, nhưng các cơ chế đó có điều kiện và không thay thế HTTPS server chuẩn.

## 3. Cú pháp `Strict-Transport-Security` và cách diễn giải

Một số mẫu header, dùng **riêng từng phương án**, không phát tất cả cùng lúc:

```http
Strict-Transport-Security: max-age=300
```

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

```http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

| Directive | Ý nghĩa | Lưu ý |
|---|---|---|
| `max-age=300` | Browser nhớ HTTPS-only trong 300 **giây** | Hữu ích khi thử nghiệm rollout |
| `max-age=31536000` | Thời hạn một năm | Rất khó quay lại HTTP trong thời gian browser còn nhớ |
| `includeSubDomains` | Áp policy cho mọi subdomain/nested subdomain | Có thể phá dịch vụ chưa có HTTPS trên subdomain |
| `preload` | Thể hiện ý định tham gia HSTS preload list | Không tự thêm domain vào browser preload list |
| `max-age=0` | Xóa policy do host đã học khi nhận qua HTTPS hợp lệ | Không có tác dụng nếu chỉ phát từ HTTP; không gỡ ngay policy parent/preload |

Browser cập nhật thời điểm hết hạn khi nhận header hợp lệ mới. Một host liên tục trả `max-age=31536000` có thể khiến expiration tiếp tục được kéo dài; không phải sau đúng một năm kể từ deploy là browser tự quên policy nếu user vẫn truy cập HTTPS hằng ngày.

**HSTS áp dụng theo hostname**, không theo đường dẫn `/login`, `/admin` hay `/api`. Đặt header trong một controller rồi nghĩ HSTS chỉ bảo vệ controller đó là sai mô hình. `includeSubDomains` từ `example.com` bao gồm `app.example.com`, `api.example.com`, `legacy.example.com`, `printer.internal.example.com` và nested subdomains, miễn host thực thuộc suffix domain.

### 3.1. Host cha, host con và phạm vi HSTS

| Host đã học HSTS | Header | Request tới | Có được parent policy bao phủ? |
|---|---|---|---|
| `example.com` | `max-age=300` | `example.com` | Có |
| `example.com` | `max-age=300` | `app.example.com` | Không (trừ policy riêng của app) |
| `example.com` | `max-age=300; includeSubDomains` | `app.example.com` | Có |
| `example.com` | `max-age=300; includeSubDomains` | `a.b.example.com` | Có |
| `app.example.com` | `max-age=300; includeSubDomains` | `example.com` | Không |
| `app.example.com` | `max-age=300; includeSubDomains` | `api.example.com` | Không |
| `example.com` | `max-age=300; includeSubDomains` | `example.com.attacker.net` | Không |

Chỉ chọn `includeSubDomains=true` trên **parent domain mà tổ chức kiểm soát toàn bộ dịch vụ liên quan**. Nó không quan tâm một subdomain được dùng cho UI, API, email gateway hay thiết bị nội bộ; browser cố dùng HTTPS với tất cả các host bị bao phủ.

### 3.2. Port và URL

HSTS không có phạm vi theo path hay theo một cổng ứng dụng tùy ý. Khi nâng cấp HTTP URL với cổng mặc định 80, HTTPS thường dùng cổng mặc định 443. Với URL có cổng không mặc định, cơ chế nâng cấp có thể giữ cổng đã chỉ định và chuyển sang HTTPS; nếu port đó chỉ hỗ trợ HTTP, client có thể gặp lỗi. Cần test các web service/console chạy trên cổng lạ.

### 3.3. IP literal và local development

HSTS được thiết kế cho DNS hostnames và browser, không nên lấy các thử nghiệm `http://127.0.0.1` hoặc IP literal làm cơ sở kết luận về production. Trong môi trường test, dùng domain riêng và certificate CA tin cậy nếu cần đánh giá HSTS thật. Một số browser có hành vi đặc biệt với localhost, nhưng không dựa vào ngoại lệ này để thiết kế public HTTPS.

## 4. Khi nào trình duyệt chấp nhận HSTS?

Browser chỉ nên học policy khi:

1. Response đến từ `https://`.
2. TLS handshake thành công và certificate chain được trust, hostname/SAN đúng, certificate còn hiệu lực.
3. Header `Strict-Transport-Security` hợp lệ và có `max-age`.
4. Browser hỗ trợ và ghi lại policy cho hostname.
5. Request trong tương lai đến host thuộc policy được nâng cấp trước khi gửi HTTP.

Header trên response HTTP bị browser bỏ qua:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://app.example.com/
Strict-Transport-Security: max-age=31536000
```

Trong ví dụ, **redirect vẫn có ích** nhưng HSTS header được đặt trên **HTTP** không làm browser học HSTS. Để phát policy, response `https://app.example.com/` phải trả header sau khi TLS đã thành công.

### 4.1. Certificate lỗi thì sao?

Nếu HSTS đã có hiệu lực mà certificate HTTPS hết hạn, sai SAN hoặc không được trust, browser thường không cho user bỏ qua cảnh báo TLS bằng cách thông thường. Đây là một phần quan trọng của anti-downgrade protection, nhưng cũng có thể gây **outage nghiêm trọng** nếu certificate renewal bị bỏ sót.

HSTS **không sửa** certificate chain, không bổ sung TLS listener và không vượt được certificate error. Do đó phải duy trì certificate issuance, monitoring, renewal, key rotation và khả năng restore HTTPS **trước khi đặt max-age dài**.

### 4.2. HSTS không ngăn mọi kiểu tấn công

HSTS không thay thế:

- HTTPS/TLS validation và certificate pinning/trust do browser quản lý.
- Cookie `Secure`, `HttpOnly`, `SameSite` và quản lý session.
- Chống XSS, CSP, output encoding và kiểm soát third-party scripts.
- Chống CSRF cho browser auto-attached credentials.
- Authentication, authorization, role/scope, tenant/owner checks.
- Chống phishing ở **domain giả khác**, ngay cả khi domain đó có certificate HTTPS hợp lệ.
- Quản lý token/secrets: không đưa bearer token vào log, URL, crash report.

## 5. Triển khai HTTPS thật trước khi bật HSTS

Có hai mô hình thường gặp:

**Mô hình A – TLS termination tại reverse proxy/CDN/ingress:**

```text
Browser --HTTPS:443--> Nginx / Ingress / Load Balancer
                             |
                             | HTTP nội bộ hoặc mTLS
                             v
                         Spring Boot :8080
```

**Mô hình B – Spring Boot nhận HTTPS trực tiếp:**

```text
Browser --HTTPS:443/8443--> Embedded Tomcat/Jetty/Netty
                             |
                             v
                         Spring application
```

Cả hai mô hình đều có thể dùng HSTS. Điều quan trọng là **HTTPS public-facing phải hoạt động đúng**, proxy headers/trust đúng và HSTS được phát từ một nơi có chủ sở hữu chính sách rõ ràng.

### 5.1. Yêu cầu tối thiểu cho TLS/HTTPS

| Thành phần | Kiểm tra | Nếu sai |
|---|---|---|
| DNS/hostname | URL public trỏ tới edge/server đúng | Client tới nhầm host hoặc bị redirect sai |
| Certificate SAN | Certificate chứa đúng tên host | Browser cảnh báo tên miền sai |
| Trust chain | CA/intermediate chain hợp lệ | Browser không tin certificate |
| Thời hạn | Certificate chưa hết hạn, tự động gia hạn | HSTS host có thể bị khóa truy cập |
| TLS versions | TLS 1.2/1.3 theo policy hiện hành, không dùng protocol yếu | Downgrade, mất tương thích, tăng rủi ro |
| Private key | Lưu trong secret store/volume giới hạn quyền | Lộ khóa, giả mạo server |
| SNI | Edge phục vụ đúng cert cho từng host | Cert sai khi có nhiều virtual hosts |
| Redirect | HTTP → HTTPS cùng host/đường dẫn hợp lý, không loop | Browser không tới được HTTPS |
| Mixed content | JS/API/assets/websocket dùng HTTPS/WSS | Browser chặn request hoặc giảm an toàn |
| Proxy headers | Scheme/host/port public được thể hiện đúng | App nhận sai `isSecure`, redirect/cookie/HSTS |
| Giám sát | Alert expiry/handshake/errors/redirect loops | Sự cố kéo dài khi HSTS còn hiệu lực |

TLS phải phục vụ tất cả routes quan trọng, bao gồm login, API, OAuth callback, static assets và các HTTPS redirects. HSTS không được dùng để che giấu việc các URL còn HTTP.

### 5.2. HTTP redirect: chọn 301 hay 308?

HTTP listener cổng 80 nên chuyển về HTTPS thay vì tiếp tục xử lý sensitive data. Redirect 301 hoặc 308 thường được sử dụng; `307`/`308` bảo toàn HTTP method và body theo semantics hiện đại, còn 301/302 có hành vi lịch sử có thể chuyển POST thành GET.

Không cho user gửi mật khẩu/`Authorization` qua HTTP rồi mới redirect. Với browser có HSTS, request HTTP được upgrade trước khi ra mạng; với client chưa có HSTS, cần giáo dục client dùng HTTPS URL từ đầu, không trông chờ redirect bảo vệ credential trên đường truyền.

## 6. Ví dụ Nginx đứng trước ứng dụng Spring Boot

Cấu hình minh họa, không phải bản Nginx production hoàn chỉnh:

```nginx
server {
    listen 80;
    server_name app.example.com;

    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/tls/fullchain.pem;
    ssl_certificate_key /etc/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }
}
```

Cần bổ sung vận hành thật: TLS ciphers/versions, HTTP/2/HTTP/3 nếu cần, mTLS nội bộ khi phù hợp, rate limits, timeouts, error pages, log redaction, certificate automation và access controls. File private key **không được commit vào Git**.

HSTS nên có **một chủ sở hữu**:

- **Spring Security** phát HSTS trên HTTPS responses và Nginx chuyển tiếp header đó; hoặc
- **Nginx/CDN/ingress** phát HSTS trên HTTPS responses và Spring được cấu hình không phát một policy xung đột.

Nếu edge sở hữu HSTS, có thể đặt trong HTTPS `server` block:

```nginx
# Chỉ đặt trong HTTPS server block sau khi đã kiểm tra TLS.
add_header Strict-Transport-Security "max-age=300" always;
```

`always` giúp header có mặt trên nhiều response status kể cả lỗi, nhưng phải kiểm tra cấu hình inheritance/location/proxy thực tế. **Không phát HSTS trên HTTP port 80 để mong browser chấp nhận.** Không để Nginx và Spring phát hai giá trị `max-age` khác nhau, gây khó dự đoán và khó rollback.

## 7. Reverse proxy và `X-Forwarded-Proto`: điểm rất dễ sai

Browser dùng HTTPS tới proxy, nhưng proxy có thể dùng HTTP tới Spring Boot backend. Trong Servlet, nếu framework chỉ nhìn socket backend, `request.isSecure()` có thể là `false`. Vì **HstsHeaderWriter** của Spring Security mặc định dựa vào `ServletRequest.isSecure()` để quyết định phát header, response HTTPS từ phía browser có thể **không có HSTS**.

Ngoài HSTS, sai scheme còn dẫn tới:

- Link và redirect `Location` bị tạo thành `http://`.
- Form login/OIDC callback dựng sai redirect URI, loop HTTP/HTTPS.
- Logic phát cookie `Secure` hoặc các tính năng phụ thuộc scheme hoạt động không như mong muốn.
- Ứng dụng hiểu sai hostname/cổng public.

Spring Boot có cấu hình forwarded headers:

```yaml
# application.yml khi đứng sau reverse proxy ĐƯỢC TIN CẬY
server:
  forward-headers-strategy: framework
```

Một phương án khác là `server.forward-headers-strategy: native` để container xử lý các forwarded headers hỗ trợ. Chọn theo topology, web server, cloud environment và tài liệu Spring Boot hiện hành.

**Bảo mật quan trọng:** Không tin `Forwarded`/`X-Forwarded-*` do client internet tự gửi. Nginx/ingress phải **strip hoặc overwrite** những header này ở trust boundary, giới hạn quyền kết nối trực tiếp vào backend và chỉ dùng thông tin từ proxy đáng tin. Nếu attacker tự đặt `X-Forwarded-Proto: https` hoặc `X-Forwarded-Host`, link generation, redirect và một số security behaviors có thể bị điều khiển.

Khi dùng Tomcat và terminate SSL ở proxy, tài liệu Spring Boot cũng lưu ý `server.tomcat.redirect-context-root=false` có thể cần thiết để forwarded protocol được áp dụng trước khi redirect context root.

**Không nên “sửa” thiếu HSTS bằng cách phát header lên mọi HTTP request do Spring nhìn thấy**. Hãy xác minh đường HTTPS công khai và sửa scheme/edge ownership đúng, tránh làm lẫn HTTP và HTTPS ở tầng bảo mật.

## 8. HSTS trong Spring Security Servlet: hành vi mặc định

Theo tài liệu Spring Security 6.x, bộ security response headers mặc định có:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Được thêm **chỉ khi request được xem là secure/HTTPS**. Bộ writer Servlet mặc định:

- `max-age`: một năm.
- `includeSubDomains`: `true`.
- `preload`: `false`.

Đây là mặc định an toàn trong nhiều môi trường **đã triển khai HTTPS hoàn chỉnh**, nhưng có thể không phù hợp khi ứng dụng nằm trên parent domain còn subdomain cũ chạy HTTP. Khi triển khai HSTS lần đầu, hãy quyết định policy có chủ ý thay vì mặc nhiên chấp nhận default dài hạn.

### 8.1. Cấu hình Servlet cho giai đoạn thí điểm

Đặt class `HstsSecurityConfig.java` trong ứng dụng Spring Boot MVC với `spring-boot-starter-web` và `spring-boot-starter-security`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HstsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(300)
                    .includeSubDomains(false)
                    .preload(false)
                )
            );

        return http.build();
    }
}
```

**Giải thích:**

- `.httpStrictTransportSecurity(...)` là DSL HSTS của `HttpSecurity` Servlet.
- `maxAgeInSeconds(300)` = 5 phút, phù hợp với pilot nhỏ. Không coi đây là policy production vĩnh viễn.
- `includeSubDomains(false)` chỉ bao phủ host, tránh vô tình tác động mọi subdomain ở giai đoạn chưa kiểm tra.
- `preload(false)` không yêu cầu thêm domain vào preload list.
- `httpBasic` chỉ là cơ chế authentication minh họa, **không bắt buộc** để HSTS hoạt động. Basic với browser có thể chịu CSRF và cần HTTPS.
- HSTS độc lập với `authenticated()`, `hasRole` và các rule service-level authorization; có HSTS không có nghĩa dữ liệu đã được phân quyền.

Nếu đã đủ điều kiện bảo vệ parent và tất cả subdomain trong một năm, có thể thay policy bằng:

```java
// Trích đoạn bên trong HttpSecurity config:
.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
        .preload(false)
    )
)
```

**Không thêm `preload(true)` theo quán tính.** Quyết định preload cần DNS/TLS owner phê duyệt, vì hậu quả áp dụng toàn domain và rollback có thể kéo dài.

### 8.2. Nhiều security filter chains

Nếu ứng dụng có nhiều `SecurityFilterChain` và `securityMatcher` theo path, phải đảm bảo những response cần HSTS thực sự đi qua chain áp header. HSTS là chính sách **hostname-wide**, không nên vô tình chỉ xuất hiện ở `/login` mà thiếu `/error`, static paths hoặc một chain riêng.

Khi Nginx/CDN sở hữu header, verify rằng lỗi/redirect HTTPS cũng nhận policy nhất quán và không bị các layer viết trùng. Khi Spring sở hữu header, verify filter chain và scheme tại runtime.

## 9. Demo Spring Boot MVC: mã và kiểm thử đầy đủ

Ví dụ sau dùng **Java 17+, Maven và Spring Boot 3.5.7**. Nó kiểm tra `HstsHeaderWriter` ở tầng Spring Security bằng `MockMvc`, **không thay thế TLS test**. Để chạy, tạo các file với đường dẫn tương ứng:

```text
hsts-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/hsts/
    │   ├── HstsDemoApplication.java
    │   ├── HstsSecurityConfig.java
    │   └── PingController.java
    └── test/java/com/example/hsts/
        └── HstsSecurityTests.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>hsts-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Tệp `HstsDemoApplication.java`:

```java
package com.example.hsts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HstsDemoApplication.class, args);
    }
}
```

Tệp `HstsSecurityConfig.java`:

```java
package com.example.hsts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HstsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(300)
                    .includeSubDomains(false)
                    .preload(false)
                )
            );
        return http.build();
    }
}
```

Tệp `PingController.java`:

```java
package com.example.hsts;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
```

Tệp `HstsSecurityTests.java`:

```java
package com.example.hsts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HstsSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void secureRequestGetsHstsHeader() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string("Strict-Transport-Security",
                containsString("max-age=300")));
    }

    @Test
    void insecureRequestDoesNotTeachHsts() throws Exception {
        mvc.perform(get("/public/ping").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }
}
```

Chạy kiểm thử:

```bash
mvn test
```

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

**Giới hạn của demo:** Boot local mặc định nhận HTTP ở `localhost:8080` nếu không cấu hình TLS; do đó `curl -i http://localhost:8080/public/ping` không thấy HSTS là điều bình thường. `MockMvc` `.secure(true)` chỉ giả lập thuộc tính secure của Servlet request, **không kiểm tra certificate, redirect, cipher suite, proxy hoặc browser enforcement**.

Những việc demo không làm: cấp certificate, cấu hình proxy, tạo người dùng production, thực hiện login workflow hoàn chỉnh hoặc thiết kế phân quyền chi tiết. Basic auth ở đây minh họa một route protected; với trình duyệt, Basic có thể cần CSRF defense theo mô hình tự gửi credentials.

## 10. Spring Boot trực tiếp phục vụ HTTPS với SSL bundle

Nếu Spring Boot embedded web server trực tiếp làm TLS endpoint, Spring Boot 3.x hỗ trợ SSL bundle với PEM/JKS/PKCS12. Ví dụ `application.yml`:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: "file:/etc/tls/fullchain.pem"
            private-key: "file:/etc/tls/privkey.pem"

server:
  port: 8443
  ssl:
    bundle: "webserver"
```

- `spring.ssl.bundle.pem.webserver` khai báo bộ certificate/private key dạng PEM.
- `server.ssl.bundle: "webserver"` áp dụng SSL bundle cho embedded web server.
- `server.port: 8443` chọn HTTPS port trong ví dụ. Trong production, ingress/proxy có thể expose 443 và forward/route tới port phù hợp.
- File certificate/key phải tồn tại, có SAN/trust chain phù hợp và được mount từ nơi quản lý bí mật an toàn; không hardcode private key trong YAML hoặc commit vào repository.
- Spring Boot không tự lấy/gia hạn Let's Encrypt certificate chỉ bằng cấu hình SSL bundle. Cần ACME/cert-manager/ingress automation và kiểm tra vòng đời chứng chỉ riêng.
- Cấu hình SSL bundle **không tự mở HTTP listener để redirect**. Nếu cần cả HTTP port 80 và HTTPS, dùng reverse proxy hoặc cách thêm connector riêng phù hợp với web server.

Đừng trộn `server.ssl.bundle` với các thuộc tính SSL discrete không tương thích như keystore options dưới `server.ssl.*`; theo tài liệu Spring Boot, một số thuộc tính phải cấu hình ở SSL bundle thay vì kết hợp lẫn.

### 10.1. Mixed content và absolute URLs

Nếu trang chính dùng HTTPS nhưng tải script, stylesheet hoặc API bằng `http://`, browser có thể chặn mixed content hoặc tạo những vấn đề bảo mật khác. Không trông chờ HSTS cho mọi third-party domain. Dùng `https://` hoặc `wss://` ở tài nguyên liên quan và kiểm tra:

- API base URL và WebSocket URLs.
- OAuth2/OIDC redirect_uri, logout URLs và callback URLs.
- CSS/fonts/images scripts được tải từ host ngoài.
- Absolute redirect/Location headers do backend tạo sau proxy.
- CDN endpoints và static asset domain được quản trị.
- CSP `upgrade-insecure-requests` có thể hỗ trợ chuyển một số URL nhưng không sửa certificate hoặc khả năng phục vụ HTTPS của đích.

## 11. HSTS trong Spring Security WebFlux

Với reactive WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`; API cấu hình HSTS khác Servlet về tên hàm/kiểu tham số:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHstsSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .hsts(hsts -> hsts
                    .maxAge(Duration.ofMinutes(5))
                    .includeSubdomains(false)
                    .preload(false)
                )
            )
            .build();
    }
}
```

Đây là Spring config cho **ứng dụng WebFlux riêng** dùng `spring-boot-starter-webflux` và `spring-boot-starter-security`. Không dùng nhầm `HttpSecurity`/`SecurityFilterChain` hoặc `includeSubDomains` (Servlet spelling) với `includeSubdomains` (Reactive spelling). Cả hai vẫn chịu nguyên tắc HSTS chỉ có ý nghĩa với **HTTPS response đáng tin**.

Nếu cần kiểm tra WebFlux, dùng `WebTestClient` và môi trường test reactive phù hợp; nếu cần xác nhận HTTPS thật, test trên endpoint chạy TLS/proxy thực tế chứ không chỉ mô phỏng security filter. Không ép reactive pipeline bằng `block()`/`subscribe()` thủ công chỉ để xử lý header.

## 12. HSTS preload: lợi ích và hậu quả

**HSTS preload list** là danh sách domain mà browser tích hợp sẵn như HTTPS-only. Khi domain đã được phân phối tới browser, browser có thể biết policy **trước lần truy cập đầu**.

Ví dụ header được dùng trong quá trình chuẩn bị preload:

```http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

**Thêm directive `preload` không khiến browser tự động preload.** Tổ chức phải đáp ứng yêu cầu kỹ thuật và nộp qua `https://hstspreload.org/`; nếu được chấp nhận, domain cần được đưa vào các bản phát hành browser liên quan. Điều này có thể mất thời gian và có hậu quả khó đảo ngược.

Những điều kiện quan trọng theo `hstspreload.org`:

1. Certificate TLS hợp lệ.
2. Nếu có HTTP listener ở port 80, redirect HTTP → HTTPS **trên cùng hostname**.
3. **Tất cả subdomains và nested subdomains**, kể cả internal host, phải hỗ trợ HTTPS hợp lệ.
4. HTTPS base domain gửi header có `max-age` ít nhất **31536000 giây**.
5. Header có `includeSubDomains` và `preload`.
6. Nếu HTTPS base domain redirect tiếp, redirect response HTTPS đó cũng phải có HSTS.
7. Cam kết tiếp tục đáp ứng yêu cầu về sau.

Một subdomain `legacy.example.com` hoặc `printer.corp.example.com` chưa có HTTPS có thể trở nên không truy cập được qua browser nếu parent `example.com` đã có HSTS preload với `includeSubDomains`. Cần audit cả các subdomain không public; không chỉ scan homepage chính.

**Hướng dẫn của dịch vụ preload nhấn mạnh HSTS được khuyến nghị, nhưng preloading không được khuyến nghị như lựa chọn mặc định cho tất cả website.** HSTS preload phù hợp khi tổ chức thật sự kiểm soát toàn bộ domain, có lợi ích bảo mật rõ và sẵn sàng vận hành HTTPS bền vững.

### 12.1. Preload khác header `preload`

| Tình huống | Browser lần đầu vào `http://example.com` có chắc nâng cấp không? |
|---|---|
| Server chỉ phát `max-age=31536000` trên HTTPS, browser chưa học | Không bảo đảm do policy chưa được lưu |
| Server có `preload` directive nhưng chưa nằm trong browser list | Không bảo đảm |
| Domain đã nằm trong preload list của browser hiện tại | Browser dựa vào list có thể cưỡng bức HTTPS trước lần đầu |
| Browser dùng HTTPS-First riêng, domain chưa có HSTS | Có thể thử HTTPS trước, nhưng đây là hành vi riêng của browser |

Không dựa vào tên header để tự suy ra trạng thái preload thực tế. Có thể kiểm tra trên `hstspreload.org` và browser/test environment phù hợp, nhưng không nộp domain đang vận hành chỉ để “thử”.

## 13. Rollout HSTS thận trọng theo từng giai đoạn

HSTS có thời hạn và có thể làm browser không sử dụng HTTP fallback, vì thế cần **triển khai tăng dần** thay vì bật ngay một năm hoặc preload trên domain chưa sẵn sàng.

### 13.1. Giai đoạn 0 – Chuẩn bị hạ tầng

- Xác định hostname gửi header và mọi subdomain/nested domain chịu tác động nếu dùng `includeSubDomains`.
- Kiểm tra TLS certificate, chain, SAN, trust, expiry, SNI, cipher/versions và renewal.
- Kiểm tra HTTP port 80 redirect, HTTPS port 443 và các port khác đang tồn tại.
- Review login, OAuth callbacks, cookies, CSP, API assets và mixed content.
- Xác định owner HSTS header: app Spring hay CDN/ingress; không để hai nơi ghi xung đột.
- Chuẩn bị monitoring và runbook: sửa certificate, restore DNS, rollback header, tránh downtime dài.

### 13.2. Giai đoạn 1 – `max-age=300`

```http
Strict-Transport-Security: max-age=300
```

Kiểm tra người dùng thử nghiệm và các browsers chính: login, redirect, static assets, API, OAuth callback, HTTPS certificate renewal. **Chưa bật includeSubDomains** nếu vẫn còn service chưa được kiểm tra.

### 13.3. Giai đoạn 2 – 1 tuần, sau đó 1 tháng

```http
Strict-Transport-Security: max-age=604800
```

Rồi:

```http
Strict-Transport-Security: max-age=2592000
```

Chỉ tăng khi đã theo dõi đủ lâu để thấy các lỗi liên quan và có kế hoạch xử lý. Chú ý thời gian `max-age` được refresh khi browser nhận header mới; việc giảm max-age trên server không đồng nghĩa browser đã nhận thay đổi ngay.

### 13.4. Giai đoạn 3 – HSTS lâu dài

```http
Strict-Transport-Security: max-age=31536000
```

Khi toàn bộ subdomain đã được chuẩn hóa HTTPS, mới cân nhắc parent policy:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Nếu muốn preload, xem phần yêu cầu và chi phí vận hành; không tự thêm `preload` vào policy production chỉ vì một code sample.

## 14. Rollback HSTS và giới hạn của `max-age=0`

Muốn xóa policy HSTS đã học cho host, server có thể gửi trên **HTTPS hợp lệ**:

```http
Strict-Transport-Security: max-age=0
```

Nhưng:

- Browser **không** học chính sách xóa từ HTTP response.
- Nếu HTTPS certificate đang hỏng, browser có thể không nhận được header rollback; **phải sửa TLS trước**.
- Nếu parent `example.com` còn `includeSubDomains`, subdomain `app.example.com` tự gửi `max-age=0` **không thể thoát** khỏi policy parent.
- Nếu domain đã được preload, việc gỡ có quy trình riêng và có thể cần **nhiều tháng** để các browser được cập nhật.
- Nếu CDN/ingress vẫn phát `max-age` dài, trong khi app phát `max-age=0`, chính sách không nhất quán và rollback có thể thất bại.
- Một browser không quay lại HTTPS host để nhận header mới có thể giữ policy cũ tới khi hết hạn.

HSTS là cam kết có tính “sticky”: **không nên dựa vào khả năng rollback nhanh** để bù cho việc thiếu kiểm tra subdomains hoặc certificate lifecycle.

## 15. Java 17 độc lập: mô hình hóa hostname và thời hạn HSTS

Để hiểu phạm vi mà không cần Spring/Maven, chương trình sau kiểm tra: host đúng hay subdomain, hết hạn hay chưa. Đây **chỉ là mô hình tư duy**, không phải trình duyệt: bỏ qua TLS, certificate, preload, redirect, URI ports, cookie và policy storage.

Tệp `HstsPolicyDemo.java`:

```java
import java.util.Locale;

public class HstsPolicyDemo {

    record Policy(String host, long expiresAtSeconds,
                  boolean includeSubdomains) {}

    static boolean applies(Policy policy, String requestHost, long now) {
        if (now >= policy.expiresAtSeconds()) {
            return false;
        }

        String root = policy.host().toLowerCase(Locale.ROOT);
        String requested = requestHost.toLowerCase(Locale.ROOT);

        return requested.equals(root)
            || (policy.includeSubdomains()
                && requested.endsWith("." + root));
    }

    static void check(String label, Policy policy, String host, long now) {
        System.out.println(label + ": " + applies(policy, host, now));
    }

    public static void main(String[] args) {
        long createdAt = 1_000_000L;
        long lifetime = 300L;

        Policy withSubdomains =
            new Policy("example.com", createdAt + lifetime, true);

        check("Exact host", withSubdomains,
            "example.com", createdAt + 120);
        check("Subdomain", withSubdomains,
            "app.example.com", createdAt + 120);
        check("Nested subdomain", withSubdomains,
            "api.dev.example.com", createdAt + 120);
        check("Lookalike", withSubdomains,
            "example.com.attacker.net", createdAt + 120);
        check("Expired", withSubdomains,
            "example.com", createdAt + 300);

        Policy hostOnly =
            new Policy("example.com", createdAt + lifetime, false);

        check("No includeSubDomains", hostOnly,
            "app.example.com", createdAt + 120);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac HstsPolicyDemo.java
java HstsPolicyDemo
```

Stdout chính xác của chương trình:

```text
Exact host: true
Subdomain: true
Nested subdomain: true
Lookalike: false
Expired: false
No includeSubDomains: false
```

Giải thích: policy còn hạn bao phủ host chính, và thêm subdomain nếu bật flag; domain giả `example.com.attacker.net` không thỏa suffix `.example.com`; tại thời điểm hết hạn, chính sách không còn áp. `hostOnly` không tự bảo vệ subdomain. Trong browser thật, mỗi subdomain có thể có HSTS policy riêng hoặc bị parent preload; chương trình không mô phỏng những lớp đó.

## 16. Kiểm tra HSTS/HTTPS thực tế

### 16.1. Kiểm tra header trên HTTPS

```bash
curl -I https://app.example.com/
```

Response ví dụ:

```http
HTTP/2 200
strict-transport-security: max-age=300
content-type: text/html
```

HTTP status, version và chữ hoa/thường của header có thể khác; đừng khẳng định mọi request đều 200. Hãy xác minh HSTS hiện diện trên **HTTPS responses mà browser thực sự nhận**, kể cả login redirect/error responses quan trọng. `curl -I` gửi HEAD; nếu server có hành vi riêng cho HEAD, thử GET theo contract thực.

### 16.2. Kiểm tra redirect HTTP

```bash
curl -I http://app.example.com/
```

Response minh họa:

```http
HTTP/1.1 308 Permanent Redirect
Location: https://app.example.com/
```

Không dùng HTTP response có HSTS để kết luận browser học policy. HTTPS response mới là nơi kiểm tra `Strict-Transport-Security`.

### 16.3. Kiểm tra bằng browser

1. Mở DevTools → Network và truy cập HTTPS URL; quan sát `Strict-Transport-Security` ở response.
2. Dùng profile thử nghiệm riêng để browser học policy, sau đó nhập `http://` URL cùng host.
3. Browser có thể hiển thị **307 Internal Redirect** hoặc chỉ request HTTPS, tùy browser; mã 307 nội bộ không nhất thiết là redirect HTTP server thật.
4. Xác minh không phát HTTP request mạng tới HSTS host sau khi đã học policy.
5. Thử subdomains nếu có `includeSubDomains`, đặc biệt những host ít truy cập, nội bộ và host có cert riêng.
6. Kiểm tra mixed content, OAuth callbacks, HTTPS assets, cookie Secure và WebSocket `wss://`.
7. Kiểm tra certificate expiry, trust chain, SNI, SSL/TLS protocol, preload state và alerting.
8. Không phá production certificate để thử browser chặn bypass; dùng test environment riêng.

**MockMvc** xác minh header writer, còn **curl** xem response thực từ server, và **browser** mới xác minh HSTS enforcement. Ba cách test bổ sung nhau, không thay thế nhau.

### 16.4. Ma trận test

| Test case | Kết quả cần quan sát |
|---|---|
| HTTPS secure request | HSTS xuất hiện theo policy |
| HTTP insecure request | Browser không học HSTS từ HTTP |
| Browser chưa học policy | Có thể có first-visit gap |
| Browser đã học `max-age>0` | Nâng HTTP URL thành HTTPS trước mạng |
| Host `includeSubDomains=false` | Parent không tự bảo vệ child |
| Parent `includeSubDomains=true` | Child/nested child bị buộc HTTPS |
| Certificate hết hạn tại HSTS host | Browser báo lỗi nghiêm ngặt |
| Server phát `max-age=0` qua HTTPS | Có thể xóa host policy đã học |
| Server phát `max-age=0` qua HTTP | Không xóa host policy |
| Preload chưa được browser phân phối | Không thể khẳng định first-visit protection |
| Reverse proxy HTTPS nhưng app thấy HTTP | App HSTS writer có thể không phát |
| Nginx và Spring cùng phát HSTS | Cần phát hiện và thống nhất một nguồn |
| API client không phải browser | Không dựa vào HSTS để bắt buộc TLS |
| Mixed content qua HTTP | Phát hiện, sửa HTTPS URL/resource |
| Certificate renewal/rotation | Không làm gián đoạn HTTPS hay HSTS |
| CSRF/XSS/authorization | Vẫn được kiểm thử độc lập |

## 17. Các lỗi thường gặp

1. **Bật redirect nhưng bỏ HSTS**, khiến first-request HTTP vẫn có thể bị can thiệp.
2. **Đặt HSTS trên HTTP port 80**, rồi nghĩ browser đã lưu policy.
3. **Bật `includeSubDomains` ở parent khi còn subdomain HTTP-only**, khiến service cũ không truy cập được.
4. **Bật `preload` mà không hiểu danh sách browser**, nghĩ chỉ thêm directive là xong.
5. **Nhầm HSTS với TLS**, không cấu hình certificate/listener 443 nhưng lại tăng max-age.
6. **Để certificate hết hạn** hoặc SAN sai trên HSTS host, gây outage khó bypass.
7. **Dùng `max-age=31536000` ngay lần đầu** khi chưa có rollout/certificate monitoring.
8. **Tưởng `max-age=0` từ HTTP gỡ được policy** hoặc giúp thoát parent/preload.
9. **Để backend sau TLS proxy hiểu request là HTTP**, khiến HSTS/cookie/redirect không đúng.
10. **Tin `X-Forwarded-Proto` từ internet** thay vì trusted reverse proxy.
11. **Nginx và Spring phát hai HSTS headers khác nhau**, gây khó review/rollback.
12. **Tạo HSTS chỉ cho một route** dù policy áp hostname-wide.
13. **Không test HTTPS redirect/error responses**, để thiếu header ở đường đi thực tế.
14. **Mixed content** từ JS/API/font/script HTTP trên trang HTTPS.
15. **Private key nằm trong repository/image**, bỏ qua secret store và file permissions.
16. **Dựa vào MockMvc secure(true) để kết luận TLS an toàn**, dù test không chạm certificate.
17. **Dựa vào curl mà không test browser**, không thấy browser HSTS store/upgrade.
18. **Tưởng HSTS chặn XSS/CSRF/phishing**, bỏ qua các lớp phòng vệ ứng dụng.
19. **Không xem subdomain nội bộ và nested domain**, dù preload bao phủ.
20. **Không chuẩn bị rollback/runbook**, khiến lỗi certificate/HTTPS kéo dài hàng tuần hoặc lâu hơn.

## 18. Checklist triển khai production

- [ ] Hostname, certificate SAN, CA chain và thời hạn đều hợp lệ.
- [ ] TLS 1.2/1.3 và cipher suites tuân theo tiêu chuẩn hiện hành; certificate được tự động gia hạn/giám sát.
- [ ] HTTP redirect tới HTTPS đúng host, không loop, không truyền credential qua HTTP.
- [ ] Mọi login/API/OAuth redirect/static asset/WebSocket dùng HTTPS/WSS, không mixed content.
- [ ] HSTS header phát trên HTTPS responses, không trông chờ HTTP response.
- [ ] Nếu dùng proxy, cấu hình forwarded scheme/host/port đúng và chỉ tin trusted proxy.
- [ ] Chọn một owner HSTS policy ở edge hoặc Spring; không phát headers trùng/mâu thuẫn.
- [ ] `max-age` được rollout tăng dần, có monitoring và thời gian quan sát.
- [ ] Chỉ bật `includeSubDomains` khi đã audit đủ mọi subdomain/nested service.
- [ ] Chỉ cân nhắc `preload` khi chấp nhận cam kết HTTPS toàn domain và rollback kéo dài.
- [ ] Có certificate renewal alert, runbook phục hồi TLS và rollback HSTS.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite` và CSRF/XSS/authorization được bảo vệ riêng.
- [ ] Có MockMvc/WebTestClient tests cho headers, TLS integration tests và browser behavior tests.
- [ ] Không suy luận HSTS sẽ được mọi non-browser HTTP client thực thi.
- [ ] Kiểm tra lại domain/preload trạng thái sau thay đổi DNS, proxy, certificate hoặc sản phẩm con.

## 19. Tự kiểm tra

**Câu 1.** HTTP response `308` có `Strict-Transport-Security`, vậy browser đã học HSTS chưa?

**Trả lời:** Chưa từ HTTP response. Header phải nhận qua HTTPS với TLS/certificate hợp lệ.

**Câu 2.** HTTPS được terminate ở Nginx, Spring Boot nối Nginx qua HTTP. Spring Security không phát HSTS vì sao?

**Trả lời:** Với Servlet, HSTS writer mặc định xét `request.isSecure()`. Nếu framework không được cấu hình hiểu scheme gốc qua trusted proxy, nó có thể nhìn request là không secure. Cần sửa forwarded headers/trust boundary hoặc để edge sở hữu header.

**Câu 3.** Tại `example.com` phát `includeSubDomains` trong khi `legacy.example.com` chỉ có HTTP. Nguy cơ?

**Trả lời:** Browser đã học parent policy sẽ cố kết nối HTTPS đến legacy host, và có thể không truy cập được. Phải nâng cấp legacy host trước hoặc giới hạn policy ở host riêng.

**Câu 4.** Phát `max-age=0` từ HTTP port 80 là rollback hoàn chỉnh?

**Trả lời:** Không. Browser bỏ qua HSTS trên HTTP. Cần HTTPS hợp lệ, và policy parent hoặc preload có thể tiếp tục cưỡng bức HTTPS.

**Câu 5.** Dùng `preload(true)` trong Spring Security nghĩa là domain đã vào danh sách preload của Chrome?

**Trả lời:** Không. Chỉ thêm directive `preload` vào header. Cần đáp ứng `hstspreload.org`, nộp và được browser phân phối.

**Câu 6.** HSTS ngăn browser đọc cookie bằng JavaScript hoặc tự kiểm tra CSRF token?

**Trả lời:** Không. `HttpOnly` hạn chế JavaScript đọc cookie; CSRF token/Origin checks bảo vệ request; HSTS chỉ góp phần cưỡng bức HTTPS cho host.

## 20. Tài liệu tham khảo

- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797).
- [MDN — Strict-Transport-Security header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security).
- [Spring Security 6.5 — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html).
- [Spring Security 6.5 — Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html).
- [Spring Boot — SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html).
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html).
- [HSTS Preload List Submission — Requirements and Deployment](https://hstspreload.org/).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

**Ghi nhớ:** HSTS là cam kết **HTTPS-only theo hostname trong browser**, bảo vệ các request sau khi browser đã học policy hoặc domain được preload. Nó **không tạo HTTPS và không sửa lỗi certificate**. Hãy triển khai TLS/HTTPS đúng, redirect HTTP, bảo vệ private keys, cấu hình trusted proxy, kiểm thử đường đi thực tế và rollout `max-age` dần dần. `includeSubDomains` và `preload` chỉ nên bật sau khi kiểm tra, phê duyệt và cam kết bảo trì HTTPS trên toàn bộ phạm vi bị ảnh hưởng.