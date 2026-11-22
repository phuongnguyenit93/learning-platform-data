# Phân biệt chưa xác thực với lỗi phân quyền HTTP 403 trong Spring Security

## 1. Câu trả lời nhanh: 401 là thiếu chứng thực hợp lệ, 403 là từ chối truy cập

Hai câu hỏi quan trọng của một hệ thống bảo mật web là:

1. **Authentication (xác thực):** Request đến từ **ai**, và bằng chứng đăng nhập/cookie/access token có **hợp lệ** không?
2. **Authorization (phân quyền):** Chủ thể đã xác thực đó có được phép thực hiện **hành động này trên tài nguyên này** không?

Theo **RFC 9110**, HTTP **401 Unauthorized** nghĩa là request chưa được áp dụng do **thiếu thông tin xác thực hợp lệ** cho tài nguyên; tên “Unauthorized” là tên lịch sử nhưng về thực hành nó thường chỉ vấn đề **authentication**. HTTP **403 Forbidden** nghĩa là server hiểu request nhưng **từ chối thực hiện**, điển hình là **đã xác thực nhưng không đủ quyền**.

| Trạng thái | Câu hỏi nhận diện | HTTP thường gặp ở REST API | Hành động phù hợp |
| --- | --- | --- | --- |
| Chưa gửi credential đến route bắt buộc login | “Bạn là ai?” | **401** kèm `WWW-Authenticate` theo scheme | Đăng nhập/gửi credential hợp lệ |
| Username/password sai hoặc Basic credential sai | “Chứng cứ này có xác thực được không?” | **401** với HTTP Basic; form login thường **302 về trang lỗi** | Sửa credential, không đoán role |
| Bearer access token sai chữ ký/hết hạn/thu hồi | “Có token hợp lệ không?” | **401**, Bearer `invalid_token` khi thích hợp | Lấy token mới; sửa cấu hình issuer/audience |
| Principal hợp lệ nhưng thiếu `ROLE_ADMIN` | “Đã đăng nhập rồi, có được phép vào admin?” | **403** | Xin quyền đúng; không lặp login vô hạn |
| Bearer token hợp lệ nhưng thiếu scope API đòi | “Có đủ scope cho resource không?” | **403**, Bearer `insufficient_scope` nếu policy và error handler biết đó là OAuth authentication hợp lệ | Xin authorization/scope phù hợp |
| POST dùng cookie nhưng thiếu/sai CSRF token | “Request thay đổi state có nguồn gốc đáng tin không?” | **403**, **kể cả khi người dùng chưa đăng nhập** | Lấy và gửi CSRF token đúng; không tắt CSRF |
| Browser Form Login chưa authenticated | “Cần đưa user về giao diện login nào?” | Thường **302 Location: /login**, **không nhất thiết 401** | Làm theo redirect; không áp số 401 cứng nhắc |
| Đã authenticated nhưng bị business rule/tenant/ownership từ chối | “Có sở hữu tài nguyên hay thuộc tenant đúng không?” | **403**, đôi lúc 404 để tránh lộ tài nguyên theo thiết kế | Không coi đó là lỗi password |

**Hai kết luận phải đi cùng nhau:**

- Trong một **REST API HTTP Basic/Bearer được cấu hình chuẩn**, **401** chủ yếu là chưa có authentication hợp lệ; **403** chủ yếu là đã xác thực nhưng không đủ quyền.
- **Không được suy ngược từ mã 403 rằng user chắc chắn đã xác thực**, hoặc từ mã 302 rằng đã đăng nhập. `CsrfFilter`, CORS, reverse proxy, WAF, controller và custom `AuthenticationEntryPoint` cũng có thể trả 403/302 theo cấu hình.

Mục tiêu học tập: giải thích được đường đi của `AuthenticationException` và `AccessDeniedException` trong Spring Security, lý do HTTP 401/403/302, kiểm tra Bearer `WWW-Authenticate`, viết cấu hình đúng và kiểm thử âm tính để phân biệt lỗi thực tế.

## 2. Ý nghĩa theo chuẩn HTTP: RFC 9110

### 2.1. 401 Unauthorized

Một response HTTP 401 cho biết cần một **authentication challenge** phù hợp cho resource. Theo RFC 9110, **server tạo response 401 MUST gửi ít nhất một header `WWW-Authenticate`**. Client biết nên dùng scheme nào và có thể thử lại với credential mới.

Ví dụ HTTP Basic:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Cache-Control: no-store
```

Request tiếp theo:

```http
GET /api/profile HTTP/1.1
Host: app.example.test
Authorization: Basic <base64-of-username-colon-password>
```

Chuỗi `Basic <...>` là credential trên wire, không phải định dạng hash/password lưu trong DB. **Basic Base64 không phải encryption**: phải dùng HTTPS và không ghi Authorization header vào log. Sai mật khẩu hoặc không gửi Basic credentials → ứng dụng có thể trả 401.

**Không nên custom response 401 bằng `response.setStatus(401)` và bỏ `WWW-Authenticate`** rồi khẳng định đó là HTTP authentication chuẩn. Khi cấu hình Basic/Bearer nên dùng `AuthenticationEntryPoint` thích hợp để tạo challenge. Một số hệ thống JSON non-HTTP-challenge có thể đặt 401 theo quy ước khác, nhưng cần hiểu ranh giới chuẩn RFC và hành vi client.

### 2.2. 403 Forbidden

HTTP 403 cho biết server hiểu request nhưng không cho thực hiện. Ngay cả nếu credential hợp lệ, **quyền vẫn có thể không đủ**.

```http
GET /api/admin HTTP/1.1
Host: app.example.test
Authorization: Basic <valid-alice-credentials>
```

Alice đã authenticated, có `ROLE_USER` nhưng endpoint yêu cầu `ROLE_ADMIN`:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not permitted to access this resource."
}
```

