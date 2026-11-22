# Thiết kế cấp phát và xác minh với cặp khóa bất đối xứng

Trong mô hình JWT ký bằng mật mã bất đối xứng, Authorization Server giữ private key để ký token; API/resource server chỉ cần public key tương ứng để xác minh chữ ký. Cách phân tách này giúp nhiều dịch vụ xác minh token mà không phải chia sẻ bí mật có khả năng phát hành token. Tuy nhiên, chữ ký hợp lệ mới chỉ xác nhận tính toàn vẹn và nguồn ký theo khóa đã chọn. Resource server vẫn phải kiểm tra issuer, audience, token profile, thời hạn, claims và quyền truy cập tài nguyên.

Bài thực hành thuộc chương **Thực hành tổng hợp** của module **Security – JSON Web Token (JWT)**. Mục tiêu là thiết kế một luồng cấp phát và xác minh end-to-end, từ quản lý cặp khóa, ký JWS, công bố JWKS, chọn khóa theo `kid`, đến rotation, xử lý compromise và kiểm thử. Nội dung áp dụng cho mọi ngôn ngữ, runtime và framework; không phụ thuộc một ngôn ngữ hoặc framework cụ thể.

## 1. Mục tiêu và kiến trúc bài thực hành

Ta xây dựng một hệ thống mẫu gồm:

- **Authorization Server (AS):** xác thực client/người dùng theo luồng đã chọn, đánh giá quyền cấp token và ký access JWT bằng private key.
- **JWKS endpoint:** công bố public key để resource server có thể tải và xác minh.
- **Resource Server (RS):** nhận bearer token, chọn public key từ trust configuration/JWKS, xác minh chữ ký và kiểm tra claims.
- **Client:** nhận access token và gửi token tới API qua HTTPS.

~~~mermaid
flowchart LR
    C["Client"] -->|"Yêu cầu token"| AS["Authorization Server"]
    AS -->|"Ký JWS bằng private key"| T["Access JWT"]
    AS -->|"Công bố public keys"| J["JWKS endpoint"]
    C -->|"Bearer access token"| API["Resource Server"]
    API -->|"Tải/cache JWKS"| J
    API -->|"Verify signature + validate claims"| P["Authorization policy"]
    P --> R["Protected resource"]
~~~

### 1.1. Phân chia trách nhiệm

| Thành phần | Giữ private key? | Giữ public key? | Trách nhiệm |
| --- | --- | --- | --- |
| Authorization Server | Có | Có thể có | Cấp token, ký token, quản lý key lifecycle |
| JWKS endpoint | Không | Có | Công bố tập public key đã được phê duyệt |
| Resource Server | Không | Có/cache | Xác minh chữ ký và claims, thực thi authorization |
| Client | Không | Không cần | Gửi access token qua kênh bảo vệ |
| KMS/HSM | Giữ hoặc kiểm soát private key không xuất được | Có thể xuất public key | Thực hiện thao tác ký có kiểm soát |

Private key là quyền phát hành token. Nếu mọi resource server đều giữ private key, mỗi server bị xâm nhập có thể tự tạo token được các server khác tin cậy. Với mô hình bất đối xứng, resource server chỉ cần public key, nên compromise một verifier không tự động trao quyền ký.

### 1.2. Kết quả cần đạt

Sau bài thực hành, hệ thống phải chứng minh được:

1. Private key chỉ tồn tại tại issuer hoặc KMS/HSM được ủy quyền ký.
2. JWKS chỉ công bố public key, không chứa private key material.
3. Token được ký bằng thuật toán được cấu hình trước.
4. Resource server chỉ chọn key từ issuer/JWKS đã tin cậy.
5. `kid` dùng để chọn key trong đúng key set, không phải bằng chứng tin cậy.
6. Signature, `iss`, `aud`, `exp`, `nbf`, `typ` và claims được kiểm tra theo profile.
7. Key rotation không làm gián đoạn token hợp lệ và có quy trình khẩn cấp khi key compromise.
8. Các lỗi sai chữ ký, sai issuer/audience, hết hạn và sai key đều bị từ chối.

## 2. Chọn thuật toán và định dạng khóa

JWS hỗ trợ nhiều thuật toán chữ ký bất đối xứng. Issuer và verifier phải thống nhất thuật toán, loại khóa và cách biểu diễn chữ ký.

| JOSE `alg` | Họ khóa | Mô tả | Điểm cần lưu ý |
| --- | --- | --- | --- |
| RS256 | RSA | RSASSA-PKCS1-v1_5 với SHA-256 | Tương thích rộng; cần kích thước khóa đáp ứng crypto policy |
| PS256 | RSA | RSA-PSS với SHA-256 | Cần thư viện ở hai phía hỗ trợ đúng PSS parameters |
| ES256 | EC P-256 | ECDSA với SHA-256 | JWS dùng chữ ký raw `R || S`, không phải ASN.1 DER |
| EdDSA | OKP, ví dụ Ed25519 | Edwards-curve signature | Cần xác nhận thư viện và nền tảng hỗ trợ profile tương ứng |

Không chọn thuật toán dựa trên giá trị `alg` do token gửi tới. Issuer cấu hình thuật toán ký; verifier cấu hình allowlist thuật toán chấp nhận.

