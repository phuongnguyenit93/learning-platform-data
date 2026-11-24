# Xử lý token không giải mã được

Một dịch vụ nhận được token được bảo vệ bằng mã hóa nhưng **không giải mã được**. Đây có thể là token bị sửa, token gửi sai bên nhận, khóa giải mã chưa được đồng bộ, lỗi thuật toán hoặc sự cố KMS/HSM. Dù nguyên nhân nào, quy tắc bất biến là: **không thể xác minh nội dung bảo mật theo hợp đồng thì không được tạo danh tính đã xác thực hoặc cấp quyền từ token đó**. Tuy nhiên, **từ chối an toàn** không đồng nghĩa với việc coi mọi lỗi là “token giả”: kỹ sư cần phân biệt lỗi token/crypto với lỗi hạ tầng để xử lý, theo dõi và phục hồi đúng.

Ví dụ một authorization server (AS) phát **JWE encrypted access token** cho `orders-api`. Resource server (RS) giữ private decryption key trong KMS/HSM hoặc protected key store. Client gửi:

```http
GET /v1/orders/fixture-42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer ENCRYPTED_ACCESS_TOKEN_TEST_ONLY
Accept: application/json
```

Nếu RS không tìm được decryption key hoặc AES-GCM authentication tag không hợp lệ, RS **không được bỏ qua decrypt**, tự đọc Base64 claims, cho request vào controller với `sub` đoán từ header hoặc mặc định “trusted client”. Kết quả thường là **không xác thực token** và phản hồi `401 invalid_token` theo Bearer API contract. Nếu **KMS unavailable** khiến RS không thể kiểm token dù token có thể hợp lệ, RS vẫn **không cấp quyền**, nhưng có thể trả lỗi phụ thuộc dịch vụ như `503` theo hợp đồng, đồng thời tạo alert có thể điều tra.

```text
Incoming Bearer credential
          |
          v
Is this an expected JWE token for this endpoint/profile?
          |
         YES
          |
          v
Validate JWE structure + approved alg/enc + trusted recipient key ID
          |
          v
Obtain authorized decryption key or call KMS/HSM
          |
          +-- wrong/unknown key, malformed ciphertext, invalid tag
          |       -> token rejected; no principal
          |
          +-- key service unavailable / permission misconfiguration
          |       -> fail closed; classify infrastructure/security fault
          |
          v
Authenticated decryption completes successfully
          |
          v
Validate inner signature if required by profile
          |
          v
Validate issuer, audience, type, expiry, scope, sender and resource policy
          |
          +-- any check fails -> deny
          |
          v
Authorized API action (if all checks pass)
```

**Không phải mọi token đều được giải mã tại RS:** JWT dạng **JWS** là token có chữ ký, thường có payload đọc được nhưng phải **verify signature**; **opaque token** là reference credential được kiểm bằng introspection hoặc token store, không phải một JWE để RS thử decrypt. Lỗi `JWE decryption` khác lỗi `JWS signature validation`, lỗi `introspection` và lỗi `authorization`; phân biệt này là nền tảng cho đúng HTTP response, giám sát và xử lý sự cố.

Bài thuộc chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Module tìm hiểu mô hình tin cậy và vòng đời JWT/opaque token, access/refresh token trong xác thực, phân quyền và OAuth 2.0/OIDC; phát hành, kiểm claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại. Chủ đề trực tiếp ở đây là **“Xử lý token không giải mã được”**, với trọng tâm quyết định từ chối, phân loại nguyên nhân, mã hóa có xác thực, quản lý khóa, khả năng phục hồi và kiểm thử end-to-end.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **JWE encrypted JWT**, **JWS signed JWT**, **nested JWT** và **opaque token**, biết lúc nào RS/RP thực sự cần giải mã.
2. Mô tả **JWE Compact Serialization** gồm năm phần, vai trò `alg`, `enc`, `kid`, protected header, IV/nonce, ciphertext và authentication tag.
3. Giải thích vì sao **mã hóa thành công chưa chắc xác thực issuer**, và vì sao **không giải mã được thì không thể lấy claims làm căn cứ cấp quyền**.
4. Phân loại lỗi: malformed token, unsupported algorithm, unknown key, wrong recipient, corrupted ciphertext, invalid AEAD tag, key rotation gap, KMS outage và key policy denied.
5. Thiết kế **fail-closed behavior** và response phù hợp: API 401 `invalid_token`, 403 authorization denial, 503 dependency outage khi được quy định; RP login không tạo session.
6. Tránh **decryption oracle**, timing/error leakage, retry vô hạn, fallback yếu, tải khóa từ JWT header không đáng tin và log raw token.
7. Thiết kế **recipient key management, trusted JWK/JWKS, KMS/HSM**, prepublish và rotation có overlapping decrypt window.
8. Triển khai với **Java/Nimbus JOSE + JWT** và Spring Security bằng các lớp validation và exception mapping rõ ràng.
9. Kiểm thử trạng thái **trước/sau key rotation**, tampered tag, mixed token types, invalid claims và outage, với positive/negative control fixtures.
10. Viết runbook điều tra production khi tỷ lệ “cannot decrypt token” tăng mà không làm lộ credentials hoặc bỏ qua security policy.

## 2. Trước hết: token nào cần decrypt?

| Loại credential | Mục đích chính | Cách kiểm phù hợp | Khi nào có lỗi “không giải mã được”? |
| --- | --- | --- | --- |
| **JWS JWT access token** | AS ký, RS verify | JWS signature + issuer/audience/type/time/scope | Thường **không decrypt**; lỗi là signature/parser/claims |
| **JWE encrypted access token** | Claims được mã hóa cho một recipient | JWE decrypt/authenticate + token profile validation; inner JWS nếu yêu cầu | Wrong key/alg/enc/tag, corrupted JWE, unavailable decrypt |
| **Nested JWT (JWS rồi JWE)** | Issuer authentication + confidentiality | Decrypt outer JWE, verify inner JWS, validate claims | Outer decrypt failure hoặc inner signature/claims failure |
| **Opaque access token** | Reference credential không tự chứa claims công khai | AS introspection RFC 7662 hoặc lookup tin cậy | Không nên thử decrypt nếu không phải format đã định |
| **Refresh token** | Client trao đổi tại AS token endpoint | AS xác minh client/grant/family, lưu trữ/rotation | Có thể opaque hoặc encrypted theo provider; **RS API không nhận** |
| **OIDC ID token dạng JWS** | RP xác minh authentication result | Verify OP signature và OIDC claims/nonce | Không decrypt nếu chỉ là JWS |
| **OIDC encrypted ID token** | OP gửi ID token bảo mật cho RP | RP decrypt bằng registered key, sau đó kiểm signature/claims theo profile | RP decryption failure → login không hoàn thành |
| **DPoP proof JWT** | Chứng minh sender key cho request cụ thể | Verify asymmetric JWS + method/URL/ath/jti/nonce | Không phải encrypted access token |

**Không được thử tất cả các cách** theo kiểu “JWE decrypt thất bại thì thử parse JWS, rồi cuối cùng thử opaque introspection”. Điều này có thể tạo **token confusion/downgrade**: một token không hợp lệ đối với profile A lại được chấp nhận qua profile B. Nếu một API thực sự hỗ trợ nhiều token formats, việc chọn validation path phải dựa trên **trusted endpoint/issuer/resource contract và routing policy**, không do header `alg` hay lỗi ở path trước đó quyết định tùy tiện.

### 2.1. JWS không mã hóa payload

JWS Compact có **ba phần**:

```text
BASE64URL(protected_header).BASE64URL(payload).BASE64URL(signature)
```

Payload thường có thể đọc bằng Base64url decoding. **Đọc được không có nghĩa tin được**. Một API tuyệt đối không được parse `sub`/`role` rồi tạo principal khi chưa verify trusted issuer signature và policy.

### 2.2. JWE chứa dữ liệu mã hóa có xác thực

JWE Compact có **năm phần**:

```text
BASE64URL(protected_header)
.
BASE64URL(encrypted_key)
.
BASE64URL(initialization_vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
```

Với một số chế độ key-management như `dir` hoặc `ECDH-ES` trực tiếp, phần `encrypted_key` có thể **rỗng** theo chuẩn; điều đó **không tự có nghĩa token bị cắt hỏng**. Hãy để thư viện JOSE parse theo thuật toán/profile thay tự kiểm “mọi phần phải không rỗng”.

### 2.3. Opaque token không “có cấu trúc JWE ẩn”

Opaque token có thể là chuỗi random, một handle có cấu trúc riêng hoặc một format chỉ AS hiểu. Resource server dùng **hợp đồng introspection/lookup**; không được tự thử “AES decrypt” bằng mọi key vì không biết token có thực sự được mã hóa hay không. Cần bảo vệ token trong transit/storage và không log raw bearer credential.

## 3. Mô hình bên gửi, bên giải mã và bên xác minh

Giả sử OP/AS mã hóa một token cho RS:

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant KEYS as Recipient Key Registry
    participant C as OAuth Client
    participant RS as Resource Server
    participant KMS as KMS/HSM (recipient private key)
    AS->>KEYS: Fetch registered RS encryption public key
    KEYS-->>AS: Approved public JWK K1 + alg/enc policy
    AS->>AS: Build claims, sign inner JWT if profile requires
    AS->>AS: Encrypt JWE to RS public K1
    AS-->>C: Encrypted access token
    C->>RS: Authorization: Bearer JWE
    RS->>RS: Validate expected JWE profile and kid
    RS->>KMS: Authorized decrypt/unwrap operation
    KMS-->>RS: Decryption result or failure
    RS->>RS: Verify inner issuer signature if required
    RS->>RS: Validate iss, aud, exp, scope, tenant, revocation
    RS-->>C: 200 if authorized; otherwise deny
```

**Tách hai tập khóa khi có nested JWT:**

- **Encryption public key của recipient RS/RP** được AS/OP dùng mã hóa; **private decryption key của recipient** cần được giữ an toàn.
- **Signing private key của issuer AS/OP** được dùng tạo inner JWS; **signing public JWKS của issuer** được RS/RP dùng kiểm issuer authenticity.

Không trộn **issuer signing JWKS** với **recipient encryption JWKS**, không cho untrusted token chọn nguồn khóa. Một JWE được tạo bằng public encryption key của RS có thể do nhiều người mã hóa, không tự chứng minh **AS có quyền phát token**.

### 3.1. Trust boundaries quan trọng

1. **AS → recipient key registry:** AS chỉ tin encryption public key đã đăng ký cho đúng recipient/client/RS.
2. **Client → RS:** client vận chuyển bearer token; client không được quyền chỉ định key/algorithm mà RS tin.
3. **RS → KMS/HSM:** workload identity được phép decrypt đúng key/tenant/profile, có audit và rate limits.
4. **RS → issuer trust:** sau decrypt, RS kiểm inner JWS hoặc authentication mechanism theo token profile.
5. **RS → data:** `aud`/`scope`/resource ownership vẫn phải được kiểm; decrypt không cấp quyền tự động.
6. **RS → logs/telemetry:** không tiết lộ ciphertext token, plaintext, secret, failure details có thể tạo oracle.

## 4. JWE protected header: xử lý trước khi giải mã

Một JWE header giả định:

```json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-encryption-2026-a",
  "cty": "JWT"
}
```

| Trường | Vai trò | Kiểm cần có |
| --- | --- | --- |
| **`alg`** | Key management/key agreement, ví dụ `RSA-OAEP-256` | Phải nằm trong allowlist cho recipient/token profile |
| **`enc`** | Content encryption/AEAD, ví dụ `A256GCM` | Phải đúng phương thức, CEK size, IV/tag profile |
| **`kid`** | Key ID trong recipient key registry | Chỉ là selector, không là trust anchor |
| **`cty`** | Content type, thường `JWT` cho nested JWT | Kiểm đúng inner representation/profile khi áp dụng |
| **`typ`** | Media/type hint cho token theo profile | Không thay issuer/audience/signature validation |
| **`crit`** | Critical header parameters | Từ chối nếu không hiểu/không được profile hỗ trợ |
| **`zip`** | Compression parameter khi profile cho phép | Không bật tùy tiện vì rủi ro resource amplification/leakage |

**`alg` của JWE không phải `alg` của JWS.** `RSA-OAEP-256` là key management algorithm cho content encryption key (CEK), không phải chữ ký `PS256`. **`enc=A256GCM`** dùng CEK 256 bit và AES-GCM authenticated encryption, không phải “RSA ký + AES”.

### 4.1. Không tin header trước khi xác minh

Header được đọc trước khi decryption, nên attacker có thể sửa `alg`, `enc`, `kid`, `zip` hoặc `cty`. Có thể parse các trường để **kiểm chúng có khớp policy cố định hay không**, nhưng không dùng header tự khai để **mở quyền**:

```text
GOOD:
  profile = trustedOrdersJweProfile()
  require header.alg == RSA-OAEP-256
  require header.enc == A256GCM
  key = trustedRecipientKeyRegistry.require(header.kid)
  require key belongs to orders-api, suitable for decrypt

BAD:
  key = download(header.jku)
  algorithm = chooseWhateverHeaderSays(header.alg)
  disableTagCheckIfDecryptionFails()
