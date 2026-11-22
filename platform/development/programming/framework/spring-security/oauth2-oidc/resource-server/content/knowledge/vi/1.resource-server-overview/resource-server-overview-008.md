# Ranh giới tin cậy giữa nhà phát hành token, API và dịch vụ phía sau

Trong hệ thống dùng **Spring Security OAuth 2.0 Resource Server**, một access token không phải “thẻ thông hành đi khắp hệ thống”. Token thể hiện một tập phát biểu do một **nhà phát hành đáng tin cậy** đưa ra, dành cho **một hoặc một số tài nguyên cụ thể**, trong **khoảng thời gian có hiệu lực**. Mỗi API nhận token phải tự xác định liệu các phát biểu đó có đủ để cho phép thao tác đang được yêu cầu hay không.

Đây là vấn đề về **ranh giới tin cậy** (*trust boundary*): dữ liệu hoặc danh tính vừa đi từ một miền kiểm soát sang miền khác thì bên nhận phải xác thực những điều mình dựa vào để quyết định. Nó xuất hiện ít nhất ba lần trong ứng dụng nhiều dịch vụ:

1. Nhà phát hành token (Authorization Server/Identity Provider) phát hành thông tin mà API có thể kiểm chứng.
2. Resource Server tiếp nhận yêu cầu từ client, kiểm chứng token và quyết định quyền trên tài nguyên của chính mình.
3. Resource Server gọi API/dịch vụ phía sau, nơi một ranh giới xác thực và phân quyền mới bắt đầu.

Mục tiêu của bài là hiểu rõ **ai tin ai, tin điều gì, vì sao sự tin cậy đó có giới hạn**, và cách thể hiện các giới hạn ấy khi triển khai Spring Security.

## 1. Các chủ thể và trách nhiệm

Xét hệ thống bán hàng với ứng dụng web, một dịch vụ quản lý đơn hàng và một dịch vụ thanh toán:

| Thành phần | Vai trò | Điều thành phần này kiểm soát |
|---|---|---|
| **Client** (web, mobile, backend khác) | Yêu cầu token và gọi API | Cách lưu, gửi token; yêu cầu HTTP mà nó tạo ra |
| **Authorization Server/IdP** | Xác thực chủ thể theo luồng phù hợp, áp chính sách cấp quyền và phát hành token | Khóa ký, metadata, issuer, audience/scope được cấp, thời hạn token |
| **Orders API** (*Resource Server A*) | Bảo vệ dữ liệu và nghiệp vụ đơn hàng | Điều kiện truy cập endpoint, đơn hàng nào được xem/sửa, cách gọi dịch vụ khác |
| **Payments API** (*Resource Server B*) | Bảo vệ dữ liệu và nghiệp vụ thanh toán | Điều kiện truy cập thao tác thanh toán, danh tính gọi đến, quyền đối với khoản thanh toán |
| **Gateway / service mesh** (nếu có) | Định tuyến, bảo vệ đường truyền, có thể xác thực ở lớp biên | Cấu hình mạng, TLS/mTLS, kiểm soát truy cập ở điểm đi qua |

**Authorization Server không phải là mọi API**. Trong OAuth 2.0, nó phát hành access token; Resource Server nhận token để bảo vệ tài nguyên. Một hệ thống có thể dùng cùng một IdP cho nhiều API, nhưng **mỗi API vẫn có quyết định ủy quyền riêng**.

OIDC (OpenID Connect) bổ sung lớp xác thực danh tính dựa trên OAuth 2.0. Đặc biệt cần phân biệt:

| Loại token | Mục đích chính | Bên tiêu thụ dự kiến |
|---|---|---|
| **Access token** | Cho phép truy cập tài nguyên/API trong phạm vi được cấp | Resource Server phù hợp với token |
| **ID token** (OIDC) | Thông báo kết quả xác thực người dùng cho OIDC client | OIDC client, thường có `aud` là `client_id` của ứng dụng |
| **Refresh token** | Xin access token mới theo chính sách cấp phát | OAuth client trao đổi với Authorization Server |

Không dùng ID token thay access token để bảo vệ API. Một ID token có chữ ký hợp lệ vẫn không chứng minh người giữ token được phép gọi `Orders API`; `aud` của nó thường hướng tới ứng dụng client. Cũng không gửi refresh token đến Resource Server như một bearer credential.

### Sơ đồ ranh giới

```mermaid
flowchart LR
    C["Client\nWeb / Mobile"] -->|"1. Nhận access token"| I["Authorization Server / IdP"]
    I -->|"Token A: iss, aud=orders-api, scope"| C
    C -->|"2. Bearer Token A"| A["Orders API\nResource Server A"]
    A -->|"3. Token B hoặc service credential"| B["Payments API\nResource Server B"]
    I -.->|"Metadata / JWKS hoặc introspection"| A
    I -.->|"Metadata / JWKS hoặc introspection"| B
    subgraph T1["Ranh giới 1: Issuer → Orders API"]
      A
    end
    subgraph T2["Ranh giới 2: Orders API → Payments API"]
      B
    end
```

