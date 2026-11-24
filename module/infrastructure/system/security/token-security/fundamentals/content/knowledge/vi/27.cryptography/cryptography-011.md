# Không tự thiết kế crypto protocol

Một thuật toán mật mã tốt **không tự tạo nên một giao thức bảo mật tốt**. Ứng dụng có thể dùng AES-256, SHA-256, RSA-3072 hoặc Ed25519 đúng cú pháp, nhưng vẫn để lộ dữ liệu, cho phép giả mạo danh tính hoặc phát lại token nếu **ghép các bước sai**, dùng lại nonce, thiếu ràng buộc danh tính/ngữ cảnh, xử lý lỗi khác nhau hoặc cho bên chưa đáng tin điều khiển thuật toán xác minh.

Ví dụ một nhóm phát minh cơ chế đăng nhập:

```text
Client:
  token = base64(userId + ":" + expiresAt + ":" + SHA256(secret + userId))

API:
  decode token
  if expiresAt > now and hash matches -> "authenticated"
```

Nhìn bề ngoài, hệ thống có một “secret”, một “hash” và thời hạn. Nhưng đây **không phải giao thức OAuth/OIDC/JWT được chuẩn hóa**, không nêu rõ thuật toán MAC, cách encode dữ liệu, ngăn cách các trường, audience, issuer, chống replay, key rotation, quản lý session, mục đích token hoặc cách thu hồi. Cơ chế còn có thể mắc lỗi **ambiguous serialization**, dùng sai hàm băm để xác thực hoặc bị tái sử dụng token ở API không intended. **Không nên triển khai** cách này làm hệ thống authentication.

Một thiết kế an toàn hơn là dùng **giao thức được chuẩn hóa, đã được phân tích công khai**, kết hợp **thư viện đáng tin và cấu hình bắt buộc rõ ràng**:

```text
Browser / Native App                  Authorization Server
        |                                      |
        | Authorization Code + PKCE           |
        |------------------------------------->|
        | authenticated subject + consent     |
        |<-------------------------------------|
        | authorization code (short-lived)    |
        |------------------------------------->|  token endpoint over TLS,
        | code + PKCE verifier                 |  client auth where appropriate
        |<-------------------------------------|
        | access token for orders-api          |
        |
        | Authorization: Bearer access_token
        v
     Resource Server
        |
        +-- verify issuer/key or introspect opaque token
        +-- verify token type, audience, expiry, scope
        +-- verify tenant/object-level authorization
        +-- check sender binding if required
        +-- reject invalid/revoked/replayed credentials
```

Ngay cả khi dùng OAuth 2.0/OIDC đúng flow, ứng dụng vẫn phải đặt **trust boundaries, chính sách thuật toán, issuer/audience và quản lý token** phù hợp. **“Không tự thiết kế crypto protocol” không có nghĩa chỉ cần cài một thư viện và mọi lỗi bảo mật biến mất**. Ý nghĩa là không phát minh cấu trúc mã hóa, trao đổi khóa, thuật toán xác thực, format token hoặc trình tự thông điệp mới chỉ để tiết kiệm công; thay vào đó **tái sử dụng chuẩn + implementation được kiểm thử, rồi cấu hình và thẩm định những điểm lựa chọn của ứng dụng**.

Bài này thuộc chương **Cryptography** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi module gồm mô hình tin cậy và vòng đời JWT/opaque token, access token/refresh token trong authentication, authorization, OAuth 2.0/OIDC; phát hành, xác minh claims/scope/audience, lưu trữ, thu hồi và chống token bị đánh cắp/phát lại. Trọng tâm là nguyên tắc **“Không tự thiết kế crypto protocol”** trong toàn bộ hành trình phát hành và sử dụng token bảo mật.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **cryptographic primitive**, **cryptographic construction**, **protocol** và **security application profile**.
2. Giải thích vì sao dùng thuật toán mạnh chưa đủ để đảm bảo **confidentiality, integrity, authenticity, freshness, authorization và replay resistance**.
3. Mô tả **threat model** của hệ thống token: attacker trên mạng, client độc hại, token theft, compromised RS, compromised keys và lỗi cấu hình.
4. Nhận diện anti-pattern: tự ghép `hash + secret`, mã hóa không xác thực, tự tạo JWT, tự viết OAuth callback, algorithm confusion, signature stripping và token substitution.
5. Chọn **TLS 1.3, OAuth 2.0 Authorization Code + PKCE, OpenID Connect, JOSE/JWT, JWE, mTLS/DPoP** đúng mục đích thay cho giao thức tự chế.
6. Phân biệt **mã hóa** với **ký/MAC** và **chứng minh danh tính/ủy quyền**; kiểm ranh giới JWS/JWE và JWT/opaque.
7. Thiết kế **message binding** đúng client, issuer, audience, session, nonce, state, code verifier, key, endpoint và phương thức HTTP.
8. Biết vì sao **canonicalization, encoding, nonce reuse, downgrade, error oracle, side channel** dễ phá hỏng giao thức.
9. Triển khai Java/Spring dùng **framework và provider tin cậy** thay tự xây token protocol; viết kiểm thử bảo mật có cả negative paths.
10. Xác định lúc nào cần **security review, protocol expert, interoperability testing** và cách migrate giao thức legacy an toàn.

## 2. Primitive, construction, protocol và profile là bốn tầng khác nhau

| Tầng | Ví dụ | Nhiệm vụ | Không tự đảm bảo |
| --- | --- | --- | --- |
| **Primitive** | AES block cipher, SHA-256, RSA, elliptic-curve operations | Phép toán mật mã cơ sở | Định dạng message, nonces, handshake, identity |
| **Construction / mode** | AES-GCM, HMAC-SHA256, HKDF, RSA-PSS | Dùng primitive để đạt tính chất như AEAD, MAC, KDF, signature | Ai có quyền dùng, chống replay ở giao thức |
| **Protocol** | TLS 1.3, OAuth 2.0 Authorization Code + PKCE, OIDC, mTLS | Quy tắc thông điệp, vai trò, thứ tự và binding | Mọi business permission hoặc policy vận hành |
| **Application profile** | OIDC client registration, JWT access-token profile RFC 9068, DPoP profile | Ràng buộc thuật toán/claims/endpoint/use case | Không tự bảo vệ app XSS, log leak hoặc resource authorization |

### 2.1. Ba câu hỏi khác nhau

1. **Primitive/construction có an toàn trong điều kiện sử dụng không?** Ví dụ AES-GCM có nonce không bị trùng theo cùng key?
2. **Protocol có cung cấp bảo đảm mong muốn không?** Ví dụ một request có được ràng buộc với đúng session, client, nonce và audience, hay thông điệp hợp lệ ở session A bị dùng tại session B?
3. **Ứng dụng có thực thi policy đúng không?** Ví dụ access token có scope `orders:read` nhưng API bỏ kiểm tenant và trả orders của người khác.

Thất bại ở bất cứ tầng nào cũng có thể gây vi phạm. Không thể nói “đã dùng AES-256 nên giao thức đăng nhập an toàn”.

### 2.2. Security properties cần định nghĩa chính xác

| Thuộc tính | Câu hỏi kiểm chứng |
| --- | --- |
| **Confidentiality** | Bên không có key có đọc nội dung không? |
| **Integrity** | Dữ liệu bị thay đổi có bị phát hiện không? |
| **Message authentication** | Thông điệp có thực sự do bên nắm key/identity mong đợi tạo không? |
| **Entity authentication** | Bên đối thoại có được xác thực là client, server hoặc end user đúng không? |
| **Freshness** | Thông điệp thuộc transaction/thời điểm hiện tại hay bản cũ? |
| **Replay resistance** | Bản sao hợp lệ từ trước có thể được dùng lại trái phép không? |
| **Key confirmation / binding** | Đúng khóa, đúng đối tác và đúng session đã được thỏa thuận chưa? |
| **Authorization** | Subject/client có được làm hành động này trên resource này không? |
| **Revocability** | Sau sự kiện thu hồi, token còn được RS chấp nhận bao lâu? |
| **Downgrade resistance** | Attacker có làm hai bên chuyển sang thuật toán/profile yếu hơn không? |

Một **digital signature** có thể kiểm message authenticity với đúng key, nhưng **không tự ngăn phát lại**: chữ ký của một request cũ vẫn đúng khi attacker gửi lại nguyên byte. **TLS** có thể bảo vệ đường truyền nhưng **không tự kiểm client được truy cập order nào**. **OAuth consent** có thể cấp scope nhưng **không biến bearer token thành sender-constrained**.

## 3. Vì sao tự thiết kế giao thức có chi phí bảo mật khó thấy?

Giao thức mật mã phải an toàn trước **đối thủ chủ động**, không chỉ trong thử nghiệm "client và server đều hành xử đúng". Người tấn công có thể:

- Gửi message sai định dạng/khác thứ tự, trùng lặp field hoặc message quá lớn.
- Quan sát/copy thông điệp hợp lệ rồi **replay** hoặc trộn từ nhiều sessions.
- Thay `client_id`, `redirect_uri`, `aud`, `alg`, `kid`, `scope` hoặc URL để tìm đường binding yếu.
- Đưa hệ thống vào **outage, retry, race condition** hay trạng thái handshake chưa hoàn tất.
- Tấn công parser, timing/error behavior, encoding Unicode/URL/JSON/JWT.
- Xâm nhập một thành phần như browser/RS/client nhưng **chưa** có private key của AS.
- Tận dụng thuật toán cũ trong hỗn hợp key rotation/migration.

Nếu một giao thức mới chỉ được kiểm bằng kịch bản happy path, lỗi thường nằm ở **trình tự**, **ràng buộc**, **trạng thái giữa các bước** và **negative paths** hơn là phép toán mã hóa.

### 3.1. “Tự viết crypto” và “tự ghép crypto” đều có rủi ro

Hai sai lầm:

```text
DIY primitive:
  Write custom AES/RSA/HMAC from scratch.

DIY protocol:
  Use standard AES/HMAC libraries,
  but invent handshake, nonce format, key exchange,
  packet order, token grant rules and replay semantics.
```

**Cả hai đều cần tránh** trong sản phẩm thông thường. Với giao thức thực sự mới (nghiên cứu/chuyên dụng), quy trình phải có security architecture, formal/informal cryptanalysis, peer review, test vectors, independent audit và tiêu chí triển khai/migration; **không phải bài tập CRUD với deadline gấp**.

### 3.2. Đúng mỗi thành phần nhưng sai khi ghép

Giả sử API dùng:

```text
1) Encrypt userId with AES-CBC.
2) Send ciphertext to client.
3) Client returns ciphertext as login token.
4) Server decrypts and trusts userId.
```

Điểm sai: **AES-CBC encryption không tự xác thực ciphertext**, không có issuer/audience/expiry/scope, không chống replay, không có grant/revocation semantics. Dù AES nguyên thủy không bị phá, **cấu trúc token có thể không đáp ứng authentication**.

Tương tự, dùng một API RSA ký đúng mà không kiểm algorithm/type hoặc trust anchor vẫn có thể chấp nhận JWT giả từ key lạ. **Khóa mạnh không sửa giao thức sai**.

## 4. Bắt đầu bằng threat model trước khi chọn công nghệ

Không thể đánh giá giao thức chỉ bằng danh sách thuật toán. Trước tiên xác định **ai tin ai, tài sản nào cần bảo vệ và attacker kiểm soát gì**.

### 4.1. Ví dụ: hệ thống gọi API bằng access token

```mermaid
flowchart LR
    U[End User] --> B[Browser or Native Client]
    B -->|Authorization Code + PKCE| AS[Authorization Server / OP]
    AS -->|Access token| B
    B -->|Authorization: Bearer| GW[API Gateway]
    GW --> RS[Orders Resource Server]
    RS --> DB[(Orders Data)]
    AS -->|JWKS or Introspection| RS
```

**Trust boundaries:**

1. **User-agent ↔ AS:** user authentication, login UX, state/nonce/PKCE, redirect URI.
2. **Client ↔ token endpoint:** TLS, authorization code one-time, PKCE verifier, client authentication nếu có.
3. **Client ↔ RS:** token transport, audience/scope, session, bearer theft/sender proof.
4. **RS ↔ AS/JWKS/introspection:** issuer trust, key validation, token active state.
5. **RS ↔ data:** tenant, ownership, object-level authorization.
6. **Services ↔ logs/telemetry:** credentials/PII không được lộ qua debugging.

### 4.2. Một số giả định cần ghi rõ

| Giả định | Nếu sai thì sao? |
| --- | --- |
| AS private signing key không bị lộ | Attacker có thể forge tokens dưới public key đã tin |
| Client giữ PKCE verifier đúng transaction | Authorization code bị chặn có thể bị đổi trái phép nếu thiếu PKCE |
| RS chỉ tin public key của issuer đã cấu hình | Attacker có thể tráo JWKS/key và ký token giả |
| Token audience được kiểm | Token của API A có thể được dùng tại API B |
| User consent/step-up đã hoàn tất trước issuance | Token có thể cấp trước khi authentication/authorization đạt |
| RS không log raw bearer token | Token bị sao chép có thể replay ngoài kênh hợp lệ |
| Kết quả active/revoked đủ mới | Token bị thu hồi vẫn được chấp nhận do cache |

### 4.3. Đừng chọn “bí mật là internal network”

Một protocol tự chế thường giả định các service đều tin nhau vì nằm trong VPC. Nhưng SSRF, compromised service, leaked credential, CI access, lateral movement hoặc cấu hình proxy sai có thể làm biến mất giả định đó. **Phân đoạn mạng giúp giảm rủi ro nhưng không thay entity authentication, TLS, audience và authorization**.

## 5. Ưu tiên giao thức/profile được chuẩn hóa và bảo trì

