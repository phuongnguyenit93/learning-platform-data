# Phân biệt lỗi token với lỗi thông tin xác thực introspection hoặc lỗi mạng

## 1. Vì sao một API trả 401 chưa chắc nghĩa là opaque token sai?

Trong **Spring Security OAuth 2.0 Resource Server**, khi API tiếp nhận **opaque access token**, Resource Server không tự giải mã token như JWT để kiểm tra chữ ký. Thay vào đó, Resource Server gọi **OAuth 2.0 Token Introspection** của Authorization Server (AS) theo **RFC 7662**.

Hệ thống tồn tại **hai HTTP hop độc lập**:

~~~text
Hop A: OAuth Client -> Resource Server
  GET /api/orders
  Authorization: Bearer OPAQUE_ACCESS_TOKEN

Hop B: Resource Server -> Authorization Server
  POST /oauth2/introspect
  Authorization: Basic <RS introspection client credentials>
  Content-Type: application/x-www-form-urlencoded
  Body: token=OPAQUE_ACCESS_TOKEN
~~~

Điểm dễ nhầm lẫn:

- **HTTP 200 + JSON {"active":false}** ở hop B: AS trả lời request introspection hợp lệ và nói token **không active**.
- **HTTP 401** ở hop B: AS có thể đang từ chối **client ID/client secret hoặc phương thức xác thực của chính Resource Server**. Điều này **không tự chứng minh opaque token của caller sai**.
- **HTTP 503/timeout/TLS failure** ở hop B: Resource Server không có phản hồi introspection đáng tin, nên **chưa có kết luận token active hay không**.

Tất cả các trường hợp trên đều phải **không cho protected request đi tiếp** nếu Resource Server chưa xác thực được credential đáng tin. Nhưng loại lỗi, cách retry, mã phản hồi tới caller và cách xử lý vận hành phải **khác nhau**.

### Mục tiêu của bài học

Bài này tập trung vào việc:

1. Phân biệt kết quả **token invalid/inactive**, **introspection client authentication failure**, **lỗi mạng/AS outage**, **lỗi protocol** và **thiếu quyền sau xác thực**.
2. Hiểu hai loại credential, hai HTTP status và cách chúng tương tác qua Spring Security Servlet filter chain.
3. Thiết kế fail-closed, error mapping, retry/caching và observability.
4. Nhận diện lỗi cấu hình Spring Boot Resource Server mà không tự viết JWT/Bearer filter song song.
5. Xây các kịch bản kiểm thử cho opaque token authentication và các lỗi phụ thuộc upstream.

## 2. Hai loại thông tin xác thực khác nhau

Hãy phân biệt các đối tượng:

| Đối tượng | Vai trò | Credential |
|---|---|---|
| OAuth Client | Lấy access token và gọi API | Bearer access token gửi cho RS |
| Resource Server | Bảo vệ API | Nhận và xác thực access token |
| Authorization Server | Phát hành token, xác thực token qua introspection | Quản lý token và introspection endpoint |
| Introspection client | Danh tính RS dùng để được AS cho phép introspect | Client ID/secret, mTLS hoặc phương thức AS hỗ trợ |

Ví dụ request client gửi đến API:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer OPAQUE_ACCESS_TOKEN
~~~

Request Resource Server gửi đến AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=OPAQUE_ACCESS_TOKEN
~~~

Trong hop B, **Basic credentials là của Resource Server**, không phải access token của user. Base64 trong Basic **không phải mã hóa bảo mật**; kết nối cần HTTPS/TLS và credentials phải được bảo vệ bằng secret manager phù hợp.

Không phải mọi Authorization Server dùng Basic. Một số hệ thống yêu cầu **private_key_jwt, mTLS** hoặc client authentication method khác theo hợp đồng. Resource Server phải dùng đúng phương thức và có quyền introspect token theo chính sách AS.

### Không nhầm credentials của AS với token của caller

~~~text
Bearer token:
  Dùng để gọi orders-api.
  Có thể active/inactive, hết hạn, thiếu scope.

Introspection client credentials:
  Dùng để orders-api gọi auth.example.com.
  Có thể sai secret, bị disable, thiếu quyền introspect.
~~~

Nếu RS dùng sai secret, AS có thể trả 401 ở hop B **cho mọi token**, kể cả token hoàn toàn hợp lệ. Yêu cầu user đăng nhập lại hoặc liên tục refresh token không giải quyết được lỗi cấu hình đó.

## 3. RFC 7662: response nào thực sự nói token không active?

Token introspection thường dùng POST với form body:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

**token_type_hint** là tham số tùy chọn giúp AS xử lý, không tự biến token thành access token hợp lệ. Quyền gọi endpoint còn phụ thuộc introspection client registration và policy của AS.

### 3.1. HTTP 200 và active=true

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "client_id": "shop-web",
  "sub": "user-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "iss": "https://auth.example.com",
  "exp": 1910003600
}
~~~

Đây là một response hợp lệ nói token **active** theo AS. Resource Server vẫn cần kiểm tra:

- Đúng **audience/resource binding** của API không?
- Token có thuộc profile được phép dùng làm access token không?
- Scope/authority có đủ cho endpoint không?
- Principal/client có quyền với tenant và object cụ thể không?
- Các metadata cần thiết có đầy đủ và nhất quán không?

