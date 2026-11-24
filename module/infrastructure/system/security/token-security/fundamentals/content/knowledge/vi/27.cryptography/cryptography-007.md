# Signature verification

Một resource server nhận chuỗi trông như JWT, gồm ba đoạn ngăn bằng dấu chấm. Payload sau khi Base64URL decode có `sub=user-123`, `role=ADMIN` và `exp` còn hạn. Ứng dụng lập tức tin dữ liệu đó để cho phép thao tác quản trị. Đây là một lỗ hổng nghiêm trọng: **giải mã được JWT không đồng nghĩa với xác minh được chữ ký**, và ngay cả **chữ ký hợp lệ cũng không đủ để cấp quyền** nếu issuer, audience, token type, scope hoặc quyền trên tài nguyên không đúng.

**Signature verification** là quá trình xác minh tính toàn vẹn và nguồn gốc của nội dung được ký bằng khóa tin cậy theo một thuật toán đã được cho phép. Trong hệ sinh thái OAuth 2.0/OpenID Connect (OIDC), thao tác này đặc biệt quan trọng khi **access token hoặc ID token được biểu diễn bằng JWT có chữ ký JWS**. Chữ ký chỉ bảo đảm rằng nội dung ký chưa bị thay đổi và được tạo bởi bên giữ khóa ký phù hợp; **nó không tự xác định token được phép dùng ở API hiện tại**.

Bài thuộc chương **Cryptography** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung đi từ nền tảng chữ ký số/MAC, cấu trúc JWS/JWT và các thuật toán HS256/RS256/PS256/ES256/EdDSA, tới thiết lập trust anchor, JWKS, key rotation, chống algorithm/key confusion, xác minh claims và token type, triển khai Java/Spring Security, ranh giới JWT/opaque token và các ca kiểm thử an toàn.

## 1. Signature verification trả lời câu hỏi nào?

Giả sử Orders API nhận access token dưới dạng JWT:

```text
Authorization: Bearer BASE64URL_HEADER.BASE64URL_PAYLOAD.BASE64URL_SIGNATURE
```

Có ba câu hỏi khác nhau:

| Câu hỏi | Cơ chế trả lời |
|---|---|
| **Nội dung có bị sửa từ khi được ký không?** | Xác minh chữ ký JWS/MAC trên đúng signing input. |
| **Token được bên nào được tin cậy phát hành?** | Trust anchor, public key hoặc shared secret đã cấu hình theo issuer, cộng kiểm claim `iss`. |
| **Token này có thể dùng cho request hiện tại không?** | Kiểm `aud`, `exp`, `nbf`, token type, `scope`/authority, client, tenant, owner và trạng thái revoke. |

Ví dụ kẻ tấn công sửa payload từ `"scope":"orders.read"` thành `"scope":"orders.approve"` nhưng giữ nguyên signature. Nếu RS xác minh đúng, chữ ký **không còn khớp**, request phải bị từ chối.

Ngược lại, một access JWT **có chữ ký đúng của issuer** nhưng `aud=payments-api` vẫn **không hợp lệ cho Orders API**. Đây là lý do cần phân biệt **cryptographic validity** với **authorization validity**.

## 2. Chữ ký số, MAC và mã hóa: đừng gộp thành một

| Cơ chế | Khóa | Tính chất đạt được | Không tự cung cấp |
|---|---|---|---|
| **Chữ ký bất đối xứng** | Issuer ký bằng private key; verifier kiểm bằng public key. | Integrity và xác nhận người giữ private key tương ứng đã ký. | Confidentiality, authorization, chống replay tự động. |
| **MAC/HMAC** | Issuer và verifier dùng cùng shared secret. | Integrity và xác thực giữa các bên chia sẻ secret. | Bằng chứng bên nào trong nhóm giữ secret đã tạo MAC; confidentiality. |
| **Authenticated encryption** | Khóa mã hóa/xác thực theo thuật toán. | Bí mật và toàn vẹn ciphertext theo security model. | Chữ ký công khai có thể kiểm bằng public key. |
| **Hash đơn thuần** | Không có khóa. | Phát hiện thay đổi khi digest đáng tin được đối chiếu. | Chống attacker tự sửa payload **và tính lại hash**. |

Chữ ký JWT **không mã hóa payload**. Bất kỳ ai có chuỗi JWS Compact thông thường đều có thể Base64URL decode phần header và payload, kể cả khi không có khóa xác minh. **Không đưa mật khẩu, refresh token, private key hoặc dữ liệu cá nhân không cần thiết vào claims**.

### Ví dụ so sánh

```text
SHA-256(payload):
  Ai cũng có thể tính hash mới nếu tự sửa payload.

HS256(payload, secret):
  Chỉ bên có secret mới tạo MAC đúng.

RS256(payload, privateKey):
  Bên giữ private key ký; RS dùng public key để verify.

JWE encryption:
  Che nội dung theo bộ khóa/thuật toán, không thay toàn bộ
  chính sách verify signature và claims khi profile yêu cầu JWS.
```

Trong OAuth/OIDC, chọn cơ chế đúng theo **token format và profile đã thỏa thuận**, không nhìn thấy ba đoạn và tự kết luận đó là “encrypted token”.

## 3. JWS, JWT, JWE và opaque token khác nhau thế nào?

- **JWT (RFC 7519)** mô tả một dạng biểu diễn tập claims, có thể được bảo vệ bởi **JWS** hoặc **JWE** theo profile.
- **JWS (RFC 7515)** biểu diễn nội dung có chữ ký hoặc MAC; **JWS Compact Serialization** điển hình có **3 đoạn**.
- **JWE (RFC 7516)** biểu diễn nội dung được mã hóa; **JWE Compact Serialization** điển hình có **5 đoạn**. Nếu là nested JWT, cần xử lý cả encryption và signature đúng profile/thứ tự.
- **Opaque access token** là chuỗi định danh mà RS không tự hiểu claims; thường phải kiểm trạng thái/metadata bằng **introspection** hoặc nguồn tin cậy phía AS.
- **ID token** là JWT trong OIDC được RP kiểm tra danh tính; **access token** dành cho RS. Một token có chữ ký đúng vẫn có thể sai mục đích.

| Dữ liệu đầu vào | Nên làm gì? |
|---|---|
| JWT access token có JWS | Verify chữ ký và xác minh đầy đủ claims/type theo API profile. |
| JWT ID token | OIDC ID Token Validation tại RP, gồm signature/issuer/audience/time/nonce khi có. |
| Opaque access token | Introspection hoặc status service đáng tin; không tự split rồi đoán claims. |
| JWE/nested JWT | Decrypt với khóa/thuật toán hợp lệ, xác minh signature bên trong khi profile yêu cầu, rồi validate claims. |
| Refresh token | Chỉ dùng theo refresh grant ở AS; không chấp nhận tại business API. |

**Không gửi ID token tới resource API** chỉ vì cùng OP/AS phát hành. RS cần token dành cho mình và đầy đủ authorization.

## 4. Cấu trúc JWS Compact và bytes được ký

Một JWS Compact thông thường có dạng:

```text
BASE64URL(UTF8(protected header))
.
BASE64URL(payload bytes)
.
BASE64URL(signature bytes)
```

JWS Signing Input theo RFC 7515:

```text
ASCII(
  BASE64URL(UTF8(protected header))
  + "."
  + BASE64URL(payload bytes)
)
```

Dấu chấm giữa hai đoạn là **một byte ký tự ASCII thật**. Bên xác minh phải dùng **chính xác hai đoạn đã được mã hóa trên wire**, không tái serialize JSON rồi verify.

### Ví dụ header và payload ở dạng dễ đọc

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "rsa-2026-11"
}
```

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410600
}
```

Hai object là **dữ liệu minh họa**, không phải token thật. Khi ký, issuer Base64URL encode **chuỗi bytes JSON cụ thể**. Thứ tự property, khoảng trắng và cách escape ký tự có thể làm bytes khác; verifier **không được JSON.stringify lại** để tính chữ ký.

### Base64URL không phải encryption

Base64URL dùng bảng chữ phù hợp URL, thường **không có padding `=`** trong JWT Compact thông dụng. Decoder có thể đọc nội dung dễ dàng, nhưng **không thể tự tạo chữ ký hợp lệ** nếu không có signing key.

