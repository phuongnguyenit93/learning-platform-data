# Đăng xuất bằng chuyển hướng cho web và phản hồi trạng thái cho API

> **Phạm vi:** Spring Security 6 trên **Servlet stack**, Java 17+, HTTP form login và HTTP API. Bài giải thích `LogoutFilter`, `LogoutHandler`, `LogoutSuccessHandler`, vì sao **website thường chuyển hướng sau đăng xuất** (HTTP 302 + `Location`) còn **API thường trả HTTP status** (như `204 No Content`), và cách cấu hình từng nhóm URL bằng `SecurityFilterChain`. Ví dụ chạy với Spring Boot 3.3.5 và có lưu ý quan trọng về CSRF, `HttpSession`, cookie, remember-me và token stateless.

## 1. Đăng xuất không chỉ là chuyển người dùng về trang login

Đăng xuất (logout) là một **quy trình phía server và client** để chấm dứt hoặc làm mất hiệu lực trạng thái xác thực đang được ứng dụng quản lý. Ở web truyền thống, điều này thường gồm làm vô hiệu `HttpSession`, xóa `SecurityContext`, dọn cookie hoặc token liên quan, rồi chuyển browser đến một trang phù hợp. Ở API, client thường mong một **HTTP status có thể xử lý bằng chương trình** chứ không muốn nhận HTML từ trang đăng nhập.

Hai trải nghiệm minh họa:

```text
WEB - Browser dùng form login và JSESSIONID

POST /logout + CSRF token + session cookie
    -> LogoutFilter chạy các LogoutHandler
    -> HTTP 302 Location: /login?logout
    -> Browser tự thực hiện GET /login?logout
    -> Hiển thị trang login / thông báo đăng xuất


API - Client gửi POST có CSRF token hợp lệ (trong demo)

POST /api/logout
    -> LogoutFilter chạy các LogoutHandler của API chain
    -> HTTP 204 No Content
    -> Client xử lý status và xóa credentials/token đang giữ nếu phù hợp
    -> Không có redirect tới trang HTML
```

**Tách biệt ba việc:**

1. **Cleanup:** xóa context, invalidate session, thu hồi cookie/token nếu cơ chế hỗ trợ.
2. **Kết quả giao thức:** redirect cho browser hoặc trả status cho API.
3. **Thu hồi quyền xác thực thật sự:** với session server-side có thể hủy phiên; với token tự chứa, HTTP Basic hoặc remember-me cookie bị sao chép, “đã nhận status 204” **không tự đồng nghĩa** token/credentials đã bị thu hồi.

Vì vậy yêu cầu “logout thành công” phải mô tả cả **server xử lý gì** và **client sẽ làm gì tiếp theo**. Không nên chỉ thay status 302 thành 204 rồi cho rằng hệ thống đã giải quyết toàn bộ bài toán thu hồi token.

## 2. Các thành phần trong Spring Security Servlet

| Thành phần | Vai trò |
| --- | --- |
| `SecurityFilterChain` | Xác định security filters/handlers cho từng URL web hoặc API |
| `LogoutFilter` | Nhận request khớp logout URL/matcher, chạy các `LogoutHandler`, rồi gọi `LogoutSuccessHandler` |
| `LogoutHandler` | Thực hiện cleanup: xóa context, session, cookie, state/remote token theo cấu hình |
| `SecurityContextLogoutHandler` | Thông thường invalidate `HttpSession` và xóa `SecurityContext` theo cấu hình |
| `CsrfLogoutHandler` | Xử lý CSRF token khi logout nếu CSRF được cấu hình |
| `CookieClearingLogoutHandler` | Có thể xóa thêm các cookies được khai báo |
| Remember-me logout handler | Xóa cookie hoặc bản ghi remember-me theo implementation tương ứng |
| `LogoutSuccessHandler` | Quyết định **HTTP response sau cleanup**: redirect, status, body, v.v. |
| `SimpleUrlLogoutSuccessHandler` | Success handler dùng URL đích, thường tạo redirect |
| `HttpStatusReturningLogoutSuccessHandler` | Success handler trả HTTP status thay vì redirect |
| `AuthenticationEntryPoint` | Xử lý **yêu cầu đăng nhập** khi chưa xác thực; không phải logout success handler |

Các interface cần nhớ:

```java
// Chữ ký rút gọn để hiểu contract (Spring Security đã định nghĩa).
public interface LogoutHandler {
    void logout(HttpServletRequest request,
                HttpServletResponse response,
                Authentication authentication);
}

public interface LogoutSuccessHandler {
    void onLogoutSuccess(HttpServletRequest request,
                         HttpServletResponse response,
                         Authentication authentication)
            throws IOException, ServletException;
}
```

Ở Spring Security 6, Servlet API dùng `jakarta.servlet.*` thay cho `javax.servlet.*`.

**Tư duy xử lý lỗi:** `LogoutHandler` nên thực hiện cleanup ổn định; theo thiết kế Spring Security, không dùng exceptions ở handler như một cách điều hướng thông thường hoặc mặc định cho client biết logout đã xong. Nếu phải gọi dịch vụ thu hồi token từ xa, cần chiến lược lỗi rõ ràng trước khi trả status thành công. `LogoutSuccessHandler` chỉ quyết định response **sau** các logout handlers, không tự đảm bảo mọi access token đã được vô hiệu hóa.

## 3. Bộ lọc LogoutFilter chạy ở đâu và vì sao quan trọng?