Mũi tên từ IdP đến API trong sơ đồ thể hiện khả năng **xác thực nguồn gốc token** bằng JWKS hoặc introspection; nó không có nghĩa mọi access token do IdP phát hành đều hợp lệ với mọi API.

## 2. Ranh giới thứ nhất: API tin nhà phát hành token đến đâu?

Giả sử client gửi:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Header `Authorization: Bearer ...` chỉ là dữ liệu do phía gọi cung cấp. **Việc có token chưa chứng minh token hợp lệ**. Orders API phải kiểm chứng token theo chính sách được cấu hình trước.

### 2.1. Khi access token là JWT

Ví dụ payload JWT minh họa (đã rút gọn, không phải token có thể dùng thật):

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "iat": 1794600000,
  "nbf": 1794600000,
  "exp": 1794603600
}
```

Một Resource Server dựa vào JWT cần kiểm tra các lớp sau:

1. **Issuer được cho phép**: `iss` khớp chính xác issuer tin cậy mà API được cấu hình. Không chọn một issuer bất kỳ chỉ vì payload tự khai báo issuer đó.
2. **Chữ ký và thuật toán**: chữ ký đúng với khóa được nhà phát hành đáng tin cậy công bố; các thuật toán ký nằm trong tập cho phép. Phải xử lý `kid` như thông tin chọn khóa trong tập JWKS đáng tin cậy, không như địa chỉ nguồn khóa tùy ý.
3. **Thời gian hiệu lực**: `exp` chưa hết hạn, `nbf` đã tới, cùng các kiểm tra thời gian được áp dụng. Có thể cho phép chênh lệch đồng hồ nhỏ có chủ đích.
4. **Đối tượng nhận token (`aud`)**: Orders API chỉ nhận token có audience được cấu hình cho nó, chẳng hạn `orders-api`.
5. **Quyền và ràng buộc nghiệp vụ**: scope/authority đủ cho thao tác; chủ thể có quyền đối với đúng đơn hàng và tenant liên quan.

Các claim thường gặp:

| Claim | Câu hỏi nó giúp trả lời | Lưu ý về ranh giới |
|---|---|---|
| `iss` | Ai phát hành token? | Phải khớp danh sách issuer tin cậy được cấu hình |
| `aud` | Token dành cho API/tài nguyên nào? | Thiếu hoặc sai audience thì không chấp nhận cho API này |
| `sub` | Chủ thể mà token đề cập là ai? | Không đồng nghĩa có quyền với mọi bản ghi; trong môi trường nhiều issuer nên xét cặp `iss` + `sub` |
| `exp`, `nbf`, `iat` | Token có hợp lệ về thời gian? | `iat` hữu ích cho chính sách; không thay thế `exp`/`nbf` |
| `scope` / `scp` | Phạm vi quyền mà issuer cấp? | Là đầu vào cho phân quyền, chưa đủ để cho phép truy cập từng tài nguyên |
| `client_id`, `azp` (nếu có) | Ứng dụng/client liên quan đến token là gì? | Cách biểu diễn phụ thuộc nhà phát hành; không coi là quyền truy cập mặc định |
| `tenant_id`, `roles` (claim riêng) | Ngữ cảnh tenant/role theo hợp đồng hệ thống? | Chỉ tin sau khi xác thực token và kiểm tra chính sách, không nhận từ header client tự đặt |
| `jti` (nếu có) | Định danh token để đối chiếu/audit? | Không tự tạo cơ chế chống phát lại hay thu hồi |

Đối với JWT có `aud` là mảng, API kiểm tra **sự hiện diện của audience cụ thể** trong mảng. Việc token được cấp cho nhiều audience có thể hợp lệ theo hợp đồng phát hành, nhưng cũng mở rộng phạm vi token bị dùng lại; nên ưu tiên audience hẹp phù hợp kiến trúc.

**Chữ ký hợp lệ chỉ chứng minh token không bị chỉnh sửa sau khi được một bên nắm khóa tương ứng ký**. Chữ ký không tự chứng minh token được phát hành cho API hiện tại, token chưa hết hạn hoặc người dùng được quyền xem đơn hàng `ord-123`.

### 2.2. Khóa công khai, discovery và JWKS

Với JWT ký bất đối xứng, IdP giữ khóa riêng để ký; API dùng khóa công khai để xác minh. API thường lấy metadata của issuer và JWKS qua HTTPS:

```text
Issuer tin cậy được cấu hình:
  https://idp.example.com/realms/shop

Metadata OIDC/OAuth:
  issuer       -> tên issuer kỳ vọng
  jwks_uri     -> nguồn khóa xác minh chữ ký

JWT header:
  alg          -> thuật toán ký
  kid          -> khóa cần chọn trong JWKS được tin cậy