## 5. Từng bước xác minh JWS đúng ranh giới

```mermaid
flowchart TD
    T[Nhận token ở API] --> SHAPE{Đúng cấu trúc token theo profile?}
    SHAPE -- Không --> DENY[Từ chối / 401]
    SHAPE -- Có --> CONF[Chọn trust config theo API/issuer đã cho phép]
    CONF --> HEADER[Đọc protected header như dữ liệu CHƯA tin]
    HEADER --> ALG{alg/kty/key được policy cho phép?}
    ALG -- Không --> DENY
    ALG -- Có --> KEY[Chọn khóa từ JWKS/secret tin cậy]
    KEY --> SIG{Verify chữ ký trên encoded header.payload?}
    SIG -- Không --> DENY
    SIG -- Có --> CLAIM{iss/aud/exp/nbf/type đúng?}
    CLAIM -- Không --> DENY
    CLAIM -- Có --> AUTH{scope, tenant, owner, revoke state đúng?}
    AUTH -- Không --> FORBID[Từ chối / 403 hoặc 401 theo lỗi]
    AUTH -- Có --> ALLOW[Cho phép operation]
```

Quy trình có thể thay đổi thứ tự kiểm tra nội bộ để tối ưu, nhưng **không được trao quyền từ payload chưa verified**. Lỗi signature/issuer/audience/time/token type thường dẫn tới `401 invalid_token`; thiếu scope hoặc vi phạm business authorization thường là `403` theo RFC 6750 và API contract.

## 6. Thuật toán `alg`: ai được phép quyết định?

Protected header có field `alg`. Ví dụ:

```json
{"alg":"RS256","kid":"rsa-2026-11","typ":"JWT"}
```

**`alg` nằm trong token do caller cung cấp**, vì vậy không được dùng nó như quyền tự do chọn thuật toán verification.

Thiết kế đúng:

1. Hệ thống cấu hình **algorithm allowlist** theo issuer/token profile.
2. Lấy `alg` trong header chỉ để **kiểm nó phù hợp policy**.
3. Chọn verification key **đúng loại** được đăng ký/tin cậy cho thuật toán.
4. Không cho token hạ xuống thuật toán yếu hoặc `none`.
5. Không tự chuyển public key thành HMAC secret do header khai HS256.

**Không chấp nhận thuật toán chỉ vì cryptographic library “hỗ trợ”.** Một thư viện hỗ trợ cả `none`, HS256 và RS256 không có nghĩa API này được phép dùng cả ba.

## 7. HS256: HMAC-SHA-256 và giới hạn shared secret

**HS256** là JWS sử dụng **HMAC-SHA-256**. Bên phát và bên verify dùng **cùng khóa bí mật**.

```text
mac = HMAC-SHA-256(sharedSecret, signingInput)
verify = constantTimeCompare(mac, receivedSignature)
```

Theo RFC 7518, khóa HMAC phải đủ mạnh (với HS256, tối thiểu kích thước phù hợp output 256 bit của SHA-256). **Không dùng password ngắn, email, client ID hoặc chuỗi dự đoán được làm HS256 secret**.

### Rủi ro kiến trúc với nhiều resource servers

Nếu Orders API, Payments API và Reports API cùng giữ **HS256 signing secret** của AS để verify JWT, **bất kỳ RS nào bị lộ secret cũng có thể tự tạo MAC hợp lệ**. Khi cần nhiều verifier không được phép ký, chữ ký bất đối xứng thường dễ chia ranh giới trust hơn: **AS giữ private key, RS chỉ có public key**.

HS256 không “không an toàn” tự thân; rủi ro thường nằm ở **quản lý shared secret, phân phối bí mật, entropy và quyền tạo token ngoài ý muốn**.

### Không dùng public key làm HMAC secret

Một dạng **algorithm confusion** nguy hiểm: RS dự kiến verify RS256 bằng RSA public key nhưng token giả khai `alg=HS256`, và verifier lỗi dùng bytes public key như HMAC secret. Vì public key công khai, attacker có thể tính MAC tương ứng.

Phòng vệ: **khóa và thuật toán được ràng buộc trong cấu hình**, không dùng một biến string key đa năng cho HS/RS.

## 8. RS256: RSA chữ ký bất đối xứng

**RS256** sử dụng RSA signature scheme **RSASSA-PKCS1-v1_5** với SHA-256 theo JWA (RFC 7518).

- Authorization server ký bằng **RSA private key**.
- Resource server xác minh bằng **RSA public key** lấy từ trust source đáng tin.
- Public key có thể được phân phối qua JWKS; RS **không cần nắm private key**.
- Key modulus cần đáp ứng tiêu chuẩn/kích thước phù hợp; RFC 7518 yêu cầu RSA key size ít nhất **2048 bit** cho JWA RSA algorithms.

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS Endpoint
    participant RS as Resource Server
    AS->>AS: Build JWT header + claims
    AS->>AS: Sign RS256 bằng RSA private key
    AS-->>RS: Access JWT qua client request
    RS->>JWKS: Lấy/cập nhật public JWKS theo issuer cố định
    JWKS-->>RS: RSA public key với kid đã đăng ký
    RS->>RS: Verify RS256 signing input
    RS->>RS: Check iss/aud/exp/scope/tenant
```

**Một chữ ký RSA hợp lệ chỉ chứng minh token được ký bởi private key tương ứng public key đã chọn**. Chứng minh **đó là khóa của issuer được tin** là việc của trust configuration/JWKS, không thể lấy từ chữ ký một mình.

## 9. PS256: RSA-PSS khác RS256

**PS256** dùng **RSASSA-PSS** với SHA-256, MGF1 SHA-256 và tham số salt phù hợp JWA.

| Thuộc tính | RS256 | PS256 |
|---|---|---|
| RSA scheme | RSASSA-PKCS1-v1_5 | RSASSA-PSS |
| Hash | SHA-256 | SHA-256 |
| Signature encoding | RSA signature octets | RSA signature octets |
| Cấu hình verifier | PKCS#1 v1.5 | Phải cấu hình PSS đúng thông số |
| Có thay thế tùy ý? | **Không** | **Không** |

Không xem PS256 và RS256 là “đều RSA/SHA256 nên có thể verify bằng cùng một JCA call”. Ví dụ `Signature.getInstance("SHA256withRSA")` trong JCA tương ứng RS256, **không phải** PS256. Với PSS, nên dùng JOSE library uy tín hoặc cấu hình `RSASSA-PSS` và `PSSParameterSpec` chính xác.

Chọn thuật toán dựa trên **issuer contract, security policy, client/RS support**, không dựa trên khả năng đoán của token.

## 10. ES256: ECDSA và sự khác biệt DER/JWS encoding

**ES256** dùng ECDSA với **P-256** và SHA-256.

Trong JWS, chữ ký ES256 được biểu diễn dưới dạng **chuỗi cố định `R || S`**, mỗi thành phần 32 bytes (tổng 64 bytes), **không phải ASN.1 DER sequence** thường thấy trong một số API mật mã.

```text
JWS ES256 signature:
  R (32 bytes) || S (32 bytes) = 64 bytes

Một số Java JCA ECDSA APIs:
  Signature.getInstance("SHA256withECDSA")
  tạo/nhận ECDSA signature ở ASN.1 DER format