`LogoutFilter` thường nằm **trước các authentication filters** như `UsernamePasswordAuthenticationFilter` hoặc `BasicAuthenticationFilter` trong security chain. Nó chọn request thông qua `RequestMatcher`, chạy các logout handlers và gọi success handler.

```text
HTTP POST /logout hoặc POST /api/logout
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
SecurityFilterChain thích hợp (web / api)
    |
    v
CsrfFilter (kiểm tra CSRF nếu chính sách yêu cầu)
    |
    v
LogoutFilter
    |
    |-- Request có khớp logout matcher?
    |        |
    |        +-- Không -> tiếp tục qua authentication/authorization filters
    |        |
    |        +-- Có
    |             |
    |             v
    |       LogoutHandler(s)
    |       - dọn SecurityContext/session/cookie theo cấu hình
    |             |
    |             v
    |       LogoutSuccessHandler
    |       - Web: 302 Location
    |       - API: 204 No Content
    |             |
    |             v
    |       Hoàn thành HTTP response
    |
    +-- Không phải logout -> controller/filter khác tiếp tục
```

Do `LogoutFilter` được gọi sớm, **quy tắc `authorizeHttpRequests().authenticated()` ở phía sau không nhất thiết bảo vệ logout URL như một controller endpoint**. Một request logout có thể được xử lý trước khi đến `AuthorizationFilter`. Nếu API cần quyết định “chỉ người đã đăng nhập mới được revoke token của chính họ”, thiết kế phải có thành phần nhận dạng/kiểm chứng credentials **trước điểm thu hồi**, hoặc endpoint được bảo vệ/luồng revoke riêng. Không suy luận chỉ từ việc đặt `anyRequest().authenticated()`.

Với form login dùng session, việc logout không đòi hỏi server giữ một password trong request: session/context hiện tại là nguồn danh tính. Với stateless Basic, nếu `LogoutFilter` chạy trước `BasicAuthenticationFilter` thì request `POST /api/logout` có thể nhận 204 mà chưa hề chạy bước xác thực Basic. Điều này hợp lý nếu endpoint chỉ là thông báo “client hãy ngừng giữ credentials”, **không đủ** nếu nghiệp vụ cần thu hồi token thật sự.

## 4. Web logout: thường 302 chuyển hướng đến trang xác nhận

Với browser và form login, người dùng kỳ vọng trở lại trang đăng nhập hoặc màn hình công khai. Spring Security cung cấp Java DSL:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout")
        .permitAll()
);
```

Đây là **fragment** cấu hình bên trong method `SecurityFilterChain`, không phải class Java độc lập.

Khi form login và CSRF được bật theo mặc định:

1. Người dùng có session hợp lệ, gửi request **POST `/logout`** kèm CSRF token hợp lệ.
2. `CsrfFilter` kiểm tra token; yêu cầu sai token thường bị từ chối 403 trước khi logout được thực hiện.
3. `LogoutFilter` chạy các logout handlers được cấu hình; mặc định thường invalidate session, clear `SecurityContext`, xử lý CSRF token và các cookie liên quan theo handler hiện diện.
4. Success handler gửi redirect, ví dụ **302** và `Location: /login?logout`.
5. Browser tự GET URL đích và thấy trang login với thông báo tương ứng.

```http
HTTP/1.1 302 Found
Location: /login?logout
```

Chỉ hai dòng liên quan được minh họa; response còn có thể có security headers và `Set-Cookie` tùy hệ thống. `Location` có thể là URL tuyệt đối hoặc đường dẫn tương đối tùy proxy/context path.

### GET /logout có phải luôn logout?

**Không.** Khi CSRF đang bật, Spring Security thường tạo một **trang xác nhận logout** cho `GET /logout`; logout có hiệu lực thực sự được thực hiện bằng **POST**. Không dùng một link GET có side effect để “chữa” việc browser cần CSRF token. Nếu tự thiết kế form, tạo form `method="post" action="/logout"` và gửi `_csrf` hợp lệ.

Mẫu HTML với Thymeleaf/Spring MVC (chỉ là **fragment view**, không được cung cấp bởi controller ở ví dụ Java dưới đây):

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_DO_SERVER_CUNG_CAP" />
  <button type="submit">Đăng xuất</button>
</form>
```

Giá trị trong ví dụ HTML là **chỗ biểu diễn dữ liệu được server cung cấp**, không phải token hợp lệ có thể copy chạy. Nếu dùng trang logout xác nhận mặc định của Spring Security, framework xử lý token cho demo; không cần tự copy fragment HTML này.

### URL sau logout và open redirect

`logoutSuccessUrl("/login?logout")` phù hợp khi URL là đường dẫn cố định thuộc ứng dụng. Không lấy tùy tiện `?next=https://example-attacker.test` từ request rồi redirect đến đó mà không xác thực allowlist nội bộ. Đó có thể tạo **open redirect** và dẫn người dùng rời khỏi website an toàn.

Khi dùng `SimpleUrlLogoutSuccessHandler` hoặc custom success handler, xác minh URL được tạo phù hợp context path, reverse proxy và các trusted forwarded headers. Không để client tự quyết định domain redirect của logout nếu không có chính sách ràng buộc.

## 5. API logout: trả HTTP status, không tự động chuyển hướng HTML

Một API client như mobile/backend/SPA thường muốn:

- **`204 No Content`** khi server đã hoàn tất thao tác cleanup theo contract và không có body.
- Hoặc **`200 OK`** với JSON nếu API cần thêm metadata/trạng thái.
- **`401`** nếu thiết kế yêu cầu authentication và credentials không hợp lệ, ở luồng có xác thực trước khi xử lý revoke.
- **`403`** nếu authentication hợp lệ nhưng không đủ quyền/CSRF fail, tùy security contract.
- **`400`/`409`/`503`** khi có lỗi request/trạng thái/phụ thuộc hệ thống theo chính sách riêng, không nên tùy tiện coi mọi lỗi revoke là 204.

