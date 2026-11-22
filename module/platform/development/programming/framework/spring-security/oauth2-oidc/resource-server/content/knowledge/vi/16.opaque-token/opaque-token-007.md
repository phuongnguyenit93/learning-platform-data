# Thuộc tính active và xử lý token không còn hiệu lực

Khi **Spring Security OAuth 2.0 Resource Server** nhận **opaque Bearer Access Token**, nó thường không thể tự kiểm tra chữ ký, thời hạn hoặc các quyền bằng cách đọc chuỗi token. Resource Server gửi token đến **token introspection endpoint** của Authorization Server để hỏi trạng thái và metadata. Theo **RFC 7662**, phản hồi introspection có trường **`active`** dạng boolean.

Đây là ranh giới quan trọng: **`active: false` buộc Resource Server từ chối token**, trong khi **`active: true` mới chỉ cho phép tiếp tục kiểm tra quyền và điều kiện của API**. Nếu introspection endpoint lỗi, timeout hoặc trả JSON sai cấu trúc, hệ thống **không được tự suy token vẫn active**.

Bài học giải thích chi tiết ý nghĩa `active`, những nguyên nhân token trở thành inactive, cơ chế Spring Security `OpaqueTokenIntrospector`, cách xử lý 401/403, lỗi hạ tầng, cache và revocation, cùng các ví dụ cấu hình và kiểm thử. Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+** với Servlet Resource Server nhận OAuth 2.0 Access Token.

## 1. Vì sao opaque token cần introspection?

OAuth 2.0 Access Token là credential mà client dùng để gọi một Resource Server. Authorization Server có thể phát hành JWT Access Token hoặc opaque Access Token.

| Tiêu chí | JWT được xác minh cục bộ | Opaque token |
| --- | --- | --- |
| Định dạng mà API dựa vào | JOSE header, JWT claims, chữ ký. | API không dựa vào cấu trúc chuỗi token. |
| Nơi kiểm tra hợp lệ | `JwtDecoder` và JWK public keys. | `OpaqueTokenIntrospector` và Authorization Server. |
| Xác định quyền | JWT claims đã được kiểm chứng. | Metadata introspection đã được tin cậy. |
| Thu hồi trước khi hết hạn | Cần cơ chế bổ sung như denylist hoặc token ngắn hạn. | Introspection có thể phản ánh trạng thái thu hồi. |
| Phụ thuộc network mỗi lần xác thực | Thường không, sau khi có khóa thích hợp. | Thường có, trừ khi sử dụng cache theo chính sách. |
| `active` | Không phải claim JWT chuẩn bắt buộc. | Trường cốt lõi trong phản hồi RFC 7662. |

Một opaque token có thể trông như:

~~~text
v2_at_R7FkS_xxxxxx
~~~

Đó chỉ là **chuỗi minh họa**, không phải token sử dụng thật. Resource Server **không** được lấy tên người dùng từ tiền tố, giải mã Base64 để suy ra scope, hoặc xem token hợp lệ vì nó đúng độ dài. Opaque mô tả cách Resource Server sử dụng token; không nhất thiết khẳng định Authorization Server lưu token theo một cấu trúc nội bộ nhất định. Một Authorization Server thậm chí có thể hỗ trợ introspect JWT.

Request từ client:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer OPAQUE_ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Token trong header là **Bearer credential**: ai giữ nó có thể thử sử dụng những quyền được cấp, trừ khi có cơ chế sender constraint. Không đưa token vào URL, log, exception hoặc tài liệu công khai.

## 2. RFC 7662 định nghĩa active như thế nào?

**RFC 7662 — OAuth 2.0 Token Introspection** cho phép một Resource Server truy vấn Authorization Server để biết token có **đang hoạt động** và nhận metadata có thể công bố cho bên introspect hay không.

Luồng tổng quát:

~~~text
Client
  |
  | Authorization: Bearer <opaque token>
  v
Resource Server (Spring Security)
  |
  | POST /oauth2/introspect
  | token=<opaque token>
  | Xác thực chính Resource Server với Authorization Server
  v
Authorization Server
  |
  +-- Nhận diện token / grant / trạng thái
  +-- Kiểm tra expiration và revocation theo chính sách
  +-- Kiểm tra quyền introspect của Resource Server
  |
  +-- {"active":false} -> Không chấp nhận credential
  |
  +-- {"active":true,...} -> Metadata được phép công bố
  v
Resource Server
  |
  +-- Xác định principal và authorities
  +-- Kiểm tra audience/resource, scope và domain policy
  v
API controller / service
~~~

### 2.1. Gửi POST introspection

Ví dụ HTTP request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_RESOURCE_SERVER_CREDENTIALS
Accept: application/json

token=OPAQUE_ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

Hai loại credential có chức năng khác nhau:

- **Access Token** là token của client gửi cho API, được đặt trong form parameter `token` khi Resource Server introspect.
- **Client credential của Resource Server** chứng minh bên gọi introspection endpoint có quyền truy vấn. Ví dụ dùng HTTP Basic; Authorization Server có thể yêu cầu mTLS hoặc phương thức khác.

`token_type_hint=access_token` là gợi ý tùy chọn để server tìm token hiệu quả, **không phải bằng chứng xác thực**. Introspection phải thực hiện qua **HTTPS** có xác minh chứng chỉ và hostname; không log body chứa token hay Basic credentials.