```

Vì vậy, **không trực tiếp đưa 64 bytes JWS ES256 vào JCA verifier chờ DER** hoặc áp dụng conversion thủ công thiếu chuẩn hóa. Dùng Nimbus JOSE + JWT hoặc thư viện JOSE đã xử lý encoding, curve/key validation và lỗi signature đúng.

**Đừng trộn EC key curves:** `ES256` dùng P-256; `ES384` dùng P-384; `ES512` dùng P-521. Thuật toán, key type và curve phải tương thích với policy.

## 11. EdDSA/Ed25519 và hỗ trợ thư viện

Trong JOSE, `EdDSA` (RFC 8037) mô tả chữ ký dùng các EdDSA curves được hỗ trợ, thường là **Ed25519**.

- Issuer ký bằng private key Ed25519.
- RS verify bằng public key đã được pin/tin theo issuer.
- JWK key type cho OKP sử dụng các trường như `kty=OKP`, `crv=Ed25519` và `x`.
- Không được tự suy rằng mọi runtime/JDK/JOSE library hỗ trợ `EdDSA` với cấu hình giống nhau.

Ví dụ một header:

```json
{"alg":"EdDSA","kid":"ed25519-2026-11","typ":"at+jwt"}
```

**Lưu ý:** `typ=at+jwt` là định danh token type cho profile JWT access token, không phải một trường bảo đảm token đã được phép dùng. Cần xác minh cryptographic key/alg và claims.

Khi chọn EdDSA, kiểm môi trường hỗ trợ, quy định tổ chức/FIPS khi áp dụng và khả năng key rotation, không tự thêm thuật toán vào allowlist chỉ vì public key xuất hiện trong JWKS.

## 12. `alg=none`: vì sao phải từ chối trong access-token/API context?

JWS/JWT specifications từng mô tả **Unsecured JWT/JWS** với `alg=none` cho các trường hợp được quy định riêng. Nhưng **API dùng access token để cấp quyền không được chấp nhận một token không có chứng cứ mật mã tin cậy chỉ vì header khai none**.

Ví dụ giả mạo:

```text
header:  {"alg":"none","typ":"JWT"}
payload: {"sub":"admin","aud":"orders-api","scope":"orders.approve"}
signature: <empty>
```

Nếu RS chỉ Base64URL decode rồi tin claims, attacker có thể tự đổi thành admin.

**Policy minh bạch:** trong hệ thống này, access/ID JWT phải được ký bằng thuật toán đã đăng ký hoặc bảo vệ theo profile khác rõ ràng; `alg=none` bị reject. Không “fallback unsigned” khi JWKS endpoint không truy cập được.

## 13. `kid` chỉ là gợi ý chọn khóa, không phải nguồn trust

Protected header thường có `kid`:

```json
{"alg":"RS256","kid":"rsa-2026-11","typ":"JWT"}
```

`kid` là key identifier **do token chứa**. Nó giúp verifier tìm đúng key trong tập khóa **đã tin cậy**.

**Không**:

- Dùng `kid` làm đường dẫn file trực tiếp, ví dụ đọc `/keys/<kid>` mà không kiểm chuẩn.
- Dùng `kid` ghép thành URL rồi tải public key từ Internet.
- Dùng `kid` làm SQL/query không parameterized.
- Dùng `kid` của issuer A để tìm key issuer B trong một global map.
- Khi không thấy `kid`, tự dùng một public key do caller cung cấp.

**Nên**:

- Giới hạn length/charset của `kid` theo implementation.
- Chỉ tìm key trong **trusted issuer JWKS/key ring** đã cấu hình.
- Match key type, algorithm, usage/operations và key status.
- Kiểm signature và tất cả claims sau khi chọn key.
- Nếu không tìm thấy key phù hợp, **fail closed**, có thể refresh JWKS có kiểm soát.

**`kid` không phải định danh toàn cục duy nhất.** Hai issuers có thể dùng trùng `kid=rsa-1`; key lookup phải gắn issuer/trust domain.

## 14. JWKS: public keys đến từ đâu và được tin thế nào?

**JSON Web Key Set (JWKS)** là tập JWKs chứa metadata/key material công khai cho verifier. Ví dụ một RSA public JWK:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "rsa-2026-11",
      "alg": "RS256",
      "n": "RSA_MODULUS_BASE64URL_PLACEHOLDER",
      "e": "AQAB"
    }
  ]
}
```

Đây là **mẫu hình thức**, không phải key đủ để verify. Giá trị `n` là modulus thật phải được tạo/phát hành bởi hệ thống ký và thỏa kích thước an toàn.

### Trust chain phải bắt đầu từ cấu hình, không từ token

Một RS có thể biết trước:

```text
Trusted issuer:
    https://id.example.test

Trusted metadata/JWKS:
    Lấy từ OIDC/OAuth AS discovery của issuer đã cấu hình
    hoặc JWKS URI cố định đã được thẩm định.

Allowed alg:
    RS256

Expected audience:
    orders-api
```

Luồng đáng tin: cấu hình issuer → metadata/JWKS URI của issuer đó → HTTPS + hostname verification → JWK phù hợp `kid`/`kty`/`alg` → signature → claims.

**Không đảo chiều:** nhận JWT → tin `iss` chưa verified → gọi URL bất kỳ từ payload/header → tin key trả về → coi token hợp lệ. Trong hệ thống multi-issuer, có thể đọc issuer chưa verified **chỉ như hint chọn trong allowlist cố định**, sau đó vẫn phải kiểm `iss` trùng chính xác trusted issuer của key và audience/policy.

## 15. Chống `jku`, `x5u` và embedded-key injection

Một số JWS headers có các tham số như `jku` (URL chứa JWK Set), `x5u` (X.509 URL), `x5c` (certificate chain) hoặc `jwk` (embedded key).

Attacker có thể tạo token ký bằng **private key của chính họ**, rồi đặt `jku=https://attacker.example.test/jwks.json`. Nếu RS tải URL đó và tin public key trả về, chữ ký có thể verify **bằng key của attacker**, nhưng đó **không phải issuer được tin cậy**.

```mermaid
flowchart TD
    ATT[Attacker tự ký token] --> H[Header jku trỏ đến JWKS của attacker]
    H --> BAD{Verifier tin URL trong header?}
    BAD -- Có --> LOAD[Fetch public key attacker]
    LOAD --> FAILSEC[Signature verify nhưng trust sai]
    BAD -- Không --> TRUST[Chỉ dùng pinned issuer JWKS]
    TRUST --> CHECK{Có trusted matching key?}
    CHECK -- Không --> DENY[Reject]
    CHECK -- Có --> VERIFY[Verify + claim validation]
```

**Nguyên tắc:** không dùng các key-location/key-embedding headers làm authority nếu không có profile xác thực/allowlist rất chặt. Chỉ tin certificate/JWK sau **key trust validation và issuer binding**, không coi việc có chữ ký toán học khớp một khóa bất kỳ là đủ.

### Chống SSRF khi tải JWKS

- Pin issuer/metadata origin và HTTPS.
- Không follow cross-origin redirects tùy tiện.
- Không fetch URL, IP private/link-local hoặc hostname do user kiểm soát.
- Kiểm TLS certificate/hostname đúng.
- Giới hạn response size, timeouts, content type/schema và key count.
- Cache/refresh có giới hạn để không biến `kid` lạ thành DoS.

## 16. Key rotation và thời gian tồn tại của token

AS có thể thay signing key theo chu kỳ hoặc sau sự cố. Trong một giai đoạn chuyển tiếp, JWKS có thể chứa **nhiều public keys**:

```text
K1: old signing key, đã ngừng phát token mới
K2: current signing key, đang phát token mới

JWT ký K1 còn hạn → RS có thể cần K1 để verify.
JWT ký K2 mới → RS cần refresh JWKS nhận K2.
```

**Rotation an toàn:**

1. Tạo key mới ở key manager/HSM theo policy.
2. Công bố public key K2 trước hoặc đồng thời khi bắt đầu dùng K2 theo rollout plan.
3. Ký token mới bằng K2; giữ public K1 cho tokens cũ còn hợp lệ nếu không có compromise.
4. Cho phép RS refresh JWKS có kiểm soát và đo unknown-`kid` rate.
5. Gỡ K1 sau khi các token ký K1 hết hạn cộng clock skew/caching window phù hợp, trừ khi có yêu cầu revoke.
6. Audit key IDs/algorithms và lỗi rollout mà không ghi tokens.

**Nếu private signing key K1 bị lộ**, không áp dụng quy tắc “cứ giữ K1 đến khi mọi token hết hạn”. Đây là **key compromise**; cần phối hợp loại K1 khỏi tập keys được tin, đánh giá blast radius, chặn tokens giả, tổ chức reauthentication/issuance và bảo đảm RS cập nhật trust state.

### Unknown `kid` nên xử lý thế nào?

- Có thể kích hoạt **JWKS refresh tối đa theo rate/budget** để tránh token mới bị từ chối vì rotation.
- Nếu sau refresh vẫn không có key phù hợp, **reject**.
- Không thử mọi issuer JWKS hoặc mọi URL trong header.
- Không “tạm bỏ verify” vì key mới chưa xuất hiện.