Khi có nhu cầu cụ thể, lựa chọn đầu tiên nên là **một chuẩn phù hợp đã được review công khai**, không tự viết một “mini OAuth” hoặc “TLS lite”.

| Mục đích | Lựa chọn thích hợp | Tránh tự chế |
| --- | --- | --- |
| Bảo vệ giao tiếp mạng client/server | **TLS 1.3** hoặc cấu hình TLS phù hợp chính sách | XOR/AES+JSON tự tạo trên HTTP |
| Đăng nhập user bên ngoài qua OP | **OIDC Authorization Code + PKCE**, client library tin cậy | Login bằng chuỗi email/hash trong query |
| Ủy quyền API delegated user | **OAuth 2.0** và security profile hiện hành | Tự nhét `role=admin` vào token chưa verify |
| Xác thực service-to-service | OAuth Client Credentials/mTLS/workload identity theo architecture | Shared “internal” password truyền trong header tự đặt |
| JWT signature/interoperability | **JWS/JWT theo JOSE**, RFC 8725, library tin cậy | JSON + SHA-256 + Base64 “ký tay” |
| JWT claims bí mật | **JWE** khi profile cần, hoặc tránh đặt secret/PII trong JWT | AES-CBC ciphertext dùng trực tiếp làm identity proof |
| Server hỏi token còn active | **RFC 7662 introspection** | Cache boolean `tokenExists=true` không có revoke model |
| Thu hồi token | **RFC 7009**, grant/token family policy | Xóa cookie frontend rồi gọi là token revoked |
| Ràng buộc token với bên giữ khóa | **mTLS-bound tokens / DPoP (RFC 8705/9449)** | Tự ký header `Device-ID` bằng string đoán được |
| Derive independent subkeys | **HKDF (RFC 5869)**/vetted KDF khi đúng use case | `SHA256(master + purpose)` tự phát minh |
| Mã hóa dữ liệu ở tầng ứng dụng | **AEAD (AES-GCM/ChaCha20-Poly1305)** qua managed crypto SDK | AES-ECB/CBC không MAC, IV reuse |
| Lưu mật khẩu | **Argon2id hoặc PBKDF2/bcrypt/scrypt theo chính sách** | SHA-256(password) không salt rồi dùng như credential |

**“Chuẩn” không đồng nghĩa luôn chọn theo thói quen**: TLS 1.3, OAuth 2.0 và OIDC giải quyết mục tiêu khác nhau; không triển khai tất cả nếu không cần. Một hệ thống service-only có thể dùng mTLS/workload identity và OAuth Client Credentials **mà không có OIDC end-user login**.

### 5.1. Chuẩn cũng có version và profile

Ví dụ:

- OAuth 2.0 có nhiều grant types; **Implicit Flow** hoặc Resource Owner Password Credentials không phải lựa chọn mới mặc định cho ứng dụng hiện đại.
- PKCE dùng `S256` theo best practice; không coi việc client tự gửi `code_verifier` trong HTTP header tùy ý là PKCE.
- JOSE/JWT có nhiều thuật toán/serializations; **RFC 8725** hướng dẫn validation, algorithm policy, cross-JWT confusion.
- TLS phải được cấu hình trust/cipher/hostname validation phù hợp; bật HTTPS nhưng tắt certificate validation là sai.
- JWE hỗ trợ nhiều key management/content encryption algorithms; không bật mọi lựa chọn legacy chỉ để “compatible”.

Ưu tiên **bản chuẩn và implementation được bảo trì, có security advisories và compatibility matrix**, không sao chép đoạn code từ bài viết cũ rồi coi là giao thức cập nhật.

## 6. Nguy cơ thứ nhất: tự tạo token bằng Base64, hash hoặc encryption

### 6.1. Base64 không có bảo mật

```text
payload = base64url("{\"sub\":\"user-42\",\"role\":\"admin\"}")
```

Bất kỳ ai có token đều có thể đọc và tạo payload mới. **Encoding không phải signing hoặc encryption**. Nếu server tin payload chỉ vì decode hợp lệ, attacker có thể tự ghi role.

### 6.2. Hash thuần không xác thực nguồn gốc

```text
token = base64url(payload) + "." + hex(SHA256(payload))
```

Vì SHA-256 là hàm công khai, attacker thay payload rồi tính digest mới. **HMAC** có secret mới cung cấp MAC, nhưng tự viết format HMAC token vẫn cần key/serialization/issuer/audience/expiry/replay policy; trong OAuth nên dùng **vetted token service** thay phát minh format.

### 6.3. `SHA256(secret || message)` không thay HMAC

Một lối tự chế là ghép `secret + message` rồi SHA-256. Cách làm đó **không phải HMAC chuẩn**, và các cấu trúc prefix-MAC dựa trên một số hàm băm Merkle–Damgård có thể gặp vấn đề length-extension nếu dùng sai. **HMAC** được chuẩn hóa để tránh lớp lỗi này; khi cần MAC, dùng HMAC chuẩn qua library và key đủ entropy, không tạo construction tùy ý.

### 6.4. Encryption không chứng minh ai cấp token

Mã hóa một chuỗi `user_id` bằng AES rồi gọi đó là “session token” có thể thiếu:

- **Integrity/authentication** nếu dùng mode không AEAD.
- **Purpose/audience**: token dành API nào?
- **Time/TTL**: còn dùng được khi nào?
- **Anti-replay**: bản cũ bị chặn ra sao?
- **Revoke**: user logout/revoke rồi RS biết thế nào?
- **Key rotation**: token cũ giải mã bằng key nào, hết trust lúc nào?

Một ứng dụng có thể dùng **opaque high-entropy reference token** được AS phát và quản lý server-side, hoặc chuẩn JWS/JWE/JOSE phù hợp. **Không tự chế ciphertext làm bearer authorization credential**.

### 6.5. JWT có chữ ký chưa đồng nghĩa access token hợp lệ

Với JWT:

```text
header.payload.signature
```

RS phải kiểm **signature theo thuật toán/key trust được pin**, sau đó kiểm `iss`, `aud`, `exp`/`nbf`, token `typ`/purpose, scope/client/tenant và authorization tài nguyên. Một JWT ký hợp lệ cho `profile-api` **không thể dùng** tại `payments-api` chỉ vì cùng AS.

## 7. Nguy cơ thứ hai: tự ghép encryption và authentication

### 7.1. AES-ECB làm rò cấu trúc

AES-ECB mã hóa các block giống nhau thành ciphertext blocks giống nhau dưới cùng key, làm lộ pattern. **Không dùng ECB để bảo vệ dữ liệu ứng dụng hoặc làm token format**. Với dữ liệu cần confidentiality + integrity, ưu tiên AEAD chuẩn.

### 7.2. AES-CBC không MAC có thể bị sửa hoặc làm lộ oracle

Encryption **không tự cung cấp integrity**. Nếu một API giải mã AES-CBC rồi trả lỗi khác nhau giữa "padding sai" và "user không tồn tại", attacker có thể tận dụng **error oracle** trong một số mô hình.

```text
BAD:
  ciphertext = AES-CBC(key, iv, plaintext)
  server accepts decrypted plaintext without authenticating it

PREFERRED:
  use vetted AEAD construction with key, nonce/IV, ciphertext,
  authentication tag and authenticated associated data (AAD).
```

Không tự viết "encrypt then hash", "MAC then encrypt" hoặc "encrypt then MAC" theo một packet format ad hoc. Các thứ tự composition có những điều kiện bảo mật riêng; **dùng AEAD primitive và message format đã được quy định/test** thay vì tự phát minh serialization.

### 7.3. AES-GCM có điều kiện nonce cực quan trọng

Với AES-GCM, **không được tái sử dụng cùng nonce/IV với cùng key**. Key mạnh 256 bit **không cứu** việc reuse nonce. Với AEAD, phải:

- Dùng **nonce generation strategy theo library/protocol**, bảo đảm uniqueness per key.
- Kiểm authentication tag **trước khi tin plaintext**.
- Dùng `AAD` để ràng buộc metadata không mã hóa nhưng cần xác thực (ví dụ version, tenant context, message type) theo profile.
- Quản lý key rotation và sequence/persistence khi dùng counter-based nonces.
- Không tự cắt/ghép tag, IV, key hay ciphertext tùy ý.

### 7.4. JWE không chỉ là gọi `Cipher.doFinal`

JWE định nghĩa key-management `alg`, content encryption `enc`, protected header, encrypted key, IV, ciphertext, tag và serialization. Nếu tự “JWE-compatible” bằng việc gộp AES output vào JWT 3 phần, sẽ **không còn profile/interoperability** mong đợi.

Với nested signed-and-encrypted JWT, thường ký nội dung bằng JWS rồi mã hóa bằng JWE theo profile. **Decrypt thành công không tự xác minh issuer**, vì người có public encryption key có thể tạo ciphertext; RP cần validate inner JWS và claims nếu trust contract yêu cầu.

## 8. Nguy cơ thứ ba: nonce, freshness và chống replay thiếu ràng buộc

Một chữ ký/MAC hợp lệ chứng minh **message chưa bị sửa**, không chứng minh message thuộc **transaction hiện tại**. Attacker có thể copy request hoặc token hợp lệ rồi gửi lại.

### 8.1. Nonce không chỉ là “số ngẫu nhiên”

Một nonce là giá trị được dùng theo **ngữ nghĩa protocol cụ thể**:

- Với **AES-GCM**, yêu cầu then chốt là **unique key–nonce pair**.
- Với **OIDC**, `nonce` ràng buộc ID token với authentication request của RP khi được dùng/yêu cầu.
- Với **DPoP**, AS có thể phát nonce cho client proof; proof còn có `jti`/`iat` và request binding.
- Với một challenge–response protocol được chuẩn hóa, nonce thường ngăn replay của câu trả lời cũ sang phiên mới.

Không thể kết luận “thêm trường `nonce` vào JSON thì đã chống replay”. **Bên kiểm phải tạo/ghi nhớ hoặc xác minh giá trị đúng session/không lặp theo policy**.

### 8.2. Timestamp không đủ chống replay

```text
request = {
  "action": "transfer",
  "amount": 1000000,
  "timestamp": now
}
signature = Sign(privateKey, request)
```

Nếu server chấp nhận signature trong một cửa sổ 5 phút và **không kiểm request ID/nonce one-time**, attacker có thể gửi lại cùng request nhiều lần trong 5 phút. **Timestamp có tác dụng giới hạn độ tuổi, không tự bảo đảm at-most-once semantics**.

### 8.3. Request replay và token replay là hai lớp khác

- **Bearer access token:** copy token còn hạn có thể cho attacker gửi request mới được phép, trừ khi có sender binding/controls.
- **Authorization code:** phải short-lived, one-time và PKCE/client binding; code bị đánh cắp không nên đổi được ngoài client/transaction.
- **Refresh token:** rotation, client binding, reuse detection và revocation theo policy.
- **DPoP proof:** xác minh `htu`, `htm`, `iat`, `jti`, nonce khi áp dụng, `ath`/key binding; không chỉ signature.
- **Business command:** idempotency keys/transaction constraints có thể cần riêng để tránh double charge ngay cả khi authentication đúng.

**Không lấy `jti` của access token làm bằng chứng mỗi API request mới duy nhất**: token có thể được dùng hợp lệ nhiều lần. Replay defense phải phù hợp **loại credential và semantics**.

### 8.4. State machine làm rõ lúc nào được phát token

```mermaid
stateDiagram-v2
    [*] --> REQUEST_VALIDATED
    REQUEST_VALIDATED --> AUTHENTICATION_PENDING
    AUTHENTICATION_PENDING --> AUTHENTICATED: Subject verified
    AUTHENTICATED --> CONSENT_PENDING: Need consent
    CONSENT_PENDING --> APPROVED: Consent and policy complete
    AUTHENTICATED --> APPROVED: Valid pre-existing grant
    APPROVED --> CODE_ISSUED: Registered redirect + binding
    CODE_ISSUED --> CODE_CONSUMED: Valid one-time PKCE exchange
    AUTHENTICATION_PENDING --> DENIED: Fail or cancel
    CONSENT_PENDING --> DENIED: Deny or timeout
    DENIED --> [*]
    CODE_CONSUMED --> [*]
```

Đây là mô hình đơn giản cho OAuth/OIDC code flow. Một hệ thống có MFA/step-up cần trạng thái riêng: **không có đường từ `AUTHENTICATION_PENDING`, `CONSENT_PENDING` hoặc `STEP_UP_PENDING` sang token issuance** khi chưa hoàn tất policy. Tạo JWT cryptographically valid **trước** khi xác thực/consent hoàn tất là lỗi giao thức, không phải lỗi thuật toán ký.

## 9. Nguy cơ thứ tư: ràng buộc sai danh tính, channel và ngữ cảnh

### 9.1. Những trường cần binding

Một giao thức an toàn phải xác định **thông điệp ký/MAC bảo vệ chính xác điều gì**:

| Binding | Ví dụ | Nếu thiếu |
| --- | --- | --- |
| **Issuer** | `iss=https://id.example.test` | Token AS khác có thể bị chấp nhận |
| **Recipient/audience** | `aud=orders-api` | Token API A dùng tại API B |
| **Client** | `client_id=storefront-web` | Code/grant/token bị chuyển client |
| **Subject** | `sub=user-42` sau xác minh | Account/tenant swapping |
| **Transaction** | `state`, PKCE verifier, OIDC nonce | Callback/login/replay từ phiên khác |
| **HTTP method/URL** | DPoP `htm`/`htu` | Proof cho GET bị dùng vào POST/endpoint khác |
| **Token hash** | DPoP `ath` | Proof hợp lệ bị gắn với token khác |
| **Expiry/not-before** | `exp`, `nbf` | Token/messages sống ngoài thời hạn |
| **Grant/scope** | `orders:read` | Quyền bị mở rộng sau issuance |
| **Tenant/resource** | Tenant A, order 42 | Cross-tenant/data ownership bypass |
| **Sender/key** | mTLS certificate/`cnf`, DPoP thumbprint | Bearer token bị copy và replay |

