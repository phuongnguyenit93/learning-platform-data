# Symmetric và asymmetric key

Trong hệ thống OAuth 2.0/OIDC, **Authorization Server (AS)** phát access token cho nhiều **Resource Server (RS)** như `orders-api`, `payments-api` và `reports-api`. Để bảo đảm token không bị sửa và được phát bởi issuer đáng tin, nhiều hệ thống dùng **chữ ký JWS**. Với **symmetric key**, các bên dùng một khóa bí mật chung; với **asymmetric key**, AS giữ private signing key, còn các RS dùng public verifying key.

Khác biệt này ảnh hưởng trực tiếp đến **ranh giới tin cậy**: nếu dùng `HS256` chung cho AS và ba RS, bên nào giữ shared secret cũng có khả năng tạo chữ ký hợp lệ. Nếu AS ký bằng RSA/ECDSA/EdDSA, RS có thể xác minh bằng public key mà **không có khả năng ký token giả chỉ với public key**. Tuy nhiên, chữ ký hợp lệ **không tự cấp quyền**: RS vẫn phải kiểm `iss`, `aud`, `exp`, `scope`, loại token, principal/tenant và quyền trên tài nguyên.

Bài thuộc chương **Cryptography** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: nắm mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access/refresh token; phát hành, kiểm claims/scope/audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại trong OAuth 2.0/OpenID Connect.

> **Câu cần nhớ:** “Private key ký, public key xác minh” thuộc **chữ ký bất đối xứng**. “Public key mã hóa, private key giải mã” mô tả một cách dùng **mã hóa khóa công khai**. **Ký** và **mã hóa** không tương đương. JWT được ký **không mặc nhiên được mã hóa**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt khóa đối xứng, cặp khóa public/private, MAC, chữ ký số, mã hóa đối xứng và key agreement.
2. Giải thích sự khác nhau giữa `HS256`, `RS256`, `PS256`, `ES256` và `EdDSA`.
3. Phân biệt **JWS** (integrity/source authentication theo trust model) với **JWE** (confidentiality), hiểu tại sao Base64URL payload của JWS không bí mật.
4. Vẽ mô hình AS signer và nhiều RS verifiers, chỉ ra nguy cơ khi chia sẻ HMAC secret rộng khắp.
5. Đọc JOSE `alg`, `kid`, `typ`, JWK và JWKS, và biết tại sao `kid` không phải trust anchor.
6. Thiết kế key generation, storage, distribution, rotation, retirement và incident response.
7. Liên hệ signing keys với OAuth 2.0/OIDC: ID/access token, refresh/opaque token, `private_key_jwt`, `client_secret_jwt`, DPoP và mTLS.
8. Cấu hình JWT validation trong Spring Security và sử dụng Java JCA minh họa HMAC/RSA.
9. Chống lỗi `alg=none`, algorithm confusion, attacker JWKS/key injection, token substitution, sai issuer/audience và token replay.
10. Xây dựng bộ kiểm thử tích cực/tiêu cực cho phát hành token, xác minh, rotation, key compromise và phân quyền.

## 2. Hai mô hình khóa cơ bản

### 2.1. Symmetric key — một secret được chia sẻ

Với **HMAC**, bên phát và bên kiểm dùng **cùng key `K`**:

~~~text
                 Shared secret K
                 /             \
        Authorization Server   Resource Server
            HMAC(K,M)             HMAC(K,M)
               |                     |
         Signature/MAC          Compare the MAC
~~~

- AS biết `K` để ký/MAC token.
- RS biết `K` để tính lại và kiểm.
- **Mọi bên biết `K` có thể tạo MAC hợp lệ**. Do đó không tách tuyệt đối quyền ký khỏi quyền xác minh.
- Khóa phải có entropy đủ mạnh và chỉ phân phối qua kênh/quy trình bảo mật.
- Nếu một RS bị chiếm quyền làm lộ `K` dùng chung, attacker có thể ký token giả theo khóa đó.

Trong mã hóa đối xứng (ví dụ AES-GCM), cùng một secret phù hợp được dùng để encrypt/decrypt. **Không nên dùng cùng key material cho HMAC và encryption** trừ khi protocol cụ thể thiết kế key derivation và domain separation an toàn.

### 2.2. Asymmetric key — public và private

~~~text
Authorization Server                     Resource Server
   PRIVATE signing key                      PUBLIC verifying key
          |                                         |
      Sign(M)  -------- signed token ---------> Verify(M,S)
          |                                         |
      Can sign                              Cannot sign from public key
~~~

- **Private key** phải được bảo mật, chỉ issuer/signer có quyền ký.
- **Public key** có thể được công bố qua JWKS tin cậy và phân phối tới nhiều verifiers.
- RS chỉ giữ public key **không thể tự tạo chữ ký hợp lệ** nếu thuật toán/khóa an toàn.
- RS cần chứng minh public key thật sự thuộc **trusted issuer**, không tin key do token hoặc attacker gửi.

Một cặp khóa dùng cho **encryption/key agreement** có ngữ nghĩa khác cặp khóa dùng cho chữ ký. Không tự sử dụng một key pair cho mọi mục đích khi scheme/key usage policy không cho phép.

### 2.3. So sánh theo vận hành

| Tiêu chí | Symmetric key | Asymmetric key |
|---|---|---|
| Khóa phải bảo mật | Shared secret tại signer và verifiers. | Private signing key tại signer; public key không bí mật. |
| Ký/MAC token | HMAC `HS256`. | RSA `RS256`/`PS256`, ECDSA `ES256`, EdDSA. |
| Mã hóa | AES-GCM, ChaCha20-Poly1305. | RSA-OAEP/key agreement kết hợp symmetric encryption. |
| RS có thể tạo chữ ký giả nếu bị chiếm? | Có, nếu lấy được secret ký dùng chung. | Không nếu chỉ có public verification key. |
| Phân phối verifier key | Phải giữ secret khi cấp cho verifiers. | Public key qua trusted JWKS/configuration. |
| Rotation | Đồng bộ secret tới các bên nắm secret. | AS thay private key; RS cập nhật public JWKS. |
| Chi phí | MAC thường nhanh và gọn. | Ký/verify có chi phí thuật toán tùy loại khóa. |
| Sự cố | Lộ một shared secret ảnh hưởng mọi bên sử dụng nó. | Lộ public key không cho phép ký; lộ private key vẫn nghiêm trọng. |

**Không phải asymmetric luôn an toàn hơn trong mọi hoàn cảnh.** Quản lý private key yếu, trusting arbitrary JWKS hoặc cấu hình sai `alg` có thể phá hoàn toàn mô hình.

## 3. Bốn mục tiêu mật mã thường bị nhầm

### 3.1. Confidentiality — bí mật nội dung

Encryption bảo vệ nội dung khỏi bên **không có key giải mã**. Ví dụ AES-GCM bảo vệ dữ liệu được mã hóa bằng secret key, JWE bảo vệ token payload ở tầng đối tượng. TLS bảo vệ **đường truyền**, nhưng khi token đi ra khỏi kênh TLS, bản sao token vẫn có thể bị lộ ở log/storage.

### 3.2. Integrity — phát hiện sửa đổi

MAC hoặc chữ ký phát hiện thay đổi dữ liệu đã được bảo vệ. JWT JWS compact thông thường có:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

**Header/payload trong JWS không được mã hóa**. Người thấy chuỗi JWT thường đọc được `sub`, `scope`, `aud` sau khi Base64URL-decode, dù không thể sửa payload mà vẫn giữ chữ ký hợp lệ.

### 3.3. Source authentication — tin đúng signer

HMAC hợp lệ chứng minh **bên biết shared secret** đã tạo MAC, không nhất thiết phân biệt AS/RS nếu họ cùng giữ khóa. Chữ ký số chứng minh **private key tương ứng với public key đáng tin** đã ký message, nhưng trust binding tới `iss`/AS vẫn phải được xác minh.

### 3.4. Authorization và replay là hai lớp riêng

Token `active=true` hoặc chữ ký đúng **không tự chứng minh** user đang hiện diện hay có quyền tenant hiện tại. Bearer token bị đánh cắp có thể bị replay trước expiry; cần TTL, audience/scope tối thiểu, HTTPS, secure storage, DPoP/mTLS sender constraints, revocation/state và object-level authorization.

### 3.5. “Không thể chối bỏ” cần ngữ cảnh

Chữ ký bất đối xứng có thể tách signer và verifier, nhưng “non-repudiation” theo pháp lý còn phụ thuộc key custody, chứng thư, audit, thời gian và quy trình. **JWT do AS ký không phải chữ ký tay của user có `sub` trong payload**.

## 4. Primitive: HMAC, AEAD, RSA, EC và EdDSA

### 4.1. HMAC khác hash trần

~~~text
SHA256(message)             -> digest không có secret
HMAC_SHA256(key, message)   -> keyed message authentication code
~~~

**SHA-256(payload + secret)** tự chế không thay thế HMAC chuẩn. Dùng crypto library, secret đủ entropy và key usage riêng.

### 4.2. Mã hóa đối xứng: AEAD

**AES-GCM** hoặc **ChaCha20-Poly1305** cung cấp authenticated encryption:

~~~text
AEAD_Encrypt(K, nonce, plaintext, AAD)
    -> ciphertext + authentication tag

AEAD_Decrypt(K, nonce, ciphertext, AAD, tag)
    -> plaintext OR authentication failure
~~~

- Với AES-GCM, **không tái sử dụng nonce dưới cùng key**, nếu không có thể phá confidentiality/integrity.
- AAD được **xác thực nhưng không mã hóa**.
- Chọn nonce/tag/key length theo library và tiêu chuẩn; không tự thay đổi tham số ngẫu hứng.
- AEAD xác thực ciphertext theo encryption key, **không tự chứng minh một user cụ thể đã cấp quyền**.

