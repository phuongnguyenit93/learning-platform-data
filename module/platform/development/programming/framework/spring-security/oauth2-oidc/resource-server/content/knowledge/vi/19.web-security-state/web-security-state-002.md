# SessionCreationPolicy.STATELESS và các thành phần có thể tạo trạng thái

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một cấu hình thường gặp là:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Nhiều người hiểu câu lệnh này thành: “Ứng dụng không bao giờ có `HttpSession`, không tạo cookie, không giữ bất kỳ trạng thái nào và mọi request đều hoàn toàn độc lập”. **Đó là kết luận quá rộng.**

Ý nghĩa cốt lõi của `SessionCreationPolicy.STATELESS` là **Spring Security không tạo `HttpSession` để duy trì quá trình xác thực và không dùng `HttpSession` để lấy lại `SecurityContext`**. Nó không cấm controller, servlet filter khác, Spring MVC, CSRF repository, OAuth2 Login, thư viện bên thứ ba hoặc hạ tầng bên ngoài tạo/lưu trạng thái theo những cơ chế riêng.

Một REST API chỉ dùng bearer access token trong header `Authorization` thường **không cần lưu authentication vào HTTP session**: mỗi request cung cấp token và được xác minh lại. Tuy nhiên vẫn có thể tồn tại các loại trạng thái khác như cache JWKS, cache introspection, database, rate limiting, CSRF token, login state, cookie hoặc HTTP session do một thành phần khác tạo ra.

> **Thông điệp chính:** `STATELESS` là một **chính sách quản lý session của Spring Security**, không phải lệnh bảo đảm “toàn bộ ứng dụng không có state”. Muốn một endpoint thật sự không tạo `HttpSession`, cần xem cả filter chain, các thành phần Spring Security khác và toàn bộ luồng xử lý Servlet/Spring MVC.

Bài học phân biệt bốn chính sách tạo session, vai trò của `SecurityContextRepository` và `RequestCache`, những nguồn tạo trạng thái tiềm ẩn, cách tổ chức REST Resource Server song song với OIDC Login, cùng các phương pháp kiểm thử/chẩn đoán `JSESSIONID`.

## 1. Bắt đầu từ yêu cầu của OAuth 2.0 Resource Server

Với JWT bearer token, client thường gọi API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Resource Server xác minh chữ ký, issuer, audience, thời hạn, scope và những điều kiện khác theo contract. Nếu token hợp lệ, Spring Security tạo `Authentication` trong `SecurityContext` để các component của **request hiện tại** dùng.

~~~text
Request A: Authorization: Bearer token-123
   |
   v
BearerTokenAuthenticationFilter
   |
   v
JwtDecoder + claim validators
   |
   v
SecurityContext(Authentication for A)
   |
   v
AuthorizationFilter -> Controller -> Response
   |
   v
Kết thúc request: không lưu Authentication vào HttpSession

Request B: Authorization: Bearer token-123
   |
   v
Xác minh token theo policy cho request B
   |
   v
SecurityContext(Authentication for B)
   |
   v
Authorization -> Response
~~~

Trong mô hình này, Resource Server **không cần ghi `Authentication` vào session** để nhận ra cùng một client ở request kế tiếp. Credential là bearer token được gửi lại.

Điều tương tự có thể áp dụng cho opaque token:

~~~text
Bearer opaque token -> OpaqueTokenIntrospector -> Authentication
```

Khác biệt chính là cách token được xác minh: JWT thường được kiểm tra cục bộ theo chữ ký/JWKS, còn opaque token thường gọi introspection endpoint. **Cả hai đều có thể dùng `SessionCreationPolicy.STATELESS`**, nhưng introspection có network call và có thể có cache.

### 1.1. Stateless authentication không có nghĩa token “không còn trạng thái” ở mọi nơi

Authorization Server có thể quản lý:

- Client registration, consent và quyền người dùng.
- Refresh tokens hoặc phiên đăng nhập phía AS.
- Token revocation hoặc token-introspection state.
- Key rotation, JWKS và metadata.
- Role/permission data và policy.
- Audit events hoặc rate limits.

Resource Server cũng có thể dùng cache public keys, kết quả introspection, membership, denylist, rate limiter hoặc database để phân quyền. **Những dữ liệu này không nhất thiết là HTTP session**.

Một API có thể stateless ở **tầng lưu `SecurityContext`** nhưng vẫn sử dụng state nghiệp vụ và hạ tầng.

## 2. Bốn giá trị SessionCreationPolicy

Spring Security có enum `org.springframework.security.config.http.SessionCreationPolicy`.

| Chính sách | Hành vi dự kiến của Spring Security | Điểm cần phân biệt |
|---|---|---|
| `ALWAYS` | Luôn tạo một `HttpSession` | Phù hợp một số flow session-oriented |
| `IF_REQUIRED` | Chỉ tạo session khi Spring Security cần | Một flow login/request cache có thể khiến session xuất hiện |
| `NEVER` | Spring Security không tự tạo session, **nhưng có thể dùng session đã tồn tại** | Không tương đương `STATELESS` |
| `STATELESS` | Spring Security không tạo `HttpSession` và **không dùng session để lấy `SecurityContext`** | Không cấm code ngoài phạm vi này tạo session |

Ý nghĩa được mô tả trong Javadoc của `SessionCreationPolicy` và tài liệu session management của Spring Security.

### 2.1. Phân biệt `NEVER` và `STATELESS`

Đây là sự khác nhau đặc biệt quan trọng.

Với `NEVER`:

~~~text
Request tới API
    |
    +-- Đã có HttpSession do thành phần khác tạo?
             |
             +-- Có -> Spring Security có thể dùng session đó
             |
             +-- Không -> Spring Security không chủ động tạo
~~~

Với `STATELESS`:

~~~text
Request tới API
    |
    +-- Có HttpSession hay không?
             |
             +-- Spring Security không lấy SecurityContext từ đó
             |
             +-- Authentication của bearer token được xác thực theo request
```

Nếu mục tiêu là **không dựa vào session để xác thực API**, `STATELESS` diễn đạt mục tiêu rõ hơn `NEVER`.

Tuy nhiên nếu controller vẫn gọi `request.getSession()`, Servlet container **có thể tạo session** ngay cả khi Security chain cấu hình `STATELESS`.

### 2.2. `IF_REQUIRED` không phải lúc nào cũng tạo session

Nếu một request không kích hoạt tính năng yêu cầu session, có thể không có `JSESSIONID` ngay cả khi policy là `IF_REQUIRED`. Ngược lại, request cache, login hoặc CSRF có thể làm session xuất hiện khi phù hợp với flow.

Không thể kết luận một chain stateful hay stateless chỉ nhìn một response không có cookie. Phải xem cấu hình và các đường xử lý thật.

## 3. `SecurityContextHolder` có “state” nhưng không đồng nghĩa HTTP session

