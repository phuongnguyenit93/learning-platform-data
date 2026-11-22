# HTTPS, reverse proxy và URL công khai của ứng dụng

## 1. Vấn đề triển khai: trình duyệt thấy HTTPS, ứng dụng lại thấy HTTP

Trong môi trường phát triển, Spring Boot thường chạy tại `http://localhost:8080`. Khi triển khai thực tế, người dùng truy cập một địa chỉ công khai như `https://app.example.com`. Giữa người dùng và ứng dụng có thể có **reverse proxy**, load balancer, Kubernetes Ingress hoặc CDN chịu trách nhiệm nhận kết nối và **kết thúc TLS (TLS termination)**.

Một sơ đồ phổ biến:

```text
Browser / mobile client
        |
        | HTTPS:443, Host: app.example.com
        v
Internet-facing reverse proxy / load balancer
        |  (xác thực TLS, chính sách host và header)
        |
        | HTTP:8080 trên loopback hoặc mạng nội bộ bảo vệ
        | X-Forwarded-Proto: https
        | X-Forwarded-Host: app.example.com
        | X-Forwarded-Port: 443
        v
Spring Boot + Spring Security
        |
        v
Controller / Service / dữ liệu
```

Nếu ứng dụng chỉ nhìn thấy kết nối nội bộ HTTP mà **không nhận được thông tin địa chỉ gốc đã kiểm chứng**, nhiều chức năng có thể hoạt động sai:

- Redirect từ `/private` tới `http://localhost:8080/login` hoặc `http://app.example.com/login` thay vì `https://app.example.com/login`.
- OAuth2/OIDC tạo `redirect_uri` mang scheme, host, port hoặc path không khớp với callback đã đăng ký ở Identity Provider (IdP), gây lỗi `redirect_uri_mismatch`.
- Hệ thống tạo liên kết tuyệt đối trong email quên mật khẩu, xác nhận tài khoản, thông báo hoặc API JSON trỏ tới hostname nội bộ.
- Cookie phiên không được đặt thuộc tính `Secure` đúng chính sách hoặc browser không gửi cookie vì domain, path và SameSite không khớp.
- HSTS không xuất hiện theo dự đoán, hoặc proxy và ứng dụng cùng ghi header nhưng với chính sách khác nhau.
- Ứng dụng tin `X-Forwarded-Host` do client tự giả, dẫn tới **Host header poisoning**, liên kết đặt lại mật khẩu tới domain của kẻ tấn công, redirect sai hoặc nhầm tenant.

Cốt lõi không chỉ là “bật HTTPS”. Ta phải xác định rõ **URL công khai chuẩn, nơi TLS kết thúc, mạng/hạ tầng nào được tin để viết header gốc và cách Spring Boot sử dụng thông tin đó**.

Bài này dùng **Spring Boot 3.x / Spring Security 6.x, Java 17+ trên Servlet/MVC**, kèm ví dụ Nginx cùng máy với ứng dụng. Những khác biệt của WebFlux, Kubernetes và nhiều proxy được nêu riêng; không trộn cơ chế Servlet vào reactive.

## 2. Bốn thành phần của URL công khai

URL công khai (*public base URL*, đôi khi gọi external URL/canonical origin) là địa chỉ mà **người dùng thật sự phải dùng** để truy cập ứng dụng.

Ví dụ:

```text
https://app.example.com/portal
|____| |_____________| |_____|
scheme       host       path prefix

Port chuẩn HTTPS 443 thường không hiển thị trong URL.
```

Các thành phần phải nhất quán:

| Thành phần | Cấu hình public | Giá trị backend có thể nhìn thấy nếu không xử lý |
| --- | --- | --- |
| Scheme | `https` | `http` |
| Host | `app.example.com` | `127.0.0.1`, `backend` hoặc host nội bộ |
| Port | `443` (thường ẩn) | `8080` |
| Path prefix | `/portal` hoặc không có | Có thể đã bị proxy bỏ trước khi forward |
| Client IP | IP ở biên mạng đã xác minh | IP của proxy/CDN |
| Request target | `/private`, `/portal/private` | Đường dẫn đã được rewrite |

Hai dạng URL nên được phân biệt rõ:

- **URL nội bộ**: `http://127.0.0.1:8080`, chỉ để proxy trên cùng máy kết nối ứng dụng; không đưa vào email, HTML redirect, callback OIDC hoặc hướng dẫn cho người dùng.
- **URL công khai**: `https://app.example.com`, phải nằm trong cấu hình hạ tầng và được dùng nhất quán với certificate, DNS, allowed hosts và hệ thống xác thực.

Một ứng dụng không nên tùy tiện lấy `Host` của mọi HTTP request để tạo password-reset link. Với email, callback bảo mật và link công khai chủ động phát ra, nên dùng một **cấu hình public base URL có kiểm soát** hoặc một tenant-origin đã được kiểm tra theo allowlist. Forwarded header giúp framework hiểu request qua proxy, **không thay thế chính sách chọn origin đáng tin**.

## 3. HTTPS được thiết lập ở đâu?

### 3.1. TLS termination ở reverse proxy

Một kiến trúc thường gặp:

```text
Client --TLS/HTTPS--> Nginx, Ingress hoặc Load Balancer
Proxy  --HTTP-------> Spring Boot private backend
```

Hình thức này chấp nhận được **khi kênh backend nằm trong ranh giới mạng được bảo vệ**: loopback trên cùng máy, mạng nội bộ cô lập, security group hoặc network policy chỉ cho các proxy tin cậy tới cổng backend. Nếu đoạn proxy–backend đi qua hạ tầng hoặc mạng không được tin cậy, cần cân nhắc TLS/mTLS cho đoạn này thay vì mặc định HTTP luôn an toàn.