### 4.3. Họ chữ ký số

| JOSE algorithm | Primitive | Công dụng và lưu ý |
|---|---|---|
| `HS256` | HMAC-SHA-256 | MAC đối xứng, verifier có thể tạo MAC. |
| `RS256` | RSASSA-PKCS1-v1_5 + SHA-256 | Chữ ký RSA theo JWS, **không phải mã hóa RSA**. |
| `PS256` | RSASSA-PSS + SHA-256 | Chữ ký RSA-PSS theo JWA parameters. |
| `ES256` | ECDSA P-256 + SHA-256 | Chữ ký EC; JOSE dùng raw `R || S` encoding. |
| `EdDSA` | EdDSA theo profile, thường Ed25519 | Chữ ký Edwards-curve; cần provider/library support. |
| `A256GCM` | AES-GCM | **JWE content encryption**, không phải JWS signature. |
| `RSA-OAEP-256` | RSA-OAEP key management | Dùng trong JWE, **không phải ký JWT**. |
| `ECDH-ES` | ECDH key agreement | Dùng để derive key cho JWE, không phải ECDSA. |

### 4.4. Key agreement không đồng nghĩa xác minh signer

ECDH/ECDH-ES dùng key agreement/KDF để derive key khi có public/private key materials phù hợp. Nó không thay ECDSA/EdDSA signing. Nếu không xác thực nguồn public key của peer, key agreement **không tự đảm bảo danh tính của peer**.

## 5. JOSE: JWS, JWE, JWK, JWKS

### 5.1. JWS compact ba phần

~~~text
BASE64URL(protected-header) .
BASE64URL(payload) .
BASE64URL(signature)
~~~

Protected header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "as-signing-2026-11"
}
~~~

- `alg` là thuật toán **được token khai báo**, phải đối chiếu với policy đã cấu hình.
- `typ` có thể phân biệt token purpose theo profile, ví dụ `at+jwt` cho RFC 9068.
- `kid` giúp tìm key trong tập key tin cậy; **không tự là chứng cứ issuer/key đúng**.
- Header chưa được xác minh là **untrusted input**.

### 5.2. JWE compact năm phần

~~~text
protected-header .
encrypted-key .
initialization-vector .
ciphertext .
authentication-tag
~~~

Ví dụ JWE header:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "payments-encryption-2026-11"
}
~~~

`alg` xác định key management, `enc` xác định content encryption. **JWE không mặc định có chữ ký nguồn**. Nếu yêu cầu cả integrity/authentication của issuer và confidentiality, thiết kế nested JWT (ký rồi mã hóa) hoặc profile JOSE tương ứng; phải **xác minh cả lớp ngoài lẫn lớp trong** theo policy.

### 5.3. JWK public key

Public JWK RSA minh họa về cấu trúc:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "as-signing-2026-11",
  "alg": "RS256",
  "n": "PLACEHOLDER_BASE64URL_RSA_MODULUS",
  "e": "AQAB"
}
~~~

`n` là **placeholder, không phải modulus hợp lệ**. Public JWKS **không chứa** private JWK fields như RSA `d`, `p`, `q`; không bao giờ xuất private key ra metadata công khai.

Public JWK EC:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "kid": "as-ec-2026-11",
  "use": "sig",
  "alg": "ES256",
  "x": "PLACEHOLDER_X",
  "y": "PLACEHOLDER_Y"
}
~~~

Với Ed25519, JWK `kty=OKP`, `crv=Ed25519` và public coordinate `x`; private `d` là bí mật.

### 5.4. JWKS chứa nhiều public keys

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-old",
      "alg": "RS256",
      "e": "AQAB",
      "n": "PLACEHOLDER_OLD_PUBLIC_MODULUS"
    },
    {
      "kty": "RSA",
      "kid": "signing-new",
      "alg": "RS256",
      "e": "AQAB",
      "n": "PLACEHOLDER_NEW_PUBLIC_MODULUS"
    }
  ]
}
~~~

Khi xoay vòng, AS có thể công bố **old + new public keys** trong giai đoạn chuyển tiếp. Không coi `kid` là URL, file path hoặc quyền tải một public key tùy ý từ JWT header.

### 5.5. Key selection phải dựa trên trusted issuer

~~~text
trustedIssuerConfig
    -> trusted JWKS URI or pinned verifying keys

untrusted JWT header.kid
    -> look up matching key ONLY in trusted key set

then validate:
    signature + allowed alg/key type/use
    issuer + audience + expiry/time + token purpose
    scope + principal type + tenant/resource authorization
~~~

Các header `jku`/`x5u`/`jwk` có thể chứa URL/khóa do attacker tự khai. **Không tự fetch hoặc tin chúng từ bearer token** nếu không có protocol và trust policy được thẩm định. `kid` cũng không được đưa vào đường dẫn file để đọc key trên ổ đĩa.

## 6. AS và nhiều RS: hậu quả phân phối signing keys

### 6.1. HS256 shared-secret blast radius

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant O as Orders API
    participant P as Payments API
    AS->>O: Provision shared HMAC secret K via secure config
    AS->>P: Provision same HMAC secret K via secure config
    AS->>AS: Sign JWT using HMAC K
    AS-->>O: JWT HS256
    O->>O: Verify HMAC using K
    Note over O,P: Compromise of K in any RS can enable forgery
~~~

Sơ đồ giải thích việc **phân phối secret qua secret manager/kênh bảo mật**, không gửi key trực tiếp như token response. Một secret dùng chung cho nhiều RS làm tăng hậu quả khi chỉ một RS bị xâm nhập. Có thể chia key theo resource/trust domain nhưng vẫn cần quản trị key/rotation chặt.

### 6.2. Asymmetric signing tách private signer khỏi public verifier

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS
    participant O as Orders API
    participant P as Payments API
    AS->>AS: Sign JWT with private signing key
    AS->>JWKS: Publish corresponding public verification key
    O->>JWKS: Retrieve issuer public JWKS
    P->>JWKS: Retrieve issuer public JWKS
    AS-->>O: Signed access JWT for orders-api
    O->>O: Verify signature, iss, aud, exp, scope
    AS-->>P: Signed access JWT for payments-api
    P->>P: Verify signature, iss, aud, exp, scope
~~~

**Cùng public key không có nghĩa token hợp lệ tại mọi RS**: `payments-api` phải từ chối JWT `aud=orders-api` dù chữ ký được xác minh bằng cùng key AS.

### 6.3. Bốn nhóm private keys không được nhầm

| Khóa | Chủ thể nắm | Công dụng |
|---|---|---|
| **AS private signing key** | Issuer/AS, HSM/KMS khi phù hợp | Ký access/ID JWTs theo issuer profile. |
| **OAuth client private key** | Confidential client | `private_key_jwt` client authentication hoặc cơ chế đã đăng ký. |
| **DPoP private key** | Client/token holder | Ký proof ràng buộc token với key. |
| **mTLS client private key** | Client hoặc workload identity | Chứng minh bên bắt tay TLS, có thể certificate-bind access token. |

**Client key không tự có quyền ký token như AS.** Việc client chứng minh identity và việc AS cấp scope/claims phải được kiểm như hai bước riêng.

## 7. HS256 ký JWT như thế nào?

### 7.1. Signing input là bytes cố định

~~~text
H = BASE64URL(UTF8(serialized-protected-header))
P = BASE64URL(UTF8(serialized-payload))

SigningInput = ASCII(H + "." + P)

S = HMAC_SHA256(K, SigningInput)

JWS = H + "." + P + "." + BASE64URL(S)
~~~

Verifier dùng **chính xác signing input từ token**, không JSON serialize lại để kiểm. Token strings có thể khác dù biểu diễn JSON cùng nghĩa vì whitespace/order khác nhau.

### 7.2. HMAC secret phải có entropy cao

`HS256` không thể biến password yếu thành key mạnh. Nên sinh **ít nhất 256-bit secret entropy** phù hợp bằng CSPRNG, lưu tại secret manager và chỉ cấp cho trust domain thích hợp. Một secret như `"myjwtsecret"` có nguy cơ bị thử đoán offline nếu attacker có JWS signing input/signature.

**Không nhúng HMAC secret vào ứng dụng mobile, public JavaScript, mã nguồn, log hoặc image container**. Kẻ tải được secret có thể tạo MAC hợp lệ.

### 7.3. HMAC hợp lệ vẫn chưa đủ

RS cần kiểm `iss`, `aud`, `exp`/`nbf`, `typ`/token purpose, `scope`, principal type, tenant và object-level policy. Chữ ký bảo vệ nội dung claims nhưng không tự chứng minh các claims có **nghĩa phù hợp ở endpoint hiện tại**.

### 7.4. Khi nào HS256 là lựa chọn có cơ sở?

Phù hợp hơn khi signer/verifier thuộc **cùng trust domain chặt**, ít bên giữ secret, rotation được kiểm soát và không cần tách quyền ký khỏi quyền verify. Khi AS có nhiều RS hoặc đối tác ngoài tổ chức, chữ ký bất đối xứng thường cải thiện ranh giới bằng cách **không phát signing secret cho RS**.

## 8. Bất đối xứng: RSA, RSA-PSS, ECDSA, EdDSA

### 8.1. RSA RS256 khác RSA PS256

