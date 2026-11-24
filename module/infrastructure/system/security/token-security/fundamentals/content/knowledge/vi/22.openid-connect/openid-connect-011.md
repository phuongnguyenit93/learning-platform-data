# Discovery metadata

**Discovery metadata** trong **OpenID Connect (OIDC)** là tài liệu JSON do **OpenID Provider (OP)** công bố để một **Relying Party (RP)/OIDC Client** biết **issuer**, các endpoint giao thức, vị trí tập khóa công khai **JWKS**, những response type, kiểu subject và thuật toán ký ID token mà OP hỗ trợ. Thay vì tự nhập từng URL của authorization endpoint, token endpoint, UserInfo endpoint và JWKS, client có thể lấy cấu hình chuẩn qua **OpenID Connect Discovery 1.0**.

Bài học thuộc chương **OpenID Connect** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ mô hình tin cậy, vòng đời token, JWT và opaque token, access/refresh/ID token, xác thực–phân quyền OAuth 2.0/OIDC, các claim như `iss`/`aud`/`exp`, scope, audience, lưu trữ và thu hồi. Đề bài tập trung vào **Discovery metadata**, không biến tài liệu cấu hình thành cơ chế xác thực hay cấp quyền.

**Nguyên tắc quan trọng:** **discovery cho biết OP tự công bố điều gì**, nhưng **không tự khiến OP đó đáng tin**. Client phải xác định **issuer được tin cậy từ cấu hình/chính sách ban đầu**, truy cập metadata an toàn, **so khớp `issuer` chính xác**, kiểm soát endpoint/thuật toán rồi mới dùng khóa từ `jwks_uri` để xác minh token. Cấu hình có nhiều URL nhìn “hợp lệ” nhưng trỏ đến OP của attacker **không được trở thành trust anchor chỉ vì trả HTTP 200**.

## 1. Discovery metadata giải quyết vấn đề gì?

Hãy xét ứng dụng Java `orders-web` cần đăng nhập người dùng qua OIDC và gọi Orders API bằng OAuth access token. Ứng dụng phải biết ít nhất:

- **Issuer của OP** dự kiến nhận đăng nhập: định danh chính xác bên phát ID token.
- **Authorization endpoint**: URL browser được chuyển đến để user login/consent.
- **Token endpoint**: URL client đổi authorization code lấy token.
- **JWKS URI**: nơi lấy public key đã được OP công bố để xác minh chữ ký ID token.
- **Các khả năng giao thức**: hỗ trợ `response_type=code` không, có PKCE S256 không, ID token dùng thuật toán nào, phương thức client authentication nào phù hợp.
- **UserInfo endpoint**, nếu cần lấy claims người dùng qua access token.

Nếu nhập các URL thủ công ở nhiều nơi, có thể trỏ nhầm issuer, dùng sai endpoint sau thay đổi cấu hình hoặc bỏ sót key rotation. **Discovery** chuẩn hóa tài liệu các metadata này.

~~~mermaid
flowchart LR
    RP["OIDC Client / Relying Party"]
    CFG["Trusted issuer từ cấu hình"]
    OP["OIDC Provider"]
    MD[("OIDC configuration JSON")]
    JWKS[("Public JWK Set")]
    API["Resource Server"]

    CFG -->|"Issuer identifier đã được chọn"| RP
    RP -->|"GET /.well-known/openid-configuration qua HTTPS"| OP
    OP --> MD
    MD -->|"issuer, endpoints, algorithms, jwks_uri"| RP
    RP -->|"GET jwks_uri qua HTTPS"| JWKS
    JWKS -->|"Public keys"| RP
    RP -->|"Authorization Code + PKCE"| OP
    OP -->|"ID token + access token"| RP
    RP -->|"Xác minh ID token bằng metadata + JWKS"| RP
    RP -->|"Access token cho đúng audience"| API
~~~

**Discovery không cấp token**, không xác thực user, không tạo authorization grant và không mặc định cho client quyền gọi API. Nó chỉ giúp client cấu hình **các bước khác** đúng chuẩn.

### Các tên thường gặp

| Thuật ngữ | Ý nghĩa |
|---|---|
| **OP (OpenID Provider)** | Authorization Server có khả năng OIDC, phát ID token |
| **RP (Relying Party)** | Ứng dụng tin OP để xác thực người dùng qua OIDC |
| **Issuer Identifier** | Giá trị HTTPS định danh OP, cũng là claim `iss` dự kiến trong ID token |
| **Provider Configuration Document** | JSON ở URL well-known dùng cho OIDC Discovery |
| **JWKS (JSON Web Key Set)** | Tập khóa công khai do OP công bố; thường phục vụ verify JWT/JWS |
| **Metadata field** | Tên–giá trị chuẩn hóa như `authorization_endpoint`, `jwks_uri` |
| **Discovery bootstrap** | Bước lấy cấu hình từ issuer đã tin hoặc qua discovery động có policy |

## 2. Từ issuer đến địa chỉ /.well-known/openid-configuration

Với issuer đơn giản:

~~~text
Issuer:
    https://login.example.test

OIDC Provider Configuration URL:
    https://login.example.test/.well-known/openid-configuration
~~~

Với issuer có path, **theo quy tắc OIDC Discovery 1.0**, gắn hậu tố `/.well-known/openid-configuration` **sau path của issuer**:

~~~text
Issuer:
    https://login.example.test/realms/shop

OIDC Provider Configuration URL:
    https://login.example.test/realms/shop/.well-known/openid-configuration
~~~

Đây là ví dụ **địa chỉ giả dùng cho học tập**, không đại diện một nhà cung cấp thực tế.

**Điều kiện đối với Issuer Identifier OIDC:**

- Là HTTPS URL có host; có thể có path.
- Không có **query** hoặc **fragment**.
- Phân biệt chính xác giá trị nhận dạng: `https://login.example.test/realms/shop` khác `https://login.example.test/realms/admin`.
- Client không tự tiện bỏ path, thêm slash, đổi tenant, viết lại scheme hoặc thay host chỉ vì một URL khác “gần giống”.
- Khi triển khai, chọn đúng quy tắc URL theo **OIDC Discovery**; chuẩn **OAuth 2.0 Authorization Server Metadata (RFC 8414)** có quy tắc đặt well-known cho issuer có path **khác OIDC**.

Ví dụ sai:

~~~text
Cấu hình issuer tin cậy:
    https://login.example.test/realms/shop

Metadata trả:
    "issuer": "https://login.example.test/realms/admin"

Kết quả:
    REJECT — issuer mismatch, dù cùng host và HTTPS.
~~~

**Không dùng metadata để tự ý đổi issuer đã tin:** nếu metadata trả issuer khác, client phải **từ chối discovery hoặc lỗi cấu hình**, không silently thay `expectedIssuer` bằng giá trị response.

## 3. Chuỗi thao tác từ bootstrap đến xác minh ID token

~~~mermaid
sequenceDiagram
    autonumber
    participant APP as Java OIDC Client
    participant CFG as Trusted configuration
    participant OP as OpenID Provider
    participant JWKS as Public JWK Set endpoint
    participant B as User Browser

    APP->>CFG: Đọc expected issuer, client registration, allowed algorithms
    CFG-->>APP: https://login.example.test/realms/shop
    APP->>OP: GET issuer/.well-known/openid-configuration
    OP-->>APP: JSON issuer/endpoints/jwks_uri/capabilities
    APP->>APP: Validate HTTPS, exact issuer, endpoint policy
    APP->>JWKS: GET jwks_uri (TLS, bounded fetch)
    JWKS-->>APP: Public signing keys
    APP->>APP: Cache metadata/keys theo issuer, expiry và policy
    APP->>B: Redirect đến trusted authorization_endpoint
    B->>OP: Authorization Code + PKCE
    OP-->>B: Redirect code + state
    B-->>APP: OAuth callback
    APP->>OP: POST code + PKCE verifier tại token_endpoint
    OP-->>APP: ID token (+ access/refresh token theo grant)
    APP->>APP: Verify signature + iss + aud + exp/iat + nonce nếu dùng
    APP-->>B: Tạo ứng dụng session theo policy