### 2.1. Ví dụ lựa chọn cho bài lab

Để bài lab dễ tích hợp với nhiều thư viện JOSE, ta dùng **RS256** làm cấu hình minh họa. Trong môi trường thực tế, có thể chọn PS256, ES256 hoặc EdDSA khi thư viện, chính sách mật mã và hệ thống đối tác hỗ trợ đồng nhất.

Các yêu cầu:

- Chỉ dùng thuật toán nằm trong allowlist.
- Không chấp nhận `none`.
- Không trộn thuật toán HMAC và chữ ký bất đối xứng trong cùng một cấu hình xác minh dễ bị nhầm lẫn.
- Không cho token quyết định loại khóa hoặc thuật toán tùy ý.
- Không tái sử dụng cùng một key pair cho nhiều mục đích mật mã không liên quan.

### 2.2. Tạo cặp khóa RSA cho môi trường lab

Có thể dùng một công cụ mật mã phổ biến để sinh khóa RSA. Ví dụ với OpenSSL:

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out issuer-private.pem
openssl pkey -in issuer-private.pem -pubout -out issuer-public.pem
~~~

Hai lệnh tạo private key và trích public key tương ứng. Đây là ví dụ lab; kích thước khóa và thuật toán production phải theo crypto baseline, yêu cầu tương thích và chính sách quản trị khóa của tổ chức.

**Không đưa `issuer-private.pem` vào repository, image/container, artifact CI hoặc thư mục được chia sẻ.** Trong production, ưu tiên KMS/HSM hoặc secret/key store có kiểm soát truy cập, audit và rotation. Nếu dùng file cho lab, giới hạn quyền đọc và xóa khóa sau khi hoàn tất.

### 2.3. Phân biệt private key và public key

Với RSA JWK:

- Public key gồm `kty`, `n`, `e` và metadata phù hợp.
- Private key còn có `d`, `p`, `q`, `dp`, `dq`, `qi` và có thể `oth`.

Với EC JWK:

- Public key có `kty`, `crv`, `x`, `y`.
- Private key có thêm `d`.

Với OKP JWK:

- Public key có `kty`, `crv`, `x`.
- Private key có thêm `d`.

