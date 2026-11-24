# Hash, MAC và digital signature

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **cryptographic hash**, **Message Authentication Code (MAC)** và **digital signature**; phân biệt toàn vẹn, chứng thực nguồn gốc thông điệp, xác minh bằng khóa công khai và giới hạn của tính không thể phủ nhận.
- Mô tả **SHA-256**, các thuộc tính kháng tiền ảnh, tiền ảnh thứ hai, va chạm; không nhầm hash với encryption hay authentication.
- Hiểu **HMAC-SHA-256** dùng khóa bí mật chung và được xác minh thế nào; phân biệt nó với việc tự nối secret và message để hash.
- Phân biệt **HS256** (HMAC), **RS256**, **PS256**, **ES256** và các thuật toán bất đối xứng như EdDSA theo profile.
- Mô tả JWT/JWS signing input, việc bảo vệ chữ ký và vì sao **Base64URL encoding, hash payload hoặc chữ ký hợp lệ không tự cấp quyền API**.
- Nhận diện **alg=none, HS/RS algorithm confusion, key confusion, kid/jku misuse, JWT substitution** và rủi ro dùng chung secret ký cho nhiều Resource Server.
- Áp dụng chính sách khóa ký, JWKS/rotation, quản lý HMAC secret và các yếu tố chống replay.
- Sử dụng sơ đồ Mermaid, ví dụ HTTP/Java, negative tests và checklist an toàn cho hệ thống token.

## 1. Ba câu hỏi mật mã trong hệ thống token

Giả sử **Authorization Server (AS)** cấp access token để Dashboard gọi **Orders API**.

Một Resource Server nhận token từ mạng cần biết:

1. **Token có bị sửa không?** Đây là bài toán **integrity**.
2. **Token có xuất phát từ nguồn phát hành được tin cậy không?** Đây là **origin authentication**, theo khóa/issuer trust.
3. **Token có được dùng tại Orders API, ngay lúc này, để làm hành động cụ thể không?** Đây là **authorization**, vượt khỏi phạm vi của riêng mật mã.

Ba công cụ có ý nghĩa khác nhau:

| Công cụ | Có khóa bí mật? | Đầu ra | Bảo đảm chính |
| --- | --- | --- | --- |
| **Cryptographic hash** | Không. | Digest có độ dài cố định. | Dấu vân tay dữ liệu; integrity khi digest tham chiếu được lấy từ **nguồn đã tin cậy**. |
| **MAC/HMAC** | Có một **secret key chung**. | Authentication tag. | Integrity và origin authentication trong **nhóm các bên biết secret**. |
| **Digital signature** | **Private key để ký**, **public key để xác minh**. | Signature. | Integrity và nguồn ký theo khóa bất đối xứng/trust configuration. |

**Mật mã chỉ là một lớp kiểm tra.** Dù hash, MAC hoặc signature hợp lệ, RS vẫn cần kiểm issuer, token type, audience, expiration, scope và permission.

### Ví dụ sửa scope

Token ban đầu có payload:

~~~json
{
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read"
}
~~~

Attacker muốn đổi thành:

~~~json
{
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:approve"
}
~~~

Nếu API chỉ Base64URL-decode rồi đọc scope, dữ liệu bị sửa có thể được chấp nhận.

- Hash không khóa do client tự gửi không ngăn attacker tính lại digest.
- HMAC đúng khóa ngăn attacker không biết secret tạo tag hợp lệ cho payload đã sửa.
- Chữ ký số đúng private key ngăn attacker chỉ biết public key tạo signature hợp lệ.

**Tuy nhiên, access token thực sự được AS cấp scope orders:approve vẫn chưa tự cho phép duyệt mọi order**: RS phải kiểm tenant và business policy.

## 2. Cryptographic hash là gì?

Một hàm hash mật mã nhận byte sequence có độ dài tùy ý và trả một digest cố định.

Ví dụ **SHA-256**:

~~~text
message = UTF8("orders:read")
digest = SHA256(message)

Output length:
    256 bits = 32 bytes
    64 hexadecimal characters
~~~

Một digest SHA-256 có thể được encode ở dạng hex hoặc Base64URL, nhưng encoding không làm tăng mức bảo mật.

### Những thuộc tính quan trọng

| Thuộc tính | Diễn giải |
| --- | --- |
| **Deterministic** | Cùng input bytes tạo cùng digest. |
| **Preimage resistance** | Từ một digest cho trước, khó tìm một input tương ứng. |
| **Second-preimage resistance** | Với một input cho trước, khó tìm input thứ hai khác nhưng cùng digest. |
| **Collision resistance** | Khó tìm hai input khác nhau có cùng digest. |
| **Avalanche behavior** | Thay đổi nhỏ ở input thường đổi nhiều bit đầu ra; đây không tự là chứng minh security. |

**Hash cố định độ dài vẫn có collision theo nguyên lý pigeonhole.** Đối với SHA-256 lý tưởng, tấn công birthday tổng quát tìm collision cần khoảng **2^128** công việc, trong khi tìm preimage tổng quát khoảng **2^256**.

### Hash không phải encryption

~~~text
SHA256(message) -> digest không được thiết kế để giải mã

AES-GCM_encrypt(key, nonce, plaintext) -> ciphertext + auth tag
AES-GCM_decrypt(key, nonce, ciphertext, tag) -> plaintext hoặc fail
~~~

Hash không giúp khôi phục plaintext đã băm. Encryption có khóa giữ **confidentiality** và khi là AEAD như AES-GCM còn có **integrity/authenticity** theo khóa encryption. Đừng dùng SHA-256 để thay encryption cho dữ liệu cần giải mã.

### Hash không có khóa xác thực

Nếu client tự gửi:

~~~json
{
  "payload": "scope=orders:approve",
  "digest": "HASH_DO_CLIENT_TU_TINH"
}
~~~

thì client có thể thay cả payload lẫn digest. API chỉ kiểm hai trường khớp nhau **không chứng minh AS đã cấp quyền đó**.

Hash hữu ích khi digest chuẩn được **ký, MAC, truyền qua kênh đã tin cậy hoặc lấy từ kho metadata đáng tin**.

## 3. Byte-level signing và encoding

Hash/MAC/chữ ký số đều hoạt động trên **bytes**, không ký một ý nghĩa JSON trừ khi protocol định nghĩa canonicalization.

Ví dụ:

~~~json
{"sub":"user-42","scope":"orders:read"}
~~~

và:

~~~json
{
  "scope": "orders:read",
  "sub": "user-42"
}
~~~

Hai đoạn có thể cùng nội dung về mặt JSON, nhưng khác byte sequence do whitespace và thứ tự property.

### Quy tắc quan trọng

- **Không parse JWT rồi serialize JSON lại trước khi verify chữ ký.** Cần kiểm đúng JWS signing input.
- Nêu rõ UTF-8 và encoding được chuẩn/profile quy định.
- Với HMAC protocol tự thiết kế, xác định độ dài/trường/phân cách/version để ngăn ambiguity.
- Khi nhiều hệ thống ký/xác minh tài liệu, dùng **canonical serialization** theo chuẩn liên quan; không tự giả định JSON luôn có cách biểu diễn duy nhất.
- **Base64URL chỉ là encoding** để byte data đi qua URL/JSON thuận tiện, không mã hóa giữ bí mật và không chứng minh nguồn gốc.

## 4. Hash trong lưu trữ và tra cứu token

Hash có ích trong token storage, nhưng **token có entropy cao** khác **mật khẩu của người dùng**.

### 4.1 Opaque token ngẫu nhiên

AS có thể tạo opaque access token từ CSPRNG đủ mạnh, rồi chỉ lưu lookup digest:

~~~text
AS:
    T = CSPRNG(high-entropy opaque token)
    lookupKey = SHA256(T)
    database[lookupKey] = grant metadata, audience, status, expiry
    return T to authorized client

Introspection:
    receive presented token T
    lookupKey = SHA256(T)
    find record and verify status
~~~

Đây là mô hình khái niệm, chưa đủ mọi yêu cầu đồng thời, lưu trữ an toàn và truy vấn thực tế. Với **token đủ entropy và phát ngẫu nhiên**, hash lookup có thể giảm mức lộ raw token trong database.