~~~

Mỗi bước có nhiệm vụ riêng:

1. **Bootstrap trust**: chọn issuer và client đã đăng ký từ cấu hình đáng tin.
2. **Discovery**: tải metadata từ issuer qua HTTPS, đối chiếu `issuer` và khả năng.
3. **Key discovery**: lấy public keys tại `jwks_uri` đã được chấp thuận theo chính sách.
4. **Authorization Code + PKCE**: thực hiện login/consent và code exchange.
5. **ID token validation**: verify chữ ký và claims. Chỉ sau bước này mới dùng kết quả authentication.
6. **API authorization**: Resource Server độc lập kiểm tra access token, audience, scope và quyền đối tượng.

**Không có bước nào cho phép RP tin JWT chỉ vì payload có `iss` đúng mà chưa kiểm tra chữ ký bằng khóa tin cậy.**

## 4. Ví dụ OIDC Discovery JSON hoàn chỉnh

Ví dụ một response từ:

~~~http
GET /realms/shop/.well-known/openid-configuration HTTP/1.1
Host: login.example.test
Accept: application/json
~~~

Response HTTP minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "metadata-v3"
~~~

JSON minh họa một OP hỗ trợ **Authorization Code + PKCE**:

~~~json
{
  "issuer": "https://login.example.test/realms/shop",
  "authorization_endpoint": "https://login.example.test/realms/shop/oauth2/authorize",
  "token_endpoint": "https://login.example.test/realms/shop/oauth2/token",
  "userinfo_endpoint": "https://login.example.test/realms/shop/oidc/userinfo",
  "jwks_uri": "https://login.example.test/realms/shop/keys",
  "response_types_supported": [
    "code"
  ],
  "response_modes_supported": [
    "query",
    "form_post"
  ],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token"
  ],
  "subject_types_supported": [
    "public",
    "pairwise"
  ],
  "id_token_signing_alg_values_supported": [
    "RS256",
    "ES256"
  ],
  "scopes_supported": [
    "openid",
    "profile",
    "email",
    "orders:read"
  ],
  "claims_supported": [
    "sub",
    "iss",
    "aud",
    "exp",
    "iat",
    "auth_time",
    "nonce",
    "email",
    "email_verified"
  ],
  "token_endpoint_auth_methods_supported": [
    "none",
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": [
    "S256"
  ],
  "revocation_endpoint": "https://login.example.test/realms/shop/oauth2/revoke",
  "end_session_endpoint": "https://login.example.test/realms/shop/oidc/logout",
  "authorization_response_iss_parameter_supported": true
}
~~~

**Đây là tài liệu giả để học**, không phải endpoint hoặc metadata của một OP thật. Một OP thực có thể công bố tập trường khác, thêm extension hoặc bỏ nhiều trường **optional**.

**Phân biệt “đã quảng bá” với “được phép”:** `scopes_supported` cho biết scope OP có thể hiểu; **không** chứng minh client `orders-web` đã được cấp tất cả scope đó. `grant_types_supported` cho biết năng lực của OP, không tự cấp mọi grant cho mọi client.

## 5. Những trường quan trọng và yêu cầu theo OIDC Discovery

Một số trường bắt buộc trong OpenID Connect Discovery 1.0:

| Trường | Mức yêu cầu/chú ý | Công dụng |
|---|---|---|
| **`issuer`** | **REQUIRED** | OP identifier; phải khớp issuer đã cấu hình và claim `iss` của ID token |
| **`authorization_endpoint`** | **REQUIRED** | Điểm vào authorization request qua browser |
| **`token_endpoint`** | **REQUIRED**, trừ trường hợp OP chỉ dùng Implicit Flow theo OIDC Discovery | Điểm đổi code và các token grants tương ứng |
| **`jwks_uri`** | **REQUIRED** | URL public keys phục vụ xác minh JWT/JWS |
| **`response_types_supported`** | **REQUIRED** | Response types OP hỗ trợ, ví dụ `code` |
| **`subject_types_supported`** | **REQUIRED** | `public`, `pairwise` subject identifier hoặc cả hai |
| **`id_token_signing_alg_values_supported`** | **REQUIRED** | JWS algorithms OP hỗ trợ để ký ID token; `RS256` phải nằm trong danh sách theo OIDC Discovery |

Các trường tùy chọn/khuyến nghị thường gặp:

| Trường | Công dụng | Rủi ro hiểu sai |
|---|---|---|
| `userinfo_endpoint` | UserInfo API; được khuyến nghị trong Discovery | Không phải client nào cũng cần gọi |
| `registration_endpoint` | Dynamic Client Registration khi OP hỗ trợ | Không được tự động đăng ký client ở bất kỳ OP lạ |
| `scopes_supported` | Các scope OP công bố | Không đảm bảo user consent hoặc client entitlement |
| `claims_supported` | Những claims OP có thể cung cấp | Không đảm bảo token/UserInfo luôn có mọi claim |
| `response_modes_supported` | Cách đóng gói authorization response | Cần client hỗ trợ, không suy từ response type |
| `grant_types_supported` | Các OAuth grants OP hỗ trợ | Client còn bị registration/policy giới hạn |
| `token_endpoint_auth_methods_supported` | Phương thức client auth được hỗ trợ | `none` chỉ phù hợp public client được đăng ký; `client_id` không phải secret |
| `code_challenge_methods_supported` | Phương thức PKCE quảng bá theo metadata extension | Không thay thực thi kiểm tra PKCE tại AS |
| `id_token_encryption_alg_values_supported` và `...enc...` | Thuật toán JWE ID token nếu triển khai | Phân biệt **encryption** với **signing** |
| `end_session_endpoint` | Extension OIDC logout/profile | Không phải endpoint OIDC Core bắt buộc |
| `revocation_endpoint` | OAuth Token Revocation (RFC 7009) | Không đảm bảo JWT đang được API xác minh offline sẽ bị chặn ngay |
| `introspection_endpoint` | OAuth Token Introspection (RFC 7662) nếu có | Không mặc định mọi API phải introspect JWT |
| `device_authorization_endpoint` | Device Grant RFC 8628 nếu hỗ trợ | Không thuộc Authorization Code flow mặc định |
| `authorization_response_iss_parameter_supported` | AS hỗ trợ `iss` trong authorization response theo RFC 9207 | Phải xử lý đúng mix-up, không chỉ đọc boolean |

Các giá trị mặc định được một số profile/chuẩn định nghĩa cho **trường optional vắng mặt**. Không nên tự kết luận “thiếu metadata tức là endpoint/feature không tồn tại” hoặc “thiếu nghĩa là bật”. Thư viện OIDC/OAuth phải áp dụng **đúng default của chuẩn và đúng chính sách client**; với thuật toán và grant nhạy cảm, ưu tiên allowlist cấu hình rõ ràng.

## 6. issuer là ranh giới tin cậy quan trọng nhất

**`issuer` là định danh logic của OP**, không chỉ là một hostname “tương tự”. Trong ID token OIDC, claim `iss` phải bằng giá trị issuer dự kiến.

Một RP cấu hình:

~~~text
EXPECTED_ISSUER:
https://login.example.test/realms/shop
~~~

Có thể gặp metadata:

| Metadata `issuer` | Kết quả | Vì sao |
|---|---|---|
| `https://login.example.test/realms/shop` | Có thể chấp nhận sau các kiểm tra khác | Khớp chính xác |
| `https://login.example.test/realms/admin` | **Từ chối** | Sai tenant/path |
| `https://login.example.test/realms/shop/` | **Từ chối** nếu expected không có slash | Khác chuỗi issuer |
| `http://login.example.test/realms/shop` | **Từ chối** | Không dùng HTTPS issuer |
| `https://attacker.example.test` | **Từ chối** | Không phải issuer đã cấu hình |
| `https://login.example.test/realms/shop?x=1` | **Từ chối** | Issuer OIDC không có query |
| URL có `#fragment` | **Từ chối** | Issuer OIDC không có fragment |

**Không tự chuẩn hóa để “sửa” issuer mismatch** bằng cách thêm/bỏ slash hoặc đổi tenant, vì có thể biến một OP không được chọn thành OP đáng tin. Quy tắc so khớp issuer trong OIDC là **exact string match** với Issuer Identifier.

### Tenant và cache

Với môi trường nhiều tenant/issuer, **cache metadata và JWKS theo issuer cụ thể**, không chỉ theo hostname hoặc `kid`. Hai tenant cùng host có thể có chính sách và key sets khác nhau. Cấu hình nhầm cache có thể cho phép token của tenant A được kiểm tra bằng cấu hình của tenant B.

## 7. Lấy metadata qua HTTPS chưa đủ nếu bootstrap sai

HTTPS/TLS giúp bảo vệ việc client giao tiếp với host của OP, nhưng **nếu client lấy host từ dữ liệu do attacker tự cung cấp rồi tin tất cả nội dung**, TLS chỉ xác thực máy chủ của attacker.

Thiết kế an toàn:

1. **Tin issuer do quản trị/configuration chọn trước** (pinned) hoặc đi qua discovery động với trust policy rõ.
2. Chỉ dùng **HTTPS**, validate chứng chỉ, hostname và TLS; không tắt certificate verification khi lỗi.
3. Tải URL well-known của issuer; không tự chuyển sang URL trong response làm issuer mới.
4. Hạn chế **redirect** của HTTP client khi fetch metadata/JWKS; nếu cần redirect, kiểm tra toàn bộ destination theo cùng chính sách.
5. Giới hạn response size, timeout, content type, JSON parser depth và tài nguyên bị dùng để phòng DoS.
6. Kiểm tra **exact issuer**, dữ liệu bắt buộc, giá trị enum và endpoint scheme/host theo policy.
7. Cố định **allowlist thuật toán, client authentication và grant** do ứng dụng cho phép.
8. Cache ngắn hạn/có kiểm soát, log event cấu hình không có secret và giám sát thay đổi bất thường.

**Không tải bất kỳ URL nào từ user-input/email để tìm “issuer của người dùng” mà thiếu kiểm soát SSRF và tenant allowlist.** Discovery là HTTP client fetch một tài nguyên mạng; nó có đầy đủ rủi ro **SSRF**, DNS rebinding và truy cập metadata service nội bộ nếu URL không được hạn chế.

## 8. jwks_uri chứa gì và không chứa gì?

`jwks_uri` trỏ đến **JSON Web Key Set (JWKS)** mà OP công bố. Các public key trong đó thường dùng để RP xác minh **chữ ký JWS của ID token**.

Ví dụ cấu trúc JWKS minh họa (khóa **không có giá trị mật mã thật**):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sig-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_BASE64URL_PLACEHOLDER",
      "e": "AQAB"
    }
  ]
}
~~~

- `kty=RSA` là họ khóa. Với EC, JWK có cấu trúc khác như `crv`, `x`, `y`.
- `kid` là **key identifier dùng chọn ứng viên khóa**, không phải secret hay dấu xác nhận khóa đáng tin.
- `use=sig` biểu thị mục đích ký (khi được công bố).
- `alg=RS256` giúp mô tả thuật toán dự kiến (khi có), **không cho phép client bỏ allowlist thuật toán riêng**.
- `n`/`e` chứa thành phần **public RSA key**; chuỗi placeholder trên **không** phải một modulus hợp lệ.
- JWKS công khai **không được chứa private key material** như `d`, `p`, `q`.

**JWKS URI không nhất thiết cùng origin với issuer ở mọi deployment.** Điều quan trọng là URL đến từ **metadata của issuer tin cậy**, được fetch qua kênh an toàn và **được chấp thuận trong chính sách**. Với sản phẩm chỉ cho một host, có thể enforce same-host; với OP công bố key host khác, cần allowlist/chấp thuận rõ ràng chứ không mở truy cập đến host bất kỳ.

### Không tin URL từ JWT header

Một JWT có thể có header:

~~~json
{
  "alg": "RS256",
  "kid": "sig-key-2026-11",
  "typ": "JWT"
}
~~~

Client chỉ dùng `kid` để chọn khóa từ **JWKS đã gắn với issuer tin cậy**. Không tự fetch URL mà attacker nhúng vào `jku`, `x5u` hoặc trường tùy ý của token rồi coi đó là nguồn khóa mới.

**`kid` không chứng minh chữ ký đúng.** Phải dùng crypto verification với algorithm/key type cho phép; không chỉ so khớp tên khóa hay decode Base64url payload.

## 9. Xác minh ID token bằng metadata và JWKS

ID token là **JWT** do OP phát cho **OIDC Client** để biểu thị kết quả authentication. RP nên dùng thư viện JOSE/OIDC được duy trì, không tự triển khai phép RSA/ECDSA/JWS khi xây dựng ứng dụng.

Một ID token payload **minh họa chưa có chữ ký**:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-pseudonym-8f2",
  "aud": "orders-web",
  "exp": 1800003600,
  "iat": 1800000000,
  "nonce": "nonce-from-request-if-used",
  "email_verified": true
}
~~~

**Đây chỉ là JSON payload học tập**, không phải JWT có thể được tin hoặc dùng đăng nhập. `exp`/`iat` là con số minh họa; kiểm tra thực tế phải dùng clock hiện tại và thời gian hợp lệ theo policy.

### Các điều kiện cần kiểm tra

| Kiểm tra | Thực hiện như thế nào? | Nếu bỏ qua |
|---|---|---|
| **Signature** | Chỉ dùng khóa public đã lấy và ràng buộc với issuer/alg được phép | Chấp nhận token giả mạo |
| **`iss`** | **Khớp chính xác** configured/discovered issuer | Nhầm OP/tenant |
| **`aud`** | Có client ID của RP; xử lý `azp` khi profile yêu cầu | Nhận token cấp cho app khác |
| **`exp`** | Token chưa hết hạn theo clock/skew policy | Nhận token cũ |
| **`iat`** | Giá trị thời gian hợp lệ theo profile/policy | Nhận token có thời gian bất thường |
| **`nonce`** | Nếu đã gửi nonce, kiểm tra claim tương ứng theo OIDC profile | Tăng nguy cơ token replay/mix-up |
| **`auth_time`/ACR/AMR** | Kiểm tra khi client cần reauthentication/assurance policy | Nhầm mức xác thực |
| **`sub`** | Subject hợp lệ, nhận dạng cùng `iss` và loại subject | Nhầm user giữa OP/tenant |
| **`at_hash`/`c_hash`** | Kiểm tra khi flow/profile áp dụng | Mất binding với access token/code trong các flow tương ứng |

**Access token không phải ID token.** Một JWT access token có thể cũng chứa `iss`/`aud`/`sub`, nhưng `aud` của nó thường là **Resource Server**, không phải client ID của RP. RP **không dùng access token như ID token**; Resource Server **không chấp nhận ID token làm credential gọi API**.

### Pseudocode verification