```

**Không fetch `jku`/`x5u` tùy ý** từ unverified header. Với recipient key, `kid` phải map trong kho khóa tin cậy của chính recipient. Nếu key ID không tồn tại, không thử quét mọi key/private key ở mọi tenant.

### 4.2. Cần giới hạn độ dài token và parser complexity

Trước khi chạy asymmetric decrypt (tốn CPU/HSM quota), áp dụng:

- Max HTTP header/token size theo API contract.
- Max JWE nesting/decompression depth và payload size.
- Strict compact serialization/JSON parser, duplicate parameter/unsupported critical headers.
- Fixed allowed algorithms, key IDs và tenant context.
- Rate limits/malicious input controls để ngăn flood `kid`/decrypt calls.

Không giải nén `zip` không giới hạn hoặc chuyển ciphertext thành log để debug parser failure.

## 5. Phân loại “không giải mã được”: sáu nhóm nguyên nhân

### 5.1. Nhóm A — Token sai cấu trúc/không phải JWE

Ví dụ: chuỗi chỉ có ba phần của JWS, JSON rác, Base64url malformed, JWE header duplicate, IV/tag sai độ dài.

**Diễn giải:** Không phải JWE hợp lệ theo profile. **Hành vi:** Reject sớm, không truy cập KMS nếu parser đủ xác định input sai, không thử decode payload thành principal.

### 5.2. Nhóm B — Sai recipient hoặc không có decryption key đúng

JWE mã hóa cho `payments-api` được gửi tới `orders-api`, `kid` không thuộc trusted keys hoặc recipient đã rotate key nhưng một node RS chưa nhận K2.

**Diễn giải:** Có thể là token gửi nhầm, lỗi key distribution hoặc key substitution attack. **Hành vi:** Không dùng key của tenant/issuer khác, bounded key refresh chỉ từ trusted registry; không fallback sang token plaintext.

### 5.3. Nhóm C — Thuật toán hoặc key parameters không phù hợp

Header `alg=RSA1_5` trong khi policy chỉ cho `RSA-OAEP-256`; `enc` không được hỗ trợ; EC key sai curve; KMS key usage `sign` bị dùng để `decrypt`.

**Diễn giải:** Mismatch hoặc downgrade attempt. **Hành vi:** Reject trước decrypt khi có thể, không “thử thuật toán khác cho tới khi ra plaintext”.

### 5.4. Nhóm D — Ciphertext, IV hoặc tag bị hỏng

Một byte ciphertext/tag bị thay, IV sai hoặc key không khớp có thể làm AEAD authentication fail. Với AES-GCM, **không được đưa plaintext ra application trước khi authentication tag hợp lệ**.

**Diễn giải:** Không thể xác định tin cậy liệu do mạng, cache, tamper, key mismatch hay bug serialization. **Hành vi:** Reject và ghi reason code tổng quát; không phơi bày chi tiết phân biệt padding/tag/key.

### 5.5. Nhóm E — Key service không khả dụng

KMS timeout, HSM session exhausted, 429 throttling, 5xx, không có workload identity/permission, key disabled hoặc region outage.

**Diễn giải:** Không được suy token giả chỉ từ KMS unavailable. **Hành vi:** **Fail closed** (không tạo principal), phân loại lỗi hạ tầng, bounded retry/backoff hoặc fallback **chỉ tới key-service path đã phê duyệt**, có thể trả 503 theo API contract.

### 5.6. Nhóm F — Decrypt xong nhưng token vẫn không hợp lệ

Outer JWE giải mã thành công nhưng inner JWS signature sai, `iss`/`aud` không khớp, token hết hạn, thiếu scope, account bị khóa, grant revoked, DPoP/mTLS proof sai.

**Diễn giải:** **Không phải decryption failure**. Hãy tách crypto layer khỏi issuer verification/authorization layer; HTTP 401/403 tùy lý do và endpoint contract.

### 5.7. Ma trận lỗi nhanh

| Triệu chứng | Lớp phát sinh | Kết quả an toàn |
| --- | --- | --- |
| `JWEObject.parse` lỗi | Parse/profile | Invalid token, không decrypt |
| Unknown `kid` | Recipient key selection | Không dùng arbitrary key, bounded refresh |
| `alg`/`enc` không allowed | Algorithm policy | Reject trước decrypt |
| AEAD tag invalid | Cryptographic authentication | Reject, không lấy plaintext |
| Wrong recipient private key | Key management | Reject; kiểm key registry/rotation |
| KMS IAM denied | Dependency/authz | Fail closed, security alert, không thử private key local |
| KMS timeout/5xx | Infrastructure | Fail closed, 503/deny theo contract, retry có hạn |
| Inner JWS invalid | Issuer authentication | Reject dù decrypt thành công |
| Valid inner JWS, expired `exp` | Claims validation | Invalid token |
| Valid token, thiếu scope | API authorization | 403/deny, không quy nhầm decrypt |

## 6. HTTP response: từ chối đúng mà không tạo oracle

API có Bearer authentication thường sử dụng **RFC 6750**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

Đây là **một cách biểu diễn hợp lệ**, không phải body/status duy nhất trong mọi framework. Với token mã hóa sai/không thể xác minh, 401 thường phù hợp. Với token đã được xác minh nhưng không đủ `scope`, API thường trả **403 `insufficient_scope`**. Với dependency KMS/AS lỗi dẫn tới không thể quyết định, có thể trả **503 Service Unavailable** theo hợp đồng vận hành, nhưng **không cấp quyền**.

| Tình huống | Điều bắt buộc | Response điển hình |
| --- | --- | --- |
| JWE malformed/tampered/tag sai | Không tạo authenticated principal | 401 Bearer `invalid_token` |
| Encryption key không thuộc recipient | Không dùng cross-tenant key | 401/invalid token |
| Inner signature/issuer/audience sai | Không tin claims | 401/invalid token |
| Valid token nhưng thiếu quyền resource | Deny action | 403/`insufficient_scope` hoặc resource policy 403 |
| KMS/RS decrypt service timeout | Fail closed; không “allow” | 503 hoặc 401 theo API contract, có alert |
| RP OIDC encrypted ID token không decrypt | Không tạo login session | Login error/callback failure, không redirect user vào authenticated area |
| OAuth token endpoint nhận refresh token invalid | Không issue access token | OAuth `invalid_grant` theo context |

**Cẩn trọng với response detail:** Không tiết lộ “đúng `kid` nhưng private key sai”, “tag byte thứ 10 sai”, “token của user Alice đã tồn tại” hoặc “bạn phải thử khóa K2”. Lỗi công khai nên thống nhất trong cùng class security invalidity; nội bộ dùng **reason code an toàn** cho troubleshooting.

### 6.1. Không đồng nhất 401 và 403

`401` nói **authentication/token chưa hợp lệ hoặc không được chấp nhận**. `403` thường nói **principal có thể hợp lệ nhưng hành động không đủ quyền**. Nếu JWE không decrypt, chưa xác định principal, nên **không trả 403 chỉ vì app giả định user tồn tại**.

### 6.2. Khi nào 503 phù hợp?

Nếu một request có thể dùng token hợp lệ nhưng KMS không phản hồi, RS không có bằng chứng token invalid; trong một API contract xác định, **503** giúp client biết “dịch vụ tạm chưa thể xác minh”, đồng thời không tiết lộ khóa. Nhưng đừng tự khẳng định mọi framework phải trả 503; mapping phải nhất quán với security policy và observability. **Không dùng 503 để cho request đi tiếp tới controller**.

### 6.3. Retry ở client không tự giải quyết token invalid

Với 401 `invalid_token` do tag sai, client cần **không gửi lại cùng token liên tục**. Tùy OAuth client, có thể refresh/reauth theo grant hợp lệ, nhưng **không blind retry vô hạn hoặc nộp refresh token tại RS**. Với 503, client có thể retry bounded với jitter/backoff; không retry tạo token mới ngoài transaction semantics.

## 7. AEAD: authentication tag là ranh giới bắt buộc

AES-GCM và các AEAD constructions cung cấp **confidentiality và integrity/authenticity đối với dữ liệu theo key/context**. Một JWE với `enc=A256GCM` thường dùng:

- **CEK:** 256-bit content-encryption key (32 byte).
- **IV/nonce:** giá trị theo JOSE profile (thường 96 bit với AES-GCM).
- **AAD:** protected header bytes theo JWE specification.
- **Ciphertext:** nội dung đã mã hóa.
- **Authentication tag:** dữ liệu để phát hiện sửa đổi/tamper (theo JWE AES-GCM thông thường 128 bit).

### 7.1. Decryption không được “xuất plaintext tạm” trước tag

```text
RECEIVE JWE
  -> check allowed alg/enc and length limits
  -> obtain correct CEK/key
  -> AEAD decrypt + authentication tag verification
       |
       +-- fail -> discard all intermediate data; reject
       |
       +-- pass -> plaintext may be parsed under token profile
  -> validate issuer/JWS/claims before authorization
```

Đừng thực thi business action hoặc đọc `sub` để tạo session từ plaintext chưa authenticated. Với streaming crypto, phải hiểu khi nào provider bảo đảm tag đã được xác minh; dùng JOSE SDK thay thủ công.

### 7.2. Không tái sử dụng key–nonce với AES-GCM

**Reuse cùng nonce/IV với cùng CEK/key** có thể gây lỗi nghiêm trọng về bí mật/toàn vẹn. Token decrypt failure có thể bắt nguồn từ implementation encryption dùng sai nonce/IV/CEK. **Không “sửa” lỗi bằng cách bỏ tag** hoặc tái sử dụng một IV cố định để các node “đồng bộ”.

### 7.3. Header có được bảo vệ không?

JWE protected header đóng vai trò **authenticated additional data** trong cấu trúc JWE; đổi `alg`/`enc`/`kid` theo cách làm sai cấu trúc thường làm quá trình kiểm tag/decrypt không thành công, nhưng **header vẫn là dữ liệu chưa tin trước khi verification**. Vì vậy cần check allowlist/key mapping trước khi chi phí decrypt và chỉ tin token sau khi cryptographic validation hoàn tất.

### 7.4. JWE giải mã được chưa chắc xác thực issuer

Ai có public encryption key của RS có thể **mã hóa** nội dung cho RS. Vì thế đối với encrypted access/ID tokens yêu cầu issuer authentication, kiến trúc thường dùng **signed-then-encrypted JWT (nested)** hoặc một profile khác có issuer authentication được chỉ rõ. **Không dùng việc decrypt thành công làm bằng chứng OP/AS đã phát token**, kể cả khi key được KMS bảo vệ.

## 8. Rotation: không decrypt được vì khóa cũ/mới lệch nhau

Một trong các nguyên nhân production thường gặp là **recipient encryption key rotation** chưa được điều phối:

```text
T0: RS holds private K1; AS encrypts to public K1.
T1: RS generates private K2; publishes public K2 to trusted AS registry.
T2: AS starts encrypting new tokens to K2.
T3: RS decrypts new K2 tokens; still decrypts eligible unexpired K1 tokens.
T4: After maximum old-token lifetime + in-flight/cache/skew window,
    RS stops accepting K1 per planned retirement policy.
```

**Đối với encryption key rotation, nơi cần giữ public/private key khác signing key rotation:**

- **AS/OP** cần **public recipient encryption key K2** trước khi mã hóa token mới.
- **RS/RP** cần **private decryption key K2** trước khi nhận JWE K2.
- **RS/RP** thường cần giữ **private K1 để decrypt token cũ** trong bounded overlap nếu planned rotation.
- Khóa issuer **signing** dùng cho inner JWS có vòng đời riêng.

### 8.1. Timeline biểu diễn key states

| Giai đoạn | AS encrypts new tokens | RS can decrypt | Policy |
| --- | --- | --- | --- |
| K1 active | Public K1 | Private K1 | Bình thường |
| K2 prepared | Vẫn public K1 | Private K1 + K2 provisioned | Prepublish K2 |
| K2 cutover | Public K2 | Private K1 + K2 | Overlap có giới hạn |
| K1 retired | Chỉ public K2 | Private K2 | K1 no longer accepted |
| K1 compromise | Stop affected K1 usage immediately | Emergency policy | Không chờ normal overlap |

### 8.2. Không xóa K1 quá sớm

Nếu AS mới chuyển encrypt sang K2 nhưng client còn giữ JWE K1 chưa hết hạn, RS xóa K1 lập tức có thể tạo **401 hàng loạt**. Đó là *availability/correctness* problem, không phải dấu hiệu mọi token bị giả. Planned rotation nên dựa trên **max token TTL, issuance cutoff, clock skew, cache/in-flight request duration và distribution**.

### 8.3. Không giữ K1 vô hạn

Giữ private old keys mãi làm tăng attack surface và rủi ro confidentiality nếu key bị lộ. Cần **thời điểm retire rõ**, monitoring token dùng old `kid`, reject after deadline và cleanup KMS/HSM key states/backups theo retention policy.

### 8.4. Compromise khác planned retirement

Nếu **recipient private K1 bị lộ**, attacker có thể giải mã những ciphertext JWE đã thu được nếu có đầy đủ token và key thích hợp. **Xóa K1 khỏi public key registry không làm ciphertext trong quá khứ bí mật trở lại**. Cần security incident response: xác định dữ liệu/token bị lộ, ngừng encrypt mới tới K1, thu hồi/reissue tokens và xem xét logs/backups/captured traffic. Đó là rủi ro khác với **issuer private signing key leak**, nơi attacker có thể forge JWS.

### 8.5. Key version/kid mismatch

Đừng để JWE header ghi `kid=K1` trong khi AS thực tế mã hóa tới **public K2** do alias vừa đổi. Token sẽ không decrypt nếu RS chọn K1 theo header. Bắt buộc **atomic mapping** recipient key ID ↔ public key ↔ encryption operation và tests khi rotate đồng thời ở nhiều nodes.

## 9. KMS/HSM trong decryption path

Một RS có thể dùng:

1. **Private key handle qua JCA/PKCS#11**, JOSE library gọi decrypt mà private key không xuất khỏi HSM.
2. **Remote KMS Decrypt/Unwrap API**, adapter lấy CEK hoặc plaintext phù hợp thuật toán/provider contract.
3. **Managed JWE/decryption service** với policy hạn chế recipient/token use và audit.

**Đừng mặc định mọi KMS cung cấp RSA-OAEP-256 decrypt hoặc hỗ trợ mọi JOSE key-management thuật toán**. Cần kiểm **exact key type, operation, padding/hash/label/format, region, IAM và quotas**. Một số KMS chỉ hỗ trợ envelope encryption hoặc key wrapping riêng, không trực tiếp decrypt JWE RSA-OAEP compact.

### 9.1. Key decryption non-exportability và CEK

Với RSA-OAEP key management, KMS/HSM có thể unwrap/decrypt **encrypted key** thành **CEK** để ứng dụng AES-GCM decrypt. Tùy architecture, **CEK vẫn có thể xuất hiện trong RAM của RS**, dù RSA private key non-exportable. Không nói “mọi token plaintext luôn nằm trong HSM” trừ khi giải pháp thực tế đúng như vậy. Bảo vệ RAM/logs/dumps và tránh giữ CEK/token plaintext lâu hơn cần thiết.

### 9.2. IAM sai không đồng nghĩa token invalid

KMS trả **AccessDenied** khi RS workload không có quyền `Decrypt`; đây là **integration/security configuration error**. Không cho request đi tiếp, nhưng cũng không coi đây là cùng loại với tag tamper. Alert và điều tra caller identity/key state, không tự nới `kms:*` cho mọi service để phục hồi nhanh.

### 9.3. KMS unavailable không thể là “bypass authentication”

```java
// ANTI-PATTERN: tuyệt đối không dùng.
try {
    return decryptAndValidate(jwe);
} catch (Exception ignored) {
    return AuthenticatedPrincipal.trustedFallback();
}
```

Đây là **fail-open** nghiêm trọng. Lỗi hạ tầng phải được xử lý theo circuit breaker, deadline, retry có hạn và response an toàn; **không tạo authenticated principal** khi không có bằng chứng hợp lệ.

### 9.4. Key separation

| Key | Chủ thể quản lý | Dùng cho |
| --- | --- | --- |
| AS/OP **private signing key** | Issuer | JWS ký token |
| RS/RP **private decryption key** | Token recipient | JWE decrypt |
| RS/RP **public encryption key** | Recipient công bố có kiểm soát | AS/OP encrypt token |
| AS/OP **public signing key** | Issuer công bố qua JWKS | RS/RP verify inner JWS |
| KMS storage **KEK** | Storage owner | Wrap/encrypt DEKs |
| Application **DEK** | Theo encryption architecture | AEAD encrypt/decrypt data at rest |
| HMAC token digest key | AS/token store | Protected opaque token lookup |

Không dùng một khóa RSA cho cả signing và decryption chỉ vì cùng key type, trừ khi profile/hardware có quy trình đặc biệt được review. **Key purpose separation** giảm cross-protocol confusion và blast radius.

## 10. Thiết kế bộ phân loại lỗi nội bộ

Một decryption component nên trả về **kết quả được phân loại** cho authentication boundary, không trả “`null`” và để caller tự đoán null nghĩa là token invalid hay KMS lỗi. Ví dụ domain model **khái niệm**:

```java
enum TokenProcessingFailure {
    MALFORMED_JWE,
    UNSUPPORTED_ALGORITHM,
    UNTRUSTED_RECIPIENT_KEY,
    DECRYPT_AUTHENTICATION_FAILED,
    DECRYPTION_SERVICE_UNAVAILABLE,
    DECRYPTION_PERMISSION_DENIED,
    INVALID_INNER_SIGNATURE,
    INVALID_TOKEN_CLAIMS,
    REVOKED_TOKEN,
    INSUFFICIENT_SCOPE
}
```

Enum trên **không phải OAuth standardized error codes** và không nên được trả nguyên ra client. Nó phục vụ internal logging/metrics, incident triage và test assertions.

### 10.1. Logic quyết định

```mermaid
flowchart TD
    A[Incoming protected endpoint credential] --> B{Expected token format/profile?}
    B -->|No| X[Reject: invalid_token]
    B -->|Yes JWE| C{Parse and policy check OK?}
    C -->|No| X
    C -->|Yes| D{Trusted recipient key available?}
    D -->|Unknown or untrusted kid| X
    D -->|KMS outage or IAM failure| Y[Fail closed: dependency fault]
    D -->|Yes| E{Authenticated decryption succeeds?}
    E -->|No: invalid tag or key| X
    E -->|Yes| F{Inner signature and token claims valid?}
    F -->|No| X
    F -->|Yes| G{Scope, tenant, resource policy allow?}
    G -->|No| Z[403 or policy denial]
    G -->|Yes| H[Authorize API action]
