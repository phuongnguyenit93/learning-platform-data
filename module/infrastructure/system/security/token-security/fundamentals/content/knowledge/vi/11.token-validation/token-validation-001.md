# Validation token ở resource server

Một API nhận yêu cầu `GET /orders/42` với header `Authorization: Bearer eyJ...`. Chuỗi trông giống JWT và payload có `scope: orders.read`, nhưng đó **chưa phải bằng chứng được phép truy cập**. Resource server cần chứng minh token đến từ nhà phát hành được tin cậy, dành cho chính API này, còn hiệu lực và đúng mục đích. **Chỉ sau khi validation thành công** mới được dùng các claims đã kiểm chứng để quyết định quyền trên tài nguyên.

Bài thuộc chương **Token validation** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Trọng tâm là quy trình xác minh **JWT và opaque access token** tại resource server trong OAuth 2.0/OIDC: trust anchor, chữ ký/JWKS, introspection, claims, audience, scope, token type, thời hạn, thu hồi, chống token bị đánh cắp/phát lại và triển khai bằng Spring Security.

## 1. Resource server là ai và chịu trách nhiệm gì?

Trong OAuth 2.0 có các vai trò liên quan:

- **Authorization Server (AS):** cấp access token và quản lý những thông tin cần thiết để kiểm tra token.
- **Client:** nhận token theo grant hợp lệ và trình token khi truy cập tài nguyên.
- **Resource Server (RS):** API chứa tài nguyên được bảo vệ; xác minh access token và thực thi chính sách truy cập.
- **Resource owner / end user:** chủ thể có quyền với tài nguyên, nếu luồng tương ứng liên quan đến người dùng.

OpenID Connect (OIDC) còn định nghĩa **ID token** phục vụ việc client xác nhận kết quả đăng nhập. ID token **không thay thế access token** khi gọi tài nguyên API; refresh token phục vụ xin access token mới tại AS, không phải credential của RS.

```mermaid
flowchart LR
    U[Người dùng] --> C[OAuth Client]
    C -->|Luồng OAuth 2.0 / OIDC| AS[Authorization Server]
    AS -->|Cấp access token| C
    C -->|Gửi token| RS[Orders Resource Server]
    RS --> V{Xác minh token}
    V -->|Không hợp lệ| E[401 / Từ chối]
    V -->|Hợp lệ| P{Kiểm tra quyền trên tài nguyên}
    P -->|Không đủ quyền| F[403 hoặc 404]
    P -->|Được phép| R[Trả dữ liệu / Thực thi tác vụ]
```

Một RS thực hiện hai nhóm công việc khác nhau:

1. **Token validation:** nhận diện credential được chấp nhận, kiểm tra nguồn phát hành, tính toàn vẹn/trạng thái, hạn dùng, loại token, audience; thiết lập principal đáng tin cậy.
2. **Authorization:** dựa trên principal và thông tin quyền đã xác minh để kiểm tra scope, role, tenant, owner, hạn mức, trạng thái đối tượng và các điều kiện nghiệp vụ.

Ví dụ: token có `aud=orders-api` và `scope=orders.read` có thể hợp lệ, nhưng chủ thể không được xem đơn hàng của tenant khác. Validation **PASS** không tự động khiến authorization **PERMIT**.

## 2. Trust anchor: xác định ai được phép phát hành token

RS không thể mở rộng danh sách issuer theo dữ liệu do người gọi cung cấp. Cần bắt đầu từ một **hợp đồng tin cậy được cấu hình trước**:

```yaml
resource_server: "orders-api"
trusted_issuer: "https://id.example.test"
expected_audience: "orders-api"
accepted_token_format: "jwt"
allowed_signing_algorithms: ["RS256"]
required_scope_for_read: "orders.read"
clock_skew_seconds: 30
```

Đây là schema **minh họa**, không phải cấu hình Spring Security có thể dùng nguyên vẹn. Trong hệ thống thật phải định nghĩa rõ issuer cho phép, JWKS/discovery hoặc introspection endpoint, token profile, audience, thuật toán, xử lý nhiều issuer, độ lệch đồng hồ và quyền bắt buộc.

**Tại sao phải pin issuer?** Kẻ tấn công có thể tạo JWT với:

```json
{
  "iss": "https://attacker.example.test",
  "aud": "orders-api",
  "sub": "admin",
  "scope": "orders.admin"
}
```

Nếu RS tự tải JWKS của mọi `iss` trong token và xem khóa ấy là đáng tin, kẻ tấn công chỉ cần tự ký token bằng khóa của mình. **Chữ ký hợp lệ theo khóa của một issuer không được phê duyệt không làm token đáng tin.**

