# CORS không thay thế kiểm tra danh tính hoặc bảo vệ CSRF

## 1. Mục tiêu: phân biệt ba lớp bảo vệ khác nhau

Trong một ứng dụng Spring Boot, developer thường gặp cả ba câu hỏi:

1. **Origin nào được phép để JavaScript trong browser đọc response từ server của tôi?** Đây là bài toán **Cross-Origin Resource Sharing (CORS)**.
2. **Request này đến từ ai, đã đăng nhập hoặc chứng minh danh tính chưa?** Đây là bài toán **authentication** của Spring Security.
3. **Một request dùng phiên đăng nhập có thật do người dùng chủ động thực hiện không, hay browser bị một website khác dụ gửi?** Đây là bài toán **Cross-Site Request Forgery (CSRF)**.

Một câu trả lời sai rất thường gặp là: “Tôi đã cấu hình CORS chỉ cho domain frontend, vậy API an toàn, không cần Spring Security login hoặc CSRF nữa”. **Sai.** CORS không xác minh mật khẩu, access token, session, user role hay CSRF token. CORS chủ yếu là chính sách browser áp dụng để quyết định **mã JavaScript từ origin khác có thể đọc response hay không**, và với request có preflight thì liệu browser có gửi request chính hay không. Server vẫn phải tự xác thực, phân quyền và bảo vệ hành động thay đổi trạng thái.

Sau bài học, bạn có thể:

- Phân biệt *same-origin* và *same-site*, một CORS *preflight* với request thực, authentication với authorization, và CORS với CSRF.
- Diễn giải ba luồng: **origin được allow nhưng chưa login**; **đã có session nhưng thiếu CSRF token**; **có cả session lẫn CSRF token hợp lệ**.
- Cấu hình Spring Security Servlet bằng `http.cors(...)`, `CorsConfigurationSource`, `authorizeHttpRequests(...)` và `csrf(...)` mà không làm ba lớp bảo vệ thay thế lẫn nhau.
- Sử dụng `CsrfToken` qua `/csrf` endpoint, hiểu vì sao token cần refresh sau login/logout.
- Kiểm thử các trường hợp bằng MockMvc: preflight, origin allowlist, truy cập chưa xác thực, POST thiếu CSRF, POST đủ CSRF.
- Nhận ra các cấu hình nguy hiểm như wildcard origin + credentials, tự reflect mọi `Origin`, tắt CSRF chỉ để tránh 403 hoặc trả 200 chỉ vì preflight hợp lệ.
- Lựa chọn đúng cho **cookie-based browser app** và **API bearer token không dựa trên cookie**.

Bài trình bày Spring Security **Servlet/Spring MVC**. Với WebFlux, các lớp và chain tương ứng là `SecurityWebFilterChain`, `CorsWebFilter` và CSRF reactive; không thể sao chép nguyên cấu hình Servlet vào WebFlux.

## 2. Bảng phân biệt: CORS, authentication, authorization, CSRF

| Cơ chế | Câu hỏi cốt lõi | Dữ liệu/thành phần | Điều không làm được |
| --- | --- | --- | --- |
| **CORS** | Browser script ở origin A có thể truy cập response từ origin B không? | `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Credentials`, `CorsFilter` | Không chứng minh ai gọi API; không cấp role; không thay CSRF |
| **Authentication** | Ai đang gọi? Có credentials hợp lệ không? | `JSESSIONID`/`SecurityContext`, password, bearer token, mTLS, API key… | Không tự quyết định user được phép sửa mọi object |
| **Authorization** | Principal này có quyền với action/object không? | `Authentication`, authorities, policy, `AuthorizationFilter` | Không kiểm tra website phát sinh request hay ý định của user |
| **CSRF protection** | Request thay đổi trạng thái dùng ambient credentials có mang bằng chứng chống giả mạo hợp lệ không? | CSRF token, Origin/Referer/Fetch Metadata policy, SameSite và kiểm tra phía server | Không xác minh danh tính thay session/login; không cho phép JavaScript đọc cross-origin response |

Ví dụ một request có thể:

- **CORS được chấp nhận nhưng chưa xác thực:** script trên frontend tin cậy được browser cho phép nhận response, nhưng server vẫn trả login redirect hoặc 401 vì không có session.
- **Đã xác thực nhưng bị chặn CSRF:** browser gửi cookie phiên hợp lệ, user có đủ quyền, nhưng `POST` thiếu token khiến server trả 403.
- **Có đủ authentication và CSRF nhưng CORS không cho origin hiện tại:** backend có thể thực thi kiểm tra auth/CSRF và tạo response, song JavaScript ở origin không được allow sẽ không được browser đọc response; với preflight không được chấp thuận, browser còn không gửi request chính.
- **CORS allow và authentication thành công nhưng authorization thất bại:** user đã login, request hợp lệ, nhưng thiếu `ROLE_ADMIN` → 403 theo policy.

**CORS thành công không bằng “đã login”. `Origin` không phải credential. CSRF token cũng không tự biến anonymous user thành một principal đã xác thực.**

## 3. Origin và site khác nhau ra sao?

Theo Web security, một **origin** được xác định bởi bộ **scheme + hostname + port**. Cùng site (theo cách trình duyệt xác định *schemeful site*) thường dựa vào scheme và registrable domain, không đồng nghĩa cùng origin.

Giả sử:

```text
Frontend: https://app.example.com
Backend:  https://api.example.com
Attacker: https://evil.example.net
```

- Frontend và backend **khác origin** vì hostname khác nhau. `fetch("https://api.example.com/...")` từ frontend có thể cần CORS.
- Frontend và backend thường được coi là **cùng site** (HTTPS và cùng registrable domain `example.com`), dù khác origin. Đây là điểm rất quan trọng khi phân tích cookie `SameSite`.
- Attacker ở `evil.example.net` khác cả origin lẫn site. Nếu browser có session cookie phù hợp chính sách, một số kiểu request có thể được kích hoạt từ website đó, dù script attacker không được đọc response.
- `https://app.example.com` và `http://app.example.com` khác origin vì scheme khác; với schemeful site, chúng cũng khác site.
- `https://app.example.com:443` và `https://app.example.com:8443` khác origin vì port khác.