```

### 10.2. Không dùng exceptions làm trust signal

Sai:

```java
// SAI: catch chung làm principal dù chưa có chứng cứ hợp lệ.
try {
    return decrypt(token);
} catch (RuntimeException err) {
    return parseUnverifiedJwtPayload(token).getSubject();
}
```

Đúng về nguyên tắc:

```text
try:
  verifiedClaims = decrypt_then_verify_then_validate(token)
  principal = createPrincipal(verifiedClaims)
  return AUTHENTICATED
catch InvalidToken:
  return DENIED_INVALID_CREDENTIAL
catch TrustedDependencyUnavailable:
  return DENIED_UNVERIFIABLE_DEPENDENCY
catch other unexpected failure:
  return DENIED + SECURITY_ALERT
```

Không có nhánh “retry với `alg=none`”, “dùng plaintext claims”, “skip tag” hoặc “khai báo internal request nên allow”.

### 10.3. Reason code nội bộ và thông báo công khai

| Internal reason | Client-visible behavior | Hành động vận hành |
| --- | --- | --- |
| `MALFORMED_JWE` | Invalid credential | Kiểm parser/client input, tăng rate limit nếu flood |
| `UNSUPPORTED_ALGORITHM` | Invalid credential | Kiểm policy downgrade attempt hoặc issuer mismatch |
| `UNTRUSTED_RECIPIENT_KEY` | Invalid credential | Bounded trusted key refresh; điều tra rotation/tenant |
| `DECRYPT_AUTHENTICATION_FAILED` | Invalid credential | Không leak tag/IV/key details; xem mismatch/tamper |
| `DECRYPTION_SERVICE_UNAVAILABLE` | Không authorize, có thể 503 | KMS/network/quota alert; bounded retry/failover |
| `DECRYPTION_PERMISSION_DENIED` | Không authorize, có thể 503 | IAM/key policy security alert; không cấp quyền mới |
| `INVALID_INNER_SIGNATURE` | Invalid credential | Kiểm issuer signing JWKS và inner token format |
| `INVALID_TOKEN_CLAIMS` | Invalid credential | Kiểm issuer/aud/type/exp/nbf/nonce |
| `REVOKED_TOKEN` | Invalid credential | Kiểm AS grant/revocation consistency |
| `INSUFFICIENT_SCOPE` | 403/deny | Kiểm scope/resource policy; không đổ lỗi decrypt |

**Đừng trả internal reason** như `DECRYPT_AUTHENTICATION_FAILED` hoặc `UNKNOWN_KID_K2` trong JSON public; attacker có thể dùng để dò chìa khóa/recipient. Internal traces cũng phải loại bỏ raw JWT, CEK và plaintext.

## 11. Java/Nimbus JOSE: kiểm profile rồi mới decrypt

**Nimbus JOSE + JWT** là một implementation JOSE thường dùng trong Java/Spring. Ví dụ này dùng **JWE outer RSA-OAEP-256 + A256GCM**, chứa **JWS inner PS256**. Đây là **profile minh họa đã pin trước**, không phải một thuật toán universal cho mọi token.

### 11.1. Kiến trúc component

```text
StrictEncryptedAccessTokenProcessor
  |
  +-- trusted expected token profile: JWE RSA-OAEP-256/A256GCM
  +-- recipientPrivateKeyRegistry: registered K1/K2 only
  +-- Nimbus JWEObject.parse + RSADecrypter
  +-- trusted issuer verifier: nested SignedJWT PS256
  +-- claims validation: iss/aud/typ/exp/scope
  +-- optional revocation/sender binding authorization layer
```

Ví dụ sau gồm **các interfaces domain do ứng dụng triển khai**, không phải toàn bộ Spring Boot application hay class chuẩn có sẵn cho registry. Nó cố ý không chuyển unchecked plaintext thành authenticated principal.

### 11.2. JWE decrypt và inner JWT dispatch

```java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.interfaces.RSAPrivateKey;
import java.text.ParseException;

interface TrustedRecipientKeys {
    // Chỉ lookup trong registry của orders-api, không theo jku/x5u của token.
    RSAPrivateKey requireOrdersDecryptionKey(String kid);
}

interface TrustedIssuerJwtVerifier {
    // Phải verify inner signature, iss, aud, typ, exp, nbf, etc.
    JWTClaimsSet verifyAndValidate(SignedJWT signedJwt);
}

public final class StrictNestedAccessJweProcessor {
    private final TrustedRecipientKeys recipientKeys;
    private final TrustedIssuerJwtVerifier issuerVerifier;

    public StrictNestedAccessJweProcessor(
        TrustedRecipientKeys recipientKeys,
        TrustedIssuerJwtVerifier issuerVerifier
    ) {
        this.recipientKeys = recipientKeys;
        this.issuerVerifier = issuerVerifier;
    }

    public JWTClaimsSet process(String compactJwe) {
        try {
            JWEObject jwe = JWEObject.parse(compactJwe);
            var header = jwe.getHeader();

            if (!JWEAlgorithm.RSA_OAEP_256.equals(header.getAlgorithm())
                || !EncryptionMethod.A256GCM.equals(header.getEncryptionMethod())
                || header.getKeyID() == null
                || header.getKeyID().isBlank()) {
                throw new InvalidProtectedTokenException();
            }
            if (header.getContentType() == null
                || !"JWT".equals(header.getContentType().toString())) {
                throw new InvalidProtectedTokenException();
            }
            if (header.getCriticalParams() != null
                && !header.getCriticalParams().isEmpty()) {
                throw new InvalidProtectedTokenException();
            }

            // Trusted registry phải kiểm key purpose, recipient, environment.
            RSAPrivateKey key = recipientKeys
                .requireOrdersDecryptionKey(header.getKeyID());

            // Authenticated decrypt: sai key/tag/ciphertext => exception.
            jwe.decrypt(new RSADecrypter(key));

            // Không coi plaintext này là claims; profile yêu cầu nested JWS.
            SignedJWT inner = SignedJWT.parse(
                jwe.getPayload().toString()
            );
            return issuerVerifier.verifyAndValidate(inner);
        } catch (ParseException | JOSEException ex) {
            // Không log ex message/raw compact JWE vì có thể tiết lộ metadata.
            throw new InvalidProtectedTokenException();
        }
    }
}

final class InvalidProtectedTokenException extends RuntimeException {
    InvalidProtectedTokenException() {
        super("Invalid protected token");
    }
}
```

**Giới hạn chủ ý của ví dụ:**

- `TrustedRecipientKeys` là abstraction phải phân biệt **unknown/mismatched `kid`** với **KMS outage/IAM denied**. Code đơn giản phía trên minh họa happy-path và `ParseException/JOSEException`; trong production cần catch/map các **domain exceptions của registry/KMS** trước khi đưa ra response.
- Provider-based private key handle có thể không được Nimbus `RSADecrypter` hỗ trợ trực tiếp. Với **remote KMS unwrap**, cần JOSE adapter phù hợp API/algorithm và bảo vệ CEK RAM; không giả định `RSAPrivateKey` exportable hoặc có thể dùng KMS ID làm private key.
- Cần giới hạn input length, total nesting, decompression, key/key-type policy, ciphertext size, parser strictness và rate limit **trước** expensive decryption.
- Nếu `cty=JWT` được chọn là mandatory trong profile này, AS phải thực sự tạo nested JWT; không suy mọi JWE hợp lệ đều bắt buộc có `cty=JWT`.
- `verifyAndValidate` phải kiểm inner trusted issuer signing key, alg, `typ`, claims; **không chỉ parse**.
- Không xuất `JWTClaimsSet` trực tiếp cho controller rồi bỏ authorization. Caller còn phải kiểm scope, tenant, sender proof, grant/revocation theo service contract.

### 11.3. Inner JWS: tách tập ký issuer và khóa giải mã recipient

```java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.time.Instant;
import java.security.interfaces.RSAPublicKey;

public final class Ps256IssuerTokenVerifier
    implements TrustedIssuerJwtVerifier {

    private final JWKSet issuerPublicKeys; // Loaded from PINNED issuer JWKS

    public Ps256IssuerTokenVerifier(JWKSet issuerPublicKeys) {
        this.issuerPublicKeys = issuerPublicKeys;
    }

    @Override
    public JWTClaimsSet verifyAndValidate(SignedJWT inner) {
        try {
            if (!JWSAlgorithm.PS256.equals(inner.getHeader().getAlgorithm())
                || inner.getHeader().getKeyID() == null) {
                throw new InvalidProtectedTokenException();
            }

            JWK jwk = issuerPublicKeys
                .getKeyByKeyId(inner.getHeader().getKeyID());
            if (!(jwk instanceof RSAKey rsaJwk)) {
                throw new InvalidProtectedTokenException();
            }
            RSAPublicKey publicKey = rsaJwk.toRSAPublicKey();
            if (publicKey.getModulus().bitLength() < 3072
                || !inner.verify(new RSASSAVerifier(publicKey))) {
                throw new InvalidProtectedTokenException();
            }

            JWTClaimsSet claims = inner.getJWTClaimsSet();
            Instant now = Instant.now();
            if (!"https://id.example.test".equals(claims.getIssuer())
                || !claims.getAudience().contains("orders-api")
                || claims.getExpirationTime() == null
                || !claims.getExpirationTime().toInstant().isAfter(now)
                || (claims.getNotBeforeTime() != null
                    && claims.getNotBeforeTime().toInstant().isAfter(now))) {
                throw new InvalidProtectedTokenException();
            }
            // Profile-specific checks still required:
            // header typ=at+jwt, client/subject, expected claims and scope,
            // sender binding and resource-level authorization/revocation.
            return claims;
        } catch (Exception ex) {
            throw new InvalidProtectedTokenException();
        }
    }
}
```

**Đây là ví dụ lớp xác minh, chưa là production-ready RS.** Cần trust issuer/key namespace, JWK key usage/alg consistency, critical header handling, token type `at+jwt`, max lifetime/skew, scope/tenant/resource-level authorization và detailed safe audit. Việc `catch (Exception)` tại *rìa xác minh issuer* không được áp dụng cho **KMS dependency outages** phía decrypt; các lỗi đó cần phân loại riêng và không bị che mất thành “tên `kid` không đúng”. Chọn RSA-3072 là **organization policy example**; JWA minimum cho RSA JWS là 2048 bit.

### 11.4. Tránh code tự thử nhiều keys

```java
// ANTI-PATTERN: không dùng cho attacker-controlled token.
for (PrivateKey key : allTenantsAndAllOldKeys) {
    try {
        return decryptJweWith(key, compactJwe);
    } catch (Exception ignored) {
        // Keep trying.
    }
}
return allowAsLegacyOpaqueToken(compactJwe);
```

Đây vừa là **cross-tenant key confusion**, vừa có thể tạo **timing/key existence oracle, CPU/KMS DoS và downgrade**. Đúng hơn là dùng `kid` làm *selector trong trusted recipient namespace*, pin token profile và reject khi không có key phù hợp. Nếu một profile legacy không có `kid`, cần phương án migration đã review và **tập key bounded**, không quét mọi khóa production.

## 12. Spring Security: JWE không tự thành JWT Resource Server

Spring Security `oauth2ResourceServer().jwt()` thường xử lý **signed JWT/JWS** theo cấu hình `JwtDecoder`; **không được mặc định giả định** nó tự giải mã mọi JWE compact hoặc tự verify nested JWS. Điều này phụ thuộc framework version, decoder/JOSE integration và customization.

### 12.1. Kiến trúc với custom trusted decoder

```text
BearerTokenAuthenticationFilter
       |
       v