## 17. Kiểm `crit` và các mở rộng header

JWS có trường `crit` để báo các header parameters **phải được hiểu và xử lý** bởi verifier. Nếu một token có critical extension mà verifier không hỗ trợ, nó **phải bị từ chối**, không được bỏ qua rồi vẫn chấp nhận signature.

Ví dụ minh họa cần thận trọng:

```json
{
  "alg": "RS256",
  "crit": ["custom-policy"],
  "custom-policy": "special-meaning"
}
```

Nếu application không hiểu/nghiệm được `custom-policy` theo profile, **reject**.

Đặc biệt, JWS còn có cơ chế **`b64=false`** (RFC 7797) cho payload không Base64URL-encoded. Đây là mở rộng có điều kiện và xử lý signing input khác. JWT thông thường trong OAuth/OIDC cần dùng profile hợp lệ của nó; **đừng tự viết parser “split dot, decode ba đoạn” để chấp nhận mọi biến thể JWS**.

**Đối với access JWT thông thường, ưu tiên JOSE library theo profile đã khóa**, không mở generic JWS extensions vô điều kiện.

## 18. Signature hợp lệ nhưng `iss` sai vẫn phải từ chối

Giả sử RS tin hai public keys do nội bộ phát hành nhưng Orders API chỉ chấp nhận issuer `https://id.example.test`.

Token:

```json
{
  "iss": "https://other-id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "exp": 1795410600
}
```

Ngay cả khi verify chữ ký bằng một key công khai hợp lệ ở key store khác, **issuer không khớp trust policy**. Phải reject.

**Issuer là namespace và trust boundary.** Một `sub=user-123` của issuer A không tự là cùng user với `sub=user-123` của issuer B. RS không được hợp nhất identities khi chỉ trùng `sub` hoặc `kid`.

### Chú ý thứ tự đọc issuer

Để tìm JWKS trong hệ thống multi-issuer, một số implementation có thể đọc unverified `iss` như một **routing hint**. Chỉ được chọn trong danh sách trusted issuers đã cấu hình; sau verify phải so `iss` chính xác. **Không biến issuer hint thành quyền tải arbitrary URLs**.

## 19. Signature hợp lệ nhưng `aud` sai vẫn phải từ chối

Access token có:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "payments-api",
  "scope": "payments.read",
  "exp": 1795410600
}
```

Orders API phải từ chối token này, dù AS cùng issuer phát hành và signature hoàn toàn đúng.

| Claim | Được dùng để kiểm gì? |
|---|---|
| `iss` | Nguồn phát hành và trust domain. |
| `aud` | Resource server hoặc client dự kiến nhận token. |
| `sub` | Subject trong issuer namespace. |
| `client_id` / `azp` | OAuth client/authorized party theo token profile. |
| `scope` / `scp` | Tập quyền đã cấp theo hợp đồng với AS. |
| `exp`, `nbf`, `iat` | Thời gian hiệu lực và thời điểm phát hành. |
| `jti` | Định danh JWT hữu ích cho denylist/replay detection theo policy. |

**`aud` trong OIDC ID token thường là RP client ID**, còn `aud` của access token dùng cho RS. Một RS không được nhận ID token rồi kiểm `aud=orders-web` như bằng chứng API permission.

## 20. Thời gian: `exp`, `nbf`, `iat` và clock skew

**Signature không có khái niệm “hết hạn”.** Một chữ ký số có thể verify đúng đối với JWT đã hết hạn từ lâu.

| Claim | Cần kiểm |
|---|---|
| `exp` | Reject sau thời điểm token hết hiệu lực, xét clock skew nhỏ theo policy. |
| `nbf` | Không chấp nhận trước thời điểm hiệu lực. |
| `iat` | Thời điểm phát hành hợp lý; dùng với policy về token age khi cần. |
| `auth_time` | OIDC user authentication freshness nếu có yêu cầu `max_age`/reauthentication. |
| `jti` | Dùng cho revoke/replay status nếu hệ thống thiết kế. |

JWT NumericDate thường biểu diễn **giây từ Unix epoch**, không phải milliseconds của Java `System.currentTimeMillis()`.

### Ví dụ

```text
issued_at     = 1795410000
expires_at    = 1795410600
ttl           = 600 giây
allowed_skew  = 30 giây theo policy cụ thể
```

Không đặt skew quá lớn để “sửa lỗi đồng hồ” vì nó mở rộng cửa sổ chấp nhận token. Dùng đồng bộ thời gian (NTP) và monitor drift.

**Một access JWT signature hợp lệ nhưng `exp` đã qua vẫn phải bị từ chối** nếu không có profile ngoại lệ rõ và an toàn; không dùng `iat` mới để bỏ qua `exp`.

## 21. Token type confusion: access JWT khác ID token

Một OP có thể phát **ID token JWT** và **JWT access token** bằng **cùng signing key**. Vì vậy **verify cùng public key không chứng minh token có đúng mục đích**.

| Thuộc tính | OIDC ID token | OAuth JWT access token |
|---|---|---|
| Bên nhận | **Relying Party/client**. | **Resource Server/API**. |
| Audience | Client ID của RP. | Resource/API identifier. |
| Mục đích | Xác nhận authentication. | Cho phép truy cập resource với scope/authorization. |
| Claims cần kiểm | OIDC `iss`, `aud`, `azp` khi áp dụng, `nonce` khi đã yêu cầu, thời gian và hash claims theo flow. | Access-token profile, `iss`, `aud`, `exp`, token type, scope và RS policy. |
| Có được dùng gọi API nghiệp vụ? | **Không.** | Có, nếu hợp lệ cho RS/operation. |

### `typ` và explicit typing

RFC 8725 khuyến nghị **explicit typing** để giảm cross-JWT confusion. RFC 9068 định nghĩa JWT access token profile với protected header `typ` là `at+jwt` hoặc `application/at+jwt` theo profile.

```json
{
  "alg": "RS256",
  "kid": "rsa-access-2026-11",
  "typ": "at+jwt"
}
```

**`typ` là dữ liệu header được ký, nhưng chỉ có ý nghĩa nếu verifier thực sự kiểm nó theo token profile.** Khi bật `at+jwt` validation, cần bảo đảm thư viện xử lý type đúng phiên bản/cấu hình; tránh để default `JWT` type check vô tình chặn token chuẩn hoặc bỏ qua yêu cầu profile.

Nếu AS dùng claim riêng `token_use=access`, hãy kiểm theo **hợp đồng của issuer**, không giả định mọi OAuth server đều có claim đó. **Token type và audience phải được validate cùng chữ ký**, không chỉ một trong ba.

## 22. OIDC ID Token Verification có yêu cầu riêng

Trong OIDC Authorization Code flow, RP nhận ID token từ OP. Ngoài xác minh JWS signature (trừ trường hợp validation được profile/flow định nghĩa đặc biệt), RP phải kiểm theo **OpenID Connect Core**:

- **`iss`** đúng configured OP issuer.
- **`aud`** chứa client ID của RP.
- **`azp`** khi cần theo số lượng audiences/đặc tả.
- **`exp`, `iat`** và các điều kiện thời gian.
- **`nonce`** khớp Authentication Request **nếu RP đã gửi nonce**.
- **`auth_time`** khi có `max_age`/reauthentication requirement.
- **`at_hash`/`c_hash`** theo flow/profile khi bắt buộc.
- Khóa/thuật toán theo client–OP registration, không chọn tùy tiện qua token header.

**Một ID token với signature hợp lệ nhưng nonce sai phải bị từ chối khi nonce được dùng**, bởi nó có thể đến từ giao dịch đăng nhập khác.

Tương tự, ID token có thể chứa thông tin cá nhân nên không được ghi raw payload vào logs hoặc gửi đến RS làm Bearer access token.

## 23. Signature verification không ngăn replay Bearer token

Một Bearer access token hợp lệ có thể bị **sao chép nguyên vẹn** mà không sửa bất kỳ byte nào. Signature vẫn đúng.

```text
T0: AS phát token T, ký RS256.
T1: Client dùng T tại Orders API.
T2: Attacker lấy được T từ log/thiết bị.
T3: Attacker gọi Orders API với nguyên T.
T4: RS verify chữ ký đúng -> vẫn phải kiểm các lớp khác.
```

Các biện pháp giảm rủi ro:

- Access-token TTL ngắn.
- `aud`/`scope` tối thiểu; object/tenant authorization.
- Token storage an toàn, TLS, chống XSS/log leaks.
- Revocation/denylist/grant state hoặc RFC 7662 introspection khi cần.
- **Sender-constrained tokens**: DPoP (RFC 9449) hoặc mTLS-bound (RFC 8705), nếu client/RS hỗ trợ và verify proof đúng.
- Replay detection trên `jti`/proof/nonces theo **profile áp dụng**, không tự tuyên bố JWS `jti` là one-time token cho mọi request.

**Signature verification chứng minh token không bị sửa; không chứng minh bearer là người ban đầu đã được cấp token.**

## 24. Revocation và signing key rotation là hai việc khác nhau

Một JWT access token được ký đúng bằng K1 có thể vẫn verify trong suốt thời hạn. Nếu user logout hoặc token bị nghi lộ:

- **Token revocation**: AS đánh dấu token/grant/family không còn hợp lệ; RS phải biết và enforce qua denylist, introspection hoặc status.
- **Signing key rotation**: AS chuyển sang key khác cho token mới; việc giữ K1 để verify token cũ **không tự revoke các token ký K1**.
- **Signing key compromise**: attacker có thể tạo token ký bằng private key bị lộ; đây là sự cố trust anchor nghiêm trọng, có thể đòi hỏi loại key khỏi JWKS/trusted key set.

| Hành động | Token cũ K1 | Token mới K2 |
|---|---|---|
| K1 chỉ ngừng ký, vẫn được tin để verify | Có thể còn hợp lệ đến `exp`. | Verify bằng K2. |
| Grant/token bị revoke nhưng RS không kiểm status | Có thể vẫn được RS nhận. | Tùy grant/issuance policy. |
| K1 bị loại khỏi trust vì compromised | Token K1 bị reject bởi RS đã cập nhật. | Token K2 có thể tiếp tục nếu trust sạch. |

**Không dùng key rotation làm thay thế mặc định cho per-token logout/revoke**, và không giữ compromised key chỉ để tránh gián đoạn.

## 25. Java 17: demo kiểm RS256 bằng JCA

Để thấy chính xác bytes được ký, có thể viết một **cryptographic verification demo** dùng RSA public key đã được lấy từ trust store an toàn.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;

public final class Rs256SignatureDemo {
    private Rs256SignatureDemo() {}

    /**
     * Chỉ minh họa crypto step cho JWS Compact dùng RS256.
     * trustedPublicKey đã được resolve từ issuer tin cậy.
     *
     * KHÔNG phải JWT validator đầy đủ:
     * chưa parse/kiểm alg, typ, kid, iss, aud, exp, scope, ...
     */
    public static boolean verify(
            String compactJws,
            RSAPublicKey trustedPublicKey)
            throws GeneralSecurityException {

        if (compactJws == null || trustedPublicKey == null) {
            return false;
        }

        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3
                || parts[0].isEmpty()
                || parts[1].isEmpty()
                || parts[2].isEmpty()) {
            return false;
        }

        final byte[] signatureBytes;
        try {
            signatureBytes = Base64.getUrlDecoder()
                .decode(parts[2]);
        } catch (IllegalArgumentException ex) {
            return false;
        }

        // Verify CHÍNH XÁC 2 encoded segments đã nhận,
        // không decode + JSON serialize lại trước khi verify.
        byte[] signingInput =
            (parts[0] + "." + parts[1])
                .getBytes(StandardCharsets.US_ASCII);

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedPublicKey);
        verifier.update(signingInput);

        return verifier.verify(signatureBytes);
    }
}
```