JWKS public chỉ được chứa thành phần public. Không bao giờ công bố các private member như `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc `k` trong endpoint công khai.

## 3. Thiết kế key registry tại Authorization Server

Issuer cần một registry quản lý key và trạng thái của từng key. Không nên chỉ lưu một biến “current private key” không có metadata hoặc quy trình chuyển đổi.

Ví dụ cấu hình logic:

~~~yaml
issuer: https://identity.example
signing:
  active_key:
    kid: rsa-2026-01
    algorithm: RS256
    private_key_reference: kms://identity/signing/rsa-2026-01
  allowed_algorithms:
    - RS256
token_profile:
  type: at+jwt
  audience:
    - https://orders-api.example
  lifetime_seconds: 300
~~~

Đây là cấu hình minh họa, không phải schema chuẩn. `private_key_reference` trỏ tới key store/KMS; không phải nội dung private key. Chỉ issuer được phép sử dụng key reference để ký.

### 3.1. Key metadata

Mỗi key nên có tối thiểu:

- `kid`: định danh duy nhất trong key set của issuer.
- `alg`: thuật toán được phép sử dụng với key.
- `kty` và `crv` nếu áp dụng.
- Trạng thái: pending, active, retiring, retired hoặc compromised.
- Thời điểm tạo, bắt đầu sử dụng, ngừng ký và gỡ khỏi JWKS.
- Vị trí lưu private key hoặc tham chiếu KMS/HSM.
- Owner, quyền sử dụng và audit history.

`kid` không phải secret và không chứng minh token hợp lệ. Nó chỉ giúp chọn candidate key. Resource server vẫn phải xác minh chữ ký và claims.

### 3.2. Tách key theo môi trường và mục đích

Không dùng cùng key pair cho:

- Development và production.
- Staging và production.
- Nhiều issuer độc lập.
- JWT signing và mục đích encryption không liên quan.
- Token người dùng và một hệ thống có trust boundary riêng nếu policy yêu cầu tách biệt.

Nếu key test bị lộ, ảnh hưởng không được lan sang production. Audience và issuer cũng cần tách theo môi trường.

## 4. Công bố public key bằng JWKS

JWKS là JSON Web Key Set, một object chứa mảng `keys`. Authorization Server có thể công bố public signing key tại endpoint được metadata/discovery hoặc trust configuration chỉ định.

Ví dụ JWKS rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "rsa-2026-01",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `n` và `kid` là placeholder minh họa; JWKS thực tế phải chứa modulus public key được serialize đúng JWK. Không thêm private parameters vào public JWKS.

### 4.1. Các trường JWK quan trọng

| Trường | Ý nghĩa | Cách dùng trong verifier |
| --- | --- | --- |
| `kty` | Loại khóa | Phải phù hợp với thuật toán |
| `kid` | Key ID | Chọn candidate trong key set của issuer |
| `use` | Mục đích khóa | Nếu có, phải là `sig` cho xác minh chữ ký |
| `key_ops` | Các thao tác được phép | Nếu có, phải bao gồm `verify` |
| `alg` | Thuật toán gắn với key | Nếu có, phải khớp allowlist/profile |
| `n`, `e` | Thành phần public RSA | Dùng dựng RSA public key |
| `crv`, `x`, `y` | Thành phần public EC | Dùng dựng EC public key |
| `crv`, `x` | Thành phần public OKP | Dùng dựng OKP public key |

Không chỉ dựa vào `kid`. Verifier phải kiểm tra key type, algorithm compatibility, `use`, `key_ops` và chất lượng tham số khóa theo profile.

### 4.2. Bảo vệ nguồn JWKS

Public key không cần giữ bí mật, nhưng tính xác thực của nguồn phân phối key rất quan trọng. Nếu attacker thay JWKS bằng public key do họ kiểm soát, verifier có thể chấp nhận token giả được ký bằng private key tương ứng.

- Cấu hình issuer và JWKS URI từ nguồn được quản trị.
- Dùng HTTPS và xác minh chứng chỉ.
- Nếu dùng OIDC Discovery, trường `issuer` trong metadata phải khớp issuer đã cấu hình.
- Không tải `jku` hoặc `x5u` tùy ý từ token để thay nguồn key.
- Kiểm soát redirect, DNS/network egress, timeout và response size.
- Cache JWKS theo issuer và URI tin cậy.
- Có audit khi thay đổi JWKS endpoint hoặc trust profile.

## 5. Cấp phát access JWT bằng private key

Issuer chỉ ký token sau khi xác thực client/user và đánh giá policy cấp quyền. Không cung cấp endpoint ký tùy ý để caller gửi payload bất kỳ rồi nhận chữ ký.

### 5.1. Chọn claims tối thiểu

Ví dụ access token claims:

~~~json
{
  "iss": "https://identity.example",
  "sub": "demo-user-01",
  "aud": "https://orders-api.example",
  "client_id": "web-client",
  "scope": "orders:read orders:create",
  "iat": 2000000000,
  "nbf": 2000000000,
  "exp": 2000000300,
  "jti": "demo-jwt-0001"
}
~~~

Đây là claims set synthetic cho bài lab. Timestamp cố định chỉ phù hợp khi test dùng clock được kiểm soát; không dùng trực tiếp làm thời gian production.

Các nguyên tắc:

- `iss` phải là issuer identifier đã cấu hình.
- `sub` phải xác định subject theo namespace issuer.
- `aud` phải chỉ đúng resource server hoặc resource set được cấp.
- `exp` nên bắt buộc trong access token profile có thời hạn.
- `iat` ghi thời điểm phát hành; `nbf` dùng khi cần thời điểm bắt đầu hiệu lực.
- `jti` có thể hỗ trợ nhận diện token/revocation theo policy.
- `scope` chỉ chứa quyền được cấp theo grant và policy.
- Không đưa PII hoặc dữ liệu nghiệp vụ không cần thiết vào token.

JWT ký không đồng nghĩa với JWT mã hóa. Payload JWS có thể đọc được; nếu cần bảo mật nội dung, phải đánh giá JWE hoặc một cơ chế bảo vệ dữ liệu riêng.

### 5.2. Protected Header

Ví dụ JOSE Protected Header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "rsa-2026-01"
}
~~~

`typ: at+jwt` phù hợp với JWT Profile for OAuth 2.0 Access Tokens khi issuer/resource server triển khai RFC 9068. Nếu dùng profile khác, phải thống nhất type theo profile đó. Không dùng một giá trị `typ` tùy tiện rồi giả định mọi verifier đều có cùng cách diễn giải.

`kid` trỏ tới key đang active. Header được đưa vào protected signing input; sau khi ký, không thể thay `kid` hoặc `alg` mà vẫn giữ chữ ký hợp lệ.

### 5.3. Signing input

Với JWS Compact, signing input có dạng:

~~~text
BASE64URL(UTF8(protected_header))
.
BASE64URL(payload)
~~~

Issuer dùng private key và thuật toán đã cấu hình để ký chính xác byte sequence này. Kết quả được Base64url encode thành signature segment:

~~~text
BASE64URL(protected_header).BASE64URL(payload).BASE64URL(signature)
~~~

Không chỉnh sửa JSON header hoặc payload sau khi tạo chữ ký. Thay đổi whitespace, thứ tự member, giá trị claim hoặc encoding sẽ làm signing input thay đổi và chữ ký không còn khớp.

### 5.4. Pseudocode cấp phát

~~~text
function issue_access_token(authenticated_principal, client, requested_scope):
    grant = authorize_token_request(
        principal = authenticated_principal,
        client = client,
        requested_scope = requested_scope
    )
    require(grant.allowed)

    key = signing_registry.active_key()
    require(key.status == "active")
    require(key.algorithm in issuer.allowed_algorithms)

    now = trusted_clock.unix_seconds()
    claims = {
        "iss": issuer.identifier,
        "sub": grant.subject,
        "aud": grant.audience,
        "client_id": client.id,
        "scope": grant.scope,
        "iat": now,
        "exp": now + grant.access_token_lifetime,
        "jti": secure_random_identifier()
    }

    header = {
        "alg": key.algorithm,
        "typ": issuer.access_token_type,
        "kid": key.kid
    }

    token = JOSE_sign(
        protected_header = header,
        payload = claims,
        private_key_reference = key.private_key_reference
    )

    audit("access_token.issued", safe_metadata_only)
    return token
~~~

Pseudocode mô tả logic. `JOSE_sign` phải là thư viện/cryptographic provider được duy trì hoặc thao tác ký được ủy quyền qua KMS/HSM. Không tự triển khai thuật toán chữ ký bằng phép toán số học thủ công.

## 6. Xác minh access JWT bằng public key

Resource server nhận bearer token và thực hiện xác minh trước khi dùng claims để cấp quyền.

### 6.1. Quy trình xác minh

1. Giới hạn kích thước token và kiểm tra JWS Compact có đúng ba segment.
2. Parse protected header theo JSON strict; coi header là dữ liệu chưa tin cậy.
3. Xác định trust profile/issuer được chấp nhận theo cấu hình.
4. Kiểm tra `alg` nằm trong allowlist đã cấu hình; không để token tự chọn thuật toán.
5. Dùng `kid` làm gợi ý chọn candidate key trong JWKS thuộc đúng issuer.
6. Kiểm tra JWK `kty`, `use`, `key_ops`, `alg` và tham số khóa.
7. Xác minh chữ ký trên đúng signing input.
8. Chỉ sau khi signature hợp lệ mới tin claims.
9. Kiểm tra `iss`, `aud`, token type, `exp`, `nbf`, `iat` và schema theo profile.
10. Kiểm tra scope/permission và quyền trên tài nguyên.
11. Ghi audit event với request ID và failure code an toàn, không log raw token.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant JWKS as Trusted JWKS
    C->>RS: Request + Bearer JWT
    RS->>RS: Parse header và kiểm tra alg allowlist
    RS->>JWKS: Chọn public key theo issuer + kid
    JWKS-->>RS: Public key candidate
    RS->>RS: Verify JWS signature
    RS->>RS: Validate iss, aud, typ, exp, nbf
    RS->>RS: Authorize scope và resource
    RS-->>C: Response hoặc 401/403
~~~

### 6.2. Pseudocode xác minh

~~~text
function verify_access_token(compact_token, api_profile):
    enforce_token_size_limit(compact_token)
    parts = split_preserving_empty_segments(compact_token, ".")
    require(length(parts) == 3)

    header = strict_decode_and_parse_jose_header(parts[0])
    require(header.alg in api_profile.allowed_algorithms)
    require(header.alg != "none")

    issuer_hint = read_untrusted_issuer_for_registry_lookup(parts[1])
    issuer_profile = trusted_issuer_registry.find_exact(issuer_hint)
    require(issuer_profile exists)
    require(issuer_profile is allowed_for(api_profile))

    jwks = load_cached_jwks_from_trusted_profile(issuer_profile)
    key = select_key(
        jwks,
        kid = header.kid,
        alg = header.alg,
        use = "sig",
        key_ops = "verify"
    )

    if key is missing:
        refresh_jwks_with_rate_limit(issuer_profile)
        key = select_key_from_refreshed_jwks(...)

    require(key exists)
    require(verify_jws_signature(compact_token, key, api_profile.allowed_algorithms))

    claims = parse_verified_claims_strictly(parts[1])
    require(claims.iss == issuer_profile.issuer)
    require(audience_matches(claims.aud, api_profile.audiences))
    require(token_type_matches(header.typ, api_profile.token_profile))
    require(time_claims_valid(claims, api_profile.clock_skew))
    validate_claim_schema(claims, api_profile)

    principal = map_verified_claims_to_principal(claims, issuer_profile)
    require(authorize_resource(principal, api_profile.resource_policy))
    return principal
~~~

Đây là pseudocode trung lập ngôn ngữ. Với một API chỉ chấp nhận một issuer, có thể lấy issuer profile cố định từ cấu hình và không cần đọc `iss` chưa xác minh để chọn profile. Với nhiều issuer, `iss` chưa xác minh chỉ được dùng để lookup chính xác trong allowlist; sau xác minh chữ ký phải kiểm tra lại `iss`.

### 6.3. Không dùng `kid` như bằng chứng xác thực

`kid` do token gửi và chưa được xác minh. Nó chỉ giúp tìm candidate key trong tập khóa đã tin cậy.

- Không dùng `kid` để tải URL tùy ý.
- Không tìm key toàn cục mà không phân biệt issuer.
- Không fallback sang key của issuer khác nếu chữ ký thất bại.
- Nếu có nhiều key cùng `kid` trong cùng key set, xử lý theo policy rõ ràng; không chọn ngẫu nhiên.
- Sau khi xác minh, `iss` phải khớp trust profile đã dùng.

### 6.4. Algorithm confusion

Một lỗi nguy hiểm là để token quyết định thuật toán mà verifier dùng, hoặc dùng public key như HMAC secret khi token chuyển từ thuật toán bất đối xứng sang thuật toán MAC.

Phòng chống:

- Cấu hình allowlist thuật toán tại verifier.
- Ràng buộc loại khóa với thuật toán.
- Không trộn secret HMAC và public key trong cùng luồng chọn khóa không kiểm soát.
- Không chấp nhận `none` cho access token cần chữ ký.
- Không tự động fallback sang thuật toán khác khi verify thất bại.

## 7. Kiểm tra claims sau khi chữ ký hợp lệ

Chữ ký hợp lệ không chứng minh token dành cho API hiện tại hoặc principal có quyền trên tài nguyên.

| Kiểm tra | Điều kiện |
| --- | --- |
| Issuer | `iss` khớp chính xác issuer được tin cậy |
| Audience | `aud` chứa resource identifier mà API chấp nhận |
| Token type | `typ`/profile khớp loại access token mà API yêu cầu |
| Expiration | `exp` tồn tại nếu profile yêu cầu và token chưa hết hạn |
| Not Before | `nbf` được đáp ứng nếu claim xuất hiện |
| Issued At | `iat` phù hợp policy và không nằm trong tương lai bất hợp lý |
| Subject | `sub` được diễn giải trong namespace issuer |
| Client | Client/application được phép theo policy |
| Scope | Scope đủ cho operation |
| Tenant/resource | Principal có quyền trên object/tenant cụ thể |

### 7.1. Audience phải đúng resource server

Token có chữ ký hợp lệ nhưng `aud` dành cho HR API không được tự động chấp nhận ở Orders API. Nếu nhiều API cùng tin issuer, mỗi API vẫn phải kiểm tra audience của chính nó.

### 7.2. Token type phải đúng

Không dùng ID Token thay access token. Nếu triển khai JWT access token theo RFC 9068, xác minh các yêu cầu của profile, bao gồm `typ: at+jwt` trong JOSE header và claims bắt buộc. Nếu dùng profile khác, ghi rõ type và validation rules trong trust configuration.

### 7.3. Authorization ở cấp tài nguyên

Scope `orders:read` không tự động cho phép đọc mọi order. Orders service vẫn phải kiểm tra ownership, tenant, trạng thái và policy nghiệp vụ. JWT cung cấp security context; resource owner đưa ra quyết định cuối cùng trên dữ liệu của nó.

## 8. Quản lý private key bằng KMS/HSM

Trong production, private key nên được bảo vệ bởi hệ thống quản lý khóa phù hợp với mức độ rủi ro. KMS/HSM có thể cho phép issuer yêu cầu ký mà không cần xuất private key ra ứng dụng.

### 8.1. Nguyên tắc bảo vệ

- Private key không nằm trong source code, container image hoặc log.
- Chỉ workload issuer được phép gọi thao tác ký.
- Tách quyền quản trị key với quyền sử dụng key nếu có thể.
- Giới hạn thuật toán và key purpose.
- Audit thao tác ký, thay đổi policy và rotation.
- Bảo vệ backup/recovery theo yêu cầu của key store.
- Có quy trình thu hồi, disable và xử lý compromise.

### 8.2. Signing service không phải endpoint ký tùy ý

Nếu issuer dùng một signing service, service đó phải nhận yêu cầu có cấu trúc và kiểm tra:

- Workload caller có được phép yêu cầu ký không.
- Issuer profile và audience có được phép không.
- Token lifetime có nằm trong giới hạn không.
- Scope/claims có được cấp theo policy không.
- Key đang active có đúng issuer và algorithm không.

Không xây dựng API kiểu `sign(arbitrary_payload)` cho caller không tin cậy. Nếu một workload bị xâm nhập có thể yêu cầu ký claims tùy ý, private key dù nằm trong HSM vẫn có thể bị lạm dụng thông qua signing oracle.

### 8.3. Audit không chứa bí mật

Có thể audit:

- Key ID và key version.
- Workload/service đã yêu cầu ký.
- Thời điểm và kết quả.
- Issuer profile và token profile.
- Request/event ID.

Không ghi private key, raw token, secret hoặc toàn bộ payload nhạy cảm vào audit log.

## 9. Key rotation không gián đoạn

Rotation bình thường cần khoảng thời gian overlap giữa public key cũ và mới. Resource server có thể cache JWKS, vì vậy thay đổi ở issuer không xuất hiện tức thời tại mọi verifier.

### 9.1. Quy trình rollover

~~~mermaid
flowchart LR
    A["Tạo key pair mới"] --> B["Publish public key mới trong JWKS"]
    B --> C["Chờ verifier refresh/cache nhận key"]
    C --> D["Issuer bắt đầu ký bằng private key mới"]
    D --> E["Giữ public key cũ trong JWKS"]
    E --> F["Token cũ hết hạn + hết thời gian chuyển tiếp"]
    F --> G["Gỡ public key cũ"]
    G --> H["Xóa/retire private key cũ theo retention policy"]
~~~

Các bước:

1. Tạo key pair mới và gán `kid` mới.
2. Đưa public key mới vào JWKS.
3. Chờ thời gian đủ để resource server nhận key mới qua refresh/cache.
4. Chuyển issuer sang ký token mới bằng private key mới.
5. Tiếp tục công bố public key cũ để xác minh token đã ký trước đó.
6. Chờ token cũ hết hạn, cộng leeway và khoảng chuyển tiếp/cache cần thiết.
7. Gỡ public key cũ khỏi JWKS và retire private key theo policy.

### 9.2. Tính thời gian overlap

Thời gian giữ public key cũ cần xét:

- Lifetime tối đa của token ký bằng key cũ.
- Clock skew/leeway được resource server cho phép.
- Thời gian cache JWKS và độ trễ refresh.
- Thời gian triển khai cấu hình tới mọi resource server.
- Request đang xử lý hoặc queue có thể còn mang token cũ.

Không gỡ public key cũ ngay khi issuer bắt đầu ký bằng key mới; token hợp lệ đã phát hành vẫn cần được xác minh trong thời hạn của nó.

### 9.3. Unknown `kid`

Khi verifier gặp `kid` chưa có trong cache:

1. Chỉ refresh JWKS của issuer đã được xác định từ trust profile.
2. Giới hạn tần suất refresh và đồng bộ request để tránh request storm.
3. Chọn lại key từ JWKS vừa cập nhật.
4. Nếu vẫn không có key, từ chối token.
5. Không tải `jku`/`x5u` từ token để tìm key thay thế.

### 9.4. Key compromise khác rotation bình thường

Nếu private key bị lộ:

- Disable key ký bị compromise ngay theo incident policy.
- Dừng phát hành token bằng key đó.
- Chuyển sang key pair mới.
- Loại key bị compromise khỏi tập key được chấp nhận và purge/refresh cache ở verifier.
- Đánh giá token đã ký bằng key bị lộ; cân nhắc introspection, denylist, session/version check hoặc yêu cầu xác thực lại.
- Điều tra thao tác ký và phạm vi token có thể bị giả mạo.

Gỡ key khỏi JWKS có thể không vô hiệu hóa ngay nếu verifier còn cache public key cũ. Với sự cố compromise, cần cơ chế khẩn cấp ngoài thời gian cache bình thường: cấu hình deny key ID, purge cache hoặc cập nhật trust registry. Không giữ key compromise chỉ để tránh gián đoạn.

## 10. Cache JWKS và độ sẵn sàng

Resource server thường cache JWKS để tránh gọi issuer ở mọi request. Cache phải cân bằng hiệu năng và khả năng nhận rotation/compromise.

### 10.1. Cache theo issuer và nguồn

Cache key nên bao gồm issuer identifier và JWKS URI tin cậy. Không cache chỉ theo `kid`, vì nhiều issuer có thể dùng cùng một `kid`.

Có thể cache:

- Public JWK đã kiểm tra.
- Thời điểm tải và HTTP cache metadata.
- Key fingerprint và key attributes.
- Trạng thái refresh đang diễn ra.
- Phiên bản trust profile.

### 10.2. Khi JWKS endpoint không khả dụng

Policy cần định nghĩa:

- Có tiếp tục dùng cached key còn tin cậy hay không.
- Stale cache tối đa bao lâu.
- Khi nào từ chối token vì key mới chưa thể xác minh.
- Cách nhận thông báo compromise khẩn cấp.
- Cách phân biệt issuer outage với token có `kid` lạ.

Không dùng stale key vô thời hạn. Cũng không tải key từ nguồn không tin cậy chỉ để duy trì availability.

### 10.3. Cache không thay thế key lifecycle

Cache giúp xác minh nhanh, nhưng không quản lý trạng thái private key. Issuer vẫn phải có registry về key active/retiring/compromised và lịch rotation. Resource server cần nhận được thay đổi trust configuration theo một cơ chế có kiểm soát.

## 11. Bài lab end-to-end

Thực hiện bài lab trong môi trường cô lập, dùng issuer, audience, key và dữ liệu synthetic.

### Bước 1 — Khai báo trust profile

Chọn:

~~~text
issuer   = https://identity.example
audience = https://orders-api.example
algorithm = RS256
token_type = at+jwt
key_id = rsa-2026-01
token_lifetime = 300 seconds
~~~

Resource server chỉ tin issuer và audience này trong môi trường lab.

### Bước 2 — Sinh key pair

Sinh private/public key bằng công cụ mật mã hoặc KMS/HSM test. Kiểm tra public key thực sự tương ứng với private key và ghi lại key ID.

### Bước 3 — Đưa public key vào JWKS

Chuyển public key thành JWK và công bố trong JWKS test. Kiểm tra endpoint chỉ chứa public parameters. Đảm bảo không có private member như `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc `k`.

