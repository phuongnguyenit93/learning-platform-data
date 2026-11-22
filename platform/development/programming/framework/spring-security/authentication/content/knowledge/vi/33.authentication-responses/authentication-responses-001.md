# AuthenticationEntryPoint và yêu cầu client cung cấp bằng chứng danh tính

> **Module:** Spring Security – Authentication. **Nhóm:** Phản hồi xác thực. Tài liệu dành cho Java 17+, Spring Boot 3.x và Spring Security 6.x trên Servlet stack. Tập trung vào vai trò của `AuthenticationEntryPoint` khi client chưa chứng minh danh tính, cách HTTP 401/403/302 mang ý nghĩa khác nhau, thách thức xác thực `WWW-Authenticate`, và thiết kế web form login song song REST API an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Diễn giải interface `AuthenticationEntryPoint` và mục đích của phương thức `commence(...)`.
2. Nêu được khi nào `ExceptionTranslationFilter` gọi EntryPoint, khi nào `AccessDeniedHandler` xử lý; lý giải tại sao các authentication filters cũng có thể gọi EntryPoint trực tiếp.
3. Phân biệt **không có credential**, **credential không hợp lệ**, **đã xác thực nhưng thiếu quyền** và **một lần submit login bị thất bại**.
4. Đọc phản hồi HTTP: redirect `302 Location`, `401 WWW-Authenticate: Basic` hoặc `Bearer`, `403 Forbidden`.
5. Chọn `LoginUrlAuthenticationEntryPoint`, `BasicAuthenticationEntryPoint`, `BearerTokenAuthenticationEntryPoint`, `HttpStatusEntryPoint` hoặc `DelegatingAuthenticationEntryPoint` theo giao thức.
6. Cấu hình Spring Security cho browser và API bằng `SecurityFilterChain`/`@Order` mà không làm REST client nhận HTML login.
7. Tùy biến JSON khi cần, nhưng không bỏ header challenge, không tiết lộ token hoặc gây vòng lặp redirect.
8. Viết kiểm thử và chạy ví dụ Java 17 chứng minh lựa chọn phản hồi đúng.

## 2. Câu trả lời cốt lõi: EntryPoint làm gì?

`AuthenticationEntryPoint` là **điểm bắt đầu authentication** ở giao diện HTTP. Khi một tài nguyên cần Authentication thích hợp mà request chưa đáp ứng, Spring Security dùng thành phần này để **yêu cầu client cung cấp bằng chứng danh tính**.

Tùy cơ chế xác thực, nó có thể:

- Redirect browser tới trang đăng nhập `/login` để người dùng nhập username/password.
- Phát `401` và `WWW-Authenticate: Basic realm="..."` để client biết server hỗ trợ HTTP Basic.
- Phát `401` và `WWW-Authenticate: Bearer` để client biết resource yêu cầu OAuth2 access token.
- Gửi một status hoặc challenge khác theo giao thức đã thỏa thuận; thực thi đúng hợp đồng HTTP và chính sách ứng dụng.

**EntryPoint không kiểm tra password hoặc JWT**: nhiệm vụ đó thuộc `AuthenticationManager`, `AuthenticationProvider`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`, `JwtDecoder` hay dịch vụ định danh tương ứng. Nó cũng không trao role và không tự cấp session/token. Nó là **đầu ra hướng dẫn authentication**, không phải authentication verifier.

Interface do Spring Security cung cấp, chữ ký Servlet (để giải thích, không tự tạo lại file interface):

```java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.core.AuthenticationException authException)
        throws java.io.IOException, jakarta.servlet.ServletException;
}
```

| Đối số | Công dụng | Yêu cầu an toàn |
|---|---|---|
| `request` | Request khiến auth bị yêu cầu | Không coi `Host`, `Authorization` hay query do client khai là bằng chứng đã xác thực |
| `response` | Nơi đặt HTTP status, `WWW-Authenticate`, `Location` hoặc body | Chỉ ghi khi response chưa committed, không tạo phản hồi mâu thuẫn |
| `authException` | Lỗi hoặc nguyên nhân cần authentication | Không phản hồi toàn bộ `getMessage()`, stack trace, JWT hay dữ liệu nhạy cảm |

EntryPoint chỉ **mời client cung cấp credential**. Để request sau đó thành công, client phải thực sự gửi bằng chứng tới authentication filter/provider phù hợp và được kiểm tra. **Một `401` không chứng minh username hay account có tồn tại.**

## 3. Liên hệ giữa Authentication, Authorization và ExceptionTranslationFilter

Luồng khái niệm của Spring Security Servlet:

```text
Client GET /private (không login/token)
               |
               v
          FilterChainProxy
       chọn SecurityFilterChain
               |
               v
      SecurityContext / auth filters
               |
               v
       ExceptionTranslationFilter
               |
               v
         AuthorizationFilter
           |          |
        permit       deny
           |          |
           v          v
       Controller  AccessDeniedException
                      |
                      v
              ExceptionTranslationFilter
                      |
           +----------+-------------------+
           |                              |
   anonymous/thiếu auth            đã auth đủ nhưng
   hoặc AuthenticationException     thiếu quyền
           |                              |
           v                              v
   AuthenticationEntryPoint       AccessDeniedHandler
           |                              |
   302 login hoặc 401 challenge      403 / custom deny