Một chuỗi tin cậy đúng bắt đầu từ **issuer đã cho phép → metadata discovery/JWKS hoặc introspection endpoint đã xác minh → token validation → chính sách RS**. TLS bảo vệ kết nối đến tên miền, nhưng không tự biến một issuer mới thành issuer mà API được phép chấp nhận.

## 3. Bước tiếp nhận credential và nhận diện token type

Yêu cầu Bearer phổ biến:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
Accept: application/json
```

Trong ví dụ, chuỗi token là **placeholder**, không phải token thật. Resource server cần giới hạn kích thước header, kiểm tra cú pháp, từ chối yêu cầu có cách truyền credential mâu thuẫn và xử lý header trùng theo quy tắc server/framework.

| Loại token | Mục đích | RS có nên nhận như access token? |
|---|---|---|
| **JWT access token** | Cho phép truy cập resource server trong phạm vi cấp quyền. | Có, nếu RS hỗ trợ profile JWT và token vượt đầy đủ validation. |
| **Opaque access token** | Credential tham chiếu đến trạng thái/token metadata được AS quản lý. | Có, nếu RS dùng cơ chế xác minh trạng thái tin cậy. |
| **ID token OIDC** | Báo kết quả xác thực danh tính cho client. | **Không.** Token này dành cho client, thường có audience là client ID. |
| **Refresh token** | Dùng tại token endpoint của AS để xin access token mới. | **Không.** Không được dùng thay access token. |

Một chuỗi có ba đoạn phân tách bằng dấu chấm không đương nhiên là access token hợp lệ. JWS, JWE, JWT cho mục đích khác và opaque token cần được xử lý theo **profile mà AS và RS đã thỏa thuận**. Nếu RS hỗ trợ nhiều định dạng, từng nhánh validation phải đạt cùng chính sách; không được “JWT không xác minh được thì tự coi là opaque và cho qua” khi chưa có cơ chế kiểm tra khác.

Bearer token nên truyền bằng header `Authorization` qua TLS, tránh đặt token vào URL query hoặc log. Không cho phép một client khai rằng “tôi đã đăng nhập” thay thế việc xuất trình access token.

## 4. Nhánh JWT: validation không phải decode

Với JWS Compact Serialization, JWT thường có dạng:

```text
base64url(protected_header).base64url(payload).base64url(signature)
```

Payload có thể đọc được mà không cần khóa ký, vì **Base64URL không phải mã hóa bí mật**. JWT cũng có thể được mã hóa dưới dạng JWE; việc giải mã và kiểm chứng phải tuân theo token profile, không tự viết trình phân tích và mật mã đơn giản.

Header và payload minh họa:

```json
{
  "alg": "RS256",
  "kid": "signing-2026-11",
  "typ": "at+jwt"
}
```

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "orders-web",
  "scope": "orders.read",
  "iat": 1795410000,
  "exp": 1795410900
}
```

Với JWT access token theo **RFC 9068**, header `typ` giúp phân biệt JWT access token khỏi các JWT mục đích khác. Validator cần đối chiếu `typ` và profile chính xác theo chuẩn và hợp đồng AS; đừng giả định mọi JWT của một issuer đều dùng được tại API.

### Các điều kiện phải xác minh

| Nhóm | Kiểm tra cần thiết | Lỗi phải xử lý bằng cách từ chối |
|---|---|---|
| Cấu trúc/format | Cú pháp JWS/JWE, kích thước, JSON và kiểu claims. | Token sai cấu trúc, kiểu dữ liệu không hợp lệ. |
| Thuật toán | `alg` nằm trong allowlist, phù hợp loại khóa và profile. | `none`, thuật toán lạ, algorithm confusion. |
| Nguồn khóa | Khóa nằm trong JWKS/nguồn đã được ràng buộc với issuer cho phép. | Khóa từ `jku`/`x5u` tùy ý hoặc issuer lạ. |
| Toàn vẹn | Chữ ký JOSE được thư viện xác minh thành công. | Chữ ký sai, payload/header bị thay đổi. |
| Issuer | `iss` khớp chính xác issuer được tin cậy. | Token của bên phát hành khác. |
| Loại token | Token phù hợp access-token profile; không phải ID token hoặc JWT mục đích khác. | Token substitution/confusion. |
| Thời hạn | `exp`, `nbf` khi có, `iat` và giới hạn tuổi nếu profile/chính sách yêu cầu. | Token hết hạn, chưa có hiệu lực hoặc quá tuổi cho phép. |
| Audience | `aud` chứa đúng định danh RS được phép. | Token của API khác. |
| Quyền cấp ở token | Scope/role theo profile đáng tin, được ánh xạ đúng. | Token hợp lệ nhưng không đủ quyền thao tác. |

