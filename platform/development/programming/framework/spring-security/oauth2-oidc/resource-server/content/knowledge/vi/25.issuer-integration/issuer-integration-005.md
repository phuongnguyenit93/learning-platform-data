# Không dùng ID token hoặc UserInfo như bước thay thế xác minh access token

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, một ứng dụng thường tích hợp với Authorization Server (AS) hoặc OpenID Provider (OP) để xác thực access token và áp dụng phân quyền. Vì OAuth 2.0 và OpenID Connect (OIDC) cùng xuất hiện trong một luồng đăng nhập, developer dễ nhầm rằng **ID token**, **UserInfo response** và **access token** đều là những cách tương đương để chứng minh quyền truy cập API.

Đó là một nhầm lẫn có thể tạo lỗ hổng nghiêm trọng. **ID token** phục vụ **Relying Party (OIDC client)** xác nhận sự kiện đăng nhập/danh tính người dùng; **UserInfo endpoint** phục vụ client lấy claims về người dùng; **access token** là credential mà **Resource Server** phải kiểm tra khi có request vào protected resource. Việc một ID token hợp lệ hoặc UserInfo trả về `sub` của người dùng **không chứng minh** Bearer access token gửi tới API đã được phát hành cho API ấy, còn hiệu lực hoặc có scope cần thiết.

> **Nguyên tắc chính:** Resource Server xác thực và phân quyền dựa trên **access token phù hợp với tài nguyên của mình**, bằng JWT validation hoặc OAuth 2.0 token introspection (hoặc cơ chế access-token validation tin cậy được giao thức/hợp đồng hỗ trợ). Không thay bước đó bằng cách kiểm ID token, gọi UserInfo, hoặc chỉ kiểm thông tin hồ sơ người dùng.

Bài học nằm trong chương **Tích hợp nhà phát hành**. Ta sẽ xác định các trust boundary trong OAuth 2.0/OIDC, phân biệt mục đích của từng token, lý do một issuer có thể cấp token với nhiều audience khác nhau, cách cấu hình Spring Security Servlet/WebFlux, các trường hợp ngoại lệ cần thiết kế riêng, và chiến lược kiểm thử chống **token substitution**, **audience confusion**, **confused deputy** và lỗ hổng phân quyền đối tượng.

## 1. Ba thành phần: access token, ID token và UserInfo

### 1.1. So sánh nhanh

| Thuộc tính | **OAuth 2.0 access token** | **OIDC ID token** | **UserInfo response** |
|---|---|---|---|
| Mục đích | Cho client gọi protected resource được AS cấp quyền | Cho Relying Party xác minh sự kiện đăng nhập và nhận định danh | Cung cấp claims về End-User cho Relying Party |
| Đối tượng tiếp nhận dự kiến | **Resource Server/API** được chỉ định | **OIDC client**, thông thường audience là `client_id` | **OIDC client** đã gọi UserInfo endpoint |
| Nơi thường được gửi | `Authorization: Bearer ...` tới API | Token response trả về client, được client validate | HTTP response từ UserInfo endpoint |
| Định dạng | Opaque hoặc JWT, tùy AS/token profile | **JWT** theo OIDC Core | JSON object (có thể có dạng ký/mã hóa tùy hợp đồng) |
| Kiểm tra quan trọng | Signature hoặc `active` từ introspection; `iss`, `aud`, time, token type, scopes | Signature, `iss`, `aud=client_id`, time, `nonce`/`azp` và ràng buộc OIDC tương ứng | Nguồn HTTPS tin cậy, access token của UserInfo và `sub` nhất quán với ID token tại RP |
| Thể hiện quyền gọi Orders API? | Có thể, nếu token được cấp cho API và mang scope/quyền phù hợp | **Không tự động** | **Không** |
| Có thể đại diện service không có người dùng? | **Có** (client credentials) | Thông thường không xuất hiện ở client-credentials flow | Thông thường không phù hợp với flow không có End-User |

**Điểm phân biệt quyết định là audience/mục đích**: cùng một issuer có thể phát hành một ID token hợp lệ cho `orders-web-client` và một access token hợp lệ cho `orders-api`. Resource Server phải biết nó được phép nhận loại credential nào. Chữ ký đúng của ID token chỉ chứng minh token đó do OP phát hành; không tự biến nó thành access token của API.

### 1.2. Hình dung bằng hai hành trình

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant RP as Web App / OIDC Client
    participant OP as OpenID Provider
    participant API as Orders Resource Server
    U->>RP: Chọn Đăng nhập
    RP->>OP: Authorization Code + PKCE flow
    OP-->>RP: Authorization code
    RP->>OP: Đổi code tại token endpoint
    OP-->>RP: ID token + access token (và có thể refresh token)
    RP->>RP: Validate ID token cho client identity/session
    opt Cần claims người dùng
        RP->>OP: GET /userinfo + access token phù hợp
        OP-->>RP: UserInfo claims
        RP->>RP: Kiểm tra sub khớp ID token
    end
    RP->>API: GET /api/orders + Bearer access token
    API->>API: Validate access token cho orders-api
    API->>API: Kiểm scope + tenant + ownership
    API-->>RP: Dữ liệu nếu được phép
```

Trong sơ đồ, client có thể thực hiện **cả ID token validation và API access-token validation**, nhưng mỗi việc trả lời câu hỏi khác nhau. API **không thừa hưởng** kết quả ID-token validation ở RP trừ khi kiến trúc có một cơ chế chuyển đổi/delegation danh tính riêng, được bảo vệ và mô tả rõ. Việc RP từng đăng nhập thành công không làm Bearer token gửi tới API tự nhiên hợp lệ.

### 1.3. Phân biệt hai câu hỏi

OIDC client hỏi:

```text
Người dùng đã được OP xác thực cho client của tôi chưa?
ID token này có đúng issuer, audience, nonce và thời hạn không?
```

Resource Server hỏi:

```text
Bearer access token này đã được issuer đáng tin xác minh chưa?
Token có được cấp cho CHÍNH API này không?
Token còn hiệu lực và có scope tương ứng không?
Principal có quyền với đối tượng/tenant được yêu cầu không?
```

Không thể lấy câu trả lời cho câu hỏi thứ nhất làm kết luận cho câu hỏi thứ hai.

## 2. Vì sao ID token không thay access token?

Theo **OpenID Connect Core 1.0**, ID token là một JWT chứa claims về sự kiện authentication của End-User tại OP và được phát hành cho Relying Party. Trong phần lớn luồng đăng nhập, `aud` của ID token chứa **OIDC client ID**, ví dụ `orders-web-client`.

Một ID token minh họa:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": "orders-web-client",
  "iat": 1893459000,
  "exp": 1893459600,
  "auth_time": 1893458900,
  "nonce": "nonce-created-by-rp"
}
```

Payload này chỉ có mục đích minh họa, không phải JWT đã được ký; timestamps không đại diện cho token thực tế. Token này có thể **hoàn toàn hợp lệ khi OIDC client kiểm tra** `aud=orders-web-client`, nhưng **không hợp lệ làm access token cho Orders API** vốn yêu cầu `aud=orders-api`.

### 2.1. Hai token của cùng một issuer, cùng một user

ID token:

```text
typ: JWT (ID token)
iss: https://identity.example.com/realms/shop
sub: user-842
aud: orders-web-client
```

Access token cho API:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "orders-web-client",
  "iat": 1893459000,
  "exp": 1893459600
}
```

Cả hai có thể được OP/AS ký bằng **cùng bộ khóa**. Nếu Resource Server chỉ xác minh chữ ký và `iss` nhưng bỏ `aud` hoặc token type/profile, nó có thể nhận **ID token của web client** như một API credential. Đây là một biến thể của **cross-JWT confusion/token substitution**.

### 2.2. Signature valid không đồng nghĩa đúng token type

```text
JWT signature valid
        |
        +-- Issuer thuộc tập tin cậy
        |
        +-- Nhưng audience = orders-web-client
        |
        v
