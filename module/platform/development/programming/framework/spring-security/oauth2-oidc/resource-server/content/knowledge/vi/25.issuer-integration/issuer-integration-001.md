# Đọc metadata và hợp đồng access token của nhà phát hành

Trong kiến trúc **Spring Security OAuth 2.0/OIDC Resource Server**, API không nên tự quyết định tin một access token chỉ vì chuỗi token có ba phần giống JWT, có claim `sub` hoặc được gửi từ một OAuth client quen thuộc. Resource Server phải biết **nhà phát hành (issuer) nào được tin cậy**, khóa hoặc introspection endpoint nào thuộc nhà phát hành đó, và **hợp đồng access token** nào được chấp nhận tại chính API.

Một Authorization Server (AS) hoặc OpenID Provider (OP) thường công bố metadata tại những endpoint thuộc nhóm `.well-known`. Metadata có thể chứa `issuer`, `jwks_uri`, `authorization_endpoint`, `token_endpoint`, `introspection_endpoint` và các capabilities khác. Tuy nhiên, **metadata không phải toàn bộ hợp đồng access token**. Resource Server vẫn cần một thỏa thuận riêng về audience, access-token profile, signing algorithms, scopes, custom claims, token lifetime, tenant boundaries, revocation và cách phản hồi lỗi.

Bài học này trình bày cách:

1. Đọc đúng **OAuth 2.0 Authorization Server Metadata** (RFC 8414) và **OpenID Connect Discovery**.
2. Xác định issuer URI, metadata endpoints và JWK Set thuộc nguồn tin cậy.
3. Phân biệt metadata về OAuth/OIDC endpoints với những điều kiện áp dụng riêng cho **access token của API**.
4. Định nghĩa hợp đồng JWT và opaque access token: issuer, audience, signature, time, scopes, principal, client, tenant, token type.
5. Cấu hình Spring Security Resource Server ở Servlet/WebFlux, bao gồm `issuer-uri` và `jwk-set-uri`.
6. Tránh tin metadata tùy ý, JWT headers chứa URL khóa, `iss` chưa xác minh, hoặc ID token được gửi nhầm làm access token.
7. Kiểm thử contract bằng JWT thực sự được ký, fake JWKS/introspection server và negative scenarios.
8. Theo dõi vận hành metadata/JWKS, key rotation, đồng bộ thời gian và thay đổi chính sách issuer.

> **Nguyên tắc cốt lõi:** Metadata giúp Resource Server **khám phá các thông tin của một issuer đã được tin cậy**. Hợp đồng access token giúp Resource Server quyết định **một token cụ thể có được chấp nhận tại API này không**. Còn HTTP/method/object authorization quyết định **caller được làm gì** sau khi token đã hợp lệ.

## 1. Ba vai trò trong một luồng OAuth 2.0

Giả sử hệ thống bán hàng có:

```text
Authorization Server / OpenID Provider:
  https://login.example.test/realms/shop

OAuth Client:
  shop-web

Resource Server:
  Orders API: https://orders.example.test
  Payments API: https://payments.example.test
```

Một user dùng `shop-web` để đăng nhập hoặc thực hiện authorization flow. AS cấp access token để client gọi API. Resource Server xác minh token trước khi xử lý dữ liệu.

```mermaid
sequenceDiagram
    participant U as User
    participant C as OAuth Client shop-web
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    U->>C: Truy cập chức năng Orders
    C->>AS: OAuth/OIDC authorization flow
    AS-->>C: Access token dành cho orders-api
    C->>RS: GET /api/orders + Bearer token
    Note over RS: Trusted issuer + key/introspection config
    RS->>RS: Token validation: iss, aud, time, alg, contract
    RS->>RS: Scope + tenant + object authorization
    RS-->>C: Data hoặc lỗi 401/403/404 phù hợp
```

Bốn identifiers thường bị lẫn:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| **Issuer** | `https://login.example.test/realms/shop` | Định danh AS đã cấp token |
| **OAuth client ID** | `shop-web` | Ứng dụng đã nhận/được cấp token |
| **Resource/API audience** | `orders-api` | Đối tượng mà token được phép sử dụng |
| **Subject** | `user-123` | Principal trong không gian identity của issuer |

Không thay `aud=orders-api` bằng `client_id=shop-web`. Một OAuth client có thể xin access tokens cho nhiều APIs; client ID không nói token hiện tại dành cho API nào.

### 1.1. Authorization Server và OpenID Provider có giống nhau?

**Authorization Server** là vai trò của OAuth 2.0, có thể cấp access token mà không hỗ trợ OIDC.

**OpenID Provider** là issuer hỗ trợ OpenID Connect, có thể cung cấp ID token và OIDC Discovery ngoài OAuth functionality.

Một AS không hỗ trợ OIDC vẫn có thể công bố **OAuth Authorization Server Metadata theo RFC 8414**. Vì thế một Resource Server không được giả định mọi issuer đều bắt buộc có `/.well-known/openid-configuration`.

### 1.2. Resource Server thường không cần thực hiện login

Spring Security Resource Server có nhiệm vụ xác thực bearer access token. Nó **không cần đóng vai OAuth login client** chỉ để kiểm tra JWT.

Trong ứng dụng kết hợp web login và API, có thể có cả OAuth Client và Resource Server dependencies, nhưng đó là hai chức năng tách biệt. Đừng lấy ID token từ đăng nhập OIDC rồi cho API chấp nhận thay access token.

## 2. Metadata là gì và giải quyết bài toán nào?

Một metadata document thường là JSON do AS công bố để những bên tương tác biết các endpoints và khả năng được hỗ trợ.

Ví dụ tối giản, mang tính minh họa:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "authorization_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.test/realms/shop/protocol/openid-connect/certs",
  "introspection_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token/introspect",
  "revocation_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/revoke",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
  "scopes_supported": ["openid", "profile", "orders.read", "orders.write"]
}
```

Không phải mọi Authorization Server đều trả tất cả các fields trên; chính xác field nào cần có tùy metadata profile và issuer. Ví dụ JSON này cũng **không chứng minh các scopes listed luôn được cấp** cho mọi OAuth client.

Metadata giúp trả lời:

- Issuer công bố định danh gì?
- JWK Set URI ở đâu?
- Token endpoint và introspection endpoint ở đâu, nếu issuer công bố?
- Các OAuth/OIDC flows, authentication methods hoặc capabilities nào được công bố?
- Resource Server có thể cấu hình discovery/JWKS từ một issuer đã biết như thế nào?

**Metadata không tự trả lời đầy đủ**:

- Audience nào là hợp lệ cho Orders API?
- Access token là JWT, opaque, JWE hay một profile riêng?
- JWT access token có `typ` bắt buộc là gì?
- AS dùng signing algorithms nào cho **access token**?
- `scope` có dạng string hay array?
- `tenant_id` có nghĩa gì, có phải claim bắt buộc không?
- Thu hồi quyền thành viên tenant có hiệu lực nhanh tới mức nào?
- `ROLE_ADMIN` có phải role global hay tenant-scoped?
- Orders API có được phép chuyển token sang Payments API không?

Những điều đó cần **hợp đồng access token** riêng.

## 3. Hai chuẩn khám phá thường gặp

### 3.1. RFC 8414: OAuth 2.0 Authorization Server Metadata

RFC 8414 định nghĩa cách một AS công bố metadata, thường dùng well-known suffix:

```text
/.well-known/oauth-authorization-server
```

Với issuer không có path:

```text
Issuer:
  https://login.example.test

OAuth AS Metadata:
  https://login.example.test/.well-known/oauth-authorization-server
```

Với issuer có path:

```text
Issuer:
  https://login.example.test/realms/shop

OAuth AS Metadata theo RFC 8414:
  https://login.example.test/.well-known/oauth-authorization-server/realms/shop
```

Điểm dễ nhầm: Với **RFC 8414**, well-known path được chèn giữa host và issuer path theo quy tắc chuẩn. Không mặc định nối `/.well-known/oauth-authorization-server` vào cuối path trong mọi issuer configuration.

### 3.2. OpenID Connect Discovery

OIDC Discovery sử dụng well-known document thường mang tên:

```text
/.well-known/openid-configuration
```

Với issuer OIDC có path:

```text
Issuer:
  https://login.example.test/realms/shop

OIDC Discovery:
  https://login.example.test/realms/shop/.well-known/openid-configuration
```

Đây là dạng **gắn suffix theo issuer URL** của OIDC Discovery. Một Authorization Server có thể hỗ trợ cả RFC 8414 và OIDC Discovery, hoặc chỉ một trong số đó.

### 3.3. Không hardcode một URL discovery cho mọi hệ thống

Ví dụ với path issuer `/realms/shop`, hai URLs có hình dạng khác nhau:

| Chuẩn | Metadata URL minh họa |
|---|---|
| OAuth AS Metadata (RFC 8414) | `https://login.example.test/.well-known/oauth-authorization-server/realms/shop` |
| OIDC Discovery | `https://login.example.test/realms/shop/.well-known/openid-configuration` |

Khi triển khai Spring Security, factory discovery của thư viện có thể thử những dạng metadata location tương thích theo phiên bản. **Không tự suy ra thứ tự fallback cố định cho mọi bản Spring Security**. Hãy dùng API discovery chính thức và kiểm tra endpoint thực tế mà issuer cung cấp.

### 3.4. Không bắt buộc mọi OAuth issuer phải có OIDC metadata

Nếu AS chỉ làm OAuth 2.0, gọi OIDC endpoint nhận 404 không đồng nghĩa AS không hợp lệ. Có thể issuer cung cấp RFC 8414 metadata, JWK Set URI tường minh hoặc opaque introspection contract.