Spring Security cho phép lấy authentication:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` thường dùng chiến lược lưu context gắn với luồng đang thực thi request (ví dụ `ThreadLocal`). Trong lúc request chạy, các filter/controller/service có thể đọc cùng authentication để phân quyền.

Đây là **request-processing state trong bộ nhớ**, không phải bằng chứng đã tạo một `HttpSession` hay cookie.

### 3.1. Hai loại trạng thái khác nhau

| Khái niệm | Vòng đời | Công dụng |
|---|---|---|
| `SecurityContext` trong request hiện tại | Gắn với quá trình xử lý request và security context lifecycle | Giúp controller/service thấy principal và authorities |
| `HttpSession` | Thường tồn tại qua nhiều request, được định danh qua session ID | Lưu dữ liệu phiên, có thể chứa security context nếu cấu hình cho phép |
| JWT bearer token phía client | Sống tới khi hết hạn/thu hồi theo policy | Credential được client gửi mỗi request |
| JWKS cache | Giữ keys một thời gian | Tăng hiệu năng xác minh chữ ký |
| Introspection cache | Giữ kết quả kiểm tra token nếu cấu hình | Giảm network call nhưng có rủi ro stale |
| Redis/DB business state | Tùy nghiệp vụ | Order, tenant, permissions, rate limits |

Khi `STATELESS`, việc `SecurityContextHolder.getContext()` có `Authentication` **là bình thường**. Nó không có nghĩa `SecurityContext` đã được lưu trong `HttpSession`.

### 3.2. Đừng bỏ qua lifecycle khi tự tạo filter

Một custom filter không nên đưa `Authentication` vào static variable hoặc `ThreadLocal` riêng rồi bỏ mặc nó sau request. Spring Security cung cấp cơ chế quản lý và dọn dẹp `SecurityContext` theo filter chain.

Nếu tự tạo authentication hoặc xử lý async threads, cần dùng cơ chế propagation/lifecycle phù hợp. Chuyển `SecurityContext` qua `@Async`, executor hoặc reactive boundary là một vấn đề riêng, **không phải lý do tự bật HTTP session**.

## 4. `SecurityContextRepository` quyết định lưu security context ở đâu

Spring Security có interface `SecurityContextRepository`. Những implementation thường gặp:

| Repository | Mục đích |
|---|---|
| `HttpSessionSecurityContextRepository` | Lấy/lưu `SecurityContext` trong `HttpSession` |
| `RequestAttributeSecurityContextRepository` | Dùng request attributes, có ích với dispatcher khác trong cùng request |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository |
| `NullSecurityContextRepository` | Không load/save `SecurityContext` qua repository |

Khi cấu hình `SessionCreationPolicy.STATELESS` theo luồng hỗ trợ thông thường, Spring Security dùng **`NullSecurityContextRepository`** để không duy trì authentication qua HTTP session.

~~~text
JWT bearer request
   |
   v
Authenticated SecurityContext
   |
   +-- Controller dùng trong request hiện tại
   |
   +-- NullSecurityContextRepository:
       không lưu context để khôi phục ở request sau
```

### 4.1. `NullSecurityContextRepository` làm gì?

Nó **không lưu authentication** qua request. Trong các request sau, Resource Server cần xác minh token được gửi lại.

Không phải vì không có session mà API phải từ chối request thứ hai. Nếu client vẫn gửi token hợp lệ ở request thứ hai, nó có thể được xác thực bình thường.

### 4.2. Phân biệt `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter`

Trong kiến trúc Spring Security hiện đại:

- `SecurityContextHolderFilter` đọc security context từ repository và làm nó sẵn có cho request; **không tự động lưu lại**.
- `SecurityContextPersistenceFilter` của các luồng/phiên bản cũ có cơ chế lưu context khi cần sau request.
- Nếu code custom muốn lưu authentication giữa các request, nó phải dùng `SecurityContextRepository.saveContext(...)` theo cấu hình tương ứng.

Tài liệu Spring Security 6 giải thích rằng `SecurityContextHolderFilter` là lựa chọn mặc định mới trong nhiều luồng; **không nên cấu hình cả hai filter persistence và holder song song**.

Với REST bearer stateless, ta **không muốn** lưu context vào `HttpSession` chỉ vì authentication thành công. Nếu ai đó tự thay repository thành `HttpSessionSecurityContextRepository` hoặc cấu hình persistence khác, kết luận “chain này không dùng session” có thể không còn đúng.

### 4.3. Không tự kết luận từ tên “stateless”

Giả sử code custom:

~~~java
.securityContext(context -> context
    .securityContextRepository(
        new HttpSessionSecurityContextRepository()))
~~~

được kết hợp với những configuration khác. Khi đó có thể phát sinh hành vi lưu context vào session, tùy điểm được gắn repository và authentication filter. Cấu hình này **mâu thuẫn với mục tiêu bearer-only stateless** nếu không có lý do rõ ràng.

Với ứng dụng nhiều `SecurityFilterChain`, một chain khác vẫn có thể dùng `HttpSessionSecurityContextRepository` để phục vụ browser login. Điều đó hợp lệ nếu phạm vi chain được tách đúng.

## 5. Cấu hình Spring Security Resource Server stateless

Dưới đây là một cấu hình **REST API nhận bearer JWT trong header**, không dựa vào form login hay session cookie.

### 5.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 5.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`issuer-uri` và audience cần khớp contract của Authorization Server. `audiences` được Spring Boot hỗ trợ trong nhiều phiên bản hiện đại; nếu version của dự án không có property tương ứng, dùng audience validator tùy chỉnh.

### 5.3. `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Chỉ phù hợp nếu API sử dụng bearer header,
            // không xác thực bằng cookie tự gửi của browser.
            .csrf(AbstractHttpConfigurer::disable)

            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Thể hiện rõ: không lưu request vào HttpSession.
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))

            .build();
    }
}
~~~

**Giải thích từng phần:**

- `SessionCreationPolicy.STATELESS`: Spring Security không tạo `HttpSession` để giữ authentication và không lấy `SecurityContext` từ session.
- `NullRequestCache`: không lưu request bị chặn để redirect lại sau đăng nhập. Với cấu hình stateless thông dụng, Spring Security đã có xử lý request cache tương ứng; khai báo ở đây nhấn mạnh mục tiêu.
- `oauth2ResourceServer(...jwt())`: xác thực bearer JWT theo mỗi request.
- `hasAuthority(...)`: endpoint cần scope đã được AS cấp.
- `anyRequest().denyAll()`: endpoint chưa được mô tả không tự mở quyền.
- `csrf.disable()`: **chỉ đúng trong bối cảnh ví dụ bearer-only**; không phải yêu cầu bắt buộc của `STATELESS`.

Đừng sao chép câu lệnh disable CSRF sang ứng dụng dùng session cookie/Browser OAuth Login mà không đánh giá nguy cơ.

### 5.4. Không nhất thiết cấu hình `NullSecurityContextRepository` bằng tay

Spring Security xử lý repository thích hợp khi áp dụng `STATELESS` theo luồng hỗ trợ. Trong nhiều ứng dụng, không cần thêm:

~~~java
.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository()))
~~~

Tùy chỉnh thủ công chỉ nên dùng khi có lý do về integration hoặc cần kiểm soát một authentication filter cụ thể. Nếu vừa override repository vừa dùng nhiều loại login, cần hiểu mỗi filter dùng repository nào và có lưu authentication hay không.

## 6. Stateless không phải “không có HttpSession ở toàn ứng dụng”

Đây là phần thường gây nhầm lẫn nhất.

### 6.1. `HttpServletRequest#getSession()` vẫn có thể tạo session

Servlet API cho phép:

~~~java
HttpSession session = request.getSession();
~~~

Theo Servlet contract, `getSession()` tương đương lấy hoặc tạo một session khi chưa có. Bởi vậy:

~~~java
request.getSession().setAttribute("cart", cart);
~~~

có thể tạo `HttpSession` trong controller, service hoặc filter dù Spring Security chain đã cấu hình `STATELESS`.