Bảng mô tả điều kiện logic; không bắt buộc thư viện phải kiểm tra theo đúng thứ tự hàng. Theo JWT nói chung, một số claim có thể tùy chọn; **RS phải áp dụng các yêu cầu bắt buộc của access-token profile đang hỗ trợ** và không tự coi việc thiếu claim quan trọng là an toàn.

### Kiểm soát thuật toán, `kid` và JWKS

- `alg` là thông tin trong JWT header **do người gửi cung cấp**, không phải lệnh để RS tự chọn một thuật toán bất kỳ. RS cần allowlist được cấu hình.
- `kid` là **định danh chọn khóa** trong tập khóa đã được tin cậy, không chứng minh khóa thuộc issuer nào.
- Không tự động tải URL từ `jku` hoặc `x5u` trong JWT khi chưa có chính sách cho phép nghiêm ngặt; có nguy cơ SSRF/đánh tráo nguồn khóa.
- Không trộn lẫn sai cách khóa HMAC đối xứng và RSA/EC bất đối xứng; phải để thư viện JOSE kiểm tra loại khóa/thuật toán phù hợp.
- JWKS có thể có nhiều public key trong giai đoạn xoay vòng. Nếu gặp `kid` lạ, RS có thể làm mới JWKS có giới hạn từ **nguồn đã xác minh**, nhưng không bỏ qua bước kiểm tra chữ ký.

Chữ ký đúng chỉ có ý nghĩa khi **khóa xác minh lấy từ đúng trust anchor** và token vượt qua tất cả điều kiện còn lại.

## 5. Claims thời gian: `exp`, `nbf`, `iat` và clock skew

JWT dùng **NumericDate**: số giây tính từ Unix epoch, không phải millisecond. Ví dụ `iat=1795410000` và `exp=1795410900` biểu diễn khoảng 900 giây (15 phút), không phải bằng chứng token đang còn hạn ở mọi thời điểm.

| Claim | Ý nghĩa | Quy tắc |
|---|---|---|
| `exp` | Thời điểm hết hạn. | Sau hạn thì không được chấp nhận, xét dung sai nhỏ nếu có quy định. |
| `nbf` | Không hợp lệ trước thời điểm này. | Từ chối trước thời điểm hiệu lực, trừ skew nhỏ được phép. |
| `iat` | Thời điểm phát hành. | Có thể kiểm tra tương quan thời gian và giới hạn tuổi token theo chính sách. |

Một JWT chung có thể không mang tất cả claims trên, nhưng access-token profile và RS thường **đòi hỏi thời hạn hiệu lực hữu hạn**. Đối với JWT access token RFC 9068, cần tuân theo các claims bắt buộc của profile.

*Clock skew* là dung sai nhỏ để chấp nhận lệch đồng hồ giữa AS và RS, **không phải cách kéo dài hạn token tùy ý**. Nếu đặt skew nhiều phút hoặc giờ, token có thể tiếp tục dùng sau khi đáng lẽ đã hết hạn. RS phải đồng bộ đồng hồ và ghi nhận các lỗi có liên quan.

Ca kiểm thử cần bao gồm: `exp` bằng hiện tại, `nbf` trong tương lai, NumericDate sai kiểu (chuỗi thay vì số), `iat` vô lý, token sống quá dài, cache còn kết quả cũ sau `exp`. Không dùng timestamp do client tự gửi làm nguồn thời gian kiểm tra đáng tin.

## 6. Audience và scope: hai phép kiểm tra độc lập

Giả sử API đơn hàng có `expected_audience=orders-api` và `GET /orders/{id}` yêu cầu `orders.read`.

| Audience | Scope | Kết quả |
|---|---|---|
| `orders-api` | `orders.read` | Qua audience/scope; còn phải kiểm tra quyền bản ghi. |
| `payments-api` | `orders.read` | Từ chối vì sai audience, dù scope giống. |
| `orders-api` | `orders.write` | Token có thể hợp lệ nhưng thiếu scope đọc. |
| `["orders-api", "reports-api"]` | `orders.read` | Phụ thuộc hợp đồng đa audience; có thể chấp nhận khi có audience của RS. |
| `orders-api-v2` | `orders.read` | Không khớp chính xác `orders-api`. |

**Audience** xác định bên nhận token, còn **scope** xác định phạm vi được cấp. `aud` trong JWT có thể là chuỗi hoặc mảng chuỗi; RS so khớp giá trị nguyên vẹn và có thể chọn chính sách “phải có audience đích” hoặc “chỉ một audience” nếu AS/RS thống nhất.

Scope thường là tập giá trị nguyên tử. Với profile RFC 9068, `scope` được biểu diễn bằng chuỗi phân tách bằng dấu cách. Một số issuer có `scp` theo schema riêng. RS phải hiểu đúng profile; không dùng `String.contains("orders.read")` vì `orders.read-all` có thể bị hiểu nhầm là `orders.read`.