### 4.2 Không hash mật khẩu bằng SHA-256 đơn thuần

Mật khẩu con người thường dễ đoán. SHA-256(password) không cung cấp công việc tính toán cố ý đủ tốn kém để chống offline dictionary attacks.

Với password, dùng **Argon2id** hoặc KDF/password hashing chuyên dụng theo platform/chính sách như scrypt/PBKDF2, salt duy nhất và tham số chi phí phù hợp.

| Loại giá trị | Cách tiếp cận |
| --- | --- |
| Opaque token CSPRNG entropy cao | Hash/HMAC lookup key có thể phù hợp. |
| Password người dùng | Password KDF với salt/cost parameters. |
| Client secret entropy thấp | Không mặc định raw SHA-256 đủ; cần thiết kế credential phù hợp. |
| Token cần khôi phục để gọi API | Hash không khôi phục được; dùng secure storage/encryption có xác thực nếu thật cần lưu raw token. |

### 4.3 Token fingerprints cho audit/logs

Một số hệ thống cần đối chiếu các lần token bị dùng lại. Có thể tạo **fingerprint không tiết lộ raw token** bằng HMAC với khóa riêng cho logging:

~~~text
fingerprint = HMAC_SHA256(loggingSecret, tokenBytes)
log: requestId, eventType, truncatedFingerprint
~~~

Fingerprint có thể vẫn là dữ liệu **liên kết hành vi người dùng**, cần giới hạn retention, quyền đọc và việc chia sẻ. Không dùng fingerprint làm Bearer credential. Không tái sử dụng HMAC secret ký JWT để tạo fingerprint.

**Không log raw access token, refresh token, ID token hay signing secret** dưới danh nghĩa “debug”.

## 5. MAC: Message Authentication Code

**MAC** nhận một message và một secret key, tạo authentication tag:

~~~text
tag = MAC(K, message)
valid = VerifyMAC(K, message, tag)
~~~

Nếu attacker không biết K, nó không thể dễ dàng tạo tag hợp lệ cho message đã bị sửa khi thuật toán và khóa được dùng đúng.

### MAC bảo vệ gì?

- Phát hiện sửa đổi message (**integrity**).
- Chứng minh bên tạo tag **biết shared secret K** (**origin authentication trong nhóm biết K**).
- Không phân biệt tuyệt đối bên nào trong nhóm biết K đã tạo tag, vì verifier cũng biết K và có thể sinh tag.

Điểm này khác chữ ký số: một RS có public key để verify signature **không có khả năng ký lại** nếu không có private key.

### MAC không mã hóa message

~~~text
message = {"sub":"user-42","scope":"orders:read"}
tag = MAC(secretKey, UTF8(message))
~~~

Ai có message vẫn có thể đọc sub/scope. Nếu cần **confidentiality**, dùng TLS, JWE hoặc AEAD/encryption phù hợp, không coi MAC là encryption.

## 6. HMAC-SHA-256 và công thức đúng

**HMAC**, được định nghĩa trong RFC 2104, là MAC dựa trên hash function. **HMAC-SHA256** sử dụng SHA-256.

Biểu diễn khái quát:

\[
\operatorname{HMAC}_K(m) =
H\big((K' \oplus opad)\,\Vert\,H((K'\oplus ipad)\,\Vert\,m)\big)
\]

Trong đó:

- **K** là khóa bí mật.
- **m** là message bytes.
- **H** là SHA-256 khi dùng HMAC-SHA256.
- **ipad/opad** là các hằng/padding theo chuẩn HMAC.
- K' được chuẩn hóa theo block size của H.
- \(\Vert\) là phép nối byte sequences.

**HMAC không phải phép SHA256(secret + message) tự chế**. Cấu trúc đơn giản đó dễ bị thiết kế sai, ambiguity hoặc length-extension attack theo điều kiện. Luôn dùng **thư viện HMAC chuẩn**, không tự cài công thức.

### Đầu ra HMAC-SHA256

HMAC-SHA256 thường có tag **256 bit**. Trong JWS HS256, tag được Base64URL-encode làm phần signature. Security thực tế còn phụ thuộc secret entropy, bảo vệ key, tần suất thử và việc verify đúng.

### Replay không được HMAC giải quyết

Một request webhook có:

~~~text
body = {"event":"order.approved","orderId":"123"}
timestamp = 2026-11-23T01:00:00Z
requestId = "evt-123"
tag = HMAC_SHA256(K, canonicalRequest)
~~~

Attacker có thể phát lại **y nguyên message, timestamp và tag** nếu recipient không kiểm freshness và replay. Nên kết hợp **timestamp window, nonce/requestId store và idempotency**. HMAC chống sửa nội dung, không tự chống replay.

## 7. HS256 của JWS là HMAC

Theo JSON Web Algorithms, **HS256 = HMAC using SHA-256**:

~~~text
AS:
    giữ secret K
    tạo HS256 JWS signature/tag bằng HMAC(K, signingInput)

Resource Server:
    cũng giữ secret K
    dùng HMAC(K, signingInput) để verify
~~~

**Bất kỳ verifier nào biết K đều có khả năng tạo HS256 JWT hợp lệ**. Đây là vấn đề về **trust boundary và secret distribution**, không có nghĩa HMAC-SHA256 tự thân là thuật toán yếu.

~~~mermaid
flowchart TD
    AS["Authorization Server giữ secret K"] --> O["Orders API cũng giữ K"]
    AS --> P["Payments API cũng giữ K"]
    AS --> R["Reports API cũng giữ K"]
    O -.->|"Nếu K bị lộ từ Orders, kẻ tấn công có thể forge token cho nơi cùng tin K"| P
~~~

Với nhiều RS, đối tác hoặc nhiều trust domains, chia sẻ signing secret ra mọi verifier làm tăng **blast radius**. Cần đánh giá sử dụng chữ ký bất đối xứng: issuer giữ private key, RS chỉ có public key.

### Quản lý khóa HS256

- Sinh secret từ **cryptographically secure random number generator**, đủ entropy theo profile/chính sách; không dùng password, tên công ty hoặc chuỗi dễ đoán.
- Lưu trong KMS/secret manager; không hardcode vào repository, image hoặc build artifact.
- Phân tách secret theo issuer, environment và token purpose nếu trust model đòi hỏi.
- Kiểm soát key retrieval, rotation, audit và quyền truy cập của mỗi RS.
- Không dùng secret ký JWT cho cả HMAC logging fingerprint hoặc webhook khác mục đích.
- Khi secret bị lộ, rotate/disable secret cũ và xem xét các JWT vẫn được RS chấp nhận.
- Không chọn JWT algorithm theo header một cách tùy tiện; HS256 chỉ được phép khi verifier **có đúng HMAC secret dành cho mục đích đó**.

## 8. Digital signature sử dụng hai loại khóa

**Chữ ký số bất đối xứng** phân tách:

- **Private key**: chỉ issuer/signing service giữ để tạo chữ ký.
- **Public key**: được phân phối qua trust configuration/JWKS để RS verify.

~~~text
signature = Sign(privateKey, messageBytes)
valid = Verify(publicKey, messageBytes, signature)
~~~

Với algorithm/key an toàn, public key **không cho phép tạo chữ ký hợp lệ**.

~~~mermaid
flowchart LR
    AS["Authorization Server giữ private signing key"] -->|"JWT đã ký"| C["OAuth Client"]
    C -->|"Bearer JWT"| RS["Orders Resource Server"]
    JWKS["Trusted JWKS / public verification key"] --> RS
    RS --> CHECK["Verify chữ ký và token claims"]
~~~

**Bên verify bằng public key không cần biết private key.** Đây là lợi thế quan trọng khi nhiều API cùng cần xác minh token nhưng chỉ AS có quyền phát hành.

### Non-repudiation có tuyệt đối không?

Chữ ký số có thể hỗ trợ bằng chứng rằng **khóa riêng đã được sử dụng để ký dữ liệu**, nhưng không tự chứng minh người cụ thể đã chủ ý ký hoặc tạo ra non-repudiation pháp lý tuyệt đối.

