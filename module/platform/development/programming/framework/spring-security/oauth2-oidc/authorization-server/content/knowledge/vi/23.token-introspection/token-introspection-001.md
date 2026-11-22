# Mục đích của OAuth2 Token Introspection

## 1. Bối cảnh: Resource Server cần biết token còn hiệu lực hay không

Trong hệ thống OAuth 2.0/OpenID Connect sử dụng **Spring Security**, **Spring Authorization Server** và Spring Boot, Authorization Server (AS) phát hành access token cho OAuth client. Client gửi token tới Resource Server (RS) để truy cập API.

RS phải quyết định request có được xác thực hay không. Với JWT access token, RS thường có thể xác minh chữ ký, issuer, audience và thời hạn ngay tại chỗ. Nhưng với opaque access token, RS không thể tự đọc claims từ token. Ngay cả JWT tự chứa cũng có thể cần kiểm tra trạng thái thu hồi hoặc trạng thái authorization mới nhất.

**OAuth 2.0 Token Introspection** được chuẩn hóa trong **RFC 7662**. Đây là giao thức để một protected resource hỏi Authorization Server về trạng thái của một token. AS trả về một JSON document có trường bắt buộc `active` và có thể kèm các metadata cần thiết để RS thực hiện authorization.

Ví dụ, hệ thống thương mại điện tử có:

- `checkout-service`: Resource Server nhận request thanh toán.
- `order-web`: OAuth client lấy access token cho người dùng.
- `auth.example.com`: Authorization Server phát hành và quản lý token.

Khi `checkout-service` nhận access token, nó gọi Introspection Endpoint của AS để hỏi token có còn active và có dành cho chính service này hay không. AS kiểm tra trạng thái token rồi trả kết quả. RS chỉ tiếp tục khi token active, đúng audience và đủ scope theo policy.

**Introspection không phải một grant type để client xin token mới.** Đây là một endpoint phục vụ việc kiểm tra trạng thái token bởi protected resource đã được AS cho phép.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mục đích và vai trò của Token Introspection theo RFC 7662.
2. Phân biệt introspection với token validation cục bộ, token revocation và token refresh.
3. Hiểu ý nghĩa của trường `active` và các metadata thường có trong response.
4. Xác định vai trò của `token` và `token_type_hint` trong request.
5. Giải thích vì sao protected resource phải được xác thực và cấp quyền gọi introspection.
6. So sánh introspection cho opaque token và JWT access token.
7. Cấu hình Spring Authorization Server và Spring Security Resource Server cho introspection.
8. Thiết kế cache, timeout, rate limit, privacy và xử lý lỗi.
9. Kiểm thử token active/inactive, audience, scope, revocation và tình huống AS outage.

## 2. Token Introspection giải quyết vấn đề gì?

Access token là credential đại diện cho quyền truy cập. RS cần xác minh ít nhất:

- Token có được AS đáng tin phát hành không?
- Token có còn trong thời hạn hiệu lực không?
- Token đã bị thu hồi hoặc vô hiệu hóa chưa?
- Token có được phát hành cho RS đang nhận request không?
- Token có scope/authority phù hợp endpoint không?
- Token có bị ràng buộc với client, subject, tenant hoặc proof-of-possession không?

Với **opaque token**, RS thường không thể xác minh các thông tin này chỉ bằng cách parse token. Token có thể chỉ là chuỗi ngẫu nhiên, còn dữ liệu authorization được lưu tại AS.

Introspection cho phép RS gửi token tới AS qua một endpoint được bảo vệ. AS tra trạng thái và trả thông tin theo policy.

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as checkout-service / Resource Server
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: API request + access token
    RS->>RS: Xác định token cần introspect
    RS->>AS: POST /oauth2/introspect<br/>RS authentication + token
    AS->>AS: Xác thực protected resource
    AS->>DB: Tra token và authorization state
    DB-->>AS: Token metadata / trạng thái
    AS->>AS: Áp dụng active và resource policy
    AS-->>RS: active + metadata được phép tiết lộ
    RS->>RS: Kiểm tra audience, scope, subject
    RS-->>C: Cho phép hoặc từ chối API request