- `RS256`: RSA PKCS#1 v1.5 signature với SHA-256 theo JWA.
- `PS256`: RSA-PSS signature với SHA-256 và tham số chuẩn JOSE.
- Dù cùng key RSA có thể được hỗ trợ cho nhiều signature schemes, **validator phải kiểm đúng thuật toán theo hợp đồng**, không chỉ thấy “RSA” là chấp nhận.

**Java `Cipher` không dùng để verify RSA JWS signatures**; signing/verify phải qua `Signature` API hoặc JOSE library.

### 8.2. ECDSA ES256 và vấn đề encoding

`ES256` dùng ECDSA P-256 + SHA-256. JOSE biểu diễn chữ ký **raw fixed-length R || S**, trong khi Java JCA `Signature` thường dùng **ASN.1 DER ECDSA signature**. Tránh tự chuyển đổi giữa DER/raw khi chưa nắm rõ; dùng JOSE library đã kiểm thử.

### 8.3. EdDSA/Ed25519 cần provider support

Ed25519 thuộc họ EdDSA; key nhỏ và có profile ký/xác minh riêng. Cần AS/RS JOSE/JCA support, trusted public JWK `kty=OKP`/`crv=Ed25519` và compliance requirements phù hợp. **Không tự đổi `alg` sang EdDSA khi verifier chưa hỗ trợ**.

### 8.4. Kích thước key và thời hạn sử dụng

Không dùng RSA 1024-bit cho JWT signing hiện đại; tham chiếu chính sách tối thiểu **RSA 2048-bit trở lên**, EC P-256/Ed25519 theo security strength tương ứng. Các thuật toán không so theo số bit bằng cách lấy 256-bit EC = 256-bit RSA. Lựa chọn theo chuẩn tổ chức và khả năng crypto agility.

### 8.5. Chữ ký đúng với key attacker vẫn vô giá trị

Attacker có thể tự tạo RSA pair và ký một JWT chứa `sub=admin`. Phép verify toán học đúng khi dùng public key attacker **không biến JWT thành đáng tin**. RS chỉ nhận public verification key đã được gắn với **trusted issuer** và đúng token profile/allowed `alg`.

## 9. Xác minh JWT: đúng key không đồng nghĩa chấp nhận token

Resource Server không nên xây dựng “JWT verifier” bằng cách **Base64-decode payload** rồi đọc `sub`/`role`. Phải xác minh chữ ký và mọi ràng buộc ngữ nghĩa.

### 9.1. Các lớp kiểm bắt buộc theo profile

1. **Chọn đúng trust configuration:** API xác định trước issuer(s) tin cậy và kiểu token được phép.
2. **Parse có giới hạn:** token có định dạng hợp lệ, không vượt size/depth; từ chối format/JWE/JWS không mong muốn.
3. **Algorithm allowlist:** chỉ nhận `alg` mà issuer/resource đã cấu hình và có key type tương ứng; không nhận `none` nếu profile không cho phép (access token thực tế phải có bảo vệ thích hợp).
4. **Trusted key source:** chọn verification key từ key set gắn với issuer, không từ header URL tùy ý.
5. **Cryptographic verification:** kiểm chữ ký/MAC trên đúng JWS signing input.
6. **Issuer:** `iss` khớp chính xác một issuer đã tin.
7. **Audience:** `aud` chứa đúng API đích; không chỉ “token đến từ AS nên hợp lệ”.
8. **Thời gian:** `exp`, `nbf`, `iat` và lifetime/clock-skew constraints theo profile.
9. **Purpose:** access JWT vs OIDC ID token vs client assertion vs DPoP proof; `typ`/token profile và issuer-specific contract.
10. **Authorization:** scope/permissions, principal type, tenant, object ownership/ACL, session/grant state nếu yêu cầu.
11. **Sender constraint:** DPoP/mTLS proof và confirmation/binding khi token có profile đó.
12. **Revocation:** state, denylist hoặc TTL chiến lược; **chữ ký đúng không biến token đã thu hồi thành hợp lệ**.

### 9.2. Lỗi `alg=none` và algorithm confusion

Một JWS header attacker sửa thành:

~~~json
{"alg":"none","typ":"JWT"}
~~~

Không được khiến RS bỏ qua signature. Tương tự, nếu RS mong `RS256` nhưng bị lừa xử lý `HS256` và dùng **bytes public RSA key** làm HMAC secret, attacker có thể giả MAC theo public key vốn ai cũng biết — đây là dạng **algorithm confusion** kinh điển.

**Quy tắc:** không quyết định thuật toán tin cậy chỉ từ header; cấu hình allowlist và key type/usage/issuer association. Libraries hiện đại giúp chống loại lỗi này nhưng ứng dụng vẫn cần cấu hình đúng.

### 9.3. Wrong `kid` không cho phép fallback sang key khác tùy ý

Nếu token `kid=unknown-999`, RS có thể **làm mới JWKS từ issuer tin cậy theo chính sách** để hỗ trợ rotation, nhưng:

- Không tải key từ URL do token khai báo.
- Không thử HMAC secret mặc định.
- Không cho token qua chỉ vì chưa lấy được JWKS.
- Không cache negative key ID vô hạn hoặc làm JWKS fetch storm do attacker gửi `kid` ngẫu nhiên.
- Không bỏ issuer/audience checks khi tìm ra một key verify được.

### 9.4. Key đúng nhưng token sai audience

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Nếu `payments-api` kiểm chữ ký bằng đúng public JWKS nhưng **bỏ `aud`**, token của Orders có thể bị dùng sai ở Payments. Đây là **token substitution**, không phải lỗi thuật toán ký. `aud` kiểm phía RS được yêu cầu bởi hợp đồng OAuth access token/profile.

### 9.5. ID token không phải access token

OIDC ID token `aud=shop-web` được **OIDC Client** sử dụng để xác minh kết quả đăng nhập; không gửi làm Bearer cho `orders-api`. Một RS kiểm signature/issuer mà bỏ token purpose có thể chấp nhận nhầm ID token, client assertion hoặc JWT khác.

Với **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, access JWT có token type/profile cụ thể (ví dụ `typ=at+jwt`), cũng phải kiểm issuer, audience và claims theo profile. **Không áp mọi quy tắc của ID token cho access token một cách máy móc**, hoặc ngược lại.

### 9.6. JSON/Web Token không mặc định liên quan end user

Một token từ **Client Credentials Grant** có thể có `sub` chỉ service principal hoặc `client_id` của client. Dù signature đúng, `GET /me` là user-only endpoint vẫn phải từ chối nếu không có user authentication/delegation đáng tin. **Public key verification chỉ kiểm người phát token, không quyết định ý nghĩa principal**.

## 10. Vòng đời khóa: tạo, phát hành, xoay vòng, nghỉ hưu, ứng cứu

### 10.1. Trạng thái key theo vai trò

~~~mermaid
stateDiagram-v2
    [*] --> GENERATED
    GENERATED --> PREPUBLISHED: Publish verifier key if needed
    PREPUBLISHED --> ACTIVE: Sign new tokens with key
    ACTIVE --> VERIFY_ONLY: Stop signing, retain verification
    VERIFY_ONLY --> RETIRED: All relevant tokens no longer accepted
    ACTIVE --> COMPROMISED: Key exposure or suspected compromise
    VERIFY_ONLY --> COMPROMISED: Key exposure or suspected compromise
    COMPROMISED --> DISABLED: Emergency revoke/deny and replace
    RETIRED --> [*]
    DISABLED --> [*]
~~~

Đây là **mô hình vận hành**, không là key-state machine chuẩn JOSE bắt buộc. Thực tế key rotation liên quan cả **key-management service, issuer deployment, RS JWKS caches** và thời hạn token.

### 10.2. Rotation bất đối xứng đúng trình tự

Một kế hoạch điển hình:

1. AS sinh cặp **K2** trong HSM/KMS hoặc secret-managed environment, giữ private key bí mật.
2. AS đưa **public K2** vào JWKS tin cậy nhưng vẫn ký token mới bằng **private K1**.
3. Đợi RS caches nhìn thấy K2 theo rollout strategy; đo khả năng JWKS refresh/`kid`.
4. AS bắt đầu ký token mới bằng K2, header `kid=K2`.
5. Trong thời gian chuyển tiếp, JWKS chứa **public K1 và public K2** để RS xác minh token K1 cũ còn hạn.
6. Ngừng phát token với K1, theo dõi token TTL tối đa, cache propagation và skew.
7. Khi không còn token hợp lệ cần verify K1, **retire K1** khỏi JWKS; hủy private K1 theo policy.
8. Kiểm canary tokens trên tất cả RS/regions trước và sau chuyển đổi.

### 10.3. Timeline rotation minh họa

~~~text
Day 0 08:00   Publish public K2 in issuer JWKS.
Day 0 09:00   RS caches refreshed, K2 visible.
Day 0 10:00   AS signs new JWT with private K2 (kid=K2).
Day 0 10:30   Last JWT signed with K1 naturally expires.
Day 0 11:00   Retire public K1 after measured safety margin.

Verification:
  K1-signed token before expiration -> accepted only if still valid.
  K2-signed token -> verify with trusted public K2.
  Wrong issuer/audience -> rejected even when signature valid.
~~~

Thời gian là **ví dụ**, không phải một quy tắc “một giờ là đủ”. Nếu AS có refresh flows, token lifetime lớn, replay grace, multiple regions hoặc caches lâu, kế hoạch phải tính thêm. **Không dùng lịch cố định mà bỏ đo cache và token validity thực tế**.

### 10.4. Không xóa public key cũ quá sớm

Nếu token K1 còn hiệu lực đến 10:30 nhưng AS xóa public K1 lúc 10:01, RS có thể từ chối người dùng hợp lệ hàng loạt. Khi không bị compromise, giữ **verify-only public key K1** đến khi tokens K1 còn hạn đã hết theo policy.

