# TLS termination, Forwarded headers và chỉ tin cậy proxy được chỉ định

## 1. Mục tiêu: phân biệt kết nối thật với thông tin do proxy chuyển tiếp

Trong ứng dụng **Spring Security Servlet**, HTTPS có thể kết thúc trực tiếp ở Tomcat/Jetty/Undertow hoặc kết thúc tại một reverse proxy, ingress, load balancer, API gateway. Khi **TLS termination** diễn ra trước backend, browser đang dùng HTTPS nhưng request proxy gửi đến Spring Boot có thể là HTTP nội bộ.

Ví dụ:

```text
                    Internet / public trust zone
Browser ── HTTPS:443 ──> Reverse proxy / TLS terminator
                                 |
                                 | HTTP:8080 trong mạng riêng
                                 | X-Forwarded-Proto: https
                                 | X-Forwarded-Host: app.example.test
                                 | X-Forwarded-Port: 443
                                 v
                        Spring Boot Servlet
                        request.getScheme() == ?
                        request.isSecure() == ?
                        redirects / OAuth2 / cookies
```

Nếu backend chỉ nhìn socket HTTP nội bộ, nó có thể nghĩ request là không an toàn (`http`, port `8080`) dù browser đã kết nối HTTPS với proxy. Nếu backend tin mọi `X-Forwarded-*` từ client Internet, attacker có thể tự đặt scheme/host/port và làm sai redirect, kiểm tra channel hoặc tạo liên kết độc hại.

**Mục tiêu đúng gồm hai phần không thể tách rời:**

1. Proxy **đáng tin** mô tả chính xác public scheme, host, port (và prefix nếu cần), để Spring MVC/Security xây dựng URL và logic channel chính xác.
2. **Chỉ** proxy đã được chỉ định mới có thể cung cấp dữ liệu này; mọi header forwarded từ phía Internet phải bị xóa hoặc chuẩn hóa trước khi đến backend.

`ForwardedHeaderFilter` hay `server.forward-headers-strategy=framework` chỉ **diễn giải header**, không tự xác minh địa chỉ IP/hệ thống nào đã tạo header. Ranh giới tin cậy phải được bảo vệ ở mạng, gateway và cấu hình upstream.

## 2. Luồng TLS termination và ba góc nhìn khác nhau

Một request có thể có ba góc nhìn:

| Tầng | Nhìn thấy | Dùng vào việc gì |
| --- | --- | --- |
| Browser | `https://app.example.test/profile` trên TLS 443 | Secure Context, HSTS, cookie Secure và tính toàn vẹn với edge |
| Reverse proxy | TLS handshake với browser; có thể chuyển tiếp bằng HTTP hoặc HTTPS | Kiểm tra domain/certificate, policy, xác thực, routing và header |
| Spring Boot Servlet | Socket từ proxy, thường `http://backend:8080` | `HttpServletRequest`, redirect URL, callback OAuth2 và channel security |

Giả sử edge đã kiểm tra TLS thành công nhưng **không chuyển forwarded headers**, ứng dụng có thể thấy:

```text
request.getScheme()      = "http"
request.isSecure()       = false
request.getServerPort()  = 8080
```

Sau khi proxy gửi thông tin public đúng và Spring Boot xử lý headers bằng một cơ chế phù hợp, ứng dụng thường thấy:

```text
request.getScheme()      = "https"
request.isSecure()       = true
request.getServerName()  = "app.example.test"
request.getServerPort()  = 443
```

Những giá trị sau phản ánh **đường kết nối phía người dùng đến proxy**, không có nghĩa socket từ proxy sang JVM đã dùng TLS. Không dùng `request.isSecure()` một mình để chứng minh backend peer được xác thực hay đường proxy → backend không thể bị nghe lén.

Có ba mô hình chính:

- **TLS passthrough:** proxy chuyển TLS đến backend; backend tự giải mã và trực tiếp thấy HTTPS. Forwarded headers có thể không cần để xác định public scheme.
- **TLS termination + HTTP backend:** edge giải mã, backend nhận HTTP trong vùng mạng được bảo vệ; cần policy và forwarded headers để tái dựng URL public.
- **TLS termination + re-encryption:** edge giải mã rồi thiết lập một kết nối TLS khác đến backend. Vẫn cần phân biệt public host/port với internal host/port; mTLS có thể xác nhận proxy là peer phía backend.

TLS từ browser đến edge không bảo vệ đường HTTP proxy → backend khi hai thành phần nằm trên các trust zone khác nhau. Với mạng liên máy, multi-tenant hoặc yêu cầu compliance, cân nhắc re-encryption/mTLS thay vì giả định “mạng nội bộ luôn an toàn”.

## 3. Những header quan trọng và phạm vi ý nghĩa

Có hai họ header:

**Họ de facto:**

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.25
X-Forwarded-Prefix: /portal
```

**Header chuẩn hóa `Forwarded` (RFC 7239):**

```http
Forwarded: for=198.51.100.25;proto=https;host=app.example.test
```

| Trường | Vai trò | Cảnh báo |
| --- | --- | --- |
| `X-Forwarded-Proto` / `proto` | Scheme mà user sử dụng tại proxy đáng tin | `https` có thể bị client tự khai nếu không sanitize |
| `X-Forwarded-Host` / `host` | Public host/authority cần dùng tạo URL | Host không đáng tin có thể gây host-header poisoning |
| `X-Forwarded-Port` | Cổng public, thường `443` | Sai port làm URL `:8080`/`:8443` lộ ra |
| `X-Forwarded-Prefix` | Public path prefix khi ingress rewrite path | Không phải mọi proxy/framework đều xử lý giống nhau |
| `X-Forwarded-For` / `for` | Chuỗi IP của client/các hop | Không phải bằng chứng user đã xác thực; nhiều hop cần policy |
| `Host` | HTTP authority của request proxy chuyển vào backend | Cũng phải được validate hoặc ấn định từ route |
| `X-Forwarded-Ssl` và các alias | Một số hệ thống legacy mô tả HTTPS | Tránh chấp nhận nhiều định dạng mâu thuẫn không được chuẩn hóa |

`Forwarded` có thể chứa **nhiều phần tử** cho nhiều proxy hop. Giá trị như `for=`, `proto=` và `host=` có thể có quoting/IPv6 và các quy tắc phân tích theo chuẩn. Không tự viết parser bằng `split(",")`/`split(";")` rồi tin phần tử đầu hoặc cuối mà chưa có trust-hop contract.

Khi cùng tồn tại `Forwarded` và `X-Forwarded-*` mâu thuẫn, từng framework/phiên bản có thể có cách ưu tiên khác nhau. **Chính sách an toàn là chuẩn hóa tại một gateway đáng tin**, chỉ chuyển bộ header được quản trị và nhất quán; backend không tự đoán bộ nào mới là sự thật.

## 4. Threat model: ai được phép khẳng định HTTPS?

Ví dụ attacker gọi thẳng HTTP vào backend và tự khai:

```http
GET /api/data HTTP/1.1
Host: internal.example
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
```

Nếu backend bật xử lý forwarded headers nhưng không chặn truy cập trực tiếp, `request.isSecure()` có thể trả `true` **dù attacker chỉ dùng HTTP**. Đó là lý do tuyệt đối không dùng header như một cơ chế xác thực TLS.

Một biến thể khác là **host-header poisoning**:

```http
GET /login HTTP/1.1
Host: app.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
```

Nếu backend tạo liên kết tuyệt đối từ host do attacker kiểm soát, email/password reset redirect, OAuth2 redirect URI hoặc `Location` có thể bị sai hoặc tạo đường dẫn đến domain lạ. OAuth2 provider có kiểm redirect URI sẽ thường từ chối URI không khớp, nhưng đó không thay thế kiểm soát input ở proxy.

Điều kiện an toàn tối thiểu:

1. Chỉ proxy/gateway được chỉ định có đường mạng tới backend.
2. Proxy chặn, xóa hoặc ghi đè forwarded headers của client **trước** khi chuyển tiếp.
3. Proxy tự tính scheme, host, port từ TLS listener và route **đã xác minh**, không sao chép header không đáng tin từ client.
4. Backend bật đúng một chiến lược xử lý forwarded headers.
5. Authorization, xác thực người dùng, CSRF và session security vẫn hoạt động riêng; `X-Forwarded-Proto` không xác thực principal.
6. Kiểm thử từ mạng ngoài xác nhận không thể vượt proxy hoặc tự thay public host/scheme.

## 5. Chọn chiến lược Spring Boot cho Servlet

Spring Boot 3.x cung cấp thuộc tính:

```yaml
server:
  forward-headers-strategy: framework
```

Các giá trị thường gặp:

| Giá trị | Ý nghĩa | Khi nào chọn |
| --- | --- | --- |
| `none` | Không diễn giải forwarded headers qua tích hợp Boot | Backend trực tiếp phục vụ TLS hoặc không tin header từ upstream |
| `framework` | Dùng cơ chế Spring Framework, thường dựa vào `ForwardedHeaderFilter` trên Servlet | Khi proxy đã chuẩn hóa forwarded headers và muốn Spring xử lý request URL |
| `native` | Dùng xử lý native của web server/container khi được hỗ trợ | Khi cần hành vi đặc thù container, ví dụ Tomcat `RemoteIpValve` |

**Không bật cả hai cơ chế rồi tự thêm nhiều filter khác** nếu chưa xác định thứ tự và contract. Hai tầng cùng diễn giải forwarded headers có thể gây kết quả khó dự đoán, nhất là khi chuỗi proxy nhiều hop.

Trong một số môi trường, Boot có thể dựa vào deployment platform để chọn strategy mặc định; đối với bài toán trust boundary, **nên cấu hình tường minh và kiểm tra trên đúng phiên bản Boot/container** thay vì suy đoán default.

### `framework` và `ForwardedHeaderFilter`

`ForwardedHeaderFilter` là một Servlet filter của Spring Framework, có thể bao bọc request/response để phản ánh scheme/host/port/prefix được chuyển tiếp khi tạo URL và redirect. Khi Boot đã tự đăng ký filter qua strategy `framework`, **không tạo thêm một filter tương đương tùy tiện**.

Filter có chế độ `removeOnly`: loại bỏ forwarded headers mà **không dùng chúng** để thay đổi request. Chế độ này hữu ích khi backend nhận một số header không đáng tin nhưng muốn xóa dấu vết trước khi downstream dùng; nó **không thay thế** việc proxy sanitize và không có khả năng phân biệt “header thật”/“header giả” chỉ bằng nội dung.

### `native` và cấu hình Tomcat

Trong một ứng dụng Servlet dùng Tomcat, chiến lược `native` có thể sử dụng `RemoteIpValve` để diễn giải proxy headers. Các tùy chọn Tomcat liên quan gồm danh sách proxy nội bộ/tin cậy và header proto/remote IP. Cấu hình chính xác cần đối chiếu với phiên bản Boot/Tomcat hiện tại, topology nhiều proxy và chế độ `server.forward-headers-strategy`.

**Không mặc định `native` có thể sửa được lỗi trust boundary chỉ bằng một cờ.** Khi IP của reverse proxy thay đổi, proxy chain có nhiều tầng hoặc CIDR cấu hình rộng quá mức, bản thân cơ chế native vẫn có thể tin nhầm giá trị không đáng tin. Dù ở chiến lược nào, lớp mạng cần chặn direct access và edge phải chuẩn hóa headers.

## 6. Ví dụ thực tế: Spring Boot Servlet nhận HTTPS tại Nginx

Giả định:

- Public URL: `https://app.example.test`
- Nginx chạy trên cùng máy với Spring Boot.
- Nginx là TLS terminator ở cổng 443.
- Spring Boot chỉ lắng nghe `127.0.0.1:8080`; **không** public cổng này.
- Nginx đặt giá trị public host/scheme/port cố định từ một route đã xác định.
- Dùng HTTP Basic với tài khoản demo chỉ để minh họa endpoint có xác thực; không phải khuyến nghị dùng Basic trên Internet.