**Scope không thay quyền trên đối tượng:** token có `orders.read` nhưng người dùng không sở hữu đơn hàng/không được ủy quyền trong tenant vẫn phải bị từ chối. Cũng không thể dùng `azp` hoặc `client_id` thay `aud` của resource server nếu policy yêu cầu audience riêng.

## 7. Nhánh opaque: xác minh qua introspection đáng tin cậy

**Opaque access token** thường là identifier ngẫu nhiên trỏ đến dữ liệu quản lý phía authorization server, không chứa payload mà RS có thể tự giải mã. RS có thể gọi **OAuth 2.0 Token Introspection** (RFC 7662) để kiểm tra token.

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    participant DB as Token Store
    C->>RS: GET /orders/42 + opaque access token
    RS->>AS: Introspection qua TLS, RS xác thực với AS
    AS->>DB: Tra token, hạn dùng, thu hồi, grant
    DB-->>AS: Trạng thái và metadata
    AS-->>RS: active + metadata được phép cung cấp
    RS->>RS: Kiểm tra active, aud, scope và principal
    RS->>RS: Kiểm tra tenant/owner
    RS-->>C: Cho phép hoặc từ chối
```

Ví dụ request introspection với thông tin **placeholder**:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <RS_CREDENTIAL_EXAMPLE>

token=OPAQUE_TOKEN_EXAMPLE&token_type_hint=access_token
```

AS có thể dùng Basic, mTLS hoặc phương thức xác thực RS khác theo hợp đồng; không có yêu cầu mọi AS đều dùng Basic. `token_type_hint` chỉ là gợi ý, không thay kiểm tra loại token.

Phản hồi được bảo vệ qua kết nối đáng tin:

```json
{
  "active": true,
  "client_id": "orders-web",
  "token_type": "Bearer",
  "sub": "user-123",
  "iss": "https://id.example.test",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410900
}
```

Hoặc:

```json
{
  "active": false
}
```

**HTTP 200 từ introspection endpoint không có nghĩa token hợp lệ**; RS phải kiểm tra `active`. Đồng thời `active=true` **không tự cấp quyền**. RS phải kiểm tra các thuộc tính bắt buộc trong hợp đồng: audience, scope, loại token, thời hạn và các dữ liệu cần thiết để kiểm soát truy cập. Nhiều trường là tùy chọn trong RFC 7662; **nếu thiếu căn cứ bắt buộc, hãy từ chối**, không tự suy từ client ID hoặc scope thành audience.

Endpoint introspection phải được lấy từ cấu hình/metadata của AS tin cậy và bảo vệ bằng TLS, xác thực RS, giới hạn quyền tra cứu. Không gọi endpoint do client cung cấp hoặc tin phản hồi introspection từ một nguồn chưa được phê duyệt.

## 8. So sánh nhánh JWT và opaque trong thực tế

| Yếu tố | JWT access token | Opaque access token |
|---|---|---|
| Cơ sở validation | Chữ ký/khóa thuộc issuer + claims. | Trạng thái/metadata từ AS tin cậy. |
| Phụ thuộc AS trên mỗi request | Có thể không cần sau khi cache JWKS hợp lệ. | Thường cần introspection hoặc cache/tra cứu tin cậy. |
| Audience và scope | Lấy từ payload đã xác minh. | Lấy từ introspection/metadata đáng tin. |
| Khả năng thu hồi sớm | Cần denylist, introspection hoặc cơ chế bổ sung. | Có thể cập nhật trạng thái ở AS; cache làm chậm phát hiện. |
| Vận hành | JWKS rotation, thuật toán, thời gian, profile. | Khả dụng introspection, xác thực caller, tải, caching. |
| Replay khi token bị lộ | Bearer JWT vẫn có thể bị dùng lại. | Bearer opaque vẫn có thể bị dùng lại. |

Không thể khẳng định định dạng nào “an toàn tuyệt đối”. Cả hai đều cần **nguồn tin cậy, giới hạn người nhận, phạm vi quyền, vòng đời token, phương án thu hồi và phòng chống đánh cắp/phát lại**.

## 9. Validation khác authorization: cần cả hai

Lấy access token có `sub=user-an`, `aud=orders-api` và `scope=orders.read`. Tại `GET /orders/42`, các câu hỏi là:

1. Token hợp lệ cho API này không? **Validation** kiểm tra issuer, chữ ký/introspection, thời hạn, audience và loại token.
2. Token có scope mà endpoint yêu cầu không? **Authorization mức thao tác** kiểm tra `orders.read`.
3. User An có được xem **đơn hàng 42** không? **Authorization mức dữ liệu** kiểm tra tenant, owner, quan hệ ủy quyền và trạng thái.
4. Tác vụ sau khi được phép có thực sự thành công không? Đây là **kết quả nghiệp vụ**, khác quyết định validation/authorization.

```mermaid
flowchart TD
    A[Request tới resource server] --> B{Credential đúng loại, hợp lệ?}
    B -- Không --> E[401 Unauthorized]
    B -- Có --> C{issuer / chữ ký hoặc active / time / aud đạt?}
    C -- Không --> E
    C -- Có --> P[Principal đã xác minh]
    P --> D{Đủ scope / role yêu cầu?}
    D -- Không --> F[403 Forbidden]
    D -- Có --> G{Có quyền trên resource / tenant?}
    G -- Không --> F
    G -- Có --> H[Thực hiện yêu cầu]
```

Đây là luồng khái niệm, không buộc thứ tự validation nội bộ của thư viện. Với API chủ ý che giấu tài nguyên không được phép xem, `404` đôi khi phù hợp thay `403`. Dù chọn mã nào, dữ liệu **không được trả về hoặc sửa đổi** khi chính sách từ chối.

## 10. Spring Security: xác minh JWT và kiểm tra audience

Với Spring Security OAuth2 Resource Server, `JwtDecoder` xác minh JWT và `SecurityFilterChain` áp dụng chính sách route. Ví dụ Java cho Spring Security 6.x:

```java
@Configuration
@EnableMethodSecurity
public class OrdersSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.test";
        String expectedAudience = "orders-api";

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            boolean accepted = jwt.getAudience() != null
                    && jwt.getAudience().contains(expectedAudience);
            return accepted
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Invalid audience", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
```

Đây là **mẫu minh họa**, đã lược `import` và các thành phần phụ thuộc. Issuer/audience nên lấy từ cấu hình bảo vệ cho môi trường thật. Ngoài issuer, thời hạn và audience, **phải áp dụng kiểm tra token type, thuật toán, khóa và yêu cầu profile access token** thích hợp với hệ thống. Không mặc định rằng việc khai `issuer-uri` hoặc ví dụ decoder này đã bao phủ toàn bộ RFC 9068 trong mọi phiên bản thư viện.

Spring Security thường ánh xạ `scope`/`scp` sang `GrantedAuthority` với tiền tố `SCOPE_`; `hasAuthority("SCOPE_orders.read")` là quy ước Spring, không phải tên scope bắt buộc trong OAuth 2.0.

### Kiểm tra quyền dữ liệu tại service

```java
@Service
public class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView getOrder(UUID id, JwtAuthenticationToken auth) {
        String subject = auth.getToken().getSubject();
        return repository.findVisibleByIdAndSubject(id, subject)
            .map(OrderView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

Đây là đoạn minh họa dựa trên `OrderRepository`/`OrderView` giả định, **không phải implementation đủ cho hệ thống đa issuer/tenant**. Trong hệ thống thật cần ràng buộc principal cùng issuer hoặc định danh nội bộ, tenant, nhóm và những điều kiện nghiệp vụ tương ứng trong chính truy vấn hoặc policy engine.

## 11. Spring Security: xác minh opaque token

Với opaque token, có thể cấu hình resource server gọi introspection endpoint đã tin cậy:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: "https://id.example.test/oauth2/introspect"
          client-id: "INTROSPECTION_CLIENT_ID_FROM_SECRET_MANAGER"
          client-secret: "INTROSPECTION_CLIENT_SECRET_FROM_SECRET_MANAGER"
```

Hai chuỗi `FROM_SECRET_MANAGER` là **placeholder**, không phải thông tin xác thực thực tế và không được hardcode client secret trong file cấu hình sản xuất. Sử dụng hệ thống quản lý bí mật và hạn chế quyền của RS đối với introspection.

SecurityFilterChain cho **lựa chọn opaque thay JWT**:

```java
@Bean
SecurityFilterChain opaqueSecurity(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll()
    );
    http.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()));
    return http.build();
}
```

Đây là **phương án thay thế** cấu hình JWT ở mục 10, không có nghĩa phải đăng ký đồng thời hai filter chain trùng phạm vi. Nếu RS nhận cả JWT và opaque, cần quy định đường chọn validator và thứ tự filter chain rõ ràng.

**Cấu hình introspection mặc định không bảo đảm mọi audience/type/claims nghiệp vụ đã được kiểm tra.** Nếu API cần `aud=orders-api` và xác minh loại token, phải bổ sung logic xác minh metadata từ AS, ví dụ bọc `OpaqueTokenIntrospector`, hoặc sử dụng chính sách/authorization manager đủ thông tin. Không suy rằng `active=true` là đủ.