**Một HMAC đúng trên `amount` nhưng không ký `currency` hoặc `recipient` không bảo vệ toàn bộ lệnh chuyển tiền**. Khi xây ứng dụng, dùng giao thức message binding đã chuẩn hóa hoặc ký payload theo **profile xác định đầy đủ các trường có ảnh hưởng đến security decision**.

### 9.2. Unknown key-share/identity misbinding

Trong các giao thức trao đổi khóa hoặc đăng nhập liên kết, hai bên có thể cùng sở hữu một key/session có vẻ hợp lệ nhưng **không đồng ý ai là đối tác đang trao đổi** nếu identity/transcript không được ràng buộc đúng. Những lỗi này được gọi theo nhiều mô hình như **identity misbinding / unknown-key share**.

Lựa chọn đáng tin là **TLS với hostname/certificate validation**, OAuth client registration/redirect URI/issuer binding và các chuẩn proof phù hợp, thay tự thiết kế handshake “server gửi nonce, client ký là xong”.

### 9.3. Không dùng user-controlled key ID làm trust

JWT header `kid` giúp chọn public key **trong trust set được cấu hình**. Nó không là “chứng chỉ uy tín” do token tự tạo. Header `jku`/`x5u` trỏ URL ngoài nếu được thư viện tự động tải mà không pin có thể gây **key substitution, SSRF và exfiltration**.

```text
BAD:
  read JWT header.jku from unverified token
  download that JWKS
  verify signature using attacker's key

GOOD:
  trusted issuer/profile configured out-of-band
  JWKS URI pinned to issuer registration / trusted discovery
  key selected by kid inside that trusted key set
  algorithm, type, issuer, audience and claims all checked
```

### 9.4. Channel binding không phải mọi thứ

TLS mã hóa và xác thực kênh nhưng nếu bearer token rò qua browser XSS, log hoặc analytics, attacker có thể dùng token trên **một TLS connection khác**. Khi threat model cần chống copy, mTLS-bound access token hoặc DPoP có thể giúp ràng buộc token với sender key/certificate. **Cả hai cần proof verification**, không chỉ có `cnf` trong token.

## 10. Nguy cơ thứ năm: protocol downgrade và algorithm confusion

### 10.1. Thuật toán từ header không phải policy

```text
JWT header:
  alg = HS256 | RS256 | PS256 | ES256 | none
  kid = arbitrary-string
```

Header được parse **trước khi verify signature** và do sender kiểm soát. Verifier chỉ nên dùng `alg`/`kid` như **input để kiểm match** với chính sách tin cậy, không để chúng mở rộng algorithm allowlist hoặc chọn khóa từ nơi bất kỳ.

### 10.2. `alg=none` và HS↔RSA confusion

Những lỗi nổi tiếng:

- Verifier chấp nhận `alg=none` rồi coi JWT không ký là authenticated token.
- Verifier chấp nhận `HS256` trong khi expected asymmetric RSA; dùng **RSA public key bytes** (công khai) như HMAC secret.
- Verifier chọn algorithm/key từ JWT của attacker mà không pin issuer/token type.
- Một JWT ID token được dùng thay OAuth access token vì cùng issuer/signature.

**Phòng:** pin allowed algorithms theo issuer/profile, kiểm key type/length, không dùng generic HMAC secret fallback, kiểm `typ`/audience và cross-JWT confusion theo **RFC 8725**.

### 10.3. Đừng tự tạo protocol version fallback

Một client thấy `PS256` verification fail rồi retry `HS256` hoặc “disable signature check để hỗ trợ old provider” là **downgrade đường bảo mật**. Migration có thể tạm hỗ trợ hai thuật toán **chỉ khi rõ issuer, key ID, token profile, thời hạn và có security approval**.

### 10.4. Cẩn trọng với canonicalization

Hai bên có thể nhìn **cùng đối tượng JSON về ý nghĩa** nhưng ký trên bytes khác nhau:

```json
{"amount":100,"currency":"VND"}
```

và

```json
{ "currency": "VND", "amount": 100 }
```

Thứ tự field, whitespace, number formats, Unicode normalization, duplicate JSON keys và encoding khiến bytes khác nhau. Nếu tự viết “canonical JSON signer”, client/server có thể diễn giải khác nhau hoặc attacker lợi dụng **parser differential**.

**JWS ký trên chuỗi byte đã được định nghĩa bởi JOSE**; library phải tạo/verify đúng signing input. Đừng “verify object bằng parse lại rồi serialize theo ý mình” nếu profile không quy định canonicalization. Với custom signed business messages, chọn **một định dạng canonical được chuẩn hóa với test vectors và review**, không tự phát minh.

## 11. Nguy cơ thứ sáu: key derivation và key separation tự chế

Một master secret có thể được dùng để sinh nhiều khóa con nhưng **không nên** viết:

```text
tokenKey = SHA256(masterKey + "token")
cookieKey = SHA256(masterKey + "cookie")
dbKey = SHA256(masterKey + "database")
```

Đây là một construction tự thiết kế với serialization và giả định không được chứng minh. Khi cần KDF từ key material đã có entropy đủ, sử dụng **HKDF (RFC 5869)** hoặc KDF đã được profile chuẩn hóa, có **salt, context/info và output length** đúng specification. Với password do người dùng nhập thì **không dùng HKDF như thay thế password hashing**; cần memory-hard password hashing như Argon2id hoặc approved KDF theo bối cảnh.

### 11.1. Domain separation là gì?

**Domain separation** nhằm ngăn cùng key material được dùng nhầm giữa hai chức năng. Ví dụ:

```text
master key (KMS-managed, high entropy)
  |
  +-- HKDF context: "jwt-signature-v1" -> K_sign
  |
  +-- HKDF context: "audit-mac-v1"     -> K_audit
  |
  +-- HKDF context: "token-digest-v1"  -> K_lookup
```

Đây là **mô hình khái niệm**, không phải chỉ thị bắt buộc tạo mọi signing key bằng HKDF. Với RSA/EC private signing keys, **keypair generation phải theo thuật toán/provider thích hợp**, không tự cắt bytes HKDF thành RSA/EC private key. Nhiều trường hợp đơn giản hơn và an toàn hơn là tạo **khóa độc lập trong KMS/HSM** theo đúng purpose.

### 11.2. Key reuse phá các ranh giới

Không nên dùng một HMAC secret cho cả:

- JWT HS256 signing.
- Webhook signatures.
- Cookie session integrity.
- Opaque token database lookup.
- Password reset link MAC.

Nếu một bên liên quan webhook biết secret để verify, họ có thể giả MAC cho các mục đích khác nếu protocol dùng cùng secret/format. **Tách keys theo use case, môi trường, issuer, client và trust boundary**, không chỉ thêm string prefix trong payload mà vẫn chia sẻ quyền sign một cách vô hạn.

### 11.3. Độ dài/entropy khóa không đủ khi key leaked

Một HS256 secret 32 byte từ CSPRNG có thể rất khó brute force, nhưng nếu bị **log ra CI, đóng trong mobile binary hoặc gửi đến nhiều RS**, attacker không cần brute force. Key management cần:

- Sinh/rotate bằng CSPRNG hoặc KMS/HSM phù hợp.
- Lưu secret trong secret manager và giữ private signing keys non-exportable khi policy cần.
- Chỉ cấp **sign** cho issuer, **verify** cho RS (public keys khi dùng asymmetric).
- Không dùng cùng signing key giữa dev/test/prod.
- Bảo vệ backup, key logs, metrics, crash dumps, traces và support tickets.
- Có emergency distrust/rotation policy khi lộ khóa.

### 11.4. Random bytes và IDs

Ngẫu nhiên mật mã phải dùng **CSPRNG**, không dùng `Math.random()` hay predictable timestamp để làm access token/session secret/nonce/challenge. Nhưng CSPRNG **không tự quản lý uniqueness** cho counter-based AEAD IV hoặc anti-replay memory; cần protocol-specific policy và state.

## 12. Nguy cơ thứ bảy: thứ tự xử lý và các kênh lỗi

Ngay cả khi mọi phép toán crypto đều chuẩn, **thứ tự kiểm tra** cũng quan trọng.

### 12.1. Không tin plaintext trước khi tag/authentication hoàn tất

Trong một luồng AEAD:

```text
Receive: header + nonce + ciphertext + tag
    |
    v
Validate message/frame length and allowed algorithms
    |
    v
Authenticated decryption: verify tag
    |
    +--> failure: reject without using any plaintext
    |
    v
Process plaintext only after integrity/authenticity succeeds
```

Không giải mã CBC rồi thực thi business action trước khi kiểm MAC. Không bỏ tag vì “nội dung JSON parse đúng”. Với streaming authenticated encryption, phải chú ý khi nào plaintext thực sự được authenticated theo **profile/library**.

### 12.2. Không parse untrusted JWT thành authenticated principal

Một số thư viện cho phép **parse JWT mà chưa verify** để đọc header/claims. Điều đó có thể cần cho key selection hoặc diagnostics, nhưng giá trị **chưa được tin**.

```java
// SAI: chỉ decode claims rồi tạo session.
var claims = decodeJwtPayloadWithoutVerification(token);
if (claims.containsKey("sub")) {
    createUserSession(claims.get("sub"));
}
```

Đúng là **verify JWS với trusted key/algorithm, issuer, audience, expiry, token type và các policy** trước khi tạo authenticated principal. Một `sub` nhìn đúng định dạng không chứng minh danh tính.

### 12.3. Error messages cũng là một phần protocol

Nếu một server trả:

```text
"wrong RSA key"        -> 401
"padding invalid"      -> 400 with long detailed body
"user identifier valid"-> 403
"token MAC wrong"      -> 500
```

thì **khác biệt lỗi, timing và side effects** có thể rò thông tin trong một số threat models. Không tự phân biệt chi tiết “token tồn tại”, “chữ ký sai” và “user tồn tại” ra response công khai. Cung cấp **reason code an toàn cho audit** và thông báo lỗi công khai theo chuẩn (ví dụ RFC 6750 `invalid_token`) mà không lộ credential/key material.

### 12.4. Constant-time comparison và side channels

Khi bắt buộc tự so sánh **MAC/digest bí mật**, cần dùng API so sánh time-resistant thích hợp của platform, không tự viết vòng lặp “return false ở byte đầu sai”. Nhưng **dùng constant-time compare không sửa protocol sai**; quan trọng là thư viện crypto hoàn chỉnh đúng và kết quả so sánh không để lộ dữ liệu qua lỗi/timing/branch khác.

### 12.5. Invalid data phải fail closed

Một số lỗi phải dẫn tới **không cấp quyền**:

- Không đọc được key hoặc JWKS tin cậy.
- Crypto library báo signature/MAC/tag invalid.
- Algorithm không nằm trong allowlist.
- Token audience/issuer/type thiếu hoặc không đúng.
- PKCE verifier/state/nonce không khớp.
- Consent/MFA chưa hoàn thành.
- Introspection outage không có trạng thái active đáng tin khi policy yêu cầu.

Không tạo fallback “catch all Exception → allow because internal request”.

## 13. Không tự viết OAuth/OIDC flow

OAuth 2.0/OIDC là các **authorization/authentication protocols**, không chỉ là cách phát một JWT sau khi user nhập password.

### 13.1. Authorization Code + PKCE có nhiều ràng buộc

Các bước chính:

```mermaid
sequenceDiagram
    actor U as End User
    participant C as OAuth Client / RP
    participant AS as Authorization Server / OP
    participant RS as Resource Server
    C->>C: Generate state + S256 code_verifier/challenge
    C-->>U: Redirect to trusted /authorize
    U->>AS: Authorization request + registered redirect
    AS->>U: Authentication + MFA/consent as required
    U-->>AS: Complete required steps
    AS->>AS: Check client/subject/scope/resource/policy
    AS-->>C: Authorization code + state through callback
    C->>C: Validate state and expected issuer/transaction
    C->>AS: POST /token, code + verifier + client authentication if required
    AS->>AS: Consume one-time code, verify PKCE, bindings, grant state
    AS-->>C: Access token (+ ID/refresh token if allowed)
    C->>RS: Send access token for RS audience
    RS->>RS: Verify issuer/type/audience/time/scope/policy
    RS-->>C: Authorized response or deny
```

Khi tự làm callback “nhận `?code=...` rồi gọi token endpoint”, developer dễ quên:

- `state` và browser transaction binding, chống login CSRF.
- `code_verifier`/`code_challenge=S256`, one-time code.
- Exact registered `redirect_uri`, không open redirect.
- Expected authorization server issuer, multi-AS mix-up defense.
- Confidential client authentication tại token endpoint.
- User authentication, MFA/step-up, consent và grant authorization gate.
- OIDC `nonce` và ID token validation khi áp dụng.
- Token storage/rotation/revocation, callback URL/referrer/log safety.

### 13.2. `state`, `nonce` và PKCE không thay nhau

| Thành phần | Ràng buộc/chức năng | Không thay thế |
| --- | --- | --- |
| **`state`** | Client liên kết authorization response với transaction/user-agent state và CSRF defense | PKCE verifier/token audience |
| **PKCE** | Ràng buộc đổi authorization code với client giữ `code_verifier` | User consent, OIDC nonce, client identity |
| **OIDC `nonce`** | Liên kết ID token với authentication request khi được gửi/yêu cầu | Exact redirect URI, PKCE |
| **`iss`/AS binding** | Chống nhầm authorization server/issuer | Scope/resource authorization |
| **`aud`** | Token dành client/RS nào | Revocation, sender proof |

