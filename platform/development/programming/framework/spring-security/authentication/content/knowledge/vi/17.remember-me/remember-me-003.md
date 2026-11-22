# TokenBasedRememberMeServices và cookie có chữ ký trong Spring Security

## 1. Tổng quan: nhớ đăng nhập không đồng nghĩa với giữ session mãi mãi

Khi người dùng chọn **Ghi nhớ đăng nhập (Remember Me)**, website có thể cho phép họ trở lại sau khi phiên HTTP trước đó hết hạn mà không cần nhập lại mật khẩu ngay lập tức. Trình duyệt giữ một cookie có thời hạn dài hơn session; ở request sau, Spring Security kiểm tra cookie đó và tạo một đối tượng xác thực phù hợp.

Trong **Spring Security Servlet**, có hai hướng phổ biến:

- **`TokenBasedRememberMeServices`**: phát cookie có dữ liệu và chữ ký dạng băm được tính từ username, expiry, password hash đang lưu trên server và một key bí mật. Không cần lưu từng remember-me token trong database.
- **`PersistentTokenBasedRememberMeServices`**: phát cookie và lưu thông tin token trong `PersistentTokenRepository`, có thể áp dụng token rotation và quản lý/thu hồi bản ghi bên server.

Bài này tập trung vào **TokenBasedRememberMeServices và cookie có chữ ký**: cách hoạt động, cách nối vào form login, cấu hình key/cookie, sự khác biệt với session, cách tự động xác thực lại, giới hạn chống replay và các bài kiểm thử.

Phạm vi: **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC**. Ví dụ chạy được với Maven, có một tài khoản in-memory để học và các test tích hợp MockMvc. Đối với production, phải thay dữ liệu demo bằng user store và secrets management phù hợp.

### Mục tiêu cụ thể

1. Hiểu rõ `RememberMeServices.loginSuccess`, `loginFail`, `autoLogin` và điểm gọi chúng.
2. Phân biệt `UsernamePasswordAuthenticationFilter`, `RememberMeAuthenticationFilter`, `RememberMeAuthenticationProvider` và `UserDetailsService`.
3. Đọc đúng cấu trúc signed cookie và hiểu Base64 không phải encryption.
4. Dùng key ký giống nhau ở service/provider, không hard-code secret, đặt TTL và cookie flags hợp lý.
5. Kiểm chứng việc chỉ cấp cookie khi có opt-in, từ chối cookie bị sửa và chặn remember-me ở các endpoint đòi `fullyAuthenticated()`.
6. Nhận thức hạn chế bảo mật: **cookie bị đánh cắp có thể bị replay trước khi hết hạn**; logout xóa cookie hiện tại không bảo đảm thu hồi bản sao đã bị sao chép.

## 2. So sánh session, remember-me và bearer token

| Tiêu chí | HTTP session | Token-based remember-me | Bearer JWT |
| --- | --- | --- | --- |
| Dữ liệu client giữ | Cookie `JSESSIONID` | Cookie `APP_REMEMBER_ME` có chữ ký | Thường `Authorization: Bearer ...` |
| Server xử lý | Tìm `HttpSession` / `SecurityContext` | Tải user, tính lại signature, xác thực remember-me token | Kiểm tra chữ ký JWT, expiry, issuer, audience |
| Dữ liệu dài hạn trên server | Session store | Không có bảng token nhớ đăng nhập riêng | Có thể stateless hoặc có cơ chế revoke |
| Mục tiêu | Giữ trạng thái phiên đang hoạt động | Khôi phục danh tính sau phiên trước | Xác thực API theo access token |
| Thu hồi | Invalidate session | Đổi password hash/key, hết hạn hoặc account status | Theo TTL/revocation/introspection |
| Mức tin cậy | Có thể là login tương tác | Remembered identity, không phải fresh login | Tùy token type/claims và policy |

**Ví dụ:** User đăng nhập hôm nay và chọn nhớ đăng nhập. Session hết hạn sau vài giờ, nhưng remember-me cookie có thể còn giá trị trong nhiều ngày. Lần mở trang sau, server nhận cookie nhớ đăng nhập, kiểm tra nó rồi thiết lập `Authentication` mới; không “hồi sinh” session ID đã hết hạn.

Remember-me **không phải lưu mật khẩu ở trình duyệt** và cũng **không phải JWT**. Trình duyệt gửi một credential có giới hạn thời gian; server xác minh credential đó. Tên cookie, đường dẫn, domain, SameSite, Secure và HttpOnly phải được thiết kế phù hợp.

## 3. Cấu trúc cookie có chữ ký

Tài liệu Spring Security 6.x mô tả payload logic dưới dạng:

~~~text
base64(
    username + ":" +
    expirationTime + ":" +
    algorithmName + ":" +
    algorithmHex(
        username + ":" +
        expirationTime + ":" +
        password + ":" +
        key
    )
)
~~~