Nếu chỉ muốn kiểm tra **session đã tồn tại**:

~~~java
HttpSession session = request.getSession(false);
~~~

`getSession(false)` **không tạo session mới**. Nó trả `null` khi request chưa có session hợp lệ.

### 6.2. Ví dụ controller vô tình tạo session

~~~java
package com.example.orders.api;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionDemoController {

    @GetMapping("/demo/create-session")
    public String createSession(HttpServletRequest request) {
        HttpSession session = request.getSession();
        session.setAttribute("demo", "created");
        return "session-created";
    }
}
~~~

**Đây là ví dụ cố tình tạo state**, không phải code khuyến nghị đặt trong một API stateless. Nếu request đi tới controller này, session có thể xuất hiện và container có thể phát `Set-Cookie: JSESSIONID=...`.

Trong một REST Resource Server yêu cầu hoàn toàn không tạo HTTP session, cần tránh logic như vậy hoặc tách nó sang phần web/session-oriented riêng.

### 6.3. Filter/thư viện cũng có thể gọi `getSession()`

Một custom servlet filter, SDK, view resolver, thư viện legacy hoặc component ghi flash message có thể tạo session mà developer không nhìn thấy trong `SecurityConfig`.

Sơ đồ trách nhiệm:

~~~text
Request
  |
  +-- Spring Security STATELESS
  |      +-- không tạo/lấy auth SecurityContext từ HttpSession
  |
  +-- Servlet Filter khác
  |      +-- có thể gọi request.getSession()
  |
  +-- Spring MVC
  |      +-- có thể xử lý @SessionAttributes / flash attributes
  |
  +-- Controller / service
  |      +-- có thể gọi request.getSession()
  |
  +-- View / library khác
         +-- có thể phát sinh session hoặc cookie riêng