Cần thêm certificate/issuer trust, key custody, audit, timestamp, quy trình quản trị và đánh giá key compromise.

Trong JWT, mục đích chính là **integrity và origin authentication dựa vào issuer/key trust**. Nó không tự xác nhận hành động của End-User.

## 9. RS256, PS256, ES256 và EdDSA

Một số thuật toán JOSE thường gặp:

| JWS alg | Họ thuật toán | Điểm cần nhớ |
| --- | --- | --- |
| **HS256** | HMAC-SHA256. | **MAC đối xứng**, verifier biết secret có thể forge. |
| **RS256** | RSASSA-PKCS1-v1_5 với SHA-256. | Chữ ký RSA bất đối xứng; verify padding/algorithm strict. |
| **PS256** | RSASSA-PSS với SHA-256. | RSA-PSS khác RS256, tham số PSS tuân JWA profile. |
| **ES256** | ECDSA P-256 với SHA-256. | Signature trong JWS dùng fixed-width r||s, không tự nhầm DER. |
| **ES384** | ECDSA P-384 với SHA-384. | Profile và key/curve phải phù hợp. |
| **EdDSA** | Edwards-curve signature như Ed25519 khi profile hỗ trợ. | Thuật toán/curve/JWK support phải tương thích profile. |

### RS256 khác PS256

Hai thuật toán đều dùng RSA nhưng khác sơ đồ padding/chữ ký. Verifier không được âm thầm “thử mọi RSA algorithm” đến khi có cái pass. **Cho phép chính xác thuật toán được cấu hình và kiểm đúng profile**.

### ECDSA cần nonce/k an toàn

ECDSA đòi hỏi xử lý nonce/k theo thuật toán đúng; dùng lại hoặc tạo yếu có thể làm lộ private key. Dùng thư viện mật mã uy tín hoặc HSM, **không tự chọn random k**.

Ed25519 có thiết kế chữ ký riêng; đừng áp cách tính nonce ECDSA cho Ed25519.

### Chọn thuật toán theo kiến trúc

Cân nhắc:

- Thuật toán/curve được AS, RS, JOSE library và môi trường chạy hỗ trợ.
- Quy định bảo mật của tổ chức.
- Trust boundary: ai được phép ký, ai chỉ cần verify.
- Quản lý khóa: HSM/KMS, rotation, kid, JWKS cache.
- Token size/performance theo đo đạc, không phỏng đoán.
- Tương thích ecosystem và kiểm thử negative cases.

Không có thuật toán nào tự cứu hệ thống nếu **private key hoặc HMAC secret bị lộ**, hoặc RS bỏ qua issuer/audience.

## 10. So sánh thuộc tính bảo mật

| Thuộc tính | Hash không khóa | HMAC/MAC | Digital signature |
| --- | --- | --- | --- |
| **Integrity khi có expected digest/tag/signature đáng tin** | Có. | Có. | Có. |
| **Chứng thực bên biết shared secret** | Không. | Có. | Không theo cơ chế shared secret. |
| **Xác minh bằng public key** | Không. | Không. | Có. |
| **RS không thể mint token khi chỉ giữ verify material** | Không áp dụng. | Không nếu RS biết MAC secret. | Có nếu RS chỉ giữ public key. |
| **Confidentiality của payload** | Không. | Không. | Không. |
| **Chống phát lại token** | Không. | Không. | Không. |
| **Tự kiểm audience, scope, exp** | Không. | Chỉ bảo vệ claims, RS vẫn cần kiểm. | Chỉ bảo vệ claims, RS vẫn cần kiểm. |
| **Tự cấp quyền trên một bản ghi** | Không. | Không. | Không. |

**Chữ ký hợp lệ không phải kết luận authorization.** Một token đúng chữ ký nhưng sai audience, quá hạn hoặc bị thu hồi vẫn phải bị từ chối.

## 11. JWT/JWS ký những bytes nào?

**JWT** là một định dạng biểu diễn claims; **JWS** là cơ chế bảo vệ integrity/authenticity thường dùng cho signed JWT.

JWS Compact Serialization thông thường có **ba phần**:

~~~text
BASE64URL(UTF8(protectedHeaderJson))
.
BASE64URL(payloadBytes)
.
BASE64URL(signatureBytes)
~~~

Các phần được **Base64URL encode**, không tự được mã hóa giữ bí mật.

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "https://orders.example.test/api",
  "client_id": "dashboard-web",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-token-123"
}
~~~

NumericDate trong ví dụ là dữ liệu giả trong quá khứ; đây chưa phải token đã ký.

### Signing input

Với Compact JWS thông thường:

~~~text
signingInput =
    ASCII(
      BASE64URL(UTF8(protectedHeaderJson))
      + "."
      + BASE64URL(payloadBytes)
    )
~~~

Tùy thuật toán:

~~~text
HS256:
    tag = HMAC_SHA256(secret, signingInput)

RS256:
    signature = RSASSA_PKCS1_V1_5_SIGN(privateKey, signingInput, SHA256)

PS256:
    signature = RSA_PSS_SIGN(privateKey, signingInput, SHA256, JWA parameters)

ES256:
    signature = ECDSA_SIGN(privateP256Key, signingInput, SHA256, JOSE encoding)
~~~

Đây là **pseudocode**, không phải công thức tự triển khai trong controller. Thư viện JOSE xử lý signing input, encoding, padding, signature format và các lỗi mật mã.

**Không parse JSON rồi reserialize để kiểm chữ ký.** Một payload JSON có thể có cùng nghĩa nhưng bytes khác nhau. Cần verify đúng bytes JWS theo profile.

Những extension như unencoded payload theo RFC 7797 phải được bật/kiểm **chỉ khi profile cho phép**; không mặc định áp cho JWT access token.

## 12. Pipeline phát hành và xác minh token

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant K as KMS / HSM signing key
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant J as Trusted JWKS

    AS->>AS: Kiểm client, grant, audience, scope và policy
    AS->>AS: Tạo header và claims theo JWT profile
    AS->>K: Ký JWS signing input
    K-->>AS: Signature bytes
    AS-->>C: Signed JWT access token
    C->>RS: Bearer JWT qua HTTPS
    RS->>J: Lấy public key theo trusted issuer/kid
    J-->>RS: Verification JWK
    RS->>RS: Verify signature/alg/key
    RS->>RS: Kiểm issuer/audience/time/type/scope/permission
    RS-->>C: Cho phép hoặc từ chối
~~~

Nếu AS dùng KMS, việc private key không thể xuất ra ngoài là ưu điểm lớn, nhưng **KMS có thể không tự biết claims/scope nào hợp lệ**. AS phải kiểm issuance policy trước khi yêu cầu ký.

**Một signing service được phép ký payload bất kỳ vẫn có thể bị lạm dụng dù private key nằm an toàn trong HSM.**

## 13. Cryptographic validation khác authorization

Một access token ký hợp lệ có thể có:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "https://payments.example.test/api",
  "scope": "payments:read",
  "exp": 1730000900
}
~~~

Orders API phải từ chối vì aud không dành cho Orders.

| Nhóm kiểm tra | Điều kiện cần |
| --- | --- |
| **Mật mã** | Signature đúng, thuật toán allowlist, key type và key trust đúng. |
| **Issuer** | iss khớp trusted issuer của RS. |
| **Type/profile** | Là OAuth access token theo profile RS hỗ trợ. |
| **Audience** | aud khớp exact resource identifier của Orders. |
| **Time** | exp chưa qua, nbf/iat theo profile và clock-skew policy. |
| **Scope** | Scope được cấp chính xác cho endpoint/method. |
| **Principal** | Client/user/service identity đúng grant và context. |
| **State** | Chưa bị revoke/deny theo SLA nếu có cơ chế trạng thái. |
| **Proof** | DPoP/mTLS proof nếu token bị sender-constrained. |
| **Resource policy** | Quyền trên order, tenant, ownership và business state. |