Một số hệ thống dùng **TLS pass-through** để ứng dụng trực tiếp nhận HTTPS; khi đó URL mà Spring thấy có thể đã đúng scheme. Một số dùng **re-encryption**: TLS ở client–proxy và TLS tiếp từ proxy–backend. Dù chọn kiến trúc nào, phải biết **ai xác minh certificate, ai cập nhật TLS config và ai chịu trách nhiệm về external origin**.

### 3.2. Certificate, HTTPS redirect và HSTS

Ở biên public, nên có:

- Certificate hợp lệ cho hostname, chuỗi CA đúng, cơ chế gia hạn/rotation được theo dõi; không dùng certificate tự ký cho khách hàng thật mà không có trust model riêng.
- TLS version/cipher phù hợp chính sách hiện hành, giới hạn HTTP plain và chuyển hướng sang HTTPS.
- Redirect **đúng hostname chuẩn**, tránh phản chiếu một Host header do client tùy ý gửi.
- HSTS sau khi chắc chắn site và các tài nguyên phụ thuộc đều hoạt động với HTTPS; cân nhắc kỹ `includeSubDomains` và `preload`.
- Đường nội bộ backend không được public trực tiếp, kể cả khi có Basic auth trên Spring Boot.

**HSTS không phải thay thế HTTPS.** HSTS hướng dẫn browser ưu tiên HTTPS cho host đã được ghi nhận; kết nối đầu tiên vẫn phải được TLS/certificate bảo vệ. Spring Security Servlet có hỗ trợ HSTS mặc định, nhưng header chỉ được phát khi request được xem là secure theo ngữ cảnh của nó. Nếu proxy kết thúc TLS nhưng ứng dụng nhận request như HTTP vì thiếu forwarded configuration, **đừng mặc định HSTS do Spring Security sẽ xuất hiện đúng như mong đợi**. Có thể chọn edge làm nơi phát HSTS, hoặc ứng dụng đã được cấu hình tin cậy; tránh hai nơi đưa chính sách mâu thuẫn.

### 3.3. Cookie an toàn sau TLS termination

Web login dùng session cookie nên kiểm tra:

| Thuộc tính | Vai trò | Cần lưu ý |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie qua HTTPS theo quy tắc của trình duyệt | Nên đặt rõ trên session production; không phụ thuộc việc backend thấy HTTP |
| `HttpOnly` | JavaScript không đọc được cookie | Không ngăn hoàn toàn các rủi ro khác như CSRF/XSS; chỉ là một lớp |
| `SameSite=Lax/Strict/None` | Giới hạn bối cảnh cross-site gửi cookie | `None` yêu cầu `Secure` trên browser hiện đại; cân nhắc OAuth2 callback/form flow |
| `Domain` | Phạm vi hostname nhận cookie | Tránh mở rộng sang mọi subdomain nếu không có nhu cầu; cookie host-only thường tốt hơn |
| `Path` | Phạm vi URL của cookie | Cẩn thận khi external app có prefix `/portal` hoặc reverse proxy rewrite |
| Session ID rotation/expiry | Hạn chế session fixation và phiên tồn tại quá lâu | Xác định timeout, logout và thu hồi phiên |

Proxy **không tự biến HTTP session cookie thiếu `Secure` thành cookie bảo mật**. Ngược lại, cấu hình `Secure=true` nhưng dùng HTTP local ở nơi không được thiết kế phù hợp có thể khiến browser không gửi lại cookie. Cần tách cấu hình local/test và production rõ ràng.

## 4. Forwarded và X-Forwarded-* có ý nghĩa gì?

Khi proxy nhận `https://app.example.com/private` rồi gửi nội bộ qua `http://127.0.0.1:8080/private`, backend muốn tạo redirect chính xác cần biết thông tin bên ngoài.

Hai họ header phổ biến:

1. Header chuẩn theo RFC 7239: `Forwarded`, ví dụ `Forwarded: for=192.0.2.20;proto=https;host=app.example.com`.
2. Các header tiền tố `X-Forwarded-*` phổ biến trên proxy/load balancer.

| Header | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `X-Forwarded-Proto` | `https` | Scheme bên ngoài |
| `X-Forwarded-Host` | `app.example.com` | Host public của request |
| `X-Forwarded-Port` | `443` | Port public |
| `X-Forwarded-For` | `192.0.2.20` | Thông tin IP nguồn qua chuỗi proxy |
| `X-Forwarded-Prefix` | `/portal` | Prefix bên ngoài khi proxy rewrite path |
| `Forwarded` | `for=192.0.2.20;proto=https;host=app.example.com` | Header chuẩn gộp nhiều thuộc tính |
| `Host` | `app.example.com` | HTTP Host trên request mà proxy chuyển tiếp; cũng cần được kiểm soát |

**Một header không tự trở nên đáng tin vì tên của nó.** Client công khai có thể gửi:

```http
GET /private HTTP/1.1
Host: app.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
X-Forwarded-Port: 443
Forwarded: proto=https;host=attacker.example
```

Nếu Spring Boot nhận trực tiếp request này hoặc proxy chuyển tiếp header giả mà không làm sạch, ứng dụng có thể suy ra một origin do attacker chọn. Hậu quả có thể gồm redirect tới domain khác, tạo URL trong email sai, nhầm tenant hoặc xử lý sai `isSecure()`.

**Quy tắc bảo vệ:** proxy ở **ranh giới tin cậy đầu tiên** phải loại bỏ hoặc ghi đè **cả header chuẩn `Forwarded` và những header `X-Forwarded-*` được hệ thống sử dụng**, bất kể client đã gửi gì. Backend chỉ chấp nhận kết nối từ proxy đáng tin. Khi có nhiều tầng proxy, phải có chính sách rõ tầng nào được tin để ghi và đọc chuỗi IP/host/scheme.

