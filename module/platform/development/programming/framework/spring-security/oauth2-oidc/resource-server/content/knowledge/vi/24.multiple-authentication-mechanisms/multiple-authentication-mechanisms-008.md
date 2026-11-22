# Xung đột giữa cookie phiên, HTTP Basic, Bearer và cơ chế khác

## 1. Tình huống mở đầu: cùng một request có nhiều “dấu hiệu đã đăng nhập”

Một ứng dụng Spring Boot phục vụ ba nhóm người dùng:

- **Trình duyệt:** người dùng đăng nhập vào `/web/**` bằng form login hoặc OpenID Connect (OIDC), sau đó sử dụng cookie phiên như `JSESSIONID`.
- **Mobile/SPA/microservice:** Client gọi `/api/**` bằng OAuth 2.0 **access token** trong `Authorization: Bearer ...`.
- **Hệ thống nội bộ cũ:** service-to-service client gọi `/internal/legacy/**` bằng `Authorization: Basic ...` trong thời gian chuyển đổi sang OAuth.

Một request từ trình duyệt có thể mang cả cookie phiên và Bearer token:

```http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
Cookie: JSESSIONID=<browser-session-cookie>
Authorization: Bearer <oauth-access-token>
Accept: application/json
```

Còn một request khác có thể chỉ mang cookie:

```http
GET /api/orders/42 HTTP/1.1
Host: shop.example.com
Cookie: JSESSIONID=<browser-session-cookie>
```

Nếu API được thiết kế **chỉ chấp nhận Bearer access token**, request thứ hai phải bị từ chối dù người dùng đã đăng nhập website. Nhưng nếu API và website dùng chung một `SecurityFilterChain` đọc HTTP session, một cookie phiên có thể bất ngờ trở thành **Authentication hợp lệ** của API.

Nguy hiểm hơn, nếu request mang Bearer token **hết hạn** nhưng vẫn có cookie phiên hợp lệ, một cấu hình hoặc custom filter sai có thể lặng lẽ “fallback” sang cookie và cho truy cập. Khi đó API đã bỏ qua ý nghĩa xác thực JWT, audience và scope của token mà Client thực sự trình.

Đây là chủ đề **xung đột giữa nhiều cơ chế xác thực**: không chỉ là hai filter cùng chạy, mà là việc xác định **credential nào có quyền quyết định danh tính**, **policy nào phải được áp dụng**, **khi nào phải từ chối**, và **không vô tình đổi đường xác thực khi một credential thất bại**.

### Các câu hỏi bài học cần giải quyết

1. Cookie phiên, HTTP Basic, Bearer, API key, mTLS và OIDC login khác nhau về bản chất thế nào?
2. Khi có nhiều `SecurityFilterChain`, Spring Security chọn chain nào?
3. Điều gì xảy ra nếu một chain bật cùng lúc `formLogin`, `httpBasic` và `oauth2ResourceServer`?
4. Nếu request có cả `JSESSIONID` và Bearer token, hệ thống nên tin credential nào?
5. Có nên thử Basic khi Bearer token sai, hoặc dùng session khi JWT hết hạn không?
6. Vì sao bật HTTP Basic hoặc cookie authentication làm thay đổi quyết định về CSRF?
7. Làm sao bảo đảm API trả `401 Bearer`, web redirect login, còn legacy endpoint trả `401 Basic`?
8. Cấu hình và kiểm thử thế nào để ngăn **credential confusion**, **session fallback** và **bypass phân quyền**?

**Nguyên tắc chính:** Định nghĩa **một hợp đồng xác thực rõ ràng cho từng vùng tài nguyên**, cho phép hoặc từ chối từng loại credential có chủ đích; không suy luận rằng “đã xác thực bằng bất cứ cách nào” đồng nghĩa được phép gọi mọi API.

---

## 2. Authentication, credential và authorization là ba khái niệm khác nhau

### 2.1. Credential: bằng chứng Client đưa tới server

Một HTTP request có thể chứa:

```http
Authorization: Bearer eyJhbGciOi...
```

hoặc:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==
```

hoặc:

```http
Cookie: JSESSIONID=...
```

hoặc một bằng chứng khác như mTLS client certificate, signed request hoặc API key qua header được quy định.

Đó là **những cách trình credential khác nhau**. Chúng không tự trả lời credential có được phép dùng cho resource hiện tại hay không.

### 2.2. Authentication: hệ thống chấp nhận credential và tạo principal

Spring Security biểu diễn kết quả thường bằng `Authentication` trong `SecurityContext`:

- `JwtAuthenticationToken` từ JWT access token.
- `BearerTokenAuthentication` từ opaque token introspection.
- `UsernamePasswordAuthenticationToken` từ form login hoặc HTTP Basic, tùy provider.
- `OAuth2AuthenticationToken` hoặc authentication chứa OIDC principal sau `oauth2Login`.
- Kiểu `Authentication` tùy biến của API key/mTLS.

**Một `Authentication` đã xác thực không tự chứng minh nó được tạo bởi cơ chế đúng cho endpoint đang gọi.**

Ví dụ:

```text
GET /api/orders/42
Expected:  JwtAuthenticationToken + SCOPE_orders.read
Observed:  UsernamePasswordAuthenticationToken from browser session
```

Nếu rule chỉ là `authenticated()`, request có thể được cho phép dù API contract yêu cầu Bearer access token.

### 2.3. Authorization: xác thực thành công vẫn có thể thiếu quyền

Bearer JWT đúng chữ ký/issuer/audience nhưng thiếu `SCOPE_orders.read` thường bị từ chối ở **authorization**, không phải authentication.

Cookie phiên hợp lệ của một user có `ROLE_USER` cũng không tự cấp scope `orders.read`. Một API cần quyền của token hoặc một policy business cụ thể, không phải đơn giản kiểm tra user có tồn tại.

### 2.4. Bảng phân biệt các cơ chế

| Cơ chế | Credential Client gửi | Authentication điển hình | Đặc điểm nổi bật |
|---|---|---|---|
| Browser session | `Cookie: JSESSIONID=...` | User từ `SecurityContext` trong session | Trình duyệt tự gửi cookie theo phạm vi cookie |
| HTTP Basic | `Authorization: Basic ...` | Username/password được xác minh | Credential có thể được trình lại mỗi request; Basic chỉ Base64-encode |
| OAuth Bearer JWT | `Authorization: Bearer ...` | `JwtAuthenticationToken` | Phải xác minh chữ ký/issuer/audience/thời hạn/token profile |
| OAuth Bearer opaque | `Authorization: Bearer ...` | `BearerTokenAuthentication` | Thường introspect với AS; phải kiểm tra `active` và policy |
| OIDC browser login | Redirect/code flow, sau đó web session | OIDC user/client authentication | Đăng nhập trình duyệt **không** đồng nghĩa API đã nhận Bearer token |
| API key | `X-API-Key` hoặc scheme được định nghĩa | Authentication tùy biến | Cần định danh Client, rotation, scope, rate limit, bảo vệ secret |
| mTLS client authentication | TLS client certificate + proof of key possession | X.509/client identity | Chứng minh bên gửi nắm private key; còn cần authorization |
| Gateway identity header | `X-Authenticated-User` từ gateway tin cậy | Principal từ proxy policy | Phải loại bỏ header Client tự gửi và xác minh ranh giới proxy |

Không đặt các cơ chế này ngang nhau về sức mạnh hoặc ngữ nghĩa. Mỗi cơ chế có cách thu hồi, bảo mật credential và policy khác nhau.

---

## 3. Những điều cần biết về từng loại credential

### 3.1. Cookie phiên: được browser gửi tự động

Sau web login, server có thể gửi:

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
Location: /web/dashboard
```

Browser sẽ gửi cookie trên request phù hợp `Domain`, `Path`, `Secure` và `SameSite`. Client JavaScript không nhất thiết phải tự thêm header Cookie; đó chính là lý do **session-based authentication thường cần bảo vệ CSRF** cho thao tác thay đổi trạng thái.

Cùng hostname `shop.example.com`, cookie có `Path=/` cũng có thể xuất hiện trong request `/api/**`. Việc cookie **có mặt** không có nghĩa API nên **dùng cookie để xác thực**.

### 3.2. HTTP Basic: không phải session, không phải Bearer

Ví dụ:

```http
Authorization: Basic c2VydmljZS1yZWFkZXI6ZGVtby1vbmx5
```

Giá trị Base64 đại diện một chuỗi `username:password`. Base64 **không phải mã hóa bảo mật**; bắt buộc sử dụng HTTPS và tránh ghi header vào log.

HTTP Basic thường được dùng trên mỗi request. Một số browser có thể **ghi nhớ credential Basic theo protection space và tự gửi lại**, nên khi HTTP Basic được chấp nhận trong browser, cần đánh giá rủi ro **CSRF và tự động gửi credential** tương tự các cơ chế ambient authentication.

Basic không có ngữ nghĩa OAuth `scope`/`audience`. Nếu API muốn dùng Basic cho một legacy client, phải định nghĩa role/permission và lifecycle credential của nó, không tự xem password là access token.

### 3.3. Bearer access token: ai có token có thể trình token

Trong OAuth 2.0 Bearer token usage:

```http
Authorization: Bearer <access-token>
```

Resource Server kiểm tra token đúng hợp đồng. JWT có thể được giải mã/xác minh với `JwtDecoder`; opaque token thường được kiểm tra qua `OpaqueTokenIntrospector`.

Với mô hình Client chủ động thêm header Authorization, browser **không tự gắn một access token chỉ vì user đã đăng nhập bằng session**. Tuy nhiên, nếu hệ thống lưu Bearer token **trong cookie** rồi để server tự lấy ra, credential trở thành ambient credential và rủi ro CSRF thay đổi; đừng mặc định “Bearer là luôn miễn CSRF”.

### 3.4. OIDC login: web app là OAuth2/OIDC Client

Khi dùng:

```java
.oauth2Login(Customizer.withDefaults())
```

ứng dụng tham gia authorization code flow với IdP để đăng nhập người dùng vào website. Nó có thể tạo web session và lưu một `OAuth2AuthenticationToken`/OIDC principal.

**OIDC ID token không phải access token cho Resource Server.** ID token thường có audience là OAuth Client ID, trong khi access token cho `orders-api` phải đáp ứng audience/scope của API.

### 3.5. API key hoặc mTLS là một hợp đồng riêng

Nếu thêm API key hoặc mTLS vào endpoint đang chấp nhận Bearer, phải trả lời:

- API key và Bearer có được dùng thay thế nhau không?
- Chúng có cấp **cùng tập quyền** hay chỉ quyền hạn chế?
- Khi cả hai xuất hiện, cần cả hai, hay chỉ một?
- Nếu một credential bị từ chối, có được dùng credential kia không?
- Principal nào được dùng để log, phân quyền và giới hạn tenant?
- Khi một credential được thu hồi, có thể dùng credential kia để bypass không?