```

`ExceptionTranslationFilter` là cầu nối từ Java security exceptions sang phản hồi HTTP. Nó bao phần xử lý phía sau trong chain, phát hiện `AuthenticationException` hay `AccessDeniedException` và chọn đúng cơ chế phản hồi.

**Phân biệt hai trường hợp:**

1. Request không có credential, nhưng `AuthorizationFilter` yêu cầu `authenticated()`. `AccessDeniedException` xuất hiện; vì đối tượng thực chất đang anonymous, `ExceptionTranslationFilter` khởi động EntryPoint.
2. User đã được xác thực đầy đủ nhưng thiếu `ROLE_ADMIN` hoặc scope/ownership phù hợp. `AccessDeniedHandler` xử lý, thường trả `403`, thay vì mời đăng nhập lại.

`AuthenticationTrustResolver` của framework có thể giúp đánh giá anonymous/remember-me và trường hợp yêu cầu xác thực mạnh hơn; **đừng chỉ kiểm tra `Authentication != null` rồi kết luận user đã login**. `AnonymousAuthenticationToken` có thể hiện diện trong SecurityContext và một số flag như `isAuthenticated()` vẫn không có nghĩa user thực sự vượt qua login.

### 3.1. EntryPoint còn được gọi trực tiếp bởi authentication filters

Không phải mọi 401 đều phải bắt nguồn từ `ExceptionTranslationFilter`:

- Nếu thiếu Bearer token, filter có thể bỏ qua; `AuthorizationFilter` về sau chặn anonymous và gọi EntryPoint qua translation.
- Nếu client gửi JWT hết hạn/sai chữ ký, `BearerTokenAuthenticationFilter` nhận credential, authentication thất bại và có thể **gọi EntryPoint thông qua failure handling riêng**.
- HTTP Basic sai username/password thường được `BasicAuthenticationFilter` xử lý thất bại, rồi gọi EntryPoint.
- Form login POST sai credential thường được `UsernamePasswordAuthenticationFilter` xử lý qua `AuthenticationFailureHandler`, chuyển về `/login?error` hoặc theo cấu hình. Đó **không phải** tình huống “anonymous chỉ vừa mở một trang cần login”.

Vì vậy khi tùy biến, cần test **thiếu credential** và **credential có nhưng invalid** riêng biệt, không chỉ một ca 401.

### 3.2. RequestCache / SavedRequest

Trong ứng dụng browser, `HttpSessionRequestCache` có thể giữ đường dẫn user muốn mở trước login. EntryPoint redirect đến trang login; khi login thành công, một success handler như `SavedRequestAwareAuthenticationSuccessHandler` có thể chuyển về request gốc.

Với API stateless dùng Basic/Bearer, client thường tự gửi lại request với credential mới; `NullRequestCache` phù hợp hơn việc tạo HTTP session. Không biến API JWT thành session-based chỉ vì có một request chưa xác thực. Saved destination phải được kiểm soát để không tạo open redirect, replay dữ liệu nhạy cảm hoặc đưa token vào `Location`.

## 4. Ba phản hồi rất dễ bị nhầm: 401, 403, 302

**401 Unauthorized** trong HTTP authentication nghĩa là **request thiếu hoặc chưa trình bằng chứng xác thực hợp lệ**. Theo RFC 9110, nếu gửi 401 trong HTTP authentication, response cần một challenge `WWW-Authenticate` áp dụng cho tài nguyên đó.

**403 Forbidden** thường có nghĩa request đã được hiểu nhưng caller không có quyền. Ví dụ token hợp lệ nhưng thiếu scope, user login xong thiếu role hoặc thiếu quyền dữ liệu. Việc bắt login lại không tự tạo thêm quyền.

**302 Found** được browser form login dùng để điều hướng tới một trang nhập credential. Nó không nên là phản hồi mặc định của REST endpoint chỉ chấp nhận bearer token.

| Tình huống | Phản hồi thường đúng | Thành phần |
|---|---|---|
| Browser GET `/profile` chưa có session login | `302 Location: /login` | `LoginUrlAuthenticationEntryPoint` |
| HTTP Basic API chưa gửi credential | `401 WWW-Authenticate: Basic` | `BasicAuthenticationEntryPoint` |
| OAuth2 API thiếu bearer token | `401 WWW-Authenticate: Bearer` | `BearerTokenAuthenticationEntryPoint` |
| OAuth2 API bearer hết hạn/sai chữ ký/revoked | `401`, có thể `error="invalid_token"` | Bearer entry point |
| Token đã hợp lệ nhưng không có scope yêu cầu | `403`, có thể `error="insufficient_scope"` | `AccessDeniedHandler` |
| Đã login nhưng thiếu `ROLE_ADMIN` | `403` | `AccessDeniedHandler` |
| POST form login username/password sai | Failure response/redirect theo UI | `AuthenticationFailureHandler` |
| POST browser thiếu CSRF hợp lệ | Thường 403 | CSRF protection/denial |
| Bearer request malformed theo RFC 6750 | Có thể 400 `invalid_request` | Bearer error policy |
| Endpoint public được phép | Tiếp tục request | Không cần EntryPoint |

Lưu ý: API endpoint có thể từ chối quyền dữ liệu bằng 404 để không tiết lộ sự tồn tại tài nguyên, tùy chính sách. Không suy diễn rằng **tất cả** lỗi 403 đều nhất thiết được phát bởi `AccessDeniedHandler` hoặc mọi 401 đều được phát bởi cùng một đường filter.

### 4.1. HTTP WWW-Authenticate là challenge

Response minh họa cho Basic:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="internal-api"
Cache-Control: no-store
```