Nếu **private K1 bị lộ**, việc giữ K1 làm verifier có thể nguy hiểm vì attacker có thể tiếp tục ký giả. Emergency rotation cần **ngừng tin K1**, revoke/deny tokens liên quan, reauthorize/reissue, dù có gián đoạn. **Đừng máy móc giữ K1 đến expiry** khi key đã compromise.

### 10.5. Rotation HS256 đòi đồng bộ bí mật

Với symmetric key:

~~~text
K1 -> old HMAC secret
K2 -> new HMAC secret

AS switches to K2 only when verifiers can validate K2 tokens.
Verifiers retain K1 temporarily for existing signed tokens.
After retirement, K1 must be removed from every signer/verifier.
~~~

Cần giới hạn nơi phát K2 và khả năng các RS có đủ quyền đọc secret. Nếu một RS chỉ giữ K1 nhưng AS đã ký K2, request fail. Nếu cả K1/K2 cùng được chấp nhận quá lâu, bề mặt keys tăng. **Mọi verifier giữ HMAC secret mới đều có khả năng ký** — rotation không sửa được shared-key trust boundary.

### 10.6. JWKS cache và unknown `kid`

JWKS thường được cache theo HTTP/provider policy. RS nên có bounded refresh khi nhìn thấy `kid` mới, xử lý rate limiting và key-mismatch failures. **JWKS endpoint đang down** không phải lý do chấp nhận unverified JWT. Với cache key cũ còn hạn, ứng dụng có thể tiếp tục verify theo strict cache policy; không mở rộng trust vô thời hạn khi issuer key state không rõ.

## 11. Bảo vệ private key và secret ở runtime

### 11.1. Key generation

- Dùng **CSPRNG** và crypto library chuẩn. RSA/EC/Ed25519 key pair phải sinh bằng API/provider đúng thuật toán.
- Đặt security strength và key size theo chuẩn tổ chức; không tự tạo RSA primes hoặc EC curve tùy ý.
- Không tạo key từ username, timestamp, `Random` thông thường hoặc password yếu.
- Mỗi môi trường production/staging/dev cần key isolation phù hợp; đừng chia private signer key giữa môi trường chỉ để tiện test.
- Phân biệt **signing**, **encryption**, **client authentication** và **sender proof** keys.

### 11.2. Lưu khóa: secret manager, KMS, HSM

| Cơ chế | Mục tiêu | Lưu ý |
|---|---|---|
| **Secret Manager** | Phân phối shared secret/private key theo RBAC và rotation policy. | Không dump secrets vào environment diagnostics, crash logs hoặc CI outputs. |
| **KMS signing API** | Có thể ký mà app không đọc private key raw theo service policy. | Quản lý key IAM, thuật toán, rate limits, latency và revoke. |
| **HSM** | Bảo vệ key material trong phần cứng/biên tin cậy chuyên dụng. | Chính sách key export, backup, failover, key generation và audit. |
| **Java KeyStore/PKCS#12** | Lưu/đọc keys tại runtime theo cấu hình. | Bảo vệ keystore password, file permissions, lifecycle; file bị copy có thể làm lộ key. |
| **JWKS public endpoint** | Công bố public verification keys. | Chỉ public fields; TLS, issuer binding, cache và integrity. |

**Public JWKS không phải nơi để cất symmetric HMAC secret.** JWK `kty=oct` mang symmetric secret; **không được đưa nó vào public JWKS**.

### 11.3. IAM least privilege cho signing keys

- Chỉ AS signing workload được gọi `Sign` với issuer private key.
- RS chỉ cần verify/public JWKS, không cấp quyền KMS sign.
- CI/CD pipeline không cần đọc production private key để chạy unit tests.
- Audit key-use events theo service identity và security policy, không ghi private key raw.
- Chia trách nhiệm approve key rotation, revoke, distribute và rollback.
- Bảo vệ backups, log snapshots, container layers và support bundles.

### 11.4. Key compromise khác token compromise

Một access token bị đánh cắp cho phép replay **trong scope/audience/lifetime của token đó** nếu bearer. **Private signing key của AS bị lộ** có thể cho attacker khả năng tạo token mới giả claims đến khi trust key bị cắt; đó là sự cố lớn hơn. **HMAC shared secret lộ ở RS** cũng có thể cho phép tạo token giả. Rotation/denylist/reissue cần phù hợp loại credential bị lộ.

### 11.5. Tránh key export tùy tiện

Nếu KMS/HSM cho phép ký nội bộ, không xuất private key xuống file/tmp/container chỉ vì thư viện JWT dễ dùng hơn. Chọn signer adapter/JOSE integration hỗ trợ ký qua KMS khi phù hợp và có kiểm thử hiệu năng. Tránh đưa private key/secret vào metrics, stack traces hoặc `toString()` của object.

## 12. Encryption trong token security: khi nào cần JWE?

### 12.1. JWS/JWE/TLS phục vụ các ranh giới khác nhau

| Biện pháp | Bảo vệ gì | Không tự làm gì |
|---|---|---|
| **HTTPS/TLS** | Confidentiality/integrity của kết nối giữa hai endpoints. | Không che token khỏi process/log sau khi kết thúc TLS. |
| **JWS** | Integrity/source verification theo signing key trust. | Không mã hóa claims khỏi người giữ token. |
| **JWE** | Confidentiality của payload đối với recipients có key phù hợp. | Không tự cấp quyền, không tự có issuer signature của lớp trong. |
| **Disk encryption** | Dữ liệu lưu trữ khi mất ổ/backup theo threat model. | Không ngăn app/DB account có quyền đọc plaintext. |
| **Opaque reference token** | Không tiết lộ claims trong token string theo hợp đồng. | Không ngăn bearer replay khi token bị đánh cắp. |

### 12.2. Mã hóa lai (hybrid encryption)

Trong JWE, thường có **Content Encryption Key (CEK)** dùng để mã hóa plaintext bằng AEAD; CEK được bảo vệ/derive qua key management scheme.

~~~text
JWE recipient public key / agreed key material
       |
Key management (e.g., RSA-OAEP-256 or ECDH-ES)
       |
Content Encryption Key (CEK)
       |
AEAD encryption (e.g., A256GCM)
       |
Ciphertext + tag, plus protected header
~~~

Không lấy RSA private signing key để mã hóa plaintext bằng một sơ đồ tự chế; dùng **JWE library** với thuật toán, key usage và recipient profile cụ thể. JWE encryption không tự là chữ ký của AS.

### 12.3. JWT claims nhạy cảm và data minimization

Một JWS access token có thể chứa `email`, `phone`, `address` hoặc `roles`. Ai có token có thể đọc payload nếu không mã hóa. Nếu claims nhạy cảm:

1. **Giảm claims trong token**; chỉ đưa fields cần cho RS.
2. Cân nhắc **opaque access token** nếu muốn RS tra metadata thay vì expose payload.
3. Cân nhắc **JWE** khi cần payload confidentiality ở tầng token và các recipients hỗ trợ decrypt.
4. Bảo vệ transport/storage, không log token.
5. Không đẩy raw PII vào JWT chỉ vì có encryption; payload vẫn tồn tại ở recipient.

### 12.4. AES-GCM nonce reuse là lỗi nghiêm trọng

Nếu dùng cùng key AES-GCM và cùng nonce hai lần, tính bảo mật có thể sụp đổ. Phải để crypto library/JOSE implementation quản lý IV/nonce an toàn theo scheme, lưu/đếm phù hợp nếu tự gọi API thấp hơn, và dùng authentication tag đầy đủ theo profile.

### 12.5. Khi encrypted JWT bị sử dụng thay access token

Resource Server phải decrypt **theo profile đã đăng ký**, rồi nếu có nested signed JWT thì kiểm signature/issuer/audience/expiry và mục đích. **Giải mã thành công không tự cho phép request**. Không nhận JWE tùy ý nếu API chỉ hỗ trợ signed access JWT/JWS.

## 13. Key roles trong OAuth 2.0 và OIDC

### 13.1. ID token: JWT dành cho OIDC Client

OIDC ID token thường được **OP ký** để Client kiểm `iss`, `sub`, `aud` (client ID), thời hạn, `nonce` khi áp dụng và các yêu cầu profile. **ID token không phải access token gửi UserInfo/Resource Server**.

### 13.2. Access token: JWT hoặc opaque

- **JWT access token:** RS dùng signing key/public JWKS của AS đúng profile để verify, rồi kiểm scope/tenant/object policy.
- **Opaque access token:** RS introspect/tra lookup tin cậy; không phải cứ opaque là “chưa ký” theo mọi mô hình bên trong.
- **Bearer access token:** có thể bị replay nếu lộ; signing algorithm không thay bearer transport.
- **Sender-constrained access token:** RS còn kiểm proof key/certificate binding theo profile.

### 13.3. Refresh token và authorization code

Refresh token thường là opaque reference credential và được AS quản lý rotation/revocation/token family; **không gửi tới RS**. Authorization code là short-lived one-time credential, được bind với client/redirect/PKCE theo flow. Không tự coi refresh token và authorization code là JWT access token chỉ vì chúng là chuỗi.

### 13.4. `client_secret_jwt` và `private_key_jwt`

Đó là **phương thức xác thực OAuth client với token endpoint**, không phải loại access token cho RS.

| Method | Key material | Ý nghĩa |
|---|---|---|
| `client_secret_jwt` | Shared client secret tương ứng. | Client ký JWT assertion bằng HMAC theo registration/profile. |
| `private_key_jwt` | Private signing key của client. | Client ký JWT assertion; AS dùng registered public key để verify. |
| `client_secret_basic` | Client ID + client secret qua HTTP Basic over TLS. | Confidential client authentication; không phải user authentication. |
| mTLS client authentication | Client certificate/private key. | Chứng minh danh tính client ở TLS layer theo registration. |