### 6.1. Project Spring Boot 3.3.5 / Java 17+

Cấu trúc:

```text
forwarded-headers-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/forwarded/
    │   │   ├── ForwardedDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── TransportController.java
    │   └── resources/application.yml
    └── test/java/demo/forwarded/TransportSecurityTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` dùng Spring MVC trên Servlet container, còn `spring-boot-starter-security` bảo vệ endpoint bằng filter chain. Project cần một Gradle wrapper tương thích với Java 17; nếu chưa có wrapper, cài Gradle rồi tạo wrapper theo quy trình build của đội dự án.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: framework
```

Cấu hình chỉ bind loopback trong demo. Nếu backend chạy trong container khác Nginx, `127.0.0.1` không còn dùng chung; phải dùng private service/network, policy chỉ cho proxy gọi vào, và có thể dùng TLS/mTLS trên hop nội bộ.

Tạo `src/main/java/demo/forwarded/ForwardedDemoApplication.java`:

```java
package demo.forwarded;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForwardedDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }
}
```

### 6.2. SecurityFilterChain và HTTPS requirement

Tạo `src/main/java/demo/forwarded/SecurityConfig.java`:

```java
package demo.forwarded;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService localUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        return http
                .requiresChannel(channel -> channel
                        .anyRequest().requiresSecure())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/diag/transport").permitAll()
                        .requestMatchers("/api/self").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Ý nghĩa kỹ thuật:**

1. `.requiresChannel(...requiresSecure())` đòi request được Spring Security xem là HTTPS. Với forwarded headers đã được **tin đúng cách**, nó nhìn scheme public. Nếu scheme vẫn là `http`, Spring Security có thể trả redirect sang HTTPS, dù edge đã nhận TLS.
2. `.requiresSecure()` **không kiểm tra nguồn gốc `X-Forwarded-Proto`**. Nếu attacker gọi trực tiếp backend và tự khai `https`, điều kiện này có thể bị đánh lừa.
3. `httpBasic()` chỉ để demo authentication. `{noop}` không hash password và không được dùng trong production; credential test chỉ hợp trên loopback.
4. Không tắt CSRF một cách tùy tiện. API demo chỉ dùng GET. Nếu ứng dụng dùng session cookie và method thay đổi trạng thái, cần thiết kế CSRF riêng.
5. Với production, cấu hình HTTPS redirect chủ yếu ở **edge** thường rõ ràng hơn, nhưng yêu cầu HTTPS tại app có thể là defense-in-depth khi trust boundary được bảo đảm.

**Đừng dùng cấu hình yêu cầu HTTPS này để thay thế network policy.** Trên đường proxy → backend, dữ liệu có thể vẫn được truyền HTTP; điều kiện HTTPS chỉ kiểm tra request metadata mà app nhìn thấy.

### 6.3. Endpoint chẩn đoán transport

Tạo `src/main/java/demo/forwarded/TransportController.java`:

```java
package demo.forwarded;

import java.security.Principal;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TransportController {

    @GetMapping("/diag/transport")
    public Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort());
    }

    @GetMapping("/api/self")
    public Map<String, Object> self(
            HttpServletRequest request,
            Principal principal) {
        return Map.of(
                "name", principal.getName(),
                "secure", request.isSecure());
    }
}
```

`HttpServletRequest` được Spring MVC đưa vào controller sau khi các filter cần thiết đã chạy. Endpoint `/diag/transport` ở đây chỉ dành cho **loopback/test**, vì tiết lộ chi tiết cấu hình host/port có thể không phù hợp với ứng dụng public. Trong production, thay bằng health check tối giản không lộ dữ liệu vận hành nhạy cảm.

`request.isSecure()` là thuộc tính **theo góc nhìn Servlet đã xử lý forwarded metadata**, không phải kết quả của một phép kiểm tra certificate gốc của client tại controller.

## 7. Cấu hình Nginx làm TLS terminator đáng tin

Đoạn sau là ví dụ cho một Nginx đứng ở edge, nhận TLS **trực tiếp từ browser** và chuyển tiếp đến Spring Boot cùng host qua loopback. Domain/certificate path chỉ là placeholder kiến trúc, phải thay bằng tài nguyên thật; cần cấu hình TLS protocol/cipher/certificate lifecycle theo chính sách hạ tầng của bạn.

```nginx
server {
    listen 80;
    server_name app.example.test;
    return 308 https://app.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/certs/app.example.test.crt;
    ssl_certificate_key /etc/nginx/certs/app.example.test.key;

    location / {
        proxy_http_version 1.1;

        # Định danh public đến từ route/certificate được quản trị.
        proxy_set_header Host app.example.test;

        # Ghi đè các trường forwarded thay vì copy từ client.
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;

        # Nếu chỉ có một proxy ở edge, IP peer có thể lấy từ $remote_addr.
        proxy_set_header X-Forwarded-For $remote_addr;

        # Xóa dạng chuẩn và alias/prefix không được dùng để tránh xung đột.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";

        proxy_pass http://127.0.0.1:8080;
    }
}
```

