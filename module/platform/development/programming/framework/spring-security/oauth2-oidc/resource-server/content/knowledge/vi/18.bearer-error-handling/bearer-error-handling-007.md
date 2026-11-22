# AuthenticationException, AccessDeniedException và ranh giới xử lý

## 1. Vì sao phải phân biệt lỗi xác thực và lỗi phân quyền?

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, API nhận request như sau:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...
```

Trước khi controller được thực thi, nhiều lớp của Spring Security có thể tham gia:

1. Tìm và tách Bearer token từ HTTP request.
2. Kiểm tra token bằng `JwtDecoder` hoặc `OpaqueTokenIntrospector`.
3. Tạo `Authentication` đã xác thực, kèm scopes/authorities.
4. Kiểm tra điều kiện HTTP authorization, ví dụ `hasAuthority("SCOPE_orders:read")`.
5. Kiểm tra điều kiện ở service/method và quyền sở hữu tài nguyên.

Khi một bước thất bại, Spring Security cần trả về thông điệp đúng ý nghĩa: **token không được chấp nhận** hay **token đã được chấp nhận nhưng thiếu quyền**. Hai trường hợp này đi qua những cơ chế exception khác nhau:

- **`AuthenticationException`** biểu diễn lỗi trong quá trình authentication, ví dụ token bị từ chối vì sai chữ ký, hết hạn hoặc không hợp lệ theo contract.
- **`AccessDeniedException`** biểu diễn quyết định từ chối một thao tác đã được yêu cầu. Nó có thể xuất hiện khi token hợp lệ nhưng thiếu authority, hoặc khi method security từ chối truy cập đối tượng.

Tuy nhiên, không có quan hệ “mọi `AuthenticationException` chắc chắn do `ExceptionTranslationFilter` xử lý” hoặc “mọi `AccessDeniedException` đều trả 403”. **Vị trí phát sinh lỗi, trạng thái người gọi và filter/handler đang có quyền xử lý** sẽ quyết định nhánh thực tế.

Bài học tập trung vào **ranh giới xử lý** của hai họ exception trong Spring Security Servlet stack, cách Resource Server tạo phản hồi **HTTP 401/403** và header **`WWW-Authenticate: Bearer`** theo **RFC 6750**, cách tùy chỉnh đúng điểm mở rộng, cùng các kịch bản kiểm thử để bảo vệ contract API.

> **Phạm vi:** Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet MVC, access token JWT hoặc opaque token. Một số tên lớp/method có thể thay đổi theo phiên bản cụ thể; cần tham chiếu API của phiên bản dự án trước khi nâng cấp. Tên issuer, endpoint, scopes và token trong bài đều là ví dụ.

## 2. Hai loại từ chối không giống nhau

Giả sử API có hai endpoint:

```text
GET  /api/orders/{id}   → cần SCOPE_orders:read
POST /api/orders        → cần SCOPE_orders:write
```

Một request `GET` có thể thất bại vì:

| Trường hợp | Authentication | Authorization | Lỗi dự kiến ở mức logic |
|---|---|---|---|
| Không gửi Bearer token | Không có principal phù hợp | Route yêu cầu xác thực | Khởi động quá trình authentication, thường 401. |
| Bearer token hết hạn | Token bị từ chối | Không xét quyền tiếp | Authentication failure, thường 401. |
| JWT sai chữ ký | Token bị từ chối | Không xét quyền tiếp | Authentication failure, thường 401. |
| JWT đúng chữ ký nhưng sai issuer/audience | Token không đạt hợp đồng của API | Không xét quyền tiếp | Authentication failure, thường 401. |
| Token hợp lệ, chỉ có `SCOPE_orders:write` | Đã xác thực | Thiếu `SCOPE_orders:read` | Access denied, thường 403. |
| Token hợp lệ, có `SCOPE_orders:read` nhưng order thuộc user khác | Đã xác thực | Không có quyền trên object | Access denied hoặc 404 theo policy dữ liệu. |
| Token hợp lệ, có scope, order thuộc chủ thể | Đã xác thực | Được phép | Tiếp tục thực thi nghiệp vụ. |

Trong OIDC, không dùng **ID Token** làm Bearer credential của Resource Server chỉ vì nó có chữ ký hợp lệ. API phải xác định access token đúng issuer, audience, loại token và hồ sơ claims. Trường hợp sai audience/loại token thuộc bước authentication/token validation, không giải quyết bằng cách tăng scope.

### 2.1. Authentication không có nghĩa đủ scope

`authenticated()` kiểm tra tình trạng xác thực, không tự suy luận access token có đủ `orders:read`.

```java
// Chỉ yêu cầu caller đã xác thực; không bảo đảm đủ scope.
.requestMatchers("/api/orders/**").authenticated()
```

Một route cần quyền thao tác cụ thể nên có:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders:read")
```

Dù vượt qua `hasAuthority`, ứng dụng vẫn phải kiểm tra owner, tenant, account, ACL và quy tắc trạng thái tài nguyên; scope không mặc nhiên cho xem tất cả đơn hàng.

### 2.2. Exception không phải mã HTTP

**`AuthenticationException` và `AccessDeniedException` là khái niệm Java/Spring Security**, không phải những response HTTP được viết sẵn. Các lớp khác nhau có trách nhiệm chuyển exception thành response:

- **`AuthenticationEntryPoint`** khởi tạo câu trả lời yêu cầu/không chấp nhận xác thực, thường dùng cho 401.
- **`AccessDeniedHandler`** xử lý quyết định từ chối quyền, thường dùng cho 403.
- **`AuthenticationFailureHandler`** có thể được filter xác thực gọi trực tiếp khi attempt authentication thất bại.
- **`ExceptionTranslationFilter`** chặn một số exception từ các filter/handler downstream và chọn entry point hoặc denied handler.
- **Spring MVC `HandlerExceptionResolver` / `@ControllerAdvice`** xử lý exception được MVC nhìn thấy; không bao phủ tất cả exception xảy ra trước controller.

Nói “throw `AccessDeniedException` là Spring tự trả đúng 403 ở mọi nơi” là một cách hiểu nguy hiểm, bởi đường xử lý exception phụ thuộc vị trí và bộ lọc có bắt được lỗi hay không.

---

## 3. Các lớp chính của Spring Security Servlet

Một filter chain của JWT Resource Server thường có những thành phần liên quan:

| Thành phần | Vai trò | Điểm cần chú ý |
|---|---|---|
| **`FilterChainProxy`** | Chọn và chạy một `SecurityFilterChain` phù hợp HTTP request. | Endpoint không khớp chain được bảo vệ có thể không áp dụng rule kỳ vọng. |
| **`BearerTokenAuthenticationFilter`** | Tách Bearer token và yêu cầu authentication qua `AuthenticationManager` hoặc resolver. | Có cơ chế xử lý lỗi authentication riêng; không chỉ trông vào `ExceptionTranslationFilter`. |
| **`JwtAuthenticationProvider`** | Dùng `JwtDecoder` xác minh JWT và chuyển thành authentication. | Decoder/validator thất bại thường được chuyển thành authentication failure. |
| **`OpaqueTokenAuthenticationProvider`** | Introspect opaque token và tạo authentication. | Lỗi token inactive khác lỗi network/credential tới AS. |
| **`ExceptionTranslationFilter`** | Chuyển `AuthenticationException`/`AccessDeniedException` từ chain phía sau thành hành vi HTTP security. | Chỉ bắt exception xảy ra trong phạm vi `filterChain.doFilter(...)` mà nó bao quanh. |
| **`AuthorizationFilter`** | Áp dụng HTTP authorization qua `AuthorizationManager`. | Khi từ chối có thể ném `AccessDeniedException` hoặc subclass tương ứng. |
| **`BearerTokenAuthenticationEntryPoint`** | Tạo Bearer challenge theo RFC 6750 cho authentication failure. | Thường trả 401 và `WWW-Authenticate: Bearer`, có chi tiết phụ thuộc OAuth2 error. |
| **`BearerTokenAccessDeniedHandler`** | Xử lý access denial cho Bearer token context. | Thường trả 403; có thể gắn `insufficient_scope` khi biết caller đã xác thực bằng OAuth2. |
| **`SecurityContextHolder`** | Lưu authentication trong context request hiện tại. | Không tự suy diễn từ raw token khi context không có authentication đáng tin. |

### 3.1. Luồng xử lý một request

```mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy / SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Có Bearer token?"}
    D -->|Có| E["AuthenticationManager"]
    E --> F{"JWT verify / introspection thành công?"}
    F -->|Không| G["AuthenticationFailureHandler"]
    G --> H["BearerTokenAuthenticationEntryPoint → 401 / challenge"]
    F -->|Có| I["Authentication trong SecurityContext"]
    D -->|Không| J["Tiếp tục với context chưa xác thực"]
    I --> K["ExceptionTranslationFilter"]
    J --> K
    K --> L["AuthorizationFilter / MVC / method security"]
    L --> M{"Bị từ chối?"}
    M -->|Không| N["Controller / Service"]
    M -->|Có, AccessDeniedException| O{"Caller đã xác thực phù hợp?"}
    O -->|Không hoặc anonymous| P["AuthenticationEntryPoint → 401"]
    O -->|Có| Q["AccessDeniedHandler → 403"]
    L -->|AuthenticationException| P
```

Sơ đồ cố ý nhấn mạnh hai điểm:

1. **Lỗi của `BearerTokenAuthenticationFilter` có thể được xử lý tại chính filter đó** bởi failure handler, trước khi exception đi tới `ExceptionTranslationFilter`.
2. `ExceptionTranslationFilter` nằm ở vị trí có thể bao quanh phần authorization downstream. Nó không phải một `try/catch` toàn bộ ứng dụng đặt ngoài mọi filter.

Thứ tự chính xác và các filter có mặt phụ thuộc cấu hình Spring Security. Khi có custom filters, multiple chains hoặc alternative authentication, phải xác nhận chúng nằm ở phía nào của ranh giới xử lý.

## 4. `AuthenticationException`: thất bại ở xác thực

`org.springframework.security.core.AuthenticationException` là superclass của các exception biểu diễn vấn đề xác thực. Các nhánh quen thuộc gồm:

- `BadCredentialsException`: credential được đưa ra nhưng không được chấp nhận trong nhiều kiểu authentication.
- `AuthenticationCredentialsNotFoundException`: không có authentication phù hợp ở nơi đòi xác thực.
- `InsufficientAuthenticationException`: mức xác thực hiện tại chưa đủ cho hành động cần thực hiện.
- `OAuth2AuthenticationException`: lỗi trong ngữ cảnh OAuth 2.0, có thể chứa đối tượng `OAuth2Error`.
- `InvalidBearerTokenException`: một loại lỗi Bearer token trong Spring Security Resource Server, với thông tin OAuth2 error tương ứng.

Không cần code ứng dụng tự ném những exception này ở mọi lớp. Thường **framework provider/filter** quyết định exception phù hợp khi xử lý token.

### 4.1. Ví dụ JWT hết hạn

`JwtDecoder` đọc Bearer JWT và kiểm tra chữ ký/claims. Nếu `exp` hết hạn, quá trình decode/validate thất bại. Thông qua authentication provider và filter, lỗi này thường được chuyển tới Bearer authentication failure handling.

```text
Authorization: Bearer <expired-JWT>
        ↓
BearerTokenAuthenticationFilter
        ↓
JwtAuthenticationProvider → JwtDecoder
        ↓
JWT validation fails
        ↓
Authentication failure handling
        ↓
HTTP 401 + WWW-Authenticate Bearer challenge
```

Ví dụ phản hồi theo kiểu RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

Header chính xác, realm, description và các security headers khác phụ thuộc handler, request, cấu hình và phiên bản. Đừng khẳng định response body sẽ luôn chứa JSON hoặc luôn có cùng `error_description`.

### 4.2. Thiếu Bearer token

Một request không gửi Authorization header có thể đi qua `BearerTokenAuthenticationFilter` **mà không phát sinh lỗi ngay**: filter không thấy token thì cho request tiếp tục. Khi đến `AuthorizationFilter`, route yêu cầu authentication/authority sẽ không được cấp quyền, và `ExceptionTranslationFilter` chọn `AuthenticationEntryPoint` vì caller chưa xác thực hoặc đang anonymous.

```text
GET /api/orders/42
(no Authorization header)
        ↓
BearerTokenAuthenticationFilter: không có token, tiếp tục
        ↓
AnonymousAuthenticationFilter (nếu cấu hình)
        ↓
AuthorizationFilter: thiếu quyền
        ↓
ExceptionTranslationFilter: anonymous/unauthenticated
        ↓
AuthenticationEntryPoint
        ↓
HTTP 401 + WWW-Authenticate: Bearer
```

Điều này giải thích tại sao **cùng một HTTP 401** có thể đến từ hai ranh giới khác nhau: failure handler của authentication filter hoặc entry point do `ExceptionTranslationFilter` gọi.

### 4.3. Header Bearer malformed

Một request có cú pháp sai, trộn nhiều phương pháp truyền token hoặc gửi token sai định dạng có thể bị Bearer token resolver từ chối trước khi JWT decoder được gọi.

Ví dụ cố tình không nên chấp nhận như hai token tương đương:

```http
GET /api/orders/42?access_token=token-B HTTP/1.1
Authorization: Bearer token-A
```

Mặc định Spring Security thường lấy Bearer token từ `Authorization` header; khả năng dùng query/form tùy `BearerTokenResolver` và cấu hình. RFC 6750 đặt các ràng buộc nhằm tránh truyền token bằng nhiều phương pháp trong một request. Không tự cho phép query parameter `access_token` vì có nguy cơ token rò vào log, browser history và proxy.

Với lỗi cú pháp `invalid_request`, RFC 6750 gợi ý HTTP **400 Bad Request** trong những trường hợp phù hợp; với `invalid_token` thường là **401**. Do đó câu “mọi `AuthenticationException` luôn trả 401” là không chính xác. `BearerTokenAuthenticationEntryPoint` có thể sử dụng HTTP status trong `BearerTokenError` nếu exception mang thông tin OAuth2 error phù hợp.

### 4.4. Trường hợp không phải AuthenticationException

Một `JwtException`, lỗi Jackson, timeout tới JWKS, lỗi HTTP introspection hoặc `IllegalArgumentException` **không nhất thiết là `AuthenticationException` tại nơi đầu tiên phát sinh**. Provider hoặc filter có thể bọc/chuyển lỗi theo cơ chế thư viện; nếu một custom component ném exception tùy ý, nó có thể đi thành **500** thay vì được chuyển sang Bearer authentication entry point.

Vì vậy, custom `JwtDecoder`/`OpaqueTokenIntrospector` phải giữ **exception contract** của API Spring Security mà nó cài đặt. Không bắt tất cả exception rồi trả về một principal “đã authenticated” khi token chưa được xác minh.

---

## 5. `AccessDeniedException`: người gọi không được phép thực hiện thao tác

`org.springframework.security.access.AccessDeniedException` xuất hiện khi một authorization decision không cho phép thao tác. Trong Spring Security 6.x, một số authorization API có thể dùng subclass như `AuthorizationDeniedException`.

Ví dụ:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders:read")
    .anyRequest().denyAll())