Response minh họa cho Bearer thiếu token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
```

Response minh họa cho Bearer token không hợp lệ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

Response minh họa cho bearer hợp lệ nhưng không đủ scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
Cache-Control: no-store
```

Đây là các **mẫu giao thức**, không phải output bắt buộc giống từng byte của mọi cấu hình. `realm`, `scope`, `error_description` và thứ tự parameters do implementation/policy xác định. RFC 6750 đề nghị khi request **hoàn toàn không có thông tin xác thực**, server không tự thêm error code mô tả token không tồn tại. Với `invalid_request` do malformed request, response có thể là 400 chứ không phải 401.

### 4.2. Client cần làm gì sau challenge?

- **HTTP Basic:** lấy username/password được phép, gửi qua HTTPS bằng header `Authorization: Basic ...`; Base64 chỉ là encoding, không mã hóa.
- **Bearer:** lấy access token từ Authorization Server theo OAuth flow phù hợp rồi gọi lại bằng `Authorization: Bearer ...`. Nếu token hết hạn, có thể refresh giới hạn; token bị revoke hoặc refresh grant không hợp lệ thì phải tái đăng nhập theo policy.
- **403 insufficient_scope:** không tự retry vô tận hoặc tự cấp scope; user/client cần quyền và consent thật nếu policy hỗ trợ. Nếu thiếu quyền đối tượng hoặc tenant, việc xin token mới cũng không được tự vượt authorization.
- **Browser 302:** hiển thị form login an toàn; sau thành công quay lại path hợp lệ. Không ghép bearer token hay password vào `next`, `redirect` hoặc `Location`.

## 5. Các AuthenticationEntryPoint thường gặp

| Class | Giao thức/tình huống | Lưu ý |
|---|---|---|
| `LoginUrlAuthenticationEntryPoint` | HTML form login | Redirect tới login URL; route login phải được permit |
| `BasicAuthenticationEntryPoint` | HTTP Basic | 401 và challenge Basic kèm realm |
| `BearerTokenAuthenticationEntryPoint` | Spring Security OAuth2 Resource Server | Dùng `BearerTokenError` để chọn status và Bearer challenge |
| `HttpStatusEntryPoint` | API/custom scheme muốn trả status đơn giản | **Không** tự thêm Basic/Bearer challenge |
| `DelegatingAuthenticationEntryPoint` | Nhiều scheme chung một chain | Chọn entry point theo `RequestMatcher` |
| `Http403ForbiddenEntryPoint` | Một số kiến trúc pre-auth | Không dùng thay mặc định cho bearer API thiếu token |
| `NoOpAuthenticationEntryPoint` | Flow tự xử lý theo thiết kế đặc biệt | Không phản hồi; dễ gây lỗi nếu dùng nhầm |

**Quy tắc quan trọng:** chọn entry point theo **authentication scheme và client contract**, không chỉ vì “muốn status 401”. Tùy biến response Basic/Bearer không được làm biến mất `WWW-Authenticate`. `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` trả 401 đơn giản nhưng không tự cung cấp header challenge cho HTTP authentication.

### 5.1. Form login

`LoginUrlAuthenticationEntryPoint` thường được tạo qua DSL:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll());
```

Đây là **snippet** trong `SecurityFilterChain`. Khi chỉ định custom login page, ứng dụng phải có `GET /login` để render template và một form POST login với CSRF token. Nếu dùng `formLogin(Customizer.withDefaults())`, Spring Security có thể cung cấp generated login page tùy cấu hình.

Đừng để `/login` cũng yêu cầu `authenticated()`: browser có thể rơi vào vòng lặp redirect `/login` → `/login`. Nếu browser đã login nhưng thiếu quyền, việc chuyển lại trang login chỉ gây nhầm lẫn.

### 5.2. Basic login

`BasicAuthenticationEntryPoint` làm cho HTTP client biết cần gửi Basic credential:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
```

Đây cũng là snippet trong chain, cần import `org.springframework.security.config.Customizer`. Với SecurityFilterChain tự khai báo, cấu hình cơ chế Basic một cách tường minh, không dựa vào mặc định của một ứng dụng Spring Boot khác.

Một số browser hiển thị hộp thoại password nếu nhận Basic challenge; một số cơ chế `XMLHttpRequest` có xử lý khác để tránh dialog. Không lấy một header client dễ giả mạo làm bằng chứng đã authenticated.

### 5.3. Bearer resource server

`BearerTokenAuthenticationEntryPoint` được Spring Security tích hợp cho OAuth2 Resource Server, giữ error response theo Bearer semantics (RFC 6750). Token sai/hết hạn có thể trả `invalid_token`, còn token hợp lệ nhưng không đủ scope thường do `BearerTokenAccessDeniedHandler` xử lý. Đừng tự đưa nguyên `authException.getMessage()` vào `error_description` hoặc JSON: nó có thể lộ issuer, lỗi chữ ký, internal URLs, user và thông tin cấu hình.

### 5.4. DelegatingAuthenticationEntryPoint

`DelegatingAuthenticationEntryPoint` có thể chọn endpoint phản hồi theo `RequestMatcher` (ví dụ API nhận 401, browser nhận redirect). Với hệ thống có ranh giới route rõ, **hai SecurityFilterChain riêng** thường dễ vận hành hơn: chain API áp dụng `/api/**` và chain browser làm fallback. Dùng `Accept: application/json` hoặc `X-Requested-With` để đoán authentication scheme không nên là biện pháp phân định tin cậy duy nhất.

