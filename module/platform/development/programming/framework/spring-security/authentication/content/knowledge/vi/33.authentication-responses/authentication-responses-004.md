# AuthenticationFailureHandler và lỗi tại endpoint đăng nhập trong Spring Security

## 1. Mục tiêu và phạm vi bài học

Một người dùng gửi `POST /login` với tên đăng nhập và mật khẩu. Server kiểm tra mật khẩu thất bại: browser nên quay lại trang đăng nhập với thông báo phù hợp, còn một API client có thể muốn nhận HTTP 401 cùng JSON lỗi chuẩn hóa. Spring Security cung cấp **`AuthenticationFailureHandler`** để quyết định **phản hồi ngay sau một lần thử authentication thất bại**.

Điểm khó là không phải mọi lỗi bảo mật đều đến từ cùng vị trí. **Đăng nhập thất bại ở authentication filter**, **truy cập trang bảo vệ khi chưa đăng nhập**, **thiếu quyền**, **thiếu CSRF token**, **validation lỗi JSON**, và **OAuth2/OIDC login callback thất bại** có các đường xử lý khác nhau. Đặt một handler sai chỗ có thể dẫn đến lộ dữ liệu tài khoản, redirect loop, API trả HTML thay vì JSON hoặc 500 không mong muốn.

Bài này giúp bạn:

1. Xác định vị trí `AuthenticationFailureHandler` trong luồng `UsernamePasswordAuthenticationFilter` → `AuthenticationManager` → `AuthenticationProvider`.
2. Phân biệt `AuthenticationFailureHandler` với `AuthenticationEntryPoint`, `AccessDeniedHandler` và `@ControllerAdvice`.
3. Biết hành vi mặc định của `SimpleUrlAuthenticationFailureHandler`, `failureUrl(...)`, `failureHandler(...)`, và khi nào nên chọn chúng.
4. Định nghĩa contract HTTP/JSON lỗi đăng nhập mà không tiết lộ user có tồn tại, bị khóa hay mật khẩu sai.
5. Viết ví dụ Spring Boot 3.5.x / Java 17+ có cả trải nghiệm form redirect và response JSON 401.
6. Kiểm thử failure/success, thiếu CSRF, chưa login, tài khoản disabled, key lỗi hoặc service unavailable bằng MockMvc.
7. Thiết kế logging, rate limiting, account lockout, chống brute force, timing side-channel, generic error message và session hygiene.
8. Hiểu giới hạn: handler chỉ định dạng/điều phối thất bại; **nó không thay thế việc kiểm chứng credential và không tự bảo vệ endpoint**.

**Phạm vi:** Servlet-based Spring Security với form login; các phần riêng nói về custom API filter, bearer, OAuth2 và reactive/WebFlux để biết nơi handler áp dụng khác nhau. Với Spring WebFlux, interface tương ứng là `ServerAuthenticationFailureHandler`, không dùng nguyên class Servlet.

## 2. Luồng thất bại tại POST /login

Đối với form login Servlet truyền thống, Spring Security cung cấp `UsernamePasswordAuthenticationFilter`, một subclass của `AbstractAuthenticationProcessingFilter`. Nó bắt request phù hợp `loginProcessingUrl` (mặc định POST `/login`), trích `username` và `password`, rồi tạo `UsernamePasswordAuthenticationToken` chưa được xác thực.

```text
Browser hoặc HTTP client
      |
      | POST /login
      | username=learner&password=wrong
      | CSRF token (nếu dùng session browser)
      v
SecurityFilterChain
      |
      | CsrfFilter (unsafe request cần token)
      |     |
      |     +-- CSRF sai/thiếu -> 403: KHÔNG phải auth failure handler
      |
      | UsernamePasswordAuthenticationFilter
      |     |
      |     | attemptAuthentication(request, response)
      |     v
      | AuthenticationManager (thường ProviderManager)
      |     |
      |     v
      | AuthenticationProvider (ví dụ DaoAuthenticationProvider)
      |     |
      |     | kiểm tra account/password/trạng thái
      |     v
      | AuthenticationException
      |
      | unsuccessfulAuthentication(...)
      |   1. SecurityContextHolder.clearContext()
      |   2. RememberMeServices.loginFail(...)
      |   3. AuthenticationFailureHandler.onAuthenticationFailure(...)
      |
      v
HTTP response
  - Browser: 302 Location: /login?error
  - JSON client: 401 + application/json (nếu tự cấu hình)
```

Luồng trên dựa trên contract `AbstractAuthenticationProcessingFilter` của Spring Security. Filter gọi handler **chỉ khi lỗi authentication được chuyển vào nhánh unsuccessful authentication**. Một exception do Controller, database, CSRF filter, custom filter sai thứ tự hoặc gateway tạo ra **không tự động** đi qua handler này.

### 2.1. Những bước Spring Security làm trước khi gọi handler

Trong cơ chế tiêu chuẩn:

- `AuthenticationManager.authenticate(...)` không chấp nhận credentials; một `AuthenticationException` được ném.
- `unsuccessfulAuthentication(...)` làm sạch `SecurityContextHolder` để request thất bại không được coi như vừa đăng nhập thành công.
- `RememberMeServices.loginFail(...)` được gọi. Nếu không cấu hình remember-me, thao tác này thường không có tác dụng.
- `AuthenticationFailureHandler.onAuthenticationFailure(request, response, exception)` quyết định URL redirect, forward, HTTP status/body hoặc phương án khác.

**Không tự gọi `SecurityContextHolder.getContext().setAuthentication(...)` trong failure handler.** Handler không được “cứu” credentials sai bằng cách cấp một Authentication hợp lệ.

### 2.2. Nhánh thành công khác hẳn

Nếu login thành công, Spring Security áp dụng session strategy, thiết lập/lưu `SecurityContext`, gọi remember-me success nếu có và cuối cùng đến `AuthenticationSuccessHandler`. Vì vậy:

- `AuthenticationFailureHandler` chỉ xử lý **thất bại của lần thử đăng nhập**.
- `AuthenticationSuccessHandler` điều khiển **phản hồi sau đăng nhập thành công**.
- Cùng một frontend JSON đôi khi cần **cả hai handlers** để không nhận 401 JSON khi sai mật khẩu nhưng lại nhận 302 HTML khi đúng mật khẩu.