Một success handler phù hợp:

```java
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT))
);
```

Đây là **fragment** cần imports `HttpStatus`, `HttpStatusReturningLogoutSuccessHandler`, `HttpSecurity`. Handler trả status thay vì 302, không yêu cầu client theo `Location`. `204 No Content` **không mang response body**, nên không viết JSON song song với status 204. Nếu cần JSON, chọn 200 và một handler tùy chỉnh phù hợp.

Ví dụ response API:

```http
HTTP/1.1 204 No Content
```

**Giới hạn quan trọng:** HTTP status chỉ báo kết quả endpoint xử lý theo contract. Với HTTP Basic, client vẫn có username/password hợp lệ thì request sau vẫn có thể authenticate. Với JWT tự chứa chưa hết hạn, xóa token phía client **không thu hồi bản sao** đã bị đánh cắp. Với token opaque hoặc refresh token lưu server-side, một logout/revoke endpoint có thể thực sự xóa/revoke record, nhưng cần logic riêng — `HttpStatusReturningLogoutSuccessHandler` **không tự revoke token**.

### 5.1. 204 hay 200?

| Mục tiêu | HTTP response thường phù hợp | Cần làm rõ |
| --- | --- | --- |
| Logout hoàn tất, không cần body | **204 No Content** | Không trả JSON hay redirect |
| Logout hoàn tất, cần dữ liệu xác nhận | **200 OK** + JSON | Không nên chứa secrets/token đầy đủ |
| Web browser cần hiển thị trang login/logout notice | **302 Found** + `Location` | Browser chuyển hướng |
| Request chưa được xác thực ở endpoint cần auth trước revoke | **401** | Phải có lớp authentication trước thao tác |
| Thiếu/sai CSRF token ở request logout cookie-based | **403** | Cleanup chưa nhất thiết chạy |
| Revoke downstream thất bại | Status lỗi phù hợp chính sách | Không báo 204 thành công nếu contract đòi revoke thật |

**Idempotency:** phía client nên coi logout như một thao tác có thể lặp lại mà không phá dữ liệu. Với session web, logout lần hai khi không có phiên có thể vẫn hiển thị trang login. Với API, một endpoint “ensure signed out” có thể trả 204 cả khi client đã logout, nhưng điều đó phải là quyết định contract, không phải quy tắc mọi API đều làm vậy.

### 5.2. Vì sao API thường không dùng redirect?

Một REST/HTTP client có thể tự theo `302`, vô tình gọi `GET /login` và nhận HTML thay vì status mong đợi. Một số client gửi cookie hoặc Authorization header khác đi qua redirect theo rule của thư viện, gây rủi ro và lỗi integration. Trả status trực tiếp giúp code phía client dễ xử lý hơn và giữ API response độc lập giao diện.

Không phải cứ có đường dẫn `/api/**` là Spring Security tự chọn status thay redirect; bạn phải cấu hình đúng **logout success handler** hoặc endpoint controller cho API chain.

## 6. CSRF: web logout và API logout đều cần threat model

Logout thay đổi trạng thái xác thực, nên **dùng POST** và bảo vệ khỏi việc site khác tự kích hoạt logout thay người dùng khi browser tự gửi credentials/cookies.

Với web form login/cookie session:

- Để CSRF mặc định hoạt động.
- Browser gửi session cookie và CSRF token do server cấp.
- `GET /logout` (nếu có) chỉ nên hiển thị form xác nhận, không thực hiện side effect.
- `POST /logout` thiếu/sai token thường nhận **403**, không được thay bằng GET logout không kiểm soát.

Với API, có hai mô hình phổ biến:

1. **Client browser có cookie hoặc HTTP Basic cache tự gửi credentials:** cần đánh giá CSRF và có thể dùng CSRF token như web.
2. **Backend/mobile hoặc Bearer token chỉ gửi chủ động trong Authorization header:** có thể áp dụng chính sách CSRF khác **nếu** chứng minh request không thể được cross-site browser tạo kèm credentials theo threat model.

Không viết `csrf.disable()` cho mọi API mà không xét client. Ví dụ runnable ở mục 8 **giữ CSRF trong cả hai chains**, nhưng API dùng `CookieCsrfTokenRepository` và endpoint `GET /api/csrf` để client lấy token cùng cookie phục vụ `POST /api/logout`. Đây là demo đầy đủ hơn việc bỏ CSRF chỉ để thử bằng curl.

### API dùng CookieCsrfTokenRepository trong ví dụ

`CookieCsrfTokenRepository` lưu CSRF token trong cookie (ví dụ `XSRF-TOKEN`), và Spring Security sẽ so khớp với token client gửi qua header như `X-XSRF-TOKEN`. Khi dùng cơ chế masking mặc định trong Spring Security 6, giá trị đưa ra cho client từ `CsrfToken.getToken()` có thể khác với raw cookie value; **dùng token server trả từ endpoint demo** thay vì đọc cookie rồi giả định luôn gửi raw cookie value sẽ đúng ở mọi handler.

Vì client lấy token bằng một request same-origin hợp lệ và gửi lại header cùng cookie, CSRF protection phân biệt với một HTML form cross-site không thể tùy ý đọc token. Khi chuyển sang frontend khác origin, phải cấu hình CORS/origin và credentials cẩn thận, không mở `Access-Control-Allow-Origin: *` cho dữ liệu nhạy cảm.