## 6. Spring Boot 3 / Spring Security 6: cấu hình tách REST API và browser UI

Ví dụ kết hợp:

- `/api/**` là API dùng JWT bearer trong `Authorization` header, stateless.
- Các route khác là web browser session + form login.

Hai cơ chế dùng **hai `SecurityFilterChain`** có thứ tự rõ. Nhờ đó API không bị trả 302 HTML trong khi client chờ Bearer challenge.

### 6.1. Gradle dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Để có password login thực tế, phải thêm `UserDetailsService` / user repository / `PasswordEncoder` phù hợp. JWT resource server cần issuer/JWK tin cậy để validate token.

### 6.2. application.yml cho JWT

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

Kiểm tra **signature, issuer, audience, exp/nbf** và authorities/scope theo policy. Không nhận ID Token dành cho client làm API access token chỉ vì nó là JWT. Chọn issuer/JWK và expected audience từ cấu hình tin cậy; đừng bỏ validation để làm hết 401.

### 6.3. SecurityFilterChain hoàn chỉnh ở mức cấu hình

File `src/main/java/com/example/security/MixedSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyRequest().authenticated())
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            // Chỉ khi API KHÔNG dùng cookie/session authentication.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // CSRF tiếp tục bật cho browser form.
        return http.build();
    }
}
```

**Cách hoạt động và giới hạn:**

1. Spring chọn **chain đầu tiên phù hợp**. `@Order(1)` với `securityMatcher("/api/**")` tách API khỏi browser chain.
2. Request API không token đến protected route sẽ có Bearer challenge thay vì redirect form. Nếu gửi token sai vào endpoint `permitAll`, authentication filter vẫn có thể từ chối trước authorization; `permitAll` không tắt mọi filter.
3. `SCOPE_admin` ở đây là một authority từ scopes của JWT theo default mapping; nếu token thiếu scope sẽ có 403 thay vì tạo credential mới.
4. `STATELESS` có nghĩa Security không dùng session để lấy Authentication cho API. Việc tắt CSRF trong chain đó **chỉ phù hợp cho API thuần header Bearer, không dựa vào cookies/automatic credentials**. Nếu API dùng session/cookie browser thì phải giữ/thiết kế CSRF.
5. Browser dùng form login với SecurityContext/session và CSRF theo cấu hình.
6. Cần `@SpringBootApplication`, endpoints, JWT decoder/issuer, user store/login provider và server HTTP thật. File cấu hình không chạy riêng bằng `javac`.
7. Khi thêm `/api` không có slash cuối hoặc nhiều Servlet mappings, kiểm tra matchers để không lọt sang chain browser. Không tự coi mọi `/**` là equivalent với exact path.

**Phản hồi HTTP minh họa** cho cấu hình trên:

```http
GET /api/orders HTTP/1.1
Host: app.example.org

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

```http
GET /profile HTTP/1.1
Host: app.example.org