## 3. AuthenticationFailureHandler có chữ ký gì?

Trong Servlet Spring Security 6.x/7.x (Jakarta), interface:

```java
package org.springframework.security.web.authentication;

public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
```

Đây là **chữ ký rút gọn để học**, cần import `jakarta.servlet.*`, `jakarta.servlet.http.*`, `java.io.IOException` và `org.springframework.security.core.AuthenticationException`; không phải class tự biên dịch độc lập.

Ba input quan trọng:

| Tham số | Cung cấp điều gì? | Lưu ý |
| --- | --- | --- |
| `HttpServletRequest` | Path, method, headers, session, correlation ID, client context | Mọi giá trị từ client đều là dữ liệu chưa tin cậy; đừng tin `username`/`Origin` làm bằng chứng |
| `HttpServletResponse` | Khả năng set status, headers, body hoặc redirect/forward | Chỉ nên commit response một lần; tránh redirect sau khi đã ghi body |
| `AuthenticationException` | Lỗi từ quy trình authentication, có thể là bad credentials, account disabled, expired, locked… | Thông điệp nội bộ không phù hợp để trả nguyên văn cho người dùng |

**Hợp đồng cốt lõi:** handler quyết định output. Nó không phải một endpoint MVC, không kiểm tra lại password, không làm authorization và không có lý do biết raw password.

### 3.1. Lỗi authentication là hierarchy, không phải HTTP status

Một số loại `AuthenticationException`:

| Exception | Ý nghĩa ở server | Gợi ý public response |
| --- | --- | --- |
| `BadCredentialsException` | Password/token không đúng hoặc bị ẩn thành bad credentials | Thông điệp chung “Đăng nhập không thành công” |
| `UsernameNotFoundException` | User không có trong user store; có thể được che thành BadCredentials | Không xác nhận account có tồn tại |
| `DisabledException` | Account disabled | Thường giữ thông điệp chung, hướng hỗ trợ trong kênh thích hợp |
| `LockedException` | Account locked | Cần policy cụ thể, tránh để endpoint cho attacker dò user |
| `AccountExpiredException` | Account hết hiệu lực | Không trả chi tiết nội bộ trong public login response |
| `CredentialsExpiredException` | Credential hết hiệu lực | Có thể mở flow đổi mật khẩu **sau khi xác minh đủ**, không tiết lộ tùy tiện |
| `AuthenticationServiceException` | Hạ tầng xác thực hoặc service gặp lỗi | Không nhầm thành “mật khẩu sai”, không để lộ stacktrace; cân nhắc 503 và alert |
| `ProviderNotFoundException` | Manager không tìm được provider hỗ trợ loại Authentication | Lỗi cấu hình cần vận hành xử lý, không phải hành vi đăng nhập thông thường |

**Đừng mặc định mọi lỗi đều “sai mật khẩu”.** Ở ranh giới public, nhiều lỗi nên được nhóm để chống enumeration; ở ranh giới vận hành, vẫn cần phân loại an toàn, monitoring và phân biệt lỗi phụ thuộc để không che sự cố hạ tầng.

## 4. Handler chuẩn có sẵn trong Spring Security

| Class/cơ chế | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `SimpleUrlAuthenticationFailureHandler` | Redirect tới `defaultFailureUrl`; nếu không có URL, có thể gửi 401 | Form login, redirect đơn giản |
| `formLogin(form -> form.failureUrl("/login?error"))` | Shortcut cấu hình failure URL | Chỉ cần redirect cố định |
| `formLogin(form -> form.failureHandler(...))` | Dùng handler do bạn cung cấp | JSON response, logging/metrics, phân nhánh |
| `ExceptionMappingAuthenticationFailureHandler` | Ánh xạ exception class name sang URL | Có luồng xử lý khác cho một số loại lỗi, phải chống enumeration |
| `DelegatingAuthenticationFailureHandler` | Chuyển tiếp handler dựa trên class exception | Nhiều strategy có hợp đồng rõ |
| `ForwardAuthenticationFailureHandler` | Internal forward thay vì HTTP redirect | Một số UI server-rendered, cần kiểm tra render/dispatcher path |
| `AuthenticationEntryPointFailureHandler` | Dùng `AuthenticationEntryPoint` để xử lý lần thử thất bại | Muốn thống nhất cách phát challenge/status cho HTTP/API |

Lưu ý: `SimpleUrlAuthenticationFailureHandler` có thể lưu exception trong request hoặc session tùy redirect/forward và cấu hình `allowSessionCreation`. Đừng coi `SPRING_SECURITY_LAST_EXCEPTION` là dữ liệu an toàn để render nguyên stack trace hoặc nội dung nhạy cảm cho người dùng.

### 4.1. Cấu hình ngắn nhất: failureUrl

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .formLogin(form -> form
            .failureUrl("/login?error")
            .permitAll())
        .build();
}
```

Đây là **trích đoạn** trong cấu hình Servlet. Nếu dùng trang login mặc định của Spring, `/login?error` thường hiển thị lỗi đăng nhập chung. Nếu tự cấu hình `loginPage("/login")`, ứng dụng phải có controller/template hiển thị trang đó.

### 4.2. Cấu hình thay thế: failureHandler

```java
@Bean
AuthenticationFailureHandler failureHandler() {
    return new SimpleUrlAuthenticationFailureHandler("/login?error");
}