**Không bật thêm một authentication filter rồi để câu trả lời ngẫu nhiên phụ thuộc thứ tự filter.**

---

## 4. Tại sao xung đột phát sinh trong Spring Security?

### 4.1. Các filter có trách nhiệm khác nhau

Trong Spring Security Servlet, tùy cấu hình, một chain có thể chứa:

- Security context filters: tải/lưu `SecurityContext`.
- `UsernamePasswordAuthenticationFilter`: xử lý form login.
- `BasicAuthenticationFilter`: xử lý HTTP Basic.
- `BearerTokenAuthenticationFilter`: xử lý OAuth Bearer token.
- `ExceptionTranslationFilter`: chuyển exception từ downstream security flow thành entry point/denied handler.
- `AuthorizationFilter`: áp dụng `authorizeHttpRequests`.

Một request có thể đi qua **nhiều filter trong cùng chain**. Mỗi filter có điều kiện kích hoạt riêng: Basic filter quan tâm header Basic, Bearer filter quan tâm header Bearer, form login filter quan tâm login processing URL. Security context filter có thể khôi phục session authentication trước khi các filter đó xử lý.

**Đừng hiểu là mọi filter đều thử mọi credential theo một thứ tự fallback được framework bảo đảm.** Thứ tự, error handler, request matcher và SecurityContextRepository quyết định hành vi thực tế.

### 4.2. AuthenticationManager không giải quyết ưu tiên giữa Cookie/Basic/Bearer

`AuthenticationManager` có thể dùng nhiều `AuthenticationProvider`, nhưng nó thường xử lý **một loại Authentication request đã được filter tạo ra**. Nó không tự quyết định rằng session cookie và Bearer token trong cùng HTTP request phải được kết hợp thế nào.

Ví dụ:

```text
BasicAuthenticationFilter
  → UsernamePasswordAuthenticationToken
  → AuthenticationManager / password provider

BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken
  → AuthenticationManager / JWT or opaque provider
```

Nếu cả session và Bearer cùng hiện diện, quyết định nên tin cái nào không chỉ là bài toán chọn provider; cần **thiết kế ranh giới chain và chính sách credential**.

### 4.3. Một chain bật ba cơ chế có thể tạo kết quả khó dự đoán

Ví dụ chưa phân tách:

```java
@Bean
SecurityFilterChain mixed(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .requestMatchers("/web/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Cấu hình trên **không phải luôn sai** về mặt kỹ thuật. Nhưng nếu sản phẩm yêu cầu API **chỉ dùng Bearer** còn web **chỉ dùng session**, nó không thể hiện ranh giới đó.

Rủi ro:

- `authenticated()` trên API có thể thỏa bằng web session nếu chain còn sử dụng session context.
- HTTP Basic có thể trở thành một đường xác thực thay thế ở vùng tài nguyên không dự kiến.
- Request thiếu Authentication có thể nhận redirect hoặc Basic challenge thay vì Bearer challenge.
- CSRF bị tắt để “sửa API 403” có thể làm yếu web session và Basic trong browser.
- Token sai hoặc credential mâu thuẫn có thể tạo error semantics không nhất quán.
- Role/authority từ cơ chế này có thể vô tình đáp ứng rule của cơ chế khác.

Giải pháp mặc định tốt hơn là **tách các vùng URL theo cơ chế**.

---

## 5. `SecurityFilterChain`: chain đầu tiên khớp được chọn

### 5.1. FilterChainProxy không cộng dồn mọi chain

Spring Security Servlet dùng `FilterChainProxy` để chọn `SecurityFilterChain` cho HTTP request. Khi có nhiều chain, framework chọn **chain đầu tiên có `RequestMatcher` khớp** theo thứ tự ưu tiên.

Ví dụ:

```text
@Order(1)  /api/**               → OAuth Bearer only
@Order(2)  /internal/legacy/**   → HTTP Basic only
@Order(3)  any request          → Browser session/form login
```

Luồng:

```mermaid
flowchart TD
    R["HTTP request"] --> P["FilterChainProxy"]
    P --> M1{"Khớp /api/**?"}
    M1 -->|Có| A["API chain: JWT/opaque Bearer, stateless"]
    M1 -->|Không| M2{"Khớp /internal/legacy/**?"}
    M2 -->|Có| L["Legacy chain: HTTP Basic, giới hạn route"]
    M2 -->|Không| W["Web catch-all: form/OIDC login, session + CSRF"]
    A --> Z["Authorization và nghiệp vụ nếu hợp lệ"]
    L --> Z
    W --> Z
```

**Không có chuyện API Bearer authentication thất bại rồi Spring Security tự chạy tiếp web chain phía sau.** Khi request đã khớp API chain, lỗi được xử lý trong chain đó.

### 5.2. `securityMatcher` chọn chain; `requestMatchers` chọn policy bên trong chain

Ví dụ:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll());
```

- `securityMatcher("/api/**")` quyết định toàn bộ filter chain có xử lý request không.
- `requestMatchers("/api/public/**")` quyết định authorization của URL **sau khi đã chọn API chain**.
- `anyRequest().denyAll()` **chỉ** áp dụng request đã khớp chain; nó không bảo vệ mọi URL của application.

Một chain không có `securityMatcher` riêng thường match mọi request, nên nếu đặt catch-all trước API thì API chain có thể không bao giờ được chọn.

### 5.3. `@Order` phải được khai báo có chủ đích

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception { ... }

@Bean
@Order(2)
SecurityFilterChain legacy(HttpSecurity http) throws Exception { ... }

@Bean
@Order(3)
SecurityFilterChain web(HttpSecurity http) throws Exception { ... }
```

Đừng dựa vào thứ tự các method xuất hiện trong file. `@Order` chỉ quyết định **thứ tự xét chain**, không phải thứ tự filter bên trong một chain.

### 5.4. Catch-all cuối không nên là `permitAll()` toàn cục

Nếu web chain cuối:

```java
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
```

một endpoint mới ngoài `/api/**` hoặc `/internal/legacy/**` có thể bất ngờ công khai.

An toàn hơn là khai báo static/login endpoints công khai, vùng web yêu cầu login và **deny by default** những URL khác. Các security filters như form login/logout có endpoint riêng, phải bảo đảm chúng nằm trong chain chứa cơ chế đó.

---

## 6. Quy tắc đề xuất: mỗi URL có một cơ chế xác thực chính

Một contract rõ ràng:

| Vùng URL | Cơ chế được phép | Cơ chế không thay thế | Phản hồi khi thiếu credential |
|---|---|---|---|
| `/api/**` | OAuth Bearer access token | Web session, HTTP Basic, API key lạ | `401` Bearer challenge |
| `/internal/legacy/**` | HTTP Basic của service được cấp phép | Bearer, web session | `401` Basic challenge |
| `/web/**` | Browser session sau form/OIDC login | Bearer trực tiếp, Basic | Redirect login |
| `/login`, `/logout` | Browser login/logout flow | Bearer token API | Theo web login policy |
| `/assets/**` | Không yêu cầu login | Không cần “fallback” | Public static resource |
| `/api/public/**` | Công khai, tùy contract xử lý Bearer | Không tự nâng quyền | Thường được phép nếu không gửi token lỗi |

Contract này không phải chuẩn bắt buộc cho mọi tổ chức, nhưng **nên có một bảng rõ ràng tương đương** trước khi viết các filter.

### 6.1. Nếu request có credential “khác loại” thì sao?

Nếu `/api/**` chỉ nhận Bearer mà Client gửi:

```http
Authorization: Basic dXNlcjpwYXNz
```

thì Basic filter **không được bật trong API chain**. Request thường được coi là **không có Bearer authentication** và protected API trả `401 Bearer`.

Điều đó không có nghĩa service account Basic chắc chắn sai mật khẩu; nó chỉ **không phải credential được API chấp nhận**.

Tương tự, nếu legacy chain chỉ nhận Basic mà Client gửi Bearer, không cần cố giải mã Bearer rồi cấp quyền legacy.

### 6.2. Credential được trình mà không hợp lệ phải fail, không fallback

Một request vào API:

```http
Cookie: JSESSIONID=<valid-web-session>
Authorization: Bearer <expired-access-token>
```

Kết quả đúng cho API Bearer-only là **từ chối token**, thường `401 invalid_token`. Không dùng session để cho qua.

Với legacy Basic endpoint:

```http
Cookie: JSESSIONID=<valid-web-session>
Authorization: Basic <wrong-password>
```

Basic authentication phải thất bại theo policy. Không dùng web session làm cứu cánh.

### 6.3. Không đồng nhất “đúng người dùng” với “đúng credential”

Một user đăng nhập web và đồng thời có JWT access token với cùng `sub`:

```text
Web session:
  user = alice
  roles = ROLE_USER

Bearer access token:
  sub = alice
  aud = orders-api
  scope = orders.read
```

Dù danh tính tương tự, hai credential có lifecycle, audience, scope và khả năng thu hồi khác nhau. Không thay thế credential API bằng session chỉ vì `principal.getName()` trùng nhau.

---

## 7. Ma trận những trường hợp kết hợp credential

Giả sử `/api/orders/42` yêu cầu Bearer token có `SCOPE_orders.read`, và API chain thực sự không đọc session authentication.

| Cookie session | Authorization header | API chain diễn giải | Kết quả điển hình |
|---|---|---|---|
| Không | Không | Thiếu Bearer | `401 Bearer` |
| Có, hợp lệ | Không | Vẫn thiếu Bearer | `401 Bearer` |
| Không | Basic hợp lệ cho legacy | Sai authentication scheme | `401 Bearer` |
| Có, hợp lệ | Basic hợp lệ | Basic không thay Bearer | `401 Bearer` |
| Không | Bearer JWT hợp lệ, đủ scope | Authentication + authorization đạt | Xử lý endpoint |
| Có, hợp lệ | Bearer JWT hợp lệ, đủ scope | Dùng Bearer; không lấy session làm quyền | Xử lý endpoint |
| Có, hợp lệ | Bearer JWT hết hạn | JWT xác thực thất bại | `401 invalid_token` |
| Có, hợp lệ | Bearer token sai audience | JWT validator từ chối | `401` |
| Không | Bearer hợp lệ, thiếu scope | Authentication đạt, authorization từ chối | `403` |
| Có, hợp lệ | Bearer hợp lệ, thiếu scope | Cookie không thêm quyền | `403` |
| Không | Bearer header sai cú pháp | Resolver từ chối request | Có thể `400 invalid_request` |
| Có, hợp lệ | Bearer hợp lệ nhưng sai tenant | Business authorization từ chối | `403`/`404` theo policy |

Mã trạng thái cụ thể phụ thuộc vào filter/handler và chính sách của ứng dụng, nhưng **kết quả quyền phải nhất quán**: cookie/Basic không bypass yêu cầu Bearer.

Với web chain, kết quả có thể khác:

| Request tới `/web/dashboard` | Session web | Header khác | Kết quả |
|---|---|---|---|
| Không cookie | Chưa login | Không Bearer | Redirect tới login |
| Cookie hợp lệ | Đã login | Không Bearer | Được phép |
| Cookie hợp lệ | Đã login | Bearer JWT sai | Web chain không bật Resource Server, nên JWT header không làm người dùng được/không được login |
| Không cookie | Chưa login | Bearer hợp lệ | Không tự biến Bearer thành web session; thường redirect login |
| Không cookie | Chưa login | Basic hợp lệ | Không tự login nếu web chain không bật Basic |

**Sự có mặt của credential không dùng tới** không phải bằng chứng user được phép truy cập URL. Khi có yêu cầu phát hiện credential mâu thuẫn chặt hơn, hệ thống có thể chủ động từ chối request mang nhiều loại credential, thay vì chỉ bỏ qua credential không được hỗ trợ.

---

## 8. Hai Authorization schemes trong một request: Basic và Bearer không thể “cộng” tùy ý

### 8.1. Một Authorization header đại diện một credential scheme

Ví dụ đúng riêng lẻ:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==
```

hoặc:

```http
Authorization: Bearer eyJhbGciOi...
```

Không tự ghép:

```http
Authorization: Basic c2VydmljZTpwYXNzd29yZA==, Bearer eyJ...
```

với kỳ vọng Spring Security hiểu là hai credential độc lập để chọn cái mạnh hơn. Đây không phải cách biểu diễn một Bearer credential hoặc Basic credential thông thường.

### 8.2. Nhiều Authorization headers có thể tạo ambiguity

Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Authorization: Basic <basic-credential>
Authorization: Bearer <bearer-token>
```

Reverse proxy, Servlet container và frameworks có thể xử lý header trùng theo cách khác nhau, như chỉ đọc giá trị đầu, kết hợp, hoặc từ chối. Nếu gateway và backend **diễn giải khác nhau**, có thể phát sinh authentication confusion.

**Thiết kế an toàn:** Trong vùng yêu cầu một credential chính, chuẩn hóa hoặc từ chối duplicate/malformed Authorization headers tại một ranh giới nhất quán. Không trông chờ `request.getHeader("Authorization")` luôn phản ánh mọi giá trị được gửi.

### 8.3. Custom detection phải xét cả gateway và backend

Một `OncePerRequestFilter` có thể kiểm tra số giá trị `Authorization` được Servlet nhìn thấy và từ chối khi không phù hợp. Ví dụ minh họa:

```java
package com.example.security;

import java.io.IOException;
import java.util.Collections;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.web.filter.OncePerRequestFilter;

public class DuplicateAuthorizationHeaderFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        int headerCount = Collections.list(
            request.getHeaders(HttpHeaders.AUTHORIZATION)).size();

        if (headerCount > 1) {
            response.sendError(
                HttpServletResponse.SC_BAD_REQUEST,
                "Multiple Authorization headers are not supported");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Đây là **minh họa về nguyên tắc**, không phải một lớp hoàn chỉnh bảo vệ mọi kiểu header smuggling. Nếu proxy đã gộp các header vào một giá trị trước Servlet, filter chỉ thấy một giá trị. Cần quy tắc normalization thống nhất ở gateway/ingress và HTTP server.

Nếu thêm custom filter vào Spring Security, phải xác định vị trí chạy trong đúng API chain hoặc policy gateway; không tự tạo một Servlet filter global rồi vô tình thay đổi login web hoặc không chạy trước proxy.

### 8.4. Không sửa bằng cách “thử tất cả rồi chọn credential thành công”

Pseudo-code không an toàn:

```text
if bearer is valid:
    use bearer
else if basic is valid:
    use basic
else if session exists:
    use session
```

Khi Bearer hết hạn hoặc bị thu hồi, Client vẫn có thể dùng Basic/session để vượt qua giới hạn token. Nếu doanh nghiệp muốn hỗ trợ **một trong nhiều cơ chế**, phải có policy phân quyền, ưu tiên, xử lý lỗi và phạm vi được thiết kế công khai; không chỉ là vòng lặp “thử đến khi thành công”.

---

## 9. Đường kiến trúc khuyến nghị: API Bearer, legacy Basic và browser session tách chain

### 9.1. Dependency Gradle

Ví dụ Spring Boot Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Ví dụ sau dùng Spring Security có `SecurityFilterChain` và lambda DSL; cần điều chỉnh theo phiên bản Spring Boot/Spring Security thực tế. Nếu dùng WebFlux, hãy xem mục dành cho `SecurityWebFilterChain`.

### 9.2. Cấu hình issuer cho JWT API

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
```

Issuer chỉ là placeholder. API cần kiểm tra chữ ký, issuer, thời hạn và **audience của `orders-api`** theo hợp đồng token. Nếu ứng dụng dùng opaque token, thay cấu hình JWT bằng introspection phù hợp.

### 9.3. Ba `SecurityFilterChain` rõ ràng

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class MultiMechanismSecurityConfig {

    // REST API: chỉ chấp nhận OAuth Bearer access token.
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    // Legacy service endpoint: chỉ Basic, read-only trong ví dụ.
    @Bean
    @Order(2)
    SecurityFilterChain legacyBasic(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/internal/legacy/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/internal/legacy/**")
                    .hasRole("LEGACY_READER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Browser website: session + form login, catch-all cuối.
    @Bean
    @Order(3)
    SecurityFilterChain browserWeb(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/assets/**",
                    "/favicon.ico",
                    "/error",
                    "/login")
                    .permitAll()
                .requestMatchers("/web/admin/**")
                    .hasRole("WEB_ADMIN")
                .requestMatchers("/web/**")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            .build();
    }
}
```

**Cần hiểu đúng những quyết định trong cấu hình:**

1. `@Order(1)` có matcher `/api/**`; mọi request API vào một chain **chỉ bật Bearer JWT**.
2. API chain tắt `httpBasic` và `formLogin`, nên không dùng chúng làm fallback.
3. `STATELESS` và `NullSecurityContextRepository` ngăn API chain dùng HTTP session làm SecurityContext authentication. `requestCache.disable()` tránh tạo saved request cho web redirect từ API.
4. `csrf.disable()` chỉ áp dụng ở API chain, với giả định API **thuần Bearer header**, không chấp nhận credential được browser tự gửi.
5. Legacy chain chỉ nhận Basic và **chỉ cho GET read-only** trong bài; vì vậy không đề xuất tắt CSRF cho Basic một cách mặc định. Nếu muốn thêm POST/PUT/DELETE bằng Basic, phải đánh giá CSRF và giới hạn các Client có thể tự gửi credential.
6. Web chain đứng cuối/catch-all, sử dụng session và form login; **không tắt CSRF**.
7. `anyRequest().denyAll()` ngăn các đường ngoài policy ở mỗi chain.
8. Cấu hình Basic ở đây không tự tạo user; cần `UserDetailsService`/authentication provider phù hợp.
9. Các route `/api/orders/**`, `/web/**` và `/internal/legacy/**` phải có Controller tương ứng mới trả được 2xx khi bảo mật cho phép.

**Đây là một cấu hình minh họa của ba vùng URL tách biệt.** Nếu ứng dụng có OAuth2 login/CSRF cookie khác, cần điều chỉnh đúng contract; không đăng ký đồng thời một chain catch-all khác tranh matcher.

### 9.4. Vì sao dùng `NullSecurityContextRepository` ở API?

`SessionCreationPolicy.STATELESS` nói Spring Security không tạo/dùng `HttpSession` để lấy SecurityContext cho cơ chế xác thực của API. Thêm `NullSecurityContextRepository` thể hiện rõ ranh giới: **không tải/lưu Authentication từ session trong API chain**.

Nó không khiến browser ngừng gửi Cookie header. Nó cũng không chặn custom code cố ý đọc `HttpSession`. Hãy tránh custom filter kiểu:

```java
HttpSession session = request.getSession(false);
if (session != null && session.getAttribute("user") != null) {
    allowApiRequest();
}
```

Nếu đặt logic đó trong API request flow, chính code ứng dụng lại phá ranh giới Bearer-only.

### 9.5. Vì sao không disable CSRF trong legacy Basic chain?

HTTP Basic có thể được browser ghi nhớ và tự gửi lại trong một số ngữ cảnh. Nếu Basic endpoint hỗ trợ thao tác thay đổi trạng thái mà browser có thể kích hoạt, nó **có nguy cơ CSRF**.

Ví dụ legacy chain trong bài chỉ cho `GET`, và mặc định CSRF của Spring Security thường không chặn GET vì đây phải là phương thức đọc không tạo side effect. Nếu sản phẩm cần Basic cho POST/DELETE, không giải quyết bằng cách disable CSRF một cách tự động; cần đánh giá cơ chế chứng minh request, nguồn Client và bảo vệ mạng/CSRF phù hợp.

### 9.6. Web chain phải bao phủ `/login` và `/logout`

Khi dùng `formLogin`, endpoint `GET /login` và `POST /login` có thể do Spring Security xử lý, không phải Controller do bạn khai báo. Nếu web chain chỉ match `/web/**`, các login endpoints có thể nằm ngoài chain.

Dùng catch-all cuối giúp bao phủ những endpoint đó. Nếu muốn web chain có matcher hẹp, phải thêm các URL login/logout/OIDC callback tương ứng vào matcher.

---

## 10. Cấp tài khoản thử nghiệm cho Basic và form login

### 10.1. UserDetailsService cho ví dụ lab

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUserConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new InMemoryUserDetailsManager(
            User.withUsername("legacy-reader")
                .password(encoder.encode("demo-legacy-password"))
                .roles("LEGACY_READER")
                .build(),
            User.withUsername("web-user")
                .password(encoder.encode("demo-web-password"))
                .roles("WEB_USER")
                .build());
    }
}
```

Đây là **credential giả lập dành cho môi trường học tập**, không phải password/secret được khuyến nghị cho production.

### 10.2. Dùng cùng UserDetailsService có gây fallback không?

Hai chain có thể dùng cùng `UserDetailsService` nhưng điều đó **không tự khiến web session được chấp nhận trong API Bearer chain**. Ranh giới nằm ở **authentication filters/session context và authorization policy** của từng chain.

Tuy nhiên, việc cho Basic legacy và form login website chia sẻ cùng kho username/password có thể không phù hợp về bảo mật/lifecycle. Khi triển khai thật, thường cần phân biệt service account với human user, giới hạn quyền và kế hoạch loại bỏ Basic.

### 10.3. Không cấp quyền API chỉ nhờ role của Basic user

`legacy-reader` được cấp `ROLE_LEGACY_READER`. Điều đó không tự cấp `SCOPE_orders.read`, và API Bearer chain vẫn phải yêu cầu access token.

Ngược lại, một Bearer token có `SCOPE_orders.read` không tự trở thành username/password Basic hợp lệ ở legacy endpoint.

---

## 11. Bảo đảm JWT được cấp đúng API, không chỉ đúng issuer

### 11.1. Cùng Authorization Server có thể cấp token cho nhiều API

Ví dụ một JWT có payload:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
```

Nó có thể được ký đúng và còn hạn, nhưng `orders-api` **không nên chấp nhận** vì token dành cho `billing-api`.

Không dùng việc tách chain chỉ nhận Bearer như một lý do bỏ issuer/audience validation.

### 11.2. Bean JwtDecoder có audience validator

Ví dụ khi muốn tự cấu hình decoder:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://id.example.com/realms/shop";

        // JWKS URI đã được phê duyệt trong cấu hình server.
        String jwksUri =
            "https://id.example.com/realms/shop/protocol/openid-connect/certs";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder
                .withJwkSetUri(jwksUri)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience));

        return decoder;
    }
}
```

Đây là **phương án tự khai báo decoder thay auto-configuration**, không phải bean phải thêm khi mọi thứ đã cấu hình đúng. Cần xác định JWKS URI, thuật toán ký được phép, issuer, audience và token profile theo hợp đồng AS.

Nếu sử dụng Spring Boot version cung cấp audience property tương ứng, có thể cấu hình theo properties; nhưng **phải kiểm tra behavior thực tế theo version**. Tránh kết luận chỉ có `issuer-uri` là luôn đủ cho audience.

### 11.3. ID token của OIDC login không thay Bearer access token

Sau khi đăng nhập website, một ID token thường có:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": "web-client-id",
  "sub": "user-417"
}
```

Đừng gửi ID token này tới `orders-api`. API cần **OAuth access token** đúng recipient và quyền `orders.read`.

### 11.4. Scope phải được kiểm tra sau authentication

Một Bearer JWT hợp lệ:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-417",
  "scope": "profile.read"
}
```

vẫn không có `SCOPE_orders.read`. Rule `hasAuthority("SCOPE_orders.read")` sẽ từ chối, thường `403 Forbidden`. Đây không phải lỗi mà cookie phiên nên được dùng để “nâng cấp quyền”.

---

## 12. Nếu API dùng opaque token thay JWT

Tách chain không phụ thuộc access token phải có dạng JWT. API có thể introspect opaque token thay vì giải mã:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Và trong API chain, thay:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
```

bằng:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
```

Đây là **hai phương án thay thế theo token contract**, không phải cứ bật cả hai DSL rồi Spring Security tự biết token thuộc issuer nào trong mọi cấu hình.

### 12.1. `active=true` không biến token thành quyền chung

Một introspection response:

```json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-417"
}
```

vẫn không phù hợp `orders-api` nếu API yêu cầu audience này. Cần kiểm tra bằng một `OpaqueTokenIntrospector` decorator hoặc hợp đồng AS–Resource Server xác nhận audience binding.

### 12.2. Introspection lỗi không được fallback sang session

Nếu AS timeout, TLS lỗi hoặc trả `active=false`, API Bearer-only **không được lấy cookie phiên hoặc Basic user** để coi request đã xác thực.

Cần phân biệt:

- `active=false`: token không được AS chấp nhận, thường `401`.
- AS không truy cập được: lỗi xác minh upstream, status có thể là 5xx/challenge tùy handler, nhưng không cấp quyền.
- Token hợp lệ thiếu scope: thường `403`.
- Token đúng scope nhưng sai tenant: từ chối theo business policy.

---

## 13. Web login qua OIDC: thay form login nhưng vẫn giữ session boundary

Nếu website dùng `oauth2Login` thay username/password nội bộ, cần thêm starter OAuth2 Client:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

Ví dụ Client registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://id.example.com/realms/shop
```

Có thể thay `browserWeb(...)` ở cấu hình ba chain bằng web chain dùng:

```java
.oauth2Login(Customizer.withDefaults())
```

thay cho:

```java
.formLogin(form -> form.permitAll())
```

Các URL phổ biến:

```text
/oauth2/authorization/company
/login/oauth2/code/company
```

phải được **web chain chứa `oauth2Login`** xử lý. Nếu web chain chỉ match `/web/**`, callback có thể không được xử lý.

### 13.1. OIDC login không làm API chuyển sang session authentication

Sơ đồ:

```mermaid
sequenceDiagram
    participant B as Browser
    participant WEB as Web chain / OIDC Client
    participant OP as OIDC Provider
    participant API as Bearer API chain

    B->>WEB: GET /web/dashboard
    WEB-->>B: 302 tới OIDC login
    B->>OP: Authorization request
    OP-->>B: Redirect code + state
    B->>WEB: GET /login/oauth2/code/company?code=...
    WEB->>OP: Đổi code, validate OIDC
    OP-->>WEB: Tokens theo OIDC client contract
    WEB-->>B: Session cookie + web redirect
    B->>WEB: GET /web/dashboard + cookie
    WEB-->>B: Trang web authenticated
    B->>API: GET /api/orders/42 + cookie, không Bearer
    API-->>B: 401 Bearer
```

**Một user đã đăng nhập IdP rồi có web session không tự mang OAuth access token hợp lệ tới Resource Server.**

### 13.2. Backend-for-Frontend (BFF) là lựa chọn có chủ đích

Nếu browser không nên giữ access token, web backend có thể nhận cookie session, kiểm tra CSRF/authorization và sử dụng **server-side authorized client** để lấy/gửi access token tới downstream API:

```text
Browser
  → /web/orders + session cookie
     → Web/BFF kiểm tra session + CSRF + tenant
        → Backend gọi orders-api
           Authorization: Bearer <access-token-for-orders-api>
```

Đây là **hai HTTP hops, hai trust contracts**. Không dùng `SecurityContext` của web để vượt qua Resource Server API ngay trong cùng application.

Backend phải quản lý token đúng audience/scope, expiry, refresh, rotation và logout theo hợp đồng; không gửi ID token làm access token.

---

## 14. `401`, `403`, `302` và `WWW-Authenticate` khi có nhiều cơ chế

### 14.1. Vì sao API muốn `401 Bearer`?

Đối với protected Resource Server endpoint không token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Khi token bị từ chối:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Một Bearer token đã xác thực nhưng thiếu scope có thể nhận:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Các tham số header/realm có thể khác theo Spring Security version, exception và custom handler. Thiếu token thường không kèm `invalid_token` vì không có token đã bị xác minh sai.

### 14.2. Legacy Basic muốn challenge khác

Nếu client gọi `/internal/legacy/status` không có Basic credential:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Realm thực tế phụ thuộc cấu hình HTTP Basic entry point. Client có thể hiển thị dialog Basic authentication dựa trên challenge, nhất là browser.

Không muốn API Bearer route trả `Basic` challenge chỉ vì hệ thống còn một legacy chain khác.

### 14.3. Website thường redirect

Với form login, request:

```http
GET /web/dashboard HTTP/1.1
```

khi chưa login có thể nhận:

```http
HTTP/1.1 302 Found
Location: /login
```

HTTP status có thể là loại redirect khác tùy config, nhưng khác về ngữ nghĩa với Bearer challenge của API.

### 14.4. Khi cùng chain hỗ trợ Basic và form login

Spring Security có thể lựa chọn `AuthenticationEntryPoint` theo request matcher/content negotiation và cấu hình exception handling. Ví dụ browser nhận redirect, client API nhận Basic challenge ở một số tổ hợp cấu hình.

**Không lấy `Accept: application/json` hoặc `User-Agent` làm security boundary chính**. Chúng là header Client có thể chỉnh. Một URL/API cần cơ chế xác thực nhất quán phải được tách matcher/chain rõ ràng hoặc có entry point policy tường minh.

### 14.5. Một server có thể gửi nhiều challenge, nhưng không đồng nghĩa tự hỗ trợ fallback

Theo HTTP authentication, response có thể chứa nhiều `WWW-Authenticate` challenges nếu tài nguyên hỗ trợ nhiều scheme. Nhưng việc quảng bá Basic + Bearer **không tự định nghĩa**:

- Credential nào ưu tiên.
- Khi cả hai được gửi thì xử lý thế nào.
- Scheme nào cấp quyền nào.
- Liệu có thể dùng session thay thế hay không.

Nếu hệ thống hỗ trợ nhiều scheme trên cùng endpoint, phải xác định các quy tắc đó trước, không dựa vào challenge như hợp đồng phân quyền đầy đủ.

### 14.6. Bảng status nhanh

| Địa chỉ | Lỗi/điều kiện | Response thường gặp |
|---|---|---|
| `/api/orders/42` | Thiếu Bearer | `401` + `WWW-Authenticate: Bearer` |
| `/api/orders/42` | Bearer sai định dạng | Có thể `400 invalid_request` |
| `/api/orders/42` | Bearer JWT hết hạn/sai chữ ký | `401 invalid_token` |
| `/api/orders/42` | Bearer đúng nhưng thiếu scope | `403` |
| `/api/orders/42` | Chỉ có Basic | `401 Bearer` |
| `/api/orders/42` | Chỉ có web session | `401 Bearer` |
| `/internal/legacy/status` | Thiếu Basic | `401 Basic` |
| `/internal/legacy/status` | Password sai | `401 Basic` |
| `/internal/legacy/status` | Chỉ có Bearer | `401 Basic` |
| `/web/dashboard` | Chưa login | Redirect `/login` |
| `/web/dashboard` | Web session đúng | Cho phép theo web rule |
| `/web/profile` POST | Session đúng, thiếu CSRF | Thường `403` |
| `/api/orders/42` | Bearer đúng, order ngoài tenant | `403`/`404` theo policy |

---

## 15. CSRF: vì sao trộn cookie, Basic và Bearer thay đổi bề mặt tấn công?

### 15.1. CSRF phụ thuộc vào credential có được browser tự gửi hay không

Giả sử browser đã login website qua `JSESSIONID`. Một trang web bên ngoài có thể tìm cách khiến browser gửi một request thay đổi trạng thái tới cùng website. Vì cookie được gửi theo quy tắc browser, server cần cơ chế CSRF bảo đảm request có chủ đích.

Với HTTP Basic, trình duyệt có thể ghi nhớ và tự gửi credential tới protection space phù hợp sau khi user xác thực. Vì vậy Basic **không mặc định miễn CSRF**.

Với API chỉ nhận **Bearer token trong Authorization header do ứng dụng Client chủ động gửi**, một trang ngoài không tự có token để gắn vào header. Đây là lý do nhiều REST API Bearer-only có thể tắt CSRF. Nhưng nếu token nằm trong cookie tự gửi hoặc API còn chấp nhận session/Basic, giả định đó có thể sai.

### 15.2. Ví dụ cấu hình có rủi ro

```java
http
    .csrf(csrf -> csrf.disable())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

Nếu chain này bảo vệ cả website session và API, tắt CSRF ở đây có thể làm các thao tác web bị kích hoạt qua ambient credentials.

### 15.3. Cách tách CSRF theo ranh giới

Trong ví dụ ba chain:

- API Bearer-only: `csrf.disable()` trong API chain khi contract cho phép.
- Web session: **giữ CSRF mặc định**.
- Basic legacy: chỉ read-only trong ví dụ; nếu có write endpoints phải đánh giá CSRF, đặc biệt nếu browser có thể gửi Basic tự động.

**Không tắt CSRF toàn ứng dụng chỉ vì một endpoint POST bị 403 trong lúc thử nghiệm.** Có thể POST web thiếu CSRF token và sự từ chối là đúng.

### 15.4. SameSite và CORS không thay CSRF

`SameSite` có thể giảm một số kiểu gửi cookie cross-site, nhưng không phải giải pháp duy nhất cho CSRF. Có những ngữ cảnh same-site nhưng cross-origin, subdomain hoặc workflow redirect khiến cấu hình cookie phức tạp.

CORS điều khiển browser có được đọc response và thực hiện những cross-origin request theo chính sách hay không. Nó **không tự xác minh user có quyền thay đổi dữ liệu**.

### 15.5. Basic bảo vệ write operations như thế nào?

Nếu hệ thống bắt buộc dùng Basic cho POST/PUT/DELETE, các phương án cần cân nhắc theo threat model:

- Chỉ cho machine clients ở network/private API surface không phục vụ browser.
- Không dựa vào CORS để chặn mọi non-browser clients.
- Bật CSRF token khi endpoint có thể được browser truy cập bằng ambient credential.
- Dùng phương thức client authentication khác như OAuth Client Credentials/mTLS khi khả thi.
- Giới hạn credentials, rate limit, audit và rotation.

Không có một câu “Basic + CSRF disabled luôn an toàn” cho mọi deployment.

---

## 16. Session state và SecurityContext: điểm dễ rò quyền nhất

### 16.1. Cookie có mặt khác session được dùng để xác thực

Một request:

```http
GET /api/orders/42 HTTP/1.1
Cookie: JSESSIONID=<web-cookie>
```

có thể đi vào API chain. Browser vẫn gửi cookie vì cookie `Path=/`, nhưng API chain **không nên khôi phục web Authentication từ session** trong kiến trúc Bearer-only.

Bộ ba trong ví dụ:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.securityContext(context -> context
    .securityContextRepository(
        new NullSecurityContextRepository()))
.requestCache(cache -> cache.disable())
```

giúp thể hiện ý định rõ ràng:

- Không dùng session làm SecurityContext cho API.
- Không lưu SecurityContext Bearer vào session.
- Không tạo request cache để redirect web login từ API.

### 16.2. `STATELESS` không xóa cookie khỏi HTTP request

`STATELESS` không làm HTTP container chặn `Cookie`, và không tự cấm một custom Filter, Controller hoặc library khác gọi `request.getSession()`.

Nên kiểm tra kỹ middleware nội bộ nào:

- Lấy `session.getAttribute("user")` rồi tạo Authentication.
- Đọc `X-User` từ proxy mà không xác minh.
- Lưu JWT Authentication vào session.
- Dùng ThreadLocal/static biến để giữ user request trước.
- Tự tạo “fallback if JWT fails then use session”.

### 16.3. Lưu Bearer Authentication vào session có thể tạo nhầm vòng đời

Trong một chain hỗn hợp, một Bearer request có thể dẫn tới Authentication được lưu vào session nếu custom persistence không được kiểm soát. Request tiếp theo không còn Bearer header nhưng vẫn được coi đã login.

Đối với API yêu cầu token trên mỗi request, điều đó trái contract. Cần dùng session policy và security context repository phù hợp, đồng thời tránh custom code chuyển Bearer Authentication thành web login một cách vô ý.

### 16.4. SecurityContextHolder là theo request/thread, không phải user global

Trong Servlet, `SecurityContextHolder` thường sử dụng ThreadLocal. Spring Security quản lý việc thiết lập/xóa context trong filter chain.

Không tạo một biến static như:

```java
static Authentication lastAuthenticatedUser;
```

để “chia sẻ” user từ Basic/Bearer vào Controller khác. Nó có thể trộn danh tính giữa nhiều request.

### 16.5. Login/logout web không đồng nghĩa token revocation

Xóa `JSESSIONID` hoặc invalidate HTTP session chỉ kết thúc web session. Một JWT Bearer còn hạn **không tự bị thu hồi** vì user logout website.

Ngược lại, một Bearer token hết hạn không tự xóa web session nếu website dùng cookie login.

Khi sản phẩm yêu cầu “logout everywhere”, phải định nghĩa sự liên kết giữa web session, IdP session, OAuth access/refresh tokens và policy thu hồi. Không dựa vào một `/logout` endpoint như giải pháp mặc định cho mọi credential.

---

## 17. Nếu sản phẩm thật sự muốn hỗ trợ nhiều cơ chế trên cùng URL

Có những hệ thống chuyển đổi dần, cần cùng `/api/**` nhận cả Basic và Bearer. Đây là lựa chọn có thể triển khai, nhưng phải **định nghĩa hợp đồng trước khi bật filter**.

### 17.1. Các câu hỏi bắt buộc

1. **Các scheme có quyền như nhau không?** Basic có thể chỉ đọc, Bearer có thể đọc/ghi.
2. **Scheme nào được chấp nhận cho HTTP method nào?** Có thể Basic chỉ GET.
3. **Có dùng session cookie không?** Nếu không, chain phải stateless.
4. **Khi request mang cả cookie và Bearer, xử lý thế nào?** Bỏ qua cookie hay từ chối vì credential conflict?
5. **Nếu Bearer sai, có thử Basic không?** Nên từ chối thay vì âm thầm chuyển đường xác thực.
6. **Nếu Client gửi hai Authorization headers, xử lý thế nào?** Thường nên từ chối.
7. **CSRF có áp dụng không?** Basic có thể là ambient credential trong browser.
8. **Rate limits/audit theo principal nào?** User hay service account?
9. **Làm sao tắt Basic khi migration kết thúc?** Có ngày hết hạn và metrics usage không?

### 17.2. Ưu tiên tách URL hoặc version surface

Thay vì cùng URL nhận cả Basic và Bearer:

```text
/internal/legacy/orders/**  → Basic
/api/orders/**              → Bearer
```

giúp:

- Xác định entry point/challenge rõ ràng.
- Giới hạn quyền legacy.
- Theo dõi và loại bỏ Basic dần.
- Tách CSRF/session/credential handling.
- Giảm khả năng lỗi filter order trở thành lỗ hổng.

Nếu business contract bắt buộc cùng một URL, hãy viết một **custom authentication policy** có kiểm thử đầy đủ và danh sách credential types rõ ràng.

### 17.3. Dùng `authenticated()` thường quá rộng

Trong mixed chain:

```java
.requestMatchers("/api/orders/**").authenticated()
```

cho phép **bất kỳ Authentication được coi là authenticated** đáp ứng, không kiểm tra nguồn credential hay quyền.

Nếu contract yêu cầu Bearer JWT và scope, cần chính sách chặt hơn. Ví dụ dùng `AuthorizationManager` minh họa:

```java
package com.example.shop;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ApiAuthorizationPolicies {

    public static AuthorizationManager<RequestAuthorizationContext>
    jwtOrdersReader() {

        return (authenticationSupplier, requestContext) -> {
            Authentication auth = authenticationSupplier.get();

            boolean jwtAccepted =
                auth instanceof JwtAuthenticationToken
                    && auth.isAuthenticated();

            boolean hasScope = jwtAccepted
                && auth.getAuthorities().stream().anyMatch(
                    authority -> "SCOPE_orders.read".equals(
                        authority.getAuthority()));

            return new AuthorizationDecision(
                jwtAccepted && hasScope);
        };
    }
}
```

Gắn vào matcher:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .access(ApiAuthorizationPolicies.jwtOrdersReader())
```

**Giới hạn của ví dụ:** Đây là policy **chỉ chấp nhận JWT Authentication** và vẫn cần decoder kiểm tra issuer/audience/signature. Nếu API dùng opaque token, Authentication type sẽ khác và policy cần được thiết kế tương ứng. AuthorizationManager cũng **không thay thế việc từ chối request mang credential mâu thuẫn** trước authentication.

Khi dùng chain Bearer-only như mục 9, thường không cần kiểm tra cụ thể `JwtAuthenticationToken` trong mọi rule; `hasAuthority("SCOPE_...")` và việc tách filter mechanism đã thể hiện contract tốt hơn.

### 17.4. Nếu hỗ trợ “Basic hoặc Bearer”, hãy dùng authorization khác theo scheme

Ví dụ business policy có thể là:

```text
Bearer JWT:
  GET orders → requires SCOPE_orders.read
  POST orders → requires SCOPE_orders.write

HTTP Basic:
  GET internal order summary → requires ROLE_LEGACY_READER
  POST/DELETE → never allowed

Web session:
  Not accepted in either API branch
```

Cần encode policy này trong filter/authorization manager và kiểm thử mọi tổ hợp. Không được:

```text
if authenticated:
    allow all order operations
```

Dù nhiều scheme được hỗ trợ, **không có credential nào được dùng để mở rộng quyền của credential còn lại** trừ khi giao thức yêu cầu cơ chế kết hợp và đã được thiết kế rõ.

### 17.5. Khi cả hai được yêu cầu thì khác với “một trong hai”

Một endpoint rủi ro cao có thể yêu cầu **mTLS client certificate + Bearer access token** cùng lúc. Đây là **hai bằng chứng bổ sung**, không phải fallback: thiếu một trong hai phải bị từ chối.

Mô hình đó cần xác minh cả TLS client identity, token sender-binding nếu dùng, audience/scope và quan hệ giữa certificate/client/token. Chỉ bật `x509()` cùng `oauth2ResourceServer()` **không tự động bảo đảm AND của cả hai bằng chứng**; hãy dùng policy phù hợp.

---

## 18. API key, mTLS và gateway headers: các xung đột khác

### 18.1. API key cùng Bearer

Một gateway có thể yêu cầu `X-API-Key` ngoài `Authorization: Bearer`. Hãy xác định:

- API key dùng để **định danh/rate-limit Client** hay là authentication credential đủ cấp quyền?
- Có bắt buộc cả key và Bearer không?
- Nếu key sai nhưng Bearer đúng, request có bị từ chối?
- Nếu Bearer hết hạn nhưng key đúng, request có bị từ chối?
- Tenant của API key và Bearer có cần trùng nhau không?

Một filter xử lý API key tự tạo `Authentication` trước Bearer filter có thể vô tình cho request đi qua `authenticated()` mà không cần Bearer.

### 18.2. mTLS và sender-constrained access token

mTLS client authentication có thể xác thực một thiết bị/service. Nếu token là **certificate-bound access token**, Resource Server còn cần kiểm tra token binding (ví dụ claim/certificate thumbprint theo profile) với chứng thư thực tế được xác minh.

Không cho rằng có một client certificate bất kỳ là đủ để sử dụng một Bearer token được cấp cho certificate khác.

### 18.3. Reverse proxy gắn user header

Ví dụ gateway sau khi xác thực user có thể chuyển:

```http
X-Authenticated-User: alice
X-Authenticated-Tenant: alpha
```

Nếu backend đọc những header này và tạo Authentication mà không bảo đảm request **chỉ tới từ gateway tin cậy**, một Client có thể tự gửi:

```http
X-Authenticated-User: admin
```

để giả mạo danh tính.

Cần bảo đảm:

- Không có đường truy cập backend trực tiếp ngoài gateway.
- Gateway loại bỏ/ghi đè những header Client gửi trước khi thêm identity.
- Kết nối gateway–backend được bảo vệ, có authentication khi cần.
- Backend xác thực tín hiệu nguồn/gateway theo policy.
- Header chỉ có quyền trong **vùng endpoint** được thiết kế cho gateway authentication.

Không để gateway header trở thành fallback cho Bearer API khi token sai.

### 18.4. Một Client ID không thay thế audience

Dù token chứa `client_id=legacy-client`, nó không mặc nhiên là token cho `orders-api` hoặc một user của web session. Cần đối chiếu issuer/audience/scope/client policy riêng.

---

## 19. CORS preflight và các request browser “thiếu token”

### 19.1. Preflight không nhất thiết mang Bearer token

Một SPA khác origin gửi:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Đây là **CORS preflight**, thường không mang Bearer token. Nếu security chain yêu cầu Authentication trước khi CORS được xử lý, browser có thể báo lỗi CORS dù token của request GET thật không sai.

### 19.2. Cấu hình CORS riêng cho API

Ví dụ trong API chain:

```java
.cors(Customizer.withDefaults())
```

và một `CorsConfigurationSource` phù hợp:

```java
@Bean
CorsConfigurationSource apiCorsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Ví dụ cần import `java.util.List` và các lớp CORS của Spring Web. Đây là mô hình API Bearer header **không yêu cầu cross-origin cookies**. Nếu cho phép credentials/cookies qua CORS, phải cấu hình origin chính xác và đánh giá CSRF/cookie policy; không dùng wildcard tùy tiện.

### 19.3. Không sửa CORS bằng cách bỏ authentication

Sai:

```java
.requestMatchers("/api/**").permitAll()
```

chỉ để OPTIONS hoạt động. Điều này có thể công khai cả GET/POST business APIs.

Cần phân biệt preflight với request thật; request thật vẫn phải gửi Bearer token và có scope phù hợp.

### 19.4. Cookie web có thể được browser gửi tới API cùng origin

Khi frontend được phục vụ từ `shop.example.com` và gọi `/api/**` cùng origin, browser có thể gửi `JSESSIONID` tự động. Điều đó không có nghĩa request API đang dùng session authentication.

**Hãy kiểm tra bằng integration test gửi cookie-only tới API**; một unit test chỉ nhìn `Authorization` header sẽ không chứng minh ranh giới session.

---

## 20. Reverse proxy, load balancer và header rewriting

### 20.1. Gateway làm mất Authorization header

Client gửi:

```http
Authorization: Bearer <valid-access-token>
```

nhưng reverse proxy loại bỏ header khi forward. Backend chỉ nhìn thấy Cookie hoặc không có credential. API có thể trả `401`, trong khi Client khẳng định “đã gửi token”.

Cần đối chiếu log **sự hiện diện/scheme**, request ID và hop qua gateway; không ghi giá trị token thật.

### 20.2. Gateway gửi Basic để xác thực tới upstream

Một số hạ tầng dùng HTTP Basic giữa proxy và backend, nhưng frontend Client dùng Bearer. Nếu gateway **thay** `Authorization: Bearer ...` bằng `Authorization: Basic ...` để tự xác thực với backend, Resource Server Bearer filter không còn token người dùng để kiểm tra.

Đây là vấn đề kiến trúc: không thể chỉ nhét hai credential vào cùng header Authorization. Cần cơ chế upstream authentication riêng và thiết kế token forwarding/identity assertion có trust boundary rõ ràng.

### 20.3. URL rewrite có thể chọn nhầm chain

Public URL:

```text
https://shop.example.com/api/orders/42
```

nhưng proxy rewrite thành:

```text
/orders/42
```

trước khi đến Spring Boot. `securityMatcher("/api/**")` có thể không khớp, request rơi vào web catch-all và trả redirect/login hoặc deny.

Kiểm tra request path **mà Servlet application thực sự nhận**, context path và matcher; không làm API chain match tất cả rồi chiếm các endpoint browser.

### 20.4. Ingress và backend phải thống nhất xử lý duplicate Authorization

Nếu một hop chọn header đầu còn hop khác chọn header cuối, attacker có thể tạo request mà proxy đã xác thực theo credential A nhưng backend lại hiểu là credential B.

Chính sách tốt là **từ chối header trùng/không hợp lệ tại ingress**, normalize header trước khi chuyển và có integration tests qua đúng gateway/proxy stack.

---

## 21. Login, logout, session fixation và vòng đời credential

### 21.1. Web session có vòng đời riêng

Web login thường:

1. Nhận credential form/OIDC.
2. Tạo Authentication của browser user.
3. Áp dụng session fixation protection.
4. Lưu SecurityContext theo chính sách web chain.
5. Browser sử dụng session cookie trên request sau.

Cookie nên có `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` và timeout theo deployment. Đừng đặt session ID trong URL/log.

### 21.2. Basic credential có vòng đời khác

HTTP Basic dùng username/password/service secret. Nó có thể bị browser cache, không được tự invalidated bởi web logout.

Cần password rotation, disable service account, rate limit, audit và giới hạn network. Dùng HTTPS vì Base64 không mã hóa credential.

### 21.3. Bearer token cũng có vòng đời khác

JWT access token có `exp`, issuer/audience và có thể có revocation strategy. Opaque token có thể được AS đánh giá `active` khi introspection.

Một token có thể vẫn còn hiệu lực sau web logout cho đến expiry/revocation theo hợp đồng. Không dùng web session logout làm bằng chứng JWT Bearer đã bị thu hồi.

### 21.4. “Logout khỏi tất cả cơ chế” phải thiết kế riêng

Nếu sản phẩm muốn logout toàn bộ:

- Invalidate local web session.
- Kết thúc OIDC/IdP session theo giao thức được hỗ trợ khi phù hợp.
- Thu hồi refresh token/access token khi AS/Client hỗ trợ.
- Vô hiệu hóa legacy Basic/service credentials chỉ khi có yêu cầu riêng, không tự reset password của cả hệ thống.
- Xóa BFF authorized client state/token cache theo chính sách.
- Giám sát sessions/tokens vẫn hoạt động tại những service khác.

Không tạo một endpoint `/logout` trong web chain rồi giả định nó tự vô hiệu hóa mọi token API.

---

## 22. Kiểm thử HTTP bằng curl: nhìn đúng challenge và redirect

Giả sử Spring Boot chạy ở `http://localhost:8080` trong lab. Khi triển khai thật phải dùng HTTPS.

### 22.1. API protected không token

```bash
curl -i 'http://localhost:8080/api/orders/42'
```

Dự kiến `401` kèm `WWW-Authenticate: Bearer`.

### 22.2. API chỉ có Basic

```bash
curl -i -u 'legacy-reader:demo-legacy-password' \
  'http://localhost:8080/api/orders/42'
```

Vì API chain không bật HTTP Basic, request không được coi là Bearer token hợp lệ. Protected API thường trả `401 Bearer`.

**Không dùng lệnh với password thật trong shell history/log**. Đây là credential thử nghiệm.

### 22.3. Legacy endpoint thiếu Basic

```bash
curl -i 'http://localhost:8080/internal/legacy/status'
```

Dự kiến `401` với challenge `Basic`.

### 22.4. Legacy endpoint với Basic phù hợp

```bash
curl -i -u 'legacy-reader:demo-legacy-password' \
  'http://localhost:8080/internal/legacy/status'
```

Nếu Controller tồn tại và đáp ứng, có thể `200 OK`. Nếu chưa có Controller, security có thể cho qua nhưng endpoint trả `404`.

### 22.5. Legacy endpoint chỉ có Bearer

```bash
curl -i -H "Authorization: Bearer $VALID_API_TOKEN" \
  'http://localhost:8080/internal/legacy/status'
```

Bearer không thay thế Basic ở legacy chain; protected endpoint thường trả `401 Basic`.

### 22.6. Web dashboard chưa login

```bash
curl -i 'http://localhost:8080/web/dashboard'
```

Có thể nhận `302 Location: /login`. Không dùng `curl -L` khi cần quan sát redirect đầu tiên.

### 22.7. API với web cookie nhưng không Bearer

```bash
curl -i \
  -H 'Cookie: JSESSIONID=demo-browser-session' \
  'http://localhost:8080/api/orders/42'
```

Theo API Bearer-only chain, thường vẫn nhận `401`. Cookie giả này không phải web session hợp lệ; integration test thực nên dùng cookie phiên **đã tạo qua login** để chứng minh ranh giới session.

### 22.8. API với Bearer token đúng

```bash
curl -i \
  -H "Authorization: Bearer $VALID_API_TOKEN" \
  'http://localhost:8080/api/orders/42'
```

Nếu token đúng chữ ký/issuer/audience và có `orders.read`, request đạt authentication/endpoint authorization, nhưng vẫn cần quyền với order `42`.

### 22.9. API với Bearer token hết hạn + cookie

```bash
curl -i \
  -H "Authorization: Bearer $EXPIRED_API_TOKEN" \
  -H 'Cookie: JSESSIONID=demo-browser-session' \
  'http://localhost:8080/api/orders/42'
```

Phải bị từ chối theo Bearer token. Không được tự fallback sang cookie.

### 22.10. Cẩn thận với debug verbose

`curl -v` có thể in Authorization header chứa token thật; `curl -u` có thể khiến credential được lưu trong command history. Khi chia sẻ kết quả test, **chỉ giữ status, các header đã lọc và correlation ID**, không dán raw token/secret.

---

## 23. Integration test với MockMvc: kiểm tra ranh giới chứ không chỉ scope

### 23.1. Vì sao phải test qua filter chain thực?

Một test Service trả 200 không chứng minh request đã đi đúng chain. Phải kiểm tra:

- URL matcher thực tế.
- API Bearer không sử dụng web session.
- Legacy Basic không sử dụng Bearer.
- Web chưa login redirect.
- Sai credential bị từ chối, không fallback.
- CSRF web còn hiệu lực.
- Bearer đúng authority vẫn cần business authorization.

### 23.2. Ví dụ MockMvc cho status và challenge

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialIsolationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiWithoutBearerReturns401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Bearer")));
    }

    @Test
    void apiDoesNotAcceptLegacyBasic() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(httpBasic(
                    "legacy-reader",
                    "demo-legacy-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void legacyRouteRequiresBasic() throws Exception {
        mvc.perform(get("/internal/legacy/status"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Basic")));
    }

    @Test
    void websiteRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Để test chạy xanh cần:

- Các bean SecurityFilterChain theo mục 9.
- UserDetailsService phù hợp.
- Các handler nếu test quyền thành công.
- JwtDecoder/test JWKS được cung cấp hoặc mock phù hợp khi ứng dụng cần khởi tạo issuer metadata trong test environment.

Đoạn này kiểm tra response semantics, chưa chứng minh JWT signature/audience validator hoạt động.

### 23.3. Test web session thực không được thay bằng `with(user())`

`with(user())` của Spring Security Test tạo Authentication giả lập trên request. Nó **không đại diện** cho browser đã login rồi gửi `JSESSIONID` thật qua chain khác.

Test session boundary nên:

1. Thực hiện `POST /login` với user test và CSRF token.
2. Lấy `MockHttpSession` từ kết quả login.
3. Gọi `GET /web/dashboard` với session đó → được phép.
4. Gọi `GET /api/orders/42` **chỉ với cùng session**, không Bearer → `401`.
5. Gọi API với JWT hợp lệ, đúng scope → được phép theo policy API.

Ví dụ khung:

```java
import org.springframework.mock.web.MockHttpSession;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

MockHttpSession session =
    (MockHttpSession) mvc.perform(
            post("/login")
                .with(csrf())
                .param("username", "web-user")
                .param("password", "demo-web-password"))
        .andExpect(status().is3xxRedirection())
        .andReturn()
        .getRequest()
        .getSession(false);

mvc.perform(get("/web/dashboard").session(session))
    .andExpect(status().isOk());

mvc.perform(get("/api/orders/42").session(session))
    .andExpect(status().isUnauthorized());
```

Đây là **khung integration test**; có thể cần điều chỉnh session creation/login success behavior theo ứng dụng và thêm Controller `/web/dashboard`. Không lưu session ID thật trong log.

### 23.4. Test JWT authority không thay decoder test

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders/42")
        .with(jwt()
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

`with(jwt())` thường tạo `JwtAuthenticationToken` giả lập và **không tự kiểm tra chữ ký/JWKS/issuer/audience**. Nó phù hợp cho rule authorization, nhưng không thể là bằng chứng Bearer token thật được xác thực đúng.

Cần test bổ sung với JWT ký bằng private key thử nghiệm, JWKS stub và decoder thật để xác nhận audience/issuer/expiry và lỗi `invalid_token`.

### 23.5. Test credential conflict chủ động

Nếu policy định nghĩa **reject duplicate Authorization headers**, cần test request qua ingress/container thật hoặc mock gần với production để bảo đảm header normalization không đi ngược nhau.

Nên kiểm tra:

- Hai Authorization headers cùng scheme.
- Một Basic và một Bearer header.
- Authorization header chứa dấu phẩy hoặc khoảng trắng bất thường.
- Bearer token hỏng cùng session cookie đã login.
- Basic sai password cùng session cookie đã login.
- Gateway gắn identity header nhưng Client cũng tự gửi header đó.
- Một header đến qua casing/normalization khác, dù HTTP header name không phân biệt hoa thường.

Test ở mỗi lớp **reverse proxy → Servlet container → Spring Security**, không chỉ unit-test resolver.

---

## 24. Kiểm thử CSRF, Basic và cơ chế khác

### 24.1. Web POST thiếu CSRF

Nếu có endpoint `POST /web/profile`, user đã login:

```java
mvc.perform(post("/web/profile")
        .session(authenticatedWebSession)
        .param("displayName", "Alice"))
    .andExpect(status().isForbidden());
```

Khi CSRF bật, đây có thể là kết quả đúng. Test có `with(csrf())` nên đi qua bước CSRF, nhưng vẫn cần handler/business permission.

### 24.2. Không dùng Basic cho mọi REST write chỉ để tránh token management

Nếu legacy Client cần ghi dữ liệu, việc cho HTTP Basic qua `/api/**` có thể tạo một credential sống lâu được gửi ở nhiều request và khó giới hạn audience/scope. Nên có kế hoạch chuyển sang OAuth Client Credentials hoặc mTLS/sender-constrained token theo kiến trúc.

### 24.3. Test 401/403 không thay test quyền đối tượng

Một Bearer token `SCOPE_orders.read` đúng nhưng thuộc tenant Alpha không được đọc order Beta. Cần test Service/Repository với predicate tenant và owner, không chỉ test `hasAuthority`.

### 24.4. Test “không fallback” là bắt buộc

Các ca đặc biệt quan trọng:

```text
valid_web_cookie + invalid_bearer
  → API must reject

valid_web_cookie + missing_bearer
  → API must reject

valid_basic + missing_bearer
  → API must reject

valid_bearer + missing_basic
  → legacy Basic endpoint must reject

valid_bearer + insufficient_scope
  → API must reject with authorization failure
```

Nếu một ca trên vô tình thành công, đó là dấu hiệu đáng điều tra về chain selection, SecurityContextRepository hoặc custom fallback.

---

## 25. Xử lý lỗi và observability có phân loại

### 25.1. Đừng log raw credentials

Không ghi:

```text
Authorization: Bearer <real-token>
Authorization: Basic <encoded-real-password>
Cookie: JSESSIONID=<real-session>
X-API-Key: <real-key>
introspection client_secret=<secret>
```

Các giá trị đó là credential, có thể bị đánh cắp từ log, tracing hoặc ticket.

### 25.2. Những dữ liệu nên ghi có kiểm soát

| Trường | Ý nghĩa |
|---|---|
| Correlation/request ID | Theo dõi request qua các hops |
| Route pattern | Xác định URL vào API, legacy hay web |
| SecurityFilterChain ID/nhóm | Biết chain thực sự được chọn |
| Credential scheme observed | Bearer, Basic, cookie-only hoặc none, **không giá trị credential** |
| Authentication result category | Missing/malformed/invalid/authenticated |
| Principal type | JWT, opaque, form, Basic, custom |
| Authority policy result | Scope/role đạt hay không |
| Tenant authorization result | Truy cập trong hay ngoài quyền |
| HTTP status và challenge type | `401 Bearer`, `401 Basic`, `302 login`, `403` |
| IdP/JWKS/introspection availability | Phân biệt token sai và hạ tầng lỗi |
| Config revision | Khi migration/thay chain policy |
| Gateway forwarding result | Có header bị strip/rewrite không? |

Cần kiểm soát PII và cardinality; không đưa raw token, user email hoặc session ID vào metric labels.

### 25.3. Log Spring Security ở môi trường phát triển

Ví dụ:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security: DEBUG
```

Mức log này có thể hữu ích khi xác định selected chain/filter, nhưng cần bật có giới hạn và tránh production logs chứa thông tin nhạy cảm.

### 25.4. Phân biệt loại sự cố

**API 302 tới `/login`:** có khả năng đi nhầm web chain hoặc entry point bị cấu hình theo browser.

**API 401 Basic:** có thể Basic entry point đang áp dụng ngoài ý định.

**API có JSESSIONID không token nhưng vẫn 200:** cần xem security context có được đọc từ session hoặc có custom fallback không.

**API có Bearer token sai nhưng vẫn 200:** đặc biệt nguy hiểm; cần xem decoder có thực sự chạy, cache/authentication state và đường lọc credential.

**Legacy Basic với đúng password nhưng 403:** có thể user thiếu `ROLE_LEGACY_READER` hoặc request bị CSRF/authorization khác từ chối.

**Web POST có cookie hợp lệ nhưng 403:** có thể là CSRF protection đang hoạt động, không nên vội tắt.

**Browser báo CORS error:** có thể preflight không được xử lý đúng; kiểm tra CORS trước khi kết luận JWT hỏng.

---

## 26. Ma trận rủi ro và giải pháp

| Sai lầm | Rủi ro/hành vi | Giải pháp |
|---|---|---|
| Một chain hỗn hợp cho cả web và API | Session có thể thỏa `authenticated()` tại API | Tách chain + stateless API |
| API thiếu `securityMatcher` | API chain chiếm toàn web | Matcher rõ và catch-all cuối |
| Web catch-all có `@Order(1)` | API bị redirect login | API chain trước web |
| `anyRequest().authenticated()` trên mixed chain | Mọi credential được coi tương đương | Chính sách theo scheme, scope và route |
| Bearer invalid → fallback session | Token hết hạn/bị thu hồi vẫn truy cập | Fail closed, Bearer-only API |
| Basic invalid → fallback session | Basic policy bị bypass | Tách Basic chain, không fallback |
| Web role được dùng như OAuth scope | Quyền web làm lộ API | Kiểm tra access token và scope |
| Basic và Bearer trong một header | Cú pháp không rõ/không hợp lệ | Một scheme cho mỗi Authorization credential |
| Nhiều Authorization headers | Proxy/backend disagreement | Reject/normalize ở ingress |
| Tắt CSRF toàn ứng dụng | Session/Basic browser dễ bị CSRF | Giữ CSRF web; API Bearer-only mới cân nhắc tắt |
| Bearer lưu cookie nhưng coi miễn CSRF | Ambient credential bị lợi dụng | Threat model theo cách credential được gửi |
| API lấy session từ HttpSession | Vượt ranh giới OAuth | NullSecurityContextRepository/STATELESS + không custom fallback |
| Form login URL ngoài web chain | `/login` lỗi hoặc không được bảo vệ | Catch-all web hoặc matcher bao phủ |
| OIDC callback ngoài web chain | Login flow thất bại | Đảm bảo callback vào `oauth2Login` chain |
| Gateway strip Bearer header | API 401 khó hiểu | Kiểm tra forwarding policy |
| Gateway thay Bearer bằng Basic | Mất user token/giao thức | Upstream credential design riêng |
| Trust `X-Authenticated-User` tự khai | User impersonation | Trust boundary gateway, strip incoming headers |
| Chỉ kiểm tra JWT issuer | Token API khác được nhận | Audience validator |
| Chỉ kiểm tra JWT scope | BOLA/cross-tenant | Repository/Service tenant-owner ACL |
| Dùng ID token OIDC tại API | Token confusion | Chỉ access token đúng audience |
| Không phân biệt 401/403/302 | Client xử lý sai, khó debug | Entry point theo chain |
| Cache Authentication quá rộng | Dùng quyết định quyền cũ | Lifecycle và invalidation theo policy |
| `with(jwt())` test xanh | Bỏ sót decoder bug | Signed JWT integration test |
| Logout web coi như revoke JWT | Token còn hạn vẫn dùng | Token lifecycle/revocation riêng |

---

## 27. Checklist thiết kế cho một hệ thống nhiều cơ chế

Trước khi triển khai, hãy trả lời đầy đủ các nhóm câu hỏi sau.

### 27.1. Vùng bảo vệ

- Những URL nào dành cho browser, API, service account, admin?
- Có endpoint nào thực sự cần nhận nhiều scheme cùng lúc không?
- Có catch-all security chain ở cuối không?
- Có path rewrite/gateway rule nào khiến matcher không khớp không?
- Các endpoint `/login`, `/logout`, OIDC authorization/callback thuộc chain nào?

### 27.2. Credential và state

- API có chỉ nhận Bearer header không?
- Session có được tải/lưu trong API chain không?
- Basic user có quyền gọi API không, hay chỉ legacy routes?
- Nếu cùng request có cookie và Bearer, credential nào được tin?
- Nếu Bearer sai, có cơ chế fallback không? Mặc định nên là **không**.
- Nếu token được lưu trong cookie, CSRF policy có còn đúng không?
- Có trường hợp hai Authorization headers mà proxy/backend xử lý khác nhau không?

### 27.3. Token và quyền

- JWT/opaque token được kiểm tra bởi decoder/introspector nào?
- Issuer, JWKS, algorithm, audience và token profile được định nghĩa ở đâu?
- Scope/authority có prefix đúng `SCOPE_` không?
- Principal từ Basic/session có vô tình mang authorities dùng cho Bearer policy không?
- Tenant/owner/ACL có được kiểm tra tại Service/Repository không?

### 27.4. Browser protection

- Web session cookie có Secure, HttpOnly, SameSite và timeout phù hợp không?
- Form/OIDC login có CSRF/correlation state không?
- Các POST/PUT/DELETE dựa vào cookie hoặc Basic trong browser có CSRF protection không?
- Logout web có invalidates session không?
- Web login có session fixation protection không?

### 27.5. Kiểm thử và vận hành

- Đã test cookie-only API trả 401 chưa?
- Đã test expired Bearer + valid cookie bị từ chối chưa?
- Đã test Basic-only gọi API Bearer bị từ chối chưa?
- Đã test Bearer-only gọi legacy Basic bị từ chối chưa?
- Đã test Basic và Bearer cùng request hoặc header trùng chưa?
- Đã test web redirect, API challenge, CSRF và CORS chưa?
- Đã chạy qua reverse proxy thật chưa?
- Log có ghi lộ credential không?
- Có kế hoạch loại bỏ Basic và migration metrics không?

---

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Website đã login bằng `JSESSIONID`. Điều đó có cho phép gọi API Bearer-only mà không gửi access token không?

**Trả lời:** Không. API chain phải xác thực Bearer token theo hợp đồng; cookie web không thay thế access token.

**Câu 2.** Một request API mang Bearer token hết hạn và web session hợp lệ. Có nên thử session nếu JWT verification thất bại không?

**Trả lời:** Không trong mô hình Bearer-only. Đây là credential fallback gây bypass thời hạn/audience/token policy; request phải bị từ chối.

**Câu 3.** Spring Security có chạy tất cả `SecurityFilterChain` rồi gộp kết quả không?

**Trả lời:** Không. `FilterChainProxy` chọn chain đầu tiên khớp; các chain phía sau không được áp dụng cho request đó.

**Câu 4.** `securityMatcher` khác `requestMatchers` thế nào?

**Trả lời:** `securityMatcher` chọn cả chain; `requestMatchers` xác định rule authorization trong chain đã chọn.

**Câu 5.** Khi bật `formLogin`, `httpBasic` và `oauth2ResourceServer` trong cùng chain, có chắc API chỉ chấp nhận Bearer không?

**Trả lời:** Không. Nếu chain đọc session và rule chỉ `authenticated()`, một loại Authentication khác có thể đáp ứng rule. Cần tách chain hoặc ràng buộc mechanism bằng policy tường minh.

**Câu 6.** Vì sao HTTP Basic không mặc định miễn CSRF?

**Trả lời:** Browser có thể ghi nhớ và tự gửi credential Basic trong protection space, khiến một trang ngoài có thể kích hoạt request đã xác thực tùy điều kiện. Phải đánh giá ambient credential và thao tác state-changing.

**Câu 7.** Nếu Bearer token đặt trong cookie, API có còn được coi miễn CSRF chỉ vì tên token là Bearer không?

**Trả lời:** Không. Khi browser tự gửi cookie chứa credential, threat model thay đổi; phải đánh giá CSRF như cơ chế dựa cookie.

**Câu 8.** HTTP Basic chỉ dùng Base64 có an toàn khi gửi qua HTTP thường không?

**Trả lời:** Không. Base64 là encoding, không phải encryption. Cần HTTPS và bảo vệ username/password như secret.

**Câu 9.** Client gửi hai Authorization headers, một Basic một Bearer. Server nên làm gì?

**Trả lời:** Nên có chính sách reject/normalize nhất quán ở ingress và backend; không giả định mọi hop luôn chọn cùng header hoặc tự ghép hai scheme được hỗ trợ.

**Câu 10.** API không có token nên trả redirect tới `/login` hay `401 Bearer`?

**Trả lời:** Theo contract Resource Server API, thường là `401` với `WWW-Authenticate: Bearer`. Redirect phù hợp hơn cho browser web login.

**Câu 11.** Một token có `SCOPE_orders.read` nhưng `aud=billing-api` có được gọi `orders-api` không?

**Trả lời:** Không nếu API yêu cầu audience `orders-api`. Scope không thay audience.

**Câu 12.** User có `ROLE_WEB_ADMIN` trong session có mặc nhiên sở hữu `SCOPE_orders.write` không?

**Trả lời:** Không. Web role và OAuth access token scope là những nguồn quyền khác nhau; không tự chuyển quyền nếu không có policy rõ ràng.

**Câu 13.** `SessionCreationPolicy.STATELESS` có làm browser ngừng gửi `JSESSIONID` không?

**Trả lời:** Không. Cookie vẫn có thể được gửi, nhưng API chain không nên sử dụng session đó làm SecurityContext authentication.

**Câu 14.** Sau web logout, một JWT Bearer được cấp trước đó có tự hết hiệu lực không?

**Trả lời:** Không mặc định. Nó còn phụ thuộc `exp`, revocation và AS/Resource Server policy, tách khỏi web session.

**Câu 15.** Test dùng `with(jwt())` trả 200 đã chứng minh token JWT thật được xác minh chữ ký đúng chưa?

**Trả lời:** Chưa. Test thường giả lập Authentication; cần integration test với decoder/JWKS và token ký thật để kiểm tra chữ ký/issuer/audience.

**Câu 16.** Nếu phải dùng API key và Bearer cùng lúc, chỉ bật hai filters có đủ để yêu cầu cả hai không?

**Trả lời:** Không. Cần quy tắc “AND” hoặc “OR”, thứ tự/ưu tiên, binding giữa Client và token, xử lý lỗi và authorization cụ thể; không phụ thuộc vào filter order ngẫu nhiên.

**Câu 17.** CORS preflight không có Bearer token có chứng minh API cho phép anonymous truy cập GET/POST không?

**Trả lời:** Không. Preflight chỉ kiểm tra chính sách CORS của browser; request thật vẫn cần credential và scope phù hợp.

**Câu 18.** Gateway có thể chuyển Bearer header sang Basic header để tự xác thực backend mà Resource Server vẫn đọc được Bearer từ cùng header không?

**Trả lời:** Không. Cần thiết kế upstream identity/credential forwarding riêng; một `Authorization` header không tự chứa đồng thời hai credential hợp lệ.

---

## 29. Tài liệu tham khảo

Các nguồn chính thức nên đối chiếu với **phiên bản Spring Security mà project đang dùng**:

- [Spring Security Reference — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, providers.
- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances): nhiều `SecurityFilterChain` và matcher.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Bearer JWT, decoder, authority mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và principal.
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): browser credentials, CSRF policy.
- [Spring Security Reference — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context và HTTP session.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC/browser login.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer transport, `WWW-Authenticate` và lỗi.
- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): HTTP Basic.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `Authorization` và `WWW-Authenticate`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC client và authentication flow.

Với các API như `SecurityFilterChain`, `SessionCreationPolicy`, `JwtDecoder` và `oauth2ResourceServer`, luôn đối chiếu **Javadoc đúng version**. Những đoạn mã ở đây minh họa kiến trúc Servlet Spring Security hiện đại và cần tích hợp theo cấu hình ứng dụng thật.

---

## 30. Ghi nhớ

Trong một ứng dụng có **cookie phiên, HTTP Basic, OAuth Bearer và cơ chế xác thực khác**, lỗi thường không đến từ việc một credential “không tồn tại”, mà từ việc **một credential hợp lệ ở ngữ cảnh A bị chấp nhận ở ngữ cảnh B**.

Các quy tắc quan trọng:

1. **Tách vùng tài nguyên theo cơ chế xác thực** bằng `securityMatcher`, `@Order` và nhiều `SecurityFilterChain` khi phù hợp: API Bearer, legacy Basic, browser session.
2. **Không fallback khi credential đã được trình nhưng thất bại**: Bearer sai không được cứu bằng cookie hoặc Basic; Basic sai không được cứu bằng web session.
3. **Không coi mọi `Authentication` là tương đương**: `authenticated()` một mình có thể quá rộng; API cần đúng token contract, scope, audience, tenant và business ACL.
4. **Giữ CSRF theo credential thực tế**: session cookie/Basic trong browser khác API thuần Bearer header; không tắt CSRF toàn bộ ứng dụng.
5. **Giải quyết duplicate/header ambiguity tại trust boundary**: không ghép Basic và Bearer, không tin header identity từ Client, kiểm tra proxy forwarding.
6. **Phản hồi theo đúng surface**: API dùng `401/403` Bearer, legacy dùng Basic challenge, website dùng login redirect/session.
7. **Kiểm thử cả tổ hợp credential**: cookie-only API, expired Bearer + valid cookie, Basic-only API, Bearer-only legacy, CSRF, CORS, logout và proxy rewrites.

**Thiết kế đúng không phải là “càng nhiều cách đăng nhập càng tốt”, mà là mỗi request chỉ nhận những credential được contract của tài nguyên đó cho phép, và không cơ chế nào âm thầm bypass cơ chế còn lại.**