**Ranh giới rõ ràng:** đây chỉ là ví dụ thuật toán RSA signature PKCS#1 v1.5 SHA-256. **Không dùng hàm này một mình để xác thực JWT**. Một validator production còn phải kiểm protected header `alg=RS256` theo allowlist, kiểm Base64URL canonical/valid structure, key matching, `typ`, critical extensions và đầy đủ claims. Hàm không tự chọn JWKS hoặc issuer và không xử lý JWE, ES256, PS256, `b64=false`.

**Không dùng `SHA256withRSA` để verify HS256 hay PS256**, và không lấy public key từ `jku` do token cung cấp.

## 26. Java/Spring Security 6.x: xác minh JWT tại Resource Server

Spring Security OAuth 2.0 Resource Server có thể dùng `NimbusJwtDecoder` để tải trusted issuer metadata/JWKS, verify signature và chạy validators.

Ví dụ cấu hình một issuer cố định và RS256:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class OrdersJwtSecurity {
    private static final String ISSUER =
        "https://id.example.test";
    private static final String AUDIENCE =
        "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            boolean matches = jwt.getAudience() != null
                && jwt.getAudience().contains(AUDIENCE);

            return matches
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Audience mismatch", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll());

        http.oauth2ResourceServer(rs ->
            rs.jwt(jwt -> {}));

        return http.build();
    }
}
```

### Đọc đúng ví dụ

- **`ISSUER` là trust anchor cố định**, không được lấy từ caller query/JWT unverified.
- Decoder giới hạn **RS256** theo cấu hình JWS algorithm.
- `JwtValidators.createDefaultWithIssuer` kiểm các điều kiện mặc định về issuer và thời gian; **audience được thêm riêng**, không mặc định suy nó đã được kiểm đầy đủ cho API.
- `SCOPE_orders.read` chỉ cấp quyền thao tác đọc; cần **owner/tenant authorization** trong service layer.
- Với RFC 9068 `at+jwt`, cần bổ sung **token type/profile validation** tương thích phiên bản Spring Security đang dùng; đoạn này chưa đầy đủ mọi yêu cầu của RFC 9068.
- Nếu production dùng JWK Set URI trực tiếp thay issuer discovery, phải cấu hình URI của **issuer đã tin** và kiểm `iss` độc lập.
- Phần thiếu: CSRF/CORS/session policy theo kiến trúc, error handling, algorithms/provider configuration, timeout, JWKS cache, key rotation, revocation, DPoP/mTLS và tests.

**Không sửa lỗi verification bằng cách tắt signature validator**. Nếu issuer rotate key khiến `kid` tạm chưa tìm được, xử lý JWKS refresh/rollout theo đúng trust policy.

## 27. Spring Boot cấu hình qua properties và claim mapping

Một cấu hình cơ bản cho JWT resource server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://id.example.test"
```

Chỉ có `issuer-uri` **không có nghĩa API tự kiểm đúng `aud=orders-api`** hoặc mọi trường token type. Cần audience/type policy, route authorization và revocation nếu hệ thống yêu cầu.

### `scope` và authorities

Trong JWT access token, AS có thể dùng:

```json
{
  "aud": "orders-api",
  "scope": "orders.read orders.export"
}
```

Spring Security thường map scopes thành `GrantedAuthority` với prefix `SCOPE_` khi token profile hỗ trợ. Nhưng **custom claims** như `permissions`, `roles`, `scp` có thể cần converter theo hợp đồng issuer.

**Không tự động tin mọi `role=ADMIN`** trong token nếu audience/type/client/issuer sai, và không lấy `scope` bằng `rawString.contains("orders.read")`. Trường `scope` phải được parse/so khớp như tập quyền, tránh nhận nhầm `orders.read-all`.

## 28. Java/Nimbus JOSE: verify với key đã tin cậy

Một thư viện JOSE có thể xử lý signature encoding và algorithm validation tốt hơn code JCA tự xây. Mô hình dưới minh họa **RS256 signature step** bằng Nimbus:

```java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.SignedJWT;
import java.security.interfaces.RSAPublicKey;

public final class NimbusSignatureExample {

    public static boolean verifyCryptographicSignature(
            String compactJwt,
            RSAPublicKey trustedPublicKey) throws Exception {

        SignedJWT jwt = SignedJWT.parse(compactJwt);

        if (!JWSAlgorithm.RS256.equals(
                jwt.getHeader().getAlgorithm())) {
            return false;
        }

        // trustedPublicKey do hệ thống cấp từ issuer/JWKS trusted,
        // KHÔNG lấy từ jku/jwk/x5u của token.
        return jwt.verify(new RSASSAVerifier(trustedPublicKey));
    }
}
```

