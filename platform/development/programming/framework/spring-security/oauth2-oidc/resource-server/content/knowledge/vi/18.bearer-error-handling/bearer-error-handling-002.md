# Phân biệt HTTP 400, 401 và 403 trong luồng Bearer

## 1. Mục tiêu: hiểu đúng lỗi trước khi sửa JWT hay phân quyền

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, client thường gọi API kèm access token:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer ACCESS_TOKEN
~~~

Khi request thất bại, ba mã HTTP dễ nhầm là **400 Bad Request**, **401 Unauthorized** và **403 Forbidden**. Chúng không diễn tả cùng một vấn đề.

- **400**: request dùng cơ chế Bearer không đúng hình thức, hoặc request HTTP có lỗi đầu vào không liên quan authentication. Trong RFC 6750, lỗi Bearer điển hình là **invalid_request**.
- **401**: Resource Server chưa có credential được chấp nhận để xác thực caller. Có thể thiếu token, token đã hết hạn, sai chữ ký, sai issuer/audience hoặc bị thu hồi. Bearer error thường là **invalid_token** khi một token đã trình bày nhưng không hợp lệ.
- **403**: credential đã được chấp nhận, nhưng caller không được phép thực hiện action theo OAuth scope hoặc chính sách nghiệp vụ. Bearer error điển hình khi thiếu scope là **insufficient_scope**.

Tư duy:

~~~text
Request gửi tới Resource Server
           |
           v
Hình thức Bearer credential đúng?
  Không -> 400 invalid_request (trường hợp điển hình)
           |
           v
Credential có được xác thực?
  Không -> 401 (có thể invalid_token)
           |
           v
Token đã xác thực có đủ quyền?
  Không -> 403 (có thể insufficient_scope)
           |
           v
Domain policy có cho phép với object/tenant?
  Không -> 403 hoặc chính sách domain tương ứng
           |
           v
Cho phép request
~~~

Sơ đồ diễn đạt logic, không phải khẳng định mọi servlet filter chạy theo thứ tự đó. CSRF, CORS, gateway, nhiều SecurityFilterChain và custom handlers cũng có thể trả 400/401/403.

**Nguyên tắc:** phân biệt **lỗi cách gửi credential**, **lỗi chấp nhận credential**, và **lỗi cấp phép hành động**. Một status code đơn lẻ chưa cho biết hết nguyên nhân.

## 2. RFC 6750: ba Bearer error codes cần nhớ

RFC 6750 quy định việc trình bày OAuth 2.0 Bearer token và những error codes liên quan.

| Bearer error | Ý nghĩa | HTTP status điển hình |
|---|---|---|
| **invalid_request** | Cách trình bày Bearer credential không hợp lệ, thiếu/sai tham số bắt buộc, dùng nhiều phương thức truyền credential không hợp lệ | **400 Bad Request** |
| **invalid_token** | Token hết hạn, bị thu hồi, malformed hoặc không được Resource Server chấp nhận | **401 Unauthorized** |
| **insufficient_scope** | Access token không có scope cần cho tài nguyên được yêu cầu | **403 Forbidden** |

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

Các cặp này là **mẫu thường phù hợp theo RFC 6750**, không nên biến thành khẳng định tuyệt đối cho mọi implementation. Ví dụ một Bearer header sai cú pháp có thể được **DefaultBearerTokenResolver** của Spring Security mô tả bằng **invalid_token** với status 401 thay vì invalid_request 400. Muốn xác nhận đúng, cần biết resolver tạo **BearerTokenError** nào.

### HTTP status khác Bearer error

**HTTP status** diễn tả kết quả request ở tầng HTTP. **Bearer error code** giải thích lỗi cụ thể theo authentication scheme Bearer. **JSON body** nếu có là hợp đồng bổ sung của API.

Ví dụ 400 do JSON body không hợp lệ không đồng nghĩa có Bearer error invalid_request. Ví dụ 403 do user không có membership tenant cũng không nhất thiết mang insufficient_scope.

## 3. Header WWW-Authenticate nói điều gì?

Một response khi caller chưa cung cấp authentication information có thể chỉ có:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không nhất thiết có trường **error**. RFC 6750 khuyến nghị khi request **không có authentication information**, Resource Server không cần thêm error code và error description, vì chưa có token nào được đưa ra để kết luận không hợp lệ.

Khi token đã được trình bày nhưng không được chấp nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Khi token hợp lệ nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Các tham số cần biết:

| Tham số | Vai trò |
|---|---|
| **Bearer** | HTTP authentication scheme của RFC 6750 |
| **realm** | Tên phạm vi bảo vệ; không phải issuer của token |
| **error** | Mã Bearer như invalid_request, invalid_token, insufficient_scope |
| **error_description** | Mô tả ngắn, an toàn, nếu server cung cấp |
| **error_uri** | URI tới tài liệu mô tả lỗi |
| **scope** | Với insufficient_scope, có thể mô tả phạm vi cần thêm |

**Không log và không trả nguyên access token** trong error_description. Không đưa private signing key, introspection secret, stack trace, issuer key material hoặc thông tin membership của user khác vào response.

WWW-Authenticate đặc biệt hữu ích để client biết có cần **credential mới** hay **quyền mới**. Nếu custom handler trả một JSON body nhưng vô tình bỏ Bearer challenge cần thiết, API có thể gây khó cho client tuân chuẩn.

## 4. HTTP 400: request dùng Bearer sai hình thức

Một trường hợp tiêu biểu của **invalid_request** là caller đưa token theo **nhiều phương thức cùng lúc**.

Ví dụ không nên làm:

~~~http
POST /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer TOKEN_A
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_B&quantity=1
~~~