@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        AuthenticationFailureHandler failureHandler)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .formLogin(form -> form
            .failureHandler(failureHandler)
            .permitAll())
        .build();
}
```

Nếu chỉ cần redirect tĩnh, `failureUrl(...)` đủ ngắn; đừng tự tạo class mới không cần thiết. Trong một `FormLoginConfigurer`, `failureUrl(...)` là shortcut chọn một handler; cấu hình cả `failureUrl` và `failureHandler` lẫn nhau dễ gây hiểu nhầm về giá trị cuối cùng. Hãy chọn một cách chính và test nó.

### 4.3. Chọn redirect hay forward?

| Tiêu chí | Redirect (thường 302) | Forward (nội bộ server) |
| --- | --- | --- |
| Browser URL sau thất bại | Thay bằng failure URL | Có thể giữ URL request gốc |
| Số HTTP round trips | Một response redirect + GET mới | Một request nội bộ |
| Request method | GET trang đích thường được browser thực hiện | Forward giữ request context/method theo servlet dispatch |
| Exception/flash state | Có thể lưu qua session tùy handler | Có thể giữ request attributes |
| Dễ dùng với SPA/API | Thường không tốt nếu API mong JSON | Cũng không tốt nếu API mong JSON |
| Cần quan tâm | Open redirect nếu URL sinh từ input không an toàn | Path, dispatch/authorization, template rendering và phương thức |

Đừng chuyển tới URL tùy ý lấy từ `next`/`redirect` query param của client. Nếu cần redirect sau login, dùng `RequestCache`/whitelist đích nội bộ hoặc cơ chế trusted mapping.

## 5. AuthenticationFailureHandler khác EntryPoint, AccessDeniedHandler và ControllerAdvice

Đây là phần quan trọng nhất khi debug: **handler đăng nhập thất bại không chịu trách nhiệm cho mọi 401/403**.

| Tình huống | Thành phần chính | Kết quả thường gặp |
| --- | --- | --- |
| `POST /login` mật khẩu sai, CSRF hợp lệ | `UsernamePasswordAuthenticationFilter` → `AuthenticationFailureHandler` | 302 `/login?error` hoặc custom 401 JSON |
| `GET /private`, chưa có Authentication | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Browser 302 tới `/login`; API 401 |
| `GET /admin`, đã login nhưng thiếu role | `AuthorizationFilter` → `AccessDeniedHandler` | 403 |
| `POST /login` thiếu CSRF token | `CsrfFilter`/CSRF access-denied handling | 403, thường **không gọi** failure handler |
| Controller `@RequestBody` không parse được JSON | MVC exception resolver / `@ControllerAdvice` | 400 hoặc lỗi validation đã định nghĩa |
| Custom filter đứng trước login filter tự ném exception | Chính filter/entry point/cấu hình chain tương ứng | Không tự động gọi failure handler của form login |
| OAuth2/OIDC callback báo lỗi IdP | OAuth2 authentication filter và handler riêng của `oauth2Login` | Redirect/error theo cấu hình OAuth2 login |
| Bearer token không hợp lệ ở resource server | Bearer authentication entry point/filter | 401 với `WWW-Authenticate: Bearer` theo hợp đồng, không dùng form handler |

**Câu nhớ nhanh:** `AuthenticationFailureHandler` là **kết quả của một lần thử login thất bại**, còn `AuthenticationEntryPoint` là **khởi đầu của login khi user muốn truy cập tài nguyên bảo vệ mà chưa đủ authentication**.

### 5.1. Ví dụ phân biệt ba request

```http
GET /private/me HTTP/1.1
Host: localhost:8080
```

Nếu anonymous: thường nhận `302 Location: /login`. Đó là luồng EntryPoint, **không phải** login failure.

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=learner&password=wrong
```

Nếu thiếu CSRF trong app bật CSRF: thường nhận **403 trước khi password được kiểm tra**. Lúc này handler đăng nhập thất bại không chạy.

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
X-CSRF-TOKEN: <valid-session-token>

username=learner&password=wrong
```

Nếu CSRF hợp lệ và password sai: `AuthenticationFailureHandler` xử lý, ví dụ redirect `/login?error`.

**Điểm debug phổ biến:** thấy 403 ở `POST /login` rồi cố sửa `failureHandler` là sai chỗ. Phải kiểm tra CSRF token, cookie/session và security chain trước.

## 6. Thiết kế response an toàn cho login failure

Không tồn tại một HTTP format duy nhất cho mọi kiểu client. Cần **hợp đồng rõ** và nhất quán.

### 6.1. Form UI: redirect với thông điệp chung

Ví dụ:

```http
HTTP/1.1 302 Found
Location: /login?error
Cache-Control: no-store
```

Trang `/login?error` có thể nói: **“Không thể đăng nhập. Kiểm tra thông tin hoặc thử lại sau.”** Tránh:

- “Username không tồn tại”;
- “Password đúng nhưng user bị khóa”;
- “Email này thuộc quản trị viên”;
- Chi tiết backend như SQL exception, provider class, LDAP DN hoặc token secret.

Các thông điệp quá cụ thể có thể hỗ trợ **user enumeration** và account targeting. Nếu có recovery flow, hãy xây dựng luồng nhất quán: ví dụ thông điệp “Nếu tài khoản hợp lệ, hướng dẫn sẽ được gửi” thay vì xác nhận email có tồn tại.

### 6.2. API client: HTTP 401 + JSON ổn định

Ví dụ phản hồi public của một login endpoint nhận form params nhưng yêu cầu JSON:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"error":"invalid_credentials","message":"Sign-in failed"}
```

Đây là output **mình chủ động lập trình** trong `AuthenticationFailureHandler`, **không phải default JSON của formLogin**. JSON body cần mã lỗi ổn định cho frontend; tránh echo `request.getParameter("password")` hoặc `exception.getMessage()`.

### 6.3. 401, 403, 429, 503 nên được hiểu thế nào?

- **401 Unauthorized:** yêu cầu authentication chưa được chấp nhận; phù hợp cho API login sai mật khẩu, token sai trong nhiều hợp đồng.
- **403 Forbidden:** user đã xác thực nhưng không có quyền hoặc CSRF validation thất bại; có thể xuất hiện ở POST login thiếu CSRF dù password chưa kiểm.
- **429 Too Many Requests:** cơ chế rate limit từ chối do vượt quota; nên định nghĩa retry window phù hợp và chống enumeration; rate limiting thường đặt **trước hoặc quanh** authentication chứ không chỉ trong failure handler.
- **503 Service Unavailable:** dependency xác thực không khả dụng, khác với user gõ sai mật khẩu; không nên biến mọi outage thành 401 rồi khóa tài khoản hàng loạt.

**Không quyết định status chỉ dựa vào tên exception một cách máy móc**; xem trust boundary, threat model, người gọi, retry behavior và hợp đồng API. Đặc biệt, đừng tạo khác biệt response/timing cho “user tồn tại nhưng disabled” so với “user không tồn tại” khi điều đó làm lộ thông tin.

### 6.4. Headers và dữ liệu nhạy cảm