### Bước 4 — Cấu hình issuer ký token

Issuer dùng:

- `kid` đang active.
- Thuật toán RS256 theo allowlist.
- Private key reference trong key store.
- Claims `iss`, `sub`, `aud`, `iat`, `exp`, `jti` và scope tối thiểu.
- Token type theo profile.

### Bước 5 — Cấp access JWT

Xác thực principal/client trong lab, áp dụng policy cấp quyền rồi ký JWS. Lưu ý chỉ giữ token trong bộ nhớ test hoặc secret-safe output; không ghi raw token vào log.

### Bước 6 — Xác minh tại resource server

Resource server tải JWKS qua URL tin cậy, chọn key theo issuer và `kid`, xác minh signature, sau đó kiểm tra claims và quyền truy cập.

### Bước 7 — Thử các trường hợp từ chối

- Sửa một byte trong payload.
- Thay signature.
- Thay `kid` sang giá trị không tồn tại.
- Đổi `alg` sang thuật toán không được phép.
- Dùng token có audience khác.
- Dùng token hết hạn.
- Dùng token có issuer khác.
- Gửi ID Token vào endpoint chỉ nhận access token.

Tất cả phải bị từ chối. Không được có trường hợp chỉ vì chữ ký hợp lệ mà token được chấp nhận sai audience hoặc sai loại.