Một cấu hình `server.forward-headers-strategy=framework` mà backend vẫn công khai cổng 8080 ra Internet là **cấu hình nguy hiểm**. Bật xử lý forwarded headers không tự xác minh rằng người gửi header là proxy đáng tin.

## 5. Spring Boot xử lý forwarded headers như thế nào?

Trong Spring Boot 3.x, cấu hình chính là:

```properties
server.forward-headers-strategy=framework
```

Các chế độ:

| Giá trị | Ý nghĩa | Khi nào xem xét |
| --- | --- | --- |
| `none` | Không dùng forwarded headers để tái tạo request origin | Backend trực tiếp nhận HTTPS hoặc hạ tầng không có forwarded headers đáng tin |
| `native` | Dùng hỗ trợ sẵn của embedded web server như Tomcat/Jetty/Undertow, tùy loại và cấu hình | Hạ tầng gửi header đơn giản phù hợp web server; cần kiểm tra chính sách proxy được tin |
| `framework` | Dùng hỗ trợ Spring Framework: Servlet `ForwardedHeaderFilter`, WebFlux `ForwardedHeaderTransformer` | Khi cần Spring xử lý đầy đủ hơn thông tin scheme/host/port/prefix |

**Không bật đồng thời nhiều cách xử lý forwarded headers theo giả định “càng nhiều càng chắc”.** Chọn một chiến lược, xem cấu hình thực tế của web server và thử đủ redirect, link, cookie. Trong một số môi trường cloud được Spring Boot nhận diện, mặc định có thể là `native`; ở các môi trường khác mặc định có thể là `none`. Không dựa vào mặc định khi đây là một yêu cầu bảo mật của deployment.

Ở ứng dụng Servlet, `ForwardedHeaderFilter` có thể điều chỉnh các phương thức request như `getScheme()`, `getServerName()`, `getServerPort()` và `isSecure()` dựa trên forwarded headers; nó cũng hỗ trợ các tình huống `X-Forwarded-Prefix` tương ứng. Nhưng **filter không giải quyết việc kiểm tra nguồn tin của header**. Đây là trách nhiệm của kiến trúc network/trusted proxy.

Với Tomcat kết thúc TLS ở proxy, tài liệu Spring Boot còn lưu ý cấu hình:

```properties
server.tomcat.redirect-context-root=false
```

để `X-Forwarded-Proto` được xử lý trước một số redirect liên quan context root. Thuộc tính này không phải điều kiện thay thế cho việc cấu hình và kiểm tra proxy; chỉ áp dụng khi dùng Tomcat và tình huống tương ứng.

### 5.1. Tránh đăng ký ForwardedHeaderFilter hai lần

Nếu dùng `server.forward-headers-strategy=framework`, Spring Boot có thể cấu hình xử lý forwarded header thích hợp. Không nên đồng thời thêm một `@Bean ForwardedHeaderFilter` thủ công mà chưa xác định thứ tự và số lần xử lý; có thể dẫn đến hành vi khó dự đoán. Khi đang tự cấu hình filter, xem tài liệu Spring Framework về thứ tự trước các filter liên quan, dispatch types và biến thể `removeOnly` nếu chỉ muốn loại bỏ forwarded headers thay vì sử dụng.

### 5.2. Vì sao cần so sánh getRequestURL và public base URL?

Một controller hoặc framework tạo URL có thể lấy scheme, host và port từ `HttpServletRequest`. Khi forwarded headers được xử lý đúng, URL dựa trên request có thể trở về external origin. Tuy nhiên, những liên kết **không xuất phát từ một HTTP request** (gửi email từ background job) hoặc **nhạy cảm bảo mật** nên dùng cấu hình public base URL/validated tenant URL riêng, không suy luận từ HTTP Host tùy ý.

## 6. Mẫu cấu hình triển khai: Nginx cùng máy, Spring Boot chỉ nghe loopback

Giả sử:

- URL public cố định là `https://app.example.com` (không có path prefix).
- Nginx và Spring Boot chạy cùng một máy.
- Nginx nhận Internet ở 80/443, Spring Boot chỉ nghe `127.0.0.1:8080`.
- Certificate TLS đã được cấp và lưu ở đường dẫn triển khai thực tế.
- Trong ví dụ, Nginx là **biên tin cậy đầu tiên**, không có CDN/proxy ở phía trước.

Một cấu hình Nginx minh họa:

```nginx
server {
    listen 80;
    server_name app.example.com;

    # Chuyển HTTP sang hostname HTTPS cố định.
    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Public origin được kiểm soát; không phản chiếu
        # Host/X-Forwarded-Host từ một client bất kỳ.
        proxy_set_header Host             app.example.com;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # Loại bỏ header chuẩn do client có thể giả.
        proxy_set_header Forwarded "";

        # Không sử dụng external path prefix ở ví dụ này.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";

        # Đây là proxy biên: lấy IP kết nối tới Nginx,
        # không tin chuỗi X-Forwarded-For của client.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP        $remote_addr;
    }
}
```

**Đây là cấu hình khung cho topology được mô tả**, không phải file production hoàn chỉnh. Đường dẫn certificate chỉ có ý nghĩa khi file thật tồn tại và được quản lý quyền truy cập; có thể cần listener 443 mặc định từ chối host không mong muốn, timeouts, header size limit, HTTPS monitoring, log redaction, rotation và reload certificate.