- `Cache-Control: no-store` để tránh lưu cache response chứa dữ liệu liên quan xác thực.
- `Content-Type: application/json` khi trả JSON; set charset/encoding rõ.
- Không echo token, password, raw exception, stack trace hoặc internal user ID.
- Nếu dùng session cookies, cấu hình `Secure`, `HttpOnly`, `SameSite` phù hợp và HTTPS.
- Nếu phản hồi chứa correlation ID, sinh từ server hoặc sanitize trước khi log; không dùng user input để chèn header nguy hiểm.
- CORS allow origin chỉ cho frontend tin cậy, không thay authentication hay CSRF.

## 7. Ví dụ chạy được: Spring Boot 3.5.16, Spring Security 6.5, Java 17

Ví dụ này có một login form tiêu chuẩn, có thể:

- Thất bại từ browser thông thường → redirect đến `/login?error`.
- Thất bại từ HTTP client gửi `Accept: application/json` → status 401 + JSON chung.
- Thiếu CSRF ở `POST /login` → 403 trước handler, minh họa ranh giới.
- Đăng nhập thành công → SecurityContext/session theo Spring mặc định và cho truy cập `/private/me`.
- User bị disabled nhận cùng **public failure contract** với password sai.

Bài dùng **in-memory users và mật khẩu demo** để bạn chạy local, không được dùng nguyên dữ liệu này cho production. Trong dự án thật dùng database/directory/IdP và quản lý secrets.

### 7.1. Cấu trúc thư mục

```text
failure-handler-demo/
├── pom.xml
└── src/
    ├── main/java/demo/login/LoginFailureApplication.java
    └── test/java/demo/login/LoginFailureApplicationTests.java
```

### 7.2. File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>failure-handler-demo</artifactId>
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

Không cần thêm một artifact riêng cho `AuthenticationFailureHandler`: nó thuộc `spring-security-web`, được `spring-boot-starter-security` kéo vào project. `BCryptPasswordEncoder` và `DaoAuthenticationProvider` cũng nằm trong hệ Spring Security tiêu chuẩn.

### 7.3. File LoginFailureApplication.java

```java
package demo.login;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}

@Configuration
class LoginSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("suspended")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .disabled(true)
                .build()
        );
    }

    @Bean
    AuthenticationFailureHandler loginFailureHandler() {
        var browserRedirect =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, failure) -> {
            // Dữ liệu lỗi public giống nhau cho account missing/locked/
            // disabled/password wrong; không echo failure.getMessage().
            response.setHeader("Cache-Control", "no-store");

            String accept = request.getHeader("Accept");
            boolean wantsJson =
                accept != null && accept.contains("application/json");

            if (wantsJson) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setCharacterEncoding(
                    StandardCharsets.UTF_8.name());

                response.getWriter().write(
                    "{\"error\":\"invalid_credentials\","
                    + "\"message\":\"Sign-in failed\"}");
                return;
            }

            // HTML browser: giữ trải nghiệm formLogin mặc định.
            browserRedirect.onAuthenticationFailure(
                request, response, failure);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler loginFailureHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().authenticated())

            // CSRF bật mặc định. POST /login phải có CSRF token.
            .formLogin(form -> form
                .failureHandler(loginFailureHandler)
                .permitAll())

            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/private/me")
    Map<String, String> currentUser(Principal principal) {
        return Map.of("user", principal.getName());
    }
}
```

**Đọc code:**

1. `UserDetailsService` có hai bản ghi. `learner` enabled; `suspended` disabled. Cả hai có BCrypt password hash để demo rõ các failure paths.
2. `formLogin(...).failureHandler(loginFailureHandler)` đăng ký handler vào **login processing filter**; không đặt handler trong MVC controller.
3. `SimpleUrlAuthenticationFailureHandler("/login?error")` cung cấp phản hồi redirect/browser chuẩn; UI mặc định của Spring sẽ thấy query `error`.
4. Khi request báo `Accept: application/json`, custom handler ghi 401 JSON generic. Đây là một **sự chọn lựa theo Accept header**, không phải browser authentication hoặc authorization.
5. `HttpSecurity` giữ CSRF mặc định; nếu thiếu token, POST sẽ bị chặn trước khi vào provider, nên mã trả có thể là 403.
6. Controller `/private/me` chỉ nhận user sau khi Spring xác thực; `Principal` không thể được thay bằng username tùy ý từ request.
7. Mã **không** cho user biết account bị disabled hay password sai. Một service sản xuất nên log nguyên nhân nội bộ theo chính sách mà không ghi password/stacktrace ra public response.

**Giới hạn quan trọng:** code minh họa phân nhánh theo `Accept` bằng phép chứa chuỗi đơn giản. Ứng dụng nhiều content types nên dùng `MediaType` parsing/negotiation chuẩn, xử lý `q` values và thống nhất contract trên toàn API. Nó cũng chưa có rate limit/lockout/audit store.

### 7.4. Chạy ứng dụng

Cần Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Mở `http://localhost:8080/private/me` trong browser: Spring chuyển đến `/login`. Dùng:

```text
Username: learner
Password: local-demo-password
```

Đăng nhập thành công rồi mở `/private/me`, response minh họa:

```json
{"user":"learner"}
```

Nhập sai password: browser nhận redirect về `/login?error`. User `suspended` với đúng password demo cũng bị từ chối thay vì được cấp session.

**Không deploy mật khẩu cố định hoặc username “learner” cho môi trường thật.** Cần secret store, password policy, HTTPS, rate limiting và user store được quản lý.

## 8. Kiểm thử chi tiết bằng MockMvc

Bài test phải phân biệt đúng handler với các failure paths xảy ra trước hoặc sau nó. Spring Boot 3.5 dùng `@SpringBootTest`, `@AutoConfigureMockMvc` và `spring-security-test`.

Tạo `src/test/java/demo/login/LoginFailureApplicationTests.java`:

```java
package demo.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousRequestUsesEntryPointNotFailureHandler()
            throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login")
                /* MockMvc's Location may be relative in some setups */);
    }

    @Test
    void badPasswordRedirectsToGenericLoginError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void nonexistentUserAlsoGetsGenericLoginError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "unknown")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void disabledAccountDoesNotRevealCause()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "suspended")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void jsonClientGets401WithoutInternalError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .accept(MediaType.APPLICATION_JSON)
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                .value("invalid_credentials"))
            .andExpect(jsonPath("$.message")
                .value("Sign-in failed"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLoginFailureHandler()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validPasswordIsNotHandledAsFailure()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Lưu ý về test redirect**: MockMvc có thể hiển thị `Location: /login` hoặc URL tuyệt đối tùy servlet/mock/redirect strategy và proxy context. Để test ổn định hơn giữa các cấu hình, thay assertion cụ thể trong test thứ hai bằng matcher về status, kết hợp kiểm tra `Location` kết thúc bằng `/login` hoặc dùng `redirectedUrlPattern("**/login")` nếu project đã thống nhất dạng URL. Thực hành chuẩn không nên chốt `http://localhost/login` khi response thực của môi trường là `/login`.