~~~text
function allowOrdersAccess(jwt, request):
    verified = trustedJwtVerifier.verify(jwt, allowedAlgorithmsAndKeys)
    if not verified:
        DENY_401()

    requireIssuer(jwt.iss, expectedIssuer)
    requireAccessTokenProfile(jwt)
    requireAudience(jwt.aud, ordersAudience)
    requireValidTime(jwt.exp, jwt.nbf)
    requireNotRevokedWhenPolicyRequires(jwt)
    requireSenderProofIfApplicable(request, jwt)
    requireExactScope(jwt.scope, "orders:read")
    requirePermission(jwt.principal, request.order)
    return PROCESS_REQUEST
~~~

**Chữ ký hợp lệ là điều kiện cần, không đủ để authorization.**

## 14. Algorithm confusion và alg=none

Header JWT có **alg**, nhưng header đến từ token **chưa được xác minh**. Thiết kế sai:

~~~text
algorithm = untrustedJwtHeader.alg
verifyWithAnyAlgorithm(algorithm, configuredKey)
~~~

### HS256/RS256 confusion

Một lớp lỗi xảy ra khi verifier:

1. Được thiết kế chấp nhận **RS256**, có RSA public key.
2. Attacker biết public key, vốn không bí mật.
3. Attacker tạo header **alg=HS256**, dùng public-key bytes như HMAC secret.
4. Verifier cấu hình sai dùng cùng public-key bytes để verify HS256.
5. Một JWT giả có thể bị chấp nhận.

Thư viện hiện đại thường giúp ngăn nhóm lỗi này, nhưng điều kiện là **cấu hình đúng thuật toán và key type**.

### Các quy tắc phòng chống

- **Allowlist chính xác alg** theo issuer/profile, không tin alg trong header làm policy.
- **Ràng alg với key type**: HS256 chỉ dùng symmetric secret, RS/PS dùng RSA public key, ES dùng EC key/curve đúng.
- Không tự thử mọi thuật toán cho đến khi thấy một cái pass.
- Khi migration giữa thuật toán, quản lý chính sách khóa/issuer/alg rõ ràng.
- Không chấp nhận **alg=none** cho API yêu cầu access token đã được xác thực mật mã.
- Từ chối các JOSE critical headers/extension ngoài profile hỗ trợ.
- **Tách validator** theo token type để ngăn dùng ID token thay access token.

JOSE có unsecured JWT trong các tình huống đặc thù, nhưng **parse được token alg=none không có nghĩa API được phép chấp nhận**.

## 15. kid, JWKS và lựa chọn nguồn khóa

Header JWS có thể chứa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-key-2026-11"
}
~~~

**kid là identifier do token gửi**, chỉ nên dùng để tìm trong **trusted issuer-specific JWKS/key registry**. Nó không tự xác nhận khóa đáng tin.

### Trusted JWKS

RS cấu hình issuer:

~~~text
expectedIssuer:
    https://identity.example.test

trustedMetadata:
    issuer = https://identity.example.test
    jwks_uri = https://identity.example.test/.well-known/jwks.json
~~~

RS cần issuer binding, TLS/hostname verification, algorithm allowlist, key use/curve và cache policy. Không lấy JWKS URL từ query, client HTTP header hoặc claims không tin cậy.

### jku và embedded jwk tấn công trust boundary

Một attacker có thể tự đặt:

~~~json
{
  "alg": "RS256",
  "jku": "https://attacker.example.test/jwks.json",
  "kid": "attacker-key"
}
~~~

Nếu verifier tải khóa từ URL trên và tin nó, attacker có thể tạo JWT với private key riêng. **Chữ ký đúng với public key attacker không chứng minh AS đã phát token.**

Tương tự, cần policy rõ cho **jwk/x5u/x5c**: không tin tùy ý URL/certificate do token đề xuất.

### kid injection và multi-issuer

Không ghép kid vào filesystem path hoặc câu SQL chưa parameterize:

~~~text
readFile("/keys/" + jwt.header.kid)
lookupSQL("... WHERE kid = '" + jwt.header.kid + "'")
~~~

Cần giới hạn kid format/length, dùng trusted key map/JWKS đã parse, xử lý unknown kid/duplicate IDs và không fallback sang key khác issuer. **kid không unique toàn cầu**; hai issuer có thể đặt cùng kid.

## 16. Key rotation: bình thường khác khẩn cấp

### Rotate có kế hoạch

Giả sử issuer chuyển từ **K-old** sang **K-new**.

~~~text
K-new:
    AS dùng private key để ký token mới
    RS lấy public key từ trusted JWKS

K-old:
    có thể tiếp tục được tin để verify token cũ còn hạn
    chỉ khi K-old không bị compromise
~~~

Một rollout an toàn:

1. Sinh K-new trong KMS/HSM hoặc key store đáng tin.
2. Công bố public key K-new qua JWKS trước hoặc đồng thời bắt đầu ký, theo kế hoạch triển khai.
3. AS ký token mới bằng private key K-new, dùng kid tương ứng.
4. RS refresh trusted JWKS, kiểm issuer/key type/allowed algorithm.
5. Nếu K-old không bị lộ, giữ public key cũ đủ để verify các token hợp lệ chưa hết hạn.
6. Loại K-old theo TTL và kiểm mọi RS đã cập nhật.
7. Theo dõi unknown kid, signature failures, JWT issuer/type/audience mismatches.

### Khi private key bị compromise

Attacker có thể tự ký JWT giả. **Denylist vài jti đã biết không đủ**, vì attacker có thể tạo jti khác.

Cần emergency response:

- Ngừng ký bằng K-old, tạo key mới trong môi trường sạch.
- Loại **K-old khỏi trust set** của mọi RS/gateway, xử lý JWKS cache và RS offline.
- Kiểm lại các token hợp pháp cùng key có thể bị ảnh hưởng; chuẩn bị cấp lại token.
- Đo propagation SLO; không tuyên bố xong chỉ vì JWKS endpoint đã xóa key.
- Điều tra dấu hiệu forged tokens, hậu quả với tài nguyên và nguyên nhân lộ khóa.

### Nếu HS256 secret bị lộ

Mỗi verifier giữ cùng HMAC secret có khả năng ký token. Lộ secret ở một RS có thể ảnh hưởng mọi nơi cùng tin K. Phải rotate/disable secret cũ, kiểm distribution và đánh giá chuyển sang asymmetric signing cho nhiều RS.

## 17. JWS, JWE và TLS không hoán đổi nhau

| Công cụ | Bảo vệ chính | Không tự bảo vệ |
| --- | --- | --- |
| **JWS** | Integrity và authenticity theo chữ ký/MAC. | Confidentiality, expiry, replay, business authorization. |
| **JWE** | Confidentiality/integrity theo encryption profile. | Issuer trust và quyền API khi không có kiểm phù hợp. |
| **TLS** | Transport được xác thực giữa các endpoints. | Claims/token type/audience và token theft từ storage. |
| **AES-GCM at rest** | Authenticated encryption cho dữ liệu/token được lưu. | Thu hồi Bearer token đã bị copy. |
| **Hash lookup** | Giảm raw opaque token lưu ở database nếu đủ entropy. | Khôi phục token hoặc chứng thực issuer. |

JWT/JWS payload được Base64URL encode thường **đọc được**, nên không cho PII/secret không cần thiết vào JWT.

Một signed Bearer token vẫn phải đi qua HTTPS. TLS không chống được việc token lộ từ XSS, extension, logs hoặc malware; cần storage hygiene, hạn quyền và revocation policy.

## 18. MAC/chữ ký hợp lệ không ngăn token replay

Giả sử attacker có một JWT T:

~~~text
T.signature = valid
T.aud = orders-api
T.scope = orders:read
T.exp = future
~~~

Attacker có thể gửi **nguyên T** đến Orders API nếu T là Bearer và chưa bị vô hiệu hóa. Không cần phá SHA-256/RSA hay sửa payload.

Các biện pháp:

- Access token ngắn hạn, scope/audience hẹp, TLS và log redaction.
- Bảo vệ client token storage; không đưa bearer tokens vào URLs.
- Revocation/denylist/introspection nếu cần chặn trước exp.
- Phân quyền theo tenant/resource và anomaly monitoring.
- **DPoP hoặc mTLS-bound AT** nếu threat model cần proof of possession.