Nếu Resource Server được cấu hình chấp nhận header và form body, nó phải tránh tình trạng tùy ý chọn token A hay B. Theo RFC 6750, việc dùng nhiều hơn một phương thức truyền token là lỗi **invalid_request**, thường 400.

Một số cách trình bày Bearer không phù hợp:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer
~~~

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer TOKEN_A,TOKEN_B
~~~

~~~http
GET /api/orders?access_token=TOKEN_IN_QUERY HTTP/1.1
Authorization: Bearer TOKEN_IN_HEADER
~~~

**Lưu ý về implementation:** các tình huống trên không mặc nhiên đều được Spring Security trả 400. DefaultBearerTokenResolver mặc định dùng header; query/form parameter không được bật sẵn, và token header malformed có thể được parser biểu diễn bằng **invalid_token**. Cần đối chiếu cấu hình thực tế.

### Query string chứa access token là lựa chọn rủi ro

Bearer token trong URL có thể bị lộ qua history, proxy logs, HTTP referrer, analytics, browser caches hoặc monitoring. Spring Security thường không cho phép URI query token theo mặc định. Client nên dùng:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

Không bật URI query token chỉ để chữa một 401 do frontend chưa thêm Authorization header.

### Không nhầm 400 do JSON validation với invalid_request Bearer

Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer VALID_TOKEN
Content-Type: application/json

{"quantity": -3}
~~~

Nếu API yêu cầu quantity dương, Spring MVC/Bean Validation có thể trả **400**, dù Bearer token hoàn toàn hợp lệ. Đây là **input validation**, không phải Bearer invalid_request.

| Lý do 400 | Lớp xử lý | Có phải Bearer error không? |
|---|---|---|
| Gửi token nhiều phương thức trái policy | BearerTokenResolver | Có thể invalid_request |
| Tham số credential Bearer bị mâu thuẫn | BearerTokenResolver | Có thể invalid_request |
| JSON body sai cú pháp | MVC JSON parser | Không |
| Form domain thiếu field bắt buộc | MVC/application validation | Không |
| Query parameter nghiệp vụ không đúng type | Request binding | Không |
| Gateway từ chối request quá lớn | Proxy/container | Không nhất thiết |

## 5. HTTP 401: thiếu hoặc không chấp nhận credential

HTTP 401 là kết quả thường gặp khi request cần authentication mà **không có authentication hợp lệ**.

Các tình huống:

1. Endpoint được bảo vệ nhưng request không có Bearer credential.
2. JWT hết hạn theo **exp**.
3. JWT chưa đến thời gian hiệu lực theo **nbf**.
4. JWT signature không hợp lệ.
5. JWS algorithm không thuộc allow-list.
6. JWT **iss** khác issuer được API tin.
7. JWT **aud** không dành cho Resource Server.
8. Token là OIDC ID token hoặc JWT assertion sai purpose, không phải access token phù hợp.
9. Token bị thu hồi hoặc bị đánh dấu invalid theo policy.
10. Opaque token introspection trả **active=false**.
11. Credential khác được trình bày nhưng không có authentication mechanism hợp lệ cho route.

### 5.1. Thiếu Bearer token

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
~~~

Nếu route yêu cầu authenticated, response thường:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không nên tự gắn **invalid_token** nếu thực tế chưa có token nào bị kiểm tra.

Một endpoint **permitAll** thì có thể trả 200 cho cùng request thiếu token. **Thiếu token không luôn có nghĩa 401**, vì chính sách route mới quyết định authentication có bắt buộc không.

### 5.2. Có JWT nhưng token invalid

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer EXPIRED_OR_INVALID_JWT
~~~

Nếu JwtDecoder không chấp nhận credential, response điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

JWT có **scope=orders.admin** nhưng signature sai vẫn **không được dùng để cấp quyền**. Token payload có thể decode Base64URL mà chưa được xác minh; những claim chưa tin cậy đó không được đưa vào SecurityContext như authenticated principal.

### 5.3. Chữ ký đúng nhưng sai issuer hoặc audience

Ví dụ:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

Dù chữ ký JWT đúng với khóa của issuer, **orders-api** không được chấp nhận token được phát cho **billing-api**. Nếu audience validator bắt buộc aud chứa orders-api, đây là **token contract failure**, thường **401 invalid_token**.

Nó **không phải** lỗi 403 insufficient_scope chỉ vì scope trong token trông phù hợp.

### 5.4. ID token không phải access token

OIDC ID token dành cho **OIDC Client/Relying Party** để xác nhận kết quả đăng nhập. Resource Server yêu cầu access token dành cho audience của API. Cùng issuer/JWKS không làm ID token thành access token.

Nếu token profile của API yêu cầu **RFC 9068** và giá trị **typ=at+jwt**, hoặc claim phân loại riêng của provider, cần kiểm tra đúng hợp đồng. Sai token type là lỗi **acceptance/authentication**, không phải lỗi thiếu quyền sau authentication.

## 6. HTTP 403: đã xác thực nhưng không đủ quyền

Một token đã được Resource Server chấp nhận:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

Nếu endpoint **POST /api/orders** yêu cầu **orders.write**, caller không đủ scope.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

**insufficient_scope** mô tả tình huống access token thiếu phạm vi quyền mà resource yêu cầu. Tham số scope có thể giúp client biết scope cần được AS cho phép, nhưng không nên tiết lộ quyền/domain policy nhạy cảm một cách không kiểm soát.

### 6.1. Không phải mọi 403 đều là insufficient_scope

Ngay cả khi token có **orders.write**, domain vẫn có thể từ chối:

- Actor không có tenant membership hiện hành.
- Order thuộc user hoặc tổ chức khác.
- Resource đã bị khóa/phê duyệt, không cho cập nhật.
- Hành động vi phạm workflow.
- Service principal không được phép làm thao tác dành cho người dùng.
- Quyền bị thu hồi sau thời điểm access token được phát hành.