Client assertion `iss`/`sub`/`aud`/`exp`/`jti` có ngữ nghĩa và constraints theo RFC 7523 và profile. **AS public JWKS dùng cho ID/access token signing không phải client JWKS dùng cho private_key_jwt** trừ khi một cấu hình rõ ràng và an toàn yêu cầu. Client không được dùng assertion mình ký để tự biến thành issuer phát access token.

### 13.5. Phân biệt client authentication và user consent

`private_key_jwt` đúng chữ ký chỉ chứng minh **client sở hữu private key đã đăng ký**. Nó không chứng minh end user đã consent `payments:refund`, không tự nâng Client Credentials Grant thành quyền user, không thay tenant/resource authorization.

## 14. DPoP và mTLS: possession key khác signing key của AS

### 14.1. DPoP proof

Với **DPoP (RFC 9449)**, client tạo proof JWT có chữ ký bằng **client-controlled private key**. Token được AS ràng buộc với public key tương ứng (theo profile). RS kiểm proof signature, method/URI/time/`jti`, `ath` khi áp dụng và token confirmation key binding.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Request access token with DPoP proof
    AS->>AS: Verify proof and bind token to client key
    AS-->>C: Sender-constrained access token
    C->>RS: Token + DPoP proof for HTTP method/URI
    RS->>RS: Validate token, proof, key binding and replay
    RS-->>C: Protected resource when authorized
~~~

**DPoP private key không phải AS signing key**. Một attacker có bản sao access token nhưng thiếu proof key sẽ khó replay hơn, nếu RS kiểm proof đúng. Nếu attacker chiếm cả client private key/process, vẫn có nguy cơ.

### 14.2. mTLS certificate-bound access token

Với **RFC 8705**, client certificate và private key có thể gắn với access token. RS phải xác minh TLS peer certificate/confirmation binding theo profile. **Không tin `X-Client-Cert` header do caller tùy ý gửi**; nếu TLS termination ở gateway, identity forwarding phải có trust boundary và xác thực kênh nội bộ.

### 14.3. HMAC/signature vẫn không chặn replay nếu không có binding

JWS signature chứng minh token bytes không bị sửa; **không chứng minh HTTP request hiện tại thuộc client gốc**. DPoP/mTLS thêm điều kiện possession, nhưng **không thay** `iss`, `aud`, `scope`, token TTL, revocation và object-level authorization.

### 14.4. Key rotation và sender binding

Khi client rotate DPoP/mTLS key, access token cũ bound với key cũ **không tự chuyển sang key mới**. Cần xin token mới và xử lý token cũ theo policy. Không vô hiệu binding chỉ để “chuyển đổi cho dễ”.

## 15. Java JCA: HMAC-SHA-256 minh họa

Dùng Java `Mac` để minh họa, không tự viết HMAC bằng digest concatenate. Cách so sánh nên tránh so chữ ký theo string có timing phụ thuộc dữ liệu.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacExample {
    private HmacExample() {}

    public static byte[] computeMac(byte[] secret, byte[] message)
            throws Exception {

        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException("HS256 key too short");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    public static boolean verifyMac(
            byte[] secret, byte[] message, byte[] candidateMac)
            throws Exception {

        if (candidateMac == null || candidateMac.length != 32) {
            return false;
        }

        byte[] expected = computeMac(secret, message);
        return MessageDigest.isEqual(expected, candidateMac);
    }

    public static void demo(byte[] secretFromSecretManager)
            throws Exception {

        byte[] message = "signed-data".getBytes(StandardCharsets.UTF_8);
        byte[] mac = computeMac(secretFromSecretManager, message);

        if (!verifyMac(secretFromSecretManager, message, mac)) {
            throw new IllegalStateException("HMAC failure");
        }
    }
}
~~~

**Giới hạn và điều kiện bảo mật:**

- `secretFromSecretManager` phải có **entropy thực**, không chỉ 32 bytes từ password lặp lại; kiểm `length >= 32` không chứng minh entropy.
- Code ký `message` minh họa, **không tạo JWT**: muốn tạo JWS phải ký đúng `base64url(header).base64url(payload)` và tuân JOSE encoding.
- `MessageDigest.isEqual` giúp tránh so sánh byte-by-byte theo nhánh ứng dụng dễ lộ thời gian, nhưng **không có bảo đảm timing bất biến tuyệt đối toàn bộ request**.
- Không ghi secret, message chứa credential hoặc MAC khi không cần thiết vào logs.
- Không dùng secret HMAC này ở mọi RS nếu muốn tách quyền signer/verifier.
- Không dùng `HS256` để ký token ở ứng dụng frontend công khai, nơi secret không thể bảo mật.

## 16. Java JCA: RSA ký và xác minh với public/private key

Ví dụ dùng `Signature` API cho RSA PKCS#1 v1.5 với SHA-256, tương ứng primitive ký trong `RS256`; **không tự xây dựng JOSE Compact Serialization**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class RsaSignatureExample {
    private RsaSignatureExample() {}

    public static byte[] sign(PrivateKey privateKey, byte[] message)
            throws Exception {

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(message);
        return signature.sign();
    }

    public static boolean verify(PublicKey publicKey,
            byte[] message, byte[] detachedSignature) throws Exception {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(detachedSignature);
    }

    public static void demoForLearning() throws Exception {
        // Ephemeral test key. In production keep private key in KMS/HSM.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "signed-data".getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(pair.getPrivate(), message);

        if (!verify(pair.getPublic(), message, signature)) {
            throw new IllegalStateException("Signature failed");
        }

        // Public key alone cannot create a valid signature.
        // Never export or log pair.getPrivate() in production.
    }
}
~~~

### 16.1. RSA-PSS là thuật toán khác

Nếu cần `PS256`, Java JCA thường dùng `Signature.getInstance("RSASSA-PSS")` cùng `PSSParameterSpec` tương thích JWA (SHA-256, MGF1 SHA-256, salt length 32, trailer field 1). **Không đổi từ `SHA256withRSA` sang `PS256` chỉ bằng đổi JWT header**; phải ký/verify đúng primitive và parameters.

### 16.2. Không tự xây ECDSA JWT từ JCA signature

ECDSA JCA thường trả DER; JOSE `ES256` cần raw `R || S`. Nếu không chuyển đổi đúng, chữ ký không tương thích hoặc có lỗi parser. Dùng thư viện JOSE đã kiểm thử thay vì tự đóng gói bytes. Tương tự EdDSA/Ed25519 phải phù hợp JWK/`alg`/provider của cả AS và RS.

### 16.3. Không lưu private key trong biến môi trường vô hạn

Một private key load vào app process có thể bị lộ qua memory dump/snapshot/diagnostics. Khi khả thi, dùng **KMS/HSM signer** giữ private key không xuất được và giảm quyền/signing operations theo IAM. Java demo tạo ephemeral key chỉ để học, **không phải mẫu vận hành production**.

## 17. Spring Security Resource Server: verify JWT bằng trusted JWKS

Với **Spring Security OAuth2 Resource Server**, ứng dụng có thể xác minh access JWT theo issuer và public JWKS. Ví dụ sau dành cho **Spring Security 6.x**, xác minh `RS256`, issuer và audience. Nó chưa thay các kiểm tra scope, tenant, object ACL hoặc sender-bound proof.

### 17.1. Decoder với thuật toán cho phép

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {
    private static final String ISSUER = "https://login.example.com";
    private static final String AUDIENCE = "orders-api";

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        // JWKS URI is trusted configuration, NOT a JWT header URL.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://login.example.com/oauth2/jwks")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience
            )
        );
        return decoder;
    }
}
~~~

Giải thích:

1. `withJwkSetUri` dùng JWKS của **trusted issuer**, không đọc URL từ `jku` của token.
2. `jwsAlgorithm(RS256)` quy định thuật toán chấp nhận, tránh lỗi cho token tự lựa chọn `HS256` hoặc `none`.
3. `JwtValidators.createDefaultWithIssuer` xử lý issuer và các điều kiện mặc định, gồm thời gian theo Spring version.
4. `audience` validator rõ ràng yêu cầu `orders-api`; **không mặc định Spring tự suy ra audience từ issuer**.
5. Nếu dùng RFC 9068, còn cần validator token profile/purpose như `typ=at+jwt`; ví dụ chưa tự kiểm điều đó.
6. `scope`/tenant/ownership phải được kiểm ở tầng authorization tương ứng.
7. Cache public JWKS, unknown `kid`, clock skew và timeout cần kiểm thử với provider/version thực tế.

### 17.2. SecurityFilterChain kiểm scope

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

**`hasAuthority("SCOPE_orders:read")` không có nghĩa user đọc được mọi đơn.** Resource Server phải kiểm owner/tenant/ACL, trạng thái đơn và chính sách nghiệp vụ. Endpoint chỉ cho user cũng phải xác minh USER principal chứ không nhận service token rồi tin `X-User-Id` từ request.

### 17.3. Khi JWKS chưa thấy `kid` mới

~~~text
K1: trusted old public key
K2: new public key, prepublished in trusted issuer JWKS

Token kid=K1, not expired, issuer/aud valid:
    verify using K1 if key still authorized.

Token kid=K2:
    refresh JWKS from trusted URI with bounded policy.
    verify with K2 if available.

Token kid=attacker-key, URL jku=attacker.example:
    reject; never download attacker-supplied key.