Origin **không** bao gồm path, query hoặc fragment. Vì vậy:

```text
https://app.example.com/dashboard
https://app.example.com/settings
```

là cùng một origin.

**Không nên dùng regex đơn giản như `endsWith("example.com")` để xác thực origin**, vì hostname giả hoặc origin có port/scheme lạ có thể lọt qua. Nếu ứng dụng nhận thông tin proxy, chỉ tin forwarded headers từ reverse proxy được quản lý; không coi mọi `Origin` hoặc `Host` do client tự khai là danh tính đáng tin cậy.

## 4. Vì sao CORS không phải authentication?

Một browser request tới API có thể kèm:

```http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
```

Nếu backend cấu hình allow origin đó, response có thể bao gồm:

```http
HTTP/1.1 302 Found
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Location: /login
```

CORS headers hợp lệ **không làm HTTP status thành 200**. Trong ví dụ Spring `formLogin` dùng session cookie, request chưa login vẫn bị chuyển tới trang login.

Đặc biệt, `Origin: https://app.example.com` chỉ cho biết origin **được browser khai báo** khi tạo request. Ngoài browser, `curl`, Postman và các client tùy chỉnh có thể đặt header `Origin` tùy ý. Vì vậy tuyệt đối không viết:

```java
// SAI - trích đoạn phản ví dụ, không dùng:
if ("https://app.example.com".equals(
        request.getHeader("Origin"))) {
    // Coi là người dùng đã đăng nhập và cho phép thao tác
}
```

Authentication phải xác minh credential từ hệ thống tin cậy, ví dụ session được tạo sau password/OIDC login, JWT có chữ ký hợp lệ với issuer/audience, API key được đối chiếu verifier, mTLS client certificate hoặc phương thức khác.

**Authorization cũng khác authentication.** Một user đã login có thể không đủ quyền sửa một bản ghi của tenant khác. Cần `hasRole(...)`, `hasAuthority(...)` và kiểm tra object ownership ở tầng service. Việc frontend thuộc allowlist không làm những kiểm tra này biến mất.

## 5. Vì sao CORS không phải CSRF protection?

CSRF nhắm vào **hành động được thực hiện dưới quyền của user mà user không chủ động yêu cầu**. Với session-cookie web app, browser có thể tự đính kèm cookie phiên vào một request khi điều kiện cookie/SameSite cho phép.

Kịch bản:

1. User đăng nhập `https://bank.example.com` và có cookie phiên.
2. User mở trang attacker `https://evil.example.net`.
3. Trang attacker dụ browser gửi POST đến endpoint thay đổi thông tin/thực hiện giao dịch.
4. Nếu backend chỉ kiểm tra session và không kiểm tra ý định bằng CSRF protection, hành động có thể được xử lý dưới danh tính của user.
5. Dù CORS không cho script attacker **đọc** response, request đơn giản như HTML form POST có thể đã được gửi và xử lý. Chặn việc đọc response **không hoàn tác thay đổi** đã xảy ra.

Sơ đồ:

```text
Attacker site                     Browser with existing session
      |                                      |
      | -- dụ browser gửi HTML form POST --> |
                                             |
                                             | POST /settings/update
                                             | Cookie: JSESSIONID=...
                                             v
                                       Spring backend
                                             |
                                      Authentication
                                             |
                                      Đã login? Có.
                                             |
                                      CSRF validation
                                      /      \
                            Token đúng?      Token thiếu/sai
                               |                 |
                        request tiếp tục     403 Forbidden
                               |
                         Authorization
                               |
                        có thể xử lý action

CORS: browser có thể chặn attacker đọc response.
CSRF: server phải chặn hành động giả mạo.
```

**Cẩn thận về cookie SameSite:** SameSite=Lax/Strict có thể ngăn cookie được gửi trong một số bối cảnh cross-site và là lớp giảm rủi ro hữu ích. Nhưng *same-site không đồng nghĩa same-origin*: nếu subdomain cùng site bị chiếm quyền hoặc endpoint có side effect ở GET, chỉ dựa vào SameSite có thể không đủ. Đối với session-cookie app, giữ CSRF protection theo threat model và tài liệu OWASP/Spring Security.

**CORS preflight không phải CSRF token.** Một request có custom header thường yêu cầu preflight; điều đó hữu ích khi chính sách CORS rất chặt và server không chấp nhận simple content types. Tuy nhiên cơ chế token mà Spring Security kiểm tra vẫn là bảo vệ riêng. Đừng bỏ `CsrfFilter` chỉ vì preflight test xanh.

## 6. Simple request và preflight: hai luồng khác nhau

### 6.1. Request không cần preflight

Một số request cross-origin đáp ứng điều kiện CORS *safelisted* có thể được browser gửi **thẳng**, không gọi OPTIONS trước. Ví dụ một HTML form dùng `POST` với `application/x-www-form-urlencoded` (cùng các điều kiện HTTP/browser liên quan).

```http
POST /api/settings HTTP/1.1
Host: api.example.com
Origin: https://evil.example.net
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
 
displayName=attacker-choice
```

Cookie chỉ được đính kèm nếu chính sách credential/cookie của browser thực sự cho phép; ví dụ ở trên minh họa một bối cảnh đã có ambient credential phù hợp. **CORS có thể chặn JS đọc response nhưng không bảo đảm request chưa tới server.** Nếu endpoint cho phép thay đổi trạng thái mà không xác minh CSRF/Origin, đây là lỗ hổng.

### 6.2. Request có preflight

Browser thường preflight khi request dùng phương thức/custom headers/non-safelisted content type, ví dụ JSON POST với `X-CSRF-TOKEN`.

```http
OPTIONS /api/settings HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Response khi origin, method và header hợp lệ:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Vary: Origin
```

