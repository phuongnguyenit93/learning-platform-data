# Ví dụ tích hợp trung lập ngôn ngữ bằng luồng xử lý và mã giả

## 1. Mục tiêu của ví dụ

Tài liệu này mô tả một cách tích hợp thư viện JWT/JOSE vào một hệ thống có authorization server và resource API. Ví dụ sử dụng mã giả và luồng xử lý trung lập, không phụ thuộc ngôn ngữ lập trình hoặc framework.

Hệ thống giả định có:

- **Authorization Server (AS):** xác minh client/grant, quyết định scope được cấp và phát hành JWT access token.
- **Client:** nhận access token và gửi token đến API theo giao thức.
- **Resource Server (RS):** xác minh token theo hợp đồng, sau đó đánh giá quyền trên từng thao tác/tài nguyên.
- **Key provider:** cung cấp khóa ký hoặc khóa xác minh từ nguồn tin cậy.
- **Policy/data provider:** cung cấp quyền nghiệp vụ và trạng thái tài nguyên hiện tại.

Ví dụ chọn chữ ký bất đối xứng để private key chỉ nằm ở AS; RS chỉ cần public key để xác minh. Cách này phù hợp khi có nhiều resource server cần xác minh token mà không được quyền phát hành token. Một hệ thống dùng HMAC vẫn có thể áp dụng cùng ranh giới xử lý, nhưng mọi verifier giữ HMAC secret đều có khả năng ký token.

Mục tiêu không phải tạo một thư viện JWT mới. Mục tiêu là xác định **ở đâu gọi chức năng của thư viện, dữ liệu nào được phép đưa vào, cấu hình tin cậy đến từ đâu và kết quả xác minh được dùng thế nào**.

## 2. Kịch bản xuyên suốt

Một ứng dụng mua sắm có client `shopping-client` gọi API đơn hàng. Người dùng `account-42` được cấp quyền đọc đơn hàng. AS phát hành JWT access token dành riêng cho `orders-api`.

| Thành phần | Giá trị minh họa |
| --- | --- |
| Issuer | `https://authorization.example.org` |
| Client ID | `shopping-client` |
| Subject | `account-42` |
| Audience | `https://api.example.org/orders` |
| Scope | `orders:read` |
| Signing algorithm | `RS256` |
| Key ID | `as-signing-2026-01` |
| Access token lifetime | 10 phút |
| Resource | Đơn hàng thuộc tài khoản/tenant được phép |

Luồng tổng thể:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant K as Key Provider
    participant RS as Resource Server
    participant P as Policy/Data Provider
    C->>AS: Yêu cầu access token theo OAuth grant
    AS->>AS: Xác minh client, subject, grant và consent
    AS->>AS: Tính audience, scope và claims được cấp
    AS->>K: Lấy signing key đã cấu hình
    K-->>AS: Private signing key + key ID
    AS->>AS: Thư viện JOSE ký JWT access token
    AS-->>C: access_token + token_type + expires_in
    C->>RS: GET /orders/987 + Bearer token
    RS->>K: Lấy public key của issuer tin cậy
    K-->>RS: JWKS/public key
    RS->>RS: Thư viện JOSE xác minh token và claims
    RS->>RS: Tạo verified principal
    RS->>P: Kiểm tra quyền đọc order 987
    P-->>RS: Policy decision
    RS-->>C: 200 dữ liệu hoặc 401/403
~~~

## 3. Xác định hợp đồng token trước khi tích hợp

Trước khi gọi thư viện, các bên phải thống nhất token contract. Hợp đồng này quyết định cách tạo, xác minh và diễn giải token.

### 3.1. Cấu hình issuer và resource server

Ví dụ cấu hình khái niệm:

~~~yaml
issuer:
  identifier: https://authorization.example.org
  jwks_uri: https://authorization.example.org/.well-known/jwks.json
  signing_algorithm: RS256
  key_id: as-signing-2026-01

resource_server:
  identifier: https://api.example.org/orders
  accepted_token_profile: oauth-jwt-access-token
  allowed_algorithms:
    - RS256
  required_claims:
    - iss
    - sub
    - aud
    - exp
    - iat
    - client_id
    - jti
  accepted_clock_skew_seconds: 30
~~~

Đây là cấu hình minh họa, không phải cú pháp bắt buộc của một thư viện. Giá trị issuer, JWKS URI, audience và allowlist thuật toán phải đến từ cấu hình được quản lý và tin cậy, không lấy từ token đang xác minh.