Ví dụ:

~~~text
JWT signature/issuer/audience/expiry: hợp lệ
Token scope: orders.write
Tenant membership của user: REVOKED
Requested operation: PUT /api/orders/42

=> Có thể authenticated thành công.
=> Domain authorization từ chối.
=> Thường 403; không nhất thiết insufficient_scope.
~~~

Một API có thể dùng mã lỗi domain riêng trong JSON response nhưng vẫn giữ HTTP semantics phù hợp.

### 6.2. 403 không tự chứng minh caller đã authenticated

Trong Spring Security, **CsrfFilter**, CORS handling, WAF hoặc reverse proxy cũng có thể trả 403 khi caller chưa có Bearer authentication. Vì thế, câu "403 nghĩa là user đã đăng nhập" chỉ là phép nhớ đơn giản cho **authorization path điển hình**, không phải định luật cho mọi HTTP response.

Muốn biết vì sao 403, cần xem **filter/handler nào trả response** và **Authentication đã được tạo hay chưa**.

## 7. Bảng so sánh 400, 401 và 403

| Tình huống | Credential được chấp nhận? | Bước thất bại | HTTP thông thường |
|---|---|---|---|
| Không có Bearer token trên protected endpoint | Không | Authentication required | **401** |
| JWT expired | Không | JwtDecoder/time validation | **401 invalid_token** |
| JWT signature invalid | Không | JWS verification | **401 invalid_token** |
| JWT issuer sai | Không | Issuer validation | **401 invalid_token** |
| JWT audience sai | Không | Audience validation | **401 invalid_token** |
| ID token dùng thay access token, bị profile check chặn | Không | Token purpose | **401 invalid_token** |
| Opaque introspection active=false | Không | Token introspection | **401 invalid_token** |
| Gửi token qua nhiều nguồn bị cấm | Chưa xác định | BearerTokenResolver | **400 invalid_request** khi resolver áp dụng |
| Header Bearer malformed | Chưa xác định | BearerTokenResolver | **400 hoặc 401**, tùy error code của resolver |
| Token active thiếu orders.write | Có | Scope authorization | **403 insufficient_scope** |
| Token active có scope nhưng sai tenant | Có | Domain authorization | **403** hoặc policy khác |
| Token active, body JSON sai | Có thể có | Input validation | **400** (không phải Bearer error) |
| Token active, POST bị CSRF filter từ chối | Không nhất thiết | CSRF | **403**, không nhất thiết thiếu scope |
| CORS preflight bị từ chối | Không nhất thiết | CORS/gateway | Có thể **403** |
| Opaque introspection AS trả 401 do RS secret sai | Chưa biết | Upstream credentials | Dependency failure; không kết luận token invalid |
| Opaque introspection AS timeout | Chưa biết | Network/AS | Dependency failure; fail closed |
| Route permitAll không token | Không cần | Public policy | Có thể **200** |
| URL không tồn tại | Tùy chain | Routing | Có thể **404** |
| HTTP method không hỗ trợ | Tùy chain | Routing | Có thể **405** |

**Status cần được đặt trong ngữ cảnh xử lý thực tế.** Chỉ dựa vào bảng mà không biết SecurityFilterChain và error handler có thể dẫn đến chẩn đoán sai.

## 8. DefaultBearerTokenResolver nhận token từ đâu?

**DefaultBearerTokenResolver** trong Spring Security thường nhận token từ **Authorization header**. Các cơ chế form body và query parameter không được bật mặc định.

Ví dụ cấu hình chỉ dùng header:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

    resolver.setAllowFormEncodedBodyParameter(false);
    resolver.setAllowUriQueryParameter(false);

    return resolver;
}
~~~

Khi cần gắn resolver:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenResolver(bearerTokenResolver())
        .jwt(Customizer.withDefaults()))
~~~

**Không mặc nhiên kết luận** URI có **?access_token=...** sẽ được Spring coi là một credential. Nếu resolver không cho query token, tham số đó có thể không được xem như nguồn Bearer token.

### Malformed header có luôn 400 không?

Không. Với một số cú pháp malformed, Spring Security có thể tạo **BearerTokenError** mang mã **invalid_token** và status **401**. Trường hợp dùng **hai phương thức gửi token** trong cấu hình cho phép nhiều nguồn lại có thể tạo **invalid_request** và status **400**.

Vì vậy:

- RFC 6750 cho biết semantics của các nhóm lỗi.
- Spring Security quyết định **BearerTokenError cụ thể** theo resolver/implementation.
- Test thực tế cần xác minh status và challenge ứng với cấu hình đang dùng.

### Nhiều Authorization headers

Proxy hoặc Servlet container có thể xử lý các duplicate headers khác nhau: giữ nhiều giá trị, lấy giá trị đầu, hoặc gộp. Không tự khẳng định DefaultBearerTokenResolver phát hiện mọi tình huống duplicate. Ở hệ thống nhạy cảm, nên có policy thống nhất tại edge và integration tests cho HTTP header duplication, tránh tình trạng proxy và app chọn credential khác nhau.

## 9. Luồng Servlet Resource Server và các điểm phát sinh lỗi