## 12. 401, 403 và lỗi validation

| Tình huống | Phản hồi thông thường | Ý nghĩa |
|---|---|---|
| Không có token ở route cần xác thực | `401 Unauthorized` | Thiếu credential. |
| JWT sai chữ ký/issuer/audience/loại token/hết hạn | `401 Unauthorized` | Credential không được chấp nhận. |
| Opaque introspection trả `active=false` | `401 Unauthorized` | Token bị coi là không hợp lệ. |
| Token hợp lệ nhưng thiếu scope | `403 Forbidden` | Principal được xác thực nhưng không đủ phạm vi thao tác. |
| Token hợp lệ, đủ scope, sai tenant/owner | `403` hoặc `404` | Không được quyền với đối tượng. |
| Bearer request sai cú pháp | Có thể `400 Bad Request` | `invalid_request` theo RFC 6750 khi phù hợp. |

Ví dụ bearer token bị từ chối:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

Ví dụ token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.approve"
```

Nếu chưa cung cấp token, challenge thông thường không nên ghi `invalid_token` vì không có token để kiểm tra. Tránh tiết lộ raw token, secret, cấu trúc policy hoặc nguyên nhân chi tiết có thể giúp kẻ tấn công trong phản hồi HTTP.

## 13. Thu hồi, cache và key rotation

### JWT tự chứa

- RS có thể xác minh tại chỗ bằng JWKS đã tin cậy. Khi AS **thu hồi quyền** hoặc token, RS không tự biết nếu chỉ kiểm chữ ký và `exp`.
- Có thể dùng access token sống ngắn, denylist, introspection hoặc trạng thái phiên bổ sung nếu yêu cầu thu hồi nhanh.
- JWKS cần cơ chế cache/refresh khi **xoay vòng khóa**; khóa `kid` chưa biết có thể dẫn đến refresh từ endpoint tin cậy có giới hạn, nhưng tuyệt đối không bỏ kiểm chữ ký.
- Khi khóa riêng phát hành token bị lộ, cần loại bỏ khóa liên quan khỏi tập tin cậy và xử lý token cũ, kể cả tác động từ chối token hợp lệ còn hạn.

### Opaque và introspection

- AS có thể đánh dấu token là không còn active. RS phát hiện tại **lần kiểm tra trạng thái mới**, nhưng nếu cache `active=true` thì thu hồi có thể bị trễ.
- Cache TTL không được vượt thời gian token còn hiệu lực và cần phù hợp mức độ chấp nhận độ trễ thu hồi.
- Khi introspection timeout hoặc AS gián đoạn, **không tự gán `active=true`**. Có thể sử dụng kết quả đã xác minh còn hạn hoặc từ chối theo chính sách đã định.
- Cần timeout, rate limit/retry có giới hạn, metrics về lỗi AS, audit và theo dõi cache để tránh quá tải hoặc điểm lỗi đơn.

Refresh token rotation và việc thu hồi refresh token giúp kiểm soát cấp mới access token, nhưng **không mặc định vô hiệu tức thì mọi access token JWT đã phát hành**. Quyền trên tài nguyên có thể đã thay đổi trong khi JWT vẫn chưa hết hạn; thao tác nhạy cảm nên xem xét chính sách mới nhất.

## 14. Bearer token bị đánh cắp vẫn có thể validation thành công

Bearer token là credential mà người nắm giữ có thể trình để được truy cập. Nếu kẻ tấn công đánh cắp token vẫn còn hạn và gửi đến đúng audience, chữ ký/issuer/thời gian đều có thể **PASS**. Validation không chứng minh người đang dùng token chính là chủ tài khoản.

Biện pháp kết hợp:

1. HTTPS/TLS; không truyền token trong URL và không ghi token vào logs/traces/crash report.
2. Bảo vệ nơi lưu token: BFF hoặc cookie phiên `HttpOnly`, `Secure`, `SameSite` cùng CSRF defense ở kiến trúc web thích hợp; ứng dụng native dùng kho bí mật OS.
3. Access token có thời hạn ngắn, scope và audience tối thiểu; kiểm tra owner/tenant ở API.
4. Sender-constrained token khi phù hợp: **DPoP** (RFC 9449) hoặc **mTLS-bound access token** (RFC 8705).
5. Giám sát bất thường, cơ chế thu hồi và chính sách khóa phiên/grant.

Với DPoP, RS phải xác minh proof dành cho method/URL yêu cầu, chữ ký proof, thời điểm, `jti` chống replay, `ath` liên kết access token và ràng buộc khóa `cnf.jkt`; nonce nếu chính sách áp dụng. Với mTLS, RS xác minh chứng chỉ bên gửi khớp thumbprint ràng buộc trong token/metadata. **Không coi token bị ràng buộc như bearer thông thường rồi bỏ qua proof/chứng chỉ.** Nếu có TLS termination tại gateway, chỉ tin thông tin chứng chỉ được chuyển qua kênh nội bộ bảo vệ, không tin header tự khai ngoài Internet.

## 15. Các lỗi thiết kế nguy hiểm

| Lỗi | Hậu quả | Phòng tránh |
|---|---|---|
| Giải mã JWT rồi tin `sub`/`scope` trước khi kiểm chữ ký. | Bên tấn công tự tạo claims. | Chỉ dùng principal sau token validation. |
| Tự chấp nhận mọi `iss` có JWKS qua HTTPS. | Trust issuer do kẻ tấn công tạo. | Issuer allowlist và khóa gắn với issuer. |
| Dùng `kid`/`jku` làm nơi lấy khóa tùy ý. | Key substitution, SSRF. | Chỉ dùng JWKS từ nguồn đã phê duyệt. |
| Cho phép `alg=none` hoặc đổi thuật toán sai quy tắc. | Algorithm confusion và giả mạo. | Algorithm/key type allowlist và JOSE library đáng tin. |
| Không kiểm `aud`. | Dùng token dành cho payments API tại orders API. | Audience bắt buộc theo hợp đồng RS. |
| Nhận ID token/refresh token làm access token. | Token substitution, dùng sai mục đích. | Token type/profile validation. |
| Kiểm `scope` bằng tìm chuỗi con. | Trộn lẫn quyền `orders.read` và `orders.read-all`. | Parse và so sánh scope chính xác. |
| Opaque `active=true` là đủ. | Nhận token sai audience hoặc thiếu quyền. | Kiểm tra metadata và quyền nghiệp vụ. |
| Introspection lỗi thì cho qua. | Fail-open khi hệ thống bảo mật gián đoạn. | Fail closed hoặc cache đã kiểm chứng còn hạn. |
| Token bị lộ qua logging. | Replay credential từ kho log. | Redact header/token, audit bằng mã nguyên nhân. |
| Gateway đã xác thực nên service tin mọi header `X-User`. | Spoof principal khi đi tắt gateway. | Bảo vệ mạng/kênh nội bộ và giới hạn nguồn header tin cậy. |

## 16. Ma trận kiểm thử ở resource server

Bộ kiểm thử tốt cần có unit tests cho authorization **và** integration tests cho validator thật. Giả sử `orders-api` tin `https://id.example.test`, audience `orders-api`, scope GET là `orders.read`.

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| V01 | JWT ký đúng, issuer/aud/time hợp lệ, scope đủ, owner khớp. | Cho phép. |
| V02 | JWT payload có scope đúng nhưng chữ ký sai. | `401`, không tin claims. |
| V03 | Token do issuer lạ ký, audience giống. | Từ chối. |
| V04 | `alg=none` hoặc thuật toán ngoài allowlist. | Từ chối. |
| V05 | Header `jku` trỏ máy chủ ngoài chính sách. | Không tải khóa tùy ý; từ chối nếu không xác minh được. |
| V06 | `exp` đã qua hoặc `nbf` quá xa tương lai. | Từ chối. |
| V07 | `aud=payments-api`. | Từ chối tại `orders-api`. |
| V08 | `aud=["orders-api","reports-api"]`. | Theo chính sách multi-audience đã thống nhất. |
| V09 | ID token hoặc JWT sai token profile được gửi đến API. | Từ chối. |
| V10 | Token đúng audience nhưng thiếu `orders.read`. | `403` nếu token hợp lệ. |
| V11 | Có `orders.read-all`, endpoint cần `orders.read`. | Không tự so khớp chuỗi con. |
| V12 | Scope đủ nhưng đơn hàng khác tenant. | `403`/`404` theo chính sách. |
| V13 | Opaque introspection `active=false`. | Từ chối. |
| V14 | Opaque `active=true` nhưng audience sai. | Từ chối. |
| V15 | Introspection không cung cấp metadata bắt buộc. | Từ chối nếu không có căn cứ khác đáng tin. |
| V16 | AS mất kết nối hoặc JWKS timeout. | Không fail-open. |
| V17 | JWKS rotation tạo `kid` mới. | Chỉ cập nhật khóa từ issuer đã tin và có giới hạn. |
| V18 | Client credentials gọi endpoint chỉ dành cho user. | Từ chối nếu policy yêu cầu user principal. |
| V19 | DPoP-bound token không có proof hoặc proof sai khóa. | Từ chối. |
| V20 | Token Bearer hợp lệ bị phát lại từ máy khác. | Thấy giới hạn của bearer validation; test lớp phát hiện/bảo vệ bổ sung. |
| V21 | Header `Authorization` sai cú pháp hoặc lặp. | Không chấp nhận credential mơ hồ. |
| V22 | Route chưa có chính sách phân quyền. | Default deny. |