### Bước 8 — Rotation

Tạo key pair thứ hai với `kid` mới. Publish public key mới, đợi cache refresh, chuyển issuer sang ký bằng key mới, xác minh cả token cũ và token mới trong thời gian overlap, sau đó retire key cũ khi các token cũ hết hạn.

### Bước 9 — Kiểm tra sự cố

Trong lab, mô phỏng key bị disable hoặc xóa khỏi trust configuration. Xác nhận verifier nhận thay đổi theo cơ chế khẩn cấp và token ký bằng key bị compromise bị từ chối theo incident policy.

## 12. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token ký bằng private key tương ứng public key trong JWKS | Chữ ký hợp lệ; tiếp tục kiểm tra claims |
| Token bị sửa payload sau khi ký | Chữ ký không hợp lệ |
| Token ký bằng private key khác | Chữ ký không hợp lệ |
| `kid` không tồn tại | Refresh JWKS có giới hạn; sau đó từ chối |
| `kid` trùng ở issuer khác | Không chọn key của issuer khác |
| `alg` không nằm trong allowlist | Từ chối trước khi verify |
| `alg: none` | Từ chối |
| RSA public key bị dùng như HMAC secret | Từ chối do algorithm/key-type mismatch |
| JWK có `use` không phải `sig` | Từ chối |
| JWK `key_ops` không cho phép verify | Từ chối |
| JWKS chứa private member | Kiểm tra deployment thất bại; không publish |
| Issuer không nằm trong trust registry | Từ chối |
| `iss` đã xác minh không khớp profile | Từ chối |
| Audience không đúng API | Từ chối |
| ID Token được gửi như access token | Từ chối |
| Token hết hạn hoặc chưa tới `nbf` | Từ chối |
| Scope không đủ | 403 hoặc kết quả từ chối theo API contract |
| Subject không có quyền trên object | Từ chối |
| JWKS endpoint timeout nhưng cached key còn hợp lệ theo policy | Xử lý theo stale-cache policy đã định nghĩa |
| JWKS trả metadata issuer sai | Từ chối metadata |
| Rotation bình thường | Token mới và token cũ còn hạn đều xác minh được trong overlap |
| Key cũ bị retire sau overlap | Token cũ hết hạn không còn được chấp nhận |
| Key bị compromise | Key ID bị chặn theo incident policy; cache được cập nhật khẩn cấp |
| Private key xuất hiện trong log/artifact | Kiểm thử thất bại và phát cảnh báo |