```

JWT hợp lệ chỉ có:

```json
{
  "sub": "alice-123",
  "scope": "orders:write",
  "aud": ["orders-api"]
}
```

`JwtGrantedAuthoritiesConverter` có thể tạo authority `SCOPE_orders:write`. Khi gọi `GET /api/orders/42`, request vẫn thiếu `SCOPE_orders:read`. `AuthorizationFilter` sẽ từ chối, và trong một Bearer Resource Server thông thường, `ExceptionTranslationFilter` dùng `AccessDeniedHandler` để trả **403**.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Đây là response *điển hình*, không phải bảo đảm rằng mọi HTTP 403 đều gắn đúng chuỗi `insufficient_scope`; `BearerTokenAccessDeniedHandler` chỉ có thể cung cấp thông tin OAuth2 phù hợp khi nhận biết trạng thái authentication tương ứng.

### 5.1. Một exception nhưng hai đường trả lời khác nhau

`ExceptionTranslationFilter` thường phân biệt theo **trạng thái authentication**:

| Exception mà filter xử lý | Trạng thái caller | Nhánh thường dùng |
|---|---|---|
| `AuthenticationException` | Bất kỳ | `AuthenticationEntryPoint`. |
| `AccessDeniedException` | Anonymous hoặc authentication chưa đủ theo `AuthenticationTrustResolver` | Khởi động authentication qua `AuthenticationEntryPoint`. |
| `AccessDeniedException` | Principal đã xác thực phù hợp | `AccessDeniedHandler`. |

Vì sao anonymous bị từ chối lại thường là **401** thay vì 403? Vì user chưa cung cấp một credential xác thực hợp lệ. API cần gửi Bearer challenge, cho client biết nó phải cung cấp token. Sau khi token hợp lệ nhưng quyền vẫn thiếu mới là tình huống thường diễn đạt bằng **403**.

Nếu ứng dụng dùng pre-auth, remember-me hoặc nhiều cơ chế authentication, `AuthenticationTrustResolver` và ngữ cảnh có thể ảnh hưởng cách Spring hiểu “đã xác thực đủ hay chưa”. Không giả định mọi `Authentication` object tự tạo đều được Spring tin ở mức như JWT đã verified.

### 5.2. BOLA/IDOR: scope hợp lệ vẫn có thể bị denied

Alice có token hợp lệ chứa `SCOPE_orders:read` nhưng cố đọc đơn của Bob:

```http
GET /api/orders/order-bob-200 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
```

HTTP rule có thể cho request qua vì đủ scope. Service vẫn phải kiểm tra owner/tenant. Ví dụ:

```java
if (!order.getOwnerSubject().equals(actor.subject())) {
    throw new AccessDeniedException("Order is not accessible");
}
```

Một policy khác có thể chọn trả **404 Not Found** khi muốn che giấu sự tồn tại của order không thuộc quyền; đó là quyết định nghiệp vụ/riêng tư, không phải thay thế cho kiểm tra authorization. Không đưa owner user ID hoặc tenant bí mật vào error body.

### 5.3. Exception ở service có tự thành 403 không?

Nếu service được controller gọi trong **luồng HTTP Servlet đang đi qua Spring Security filter chain**, và exception không bị Spring MVC xử lý trước, `AccessDeniedException` có thể truyền ra khỏi `DispatcherServlet` tới `ExceptionTranslationFilter` để được xử lý.

Nhưng điều này **không bảo đảm trong mọi kiến trúc**:

- Một `@ControllerAdvice`/`HandlerExceptionResolver` có thể xử lý exception **trong Spring MVC** trước khi nó ra tới filter.
- Một custom filter chạy **trước** `ExceptionTranslationFilter` có thể ném exception không nằm trong catch của filter đó.
- Một thao tác **async/background job/message listener** không đi qua HTTP filter chain giống request đồng bộ.
- Một service được gọi từ một entry point khác có thể cần translation policy riêng.

Do đó đối với object-level denial, cần **thống nhất ai sở hữu việc chuyển lỗi thành HTTP**: để exception truyền ra security handler hoặc chuyển thành một domain exception với MVC mapping được thiết kế rõ ràng. Tránh hai lớp cùng viết response.

---

## 6. `ExceptionTranslationFilter` làm gì và không làm gì?

Tên `ExceptionTranslationFilter` dễ khiến người học tưởng đây là “global exception handler” cho toàn bộ application. Thực tế nó là một **security filter**:

- Chạy quanh phần filter chain phía sau bằng `chain.doFilter(...)`.
- Nhận diện `AuthenticationException` và `AccessDeniedException` phát sinh trong phạm vi đó, kể cả khi exception bị bọc bên trong một số servlet exceptions theo cơ chế Spring.
- Dựa vào tình trạng authentication để chọn `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`.
- Có thể dùng `RequestCache` trong đường khởi động authentication; với API stateless thường không muốn lưu request trong session.

### 6.1. Ranh giới vị trí

```mermaid
flowchart LR
    A["Filter ở trước ExceptionTranslationFilter"] --> E["ExceptionTranslationFilter"]
    E --> Z["AuthorizationFilter / DispatcherServlet / Controller"]
    A --> B["Lỗi ngay tại filter trước"]
    B --> C["Không tự được ETF catch"]
    Z --> D["Exception truyền ngược lên"]
    D --> E
    E --> F["AuthenticationEntryPoint hoặc AccessDeniedHandler"]
```

Trong một pipeline thông thường, `BearerTokenAuthenticationFilter` xử lý lỗi do chính nó gặp bằng failure handler. Nó không cần dựa vào `ExceptionTranslationFilter` đứng ở vị trí khác để catch những lỗi đó.

Nếu bạn thêm custom filter xử lý Bearer token trước Spring Security hoặc custom authentication filter, cần xác định:

1. Filter nằm trước hay sau `ExceptionTranslationFilter`?
2. Có thực sự chạy trong `FilterChainProxy` hay được Servlet container đăng ký ngoài chain?
3. Nó ném loại exception nào?
4. Ai chịu trách nhiệm clear SecurityContext và trả response khi authentication fail?
5. Nó có gọi `chain.doFilter(...)` sau khi response đã được gửi hoặc bị commit không?

Không có “global catch” tự động cho mọi filter.

### 6.2. Ranh giới response đã commit

Nếu một filter/controller đã ghi dữ liệu và commit response, handler không thể an toàn đổi status thành 401/403 và viết thêm Bearer challenge. `ExceptionTranslationFilter` có thể báo lỗi khi phát hiện không thể xử lý exception vì response đã committed.

Quy tắc thiết kế:

- Xác minh Bearer token và authorization **trước khi** gửi dữ liệu nhạy cảm.
- Không stream một phần response rồi mới kiểm tra quyền của file/order.
- Không gọi `sendError(...)` sau khi output stream đã được committed.
- Không xử lý lỗi bằng cách vừa ghi JSON vừa gọi delegate entry point/denied handler.
- Với streaming, SSE hoặc async, đặt policy tại boundary trước khi bắt đầu stream và xác định hành vi khi quyền thay đổi trong lúc stream.

### 6.3. Request cache và API stateless

Trong ứng dụng form login, khi chưa đăng nhập, request ban đầu có thể được lưu để tiếp tục sau login. Với Resource Server Bearer token, browser redirect/session request cache thường không phải mục tiêu. Một cấu hình stateless có thể dùng:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.requestCache(cache -> cache.disable())
```

Việc tắt request cache là ví dụ phù hợp với API thuần Bearer. Nhưng nếu ứng dụng đồng thời dùng browser session, SSO login redirect hoặc giao diện MVC, phải thiết kế nhiều `SecurityFilterChain`/authentication policies rõ ràng thay vì tắt tất cả chức năng session một cách máy móc.

---

## 7. `AuthenticationEntryPoint`: ranh giới trả phản hồi khi cần authentication

Giao diện:

```java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
```

Đây là dạng chữ ký khái niệm của interface, với các imports Servlet tương ứng theo phiên bản Spring Security/Jakarta Servlet.

Trong Resource Server, **`BearerTokenAuthenticationEntryPoint`** là implementation phù hợp với RFC 6750. Nó xây dựng `WWW-Authenticate` challenge và status cho các trường hợp xác thực Bearer.

### 7.1. Challenge là gì?

Một response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

nói với client rằng resource mong đợi một Bearer credential. Một số trường hợp có OAuth2 error:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Có thể xuất hiện `realm` hoặc `error_description` nếu handler có dữ liệu và policy cho phép. Tránh phụ thuộc vào wording tiếng Anh của error description trong client logic; ứng dụng nên phân biệt bằng HTTP status và error code chuẩn.

### 7.2. Các lỗi Bearer của RFC 6750

| Mã error | Ý nghĩa | HTTP status điển hình |
|---|---|---|
| **`invalid_request`** | Bearer request sai định dạng/thiếu tham số bắt buộc/truyền token bằng nhiều phương pháp không hợp lệ. | **400 Bad Request** trong các trường hợp được RFC mô tả. |
| **`invalid_token`** | Token hết hạn, bị thu hồi, sai, không hợp lệ theo contract. | **401 Unauthorized**. |
| **`insufficient_scope`** | Request có token nhưng quyền không đủ cho resource. | **403 Forbidden**. |

RFC 6750 không yêu cầu gắn `error` vào mọi challenge khi **request hoàn toàn không cung cấp credential**. Bởi vậy không nên mong đợi mọi 401 đều chứa `error="invalid_token"`. Với no-token, chỉ cần `WWW-Authenticate: Bearer` có thể là hành vi chuẩn.

### 7.3. Không tùy tiện trả 200/302 trong API

Nếu muốn dùng JSON body tùy chỉnh cho lỗi authentication, vẫn cần giữ:

- Status có ý nghĩa 401 (hoặc 400 cho Bearer `invalid_request` phù hợp).
- `WWW-Authenticate` theo Bearer challenge.
- Không tiết lộ raw Bearer token, secret, claim PII.
- Không redirect sang login HTML khi API contract là JSON Bearer Resource Server.
- Không tạo “guest principal” đã xác thực để lấp khoảng trống khi token sai.

Một frontend có thể tự mở trang login khi nhận 401, nhưng API không cần biến mọi authentication failure thành redirect `302`.

---

## 8. `AccessDeniedHandler`: ranh giới trả phản hồi khi quyền không đủ

Giao diện:

```java
package org.springframework.security.web.access;

public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
```

Trong Resource Server Bearer, **`BearerTokenAccessDeniedHandler`** thường được dùng để thể hiện `insufficient_scope` khi caller đã xác thực theo kiểu OAuth2 phù hợp. Với principal không đủ dấu hiệu xác thực OAuth2, handler có thể chỉ trả challenge không có error chi tiết. Điều này giúp tránh đưa ra một khẳng định sai rằng “server đã xác minh token, chỉ thiếu scope” khi authentication state chưa đủ chắc chắn.

### 8.1. 403 không có nghĩa token hỏng

Token hợp lệ nhưng scope thiếu:

```text
JWT signature validation  → PASS
issuer/audience/exp        → PASS
SCOPE_orders:read          → MISSING
                           ↓
AccessDeniedHandler        → 403
```