## 7. Hai SecurityFilterChain độc lập: Web và API

Trong ứng dụng cùng phục vụ browser web và API, nên tách chain cụ thể:

```text
            HTTP request
                 |
                 v
           FilterChainProxy
                 |
        +--------+---------+
        |                  |
   path /api/**          paths khác
        |                  |
        v                  v
   API chain @Order(1)   WEB chain @Order(2)
   - HTTP Basic          - Form login
   - STATELESS           - IF_REQUIRED/session
   - Cookie CSRF         - CSRF web
   - /api/logout         - /logout
   - 204 No Content      - 302 /login?logout
```

Trong Spring Security, **chỉ chain khớp đầu tiên được chọn**. `http.securityMatcher("/api/**")` xác định phạm vi chain, còn `authorizeHttpRequests().requestMatchers(...)` xác định quyền trong chain. Vì vậy API chain phải đi trước WEB fallback, nếu không request API có thể bị web redirect tới `/login`.

Điểm dễ bỏ sót: một application có **hai logout URL khác nhau**, nhưng đều thuộc `LogoutFilter` trong chain tương ứng. Không được tự đặt `logoutSuccessUrl` ở chain web và kỳ vọng `/api/logout` cũng trả 204.

### Xử lý session web khi request logout API mang cookie

Ngay cả khi API chain dùng `SessionCreationPolicy.STATELESS`, `SecurityContextLogoutHandler` vẫn có thể nhìn thấy một `HttpSession` hiện có qua Servlet API khi thực hiện logout. Nếu API không được phép đăng xuất cả phiên web, chủ động đặt:

```java
// Fragment cho API chain để tránh logout API làm invalid web HttpSession.
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .invalidateHttpSession(false)
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT))
);
```

Đây là fragment được dùng trong ví dụ mục 8. **`STATELESS` tự nó không tương đương với “mọi logout handler tuyệt đối không đụng session hiện hữu”.** Khi cần cùng lúc sign-out web và API, cần xác định ranh giới trước, rồi có thể chủ động invalidate session web hoặc revoke tokens ở flow thống nhất khác.

## 8. Ví dụ chạy được: Spring Boot 3.3.5 + Java 17+

Bài thực hành tạo một ứng dụng Servlet có:

- Web form login: `GET /dashboard` cần login; `POST /logout` trả redirect `/login?logout`.
- API HTTP Basic: `GET /api/me` cần Basic credentials; `GET /api/csrf` cấp token dùng cho `POST /api/logout`; `POST /api/logout` trả **204**, không redirect.
- API được cấu hình `STATELESS`; logout API không tự invalidate session web.
- Demo chỉ có một user `lan` / `demo123`, role `USER`. **Chỉ dùng trên localhost để học**, không hard-code account thật.

### 8.1. Cấu trúc project

```text
logout-web-api-demo/
├── pom.xml
└── src/main/java/example/logoutdemo/
    ├── LogoutDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 8.2. pom.xml

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>logout-web-api-demo</artifactId>
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

### 8.3. LogoutDemoApplication.java

```java
package example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 8.4. SecurityConfig.java: hai chains với hai success handlers

```java
package example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

        http.requestCache(cache -> cache.requestCache(new NullRequestCache()));

        // API vẫn giữ CSRF. Token được cấp ở GET /api/csrf
        // và POST /api/logout phải gửi lại header + cookie tương ứng.
        http.csrf(csrf -> csrf
                .csrfTokenRepository(new CookieCsrfTokenRepository())
        );

        http.logout(logout -> logout
                .logoutUrl("/api/logout")
                // API logout KHÔNG tự invalidate web session nếu client
                // vô tình gửi cả JSESSIONID của giao diện web.
                .invalidateHttpSession(false)
                .logoutSuccessHandler(
                        new HttpStatusReturningLogoutSuccessHandler(
                                HttpStatus.NO_CONTENT))
        );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/dashboard").authenticated()
                .anyRequest().authenticated()
        );

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
        );

        http.formLogin(Customizer.withDefaults());

        // Default web logout: POST /logout kèm CSRF hợp lệ,
        // invalidate session + clear SecurityContext, rồi chuyển hướng.
        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
        );

        return http.build();
    }
}
```

**Đọc code theo luồng:**

1. `@Order(1)` và `securityMatcher("/api/**")` buộc request `/api/logout` vào API chain; `@Order(2)` web chain là fallback cho URL khác.
2. API `httpBasic()` chỉ là cơ chế authentication **cho các request đi qua Basic filter**. Vì `LogoutFilter` chạy trước Basic filter, `POST /api/logout` có thể được xử lý mà không dùng Basic credentials; demo này không tuyên bố đã thu hồi hay kiểm chứng credentials ở endpoint logout.
3. `SessionCreationPolicy.STATELESS` không dùng HttpSession để lấy `SecurityContext` của API. `invalidateHttpSession(false)` trong API logout giúp tránh vô tình invalidate phiên web khi client gửi kèm cookie web.
4. `NullRequestCache` tránh lưu saved request và form-login redirect cho API. API logout dùng `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)`, vì vậy không trả trang HTML.
5. `CookieCsrfTokenRepository` cho phép GET nhận CSRF token/cookie, POST gửi token qua header. `CsrfFilter` kiểm tra trước `LogoutFilter`; CSRF fail thường trả 403.
6. Web dùng form login `IF_REQUIRED` và CSRF mặc định. `logoutSuccessUrl("/login?logout")` làm browser chuyển hướng sau khi handlers chạy.
7. Ví dụ không tự đăng ký `LogoutFilter` hai lần bằng `addFilterBefore`. DSL `logout(...)` cấu hình filter sẵn có theo từng chain.
8. Một HTTP request chỉ chạy **một chain khớp đầu tiên**, nên trạng thái API không được copy tùy tiện từ chain web.

