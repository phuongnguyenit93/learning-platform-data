# Ma trận kiểm thử loại token, nguồn tin cậy, endpoint và kết quả mong đợi

## 1. Mục tiêu của ma trận

Một **Spring Security OAuth 2.0/OIDC Resource Server** có thể hỗ trợ nhiều cách xác thực trong cùng hệ thống: JWT access token được xác minh cục bộ, opaque token được kiểm tra qua introspection, token do nhiều issuer phát hành, và thậm chí các cơ chế khác như mTLS hoặc session dành cho những vùng endpoint riêng. Khi ấy, một bài test đơn lẻ kiểu “Bearer hợp lệ thì trả 200” không đủ bảo vệ hệ thống.

Lỗi bảo mật thường nằm ở **đường giao nhau**:

- JWT đúng chữ ký nhưng **được phát hành cho API khác**.
- Token của issuer A được đưa tới endpoint chỉ tin issuer B.
- Opaque token active ở Authorization Server nhưng **không dành cho Resource Server hiện tại**.
- OIDC **ID token** được sử dụng nhầm như OAuth **access token**.
- Một JWT sai chữ ký được thử lại bằng một authentication manager khác và được chấp nhận ngoài ý muốn.
- Endpoint nghiệp vụ được cấu hình nhầm vào `SecurityFilterChain` không đúng cơ chế.
- Authentication thành công, có scope, nhưng truy cập **dữ liệu tenant/owner khác**.
- Test dùng mock principal nên báo xanh trong khi việc tải JWKS hoặc introspection thật đang hỏng.

**Ma trận kiểm thử** đặt tất cả những yếu tố đó cạnh nhau:

```text
Loại credential
   × issuer / nguồn khóa / introspection trust
   × endpoint / SecurityFilterChain / resource audience
   × trạng thái token / claim / scope / dữ liệu
   → kết quả mong đợi (HTTP + tác động bảo mật + evidence)
```

Ví dụ yêu cầu cụ thể:

> “JWT access token do issuer A ký, `aud=orders-api`, có `orders:read`, gửi tới `GET /api/v2/orders` phải thành công; cùng token ấy gửi tới `/api/legacy/orders` chỉ nhận opaque token phải bị từ chối nếu introspection contract không cho phép. JWT ký bởi issuer B nhưng tự khai `iss=A` không được vượt decoder A.”

Đây là một **security contract có thể kiểm chứng**, không chỉ một danh sách HTTP status.

## 2. Ranh giới cần tách: xác thực, phân quyền và nguồn tin cậy

Một kết quả 2xx chỉ an toàn khi **cả ba câu hỏi** đã được trả lời đúng:

| Bước | Câu hỏi | Ví dụ cơ chế |
| --- | --- | --- |
| **Authentication** | Credential có hợp lệ theo nguồn tin cậy được API chấp nhận không? | JWT signature/JWKS/`iss`/`aud`/`exp`, opaque introspection `active`. |
| **Functional authorization** | Principal có quyền thực hiện chức năng không? | `hasAuthority("SCOPE_orders:read")`, role hoặc permission contract. |
| **Object/tenant authorization** | Principal có quyền trên chính bản ghi/tenant đang yêu cầu không? | Query `WHERE tenant_id = ... AND owner_id = ...`, policy bean, RLS. |

**Nguồn tin cậy (trust source)** không phải là nơi client muốn xác minh token. Nó là **cấu hình được Resource Server phê duyệt**, ví dụ:

- Một issuer chính xác cùng JWKS URL hoặc public key phù hợp.
- Một OAuth 2.0 introspection endpoint cố định, với client authentication được cấp cho Resource Server.
- Một bộ certificate CA/SAN được tin trong mTLS.
- Một session store và security configuration dành riêng cho ứng dụng browser.

Ngược lại, những giá trị như `iss`, `kid`, `jku`, `x5u` hoặc `X-Token-Type` lấy từ token/header **chưa xác minh** không được phép tự thêm nguồn tin cậy mới.

## 3. Hệ thống mẫu để xây ma trận

Giả sử một hệ thống **Orders Platform** có các vùng endpoint sau. Tên issuer, resource và token trong bài đều là **dữ liệu giả định dành cho học tập**.

| Nhóm endpoint | Cơ chế dự kiến | Nguồn tin cậy | Audience / resource | Quyền |
| --- | --- | --- | --- | --- |
| `GET /api/v2/orders/**` | JWT Bearer | Issuer A `https://login-a.example.test/realms/shop` | `orders-api` | `SCOPE_orders:read` |
| `POST /api/v2/orders/**` | JWT Bearer | Issuer A | `orders-api` | `SCOPE_orders:write` |
| `GET /api/legacy/orders/**` | Opaque Bearer | AS B introspection `https://login-b.example.test/oauth2/introspect` | `orders-legacy-api` theo contract | `SCOPE_legacy:read` |
| `POST /api/legacy/orders/**` | Opaque Bearer | AS B introspection | `orders-legacy-api` | `SCOPE_legacy:write` |
| `GET /api/internal/reports/**` | JWT machine-to-machine | Issuer C `https://workload-idp.example.test/issuer` | `reports-api` | `SCOPE_reports:read` + workload policy |
| `GET /public/status` | Public | Không yêu cầu access token | Không áp dụng | Public, không tiết lộ nội bộ |
| `/api/**` còn lại | Không được định nghĩa | Không tự nhận bất kỳ mechanism nào | Không áp dụng | Deny by default |

Trong ví dụ này:

1. **JWT A** là access token có chữ ký, issuer A, được dùng cho API v2.
2. **Opaque B** là chuỗi không thể xác minh cục bộ; API legacy kiểm tra qua AS B bằng introspection client credentials.
3. **JWT C** dành cho service/workload và endpoint reports, **không được mặc nhiên** đóng vai user ở Orders API.
4. Các vùng API có thể dùng những `SecurityFilterChain` riêng trên Servlet hoặc `SecurityWebFilterChain` riêng trên WebFlux.
5. Một resource path nằm ngoài tất cả các nhóm vẫn phải có **chính sách deny** rõ.

**Đừng áp ma trận này nguyên xi cho production:** tên đường dẫn, nguồn token và scopes phải đến từ hợp đồng OAuth/API thực tế. Một hệ thống có thể chấp nhận JWT và opaque **trên cùng endpoint**, nhưng cần một cơ chế lựa chọn được thiết kế riêng, không dựa vào thử sai.

### 3.1. Sơ đồ tuyến xử lý

```mermaid
flowchart TD
    REQ["HTTP request"] --> MATCH{"Endpoint thuộc vùng nào?"}
    MATCH -->|"v2/orders"| JA["JWT A authentication"]
    MATCH -->|"legacy/orders"| OB["Opaque B introspection"]
    MATCH -->|"internal/reports"| JC["JWT C authentication"]
    MATCH -->|"public"| PUB["Public policy"]
    MATCH -->|"Không thuộc route"| DENY["Default deny / 404 theo API"]
    JA --> JVALID["Verify JWS + trusted issuer A + aud=orders-api"]
    JC --> CVALID["Verify JWS + trusted issuer C + aud=reports-api"]
    OB --> OVALID["AS B active=true + resource contract"]
    JVALID --> AUTHZ["Functional + tenant/object authorization"]
    CVALID --> AUTHZ
    OVALID --> AUTHZ
    AUTHZ --> RESULT["2xx / 403 / policy 404"]
    PUB --> RESULT
```

Điểm cần kiểm thử là **route chọn đúng cơ chế trước khi xác thực**, rồi từng cơ chế chỉ tin đúng nguồn và resource contract.

## 4. Tạo danh mục token fixtures có danh tính rõ

Không nên chỉ tạo hai biến `validToken` và `invalidToken`. Tên fixture phải cho người đọc biết nó khác token chuẩn ở đâu.

| Fixture | Nội dung hoặc tình trạng | Dùng để kiểm thử |
| --- | --- | --- |
| `J_A_READ` | JWT JWS do A ký; `iss=A`, `aud=orders-api`, có `orders:read`, chưa hết hạn. | Positive GET v2. |
| `J_A_WRITE` | Như trên nhưng có `orders:write`. | Positive POST v2. |
| `J_A_NO_SCOPE` | JWT A hợp lệ, `aud` đúng nhưng không có scope cần thiết. | 403, không phải 401. |
| `J_A_EXPIRED` | JWS A ký đúng nhưng `exp` quá khứ ngoài clock skew. | Timestamp validation. |
| `J_A_FUTURE_NBF` | JWS A ký đúng nhưng `nbf` ở tương lai ngoài clock skew. | Not-before validation. |
| `J_A_BAD_AUD` | JWS A ký đúng nhưng `aud=payments-api`. | Resource binding. |
| `J_A_MISSING_AUD` | JWS A ký đúng, thiếu `aud` mà contract bắt buộc. | Fail-closed claim policy. |
| `J_A_WRONG_TYP` | Token ký đúng nhưng không phải access-token profile API nhận. | JWT type/token confusion. |
| `J_B_ISS_A` | JWT payload khai `iss=A` nhưng được ký bằng key B. | Không tin `iss` chưa verify. |
| `J_UNKNOWN_ISS` | JWS do issuer D chưa đăng ký phát hành. | Trusted issuer allowlist. |
| `J_A_TAMPERED` | Payload/signature của `J_A_READ` bị thay đổi không được ký lại. | Signature validation. |
| `J_C_REPORTS` | JWT C hợp lệ, `aud=reports-api`, scope `reports:read`, service actor. | Positive reports endpoint. |
| `J_C_ORDERS_LOOKALIKE` | JWT C hợp lệ nhưng mang claim/scope nhìn giống Orders token. | Cross-issuer/resource denial. |
| `O_B_READ` | Opaque token được AS B trả `active=true`, resource đúng, scope `legacy:read`. | Positive GET legacy. |
| `O_B_WRITE` | Opaque token B active và có `legacy:write`. | Positive POST legacy. |
| `O_B_NO_SCOPE` | Opaque B active nhưng thiếu scope yêu cầu. | 403 legacy. |
| `O_B_INACTIVE` | AS B trả `{"active":false}`. | 401 inactive. |
| `O_B_BAD_AUD` | AS B trả `active=true` nhưng audience của token thuộc resource khác. | Resource binding. |
| `O_B_UNKNOWN` | AS B không công nhận opaque string bất kỳ. | 401 invalid_token. |
| `OIDC_ID_A` | OIDC ID token của A, `aud` là OAuth client ID. | Không nhận ID token như access token. |
| `REFRESH_A` | Refresh token của OAuth client; không phải access token. | Từ chối ở protected resource. |
| `CLIENT_ASSERTION` | JWT dùng xác thực confidential client với AS. | Không dùng như API access token. |
| `EMPTY` | Không có `Authorization`. | 401 cho endpoint protected. |
| `MALFORMED` | Bearer header sai cú pháp hoặc token format. | 400/401 theo resolver và RFC 6750. |