KHÔNG ĐỦ để gọi Orders API.
```

Chữ ký xác minh **nguồn phát hành và tính toàn vẹn** của claims, không chứng minh rằng mọi nơi đều được sử dụng token. Audience và token profile đưa thêm ranh giới **ai được phép nhận token đó**.

### 2.3. `sub` không phải quyền truy cập

Khi ID token chứa:

```json
{"sub":"user-842","email":"user@example.com"}
```

thì `sub` xác định subject theo issuer, không phải quyền `orders.read`. Email, tên, ảnh, locale, `preferred_username` và các profile claims cũng không mặc định là quyền dùng API.

Thậm chí với **access token** đã được xác minh, `sub=user-842` không cấp quyền đọc mọi đơn hàng của user khác. Resource Server vẫn phải kiểm tra ownership, tenant, trạng thái và policy của từng object.

### 2.4. ID token validation là việc của OIDC client

OIDC client cần validate ID token, trong đó có:

- Signature/issuer/trust chain theo OP.
- `aud` chứa đúng client ID; xử lý `azp` nếu hợp đồng OIDC yêu cầu.
- `exp`, `iat` và các điều kiện thời gian.
- `nonce` khi request/flow đã sử dụng nonce.
- Các kiểm tra liên quan `auth_time`, `acr`, `amr` nếu client yêu cầu mức xác thực.
- Ràng buộc với authorization response, state/PKCE, redirect URI và client session.

Danh sách trên phục vụ **đăng nhập của client**, không thay danh sách kiểm tra access token của Resource Server.

## 3. Vì sao UserInfo cũng không thay xác minh access token?

OIDC **UserInfo endpoint** là một protected resource do OpenID Provider cung cấp. Relying Party có thể gọi nó bằng access token phù hợp để nhận những claims người dùng đã được phép chia sẻ.

Ví dụ:

```http
GET /userinfo HTTP/1.1
Host: identity.example.com
Authorization: Bearer access-token-for-userinfo
```

Response:

```json
{
  "sub": "user-842",
  "name": "Example User",
  "preferred_username": "example-user",
  "email": "user@example.com",
  "email_verified": true
}
```

Điều này có thể phù hợp để RP hiển thị tên/ảnh/email sau khi user đăng nhập, tùy scopes, consent và hợp đồng OP. Nhưng **nó không chứng minh bearer credential đã được cấp cho Orders API**.

### 3.1. UserInfo kiểm token cho UserInfo resource, không phải mọi API

Giả sử token A được OP chấp nhận ở `/userinfo`:

```text
GET https://identity.example.com/userinfo
Authorization: Bearer token-A
-> 200 {"sub":"user-842"}
```

Từ sự kiện này, Orders API **không được kết luận**:

```text
token-A có aud=orders-api;
token-A có SCOPE_orders.read;
token-A được phép thao tác trên order-123;
token-A là access token theo profile API yêu cầu;
token-A chắc chắn vẫn hợp lệ tại thời điểm thao tác sau.
```

UserInfo endpoint có policy riêng. Một token có thể được dùng cho UserInfo mà không được cấp quyền ở Orders API. Ngược lại, access token dùng trong machine-to-machine API có thể hoàn toàn hợp lệ dù **không gọi UserInfo được** vì không đại diện End-User.

### 3.2. UserInfo là nguồn hồ sơ, không phải introspection endpoint

Hai HTTP endpoint có hợp đồng khác nhau:

| API tại nhà phát hành | Mục đích | Kết quả đặc trưng |
|---|---|---|
| **UserInfo (OIDC)** | Trả claims về End-User cho Relying Party | `sub`, `name`, `email` và claims được cấp |
| **Introspection (RFC 7662)** | Cho protected resource/client đủ quyền hỏi trạng thái và metadata token | `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp` nếu AS cung cấp |
| **Token endpoint** | Đổi authorization code, refresh token, client credentials… thành token | Token response, không phải authorization decision của API |
| **JWKS endpoint** | Công bố public keys để verifier xác minh chữ ký token theo trust config | JWK Set; không phải câu trả lời “token này active?” |

Không gọi `/userinfo` rồi tự suy ra `active=true`, `aud=orders-api` hoặc scope nếu endpoint không cung cấp những bằng chứng ấy. **RFC 7662 introspection** mới định nghĩa hợp đồng hỏi trạng thái của access token.

### 3.3. Quy tắc `sub` của OIDC client

Khi Relying Party dùng UserInfo response, **OIDC Core yêu cầu kiểm tra `sub` của UserInfo khớp chính xác `sub` trong ID token** tương ứng; nếu không, UserInfo claims không được sử dụng.

```text
RP đã validate ID token:  sub = user-842
RP gọi UserInfo:         sub = user-999
=> Không dùng UserInfo claims này.
```

Quy tắc đó bảo vệ **sự liên kết profile claims với người dùng đã đăng nhập tại RP**. Nó **không phải** bước xác thực access token thay cho API. Đừng diễn giải “hai `sub` khớp” thành “scope/audience của Bearer token hợp lệ”.

### 3.4. Rủi ro privacy và tăng tải

Gọi UserInfo cho mọi API request chỉ để “xác thực” có thể:

- Thực hiện network call không cần thiết, tăng latency và phụ thuộc OP availability.
- Thu thập email, profile, phone hoặc PII mà API không cần.
- Khiến logs/metrics vô tình lưu token hoặc UserInfo response.
- Làm lẫn quyền OAuth scope với việc người dùng đồng ý chia sẻ profile claims.
- Gây lỗi cho client-credentials flow không có End-User.

Muốn kiểm tra token, dùng **access-token verification**; muốn hiển thị profile cho client, dùng UserInfo theo OIDC đúng mục đích và tuân thủ consent/data minimization.

## 4. Luồng sai: dùng ID token làm Bearer access token

Ví dụ client gửi nhầm:

```http
GET /api/orders/ORD-123 HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_FOR_WEB_CLIENT
```

Nếu Resource Server làm:

```text
parse token -> decode JWT -> signature valid -> read sub
-> tạo Authentication(user-842) -> allow
```

thì API đã thiếu **ràng buộc audience/token purpose**. Một ID token được phát cho web client có thể được gửi vào API và được hiểu là chứng chỉ cấp quyền. Nguy cơ tăng lên khi một hệ thống có nhiều clients cùng issuer và dùng chung JWKS.

### 4.1. Đường xác thực đúng

```mermaid
flowchart TD
    A["Authorization: Bearer credential"] --> B{"Access-token profile được API hỗ trợ?"}
    B -->|"Không"| X["Reject authentication"]
    B -->|"JWT access token"| C["JwtDecoder với issuer/key source tin cậy"]
    B -->|"Opaque access token"| D["OpaqueTokenIntrospector với AS tin cậy"]
    C --> E{"Signature, iss, aud, time,<br/>type/profile hợp lệ?"}
    D --> F{"active + resource/audience<br/>và metadata contract hợp lệ?"}
    E -->|"Không"| X
    F -->|"Không"| X
    E -->|"Có"| G["Authenticated Authentication"]
    F -->|"Có"| G
    G --> H{"Required scope/authority?"}
    H -->|"Không"| Y["403 / deny"]
    H -->|"Có"| I{"Tenant, owner và object policy?"}
    I -->|"Không"| Y
    I -->|"Có"| J["Cho phép xử lý"]