### 8.5. DemoController.java

```java
package example.logoutdemo;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home:public";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication auth) {
        return "dashboard:" + auth.getName();
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication auth) {
        return "api:" + auth.getName();
    }

    @GetMapping("/api/csrf")
    public String apiCsrf(CsrfToken token) {
        // Demo: trả CSRF token theo cơ chế của Spring Security 6.
        // Endpoint cùng origin, không mở CORS tùy tiện.
        return token.getToken();
    }
}
```

Không có `@PostMapping("/logout")` hay `@PostMapping("/api/logout")` trong controller. Hai POST đó được **`LogoutFilter` xử lý**, nhờ `logoutUrl` trong đúng security chain.

`GET /api/csrf` là endpoint phục vụ bài lab; trong production, nên chọn thiết kế cấp CSRF token phù hợp, có bảo vệ origin/CORS và không để proxy/CDN cache token theo cách gây lộ cho client khác. Không xem CSRF token là access token hoặc username/password.

### 8.6. Chạy ứng dụng

Từ thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Dùng JDK 17+ và Maven 3.9+; khi khởi động thành công, embedded Tomcat mặc định lắng nghe ở `http://localhost:8080`. HTTP trên localhost chỉ phục vụ demo. **Production bắt buộc HTTPS** để bảo vệ session cookies, CSRF token và Basic credentials.

## 9. Kiểm tra luồng WEB: POST logout → 302 redirect

Dùng cửa sổ browser chưa có session để thử:

1. Mở `http://localhost:8080/dashboard`; chưa login nên browser thường được chuyển tới `/login`.
2. Đăng nhập bằng `lan` / `demo123` trong trang form mặc định của Spring Security.
3. Kiểm tra `/dashboard` trả:

```text
dashboard:lan
```

4. Truy cập `GET /logout`. Trong cấu hình có CSRF, Spring Security thường hiển thị **trang xác nhận logout**. Nhấn nút logout trên trang để gửi POST kèm CSRF token.
5. Browser được chuyển tới `/login?logout`; ở Network panel có thể quan sát response của POST logout là **302**.
6. Sau khi logout, truy cập lại `/dashboard` và kiểm tra browser phải đăng nhập lại. Cần phân biệt cookie session bị invalid với việc browser vẫn giữ một giá trị `JSESSIONID` cũ trong cookie store.

**Không nên dùng `curl -I /logout` để giả lập logout**, vì `-I` gửi HEAD, không phải POST kèm CSRF. Cũng không dùng `GET /logout` làm bài test khẳng định session đã bị hủy.

Ví dụ dạng response:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login?logout
```

Đây là dòng header dự kiến. Có thể có thêm `Set-Cookie`, cache/security headers; `Location` có thể ở dạng đường dẫn tương đối và context path/proxy ảnh hưởng URL.

### Nếu login xong web logout lại bị 403

Kiểm tra yêu cầu POST có CSRF token đúng, session cookie có được gửi, URL form có đúng `/logout` trong web chain, reverse proxy có làm sai origin/scheme không. Không sửa bằng cách disable CSRF toàn ứng dụng hoặc bật GET logout không bảo vệ.

## 10. Kiểm tra luồng API: POST /api/logout → 204

Bài lab dùng `CookieCsrfTokenRepository`, nên trước khi POST phải lấy token và lưu cookie. Những lệnh sau dành cho POSIX shell:

```bash
# Lấy CSRF token do server trả + cookie XSRF-TOKEN cùng origin.
csrf_token="$(curl -s -c api-cookies.txt http://localhost:8080/api/csrf)"

# Gửi POST API logout với cookie và token qua header.
curl -i -b api-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/logout
```

Với cấu hình demo, response mong đợi:

```http
HTTP/1.1 204 No Content
```

Response 204 không có body, không có `Location` redirect; có thể có những header khác (như cookie CSRF đã bị xóa hoặc đổi) tùy logout handlers. Client không nên chờ JSON body khi status là 204.

**Vì sao lệnh không cần `--user`?** `LogoutFilter` xử lý URL logout **trước** Basic authentication filter. 204 trong demo xác nhận POST với CSRF token hợp lệ được chấp nhận bởi logout flow, **không xác nhận** username/password từ `Authorization` đã được kiểm tra hay token thật sự bị thu hồi. Đây là chủ đích bài học để tránh dạy sai rằng mọi lời gọi `/api/logout` tự động revoke một credentials stateless.

Thử CSRF thiếu hoặc không hợp lệ:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8080/api/logout
```

Kỳ vọng **403** với cấu hình CSRF của demo. Cleanup logout có thể chưa được thực hiện vì `CsrfFilter` từ chối trước `LogoutFilter`.

Sau khi logout API trả 204, vẫn có thể gọi API bằng HTTP Basic credentials đúng:

```bash
curl -s -u lan:demo123 http://localhost:8080/api/me
```

Kết quả dự kiến:

```text
api:lan
```

**Đây không phải lỗi trong demo.** Username/password vẫn là credentials hợp lệ; HTTP Basic không có một session access token để `LogoutFilter` hủy. Nếu API cần một khả năng logout/revoke thật, phải thay đổi cơ chế xác thực hoặc có chính sách khóa/thu hồi credentials phù hợp. Không ghi tài liệu nói 204 “đã vô hiệu Basic password”.