### 3.2. Token contract

Với JWT Access Token Profile theo RFC 9068, các claims cốt lõi gồm:

| Claim | Nguồn giá trị | Quy tắc |
| --- | --- | --- |
| `iss` | Cấu hình issuer | Phải khớp issuer được RS tin cậy |
| `sub` | Danh tính đã xác minh | Subject mà token đại diện |
| `aud` | Resource được cấp | Phải bao gồm định danh RS hiện tại |
| `exp` | Chính sách thời hạn | Token hết hạn tại hoặc sau mốc này |
| `iat` | Thời điểm phát hành | NumericDate |
| `jti` | Bộ sinh ID duy nhất | Định danh token |
| `client_id` | Client đã xác minh | OAuth client được cấp token |
| `scope` | Kết quả grant/policy | Chỉ chứa scope thực sự được cấp |

Header minh họa:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "as-signing-2026-01"
}
~~~

Claims Set minh họa:

~~~json
{
  "iss": "https://authorization.example.org",
  "sub": "account-42",
  "aud": "https://api.example.org/orders",
  "client_id": "shopping-client",
  "iat": 1893456000,
  "exp": 1893456600,
  "jti": "at-8c31f7",
  "scope": "orders:read"
}
~~~

Đây là header và payload minh họa, chưa phải JWT compact đã ký. Thời gian là NumericDate tính theo giây từ Unix epoch. Hợp đồng thực tế phải tuân thủ profile đã chọn và quy tắc claims của hệ thống.

### 3.3. Phân biệt cấu hình và dữ liệu từ request

| Giá trị | Nguồn tin cậy |
| --- | --- |
| Expected issuer | Cấu hình RS/metadata đã xác thực |
| Expected audience | Cấu hình API hiện tại |
| Allowed algorithms | Chính sách triển khai |
| Trusted JWKS URI | Cấu hình issuer/metadata tin cậy |
| Subject | Kết quả xác minh danh tính hoặc grant |
| Client ID | Client authentication/registration |
| Approved scope | Policy/consent/grant evaluator |
| Resource ownership | Dữ liệu nghiệp vụ hiện tại |

Không dùng `iss`, `aud`, `alg`, `jku`, `x5u`, `scope` hoặc role từ request/token để tự mở rộng trust configuration hay quyền được cấp.

## 4. Tổ chức các chức năng tích hợp

Một tích hợp dễ kiểm soát có thể chia thành các chức năng logic:

| Chức năng | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| `GrantEvaluator` | Xác minh grant và quyết định scope/resource được cấp | Tự ký JWT |
| `ClaimsFactory` | Tạo claims từ kết quả đã được tin cậy | Nhận nguyên role/scope từ client |
| `SigningKeyProvider` | Cung cấp private key và key ID được cấu hình | Tải khóa từ URL do request gửi |
| `JwtIssuer` | Gọi thư viện JOSE để tạo chữ ký | Tự quyết định người dùng có quyền gì |
| `VerificationKeyProvider` | Lấy/cache public key của issuer tin cậy | Tin JWKS URI từ token |
| `JwtVerifier` | Gọi thư viện để xác minh chữ ký và claims | Chỉ decode rồi coi payload là đáng tin |
| `PrincipalFactory` | Tạo principal từ claims đã xác minh | Nhận claims chưa xác minh |
| `AuthorizationPolicy` | Đánh giá action/resource/context | Cần signing key hoặc tự parse JWT |

Các chức năng này có thể nằm trong một tiến trình hoặc nhiều dịch vụ. Điều quan trọng là giữ ranh giới trách nhiệm và quyền truy cập khóa rõ ràng.

## 5. Phát hành JWT access token

### 5.1. Tiếp nhận yêu cầu token

Client yêu cầu token theo một OAuth grant hợp lệ. AS thực hiện các bước giao thức tương ứng để xác minh client, grant, subject và consent. Chi tiết grant không được thay thế bằng việc client gửi một payload tự khai.

Luồng logic:

~~~text
function issue_access_token(token_request):
    client = authenticate_client(token_request.client_credentials)
    if client is invalid:
        return oauth_error("invalid_client")

    grant = validate_authorization_grant(
        client = client,
        grant_data = token_request.grant,
        requested_resource = token_request.resource,
        requested_scope = token_request.scope
    )

    if grant is denied:
        return oauth_error("invalid_grant")

    approved = evaluate_grant_policy(client, grant)
    if approved is denied:
        return oauth_error("invalid_scope")

    return create_and_sign_access_token(client, approved)