Cấu hình này nhấn mạnh ba bất biến:

- `X-Forwarded-Proto` là **`https` vì chính listener 443 SSL của proxy** đã kiểm tra TLS. Nếu Nginx đứng sau một load balancer khác, không được gán `https` một cách mù quáng khi Nginx còn chấp nhận request HTTP trực tiếp từ nguồn không đáng tin.
- `X-Forwarded-Host` được gắn từ hostname route **đã định danh**, không sao chép giá trị `X-Forwarded-Host` do browser gửi. Cách dùng host cố định phù hợp ví dụ một domain, giúp giảm host-header poisoning.
- Cổng backend 8080 chỉ ở loopback. Một cấu hình tương đương trên Kubernetes cần dùng internal service và `NetworkPolicy`/ingress routing, không coi mọi Pod trong cluster là đáng tin mặc định.

Một số deployment cần giữ public host động hoặc path prefix. Khi ấy, danh sách hostname hợp lệ và mapping route phải do proxy/ingress kiểm soát, không lấy trực tiếp từ header client. Nếu có nhiều proxy hop, policy `X-Forwarded-For` phải được thiết kế riêng; **không dùng IP forwarding làm bằng chứng danh tính**.

**Quan trọng:** nhiều reverse proxy chuyển tiếp những header không được đặt lại theo mặc định. Vì vậy việc chủ động xóa/ghi đè `Forwarded` và toàn bộ alias identity/transport liên quan là một phần cấu hình security chứ không phải chi tiết thẩm mỹ.

## 8. Quan sát bằng curl: luồng đúng và luồng giả mạo

Khởi động ứng dụng Java:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 8.1. Gọi trực tiếp HTTP không có header forwarded

```bash
curl -i http://127.0.0.1:8080/diag/transport
```

Với `.requiresSecure()` trong demo, mong đợi **một chuyển hướng HTTPS** (HTTP 3xx) thay vì JSON. `Location` cụ thể phụ thuộc Spring Security `PortMapper`, host, cổng Servlet và cấu hình container; không nên dự đoán chính xác URI từ ví dụ đơn giản.

### 8.2. Giả lập một request đã qua proxy

```bash
curl -i http://127.0.0.1:8080/diag/transport \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: app.example.test" \
  -H "X-Forwarded-Port: 443"
```

Khi filter hoạt động và không có rule khác từ chối, JSON trả về tương đương:

```json
{
  "scheme": "https",
  "secure": true,
  "host": "app.example.test",
  "port": 443
}
```

**Đây là bài thử chức năng xử lý header, không phải bài thử an toàn.** Chúng ta đã tự gửi `X-Forwarded-Proto` qua HTTP và ứng dụng vẫn xem request là `secure`. Chính vì thế production phải chặn đường gọi trực tiếp và bảo đảm proxy viết headers.

### 8.3. Gọi qua HTTPS proxy thật

Sau khi cài certificate hợp lệ và public host trỏ đúng Nginx:

```bash
curl -i https://app.example.test/diag/transport
```

Dù backend socket vẫn là HTTP/8080, JSON mà Spring Boot nhìn thấy phải tương đương `scheme=https`, `secure=true`, `host=app.example.test`, `port=443`. Không dùng `curl -k` để “chứng minh TLS an toàn”: tắt kiểm tra certificate chỉ có thể phục vụ tình huống debug được kiểm soát.

### 8.4. Kiểm thử `Forwarded` chuẩn hóa

Một test local khác:

```bash
curl -i http://127.0.0.1:8080/diag/transport \
  -H "Forwarded: proto=https;host=app.example.test"
```

Nếu strategy `framework` và filter hỗ trợ, request có thể được xem là HTTPS với public host đúng. Thử nghiệm này cũng chứng minh bất kỳ ai có quyền direct access tới backend **có thể tự đưa dữ liệu forwarded** nếu network boundary không khóa.

## 9. Tại sao xảy ra redirect loop sau proxy?

Tình huống phổ biến:

1. Browser gọi `https://app.example.test/account`.
2. Proxy giải TLS và gọi `http://backend:8080/account`.
3. Spring Security thiếu/misread forwarded metadata, thấy `http`.
4. `.requiresSecure()` trả redirect về `https://app.example.test/account` (hoặc URI/port khác).
5. Browser tiếp tục gọi proxy bằng HTTPS.
6. Proxy lại gửi HTTP nội bộ; vòng lặp tiếp diễn.

Sơ đồ:

```text
Browser HTTPS
   |
   v
Proxy TLS termination --HTTP--> Spring Boot
                              sees scheme=http
                                   |
                                   v
                         302/redirect HTTPS
                                   |
                                   v
Browser HTTPS -> Proxy -> Spring Boot -> redirect ...
```

Triệu chứng có thể là `ERR_TOO_MANY_REDIRECTS`, `curl -L` lặp lại, ingress log 302 liên tiếp, hoặc người dùng không thể hoàn tất OAuth2 login.

Các nguyên nhân riêng biệt:

| Dấu hiệu | Khả năng | Hướng xác minh |
| --- | --- | --- |
| HTTPS public vẫn luôn nhận 302 sang chính URL đó | Backend luôn nghĩ `isSecure=false` | Kiểm tra `X-Forwarded-Proto` tại trusted proxy và filter/strategy |
| Redirect lộ `:8080`, `:8443` hoặc internal host | Host/port public tái dựng sai | Kiểm tra `X-Forwarded-Host`, `X-Forwarded-Port`, `Host` và port mapping |
| OAuth2 callback `http` thay vì `https` | Public base URL từ request sai | Kiểm tra forwarded metadata và redirect URI đã đăng ký |
| Redirect thay đổi giữa hai host | Proxy rewrite host không nhất quán hoặc `Host` không được validate | Chỉ định canonical host và kiểm route |
| Chỉ một replica bị loop | Khác environment config, proxy chain hoặc strategy | So sánh cấu hình/headers giữa replicas |
| Secure cookie không được gửi lại | Cookie `Secure`, domain, SameSite hoặc scheme bị suy diễn sai | Phân tích `Set-Cookie`, TLS, public origin, browser rules |
| HSTS khiến trình duyệt luôn nâng HTTP lên HTTPS | HSTS hoạt động nhưng proxy/backend xử lý scheme sai | Phân biệt browser upgrade với 302 do server tạo |

Không giải bằng cách **tắt HTTPS requirement toàn bộ** khi vấn đề thực chất là proxy không chuyển dữ liệu đúng. Đồng thời không bật trust tất cả forwarded headers ở backend public để “chữa loop” — điều đó biến một lỗi availability thành lỗi security.

## 10. OAuth2 login, absolute URL và cookie phía sau TLS proxy

### OAuth2 redirect URI

Một ứng dụng Spring Security OAuth2 Client hay dùng redirect URI có biến base URL:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          login-provider:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Đây là **đoạn cấu hình minh họa**, chưa có `provider` metadata/issuer URI hoặc endpoints nên **không phải cấu hình OIDC chạy độc lập**. Khi thực thi, `{baseUrl}` thường phụ thuộc public URL được suy ra từ request. Nếu forwarded host/proto/port sai, redirect URI có thể thành `http://internal:8080/...`, làm provider từ chối với `redirect_uri_mismatch`.

Giải pháp gồm cấu hình provider/registration chính xác, forwarded strategy sau proxy đã tin cậy, và kiểm tra redirect URI **public** khớp URI được đăng ký tại identity provider. Đừng đăng ký hàng loạt wildcard redirect URI để vượt qua mismatch.

### Secure cookie

Spring Security session hoặc các cookie khác có thể cần các thuộc tính:

- **`Secure`**: chỉ gửi qua HTTPS theo rule của browser.
- **`HttpOnly`**: không cho JavaScript truy cập cookie.
- **`SameSite`**: giảm một số nguy cơ cross-site cookie use; cần phù hợp OAuth2 login callback/redirect.
- **Domain/Path**: phải khớp public host/prefix hợp lệ.

Sau TLS termination, backend có thể phải biết public request là HTTPS để sinh redirect/cookie đúng. Tuy vậy **không coi `isSecure=true` từ header client là bằng chứng an toàn**, và không dùng forwarded headers để vượt các kiểm tra CSRF hoặc domain chính sách.

Có thể đặt chính sách session cookie có chủ đích trong Boot, tùy sản phẩm:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

Trong production chỉ triển khai `Secure` khi người dùng thực sự truy cập qua HTTPS, và cấu hình SameSite cụ thể dựa trên flow; không thêm các thuộc tính cho tiện rồi bỏ qua kiểm thử browser.

## 11. Tránh host-header poisoning khi tạo URL

Một đoạn mã có thể tạo absolute URL từ request:

```java
String scheme = request.getScheme();
String host = request.getServerName();
int port = request.getServerPort();
```

Sau khi framework xử lý forwarded headers, cả ba giá trị có thể đến từ headers đã được proxy chuyển tiếp. Nếu client được phép tự tạo `X-Forwarded-Host`, ứng dụng có thể sinh link kiểu:

```text
https://attacker.example/reset?token=...
```

khi thực tế trang của ứng dụng là `https://app.example.test`.

Các biện pháp:

1. **Tại ingress:** ấn định/allowlist host hợp lệ theo route và certificate; loại bỏ forwarded host từ client.
2. **Tại ứng dụng:** khi tạo link nhạy cảm gửi email, có thể dùng **canonical public base URL được cấu hình** thay vì hoàn toàn tin request metadata.
3. **Tại OAuth2:** đăng ký redirect URI chính xác, không dùng wildcard nguy hiểm.
4. **Tại test:** cố tình gửi `Host` và `X-Forwarded-Host` bất hợp lệ qua public endpoint; bảo đảm redirect/link không chuyển sang domain attacker.
5. **Tại logging:** ghi domain/correlation ID đã chuẩn hóa, không log raw credentials hoặc link chứa token.

Không cần cấm mọi host động nếu sản phẩm thực sự đa domain; cần một bảng mapping **tenant ↔ host được phép** do server quản lý và tránh phụ thuộc vào dữ liệu tự khai của client.

## 12. Nhiều tầng proxy và các hop được tin cậy

Một topology thực tế:

```text
Browser -> CDN -> Cloud Load Balancer -> Ingress -> Spring Boot
           TLS      TLS/HTTP?          HTTP?
```

Tại mỗi hop, cần ghi rõ:

- Hop nào là **entry point đầu tiên** được phép nhận request Internet?
- Hop nào thực sự nhìn thấy kết nối HTTPS từ user?
- Hop nào có thể tạo hoặc làm sạch `Forwarded`/`X-Forwarded-*`?
- Hop nào có thể bị gọi trực tiếp bỏ qua bước xác thực/định tuyến?
- Hop nào nhận IP client gốc và theo contract nào?
- Backend tin đúng hop nào, hay tin một mạng proxy được chỉ định?