### Bảng kết quả thực hành

| Thử nghiệm | Kết quả dự kiến | Ý nghĩa |
| --- | --- | --- |
| Chưa login, mở `/dashboard` | 302 tới login | Web yêu cầu form login |
| Login web bằng `lan` | 302 tới saved URL hoặc target | Tạo session authentication |
| `GET /dashboard` đã login | 200 `dashboard:lan` | Session auth hợp lệ |
| `GET /logout` | Trang xác nhận logout | Chưa hủy session chỉ vì GET |
| `POST /logout` + cookie/CSRF | 302 tới `/login?logout` | Cleanup web và redirect |
| `GET /dashboard` sau web logout | 302 tới login | Phiên web đã mất authentication |
| `POST /api/logout` thiếu CSRF | 403 | CsrfFilter từ chối |
| `POST /api/logout` đúng CSRF/cookie | 204, không body/redirect | API logout response thành công |
| `GET /api/me` không Basic header | 401 | Stateless API cần credentials cho route này |
| `GET /api/me` với Basic đúng sau 204 | 200 `api:lan` | 204 không revoke password Basic |

## 11. Logout cho session, remember-me, JWT và opaque token khác nhau

### 11.1. Web session

Web session là state server-side, nên một `SecurityContextLogoutHandler` có thể invalidate `HttpSession`, khiến session ID hiện tại không còn truy cập được `SecurityContext` cũ. Điều này thường là **logout thật** với authentication dựa trên phiên.

Một số ứng dụng còn dùng Spring Session/Redis session store, thiết bị khác hoặc SSO session. Logout session hiện tại **không mặc nhiên hủy** tất cả các phiên trên thiết bị khác hoặc một phiên ở Identity Provider. Nếu cần global logout, hãy bổ sung flow tương ứng.

### 11.2. Remember-me cookie

Nếu đã bật remember-me, cookie nhớ đăng nhập có thể khôi phục người dùng sau khi session bị hủy. Vì vậy logout flow cần tích hợp `RememberMeServices` để xóa cookie và, với persistent remember-me, dọn token record. Spring Security có thể thêm remember-me logout handler theo cấu hình.

Tuy nhiên việc xóa cookie ở browser **không bảo đảm thu hồi bản sao cookie đã bị đánh cắp** nếu là signed token-based remember-me còn hạn. Các yêu cầu thu hồi thiết bị riêng lẻ cần thiết kế token store/revocation phù hợp.

### 11.3. Bearer JWT

JWT tự chứa thường còn hợp lệ cho tới khi hết hạn (nếu chữ ký, issuer, audience và các điều kiện khác hợp lệ). `SecurityContextLogoutHandler` không thể tự “xóa” một JWT đã phát hành khỏi thế giới. Client có thể xóa token cục bộ; nếu cần thu hồi tức thời phải có denylist/revocation, short-lived access token và refresh token rotation/revocation, hoặc policy tương ứng của IdP.

### 11.4. Opaque/refresh token với server-side store

Nếu server kiểm soát token record, có thể xây logout endpoint **xác thực token trước**, tìm chính xác token hoặc family được thu hồi, cập nhật token store một cách nhất quán, rồi trả 204/200 nếu thành công. Cần định nghĩa idempotency và lỗi từ hệ thống token store.

Một fragment mô tả thiết kế:

```text
POST /api/logout + Bearer access/refresh token
    -> authentication filter kiểm tra token
    -> controller/service dùng principal hoặc token ID đáng tin cậy
    -> revoke server-side token/refresh-token family (nếu có)
    -> clear context/credentials theo chính sách
    -> 204 No Content khi contract đã hoàn tất
```

**Đoạn trên là kiến trúc minh họa, không phải cơ chế tự phát sinh khi gọi `http.logout()`.** Trong một API bearer stateless, nếu muốn controller nhận `Authentication` đã kiểm chứng trước khi revoke, có thể dùng controller/service endpoint bảo vệ qua authentication/authorization chain thay vì dùng LogoutFilter xử lý trước authentication filters. Thiết kế thực tế còn phụ thuộc authorization server, token type và khả năng thu hồi của provider.

## 12. Redirect handler và status handler: cách tùy chỉnh có kiểm soát

### 12.1. Dùng SimpleUrlLogoutSuccessHandler

Trong trường hợp cần logic chọn URL sau logout ở web, Spring Security có `SimpleUrlLogoutSuccessHandler`. Tuy nhiên với URL cố định, cú pháp `logoutSuccessUrl("/login?logout")` thường ngắn gọn và ít lỗi hơn.

```java
// Fragment thay cho logoutSuccessUrl khi muốn tạo handler rõ ràng.
SimpleUrlLogoutSuccessHandler handler = new SimpleUrlLogoutSuccessHandler();
handler.setDefaultTargetUrl("/login?logout");
http.logout(logout -> logout.logoutSuccessHandler(handler));
```

Fragment cần import `org.springframework.security.web.authentication.logout.SimpleUrlLogoutSuccessHandler`; không đặt đồng thời nhiều success handlers rồi kỳ vọng tất cả đều chạy. Nếu code tự chọn URL theo request, phải chống open redirect và tránh lộ thông tin nhạy cảm trong query.

### 12.2. Trả JSON 200 cho API

Nếu client cần body, có thể dùng một custom handler:

```java
// Fragment thay thế cho HttpStatusReturningLogoutSuccessHandler.
// Dùng khi contract API yêu cầu JSON body.
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .invalidateHttpSession(false)
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"status\":\"signed_out\"}");
        })
);
```