Trusted JWKS service down:
    do not accept unverified tokens.
    apply strict cache/outage policy.
~~~

**Public-key rotation khác grant/token revocation.** AS đổi signing key không đồng nghĩa đã vô hiệu mọi refresh tokens hoặc sessions; cần policies độc lập.

## 18. Authorization Server: dùng private key sau khi kiểm grant

### 18.1. Đừng coi signer là authorization engine

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant P as Grant and Resource Policy
    participant K as KMS/HSM Signer
    participant RS as Resource Server
    C->>AS: Token request under valid OAuth grant
    AS->>P: Verify client, subject, consent, scope, audience
    P-->>AS: Approved token claims
    AS->>K: Sign JWS signing input with authorized private key
    K-->>AS: Digital signature
    AS-->>C: Access JWT
    C->>RS: Bearer access JWT
    RS->>RS: Verify AS key and token claims, apply resource ACL
    RS-->>C: Protected result only when authorized
~~~

KMS/HSM có thể ký bytes được yêu cầu, nhưng **không tự biết user có quyền hoàn tiền hay không**. AS phải tính claims đúng trước khi yêu cầu ký; RS cũng phải kiểm quyền ở API đích.

### 18.2. Token được ký đúng vẫn có thể cấp sai quyền

Nếu AS có bug và tạo `scope=payments:refund` cho user không được phép, chữ ký `RS256` hoàn toàn có thể hợp lệ. Đây là **lỗ hổng issuance policy**, không phải lỗi toán học chữ ký. Tests phải chứng minh issued scopes không vượt client registration, current grant/consent, user/service permission, resource và tenant policy.

### 18.3. Nhiều loại token có thể cùng một issuer key

Một OP có thể phát **ID token `aud=shop-web`**, **access token `aud=orders-api`** và **token client assertion/token exchange profile**. Dù signature cùng xác minh bằng public JWKS, RS phải kiểm đúng **token type, audience, issuer, lifetime và principal semantics**. Khi cần giảm cross-JWT confusion, cân nhắc tách signing keys/issuers theo purpose nhưng **không bỏ type checks**.

### 18.4. Least privilege cho KMS/HSM

- AS signing service được phép gọi `Sign` với issuer key đã đăng ký.
- Resource Server chỉ được đọc public JWKS; không cấp quyền `Sign` cho RS.
- CI/test dùng test key pair, không dùng private signer production.
- Không log raw private key, ký thử bằng dữ liệu tùy ý từ user hay export key từ HSM chỉ để tiện debug.
- Rotation controllers và operators cần IAM/audit/two-person controls nếu rủi ro yêu cầu.

## 19. Migration từ HS256 sang chữ ký bất đối xứng

Không thể chuyển HS256 → RS256/PS256 chỉ bằng cách thay `alg` header: cần đổi crypto primitive, keys, trust configuration, JWKS và hành vi verifiers.

### 19.1. Kế hoạch thực hiện

1. **Inventories:** liệt kê AS, RS, audiences, issuers, HS256 secrets, token TTL, điểm lưu secret và các clients/partners.
2. **Generate K2:** tạo RSA/EC/EdDSA signing key pair theo policy, private key nằm trong KMS/HSM/secret-managed signer.
3. **Publish:** công bố public K2 trong issuer JWKS qua trusted HTTPS, bảo vệ private material.
4. **Prepare verifiers:** cấu hình allowlist thuật toán và issuer/audience/key usage rõ cho các RS; canary test K2.
5. **Switch AS signer:** bắt đầu phát token với private K2/`kid=K2` khi verifiers đã sẵn sàng.
6. **Transition:** trong cửa sổ cần thiết, RS có thể hỗ trợ **hai profiles được cấu hình rõ** để xử lý token HS256 cũ đến khi hết hạn; không để `alg` tự chọn key source tùy tiện.
7. **Retire old secret:** ngừng ký HS256, từ chối token cũ sau policy window và xóa HS256 secret khỏi RS/config/CI.
8. **Verify:** đo errors, JWKS propagation, wrong algorithm acceptance và bảo đảm không còn endpoint nhận HS256 ngoài policy.

### 19.2. Sai lầm thuật toán tự chọn theo JWT header

**Sai:**

~~~text
if header.alg == "HS256":
    verify using publicRsaKeyBytes as HMAC secret
else if header.alg == "RS256":
    verify using embedded header.jwk
else if header.alg == "none":
    accept payload
~~~

**Đúng theo nguyên tắc:**

~~~text
trusted issuer + token profile
    -> configured allowed algs and key types
    -> issuer-trusted key source or secret
    -> signature/MAC verification
    -> issuer/audience/time/purpose validation
    -> scope/tenant/object authorization
~~~

Không chấp nhận unverified JWT để giảm outage. Nếu chính sách bảo mật không cho phép dual acceptance, có thể chọn **reissue ngay và chấp nhận gián đoạn có kiểm soát** thay vì giữ HS256 lâu hơn; phải có migration plan rõ.

## 20. Threat model: lỗi thường gặp về keys và JWT

| Sai lầm/tấn công | Hậu quả | Biện pháp |
|---|---|---|
| HS256 secret yếu | Attacker đoán secret offline khi thấy một token. | CSPRNG, entropy đủ, secret manager. |
| Secret HS256 phát cho nhiều RS | Một RS bị chiếm có thể ký giả token. | Asymmetric signing hoặc tách strict trust domains. |
| JWT `alg=none` được chấp nhận | Token không chữ ký thành hợp lệ. | Strict algorithm allowlist. |
| HS256/RS256 confusion | Public RSA key bị dùng như HMAC secret. | Bind key type/use/alg, tách validators. |
| `kid` path traversal | Truy cập file key tùy ý. | Chỉ lookup trong trusted key set. |
| `jku`/`x5u` từ attacker | SSRF hoặc lấy public key attacker. | Không trust token-provided URL. |
| Embedded `jwk` được tin | Attacker ký bằng private key riêng rồi gửi public key. | Pinned issuer JWKS. |
| Public JWKS chứa `d`/RSA private fields | Private signing key bị lộ. | Automated key export checks và incident response. |
| Công khai `kty=oct` JWK | HMAC secret bị công bố. | Không publish symmetric secrets. |
| Bỏ kiểm `iss` | Nhận token từ issuer ngoài trust list. | Exact issuer validation. |
| Bỏ kiểm `aud` | Token Orders được dùng tại Payments. | Resource audience validation. |
| Bỏ token type/purpose checks | OIDC ID token dùng như access token. | Validate token profile/`typ`/aud. |
| Bỏ `exp`/`nbf` | Token hết hạn hoặc chưa active được dùng. | Time validators và bounded clock skew. |
| Chỉ Base64-decode không verify | Attacker tự sửa `scope=admin`. | Cryptographic verification trước claims. |
| JWS được hiểu là encrypted | Lộ email/PII từ payload. | Minimize claims, opaque/JWE khi cần. |
| JWE giải mã thành công là accept | Không xác minh nguồn ký/purpose. | Đúng JWE/JWS profile, issuer và claims checks. |
| AES-GCM nonce reuse | Có thể phá confidentiality/integrity. | Unique nonce under key, library AEAD. |
| Private key ở frontend/CI logs | Token forgery nếu key bị đánh cắp. | Server-only signer, KMS/HSM/secret manager. |
| RS có KMS `Sign` quyền | RS compromise thành issuer compromise. | IAM least privilege, verify-only RS. |
| Xóa K1 public key quá sớm | Token còn hạn bị từ chối. | Prepublish/overlap hợp lý khi K1 không compromise. |
| Giữ K1 sau khi private K1 bị lộ | Attacker vẫn ký token giả. | Emergency deny/rotate/reissue. |
| Random unknown `kid` làm fetch storm | DoS JWKS/AS. | Bounded refresh/rate limit/cache. |
| Bearer token bị log | Replay dù JWT signature hợp lệ. | Không log tokens, TTL/sender binding/revoke. |
| DPoP proof không kiểm key binding | Sender protection bị bypass. | Verify proof, `ath`/`jti`/`htu`/`htm` theo profile. |
| Token đúng chữ ký, sai tenant | BOLA/IDOR hoặc dữ liệu sai tổ chức. | Tenant/object-level authorization. |

**Phân biệt sự cố:** lộ **một access token** cho phép lạm dụng bearer trong phạm vi token; lộ **AS private signing key** hoặc **shared HS256 secret** có thể cho phép ký token giả. Không xử lý hai loại sự cố bằng đúng một thao tác “revoke một JWT”.

## 21. Key lifecycle: audit, metrics và ứng cứu sự cố

### 21.1. Audit không lưu key hoặc token thô

~~~json
{
  "event": "jwt_signing_key_activated",
  "issuer": "https://login.example.com",
  "key_id": "as-signing-2026-11",
  "algorithm": "RS256",
  "key_use": "sig",
  "previous_phase": "PREPUBLISHED",
  "current_phase": "ACTIVE",
  "actor_type": "SERVICE",
  "actor_id": "key-rotation-controller",
  "approval_ref": "rotation-approval-81",
  "result": "SUCCESS",
  "trace_id": "68a1c238039c4d1d953198723afb7db8"
}
~~~

`key_id` là identifier phục vụ vận hành, không phải private material. Không log/export private RSA/EC/JWK `d`, HMAC secret, KMS credentials, raw access/refresh/ID tokens hoặc `Authorization` headers. Audit key usage phải có RBAC và retention phù hợp.

### 21.2. Metrics minh họa