**Hợp đồng tích hợp được xác định trước** mới là nguồn tin cậy để quyết định các endpoints nào cần dùng.

## 4. Đọc một metadata document đúng cách

Ví dụ lệnh xem metadata, dùng endpoint đã được tổ chức công bố:

```bash
curl --fail-with-body -sS \
  "https://login.example.test/realms/shop/.well-known/openid-configuration"
```

Dùng `--fail-with-body` nếu curl version hỗ trợ; nếu không, dùng `curl -i` và kiểm tra HTTP status trước khi parse JSON.

Một số metadata fields quan trọng:

| Field | Ý nghĩa | Có bắt buộc cho mọi Resource Server? |
|---|---|---|
| `issuer` | Định danh issuer được metadata công bố | Rất quan trọng cho trust và JWT issuer validation |
| `jwks_uri` | URL của JWK Set được issuer công bố | Cần khi xác minh JWT bằng remote public keys |
| `authorization_endpoint` | Endpoint dùng trong OAuth authorization flow | Thường dành cho OAuth client hơn là API |
| `token_endpoint` | Endpoint cấp access token | Client cần; API Resource Server thường không tự gọi để xác minh JWT |
| `introspection_endpoint` | Endpoint hỏi trạng thái/thông tin token | Cần nếu API dùng opaque introspection |
| `revocation_endpoint` | Endpoint đề nghị thu hồi token | Không đồng nghĩa API được phép gọi; thường thuộc OAuth client/AS contract |
| `userinfo_endpoint` | OIDC UserInfo endpoint | Không thay access-token validation ở API |
| `grant_types_supported` | Các grant types được AS công bố | Không chứng minh client cụ thể được dùng mọi grant |
| `response_types_supported` | Các authorization response types | Không thay chứng minh access token phù hợp API |
| `scopes_supported` | Tập scopes issuer hỗ trợ/công bố | Không có nghĩa mỗi token đều chứa chúng |
| `id_token_signing_alg_values_supported` | Thuật toán ký ID token theo OIDC | Không tự xác định thuật toán của access token |
| `token_endpoint_auth_methods_supported` | Client authentication methods tại token endpoint | Không đồng nghĩa introspection auth methods |

Không đồng nhất endpoint capabilities với token contract. Ví dụ `scopes_supported` có `orders.write` nhưng client nhận token chỉ có `orders.read`, API vẫn phải chặn POST cần quyền ghi.

## 5. Nguồn tin cậy phải có trước discovery

Một bước tích hợp không an toàn:

```text
Nhận bearer token từ Internet
  -> tự parse JWT payload chưa kiểm chứng
  -> lấy iss từ payload
  -> kết nối tới URL issuer do caller khai
  -> tải metadata/JWKS
  -> dùng khóa vừa tải để xác minh token
  -> chấp nhận nếu chữ ký khớp
```

Attacker có thể tạo issuer và khóa riêng, ký token của chính họ, rồi điều khiển Resource Server kết nối nguồn đó. Đây là kiểu **tin nguồn khóa do token chưa xác minh chỉ định**.

Thiết kế đúng:

1. **Cấu hình trước** trusted issuer URI hoặc allowlist các issuers.
2. Resource Server chỉ khám phá metadata thuộc những issuers đã được cho phép.
3. Metadata phải được tải qua kết nối HTTPS đã xác minh chứng chỉ và hostname, theo hợp đồng triển khai.
4. Field `issuer` trong metadata phải phù hợp với trusted issuer đã cấu hình.
5. JWT được xác minh bằng trusted keys và algorithms được phép.
6. Claims `iss`, `aud`, time, token type và custom rules phải đạt.
7. Khi có nhiều issuers, routing phải được giới hạn vào allowlist chứ không tự thêm issuer mới theo input.

### 5.1. Một issuer URL chưa có nghĩa metadata đáng tin

HTTPS cung cấp bảo vệ transport và server identity theo PKI, nhưng Resource Server vẫn phải biết nó **đang tin đúng tổ chức/issuer nào**. Một metadata document hoàn toàn hợp lệ từ domain của attacker không giúp API có lý do nhận tokens của attacker.

### 5.2. Không disable TLS validation

Để “sửa lỗi discovery” không được:

- Tắt certificate validation.
- Bỏ hostname verification.
- Dùng HTTP không bảo vệ trong production khi contract yêu cầu HTTPS.
- Tự redirect tới URL nội bộ/tùy ý thiếu kiểm soát.
- Chấp nhận metadata/JWKS từ fallback domain không thuộc trust policy.

Nếu môi trường có private CA hoặc mTLS, cần cấu hình truststore/HTTP client tương ứng, không bỏ kiểm tra chứng chỉ.

### 5.3. SSRF khi làm dynamic discovery

Metadata/JWKS endpoints là network URLs. Nếu URL được tạo từ input chưa xác thực, backend có thể bị buộc truy cập localhost, metadata cloud hoặc các mạng nội bộ. Dùng allowlist issuers/endpoints, quy tắc egress và redirect policy có kiểm soát.

## 6. Issuer URI: một giá trị định danh, không chỉ hostname

Giả sử metadata trả:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "jwks_uri": "https://login.example.test/realms/shop/protocol/openid-connect/certs"
}
```

JWT access token hợp lệ của issuer này thường có:

```json
{
  "iss": "https://login.example.test/realms/shop"
}
```

Resource Server phải so sánh issuer theo chính sách chính xác.

### 6.1. Những biến thể có thể khác issuer

```text
https://login.example.test/realms/shop
https://login.example.test/realms/shop/
https://LOGIN.example.test/realms/shop
http://login.example.test/realms/shop
https://login.example.test/realms/other
```

Không mặc định chuẩn hóa thủ công hoặc coi mọi biến thể là cùng issuer; issuer comparison phải tuân contract/specification mà thư viện hỗ trợ. Đặc biệt **scheme, path và dấu slash cuối có thể có ý nghĩa**. Một issuer mismatch không nên được sửa bằng cách bỏ hoàn toàn issuer validation.

### 6.2. Realm hoặc tenant path không tự là data tenant

Ví dụ issuer `/realms/shop` có thể cấp token cho nhiều data tenants:

```text
shop-a
shop-b
shop-c
```

Không lấy path `shop` rồi gán thành tenant của mọi request. Identity realm, OAuth issuer và tenant dữ liệu là những concepts khác nhau. Nếu AS cung cấp `tenant_id`, phải xác định claim đó có ý nghĩa gì và có cần membership check server-side không.

## 7. Đọc JWK Set từ `jwks_uri`

Trong JWT Resource Server, AS thường ký access token bằng private key. Resource Server lấy public keys tại `jwks_uri` để xác minh chữ ký.

Ví dụ:

```bash
curl --fail-with-body -sS \
  "https://login.example.test/realms/shop/protocol/openid-connect/certs"
```

Response minh họa:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-key-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA_MODULUS_BASE64URL>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-key-02",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA_MODULUS_BASE64URL>",
      "e": "AQAB"
    }
  ]
}
```

Đây là public key material minh họa; các giá trị placeholder không phải khóa hợp lệ.

| Thuộc tính JWK | Ý nghĩa |
|---|---|
| `kty` | Loại key, ví dụ RSA hoặc EC |
| `kid` | Key identifier, hỗ trợ chọn key phù hợp |
| `use` | Mục đích key, ví dụ `sig` khi có |
| `key_ops` | Các thao tác key được phép nếu công bố |
| `alg` | Algorithm được JWK gợi ý/khai báo nếu có |
| `n`, `e` | Các thành phần public key RSA |
| `crv`, `x`, `y` | Các thành phần EC key theo đường cong tương ứng |

Resource Server cần xác minh JWS bằng khóa phù hợp, nhưng `kid` **không tự chứng minh key đáng tin**. Key phải đến từ JWKS của issuer mà ứng dụng đã cho phép.

### 7.1. JWK Set public không có nghĩa bỏ xác thực JWT

Public keys được công bố để Resource Server kiểm chữ ký; điều đó không cấp quyền cho người xem JWKS. Private keys vẫn do AS bảo vệ. Một attacker có thể xem public key nhưng không thể tạo chữ ký hợp lệ nếu không có private key.

### 7.2. Không dùng `jku` hoặc `x5u` từ JWT để tự lấy khóa

JWT header có thể chứa các tham số trỏ tới URL khóa/chứng chỉ. Không cho token chưa được tin quyết định một endpoint mới mà API sẽ tải. Trong cấu hình điển hình, JWKS URI phải đến từ trusted metadata/config, không từ token header do caller điều khiển.

### 7.3. JWKS key lookup thất bại phải fail closed

Nếu token có `kid=unknown-key` mà không có key nào phù hợp trong trusted set, **không bỏ qua signature verification**. Việc thử refresh JWKS tùy decoder/cache có thể hữu ích, nhưng nếu vẫn không có khóa đáng tin thì phải từ chối.

## 8. JWT header: `alg`, `kid` và `typ`

Ví dụ header:

```json
{
  "alg": "RS256",
  "kid": "shop-key-02",
  "typ": "at+jwt"
}
```

Ba trường có vai trò khác nhau:

- `alg` là thuật toán ký JWS.
- `kid` hỗ trợ chọn public key tương ứng từ tập khóa đáng tin.
- `typ` có thể mô tả loại JWT/profile theo hợp đồng.

**JWT header là dữ liệu chưa được tin trước signature verification.** Decoder phải kiểm tra thuật toán theo allowlist, key source theo trusted issuer, và type profile theo hợp đồng ứng dụng.

### 8.1. Không chấp nhận thuật toán do token tự chọn