**active=true không đồng nghĩa được gọi mọi API.** Một token active nhưng chỉ dành cho **billing-api** không được tự dùng gọi **orders-api**.

### 3.2. HTTP 200 và active=false

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

Đây mới là tín hiệu token được AS báo **không active**. Có thể có nhiều lý do:

- Token giả/không tồn tại.
- Token đã hết hạn.
- Token đã bị thu hồi.
- Token bị vô hiệu theo policy AS.
- Token không được AS công nhận trong ngữ cảnh introspection caller.
- AS không tiết lộ nguyên nhân theo chính sách bảo mật.

**Không khẳng định active=false = expired.** RFC 7662 chủ ý không yêu cầu AS nêu chi tiết vì sao token không active; một số AS dùng active=false cho những tình huống mà RS không được biết sự tồn tại của token.

Kết luận đúng:

~~~text
HTTP 200 + active=false từ AS đáng tin
  -> Token không được chấp nhận cho request này.
  -> Không tạo authenticated principal.
  -> Hop A thường trả 401 / Bearer invalid_token tùy cấu hình.
~~~

### 3.3. HTTP 200 nhưng JSON malformed

Ví dụ sai type:

~~~json
{
  "active": "true"
}
~~~

**active** trong RFC 7662 là boolean, không phải string. Ví dụ khác:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read"
}
~~~

Không có **active**.

Đây là **protocol/contract failure**, không được tự mặc định active=true hoặc tự đổi thành active=false. Một HTTP 200 có thể chứa HTML từ gateway hoặc JSON của endpoint khác; response phải đáp ứng đúng schema mà introspector trông đợi.

## 4. HTTP 401 từ introspection endpoint: lỗi RS-to-AS authentication

Ví dụ AS trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

Đây là **lỗi hop B**. RS có thể đang:

- Gửi sai client ID hoặc secret.
- Dùng secret cũ sau khi AS rotate credentials.
- Dùng client đã bị disabled hoặc chưa được cấp quyền introspect.
- Dùng Basic trong khi AS yêu cầu mTLS/private_key_jwt.
- Gọi sai endpoint/realm/tenant của Authorization Server.
- Gửi credentials ở vị trí không đúng.
- Bị reverse proxy xóa hoặc thay header Authorization.
- Dùng client certificate đã hết hạn khi AS yêu cầu mTLS.

Những lỗi trên **không đưa ra quyết định về access token của caller**.

~~~text
Opaque token của user: có thể active.
RS introspection secret: sai.

AS nhận POST introspection:
  -> trả 401 invalid_client
  -> không trả trạng thái token đáng tin.

Đánh giá đúng:
  INTROSPECTION_CLIENT_AUTH_FAILURE
  KHÔNG phải TOKEN_INACTIVE.
~~~

### HTTP 403 từ AS

Một AS hoặc gateway có thể trả 403 Forbidden nếu introspection client được nhận diện nhưng **không được phép** truy vấn token/realm/resource đó.

Cần kiểm tra quyền client registration, policy introspection và tenant binding. HTTP 403 ở hop B **khác** HTTP 403 ở hop A khi một user đã xác thực nhưng thiếu scope.

Status/error chính xác còn phụ thuộc Authorization Server, chính sách triển khai và HTTP gateway. Không suy đoán chắc chắn sai secret chỉ từ một status 401/403 khi chưa kiểm tra contract của AS.

## 5. HTTP 400: request introspection không hợp lệ

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_request"
}
~~~

Một số nguyên nhân:

- Thiếu tham số **token**.
- Gửi JSON khi endpoint chỉ nhận **application/x-www-form-urlencoded**.
- Sai encoding, tham số malformed hoặc request bị proxy thay đổi.
- Request trỏ đến endpoint token issuance thay vì introspection.
- Gửi phương thức HTTP hoặc cách xác thực không đúng hợp đồng.

**Không nên kết luận “token hết hạn” khi thấy HTTP 400 từ AS.** Với một token không active, một AS tuân RFC 7662 thường có thể trả **200 + active=false**. HTTP 400 cần được điều tra như **lỗi request/protocol**.

Một trường hợp có thể gây hiểu nhầm là endpoint được cấu hình sai: API gọi **/oauth2/token** hoặc endpoint login; server trả lỗi request, không phải introspection result.

## 6. HTTP 429/5xx, DNS, timeout và TLS: lỗi hạ tầng, không phải lỗi token

Các failure modes quan trọng:

| Triệu chứng | Phân loại | Có kết luận token inactive chưa? |
|---|---|---|
| HTTP 429 Too Many Requests | AS throttling/quota | **Chưa** |
| HTTP 500 | Lỗi nội bộ AS | Chưa |
| HTTP 502/503/504 | Gateway/AS unavailable | Chưa |
| DNS resolution failure | Network | Chưa |
| Connection refused/reset | Network | Chưa |
| Connect timeout | Network | Chưa |
| Read timeout | Network/AS chậm | Chưa |
| TLS certificate unknown/expired | TLS trust/configuration | Chưa |
| Hostname mismatch | TLS trust/configuration | Chưa |
| HTTP 200 nhưng nội dung sai schema | Protocol response error | Chưa |

Không có response introspection đáng tin **không tương đương** active=false.

Có thể ghi:

~~~text
Upstream did not answer in time
    !=
AS answered "active=false".
~~~

Cách ứng xử an toàn:

1. **Fail closed:** không xác thực opaque token khi không có bằng chứng hợp lệ.
2. **Giữ nguyên nhân dependency failure** để sửa AS/network/configuration.
3. Retry bounded cho transient failures, không retry vô hạn.
4. Timeout rõ ràng để tránh giữ servlet threads lâu.
5. Circuit breaker và backoff khi AS đang quá tải.
6. Caching có giới hạn, không dùng stale allow-decision vô thời hạn.
7. Không vô hiệu hóa TLS verification để “làm introspection chạy”.
8. Không tải introspection endpoint tùy ý từ token không đáng tin.

## 7. Ma trận chuẩn: phân biệt kết quả ở hop B

| Kết quả từ AS | Loại kết quả | Hành động Resource Server | Hướng xử lý hop A |
|---|---|---|---|
| **200 + active=true**, metadata đúng | Thành công | Tạo authenticated principal, kiểm tra quyền | Tiếp tục endpoint hoặc 403 nếu thiếu quyền |
| **200 + active=false** | TOKEN_INACTIVE | Không xác thực token | Thường 401, invalid_token |
| **200 + active=true**, sai audience | TOKEN_CONTRACT_INVALID | Không nhận token cho API | Thường 401 |
| **200 + active=true**, thiếu scope | AUTHORIZATION_DENIED | Authenticated nhưng quyền không đủ | Thường 403 |
| **401 invalid_client** | RS_INTROSPECTION_AUTH_FAILURE | Không có kết luận về token, fail closed | Server/dependency failure; không gắn nhãn token invalid |
| **403 forbidden ở AS** | RS_INTROSPECTION_ACCESS_DENIED | Không có kết luận về token | Server/dependency failure |
| **400 invalid_request** | INTROSPECTION_PROTOCOL_ERROR | Sửa request/config, fail closed | Lỗi server/dependency phù hợp |
| **429** | INTROSPECTION_RATE_LIMIT | Backoff/limit, fail closed | Thường lỗi dependency như 503 |
| **5xx** | INTROSPECTION_AS_UNAVAILABLE | Retry bounded, fail closed | Thường 503 hoặc mã server phù hợp |
| **DNS/TLS/timeout** | INTROSPECTION_TRANSPORT_ERROR | Fail closed, alert | Thường lỗi dependency |
| **200 nhưng malformed JSON** | INTROSPECTION_INVALID_RESPONSE | Fail closed, điều tra protocol | Lỗi dependency/protocol |

**“Thường” ở đây là hướng thiết kế**, không phải cam kết Spring Security mặc định luôn trả đúng status đó trong mọi phiên bản. Cách framework ánh xạ exception ra HTTP còn phụ thuộc introspector, provider, authentication entry point và cấu hình ứng dụng.

## 8. 401 ở hop A và 401 ở hop B là hai khái niệm khác nhau

~~~text
Hop A:
  Client --Bearer opaque token--> Orders API
  API trả 401:
    Caller credential bị từ chối (hoặc error mapping chưa chuẩn).

Hop B:
  Orders API --RS client credentials--> Authorization Server
  AS trả 401:
    RS không được chấp nhận để gọi introspection.
    Không tự nói gì chắc chắn về opaque token của caller.
~~~

Cũng như vậy:

~~~text
403 ở hop A:
  Caller đã xác thực nhưng không được phép thực hiện action.

403 ở hop B:
  RS client chưa được phép introspect theo policy của AS.
~~~

Một lỗi vận hành phổ biến: RS dùng secret cũ nên AS trả 401, framework hoặc handler chuyển thành 401 cho caller. Frontend tưởng token hết hạn rồi gọi refresh token liên tục, nhưng **refresh không thể sửa secret ở backend**.

Phải quan sát status ở **cả hai hop**, không dùng chỉ một metric **http.response.status=401** rồi kết luận “nhiều token đã hết hạn”.

## 9. Trong Spring Security, introspection nằm ở đâu?

Chuỗi xử lý Servlet thường có dạng:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter

    C->>F: Authorization: Bearer opaque-token
    F->>M: BearerTokenAuthenticationToken
    M->>P: authenticate(token)
    P->>I: introspect(raw token)
    I->>AS: POST /introspect + RS credentials
    alt 200 active=true
      AS-->>I: trusted attributes
      I-->>P: OAuth2AuthenticatedPrincipal
      P-->>M: BearerTokenAuthentication
      M-->>F: Authenticated result
      F->>A: Continue, evaluate authority
    else 200 active=false
      AS-->>I: inactive
      I-->>P: Token rejected
    else 401/403/5xx/network
      AS-->>I: Failure or no response
      I-->>P: Introspection error; no authenticated principal
    end
~~~

Các lớp quan trọng:

| Thành phần | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Trích xuất Bearer credential của caller |
| **BearerTokenAuthenticationToken** | Authentication request chưa xác thực, mang raw token |
| **OpaqueTokenAuthenticationProvider** | Gọi introspector để xác thực opaque token |
| **OpaqueTokenIntrospector** | Introspect token và trả OAuth2AuthenticatedPrincipal khi thành công |
| **OAuth2AuthenticatedPrincipal** | Principal/attributes đáng tin từ introspection |
| **BearerTokenAuthentication** | Kết quả Authentication sau khi introspection thành công |
| **SecurityContextHolder** | Lưu context của request cho authorization |
| **AuthorizationFilter** | Kiểm tra quyền endpoint |
| **BearerTokenAuthenticationEntryPoint** | Xử lý authentication challenge |
| **BearerTokenAccessDeniedHandler** | Xử lý thiếu quyền đối với Bearer authentication |