~~~text
jwt_signature_validation_total{issuer,algorithm,result}
jwt_wrong_audience_total{resource}
jwt_unknown_kid_total{issuer}
jwks_refresh_total{issuer,result}
jwks_refresh_latency_seconds{issuer}
kms_sign_request_total{key_group,result}
kms_sign_latency_seconds{key_group}
jwt_key_rotation_phase{issuer,phase}
jwt_expired_total{resource}
~~~

Không sử dụng raw token, `jti`, email/user ID hoặc `kid` từ bearer header làm metric labels không giới hạn cardinality. Nếu cần ghi `kid` để điều tra, giới hạn độ dài, escape và đặt trong audit/log có kiểm soát.

### 21.3. Sự cố lộ private signing key

Playbook:

1. **Ngăn lộ tiếp:** thu hồi quyền truy cập, đóng key export, bảo vệ logs/CI/backups.
2. **Xác minh phạm vi:** issuer, key ID, nơi sử dụng, tokens còn hạn, RS/regions liên quan.
3. **Sinh key mới an toàn:** bảo vệ private key trong KMS/HSM, prepublish public key nếu thời gian cho phép.
4. **Ngừng tin key cũ:** đưa key bị lộ vào emergency denial/retirement trên các RS; xử lý outage/reissue.
5. **Revoke/deny tokens:** đánh giá issued tokens, denylist/issuer-key cutoff và token/grant policies.
6. **Phát token mới:** chỉ theo grant/authorization hiện hành, không “re-sign” bất kỳ user claims tự khai.
7. **Kiểm tất cả RS:** test token K cũ bị từ chối ở mọi vùng; JWKS caches và mobile/partner verifiers cần được tính.
8. **Điều tra:** tìm forged tokens, abnormal audience/scopes, KMS `Sign` audit, dữ liệu đã bị truy cập.
9. **Khắc phục gốc:** IAM, backup, CI, private key handling, signer deployment.
10. **Đo khắc phục:** chứng minh token giả bằng key cũ không còn được nhận theo incident SLA.

Nếu chỉ lộ **một bearer token** mà signing key vẫn an toàn, không mặc định phải rotate issuer signing key; ưu tiên revoke token/grant và xử lý token leakage. Hai kiểu incident có mức ảnh hưởng khác nhau.

### 21.4. Rollback phải không mở lỗ hổng

Khi deployment K2 lỗi, việc quay lại K1 chỉ được phép nếu K1 **chưa bị compromise**, thuộc allowed key policy và các RS sẵn sàng xác minh. Không “rollback” sang HS256 secret từng bị lộ hoặc bật `alg=none` để giữ availability.

## 22. Ma trận kiểm thử mật mã và token validation

Các test phải dùng **issuer, public/private keys, user và bearer tokens giả trong môi trường cô lập**, không dùng production signer/private key.

### 22.1. Fixtures

~~~text
Issuer trusted: https://login.example.com
Issuer untrusted: https://other-login.example.com
Resource Server: orders-api
Accepted access JWS alg: RS256
Expected audience: orders-api
Expected access JWT type: at+jwt (if RFC 9068 profile)
Required scope: orders:read

Key K1: test RSA private/public pair, trusted kid=K1
Key K2: test RSA pair for safe rotation
Key Kx: test attacker RSA pair, NOT in trusted JWKS
HS1: test HMAC secret, NOT accepted by RS256-only RS
~~~

### 22.2. Chữ ký và nguồn khóa

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| JWT RS256 hợp lệ | Ký K1, `kid=K1`, claims đúng. | Verify rồi áp authorization. |
| Sửa payload | Đổi `scope=orders:read` thành `admin`. | Signature fail. |
| Sửa header `alg=none` | Bỏ signature. | Từ chối. |
| RS256/HS256 confusion | Tạo HS256 MAC bằng RSA public bytes. | RS256-only RS từ chối. |
| PS256 trên RS256-only | Ký RSA-PSS hợp lệ. | Reject thuật toán ngoài allowlist. |
| Attacker Kx | JWT chữ ký đúng với private Kx. | Reject vì Kx không trusted. |
| Embedded `jwk` | Đính kèm attacker public JWK. | Không nhận làm trust anchor. |
| Attacker `jku` URL | Header trỏ host attacker. | Không fetch/từ chối. |
| `kid=../../key` | Cố đọc file ngoài set. | Không path traversal/key source injection. |
| Unknown `kid` | K không có trong trusted JWKS. | Bounded refresh trusted URI rồi reject. |
| Wrong key usage | `use=enc` ở key cần verify signature. | Reject theo profile/key policy. |
| Weak RSA key | Không đạt key-strength policy. | Reject/không deploy. |
| Public JWKS chứa `d` | Vô tình export private key. | Security/pipeline test fail, incident response. |
| Public JWKS chứa `kty=oct` với `k` | Lộ HMAC shared secret. | Security/pipeline test fail. |
| ES256 DER encoding sai | Chữ ký JWS không theo raw `R || S`. | Verify reject. |
| EdDSA không được hỗ trợ | Token `alg=EdDSA` tại RS chưa cấu hình. | Fail closed, không downgrade. |

### 22.3. Claims, purpose và quyền API

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Wrong issuer | JWT ký bởi issuer khác. | Từ chối. |
| Wrong audience | `aud=payments-api` tại Orders. | Từ chối dù chữ ký đúng. |
| Missing audience | Không có `aud` trong profile yêu cầu. | Từ chối. |
| Expired token | `exp` đã qua. | Từ chối. |
| Future `nbf` | Chưa đến thời điểm hợp lệ. | Từ chối. |
| ID token substitution | OIDC ID token `aud=shop-web` tại Orders. | Từ chối purpose/audience. |
| Client assertion substitution | `private_key_jwt` dùng làm access token. | Từ chối. |
| Service token tại user-only endpoint | `client_id=reporting-worker`, thiếu USER context. | Từ chối. |
| Missing scope | Chỉ `orders:write` gọi GET orders. | Từ chối. |
| Cross-tenant request | User Beta gọi tài nguyên Anpha. | Từ chối ACL/tenant. |
| BOLA/IDOR | Scope read đủ nhưng không sở hữu order. | Từ chối. |
| Revoked JWT còn đúng signature | Token state/denylist không còn active. | Từ chối theo policy. |
| DPoP-bound token thiếu proof | Bearer copy không có sender key. | Từ chối. |

### 22.4. Xoay vòng, JWE và storage

| Test | Điều kiện | Kỳ vọng |
|---|---|---|
| K2 prepublished | JWKS chứa public K1 + K2. | RS có thể nhận tokens K2 sau rollout. |
| Signer chuyển K2 | New JWT dùng `kid=K2`. | RS verify K2 với trusted JWKS. |
| Token K1 còn hạn | K1 không compromise, verify-only. | Cho phép theo chính sách đến expiry. |
| K1 nghỉ hưu | Đã hết tokens cần K1. | Không nhận K1 sau retirement. |
| K1 private compromise | Key bị lộ. | Emergency cutoff, không giữ K1 như rotate bình thường. |
| JWKS outage, unknown kid | RS không thể verify key mới. | Fail closed. |
| Random kid storm | Nhiều kid giả. | Không làm AS/JWKS DoS. |
| JWS có email/PII | Base64URL decode. | Chứng minh không phải ciphertext; giảm claims. |
| JWE wrong recipient key | Không có key giải mã. | Decrypt fail. |
| JWE authentication tag bị sửa | Thay ciphertext/tag. | AEAD verify fail. |
| JWE decrypted, inner signature sai | Profile đòi nested signed JWT. | Từ chối. |
| Nonce reuse trong code mẫu | GCM cùng key+nonce. | Security design test/policy fail. |
| HMAC secret trong Git/log | Canary/secret scanner phát hiện. | Fail pipeline, rotate khi cần. |
| RS có quyền KMS Sign | IAM policy sai. | Permission test fail. |

### 22.5. Kiểm tra bằng pseudocode

~~~text
test "trusted signer plus valid audience":
    K1 = testIssuer.generateRsaKeyPair()
    access = signJwt(
        key=K1.private, kid="K1", alg="RS256",
        claims={iss:trustedIssuer, aud:"orders-api",
                sub:"user-742", scope:"orders:read",
                exp:futureTime}
    )
    assert ordersApi.verifiesWithTrustedPublicK1(access)
    assert paymentsApi.rejects(access)
    assert ordersApi.rejects(tamperPayload(access, scope="admin"))

test "attacker key is not issuer key":
    Kx = attacker.generateRsaKeyPair()
    forged = signJwt(Kx.private,
                     claims={iss:trustedIssuer, sub:"admin"},
                     header={kid:"Kx", jku:attackerUrl})
    assert ordersApi.rejects(forged)
    assert no network request is made to attackerUrl

test "algorithm confusion is rejected":
    forged = makeHs256JwtUsingPublicRsaKeyAsHmacSecret()
    assert rs256OnlyApi.rejects(forged)

test "rotation of signing key":
    issuer.publishPublicKey(K2)
    assert allRSCanResolveTrustedKid("K2")
    issuer.switchSigningPrivateKey(K2.private)
    assert allRSVerify(issuer.issueAccessJwt())
    afterLastK1TokenExpires():
        issuer.retireK1()
        assert K1 not accepted

test "valid signature is not resource authorization":
    token = issuer.issueAccessJwt(
        sub="user-742", aud="orders-api",
        scopes={"orders:read"}
    )
    assert ordersApi.rejectsReadFromUnauthorizedTenant(token)
~~~

Pseudocode không phải tests chạy trực tiếp; cần integration tests qua AS/RS với signing keys/certificates test, JWT profile validators, mock clock, JWKS caching và resource database ACL.

## 23. Bài tập tình huống và đáp án

### Bài 1 — HS256 verifier có thể trở thành signer?