## 13. Vận hành và quan sát

Ghi nhận kết quả vận hành bằng metadata an toàn:

~~~json
{
  "event": "jwt.signature_verification",
  "request_id": "req-lab-0001",
  "issuer_profile": "identity-lab",
  "kid": "rsa-2026-01",
  "algorithm": "RS256",
  "result": "success",
  "duration_ms": 4
}
~~~

Không ghi raw JWT, private key, secret, toàn bộ claims hoặc dữ liệu cá nhân không cần thiết.

Metrics nên theo dõi:

- Số token được ký theo issuer/key version.
- Số lần verify thành công/thất bại theo issuer và failure code.
- Tỷ lệ unknown `kid` và JWKS refresh.
- JWKS fetch latency, cache hit ratio và stale-cache usage.
- Thời gian ký tại KMS/HSM.
- Số key active/retiring/compromised.
- Thời gian phân phối key rotation tới resource server.
- Sự kiện signature failure tăng bất thường.

Không dùng raw token, subject hoặc token reference có cardinality cao làm metric label. Dùng log/trace đã redact để điều tra từng request.

## 14. Những lỗi thiết kế thường gặp

### Lỗi 1 — Chia sẻ private key cho mọi resource server

Resource server có thể tự ký token nếu bị xâm nhập.