```

Introspection tạo một bước kiểm tra online giữa RS và AS. Nhờ đó, AS có thể áp dụng trạng thái authorization mới nhất theo khả năng lưu trữ và chính sách của hệ thống.

### 2.1. Token Introspection không phải token issuance

| Hoạt động | Ai gọi? | Mục đích |
|---|---|---|
| Token issuance | OAuth client | Xin AS phát hành token |
| Token introspection | Protected resource / RS | Hỏi AS token có active và metadata gì |
| Token revocation | OAuth client được phép | Yêu cầu AS thu hồi token |
| Refresh | OAuth client | Đổi refresh token lấy access token mới |
| UserInfo | OIDC client | Lấy claims về End-User theo access token |

Một request introspection không làm mới token, không kéo dài `exp` và không tự thu hồi token. Nó chỉ hỏi trạng thái tại thời điểm AS xử lý request.

## 3. RFC 7662: Introspection Endpoint

RFC 7662 định nghĩa endpoint mà Authorization Server công bố để protected resource kiểm tra token. URI cụ thể tùy cấu hình/metadata; trong ví dụ Spring Authorization Server thường dùng:

```text
POST /oauth2/introspect
```

Endpoint phải được bảo vệ. AS cần xác thực protected resource gọi endpoint và quyết định resource đó có được quyền introspect hay không. Không để endpoint công khai cho bất kỳ ai vì nó có thể trở thành công cụ dò token hoặc thu thập metadata.

### 3.1. Ai được gọi introspection?

Thông thường, RS có một OAuth client registration riêng để xác thực với AS. Credential này đại diện **dịch vụ introspection requester**, không phải token đang được kiểm tra.

Ví dụ:

| Credential/thành phần | Ý nghĩa |
|---|---|
| `checkout-service-introspector` | Client identity của RS khi gọi introspection |
| Client secret/private key/mTLS credential | Xác thực RS với AS |
| `token` trong form body | Access token của end-user hoặc workload đang cần kiểm tra |
| `client_id` trong response | OAuth client đã yêu cầu token được introspect, nếu AS cung cấp |

Không dùng access token đang được kiểm tra làm client secret của introspection endpoint. Cũng không nhầm `client_id` của RS với `client_id` trong metadata của token.

### 3.2. Endpoint introspection phải dùng TLS

Token và metadata authorization là dữ liệu nhạy cảm. RS cần gọi introspection endpoint qua HTTPS/TLS và xác minh certificate của AS theo trust policy. Không gửi token qua HTTP không mã hóa hoặc tới endpoint tùy ý.

Trong môi trường nhiều service, dùng service discovery/configuration tin cậy, giới hạn outbound network và xác thực client. Tránh cho caller bên ngoài tự chọn introspection URL.

## 4. Introspection Request

Theo RFC 7662 `2.1, request dùng HTTP POST với content type `application/x-www-form-urlencoded`. Tham số `token` là bắt buộc; `token_type_hint` là tùy chọn.

Ví dụ:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_TO_CHECK
&token_type_hint=access_token
```

Giá trị token trong ví dụ chỉ là placeholder. Không đưa token thật vào URL query, log, trace hoặc ticket.

### 4.1. Tham số `token`

`token` là token cần kiểm tra. Có thể là access token hoặc token type khác mà AS hỗ trợ introspection. Trong kiến trúc Resource Server, trường hợp thường gặp là access token.

AS cần tra token trong kho authorization hoặc cơ chế quản lý token tương ứng. Không chỉ decode JWT rồi trả `active=true` vì token có thể đã bị thu hồi, hết hạn, chưa có hiệu lực hoặc không được cấp cho resource đang hỏi.

### 4.2. Tham số `token_type_hint`

`token_type_hint` là gợi ý về loại token mà client đang gửi. Giá trị có thể gồm:

- `access_token`
- `refresh_token`

Đây chỉ là **hint**, không phải bằng chứng loại token. AS có thể dùng nó để chọn nơi tra cứu trước. Nếu không tìm thấy token theo hint, RFC 7662 yêu cầu AS tiếp tục thử các loại token được hỗ trợ theo quy tắc của giao thức.

Không tin `token_type_hint` để bỏ qua kiểm tra loại token hoặc trả metadata không phù hợp. Nếu endpoint chỉ cho phép introspect access token, policy phải giới hạn rõ.

### 4.3. Xác thực requester độc lập với token được introspect

Header Basic trong ví dụ là credential của `checkout-service-introspector`. AS phải:

1. Xác thực client/resource server gọi introspection.
2. Kiểm tra requester có được phép gọi endpoint không.
3. Kiểm tra token đầu vào.
4. Chỉ trả metadata mà requester được phép biết.

Một kẻ tấn công biết token của user nhưng không có credential của RS không được phép gọi introspection để dò trạng thái hoặc đọc claims.

## 5. Introspection Response và trường active

Response thành công thường là JSON:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read payments.status.read",
  "client_id": "order-web",
  "token_type": "Bearer",
  "exp": 1794825600,
  "iat": 1794825300,
  "sub": "user-42",
  "aud": [
    "https://checkout-api.example.com"
  ],
  "iss": "https://auth.example.com",
  "jti": "token-id-123"
}
```

Đây là response minh họa. AS có thể trả thêm hoặc bỏ các metadata tùy chọn theo token type và policy. Trường `active` là trường bắt buộc.

### 5.1. Ý nghĩa của `active`

`active` phải là JSON boolean:

- `true`: token được AS coi là active tại thời điểm introspection theo policy áp dụng.
- `false`: token không active hoặc AS không thể xác nhận token hợp lệ cho protected resource này.

Theo RFC 7662, token active thường phải được AS phát hành, chưa hết hạn, chưa bị thu hồi và hợp lệ đối với protected resource đang thực hiện introspection. AS có thể áp dụng thêm điều kiện theo policy.

**`active=true` không có nghĩa request API tự động được phép.** RS vẫn cần kiểm tra audience, scope, tenant, subject, sender constraint và authorization nghiệp vụ.