**Lưu ý về header cleanup:** Nginx có thể chuyển tiếp những header HTTP khác mà không được ghi đè tường minh. Hệ thống thực tế phải rà soát toàn bộ các header được framework/gateway sử dụng (chuẩn `Forwarded` và biến thể `X-Forwarded-*`), xóa hoặc normalize ở ingress tin cậy. Đoạn cấu hình trên minh họa các trường cốt lõi cho origin đã chọn; nó **không phải tuyên bố rằng mọi header forward có thể có đều đã được xử lý bằng wildcard**.

Nếu phía trước Nginx còn CDN/load balancer, `$remote_addr` có thể là IP của tầng đó, không phải của người dùng cuối. Muốn dùng IP thật cho audit/rate-limit, phải khai báo **chính xác các hop/IP ranges được tin**, tránh bật “trust all forwarded for”. IP client được xác định từ chuỗi proxy khác với danh tính user trong `Authentication`.

### Vì sao tránh dùng proxy_set_header Host $http_host bừa bãi?

`$http_host` có thể phản ánh header Host từ client. Nếu Nginx nhận request có Host lạ rồi đưa nó vào backend hoặc forwarded headers, ứng dụng có thể tạo absolute URL do client điều khiển. Trong cấu hình một hostname cố định, gửi `app.example.com` rõ ràng đơn giản hơn. Với multi-tenant host động, phải có **danh sách host/tenant đã xác minh** và route tới đúng tenant, không chấp nhận mọi Host tùy ý.

### Kết nối nội bộ và firewall

Đặt trong `application-prod.properties`:

```properties
server.address=127.0.0.1
server.port=8080
```

Ví dụ này chỉ áp dụng khi Nginx và Spring Boot **cùng host**. Trong container/Kubernetes, `127.0.0.1` trong một pod/container có thể không liên thông với reverse proxy chạy ở nơi khác. Khi đó backend có thể cần listen trong network namespace/container và dùng firewall, security groups hoặc NetworkPolicy để **chỉ proxy/ingress tin cậy mới kết nối được**.

Bài toán không phải nhất thiết backend luôn dùng 127.0.0.1, mà là **backend không được có đường Internet trực tiếp có thể gửi forwarded header giả mạo**.

## 7. Ví dụ Java 17+ kiểm tra URL được ứng dụng nhận diện

Để có bài kiểm tra lặp lại được, ta tạo một ứng dụng Spring Boot Servlet. Nó có:

- `GET /public`: endpoint công khai để kiểm tra TLS và routing.
- `GET /private`: endpoint yêu cầu form login, dùng để quan sát redirect.
- `GET /admin/diagnostics`: chỉ cho `ROLE_ADMIN`, trả thông tin request mà **Spring đã diễn giải** (scheme, host, port, secure) và giá trị public base URL cấu hình.
- Tài khoản demo `viewer` và `admin` lưu trong bộ nhớ; không dùng cho production.

Tạo Spring Boot 3.x / Spring Security 6.x / Java 17+, dependencies `Spring Web` và `Spring Security`. Tệp:

```text
src/main/java/demo/publicurl/PublicUrlApplication.java
```

```java
package demo.publicurl;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PublicUrlApplication {

    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Routes {
        private final String configuredPublicBaseUrl;

        Routes(
                @Value("${app.public-base-url}") String publicUrl) {
            this.configuredPublicBaseUrl = publicUrl;
        }

        @GetMapping("/public")
        public Map<String, String> publicEndpoint() {
            return Map.of("status", "ready");
        }

        @GetMapping("/private")
        public Map<String, String> privateEndpoint(
                Authentication authentication) {
            return Map.of(
                "message", "authenticated",
                "actor", authentication.getName()
            );
        }

        @GetMapping("/admin/diagnostics")
        public Map<String, Object> diagnostics(
                HttpServletRequest request) {
            return Map.of(
                "scheme", request.getScheme(),
                "host", request.getServerName(),
                "port", request.getServerPort(),
                "secure", request.isSecure(),
                "configuredPublicBaseUrl",
                    configuredPublicBaseUrl
            );
        }
    }
}
```

Đây là một chương trình **chạy được trong dự án Spring Boot có classpath Spring**, không thể biên dịch chỉ bằng `javac PublicUrlApplication.java`. `@Value` đọc giá trị cấu hình của ứng dụng, không phải dữ liệu do browser gửi.

**Quan trọng:** endpoint `/admin/diagnostics` phục vụ học tập và điều tra có kiểm soát; trong sản phẩm thật nên loại bỏ sau khi nghiệm thu, hoặc chỉ cho nhóm vận hành được phép và hạn chế thông tin. Không trả raw headers, Cookie, Authorization token hoặc internal network configuration cho client.

### 7.1. Cấu hình chạy local

`src/main/resources/application.properties`:

```properties
spring.application.name=public-url-lab
server.port=8080
app.public-base-url=http://localhost:8080

# Không tin forwarded headers khi app nhận request trực tiếp ở local.
server.forward-headers-strategy=none
```

Chạy:

```bash
./gradlew bootRun

# Windows PowerShell:
# .\gradlew.bat bootRun
```

Với cấu hình local, `http://localhost:8080/public` nhận **200** cùng JSON `{"status":"ready"}`. `http://localhost:8080/private` khi chưa xác thực thường trả **302** tới trang login. Sau khi đăng nhập bằng `viewer` hoặc `admin`, `/private` trả tên tài khoản đã xác thực.

### 7.2. Cấu hình production sau proxy

`src/main/resources/application-prod.properties`:

```properties
# Chỉ cho ví dụ Nginx cùng máy.
server.address=127.0.0.1
server.port=8080

# Chỉ bật sau khi proxy đáng tin xóa/ghi đè
# header forwarded từ request Internet.
server.forward-headers-strategy=framework

# Hữu ích khi Tomcat hoạt động sau TLS termination.
server.tomcat.redirect-context-root=false

# Chính sách cookie cho HTTPS public.
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Nguồn tin cậy để tạo link public chủ động.
app.public-base-url=https://app.example.com
```