**Cách sửa:** private key chỉ nằm ở issuer/KMS/HSM; verifier chỉ nhận public key.

### Lỗi 2 — Dùng `kid` để tải URL từ token

Header có thể bị attacker điều khiển để kích hoạt fetch URL hoặc thay nguồn khóa.

**Cách sửa:** `kid` chỉ tra trong JWKS đã gắn với issuer tin cậy.

### Lỗi 3 — Chấp nhận mọi `alg` mà thư viện hỗ trợ

Verifier có thể rơi vào algorithm confusion hoặc chấp nhận thuật toán yếu/không phù hợp.

**Cách sửa:** pin allowlist thuật toán và ràng buộc với key type.

### Lỗi 4 — Chỉ kiểm tra chữ ký

Token có thể được ký đúng nhưng dành cho API khác hoặc đã hết hạn.

**Cách sửa:** kiểm tra issuer, audience, token type, thời gian, schema, scope và quyền tài nguyên.

### Lỗi 5 — Gỡ public key cũ quá sớm

Token cũ còn hạn nhưng verifier không còn public key để xác minh.

**Cách sửa:** giữ public key cũ trong overlap đủ dài theo maximum token lifetime, clock skew và JWKS cache.

### Lỗi 6 — Giữ public key compromise vì cache

Verifier tiếp tục tin key đã bị lộ để tránh gián đoạn.

