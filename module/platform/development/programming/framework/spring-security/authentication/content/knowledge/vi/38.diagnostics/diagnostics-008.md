# CSRF bị từ chối trước khi thông tin đăng nhập tới provider

## 1. Hiện tượng và kết luận cần kiểm chứng

Một người dùng nhập đúng username/password vào form đăng nhập nhưng nhận **HTTP 403 Forbidden** khi gửi `POST /login`. Trong khi debug, breakpoint tại `UserDetailsService.loadUserByUsername`, `PasswordEncoder.matches` hoặc `AuthenticationProvider.authenticate` không chạy. Thay password đúng thành password sai vẫn nhận cùng kết quả.

Nếu request bị từ chối bởi **`CsrfFilter`**, đó là hành vi đúng của Spring Security: request **dừng trước `UsernamePasswordAuthenticationFilter`**, vì vậy chưa có bước tạo `UsernamePasswordAuthenticationToken` để chuyển tới `AuthenticationManager` và provider.

Nhưng **không phải mọi HTTP 403 đều là lỗi CSRF**. Một rule authorization, custom filter, access-denied handler hay gateway cũng có thể trả 403. Bài học này hướng dẫn chứng minh chính xác nguyên nhân bằng filter order, request/session trace và test đối chứng có bộ đếm lần gọi provider.

### Mục tiêu

1. Giải thích vì sao CSRF được bảo vệ cả trên **POST đăng nhập**.
2. Hiểu thứ tự `CsrfFilter → UsernamePasswordAuthenticationFilter → AuthenticationManager/Provider`.
3. Phân biệt `MissingCsrfTokenException` và `InvalidCsrfTokenException`, 403 do CSRF với 401/302/403 từ các tầng khác.
4. Chẩn đoán `_csrf` form parameter, session cookie, token repository, request handler và masked-token semantics.
5. Xử lý form HTML, Thymeleaf, SPA, fetch, reverse proxy và nhiều SecurityFilterChain.
6. Viết JUnit 5/MockMvc tests trong Spring Boot 3.x / Spring Security 6.x / Java 17+ để chứng minh **provider được gọi 0 lần** khi CSRF thất bại.
7. Không tắt CSRF trên toàn ứng dụng như một cách chữa lỗi.
8. Đưa ra checklist điều tra production mà không làm lộ mật khẩu, token hoặc session cookie.

**Cách nghĩ chính:** CSRF là một bước bảo vệ **trước authentication**, không phải một loại kết quả xác minh mật khẩu.

## 2. Vì sao POST /login phải có CSRF token?

CSRF (Cross-Site Request Forgery) xảy ra khi một trang do attacker điều khiển khiến browser của người dùng tự gửi request tới trang mục tiêu kèm các credentials browser tự gắn vào, đặc biệt là cookie.

Một request đăng nhập cũng **thay đổi trạng thái phiên**. Nếu không có CSRF protection, một trang độc hại có thể cố đăng nhập browser nạn nhân vào một account do attacker kiểm soát (login CSRF), tạo sự nhầm lẫn giữa chủ account và người đang dùng trình duyệt, từ đó dẫn tới các hệ quả nghiệp vụ không mong muốn.

Mô hình bảo vệ:

~~~text
Browser của nạn nhân
    |
    +--> website ngoài ý muốn cố gửi POST /login
                |
                v
          Spring Security
                |
                +--> CsrfFilter
                      |
                      +-- có CSRF proof hợp lệ? KHÔNG
                      |       → AccessDeniedHandler, thường 403
                      |
                      +-- CÓ
                              → filter xử lý credentials mới chạy
~~~

CSRF proof phải đến từ một phần request mà website ngoài ý muốn **không thể tự gửi đúng chỉ nhờ browser tự thêm cookie**, ví dụ hidden form input hoặc header được lấy từ nguồn same-origin đáng tin.

- **CSRF token không phải access token.**
- **CSRF token không xác minh password.**
- **CSRF token hợp lệ chưa có nghĩa người dùng đã đăng nhập.**
- **`permitAll("/login")` chỉ liên quan tới authorization, không tắt CsrfFilter.**

Đây là lý do một endpoint public dành cho người chưa đăng nhập vẫn có thể yêu cầu CSRF token khi xử lý POST.

## 3. Thứ tự filter quyết định nơi request dừng

Trong Servlet Spring Security 6.x, `FilterChainProxy` chọn một `SecurityFilterChain` phù hợp. Một thứ tự điển hình cho form login là:

~~~text
POST /login
   |
   v
DelegatingFilterProxy
   |
   v
FilterChainProxy chọn SecurityFilterChain
   |
   v
SecurityContextHolderFilter và filter hạ tầng
   |
   v
CsrfFilter
   |
   +-- POST phải được kiểm tra CSRF
   +-- load expected token từ CsrfTokenRepository
   +-- resolve actual token qua CsrfTokenRequestHandler
   +-- so khớp
       |
       +-- MISSING hoặc INVALID
       |      → CsrfException
       |      → AccessDeniedHandler
       |      → thường HTTP 403
       |      → DỪNG, không gọi chain.doFilter tiếp
       |
       +-- VALID
              |
              v
       UsernamePasswordAuthenticationFilter
              |
              +-- đọc username/password từ request
              +-- AuthenticationManager.authenticate(...)
              +-- AuthenticationProvider.authenticate(...)
              +-- UserDetailsService / PasswordEncoder
              +-- authentication success/failure handling
              |
              v
       các filter và authorization còn lại
~~~