~~~

Đây là pseudocode mô tả trách nhiệm. Tên hàm và kiểu lỗi thực tế phụ thuộc OAuth flow và giao thức triển khai.

### 5.2. Tạo claims từ kết quả grant

Chỉ sau khi grant được chấp thuận, hệ thống mới tạo Claims Set:

~~~text
function build_access_token_claims(client, approved_grant):
    now = current_unix_time()

    return {
        "iss": TRUSTED_ISSUER,
        "sub": approved_grant.subject_id,
        "aud": approved_grant.resource_identifier,
        "client_id": client.registered_client_id,
        "iat": now,
        "exp": now + ACCESS_TOKEN_LIFETIME,
        "jti": secure_unique_identifier(),
        "scope": join_with_spaces(approved_grant.scopes)
    }
~~~

Lưu ý:

- Subject phải đến từ danh tính/grant đã xác minh.
- Audience phải là resource được AS chấp thuận.
- Scope phải là kết quả chính sách, không phải danh sách client tự yêu cầu được chấp nhận nguyên trạng.
- `jti` phải mới cho mỗi token.
- Thời hạn phải theo chính sách; không lấy `exp` tùy ý từ client.
- Chỉ thêm claims mở rộng nếu có hợp đồng và nhu cầu thực tế.

### 5.3. Ký JWT qua thư viện JOSE

Pseudocode:

~~~text
function sign_access_token(claims):
    signing_config = trusted_issuer_config()
    key = signing_key_provider.get_active_key(
        issuer = signing_config.issuer,
        algorithm = signing_config.algorithm,
        purpose = "access-token-signing"
    )

    protected_header = {
        "typ": "at+jwt",
        "alg": signing_config.algorithm,
        "kid": key.key_id
    }

    token = jose_library.create_jws(
        protected_header = protected_header,
        payload = claims,
        signing_key = key.private_key
    )

    return token
~~~

Các điểm kiểm soát:

1. Thuật toán đến từ cấu hình issuer, không đến từ request.
2. Private key được lấy từ key provider hoặc HSM/secret manager phù hợp.
3. `kid` xác định phiên bản khóa để verifier chọn public key.
4. Thư viện phải hỗ trợ thuật toán và profile đã thống nhất.
5. Không ghi private key hoặc JWT nguyên văn vào log.
6. Nếu ký thất bại, không trả token một phần hoặc token không được xác minh.

### 5.4. Trả OAuth token response

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<signed-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Client nhận access token như credential. Client không cần tự xác minh chữ ký để quyết định quyền truy cập API; resource server chịu trách nhiệm xác minh token khi nhận request. Nếu dùng OIDC, ID token là credential riêng dành cho OIDC client và phải được xử lý theo OIDC Core.

## 6. Xác minh JWT tại resource server

### 6.1. Nhận Bearer token

Client gửi access token trong header Authorization:

~~~http
GET /orders/987 HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
Accept: application/json
~~~

API cần lấy đúng một credential theo cú pháp được hỗ trợ. Không nhận token tùy tiện từ query string nếu hợp đồng API quy định dùng Authorization header. Giới hạn kích thước header/token để tránh tiêu thụ tài nguyên không kiểm soát.

### 6.2. Xác định cấu hình tin cậy trước khi xác minh

Resource server phải biết trước:

- Issuer được phép phát hành token.
- Audience của API hiện tại.
- Token profile/type được chấp nhận.
- Danh sách thuật toán được phép.
- Nguồn khóa xác minh tin cậy.
- Claims bắt buộc và chính sách thời gian.

Không lấy expected issuer, JWKS URI hoặc thuật toán từ JWT không tin cậy. Header `kid` chỉ được dùng để chọn khóa trong JWKS/kho khóa của issuer đã cấu hình.

### 6.3. Lấy public key từ JWKS

Pseudocode:

~~~text
function get_verification_key(configured_issuer, token_header):
    assert configured_issuer is trusted
    assert token_header.alg is in configured_issuer.allowed_algorithms

    jwks = jwks_cache.get(configured_issuer.jwks_uri)
    if jwks is expired:
        jwks = refresh_from_trusted_uri(configured_issuer.jwks_uri)

    key = jwks.find_by_kid(token_header.kid)
    if key is not found:
        jwks = refresh_from_trusted_uri(configured_issuer.jwks_uri)
        key = jwks.find_by_kid(token_header.kid)

    if key is not found:
        reject_unknown_signing_key()

    validate_key_type_use_and_algorithm(key, token_header.alg)
    return key