Không “tối ưu” bằng cách dùng **một giá trị random duy nhất** cho mọi trường khi chuẩn/security profile yêu cầu giá trị/chức năng riêng. Tách transaction artifacts với TTL và storage phù hợp.

### 13.3. Token endpoint có cấu trúc giao thức chuẩn

Với OAuth 2.0 token endpoint, một request điển hình:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_TEST_PLACEHOLDER

grant_type=authorization_code&code=CODE_TEST_ONLY&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=VERIFIER_TEST_ONLY
```

Đây là **mẫu minh họa**, placeholder không có giá trị dùng thật. Không tự phát minh token endpoint nhận JSON và các key tùy ý nếu đang tuyên bố tuân OAuth profile; không đặt code/verifier/refresh token vào URL hoặc log.

### 13.4. Bắt đầu bằng client SDK và AS có chuẩn

**Trong Java/Spring**, dùng Spring Security OAuth2 Client/OIDC login cho RP, Spring Security Resource Server cho API, và Authorization Server framework được bảo trì nếu tổ chức thật sự cần vận hành AS. **Không tự viết code để mint JWT từ một controller `/login`** nếu mục tiêu là OAuth 2.0/OIDC federation.

Tuy nhiên vẫn cần cấu hình:

- Issuer URI và client registration đúng môi trường.
- Redirect URI exact match và trusted reverse proxy headers.
- PKCE S256 theo profile/phiên bản thư viện.
- Token persistence/secrets và HTTP/TLS timeouts.
- Audience/scope/tenant validation.
- Logout, refresh rotation, revocation/fail-closed behavior.

## 14. Java/Spring: ví dụ RP OIDC thay cơ chế login tự chế

Một ứng dụng Spring Boot server-side có thể dùng cấu hình:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-id:
            provider: corporate-op
            client-id: storefront-web
            client-secret: REPLACE_WITH_MANAGED_SECRET
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          corporate-op:
            issuer-uri: https://id.example.test
```

Đây là **ví dụ cấu hình**, không chứa secret thật. Các phiên bản Spring Security có hành vi PKCE/nonce/provider validation và các options khác nhau; cần xác nhận **PKCE S256** được bật/thi hành theo yêu cầu security profile cả với confidential client. Không dùng `http://localhost` callback ở production public.

### 14.1. Filter chain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcLoginSecurity {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Filter chain này **không là toàn bộ cấu hình production**. Phải xác minh session cookie/CSRF/forwarded headers, token security, app roles và tenant policy. **Không chuyển từ "tự viết OAuth" sang "cài framework rồi tắt CSRF, state, nonce hoặc JWT verification để sửa lỗi"**.

### 14.2. Sử dụng `OidcUser` đã được framework xác minh

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {
    @GetMapping("/me/identity-key")
    String identityKey(@AuthenticationPrincipal OidcUser user) {
        if (user == null || user.getIdToken() == null) {
            throw new IllegalStateException("OIDC login required");
        }
        // Minh họa: một identity cần cả issuer lẫn subject.
        // Production nên map sang internal user ID, tránh lộ raw key nếu không cần.
        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getSubject();
        return issuer + "|" + subject;
    }
}
```

**Không sử dụng email làm immutable identity key**, vì có thể thay đổi/trùng giữa các OP. `OidcUser` ở ví dụ là principal được tạo qua **OIDC login đã verify**, không lấy từ JSON input chưa xác thực.

### 14.3. Đăng nhập thành công không tự cấp quyền API

OIDC xác định OP đã xác thực user; resource authorization vẫn cần membership, scope, tenant/object ownership. Không lấy `name`, `email_verified` hoặc một claim role chưa có trusted mapping để tự cấp admin.

## 15. Java/Spring: Resource Server không tự viết JWT verifier

Với JWT access token, **không parse bằng `split(".")` rồi tin claims**. Spring Resource Server có JWT decoder/validators cho signature/issuer/time, nhưng ứng dụng còn phải pin audience/algorithm/token type khi policy cần.

### 15.1. Cấu hình issuer cho JWT RS

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test
```

Chỉ khai báo `issuer-uri` **không chứng minh đầy đủ** kiểm audience, `typ` hoặc crypto policy của tổ chức. Cần explicit validators/cấu hình tương ứng.

### 15.2. Ví dụ pin thuật toán và audience

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtValidation {
    private static final String ISSUER = "https://id.example.test";

    @Bean
    JwtDecoder ordersDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://id.example.test/oauth2/jwks")
            .jwsAlgorithm(SignatureAlgorithm.PS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
```

**Giới hạn của ví dụ:** pinned `PS256` và issuer/aud không tự kiểm JWT access-token `typ`, tenant, required scopes/resource ownership, sender proof hoặc revocation. Đồng thời khóa RSA modulus/key usage policy và JWKS key rotation còn cần review theo version Spring/Nimbus. Phải bổ sung **security rules cho endpoint**:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/v1/orders/**").hasAuthority("SCOPE_orders:read")
    .anyRequest().denyAll())
.oauth2ResourceServer(oauth -> oauth.jwt(
    org.springframework.security.config.Customizer.withDefaults()))
```

Đây là **fragment DSL**, không phải một lớp Java đầy đủ và chưa biểu diễn method-specific write policy. Với API thật, kiểm `aud`, `typ`, method/action scope và tenant/ownership riêng. Một token ký đúng nhưng hết hạn hoặc dùng cho API khác phải bị từ chối.

### 15.3. Opaque access token dùng introspection

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: TEST_PLACEHOLDER_FROM_SECRET_MANAGER
```

RS không cần tự thiết kế format opaque token hay JWT-like decoding. Nó gọi introspection theo RFC 7662 với **RS authentication**, kiểm `active` và metadata/policy, áp dụng caching/revocation objective. **`active=true` không thay `aud`, scope hoặc tenant authorization**, và introspection outage không được mặc định allow.

### 15.4. Framework luôn cần negative-path tests

Một test “valid access JWT → 200” không đủ. Cần thêm `alg=none`, wrong issuer/audience/type, expired, insufficient scope, mismatch `kid`, JWKS outage, ID token gửi vào RS, opaque inactive và revoked access token.

## 16. Java/JCA: AEAD đúng API nhưng đừng tự biến thành giao thức truyền token

Khi thực sự cần **mã hóa dữ liệu ứng dụng** (ví dụ data at rest) và không có higher-level SDK phù hợp, dùng **authenticated encryption** do JCA/provider bảo trì, không tự viết AES hoặc packet cipher. Ví dụ sau minh họa **một lần mã hóa trong process**, không phải một token protocol/format persistence/transport hoàn chỉnh:

```java
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.SecureRandom;
import java.nio.charset.StandardCharsets;

final class SingleMessageAeadExample {
    static final int GCM_IV_BYTES = 12;
    static final int GCM_TAG_BITS = 128;

    static byte[] encryptOnce(
        byte[] plaintext,
        byte[] authenticatedContext,
        SecretKey key
    ) throws Exception {
        byte[] iv = new byte[GCM_IV_BYTES];
        new SecureRandom().nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, iv));
        cipher.updateAAD(authenticatedContext);

        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        // Chỉ minh họa output một message. Không tự ghép thành token.
        // Caller cần một profile format/version/keyId/IV/AAD rõ ràng,
        // replay/rotation policies và decryption/authentication handling.
        return ciphertextWithTag;
    }
}
```

**Lưu ý về giới hạn:** ví dụ này **không trả về `iv`**, vì mục đích là minh họa lời gọi AEAD, **không cung cấp format có thể giải mã để dùng production**. Nếu phải lưu/transmit ciphertext, cần format chuẩn chứa IV/key reference/version/AAD/codec phù hợp và assurance rằng key+IV **không bao giờ tái sử dụng**, kể cả qua restart/multi-node. Với high-throughput/bounded nonce collision risks, random-IV policy phải được đánh giá theo quy mô; cân nhắc **managed envelope encryption hoặc JWE SDK** thay tự xây wire protocol. Không dùng `Cipher` trực tiếp để phát bearer access token.

### 16.1. AEAD tag failure phải từ chối

```text
Decrypt with correct key, IV and exact AAD.
If authentication fails:
   reject message, do not expose plaintext,
   do not retry without tag or switch to CBC.
```

Một số thư viện có exception như `AEADBadTagException`; không catch rồi coi plaintext là đủ dùng. Nếu AAD gồm tenant ID, **decryption phải dùng đúng tenant context** mà ứng dụng xác định từ trusted source, không để ciphertext tự đặt tenant nhằm bypass.

### 16.2. KDF, keys và provider

Không sinh AES key bằng `SHA256(password)` rồi gọi là AES-256 bảo mật. Dùng key sinh từ CSPRNG/KMS hoặc KDF được chuẩn hóa đúng nguồn secret/entropy, quản lý rotation/permissions và kiểm provider support. Không dùng cùng AES key cho mọi loại thông điệp/protocol nếu có thể domain-separate.

## 17. JOSE: dùng JWS/JWE đúng profile, không tự chế serialization

### 17.1. JWS Signing Input là bytes theo chuẩn

Trong JWS compact, signing input dùng:

```text
BASE64URL(UTF8(protected_header)) + "." + BASE64URL(payload)
```

Với payload/options đặc biệt, áp dụng semantics JWS/profile tương ứng. **Không parse JSON rồi tự serialize/normalize trước khi verify** nếu không đúng specification; chữ ký áp dụng lên **byte representation** được quy định, không phải “JSON object nghĩa tương tự”.

### 17.2. JWK/JWKS và trust anchor

```json
{
  "kty": "RSA",
  "kid": "issuer-signing-key-1",
  "use": "sig",
  "alg": "PS256",
  "n": "PUBLIC_MODULUS_BASE64URL_PLACEHOLDER",
  "e": "AQAB"
}
```

Đây là public JWK minh họa; `n` placeholder không phải key thật. RS/RP chọn key **trong JWKS của issuer đã được tin**, kiểm key type/length/algorithm policy, signature và claims. **Không fetch `jku` từ attacker token**, không công bố RSA private parameters `d`/`p`/`q` qua public JWKS.

### 17.3. Token type separation

| Token | Ai sử dụng | Không được dùng làm |
| --- | --- | --- |
| **OIDC ID token** | RP/client xác minh user authentication result | Bearer access token để gọi API nghiệp vụ |
| **OAuth access token** | RS đúng `aud`, đúng scope/permission | Đăng nhập RP chỉ bằng decode `sub` |
| **Refresh token** | Client gửi tới AS token endpoint để refresh | Credential gọi RS nghiệp vụ |
| **Client assertion JWT** | AS xác thực OAuth client | Access token cho user/API |
| **DPoP proof JWT** | AS/RS kiểm proof cho request cụ thể | Token thay thế access token |
| **Signed webhook message** | Webhook consumer xác minh event producer | Proof rằng user có quyền vào API |

**Cùng dùng ES256/PS256 không làm các token hoán đổi được.** Profile cần explicit `typ`/claims, audience, issuer, key trust và validation rules riêng.

### 17.4. JWE key management khác JWS signing

Trong JWE, `alg` chỉ **key management**, `enc` chỉ **content encryption**:

```json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "typ": "JWT"
}
```

Một JWE được giải mã bằng private key của RP **chưa tự xác minh OP đã phát claims**. Nếu profile đòi issuer authentication, cần kiểm nested JWS hoặc bảo đảm tương đương được chuẩn hóa. Tránh `RSA1_5` JWE legacy, AEAD tag bypass và dynamic algorithm downgrade.

## 18. Protocol composition: điều nguy hiểm thường nằm giữa hai hệ thống

Một ứng dụng có thể dùng **TLS + OAuth + JWT + API gateway** nhưng ghép sai:

```text
Browser obtains access token for profile-api
    |
    v
API Gateway verifies signature and exp only
    |
    v
Orders API trusts gateway header "X-User-ID"
    |
    v