```

Ranh giới rất quan trọng: **nguồn cấu hình tin cậy phải xuất phát từ chính API hoặc hệ thống cấu hình**, không xuất phát từ chuỗi `iss`, `jku`, `x5u` hay URL bất kỳ bên trong token chưa xác thực. Không để token của kẻ tấn công chỉ định máy chủ mà API tải khóa xác minh; nếu không, kẻ tấn công có thể dựng một nguồn khóa của riêng mình hoặc gây truy cập mạng ngoài ý muốn.

Các điểm triển khai thực tế:

- Dùng HTTPS, xác minh chứng chỉ TLS và bảo vệ cấu hình issuer/JWK endpoint.
- Cho phép xoay vòng khóa: JWKS có thể chứa nhiều khóa, `kid` giúp chọn khóa phù hợp; đồng bộ cache/refresh theo cơ chế thư viện và kế hoạch xoay vòng của IdP.
- Khống chế thuật toán chấp nhận; không suy luận “token nói `alg=none` thì bỏ qua chữ ký”.
- Sự cố truy cập JWKS có thể ảnh hưởng việc kiểm tra token dùng khóa mới; cần thiết kế tình huống IdP/JWKS tạm gián đoạn.
- Coi JWKS là **khóa công khai để xác thực nguồn phát hành**, không phải danh sách người dùng/quyền truy cập.

### 2.3. Khi access token là opaque token

Access token **không bắt buộc là JWT**. Nếu token là một chuỗi không thể tự giải nghĩa, Resource Server có thể dùng **token introspection** theo thỏa thuận với Authorization Server:

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant I as Authorization Server
    C->>A: Bearer opaque access token
    A->>I: Introspection (xác thực chính API)
    I-->>A: active, scope, aud, sub, iss... theo triển khai
    A->>A: Kiểm tra active + audience + quyền + tài nguyên
    A-->>C: Kết quả API
```

Introspection trả về trạng thái và metadata theo hợp đồng IdP. API vẫn phải kiểm tra audience/phạm vi và phân quyền nghiệp vụ nếu dữ liệu có sẵn; không thể coi một kết quả `active: true` là quyền toàn hệ thống. Thông tin xác thực mà Resource Server dùng tại introspection endpoint phải được quản lý như bí mật dịch vụ.

So sánh hai cách:

| Đặc điểm | JWT tự xác minh | Opaque token + introspection |
|---|---|---|
| Kiểm tra token | Chủ yếu tại API bằng khóa xác minh và claim | API hỏi Authorization Server |
| Phụ thuộc IdP ở thời điểm yêu cầu | Thường ít hơn sau khi có khóa cần thiết | Cao hơn nếu introspection trực tuyến mỗi lần |
| Thu hồi token trước `exp` | Khó có hiệu lực ngay nếu chỉ kiểm chứng JWT offline | Có thể thấy trạng thái thu hồi theo cơ chế introspection |
| Dữ liệu được thấy | Các claim đã chứa trong JWT | Metadata mà introspection endpoint trả về |
| Chi phí/độ trễ | Xác minh mật mã tại chỗ | Gọi mạng, xác thực introspection, cân nhắc cache |

Nếu cache kết quả introspection để tăng hiệu năng, cần chấp nhận độ trễ giữa lúc thu hồi và lúc cache hết hiệu lực. Ngay cả với JWT, muốn khả năng thu hồi gần tức thời thường phải bổ sung thời hạn token ngắn, trạng thái máy chủ hoặc cơ chế khác, thay vì chỉ dựa vào chữ ký.

## 3. Ranh giới thứ hai: Token hợp lệ chưa có nghĩa thao tác được phép

Sau khi Spring Security xác thực bearer token thành công, API biết một số thông tin về chủ thể và quyền được phát hành. Nó **chưa tự biết** liệu chủ thể đó có được xem đơn hàng cụ thể, sửa địa chỉ giao hàng hoặc thực hiện hoàn tiền hay không.

Ví dụ:

```text
Token hợp lệ:
  iss   = IdP tin cậy
  aud   = orders-api
  sub   = user-842
  scope = orders.read

GET /api/orders/ord-123

Đơn hàng ord-123:
  owner = user-901
  tenant = tenant-b
```

Scope `orders.read` có thể cho biết client được gọi chức năng đọc đơn hàng, nhưng **không phải quyền đọc đơn hàng của người khác**. Orders API cần áp dụng chính sách trên thực thể cụ thể, ví dụ: owner là chủ thể hiện tại, hoặc người dùng có quyền nghiệp vụ đủ mạnh trong đúng tenant. Không được chấp nhận `tenant_id` từ URL/header rồi dùng nó làm bằng chứng người gọi thuộc tenant đó.

Có thể xem quyết định cho phép như một phép giao:

```text
Cho phép yêu cầu
  = token được xác thực và dành cho API này
  AND có quyền gọi thao tác (scope/authority)
  AND có quyền trên đối tượng dữ liệu (owner, tenant, trạng thái, nghiệp vụ)
  AND thỏa điều kiện bổ sung (nếu có)
```