### DPoP proof là chữ ký khác chữ ký AS

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as Client giữ DPoP private key
    participant RS as Resource Server

    AS-->>C: Access token gắn DPoP key thumbprint
    C->>C: Ký proof theo method, URI, thời gian, jti
    C->>RS: Bearer/bound AT + DPoP proof theo profile
    RS->>RS: Verify token của AS và audience/scope
    RS->>RS: Verify proof signature, binding và replay guard
    RS-->>C: Cho phép hoặc từ chối
~~~

Token signature chứng minh AS đã ký claims. DPoP proof chứng minh bên gọi có private key ràng với token **trong request hiện tại**. Hai cơ chế không thay nhau.

## 19. ID token và access token: cùng khóa, khác mục đích

Trong OIDC, **ID token** dành cho Relying Party/client để xác minh authentication; trong OAuth, **access token** dành cho Resource Server.

~~~text
ID token:
    aud = dashboard-web
    dành cho RP login context

Access token:
    aud = https://orders.example.test/api
    scope = orders:read
    dành cho Orders API
~~~

Một OP/AS có thể dùng cùng signing key cho cả hai. Nếu RS chỉ kiểm chữ ký mà không kiểm **type/audience**, ID token có thể bị chấp nhận sai như AT (**cross-JWT confusion**).

Biện pháp:

1. Tách ID-token validator của RP và access-token validator của RS.
2. Kiểm issuer, aud, thời gian, type/profile và các claims bắt buộc **theo từng mục đích**.
3. JWT access token profile RFC 9068 có explicit typing như **at+jwt** theo quy tắc profile.
4. Không coi ID token chứa custom role là token có quyền gọi API.
5. Không chuyển AT của Payments sang Orders vì cùng issuer/sub.
6. Khi nhiều token types dùng chung key, áp rules loại trừ nhau để chống cross-JWT confusion theo RFC 8725.

Header **typ=at+jwt** không thay việc verify chữ ký, issuer và audience.

## 20. Crypto đúng nhưng issuance policy sai

Một AS có thể có bug:

~~~text
Client = reporting-bot
Requested scope = payments:approve
AS grant policy = sai, cấp nhầm toàn bộ requested scope
Signature = hoàn toàn hợp lệ
~~~

Chữ ký chỉ bảo vệ **bytes mà AS đã ký**; không bảo đảm claims được cấp đúng theo quy tắc nghiệp vụ.

Cần phòng ở nhiều lớp:

- AS kiểm **client–resource–scope allowlist**, consent, grant, audience.
- Signing service có quyền gọi hạn chế, audit và bảo vệ private key.
- RS kiểm issuer, audience, type, exp, scope, client/principal và quyền trên tài nguyên/tenant.
- Monitoring bất thường khi cấp quyền nhạy cảm.
- Khi cấp sai, chặn issuance mới, revoke token/grant liên quan và đo RS enforcement.
- Kiểm thử negative cases về over-privilege/cross-resource token forwarding.

**Một MAC/chữ ký đúng không thể thay policy authorization đúng.**

## 21. Java: SHA-256 và HMAC-SHA256 đúng API

Java có **MessageDigest** cho SHA-256 và **Mac** cho HMAC. Mã sau minh họa sử dụng JCA, không tự hiện thực HMAC.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HashAndHmacDemo {

    public static byte[] sha256(byte[] message) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return md.digest(message);
    }

    public static byte[] hmacSha256(
            byte[] key,
            byte[] message) throws Exception {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(message);
    }

    public static boolean verifyHmacSha256(
            byte[] key,
            byte[] message,
            byte[] suppliedTag) throws Exception {

        byte[] expectedTag = hmacSha256(key, message);
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    public static void main(String[] args) throws Exception {
        byte[] message =
                "orders:read".getBytes(StandardCharsets.UTF_8);

        // Demo: credential lấy từ nguồn bí mật được kiểm soát.
        // Không hardcode khóa trong mã nguồn.
        String encoded = System.getenv("EXAMPLE_HMAC_KEY_B64");

        if (encoded == null) {
            throw new IllegalStateException("Missing demo HMAC key");
        }

        byte[] key = Base64.getDecoder().decode(encoded);

        byte[] digest = sha256(message);
        byte[] tag = hmacSha256(key, message);

        String digestUrl = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);

        System.out.println("SHA-256 digest: " + digestUrl);
        System.out.println(
                "HMAC verification: "
                + verifyHmacSha256(key, message, tag)
        );

        // Không log key hoặc tag của credential thật.
        java.util.Arrays.fill(key, (byte) 0);
    }
}
~~~

### Nhận xét bảo mật

1. **MessageDigest** chỉ tính digest, không có secret key. Nó không tự xác thực issuer.
2. **Mac** dùng HMAC-SHA256 với key bí mật. Đảm bảo key đủ entropy, được lấy từ secret manager hoặc cơ chế quản lý khóa đáng tin.
3. **StandardCharsets.UTF_8** bảo đảm bytes đồng nhất; đừng phụ thuộc default charset.
4. **MessageDigest.isEqual** nên được dùng thay cách tự so sánh ngây thơ theo từng byte rồi trả về ngay khi gặp khác biệt. Dù vậy, ứng dụng còn cần xử lý độ dài tag/profile đúng.
5. Ví dụ chỉ trả tag HMAC, **không mã hóa message**.
6. Mã tự xóa byte[] chỉ giảm thời gian sống của một bản key, không bảo đảm secret biến mất khỏi mọi bản sao JVM/OS; nên ưu tiên KMS hoặc secret manager có boundary phù hợp.
7. Biến môi trường cũng có rủi ro bị lộ qua process dump/config; secret injection phải theo security policy.
8. Nếu dùng HMAC để ký JWT, **không tự ghép JWS và verify trong controller**. Nên dùng thư viện JOSE/JWT có kiểm tra header, alg, issuer và claims.

### Không dùng hash như mật khẩu verifier cho token entropy thấp

Với opaque token do CSPRNG sinh đủ mạnh, hash lookup có thể hợp lý. Với password, API phải dùng password KDF như Argon2id, không chỉ SHA-256. Với client secret không đủ entropy hoặc đã lộ, hashing không thể thay credential rotation.

## 22. Java: ký và xác minh RSA-PSS

**RSASSA-PSS** là chữ ký bất đối xứng; Java JCA cung cấp **Signature**. Ví dụ dưới đây sinh key **chỉ trong bộ nhớ để học**, ký một message và verify bằng public key.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;

public final class RsaPssDemo {

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");

        generator.initialize(3072, new SecureRandom());
        KeyPair pair = generator.generateKeyPair();

        byte[] message =
                "example-signed-message".getBytes(
                        StandardCharsets.UTF_8);

        // Tham số phù hợp ý tưởng PS256 theo JOSE:
        // SHA-256, MGF1(SHA-256), salt length 32 bytes.
        PSSParameterSpec pss = new PSSParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA256,
                32,
                1
        );

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(pss);
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(pss);
        verifier.initVerify(pair.getPublic());
        verifier.update(message);

        boolean valid = verifier.verify(signature);

        if (!valid) {
            throw new SecurityException("Invalid signature");
        }

        System.out.println("Signature verified: " + valid);
    }
}
~~~

### Vì sao đây chưa phải code tạo PS256 JWT?

- **Message** ở ví dụ là chuỗi tự định nghĩa, chưa phải **JWS signing input**.
- Chưa tạo protected header, payload, Base64URL compact serialization, kid hoặc JWKS.
- Chưa có issuer/audience/exp/scope và access-token profile.
- Sinh private key mỗi lần chạy **không phù hợp production**; signing key phải có lifecycle, security boundary, backup/rotation và audit đúng.
- RSA-PSS có những tham số bắt buộc theo JWA; ở trên chỉ minh họa đúng nhóm tham số SHA-256/MGF1-SHA256/saltLen 32 cho PS256. Dùng thư viện JOSE kiểm protocol, không tự đoán.
- Provider/JDK có thể có yêu cầu API khác nhau về init/setParameter; luôn kiểm thử trên runtime thực tế.