### 2.2. Phản hồi active=true

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "orders-web-client",
  "token_type": "Bearer",
  "sub": "person-123",
  "iss": "https://login.example.test/realms/demo",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

`active: true` biểu thị Authorization Server xem token active trong ngữ cảnh introspection. Những trường khác như `scope`, `sub`, `iss`, `aud`, `exp`, `client_id` tùy vào token và contract của Authorization Server; không giả định mọi server đều trả đủ.

Ngay cả khi `active:true`, API vẫn phải kiểm tra:

- Token có được cấp cho **resource/audience đúng API** không?
- Có đúng scope/authority cho endpoint không?
- Có đáp ứng policy về token type, issuer/client và các claims bắt buộc không?
- Nếu nghiệp vụ gắn user, local account còn hoạt động và được phép thao tác không?
- Caller có quyền trên bản ghi/tenant đang yêu cầu không?

**Active là một điều kiện cần trong cơ chế introspection, không phải quyết định toàn bộ authorization.**

### 2.3. Phản hồi active=false

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

**Introspection HTTP 200 không nghĩa là Access Token hợp lệ.** Nó chỉ cho biết server đã xử lý thành công yêu cầu introspection. Thuộc tính `active` quyết định token có được tiếp tục xác thực hay không.

RFC 7662 yêu cầu token không active hoặc bên gọi không được phép introspect token cụ thể phải được biểu diễn bằng `active:false` và không nên trả metadata bổ sung. Việc không tiết lộ lý do giúp giảm khả năng thăm dò token có tồn tại, còn hạn hay đã bị thu hồi.

Resource Server phải dừng authentication khi nhận `active:false`; **không tạo principal giả, không cấp authorities mặc định** và không chuyển sang đọc scope từ dữ liệu token chưa xác minh.

## 3. Kiểu dữ liệu của active: chỉ JSON boolean

`active` là **boolean bắt buộc** trong phản hồi introspection thành công theo RFC 7662.

| JSON trả về | Hợp lệ về kiểu active? | Hành động |
| --- | --- | --- |
| `{"active":true}` | Có. | Có thể tiếp tục kiểm tra metadata và quyền. |
| `{"active":false}` | Có. | **Từ chối token**. |
| `{"active":"true"}` | Không: string. | Không chấp nhận; báo lỗi contract/protocol. |
| `{"active":"false"}` | Không: string. | Không chấp nhận. |
| `{"active":1}` | Không: number. | Không chấp nhận. |
| `{"active":0}` | Không: number. | Không chấp nhận. |
| `{"active":null}` | Không. | Không chấp nhận. |
| `{}` | Không: thiếu trường bắt buộc. | Không chấp nhận. |
| `{"active":[]}` | Không. | Không chấp nhận. |
| Body rỗng/JSON sai cú pháp | Không. | Không chấp nhận, ghi nhận lỗi protocol. |

Nếu tự xử lý JSON, không sử dụng cách ép kiểu mơ hồ:

~~~java
// KHÔNG LÀM: có thể che giấu sai kiểu JSON.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active")));
~~~

Với một `Map<String,Object>` đã parse bằng JSON parser tin cậy, chỉ được diễn giải active đúng khi value thực sự là `Boolean.TRUE`. Nếu value là null, string hoặc number, không coi đó là một introspection response hợp lệ.

Một **`OpaqueTokenIntrospector` chuẩn** sẽ xử lý điều kiện active trong cơ chế xác thực. Nếu triển khai introspector riêng, phải duy trì semantics đó; không tạo principal từ response không có boolean active đúng.

## 4. active=false có thể có nhiều nguyên nhân

Không được mặc định rằng mọi `active:false` đồng nghĩa token đã hết hạn.

### 4.1. Token hết hạn

Ví dụ:

~~~text
10:00  Authorization Server phát hành token
10:05  introspection -> active=true
10:15  token hết hạn theo expiration policy
10:16  introspection -> active=false
~~~

Nếu introspection trả `exp`, giá trị này theo RFC 7662 là thời điểm dạng NumericDate (giây Unix epoch). Không tự diễn giải mili-giây thành giây hoặc nhận chuỗi bất kỳ là expiration hợp lệ nếu contract đòi JSON number.

### 4.2. Token bị thu hồi

Theo **RFC 7009 — Token Revocation**, Authorization Server có thể hỗ trợ thu hồi token:

~~~text
T0: Access Token active
T1: Client hoặc quản trị viên yêu cầu revoke token/grant
T2: Authorization Server ghi nhận revocation
T3: Introspection mới -> active=false
~~~

**T3 không nhất thiết xảy ra ở mọi Resource Server ngay lập tức** nếu có cache kết quả `active:true`, đồng bộ nhiều node hoặc độ trễ cập nhật trạng thái. Việc thu hồi Refresh Token/grant có kéo theo thu hồi Access Token hay không còn phụ thuộc chính sách và triển khai của Authorization Server.

### 4.3. Token không tồn tại hoặc không thuộc server này

Một chuỗi do người dùng tự tạo không được chấp nhận chỉ vì giống định dạng opaque token. Authorization Server có thể trả `active:false` nếu không nhận diện token. Không nên phản hồi chi tiết “không tìm thấy token X” so với “token X đã bị revoke”, vì khác biệt đó có thể thành công cụ dò token.

### 4.4. Token chưa có hiệu lực