**Đây vẫn chưa phải full JWT acceptance**: cần kiểm token profile, header `typ`, critical extensions, issuer, audience, timestamps, scope, key ID mapping, revocation và resource authorization. Một RS production nên dùng framework decoder có các validators đã được cấu hình thay vì ghép mỗi hàm `verify()` với `getJWTClaimsSet()` rồi cấp quyền.

Đặc biệt, **đừng xử lý claims sau `SignedJWT.parse()` như đã được verified**. Parsing chỉ chuyển bytes thành object.

## 29. Fail closed: lỗi verification cần xử lý thế nào?

| Lỗi | Kết quả an toàn |
|---|---|
| JWS không đúng số đoạn/encoding. | Reject. |
| Header `alg=none`, HS256 khi policy chỉ cho RS256. | Reject. |
| `kid` không tìm thấy trong JWKS đã tin. | Refresh có kiểm soát; nếu vẫn không có thì reject. |
| `kid` trùng ở hai issuers. | Chỉ lookup trong issuer/trust domain đúng; không global fallback. |
| Signature sai. | Reject; không tin claims. |
| JWKS endpoint timeout, không có key tin cậy đã cache. | Fail closed; không bỏ verify. |
| Public key mismatch/compromised. | Reject hoặc chuyển key state theo incident policy. |
| `iss` khác issuer đã cấu hình. | Reject. |
| `aud` không có API hiện tại. | Reject. |
| JWT expired hoặc chưa đến `nbf`. | Reject. |
| ID token được gửi như access token. | Reject token purpose. |
| Access token valid nhưng scope thiếu. | Deny operation, thường `403 insufficient_scope`. |
| Token hợp lệ nhưng owner/tenant sai. | Deny theo object authorization. |

**Lỗi signature không nên biến thành “cho phép để hệ thống luôn sẵn sàng”.** Tính sẵn sàng cần giải bằng cache trust keys đã xác minh, JWKS prefetch và circuit/rollout policy, không bằng việc bỏ kiểm mật mã.

## 30. Đầu vào xấu và giới hạn parser

Một JWT có thể được attacker gửi trực tiếp tới API. Vì vậy cần:

- **Giới hạn độ dài Authorization header/token** theo hợp đồng và gateway/RS.
- Reject quá nhiều dấu chấm, đoạn rỗng, Base64URL/JSON không hợp lệ.
- Giới hạn kích thước header/payload, JSON depth và số lượng keys.
- Không chấp nhận duplicate JSON member names khi parser/profile không xác định rõ hành vi, đặc biệt `alg`, `kid` và claims quan trọng.
- Không cho token điều khiển arbitrary URL fetch hoặc file access.
- Reject unsupported critical headers và token serializations.
- Không thử hàng trăm algorithms/keys cho mỗi request.
- Ghi nhận metrics theo category mà không log raw token.

**Attack surface không chỉ là RSA math**. Một verifier đúng chữ ký nhưng parser, key resolver hoặc issuer routing sai vẫn có thể bị khai thác.

## 31. Multi-issuer và multi-tenant: khóa không thể dùng chéo

Một Orders API có thể chấp nhận tokens từ hai AS được phép:

```text
Issuer A:
  https://id-a.example.test
  JWKS A
  Allowed alg A
  Audiences A

Issuer B:
  https://id-b.example.test
  JWKS B
  Allowed alg B
  Audiences B
```

**Cần tách trust config**:

- Issuer A không được dùng public key của B trừ khi có trust federation được thiết kế rõ.
- `kid=rsa-1` ở A không giống `kid=rsa-1` ở B.
- Cache keys phải bao gồm issuer/trust domain và key identifier.
- Claim `sub` phải được diễn giải trong namespace `iss`.
- Token của tenant A không được truy cập dữ liệu tenant B chỉ nhờ có `scope=orders.read`.
- Nếu API không biết chọn issuer nào, **không gửi raw token đến endpoint tùy ý do caller gợi ý**.

**Multi-tenant authorization là bước sau cryptographic verification**, nhưng phải được thiết kế cùng trust boundary; key hợp lệ của một issuer không biến mọi tenant claim thành quyền toàn cục.

## 32. Signature verification và RFC 7662 introspection

**Opaque token** không mang JWS signature để RS tự verify theo cấu trúc. RS có thể gọi AS qua **RFC 7662 Token Introspection**:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RS_INTROSPECTION_AUTH_PLACEHOLDER