### 5.2. Vì sao inactive response không nên tiết lộ chi tiết?

Với token không active, AS nên trả tối thiểu:

```json
{
  "active": false
}
```

Không nên tiết lộ token sai chữ ký, đã hết hạn, bị revoke, không tồn tại hay thuộc một client khác vì những khác biệt đó có thể hỗ trợ attacker dò credential hoặc thu thập thông tin nội bộ.

AS có thể ghi lý do chi tiết vào audit nội bộ có phân quyền, nhưng response công khai nên tránh tiết lộ nguyên nhân cụ thể.

### 5.3. HTTP 200 và active false là hai ý nghĩa khác nhau

Một token không active thường vẫn được trả về trong một introspection response thành công với `active=false`. Đây không phải lỗi server.

| Tình huống | Ý nghĩa |
|---|---|
| HTTP 200, `active=true` | AS xác nhận token active |
| HTTP 200, `active=false` | Request introspection hợp lệ, token không active |
| HTTP 400, `invalid_request` | Request thiếu/sai tham số |
| HTTP 401, `invalid_client` hoặc cơ chế tương ứng | Requester không xác thực được |
| HTTP 5xx/timeout | AS hoặc hạ tầng gặp sự cố; RS không thể xác nhận trạng thái |

Không biến timeout thành `active=true`. Nếu RS không thể xác minh trạng thái theo policy, cần xử lý như dependency failure và áp dụng availability policy đã định.

## 6. Các metadata thường có trong response

RFC 7662 định nghĩa một số metadata có thể xuất hiện khi token active:

| Field | Ý nghĩa |
|---|---|
| `scope` | Scope đã được cấp, thường là chuỗi phân tách bằng dấu cách |
| `client_id` | OAuth client đã yêu cầu token |
| `username` | Tên người dùng theo định nghĩa AS nếu có |
| `token_type` | Loại token theo OAuth token type registry |
| `exp` | Thời điểm hết hạn (NumericDate) |
| `iat` | Thời điểm phát hành |
| `nbf` | Thời điểm token bắt đầu có hiệu lực |
| `sub` | Subject của token |
| `aud` | Audience/resource nhận token |
| `iss` | Issuer phát hành token |
| `jti` | Định danh token |
| `cnf` | Confirmation claim cho sender-constrained token hoặc binding khác |

Các metadata trên không nhất thiết đều có trong mọi response. AS phải bảo vệ privacy và chỉ tiết lộ thông tin cần thiết cho protected resource được xác thực.

### 6.1. `scope`

`scope` mô tả quyền được cấp, thường dùng dạng chuỗi space-delimited:

```text
orders.read payments.status.read
```

RS có thể ánh xạ scope thành authorities và kiểm tra theo endpoint. Không suy ra quyền quản trị từ một chuỗi scope tùy ý nếu không có policy mapping rõ.

### 6.2. `aud`

`aud` giúp RS xác định token có dành cho mình không. Nếu AS trả audience, RS phải kiểm tra identifier của chính mình nằm trong audience theo contract.

Không chấp nhận token chỉ vì `active=true` khi token thực tế được cấp cho API khác. Active là trạng thái token theo ngữ cảnh introspection; audience vẫn là một phần authorization contract.

### 6.3. `sub` và `client_id`

`sub` đại diện subject mà token nói tới; `client_id` cho biết OAuth client yêu cầu token. Với Authorization Code, subject có thể là user; với Client Credentials, subject có thể đại diện workload theo semantics của AS.

Không nhầm client gọi introspection với client đã yêu cầu access token. Hai danh tính này thường khác nhau.

### 6.4. `cnf`

Với token sender-constrained, metadata `cnf` có thể mang thông tin binding. Ví dụ DPoP-bound token có `cnf.jkt`. RS vẫn phải xác minh proof-of-possession tương ứng; introspection trả claim `cnf` không tự chứng minh request hiện tại giữ private key.

## 7. Token Introspection và JWT local validation

Có hai chiến lược xác minh token phổ biến:

1. **Local validation:** RS tự xác minh JWT signature, issuer, audience, expiry và claims.
2. **Remote introspection:** RS hỏi AS về trạng thái token qua endpoint được bảo vệ.

| Tiêu chí | JWT local validation | Remote introspection |
|---|---|---|
| Network call cho mỗi request | Không bắt buộc | Có, nếu không cache |
| Hỗ trợ opaque token | Không tự đọc được | Có |
| Kiểm tra trạng thái revoke mới nhất | Cần cơ chế bổ sung | Có thể phản ánh trạng thái AS mới nhất |
| Latency | Thường thấp | Phụ thuộc network/AS |
| Availability dependency | Phụ thuộc JWKS/cache | Phụ thuộc introspection endpoint |
| Dữ liệu authorization | Claims trong token | Metadata AS trả về |
| Kiểm soát tập trung | Khó cập nhật token đã phát | AS có thể áp dụng trạng thái hiện tại |
| Privacy | Claims có thể nằm trong JWT client giữ | AS có thể chỉ tiết lộ metadata cho RS được phép |