Một token có `nbf` trong tương lai hoặc bị chặn bởi điều kiện của grant/session có thể được Authorization Server xem inactive theo policy. Resource Server không tự sửa thời hạn `nbf` để làm token hợp lệ.

### 4.5. Resource Server không được phép introspect token

RFC 7662 cho phép phản hồi `active:false` khi bên gọi **không được quyền biết thông tin token cụ thể**. Vì vậy, một token có thể còn hiệu lực ở ngữ cảnh khác nhưng vẫn bị Resource Server hiện tại từ chối.

Điều này cũng có nghĩa **không thể suy nguyên nhân chính xác từ `active:false`**. Kết luận mà API cần là “không chấp nhận credential này tại đây”.

### 4.6. Trạng thái local account là lớp độc lập

Ví dụ Authorization Server trả `active:true` nhưng tài khoản nội bộ bị khóa:

~~~text
Introspection: active=true
app_user.status: SUSPENDED
Resource permission: denied
~~~

Trong trường hợp đó, token có thể hợp lệ ở OAuth layer nhưng **phải bị từ chối tại domain authorization**. Không coi active=true là bằng chứng user còn quyền trên mọi tenant hoặc mọi đơn hàng.

## 5. HTTP 200 active=false khác lỗi 401/503 của introspection

Cần phân biệt:

1. **Client → Resource Server:** request Bearer có thể được trả 401 nếu token invalid.
2. **Resource Server → Authorization Server:** request introspection có thể được trả 401 nếu credential introspection bị từ chối.
3. **Authorization Server → Resource Server:** HTTP 200 + JSON `active:false` báo trạng thái token không được chấp nhận.

| Phản hồi upstream | Ý nghĩa | Cách Resource Server xử lý |
| --- | --- | --- |
| HTTP 200, `active:true` | Token active. | Tiếp tục kiểm tra metadata/chính sách. |
| HTTP 200, `active:false` | Token không được chấp nhận. | **Authentication thất bại**; endpoint bảo vệ thường 401. |
| HTTP 200, thiếu `active` | Phản hồi sai RFC. | Không chấp nhận token; phân loại protocol error. |
| HTTP 401 tại introspection | Credential của **Resource Server** không hợp lệ, hoặc cơ chế upstream từ chối. | Không xác thực token; điều tra client authentication. |
| HTTP 403 tại introspection | Bên gọi không được phép hoặc policy upstream từ chối. | Không xác thực token; phân loại tích hợp/chính sách. |
| HTTP 429/503/5xx | Upstream quá tải hoặc lỗi. | **Fail closed**, không kết luận token active. |
| Timeout/DNS/TLS failure | Không truy vấn được trạng thái. | Fail closed, xử lý lỗi network; không suy active=false theo nghĩa nghiệp vụ. |

**Không trộn “token inactive” với “introspection service unavailable” trong logging/metrics.** Nếu mọi lỗi đều ghi “expired token”, đội vận hành khó phát hiện client secret bị sai hoặc hệ thống định danh bị outage.

Khi upstream lỗi, HTTP response của Resource Server phụ thuộc framework, handler và hợp đồng API; có thể cân nhắc **503 Service Unavailable** để diễn đạt lỗi phụ thuộc xác thực, nhưng tuyệt đối không biến lỗi thành request authenticated. Không khẳng định mọi lỗi introspection đều phải được chuyển thành 401 hoặc 503 giống nhau.

## 6. Spring Security xử lý opaque token qua những thành phần nào?

Luồng Servlet thường là:

~~~text
Authorization: Bearer <opaque token>
                |
                v
BearerTokenAuthenticationFilter
                |
                v
BearerTokenAuthenticationToken
                |
                v
OpaqueTokenAuthenticationProvider
                |
                v
OpaqueTokenIntrospector.introspect(token)
                |
                +-- active=false -> xác thực thất bại
                |
                +-- response không hợp lệ / upstream lỗi
                |   -> không tạo Authentication thành công
                |
                +-- active=true -> OAuth2AuthenticatedPrincipal
                                     |
                                     v
                              BearerTokenAuthentication
                                     |
                                     v
                              GrantedAuthorities (SCOPE_...)
                                     |
                                     v
                              AuthorizationFilter
                                     |
                                     v
                              Controller / Service policy
~~~

`OpaqueTokenIntrospector` là interface thực hiện introspection và trả **`OAuth2AuthenticatedPrincipal`** khi token hợp lệ. Khi phản hồi là inactive, introspector tiêu chuẩn từ chối token thay vì trả principal.

**Principal của opaque token không nhất thiết là `Jwt`.** Với JWT Resource Server, Authentication thường là `JwtAuthenticationToken`; với opaque, nó thường là `BearerTokenAuthentication` chứa `OAuth2AuthenticatedPrincipal`. Tránh ép `@AuthenticationPrincipal Jwt` trong API chỉ sử dụng opaque introspection.

### 6.1. Scope ánh xạ thành authorities

Nếu response trả:

~~~json
{"active":true,"scope":"orders.read orders.write","sub":"person-123"}
~~~

Spring Security thường xây dựng:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Ví dụ:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

**Active=true không tự cấp scope nào.** Nếu token active mà không có authority cần thiết, request đã xác thực nhưng có thể nhận **403 Forbidden**.

## 7. Cấu hình Spring Boot Opaque Token Resource Server

### 7.1. Dependencies

Ví dụ Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 7.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Các giá trị:

- **`introspection-uri`**: endpoint HTTPS được Authorization Server công bố.
- **`client-id`**: danh tính Resource Server được phép introspect.
- **`client-secret`**: credential để xác thực Resource Server với introspection endpoint, đọc từ environment/secret manager.

Không hardcode client secret thật vào repository hay ví dụ công khai. Nếu Authorization Server dùng mTLS hoặc client authentication khác Basic, cấu hình introspector/HTTP client phù hợp; đừng mặc định mọi endpoint hỗ trợ cùng cơ chế.

### 7.3. SecurityFilterChain

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
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ này chỉ áp dụng chain cho `/api/**`. Một ứng dụng còn web/management endpoints phải có chain khác hoặc fallback tương ứng để tránh path nằm ngoài bảo vệ. `STATELESS` và tắt CSRF thích hợp với API thuần Bearer header; **không dùng nguyên xi cho website OIDC Login xác thực bằng session cookie**.

### 7.4. Lấy OAuth2AuthenticatedPrincipal

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalController {

    @GetMapping("/api/orders/me")
    Map<String, String> current(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("principalName", principal.getName());
    }
}
~~~

Controller chỉ minh họa cách đọc principal, không phải endpoint production nên công bố tùy ý thông tin danh tính. Khi API dùng local user hoặc tenant membership, cần mapping và authorization theo domain; không chỉ trả những attributes thu được từ introspection.

## 8. Từ active=false đến HTTP 401

Một request token bị revoke:

~~~text
Client                       Resource Server             Authorization Server
  |                                 |                            |
  | GET /api/orders/42              |                            |
  | Bearer revoked-token            |                            |
  |-------------------------------->|                            |
  |                                 | POST introspect            |
  |                                 |--------------------------->|
  |                                 |                            |
  |                                 | 200 {"active":false}       |
  |                                 |<---------------------------|
  |                                 |                            |
  | 401 Unauthorized                |                            |
  |<--------------------------------|                            |
~~~

Một phản hồi Resource Server có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Không thể xác thực yêu cầu."}
~~~

Chi tiết trong `WWW-Authenticate` và body có thể thay đổi theo exception handler/Spring Security version; không phải 401 nào cũng có chính xác ví dụ trên. Đừng tiết lộ token, `sub`, nguyên nhân revocation nội bộ hoặc stack trace cho client.

### 8.1. So sánh 401 và 403

| Trạng thái | Authentication | Authorization | HTTP thường dùng |
| --- | --- | --- | --- |
| Không có Bearer token ở endpoint bảo vệ | Thất bại | Không xét | **401** |
| Introspection `active:false` | Thất bại | Không xét | **401** |
| Introspection `active:true`, scope thiếu | Thành công | Thất bại | **403** |
| Introspection active, scope đúng, order thuộc user khác | Thành công | Thất bại | **403/404** theo domain policy |
| Introspection active, đủ điều kiện | Thành công | Thành công | **2xx** tùy controller |
| Introspection timeout/503 | Không xác minh được | Không được cho phép | **Fail closed**, có thể trả 5xx/503 theo API contract |

Với OAuth 2.0 Bearer Token, lỗi 401 liên quan credential; lỗi 403 thường liên quan quyền của caller đã được xác thực. Không dùng `active:false` như cách mô tả mọi lỗi authorization.

## 9. Active=true có thể vẫn không đủ cho API

### 9.1. Audience/resource sai

Introspection có thể trả:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "billing.read",
  "sub": "person-123"
}
~~~

Token active nhưng được cấp cho **billing-api**. **orders-api** không nên chấp nhận token chỉ vì nó active. Cần kiểm tra `aud`, resource indicator, hoặc chính sách introspection/resource binding theo contract của Authorization Server.

Nếu issuer không trả trường cần thiết, **không tự bỏ điều kiện**. Hãy thống nhất metadata, hoặc cơ chế ràng buộc Resource Server tại Authorization Server.

### 9.2. Scope thiếu

~~~json
{"active":true,"sub":"person-123"}
~~~

Nếu API cần `orders.read`, token thiếu scope đó không được tự cấp `SCOPE_orders.read`. Tùy token contract, một token không có scope vẫn có thể hợp lệ nhưng **không đủ quyền**.

### 9.3. Token không phù hợp token profile

OIDC **ID Token** dành cho OIDC Client/Relying Party, không mặc nhiên là OAuth 2.0 Access Token dành cho Resource Server. Một token được phát hành hợp lệ ở hệ thống định danh nhưng dùng sai loại/mục đích vẫn phải bị từ chối theo chính sách token profile.

### 9.4. Local user bị khóa

~~~text
Opaque token: active=true
Local account: SUSPENDED
User muốn xem đơn của tenant khác
~~~

API phải áp **domain authorization** riêng: account status, tenant membership, ownership và hành động được phép. Token active không biến user thành chủ sở hữu mọi bản ghi.

## 10. Custom OpaqueTokenIntrospector: giữ nguyên kiểm tra active

Nếu cần kiểm tra audience hoặc metadata riêng, hướng an toàn là **bọc một introspector chuẩn**, không tự tạo principal từ token string.

### 10.1. Đừng tự cấp quyền khi không introspect

Đoạn sau sai về bảo mật:

~~~java
// KHÔNG LÀM: biến chuỗi bất kỳ thành principal có quyền cao.
@Bean
OpaqueTokenIntrospector insecureIntrospector() {
    return token -> new DefaultOAuth2AuthenticatedPrincipal(
        "unknown",
        Map.of("sub", token),
        List.of(new SimpleGrantedAuthority("SCOPE_admin.manage")));
}
~~~