~~~text
verifyOidcIdToken(jwt, transaction, trustedProvider):
    reject malformed token / unsupported typ or alg per profile
    header = parseUntrustedHeader(jwt)
    require header.alg in clientAllowedIdTokenAlgorithms
    jwks = cachedKeysFor(trustedProvider.issuer)

    candidateKey = selectKeyByKidAndKeyType(jwks, header.kid, header.alg)
    require candidateKey is from trusted JWKS for expected issuer
    verifyJwsSignature(jwt, candidateKey, header.alg)

    claims = parseVerifiedPayload(jwt)
    require claims.iss == trustedProvider.issuer
    require claims.aud contains registered client_id
    validate azp if required by OIDC Core
    require claims.exp valid and claims.iat valid under policy
    if transaction.usedNonce:
        require claims.nonce == transaction.expectedNonce
    validate auth_time/acr/amr and at_hash/c_hash when applicable
    establish authentication for (issuer, subject) only after PASS
~~~

**Pseudocode, không phải API thư viện có sẵn.** Claim check phải tuân đúng OIDC profile, crypto library và context của authorization response; không chỉ sao chép các bước như một “JWT parser homemade”.

## 10. Thuật toán và phản ứng với alg=none

`id_token_signing_alg_values_supported` cho biết OP quảng bá khả năng ký ID token. Nhưng **client chỉ chấp nhận những thuật toán phù hợp registration/security policy**.

Ví dụ client policy:

~~~text
OP metadata advertises:
    ["RS256", "ES256"]

Client allowed ID token algorithms:
    ["RS256"]

Negotiated/use-allowed:
    ["RS256"]
~~~

Không nên:

- Để JWT header `alg` tự quyết định thuật toán có được tin hay không.
- Chấp nhận `alg=none` chỉ vì parser trả về payload đọc được.
- Dùng một khóa đối xứng HS256 để “verify” chữ ký RS256 bằng bytes của public key (algorithm confusion).
- Tự chuyển sang thuật toán yếu nếu metadata thiếu thuật toán client hỗ trợ.
- Lấy public key từ `jku` do token đưa ra.
- Dùng client secret làm RSA public key hoặc đảo mục đích key.

**OIDC cho phép một số profile/cấu hình đặc thù liên quan `none`**, nhưng không được coi nó là lựa chọn an toàn mặc định. Với ứng dụng dùng ID token ký bất đối xứng, cấu hình **allowlist rõ** như RS256/ES256 theo registration, yêu cầu chữ ký và từ chối header/metadata không khớp.

**Discovery không phải “cho phép tất cả thuật toán được quảng bá”**. Policy của client **phải giới hạn tập được phép**, và OP vẫn cần gắn thuật toán vào registration/cấu hình phù hợp.

## 11. JWKS rotation, caching và unknown kid

OP cần xoay khóa ký định kỳ hoặc khi sự cố. RP không nên đóng đinh một public key mãi mãi, nhưng cũng không được **refresh JWKS vô hạn theo `kid` do attacker chọn**.

~~~mermaid
sequenceDiagram
    autonumber
    participant OP as OpenID Provider
    participant CACHE as RP JWKS cache
    participant RP as RP Token Verifier

    OP->>OP: Đang ký bằng K1
    CACHE->>OP: GET jwks_uri
    OP-->>CACHE: JWKS public K1 (cache headers)
    OP->>OP: Công bố K2 trước khi dùng
    CACHE->>OP: Refresh theo cache policy
    OP-->>CACHE: JWKS gồm K1 và K2
    OP->>RP: ID token ký K2
    RP->>CACHE: Tìm kid K2 từ issuer tin cậy
    CACHE-->>RP: Public K2
    RP->>RP: Verify signature + iss/aud/exp/nonce
    OP->>OP: Đợi token K1 hết hạn rồi bỏ K1 theo policy
~~~

### Nguyên tắc rotation

1. **Cache theo issuer/JWKS URI và chính sách thuật toán**, không gộp khóa hai tenant vì `kid` trùng.
2. Dùng HTTP caching hints (`Cache-Control`, `ETag`) khi thích hợp, nhưng giới hạn min/max TTL theo security policy.
3. Khi gặp **unknown `kid`**, có thể kích hoạt **một lần refresh có rate limit** và chống stampede. Không mở fetch mới cho từng token/header attacker.
4. Không dùng JWKS stale vô thời hạn nếu key đã bị thu hồi; đồng thời cân nhắc khả năng availability khi OP tạm lỗi.
5. OP nên **công bố key mới trước khi ký**, và duy trì key cũ cho đến khi token hợp lệ đã ký bằng nó hết hiệu lực, trừ khi revoke khẩn cấp.
6. Nếu metadata `jwks_uri` đổi bất thường, cần đánh giá và quan sát thay vì âm thầm tin URL bất kỳ.
7. Cơ chế revoke khẩn cấp phải có policy riêng: **cache không tự biết key đã bị compromise** nếu chưa refresh.

**JWKS rotation không bằng refresh token rotation.** JWKS là khóa ký ID token/JWT; refresh-token rotation là cách AS giảm replay đối với **credential xin token mới**.

## 12. Endpoint discovery không thay thế client registration

OP có thể quảng bá:

~~~json
{
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token"
  ],
  "token_endpoint_auth_methods_supported": [
    "none",
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Nhưng `orders-web` vẫn cần registration:

~~~text
client_id                 = orders-web
redirect_uri              = https://app.example.test/auth/callback
grant_type                = authorization_code
response_type             = code
token_endpoint_auth       = private_key_jwt (nếu được đăng ký)
PKCE                      = S256
allowed_scopes            = openid profile orders:read (theo policy)
~~~

**Phân biệt:**

- **Provider metadata:** năng lực **chung** của OP.
- **Client registration:** những gì **client cụ thể được phép** và phải thực hiện.
- **Authorization request:** những quyền/grant client muốn sử dụng trong **transaction cụ thể**.
- **Consent/policy:** những quyền OP thực sự chấp thuận.
- **Token claims:** những quyền/audience mà AS **đã cấp**.

Nếu metadata có `private_key_jwt` nhưng client chỉ được đăng ký `client_secret_basic`, client không thể tự đổi phương thức auth chỉ vì OP quảng bá. Với **public SPA/native client**, không gửi client secret hardcoded; nếu `none` được registration cho phép, vẫn cần PKCE và client/redirect binding theo policy.

## 13. Discovery và Authorization Code + PKCE

OIDC Authorization Code Flow thường bắt đầu như sau:

~~~http
GET /realms/shop/oauth2/authorize?response_type=code&client_id=orders-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fauth%2Fcallback&scope=openid%20profile&state=<STATE>&code_challenge=<S256_CHALLENGE>&code_challenge_method=S256&nonce=<NONCE> HTTP/1.1
Host: login.example.test
~~~

- `authorization_endpoint` phải đến từ **metadata đã verify**.
- `response_type=code` phải được OP hỗ trợ và client registration cho phép.
- `openid` trong `scope` báo hiệu yêu cầu OIDC; nếu không yêu cầu OIDC, một OAuth token response không mặc nhiên có ID token.
- `state` liên kết callback với transaction; `nonce` được kiểm tra nếu có và theo profile OIDC.
- `code_challenge_method=S256` cần OP hỗ trợ và AS kiểm tra khi code exchange.
- `redirect_uri` phải khớp registration; metadata **không** cấp quyền chọn redirect tùy ý.

Sau authorization callback, client gửi authorization code + `code_verifier` vào **token_endpoint** đã được xác minh, qua HTTPS, với client authentication theo registration. OP trả access token và **ID token** trong OIDC Code Flow thành công; refresh token có thể có nếu grant/policy cho phép.

**Đừng dùng metadata để tự chuyển token endpoint theo response của từng user**. Mọi authorization transaction cần bind issuer dự kiến, redirect URI, client ID và token endpoint tin cậy trước khi nhận code; điều này còn giúp tránh **authorization server mix-up**.

## 14. Discovery và UserInfo, scopes, claims

Metadata `userinfo_endpoint` cho RP biết nơi gọi **UserInfo API** bằng access token được cấp phù hợp. Nó **không** cho phép gửi ID token hoặc refresh token tới UserInfo endpoint.

Ví dụ request:

~~~http
GET /realms/shop/oidc/userinfo HTTP/1.1
Host: login.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_USERINFO>
Accept: application/json
~~~

Ví dụ JSON response UserInfo:

~~~json
{
  "sub": "user-pseudonym-8f2",
  "name": "Alex Example",
  "email": "alex@example.test",
  "email_verified": true
}
~~~

**Cần đối chiếu `sub` UserInfo với `sub` trong ID token đã xác minh** theo OIDC Core. Nếu không khớp, client **MUST NOT** dùng UserInfo claims đó; có thể đã xảy ra nhầm phiên/token/subject.

### Sự khác nhau giữa supported scopes và granted scopes

| Thuộc tính | Nói điều gì? | Không chứng minh điều gì? |
|---|---|---|
| `scopes_supported` | OP có khả năng hiểu một số scope | Client đã được grant tất cả scope |
| `claims_supported` | OP có thể cung cấp một số claims | Mọi request sẽ có tất cả claims đó |
| `scope=openid profile email` request | Client yêu cầu OIDC + claims theo scope | AS sẽ cấp toàn bộ |
| Token response `scope` | Scope thực sự được cấp theo contract | Client có quyền ngoài scope hoặc object-level policy |
| Access token `aud`/`scope` | Resource Server cần xác minh và authorize | RP đã đăng nhập chỉ vì token tồn tại |
| ID token `sub` | Subject xác thực của OP cho RP | Email là khóa định danh ổn định toàn cầu |

**`sub` là định danh người dùng trong ngữ cảnh issuer**. Dùng cặp (`iss`, `sub`) để làm identity key ổn định theo chính sách; không dùng email làm primary security identity, vì email có thể thay đổi, chưa xác minh hoặc trùng ở nhiều issuer.

## 15. Subject types: public và pairwise

`subject_types_supported` trong OIDC metadata quảng bá các kiểu `sub` mà OP có thể phát:

- **`public`:** cùng một user thường có subject identifier chung giữa nhiều client của OP theo mô hình public subject.
- **`pairwise`:** OP có thể tạo subject identifier khác nhau theo sector identifier/client relationship, nhằm giảm khả năng nhiều RP liên kết người dùng dựa trên `sub`.
- Client registration và OP policy quyết định loại được sử dụng; không phải cứ metadata có `pairwise` thì client đã được dùng loại này.

### Hệ quả với user database

Nếu `orders-web` lưu identity theo `email` rồi user đổi email hoặc đăng nhập qua issuer khác, có thể nhầm tài khoản. Nên dùng khóa định danh **issuer + subject** và chính sách liên kết tài khoản có xác minh. Nếu OP đổi subject type/public→pairwise hoặc sector configuration, **không tự merge user** dựa trên email không được chứng thực.

**Discovery cho biết khả năng subject type**, không cho phép client tùy ý biến claim `sub` thành toàn cục.

## 16. OIDC Discovery và OAuth 2.0 Authorization Server Metadata khác nhau

Hai chuẩn có nhiều field chung, nhưng **không nên coi chúng hoàn toàn tương đương**.

| Khía cạnh | OpenID Connect Discovery 1.0 | RFC 8414 OAuth AS Metadata |
|---|---|---|
| Mục tiêu | Khám phá **OpenID Provider**, ID token/UserInfo và OAuth endpoints | Khám phá **OAuth Authorization Server** và các khả năng OAuth |
| Well-known phổ biến | `/.well-known/openid-configuration` | `/.well-known/oauth-authorization-server` |
| Issuer có path | OIDC gắn well-known **sau issuer path** | RFC 8414 đặt well-known theo **quy tắc vị trí khác** cho issuer có path |
| Trường OIDC đặc thù | `subject_types_supported`, `id_token_signing_alg_values_supported`, claims/UserInfo | Không mặc định cần trường OIDC này |
| JWKS | Public signing keys cho OP/ID token và các profile liên quan | Có thể công bố JWKS cho OAuth/JWT access token profiles |
| Cách kiểm tra | OIDC issuer exact match + ID token validation | OAuth AS trust/issuer endpoint + OAuth token/profile validation |
| Tính tương thích | Nhiều OP hỗ trợ cả hai | Không mặc định có OIDC chỉ vì AS có RFC 8414 endpoint |

**Cảnh báo về path:** không ghép URL RFC 8414 theo thói quen rồi áp dụng sang OIDC issuer có path, hoặc ngược lại. Khi dùng library, chỉ rõ discovery profile cần thiết và **verify issuer trong JSON khớp issuer đã chọn**.

Một metadata OAuth chỉ có `token_endpoint`/`jwks_uri` **không làm AS tự nhiên trở thành OIDC OP**. Để thực hiện OIDC, cần đúng registration/profile, `openid` scope, ID token và các quy tắc OIDC Core.

## 17. WebFinger: khám phá issuer động khi nào?

OIDC Discovery 1.0 còn mô tả cách dùng **WebFinger (RFC 7033)** để tìm issuer từ identifier của người dùng trong các tình huống sản phẩm cho phép **dynamic OP discovery**. Đây là **bước khác** với tải Provider Configuration JSON của một issuer đã biết.

Ví dụ minh họa:

~~~http
GET /.well-known/webfinger?resource=acct%3Aalice%40example.test&rel=http%3A%2F%2Fopenid.net%2Fspecs%2Fconnect%2F1.0%2Fissuer HTTP/1.1
Host: example.test
Accept: application/jrd+json
~~~

Ví dụ response WebFinger:

~~~json
{
  "subject": "acct:alice@example.test",
  "links": [
    {
      "rel": "http://openid.net/specs/connect/1.0/issuer",
      "href": "https://login.example.test/realms/shop"
    }
  ]
}
~~~

Ứng dụng có thể sau đó lấy OIDC metadata từ issuer được tìm ra **chỉ khi issuer đó vượt trust policy**.

**Rủi ro lớn:** dynamic WebFinger có thể biến user input thành URL fetch hoặc cho attacker tự công bố issuer mà RP sẽ tin. Do đó:

- Với hệ thống enterprise một OP, **pin issuer** thường đơn giản và dễ kiểm toán hơn WebFinger.
- Nếu triển khai discovery động, phải có **tenant/domain allowlist**, chống SSRF, quy tắc ánh xạ identity↔issuer, xác minh OP/client registration và quản lý onboarding.
- Không cho user nhập `https://127.0.0.1`, cloud metadata IP hoặc URL nội bộ để server tự động fetch tùy ý.
- Không coi WebFinger response là consent, client registration hoặc bằng chứng issuer an toàn.
- Sau khi chọn issuer hợp lệ vẫn **phải tải và xác minh OIDC metadata** và ID token đúng issuer.

## 18. Rủi ro bảo mật: metadata poisoning, mix-up và SSRF

~~~mermaid
flowchart TD
    A["Client cần cấu hình OP"] --> B{"Issuer đến từ cấu hình tin cậy?"}
    B -->|"Không / user input tùy ý"| X["STOP: SSRF/rogue OP risk"]
    B -->|"Có"| C["Fetch OIDC metadata qua HTTPS + limits"]
    C --> D{"JSON issuer exact match?"}
    D -->|"Không"| Y["Reject: issuer substitution"]
    D -->|"Có"| E{"Endpoints/JWKS URLs trong policy?"}
    E -->|"Không"| Z["Reject: endpoint SSRF/substitution"]
    E -->|"Có"| F{"Required fields/capabilities/alg allowlist OK?"}
    F -->|"Không"| W["Reject: invalid/unsafe provider metadata"]
    F -->|"Có"| G["Cache config theo issuer; lấy JWKS an toàn"]
    G --> H["OIDC flow + token validation"]
~~~

### Các dạng tấn công

| Tấn công | Cơ chế | Phòng vệ |
|---|---|---|
| **Rogue OP / metadata poisoning** | RP tin issuer tự xưng do attacker cung cấp | Bootstrap trust, exact issuer, allowlist, reviewed onboarding |
| **SSRF qua issuer** | Server fetch URL user nhập vào loopback/private IP/cloud metadata | Không fetch URL tùy ý, allowlist host/IP, DNS rebinding checks, outbound restrictions |
| **SSRF qua `jwks_uri`** | Metadata trỏ tới địa chỉ nội bộ hoặc endpoint attacker | URL policy, TLS, no redirects, controlled egress |
| **Authorization server mix-up** | Code/verifier của issuer A bị gửi token endpoint B | Bind issuer/client/redirect/token endpoint với transaction, `iss` RFC 9207 khi áp dụng |
| **Cross-tenant key confusion** | Cache JWKS theo `kid` mà không theo issuer | Cache partition theo issuer + key policy |
| **JWT `jku` injection** | JWT header dẫn verifier tới URL key attacker | Chỉ lấy khóa từ JWKS của trusted metadata |
| **Algorithm downgrade/confusion** | Client chấp nhận `alg` không được đăng ký | Algorithm allowlist, đúng key type, reject unsupported |
| **Malicious redirect** | Metadata/JWKS GET tự follow đến host lạ | No redirects hoặc validate destination từng hop |
| **Metadata cache poisoning** | Cấu hình sai được cache/rollout cho nhiều tenant | Pin issuer, signature/TLS trust, per-tenant cache, drift monitoring |
| **Unknown kid DoS** | Flood JWT với `kid` ngẫu nhiên khiến RP fetch JWKS liên tục | Refresh bounded, rate limit, single-flight cache, circuit breaker |
| **Stale/revoked key** | RP tin key đã bị OP gỡ quá lâu | Cache TTL, urgent refresh/revoke mechanism, tested rotation |

**Không phải chỉ cần có `https` trên mọi URL là đủ:** HTTPS có thể kết nối hoàn toàn an toàn tới máy chủ do attacker sở hữu. Trust anchor phải đến **trước** discovery.

## 19. Java 17 + Jackson: tải và kiểm tra metadata có giới hạn

Đoạn Java dưới đây minh họa **chỉ bước OIDC metadata bootstrap**, không tự triển khai code exchange hay JWT cryptography. Nó dùng **JDK 17 HttpClient** và **Jackson Databind** (phải có thư viện Jackson trong dependency của dự án), giới hạn dung lượng JSON và **không follow HTTP redirect**.

Ví dụ assume một OP tin cậy có issuer cố định:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Locale;
import java.util.Set;

public final class TrustedOidcDiscovery {
    private static final String EXPECTED_ISSUER =
            "https://login.example.test/realms/shop";

    // OIDC Discovery: hậu tố sau issuer path.
    private static final URI METADATA_URI = URI.create(
            EXPECTED_ISSUER + "/.well-known/openid-configuration"
    );

    // Chỉ policy minh họa cho deployment này;
    // một OP thật có thể cần thêm các host được phê duyệt.
    private static final Set<String> ALLOWED_HOSTS =
            Set.of("login.example.test");
    private static final int MAX_METADATA_BYTES = 256 * 1024;

    private static final ObjectMapper JSON = new ObjectMapper();

    public record Provider(
            String issuer,
            URI authorizationEndpoint,
            URI tokenEndpoint,
            URI jwksUri
    ) {}

    private static String requiredText(JsonNode root, String name) {
        JsonNode value = root.path(name);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid metadata field: " + name
            );
        }
        return value.asText();
    }

    private static boolean containsText(
            JsonNode root, String name, String expected
    ) {
        JsonNode values = root.path(name);
        if (!values.isArray()) {
            return false;
        }
        for (JsonNode value : values) {
            if (value.isTextual()
                    && expected.equals(value.asText())) {
                return true;
            }
        }
        return false;
    }

    private static URI trustedEndpoint(
            JsonNode root, String field
    ) {
        URI uri = URI.create(requiredText(root, field));
        if (!uri.isAbsolute()
                || !"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getRawFragment() != null
                || !ALLOWED_HOSTS.contains(
                        uri.getHost().toLowerCase(Locale.ROOT))) {
            throw new IllegalArgumentException(
                    "Untrusted endpoint in metadata: " + field
            );
        }
        return uri;
    }

    public static Provider fetch()
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(4))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(METADATA_URI)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request, HttpResponse.BodyHandlers.ofInputStream()
        );
        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException(
                        "OIDC metadata retrieval failed"
                );
            }
            String type = response.headers()
                    .firstValue("Content-Type")
                    .orElse("")
                    .toLowerCase(Locale.ROOT);
            if (!type.split(";", 2)[0].trim()
                    .equals("application/json")) {
                throw new IOException(
                        "Unexpected metadata content type"
                );
            }

            byte[] bytes = body.readNBytes(MAX_METADATA_BYTES + 1);
            if (bytes.length > MAX_METADATA_BYTES) {
                throw new IOException("OIDC metadata too large");
            }

            JsonNode root = JSON.readTree(bytes);
            if (root == null || !root.isObject()) {
                throw new IOException("Malformed OIDC metadata");
            }

            String issuer = requiredText(root, "issuer");
            if (!EXPECTED_ISSUER.equals(issuer)) {
                throw new SecurityException(
                        "OIDC issuer does not match trusted issuer"
                );
            }

            if (!containsText(
                    root, "response_types_supported", "code")
                    || !containsText(
                    root, "subject_types_supported", "public")
                    || !containsText(
                    root, "id_token_signing_alg_values_supported",
                    "RS256")) {
                throw new SecurityException(
                        "Unsupported OIDC provider capabilities"
                );
            }

            return new Provider(
                    issuer,
                    trustedEndpoint(root, "authorization_endpoint"),
                    trustedEndpoint(root, "token_endpoint"),
                    trustedEndpoint(root, "jwks_uri")
            );
        }
    }

    private TrustedOidcDiscovery() {}
}
~~~