Các fixture `J_*` liên quan cryptographic trust phải được ký bằng **test private keys** và được xác minh bằng **trusted test public keys**. `O_*` nên dùng một mock introspection endpoint có bảng trạng thái rõ ràng. Không sử dụng production keys, production secrets hoặc token người dùng thật trong test.

### 4.1. Dữ liệu JWT mẫu

```json
{
  "iss": "https://login-a.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893456000
}
```

Đây chỉ là **payload minh họa**. Những mốc thời gian tĩnh có thể hết hạn hoặc chưa có hiệu lực vào thời điểm chạy test. Trong test chạy tự động, tạo `iat`, `nbf`, `exp` từ một **fixed Clock** hoặc từ thời điểm test với khoảng an toàn; negative fixture phải chủ động chọn mốc nằm ngoài clock skew.

### 4.2. Dữ liệu introspection mẫu

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "legacy-user-123",
  "aud": ["orders-legacy-api"],
  "scope": "legacy:read",
  "client_id": "legacy-web-client"
}
```

Và token inactive:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
```

**HTTP 200 của introspection endpoint không đồng nghĩa token active.** Phải đánh giá `active` và các metadata theo hợp đồng. Nếu AS B không trả `aud` nhưng áp dụng resource binding dựa trên introspection client identity, test phải xác minh **bảo đảm đó**, không tự điền audience trong ứng dụng.

## 5. Quy ước đánh giá kết quả: không chỉ HTTP status

Một test case nên chứa tối thiểu:

```text
CASE_ID
METHOD + ENDPOINT
TOKEN_FIXTURE / AUTHORIZATION TRANSPORT
EXPECTED_SECURITY_CHAIN
EXPECTED_AUTHENTICATION_SOURCE
EXPECTED_HTTP_STATUS
EXPECTED_BEARER_ERROR (nếu áp dụng)
EXPECTED_AUTHORITIES / DATA_SCOPE
EXPECTED_SIDE_EFFECTS
EXPECTED_UPSTREAM_CALLS
```

Ví dụ:

```yaml
id: V2-READ-001
request:
  method: GET
  path: /api/v2/orders
  authorization: Bearer J_A_READ
expected:
  chain: jwt-a
  trustSource: issuer-a-jwks
  status: 200
  authorities:
    contains: [SCOPE_orders:read]
  introspectionCalls: 0
  resultTenant: tenant-a-only
```

Tên `J_A_READ` là **test fixture reference**, không phải raw Bearer value. Khi gửi HTTP thật, test sẽ thay bằng chuỗi test JWT đã ký.

### 5.1. Status 400, 401, 403, 404 và 5xx

| Kết quả | Ý nghĩa theo contract thông dụng | Lưu ý |
| --- | --- | --- |
| **200/201/204** | Authentication và authorization đạt, nghiệp vụ hoàn thành. | Phụ thuộc endpoint/method; không mặc nhiên mọi positive case là 200. |
| **400 Bad Request** | Bearer request sai định dạng, `invalid_request` trong tình huống RFC 6750 phù hợp. | Spring resolver và transport policy quyết định chi tiết. |
| **401 Unauthorized** | Credential thiếu hoặc không được chấp nhận. | Thường có `WWW-Authenticate: Bearer`; `invalid_token` cho token bị từ chối. |
| **403 Forbidden** | Authentication thành công nhưng scope/quyền không đủ. | Có thể `insufficient_scope`; không mọi 403 đều là thiếu OAuth scope. |
| **404 Not Found** | Tài nguyên không tồn tại hoặc policy chủ động che sự tồn tại. | Cần contract nhất quán, không tiết lộ owner/tenant khác. |
| **429 Too Many Requests** | Rate-limit do gateway/API hoặc AS nếu được map có chủ đích. | Không đổi sang “token hợp lệ” vì retry. |
| **5xx / 503** | Sự cố dependency như JWKS/introspection hoặc lỗi server. | Phải **fail-closed**; status cụ thể phụ thuộc handler, không tự gắn nhãn caller token invalid. |

Với Bearer challenge theo **RFC 6750**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

Với token hợp lệ nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Đây là response điển hình chứ không phải literal header mặc định của mọi version/custom handler. Nếu chưa có credential, một challenge `Bearer realm="orders-api"` **không cần `error="invalid_token"`**.

## 6. Ma trận chính: loại token × endpoint

Quy ước: `2xx` là mã thành công đúng contract endpoint; `401`/`403` dựa trên luồng xác thực và phân quyền ở hệ thống mẫu.

| Token / credential | GET `/api/v2/orders` (JWT A, read) | GET `/api/legacy/orders` (opaque B, read) | GET `/api/internal/reports` (JWT C, read) | Kết luận cần kiểm chứng |
| --- | --- | --- | --- | --- |
| `J_A_READ` | **2xx** | **401** theo contract chỉ opaque B | **401** | Token A không tự mở vùng legacy hoặc reports. |
| `J_A_WRITE` thiếu read | **403** | **401** | **401** | Scope write không tự bao hàm read nếu policy không quy định. |
| `J_A_NO_SCOPE` | **403** | **401** | **401** | Token hợp lệ, thiếu chức năng ở v2. |
| `J_A_EXPIRED` | **401** | **401** | **401** | Token hết hạn không được fallback. |
| `J_A_BAD_AUD` | **401** | **401** | **401** | Cùng issuer nhưng sai resource vẫn bị từ chối. |
| `J_B_ISS_A` | **401** | **401** | **401** | Claim issuer không chứng minh chữ ký. |
| `J_C_REPORTS` | **401** | **401** | **2xx** | Workload token chỉ dùng ở reports. |
| `J_C_ORDERS_LOOKALIKE` | **401** | **401** | **401/403** theo token reports contract | Claim nhìn giống Orders scope không đủ. |
| `O_B_READ` | **401** | **2xx** | **401** | Opaque token được AS B xác minh, không đi đường JWT. |
| `O_B_NO_SCOPE` | **401** | **403** | **401** | Opaque active nhưng thiếu chức năng. |
| `O_B_INACTIVE` | **401** | **401** | **401** | `active=false` phải bị từ chối. |
| `O_B_BAD_AUD` | **401** | **401** theo resource-binding policy | **401** | Active token không tự có quyền gọi mọi API. |
| `OIDC_ID_A` | **401** | **401** | **401** | ID token không phải API access token. |
| `REFRESH_A` | **401** | **401** | **401** | Refresh token không dùng ở Resource Server. |
| `CLIENT_ASSERTION` | **401** | **401** | **401** | Client assertion không phải access token. |
| Không có Bearer | **401** | **401** | **401** | Endpoint protected yêu cầu authentication. |

**Điều kiện của bảng:** AS B trong ví dụ **không công nhận** JWT A/JWT C/ID token/refresh token và policy legacy chỉ nhận opaque B; JWT A decoder và JWT C decoder có issuer/audience validators riêng. Nếu một AS thực tế hỗ trợ introspect JWT A như token active cho endpoint legacy, phải **định nghĩa contract khác và cập nhật kỳ vọng**; Spring không tự chọn status bằng cách nhìn format.

### 6.1. Vì sao JWT đúng chữ ký có thể là 403 ở một route nhưng 401 ở route khác?

`J_A_NO_SCOPE` ở `GET /api/v2/orders` được issuer A ký, audience đúng, chưa hết hạn. Nó **qua authentication** nhưng thiếu `SCOPE_orders:read`, nên thường là **403**. Cùng token đó ở `/api/internal/reports` không đạt **issuer C / audience reports-api**, nên bị từ chối **trước authorization**: **401**.

Như vậy, test phải hiểu **thất bại ở bước nào**, không chỉ so số HTTP.

### 6.2. Vì sao `J_A_WRITE` không mặc nhiên có read?

OAuth scopes là các chuỗi có ý nghĩa theo **resource policy**, không tự có thứ bậc. `orders:write` không bắt buộc bao hàm `orders:read`. Nếu API muốn quy tắc “write cũng đọc được”, phải viết authorization policy rõ và test bằng một case riêng, không ngầm hiểu từ tên scope.

## 7. Ma trận sâu: nguồn tin cậy × JWT token profile

Một JWT được xem là hợp lệ với Resource Server khi **cả chữ ký và claims** đúng theo trust profile. Cần các test sau cho endpoint JWT A:

| Case | Nguồn khóa JWS | `iss` trong payload | `aud` | Thời hạn / profile | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| JWT-T01 | Private key test A; trusted public key A | A | `orders-api` | Hợp lệ | **2xx** nếu đủ scope. |
| JWT-T02 | Private key test B | A | `orders-api` | Hợp lệ | **401**: không chấp nhận chữ ký B dưới trust A. |
| JWT-T03 | Private key test A | B | `orders-api` | Hợp lệ | **401**: issuer claim mismatch. |
| JWT-T04 | Private key test A | A | `payments-api` | Hợp lệ | **401**: wrong audience. |
| JWT-T05 | Private key test A | A | Thiếu `aud` | Hợp lệ | **401** nếu audience bắt buộc. |
| JWT-T06 | Private key test A | A | `orders-api-admin` | Hợp lệ | **401**: không substring-match audience. |
| JWT-T07 | Private key test A | A | `["payments-api", "orders-api"]` | Hợp lệ | Theo contract: membership có thể chấp nhận; exact-single có thể từ chối. |
| JWT-T08 | Private key test A | A | `orders-api` | `exp` quá khứ ngoài clock skew | **401**. |
| JWT-T09 | Private key test A | A | `orders-api` | `nbf` ở tương lai ngoài clock skew | **401**. |
| JWT-T10 | Private key test A | A | `orders-api` | Thiếu mandatory `exp` | **401** nếu token profile bắt buộc `exp`. |
| JWT-T11 | JWS payload sửa nhưng không ký lại | A | `orders-api` | Trông hợp lệ | **401**: signature invalid. |
| JWT-T12 | `alg=none` hoặc thuật toán bị cấm | A | `orders-api` | Trông hợp lệ | **401**. |
| JWT-T13 | Ký đúng nhưng `typ`/token profile là ID token | A | Thường là OAuth client ID | Có thể còn hạn | **401**. |
| JWT-T14 | `kid` lạ, không tìm thấy trusted key | A | `orders-api` | Hợp lệ | Không tạo principal khi không xác minh được. |
| JWT-T15 | `jku`/`x5u` trỏ host attacker | A hoặc giả | `orders-api` | Trông hợp lệ | Không tải/trust key source tùy ý. |
| JWT-T16 | JWS đúng issuer A, có duplicate/claim sai kiểu | A | Theo input | Theo input | Từ chối theo parser/token profile contract. |