StrictEncryptedJwtDecoder (custom adapter)
       |
       +-- enforce compact JWE profile + size limits
       +-- trusted recipient key + KMS/HSM decrypt
       +-- verify inner JWS against issuer JWKS
       +-- validate iss/aud/typ/exp/nbf
       |
       v
Verified Jwt / Authentication token
       |
       v
Spring Security authorization rules + service-layer tenant policy
```

**Không nên** tự tạo Spring `Jwt` bằng cách `Jwt.withTokenValue(encryptedToken).claims(parsedUntrustedClaims)` trước khi verify/decrypt. Nếu adapter trả `Jwt`, **mọi claim đã phải qua trust/crypto/token validation** trước khi framework chấp nhận.

### 12.2. Fragment cấu hình Spring Security

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersJweResourceServerSecurity {
    @Bean
    SecurityFilterChain resourceApi(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                Customizer.withDefaults()));
        return http.build();
    }
}
```

**Fragment này chỉ cho thấy resource-server authorization filter.** Nó **không tự bật JWE decrypt**. Phải cung cấp một **custom `JwtDecoder`/authentication provider** đã decrypt outer JWE, verify inner JWS và validate claims đúng profile; Spring `jwt()` không thay logic đó. Cần kiểm phiên bản, error mapping, CSRF/session model và audience/tenant validation ở resource layer.

### 12.3. `JwtDecoder` domain contract (pseudocode)

```java
// PSEUDOCODE - triển khai framework adapter dựa trên Spring version.
final class StrictEncryptedJwtDecoder /* implements JwtDecoder */ {
    VerifiedJwt decode(String bearerValue) {
        requireSizeAndExpectedFormat(bearerValue);
        var jwe = trustedJweProcessor.decryptAndVerifyInnerJwt(bearerValue);
        requireIssuerAudienceTypeAndLifetime(jwe);
        return createVerifiedFrameworkJwt(jwe);
    }
}
```

Trong implementation thực, `JwtDecoder.decode` trả `Jwt` hoặc throw `JwtException` theo Spring contract. **Các lỗi hạ tầng như KMS unavailable phải được biểu diễn/catch riêng để auth boundary fail closed**, có thể custom `AuthenticationEntryPoint`/security exception handling trả 503 theo API contract. Spring Security filter exceptions **không nhất thiết** được xử lý bởi `@ControllerAdvice` của MVC controller; test filter-chain response thực tế.

### 12.4. Spring Opaque Token là đường khác

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: TEST_ONLY_PLACEHOLDER
```

Với opaque bearer token, RS dùng `OpaqueTokenIntrospector` theo AS contract, không thử decrypt như JWE. Introspection `active=false` không có authenticated principal; `active=true` vẫn cần audience/type/scope/policy. **Không cấu hình song song JWT và opaque rồi fallback tùy ý** nếu security profile chưa định nghĩa token routing an toàn.

### 12.5. AuthenticationEntryPoint và lỗi công khai

Với JWE invalid, Spring Bearer authentication layer có thể tạo:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Với KMS outage, custom exception translation có thể trả `503` (theo service contract) nhưng phải xác minh **không có authenticated SecurityContext**, controller **không chạy business operation**, và log/response không lộ raw token hoặc key details.

## 13. OIDC: encrypted ID token không decrypt → không đăng nhập

Trong OIDC, RP có thể đăng ký yêu cầu OP mã hóa ID token tới **public encryption key của client/RP** theo negotiated `id_token_encrypted_response_alg` và `id_token_encrypted_response_enc`. Khi RP nhận JWE nhưng **không decrypt được**:

1. Không parse claims `sub`/`email` từ ciphertext hay một payload chưa xác minh.
2. Không tạo authenticated local session hoặc link account.
3. Kiểm expected issuer/client registration và **đúng private decryption key/version**.
4. Nếu outer decrypt được, xác minh ID token signature/claims/nonce theo OIDC profile trước login.
5. Trả login failure user-friendly, không hiển thị `kid`/KMS errors hay raw ID token.
6. Nếu nguyên nhân key rotation/config, khôi phục registration/key distribution theo runbook; **không tắt ID token encryption tùy tiện** cho một client vốn yêu cầu encrypted responses.

### 13.1. Ví dụ trường hợp RP đổi khóa sai thứ tự

```text
RP generated new K2 and deleted K1 private.
OP still encrypts ID tokens to public K1 from registered client JWKS.
RP callback receives JWE kid=K1.
Decrypt fails -> login failure.
```

Giải pháp không phải bypass decryption. RP phải **công bố/đăng ký K2 đúng quy trình, phối hợp OP switch, giữ K1 trong bounded overlap** nếu planned rotation và policy cho phép. Nếu K1 compromise, cần ưu tiên incident policy chứ không ép giữ khóa nguy hiểm vì UX login.

### 13.2. OIDC nonce và account binding

Decrypt thành công nhưng `nonce` sai, `aud` khác client ID, `iss` lạ hoặc `exp` hết hạn thì **không đăng nhập**. Bảo mật local account liên kết theo (`iss`, `sub`) hoặc trusted account-linking procedure, không chỉ email. Decryption không thay các checks đó.

### 13.3. Không nhầm encrypted UserInfo với ID token

OIDC còn có thể dùng encrypted/signed UserInfo responses với registration/profile riêng. **Không xử lý mọi JWE đến RP như ID token**. Cần endpoint/content-type/profile-aware validation để tránh cross-JWT confusion.

## 14. Access token encryption: RS cần xác định recipient và issuer

Một AS có thể phát encrypted access token riêng cho `orders-api`. Một JWE có thể là:

- **Encrypted JSON claims** được profile ứng dụng/authorization framework định nghĩa với issuer authentication khác.
- **Nested signed-then-encrypted JWT**, outer JWE bảo vệ confidentiality và inner JWS bảo vệ issuer authenticity.

Nếu không có trust contract rõ, **không coi “AES tag hợp lệ” là bằng chứng OAuth authorization**. Khi sử dụng public-key encryption, bất kỳ bên nào biết public key có thể encrypt dữ liệu cho RS; inner signature/issuer authentication là điều cần được quyết định trong token profile.

### 14.1. Không mã hóa cho sai audience

Ví dụ token JWE được mã hóa cho `orders-api` nhưng inner JWT có `aud=payments-api`. Nếu RS giải mã được vì dùng cùng decryption key hoặc shared key store, **vẫn phải deny** vì audience sai. Mã hóa dành đúng recipient và audience chính xác là **hai ranh giới bổ sung**, không thay nhau.

### 14.2. Mã hóa không tự giới hạn scope

Một JWE chứa `scope=orders:read` không được phép gọi `POST /orders` chỉ vì decrypt/tag pass. API còn cần scope, role, tenant/object ownership và consent/grant state. Thường **401** khi token invalid, **403** khi token valid nhưng thiếu quyền theo API contract.

### 14.3. Token revocation vẫn cần thiết

Một token JWE có thể vẫn decrypt/authenticate thành công sau khi AS **revoke authorization grant**. Cryptographic decryption không tự biết state tại AS. Nếu RS cần revoke-aware enforcement, dùng introspection, denylist, grant version hoặc cơ chế đã được thiết kế, với độ trễ propagation và cache policy rõ.

### 14.4. Sender constraints

JWE confidentiality **không làm bearer token chống bị sao chép**. Nếu attacker có một JWE access token hợp lệ, họ có thể replay cả ciphertext tới RS mà không cần giải mã token. Khi threat model yêu cầu, dùng mTLS-bound hoặc DPoP-bound tokens với **proof/key binding** đúng profile; RS phải kiểm proof/cert, không chỉ outer decrypt.

## 15. Không dùng decryption failures như token-existence oracle

### 15.1. Lý do

Nếu API trả thông báo khác nhau:

```text
"unknown kid"              -> 404
"right key but bad tag"     -> 401 with detail "wrong authentication tag"
"private key K1 disabled"   -> 422
"token for tenant A"       -> 403 naming tenant A
```

attacker có thể thăm dò key registry, recipient/tenant topology hoặc cấu trúc token. Các khác biệt thời gian do decrypt thử nhiều keys cũng có thể là **side channel**. Response công khai cần được chuẩn hóa và **không tiết lộ dữ liệu nội bộ của cryptographic boundary**.

### 15.2. Lỗi đối với input sai vs outage

Có thể phân biệt **invalid credential (401)** và **service unavailable (503)**, vì mục tiêu vận hành khác nhau; nhưng trong cùng loại credential invalid không nên trả diagnostic key/tag chi tiết. Với KMS IAM denied có thể cần incident ticket và alert nhanh, không reveal principal/key reference cho client.

### 15.3. Rate limit và anti-DoS

Asymmetric decrypt/KMS call có chi phí. Attacker có thể gửi hàng ngàn token giả để:

- Làm RS phân tích JWE lớn.
- Gây `kid` refresh storm.
- Tiêu hao KMS/HSM decrypt quotas.
- Lấp đầy logs/audit queues.

Kiểm size/algorithm/kid format sớm, dùng **trusted bounded cache**, rate limits, circuit breaker và quota per workload. **Không loại bỏ các crypto checks để tăng throughput**.

### 15.4. Không ghi ciphertext rồi coi là vô hại

Một encrypted access token vẫn là **bearer credential**. Dù nhân viên support không đọc được claims, raw JWE bị sao chép có thể được dùng để gọi API nếu token còn hiệu lực. **Không log raw JWE, ID token, refresh token, Authorization headers hoặc URL chứa token**. Logs cần safe request correlation, normalized error class và approved key alias ref.

## 16. Cache, retry và giới hạn phục hồi

### 16.1. “Unknown `kid`” khác “KMS trả 503”

Nếu JWE chỉ đến với `kid=K2` chưa có trong **trusted recipient key registry**, một bounded refresh/reload có thể phù hợp khi prepublished K2 vừa được triển khai. Nếu KMS 503 trong khi key reference đã biết, đây là **dependency outage**, không phải lý do tải arbitrary JWK từ `jku`.

### 16.2. Không thử lặp mọi khóa

Thử K1, K2, K3... với mỗi attacker-supplied JWE:

- Tăng chi phí KMS/hardware.
- Kéo dài response timing tùy khóa.
- Có thể xuyên qua các tenant/issuer boundaries.
- Che giấu lỗi key registration và downgrade.

Map `kid` tới **key set có giới hạn theo recipient/tenant/profile**. Nếu profile legacy không có `kid`, define migration exception rõ với số lượng key giới hạn, TTL ngắn và sunset date; không mặc định scan toàn kho khóa.

### 16.3. Retry policy cho KMS

```text
KMS response class:
  AccessDenied -> no retry without configuration/security review
  KeyDisabled  -> no retry until managed key state changes
  429 / 503    -> bounded exponential backoff + jitter
  Timeout      -> retry only within request deadline

All cases:
  no principal until authenticated decrypt succeeds
  no logging raw token
  no local insecure fallback
```

Đừng retry vô hạn; việc retry hàng loạt khiến outage/429 tệ hơn. Dùng per-service budget, capacity planning và adaptive throttling.

### 16.4. Không cache plaintext/claims lâu vô hạn

Nếu RS cache decrypted token/verified principal để giảm KMS cost, cache cần:

- Keyed by safe cryptographic token reference thay vì raw bearer token string trong logs.
- TTL **không vượt `exp`** và authn/authorization/revocation security bounds.
- Scope theo issuer/audience/recipient key/token type/tenant context.
- Invalidation khi key compromised, grant revoked hoặc policy thay đổi.
- Không lưu plaintext JWE claims/CEK vào distributed cache không bảo vệ.

**Caching verified principal không biến grant revoked thành valid**. Khi revocation objective yêu cầu near-immediate deny, có cơ chế cache invalidation/state checks tương ứng.

## 17. Multi-region: cùng token có thể decrypt ở A nhưng lỗi ở B

```text
AS encrypts token to public K2, kid=K2

RS Region A:
  private K2 available + policy updated -> decrypt PASS

RS Region B:
  key registry still K1-only -> unknown kid / decrypt FAIL

RS Region C:
  key K2 exists, KMS IAM role denied -> dependency fault