Sai:

```text
if token.header.alg == anything:
    choose algorithm requested by token
    use any provided key
    accept if operation succeeds
```

Đúng hơn:

```text
Issuer contract:
  accepted access token JWS algs = [RS256]

Decoder:
  only use trusted JWKS keys suitable for RS256
  reject none/unsupported/algorithm-confusion cases
```

Nếu issuer có hợp đồng hỗ trợ ES256 hoặc PS256 thì cấu hình có thể khác. Không mở toàn bộ algorithms chỉ để “chạy được” một token lỗi.

### 8.2. ID token alg metadata không thay access-token alg contract

OIDC metadata có thể công bố `id_token_signing_alg_values_supported`. Tên trường nói rõ **ID token**. Resource Server không nên suy luận đây là danh sách thuật toán cho JWT **access tokens** nếu AS không có tài liệu/hợp đồng xác nhận.

### 8.3. `typ=at+jwt` và RFC 9068

RFC 9068 mô tả JWT Profile for OAuth 2.0 Access Tokens, bao gồm header token type `at+jwt` (hoặc dạng media type tương ứng trong chuẩn). Nhưng **không phải mọi AS phát hành JWT access token đều triển khai RFC 9068 đầy đủ**.

Nếu Resource Server yêu cầu profile này, cần:

- Thỏa thuận AS phát hành token theo profile.
- Xác minh đúng `typ` và claims bắt buộc theo chuẩn/profile.
- Kiểm tra expected audience.
- Không nhận OIDC ID token hoặc JWT khác chỉ vì cùng key/issuer.

Không mặc định Spring Security validator mặc định đã thực thi toàn bộ RFC 9068 profile; behavior phụ thuộc phiên bản và cấu hình decoder.

## 9. Hợp đồng access token là gì?

Một **access-token contract** là thỏa thuận giữa AS, OAuth clients và Resource Servers, có thể được thể hiện qua tài liệu kiến trúc, test fixtures, issuer configuration và chính sách triển khai.

Một hợp đồng cho Orders API có thể gồm:

```yaml
# Chỉ là bản mô tả contract, KHÔNG phải Spring Boot configuration.
issuer:
  value: https://login.example.test/realms/shop
  discovery: oidc-or-oauth-metadata

resource:
  id: orders-api
  audience: orders-api

access_token:
  format: jwt
  profile: rfc9068
  signing_algorithms:
    - RS256
  public_keys: trusted-issuer-jwks
  expires_at_required: true
  accepted_clock_skew_seconds: 60

claims:
  required:
    - iss
    - sub
    - aud
    - exp
    - scope
  custom:
    tenant_id:
      required: true
      type: string
      semantics: active-data-tenant

authorization:
  scope_authorities_prefix: SCOPE_
  read: orders.read
  write: orders.write

revocation:
  strategy: short-lived-tokens-plus-server-side-policy
```

**Lưu ý:** Đây là ví dụ do hệ thống tự định nghĩa. Chuẩn OAuth 2.0 không bắt mọi issuer trả `tenant_id` hay phát scopes theo đúng danh sách trên. Nếu AS không triển khai RFC 9068, hãy chọn profile thực tế thay vì áp yêu cầu này một cách mù quáng.

### 9.1. Những trường bắt buộc phải được thống nhất

| Nhóm | Câu hỏi cần có đáp án |
|---|---|
| Token format | Access token là JWT, opaque, JWE hay định dạng khác? |
| Issuer | Giá trị `iss` chính xác và AS endpoints là gì? |
| Trust | JWKS/introspection URL, TLS trust, client credentials, rotation policy? |
| Audience | Resource Server ID nào token phải chứa? |
| Type/profile | Token type/`typ` nào được chấp nhận; có RFC 9068 không? |
| Crypto | Signing algorithms và key types nào được cho phép? |
| Lifetime | `exp`, `nbf`, `iat`, skew, TTL tối đa? |
| Identity | `sub` namespace, service principal khác end user thế nào? |
| Authorization | `scope`/`scp`/`roles` có ý nghĩa gì? Mapping thế nào? |
| Client | Có cần ràng buộc `client_id`/`azp` theo application allowlist không? |
| Tenant | Claim hay membership nào xác định active tenant; quyền có scope theo tenant không? |
| Revocation | JWT offline, introspection, denylist hay TTL ngắn? |
| Errors | Authentication 401 và authorization 403 được biểu diễn ra sao? |
| Compatibility | Thay đổi issuer/claims/keys được rollout thế nào? |

Contract có giá trị khi được **kiểm chứng bằng code và tests**, không chỉ là bảng tài liệu.

## 10. Một JWT access token minh họa

JWT payload:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800,
  "jti": "jti-123"
}
```

Giải thích:

| Claim | Ý nghĩa | Kiểm tra ở Orders API |
|---|---|---|
| `iss` | Token được phát hành bởi AS nào | Exact expected trusted issuer |
| `sub` | Subject theo issuer | Có mặt/đúng kiểu nếu contract đòi |
| `aud` | API được phép nhận token | Phải chứa `orders-api` |
| `client_id` | OAuth client được ghi nhận theo token profile | Client allowlist nếu policy yêu cầu |
| `scope` | Tập scopes được cấp | Ánh xạ và kiểm tra per endpoint |
| `tenant_id` | Tenant theo hợp đồng riêng | Kiểm tra kiểu/giá trị và membership khi cần |
| `iat` | Issued-at | Dùng nếu có max-token-age policy |
| `nbf` | Not-before | Không dùng trước thời điểm hợp lệ |
| `exp` | Expiration | Không chấp nhận token quá hạn |
| `jti` | Token identifier | Có thể phục vụ audit/denylist, không tự cấp quyền |

Với Spring Security, token **chỉ được tin sau khi signature và validators đạt**. Đừng lấy chuỗi Base64URL payload và đưa thẳng vào `SecurityContext`.

### 10.1. Sự hiện diện của claim khác ngữ nghĩa của claim

Một token có `tenant_id="shop-a"` không tự chứng minh caller vẫn là thành viên shop-a nếu membership có thể bị thu hồi. Một token có `scope="orders.read"` không có nghĩa user được xem đơn của bất kỳ người nào. Một token có `client_id="shop-web"` không thể dùng tại Payments API nếu audience chỉ là Orders API.

## 11. Audience phải gắn với Resource Server, không phải client ID

Một client dùng nhiều APIs:

```text
OAuth client:
  shop-web

Orders access token:
  aud = ["orders-api"]

Payments access token:
  aud = ["payments-api"]