Nếu CDN đã gửi `X-Forwarded-Proto=https`, một ingress nội bộ lại dùng biến `$scheme` của **HTTP hop CDN → ingress** và ghi đè thành `http`, backend sẽ thấy sai scheme và có thể redirect loop. Ngược lại, nếu ingress copy thẳng `$http_x_forwarded_proto` từ bất kỳ client nào, attacker có thể spoof.

**Quy tắc:** chỉ tiếp nhận thông tin public từ một upstream **đã được xác thực về mạng/identity**, sau đó chuẩn hóa thành bộ header được quản trị trước khi chuyển cho backend. Nếu upstream không đáng tin, tính public scheme từ chính listener/route mà hop đang kiểm soát. Không tự khắc phục bằng cách tin mọi giá trị có sẵn.

Với các hệ thống container/orchestrator, có thể dùng firewall, security groups, Kubernetes NetworkPolicy, service mesh policy, workload identity và mTLS. Một security group mở toàn VPC/cluster rộng hơn cần thiết có thể khiến một workload nội bộ giả mạo proxy để đặt identity/transport metadata.

## 13. `X-Forwarded-For`, IP client và kiểm tra proxy

`X-Forwarded-For` thường là chuỗi IP có nhiều hop:

```http
X-Forwarded-For: 198.51.100.25, 10.0.1.8, 10.0.2.12
```

Chuỗi này **không có giá trị tin cậy nếu client có thể tự thêm phần đầu** và proxy không có policy để tách hop đáng tin. Không viết rule phân quyền:

```java
// KHÔNG an toàn: tin IP trong header do client có thể gửi.
String clientIp = request.getHeader("X-Forwarded-For");
```

`clientIp` là dữ liệu chưa xác thực trừ khi đã được một chain đáng tin chuẩn hóa. Có thể dùng IP đã xác minh cho rate limiting/audit và các policy bổ trợ, nhưng **không dùng IP hoặc forwarded headers thay cho authentication** của user.

Nếu ứng dụng cần kiểm danh sách proxy được phép:

- Ưu tiên network rule chặn direct backend access thay vì tự kiểm một header.
- Với Tomcat native processing, xem khả năng cấu hình proxy nội bộ/tin cậy và kiểm tra trên topology thật.
- Với môi trường mTLS, có thể xác thực certificate/workload identity của **immediate peer** và không tin một assertion header từ client thường.
- Không xem một địa chỉ IP trong `X-Forwarded-For` là địa chỉ **peer socket** mà JVM đã kết nối.
- Nếu framework đã thay đổi `getRemoteAddr()` theo forwarded metadata, `getRemoteAddr()` ở controller cũng không nhất thiết là địa chỉ TCP peer nguyên bản.

Trong phần lớn ứng dụng, backend không cần tự phân loại mỗi hop bằng Java code; **chỉ định rõ một proxy ingress đáng tin** và để hạ tầng bảo đảm nó là nguồn duy nhất cấp forwarded metadata là mô hình dễ kiểm toán hơn.

## 14. Thử nghiệm MockMvc với Spring Security và forwarded headers

Ta kiểm thử **hai hợp đồng khác nhau**:

1. Ứng dụng **xử lý** header được đưa vào và tái dựng request public.
2. Hạ tầng **ngăn client Internet tự tạo** header giả và ngăn truy cập trực tiếp.

MockMvc thích hợp cho hợp đồng (1), nhưng không chứng minh (2). Một MockMvc test không có mạng thật **không thể** xác nhận firewall, TLS certificate, mTLS hoặc Nginx đã sanitize.

Tạo `src/test/java/demo/forwarded/TransportSecurityTest.java`:

```java
package demo.forwarded;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TransportSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void httpRequestWithoutForwardedMetadataIsRedirected()
            throws Exception {
        mvc.perform(get("/diag/transport"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void trustedForwardedMetadataChangesServletView() throws Exception {
        mvc.perform(get("/diag/transport")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scheme").value("https"))
                .andExpect(jsonPath("$.secure").value(true))
                .andExpect(jsonPath("$.host")
                        .value("app.example.test"))
                .andExpect(jsonPath("$.port").value(443));
    }

    @Test
    void basicCredentialsAndHttpsMetadataAreSeparateChecks()
            throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test")
                        .header("X-Forwarded-Port", "443")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.secure").value(true));
    }

    @Test
    void forwardedHttpsDoesNotAuthenticateAUser() throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .header("X-Forwarded-Host", "app.example.test"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsNotMadeValidByForwardedHttps()
            throws Exception {
        mvc.perform(get("/api/self")
                        .header("X-Forwarded-Proto", "https")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Bộ test trên dùng Spring Boot context và MockMvc có filter integration. Với stack khác hoặc cấu hình riêng, phải bảo đảm `ForwardedHeaderFilter` đã thực sự tham gia filter chain trong MockMvc; nếu strategy `framework` chỉ được áp dụng ở server thật, hãy kiểm tra test wiring và đưa filter vào MockMvc theo cấu hình thực thay vì sửa kỳ vọng bảo mật cho “pass”.

**Điểm cần nhớ:** test thứ hai cố tình gửi forwarded header từ request giả để chứng minh Spring sẽ xử lý nó. Điều đó **không phải một security pass** khi backend exposed; test network ở phần sau mới xác nhận không thể spoof qua public entry point.

## 15. Kiểm tra end-to-end ở ranh giới tin cậy

Sau khi deploy Nginx/ingress và backend, tối thiểu cần những thử nghiệm độc lập:

### 15.1. Không thể gọi thẳng backend từ ngoài

Từ một máy ở ngoài mạng proxy (không phải từ localhost):

```bash
curl -i --connect-timeout 3 http://backend-internal.example:8080/diag/transport
```

Kỳ vọng **không thể kết nối qua đường ngoài được cho phép**, không phải trả một response giả "secure" của application. Host là ví dụ; trong mạng thật hãy dùng địa chỉ backend nội bộ mà môi trường kiểm thử được quyền thử. Kiểm tra security group, load balancer backend target và Kubernetes service type/NetworkPolicy.

### 15.2. Client không thể giả `X-Forwarded-Proto`

```bash
curl -i https://app.example.test/diag/transport \
  -H "X-Forwarded-Proto: http" \
  -H "X-Forwarded-Host: attacker.example" \
  -H "Forwarded: proto=http;host=attacker.example"