**Cách đọc:** `kid` chỉ giúp chọn một candidate key trong **trusted JWKS**, không tự tạo trust. Một attacker có thể tự ký token bằng key riêng và đặt `kid` trùng key A, nhưng signature verification với trusted key A vẫn phải thất bại.

### 7.1. Test signature khác test validator

Hai loại negative test cần cùng tồn tại:

```text
JWS signature SAI + claims có vẻ đúng -> reject ở JOSE layer.

JWS signature ĐÚNG + exp/iss/aud SAI -> reject ở claim validators.
```

Nếu chỉ test JWS sai chữ ký, một refactor bỏ `JwtTimestampValidator` hoặc issuer validator có thể không bị phát hiện.

### 7.2. Bảo toàn validators mặc định

Khi thêm audience validator cho `NimbusJwtDecoder`:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER_A);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Access token is not for this resource",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

`setJwtValidator(...)` thay validator hiện tại, **không tự append** vào bộ mặc định. Nếu chỉ gắn audience, token đã ký hợp lệ nhưng hết hạn hoặc issuer sai có thể mất lớp kiểm tra cần thiết tùy decoder/version.

### 7.3. Issuer và public-key source phải được ràng buộc

Một token khai `iss=A` không được khiến server tự gọi:

```java
ReactiveJwtDecoders.fromIssuerLocation(unverifiedIssuer);
```

cho mọi URL do token đưa ra. Với nhiều issuers, dùng `JwtIssuerAuthenticationManagerResolver` (Servlet) hoặc `JwtIssuerReactiveAuthenticationManagerResolver` (WebFlux) có trusted issuer allowlist; decoder **vẫn phải xác minh issuer và JWS** sau bước routing.

## 8. Ma trận sâu: opaque token và AS introspection

RFC 7662 yêu cầu Resource Server có thể hỏi trạng thái token qua endpoint. Thêm kiểm tra **upstream HTTP status**, **`active`**, **resource-binding** và **HTTP client credentials**.

| Case | AS B trả về | Ý nghĩa | Kỳ vọng ở `/api/legacy/orders` |
| --- | --- | --- | --- |
| OPAQUE-T01 | HTTP 200, `active=true`, scope `legacy:read`, resource đúng | Token hợp lệ, đủ quyền | **2xx**. |
| OPAQUE-T02 | HTTP 200, `active=true`, thiếu `legacy:read` | Authenticated, thiếu scope | **403**. |
| OPAQUE-T03 | HTTP 200, `active=false` | Inactive | **401 invalid_token**. |
| OPAQUE-T04 | HTTP 200, `active=true`, `aud=payments-api` | Token dành resource khác | **401** nếu API kiểm tra audience trong introspector. |
| OPAQUE-T05 | HTTP 200 nhưng thiếu `active` hoặc kiểu sai | Response không theo contract | Fail-closed, không tạo principal. |
| OPAQUE-T06 | HTTP 200, JSON malformed | Lỗi protocol | Fail-closed. |
| OPAQUE-T07 | HTTP 401/403 từ introspection endpoint | **Resource Server client credentials/quyền** sai | Fail-closed; phân loại dependency/config issue. |
| OPAQUE-T08 | HTTP 429/503 từ AS | Throttling/unavailable | Fail-closed; xử lý dependency phù hợp. |
| OPAQUE-T09 | Connection timeout/TLS failure | Không thể xác nhận | Fail-closed; không tạo principal. |
| OPAQUE-T10 | Response `active=true` với claims `scope` sai kiểu | Sai hợp đồng | Policy quyết định reject; không cấp quyền từ dữ liệu lạ. |
| OPAQUE-T11 | Token đã bị revoke ngay trước request | AS trả `active=false` | **401**, trừ staleness đã được cache policy cho phép. |
| OPAQUE-T12 | HTTP Basic client secret đã rotate nhưng API còn v1 | AS từ chối client auth | Không coi mọi user token invalid; báo lỗi vận hành. |

### 8.1. Không nhầm hai HTTP 401

```text
Client  ───Bearer token──▶  Resource Server
Resource Server ──Basic credentials + token──▶ AS introspection
```

- **API trả 401 cho caller**: credential của caller không được API chấp nhận.
- **AS trả 401 cho Resource Server**: có thể do **introspection client ID/secret/mTLS/private_key_jwt** không hợp lệ.

Hai hop HTTP khác nhau. Một AS trả 401 cho introspection request **không chứng minh token của caller đã hết hạn**. Trong cả hai trường hợp, không được fail-open, nhưng telemetry và runbook phải phân biệt nguyên nhân.

### 8.2. Test introspection client authentication

Test HTTP với mock AS nên assert:

1. Request dùng **POST** tới URI cấu hình đáng tin.
2. `Content-Type: application/x-www-form-urlencoded` và field `token` đúng.
3. HTTP Basic/mTLS/client assertion được cấu hình đúng client registration.
4. Client ID/secret chứa ký tự đặc biệt không bị double-encode.
5. Không gửi access token hoặc introspection secret tới host tùy ý.
6. Không log Authorization Basic header hoặc `token` form body.

Với Spring Security 6.5+, `SpringOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` là một cấu hình phù hợp cho Servlet khi AS dùng client secret; WebFlux cần `ReactiveOpaqueTokenIntrospector` và implementation reactive. API theo version có thể khác; kiểm tra dependency thật.

### 8.3. Introspection của JWT cũng có thể hợp lệ theo contract

Một Authorization Server có thể yêu cầu introspect **JWT access token** để kiểm tra revocation. Trong trường hợp đó, “opaque token authentication” nói về **cách xác minh**, không nhất thiết định dạng chuỗi token.

Vì thế, ma trận không được ghi “JWT gửi tới opaque chain luôn 401 trong mọi hệ thống”. Trong hệ thống mẫu của bài, **AS B không công nhận JWT A**, nên kỳ vọng là 401. Trong production, hãy định nghĩa rõ hợp đồng:

```text
Token issuer A → JWT decoder A
Token issuer B → AS B introspection
Không tự chuyển token bị từ chối ở A sang B
```

Nếu hai cơ chế được phép trên cùng route, cần một nguồn phân biệt **đáng tin** và các negative tests chống token confusion.

## 9. Ma trận Bearer transport và request malformed

Resource Server không chỉ kiểm tra payload token; nó phải hiểu **credential được gửi qua HTTP như thế nào**.

| Case | Request | Chính sách mong đợi |
| --- | --- | --- |
| HTTP-T01 | Không có `Authorization` ở protected endpoint | 401 + Bearer challenge, thường không kèm `error`. |
| HTTP-T02 | `Authorization: Bearer <valid>` | Chuyển đúng chuỗi token đến manager của route. |
| HTTP-T03 | `Authorization: Basic ...` tới Bearer-only API | Không lấy Basic làm Bearer; thường 401 nếu không hỗ trợ Basic. |
| HTTP-T04 | `Authorization: Bearer` không có token | Invalid Bearer request/credential theo resolver, thường 400 hoặc 401. |
| HTTP-T05 | `Authorization: Bearer token-with-invalid-chars` | Từ chối theo cú pháp Bearer. |
| HTTP-T06 | Nhiều headers `Authorization` khác nhau | Từ chối hoặc xử lý theo policy rõ; không chọn credential tùy tiện. |
| HTTP-T07 | Header Bearer và query `access_token` đồng thời | Thường từ chối ambiguous request nếu cả hai transport được hỗ trợ. |
| HTTP-T08 | `GET /api/orders?access_token=...` | Không chấp nhận query token khi policy chỉ hỗ trợ header. |
| HTTP-T09 | Token trong form body | Chỉ cho phép nếu đã chủ động bật đúng RFC/contract. |
| HTTP-T10 | Header cực dài hoặc token kích thước bất thường | Giới hạn kích thước/request, không gây memory exhaustion. |
| HTTP-T11 | Hai Bearer credentials nối trong một giá trị | Không tự “lấy token đầu tiên” rồi bỏ qua phần sau. |
| HTTP-T12 | Header có CRLF/control characters | Từ chối tại gateway/container/parser; không reflection vào logs/challenge. |

Spring Security có `DefaultBearerTokenResolver` trong Servlet và converter/resolver tương ứng trên WebFlux. **Không tự normalize header để chấp nhận các format tùy tiện**, nhất là nếu reverse proxy và Resource Server có cách hiểu khác nhau.

### 9.1. Query-string tokens làm tăng rủi ro lộ credential

`access_token` trong URL có thể bị ghi vào:

- Proxy/access logs và WAF.
- Browser history, referrer, analytics.
- Cache keys, traces, error report URLs.

Ưu tiên `Authorization: Bearer`. Test nên assert **server không vô tình bật query parameter token support** khi policy chưa cho phép.

### 9.2. Có Bearer invalid vào endpoint permitAll

Một endpoint `permitAll()` có thể vẫn đi qua authentication filter. Nếu client **chủ động** gửi Bearer token không hợp lệ, filter có thể trả 401 trước khi đến authorization rule `permitAll`. Vì thế:

```text
GET /public/status, không Authorization  → public success
GET /public/status, Bearer sai           → cần test theo chain/resolver thật
```