Orders API returns cross-tenant order because audience/tenant unchecked
```

Không có lỗi “AES yếu” hoặc “RSA bị phá”; lỗi là **trust boundary và protocol composition**.

### 18.1. Claims từ gateway phải có provenance

Nếu gateway tạo `X-User-ID` hoặc `X-Scopes` cho backend:

- Chỉ backend **sau gateway tin cậy** được nhận header đó.
- Gateway phải **xóa/ghi đè** các header cùng tên do external caller gửi.
- Backend phải có mTLS/network auth đảm bảo request thật sự từ gateway, hoặc tự validate token.
- Gateway/RS phải kiểm issuer, audience, token type, expiry và policy.
- Tenant/ownership authorization không được bỏ vì đã có header user ID.

Không biến header thường thành “cryptographic proof” chỉ bằng đặt tên `X-Secure-Principal`.

### 18.2. HTTP request signing phải ràng buộc đủ dữ liệu

Nếu một nghiệp vụ cần signed HTTP requests ngoài OAuth, đừng ký riêng request body rồi bỏ method/path/host/context. Chọn **HTTP Message Signatures RFC 9421** hoặc profile đã chuẩn hóa, xác định components cần ký theo threat model, thời gian, nonce, key ID, signature algorithm, canonicalization và replay handling.

**Không tự tạo** `X-Signature = SHA256(secret + body)` rồi công bố nó là universal request authentication; không có nghĩa mọi HTTP Message Signatures deployment tự giải quyết OAuth authorization hay tenant policy.

### 18.3. Message queue và asynchronous jobs

Một event `orderPaid` được ký/MAC hợp lệ có thể bị phát lại qua queue nếu consumer không có **event ID/idempotency state**, issuer/producer trust, tenant binding và retention policy. Không dùng “JWT đã ký” như bằng chứng sự kiện chỉ cần xử lý đúng một lần.

### 18.4. File uploads, callbacks và redirects

Với OAuth callback, `code`/`state` nằm trong browser navigation; nếu RP tải analytics/scripts ngoài trước khi xử lý callback hoặc log full URL, authorization code có thể bị lộ. **Bảo vệ token transport và callback** là một phần của giao thức, không được khắc phục chỉ bằng signature mạnh hơn.

## 19. Có bao giờ được tạo một protocol mới?

Đối với sản phẩm học tập/doanh nghiệp, **mặc định là không**. Khi không có chuẩn phù hợp vì hệ thống có yêu cầu đặc biệt, nhóm cần chuyển từ “implementation task” thành **security protocol engineering project** với review độc lập.

### 19.1. Điều kiện tối thiểu cho một protocol mới

1. **Business/security objective** được ghi cụ thể, chứng minh chuẩn sẵn có không đáp ứng.
2. **Threat model:** attackers, capabilities, trust anchors, assets và giả định vận hành.
3. **Formal security goals:** authentication, secrecy, integrity, freshness, replay, forward secrecy nếu cần, key compromise impact.
4. **Message specification:** serialization/canonicalization, version, transcript, identities, channels, key IDs, nonce policy, limits.
5. **Cryptographic design:** chọn primitive/construction đã chuẩn hóa; không tự viết primitive.
6. **Independent cryptographic review** và red-team/peer review có năng lực phù hợp.
7. **Protocol state-machine tests**, fuzzing, test vectors, interop fixtures, negative paths và formal methods khi phù hợp.
8. **Key lifecycle:** generation, distribution, rotation, compromise recovery, algorithm agility.
9. **Migration/versioning/downgrade protection** và cách vô hiệu phiên/tokens cũ.
10. **Operational controls:** logging redaction, rate limiting, monitoring, incident runbook và policy ownership.

Chỉ khi hoàn thành các bước và có phê duyệt, một giao thức bespoke mới có thể được xem xét. Điều này **không có nghĩa mọi protocol bespoke đều không thể an toàn**, mà là chi phí chứng minh an toàn và vận hành lớn hơn nhiều so với việc dùng chuẩn.

### 19.2. Không nhầm custom business protocol với tự phát minh crypto

Ứng dụng được phép thiết kế business APIs như `POST /orders`, workflows và access policies. Nhưng khi cần:

- **Authentication:** dùng OIDC/mTLS/workload identity chuẩn.
- **Authorization:** dùng OAuth access tokens, scopes, object-level policy.
- **Confidentiality/integrity on network:** dùng TLS hoặc managed messaging security.
- **Credential signing:** dùng JOSE/JWS hoặc standardized message signing.
- **Encryption at rest:** dùng KMS/AEAD SDK/envelope encryption.

“Tự xây order workflow” là nghiệp vụ; “tự sáng tạo handshake/cryptographic token format/key exchange” mới là **rolling your own crypto protocol**.

## 20. Review checklist cho một thiết kế trước khi code

Trong buổi kiến trúc, nhóm nên trả lời các câu hỏi sau **bằng tài liệu và test criteria**:

| Câu hỏi | Bằng chứng cần thấy |
| --- | --- |
| Giải pháp có chuẩn sẵn có không? | RFC/profile/thư viện và lý do lựa chọn |
| Ai là issuer/client/RS/RP/end user? | Sơ đồ roles/trust boundaries |
| Attacker điều khiển trường nào? | Threat model và untrusted input inventory |
| Key/credential nào thực sự bí mật? | KMS/HSM/IAM/trust matrix |
| Message nào cần bảo mật? | Confidentiality/integrity/authentication properties |
| Nonce/replay được quản lý ra sao? | State/TTL/one-time/replay cache theo profile |
| Dữ liệu nào được ký/MAC? | Message binding/canonicalization specification |
| `alg`/key source đến từ đâu? | Explicit algorithm policy và trusted issuer registry |
| Có chuyển token giữa contexts không? | Token type/audience/issuer tests |
| Authentication gate ở đâu? | State machine trước token/session issuance |
| Consent/authorization gate ở đâu? | Grant/scope/resource policy |
| Key rotation/revoke hoạt động ra sao? | End-to-end tests và time-to-deny |
| Lỗi/outage xử lý thế nào? | Fail-closed behavior, bounded retries |
| Logs có chứa secrets không? | Redaction tests/retention controls |
| Migration/legacy interoperability? | Deprecation path có hạn và test vectors |

### 20.1. Các dấu hiệu cần dừng và review

Các phát biểu sau là **red flags**:

- “Chỉ là internal token, không cần OAuth.”
- “Base64 nhìn khó đọc rồi.”
- “AES-256 rất mạnh nên không cần MAC.”
- “Dùng `SHA256(secret + payload)` là đủ, HMAC phức tạp.”
- “Tự viết OAuth callback chỉ khoảng 30 dòng.”
- “JWT header đã ghi `alg` thì mình verify theo nó.”
- “Không kiểm issuer/audience vì cả công ty dùng một provider.”
- “Không cần `nonce`, thêm timestamp là chống replay.”
- “Đã có TLS nên token copy đi chỗ khác cũng không dùng được.”
- “JWT không cần revoke vì chữ ký vẫn đúng.”
- “KMS timeout thì fallback sang hardcoded signing key.”
- “Khi introspection fail cứ allow để hệ thống không downtime.”

Mỗi câu có thể ẩn một **giả định sai về security property hoặc trust boundary**. Cách sửa là quay về chuẩn, ghi yêu cầu và thiết kế test/architecture bảo vệ tương ứng.

## 21. Khi dùng thư viện chuẩn vẫn có thể mắc lỗi

### 21.1. Dependency không tự là policy

Một JOSE library có thể hỗ trợ `HS256`, `RS256`, `PS256`, `ES256` và `none`. Hệ thống **không nên bật tất cả**; policy cần chọn những algorithm/type phù hợp, kiểm issuer/key/claims. Một TLS library có thể cho phép tắt hostname verification; cấu hình như vậy phá expected server identity.

### 21.2. Version/patching quan trọng

Thư viện OAuth/OIDC/JOSE có thể có security advisories về parser, JWT validation, redirect handling, JWKS fetching hoặc token caching. Cần:

- Dependency inventory/SBOM.
- Pinned/managed dependency versions và security upgrade cadence.
- Kiểm transitive dependencies.
- Theo dõi security advisories từ maintainers.
- Regression tests trước và sau upgrade.

Không fork library rồi tùy tiện bỏ validation để “giảm CPU”.

### 21.3. Interoperability tests không chỉ kiểm successful login

Khi AS và client khác vendors, test:

- PKCE S256, state, nonce và issuer binding.
- Client authentication tại token endpoint.
- Algorithm/key registration và JWKS rotation.
- ID token claims/`azp`/auth_time khi áp dụng.
- Access JWT `typ`/`aud`/scope theo profile hoặc opaque introspection.
- Refresh rotation/reuse, revocation, logout semantics.
- Errors: `invalid_grant`, `invalid_client`, `invalid_token`, `consent_required`...

Không yêu cầu mọi provider trả một JSON lỗi hay logout behavior giống nhau khi chuẩn/profile không định nghĩa như vậy. Nhưng **mọi thất bại validation phải fail closed**.

## 22. Ma trận kiểm thử: phát hiện “crypto đúng nhưng protocol sai”

Để xác nhận hệ thống **không tự tạo một giao thức yếu**, cần chạy **positive và negative tests** ở những ranh giới: parser, crypto, trust, transaction, replay, authorization, revocation, errors và deployment. Các test sau là **mục tiêu thiết kế**, không phải một bộ kiểm thử tự động chạy được nguyên bảng.

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | OIDC Authorization Code + PKCE S256 hợp lệ | RP kiểm transaction + ID token và login theo policy |
| 2 | Authorization callback không có `state` | Không đổi code/tạo session |
| 3 | Callback `state` sai | Từ chối, không login |
| 4 | Code của phiên A gửi sang phiên B | Transaction/PKCE binding fail |
| 5 | Authorization code dùng lần hai | AS token endpoint từ chối |
| 6 | PKCE `code_verifier` sai | Không cấp token |
| 7 | PKCE plain trong profile yêu cầu S256 | Reject hoặc không được khởi tạo |
| 8 | Redirect URI khác registration | AS không redirect đến URI không được tin |
| 9 | Authorization response từ issuer lạ | RP từ chối mix-up |
| 10 | User chưa authentication xong | AS không phát code/token |
| 11 | MFA/step-up đang pending | Không phát token trước assurance gate |
| 12 | Consent bị từ chối | Không cấp grant tương ứng |
| 13 | Consent preview trước login | Không tạo durable user grant trước verified subject |
| 14 | `prompt=none` nhưng cần consent | OIDC error thích hợp; không silently approve |
| 15 | Client Credentials được cấp service token | RS không biến service token thành end-user login |
| 16 | Access token active đúng `iss`/`aud`/scope | RS có thể authorize theo resource policy |
| 17 | Access token có chữ ký sai | RS từ chối |
| 18 | JWT `alg=none` | RS/RP từ chối protected token |
| 19 | JWT `alg=HS256` khi expected PS256 | Từ chối algorithm confusion |
| 20 | RSA 1024-bit trong JWS policy | Từ chối weak key |
| 21 | ES256 token với wrong curve | Từ chối |
| 22 | `kid` không có trong trusted issuer JWKS | Fail closed, bounded refresh |
| 23 | Issuer A/B dùng cùng `kid` | Không dùng key của B cho A |
| 24 | JWT `jku` trỏ attacker host | Không tải/trust unregistered key URL |
| 25 | Public JWKS chứa private key field | Security gate FAIL, rotate/incident |
| 26 | ID token gửi đến RS thay access token | Từ chối token type/audience |
| 27 | Refresh token gửi đến RS | Từ chối |
| 28 | DPoP proof gửi thay access token | Từ chối |
| 29 | Access JWT có `aud=profile-api` vào orders API | Từ chối |
| 30 | Access JWT có `scope=orders:read` gọi write API | 403/insufficient scope |
| 31 | Access JWT đúng nhưng tenant khác | Resource policy deny |
| 32 | ID token `aud` của client khác | RP từ chối |
| 33 | OIDC ID token đúng chữ ký nhưng nonce sai | RP từ chối khi nonce được yêu cầu |
| 34 | OIDC UserInfo `sub` khác ID token `sub` | RP không gộp identity |
| 35 | JWT `exp` đã qua | Từ chối |
| 36 | JWT `nbf` trong tương lai | Từ chối |
| 37 | JWT payload thiếu claim bắt buộc | Từ chối theo token profile |
| 38 | Token JWT ký đúng nhưng grant revoked | RS deny theo revocation-aware security objective |
| 39 | Opaque token `active=false` | RS deny dù introspection HTTP 200 |
| 40 | Introspection trả `active="true"` string | Parser strict từ chối |
| 41 | AS introspection timeout | Không fail-open |
| 42 | JWKS outage | Không bỏ signature check |
| 43 | HSM signing outage | AS không fallback unsigned/weak key |
| 44 | HMAC secret hardcoded đoán được | Static/config review FAIL |
| 45 | Signing secret dùng chung webhook và JWT | Key separation policy FAIL |
| 46 | JWT parser nhận duplicated JSON claims | Strict parser/profile handling, không bị ambiguity |
| 47 | Header có `crit` không hỗ trợ | Từ chối |
| 48 | JSON khác thứ tự field nhưng ký sai bytes | Không "tự sửa" signature |
| 49 | Text Unicode normalized khác giữa producer/verifier | Từ chối hoặc thống nhất canonical profile |
| 50 | AES-GCM dùng lại key+nonce | Crypto protocol test FAIL |
| 51 | AES-GCM tag bị sửa | Reject, không dùng plaintext |
| 52 | AES-CBC padding lỗi khác MAC lỗi có thể quan sát | Security review không để oracle |
| 53 | JWE giải mã được nhưng inner JWS sai | RP từ chối identity theo signed profile |
| 54 | JWE `enc=A256GCM` CEK sai độ dài | Reject |
| 55 | JWE `alg`/`enc` ngoài allowlist | Reject |
| 56 | DPoP proof đúng signature nhưng `htu` sai | RS từ chối |
| 57 | DPoP `htm` sai | RS từ chối |
| 58 | DPoP `ath` sai | RS từ chối access-token binding |
| 59 | DPoP `jti` bị phát lại | RS/AS replay defense từ chối theo profile |
| 60 | mTLS-bound token dùng cert không đúng | RS từ chối |
| 61 | mTLS certificate info chỉ do external header khai | Không tin raw header, yêu cầu trusted TLS/proxy |
| 62 | Timestamp vẫn trong window nhưng business request được replay | Business idempotency/replay policy deny duplicate |
| 63 | Webhook chỉ ký body, đổi recipient/method ngoài signature profile | Test phát hiện message-binding gap |
| 64 | API gateway nhận forged `X-User-ID` từ client | Header được strip/replaced, backend không tin untrusted |
| 65 | Access token xuất hiện ở URL/referrer/log | Security test FAIL |
| 66 | K1 signing key được rotate planned sang K2 | Verifiers chấp nhận đúng key trong overlap |
| 67 | K1 compromised nhưng verifier cache còn trust | Emergency distrust/time-to-deny test |
| 68 | Revoke refresh token rồi client vẫn refresh thành công | Fail theo AS revocation/family policy |
| 69 | Reverse proxy tự suy callback base URL từ untrusted Host | Chặn host/header injection |
| 70 | Parser cho phép oversized JOSE token | Enforce size/depth/rate limits |
| 71 | Authenticated user không có object permission | 403/deny |
| 72 | Client giả issuer hoặc JWKS URL ở callback | Chỉ chọn trusted AS registration |
| 73 | Logout RP nhưng access token vẫn active | Kết quả theo explicit revoke/logout contract, không giả định |
| 74 | Two regions chấp nhận revoked JWT khác nhau | Đo bounded propagation và sửa cache/state |
| 75 | Two clients cùng email khác (`iss`, `sub`) | Không tự link account |
| 76 | Third-party script lấy bearer token ở browser | Threat model/token storage/BFF/XSS controls |
| 77 | TLS cert hostname sai | Không tắt hostname verification |
| 78 | Protocol error quá chi tiết làm lộ token existence | Giảm error oracle, giữ reason code trong audit |
| 79 | Secret/ID token bị in qua exception/toString | Logging redaction test FAIL |
| 80 | Vetted library nâng version | Regression suite vẫn chặn wrong alg/issuer/aud/replay |

### 22.1. Test oracle nên gồm hai tầng

```text
Cryptographic/protocol validity:
  expected key/algorithm/issuer/transaction/token-type checks PASS