### ES256 không phải RSA-PSS

ES256 dùng ECDSA P-256. JWS representation của ECDSA signature là dạng fixed-width **R || S**, trong khi một số API JCA dùng ASN.1 DER cho chữ ký ECDSA.

**Không copy trực tiếp ECDSA DER signature vào compact JWS** mà không chuyển đúng định dạng theo JWA. Tốt hơn là dùng thư viện JOSE có hỗ trợ thuật toán được chọn thay vì tự triển khai chuyển đổi.

### Chữ ký số khác TLS client authentication

Chữ ký của AS trên JWT không tự chứng minh client đang kết nối có private key hay certificate liên quan. Với DPoP/mTLS-bound tokens, RS phải kiểm thêm proof/certificate của HTTP request theo token binding.

## 23. Spring Security: JWT decoder với issuer/audience/algorithm policy

Ví dụ cấu hình Resource Server cho một issuer và **RS256**. Đây là minh họa về nơi gắn validator, cần điều chỉnh theo Spring Security version và profile đang triển khai.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtValidationConfig {

    private static final String ISSUER =
            "https://identity.example.test";

    private static final String JWKS_URI =
            "https://identity.example.test/.well-known/jwks.json";

    private static final String AUDIENCE =
            "https://orders.example.test/api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> withIssuer =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> withAudience = jwt -> {
            List<String> aud = jwt.getAudience();

            if (aud != null && aud.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Invalid access token audience",
                            null
                    )
            );
        };

        OAuth2TokenValidator<Jwt> withType = jwt -> {
            String typ = jwt.getHeaders().get("typ") instanceof String
                    ? (String) jwt.getHeaders().get("typ")
                    : null;

            // RFC 9068 explicit typing theo profile.
            if ("at+jwt".equals(typ)
                    || "application/at+jwt".equals(typ)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Wrong JWT token type",
                            null
                    )
            );
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        withIssuer,
                        withAudience,
                        withType
                )
        );

        return decoder;
    }
}
~~~

### Những giới hạn của ví dụ

- **Không phải một cấu hình production hoàn chỉnh**: cần cấu hình SecurityFilterChain, routes/methods, authorities/scopes và business permission.
- **Issuer/JWKS URI** là giá trị tin cậy từ cấu hình, không lấy từ JWT header jku hoặc user request.
- **RS256** là allowlist minh họa. Với PS256/ES256/EdDSA phải dùng API thư viện hỗ trợ đúng profile/algorithms và key type.
- **audience contains** phù hợp một số profiles; nếu RS yêu cầu **single audience**, phải từ chối multi-aud ngoài policy.
- **typ** có thể được JOSE library/decoder diễn giải hoặc xử lý nội bộ khác nhau tùy phiên bản Spring; cần kiểm supported API, behavior thật và profile RFC 9068, không giả định dòng kiểm string ở ví dụ đủ cho mọi môi trường.
- Các yêu cầu khác của **JWT AT profile RFC 9068** còn cần được kiểm; typ alone không đủ. Phải phân biệt client_credentials và user grant theo subject/client/policy.
- **exp, nbf, issuer validators** được gắn theo thư viện, nhưng cần xác nhận actual behavior và allowed clock skew/version.
- Quyền **orders:read** và tenant/ownership phải được kiểm ở RS; signing key không nói gì về business permission.
- Với token bị revoke trước exp, cần state lookup/denylist/introspection theo thiết kế; signature validation offline không tự biết revoke.
- Không bật fallback decoder cho alg=none, HS256 hoặc issuer khác khi RS256 validation thất bại.

### Tại sao không dựa hoàn toàn vào JWT header?

Header typ/alg/kid là **dữ liệu nằm trong token cần được kiểm mật mã**. Thư viện được cấu hình với issuer/keys/algorithms tin cậy phải xử lý header theo policy, không để token tự quyết định trust anchor.

### So sánh HMAC và RSA verifier trong Java

- **HMAC**: bên verify có secret dùng để tạo MAC; không cấp secret bừa bãi cho mọi service.
- **RSA/ECDSA/EdDSA**: bên verify có public key; chỉ signing service có private key.
- **JWT signing**: tạo signature cho JWS signing input, không phải chỉ ký một chuỗi user role tự định nghĩa.
- **JWT authorization**: sau verify còn kiểm issuer, audience, type, exp, scope và permission.

**Cấu hình thư viện đúng thường quan trọng hơn việc tự viết thêm một hàm RSA.verify() trong controller.**

## 24. Những nhầm lẫn mật mã dẫn đến lỗ hổng token

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| **SHA-256(payload) được coi là chữ ký** | Attacker có thể tính digest cho payload mới. | Dùng JWS HMAC hoặc chữ ký số với key tin cậy. |
| **Base64URL là mã hóa** | Encoding không bảo vệ confidentiality hay integrity. | JWS cho integrity; JWE/TLS/AEAD cho confidentiality theo đúng lớp. |
| **Hash token entropy thấp** | Dễ offline brute-force bằng dictionary. | Token CSPRNG entropy cao; password dùng KDF với salt/cost. |
| **SHA256(secret + message) là HMAC** | Cấu trúc tự chế có thể lỗi/length-extension/ambiguity. | Dùng HMAC chuẩn qua thư viện. |
| **RS có HS256 secret vẫn không thể ký** | Verifier HMAC giữ secret có thể tự sinh tag. | Phân tách trust, cân nhắc asymmetric signatures. |
| **RS256 và PS256 là một** | RSA signature schemes khác padding/parameters. | Allowlist và verify đúng algorithm. |
| **ES256 signature DER luôn là JWS signature** | JOSE dùng dạng r||s cố định. | Dùng JOSE library xử lý chuyển đổi. |
| **Chỉ đọc JWT claims không verify** | Payload có thể tự sửa. | Verify JOSE signature/alg/key trước khi tin. |
| **Dùng alg header làm policy** | Header trước verify do attacker điều khiển. | Allowlist alg theo issuer/profile. |
| **Chấp nhận alg=none** | Không có chứng thực mật mã cho JWT yêu cầu signed. | Từ chối theo access-token profile. |
| **Lấy public key từ jku bất kỳ** | Attacker tự cung cấp khóa để verify token tự ký. | Trusted issuer-specific JWKS. |
| **Tin kid là nguồn gốc khóa** | kid chỉ là hint/ID, có thể trùng giữa issuer. | Ràng issuer, key type, use và alg. |
| **JWT signature đúng nghĩa API được phép** | Token có thể sai aud/scope/time/type/tenant. | Cryptographic + semantic + business validation. |
| **Dùng ID token như access token** | ID token dành cho RP; audience/mục đích khác. | RS chỉ nhận AT đúng profile/aud. |
| **Một AS ký mọi thứ nên dùng một validator** | Dễ cross-JWT confusion. | Validators riêng theo token purpose. |
| **Chữ ký bảo vệ khỏi replay** | Attacker có thể trình nguyên Bearer token. | TTL, audience, TLS, sender-constraining và revocation. |
| **Rotate key là RS ngừng tin key cũ ngay** | JWKS key có thể được cache. | Đo propagation, emergency trust removal khi compromise. |
| **Denylist jti đã biết giải quyết signing key leak** | Attacker tạo JWT giả với jti mới. | Loại trust với private key bị xâm phạm. |
| **HMAC compare bằng string == / so byte sớm** | Có thể tạo timing/encoding ambiguity. | Kiểm length/profile và constant-time compare của thư viện. |
| **JWS giữ bí mật sub/email** | Payload thường có thể decode. | Hạn chế claims, dùng JWE/other confidentiality controls khi cần. |
| **Client secret trong JWT payload vẫn an toàn vì token ký** | Signature không mã hóa secret. | Không cho credential vào token payload. |
| **KMS bảo vệ khóa nên AS không thể phát sai quyền** | KMS có thể ký payload do AS bị compromise yêu cầu. | Issuance policy, ACL, approval và monitoring. |

### Một lỗi đặc biệt: hash để tạo “signed JWT” tự chế

Sai:

~~~text
header.payload.SHA256(header + "." + payload)
~~~

Không có secret hoặc private key, attacker có thể tạo header/payload mới rồi tính lại hash. Không dùng dạng này làm token authentication.

### Một lỗi đặc biệt: so sánh HMAC tag bằng chuỗi văn bản

Tag là **bytes**. Nếu bên tạo dùng Base64URL nhưng verifier giải mã Base64 thường, hoặc có padding/normalization khác profile, có thể lỗi logic hoặc chấp nhận biểu diễn không chuẩn.

Nên:

1. Parse token/tag strict theo encoding.
2. Kiểm độ dài tag và thuật toán mong đợi.
3. Tính expected tag bằng thư viện HMAC chuẩn.
4. Dùng primitive so sánh phù hợp nhằm giảm timing leaks.
5. Fail closed với malformed encoding hoặc tag sai.

Không tự viết vòng lặp trả false ở byte đầu tiên khác rồi coi là constant time.

## 25. Tình huống tổng hợp trong hệ thống OAuth

### Case A — Orders API và Payments API cùng verify JWT

**Bối cảnh:**

~~~text
AS:
    phát AT cho Orders và Payments bằng private RSA key

Orders:
    giữ public key
    aud = orders-api

Payments:
    giữ public key
    aud = payments-api
~~~

Attacker đánh cắp AT có aud=Orders rồi gửi sang Payments.

**Kết quả đúng:** Payments có thể verify chữ ký thành công nhưng **phải từ chối** vì aud sai. Việc dùng RSA không thay audience restriction.

**Bài học:** chữ ký chứng minh AS phát claims; RS phải xét intended recipient và quyền API.

### Case B — HS256 secret dùng chung giữa ba service

AS, Orders và Payments cùng giữ HMAC secret K. Orders bị compromise và K xuất hiện trong log memory dump.

**Rủi ro:** attacker có K và có thể tạo tag HMAC cho token mới, không chỉ đọc token cũ. Tác động có thể lan sang Payments nếu cùng tin K.

**Containment:**

1. Disable/rotate K theo incident playbook.
2. Phân phối secret mới an toàn, đo trạng thái các RS đã ngừng tin K cũ.
3. Kiểm JWT giả được dùng, scope/audience và dữ liệu bị tác động.
4. Xem xét tách trust domains hoặc chuyển sang asymmetric signing để RS chỉ có public verification keys.
5. Khắc phục nguồn lộ K và tăng controls về memory/log/secret retrieval.

**Không khẳng định đã xử lý xong** chỉ vì đổi secret ở AS mà các RS vẫn dùng secret cũ trong cache/config.

### Case C — Token giả có alg=HS256 trong một RS kỳ vọng RS256

Attacker biết public RSA key của issuer và tạo JWT HS256 dùng key bytes đó như HMAC secret.

**Kết quả đúng:** Verifier đã được cấu hình RS256 và RSA public key **từ chối alg=HS256 ngay theo algorithm policy**. Không chuyển sang HMAC verifier.

**Negative test:** header alg=HS256 với signature HMAC đúng theo public-key bytes vẫn không được RS chấp nhận.

### Case D — Signing key bị lộ nhưng JWT cũ chưa hết hạn

Một backup chứa signing private key K-old bị công khai. AS đã rotate sang K-new nhưng RS vẫn cache K-old trong JWKS.

**Rủi ro:** attacker ký JWT giả với K-old. Các RS còn tin K-old có thể nhận token giả, kể cả khi AS không phát token đó.

**Containment:** emergency remove K-old trust ở các RS, kiểm cache/edge/replicas, đánh giá token hợp pháp cùng key bị ảnh hưởng, đo SLO và audit bất thường.

### Case E — Claims được ký hợp lệ nhưng quyền sai

AS cấp nhầm scope payments:approve cho reporting-bot vì một policy bug. JWT được ký đúng PS256.

**Kết quả đúng về kiến trúc:**

- AS sửa allowlist để không phát token mới sai.
- Revoke token/grant bị ảnh hưởng theo policy.
- Payments API kiểm **client/principal permission**, không chỉ scope/signature.
- Điều tra hành động đã thực hiện trước containment.

**Chữ ký số không sửa sai policy**.

### Case F — DPoP access token bị sao chép

Attacker sao chép một access token được ràng với public key DPoP nhưng không sở hữu private key tương ứng.

**Kết quả mong đợi:** RS xác minh token của AS nhưng **từ chối request không có DPoP proof hợp lệ** hoặc proof không khớp key/method/URI/time/replay constraints.

Nếu client runtime bị chiếm, attacker có thể vẫn yêu cầu client hợp pháp ký proof; cần kết hợp bảo vệ client, scope hạn chế và monitoring.

## 26. Negative tests cho hash, HMAC và digital signature

Các test sau dùng **test keys và tokens giả trong môi trường được phép**, không cần truy cập signing secret production.

| Test | Đầu vào/tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **SHA-256 deterministic** | Cùng bytes đầu vào. | Cùng digest. |
| **Hash khác bytes** | Thay một byte input. | Digest khác trong ca kiểm cụ thể. |
| **Hash-only giả chữ ký** | Attacker sửa payload và tự tính lại SHA-256. | RS từ chối vì không có MAC/signature hợp lệ. |
| **Hash vs encryption** | Cố decode digest để lấy plaintext. | Không tồn tại decrypt tương ứng. |
| **Mật khẩu SHA-256 thuần** | Password storage chỉ SHA256(password). | Security review từ chối; dùng password KDF. |
| **Opaque token yếu** | Token là chuỗi dễ đoán. | Phát hiện thiếu entropy; yêu cầu CSPRNG. |
| **HMAC đúng secret** | Message và tag hợp lệ. | Verify thành công. |
| **HMAC sai secret** | Cùng message, key khác. | Verify fail. |
| **HMAC message bị sửa** | Thay scope, giữ tag cũ. | Verify fail. |
| **HMAC tag bị sửa** | Flip bit trong tag. | Verify fail. |
| **HMAC tag bị cắt ngắn** | Tag ngắn hơn profile cho phép. | Fail strict policy. |
| **HMAC encoding mơ hồ** | Base64URL malformed/extra bytes. | Parser/verifier từ chối. |
| **Timing-sensitive compare** | So sánh tag bằng code return-early. | Test/review phát hiện và sửa theo primitive an toàn. |
| **HMAC secret dễ đoán** | Secret là password nhỏ. | Phát hiện khóa yếu, không triển khai. |
| **HMAC secret lộ ở RS** | Attacker có secret chung. | Incident response rotate và đánh giá forging scope. |
| **RSA signature hợp lệ** | Đúng key/message/alg. | Verify thành công. |
| **RSA payload sửa** | Thay bytes sau khi ký. | Verify fail. |
| **RSA signature giả** | Ký bằng private key của attacker. | RS từ chối theo trusted public key. |
| **Public key issuer khác** | Token ký bởi issuer B gửi RS tin issuer A. | Từ chối. |
| **RS256 token ở PS256-only RS** | Header/alg RS256. | Từ chối theo allowlist. |
| **PS256 tham số sai** | PSS salt/hash/MGF parameters lệch. | Verify fail. |
| **ECDSA signature sai encoding** | JWS signature bị đưa dưới dạng DER không đúng profile. | Từ chối. |
| **ECDSA wrong curve** | EC key/curve ngoài allowed profile. | Từ chối. |
| **alg=none** | JWT không chữ ký. | RS từ chối. |
| **HS/RS confusion** | HS256 tag dùng RSA public key bytes. | RS256 verifier từ chối. |
| **Unknown alg** | Header đề xuất thuật toán không hỗ trợ. | Từ chối, không fallback. |
| **Unknown kid** | kid không tồn tại trong trusted JWKS. | Từ chối/refresh theo policy an toàn. |
| **kid thuộc issuer khác** | Hai issuer dùng cùng key ID. | Không dùng key sai issuer. |
| **kid injection** | Path traversal/SQL fragment trong kid. | Không đọc file hoặc chạy query nguy hiểm. |
| **Untrusted jku** | Token trỏ JWKS attacker. | RS không fetch/tin URL này. |
| **Embedded jwk attacker** | Token mang public key tự khai. | Không coi là issuer trust anchor. |
| **Key use sai** | JWK không dành cho signing/alg phù hợp. | Từ chối theo profile. |
| **JWKS cache key compromised** | K-old đã bị loại nhưng RS vẫn cache. | Phát hiện/chặn, không báo containment sớm. |
| **JWT payload đúng nhưng chữ ký sai** | Claims hợp lệ, signature invalid. | Từ chối. |
| **JWT signature đúng nhưng iss sai** | Issuer khác trust config. | Từ chối. |
| **JWT signature đúng nhưng aud sai** | Payments AT gửi Orders. | Từ chối. |
| **JWT signature đúng nhưng exp qua** | Token hết hạn. | Từ chối. |
| **JWT signature đúng nhưng nbf tương lai** | Token chưa có hiệu lực. | Từ chối. |
| **JWT đúng nhưng scope thiếu** | AT chỉ read gọi approve. | Từ chối authorization. |
| **ID token làm AT** | ID token đúng chữ ký đưa tới RS. | Từ chối type/audience. |
| **Wrong typ** | JWT không mang profile được RS chấp nhận. | Từ chối. |
| **Token bị revoke** | JWT còn hạn nhưng jti/grant bị revoked theo policy. | RS chặn theo SLA. |
| **Bearer replay** | Gửi lại nguyên token còn hạn. | Cho thấy signature alone không chống replay; áp chính sách sender/replay tương ứng. |
| **DPoP proof không có** | AT ràng DPoP nhưng request thiếu proof. | Từ chối. |
| **DPoP key khác** | Proof ký bằng key không khớp token binding. | Từ chối. |
| **DPoP replay** | Reuse proof jti/time theo chính sách. | Từ chối. |
| **JWE parse sai** | JWE bị coi là JWS signed AT. | Từ chối hoặc xử lý đúng profile. |
| **Token lộ qua log** | Logging ghi raw Authorization header. | Test phát hiện leakage, redaction bắt buộc. |
| **Signing key leak** | Token giả ký K-old sau rotation. | Tất cả RS đã rút trust K-old phải từ chối. |
| **AS overgrant** | JWT ký hợp lệ nhưng scope vượt policy. | Kiểm issuer/AS issuance và RS permission; không chỉ signature. |
| **Cross-tenant** | AT đúng chữ ký/scope nhưng tài nguyên tenant khác. | RS từ chối. |