### 3.1. HTTP 401 và 403

Hai trường hợp này giúp thể hiện ranh giới:

- **401 Unauthorized**: chưa có chứng thực hợp lệ cho tài nguyên được bảo vệ; ví dụ không có bearer token, token sai chữ ký, sai issuer, sai audience hoặc hết hạn.
- **403 Forbidden**: đã xác thực nhưng thiếu quyền đối với thao tác/tài nguyên, ví dụ thiếu scope hoặc không phải chủ đơn. Một API có thể trả `404` trong một số trường hợp để tránh tiết lộ sự tồn tại của tài nguyên, tùy chính sách.

Thông báo `WWW-Authenticate: Bearer` có thể mang mã lỗi OAuth như `invalid_token` hoặc `insufficient_scope`; không đưa token, secret hoặc thông tin nội bộ nhạy cảm vào phản hồi.

### 3.2. Ví dụ cấu hình Resource Server bằng Spring Security 6

Ví dụ này dành cho API REST nhận bearer **JWT**. API nhận token từ issuer đã cấu hình và yêu cầu audience `orders-api`. Tên issuer và audience phải thay bằng giá trị đúng của môi trường triển khai.

```yaml
# application.yml
app:
  security:
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

```java
@Configuration
@EnableMethodSecurity
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            // Phù hợp cho REST API chỉ nhận Bearer header, không dùng cookie
            // phiên đăng nhập để xác thực các thao tác thay đổi trạng thái.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String requiredAudience) {

        // Lấy cấu hình khóa từ issuer mà ứng dụng đã chủ động tin cậy.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        // Kiểm tra các điều kiện mặc định (trong đó có thời gian)
        // và bắt buộc issuer khớp chính xác.
        OAuth2TokenValidator<Jwt> defaultChecks =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultChecks, audienceCheck));
        return decoder;
    }
}
```

Các lớp trong ví dụ thuộc các package `org.springframework.security.*`, còn `@Configuration`, `@Bean`, `@Value` và `HttpMethod` thuộc Spring Framework. Mẫu cấu hình dùng kiểu API của Spring Security 6; khi áp dụng cần thống nhất với phiên bản đang dùng.

Điều đáng chú ý:

- `oauth2ResourceServer().jwt()` thiết lập xác thực bearer JWT cho API. API không xử lý đăng nhập tương tác hoặc cấp token ở đây.
- `JwtDecoder` được tạo từ **issuer do ứng dụng cấu hình**, sau đó có kiểm tra issuer, thời gian và audience. Với cách tự cung cấp `JwtDecoder`, ứng dụng phải bảo đảm các validator cần thiết đã được gắn đúng.
- Theo quy ước mặc định, Spring Security chuyển scope thành authority có tiền tố `SCOPE_`, chẳng hạn `orders.read` thành `SCOPE_orders.read`. Nếu IdP dùng claim/định dạng khác, cần cấu hình converter tương ứng.
- Cấu hình URL chỉ là phân quyền **ở mức thao tác**. Endpoint còn phải tra cứu quyền với từng đơn hàng, tenant và các điều kiện nghiệp vụ.
- Vô hiệu CSRF trong ví dụ chỉ phù hợp khi endpoint xác thực bằng bearer token được gửi rõ ràng, không dựa vào cookie tự động đính kèm. Nếu ứng dụng đồng thời dùng session/cookie, phải thiết kế CSRF theo luồng đó.

Một đoạn kiểm tra quyền cấp đối tượng ở tầng dịch vụ có thể viết theo ý tưởng:

```java
public OrderDto getOrder(String orderId, Jwt jwt) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    // Chỉ là ví dụ: ứng dụng thực tế có thể sử dụng một policy service
    // để xử lý tenant, vai trò quản trị và trạng thái đơn.
    boolean ownerMatches = order.getOwnerSubject().equals(jwt.getSubject());
    boolean tenantMatches =
        order.getTenantId().equals(jwt.getClaimAsString("tenant_id"));

    if (!ownerMatches || !tenantMatches) {
        throw new AccessDeniedException("Order access denied");
    }

    return toDto(order);
}
```

Ở đây `jwt` là JWT **đã được Spring Security xác thực**, lấy từ ngữ cảnh xác thực của endpoint/controller, không phải một payload người gọi tự giải mã rồi truyền vào. Việc lưu `ownerSubject` phải thống nhất phạm vi định danh: nếu chấp nhận nhiều issuer, đừng coi `sub` riêng lẻ là định danh toàn cục.

### 3.3. Bearer token chứng thực người mang token

Bearer token có đặc điểm: ai nắm được token có thể sử dụng nó, trong giới hạn chính sách API, cho đến khi token hết hiệu lực hoặc bị vô hiệu hóa theo cơ chế tương ứng. API thường **không biết người gửi HTTP hiện tại có chính là chủ thể ban đầu đã nhận token hay không**.

Vì thế cần HTTPS ở các đoạn truyền, tránh ghi token nguyên vẹn vào log, URL, analytics, lỗi hoặc trace; giữ token ngắn hạn và bảo vệ nơi lưu. Khi yêu cầu chống phát lại hoặc ràng buộc token với một bên gửi cụ thể, có thể cân nhắc cơ chế sender-constrained token như mTLS-bound access token hoặc DPoP, nhưng **Resource Server và hạ tầng phải thực sự xác minh bằng chứng ràng buộc đó**. Chỉ thấy claim nói token “đã được ràng buộc” chưa đủ.

## 4. Ranh giới thứ ba: Orders API gọi Payments API

Đây là nơi rất dễ nhầm giữa “dịch vụ nằm trong mạng nội bộ” và “dịch vụ đáng tin cậy”.

Giả sử:

```text
Client ── Token A (aud=orders-api) ──▶ Orders API
Orders API ── ? ──▶ Payments API
```

Orders API đã kiểm tra Token A thành công. Điều đó **không tự động trao cho Orders API quyền sử dụng Token A để gọi Payments API**. Payments API có audience, scope, danh tính được phép và chính sách tài nguyên riêng.

Nếu Orders API chuyển tiếp nguyên Token A trong khi `aud=orders-api`, Payments API phải từ chối token đó vì **token không dành cho mình**, kể cả hai API cùng tin một IdP và cùng sử dụng JWKS.

### 4.1. Ba chiến lược cấp danh tính cho lời gọi phía sau

| Phương án | Khi phù hợp | Payments API nhận diện điều gì? | Ranh giới phải giữ |
|---|---|---|---|
| **Token relay / pass-through** | Token đầu vào **được phép dùng cho Payments API** theo hợp đồng phát hành và chính sách hai API | Chủ thể và quyền đã có trong token được chuyển tiếp | Payments API tự xác minh `iss`, `aud`, thời hạn và quyền; không relay chỉ vì thuận tiện |
| **Token exchange / on-behalf-of** | Payments API cần ngữ cảnh ủy quyền của người dùng nhưng token đầu vào chỉ dành cho Orders API | Token mới dành cho `payments-api`, có thể mang chủ thể người dùng và thông tin bên hành động theo hỗ trợ của IdP | IdP quyết định có cho exchange, target audience và scope nào; Payments API chỉ nhận token mới |
| **Client credentials** | Orders API thực hiện chức năng dịch vụ độc lập với quyền người dùng, ví dụ ghi nhận sự kiện hệ thống | Danh tính service client của Orders API | Chỉ cấp scope máy–máy cần thiết; Payments API không suy đoán người dùng từ service token |

Một chiến lược khác là dùng workload identity hoặc danh tính dịch vụ của nền tảng, miễn phía nhận có cơ chế kiểm chứng phù hợp. **TLS/mTLS bảo vệ kênh hoặc xác thực dịch vụ, nhưng không tự thay thế phân quyền OAuth đối với người dùng/tài nguyên**.

#### Phương án A: Relay token có chủ đích

Chỉ chuyển tiếp access token đầu vào nếu token và hợp đồng giữa các bên cho phép Payments API chấp nhận nó. Ví dụ IdP phát hành token chứa `aud` bao gồm `orders-api` và `payments-api`, đồng thời scope đủ hẹp. Payments API vẫn độc lập xác thực và phân quyền.

Hạn chế: cùng một bearer credential đi qua nhiều dịch vụ làm tăng bề mặt lộ lọt; phạm vi audience rộng hơn có thể làm tăng tác hại khi token bị đánh cắp. Không relay ID token hoặc refresh token đến API phía sau.

#### Phương án B: Token exchange / on-behalf-of

Trong luồng được IdP hỗ trợ, Orders API đổi Token A lấy Token B có audience là Payments API. Ví dụ:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant I as Authorization Server
    participant O as Orders API
    participant P as Payments API
    C->>I: Xin access token cho orders-api
    I-->>C: Token A: aud=orders-api
    C->>O: Yêu cầu + Token A
    O->>O: Xác minh Token A và quyền với đơn hàng
    O->>I: Token exchange Token A, xin aud=payments-api
    I-->>O: Token B: aud=payments-api, scope giới hạn
    O->>P: Gọi API + Token B
    P->>P: Xác minh Token B + quyền thanh toán
    P-->>O: Kết quả
    O-->>C: Kết quả yêu cầu
```