Nếu được dùng ở production, bất kỳ Bearer token nào cũng có thể được xem là hợp lệ và có quyền quản trị.

### 10.2. Bọc introspector để kiểm tra audience

Ví dụ sau dùng `NimbusOpaqueTokenIntrospector` có trong Spring Security 6.x. API tạo/thiết lập HTTP client có thể thay đổi giữa các minor versions, nên phiên bản dự án phải chọn constructor phù hợp.

~~~java
import java.util.Collection;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.oauth.introspection-uri}") String endpoint,
            @Value("${app.oauth.introspection-client-id}") String id,
            @Value("${app.oauth.introspection-client-secret}") String secret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(endpoint, id, secret);

        return token -> {
            // Delegate đã xác minh active trước khi trả principal.
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            if (!hasAudience(
                    principal.getAttribute("aud"), "orders-api")) {
                throw new BadOpaqueTokenException(
                    "Token is not intended for this API");
            }

            return principal;
        };
    }

    private static boolean hasAudience(Object raw, String expected) {
        if (raw instanceof String value) {
            return expected.equals(value);
        }
        if (raw instanceof Collection<?> values) {
            return values.stream().anyMatch(
                item -> Objects.equals(expected, item));
        }
        return false;
    }
}
~~~

Cấu hình tương ứng:

~~~yaml
app:
  oauth:
    introspection-uri: https://login.example.test/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Những điểm cần nhớ:

- Delegate chuẩn kiểm tra **`active`**. Nếu inactive, `introspect` không trả principal thành công.
- Decorator chỉ thêm **audience policy** và từ chối khi `aud` không đúng hoặc thiếu.
- Không catch lỗi của delegate rồi trả principal mặc định. Khi upstream không sẵn sàng, **fail closed**.
- Một bean `OpaqueTokenIntrospector` tùy chỉnh có thể khiến Boot nhường auto-configuration, vì vậy phải truyền **đúng endpoint và credential** cho bean đang thực sự được sử dụng.
- Đây là ví dụ cho contract có `aud` dạng string hoặc collection. Nếu Authorization Server khác, cần policy tương ứng; không ép kiểu tùy ý.

Khi custom introspector, tránh thay đổi metadata `active` thành giá trị do ứng dụng tự khai. Nếu cần user status riêng, kiểm tra trong account/domain policy thay vì sửa nội dung phản hồi RFC 7662.

## 11. Caching và tác động đến việc thu hồi token

Introspection giúp Resource Server biết trạng thái token gần thời điểm request, nhưng **cache kết quả active** có thể khiến một token đã revoke vẫn được sử dụng trong một khoảng ngắn.

### 11.1. Timeline ví dụ

~~~text
10:00:00  Resource Server introspect token-A -> active=true
          Cache active result trong 60 giây

10:00:20  Authorization Server revoke token-A

10:00:30  Client gửi token-A
          Cache vẫn báo active=true
          -> request có thể được xử lý theo TTL cache

10:01:01  Cache hết hạn, introspection lại
          -> active=false -> từ chối
~~~

Đây là ví dụ về **trade-off chính sách cache**, không phải cam kết Spring Security mặc định luôn cache 60 giây. Cấu hình thực tế của introspector/cache cần được xác định riêng theo phiên bản triển khai.

### 11.2. Quy tắc TTL

Nếu phản hồi có `exp` đúng schema, thời gian cache tối đa có thể được giới hạn:

~~~text
cacheTtl = min(
    policyMaxTtl,
    tokenExpiration - currentTime
)
~~~

Không cache quá thời hạn token. Nếu không có `exp`, chỉ cache trong giới hạn đã được chấp thuận hoặc **không cache**. TTL càng dài thì khả năng nhìn thấy revocation càng chậm.

Lựa chọn phụ thuộc:

- **Tính nhạy cảm của API**: duyệt giao dịch tài chính có thể cần trạng thái gần thời gian thực hơn API đọc dữ liệu phổ thông.
- **Khả năng sẵn sàng của Authorization Server**: introspection mỗi request tăng phụ thuộc mạng.
- **Load/latency**: cache có thể giảm chi phí xác thực.
- **Tuổi thọ token**: token ngắn hạn giới hạn cửa sổ dùng lại nhưng không thay revocation.
- **Ràng buộc audience/scope**: cache phải giữ đúng metadata của **token cụ thể**, không gộp theo user.

### 11.3. Không cache theo sub hoặc client_id

Hai Access Token cùng `sub` có thể khác scope, audience, thời hạn và revocation status. Nếu cache theo `sub`, một token ít quyền có thể nhận metadata nhiều quyền của token khác.

Cache phải có thiết kế khóa hợp lệ theo **token identity** và ranh giới resource/issuer; không đưa raw token vào logging hoặc metrics. Nếu chọn hash/token fingerprint cho cache key, phải đánh giá entropy của token, mức độ bảo mật của cache và khả năng lộ thông tin qua heap/dump.

### 11.4. Cache active=false?

Negative caching có thể giảm tải khi client liên tục gửi token không hợp lệ. Nhưng cần:

- TTL ngắn và giới hạn bộ nhớ để tránh hàng loạt token rác làm đầy cache.
- Không giữ raw token vô thời hạn.
- Không cache một **lỗi HTTP 503/timeout** như kết luận token inactive.
- Xét kịch bản `nbf` hoặc trạng thái token có thể thay đổi theo chính sách.

Cache kết luận token inactive khác hoàn toàn cache lỗi upstream. Cả hai không nên bị trộn dưới cùng một khóa `active=false`.

### 11.5. Khi cần revocation gần tức thời

Các lựa chọn gồm:

1. Introspect mỗi request hoặc với những thao tác nhạy cảm.
2. Dùng TTL cache rất ngắn, không vượt `exp`.
3. Phát thông báo invalidation/revocation tới cache nếu kiến trúc hỗ trợ.
4. Dùng Access Token ngắn hạn.
5. Kiểm tra local account và quyền domain ở thời điểm thao tác.

Không hứa “opaque token revoke là chặn ngay” khi hệ thống còn cache hoặc đồng bộ trạng thái bất đồng bộ.

## 12. Introspection outage phải fail closed

Khi Authorization Server không trả lời:

~~~text
Client -> API: Bearer token-A
API -> Introspection endpoint: POST token-A
Endpoint -> API: timeout/503/TLS failure

API KHÔNG có chứng cứ mới token-A còn active.
API KHÔNG được tạo principal hợp lệ tùy ý.
API KHÔNG được bỏ qua authentication vì upstream lỗi.
~~~

### 12.1. Ví dụ fail-open cần tránh

~~~java
// KHÔNG LÀM.
try {
    return introspector.introspect(token);
} catch (Exception any) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "fallback-user",
        Map.of("sub", "fallback-user"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.write")));
}
~~~

Lỗi mạng sẽ biến thành quyền truy cập. Một cache valid còn TTL theo chính sách **khác** với việc catch-all tạo Authentication giả: chính sách cache phải định nghĩa trước mức độ chấp nhận revocation latency và được kiểm thử.

### 12.2. Retry với giới hạn

Có thể retry lỗi transient khi introspection timeout/503, nhưng phải đặt:

- Connection/read timeout và tổng thời gian retry tối đa.
- Backoff và jitter khi phù hợp để tránh request storm.
- Circuit breaker/bulkhead nếu workload lớn.
- Không retry vô hạn phản hồi **`active:false`**: đó là kết luận token không được chấp nhận.
- Không retry vô hạn HTTP 401 vì client secret sai.
- Không làm lộ token/secret trong logs hoặc HTTP error body.

Khi vẫn không xác thực được, request phải **không được thực thi như authenticated**, dù API chọn phản hồi 401 hay 5xx/503 theo exception mapping.

## 13. Bảo vệ introspection endpoint và credential

Vì Access Token được gửi nguyên văn đến Authorization Server, đây là một đường truyền nhạy cảm:

1. Chỉ dùng **HTTPS** có TLS certificate và hostname verification.
2. Dùng introspection URI từ **cấu hình đáng tin cậy**, không từ token chưa xác thực hoặc request parameter.
3. Giới hạn outbound egress, redirect, DNS/proxy theo network policy.
4. Xác thực Resource Server đến introspection endpoint bằng credential chỉ có quyền cần thiết.
5. Đặt client secret trong secret manager/environment, hỗ trợ rotation.
6. Không ghi raw token, Basic Authorization header, introspection POST body hoặc dữ liệu cá nhân vào logs.
7. Đặt timeout và giới hạn tải/connection pool phù hợp.
8. Theo dõi lỗi theo category nhưng không biến các labels chứa raw Bearer token.

### 13.1. Credential của Resource Server bị hỏng

Nếu client secret hết hạn/rotate sai, Authorization Server có thể trả HTTP 401 cho **toàn bộ introspection requests**, khiến hàng loạt API requests không thể xác thực. Điều này không chứng minh tất cả user tokens đã hết hạn.

Cần theo dõi riêng lỗi **client authentication upstream**, kiểm tra truststore/mTLS khi dùng, triển khai rotation có kế hoạch và bảo vệ secret.

### 13.2. Sender-constrained tokens

Nếu hệ thống dùng mTLS-bound access tokens hoặc DPoP, `active:true` không tự chứng minh caller thực sự sở hữu private key ràng buộc. Resource Server phải thực thi **proof-of-possession** và đối chiếu confirmation information (`cnf` khi contract liên quan) theo chuẩn token-binding tương ứng. Không coi introspection active là thay thế sender constraint.

## 14. Kiểm thử active=true/false và từng nhánh lỗi

### 14.1. Ma trận test

| Kịch bản | Introspection | Kết quả mong đợi |
| --- | --- | --- |
| Token đọc hợp lệ | 200, `active:true`, `scope:orders.read` | Có thể qua GET nếu policy khác đáp ứng. |
| Token thiếu scope ghi | 200, `active:true`, chỉ `orders.read` | POST bị **403**. |
| Token revoked | 200, `active:false` | **401**, controller không được gọi. |
| Token expired | 200, `active:false` | **401**. |
| Token không tồn tại | 200, `active:false` | **401**. |
| Token active, audience khác | 200, `active:true`, `aud:billing-api` | Từ chối theo audience/resource policy. |
| `active` là string | 200, `{"active":"false"}` | Không tạo Authentication; ghi protocol error. |
| Thiếu `active` | 200, `{}` | Không tạo Authentication. |
| Introspection trả HTTP 401 | Resource Server credential sai | Không cho truy cập, phân loại tích hợp. |
| Introspection trả HTTP 503 | Upstream unavailable | Fail closed; không suy token inactive theo nghĩa nghiệp vụ. |
| Upstream timeout | Không có response | Fail closed, retry có giới hạn. |
| Token active, local account bị khóa | 200, `active:true` | Domain authorization từ chối. |
| Token vừa revoke, cache còn active | Cache hit | Kiểm tra cửa sổ sử dụng tối đa đúng TTL. |