### Ma trận năm phép kiểm bắt buộc

~~~text
1. Payload sửa + chữ ký cũ -> DENY cryptographic verification.
2. alg HS256 trong RS256-only verifier -> DENY algorithm policy.
3. Signature đúng nhưng aud sai -> DENY recipient validation.
4. Signature đúng nhưng scope/permission thiếu -> DENY authorization.
5. Bearer token bị copy -> đánh giá replay risk, sender binding và revocation.
~~~

## 27. Checklist thiết kế và triển khai

1. **Mục đích:** Đã phân biệt hash, MAC và digital signature trong kiến trúc?
2. **Hash:** Có dùng SHA-256 hoặc primitive được policy chấp nhận, không coi hash là authentication?
3. **Password:** Không lưu password bằng SHA-256 thuần; dùng password KDF đúng chuẩn?
4. **Opaque token:** Token được sinh bằng CSPRNG đủ entropy; lookup digest/HMAC được thiết kế an toàn?
5. **Hash logs:** Không log raw tokens; fingerprint nếu cần có privacy/retention policy?
6. **MAC:** Có dùng HMAC chuẩn thay vì SHA256(secret+message)?
7. **HMAC keys:** Secret đủ mạnh, không hardcode, được quản lý bằng secret manager/KMS?
8. **Key separation:** Khóa JWT, webhook và logging fingerprint không bị dùng chéo mục đích?
9. **HS256 trust:** Chỉ các bên thực sự được phép có signing power mới nhận secret?
10. **Asymmetric:** RS chỉ có public key; private key được giữ tại signing authority?
11. **Algorithm:** Có allowlist alg rõ ràng theo issuer/profile, không tự tin header?
12. **Key type:** HMAC secret không bị dùng như RSA verification key và ngược lại?
13. **Unsigned:** alg=none không được chấp nhận ở OAuth API cần signed tokens?
14. **JWS signing input:** Dùng thư viện JOSE đúng bytes, không reserialize JSON để verify?
15. **Key lookup:** kid chỉ tra trusted issuer-specific JWKS; unknown/duplicate kid xử lý an toàn?
16. **Remote key:** Không fetch jku/x5u do token tự chỉ định khi không có trust contract?
17. **Issuer:** JWT được ràng với issuer tin cậy, không trộn keys giữa nhiều AS?
18. **Token purpose:** ID token, access token, logout token và client assertions có validator riêng?
19. **Audience:** RS kiểm exact resource identifier, không chỉ kiểm chữ ký?
20. **Time:** exp/nbf/iat được kiểm theo profile, có clock skew hợp lý?
21. **Scope/permission:** RS kiểm scope endpoint và resource/tenant policy?
22. **Revocation:** Với JWT offline, có TTL/denylist/version/introspection theo threat model?
23. **Replay:** AT ngắn hạn, TLS, không lộ token; DPoP/mTLS khi cần sender proof?
24. **JWE:** Nếu cần bảo mật claims, có encryption profile đúng; không coi JWS là mã hóa?
25. **Key rotation:** Có kế hoạch prepublish, JWKS cache, old key retire và negative tests?
26. **Key compromise:** Có emergency playbook loại bỏ key khỏi trusted RS và đo propagation?
27. **ECDSA/PS256:** Library xử lý curve, encoding và PSS parameters theo JOSE?
28. **Constant-time:** HMAC verification/tag comparison dùng primitive phù hợp, không tự viết so sánh dễ rò thời gian?
29. **Authorization:** Không coi chữ ký hợp lệ là quyền làm mọi hành động?
30. **Monitoring:** Theo dõi alg mismatch, unknown kid, bad signatures, wrong audience, replay, key retrieval và cache lag?
31. **Incident response:** Có thể rotate/revoke và xác minh enforcement khi secret/private key bị lộ?
32. **Negative tests:** Có bộ test tampering, alg confusion, kid/jku, signature errors, wrong token type/aud và replay?

## Kết luận

**Hash, MAC và digital signature là ba công cụ mật mã khác nhau**, không thể thay thế tùy ý:

- **Cryptographic hash**, chẳng hạn SHA-256, tạo digest không khóa để biểu diễn dấu vân tay dữ liệu; **không tự chứng thực issuer hay người gửi**.
- **MAC/HMAC**, chẳng hạn HMAC-SHA256 hay **HS256 trong JWS**, bảo vệ integrity và origin authentication giữa các bên biết **cùng secret**; bất kỳ verifier giữ secret cũng có năng lực tạo tag hợp lệ.
- **Digital signature**, chẳng hạn **RS256, PS256, ES256 hoặc EdDSA theo profile**, cho phép issuer giữ **private signing key** còn Resource Server chỉ cần **public verification key**, giúp phân tách quyền phát hành và xác minh.

Khi áp dụng cho JWT/OAuth, **chữ ký/MAC hợp lệ chỉ là điểm bắt đầu của validation**. Resource Server còn phải kiểm **issuer, audience, token type/profile, expiration, scope, principal, trạng thái thu hồi, sender proof khi áp dụng và permission trên tài nguyên**. Không có primitive nào tự giải quyết token theft/replay hay policy cấp quyền sai.

Đầu tư vào **thuật toán chuẩn, thư viện JOSE đáng tin, key management, JWT profile isolation, kiểm thử âm tính và revocation/incident response** mới tạo nên một hệ thống token có ranh giới tin cậy vững chắc.

### Tài liệu tham khảo

- [FIPS 180-4 — Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final)
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104)
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA algorithms](https://www.rfc-editor.org/rfc/rfc4231)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797)
- [RFC 8037 — CFRG Elliptic Curve EdDSA for JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [NIST SP 800-57 Part 1 — Key Management Guidance](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)