~~~

Thực tế cần có timeout, giới hạn kích thước JWKS, xác thực TLS, cache policy và xử lý lỗi mạng. Không tải lại JWKS vô hạn mỗi khi gặp `kid` lạ vì attacker có thể lợi dụng để gây tải. Có thể áp dụng refresh cooldown, negative cache có thời hạn ngắn và giới hạn tần suất làm mới.

### 6.4. Xác minh bằng thư viện JOSE

Pseudocode:

~~~text
function verify_access_token(compact_token):
    token = jose_library.parse_compact_jws(compact_token)

    header = token.protected_header
    if header.typ != "at+jwt":
        reject_invalid_token("wrong_token_type")

    if header.alg not in TRUSTED_ALLOWED_ALGORITHMS:
        reject_invalid_token("disallowed_algorithm")

    key = get_verification_key(TRUSTED_ISSUER, header)

    verified_jws = jose_library.verify_jws(
        compact_token,
        verification_key = key,
        allowed_algorithms = TRUSTED_ALLOWED_ALGORITHMS
    )

    claims = verified_jws.claims
    validate_required_claims(claims)
    validate_issuer(claims.iss, EXPECTED_ISSUER)
    validate_audience(claims.aud, EXPECTED_AUDIENCE)
    validate_time_claims(claims, allowed_clock_skew)
    validate_access_token_profile(claims)

    return claims
~~~

Tên hàm chỉ là pseudocode. API của thư viện có thể kết hợp parse, signature verification và claim validation trong một lời gọi. Dù dùng API nào, không sử dụng payload trước khi xác minh chữ ký và claims hoàn tất.

### 6.5. Kiểm tra claims và profile

Với ví dụ RFC 9068:

- `typ` phải nhận diện JWT access token theo profile, thường là `at+jwt`.
- `iss` phải khớp issuer tin cậy.
- `aud` phải bao gồm resource identifier của API hiện tại.
- `exp` phải còn hiệu lực; `nbf` nếu có phải đạt điều kiện thời gian.
- `iat`, `sub`, `client_id`, `jti` và claims bắt buộc khác phải hiện diện, đúng kiểu và đáp ứng profile.
- `scope` phải được diễn giải theo hợp đồng OAuth của API.

Kiểm tra audience là bắt buộc về mặt ranh giới: token dành cho `payments-api` không được chấp nhận tại `orders-api` chỉ vì cùng issuer và chữ ký hợp lệ.

### 6.6. Tạo principal đã xác minh

Sau khi token vượt qua mọi kiểm tra, tạo một đối tượng logic chứa dữ liệu cần cho policy:

~~~text
verified_principal = {
    issuer: verified_claims.iss,
    subject: verified_claims.sub,
    client_id: verified_claims.client_id,
    audience: verified_claims.aud,
    scopes: parse_scopes(verified_claims.scope),
    token_id: verified_claims.jti,
    expires_at: verified_claims.exp
}
~~~

Principal này chỉ được tạo từ claims đã xác minh. Không giữ raw payload như nguồn sự thật thứ hai và không để lớp nghiệp vụ tự decode JWT lần nữa.

## 7. Quyết định phân quyền trên tài nguyên

### 7.1. Scope chỉ là một phần của policy

Token có `orders:read` cho biết quyền đọc đã được cấp trong phạm vi hợp đồng. API vẫn phải kiểm tra người gọi có được đọc đúng đơn hàng được yêu cầu không.

Pseudocode:

~~~text
function get_order(request, principal):
    if "orders:read" not in principal.scopes:
        return forbidden("insufficient_scope")

    order = order_repository.find(request.order_id)
    if order is not found:
        return not_found()

    decision = authorization_policy.evaluate(
        subject = principal.subject,
        client = principal.client_id,
        action = "orders:read",
        resource = order,
        context = current_security_context()
    )

    if decision is denied:
        return forbidden()

    return success(order)
~~~

Ví dụ policy có thể yêu cầu subject là chủ sở hữu đơn hàng hoặc thuộc tenant được phép. Scope không tự động cấp quyền đọc mọi bản ghi.

### 7.2. Kiểm tra quyền hiện tại

Một số thông tin thay đổi nhanh hơn thời hạn token:

- Tài khoản bị khóa.
- Thành viên bị loại khỏi tenant.
- Quyền quản trị bị thu hồi.
- Đơn hàng chuyển sang trạng thái không được phép xem.
- Consent hoặc grant bị thu hồi.

Nếu nghiệp vụ yêu cầu thay đổi có hiệu lực ngay, API phải kiểm tra nguồn trạng thái hiện tại, introspection, denylist hoặc một cơ chế thu hồi phù hợp. Không giả định claims trong JWT luôn phản ánh trạng thái mới nhất.

### 7.3. Mặc định từ chối khi policy không xác định

Nếu policy provider không trả được quyết định hoặc dữ liệu quyền không thể xác minh, endpoint nhạy cảm không nên mặc định allow. Xác định rõ hành vi khi dependency lỗi:

- Với thao tác nhạy cảm, fail closed hoặc tạm thời không xử lý.
- Phân biệt lỗi hạ tầng với quyết định deny trong log/metrics.
- Không trả thông tin nội bộ nhạy cảm trong response.
- Có retry có giới hạn nếu thao tác an toàn để retry.

## 8. Response và xử lý lỗi

### 8.1. Request thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "987",
  "owner": "account-42",
  "status": "processing"
}
~~~

### 8.2. Token không hợp lệ

Token thiếu, sai chữ ký, hết hạn, sai issuer/audience hoặc sai token profile thường dẫn đến 401:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{
  "error": "invalid_token",
  "request_id": "req-91c2"
}
~~~

Không trả chi tiết như secret, public key nội bộ, vị trí JWKS, stack trace hoặc claims nhạy cảm.

### 8.3. Token hợp lệ nhưng thiếu quyền

Nếu token đã xác minh nhưng không có scope cần thiết, API có thể trả 403:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders:read"
Content-Type: application/json

{
  "error": "insufficient_scope",
  "request_id": "req-91c3"
}
~~~

Với resource-level authorization, API có thể trả 403 hoặc 404 theo chính sách tránh tiết lộ sự tồn tại của tài nguyên. Quyết định này thuộc hợp đồng API.

### 8.4. Lỗi thư viện và lỗi dependency

Phân biệt ít nhất:

| Lỗi | Phân loại | Hành vi |
| --- | --- | --- |
| Token malformed/invalid signature | Credential invalid | 401 |
| Issuer/audience/profile sai | Credential invalid | 401 |
| Thiếu scope hoặc quyền tài nguyên | Authorization denied | 403/404 theo policy |
| JWKS endpoint tạm thời không truy cập được và không có khóa cache hợp lệ | Dependency failure | Không bỏ qua xác minh; trả lỗi dịch vụ phù hợp |
| Policy provider không sẵn sàng | Dependency failure | Không mặc định allow |
| Lỗi lập trình/cấu hình khóa | Internal failure | Báo lỗi nội bộ, không lộ chi tiết cho client |

Không chuyển mọi exception của thư viện thành 401 một cách máy móc. Lỗi token không hợp lệ khác lỗi hệ thống không thể xác minh vì JWKS hoặc key provider ngừng hoạt động.

## 9. Quản lý khóa và luân chuyển khóa

### 9.1. Trách nhiệm của issuer

Issuer cần:

- Sinh private key bằng cơ chế mật mã phù hợp hoặc dùng HSM/key management service.
- Bảo vệ private key và giới hạn quyền sử dụng.
- Gắn kid duy nhất cho phiên bản khóa.
- Công bố public key tương ứng qua JWKS đã xác thực.
- Theo dõi thời điểm bắt đầu/kết thúc sử dụng khóa.
- Có quy trình thay khóa định kỳ và ứng phó khi khóa bị lộ.

Không công bố HMAC secret trong JWKS công khai. Với chữ ký bất đối xứng, public key có thể được phân phối cho verifier; private key không được đưa vào JWKS công khai.

### 9.2. Luân chuyển bình thường

Một trình tự chuyển khóa không gây gián đoạn:

1. Tạo cặp khóa mới.
2. Công bố public key mới trong JWKS trước khi dùng private key mới để ký.
3. Chờ các verifier có cơ hội làm mới JWKS/cache.
4. Bắt đầu ký token mới bằng private key mới và kid mới.
5. Giữ public key cũ trong JWKS ít nhất đến khi token cũ không còn được chấp nhận, cộng clock skew và cache propagation.
6. Gỡ public key cũ khi không còn token hợp lệ cần xác minh.