Spring Security mô tả thứ tự khái niệm **exploit protection trước authentication, authentication trước authorization**. `CsrfFilter` là một chốt sớm trong luồng.

### Hệ quả khi đặt breakpoint

Với CSRF không hợp lệ:
- `AuthenticationProvider.authenticate()` **không được gọi**.
- `PasswordEncoder.matches()` **không chạy**.
- `AuthenticationFailureHandler` dành cho bad credentials **không nhất thiết chạy**, vì provider chưa trả `BadCredentialsException`.
- `AuthenticationSuccessHandler` không chạy.
- Không có authentication mới được tạo từ POST đó.

Vì vậy, nếu chỉ thêm log trong provider, bạn có thể không thấy gì rồi kết luận nhầm rằng `AuthenticationManager` bị cấu hình sai. Đầu tiên phải tìm **filter đã kết thúc request**.

**Giới hạn:** Ứng dụng có thể có nhiều chain, custom servlet filters và authentication mechanisms. Không suy đoán thứ tự nếu `/login` rơi vào chain khác; kiểm tra đúng chain tại runtime.

## 4. Phân biệt response: 403, 302, 401 và 404

| Dấu hiệu | Nguồn thường gặp | Provider được gọi? | Hướng điều tra |
|---|---|---|---|
| `POST /login` → 403, token thiếu | `CsrfFilter` | Không | Form/cookie/CSRF |
| `POST /login` → 403, token sai | `CsrfFilter` | Không | Session/repository/handler |
| `POST /login` → 302 `/login?error` | Default authentication failure | Thường có | Password, UDS, account flags |
| `POST /login` → 302 `/` hoặc saved URL | Authentication success | Thường có | Session và redirect |
| `GET /private` → 302 `/login` | Form login entry point | Không liên quan trực tiếp | Chưa authenticated |
| API `401` với `WWW-Authenticate` | Basic/Bearer entry point | Tùy cơ chế | Credentials/token |
| `403` sau authenticated request | Authorization/CSRF/custom rule | Tùy tình huống | Exception/filter |
| `POST /login` → 404 | Sai login processing path hoặc chain | Không | URL/matcher |
| Browser báo CORS failure | CORS/preflight/network | Chưa chắc request đã tới provider | CORS/credentials |