token=OPAQUE_ACCESS_TOKEN_PLACEHOLDER&token_type_hint=access_token
```

AS kiểm token và trả metadata:

```json
{
  "active": true,
  "aud": "orders-api",
  "scope": "orders.read",
  "sub": "user-123",
  "exp": 1795410600
}
```

**RS không verify JWS signature của opaque string**; nó tin vào **AS introspection endpoint được xác thực qua TLS và caller authentication/authorization** theo hợp đồng. RS vẫn phải kiểm `active`, audience, scopes, token type và quyền tài nguyên.

Ngược lại, JWT access token có thể local verify signature nhưng **vẫn cần revoke enforcement** nếu token bị đánh cắp. Một JWT ký đúng có thể bị AS revoke hoặc grant hết hạn trong khi chữ ký toán học vẫn đúng.

## 33. Logging, audit và privacy khi xác minh chữ ký

Bản thân JWT access token là bearer credential; cả signature và claims có thể là dữ liệu nhạy cảm. Không ghi token nguyên bản vào logs chỉ để debug signature fail.

| Event | Nên ghi | Không nên ghi |
|---|---|---|
| `JWT_SIGNATURE_INVALID` | Issuer config ID, alg expected/observed dạng phân loại, correlation ID. | Raw JWT, toàn bộ payload hoặc signing input. |
| `JWT_UNKNOWN_KID` | Issuer ID, kid đã xử lý/giới hạn độ dài, JWKS cache state. | Header nguyên bản không sanitize. |
| `JWT_ALG_REJECTED` | Allowed/actual algorithm category, policy version. | Signing key/secret. |
| `JWT_ISSUER_DENIED` | Configured issuer reference, reason code. | PII/token claims đầy đủ. |
| `JWT_AUDIENCE_DENIED` | Expected audience, route, reason. | Raw access token. |
| `JWKS_REFRESH_FAILED` | Trusted endpoint ID, TLS/network reason, cache status. | Full URL query có credential. |
| `TOKEN_REVOKED` | Token/grant HMAC reference, issuer, time. | Token giá trị thô, private key. |

**Không log** HS256 secret, private signing key, refresh/access token, Authorization header hoặc nguyên ID token. Có thể dùng HMAC(token) với khóa audit riêng để tương quan mà không rò token; vẫn cần retention và quyền truy cập log chặt.

## 34. Threat modeling: các lớp tấn công chữ ký JWT

| Đường tấn công | Cơ chế lỗi | Biện pháp chính |
|---|---|---|
| **Decode-only** | Dùng payload chưa verified làm identity. | Bắt buộc verify cryptographic signature/MAC. |
| **`alg=none` downgrade** | Nhận unsigned token trong API yêu cầu signed. | Algorithm allowlist, reject none. |
| **RS256 → HS256 confusion** | Dùng public key như HMAC secret. | Bind key type/alg, tách HS/RS key paths. |
| **Attacker `jku`/`jwk`** | Tự ký rồi ép RS dùng key attacker. | Trusted JWKS only, ignore/restrict header key sources. |
| **`kid` path/SQL injection** | Header điều khiển file/db query không an toàn. | Safe lookup, bounds, parameterized query. |
| **Cross-issuer key confusion** | Dùng issuer B key để nhận issuer A claims. | Issuer-specific trust/key mapping. |
| **ECDSA DER/JOSE mismatch** | Tự xử lý signature encoding sai. | JOSE library, algorithm tests. |
| **Unknown critical header** | Bỏ qua mandatory extension. | Reject unsupported `crit`. |
| **Type confusion** | ID token được chấp nhận làm API access. | `typ`/token type + audience validation. |
| **Audience bypass** | JWT ký đúng nhưng dành API khác. | Expected `aud` validator. |
| **Expired-token acceptance** | Signature vẫn đúng sau hạn. | `exp`/`nbf`/time policy. |
| **JWT replay** | Bản sao Bearer token còn signature đúng. | TTL, storage, revocation, sender constraints. |
| **JWKS cache DoS** | Mỗi `kid` lạ gây refresh mạng. | Rate-limited JWKS refresh/negative caching. |
| **Signing key compromise** | Attacker ký được token hợp lệ. | Key incident response, trust removal, coordinated rotation. |

## 35. Ma trận kiểm thử Signature verification

Giả sử Orders API chỉ chấp nhận **JWT access token ký RS256** từ `https://id.example.test`, audience `orders-api`, route GET cần `orders.read`; issuer công bố trusted JWKS. Một số test mở rộng sang HS256, PS256, ES256 và EdDSA trong môi trường/profile riêng, không có nghĩa Orders API phải chấp nhận tất cả.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| SV01 | RS256 JWT ký đúng key, đúng issuer/aud/exp/scope. | Verify + authorization pass. |
| SV02 | Chỉ Base64URL decode payload nhưng chưa verify. | Không tạo authenticated principal. |
| SV03 | Sửa một byte của payload mà giữ signature. | Reject signature. |
| SV04 | Sửa protected header mà giữ signature. | Reject signature. |
| SV05 | Header `alg=none`, signature rỗng. | Reject. |
| SV06 | Header `alg=HS256` khi policy chỉ RS256. | Reject algorithm. |
| SV07 | Attacker tạo HS256 MAC bằng RSA public key bytes. | Reject algorithm/key confusion. |
| SV08 | RS256 token được verify bằng key không đúng. | Reject. |
| SV09 | Token ký bằng private key attacker, `jku` trỏ attacker JWKS. | Reject untrusted key source. |
| SV10 | Token nhúng `jwk` do attacker tạo. | Không tin embedded key để xác thực issuer. |
| SV11 | `kid` chứa `../` hoặc ký tự control. | Safe lookup/reject, không file traversal. |
| SV12 | `kid` có payload SQL/escape. | Không injection; safe query/validation. |
| SV13 | `kid` không tồn tại. | Rate-limited refresh nếu cần rồi reject. |
| SV14 | Unknown `kid` hàng nghìn giá trị mỗi giây. | Không gây unbounded JWKS fetch. |
| SV15 | Key K2 được rotate hợp lệ, JWKS cập nhật. | Token K2 verify sau trust refresh. |
| SV16 | Token K1 còn hạn khi K1 chỉ ngừng signing. | Verify nếu K1 vẫn trong trusted key set. |
| SV17 | K1 bị đánh dấu compromised và gỡ trust. | Token K1 bị reject tại RS đã cập nhật. |
| SV18 | Hai issuers có cùng `kid=rsa-1`. | Không cross-issuer key reuse. |
| SV19 | Token issuer B, chỉ issuer A được phép. | Reject issuer. |
| SV20 | Unverified `iss` là URL tới metadata attacker. | Không SSRF/key substitution. |
| SV21 | JWKS trả HTTP redirect sang host khác. | Không tự follow kèm trust/token; enforce policy. |
| SV22 | JWKS TLS cert/hostname không hợp lệ. | Reject key fetch; không bỏ verify. |
| SV23 | JWKS response quá lớn/too many keys. | Bounded parser/DoS protection. |
| SV24 | JWKS key `kty=oct` trong RS256-only issuer. | Reject key type mismatch. |
| SV25 | RSA public key quá ngắn theo policy. | Reject weak key. |
| SV26 | Token ES256 có JWS raw `R||S` hợp lệ ở profile ES256. | JOSE verifier pass, không nhầm DER. |
| SV27 | ES256 signature bị đưa vào RS256 verifier. | Reject algorithm. |
| SV28 | PS256 token được xử lý như RS256. | Reject mismatch. |
| SV29 | EdDSA token nhưng issuer/RS không hỗ trợ algorithm. | Reject, không fallback. |
| SV30 | `crit` chứa extension không hỗ trợ. | Reject. |
| SV31 | Unsupported `b64=false` được dùng trong JWT profile này. | Reject nếu profile không cho phép. |
| SV32 | Token có duplicate header `alg`. | Parser/profile reject hoặc xử lý theo chính sách strict, không ambiguous accept. |
| SV33 | JWT không đủ 3 đoạn hoặc thêm dấu chấm. | Reject malformed compact JWS. |
| SV34 | Invalid Base64URL ký tự/padding/schema. | Reject theo parser strict. |
| SV35 | JSON payload lặp `aud`/`iss` mâu thuẫn. | Reject ambiguous claims, không cho parser confusion. |
| SV36 | JWT ký đúng nhưng `iss` sai. | Reject. |
| SV37 | JWT ký đúng nhưng `aud=payments-api`. | Orders API reject. |
| SV38 | JWT ký đúng nhưng `exp` đã qua. | Reject. |
| SV39 | JWT ký đúng nhưng `nbf` ở tương lai. | Reject. |
| SV40 | NumericDate tính bằng milliseconds sai profile. | Reject/không chấp nhận nhầm lifetime. |
| SV41 | JWT ký đúng nhưng `scope=orders.read-all`, route cần `orders.read`. | Không substring match; reject. |
| SV42 | JWT scope đọc nhưng route cần approve. | Deny `403`. |
| SV43 | JWT đúng scope/aud nhưng order thuộc tenant khác. | Deny object-level authorization. |
| SV44 | OIDC ID token ký đúng, `aud=orders-web` gửi Orders API. | Reject token type/audience. |
| SV45 | OIDC ID token nonce mismatch trong RP. | Reject OIDC login. |
| SV46 | RFC 9068 access JWT thiếu/wrong `typ` theo policy. | Reject token type. |
| SV47 | JWT bị revoke nhưng chữ ký vẫn hợp lệ. | RS denylist/status từ chối theo policy. |
| SV48 | Bearer token bị sao chép và phát lại. | Signature vẫn đúng; kiểm replay protections/authorization khác. |
| SV49 | DPoP token không có proof đúng. | RS reject dù JWT signature hợp lệ. |
| SV50 | AS JWKS tạm không có mạng nhưng key tin cậy còn cached. | Verify theo cache/trust policy, không bỏ claims. |
| SV51 | JWKS mạng lỗi, không có key hợp lệ. | Fail closed, không chấp nhận JWT. |
| SV52 | Header JWT 10 MB hoặc JSON nesting bất thường. | Reject size/depth; không DoS parser. |
| SV53 | Resource Server chỉ cấu hình `issuer-uri`, thiếu audience check. | Integration test phát hiện. |
| SV54 | Spring Test `jwt()` giả lập principal, route pass. | Không coi là bằng chứng signature verification thật. |
| SV55 | Introspection `active=false` cho opaque token. | RS reject, không cố verify như JWS. |
| SV56 | JWT access token được gửi tới endpoint token/refresh grant như refresh token. | AS reject wrong token purpose. |
| SV57 | HS256 shared secret yếu/đoán được. | Secret-policy test phát hiện, không deploy. |
| SV58 | HS256 valid nhưng issuer không tin/RS không có đúng secret. | Reject, không trust any matching MAC. |
| SV59 | Private signing key lộ trong CI. | Incident response: rotate/trust removal và rà tokens. |
| SV60 | Log/debug in raw JWT hoặc private key. | Redaction/security test fail. |

### Thiết kế các tầng kiểm thử

- **Unit tests:** Base64URL/parser errors, allowed algorithm checks, exact `aud`/`iss`, clock skew, scope matching.
- **Cryptographic tests:** ký JWT thật bằng test private keys; đổi một byte header/payload/signature; wrong key/alg/curve, ECDSA JWS encoding.
- **JWKS integration tests:** trusted discovery, unknown `kid`, key overlap/rotation, TLS/malicious redirects, cache refresh/rate limiting.
- **Resource-server tests:** real `JwtDecoder` verify cryptographic signature, `typ`/claims, authorities, object authorization; test unauthorized/forbidden outcomes.
- **OIDC client tests:** ID token signature, issuer/audience/azp, nonce/at_hash/c_hash theo flow.
- **Security/resilience tests:** SSRF, alg confusion, key injection, replay, signing-key incident, JWKS outage và logs.
- **Opaque-token tests:** introspection caller authentication, `active`, audience/scope và revoke latency.