JSON trên là **ví dụ response ứng dụng tự định dạng** (Problem Details theo RFC 9457), **không phải body mặc định bắt buộc của Spring Security**. Nhiều cấu hình sẽ trả body trống, HTML error page hoặc cấu trúc lỗi riêng. Status 403 không đồng nghĩa “password sai”.

### 2.3. WWW-Authenticate và khác biệt của scheme

- **401** theo RFC 9110 yêu cầu `WWW-Authenticate` và có thể chỉ định `Basic`, `Bearer` hoặc scheme khác; không có nghĩa luôn là Basic.
- **403** không buộc có `WWW-Authenticate` trong mọi trường hợp. Tuy nhiên, **OAuth Bearer 403** với `insufficient_scope` **có thể có** `WWW-Authenticate: Bearer ...` theo RFC 6750.
- Response **407 Proxy Authentication Required** dùng `Proxy-Authenticate`, không phải 401/403 của origin server. Phân biệt gateway/proxy trả lỗi trước khi request vào Spring.
- **404 Not Found** là tài nguyên không tồn tại hoặc có thể dùng theo chính sách để che sự tồn tại resource không được phép nhìn; không coi 404 luôn là authorization success/failure.

## 3. Luồng xử lý trong Spring Security Servlet

Spring Security phân biệt lỗi cần **bắt đầu xác thực** với lỗi **từ chối quyền** bằng các thành phần quan trọng:

- `SecurityContextHolder` / `Authentication`: danh tính và danh sách authorities hiện tại.
- `AuthorizationFilter` (với `authorizeHttpRequests`) hoặc method security `@PreAuthorize`: áp policy.
- `AuthenticationException`: một bước xác thực gặp vấn đề, ví dụ credentials không hợp lệ.
- `AccessDeniedException`: rule truy cập từ chối.
- `ExceptionTranslationFilter`: dịch các exception bảo mật từ đoạn filter downstream thành hành động tương ứng.
- `AuthenticationEntryPoint`: **bắt đầu/yêu cầu authentication** (401 Basic/Bearer, hoặc 302 Form Login).
- `AccessDeniedHandler`: xử lý **không đủ quyền** của user đã authenticated, thường 403.

### 3.1. Sơ đồ quyết định

```text
HTTP request
    |
    v
SecurityFilterChain
    |
    | Authentication filters giải mã cookie/Basic/Bearer/session...
    | CsrfFilter/CorsFilter có thể chặn trước trong vài tình huống
    v
AuthorizationFilter / @PreAuthorize
    |
    +---- Access GRANTED ------------------> Controller / resource
    |
    +---- Access DENIED: AccessDeniedException
                         |
                         v
                ExceptionTranslationFilter
                         |
                  Authentication đủ tin cậy?
                  /                    \
             NO /                      \ YES
               v                        v
        AuthenticationEntryPoint     AccessDeniedHandler
        (401 hoặc 302,               (thường HTTP 403)
         tùy auth scheme)

AuthenticationException từ downstream:
    -> AuthenticationEntryPoint (401/302 tùy scheme)
```

Lưu ý kỹ thuật: các authentication filter như `BasicAuthenticationFilter` hay `BearerTokenAuthenticationFilter` có thể **tự gọi** `AuthenticationEntryPoint`/failure handler khi authentication thất bại; không phải mọi exception trên toàn chain đều đi qua `ExceptionTranslationFilter`. Bộ filter này đặc biệt quan trọng khi authorization hoặc method security ném exception ở đoạn nó bao quanh.

### 3.2. AccessDeniedException không luôn biến thành 403

Nếu user **anonymous** yêu cầu route chỉ cho ADMIN, Spring Security thường nhận một `AccessDeniedException` từ authorization rule. Nhưng `ExceptionTranslationFilter` thấy user chưa authenticated và chuyển sang `AuthenticationEntryPoint`:

- Với API Basic/Bearer: thường **401 challenge**.
- Với Form Login: thường **302 redirect tới /login**.

Nếu user **đã authenticated đủ** nhưng thiếu role/scope: chuyển tới `AccessDeniedHandler`, thường **403**. Đây là lý do **cùng một route** có thể trả 401 khi anonymous nhưng 403 khi Alice đã login và thiếu quyền.

### 3.3. AnonymousAuthenticationToken gây nhầm lẫn

Spring Security có thể đặt `AnonymousAuthenticationToken` trong SecurityContext thay vì để `Authentication=null`. Loại token này có thể có `isAuthenticated()=true` ở API của đối tượng nhưng **không được xem như người dùng đăng nhập thật** khi dùng authorization DSL `authenticated()`. Spring sử dụng cơ chế nhận diện anonymous/trust resolver để áp rule đúng.

**Không tự kiểm tra bằng cách:**

```java
Authentication auth = SecurityContextHolder
        .getContext().getAuthentication();
if (auth != null && auth.isAuthenticated()) {
    // Sai nếu coi đây là kết luận đủ rằng user thật đã login.
}
```

Hãy dùng Spring Security `.authenticated()`, `.hasRole(...)`, `@PreAuthorize`, hoặc `AuthenticationTrustResolver` nếu cần nhận diện anonymous bằng code. Đừng viết lại bộ lọc chỉ dựa vào boolean `isAuthenticated()`.

**Remember-me/partial authentication** cũng có thể bị yêu cầu xác thực mạnh hơn ở endpoint cần full authentication, tùy rule; đừng tự phân loại mọi đối tượng Authentication != null thành “đủ quyền”.

## 4. Một route, nhiều status: trường hợp điển hình

Giả sử GET `/api/admin` yêu cầu `ROLE_ADMIN`.