Không mặc định `permitAll` có nghĩa “mọi invalid credential đều bị bỏ qua”. Nếu muốn public endpoint hoàn toàn tách khỏi Bearer filter, cần thiết kế chain matcher riêng và test security boundary.

## 10. Ma trận HTTP method, scope và object ownership

Ngay cả khi token hợp lệ, quyền phải khớp **HTTP method và dữ liệu**:

| Case | Request | Token | Kết quả mong đợi |
| --- | --- | --- | --- |
| AUTHZ-T01 | `GET /api/v2/orders` | `J_A_READ` | 2xx, danh sách **chỉ thuộc actor/tenant hợp lệ**. |
| AUTHZ-T02 | `POST /api/v2/orders` | `J_A_READ` | **403** nếu thiếu `orders:write`. |
| AUTHZ-T03 | `POST /api/v2/orders` | `J_A_WRITE` | **201/2xx** nếu request hợp lệ và domain policy đạt. |
| AUTHZ-T04 | `GET /api/v2/orders` | `J_A_WRITE` | **403** trừ khi policy quy định write bao hàm read. |
| AUTHZ-T05 | `GET /api/v2/orders/{idA}` | `J_A_READ`, owner tenant A | 2xx, đúng bản ghi. |
| AUTHZ-T06 | `GET /api/v2/orders/{idB}` | `J_A_READ`, bản ghi tenant B | **403/404**, không rò dữ liệu. |
| AUTHZ-T07 | `GET /api/v2/orders/{unknown}` | `J_A_READ` | 404 (hoặc domain contract khác), không tiết lộ tồn tại của tenant khác. |
| AUTHZ-T08 | `POST /api/v2/orders` | `J_A_WRITE`, body gán `tenant_id=B` | **Từ chối hoặc bỏ qua tenant giả**; không tạo bản ghi tenant B. |
| AUTHZ-T09 | `DELETE /api/v2/orders/{idA}` | `J_A_READ` | **403/405** tùy route/method policy; không xóa dữ liệu. |
| AUTHZ-T10 | `GET /api/internal/reports` | `J_C_REPORTS` | 2xx nếu service identity được policy cho phép. |
| AUTHZ-T11 | `GET /api/v2/orders` | `J_C_REPORTS` | **401** do issuer/resource boundary, không dựa vào role claim. |

**Quan trọng:** 403/404 cho truy cập bản ghi tenant khác là một lựa chọn có chủ đích. Nếu API che sự tồn tại tài nguyên bằng 404, test phải kiểm tra **không có sự khác biệt response rõ ràng** cho đối tượng tồn tại nhưng không được phép và đối tượng không tồn tại.

### 10.1. Dữ liệu kiểm thử cross-tenant

Fixture tối thiểu:

```text
Tenant Alpha:
  issuer A, sub=user-123
  internal user id=1111...
  order A-001 owner=1111..., tenant=Alpha

Tenant Bravo:
  issuer B hoặc tenant mapping khác theo contract
  internal user id=2222...
  order B-001 owner=2222..., tenant=Bravo
```

Test phải gửi token của Alpha để đọc B-001 và assert **không được truy cập**, ngay cả khi token Alpha có `orders:read`.

### 10.2. Trùng subject/email giữa issuers

Nếu issuer A và issuer B cùng phát:

```json
{"sub": "user-42", "email": "same@example.test"}
```

đó **không phải bằng chứng** hai token cùng danh tính. External identity nên dựa trên `(verified iss, verified sub)` hoặc account-linking contract đã kiểm chứng. Test cần chứng minh:

- User A không đọc được dữ liệu user B chỉ vì trùng `sub`.
- Email/tên hiển thị không tự hợp nhất tài khoản.
- Tenant membership được kiểm tra từ nguồn đáng tin.

## 11. Nhiều cơ chế xác thực: đừng để cơ chế yếu hơn mở endpoint mạnh hơn

Một API có thể đồng thời sử dụng Bearer JWT, opaque introspection, HTTP Basic, API key, browser session hoặc mTLS. Có **nhiều cơ chế** không có nghĩa một endpoint nên chấp nhận tất cả.

### 11.1. Phân biệt routing theo endpoint với routing theo token

**Routing theo endpoint đã được quy định trong API contract**:

```text
/api/v2/**          -> JWT issuer A
/api/legacy/**      -> opaque introspection AS B
/api/internal/**    -> JWT issuer C + network/workload policy
/web/**             -> browser session (nếu có)
```

Cách này rõ ràng, dễ viết ma trận và test.

**Routing theo một header do client tự gửi**:

```http
X-Token-Type: opaque
Authorization: Bearer ...
```

Header đó chỉ là dữ liệu caller kiểm soát, không tự tạo trust. Cần protocol/design riêng nếu thật sự muốn một endpoint nhận nhiều credential types.

### 11.2. Anti-pattern: fallback theo exception

```java
// SAI: jwtManager từ chối -> thử opaqueManager bất kể nguyên nhân.
return jwtManager.authenticate(authentication)
        .onErrorResume(error ->
                opaqueManager.authenticate(authentication));
```

Một JWT sai issuer/audience hoặc chữ ký có thể được kiểm tra bằng kênh có chính sách khác. Test phải chứng minh **không có fallback khi token bị từ chối**, đặc biệt khi:

- JWT A hợp lệ nhưng không dành cho legacy resource.
- JWT A signature sai.
- JWT A `iss` giả.
- Opaque B active nhưng dành cho payments API.
- Introspection AS unavailable.

### 11.3. Cần xét authentication precedence và path matcher

Một request có thể khớp nhiều route patterns, nhưng `FilterChainProxy` trong Servlet chọn **một `SecurityFilterChain` đầu tiên khớp** theo thứ tự. Với WebFlux, `WebFilterChainProxy`/`SecurityWebFilterChain` cũng áp dụng lựa chọn theo matcher và thứ tự.

Ví dụ rủi ro:

```text
@Order(1)  matcher("/api/**")          -> Basic authentication
@Order(2)  matcher("/api/v2/**")       -> JWT
```

Chain rộng ở vị trí trước có thể **che khuất** chain JWT. Bài test JWT thành công ở một controller mock **không chứng minh** request HTTP thực đi qua đúng chain.

Một cấu hình đúng nên đặt chain cụ thể trước chain tổng quát, và có **unmatched-route policy** rõ ràng.

## 12. Ví dụ cấu hình hai SecurityFilterChain trên Servlet

Đoạn code dưới đây minh họa cách phân tách JWT A và opaque B theo **đường endpoint**. Nó không chứng minh đủ bảo mật nếu chưa có bean decoder/introspector và domain authorization tương ứng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleResourceServerChains {

    @Bean
    @Order(1)
    SecurityFilterChain v2JwtApi(
            HttpSecurity http,
            JwtDecoder issuerAJwtDecoder) throws Exception {

        return http
                .securityMatcher("/api/v2/**")
                .sessionManagement(sm ->
                        sm.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(jwt ->
                                jwt.decoder(issuerAJwtDecoder)))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain legacyOpaqueApi(
            HttpSecurity http,
            OpaqueTokenIntrospector asBIntrospector) throws Exception {

        return http
                .securityMatcher("/api/legacy/**")
                .sessionManagement(sm ->
                        sm.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:read")
                        .requestMatchers(HttpMethod.POST,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(opaque ->
                                opaque.introspector(asBIntrospector)))
                .build();
    }
}
```

Đây là **một phần cấu hình**; hệ thống mẫu còn cần chain reports, public endpoint và default-deny policy, hoặc một security architecture tổng quát đạt các yêu cầu đó. Không copy đoạn này rồi mặc định phần không được cover sẽ tự deny.

**CSRF:** Với REST API thật sự chỉ nhận Bearer token trong `Authorization` và không dựa cookie/session, có thể cân nhắc tắt CSRF trong các chain đó. Ví dụ trên **chưa vô hiệu CSRF**, nên test POST có thể bị 403 vì thiếu CSRF token ngay cả khi có `orders:write`. Hãy định nghĩa chính sách CSRF theo credential transport, cấu hình rõ, và test đúng. Không tắt CSRF cho browser session app chỉ để một POST test trở thành 2xx.

### 12.1. Decoder JWT A có issuer và audience

Ví dụ logic tạo decoder:

```java
String issuerA = "https://login-a.example.test/realms/shop";
String jwksA = "https://login-a.example.test/realms/shop/certs";

NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwksA)
        .build();

OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuerA);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Wrong resource audience",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

Những biến này cần được đưa vào `@Bean`/trusted configuration để dùng trong chain, không hardcode các URL production ở nhiều chỗ. `withJwkSetUri` không tự bảo đảm `iss` đúng; phải giữ issuer validation. Token type/profile/allowed algorithms cũng cần theo contract.

### 12.2. Introspector opaque B

Với các phiên bản Spring Security hỗ trợ builder:

```java
OpaqueTokenIntrospector rawB =
        SpringOpaqueTokenIntrospector
                .withIntrospectionUri(
                        "https://login-b.example.test/oauth2/introspect")
                .clientId(introspectionClientId)
                .clientSecret(introspectionClientSecret)
                .build();
```

Trong Spring Security 6.5+, builder Spring implementation đã xuất hiện; các version cũ có API khác. Cần dùng secret manager, HTTPS, timeout và resource-binding policy. Nếu AS B trả `aud`, thêm decorator xác minh `orders-legacy-api`; nếu AS đã ràng buộc resource theo introspection client registration, test bảo đảm đó.

### 12.3. Không gắn JwtDecoder A cho mọi chain

Nếu một `SecurityFilterChain` có matcher rộng sử dụng A decoder rồi che phủ legacy/reports, ma trận phải phát hiện:

- `J_A_READ` bị chấp nhận sai ở legacy?
- `O_B_READ` bị trả 401 ở legacy do chọn JWT chain?
- `J_C_REPORTS` có bị decoder A từ chối trên reports?
- Endpoint nào không có chain và đã bị bỏ bảo vệ?

Chính vì vậy cần **HTTP integration tests chạy toàn bộ filter chain**, không chỉ unit test decoder.

## 13. WebFlux: ma trận tương đương với SecurityWebFilterChain