Client có thể cần xin cấp thêm scope đúng quy trình OAuth (nếu được phép), không đơn giản chỉ refresh cùng một token để tự động tăng quyền.

### 8.2. 403 cũng có thể xuất phát từ ràng buộc khác scope

Ví dụ request đã authenticated, scope đủ nhưng:

- User không thuộc tenant yêu cầu.
- User không sở hữu order.
- Role bị hạn chế theo bộ phận.
- Một hành động cần phê duyệt kép.
- Một endpoint yêu cầu điều kiện feature entitlement.
- CSRF protection từ chối một request dùng cookie/session, vì `CsrfException` thuộc họ access-denied ở Security stack.

Không nên mặc định mọi 403 đều tương đương **`insufficient_scope`**. Nếu tùy chỉnh handler và luôn ghi `error="insufficient_scope"` cho mọi `AccessDeniedException`, có thể làm client hiểu sai rằng chỉ cần xin thêm scope, kể cả khi bị từ chối vì owner/tenant hoặc CSRF.

Một API có thể trả `404` khi resource không thuộc quyền nhìn thấy để tránh object enumeration; đó là quyết định **domain authorization/error policy** riêng. Khi thay mã status, cần kiểm tra điều kiện RFC 6750 và phản hồi đang nằm ở handler nào để không mâu thuẫn ý nghĩa của Bearer challenge.

---

## 9. Cấu hình Spring Boot/Spring Security căn bản

Ví dụ API `orders-api` nhận JWT access token. Nếu dùng Maven với Spring Boot parent/BOM:

```xml
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
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
```

Cấu hình issuer và audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          audiences:
            - orders-api
```

Đây là cấu hình ví dụ cho JWT. Nếu dùng opaque token, chọn `opaquetoken` với introspection URI và credential phù hợp; không mặc định hai cơ chế sẽ tự thay thế nhau khi một cơ chế thất bại.

### 9.1. `SecurityFilterChain` đòi scope rõ ràng

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Chỉ phù hợp API stateless sử dụng Bearer header,
            // không dùng cookie/session làm cơ chế auth chính.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Cấu hình này chỉ xác định **HTTP-level authorization**. Controller/service cần thêm object-level authorization với owner/tenant. Nếu API dùng session cookie, không sao chép `csrf(...disable)` vô điều kiện.

### 9.2. Một route và hai kết quả khác nhau

`GET /api/orders/42`:

| Header và token | Authority | Kết quả thường gặp |
|---|---|---|
| Không có `Authorization` | Không có | 401, Bearer challenge. |
| `Authorization: Bearer ...` hết hạn | Không tạo authentication hợp lệ | 401, có thể `invalid_token`. |
| JWT hợp lệ cho API nhưng không có scope đọc | `SCOPE_profile` | 403, có thể `insufficient_scope`. |
| JWT hợp lệ và đủ scope đọc | `SCOPE_orders:read` | Qua HTTP rule, còn object/business policy. |
| JWT hợp lệ, đủ scope, ID thuộc người khác | `SCOPE_orders:read` | Denied tại service hoặc 404 theo policy. |

Nếu cùng một request trả 302 login page hoặc 200 HTML login form, có khả năng API đã bị cấu hình form login/session entry point khác thay vì Bearer entry point. Cần kiểm tra multiple filter chains và matcher order.

---

## 10. Tùy chỉnh `AuthenticationEntryPoint` và `AccessDeniedHandler` đúng cách

Một nhóm muốn trả JSON nhất quán, ví dụ:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A valid access token is required",
  "requestId": "req-123"
}
```

và:

```json
{
  "code": "ACCESS_DENIED",
  "message": "Access is not permitted",
  "requestId": "req-456"
}
```

Điều có thể làm là **ủy quyền phần Bearer challenge/status cho handler chuẩn**, sau đó thêm phần body an toàn nếu response chưa commit và status phù hợp. Không viết lại toàn bộ RFC 6750 parsing bằng tay chỉ để thay error JSON.

### 10.1. Dùng handler chuẩn cho Bearer

Cấu hình tường minh:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Configuration
public class BearerErrorHandlers {

    @Bean
    AuthenticationEntryPoint bearerEntryPoint() {
        return new BearerTokenAuthenticationEntryPoint();
    }