### 7.1. Opaque token là use case điển hình

Opaque token không chứa claims có thể đọc cục bộ. RS không thể xác minh chữ ký JWT hoặc tự đọc `exp`. Introspection cho phép AS tra token và trả `active` cùng metadata.

Điều này hữu ích khi muốn:

- Che giấu cấu trúc token.
- Giữ authorization state ở AS.
- Thu hồi token và phản ánh trạng thái mới nhanh hơn.
- Trả metadata theo quyền của protected resource.
- Hỗ trợ nhiều loại token trong một hệ thống.

### 7.2. JWT cũng có thể được introspect

JWT có thể được xác minh cục bộ, nhưng introspection vẫn hữu ích nếu hệ thống cần kiểm tra trạng thái authorization hiện tại, revocation hoặc policy động. Việc token có thể decode không có nghĩa RS nên tự quyết định trạng thái mà không xét yêu cầu sản phẩm.

Một hệ thống có thể dùng JWT local validation cho phần lớn request và introspection cho một số tài nguyên nhạy cảm. Cần tránh hai đường validation có policy khác nhau gây kết quả không nhất quán.

### 7.3. Introspection không tự tạo revocation tức thời nếu state không được chia sẻ

Nếu AS lưu trạng thái token ở memory riêng từng instance hoặc authorization store không nhất quán, một node có thể báo active trong khi node khác đã revoke. Muốn introspection phản ánh trạng thái chính xác, issuance, revocation và introspection phải dùng cùng nguồn trạng thái tin cậy hoặc cơ chế đồng bộ được xác định.

## 8. Phân biệt introspection với revocation và refresh

| Cơ chế | Chuẩn | Ai khởi tạo? | Kết quả |
|---|---|---|---|
| Token Introspection | RFC 7662 | Protected resource | Trả trạng thái và metadata token |
| Token Revocation | RFC 7009 | OAuth client được phép | Yêu cầu AS vô hiệu hóa token |
| Refresh Token Grant | RFC 6749 | OAuth client | Đổi refresh token lấy access token mới |
| JWT validation | RFC 7519/JWS và profile liên quan | Resource Server | Xác minh token cục bộ |

Ví dụ: người dùng đăng xuất và client gọi revocation endpoint để thu hồi refresh token. Sau đó, `checkout-service` introspect access token. Nếu AS đã cập nhật trạng thái và token được quản lý theo cách hỗ trợ revoke, response có thể trả `active=false`.

**Introspection không phải thao tác thu hồi.** Nó chỉ cho RS biết AS đang coi token như thế nào tại thời điểm truy vấn.

## 9. Spring Authorization Server: cấu hình Introspection Endpoint

Spring Authorization Server cung cấp Token Introspection Endpoint trong protocol endpoints. Endpoint thường được bảo vệ bởi client authentication và sử dụng `OAuth2AuthorizationService` để tra authorization/token state.

Trong cấu hình hiện đại, có thể dùng configurer:

```java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.tokenIntrospectionEndpoint(Customizer.withDefaults()));

        return http.build();
    }
}
```

Đây là ví dụ tập trung vào endpoint configurer, không phải toàn bộ Authorization Server. Ứng dụng còn cần registered client repository, authorization service, token generator, JWK source, issuer và các chain/login flow cần thiết.

Trong nhiều cấu hình, introspection endpoint đã được cấu hình mặc định bởi Authorization Server configurer; gọi `tokenIntrospectionEndpoint` là cách thể hiện rõ điểm tùy biến. Kiểm tra API đúng phiên bản dependency trước khi dùng vì package và signature có thể thay đổi giữa các dòng phát hành.

### 9.1. Authorization store phải lưu được token state

Introspection cần tìm token và đánh giá trạng thái. Vì vậy, AS phải có `OAuth2AuthorizationService` được dùng nhất quán khi phát hành, refresh, revoke và introspect token.

Các lựa chọn thường gặp:

- `InMemoryOAuth2AuthorizationService`: thuận tiện cho demo/test, mất state khi process restart và không phù hợp nhiều instance production.
- `JdbcOAuth2AuthorizationService`: lưu authorization/token state trong database; cần schema, index, transaction và migration phù hợp.
- Custom authorization service: có thể dùng database/cache khác nhưng phải bảo đảm consistency, lookup và revocation semantics.

Không phát token qua một service rồi introspect ở một service khác không chia sẻ state mà kỳ vọng luôn nhận được kết quả chính xác.

### 9.2. Registered client gọi introspection

Resource Server cần một client registration riêng để xác thực với AS. Ví dụ confidential service:

```java
RegisteredClient introspectionClient = RegisteredClient
    .withId("checkout-introspector-internal-id")
    .clientId("checkout-service-introspector")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("introspection.call")
    .build();
```

Đoạn code minh họa client identity. Scope `introspection.call` chỉ là tên nghiệp vụ giả định; endpoint introspection thường dựa trên authenticated client và policy của AS, không mặc nhiên dùng scope này nếu ứng dụng chưa triển khai kiểm tra. Không thêm grant hoặc scope không được framework/policy sử dụng.