### Ranh giới và việc chưa làm trong snippet

1. **`ALLOWED_HOSTS` chỉ là chính sách minh họa** cho triển khai này, **không phải yêu cầu chuẩn rằng mọi OIDC endpoint phải cùng host**. Cần cho phép chính xác host hợp lệ theo deployment.
2. `METADATA_URI` được dựng từ **issuer cố định**, không phải nhập từ user/email/HTTP request.
3. Đã chặn redirect và giới hạn body, nhưng production cần thêm **egress filter**, bảo vệ DNS rebinding/private IP, retry policy, cache TTL/ETag, giới hạn parser và vận hành với proxy.
4. Đã xác nhận support `code`/`public`/`RS256` cho client giả định, nhưng client thực tế còn cần **PKCE S256**, grant/method/client registration, scopes và profile khác.
5. **`Provider` chỉ chứa thông tin cấu hình**; không chứng minh user authentication hoặc token validity.
6. Chưa tải hoặc xác minh **JWKS**, chưa parse/verify ID token, chưa xử lý `state`/`nonce`/`aud`/`exp`. Dùng thư viện OIDC/JOSE được bảo trì cho các bước này.
7. Mã nguồn không log credential hay metadata raw body; ở sản phẩm thật, giữ telemetry an toàn và đo tỉ lệ discovery failure.
8. Cần **pin Jackson version an toàn và kiểm thử malformed JSON/duplicate keys** theo parser policy ứng dụng; không dùng JSON parser tùy tiện.

## 20. Spring Security OIDC client: cấu hình issuer-uri đúng trust boundary

Trong ứng dụng Spring Security, cấu hình provider bằng **trusted issuer URI** thường giúp framework tìm metadata phù hợp qua discovery khi cấu hình client được khai báo đầy đủ. Ví dụ **minh họa cấu trúc YAML** (các chi tiết phụ thuộc phiên bản Spring Boot/Spring Security và registration thực tế):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          orders-web:
            provider: corporate-op
            client-id: orders-web
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          corporate-op:
            issuer-uri: https://login.example.test/realms/shop