**Không viết filter JWT song song** để “dự phòng” khi opaque introspection lỗi. Một filter tự decode opaque token không thể mặc nhiên xác minh token mà AS định nghĩa là opaque.

### Exception trong Spring Security không tự chứa mọi upstream status

Các loại exception có thể gặp theo phiên bản như:

- **BadOpaqueTokenException**: liên quan token không được chấp nhận ở introspection.
- **OAuth2IntrospectionException**: lỗi xảy ra trong quá trình introspection, không nhất thiết đồng nghĩa token inactive.

Tùy implementation và Spring Security version, lỗi HTTP 401/403, JSON malformed hoặc network có thể được bọc thành exception với cause khác nhau. **Không phân loại chính xác AS outage bằng cách so khớp chuỗi message**, vì message có thể thay đổi hoặc chứa thông tin nhạy cảm.

Muốn phân biệt upstream 401, 403, 429, 5xx, timeout hoặc TLS, cần lấy status/cause **ở HTTP client hoặc protocol-aware adapter của introspector** trước khi mất thông tin.

## 10. Cấu hình Spring Boot cho opaque token

Một ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
~~~

Trong deployment, thay placeholder bằng secret được cung cấp qua **environment variable/secret manager**, không commit client secret vào repository hay cấu hình công khai.

Ví dụ SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Ý nghĩa:**

1. Endpoint **/api/** dùng Spring Security opaque-token Resource Server.
2. RS gọi introspection endpoint theo cấu hình và credentials được cung cấp.
3. Khi AS nói **active=true** và response đáp ứng hợp đồng, RS tạo authenticated principal.
4. Những scope được trả từ AS có thể trở thành authority **SCOPE_...** theo converter mặc định phù hợp.
5. Cấu hình chỉ mang tính ví dụ; cần thêm các quy tắc resource binding, principal type và domain authorization theo hợp đồng AS.

**Introspection URI phải thuộc AS đáng tin.** Không mặc định mọi issuer dùng suffix **/oauth2/introspect**, không lấy URL introspection từ request Bearer token.

### Hai loại secret cần bảo vệ

- Raw opaque access token trong HTTP Authorization header: là **Bearer credential của caller**, không log.
- Introspection client secret: là **credential của Resource Server đối với AS**, không log.

Đừng đưa cả hai vào stack trace, HTTP 500 body, metrics labels, tracing spans hoặc file config được công bố.

## 11. Cách phân loại exception mà không giấu lỗi hạ tầng

Một mô hình ứng dụng có thể định nghĩa outcome nội bộ:

~~~text
ACTIVE(principal)
INACTIVE
RS_CREDENTIALS_REJECTED
RS_NOT_ALLOWED_TO_INTROSPECT
BAD_INTROSPECTION_REQUEST
INTROSPECTION_THROTTLED
AS_UNAVAILABLE
NETWORK_TIMEOUT
TLS_FAILURE
MALFORMED_RESPONSE
~~~

Đây là **outcome model đề xuất**, không phải enum chuẩn của Spring Security. Nó giúp observability và API response mapping.

Có thể trang bị một **OpaqueTokenIntrospector decorator** để ghi kết quả chung:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ObservedOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final IntrospectionMetrics metrics;

    public ObservedOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            IntrospectionMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        try {
            OAuth2AuthenticatedPrincipal principal =
                    delegate.introspect(token);
            metrics.record("active");
            return principal;
        }
        catch (BadOpaqueTokenException ex) {
            metrics.record("inactive");
            throw ex;
        }
        catch (OAuth2IntrospectionException ex) {
            metrics.record("introspection_failure");
            throw ex;
        }
    }
}
~~~

Ở ví dụ này:

- **IntrospectionMetrics** là service do ứng dụng tự định nghĩa.
- **delegate** là introspector phù hợp do Spring Security hoặc ứng dụng cung cấp; snippet chỉ minh họa decorator, không phải bean wiring đầy đủ.
- **BadOpaqueTokenException** được bắt trước exception introspection tổng quát.
- Exception được **rethrow**, không đổi tất cả thành lỗi invalid token.
- Không log argument **token**.
- Cấu trúc hierarchy/exception subtype và lỗi được bọc phụ thuộc version và implementation.

**Giới hạn quan trọng:** Decorator này chỉ tách token-inactive ở mức exception có sẵn với introspection error chung. Muốn phân loại **401 vs 403 vs 5xx vs timeout/TLS**, cần HTTP-aware adapter hoặc instrumentation trong client thực sự gọi AS. Đừng tự suy luận status upstream từ **ex.getMessage()**.

## 12. Điều khiển response hop A: 401, 403, 500 hay 503?

Khi AS trả **active=false**, API thường phải từ chối Bearer credential. Một response phù hợp có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Khi token đã xác thực nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Khi introspection credentials bị AS từ chối hoặc AS outage, API cần thể hiện **server dependency failure**, có thể chọn:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "error": "authentication_dependency_unavailable"
}
~~~

**503 là ví dụ về API error contract được thiết kế**, không phải yêu cầu bắt buộc của RFC 7662 hay hành vi mặc định được bảo đảm bởi mọi Spring Security version.