Với WebFlux, cấu hình sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveApiChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain jwtOrders(
            ServerHttpSecurity http,
            ReactiveJwtDecoder issuerADecoder) {

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/v2/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(jwt ->
                                jwt.jwtDecoder(issuerADecoder)))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain opaqueLegacy(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspectorB) {

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/legacy/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/legacy/orders/**")
                            .hasAuthority("SCOPE_legacy:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(opaque ->
                                opaque.introspector(introspectorB)))
                .build();
    }
}
```

Code minh họa yêu cầu imports `@Configuration`, `@Bean`, `@Order`, `@EnableWebFluxSecurity`, `PathPatternParserServerWebExchangeMatcher`, `ServerHttpSecurity`, `SecurityWebFilterChain` và reactive decoder/introspector tương ứng. Nó chỉ cấu hình các GET trong hai vùng; POST chưa được cho phép, reports/public và default-deny cần thiết kế ngoài ví dụ.

**Không ghép Java Servlet `AuthenticationManager` hoặc `JwtDecoder` đồng bộ vào WebFlux rồi gọi `.block()` trên Netty event-loop.** Reactive Resource Server cần `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector` và `ReactiveAuthenticationManager`; tests dùng `WebTestClient`.

### 13.1. Khi JWT có nhiều issuers trên WebFlux

Nếu API JWT nhận hai issuers đáng tin:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

Đưa resolver vào:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver))
```

**Lưu ý:** `fromTrustedIssuers` tập trung vào trusted issuer selection. Audience và scope/tenant policies riêng phải được bổ sung đúng cách bằng manager/decoder registry tùy chỉnh khi cần. Đọc `iss` từ JWT chưa xác minh chỉ để chọn ứng viên; decoder được chọn vẫn phải xác minh JWS và issuer.

## 14. Tổ chức kiểm thử theo ba tầng để tránh “test xanh giả”

| Tầng | Công cụ | Chứng minh điều gì? | Không chứng minh điều gì? |
| --- | --- | --- | --- |
| **Unit policy** | JUnit, custom validators, `JwtGrantedAuthoritiesConverter`, policy beans | Logic issuer/audience/claim mapping, object decisions khi dependencies mock. | Chữ ký JWS, thực tế HTTP chain, TLS/JWKS/introspection. |
| **Component/protocol** | Signed test JWS + `NimbusJwtDecoder`, WireMock/MockWebServer introspection, StepVerifier nếu reactive | Chữ ký/claims với decoder thật; HTTP introspection request/response. | Toàn bộ route ordering và domain layer nếu chưa chạy app. |
| **HTTP integration** | `MockMvc` + Spring Security filters, `WebTestClient` + WebFlux Security | Route → đúng chain → đúng manager → 401/403/2xx → đúng dữ liệu/tác động. | Tự động chứng minh sản xuất có IAM/TLS/AS thật cấu hình giống test. |

Một chiến lược tốt phối hợp cả ba:

```text
Unit tests  -> policy logic đúng
Protocol    -> nguồn tin cậy được xác minh đúng
HTTP        -> request đi đúng security mechanism và dữ liệu được bảo vệ
```

### 14.1. Bẫy của `jwt()` trong MockMvc

```java
mockMvc.perform(get("/api/v2/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

`jwt()` của `spring-security-test` tạo authentication giả lập. Test này phù hợp kiểm tra **authorization** nhưng có thể **bỏ qua `JwtDecoder`, signature, issuer, audience, expiry**.

Vì vậy nó **không chứng minh** `J_B_ISS_A` bị từ chối, không chứng minh JWT A đi nhầm legacy bị từ chối, và cũng không chứng minh JWKS rotation hoạt động.

### 14.2. Bẫy của `mockJwt()` trong WebFlux

```java
webTestClient.mutateWith(
        mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get()
        .uri("/api/v2/orders")
        .exchange()
        .expectStatus().isOk();
```

`mockJwt()` cũng dựng principal giả. Không dùng kết quả trên để tuyên bố `ReactiveJwtDecoder` xác minh chữ ký hoặc issuer resolver đã chọn manager đúng. Full trust-path test cần **Bearer header với signed JWS thật của môi trường test**.

## 15. Xây JWT fixtures có chữ ký thực sự

Một bộ tests tốt nên có **hai bộ khóa test khác nhau**, không chỉ một decoder lambda luôn trả JWT.

```text
Test issuer A:
  private key A (chỉ trong test)
  public JWK A, kid=a-key-1

Test issuer B:
  private key B (chỉ trong test)
  public JWK B, kid=b-key-1
```

Để tạo `J_B_ISS_A`:

1. Dựng payload khai `iss=A`, `aud=orders-api`, `exp` còn hiệu lực.
2. **Ký payload bằng private key B**.
3. Gửi token tới endpoint JWT A.
4. Decoder A chỉ tin public keys A nên **signature phải thất bại**.
5. Assert HTTP 401 và không có domain side effects.

Để tạo JWT sai audience có chữ ký đúng:

1. Dùng private key A.
2. `iss=A` và `exp` hợp lệ.
3. `aud=payments-api`.
4. Decoder A phải từ chối ở **audience validator**, không phải ở signature.

Để tạo JWT expired nhưng ký đúng:

1. Private key A ký payload.
2. `exp` đủ xa trong quá khứ so với clock skew.
3. Assert token bị từ chối ngay cả khi `aud` và scope đều đúng.

**Tuyệt đối không dùng production private keys** để tạo fixtures. Với integration tests, có thể cung cấp public JWK qua mock server hoặc tạo decoder từ test public key; phải bảo đảm cấu hình issuer/audience y hệt các bảo đảm production.

### 15.1. Test JWKS rotation

Một issuer đáng tin có thể phát hành key mới:

```text
Lần 1: JWKS A chứa a-key-1.
Lần 2: JWKS A chứa a-key-1 + a-key-2.
Lần 3: JWKS A bỏ a-key-1 sau cửa sổ overlap.
```

Test:

- JWT ký bằng key đang được công bố được chấp nhận sau khi decoder refresh/cập nhật cache đúng.
- JWT ký bằng key không trusted bị từ chối.
- `kid` lạ không làm decoder tải `jku` attacker.
- Key rotation của A không biến public key B thành key hợp lệ của A.
- Khi JWKS endpoint tạm lỗi và key chưa cache, API **fail-closed**.

Không cần test chính xác mọi chi tiết cache timing bằng sleep dài; dùng mock key source, clock/cấu hình cache có kiểm soát và assert behavior.

## 16. Thiết kế mock introspection server đúng mục đích

Một mock HTTP server nên có mapping từ token fixture tới response:

```text
O_B_READ       -> 200 {"active":true, "scope":"legacy:read", ...}
O_B_WRITE      -> 200 {"active":true, "scope":"legacy:write", ...}
O_B_NO_SCOPE   -> 200 {"active":true, "scope":"profile:read", ...}
O_B_INACTIVE   -> 200 {"active":false}
O_B_BAD_AUD    -> 200 {"active":true, "aud":["payments-api"], ...}
O_B_UNKNOWN    -> 200 {"active":false}
```

Mock server phải kiểm tra **request thực sự đi tới introspection endpoint**:

```http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic <test-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=O_B_READ
```

Trong bài này `O_B_READ` là tên fixture minh họa; test có thể dùng chuỗi ngẫu nhiên riêng. Không ghi Basic header hoặc token thật vào logs/snapshots.

### 16.1. Assert số lần gọi đúng trust source

Với `GET /api/v2/orders` và `J_A_READ`:

```text
JWT decoder A: được dùng
Introspection AS B: 0 calls
JWT decoder C: không được dùng
```

Với `GET /api/legacy/orders` và `O_B_READ`:

```text
Introspection AS B: nhận 1 request khi không cache
JWT decoder A: không được dùng
JWT decoder C: không được dùng
```

**Nếu ứng dụng có cache**, call count có thể khác. Khi kiểm tra đường xác thực, hãy cô lập hoặc vô hiệu cache trong test, hoặc sử dụng fixture mới để bảo đảm **cache miss**. Đừng đồng nhất kết quả 200 từ cache với việc remote introspection credential đang hoạt động.

### 16.2. Test lỗi AS nhưng không fail-open

Mock server trả HTTP 503/timeout:

```text
Expected authentication: NONE
Expected resource data: NONE
Expected writes: NONE
Expected telemetry: introspection_dependency_error
Expected HTTP: safe failure according to API error contract
```

Không tự dự đoán mọi Spring Security version sẽ trả đúng 503. Một số exception mapping có thể trả 401/5xx; điều kiện **bất biến** phải kiểm thử là **không có authenticated principal và không chạm nghiệp vụ**.

## 17. Parameterized tests: biểu diễn ma trận thành dữ liệu

Một cách tổ chức JUnit 5 là tạo record mô tả case và `@ParameterizedTest`. Đoạn code sau là **khung tích hợp**; `TestTokens` phải được hiện thực bằng JWS test encoder và fixtures/mock AS theo những mục trên.

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MultiMechanismHttpMatrixTest {

    @Autowired MockMvc mvc;
    @Autowired TestTokens tokens; // Test fixture service do dự án tạo.

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of("J_A_READ",
                        "/api/v2/orders", 200, null),
                Arguments.of("J_A_NO_SCOPE",
                        "/api/v2/orders", 403, "insufficient_scope"),
                Arguments.of("J_A_EXPIRED",
                        "/api/v2/orders", 401, "invalid_token"),
                Arguments.of("J_A_BAD_AUD",
                        "/api/v2/orders", 401, "invalid_token"),
                Arguments.of("O_B_READ",
                        "/api/legacy/orders", 200, null),
                Arguments.of("O_B_INACTIVE",
                        "/api/legacy/orders", 401, "invalid_token"),
                Arguments.of("J_A_READ",
                        "/api/legacy/orders", 401, "invalid_token"),
                Arguments.of("J_C_REPORTS",
                        "/api/v2/orders", 401, "invalid_token")
        );
    }

    @ParameterizedTest(name = "{0} -> {1}, expected {2}")
    @MethodSource("cases")
    void securityMatrix(String fixture, String path,
                        int expectedStatus, String bearerError)
            throws Exception {

        String signedOrOpaqueTestToken = tokens.resolve(fixture);

        var result = mvc.perform(get(path)
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + signedOrOpaqueTestToken))
                .andExpect(status().is(expectedStatus));

        if (bearerError != null) {
            result.andExpect(
                    header().string(
                            HttpHeaders.WWW_AUTHENTICATE,
                            containsString(
                                    "error=\"" + bearerError + "\"")));
        }
    }
}
```

**Điều kiện để ví dụ có ý nghĩa:**

- `TestTokens` là test component riêng, tạo/lấy **token giá trị thật trong request** (JWS signed hoặc opaque string), không inject Authentication giả.
- Mock AS/keys/decoder đã được cấu hình cho test context.
- Controller `GET /api/v2/orders` và `GET /api/legacy/orders` trả 200 với actor có quyền; dependencies nghiệp vụ được stub an toàn.
- Bearer entry point và access denied handler thực sự trả error codes như `invalid_token`/`insufficient_scope`. Tùy failure và custom handler, test assertion về header cần điều chỉnh theo giao thức đã định nghĩa.
- Ứng dụng có thể thêm authentication factor authorities ở phiên bản mới; không assert toàn bộ authority count bằng một hằng số nếu policy chỉ cần kiểm tra scope.

### 17.1. Đưa trust-source expectation vào code

HTTP status chưa đủ. Với mocks/spies, bổ sung:

```java
// Ý tưởng assertion; object test doubles do ứng dụng cung cấp.
verify(jwtADecoder).decode(jARead);
verifyNoInteractions(introspectionClientB);
verifyNoInteractions(jwtCDecoder);
```

Trong code thực tế, tùy Spring version/configuration có thể verify trên decoder mock, HTTP mock server hoặc instrumentation của manager. Nếu dùng real decoder, mock HTTP JWKS server và kiểm tra **request outbound**, không nhất thiết có Mockito spy vào tất cả classes.

Đừng sử dụng `@MockBean JwtDecoder` luôn trả JWT thành công để “kiểm thử JWS signature”; đó là một **test double** bypass cryptography.

### 17.2. Test POST và side effects

Không chỉ đổi `GET` thành `POST` rồi assert status. Với endpoint ghi dữ liệu, cần:

1. Token sai/thiếu quyền → không có row mới, event mới hoặc external side effect.
2. POST hợp lệ → tạo record trong đúng tenant.
3. Token tenant A với request body khai tenant B → không thể ghi vào B.
4. Test CSRF policy đúng credential transport; với API browser/cookie còn CSRF cần thực sự áp dụng.
5. Test idempotency, validation và domain constraints riêng khỏi authentication.

Nếu API cố tình dùng 404 cho truy cập object ngoài quyền, test nên assert **không có timing/response khác biệt dễ lộ dữ liệu** ở mức thực tế có thể kiểm soát.

## 18. WebTestClient: data-driven test cho WebFlux

Với WebFlux, test tương đương nhưng sử dụng `WebTestClient`:

```java
record ReactiveCase(
        String fixture,
        String path,
        int expectedStatus) {
}

List<ReactiveCase> matrix = List.of(
        new ReactiveCase("J_A_READ", "/api/v2/orders", 200),
        new ReactiveCase("J_A_EXPIRED", "/api/v2/orders", 401),
        new ReactiveCase("O_B_READ", "/api/legacy/orders", 200),
        new ReactiveCase("O_B_INACTIVE", "/api/legacy/orders", 401)
);

for (ReactiveCase testCase : matrix) {
    webTestClient.get()
            .uri(testCase.path())
            .headers(h -> h.setBearerAuth(
                    testTokens.resolve(testCase.fixture())))
            .exchange()
            .expectStatus()
            .isEqualTo(testCase.expectedStatus());
}
```

Đây là đoạn **test-body template**, không phải một class JUnit độc lập. `webTestClient`, `testTokens` và mock AS/JWKS cần được tạo trong test setup; endpoint phải trả 200 như giả định.

**Quan trọng:** dùng `headers(...setBearerAuth(...))` với **JWT/opaque test value thực**. Nếu dùng `mutateWith(mockJwt())` thì bạn đang kiểm tra authorization với principal giả, không chứng minh `ReactiveJwtDecoder` hoặc `JwtIssuerReactiveAuthenticationManagerResolver` đã chạy.

### 18.1. Test Reactor signals khi cần

Manager reactive có contract:

```java
Mono<Authentication> authenticate(Authentication input);
```

Với `StepVerifier`:

```java
StepVerifier.create(
        jwtManager.authenticate(
                new BearerTokenAuthenticationToken(signedTestJwt)))
        .expectNextMatches(Authentication::isAuthenticated)
        .verifyComplete();
```

Test manager này **không tự chứng minh** request được route tới đúng `SecurityWebFilterChain` hoặc HTTP 401/403 được xây đúng. Cần WebTestClient integration test.

## 19. Dùng contract matrix để kiểm tra authentication manager resolver

Khi một endpoint được phép nhận JWT của nhiều issuers, manager resolver có thể chọn theo trusted issuer. Một ma trận riêng:

| `iss` hint trong JWS | Ký bằng key | Trusted registry | Decoder dự kiến | Kết quả |
| --- | --- | --- | --- | --- |
| A | A | A, C | A | Verify + claims pass nếu đúng resource. |
| C | C | A, C | C | Verify + claims pass nếu đúng resource. |
| D lạ | D | A, C | Không có | Reject; không discovery tới D. |
| A | C | A, C | A | Reject chữ ký; **không thử C**. |
| C | A | A, C | C | Reject chữ ký; **không thử A**. |
| A | A nhưng `aud=payments-api` | A, C | A | Reject wrong audience. |

Trong WebFlux:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

Trong Servlet:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver
                .fromTrustedIssuers(ISSUER_A, ISSUER_C);
```

Factory `fromTrustedIssuers` có version requirements (được thêm ở Spring Security 6.2 cho các API liên quan); nếu dependency cũ hơn, dùng constructor/API phù hợp phiên bản. **Không tự tạo decoder từ `iss` tùy ý**.

### 19.1. Audience per issuer

`fromTrustedIssuers(A,C)` không phải lời hứa tự áp **mọi audience/policy riêng**. Nếu A dành cho `orders-api` và C dành cho `reports-api`, phải xây decoder/manager với expected audience riêng hoặc tạo resolver registry đáng tin, rồi test cross-audience negative cases.

### 19.2. Những thay đổi không làm mất test coverage

Nếu thêm issuer D hợp pháp:

1. Onboard D ở control plane (issuer URI, JWKS, algorithm, audience, token profile, tenant mapping).
2. Cập nhật trusted registry.
3. Thêm positive JWT D theo resource cho phép.
4. Thêm negative D ở resource khác.
5. Thêm D-key signature spoofing và wrong-audience test.
6. Test offboard D thì request mới bị từ chối.

Không tự sinh trust registry từ hàng loạt JWT issuer strings thấy trong logs.

## 20. Kiểm tra public, health và admin endpoints

Những endpoint không nhận Bearer token hoặc phục vụ monitoring thường bị bỏ qua trong ma trận.

| Endpoint | Credential | Kỳ vọng | Rủi ro nếu sai |
| --- | --- | --- | --- |
| `GET /public/status` | Không Bearer | 2xx tối giản. | Lộ cấu hình/hạ tầng nếu trả quá nhiều chi tiết. |
| `GET /public/status` | Bearer malformed | Phụ thuộc security chain; phải có test thực. | Giả định sai rằng `permitAll` bỏ qua mọi filter. |
| `GET /actuator/health` | Không auth hoặc auth theo deployment policy | Phản hồi có kiểm soát. | Lộ readiness/dependency details không cần thiết. |
| `GET /actuator/env` | Anonymous | **Không được truy cập công khai**. | Lộ secret references/configuration. |
| `GET /api/internal/reports` | JWT C + đúng scope | 2xx khi workload được phép. | Admin/workload endpoint mở với user JWT. |
| `GET /api/internal/reports` | JWT A + scope trùng tên | **401** theo issuer/resource contract. | Cross-mechanism privilege escalation. |
| Route chưa khai báo | Bất kỳ token | Deny/404 theo contract. | Missing chain hoặc fallback `permitAll`. |

**Security matcher và method matcher khác nhau:** `GET /api/v2/orders` không chứng minh `POST /api/v2/orders` an toàn. Mỗi phương thức nguy hiểm cần positive/negative cases, đặc biệt khi CSRF và browser credentials có mặt.

## 21. Một chiều khác: tenant và actor type

Nếu API hỗ trợ end-user JWT, machine JWT, opaque token và multi-tenant, test thêm:

| Actor/token | Resource | Kỳ vọng |
| --- | --- | --- |
| User A có `orders:read` | Order A | Allow nếu owner/membership đúng. |
| User A có `orders:read` | Order B tenant khác | Deny/404. |
| User A có `orders:admin` chỉ trong tenant A | Admin action tenant B | Deny. |
| Machine client C có `reports:read` | Reports endpoint được cấp | Allow. |
| Machine client C có `reports:read` | User-owned order endpoint | Deny theo profile/issuer policy. |
| User từ issuer A, `sub=user-1` | User issuer B cũng `sub=user-1` | Không tự hợp nhất account. |
| User A với email trùng user B | User B data | Deny trừ khi có account-linking contract đã xác minh. |
| Token A đúng nhưng `tenant_id` bị client override qua header | Tenant B data | Deny. |

**Token type và actor type không đồng nghĩa nhau.** JWT có thể đại diện end-user hoặc workload, tùy grant/token profile. Không suy luận user từ việc token là JWT hoặc email claim có mặt.

### 21.1. Query-level tenant isolation

Mẫu dữ liệu nên được giới hạn tại database:

```sql
SELECT id, tenant_id, owner_user_id, total_amount
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_user_id = :verifiedUserId;
```

Các tham số `verifiedTenantId` và `verifiedUserId` phải đến từ **internal actor context đã được xác minh**, không từ query/header do caller tự khai. Nếu policy cho phép tenant admin đọc tất cả đơn trong tenant, thay owner condition bằng authorization tương ứng; tenant condition vẫn cần được giữ.

## 22. “Không cho phép” phải đồng nghĩa không có side effect

Với những thao tác có thể thay đổi dữ liệu, test nên assert nhiều thứ:

```text
Expected HTTP: 401 hoặc 403
Expected authentication: failed / denied
Expected domain service invocation: 0 (nếu security chặn trước controller)
Expected DB writes: 0
Expected external events: 0
Expected outbound payment/email requests: 0
Expected audit: security denial event an toàn
```

Một handler sai có thể ghi dữ liệu trước khi trả 403. Khi đó test chỉ nhìn HTTP status vẫn **bỏ sót tổn hại thực**.

Nếu method security chạy trong service và controller đã được gọi, không nhất thiết domain service invocation là 0, nhưng **không được có tác động không được phép**. Thiết kế assert theo boundary thực tế.

### 22.1. Atomicity và side effects

Trong reactive hoặc async flows, việc một request đã trả 403 không bảo đảm background `subscribe()` trước đó đã dừng. Không tự fire-and-forget một nghiệp vụ nhạy cảm trước khi authorization đạt.

Test cần kiểm tra:

- Không có queue message được publish.
- Không có transaction commit.
- Không có downstream API side effect.
- Không tạo file/export của tenant khác.

## 23. Kiểm thử lỗi hạ tầng và rotation

Các test chỉ dùng token hợp lệ/không hợp lệ về mặt claim sẽ không phát hiện lỗi vận hành như:

- JWKS endpoint mất kết nối.
- Issuer đăng key mới nhưng cache chưa nhận.
- Introspection AS timeout.
- Client secret introspection đã rotate mà Resource Server vẫn dùng bản cũ.
- Mismatch metadata issuer URL/JWKS.
- TLS certificate hết hạn hoặc trust store sai.

### 23.1. Ma trận dependency

| Case | Trust source | Tình huống | Kỳ vọng |
| --- | --- | --- | --- |
| DEP-T01 | JWKS A | Cache có key A cũ đã được tin, token dùng key đó | Có thể verify theo cache/policy. |
| DEP-T02 | JWKS A | Key A mới, JWKS không truy cập được | Không tự chấp nhận token chưa xác minh. |
| DEP-T03 | JWKS A | Key mới được publish đúng | Decoder cập nhật theo cơ chế cache/key rotation và verify. |
| DEP-T04 | JWKS A | TLS certificate không trusted | Từ chối; không bỏ TLS verification. |
| DEP-T05 | AS B introspection | Timeout | Fail-closed; không có authenticated principal. |
| DEP-T06 | AS B introspection | `client_secret` cũ không còn active | Fail-closed; ghi nhận cấu hình credential. |
| DEP-T07 | AS B introspection | AS trả malformed JSON | Fail-closed; không dùng claims dở dang. |
| DEP-T08 | AS B introspection | Cache hit active, nhưng AS vừa revoke | Theo TTL/revocation policy đã phê duyệt; test stale window. |
| DEP-T09 | Issuer registry | Tenant/issuer đã offboard | Request mới từ issuer không còn trusted phải bị từ chối. |
| DEP-T10 | Config rollout | Một pod dùng issuer/secret cũ | Canary/cluster tests phát hiện sự không nhất quán. |

### 23.2. Test fail-closed không nhất thiết assert tất cả đều 401

Khi AS/JWKS unavailable, kết quả đúng tối thiểu là:

- Không tạo authentication đã được xác minh nếu không đủ bằng chứng.
- Không truy cập dữ liệu/side effects.
- Không lộ raw token, keys hoặc introspection client secret.
- Có telemetry **phân biệt dependency unavailable với token invalid**.
- Phản hồi HTTP theo API contract và Spring exception handling được kiểm thử, có thể là 5xx/503 thay vì luôn 401.

Không “sửa” test bằng cách làm lỗi hạ tầng trở thành login success hoặc thêm `onErrorResume` trả principal giả.

## 24. Tránh rò rỉ dữ liệu kiểm thử và dữ liệu sản xuất

Test authentication có nguy cơ in token/keys vào output khi thất bại:

```java
// SAI: thất bại là log trọn access token.
log.error("JWT decode failed: token={}, error={}", token, exception);
```

Nên ghi:

```java
log.warn(
        "Authentication denied: requestId={}, routeGroup={}, category={}",
        safeRequestId, "orders-v2", "invalid-token");
```

Đối với test fixtures:

1. Chỉ dùng private key và client secret **dành cho test**.
2. Không đưa production access/refresh tokens vào test failure messages.
3. Mock introspection server không log `Authorization: Basic ...` hoặc raw `token` body trong CI artifacts.
4. Test response `WWW-Authenticate`/JSON không có token, private key, internal JWKS URL, stack trace.
5. Tránh dùng raw unverified `iss`, `kid` hoặc `sub` làm metrics label cardinality cao.
6. Test request identifiers/correlation IDs không chứa PII hoặc credential.

Nếu cần tập hợp failures theo token, ưu tiên correlation ID; không ghi prefix/suffix dài của token để “dễ nhận diện”.

## 25. Giảm số tổ hợp nhưng không bỏ những giao điểm nguy hiểm

Nếu có:

```text
4 token types
× 3 trust sources
× 8 endpoints
× 6 claim states
× 4 scopes
× 3 tenant states
 = 6.912 tổ hợp
```

Không nhất thiết thực hiện tất cả bằng HTTP integration test. Có thể phân tầng:

**Tier A — Bắt buộc cho mỗi security boundary:**

- Token đúng cơ chế + đúng issuer + đúng audience + đủ scope.
- Token đúng cơ chế nhưng **sai issuer**.
- Token đúng issuer nhưng **sai audience**.
- Token sai chữ ký/`active=false`.
- Token đúng authentication nhưng **thiếu scope**.
- Token đúng scope nhưng **khác tenant/owner**.
- Token **sai loại** ở endpoint (JWT A → opaque B, opaque B → JWT A, ID/refresh → API).
- Route không được định nghĩa.
- Dependency unavailable → fail-closed.

**Tier B — Claim/transport/operational edge cases:**

- `exp`, `nbf`, `typ`, algorithms, `kid`, unknown issuer.
- Bad HTTP Bearer syntax, duplicate credentials, query token.
- Key/secret rotation, caches, request concurrency.
- mTLS, session/API-key mixing nếu hệ thống có dùng.

**Tier C — High-volume fuzz/property tests:**

- JWT/JSON malformed, unicode/control characters.
- JWT header `kid`/`alg`/`jku` bất thường.
- Token length, concurrency, denial-of-service resistance.
- Hoán vị scopes/claims theo token profile.

**Pairwise testing** có thể giảm số trường hợp ở các chiều ít tương tác, nhưng các negative cases **cross-trust**, **cross-audience**, **cross-tenant** và **fallback confusion** phải được giữ tường minh. Đó là những giao điểm có rủi ro privilege escalation lớn nhất.

### 25.1. Gắn ID ổn định cho mọi case

Một schema JSON/YAML nội bộ (không phải summary của bài):

```yaml
caseId: MM-JWT-AUDIENCE-003
category: token-contract
tokenFixture: J_A_BAD_AUD
method: GET
path: /api/v2/orders
expected:
  trustedSource: issuer-a-jwks
  authentication: rejected
  httpStatus: 401
  bearerError: invalid_token
  domainWrites: 0
  introspectionCalls: 0
```

Khi policy đổi có chủ đích, cập nhật case cùng quyết định review. Không âm thầm sửa expected status cho khớp output nếu chưa hiểu thay đổi trust boundary.

## 26. Quy trình triển khai ma trận vào CI/CD

### 26.1. Tại pull request

1. Chạy unit tests cho JWT claim validators, authority converters và domain policy.
2. Chạy protocol tests với signed test JWS và mock introspection AS.
3. Chạy HTTP integration matrix cho **mỗi security chain/route**.
4. Assert status, Bearer challenge, route manager và side effects.
5. Kiểm tra negative cross-issuer/cross-audience/cross-tenant cases.

### 26.2. Trước triển khai

1. Kiểm tra issuer/JWKS/introspection URLs đến từ trusted config.
2. Kiểm tra secret manager và client credentials B đúng version.
3. Kiểm tra các SecurityFilterChain matchers/order không che nhau.
4. Kiểm tra CSRF policy nếu có browser cookie/session.
5. Kiểm tra default-deny hoặc 404 route chưa khai báo.
6. Xác nhận logs/traces đã redact token, secret và key material.

### 26.3. Sau triển khai/canary

1. Kiểm tra issuer A JWT thành công ở v2 và bị từ chối ở vùng khác.
2. Kiểm tra opaque B được introspect bằng chính credential của canary.
3. Kiểm tra workload C chỉ dùng trên reports.
4. Theo dõi 401/403/5xx theo **trusted route group** thay vì raw token.
5. Kiểm tra cross-tenant domain queries bằng test account được phép.
6. Giám sát key/secret rotation, latency JWKS/introspection và cache.

Không gửi production tokens vào monitoring service không được cấp quyền. Dùng test identities/scopes tối thiểu và audit những hành động canary.

## 27. Những anti-pattern trong ma trận kiểm thử

### 27.1. Chỉ có một token valid và một token invalid

Hai fixture không thể chứng minh issuer, audience, token type, scope, tenant, key rotation hoặc route isolation. Cần các trường hợp giao nhau tường minh.

### 27.2. Chỉ assert HTTP status

Một 403 được trả **sau khi ghi DB** vẫn là lỗi bảo mật. Assert side effects và dữ liệu/tenant không bị rò.

### 27.3. Dùng JWT mock để kiểm tra trust

`mockJwt()`/`jwt()` có thể bypass decoder/issuer resolver. Dùng signed JWS thật khi muốn chứng minh signature, `iss`, `aud`, `exp`, `typ` và JWKS selection.

### 27.4. Token sai chữ ký được thử tiếp ở opaque introspection

Fallback theo exception có thể phá trust boundary. Ma trận phải assert **không thử cơ chế khác** khi token bị từ chối theo policy ban đầu.

### 27.5. Coi HTTP 200 introspection là active=true

`{"active":false}` vẫn là token không hợp lệ. Test phải kiểm tra body `active`.

### 27.6. Không test issuer lạ

`iss` chưa xác minh không được khiến API tải JWKS ở host bất kỳ. Test phải xác nhận không có outbound discovery tới unknown issuer.

### 27.7. Coi JWT A và B có cùng sub/email là cùng user

External identity cần namespace issuer. Cross-tenant account/linking phải được kiểm chứng, không so trùng email.

### 27.8. Bỏ phương thức HTTP khác

GET bảo mật đúng không bảo đảm POST, PUT, PATCH, DELETE đúng. CSRF, side effects và method matchers có thể khác.

### 27.9. Bỏ route ngoài matcher

Một URL không khớp chain bảo mật theo dự kiến có thể rơi vào chain mặc định không được cấu hình. Cần test default-deny và matcher ordering.

### 27.10. Dùng status 401 cho mọi lỗi

Token active nhưng thiếu quyền là 403 thông dụng; syntax có thể là 400; dependency error cần phân loại. Gắn nhãn mọi lỗi là invalid token làm khó vận hành và gây lỗi hành vi client.

### 27.11. Dùng response của một test double làm bằng chứng cryptography

Mockito mock `JwtDecoder` có thể trả `Jwt` hợp lệ cho **bất kỳ chuỗi nào**, vì thế không chứng minh JWS verification.

### 27.12. Coi một lần cache hit là kiểm tra AS credential

Opaque token được cache active có thể trả 200 dù introspection client secret đã sai. Muốn kiểm tra rotation phải thực hiện **cache miss hoặc real introspection probe**.

### 27.13. Test endpoint công khai bằng cách gửi invalid Bearer rồi yêu cầu luôn 200

`permitAll` không nhất thiết bỏ qua Bearer filter. Phải xác định public route có chain riêng hay có authentication processing.

### 27.14. Đổi expected result theo implementation lỗi

Khi token B bất ngờ truy cập được API A, đừng chỉ sửa expected status từ 401 sang 200 để test xanh. Trước tiên xác định trust policy có **chủ ý** thay đổi hay hệ thống đang cho phép cross-mechanism access.

## 28. Bài thực hành tổng hợp

Hãy giả sử đội phát triển thêm endpoint:

```http
POST /api/v2/orders/6a5c.../approve
```

Policy mới:

- Chỉ JWT issuer A, `aud=orders-api`.
- Token phải còn hạn, đúng JWT access-token profile.
- Phải có `SCOPE_orders:approve`.
- Actor phải là approver của tenant sở hữu order.
- Không được tự phê duyệt order do chính mình tạo nếu business policy cấm.

Ma trận tối thiểu:

| Case | Token | Order / actor | Expected |
| --- | --- | --- | --- |
| APPROVE-01 | JWT A hợp lệ, `orders:approve` | Approver tenant A, không phải creator | 2xx; approval event một lần. |
| APPROVE-02 | JWT A hợp lệ, `orders:read` | Approver tenant A | 403; không có approval event. |
| APPROVE-03 | JWT A hết hạn, `orders:approve` | Approver tenant A | 401; không có event. |
| APPROVE-04 | JWT C hợp lệ, cùng tên scope | Order A | 401 theo issuer/resource boundary. |
| APPROVE-05 | Opaque B active với quyền tên tương tự | Order A | 401 theo route chỉ JWT A. |
| APPROVE-06 | OIDC ID token A | Order A | 401. |
| APPROVE-07 | JWT A đúng nhưng `aud=payments-api` | Order A | 401. |
| APPROVE-08 | JWT A đúng, `orders:approve` | Approver tenant B | 403/404; không có event. |
| APPROVE-09 | JWT A đúng, `orders:approve` | Creator tự phê duyệt | 403 theo domain policy. |
| APPROVE-10 | JWT A đúng, `orders:approve` | Order không tồn tại | 404; không có event. |
| APPROVE-11 | JWT A tampered | Approver tenant A | 401. |
| APPROVE-12 | Không credential | Order A | 401 + Bearer challenge. |
| APPROVE-13 | JWT A đúng, `orders:approve` | Không được phép gửi request body `tenant=B` để ghi B | Deny/no side effect. |
| APPROVE-14 | JWKS A unavailable, token key chưa cache | Order A | Fail-closed. |

Bài tập này minh họa điều quan trọng: **một endpoint mới không chỉ tạo một positive test**. Nó còn phải xác định những credential, nguồn tin cậy, resource và actor **không được phép** đi qua.

## 29. Câu hỏi tự kiểm tra

**1. Tại sao cần ma trận nhiều chiều?** Vì nhiều lỗi phát sinh khi **token hợp lệ ở một ngữ cảnh** được dùng ở **ngữ cảnh khác**, chẳng hạn sai issuer, audience, chain hoặc tenant.

**2. JWT có chữ ký hợp lệ đã đủ để gọi API chưa?** Chưa. Cần issuer, audience, thời hạn, token profile và quyền.

**3. `iss` trong JWT trước xác minh có đáng tin không?** Không. Chỉ được dùng làm routing hint tới **trusted issuer**; decoder phải xác minh lại chữ ký/issuer.

**4. Token JWT A gửi tới opaque B endpoint luôn bị 401 trong mọi hệ thống không?** Không. Phụ thuộc AS B có công nhận token đó theo contract hay không. Trong hệ thống mẫu, AS B **không công nhận**, nên kỳ vọng là 401.

**5. Opaque introspection HTTP 200 có đủ xác thực không?** Không. Phải kiểm tra `active` và resource/claim contract.

**6. Khi token hợp lệ nhưng thiếu scope, HTTP thường là gì?** Thường **403 Forbidden**, khác 401 khi credential bị từ chối ở authentication.

**7. Tại sao phải kiểm thử token sai audience có chữ ký đúng?** Để phát hiện thiếu audience validator; signature validation riêng không chặn được token dành cho API khác.

**8. OIDC ID token có thể dùng như OAuth access token không?** Không được mặc nhiên. Resource Server cần chấp nhận đúng access-token profile/audience.

**9. Vì sao không fallback từ JWT manager lỗi sang opaque manager?** Nó có thể phá trust boundary và tạo token confusion.

**10. `MockMvc.jwt()` hoặc `WebTestClient.mockJwt()` kiểm tra chữ ký thật không?** Không; chúng chủ yếu tạo principal giả để kiểm tra authorization.

**11. Vì sao ma trận phải có expected trust source?** Để phát hiện request đã đi qua **sai SecurityFilterChain hoặc decoder/introspector** dù HTTP status có vẻ đúng.

**12. Vì sao cần assert domain side effects?** Một 401/403 trả sau khi ghi dữ liệu vẫn có thể gây lỗi bảo mật.

**13. Có phải `SCOPE_orders:write` mặc nhiên cho quyền read không?** Không; chỉ khi policy quy định tường minh.

**14. Lỗi AS introspection client secret sai có chứng minh access token của user inactive không?** Không. Đây có thể là lỗi Resource Server–AS client authentication; vẫn fail-closed.

**15. Khi JWKS endpoint mất mạng có được bỏ qua signature validation không?** Không.

**16. Có nên dùng email làm khóa định danh khi chuyển issuer không?** Không nếu chưa có account-linking contract; thường dùng `(verified iss, verified sub)`.

**17. Vì sao test phải có route không được định nghĩa?** Để phát hiện endpoint lọt khỏi matcher và đi vào chain thiếu bảo vệ.

**18. Vì sao phải tách CSRF khỏi OAuth scope?** Vì POST có thể trả 403 do CSRF policy trước khi scope authorization; phải kiểm tra credential transport và chain riêng.

**19. Có cần test resource audience cho opaque token không?** Có nếu contract yêu cầu. AS có thể trả `aud` hoặc ràng buộc resource dựa vào introspection client quyền hạn; test đúng bảo đảm đó.

**20. Khi tenant A và tenant B có cùng scope, đã cách ly dữ liệu chưa?** Chưa. Phải kiểm tra internal identity, membership, owner và tenant-scoped data access.

## 30. Tài liệu và tiêu chuẩn tham khảo

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách truyền token và các lỗi `invalid_request`, `invalid_token`, `insufficient_scope`. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `nbf`. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** tránh algorithm/token confusion, kiểm soát issuer/audience và key trust. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** token profile/access-token type và required claims theo profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` và metadata introspection. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6749 — OAuth 2.0 Authorization Framework:** access/refresh tokens và client authentication. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 9110 — HTTP Semantics:** HTTP 401/403/404 và authentication challenge. https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Servlet Security Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html
- **Spring Security Reference — Reactive JWT Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Reactive Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security Reference — Servlet Testing:** https://docs.spring.io/spring-security/reference/servlet/test/index.html
- **Spring Security Reference — Reactive Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **Spring Security API — `JwtIssuerAuthenticationManagerResolver`, `JwtIssuerReactiveAuthenticationManagerResolver`, `JwtValidators`, `NimbusJwtDecoder`, `NimbusReactiveJwtDecoder`:** xem Javadoc đúng phiên bản phụ thuộc dự án.

## 31. Kết luận

Khi một Resource Server hỗ trợ **nhiều cơ chế xác thực**, bài kiểm thử phải trả lời rõ **token thuộc loại nào, issuer/nguồn khóa hoặc introspection server nào được tin, request vào endpoint nào, và chính xác kết quả nào được phép xảy ra**. Một ma trận chỉ có “valid → 200, invalid → 401” sẽ bỏ sót phần lớn vấn đề **cross-issuer, cross-resource và cross-tenant**.

Tập tối thiểu nên luôn có:

```text
Positive: đúng loại + đúng issuer/trust + đúng audience + đúng route
          + đúng scope + đúng owner/tenant  → thành công

Negative: sai loại hoặc nguồn tin cậy     → 401
Negative: đúng issuer nhưng sai audience  → 401
Negative: signature invalid / inactive    → 401
Negative: token hợp lệ nhưng thiếu quyền  → 403
Negative: đúng scope nhưng khác tenant    → 403/404 theo policy
Negative: AS/JWKS unavailable             → fail-closed, không side effect
Negative: route chưa định nghĩa           → default deny / 404
```

Cuối cùng, hãy chạy **signed JWT tests và HTTP introspection mock** để chứng minh nguồn tin cậy; dùng **MockMvc/WebTestClient qua filter chain** để chứng minh routing và HTTP behavior; và kiểm tra **dữ liệu cùng side effects** để chứng minh authorization nghiệp vụ. Câu hỏi lớn nhất của ma trận không chỉ là **“request có trả 200 không?”**, mà là **“một credential chỉ được chấp nhận ở đúng trust boundary, trên đúng resource, với đúng quyền và không thể vượt sang tenant/cơ chế khác hay không?”**.