~~~mermaid
sequenceDiagram
    participant Client
    participant F as BearerTokenAuthenticationFilter
    participant R as BearerTokenResolver
    participant P as AuthenticationProvider
    participant D as JwtDecoder / Introspector
    participant A as AuthorizationFilter
    participant E as EntryPoint / DeniedHandler

    Client->>F: Request với hoặc không có Bearer
    F->>R: resolve(request)
    alt Invalid Bearer request
      R-->>F: BearerTokenError / auth exception
      F->>E: Authentication failure
      E-->>Client: 400/401 tùy BearerTokenError
    else Missing token
      R-->>F: null
      F->>A: Không tạo Bearer authentication
      A->>E: Protected endpoint cần auth
      E-->>Client: 401 challenge
    else Bearer token extracted
      R-->>F: raw token
      F->>P: BearerTokenAuthenticationToken
      P->>D: decode hoặc introspect
      alt Token invalid
        D-->>P: Authentication failure
        P-->>F: AuthenticationException
        F->>E: Failure
        E-->>Client: 401 invalid_token điển hình
      else Token accepted
        D-->>P: Trusted principal
        P-->>F: Authenticated result
        F->>A: SecurityContext được thiết lập
        A->>A: Check authority / scope
        alt Authorization denied
          A->>E: AccessDeniedException
          E-->>Client: 403 thông thường
        else Authorization succeeds
          A-->>Client: Tiếp tục controller
        end
      end
    end
~~~

Đây là **sơ đồ trách nhiệm logic**, không bảo đảm mọi exception đi qua cùng một filter trong mọi Spring Security version.

Một số thành phần:

| Lớp | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Trích Bearer và gửi yêu cầu xác thực |
| **BearerTokenResolver** | Chọn nguồn/cú pháp credential từ request |
| **BearerTokenAuthenticationToken** | Giữ raw credential chưa xác thực |
| **JwtAuthenticationProvider** | Xác thực JWT qua JwtDecoder |
| **OpaqueTokenAuthenticationProvider** | Xác thực opaque token qua OpaqueTokenIntrospector |
| **JwtDecoder** | Verify signature, algorithm, JWT claims validators |
| **OpaqueTokenIntrospector** | Hỏi AS về token active và metadata |
| **JwtAuthenticationConverter** | Ánh xạ JWT đã xác thực thành authorities |
| **SecurityContextHolder** | Giữ Authentication hợp lệ của request |
| **AuthorizationFilter** | Thực thi security policy cho endpoint |
| **ExceptionTranslationFilter** | Dịch một số authentication/access-denied exceptions |
| **BearerTokenAuthenticationEntryPoint** | Tạo Bearer challenge đối với authentication failure |
| **BearerTokenAccessDeniedHandler** | Phản hồi từ chối quyền với Bearer semantics |

**Điểm khác biệt:** Authentication failure có thể được **BearerTokenAuthenticationFilter** xử lý bằng failure handler/entry point trực tiếp. AccessDeniedException ở lớp sau thường được **ExceptionTranslationFilter** đưa đến access-denied handler hoặc authentication entry point. Không được giả định mọi lỗi đều đến từ controller.

## 10. AuthenticationException và AccessDeniedException

Trong Spring Security:

- **AuthenticationException** thể hiện việc chưa được xác thực hoặc credential không được chấp nhận.
- **AccessDeniedException** thể hiện yêu cầu quyền không được đáp ứng.

Tuy nhiên, một AccessDeniedException với request **anonymous/chưa authenticated** có thể được ExceptionTranslationFilter chuyển sang authentication entry point (thường **401**). Nếu có Authentication được xác thực và không đủ quyền, thường đi đến **403**.

~~~text
Not authenticated + protected route
  -> AuthenticationEntryPoint
  -> 401

Authenticated + insufficient authority
  -> AccessDeniedHandler
  -> 403
~~~

Không có nghĩa mọi 403 đến từ AccessDeniedHandler, vì CSRF/CORS/gateway có thể tạo 403 ở bước khác.

### Cẩn thận với SecurityContext

Một filter tự viết decode Base64URL JWT rồi gắn principal vào SecurityContext **trước khi xác minh signature** có thể phá vỡ cả semantics 401/403 và ranh giới bảo mật.

Giữ cơ chế chuẩn:

~~~text
BearerTokenAuthenticationToken (chưa xác thực)
   -> JwtAuthenticationProvider hoặc OpaqueTokenAuthenticationProvider
   -> verified Authentication
   -> SecurityContext
   -> AuthorizationFilter / method security
~~~

Không tạo bộ lọc JWT song song chỉ để tự quyết định 401/403.

## 11. Cấu hình Spring Security JWT Resource Server minh họa

Với Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Với cấu hình và JWT đạt token contract:

| HTTP request | Status thường gặp |
|---|---|
| GET /api/orders không token | **401** |
| GET /api/orders với JWT expired | **401 invalid_token** |
| GET /api/orders với JWT orders.read | Có thể tiếp tục |
| POST /api/orders với JWT chỉ orders.read | **403** |
| POST /api/orders với JWT orders.write | Có thể tiếp tục, còn phụ thuộc domain |
| GET /api/public/help không token | Không cần authentication theo matcher |

**CSRF caveat:** ví dụ tắt CSRF chỉ nhằm minh họa API **thuần Bearer stateless**, không dùng session/cookie authentication cho các request browser. Không sao chép cấu hình disable CSRF cho ứng dụng có cookie-based authentication mà chưa đánh giá mô hình bảo mật.

**Audience caveat:** chỉ khai báo issuer-uri không tự bảo đảm access token có audience dành cho orders-api trong mọi cấu hình. Cần thiết lập token contract/validators phù hợp.

## 12. Kiểm tra issuer/audience trước khi xét scope

Một JWT có:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

không được dùng gọi **orders-api** nếu audience policy yêu cầu **orders-api**. Dù token có scope orders.read, lỗi vẫn thuộc **authentication/token acceptance** khi sai audience, thường **401**, chứ không phải 403.

Ví dụ JwtDecoder kiểm tra issuer và audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com/realms/shop";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                                "Wrong resource audience", null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));

    return decoder;
}
~~~