```

Nếu đi qua **TLS listener chính thức** của Nginx demo, backend phải vẫn thấy public values do proxy đặt: `scheme=https`, `host=app.example.test`, `port=443`. Nếu backend thấy attacker host, cần kiểm lại policy header stripping và thứ tự proxy/filter.

### 15.3. HTTP public chỉ redirect sang canonical HTTPS

```bash
curl -I http://app.example.test/diag/transport
```

Với Nginx demo, kỳ vọng status `308 Permanent Redirect` và `Location` bắt đầu bằng `https://app.example.test/`. Không tạo `Location` theo `Host` không được allowlist. Dùng `curl -I` gửi HEAD; nếu route có behavior riêng với HEAD, thử `curl -i` GET tương ứng.

### 15.4. Không có infinite redirect

```bash
curl -IL --max-redirs 5 https://app.example.test/diag/transport
```

Kiểm tra chuỗi response không tự chuyển hướng vô hạn hoặc đổi giữa http/https; `curl` có thể báo lỗi khi vượt `--max-redirs`. Hãy kiểm các hop và `Location` do proxy/backend phát ra; không xem một redirect 301/302 tự nó là lỗi.

### 15.5. Kiểm tra OAuth2 callback và cookie

Nếu ứng dụng có OAuth2 login, kiểm tra callback URL và `redirect_uri` tại authorization server đúng **public HTTPS host**, không chứa backend port/internal DNS. Kiểm tra cookie `Secure`, `HttpOnly`, `SameSite`, domain/path đúng với browser.

### 15.6. Mô phỏng sự cố một proxy hop

Tạm bỏ một header forwarded trong môi trường staging có kiểm soát: app có redirect sai không? Một proxy hop có ghi đè `https` thành `http` không? Có metric nào nhận ra redirect loop, tăng 302 và login failure không?

Các bài test nêu trên phải được chạy trên topology **thật hoặc staging tương đương**. MockMvc không kiểm tra network-level trust.

## 16. Quan sát hệ thống mà không làm lộ bí mật

Khi gặp lỗi vận hành sau TLS proxy, cần phân biệt dữ liệu **gốc** và dữ liệu **đã qua forwarding processing**. Có thể ghi log ở mức tạm thời trong môi trường an toàn:

- correlation/request ID do edge cấp và ứng dụng nhận được;
- route/domain public được validate;
- tên proxy/ingress hoặc workload identity;
- `scheme`, `serverName`, `serverPort`, `isSecure` **sau filter**;
- status HTTP và `Location` đã sanitize;
- thời gian ở proxy, thời gian ở ứng dụng và số redirect.

Không ghi raw bearer token, cookie, header Authorization, toàn bộ JWT hay user session. Không đưa một endpoint chẩn đoán đầy đủ ra Internet khi có thể bị lạm dụng để tìm topology nội bộ.

Một bảng quan sát:

| Dữ liệu | Nơi đo | Dấu hiệu xấu |
| --- | --- | --- |
| TLS negotiated protocol/cert | Edge | Certificate sai host/hết hạn, TLS handshake failure |
| Original public scheme | Edge sau xác minh | HTTP public lẫn với HTTPS không đúng route |
| Sanitized forwarded scheme | Proxy → backend | `http` dù public là HTTPS |
| Reconstructed Servlet request | Spring Boot | `isSecure=false`, host/port internal |
| `Location` | HTTP response | Redirect về cùng URI, internal host hoặc attacker host |
| Browser cookie | Client DevTools | Cookie thiếu Secure/Domain/Path hoặc bị block |
| Login/auth flow | App/IdP | `redirect_uri_mismatch`, state mismatch, auth loop |

Nếu debug nhiều tầng, dùng correlation ID để nối một request public với proxy upstream request. Tách lỗi `401/403` do authentication/authorization khỏi lỗi `3xx` do scheme/redirect. Những vấn đề này có thể cùng xảy ra nhưng nguyên nhân khác nhau.

## 17. Các lỗi cấu hình thường gặp và giải pháp đúng

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bật `framework` khi backend vẫn public | Client tự khai `X-Forwarded-Proto=https` | Chặn direct access, buộc request qua trusted proxy |
| Edge không xóa `Forwarded` từ client | Xung đột/host poisoning | Strip header đến từ Internet và chuẩn hóa một nguồn |
| Edge copy `X-Forwarded-Proto` của client | Giả mạo HTTPS | Tính scheme từ listener TLS/nguồn upstream đã xác thực |
| Ingress dùng `$scheme=http` dù CDN nhận HTTPS | Vòng lặp 302 | Thiết kế contract cho multi-hop và xác minh CDN ingress |
| Sai public port | `Location` chứa `:8080`/`:8443` | Gửi public port đúng, kiểm lại port mapper |
| Dùng `request.isSecure()` làm proof backend TLS | Có thể bỏ qua bảo mật hop nội bộ | Xác minh peer qua network policy/mTLS và transport thật |
| Tạo absolute URL từ host chưa allowlist | Redirect/link đến domain attacker | Canonical host hoặc tenant-domain mapping được quản lý |
| Dùng `X-Forwarded-For` làm identity | Giả mạo client IP và phân quyền sai | Authentication riêng, trusted proxy chain policy |
| Vừa framework vừa native filter | Thứ tự unwrap/wrap không rõ | Chọn một strategy và test trên đúng container |
| Chỉ test MockMvc mà bỏ network test | Không biết backend có exposed hay không | Thử direct access và header spoof từ Internet |
| OAuth2 redirect-uri đăng ký cho host internal | Login failure | Cấu hình public HTTPS callback hợp lệ |
| Tắt CSRF vì tưởng edge đã bảo vệ | Rủi ro cross-site với session cookie | Giữ CSRF khi có credential tự gửi từ browser |
| Thiếu Secure cookie sau termination | Cookie có thể bị gửi qua HTTP nếu browser cho phép | Kiểm tra TLS policy và secure cookie |
| Tin cả danh sách proxy CIDR quá rộng | Workload nội bộ bất kỳ có thể đặt header | Giới hạn nguồn theo workload/proxy thật, phân tách trust zones |
| Redirect HTTP ở cả edge và backend không nhất quán | Redirect loop | Đặt canonical HTTPS tại edge, thống nhất forwarding cho backend |

