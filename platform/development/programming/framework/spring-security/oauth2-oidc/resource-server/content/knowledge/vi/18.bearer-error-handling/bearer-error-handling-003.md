# WWW-Authenticate và challenge theo RFC 6750

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một API thường nhận access token qua request header **Authorization: Bearer ...**. Khi request không có token, token không hợp lệ hoặc token đã xác thực nhưng thiếu quyền, server không chỉ trả HTTP 401/403 một cách tùy ý: **RFC 6750 — OAuth 2.0 Bearer Token Usage** định nghĩa cách Resource Server gửi **Bearer challenge** qua response header **WWW-Authenticate**.

Ba tình huống cần phân biệt:

- **Không có thông tin xác thực**: endpoint được bảo vệ trả **401 Unauthorized** kèm Bearer challenge; theo RFC 6750, server **SHOULD NOT** tự thêm mã lỗi cụ thể khi client chưa đưa thông tin xác thực.
- **Có Bearer token nhưng không hợp lệ**: thông thường trả **401 Unauthorized**, challenge có **error="invalid_token"**.
- **Token đã được xác thực nhưng không đủ scope**: thông thường trả **403 Forbidden**, challenge có **error="insufficient_scope"**, có thể chỉ ra scope cần thiết.

Ngoài ra, request Bearer bị malformed hoặc sử dụng nhiều cách truyền token cùng lúc thuộc nhóm **invalid_request**, mà RFC 6750 khuyến nghị **400 Bad Request**.

Spring Security cung cấp các thành phần như **BearerTokenAuthenticationEntryPoint**, **BearerTokenAccessDeniedHandler**, **BearerTokenError** và **BearerTokenErrors** để biểu diễn những kết quả này. Bài học đi từ chuẩn HTTP, thông số của challenge, ví dụ request/response, cách thiết lập trong Servlet Resource Server và kiểm thử thực tế.

## 1. WWW-Authenticate là gì?

HTTP authentication phân biệt hai phía:

| Header | Bên gửi | Vai trò |
|---|---|---|
| **Authorization** | **Client → Resource Server** | Client trình thông tin xác thực, ví dụ Bearer access token |
| **WWW-Authenticate** | **Resource Server → Client** | Server đưa ra **authentication challenge**, thông báo phương thức xác thực được hỗ trợ và có thể kèm thông tin lỗi |

Ví dụ client gọi Orders API mà không gửi token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Accept: application/json
~~~

Một phản hồi chuẩn theo RFC 6750 có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
~~~

Client hiểu rằng tài nguyên được bảo vệ bằng **Bearer authentication scheme**. Nếu client đã được cấp access token phù hợp, request kế tiếp có thể dùng:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <access-token>
~~~

Các giá trị trong dấu ngoặc nhọn chỉ là placeholder, không phải token thật.

**WWW-Authenticate không phải địa chỉ nhận access token** và không phải response của token endpoint. Nó là **challenge từ Resource Server** khi truy cập protected resource. Client cần lấy token bằng một OAuth2 flow phù hợp với Authorization Server và sau đó trình token cho API.

### 1.1. Challenge không nhất thiết là lỗi trong JSON body

Một API có thể có body:

~~~json
{
  "code": "UNAUTHORIZED",
  "message": "Authentication required"
}
~~~

Nhưng body JSON như vậy **không thay thế** HTTP header WWW-Authenticate khi giao thức yêu cầu Bearer challenge. Các OAuth clients, HTTP libraries và automated tests có thể dựa vào status/header, không dựa vào một schema body tùy biến.

Ngược lại, response có WWW-Authenticate **không bắt buộc phải có JSON body**. Resource Server có thể gửi status, header và body trống theo hợp đồng API.

### 1.2. Không nhầm với HTTP Basic

HTTP hỗ trợ nhiều authentication schemes, ví dụ:

~~~http
WWW-Authenticate: Basic realm="legacy-app"
~~~

hoặc:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

**Basic** thường gắn với username/password hoặc client credentials theo cơ chế tương ứng. **Bearer** gắn với possession of access token. Không được đổi **Bearer** thành **Basic** trong challenge của Resource Server chỉ vì introspection endpoint dùng client authentication bằng HTTP Basic.

Một server có thể quảng bá nhiều challenge theo luật HTTP nếu thật sự hỗ trợ nhiều schemes; việc ghép/chia nhiều header fields phải tuân thủ HTTP syntax. Bài học này tập trung vào **Bearer challenge** của RFC 6750.

## 2. Cấu trúc Bearer challenge

Theo **RFC 6750 §3**, một Bearer challenge sử dụng authentication scheme **Bearer** kèm các **auth-params** phù hợp.

Ví dụ đầy đủ để giải thích cú pháp:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", error_description="Insufficient scope", scope="orders.write"
~~~

Các trường:

| Auth-param | Ý nghĩa | Ghi chú |
|---|---|---|
| **realm** | Xác định phạm vi bảo vệ theo HTTP authentication | Tùy chọn; không thay cho issuer/tenant policy |
| **error** | Mã lỗi OAuth Bearer | RFC 6750 định nghĩa **invalid_request**, **invalid_token**, **insufficient_scope** |
| **error_description** | Diễn giải ngắn, dành cho lập trình viên/client | Không chứa bí mật, token hoặc stack trace |
| **error_uri** | URI tài liệu giải thích lỗi | Không phải token endpoint hay jwks_uri |
| **scope** | Các scope cần có để truy cập resource | Tùy chọn; danh sách scope phân cách bằng khoảng trắng |

Về mặt cấu trúc, response có thể có nhiều tham số phân cách bằng dấu phẩy. Chẳng hạn:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token expired"
~~~

Không nhầm dấu **phẩy** ngăn cách các auth-param với dấu **khoảng trắng** giữa nhiều giá trị scope:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read orders.write"
~~~

Tùy chính sách, tham số **scope** có thể liệt kê nhiều scope cần thiết. Việc dùng chuỗi scope phải tuân theo quy tắc của OAuth2, trong đó tên scope **phân biệt chữ hoa/chữ thường**.

### 2.1. Các auth-param có bắt buộc xuất hiện không?

Không phải response nào cũng cần có đủ **realm**, **error**, **error_description**, **error_uri**, **scope**. Trong một hệ thống cụ thể:

- **realm** có thể được cấu hình hoặc không.
- **error** thường không có khi request chưa gửi thông tin xác thực, theo khuyến nghị RFC.
- **error_description** và **error_uri** là thông tin bổ sung, không nhất thiết luôn được trả.
- **scope** thường có ý nghĩa khi server thông báo **insufficient_scope**; nó không bắt buộc phải được tiết lộ.