Đoạn code chỉ minh họa kiểm tra issuer/audience. Framework còn cần verify chữ ký/thuật toán và những ràng buộc **access-token profile** khác theo hợp đồng AS, đặc biệt khi phân biệt ID token và access token.

**setJwtValidator(...) thay các validators đang được gắn với decoder**. Khi thêm điều kiện riêng, phải giữ issuer/time và những profile validators cần thiết. Không dùng một audience validator thay thế chữ ký hoặc thời hạn JWT.

## 13. Scope trong JWT và cách Spring Security tạo authorities

Một JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

thường được Spring Security ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Điều này giải thích:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Nếu JWT chỉ có orders.read, POST cần orders.write thường bị **403**.

### SCOPE_ khác ROLE_

- **hasAuthority("SCOPE_orders.write")** xét authority từ scope.
- **hasRole("ADMIN")** theo convention thường xét authority **ROLE_ADMIN**.
- Claim **roles: ["ADMIN"]** không mặc nhiên thành ROLE_ADMIN trong converter scope mặc định.

Nếu custom JwtGrantedAuthoritiesConverter thay converter mặc định, **SCOPE_...** có thể không được tạo như trước. Đây là lỗi mapping authorization dẫn đến 403 dù token có scope hợp lệ, không phải token invalid.

## 14. BearerTokenAuthenticationEntryPoint và BearerTokenAccessDeniedHandler

Hai extension points của Spring Security:

- **BearerTokenAuthenticationEntryPoint**: trả authentication challenge, thường khi thiếu/invalid credential, có thể sử dụng BearerTokenError để xác định status/error.
- **BearerTokenAccessDeniedHandler**: xử lý access denied trong Bearer Resource Server; có thể trả **insufficient_scope** khi authentication có ngữ nghĩa OAuth2 Bearer phù hợp.

Ví dụ dùng handlers chuẩn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiErrorHandlers(HttpSecurity http)
        throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(
                            new BearerTokenAuthenticationEntryPoint())
                    .accessDeniedHandler(
                            new BearerTokenAccessDeniedHandler())
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

Đây là ví dụ về **handler wiring**, không phải toàn bộ cấu hình production. Trong ứng dụng thực tế cần phối hợp security matchers, CSRF, session, issuer, audience và domain policy.

### Vì sao không tự trả mọi lỗi thành 403?

Một custom handler kiểu:

~~~java
response.setStatus(403);
~~~

cho mọi exception có thể làm request thiếu token, token sai chữ ký hoặc token expired đều bị hiểu là **thiếu quyền**. Tương tự một handler luôn trả 401 sẽ biến domain authorization denial thành **invalid_token**, khiến client refresh liên tục.

Muốn trả body JSON đồng nhất, hãy giữ **HTTP status + WWW-Authenticate** theo ngữ nghĩa lỗi; body chỉ bổ sung thông tin không nhạy cảm.

## 15. Opaque token: phân biệt lỗi access token với lỗi introspection

Opaque Resource Server dùng introspection theo RFC 7662:

~~~text
Hop A: Client -> orders-api
  Authorization: Bearer OPAQUE_TOKEN

Hop B: orders-api -> Authorization Server
  POST introspection
  Authorization: Basic RS_CLIENT_CREDENTIALS
  token=OPAQUE_TOKEN
~~~

Các kết quả khác nhau:

| Kết quả ở hop B | Ý nghĩa | Có kết luận token invalid? |
|---|---|---|
| 200 + active=true | AS xác nhận token active | Không; token có thể còn thiếu audience/scope |
| 200 + active=false | AS không chấp nhận token | **Có**, theo introspection semantics |
| 401 invalid_client | RS credentials sai/không được AS chấp nhận | **Chưa** |
| 403 từ AS | RS thiếu quyền introspect | Chưa |
| 429/5xx | AS bị throttled hoặc unavailable | Chưa |
| DNS/TLS/timeout | Lỗi mạng/tin cậy kênh | Chưa |
| 200 nhưng malformed JSON | Protocol/response failure | Chưa |

**Không chuyển nguyên HTTP 401 ở hop B thành lỗi invalid_token ở hop A.** Nếu introspection client secret hết hạn, token của người dùng có thể vẫn active. Đây là lỗi RS-to-AS cần fail closed và error mapping phù hợp, ví dụ **503 Service Unavailable** theo hợp đồng ứng dụng.

Không khẳng định Spring Security mặc định luôn trả 503 cho lỗi AS; hành vi phụ thuộc implementation, exception mapping, entry point và security chain.

### Vì sao không được fail open?

Nếu AS timeout mà API chấp nhận opaque token chưa được xác minh:

~~~text
AS unavailable
    -> API bỏ qua introspection
    -> Attacker dùng token giả
    -> API cấp quyền trái chính sách
~~~

Vì vậy phải **không cho protected operation đi tiếp** nếu không có bằng chứng token hợp lệ. Fail closed không bắt buộc đồng nghĩa trả 401 invalid_token; có thể giữ lỗi dependency để vận hành biết nguyên nhân thật.

## 16. CSRF và CORS: các 403 không xuất phát từ thiếu scope

Một POST có Bearer token hợp lệ vẫn có thể nhận 403:

~~~text
CsrfFilter đang yêu cầu CSRF token cho POST
Request không có CSRF token
    -> 403
~~~

Trường hợp này không nên sửa bằng cách cấp thêm OAuth scope. Trong ứng dụng dùng cookie/session authentication, CSRF protection có mục đích quan trọng. Với API thuần Bearer header và không có ambient browser credentials, CSRF policy có thể được thiết kế khác, nhưng phải xem mô hình bảo mật thực tế.

Tương tự, CORS preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không mang Bearer token**. Nếu CORS chưa được xử lý đúng và security yêu cầu authentication trên OPTIONS, preflight có thể bị 401/403. Cần xem CORS filter/matcher và gateway, không thay JwtDecoder hoặc scope converter.