### 14.2. Test với Fake OpaqueTokenIntrospector

Để test **HTTP authorization** độc lập với mạng, có thể tạo một fake introspector chỉ trong test:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@TestConfiguration
class TestOpaqueIntrospectorConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector() {
        return token -> {
            if (!"active-reader-test-token".equals(token)) {
                throw new BadOpaqueTokenException(
                    "Test token is not active");
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                "person-123",
                Map.of("sub", "person-123", "scope", "orders.read"),
                List.of(new SimpleGrantedAuthority(
                    "SCOPE_orders.read")));
        };
    }
}
~~~

Từ fake này có thể gửi Bearer string thật qua filter:

~~~text
GET /api/orders/42
Authorization: Bearer active-reader-test-token
-> Được xác thực với quyền orders.read

POST /api/orders/42
Authorization: Bearer active-reader-test-token
-> 403 nếu endpoint cần orders.write

GET /api/orders/42
Authorization: Bearer some-other-token
-> 401
~~~

Đây là **test double** và không được dùng trong production. Vì fake quyết định active bằng logic riêng, những test này **không chứng minh cách HTTP introspection client đọc JSON `active`**. Cần thêm integration test với server mock.

### 14.3. MockMvc opaqueToken() không gọi introspection

Ví dụ helper `spring-security-test`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`opaqueToken()` tạo Authentication giả lập đã xác thực, không gửi token đến introspection endpoint. Nó phù hợp để test **authorization** nhưng **không thể chứng minh active=false bị từ chối**. Với test revocation, phải gửi Bearer token thật qua một introspector thật hoặc test endpoint.

### 14.4. Integration test với mock introspection server

Thiết kế server fixture:

~~~text
POST /oauth2/introspect, token=active-reader
  -> HTTP 200
  {"active":true,"sub":"person-123",
   "scope":"orders.read","aud":["orders-api"]}

POST /oauth2/introspect, token=inactive
  -> HTTP 200
  {"active":false}

POST /oauth2/introspect, token=wrong-audience
  -> HTTP 200
  {"active":true,"scope":"orders.read","aud":["billing-api"]}

POST /oauth2/introspect, token=malformed
  -> HTTP 200
  {"active":"false"}

POST /oauth2/introspect, token=outage
  -> HTTP 503
~~~

Các bước:

1. Dựng WireMock, MockWebServer hoặc HTTP test server tương tự.
2. Cấu hình `introspection-uri` tới server fixture và credential test, không dùng production secret.
3. Gửi request đến Resource Server với `Authorization: Bearer inactive` **không sử dụng `opaqueToken()`**.
4. Xác nhận API trả 401, không gọi controller/domain service, đồng thời mock server thực sự nhận POST introspection.
5. Lặp lại với `active-reader`, scope thiếu, audience sai, response sai JSON type, HTTP 503 và timeout.
6. Nếu có cache, test token ban đầu active rồi bị revoke, xác nhận khi TTL hết phải bị chặn.

Một introspection fixture có thể dùng localhost HTTP **chỉ trong môi trường test cô lập**; test production network/TLS phải thực thi HTTPS và certificate verification thật theo policy. Không đưa Access Token hoặc client secret production vào test.

### 14.5. Kiểm thử cache khi token bị revoke

~~~text
T1: Mock server trả active=true cho token-A.
T2: API gọi token-A, cache giữ kết quả theo cấu hình.
T3: Mock server chuyển sang active=false cho token-A.
T4: API gọi token-A trước và sau TTL.
T5: Sau TTL phải introspect lại và từ chối.
~~~

Test này cho biết **revocation latency được chấp nhận** thật sự là bao nhiêu. Đừng chỉ unit test `active:false` rồi kết luận hệ thống xử lý revoke tức thời trong khi cache vẫn giữ `active:true`.

## 15. Troubleshooting khi API từ chối opaque token

| Biểu hiện | Điều cần xác nhận | Hướng xử lý |
| --- | --- | --- |
| Introspection HTTP 200 nhưng API 401 | JSON `active` có phải boolean false, hay schema sai? | Phân biệt inactive và protocol error. |
| Mọi request 401 sau đổi secret | Client credentials cho introspection có đúng không? | Kiểm tra credential rotation, mTLS/Basic và Authorization Server logs an toàn. |
| Token còn hạn nhưng `active:false` | Có revoke, issuer/endpoint sai, quyền introspect bị giới hạn? | Xác nhận contract; không tự chấp nhận token. |
| Token active nhưng POST 403 | Scope trả về có `orders.write` không? | Kiểm tra authorities và HTTP rule. |
| Token active nhưng domain 403 | User/tenant/owner/status có phù hợp? | Kiểm tra policy nghiệp vụ; không kết luận token invalid. |
| Token revoke vẫn hoạt động trong thời gian ngắn | Có cache active không? TTL bao lâu? | Điều chỉnh cache/invalidation theo revocation SLA. |
| Introspection timeout, API lỗi | Upstream DNS/TLS/connect timeout/capacity? | Retry có giới hạn, bảo vệ service và fail closed. |
| `active:"true"` bị từ chối | Sai kiểu JSON. | Sửa Authorization Server/adapter, không ép kiểu mơ hồ. |
| Principal code cần Jwt nhưng nhận null | API cấu hình opaque token. | Dùng `OAuth2AuthenticatedPrincipal`/Bearer authentication. |
| ID Token đăng nhập web không gọi được API | Sai loại token/resource. | Cấp đúng Access Token cho API theo OAuth contract. |