Đừng xử lý tất cả những lỗi trên bằng một setting duy nhất. Bài toán phải được giải ở cả **topology mạng**, **chuẩn hóa header**, **Servlet forwarding** và **cấu hình Spring Security**.

## 18. Quy tắc triển khai với Kubernetes / Ingress / service mesh

Trong Kubernetes, một Spring Boot Service có thể chỉ là `ClusterIP` nhưng vẫn có khả năng được gọi từ các Pod khác. `ClusterIP` **không đồng nghĩa chỉ ingress được phép gọi**. Nếu ứng dụng tin `X-Forwarded-*`, hãy kiểm soát nguồn truy cập bằng NetworkPolicy hoặc chính sách mesh phù hợp.

Những điểm cần đánh giá:

1. Ingress controller nào thực sự là TLS terminator? Nếu có CDN/LB bên ngoài, ai giữ thông tin client TLS gốc?
2. Ingress có sanitize `Forwarded` và `X-Forwarded-*` từ nguồn không đáng tin không?
3. Ingress/service mesh có được phép ghi đè proto/host/port và có route canonical host không?
4. Pod backend có thể được gọi từ Pod không thuộc ingress không?
5. Khi ingress → backend dùng HTTP, đường truyền có nằm trong trust zone được bảo vệ không? Nếu không, dùng TLS/mTLS.
6. `server.forward-headers-strategy` có giống nhau trên mọi replica và environment không?
7. Ingress rewrite `/portal` thành `/` có cần `X-Forwarded-Prefix`/context-path nhất quán không?
8. OAuth2 callback và absolute redirects có qua đúng public host/port sau rewrite không?
9. Secure cookie, CORS và CSRF có phù hợp public origin thật không?
10. Khi failover/chuyển node, có hop mới làm mất hoặc thay đổi header forwarding không?

Với service mesh/Envoy, hãy ưu tiên cấu hình trust-hop và header sanitization của chính ingress/gateway thay vì tự dựng những header client-controlled trong application. Kiểm toán route và policy phải đi cùng thay đổi network topology.

## 19. Checklist bảo mật và vận hành trước production

- Public traffic chỉ đi qua những edge/ingress được chỉ định và dùng TLS với certificate/hostname hợp lệ.
- Backend không thể bị gọi trực tiếp từ Internet hoặc workload không được phép.
- Edge **xóa/ghi đè** mọi forwarded headers do client gửi, bao gồm `Forwarded` và các alias ảnh hưởng public URL.
- Host public được allowlist hoặc cố định theo route, không lấy từ giá trị attacker có thể kiểm soát.
- Scheme, host, port, prefix public được phản ánh chính xác vào Spring Servlet request.
- Chọn **một** chiến lược Boot: `framework`, `native` hoặc `none` theo topology; tránh filter trùng.
- Spring Security `.requiresSecure()`/redirect policy không gây vòng lặp sau TLS termination.
- Authentication và Authorization không dựa vào forwarded headers làm chứng minh user.
- HTTP hop proxy → backend có network policy phù hợp hoặc re-encryption/mTLS nếu rủi ro yêu cầu.
- `X-Forwarded-For` được dùng đúng cho audit/rate limit nếu cần, không thay identity.
- OAuth2 login/OIDC redirect URI, reset links, absolute URLs và callback đều dùng canonical HTTPS origin.
- Cookie `Secure`, `HttpOnly`, `SameSite`, CSRF và session được cấu hình dựa trên public browser behavior.
- Có test 3xx redirect, invalid host, spoofed proto, double headers, direct backend access và nhiều proxy hop.
- Monitoring phát hiện redirect loops, host/port lộ nội bộ và certificate/ingress failures.
- Logs không ghi session cookies, access tokens hoặc dữ liệu nhạy cảm từ raw headers.

## Ghi nhớ

**TLS termination** chuyển việc giải mã HTTPS sang proxy; backend có thể thấy HTTP nội bộ. **`Forwarded`/`X-Forwarded-*` giúp Spring Boot/Spring Security Servlet suy ra public scheme, host, port**, nhưng các header đó **không tự đáng tin**. Muốn sử dụng chúng an toàn, phải khóa direct backend access, xác định chính xác proxy được tin cậy, strip/rewrite header client tại edge và chọn đúng một chiến lược xử lý forwarded headers. Khi cả hai lớp **trust boundary + forwarding interpretation** khớp nhau, HTTPS redirect, OAuth2 callback, absolute URLs và cookie mới có thể hoạt động nhất quán mà không tạo lỗ hổng header spoofing.