Một số phiên bản Spring Security có thể trả **WWW-Authenticate: Bearer** mà không có realm, hoặc thêm tham số mở rộng theo release line. Vì thế **không nên viết test yêu cầu header bằng đúng một chuỗi literal cố định của mọi phiên bản** khi ứng dụng không khóa chính xác cấu hình.

### 2.2. Quy tắc không lặp tham số

RFC 6750 quy định các tham số thuộc nhóm **realm**, **scope**, **error**, **error_description** và **error_uri** không được xuất hiện lặp lại theo quy tắc tương ứng.

Ví dụ nên tránh:

~~~http
WWW-Authenticate: Bearer realm="orders-api", realm="admin-api", error="invalid_token"
~~~

Lặp tham số khiến client khó diễn giải challenge và có thể gây khác biệt giữa các parser. Khi tự tạo header, dùng một builder/handler phù hợp thay vì nối chuỗi không kiểm soát.

### 2.3. Các giá trị không phải văn bản tùy ý

**error** và **error_description** phải đáp ứng ràng buộc ký tự của RFC 6750/RFC 6749; **error_uri** phải theo URI-reference syntax và giới hạn ký tự tương ứng. Không đặt **raw newline**, ký tự điều khiển, dấu quote chưa escape hoặc giá trị không hợp lệ vào auth-param.

Ví dụ mô tả lỗi mang dữ liệu không đáng tin là nguy hiểm:

~~~text
error_description = exception.getMessage()
~~~

nếu exception chứa raw token, nội dung từ HTTP request, chuỗi xuống dòng hoặc thông tin nội bộ. Với thông điệp công khai, nên dùng **chuỗi cố định ngắn, an toàn**, tránh header injection và rò rỉ hệ thống.

## 3. Ba mã lỗi của RFC 6750 §3.1

RFC 6750 định nghĩa ba mã lỗi chính cho Bearer authentication trên protected resource.

| Error code | Ý nghĩa | HTTP status khuyến nghị |
|---|---|---|
| **invalid_request** | Request mang Bearer token không đúng cấu trúc/quy tắc truyền token | **400 Bad Request** |
| **invalid_token** | Token đã gửi không hợp lệ, hết hạn, bị thu hồi hoặc sai điều kiện xác thực | **401 Unauthorized** |
| **insufficient_scope** | Token được xác thực nhưng không có đủ scope cho resource | **403 Forbidden** |

Trong RFC, các status trên được diễn đạt bằng **SHOULD**, không phải quy tắc duy nhất cho mọi loại lỗi HTTP. Ngoài ra, Spring Security có thể mapping một số tình huống cụ thể qua **BearerTokenError**/exception handling khác nhau.

### 3.1. invalid_request — request không đúng

Một số tình huống:

- Request dùng **hơn một cách** gửi access token cùng lúc.
- Tham số token bị lặp.
- Bearer authentication request thiếu hoặc có tham số bắt buộc không hợp lệ.
- Một kiểu trình token không được endpoint hỗ trợ.
- Request bị malformed theo quy tắc Bearer.

Một response minh họa:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request", error_description="Multiple bearer tokens"
Content-Length: 0
~~~

RFC khuyến nghị 400 cho invalid_request. **Tuy nhiên không được suy ra mọi chuỗi Authorization malformed đều chắc chắn trở thành invalid_request/400 trong mọi bản Spring Security.** Ví dụ một số đường code của **DefaultBearerTokenResolver** có thể biểu diễn Bearer header malformed thành **invalid_token**; phải kiểm chính xác exception và status mà bản framework đang dùng tạo ra.

### 3.2. invalid_token — token không được chấp nhận

Ví dụ:

- Access token JWT sai chữ ký hoặc thuật toán không được phép.
- JWT sai **iss** hoặc **aud**.
- Token hết hạn (**exp**) hoặc chưa đến hạn (**nbf**) theo policy.
- Opaque token bị introspection đánh dấu **active=false**.
- Token đã bị thu hồi.
- Token giả, không tồn tại hoặc không được nguồn issuer tin cậy xác nhận.

Response điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="Invalid access token"
Content-Length: 0
~~~

RFC cũng minh họa lỗi access token hết hạn bằng mô tả **The access token expired**. Với production, không nhất thiết tiết lộ phân loại chính xác của mọi lỗi signature/claim; điều quan trọng là client hiểu token bị từ chối.

**invalid_token không có nghĩa client chỉ cần thêm scope.** Client thường phải kiểm token đang dùng, lấy token mới hợp lệ theo OAuth flow phù hợp hoặc yêu cầu người dùng xác thực lại khi thật sự cần.

### 3.3. insufficient_scope — token hợp lệ nhưng quyền chưa đủ

Giả sử endpoint:

~~~text
POST /api/orders/42/approve
Required authority: SCOPE_orders.approve
~~~

Client có access token được xác thực nhưng chỉ có:

~~~text
SCOPE_orders.read
~~~

Resource Server có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.approve"
Content-Length: 0
~~~

**scope="orders.approve"** là một lời gợi ý về phạm vi quyền cần thiết; RFC cho phép nhưng **không bắt buộc** server cung cấp tham số này.

Client không thể tự thêm **orders.approve** vào chuỗi JWT rồi gửi lại. Việc được cấp scope thuộc quyết định của **Authorization Server và chính sách cấp quyền**, không phải quyền chỉnh JSON của client.

### 3.4. 401 khác 403 thế nào?

- **401 Unauthorized** thường nghĩa là request chưa có thông tin xác thực phù hợp hoặc token được trình không thể xác thực.
- **403 Forbidden** thường nghĩa là identity/token đã được xác thực nhưng **không đủ quyền** để thực hiện hành động.

Trong Spring Security, **AccessDeniedException** có thể xuất hiện ở nhiều trạng thái; cách **ExceptionTranslationFilter** quyết định gọi entry point hay access denied handler còn phụ thuộc Authentication hiện tại. Do đó status không chỉ do tên exception quyết định.

Một ứng dụng cũng có thể trả **404 Not Found** để che giấu sự tồn tại tài nguyên theo domain policy. Khi đó phải phân biệt chính sách che dữ liệu với xử lý **insufficient_scope** theo chuẩn Bearer; không nên mặc định mọi AccessDeniedException đều phải phơi bày scope.

## 4. Thiếu token: Bearer challenge không kèm error

Một chi tiết RFC 6750 rất dễ bị bỏ qua: **khi request không chứa thông tin authentication**, server **SHOULD NOT** đưa ra error code hoặc error information cụ thể.

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Điều này khác với token sai:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <invalid-access-token>
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