| Caller | Credential | Authentication result | Authorization | Response theo API Basic ví dụ |
| --- | --- | --- | --- | --- |
| Browser anonymous | Không có | Không có người dùng đã login | Thiếu role | **401** + Basic challenge |
| Alice | Basic username/password **sai** | Authentication thất bại | Không xét role như authenticated | **401** + Basic challenge |
| Alice | Basic hợp lệ, `ROLE_USER` | Authentication thành công | Thiếu `ROLE_ADMIN` | **403** |
| Admin | Basic hợp lệ, `ROLE_ADMIN` | Authentication thành công | Đủ role | **200** |
| Alice | Basic hợp lệ nhưng CSRF sai trên **POST** | Có thể bị chặn tại CSRF filter trước authorization | CSRF không đạt | **403**, không chứng minh đã thiếu role |
| Alice | Basic hợp lệ, `ROLE_ADMIN` nhưng tenant khác | Authenticated | Business authorization deny | **403** hoặc che resource bằng 404 nếu policy cho phép |

Những response trên giả định project Basic API ở mục 7. Trong Form Login, anonymous tới trang bảo vệ có thể nhận **302**; trong Resource Server, Bearer token invalid có challenge riêng; với custom handlers/WAF kết quả có thể khác. Do đó **status code được suy ra từ cả loại authentication + thời điểm exception + config**, không chỉ từ role.

## 5. Browser Form Login: 302 không đồng nghĩa 401 hay authenticated

Ứng dụng Spring MVC dùng `formLogin()` thường tương tác qua trình duyệt:

```text
Anonymous GET /admin
    |
    -> authorization deny
    -> LoginUrlAuthenticationEntryPoint
    -> HTTP 302 Location: /login
    |
    -> Browser GET /login
    -> HTTP 200 HTML login page
    |
    -> POST /login with username, password, CSRF
           -> Correct: redirect success target
           -> Wrong: redirect /login?error
    |
    -> Logged-in USER GET /admin
           -> HTTP 403 (không đủ ROLE_ADMIN)
```

**Điểm kiểm thử:** đừng nhìn `GET /login` trả 200 rồi ghi “user được truy cập /admin”. Một HTTP client tự động follow redirects có thể che mất status 302 ban đầu và chỉ hiển thị 200 của **trang login**. Hãy tắt auto-follow redirect hoặc kiểm `Location` và **URL cuối cùng**.

Ví dụ HTTP:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login
```

Vì HTML browser cần trang để nhập chứng cứ, redirect là hành vi tự nhiên; **không phải thiếu bảo mật chỉ vì route chưa login không trả 401**.

Với API trả JSON, redirect HTML login thường gây trải nghiệm kém: frontend nhận HTML thay cho JSON, fetch có thể follow redirect rồi báo lỗi parse. Thiết kế **SecurityFilterChain hoặc EntryPoint riêng** cho API Basic/Bearer và web form login nếu cùng ứng dụng có cả hai.

## 6. Bearer access token: RFC 6750, 401 invalid_token, 403 insufficient_scope

Trong ứng dụng API xác thực bằng OAuth2 Bearer token, RFC 6750 bổ sung quy tắc phản hồi cụ thể. Spring Security Resource Server có `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` phục vụ việc này.

### 6.1. Không có token

```http
GET /reports HTTP/1.1
Host: api.example.test
```

Response ví dụ theo RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
```

**Không có token** thì không nên phun ra `error_description`/details không cần thiết. API đang yêu cầu client cung cấp Bearer token phù hợp.

### 6.2. Token có nhưng không hợp lệ

Các lỗi như signature sai, `exp` hết hạn, `nbf` chưa đến, issuer không đáng tin, audience không thuộc API hoặc token bị revoke theo validator có thể làm authentication thất bại:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token"
```

Đây là ví dụ status/challenge. Các thuộc tính header cụ thể do provider/version/config quyết định; không mặc định Spring luôn gửi `realm` hoặc `error_description` đúng chuỗi mẫu.

### 6.3. Token hợp lệ nhưng thiếu scope

Token hợp lệ về issuer, signature, audience và thời hạn, nhưng có `scope="profile"` trong khi `GET /reports` yêu cầu `reports.read`:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports-api",
                  error="insufficient_scope",
                  scope="reports.read"
```

Theo RFC 6750, `insufficient_scope` **SHOULD** trả 403; thuộc tính `scope` là tùy chọn. `BearerTokenAccessDeniedHandler` của Spring chỉ có thể báo `insufficient_scope` khi nhận diện đã có một OAuth2 Authentication hợp lệ; ngược lại nó có thể chỉ trả scheme/realm. **Không viết test đòi exact string `scope=...` nếu ứng dụng không cấu hình thông tin đó.**

### 6.4. Token malformed đôi khi không phải 401

Theo RFC 6750, `invalid_request` do request dùng nhiều cách gửi token, sai định dạng yêu cầu hoặc tham số không hợp lệ có thể trả **400 Bad Request**. Đừng gộp **mọi** lỗi Bearer token vào 401 hay 403.

### 6.5. Phân quyền API vẫn tách khỏi Authentication

Sau khi Resource Server verify token, Spring có thể ánh xạ scope `reports.read` thành authority `SCOPE_reports.read`. Rule:

```java
.requestMatchers("/reports/**")
.hasAuthority("SCOPE_reports.read")
```

chỉ quyết định quyền truy cập; nó **không** tự validate JWT signature, issuer/audience nếu `JwtDecoder` đã cấu hình sai. Và một JWT đúng chữ ký nhưng cấp cho client/API khác vẫn không nên được chấp nhận.

### 6.6. Cấu hình Resource Server minh họa, riêng với ví dụ Basic

Trong một project Spring Boot 3.x khác có `spring-boot-starter-oauth2-resource-server` và provider OAuth/OIDC thật:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/tenant
          audiences: api://reports