```

ID token không đi vào nhánh này chỉ vì nó là một JWT có chữ ký. Với API chấp nhận JWT access token theo một profile cụ thể như **RFC 9068**, verifier có thể yêu cầu thêm `typ=at+jwt` hoặc các profile constraints khác. Dùng đúng hợp đồng của Authorization Server; không dựa hoàn toàn vào tên file, hình dạng ba phần hay một claim do caller tự khai.

### 4.2. `at_hash` trong ID token cũng không thay xác minh access token

Trong một số luồng OIDC, ID token có claim `at_hash` để Relying Party kiểm tra sự liên kết giữa access token và ID token theo quy tắc của OIDC. Nhưng `at_hash`:

- Không chứng minh access token được cấp cho `orders-api`.
- Không thay `aud`/`scope`/issuer/time/active checks của Resource Server.
- Không có nghĩa ID token là access token.
- Không tự tạo permission trên dữ liệu nghiệp vụ.

`at_hash` thuộc kiểm tra token binding ở phía **OIDC client** theo flow phù hợp. API vẫn phải xác thực **access token được trình cho API**.

### 4.3. Trường hợp đặc biệt cần thiết kế riêng

Một số hệ thống có giao thức **đã thiết kế rõ** để dùng một identity assertion hoặc ID-token-like JWT cho một service cụ thể. Điều đó không có nghĩa nên coi nó là OAuth 2.0 access token. Nếu chấp nhận kiểu assertion ấy, cần định nghĩa một **authentication protocol riêng**: issuer, audience chính xác của service, replay prevention, nonce/challenge khi phù hợp, thời hạn, purpose, caller binding, permissions và migration rules.

Không âm thầm bật “accept ID token as API Bearer” chỉ vì một SDK gửi nhầm token. Nếu mục đích là delegated API access, giải pháp chuẩn thường là yêu cầu **access token đúng audience** hoặc **token exchange** qua Authorization Server được tin cậy.

## 5. Access token là gì và Resource Server phải kiểm tra gì?

OAuth 2.0 access token là credential dùng truy cập protected resources. **Định dạng không bắt buộc là JWT**: token có thể là một chuỗi opaque/reference token hoặc JWT self-contained, theo cách AS triển khai.

### 5.1. JWT access token

Với JWT access token cho Orders API, API cần kiểm tra:

1. **Nguồn tin cậy:** `iss` khớp issuer đã cấu hình/allowlist, không phải issuer tùy ý từ bearer token.
2. **Chữ ký:** JWS signature hợp lệ bằng public key/key source tin cậy, thuật toán được policy cho phép.
3. **Audience:** `aud` chứa đúng resource identifier, ví dụ `orders-api`.
4. **Thời gian:** `exp`, `nbf`, clock skew và token profile phù hợp; không nhận token hết hạn.
5. **Token purpose/profile:** đây là access token được API chấp nhận, không phải ID token hoặc một JWT khác dùng sai mục đích; có thể cần `typ`/`token_use` theo hợp đồng issuer.
6. **Authorities:** scope/roles/permissions được ánh xạ từ những claims **đã xác minh**, không từ header do client tự gửi.
7. **Business authorization:** user/client/tenant có được thao tác trên đối tượng này không?

Đây là các lớp kiểm tra. Không bước nào được thay bằng `GET /userinfo`.

### 5.2. Opaque access token

Với opaque token, Resource Server không cần — và thường không thể — parse các claims tại chỗ. Nó dùng một `OpaqueTokenIntrospector` gọi introspection endpoint đáng tin theo **RFC 7662**, và nhận principal hoặc lỗi.

Response minh họa:

```json
{
  "active": true,
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.update",
  "client_id": "orders-web-client",
  "exp": 1893459600
}
```

AS có thể không trả mọi field tùy loại token/hợp đồng, nhưng `active` là field bắt buộc của response introspection. Resource Server cần thỏa thuận **token-resource binding** đủ mạnh, đặc biệt audience, issuer và type khi AS có nhiều resources.

`active=true` không đồng nghĩa “được mọi hành động”: token có thể không có scope phù hợp hoặc khác tenant. Ngược lại, nếu introspection thất bại vì AS timeout, **không** tạo một principal có scope mặc định.

### 5.3. Scope, audience và identity giải quyết các câu hỏi khác nhau

| Thuộc tính | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| `iss` | Ai là nhà phát hành được tin cậy? | `https://identity.example.com/realms/shop` |
| `aud` | Token dành cho tài nguyên/recipient nào? | `orders-api` |
| `sub` | Chủ thể là ai trong phạm vi issuer? | `user-842` |
| `client_id` | OAuth client nào liên quan đến token? | `orders-web-client` |
| `scope` | Phạm vi thao tác được cấp? | `orders.read` |
| `tenant_id` (extension) | Tenant nào token gắn với theo hợp đồng? | `tenant-a` |
| Ownership/ACL trong DB | Actor có được truy cập order này? | Order thuộc user trong tenant A |

`email_verified=true` trong ID token/UserInfo không thay được bất kỳ kiểm tra `aud` hoặc `scope` nào ở đây.

## 6. Tại sao các token của cùng issuer dễ bị nhầm?

Trong một IdP triển khai OAuth 2.0 + OIDC, cùng OP/AS có thể phát hành:

- ID token cho browser/desktop/mobile clients.
- Access token cho UserInfo endpoint hoặc một resource khác.
- JWT access token cho Orders API.
- Opaque access token cho Billing API.
- Refresh token để client đổi access token mới.
- Các JWT assertion cho client authentication hoặc token exchange.

Nhiều loại có thể cùng giá trị `iss`, cùng `sub` và được ký bằng cùng khóa. Nếu Resource Server chỉ làm:

```java
if (jwtHasValidSignature && trustedIssuer.equals(jwt.getIssuer())) {
    allow();
}
```

thì chưa chứng minh **token type/audience** đúng. Điều này mở đường **cross-JWT confusion**: một token hợp lệ trong bối cảnh A bị tái sử dụng ở bối cảnh B.

### 6.1. Token substitution

Một ví dụ:

```text
OIDC web client: orders-web
API: orders-api

OP phát ID token:
  aud = orders-web
  sub = user-842
  signature = hợp lệ

Attacker/client gửi ID token vào:
  GET /api/orders/ORD-123

API chỉ kiểm chữ ký + iss + sub:
  -> vô tình coi ID token là bearer access token
```

**Biện pháp:** Resource Server phải kiểm chính xác **audience dành cho API**, token profile và scopes. Với RFC 9068, đây là JWT access token profile riêng; với AS khác, cần hợp đồng tương đương được test.

### 6.2. Confused deputy do token dành cho API khác

Token hợp lệ:

```json
{
  "iss": "https://identity.example.com",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
```

nếu bị Orders API nhận chỉ vì có `scope=orders.read`, API đã dùng một token không cấp cho mình. Scope name có thể trùng giữa resources; **audience/resource binding** mới bảo đảm token được cấp đúng recipient.

### 6.3. UserInfo response substitution

Một RP có thể nhận UserInfo cho user A nhưng lưu claims nhầm vào session user B do token/session mix-up. Vì vậy RP phải kiểm `sub` khớp ID token trước khi dùng claims. Dù match, điều này chỉ nói **UserInfo response gắn với tài khoản đăng nhập đúng tại RP**, không chứng minh API Bearer token có audience, scope hay còn active.

## 7. Spring Security Servlet: xác thực JWT access token đúng cách

Một Orders API dùng **Spring Security Servlet** có thể cấu hình JWT Resource Server:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Trong một số Spring Boot versions, starter/resource server dependency đã kéo các modules security khác phù hợp; cách khai báo có thể rút gọn dựa trên BOM hiện tại. Quan trọng là **Resource Server stack**, không phải OAuth client login stack.

### 7.1. Khai báo issuer và audience