~~~

Điều cần hiểu:

- `issuer-uri` **được chọn và quản lý bởi hệ thống tin cậy**, không được copy từ request do user nhập.
- Tên `corporate-op` chỉ là key cấu hình nội bộ, **không** thay claim `iss`.
- Nếu client là confidential, phải cấu hình **client authentication credentials** bằng secret manager/hardware key phù hợp, **không viết plaintext secret vào repository**.
- `redirect-uri` cần khớp URI đã đăng ký; OAuth callback còn kiểm tra `state`/PKCE, CSRF/mix-up và tạo session an toàn.
- Nếu provider không tự discovery được hoặc metadata không hợp lệ, phải **fail closed**, không bỏ issuer validation hoặc tắt TLS để “đăng nhập cho chạy”.
- Thư viện có thể cache metadata/JWKS và quản lý key rotation; kiểm tra cấu hình thực tế của phiên bản đang triển khai, không tự giả định cache an toàn vô hạn.

**Không phải mọi trường metadata tự động trở thành lựa chọn client**. Ví dụ OP quảng bá `none` token auth, nhưng client backend đã đăng ký `private_key_jwt`, framework cần tuân registration/secret policy.

## 21. Failure modes và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý an toàn |
|---|---|---|
| HTTP 404 tại well-known URL | Đặt sai vị trí path/issuer, OP không hỗ trợ Discovery | Kiểm tra issuer/profile; không tự đoán các host khác |
| Metadata trả `issuer` khác cấu hình | Sai tenant, reverse proxy, config drift hoặc response bị thay | **Từ chối**, xử lý cấu hình |
| HTTP 200 nhưng thiếu `jwks_uri` | Không phải OIDC metadata hợp lệ hoặc OP misconfigured | Không xác minh JWT bằng nguồn khóa tùy ý |
| Không có `response_types_supported: code` | OP/profile không hỗ trợ code flow dự kiến | Không tự đổi sang implicit |
| OP chỉ quảng bá alg ngoài allowlist | Policy crypto không khớp | Dừng/fail closed hoặc sửa registration/provider |
| `jwks_uri` trả key mới và `kid` lạ | OP rotate key hoặc token giả | Bounded JWKS refresh, verify kỹ; không fetch arbitrary URL |
| JWKS dùng cache quá lâu | Key cũ bị gỡ/compromise | Respect cache policy, rotation/revocation plan |
| `userinfo_endpoint` vắng mặt | OP không quảng bá hoặc không hỗ trợ UserInfo | Không tự suy đoán endpoint; dùng ID token claims phù hợp |
| `userinfo.sub` khác ID token `sub` | Sai token/session hoặc bị thay response | **Từ chối UserInfo claims** |
| Token có `iss` tenant khác | Mix-up hoặc token từ provider khác | Từ chối, kiểm tra state/issuer binding |
| Token có `aud` là API thay vì RP client | Access token bị dùng làm ID token | Từ chối authentication từ token sai purpose |
| Discovery liên tục khi OP lỗi | Không cache/backoff, gây DoS phụ thuộc OP | Bounded retry, cache/circuit breaker, observability |
| Metadata từ URL user nhập | SSRF / rogue provider | Pin issuer / approved tenant list / outbound restrictions |
| Client nhận `id_token` nhưng không verify signature | Parser-only hoặc alg downgrade | Sửa thư viện/config, fail closed |
| Discovery đúng nhưng API trả 403 | Scope/role/object ACL không đủ | Kiểm tra granted scope và API policy, không nhầm metadata |

**Chẩn đoán phải có giới hạn log**: ghi issuer identifier đã được phê duyệt, event code, status, key reference/correlation ID; **không log** raw ID token/access/refresh token, code/verifier, Authorization header hoặc user PII không cần thiết.

## 22. Cache, quan sát thay đổi và vòng đời vận hành

Metadata và JWKS là **thông tin cấu hình/khóa**, có vòng đời khác access token:

| Dữ liệu | Vòng đời/kiểm soát | Sai lầm phổ biến |
|---|---|---|
| OIDC provider metadata | Cache theo issuer, HTTP TTL/ETag + application policy | Cache chung mọi tenant hoặc auto trust endpoint mới |
| JWKS public signing keys | Cache theo issuer/JWKS URI; refresh bounded/rotation | Tin khóa `kid` từ issuer khác, fetch vô hạn |
| ID token | Verify tại RP, `exp`/`iat`/`nonce` theo profile | Chỉ decode JWT, bỏ chữ ký hoặc issuer |
| Access token | RS validate JWT/introspection, audience/scope | RP nhầm access token với ID token |
| Refresh token | Chỉ AS token endpoint; rotation/revocation policy | Nhầm JWKS rotation với refresh token rotation |
| Client registration | Quản trị/config từ OP và client | Coi metadata supported = client đã được phép |
| User session | Cookie/session policy, logout/reauthentication | Coi metadata refresh tự logout user |

### Gợi ý telemetry

Theo dõi **metadata retrieval success**, issuer mismatch, missing required fields, endpoint/algorithm policy mismatch, JWKS refresh success, unknown `kid` rate, signature failures, stale key usage và latency theo issuer. Khi OP thay endpoint hoặc signing algorithm:

- Có cảnh báo/đánh giá security review cho thay đổi bất thường.
- Không vô điều kiện áp dụng metadata mới cho mọi tenant.
- Xác minh khả năng tương thích và điều kiện rollback an toàn.
- Đảm bảo hoạt động key rotation không khiến RP chấp nhận token của issuer khác.

Tránh log đầy đủ toàn bộ JWT/HTTP response nhạy cảm chỉ để debug; dùng metadata fields được allowlist và correlation IDs không chứa credential.

## 23. Case study: hai tenants cùng hostname nhưng khác issuer và khóa

Giả sử công ty có hai OP tenants:

~~~text
Issuer A:
  https://login.example.test/realms/retail
OIDC config A:
  https://login.example.test/realms/retail/.well-known/openid-configuration

Issuer B:
  https://login.example.test/realms/admin
OIDC config B:
  https://login.example.test/realms/admin/.well-known/openid-configuration
~~~

Ứng dụng `orders-web` chỉ tin issuer **retail**. Cả hai có thể dùng **hostname giống nhau**, `kid` trùng tên hoặc các endpoint nhìn khá giống.

### Đường lỗi

1. RP cấu hình issuer retail nhưng nhận metadata issuer admin do cache bị trộn.
2. RP không so khớp exact issuer và lấy JWKS của admin.
3. RP nhận ID token ký đúng bằng khóa admin, có `iss` admin và `aud` trùng tên client ở một registration khác.
4. Nếu RP chỉ verify chữ ký và `aud` mà bỏ `iss`, token **sai tenant** có thể bị nhận làm identity của retail.

### Đường đúng

1. `expectedIssuer` được pin thành `https://login.example.test/realms/retail`.
2. Metadata phải trả **`issuer` khớp chính xác**; nếu admin thì fail.
3. JWKS được cache **theo issuer**, không chỉ hostname/kid.
4. Chỉ accept JWS algorithm được phép, verify ID token `iss`/`aud`/`exp`/`nonce` khi áp dụng.
5. RP lưu user identity theo **issuer + sub**; không tự merge account vì email giống nhau.
6. Resource Server dùng **access token đúng audience** cho Orders API, không dùng ID token như bearer access token.

**Kết luận case:** discovery metadata là cấu hình **gắn với một issuer cụ thể**, không phải thư viện endpoint dùng chung cho mọi tenant. Exact issuer matching ngăn nhiều lớp mix-up ngay từ bootstrap.