```

Đôi khi hai tokens đều có cùng `iss`, `sub` và `client_id` nhưng khác audience và scope. Orders API chỉ nên nhận token mà `aud` chứa định danh Orders API.

### 11.1. Scope không thay audience

Token:

```json
{
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

vẫn không phù hợp với Orders API theo hợp đồng audience. Một string trông như scope Orders không chứng minh token được cấp cho Orders Resource Server.

### 11.2. Audience có thể chứa nhiều resource identifiers

JWT `aud` có thể là string hoặc array theo JSON Web Token specification. Spring Security `Jwt.getAudience()` cung cấp danh sách audiences cho việc validation.

Nếu AS cấp multi-audience access token, Resource Server vẫn phải kiểm tra **định danh của chính nó có mặt trong danh sách**, và cần đánh giá tính cần thiết/rủi ro của token đa audience. Không mặc định “token có ít nhất một audience” là đủ.

### 11.3. Resource Indicators RFC 8707

OAuth 2.0 Resource Indicators cho phép client chỉ định một resource khi xin token trong các flows được AS hỗ trợ:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
resource=https%3A%2F%2Forders.example.test&
scope=orders.read
```

Ví dụ rút gọn không chứa phần client authentication; token endpoint vẫn phải được bảo vệ theo client type và AS contract.

**Không mặc định dùng `resource` sẽ luôn tạo `aud` bằng đúng chuỗi resource.** Cần kiểm tra mapping trong hợp đồng AS. Resource Server phải xác minh actual audience của token.

## 12. Scope và authority mapping trong Spring Security

Ví dụ claim:

```json
{
  "scope": "orders.read orders.write"
}
```

Với cấu hình thông dụng, Spring Security chuyển thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

và API dùng:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
```

### 12.1. `scopes_supported` trong metadata không phải scopes của token

Metadata có:

```json
{
  "scopes_supported": [
    "openid",
    "profile",
    "orders.read",
    "orders.write",
    "orders.export"
  ]
}
```

Nhưng token chỉ có:

```json
{"scope": "orders.read"}
```

Caller vẫn **không** có `SCOPE_orders.export`. Resource Server phải đọc authorities từ token đã xác minh hoặc introspection response, không lấy toàn bộ `scopes_supported` làm quyền cho mọi caller.

### 12.2. `scope` và `scp` không luôn cùng định dạng

Một AS dùng:

```json
{"scope": "orders.read orders.write"}
```

AS khác có thể dùng:

```json
{"scp": ["orders.read", "orders.write"]}
```

Điều này là **contract của issuer/token profile**. Không tự động áp parser của một AS lên AS khác. Kiểm tra converter behavior theo phiên bản Spring Security và cấu hình claim names/types tường minh khi cần.

### 12.3. `roles` có phải `ROLE_...` không?

OIDC/OAuth metadata không quy định mọi AS phải cấp roles theo một claim chuẩn giống nhau. Các claims như:

```json
{
  "roles": ["ORDER_MANAGER"],
  "realm_access": {
    "roles": ["shop-user"]
  }
}
```

có thể là cấu trúc đặc thù của sản phẩm hoặc deployment. Nếu muốn map sang `ROLE_ORDER_MANAGER`, cần converter dựa trên **contract đáng tin**, không cấp role theo một field mà caller có thể điều khiển.

## 13. Chuyển custom claims thành domain identity

Một tenant-aware API có thể cần:

```json
{
  "sub": "user-123",
  "tenant_id": "shop-a",
  "groups": ["shop-a/orders-editors"]
}
```

Cần xác định:

1. Tenant claim là một tenant hay danh sách membership?
2. Tenant ID có global namespace hay phụ thuộc issuer?
3. Role/group có hiệu lực trong tenant nào?
4. Membership thay đổi thì token cũ còn được dùng không?
5. `sub` là user ID ổn định hay service principal?
6. Nếu AS không trả `tenant_id`, API lấy từ nguồn server-side nào?

Một authentication converter có thể tạo `AuthenticatedActor`/domain principal từ claims đã xác thực. Nhưng nó **không được tự điền tenant từ URL** rồi coi là đã được AS xác minh.

### 13.1. Hợp đồng nhiều issuers phải tránh trùng identity

Hai issuers có thể phát hành `sub="user-123"` cho hai tài khoản khác nhau. Khi truy vấn owner của đơn hàng, identity thường cần cặp **(iss, sub)** hoặc mapping nội bộ đáng tin.

Không dùng username/email một mình làm khóa ownership trong multi-issuer system khi contract không bảo đảm tính duy nhất và ổn định.

## 14. Thời gian: `exp`, `nbf`, `iat` và clock skew

JWT claims thời gian thường theo NumericDate: số giây từ Unix epoch.

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Ý nghĩa:

| Claim | Mục đích |
|---|---|
| `iat` | Thời điểm phát hành |
| `nbf` | Thời điểm sớm nhất token có hiệu lực |
| `exp` | Thời điểm token hết hạn |

Resource Server phải kiểm tra timestamps theo validator/contract, đồng thời có thể sử dụng clock skew nhỏ để xử lý lệch đồng hồ. Không nên dùng skew quá lớn để kéo dài hiệu lực token.

### 14.1. Metadata không tự chứng minh JWT chưa hết hạn

AS metadata có `issuer` và `jwks_uri` chính xác, nhưng một JWT cũ vẫn có thể hết hạn. Mỗi token cần được kiểm tra tại thời điểm authentication.

### 14.2. `iat` không thay thế expiration

Một token phát hành cách đây 5 phút không tự chứng minh còn hợp lệ. Nếu contract bắt buộc `exp`, kiểm tra sự hiện diện và giá trị của nó; không tự đặt `exp=now+1h` khi token thiếu claim.

### 14.3. Revocation là bài toán khác expiration

JWT tự chứa có thể xác minh offline cho đến khi hết hạn. Nếu cần thu hồi quyền/token nhanh, hệ thống có thể dùng TTL ngắn, revocation/denylist, introspection hoặc policy service theo kiến trúc. Chỉ có discovery metadata **không cho biết một JWT hiện đã bị thu hồi hay chưa**.

## 15. Phân biệt JWT access token với OIDC ID token

OIDC ID token và OAuth access token có thể đều dùng compact JWT format và có cùng issuer, nhưng mục đích khác:

| Đặc điểm | OIDC ID token | OAuth access token |
|---|---|---|
| Bên nhận chính | OIDC client | Resource Server/API |
| Audience thường gặp | OAuth client ID | Resource ID của API |
| Mục đích | Truyền thông tin authentication cho client | Cho API kiểm tra token và quyền truy cập |
| `sub` | Có thể có | Có thể có tùy profile |
| Scope API | Không phải nguồn mặc định của API permission | Có thể mang scopes/permissions theo contract |
| Sử dụng trong `Authorization: Bearer` tới Orders API | Không nên nếu không phải access token dành cho API | Đúng vai trò khi được AS cấp |

Ví dụ ID token:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["shop-web"],
  "email": "user@example.test"
}
```

ID token có thể hợp lệ với shop-web, nhưng **Orders API không được chấp nhận** nếu audience contract yêu cầu `orders-api`. Không bỏ audience validation chỉ vì hai tokens cùng issuer và cùng `sub`.

### 15.1. UserInfo endpoint không thay access-token contract

OIDC metadata có thể đưa `userinfo_endpoint`. API Resource Server thường không cần gọi UserInfo để quyết định bearer token có đúng audience và scope. UserInfo là endpoint thuộc OIDC profile, không phải công cụ tự động xác minh JWT signature của API.

### 15.2. Tránh cross-JWT confusion

Issuer có thể phát hành nhiều loại JWT: ID token, access token, refresh-related assertions, logout token, service assertions hoặc internal tokens. Nếu chúng dùng chung key, **signature đúng không tự bảo đảm token đúng loại**.

Khi contract yêu cầu token type/profile, hãy xác minh `typ` và các claims phù hợp, không chỉ `iss`/`sub`.

## 16. Nếu issuer cấp opaque access token thì đọc gì?

Không phải mọi access token có dạng JWT. Với opaque token:

```text
Authorization: Bearer 8NqVx2pLmZ_some_opaque_value
```

Resource Server không thể xem chuỗi token để tự lấy claims. Cần có **introspection endpoint** của AS theo RFC 7662 và thông tin xác thực cho Resource Server.

Metadata có thể công bố:

```json
{
  "issuer": "https://login.example.test/realms/shop",
  "introspection_endpoint": "https://login.example.test/realms/shop/protocol/openid-connect/token/introspect"
}
```

Nhưng URI đó **không tự cung cấp credentials**; API phải được AS cấp quyền dùng introspection endpoint (ví dụ Basic client authentication, private_key_jwt hoặc mTLS theo hợp đồng).

### 16.1. Introspection request

Ví dụ minh họa:

```http
POST /realms/shop/protocol/openid-connect/token/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

Server có thể trả:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://login.example.test/realms/shop",
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

Đây là **response minh họa**. Ngoài `active`, các trường còn lại phụ thuộc AS và contract. Không tự giả định RFC 7662 buộc mọi issuer trả `iss`, `aud`, `tenant_id`, `exp`.

### 16.2. `active=true` chưa đủ cho mọi API

Một token active có thể dành cho Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read"
}
```

Orders API cần ràng buộc `aud` hoặc resource identity theo hợp đồng; nếu contract yêu cầu audience `orders-api` và AS cung cấp field, một wrapper `OpaqueTokenIntrospector` có thể từ chối token sai audience.

### 16.3. Introspection client ID khác caller client ID

- `client-id` trong cấu hình Resource Server introspection: định danh API dùng khi gọi AS.
- `client_id` trong introspection response: OAuth client đã được AS ghi nhận là client của token.

Chúng không nhất thiết giống nhau. Không so sánh hai giá trị như thể chúng là cùng một chủ thể.

## 17. JWT validation và opaque introspection là hai hợp đồng khác nhau

| Vấn đề | JWT Resource Server | Opaque Resource Server |
|---|---|---|
| Token format | JWT/JWS được hỗ trợ | Chuỗi opaque do AS cấp |
| Trust mechanism | Public-key signature + validators | AS introspection qua endpoint đáng tin |
| Chìa khóa endpoint | `jwks_uri`/configured key | `introspection_endpoint`/configured URI |
| Auth credentials tới AS | Thường không cần cho public JWKS | Thường cần credentials/authorization |
| Revocation | Phụ thuộc TTL/denylist/introspection khác | AS có thể đánh giá `active` trực tuyến |
| Network dependency | Metadata/JWKS fetch/cache | Thường có introspection call theo request/token |
| Resource audience | `aud` trong JWT | Audience/resource info do AS introspect trả theo contract |
| Scope mapping | Claims trong JWT | Claims/authorities từ introspection |
| Failure mode | Signature/issuer/audience/time/JWKS | inactive/AS HTTP timeout/credential errors/contract |
| Error principle | Fail closed | Fail closed |

Không chọn chế độ chỉ dựa vào việc token “trông có dấu chấm”. Chọn JWT/opaque theo AS token format contract và Resource Server architecture.

## 18. Spring Boot Servlet: cấu hình issuer URI

Một lựa chọn đơn giản cho JWT Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Spring Security/JWT auto-configuration có thể sử dụng issuer discovery để tìm JWK Set URI và áp issuer validation theo phiên bản. Cách này phù hợp khi AS công bố metadata chuẩn và Resource Server chỉ tin một issuer.

### 18.1. HTTP authorization vẫn phải cấu hình

```java
@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/catalog"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders"
                ).hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

`issuer-uri` có thể giúp xác định nguồn token; còn `hasAuthority(...)` đánh giá quyền thao tác HTTP. Một token issuer đúng nhưng scope không đủ vẫn phải bị 403; token issuer sai hoặc signature invalid thường bị 401.

### 18.2. Metadata discovery không thay audience validation

Một issuer có thể cấp tokens cho Orders API, Payments API và Admin API. **Chỉ cấu hình issuer URI chưa tự biết expected audience của Orders API** trong mọi bản Spring Boot/Spring Security. Hãy cấu hình `audiences` nếu phiên bản hỗ trợ hoặc đặt `OAuth2TokenValidator<Jwt>` tùy biến.

## 19. Spring Boot: cấu hình JWK Set URI tường minh