### 9.3. Xử lý kid không tìm thấy

Khi verifier nhận kid chưa có trong cache:

1. Làm mới JWKS từ URI tin cậy với giới hạn tần suất.
2. Tìm lại khóa theo kid.
3. Kiểm tra loại khóa, mục đích sử dụng và thuật toán.
4. Nếu vẫn không tìm thấy, từ chối token.

Không bỏ qua xác minh chữ ký, không thử tất cả khóa không phân biệt mục đích và không tải khóa từ URL do token chỉ định.

### 9.4. Khóa bị lộ

Nếu private key bị lộ, attacker có thể tạo JWT giả có chữ ký hợp lệ theo public key tương ứng. Cần ngừng tin khóa bị ảnh hưởng tại verifier, chuyển issuer sang khóa mới, đánh giá token/phiên liên quan và thu hồi credential theo khả năng của hệ thống. Trong sự cố, không duy trì khóa cũ chỉ để chờ hết hạn nếu điều đó cho phép tiếp tục giả mạo.

## 10. Cache, hiệu năng và khả năng sẵn sàng

### 10.1. Cache JWKS đúng cách

Tải JWKS ở mọi request gây độ trễ và phụ thuộc mạng không cần thiết. Cache public key theo issuer và kid, đồng thời tuân theo cache headers/metadata và chính sách vận hành.

Cache cần cân bằng:

- **Độ sẵn sàng:** vẫn xác minh được token hợp lệ khi JWKS endpoint tạm thời lỗi, nếu có khóa cache còn được tin.
- **Khả năng cập nhật:** nhận biết khóa mới khi issuer rotation.
- **Thu hồi:** không tiếp tục tin khóa đã bị thu hồi quá lâu trong sự cố.
- **Chống lạm dụng:** tránh refresh storm do nhiều token có kid lạ.

### 10.2. Không cache quyết định vượt quá vòng đời

Nếu cache verified principal hoặc authorization decision, thời gian cache phải phù hợp với exp, thay đổi quyền và trạng thái tài nguyên. Không để cache cho phép truy cập lâu hơn token hoặc policy cho phép.

Cache quyết định phân quyền cần cân nhắc:

- Token có thể bị thu hồi trước exp.
- Thành viên tenant hoặc quyền có thể bị thay đổi.
- Resource ownership/trạng thái có thể thay đổi.
- Cache key phải bao gồm subject, client, action, resource và context cần thiết.

### 10.3. Xử lý khi dependency lỗi

Không được biến lỗi key provider/JWKS thành “bỏ qua chữ ký”. Không được biến lỗi policy provider thành “allow mặc định”. Đối với thao tác nhạy cảm, nếu không thể xác minh credential hoặc quyền thì phải từ chối/tạm hoãn theo chính sách an toàn.

## 11. Kiểm thử tích hợp

Kiểm thử cần chứng minh cả ba giai đoạn hoạt động độc lập và được nối đúng thứ tự. Không chỉ kiểm tra rằng thư viện có thể ký rồi xác minh lại token do chính nó tạo.

### 11.1. Kiểm thử phát hành

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Client/grant hợp lệ và scope được cấp | Tạo token với issuer, subject, audience, client, scope và thời gian đúng |
| Client không hợp lệ | Không phát hành token |
| Grant không hợp lệ | Từ chối theo OAuth error |
| Client yêu cầu scope ngoài quyền | Chỉ cấp scope được policy chấp thuận hoặc từ chối |
| Audience không được phép | Không phát hành token cho resource đó |
| Signing key không sẵn sàng | Không phát hành token |
| Token thiếu claim bắt buộc theo profile | Test thất bại; không đưa token vào sử dụng |

### 11.2. Kiểm thử xác minh

| Token/test input | Kết quả mong đợi |
| --- | --- |
| Chữ ký hợp lệ, issuer và audience đúng | Verification thành công |
| Payload bị sửa | Từ chối chữ ký |
| Sai issuer | Từ chối |
| Sai audience | Từ chối |
| Hết hạn hoặc chưa đến nbf | Từ chối |
| Thuật toán ngoài allowlist | Từ chối |
| typ không phải access token profile được hỗ trợ | Từ chối |
| kid không tồn tại sau refresh JWKS | Từ chối |
| Thiếu claim bắt buộc hoặc sai kiểu | Từ chối |
| JWKS không truy cập được và không có khóa cache tin cậy | Không bỏ qua xác minh; báo lỗi dependency |