Tổ hợp header/order/casing có thể thay đổi theo framework và browser; đây là **ví dụ cấu trúc**, không phải cam kết byte-for-byte. Preflight **không gửi cookie phiên**, và 200 ở đây chỉ xác nhận *chính sách cross-origin* cho request sẽ được gửi, **không chứng minh user đã đăng nhập**.

Sau đó browser mới gửi request chính:

```http
POST /api/settings HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: JSESSIONID=...
Content-Type: application/json
X-CSRF-TOKEN: <token-issued-for-session>

{"displayName":"Lan"}
```

Lúc này backend vẫn phải kiểm tra:

- Cookie/session/token xác thực hợp lệ chưa?
- User có quyền sửa settings của tài khoản đó không?
- `X-CSRF-TOKEN` có khớp token gắn với session/chiến lược CSRF của server không?
- JSON được validate và action có vi phạm business policy không?

**Nhớ:** browser có thể cache kết quả preflight theo `Access-Control-Max-Age`, nhưng mỗi request thực vẫn cần authentication, authorization và CSRF phù hợp. Preflight success không phải access token.

### 6.3. Tại sao CORS phải chạy trước Spring Security?

Tài liệu chính thức của Spring Security giải thích rằng preflight không chứa `JSESSIONID`. Nếu authentication/authorization xử lý preflight như request protected thông thường trước CORS, nó có thể bị trả 401/302/403 sai, làm browser báo lỗi CORS.

Cấu hình `http.cors(Customizer.withDefaults())` kết hợp một `UrlBasedCorsConfigurationSource` giúp Spring Security tích hợp CORS processing đúng thứ tự. Nó **không** có nghĩa bỏ bảo vệ đối với request thực.

## 7. Mô hình ba điều kiện độc lập cho một API

Giả sử `POST /api/settings` thay đổi cài đặt của người dùng. Chính sách đúng có thể biểu diễn:

```text
Browser cross-origin read permission:
    Origin thuộc allowlist?
       Có -> browser được đọc response theo CORS nếu mọi điều kiện đúng
       Không -> browser không được đọc; có thể không gửi request chính
       
Server request validity:
    Authentication hợp lệ?
       Không -> 401/redirect login
       Có -> tiếp tục
    CSRF proof hợp lệ cho unsafe method và session?
       Không -> 403
       Có -> tiếp tục
    User có role/ownership để sửa dữ liệu?
       Không -> 403
       Có -> xử lý action và trả response
```

Các bước không bắt buộc xuất hiện theo thứ tự văn bản trong mọi filter chain, vì Spring Security có filter ordering/exception handling, nhưng **điều kiện bảo mật không thay thế nhau**.

Bảng so sánh theo tình huống:

| Origin trong allowlist | Session valid | CSRF token valid | Quyền nghiệp vụ | Điều được kết luận |
| --- | --- | --- | --- | --- |
| Có | Không | Không | Không xét | Browser được phép CORS về mặt origin; **không được thao tác** |
| Có | Có | Không | Có | Request thay đổi trạng thái bị **CSRF chặn** |
| Có | Có | Có | Không | Auth/CSRF hợp lệ; **authorization chặn** |
| Có | Có | Có | Có | Request có thể được xử lý |
| Không | Có | Không | Có | Browser không được đọc response; server còn phải **tự ngăn CSRF** |
| Không | Có | Có | Có | Với request được browser gửi, CORS sẽ hạn chế đọc response; quyết định server-side vẫn phụ thuộc policies khác |

**Không dùng bảng này để suy luận một HTTP status cố định:** Spring Security form login có thể redirect 302, bearer API thường trả 401, CORS preflight bị từ chối thường nhận 403 và browser báo network/CORS error. Các mã HTTP tùy cơ chế, filter ordering và handler; phải kiểm tra bằng request thực.

## 8. Ví dụ Spring Boot 3.5 / Java 17: giữ CORS, authentication, CSRF riêng biệt

Ví dụ dưới là một ứng dụng Spring Boot **3.5.16, Java 17+, Servlet MVC** có:

- Frontend tin cậy dự kiến ở `https://app.example.com`; backend ở `https://api.example.com`.
- CORS chỉ allow **đúng** frontend, cho phép gửi session cookie khi browser cấu hình `credentials: "include"`.
- Đăng nhập bằng Spring Security **formLogin + HTTP session**. Dữ liệu mẫu chỉ dùng local development.
- CSRF **bật mặc định** cho POST/PUT/PATCH/DELETE; dùng `GET /csrf` để frontend lấy token.
- `GET /api/me` cần authenticated.
- `POST /api/settings` cần `ROLE_USER`, đồng thời vẫn phải qua CSRF filter.
- Controller minh họa xác thực/phân quyền nhưng **không ghi database**; response xác nhận payload đã được chấp nhận.

Đây là ví dụ học tập: phải thay origin, tài khoản, password, session store, TLS, account policy và cả CSRF/login UX khi triển khai thực tế.

### 8.1. Cấu trúc

```text
cors-csrf-security-demo/
├── pom.xml
├── src/main/java/demo/security/CorsCsrfApplication.java
└── src/test/java/demo/security/CorsCsrfApplicationTests.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>cors-csrf-security-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

`spring-boot-starter-security` cung cấp Spring Security config/web và password encoder implementations. `spring-security-test` dùng cho MockMvc. Không cần dependency “CORS security” riêng: Spring Web MVC và Spring Security đã hỗ trợ các lớp phù hợp.

### 8.3. `CorsCsrfApplication.java`

```java
package demo.security;