Chạy profile production trong môi trường **thực sự có reverse proxy**:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

Nếu chưa có Nginx/TLS, không dùng profile này để kiểm thử browser HTTP local: backend chỉ bind loopback và cookie `Secure` có thể không hoạt động theo kỳ vọng trên HTTP. Nhớ cấu hình certificate/DNS/proxy trước khi đánh giá kết quả.

**Vì sao đặt public URL riêng dù đã bật forwarded headers?** Forwarded headers giúp Spring diễn giải **request đến qua proxy**. Nhưng nếu ứng dụng gửi email từ scheduled job hoặc tạo redirect/link bảo mật không dựa trên request, nó vẫn cần một origin đã được cấu hình và kiểm soát. Chỉ nhận `X-Forwarded-Host` để dựng mọi liên kết tuyệt đối có thể gây rủi ro Host poisoning nếu một hop cấu hình sai.

### 7.3. Khi dùng nhiều môi trường

Có thể tách public base URL:

```text
Local:    http://localhost:8080
Staging:  https://staging.example.com
Prod:     https://app.example.com
```

Mỗi môi trường nên có hostname, certificate, callback OAuth2, cookie scope và secret registration tương ứng; không dùng chung callback/credential của production ở development. Nếu dùng secret manager/config server, bảo vệ quyền thay đổi `app.public-base-url` vì nó có thể ảnh hưởng đường dẫn bảo mật gửi cho người dùng.

## 8. Kiểm tra thực tế từ phía ngoài reverse proxy

Sau khi DNS, TLS và Nginx chạy, thử từ máy **không có quyền kết nối backend trực tiếp**:

```bash
# 1. Certificate hợp lệ, endpoint public trả 200.
curl -i https://app.example.com/public

# 2. HTTP ở public edge phải chuyển sang HTTPS.
curl -i http://app.example.com/public

# 3. Endpoint private chưa có phiên -> redirect login.
curl -i https://app.example.com/private

# 4. Xem chỉ các response headers.
curl -I https://app.example.com/public
```

Các kết quả dự kiến:

| Test | Điều cần thấy | Nếu khác |
| --- | --- | --- |
| HTTPS public | 200, JSON, không lỗi certificate | Kiểm tra DNS/cert/SNI/proxy route/app health |
| HTTP public | 301/308 tới `https://app.example.com/...` | Kiểm tra listener port 80 và redirect host |
| HTTPS private anonymous | 302 tới login (do form login) | Kiểm tra SecurityFilterChain, session, entry point |
| Redirect Location | Không xuất hiện `localhost:8080`/`http://`/private host | Kiểm tra forwarded strategy và proxy headers |
| Cookie sau login | `Secure`, `HttpOnly`, SameSite/path theo thiết kế | Kiểm tra cookie properties, HTTPS, prefix |
| HSTS | Header phù hợp chính sách trên HTTPS | Kiểm tra owner phát header và `isSecure()` |
| Backend port | Không truy cập được từ Internet | Kiểm tra binding/firewall/ingress restrictions |

**Không dùng `curl -k` để tuyên bố HTTPS đã đúng.** `-k` bỏ kiểm tra certificate và có thể che lỗi hostname hoặc trust chain. Chỉ dùng `-k` trong môi trường test đã biết rõ lý do, không xem nó là bằng chứng an toàn.

`curl -I` gửi HEAD, có thể được xử lý khác GET nếu endpoint hoặc filter tùy chỉnh. Nếu thiếu header trong HEAD, thử `curl -i` với GET trước khi kết luận; đặc biệt với redirect và cookie khi login.

### 8.1. Kiểm tra header trực tiếp bằng cách giả mạo

Mục tiêu bảo mật của topology này là: **một request Internet không thể tự chọn external scheme/host bằng cách gửi header giả**.

Ví dụ một client có thể thử:

```bash
curl -i https://app.example.com/private \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: host=attacker.example;proto=http'
```

Khi Nginx ở biên thực hiện normalizing đúng và ứng dụng chỉ nhận request qua Nginx, redirect/login response **không được dùng `attacker.example`**, cũng không được quay về scheme `http`. Lưu ý lệnh này chỉ thử một tập header; bài nghiệm thu security phải kiểm tra mọi header hạ tầng đã quyết định sử dụng, bao gồm biến thể `X-Forwarded-Prefix` nếu có.

**Thử nghiệm này không thay thế network ACL.** Kể cả proxy làm sạch header đúng, attacker có thể giả header khi cổng backend 8080 bị mở trực tiếp. Cần xác minh từ bên ngoài rằng backend không thể truy cập ngoài tuyến được phép.

### 8.2. Xem thông tin trong diagnostics

Đăng nhập tài khoản `admin` qua browser trên `https://app.example.com/login`, sau đó mở `https://app.example.com/admin/diagnostics`. Với proxy/Boot setup đúng, nội dung JSON có dạng:

```json
{
  "scheme": "https",
  "host": "app.example.com",
  "port": 443,
  "secure": true,
  "configuredPublicBaseUrl": "https://app.example.com"
}
```

Thứ tự key không cố định và cấu hình cổng/host có thể khác theo môi trường thực. Giá trị này chỉ là **kỳ vọng với topology trong bài**, không phải stdout đã đo. Sau khi kiểm tra, xóa hoặc vô hiệu endpoint diagnostics trong production để tránh lộ thông tin vận hành không cần thiết.