### 11.3. Kiểm thử phân quyền

| Principal/token | Resource/action | Kết quả mong đợi |
| --- | --- | --- |
| Scope orders:read, là chủ sở hữu | Đọc đơn hàng | Allow |
| Scope orders:read, không có quyền trên bản ghi | Đọc đơn hàng của subject khác | Deny |
| Chỉ có orders:read | Xóa đơn hàng | Deny |
| Token audience khác | Bất kỳ thao tác orders | Từ chối ở bước verification |
| Quyền vừa bị thu hồi | Thao tác nhạy cảm | Deny theo trạng thái/policy hiện tại |
| Policy provider lỗi | Thao tác nhạy cảm | Không mặc định allow |

### 11.4. Kiểm thử key rotation

- Public key mới được công bố trước khi token mới được ký.
- Verifier nhận token với kid mới sau khi refresh JWKS.
- Token cũ vẫn xác minh trong giai đoạn chuyển tiếp hợp lệ.
- Sau khi gỡ khóa cũ, token ký bằng khóa cũ bị từ chối.
- kid lạ không gây refresh liên tục hoặc tải URL tùy ý.

## 12. Quan sát và audit mà không làm lộ token

Ghi nhận đủ thông tin để vận hành:

- Request ID/correlation ID.
- Issuer đã cấu hình.
- Key ID được chọn.
- Kết quả signature/claims validation.
- Mã lỗi tổng quát và giai đoạn thất bại.
- Kết quả authorization policy.
- Thời gian xử lý JWKS, verification và policy evaluation.

Không ghi:

- Raw JWT access token, ID token hoặc refresh token.
- Private key, HMAC secret hoặc material giải mã.
- Cookie phiên hoặc Authorization header.
- Toàn bộ payload nếu có claims cá nhân/nhạy cảm.

Nếu cần liên kết sự kiện, dùng request ID hoặc fingerprint được tạo bằng khóa logging riêng và có chính sách retention. Không dùng token nguyên văn làm correlation identifier.

## 13. Một số nguyên tắc khi chọn thư viện

Ví dụ này không chỉ định một thư viện cụ thể. Khi đánh giá thư viện JOSE/JWT, cần xem:

1. Có hỗ trợ các chuẩn JOSE cần thiết như JWS, JWK/JWKS và JWE nếu ứng dụng cần không?
2. Có cho cấu hình allowlist thuật toán rõ ràng không?
3. Có hỗ trợ kiểm tra issuer, audience, expiration, not-before và required claims không?
4. Có xử lý key selection bằng kid mà không tin URL tùy ý trong token không?
5. Có hỗ trợ key rotation/JWKS refresh hoặc cung cấp hook để tích hợp an toàn không?
6. Có phân biệt parse/decode với verify/validate không?
7. Có API rõ ràng cho token type/profile và custom validation không?
8. Có xử lý lỗi phân biệt được invalid token với lỗi key provider/dependency không?
9. Có lịch sử bảo trì, cập nhật bảo mật và tài liệu đáng tin cậy không?
10. Có test vector và khả năng tương tác với thư viện/issuer khác không?

Không chọn thư viện chỉ vì API ngắn hoặc dễ gọi. Một API decode đơn giản không tương đương API xác minh đầy đủ. Cần kiểm tra mặc định thuật toán, hành vi khi thiếu claims và cách thư viện xử lý khóa.

## 14. Tổng hợp pseudocode end-to-end

Luồng ở resource server có thể được biểu diễn gọn:

~~~text
function handle_order_request(http_request):
    raw_token = extract_bearer_token(http_request)
    if raw_token is missing:
        return unauthorized()

    verification_config = load_trusted_resource_server_config()

    try:
        verified_claims = jwt_verifier.verify(
            token = raw_token,
            issuer = verification_config.issuer,
            audience = verification_config.audience,
            allowed_algorithms = verification_config.algorithms,
            token_profile = verification_config.profile,
            trusted_key_provider = verification_config.key_provider
        )
    catch InvalidToken:
        return unauthorized()
    catch VerificationDependencyUnavailable:
        return service_unavailable()

    principal = principal_factory.from_verified_claims(verified_claims)

    order = order_repository.find(http_request.order_id)
    if order is not found:
        return not_found()

    decision = authorization_policy.evaluate(
        principal = principal,
        action = "orders:read",
        resource = order,
        context = current_security_context()
    )

    if decision is denied:
        return forbidden()

    return ok(order)
~~~