Có thể chọn 500 cho lỗi cấu hình nghiêm trọng như introspection secret sai; có thể chọn 503 cho timeout/outage. Điều quan trọng là **không tuyên bố access token invalid khi chưa có một kết luận token-state đáng tin**.

### Vì sao @ControllerAdvice có thể không bắt lỗi?

**BearerTokenAuthenticationFilter** chạy trong Servlet filter chain, trước controller. Exception từ introspector/provider có thể được xử lý qua Spring Security authentication failure handler/entry point hoặc đường lỗi của filter chain, **không nhất thiết đi tới @ExceptionHandler trong MVC**.

Nếu muốn phân biệt token-invalid với upstream outage trong response:

1. Lấy kết quả phân loại từ HTTP client/introspection adapter.
2. Giữ failure reason qua Spring Security authentication boundary.
3. Định nghĩa failure/entry-point/exception handler phù hợp với filter chain và framework version.
4. Bảo đảm mọi failure đều không tạo authenticated principal.
5. Không leak endpoint Basic challenge hoặc thông tin client secret từ AS sang caller.
6. Kiểm thử end-to-end status thực tế, không đoán chỉ từ cấu hình property.

**Không forward nguyên** upstream:

~~~http
WWW-Authenticate: Basic realm="introspection"
~~~

tới caller của **orders-api**. Caller của API sử dụng Bearer token, không phải RS introspection credentials.

## 13. Retry: không phải lỗi nào cũng có thể thử lại

| Tình huống ở hop B | Retry có hợp lý? | Lý do |
|---|---|---|
| **200 active=false** | **Không** | AS đã cho kết luận token không active |
| **401 invalid_client** | **Không với cùng credentials** | Cần sửa client ID/secret/method |
| **403 denied** | Không retry mù | Cần sửa permission của RS client |
| **400 invalid_request** | Không retry request sai | Cần sửa endpoint/body/encoding |
| **429 throttled** | Có thể, với backoff/rate limit | Tránh làm AS quá tải |
| **502/503/504** | Có thể bounded retry | Lỗi transient |
| **Connect/read timeout** | Có thể bounded retry | Cần deadline và circuit breaker |
| **TLS validation error** | Không tắt TLS để retry | Cần sửa certificate/truststore |
| **Malformed HTTP 200 JSON** | Chỉ retry theo policy hạn chế | Có thể là lỗi protocol cố định |

Retry đúng cần:

- Số lần thử nhỏ, không vòng lặp vô hạn.
- Tổng deadline phù hợp latency budget của API.
- Exponential backoff với jitter.
- Respect **Retry-After** khi có và phù hợp.
- Rate limiting/circuit breaker để ngăn retry storm.
- Phân biệt timeout do AS và timeout do gateway.
- Không làm AS phải xử lý hàng nghìn introspection requests lặp từ cùng request user.

Một backend dùng synchronous introspection có thể bị cạn Servlet threads nếu chờ upstream lâu và retry vô hạn. Bảo vệ availability của RS là một phần thiết kế.

## 14. Cache introspection: kết quả cũ và lỗi phụ thuộc

Vì introspection có thể tốn network call, Resource Server có thể cache kết quả. Nhưng cache phải tôn trọng token state và thời hạn.

### 14.1. Cache active=true

~~~text
T0: AS trả active=true, scope=orders.read.
T1: RS cache trong 30 giây.
T2: AS revoke token.
T3: RS tiếp tục thấy cached active=true cho đến khi cache hết hạn,
    nếu không có invalidation.
~~~

Vì thế **cache active=true làm tăng cửa sổ thu hồi token**. Cần có TTL ngắn, không vượt quá token expiration và phù hợp SLA revocation.

### 14.2. Cache active=false

Có thể negative-cache kết quả token không active theo chính sách, nhưng phải tránh attacker dùng token rác gây cache flood. Không biến lỗi transport thành active=false rồi cache nó.

### 14.3. Không cache timeout hay upstream 401 như token inactive

~~~text
AS response: 401 invalid_client
    != cache(token, active=false)

AS request: timeout
    != cache(token, active=false)
~~~

Nếu RS khắc phục secret hoặc mạng, token thực tế còn active phải có khả năng được introspect lại. Cache lỗi cấu hình như kết quả token sẽ gây tiếp tục từ chối sai sau khi hạ tầng đã sửa.

### 14.4. Fail closed và stale cached allow

Nếu AS unavailable, một ứng dụng có thể muốn dùng cached positive introspection result để giảm outage. Chỉ được làm thế nếu **trust/revocation policy cho phép**, kết quả cache còn nằm trong giới hạn tuổi, token chưa hết hạn và có ràng buộc tài nguyên đúng.

Không tự bật kiểu:

~~~text
if introspection fails:
    accept any opaque token
~~~

Đó là **fail open** và có thể cho token giả truy cập API.

## 15. TLS, secret rotation và lỗi sai realm

### TLS/hostname mismatch

Ví dụ RS gọi:

~~~text
https://auth-internal.example.local/introspect
~~~

nhưng chứng thư endpoint chỉ hợp lệ cho:

~~~text
auth.example.com
~~~

Kết nối TLS có thể thất bại trước khi có HTTP response. Đây là **TLS/trust failure**, không phải token inactive. Cách sửa là chứng thư, hostname, DNS hoặc truststore, **không tắt hostname verification**.

### Secret rotation không đồng bộ