Secret phải đến từ secret manager. Trong môi trường production, có thể chọn `private_key_jwt` hoặc mTLS theo threat model và khả năng của phiên bản.

### 9.3. Xác thực requester và phân quyền endpoint

AS cần bảo đảm client gọi introspection là protected resource được phép. Không phải cứ đăng ký một OAuth client là tự động được introspect mọi token.

Một policy có thể giới hạn:

- Client nào được introspect.
- Token type nào được kiểm tra.
- Tenant/resource scope nào được phép nhìn thấy.
- Metadata nào được trả.
- Tần suất request.
- Mạng hoặc workload identity được chấp nhận.

Đừng tiết lộ metadata nhạy cảm của token cho client không có quan hệ với resource đó.

## 10. Resource Server gọi Introspection Endpoint

Spring Security Resource Server hỗ trợ opaque token introspection. Cấu hình qua Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: checkout-service-introspector
          client-secret: SECRET_FROM_SECURE_CONFIGURATION
```

`SECRET_FROM_SECURE_CONFIGURATION` là placeholder. Không commit secret thực vào YAML hoặc Git. Dùng environment/secret manager và bảo vệ log cấu hình.

Sau đó cấu hình Resource Server:

```java
@Bean
SecurityFilterChain resourceServerSecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/health").permitAll()
            .requestMatchers("/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
```

Spring Security sử dụng introspector được cấu hình để gửi token tới AS, đọc response và tạo authenticated principal. Các authorities thường được tạo từ scope trong response. Kiểm tra mapping thực tế nếu hệ thống dùng claim tùy biến.

### 10.1. Introspection requester và access token là hai credential khác nhau

Khi Spring Security gọi introspection:

- `client-id`/`client-secret` trong cấu hình dùng để **Resource Server xác thực với AS**.
- Access token trong request API được gửi làm tham số `token` để **AS kiểm tra**.

Không lấy access token end-user làm client secret của introspection client. Không gửi secret introspection client tới Resource Server khác.

### 10.2. Ánh xạ scope thành authority

Nếu response có:

```json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "sub": "user-42",
  "aud": ["https://checkout-api.example.com"]
}
```

Resource Server có thể ánh xạ thành:

```text
SCOPE_orders.read
SCOPE_orders.cancel
```

Sau đó dùng `hasAuthority`/method security và kiểm tra ownership/tenant trong domain. Không coi `active=true` là quyết định authorization cuối cùng.

### 10.3. Kiểm tra audience trong ứng dụng

Không phải mọi introspection client/library tự động enforce audience theo identifier của từng API. Cần xác minh behavior của phiên bản Spring Security và thêm validator/policy nếu cần.

Nếu AS trả `aud`, RS phải kiểm tra token dành cho chính nó. Nếu response không có audience, RS cần một contract khác để xác định resource binding hoặc yêu cầu AS chỉ trả active cho đúng requester theo semantics đã cấu hình.

## 11. Introspection cache: cân bằng freshness và hiệu năng

Nếu RS introspect cho mọi API request, mỗi request sẽ tạo thêm network round-trip và tải cho AS. Có thể cache kết quả trong một khoảng ngắn, nhưng cache làm chậm khả năng nhìn thấy revocation hoặc policy change.

### 11.1. Positive cache

Positive cache giữ kết quả `active=true`. Key nên dựa trên token fingerprint/hash, không lưu raw token trong key hiển thị hoặc metrics. TTL phải bị giới hạn bởi:

- Thời gian còn lại tới `exp`.
- Mức freshness mà sản phẩm yêu cầu.
- Thời gian chấp nhận rủi ro sau revocation.
- Cache invalidation nếu AS có cơ chế push/eviction.
- Audience/tenant/resource context nếu response phụ thuộc requester.

Ví dụ: access token còn 60 giây, cache không được giữ active quá 60 giây; nếu chính sách yêu cầu phản ánh revocation trong 10 giây, cache positive cũng không nên dài hơn giới hạn đó.

### 11.2. Negative cache

Có thể cache `active=false` trong một khoảng rất ngắn để tránh lặp request với token rác. Tuy nhiên:

- Token vừa được phát hành có thể chưa đồng bộ tới introspection store.
- Cache negative quá lâu có thể từ chối token vừa hợp lệ.
- Token fingerprint cần an toàn và bounded.
- Không trả thông tin chi tiết vì sao token inactive.

### 11.3. HTTP cache header và internal cache

RFC 7662 yêu cầu response introspection có `Cache-Control: no-store` và `Pragma: no-cache` để ngăn HTTP intermediary/browser cache response nhạy cảm.

Điều đó không có nghĩa RS không thể xây dựng một **internal authorization cache** theo policy riêng. Internal cache là state ứng dụng có TTL, security controls và invalidation; không được biến response thành tài nguyên HTTP có thể cache công khai.

### 11.4. Cache không được biến timeout thành active

Nếu AS timeout, không được lấy một response lỗi rồi cache như `active=true`. Có thể dùng kết quả positive đã cache trong thời gian TTL còn hiệu lực nếu policy cho phép. Khi không có kết quả đủ mới, RS phải áp dụng failure policy an toàn.

## 12. Xử lý AS outage và lỗi introspection

Introspection tạo runtime dependency vào AS. Cần phân biệt các tình huống:

| Tình huống | Ý nghĩa | Hướng xử lý |
|---|---|---|
| HTTP 200, `active=false` | Token không active | Từ chối request (thường 401) |
| HTTP 200, `active=true` | Token active | Tiếp tục audience/scope/policy checks |
| HTTP 400 | Request introspection sai | Điều tra integration/config |
| HTTP 401 | Introspection client authentication thất bại | Kiểm tra credential/rotation |
| HTTP 403 | Requester không được phép introspect | Kiểm tra policy/registration |
| HTTP 429 | AS giới hạn lưu lượng | Backoff, cache hợp lệ, quota |
| HTTP 5xx | AS hoặc dependency gặp sự cố | Circuit breaker, timeout, fallback policy |
| Network timeout | Không thể xác nhận trạng thái | Không coi là token active |
| Invalid response/schema | Không thể tin kết quả | Fail safely và alert |

### 12.1. Fail-open hay fail-closed?

Với endpoint thanh toán, admin hoặc dữ liệu nhạy cảm, khi không thể introspect và không có cache hợp lệ, thường phải **fail-closed**: từ chối hoặc trả lỗi tạm thời thay vì coi token active.

Một số hệ thống availability-critical có thể chấp nhận dùng positive cache còn hiệu lực trong thời gian ngắn. Đó là policy có giới hạn, không phải fail-open vô điều kiện.

Phân biệt:

- Token inactive: request không được xác thực, thường trả 401.
- AS unavailable: RS không thể xác minh, có thể trả 503 hoặc lỗi dependency phù hợp.
- Token active nhưng thiếu scope: 403.

Không trả 401 cho mọi lỗi AS nếu điều đó khiến client tưởng credential sai và liên tục đăng nhập/xin token mới.

### 12.2. Timeout và retry

Đặt timeout riêng cho introspection HTTP client, gồm connect/read/response deadline phù hợp SLO. Retry chỉ với lỗi tạm thời và có giới hạn, exponential backoff/jitter. Không retry vô hạn hoặc retry ngay mọi request API khi AS đang outage.

Nếu 100 request đồng thời cùng cần introspection, cân nhắc request coalescing/single-flight cho cùng token fingerprint để giảm tải. Cơ chế này phải bảo đảm một kết quả không bị dùng cho token khác.

### 12.3. Circuit breaker và bulkhead

Circuit breaker có thể ngừng gọi AS khi lỗi liên tục, giúp tránh làm cạn connection pool. Bulkhead giới hạn số introspection calls đồng thời. Khi circuit mở, dùng cache positive còn hiệu lực nếu policy cho phép; nếu không, trả lỗi tạm thời.

Không bỏ qua validation hoặc đánh dấu token active chỉ vì circuit breaker đang mở.

## 13. Bảo mật Introspection Endpoint

### 13.1. Chống token scanning

Nếu endpoint công khai, attacker có thể gửi hàng triệu token đoán để xác định token nào hợp lệ. Bảo vệ:

- Bắt buộc authentication của protected resource.
- Chỉ cho phép registered resource/client đã được cấp quyền.
- Rate limit theo client đã xác thực và nguồn mạng đáng tin.
- Giới hạn request body, header và token length.
- Không tiết lộ lý do inactive.
- Theo dõi tỷ lệ active/inactive bất thường.
- Không đưa endpoint vào public API gateway nếu không cần.

### 13.2. Least privilege cho introspection requester

Mỗi RS nên có identity riêng hoặc nhóm identity có phân quyền. Khi credential của một RS bị lộ, attacker không nên có quyền introspect mọi loại token hoặc đọc metadata không liên quan.

Có thể giới hạn resource audience, tenant, token type và response claims. Nếu AS không hỗ trợ per-resource introspection policy mặc định, bổ sung policy qua extension point phù hợp và test kỹ.

### 13.3. Bảo vệ credential

- Dùng secret manager hoặc private key store.
- Hỗ trợ rotation với overlap nếu phương thức xác thực cho phép.
- Không log HTTP Basic header.
- Ưu tiên private_key_jwt hoặc mTLS khi phù hợp threat model.
- Dùng TLS và certificate validation.
- Thu hồi credential introspection khi service bị xâm nhập.

### 13.4. Không cho caller chọn introspection URL

Nếu RS nhận token từ client bên ngoài, không lấy URL introspection từ request parameter, JWT claim tùy ý hoặc header caller. Endpoint phải là cấu hình tin cậy. Nếu không, attacker có thể khiến RS gửi token tới server của attacker, dẫn tới token exfiltration hoặc SSRF.

## 14. Introspection với JWT và opaque token trong Spring

### 14.1. Opaque token

Với opaque token, Spring Security dùng `OpaqueTokenIntrospector` để gọi AS. Response `active` quyết định token có được xem là active; metadata được chuyển thành principal/authorities.

Đây là cách phổ biến khi AS giữ token state tập trung hoặc muốn RS không cần biết định dạng nội bộ.

### 14.2. JWT

Với JWT, Resource Server thường dùng `JwtDecoder` để xác minh cục bộ. Nếu cần trạng thái revoke mới nhất, có thể:

- Dùng introspection cho token JWT theo AS implementation.
- Kết hợp local signature validation với online status check.
- Dùng denylist/event propagation hoặc token version.
- Chuyển sang opaque token cho use case cần trạng thái tập trung.

Không giả định mọi AS introspection JWT theo cùng cách. Một số implementation chỉ tra authorization store; số khác có thể validate token theo cấu hình. Phải kiểm tra contract thực tế.

### 14.3. Hai filter chain không nên nhầm vai trò

Nếu cùng một Spring Boot process vừa là Authorization Server vừa là Resource Server:

- AS chain bảo vệ `/oauth2/introspect` và các OAuth endpoints.
- RS chain bảo vệ API nghiệp vụ.
- RS introspection client là client credential dùng khi gọi AS.
- Access token end-user/workload là credential được kiểm tra tại API.

Tách chain và matcher đúng thứ tự để request API không bị xử lý nhầm như OAuth endpoint hoặc ngược lại.

## 15. Các lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho endpoint introspection công khai | Token scanning, metadata leakage | Authenticate và authorize requester |
| Dùng token cần kiểm tra làm Basic credential | Nhầm hai credential | Dùng identity riêng của RS |
| Tin `token_type_hint` như bằng chứng | Sai loại lookup hoặc policy | Coi là hint, xác minh token thật |
| `active=true` là cho phép mọi API | Bỏ qua audience/scope | RS tiếp tục authorization |
| `active=false` trả lý do chi tiết | Token enumeration | Response tối thiểu |
| Timeout coi là active | Fail-open trái policy | Fail safely hoặc dùng cache hợp lệ |
| Cache positive quá lâu | Revocation chậm | TTL theo exp và revocation SLO |
| Cache response qua proxy | Lộ metadata/token status | no-store/no-cache |
| Không chia sẻ authorization store | Node trả active/inactive khác nhau | Shared consistent state |
| Không giới hạn request size | Memory/CPU exhaustion | Body/token length cap |
| Log token/body/Basic header | Credential leakage | Redaction |
| Introspect mọi API request không cache | Tăng latency và AS load | Cache có kiểm soát hoặc local JWT validation |
| Bỏ audience check | Token API khác bị chấp nhận | Kiểm tra aud/resource |
| Dùng introspection thay revocation | Hiểu sai giao thức | Revocation endpoint và introspection là hai thao tác |
| Dùng introspection thay refresh | Không có token mới | Dùng refresh grant khi được phép |
| Bắt mọi lỗi thành 401 | Client retry/auth loop | Phân biệt inactive và AS unavailable |

## 16. Kiểm thử Token Introspection

### 16.1. Ma trận request/response

| Ca kiểm thử | Input | Kết quả mong đợi |
|---|---|---|
| Token active | Token được phát, còn hạn, chưa revoke | `active=true` |
| Token không tồn tại | Chuỗi token ngẫu nhiên | `active=false` |
| Token hết hạn | `exp` đã qua | `active=false` |
| Token bị revoke | Authorization state đánh dấu inactive | `active=false` |
| Token chưa có hiệu lực | `nbf` ở tương lai | `active=false` theo policy |
| Thiếu token parameter | Không có `token` | `invalid_request` |
| Token rỗng | `token` rỗng | Từ chối request |
| Sai token_type_hint | Hint khác loại thực | AS vẫn tra theo quy tắc RFC |
| Requester sai credential | Basic/private_key_jwt sai | Từ chối authentication |
| Requester không được phép | Client hợp lệ nhưng policy cấm | Từ chối authorization |
| Thiếu TLS | Request không qua transport bảo vệ | Bị chặn ở deployment boundary |
| Token sai audience | Token không dành cho RS | Không được chấp nhận tại RS |
| Token thiếu scope | Active nhưng không đủ quyền | RS trả 403 |
| Response không có active | Schema sai | RS từ chối response |
| Response active không phải boolean | Sai kiểu JSON | RS từ chối response |

### 16.2. Ma trận cache và outage

| Ca | Điều kiện | Kết quả cần chứng minh |
|---|---|---|
| Positive cache hit | Token active trong cache TTL | Không gọi AS |
| Cache gần hết TTL | Token còn ít thời gian | Cache không vượt exp |
| Token bị revoke | Cache positive còn tồn tại | Độ trễ revocation nằm trong SLO đã chọn |
| Negative cache | Token inactive | Không tạo cache lâu gây false negative |
| AS timeout | Không có kết quả mới | Không coi active |
| AS 429/503 | Limiter/outage | Backoff và circuit breaker |
| Replay request coalescing | Nhiều thread cùng token | Một introspection request nếu policy cho phép |
| Multi-instance | Các node dùng cùng AS/store | Trạng thái nhất quán theo thiết kế |
| Credential rotation | RS thay secret/key | Token introspection mới xác thực được |

### 16.3. Integration test trong Spring

Với Spring Security Resource Server, cấu hình test AS mock hoặc test server thực để xác minh:

1. Request API có opaque token gọi đúng introspection URI.
2. RS xác thực bằng introspection client credential.
3. Response `active=true` tạo authenticated principal.
4. Scope trong response được ánh xạ thành authority.
5. `active=false` khiến request bị từ chối.
6. Token active nhưng thiếu scope bị 403.
7. Token active nhưng sai audience bị từ chối theo validator/policy.
8. Timeout/5xx được xử lý theo failure policy.
9. Không log access token hoặc Basic credential.

Đối với Spring Authorization Server, test Token Introspection Endpoint thật qua `SecurityFilterChain`, registered client authentication và `OAuth2AuthorizationService`. Không chỉ mock service lookup rồi kết luận endpoint đã được bảo vệ.

## 17. Observability và vận hành

### 17.1. Metrics nên theo dõi

- Introspection requests/second theo requester client.
- Tỷ lệ `active=true` và `active=false`.
- HTTP 400/401/403/429/5xx.
- Latency p50/p95/p99 của endpoint.
- Database/authorization store lookup latency.
- Timeout, connection pool exhaustion và circuit breaker state.
- Cache hit/miss ratio và positive cache age.
- Độ trễ từ revocation tới khi RS từ chối token.
- Tỷ lệ request bị từ chối do audience/scope.
- Credential rotation và authentication failure.

Không đưa raw token, token string, secret hoặc giá trị tùy ý do caller gửi vào metric labels.

### 17.2. Audit event

Có thể ghi event như `TOKEN_INTROSPECTED`, `TOKEN_INTROSPECTION_DENIED`, `INTROSPECTION_CLIENT_AUTH_FAILED` và `TOKEN_REVOCATION_OBSERVED`.

Audit nên chứa correlation ID, requester client ID đã xác thực, token fingerprint/JTI đã pseudonymize khi cần, kết quả active/inactive, thời điểm và policy outcome. Không lưu raw token hoặc Basic header.

### 17.3. Runbook khi introspection latency tăng

1. Kiểm tra RPS theo requester và active/inactive ratio.
2. Kiểm tra DB/authorization store latency, index và connection pool.
3. Kiểm tra network giữa RS và AS, TLS handshake và DNS.
4. Kiểm tra cache hit ratio và TTL.
5. Kiểm tra client retry storm, timeout và circuit breaker.
6. Xác định lỗi credential rotation hoặc AS deployment.
7. Nếu cần, giảm tải bằng quota/backoff và dùng cache positive còn hiệu lực theo policy.
8. Không chuyển sang fail-open vô điều kiện để làm biểu đồ 5xx giảm.

## 18. Checklist production

- [ ] Introspection Endpoint chỉ cho protected resource/client được xác thực và cấp quyền gọi.
- [ ] Endpoint dùng HTTPS/TLS và RS xác minh certificate của AS.
- [ ] Request dùng POST form với `token` bắt buộc.
- [ ] `token_type_hint` được xem là gợi ý, không phải bằng chứng.
- [ ] Response có `active` kiểu boolean.
- [ ] Inactive response không tiết lộ lý do nhạy cảm.
- [ ] RS phân biệt active với authorization theo audience/scope/tenant.
- [ ] Introspection requester có identity riêng và credential được bảo vệ.
- [ ] Authorization store dùng chung cho issuance, revocation và introspection.
- [ ] HTTP response có `Cache-Control: no-store` và `Pragma: no-cache`.
- [ ] Internal cache có TTL giới hạn theo expiry và revocation SLO.
- [ ] Timeout, retry, circuit breaker và bulkhead được cấu hình.
- [ ] AS outage không tự động biến token thành active.
- [ ] Không gửi token tới introspection URL do caller chỉ định.
- [ ] Không log token, secret, Authorization header hoặc request body nhạy cảm.
- [ ] Có test active/inactive, revoked, expired, invalid requester, wrong audience/scope và outage.
- [ ] Đo được latency, active ratio, errors, cache hit và revocation propagation.

### Kiến thức cốt lõi

**OAuth 2.0 Token Introspection (RFC 7662) cho phép một protected resource hỏi Authorization Server về trạng thái và metadata của token.** Request gửi token qua POST tới endpoint được bảo vệ; AS xác thực requester và trả JSON có trường bắt buộc `active`. Nếu token inactive, response nên tối thiểu để tránh tiết lộ lý do.

Trong Spring Authorization Server, Introspection Endpoint sử dụng authorization/token state do `OAuth2AuthorizationService` quản lý. Trong Spring Security Resource Server, opaque token support dùng introspector để xác minh trạng thái và tạo principal/authorities. Introspection đặc biệt hữu ích cho opaque token và use case cần trạng thái tập trung; đổi lại, nó tạo network dependency và cần timeout, cache, rate limit cùng failure policy. **`active=true` chỉ xác nhận trạng thái token; Resource Server vẫn phải kiểm tra audience, scope và quyền nghiệp vụ trước khi cho phép truy cập.**

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