Ý nghĩa:

- `username`: định danh người dùng có thể tìm lại qua `UserDetailsService`.
- `expirationTime`: thời điểm hết hạn tuyệt đối, tính theo **milliseconds từ Unix epoch**.
- `algorithmName`: tên thuật toán dùng cho signature, ví dụ `SHA256`.
- `password`: giá trị từ `UserDetails.getPassword()` ở server, thường là **hash BCrypt/PasswordEncoder**, không phải mật khẩu gốc gửi cho client.
- `key`: bí mật của ứng dụng; cùng giá trị phải được dùng ở các thành phần remember-me liên quan.
- `algorithmHex(...)`: giá trị băm thể hiện dưới dạng hexadecimal.
- `base64(...)`: mã hóa biểu diễn để truyền qua cookie, **không che giấu dữ liệu**.

Một ví dụ định dạng sau khi giải Base64:

~~~text
student:1800000000000:SHA256:<signature-hex>
~~~

Đây là dữ liệu **minh họa hình dạng**, không phải cookie dùng để đăng nhập được. Signature phải được tính đúng bằng bí mật và dữ liệu server.

### Các bước kiểm tra khi nhận cookie

~~~text
Browser gửi Cookie: APP_REMEMBER_ME=...
                   |
                   v
RememberMeAuthenticationFilter
       (chưa có Authentication cho request)
                   |
                   v
TokenBasedRememberMeServices.autoLogin(...)
       - tìm và giải mã cookie
       - kiểm tra cấu trúc/expiry
       - UserDetailsService.loadUserByUsername(username)
       - kiểm tra account status
       - tính lại signature từ password hash + key
       - so khớp signature
                   |
                   v
RememberMeAuthenticationToken
                   |
                   v
AuthenticationManager / RememberMeAuthenticationProvider
                   |
                   v
SecurityContext + authorization + controller
~~~

Nếu cookie bị sửa username, expiry hoặc signature mà không tính lại đúng chữ ký, server từ chối. Thời điểm hết hạn cũng được đưa vào dữ liệu ký, nên client không thể hợp lệ hóa token bằng cách sửa thời gian hết hạn sau khi giải Base64.

**Base64 không cung cấp bí mật nội dung.** Tên username trong cookie có thể được đọc. Cookie còn hạn **có thể được gửi từ thiết bị khác** nếu bị đánh cắp; chữ ký chống sửa đổi chứ không ràng buộc người gửi với thiết bị ban đầu.

### Thời hạn bắt đầu khi nào?

Token-based remember-me có thời hạn tính từ **lần đăng nhập tương tác thành công và phát cookie**. Việc tự đăng nhập lại bằng remember-me cookie không mặc định phát lại một cookie mới để kéo dài thời hạn mãi mãi. Mặc định Spring Security dùng thời hạn thường là **14 ngày**; ví dụ dưới đây đặt **7 ngày**.

Phân biệt:
- `expirationTime` bên trong payload: milliseconds, được đưa vào dữ liệu ký và dùng khi xác minh.
- `Cookie Max-Age`: seconds, hướng dẫn trình duyệt giữ cookie.
- Session timeout: một cấu hình khác, không quyết định trực tiếp tuổi thọ cookie remember-me.

### Thuật toán SHA-256 và tương thích cookie cũ

Trong Spring Security 6.5, có constructor:

~~~java
new TokenBasedRememberMeServices(
    key, userDetailsService, RememberMeTokenAlgorithm.SHA256);
~~~

`encodingAlgorithm` dùng tạo chữ ký; `matchingAlgorithm` có thể dùng để xác minh cookie cũ không có trường thuật toán trong payload. Không nên chủ động sử dụng MD5 cho triển khai mới chỉ vì các ví dụ legacy có nhắc đến nó. Nếu cần migrate cookie cũ, đánh giá và giới hạn cửa sổ tương thích.

Định dạng này là giải pháp signed-cookie của Spring Security, **không cần tự viết HMAC/JWT codec**. Không bao giờ gửi signing key cho frontend.

## 4. Các thành phần phối hợp trong filter chain

`RememberMeServices` có ba phương thức chính:

~~~java
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication);
~~~

| Thành phần | Khi nào chạy | Nhiệm vụ |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | Người dùng gửi form username/password | Tạo yêu cầu xác thực tương tác |
| `AuthenticationManager`, `DaoAuthenticationProvider` | Khi login bằng password | Kiểm tra password bằng `UserDetailsService` và `PasswordEncoder` |
| `RememberMeServices.loginSuccess` | Sau login tương tác thành công | Kiểm tra opt-in, phát cookie nhớ đăng nhập nếu phù hợp |
| `RememberMeServices.loginFail` | Sau login tương tác thất bại | Có thể xóa cookie nhớ đăng nhập |
| `RememberMeAuthenticationFilter` | Request thiếu authentication nhưng có cookie nhớ đăng nhập | Gọi `autoLogin` và tiếp tục xác thực token |
| `RememberMeAuthenticationProvider` | Khi nhận `RememberMeAuthenticationToken` | Xác minh token theo key của remember-me mechanism |
| `UserDetailsService` | Khi cần lấy lại account | Cung cấp username/password hash/authorities hiện tại |
| `LogoutFilter` + LogoutHandler | Khi logout | Xóa cookie và xử lý session/logout policy |
| `SecurityContextRepository` | Khi load/save context | Khôi phục danh tính trong request/phiên, không thay remember-me signature |