Nếu tổ chức biết chính xác JWK Set URL:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
```

Ý nghĩa:

- `issuer-uri`: expected issuer dùng cho token validation.
- `jwk-set-uri`: nguồn public keys để xác minh chữ ký.

Một số cấu hình có thể giảm dependency startup vào discovery metadata bằng cách cung cấp `jwk-set-uri` tường minh, nhưng JWKS vẫn có thể cần HTTP fetch khi xác minh tokens. Chi tiết startup/runtime fetch phụ thuộc phiên bản và caching.

**Không bỏ issuer validation chỉ vì có JWK Set URI.** JWKS cho biết nguồn key đã cấu hình; `iss` phải được đối chiếu với expected issuer riêng.

### 19.1. Audience property nếu Boot hỗ trợ

Ví dụ cho các phiên bản Spring Boot có hỗ trợ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

Cần kiểm tra property được hỗ trợ ở version đang dùng, và xem bean decoder có bị custom override không. Khi developer tự tạo `JwtDecoder` bean, Boot có thể không tự gắn mọi property validators lên bean đó.

## 20. Java configuration: khám phá issuer với `JwtDecoders`

Một factory thường dùng trong Servlet Resource Server:

```java
@Bean
JwtDecoder jwtDecoder() {
    String issuer =
        "https://login.example.test/realms/shop";

    return JwtDecoders.fromIssuerLocation(issuer);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
```

Factory sử dụng issuer discovery theo cơ chế Spring Security hỗ trợ. Nếu chỉ cần behavior tương tự cấu hình property, không nhất thiết phải tạo bean riêng.

### 20.1. Khi cần custom validator, tạo NimbusJwtDecoder có kiểm soát

Một ví dụ cụ thể hơn:

```java
@Configuration
public class OrdersJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String JWKS =
        "https://login.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String EXPECTED_AUDIENCE =
        "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(EXPECTED_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaults,
                audience
            )
        );

        return decoder;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

Đây là một ví dụ quan trọng:

1. `NimbusJwtDecoder` xác minh JWT bằng key lấy từ trusted JWKS.
2. `JwtValidators.createDefaultWithIssuer(...)` cung cấp các validators mặc định cùng issuer.
3. Custom audience validator đòi `aud` chứa `orders-api`.
4. `DelegatingOAuth2TokenValidator<>` kết hợp các validators theo logic phải thỏa cùng nhau.

**Không chỉ gọi `setJwtValidator(audience)` rồi vô tình thay thế issuer/timestamp validation.** Khi tạo decoder riêng, developer phải chịu trách nhiệm giữ đủ những rule cần thiết.

### 20.2. Có thể bắt buộc claim tenant theo hợp đồng

Nếu API đơn tenant và AS luôn phát hành `tenant_id`:

```java
OAuth2TokenValidator<Jwt> tenantRequired = jwt -> {
    Object value = jwt.getClaim("tenant_id");

    if (value instanceof String tenant && !tenant.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required tenant claim is missing",
            null
        )
    );
};
```

Nó có thể được kết hợp cùng defaults và audience. Đây là **rule tùy biến theo contract**, không phải yêu cầu mặc định của mọi JWT access token.

### 20.3. Không tự sửa claim để qua validation

Không làm:

```java
if (jwt.getAudience().isEmpty()) {
    // Sai: biến token thiếu audience thành token được API chấp nhận.
    claims.put("aud", List.of("orders-api"));
}
```

Nếu AS cấp token không đúng audience, phải sửa cấu hình cấp token/hợp đồng, không làm validator luôn đúng bằng cách thêm claim phía Resource Server.

## 21. Spring WebFlux: cấu hình discovery bằng ReactiveJwtDecoder

Với WebFlux, interface là `ReactiveJwtDecoder` và result là `Mono<Jwt>`.

Ví dụ:

```java
@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
            "https://login.example.test/realms/shop"
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

Đây là ví dụ WebFlux; không dùng Servlet `HttpSecurity`/`SecurityFilterChain` thay vào.

### 21.1. Reactive Nimbus và JWKS tường minh

Khi cần decoder riêng:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri(
                "https://login.example.test/realms/shop/protocol/openid-connect/certs"
            )
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://login.example.test/realms/shop"
        )
    );

    return decoder;
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

Nếu API cần audience, bổ sung audience validator theo cách ở phần Servlet, **không chỉ giữ issuer**. Một `JwtDecoder` đồng bộ không tự thay `ReactiveJwtDecoder`.

### 21.2. Không thực hiện blocking discovery trong WebFlux event loop

Nếu ứng dụng tự viết discovery/metadata client, tránh `RestTemplate` hoặc `.block()` trên Netty event loop. Dùng support reactive của Spring Security/HTTP client phù hợp, có timeouts và controls.

## 22. Opaque token trong Servlet Spring Security

Nếu hợp đồng token là opaque:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/realms/shop/protocol/openid-connect/token/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Cấu hình filter chain:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Một `OpaqueTokenIntrospector` của Spring Security sẽ gọi AS để xác thực token theo cấu hình. Nếu cần audience/client/tenant rules, có thể bọc implementation delegate bằng decorator.

### 22.1. Decorator chỉ trả principal khi contract đạt

Ví dụ:

```java
public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean matched =
            aud instanceof String text
                && "orders-api".equals(text);

        if (aud instanceof Collection<?> values) {
            matched = values.stream()
                .anyMatch("orders-api"::equals);
        }

        if (!matched) {
            throw new BadOpaqueTokenException(
                "Wrong audience"
            );
        }

        return principal;
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

Lưu ý:

- Delegate phải kiểm tra `active` trước.
- Nếu AS không trả `aud` nhưng contract yêu cầu audience, phải thỏa thuận AS trả claim hoặc dùng cơ chế resource binding khác.
- Không cho token active của Payments API đi qua Orders API.
- Không bắt exception của delegate rồi tạo principal giả.
- Wrapper token-wide không thay owner/tenant record authorization.

## 23. Signing algorithms và token profile là hợp đồng riêng

Một AS có OIDC metadata:

```json
{
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
```

Điều đó không chứng minh access token hiện tại dùng RS256/ES256 với cùng constraints.

Một **access-token contract** cần trả lời:

```text
Access token format:
  JWT JWS compact

Accepted access-token JWS algorithms:
  RS256

Expected header type:
  at+jwt, if AS implements RFC 9068 profile

Trusted public key set:
  issuer JWKS URL

Key rotation:
  publish new key before signing with it
  retain old key until old tokens expire

Token encryption:
  not used (or separately specified if JWE is used)
```

### 23.1. JWE khác JWS

- **JWS:** token được ký, Resource Server xác minh chữ ký.
- **JWE:** token được mã hóa; Resource Server cần decryption keys/processing phù hợp trước khi có thể xác thực claims theo profile.

Một token có năm phần compact có thể là JWE thay vì JWS. Không tự parse mọi token như JWT ba phần, và không coi “đã giải mã Base64” là đã xác minh tính hợp lệ.

Nếu AS cấp encrypted access tokens, Resource Server phải có hợp đồng JWE riêng và implementation được hỗ trợ; không tự tắt mã hóa hoặc chấp nhận plaintext tokens tùy tiện.

## 24. Sender-constrained access tokens cần kiểm chứng bổ sung

Một số AS phát hành access token **ràng buộc với bên gửi** thay vì bearer token có thể dùng bởi bất kỳ ai sở hữu chuỗi token.

Hai cơ chế phổ biến:

- **mTLS-bound access tokens** theo RFC 8705.
- **DPoP-bound access tokens** theo RFC 9449.

JWT/introspection có thể có thông tin `cnf` mô tả confirmation key/thumbprint theo profile. Nhưng chỉ có claim `cnf` **không chứng minh request hiện tại thực sự sở hữu khóa**.

### 24.1. mTLS

Resource Server cần kiểm tra client certificate trong kết nối TLS và so khớp thumbprint/binding theo contract. Nếu API nằm sau gateway TLS termination, cần thiết kế trust boundary rõ để backend không tin một header chứng chỉ do Internet client tự gửi.

### 24.2. DPoP

DPoP yêu cầu kiểm tra proof JWT/HTTP binding, method, URI, timestamp, nonce/replay rules và public key thumbprint theo chuẩn/hợp đồng. Không đơn giản chấp nhận `Authorization: DPoP ...` rồi xử lý nó như Bearer thường.

**Không mặc định Spring Security Resource Server cấu hình JWT issuer-uri đã tự hỗ trợ đầy đủ mọi sender-constrained token mechanism.** Cần kiểm tra capabilities và cấu hình version thực tế.

### 24.3. Vì sao phần này liên quan metadata?

AS có thể công bố một số capabilities về DPoP/mTLS trong metadata theo extensions. Nhưng metadata quảng bá hỗ trợ một feature **không có nghĩa mọi access token đều dùng feature đó**, hoặc Resource Server đã tự triển khai xác minh proof. Hợp đồng token/client/RS phải thống nhất.

## 25. JWKS rotation: metadata đúng nhưng token vẫn lỗi

Giả sử AS đang dùng key `kid=old-2026`, rồi luân chuyển sang `kid=new-2026`.

Một kế hoạch vận hành:

1. AS tạo key pair mới.
2. AS công bố **public JWK mới** tại trusted JWKS trước khi phát token mới.
3. AS vẫn giữ public JWK cũ trong giai đoạn token cũ còn hiệu lực.
4. AS bắt đầu ký tokens mới với key mới.
5. Resource Servers cập nhật/cached JWKS và chọn key theo `kid`.
6. Sau khi tokens cũ hết hạn và chuyển đổi an toàn, AS gỡ key cũ.
7. Theo dõi failures, rollback plan và timeline.

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS Endpoint
    participant RS as Resource Server
    AS->>JWKS: Publish public key NEW alongside OLD
    AS->>RS: New JWT header kid=NEW via client request
    RS->>JWKS: Refresh JWKS when cache/lookup requires
    JWKS-->>RS: Keys OLD + NEW
    RS->>RS: Verify signature with NEW
    Note over AS,RS: Keep OLD until valid old tokens have expired
    AS->>JWKS: Remove OLD after safe transition