### Vì sao POST 403 nhưng GET 200?

Các khả năng:

1. POST yêu cầu **orders.write**, GET chỉ cần **orders.read**.
2. CSRF protection chặn unsafe HTTP method.
3. Domain policy không cho thay đổi trạng thái resource.
4. Gateway/WAF có rule riêng cho POST.
5. POST được SecurityFilterChain khác xử lý.

Cùng JWT không bảo đảm mọi HTTP method được cho phép.

## 17. Khi nào domain trả 404 thay vì 403?

Một số API cố ý trả **404 Not Found** khi caller không có quyền biết một resource tồn tại, ví dụ đơn hàng thuộc tenant khác.

~~~text
GET /api/orders/42
Order 42 thuộc tenant khác.
Policy không cho tiết lộ sự tồn tại.

Response có thể là 404 theo API contract.
~~~

Đây là quyết định **domain authorization/information hiding**, không thay thế Bearer token acceptance. Một JWT hết hạn vẫn cần bị từ chối theo authentication; một introspection outage không được che thành 404.

Điều này minh họa rằng **403 là mã điển hình của authorization denial**, nhưng không phải mọi domain denial đều nhất thiết phải dùng 403.

## 18. Frontend nên phản ứng ra sao?

| Kết quả | Client nên làm | Không nên làm |
|---|---|---|
| 400 invalid_request | Sửa header/cách truyền token, bỏ duplicate credential | Refresh token liên tục khi request format vẫn sai |
| 401 khi không cung cấp token | Lấy access token qua flow phù hợp rồi thử lại | Coi chưa có token là đã bị revoke |
| 401 invalid_token | Kiểm tra expiry/issuer/audience, lấy token hợp lệ qua flow được phép | Tự sửa JWT payload hoặc retry vô hạn cùng token |
| 403 insufficient_scope | Xin consent/scope/role nếu AS và product cho phép; hoặc hiển thị thiếu quyền | Refresh vô hạn với cùng grant |
| 403 domain policy | Hiển thị hành động không được phép | Tìm token của API khác để bypass |
| 400 input validation | Sửa JSON/body/query nghiệp vụ | Sửa OAuth token không liên quan |
| 503 do introspection outage | Backoff/retry có giới hạn theo contract, thông báo phụ thuộc unavailable | Logout tất cả người dùng vì tưởng token sai |

**401 không mặc nhiên nghĩa phải refresh token ngay lập tức.** Nếu JWT có audience/issuer sai, refresh từ cùng nguồn có thể tiếp tục sai. Nếu backend introspection credentials sai, client refresh không giúp gì.

**403 không mặc nhiên nghĩa refresh token sẽ có quyền.** Nếu AS chưa cấp scope hoặc user không được cho phép, client phải thực hiện quy trình xin quyền hợp lệ hoặc dừng hành động.

## 19. Custom JSON errors: giữ đúng status và challenge

Một hợp đồng API có thể bổ sung JSON body:

~~~json
{
  "code": "ACCESS_TOKEN_INVALID",
  "message": "The access token cannot be accepted",
  "requestId": "req-1042"
}
~~~

Các mã như **ACCESS_TOKEN_INVALID** chỉ là ví dụ do ứng dụng định nghĩa, **không phải RFC Bearer error code**.

Một mapping minh họa:

| Nguồn lỗi | HTTP | WWW-Authenticate | Body code nội bộ |
|---|---|---|---|
| Bearer transport invalid | 400 theo resolver | Bearer invalid_request khi phù hợp | BEARER_REQUEST_INVALID |
| Route yêu cầu auth nhưng không token | 401 | Bearer, không nhất thiết error | AUTHENTICATION_REQUIRED |
| JWT/opaque token bị từ chối | 401 | Bearer invalid_token | ACCESS_TOKEN_INVALID |
| Token active thiếu scope | 403 | Bearer insufficient_scope | INSUFFICIENT_SCOPE |
| Token active nhưng vi phạm domain policy | 403 | Không nhất thiết insufficient_scope | ACCESS_DENIED |
| AS introspection unavailable | 503 theo contract | Không cáo buộc token invalid | AUTH_DEPENDENCY_UNAVAILABLE |
| HTTP input body invalid | 400 | Không phải Bearer challenge | INPUT_VALIDATION_FAILED |

**Không nhất thiết mọi 400 đều có WWW-Authenticate**, đặc biệt khi lỗi nằm ở MVC input validation.

### Vì sao @ControllerAdvice chưa đủ?

BearerTokenAuthenticationFilter và nhiều Spring Security filters chạy trước Spring MVC controller. Exception từ đó có thể được xử lý bởi failure handler hoặc AuthenticationEntryPoint chứ không đi qua **@ControllerAdvice**.

Muốn tùy biến đúng:

- Tách lỗi Bearer transport, authentication và authorization.
- Dùng handlers/entry point ở Security filter boundary khi thích hợp.
- Giữ HTTP status và Bearer challenge.
- Không ghi raw token/secret vào body.
- Test end-to-end đi qua SecurityFilterChain.

## 20. State machine để phân loại lỗi

~~~mermaid
flowchart TD
    A["HTTP request đến API"] --> B{"Bearer transport hợp lệ?"}
    B -- "Không" --> BAD["invalid_request / resolver-specific error"]
    B -- "Có" --> C{"Có credential cần thiết?"}
    C -- "Không" --> NO["401 Bearer challenge khi route protected"]
    C -- "Có" --> D{"Token accepted?"}
    D -- "Không" --> INVALID["401 invalid_token thông thường"]
    D -- "Có" --> E["Authenticated principal"]
    E --> F{"Đủ scope/authority?"}
    F -- "Không" --> SCOPE["403 insufficient_scope khi phù hợp"]
    F -- "Có" --> G{"Domain policy cho phép?"}
    G -- "Không" --> DENY["403 hoặc policy-specific denial"]
    G -- "Có" --> OK["Tiếp tục"]