```

Ba lỗi **khác nhau về nguyên nhân**, dù người dùng đều thấy login/API failure. Triển khai cần:

1. K2 private keys/permissions có mặt tại mọi authorized region trước issuer cutover.
2. AS/OP chỉ bắt đầu encrypt K2 sau khi key registry client/RS cập nhật.
3. K1 decrypt vẫn có trong bounded planned window.
4. Monitoring theo region/key ID/service identity, không theo raw tokens.
5. Drills cho failover, restore key, KMS outage, alias mismatch và rollback.

### 17.1. DR không chỉ khôi phục encryption key

Nếu restore private K1 nhưng mất grant/revocation store, RS có thể decrypt token cũ và chấp nhận token mà AS đã thu hồi. DR cần cả **issuer trust, token policy, revocation state, client registration, KMS key state, JWKS mapping và audit**.

### 17.2. Region-specific key restrictions

Một số giải pháp KMS/HSM có key residency/region/tenant policy riêng. Không copy private K1 sang region khác chỉ để “sửa lỗi decrypt” nếu yêu cầu pháp lý/chính sách cấm. Có thể cần **per-region key registration**, token routing, multi-recipient JOSE profile hoặc thiết kế khác được security review.

### 17.3. Concurrency khi rotate keys

AS có thể lấy `kid=K1` trước khi một config refresh làm encryption public key chuyển K2. Nếu không pin snapshot immutable của key material + `kid` trong cùng request, token bị lệch và không decrypt. Test race:

```text
Thread A reads kid=K1
Thread B updates current encryption key -> K2
Thread A encrypts using currentKey() = K2
JWE header still kid=K1
=> unintended undecryptable token
```

Giải pháp: **atomic immutable key-version snapshot** cho header + public encryption operation, canary/issuer rollout, không dùng mutable global alias hai lần trong một issuance request.

## 18. Audit và telemetry an toàn

### 18.1. Hai chiều quan sát

- **Token issuer:** ghi an toàn recipient public-key ID, `alg`/`enc`, token profile, issuance approval, không raw JWE.
- **RS/RP:** ghi safe request ID, trusted recipient profile, normalized failure class, region/key registry state, latency.
- **KMS/HSM:** ghi workload identity, key reference/version, API operation, IAM decision, error category và request correlation.

### 18.2. Ví dụ event không chứa raw token

```json
{
  "event": "token_processing_denied",
  "trusted_resource_ref": "orders-api",
  "token_profile": "nested-jwe-access",
  "algorithm_expected": "RSA-OAEP-256",
  "encryption_expected": "A256GCM",
  "recipient_key_ref": "orders-key-2026-b",
  "error_category": "DECRYPT_AUTHENTICATION_FAILED",
  "auth_result": "DENIED",
  "region": "test-region-A",
  "correlation_id": "req-2026-test-42"
}
```

`recipient_key_ref` trong audit là approved/normalized internal reference, **không phải arbitrary attacker-provided `kid`**. Không log full JWT header (có thể chứa malicious strings), claims, signature, CEK, ciphertext, KMS plaintext hoặc exception trace chứa raw token.

### 18.3. Metrics

```text
jwe_process_total{resource="orders-api",result="ok|invalid|dependency"}
jwe_decrypt_duration_seconds{resource="orders-api",profile="rsa-oaep-256-a256gcm"}
jwe_invalid_token_total{reason="malformed|alg|kid|tag|inner_signature|claims"}
kms_decrypt_errors_total{service="orders-api",class="timeout|denied|throttled"}
recipient_key_rotation_phase{resource="orders-api",phase="prepared|active|retired"}
jwe_processing_denial_total{region="A|B",class="policy|crypto|dependency"}
```

**Không dùng raw token, user ID, arbitrary `kid` strings hoặc untrusted issuer URLs làm metrics labels**. Alert nên dựa trên baseline/threshold và correlate với deployments/rotations, không coi mọi invalid tag là một cuộc tấn công đã được chứng minh.

### 18.4. Audit không tạo decryption oracle

Logs chi tiết chỉ dành cho authorized operators, có retention/security controls. External error vẫn thống nhất, tránh trả key/version/tenant existence. Kể cả nội bộ, **đừng ghi exact ciphertext** để “ngày mai debug” — nó vẫn là credential có thể bị replay.

## 19. Ma trận kiểm thử “token không giải mã được”

Để bảo đảm hệ thống **từ chối đúng**, không chỉ test một token JWE hợp lệ trả HTTP 200. Cần kiểm **negative cases**, error mapping, key lifecycle, sender/issuer/claim policy và những đường lỗi không được phép biến thành authenticated principal.

| # | Kịch bản | Kết quả bắt buộc/điều cần kiểm |
| --- | --- | --- |
| 1 | Nested JWE hợp lệ, đúng key/alg/enc/JWS/claims/scope | API cho phép theo resource policy |
| 2 | Không có bearer token ở protected endpoint | 401/deny |
| 3 | Một chuỗi rác thay JWE | Parser reject, không KMS call |
| 4 | JWS ba phần gửi vào JWE-only endpoint | Reject, không fallback sang JWT |
| 5 | Opaque token gửi vào JWE-only endpoint | Reject theo profile, không “thử decrypt” tùy ý |
| 6 | JWE bốn phần hoặc sáu phần | Parser reject |
| 7 | `encrypted_key` rỗng với `alg=dir` ngoài allowlist | Reject do alg policy, không chỉ vì empty |
| 8 | `encrypted_key` rỗng với RSA-OAEP-256 | Reject malformed theo key management profile |
| 9 | Protected header Base64url invalid | Reject |
| 10 | Protected header JSON malformed/duplicate params | Strict parser/profile reject |
| 11 | JWE token quá lớn | Reject trước expensive decrypt |
| 12 | `alg=RSA1_5` ngoài allowlist | Reject; không legacy fallback |
| 13 | `alg=none` trong JWE profile | Reject unsupported alg |
| 14 | `alg=RSA-OAEP` nhưng expected RSA-OAEP-256 | Reject nếu profile pin OAEP-256 |
| 15 | `enc=A128GCM` nhưng expected A256GCM | Reject |
| 16 | `enc` không thuộc policy | Reject, không tự chọn decoder |
| 17 | `kid` thiếu khi profile yêu cầu | Reject |
| 18 | `kid` lạ | Reject hoặc bounded refresh từ trusted registry, rồi reject |
| 19 | `kid` giống nhau giữa hai tenant | Không chọn key tenant khác |
| 20 | `kid` chứa path traversal/URL | Không sử dụng như file path/URL |
| 21 | Header `jku` trỏ attacker URL | Không tải/trust public key tùy ý |
| 22 | Header `x5u` trỏ metadata service | Chặn SSRF/key substitution |
| 23 | Header `crit` không được hỗ trợ | Reject |
| 24 | Header `zip` ngoài profile | Reject; không decompress tùy ý |
| 25 | Compressed JWE có output quá lớn | Bounded decompression/size enforcement |
| 26 | Wrong RS decryption key | Decrypt fail, no principal |
| 27 | Wrong KMS key version theo `kid` | Reject và alert mapping/rotation |
| 28 | Wrong RSA key size/purpose | Reject theo key policy |
| 29 | KMS decrypt key state `Disabled` | Fail closed, classify dependency/key state |
| 30 | Recipient key được giữ trong issuer signing JWKS nhầm vai trò | Không cross-use signing/encryption keys |
| 31 | AES-GCM ciphertext bị thay một byte | Authentication tag check fail, reject |
| 32 | AES-GCM authentication tag bị thay | Reject, không dùng partial plaintext |
| 33 | IV bị thay | Reject, không bỏ tag |
| 34 | JWE AAD/protected header bị thay | Reject khi integrity/protocol validation fail |
| 35 | CEK sai | Decrypt/authentication fail, reject |
| 36 | CEK A256GCM sai độ dài | Reject cryptographic parameters |
| 37 | Encryption reused IV cùng key | Security test identifies sender bug |
| 38 | Tag verification exception | Không in tag/CEK/plaintext; reject |
| 39 | Outer decrypt thành công nhưng plaintext không phải JWS | Reject nested profile |
| 40 | Outer decrypt thành công, inner JWS signature sai | Reject issuer authenticity |
| 41 | Outer decrypt thành công, inner `alg=none` | Reject |
| 42 | Outer decrypt thành công, inner JWS `kid` lạ | Reject trusted issuer key selection |
| 43 | Outer decrypt thành công, inner `iss` sai | Reject |
| 44 | Outer decrypt thành công, inner `aud` sai | Reject |
| 45 | Outer decrypt thành công, inner `typ` sai | Reject theo profile |
| 46 | Inner JWT hết hạn | Reject; không đổ lỗi decrypt |
| 47 | Inner JWT `nbf` trong tương lai | Reject |
| 48 | Inner JWT thiếu claim bắt buộc | Reject |
| 49 | Inner JWT active nhưng thiếu `orders:write` | 403/deny write |
| 50 | Inner JWT hợp lệ nhưng sai tenant | 403/resource policy denial |
| 51 | Encrypted ID token đến RP nhưng `nonce` sai | Không tạo login session |
| 52 | Encrypted ID token `aud` client khác | RP reject |
| 53 | Encrypted access token bị dùng làm ID token | RP reject token purpose |
| 54 | Refresh token gửi RS như JWE access | Reject token type/use |
| 55 | DPoP proof không khớp `ath`/`htu`/`htm` | RS deny dù JWE decrypt |
| 56 | mTLS-bound token với wrong peer cert | RS deny |
| 57 | JWE ciphertext bị copy và replay như bearer | Token theft defenses/revocation tests |
| 58 | Grant revoked nhưng JWE vẫn decrypt | RS revoke-aware policy deny |
| 59 | KMS AccessDenied | Fail closed, alert IAM, no insecure fallback |
| 60 | KMS 429 throttling | Bounded backoff, no principal |
| 61 | KMS 503/network outage | Fail closed, safe service error |
| 62 | KMS timeout | No unlimited retries/allow |
| 63 | HSM session exhausted | No legacy plaintext fallback |
| 64 | KMS key disabled during decrypt | Deny and operational classification |
| 65 | RSA-OAEP-256 not supported by provider | Reject/no downgrade to RSA1_5 |
| 66 | AS public K2 published nhưng RS chưa có private K2 | Detect rollout/recipient registration gap |
| 67 | RS private K2 ready nhưng AS vẫn encrypt K1 | Overlap K1 valid theo planned window |
| 68 | RS xóa K1 trước old JWE expiry | Detect availability regression |
| 69 | Old K1 token sau retirement deadline | Reject according to policy |
| 70 | K1 compromised, AS ngừng encrypt nhưng RS còn trust/decrypt | Incident propagation test |
| 71 | KMS alias K2 nhưng JWE header `kid=K1` | Reject/canary mapping fails |
| 72 | Multi-region A decrypt, B unknown `kid` | Rotation readiness/region tests |
| 73 | Multi-region key residency policy bị vi phạm | Security/compliance gate fail |
| 74 | AS/RS restore stale recipient keys/grant state | No unauthorized resurrection |
| 75 | Unknown `kid` flood | Rate-limited trusted refresh, no KMS DoS |
| 76 | Error response nêu đúng tên private key | Error-oracle/privacy test fail |
| 77 | Raw JWE/ID/access token có trong log/CI/APM | Redaction/security gate fail |
| 78 | Plaintext JWT claims/CEK xuất hiện trong metrics | Security gate fail |
| 79 | Invalid token được cache như “key service outage” vô thời hạn | Error/cache separation test fail |
| 80 | JWE invalid được custom Spring decoder trả authenticated `Jwt` | Security test fails; no principal |

### 19.1. Test tầng nào trả lời câu hỏi gì?

- **Unit:** parser/allowlist/`kid` routing, error classification, tag failure handling, claims/scope checks.
- **Component:** Nimbus JWE decrypt, trusted registry, inner JWS verification, Spring `JwtDecoder`/authentication entry point.
- **Integration:** AS thực phát JWE thử nghiệm cho RS/RP với key K1/K2 thật ở sandbox, đúng `alg`/`enc`, KMS/HSM adapter.
- **End-to-end:** OAuth grant → token issuance → encryption → client API → decrypt → issuer verify → authorization/revocation.
- **Resilience:** KMS quota/outage, HSM sessions, JWKS/key rollover, multi-region, failover, cached verified tokens.
- **Security:** wrong recipient, key substitution, malformed critical headers, decompression bomb, invalid tag, data leakage, downgrade và replay.

### 19.2. Không tự gây mất khả dụng production để test

Các case destructive (disable recipient key, revoke thật, KMS outage, private key compromise drill) chạy trong **sandbox cô lập** hoặc môi trường được change-approved. Không gửi test ciphertext với credential thật đến arbitrary provider; không log raw production tokens để “tạo fixture”.

## 20. Kịch bản tích hợp: cùng một token trước và sau rotation

### 20.1. Baseline trước rotation

1. Provision recipient private key **K1** tại RS test, đăng ký public K1 với AS test.
2. AS phát **nested JWE** với `alg=RSA-OAEP-256`, `enc=A256GCM`, `kid=K1` và inner PS256 JWS có `iss`/`aud=orders-api`, `scope=orders:read`.
3. RS gọi `GET /v1/orders/fixture-42` bằng JWE K1 → **200**.
4. No-token/wrong-scope control → **401/403** đúng contract.
5. Nếu JWE K1 không chạy được trước rotation, kết quả test là **SETUP_FAILED**, không gọi lỗi hậu rotation là PASS.

### 20.2. Prepublish K2

6. Tạo recipient private **K2**, đăng ký public K2 vào trusted registry của AS.
7. Kiểm tất cả RS nodes/regions có quyền decrypt K2 và policy cho `alg`/`enc` mong đợi.
8. AS chuyển encrypt new JWE sang K2, header `kid=K2`; kiểm JWE mới → 200.
9. Trong planned overlap, JWE K1 cũ còn hợp lệ và K1 được phép decrypt → 200 theo TTL/grant/security policy.
10. Sau deprecation window, JWE K1 phải bị từ chối **theo key retirement policy**, dù tokens cũ có thể đã expired trước đó.

### 20.3. Key rotation vs invalid claims

Test thêm inner PS256 JWS sai `aud`, hết hạn hoặc revoked. Nếu RS decrypt thành công nhưng response 401, **đừng ghi “K2 decrypt failed”**. Phân loại đúng **invalid inner JWT/authorization state**.

### 20.4. Một phép thử không đủ

Một JWE K2 thành công trên **region A** chưa chứng minh region B đã có decryption key. Test tất cả supported routing paths, hoặc có synthetic probes tương đương; theo dõi **key readiness** trước issuer cutover.

## 21. Java/JUnit: test negative-path theo security invariant

Những ví dụ dưới đây dùng **test abstractions** như `jweFixtures`, `ordersApi`, `kmsSandbox` — không phải API chuẩn có sẵn trong JUnit/Nimbus. Mục tiêu là định nghĩa test oracle, không tự xây cryptographic primitive.

### 21.1. Valid nested JWE được chấp nhận đúng quyền

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EncryptedAccessTokenIT {
    @Test
    void validNestedJweAuthorizesOnlyExpectedEndpoint() {
        var jwe = jweFixtures.issueOrdersReadTokenEncryptedTo("K1");

        assertEquals(200, ordersApi.getOrder(jwe, "fixture-42").status());
        assertEquals(403, ordersApi.deleteOrder(jwe, "fixture-42").status());
    }
}
```

**Điều kiện:** fixture `GET` có data thuộc user/tenant đúng quyền; `DELETE` yêu cầu quyền write/delete khác `orders:read`. Nếu endpoint public hoặc business policy cho cả delete, đây không phải oracle đúng.

### 21.2. Tag bị sửa không tạo principal

```java
@Test
void tamperedAuthenticationTagCannotCreatePrincipal() {
    var valid = jweFixtures.issueOrdersReadTokenEncryptedTo("K1");
    var tampered = jweFixtures.flipOneTagByte(valid);

    var result = ordersApi.getOrder(tampered, "fixture-42");

    assertEquals(401, result.status());
    assertEquals(0, businessAudit.unauthorizedReads());
    assertFalse(authenticationEvents.wasPrincipalCreatedFor(result.requestId()));
}
```