```

### 25.1. `kid` mới và cache

Nếu Resource Server chưa thấy `kid` mới trong cache, decoder có thể tải lại JWKS theo implementation. Nhưng nếu JWKS chưa công bố key mới hoặc network không sẵn sàng, token không có trusted key để xác minh. **Không tắt signature validation** để chữa lỗi rotation.

### 25.2. `kid` có thể bị trùng hoặc thiếu

Key selection không nên chỉ dựa vào `kid` mà bỏ thuật toán, key type, key use và issuer context. Nếu nhiều keys không thể phân biệt an toàn, decoder cần từ chối hoặc xử lý theo contract triển khai, không tùy ý lấy một key.

### 25.3. JWKS cache khác access-token validation cache

Một decoder cache public keys để giảm HTTP requests nhưng vẫn xác minh mỗi JWT. Cache key không có nghĩa JWT còn hiệu lực khi `exp` đã qua hoặc token sai audience.

## 26. Metadata/JWKS outage và failure handling

Các sự cố có thể xuất hiện:

| Triệu chứng | Khả năng | Tác động |
|---|---|---|
| Metadata trả 404 | Nhầm URL OIDC/RFC 8414 hoặc issuer không hỗ trợ endpoint đó | Không discovery được |
| Metadata issuer mismatch | Cấu hình sai realm, path hoặc server proxy | Không nên tin kết quả |
| TLS handshake failure | Certificate/truststore/mTLS/hostname vấn đề | Không tải metadata/JWKS |
| Metadata JSON malformed | AS/gateway response lỗi | Discovery thất bại |
| `jwks_uri` không truy cập được | Network/egress/DNS/service outage | Không có fresh keys |
| JWT có `kid` mới nhưng JWKS cũ | Rotation chưa đồng bộ | Signature verification thất bại |
| JWT `iss` sai | Token của issuer khác | Authentication bị từ chối |
| JWT `aud` sai | Token dành cho API khác | Authentication bị từ chối |
| JWT `exp` quá hạn | Token hết hạn | Authentication bị từ chối |
| Opaque introspection 401 | Introspection client credentials sai/không đủ quyền | Authentication không thể hoàn tất |
| Opaque introspection timeout | AS/network unavailable | Fail closed |
| Token active thiếu claim contract | Contract mismatch | Wrapper/validator từ chối |

Lỗi hạ tầng không có nghĩa token đã bị thu hồi, nhưng **không thể cấp Authentication thành công nếu chưa xác minh được**.

### 26.1. Startup dependency khác runtime dependency

Khi tạo decoder từ issuer discovery, một số cấu hình có thể cần HTTP metadata ngay khi khởi tạo; cấu hình khác có thể trì hoãn fetch hoặc dùng JWK URI có sẵn. Vì vậy:

- Không khẳng định mọi version Spring Security luôn fail startup khi AS down.
- Không khẳng định mọi version luôn hoàn toàn lazy.
- Kiểm tra behavior trong dependency version thực tế.
- Thiết kế readiness/startup checks, timeouts và monitoring phù hợp.

### 26.2. Timeout và retry

Network discovery/JWKS/introspection cần timeouts, giới hạn kết nối và retry/backoff có kiểm soát. Retry invalid JWT hoặc token inactive vô hạn không giải quyết vấn đề. Một AS outage có thể gây thác lỗi khi nhiều APIs cùng thử discovery/JWKS refresh, nên cần capacity planning.

## 27. Multi-issuer integration: mỗi issuer có contract riêng

Một API có thể tin hai issuers:

```text
Issuer A:
  https://login.example.test/realms/shop
  JWKS A
  audience: orders-api

Issuer B:
  https://partners.example.test/realms/partners
  JWKS B
  audience: orders-partners-api
```

Không nên dùng một decoder với JWKS A rồi chấp nhận token issuer B, hoặc tự gộp tất cả keys vào một tập không ràng buộc issuer.

### 27.1. Routing phải có issuer allowlist

Một authentication manager resolver có thể cần đọc `iss` chưa xác thực **chỉ để chọn** giữa những issuers đã allowlist:

```text
unverified iss = https://partners.example.test/realms/partners

if issuer in trustedAllowlist:
    choose configured decoder for that issuer
    decode and verify signature + iss + aud + time
else:
    reject
```

Nhận một issuer bất kỳ rồi tự tạo decoder từ URL đó là nguy hiểm. Việc đọc claim chưa xác minh **không được coi là xác thực claim**.

### 27.2. Claims có thể khác ngữ nghĩa giữa issuers

Issuer A dùng:

```json
{"tenant_id": "shop-a", "scope": "orders.read"}
```

Issuer B dùng:

```json
{"organization": "partner-17", "permissions": ["orders:read"]}
```

Nếu API cho cả hai đi qua, cần resolver/converter theo từng issuer contract. Không lấy `permissions` của đối tác và ánh xạ trực tiếp thành admin quyền nội bộ nếu chưa có policy explicit.

### 27.3. Subject namespace

`(iss A, sub=user-123)` có thể khác `(iss B, sub=user-123)`. Domain identity mapping nên xét issuer-qualified principal hoặc internal account ID được server-side ánh xạ.

## 28. Metadata có thể thay đổi, nhưng trust không nên tự động mở rộng

AS upgrade có thể thêm:

- Scopes mới.
- Grant types mới.
- Signing algorithms được hỗ trợ thêm.
- Token auth methods.
- Endpoint mới.
- Claims OIDC bổ sung.

Resource Server **không nên tự động cấp thêm quyền** chỉ vì metadata có thêm `scopes_supported`. Tương tự, không tự cho phép một signing algorithm yếu/khác loại chỉ vì một capability list thay đổi. Hợp đồng access token và Resource Server policy vẫn cần review/deploy độc lập.

### 28.1. Những thay đổi cần phối hợp với API

| Thay đổi phía AS | Resource Server cần xem xét |
|---|---|
| Issuer URI đổi | Trusted issuer config, rollout hai issuer hay migration |
| JWKS URL đổi | Fetch/caching/TLS/network, rotation |
| Signing algorithm đổi | Algorithm allowlist, key type, decoder support |
| Audience mapping đổi | Expected `aud`, OAuth resource/client request |
| `scope` từ string sang array | Authority converter |
| Tenant claim đổi tên | Claim validator/actor mapper |
| Access token từ JWT sang opaque | Decoder → introspector architecture |
| Token lifetime đổi | Exp/nbf/skew/revocation policy |
| New sender constraint | DPoP/mTLS proof verification |
| Roles structure đổi | Domain permission mapping |
| Client ID behavior đổi | Client allowlist/integration tests |

Không sửa bằng cách tắt validation “cho tương thích”. Cần contract versioning, integration tests và lộ trình chuyển đổi.

## 29. Định nghĩa hợp đồng giữa AS, OAuth Client và Resource Server

Một tài liệu hợp đồng có thể chứa các trường:

```text
Issuer:
  https://login.example.test/realms/shop

Discovery:
  OIDC discovery enabled
  JWKS published at documented URL

Resource:
  Orders API identifier orders-api

Clients:
  shop-web uses authorization_code + PKCE
  trusted-worker uses client_credentials

Token type:
  JWT access token, signed JWS
  RFC 9068 profile enabled if AS supports it

Claims:
  iss: exact issuer
  aud: includes orders-api
  sub: stable subject within issuer namespace
  scope: space-delimited string
  tenant_id: active tenant as string
  exp: required
  nbf: optional per AS profile

Signing:
  RS256 accepted
  JWKS rotation overlap required

