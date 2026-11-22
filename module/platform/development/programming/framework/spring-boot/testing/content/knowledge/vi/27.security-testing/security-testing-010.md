# Kiểm thử CORS, security header và xử lý lỗi bảo mật trong Spring Boot

## Mục tiêu và phạm vi

Một REST API dùng Spring Boot và Spring Security có thể trả `200 OK` đúng nội dung nhưng vẫn có lỗi bảo mật: trình duyệt không gửi được request vì **CORS preflight bị chặn**, endpoint vô tình phản hồi cho origin không được phép, trang bị nhúng trong iframe, thiếu security headers, phản hồi lỗi tiết lộ nội bộ hoặc `401`/`403` bị trộn lẫn.

Bài thuộc nhánh **Bảo mật** của module **Spring Boot – testing**, tập trung vào chủ đề **Kiểm thử CORS, security header và xử lý lỗi bảo mật**. Trọng tâm là viết các **security integration tests có assertions cụ thể** để bắt được sai lệch giữa cấu hình `SecurityFilterChain`, MVC controller và HTTP response thực tế.

Học xong, bạn có thể:

1. Phân biệt **CORS**, **authentication**, **authorization** và **CSRF**, không coi chúng là một cơ chế.
2. Giải thích **CORS preflight OPTIONS** cần được xử lý trước xác thực và vì sao request này thường không có session cookie hay Authorization header.
3. Tạo `CorsConfigurationSource` giới hạn **origin/method/request headers** và kiểm `Access-Control-Allow-Origin`, `Allow-Credentials`, `Allow-Methods`, `Allow-Headers`, `Expose-Headers`, `Max-Age`.
4. Viết ca **allow** và **deny**: origin lạ, method không cho phép, request header không cho phép, cross-origin GET có/không authentication.
5. Kiểm response headers `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control`, `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy` và `Permissions-Policy`.
6. Hiểu headers nào là default của Spring Security 6.3, headers nào phải cấu hình rõ và khi nào HSTS chỉ xuất hiện trên HTTPS.
7. Viết bài test phân biệt **401 chưa xác thực**, **403 đã xác thực nhưng thiếu quyền**, **403 thiếu/sai CSRF**, **400 sai request data**.
8. Phân biệt `AuthenticationEntryPoint`/`AccessDeniedHandler` trong **security filter chain** với `@RestControllerAdvice` xử lý lỗi trong MVC.
9. Giữ response JSON lỗi an toàn, nhất quán, không trả exception stacktrace, credentials hoặc thông tin nội bộ.
10. Test bằng `@SpringBootTest` + `@AutoConfigureMockMvc` + `spring-security-test`, giữ nguyên security filters thay vì tắt chúng cho test xanh.
11. Phân tích giới hạn của MockMvc đối với **TLS, reverse proxy, browser CORS enforcement, HTTP/2 và end-to-end networking**.
12. Chạy project ví dụ **Java 17 + Spring Boot 3.3.5 + Spring Security 6.3.x + Gradle + JUnit Jupiter**, không cần Docker/database.

**Nguyên tắc chính:** **CORS không thay thế authorization**. Một origin được phép không tự có quyền đọc hay ghi dữ liệu; một client không phải trình duyệt vẫn có thể gọi API ngoài chính sách CORS. Security tests phải kiểm riêng từng lớp bảo vệ và cả đường lỗi.

## 1. Kiến trúc bảo mật của một request

Spring MVC/Spring Security được xây từ các servlet filters, interceptor và controller. Một request thường đi qua:

~~~text
Browser hoặc HTTP client
         |
         v
HTTP request: Method / Origin / Authorization /
              Cookies / CSRF / Content-Type
         |
         v
Servlet container / reverse proxy boundary
         |
         v
Spring Security FilterChainProxy
         |
         +-- CORS processing
         |     +-- Preflight hợp lệ: trả OPTIONS response sớm
         |     +-- Origin/method/header bị cấm: từ chối CORS
         |
         +-- Security headers / CSRF / Authentication
         |
         +-- Authorization
         |     +-- Chưa login/credential sai -> 401
         |     +-- Có login nhưng thiếu quyền -> 403
         |
         v
DispatcherServlet -> @RestController
         |
         +-- @Valid / JSON binding -> 400 khi invalid
         |
         +-- @RestControllerAdvice (MVC exceptions)
         |
         v
HTTP response: status + headers + JSON body
~~~

Sơ đồ cho thấy thứ tự **khái niệm**, không phải bản kê tuyệt đối thứ tự của mọi filter/custom chain. Một security exception có thể được xử lý **trước khi request đến controller**, vì vậy `@ControllerAdvice` không phải nơi duy nhất điều phối lỗi bảo mật.

### Bốn trục cần test riêng

| Trục | Câu hỏi cần trả lời | Bằng chứng |
| --- | --- | --- |
| CORS | Browser-origin nào được phép đọc response của API? | OPTIONS/Origin/Access-Control response headers |
| Authentication | Ai đã xác thực? | 401 khi thiếu hoặc sai credentials, 200 khi hợp lệ |
| Authorization | Identity đó được làm hành động gì? | 403 khi sai role, 200/201 khi đúng role |
| CSRF | Request thay đổi trạng thái có token phù hợp không? | POST không token/sai token 403, token hợp lệ mới đi tiếp |

Ví dụ, một `POST /api/orders` có thể bị chặn ngay ở CORS vì origin không hợp lệ, bị chặn ở CSRF vì thiếu token, bị chặn ở authentication vì chưa đăng nhập, hoặc bị chặn ở authorization vì role chỉ được đọc. **Không phải mọi 403 có cùng nguyên nhân.**

## 2. CORS không phải authentication

**Cross-Origin Resource Sharing (CORS)** là cơ chế theo browser security model cho phép server chỉ định những **web origins** được phép đọc response của các cross-origin requests. Origin là bộ **scheme + hostname + port**.

Ví dụ:

- `https://portal.example.test` là một origin.
- `https://portal.example.test:8443` là origin khác vì port khác.
- `http://portal.example.test` khác vì scheme khác.
- `https://evil.example.test` không phải origin được phép chỉ vì cùng suffix `example.test`.
- `Origin: null` có ngữ nghĩa riêng (sandbox/file/opaque origin), không được tự xem là trusted.

### CORS hạn chế điều gì?

Trình duyệt áp dụng CORS khi JavaScript từ một origin cố đọc response của origin khác. CORS không đảm bảo request chưa được gửi trong mọi tình huống (các simple requests có thể được gửi), và **không phải firewall** hay authorization check chống curl/Postman/server-to-server. Một HTTP client không phải browser có thể tự gửi header `Origin` hoặc không gửi; server vẫn phải xác thực và phân quyền.

**Sai:** “Cho phép origin frontend thì endpoint đã an toàn”.

**Đúng:** “Cho phép origin frontend giúp browser truy cập cross-origin theo chính sách; endpoint vẫn phải kiểm token/session/role và input của từng request”.

### Preflight là gì?

Với request không thuộc dạng “simple” theo Fetch/CORS rules, browser thường gửi **OPTIONS preflight** trước request thực. Ví dụ frontend muốn gọi:

~~~http
POST /api/orders HTTP/1.1
Origin: https://portal.example.test
Authorization: Basic ...
Content-Type: application/json
X-Request-Id: req-123

{"item":"book","quantity":2}
~~~

Browser có thể gửi preflight trước:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-request-id
~~~

Nếu server đồng ý, response đại diện có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type,x-request-id
Access-Control-Max-Age: 600
~~~

Đây là **ví dụ response minh họa**, không phải stdout/body cố định của mọi servlet container. Danh sách methods/headers và cách viết dấu cách có thể thay đổi tùy CORS processor. Bài test nên kiểm ý nghĩa quan trọng thay vì phụ thuộc formatting không thuộc contract.

### Vì sao preflight thường không có credentials?

Browser preflight không mang authorization credentials như request chính theo cách thông thường. Nếu security filter đòi login hoặc CSRF trước khi kiểm CORS, preflight có thể bị trả 401/403, làm frontend báo CORS error. Spring Security khuyến cáo **xử lý CORS trước Spring Security authorization** bằng `http.cors(...)` và `CorsConfigurationSource` hoặc tích hợp MVC CORS đúng cách.

### Allowed vs exposed headers

Đây là hai hướng khác nhau:

- `Access-Control-Allow-Headers`: **request headers** browser được phép gửi trong cross-origin request, ví dụ Authorization, Content-Type.
- `Access-Control-Expose-Headers`: **response headers** mà JavaScript được phép đọc ngoài safelisted response headers, ví dụ `X-Request-Id`.

Cho phép request header `Authorization` không tự có nghĩa response header `X-Request-Id` được frontend đọc. Cần test đúng hướng.

## 3. CORS allowlist an toàn