    @Bean
    AccessDeniedHandler bearerDeniedHandler() {
        return new BearerTokenAccessDeniedHandler();
    }
}
```

Sau đó, trong `SecurityFilterChain` có thể cấu hình:

```java
.oauth2ResourceServer(oauth -> oauth
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

Khi dùng tham số bean injection, `bearerEntryPoint` và `bearerDeniedHandler` phải là bean/injected variables đúng kiểu. Đoạn trên là **mảnh cấu hình để ghép** vào chain hiện hữu, không phải một chain độc lập. Việc khai báo entry point/denied handler qua DSL Resource Server giúp cấu hình theo cơ chế Bearer; nếu có các authentication schemes khác, có thể còn cần `exceptionHandling(...)` và matcher chính xác.

### 10.2. Giải pháp thực dụng: logging/decorating rồi delegate

Không phải mọi API cần JSON body. Nhiều hệ thống giữ response `WWW-Authenticate` mặc định, ghi event/metric riêng và để client đọc HTTP status/error code từ header. Đây là cách giảm nguy cơ tùy chỉnh làm sai semantics RFC 6750.

Ví dụ decorator cho entry point:

```java
package com.example.orders.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

public final class ObservedBearerEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Chỉ ghi mã lý do hữu hạn, path đã chuẩn hóa, request ID.
        // Không ghi raw Authorization header, exception message
        // từ thư viện nếu có thể chứa token/PII.
        recordAuthFailure(request, exception);

        delegate.commence(request, response, exception);
    }

    private void recordAuthFailure(
            HttpServletRequest request,
            AuthenticationException exception) {
        // Tích hợp metrics/logs an toàn tùy ứng dụng.
    }
}
```

Tương tự cho denied handler:

```java
package com.example.orders.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class ObservedBearerDeniedHandler
        implements AccessDeniedHandler {

    private final BearerTokenAccessDeniedHandler delegate =
        new BearerTokenAccessDeniedHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        recordAccessDenied(request, exception);
        delegate.handle(request, response, exception);
    }

    private void recordAccessDenied(
            HttpServletRequest request,
            AccessDeniedException exception) {
        // Tích hợp metrics/logs an toàn tùy ứng dụng.
    }
}
```

Ưu điểm là các chi tiết challenge, `invalid_token`, `insufficient_scope` và status mà Spring Security có thể xác định **được giữ ở implementation chuẩn**. Phương án này không tự viết JSON body.

### 10.3. Khi thực sự cần JSON body

Một pattern có thể:

1. Gọi handler chuẩn để chuẩn bị status và `WWW-Authenticate`.
2. Nếu response chưa committed, status phù hợp, content-type chưa được gửi và error contract cho phép, đặt `application/problem+json` hoặc `application/json`.
3. Ghi body **không chứa token, claim nhạy cảm hay thông tin owner khác**.
4. Không gọi `sendError` sau khi response body đã bắt đầu.
5. Không ghi hai body từ hai handlers khác nhau.
6. Test thực tế qua filter chain và gateway với cả request thiếu token, token sai, scope thiếu.

Cách làm này cần cẩn trọng: một handler chuẩn có thể sử dụng `setStatus` hoặc `sendError` tùy implementation; `sendError` có thể commit hoặc làm container render trang lỗi. **Không mặc định có thể ghi body sau `delegate.commence(...)` ở mọi phiên bản/Servlet container.** Nếu bắt buộc một JSON contract chặt, nên viết handler có kiểm thử integration đầy đủ, tự dựng Bearer challenge theo đúng `BearerTokenError` và status chuẩn, thay vì chồng body không được kiểm soát.

### 10.4. Không để ErrorController che phản hồi Bearer

Spring Boot có error dispatch/mapping (`/error`) và có thể tạo JSON hoặc trang HTML mặc định cho một số lỗi. Security handler có trách nhiệm của nó, không phải mọi 401/403 đều cần đi qua Boot `ErrorController`.

Nếu thấy response `WWW-Authenticate` biến mất sau một custom error handler hoặc error page, phải kiểm tra:

- `sendError`/forward tới `/error`.
- Dispatcher type `ERROR` có bị áp dụng một filter chain khác không?
- Response đã committed hay chưa?
- Một `@ControllerAdvice` có xử lý security exception ở MVC rồi viết response riêng?
- Reverse proxy/gateway có sửa headers không?

Thử response thực qua HTTP, không chỉ gọi method trực tiếp.

---

## 11. Cấu hình `exceptionHandling` và multiple filter chains

Spring Security có DSL:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler))
```

Và Resource Server DSL:

```java
.oauth2ResourceServer(oauth -> oauth
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

Các điểm cấu hình có thể phối hợp hoặc ghi đè tùy cấu trúc chain và phiên bản. Với API thuần Bearer, thường đơn giản nhất là giữ cấu hình Resource Server nhất quán, khai báo đúng entry point/denied handler và integration test response. Nếu app còn dùng form login, Basic, session hoặc endpoint web công khai, hãy tách chain bằng `securityMatcher` và `@Order` nếu thích hợp.

### 11.1. Một ứng dụng vừa có browser UI vừa có API

Ví dụ ý tưởng:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/ping").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/web/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Các imports tương ứng cần có (`@Order`, `@Bean`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`). Đây là **mẫu minh họa tách chains**, chưa phải cấu hình bảo mật hoàn chỉnh: API chain phải thêm scope rules/stateless/CSRF policy; web chain cần CSRF/session policy tương ứng. `@Order` xác định ưu tiên chain; Spring Security chọn **chain đầu tiên khớp**. Nếu `securityMatcher` vô tình phủ trùm rộng, request `/api/**` có thể nhận login redirect của form login hoặc request web có thể đi vào Bearer handler.

### 11.2. Matcher order và security holes

Trong cùng một chain, authorization rules thường được xét theo thứ tự; matcher tổng quát đặt trước matcher riêng có thể khiến quy tắc riêng không còn hiệu lực.

Sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
```

`/api/admin/**` đã khớp rule đầu, nên requirement `ADMIN` ở sau không được áp dụng. Thứ tự đúng hơn:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

Vẫn cần các scopes cụ thể cho API thực tế. Việc thay mọi `hasAuthority` bằng `authenticated()` chỉ để tránh 403 là **privilege broadening**, không phải sửa lỗi.

---

## 12. Ranh giới Spring Security filter và Spring MVC exception handling

Trong ứng dụng Spring MVC, `DispatcherServlet` có hệ thống giải quyết exception riêng:

- `@ExceptionHandler` trong controller.
- `@ControllerAdvice`.
- `HandlerExceptionResolver` / framework resolvers.
- Boot error handling cho exception không được xử lý.

Những cơ chế này không phải phiên bản thay thế hoàn toàn của `AuthenticationEntryPoint` và `AccessDeniedHandler`.

### 12.1. Vì sao `@RestControllerAdvice` không bắt mọi lỗi token?

Lỗi như JWT sai chữ ký xảy ra ở **`BearerTokenAuthenticationFilter`**, **trước** khi request vào controller:

```text
HTTP request
  → Servlet filters / Spring Security
    → BearerTokenAuthenticationFilter: JWT invalid
      → AuthenticationFailureHandler / EntryPoint
  (DispatcherServlet chưa chạy)
```

Vì vậy:

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<?> handle(AuthenticationException ex) {
        // Không được đảm bảo gọi cho lỗi từ BearerTokenAuthenticationFilter.
        return ResponseEntity.status(401).build();
    }
}
```

Đoạn trên không phải cách đáng tin để “bắt mọi 401”. Security filter có quyền xử lý trực tiếp lỗi ngoài MVC. Dùng `AuthenticationEntryPoint` cho lỗi authentication filter/`ExceptionTranslationFilter`; chỉ dùng advice cho exception thực sự nằm trong MVC boundary và được design rõ.

### 12.2. Nếu service ném `AccessDeniedException` thì sao?

Giả sử:

```java
@Service
class OrderService {
    Order getOrder(String id, Actor actor) {
        Order order = repository.findById(id)
            .orElseThrow(NotFoundException::new);

        if (!authorization.canRead(actor, order)) {
            throw new AccessDeniedException("Order forbidden");
        }
        return order;
    }
}
```

Nếu `AccessDeniedException` truyền ra khỏi controller/DispatcherServlet, `ExceptionTranslationFilter` có thể chặn nó khi request nằm trong chain phù hợp. Nhưng một `@ControllerAdvice` quá rộng có thể bắt trước:

```java
// RỦI RO: bắt toàn bộ exception rồi trả 200/400/500 tùy ý.
@ExceptionHandler(Exception.class)
ResponseEntity<?> handleAll(Exception ex) {
    return ResponseEntity.ok(Map.of("error", "failed"));
}
```

Cách trên biến authorization denial thành HTTP 200 — sai cả về an ninh lẫn observability. Nếu cần advice bao phủ domain exceptions, hãy:

- Không biến security exceptions thành success.
- Rõ ràng phân biệt `AccessDeniedException` với lỗi business.
- Không ghi raw token hoặc nội dung nhạy cảm.
- Giữ status/header phù hợp với HTTP/Bearer contract.
- Có integration tests chứng minh request không đủ quyền không lọt vào business logic.

### 12.3. Vấn đề custom servlet filter đặt ngoài Spring Security

Nếu một filter được đăng ký bằng `FilterRegistrationBean` hoặc `@Component` như servlet filter **ngoài `FilterChainProxy`**, cách nó tham gia chain khác với filter được thêm bằng `http.addFilterBefore/After(...)`. Lỗi nó ném có thể không bao giờ tới `ExceptionTranslationFilter`.

Do đó đừng đưa authorization logic nhạy cảm vào một filter bất kỳ rồi kỳ vọng Spring Security tự xử lý lỗi giống filter của framework. Nếu phải có custom filter:

1. Xác định vị trí và lifecycle chính xác.
2. Xác định ai catch failure.
3. Giữ đúng SecurityContext cleanup.
4. Dùng entry point/denied handler có contract rõ nếu response tự do.
5. Kiểm tra behavior trên cả `REQUEST`, `ASYNC`, `ERROR` dispatch khi cần.
6. Tránh double registration cùng một filter ở Servlet container và Spring Security.

### 12.4. Trường hợp phương thức không chạy qua HTTP

Method security cũng có thể được gọi từ scheduled job, messaging consumer hoặc application event listener. Nếu method ném `AccessDeniedException` mà không có một HTTP request đang đi qua `ExceptionTranslationFilter`, **không có Bearer HTTP 403 tự động**. Caller ở các entry points đó phải có domain error policy riêng, ví dụ không ack message, đưa vào DLQ hoặc ghi audit theo yêu cầu. Đừng dùng response HTTP như mô hình chung cho mọi call site.

---

## 13. Chọn exception ở lớp custom đúng ngữ cảnh

Một API có thể có các thành phần tự viết:

- `JwtDecoder` hoặc JWT validator.
- `OpaqueTokenIntrospector` custom.
- `Converter<Jwt, ? extends AbstractAuthenticationToken>`.
- `AuthorizationManager` tùy biến.
- `@PreAuthorize` với authorization bean.
- Domain service kiểm tra owner/tenant.

Mỗi nơi có trách nhiệm khác nhau.

### 13.1. Từ chối token ở authentication boundary

Nếu token thiếu audience bắt buộc, sai issuer hoặc opaque introspection báo inactive, hãy từ chối **trước khi tạo authentication thành công**.

```text
Token có chữ ký hợp lệ nhưng aud không chứa orders-api
      ↓
JWT validator / token contract validator thất bại
      ↓
JwtDecoder / authentication provider
      ↓
Authentication failure (Bearer challenge)
```

Không tạo `JwtAuthenticationToken` đã xác thực rồi ném `AccessDeniedException` sau đó chỉ vì audience sai. Audience là **điều kiện để chấp nhận token làm credential của API**.

### 13.2. Từ chối quyền ở authorization boundary

Nếu token đã hợp lệ, nhưng thiếu `SCOPE_orders:read`, quy tắc HTTP authorization hoặc method authorization từ chối. Không nên giả vờ token sai chữ ký để tạo 401, vì client sẽ khó hiểu nguyên nhân và có thể liên tục refresh token không tăng scope.

Tương tự, nếu token đã authenticated và có scope nhưng không được xem đơn của Bob, domain policy từ chối quyền object.

### 13.3. Lỗi hạ tầng không nên đánh tráo thành token sai

Khi JWKS endpoint, introspection endpoint hoặc database entitlement bị timeout, chương trình **chưa có kết quả đáng tin** để xác thực hoặc cấp quyền. Bảo mật yêu cầu **fail closed**, nhưng phải cân nhắc cách phân loại lỗi:

- JWT signature sai hoặc token inactive: lỗi credential/token.
- Introspection client secret hết hạn: lỗi tích hợp Resource Server–AS.
- AS trả `503`: lỗi dependency.
- Database ownership lookup timeout: lỗi nghiệp vụ/phân quyền chưa thể quyết định.

Không tự làm:

```java
try {
    return introspector.introspect(token);
} catch (Exception ex) {
    return anonymousOrPrivilegedPrincipal();
}
```

Không tự trả `200` vì “AS có thể chỉ đang lỗi”. Nếu API cần 503 cho dependency outage, hãy thiết kế một handler/lớp exception translation tương ứng, nhưng không dùng một `@ControllerAdvice` tùy tiện để phá đường Bearer validation.

### 13.4. Hạn chế `try/catch Exception` quá rộng

Ví dụ không tốt:

```java
try {
    updateOrder();
} catch (Exception ex) {
    return ResponseEntity.status(401).build();
}
```

Code này đánh đồng:

- Token sai.
- Thiếu scope.
- Order không thuộc owner.
- SQL connection timeout.
- Bug `NullPointerException`.
- Đơn không tồn tại.

Kết quả là response sai nghĩa và sự cố lập trình bị che. Phải phân loại exception theo **boundary và ownership** thay vì biến mọi thất bại thành authentication failure.

---

## 14. Dùng `AuthenticationEntryPoint` trực tiếp trong một custom component: nên hay không?

Một số code định làm:

```java
if (tokenInvalid) {
    response.setStatus(401);
    response.getWriter().write("unauthorized");
    filterChain.doFilter(request, response);
}
```

Điều này có nhiều lỗi:

- Sau khi trả response 401 lại tiếp tục chạy filter chain.
- Không có `WWW-Authenticate: Bearer`.
- Có thể controller vẫn được thực thi và ghi đè/commit response.
- SecurityContext có thể còn authentication cũ nếu custom filter quản lý sai.
- Nội dung response có thể chứa dữ liệu lỗi nội bộ.

Nếu custom filter **thực sự sở hữu việc authentication và không dùng filter chuẩn**, một pattern là:

```java
try {
    Authentication authentication = authenticateToken(request);
    SecurityContextHolder.getContext()
        .setAuthentication(authentication);
    filterChain.doFilter(request, response);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    bearerEntryPoint.commence(request, response, ex);
    return;
}
```

Đây chỉ là **pseudocode** để minh họa các bước quản lý exception; production code còn cần thiết kế SecurityContext repository, authentication result, async dispatch, double filter registration, bearer resolver, token errors và lifecycle đúng phiên bản Spring. **Ưu tiên dùng `BearerTokenAuthenticationFilter` chuẩn** thay vì tự viết xác thực Bearer để hạn chế sai ranh giới.

### 14.1. Không ném AccessDeniedException trước khi có Authentication

Nếu một custom filter trước authentication tự ném `AccessDeniedException` cho token thiếu, kết quả phụ thuộc handler, trust resolver và vị trí filter. Nếu không nằm trong vùng catch của `ExceptionTranslationFilter`, có thể là `500`. Tốt hơn là để Bearer resolver/filter và HTTP authorization xử lý bằng semantics chuẩn.

### 14.2. Clear context khi authentication fail

Spring Security filter/provider chuẩn có trách nhiệm xử lý SecurityContext theo lifecycle của framework. Khi tự tùy biến, không được giữ một authentication cũ trong thread-local rồi xử lý request kế tiếp. Trong servlet applications có thread pool, bug context leakage đặc biệt nguy hiểm.

Không tạo `UsernamePasswordAuthenticationToken.authenticated(...)` hoặc `JwtAuthenticationToken` bằng claims lấy từ payload JWT chưa xác minh. Có `isAuthenticated=true` trong Java object **không chứng minh** JWT signature/issuer/audience đã vượt qua trust policy.

---

## 15. Kiểm thử 401/403 và Bearer challenge

Một bộ test chỉ assert `status().isUnauthorized()` hoặc `status().isForbidden()` vẫn chưa đủ. Nên kiểm tra đồng thời:

1. Spring filter chain thực sự chạy.
2. Trạng thái HTTP phù hợp.
3. Header `WWW-Authenticate` giữ Bearer semantics khi cần.
4. Controller/service **không thực thi** với token không hợp lệ.
5. Token hợp lệ thiếu quyền không bị nhầm thành token sai.
6. Không tiết lộ raw token/claims/secret trong response.
7. Error handler không tự đổi 401/403 thành 200/302/500.

### 15.1. Test không có token

Giả sử có `GET /api/orders/42` và route yêu cầu `SCOPE_orders:read`:

```java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.startsWith;

@Test
void missingBearerTokenGetsChallenge() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "WWW-Authenticate", startsWith("Bearer")));
}
```

Không assert rằng header bắt buộc chứa `invalid_token` khi **không hề có token**, vì RFC 6750 cho phép challenge không có error code trong trường hợp này.

### 15.2. Test token hợp lệ nhưng thiếu scope

Dùng `spring-security-test`:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthenticatedJwtWithoutReadScopeIsForbidden()
        throws Exception {
    mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:write"))))
        .andExpect(status().isForbidden());
}
```

`jwt()` là request post-processor tạo authentication giả phục vụ test **authorization**; nó không chứng minh JWT decoder đã xác minh chữ ký, `exp`, audience hoặc JWKS. Để kiểm tra lỗi token thực sự, cần gửi Bearer JWT ký bằng test keypair qua filter chain và cấu hình decoder tương ứng.

### 15.3. Test `invalid_token` bằng token ký thật

Một integration test có thể tạo keypair RSA thử nghiệm, ký JWT giả định với:

- Issuer `https://auth.example.test/realms/orders`.
- Audience `orders-api`.
- `exp` hợp lệ hoặc hết hạn.
- Scope `orders:read`.
- Signature hợp lệ hoặc bị sửa.

Cấu hình Resource Server chỉ tin public key/JWKS test. Ví dụ kế hoạch test:

```text
given valid signed access token:
    GET /api/orders/42 → qua authentication, tiếp tục authorization

given same JWT with modified payload and old signature:
    GET /api/orders/42 → 401; Bearer invalid_token

given expired but correctly signed JWT:
    GET /api/orders/42 → 401

given signed JWT for payments-api:
    GET /api/orders/42 → 401

given signed JWT for orders-api but without orders:read:
    GET /api/orders/42 → 403

given signed JWT with scope but order belongs to Bob:
    GET /api/orders/order-bob → 403/404 theo policy
```

Không dùng private signing key production trong test. Không đặt `.with(jwt())` vào những test cần thực sự kiểm tra decoder, vì mock sẽ bỏ qua authentication step.

### 15.4. Thử response của custom entry point và denied handler

Nếu triển khai decorator hoặc JSON handler, test phải xác nhận:

- Missing token → 401 và Bearer challenge.
- Invalid token → 401 và `invalid_token` khi framework/exception cung cấp.
- Malformed Bearer request → status theo `invalid_request`, có thể 400.
- Valid token thiếu scope → 403, challenge/error phù hợp.
- Principal OAuth2 không đủ quyền → handler không tiết lộ scope/claims nhạy cảm.
- Handler chỉ viết response **một lần**.
- Response không đổi thành login redirect 302 khi đi qua API chain.
- `GET /api/public/ping` cho phép nếu thực sự public, và không áp Bearer challenge không cần thiết.
- `/api/admin/**` không bị một matcher `authenticated()` tổng quát che rule role/scope.
- Header security khác (nếu có) không bị vô tình xóa khi viết JSON body.

### 15.5. Test boundaries: filter vs MVC

Tạo hai test tách biệt:

**Test A — lỗi ngay tại authentication filter**

```text
Authorization: Bearer <invalid token>
    ↓
JwtDecoder fails
    ↓
BearerTokenAuthenticationFilter invokes entry point
    ↓
Assert: controller không chạy, 401 + challenge
```

**Test B — lỗi access denied phía sau**

```text
Authentication valid, authorities thiếu SCOPE_orders:read
    ↓
AuthorizationFilter denies
    ↓
ExceptionTranslationFilter invokes denied handler
    ↓
Assert: controller không chạy, 403
```

Có thể thêm **Test C — denial ở service**:

```text
JWT valid, scope đúng
    ↓
Controller calls service
    ↓
Service/Method Security denies access to Bob's order
    ↓
Assert: 403/404 theo cách ứng dụng đã thiết kế
        và không trả dữ liệu của Bob
```

Nếu Test C trả 500, hãy kiểm tra controller advice/exception resolver, filter chain, loại exception và việc response đã commit. Đừng sửa bằng cách bỏ object authorization.

### 15.6. Test với opaque token

Nếu API dùng introspection, thêm kịch bản:

| Introspection outcome | Kỳ vọng |
|---|---|
| `{"active":false}` | Không có authentication; không vào controller. |
| `{"active":true,"scope":"orders:read"}` | Đủ scope route đọc nếu contract API khác đều đạt. |
| `{"active":true,"scope":"orders:write"}` | Token active nhưng thiếu read → 403. |
| HTTP 401 từ AS do introspection client credential sai | Không cho qua; cảnh báo lỗi tích hợp. |
| HTTP 503/timeout từ AS | Không cho qua; lỗi dependency được phân loại rõ. |
| Response JSON thiếu `active` hoặc sai kiểu | Không coi token active. |

Spring Security Test `opaqueToken()` cũng có thể mock authentication cho route tests, nhưng nó **không gọi introspection HTTP thực**, nên không thay thế test với mock AS endpoint.

---

## 16. Chẩn đoán những lỗi thường gặp

### 16.1. JWT sai nhưng API trả 500

Các khả năng:

- Custom `JwtDecoder` ném một exception không được provider/filter xử lý như authentication failure.
- Custom filter ném lỗi trước `ExceptionTranslationFilter`.
- `@ControllerAdvice` hoặc ErrorController viết response không phù hợp.
- Response đã commit rồi handler lại cố gọi `sendError`.
- Một lỗi code thật sự xảy ra khi parse/convert claims.

Đừng tự sửa bằng `catch (Exception ex) { return 401; }`. Cần tìm đúng boundary và giữ exception contract của framework.

### 16.2. Thiếu scope nhưng API trả 401

Các khả năng:

- Token thực ra **không được xác thực thành công**: sai issuer/audience, hết hạn, decoder lỗi.
- Principal được custom converter tạo với `isAuthenticated=false` hoặc kiểu không phù hợp.
- `ExceptionTranslationFilter` đánh giá authentication là anonymous/insufficient.
- Handler custom biến mọi `AccessDeniedException` thành 401.
- API chain không phải chain đang được bạn nghĩ là chạy.

Kiểm tra authentication đã được tạo chưa, authorities nào có mặt, route rule nào khớp. Không log raw token, chỉ log reason codes/issuer ID đã chuẩn hóa nếu chính sách cho phép.

### 16.3. Token sai nhưng API trả 403

Có thể custom authentication filter tạo một principal đã authenticated từ dữ liệu chưa xác minh, khiến authorization layer xử lý tiếp rồi từ chối do thiếu scope. Đây là dấu hiệu cần xem lại trust boundary. Một JWT chưa xác minh chữ ký không được biến thành authenticated user.

Một nguyên nhân khác là custom denied handler trả 403 cho mọi lỗi thiếu authentication. Hãy kiểm tra no-token và invalid-token tests với entry point chuẩn.

### 16.4. API trả redirect 302 thay vì Bearer challenge

App có thể đang dùng form login entry point do:

- `formLogin()` được áp dụng trên cùng chain.
- Multiple chains/`securityMatcher` sai.
- `exceptionHandling` được override.
- Request không nằm trong `/api/**` chain.
- Browser Accept headers làm framework chọn entry point khác khi có nhiều cơ chế.

Với API thuần Bearer, xác định một chain rõ ràng cho `/api/**` và test `WWW-Authenticate: Bearer`.

### 16.5. API trả 403 nhưng không có `insufficient_scope`

Đó không luôn là lỗi. `BearerTokenAccessDeniedHandler` có thể chỉ thêm `insufficient_scope` khi nó xác định được caller có OAuth2 authentication phù hợp. Một 403 do CSRF, ACL hoặc custom handler cũng có thể có response khác. Không ép mọi 403 mang error code giống nhau khi nguyên nhân không phải scope.

### 16.6. `@RestControllerAdvice` không chạy với token hết hạn

Điều này là bình thường nếu token bị từ chối trong `BearerTokenAuthenticationFilter`, trước MVC. Hãy kiểm tra `AuthenticationEntryPoint`/`AuthenticationFailureHandler` của Resource Server thay vì cố bắt trong controller advice.

### 16.7. Security exception lọt khỏi chain khi thêm custom filter

Nếu custom filter ở ngoài hoặc trước `ExceptionTranslationFilter` ném `AccessDeniedException`, filter này có thể không bắt. Đừng chỉ thay exception type; phải xem vị trí, filter ownership và cách lập HTTP response. Có thể ủy quyền đúng handler chuẩn ở điểm mà custom filter sở hữu failure, hoặc di chuyển quyết định authorization vào `AuthorizationManager`/method security phù hợp.

### 16.8. Token hợp lệ có scope nhưng API lộ dữ liệu tenant khác

Đây là lỗi **object-level authorization** chứ không chỉ là lỗi 401/403. Scope không tự xác định quyền trên bản ghi. Service/repository phải lọc theo owner, tenant, delegated access hoặc ACL, và test truy cập chéo tenant/user.

---

## 17. Nguyên tắc an toàn khi tạo error response

Một error response hữu ích không cần tiết lộ credential hoặc chi tiết token.

Nên có:

- HTTP status phù hợp.
- `WWW-Authenticate: Bearer` theo RFC 6750 khi cần.
- Error code ổn định, ví dụ `invalid_token` hoặc `insufficient_scope` trong header đúng ngữ cảnh.
- Correlation/request ID để vận hành.
- Message ngắn, không tiết lộ thông tin user khác.
- `Cache-Control: no-store` nếu ứng dụng có response error chứa thông tin nhạy cảm hoặc theo contract phù hợp.
- Log/metric nội bộ phân loại lỗi.

Không nên có:

- Raw `Authorization: Bearer ...` hoặc access token trong body.
- JWT payload đầy đủ, refresh token, introspection client secret.
- Exception stack trace gửi tới client.
- `error_description` từ upstream chứa PII hoặc URL nội bộ không lọc.
- Thông tin “order thuộc Bob ở tenant B” khi Alice không được phép biết.
- Tên scopes admin nội bộ không cần thiết phải công bố.

### 17.1. Có nên dùng RFC 7807 / RFC 9457 Problem Details?

API có thể dùng `application/problem+json` để nhất quán lỗi nghiệp vụ. Ví dụ:

```json
{
  "type": "https://api.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action",
  "instance": "/api/orders/42"
}
```

Đây là **format của response body**, không thay cho `WWW-Authenticate` khi Bearer challenge được yêu cầu. Một JSON body đẹp nhưng status sai hoặc thiếu header chuẩn vẫn có thể làm client OAuth xử lý sai.

Cần cân nhắc không echo raw URL/path chứa thông tin riêng tư trong `instance`. Không tạo nội dung khác nhau làm lộ tồn tại object bị che giấu.

### 17.2. Đừng biến mọi denied thành `insufficient_scope`

Phân loại:

```text
AUTHN_NO_TOKEN
AUTHN_INVALID_TOKEN
AUTHN_MALFORMED_BEARER_REQUEST
AUTHZ_INSUFFICIENT_SCOPE
AUTHZ_OBJECT_NOT_ALLOWED
AUTHZ_TENANT_DENIED
AUTHZ_CSRF_DENIED
DEPENDENCY_JWKS_UNAVAILABLE
DEPENDENCY_INTROSPECTION_UNAVAILABLE
```

Đây là **reason codes cho log/metrics nội bộ**, không cần gửi tất cả cho client. Một số lỗi authn hoặc dependency có thể cùng dẫn đến request bị từ chối nhưng có runbook khác.

---

## 18. Monitoring và audit ranh giới lỗi

Một vấn đề vận hành phổ biến là tỷ lệ 401 tăng đột biến sau JWKS rotation, hoặc 403 tăng sau khi Authorization Server đổi claim scopes. Chỉ xem một biểu đồ “HTTP errors” không đủ tìm nguyên nhân.

Các chỉ số hữu ích:

| Metric | Mục tiêu |
|---|---|
| `http_server_requests_seconds{status=401}` | Tỷ lệ/latency request không được xác thực. |
| `http_server_requests_seconds{status=403}` | Tỷ lệ/latency request bị từ chối quyền. |
| `bearer_authentication_failure_total{reason=...}` | Phân loại no-token, invalid token, malformed bearer, audience, expiry. |
| `bearer_access_denied_total{reason=...}` | Scope/role, object ACL, tenant, CSRF. |
| `jwks_fetch_error_total` | Lỗi phụ thuộc JWKS có thể gây authn failures. |
| `introspection_error_total{class=...}` | Inactive token khác timeout/401 introspection client. |
| `authorization_decision_total{result=...}` | Quan sát quyết định permit/deny trên các policies được phép đo. |

Giữ label cardinality hữu hạn: không gắn nguyên `sub`, token, `jti`, scope value do attacker điều khiển hoặc resource ID của mỗi order vào metric labels. Với audit nhạy cảm, tuân thủ chính sách lưu trữ PII và phân quyền truy cập log.

Một runbook tối thiểu khi `401`/`403` tăng:

1. Xác định API route, region/pod/version và thời điểm tăng.
2. Kiểm tra response status cùng `WWW-Authenticate`.
3. Phân biệt no-token, expired/invalid token, wrong issuer/audience, insufficient authority.
4. Kiểm tra JWKS/introspection endpoint, cache rotation và HTTP timeout nếu 401/5xx liên quan dependency.
5. Kiểm tra mapper `scope`/`scp` và matcher order nếu 403 tăng sau deploy.
6. Kiểm tra owner/tenant business policy nếu chỉ một số object bị denied.
7. Kiểm tra custom entry point, denied handler và ControllerAdvice nếu status/header sai.
8. Tái tạo bằng test mà không xuất raw token production.
9. Khôi phục qua cấu hình/rollout đã kiểm chứng; không tắt authentication/authorization cho nhanh.
10. Bổ sung negative test để tránh tái diễn.

---

## 19. Một ma trận quyết định cho API Bearer

| Điểm xảy ra | Exception / tình huống | Ai thường xử lý? | HTTP kết quả thường thấy |
|---|---|---|---|
| `BearerTokenResolver` | Header Bearer sai cú pháp, phương pháp token không hợp lệ | `BearerTokenAuthenticationFilter` + failure handler/entry point | RFC 6750 `invalid_request`, có thể 400. |
| `JwtAuthenticationProvider` | JWT signature/exp/issuer/audience không hợp lệ | Authentication filter + entry point | 401, `invalid_token`. |
| `OpaqueTokenAuthenticationProvider` | `active=false` | Authentication filter + entry point | 401, `invalid_token` hoặc challenge phù hợp. |
| Không gửi token | Filter không có credential; rule bảo vệ từ chối | `ExceptionTranslationFilter` + entry point | 401, Bearer challenge. |
| `AuthorizationFilter` | Authenticated JWT thiếu `SCOPE_orders:read` | `ExceptionTranslationFilter` + denied handler | 403, có thể `insufficient_scope`. |
| Method security | `@PreAuthorize` từ chối | Nếu exception truyền qua HTTP filter chain: ETF/handler; nếu MVC bắt trước: MVC handler | Thường 403, phụ thuộc boundary. |
| Service owner check | Không được phép đọc order | Domain policy + error mapping đã thiết kế | 403 hoặc 404. |
| CSRF filter | CSRF token không đạt (ứng dụng cookie/session) | Security access denied handling tại điểm tương ứng | Thường 403, không nhất thiết là insufficient_scope. |
| AS/JWKS timeout | Dependency không phản hồi | Decoder/introspector/provider hoặc custom error boundary | Fail closed; status phụ thuộc thiết kế/exception mapping. |
| Controller/service bug | `NullPointerException`, lỗi DB | MVC/Boot error handling phù hợp | Thường 5xx, không tự đổi thành 401/403. |
| Response đã commit | Exception xảy ra sau khi gửi dữ liệu | Handler có thể không thể đổi response | Lỗi vận hành thiết kế; cần kiểm tra quyền trước khi ghi. |

**Lưu ý:** bảng mô tả đường đi thường gặp, không phải hợp đồng bất biến cho mọi phiên bản/cấu hình. Đặc biệt, với custom filters hoặc exception resolvers, phải kiểm tra response thực qua integration tests.

---

## 20. Một ví dụ end-to-end về ba request

### Request A — Không có token

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
```

Chuỗi quyết định:

```text
BearerTokenAuthenticationFilter: không có Bearer token
  → request tiếp tục
AuthorizationFilter: yêu cầu SCOPE_orders:read nhưng chưa authenticated
  → AccessDeniedException
ExceptionTranslationFilter: anonymous/unauthenticated
  → BearerTokenAuthenticationEntryPoint
Response: thường 401 + WWW-Authenticate: Bearer
```

### Request B — Token hợp lệ, thiếu scope

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-jwt-with-orders-write-only>
```

Chuỗi quyết định:

```text
BearerTokenAuthenticationFilter
  → JwtDecoder xác minh token thành công
  → Authentication có SCOPE_orders:write
AuthorizationFilter yêu cầu SCOPE_orders:read
  → AccessDeniedException
ExceptionTranslationFilter thấy caller đã authenticated
  → BearerTokenAccessDeniedHandler
Response: thường 403; có thể error="insufficient_scope"
```

### Request C — Token hợp lệ, đủ scope nhưng sai owner

```http
GET /api/orders/order-bob-200 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-jwt-for-alice-with-orders-read>
```

Chuỗi quyết định:

```text
JwtDecoder: chữ ký, issuer, audience, exp hợp lệ
AuthorizationFilter: SCOPE_orders:read có mặt
Controller/Service: tra order-bob-200
Domain policy: order.owner != alice
  → deny
Response: 403 hoặc 404 theo API policy
Không trả dữ liệu của Bob.
```

Ba request trên minh họa:

```mermaid
flowchart TD
    A["Bearer request"] --> B{"Token đã được xác thực?"}
    B -->|Không| C["AuthenticationEntryPoint → 401"]
    B -->|Có| D{"Đủ scope/authority?"}
    D -->|Không| E["AccessDeniedHandler → 403"]
    D -->|Có| F{"Được phép truy cập đối tượng?"}
    F -->|Không| G["Domain denial → 403/404"]
    F -->|Có| H["Thực thi nghiệp vụ"]
```

Đây là **sơ đồ chính sách logic**; trong filter chain thực tế, no-token denial có thể bắt đầu bằng `AccessDeniedException` rồi được `ExceptionTranslationFilter` chuyển sang entry point, như Request A đã giải thích.

---

## 21. Những sai lầm cần tránh

| Sai lầm | Vì sao sai | Cách tiếp cận đúng |
|---|---|---|
| “`AuthenticationException` luôn do `ExceptionTranslationFilter` bắt.” | Bearer authentication filter có failure handler riêng, nằm ngoài catch downstream của ETF. | Hiểu vị trí phát sinh và owner của từng handler. |
| “`AccessDeniedException` luôn tạo 403.” | Anonymous có thể được gửi tới authentication entry point và nhận 401. | Xem `AuthenticationTrustResolver` và context. |
| “Mọi 401 phải có `invalid_token`.” | Không gửi credential có thể chỉ nhận `WWW-Authenticate: Bearer` không kèm error. | Bám RFC 6750. |
| “Mọi 403 là thiếu scope.” | Có thể là ACL, tenant, object policy hoặc CSRF. | Không gắn `insufficient_scope` cho mọi denied vô điều kiện. |
| “`@ControllerAdvice` là global handler cho mọi Spring Security filter.” | Filter trước DispatcherServlet không được MVC advice tự bắt. | Dùng entry point/denied handler đúng boundary. |
| “Một token hợp lệ là đủ truy cập mọi order.” | Scope không chứng minh ownership. | Kiểm tra object-level authorization. |
| “Token sai chữ ký vẫn tạo principal rồi route sẽ từ chối.” | Có thể tạo context không đáng tin, sai HTTP semantics. | Từ chối token tại authentication. |
| “Có thể viết JSON body sau mọi `sendError`.” | Response có thể đã commit/được container quản lý. | Test handler/commit lifecycle; giữ challenge chuẩn. |
| “Xử lý lỗi bằng 302 login page là tốt cho API.” | Client Bearer muốn status/challenge, không phải HTML login. | Tách API chain khỏi browser form-login chain. |
| “Dùng `try/catch Exception` rồi trả 401 là an toàn.” | Che bug, network, scope và object denial. | Phân loại exception theo trách nhiệm. |
| “Test `jwt()` chứng minh token hết hạn bị từ chối.” | `jwt()` mock authentication, không chạy decoder. | Dùng signed JWT integration test riêng. |
| “Đổi `hasAuthority` thành `authenticated()` sẽ sửa 403.” | Làm route rộng quyền ngoài ý muốn. | Sửa grant/mapping/policy, không hạ bảo mật. |
| “`CsrfException` luôn do Bearer thiếu scope.” | CSRF là nhóm access denied khác ngữ nghĩa. | Đặt CSRF policy phù hợp cookie/token model. |
| “Custom filter ở đâu cũng được ETF bảo vệ.” | ETF chỉ bao quanh đoạn chain downstream của nó. | Sắp xếp filter hoặc xử lý failure đúng chỗ. |

---

## 22. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope` và HTTP status.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authentication/authorization context và OAuth scopes.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): ràng buộc token type, issuer/audience khi dùng JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): inactive token và metadata opaque token.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/access/ExceptionTranslationFilter.html): cơ chế điều phối entry point/denied handler.
- [Spring Security — BearerTokenAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html): authentication filter và failure handling.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): Bearer challenge.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): xử lý access denial cho Bearer.
- [Spring Security — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, exception translation và architecture.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): authorization rules và filter behavior.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, authorities và request authorization.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object-level checks.

**Kết luận:** `AuthenticationException` và `AccessDeniedException` đại diện **hai lớp quyết định khác nhau**, nhưng HTTP response cuối cùng còn phụ thuộc **exception được ném ở đâu, ai bắt nó và caller đã được xác thực hay chưa**. Trong Spring Security Resource Server, hãy để Bearer authentication filter và `ExceptionTranslationFilter` phối hợp với `AuthenticationEntryPoint`/`AccessDeniedHandler` phù hợp, giữ đúng challenge RFC 6750, và tiếp tục kiểm tra scope/ownership ngay cả khi token đã được xác minh thành công.