Nếu thấy `scheme=http`, `secure=false`, host là `127.0.0.1` hoặc port `8080`, cần xem Boot profile, `server.forward-headers-strategy`, Nginx `proxy_set_header`, server route và thứ tự/proxy trust. Đừng sửa bằng cách hard-code `request.isSecure()=true` ở một controller: vấn đề nằm ở nguồn thông tin gốc và tin cậy hạ tầng.

## 9. Kiểm thử tích hợp Spring Security với forwarded headers

Đối với Spring Boot 3.x Servlet, có thể dùng `MockMvc` và `spring-security-test` để kiểm tra app diễn giải request theo forwarded headers trong một **context test được cấu hình chủ động**. Thêm dependencies test vào `build.gradle` của dự án Initializr:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo file:

```text
src/test/java/demo/publicurl/PublicUrlApplicationTests.java
```

```java
package demo.publicurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "server.forward-headers-strategy=framework",
    "app.public-base-url=https://app.example.com"
})
@AutoConfigureMockMvc
class PublicUrlApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void forwardedOriginIsObservedForAdmin() throws Exception {
        mvc.perform(
            get("/admin/diagnostics")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "app.example.com")
                .header("X-Forwarded-Port", "443")
                .with(user("admin").roles("ADMIN"))
        )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scheme").value("https"))
            .andExpect(jsonPath("$.host").value("app.example.com"))
            .andExpect(jsonPath("$.port").value(443))
            .andExpect(jsonPath("$.secure").value(true))
            .andExpect(jsonPath("$.configuredPublicBaseUrl")
                .value("https://app.example.com"));
    }

    @Test
    void nonAdminCannotSeeDiagnostics() throws Exception {
        mvc.perform(get("/admin/diagnostics")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

**Để tạo file Java thực tế**, viết các import ngắt dòng trong snippet thành các câu lệnh một dòng (và bỏ phiên bản ngắt dòng):

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Java parser cho phép xuống dòng giữa các token, nhưng cách viết một dòng làm bản copy/paste rõ ràng. Chạy:

```bash
./gradlew test
```

**Kỳ vọng:** bốn test pass trên bộ dependency và cơ chế auto-config được nêu, khi filter forwarding của Boot thật sự được nạp vào MockMvc. Đây là kỳ vọng mã, **không phải kết quả đã biên dịch/chạy thực tế trong tài liệu**. Nếu test không thấy forwarded origin, xem `ForwardedHeaderFilter` có được đăng ký và áp dụng trong test context/MockMvc không.

Các bài test này **không chứng minh proxy đã loại bỏ header giả**: chúng chủ động cung cấp `X-Forwarded-*` cho Spring và kiểm tra framework hiểu thế nào. Để chứng minh **hạ tầng chống spoofing**, cần test HTTP thật qua Nginx/Ingress và xác minh rằng người dùng ngoài Internet không vào được backend trực tiếp.

## 10. OAuth2/OIDC redirect URI sau proxy

Trường hợp hay gặp nhất là **OIDC login** hoặc OAuth2 Authorization Code flow. Mặc định, Spring Security OAuth2 Login sử dụng template redirect URI dạng:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

Với app public `https://app.example.com` và client registration `corp`, callback cần được IdP đăng ký chính xác là:

```text
https://app.example.com/login/oauth2/code/corp
```

Nếu Spring lấy scheme/host từ backend sai, nó có thể tạo:

```text
http://127.0.0.1:8080/login/oauth2/code/corp
http://app.example.com/login/oauth2/code/corp
https://app.example.com:8080/login/oauth2/code/corp
```

Những giá trị này không khớp với redirect URI đã đăng ký và khiến IdP từ chối hoặc trình duyệt bị đưa tới địa chỉ không thể truy cập. **Đừng sửa bằng cách nới wildcard callback**; phải sửa nguyên nhân external origin.

Ví dụ cấu hình client registration trong dự án Spring Boot có dependency **OAuth2 Client** và IdP OIDC thật:

```properties
spring.security.oauth2.client.registration.corp.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.scope=openid,profile
spring.security.oauth2.client.registration.corp.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.provider.corp.issuer-uri=${OIDC_ISSUER_URI}
```

Trong đoạn properties, các chuỗi như `${OIDC_CLIENT_ID}` là **placeholder môi trường** và sẽ được diễn giải theo cú pháp Spring sau khi copy từ bài; không đặt secret thật vào repository. Đây là **cấu hình minh họa có điều kiện**, không làm chương trình form login ở mục 7 tự biến thành OIDC client nếu chưa thêm starter OAuth2 Client, provider hợp lệ và `oauth2Login(...)` tương ứng.

**Một phương án bảo thủ** khi sản phẩm chỉ có một public origin là dùng redirect URI cố định `https://app.example.com/login/oauth2/code/corp`, nhưng vẫn phải bảo đảm Spring Security matcher/callback và proxy path khớp; đừng dùng dynamic host từ request chưa kiểm chứng.

### 10.1. OAuth callback là một endpoint an ninh

OIDC không chỉ cần đúng hostname: callback còn phụ thuộc `state`, việc đổi authorization code, ID token validation, OIDC nonce (theo cấu hình), session/cookie trong browser và thời gian sống của authorization request. Vì vậy khi proxy sửa scheme/host/path, callback có thể bị lỗi ở **nhiều tầng**. Không vô hiệu `state`/nonce hoặc tắt CSRF chỉ vì login không hoàn tất.

Nếu IdP đặt cookie hoặc dùng cross-site redirect/form-post, cần kiểm tra `SameSite` của **cookie phiên ứng dụng**. Không thay `SameSite=None` trên mọi cookie mà chưa hiểu luồng và hậu quả CSRF. Với callback kiểu GET thông thường, hành vi có thể khác callback form-post, nên thử bằng trình duyệt thực.

### 10.2. SAML và email link cũng có vấn đề tương tự