### 15.1. Quan sát mà không lộ credential

Nên ghi:

- Request ID, thời điểm, nhóm lỗi.
- `token_inactive`, `introspection_timeout`, `introspection_http_401`, `introspection_schema_error`, `insufficient_scope`.
- Latency và tỷ lệ lỗi introspection.
- Cache hit/miss và lượng invalidation khi có cache.
- Audit nghiệp vụ với định danh được kiểm soát truy cập.

Không ghi:

- Raw opaque Access Token, dù đã revoke.
- Header `Authorization` ở API hoặc introspection request.
- Client secret, mTLS private key hoặc form body chứa token.
- Toàn bộ introspection response có claims cá nhân.
- Token string làm metric label hoặc tracing attribute.

## 16. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Thấy HTTP 200 từ introspection thì cho phép request. | 200 có thể chứa `active:false`. | Kiểm tra JSON boolean active. |
| Nhận `active:"true"` như boolean true. | Sai kiểu/contract, có thể che lỗi phát hành. | Chỉ chấp nhận response hợp lệ theo RFC. |
| Khi upstream timeout, tự xem token active. | Fail-open khi authentication phụ thuộc hạ tầng. | Fail closed, báo lỗi vận hành có kiểm soát. |
| Dùng scope từ token opaque bằng cách tách chuỗi. | Dữ liệu không được xác thực. | Chỉ lấy metadata introspection từ nguồn tin cậy. |
| Cache active đến vô hạn. | Token revoke vẫn dùng lâu dài. | TTL giới hạn và invalidation. |
| Cache theo user ID thay vì token. | Lẫn scope/audience giữa token khác nhau. | Cache theo token identity phù hợp. |
| Cache HTTP 503 như active=false. | Nhầm outage với token invalid, ảnh hưởng hồi phục. | Phân biệt error và state, retry/metrics riêng. |
| active=true thì cấp mọi quyền. | Bỏ qua scope/tenant/owner. | Authorization độc lập sau authentication. |
| Token dành cho API khác vẫn được nhận. | Audience/resource không được kiểm tra. | Ràng buộc resource theo contract. |
| OIDC ID Token được dùng thay Access Token. | Sai mục đích/caller. | Chấp nhận đúng loại Access Token. |
| Logout luôn giả định revoke Access Token. | Logout session chưa chắc revoke token. | Thiết kế lifecycle và kiểm thử revoke cụ thể. |
| Custom introspector trả principal trong catch exception. | Bỏ qua active và lỗi network. | Delegate chuẩn + validator bổ sung, fail closed. |
| Chỉ test bằng MockMvc opaqueToken(). | Không kiểm tra HTTP introspection thật. | Thêm integration test gửi Bearer qua introspector. |
| Log raw token khi lỗi. | Rò rỉ credential. | Metrics/error categories không chứa token. |

## 17. Quy trình triển khai áp dụng trong dự án

1. **Xác định hợp đồng token:** API nhận opaque Access Token, token profile, issuer, resource/audience, scopes và thời hạn cần thiết.
2. **Thống nhất introspection contract:** endpoint HTTPS, phương thức client authentication, `active` boolean và metadata được phép trả về.
3. **Cấu hình Spring Security:** `spring.security.oauth2.resourceserver.opaque-token` và `oauth2ResourceServer().opaqueToken()`.
4. **Giữ nguyên ngữ nghĩa active:** inactive thì authentication thất bại; response sai kiểu/missing active không được tạo principal.
5. **Kiểm tra resource và quyền:** audience, scope, domain account/tenant và tài nguyên cụ thể độc lập với active.
6. **Xử lý lỗi upstream:** phân biệt inactive token với introspection outage/credential failure; fail closed, giới hạn retry và timeout.
7. **Định nghĩa cache TTL và revocation latency:** không vượt token expiration, không cache lỗi transport như inactive, có kế hoạch invalidation.
8. **Bảo vệ token và secrets:** HTTPS/TLS, allowlist endpoint, client credential least privilege, không log raw token.
9. **Kiểm thử positive/negative:** active=true, false, JSON sai kiểu, timeout, 503, thiếu scope, sai audience và local user bị khóa.
10. **Kiểm thử thay đổi trạng thái:** token từng active rồi revoke; xác nhận ảnh hưởng cache theo policy thực tế.

**Ghi nhớ:** Trong OAuth 2.0 introspection, **`active:false` có nghĩa Resource Server không được chấp nhận token**, chứ không nhất thiết tiết lộ chính xác vì sao token inactive. **`active:true` không đồng nghĩa được truy cập mọi API**; còn phải kiểm tra resource, scope và quyền nghiệp vụ. Nếu introspection gặp sự cố, hệ thống phải **fail closed** và phân biệt lỗi hạ tầng với token không còn hiệu lực.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — OpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449).