```

**Không thể suy ra toàn bộ request không có state chỉ từ một dòng `.sessionCreationPolicy(STATELESS)`.**

## 7. `RequestCache` có thể lưu request chờ đăng nhập

Trong ứng dụng browser, nếu người dùng truy cập một URL riêng tư khi chưa đăng nhập, Spring Security có thể nhớ request ban đầu:

~~~text
GET /reports/private
   |
   +-- Chưa đăng nhập
   |
   +-- HttpSessionRequestCache lưu SavedRequest
   |
   +-- Redirect tới login
   |
   +-- Login thành công
   |
   +-- Redirect trở lại /reports/private
~~~

`HttpSessionRequestCache` lưu dữ liệu vào `HttpSession` khi request cần được ghi nhớ.

Trong REST API sử dụng bearer token, thông thường không muốn redirect sang form login hoặc lưu request chờ đăng nhập. Client cần nhận `401` với Bearer challenge hoặc lỗi phù hợp, sau đó tự gửi token hợp lệ trong request tiếp theo.

### 7.1. `NullRequestCache` giải quyết điều gì?

~~~java
.requestCache(cache -> cache
    .requestCache(new NullRequestCache()))
~~~

`NullRequestCache` không lưu request và không khôi phục saved request. Điều đó tránh một nguồn tạo session liên quan đăng nhập tương tác.

Theo tài liệu Spring Security, cấu hình `STATELESS` thông dụng đã ngăn request được lưu vào session. Việc khai báo `NullRequestCache` tường minh giúp đọc config rõ hơn và bảo vệ thiết kế khi cần custom nhiều thành phần.

### 7.2. Không nhầm saved request với caching dữ liệu API

`RequestCache` của Spring Security là cơ chế lưu **request để chuyển hướng sau authentication**, không phải HTTP response cache hay cache nghiệp vụ. Một `Cache-Control` header hoặc Redis cache không đồng nghĩa sử dụng `HttpSessionRequestCache`.

Nếu hệ thống có caching reverse proxy, CDN hoặc Spring Cache, cần xem chính sách bảo vệ dữ liệu riêng, không chỉ `SessionCreationPolicy`.

## 8. CSRF có thể tạo state dù authentication stateless

**`SessionCreationPolicy.STATELESS` không tự động tắt hoặc loại bỏ mọi cơ chế CSRF.** CSRF là một lớp bảo vệ độc lập, phụ thuộc loại credential mà browser tự động gửi tới server.

Spring Security Servlet hỗ trợ:

- `HttpSessionCsrfTokenRepository`: lưu expected CSRF token trong `HttpSession`.
- `CookieCsrfTokenRepository`: lưu token trong cookie.
- Repository tùy chỉnh: lưu ở nguồn do ứng dụng xác định.

Theo tài liệu Spring Security, repository mặc định thông dụng là **`HttpSessionCsrfTokenRepository`**. Spring Security 6 dùng cơ chế **deferred CSRF token loading**, nên session không nhất thiết bị tải hoặc tạo trên mọi GET; session có thể được cần khi token thực sự được truy xuất/sinh/lưu.

### 8.1. Ví dụ cơ chế có thể tạo session

Một ứng dụng hiển thị form HTML và cần CSRF token:

~~~html
<form method="post" action="/profile/update">
  <input type="hidden" name="_csrf" value="...">
  <button type="submit">Save</button>
</form>
~~~

Nếu expected token lưu bằng `HttpSessionCsrfTokenRepository`, lúc sinh/lưu token hoặc xử lý một request có token, session có thể được sử dụng.

**Vì vậy API có `STATELESS` nhưng vẫn bật một CSRF flow dựa trên session không bảo đảm không có `JSESSIONID`.** Phải xem cụ thể `CsrfTokenRepository` và những request làm token được materialize.

### 8.2. Khi nào có thể disable CSRF?

Với API thuần:

~~~text
Client chủ động gửi Authorization: Bearer <access-token>
Browser không tự động đính kèm credential xác thực
Không có session cookie/Basic authentication flow tự gửi
~~~

mô hình CSRF thường không giống app browser dùng cookie. Có thể cân nhắc tắt CSRF sau khi đánh giá toàn bộ cơ chế credential.

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

**Tuy nhiên:** API có thể stateless về `SecurityContext` nhưng **vẫn dễ bị CSRF** nếu bearer token hoặc credential khác được browser gửi tự động qua cookie. Stateless server không đồng nghĩa chống CSRF.

### 8.3. Cookie-based authentication và CSRF

Nếu access token được đặt trong cookie `HttpOnly`, browser thường tự gửi cookie cho request cùng site và trong những điều kiện cross-site nhất định theo thuộc tính cookie. Cần xem **CSRF protection, `SameSite`, Origin/Referer policy, CORS và cách cookie được dùng**.

Đừng suy luận:

~~~text
JWT nằm trong cookie -> JWT là stateless -> không có CSRF
~~~

Hai câu sau không suy ra câu đầu. Token trong cookie có thể là credential tự động gửi, nên threat model khác với bearer header do client chủ động gắn.

### 8.4. `CookieCsrfTokenRepository` vẫn là state ở client

Chuyển từ session CSRF repository sang cookie repository có thể loại bỏ một số nhu cầu sử dụng `HttpSession`, nhưng expected CSRF token lúc đó vẫn tồn tại ở **cookie phía client**.

Đây là **state**, chỉ khác nơi lưu. Nó cũng không xóa những yêu cầu bảo vệ CSRF, XSS hoặc kiểm soát cách JavaScript đọc token tùy thiết kế.

## 9. OAuth2 Login / OIDC Login thường cần trạng thái tạm thời

Một **OAuth2/OIDC Client** có flow trình duyệt khác một **Resource Server** chỉ nhận access token.

Ví dụ Authorization Code + PKCE/OIDC:

~~~text
Browser truy cập ứng dụng
       |
       v
Ứng dụng redirect tới Authorization Server
       |
       +-- lưu OAuth2 authorization request / state
       +-- PKCE code_verifier cần được khôi phục an toàn
       +-- OIDC nonce có thể cần đối chiếu
       |
       v
User đăng nhập tại Authorization Server
       |
       v
Callback /login/oauth2/code/{registrationId}
       |
       +-- đối chiếu state/nonce theo flow
       +-- lấy authorization code
       +-- đổi code lấy tokens
       |
       v
Thiết lập trạng thái đăng nhập ứng dụng (tùy thiết kế)
~~~

Spring Security OAuth2 Login thường dùng `HttpSessionOAuth2AuthorizationRequestRepository` để lưu `OAuth2AuthorizationRequest` trong `HttpSession` giữa redirect và callback.

### 9.1. Đặt `STATELESS` cho OAuth2 Login một cách máy móc có thể làm hỏng flow

Nếu cùng chain:

~~~java
.oauth2Login(Customizer.withDefaults())
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

mà vẫn giữ authorization request repository dựa vào session, flow redirect/callback có thể bị lỗi do trạng thái tạm thời không được khôi phục hoặc do cách session được tạo/sử dụng không nhất quán với chính sách.

Đây không phải lỗi của JWT signature, mà là **mâu thuẫn kiến trúc**: OAuth2 Login cần giữ state/PKCE/nonce, còn bearer-only API không cần lưu login state vào session.

Giải pháp thường gặp:

1. **Tách `SecurityFilterChain`**: API stateless; browser login/session chain riêng.
2. Hoặc thiết kế **`AuthorizationRequestRepository` không dựa vào HTTP session** nhưng vẫn phải bảo vệ `state`, PKCE verifier, OIDC nonce và chống replay theo yêu cầu protocol.
3. Không vô hiệu hóa kiểm tra `state`/nonce chỉ để làm cho login “hoạt động” với `STATELESS`.

### 9.2. Stateless Resource Server và OIDC Client không phải vai trò giống nhau

Một ứng dụng có thể đóng cả hai vai trò, nhưng nên xác định:

| Vai trò | Credential thường gặp | Trạng thái cần thiết |
|---|---|---|
| Resource Server API | JWT/opaque bearer access token | Không bắt buộc session để lưu authentication |
| OIDC Client browser | Authorization Code/OIDC login, cookie/session hoặc BFF | Thường cần flow state, có thể có session |
| Authorization Server | Phát access/refresh token, consent, keys | Có nhiều state phía AS |
| Backend-for-Frontend | Cookie đăng nhập frontend, giữ access token phía server | Có thể cần server-side session/token store |

Đừng áp dụng một câu “tất cả ứng dụng OAuth2 phải stateless” cho mọi vai trò.

## 10. Ứng dụng vừa có REST API, vừa có OIDC Login

Một kiến trúc phổ biến là:

~~~text
/api/**         -> Bearer JWT Resource Server, stateless
/web/**         -> Browser OIDC Login, session/CSRF theo kiến trúc
/oauth2/**      -> OAuth2 authorization redirect
/login/**       -> OAuth2 Login callback hoặc login page
/actuator/**    -> Chính sách vận hành riêng
~~~

Có thể cấu hình **hai `SecurityFilterChain`** với thứ tự rõ ràng.

### 10.1. Chain API stateless

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giả định:** ví dụ này cần dependency của **OAuth2 Client** nếu bật `oauth2Login`:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
~~~

và client registration/provider configuration hợp lệ; code trên không tự có OAuth2 Login hoạt động nếu thiếu cấu hình IdP/redirect URI.

### 10.2. Vì sao chain thứ hai không đặt `STATELESS`?

Chain web dùng OAuth2 Login. Trạng thái authorization request/PKCE/OIDC nonce và session đăng nhập có thể cần được lưu qua redirect. Có thể dùng cấu hình mặc định phù hợp hoặc thiết kế state storage riêng.

CSRF cho browser chain cũng không bị tắt trong ví dụ, vì browser có thể dùng cookie.

### 10.3. Khi có nhiều chain, session vẫn có thể tồn tại

Nếu browser truy cập web chain và server tạo `HttpSession`, cookie `JSESSIONID` có thể được gửi ở request tới `/api/**` tùy cookie path/domain và hành vi browser.

Điều đó **không tự chứng minh** API chain đang dùng session để khôi phục authentication. Với cấu hình `STATELESS` đúng, API chain vẫn yêu cầu bearer token và không lấy security context từ session chỉ vì cookie đã tồn tại.

**Tuy nhiên:** phải test rằng API chain thật sự được chọn và không có cơ chế khác nhận session cookie như một credential hợp lệ.

### 10.4. Ranh giới `securityMatcher` rất quan trọng

Trong nhiều chain:

- `securityMatcher("/api/**")` quyết định **chain API áp dụng ở đâu**.
- `requestMatchers(...)` bên trong chain quyết định HTTP authorization cho request đã thuộc chain.
- `@Order` xác định chain nào được xét trước.
- `anyRequest()` trong một chain không bảo vệ mọi request ngoài phạm vi `securityMatcher` của nó.

Nếu chỉ có chain `/api/**` mà không có fallback cho phần khác, những URL không khớp có thể nằm ngoài filter chain của Spring Security. Hãy bảo đảm có chain phù hợp hoặc fallback policy.

## 11. Các thành phần có thể tạo `HttpSession` hoặc state khác

Bảng sau rất hữu ích khi thấy `Set-Cookie: JSESSIONID` dù API dùng `STATELESS`.

| Thành phần/cơ chế | Có thể tạo/lưu loại state gì? | Cần kiểm tra |
|---|---|---|
| Controller `request.getSession()` | `HttpSession` | Có đang dùng để lưu cart/user/flag không? |
| Servlet filter/custom interceptor | `HttpSession` | Có `getSession()` hoặc session attribute không? |
| `HttpSessionSecurityContextRepository` | `SecurityContext` trong session | Có override repo stateless không? |
| `HttpSessionRequestCache` | `SavedRequest` trong session | Có redirect/login flow hoặc cache request không? |
| `HttpSessionCsrfTokenRepository` | Expected CSRF token trong session | CSRF token có được load/generate không? |
| `HttpSessionOAuth2AuthorizationRequestRepository` | OAuth2 authorization request/state | Chain nào xử lý OAuth2 Login? |
| Form login / login success handler | Auth/session/saved request tùy config | Có đang bật login interactive không? |
| Session fixation strategy | Đổi session ID hoặc migrate session khi login | Có chain browser login nào không? |
| Session concurrency tracking | Session registry/tracking | Tính năng giới hạn concurrent login có bật? |
| Spring MVC `@SessionAttributes` | Model attributes trong session | Controller MVC có stateful không? |
| Bean `@SessionScope` | Dữ liệu bean theo session | Bean có được truy cập trong request? |
| Flash attributes và redirect | Flash map có thể được giữ qua request, thường liên quan session | Có dùng `RedirectAttributes.addFlashAttribute` không? |
| `SessionLocaleResolver` | Locale trong session | MVC locale strategy đang dùng gì? |
| JSP/view/third-party library | Session hoặc cookie tùy công nghệ | View technology có tự tạo session không? |
| Spring Session (Redis/JDBC) | Backing storage cho `HttpSession` | Có bean/filter thay servlet session storage không? |
| API gateway / reverse proxy | Cookie khác, sticky routing, cache | Cookie do proxy hay app phát? |
| Cache JWKS/introspection | Cache dữ liệu xác minh token | Không phải HTTP session, nhưng vẫn là state |
| Rate limiter, revocation list, ACL DB | Business/security state | Stateless authentication không loại bỏ |

**Một hàng trong bảng không có nghĩa thành phần luôn tạo session.** Ví dụ CSRF deferred loading có thể tránh chạm session trên GET thông thường; `@SessionAttributes` chỉ tác động khi controller thực sự dùng cơ chế đó; login success handler chỉ chạy khi login tương ứng diễn ra.

## 12. `Spring Session` và Redis không đồng nghĩa mọi API đang stateful authentication

Khi project dùng Spring Session, `HttpSession` có thể được lưu trong Redis hoặc JDBC thay vì chỉ trong bộ nhớ servlet container.

Ví dụ:

~~~text
Servlet request.getSession()
          |
          v
Spring Session wrapper
          |
          v
Redis / JDBC session repository
```

Điều này làm session có thể sống qua nhiều node và thay đổi cách quan sát metrics/cookie.

Nhưng nếu API bearer stateless **không gọi `getSession()` và không lưu `SecurityContext`**, việc project có dependency Spring Session không nhất thiết nghĩa API đó đang dùng session authentication.

Ngược lại, nếu một controller hoặc filter vô tình tạo session, nó có thể ghi state vào Redis. Kiểm tra Spring Session storage và events có thể giúp tìm nguồn phát sinh.

**Đừng giải quyết vấn đề bằng cách xóa Spring Session dependency bừa bãi** nếu ứng dụng còn có OIDC Login hoặc web area thật sự cần session.

## 13. `JSESSIONID` xuất hiện nghĩa là gì?

Servlet container thường dùng cookie `JSESSIONID` để định danh `HttpSession`. Một response có thể chứa:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=F5A...; Path=/; HttpOnly; Secure
~~~

Nó thường cho thấy một session đã được tạo hoặc được quản lý trong luồng xử lý. Tuy nhiên:

- `JSESSIONID` **không tự chứng minh** Spring Security đang lưu authentication trong session.
- Cookie có thể được phát qua **một chain khác**, một endpoint trước đó hoặc bởi Servlet component.
- Client có thể gửi `Cookie: JSESSIONID=...` từ trước ngay cả khi API không dùng nó.
- Không có `JSESSIONID` **không chứng minh** ứng dụng hoàn toàn stateless: có thể tồn tại Redis, DB, JWT denylist hoặc cookie khác.

### 13.1. Phân biệt cookie trong request và response

Request:

~~~http
GET /api/orders HTTP/1.1
Cookie: JSESSIONID=old-session-id
Authorization: Bearer <access-token>
~~~

Response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=new-session-id; Path=/; HttpOnly
~~~

Hai quan sát khác nhau. `Cookie` do client gửi có thể chỉ là cookie cũ; `Set-Cookie` cho thấy một thành phần phía server/proxy phát hoặc thay cookie.

Để biết **ai tạo session**, phải tìm callsite `getSession()` hoặc cơ chế tương ứng, không chỉ nhìn thấy cookie.

### 13.2. `JSESSIONID` không phải bearer token

Trong một JWT Resource Server được cấu hình chỉ nhận bearer header, cookie `JSESSIONID` không thay thế được:

~~~http
Authorization: Bearer <access-token>
~~~

Nếu bỏ header bearer mà API vẫn cho truy cập chỉ nhờ `JSESSIONID`, cần điều tra chain nào đang xác thực request, hoặc có cơ chế session/cookie khác đang được bật. Đây có thể là mục tiêu thiết kế có chủ đích ở browser chain, nhưng cần được tách rõ khỏi bearer-only API.

## 14. Dùng `getSession(false)` để quan sát mà không tạo session

Một lỗi chẩn đoán phổ biến là dùng:

~~~java
// Nguy hiểm cho việc quan sát: chính dòng này có thể tạo session.
request.getSession().getId();
~~~

Vì `getSession()` có thể tạo session, công cụ debug đang **tự gây ra hiện tượng cần điều tra**.

Thay bằng:

~~~java
HttpSession existing = request.getSession(false);

boolean hasSession = existing != null;
~~~

Nếu cần quan sát sau toàn bộ filter/controller, có thể viết filter tạm chỉ dùng `getSession(false)`.

### 14.1. Filter quan sát session dành cho môi trường phát triển

~~~java
package com.example.orders.diagnostics;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionObservationFilter
        extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SessionObservationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        boolean existedBefore =
            request.getSession(false) != null;

        try {
            chain.doFilter(request, response);
        } finally {
            boolean existsAfter =
                request.getSession(false) != null;

            log.debug(
                "path={} sessionBefore={} sessionAfter={}",
                request.getRequestURI(),
                existedBefore,
                existsAfter
            );
        }
    }
}
~~~

Đây là **filter minh họa**. Nếu muốn sử dụng, cần đăng ký filter cho đúng dispatcher/path/order và chỉ bật dưới cấu hình dev/test/diagnostics phù hợp. Tránh để diagnostics filter trở thành bộ thu dữ liệu nhạy cảm trong production.

Bộ lọc này chỉ quan sát sự hiện diện của session **trước/sau phạm vi mà nó bao quanh**. Một filter chạy sớm hơn có thể đã tạo session trước phép đo, hoặc session bị invalidate trong khi xử lý. Nó **không tự xác định chính xác callsite tạo session**.

### 14.2. Khi cần tìm chính xác nguồn tạo session

Các hướng điều tra:

1. Tìm trong code được phép kiểm tra những lời gọi `getSession()`, `getSession(true)`, `setAttribute` trên session.
2. Kiểm tra các MVC features như `@SessionAttributes`, flash attributes, session-scoped beans.
3. Kiểm tra `SecurityContextRepository`, `RequestCache`, `CsrfTokenRepository`, OAuth2 AuthorizationRequestRepository.
4. Kiểm tra filter chain được chọn, đặc biệt ứng dụng có nhiều chains.
5. Quan sát session creation events hoặc servlet-session diagnostics trong test environment.
6. Đối chiếu response `Set-Cookie` với access logs và chain/handler thực sự.
7. Kiểm tra Spring Session/Redis, proxy hoặc container nếu cookie không xuất phát từ application component.

Một lần quan sát `JSESSIONID` chưa đủ để kết luận nguyên nhân.

## 15. Kiểm tra bằng HTTP request thực tế

Các ví dụ dưới đây dùng địa chỉ và token giả định.

### 15.1. Gọi endpoint công khai không có cookie

~~~bash
curl -i https://api.example.com/api/public/ping
~~~

Quan sát:

- Response có `Set-Cookie: JSESSIONID` không?
- Các header khác có đúng chính sách không?
- Request có thực sự đi qua API chain không?

Lưu ý `permitAll()` vẫn thuộc security filter chain. Nếu client gửi **bearer token sai** tới endpoint public, authentication filter có thể từ chối trước khi request đến bước authorization; vì vậy nên thử trường hợp không gửi token riêng.

### 15.2. Gọi endpoint cần token

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Với API bearer stateless đúng, request hợp lệ có thể được xử lý mà không cần tạo `HttpSession`. **Nhưng** việc không thấy cookie chưa chứng minh toàn bộ hệ thống không có state.

### 15.3. Thử với cookie cũ

~~~bash
curl -i \
  -H "Cookie: JSESSIONID=some-old-value" \
  https://api.example.com/api/orders
~~~

Nếu endpoint cần bearer và không có `Authorization` header, theo policy nó nên không xác thực được chỉ bằng cookie cũ.

Đừng đưa real session ID hoặc access token vào ticket/log/chat. Session ID và bearer token đều có thể là credential nhạy cảm.

### 15.4. Thử hai request độc lập

~~~bash
curl -i https://api.example.com/api/public/ping
curl -i https://api.example.com/api/public/ping
~~~

Có thể dùng `curl` với cookie jar trong môi trường test để phân biệt lần đầu server tạo session hay client gửi cookie từ phiên trước, nhưng đừng lưu jar chứa credential thật ở nơi không an toàn.

## 16. Kiểm thử kỹ thuật: request không tạo `HttpSession`

Một test integration đơn giản có thể xác nhận một public endpoint không tạo session khi toàn bộ request chạy qua Spring MVC/Security trong môi trường test.

Ví dụ controller:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

MockMvc:

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StatelessSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestDoesNotCreateSession() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(result ->
                assertNull(result.getRequest().getSession(false)));
    }
}
~~~

Test giả định filter chain tương ứng đang hoạt động và endpoint `ping` tồn tại. `getSession(false)` trong assertion **không tạo session**, nên phù hợp để quan sát.

**Giới hạn:** test một endpoint không chứng minh *mọi* request/HTTP method đều không tạo session. Phải test riêng code path bật CSRF, login, error, redirect, custom filter và các endpoint sử dụng MVC state.

### 16.1. Test chứng minh API không tin cookie session

Một yêu cầu bảo mật quan trọng là request vào `/api/orders` **không được xác thực chỉ bằng `JSESSIONID`** nếu đó là một bearer-only API.

Có thể thiết kế integration test:

~~~text
Given một session/cookie từ browser login chain
When gọi GET /api/orders chỉ với cookie đó, không có Bearer header
Then API chain trả 401 hoặc không cho truy cập theo policy
```

Bài kiểm tra này phải chạy qua các `SecurityFilterChain` thật và xác nhận chain `/api/**` được chọn. Không chỉ mock một `Authentication` rồi kết luận session không được dùng.

### 16.2. Test authentication không đồng nghĩa session test

`SecurityMockMvcRequestPostProcessors.jwt()` của Spring Security Test tạo mock JWT authentication để kiểm tra authorization. Nó có thể bỏ qua JWT signature/issuer validation thực. Cơ chế test security context cũng có thể khác luồng bearer token thực tế.

Vì vậy để chứng minh “request bearer token hợp lệ không tạo session”, nên dùng integration test với `JwtDecoder` được kiểm soát/test key hoặc một test harness thực sự đi qua bearer authentication path, rồi quan sát session/cookie. Không chỉ dựa vào `.with(jwt())` để kết luận behavior production.

### 16.3. Các test âm tính nên có

| Tình huống | Mong đợi theo API bearer-only |
|---|---|
| Public GET không token | Cho phép, không cần tạo authentication session |
| Private GET không token | 401 theo bearer entry point |
| Private GET có JWT hợp lệ | Được xác thực từ token, không cần session |
| Private GET chỉ có `JSESSIONID` | Không được coi là đã xác thực nếu không có cơ chế cookie auth |
| Private GET có JWT hết hạn | 401 |
| JWT đúng nhưng thiếu scope | 403 |
| Request khác với cùng JWT | Xác thực dựa trên token được gửi lại |
| Controller vô tình `getSession()` | Test phát hiện session |
| CSRF repository dựa session được kích hoạt | Test phát hiện state tùy cấu hình |
| OAuth2 Login redirect/callback | Được giữ trong web chain có state phù hợp |
| API URL ngoài security matcher | Không được bypass protection |
| Error/forward dispatch | Không tạo/chấp nhận state ngoài dự kiến |

**Đây là đề xuất ca kiểm thử**, không phải một lượt QA/Gradle cần chạy trong giai đoạn soạn bài.

## 17. Cookies, JWT, CSRF và XSS: các mối quan tâm khác nhau

Có thể gặp ba kiểu client:

| Client | Credential thường gửi | Nguy cơ cần quan tâm |
|---|---|---|
| CLI/server-to-server | `Authorization: Bearer ...` | Bảo vệ token, transport TLS, validation |
| SPA gửi Bearer header | Token do JavaScript/chương trình chủ động đưa vào header | Token theft/XSS, CORS, storage policy |
| Browser gửi cookie | Cookie được browser tự gửi theo thuộc tính | CSRF, session/cookie security, SameSite |

`STATELESS` không quyết định cách **client** lưu token. API không dùng HTTP session nhưng vẫn có thể nhận một bearer token lưu trong cookie hoặc sử dụng cookie session ở chain khác.

### 17.1. Tắt CSRF không giải quyết XSS

Nếu token bị JavaScript độc hại lấy được, CSRF protection không tự ngăn kẻ tấn công dùng token đó. Cần kết hợp CSP, escaping, dependency hygiene, hạn chế scope và chính sách token storage phù hợp.

Ngược lại, token trong cookie `HttpOnly` có thể chống JavaScript đọc trực tiếp cookie nhưng cookie tự gửi làm phát sinh yêu cầu xem xét CSRF. Không có một tùy chọn lưu token mặc định đúng cho mọi kiến trúc.

### 17.2. CORS không phải authentication

Một cấu hình CORS hạn chế `Origin` chỉ ảnh hưởng cách **browser** đọc response cross-origin; nó không tự từ chối các HTTP client không phải browser. CORS và stateless session policy độc lập với bearer authentication.

Nếu browser SPA gửi `Authorization` header, CORS preflight có thể cần được xử lý trước authentication, nhưng không nên mở rộng quyền endpoint nghiệp vụ chỉ để “sửa CORS”.

## 18. Logout của API stateless có ý nghĩa gì?

Với session login, logout có thể invalidate `HttpSession` và xóa `SecurityContext` lưu trong đó. Với JWT bearer API stateless:

~~~text
Client bỏ token ở phía mình
         |
         +-- Không tự làm JWT đã phát hành hết hiệu lực ở mọi nơi
```

`STATELESS` không tự revoke access token.

Nếu JWT vẫn còn thời hạn và Resource Server chỉ xác minh chữ ký cục bộ, bearer token bị lộ vẫn có thể được dùng lại cho tới khi hết hạn hoặc có cơ chế thu hồi phù hợp.

Các chiến lược tùy mục tiêu:

- Access token TTL ngắn và refresh token được quản lý ở AS.
- Token revocation/introspection nếu token profile hỗ trợ và API cần trạng thái hiện tại.
- Denylist hoặc security-version check khi muốn vô hiệu hóa trước hạn.
- Token binding/proof-of-possession nếu threat model và hạ tầng hỗ trợ.
- Cơ chế logout riêng cho OIDC Client/browser session, không nhầm với API bearer credential.

**Không xây endpoint `/logout` cho JWT rồi mặc định kết luận token đã bị vô hiệu hóa** nếu endpoint chỉ xóa một session không liên quan.

## 19. State bên ngoài `HttpSession` vẫn có thể hợp lệ

Một API bearer Resource Server thường có state cần thiết:

### 19.1. JWKS cache

Khi xác minh JWT theo `issuer-uri`/`jwk-set-uri`, thư viện thường cache public keys/JWK Set. Đây là state về **khóa xác minh**, không phải session login của người dùng.

Key rotation đòi cache cập nhật đúng; xóa mọi cache để “thật stateless” có thể làm giảm hiệu năng và tăng phụ thuộc mạng mà không cải thiện mô hình session.

### 19.2. Opaque introspection cache

Resource Server có thể cache kết quả introspection để giảm độ trễ. Cache này có thể lưu trạng thái token active, scopes hoặc roles trong thời gian ngắn. Đây là state bảo mật đáng quản lý, đặc biệt khi token revoked.

Nó **khác `HttpSession`** nhưng vẫn ảnh hưởng revocation freshness.

### 19.3. Rate limiter và chống replay

Một API có thể dùng Redis để theo dõi rate limits, idempotency keys hoặc nonce đã sử dụng, dù authentication stateless. Điều đó không mâu thuẫn trực tiếp với `SessionCreationPolicy.STATELESS`.

Một hành động nhạy cảm có thể **cần** state server-side để chống double-submit/replay. Không cố loại bỏ nó chỉ vì muốn gọi toàn bộ hệ thống là stateless.

### 19.4. Phân quyền theo tenant/ACL

JWT có scope `orders.read` không tự chứng minh quyền trên mọi order. Resource Server có thể truy vấn database để kiểm tra membership/ownership. Đây là **business authorization state**, không phải session authentication.

## 20. Khác biệt giữa Spring Security Servlet và WebFlux

Các ví dụ trong bài dùng `HttpSecurity`, `SecurityFilterChain`, `HttpSession` và servlet APIs.

Trong Spring WebFlux:

- Sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`.
- Khái niệm web session là `WebSession`, không phải `jakarta.servlet.http.HttpSession`.
- Cơ chế lưu security context có các interface reactive riêng như `ServerSecurityContextRepository`.
- Chính sách/session APIs khác Servlet; không copy nguyên enum `SessionCreationPolicy` vào WebFlux rồi kỳ vọng tương đương.

**Tư duy chung** vẫn là tách authentication state, browser login state, CSRF state và business state, nhưng đường cấu hình cụ thể phải đúng stack.

## 21. Ma trận chẩn đoán `JSESSIONID` bất ngờ

| Hiện tượng | Nguyên nhân có thể | Điều nên kiểm tra |
|---|---|---|
| `JSESSIONID` ngay ở public GET | Controller/filter/MVC tạo session | `getSession()`, `@SessionAttributes`, flash attrs |
| Session xuất hiện khi mở HTML form | `HttpSessionCsrfTokenRepository` | CSRF token có được materialize không |
| Session khi vào `/oauth2/authorization/...` | OAuth2 Login authorization request | `HttpSessionOAuth2AuthorizationRequestRepository` |
| Session sau form login thành công | Session authentication / fixation strategy | Web chain vs API chain |
| Session sau 401/redirect | `HttpSessionRequestCache`/saved request | Request cache và login entry point |
| API có session khi response lỗi | Error/forward/view hoặc filter khác | Error dispatch, JSP, request cache |
| Mỗi API request có Redis session entry | Spring Session + thành phần gọi `getSession()` | Spring Session filters, source callsite |
| Cookie `JSESSIONID` từ browser nhưng API không dùng được | Cookie của web chain cũ | Xác minh chain API vẫn yêu cầu Bearer |
| Cùng cookie truy cập API không Bearer vẫn được | API chain có thể nhận session auth | Kiểm tra securityMatcher/repository/filter |
| Không có `JSESSIONID` nhưng có Redis/DB state | Introspection, cache, ACL, rate limiting | Đừng nhầm HTTP session với state khác |
| Sau khi thêm `.oauth2Login()` API bắt đầu redirect | Chain trộn browser và bearer flow | Tách filter chains, entry points |
| `STATELESS` mà custom filter lưu SecurityContext vào session | Repository bị override | `SecurityContextRepository` của từng filter |

**Không sửa triệt để bằng cách chỉ xóa cookie ở reverse proxy**. Nếu server vẫn tạo session và dùng nó, che `Set-Cookie` có thể làm login/CSRF hỏng và không giải quyết state leak. Cần tìm nguyên nhân tạo state trước.

## 22. Những cấu hình dễ gây hiểu nhầm

### 22.1. `STATELESS` cùng `formLogin()`

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.formLogin(Customizer.withDefaults())
~~~

Đây có thể là mâu thuẫn với mục tiêu dùng session login tương tác, saved request, CSRF và chuyển hướng. Không mặc định mọi flow sẽ hoạt động như mong muốn. Nếu hệ thống cần web login, thiết kế chain riêng phù hợp.

### 22.2. `STATELESS` cùng `oauth2Login()`

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.oauth2Login(Customizer.withDefaults())
~~~

OAuth2 Login thường dùng session để lưu authorization request/state và PKCE context qua redirect. Chỉ đổi `STATELESS` không biến login thành stateless đúng protocol. Cần thiết kế state storage an toàn hoặc tách chain.

### 22.3. `STATELESS` cùng `HttpSessionCsrfTokenRepository`

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
~~~

Tùy khi CSRF token được truy xuất/lưu, repository có thể sử dụng `HttpSession`. Nếu API cần xác thực cookie, vẫn có thể phải bảo vệ CSRF; không xóa CSRF vì muốn hết `JSESSIONID` mà chưa phân tích threat model.

### 22.4. `STATELESS` cùng custom `HttpSessionSecurityContextRepository`

~~~java
.securityContext(context -> context
    .securityContextRepository(
        new HttpSessionSecurityContextRepository()))
~~~

Điều này có thể khiến authentication được lưu/đọc theo behavior custom, trái với ý định không dùng session. Chỉ thực hiện khi có thiết kế và kiểm chứng rõ về phiên/các filter.

### 22.5. `STATELESS` nhưng code app vẫn gọi session

~~~java
@GetMapping("/api/me")
String me(HttpServletRequest request) {
    request.getSession().setAttribute("visited", true);
    return "ok";
}
~~~

Lệnh `getSession()` là nguyên nhân trực tiếp tạo `HttpSession`. Không nên đổ lỗi cho `BearerTokenAuthenticationFilter` nếu đây là callsite thực.

## 23. Một quy trình lựa chọn thiết kế

Khi xây dựng API OAuth 2.0/OIDC:

**Bước 1 — Phân loại các entrypoints.** API chỉ nhận bearer header, browser OIDC login, BFF, admin UI, actuator và callback cần được xét riêng.

**Bước 2 — Xác định nơi chứa credential.** Bearer header do client chủ động gửi hay cookie tự động gửi? Có session login không?

**Bước 3 — Chọn policy tương ứng.** Bearer-only Resource Server thường dùng `STATELESS`; browser login thường có session hoặc state storage tương đương.

**Bước 4 — Kiểm tra `SecurityContextRepository` và `RequestCache`.** Không để bearer API lưu security context hoặc saved request vào session ngoài ý muốn.

**Bước 5 — Xem CSRF policy.** Đánh giá dựa vào browser credential model, không dựa riêng vào chữ stateless.

**Bước 6 — Tìm nguồn tạo session ngoài security.** Controller, filter, `@SessionAttributes`, flash attrs, OAuth2 Login và Spring Session.

**Bước 7 — Test đúng filter chains và request paths.** Một route public GET không chứng minh POST hoặc callback không tạo state.

**Bước 8 — Kiểm tra quyền tài nguyên.** `STATELESS` không thay thế authorization theo tenant/owner.

**Bước 9 — Xác định vòng đời token và logout.** Stateless Resource Server không tự revoke JWT.

**Bước 10 — Theo dõi thay đổi cấu hình.** Khi thêm web login, CSRF hoặc Redis, cần xem lại giả định “API không dùng session”.

## 24. Những hiểu nhầm thường gặp

**“`STATELESS` cấm toàn bộ ứng dụng tạo session.”** Sai. Nó là chính sách về cách Spring Security dùng `HttpSession`, không cấm Servlet/MVC/application code tạo session.

**“`NEVER` và `STATELESS` giống nhau.”** Sai. `NEVER` có thể dùng session đã tồn tại; `STATELESS` không dùng session để lấy `SecurityContext`.

**“`SecurityContextHolder` có Authentication là đã có HttpSession.”** Sai. Context có thể tồn tại trong thời gian xử lý request mà không được lưu qua request.

**“Một request có `JSESSIONID` nghĩa là API đã xác thực bằng cookie.”** Không nhất thiết. Cookie có thể tồn tại từ web chain, nhưng API chain vẫn có thể chỉ chấp nhận bearer.

**“Không có cookie là toàn bộ ứng dụng không có state.”** Sai. Có thể có cache, database, revocation hoặc rate limiting state.

**“`STATELESS` tự tắt CSRF.”** Không. CSRF là cơ chế riêng; repository có thể dùng session/cookie tùy cấu hình.

**“API stateless luôn an toàn trước CSRF.”** Sai nếu credential được browser gửi tự động (ví dụ cookie).

**“`oauth2Login` không cần giữ state vì dùng OAuth2.”** Sai. Authorization Code/OIDC flow thường cần state/PKCE/nonce qua redirect.

**“JWT stateless nghĩa là `/logout` sẽ vô hiệu hóa mọi JWT cũ.”** Sai. Cần revocation/introspection/denylist hoặc cơ chế khác nếu muốn chặn trước expiry.

**“`getSession(false)` có thể tạo session.”** Sai. Nó chỉ lấy session hiện có; `getSession()`/`getSession(true)` có thể tạo mới.

**“Không nên dùng Redis nếu API stateless.”** Không đúng. Redis có thể được dùng cho rate limiting, ACL, cache, idempotency hoặc session của web chain khác.

**“Chỉ cần thêm `.anyRequest().denyAll()` ở API chain là cả ứng dụng an toàn.”** Không nếu API chain bị giới hạn bởi `securityMatcher` và các URL khác không có chain phù hợp.

**“Thấy `JSESSIONID` là cứ xóa cookie ở proxy.”** Không nên. Phải tìm nguyên nhân tạo session và xác định flow thực sự cần nó.

## 25. Câu hỏi tự kiểm tra

**1.** `SessionCreationPolicy.STATELESS` bảo đảm điều gì?

> Spring Security không tạo `HttpSession` và không dùng session để lấy `SecurityContext`. Nó không cấm mọi component khác tạo/lưu state.

**2.** `NEVER` khác `STATELESS` ở đâu?

> `NEVER` không tự tạo session nhưng có thể dùng session có sẵn; `STATELESS` không sử dụng session để khôi phục security context.

**3.** Vì sao JWT Resource Server vẫn có `Authentication` trong controller dù stateless?

> `Authentication` được tạo cho request hiện tại từ bearer token và đặt vào `SecurityContext` request, không nhất thiết lưu trong `HttpSession`.

**4.** Dòng `request.getSession().setAttribute(...)` có tạo session trong stateless API được không?

> Có. Servlet API có thể tạo `HttpSession` dù Spring Security dùng `STATELESS`.

**5.** Khi muốn kiểm tra session hiện hữu mà không tạo mới nên gọi gì?

> `request.getSession(false)`.

**6.** `HttpSessionRequestCache` có thể tạo state gì?

> `SavedRequest` trong session để tiếp tục điều hướng sau khi người dùng đăng nhập. Bearer-only API thường không cần cơ chế này.

**7.** Vì sao CSRF có thể liên quan session?

> `HttpSessionCsrfTokenRepository` lưu expected CSRF token trong `HttpSession` khi token được dùng hoặc lưu; Spring Security hiện đại thường deferred-load token.

**8.** Một OAuth2/OIDC Login flow có thể cần trạng thái nào?

> Authorization request, `state`, PKCE `code_verifier`, nonce và session login tùy kiến trúc. Không nên vô hiệu hóa những kiểm tra này để ép stateless.

**9.** API có `STATELESS` và vẫn xuất hiện `JSESSIONID`. Kết luận ngay Spring Security JWT đang lưu authentication có đúng không?

> Không. Phải kiểm tra controller/filter, CSRF, request cache, login chain, Spring MVC hoặc proxy trước khi kết luận.

**10.** JWT stateless có xóa bỏ nhu cầu database/Redis không?

> Không. Business data, ACL, rate limits, idempotency, cache và revocation có thể cần state riêng, không đồng nghĩa HTTP session.

**11.** Vì sao phải phân biệt cookie request và `Set-Cookie` response?

> Cookie request có thể là cookie cũ do browser gửi; `Set-Cookie` thể hiện server/proxy phát hoặc đổi cookie. Hai dấu hiệu không chứng minh cùng một nguồn state.

**12.** Khi ứng dụng vừa phục vụ `/api/**` bearer JWT vừa có OIDC Login trên web UI, cách triển khai thường hợp lý?

> Tách `SecurityFilterChain` theo phạm vi: API stateless và web chain giữ state cần thiết cho OAuth2 Login/CSRF, cùng một fallback security policy rõ.

## 26. Tài liệu tham khảo

- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): ý nghĩa `STATELESS`, security context, request cache, chiến lược session và các phiên bản filter.
- [Spring Security — SessionCreationPolicy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/http/SessionCreationPolicy.html): bốn giá trị `ALWAYS`, `IF_REQUIRED`, `NEVER`, `STATELESS`.
- [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository`, `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository`, `SecurityContextHolderFilter`.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer JWT, claim validation và scope mapping.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và opaque authentication.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `HttpSessionCsrfTokenRepository`, `CookieCsrfTokenRepository` và deferred token loading.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): browser OAuth2 Login flow, authorization request và redirect.
- [Spring Security — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): customization của authorization request repository và login flow.
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, `@Order` và phạm vi security chains.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/): session storage, Redis/JDBC và tích hợp Servlet.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer header và lỗi authentication.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, Authorization Code, refresh token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC login và các yêu cầu như nonce.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` và `code_challenge` trong Authorization Code flow.

**Kết luận:** với Resource Server nhận bearer access token, `SessionCreationPolicy.STATELESS` là cách diễn đạt rõ rằng **Spring Security không duy trì authentication bằng `HttpSession` giữa các request**. Nhưng `HttpSession` vẫn có thể xuất hiện từ MVC, CSRF, saved requests, OAuth2 Login hoặc code/thư viện khác; và những state như JWKS cache, database, Redis, introspection hoặc revocation không biến mất. Muốn một API đúng nghĩa **không phụ thuộc HTTP session để xác thực**, hãy kiểm tra toàn bộ đường request, tách các chain có nhu cầu khác nhau, quan sát bằng `getSession(false)` và bảo vệ độc lập những vấn đề như CSRF, quyền trên tài nguyên và vòng đời token.