Các status/redirect trên là **mặc định thường gặp**, không bất biến. Custom `AccessDeniedHandler`, `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, reverse proxy hoặc exception mapper có thể thay đổi status/body.

**Quy tắc điều tra:** không coi “response là 403” đủ kết luận CSRF; cần exception/handler hoặc test đối chứng xác nhận.

## 5. CsrfFilter kiểm tra điều gì?

Spring Security servlet mặc định bật CSRF cho các **unsafe HTTP methods** như `POST`, `PUT`, `PATCH`, `DELETE`. Thường bỏ qua `GET`, `HEAD`, `OPTIONS`, `TRACE` theo matcher mặc định.

~~~text
GET /login
  → trang form có thể tạo/render CSRF token
  → không cần trình CSRF proof như POST

POST /login
  → có yêu cầu CSRF protection
  → actual token phải khớp expected token
  → nếu sai/thiếu, request bị chặn trước provider
~~~

Không biến hành động thay đổi trạng thái thành GET chỉ để tránh CSRF. Login submit, logout, đổi password, xác minh liên hệ và các thao tác ghi phải dùng HTTP method phù hợp.

### 5.1. Expected token so với actual token

- **Expected token** lấy từ `CsrfTokenRepository`. Repository mặc định của Servlet thường là `HttpSessionCsrfTokenRepository`, lưu token gắn với `HttpSession`.
- **Actual token** đến từ HTTP request, thường là form field `_csrf` hoặc header CSRF.
- **`CsrfTokenRequestHandler`** chịu trách nhiệm đưa token ra request attribute và resolve token đã gửi từ header/parameter.

Nếu request không có expected token cần thiết, có thể gặp `MissingCsrfTokenException`. Khi expected token tồn tại nhưng submitted token không khớp, có thể gặp `InvalidCsrfTokenException`. Cả hai thuộc `CsrfException`, mở rộng `AccessDeniedException`.

**Không kết luận chỉ bằng tên exception rằng browser chưa hề gửi trường token**. Request có thể mang trường đúng tên nhưng token thuộc session khác hoặc không đúng cách encoding mà handler mong đợi.

### 5.2. Session là một phần của việc so khớp

~~~text
GET /login
    Cookie: JSESSIONID=A
    → hidden _csrf được render theo session A

POST /login
    Cookie: JSESSIONID=B hoặc không có session A
    → expected token khác/missing
    → CSRF rejection trước authentication
~~~

Trường hợp này xuất hiện khi:
- cookie bị browser bỏ do `SameSite`, `Secure`, `Domain`, `Path`;
- user để trang login mở quá lâu, session hết hạn;
- cookie/session thay đổi vì logout/login khác tab;
- load balancer chuyển POST sang node không chia sẻ session;
- HTML form cũ bị cache và tái sử dụng cho session khác.

Chỉ ghi trạng thái session/cookie **có hay không** khi điều tra; đừng đưa giá trị `JSESSIONID` hay `_csrf` thật vào log.

## 6. Form HTML và Thymeleaf: nguồn cấp CSRF token

Form login tiêu chuẩn thường gửi:

~~~http
POST /login HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_VALUE

username=alice&password=...&_csrf=MASKED_TOKEN
~~~

Đoạn trên chỉ minh họa **tên trường**, không phải credential hay token có thể dùng thật.

Ví dụ Thymeleaf:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="utf-8"><title>Đăng nhập</title></head>
<body>
  <form th:action="@{/login}" method="post">
    <label for="username">Tên đăng nhập</label>
    <input id="username" name="username" autocomplete="username">

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password">

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

Khi view engine tích hợp đúng với `CsrfRequestDataValueProcessor`, Thymeleaf có thể **tự sinh hidden CSRF input** cho POST form. Nếu dùng template engine khác mà nó không hỗ trợ cơ chế này, cần render field rõ ràng từ server:

~~~html
<!-- Chỉ thêm thủ công khi view layer không tự tạo CSRF input -->
<input type="hidden" th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Dấu `th:` là cú pháp Thymeleaf; cần dùng trong template Thymeleaf thực sự. **Không chèn hai input cùng tên `_csrf`** nếu view layer đã tự thêm một input. Kiểm tra DOM đã render trên trình duyệt, không chỉ nhìn template source.

### `permitAll` không phải bypass CSRF

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
~~~

Request anonymous được phép truy cập endpoint login theo authorization. POST login vẫn phải qua `CsrfFilter`. Thêm `permitAll` lần nữa không sửa được CSRF token mismatch.

## 7. Cách chẩn đoán theo thứ tự ưu tiên

### Bước 1 — Xác minh request thật, không dựa vào lời mô tả UI

Trong DevTools → Network, ghi nhận:
- HTTP method, path, status và redirect chain;
- Content-Type là `application/x-www-form-urlencoded`, `multipart/form-data` hay JSON;
- token parameter hoặc header có **hiện diện** không (không copy giá trị);
- session cookie có được gửi hay không (không copy giá trị);
- yêu cầu có đi qua redirect khác hostname/scheme/port không;
- `/login` có đúng là URL do filter đăng nhập xử lý không.

Không upload HAR chứa credential/session/CSRF/bearer token lên công cụ ngoài hệ thống.

### Bước 2 — Xác định SecurityFilterChain đang match

Mỗi `SecurityFilterChain` có matcher và thứ tự riêng. Nếu chain `@Order(1)` xử lý `/api/**`, `POST /api/login` có thể **không** đi qua chain chứa `formLogin()`.

Bật DEBUG trong môi trường test hoặc thời gian ngắn khi điều tra:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Quan sát log startup `DefaultSecurityFilterChain`: có `CsrfFilter`, `UsernamePasswordAuthenticationFilter`, `AuthorizationFilter` không? Nếu không có login filter trong chain, đừng debug provider của chain khác.

TRACE có thể cung cấp thêm dấu vết nhưng phải rà soát khả năng lộ headers/parameters và chỉ bật ngắn hạn, có kiểm soát.

### Bước 3 — Xác nhận lỗi phát sinh tại CsrfFilter

Dấu hiệu mạnh:
1. `POST /login` thiếu/sai token trả 403.
2. `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException` xuất hiện tại security layer.
3. Với **cùng URL/method** và CSRF hợp lệ, provider mới được gọi.
4. Đặt counter/breakpoint ngay đầu `AuthenticationProvider.authenticate`: bằng **0** cho request CSRF fail.

Đừng chỉ dùng `AuthenticationFailureHandler` để bắt các lỗi này: handler đó thường chạy sau khi provider đã thử xác thực, còn CSRF rejection xảy ra trước.

### Bước 4 — Tìm nguyên nhân token sai

Kiểm tra đủ:
- GET login có tạo/render token không?
- Form hidden field hay header có đúng tên không?
- GET và POST có cùng session/context không?
- Frontend có gửi cookie đúng policy không?
- Token bị clear sau login/logout, hoặc form cũ tồn tại lâu?
- `CsrfTokenRequestHandler` xử lý raw/masked token đúng không?
- Có `CookieCsrfTokenRepository` riêng cho SPA không?
- Proxy/cache/CDN có thay hostname/cookie hoặc cache HTML login không?

### Bước 5 — Khi CSRF PASS mới xem credentials/provider

Sau khi vượt `CsrfFilter`, kiểm tra:
- URL trùng `loginProcessingUrl`.
- Form dùng đúng `username` và `password` hoặc custom parameter names.
- `AuthenticationManager` và provider hỗ trợ `UsernamePasswordAuthenticationToken`.
- `UserDetailsService` nạp đúng account.
- `PasswordEncoder.matches` xử lý đúng hash đã lưu.
- Account có bị locked/disabled/expired không.
- Success/failure handler redirect và tạo session đúng không.

**Chẩn đoán đúng thứ tự sẽ tránh sửa PasswordEncoder trong khi password chưa từng được chuyển tới đó.**

## 8. Ma trận triệu chứng → nguyên nhân → hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| GET form OK, POST login 403 | Form thiếu `_csrf` | Render và gửi token |
| HTML tĩnh không có hidden field | View không tích hợp CSRF | Tạo input từ server |
| Token có mặt, POST vẫn 403 | Session lệch hoặc handler đọc sai | Kiểm tra repository/handler/cookie |
| Đăng nhập từ tab cũ sau logout | Token bị clear và form cũ | Reload form, lấy token mới |
| SPA POST đầu sau login 403 | Token cũ đã clear, deferred loading | Bootstrap token mới |
| SPA đọc cookie raw, server mong XOR masked | Request handler không tương thích | Dùng cấu hình SPA chính thức |
| Browser fetch không có session cookie | `credentials`, `SameSite`, CORS hoặc cookie attributes | Sửa cookie/credentials |
| Đổi tên header CSRF | Frontend và backend khác contract | Dựa `CsrfToken.getHeaderName()` |
| Form POST JSON vào default formLogin | Filter mặc định đọc form parameters | Dùng form-urlencoded hoặc auth filter JSON riêng |
| `/api/login` 403 còn `/login` OK | Different SecurityFilterChain | Kiểm tra matcher/order |
| CSRF fail trên một replica | Session store không phân tán | Spring Session/sticky routing phù hợp |
| HTTP→HTTPS redirect làm mất cookie | Secure/domain/scheme chưa đúng | Sửa public URL/trusted proxy |
| MockMvc POST 403 | Test thiếu `.with(csrf())` | Thêm CSRF proof trong positive case |
| `@WithMockUser` nhưng POST vẫn 403 | Mock identity không cung cấp CSRF | Thêm `csrf()` riêng |
| POST `/login` 302 error | Provider được gọi, credentials sai | Chẩn đoán authentication |
| GET private 403 | Rule thiếu authority hoặc custom policy | Chẩn đoán authorization |
| Browser báo CORS preflight lỗi | OPTIONS bị chặn/cors config | Chẩn đoán CORS, không mặc định CSRF |

Một request có thể có nhiều lỗi nhưng **lỗi xuất hiện trước thường che lỗi phía sau**. Sau khi CSRF được sửa, ứng dụng có thể bắt đầu trả `/login?error` vì password thực sự không đúng.

## 9. Spring Security 6.x: deferred loading và XOR token

Hai thay đổi quan trọng khi nâng cấp Spring Security 5 → 6:

### 9.1. Deferred CSRF loading

CSRF token có thể chỉ được tạo/load khi thực sự cần, chẳng hạn khi:
- POST cần validation;
- server render form chứa `_csrf`;
- SPA chủ động bootstrap token.

Một trang GET không sử dụng CSRF token không nhất thiết phát hành session/cookie mới. Do đó đừng suy rằng token luôn sẵn có sau mọi GET.

### 9.2. Masked vs raw token để chống BREACH

`XorCsrfTokenRequestAttributeHandler` mặc định hỗ trợ BREACH protection: hidden token render có thể **khác chuỗi** giữa hai lần render, trong khi repository vẫn giữ cùng raw token.

~~~text
CsrfTokenRepository:
    rawToken = SECRET

HTML form render lần 1:
    _csrf = MASKED_VALUE_1

HTML form render lần 2:
    _csrf = MASKED_VALUE_2

POST:
    XorCsrfTokenRequestAttributeHandler
    → decode value đã mask
    → compare raw token trong repository
~~~

Không dùng so sánh `String.equals(maskedFormValue, rawRepositoryValue)` để kết luận lỗi. Đường resolve do `CsrfTokenRequestHandler` thực hiện.

### 9.3. CookieCsrfTokenRepository cho SPA

SPA hay dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript có thể đọc CSRF cookie, thường mang tên `XSRF-TOKEN`, và gửi raw token qua header `X-XSRF-TOKEN`.

Nhưng chỉ chuyển repository **chưa đủ** nếu handler đang mong masked value. Spring Security 6.5 có mẫu `SpaCsrfTokenRequestHandler`:
- sử dụng handler phù hợp khi đọc raw token từ header;
- giữ XOR handler khi hiển thị token trong HTML form;
- chủ động làm deferred token được load để trả cookie mới khi cần.

Việc bỏ `HttpOnly` chỉ dành cho **cookie CSRF** khi JS thật sự cần đọc. **Không** bỏ `HttpOnly` trên cookie session authentication chỉ để “dễ debug”.

## 10. Sau login/logout, token có thể bị xóa

`CsrfAuthenticationStrategy` và `CsrfLogoutHandler` có thể clear token cũ khi authentication thành công hoặc logout. Một SPA giữ token A từ trước có thể gặp:

~~~text
GET CSRF bootstrap → SPA giữ token A
POST /login với A  → login thành công
Authentication success → clear A
POST /settings với A → 403
~~~

**Giải pháp:** ứng dụng phải lấy token mới sau login/logout và gửi cùng session/cookie mới. Với deferred loading, một GET không sử dụng/render token có thể không tạo token mới; cần bootstrap endpoint/handler đúng.

Không giải quyết bằng `permitAll("/settings")` hoặc vô hiệu hóa CSRF trên mọi POST.

## 11. Dự án Spring Boot 3.5 / Spring Security 6.5 / Java 17

Để chứng minh **provider không được gọi khi CSRF sai**, ta tạo một provider demo có bộ đếm. Form login dùng filter thật của Spring Security, không tự xử lý trong controller.

**Giới hạn:** mã này phục vụ học/test. Provider chỉ nhận user `alice` với password test từ cấu hình; không thay thế thiết kế production với persistent `UserDetailsService`, MFA/passkey, rate limit hoặc audit.

### 11.1. Cấu trúc

~~~text
csrf-diagnosis/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/csrfdiagnosis/
    │   │   ├── CsrfDiagnosisApplication.java
    │   │   ├── RecordingAuthenticationProvider.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PrivateController.java
    │   └── resources/application.yml
    └── test/java/com/example/csrfdiagnosis/
        └── CsrfBeforeProviderTest.java
~~~

### 11.2. `pom.xml`

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>csrf-diagnosis</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Spring Boot parent quản lý dependency versions tương thích, bao gồm `spring-security-test` ở test scope.

### 11.3. `application.yml`

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

Khi chạy local, cung cấp `DEMO_USER_PASSWORD`; trong tests, `@SpringBootTest(properties=...)` cấp một password test riêng nên không cần environment variable.

### 11.4. `CsrfDiagnosisApplication.java`

~~~java
package com.example.csrfdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDiagnosisApplication.class, args);
    }
}
~~~

### 11.5. `RecordingAuthenticationProvider.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.env.Environment;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public final class RecordingAuthenticationProvider
        implements AuthenticationProvider {

    private final PasswordEncoder encoder;
    private final String storedHash;
    private final AtomicInteger calls = new AtomicInteger();

    public RecordingAuthenticationProvider(
            PasswordEncoder encoder, Environment environment) {
        this.encoder = encoder;
        String password =
                environment.getRequiredProperty("demo.user.password");
        this.storedHash = encoder.encode(password);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        calls.incrementAndGet();

        String username = request.getName();
        String submitted = String.valueOf(
                request.getCredentials());

        if (!"alice".equals(username)
                || !encoder.matches(submitted, storedHash)) {
            throw new BadCredentialsException(
                    "Invalid credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Override
    public boolean supports(Class<?> type) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
    }

    int calls() {
        return calls.get();
    }

    void resetCalls() {
        calls.set(0);
    }
}
~~~

Bộ đếm ở dòng đầu `authenticate()` minh họa chính xác: khi CSRF sai, nó không tăng; khi CSRF hợp lệ, bước xác minh credential mới chạy.

Password được mã hóa bằng encoder ở lúc tạo bean; test không dựa vào chuỗi plaintext trong DB. **Không dùng provider một-user này ở production.**

### 11.6. `SecurityConfiguration.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            RecordingAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        return http
                .csrf(Customizer.withDefaults())
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

`ProviderManager(List.of(provider))` đảm bảo đây là **provider duy nhất của AuthenticationManager demo**, giúp diễn giải bộ đếm mà không cần đoán provider fallback khác. `formLogin` cài `UsernamePasswordAuthenticationFilter`. `csrf` giữ mặc định. `permitAll` không bỏ qua CSRF.

### 11.7. `PrivateController.java`

~~~java
package com.example.csrfdiagnosis;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {
    @GetMapping("/private")
    public Map<String, Object> privateEndpoint(
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
~~~

Sau login thành công, `GET /private` sẽ cho nội dung tương đương `{"username":"alice","authenticated":true}`. Với anonymous, form login thường redirect tới `/login`.

## 12. JUnit 5 / MockMvc: chứng minh CSRF chặn trước provider

File `src/test/java/com/example/csrfdiagnosis/CsrfBeforeProviderTest.java`:

~~~java
package com.example.csrfdiagnosis;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "demo.user.password=local-only-test-password")
@AutoConfigureMockMvc
class CsrfBeforeProviderTest {

    @Autowired MockMvc mvc;
    @Autowired RecordingAuthenticationProvider provider;

    @BeforeEach
    void reset() {
        provider.resetCalls();
    }

    @Test
    void loginPageCanRenderTokenWithoutProvider()
            throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("_csrf")));
        assertEquals(0, provider.calls());
    }

    @Test
    void correctPasswordWithoutCsrfIsRejectedBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().isForbidden())
            .andExpect(unauthenticated());
        assertEquals(0, provider.calls());
    }

    @Test
    void wrongPasswordWithoutCsrfIsAlsoRejectedBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isForbidden());
        assertEquals(0, provider.calls());
    }

    @Test
    void invalidCsrfIsRejectedBeforeProvider() throws Exception {
        mvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().isForbidden());
        assertEquals(0, provider.calls());
    }

    @Test
    void correctPasswordWithCsrfReachesProvider()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-only-test-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"));
        assertEquals(1, provider.calls());
    }

    @Test
    void wrongPasswordWithCsrfReachesProvider()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
        assertEquals(1, provider.calls());
    }

    @Test
    void formLoginHelperAlreadyIncludesValidCsrf()
            throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("local-only-test-password"))
            .andExpect(authenticated().withUsername("alice"));
        assertEquals(1, provider.calls());
    }
}
~~~

Chạy:

~~~bash
mvn clean test
~~~

**Kỳ vọng:** 7 tests PASS, nếu đã có Maven/JDK 17+ và dependencies tương ứng. Báo cáo ở `target/surefire-reports/`; không có stdout Maven cố định trên mọi máy.

### 12.1. Ma trận kết quả các test

| Request | HTTP status dự kiến | Provider calls |
|---|---|---:|
| GET `/login` | 200 | 0 |
| POST đúng password, **không CSRF** | **403** | **0** |
| POST sai password, **không CSRF** | **403** | **0** |
| POST đúng password, **CSRF invalid** | **403** | **0** |
| POST đúng password, **CSRF valid** | 302 success | **1** |
| POST sai password, **CSRF valid** | 302 `/login?error` | **1** |
| `formLogin()` helper, đúng password | 302 success | **1** |

Lưu ý quan trọng: `SecurityMockMvcRequestBuilders.formLogin()` **tự gắn CSRF token hợp lệ**. Muốn test thiếu token phải dùng request thô `post("/login")` không `.with(csrf())`.

`@WithMockUser` không tự cấp CSRF token cho POST; `@AutoConfigureMockMvc(addFilters=false)` sẽ làm bài test không còn xác minh filter behavior thật.

**Giới hạn kiểm thử:** MockMvc có CSRF postprocessor giúp kiểm tra filter chain, nhưng không chứng minh browser thật đã giữ cookie/session đúng qua reverse proxy, nhiều nodes hoặc SPA bootstrap. Cần integration/E2E test thêm.

## 13. Chương trình Java 17 độc lập: thứ tự trước/sau provider

Nếu chưa cài Spring, chương trình sau mô phỏng nguyên tắc **early return khi CSRF sai**. Nó không thực hiện cryptographic CSRF verification thật và **không phải production authentication**.

File `CsrfBeforeProviderDemo.java`:

~~~java
public final class CsrfBeforeProviderDemo {

    enum CsrfResult {
        MISSING, INVALID, VALID
    }

    record LoginRequest(CsrfResult csrf, String password) {
    }

    static final class RecordingProvider {
        int calls;

        boolean authenticate(String password) {
            calls++;
            return "correct-test-password".equals(password);
        }
    }

    static String handle(
            LoginRequest request, RecordingProvider provider) {
        if (request.csrf() != CsrfResult.VALID) {
            return "403 CSRF";
        }
        return provider.authenticate(request.password())
                ? "302 HOME" : "302 LOGIN_ERROR";
    }

    static void show(
            String label, LoginRequest request,
            RecordingProvider provider) {
        System.out.println(label + "=" + handle(request, provider)
                + ", providerCalls=" + provider.calls);
    }

    public static void main(String[] args) {
        RecordingProvider provider = new RecordingProvider();
        show("missing", new LoginRequest(
                CsrfResult.MISSING, "correct-test-password"), provider);
        show("invalid", new LoginRequest(
                CsrfResult.INVALID, "correct-test-password"), provider);
        show("wrong", new LoginRequest(
                CsrfResult.VALID, "wrong"), provider);
        show("correct", new LoginRequest(
                CsrfResult.VALID, "correct-test-password"), provider);
    }
}
~~~

Chạy:

~~~bash
javac CsrfBeforeProviderDemo.java
java CsrfBeforeProviderDemo
~~~

**Stdout chính xác:**

~~~text
missing=403 CSRF, providerCalls=0
invalid=403 CSRF, providerCalls=0
wrong=302 LOGIN_ERROR, providerCalls=1
correct=302 HOME, providerCalls=2
~~~

Số lần provider là **tích lũy** từ đầu chương trình. Hai request đầu không làm nó tăng; chỉ hai request có CSRF hợp lệ mới đi đến bước `authenticate`.

## 14. Khi chỉ browser thật lỗi, còn MockMvc PASS

### 14.1. Cookie/session bị mất hoặc đổi

Kịch bản:
1. Browser lấy form `/login` và token trong session A.
2. POST đi sang replica B không chia sẻ session A.
3. Expected token ở B không tìm thấy hoặc khác.
4. CsrfFilter từ chối trước provider.

Cách khắc phục:
- Spring Session với shared repository hoặc session affinity phù hợp.
- Kiểm tra `JSESSIONID` thực sự được gửi trở lại, cùng hostname và path.
- Kiểm tra cookie `Secure`, `SameSite`, `Domain`, `Path`, expiry.
- Không cache HTML form có CSRF token ở CDN cho nhiều users.
- Không log raw cookies/token để phân tích.

### 14.2. Fetch/SPA thiếu credentials

Với frontend cùng origin, `fetch` có thể dùng `credentials: "same-origin"`:

~~~javascript
await fetch("/login", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type":
      "application/x-www-form-urlencoded;charset=UTF-8"
  },
  body: new URLSearchParams({
    username: usernameFromForm,
    password: passwordFromForm,
    _csrf: maskedTokenFromTrustedPage
  })
});
~~~

Đây là **mảnh JavaScript minh họa**, giả định token được render đúng cho session hiện hành. Không hardcode token hoặc truyền giá trị của một session khác.

Với cross-origin, cần kiểm tra `credentials: "include"`, CORS cho phép **origin cụ thể** kèm credentials, cookie policy và CSRF proof tương ứng. Không dùng wildcard CORS hoặc tắt CSRF để “sửa” lỗi cookie.

### 14.3. SameSite có thay CSRF không?

Cookie `SameSite=Lax/Strict` có tác dụng bổ sung, nhưng “same-site” không bằng “same-origin”. Một subdomain cùng site, redirect, browser differences, XSS hoặc các ambient credentials khác có thể thay đổi threat model. Với browser session app, CSRF token là lớp bảo vệ quan trọng, còn SameSite là **defense in depth**.

### 14.4. Header sai tên

Tên header phụ thuộc repository:
- `HttpSessionCsrfTokenRepository` thường sử dụng `X-CSRF-TOKEN`.
- `CookieCsrfTokenRepository` thường sử dụng `X-XSRF-TOKEN`.

Không copy mặc định của một stack frontend rồi giả định backend dùng cùng header. Đọc `CsrfToken.getHeaderName()` hoặc cấu hình repository/handler.

## 15. CORS và CSRF khác nhau

| Cơ chế | Điều kiểm tra | Thất bại |
|---|---|---|
| CORS | Origin nào có thể thực hiện/đọc một số cross-origin JS requests | Preflight/response blocked ở browser |
| CSRF | Unsafe request có proof đúng context không | Thường 403 tại CsrfFilter |
| Authentication | Credential/token có đúng không | Login error, 401 hoặc flow-specific |
| Authorization | Principal có quyền trên resource không | 403 sau xác thực/kiểm tra |

Một preflight `OPTIONS` có thể bị CORS chặn **trước khi POST login được gửi**, hoàn toàn khác với POST đã đến backend nhưng thiếu CSRF.

CORS không thay CSRF: ngay cả khi browser không cho JavaScript đọc response, các HTML form và credential auto-attachment vẫn có thể tạo tác động trong một số tình huống.

## 16. Multiple SecurityFilterChain và custom login paths

Một ứng dụng có thể cấu hình:

~~~java
http.formLogin(form -> form
        .loginPage("/sign-in")
        .loginProcessingUrl("/auth/submit")
        .permitAll());
~~~

Khi đó GET `/sign-in` là trang login **ứng dụng phải render**, còn POST `/auth/submit` mới là processing endpoint. Chỉ chuyển `loginPage` mà form vẫn POST `/login` sẽ gây lệch luồng.

Với nhiều chains, `FilterChainProxy` chọn **chain khớp đầu tiên** theo order/matcher. Các endpoint do filter tạo (như POST `/login`) chỉ tồn tại trong phạm vi chain chứa filter. Nếu `/api/login` rơi vào chain Resource Server trước chain form login, không có lý do mặc nhiên để `UsernamePasswordAuthenticationFilter` của chain sau chạy.

Để chẩn đoán:
1. Xác định `@Order`, `securityMatcher` và path của mỗi chain.
2. Kiểm tra selected chain có `CsrfFilter` không.
3. Kiểm tra selected chain có `UsernamePasswordAuthenticationFilter` không.
4. Xác nhận `loginProcessingUrl` nằm trong matcher đúng.
5. Không thêm `permitAll` hoặc bỏ CSRF ở chain khác khi chưa biết chain được chọn.

**Một response 403 có thể do CSRF ở chain được chọn chứ không phải provider của chain mà bạn đang debug.**

## 17. Có được tắt CSRF để giải quyết nhanh không?

**Không tắt CSRF toàn cục trên browser form-login/session application.**

Ví dụ cần tránh:

~~~java
// Không dùng để khắc phục lỗi POST /login trong ứng dụng browser:
http.csrf(csrf -> csrf.disable());
~~~

Nó có thể làm POST trước đó bị 403 trở nên “đăng nhập được”, nhưng đã **xóa cơ chế chống login CSRF** và bảo vệ unsafe requests khác.

Một API thực sự stateless, **chỉ** xác thực bằng bearer token trong `Authorization` header do client chủ động gửi và không dùng ambient browser credentials, có thể không cần CSRF cho các routes cụ thể. Tuy nhiên phải:
- đánh giá việc API có nhận cookie/session/HTTP Basic/client certificate hay không;
- tách route/chain rạch ròi;
- dùng `csrf.ignoringRequestMatchers` rất hẹp nếu đã có quyết định an ninh;
- test không có đường cookie-auth bị bỏ qua;
- đánh giá lại khi thêm refresh-token cookie, BFF/SPA session hoặc SSO.

**SessionCreationPolicy.STATELESS không tự chứng minh không có rủi ro CSRF** nếu endpoint vẫn chấp nhận loại credential browser tự gắn.

## 18. Log và quan sát an toàn khi điều tra

Các trường có thể ghi nhận:
- UTC timestamp, request ID, method, path và selected chain;
- `result=CSRF_REJECTED`, `AUTH_BAD_CREDENTIALS`, `AUTH_SUCCESS`;
- loại exception `MissingCsrfTokenException` / `InvalidCsrfTokenException`;
- `csrf_field_present`, `csrf_header_present`, `session_present` là **boolean**;
- backend node/replica, proxy path, frontend build version;
- tỷ lệ 403 của POST login trước/sau deploy, tỷ lệ authentication failures khi CSRF pass;
- kết quả test provider calls và correlation ID.

**Không log:** raw password, raw CSRF token, Authorization header, Cookie/JSESSIONID, full POST body, bearer token, session ID hoặc những thông tin cá nhân không cần thiết. Nếu bật DEBUG/TRACE, có hạn thời gian và quyền xem rõ.

Một lỗi CSRF đôi khi bị trình bày như “password incorrect” ở UI tùy biến. Cần logging/monitoring phân biệt tầng phát sinh để support không yêu cầu người dùng đổi mật khẩu vô ích.

## 19. Ma trận kiểm thử vận hành

| Trường hợp | Kỳ vọng |
|---|---|
| `POST /login` thiếu CSRF, password đúng | 403, providerCalls=0 |
| `POST /login` thiếu CSRF, password sai | 403, providerCalls=0 |
| `POST /login` invalid CSRF, password đúng | 403, providerCalls=0 |
| `POST /login` valid CSRF, password đúng | Authentication success |
| `POST /login` valid CSRF, password sai | Authentication failure |
| `GET /login` anonymous | Form/token render |
| `@WithMockUser` + POST không CSRF | Vẫn bị CSRF chặn |
| `formLogin()` MockMvc builder | Tự có valid CSRF |
| Form từ session A, POST session B | Rejection trong session repository model |
| Session hết hạn nhưng HTML form cũ | Yêu cầu token/form mới |
| SPA sau login dùng token đã clear | Rejection cho tới khi refresh token |
| SPA header raw đúng handler | Đi qua CSRF filter |
| SPA raw header vào masked-only handler | Rejection |
| Cookie `SameSite/Secure/Path` sai | Browser có thể không gửi session |
| Hai replica không chia sẻ HttpSession | Token mismatch/missing |
| CORS preflight fail | Phân biệt với POST CSRF failure |
| Custom loginProcessingUrl | Form action đúng URL |
| Multiple chain ordering | Correct filter chain selected |
| Form submit JSON với default form login | Không tự giả định provider đọc JSON |
| POST /logout không CSRF | Bị chặn theo chính sách |
| Stateless bearer-only API | Route-level CSRF policy theo threat model |
| Logs test/prod | Không chứa raw credentials hoặc session tokens |

Một test CSRF thực sự phải **giữ security filter chain được bật**. Nếu `@AutoConfigureMockMvc(addFilters=false)`, các test có thể cho kết quả “thành công” giả vì mọi filter bảo vệ đã bị bỏ qua.

## 20. Lỗi khắc phục phổ biến

1. Tắt CSRF trên toàn hệ thống để làm `POST /login` hoạt động.
2. Cho `permitAll("/login")` rồi cho rằng token không còn cần.
3. Sửa `PasswordEncoder` khi provider chưa được gọi lần nào.
4. Đổi login submit thành GET để tránh CSRF.
5. Log raw token/password/session để so sánh.
6. Bật cookie `SameSite=None` không xem HTTPS và cross-origin trust.
7. Giữ lại token cũ sau login/logout rồi cố reuse.
8. Chỉ bật `CookieCsrfTokenRepository` cho SPA nhưng không xem XOR request handler.
9. Nhầm `formLogin()` test builder với raw POST thiếu CSRF.
10. Tắt MockMvc security filters để test pass.
11. Quên cookie/session affinity trong cluster.
12. Debug nhầm SecurityFilterChain vì multiple matchers.
13. Xem mọi 403 là lỗi CSRF.
14. Xem CORS và CSRF là một cơ chế.
15. Tin các forwarded headers do client tự cung cấp.
16. Cache HTML login form/token cho mọi user.
17. Cho phép client nhận CSRF token từ nguồn bên ngoài hoặc user khác.
18. Bỏ CSRF ở đổi password, reset account và thao tác account nhạy cảm.
19. Nghĩ CSRF fail phải đi qua `AuthenticationFailureHandler`.
20. Tưởng `InvalidCsrfTokenException` có nghĩa chắc chắn token field vắng mặt.
21. Coi JWT token verifier đã chạy khi request bị CsrfFilter chặn trước.
22. Không kiểm tra request method/path/encoding ở client.

## 21. Checklist xử lý sự cố

- [ ] Xác nhận method/URL và `loginProcessingUrl`.
- [ ] Xác định SecurityFilterChain và thứ tự `CsrfFilter` so với login filter.
- [ ] Xác nhận CSRF error bằng exception/diagnostics hoặc test đối chứng.
- [ ] GET login render `_csrf` và POST gửi lại theo đúng session.
- [ ] Cookie/session có đúng Secure/SameSite/Domain/Path/expiry.
- [ ] Thymeleaf/form không bị thiếu hoặc duplicate token.
- [ ] SPA biết raw vs masked token, handler và repository phù hợp.
- [ ] SPA refresh token sau authentication/logout khi cần.
- [ ] CORS/credentials/proxy được cấu hình đúng, không wildcard nguy hiểm.
- [ ] Test missing, invalid và valid CSRF cho password đúng/sai.
- [ ] Provider counter/breakpoint xác nhận CSRF fail xảy ra **trước** provider.
- [ ] Bad password khi CSRF valid được báo bởi authentication flow.
- [ ] Không tắt CSRF toàn cục hoặc disable MockMvc filters.
- [ ] Test cluster/session store và browser thực.
- [ ] Không log raw password, token, cookies hoặc session ID.
- [ ] Có regression test trong CI cho lỗi CSRF trước provider.

## 22. Kết luận

**Đúng mật khẩu nhưng POST login trả 403, provider không được gọi** là một triệu chứng rất phù hợp với việc `CsrfFilter` từ chối request trước authentication. Muốn xác nhận, kiểm tra đúng security chain, CSRF exception, token repository, request handler và cookie/session; so sánh với request CSRF hợp lệ và đếm lời gọi provider.

~~~text
POST /login
    → đúng selected SecurityFilterChain?
    → CsrfFilter: token/session/handler hợp lệ?
          ├── Không → 403, providerCalls=0
          └── Có   → UsernamePasswordAuthenticationFilter
                        → AuthenticationManager
                        → AuthenticationProvider
                              ├── password sai → auth failure
                              └── password đúng → auth success
~~~

**Sửa cơ chế cung cấp CSRF proof và lifecycle của session; không sửa bằng cách vô hiệu hóa lớp bảo vệ.** Với Spring Security 6, đặc biệt chú ý deferred loading, XOR masked token và việc SPA cần token mới sau login/logout.

## 23. Tài liệu tham khảo

1. [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CsrfFilter, repository, request handler, login CSRF, SPA.
2. [Spring Security 6.5 — Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): thứ tự filter, FilterChainProxy, selected chain.
3. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): UsernamePasswordAuthenticationFilter và cách render form token.
4. [Spring Security 6.5 — Form Login MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): formLogin builder tự thêm CSRF token.
5. [Spring Security 6.5 — SecurityMockMvcRequestBuilders API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestBuilders.html): các request builders, CSRF.
6. [Spring Security 6.5 — CSRF Exceptions API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/package-summary.html): missing/invalid CSRF.
7. [Spring Security 6.5 — Multiple Filter Chains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): SecurityFilterChain matchers/endpoint scope.
8. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, SameSite và các biện pháp phòng thủ.
9. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session/cookie security và invalidation.