Đây là fragment của một **lựa chọn thay thế** trong API chain. Với response 200, JSON body có thể giúp một số clients. Nhưng không trả credential, stack trace hay token record vào response. Nếu thật sự cần **204**, dùng handler trả status mà không body như ví dụ mục 8.

### 12.3. Cookie cleanup không đồng nghĩa với cookie invalidation từ server

Có thể cấu hình:

```java
// Fragment: bổ sung khi ứng dụng biết chính xác cookie name/path.
http.logout(logout -> logout
        .deleteCookies("JSESSIONID", "remember-me")
        .logoutSuccessUrl("/login?logout"));
```

Đây là ví dụ để hiểu `CookieClearingLogoutHandler`, không phải yêu cầu phải xóa mọi cookie bằng tên trên tất cả môi trường. Một cookie chỉ bị browser xóa nếu response `Set-Cookie` có domain/path và các thuộc tính tương thích. Hủy `HttpSession` phía server mới là bước làm phiên cũ mất hiệu lực; browser còn giữ cookie ID không làm session server-side sống lại.

Với remember-me, ưu tiên cấu hình/integrate `RememberMeServices` đúng cách để logout handler biết cookie hoặc token repository tương ứng, thay vì chỉ thêm `deleteCookies` mà bỏ qua server-side persistent tokens.

## 13. Quy tắc bảo mật cho logout

- **CSRF:** logout là state-changing action. Browser dùng cookie cần token CSRF hợp lệ; đừng biến `GET /logout` thành hành động logout không có bảo vệ.
- **HTTPS:** bảo vệ session cookies, Basic credentials, CSRF token và mọi bearer tokens khỏi bị đánh cắp trên đường truyền. Dùng `Secure`/`HttpOnly`/`SameSite` theo threat model.
- **Cache:** sau logout, trang nhạy cảm không nên được lưu cache không kiểm soát trên browser/proxy. Kiểm tra `Cache-Control` và không để thông tin nhạy cảm hiển thị từ history/back cache theo chính sách.
- **Idempotency:** xác định rõ logout lặp lại phải phản hồi thế nào. Đừng vô tình gây tác dụng phụ tới tài khoản khác từ một logout request không còn authentication.
- **Không rò rỉ:** không đưa session ID, Authorization header, access/refresh token hoặc password vào URL `Location` hay logs.
- **State per device:** logout web hiện tại khác logout all devices và khác thu hồi token/SSO session; đặt tên API rõ ràng.
- **SSO/OIDC:** local logout không mặc nhiên đăng xuất khỏi Identity Provider; back-channel/front-channel logout hoặc OIDC RP-initiated logout là các flow khác, cần kiểm tra provider.
- **SecurityContext và browser:** `SecurityContextHolder` là phạm vi request; hủy session và context không làm browser tự quên Basic password cache.
- **Chống open redirect:** chỉ redirect tới URL an toàn/được kiểm soát, không tin tham số đích tùy ý.
- **Status trung thực:** chỉ trả “revoked” nếu token thật đã được thu hồi theo hợp đồng; `HttpStatusReturningLogoutSuccessHandler` không tự làm việc đó.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| Web POST logout trả 403 | Thiếu/sai CSRF token hoặc cookie phiên không khớp | `CsrfFilter`, form action, hidden CSRF, SameSite/cookie |
| GET /logout không hủy phiên | Với CSRF enabled, GET chỉ hiện trang xác nhận | Dùng POST đúng token |
| Web logout trả 204 thay vì redirect | Request đi nhầm API chain hoặc handler API được đăng ký cho web | `securityMatcher`, `@Order`, logout matcher |
| API logout trả 302 tới HTML login | Request vào web chain hoặc dùng default redirect success handler | API chain match, `HttpStatusReturningLogoutSuccessHandler` |
| API logout đúng CSRF nhưng user vẫn gọi được API | Basic credentials hoặc JWT còn hợp lệ | Phân biệt status cleanup và thu hồi credentials |
| API request POST /api/logout thiếu auth vẫn 204 | `LogoutFilter` xử lý trước BasicAuthenticationFilter | Nếu cần token revocation authenticated, dùng flow/service được bảo vệ |
| API logout làm web session cũng chết | Logout handler thấy/invalidate `HttpSession` có sẵn | Xem `invalidateHttpSession(false)` cho API chain, hoặc thống nhất policy |
| Web logout xong trở lại dashboard vẫn 200 | Session/context chưa bị xóa, client gửi cookie/token khác, remember-me auto-login | Debug session invalidation, SecurityContextRepository, remember-me |
| Có `Set-Cookie` nhưng browser vẫn giữ cookie | Domain/path/SameSite/Secure không phù hợp | Inspect cookie attributes, context path, proxy |
| Có 204 nhưng client vẫn theo redirect | Proxy/API gateway/custom handler hoặc frontend hiểu status sai | Network traces, endpoint handler, gateway |
| Đổi logout URL rồi GET/POST 404 | URL nằm ngoài securityMatcher hoặc trùng controller matcher | Exact chain, logoutUrl, request method |
| JWT logout chỉ xóa context, token bị đánh cắp vẫn dùng được | JWT không có denylist/revocation | Thiết kế revoke/rotation/TTL |
| Logout liên tục bị 401 | Endpoint tự yêu cầu authentication sai tầng, credential thiếu, hoặc gateway chặn trước app | Security chain order, gateway policy, endpoint contract |

### Quy trình debug có hệ thống