AS và hai APIs dùng cùng HMAC secret `K`. Attacker xâm nhập một API và đọc được `K`.

**Đáp án:** Có thể tạo HMAC chữ ký hợp lệ và giả JWT trong trust domain dùng `K` nếu không có những ràng buộc khác đủ chặn. Cần ứng cứu lộ key, rotate secret, đánh giá token đã cấp; về lâu dài cân nhắc asymmetric signing để RS chỉ giữ public key.

### Bài 2 — JWT RS256 có mã hóa email không?

Access JWT ký `RS256` có `email` và `sub` trong payload.

**Đáp án:** Không. Base64URL payload có thể đọc được, dù attacker không thể sửa payload mà vẫn giữ signature hợp lệ. Giảm PII, cân nhắc opaque/JWE khi cần confidentiality, bảo vệ transport/storage.

### Bài 3 — Attacker cung cấp public key riêng

Attacker ký token `sub=admin` bằng Kx rồi thêm public JWK Kx ở header.

**Đáp án:** RS phải từ chối vì Kx không thuộc **trusted issuer public key set**. Chữ ký đúng về mặt toán học với một key do attacker chọn không tạo identity/authorization trust.

### Bài 4 — Rotation K2 gặp cache cũ

AS ký bằng K2 lúc 10:00, RS cache JWKS đến 10:30 vẫn chỉ biết K1.

**Đáp án:** Token K2 có thể bị từ chối vì unknown `kid`. Cần prepublish public K2, bounded refresh, canary test và đo cache propagation trước khi switch signer. Không bỏ verify để tránh lỗi.

### Bài 5 — Private signing key bị lộ

Private K1 của issuer bị lộ, trong khi public K1 vẫn nằm trong JWKS cho tokens cũ còn hạn.

**Đáp án:** Đây là **emergency compromise**, không phải rotation bình thường. Giữ key tin cậy có thể cho attacker ký tokens giả. Cần key cutoff, revoke/reissue theo policy, cập nhật RS/partners, audit forged tokens và chấp nhận/giảm gián đoạn có kiểm soát.

### Bài 6 — Dùng cùng RSA key cho ký và mã hóa?

Một đội muốn dùng RSA private signer key của issuer để giải mã JWE.

**Đáp án:** Không tự dùng cùng key cho hai mục đích. Nên tách signing/decryption keys theo key usage, scheme, trust boundary và lifecycle, tránh cross-protocol/key-compromise blast radius.

### Bài 7 — Signature đúng, tenant sai

Token có `RS256` signature đúng, issuer/audience/scope đúng nhưng user chỉ thuộc tenant Beta và request tài nguyên Anpha.

**Đáp án:** Từ chối. Crypto kiểm trust của token issuer và integrity, không cấp quyền trên record/tenant. Resource Server phải kiểm membership và object ACL.

### Bài 8 — DPoP proof có thay access token signature?

Client tạo DPoP proof hợp lệ nhưng access token bị attacker sửa `scope`.

**Đáp án:** Không. RS phải kiểm chữ ký/claims **access token của AS** và proof/key binding của DPoP riêng. Proof không “hợp thức hóa” access token bị sửa.

### Bài 9 — Public JWK có phải secret không?

JWKS của AS công bố RSA `n` và `e`.

**Đáp án:** Đây là **public key parameters** được thiết kế để công bố. Sự cố xảy ra nếu JWKS chứa private `d`/RSA CRT fields hoặc symmetric `oct` secret key.

### Bài 10 — JWE giải mã được thì đã xác thực issuer?

RS giải mã thành công một JWE và lấy `role=admin` từ plaintext.

**Đáp án:** Chưa chắc. Phải biết bên tạo ciphertext có được tin cậy không, có signed inner token nào cần verify không, issuer/purpose/audience/expiry và resource authorization như thế nào. Decryption success không tự cấp quyền.

## 24. Checklist triển khai

- [ ] Phân biệt MAC, chữ ký số, encryption và key agreement theo **mục tiêu bảo mật**.
- [ ] Không coi JWS JWT được mã hóa; payload có thể đọc được.
- [ ] Không dùng hash trần hay hash + secret tự chế thay HMAC chuẩn.
- [ ] HS256 secret phải có entropy đủ, do CSPRNG sinh và lưu an toàn.
- [ ] Nhận thức HS256 verifier có secret cũng có thể tạo MAC hợp lệ.
- [ ] AS giữ private signing key; RS nhận public JWKS khi dùng asymmetric signature.
- [ ] Không xuất private signing key, private JWK hoặc symmetric `oct` key trên public JWKS.
- [ ] Tách keys cho issuer signing, encryption, client assertion, DPoP và mTLS.
- [ ] JWKS URI/issuer lấy từ nguồn tin cậy qua HTTPS, không do token header quyết định.
- [ ] `alg` được allowlist, có key type/use tương thích; từ chối `none`/algorithm confusion.
- [ ] `kid` chỉ chọn key trong trusted key set, không được dùng làm path/URL.
- [ ] Không fetch `jku`/`x5u`/embedded `jwk` tùy ý từ untrusted JWT.
- [ ] Verify signature/MAC trước khi dùng claims; Base64 decode không phải verify.
- [ ] RS kiểm issuer, audience, expiry/nbf, purpose, scope, principal, tenant và object policy.
- [ ] Không nhận OIDC ID token/client assertion/refresh token thay access token.
- [ ] AS phát scopes/claims theo client/grant/consent/resource policy, không copy quyền tự khai.
- [ ] JWE và AEAD dùng thư viện chuẩn; kiểm nonce uniqueness và authentication tag.
- [ ] Khi cần cả encryption và signature, áp nested/provenance validation theo profile.
- [ ] RSA/EC/EdDSA key size và algorithms phù hợp security policy, không dùng RSA 1024-bit.
- [ ] Private key/secrets ở KMS/HSM/Secret Manager hoặc cơ chế tương đương có RBAC/audit.
- [ ] Production và test không dùng chung private signing key.
- [ ] Rotation có prepublish K2, switch signer, bounded overlap K1 và retirement sau expiry nếu không compromise.
- [ ] Khi key bị compromise, có playbook emergency key cutoff, revocation và reissue.
- [ ] Không tắt signature/issuer/audience/time validation vì JWKS outage.
- [ ] Bảo vệ bearer access token khỏi bị lấy/replay: TLS, storage, TTL, revocation/state và sender proof nếu có.
- [ ] DPoP/mTLS proof có kiểm key binding, HTTP method/URI, freshness và replay policy.
- [ ] Không cấp quyền tenant/object chỉ vì token có signature đúng.
- [ ] Không ghi private key, HMAC secret, token thô hoặc client credentials vào logs/metrics/traces.
- [ ] Có negative tests alg confusion, kid injection, token substitution, wrong issuer/audience, rotation/outage và ACL.
- [ ] Khi signer/key/token trust không xác định, hệ thống **fail closed**.

**Ghi nhớ:** **Symmetric key** dùng chung secret nên bên biết khóa để verify HMAC cũng có thể tạo MAC. **Asymmetric key pair** cho phép AS giữ private signing key và RS xác minh bằng public key, tách quyền ký khỏi quyền kiểm. **JWS bảo vệ integrity và xác minh nguồn theo trust model, không mã hóa payload; JWE bảo vệ confidentiality nhưng không tự cấp quyền hoặc chứng minh issuer signature.** Dù dùng thuật toán nào, RS vẫn phải kiểm **issuer, audience, thời gian, token purpose, scope, tenant và quyền trên tài nguyên**. Key rotation, an toàn khóa, token storage, replay defense và revocation là các lớp bảo vệ bổ sung.

## 25. Tài liệu chuẩn và tham khảo

- **RFC 7515 — JSON Web Signature (JWS):** protected headers, signing input, compact serialization và signature verification.
- **RFC 7516 — JSON Web Encryption (JWE):** compact serialization, key management, content encryption và authentication tag.
- **RFC 7517 — JSON Web Key (JWK):** `kty`, `kid`, `use`, `key_ops` và public/private key parameters.
- **RFC 7518 — JSON Web Algorithms (JWA):** `HS256`, `RS256`, `PS256`, `ES256`, `RSA-OAEP`, `A256GCM` và key/algorithm parameters.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `nbf` và JWT claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm confusion, issuer/audience validation, `typ` và cross-JWT confusion.
- **RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE:** `OKP`, Ed25519/EdDSA và related profiles.
- **RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA):** Ed25519/Ed448.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `at+jwt`, access token claims và RS verification.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client/grant/access-refresh token/scope và AS/RS roles.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token replay, theft và RS authentication challenges.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** OAuth token/authorization security và replay mitigations.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque access token metadata và server-side state.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke token/grant lifecycle.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** client JWT assertions và key roles.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWT, sender binding và replay checks.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client/key usage.
- **OpenID Connect Core 1.0 / Discovery 1.0:** ID token verification, issuer/JWKS metadata và client trust.
- **NIST SP 800-57 — Recommendation for Key Management:** key generation, protection, cryptoperiod, rotation/retirement.
- **NIST SP 800-131A — Transitioning the Use of Cryptographic Algorithms and Key Lengths:** cryptographic algorithm/key-strength transitions.
- **OWASP JSON Web Token Cheat Sheet / Cryptographic Storage Cheat Sheet / Key Management Cheat Sheet:** JWT/key validation, secure storage và rotation.
- **Spring Security Reference — OAuth2 Resource Server JWT:** `NimbusJwtDecoder`, JWKS, issuer/audience validators và authorities.
- **Spring Authorization Server Reference:** JWKSource, token signing/issuance và OAuth/OIDC server profiles.