**Không nhất thiết có token thì mới phải có header WWW-Authenticate.** RFC 6750 yêu cầu Resource Server gửi challenge khi protected resource request không có credentials hoặc không có token đủ khả năng truy cập. Challenge giúp client biết scheme cần dùng.

Không dùng **invalid_token** như mã lỗi bắt buộc cho request hoàn toàn không gửi credential; trong tình huống đó chưa có token để kết luận nó “invalid”.

## 5. Sơ đồ quyết định khi Resource Server nhận Bearer request

~~~mermaid
flowchart TD
    R[HTTP request tới protected endpoint] --> T{Có Bearer token phù hợp cú pháp?}
    T -->|Không có credential| C[401 + WWW-Authenticate Bearer, không error]
    T -->|Malformed / duplicate| B[Bearer error: invalid_request hoặc mapping framework]
    T -->|Có token| V{JWT verify hoặc introspection đạt?}
    V -->|Không| I[401 + error=invalid_token]
    V -->|Có| Q{Claims/token policy hợp lệ?}
    Q -->|Không| I
    Q -->|Có| A{Đủ scope/authority?}
    A -->|Không| F[403 + error=insufficient_scope nếu nhận diện OAuth2 authentication]
    A -->|Có| D{Quyền dữ liệu/tenant hợp lệ?}
    D -->|Không| P[403/404 theo domain policy]
    D -->|Có| OK[Cho phép controller/service xử lý]
~~~

Đây là sơ đồ **logic**, không áp đặt cùng một HTTP response cho mọi implementation. Ví dụ:

- **invalid_request** theo RFC thường 400; trường hợp header malformed cụ thể có thể được framework diễn giải khác.
- Một access denied handler có thể không chứng minh được Authentication là OAuth2; khi đó nó có thể chỉ trả Bearer challenge chung thay vì **insufficient_scope**.
- Domain policy từ chối một bản ghi không nhất thiết muốn tiết lộ scope hay mô tả lỗi.
- Nếu không chain Spring Security nào xử lý request, không thể dựa vào sơ đồ này để suy ra API đã được bảo vệ.

## 6. Các thành phần Spring Security tham gia

Trong **Servlet Resource Server**:

~~~mermaid
flowchart LR
    H[Authorization: Bearer token] --> F[BearerTokenAuthenticationFilter]
    F --> M[AuthenticationManager / Provider]
    M --> J[JwtDecoder hoặc OpaqueTokenIntrospector]
    J -->|Thất bại| E[BearerTokenAuthenticationEntryPoint]
    J -->|Thành công| A[Authentication trong SecurityContext]
    A --> R[authorizeHttpRequests / method security]
    R -->|Thiếu quyền| D[BearerTokenAccessDeniedHandler]
    E --> W[HTTP status + WWW-Authenticate]
    D --> W
    R -->|Đủ quyền| C[Controller / Service]
~~~

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Lấy token qua BearerTokenResolver và yêu cầu xác thực |
| **DefaultBearerTokenResolver** | Mặc định tìm Bearer token trong Authorization header và áp quy tắc parse |
| **JwtAuthenticationProvider/JwtDecoder** | Xác minh JWT signature, issuer, thời hạn và validators được cấu hình |
| **OpaqueTokenAuthenticationProvider/OpaqueTokenIntrospector** | Kiểm token qua introspection đã được tin cậy |
| **BearerTokenAuthenticationEntryPoint** | Khởi phát phản hồi khi authentication thiếu/thất bại; tạo Bearer challenge |
| **BearerTokenAccessDeniedHandler** | Xử lý quyền truy cập bị từ chối, có thể tạo insufficient_scope challenge |
| **BearerTokenError** | Mang error code, HTTP status, description, URI và scope |
| **BearerTokenErrors** | Factory tạo những error phổ biến trong RFC 6750 |
| **ExceptionTranslationFilter** | Điều phối AuthenticationEntryPoint/AccessDeniedHandler khi exception đi qua filter chain tương ứng |

**BearerTokenAuthenticationEntryPoint** và **BearerTokenAccessDeniedHandler** có vai trò khác nhau. Chúng không phải là các thành phần giải mã JWT hay introspect opaque token.

### 6.1. BearerTokenAuthenticationEntryPoint

Lớp:

~~~text
org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint
~~~

Đây là implementation **AuthenticationEntryPoint**, dùng **BearerTokenError** trong **OAuth2AuthenticationException** khi có để xác định HTTP status và những tham số trong **WWW-Authenticate**.

Ví dụ:

- Không có token ở protected endpoint → thường tạo challenge **Bearer** cùng realm nếu cấu hình, không kèm error.
- Một token bị JwtDecoder từ chối → có thể tạo challenge với **error="invalid_token"**.
- Một request malformed được biểu diễn bằng **BearerTokenError invalid_request** → entry point có thể dùng HTTP status **400** từ error.

API **setRealmName(String)** giúp thiết lập realm mặc định.

### 6.2. BearerTokenAccessDeniedHandler

Lớp:

~~~text
org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler
~~~

Đây là implementation **AccessDeniedHandler** cho request bị từ chối quyền.

Theo Java API của Spring Security, nếu handler **có đủ bằng chứng request mang OAuth 2.0 Authentication hợp lệ**, nó có thể trả **insufficient_scope**. Nếu không xác định được authentication như vậy, handler thường chỉ biểu diễn scheme **Bearer** và realm cấu hình, thay vì chắc chắn gắn **insufficient_scope**.

Điều này tránh một suy luận sai:

> Không phải cứ thấy HTTP 403 trong Spring Security là response bắt buộc có error="insufficient_scope".

Một số 403 đến từ CSRF, quyền tài nguyên/tenant, custom access denied handler hoặc cơ chế khác. Header thực tế phụ thuộc **security chain, handler, authentication type và nguyên nhân từ chối**.

### 6.3. BearerTokenError và BearerTokenErrors

Các class trong package:

~~~text
org.springframework.security.oauth2.server.resource
~~~

**BearerTokenErrors** cung cấp factory method như:

~~~java
BearerTokenErrors.invalidRequest("Malformed bearer request");
BearerTokenErrors.invalidToken("Invalid access token");
BearerTokenErrors.insufficientScope("Insufficient scope", "orders.approve");
~~~

Đây là các đối tượng lỗi, không tự động ghi HTTP response nếu không đi qua handler phù hợp.

**BearerTokenError** có các trường liên quan tới error code, HTTP status, description, error URI và scope. **BearerTokenAuthenticationEntryPoint** biết cách đọc dữ liệu này để dựng challenge. Khi custom, cần chú ý mô tả lỗi đúng tập ký tự RFC và không chứa token/secret.