Issuer có luồng độc lập:

~~~text
function handle_token_request(token_request):
    client = client_authenticator.authenticate(token_request)
    grant = grant_service.validate(token_request, client)
    approved = grant_policy.evaluate(client, grant)

    if approved is denied:
        return oauth_error()

    claims = claims_factory.create(approved)
    signing_key = signing_key_provider.active_key()
    token = jose_library.sign(
        claims = claims,
        algorithm = configured_algorithm,
        key = signing_key.private_key,
        key_id = signing_key.kid,
        type = "at+jwt"
    )

    return oauth_token_response(token, approved)
~~~

Hai luồng độc lập nhưng phải dùng cùng token contract. Issuer phát hành đúng audience/claims/profile; resource server xác minh đúng hợp đồng rồi mới đánh giá quyền.

## 15. Checklist triển khai

### Hợp đồng và cấu hình

- [ ] Issuer, audience, token profile và claims được định nghĩa trước.
- [ ] Allowlist thuật toán được cấu hình độc lập với token.
- [ ] JWKS URI/key source đến từ issuer metadata/cấu hình tin cậy.
- [ ] Clock skew và lifetime được thống nhất.
- [ ] Claims tùy chỉnh có kiểu dữ liệu và ngữ nghĩa rõ.

### Phát hành

- [ ] Xác minh client/grant trước khi tạo claims.
- [ ] Scope/resource được tính từ policy có thẩm quyền.
- [ ] Claims được tạo từ dữ liệu đã xác minh.
- [ ] jti duy nhất và thời hạn phù hợp.
- [ ] Private key được bảo vệ; kid gắn với phiên bản khóa.
- [ ] Token response có Cache-Control: no-store và không log token.

### Xác minh

- [ ] Không dùng claims trước khi xác minh.
- [ ] Kiểm tra loại token, thuật toán, chữ ký, issuer và audience.
- [ ] Kiểm tra claims bắt buộc và thời gian.
- [ ] JWKS cache/refresh có timeout và giới hạn tần suất.
- [ ] Xử lý kid lạ an toàn.
- [ ] Không bỏ qua verification khi key provider lỗi.

### Phân quyền

- [ ] Principal chỉ được tạo từ claims đã xác minh.
- [ ] Kiểm tra scope và quyền trên tài nguyên.
- [ ] Đối chiếu tenant/ownership/trạng thái hiện tại khi cần.
- [ ] Không mặc định allow khi policy provider lỗi.
- [ ] Tách lỗi invalid token khỏi insufficient permission.

### Vận hành và kiểm thử

- [ ] Có test cho token hợp lệ và các trường hợp sai chữ ký/issuer/audience/time/type.
- [ ] Có test cho thiếu scope, sai resource ownership và quyền bị thu hồi.
- [ ] Có test key rotation và JWKS outage.
- [ ] Có audit/metrics nhưng không log token hoặc secret.
- [ ] Có quy trình xử lý khóa bị lộ và thu hồi credential.

## 16. Kết luận

Một tích hợp JWT rõ ràng bắt đầu từ token contract và tách ba giai đoạn. Authorization server xác minh grant, tính quyền được cấp, tạo claims và ký token bằng khóa tin cậy. Resource server lấy khóa từ nguồn tin cậy, xác minh chữ ký, issuer, audience, token profile và thời gian trước khi tạo principal. Sau đó policy evaluator mới quyết định principal có được thực hiện action trên resource trong context hiện tại hay không.

Thư viện JOSE/JWT chịu trách nhiệm về thao tác định dạng và mật mã theo cấu hình; ứng dụng chịu trách nhiệm cung cấp dữ liệu tin cậy, chính sách khóa, hợp đồng claims và quyết định nghiệp vụ. Không dùng parse/decode thay cho verify, không dùng token hợp lệ thay cho authorization và không bỏ qua xác minh khi dependency gặp lỗi.

**Luồng an toàn là: grant được chấp thuận → token được phát hành đúng hợp đồng → token được xác minh đúng ngữ cảnh → quyền được đánh giá trên tài nguyên thực tế.**

## Tài liệu chuẩn để đọc tiếp

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): tạo và xác minh chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn khóa và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT theo ngữ cảnh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): phát hành và sử dụng access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách trình bearer token.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata issuer và JWKS URI.
- [NIST SP 800-162 — Guide to Attribute Based Access Control (ABAC)](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): đánh giá quyền theo subject, resource, action và environment.