Ở đây **Authorization Server là nơi quyết định** có cho phép đổi token, đổi sang audience nào, scope tối đa là gì và có giữ ngữ cảnh người dùng hay không. Các sản phẩm IdP dùng tên/cơ chế khác nhau; không mặc định mọi IdP đều hỗ trợ RFC 8693 hoặc một luồng on-behalf-of tương đương. Token mới phải được kiểm chứng tại Payments API như mọi access token khác.

Ví dụ kỳ vọng:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["payments-api"],
  "scope": "payments.create",
  "exp": 1794600900
}
```

Payload trên chỉ minh họa `aud` và `scope` của token đích. Cách thể hiện actor/delegation, client và chủ thể có thể khác tùy giao thức, IdP và chính sách; **không suy diễn quyền “đại diện người dùng” chỉ từ `sub`**.

#### Phương án C: Client credentials giữa các dịch vụ

Nếu Orders API gọi Payments API bằng chính danh tính dịch vụ:

```text
Orders API ── client_credentials ──▶ Authorization Server
Orders API ◀── Token S (aud=payments-api; quyền của service) ── IdP
Orders API ── Token S ──▶ Payments API
```

Payments API xác thực Orders API như một **service principal**. Token S không mặc nhiên biểu diễn `user-842`; Orders API phải tự xác minh quyền người dùng trước khi tạo lệnh nội bộ. Nếu Payments API cũng cần biết người dùng đã ủy quyền thao tác, phải thiết kế cơ chế delegation có kiểm chứng thay vì gắn tùy ý `X-User-Id: user-842`.

Một thiết kế an toàn thường tách scope: `payments.create.internal` chỉ dành cho service được cấp phép; `payments.read` dành cho API ngoài nếu cần. Quyền dịch vụ phải đủ hẹp, token có thời hạn thích hợp và bí mật client không xuất hiện trong source code/log.

### 4.2. “Confused deputy” khi API trung gian có quyền lớn

*Confused deputy* xảy ra khi một dịch vụ có quyền mạnh bị dẫn dắt để thực hiện hành động mà bên yêu cầu không được quyền. Ví dụ:

1. Người dùng A được phép xem đơn hàng của A, gọi Orders API với `orderId` của B.
2. Orders API xác thực token nhưng **không kiểm tra quyền trên `orderId`**.
3. Orders API dùng service token có `payments.refund.internal` để yêu cầu Payments API hoàn tiền cho B.
4. Payments API chỉ biết cuộc gọi đến từ Orders API có quyền hoàn tiền; hệ thống đã trao quyền vượt quá ý định.

Cách bảo vệ là phối hợp cả hai ranh giới: Orders API kiểm tra quyền của người dùng trên đúng đơn hàng trước khi gọi, còn Payments API kiểm tra quyền service, loại tác vụ và các quy tắc thanh toán (trạng thái, giới hạn, tính hợp lệ của order/payment). Với thao tác nhạy cảm, cần cân nhắc thêm bằng chứng ủy quyền có thể kiểm chứng, idempotency và audit.

## 5. Gateway, proxy và mạng nội bộ có thay đổi ranh giới không?

Gateway có thể xác minh JWT tại lớp biên, giúp chặn nhiều yêu cầu sai sớm. Tuy nhiên, có hai kiến trúc khác nhau:

**Mỗi Resource Server tự xác minh token:** gateway chuyển bearer token hợp lệ đến từng API; API tự kiểm tra issuer, audience và quyền của mình. Đây là cách giữ ranh giới rõ ràng khi có nhiều đường gọi, nhiều service hoặc nguy cơ đi vòng qua gateway.

**Ủy quyền xác thực cho gateway:** API phía sau tin kết quả xác thực do gateway chuyển tới qua kênh nội bộ được bảo vệ. Khi chọn cách này, cần bảo đảm API **chỉ có thể nhận traffic từ gateway/nguồn được tin**, kết nối được xác thực (ví dụ mTLS hoặc cơ chế tương đương), gateway xóa/ghi đè header danh tính từ client và API phân quyền trên dữ liệu danh tính đã bảo vệ. Nếu người gọi bên ngoài có thể kết nối trực tiếp rồi tự đặt `X-User-Id`, `X-Roles` hoặc `X-Tenant-Id`, ranh giới đã bị phá vỡ.

Ví dụ nguy hiểm:

```http
GET /internal/payments HTTP/1.1
X-User-Id: admin
X-Roles: SUPER_ADMIN
```

Các header này **không phải bằng chứng xác thực** nếu chúng đi thẳng từ client hoặc có thể bị giả mạo trên bất cứ hop nào. Thông tin danh tính chuyển nội bộ nên có hợp đồng nguồn tin cậy rõ ràng, cơ chế chống sửa đổi/giả mạo tại đường truyền và phân tách quyền.

Đừng đồng nhất:

- **Network trust**: có được thiết lập kết nối đến service hay không?
- **Service authentication**: phía gọi thực sự là workload/dịch vụ nào?
- **User/delegation authentication**: ai là người dùng hoặc bên mà dịch vụ đang thay mặt?
- **Authorization**: hành động cụ thể đối với đối tượng cụ thể có được phép hay không?

Một kết nối mTLS có thể trả lời “workload đang kết nối là Orders API”, nhưng không tự trả lời “user-842 được phép hoàn tiền payment-777”.

## 6. Những nhầm lẫn phổ biến qua từng ranh giới

| Tình huống | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Orders API chấp nhận mọi JWT do cùng IdP ký | Token được cấp cho API khác có thể bị dùng nhầm tại Orders API (*token substitution*) | Kiểm tra `iss` **và `aud` dành cho Orders API** |
| API lấy issuer hoặc `jku` từ token chưa kiểm chứng rồi tải khóa | Bên gọi chi phối nguồn khóa và có thể gây truy cập URL ngoài ý muốn | Cấu hình allowlist issuer và endpoint lấy khóa; không đi theo URL tùy ý từ token |
| Dùng ID token làm bearer access token | ID token chủ yếu dành cho OIDC client, sai mục tiêu nhận và semantics | Chỉ chấp nhận access token đáp ứng hợp đồng Resource Server |
| Thấy `SCOPE_orders.read` rồi trả mọi đơn hàng | Scope không quyết định ownership/tenant | Kiểm tra quyền ở mức tài nguyên và nghiệp vụ |
| Orders API chuyển token có `aud=orders-api` sang Payments API | Payments API không phải audience của token | Dùng token exchange hoặc credential phù hợp; Payments API xác minh token nhận được |
| Payments API chỉ tin `X-User-Id` | Header có thể bị client giả mạo hoặc gateway chuyển nhầm | Chỉ tin danh tính có nguồn và kênh xác thực được bảo đảm |
| Nhận mọi token từ bất kỳ tenant/issuer nào | Token hợp lệ ở miền này bị áp vào miền khác | Giới hạn issuer/tenant cho route, đối chiếu tenant với tài nguyên |
| Cho rằng JWT hết quyền ngay khi người dùng logout | JWT offline có thể còn hợp lệ đến `exp` | Chọn TTL, thu hồi/kiểm tra trạng thái khi nghiệp vụ yêu cầu |
| Đưa bearer token vào URL hoặc log | Token có thể lộ qua log, lịch sử, công cụ giám sát | Truyền qua Authorization header; lọc token khỏi telemetry |
| Chỉ dựa vào “service nằm trong VPC” | Đường đi nội bộ không chứng minh danh tính hoặc phân quyền | Xác thực workload và áp chính sách tại mỗi điểm nhận |

### 6.1. Multi-tenant và nhiều issuer

Trong SaaS, API có thể chấp nhận token từ nhiều tenant hoặc nhiều issuer. Đây không phải lý do để tự động tin mọi `iss` có trong JWT.

Một thiết kế nhiều issuer cần:

1. Danh sách/nguồn đăng ký issuer đáng tin cậy theo cấu hình quản trị; chọn bộ xác thực phù hợp từ danh sách đó.
2. Kiểm tra **mỗi** token theo đúng issuer, chữ ký, audience và các điều kiện thời gian.
3. Ánh xạ chủ thể và tenant theo hợp đồng; không lấy `tenant_id` do client tự đặt làm nguồn sự thật.
4. Ràng buộc mọi truy vấn dữ liệu và thao tác nghiệp vụ vào tenant đã xác minh; không dựa vào tiền tố ID hoặc route đơn thuần.

Ví dụ, `sub=user-1` do hai issuer khác nhau phát hành có thể là hai người khác nhau. Ngay cả khi cùng issuer, vai trò và quyền có thể thay đổi theo tenant; mọi quyền tenant phải được giải thích theo chính sách cụ thể.

### 6.2. Hiệu lực của sự tin cậy theo thời gian

Chấp nhận một JWT tại thời điểm T chỉ chứng minh các điều kiện xác thực và chính sách hiện hành phù hợp ở T. Sự kiện xóa người dùng, thay đổi role hoặc thu hồi quyền không luôn phản ánh ngay trong token đã cấp. Do đó hệ thống nhạy cảm có thể cần kết hợp:

- Access token sống ngắn và giới hạn audience/scope.
- Kiểm tra quyền nghiệp vụ dựa trên dữ liệu hiện tại ở API.
- Introspection hoặc cơ chế trạng thái/thu hồi khi chính sách đòi hỏi.
- Quản trị thay đổi khóa và ứng phó khi khóa ký bị lộ.

Chọn TTL ngắn giúp giảm thời gian token bị lộ có thể bị lợi dụng, nhưng không thay thế bảo vệ token và kiểm soát quyền.

## 7. Phân tích ba kịch bản end-to-end

### Kịch bản A — Người dùng xem đơn hàng của mình

```text
1. Client lấy access token:
   iss   = https://idp.example.com/realms/shop
   aud   = orders-api
   sub   = user-842
   scope = orders.read