~~~

Sơ đồ chưa biểu diễn **CSRF/CORS/AS dependency error/gateway**; chúng có thể tạo lỗi ở các tầng khác và cần được chẩn đoán độc lập.

## 21. Bộ kịch bản kiểm thử 400/401/403

Các test cases dưới đây là **kỳ vọng thiết kế**, không phải kết quả test đã thực thi.

| Test case | Kỳ vọng |
|---|---|
| GET protected không có Authorization header | 401 Bearer challenge |
| JWT expired | 401 invalid_token |
| JWT signature invalid | 401 invalid_token |
| JWT issuer sai | 401 invalid_token |
| JWT audience sai | 401 invalid_token |
| ID token dùng làm access token, profile validator từ chối | 401 |
| Opaque introspection active=false | 401 |
| Bearer transport duplicated bị resolver chặn | invalid_request/status theo contract |
| Bearer header malformed | Kiểm tra actual BearerTokenError của resolver |
| Valid token chỉ orders.read gọi POST cần orders.write | 403 insufficient_scope khi phù hợp |
| Valid token có write nhưng tenant membership bị thu hồi | Domain denial, thường 403 |
| Valid token nhưng JSON body sai | 400 input validation |
| POST bị CSRF filter chặn | 403 từ CSRF, không phải scope |
| OPTIONS preflight CORS chưa cấu hình đúng | Có thể 401/403 từ CORS/security |
| Opaque introspection 401 invalid_client | Không coi token caller invalid |
| AS introspection timeout | Fail closed, dependency failure |
| Route permitAll không token | Không buộc trả 401 |
| Token valid, đủ quyền, domain object cho phép | Không bị chặn bởi auth/authz |

### Test phải đúng tầng

**BearerTokenResolver unit tests**: cú pháp header, duplicate credential, query/form policy và exception.

**JwtDecoder/opaque introspector tests**: signature, issuer, audience, expiration, token purpose, active=false, upstream errors.

**SecurityFilterChain integration tests**: thật sự đi qua BearerTokenAuthenticationFilter/entry point/denied handler để xác nhận HTTP status, header và absence of authentication khi token invalid.

**Domain authorization tests**: thiếu ownership/membership, status resource và quyền theo tenant.

Spring Security Test **jwt()** request post-processor có thể tạo authentication giả để test authorization; nó có thể **bỏ qua JwtDecoder thực**. Vì thế một test dùng jwt() không đủ chứng minh signature/issuer/audience verification production hoạt động.

### Không chỉ kiểm tra status code

Khi test error contract, cần khẳng định:

- HTTP status.
- WWW-Authenticate scheme và Bearer error (khi contract yêu cầu).
- Không có access token hoặc secret trong response.
- Không tạo Authentication thành công khi token invalid.
- Không gọi domain service khi authentication chưa đạt.
- Không gán insufficient_scope cho token sai issuer/audience.
- Không nhầm lỗi AS introspection với invalid token.
- Không để custom handlers làm mất challenge hoặc thay status sai.

## 22. Troubleshooting khi status khác kỳ vọng

### 22.1. Không token nhưng API trả 403

Có thể do:

- CsrfFilter từ chối trước authentication.
- CORS/gateway chặn request.
- Custom handler luôn trả 403.
- SecurityFilterChain matcher sai.
- Anonymous request bị translate theo cấu hình không mong đợi.
- Custom filter ghi sai SecurityContext.

**Cách xử lý:** kiểm tra filter chain, matcher, CSRF/CORS, entry point và authentication state. Không vội thay JWT scopes.

### 22.2. JWT đúng scope nhưng API trả 401

Có thể:

- JWT hết hạn hoặc chưa có hiệu lực.
- Chữ ký sai, JWKS rotation/cache chưa đồng bộ.
- Issuer URI sai, kể cả path/realm/trailing slash.
- Audience sai.
- Token là ID token hoặc token loại khác.
- Bearer header malformed.
- Opaque introspection active=false.
- AS introspection lỗi cấu hình và bị mapping nhầm thành invalid_token.

**Scope không thay thế token acceptance.** Chỉ sau khi Resource Server đã xác thực token, scope mới là authority đáng tin để xét authorization.

### 22.3. JWT hợp lệ nhưng API trả 403

Có thể:

- Thiếu scope/authority cần cho endpoint.
- **SCOPE_** vs **ROLE_** mapping khác kỳ vọng.
- JwtGrantedAuthoritiesConverter tùy biến đã bỏ scope.
- Domain policy từ chối tenant/owner/order status.
- CSRF hoặc CORS chặn.
- Gateway hoặc WAF trả 403.

Đọc nguyên nhân từ handler hoặc policy, không kết luận chỉ bằng status.

### 22.4. Mọi request đồng loạt trả 401 sau deploy

Nếu dùng opaque token, hãy xem HTTP status **RS → AS introspection**. Upstream 401 **invalid_client** gợi ý client ID/secret/mTLS credentials sai. Với JWT, xem issuer URI, JWKS, algorithm và validators.

Không buộc mọi user đăng xuất đăng nhập lại khi chính API đang dùng introspection secret sai.

### 22.5. GET hoạt động nhưng POST 403

Kiểm tra:

- GET cần orders.read; POST cần orders.write?
- CSRF có bật cho POST?
- POST có bị domain policy cấm?
- Có nhiều SecurityFilterChain không?
- Có proxy/WAF rule theo method không?