Authorization validity:
  expected audience/scope/tenant/resource policy PASS

Any mandatory failure:
  NO authenticated principal / NO access/refresh token issuance /
  NO authorized business side effect.
```

Một token `scope=orders:read` gửi đến DELETE endpoint có thể bị 403 dù **token hoàn toàn hợp lệ về crypto và authentication**. Test cần phân biệt **token invalid (401)** với **quyền thiếu (403)** để không quy nhầm lỗi sang thuật toán ký.

### 22.2. Dùng token fixtures giả, không dùng credential thật

Các ca test nên sinh token trong sandbox với issuer/keys/clients riêng:

```text
Sandbox AS: https://id.test.example
Sandbox RS: https://orders.test.example
Safe fixture labels: ACCESS_VALID, ACCESS_REVOKED, ID_WRONG_AUD

No production tokens, private keys or user PII in CI output.
```

Kiểm log sinks, APM, proxy, build artifacts và crash reports bằng synthetic sentinel values để phát hiện secret leakage. Không thử brute force tokens/queries trên hệ thống production nếu không có thẩm quyền và change control.

## 23. Từ “happy path” đến adversarial state-machine tests

Protocol security nằm ở **chuỗi thông điệp**, nên test từng method đơn lẻ không đủ.

### 23.1. Chuỗi bình thường

```text
REGISTER CLIENT
-> START AUTH REQUEST
-> LOGIN + REQUIRED MFA
-> CONSENT
-> ISSUE ONE-TIME CODE
-> EXCHANGE WITH PKCE
-> ISSUE ACCESS TOKEN
-> RS VALIDATION
-> ACCESS GRANTED IF POLICY ALLOWS
```

### 23.2. Chuỗi bị trộn session

```text
START AUTH REQUEST (session A)
START AUTH REQUEST (session B)
CALLBACK FROM A delivered to B
-> EXPECT state/issuer/PKCE/nonce binding rejection
```

Nếu ứng dụng chỉ lưu một `code_verifier` global và nhiều tab ghi đè, callback có thể lỗi/nhầm transaction. **Tách transaction references**, TTL và session binding; không bỏ PKCE vì multi-tab khó xử lý.

### 23.3. Chuỗi bị replay

```text
CODE ISSUED
-> FIRST EXCHANGE (success)
-> SECOND EXCHANGE with same code (reject)

REFRESH R1
-> ROTATE TO R2
-> REUSE R1 (detect and apply family policy)

DPoP proof JTI=P1
-> FIRST request (if valid, process)
-> REPLAY P1 (deny according to replay policy)
```

Không tự bắt mỗi lần dùng access token có `jti` phải unique: Bearer access token có thể dùng nhiều lần. Anti-replay phải đúng **loại thông điệp**, không dùng một quy tắc toàn hệ thống mơ hồ.

### 23.4. Chuỗi failover/outage

```text
JWKS K1 cached
AS publishes K2
AS starts signing K2
RS cannot reach JWKS
-> Expected: fail closed for unknown K2, not skip signature
-> Operational fix: prepublish/warm caches, controlled recovery

Opaque access token
RS introspection times out
-> Expected: no unauthorized allow
-> May return 503 under API contract
```

### 23.5. Transaction/consent races

```text
AUTHENTICATION_PENDING
-> user clicked consent preview
-> MFA challenge sent
-> user cancels
-> late MFA callback success
-> EXPECT: no code/token issued for cancelled transaction
```

Một protocol tự chế dễ bị **late callback**, double submit, concurrent refresh và eventually consistent grant state. Cần state transitions atomic/idempotent khi appropriate, không cho trạng thái `CANCELLED/REVOKED` hồi sinh qua callback trễ.

## 24. Java/JUnit: ví dụ test chính sách an toàn

Các ví dụ là **pseudocode theo domain**; helper như `TokenFixtureIssuer`/`OAuthTestHarness` do test project xây, không phải API Spring/JUnit có sẵn. Mục tiêu là nêu **assertions**, không tự cài đặt mật mã.

### 24.1. Không chấp nhận algorithm ngoài allowlist

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class JoseAlgorithmPolicyTest {
    @Test
    void forgedTokenCannotSelectHs256WhenRsRequiresPs256() {
        var fixture = TestTokenFixtures.jwtWithAlgorithm("HS256");

        assertThrows(InvalidTokenException.class,
            () -> ordersTokenValidator.validate(fixture));

        assertEquals(0, businessSideEffects.createdCount());
    }

    @Test
    void unsecuredJwtIsNotAcceptedForApiAuthentication() {
        var fixture = TestTokenFixtures.unsecuredJwtWithSub("admin");

        assertThrows(InvalidTokenException.class,
            () -> ordersTokenValidator.validate(fixture));
    }
}
```

**Không tự xây code giả mạo ngoài môi trường test** chỉ để thử bypass; thư viện JOSE test fixture đủ phục vụ validation. Với một token sai signature/algorithm, không tạo principal hoặc side effects.

### 24.2. Không chấp nhận token đúng crypto nhưng sai audience

```java
@Test
void validJwtForProfileApiIsNotValidForOrdersApi() {
    var token = issuerFixtures.issueSignedAccessToken(
        "PS256", "profile-api", "profile:read");

    var response = ordersApi.getOrders(token);

    assertEquals(401, response.statusCode());
    assertEquals(0, ordersRepository.unauthorizedReadCount());
}
```

Đây là test **token purpose/audience binding**, không phải test độ dài khóa. Nó chứng minh crypto validity là **điều kiện cần nhưng chưa đủ**.

### 24.3. Login chưa hoàn tất không thể cấp token

```java
@Test
void pendingMfaCannotProduceAuthorizationCode() {
    var tx = oauthFixtures.authorizationRequestWithPkce();
    oauthFixtures.authenticatePasswordOnly(tx);

    assertThrows(AuthenticationIncompleteException.class,
        () -> authorizationService.finalizeAndIssueCode(tx));

    verifyNoInteractions(authorizationCodeIssuer);
    verifyNoInteractions(accessTokenIssuer);
}
```

Các class và fixtures là minh họa. Test cần kiểm **database/token issuer side effects**, không chỉ HTTP 400. Nếu quá trình finalize có external callbacks, test cả late/replay/race paths.

### 24.4. Token bị revoke dù signature vẫn hợp lệ

```java
@Test
void revokedJwtCannotAuthorizeApiAfterPropagationBound() {
    var token = testAs.issueJwtAccessToken("orders-api", "orders:read");
    assertEquals(200, ordersApi.getOrders(token).statusCode());

    testAs.revokeGrantFor(token);
    testAs.awaitGrantInactive(token);
    ordersApi.awaitRevocationPropagation(token);

    assertEquals(401, ordersApi.getOrders(token).statusCode());
}
```

Test này chỉ hợp lệ khi **RS có revocation-aware mechanism** và propagation SLA rõ; nếu RS JWT-only offline, kết quả deny trước `exp` không thể được khẳng định khi kiến trúc chưa hỗ trợ. Test fixtures cần cấp token đủ thời gian sống để không bị expiry nhầm nguyên nhân.

### 24.5. Không cho error fallback thành allow

```java
@Test
void introspectionOutageNeverMakesUnknownTokenAuthenticated() {
    testAs.introspectionEndpointReturns503();
    var response = ordersApi.getOrders("TEST_OPAQUE_TOKEN");

    assertNotEquals(200, response.statusCode());
    assertEquals(0, ordersRepository.unauthorizedReadCount());
}
```

Response có thể 401 hoặc 503 tùy RS/service contract; invariant quan trọng là **không có authenticated principal hay business action khi thiếu trạng thái active đáng tin**.

## 25. Tình huống thực tế và cách lựa chọn thay thế

### 25.1. “Tạo JWT mini để đỡ cài OIDC”

Nhóm tự định nghĩa chuỗi:

```text
userId.expiry.sha256(sharedSecret+userId+expiry)
```

Họ quên client registration, consent, scope, issuer, audience, key rotation, logout, refresh, replay và security monitoring.

**Hướng xử lý:** nếu chỉ là một ứng dụng web có server-side session, dùng **session framework được bảo vệ**; nếu cần login liên kết, dùng **OIDC code flow + PKCE**; nếu cần gọi API, dùng OAuth access token đúng RS/scope. **Không bắt buộc mọi session đều phải là JWT**.

### 25.2. “Dùng AES-CBC để giấu role”

Developer mã hóa `{"sub":"alice","role":"admin"}` và server chỉ decrypt. Không có authentication tag và token lifecycle.

**Hướng xử lý:** dùng session/AS token issuance chuẩn; nếu nội dung thực sự cần được giữ bí mật, dùng **JWE/AEAD** theo profile và kiểm issuer/authorization riêng, không tin plaintext chỉ vì decrypt được.

### 25.3. “Tạo API signature bằng SHA256(secret + body)”

Không có method/path/query/recipient/nonce/context binding; parser client/server có thể hiểu JSON khác nhau.

**Hướng xử lý:** nếu phù hợp, dùng **OAuth/mTLS**; nếu cần signed HTTP requests độc lập, cân nhắc **RFC 9421 HTTP Message Signatures** theo profile đã review và replay controls.

### 25.4. “Cho token tự chọn JWKS URL”

RS tải `jku` từ JWT chưa verify và thấy chữ ký đúng với key vừa tải.

**Hướng xử lý:** issuer/JWKS trust từ trusted configuration; pin algorithm/type/key size, chặn SSRF, kiểm `iss`/`aud`/token type. Một signature check với **attacker-chosen key** không chứng minh token đến từ AS đáng tin.

### 25.5. “TLS chạy rồi, không cần PKCE”

Authorization code có thể bị lộ qua OS redirect/callback/browser logs/extension/URI handlers trong một số threat models. TLS bảo vệ channel nhưng không thay **authorization code binding**.

**Hướng xử lý:** Authorization Code + PKCE `S256`, `state`, strict redirect URI và issuer binding theo OAuth security profile.

### 25.6. “Có timestamp rồi, không thể replay”

Webhook ký đúng nhưng giữ timestamp window 5 phút và không có event ID/anti-replay. Gửi lại trong window có thể gây cùng business action nhiều lần.

**Hướng xử lý:** chuẩn message signing khi cần, nonce/event ID replay defense và **business idempotency**; đừng tự cho timestamp là proof one-time.

### 25.7. “MFA chưa xong nhưng token ký rồi”

AS phát code/access token ngay sau password success để giảm latency, cho phép user hoàn tất MFA sau.

**Hướng xử lý:** token issuance gate chỉ chạy khi **authentication assurance và consent/authorization policy hoàn tất**. Ký mạnh PS256 không sửa state-machine bypass.

### 25.8. “ID token đã ký nên API nào cũng tin”

RS nhận ID token của RP, vì cùng OP/JWKS nên kiểm signature và cho truy cập orders.

**Hướng xử lý:** token type/purpose separation; ID token xác thực user cho RP, access token dành RS; kiểm `aud`, `typ`, scope và policy tài nguyên.

### 25.9. “Đã revoke, nhưng JWT còn đúng chữ ký”

AS revoke grant nhưng RS chỉ verify JWT offline; token vẫn được dùng tới `exp`.

**Hướng xử lý:** thiết kế **revocation-aware enforcement** (introspection, denylist, grant version, sender constraints/short TTL tùy objective), đo time-to-deny. Không tự gọi signature invalid hoặc xoay khóa toàn hệ thống cho mỗi logout.

### 25.10. “KMS unavailable thì dùng fallback secret”

AS có PS256 key trong HSM nhưng khi lỗi lại ký HS256 bằng hardcoded shared secret.

**Hướng xử lý:** **fail closed issuance** hoặc dùng approved alternate signing key/path đã review; không tự hạ chuẩn và không cho client/RS chấp nhận thuật toán ngoài allowlist.

### 25.11. “Mã hóa bằng AES-GCM nhưng cố định IV”

Developer dùng AES-256-GCM với key dài 32 byte và nonce toàn zero cho mỗi message.

**Hướng xử lý:** managed AEAD/JWE SDK, key–nonce uniqueness, encrypt-once policy, tag validation, rotation và test no-reuse. Khóa 256 bit không bảo vệ được nonce reuse.

### 25.12. “Dùng RSA public key làm HMAC secret”

Một generic JWT verifier chấp nhận HS256 trong khi expected RS256; bytes của public key được dùng như HMAC secret.

**Hướng xử lý:** pin algorithm/key type/issuer trust, chống algorithm confusion; không dùng generic verifier chọn key type từ untrusted `alg`.

### 25.13. “Một issuer dành cho cả công ty nên không cần audience”

Orders và Payments cùng tin AS; token `aud=orders-api` được Payments chấp nhận chỉ vì signature đúng.

**Hướng xử lý:** resource audience validation và scope policy, không coi shared issuer là global permission.

### 25.14. “Mọi lỗi introspection đều 200 để đảm bảo availability”

RS tự trả 200 khi AS introspection timeout.