Ví dụ test không phụ thuộc Location tuyệt đối:

```java
@Test
void anonymousRequestIsRedirectedForAuthentication()
        throws Exception {
    mvc.perform(get("/private/me"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string("Location",
            org.hamcrest.Matchers.endsWith("/login")));
}
```

Để dùng đoạn trên, thêm static import `MockMvcResultMatchers.header`; đoạn này có thể thay cho test thứ hai khi URL do environment thay đổi.

Chạy:

```bash
mvn test
```

**Kỳ vọng:** sau khi điều chỉnh assertion `Location` theo cấu hình Spring/MockMvc thực tế, **8 test pass** nếu project và dependency đúng. Đây là kiểm tra HTTP/chain ở mức MockMvc; nó **không** đo khả năng chống brute force ngoài thực tế, không kiểm tra secret store/IdP thật, TLS hay proxy headers.

### 8.1. Vì sao không assert Exception.getMessage()?

- Message phụ thuộc provider, locale, user store và phiên bản.
- Nội dung chi tiết có thể làm lộ user existence/account status.
- Các backend như LDAP/AD hoặc IdP có mã lỗi riêng.
- Public contract nên ổn định theo **error code** hoặc URL lỗi đã quy định, còn server logs có structured reason code an toàn.

### 8.2. Những test production nên bổ sung

- JSON client với user không tồn tại, sai password và account disabled phải có **public response tương đương** (với chính sách cụ thể).
- CSRF token sai dù session đúng vẫn 403, không gọi handler password.
- Nếu có account lockout/rate limit, test quota, concurrency, reset window, time boundary và không tiết lộ user enumeration.
- Test khi user store down: không được trả 200, và không khóa hàng loạt user vì “bad password” giả.
- Test session sau failure không được tạo authentication thành công; sau success có principal đúng.
- Test CORS preflight/login endpoint qua ingress khi frontend khác origin.
- Test redirect không chấp nhận URL ngoài hoặc dấu CRLF từ query param.
- Test API/frontend contract xử lý 302/401/403 đúng, không coi status 200 sau fetch redirect là login success.

## 9. Khi frontend muốn gửi JSON body thay vì form-urlencoded

`UsernamePasswordAuthenticationFilter` mặc định đọc tham số request `username` và `password` của form login. Nó **không tự deserialize JSON body** như:

```http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"learner","password":"secret"}
```

Gắn `failureHandler(...)` chỉ thay **phản hồi khi xác thực thất bại**, không thay bộ phận **đọc input**. Nếu frontend muốn JSON login thật, có thể:

1. Thiết kế custom authentication filter dùng Spring Security `AuthenticationManager`; filter parse/validate JSON và gọi manager, sau đó dùng cùng failure/success handlers.
2. Dùng một cơ chế tiêu chuẩn khác phù hợp kiến trúc, ví dụ OIDC Authorization Code + PKCE với backend session hoặc OAuth2 token flow cho client phù hợp.
3. Có controller auth riêng nhưng phải chủ động thiết kế `SecurityContextRepository`, CSRF, session fixation, security events và exception behavior; không đơn giản gọi `authenticate()` rồi gửi cookie tự tạo.

**Không vô tình biến GET thành login bằng password query parameters.** Password không được đi vào URL do lịch sử browser, proxy logs, analytics và Referer. Nếu API dùng JSON request body thì phải xử lý content type, giới hạn payload, request validation và error contract ngay từ input filter.

### 9.1. Phản hồi JSON thành công cũng cần thiết kế

Một SPA có thể mong:

```json
{
  "user": "learner",
  "authenticated": true
}
```

Nếu chỉ cấu hình JSON failure handler nhưng vẫn giữ default success handler cho HTML, login đúng thường redirect đến saved request hoặc default URL, không tự trả JSON trên. Muốn contract hoàn toàn JSON, cần cấu hình **`AuthenticationSuccessHandler` tương ứng** và đảm bảo Spring Security thật sự save context/session hoặc phát token theo kiến trúc.

Đặc biệt, đừng trả JWT trong failure handler hoặc gắn “success”:true khi manager từ chối credentials.

## 10. Khi nào dùng AuthenticationEntryPoint thay vì FailureHandler?

**Trường hợp 1 — resource protected, chưa đăng nhập:**

```text
GET /private/me
  -> AuthorizationFilter: anonymous không đủ
  -> ExceptionTranslationFilter
  -> AuthenticationEntryPoint
  -> Redirect tới login form hoặc HTTP 401
```

**Trường hợp 2 — gửi credential sai trong login attempt:**

```text
POST /login + valid CSRF
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager
  -> BadCredentialsException
  -> AuthenticationFailureHandler
  -> 302 /login?error hoặc 401 JSON
```

Để API trả 401 thay vì redirect ở resource không có session, có thể cấu hình riêng entry point:

```java
// Trích đoạn Servlet SecurityFilterChain cho một API thực sự stateless:
http.exceptionHandling(ex ->
    ex.authenticationEntryPoint(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
```

Cần import `org.springframework.http.HttpStatus` và `org.springframework.security.web.authentication.HttpStatusEntryPoint`. Đoạn này **không điều khiển** nhánh POST login failure của form filter đã gắn `AuthenticationFailureHandler`.

Dùng nhiều `SecurityFilterChain` khi web UI có form login/session còn REST API dùng bearer token, JSON và stateless policy. Đừng cấu hình một entry point JSON toàn cục rồi vô tình khiến browser form login bị trả JSON khó hiểu.

## 11. Lỗi từ CSRF, CORS và AuthorizationFilter không thuộc cùng handler

### 11.1. CSRF

Session-based form login là một unsafe `POST` nên Spring Security mặc định yêu cầu CSRF token. Khi token thiếu/sai:

- `CsrfFilter` xử lý và từ chối request, thường 403.
- `UsernamePasswordAuthenticationFilter` chưa nhận được request để thử password.
- `AuthenticationFailureHandler` không có `BadCredentialsException` để xử lý.

**Đừng tắt CSRF** toàn app chỉ để thấy failure handler hoạt động với Postman. Hãy lấy CSRF token hợp lệ, giữ session cookie và gửi lại khi POST; với MockMvc dùng `with(csrf())` cho test login success/failure.

### 11.2. CORS

Preflight OPTIONS đến endpoint login thường không mang session cookie; CORS cần xử lý trước authentication. Nếu frontend khác origin thấy lỗi “CORS”, không nên sửa bằng cách đặt handler trả `Access-Control-Allow-Origin: *` hoặc coi origin là danh tính.

Cấu hình CORS bằng allowlist tin cậy, `http.cors(...)` và `CorsConfigurationSource` phù hợp. Backend vẫn cần kiểm tra credentials trên POST login và CSRF cho các request dùng browser session.

### 11.3. Thiếu role

Đã login nhưng không có role cần thiết là **authorization failure**. `AccessDeniedHandler` (thường thông qua `ExceptionTranslationFilter`) xử lý, có thể trả 403. Không đưa người dùng về `/login?error` như thể mật khẩu sai; điều đó gây nhầm lẫn và vòng login vô hạn.

## 12. Xử lý exception theo loại: cần chống user enumeration

Spring có `ExceptionMappingAuthenticationFailureHandler` và `DelegatingAuthenticationFailureHandler` để phân luồng dựa trên subclass `AuthenticationException`. Ví dụ concept:

```java
// Trích đoạn cấu hình, không phải class Java độc lập.
var handler = new ExceptionMappingAuthenticationFailureHandler();
handler.setDefaultFailureUrl("/login?error");
handler.setExceptionMappings(Map.of(
    CredentialsExpiredException.class.getName(),
    "/account/recovery"));
```

Điều này có thể hữu ích cho ứng dụng có quy trình an toàn riêng cho credential hết hạn. Nhưng **nguy cơ** là một attacker thử nhiều username và quan sát redirect để biết account nào tồn tại/đã hết hạn.

Các nguyên tắc:

1. Chỉ chuyển sang một flow đặc biệt sau khi caller đã có đủ bằng chứng danh tính, hoặc flow được thiết kế chống enumeration.
2. Cho response/thời gian trả lời tương tự giữa user không tồn tại và password sai khi khả thi.
3. Nếu hiển thị generic error, vẫn có thể log internal reason code với metadata tối thiểu cho incident response.
4. Không trả tên exception class, LDAP code, DB ID hay stacktrace cho public clients.
5. Với lỗi hạ tầng, quản lý status/retry riêng; đừng hạ xuống `BadCredentialsException` nếu nó che outage và kích hoạt lockout sai.

**Ý tưởng sai:** “DisabledException thì redirect /disabled-user?username=alice, BadCredentialsException thì /wrong-password”. Cách này cung cấp oracle liệt kê tài khoản.

## 13. Failure handler và giới hạn của remember-me/session

Một request đăng nhập thất bại không được tạo Authentication thành công mới. Tuy nhiên, thiết kế session cần được nhìn rộng hơn:

- Browser có thể vẫn có một **session đã đăng nhập trước đó** rồi gửi một lần login attempt khác; tùy chain và security context lifecycle, phải test chính sách reauthentication và xử lý session hiện hữu, không suy luận chỉ dựa vào response status.
- `unsuccessfulAuthentication(...)` dọn SecurityContext cho request và gọi `RememberMeServices.loginFail(...)`, nhưng các yêu cầu logout/invalidate session/clear custom cookie phải được thiết kế rõ cho threat model.
- CSRF token có thể bị thay khi login/logout theo chiến lược Spring; sau successful login, frontend SPA có thể cần lấy lại token mới.
- Không lưu raw password trong session hay `SPRING_SECURITY_LAST_EXCEPTION`; tránh render exception object trực tiếp ra template.
- Nếu dùng `SimpleUrlAuthenticationFailureHandler`, cần lưu ý `allowSessionCreation`, `useForward` và failure URL; không tự vô hiệu mọi session khi login sai vì có thể phá state cần thiết cho login UI hoặc gây DoS.

Với yêu cầu bảo mật cao, sau nhiều lần failed login có thể bắt buộc reauthentication, clear remember-me hoặc invalidate session theo policy. **Làm có chủ đích và có test**, không thực hiện bên trong một handler chung mà không phân tích trải nghiệm và session fixation.

## 14. Brute force, credential stuffing và rate limiting

Một handler trả thông điệp đẹp **không phải lớp phòng chống brute force**. Cần cơ chế hạn chế thử credential trước hoặc quanh authentication flow.

### 14.1. Các lớp phòng thủ

- Rate limit theo IP, IP range, user identifier chuẩn hóa và device/client signals khi phù hợp; chống attacker đổi IP để tránh quota.
- Khóa tài khoản theo chính sách có chống DoS (attacker cố tình làm khóa user khác).
- Progressive delay/step-up challenge ở các tình huống rủi ro; không tạo khác biệt đủ để enumeration.
- Monitor số lần thất bại, tỷ lệ login success/failure, nguồn traffic bất thường và password spraying.
- Dùng password hash phù hợp như Argon2id/bcrypt/scrypt cho mật khẩu lưu trữ; không so plaintext.
- Dùng HTTPS, session/cookie security, MFA và passkey khi phù hợp.
- Sau reset password hoặc account recovery, xem xét invalidate sessions/tokens theo chính sách và thông báo cho user.

### 14.2. Vì sao không chỉ sleep trong AuthenticationFailureHandler?

Phản ví dụ:

```java
// SAI cho production: giữ servlet worker thread khi attacker spam.
Thread.sleep(5000);
```

Nếu mỗi login sai giữ một request thread 5 giây, attacker có thể tạo **denial-of-service**. Rate limit nên do gateway/service lưu trạng thái thích hợp triển khai, có concurrency control và circuit breaker. Nếu dùng Java trong-process, phải xem nhiều instance/restart và không tạo memory leak theo mỗi username/IP.

### 14.3. Logging an toàn

Log **sự kiện**, không log secret:

```text
event=AUTH_LOGIN_FAILURE
request_id=<server-generated-id>
result=DENIED
reason_code=BAD_CREDENTIALS
client_ip=<validated-proxy-aware-address>
user_ref=<safe-pseudonymous-reference>
provider=form_password
```

Đây là **schema log minh họa**, không phải output mặc định Spring. Mã reason nội bộ có thể chi tiết hơn public response nhưng phải tuân thủ privacy/retention policy; không tự log raw username nếu không cần. Tuyệt đối không log password, CSRF token, session ID, bearer tokens hoặc stacktrace chứa thông tin nhạy cảm.

**Lưu ý:** `request.getRemoteAddr()` là địa chỉ kết nối thực của servlet, có thể là reverse proxy; chỉ tin `X-Forwarded-For`/Forwarded khi được proxy quản lý ghi lại và ứng dụng cấu hình trust boundary đúng. Không dùng header tùy ý từ Internet làm dữ liệu chắc chắn cho rate limiting.

## 15. API error contract và Problem Details

Đối với backend phục vụ SPA, có thể dùng mã lỗi ổn định và tùy chọn RFC 9457 Problem Details:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Sign-in failed",
  "instance": "/login"
}
```

Nếu dùng media type `application/problem+json`, hãy áp dụng schema/serialization, content negotiation và HTTP status phù hợp; đây là **ví dụ contract thiết kế**, không phải Spring form login tự tạo sẵn. Không nhét raw `AuthenticationException.getMessage()` vào `detail`.

Hãy phân biệt lỗi request format và lỗi auth:

| Tình huống | Contract gợi ý | Có qua form failure handler không? |
| --- | --- | --- |
| JSON malformed trong custom JSON login filter | 400 Bad Request | Tùy custom filter/exception handler |
| Username/password đúng định dạng nhưng credentials sai | 401 Unauthorized (JSON) | Có nếu filter chuyển `AuthenticationException` vào failure handler |
| POST thiếu CSRF token | 403 Forbidden | Thường không |
| Login bị hạn chế do quota | 429 Too Many Requests | Tùy nơi đặt limiter; không mặc định |
| Auth backend mất kết nối | 503 Service Unavailable nếu contract/chính sách phù hợp | Có thể có nếu được chuyển thành AuthenticationException, nhưng nên giám sát lỗi riêng |
| Đã login, thiếu role | 403 Forbidden | Không; AccessDeniedHandler |
| GET protected, chưa login | 302 /login hoặc 401 API | Không; AuthenticationEntryPoint |

**Đừng xây dựng API contract phụ thuộc một error message localization.** Frontend nên dựa vào `error`/`type` và HTTP status; text có thể thay đổi theo ngôn ngữ.

## 16. Custom authentication filter cần tự xử lý lỗi đúng vị trí

Không phải mọi login đều dùng `UsernamePasswordAuthenticationFilter`. Nếu viết API key/JWT login filter riêng:

1. Đọc và validate credentials từ request.
2. Tạo `Authentication` chưa xác thực.
3. Gọi `AuthenticationManager.authenticate(...)`.
4. Nếu thất bại, **gọi failure handler hoặc entry point phù hợp**, đừng mặc nhiên để exception nổi ra 500.
5. Nếu thành công, thiết lập SecurityContext, áp dụng session strategy/repository hoặc token issue đúng kiến trúc và gọi success handler.
6. Xóa credential nhạy cảm, clear context khi cần và không log secret.

Ví dụ **trích đoạn logic trong filter tự viết**, không phải full runnable class:

```java
try {
    Authentication accepted = authenticationManager.authenticate(
        new UsernamePasswordAuthenticationToken(username, password));

    SecurityContext context =
        SecurityContextHolder.createEmptyContext();
    context.setAuthentication(accepted);
    SecurityContextHolder.setContext(context);

    // Đối với stateful login còn cần session strategy,
    // SecurityContextRepository.saveContext(...),
    // success handler, CSRF/session lifecycle.
} catch (AuthenticationException failed) {
    SecurityContextHolder.clearContext();
    failureHandler.onAuthenticationFailure(
        request, response, failed);
    return;
}
```

Mã **không độc lập** và **không hoàn chỉnh cho một login filter production**: nó thiếu khai báo `authenticationManager`, `failureHandler`, request/response, các bước persist context/session, remember-me và success. Mục tiêu chỉ chỉ ra vị trí xử lý exception.

**Không coi catch-all `Exception` rồi trả 401 là an toàn.** Null pointer, lỗi DB, IOException, serialization hay bug nội bộ không nhất thiết là credential failure. Bắt `AuthenticationException` đúng contract, và để những lỗi kỹ thuật khác vào error pipeline có kiểm soát, monitoring và response 5xx khi phù hợp.

## 17. OAuth2/OIDC, bearer token và WebFlux có các handler riêng

### 17.1. OAuth2/OIDC login

Trong Spring Security Servlet, `oauth2Login()` có authentication filter riêng xử lý authorization response/callback. Có thể cấu hình:

```java
// Trích đoạn cấu hình, cần OAuth2 Client dependencies và IdP thật:
http.oauth2Login(oauth -> oauth
    .failureHandler(customOAuth2FailureHandler));
```

Không suy luận rằng `formLogin(...).failureHandler(...)` sẽ tự xử lý lỗi `invalid_state`, callback OAuth2, token exchange hoặc OIDC ID Token validation. Chỉ redirect về frontend với **mã lỗi generic**, không đưa authorization code, ID token hoặc raw provider error detail vào URL/log.

### 17.2. Resource Server / bearer

Một API nhận bearer token để gọi resource không nhất thiết có một “login endpoint” cùng filter. Bearer token sai thường được xử lý bằng `BearerTokenAuthenticationEntryPoint` và API trả HTTP 401 kèm `WWW-Authenticate: Bearer`; thiếu scope/quyền có thể thành 403. Đừng trả HTML `/login?error` cho một machine client đang gọi REST API.

### 17.3. WebFlux/reactive

Với WebFlux, interface là:

```java
// Chữ ký API reactive (minh họa, không phải full class):
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

Dùng `ServerAuthenticationFailureHandler` và `SecurityWebFilterChain` tương ứng. Không import `jakarta.servlet.http.HttpServletResponse` để xử lý reactive login.

## 18. Những lỗi phổ biến và quy trình debug