~~~text
AS đã thay introspection client secret từ V1 sang V2.

RS instance 1: sử dụng V2 -> AS 200
RS instance 2: sử dụng V1 -> AS 401

Cùng một opaque token:
  request qua instance 1 thành công;
  request qua instance 2 lỗi.
~~~

Đây là **configuration drift**, không phải token ngẫu nhiên hết hạn. Giám sát nên có RS instance ID và **secret version alias không nhạy cảm**, không bao giờ ghi secret thật vào log.

### Sai realm hoặc AS endpoint

Một Authorization Server có nhiều realm/tenant có thể có credentials và endpoint introspection riêng. Gọi token của realm A vào endpoint của realm B có thể trả **active=false** hoặc 401/403 tùy provider.

Cần cấu hình trust domain, endpoint và credentials theo hợp đồng. Không cho opaque token tự khai URL để RS gọi một AS bất kỳ. Opaque string không có cấu trúc JWT bắt buộc để tự đọc issuer.

## 16. Multi-issuer opaque token và lựa chọn endpoint

Nếu API tin nhiều Authorization Servers, cần routing introspection theo ngữ cảnh đáng tin:

~~~text
/tenant-a/api/** -> Introspection endpoint A + client credentials A
/tenant-b/api/** -> Introspection endpoint B + client credentials B
~~~

Hoặc một **AuthenticationManagerResolver**/mô hình multi-tenant tương ứng nếu kiến trúc Spring Security hỗ trợ.

Không nên:

~~~text
read opaque token prefix
    -> tạo URL bất kỳ từ request
    -> gửi token đến URL đó
    -> tin response
~~~

trừ khi prefix và endpoint binding thuộc một giao thức token đã được AS định nghĩa, giới hạn bằng allow-list và không thể bị dùng cho SSRF.

Nếu hai endpoints dùng chung token string trùng nhau theo ngẫu nhiên, cache cần phân tách theo endpoint/trust domain, không gom mọi introspection results thành một namespace duy nhất.

## 17. Authentication khác authorization: active=true vẫn có thể 403

Ví dụ AS trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910003600
}
~~~

Endpoint POST cần:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Khi đó:

~~~text
Token state:
  active=true

Authentication:
  thành công nếu toàn bộ token acceptance contract đạt

Authorization:
  token thiếu SCOPE_orders.write
  => từ chối, thường 403
~~~

Tương tự, token active và có write vẫn có thể bị từ chối vì user không còn tenant membership, order thuộc owner khác hoặc order đã bị khóa. Domain authorization nằm **sau** token introspection, không phải kết quả **active=false**.

### Scope không đồng nghĩa mọi role và permission

Một introspection response có **scope=orders.write** thường nói token đã được AS cấp phạm vi write. Nhưng API vẫn cần kiểm tra object-level authorization và các quyền hiện hành nếu policy yêu cầu. Không lấy **roles**, **groups** hoặc **sub** từ response để tự cấp quản trị domain nếu chưa định nghĩa mapping/trust contract.

## 18. Observability: theo dõi lỗi ở đúng hop

Các metric dimensions nên là những giá trị kiểm soát cardinality:

| Trường | Ví dụ | Cần lưu ý |
|---|---|---|
| introspection.endpoint_id | shop-as-primary | ID cấu hình tin cậy, không phải URL do token nhập |
| introspection.outcome | inactive | active/inactive/upstream_auth/network/... |
| introspection.upstream_status | 200, 401, 503, none | Status của hop B |
| api.response_status | 401, 403, 503 | Status của hop A |
| introspection.latency | histogram | Xác định timeout/saturation |
| rs.instance | api-pod-3 | Phát hiện config drift |
| error_category | client_auth, network, protocol | Không chứa secret |
| secret.version_alias | auth-secret-v2 | Chỉ alias, không có secret value |

Không đưa raw Bearer token, Basic Authorization header, request form token, client secret, PII hoặc HTTP response chứa thông tin nhạy cảm vào logs/traces.

### Những cảnh báo hữu ích

- **Upstream 401 rate tăng sau deploy:** có thể client ID/secret, mTLS hoặc sai auth method.
- **Upstream 403 rate tăng:** có thể thiếu quyền introspect.
- **Timeout/503 tăng đồng loạt:** có thể AS outage, gateway saturation.
- **TLS errors tăng sau certificate rotation:** kiểm tra truststore/hostname.
- **active=false tăng** nhưng upstream 200 ổn định: có thể token thật sự không active hoặc client gửi token sai.
- **Một replica lỗi trong khi replica khác ổn:** kiểm tra secret/config drift.

Chỉ theo dõi tổng số client-facing 401 **không đủ** để phân loại nguyên nhân.

## 19. Sơ đồ state machine phân lớp lỗi

~~~mermaid
flowchart TD
    A["Client gửi Bearer opaque token"] --> B{"Bearer request hợp lệ?"}
    B -- "Không" --> R["Bearer request failure"]
    B -- "Có" --> C["POST trusted introspection endpoint"]
    C --> D{"Có HTTP response?"}
    D -- "Không: network/TLS/timeout" --> INF["Dependency failure, fail closed"]
    D -- "Có" --> E{"HTTP status?"}
    E -- "401/403" --> AUTH["RS introspection client auth/access failure"]
    E -- "429/5xx" --> INF
    E -- "400" --> PROT["Bad introspection request"]
    E -- "200" --> F{"JSON active boolean?"}
    F -- "false" --> INV["Token inactive; reject credential"]
    F -- "true" --> G["Validate audience/resource metadata"]
    F -- "Missing/invalid" --> PROT
    G --> H{"Token contract met?"}
    H -- "Không" --> INV
    H -- "Có" --> I["Authenticated principal"]
    I --> J{"Enough scope/domain authority?"}
    J -- "Không" --> DENY["Authorization denied"]
    J -- "Có" --> OK["Allow operation"]
    AUTH --> ERR["Server dependency/configuration error"]
    PROT --> ERR