**Cách sửa:** có emergency deny/purge mechanism; compromise cần xử lý khác rotation bình thường.

### Lỗi 7 — Công bố private JWK trong JWKS

Endpoint vô tình làm lộ quyền ký token.

**Cách sửa:** public JWKS chỉ chứa public parameters; có automated test kiểm tra không có private members.

### Lỗi 8 — Ký token tùy ý qua signing service

Workload có thể yêu cầu ký claims tùy ý, tạo signing oracle.

**Cách sửa:** signing service xác thực caller và tự áp dụng policy cấp token trước khi ký.

## 15. Checklist triển khai production

### Issuer và signing

- [ ] Issuer identifier được cấu hình cố định và quản trị.
- [ ] Private key được giữ trong KMS/HSM hoặc key store có kiểm soát.
- [ ] Chỉ workload cần thiết có quyền ký.
- [ ] Thuật toán ký nằm trong allowlist.
- [ ] `kid` duy nhất trong key set của issuer.
- [ ] Claims tối thiểu, audience cụ thể và lifetime hợp lý.
- [ ] Signing service không cho ký payload tùy ý.
- [ ] Audit thao tác ký không ghi token hoặc key material.

### JWKS và verifier

- [ ] JWKS chỉ công bố public key.
- [ ] JWKS URI được lấy từ trust configuration/discovery đã xác minh.
- [ ] Verifier kiểm tra issuer và audience.
- [ ] `kid` chỉ chọn candidate trong key set đúng issuer.
- [ ] Kiểm tra `kty`, `use`, `key_ops`, `alg` và key strength.
- [ ] Verifier pin algorithm allowlist và từ chối `none`.
- [ ] Kiểm tra token type, exp, nbf, iat và claims schema.
- [ ] Authorization kiểm tra scope và quyền trên object.
- [ ] Unknown `kid` refresh có rate limit.

### Lifecycle và vận hành

- [ ] Có key inventory, owner, trạng thái và lịch rotation.
- [ ] Có overlap giữa key cũ và mới.
- [ ] Cache JWKS có TTL và stale policy rõ ràng.
- [ ] Có quy trình emergency key compromise.
- [ ] Tách key/issuer/audience giữa môi trường.
- [ ] Có metrics về ký, verify, JWKS và rotation.
- [ ] Log không chứa raw JWT hoặc private key.
- [ ] Có test corpus cho signature, claims, audience, rotation và compromise.

## 16. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Thành phần nào giữ private key để ký access JWT? | Authorization Server hoặc signing service/KMS được ủy quyền. |
| Resource server cần giữ loại key nào? | Public key tương ứng để xác minh. |
| Có thể dùng public key để tạo chữ ký RSA hợp lệ không? | Không, nếu dùng đúng thuật toán chữ ký bất đối xứng. |
| JWKS công khai có được chứa private member `d` không? | **Không.** Chỉ công bố public parameters. |
| `kid` có chứng minh token hợp lệ không? | **Không.** Nó chỉ giúp chọn candidate key. |
| Có nên để header `alg` tự quyết định thuật toán verifier không? | **Không.** Verifier phải pin allowlist từ cấu hình. |
| Chữ ký hợp lệ có đủ để chấp nhận token không? | **Không.** Còn phải kiểm tra issuer, audience, type, thời gian, claims và authorization. |
| Vì sao cần giữ public key cũ trong rotation? | Để xác minh token cũ còn hạn đã được ký trước khi chuyển key. |
| Có nên giữ key bị compromise trong overlap bình thường không? | **Không.** Phải có emergency disable/purge theo incident policy. |
| Token JWS có được mã hóa payload không? | **Không.** Chữ ký bảo vệ integrity/authenticity; payload thường đọc được. |
| KMS/HSM có loại bỏ nhu cầu kiểm tra policy cấp token không? | **Không.** KMS bảo vệ thao tác key; issuer vẫn phải kiểm soát ai được yêu cầu ký và claims nào được phát hành. |

## 17. Ghi nhớ

- Issuer ký bằng private key; resource server xác minh bằng public key. Không chia sẻ private key cho verifier.
- JWS signing input là protected header và payload đã Base64url encode; mọi thay đổi sau ký làm chữ ký không còn hợp lệ.
- Chọn thuật toán từ policy cấu hình, không từ token; ràng buộc thuật toán với loại khóa và từ chối `none`.
- JWKS chỉ công bố public parameters; nguồn JWKS phải gắn với issuer tin cậy.
- `kid` là gợi ý chọn key trong key set đúng issuer, không phải bằng chứng xác thực.
- Sau khi signature hợp lệ, vẫn phải kiểm tra `iss`, `aud`, `typ`, thời gian, schema, scope và quyền trên tài nguyên.
- Bảo vệ private key bằng KMS/HSM, quyền tối thiểu, audit và quy trình rotation.
- Rotation bình thường cần overlap; key compromise cần emergency deny/purge và đánh giá token đã ký.
- Cache JWKS phải có TTL, refresh control và stale policy rõ ràng.
- Kiểm thử end-to-end gồm token hợp lệ, chữ ký sai, sai audience/issuer/type, key rotation và compromise.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 – JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8037 – CFRG Elliptic Curve Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8414 – OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [NIST SP 800-57 Part 1 – Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