SAML 2.0 ACS URL, metadata entity descriptors hoặc các link xác minh tài khoản/reset password cũng cần public host/scheme/path chính xác. Không dùng URL nội bộ được dựng từ `request.getServerName()` chưa được bảo vệ cho các thông điệp gửi ra ngoài. Trong hệ thống nhiều tenant, URL ngoài có thể phụ thuộc tenant, nhưng chỉ chọn từ hostname được đăng ký và kiểm soát.

## 11. Ứng dụng có path prefix /portal: lỗi khó nhận biết

Một proxy có thể publish:

```text
Public:  https://app.example.com/portal/private
Backend: http://127.0.0.1:8080/private
```

Ở đây `/portal` là **prefix bên ngoài** và proxy đã bỏ nó trước khi gửi backend. Spring nếu không biết prefix có thể tạo redirect tới `https://app.example.com/login` thay vì `https://app.example.com/portal/login`.

`X-Forwarded-Prefix: /portal` có thể giúp Spring Framework dựng lại context path cho request theo topology được hỗ trợ. Tuy nhiên, **prefix forwarding không phải một phép đổi đường dẫn tổng quát áp dụng giống nhau cho mọi proxy, Servlet, OAuth callback và security matcher**.

Cần quyết định một chiến lược nhất quán:

1. Giữ context path ứng dụng đúng bằng prefix public khi thích hợp, và proxy giữ nguyên prefix; hoặc
2. Proxy bỏ prefix trước khi gửi backend, đồng thời ghi `X-Forwarded-Prefix` đã được kiểm soát; hoặc
3. Tạo route/callback/link theo cấu hình external base URL cố định, được kiểm thử end-to-end.

Không kết hợp bừa bãi cả `server.servlet.context-path=/portal`, rewrite bỏ prefix và `X-Forwarded-Prefix=/portal` rồi kỳ vọng mọi URL tự đúng; rất dễ xảy ra redirect nhân đôi `/portal/portal` hoặc mất prefix. Mọi trường hợp phải thử `/login`, static resources, logout, OAuth2 callback và đường dẫn trở lại sau login.

Một test quan trọng:

```text
GET https://app.example.com/portal/private
-> 302 Location: https://app.example.com/portal/login
-> trang login / form action / CSS / callback đều giữ /portal
```

Đây là **kỳ vọng kiến trúc**, không phải output được bảo đảm chỉ vì một thuộc tính forward header đã được bật.

## 12. Nhiều proxy/CDN/Kubernetes Ingress: ranh giới tin cậy di chuyển

Sơ đồ nhiều tầng:

```text
Client
  -> CDN / WAF
  -> cloud load balancer
  -> Kubernetes Ingress / reverse proxy
  -> Spring Boot pod
```

Mỗi hop có thể sửa Host, scheme, port, đường dẫn và IP nguồn. Cần định nghĩa rõ:

- **Hop nào là trust boundary đầu tiên?** Nó phải xóa header giả do Internet gửi và tạo dữ liệu gốc đáng tin.
- **Hop nào chuẩn hóa forwarded headers trước backend?** Chỉ truyền nguồn sự thật đã xác minh, không nối thêm chuỗi bất kỳ từ client.
- **Backend nhận kết nối từ đâu?** Dùng private networks, security groups, NetworkPolicy, service mesh identity/mTLS theo mô hình.
- **TLS ở hop nào?** Nếu có TLS termination ở CDN và thêm TLS ở ingress, đừng truyền `X-Forwarded-Proto=http` chỉ vì hop cuối kết nối HTTP với pod.
- **Ai phát HSTS?** Edge hoặc app, giữ một chính sách nhất quán.
- **Host nào được chấp nhận?** Tránh dùng mọi host tùy ý làm origin của link bảo mật hoặc tenant identity.
- **IP nguồn được phục hồi thế nào?** X-Forwarded-For có thể chứa nhiều hop, phải tính theo proxy tin cậy, không tin phần đầu chuỗi do client gửi.

Với Spring Boot WebFlux, chiến lược `server.forward-headers-strategy=framework` được xử lý bởi cơ chế Spring Framework phù hợp reactive như `ForwardedHeaderTransformer`. **Không tự thêm Servlet `ForwardedHeaderFilter` vào ứng dụng WebFlux**; kiểm tra pipeline `WebFilter` và reactive request tương ứng.

### Multiple domains và tenant

Nếu mỗi tenant có hostname riêng, ví dụ `https://tenant-a.example.com` và `https://tenant-b.example.com`, không đơn giản lấy raw `Host` làm bằng chứng tenant. Cần một registry hostname–tenant đã được kiểm chứng, certificate phù hợp và bước xác định tenant sau khi ingress xác thực/normalize host. Quyền truy cập vẫn phải kiểm tra user thuộc tenant đó; một request có host hợp lệ không làm caller có quyền xem dữ liệu tenant.

## 13. Những lỗi hay gặp và cách gỡ

### 13.1. Redirect loop giữa HTTP và HTTPS

Triệu chứng: browser liên tục đi giữa một URL HTTP và HTTPS hoặc `ERR_TOO_MANY_REDIRECTS`. Có thể proxy redirect HTTP sang HTTPS nhưng app vẫn nghĩ request là HTTP rồi redirect lại, hoặc thứ tự forwarded header xử lý sai. Kiểm tra `X-Forwarded-Proto` từ proxy, Boot strategy và custom HTTPS redirect logic. Đừng tắt HTTPS enforcement để che loop; cần sửa sự khác nhau về scheme.

### 13.2. Location chứa localhost hoặc :8080

Kiểm tra application đang nhận header forward chưa, cấu hình `server.forward-headers-strategy` thực tế, có host cố định được proxy gửi và có app code tự tạo URL bằng `localhost` không. Nếu là email từ background job, dùng `app.public-base-url` đáng tin thay vì nhờ request context vốn không tồn tại.