**Spring Security Test `jwt()` tạo principal giả để test route authorization; nó không chứng minh decoder đã xác minh chữ ký thật.** Để kiểm end-to-end phải dùng JWT ký thật bằng test issuer/JWKS đáng tin, không chỉ mock `JwtAuthenticationToken`.

## 36. Các tình huống học tập

### Tình huống A — JSON hiển thị ADMIN

Developer decode JWT, thấy `{"role":"ADMIN"}` và mở endpoint quản trị. Không có verification.

**Hỏi:** Vấn đề nằm ở đâu?

> Base64URL decoding không kiểm tính toàn vẹn hoặc nguồn phát. Attacker có thể tự tạo payload. Cần signed token verification với key/alg đã tin, rồi kiểm issuer, audience và quyền thật.

### Tình huống B — Chữ ký đúng nhưng token dùng nhầm API

Orders API nhận JWT ký RS256 hợp lệ, nhưng `aud=payments-api`.

**Hỏi:** Có nên cho qua vì AS chung?

> Không. Signature validity không thay audience. RS phải từ chối token không dành cho Orders API.

### Tình huống C — Header yêu cầu `HS256`

RS chỉ nên nhận RS256 và có public key RSA công khai. Attacker đưa token HS256 ký bằng bytes từ public key.

**Hỏi:** Vì sao không “linh hoạt” chọn verifier theo header?

> Có thể dẫn tới algorithm confusion: verifier dùng public key làm secret HMAC. Cần khóa **thuật toán và loại khóa** theo issuer policy.

### Tình huống D — `jku` trỏ tới attacker

Token được ký bởi private key attacker và có `jku` dẫn tới JWKS của attacker. Signature verification bằng key đó có thể trả true.

**Hỏi:** Có được chấp nhận không?

> Không. Key nằm ngoài trust anchor của issuer. Toán học chữ ký đúng không chứng minh token do AS tin cậy ký.

### Tình huống E — Key rotation làm nhiều token lỗi

AS đổi signing key K1 → K2. RS cache JWKS chưa có K2 và báo unknown `kid`.

**Hỏi:** Có được bỏ kiểm signature tạm thời?

> Không. Cần rotation rollout với JWKS overlap, controlled refresh và cache. Nếu chưa tìm được key tin cậy, từ chối token.

### Tình huống F — OIDC ID token được dùng để gọi API

RP nhận ID token JWT từ OP, signature verify thành công rồi gửi nó vào Orders API.

**Hỏi:** Có an toàn không?

> Không. ID token dành cho RP, không phải RS; audience/type/purpose khác. API cần access token đúng `aud` và `scope`.

### Tình huống G — Token cũ vẫn được ký đúng sau logout

Người dùng logout, refresh token đã revoke, nhưng access JWT chưa hết hạn.

**Hỏi:** Signature có tự fail không?

> Không. Signature verify trên bytes không thay đổi. Để chặn trước `exp`, RS cần denylist/grant status/introspection hoặc revocation policy khác.

### Tình huống H — ES256 được đưa qua JCA như DER

Developer đưa nguyên 64 bytes JWS ES256 vào `SHA256withECDSA` của JCA chờ DER signature và gặp lỗi.

**Hỏi:** Vì sao?

> JOSE ES256 dùng `R||S` cố định; nhiều JCA providers dùng ASN.1 DER. Dùng thư viện JOSE hoặc conversion được kiểm chứng thay vì tự xử lý thiếu chuẩn.

### Câu hỏi tự đánh giá

1. Signature verification khác Base64URL decoding ở đâu?
2. JWS Signing Input gồm chính xác những bytes nào?
3. Vì sao không tái serialize JSON header/payload khi verify chữ ký?
4. HS256 khác RS256 ở mô hình phân phối khóa và quyền ký như thế nào?
5. Thuật toán `alg` có được chọn hoàn toàn từ token header không?
6. Tại sao RS256/HS256 confusion có thể biến public key thành secret giả?
7. PS256 khác RS256 ở scheme và JCA configuration nào?
8. Vì sao chữ ký ES256 trong JWS không giống DER ECDSA signature?
9. `kid` có phải nguồn tin cậy để tải key từ URL tùy ý không?
10. Trust chain issuer → metadata/JWKS → key → signature cần kiểm những bước nào?
11. Với nhiều issuers cùng dùng `kid=rsa-1`, key resolver cần làm gì?
12. Vì sao unknown `kid` nên refresh có giới hạn rồi fail closed?
13. `crit` và `b64=false` ảnh hưởng generic JWS parser thế nào?
14. Signature đúng có làm `exp` hoặc `aud` được bỏ qua không?
15. JWT access token với `typ=at+jwt` khác ID token ở chỗ nào?
16. Vì sao JWT ký đúng vẫn có thể bị replay khi là Bearer token?
17. Key rotation có đồng nghĩa revoke mọi token cũ không?
18. Với opaque token, RS lấy trạng thái từ đâu thay vì JWS verification?
19. Spring Security chỉ có `issuer-uri` có tự đủ audience/scope/object policy không?
20. Những integration tests nào chứng minh cryptographic verification thật?

## 37. Ghi nhớ

- **Signature verification bảo đảm tính toàn vẹn và xác thực nguồn khóa ký**, không tự bảo đảm confidentiality, token lifetime, đúng audience hoặc quyền nghiệp vụ.
- **Base64URL decoding là đọc dữ liệu, không phải xác minh chữ ký.** Một JWT payload đọc được vẫn có thể giả mạo.
- **JWS Compact ký đúng encoded protected header + dấu chấm + encoded payload**; không JSON serialize lại trước verify.
- **Algorithm allowlist và key type binding là bắt buộc.** Không nhận `none` hoặc để token tự ép RS256 thành HS256.
- **HS256 dùng secret chung; RS256/PS256/ES256/EdDSA dùng asymmetric keys** theo những schemes/encodings khác nhau; không hoán đổi verifier.
- **`kid` chỉ chọn khóa trong trusted key set**, không phải quyền tải `jku`/`x5u`/`jwk` từ attacker.
- **Issuer là trust anchor**. JWKS, key rotation và multi-issuer lookup phải được cấu hình/giới hạn an toàn.
- **Signature pass vẫn phải kiểm `iss`, `aud`, `exp`, `nbf`, token type và policy**, rồi kiểm `scope`, tenant/owner, revoke state tại RS.
- **ID token dành cho RP; access token dành cho RS**. Cùng public key không khiến chúng thay thế nhau.
- **JWT tự chứa vẫn có chữ ký đúng sau logout hoặc khi bị sao chép**; revocation và sender constraints là các lớp bảo vệ riêng.
- **Opaque token dùng introspection/status, không dựa trên JWS signature của một chuỗi opaque**.
- **Ưu tiên JOSE/OAuth2 libraries và tests với JWT ký thật** hơn custom verifier cấp quyền từ claims.
- **Fail closed khi không có key đáng tin, chữ ký sai hoặc claims thiếu**; audit lý do theo reference mà không ghi raw token/secrets.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): compact serialization, signing input, protected header và verification.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS256, RS256, PS256, ES256, key/algorithm requirements.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWKS, `kty`, `kid`, key metadata.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims và token representation.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): encrypted/nested token khác signature verification.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): `b64=false` và critical headers.
- [RFC 8037 — CFRG Elliptic Curve OKP/EdDSA for JOSE](https://www.rfc-editor.org/rfc/rfc8037): Ed25519/Ed448 và JOSE key representation.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, explicit typing, issuer/audience và key validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `at+jwt`, `iss`, `aud`, `scope` và RS access token validation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, access/refresh token purposes.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): opaque/status/revoke khác local JWT signature verification.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): replay, token storage, refresh security và sender constraints.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): sender-bound tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token Validation, OIDC issuer/audience/nonce.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) và [Spring Security OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): JWT decoder, validation và OIDC client.