Đừng assert toàn bộ text “bad tag at byte N” hoặc đưa ciphertext/tampered token vào CI output. Chỉ cần chứng minh **authentication failed + no business side effect**.

### 21.3. Unknown key không được trigger arbitrary URL fetch

```java
@Test
void forgedRecipientKidCannotCauseKeySubstitution() {
    var token = jweFixtures.headerWithUnknownKidAndUntrustedJku();

    var result = ordersApi.getOrder(token, "fixture-42");

    assertEquals(401, result.status());
    assertEquals(0, outboundNetworkCalls.toUnknownJwksHosts());
}
```

Test này kiểm no-SSRF/key substitution. Nếu profile có trusted refresh, chỉ nên liên hệ registry endpoint đã pin và có rate limit.

### 21.4. KMS outage không cho qua request

```java
@Test
void kmsTimeoutFailsClosed() {
    kmsSandbox.simulateDecryptTimeout();
    var encrypted = jweFixtures.issueOrdersReadTokenEncryptedTo("K1");

    var response = ordersApi.getOrder(encrypted, "fixture-42");

    assertNotEquals(200, response.status());
    assertEquals(0, ordersRepository.unauthorizedReadCount());
    assertEquals(0, insecureFallbackDecryptor.invocationCount());
}
```

HTTP status có thể là 503 hoặc 401 theo contract; điều bất biến là **không authenticated principal**. Trong test thực phải setup token fixture **trước khi mô phỏng outage**, tránh làm AS issuance không có token.

### 21.5. Inner JWT sai audience dù decrypt thành công

```java
@Test
void successfulDecryptDoesNotBypassAudienceCheck() {
    var token = jweFixtures.encryptSignedToken(
        "K1", "profile-api", "profile:read");

    var response = ordersApi.getOrder(token, "fixture-42");

    assertEquals(401, response.status());
}
```

Một “decrypt OK” chỉ tạo plaintext trusted *về mặt AEAD*; nó **không chứng minh token dành cho orders API**.

### 21.6. RP không tạo OIDC session nếu ID token không decrypt

```java
@Test
void encryptedIdTokenFailureDoesNotCreateLoginSession() {
    var callback = oidcFixtures.responseWithWrongRecipientKey();

    var response = oidcRp.handleCallback(callback);

    assertFalse(response.createdAuthenticatedSession());
    assertFalse(response.exposedEncryptedIdTokenInBody());
}
```

Test thêm `state`, `nonce`, `iss`, `aud` và signing validation đúng profile. Không thay encrypted ID token validation bằng việc đọc `email` từ UserInfo chưa có authenticated transaction.

### 21.7. Planned overlap không phải downgrade

```java
@Test
void oldKeyAcceptedOnlyWithinApprovedRotationWindow() {
    var oldJwe = jweFixtures.issueOrdersReadTokenEncryptedTo("K1");
    assertEquals(200, ordersApi.getOrder(oldJwe, "fixture-42").status());

    recipientKeyLifecycle.prepublishK2();
    recipientKeyLifecycle.activateK2();
    var newJwe = jweFixtures.issueOrdersReadTokenEncryptedTo("K2");
    assertEquals(200, ordersApi.getOrder(newJwe, "fixture-42").status());

    recipientKeyLifecycle.retireK1AfterWindow();
    assertEquals(401, ordersApi.getOrder(oldJwe, "fixture-42").status());
}
```

Đây là pseudocode; test thật nên dùng **fake clock/lifecycle hooks**, không sleep theo giờ thực hoặc dùng token đã hết hạn để “chứng minh” K1 retirement.

### 21.8. Spring authentication entry point phải nằm trước controller

```text
Given: one malformed JWE on protected GET /orders
When: Spring Security Filter Chain authenticates request
Then:
  JwtDecoder throws invalid-credential exception
  AuthenticationEntryPoint sends 401
  SecurityContext has no authenticated principal
  Orders controller not invoked
  No secret/token raw bytes in logs
```

Đừng chỉ unit-test một `@ControllerAdvice` vì authentication failures thường xảy ra **trước MVC controller** trong Spring filters.

## 22. Chẩn đoán production: đọc dấu hiệu theo lớp

| Quan sát | Nguyên nhân có thể | Bước điều tra an toàn |
| --- | --- | --- |
| Tỷ lệ 401 tăng ngay sau AS release | `alg`/`enc`/`kid` mới chưa được RS hỗ trợ | So signer config vs recipient registry; canary K2 |
| Chỉ một region fail decrypt | Private K2/permissions/registry chưa đồng bộ | Region readiness/KMS IAM/rotation timeline |
| Chỉ nested JWT fail sau decrypt | Inner signing key/JWKS/claims đổi | Kiểm inner `alg`/issuer/aud/type bằng safe fixture |
| KMS trả 403 | Workload role/key policy sai hoặc disable | Review authorized principal, KMS audit |
| KMS 429/503 tăng | Quota, network, capacity, outage | Throttle/retry budget, provider status, p95 latency |
| JWE tag errors tăng sau middleware change | Token bytes bị cắt/sửa/normalize | So transport length, proxy header limits, encoding |
| Chỉ ID tokens của một RP fail | RP private key/client registration mismatch | Kiểm RP K1/K2 và OP encryption public key |
| K1 hết decrypt sau rotation | Xóa private K1 quá sớm | Planned overlap/TTL/security policy |
| JWT `exp` hết hạn trong khi decrypt OK | Token lifetime issue | Claim validation; không gọi là decrypt failure |
| 403 sau decrypt OK | Scope/resource/tenant deny | Authorization policy, không đổ lỗi crypto |
| KMS success nhưng API vẫn 401 | Inner JWS invalid hoặc claims/token type sai | Verify issuer signing trust và token profile |
| 200 khi KMS down | **Fail-open bug** hoặc cache quá hạn | Ngăn business allow, đánh giá incident |
| Public response lộ `kid` và key state | Decryption oracle | Error normalization/security review |
| JWE hợp lệ trên test, fail trên production | Khác key registry, algorithms, IAM hoặc JOSE versions | Config diff safe metadata, no secrets |

### 22.1. Ba câu hỏi để khoanh vùng nhanh

1. **Đây có phải token cần decrypt ở endpoint này không?** Nếu là opaque/JWS thì route validation sai.
2. **Đã chọn đúng recipient key và cryptographic operation chưa?** Kiểm profile, `kid` mapping, KMS availability, alg/enc/format.
3. **Decrypt có thành công nhưng token bị từ chối bởi issuer/claims/authorization không?** Kiểm inner signature và policy tách biệt.

### 22.2. Không “fix” bằng cách tắt bảo mật

Những biện pháp sau **không được chấp nhận**:

- Bỏ AEAD authentication tag verification.
- Thử decrypt bằng tất cả keys đến khi có plaintext, vượt tenant boundaries.
- Chấp nhận `alg=none` hoặc `RSA1_5` do “legacy support” không review.
- Thay JWE bằng unencrypted JWT nếu client/AS contract yêu cầu encryption.
- Bỏ inner signature vì “JWE đã decrypt”.
- Đổi `KMS AccessDenied` thành allow.
- Log raw token hoặc xuất private key để debug.
- Bỏ issuer/audience/scope validation để RS trả 200.

### 22.3. Xác định phạm vi trước khi rollback

Nếu một release lỗi recipient key K2, rollback signer/AS encryption to K1 có thể là phương án **chỉ khi K1 còn được tin, không compromised, đúng security policy** và toàn bộ RS đã có K1. Không rollback từ cryptographic security fix về cipher yếu hoặc key đã bị nghi lộ.

## 23. Runbook xử lý sự cố “cannot decrypt token”

### Bước 1 — Chặn cấp quyền sai

Xác minh tất cả RS/RP **fail closed**: khi decrypt thất bại không tạo principal/session, không chạy business action, không dùng unverified claims. Nếu có fail-open, **ưu tiên cô lập đường đó** theo incident severity.

### Bước 2 — Phân nhóm tín hiệu

```text
INVALID_TOKEN_INPUT:
  malformed, wrong alg/enc, untrusted kid, tag fail

INTEGRATION_OR_DEPENDENCY:
  key missing in region, disabled key, KMS IAM, throttling, outage

POST_DECRYPT_VALIDATION:
  inner signature, issuer, audience, typ, exp, scope, revoked grant
```

Ghi safe request IDs, region, configured profile/key alias, deploy version và error category. **Không copy raw JWE/CEK/private key/claims vào incident channel**.

### Bước 3 — Kiểm cấu hình trusted

Kiểm:

- AS/OP encryption public key đang đăng ký thuộc recipient nào?
- RS/RP private key K1/K2 có sẵn, đúng algorithm/usage và key residency không?
- `kid` ↔ actual public key ↔ private key mapping có nhất quán không?
- Issuer signing JWKS cho inner JWS có được tin không?
- Các nodes/caches có cùng policy version và rotation phase không?
- HTTP proxy có cắt/sửa header Authorization vì size limits không?

### Bước 4 — Kiểm KMS/HSM

Tra theo safe correlation:

- Workload identity và IAM `Decrypt`.
- Key state, version, aliases, algorithm support.
- Provider error class, quota, network/session health.
- Các region được phép dùng key, backup/failover trạng thái.
- Service logs có bị vô tình in ciphertext/plaintext không?

### Bước 5 — Khắc phục đúng nguyên nhân

- **Deployment gap:** khôi phục key readiness, prepublish, staged rollout.
- **KMS outage:** bounded retry/circuit breaker, approved alternate decrypt path nếu có, không bypass.
- **Tamper/malformed flood:** reject, rate-limit, investigate abuse/transport.
- **Inner JWT invalid:** sửa issuer signing/claims pipeline, không thay decrypt policy.
- **Key compromised:** ngừng encrypt mới, đánh giá confidentiality của token đã phát/captured, rotate and revoke/reissue theo risk.

### Bước 6 — Kiểm regression và đóng sự cố

1. Issuer test phát JWE K1/K2 đúng profile; RS/RP decrypt và validate thành công.
2. Tampered tag/malformed/unknown kid vẫn 401, không có principal.
3. KMS outage vẫn fail closed; 503/response theo contract.
4. Valid token sai audience/scope/expired/revoked bị deny đúng lớp.
5. Các regions/verifiers thống nhất state theo security/availability objective.
6. Logs/metrics/CI không có raw tokens, PII plaintext, CEK, private key.
7. Có root cause, hành động phòng ngừa, owner, timeline và tests chống tái diễn.

### 23.1. Khi private decryption key bị lộ

**Confidentiality incident**: attacker có thể đọc các ciphertext token họ đã hoặc có thể thu thập. Tùy threat model và lifetime, cần:

- Stop issuing new JWE to compromised public key.
- Register/activate new recipient encryption key K2 qua trusted channel.
- Đánh giá các old JWE đã phát, captured tokens/logs và phạm vi PII/claims nhạy cảm.
- Revoke/reissue affected tokens/grants nếu bearer theft/replay risk.
- Hạn chế/xóa old key theo incident policy; cân nhắc availability của old tokens.
- Điều tra nguyên nhân lộ key material (RAM dumps, backups, logs, IAM, device).

**Không thể “khôi phục bí mật trong quá khứ” chỉ bằng xóa K1 khỏi JWKS**; encryption key có thể đã bị copy và old ciphertext có thể còn lưu ở ngoài.

### 23.2. Khi issuer signing key bị lộ

**Authenticity incident** khác: attacker có thể **forge inner JWS**. Cần emergency distrust compromised signing public key tại verifiers, không chỉ rotate recipient encryption key. **Đổi encryption key không ngăn forged JWS nếu RS còn tin issuer signing key đã bị lộ**.

## 24. Chọn encrypted JWT, signed JWT hay opaque token?

**Một hệ thống có lỗi “không giải mã được JWE” chưa chắc nên dùng JWE ngay từ đầu.** Chọn định dạng dựa trên nhu cầu bảo mật và interoperability:

| Câu hỏi | Nếu câu trả lời là… | Gợi ý thiết kế |
| --- | --- | --- |
| RS cần biết claims mà không gọi AS? | Có | JWS JWT access token với issuer/aud/scope validation, cân nhắc revocation window |
| Payload claims phải bí mật với người cầm token? | Có | JWE/nested JWS+JWE theo profile; tránh đặt dữ liệu không cần vào token |
| Muốn AS kiểm soát trạng thái active/revoke tập trung? | Có | Opaque token + introspection hoặc revocation-aware JWT mechanism |
| Client không nên biết claims? | Có | Opaque có thể đơn giản hơn, hoặc encrypted token nếu offline RS verification cần thiết |
| RS có thể giữ key decrypt và xử lý KMS availability? | Không | Cân nhắc opaque/introspection hoặc JWS chứa claims tối thiểu |
| Cần sender proof chống copy bearer token? | Có | DPoP/mTLS-bound token; JWE **không thay** sender constraint |
| Có nhiều RS với access permissions khác nhau? | Có | Audience/resource indicators, token separation và key/profile namespace |
| OP/RP yêu cầu encrypted ID token theo registration? | Có | Đúng JOSE `alg`/`enc`/recipient key lifecycle, kiểm OIDC sau decrypt |

### 24.1. Không phải “JWE mạnh hơn JWS cho mọi thứ”

- **JWS** bảo vệ nguồn gốc/toàn vẹn claims bằng signature. Claims có thể đọc được nhưng RS chỉ cần public key và không cần decrypt trên mỗi request.
- **JWE** bảo vệ confidentiality claims cho recipient, nhưng cần decryption key custody và key-service availability; một JWE encrypt bằng recipient public key không tự chứng minh issuer.
- **Nested JWT** kết hợp nhiều bảo đảm theo profile nhưng tăng số lớp lỗi và nhu cầu rotation/key management.
- **Opaque token** có thể tránh lộ claims tới client, cho AS state control qua introspection; đổi lại là dependency/latency và caching/revocation design.

**Nguyên tắc:** chọn token format đơn giản nhất đáp ứng threat model. Đừng bật encryption chỉ để “khó đọc” khi payload không có claims nhạy cảm và KMS/rotation complexity vượt giá trị; cũng đừng bỏ confidentiality khi registration và privacy requirement bắt buộc JWE.

### 24.2. Khi nào encrypted token là lựa chọn hợp lý?

Ví dụ:

```text
Issuer AS:
  signs claims per approved profile
  encrypts token to recipient RS registered key

Recipient RS:
  must process claims offline
  must keep claims hidden from token holder/intermediaries
  has approved HSM/KMS decrypt/rotation architecture
  verifies inner issuer signature and permissions
```

Trong trường hợp này, JWE có thể phù hợp nếu được security/interoperability review. **Không dùng một custom “Base64(AES(JSON))”** để thay JWE — nó thiếu JOSE serialization/key policy và dễ mắc lỗi tag/nonce/identity/replay.

## 25. Tình huống thực tế: cách giải thích lỗi không decrypt

### Tình huống A — Gửi JWS vào JWE-only RS

AS gửi token `header.payload.signature` ba phần. Orders API nhận token, code gọi `JWEObject.parse` và báo malformed.

**Phân tích:** Có thể client dùng nhầm access-token format hoặc AS profile rollout chưa đồng bộ. **Không có “token không decrypt vì key sai”** ở đây; RS mong JWE nhưng nhận JWS. Cần sửa contract/routing, không fallback sang unsigned claims hoặc cho mọi token format vào cùng decoder.

### Tình huống B — Opaque token bị tưởng là encrypted JWT

Client Credentials flow trả chuỗi opaque ngẫu nhiên. RS dùng JWE decoder chỉ vì API header tên `Authorization: Bearer`.

**Phân tích:** Bearer token **không phải** tín hiệu format JWE. RS cần cấu hình OAuth introspection hoặc token profile đúng. Gọi decrypt trên opaque string là sai hợp đồng.

### Tình huống C — Protected header `kid` tới K2 nhưng RS chỉ có K1

Issuer công bố K2 quá sớm, region A có K2 nhưng region B chưa phân phối.

**Phân tích:** Rotation readiness gap. Khắc phục bằng prepublish/recipient key provision, canary và deployment gate. Không để region B tạm tin plaintext hoặc hỏi attacker-supplied `jku`.

### Tình huống D — AES-GCM tag invalid sau proxy thay đổi

Trước release gateway, JWE decrypt thành công. Sau release, một proxy trim hoặc encode lại header quá dài, làm thay token bytes.

**Phân tích:** Kiểm HTTP header size, normalization, limits, WAF/caching, không dump raw bearer token. **Không bỏ tag**; thay proxy transport logic để giữ credential bytes nguyên vẹn.

### Tình huống E — KMS AccessDenied cho một AS/RS workload

Đổi workload IAM role khiến RS không được `Decrypt` K2. Mọi JWE K2 đều thất bại, dù issuer tạo token đúng.

**Phân tích:** Infrastructure/security configuration error. Fail closed, alert, rà key policy/principal và deploy; không gọi token là “forged” chỉ vì không truy cập được KMS.

### Tình huống F — JWE decrypt thành công nhưng inner JWS invalid

AS encrypt một JWT mà private signing key/algorithm hoặc `kid` inner không khớp trusted issuer JWKS; outer AES-GCM vẫn OK.

**Phân tích:** **Issuer signature verification failure**, không phải lỗi recipient key. RS phải từ chối; không dùng plaintext claims để tạo principal.

### Tình huống G — ID token encrypted tới public key cũ của RP

RP đổi private K1→K2 nhưng OP registration vẫn có public K1. RP callback không decrypt được JWE K1.

**Phân tích:** Client registration/rotation mismatch. Không tạo session/không tắt mã hóa để login; phối hợp OP/RP key rollover theo policy, có bounded overlap khi planned.

### Tình huống H — RSA-OAEP-256 không được KMS hỗ trợ

AS phát JWE profile `alg=RSA-OAEP-256`, RS chọn KMS API chỉ hỗ trợ thuật toán/operation khác.

**Phân tích:** Provider capability/adapter mismatch. Không chuyển sang `RSA1_5` hoặc raw RSA không padding vì “dễ chạy”. Đổi provider/tier/profile được review hoặc sử dụng JCA/PKCS#11 path phù hợp.

### Tình huống I — Valid JWE vẫn bị 403

Orders API decrypt, verify inner JWS, `aud=orders-api` và `exp` hợp lệ. Token chỉ có `scope=orders:read` nhưng client gọi `POST /orders`.

**Phân tích:** Authentication valid, authorization denied. **403** là hợp lý theo policy; không ghi “JWE decrypt failed” hoặc thử dùng key khác.

### Tình huống J — Grant revoked nhưng ciphertext vẫn decrypt

AS revoke refresh family hoặc access token state. JWE còn đúng key/tag, RS nếu chỉ kiểm crypto có thể chấp nhận đến `exp`.

**Phân tích:** Revocation-state enforcement, không phải decryption. Chọn introspection/denylist/grant version/short TTL phù hợp security objective.

### Tình huống K — Bearer JWE bị lấy từ log

Logging middleware lưu full `Authorization` header vì token “đã mã hóa”, nghĩ attacker không thể đọc.

**Phân tích:** Ciphertext JWE là **credential có thể replay**, dù không đọc được claims. Phải redaction, revoke/reissue tokens bị lộ, rà access logs và tăng sender constraints nếu risk đòi.

### Tình huống L — Hai tenants dùng cùng `kid`

Token từ tenant B ghi `kid=main` giống token tenant A; RS chỉ lookup key global theo `kid` và thử key B khi A failed.

**Phân tích:** Key namespace/trust boundary bug. Registry phải ràng buộc recipient/tenant/token profile, không quét global key set.

### Tình huống M — KMS lỗi nhưng code fallback hardcoded key

Developer thêm:

```java
// SAI: fallback vượt trust/key policy.
try {
    return decryptWithKms(token);
} catch (Exception e) {
    return decryptWithLocalHardcodedKey(token);
}
```

**Phân tích:** Có thể làm lộ private key và mở downgrade/trust mismatch. Không dùng code này. Chỉ failover qua **approved key-service path với cùng key/recipient/security assurances** hoặc trả lỗi fail closed.

### Tình huống N — RS thử parse Base64 claims khi decrypt thất bại

Token bị tampered làm tag invalid, nhưng code fallback `decodeBase64(payload)` rồi lấy `sub`.

**Phân tích:** Authentication bypass. Không có authenticated plaintext, không có trusted claims; request phải bị từ chối.

### Tình huống O — `zip` tạo decompression bomb

Một JWE profile cho phép compression nhưng không có limits; attacker gửi token nhỏ làm output rất lớn sau decrypt/decompress.

**Phân tích:** Resource exhaustion. Nếu profile không cần compression, **cấm `zip`**; nếu cần, áp giới hạn kích thước, độ sâu, work budget, request rate. Không “decrypt OK” rồi unbounded allocate.

### Tình huống P — Encryption key compromise bị nhầm signing key compromise

Private decryption K1 bị lộ, đội vận hành chỉ rotate inner issuer signing key. Attacker vẫn giải mã captured JWE K1.

**Phân tích:** Hai assets khác nhau. **Recipient decryption key leak** làm nguy cơ confidentiality; **issuer signing key leak** làm nguy cơ authenticity/forgery. Incident scope và rotation phải nhắm đúng key cùng các tokens/grants liên quan.

## 26. Bài thực hành

### Bài A — Phân biệt loại token

Phân loại ba input:

```text
TOKEN_1 = header.payload.signature
TOKEN_2 = header.encryptedKey.iv.ciphertext.tag
TOKEN_3 = opaque random reference without JOSE structure
```

Chọn hướng xác minh phù hợp cho RS và giải thích vì sao **`Authorization: Bearer` không tự chỉ định token format**.

### Bài B — Cấu trúc JWE

Vẽ 5 thành phần của JWE Compact. Nêu thành phần nào có thể rỗng trong một số `alg` profiles. Phân biệt `alg` và `enc`, giải thích CEK, protected header, IV và authentication tag.

### Bài C — Decrypt thành công có đủ?

Recipient RS có public encryption key ai cũng có thể biết. Một attacker tự tạo ciphertext với `sub=admin` mã hóa vào đúng public key đó.

Hãy giải thích vì sao **decrypt/tag pass** không chứng minh AS đã cấp claims. Thiết kế nested signed-then-encrypted JWT và kiểm issuer signature/claims.

### Bài D — Sửa Java catch-all

```java
// SAI
try {
    return decryptJwe(token);
} catch (RuntimeException e) {
    return makePrincipal("guest", "orders:write");
}
```

Viết phương án fail-closed: classify invalid token vs KMS dependency outage, không tạo principal/side effects, dùng `AuthenticationEntryPoint`/HTTP contract phù hợp và log safe reason code.

### Bài E — Kiểm AES-GCM tag

Một JWE bị thay một byte ciphertext hoặc tag. Nêu expected decryption result và tại sao tuyệt đối không dùng plaintext nếu tag không hợp lệ. So sánh với JWS signature invalid.

### Bài F — Rotation K1 → K2

Access JWE max TTL 15 phút, RS có ba regions, AS encrypt sang K2 từ 10:00. Region B chưa có private K2 đến 10:04.

Lập kế hoạch prepublish, K2 readiness gate, canary, overlap K1 và verification timeline. Vì sao chỉ kiểm region A xanh là chưa đủ?

### Bài G — Wrong `kid` nhưng có đúng key khác

Header ghi `kid=K1`, ciphertext mã hóa tới K2. RS thử K1 rồi thất bại. Có nên thử mọi keys để tìm K2 không? Hãy giải thích rủi ro timing/KMS DoS/cross-tenant confusion và thiết kế immutable mapping.

### Bài H — OIDC encrypted ID token

RP đã đăng ký encrypted ID token `RSA-OAEP-256/A256GCM`. OP gửi token tới public K1 nhưng RP vừa xóa private K1.

Mô tả expected login failure và cách phối hợp key rollover. Có nên bỏ `id_token_encrypted_response_alg` khỏi client registration để user login tạm không?

### Bài I — OAuth 401/403/503

Cho ba tình huống:

1. JWE authentication tag invalid.
2. Decrypt + verify thành công, token thiếu `orders:write`.
3. KMS timeout, không xác định được tính hợp lệ.

Chọn hành vi **không cấp quyền** và HTTP mapping phù hợp theo API contract, giải thích vì sao status khác nhau nhưng **không có trường hợp fail-open**.

### Bài J — Spring Security encrypted JwtDecoder

Dựng component test dùng `MockMvc` và một custom decoder đã kiểm JWE:

- Valid nested access token → 200 cho GET đúng resource.
- Invalid tag → 401, controller không chạy.
- Inner wrong `aud` → 401.
- Valid but insufficient scope → 403.
- KMS unavailable → no principal, 503/deny theo configured entry point.

Giải thích vì sao chỉ dùng `.oauth2ResourceServer(oauth -> oauth.jwt())` với default JWS decoder **không bảo đảm decrypt JWE**.

### Bài K — Nimbus profile check

Sửa `StrictNestedAccessJweProcessor` cho production:

1. Check max size trước `JWEObject.parse`.
2. Pin `alg=RSA-OAEP-256` và `enc=A256GCM`.
3. Recipient namespace/KMS key purpose và retired-key policy.
4. Distinguish unknown key vs dependency errors.
5. Verify inner PS256 signature, `iss`/`aud`/`typ`/`exp`/`nbf` và scope.
6. Không log raw `compactJwe`/claims/CEK.

### Bài L — Key-service outage

KMS trả 429 sau một deploy; RS bị storm 50.000 requests. Hãy thiết kế bounded backoff, rate limit, circuit breaker, quota monitoring và các đường failover được phê duyệt. Vì sao “bỏ tag verification để tiếp tục phục vụ” là sai?

### Bài M — Token theft

Một raw JWE access token xuất hiện trong proxy logs. Token mã hóa bằng RSA-OAEP-256/A256GCM và inner JWS PS256 còn hạn. Có an toàn vì attacker không giải mã được không? Đề xuất revoke/reissue, log remediation, scopes/TTL và mTLS/DPoP sender constraints.

### Bài N — Private decryption key lộ

Key K1 bị export trái phép từ backup. Một số ciphertext K1 đã xuất hiện trong network traces. Hãy viết runbook phân biệt confidentiality breach với issuer signing key compromise; đánh giá backward exposure, stop new encryption, key rotation và token revocation.

### Bài O — Opaque token không decrypt

RS nhận token opaque từ AS nhưng nhà phát triển cố gọi `JWEObject.parse` rồi nhận 401. Hãy thiết kế lại đường RFC 7662 introspection, kiểm `active`, `aud`/scope/token type và xử lý introspection unavailable.

### Bài P — Error oracle

API trả ba JSON errors: `{"error":"kid K2 missing"}`, `{"error":"GCM tag incorrect"}`, `{"error":"private key disabled"}`. Nêu rủi ro thông tin bị lộ và thiết kế một response invalid-token chung, một response service-unavailable theo policy và internal correlation ID.

### Bài Q — Multi-region và tenant

Issuer encrypt token cho recipient tenant A. Region B có KMS key của tenant B cùng `kid=main`. Tại sao không được thử key B? Vẽ trusted key registry có namespace `recipient + environment + key ID + algorithm`.

### Bài R — Báo cáo CI không lộ dữ liệu

Xây báo cáo kiểm thử gồm:

```text
case_id
token_fixture_label (not bearer bytes)
trusted_recipient_ref
expected_alg/enc
expected_key_state
decryption_outcome
inner_signature_outcome
claims_validation_outcome
http_status
principal_created (boolean)
business_side_effects (count)
error_class
region
result PASS/FAIL
```

Không dùng raw token, CEK, signing input, ID token plaintext, KMS credentials hoặc private keys. Thêm case chứng minh logs không chứa sentinel.

### Bài S — Phân biệt nguyên nhân 401

API trả 401 cho cả:

- Token tampered tag.
- Token decrypt thành công nhưng expired.
- Token decrypt thành công, inner issuer signature sai.
- Token đúng crypto nhưng wrong audience.

Viết bảng **internal reason categories** để phân biệt và hướng điều tra; giải thích vì sao client không cần biết tag/key details.

### Bài T — Chọn token format

Một hệ thống 20 microservices có yêu cầu dữ liệu claims tối thiểu, RS có thể dùng trusted public signing keys và không muốn key decrypt ở mỗi region. Một hệ thống khác cần claims bí mật với browser client và RP yêu cầu encrypted ID token. Hãy chọn JWS, JWE/nested hoặc opaque/introspection phù hợp từng hệ thống và trade-off latency/rotation/revocation.

## 27. Checklist trước khi triển khai production