~~~

Mô hình này tránh hai anti-pattern:

- **Fail open:** không introspect được nhưng vẫn tin token.
- **Misclassification:** không introspect được nhưng nói access token của caller đã bị AS từ chối.

Cả hai đều đáng tránh trong Resource Server.

## 20. Ma trận kiểm thử cho từng trạng thái introspection

Các kịch bản dưới đây là **kỳ vọng thiết kế**, không phải kết quả test đã chạy.

| Stub AS hoặc điều kiện mạng | Phân loại mong đợi | Tính bảo mật |
|---|---|---|
| 200 + active=true + đủ scope/audience | ACTIVE | Tạo principal rồi authorize |
| 200 + active=false | TOKEN_INACTIVE | Không tạo principal; thường 401 |
| 200 + active=true nhưng thiếu scope | AUTHORIZATION_DENIED | Thường 403 |
| 200 + active=true nhưng sai audience | TOKEN_CONTRACT_FAILURE | Từ chối token |
| 401 + invalid_client | UPSTREAM_AUTH_FAILURE | Không coi token inactive |
| 403 + forbidden | UPSTREAM_ACCESS_DENIED | Không coi token inactive |
| 400 + invalid_request | INTROSPECTION_REQUEST_ERROR | Sửa request, không retry mù |
| 429 | THROTTLED | Backoff/circuit breaker, fail closed |
| 500/502/503/504 | UPSTREAM_UNAVAILABLE | Fail closed, dependency response |
| DNS failure | NETWORK_ERROR | Fail closed |
| Connect timeout | TIMEOUT | Fail closed, deadline |
| Read timeout | TIMEOUT | Fail closed, bounded retry |
| TLS hostname mismatch | TLS_ERROR | Không bỏ TLS check |
| 200 + active="true" | PROTOCOL_ERROR | Không coi string là boolean |
| 200 + thiếu active | PROTOCOL_ERROR | Không mặc định active |
| 200 + HTML login page | WRONG_ENDPOINT/PROTOCOL_ERROR | Không tạo principal |
| RS secret V1/V2 khác giữa hai pods | CONFIG_DRIFT | Ghi lỗi theo instance |
| Cache active=true stale sau revoke | CACHE_FRESHNESS | Theo TTL/revocation policy |
| Timeout bị cache thành active=false | INVALID_ERROR_CACHING | Không đánh đồng dependency failure và token failure |

Các tầng test nên tách:

1. **Introspection HTTP client contract:** giả lập status/JSON/network/TLS.
2. **Resource Server integration:** request đi qua BearerTokenAuthenticationFilter, OpaqueTokenAuthenticationProvider và introspector thực/giả lập.
3. **Authorization test:** active principal có đủ scope hay đúng quyền trên resource không.

Một test chỉ mock sẵn authenticated principal **không chứng minh** upstream credentials và network error handling của hệ thống đã được kiểm tra.

## 21. Khi hàng loạt người dùng đồng thời thấy invalid_token

Một sự cố mẫu:

~~~text
10:00 Hệ thống vận hành bình thường.
10:05 AS rotate introspection client secret.
10:06 RS chưa nhận secret mới.
10:07 500 users báo API trả 401.
10:08 Frontend tự refresh token, vẫn 401.
~~~

Chẩn đoán theo thứ tự:

1. **AS có trả HTTP 200 + active=false không?** Nếu không, đừng vội nói token sai.
2. **Upstream có trả 401 invalid_client không?** Kiểm tra introspection secret và method.
3. **Lỗi có xảy ra đồng loạt hoặc chỉ trên một RS replica không?** Kiểm tra config drift.
4. **Introspection client đã bị disable hoặc mất quyền chưa?**
5. **Endpoint có đúng realm/tenant không?**
6. **Reverse proxy có giữ HTTP Authorization và mTLS policy đúng không?**
7. **Có TLS/DNS/timeout/5xx thay vì AS authentication failure không?**
8. **Framework đang map introspection failure ra client-facing 401 như thế nào?**
9. **Sau khi sửa secret, token cũ chưa hết hạn có được introspect active không?**
10. **Có cache lỗi cũ cần invalidation không?**

Không bắt người dùng đăng xuất hàng loạt để chữa **credential của Resource Server đã hết hạn**.

## 22. Checklist triển khai error contract an toàn

Với một protected opaque-token endpoint, hãy xác định:

1. Hop A Bearer token có đúng cú pháp không?
2. Introspection endpoint có thuộc AS tin cậy và cấu hình tĩnh/allow-list không?
3. RS dùng credentials/method có quyền introspect không?
4. AS có trả response hợp lệ chứa **active** boolean không?
5. Nếu **active=false**, có từ chối credential nhưng không tiết lộ nguyên nhân nhạy cảm không?
6. Nếu HTTP 401/403 upstream, có alert configuration/IAM thay vì đổi thành token invalid không?
7. Nếu HTTP 429/5xx, có bounded retry và failure mapping phù hợp không?
8. Nếu timeout/TLS/DNS, có fail closed và giữ được nguyên nhân hạ tầng không?
9. Nếu **active=true**, có kiểm tra resource binding, scope và domain permission không?
10. Có tách upstream status khỏi client-facing status trong metrics không?
11. Có cache policy phù hợp token expiration và revocation SLA không?
12. Nếu dependency unavailable, hành vi response có được thiết kế/test rõ không?
13. Có bảo vệ raw access tokens, Basic credentials, client secrets khỏi log và error body không?
14. Secret rotation/AS availability có owner và alert rõ ràng không?
15. Không có custom Bearer filter khác đang âm thầm ghi đè Authentication đúng không?

## 23. Những sai lầm phổ biến

| Sai lầm | Nguy cơ | Cách làm đúng |
|---|---|---|
| Catch mọi exception rồi throw invalid_token | Che AS outage và config errors | Phân loại theo protocol/transport |
| Hop B trả 401 thì hop A luôn 401 | Đổ lỗi client khi RS secret sai | Tách hai HTTP hops |
| AS timeout thì mặc định active=true | **Bypass authentication** | Fail closed |
| Retry 401 invalid_client vô hạn | Không sửa credentials, tăng tải AS | Sửa IAM/secret/method |
| Retry 200 active=false đến khi active=true | Vô hiệu semantics AS | Từ chối credential |
| Bỏ TLS verification để “fix” lỗi | Mất trust với AS | Sửa trust/cert/hostname |
| Dùng public OAuth client làm introspection client | Không có confidential credentials thích hợp | Cấp RS client với quyền introspect |
| 200 active=true là đủ cho mọi API | Token có thể sai audience/scope | Kiểm tra token/resource contract |
| Cache timeout thành token inactive | Sau khi AS khôi phục vẫn từ chối sai | Không cache dependency failure như token state |
| Cache active=true không giới hạn | Token bị revoke vẫn dùng được | TTL và invalidation phù hợp |
| Ghi raw token và Basic header vào logs | Lộ Bearer token và RS secret | Sanitized observability |
| Chỉ dùng @ControllerAdvice xử lý filter errors | Exception có thể phát trước MVC | Xử lý đúng Security filter boundary |
| Tự parse opaque token như JWT | Token không theo cấu trúc JWT | Dùng introspection |
| Để opaque token tự chọn introspection URL | SSRF/trust confusion | Endpoint allow-list |
| Xem upstream 403 như caller thiếu scope | Nhầm thiếu quyền RS introspection với domain auth | Phân loại đúng hop |

## 24. Kết luận và tài liệu tham khảo

Ba trường hợp khác nhau cần ghi nhớ:

~~~text
(A) AS trả HTTP 200 + {"active":false}
    -> Token không active.
    -> Caller credential không được chấp nhận.

(B) AS trả HTTP 401/403 cho POST introspection
    -> RS có vấn đề với client credentials hoặc quyền introspect.
    -> Chưa có kết luận token active hay không.

(C) AS không thể trả response đáng tin (network/TLS/5xx/malformed)
    -> Lỗi dependency/protocol.
    -> Chưa có kết luận token active hay không.
~~~

Một opaque-token Resource Server an toàn phải **fail closed** trong cả ba trường hợp nếu chưa chứng minh được token hợp lệ, đồng thời **giữ nguyên nhân lỗi** để trả response chính xác và sửa đúng thành phần.

**Những nguyên tắc cuối cùng:**

- **active=false từ một introspection response hợp lệ là kết luận token-state.**
- **HTTP 401/403 từ AS là lỗi credential/permission của RS với introspection, không tự nói token caller sai.**
- **Timeout, TLS, DNS, 429, 5xx và JSON malformed là lỗi phụ thuộc/protocol, không phải active=false.**
- **Resource Server không được fail open**, cũng không nên đánh đồng mọi sự cố thành invalid_token.
- **Muốn trả 503 khi AS outage cần error translation đúng ranh giới Security filter**, không giả định mặc định.
- **Scope và quyền nghiệp vụ được kiểm tra sau khi token active**, không dùng active=true làm giấy phép truy cập.
- **Retries, cache và secret rotation phải có giới hạn và chính sách**, không làm giảm ranh giới tin cậy.
- **Quan sát hai HTTP hop riêng biệt**, bảo vệ token và credentials khỏi logs.

### Tài liệu nền tảng

- **RFC 7662 — OAuth 2.0 Token Introspection:** introspection request/response, active boolean và authentication tới endpoint. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách trình bày access token và Bearer error semantics. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client authentication, access token và OAuth errors. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7009 — OAuth 2.0 Token Revocation:** token revocation và vòng đời token. https://www.rfc-editor.org/rfc/rfc7009
- **Spring Security Reference — Opaque Token Resource Server (Servlet):** cấu hình introspection và opaque token authentication. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Resource Server:** filter/provider và xử lý Bearer authentication. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security API — OpaqueTokenIntrospector:** hợp đồng introspection token. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html
- **Spring Security API — BadOpaqueTokenException:** lỗi token không được chấp nhận. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html
- **Spring Security API — OAuth2IntrospectionException:** lỗi introspection tổng quát. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OAuth2IntrospectionException.html