1. Xác nhận **HTTP method**, path, cookies, CSRF header và Authorization scheme, nhưng không log giá trị secrets.
2. Xác nhận chain được chọn qua `FilterChainProxy`, matcher `/api/**` hoặc web fallback, và `LogoutFilter` trong chain đó.
3. Kiểm tra **CsrfFilter** đã cho request qua chưa; nếu 403 trước logout, cleanup chưa chạy.
4. Xác nhận `LogoutHandler` có thực hiện invalidate session/clear context/cookie hoặc token revocation theo yêu cầu không.
5. Xác nhận `LogoutSuccessHandler` thực sự được gọi: web redirect hay API status.
6. Xem `Location`, `Set-Cookie`, response status/body, không suy luận từ trang hiển thị sau redirect.
7. Gửi một request **mới sau logout** đến tài nguyên bảo vệ: web session không còn, API Basic vẫn có thể thành công khi credentials còn đúng.
8. Nếu có remember-me, JWT, SSO hoặc token store, kiểm tra riêng cơ chế revocation, không chỉ logout local.

Development có thể bật log an toàn:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật logging raw Authorization, password, CSRF token, session IDs hoặc refresh tokens ở production.

## 15. Câu hỏi tự ôn

1. **LogoutHandler khác LogoutSuccessHandler?** Handler đầu dọn security state; handler sau quyết định response HTTP.
2. **Vì sao web thường trả 302 sau logout?** Browser cần được điều hướng tới trang login/trang công khai.
3. **Vì sao API thường trả 204?** Client cần status machine-readable, không cần HTML redirect hay body.
4. **GET /logout mặc định có hủy session khi CSRF bật?** Thường không, nó hiển thị trang xác nhận; POST kèm CSRF mới thực hiện logout.
5. **CSRF fail dẫn đến gì?** Có thể 403 trước khi LogoutFilter chạy.
6. **Nếu API logout trả 204, Basic password có hết hiệu lực?** Không. Basic credentials vẫn hợp lệ nếu server không đổi/thu hồi chúng.
7. **LogoutFilter chạy trước hay sau BasicAuthenticationFilter?** Thường **trước**, nên logout URL không nhất thiết có Basic-authenticated principal.
8. **`STATELESS` có tự ngăn API logout handler invalidate một HttpSession web hiện có?** Không; phải xét/logout handler policy riêng.
9. **Vì sao dùng `invalidateHttpSession(false)` trong API chain demo?** Tránh vô tình hủy web session khi nhận cookie web, không tạo cơ chế revoke token.
10. **`204 No Content` có thể trả JSON body không?** Không; nếu cần body hãy chọn 200/response khác.
11. **Logout có tự thu hồi JWT chưa hết hạn?** Không, cần revocation/denylist hoặc thiết kế token lifecycle khác.
12. **Nếu web logout thành công nhưng trang nhạy cảm vẫn hiện qua back button?** Xem browser cache/control, đồng thời test network request thật để biết server còn cho truy cập không.
13. **Logout một thiết bị và logout tất cả thiết bị có giống nhau không?** Không; session/token store và logout contract phải định nghĩa riêng.
14. **Open redirect sau logout là gì?** Cho client quyết định URL redirect đến domain ngoài mà không kiểm soát.
15. **Khi nào dùng controller API thay LogoutFilter?** Khi cần xác thực bearer token trước, kiểm tra quyền và revoke theo token ID trong service riêng.

## 16. Checklist triển khai

- [ ] Tách web và API theo `SecurityFilterChain` khi hai nhóm có logout response khác nhau.
- [ ] Web: dùng POST logout cùng CSRF, dọn session/context, redirect tới URL cố định an toàn.
- [ ] API: xác định status thành công (`204` không body hoặc `200` có JSON), tránh HTML redirect.
- [ ] Phân biệt `LogoutHandler` xử lý cleanup với `LogoutSuccessHandler` trả HTTP response.
- [ ] Không dựa vào `authorizeHttpRequests().authenticated()` để mặc định chặn URL đã được `LogoutFilter` xử lý trước.
- [ ] Nếu API logout không được làm mất web session, đặt `invalidateHttpSession(false)` và kiểm tra handlers khác.
- [ ] Áp dụng CSRF theo loại client/credentials; không tắt toàn cục chỉ vì API dùng Basic hoặc STATELESS.
- [ ] Nếu logout được quảng bá là “thu hồi token”, thực sự triển khai revocation và báo lỗi khi revoke thất bại.
- [ ] Dùng HTTPS và cookie security; tránh open redirect, URL chứa token, logging secrets.
- [ ] Với remember-me, kiểm tra logout handler xóa cookie/token repository phù hợp.
- [ ] Với JWT/SSO, xác định logout local khác global logout hoặc token revocation.
- [ ] Test cả request logout, redirect/status, và **request bảo vệ mới sau logout**, không chỉ nhìn 302/204.
- [ ] Kiểm thử web/API bằng client thực tế; bảo đảm CSRF cookie và token được gửi đúng.

**Tổng kết:** trong Spring Security Servlet, **`LogoutFilter`** nhận yêu cầu đăng xuất, các **`LogoutHandler`** làm sạch state, còn **`LogoutSuccessHandler`** quyết định phản hồi. **Web** thường dùng redirect `302 /login?logout`; **API** thường trả `204 No Content` hoặc status/JSON theo contract. Chính sách session, CSRF và khả năng thu hồi Basic/JWT/remember-me phải được thiết kế độc lập — **status thành công không phải phép chứng minh mọi credentials đã bị vô hiệu hóa**.