API authorization:
  GET /api/orders/** requires orders.read
  POST /api/orders requires orders.write
  Object/tenant ownership verified server-side

Revocation:
  Token TTL and urgent revoke strategy documented

Error contract:
  No/invalid token -> 401 Bearer challenge
  Valid token, insufficient authority -> 403
  Object not visible -> 403/404 per policy
```

Trong thực tế, hợp đồng còn cần quy định **ai sở hữu thay đổi** (AS team vs API team), môi trường staging/prod, TLS certificates, observability, security incident runbook và compatibility window.

### 29.1. Không đưa client secret vào hợp đồng công khai

Tài liệu nên mô tả cách cấp secrets/credentials, không ghi plaintext introspection client secret, private JWK hoặc refresh tokens. Public JWKS là public key material, nhưng private signing keys phải ở hệ thống quản lý khóa của AS.

## 30. Phân quyền HTTP sau khi token đã đúng contract

Token đã vượt:

```text
Signature: valid
Issuer: correct
Audience: orders-api
Expiration: valid
Tenant claim: well formed
```

nhưng client gửi:

```http
DELETE /api/orders/order-42
Authorization: Bearer <VALID_READ_ONLY_TOKEN>
```

Nếu token chỉ có `orders.read` thì HTTP authorization phải từ chối.

Ví dụ Servlet:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll()
)
```

Một câu hỏi khác: caller có `orders.read`, nhưng order-42 thuộc tenant khác. **Object-level authorization** trong service/repository vẫn phải từ chối. Không trộn token contract, action permission và ownership.

### 30.1. 401 và 403 khác nhau

| Failure | Nhóm | HTTP thường gặp |
|---|---|---|
| Thiếu bearer token ở endpoint protected | Chưa xác thực | `401` |
| JWT sai signature/issuer/audience/exp | Token authentication | `401 invalid_token` |
| Opaque token inactive | Token authentication | `401 invalid_token` |
| Token đúng nhưng thiếu `orders.write` | Action authorization | `403` |
| Token đúng scope nhưng order thuộc user/tenant khác | Object authorization | `403` hoặc `404` |
| Service business state không cho cancel | Business rule | Có thể `409` |
| JWKS/introspection outage | Infrastructure/authentication cannot complete | Fail closed; status phụ thuộc exception flow |

Không kết luận một token hết hạn chỉ vì thấy 401; nó còn có thể sai issuer, audience, signature hoặc token type.

## 31. Kiểm tra metadata bằng curl: những gì nên ghi nhận

Một quy trình kiểm tra thủ công khi tích hợp AS:

### Bước 1 — Xác định trusted issuer chính xác

```text
https://login.example.test/realms/shop
```

Đây là cấu hình trước, không lấy từ token chưa xác minh.

### Bước 2 — Lấy metadata của issuer

```bash
curl -i \
  "https://login.example.test/realms/shop/.well-known/openid-configuration"
```

Nếu AS dùng RFC 8414, thử **URL RFC 8414 đúng theo issuer contract**, không suy đoán:

```bash
curl -i \
  "https://login.example.test/.well-known/oauth-authorization-server/realms/shop"
```

Ghi nhận HTTP status, `Content-Type`, TLS certificate validation, giá trị `issuer` và `jwks_uri`.

### Bước 3 — Xác minh metadata issuer

Kỳ vọng:

```text
configured_issuer == metadata.issuer
```

Nếu không khớp, không tự đổi expected issuer bằng nội dung bất kỳ trong metadata; cần kiểm tra base URL/proxy/realm config.

### Bước 4 — Lấy JWKS từ trusted URI

```bash
curl -i \
  "https://login.example.test/realms/shop/protocol/openid-connect/certs"
```

Ghi nhận `keys`, `kid`, key types và thuật toán theo contract. Không copy private key; JWK Set công bố public keys phù hợp.

### Bước 5 — Xin token test đúng flow

OAuth client test dùng authorization_code + PKCE hoặc client_credentials theo loại ứng dụng. Không dùng password grant chỉ để “test nhanh” nếu AS/client không hỗ trợ hoặc policy không cho phép.

### Bước 6 — Kiểm tra claims của token được ký

Sau khi decoder xác minh signature, kiểm tra:

```text
iss
aud
exp
nbf
sub
scope/scp
client_id or azp, if contract
tenant_id, if contract
typ/alg/kid, if contract
```

Không log/raw-upload production token vào hệ thống thiếu tin cậy.

### Bước 7 — Test API negative cases

Token cho Payments API phải bị Orders API từ chối. Token hết hạn/sai issuer/sai signature phải bị từ chối. Token hợp lệ thiếu write scope phải bị 403 khi POST.

## 32. Kiểm thử bằng JWT thật và JWKS giả lập

Unit test token validation khác unit test HTTP authorization.

### 32.1. Test decoder với JWT thực sự được ký

Chuẩn bị test RSA/EC keypair (không dùng production key) và fake JWKS endpoint cung cấp public key. Tạo JWT test được ký bằng private key tương ứng:

| JWT fixture | Signature | Claims | Kỳ vọng |
|---|---|---|---|
| Valid Orders token | Trusted test key | iss/aud/time đúng | Decode thành công |
| Wrong signature | Other key | Claims giống token tốt | Từ chối |
| Unknown `kid` | Không có trong trusted JWKS | Claims đúng | Từ chối |
| Wrong issuer | Trusted signature | `iss` khác | Từ chối |
| Wrong audience | Trusted signature | `aud=payments-api` | Từ chối |
| Expired | Trusted signature | `exp` đã qua | Từ chối |
| Future `nbf` | Trusted signature | Token chưa có hiệu lực | Từ chối |
| Missing tenant required | Trusted signature | Không có tenant | Từ chối theo custom contract |
| Unexpected token type | Trusted signature | Header `typ` sai | Từ chối nếu policy yêu cầu |
| New rotated key | Trusted new key | Claims hợp lệ | Thành công sau JWKS cập nhật phù hợp |

Các tests này phát hiện lỗi decoder/validators mà HTTP tests mô phỏng không phát hiện.

### 32.2. `jwt()` trong Spring Security Test không thay decoder test

Ví dụ MockMvc:

```java
mockMvc.perform(get("/api/orders/order-42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority(
                "SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Đoạn này hữu ích để test HTTP authorization với principal giả lập. Nhưng `jwt()` **thường bypass JWT signature verification**. Nếu muốn biết issuer/JWKS/audience validator hoạt động thật, phải gửi JWT signed fixture qua decoder hoặc test decoder trực tiếp.

Status `200` trong ví dụ cũng phụ thuộc controller/service/test fixtures đã được cấu hình để trả dữ liệu hợp lệ.

### 32.3. Opaque introspection cần fake AS HTTP server

Dùng WireMock/MockWebServer hoặc HTTP stub phù hợp:

- Stub `active=true` với expected audience/scopes/tenant.
- Stub `active=false`.
- Stub audience sai.
- Stub missing required claim.
- Stub timeout, 401 credentials invalid, malformed JSON, 503.
- Gửi request với **real Bearer header** qua Spring Security filter chain.
- Xác nhận introspector thật được gọi; không dùng `mockOpaqueToken()` cho test này.

`mockOpaqueToken()` hữu ích cho test authorization, nhưng bỏ qua HTTP introspection thực tế.

## 33. Test sự phụ thuộc metadata và JWKS

Một test integration với fake issuer có thể mô phỏng:

```text
Trusted issuer test URI
  -> metadata HTTP endpoint
  -> jwks_uri pointing to test JWKS
  -> public test keys
  -> signed JWT requests
```

Những case cần thử:

1. Metadata `issuer` đúng.
2. Metadata `issuer` sai.
3. Discovery endpoint không tồn tại.
4. JWKS trả 200 với public keys hợp lệ.
5. JWKS trả HTML/malformed JSON.
6. TLS/connection/timeout failure (nếu test infrastructure hỗ trợ).
7. Key rotation thêm `kid` mới.
8. Key rotation gỡ key cũ đúng/sai thời điểm.
9. JWT sai algorithm.
10. JWT sai audience.
11. API nhận token issuer khác allowlist.
12. Metadata/JWKS redirect sang host không thuộc trust policy.

Không gọi AS production trong unit tests chỉ để kiểm tra validation, vì network/test credentials/rotation làm tests flaky. Dùng fixtures riêng và môi trường tích hợp có kiểm soát.

### 33.1. Kiểm tra cache JWKS thực tế

Một JWT mới với `kid` mới có thể cần refresh public keys. Test phải mô phỏng đúng JWKS/cache policy của decoder đang dùng. **Không kết luận test key rotation đã thành công chỉ vì decoder nhận một `Jwt` được mock sẵn.**

### 33.2. Không hardcode token vĩnh viễn

Test token chứa `exp` quá xa tương lai hoặc bỏ expiration tùy ý có thể che lỗi timestamp validation. Dùng clock/test fixtures có thời gian phù hợp để kiểm tra cả valid/expired/not-before.

## 34. Kịch bản troubleshooting metadata phổ biến

### 34.1. `/.well-known/openid-configuration` trả 404

Có thể issuer không hỗ trợ OIDC hoặc path khác RFC 8414. Kiểm tra contract và endpoint công bố; không tự tin một endpoint do client gợi ý.

### 34.2. Metadata `issuer` không bằng configured issuer

Có thể sai base path/realm, reverse proxy host/scheme hoặc AS cấu hình public URL sai. Sửa cấu hình AS/proxy/issuer theo hợp đồng; không tắt validation.

### 34.3. `jwks_uri` đúng nhưng JWT vẫn 401

Có thể:

- JWT sai `iss`.
- JWT sai `aud`.
- JWT hết hạn hoặc `nbf` tương lai.
- Key/`kid` không tương ứng.
- Signing algorithm không được phép.
- Token type/profile sai.
- Header JWT/JWS malformed.
- AS phát encrypted token nhưng decoder chỉ hỗ trợ JWS.

**Đọc JWKS thành công không chứng minh token được chấp nhận.**

### 34.4. JWT signature đúng nhưng thiếu scope

Token authentication thành công nhưng route cần authority khác. Đây thường là HTTP 403. Kiểm tra scope cấp thực tế, converter và permission mapping, không chỉnh JWKS.

### 34.5. 401 sau key rotation

Kiểm tra metadata/JWKS URL, thời gian công bố key mới, cache freshness, `kid` và thời gian giữ old key. Không bỏ signature verification để qua sự cố.

### 34.6. Opaque introspection active nhưng API từ chối

Có thể token sai audience, tenant, client allowlist, token type hoặc thiếu required claims. `active=true` không có nghĩa token dành cho mọi Resource Server.

### 34.7. AS timeout và API bị lỗi rộng

Xem network/egress/TLS/introspection credentials, HTTP connection pooling, retry. API phải fail closed; tối ưu caching hoặc degradation chỉ theo risk policy, không tự giả Authentication.

### 34.8. Nhiều applications dùng chung AS nhưng behavior khác

Có thể mỗi Resource Server có expected audience, scope mapping, custom validators hoặc trusted issuer khác nhau. So contract và versions thay vì giả định “cùng login server thì token nào cũng dùng được ở mọi API”.

## 35. Những sai lầm cần tránh

### Sai lầm 1 — Tin mọi issuer vì metadata tồn tại

Attacker có thể triển khai một issuer hợp lệ của họ. Trusted issuer phải được cho phép trước discovery.

### Sai lầm 2 — Lấy `iss` từ unverified JWT rồi fetch arbitrary JWKS

Có thể dẫn đến trust injection/SSRF. Chỉ route trong issuer allowlist; signature và issuer validator phải xác minh sau khi chọn decoder.

### Sai lầm 3 — Nhầm RFC 8414 URL với OIDC Discovery URL

Với issuer có path, vị trí well-known khác nhau. Dùng chuẩn mà AS hỗ trợ và thư viện discovery chính thức.

### Sai lầm 4 — Tin `jwks_uri` nhưng bỏ issuer validation

JWKS là nguồn khóa; JWT claim `iss` vẫn phải đúng expected issuer.

### Sai lầm 5 — Dùng metadata `scopes_supported` làm quyền cho caller

Đó là danh sách capabilities, không phải scopes đã được cấp trong một token cụ thể.

### Sai lầm 6 — Dùng `id_token_signing_alg_values_supported` như access-token alg allowlist

Thông tin đó dành cho ID token. Hợp đồng access token phải độc lập.

### Sai lầm 7 — Chấp nhận JWT chỉ vì có `sub`

Payload chưa xác thực có thể bị sửa. Kể cả đã ký, token vẫn cần audience, type/time/scopes.

### Sai lầm 8 — Chấp nhận ID token tại API

ID token dành cho OIDC client. API cần access token đúng audience và profile.

### Sai lầm 9 — Dùng `client_id` thay `aud`

Client có thể gọi nhiều APIs. Token phải dành cho chính Resource Server.

### Sai lầm 10 — Không kiểm tra `typ` khi hợp đồng yêu cầu

Một issuer ký nhiều JWT types. Cross-JWT confusion có thể xảy ra nếu chỉ dựa vào signature.

### Sai lầm 11 — Để thuật toán JWT do untrusted header quyết định

Chỉ cho algorithms phù hợp key/issuer contract; không chấp nhận `none` cho JWT bearer API.

### Sai lầm 12 — Dùng `jku`/`x5u` từ token để tải khóa

URL khóa phải đến từ trusted configuration/metadata, không từ token do caller tạo.

### Sai lầm 13 — Khi thêm audience validator làm mất default checks

Kết hợp `JwtValidators.createDefaultWithIssuer(...)` với custom validators, không vô tình xóa issuer/timestamp policy.

### Sai lầm 14 — Tự điền tenant/audience cho token thiếu claim

Điều đó biến một token sai contract thành token được API chấp nhận. Thỏa thuận lại với AS hoặc từ chối.

### Sai lầm 15 — Dùng `active=true` cho mọi API

Opaque token có thể active nhưng dành cho resource khác. Cần kiểm tra AS contract về audience/resource binding.

### Sai lầm 16 — Không phân biệt introspection credentials với OAuth caller client ID

Hai client IDs thuộc hai vai trò khác nhau. Không so sánh bằng nhau tùy tiện.

### Sai lầm 17 — Hardcode key rồi quên rotation

Khóa cũ/new key không đồng bộ gây outage; cần JWKS/cache/rotation plan.

### Sai lầm 18 — Khi metadata/JWKS timeout thì tự tạo principal

Đó là *fail open*. Không thể tin token nếu chưa xác minh được.

### Sai lầm 19 — Tự động cấp thêm quyền khi metadata thay đổi

Metadata mới có scope mới không có nghĩa users có scope đó. Authorization dựa trên token và policy.

### Sai lầm 20 — Chỉ kiểm thử bằng `jwt()`/`mockJwt()`

Mocks không chứng minh signature/JWKS/issuer/audience checks. Cần signed token integration tests.

### Sai lầm 21 — Xem scope đọc là quyền xem mọi bản ghi

Action permission không thay object-level authorization, ownership hoặc tenant.

### Sai lầm 22 — Log raw access token và secrets

Bearer token và introspection secrets là credentials. Không đưa vào logs, crash reports hoặc ticket.

### Sai lầm 23 — Bỏ qua network/TLS/DNS và egress policy

Discovery/JWKS/introspection là outbound HTTP calls. Cần truststore, timeouts, retries/circuit breaking phù hợp.

### Sai lầm 24 — Đồng nhất nhiều issuers có cùng subject

`sub` nên được hiểu trong issuer namespace; tránh trộn identity đa nhà phát hành.

## 36. Runbook tích hợp nhà phát hành cho Orders API

**Bước 1 — Ghi trusted issuer:** Xác nhận exact URL, environment, authority owner và đường dẫn OIDC/OAuth metadata được hỗ trợ.

**Bước 2 — Đọc metadata:** Xác minh HTTPS/TLS, HTTP status, `issuer` và `jwks_uri` hoặc `introspection_endpoint`.

**Bước 3 — Chọn token mode:** JWT hay opaque? Nếu JWT, signing key source và algorithms nào? Nếu opaque, introspection credentials và network contract nào?

**Bước 4 — Chốt resource audience:** Orders API có expected `aud=orders-api` hoặc identifier khác? OAuth client xin đúng token cho tài nguyên nào?

**Bước 5 — Chốt token type/profile:** Có RFC 9068 không, `typ` là gì, `exp`/`nbf` bắt buộc thế nào, có sender constraint không?

**Bước 6 — Chốt permissions:** `scope`/`scp`/custom roles/permissions, tiền tố authorities, rights theo tenant hay global.

**Bước 7 — Chốt identity:** `sub` namespace, service principals, tenant membership, claim conversions và object-level authorization.

**Bước 8 — Cấu hình Spring Security:** `issuer-uri` hoặc `jwk-set-uri` + validators, hoặc opaque introspection + contract wrapper. Giữ default deny.

**Bước 9 — Kiểm thử tiêu cực:** Wrong issuer, audience, expired, invalid signature, wrong typ, wrong alg, missing claims, scope không đủ, cross-tenant access.

**Bước 10 — Kiểm thử biến cố:** JWKS rotation, AS outage, introspection timeout, changed metadata, clock skew, stale token.

**Bước 11 — Quan sát:** 401/403 phân loại, metadata/JWKS HTTP latency, key-cache miss, issuer mapping, request ID; không log credentials.

**Bước 12 — Quản trị thay đổi:** Có contract version, chính sách rollout/rollback khi issuer đổi signing alg, claims, key, audience hoặc token format.

Quy trình này giúp tránh việc chỉ đọc metadata rồi cho rằng Resource Server đã an toàn.

## 37. Một ví dụ end-to-end

Giả sử AS công bố:

```text
Trusted issuer:
  https://login.example.test/realms/shop

Trusted JWKS:
  https://login.example.test/realms/shop/protocol/openid-connect/certs

Orders Resource Server:
  expected aud = orders-api
  accepted alg = RS256
  access-token type = at+jwt (theo hợp đồng AS)
  required scope for GET orders = orders.read
```

Client gửi:

```http
GET /api/orders/order-42
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

JWT có:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "shop-a",
  "exp": 1900000000
}
```

Resource Server cần xác minh theo thứ tự logic:

```text
1. Bearer token có đúng format được hỗ trợ không?
2. JWS có signature hợp lệ với trusted key không?
3. Signing algorithm có được phép không?
4. JWT type/profile có đúng access-token contract không?
5. iss có đúng trusted issuer không?
6. aud có chứa orders-api không?
7. exp/nbf và các claims required có hợp lệ không?
8. Authentication có SCOPE_orders.read không?
9. user-123 có quyền đọc order-42 trong shop-a không?
10. Response có lọc fields đúng policy không?
```

**Nếu bước 2–7 thất bại:** token không được xác thực; thường phản hồi 401 theo Bearer semantics.

**Nếu bước 8 thất bại:** token hợp lệ nhưng không có quyền thao tác; thường phản hồi 403.

**Nếu bước 9 thất bại:** token đúng nhưng tài nguyên không thuộc quyền; phản hồi 403 hoặc 404 theo policy để tránh tiết lộ sự tồn tại.

Nếu token có `aud=["payments-api"]`, dù metadata và JWKS đều đúng, Orders API phải từ chối. **Đọc metadata đúng mới là điều kiện để xác minh token; không phải kết luận token nào cùng issuer cũng hợp lệ ở API.**

## 38. Tài liệu tham khảo

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata và well-known discovery cho OAuth Authorization Server.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `openid-configuration`, OpenID Provider metadata và issuer discovery.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC ID token và khác biệt với OAuth access token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set và các thuộc tính key.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký JWS và protected headers.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWT/JWE encryption model.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thuật toán, issuer/key trust và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile, claims và typ.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection cho opaque/access tokens.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu access token dành cho resource cụ thể.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange/delegation khi cần token downstream với audience khác.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS sender-constrained tokens.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP sender constraints.
- [Spring Security Reference — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWKS, decoder, validators và scope mapping.
- [Spring Security Reference — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và custom `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, WebFlux issuer/JWKS.
- [Spring Security Reference — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): introspection trong WebFlux.
- [Spring Security Reference — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): action-level authorization sau authentication.

**Kết luận:** Tích hợp một OAuth 2.0/OIDC issuer vào Spring Security Resource Server gồm **hai hợp đồng liên quan nhưng không trùng nhau**. Metadata (RFC 8414/OIDC Discovery) giúp xác định issuer, endpoints và trusted JWKS/introspection infrastructure. Hợp đồng access token xác định JWT/opaque format, signing algorithms, type/profile, issuer, audience, thời gian, subject, scopes, tenant và các quy tắc riêng của API. Resource Server phải **tin issuer trước khi discovery**, xác minh token trước khi dùng claims, kiểm tra đúng audience và action/object authorization, đồng thời fail closed khi metadata/JWKS/introspection không thể xác thực. **Một metadata document đúng không làm mọi token của cùng issuer trở thành access token hợp lệ cho API.**