**Lưu ý về Spring Security Test:** helper `jwt()` có thể tạo authentication giả lập để kiểm tra route/method security, **không chứng minh chữ ký JWT thực được xác minh**. Cần integration test qua decoder thật với issuer/JWKS và khóa riêng của môi trường test, cùng mock introspection tin cậy cho nhánh opaque. Không dùng khóa ký sản xuất để tạo fixture thử nghiệm.

Trong audit, chỉ ghi trace/request ID, endpoint, mã lỗi như `INVALID_SIGNATURE`/`EXPIRED_TOKEN`/`AUDIENCE_MISMATCH`/`INSUFFICIENT_SCOPE`, issuer/principal **đã xác minh** và kết quả cuối. **Không ghi raw access token, refresh token, ID token hoặc claims chưa được xác minh như danh tính chắc chắn**.

## 17. Tình huống tổng hợp

Giả sử An được cấp JWT access token còn hạn, có `iss=https://id.example.test`, `aud=orders-api` và `scope=orders.read`. Chữ ký được kiểm tra bằng khóa issuer tin cậy.

1. **An đọc đơn hàng của An:** validation PASS, scope PASS, owner PASS → cho phép.
2. **An đọc đơn hàng của Bình:** validation PASS, scope PASS, owner FAIL → từ chối.
3. **An phê duyệt đơn hàng:** validation PASS, thiếu `orders.approve` → từ chối (thường `403`).
4. **Client gửi token này sang payments API:** audience sai → từ chối dù chữ ký đúng.
5. **Client gửi ID token OIDC đến orders API:** sai loại/đối tượng nhận → từ chối.
6. **Quyền đọc của An bị thu hồi trước khi JWT hết hạn:** validation tại chỗ có thể vẫn PASS đến `exp`; kết quả phụ thuộc cơ chế thu hồi/kiểm tra quyền hiện hành.
7. **Bearer token bị đánh cắp:** kẻ tấn công có thể gửi token tới đúng API; validation có thể PASS nếu token vẫn hợp lệ. Cần thêm lớp bảo vệ, giám sát và kiểm soát quyền.