### 27.1. Token profile và trust

- [ ] Phân biệt JWS/JWE/nested/opaque/refresh/ID token; endpoint nào cần decrypt được quy định rõ.
- [ ] Không dùng fallback “JWE decrypt fail → JWS/opaque/unverified claims” ngoài security-approved routing policy.
- [ ] Chọn `alg`/`enc` theo allowlist từ trusted recipient registration, không từ JWT header tùy ý.
- [ ] JWE compact parser chấp nhận đúng cấu trúc 5 phần và algorithm-specific empty encrypted key semantics.
- [ ] Chặn oversized tokens, malformed Base64url, duplicate/critical header parameters, uncontrolled compression.
- [ ] `kid` map vào trusted recipient key namespace, không quét global keys/cross-tenant.
- [ ] Không fetch arbitrary `jku`/`x5u` hoặc public key do token tự cung cấp.
- [ ] Tách recipient decryption keys khỏi issuer signing JWKS và key material khác.
- [ ] Client/RP/RS dùng đúng key profile và có evidence key origin/non-exportability khi policy yêu cầu.

### 27.2. Decryption và validation

- [ ] Authenticated encryption tag luôn được kiểm đầy đủ; không tin plaintext tạm.
- [ ] AES-GCM CEK/IV/tag lengths đúng JOSE profile, không dùng lại key+nonce.
- [ ] RSA-OAEP-256/ECDH-ES/key agreement được triển khai bằng JOSE library/provider được kiểm thử; không tự viết crypto.
- [ ] KMS/JCA RAW-vs-DIGEST, key unwrap/output semantics và provider support được xác minh theo thuật toán.
- [ ] Decrypt success **không tự chứng minh issuer**; nested inner JWS được verify nếu token profile yêu cầu.
- [ ] Nội dung inner JWT có `iss`, `aud`, `typ`, `exp`, `nbf`/claims validation theo profile.
- [ ] RS kiểm scope, tenant, ownership và sender-constraining nếu yêu cầu.
- [ ] RP OIDC kiểm `nonce`, `aud=client_id`, issuer, `azp`/`auth_time` khi áp dụng và không tạo session nếu invalid.
- [ ] Revoked access token/refresh family không được hồi sinh vì JWE vẫn decrypt.
- [ ] Opaque token đi qua introspection, không bị ép thành encrypted JWT.

### 27.3. Error handling và privacy

- [ ] Crypto/parse/key lookup failure **không tạo authenticated principal** và không chạy business action.
- [ ] Invalid-token 401 vs authorization 403 vs KMS service outage 503 được ánh xạ theo hợp đồng rõ ràng.
- [ ] KMS AccessDenied/Disabled/Timeout/429/5xx có normalized internal reason codes.
- [ ] Không leak tag/key/tenant existence trong HTTP errors; chống padding/decryption oracle và timing side channels.
- [ ] Không retry vô hạn, thử tất cả keys hoặc downgrade alg/enc để lấy plaintext.
- [ ] No-service-path fallback cho phép unverified token thành trusted token.
- [ ] Không log raw JWE/Authorization header/ID token/refresh token/plaintext/CEK/private key; trace IDs an toàn.
- [ ] Negative cache/verified-principal cache có TTL, issuer/audience/scope context và invalidation đúng.
- [ ] JWKS/recipient key refresh bounded, rate-limited và không dẫn tới SSRF.

### 27.4. Vận hành và kiểm thử

- [ ] AS và RS/RP có key rotation runbook: K2 prepublish, readiness, cutover, K1 overlap/retire.
- [ ] Emergency compromise runbook phân biệt recipient private decryption key vs issuer signing key.
- [ ] Multi-region/private key residency, IAM `Decrypt`, HSM sessions, KMS quota/HA/DR được kiểm thử.
- [ ] Token expiration, grant/revocation store và KMS/JWKS state không bị rollback trái security policy khi DR.
- [ ] CI có test good JWE, bad tag, wrong recipient, unknown `kid`, wrong alg/enc, invalid inner signature, wrong audience/scope và KMS outage.
- [ ] Spring Security test xác minh invalid JWE bị chặn ở filter chain, controller không chạy.
- [ ] KMS errors có metrics/alerts/correlation an toàn không chứa token material.
- [ ] Key-size/algorithm/JOSE library versions được quản lý, patch/advisories và negative regression tests có lịch.
- [ ] Có owner cho token profile, encryption keys, KMS/HSM, RP client registration, RS authorization và incident response.

## 28. Câu hỏi tự kiểm tra

**1. Token JWE và JWS khác nhau thế nào?** JWE bảo vệ confidentiality bằng encryption; JWS bảo vệ signature/integrity/authenticity. Nested JWT có thể kết hợp cả hai theo profile.

**2. JWE Compact có mấy phần?** Năm phần: protected header, encrypted key, IV, ciphertext và authentication tag.

**3. Trong mọi JWE, phần encrypted key có bắt buộc không rỗng?** Không. Một số `alg` như `dir` hoặc direct ECDH-ES dùng empty encrypted key theo specification.

**4. `alg` và `enc` trong JWE khác gì?** `alg` quản lý/thiết lập content encryption key; `enc` xác định content encryption algorithm như A256GCM.

**5. A256GCM cần CEK bao nhiêu bit?** 256 bit, tức 32 byte.

**6. Có thể bỏ authentication tag nếu KMS decrypt lỗi không?** Không. Điều đó phá authenticated encryption.

**7. Decrypt JWE thành công có tự chứng minh AS là issuer không?** Không với public-key encryption; cần issuer signature/trust/profile validation.

**8. Tại sao token không decrypt không thể tạo user session?** Không có verified authentication claims; làm vậy là fail-open.

**9. Một JWS JWT có cần decrypt không?** Không nếu chỉ signed JWS; cần verify signature và claims.

**10. Opaque access token được RS kiểm kiểu gì?** Qua introspection/lookup tin cậy theo AS contract, không bắt buộc decrypt.

**11. JWE tag sai thì API thường trả gì?** Không cấp quyền; Bearer invalid credential thường 401 theo RFC 6750.

**12. Token decrypt thành công nhưng thiếu scope thường trả gì?** 403/insufficient scope hoặc deny theo authorization contract.

**13. KMS timeout có nghĩa token giả không?** Không. Đó là dependency uncertainty; vẫn fail closed, có thể 503.

**14. Vì sao KMS AccessDenied cần phân loại riêng?** Nó chỉ ra IAM/key policy/security integration issue, không tự chứng minh ciphertext invalid.

**15. Vì sao không thử mọi key?** Rủi ro timing/key oracle, cross-tenant confusion, KMS/CPU DoS và che key registry bugs.

**16. `kid` có phải trust anchor không?** Không. Chỉ là key selector bên trong trusted recipient registry.

**17. Có thể tải `jku` tự khai từ JWT chưa xác minh không?** Không tùy tiện; nguy cơ SSRF và key substitution.

**18. Vì sao K2 phải sẵn có trước issuer cutover?** RS/RP cần private K2 để decrypt JWE mới; nếu chưa có sẽ gây lỗi hàng loạt.

**19. Tại sao giữ K1 trong planned overlap?** Để decrypt token K1 chưa hết hạn/được policy cho phép dùng tiếp.

**20. K1 có nên được giữ mãi không?** Không. Có retention/retirement deadline và emergency compromise response.

**21. Recipient encryption public key khác issuer signing public key như thế nào?** Một để AS mã hóa cho recipient; một để recipient kiểm inner issuer signature.

**22. Private decryption key bị lộ gây rủi ro gì?** Attacker có thể giải mã captured ciphertext/tokens; confidentiality của dữ liệu cũ có thể bị ảnh hưởng.

**23. Issuer signing private key bị lộ gây rủi ro gì?** Attacker có thể forge JWS được verifiers tin cho tới khi emergency distrust.

**24. JWE làm bearer token không thể bị replay sao?** Không. Copy toàn token JWE có thể replay dù attacker không đọc claims.

**25. mTLS/DPoP giúp gì?** Sender-constraining/ràng buộc access token với proof/cert và request, hạn chế replay khi chỉ token bị sao chép.

**26. Decrypt thành công có bỏ audience check không?** Không. Audience và resource permission phải được kiểm riêng.

**27. Expiry và revocation khác decryption thế nào?** Chữ ký/tag vẫn có thể hợp lệ sau expiry/revoke; RS phải kiểm claims/state.

**28. Một Spring Resource Server JWT decoder mặc định có luôn decrypt JWE không?** Không được giả định; cần custom JOSE decoder/profile được kiểm thử.

**29. Vì sao `@ControllerAdvice` không đủ cho filter auth errors?** Authentication failures có thể xảy ra trong Spring Security filter trước MVC controller; cần entry point/exception translation đúng.

**30. Có thể tạo `Jwt` principal từ unverified claims rồi kiểm sau không?** Không. Chỉ tạo authentication sau hoàn tất verification/validation.

**31. Vì sao AES-GCM nonce không được tái sử dụng với cùng key?** Vì reuse có thể phá confidentiality/integrity.

**32. Cần retry mãi khi KMS trả 429 không?** Không. Dùng bounded backoff/jitter/rate limits và fail closed.

**33. Vì sao không log encrypted access token?** Nó vẫn là bearer credential có thể bị replay.

**34. Vì sao không dùng raw `kid` làm metric label?** Có thể lộ metadata và gây high-cardinality/DoS vì input do attacker kiểm soát.

**35. Một JWE K2 chạy ở region A có chứng minh tất cả regions an toàn không?** Không. Phải kiểm key readiness và policy từng vùng.

**36. Nếu token sau rotation không decrypt, có nên hạ xuống `RSA1_5` không?** Không nếu ngoài approved policy; đây là downgrade và có rủi ro lịch sử.

**37. OIDC encrypted ID token lỗi phải làm gì với login?** Không tạo session, phân loại failure và khôi phục registration/key path có kiểm soát.

**38. Decrypt error và inner JWT signature error có cùng nguyên nhân không?** Không. Outer decryption và inner issuer authenticity là hai bước/trust boundaries khác nhau.

**39. Một KMS key non-exportable có bảo đảm CEK không bao giờ ở RAM RS không?** Không. Tùy key-management/unwrap API; CEK có thể ra ứng dụng dù private RSA key không xuất.

**40. Thành công của xử lý token không giải mã được được định nghĩa ra sao?** Không có unauthorized principal/business action, error classification đúng, không lộ token/keys, có phục hồi có kiểm soát và các token hợp lệ không bị từ chối ngoài security/availability contract.

## 29. Tiêu chuẩn và tài liệu tham khảo

Các nguồn sau định nghĩa các primitive, token profiles, error semantics và security guidelines. Cần đối chiếu **phiên bản thư viện/provider và token registration** thực tế trước khi triển khai.

- **RFC 7516 — JSON Web Encryption (JWE):** compact serialization năm phần, protected header/AAD, key management, ciphertext và tag validation.
- **RFC 7518 — JSON Web Algorithms (JWA):** `RSA-OAEP-256`, `A256GCM`, `ECDH-ES`, JWE/JWS algorithm parameters và key/IV/tag requirements.
- **RFC 7515 — JSON Web Signature (JWS):** signing input, protected header, signature verification, critical parameters.
- **RFC 7517 — JSON Web Key (JWK):** `kty`, `kid`, `use`/`key_ops`, public/private JWK và JWKS.
- **RFC 7519 — JSON Web Token (JWT):** registered claims, JWE/JWS JWT representations và nested JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** token typing, algorithm confusion, trusted key selection, issuer/audience validation và cross-JWT confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** token `typ=at+jwt`, issuer/audience/claims validation cho RS.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, grants, client authentication, token lifecycles.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `invalid_token`, `insufficient_scope`, `WWW-Authenticate`, bearer credential security.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque/access token status, `active` response và introspection caller protections.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke access/refresh token, token/grant state.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay, sender constraints, refresh rotation và OAuth security guidance.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** sender-bound access tokens.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** per-request proof JWT, key binding và replay protection.
- **OpenID Connect Core 1.0:** encrypted ID tokens/UserInfo response registration, signature/issuer/audience/nonce verification và RP session handling.
- **OpenID Connect Discovery/Dynamic Client Registration:** issuer/client metadata, encryption key/algorithm registration theo profile.
- **NIST SP 800-38D — Recommendation for Galois/Counter Mode (GCM):** AEAD, IV uniqueness, authentication tags và security requirements.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management:** key lifecycle, rotation, separation và compromise handling.
- **OWASP JSON Web Token Cheat Sheet:** JOSE/alg/key trust, token sidejacking, storage và rejection rules.
- **OWASP Cryptographic Storage Cheat Sheet:** authenticated encryption, key custody, GCM nonce và secure libraries.
- **OWASP Error Handling Cheat Sheet:** generic external error responses và tránh information leakage.
- **Nimbus JOSE + JWT documentation:** JWEObject, RSADecrypter, SignedJWT/JWK/JWKS, JOSE providers và nested JWT processing.
- **Spring Security OAuth2 Resource Server documentation:** JwtDecoder/opaque introspection, Bearer authentication entry points, token validation và authorization.
- **Spring Authorization Server documentation:** token generation, issuer key management, grants và token endpoint/security integration.

**Kết luận:** **“Token không giải mã được” không phải một lý do để nới lỏng xác thực.** Trước tiên phải biết endpoint mong **JWE, JWS, nested JWT hay opaque token**; nếu là JWE thì kiểm **cấu trúc năm phần, `alg`/`enc`/`kid` theo policy**, chọn đúng **recipient decryption key** và chỉ tin plaintext khi **AEAD authentication thành công**. Tiếp theo cần **xác thực issuer bằng inner JWS hoặc profile phù hợp**, kiểm `iss`, `aud`, `typ`, `exp`, scope, sender proof và grant/revocation/tenant authorization. Khi lỗi, **không tạo principal, không fallback plaintext, không bỏ tag và không log bearer token**; phân biệt invalid credential với KMS/HSM outage để trả response và điều tra đúng. Với key rotation, **provision K2 trước cutover, giữ K1 trong bounded overlap nếu hợp lệ và có emergency path khi private key bị lộ**. Hệ thống đáng tin không phải hệ thống luôn decrypt được mọi token, mà là hệ thống **chỉ cấp quyền cho token được xác minh đầy đủ, từ chối an toàn và phục hồi có kiểm soát khi crypto/key infrastructure gặp lỗi**.