2. Client gọi GET /api/orders/ord-123 kèm Bearer token.

3. Orders API:
   - xác minh chữ ký / issuer / thời gian / audience;
   - nhận authority SCOPE_orders.read;
   - đọc đơn hàng và kiểm tra user-842 là chủ sở hữu đúng tenant.

4. Nếu tất cả điều kiện đúng: trả dữ liệu được phép.
```

Đầu ra mong đợi khác nhau khi đổi một điều kiện:

| Thay đổi | Kết quả thiết kế kỳ vọng |
|---|---|
| Token sai chữ ký | 401 |
| Token ký đúng nhưng `aud=payments-api` | 401 |
| Token hết hạn | 401 |
| Token hợp lệ nhưng không có `orders.read` | 403 |
| Token hợp lệ, có `orders.read`, nhưng đơn thuộc người khác | 403 hoặc 404 theo chính sách che giấu tài nguyên |
| Token và quyền trên đúng đơn đều hợp lệ | Xử lý yêu cầu và chỉ trả trường dữ liệu được phép |

### Kịch bản B — Đặt hàng cần tạo yêu cầu thanh toán

```text
Client -> Orders API:
  access token A: aud=orders-api, scope=orders.create

Orders API:
  xác minh A, kiểm tra quyền tạo đơn và dữ liệu đơn hàng
  lấy token B phù hợp cho Payments API