### Đăng nhập tương tác

~~~text
POST /login
username=student&password=...&remember-me=on
            |
            v
UsernamePasswordAuthenticationFilter
            |
            v
DaoAuthenticationProvider: password hợp lệ?
            |
      +-----+------+
      |            |
     Sai          Đúng
      |            |
      v            v
loginFail(...)  loginSuccess(...)
      |            |
      v            v
401 + cookie     Nếu opt-in: tạo cookie ký
bị xóa          200 + session + remember-me cookie
~~~

### Đăng nhập bằng cookie ở request sau

~~~text
GET /api/me
chỉ gửi APP_REMEMBER_ME, không gửi JSESSIONID cũ
            |
            v
RememberMeAuthenticationFilter
            |
            v
TokenBasedRememberMeServices.autoLogin(...)
            |
            v
UserDetailsService + kiểm tra signature/expiry/account
            |
            v
RememberMeAuthenticationProvider
            |
            v
Authenticated principal ở mức remember-me
            |
            v
Authorization kiểm tra endpoint
~~~

Khi dùng `http.rememberMe(...)` trong `SecurityFilterChain`, Spring Security hỗ trợ lắp các cơ chế liên quan. Không cần tự thêm một `RememberMeAuthenticationFilter` độc lập nếu đã dùng DSL, tránh filter chạy trùng hoặc manager khác nhau.

## 5. Những lựa chọn cấu hình cần quyết định

| Cấu hình | Vai trò | Khuyến nghị |
| --- | --- | --- |
| `key` | Bí mật để tạo/kiểm tra token | Ngẫu nhiên, dài, tách môi trường, lưu secrets manager |
| `UserDetailsService` | Đọc user/password hash hiện hành | Cùng user store tin cậy với authentication |
| `RememberMeTokenAlgorithm.SHA256` | Thuật toán tạo signature | Lựa chọn tham chiếu cho Spring Security 6.5 |
| `setTokenValiditySeconds(...)` | TTL token/cookie | Chọn theo rủi ro; demo 7 ngày |
| `setParameter("remember-me")` | Field opt-in | Phải trùng tên field trong form |
| `setAlwaysRemember(false)` | Không tự cấp cookie | Mặc định nên tôn trọng opt-in |
| `setCookieName("APP_REMEMBER_ME")` | Tên cookie | Đặt tên có nhận diện rõ |
| `setUseSecureCookie(true)` | Chỉ gửi cookie qua HTTPS | Bắt buộc ở production |
| `setCookieCustomizer(...)` | Thêm thuộc tính cookie | `SameSite=Lax` theo threat model |
| `setMatchingAlgorithm(...)` | Fallback kiểm tra cookie legacy | Giữ SHA256 nếu không migrate dữ liệu cũ |

**Key phải nhất quán giữa các node.** Nếu server A phát cookie với key A nhưng server B dùng key B, người dùng bị từ chối nhớ đăng nhập không ổn định khi qua load balancer. Ngược lại, dùng **cùng key giữa dev và production** không an toàn. Cần một key bảo mật cho mỗi môi trường, được quản lý tập trung.

**Password hash cũng phải ổn định.** Nếu service tự `encode()` lại mật khẩu người dùng mỗi lần đọc từ database, BCrypt sinh salt mới làm hash thay đổi, khiến signature của cookie trước đó không còn khớp. Password hash phải được lưu và tải lại nhất quán cho tới khi password được thay đổi/rehash có chủ đích.

## 6. Chương trình Java 17 + Spring Boot 3.5 hoàn chỉnh

Demo sẽ có:
- `POST /login`: form-urlencoded, username/password và checkbox `remember-me=on`.
- `GET /api/csrf`: trả CSRF token cho client.
- `GET /api/me`: hiển thị username và cờ `rememberMe`.
- `GET /api/strong`: yêu cầu `fullyAuthenticated()`, không chỉ remember-me.
- `POST /logout`: logout và xóa cookie theo cơ chế framework.

`REMEMBER_ME_KEY` là environment/property bắt buộc. Production mặc định yêu cầu cookie `Secure`; localhost HTTP chỉ nên override một cách có chủ đích.

### 6.1. Cấu trúc dự án và Maven