### 13.3. OIDC báo redirect_uri_mismatch

Đối chiếu **từng ký tự** scheme, host, port, prefix, callback path và registration ID với URI đăng ký ở IdP. Không mở wildcard callback; fix routing và forwarded strategy. Xem cả cookie/session khi callback bị lỗi state.

### 13.4. Cookie không được lưu hoặc login bị mất phiên

Xem `Set-Cookie` trong DevTools: Secure, HttpOnly, SameSite, Domain, Path. Đối chiếu hostname ngoài với internal host, HTTP/HTTPS, path prefix. Không log session ID để debug; dùng request/correlation ID không nhạy cảm.

### 13.5. HSTS không xuất hiện

Kiểm tra request ngoài thực sự HTTPS và nơi dự kiến phát HSTS (edge hay Spring). Nếu Spring Security chịu trách nhiệm, cần request được coi là secure. Không bật HSTS preload hoặc includeSubDomains trước khi biết mọi subdomain sẵn sàng HTTPS; chính sách này có thể gây gián đoạn dài hạn.

### 13.6. Client giả X-Forwarded-Host tạo redirect attacker.example

Đây là **lỗ hổng trust boundary**, không phải chỉ một bug format. Kiểm tra đường direct-to-backend, ingress normalize, standard `Forwarded` và `X-Forwarded-*`, host allowlist. Sửa ở ranh giới proxy và cấu hình generated security links, không chỉ lọc chuỗi `attacker.example` trong một controller.

### 13.7. Có HTTPS nhưng API vẫn trả 403/401

HTTPS không cấp quyền. Kiểm tra authentication/session/cookie, CSRF, token audience/scope, AuthorizationManager và role/owner/tenant như bình thường. Nếu proxy bỏ header `Authorization` hoặc cookie thì có thể gây 401; nếu POST thiếu CSRF token có thể gây 403. Phân biệt lỗi transport, authentication và authorization.

### 13.8. Redirect từ proxy khác redirect của Spring

Proxy có thể tự tạo 301/308, trong khi Spring Security tạo 302 tới login. `curl -i` không theo redirect giúp quan sát từng bước. Khi có nhiều redirect, dùng log proxy và ứng dụng với request ID an toàn để phân biệt lớp nào phát `Location`.

### 13.9. Trình duyệt báo Mixed Content

Trang HTTPS tham chiếu `http://app.example.com/assets/...` hoặc gọi API HTTP. Kiểm tra base URL trong template, frontend build/runtime config, static resource URL và phía proxy. Không dùng `http://127.0.0.1:8080` làm URL API cho browser; từ máy người dùng địa chỉ đó là loopback của **máy họ**, không phải server.

### 13.10. Spring Security HSTS và edge HSTS mâu thuẫn

Hai lớp phát giá trị `Strict-Transport-Security` khác nhau gây khó giám sát. Xác định nơi chịu trách nhiệm, kiểm tra header response thực tế ngoài Internet và chính sách cho mọi domain. Không tin rằng app đã tạo header nếu edge có thể thêm, sửa hoặc loại bỏ trước khi client nhận.

## 14. Checklist nghiệm thu deployment

- [ ] DNS và certificate hợp lệ cho đúng public hostname.
- [ ] HTTP public chuyển sang HTTPS chuẩn; không phản chiếu host tùy ý.
- [ ] Xác định public scheme/host/port/path prefix và nơi lưu cấu hình canonical.
- [ ] Proxy được tin loại bỏ/ghi đè header `Forwarded` và `X-Forwarded-*` do Internet gửi.
- [ ] Backend không truy cập trực tiếp từ Internet; internal hop được bảo vệ.
- [ ] Spring Boot dùng **một** forwarded-header strategy phù hợp và đã kiểm thử.
- [ ] URL tạo từ request, Location của 302 và link email không lộ internal host/port.
- [ ] Cookie phiên có Secure/HttpOnly/SameSite/Domain/Path đúng môi trường.
- [ ] HSTS có chính sách rõ và thực sự xuất hiện đúng tại HTTPS public edge.
- [ ] CSRF vẫn bảo vệ thao tác browser thay đổi trạng thái, không bị tắt chỉ để chữa 403.
- [ ] OIDC/OAuth2 redirect URI đúng tuyệt đối, callback và state/session hoạt động.
- [ ] Path prefix `/portal` không bị mất hoặc lặp trong login/logout/static assets.
- [ ] Multi-tenant host mapping và authorization kiểm tra độc lập, không tin raw Host.
- [ ] Thử request giả `X-Forwarded-Host/Proto/Forwarded` qua public edge.
- [ ] Không dùng `curl -k` làm bằng chứng certificate đúng.
- [ ] Kiểm tra 401/403/302/200 và status/Location/Set-Cookie từ ngoài proxy, không chỉ test controller.
- [ ] Giảm DEBUG/TRACE sau điều tra; tránh log credential, token, cookie và dữ liệu cá nhân.

**Điểm cần nhớ:** trong deployment sau reverse proxy, Spring Security có thể bảo vệ đúng danh tính và role nhưng vẫn sinh **redirect, cookie, callback hoặc link sai** nếu ứng dụng không biết external origin. Hãy quản lý public URL như một phần của cấu hình bảo mật, chỉ tin forwarded headers từ proxy đã được kiểm soát và kiểm thử **toàn tuyến browser → proxy → Spring Boot → browser**.

### Tài liệu chính thức

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Framework — Forwarded Headers và ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Security — Security HTTP Response Headers và HSTS](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Advanced OAuth2 Login / Redirection Endpoint](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