Ví dụ cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
```

`issuer-uri` trỏ tới issuer đã được tin cậy. Với những phiên bản Spring Boot hỗ trợ `audiences`, property này giúp kiểm ràng buộc recipient. Nếu đang ở phiên bản không hỗ trợ hoặc đã cung cấp `JwtDecoder` bean tùy chỉnh, phải tự bảo đảm audience validator thực sự được gắn; **không mặc định chỉ khai YAML là mọi decoder đều kiểm audience**.

### 7.2. Cấu hình HTTP authorization

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            // Ví dụ API thuần Bearer header, không dùng cookie
            // browser làm credential cho các request ghi.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Đây là cấu hình minh họa Spring Security 6.x. Spring Security dựa vào `JwtDecoder` để kiểm access token, rồi map scopes thành authorities như `SCOPE_orders.read`. Các HTTP rules kiểm **authority từ access token đã xác minh**. Không có chỗ nào yêu cầu API gọi UserInfo hoặc nhận ID token.

Vì `securityMatcher("/api/**")` chỉ bảo vệ nhóm URL được chọn, ứng dụng phải có chain khác/fallback để bảo vệ các endpoint ngoài `/api/**`. CORS/CSRF, actuator, health, forward/error dispatch cần chính sách riêng tùy mô hình triển khai.

### 7.3. Validator tường minh khi yêu cầu nghiêm ngặt

Nếu cần kiểm soát JWKS, thuật toán và audience per issuer, có thể tạo một `JwtDecoder`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder ordersJwtDecoder(
        @Value("${app.security.issuer}") String expectedIssuer,
        @Value("${app.security.jwks-uri}") String jwksUri,
        @Value("${app.security.audience}") String expectedAudience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndDefaults =
        JwtValidators.createDefaultWithIssuer(expectedIssuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected resource audience",
                    null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndDefaults, audience));

    return decoder;
}
```

`application.yml` tương ứng:

```yaml
app:
  security:
    issuer: https://identity.example.com/realms/shop
    jwks-uri: https://identity.example.com/realms/shop/jwks
    audience: orders-api
```

`jwks-uri` ở trên là **đường dẫn giả lập**, phải thay bằng URI do issuer cung cấp/đã được thẩm định; đừng tự nối một path bất kỳ vào issuer rồi mặc định đúng. `RS256` chỉ đúng nếu có hợp đồng issuer dùng thuật toán đó; không bật thêm algorithms ngoài nhu cầu để “token nào cũng pass”.

**Quan trọng:** `setJwtValidator(...)` đặt validator mới. Nếu chỉ đặt audience validator mà quên `issuerAndDefaults`, bạn có thể vô tình mất kiểm tra issuer/thời gian. Ví dụ đã gộp chúng. Khi dùng JWT access token profile theo **RFC 9068**, còn cần kiểm tra `typ`/token-use và các yêu cầu profile phù hợp với phiên bản thư viện/AS.

### 7.4. Không biến `JwtAuthenticationToken` thành bằng chứng chỉ vì tự tạo

Anti-pattern:

```java
// Sai: xây Authentication từ claims chưa được decoder xác minh.
Jwt forged = Jwt.withTokenValue(rawBearer)
    .header("alg", "none")
    .claim("sub", request.getParameter("user"))
    .claim("scope", "orders.delete")
    .build();

SecurityContextHolder.getContext()
    .setAuthentication(new JwtAuthenticationToken(forged));
```

`Jwt.withTokenValue(...).build()` có thể dùng trong **test fixture** của một `Jwt` object, nhưng **không xác minh chữ ký**. Production phải dùng `JwtDecoder` đáng tin trong Resource Server authentication flow.

## 8. Spring Security Servlet: opaque access token bằng introspection

Nếu AS phát **opaque token**, Resource Server có thể dùng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Security chain:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Tùy version, Spring Security dùng implementation `OpaqueTokenIntrospector` tương ứng để gọi endpoint và xác thực token. **Đây là token introspection**, không phải UserInfo. Cần client credentials/HTTPS đáng tin, timeout và chính sách `active`/audience/scope.

### 8.1. Introspection response và ánh xạ scope

```json
{
  "active": true,
  "iss": "https://identity.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842",
  "client_id": "orders-web-client"
}
```

Đường opaque resource server thông thường chuyển `orders.read` thành `SCOPE_orders.read`. Nhưng một số AS chỉ trả metadata tối thiểu; Resource Server phải có **hợp đồng access token phù hợp resource**. Nếu yêu cầu kiểm audience và AS trả `aud`, có thể bọc introspector để kiểm.

### 8.2. Decorator không thay thế delegate

```java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class OrdersAudienceIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String audience;

    public OrdersAudienceIntrospector(
            OpaqueTokenIntrospector delegate,
            String audience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.audience = Objects.requireNonNull(audience);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Chỉ nhận principal sau khi delegate đã xác minh token.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object rawAudience = principal.getAttribute("aud");
        boolean matches =
            (rawAudience instanceof String value
                && audience.equals(value))
            || (rawAudience instanceof Collection<?> values
                && values.contains(audience));

        if (!matches) {
            throw new BadOpaqueTokenException(
                "Access token audience is not accepted");
        }
        return principal;
    }
}
```

Decorator chỉ **bổ sung policy** lên kết quả introspection đáng tin. Nó không gọi UserInfo, không tự tạo `active=true`, không thêm `SCOPE_orders.read` khi AS không cấp. Nếu delegate báo inactive/network error, không tạo principal dự phòng.

### 8.3. Token không active và lỗi AS

| Response/trạng thái | Hành vi |
|---|---|
 `{"active":false}` | Authentication thất bại |
 `{"active":true,"scope":"orders.read"}` | Có thể xác thực; tiếp tục resource/authority policy |
 Audience sai | Từ chối theo policy |
 AS timeout/5xx | Không có bằng chứng token active; **fail closed** |
 Response thiếu thông tin bắt buộc theo contract | Từ chối/raise lỗi; không tự đoán |

Lỗi hạ tầng AS không nhất thiết mang ý nghĩa token vô hiệu vĩnh viễn. HTTP status cuối cùng có thể được xử lý khác 401 tùy exception handler, nhưng **không được cho phép request** khi không xác minh được.

## 9. WebFlux: API cũng phải xác minh access token

Trong **Spring WebFlux**, tương đương với Servlet là `SecurityWebFilterChain`/`ServerHttpSecurity`, `ReactiveJwtDecoder` và `ReactiveOpaqueTokenIntrospector`.

### 9.1. JWT Resource Server trong WebFlux

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
    .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Đây là API thuần Bearer header. Nếu browser có cookies/session, cần chính sách CSRF riêng. Decoder reactive vẫn phải kiểm issuer/audience/time/signature/token profile; đừng để một OIDC client ID token được nhận chỉ vì nó là JWT có chữ ký đúng.

### 9.2. Opaque token trong WebFlux

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Spring Security sử dụng `ReactiveOpaqueTokenIntrospector` trả `Mono<OAuth2AuthenticatedPrincipal>`. Đường xác thực hợp lệ là:

```text
Bearer opaque access token
    -> ReactiveOpaqueTokenIntrospector
    -> Mono<OAuth2AuthenticatedPrincipal> (chỉ khi token hợp lệ)
    -> Reactive Authentication
    -> Reactor SecurityContext
    -> authorizeExchange / method/domain authorization
```

Không nên:

```java
// KHÔNG LÀM: UserInfo chỉ trả profile, không phải API token verifier.
return userInfoWebClient.get()
    .uri("/userinfo")
    .headers(h -> h.setBearerAuth(token))
    .retrieve()
    .bodyToMono(UserProfile.class)
    .map(profile -> authenticationWithAllScopes(profile.sub()));
```

Đoạn này dùng UserInfo làm nguồn cấp `SCOPE_` cho Orders API; hoàn toàn thiếu ràng buộc `aud`/token profile/resource-specific scope. Nếu UserInfo response 200, code sai vẫn có thể cấp mọi quyền theo chính sách của mình.

### 9.3. Tránh blocking trong reactive authentication

Không dùng:

```java
return Mono.just(blockingUserInfoCall(token));
```

hoặc:

```java
return introspector.introspect(token).block();
```

trong Netty event loop. Dùng các Spring Security reactive components thích hợp. `Mono` có thể trì hoãn công việc tới subscription; không tự `subscribe()` tách rời security filter, vì lỗi có thể bị bỏ qua và race với logic nghiệp vụ.

## 10. Ứng dụng vừa là OIDC client vừa là Resource Server

Đây là tình huống dễ gây nhầm nhất:

```text
Một Spring Boot application:
  /web/**  : OAuth2 Login / OIDC Relying Party
  /api/**  : OAuth2 Resource Server
```

Ứng dụng có thể:

- Dùng `oauth2Login()` để đăng nhập người dùng browser; Spring Security OAuth client xử lý OIDC ID token và UserInfo.
- Dùng `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` cho các REST endpoints nhận access token.

Hai flow **có thể cùng chung issuer và cơ sở dữ liệu người dùng**, nhưng khác **authentication contract**.

### 10.1. Phân tách bằng nhiều filter chains

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitClientAndResourceSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/login/**",
                "/oauth2/**", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/oauth2/**", "/login/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Mẫu này **minh họa phân tách**, không phải cấu hình đầy đủ mọi endpoint; login callback, authorization-request base URI, CSRF logout, routing, error dispatch, public assets và fallback chain phải được rà soát theo ứng dụng. Quan trọng là browser/OIDC login không tự quyết định quyền của API Bearer.

### 10.2. Session browser không thay Bearer token

Một browser đã đăng nhập `/web/**` có thể gửi `JSESSIONID` tới cùng host. Nếu `/api/**` yêu cầu Bearer access token, **không cho phép API vô tình dùng session Authentication trước đó** để bỏ qua bearer check.

Tương tự, một API request có ID token:

```http
Authorization: Bearer <id_token>
```

không được biến thành authenticated request chỉ vì web login module hiểu ID token đó ở ngữ cảnh OIDC client.

### 10.3. Backend-for-Frontend (BFF) cần phân biệt hai boundary

Trong BFF:

```text
Browser cookie -> BFF session được bảo vệ (OIDC login)
BFF -> downstream Orders API với access token phù hợp
```

BFF có thể kiểm session của browser và gọi API server-side bằng access token lấy từ authorized client. Downstream Resource Server vẫn phải validate **access token dành cho nó**. Nếu BFF chủ định đóng vai proxy tin cậy và dùng một giao thức service-to-service khác, đó là một **trust delegation architecture riêng** cần bảo vệ bằng mTLS/signature/audience/authorization; không được diễn giải UserInfo hoặc cookie session thành access token.

## 11. Kiểm soát token purpose và audience khi tích hợp issuer

Khi onboarding IdP/AS cho Orders API, cần một **hợp đồng access token**, không chỉ metadata “issuer hoạt động”:

1. Issuer URI chính xác của Authorization Server.
2. Access token định dạng JWT hay opaque; có thể hỗ trợ cả hai nhưng phải định tuyến có kiểm soát.
3. Audience/resource identifier của Orders API.
4. Scope catalog và semantics: `orders.read`, `orders.create`, `orders.update`, `orders.delete`.
5. Token lifetime, refresh/revocation và key rotation.
6. Thuật toán/ký/chứng thư hoặc introspection endpoint/client credentials.
7. Token type/profile: RFC 9068, vendor-specific `typ`/`token_use`/`scp`, và quy tắc parsing.
8. Identity model: user access token và client-credentials tokens khác nhau thế nào.
9. Tenant/membership/issuer binding.
10. Test contract với các token **đúng và sai audience**, ID token và token dành cho API khác.

### 11.1. Không tự suy issuer từ token chưa xác minh

Resource Server có thể đọc `iss` từ một JWT chưa verify để **chọn decoder trong trusted registry** khi hỗ trợ multi-issuer. Nhưng không được lấy:

```java
String issuer = parseUnverifiedJwt(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
```

mà không whitelist issuer; attacker có thể ép server gọi discovery/JWKS tới URL ngoài ý muốn (**SSRF**) và tạo verifier tin nguồn chưa được quản trị. Decoder được chọn còn phải xác minh chữ ký và **issuer cuối cùng** khớp issuer đã chọn.

### 11.2. Cùng `sub` không có nghĩa cùng identity

Issuer A và B đều có thể cấp `sub=user-842`. Một identity key an toàn bắt đầu từ:

```text
identity = (verified issuer, subject)
```

OIDC ID token và UserInfo cùng `sub` không giải quyết vấn đề cross-issuer/cross-tenant cho API. Cần account linking có kiểm soát, không suy danh tính từ email.

### 11.3. Đừng nâng quyền từ profile claims

Anti-pattern:

```java
if (userInfo.email().endsWith("@example.com")) {
    grant("SCOPE_orders.delete");
}
```

Email domain/UserInfo profile là dữ liệu nhận dạng/hiển thị, không mặc định là authorization policy cho API. Ngay cả email đã xác minh cũng không thay permission trong token và business source-of-truth. Nếu tổ chức dùng group membership/entitlements từ một nguồn authorization riêng, cần contract, freshness, scope, tenant và audit rõ; **không gọi UserInfo rồi tự coi mọi claim là quyền**.

## 12. Machine-to-machine: trường hợp không có ID token/UserInfo

Với **OAuth 2.0 Client Credentials Grant**:

```mermaid
sequenceDiagram
    participant S as Order Worker
    participant AS as Authorization Server
    participant API as Orders API
    S->>AS: client_credentials, client auth, scope/resource
    AS-->>S: access token
    S->>API: Authorization: Bearer access-token
    API->>API: Verify JWT hoặc introspect opaque token
    API->>API: Kiểm aud, scope, service identity, tenant
    API-->>S: Được phép hoặc từ chối
```

Không có End-User tương tác nên flow này thông thường **không có ID token**; `/userinfo` cũng không có ý nghĩa để trả profile của End-User. Nếu Resource Server thiết kế “mọi Bearer token phải có ID token kèm theo” hoặc “phải gọi UserInfo để biết ai đăng nhập” thì có thể làm hỏng machine-to-machine flow và tạo các giải pháp bypass nguy hiểm.

### 12.1. Service principal không phải user principal

Access token có thể chứa:

```json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "client_id": "order-worker",
  "scope": "orders.reconcile",
  "exp": 1893459600
}
```

`sub` có thể không xuất hiện hoặc mang semantics của client tùy AS. Resource Server phải xác minh **client identity/subject theo token profile**, không tự tạo `userId` từ UserInfo để khớp mô hình human login.

### 12.2. Rủi ro gắn service token thành user

Nếu code cố dùng:

```text
access token -> /userinfo -> không có sub -> fallback admin
```

thì service token có thể bị gán một danh tính human hoặc quyền admin không có nguồn tin cậy. Thiết kế đúng là một **service principal model** với scope, resource audience và business ACL riêng.

## 13. 401, 403 và điểm quyết định từ chối

Trong Resource Server, hai loại lỗi phổ biến:

| Tình huống | Tầng | Kết quả thường gặp |
|---|---|---|
| Thiếu Bearer access token | Authentication | 401 |
| Bearer là ID token có `aud=orders-web-client` | Access token validation | **401** vì không phải token hợp lệ cho API |
| JWT chữ ký sai/issuer lạ/expired | JWT decoder | 401 |
| Opaque token `active=false` | Introspection | 401 |
| Token dành cho `billing-api` gửi tới Orders API | Audience validation | 401 |
| Token hợp lệ nhưng thiếu `SCOPE_orders.read` | Authorization | **403** |
| Token hợp lệ nhưng khác tenant/owner | Domain authorization | 403 hoặc 404 theo chính sách |
| UserInfo trả profile thành công nhưng access token sai audience | Access token validation | **401**, không được override bằng profile |
| Introspection endpoint timeout | Infrastructure/authentication unavailable | Phải fail closed; HTTP status tùy exception handling |

Theo RFC 6750, Bearer API có thể dùng `WWW-Authenticate: Bearer` kèm `invalid_token` hoặc `insufficient_scope` trong trường hợp phù hợp. Custom exception handlers/gateway có thể thay body/status, nhưng **không được biến token không hợp lệ thành request authenticated**.

### 13.1. Đừng biến token sai thành “guest logged in”

Anti-pattern:

```java
try {
    Authentication auth = validateAccessToken(token);
    return auth;
} catch (Exception ex) {
    // KHÔNG LÀM: cấp quyền ngay khi validation lỗi.
    return new UsernamePasswordAuthenticationToken(
        "guest",
        null,
        List.of(new SimpleGrantedAuthority(
            "SCOPE_orders.read")));
}
```

Kể cả nếu “guest” chỉ có read scope, một client không có credential hợp lệ đã được cấp quyền. Nếu endpoint thực sự public, khai báo `permitAll` phù hợp và áp data policy, **không giả lập principal có scope**.

## 14. Các lỗi tích hợp issuer thường dẫn đến dùng nhầm token

### 14.1. Frontend gửi ID token thay access token

Một số SDK trả về nhiều fields:

```json
{
  "id_token": "...",
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

Nếu client chọn nhầm `id_token` làm `Authorization: Bearer`, API sẽ 401 khi audience/type validation được thiết kế đúng. Giải pháp là **sửa client để gửi access token đúng resource**, không tắt validation trên API.

### 14.2. API dùng client ID thay resource audience

Trong OIDC:

```text
ID token:     aud = orders-web-client
Access token: aud = orders-api
```

Nếu Resource Server cấu hình `audience=orders-web-client` cho tiện test ID token, nó có thể nhận một token được cấp cho RP, không phải API. Resource Server audience phải lấy từ **API resource registration** hoặc issuer contract, không đơn giản dùng OAuth client ID của giao diện web.

### 14.3. Cấp token chỉ có `openid` rồi kỳ vọng gọi API

`openid` là scope đặc trưng để yêu cầu OIDC authentication. Nó **không mặc định** tương đương `orders.read`. Nếu client cần gọi Orders API, phải yêu cầu token có **resource/audience và API scopes** được AS cho phép.

Có thể dùng `resource` theo **RFC 8707** hoặc AS-specific audience parameter, tùy provider. Không tự giả định mọi IdP cấp access token cho mọi API chỉ vì user đã đăng nhập.

### 14.4. AS không phát JWT access token

Một số IdP phát opaque access token. Client cố parse token như JWT rồi lấy ID token thay thế vì “ID token parse được” là sai. Resource Server phải chọn **opaque introspection** hoặc một hợp đồng xác minh access token được AS hỗ trợ, không đổi mục đích của ID token.

### 14.5. UserInfo bị xem là “kiểm tra active”

Nếu developer viết:

```text
UserInfo trả 200 -> token active -> tạo Authentication
```

thì còn thiếu bằng chứng audience/permission/issuer contract của API. Đây không phải introspection theo RFC 7662, và một UserInfo endpoint có thể có semantics/tolerance khác API. Hãy gọi **introspection endpoint** nếu token opaque và đó là cơ chế AS công bố.

### 14.6. Cùng signing key nên coi mọi JWT như access token

Một issuer có thể ký ID token, access token, logout token, client assertion và security event token bằng những key liên quan. Do đó **ký hợp lệ không thay token-purpose validation**. Với JWT AT theo RFC 9068, resource server kiểm tra profile; với token khác, cần định nghĩa một policy tương đương.

### 14.7. Token exchange bị hiểu nhầm là “thay nhãn”

Khi một client có token cho resource A nhưng cần gọi resource B, không nên sửa `aud` hoặc đổi tên token trên HTTP request. **OAuth 2.0 Token Exchange (RFC 8693)** cho phép một AS được tin cậy phát hành token mới cho target resource theo chính sách. Token mới cần được Resource Server B xác minh. Không phải hệ thống nào cũng hỗ trợ token exchange; phải dùng đúng hợp đồng provider.

## 15. Kiểm thử: phải chứng minh API từ chối ID token

Một test suite Resource Server không chỉ có “JWT access token tốt → 200”. Phải có cả **ID token được ký hợp lệ nhưng sai audience** và **token đúng issuer dành cho API khác**.

### 15.1. Ma trận JWT quan trọng

| Input | Signature | Issuer | Audience/type | Kỳ vọng |
|---|---|---|---|---|
| Access token đúng profile, đủ `orders.read` | Hợp lệ | Tin cậy | `orders-api` | Qua authentication; tiếp tục authz/domain |
| ID token của `orders-web-client` | **Hợp lệ** | Tin cậy | `orders-web-client` | **Từ chối** ở API |
| JWT access token cho `billing-api` | Hợp lệ | Tin cậy | `billing-api` | **Từ chối** |
| Token đúng audience nhưng sai chữ ký | Sai | Tin cậy theo claim | `orders-api` | **Từ chối** |
| Token issuer khác không allowlist | Có thể hợp lệ cho issuer khác | Không tin cậy | `orders-api` | **Từ chối** |
| Token đã hết hạn | Hợp lệ | Tin cậy | `orders-api` | **Từ chối** |
| Token sai `typ`/token purpose theo profile | Hợp lệ | Tin cậy | Có thể đúng audience | **Từ chối** theo token profile |
| Access token đúng, thiếu `orders.read` | Hợp lệ | Tin cậy | `orders-api` | Authenticated nhưng **403** khi đọc |
| Access token đủ scope, order khác owner | Hợp lệ | Tin cậy | `orders-api` | **403/404** theo domain policy |

**Đặc biệt:** ID token test phải có **chữ ký hợp lệ với issuer tin cậy**. Nếu test chỉ dùng một chuỗi rác, bạn chưa chứng minh API kiểm **audience/purpose**, bởi token đã bị từ chối ngay do signature.

### 15.2. Test validator issuer/audience ở mức unit

Ví dụ kiểm audience validator với `Jwt` object được dựng cho test:

```java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenAudiencePolicyTest {

    @Test
    void idTokenAudienceMustNotMatchOrdersApi() {
        Jwt idTokenShapedFixture = Jwt.withTokenValue(
                "synthetic-id-token")
            .header("alg", "RS256")
            .issuer("https://identity.example.com/realms/shop")
            .audience(List.of("orders-web-client"))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(600))
            .subject("user-842")
            .build();

        assertThat(idTokenShapedFixture.getAudience())
            .doesNotContain("orders-api");
    }
}
```

Đây là **test fixture** cho điều kiện audience, **không phải** test signature verification. Test thật của validator nên gọi chính `OAuth2TokenValidator<Jwt>` mà decoder đang dùng và assert failure, thay vì chỉ đọc claim. Và để chứng minh Resource Server từ chối ID token có **chữ ký hợp lệ**, phải chạy decoder/filter với test key.

### 15.3. Integration test với hai JWT được ký bằng cùng issuer key

Thiết lập kiểm thử:

```text
Test issuer:
  https://issuer.test
  JWKS: public key test-K
  Private key test-K chỉ trong test fixture

JWT #1:
  signed with test-K
  iss = https://issuer.test
  aud = orders-api
  typ/profile = access token
  scope = orders.read

JWT #2:
  signed with test-K
  iss = https://issuer.test
  aud = orders-web-client
  typ/profile = OIDC ID token

Resource Server:
  trusted issuer = https://issuer.test
  required audience = orders-api

Expected:
  JWT #1 -> authenticated (và có thể 200)
  JWT #2 -> 401, không đi vào controller
```

Đây là test bắt đúng **token substitution**. Không cần dùng credentials/keys của môi trường production; nên dùng issuer/JWKS test server hoặc một `JwtDecoder` với test key được cấu hình.

### 15.4. `mockMvc().with(jwt())` không chứng minh decoder

Trong Servlet test:

```java
mockMvc.perform(get("/api/orders/ORD-123")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

`jwt()` là **test post processor**: thường tạo Authentication có sẵn, bỏ qua Bearer token decoder và JWT signature/audience validation. Nó phù hợp để kiểm **HTTP/method authorization**, không phù hợp làm bằng chứng API từ chối ID token thật.

Với WebFlux, `mockJwt()` có giới hạn tương tự. Muốn kiểm token type/issuer/audience, gửi **compact Bearer JWT** vào filter chain với decoder và test keys thật.

### 15.5. Test opaque introspection

Mock introspection endpoint trả:

```json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

và:

```json
{
  "active": false
}
```

Kiểm thử:

- `active=true` và audience/scope đúng → tiếp tục authorization.
- `active=false` → không authenticated.
- `active=true` nhưng audience khác → decorator/policy từ chối.
- Introspection timeout/5xx → không tạo principal có scope dự phòng.
- UserInfo endpoint trả 200 nhưng introspection `active=false` → **không** xác thực ở Orders API.
- M2M token active nhưng UserInfo không hỗ trợ → Resource Server vẫn áp contract access token, **không cần UserInfo**.

### 15.6. Test UserInfo/ID token ở RP riêng

Đối với OIDC client, test:

- ID token đúng issuer, audience, nonce/time được chấp nhận khi đăng nhập.
- ID token sai nonce/audience bị từ chối.
- UserInfo `sub` khớp ID token → profile claims được sử dụng theo policy.
- UserInfo `sub` khác ID token → **không dùng claims**.
- UserInfo thất bại → không tự giả định login hay API scope thành công theo flow.

Đây là tests của **OIDC client**, không thay tests JWT/opaque access-token verification ở Resource Server.

## 16. Phân quyền nghiệp vụ: đúng access token vẫn chưa đủ

Access token đã được xác thực:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

không có nghĩa user có thể đọc mọi order. `orders.read` là quyền đối với **loại thao tác**, còn quyền đọc **ORD-123** thuộc tenant khác phải kiểm ở domain.

### 16.1. Service authorization minh họa

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedOrderQueries {

    private final OrderRepository orders;

    public AuthorizedOrderQueries(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView getOrder(
            String orderId,
            Authentication authentication) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            throw new AccessDeniedException(
                "JWT access token required");
        }

        var jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenant = jwt.getClaimAsString("tenant_id");

        return orders
            .findVisibleByIdAndActor(
                orderId, issuer, subject, tenant)
            .orElseThrow(OrderNotFoundException::new);
    }
}
```

Đoạn code minh họa một service nhận Authentication đã được Spring Security xác thực và kiểm scope. `OrderRepository`, `OrderView`, `OrderNotFoundException`, `AccessDeniedException` là các kiểu/domain APIs cần import/định nghĩa. Trong production, service nên lấy actor từ trusted security context thay vì chấp nhận một `Authentication` tùy ý do tầng không tin cậy tự truyền; với method security cần `@EnableMethodSecurity` và lời gọi qua Spring proxy. Nếu dùng opaque token, phải viết adapter principal tương ứng, không ép mọi token về `JwtAuthenticationToken`.

### 16.2. Khi token chứa roles có vẻ “admin”

Đừng làm:

```java
if (idToken.claim("admin") == true ||
    userInfo.groups().contains("admins")) {
    allowDeleteAnyOrder();
}
```

Các role claims từ ID token/UserInfo có thể được OP phát hành cho **mục đích client khác**, không mặc định là quyền API. Nếu API thực sự cần entitlements từ authorization service riêng, phải có hợp đồng trust/audience/tenant, mapping và freshness rõ, chứ không lấy từ hồ sơ OIDC rồi tự tạo authority không giới hạn.

### 16.3. Không che lỗ hổng bằng việc trả 404

Một API có thể trả 404 cho order khác owner để tránh tiết lộ tồn tại tài nguyên. Nhưng đó phải là kết quả của **một policy ownership/tenant thật**, không phải cách né kiểm access token. Token không hợp lệ cần bị từ chối trước khi truy vấn dữ liệu nhạy cảm.

## 17. Tích hợp nhà phát hành: checklist khi nhận SDK hoặc tài liệu IdP

Một hướng dẫn tích hợp đôi khi chỉ cung cấp:

```text
OIDC discovery URL
client_id
client_secret
/userinfo endpoint
authorization endpoint
token endpoint
```

Đó **chưa đủ** để thiết kế Resource Server. Cần yêu cầu thêm:

- API nhận **access token** theo format nào?
- JWT access token có issuer, audience, scope và token type/profile nào?
- JWKS URI nào và thuật toán ký được phép?
- Nếu opaque, introspection endpoint, client authentication và response fields thế nào?
- Access token được cấp cho **resource/audience Orders API** bằng parameter/registration nào?
- `client_credentials` và authorization-code flows phát token khác nhau thế nào?
- Có revocation và TTL/caching recommendations không?
- Token có trường tenant hay permissions không, semantics nào được AS bảo đảm?
- IdP hỗ trợ nhiều issuers/realms/tenants thì trust registry quản lý ra sao?
- Quy trình rotation/offboarding và cách thử token sai audience/ID token là gì?

Không chuyển sang dùng ID token hoặc UserInfo chỉ vì hướng dẫn của nhà cung cấp chưa trình bày access-token validation. Nếu contract thiếu, cần hoàn thiện cấu hình AS/API hoặc chọn một cơ chế xác thực access token được hỗ trợ.

### 17.1. Chuỗi tin cậy của metadata

Với JWT, issuer metadata/JWKS nên được lấy từ **issuer đã được allowlist**. Không cho request tùy ý chọn `iss`/`jwks_uri` rồi tạo decoder mới. Với opaque token, introspection URI và credentials phải đến từ **cấu hình được quản lý**, không từ bearer token hoặc `X-Provider-URL` header.

### 17.2. Tách các điểm có thể thay đổi

```text
OIDC CLIENT:
  authorize + token response
  validate ID token
  optionally call UserInfo
  client login/session

RESOURCE SERVER:
  receive Bearer access token
  validate JWT or introspect opaque token
  create Authentication + authorities
  enforce audience/scope/tenant/ownership
```

Nếu thay đổi IdP làm format UserInfo thay đổi, việc đó không nên khiến API thay chính sách xác thực access token. Nếu AS đổi JWT access-token audience, phải cập nhật Resource Server validators/trust contract, không chỉ sửa OIDC login UI.

## 18. Các anti-pattern và cách sửa

| Anti-pattern | Vấn đề | Hướng đúng |
|---|---|---|
| Gửi ID token làm Bearer token của API | ID token dành cho RP; dễ token substitution | Gửi access token đúng audience/API scope |
| API chỉ verify signature và `iss` | Có thể nhận ID token hoặc JWT của API khác | Kiểm `aud` và token purpose/profile |
| Gọi UserInfo để “validate access token” | UserInfo không phải RFC 7662 introspection | Dùng JwtDecoder hoặc OpaqueTokenIntrospector |
| UserInfo trả `sub` là cấp `SCOPE_orders.read` | Claims profile không phải permission API | Ánh xạ scopes/permissions từ nguồn authorization đáng tin |
| ID token có email domain đúng là đủ quyền | Email không thay issuer/audience/scope/domain policy | Business authorization đúng nguồn |
| Client chỉ yêu cầu `openid` rồi gọi API | OIDC login scope không tự cấp API scope | Yêu cầu token có resource/audience và scopes phù hợp |
| API không hiểu opaque token nên dùng ID token | Sai mục đích credential | Token introspection hoặc profile AS hỗ trợ |
| `at_hash` khớp nên bỏ access-token validation | Chỉ là binding check ở RP theo flow | Resource Server vẫn xác minh access token |
| API dùng OAuth client ID làm audience mặc định | Nhận nhầm ID token dành cho client | Audience/resource ID của API |
| ID token của issuer A được dùng trong tenant B | Issuer/subject/tenant bị trộn | Verify issuer, aud, token profile và tenant ACL |
| JWT raw có `iss` “tin cậy” là đủ | Claim chưa verify do attacker kiểm soát | Trusted registry + verify signature/issuer |
| `Jwt.withTokenValue(...)` là signature test | Test fixture không verify chữ ký | Signed JWT + test decoder |
| `mockJwt()` chứng minh API reject ID token | Mock có thể bypass decoder | Integration test compact signed token |
| Gặp introspection timeout thì gọi UserInfo | Cơ chế khác mục đích, có thể fail-open | Fail closed, xử lý AS availability |
| M2M token không gọi UserInfo được nên gán admin | Không có End-User không phải auth failure để bypass | Xử lý service principal theo access token |
| Caching UserInfo như “token active forever” | Profile cache không phải token-status cache | TTL/revocation policy dựa access token |
| Tắt audience validator để client hết 401 | Mở cửa token substitution | Sửa audience/token issuance ở IdP/client |
| Token có `scope` nhưng object khác owner | Scope chỉ là quyền loại thao tác | Domain policy owner/tenant/state |

## 19. Quy trình xử lý lỗi thực tế

### 19.1. Client nói “đăng nhập được nhưng API 401”

Kiểm tra theo thứ tự:

1. Client đang gửi `access_token` hay `id_token`?
2. Access token có được cấp cho **Orders API** không? `aud`/resource identifier là gì?
3. Issuer/token profile và khóa ký có đúng với Resource Server config không?
4. Token đã hết hạn/chưa có hiệu lực hoặc bị thu hồi chưa?
5. Nếu opaque, API có dùng đúng introspection endpoint/credentials không?
6. Token là JWT AT hay ID token/JWT assertion khác?
7. Có nhầm OAuth client ID và API audience không?

**Không sửa 401 bằng cách** cho API nhận ID token hoặc gọi UserInfo thay decoder.

### 19.2. Client nói “API 403 dù UserInfo có email và tên”

Resource Server có thể đã xác thực access token thành công nhưng:

- Thiếu `SCOPE_orders.read`.
- Scope converter đang dùng prefix khác `SCOPE_`.
- HTTP matcher yêu cầu quyền khác.
- Tenant/owner/ACL không cho phép.
- User/client service identity không có entitlement cần thiết.

UserInfo trả tên/email không làm thay đổi một quyết định 403 có căn cứ. Kiểm tra authorities của **access token đã được xác minh** và domain policy.

### 19.3. ID token của client khác được API chấp nhận

Đây là sự cố an toàn cần xử lý ngay:

1. Xác định Resource Server có đang bỏ audience/token type check không.
2. Cập nhật JWT decoder validators hoặc opaque introspection contract.
3. Bổ sung test ID token ký hợp lệ nhưng `aud` của client.
4. Kiểm tra những APIs khác dùng cùng verifier/issuer/key.
5. Đánh giá logs/audit và thực hiện incident response theo chính sách.
6. Không làm lộ raw tokens hoặc dữ liệu cá nhân trong báo cáo công khai.

### 19.4. UserInfo thành công, access token introspection inactive

Không được chọn kết quả “thành công” của UserInfo để override introspection. Hai endpoints có policy/timing/resource khác nhau, và UserInfo 200 không mang hợp đồng `active=true` của Orders API.

## 20. Tóm tắt bằng một cây quyết định

```mermaid
flowchart TD
    A["Ứng dụng có token từ OIDC/OAuth provider"] --> B{"Đang xử lý vai trò nào?"}
    B -->|"OIDC Client / RP"| C["Validate ID token cho đăng nhập"]
    C --> D{"Cần claims hồ sơ?"}
    D -->|"Có"| E["Gọi UserInfo bằng token phù hợp<br/>và kiểm tra sub khớp ID token"]
    D -->|"Không"| F["Quản lý client session theo chính sách"]
    E --> F
    B -->|"Resource Server / API"| G{"Credential gửi tới API là access token<br/>phù hợp profile không?"}
    G -->|"Không"| X["401: không dùng ID token/UserInfo thay thế"]
    G -->|"Có, JWT"| H["JwtDecoder: signature + issuer<br/>audience + time + type/profile"]
    G -->|"Có, opaque"| I["OpaqueTokenIntrospector:<br/>active + resource metadata"]
    H --> J{"Token hợp lệ cho API?"}
    I --> J
    J -->|"Không"| X
    J -->|"Có"| K{"Scope/authority đủ?"}
    K -->|"Không"| Y["403: thiếu quyền"]
    K -->|"Có"| L{"Owner/tenant/object state đủ?"}
    L -->|"Không"| Y
    L -->|"Có"| M["Cho phép thao tác"]
```

Một OIDC client có thể đồng thời gọi một Resource Server. Nhưng **đường trên và đường dưới không thể hoán đổi**: `ID token → UserInfo` là việc của client; `Bearer access token → JWT validation/introspection → authorization` là việc của API.

## 21. Kết luận

```text
OIDC / OAuth 2.0 TOKEN INTEGRATION

ID TOKEN
  audience thường là client_id
  dành cho Relying Party / đăng nhập OIDC
  validate theo OIDC Core (iss, aud, exp, nonce, ...)
  KHÔNG dùng thay access token của API

USERINFO
  cung cấp End-User claims cho Relying Party
  sub phải khớp ID token khi client sử dụng
  KHÔNG phải RFC 7662 introspection
  KHÔNG tự chứng minh API audience/scope

ACCESS TOKEN
  credential để gọi protected resource
  audience/resource phải đúng API
  JWT: verify signature + issuer + audience + time + type
  Opaque: trusted introspection + active + resource contract
  scope/authority chỉ từ nguồn đã xác minh
  domain: owner + tenant + object-level policy

KHÔNG BAO GIỜ TỰ ĐỘNG:
  ID token valid -> API authorized
  UserInfo returns 200 -> API token valid
  email verified -> SCOPE_orders.delete
  AS timeout -> default authenticated principal
```

**Resource Server phải xác minh access token cho chính mình.** Một ID token có thể hợp lệ đối với OIDC client, nhưng sai audience hoặc token purpose của API; một UserInfo response có thể trả profile chính xác, nhưng không mang hợp đồng xác minh access token của API. Spring Security cung cấp `JwtDecoder` và `OpaqueTokenIntrospector` (cùng các thành phần reactive tương ứng) để thực hiện đúng trust boundary này.

Khi tích hợp nhà phát hành, hãy xác định rõ **access-token profile, issuer, audience, key source/introspection endpoint, scope và tenant policy**. Dùng ID token/UserInfo đúng vai trò của Relying Party, sau đó kiểm thử bằng những token **được ký hợp lệ nhưng sai mục đích** để đảm bảo API không bao giờ nhận nhầm ID token hoặc token dành cho resource khác.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation, UserInfo endpoint, `sub` matching, `nonce` và `at_hash`.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, UserInfo endpoint, `jwks_uri` và metadata.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, scopes, client/Resource Server.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential và HTTP 401/403.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, `aud` và introspection contract.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `sub`, `exp` và claims.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): audience validation, cross-JWT confusion và token substitution.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `typ=at+jwt` và JWT access token requirements.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): xác định protected resource/audience khi xin token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): đổi token cho target service bằng AS tin cậy.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, JwtDecoder và `SCOPE_` mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection và `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder trong WebFlux.
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth/OIDC login ở phía client.
- [Spring Security Reference — OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): quản lý authorized client/access token ở client.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP authorization và `hasAuthority`.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm quyền trên từng tài nguyên sau token validation.