| Triệu chứng | Khả năng cao | Cách phân biệt |
| --- | --- | --- |
| POST /login sai password trả 403 thay vì redirect | Thiếu/sai CSRF token | Xem CsrfFilter, session cookie và token |
| POST /login trả 404 | Sai `loginProcessingUrl`, matcher/filter chain hoặc MVC route xung đột | Kiểm tra URL, method, SecurityFilterChain |
| Handler không chạy dù password sai | Request không khớp login filter hoặc đã bị filter trước chặn | Bật log DEBUG có kiểm soát và inspect filter order |
| Handler chạy nhưng redirect loop | Failure URL cũng yêu cầu authentication hoặc cấu hình EntryPoint sai | `formLogin(...).permitAll()` và mapping trang login |
| JSON frontend nhận HTML /login?error | Handler redirect thay vì JSON hoặc Accept không khớp | Kiểm tra Content-Type/Accept và handler configuration |
| JSON login sai password nhận 401 nhưng đúng password vẫn nhận 302 | Chỉ đổi failure handler, chưa đổi success handler | Thiết kế hai nhánh success/failure |
| Username không tồn tại có response khác user locked | Mapping exception quá cụ thể | Chuẩn hóa public response, cân nhắc timing |
| Không thấy 401/302 khi chưa login vào protected resource | Authorization matcher quá rộng, `permitAll()` che route | Kiểm tra `authorizeHttpRequests` và nhiều chains |
| Tài khoản disabled vẫn login được | Provider/custom authentication không kiểm tra account status | Kiểm tra UserDetailsChecker/provider contract |
| Mọi lỗi hạ tầng đều trả “wrong password” | Catch-all chuyển exception thành BadCredentials | Giữ phân loại service error và monitoring |
| 500 khi custom filter gặp bad key | Exception thoát khỏi filter trước ExceptionTranslationFilter | Custom filter bắt AuthenticationException, gọi handler |
| Browser login sai vẫn giữ user cũ | Session/security context lifecycle bị cấu hình sai | Test reauthentication, context clearing và session policy |
| Logged error chứa plaintext password | Handler/logging ghi raw request params | Redact secrets tại app, proxy, APM và error pipeline |
| Rate limit không có tác dụng khi deploy nhiều nodes | Counter chỉ lưu memory của từng node | Dùng store/distributed limiter phù hợp |
| Không phân biệt credential error với quyền user | Dùng AuthenticationFailureHandler để xử lý 403 authorization | Dùng đúng AccessDeniedHandler |

Trình tự kiểm tra:

1. Request có đi vào **đúng SecurityFilterChain** không? Path, method và context path khớp chưa?
2. Với form login, POST có CSRF token hợp lệ và session cookie tương ứng không?
3. `UsernamePasswordAuthenticationFilter` có bắt request không?
4. `AuthenticationManager` đang gọi provider nào? Exception cụ thể là gì ở log nội bộ?
5. `unsuccessfulAuthentication(...)` có gọi đúng `AuthenticationFailureHandler` được cấu hình không?
6. Handler trả 302/401/JSON phù hợp `Accept` và contract chưa?
7. Failure URL có thể truy cập anonymous không? Browser có redirect loop không?
8. Gateway/CORS/proxy có chỉnh Location, cookie, headers hoặc cache không?
9. Có lộ username existence, trạng thái account, password, token hoặc exception detail không?
10. Có rate limiting, audit và test concurrency không?

Spring Security debugging trong môi trường test có thể tăng log category bảo mật, nhưng **không bật wire request logging ghi username/password/session token lên production**.

## 19. Bài tập tự kiểm tra

1. **Sai password ở `POST /login` thường gọi gì?** `AuthenticationFailureHandler` trong authentication filter đã xử lý request.
2. **GET `/admin` chưa login dùng handler nào?** Thường `AuthenticationEntryPoint` sau luồng `ExceptionTranslationFilter`.
3. **Một user đã login nhưng thiếu `ROLE_ADMIN` được xử lý thế nào?** Authorization/access-denied (thường 403), không phải form failure handler.
4. **Tại sao POST /login thiếu CSRF trả 403 dù password sai?** `CsrfFilter` từ chối request trước lần thử authentication.
5. **Mặc định `failureUrl` là gì đối với form login?** Thường `/login?error`.
6. **Vì sao không trả `exception.getMessage()` cho client?** Có thể tiết lộ trạng thái tài khoản, provider details hoặc dữ liệu nội bộ, hỗ trợ enumeration.
7. **Một JSON SPA chỉ thay failureHandler đã đủ chưa?** Chưa; success handler, input parsing, session/token contract cũng cần tương thích.
8. **JSON body `{"username":...}` có tự được UsernamePasswordAuthenticationFilter đọc không?** Không; form filter mặc định dựa trên request parameters.
9. **`SimpleUrlAuthenticationFailureHandler` khác `AuthenticationFailureHandler` thế nào?** Interface là contract; class là implementation phổ biến để redirect/forward/401.
10. **DisabledException có nên luôn public một redirect riêng?** Không; phải đánh giá account enumeration và luồng recovery.
11. **Có thể dùng `@ControllerAdvice` để bắt mọi exception từ authentication filter không?** Không bảo đảm; authentication filter chạy trước MVC controller/exception resolver.
12. **Rate limiting nên chỉ nằm trong failure handler không?** Không. Cần hạn chế ở tầng request/authentication/gateway với state phù hợp và tránh DoS.
13. **Vì sao login sai không nên sinh valid SecurityContext?** Vì chứng minh credential thất bại; cấp session sẽ là bypass authentication.
14. **Tại sao Resource Server thường không redirect tới `/login?error`?** Machine clients mong 401/403 và bearer challenge, không mong HTML login.
15. **Khi nào dùng custom handler?** Khi cần response contract, metrics/audit hoặc điều hướng đặc biệt an toàn, không chỉ để đổi failure URL đơn giản.

## 20. Tài liệu chính thức để đối chiếu

- Spring Security – Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security – Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – AuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
- Spring Security – SimpleUrlAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html
- Spring Security – AbstractAuthenticationProcessingFilter API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
- Spring Security – ExceptionMappingAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/ExceptionMappingAuthenticationFailureHandler.html
- Spring Security – DelegatingAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationFailureHandler.html
- Spring Security – AuthenticationEntryPoint API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