~~~text
signed-remember-demo/
├── pom.xml
└── src/
    ├── main/java/demo/remember/SignedRememberApplication.java
    └── test/java/demo/remember/SignedRememberApplicationTests.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>signed-remember-demo</artifactId>
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
~~~

### 6.2. Mã nguồn chính

File `src/main/java/demo/remember/SignedRememberApplication.java`:

~~~java
package demo.remember;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices.RememberMeTokenAlgorithm;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SignedRememberApplication {

    public static void main(String[] args) {
        SpringApplication.run(SignedRememberApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Demo: password hash được tạo lại khi ứng dụng restart.
        // Production cần database với hash lưu ổn định.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    TokenBasedRememberMeServices rememberMeServices(
            UserDetailsService users, Environment env) {

        String key = env.getRequiredProperty("REMEMBER_ME_KEY");
        boolean secureCookie = Boolean.parseBoolean(
            env.getProperty("APP_REMEMBER_ME_SECURE", "true"));

        TokenBasedRememberMeServices services =
            new TokenBasedRememberMeServices(
                key, users, RememberMeTokenAlgorithm.SHA256);

        services.setMatchingAlgorithm(RememberMeTokenAlgorithm.SHA256);
        services.setTokenValiditySeconds(7 * 24 * 60 * 60);
        services.setParameter("remember-me");
        services.setAlwaysRemember(false);
        services.setCookieName("APP_REMEMBER_ME");
        services.setUseSecureCookie(secureCookie);

        // Spring Boot 3.5 hỗ trợ Servlet 6 Cookie attributes.
        services.setCookieCustomizer(
            cookie -> cookie.setAttribute("SameSite", "Lax"));

        return services;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            TokenBasedRememberMeServices rememberMeServices,
            Environment env) throws Exception {

        String key = env.getRequiredProperty("REMEMBER_ME_KEY");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/strong")
                    .fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/login")
                .successHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"status\":\"authenticated\"}");
                })
                .failureHandler((request, response, error) -> {
                    response.setStatus(
                        HttpServletResponse.SC_UNAUTHORIZED);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"error\":\"login_failed\"}");
                })
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(key)
                .rememberMeServices(rememberMeServices)
            )
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            // Không tắt CSRF cho form login bằng cookie.
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessHandler((request, response, auth) ->
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT))
            );

        return http.build();
    }

    @RestController
    static class Api {

        private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
        }

        @GetMapping("/api/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "rememberMe", trust.isRememberMe(authentication));
        }

        @GetMapping("/api/strong")
        Map<String, String> strong() {
            return Map.of("status", "interactive-login");
        }
    }
}
~~~

### 6.3. Những điểm then chốt trong cấu hình

**Key từ environment:** `Environment.getRequiredProperty("REMEMBER_ME_KEY")` khiến ứng dụng không khởi chạy nếu thiếu key. Không đặt secret hard-code trong code. Trong test, property được thiết lập riêng bằng `@SpringBootTest(properties=...)`; production dùng secret store hoặc biến môi trường.

**Service và provider cùng key:** cùng `key` được truyền cho `TokenBasedRememberMeServices` và DSL `rememberMe(...).key(key)`. Không dùng hai key khác nhau ở service/provider.

**Form login phát cookie:** `formLogin` dùng filter chuẩn của Spring Security; sau xác thực thành công, hook `RememberMeServices.loginSuccess` chạy và phát cookie khi form có `remember-me=on`. Success handler chỉ tạo JSON, không tự giả lập remember-me token.

**Cookie có phạm vi và TTL rõ:** `setTokenValiditySeconds(604800)`, cookie name `APP_REMEMBER_ME`, `HttpOnly` mặc định, `SameSite=Lax` qua Servlet cookie customizer. `APP_REMEMBER_ME_SECURE` mặc định `true`; chỉ cấu hình `false` khi chạy demo trên HTTP localhost.

**Không nhầm remembered và full login:** `GET /api/me` trả cờ `rememberMe` theo `AuthenticationTrustResolver`; `GET /api/strong` dùng `fullyAuthenticated()` để yêu cầu người dùng đăng nhập tương tác khi chỉ còn remember-me cookie.

**CSRF và logout:** vì browser tự đính kèm cookie, CSRF được giữ nguyên. Logout được giao cho DSL và các LogoutHandler tích hợp, bao gồm khả năng xóa cookie remember-me ở browser.

**Một hạn chế của user in-memory:** BCrypt tạo salt ngẫu nhiên khi ứng dụng restart, dẫn tới password hash khác; cookie ký bằng hash trước đó sẽ bị vô hiệu. Đây là hành vi phụ của demo, không phải cơ chế bắt buộc rotate token sau mỗi restart.

## 7. Chạy thủ công với curl

### 7.1. Chuẩn bị key và chạy ứng dụng

Trong terminal Bash trên môi trường localhost, cần có JDK 17+, Maven và OpenSSL:

~~~bash
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
export APP_REMEMBER_ME_SECURE=false
mvn spring-boot:run
~~~

`openssl rand -hex 32` sinh 32 byte ngẫu nhiên biểu diễn thành 64 ký tự hex. Lưu ý **chỉ** dùng `APP_REMEMBER_ME_SECURE=false` trong demo HTTP local; production phải dùng HTTPS và cookie Secure.

Trên Windows PowerShell, đặt hai biến môi trường tương ứng qua cơ chế secret generation phù hợp, rồi chạy `mvn spring-boot:run`. Trong production dùng cùng key giữa các instance và không thay tùy tiện trong thời gian cookie còn hiệu lực.

### 7.2. Lấy CSRF token

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Kỳ vọng JSON dạng:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<gia-tri-token-thuc-te>"}
~~~

Giữ cookie session trong `cookies.txt` và lấy token thật từ response. Không gửi nguyên văn placeholder.

### 7.3. Login có chọn remember-me

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <gia-tri-token-thuc-te>' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  --data-urlencode 'remember-me=on' \
  http://localhost:8080/login
~~~

Kết quả mong đợi `200 OK` và body:

~~~json
{"status":"authenticated"}
~~~

Có thể thấy `Set-Cookie: APP_REMEMBER_ME=...` với `Max-Age=604800`. Cookie này là signed token; không tự đưa giá trị thật vào log hay tài liệu. Thứ tự thuộc tính cookie và header tùy container/browser.

### 7.4. Login không chọn remember-me

Dùng cookie jar sạch và bỏ `--data-urlencode 'remember-me=on'`. Login vẫn có thể thành công và lưu session thường, nhưng không nên cấp **cookie remember-me mới**. Nếu browser còn cookie cũ từ lần login trước, hãy xóa cookie cũ trước khi kiểm tra, tránh hiểu nhầm.

### 7.5. Kiểm tra auto-login không có JSESSIONID

Chỉ gửi `APP_REMEMBER_ME` từ request đăng nhập có opt-in:

~~~bash
curl -i \
  -H 'Cookie: APP_REMEMBER_ME=<gia-tri-cookie-da-duoc-cap>' \
  http://localhost:8080/api/me
~~~

Kỳ vọng:

~~~json
{"username":"student","rememberMe":true}
~~~

Ngược lại, nếu dùng session cookie hợp lệ ngay sau login tương tác, response của `/api/me` thường có `rememberMe=false`.

### 7.6. Endpoint nhạy cảm và logout

~~~bash
curl -i \
  -H 'Cookie: APP_REMEMBER_ME=<gia-tri-cookie-da-duoc-cap>' \
  http://localhost:8080/api/strong
~~~

Chỉ remember-me **không thỏa** `fullyAuthenticated()`, nên endpoint yêu cầu đăng nhập tương tác lại. Với entry point API trong ví dụ, kỳ vọng HTTP 401.

Logout tương tác sử dụng `POST /logout` và CSRF token mới/current:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'X-CSRF-TOKEN: <csrf-token-hien-tai>' \
  -X POST http://localhost:8080/logout
~~~

Kỳ vọng `204 No Content` từ logout success handler. Cần lấy CSRF token sau login nếu token cũ đã bị xoay. Logout có thể xóa remember-me cookie trong browser, nhưng **không revoke bản sao cookie đã bị đánh cắp** trong một thiết kế signed-token không có kho revocation riêng.

## 8. Kiểm thử tích hợp bằng MockMvc

Chỉ test `UserDetailsService` hay decode Base64 chưa chứng minh remember-me thực sự được nối đúng với filter chain. Các test sau thử login có opt-in, không opt-in, tự đăng nhập chỉ bằng cookie, chống sửa expiry, trạng thái remembered và CSRF.

Tạo `src/test/java/demo/remember/SignedRememberApplicationTests.java`:

~~~java
package demo.remember;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "REMEMBER_ME_KEY=integration-test-secret-only",
    "APP_REMEMBER_ME_SECURE=false"
})
@AutoConfigureMockMvc
class SignedRememberApplicationTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-password");
        if (remember) {
            request.param("remember-me", "on");
        }
        return mvc.perform(request)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("authenticated"))
            .andReturn();
    }

    private Cookie signedCookie() throws Exception {
        Cookie cookie = login(true).getResponse()
            .getCookie("APP_REMEMBER_ME");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void optInIssuesCookieWithExpectedLifetime() throws Exception {
        Cookie cookie = signedCookie();
        assertEquals("APP_REMEMBER_ME", cookie.getName());
        assertTrue(cookie.isHttpOnly());
        assertEquals(7 * 24 * 60 * 60, cookie.getMaxAge());
        assertFalse(cookie.getValue().isBlank());
    }

    @Test
    void noOptInDoesNotIssueNewCookie() throws Exception {
        MvcResult result = login(false);
        assertNull(result.getResponse().getCookie("APP_REMEMBER_ME"));
    }

    @Test
    void interactiveSessionIsNotRememberMe() throws Exception {
        MvcResult login = login(true);
        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.rememberMe").value(false));

        mvc.perform(get("/api/strong").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void rememberedCookieAuthenticatesWithoutOldSession()
            throws Exception {
        Cookie cookie = signedCookie();

        // Không truyền JSESSIONID hay session từ lần login trước.
        mvc.perform(get("/api/me").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberMeCannotEnterFullyAuthenticatedEndpoint()
            throws Exception {
        mvc.perform(get("/api/strong").cookie(signedCookie()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tamperedExpiryDoesNotPassSignatureCheck() throws Exception {
        Cookie issued = signedCookie();
        String raw = new String(
            Base64.getDecoder().decode(issued.getValue()),
            StandardCharsets.UTF_8);
        String[] parts = raw.split(":", -1);

        assertEquals(4, parts.length);
        parts[1] = Long.toString(
            Long.parseLong(parts[1]) + 5_000L);

        String forged = Base64.getEncoder().encodeToString(
            String.join(":", parts).getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/api/me").cookie(
                new Cookie("APP_REMEMBER_ME", forged)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void malformedCookieIsRejected() throws Exception {
        mvc.perform(get("/api/me").cookie(
                new Cookie("APP_REMEMBER_ME", "invalid")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void badPasswordNeverIssuesUsableRememberMeCookie()
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("remember-me", "on"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        Cookie cookie = result.getResponse()
            .getCookie("APP_REMEMBER_ME");

        // loginFail có thể trả cookie xóa với Max-Age=0.
        assertTrue(cookie == null || cookie.getMaxAge() == 0);
    }

    @Test
    void csrfIsRequiredForInteractiveLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-password")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Dự kiến:** 9 bài kiểm thử thành công khi các dependency và cấu hình khớp với ví dụ. Đây là mã test để người học thực thi; không phải kết quả chạy đã quan sát trong một dự án production.

Những điểm đáng chú ý:
- Test `rememberedCookieAuthenticatesWithoutOldSession` chỉ đưa cookie nhớ đăng nhập, nhờ đó không nhầm với session còn hiệu lực.
- Test `tamperedExpiryDoesNotPassSignatureCheck` sửa **trường expiry đã được ký** và giữ nguyên signature, nên phải bị từ chối.
- Test login thất bại không cố assert “không có Set-Cookie”, vì `loginFail` có thể tạo một cookie **xóa** với `Max-Age=0`.
- Test endpoint `fullyAuthenticated()` xác nhận remembered principal không đồng nghĩa với lần đăng nhập tương tác mới.

Trong ứng dụng thật nên bổ sung test key rotation, password hash update, khóa user, hết hạn sau thời gian giả lập, logout và hành vi nhiều node.

## 9. Giới hạn lớn nhất: stolen-cookie replay

**Chữ ký bảo vệ tính toàn vẹn, không chống sử dụng lại một cookie bị đánh cắp.**

~~~text
Ngày 1: User đăng nhập, nhận cookie C còn hạn 7 ngày.
Ngày 2: Kẻ tấn công sao chép cookie C.
Ngày 3: User logout; browser xóa C.
Ngày 4: Kẻ tấn công gửi bản sao C tới server.
        Nếu C chưa hết hạn và key/password hash/account còn hợp lệ,
        token-based service có thể vẫn chấp nhận C.
~~~

Với token-based remember-me, hệ thống không có bản ghi token duy nhất để đánh dấu bản sao C là “đã bị thu hồi”. Những cách vô hiệu hóa có thể gồm:
- Để cookie hết hạn.
- Thay password hash của account, ví dụ đổi password.
- Đổi signing key (làm mất hiệu lực **tất cả** cookie ký bằng key cũ).
- Vô hiệu/khóa account qua user-status checker và policy.
- Chuyển sang thiết kế persistent-token/revocation nếu cần xử lý từng thiết bị.

Không coi `HttpOnly`, `Secure` hoặc `SameSite` là biện pháp thu hồi. Chúng giảm một số khả năng rò cookie hoặc gửi cookie trong các bối cảnh nguy hiểm, nhưng không biến bản sao bị đánh cắp thành vô dụng.

## 10. Token-based và persistent-token: khi nào chọn?

| Đặc điểm | TokenBasedRememberMeServices | PersistentTokenBasedRememberMeServices |
| --- | --- | --- |
| Có database token nhớ đăng nhập? | Không | Có `PersistentTokenRepository` |
| Kích thước vận hành | Nhẹ | Cần schema/cleanup và trạng thái token |
| Tạo/kiểm tra | Hash-signature từ username/expiry/password hash/key | Token series/value đối chiếu repository |
| Xóa cookie khi logout | Có | Có |
| Thu hồi một token cụ thể đã bị đánh cắp | Không có cơ chế stateful riêng | Có thể quản lý token/series server-side |
| Cần UserDetailsService | Có | Có |
| Mục đích phù hợp | Website rủi ro thấp-trung bình, TTL ngắn vừa đủ | Cần theo dõi và thu hồi tốt hơn |

Persistent token không phải “an toàn tuyệt đối”: cần quản lý database, rotation, lifecycle, detection khi token bị dùng lại và xử lý đồng bộ giữa các node. Nếu yêu cầu bảo mật rất cao, cân nhắc **không bật remember-me** cho loại tài khoản hoặc tài nguyên đó.

## 11. Authn trust level và quyền truy cập

Một remembered user có thể có `ROLE_USER` và vẫn không được phép thực hiện chuyển tiền hoặc thay đổi thông tin nhạy cảm. Spring Security phân biệt `isRememberMe(Authentication)` và các trường hợp fully authenticated. Do đó:

~~~java
// Đoạn cấu hình minh họa trong SecurityFilterChain:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profile").authenticated()
    .requestMatchers("/payments/**").fullyAuthenticated()
    .anyRequest().denyAll());
~~~

`fullyAuthenticated()` không chứng minh MFA đã hoàn thành, không bảo đảm lần xác thực đủ “gần” về thời gian, và không thay thế kiểm tra ownership/tenant. Với thao tác nhạy cảm, thiết kế step-up authentication và authorization tương ứng.

Remember-me filter chỉ giúp tạo lại danh tính; hệ thống **vẫn** phải kiểm tra authorities và quyền trên tài nguyên.

## 12. Key, cookie security và vận hành production

### Key và hash

- Key phải có entropy cao, tách môi trường và không commit vào repository.
- Các instance chung cụm dùng key nhất quán. Key khác nhau dẫn đến auto-login thất bại ngẫu nhiên.
- Key rotation sẽ làm cookie ký bằng key cũ mất hiệu lực; cần chuẩn bị UX yêu cầu login lại.
- Đổi password hash có thể làm cookie cũ không còn hợp lệ; đây thường là cơ chế tốt khi người dùng đổi mật khẩu.
- Nếu mỗi lần gọi `loadUserByUsername` lại tạo BCrypt hash mới thay vì đọc hash lưu ở DB, token không ổn định. Demo in-memory rehash khi **restart ứng dụng** nên cookie từ lần chạy trước cũng có thể mất hiệu lực.

### Cookie

- `Secure`: chỉ gửi qua HTTPS; cần bật ở production.
- `HttpOnly`: giảm nguy cơ JavaScript đọc trực tiếp cookie, nhưng XSS vẫn có thể gọi request với cookie tự đính kèm.
- `SameSite`: hỗ trợ giảm một số bối cảnh CSRF; không thay thế CSRF token.
- `Path/Domain`: giới hạn phù hợp, tránh gửi sang subdomain không đáng tin.
- `Max-Age`: là hướng dẫn cho trình duyệt, không thay kiểm tra expiration có chữ ký ở server.
- Không ghi nguyên header `Cookie` hoặc `Set-Cookie` vào log truy cập/trace.

### CSRF và CORS

Browser tự gửi cookie theo scope, nên ứng dụng nhớ đăng nhập vẫn cần phòng CSRF theo threat model. Form login và logout là các thao tác có thay đổi trạng thái; không tắt `csrf` chỉ vì dùng JSON.

Trong SPA tách origin, cần phân biệt `SameSite`, CORS allowlist và `fetch credentials`. Không cấu hình `Access-Control-Allow-Origin: *` cùng credentials; không dùng `SameSite=None` một cách vô điều kiện.

### Session

Remember-me không làm session vĩnh viễn. Session ID vẫn do Servlet container cấp, có thời hạn và cơ chế rotation/fixation protection riêng. Một request chỉ có remember-me cookie có thể được Spring Security dùng để dựng lại context, rồi ứng dụng có thể tạo phiên mới tùy cấu hình. Cần test session và cookie riêng.

## 13. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login đúng nhưng không có remember-me cookie | Quên `remember-me=on`, service không nối với filter, success không hoàn tất | Kiểm tra opt-in và DSL `http.rememberMe` |
| Cookie có trong browser nhưng request không gửi | Secure trên HTTP, sai domain/path, SameSite/CORS | Kiểm tra request headers và cookie scope |
| Request có cookie nhưng 401 | Sai key, expired token, password hash thay đổi, user bị disable | So khớp key, expiry, UserDetailsService |
| Lúc được lúc không qua nhiều node | Signing key khác giữa các instance | Đồng bộ secret trên cụm |
| Cookie mất hiệu lực sau mỗi restart demo | BCrypt re-encode hash in-memory | Dùng persistent user store khi vận hành thật |
| Quên login nhưng cookie cũ vẫn hiện diện | Login không opt-in không xóa mọi cookie cũ theo mong đợi | Test bằng cookie jar sạch, xác định UX |
| Cookie sửa expiry nhưng vẫn 200 | Có session khác đang xác thực, test không thực sự thử cookie-only | Bỏ JSESSIONID và sửa trường đã được ký |
| Logout xong vẫn vào được | Có session khác hoặc bản sao cookie chưa bị revoke | Kiểm tra session và sự khác nhau giữa xóa cookie/thu hồi |
| Endpoint nhạy cảm không yêu cầu login lại | Chỉ cấu hình `authenticated()` | `fullyAuthenticated()` / step-up auth |
| 403 trên login | CSRF token thiếu/sai | Giữ cookie phiên, lấy token mới và gửi header đúng |
| Token hợp lệ nhưng quyền không đúng | UserDetailsService/authority mapping không nhất quán | Kiểm tra authorities nạp từ server |
| Mọi user được nhớ mà không hỏi | `alwaysRemember=true` | Đặt false và cung cấp checkbox |
| Key xuất hiện trong source/log | Quản lý secrets sai | Chuyển secret store, rotate key, audit |

## 14. Checklist bảo mật và kiểm thử

- [ ] Chỉ phát remember-me cookie sau **interactive login thành công** và opt-in rõ.
- [ ] Key bí mật dài, an toàn, ổn định trên nhiều node, tách dev/staging/prod.
- [ ] `TokenBasedRememberMeServices` và `RememberMeAuthenticationProvider` dùng key nhất quán.
- [ ] Sử dụng algorithm phù hợp (ví dụ SHA-256) và TTL hạn chế.
- [ ] `UserDetailsService` tải password hash hiện tại, không tự rehash ngẫu nhiên mỗi request.
- [ ] Account locked/disabled không thể auto-login qua cookie còn hạn.
- [ ] Cookie `Secure` khi HTTPS, `HttpOnly`, `SameSite` và domain/path được xem xét.
- [ ] CSRF protection vẫn hiệu lực với các request dùng cookie.
- [ ] Test phân biệt session login và cookie-only remember-me.
- [ ] Test sửa expiry/signature, cookie sai, không opt-in, login sai và logout.
- [ ] Yêu cầu re-auth/step-up cho endpoint nhạy cảm, không chỉ kiểm tra `authenticated()`.
- [ ] Không log signing key, password hash, Cookie hoặc Set-Cookie chứa credential.
- [ ] Có phương án xử lý đánh cắp cookie: password reset/key rotation hoặc persistent tokens.
- [ ] Cân nhắc khối lượng token cũ khi thay key/algorithm trong rollout.
- [ ] Không tự viết lại thuật toán ký hoặc xây JWT decoder cho cookie này.

## 15. Câu hỏi tự kiểm tra

1. `TokenBasedRememberMeServices` cần `UserDetailsService` để làm gì?
2. Tại sao Base64 không bảo vệ tính bí mật của username trong cookie?
3. Trường expiry nằm trong chữ ký mang lại khả năng gì?
4. Khi nào `loginSuccess`, `loginFail` và `autoLogin` được gọi?
5. Vì sao `RememberMeAuthenticationProvider` phải dùng cùng key?
6. Tại sao đổi password hash làm token cũ không hợp lệ?
7. Logout xóa cookie browser có đủ thu hồi token đã bị đánh cắp không?
8. Vì sao một principal có `ROLE_USER` vẫn có thể bị từ chối ở `fullyAuthenticated()`?
9. Cookie Secure/HttpOnly/SameSite có thay thế CSRF protection được không?
10. Khi nào `PersistentTokenBasedRememberMeServices` thích hợp hơn?
11. Vì sao test remember-me phải loại bỏ JSESSIONID?
12. Điều gì xảy ra khi mỗi node sau load balancer dùng key khác nhau?

## 16. Tài liệu tham khảo

1. Spring Security 6.5 — Remember-Me Authentication, signed cookie và persistent token: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
2. Spring Security 6.5 API — `TokenBasedRememberMeServices`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html
3. Spring Security 6.5 API — `AbstractRememberMeServices` (cookie, opt-in, TTL, Secure, LogoutHandler): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html
4. Spring Security 6.5 API — `RememberMeAuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html
5. Spring Security 6.5 API — `RememberMeAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationProvider.html
6. Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Kết luận:** `TokenBasedRememberMeServices` giúp nhận diện lại user qua **cookie có chữ ký** khi session cũ không còn, nhưng cookie đó là một bearer credential có thể bị replay nếu bị đánh cắp. Sử dụng key mạnh, TTL rõ ràng, opt-in, cookie security và yêu cầu login tương tác lại cho hành động nhạy cảm; chọn persistent-token hoặc cơ chế thu hồi khác khi cần kiểm soát theo từng thiết bị.