## 7. Cấu hình Resource Server tự tạo Bearer challenge

Một cấu hình Spring Boot cơ bản cho JWT Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Ví dụ Servlet **SecurityFilterChain**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Với cấu hình mặc định phù hợp, Spring Security sử dụng Bearer-specific entry point và access denied handler cho Resource Server.

- **GET /api/orders/42** không có token: thường **401** và Bearer challenge.
- Token JWT sai chữ ký, issuer, audience hoặc hết hạn: thường **401** với Bearer error tương ứng.
- Token hợp lệ nhưng chỉ có **orders.write** khi gọi GET cần **orders.read**: thường **403** và có thể có **insufficient_scope**.
- Token hợp lệ, đúng scope: đi vào handler; service còn cần kiểm quyền trên đơn 42.
- Endpoint **/api/public/** được **permitAll**: không yêu cầu authentication để qua rule, nhưng security filters vẫn có thể xử lý một Bearer token mà client gửi.

**Các status/header là hành vi thông dụng**, không nên khẳng định luôn giống hệt từng byte trong mọi bản Spring Boot/Spring Security, vì cấu hình realm, handler, metadata extension hoặc custom security có thể thay đổi chúng.

## 8. Tùy chỉnh realm bằng các handler chuẩn

Đôi khi API muốn thể hiện một realm ổn định, ví dụ **orders-api**, để client hoặc log dễ phân biệt protection space.

Có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ChallengeConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler deniedHandler =
            new BearerTokenAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Dòng **authenticationEntryPoint(entryPoint)** và **accessDeniedHandler(deniedHandler)** áp vào cấu hình OAuth2 Resource Server tương ứng. Nếu ứng dụng có nhiều SecurityFilterChain, phải gắn đúng handlers vào chain thực sự xử lý request.

**realm không có nghĩa issuer.** Dù header có **realm="orders-api"**, điều đó không thay thế kiểm **iss**, **aud**, key source hay ownership. Realm là thông tin protection space theo HTTP, không phải bằng chứng token được Authorization Server cấp.

### 8.1. Có nên tự nối chuỗi WWW-Authenticate?

Thường **không cần**. Các handler chuẩn đã biết cách lấy thông tin từ Spring Security exceptions. Tự nối:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer realm=\"" + untrustedValue + "\""
);
~~~

có thể tạo lỗi escaping, header injection hoặc làm mất thông tin **error/description/scope**. Nếu cần response format rất đặc biệt, hãy giới hạn giá trị theo RFC, dùng nguồn cấu hình đáng tin và kiểm bằng tests.

### 8.2. Một số phiên bản có thể thêm resource_metadata

Các phiên bản Spring Security mới hơn có thể hỗ trợ tham số mở rộng **resource_metadata** liên quan tới OAuth Protected Resource Metadata, theo **RFC 9728**. Tham số này không phải một trong năm tham số cốt lõi được RFC 6750 §3 nêu ra, nhưng RFC cho phép các auth-param mở rộng.

Ví dụ mô hình header trên một version hỗ trợ extension:

~~~http
WWW-Authenticate: Bearer realm="orders-api", resource_metadata="https://orders-api.example.com/.well-known/oauth-protected-resource"
~~~

Không nên cho rằng mọi bản Spring Security đều trả **resource_metadata**, hoặc sao chép nguyên URL trong ví dụ cho mọi deployment. Nếu có proxy/context path, cần bảo đảm endpoint metadata được công bố đúng và không tạo URL từ Host/Forwarded header không đáng tin.

**resource_metadata** cũng không thay thế **error_uri**: một bên mô tả protected resource, bên kia là URI tài liệu giải thích lỗi cụ thể.

## 9. Opaque token cũng dùng cùng kiểu Bearer challenge

Đổi cấu hình JWT sang opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: replace-through-secret-manager
~~~

Và trong SecurityFilterChain:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Sự khác biệt chính nằm ở cách **xác thực token**:

- JWT: JwtDecoder kiểm chữ ký, issuer, audience/timestamps theo validators.
- Opaque: OpaqueTokenIntrospector liên hệ Authorization Server tin cậy, kiểm kết quả introspection và policy.

Nhưng bên client, HTTP header vẫn là:

~~~http
Authorization: Bearer <access-token>
~~~

và lỗi phía Resource Server vẫn dùng **Bearer challenge** theo RFC 6750 trong các tình huống thích hợp.

Nếu opaque token bị thu hồi và AS trả **active=false**, Resource Server thường trả **401** với **invalid_token**. Nếu token active nhưng thiếu **SCOPE_orders.read**, thường là **403** với challenge tương ứng.

**Không phân biệt JWT hay opaque token bằng mã error trong WWW-Authenticate.** Những mã này mô tả tình trạng xác thực/quyền Bearer, không tiết lộ bắt buộc token representation.

## 10. invalid_request và vị trí trình Bearer token

RFC 6750 §2 mô tả ba phương thức truyền access token tới Resource Server:

1. **Authorization header** — cách khuyến nghị và được Spring Security hỗ trợ mặc định.
2. **Form-encoded body parameter** trong các điều kiện chặt chẽ của đặc tả.
3. **URI query parameter** — chỉ để tương thích một số tình huống; RFC không khuyến nghị do token dễ lộ.

**Client MUST NOT sử dụng nhiều hơn một phương thức truyền token trong cùng một request.** Ví dụ một request vừa có Bearer header vừa có **access_token** query parameter (khi server hỗ trợ query token) có thể dẫn đến **invalid_request**.

### 10.1. Request hợp lệ dùng Authorization header

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <access-token>
~~~

Đây là phương thức nên dùng. Token phải được bảo vệ bằng HTTPS và tránh lưu trong logs.

### 10.2. Request dùng hai phương thức

~~~http
GET /api/orders/42?access_token=<second-token> HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer <first-token>
~~~

Theo RFC, gửi token bằng nhiều hơn một phương thức trong cùng request là không hợp lệ. Khi resolver **được cấu hình cho phép đọc query token**, nó có thể phát hiện trùng và báo **invalid_request**.

**Nhưng Spring Security DefaultBearerTokenResolver mặc định không nhận token từ URI query hoặc form body.** Vì vậy, không được khẳng định nó chắc chắn báo lỗi trùng phương thức trên cấu hình mặc định nếu một phương thức bị tắt. Khi kiểm security, hãy xác nhận cấu hình **BearerTokenResolver** thực tế.

### 10.3. DefaultBearerTokenResolver

Trong Servlet Resource Server:

~~~text
org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver
~~~

Các tùy chọn cần biết:

| API | Mặc định và ý nghĩa |
|---|---|
| **setAllowUriQueryParameter(boolean)** | Mặc định **false**, không đọc Bearer token từ URL query |
| **setAllowFormEncodedBodyParameter(boolean)** | Mặc định **false**, không đọc token từ form body |
| **setBearerTokenHeaderName(String)** | Mặc định **Authorization**; có thể đổi sang header khác khi cần |

Không bật truyền token bằng query parameter chỉ để thao tác thử tiện hơn. URL dễ xuất hiện trong browser history, proxy access logs, referer, telemetry hoặc bookmark. Nên ưu tiên Authorization header qua HTTPS.

### 10.4. Request malformed không luôn có cùng status từ mọi parser

Về mặt RFC, **invalid_request/400** là mô hình thường gặp cho malformed Bearer request. Tuy nhiên trong Spring Security, code path cụ thể có thể tạo:

- **BearerTokenErrors.invalidRequest(...)** cho request có nhiều token.
- **BearerTokenErrors.invalidToken(...)** cho một số Bearer header sai format.

Do đó, nếu test mong **400** cho tất cả chuỗi Authorization malformed, test có thể không khớp implementation/version. Hãy xác nhận **error code và HTTP status** do BearerTokenResolver/entry point thực tế phát sinh.

Đừng thay lỗi **invalid_token** thành **insufficient_scope** chỉ vì muốn client xin thêm quyền; hai lỗi có nguyên nhân và cách xử lý khác nhau.

## 11. Điều gì xuất hiện trên 403?

Một phản hồi 403 có thể đến từ nhiều cơ chế:

| Nguyên nhân | Đặc trưng |
|---|---|
| OAuth2 token hợp lệ nhưng thiếu scope/authority | Có thể được diễn giải thành **insufficient_scope** |
| Role/permission ứng dụng chưa đủ | AccessDeniedException, có thể được handler tùy biến xử lý |
| Kiểm ownership/tenant thất bại | Domain policy từ chối; có thể trả 403/404 |
| CSRF từ chối request trong ứng dụng dùng CSRF protection | Không đồng nghĩa thiếu OAuth scope |
| Access denied từ chain không thuộc OAuth2 Resource Server | Không chắc dùng Bearer-specific handler |

Theo JavaDoc, **BearerTokenAccessDeniedHandler** chỉ phát **insufficient_scope** khi đủ căn cứ authentication là OAuth2 hợp lệ. Nếu không, nó có thể chỉ trả scheme Bearer/realm.

### 11.1. Ví dụ scope khác role

Authentication có:

~~~text
SCOPE_orders.read
ROLE_SUPPORT
~~~

Endpoint yêu cầu:

~~~java
.hasRole("ADMIN")
~~~

Không đạt vì thiếu **ROLE_ADMIN**. Trả 403 là hợp lý theo policy, nhưng client **không thể tự suy ra** rằng thêm OAuth2 scope orders.write sẽ giúp qua hasRole ADMIN.

Nếu API dùng các authority không phải scope, cần thiết kế thông báo lỗi có trách nhiệm. Đừng tự động gửi **scope="ADMIN"** nếu ADMIN là role nội bộ không phải OAuth scope mà Authorization Server cấp.

### 11.2. scope trong challenge có nên tiết lộ?

**scope** là auth-param tùy chọn. Nếu đưa ra, phải bảo đảm:

- Scope thực sự là scope thuộc hợp đồng OAuth2 của API.
- Tên scope đúng phân biệt hoa/thường.
- Không lộ tên permission/chi tiết nội bộ không nên công bố.
- Client hiểu đó là scope cần xin từ Authorization Server, **không phải giá trị client tự ghi vào token**.
- Khi endpoint có điều kiện quyền phức tạp, không tạo gợi ý scope thiếu/chưa chắc đủ.

Các rule **hasAuthority("SCOPE_...")** không nhất thiết khiến Spring Security tự suy ra tên scope cần thiết để chèn vào WWW-Authenticate. Nếu cần thông báo scope cụ thể, phải thiết kế/tùy biến phù hợp.

## 12. Client nên xử lý Bearer challenge thế nào?

Bên API client, nên phân loại tối thiểu:

| HTTP/challenge | Cách xử lý thường hợp lý |
|---|---|
| **401 Bearer, không error** | Chưa gửi credential hoặc chưa xác thực; xác định cách lấy access token hợp lệ |
| **401 + invalid_token** | Không tái sử dụng token đã bị từ chối; thử lấy token mới theo OAuth flow/refresh policy |
| **400 + invalid_request** | Sửa cấu trúc/phương thức gửi Bearer token; không retry nguyên request vô hạn |
| **403 + insufficient_scope** | Xác định quyền cần thiết và xem user/client có thể được cấp scope đó không |
| **403 không có insufficient_scope** | Có thể là authorization/domain policy khác; không giả định refresh token sẽ giải quyết |
| **5xx từ API/upstream authentication** | Xử lý lỗi tạm thời theo retry/backoff phù hợp; không phát tán credentials |

Một client **không được** mặc định lặp refresh token và gửi lại vô hạn mỗi khi gặp 401. Nếu issuer, audience, resource hoặc scope không phù hợp, lấy thêm access token cùng loại có thể vẫn thất bại. Giới hạn retry và xử lý lỗi cấu hình.

### 12.1. WWW-Authenticate không phải OAuth token response

Authorization Server trả **token response** với các trường như **access_token**, **token_type**, **expires_in** khi cấp token thành công. Resource Server trả **WWW-Authenticate** khi challenge access tới protected resource.

Ví dụ không được hiểu:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

là một URL redirect bắt buộc, một authorization endpoint hoặc chỉ dẫn gửi **client secret** tới Resource Server. Nó chỉ mô tả HTTP authentication scheme của protected resource.

### 12.2. 401 không phải lời mời chuyển sang HTTP Basic

Nếu Resource Server gửi **Bearer** challenge, client nên dùng Bearer access token theo OAuth2. Đổi sang Basic username/password cho endpoint API không phải phương án đúng trừ khi API thật sự quảng bá và cho phép Basic authentication riêng.

## 13. Test bằng curl: xem status và header

Giả sử một Orders API ở môi trường test:

~~~text
https://orders-api.example.com/api/orders/42
~~~

### 13.1. Không gửi token

~~~bash
curl --include --silent --show-error \
  https://orders-api.example.com/api/orders/42
~~~

Quan sát:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Một response thực tế có thể khác ở realm hoặc các auth-param mở rộng. Tiêu chí quan trọng: **protected endpoint không được cho qua chỉ vì request thiếu token** và có Bearer challenge phù hợp.

### 13.2. Gửi token không hợp lệ

~~~bash
curl --include --silent --show-error \
  -H "Authorization: Bearer not-a-valid-access-token" \
  https://orders-api.example.com/api/orders/42
~~~

Response thường gặp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không gửi credential thật vào ví dụ, logs hoặc ticket. Các chuỗi trong ví dụ là giả định để học.

### 13.3. Gửi token hợp lệ nhưng thiếu scope

Cần một **test token** được cấp bởi issuer test, đúng audience nhưng thiếu **orders.read**.

~~~bash
curl --include --silent --show-error \
  -H "Authorization: Bearer <valid-test-token-without-orders-read>" \
  https://orders-api.example.com/api/orders/42
~~~

Response có thể là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Với cấu hình tùy biến, có thể có **realm** và **scope**. Không được tự gõ raw token production vào shell có history/logs không được kiểm soát. Dùng môi trường và token test phù hợp.

### 13.4. Khi curl thấy header nhưng browser không đọc được

Browser JavaScript chạy **cross-origin fetch** có thể bị CORS giới hạn quyền đọc response headers. **WWW-Authenticate không phải mặc định một CORS-safelisted response header**.

Nếu ứng dụng cần cho frontend đọc header này, CORS policy của server có thể phải expose rõ:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Điều kiện này **không cấp quyền truy cập API** và không thay thế JWT verification. Nó chỉ cho phép browser JavaScript truy cập header theo CORS policy. Cũng cần cấu hình allowed origins, methods, credentials và preflight phù hợp; không mở CORS vô điều kiện.

## 14. Kiểm thử Spring Security bằng MockMvc

Đối với Servlet Spring Security, có thể dùng **MockMvc với security filters được bật** để kiểm phản hồi.

### 14.1. Test request không có token

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

// Trong test class đã inject MockMvc và tải SecurityFilterChain thật.
@Test
void protectedEndpointWithoutTokenHasBearerChallenge() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("Bearer")
        ));
}
~~~

Nếu application config đặt realm, có thể assert thêm realm. Nhưng không nên yêu cầu **error="invalid_token"** cho request không chứa token, vì RFC khuyên không đưa error info trong trường hợp ấy.

### 14.2. Test token giả được decoder từ chối

Một bài integration test nên cấu hình **JwtDecoder** bằng test issuer/key phù hợp hoặc mock decoder **chủ động ném JwtException** khi nhận token giả. Sau đó gửi Authorization header thật qua security filters, kiểm status 401 và Bearer challenge.

Ví dụ request assertion, giả định test fixture đã bảo đảm decoder từ chối token:

~~~java
@Test
void invalidJwtHasInvalidTokenChallenge() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer a-rejected-test-token"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            containsString("invalid_token")
        ));
}
~~~

**Chỉ dùng assertion trên khi decoder/test fixture chắc chắn từ chối token đầu vào**. Nếu test không chạy JwtDecoder thật, kết quả không chứng minh signature verification production. Một MockMvc test chỉ dùng **jwt() request post-processor** cũng thường bỏ qua bước decode JWT signature.

### 14.3. Test scope thiếu bằng Authentication mô phỏng

Spring Security Test có **jwt()** để tạo Authentication trong test authorization:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthWithoutReadScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

Bài test trên kiểm rule **hasAuthority("SCOPE_orders.read")**. Nó không chứng minh token đã được issuer ký hoặc decoder đã hoạt động. Nếu muốn assert **insufficient_scope** trong WWW-Authenticate, cần test với **BearerTokenAccessDeniedHandler phù hợp** và Authentication dạng OAuth2 mà handler nhận diện được.

### 14.4. Test header vừa đủ linh hoạt

Không nên chỉ assert:

~~~java
header().string(HttpHeaders.WWW_AUTHENTICATE,
    "Bearer realm=\"orders-api\"")
~~~

trong mọi test, nếu framework có thể thêm **resource_metadata** hoặc chi tiết lỗi theo version. Có thể:

- Assert **HTTP status** rõ.
- Assert header hiện diện và chứa **Bearer**.
- Assert **error="invalid_token"** hoặc **error="insufficient_scope"** trong test mà setup thật sự tạo tình huống đó.
- Assert realm và scope nếu chúng là **hợp đồng của ứng dụng**.
- Khi cần parser-level compliance, dùng trình parse phù hợp thay vì tìm một chuỗi con có thể xuất hiện trong description.

Một số test có thể kiểm exact header để khóa một API contract, nhưng cần có chủ đích và test fixture/version ổn định.

### 14.5. Test không có handler không có giá trị tương tự

Nếu gọi một URL không tồn tại và thấy **404**, không thể kết luận Spring Security đã trả đúng Bearer challenge cho endpoint cần bảo vệ. Test phải gọi **endpoint có handler thật** hoặc test-only route, với security filters được bật.

**@AutoConfigureMockMvc(addFilters=false)** hoặc **standaloneSetup** không tự chạy filter chain như production. Khi test security response, cần gắn **springSecurityFilterChain** hoặc dùng Spring Boot test context có filters.

## 15. Rủi ro khi middleware/proxy thay đổi response

Challenge được tạo ở Resource Server nhưng có thể đi qua gateway, ingress hoặc reverse proxy.

Các lỗi vận hành thường thấy:

- Gateway **loại bỏ WWW-Authenticate** và chỉ giữ status 401.
- Gateway **thay 401 thành 302 redirect** đến trang login HTML, khiến OAuth API client khó xử lý.
- Proxy trả 401 từ một authentication scheme khác như Basic, che Bearer challenge của backend.
- API Gateway tự tạo 403 nhưng không dùng cùng policy Bearer.
- CORS khiến browser không đọc được WWW-Authenticate.
- Response cache/CDN giữ nhầm phản hồi chứa metadata nhạy cảm hoặc trộn phản hồi theo người dùng.
- Application exception handler đổi toàn bộ authentication failures thành 200 với JSON **success=false**.

**Một API có SecurityFilterChain đúng chưa chắc người dùng ngoài Internet nhận header đúng** nếu proxy thay đổi response. Cần test ở **backend** và qua **public URL thực tế**.

### 15.1. Nhiều WWW-Authenticate challenges

Theo HTTP, server có thể quảng bá nhiều authentication schemes hoặc nhiều challenge. Khi đi qua proxy, cần bảo đảm header fields được chuyển/ghép theo đúng ngữ nghĩa HTTP, tránh parser không nhận được Bearer challenge.

Không gộp challenge với **Proxy-Authenticate**: **WWW-Authenticate** là challenge cho origin resource, còn Proxy-Authenticate liên quan tới proxy authentication.

### 15.2. Reverse proxy và scheme/host đáng tin

Nếu framework tạo các URL mở rộng (chẳng hạn resource_metadata), cấu hình reverse proxy có thể ảnh hưởng scheme/host bên ngoài. Không tin **Host**, **Forwarded** hoặc **X-Forwarded-*** từ client không đáng tin để dựng metadata URL trỏ tới attacker. Chỉ xử lý forwarded headers từ proxy đã được xác thực/quản trị.

## 16. Không dùng WWW-Authenticate như kênh tiết lộ thông tin

Response header là dữ liệu phía client có thể quan sát. Vì thế:

- Không đưa **raw access token**, refresh token, client secret hoặc private signing key vào error_description.
- Không tiết lộ stack trace, path file, database query, key material hay cấu hình nội bộ.
- Không phản chiếu trực tiếp giá trị chưa xác thực từ request vào header.
- Không dùng mô tả lỗi quá chi tiết để phân biệt token tồn tại/hết hạn/đã bị thu hồi nếu điều đó làm tăng khả năng dò token.
- Giới hạn thông tin về scopes/roles nhạy cảm; chỉ công bố những scope API contract cho phép.
- Ghi nhận lỗi qua request ID/metric có kiểm soát, không log Authorization header.
- Dùng HTTPS để bảo vệ Bearer token ở request; WWW-Authenticate không thay thế TLS.
- Cẩn thận với HTTP response splitting/CRLF injection khi custom header.

Một lỗi tốt cho client là **có thể xử lý được**, nhưng không cần kể mọi chi tiết bảo mật nội bộ.

### 16.1. error_uri nên chỉ đến tài liệu ổn định

Nếu đưa **error_uri**, nên dùng một URL tài liệu công khai, ổn định và được phép truy cập:

~~~http
WWW-Authenticate: Bearer error="invalid_token", error_uri="https://docs.example.com/api/auth/errors#invalid-token"
~~~

Không đưa URI nội bộ hoặc token vào query string. **error_uri** không phải kênh refresh access token tự động và không nên khiến client gửi credentials sang URL lạ.

### 16.2. Không coi realm là ranh giới phân quyền

Ví dụ:

~~~http
WWW-Authenticate: Bearer realm="tenant-a"
~~~

không chứng minh tenant A là issuer hoặc client đang được phép truy cập tenant A. **Realm** chỉ là metadata challenge. Resource Server vẫn phải kiểm signature/introspection, issuer, audience và tenant/ownership policy độc lập.

## 17. Một số tình huống 401/403/400 cần phân biệt

| Request/tình trạng | HTTP thường gặp | Bearer challenge |
|---|---|---|
| Protected endpoint, không Authorization | **401** | **Bearer** với realm nếu cấu hình; thường không error |
| JWT đã gửi nhưng chữ ký sai | **401** | **error="invalid_token"** |
| JWT đúng chữ ký nhưng sai issuer/audience | **401** | **error="invalid_token"** |
| JWT hết hạn | **401** | **error="invalid_token"**, mô tả nếu được công bố |
| Opaque token bị AS trả active=false | **401** | **error="invalid_token"** |
| Gửi nhiều token theo nhiều phương thức được resolver phát hiện | **400** theo khuyến nghị RFC | **error="invalid_request"** |
| Bearer header malformed | Tùy lỗi resolver/version | Có thể invalid_token hoặc invalid_request |
| Token hợp lệ, thiếu scope cần thiết | **403** | Có thể **error="insufficient_scope"** |
| Token hợp lệ, có scope nhưng không sở hữu tài nguyên | **403** hoặc **404** theo domain policy | Không bắt buộc phơi bày scope |
| Không khớp bất kỳ SecurityFilterChain nào | Không thể suy ra | Không bảo đảm có Bearer challenge |
| CORS preflight OPTIONS | Tùy CORS/security policy | Không phải bằng chứng request GET/POST đã xác thực |
| Introspection upstream timeout | Lỗi hạ tầng xác thực | Không fail-open; status/headers theo exception mapping |

**Không dùng trạng thái HTTP đơn lẻ để kết luận request đã hoặc chưa qua JWT validation.** Hãy kiểm SecurityFilterChain, exception path, Authentication type và các headers thực tế.

## 18. Troubleshooting khi WWW-Authenticate không như mong đợi

### 18.1. API trả 401 nhưng không có WWW-Authenticate

Các nguyên nhân có thể:

- Response 401 do controller tự trả, không đi qua Bearer entry point.
- Custom AuthenticationEntryPoint ghi status nhưng bỏ header.
- Request không khớp SecurityFilterChain cần thiết.
- API Gateway hoặc reverse proxy loại bỏ header.
- Browser CORS không expose header cho JavaScript.
- Một security chain khác với form login/Basic được chọn trước.

Cách kiểm: gọi backend trực tiếp trong môi trường được phép bằng **curl -i**, xem chain/filter configuration, sau đó so với response qua public gateway.

### 18.2. API trả login HTML hoặc 302 thay vì Bearer challenge

Có thể Resource Server chain không được chọn, còn security chain web-login được chọn. Kiểm **@Order**, **securityMatcher**, **ExceptionTranslationFilter** và Resource Server DSL.

Một API thuần thường nên trả status/challenge rõ thay vì redirect trang đăng nhập HTML, trừ khi kiến trúc chủ động hỗ trợ một luồng khác.

### 18.3. API trả 403 nhưng không có insufficient_scope

Có thể đó là:

- Domain-level AccessDeniedException, không trực tiếp do OAuth scope.
- Authentication không thuộc loại mà BearerTokenAccessDeniedHandler chứng minh được là OAuth2.
- AccessDeniedHandler đã bị tùy biến.
- CSRF hoặc policy khác.
- Header bị proxy/cors che khuất.

Không nên ép mọi 403 thành **insufficient_scope**, vì sẽ làm client suy ra sai cách khắc phục.

### 18.4. Client nhận invalid_token dù token JWT giải mã ra claims đẹp

JWT có thể được Base64URL-decode nhưng sai signature, issuer, audience, thời hạn hoặc token type. **Đọc claims không thay thế xác minh JWT**, và token do issuer ký cho API khác vẫn có thể bị từ chối.

### 18.5. Client nhận invalid_request với nhiều token

Kiểm Authorization header, query parameter, form body và cấu hình resolver. Không gửi cùng lúc token ở hai vị trí. Tránh tự bật token query parameter để thuận tiện debug.

### 18.6. Header chứa resource_metadata bất ngờ

Đây có thể là extension từ Spring Security release mới liên quan OAuth Protected Resource Metadata. Kiểm framework version và Resource Server configuration. Đừng coi nó là invalid_request chỉ vì RFC 6750 nguyên thủy không liệt kê tham số đó.

### 18.7. Mô tả lỗi có ký tự không hợp lệ

Khi tự xây header, một message tiếng Việt có dấu, dấu quote hoặc xuống dòng có thể không đáp ứng tập ký tự của RFC 6750. Tránh nhét text Unicode tùy ý vào auth-param; đặt thông điệp địa phương hóa trong response body theo API contract, giữ header theo cú pháp chuẩn.

## 19. Checklist thiết kế Bearer error response

Trước khi đưa API vào vận hành, cần trả lời:

1. **Protected endpoint không token** có trả HTTP 401 và Bearer challenge không?
2. Có phân biệt token **không có** với token **invalid** không, tránh phát error chi tiết khi chưa có credential?
3. JWT/opaque token không hợp lệ có được xử lý qua JwtDecoder/introspection đáng tin cậy trước khi sinh lỗi không?
4. Token hợp lệ thiếu scope có ra **403**, không bị nhầm thành lỗi signature không?
5. **BearerTokenAuthenticationEntryPoint** và **BearerTokenAccessDeniedHandler** có được gắn đúng SecurityFilterChain không?
6. Có chain khác hoặc proxy nào thay đổi status/header không?
7. Nếu tùy chỉnh realm, mọi chain liên quan dùng realm nhất quán chứ?
8. **error_description**, **error_uri**, **scope** có tránh rò rỉ thông tin/credential và đúng ký tự RFC không?
9. Mẫu JSON lỗi tùy biến có giữ nguyên WWW-Authenticate khi cần không?
10. CORS có expose WWW-Authenticate cho frontend khi thực sự cần không?
11. Test có phân biệt **401 không token**, **401 invalid_token**, **400 invalid_request** khi phù hợp và **403 thiếu quyền** không?
12. MockMvc đã bật security filters và dùng handler có thật chưa?
13. Các kiểm thử đi qua gateway/ingress có cho cùng kết quả như backend không?
14. Client có giới hạn retry/refresh token và không tự nâng scope không?
15. Có test cho một bearer header malformed trên đúng phiên bản Spring Security, thay vì giả định status cố định không?

## 20. Bài tập thực hành

Giả sử Orders API có policy:

~~~text
Issuer: https://login.example.com/realms/shop
Audience: orders-api
GET /api/orders/**  -> SCOPE_orders.read
POST /api/orders/** -> SCOPE_orders.write
Realm: orders-api
~~~

Hãy dự đoán:

**A. GET /api/orders/42 không có Authorization header**

Một phản hồi phù hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Không nhất thiết có **error**.

**B. GET /api/orders/42 với JWT giả, sai chữ ký**

Một phản hồi phù hợp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Dù JWT tự khai đúng iss/aud/scope, chữ ký không được issuer xác nhận nên không hợp lệ.

**C. POST /api/orders/42 chỉ có scope orders.read**

Một phản hồi phù hợp:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Tham số **scope** mang tính tùy chọn. Client cần được cấp token có scope phù hợp theo OAuth flow; không tự sửa JWT payload.

**D. GET /api/orders/42 có cả Authorization Bearer và access_token query**

Nếu Resource Server được cấu hình đọc cả hai vị trí và phát hiện token trùng phương thức:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
~~~

Nhưng nếu resolver mặc định **không** đọc query token, kết quả thực tế có thể khác. Bài tập yêu cầu nêu rõ **cấu hình resolver** trước khi dự đoán.

**E. GET /api/orders/42 với token hợp lệ nhưng đơn thuộc tenant khác**

Đây là **domain authorization failure**. Có thể trả 403 hoặc 404 theo chính sách bảo vệ tài nguyên; không nhất thiết phải công bố **scope** hay **insufficient_scope** nếu nguyên nhân không phải thiếu OAuth scope.

### 20.1. Bài tập nhận diện thành phần Spring Security

Điền nhiệm vụ:

| Thành phần | Nhiệm vụ |
|---|---|
| **DefaultBearerTokenResolver** | Tìm/đọc Bearer token từ request |
| **BearerTokenAuthenticationFilter** | Đưa token qua authentication flow |
| **JwtDecoder/OpaqueTokenIntrospector** | Xác minh token theo nguồn tin cậy |
| **BearerTokenAuthenticationEntryPoint** | Trả challenge cho authentication failure |
| **BearerTokenAccessDeniedHandler** | Xử lý từ chối quyền và challenge phù hợp |
| **BearerTokenErrors** | Tạo BearerTokenError chuẩn như invalid_token |
| **authorizeHttpRequests** | Kiểm authority/role/policy trên request |

Đặc biệt, **ExceptionTranslationFilter** tham gia điều phối exception từ downstream trong filter chain, còn **BearerTokenAuthenticationFilter** có thể trực tiếp gọi entry point khi Bearer authentication thất bại. Điều này giải thích vì sao không phải mọi lỗi đều đi qua cùng một handler.

## Kết luận

**WWW-Authenticate** là response header mang authentication challenge. Đối với OAuth 2.0 Resource Server, **RFC 6750** định nghĩa Bearer challenge và các mã lỗi **invalid_request**, **invalid_token**, **insufficient_scope**, với những status thường tương ứng **400**, **401**, **403**.

Phân biệt quan trọng nhất là:

- **Không có token:** 401 + Bearer challenge, thường **không error**.
- **Token không hợp lệ:** 401 + **invalid_token**.
- **Token hợp lệ nhưng thiếu scope:** 403 + **insufficient_scope** khi xử lý theo OAuth2 Bearer và handler có đủ thông tin.
- **Request sai cách trình token:** có thể **invalid_request/400**, tùy policy và implementation.

Trong Spring Security Servlet Resource Server, **BearerTokenAuthenticationEntryPoint** xử lý authentication challenge, **BearerTokenAccessDeniedHandler** xử lý từ chối quyền và **BearerTokenError** cung cấp metadata lỗi. Không tự viết header thiếu kiểm soát, không coi một status HTTP là bằng chứng JWT đã được xác minh và không để API Gateway, CORS hoặc custom exception handler làm mất Bearer challenge cần thiết.

### Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 3 và 3.1](https://www.rfc-editor.org/rfc/rfc6750#section-3)
- [RFC 9110 — HTTP Semantics: WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110#section-11.6.1)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [Spring Security — Servlet OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security API — BearerTokenError](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/BearerTokenError.html)
- [Spring Security API — BearerTokenErrors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/BearerTokenErrors.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