import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsCsrfApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwords) {
        UserDetails learner = User.withUsername("learner")
            .password(passwords.encode("local-learning-only"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Không dùng "*" hoặc phản chiếu Origin của mọi người gọi.
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));

        // Cho phép request credentialed từ origin đã allow.
        // Đây KHÔNG phải cấp phép login hoặc miễn kiểm tra CSRF.
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Integrate CorsFilter before Spring authentication logic.
            .cors(Customizer.withDefaults())

            // Giữ CSRF bảo vệ unsafe methods dùng session cookie.
            .csrf(Customizer.withDefaults())

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/public", "/csrf").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/me").authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/api/settings").hasRole("USER")
                .anyRequest().denyAll())

            // Form login dùng session; URL login được permitAll.
            .formLogin(form -> form
                .defaultSuccessUrl("/public", true)
                .permitAll())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/")
    Map<String, String> index() {
        return Map.of(
            "csrfEndpoint", "/csrf",
            "loginPage", "/login",
            "protectedEndpoint", "/api/me");
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/api/me")
    Map<String, String> whoAmI(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @PostMapping("/api/settings")
    Map<String, String> requestSettingsChange(
            @RequestBody DisplayNameRequest input,
            Principal principal) {
        // Không ghi DB; chỉ mô tả request đã qua SecurityFilterChain.
        return Map.of(
            "status", "accepted",
            "user", principal.getName(),
            "requestedDisplayName", input.displayName());
    }

    record DisplayNameRequest(String displayName) {}
}
```

**Từng phần đang bảo vệ gì?**

- `corsConfigurationSource()` dùng allowlist **exact origin**, đúng scheme/host/port. `setAllowCredentials(true)` cho phép credentialed CORS từ origin này nếu browser và cookie policy cũng cho phép.
- `http.cors(...)` làm CORS processing diễn ra trước authentication của Spring, phù hợp preflight không có session cookie.
- `csrf(...)` vẫn bật. Spring Security mặc định kiểm tra unsafe HTTP methods, ví dụ POST, với CSRF token hợp lệ; CORS không thay thế bước này.
- `authorizeHttpRequests(...)` yêu cầu danh tính ở `/api/me` và thêm `ROLE_USER` ở `POST /api/settings`. Đổi origin không thể cấp quyền user.
- `formLogin(...)` cung cấp login page/processing filter và session-based authentication. `permitAll()` áp dụng các endpoint login do Spring quản lý, không phải `permitAll()` cho toàn bộ ứng dụng.
- `CsrfToken` được Spring Security cấp và lưu theo strategy của `CsrfTokenRepository` (mặc định thường gắn session trong cấu hình này). GET `/csrf` làm token sẵn có cho frontend.
- `Map.of(...)` ở controller chỉ là JSON trả về, chưa cập nhật hệ thống thật. Khi thêm DB, phải kiểm tra ownership/validation ở service thay vì chỉ dựa trên `ROLE_USER`.

**Quan trọng:** `https://app.example.com` là origin production minh họa, không phải một frontend được tạo bởi project. Để thử từ frontend dev như `http://localhost:5173`, sửa allowlist thành **chính xác origin dev đó** và chỉ giữ cấu hình này trong môi trường dev. Khi test backend trực tiếp trên `http://localhost:8080`, CORS không áp dụng nếu request cùng origin hoặc không mang `Origin` như browser cross-origin request.

## 9. Trình tự browser với CSRF token và session

Giả sử frontend thực tế chạy ở `https://app.example.com`, backend tại `https://api.example.com` có TLS và routing đúng theo ví dụ. Vì backend dùng **session cookie**, frontend cần `credentials: "include"` cho cross-origin fetch, còn cookie vẫn chịu chính sách SameSite, Secure và cấu hình browser.

### 9.1. Lấy CSRF token trước khi gửi POST

```javascript
const API_BASE = "https://api.example.com";

async function obtainCsrf() {
  const response = await fetch(API_BASE + "/csrf", {
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error("Cannot obtain CSRF token");
  }
  const csrf = await response.json();
  return { name: csrf.headerName, value: csrf.token };
}

// Trên cùng một page đã được server cho phép origin:
const csrfBeforeLogin = await obtainCsrf();
console.log(csrfBeforeLogin.name);  // Thường là "X-CSRF-TOKEN"
// Không in token thật ra logs/console trong production.
```

Endpoint `/csrf` được phép cho anonymous để lấy một token gắn với phiên ban đầu. **Việc lấy được CSRF token không chứng minh user đã login.** Một client chưa authenticated vẫn có thể lấy token nếu sản phẩm cho phép; server phải kiểm tra authentication khi gọi protected resources.

### 9.2. Login và refresh token

Spring Security Form Login processing endpoint mặc định là POST `/login`. Một frontend có thể gửi form encoding + CSRF header qua fetch:

```javascript
async function login(username, password) {
  const csrf = await obtainCsrf();

  const response = await fetch(API_BASE + "/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.name]: csrf.value
    },
    body: new URLSearchParams({ username, password })
  });

  // Form login có thể redirect đến /public hoặc /login?error.
  // Ứng dụng thực nên kiểm tra trạng thái đăng nhập bằng API.
  if (!response.ok) {
    throw new Error("Login request failed or was rejected");
  }

  // MẶC ĐỊNH, Spring làm mới CSRF token sau authentication.
  return obtainCsrf();
}
```

**Không dùng `response.ok` một mình để khẳng định “password đúng”**: browser fetch thường follow redirect, và response cuối có thể là trang login lỗi với HTTP 200. Sau login, hãy gọi `/api/me` và kiểm tra kết quả đã authenticated, hoặc thiết kế JSON login API có hợp đồng rõ ràng.

Sau login hoặc logout, Spring Security có thể xóa CSRF token cũ theo `CsrfAuthenticationStrategy` / `CsrfLogoutHandler`. **Frontend phải lấy token mới**, nếu không request POST sau đó có thể trả 403 dù session mới đã hợp lệ. Không đặt CSRF token trong URL query, localStorage có thời hạn tùy ý hay log.

### 9.3. Gửi request có cả session và CSRF token

```javascript
async function requestDisplayNameChange(newName) {
  const csrf = await obtainCsrf();

  const response = await fetch(API_BASE + "/api/settings", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.name]: csrf.value
    },
    body: JSON.stringify({ displayName: newName })
  });

  if (!response.ok) {
    throw new Error("Settings request rejected: " + response.status);
  }
  return response.json();
}
```

Đối với frontend thật, không nhất thiết cần gọi `GET /csrf` trước *mỗi* POST: có thể quản lý token theo chu kỳ session và refresh sau login/logout hoặc khi hết hiệu lực. Ví dụ gọi lại để trình bày luồng đơn giản, không phải thiết kế tối ưu lưu lượng.

Vì request chứa `Content-Type: application/json` và custom `X-CSRF-TOKEN`, browser sẽ phát preflight ở trường hợp cross-origin phù hợp. Sau preflight thành công, Spring vẫn phải nhận **cookie phiên hợp lệ và CSRF token hợp lệ** để xử lý POST.

**Hai origin cùng site nhưng khác origin** như `app.example.com` và `api.example.com` có thể phối hợp với session cookie theo chính sách browser. Nếu frontend nằm ở site hoàn toàn khác, cần cân nhắc third-party cookie blocking và `SameSite=None; Secure`; nên ưu tiên same-site reverse proxy/BFF khi phù hợp. Không “chữa” lỗi cookie bằng cách mở `Access-Control-Allow-Origin: *`.

## 10. Kiểm thử Spring Security bằng MockMvc

Trong Spring Boot 3.5, `spring-boot-starter-test` và `spring-security-test` cung cấp `MockMvc` và helpers `user(...)`/`csrf()`. Các test dưới đây **không cần frontend thật** và trực tiếp kiểm tra các lớp bảo vệ.

Tạo file `src/test/java/demo/security/CorsCsrfApplicationTests.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedOriginPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/settings")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"));
    }

    @Test
    void disallowedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/settings")
                .header(HttpHeaders.ORIGIN, "https://evil.example.net")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginDoesNotAuthenticateAnonymousUser()
            throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedUserMayReadSafeEndpointWithoutCsrf()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("learner").roles("USER"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }

    @Test
    void authenticatedUserCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/settings")
                .with(user("learner").roles("USER"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserWithCsrfMayPost() throws Exception {
        mvc.perform(post("/api/settings")
                .with(user("learner").roles("USER"))
                .with(csrf().asHeader())
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.user").value("learner"))
            .andExpect(jsonPath("$.requestedDisplayName").value("Lan"));
    }

    @Test
    void csrfEndpointReturnsTokenToClient() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token").isString())
            .andExpect(jsonPath("$.headerName").isString());
    }
}
```

Chạy:

```bash
mvn test
```

Nếu môi trường có Java 17+ và tải được dependencies, **dự kiến 7 test pass**. Mã kiểm tra tĩnh, không giả vờ đã chạy Maven trong Google Sheet. Những test này chứng minh:

- OPTIONS preflight từ origin cho phép nhận CORS permission **không cần session**.
- OPTIONS từ origin lạ bị CORS chặn.
- `Origin` hợp lệ **không vượt qua authentication**.
- GET với user mock được phép mà không cần CSRF token vì GET được coi là safe method.
- POST có user mock nhưng thiếu CSRF → 403.
- POST có user, quyền và CSRF → controller trả JSON.
- Backend cung cấp CSRF token qua endpoint được bảo vệ bởi thiết kế session.

**Quan trọng về mức độ test:** `with(user(...))` tạo authentication giả lập cho request, không kiểm chứng mật khẩu thật; `with(csrf())` tạo token phù hợp test, không chứng minh browser đã bảo vệ cookie trong production. Cần integration test thực qua reverse proxy, browser cookie policy và TLS.

## 11. Kiểm tra nhanh bằng curl và DevTools

Khởi động project:

```bash
mvn spring-boot:run
```

### 11.1. Xem phản hồi CORS preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/settings \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
```

Kỳ vọng: mã thành công (thường 200), có `Access-Control-Allow-Origin: https://app.example.com`. Preflight **không cần login**.

Thay `Origin` bằng `https://evil.example.net`:

```bash
curl -i -X OPTIONS http://localhost:8080/api/settings \
  -H 'Origin: https://evil.example.net' \
  -H 'Access-Control-Request-Method: POST'
```

Kỳ vọng: bị từ chối bởi CORS processor, thường HTTP 403. Những thử nghiệm curl này chỉ xác nhận **server trả headers nào**; curl không áp dụng browser CORS policy, nên không chứng minh hành vi của tất cả trình duyệt.

### 11.2. Origin được allow nhưng request chưa login

```bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: https://app.example.com'
```

Kỳ vọng với cấu hình `formLogin`: response **302 redirect đến login**, không phải tự động 200. CORS không hề tạo session.

### 11.3. POST cần CSRF ngay cả khi có session

Đối với session cookie, quá trình thực tế phải:

1. `GET /csrf`, giữ cookie jar và token.
2. `POST /login` gửi username/password cùng CSRF header và cookie đã nhận.
3. Lấy lại CSRF token sau login.
4. `POST /api/settings` gửi cookie và CSRF header.
5. Bỏ CSRF header ở một POST tương tự: kỳ vọng 403.

Nếu dùng `curl` shell, có thể giữ cookies với `-c cookies.txt -b cookies.txt` và trích JSON qua công cụ phù hợp. **Không hard-code token mẫu**: token thực được server sinh, phải lấy từ response chính xác của cùng cookie session. Không đưa file cookie/token ra kho Git.

Browser DevTools giúp quan sát:

- `Network → OPTIONS`: `Origin`, `Access-Control-Request-Method`, các response headers.
- Request POST thực: có `Cookie` hay không, có `X-CSRF-TOKEN` không, status thật là 401/302/403/200?
- Cookies: Domain, Path, SameSite, Secure và expiry.
- Console: CORS error có nghĩa JavaScript bị chặn đọc response; **không tự suy ra backend đã không nhận request**.
- Redirect chain: request tới HTML login có thể làm frontend tưởng lỗi CORS vì response cuối thiếu header hoặc không cùng origin như dự kiến.

## 12. Cấu hình CORS an toàn: những điều nên và không nên

### 12.1. Không dùng wildcard cùng credentials

Cấu hình dưới sai về mặt browser CORS contract khi gửi credentials:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browser sẽ từ chối chia sẻ response với credentialed request trong trường hợp này. Đừng chữa bằng cách tắt bảo mật của browser hay dùng `mode: "no-cors"`: mode đó cho response *opaque* không đọc được, cũng không làm API an toàn hơn.

Thay vào đó, với frontend tin cậy:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Nếu có nhiều origin được allow, server nên chọn trả origin **đã đối chiếu allowlist** và đặt `Vary: Origin` khi response thay đổi theo Origin để tránh cache nhầm.

### 12.2. Không tự phản chiếu mọi Origin

Phản ví dụ:

```java
// SAI: chấp thuận mọi Origin, không kiểm tra allowlist.
response.setHeader("Access-Control-Allow-Origin",
    request.getHeader("Origin"));
response.setHeader("Access-Control-Allow-Credentials", "true");
```

Khi site attacker truy cập với credentials, server có thể cho phép site đó **đọc dữ liệu người dùng**. Điều này không chỉ thiếu authentication mà còn tạo nguy cơ exfiltration khi user đã authenticated.

Hãy cho phép **chỉ origin bạn thật sự sở hữu và vận hành**, kiểm tra subdomain takeover, preview deployment/third-party widget và chính sách XSS. Một origin đã nằm trong allowlist thường được giao quyền rất lớn để đọc dữ liệu qua fetch, nhất là khi `allowCredentials=true`.

### 12.3. Không mở quá rộng methods, headers, paths

- Chỉ allow những methods frontend cần: GET, POST, PATCH…; không allow không giới hạn vì tiện.
- `setAllowedHeaders(...)` nên nêu các request headers cần thiết; khi allow custom headers, nhớ rằng attacker kiểm soát được JS trên bất kỳ origin đã được allow.
- Giới hạn CORS mapping đúng endpoint cần cross-origin, ví dụ `/api/**`, `/csrf`, `/login`. Nếu frontend cùng origin, có thể không cần mở CORS.
- Không vô tình cho allowlist staging/dev origin rộng sang production.
- Kiểm tra CORS ở reverse proxy/gateway **và** Spring: hai tầng chồng header mâu thuẫn có thể làm browser fail hoặc mở quá rộng.

Trong ví dụ, `/**` được dùng vì form login và CSRF endpoint cũng phục vụ frontend khác origin. Sản phẩm thực nên giảm phạm vi dựa trên những route tồn tại.

## 13. CSRF với các kiểu authentication khác nhau

Câu hỏi thực tế: **API đang dựa vào credential mà browser tự gửi hay phải chủ động đưa credential vào mỗi request?**

| Mô hình | CSRF cần xem xét thế nào? |
| --- | --- |
| **Form login + JSESSIONID cookie** | Có nguy cơ CSRF với unsafe methods; giữ token/server-side CSRF protection |
| **OIDC login rồi dùng session cookie** | Vẫn cần CSRF cho các mutation của app; OIDC login state/nonce không tự thay CSRF token của mọi POST |
| **JWT/access token lưu trong cookie tự gửi** | Vẫn có nguy cơ CSRF như session cookie, dù token có chữ ký |
| **HTTP Basic browser tự gửi credentials** | Cần đánh giá CSRF vì browser có thể tự gắn credentials theo auth cache/chính sách |
| **Bearer JWT do JS gắn qua `Authorization: Bearer ...`, không dùng cookie/session** | Classic browser CSRF thường thấp hơn vì attacker không tự gắn được header bearer của nạn nhân; vẫn cần XSS/token theft protection và kiểm tra kiến trúc |
| **API key do server-to-server client tự gửi header** | CORS chủ yếu không liên quan client ngoài browser; CSRF thường không áp dụng theo cùng cơ chế nếu browser không tự gửi credential |
| **mTLS hoặc client cert được browser dùng tự động** | Cần phân tích browser/credential auto-attachment và loại thao tác; không áp đặt “mTLS nên không CSRF” |

**Không quyết định `csrf.disable()` chỉ từ việc đường dẫn bắt đầu bằng `/api/`.** Một API có chữ “REST” nhưng dùng session cookie thì CSRF vẫn đáng quan tâm. Ngược lại, một OAuth2 Resource Server thực sự stateless với access token chỉ được client chủ động gắn Authorization header có thể cấu hình bỏ CSRF cho **chain tương ứng**, nhưng điều kiện phải được xác minh chứ không suy đoán.

### 13.1. Nhiều SecurityFilterChain và ranh giới

Trong ứng dụng hỗn hợp, có thể tách:

```text
/api/bearer/**:
    SecurityFilterChain stateless
    OAuth2 Resource Server / bearer authentication
    CSRF policy dựa trên việc không có ambient credentials
/web/**:
    SecurityFilterChain stateful
    formLogin hoặc OAuth2 Login + JSESSIONID
    CSRF protection cho unsafe methods
```

Mỗi chain cần CORS configuration phù hợp nếu được gọi cross-origin; chú ý `@Order` và `securityMatcher(...)`: request khớp **chain đầu tiên phù hợp**, không qua mọi chain. Cấm thiết kế `permitAll` hoặc no-CSRF matcher bao phủ nhầm đường stateful.

Ví dụ trích đoạn **không phải class chạy độc lập**:

```java
// Chỉ minh họa phạm vi sau khi đã thiết kế auth mechanism:
http.securityMatcher("/api/bearer/**")
    .sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

Chỉ dùng khi chain này **không dựa vào session cookie hoặc credential tự đính kèm** và đã xác minh JWT issuer/audience/signature theo cấu hình thực tế. Không đem `csrf.disable()` từ đây sang form login chain.

## 14. SameSite, custom headers và các lớp phòng thủ phụ

### 14.1. SameSite không tương đương Origin

Cookie có thể có:

```http
Set-Cookie: JSESSIONID=opaque-value; Secure; HttpOnly; SameSite=Lax; Path=/
```

- `HttpOnly` giảm truy cập cookie qua JavaScript thông thường, nhưng không ngăn browser tự gửi cookie.
- `Secure` yêu cầu HTTPS (ngoại lệ hành vi loopback/browser có thể khác); không thay authentication.
- `SameSite=Lax/Strict` hạn chế cookie ở một số request cross-site, nhưng trang attacker cùng site/subdomain có thể là cùng-site dù khác origin.
- `SameSite=None; Secure` hỗ trợ một số kịch bản cross-site cookie, song tăng bề mặt CSRF và còn phụ thuộc chính sách chặn third-party cookie.
- Cookie domain quá rộng (ví dụ cấp cookie cho mọi subdomain) có thể gia tăng rủi ro khi subdomain không được kiểm soát. Nên ưu tiên host-only cookie hoặc các tiền tố như `__Host-` trong thiết kế phù hợp.

### 14.2. Custom header không thần kỳ

Một chiến lược chống CSRF cho Ajax API là yêu cầu một custom header mà attacker cross-origin không thể gắn qua browser nếu preflight không được allow. OWASP mô tả chiến lược này khi **chỉ allow origin tin cậy**, không chấp nhận simple request bodies theo cách bypass và không có client khác không tuân thủ browser restriction.

Nhưng **custom header tên bất kỳ mà server chỉ kiểm tra sự hiện diện** không mạnh bằng session-bound CSRF token trong mọi threat model: nếu trusted origin bị XSS hoặc CORS allowlist quá rộng, attacker có thể gửi đúng header. Trong ví dụ, Spring Security **so token đã phát**, không chỉ xem có header `X-CSRF-TOKEN` là đủ.

### 14.3. Defense in depth

Ngoài CSRF token, cân nhắc:

- **Origin/Referer verification** cho unsafe methods khi policy phù hợp; `Origin` thiếu hoặc `null` không được mặc nhiên xem là trusted.
- **Fetch Metadata** (ví dụ `Sec-Fetch-Site`) để chặn cross-site requests không mong muốn; kiểm tra browser support và request ngoại lệ.
- **Content Security Policy** và phòng XSS: nếu origin frontend đã bị attacker chạy JS, token có thể bị đánh cắp hoặc hành động có thể được kích hoạt trong trusted origin.
- **Strict HTTPS/HSTS**, session fixation protection, timeout và logout.
- **Idempotency and business constraints** cho các mutation quan trọng; không dùng GET để thay đổi dữ liệu.
- **Rate limiting** và logging/audit có lọc dữ liệu nhạy cảm.

CSRF token không ngăn một user tự chủ ý thực hiện hành động trái phép: authorization và business validation vẫn bắt buộc. CORS không thay thế bất kỳ phần nào trong chuỗi này.

## 15. Những lỗi Spring Security thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| Browser báo CORS dù API đã có `@CrossOrigin` | Security chain xử lý preflight trước MVC; CORS source không tích hợp hoặc gateway thiếu headers | Bật `http.cors(...)` và cấu hình source; xem OPTIONS/response tại ingress |
| OPTIONS trả 302 đến `/login` | Preflight không mang cookie và bị auth filter chặn trước CORS | Cho CORS xử lý preflight đúng thứ tự, không tắt auth của request thật |
| Preflight 200 nhưng GET/POST trả 401 hoặc login redirect | CORS cho origin, nhưng request không có credential hợp lệ | Kiểm tra `Cookie`/Bearer, session, SameSite và login |
| GET có session trả 200, POST cùng session trả 403 | CSRF token thiếu, sai, hết hạn hoặc đã bị rotate sau login/logout | Lấy token mới, gửi qua header/parameter đúng; kiểm tra `CsrfTokenRepository` |
| POST 403 dù có `X-CSRF-TOKEN` | Header chỉ có tên nhưng token không đúng session; repo dùng token khác | Kiểm tra token đã phát cho đúng phiên và cookie |
| `Access-Control-Allow-Origin: *` cùng credentials không hoạt động | Browser cấm wildcard với credentialed CORS | Allowlist origin cụ thể; đừng dùng phản chiếu Origin |
| Postman/curl gọi API được còn browser bị CORS | Các client ngoài browser không áp dụng CORS read restrictions | Kiểm tra browser Origin/preflight; đừng coi Postman pass là chứng minh CORS |
| App trả dữ liệu nhạy cảm cho origin attacker | CORS phản chiếu Origin hoặc allowlist chứa site đã bị chiếm | Khóa allowlist, đánh giá subdomain takeover, kiểm tra session/authorization |
| Cookie không gửi từ frontend | `fetch` thiếu `credentials: include`, SameSite/Secure/domain/path sai hoặc third-party cookie policy | Xem Cookie/Set-Cookie trong DevTools và site relationship |
| Session đúng nhưng sau login POST đầu bị 403 | CSRF token cũ bị xóa/rotate khi authentication success | Gọi lại `GET /csrf` sau login |
| CSRF bị tắt để “sửa CORS” | Nhầm trách nhiệm bảo vệ, có thể mở lỗ hổng giả mạo request | Bật lại CSRF, phân tích preflight, cookie và token riêng |
| Mọi request từ frontend tin cậy thành admin | Code coi `Origin` là username/authority | Chỉ xác thực bằng credential, role từ server-side policy |
| Một API có hai CORS headers mâu thuẫn | Proxy, MVC và Security cùng cấu hình chồng | Chọn ownership rõ và thử qua đường ingress thật |
| Frontend dùng `mode: no-cors`, không đọc được JSON | Response opaque theo browser Fetch, không sửa server CORS | Bỏ `no-cors`, cấu hình CORS cho origin/method/header hợp lệ |
| CORS cho origin chính xác nhưng vẫn bị chặn | Scheme/port khác; request có header/method chưa được allow | So sánh origin đầy đủ và Access-Control-Request-* |
| GET làm thay đổi dữ liệu mà không đòi CSRF | GET thường không được CSRF filter bảo vệ như unsafe methods | Chuyển mutation sang POST/PUT/PATCH/DELETE và giữ CSRF |

### 15.1. Đọc status đúng ngữ cảnh

Một response `403` có thể đến từ nhiều nơi: CORS processor, CSRF validation, `AuthorizationFilter`/AccessDeniedHandler, business policy. Không kết luận “thiếu quyền” chỉ từ status.

Trình tự debug:

1. Trong DevTools, có OPTIONS preflight không? Nó có bị từ chối trước request chính không?
2. Response có header `Access-Control-Allow-Origin` phù hợp và `Access-Control-Allow-Credentials` khi cần không?
3. Request thực có mang session cookie/access token không?
4. Spring Security đã tạo đúng `Authentication` và authorities chưa?
5. Request unsafe method có CSRF token khớp session chưa?
6. Controller/service có kiểm tra role và ownership không?
7. Proxy/cookie domain/SameSite và redirects có làm thay đổi hành vi giữa local/staging/production không?

Có thể tăng logging Spring Security trong môi trường dev riêng để biết filter nào từ chối. **Không bật log request headers/cookies/tokens đầy đủ trong production**.

## 16. Các câu hỏi tự kiểm tra

1. **CORS allow `https://app.example.com` có chứng minh ai gọi API?** Không. Origin là ranh giới browser read access, không phải principal.
2. **Vì sao có thể có CORS preflight 200 nhưng request sau bị 401?** Vì OPTIONS chỉ kiểm tra method/origin/header, còn request thật phải xác thực.
3. **Nếu attacker không đọc được response do CORS, có chắc server không thực hiện action?** Không. Simple requests có thể đã được gửi; CSRF bảo vệ thao tác.
4. **CORS preflight có mang `JSESSIONID` không?** Không; vì vậy CORS phải được xử lý trước khi áp dụng authentication vào request thực.
5. **GET và POST có yêu cầu CSRF giống nhau không?** Theo mặc định Spring Security bảo vệ unsafe methods như POST; GET phải không có side effect và vẫn cần authentication/authorization nếu protected.
6. **Vì sao cần refresh CSRF token sau login/logout?** Spring Security có thể clear/rotate token theo authentication/logout strategy.
7. **`Access-Control-Allow-Origin: *` và `Allow-Credentials: true` có cho phép browser gửi cookie và đọc response không?** Không; credentialed CORS không chấp nhận wildcard.
8. **SameSite cookie có ngăn request khác origin nhưng cùng site không?** Không bảo đảm; same-site rộng hơn same-origin.
9. **Nếu token JWT lưu trong cookie tự gửi, có cần nghĩ đến CSRF không?** Có; JWT không thay đổi bản chất ambient credential.
10. **Nếu API key do server-to-server client tự gửi header, CORS có quản lý client đó không?** Hầu như không; CORS là browser policy, server vẫn phải xác thực API key.
11. **Nếu user đã authenticated nhưng không có `ROLE_ADMIN`, bật CORS có cho phép admin action không?** Không; authorization phải từ chối.
12. **Có nên tắt CSRF toàn bộ chỉ vì frontend SPA dùng fetch?** Không; phải xem SPA có dựa vào cookie/session hay không và bảo vệ từng chain.
13. **Khi nào custom header có giá trị chống CSRF?** Khi browser preflight và CORS allowlist thực sự chặt, server không cho bypass bằng simple requests; nên kết hợp kiểm tra token theo threat model.
14. **Trường hợp test dùng `with(user(...))` có chứng minh password login end-to-end không?** Không. Nó giả lập Authentication để tập trung kiểm tra authorization/CSRF.
15. **Nếu frontend tin cậy bị XSS, liệu CORS chống được?** Không. Script nằm trên trusted origin có thể gửi được request được allow; cần chống XSS và kiểm soát token/session.
16. **Để biết POST bị CORS hay CSRF chặn, xem gì?** Cả preflight, request thực, response, cookie, CSRF header và Spring Security filter logs trong môi trường an toàn.

## 17. Checklist trước khi đưa ra production

- [ ] Origin allowlist chính xác, không phản chiếu tùy tiện hoặc cho cả wildcard với credentials.
- [ ] CORS được xử lý **trước authentication** cho preflight; OPTIONS không phải một đường bỏ qua security của request chính.
- [ ] API nhạy cảm luôn yêu cầu authentication và authorization phía server.
- [ ] Cookie/session-based unsafe requests được bảo vệ bởi CSRF token hoặc cơ chế tương đương được thiết kế, kiểm chứng và audit.
- [ ] CORS allow chỉ cho những HTTP methods/request headers/routes thực sự cần.
- [ ] CSRF token được làm mới đúng thời điểm login/logout; frontend lưu và gửi qua kênh phù hợp.
- [ ] Cookie HttpOnly, Secure, SameSite, Domain, Path và trust proxy được cấu hình theo kiến trúc thực tế.
- [ ] Không có GET endpoint làm thay đổi state.
- [ ] Test được cùng-origin, cross-origin allow, cross-origin deny, missing auth, missing CSRF, invalid CSRF, wrong role và valid request.
- [ ] Cân nhắc CSRF cho JWT-in-cookie, Basic Auth, mTLS/browser credentials; không chỉ dựa tên “REST API”.
- [ ] Logging/APM không ghi token CSRF, session cookies, password hoặc raw bearer tokens.
- [ ] XSS/CSP, Origin/Referer/Fetch Metadata checks, rate limits và session expiration được đánh giá.
- [ ] Integration test chạy qua reverse proxy/gateway thật; tránh CORS headers bị hai tầng chỉnh trái nhau.
- [ ] Tài liệu hóa rõ security owner của từng `SecurityFilterChain`, origin, authentication mode, CSRF mode và endpoint.

## 18. Tài liệu chính thức

- Spring Security – CORS (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Testing, MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework – CORS support: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- MDN – Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – CSRF attack and defenses: https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF
- MDN – Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP – Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Cross-Site Scripting Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