**Hướng xử lý:** fail closed; nếu có **bounded stale cache** được security review cho endpoint rủi ro thấp, phải có TTL, incident revoke/deny mechanism và explicit authorization contract. Không có catch-all allow.

## 26. Khi cần migrate giao thức tự chế

Một hệ thống legacy có thể đã có token/cipher format riêng. Thay ngay toàn bộ không có kế hoạch có thể gây downtime hoặc làm mất thông tin authorization.

### 26.1. Inventory trước khi thay

1. Xác định **issuer/consumers**, client, RS, gateways, token TTL/refresh, format, keys và nơi lưu.
2. Kiểm **giao thức cũ bảo vệ gì**: encryption/MAC/signature, audience, scope, expiry, replay, revoke, client/user binding.
3. Phân loại **lỗ hổng nghiêm trọng** cần chặn ngay (forged token, unauthenticated encryption, fail-open, leaked key).
4. Chọn **chuẩn thay thế**: server-side session, OIDC, OAuth access/opaque token, JWS/JWE, mTLS/DPoP.
5. Thiết kế **compatibility window** và cơ chế dừng chấp nhận legacy token, không bật legacy vô thời hạn.
6. Thử E2E các paths, outage, revocation, key rotation và logging.

### 26.2. Dual-read có rủi ro downgrade

Giả sử giai đoạn migration:

```text
Issuer new: OAuth JWT access tokens PS256
Legacy old: base64+custom-MAC tokens

RS temporarily accepts both.
```

Không viết verifier “thử JWT mới thất bại thì tự fallback legacy” cho **mọi** input. Cần routing/format discriminator có chính sách, user/client/resource constraints, hạn chót, rate limits và test attacker không thể biến token mới thành legacy để bỏ validation. Nếu legacy có lỗ hổng forgery nghiêm trọng, **không thể dual-read an toàn**; cần buộc reauthentication/reissuance hoặc shutdown compatibility path.

### 26.3. Planned deprecation

```text
Phase A: Stop issuing legacy tokens.
Phase B: Issue standardized tokens; deploy policy-aware verifiers.
Phase C: Accept old tokens only in short reviewed transition
         if safe and necessary, with an explicit end date.
Phase D: Invalidate old grant/session/token formats.
Phase E: Remove legacy parsers/keys; add tests for permanent reject.
```

Không dùng `alg=none` hay “ignore signature for old clients” làm migration shortcut. Test cả **old tokens refused after deadline** và **new tokens work with correct issuer/audience/policy**.

### 26.4. Rollback phải giữ trust boundary

Nếu rollback code khiến verifier nhận lại legacy tokens yếu, đây là **security regression**. Có thể rollback vận hành nhưng vẫn giữ cấm thuật toán/token format không an toàn. Crypto policy và trust configuration phải là **change-controlled assets** độc lập với business deployment khi cần.

## 27. Sự cố và phản ứng khi phát hiện DIY crypto lỗi

### 27.1. Trường hợp token tự chế có thể bị giả mạo

1. **Chặn đường chấp nhận token yếu** theo incident severity; không chỉ đổi secret rồi giữ parser sai.
2. **Xác định phạm vi** clients, users, tenants, endpoints, token families bị ảnh hưởng.
3. **Rotate/revoke keys/tokens/grants** phù hợp, cập nhật trust state ở RS/gateway.
4. **Rà logs** bằng request IDs và audit metadata, không paste raw tokens vào ticket.
5. **Kiểm business operations trái phép**, nhất là quyền admin, thanh toán, data export, cross-tenant.
6. **Thay giao thức** bằng chuẩn/vetted implementation với negative tests.
7. **Theo dõi propagation**: mọi RS đã ngừng accept old/forged tokens hay chưa.
8. **Đánh giá root cause**: thiếu threat model, security review, CI test, library governance hay cấu hình allowlist.

### 27.2. Khi lộ private signing key

Attacker có thể **tự ký token mới** dưới public key đã tin. Chỉ phát một khóa mới không ngăn RS đang cache public key cũ tiếp tục chấp nhận forged token.

- Disable signer K1 và hạn chế/thu hồi quyền key access.
- Xử lý **emergency distrust K1** tại JWKS/verifiers, invalidate caches và pinning.
- Phát K2 bằng trusted process.
- Xem xét tokens/sessions/grants liên quan và reauthentication/denylists theo chính sách.
- Đo time-to-deny ở mọi region/RS, không giả định đã xong vì JWKS đã thay.

### 27.3. Khi phát hiện AEAD nonce reuse

Mức độ ảnh hưởng phụ thuộc algorithm/mode, key scope, số messages và dữ liệu được bảo vệ; cần **crypto expert** đánh giá. Có thể phải rotate encryption keys, ngừng format lỗi, đánh giá confidentiality/integrity của dữ liệu đã mã hóa và re-encrypt bằng mechanism an toàn. **Không chỉ sửa nonce cho message mới rồi xem ciphertext cũ vô hại.**

### 27.4. Khi phát hiện OAuth flow sai state/PKCE

Kiểm login CSRF/session swapping, code interception, account linking và token issuance. Bật/siết PKCE S256, `state`/issuer/nonce binding theo profile, revoke affected sessions/grants và test cả callback race/multi-tab.

### 27.5. Incident report nên tách lỗi thuật toán và lỗi giao thức

```text
incident_classification:
  crypto_primitive_or_provider_error
  key_management_error
  protocol_message_binding_error
  token_type_or_audience_confusion
  authorization_policy_error
  replay_or_revocation_gap
  information_leak_or_error_oracle

artifacts:
  safe_request_ids
  affected_issuer_client_resource_refs
  timeline_of_key_policy_state
  verification_test_results
  no raw credentials / private keys
```

Đây là mẫu metadata điều tra, không phải format chuẩn. Mỗi nhóm lỗi có cách khắc phục khác nhau: **tăng RSA từ 2048 lên 4096 không sửa thiếu audience; thêm PKCE không sửa key leak; thêm AEAD không tự sửa replay**.

## 28. Bài thực hành

### Bài A — Phân loại tầng bảo mật

Cho các kỹ thuật:

```text
AES-256
AES-GCM
HMAC-SHA256
HKDF
TLS 1.3
OAuth 2.0 Authorization Code + PKCE
OIDC ID token validation
JWS compact serialization
Spring Security Resource Server
Object-level authorization in Orders API
```

Hãy phân loại đâu là **primitive/construction**, đâu là **protocol/profile**, đâu là **framework implementation** và đâu là **application policy**. Giải thích vì sao một phần tử riêng không bảo đảm toàn bộ security objective.

### Bài B — Sửa một token tự chế

Developer muốn dùng:

```text
token = BASE64(userId + "|" + expiry + "|" + SHA256(secret+userId))
```

Nêu **ít nhất tám** vấn đề liên quan integrity, serialization, token purpose, issuer, audience, scope, client, replay, expiry, key management, revocation hoặc authorization. Đề xuất một lựa chọn thích hợp hơn:

1. Server-side session framework nếu chỉ là login web nội bộ.
2. OIDC nếu cần authentication qua external OP.
3. OAuth access token opaque/JWT nếu cần cho RS theo scope/audience.

**Không yêu cầu viết lại token format tự chế**; mục tiêu bài tập là lựa chọn kiến trúc.

### Bài C — “AES-256” có đủ?

Một nhóm mã hóa trạng thái login:

```text
AES mode = CBC
IV = constant
No authentication tag/MAC
Token contains user role
Server trusts decrypted JSON
```

Chỉ ra các lỗi: mode chưa cung cấp integrity, IV policy, thiếu identity/grant binding, không có anti-replay/revocation. Hãy đề xuất dùng session/standard token và **AEAD/JWE nếu thật sự cần confidentiality**, nhưng không tự biến ciphertext thành bearer token protocol.

### Bài D — Có chữ ký nhưng vẫn replay

Một request thanh toán được ký bằng private key, gồm amount và timestamp trong 5 phút. Hãy giải thích vì sao attacker gửi lại nguyên request trong cửa sổ còn có thể gây xử lý lặp, và cách **idempotency key/event ID/replay cache** kết hợp với protocol hiện có giúp chống double processing.

### Bài E — So sánh `state`, PKCE và `nonce`

Ba sự cố:

1. Callback thuộc login session A được gửi vào browser session B.
2. Authorization code bị chặn và attacker muốn tự đổi sang token.
3. ID token cũ được phát lại cho một authentication request khác.

Chọn **state/transaction binding**, **PKCE S256**, **OIDC nonce/ID token validation** phù hợp. Vì sao không dùng một cơ chế để thay cả ba?

### Bài F — Cross-JWT confusion

AS phát:

```text
id_token:
  iss = https://id.example.test
  aud = storefront-web
  typ = JWT

access_token:
  iss = https://id.example.test
  aud = orders-api
  typ = at+jwt
  scope = orders:read
```

Cả hai được ký bằng PS256 từ issuer đã tin. Tại sao Orders API không được chấp nhận ID token? Tại sao RP không được lấy access token rồi coi nó là ID token chỉ vì có `sub`? Hãy mô tả các **profile validators** tương ứng.

### Bài G — Key substitution qua `jku`

Một RS có JWKS URI cố định cho issuer A nhưng library mặc định cũng cho phép tải `jku` trong JWT header. Hãy đề xuất cách **pin trusted issuer registry**, vô hiệu arbitrary key URLs, kiểm `kid`/`alg`/key type và test SSRF. Vì sao một chữ ký hợp lệ bằng public key do token tự cung cấp **không chứng minh AS A đã ký**?

### Bài H — Sửa fallback lỗi

```java
// Code sai: lỗi crypto lại cấp quyền.
try {
    return tokenValidator.verify(token);
} catch (Exception ex) {
    return AuthenticatedPrincipal.adminFallback();
}
```

Viết thiết kế fail-closed thích hợp: trả 401 với invalid token, 503 tùy service contract khi không truy cập được dependency, audit reason codes và **không tạo principal**. Không copy raw token vào exception/log.

### Bài I — JCA AES-GCM không phải một protocol

Đánh giá `SingleMessageAeadExample`:

1. Nó có kiểm tag qua JCA `doFinal` không?
2. Nonce/IV có được trả để giải mã message không?
3. Với nhiều nodes và nhiều tỷ message, random 96-bit IV có cần đánh giá collision/security bound không?
4. Làm sao quản lý key ID, rotation, AAD/metadata version, canonical message encoding?
5. Vì sao không nên gửi riêng ciphertext output của ví dụ làm access token?

Nêu lý do sử dụng managed envelope encryption/JWE library trong hệ thống có yêu cầu interoperable message format.

### Bài J — KDF và domain separation

Một tổ chức dùng cùng secret cho HS256 access tokens, webhook HMAC và cookie integrity. Hãy xác định rủi ro **cross-protocol key reuse**. Đề xuất tách independent keys bằng KMS/HSM hoặc dùng HKDF theo specification khi nguồn key đủ entropy; nêu vì sao **HKDF không thay password hashing**.

### Bài K — Spring Resource Server

Dựa vào `OrdersJwtValidation`:

1. Kiểm trusted issuer và PS256.
2. Thêm audience `orders-api`.
3. Thêm token type/claims/profile validation nếu hệ thống dùng RFC 9068.
4. Giới hạn scope `orders:read` cho GET và `orders:write` cho POST/PATCH/DELETE tùy policy.
5. Kiểm tenant/resource ownership.
6. Test wrong alg/issuer/audience/type, expired JWT và JWKS outage.
7. Giải thích tại sao vẫn cần revoke-aware enforcement nếu JWT có thể bị revoke trước `exp`.

### Bài L — OIDC account mapping

Hai OP trả cùng `email=alice@example.test` nhưng (`iss`, `sub`) khác nhau. RP tự link account chỉ bằng email. Hãy viết quy tắc mapping/linking an toàn và nêu vì sao ID token signature validation **không tự chứng minh** hai identities cùng một account nội bộ.

### Bài M — Migration khỏi legacy protocol

Hệ thống cũ phát token theo `Base64(user|timestamp|hash)`, RS mới muốn chấp nhận OAuth access JWT PS256:

1. Kiểm kê legacy clients/RS/keys/session TTL.
2. Xác định legacy token có thể bị forge hay không.
3. Chọn migration/reauth/reissue phù hợp.
4. Thiết kế cách từ chối legacy token sau deadline.
5. Không dùng `JWT verify failed → legacy fallback` cho mọi input.
6. Test no-downgrade, key rotation và revoke.

Nếu legacy format có lỗ hổng forgery không thể cô lập, **không giữ dual-read chỉ vì backward compatibility**.

### Bài N — DPoP và request binding

Client có private key DPoP và access token bound với thumbprint. Một proof đã ký đúng nhưng có `htu=/orders`, `htm=GET` được gửi lại để gọi `POST /payments`.

Hãy chỉ ra vì sao **verify signature thôi chưa đủ**, và kiểm `htu`, `htm`, `ath`, `jti`, `iat`, nonce khi có, key thumbprint/`cnf`. Khi nào mTLS sender-bound token là lựa chọn phù hợp hơn?

### Bài O — Threat modeling

Vẽ sơ đồ:

```text
Browser -> RP -> AS -> RS -> Database
                    \-> JWKS/introspection
```

Đánh dấu attacker có thể kiểm **browser JavaScript**, một **compromised client**, một **compromised RS**, và một **network proxy**. Nêu ranh giới nào còn đứng vững nếu chỉ RS bị xâm nhập nhưng AS signing private key vẫn được giữ trong HSM và RS chỉ có public JWKS.

### Bài P — Incident drill

Private signing key K1 bị lộ qua CI log, một số RS vẫn cache public K1. Hãy phác thảo:

- Stop signing K1, rotate trusted keys.
- Emergency distrust K1 và invalidate JWKS caches.
- Revoke/reissue các tokens/grants bị ảnh hưởng theo policy.
- Chứng minh RS trên mọi region không còn accept JWT ký K1.
- Điều tra API actions và bảo vệ logs/tickets.

Vì sao chỉ phát K2 hoặc tăng `exp` validation không giải quyết ngay forged JWT ký K1?

## 29. Checklist thiết kế và triển khai production

- [ ] Có tài liệu **security objective, threat model, trust boundaries, attacker capabilities và assumptions**.
- [ ] Chọn chuẩn/protocol đã được review, bảo trì và có implementation phù hợp; không phát minh token/encryption/handshake format cho authentication.
- [ ] Phân biệt primitive, construction, protocol và application authorization policy.
- [ ] Không dùng Base64, URL encoding hoặc hash công khai làm authentication/signature proof.
- [ ] Không tự làm `SHA256(secret + message)` thay HMAC; khi cần MAC, dùng construction chuẩn và key entropy cao.
- [ ] Không lấy password/clock làm signing secret; CSPRNG/KMS/HSM được kiểm soát.
- [ ] Không dùng AES-ECB, unauthenticated CBC hoặc encryption-only ciphertext như bearer authorization token.
- [ ] Nếu dùng AEAD, quản lý **key–nonce uniqueness, tag validation, AAD/context binding** theo library/protocol.
- [ ] Không tự tạo JWE/JWS serialization; dùng JOSE implementation với allowed algorithms và profile rõ.
- [ ] Không cho JWT `alg` hoặc `jku`/`x5u`/embedded JWK tự định nghĩa thuật toán/trust anchor.
- [ ] JOSE verifier pin algorithm, key type/length/curve, issuer JWKS, `kid` namespace và key usage.
- [ ] Protected JWT không tự chấp nhận `alg=none`; chống HS↔RSA confusion.
- [ ] JWT access/ID tokens được tách theo `typ`, issuer, audience và required claims.
- [ ] Không decode JWT unverified rồi tạo authenticated principal từ `sub`/`role`.
- [ ] RS kiểm signature hoặc introspection `active`, expiry, audience, scope và resource-level policy.
- [ ] RP OIDC kiểm `iss`, `aud=client_id`, `exp`, `nonce` khi áp dụng, `azp`/`auth_time` khi cần và account mapping (`iss`, `sub`).
- [ ] OAuth Authorization Code + PKCE `S256`, strict registered redirect URI, state/transaction binding và issuer selection đúng.
- [ ] Token issuance chỉ xảy ra khi **authentication/MFA/consent/authorization** đã hoàn tất.
- [ ] Không gửi code, PKCE verifier, refresh/access/ID token, secrets vào URL, log, referrer, analytics hoặc support ticket.
- [ ] TLS được cấu hình với certificate/hostname validation; không tắt trust validation để debug.
- [ ] DPoP/mTLS sender constraints được RS kiểm proof/cert thực tế, không chỉ đọc `cnf`.
- [ ] Nonce, timestamp, `jti`/request ID được dùng **theo đúng semantics từng protocol**, có replay defense tương ứng.
- [ ] Business operations nhạy cảm có idempotency/re-check policy nếu cần; chữ ký đúng không mặc nhiên ngăn double processing.
- [ ] Key separation theo use case/môi trường/issuer; không chia sẻ signing secret tràn lan cho verifiers.
- [ ] KMS/HSM/secret manager least privilege; RS chỉ verify, AS mới có quyền sign khi dùng asymmetric signing.
- [ ] Key rotation có pre-publish, accepted overlap được giới hạn và emergency compromise handling.
- [ ] Outage/parse/signature/tag/nonce error **fail closed**, không chuyển thành “allow” hoặc downgrade.
- [ ] Có strict parsers, limits cho message/header/token size, duplicate fields, unsupported `crit`/algorithms.
- [ ] JWKS/introspection endpoints và outbound network theo trusted configuration, tránh SSRF/token exfiltration.
- [ ] Refresh token rotation, replay detection và revoke/consent/logout boundaries được định nghĩa riêng.
- [ ] Caching introspection/JWKS có TTL/invalidation phù hợp security objective, không tin revoked key/token quá hạn.
- [ ] Có **unit, integration, E2E, adversarial state-machine và negative-path tests** cho các ranh giới bảo mật.
- [ ] Key/token/secret không xuất hiện trong logs/APM/CI/dumps; audit giữ reason code và safe references.
- [ ] Dùng dependency được bảo trì, theo dõi advisories, nâng cấp có regression tests.
- [ ] Crypto/algorithm policy có owner, version, phê duyệt, timeline migration và no-downgrade tests.
- [ ] Giao thức bespoke chỉ được cân nhắc sau threat model, independent crypto review, formal/peer analysis và explicit sign-off.

## 30. Câu hỏi tự kiểm tra

**1. Tại sao không nên tự thiết kế crypto protocol dù dùng AES-256?** Vì giao thức còn phụ thuộc xác thực message, nonce, key exchange, danh tính, thứ tự thông điệp, replay, authorization và error handling; AES riêng không đảm bảo chúng.

**2. Primitive khác protocol thế nào?** Primitive là phép toán mật mã cơ sở; protocol xác định vai trò, trình tự, ràng buộc và xử lý trạng thái giữa các bên.

**3. HMAC khác `SHA256(secret + message)` ra sao?** HMAC là MAC chuẩn với thiết kế key-based integrity; prefix-hash tự chế không thay được HMAC và có thể có lỗi cấu trúc.

**4. Base64 có phải encryption không?** Không. Đây chỉ là encoding.

**5. JWS signed token có che giấu payload không?** Không. JWS chủ yếu bảo vệ integrity/authenticity; payload thường đọc được.

**6. JWE decrypt thành công có nghĩa AS đã ký claims không?** Không tự động. Cần issuer authentication/signature hoặc assurance tương đương theo profile.

**7. Vì sao không dùng AES-CBC không MAC cho login token?** Nó không tự cung cấp integrity; protocol còn thiếu identity/audience/expiry/replay/revoke.

**8. AES-GCM key 256 bit có cho phép tái sử dụng nonce không?** Không. Reuse key+nonce có thể phá confidentiality/integrity.

**9. Timestamp có tự chống replay không?** Không. Bản sao còn trong cửa sổ thời gian vẫn có thể được xử lý lại nếu thiếu replay/idempotency policy.

**10. `jti` của access token có phải one-time request nonce không?** Không mặc định; access token có thể được dùng nhiều lần, `jti` thường là token ID.

**11. `state` và PKCE có cùng chức năng không?** Không. State liên kết callback/CSRF transaction; PKCE ràng buộc authorization code exchange.

**12. OIDC `nonce` dùng để làm gì?** Ràng buộc ID token với authentication request khi được gửi/áp dụng theo OIDC profile.

**13. Vì sao `alg=none` nguy hiểm ở verifier protected JWT?** Vì token không chữ ký có thể bị coi là authenticated nếu verifier không enforce signing policy.

**14. HS256↔RS256 confusion là gì?** Verifier có thể nhầm RSA public key công khai thành HMAC shared secret, làm sai trust boundary.

**15. Có được tin `kid` là public key hợp lệ chỉ vì nó tồn tại không?** Không. Key phải thuộc issuer/trust set đã được xác minh và phù hợp algorithm/purpose.

**16. Tại sao không tải `jku` từ header chưa verify?** Vì attacker có thể thay nguồn public key hoặc gây SSRF/key substitution.

**17. JWT ký hợp lệ có thể bị từ chối do sai `aud` không?** Có. Chữ ký đúng nhưng token không dành cho RS hiện tại.

**18. ID token có thể dùng làm Bearer access token của API không?** Không theo profile OAuth/OIDC thông thường; token purpose/audience khác nhau.

**19. Một RS bị compromise có tạo JWT của AS được nếu chỉ có public JWKS không?** Không chỉ từ public key; nhưng vẫn có thể gây rò tokens/trust/config hoặc thực hiện hành vi trái phép trong RS.

**20. KMS/HSM có tự kiểm scope, tenant và resource ownership không?** Không. Key operations và authorization policy là các tầng khác.

**21. Nếu JWT access token bị revoke, signature có tự sai không?** Không. RS cần cơ chế revocation-aware hoặc chờ expiry theo thiết kế.

**22. DPoP proof ký đúng có đủ không?** Không. Cần request binding, token/key thumbprint, replay và nonce khi áp dụng.

**23. Có cần request idempotency khi đã ký HTTP request không?** Có thể cần cho nghiệp vụ; chữ ký không đảm bảo một business transaction chỉ được xử lý một lần.

**24. OAuth Client Credentials có end user consent/login mặc định không?** Không. Đây là grant cho service/client principal theo AS policy.

**25. Nên làm gì khi crypto library báo unsupported algorithm?** Fail closed hoặc thay profile/provider theo change control, không tự chuyển sang `none`/HS256 yếu hơn.

**26. Đã dùng Spring Security có cần kiểm audience/scope không?** Có. Framework cung cấp cơ chế, nhưng ứng dụng phải cấu hình validators và authorization policy đúng.

**27. Vì sao không dùng `Thread.sleep` và vài happy-path tests để chứng minh giao thức?** Vì lỗi có thể nằm ở replay, concurrency, session binding, cache/outage; cần adversarial tests và bounded assertions.

**28. Được tự thiết kế business workflow không?** Được. Nguyên tắc tránh tự phát minh security protocol/cryptographic construction khi có chuẩn phù hợp.

**29. Khi nào có thể nghiên cứu protocol mới?** Khi có nhu cầu đặc thù đã chứng minh, threat model, crypto experts, independent review, interoperability/test vectors, formal analysis và explicit governance.

**30. Khi phát hiện token tự chế có thể forge, ưu tiên gì?** Chặn acceptance path, revoke/rotate keys/grants theo scope, điều tra ảnh hưởng và chuyển sang giao thức chuẩn với test fail-closed.

## 31. Tài liệu tiêu chuẩn và hướng dẫn tham khảo

- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** handshake, cipher suites, authentication, transcript binding và channel security.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** roles, authorization grants, authorization/token endpoints và scopes.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** PKCE, redirect/issuer mix-up defenses, token theft, refresh rotation và OAuth threat model.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code verifier/challenge và `S256`.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer binding cho authorization response.
- **RFC 8252 — OAuth 2.0 for Native Apps:** external user-agent và redirect binding.
- **OpenID Connect Core 1.0:** authentication result, ID token, nonce, subject, UserInfo, `auth_time`/`acr`/`amr`.
- **OpenID Connect Discovery 1.0:** trusted issuer metadata, endpoints và JWKS URI.
- **RFC 7515 — JSON Web Signature (JWS):** protected header, signing input, signature serialization.
- **RFC 7516 — JSON Web Encryption (JWE):** encryption serialization, algorithms, IV/tag và nested JWT contexts.
- **RFC 7517 — JSON Web Key (JWK):** JWKS, `kid`, key types/usage.
- **RFC 7518 — JSON Web Algorithms (JWA):** HS/RS/PS/ES, encryption algorithms, key requirements.
- **RFC 7519 — JSON Web Token (JWT):** JWT compact format và registered claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm confusion, key trust, cross-JWT confusion và explicit typing.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `at+jwt`, audience, resource-server claims validation.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke token/grant theo policy và request handling.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, introspection caller protection và response semantics.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client identity và sender-constraining.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWT, asymmetric key, `htu`/`htm`/`jti`/`ath` và replay handling.
- **RFC 9421 — HTTP Message Signatures:** structured HTTP signature inputs, signature parameters và canonicalization theo profile.
- **RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF):** key derivation với extract/expand và context separation.
- **RFC 9180 — Hybrid Public Key Encryption (HPKE):** một ví dụ về construction/protocol encryption được chuẩn hóa khi đúng use case; không mặc nhiên thay OAuth/JOSE.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management:** key lifecycles, strength và key separation guidance.
- **NIST SP 800-38D — Galois/Counter Mode (GCM):** authenticated encryption, IV/nonce và tag requirements.
- **OWASP Cryptographic Storage Cheat Sheet:** authenticated encryption, key management, secure algorithms.
- **OWASP OAuth 2.0 / JSON Web Token Cheat Sheets:** bảo vệ authorization flow, JWT validation, token storage và chống token sidejacking.
- **Spring Security OAuth2 Client, OAuth2 Login và Resource Server documentation:** sử dụng framework chuẩn cho RP/RS, issuer/audience/token validation.
- **Nimbus JOSE + JWT documentation:** JOSE implementation, JWK/JWKS, JWT processing, algorithm/key selection.

**Kết luận:** **Không tự thiết kế crypto protocol** là nguyên tắc kiến trúc quan trọng vì an toàn không nằm riêng ở một phép toán AES, RSA, SHA hay HMAC. Nó nằm ở **cách xác thực danh tính, thỏa thuận/chọn khóa, ràng buộc thông điệp với transaction/issuer/audience, chống replay/downgrade, quản lý trạng thái, xử lý lỗi và thu hồi quyền**. Khi cần login và API security, hãy dùng **TLS + OAuth 2.0/OIDC + JOSE/introspection + các thư viện được bảo trì**, đồng thời cấu hình algorithm allowlist, PKCE/state/nonce, key trust, scope/audience, resource policy và revocation chính xác. Khi cần mã hóa ứng dụng, dùng **AEAD/JWE/managed encryption SDK** đúng protocol thay vì tự ghép cipher. Hãy dành công sức kỹ thuật cho **threat model, cấu hình, kiểm thử negative paths, vận hành và ứng phó sự cố**, không phát minh một giao thức mật mã mới chỉ vì code ngắn hơn. Một giao thức được chuẩn hóa, có implementation đúng và được xác minh end-to-end là nền tảng vững chắc hơn cho vòng đời token chống giả mạo, đánh cắp và phát lại.