Cấu hình minh họa dùng **exact origin**:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(
        List.of("https://portal.example.test"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(
        List.of("Authorization", "Content-Type",
                "X-Request-Id"));
config.setExposedHeaders(List.of("X-Request-Id"));
config.setAllowCredentials(true);
config.setMaxAge(600L);
~~~

Đây là snippet thuộc class cấu hình đầy đủ ở phần sau. Khi `allowCredentials=true`, **không cấu hình `allowedOrigins("*")`**; Spring Framework không chấp nhận tổ hợp wildcard origins/credentials này. Với một số use cases có pattern origins, `allowedOriginPatterns` là API riêng cần quản lý allowlist thật, không diễn tả bằng patterns quá rộng.

### Không “echo Origin” tùy ý

Ví dụ sai về kiến trúc:

~~~java
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

Nếu không validate origin trước khi phản hồi, bạn đang cho phép origin bất kỳ được đưa vào header. Một số setups còn kết hợp `Access-Control-Allow-Credentials: true`, khiến dữ liệu credentialed có nguy cơ bị đọc bởi site không được phép.

Một allowlist tốt:

1. Chỉ gồm origins được team sở hữu/quản lý.
2. Phân biệt production, staging, local development.
3. Không dùng wildcard cho credentialed APIs.
4. Giới hạn methods và headers đúng nhu cầu.
5. Có tests negative với một origin cụ thể không được phép.
6. Không dựa vào CORS để bảo vệ endpoint khỏi non-browser clients.
7. Khi phản hồi thay đổi theo origin, quan tâm `Vary: Origin` và cache/CDN behavior.
8. Không tự tin rằng “test trình duyệt local được” là policy đúng cho production.

## 4. Security headers: mặc định và tùy chọn

Spring Security có bộ mặc định giúp giảm rủi ro trình duyệt. Tuy nhiên **không phải mọi header phổ biến đều được bật mặc định**.

| Header | Mục tiêu | Lưu ý kiểm thử |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Chống content MIME sniffing | Spring Security default |
| `X-Frame-Options: DENY` | Giảm clickjacking | Spring Security default |
| `Cache-Control: no-cache, no-store, ...` | Giảm cache dữ liệu nhạy cảm | Default cho responses phù hợp; app có thể chủ động override |
| `Pragma: no-cache`, `Expires: 0` | Cache control tương thích cũ | Default nếu không có custom cache policy |
| `Strict-Transport-Security` | Buộc browser dùng HTTPS cho hostname sau khi đã nhận HSTS | **Chỉ thêm trên HTTPS** theo mặc định |
| `X-XSS-Protection: 0` | Tắt bộ lọc XSS cũ dễ gây rủi ro | Không phải biện pháp thay cho CSP/output encoding |
| `Content-Security-Policy` | Giới hạn nguồn script/style/object/frame | **Không tự có** nếu không cấu hình |
| `Referrer-Policy` | Kiểm thông tin referrer gửi ra ngoài | **Cần cấu hình** |
| `Permissions-Policy` | Quyền dùng camera/microphone/location… | **Cần cấu hình** |
| `Access-Control-Allow-Origin` | Browser cross-origin read permission | Là CORS, **không phải** security header mặc định độc lập |

### HSTS: không thể test bằng HTTP thường

Spring Security chỉ thêm HSTS khi request được nhận biết là **secure/HTTPS**. Trong MockMvc:

~~~java
mvc.perform(get("/api/public").secure(true))
    .andExpect(header().exists(
            "Strict-Transport-Security"));
~~~

Còn request thường:

~~~java
mvc.perform(get("/api/public"))
    .andExpect(header().doesNotExist(
            "Strict-Transport-Security"));
~~~

Đây là hai snippets giả định `mvc` đã được inject và `get`/`header` có static imports. Nếu app ở sau ingress/reverse proxy TLS termination, servlet container cần được cấu hình để nhận đúng thông tin forwarded scheme; một MockMvc `secure(true)` **không chứng minh** ingress/proxy production đã thiết lập HTTPS detection đúng.

### CSP là defense-in-depth, không phải input validation

`Content-Security-Policy` giúp browser hạn chế những nguồn nội dung có thể thực thi, nhưng không thay cho output encoding, validation, HTML sanitizer hoặc tránh unsafe DOM sinks. Một API chỉ trả JSON có thể dùng policy chặt; một ứng dụng có HTML, inline scripts hoặc third-party resources phải thiết kế policy phù hợp và thử trên browser thật.

### Những headers không nên dựa vào

- Không dùng `X-XSS-Protection: 1` như một biện pháp XSS chính; nhiều browser hiện đại bỏ cơ chế cũ.
- Không tự động bật HPKP; header này không còn là khuyến nghị hiện đại.
- Đừng thêm `Access-Control-Allow-Origin: *` chỉ để dập lỗi frontend khi endpoint có credentials.
- Không cắt hết security headers trên error responses. API lỗi cũng có thể chứa dữ liệu nhạy cảm.
- Không đặt chính sách CSP “chặt” chỉ trong code test mà production không hề cấu hình.

## 5. Authentication vs authorization vs CSRF vs validation error

| Trạng thái | Tình huống điển hình | Expected |
| --- | --- | --- |
| 200/201 | Đủ authentication, đủ permission và request hợp lệ | Thành công |
| 401 Unauthorized | Chưa đăng nhập hoặc Basic credentials sai | Lỗi authentication, nên có `WWW-Authenticate` với Basic |
| 403 Forbidden | Authenticated nhưng không có role/quyền | Lỗi authorization |
| 403 Forbidden | Thiếu/sai CSRF trên unsafe method khi CSRF enabled | Bị filter CSRF chặn, có thể **trước** authentication/authorization |
| 403 Forbidden | CORS preflight origin/method/header không hợp lệ | CORS filter từ chối; thường **không** có JSON lỗi tùy chỉnh của authentication |
| 400 Bad Request | Input bind/validation sai khi đã qua security filter | Lỗi MVC validation, có thể do `@RestControllerAdvice` xử lý |

**Quan trọng:** Không viết test giả định “mọi 403 đều có JSON `ACCESS_DENIED`”. 403 có thể được tạo bởi **CorsFilter**, **CsrfFilter**, **AccessDeniedHandler** hoặc business error layer, mỗi đường đi qua các handler khác nhau. Cần chỉ rõ request thuộc trường hợp nào và assertions có ý nghĩa.

### Không tiết lộ thông tin qua body lỗi

Với authentication/authorization, body an toàn có thể là:

~~~json
{"code":"AUTH_REQUIRED"}
~~~

hoặc:

~~~json
{"code":"ACCESS_DENIED"}
~~~

Tránh trả:

~~~json
{"error":"SELECT * FROM users WHERE ...; username=admin; password=..."}
~~~

Đây là ví dụ *không được làm*. Không phản hồi stack trace, tên class, SQL query, secrets, auth token, nội dung audit/private claims hoặc chi tiết cho phép enumeration tài khoản.

Trong logs nội bộ, có thể ghi request ID, status, exception type đã sanitize và nguyên nhân phục vụ debug, nhưng không đẩy thông tin này nguyên vẹn ra public JSON body.

## 6. Project runnable: Java 17, Spring Boot 3.3.5, Spring Security

Project dùng **Spring MVC servlet stack**, không dùng WebFlux. Ta sẽ kiểm:

- `/api/public` cho mọi người (trả JSON, response header `X-Request-Id`).
- `GET /api/orders` cho roles `READER` hoặc `EDITOR`.
- `POST /api/orders` chỉ cho role `EDITOR`, thêm **CSRF token** và input validation.
- Paths không được liệt kê → `denyAll()`.
- CORS chỉ cho `https://portal.example.test`, GET/POST và ba request headers được chỉ định.
- JSON body cho lỗi authentication/authorization qua Security handlers; body cho MVC validation qua `@RestControllerAdvice`.
- Các security headers mặc định và CSP/Referrer/Permissions Policy tùy chỉnh.

**Project không cần database, Docker, JWT server, LDAP, email hoặc API đối tác.** In-memory accounts và Basic auth dùng cho bài học kiểm filter behavior; **không phải khuyến nghị dùng `{noop}` passwords trên production**.

### 6.1. Cây thư mục

~~~text
security-web-test-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/securitylab/
    │   ├── SecurityLabApplication.java
    │   ├── ApiSecurityConfig.java
    │   ├── ShopApiController.java
    │   └── ApiValidationAdvice.java
    └── test/java/com/example/securitylab/
        ├── CorsPolicyTest.java
        ├── SecurityHeaderTest.java
        └── SecurityFailureTest.java
~~~

Scripts/JAR của Gradle Wrapper được sinh bằng Gradle phù hợp hoặc lấy từ repository chuẩn; `gradle-wrapper.jar` là file binary, không copy được từ tài liệu Markdown.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'security-web-test-lab'
~~~

### 6.3. `build.gradle` (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter-web` đem Spring MVC, embedded Tomcat, Jackson HTTP message converters và `MockMvc` test infrastructure.
- `spring-boot-starter-security` đem Spring Security servlet filter chain, Basic authentication, CSRF và security headers.
- `spring-boot-starter-validation` cho Jakarta Validation `@NotBlank`, `@Min` cùng Hibernate Validator.
- `spring-boot-starter-test` đem Spring Boot Test, JUnit Jupiter, MockMvc support, Hamcrest và assertions.
- `spring-security-test` đem request post-processors `httpBasic()`, `user()` và `csrf()`.
- `useJUnitPlatform()` bắt buộc Gradle tìm JUnit Jupiter tests.
- Versions Spring Security/JUnit/Validation được Boot BOM quản lý; không ghim Spring Security 7 vào project Boot 3.3.

**Không dùng `@WebMvcTest` trong các class runnable**, vì mục tiêu là xác minh **cấu hình security filter chain thật của ứng dụng**. Có thể dùng MVC slice nếu chủ động import config/filters cần thiết, nhưng full-context MockMvc làm ranh giới bài học rõ hơn.

### 6.4. `SecurityLabApplication.java`

~~~java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` là root component scan; ba lớp còn lại cùng package nên được Spring tìm thấy. Project chạy bằng `./gradlew test`, hoặc `./gradlew bootRun` cho manual HTTP smoke test trên port mặc định.

## 7. `ApiSecurityConfig.java`: CORS, authentication, roles và headers

**`src/main/java/com/example/securitylab/ApiSecurityConfig.java`**

~~~java
package com.example.securitylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiSecurityConfig {

    public static final String ALLOWED_ORIGIN =
            "https://portal.example.test";

    public static final String CSP =
            "default-src 'none'; base-uri 'none'; "
                + "frame-ancestors 'none'";

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(ALLOWED_ORIGIN));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-Id"));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Credentials CHỈ DÀNH CHO DEMO.
        // Không dùng {noop} trong production.
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password("{noop}editor-pass")
                .roles("EDITOR")
                .build());
    }

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, exception) -> {
            response.setHeader(
                "WWW-Authenticate", "Basic realm=\"demo\"");
            writeError(
                response, HttpServletResponse.SC_UNAUTHORIZED,
                "AUTH_REQUIRED");
        };
    }

    @Bean
    AccessDeniedHandler apiAccessDeniedHandler() {
        return (request, response, exception) ->
            writeError(
                response, HttpServletResponse.SC_FORBIDDEN,
                "ACCESS_DENIED");
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint,
            AccessDeniedHandler apiAccessDeniedHandler)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            // Giữ CSRF enabled để test hành vi thực.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                        HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(
                        HttpMethod.GET, "/api/orders")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(
                        HttpMethod.POST, "/api/orders")
                    .hasRole("EDITOR")
                .anyRequest()
                    .denyAll())
            .httpBasic(basic -> basic
                .authenticationEntryPoint(
                    apiAuthenticationEntryPoint))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    apiAuthenticationEntryPoint)
                .accessDeniedHandler(
                    apiAccessDeniedHandler))
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(CSP))
                .referrerPolicy(referrer -> referrer
                    .policy(
                        ReferrerPolicyHeaderWriter
                            .ReferrerPolicy.NO_REFERRER))
                .permissionsPolicy(permissions -> permissions
                    .policy(
                        "camera=(), microphone=(), "
                        + "geolocation=()")));

        return http.build();
    }

    private static void writeError(
            HttpServletResponse response,
            int status,
            String code) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(
                StandardCharsets.UTF_8.name());
        response.setContentType(
                MediaType.APPLICATION_JSON_VALUE);

        // code được gọi bằng các hằng chuỗi đáng tin cậy,
        // không đưa exception message/client input vào JSON.
        response.getWriter().write(
                "{\"code\":\"" + code + "\"}");
    }
}
~~~

### 7.1. `CorsConfigurationSource` được nối với security chain ra sao?

`UrlBasedCorsConfigurationSource` là bean chứa policy cho path `/api/**`. `http.cors(Customizer.withDefaults())` cho Spring Security tích hợp CORS processing vào security chain. Spring Security biết dùng nguồn `UrlBasedCorsConfigurationSource` được khai báo, giúp xử lý preflight **trước** yêu cầu login/CSRF thông thường.

**Điểm cần nhớ:** Không chỉ định `OPTIONS /api/orders` là `permitAll` rồi cho rằng CORS đã đúng. Nếu thiếu CORS processor, server có thể trả OPTIONS 200/403 nhưng **thiếu `Access-Control-Allow-Origin`**, browser vẫn từ chối request chính. Ngược lại, CORS processor đúng vẫn phải từ chối các origin/method/header ngoài allowlist.

### 7.2. Vì sao origin không chứa dấu sao?

Vì demo cho phép `allowCredentials(true)`, policy dùng exact origin. Khi browser gửi cookie/HTTP credentials theo Fetch credentials mode, server phải chấp thuận origin cụ thể; wildcard không tương thích với credentialed response theo browser rules.

**Thực tế production:** allowed origins nên được externalize per environment (configuration properties) với một allowlist được review. Dùng constant trong tutorial để assertions độc lập với CI settings. Đừng sửa production allowlist bằng cách lấy Origin request rồi trả nguyên lại.

### 7.3. `authorizeHttpRequests` phải khớp HTTP method

- GET `/api/public` → `permitAll`, không cần authentication.
- GET `/api/orders` → role `READER` hoặc `EDITOR`.
- POST `/api/orders` → role `EDITOR`, còn cần CSRF hợp lệ.
- Các paths/methods khác → `denyAll`.

`hasRole("EDITOR")` tương ứng authority `ROLE_EDITOR`. Dùng `User.withUsername(...).roles("EDITOR")` để Spring tạo đúng authority prefix; tránh dùng `hasRole("ROLE_EDITOR")` gây double prefix.

### 7.4. Basic authentication và JSON errors

Demo có hai user test. Nếu không có credentials hoặc credentials sai:

- `AuthenticationEntryPoint` trả 401.
- Response thêm `WWW-Authenticate: Basic realm="demo"`.
- Body `{"code":"AUTH_REQUIRED"}`.

Nếu đã xác thực nhưng không có permission:

- `AccessDeniedHandler` trả 403.
- Body `{"code":"ACCESS_DENIED"}`.

Hai callbacks **nằm trong Spring Security filter handling**. Chúng được cấu hình tường minh, bao gồm cho HTTP Basic filter, để tránh khác biệt mặc định khi Basic auth lỗi. Body lỗi không chứa exception message hoặc stack trace.

### 7.5. Vì sao vẫn bật CSRF?

Trong demo, ta cố tình giữ default `CSRF` để có thể test tác động lên unsafe method `POST`. Trong một API thực sự stateless dùng Bearer token chỉ từ Authorization header và không dùng browser cookies/ambient credentials, team có thể quyết định khác sau threat modeling. Không dùng “REST API” như lý do duy nhất để tắt CSRF: nếu app dùng session cookie, Basic auth trong browser hoặc authentication dựa trên cookies, CSRF vẫn có thể là rủi ro.

### 7.6. Security headers và scope

CSP trong ví dụ là `default-src 'none'; base-uri 'none'; frame-ancestors 'none'`. Đó là policy rất chặt phù hợp REST API trả JSON và không chứa tài nguyên HTML frontend. Nếu app còn có giao diện HTML, policy này có thể chặn scripts/styles cần thiết; phải thiết kế CSP theo từng response/site hoặc filter chain đúng, không copy mù.

`Referrer-Policy: no-referrer` và `Permissions-Policy: camera=(), microphone=(), geolocation=()` là **opt-in**; Spring Security 6.3 hỗ trợ DSL tương ứng. Các header defaults như `nosniff`, `X-Frame-Options: DENY` và cache-control vẫn được giữ.

## 8. `ShopApiController.java`: endpoint kiểm thử thật

**`src/main/java/com/example/securitylab/ShopApiController.java`**

~~~java
package com.example.securitylab;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ShopApiController {

    @GetMapping("/public")
    public ResponseEntity<Map<String, String>> publicInfo() {
        return ResponseEntity.ok()
            .header("X-Request-Id", "server-generated-demo")
            .body(Map.of("message", "public-ok"));
    }

    @GetMapping("/orders")
    public List<OrderView> listOrders() {
        return List.of(
            new OrderView("ORD-001", "Java book", 1));
    }

    @PostMapping("/orders")
    public ResponseEntity<OrderView> createOrder(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderView created = new OrderView(
                "ORD-101", request.item(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(created);
    }

    public record CreateOrderRequest(
            @NotBlank String item,
            @Min(1) int quantity) {
    }

    public record OrderView(
            String id, String item, int quantity) {
    }
}
~~~

Đây là API *in-memory deterministic* chỉ nhằm kiểm servlet/security behavior. Nó **không ghi database**, không gửi payment/email, nên có thể chạy tests không cần teardown. ID `ORD-101` là giá trị cố định của fixture demo, không phải cơ chế sinh ID production.

### Vì sao không trả lại `X-Request-Id` từ request?

Demo phát một header `X-Request-Id` **do server tự đặt** để minh họa `Access-Control-Expose-Headers`. Trong production, có thể nhận correlation ID từ upstream nhưng cần kiểm format/length và ngăn header injection trước khi phản hồi. Không echo untrusted user input vào response headers một cách tùy tiện.

### Validation độc lập với security

`@Valid @RequestBody` có `@NotBlank` và `@Min(1)`. Khi người dùng đã đủ role và CSRF hợp lệ nhưng gửi `{"item":"","quantity":0}`, Spring MVC validation fail **400**. Trước khi request đến bước này, Security Filter Chain vẫn có quyền trả 401/403. Bài test phải tách từng điều kiện, không coi mọi invalid POST đều là 400.

## 9. `ApiValidationAdvice.java`: lỗi thuộc MVC khác lỗi Security Filter

**`src/main/java/com/example/securitylab/ApiValidationAdvice.java`**

~~~java
package com.example.securitylab;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            MethodArgumentNotValidException exception) {

        // Không đưa binding values, stack trace hoặc
        // exception.getMessage() ra response công khai.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
~~~

Ở đây `@RestControllerAdvice` chỉ xử lý **lỗi validation do MVC phát sinh**. Còn `AuthenticationEntryPoint` và `AccessDeniedHandler` xử lý lỗi từ security filter chain. Một `@ControllerAdvice` không tự bắt được `AuthenticationException`/`AccessDeniedException` bị filter bắt và xử lý trước `DispatcherServlet`.

Khi production muốn format lỗi thống nhất theo RFC 9457 Problem Details, có thể dùng `ProblemDetail`/`ResponseEntityExceptionHandler` cho MVC và tự viết JSON cùng schema ở security entry point/denied handler. Nhưng **đừng chỉ sửa @RestControllerAdvice rồi cho rằng 401/403 đã đổi format**.

### Chính sách mapping an toàn

| Mã | Body trong demo | Nguồn xử lý |
| --- | --- | --- |
| 401 | `{"code":"AUTH_REQUIRED"}` | AuthenticationEntryPoint |
| 403 vì thiếu role | `{"code":"ACCESS_DENIED"}` | AccessDeniedHandler |
| 403 vì CSRF | Không khẳng định luôn cùng JSON code; kiểm status/CSRF behavior | CsrfFilter/handler tùy cấu hình |
| 403 vì CORS | Body có thể là `Invalid CORS request`, không dùng API auth JSON | CorsFilter |
| 400 vì validation | `{"code":"INVALID_INPUT"}` | @RestControllerAdvice |

Lý do body của CSRF và CORS có thể khác: các filter **có thể chấm dứt request trước** khi đến nơi bạn thiết kế JSON errors. Hãy cố ý customize từng layer nếu hợp đồng sản phẩm thực sự đòi một JSON schema thống nhất, không viết assertions dựa vào một giả định ngầm.

## 10. Test 1: CORS positive, negative và xác thực

**`src/test/java/com/example/securitylab/CorsPolicyTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class CorsPolicyTest {

    private static final String TRUSTED =
            ApiSecurityConfig.ALLOWED_ORIGIN;

    private static final String UNTRUSTED =
            "https://untrusted.example.test";

    @Autowired
    private MockMvc mvc;

    @Test
    void preflightSucceedsWithoutAuthorizationOrCsrf()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    TRUSTED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                    "true"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                    containsString("authorization")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_MAX_AGE,
                    "600"));
    }

    @Test
    void untrustedOriginPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedHttpMethodPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "DELETE"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedRequestHeaderPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Admin-Override"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginCanReadPublicExposedHeader()
            throws Exception {

        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Request-Id"))
            .andExpect(header().string(
                "X-Request-Id", "server-generated-demo"))
            .andExpect(jsonPath("$.message")
                .value("public-ok"));
    }

    @Test
    void trustedOriginDoesNotBypassAuthentication()
            throws Exception {

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(jsonPath("$[0].id")
                .value("ORD-001"));
    }

    @Test
    void untrustedActualOriginRejectedEvenForPublicPath()
            throws Exception {

        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, UNTRUSTED))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void ordinaryRequestWithoutOriginNeedsNoCorsHeader()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

### 10.1. Bài test preflight thực sự bảo vệ gì?

`preflightSucceedsWithoutAuthorizationOrCsrf` **không gửi Authorization, session cookie hoặc CSRF token**, nhưng vẫn nhận response CORS hợp lệ. Đó là điều browser cần để được phép tiếp tục gửi request POST thực. Nếu CORS xử lý sau authentication, method này có thể fail 401; nếu CSRF chặn OPTIONS sai, nó có thể fail 403.

**Không cần khai báo `@RequestMapping(method=OPTIONS)` trong controller.** `CorsFilter` có thể trả preflight response trước khi chạm controller. Bài test dùng OPTIONS trực tiếp để kiểm chính policy.

### 10.2. Ba negative cases có ý nghĩa riêng

- **Origin lạ:** browser từ `https://untrusted.example.test` không được phép theo allowlist.
- **Method DELETE:** Origin trusted nhưng policy chỉ cho GET/POST, vì thế request DELETE không được phép từ browser.
- **Header X-Admin-Override:** Request method được cho phép nhưng header không nằm trong `allowedHeaders`, preflight phải bị từ chối.

Không gộp ba biến vào một test. Nếu cùng một request vừa có origin sai vừa có method sai, test 403 **không cho biết policy nào đã hoạt động đúng**.

### 10.3. Trusted origin vẫn phải đăng nhập

Test `trustedOriginDoesNotBypassAuthentication` minh họa đúng chỗ dễ nhầm: request GET đến endpoint protected từ origin hợp lệ vẫn trả 401 nếu thiếu credentials; khi thêm HTTP Basic hợp lệ mới được 200. Header `Access-Control-Allow-Origin` có thể xuất hiện trên phản hồi 401 để frontend tin cậy **đọc được lỗi đăng nhập**. Đây không phải bảo mật bị thủng; status 401 vẫn có hiệu lực.

### 10.4. Không có Origin thì sao?

Một server-side client hoặc curl có thể không gửi `Origin`. Request `GET /api/public` vẫn trả 200; CORS header có thể không xuất hiện vì **không có cross-origin check đang diễn ra**. Điều này nhắc lại CORS là browser sharing policy, không phải general access-control gate.

## 11. Test 2: default và opt-in security headers

**`src/test/java/com/example/securitylab/SecurityHeaderTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class SecurityHeaderTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void defaultSecurityHeadersExistOnSuccess()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")))
            .andExpect(header().string(
                "X-XSS-Protection", "0"));
    }

    @Test
    void configuredPolicyHeadersAreReturned()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                "Permissions-Policy",
                "camera=(), microphone=(), "
                + "geolocation=()"));
    }

    @Test
    void hstsIsPresentOnlyWhenRequestIsSecure()
            throws Exception {

        mvc.perform(get("/api/public").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")));

        mvc.perform(get("/api/public").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    @Test
    void unauthorizedResponsesKeepSecurityHeaders()
            throws Exception {

        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")));
    }

    @Test
    void authorizationDeniedStillHasSecurityHeaders()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("reader").roles("READER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"Java book\",\"quantity\":2}"))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP));
    }

    @Test
    void validationErrorsStillHaveSecurityHeaders()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP));
    }
}
~~~

### 11.1. Đâu là mặc định, đâu là cấu hình rõ?

Trong Spring Security 6.3:

- `X-Content-Type-Options: nosniff` là default.
- `X-Frame-Options: DENY` là default.
- `Cache-Control` tránh caching là default trong hoàn cảnh thông thường, app có thể override.
- `X-XSS-Protection: 0` thể hiện không dựa vào legacy XSS filter.
- `Strict-Transport-Security` được viết **khi request được nhận biết secure**.
- `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy` xuất hiện trong demo vì **SecurityConfig đã bật chúng**.

Nếu team xóa đoạn `headers(...contentSecurityPolicy...)` khỏi config mà test CSP vẫn xanh, test sai hoặc đang sử dụng context/mock khác. Một phép **mutation test** có ích là tạm xóa policy ở branch local và chứng minh test đỏ, rồi hoàn nguyên.

### 11.2. Security headers trên error paths

Test không chỉ xem 200. Một endpoint protected trả 401 hoặc 403, và controller trả 400, vẫn cần headers bảo vệ thích hợp. Security headers có thể giảm nguy cơ clickjacking, content sniffing hoặc caching **ngay trên error response**. Không chỉ test response thành công rồi cho rằng filters cũng chạy đúng trên mọi exception path.

### 11.3. HSTS trong reverse proxy deployments

`MockHttpServletRequest.secure(true)` mô phỏng request được nhận biết HTTPS. Điều này bảo vệ **logic viết HSTS ở application layer**, nhưng chưa chứng minh ingress/nginx/load balancer truyền đúng `X-Forwarded-Proto` hoặc `Forwarded`. Nếu production dùng TLS termination, cần test trực tiếp qua proxy với HTTPS thật, kiểm không tin các forwarded headers từ nguồn không được phép.

## 12. Test 3: 401, 403, CSRF và input validation

**`src/test/java/com/example/securitylab/SecurityFailureTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class SecurityFailureTest {

    @Autowired
    private MockMvc mvc;

    private static final String VALID_ORDER =
            "{\"item\":\"Java book\",\"quantity\":2}";

    @Test
    void missingAuthenticationReturns401Json()
            throws Exception {

        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo\""))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));
    }

    @Test
    void invalidBasicCredentialsReturn401()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));
    }

    @Test
    void readerCanAccessReadOnlyEndpoint()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id")
                .value("ORD-001"));
    }

    @Test
    void editorCanAccessReadOnlyEndpoint()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("editor", "editor-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].item")
                .value("Java book"));
    }

    @Test
    void readerCannotCreateEvenWithValidCsrf()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("reader").roles("READER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code")
                .value("ACCESS_DENIED"));
    }

    @Test
    void editorWithoutCsrfIsDeniedBeforeController()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfIsDenied()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithCsrfAndValidBodyCanCreate()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id")
                .value("ORD-101"))
            .andExpect(jsonPath("$.quantity")
                .value(2));
    }

    @Test
    void invalidBodyReturns400OnlyAfterSecurityPasses()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void authenticatedUserStillCannotAccessDenyAllPath()
            throws Exception {

        mvc.perform(get("/api/internal")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code")
                .value("ACCESS_DENIED"));
    }

    @Test
    void publicEndpointDoesNotRequireCredentials()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                .value("public-ok"));
    }
}
~~~

### 12.1. Vì sao `user()` và `httpBasic()` được dùng khác nhau?

- `httpBasic("reader","reader-pass")` thêm **Authorization Basic header** thực vào MockMvc request. Bộ test chạy qua Basic authentication filter và `UserDetailsService`, giúp bắt credential/password behavior.
- `user("reader").roles("READER")` là Spring Security test request post-processor để thiết lập identity/authorities cho test. Nó lý tưởng khi mục tiêu là **authorization/CSRF** mà không muốn lặp lại login. Nó **không** chứng minh mật khẩu reader đúng.
- `csrf()` tạo token hợp lệ cho MockMvc request; `csrf().useInvalidToken()` giúp test rejection path.
- `@WithMockUser` cũng hữu ích nhưng áp dụng theo test method/class, cần hiểu mock security context và không nhầm với login thật.

Vì vậy test authentication nên dùng Basic header, còn test authorization có thể dùng `user()`. Hai cách tạo request không thay thế cho nhau ở mọi mục tiêu.

### 12.2. Lỗi 401 và 403

**401** phản ánh chưa xác thực hoặc credentials sai (khi request tới protected endpoint). Khi Basic được dùng, `WWW-Authenticate` là challenge thích hợp. **403** phản ánh identity đã xác thực nhưng thiếu quyền trong test role-specific, hoặc request bị chặn bởi CSRF/CORS.

Một điều tinh tế: Với **POST không CSRF**, filter có thể trả **403 trước khi Spring đánh giá authentication**. Vì thế không nên viết test “anonymous POST luôn phải 401”. Để kiểm authentication chính xác, dùng GET protected hoặc gửi CSRF hợp lệ khi muốn đi qua CSRF filter.

### 12.3. Lỗi validation 400 chỉ khi đi đến MVC

`invalidBodyReturns400OnlyAfterSecurityPasses` gửi user role EDITOR + CSRF token hợp lệ, nên request mới tới controller/validation. Nếu bỏ `csrf()`, expected 400 có thể bị thay bằng **403** vì controller chưa từng xử lý body. Test báo đỏ là đúng: security filter vẫn hoạt động.

### 12.4. Test `denyAll` là defense-in-depth

Ngay cả EDITOR không được phép GET `/api/internal` vì `anyRequest().denyAll()`. Điều này bảo vệ trường hợp developer thêm endpoint mới nhưng quên cập nhật rule allowlist. Trong production, authorization vẫn cần review theo đường dẫn cụ thể, permission model và domain rules; denyAll cuối chain không tự chứng minh mọi service-layer authorization đều đúng.

## 13. Kết quả dự kiến và cách chạy

Project có **25 phương thức `@Test`**:

| Test class | Số test | Mục tiêu |
| --- | ---: | --- |
| `CorsPolicyTest` | 8 | Trusted/untrusted origin, preflight, methods/headers, browser errors |
| `SecurityHeaderTest` | 6 | Defaults, opt-in headers, HTTPS/HSTS, error responses |
| `SecurityFailureTest` | 11 | 401, Basic credentials, roles, CSRF, validation, denyAll |
| **Tổng** | **25** | Spring Security filter chain + MVC assertions |

### Chạy bằng Gradle

JDK 17 và Gradle Wrapper tương thích đã có trong project root:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy một class:

~~~bash
./gradlew test --tests 'com.example.securitylab.CorsPolicyTest'
./gradlew test --tests 'com.example.securitylab.SecurityHeaderTest'
./gradlew test --tests 'com.example.securitylab.SecurityFailureTest'
~~~

Báo cáo JUnit thường nằm tại:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.securitylab.CorsPolicyTest.xml
    ├── TEST-com.example.securitylab.SecurityHeaderTest.xml
    └── TEST-com.example.securitylab.SecurityFailureTest.xml
~~~

**Expected:** Khi source và dependencies tương thích, dự kiến **25 JUnit test methods pass**. Đây là **kết quả kỳ vọng từ thiết kế**, không phải khẳng định đã thực thi Gradle trên môi trường người học. Không có `System.out.println` trong code nên không có stdout nghiệp vụ cố định. Nếu Gradle reuse cache `UP-TO-DATE/FROM-CACHE`, cần buộc chạy lại khi chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu chưa có Wrapper và đã có Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó commit Wrapper scripts/JAR theo policy repo. Không tự đổi Gradle version trên ứng dụng thật chỉ vì ví dụ có một bản đề xuất.

### Vì sao không cần `@ExtendWith(SpringExtension.class)`?

`@SpringBootTest` tích hợp Spring TestContext/JUnit Jupiter thông qua meta-annotations. `@AutoConfigureMockMvc` tạo `MockMvc` bean phù hợp Spring context. Không cần tự gọi `MockMvcBuilders.standaloneSetup(...)`, vì cách đó **không đảm bảo toàn bộ Security FilterChainProxy được gắn** nếu bạn quên `springSecurity()`/filters.

### Vì sao không dùng `@AutoConfigureMockMvc(addFilters=false)`?

Vì `addFilters=false` có thể **bỏ Security filters** ra khỏi MockMvc pipeline, khiến các tests CORS, CSRF, headers và authorization **xanh giả hoặc fail vì không thực thi chính sách**. Trong bài này, dùng default `addFilters=true` của `@AutoConfigureMockMvc`. Đây là điều cốt lõi của security integration test.

## 14. Smoke test HTTP thực bằng curl

MockMvc đủ để kiểm servlet filter behavior, nhưng không mở real socket. Khi muốn xem HTTP bytes ở môi trường dev/sandbox, chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Trong terminal khác, dùng HTTP localhost và tài khoản **demo test-only**.

### Public endpoint

~~~bash
curl -i http://localhost:8080/api/public
~~~

Kỳ vọng status 200, JSON body `{"message":"public-ok"}` và các security headers phù hợp. Trên HTTP thuần, HSTS mặc định **không** xuất hiện.

### 401 không có credentials

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Kỳ vọng 401, `WWW-Authenticate: Basic realm="demo"` và JSON `AUTH_REQUIRED`.

### 200 với Basic credentials test

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/orders
~~~

Kỳ vọng 200 và JSON array có order `ORD-001`. **Không dùng lệnh có password thật trong shell history/log CI**; đây chỉ là demo credentials.

### CORS preflight được phép

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/orders \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Kỳ vọng 200 cùng `Access-Control-Allow-Origin: https://portal.example.test`. Không cần credentials cho preflight.

### CORS preflight bị từ chối

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/orders \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

Kỳ vọng 403. **Không** có `Access-Control-Allow-Origin` cho origin này. Curl hiển thị HTTP response nhưng không áp dụng browser CORS policy; browser mới quyết định JavaScript có được đọc response hay không.

### POST có CSRF

Trong lab, việc tạo token CSRF bằng `csrf()` dễ nhất với MockMvc. Gửi curl POST không token vào API có CSRF enabled thường nhận 403; đây là kết quả mong đợi. Một browser session thật phải có cách lấy và gửi CSRF token phù hợp (meta tag, cookie token repository, form token hoặc CSRF endpoint được thiết kế an toàn). **Không tắt CSRF chỉ để curl POST trả 201.**

## 15. Test security thật sự phải gồm cả negative assertions

Một số tests chỉ xác nhận được phép:

~~~java
mvc.perform(get("/api/public"))
    .andExpect(status().isOk());
~~~

Test này không phát hiện policy đang cho mọi origin truy cập protected resources. Cần thử **đối nghịch**:

~~~java
mvc.perform(options("/api/orders")
        .header("Origin",
                "https://untrusted.example.test")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Các ca âm tính cần có **một biến sai tại một thời điểm**: origin, method, header, credentials, role, CSRF, body. Khi một test trộn origin sai + role sai + CSRF sai, status 403 có thể đúng dù phần cần kiểm đã bị tắt, khiến false positives.

### Mutation testing thủ công

Một cách review nhanh:

1. Tạm thêm origin lạ vào allowlist — test origin denied phải đỏ.
2. Tạm thêm method DELETE vào allowlist — test method denied phải đỏ.
3. Tạm thêm `X-Admin-Override` vào allowed headers — test header denied phải đỏ.
4. Tạm bỏ `http.cors` — test preflight allowed phải đỏ.
5. Tạm bỏ `.hasRole("EDITOR")` cho POST — test reader forbidden phải đỏ.
6. Tạm `csrf.disable()` — tests CSRF rejection phải đỏ.
7. Tạm bỏ CSP directives — test CSP header phải đỏ.
8. Tạm xóa Basic authentication — tests authentication/basic phải đỏ.

Hoàn nguyên từng thay đổi; không merge code cố ý yếu. Một test chỉ pass khi mọi thứ đúng **và đỏ khi phá đúng policy được bảo vệ** mới có giá trị cao.

## 16. HSTS, HTTPS và reverse proxy

HSTS là header yêu cầu browser dùng HTTPS cho một hostname trong thời hạn đã cấu hình. Spring Security mặc định phát header này trên HTTPS requests; thường có `max-age=31536000` và `includeSubDomains` tùy config.

### Vì sao HTTPS-only?

Trình duyệt chỉ nên học HSTS từ một HTTPS connection hợp lệ, tránh attacker trên HTTP path chèn chính sách tùy ý. Bài dùng `.secure(true)` để mô phỏng servlet request secure. Điều đó kiểm **HeaderWriter behavior** nhưng chưa kiểm:

- TLS certificate chain/hostname/SNI.
- Reverse proxy chuyển HTTP ở upstream thành HTTPS ở client.
- `Forwarded`/`X-Forwarded-Proto` có được trust đúng proxy hay không.
- HTTP→HTTPS redirect policy.
- HSTS presence trên response từ CDN/nginx, không chỉ app.
- HSTS `includeSubDomains` có ảnh hưởng subdomains mà team không quản lý hay không.

### Kịch bản production test

Nếu frontend qua `https://api.example.com` ở ingress, chạy một HTTPS smoke test qua ingress thực hoặc sandbox tương đương:

1. TLS handshake/certificate hợp lệ.
2. Response không bị redirect lặp.
3. HSTS có directives đúng chính sách.
4. CORS chính xác với origin frontend.
5. Không tin `X-Forwarded-Proto: https` từ client tùy ý khi ngoài trusted proxies.
6. Security headers không bị ingress ghi đè sai.
7. Các trang/JSON errors cũng giữ chính sách nếu có thể.

Không khuyến nghị bật `preload`/`includeSubDomains` mà không kiểm toàn bộ host/subdomains và khả năng vận hành HTTPS của tổ chức.

## 17. CORS preflight caching, Vary và reverse proxies

Browser có thể cache preflight kết quả theo `Access-Control-Max-Age` (trong demo là 600 giây), trong giới hạn riêng của browser. Vì vậy:

- Thay đổi CORS policy có thể không ngay lập tức tác động đến browser đang giữ preflight cache.
- CDN/reverse proxy cần tôn trọng cache keys đúng theo Origin, requested method và requested headers.
- `Vary: Origin` cùng các thành phần liên quan giúp caches không trộn responses cho hai origins khác nhau.
- Một CDN cấu hình sai có thể trả CORS headers của origin A cho origin B.
- `Access-Control-Max-Age` không phải `Cache-Control` của business response; chúng phục vụ hai cache cơ chế khác nhau.

### Nên test `Vary` thế nào?

Trong một integration test có CORS processor, có thể kiểm response có `Vary` liên quan. Tuy nhiên cách framework gộp header thành một dòng hoặc nhiều dòng có thể khác theo servlet container. Đừng assert một exact string khi HTTP header có danh sách/format hợp lệ khác. Để bảo vệ cache thực, cần test qua CDN/proxy hoặc test cache configuration riêng.

### CORS khi có nhiều SecurityFilterChain

Nếu app có nhiều chains (ví dụ `/api/**` bearer JWT, `/admin/**` form login), mỗi chain có security matcher riêng. CORS config phải gắn với chain cần nó; một chain thiếu `cors` hoặc có ưu tiên cao có thể khiến path trùng bị trả 401 preflight.

Trong dự án nhiều chains, thêm một CORS matrix theo **từng path và chain**. Không giả định chỉ vì `/api/orders` preflight pass thì `/admin/orders` cũng được xử lý đúng.

## 18. CSRF, cookie authentication và SameSite

CSRF và CORS thường bị trộn lẫn:

- **CORS** điều khiển khả năng JavaScript cross-origin đọc response và một số request flows.
- **CSRF** chống việc browser tự gửi ambient credentials tới hành động thay đổi trạng thái không được người dùng chủ động cho phép.
- **SameSite cookie attribute** là một lớp giảm CSRF/cross-site cookie sending, nhưng không phải lý do duy nhất để bỏ CSRF tokens.
- **Authentication** xác minh identity.
- **Authorization** kiểm permission của identity.

Trong demo, POST cần role EDITOR và CSRF token hợp lệ. `csrf()` của `spring-security-test` tạo token phù hợp với test; không cần tắt CSRF để kiểm authorization.

### CORS allowed origin không có nghĩa POST luôn thành công

Từ `https://portal.example.test`, preflight có thể pass 200 vì policy cho POST với Authorization/Content-Type. Nhưng request chính có thể:

- 401 nếu thiếu Basic credentials;
- 403 nếu role READER;
- 403 nếu role EDITOR nhưng thiếu CSRF;
- 400 nếu EDITOR có CSRF nhưng JSON invalid;
- 201 nếu EDITOR có CSRF và JSON valid.

Đây là **hành vi đúng** khi nhiều lớp bảo vệ cùng hoạt động. Một frontend bắt buộc phải xử lý cả trường hợp browser CORS network-level error và HTTP JSON error khi CORS cho phép đọc response.

### Khi nào tắt CSRF cho API?

Một stateless API chỉ chấp nhận Bearer token trong Authorization header, không dùng cookie/session/ambient browser credentials, có thể không cần CSRF như app dùng session cookie. Quyết định phải dựa trên **threat model**, authentication transport và clients, không dựa vào việc API trả JSON.

Nếu tắt CSRF có chủ đích, viết test khẳng định request bảo vệ bằng **Bearer authentication/authorization** vẫn đúng và không mở endpoint anonymous. Không copy `.csrf(csrf -> csrf.disable())` vào mọi Spring REST app vì gặp lỗi 403.

## 19. Authentication errors: không để lộ account enumeration

Một phản hồi lỗi authentication tốt nên thống nhất về thông tin công khai. Ví dụ sai:

~~~json
{"message":"User alice@example.com exists but entered wrong password"}
~~~

Điều này có thể tiết lộ sự tồn tại của user. Tương tự:

~~~json
{"message":"User not found in table internal_users where id=..."}
~~~

có thể làm lộ schema. Với API demo:

~~~json
{"code":"AUTH_REQUIRED"}
~~~

cho cả **thiếu credentials** và **Basic password sai**. Internal logs có thể ghi error type, request ID và context đã sanitize để điều tra. Không log raw Authorization header, cookie, password, token, PII ngoài chính sách.

### Header `WWW-Authenticate`

HTTP Basic dùng `WWW-Authenticate: Basic realm="demo"` cho 401. Với OAuth2 Resource Server/Bearer token, response thường có challenge với Bearer scheme và các error codes cụ thể theo RFC 6750. **Không tái sử dụng Basic challenge** nếu ứng dụng thực dùng JWT/OAuth2.

Khi test migration sang JWT, cần kiểm:

- Không có Bearer token → 401.
- Token sai chữ ký/hết hạn/sai issuer/audience → 401 theo cấu hình.
- Token hợp lệ thiếu scope/authority → 403.
- Token hợp lệ đủ scope → 200/201.
- Body lỗi không chứa signed token/secret/internal exception.
- CORS preflight vẫn được xử lý trước authentication.

Trong Spring Security, `spring-security-test` có `jwt()`/`opaqueToken()` request post-processors cho unit/integration authorization tests, nhưng chúng **không tự chứng minh token decoder/remote JWKS HTTP validation**. Khi cần kiểm decoder, phải có test riêng cho auth server/JWKS wiring.

## 20. Authorization: role checks chưa đủ cho dữ liệu đa tenant

Role `EDITOR` được quyền POST orders trong lab. Nhưng production thường còn cần **object-level authorization**:

- Editor tenant A không được đọc order tenant B.
- User chỉ được sửa account thuộc organization của họ.
- Admin role có thể chỉ áp dụng một miền dữ liệu.
- Service phải kiểm ownership trước write, không chỉ request path.
- Repository queries phải filter tenant ID/ACL đúng.
- Không trả dữ liệu nhạy cảm qua IDOR (`/api/orders/{otherTenantId}`).

Các checks cần **integration test ở service/data layer** có fixture theo user/tenant, kết hợp withMockUser/JWT claims hoặc real authentication mechanism. Một test chỉ bảo vệ HTTP role matcher không chứng minh toàn bộ ABAC/ownership policy.

### `denyAll` cuối cùng

Dùng `anyRequest().denyAll()` giúp endpoint mới chưa được cho phép mặc định bị chặn. Đây là defense-in-depth, không thay permission model. Khi đặt `permitAll()` cho health/docs/static assets, nên review từng path và role, không mở `/**` để API chạy.

## 21. Xử lý lỗi bảo mật và Problem Details

Spring Framework cung cấp `ProblemDetail` để biểu diễn HTTP API errors theo chuẩn Problem Details. Tuy nhiên security filters không tự đi qua `@RestControllerAdvice`, nên nếu team muốn cùng schema cho MVC và Security, cần:

1. Thiết kế public error schema ổn định (ví dụ `type`, `title`, `status`, `code`, `requestId`).
2. Chọn `AuthenticationEntryPoint` để dựng 401.
3. Chọn `AccessDeniedHandler` để dựng authorization 403.
4. Nếu muốn JSON cho CSRF 403, cấu hình handler đúng tầng filter và kiểm lại các paths; không giả định handler role-denied sẽ bao phủ tất cả CSRF scenarios.
5. Nếu muốn JSON cho CORS rejection, cần xử lý đúng CORS processor/filter; cân nhắc browser không cho JS đọc response của origin bị từ chối.
6. `@RestControllerAdvice` xử lý MVC validation/business exceptions.
7. Cùng test security headers, content type và thông tin bị lộ trên mọi error paths.

### Một số status codes không được đổi tùy tiện

- Missing/invalid credentials ở protected endpoint: **401**, không tự chuyển thành 403 để “tránh popup Basic” khi hợp đồng auth cần challenge.
- Authenticated nhưng không có permission: **403**.
- JSON/body invalid sau security: **400** (hoặc status khác khi có contract rõ).
- Rate limiting: **429 Too Many Requests**, không phải auth failure.
- Internal exception: **500**, trả lỗi tổng quát, không stack trace.
- CORS forbidden: server có thể dùng 403 nhưng **browser JS không nhất thiết đọc được body**.

Không đưa raw exception reason từ `AccessDeniedException`, JWT parsing, database, LDAP hoặc authorization service ra response. Lý do chi tiết nên ở logs/traces có quyền truy cập phù hợp.

## 22. Test bằng `@WebMvcTest` khi nào?

Full-context `@SpringBootTest` nạp toàn bộ application beans, nhanh chậm tùy độ lớn app. `@WebMvcTest` có thể là lựa chọn tốt để kiểm controller MVC binding/validation, nhưng **security testing** có những điều kiện cần nhận thức:

- Spring Boot MVC slice có thể include security configuration/filters tùy component scans và auto-configurations.
- Nếu project có custom SecurityFilterChain ở một `@Configuration` không được slice scan, cần `@Import(ApiSecurityConfig.class)` hoặc cấu hình rõ để test đúng chain.
- Nếu bạn dùng `@AutoConfigureMockMvc(addFilters=false)`, tests sẽ không kiểm security filters.
- Nếu controller inject service khác không thuộc MVC slice, cần `@MockBean` (Boot 3.3)/`@MockitoBean` ở các phiên bản Spring Framework mới hơn hoặc test configuration phù hợp.
- Unit controller test không thể thay test **Bean wiring/cors/filter-chain thật** nếu đó là hợp đồng.
- Với multiple chains, slice có thể nạp chỉ một phần và tạo false confidence.

**Nên chọn test nhỏ nhất đủ chứng minh hợp đồng**, nhưng đừng cắt khỏi test chính thành phần bạn đang muốn kiểm. Trong bài này, full-context MockMvc được chọn để giữ toàn bộ SecurityConfig thật mà không cần browser/server port.

### Khi cần `RANDOM_PORT` hoặc browser E2E

MockMvc gọi servlet pipeline **không mở TCP socket thật**. Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client hoặc Playwright/browser nếu mục tiêu gồm:

- Session cookie `SameSite`, `Secure`, `HttpOnly` qua browser;
- CORS enforcement thật của Fetch API;
- TLS handshake, HSTS qua HTTPS và reverse proxy;
- HTTP redirect/caching/CDN behavior;
- Network authentication proxies/forwarded headers;
- Cookie domain/path và credential mode;
- HTTP/2 hoặc WebSocket handshake.

Không claim rằng một header assertion trong MockMvc là end-to-end network security verification.

## 23. Chẩn đoán CORS và security tests thất bại

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| OPTIONS từ browser trả 401 | CORS xử lý sau authentication hoặc filter chain thiếu cors | Có `http.cors(...)` và source đúng chain/path |
| OPTIONS trả 403 dù origin đúng | Method/request header không có trong allowlist | Kiểm `Access-Control-Request-Method/Headers` thực |
| POST được trong Postman, browser báo CORS | Postman/curl không enforce CORS | Kiểm Origin/preflight + browser devtools |
| Preflight trả 200 nhưng browser vẫn chặn | Thiếu ACAO/ACAH/ACAM/ACAC phù hợp | Kiểm response headers thực, không chỉ status |
| Bật `allowCredentials` mà dùng `*` origin | Wildcard/credential conflict | Allowlist exact origins hoặc patterns được review |
| Localhost được, staging không | Scheme/port/subdomain khác | Phân biệt exact origin theo environment |
| CORS 403 nhưng body không phải JSON `ACCESS_DENIED` | CorsFilter từ chối trước security handlers | Kiểm policy và filter, không ép JSON auth error |
| Reader POST nhận 403 trước role check | Thiếu CSRF | Thêm `csrf()` trong test role-specific |
| Anonymous POST 403 thay vì 401 | CsrfFilter chạy trước authentication | Kiểm 401 bằng GET protected hoặc request có valid CSRF |
| POST invalid JSON nhận 403 thay 400 | Thiếu auth/role/CSRF | Cho request qua security trước khi kiểm validation |
| 401 không có `WWW-Authenticate` | Custom entry point không tạo Basic challenge | Cấu hình entry point đúng authentication scheme |
| 403 role-denied trả 401 | User chưa authenticated hoặc test principal setup sai | `httpBasic`/`user` đúng test goal |
| 200 khi không có credentials | Filter disabled hoặc path permitAll quá rộng | Kiểm @AutoConfigureMockMvc filters và SecurityFilterChain |
| `nosniff`/`X-Frame-Options` thiếu | HeaderWriterFilter bị bypass/custom disabled | Kiểm chain, headers config và filters |
| CSP không có | CSP không bật mặc định | Cấu hình `contentSecurityPolicy` rõ |
| Referrer/Permissions thiếu | Chưa opt-in | Cấu hình headers DSL |
| HSTS thiếu trên HTTP MockMvc | Đúng mặc định: HSTS chỉ HTTPS | Dùng `secure(true)`; kiểm proxy/TLS riêng |
| HSTS thiếu sau ingress HTTPS | Forwarded headers/proxy trust sai | Kiểm trusted proxy configuration và HTTPS smoke |
| Headers xuất hiện ở 200 nhưng thiếu ở 500 | Error dispatch/ingress/another chain | Test real error paths + filter registration |
| Browser vẫn có XSS dù CSP | CSP không thay output encoding/DOM sanitization | Review sinks, CSP directives và browser tests |
| Header origin của tenant này xuất hiện cho tenant khác | CDN cache `Vary` sai | Kiểm cache keys theo Origin |
| Test pass khi security disabled | Test chỉ mock controller/disable filters | Dùng MockMvc addFilters=true và negative tests |
| Test chạy riêng pass nhưng suite fail | Shared SecurityContext/cookies/MockMvc state | Isolate tests, không mutate global state |
| 401 body có stack trace/password | Error handler phản chiếu exception | Dùng stable error code, sanitize logs |
| AUTH_REQUIRED JSON cho wrong password fail | BasicAuthenticationFilter dùng entry point khác | Cấu hình Basic entry point và exception handling nhất quán |

### Debug có hệ thống

1. Ghi nhận method, path, Origin, `Access-Control-Request-*`, Authorization presence, CSRF presence (không log giá trị secrets).
2. Xác định request có phải **CORS preflight** không.
3. Xem request đã match đúng `SecurityFilterChain` chưa.
4. Xem `CorsConfigurationSource` áp dụng đúng path/origin/method/header.
5. Xem CSRF có chặn unsafe request trước auth/authorization không.
6. Phân biệt anonymous vs authenticated principal.
7. Kiểm role/authority prefix, request method matchers và `denyAll`.
8. Xem response headers và error body đến từ CORS, Security hay MVC.
9. Nếu header thiếu, xác định filter bị bỏ hoặc error dispatch qua chain khác.
10. Nếu chỉ browser fail, dùng browser DevTools + real HTTPS/cookie/credentials mode.
11. Nếu test xanh bất thường, tạm phá policy để chứng minh negative test đỏ.
12. Không thêm `permitAll()` hoặc `csrf.disable()` như cách chữa chung khi chưa biết root cause.

## 24. Threat-model-driven test matrix

Một bộ test production không chỉ chọn status codes theo thói quen. Hãy xác định loại client, dữ liệu và threat model:

| Threat | Mục tiêu test | Ví dụ |
| --- | --- | --- |
| Cross-origin data read | CORS origin allowlist/credentials | Origin không thuộc trusted list không nhận ACAO |
| CSRF | Unsafe methods cần token khi dùng cookies/session | POST thiếu token bị 403 |
| Unauthorized API access | Authentication trên protected paths | GET protected không credentials là 401 |
| Privilege escalation | Role/permission checks | READER POST là 403 dù CSRF hợp lệ |
| IDOR | Ownership/tenant checks | User A không đọc entity của B |
| Clickjacking | X-Frame-Options/CSP frame-ancestors | DENY / frame-ancestors none |
| MIME confusion | X-Content-Type-Options | nosniff |
| XSS | Output encoding/CSP | CSP tồn tại, browser script source bị hạn chế |
| Sensitive data caching | Cache-Control | no-store trên responses nhạy cảm |
| TLS downgrade | HSTS/HTTPS | HSTS trên secure, HTTPS ingress correct |
| Information disclosure | Error JSON/logging | Không có stacktrace, secrets, SQL queries |
| Wrong CORS cache | Vary/CDN behavior | Origin A không được tái sử dụng header cho B |
| Endpoint accidentally exposed | Deny-by-default | Unknown path/role không nhận 200 |

Không phải mọi API cần cùng một CSP/Permissions-Policy. Nhưng mỗi quyết định bảo mật nên có **lý do và assertion có thể phát hiện regression**.

## 25. Bài tập thực hành

**Bài A — phá preflight:** Xóa `http.cors(Customizer.withDefaults())` trong một branch test. Chạy `CorsPolicyTest` và giải thích vì sao preflight không còn đáp ứng ACAO đúng.

**Bài B — origin sai:** Thêm `https://untrusted.example.test` vào allowed origins rồi chạy negative test. Test phải phát hiện policy mở rộng ngoài ý muốn.

**Bài C — method allowlist:** Thêm DELETE vào `allowedMethods` nhưng không thêm controller DELETE. So sánh CORS preflight có thể pass trong khi DELETE thực vẫn 403/404/405 vì authorization/controller khác.

**Bài D — request header allowlist:** Thêm `X-Admin-Override` vào allowedHeaders. Negative preflight test phải đỏ, cho thấy test đang bảo vệ cấu hình.

**Bài E — credentials/wildcard:** Thử `setAllowedOrigins(List.of("*"))` cùng `setAllowCredentials(true)` trên môi trường test. Quan sát vấn đề cấu hình và giải thích vì sao không chấp nhận với credentialed requests.

**Bài F — header exposure:** Bỏ `setExposedHeaders(List.of("X-Request-Id"))`. Test `allowedOriginCanReadPublicExposedHeader` phải fail dù HTTP response vẫn có `X-Request-Id`.

**Bài G — 401 vs 403:** Dùng `httpBasic("reader","wrong-password")` so với `user("reader").roles("READER")` POST + csrf. Phân biệt authentication failure và authorization failure.

**Bài H — CSRF:** Bỏ `with(csrf())` trong POST role EDITOR. Expected 201 trở thành 403. Không chỉnh matcher thành 403 chỉ để test xanh khi bạn đang kiểm success path.

**Bài I — invalid token:** Thử `with(csrf().useInvalidToken())`, bảo đảm request bị từ chối dù authentication/role hợp lệ.

**Bài J — validation path:** Dùng EDITOR + CSRF hợp lệ nhưng `item=""` và `quantity=0`. Test phải trả 400 `INVALID_INPUT`. Sau đó bỏ `csrf()` và quan sát việc 403 xảy ra trước MVC.

**Bài K — headers trên error:** Bỏ `headers(...ContentSecurityPolicy...)`. Kiểm 200/401/403/400 đều được test phát hiện CSP thiếu.

**Bài L — HSTS:** Thay `.secure(true)` bằng HTTP request thường. Giải thích vì sao không có HSTS và cần HTTPS integration smoke qua reverse proxy.

**Bài M — deny all:** Tạm thay `anyRequest().denyAll()` bằng `permitAll()`. Kiểm request `/api/internal` không được mở công khai.

**Bài N — cookie credentials:** Thiết kế một application test với session cookie và CSRF token repository, rồi dùng browser E2E kiểm `SameSite`, `Secure`, `HttpOnly`, credentials mode và CORS.

**Bài O — multi-tenancy:** Tạo `GET /api/orders/{id}` với DB test có orders thuộc hai tenants. READER tenant A không được đọc tenant B dù đã authenticated.

**Bài P — JWT/Bearer:** Thay Basic demo bằng Resource Server. Viết tests missing/invalid/expired token 401, thiếu scope 403, đủ scope 200, preflight vẫn pass.

**Bài Q — ProblemDetail:** Dùng một JSON error schema thống nhất cho auth/forbidden/validation nhưng không đưa nội bộ ra client. Kiểm filter errors không được xử lý nhầm bởi MVC advice.

**Bài R — CSP browser:** Tạo HTML test page cần CSS/JS đã được cho phép, dùng browser kiểm CSP trên thực tế. Không chỉ assert header string.

**Bài S — CDN cache:** Tạo integration test qua reverse proxy để một origin không nhận cached ACAO của origin khác.

**Bài T — security test mutation:** Lần lượt phá allowlist/role/CSRF/CSP, chứng minh negative tests đỏ rồi hoàn nguyên config.

## 26. Checklist trước khi merge Spring Security tests

- [ ] Đã xác định client browser hay server-to-server, CORS có phải boundary thực tế không?
- [ ] Preflight OPTIONS được xử lý trước authentication và CSRF phù hợp?
- [ ] Allowed origins exact/controlled, không echo Origin không kiểm tra?
- [ ] `allowCredentials=true` không đi cùng `allowedOrigins("*")`?
- [ ] GET/POST/DELETE và requested headers có positive/negative cases riêng?
- [ ] Test preflight kiểm `Access-Control-Allow-*`, không chỉ HTTP status?
- [ ] Test actual cross-origin response kiểm ACAO và `Expose-Headers` khi cần?
- [ ] Test origin không được phép không nhận ACAO?
- [ ] Biết CORS không thay thế authorization?
- [ ] Đã kiểm anonymous 401, bad credentials 401, authenticated thiếu quyền 403?
- [ ] Tests CSRF có `csrf()` khi muốn kiểm role/controller behavior?
- [ ] Đã kiểm missing/invalid CSRF gây 403 ở unsafe methods?
- [ ] Validation test dùng user/role/CSRF hợp lệ để thật sự đi tới MVC?
- [ ] `AuthenticationEntryPoint` và `AccessDeniedHandler` có public JSON an toàn?
- [ ] `@RestControllerAdvice` không bị hiểu nhầm là handler mọi lỗi từ security filters?
- [ ] Basic/Bearer authentication có `WWW-Authenticate` đúng scheme nếu cần?
- [ ] `X-Content-Type-Options: nosniff` được kiểm?
- [ ] `X-Frame-Options: DENY` hoặc frame policy phù hợp?
- [ ] `Cache-Control` bảo vệ responses nhạy cảm?
- [ ] HSTS được kiểm trên HTTPS request, không ép nó có trên HTTP plain?
- [ ] CSP/Referrer/Permissions Policy đã bật ở app khi test yêu cầu?
- [ ] Security headers không biến mất trên 401/403/400?
- [ ] `@AutoConfigureMockMvc` giữ filters, không `addFilters=false`?
- [ ] Các security test không dựa toàn bộ vào mocked `SecurityFilterChain`?
- [ ] Với nhiều security chains, policy CORS/authorization được kiểm từng path?
- [ ] Với browser cookies và HTTPS reverse proxy, có network/browser test bổ sung?
- [ ] Không dùng test credentials hoặc `{noop}` trong production?
- [ ] Response/log không rò tokens, passwords, PII, SQL hoặc stacktrace?
- [ ] Test chạy độc lập, không dựa vào shared SecurityContext/cookies/test order?
- [ ] Test matrix có negative assertions để bắt policy mở rộng?
- [ ] Gradle/JUnit report xác nhận tests chạy thật, không chỉ cache task?

## 27. Tài liệu tham khảo

Các tài liệu sau làm nền cho ví dụ **Spring Boot 3.3.5 / Spring Security 6.3.x**. Với Spring Security 6.4+/7.x, một số DSL APIs có thể đổi hoặc bị deprecated; đối chiếu đúng version trước khi copy sang production.

- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS phải trước security, `CorsConfigurationSource`, Spring MVC integration.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): defaults, HSTS HTTPS-only, CSP, Referrer Policy, Permissions Policy.
- [Spring Security 6.3 API — HeadersConfigurer](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/config/annotation/web/configurers/HeadersConfigurer.html): DSL `contentSecurityPolicy`, `permissionsPolicy`, header writer configuration.
- [Spring Security — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): `springSecurity()`, request post-processors, filter registration.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()`, `@WithMockUser` và SecurityContext.
- [Spring Security — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html): `httpBasic()` tạo Authorization header cho test.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().useInvalidToken()`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF threat model, defaults và protection.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, servlet test scopes.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `UrlBasedCorsConfigurationSource`, allowed origins/headers/methods.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ControllerAdvice`/`@ExceptionHandler` trong MVC.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser behavior, preflight, credentials and headers.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security): HTTPS-only HSTS và các directives.

**Ghi nhớ:** Một bộ security tests chất lượng phải chứng minh cả **điều được phép** và **điều bị từ chối**. Với CORS, kiểm preflight và response headers theo origin/method/header; với security headers, kiểm default/opt-in và **HSTS trên HTTPS**; với lỗi, phân biệt 401 authentication, 403 authorization/CSRF/CORS và 400 MVC validation. Dùng MockMvc với **SecurityFilterChain thật**, giữ CSRF khi đó là contract, không để error handlers lộ thông tin, và bổ sung browser/HTTPS/proxy tests khi bảo vệ network boundary thực tế.