```

Chỉ chạy khi issuer thật cung cấp metadata/JWKS, token được phát cho audience phù hợp. Ví dụ `issuer.example.test` là hostname minh họa.

SecurityFilterChain (đặt vào **ứng dụng Resource Server**, không đồng thời với chain Basic mục 7 nếu chưa thiết kế matcher/order):

```java
@Bean
SecurityFilterChain reportApi(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
```

Đoạn trên là **fragment trong class @Configuration**, cần imports cho `HttpSecurity`, `SecurityFilterChain`, `Customizer` và bean JWT decoder do Boot tạo. `oauth2ResourceServer().jwt()` **không tự quyết định audience đúng nếu bạn không cấu hình validation**. Cần kiểm tra issuer, audience, expiry, scope và business authorization.

## 7. Ví dụ Java 17 + Spring Boot 3 / Spring Security 6: HTTP Basic 401/403

Ví dụ thực nghiệm dưới đây cố ý dùng **HTTP Basic** để nhìn 401/403 rõ ràng, không cần OAuth server, JWT hoặc browser login form. Nó là project **Servlet MVC** tối giản và dùng **Spring Security 6.x**. Các địa chỉ localhost chỉ để development; trên hệ thống thật bắt buộc HTTPS.

### 7.1. Khởi tạo dự án và dependencies

Tạo project Spring Boot 3.x với Java 17+ từ Spring Initializr, chọn Gradle Groovy, Spring Web, Spring Security. Bổ sung test support trong `build.gradle` đã có plugin Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 7.2. Main application

File `src/main/java/com/example/authstatus/AuthStatusApplication.java`:

```java
package com.example.authstatus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthStatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStatusApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain

File `src/main/java/com/example/authstatus/SecurityConfig.java`:

```java
package com.example.authstatus;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/profile", "/api/settings")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Giải thích:**

- `/api/public` cho phép anonymous; request không gửi credential trả 200.
- `/api/profile` cần authenticated; anonymous hoặc Basic credential sai trả 401 với Basic challenge trong flow chuẩn.
- `/api/admin` cần `ROLE_ADMIN`; Alice đã authenticated với `ROLE_USER` sẽ nhận 403, admin được phép.
- `/api/settings` cần authenticated, nhưng **CSRF vẫn bật theo mặc định**, vì ví dụ cố ý cho thấy một POST có Basic hợp lệ vẫn có thể bị 403 do thiếu CSRF token.
- Không bật `formLogin()` trong ví dụ này, nên không cần nhầm status 302 redirect khi test Basic.
- `.anyRequest().denyAll()` từ chối mọi URL khác; với anonymous route bị deny, EntryPoint có thể trả 401. Không coi đây là hành vi 404 của ứng dụng.

Với client trình duyệt, HTTP Basic có thể được browser cache và **tự gửi Authorization** trong những request tiếp theo. Vì vậy không được mặc định tắt CSRF chỉ vì app đang dùng Basic; CSRF phụ thuộc khả năng browser tự đính credential. Các API Bearer chỉ chấp nhận token đưa tường minh trong JS header có mô hình khác, nhưng vẫn phải phân tích cách client lưu/gửi token.

### 7.4. Controller

File `src/main/java/com/example/authstatus/ApiController.java`:

```java
package com.example.authstatus;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/api/profile")
    public String profile(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/api/settings")
    public String settings() {
        return "updated";
    }
}
```

Khi role hợp lệ, GET trả body tương ứng. `POST /api/settings` dùng để test CSRF, không phải ứng dụng lưu cài đặt thật.

### 7.5. Chạy thử với curl

Khởi động project đã tạo:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Một số lệnh minh họa; chạy trong terminal development, **không gửi Basic password thật lên dịch vụ không có TLS**, và lưu ý thông tin trên command line có thể xuất hiện trong process history:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u alice:alice-pass http://localhost:8080/api/profile
curl -i -u alice:alice-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u alice:wrong http://localhost:8080/api/profile
```

Kỳ vọng status:

| Request | Status | Căn cứ |
| --- | --- | --- |
| `GET /api/public` anonymous | **200** | permitAll |
| `GET /api/profile` anonymous | **401** | Thiếu HTTP Basic authentication; có challenge |
| `GET /api/profile` với Alice hợp lệ | **200** | authenticated |
| `GET /api/admin` với Alice hợp lệ | **403** | ROLE_USER ≠ ROLE_ADMIN |
| `GET /api/admin` với Admin hợp lệ | **200** | ROLE_ADMIN |
| `GET /api/profile` với Alice sai password | **401** | Authentication thất bại |

Đây là hành vi **kỳ vọng của đúng cấu hình demo**. Test thực tế cần xem status và `WWW-Authenticate` để bảo đảm ứng dụng không bị reverse proxy hay interceptor khác thay response.

### 7.6. CSRF 403 ngay cả khi credential hợp lệ

```http
POST /api/settings HTTP/1.1
Host: localhost:8080
Authorization: Basic <valid-alice-credential>
Content-Type: application/x-www-form-urlencoded

theme=dark
```

Nếu request không có CSRF token hợp lệ, mặc định Spring Security sẽ **403**. Lý do không phải Alice thiếu quyền `/api/settings`; request bị chặn bởi **CSRF protection**. Để POST thành công trong test MVC, phải gửi CSRF token được app cấp và đúng session/repository, hoặc thiết kế API không dựa vào browser auto-attached credential rồi đặt CSRF policy phù hợp.

Khi chỉ gửi thêm header giả như `X-CSRF-TOKEN: anything` mà không liên hệ token repo/session, Spring Security vẫn nên từ chối. Không tắt CSRF toàn web app chỉ để làm ví dụ POST 200.

## 8. Test tích hợp MockMvc: assert 401, 403 và nhánh thành công

Tạo file `src/test/java/com/example/authstatus/ResponseStatusTest.java` trong project Boot ở mục 7:

```java
package com.example.authstatus;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResponseStatusTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResourceAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void missingCredentialsUsesBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE, containsString("Basic")));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminGets200() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void validPasswordDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/settings")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validPasswordAndCsrfCanPost() throws Exception {
        mvc.perform(post("/api/settings")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isOk());
    }
}
```

Đây là **test class chạy trong Spring Boot 3.x** với hai dependency test đã khai báo, không phải chương trình chạy trực tiếp bằng `javac`. Test dùng `httpBasic(...)` để chạy **đường xác thực Basic thực qua SecurityFilterChain**, không giả lập role. `csrf()` của Spring Security Test tạo CSRF token phù hợp cho MockMvc.

**Điểm dễ sai:** test `.with(user("alice").roles("ADMIN"))` hoặc `@WithMockUser(roles="ADMIN")` chỉ chứng minh **authorization** khi có principal được giả lập, **không chứng minh Basic password authentication thực tế**. Hãy có cả hai loại test với mục tiêu được ghi rõ.

Khi demo dùng password encoder BCrypt, mỗi lần khởi động hash mới nhưng mật khẩu gốc của fixture vẫn `alice-pass`, `admin-pass`. Kỳ vọng status ổn định nếu SecurityFilterChain được load đúng và không có filter bổ sung.

### Kiểm tra thêm, không chỉ HTTP status

Test 403 vì thiếu role nên xác nhận controller không phát side effect. Với database, kiểm tra record không được tạo; với payment, kiểm sự kiện không phát. Một response 302/403 không đủ để loại trừ lỗi controller đã chạy trước khi bị chặn nếu bạn tự viết bảo mật ở tầng sai.

## 9. Tại sao 403 không đủ để kết luận “đã xác thực”?

Có ít nhất sáu nguồn trả 403 ngoài việc thiếu role:

1. **CSRF:** POST/PUT/PATCH/DELETE bằng cookie hoặc Basic trong browser thiếu token CSRF hợp lệ. `CsrfFilter` có thể xử lý từ chối trước nhánh EntryPoint/authorization thông thường.
2. **CORS:** Cross-origin request không nằm trong allowlist; browser có thể báo lỗi CORS và server/proxy từ chối preflight hoặc response; đây không phải kết luận user là Alice hay Bob.
3. **WAF/reverse proxy/API Gateway:** Nginx, CDN, rate limiting policy hay edge ACL có thể trả 403 trước khi request đến JVM. Spring logs có thể không thấy request.
4. **Custom AuthenticationEntryPoint:** Nếu không cấu hình scheme nào tạo 401/302, một EntryPoint như `Http403ForbiddenEntryPoint` có thể trả 403 cho **anonymous**. Điều này không thể suy ra là user authenticated.
5. **Method/business authorization:** `@PreAuthorize`, ownership, tenant guard, feature policy hoặc chính controller tự trả 403 có thể không cùng phân nhánh filter-chain bạn đang tưởng.
6. **Path/method policy:** Matcher hoặc `denyAll()` áp lên endpoint ngoài ý muốn, URL khác context path, filter-chain order không đúng, hoặc policy đang chặn method. Có thể được chuyển thành 401/403 tùy authentication và EntryPoint.

Vì vậy công thức đúng là:

- **Xác định endpoint, HTTP method, security chain và loại credential.**
- **Kiểm authentication đã thành công chưa**, kiểm principal và authority theo cách an toàn.
- **Xác định filter/handler nào phát response**, xem `WWW-Authenticate`/`Location`.
- **Chỉ sau đó** kết luận thiếu authentication hay thiếu permission.

Không sửa lỗi 403 bằng việc tự động ép user logout ở mọi trường hợp; nếu 403 vì CSRF hoặc role, login lại có thể không khắc phục và gây vòng lặp.

## 10. ExceptionHandlingConfigurer: chọn đúng EntryPoint và DeniedHandler

Trong Servlet Security, DSL thường có dạng:

```java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(myAuthenticationEntryPoint)
    .accessDeniedHandler(myAccessDeniedHandler));
```

Đây là **API minh họa**: `myAuthenticationEntryPoint`/`myAccessDeniedHandler` phải là các bean/instance bạn đã tạo. Không đưa hai tên biến chưa định nghĩa vào class demo ở mục 7 rồi chạy. Các hook có mục đích khác nhau:

- `AuthenticationEntryPoint` xử lý cần bắt đầu authentication: Basic/Bearer 401 với challenge, LoginUrl 302, hoặc cơ chế UI phù hợp.
- `AccessDeniedHandler` xử lý quyền bị deny khi chủ thể đã được xác thực ở nhánh thích hợp: thường 403.
- `ExceptionTranslationFilter` **dịch exception thành hai lựa chọn**; bản thân nó không thay thế `AuthorizationManager` quyết định quyền.

### 10.1. Tuỳ chỉnh body 403 nhưng giữ HTTP Basic challenge 401

Trong project Basic đã có, nếu muốn response JSON cho 403, bạn có thể cấu hình **chỉ** AccessDeniedHandler, giữ `httpBasic()` tạo 401 challenge chuẩn:

```java
// Đoạn cấu hình bổ sung trong SecurityFilterChain đang có.
http.exceptionHandling(ex -> ex
    .accessDeniedHandler((request, response, error) -> {
        response.setStatus(403);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(
            "{\"type\":\"about:blank\",\"title\":\"Forbidden\"," +
            "\"status\":403}");
    }));
```

Nếu bạn tùy chỉnh AuthenticationEntryPoint 401, **giữ `WWW-Authenticate` thích hợp** cho Basic/Bearer. Không dùng một shared handler gắn status 403 cho cả `AuthenticationException` lẫn `AccessDeniedException` chỉ để frontend “nhìn đồng nhất”.

Tách phần format lỗi khỏi chính sách bảo mật. Khi cần Problem Details có `type`/`title`/`status`/correlation ID, đừng tiết lộ stack trace, user existence, mật khẩu đúng/sai chi tiết, token signature content, tên internal role nhạy cảm hay object owner ID.

### 10.2. Khi có web form và REST API trong một ứng dụng

Có thể có **hai SecurityFilterChain theo matcher/priority**:

- `/api/**`: xác thực bằng Bearer hoặc Basic; unauthorized trả 401 challenge; denied trả 403 JSON.
- `/web/**`: formLogin; anonymous redirect 302 tới trang đăng nhập; authenticated thiếu quyền trả 403 HTML/Access Denied page.

Dùng `@Order(1)` với `securityMatcher("/api/**")` và `@Order(2)` hoặc fallback chain cho web; **không để API rơi vào formLogin chain** khiến client fetch thấy HTML login. Ưu tiên cấu hình chuyên biệt cho từng protocol và kiểm tra `FilterChainProxy` trace xem request đã match chain nào. Đây là định hướng kiến trúc, không nên copy hai chain cùng matcher mà không xác định priority/entry point.

**Bảo vệ CSRF riêng từng chain:** web form dùng cookie cần CSRF; API pure Bearer header không do browser tự đính có thể có chính sách khác. Không nên vô hiệu hóa CSRF trên toàn app chỉ vì một phần dùng JWT.

## 11. Frontend và HTTP client nên xử lý 401/403 thế nào?

### 11.1. Xử lý 401

- Nếu API Bearer trả 401 `invalid_token`: có thể thử refresh access token theo OAuth client đúng chuẩn (nếu refresh token/rotation hợp lệ), rồi retry tối đa một lần cho request phù hợp; không retry vô hạn.
- Nếu không có session/refresh được: chuyển tới UI login hoặc báo cần đăng nhập lại.
- Với HTTP Basic: ứng dụng hoặc browser có thể hỏi credentials; đừng log Authorization header hay mật khẩu.
- Khi server trả 401 do token bị revoke/issuer sai: đừng giả định refresh luôn sửa được; kiểm tra security incident/config.
- Không đặt redirect-to-login phía frontend cho **mọi** response 403; người dùng đã logged in có thể chỉ thiếu permission.

### 11.2. Xử lý 403

- Hiển thị “Bạn không có quyền thực hiện hành động này” một cách trung lập, không lộ role/tenant/owner metadata.
- Với Bearer `insufficient_scope`, nếu ứng dụng có flow xin quyền bổ sung, hướng người dùng tới re-consent/re-authorization; không cố spam cùng token.
- Với CSRF 403, đồng bộ lại session/CSRF token theo UX an toàn, sửa form/header và thử lại với logic chống duplicate action; **không tắt CSRF**.
- Với WAF/CORS/edge 403, xem log/headers/correlation ID của lớp tạo lỗi trước khi sửa policy Spring.
- Không tự động xóa local session và đăng nhập lại chỉ vì role thiếu; tránh làm người dùng bị logout vô nghĩa.

### 11.3. Tránh auto-follow redirects làm sai phân loại

Các thư viện HTTP, browser và `fetch` có thể **follow redirect 302**. Nếu API response ban đầu là 302 tới `/login`, client có thể nhận 200 HTML login page và lỗi JSON parse. Debug bằng DevTools → Network với chuỗi request/redirect hoặc tắt follow redirect trong HTTP client test. Khi cấu hình API, hãy tạo EntryPoint trả 401 challenge thay vì redirect HTML.

### 11.4. Thông tin phản hồi nên lộ tối thiểu

Đừng phản hồi các khác biệt cho phép liệt kê tài khoản (“user admin tồn tại nhưng password sai”, “user bob không tồn tại”), không gửi JWT/CSRF token hoặc stack trace trong body lỗi. Log nội bộ có thể phân loại `authentication_failure`, `access_denied`, `csrf_rejected` theo correlation ID; response cho caller chỉ chứa thông tin họ cần để hành động hợp lệ.

## 12. Các test dễ nhầm và cách viết đúng

| Test ID | Request | Tiền điều kiện | Kết quả mong đợi trong config demo |
| --- | --- | --- | --- |
| A01 | GET `/api/public` | Không credential | 200 |
| A02 | GET `/api/profile` | Không credential | 401 + Basic challenge |
| A03 | GET `/api/profile` | Basic Alice sai password | 401 |
| A04 | GET `/api/profile` | Basic Alice đúng | 200 |
| A05 | GET `/api/admin` | Không credential | 401 + Basic challenge |
| A06 | GET `/api/admin` | Basic Alice đúng, `ROLE_USER` | 403 |
| A07 | GET `/api/admin` | Basic Admin đúng, `ROLE_ADMIN` | 200 |
| A08 | POST `/api/settings` | Basic Alice đúng, **CSRF thiếu** | 403 do CSRF |
| A09 | POST `/api/settings` | Basic Alice đúng, CSRF hợp lệ | 200 |
| A10 | POST `/api/settings` | Anonymous, CSRF thiếu | Thường 403 CSRF; không suy rằng anonymous là authenticated |
| F01 | GET `/web/admin` | Form Login anonymous | Thường 302 tới login |
| F02 | GET `/web/admin` | Session user login, thiếu ROLE_ADMIN | 403 |
| F03 | POST `/login` | Password sai + CSRF hợp lệ | Thường 302 về `/login?error` |
| B01 | GET `/reports` | Bearer token thiếu | 401 Bearer challenge |
| B02 | GET `/reports` | Bearer token hết `exp` | 401 `invalid_token` |
| B03 | GET `/reports` | Bearer token đúng, thiếu scope | 403 `insufficient_scope` nếu OAuth authentication hợp lệ và handler hỗ trợ |
| B04 | GET `/reports` | Bearer token đúng scope nhưng sai aud | 401 vì token không hợp lệ cho API |
| B05 | GET `/reports` | Bearer token malformed request | Có thể 400 `invalid_request` |
| G01 | GET resource | WAF chặn trước JVM | 403 từ edge, không có Spring trace |
| G02 | OPTIONS preflight | CORS không cho phép origin | Browser có thể báo CORS; response cụ thể tùy layer |
| M01 | POST domain action | Principal có role nhưng không sở hữu tài nguyên | 403 hoặc 404 theo policy, không side effect |
| M02 | POST domain action | Authentication hợp lệ nhưng CSRF sai | 403; không thay vì login lại |

**Một số test là tình huống ngoài project Basic**, cần cấu hình Form Login, Resource Server, WAF/CORS tương ứng. Không kỳ vọng cả 22 test chạy bằng cùng một SecurityFilterChain ở mục 7.

Khi test 403 do thiếu permission, hãy bảo đảm **credential đúng và CSRF hợp lệ**. Nếu CSRF chặn trước, test có thể pass với 403 **dù rule role bị cấu hình sai**, tạo false positive. Chỉ dùng GET khi muốn đo authorization mà không bị CSRF của request state-changing làm nhiễu.

## 13. Java 17 độc lập: mô hình trạng thái 401/403 để tự kiểm tra

Ví dụ sau không dùng Spring, Servlet hoặc JWT. Nó là một **decision model nhỏ** giúp kiểm sự khác biệt giữa *chưa xác thực*, *không đủ quyền* và *CSRF bị chặn sớm*, không khẳng định tái hiện toàn bộ ExceptionTranslationFilter. Lưu thành `AuthenticationStatusLab.java`.

```java
public final class AuthenticationStatusLab {

    enum Identity {
        ANONYMOUS,
        USER,
        ADMIN
    }

    record Request(
            Identity identity,
            boolean requiresAdmin,
            boolean csrfRequired,
            boolean csrfValid) {}

    static int status(Request request) {
        // Trong mô hình này, CSRF filter có thể chặn trước.
        if (request.csrfRequired() && !request.csrfValid()) {
            return 403;
        }
        if (request.identity() == Identity.ANONYMOUS) {
            return 401;
        }
        if (request.requiresAdmin()
                && request.identity() != Identity.ADMIN) {
            return 403;
        }
        return 200;
    }

    public static void main(String[] args) {
        System.out.println("anonymousProfile=" +
                status(new Request(Identity.ANONYMOUS,
                        false, false, true)));

        System.out.println("aliceProfile=" +
                status(new Request(Identity.USER,
                        false, false, true)));

        System.out.println("aliceAdmin=" +
                status(new Request(Identity.USER,
                        true, false, true)));

        System.out.println("adminAdmin=" +
                status(new Request(Identity.ADMIN,
                        true, false, true)));

        System.out.println("csrfBeforeAuth=" +
                status(new Request(Identity.ANONYMOUS,
                        false, true, false)));

        System.out.println("csrfAfterAuth=" +
                status(new Request(Identity.ADMIN,
                        true, true, false)));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac AuthenticationStatusLab.java
java AuthenticationStatusLab
```

Stdout chính xác:

```text
anonymousProfile=401
aliceProfile=200
aliceAdmin=403
adminAdmin=200
csrfBeforeAuth=403
csrfAfterAuth=403
```

Ý nghĩa:

- `anonymousProfile=401`: chưa có authentication cho route bảo vệ, nên logic REST challenge yêu cầu đăng nhập.
- `aliceProfile=200`: credential được giả định hợp lệ và route chỉ cần authenticated.
- `aliceAdmin=403`: Alice đã authenticated nhưng thiếu vai trò.
- `adminAdmin=200`: có cả authentication và permission.
- `csrfBeforeAuth=403` **mấu chốt**: một request anonymous cũng có thể nhận 403 vì CSRF filter chặn **trước** khi xử lý quyền.
- `csrfAfterAuth=403`: ngay cả Admin cũng không vượt CSRF khi request cần CSRF.

**Giới hạn:** chương trình không triển khai `WWW-Authenticate`, Basic password validation, Session, OAuth2 Bearer decoder, 302 Form Login hay actual Spring CSRF filters. Nó mô phỏng ranh giới quyết định, còn test MockMvc mục 8 mới kiểm filter chain thực.

## 14. Troubleshooting theo thứ tự chẩn đoán thay vì đoán từ status

Khi khách hàng báo “đã đăng nhập nhưng vẫn 403”, đi từ **lớp ngoài vào lớp trong**:

1. **Ghi request method + path + scheme + correlation ID** (không log credential). Đây là GET/POST, path thực, context path, domain và API/Web?
2. **Xác định response gốc**: status 401/403/302? Có `WWW-Authenticate: Basic/Bearer`? Có `Location: /login`? Có dấu CDN/WAF/gateway?
3. **Xác định security chain** đang match: `/api/**` có vô tình đi vào form-login chain không? `@Order` và `securityMatcher` hợp lý?
4. **Xác định authentication đã thành công**: Basic username/password, JWT signature/issuer/audience/expiry, session cookie và principal có hợp lệ? AnonymousAuthenticationToken không phải logged-in user.
5. **Nếu auth đã có**, đọc authorities đã được phát từ trusted authentication source: `ROLE_USER` hay `ROLE_ADMIN`, `SCOPE_x` hay `scope`? Nhớ `hasRole("ADMIN")` mặc định cần `ROLE_ADMIN`, còn `hasAuthority("SCOPE_reports.read")` khớp tên đầy đủ.
6. **CSRF/CORS trước authorization**: nếu POST 403, kiểm CSRF token/cookie và Origin/Fetch metadata/Referer policy theo app. Đừng bỏ lớp CSRF tùy tiện.
7. **Method security và nghiệp vụ**: `@PreAuthorize`, owner/tenant, account locked, MFA step-up và deny rules khác?
8. **Handler nào gửi response?** `AuthenticationEntryPoint`, `AccessDeniedHandler`, `CsrfFilter`, controller, gateway hay exception mapper? Không đổi status bừa bãi trước khi biết nguồn.
9. **Kiểm không có side effect**: request bị từ chối không được thay đổi database hoặc phát domain events.
10. **Đối chiếu bản thiết kế API**: REST cần 401/403 hợp lý, browser cần redirect login, Bearer cần challenge theo RFC 6750, UI cần thông điệp an toàn.

### Một số dấu hiệu thường gặp

| Quan sát | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| GET API anonymous trả 302 rồi HTML | API vào FormLogin EntryPoint | Tách API chain, dùng Basic/Bearer EntryPoint đúng |
| GET API anonymous trả 403 dù muốn 401 | Không có EntryPoint phù hợp/đang dùng Http403ForbiddenEntryPoint | Cấu hình scheme/API challenge và verify filter chain |
| User được 403 dù có `ROLE_ADMIN` trong DB | Spring Authentication chưa chứa authority, hoặc prefix/mapping sai | Kiểm `GrantedAuthority` từ trusted source và role mapping |
| JWT hợp lệ nhưng 401 | Sai issuer/audience/expiry/signature, JWKS không đúng | Đọc auth failure đã lọc secret; sửa validation không bỏ qua |
| JWT hợp lệ nhưng 403 | Thiếu scope/role/ownership, Bearer access denied | Xin scope phù hợp, sửa mapping business policy |
| POST 403 nhưng GET 200 | CSRF token thiếu hoặc policy riêng cho method | Kiểm CSRF và request matcher; không disable global |
| Header Basic/Bearer biến mất | Proxy/gateway không forward Authorization | Cấu hình proxy an toàn, không expose token trong log |
| Dùng `@WithMockUser` thì pass, login thật fail | Test bỏ qua AuthenticationProvider | Test Basic/Bearer/cookie thực cùng MockMvc integration |
| Browser fetch lỗi parse JSON nhưng status 200 | Auto-follow 302 tới /login trả HTML | Check redirect chain và Content-Type |
| Backend không thấy request 403 | Edge/WAF/CORS chặn trước Spring | So correlation ID và gateway logs |
| User có quyền nhưng tenant object bị deny | Ownership/tenant guard chặn đúng | Không lách bằng nâng ROLE_ADMIN bừa bãi |
| Tự custom EntryPoint trả 401 body JSON không header | Thiếu WWW-Authenticate theo HTTP challenge chuẩn | Dùng Basic/Bearer EntryPoint hoặc giữ đúng challenge |
| 401 lặp vô hạn sau refresh token | Client interceptor retry loop, refresh fail | Retry hữu hạn, invalidate credential đúng cách |
| Role bị coi là username | Nhầm Authentication và Authorization | Dùng principal cho identity, authorities cho permission |

## 15. Checklist khi review Spring Security authentication response

- [ ] Đã phân biệt **authentication** (thiếu/sai credential) với **authorization** (đã xác thực nhưng thiếu quyền).
- [ ] API 401 có `WWW-Authenticate` phù hợp Basic/Bearer theo RFC 9110; không dùng một handler 403 cho mọi trường hợp.
- [ ] 403 với authenticated user thiếu role/scope là expected; không ép user login lại vô hạn.
- [ ] **403 không chứng minh đã authenticated**: đã kiểm CSRF, WAF, CORS, Http403ForbiddenEntryPoint, custom controller và route policy.
- [ ] Form Login anonymous có thể nhận **302** tới login; test không nhầm status 200 của trang đăng nhập với truy cập resource thành công.
- [ ] Spring `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler` được hiểu đúng; authenticated vs anonymous được nhận diện bằng Spring policy, không chỉ `auth != null`.
- [ ] Basic/Bearer credentials đã được kiểm thật; test `@WithMockUser` không bị dùng làm bằng chứng credential validation.
- [ ] Đã test anonymous, wrong password, authenticated user thiếu role, admin đủ role, Bearer invalid/scope, POST thiếu CSRF và happy path.
- [ ] Khi 403 do CSRF, request bị chặn trước side effect; test role-only dùng CSRF hợp lệ để tránh false positive.
- [ ] UI xử lý 401 bằng yêu cầu authentication, 403 bằng thông điệp permission/scope và không xóa session vô lý.
- [ ] Có xác minh issuer/audience/expiry với JWT, role prefix `ROLE_`, scope prefix `SCOPE_`, tenant/owner policy riêng.
- [ ] Log phục vụ chẩn đoán nhưng không lộ Authorization header, access token, password, cookie, nội bộ user details.

**Tóm tắt cuối cùng:** **401** thường nghĩa là *chưa có authentication hợp lệ*, **403** thường nghĩa là *không được phép làm điều đã yêu cầu*. Nhưng status là **kết quả của cả luồng và cấu hình**: trong Spring Security, anonymous gặp `AccessDeniedException` có thể được xử lý bằng EntryPoint tạo **401 hoặc 302**, user đã login thiếu quyền đi qua AccessDeniedHandler tạo **403**, và CSRF/gateway vẫn có thể tạo **403 ngay cả khi anonymous**. Để kết luận chính xác, xem auth scheme, filter/handler, credential, quyền và request method cùng lúc.

### Tài liệu chuẩn

- [RFC 9110 — HTTP Semantics, 401, 403 và WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — Bearer Token Usage, invalid_token và insufficient_scope](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Security 6.5 — ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security 6.5 — Servlet Architecture và Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