### Tự kiểm tra

1. Tại sao decode JWT thành công không có nghĩa validation thành công?
2. Vì sao không được chọn JWKS từ `iss` hoặc `jku` của token do bên ngoài gửi mà thiếu allowlist?
3. Một token có chữ ký đúng nhưng `aud` dành cho API khác có được chấp nhận không?
4. Tại sao ID token không thể thay access token?
5. Với opaque token, `active=true` đã đủ cho phép truy cập đơn hàng chưa?
6. Khi AS/JWKS không truy cập được, tại sao không được tự bỏ qua kiểm tra?
7. Khi nào cache và key rotation làm thay đổi độ mới của kết quả xác minh?
8. Tại sao bearer token của người dùng có thể bị validation chấp nhận khi nó đã bị đánh cắp?

## 18. Kết luận

- **Resource server phải xác minh access token trước khi tin claims**, dựa trên issuer, khóa hoặc introspection được phê duyệt và chính sách audience/token type của chính API.
- **JWT** cần kiểm tra chữ ký, thuật toán, nguồn khóa, issuer, token profile, thời gian và audience. **Opaque token** cần kiểm tra trạng thái/metadata qua AS tin cậy và hợp đồng validation rõ ràng.
- **ID token và refresh token không dùng làm access token** tại API tài nguyên.
- **Validation và authorization là hai lớp:** token hợp lệ chưa chắc đủ scope, role, tenant, owner hay quyền nghiệp vụ.
- **401** thường dành cho token thiếu/không hợp lệ; **403** thường dành cho token hợp lệ nhưng không đủ quyền.
- **Thu hồi, caching và key rotation** ảnh hưởng cách RS cập nhật trạng thái; không bỏ validation khi hệ thống bảo mật bị lỗi.
- **Bearer token bị đánh cắp vẫn có thể được xác minh thành công**. Cần bảo vệ khi lưu/truyền, giảm scope/audience, giới hạn thời hạn và cân nhắc sender-constrained token.

### Tài liệu chuẩn tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò client/AS/RS và access/refresh token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token và các mã lỗi.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519): JOSE, khóa và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): chống algorithm confusion và token substitution.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token validation và claims.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque/access token metadata và `active`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): an toàn token và phòng chống lạm dụng.
- [RFC 9449 — DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained access tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và validation tại OIDC client.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) và [Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): tích hợp resource server trong Java.