Orders API -> Payments API:
  access token B: aud=payments-api,
                  scope=payments.create hoặc quyền service tương ứng

Payments API:
  xác minh B, kiểm tra quyền tạo payment và quy tắc thanh toán
```

Nếu dùng token exchange, Token B có thể thể hiện ngữ cảnh người dùng theo khả năng IdP. Nếu dùng client credentials, Token B chứng thực Orders API và Payments API phải áp quy tắc riêng cho service đó. Trong **cả hai** trường hợp, Payments API không bỏ qua kiểm tra vì cuộc gọi xuất phát từ mạng nội bộ.

### Kịch bản C — Công việc định kỳ đối soát

Một scheduled job không có người dùng đang đăng nhập:

```text
Reconciliation Job
  -> Authorization Server: client_credentials
  <- Token R: aud=payments-api, scope=payments.reconcile
  -> Payments API: Authorization: Bearer Token R
```

Payments API xác thực service principal và chỉ cho phép endpoint đối soát. Không phát minh `sub` của người dùng để “giống” luồng tương tác. Nếu công việc đòi quyền người dùng, cần xác định luồng ủy quyền thích hợp.

## 8. Thiết kế ranh giới trong code và hạ tầng

Một cách thực tế để không đánh mất ranh giới là **đặt quyết định ở đúng nơi sở hữu tài nguyên**:

| Quyết định | Nơi chịu trách nhiệm chính |
|---|---|
| Ai được đăng nhập, client nào có thể xin token? | IdP/Authorization Server |
| Token do issuer tin cậy phát hành, còn hạn, đúng audience? | Resource Server nhận token |
| Endpoint cần scope/authority nào? | Resource Server |
| Người dùng/tenant có quyền trên bản ghi này? | Dịch vụ sở hữu nghiệp vụ và dữ liệu |
| Dịch vụ A có được lấy credential để gọi B? | IdP / hạ tầng workload identity / chính sách cấp quyền dịch vụ |
| Service B có chấp nhận credential từ A không, được làm gì? | Service B |
| Đường truyền/secret/log có an toàn không? | Các bên vận hành kênh, service và nền tảng |

Khi xây dựng luồng mới, nên trả lời được những câu hỏi sau bằng cấu hình và mã nguồn cụ thể:

1. **Issuer nào được tin?** API có allowlist ổn định hay cơ chế quản trị nhiều issuer? Khóa xác minh đến từ đâu?
2. **Token dành cho ai?** API thực sự kiểm tra `aud` nào? Có nhận ID token nhầm không?
3. **Ai được làm gì?** Scope/authority chỉ mở đúng endpoint, còn quyền object và tenant kiểm tra ở đâu?
4. **Đi qua hop tiếp theo bằng danh tính nào?** Relay, token exchange hay client credentials? Quyền, audience, thời hạn có hẹp đủ không?
5. **Nếu token/header bị lấy cắp hoặc giả mạo thì sao?** TLS/mTLS, header sanitation, bí mật, log, hết hạn và thu hồi được xử lý thế nào?
6. **Nếu một tầng bị vượt qua thì tầng sau phản ứng ra sao?** API phía sau còn kiểm tra xác thực và phân quyền độc lập hay không?

## 9. Ghi nhớ về mô hình tin cậy

Một hệ thống OAuth 2.0/OIDC an toàn cần giữ riêng ba câu trả lời:

> **IdP phát biểu** token đại diện cho ai, được cấp trong điều kiện nào và dành cho tài nguyên nào.  
> **Resource Server kiểm chứng** token đó có đáng tin và dành cho mình hay không.  
> **Dịch vụ sở hữu nghiệp vụ quyết định** thao tác trên dữ liệu cụ thể có được phép hay không.

Khi Resource Server lại gọi dịch vụ khác, quy trình bắt đầu lại ở ranh giới mới. **Cùng IdP, cùng mạng nội bộ hoặc cùng chữ ký JWT không làm hai API trở thành một miền quyền duy nhất.**

### Tài liệu tiêu chuẩn để tra cứu sâu

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