## 24. Ma trận kiểm thử Discovery metadata

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| **T1 — Root issuer** | Issuer không có path | Tìm đúng `/.well-known/openid-configuration` |
| **T2 — Path issuer** | Issuer `/realms/shop` | Tìm đúng OIDC metadata URL sau path, không dùng nhầm quy tắc RFC 8414 |
| **T3 — Exact match** | Metadata issuer đúng | Chấp nhận sau các kiểm tra khác |
| **T4 — Trailing slash drift** | Metadata issuer thêm dấu `/` | Từ chối nếu không đúng chuỗi đã cấu hình |
| **T5 — Cross-tenant** | Metadata issuer khác path, cùng host | Từ chối |
| **T6 — HTTP issuer** | Issuer bắt đầu bằng `http://` | Từ chối |
| **T7 — Query/fragment issuer** | Issuer có `?` hoặc `#` | Từ chối |
| **T8 — TLS failure** | Chứng chỉ OP không hợp lệ | Fail closed, không tắt TLS verification |
| **T9 — Metadata redirect** | HTTP 302 tới host khác | Từ chối theo chính sách no-redirect |
| **T10 — Oversized JSON** | Response vượt giới hạn size | Từ chối an toàn, không exhaust memory |
| **T11 — Bad content type/JSON** | HTML hoặc JSON hỏng | Từ chối |
| **T12 — Missing issuer** | JSON không có `issuer` | Từ chối |
| **T13 — Missing jwks_uri** | JSON không có `jwks_uri` | Từ chối |
| **T14 — Missing code support** | Không có `code` trong response types | Không dùng code flow theo policy |
| **T15 — Unsupported alg** | OP không có ID token signing alg client cho phép | Từ chối |
| **T16 — Client auth mismatch** | OP quảng bá `private_key_jwt`, client đăng ký Basic | Không tự thay client auth method |
| **T17 — JWKS private key** | JWK bất ngờ chứa trường private | Reject/alert metadata security violation |
| **T18 — JWT jku injection** | JWT header `jku` trỏ attacker | Không fetch; dùng trusted jwks_uri |
| **T19 — Unknown kid** | JWT chứa `kid` ngẫu nhiên nhiều lần | JWKS refresh rate-limited, không gây DoS |
| **T20 — JWKS rotation** | Key mới được OP công bố trước khi ký | Client verify key mới theo cache/refresh policy |
| **T21 — Expired token** | Chữ ký đúng, `exp` quá hạn | Từ chối |
| **T22 — Wrong audience** | ID token dành client khác | Từ chối |
| **T23 — Wrong issuer** | ID token từ tenant khác | Từ chối |
| **T24 — UserInfo subject mismatch** | UserInfo `sub` khác ID token `sub` | Không dùng response claims |
| **T25 — Access as ID token** | JWT access token đưa vào login RP | Từ chối |
| **T26 — WebFinger rogue issuer** | User input trả OP không allowlisted | Không kết nối / không tin OP |
| **T27 — SSRF** | `issuer`/`jwks_uri` trỏ loopback/private network | Chặn theo egress/trust policy |
| **T28 — Metadata cache mix-up** | Hai issuers cùng host và kid | Cache tách issuer/key policy, không trộn |
| **T29 — No offline metadata** | OP mất mạng và cache hết hạn | Theo availability/security policy, không bỏ verify |
| **T30 — Scope vs grant** | Metadata có scope nhưng client không được cấp | AS/RS từ chối quyền không được grant |

Kiểm thử bằng **issuer mock/staging, JWT test và canary giả**, không dùng ID/access/refresh token production thật trong HAR, log, CI, URL hoặc báo cáo lỗi.

## 25. Checklist triển khai Discovery metadata

1. **Chọn issuer tin cậy trước**, từ cấu hình/tenant onboarding có kiểm duyệt; không tin URL tự nhập tùy ý.
2. **Dựng OIDC well-known URL đúng chuẩn**, đặc biệt khi issuer có path; không nhầm quy tắc RFC 8414.
3. **HTTPS/TLS certificate verification bắt buộc**, kiểm soát redirect, timeout và egress.
4. **Lấy JSON có giới hạn**: kích thước, content type, parser limits, không logging toàn bộ response khi không cần.
5. **Exact-match `issuer`** với issuer đã chọn; không tự rewrite slash/path/tenant để “cho khớp”.
6. **Validate required OIDC fields**: issuer, authorization endpoint, JWKS URI, response types, subject types, ID token algs và token endpoint khi code flow cần.
7. **Đánh giá capabilities theo client registration**, không xem metadata có scope/grant là đã được cấp quyền.
8. **Allowlist thuật toán ID token**; không dựa vào JWT header `alg` hay tự chuyển xuống `none`/HS256.
9. **Lấy JWKS từ trusted `jwks_uri`**, chỉ dùng public key và đúng key type/algorithm; không fetch `jku`/`x5u` từ token.
10. **Partition cache theo issuer**, tôn trọng TTL/ETag, bounded refresh on unknown `kid` và rotation plan.
11. **Dùng PKCE S256, state và issuer binding** trong Authorization Code flow, không nhầm discovery với user authentication.
12. **Verify ID token cryptographically**: signature, exact `iss`, client `aud`, time, nonce/`azp`/other claims theo profile.
13. **Không dùng ID token để gọi Resource Server**; access token phải đúng audience/scope, opaque token introspection khi cần.
14. **UserInfo endpoint không phải dữ liệu tự tin cậy**: dùng đúng access token và đối chiếu `sub` với verified ID token.
15. **Tách OAuth AS metadata khỏi OIDC Discovery**, kể cả vị trí well-known và yêu cầu ID token fields.
16. **WebFinger chỉ khi thật sự cần dynamic OP discovery**, với allowlist chống SSRF và onboarding policy.
17. **Theo dõi drift**: issuer, JWKS URI, endpoints, algs và token/key validation failures; fail closed cho thay đổi không được phê duyệt.
18. **Không log credential**: authorization code, verifier, ID/access/refresh token, client secrets và raw Authorization header.
19. **Có test bảo mật âm tính**: issuer mismatch, cross-tenant, attacker JWKS, unknown `kid` flood, JSON hỏng, SSRF, wrong `aud`/`iss` và UserInfo mismatch.
20. **Ghi rõ trách nhiệm**: discovery quản lý cấu hình OP; AS cấp quyền/token; RP xác minh authentication; RS xác minh access token và object-level authorization.

**Kết luận:** **OIDC Discovery metadata** giúp RP tìm đúng endpoint và khóa công khai để thực hiện OpenID Connect, nhưng **không thể tự tạo niềm tin**. Nền tảng an toàn là **issuer được chọn trước**, **metadata qua HTTPS và khớp issuer chính xác**, **endpoint/JWKS/algorithm đúng chính sách**, **cache/key rotation có kiểm soát** và **xác minh ID token đầy đủ**. Sau khi đăng nhập, access/refresh token vẫn có vòng đời và ràng buộc audience, scope, lưu trữ, thu hồi riêng; Resource Server không miễn kiểm tra chỉ vì client đã dùng Discovery.

### Tài liệu tiêu chuẩn và tham khảo

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, WebFinger, issuer matching và metadata fields.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation, Authorization Code Flow, UserInfo và subject.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata OAuth AS và quy tắc well-known khác OIDC Discovery.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWKS format.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): xác minh chữ ký JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims `iss`, `aud`, `exp`, `iat`, `sub`.
- [RFC 7033 — WebFinger](https://www.rfc-editor.org/rfc/rfc7033): khám phá issuer động từ resource identifier.
- [RFC 9207 — OAuth Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): chống AS mix-up thông qua `iss`.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): `code_challenge`/`code_verifier` trong Authorization Code Flow.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): OAuth trust, redirect, token và client security.
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): xác định Resource Server/audience mục tiêu.
- [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): vòng đời OAuth tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT khác ID token.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): phòng vệ OAuth/OIDC client.
- [OWASP Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): SSRF hardening khi fetch metadata/JWKS.