Không phải mọi khác biệt GET/POST đều liên quan scope.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Vấn đề | Hướng sửa |
|---|---|---|
| Mọi lỗi đều trả 401 | Che lỗi request/authorization | Phân tầng 400/401/403 |
| Mọi lỗi đều trả 403 | Client không biết cần token | Trả 401 khi authentication required/failed |
| Malformed header luôn bị ép 400 | Không khớp resolver implementation | Dùng BearerTokenError và test thực tế |
| Token thiếu scope → invalid_token | Nhầm authorization với authentication | 403 insufficient_scope khi thích hợp |
| Token sai audience → insufficient_scope | Nhận nhầm token của API khác | Từ chối ở token acceptance |
| Không token → invalid_token | Chưa có token để đánh giá | 401 challenge không error nếu phù hợp |
| AS introspection 401 → token caller sai | Nhầm hai HTTP hops | Phân biệt RS-to-AS credentials |
| AS timeout → cho phép opaque token | Bypass authentication | Fail closed |
| 403 domain denial luôn gắn insufficient_scope | Sai semantics và có thể lộ policy | Domain error/403 phù hợp |
| Ghi raw Bearer token vào logs | Lộ credential | Sanitized logs và request ID |
| Bật query access_token để chữa 401 | Token có thể lộ qua URL | Dùng Authorization header |
| Tắt CSRF bừa để chữa 403 | Tạo rủi ro cho cookie endpoints | Chọn CSRF policy theo trust model |
| Custom JWT filter tự tạo Authentication | Bypass JwtDecoder hoặc ghi đè SecurityContext | Giữ Resource Server chuẩn |
| Chỉ xử lý lỗi trong @ControllerAdvice | Không bắt lỗi từ security filters | Security entry point/denied handler |
| 403 → frontend refresh token vô hạn | Có thể không có grant được phép | Tôn trọng authorization contract |
| JSON error body thay thế mọi WWW-Authenticate | Client mất challenge semantics | Giữ status/header đúng |

## 24. Quy tắc quyết định trước khi trả lỗi

Khi thấy một lỗi Bearer, trả lời các câu hỏi:

1. Request có vào đúng SecurityFilterChain không?
2. Có Bearer credential từ một nguồn được chấp nhận không?
3. BearerTokenResolver có báo error về format/duplicated credentials không?
4. Token có được JwtDecoder hoặc introspector xác thực không?
5. JWT signature, issuer, audience, lifetime và token purpose có hợp lệ không?
6. Nếu opaque token, AS trả **active=false** hay upstream AS/credentials lỗi?
7. Authentication đã được tạo trong SecurityContext chưa?
8. Endpoint cần scope/authority nào?
9. Domain policy có chấp nhận actor với tenant/resource không?
10. Status do Spring Security, MVC, CSRF, CORS hay gateway tạo?
11. WWW-Authenticate có còn phản ánh đúng Bearer error không?
12. Response/log có lộ Bearer token, secret hoặc dữ liệu authorization nội bộ không?

Những câu hỏi trên giúp phân biệt lỗi thực tế thay vì sửa mã trạng thái hoặc JWT theo trực giác.

## 25. Tổng kết

~~~text
400 BAD REQUEST
  Request trình bày Bearer credential không hợp lệ về phương thức/cấu trúc
  -> invalid_request trong các trường hợp RFC 6750 phù hợp
  Hoặc request input nghiệp vụ lỗi ở MVC, không phải Bearer error.

401 UNAUTHORIZED
  Caller chưa có credential được Resource Server chấp nhận.
  -> Không có token: Bearer challenge.
  -> Có token không hợp lệ: invalid_token thường gặp.

403 FORBIDDEN
  Caller đã được xác thực nhưng action không được phép.
  -> Thiếu OAuth scope: insufficient_scope khi đúng ngữ nghĩa.
  -> Domain policy từ chối: 403 hoặc domain-specific response.
~~~

**Nhớ ba nguyên tắc quan trọng:**

1. **Phân loại theo tầng lỗi, không chỉ status.** BearerTokenResolver, JwtDecoder, introspector, AuthorizationFilter, domain service, CSRF/CORS và gateway có thể tạo các response khác nhau.
2. **Giữ đúng ranh giới authentication và authorization.** Token sai issuer/audience/signature không được coi là authenticated rồi xử lý như thiếu scope.
3. **Giữ Bearer challenge an toàn.** HTTP status, WWW-Authenticate và error description cần đúng semantics, không tiết lộ token hoặc secret.

Một Resource Server được thiết kế tốt không chỉ trả đúng **400/401/403**, mà còn giúp client xử lý đúng lỗi, giúp vận hành xác định nguyên nhân và không đánh đổi bảo mật để có mã phản hồi “dễ nhìn”.

## 26. Tài liệu tham khảo

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi token, WWW-Authenticate, invalid_request, invalid_token và insufficient_scope. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics:** ý nghĩa HTTP 400, 401, 403 và authentication challenges. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 6749 — OAuth 2.0 Authorization Framework:** access token và scope. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7519 — JSON Web Token:** iss, sub, aud, exp và các registered claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** issuer/audience, algorithm validation và token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token purpose và profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token active/inactive và response semantics. https://www.rfc-editor.org/rfc/rfc7662
- **Spring Security — OAuth 2.0 Resource Server (Servlet):** Bearer authentication architecture. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security — JWT Resource Server:** decoder, validators và authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Opaque Token Resource Server:** token introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security API — DefaultBearerTokenResolver:** cấu hình nguồn Bearer credentials. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html
- **Spring Security API — BearerTokenAuthenticationEntryPoint:** Bearer challenge. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html
- **Spring Security API — BearerTokenAccessDeniedHandler:** xử lý access denied trong Bearer context. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html