HTTP/1.1 302 Found
Location: /login
```

Ví dụ gộp request và response để nhìn khác biệt, không phải một HTTP exchange wire-format đầy đủ. `Location` thật có thể là absolute URL và phụ thuộc proxy/context path.

## 7. HTTP Basic: kích hoạt riêng khi thực sự cần

Với API nội bộ dùng Basic, cơ chế phù hợp khác Bearer. Ví dụ cấu hình một chain độc lập cho `/internal-basic/**`:

```java
@Bean
@Order(1)
SecurityFilterChain basicChain(HttpSecurity http)
        throws Exception {

    http
        .securityMatcher("/internal-basic/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

Đoạn trên là **snippet** trong class `@Configuration` đã có imports và dependencies, cần điều phối thứ tự nếu còn chain khác. Cần `AuthenticationProvider` / `UserDetailsService` tương ứng cho password login.

Luồng:

```text
1. Client GET /internal-basic/report (không credential)
2. Server: 401 + WWW-Authenticate: Basic realm="..."
3. Client gửi Authorization: Basic <base64(username:password)>
4. BasicAuthenticationFilter xác minh qua AuthenticationManager
5. Authentication thành công và đủ quyền: request tiếp tục
```

Base64 là encoding, không bảo mật bí mật. Bắt buộc dùng TLS, redaction Authorization, rate-limit, chính sách password và client secret phù hợp. Basic có thể là giải pháp nội bộ đơn giản nhưng không phải thay thế OAuth Bearer mặc định cho mọi API.

## 8. EntryPoint, FailureHandler và AccessDeniedHandler không giống nhau

| Thành phần | Trách nhiệm | Điểm gọi thường thấy |
|---|---|---|
| `AuthenticationEntryPoint` | Yêu cầu hoặc khởi động authentication | Anonymous truy cập protected resource, Basic/Bearer invalid |
| `AuthenticationFailureHandler` | Xử lý **một lần thử login** đã được submit nhưng thất bại | Form POST login sai password |
| `AuthenticationSuccessHandler` | Điều hướng hoặc xử lý hậu đăng nhập thành công | Saved request redirect, login audit |
| `AccessDeniedHandler` | Xử lý permission denied cho principal đã xác thực | 403 thiếu role/scope/ownership |
| `AuthenticationProvider` | Kiểm chứng credential và tạo Authentication | PasswordEncoder, JwtDecoder/introspection |
| `RequestCache` | Lưu đích web user muốn mở trước login | HttpSessionRequestCache cho form, NullRequestCache cho API |

Thấy route `/admin` trả 403 **không có nghĩa EntryPoint cấu hình sai**. Có thể đã xác thực thành công nhưng thiếu authority. Cần kiểm tra `authorizeHttpRequests`, method security, tenant/ownership trong domain và `AccessDeniedHandler`. Ngược lại, API thiếu token trả 302 login HTML có thể là do bị match nhầm web chain hoặc form entry point.

### 8.1. Vì sao @ControllerAdvice thường không điều khiển 401?

Nhiều 401/403 xảy ra trong Servlet security filters **trước khi DispatcherServlet gọi controller**. `@ControllerAdvice` / `@ExceptionHandler` của MVC không đương nhiên bắt được security exception đã được filter xử lý. Đặt policy authentication response ở `exceptionHandling(...)`, `httpBasic(...)` hoặc `oauth2ResourceServer(...)` trong security chain đúng.

### 8.2. Custom filters và phạm vi bắt exception

Một custom filter đặt **trước** `ExceptionTranslationFilter` có thể ném lỗi trước khi bộ lọc dịch ngoại lệ bao được lời gọi. Nếu tự viết authentication filter, dùng đúng failure handling/entry point, không ném `RuntimeException("bad token")` rồi giả định framework tự trả 401. Kiểm tra thứ tự filter và response-commit để tránh ghi phản hồi hai lần.

## 9. Tùy biến JSON 401 mà vẫn giữ Bearer challenge

API đôi khi muốn JSON body có format nhất quán; nhưng đoạn này là **sai** nếu dùng một mình để thay Bearer EntryPoint:

```java
// SAI: mất thông tin WWW-Authenticate Bearer.
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
```

Cách an toàn hơn: **ủy quyền status/header cho Spring Security** và chỉ thêm body không chứa bí mật. Ví dụ class `JsonBearerEntryPoint` trong Spring Security 6.x (cần starter OAuth2 Resource Server):

```java
package com.example.security;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

public final class JsonBearerEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException error)
            throws IOException, ServletException {

        // Giữ đúng WWW-Authenticate và status theo BearerTokenError.
        delegate.commence(request, response, error);

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();
        String title = (status == 400)
            ? "Bad Request" : "Unauthorized";

        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");
        response.getWriter().write(
            "{\"type\":\"about:blank\",\"title\":\""
            + title + "\",\"status\":" + status + "}");
    }
}
```

Đây là **mảnh tích hợp Spring**, không phải app chạy bằng `javac` đơn lẻ. Class trên cố ý **không** echo `error.getMessage()` ra client. Delegate đã quyết định status dựa trên BearerTokenError nếu có; client vẫn nhận challenge.

Gắn vào `oauth2ResourceServer` của API chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(new JsonBearerEntryPoint())
    .jwt(Customizer.withDefaults()))
```

Nếu muốn cả nhánh `ExceptionTranslationFilter` sử dụng JSON EntryPoint, cấu hình `exceptionHandling(ex -> ex.authenticationEntryPoint(...))` tương ứng trên **API chain**. Kiểm tra bằng integration tests cả đường **thiếu token** và **token không hợp lệ**, vì các lỗi có thể đi qua handler khác nhau.

Đối với **403** của Bearer API, `BearerTokenAccessDeniedHandler` có thể cung cấp `WWW-Authenticate` với `insufficient_scope` khi thích hợp. Không ghi đè bằng một JSON 401 chỉ vì code muốn body đồng nhất. Nếu thêm custom body 403, dùng delegate AccessDeniedHandler và giữ nguyên header/status do nó tạo.

### 9.1. HttpStatusEntryPoint không phải default Bearer EntryPoint

`HttpStatusEntryPoint` có thể tạo một status cố định như 401:

```java
.exceptionHandling(ex -> ex.authenticationEntryPoint(
    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
```

Imports trong project:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
```

Đây là snippet phù hợp trong một số **custom protocol** nhưng **không đủ** để tạo `WWW-Authenticate` cho Basic/Bearer. HTTP authentication theo RFC 9110 yêu cầu challenge khi 401; Bearer RFC 6750 còn có `invalid_token`, `insufficient_scope` và các trạng thái khác. Ưu tiên entry point đúng scheme hoặc tự triển khai đầy đủ hợp đồng.

## 10. Thiết kế API lỗi rõ ràng cho client

**Không biến mọi trường hợp thành một câu “Unauthorized”.** Client cần phân biệt thiếu credential, token hết hạn, quyền không đủ, CSRF và lỗi ứng dụng:

- `401 Bearer`: token thiếu/invalid. Frontend có thể đề nghị login hoặc refresh một lần có kiểm soát theo OAuth grant.
- `403`: token đã được xác minh nhưng thiếu quyền. Không tự refresh vô hạn và không tự “thử lại” với một account khác chỉ để vượt policy.
- `400 invalid_request`: malformed Bearer usage phải được sửa ở client.
- `302 /login`: dành cho browser form flow; không bắt REST/mobile client follow HTML login chỉ để nhận 200.
- `429 Too Many Requests`: rate limiting cho login/token brute-force; không giả thành 401 mãi.
- `503` hoặc status vận hành theo policy: phụ thuộc hệ thống xác thực/IdP đang sự cố, không fail open, không khẳng định credential sai chỉ vì dịch vụ introspection đang timeout.

Nếu dùng Problem Details JSON, giữ status thực ở body/header nhất quán, không phản chiếu raw exception hay secrets, và đảm bảo `Cache-Control` phù hợp.

### 10.1. URL login và redirect phải an toàn

Một login entry point có thể redirect dựa trên configured `/login`. Không dùng raw `next` hoặc `Host`/`X-Forwarded-Host` làm login origin nếu không có trust boundary, kẻ tấn công có thể xây URL giả để lấy credential. Đối với proxy, canonical HTTPS origin được quản trị, forwarded headers chỉ từ proxy tin cậy. Saved request redirect sau login chỉ nên đến path/domain đã được xác minh.

Không bao giờ đặt raw Bearer access token, Basic password, refresh token hoặc cookie value trong `Location`, query hay log; URL có thể bị browser history/referrer/proxy lưu lại.

### 10.2. CORS preflight và CSRF

Preflight CORS `OPTIONS` từ browser thường không gửi bearer credential. Nếu API security chặn 401 trước khi CORS chạy, frontend thấy lỗi CORS thay vì chính sách auth. Cấu hình CORS với allowed origins/methods/headers rõ ràng ở Spring Security; không mở `permitAll("/api/**")` hay tắt security toàn ứng dụng để sửa.

CSRF và CORS khác nhau: browser session/cookie authentication cần chính sách CSRF. Với API **chỉ** dùng `Authorization: Bearer` do client thêm thủ công và không có cookie tự gửi, có thể chọn CSRF handling khác; phải dựa trên threat model, không máy móc tắt CSRF ở mọi chain.

## 11. Java 17 độc lập: mô phỏng chọn response

Chương trình sau chạy được bằng Java 17 và **không dùng Spring**. Nó giả định verifier đã xác định credential `MISSING`/`INVALID`/`VALID_BUT_DENIED`/`VALID_ALLOWED`, chỉ mô phỏng cách chọn response/challenge. Nó **không xác minh JWT, password, session, role thực tế**.

Lưu file `AuthenticationEntryPointDemo.java`:

```java
public class AuthenticationEntryPointDemo {

    enum Scheme { FORM, BASIC, BEARER }
    enum State { MISSING, INVALID, VALID_BUT_DENIED, VALID_ALLOWED }

    record Response(int status, String detail) {
        @Override
        public String toString() {
            return status + " " + detail;
        }
    }

    static Response respond(Scheme scheme, State state) {
        if (state == State.VALID_ALLOWED) {
            return new Response(200, "OK");
        }

        if (state == State.VALID_BUT_DENIED) {
            return scheme == Scheme.BEARER
                ? new Response(403,
                    "WWW-Authenticate=Bearer error=\"insufficient_scope\"")
                : new Response(403, "Forbidden");
        }

        return switch (scheme) {
            case FORM -> new Response(302, "Location=/login");
            case BASIC -> new Response(401,
                "WWW-Authenticate=Basic realm=\"study\"");
            case BEARER -> state == State.MISSING
                ? new Response(401, "WWW-Authenticate=Bearer")
                : new Response(401,
                    "WWW-Authenticate=Bearer error=\"invalid_token\"");
        };
    }

    public static void main(String[] args) {
        System.out.println("FORM missing: " +
            respond(Scheme.FORM, State.MISSING));
        System.out.println("BASIC missing: " +
            respond(Scheme.BASIC, State.MISSING));
        System.out.println("BEARER missing: " +
            respond(Scheme.BEARER, State.MISSING));
        System.out.println("BEARER invalid: " +
            respond(Scheme.BEARER, State.INVALID));
        System.out.println("BEARER denied: " +
            respond(Scheme.BEARER, State.VALID_BUT_DENIED));
        System.out.println("FORM denied: " +
            respond(Scheme.FORM, State.VALID_BUT_DENIED));
        System.out.println("BASIC allowed: " +
            respond(Scheme.BASIC, State.VALID_ALLOWED));
    }
}
```

Lệnh:

```bash
javac AuthenticationEntryPointDemo.java
java AuthenticationEntryPointDemo
```

Stdout chính xác:

```text
FORM missing: 302 Location=/login
BASIC missing: 401 WWW-Authenticate=Basic realm="study"
BEARER missing: 401 WWW-Authenticate=Bearer
BEARER invalid: 401 WWW-Authenticate=Bearer error="invalid_token"
BEARER denied: 403 WWW-Authenticate=Bearer error="insufficient_scope"
FORM denied: 403 Forbidden
BASIC allowed: 200 OK
```

**Giải thích:** FORM chưa login được redirect; Basic/Bearer trả challenge; token sai nhận `invalid_token`; caller có credential hợp lệ nhưng thiếu scope bị 403; user thiếu quyền form cũng bị 403. Dòng 200 mô phỏng **controller bình thường đã được tiếp tục**, không phải EntryPoint cấp 200.

**Giới hạn:** demo không mô phỏng `ExceptionTranslationFilter`/RequestCache/anonymous/remember-me, Basic filter, JWT signature, CORS, CSRF hoặc Spring Security thực. Trong production phải dựa trên framework và validator đúng thay vì copy mô hình `switch` này vào filter.

## 12. Kiểm thử đúng luồng với curl

Dùng HTTPS và IdP thật trong môi trường test. Đây là các lệnh tham khảo, không phát credential thật tới domain ví dụ:

```bash
# Không token: dự kiến 401 + WWW-Authenticate Bearer.
curl -i https://api.example.org/api/orders

# Token invalid: dự kiến 401 + Bearer invalid_token.
curl -i -H 'Authorization: Bearer not-a-real-token' \
  https://api.example.org/api/orders

# Token hợp lệ, thiếu scope: dự kiến 403.
curl -i -H 'Authorization: Bearer TEST_READ_ONLY_TOKEN' \
  https://api.example.org/api/admin/reports

# Browser không session: có thể nhận 302 Location /login.
curl -i https://app.example.org/profile
```

Cần có API triển khai thực, endpoint, issuer/JWKS và token hợp lệ ở case thứ ba. Nếu dùng `curl -L`, client sẽ tự follow redirect, khiến bạn thấy `200` của trang login cuối cùng và bỏ sót `302` ban đầu. Khi kiểm thử entry point, trước hết dùng `curl -i` **không** bật follow redirects.

## 13. Kiểm thử Spring Security và failure paths

Có thể dùng Spring Security Test/MockMvc trong Spring Boot:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Snippet trong test class có `MockMvc mvc`, endpoints và test application context:

```java
mvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "WWW-Authenticate",
        org.hamcrest.Matchers.startsWith("Bearer")));

mvc.perform(get("/profile"))
    .andExpect(status().is3xxRedirection());
```

Imports tùy test:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
```

Để mô phỏng bearer đã được xác thực nhưng thiếu scope với `spring-security-test`:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_read"))))
    .andExpect(status().isForbidden());
```

Thêm imports:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

Đây là **test snippets**, không phải file Java độc lập. `jwt()` là testing postprocessor, không tự sinh JWT ký bởi IdP. Test application context có thể còn cần `JwtDecoder` test bean hoặc issuer config phù hợp để khởi động. Ngoài mock tests, nên integration-test JWT thật (chữ ký/`iss`/`aud`/`exp`) với test IdP/JWK.

### 13.1. Ma trận trường hợp bắt buộc

| Test | Kết quả kỳ vọng |
|---|---|
| Browser anonymous gọi protected page | 302 login page đúng, không nhận Bearer JSON |
| Browser đã auth nhưng thiếu role | 403, không redirect login loop |
| Basic client thiếu credentials | 401 + `WWW-Authenticate: Basic` |
| Basic client sai password | 401 challenge, không lộ tài khoản |
| API Bearer thiếu token | 401 + `WWW-Authenticate: Bearer` |
| API Bearer token hết hạn | 401 invalid_token |
| API Bearer JWT giả/sai issuer/sai audience | Không xác thực, thường 401 |
| API Bearer đúng token nhưng thiếu scope | 403; có thể header insufficient_scope |
| API Bearer đủ scope | Request qua filter; business authorization vẫn áp dụng |
| GET /api/public không token | Cho đi tiếp dù `/api/**` có security chain |
| GET /api/public với invalid Bearer | Có thể bị authentication filter từ chối; test rõ |
| Form login POST sai password | FailureHandler xử lý, không nhầm EntryPoint |
| CSRF thiếu ở form POST | Bị chặn theo CSRF policy |
| API CORS preflight hợp lệ | CORS được xử lý, không auth challenge sai |
| JSON Bearer entrypoint tùy biến | Status/header challenge còn nguyên, body trung tính |
| Hai security chains bị đảo thứ tự | Test phát hiện API bị form redirect |
| Login page tự bảo vệ | Test phát hiện vòng lặp 302 |
| Saved request redirect tới external URL giả | Không chuyển hướng ra domain tùy ý |
| Authorization header/cookie trong log | Không xuất hiện secret |
| Custom filter ném exception quá sớm | Phản hồi rõ và không double write |
| Nhiều nodes/proxies | 401/403/302 nhất quán, không lộ internal host |

### 13.2. Kiểm thử hai đường 401 riêng

**Đường A:** không có `Authorization`, `AuthorizationFilter` yêu cầu xác thực → `ExceptionTranslationFilter` chọn EntryPoint.

**Đường B:** client gửi Bearer JWT sai chữ ký, filter xác thực thất bại ngay → handler/EntryPoint của Resource Server.

Nếu chỉ kiểm tra A, cấu hình tùy biến có thể vẫn khiến B trả HTML lỗi, JSON khác hoặc thiếu `WWW-Authenticate`. Thêm trường hợp **token valid nhưng role/scope thiếu** để bảo đảm 403 vẫn đi qua AccessDeniedHandler, không bị đổi thành 401.

## 14. Các lỗi cần tránh

| Lỗi | Hậu quả | Giải pháp |
|---|---|---|
| API Bearer trả 302 tới HTML login | REST client không hiểu, retry/redirect lỗi | Chain API riêng, Bearer EntryPoint |
| Chỉ có 401 JSON nhưng thiếu `WWW-Authenticate` | Vi phạm HTTP challenge semantics | Delegate cho Basic/Bearer EntryPoint |
| Authenticated user thiếu role lại bị 401 | Client login lại vô hạn | 403/AccessDeniedHandler và policy đúng |
| Anonymous gọi API bị 403 không challenge | Client không biết cách xác thực | EntryPoint 401 + scheme |
| Form POST password sai xử lý qua nhầm handler | Flow không đúng UX/security | AuthenticationFailureHandler |
| Tùy biến ở `@ControllerAdvice` | Lỗi filter xảy ra trước MVC, không có hiệu lực | Configure handlers trong SecurityFilterChain |
| Lấy raw `authException.getMessage()` để gửi client | Rò issuer/token/internal config | Body code trung tính, audit đã redact |
| Dùng `HttpStatusEntryPoint` thay Bearer delegate | Mất challenge và error semantics | `BearerTokenAuthenticationEntryPoint` |
| `/login` yêu cầu authenticated | Redirect loop | PermitAll login và assets |
| Dựa vào Accept header để chọn scheme | Bị client/proxy thay đổi, trả sai contract | Cố định API path/chain |
| Dùng `permitAll` để “bỏ hết filters” | Invalid bearer ở public route vẫn 401 | Hiểu thứ tự filter, test intentional behavior |
| Tắt CSRF toàn bộ để API chạy | Web cookie endpoints dễ CSRF | Tách chains, chỉ tắt sau threat model |
| Bỏ verify JWT audience | Dùng token cấp cho API khác | Validate issuer, audience, signature, time |
| Ghi token vào URL/log/redirect | Lộ bearer credential | Authorization header qua TLS, redaction |
| Thiếu kiểm tra quyền từng resource | Token hợp lệ nhưng BOLA/IDOR | Domain authorization/tenant/ownership |

## 15. Checklist triển khai production

1. Xác định rõ client dùng form, Basic, OAuth Bearer hay custom challenge.
2. Chọn EntryPoint phù hợp scheme; giữ `WWW-Authenticate` khi response 401.
3. Định nghĩa 401 cho authentication thiếu/invalid, 403 cho permission denied, 302 cho form redirect.
4. Hiểu `ExceptionTranslationFilter` khác các authentication filters/FailureHandler.
5. Cấu hình `SecurityFilterChain` và `@Order` sao cho API không bị browser fallback bắt nhầm.
6. Giữ CSRF ở web session, cân nhắc stateless API riêng; xử lý CORS preflight đúng.
7. Cấu hình JWT decoder issuer/audience/signature/time, không dùng EntryPoint để “sửa” token sai.
8. Kiểm soát `/login`, request cache, saved redirect, không mở open redirect hoặc login loop.
9. Không log Authorization/JWT/password, không gửi exception details ra ngoài.
10. Kiểm tra 401 thiếu token **và** 401 token sai, cộng 403 thiếu scope/role trong mỗi release.
11. Dùng `curl -i` không follow redirect khi debug, xem cả `WWW-Authenticate` và `Location`.
12. Giữ test tích hợp với actual IdP/keys và security filters, không chỉ unit test mô phỏng.
13. Theo dõi thống kê 401/403 theo API route và error reason đã loại bỏ bí mật.
14. Khi nâng Spring Security, kiểm tra version-specific defaults và tiếp tục chạy test protocol.

## 16. Câu hỏi tự kiểm tra

**1.** `AuthenticationEntryPoint` có xác minh mật khẩu hay chữ ký JWT không?  
**Đáp:** Không, nó tạo HTTP response yêu cầu credential. AuthenticationProvider/filter/decoder thực hiện verification.

**2.** Browser chưa login gọi `GET /private`, một cách phản hồi hợp lý?  
**Đáp:** Với form login, `302 Location: /login`.

**3.** REST bearer API thiếu Authorization, một cách phản hồi hợp lý?  
**Đáp:** `401 WWW-Authenticate: Bearer`.

**4.** Token hợp lệ nhưng thiếu scope, có nên gọi EntryPoint để đăng nhập lại?  
**Đáp:** Không; thông thường AccessDeniedHandler trả 403 và có thể mang `insufficient_scope`.

**5.** Vì sao `Authentication != null` chưa chứng minh người dùng đã login thật?  
**Đáp:** `AnonymousAuthenticationToken` và cơ chế remember-me/partial auth có thể được biểu diễn trong security context; phải dựa vào policy/AuthenticationTrustResolver phù hợp.

**6.** Form login gửi password sai sẽ luôn đi qua `ExceptionTranslationFilter`?  
**Đáp:** Không. `UsernamePasswordAuthenticationFilter` thường dùng `AuthenticationFailureHandler`.

**7.** Tại sao một 401 JSON hợp lệ về cú pháp vẫn có thể sai giao thức?  
**Đáp:** Nếu là HTTP Basic/Bearer mà không có `WWW-Authenticate`, client không có authentication challenge cần thiết theo HTTP.

**8.** `curl -L` có thể làm bạn hiểu nhầm status 302 ra sao?  
**Đáp:** Nó theo redirect tới trang login và chỉ nhìn response cuối, có thể là 200; dùng `curl -i` để xem status gốc.

**9.** `permitAll("/api/public")` có luôn bỏ qua bearer validation không?  
**Đáp:** Không, auth filter có thể xử lý token chủ động gửi vào và từ chối token hỏng trước authorization.

**10.** Khi cần khác nhau giữa JSON API và browser, có nên check `Accept: application/json` để quyết định ai đã authenticated?  
**Đáp:** Không. Tách rõ security chains và xác minh bằng chứng thực; Accept chỉ mô tả định dạng representation.

## Tài liệu tham khảo

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationEntryPoint`, `AuthenticationManager` và authentication filters.
- [Spring Security — Servlet Architecture/ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html): security exception translation, `RequestCache`, `AccessDeniedHandler`.
- [Spring Security 6.5 — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): `commence` và HTTP response contract.
- [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationEntryPoint` và filter failure.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `LoginUrlAuthenticationEntryPoint`, login failures và success.
- [Spring Security — OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): bearer challenge/error responses.
- [Spring Security 6.5 — DelegatingAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationEntryPoint.html): chọn entry point bằng `RequestMatcher`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `401`, `WWW-Authenticate` và `403`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): `invalid_request`, `invalid_token`, `insufficient_scope`.
