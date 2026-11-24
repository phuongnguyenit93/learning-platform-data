# Khi opaque token đơn giản hơn encrypted token

Một hệ thống thương mại điện tử có **Authorization Server (AS)** cấp access token cho `orders-api`, `payments-api` và `profile-api`. Mỗi API chỉ cần biết token có còn hiệu lực không, đến từ đúng issuer không, có đúng audience/scope không và người gọi có được truy cập bản ghi đang yêu cầu không. Nhóm phát triển lo thông tin trong JWT có thể bị người dùng đọc và đưa ra đề xuất: **“Mã hóa JWT thành JWE, vậy mọi thứ vừa kín vừa an toàn.”**

JWE có thể che payload khỏi người không có khóa giải mã, nhưng đổi lại phát sinh câu hỏi: **ai giữ decryption key, API nào được giải mã, xoay vòng key ra sao, làm sao thu hồi token trước hạn, xử lý nhiều recipients thế nào, và giải mã thành công có chứng minh issuer đáng tin không?** Nếu ứng dụng chỉ cần một credential không tự bộc lộ claims, một chuỗi ngẫu nhiên **opaque access token** cùng bản ghi trạng thái ở AS thường **đơn giản hơn**: API gửi token tới endpoint introspection có xác thực, AS trả metadata được phép dùng và trạng thái `active`.

Điều này **không** có nghĩa opaque token luôn tốt hơn JWE. Opaque reference token đổi độ phức tạp mật mã ở các verifiers lấy **token store, lookup, introspection, cache, độ trễ và tính sẵn sàng**. Bài này hướng dẫn chọn phương án theo **trust boundary, data privacy, revocation, latency, availability và vận hành**, không chọn chỉ theo vẻ ngoài “chuỗi nhìn bí ẩn hơn”.

Bài thuộc chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, nơi người học nắm mô hình tin cậy/vòng đời token, phân biệt JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC, và kiểm claims, scope, audience, lưu trữ, thu hồi, phòng chống đánh cắp hoặc phát lại. **Phạm vi trực tiếp là: khi nào sử dụng opaque token giúp tránh sự phức tạp không cần thiết của encrypted token.**

> **Ý chính:** Nếu mục tiêu chỉ là **không để token string bộc lộ claims** và muốn AS **quản lý tập trung trạng thái/thu hồi**, opaque reference token thường là đường đi ngắn. **Không cần JWE chỉ để tránh người dùng Base64URL-decode JWT.** Nhưng token opaque **vẫn là bearer credential**, cần TLS, bảo vệ lưu trữ/log, audience/scope, authorization và chống replay phù hợp.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **opaque reference token**, **JWT được ký bằng JWS**, **JWT được mã hóa bằng JWE**, **nested signed-and-encrypted JWT** và **token state ở server**.
2. Giải thích **Base64URL encoding không phải encryption**, JWS signature khác JWE confidentiality, và JWE không tự thay issuer authentication/authorization.
3. Liệt kê các yêu cầu khiến opaque reference token trở nên đơn giản: **data minimization, revocation gần thời gian thực, trạng thái grants, ít RS, trust tập trung**.
4. Mô tả luồng AS phát token CSPRNG, lưu fingerprint/metadata, RS introspect qua RFC 7662 và xử lý `active`/`scope`/`aud`/`iss`/`exp`.
5. Nêu giới hạn: **introspection latency, AS dependency, cache-staleness, outage, rate limiting, data store consistency**.
6. Phân biệt **RFC 7009 revocation** với việc xóa key JWE, hết hạn access token, refresh token rotation và logout.
7. Phân tích JWE key distribution, algorithm/key management, AEAD, multi-service recipients, key rotation và sự phức tạp của nested token validation.
8. So sánh kiến trúc OAuth 2.0/OIDC: backend/BFF, microservices, mobile/public clients, mTLS/DPoP, opaque access/refresh token, ID token.
9. Đọc được ví dụ HTTP introspection/revocation, Java CSPRNG/token fingerprint và Spring Security opaque-token Resource Server.
10. Lập bảng quyết định, ma trận lỗi bảo mật, kịch bản thử nghiệm và checklist để chọn **opaque vs JWE** theo yêu cầu thực, không theo khẩu hiệu “stateless tốt hơn”.

## 2. Đặt tên đúng: token là gì và “opaque” có nghĩa gì?

### 2.1. Opaque token: client không giải mã được cấu trúc hữu ích

Trong OAuth 2.0, **access token là credential được AS cấp** để client gọi Resource Server; định dạng cụ thể có thể không được định nghĩa cho client. **Opaque** nghĩa là bên sử dụng token như một chuỗi credential **không được dựa vào cấu trúc nội bộ**.

Một thiết kế phổ biến là **reference token**: AS sinh chuỗi ngẫu nhiên khó đoán, dùng nó làm khóa tra một bản ghi token/grant ở server.

~~~text
Client receives:  8rP3...random...Qm7

AS trusted token store:
  fingerprint(token) -> {
      token_type: "access",
      issuer: "https://login.example.com",
      subject: "user-742",
      client_id: "shop-bff",
      audience: ["orders-api"],
      scope: ["orders:read"],
      expires_at: "...",
      revoked_at: null,
      tenant_ref: "tenant-beta"
  }
~~~

Giá trị token ở trên **chỉ minh họa**, không phải token thật. Một token opaque có thể được triển khai bằng cách khác bên trong; **opaque không phải bảo đảm mọi AS đều dùng DB lookup**, nhưng mô hình **opaque random reference + AS state/introspection** là trọng tâm bài.

### 2.2. JWT ký bằng JWS không phải token được mã hóa

JWT dạng compact JWS thường có **ba phần**:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Payload JWS chứa claims và thường **đọc được** sau Base64URL decode. Chữ ký giúp xác minh integrity/nguồn ký theo key trust, không che `sub`, `aud`, `scope` hay email khỏi người cầm token.

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Claims này là ví dụ. **Đọc payload** không nhất thiết **sửa được claims** nếu chữ ký đúng và RS verify chuẩn; nhưng quyền đọc dữ liệu nhạy cảm vẫn là vấn đề privacy. Không giải quyết bằng cách gọi Base64URL là “encryption”.

### 2.3. JWE: mã hóa nội dung token

JWE Compact Serialization thường có **năm phần**:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

Protected header có thể mô tả:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-recipient-key-2026-11"
}
~~~

- `alg`: thuật toán **key management**, ví dụ RSA-OAEP-256 hoặc ECDH-ES.
- `enc`: thuật toán **mã hóa nội dung có xác thực**, ví dụ A256GCM.
- `kid`: key selector trong **nguồn khóa của recipient được tin**, không tự xác minh ai là issuer.
- Nội dung chỉ bên có key phù hợp mới giải mã được theo profile.

**JWE không tự bằng chứng AS đã ký**. Với profile yêu cầu issuer signature, cần bảo vệ nguồn nội dung bằng mô hình được định nghĩa rõ (ví dụ **nested JWT ký rồi mã hóa**) và kiểm cả lớp cần thiết. Thành công khi decrypt không tự cho phép request.

### 2.4. Ba lựa chọn không tương đương

| Thuộc tính | Opaque reference token | JWT JWS ký | Encrypted JWT/JWE |
|---|---|---|---|
| String có trực tiếp bộc lộ claims? | Không, nếu chỉ là random handle. | Có thể đọc claims sau Base64URL decode. | Không dễ đọc plaintext nếu không có decryption key. |
| Client cần hiểu payload? | Không. | Không nên tự diễn giải access token; RS đọc theo hợp đồng. | Không, trừ recipient được chỉ định. |
| RS lấy authorization metadata thế nào? | Introspection/lookup được AS cho phép. | Validate signature và claims trong token. | Decrypt rồi validate các lớp/claims theo profile. |
| RS phải giữ private/symmetric decryption key? | Không, với introspection qua kênh an toàn. | Không với asymmetric signing/public JWKS. | Thường phải có khả năng decrypt (key riêng hoặc dịch vụ giải mã). |
| Kiểm hiệu lực trước hạn | AS token state `active` nếu RS gọi/nhận cập nhật; cache ảnh hưởng độ trễ. | Thường cần denylist/state/event nếu muốn thu hồi trước `exp`. | Vẫn cần state/denylist/event nếu muốn thu hồi trước `exp`. |
| Phụ thuộc AS khi mỗi request | Có thể có nếu introspection trực tiếp. | Thường không khi JWKS cached và verify local. | Thường không cho decrypt local, nhưng phụ thuộc key services nếu decrypt từ xa. |
| Quản lý khóa | Token random và AS storage; transport/service credentials vẫn cần keys. | Issuer signing key + verifier public keys. | Decryption key management/rotation + issuer authenticity nếu yêu cầu. |
| Replay khi token bị lộ | **Có** nếu Bearer và còn active. | **Có** nếu Bearer và còn hạn. | **Có** nếu Bearer và được recipient chấp nhận. |

**Không chọn opaque chỉ vì “nó không có dấu chấm”.** Token opaque vẫn phải có entropy mạnh, TTL, audience, scope và kiểm quyền đúng. Một opaque string chứa user ID được Base64 encode hoặc quá ngắn **không phải credential an toàn**.

## 3. Câu hỏi đầu tiên: đang cần che gì và khỏi ai?

### 3.1. Trường hợp chỉ cần token không bộc lộ claims

Nếu frontend, log gateway hoặc trung gian có thể nhìn thấy access token, và không có nhu cầu cho chúng đọc `sub`, email, địa chỉ, vai trò hoặc tenant, cách đơn giản thường là **không nhét claims đó vào token string**.

~~~text
Opaque:
  Client sees random handle only
  RS gets only minimum metadata through trusted AS introspection

JWE:
  Client sees ciphertext
  RS must decrypt or call trusted decryption service
  Then validate provenance and authorization
~~~

Với opaque, bạn chuyển dữ liệu claims nhạy cảm sang **trusted AS/token store** và thiết kế policy trả metadata tối thiểu. Với JWE, bạn cần **crypto recipients và key custody**, nhưng có thể tránh network introspection trên từng request nếu tokens cho phép self-contained validation.

### 3.2. Token confidentiality khác resource confidentiality

Nếu dữ liệu đơn hàng API trả về cần bí mật, việc sử dụng opaque access token không mã hóa **response body**. Ngược lại, JWE mã hóa token cũng không mã hóa bảng orders, API response hay logs chứa dữ liệu đơn hàng. Cần TLS, data-at-rest protection và application authorization riêng.

### 3.3. Privacy không chỉ là chọn thuật toán

Giả sử JWS mang email và phone số của user, đội phát triển có các lựa chọn:

1. **Bỏ các claims không cần thiết** khỏi access token.
2. Chỉ dùng `sub`/internal IDs, hạn chế PII.
3. Chọn opaque access token nếu muốn token string không tiết lộ metadata.
4. Dùng JWE nếu có yêu cầu recipient-level confidentiality và key management được kiểm soát.
5. Dù chọn gì, **không log raw access/refresh token**; lưu trữ/truyền token an toàn.

Một JWE có thể che PII đối với client nhưng sau khi RS decrypt, ứng dụng vẫn có thể đưa PII vào logs. **Encryption không thay data minimization**.

### 3.4. Opaque token không phải “mã hóa không cần khóa”

Opaque random reference không mã hóa thông tin user; nó **không chứa plaintext claims để giải mã**. Secret thực sự là **giá trị token ngẫu nhiên**. AS có thể dùng HMAC/sha256 fingerprint để tra token, encryption-at-rest để bảo vệ token store và TLS cho introspection. Đừng kết luận một hệ thống opaque không cần cryptography: nó vẫn cần **CSPRNG, transport identity, storage protection và đôi khi sender-bound proof**.

## 4. Vì sao JWE đôi khi giải quyết quá nhiều thứ so với yêu cầu?

### 4.1. Vòng đời key của JWE

Nếu AS gửi encrypted JWT cho `orders-api`, cần trả lời:

- **Recipient nào sở hữu key decrypt?** Orders RS hay một gateway/decryption service?
- Dùng `RSA-OAEP-256`, `ECDH-ES` hoặc profile key management khác? `A256GCM`/AEAD với nonce/tag đúng?
- Public encryption key của RS được AS tin qua nguồn nào?
- Private decryption key nằm trong KMS/HSM, keystore hay container? Có non-exportable không?
- Nếu Orders RS có **nhiều bản sao/nhiều vùng**, key được đồng bộ hoặc điều phối decryption thế nào?
- Khi K1 rotate sang K2, những token JWE K1 còn hạn được xử lý ra sao?
- AS có cần ký JWT trước khi encrypt để RS xác minh **issuer/provenance** không?
- `kid` từ header được tìm trong trusted recipient key set hay có nguy cơ attacker key selection?
- Khi RS không decrypt được, response/error/log có rò plaintext, key ID hoặc oracle information không?
- Thêm RS thứ hai được phép nhận token bằng cách nào mà không chia private key bừa bãi?

Mỗi câu hỏi có thể có lời giải đúng, nhưng chúng là **chi phí hệ thống thực** nếu nhu cầu ban đầu chỉ là “đừng để access token tự chứa PII”.

### 4.2. Key distribution và nhiều Resource Servers

~~~mermaid
flowchart TD
    AS[Authorization Server]
    O[Orders API]
    P[Payments API]
    R[Reports API]
    K1[Orders decryption key K1]
    K2[Payments decryption key K2]
    K3[Reports decryption key K3]
    AS -->|Encrypted token for Orders| O
    AS -->|Encrypted token for Payments| P
    AS -->|Encrypted token for Reports| R
    O --> K1
    P --> K2
    R --> K3
~~~

Nếu dùng **recipient-specific keys**, phải có cơ chế phát token cho đúng recipients và ràng buộc audience. Nếu dùng **một shared symmetric decryption key** cho nhiều RS, người giữ khóa có thể decrypt nội dung token của các bên khác nếu luồng không tách ranh giới; blast radius tăng. Với **multi-recipient JWE**, format và key management có thể phức tạp hơn JWE compact single-recipient thông thường.

### 4.3. JWE “stateless” không có nghĩa bỏ được revocation

Một encrypted JWT mang `exp` tương lai vẫn có thể được giải mã và chấp nhận **sau khi user bị khóa tài khoản hoặc consent bị rút**, nếu RS không biết sự thay đổi và không kiểm state. Việc **xoay khóa giải mã** chỉ là điều khiển khả năng decrypt, không phải thay cho chính sách thu hồi một grant cụ thể.

Muốn revoke một token JWE trước `exp` mà không ảnh hưởng tokens khác, cần một dạng trạng thái, ví dụ:

- Centralized denylist/`jti` state.
- Short access-token TTL + refresh token revocation.
- Push revocation events cùng local caches/bounded staleness.
- Check grant/session status qua backend.
- Per-user/grant key rotation (thường phức tạp và không nên mặc định).

Khi đã cần **state và network check**, hãy đặt câu hỏi có thực sự cần JWE self-contained claims hay opaque reference token đơn giản hơn.

### 4.4. Encryption không chống token replay

Một JWE access token dùng như **Bearer** vẫn có thể bị attacker phát lại khi còn hiệu lực. Kẻ tấn công **không cần đọc plaintext** để gửi nguyên chuỗi ciphertext qua header:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <captured-encrypted-token>
~~~

Dấu `<captured-encrypted-token>` là placeholder, không phải credential thật. Chống replay cần bảo vệ token storage/log, TLS, TTL/audience/scope tối thiểu, revocation và **sender-constrained tokens** (DPoP hoặc mTLS) khi threat model yêu cầu. JWE riêng lẻ không ràng buộc token với người gửi.

## 5. Opaque reference token: biến “mật mã ở RS” thành “kiểm tra trạng thái ở AS”

### 5.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client / BFF
    participant AS as Authorization Server
    participant T as Secure Token Store
    participant RS as Orders Resource Server

    C->>AS: Valid OAuth grant / token request
    AS->>AS: Verify client, grant, subject, scope, audience
    AS->>AS: Generate high-entropy random reference token
    AS->>T: Store token fingerprint, grant metadata and expiry
    AS-->>C: Opaque access token
    C->>RS: Authorization Bearer opaque-token
    RS->>AS: Authenticated RFC7662 introspection over TLS
    AS->>T: Resolve fingerprint and current token state
    T-->>AS: active metadata or inactive
    AS-->>RS: active, scope, aud, iss, exp and authorized metadata
    RS->>RS: Validate audience, scope, principal, tenant and object policy
    RS-->>C: Allowed resource or denial
~~~

Thay vì RS giữ private JWE decryption key, RS dùng **introspection client credentials/service identity** với quyền tối thiểu để hỏi AS. Token string chỉ là reference. AS có thể dùng DB/Redis/token grant store để quyết định `active`.

### 5.2. “Một chỗ ra quyết định” không phải “mọi quyền đặt ở AS”

AS có thể kiểm token/grant state, issuer, scopes đã cấp và audience. Nhưng **Orders RS** vẫn phải kiểm:

- Token có được dành cho `orders-api`?
- Scope có `orders:read`?
- Principal là user hay service identity, có dùng đúng endpoint không?
- User thuộc đúng tenant không?
- Order ID này thuộc user hay user có quyền xem không?
- Có chính sách business mới khiến request bị từ chối không?

Không chuyển toàn bộ BOLA/IDOR/tenant ACL sang `active=true`; introspection chỉ trả metadata, **không thay quyết định authorization tại API**.

### 5.3. Dữ liệu server-side có thể sửa hoặc thu hồi

~~~text
accessTokenIndex[tokenFingerprint] = {
  token_type: ACCESS,
  issuer: trustedIssuer,
  subject: user-742,
  client_id: shop-bff,
  audience: orders-api,
  scope: orders:read,
  tenant: tenant-beta,
  issued_at: ...,
  expires_at: ...,
  revoked_at: null,
  grant_ref: internalGrantRef
}

Revoke:
  set revoked_at = now
  introspection returns active=false
~~~

Không cần reencrypt/reissue **mọi token khác** chỉ để vô hiệu một reference. Đây là lợi ích khi yêu cầu **thu hồi từng token/grant** mạnh. Nhưng tác dụng tại RS phụ thuộc **introspection response cache, replication lag và outage policy**.

### 5.4. “Không cần khóa giải mã tại RS” không có nghĩa không có credentials tại RS

RS phải **xác thực với introspection endpoint**: mTLS, client secret, private_key_jwt hoặc phương thức trusted service-to-service theo AS profile. Credential này vẫn cần bảo vệ, quyền gọi introspection phải được giới hạn, TLS và logging phải an toàn. **Mỗi RS không có JWE decryption key** không đồng nghĩa có thể phát introspection requests công khai/anonymous.

## 6. RFC 7662 introspection: hợp đồng thực sự cần kiểm

### 6.1. Request do Resource Server được xác thực gửi

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <redacted-rs-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<redacted-opaque-access-token>&token_type_hint=access_token
~~~

Đây là ví dụ hình thức; giá trị được đánh dấu redacted/placeholder, **không dùng credential thật**. Theo RFC 7662, introspection endpoint thường dùng HTTP POST với form-encoded `token` và `token_type_hint`; caller phải được AS xác thực/ủy quyền theo policy. `token_type_hint` chỉ là gợi ý, **không thay authorization và không bắt AS tin tuyệt đối**.

### 6.2. Response active

~~~json
{
  "active": true,
  "scope": "orders:read",
  "client_id": "shop-bff",
  "username": "user-742",
  "token_type": "Bearer",
  "exp": 1893456000,
  "iat": 1893452400,
  "sub": "user-742",
  "aud": ["orders-api"],
  "iss": "https://login.example.com"
}
~~~

RFC 7662 định nghĩa `active` cùng các trường metadata có thể có; **không phải mọi AS đều trả tất cả fields**. RS phải kiểm các điều kiện bắt buộc của hợp đồng: active true, expected issuer, audience, scope và lifetime khi profile đòi. Nếu AS không trả một trường RS bắt buộc để an toàn, phải **fail closed hoặc sửa hợp đồng**, không tự suy ra giá trị an toàn.

### 6.3. Response inactive

~~~json
{
  "active": false
}
~~~

AS có thể trả `active=false` cho token không tồn tại, đã hết hạn, bị revoke hoặc không được phép introspect theo policy. **Không tiết lộ user/tenant/reason của token inactive cho caller không có quyền**. Phía RS xử lý như invalid token, không dựa vào lời giải thích “revoked vs unknown” để cấp quyền.

### 6.4. HTTP 200 không đồng nghĩa token active

Một introspection response có HTTP status **200 OK** và body `{"active":false}` vẫn biểu thị token **không được chấp nhận**. Phải parse body và kiểm `active===true`. Không code:

~~~text
if (introspectionHttpStatus == 200) {
    acceptBearerToken();  // SAI
}
~~~

Tương tự, HTTP timeout/401/403/5xx từ introspection endpoint không được diễn giải thành `active=true`. Tách **service failure** khỏi **token inactive** để log/metrics phù hợp, nhưng **không cho qua request** nếu không có chứng cứ token hợp lệ theo chính sách.

### 6.5. Chỉ trả metadata đủ dùng cho RS

Nếu `orders-api` chỉ cần `sub`, `aud`, `scope`, `exp` và một tenant reference, AS không nên trả PII như địa chỉ/số điện thoại hay scopes ngoài resource không được phép. Introspection metadata là **dữ liệu có thể nhạy cảm** và chỉ nên trả cho authenticated/authorized RS, có audience/tenant policy tương ứng.

### 6.6. Không coi introspection như một public token validator

Một endpoint không yêu cầu xác thực hoặc không rate limit có thể trở thành **token enumeration/probing oracle**, công cụ dò credential và dịch vụ DoS. Áp dụng:

- TLS và caller authentication, key/secret lifecycle riêng.
- Resource-level authorization cho token metadata.
- Rate limiting/throttling phù hợp, request size constraints.
- Response minimization, đặc biệt với inactive tokens.
- Audit `introspection_active`/`inactive`/`failed` bằng **fingerprint/internal ref**, không raw token.
- Không cache response chứa user data ở shared public CDN/proxy.

## 7. RFC 7009 revocation: một nơi dừng token theo trạng thái

### 7.1. Revocation request

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Authorization: Basic <redacted-authorized-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<redacted-token>&token_type_hint=access_token
~~~

Với RFC 7009, endpoint thu hồi token yêu cầu **client authentication khi áp dụng** và xác minh quyền client theo spec; response thành công thường HTTP **200** kể cả token đã không hợp lệ hoặc không tồn tại nhằm hạn chế token existence probing. **HTTP 200 không đồng nghĩa token trước đó đã active**.

### 7.2. Tác động tới opaque access token

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant T as Token Store
    participant RS as Resource Server
    C->>AS: RFC7009 revoke opaque access token
    AS->>T: Mark token/grant state revoked atomically
    AS-->>C: HTTP 200 under revocation rules
    RS->>AS: Next authenticated introspection
    AS->>T: Look up fingerprint and active state
    T-->>AS: Revoked
    AS-->>RS: active false
    RS-->>C: Reject further use
~~~

Khi không có positive cache ở RS và state được đọc nhất quán, RS có thể quan sát revoke ở **request tiếp theo**. Nhưng đa vùng, replicated stores và caches có thể tạo **cửa sổ trễ**. Không hứa “thu hồi ngay lập tức tuyệt đối” chỉ vì token opaque.

### 7.3. Refresh token và access token phải phân biệt

- **Access token** cấp quyền gọi RS; thường ngắn hạn.
- **Refresh token** được AS nhận tại token endpoint để xin access token mới theo grant; không gửi refresh token cho RS.
- Revoke một refresh token có thể tác động grant/related tokens theo policy và RFC 7009 semantics; không mặc định mọi AS thu hồi mọi access tokens tương ứng tức thì.
- Rotation/reuse detection của refresh family là **state machine riêng**; opaque access token không tự có refresh rotation.
- Logout BFF session, revoke refresh family và revoke access token là **các hành động khác nhau**.

### 7.4. JWE vẫn phải có cơ chế thu hồi tương ứng

Một access token JWE đã phát và còn decrypt được theo key/trust policy vẫn có thể được nhận khi grant đã revoke nếu RS không kiểm state. Muốn revoke từng JWE mà không vô hiệu toàn bộ recipient key, phải bổ sung denylist/state/events hoặc dùng TTL cực ngắn. Khi đã có central state, ưu thế vận hành của opaque token có thể rõ ràng hơn.

## 8. Đổi lại của opaque: introspection cache và cửa sổ thu hồi

### 8.1. Vì sao cần cache?

Nếu `orders-api` nhận 20.000 requests/giây và hỏi AS introspection cho từng request, AS/token store phải chịu số lookup tương ứng, thêm network latency, failure dependency và chi phí. Vì vậy nhiều kiến trúc cache **positive introspection** tại RS hoặc một gateway tin cậy.

~~~text
First request with token T:
  RS -> AS authenticated introspection
  AS -> active=true, exp, aud, scope, sub
  RS -> cache approved metadata with bounded TTL

Next request using T:
  RS -> cache lookup
  RS -> if cache valid, enforce audience/scope/object policy
~~~

**Cache không thay authorization**: mỗi request vẫn kiểm resource permission, tenant/object ownership và sender binding khi áp dụng.

### 8.2. TTL và revocation visibility

Một upper-bound mang tính thiết kế:

\[
T_{\mathrm{cache}}\leq\min(T_{\mathrm{configured}},T_{\mathrm{remainingTokenLifetime}},T_{\mathrm{riskLimit}})
\]

Ví dụ: token còn 120 giây, configured positive-cache TTL 15 giây, mục tiêu thu hồi nhìn thấy trong 20 giây. Cache có thể giới hạn ở **15 giây hoặc ngắn hơn**. Nhưng **TTL 15 giây không tự bảo đảm SLA 20 giây** nếu token-store replication lag, clock skew, nhiều tầng cache, request-in-flight hoặc message bus trễ. Phải đo **end-to-end revoke-to-deny latency**.

Không refresh TTL “từ lúc cache hit” vô hạn. Metadata cached phải không còn được chấp nhận qua `exp` và key gồm issuer/RS/token identity context thích hợp.

### 8.3. Tại sao thu hồi không tức thời tuyệt đối?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    participant ST as Token Store
    C->>RS: Request with token T
    RS->>AS: Introspect T
    AS->>ST: Read token state
    AS-->>RS: active true
    RS->>RS: Cache active metadata for short TTL
    C->>AS: Revoke T
    AS->>ST: Set revoked state
    AS-->>C: Revocation acknowledged
    C->>RS: Reuse T before cache expiry
    RS->>RS: May still see cached active metadata
    RS->>AS: Re-introspect after TTL or invalidation
    AS-->>RS: active false
    RS-->>C: Reject
~~~

Đối với API rủi ro cao, có thể cần cache TTL ngắn hơn, push invalidation, online permission check hoặc thực hiện introspection mỗi thao tác nhạy cảm. Một API chỉ đọc dữ liệu ít nhạy cảm có thể có độ trễ chấp nhận khác. **Không áp cùng TTL cho mọi scope**.

### 8.4. Negative cache, token guessing và log leakage

Cache `active=false` ngắn hạn có thể giảm lặp lookup, nhưng đừng cho attacker sinh hàng triệu random credentials lấp cache. Tránh:

- Cache raw bearer token dưới dạng key có thể bị dump/log.
- Ghi token string vào high-cardinality metrics/traces.
- Cache vô hạn `active=false` khi có race giữa issuance/replication.
- Phân biệt unknown/revoked/expired với PII cho caller không có quyền.
- Đổi `active=false` thành `active=true` khi introspection timeout.

Nếu cần, cache bằng token fingerprint thay raw string, có bound size/TTL/rate limiting và key namespace theo issuer/RS.

### 8.5. Push invalidation không miễn distributed-systems design

AS có thể phát `TOKEN_REVOKED` tới RS/gateway để clear positive cache. Nhưng message delivery, authentication, duplicate/out-of-order, subscriber outage và replication consistency trở thành phần phải quản trị. **Push invalidation không làm state biến mất**; khi event bị mất vẫn cần TTL hoặc online checks để chặn stale acceptance.

## 9. Introspection outage: availability là cái giá thật

### 9.1. Phân loại tình huống

| Trạng thái | Quan sát | Hành vi an toàn |
|---|---|---|
| Token inactive | HTTP 200, `{"active":false}`. | Reject token. |
| Introspection auth lỗi | HTTP 401/403 của AS đối với RS credential. | Không tin token, sửa caller authentication. |
| AS timeout hoặc 5xx | Không có metadata đáng tin mới. | Fail closed/degraded cache theo policy đã duyệt, không coi token active. |
| Cached active response còn hạn | Có dữ liệu verified trong bounded window. | Có thể tiếp tục theo policy; vẫn kiểm `exp`/`aud`/`scope`/binding. |
| Cache hết hạn và AS unreachable | Không có bằng chứng hiện tại. | Fail closed với protected resource; không trả protected content. |
| AS signer KMS lỗi | Token issuance mới có thể thất bại. | Introspection có thể vẫn hoạt động nếu token state service độc lập. |

Không bao giờ viết `if AS down then allow all bearer tokens`. Với high availability, đầu tư **AS introspection HA, token store replication và capacity**, chứ không bỏ kiểm tra authentication.

### 9.2. Self-contained và reference token đều có phụ thuộc

~~~text
Signed/encrypted self-contained JWT:
  May be verified/decrypted locally with cached trusted keys.
  Early revocation may require state or events.
  Remote KMS decryption reintroduces dependency.

Opaque reference token:
  Central AS state can reflect revocation.
  Live introspection adds network and AS availability dependency.
  Bounded cache reduces traffic but increases stale-state window.
~~~

Không khẳng định JWE luôn “offline” nếu decryption qua remote key service. Không khẳng định opaque luôn “lookup DB từng request” nếu đã dùng cache đúng policy.

### 9.3. Reliability patterns

- Timeout ngắn nhưng phù hợp P99 introspection latency.
- Retry giới hạn, jitter, tránh retry storm.
- Circuit breaker và bulkheads cho AS/token store.
- Rate limit token probes, cap body/header sizes.
- Cache hit/miss/TTL và AS introspection failure metrics.
- Token store persistence/replication/DR; tránh “hồi sinh” revoked token khi failover.
- Policy rõ cho outage: với token không xác minh được, **không fail open**.

Một circuit breaker mở không cho phép bypass introspection rồi chấp nhận token. Khi chắc chắn credential sai, trả 401 invalid_token theo Bearer contract; khi phụ thuộc tạm không thể kiểm, có thể trả 503 Service Unavailable tùy gateway contract, nhưng **không trả 200 protected data**.

### 9.4. High availability không chỉ là thêm AS replicas

Token state cần consistency cho revocation writes, TTL check độc lập cleanup, replication/clock management và backup restore. Failover không được đưa token đã revoke trở lại `active=true` vì replica quá cũ. Đo revoke-to-deny sau failover, regional outage, introspection cache expiry và malicious token storms.

## 10. Những yêu cầu thường khiến opaque đơn giản hơn JWE

### 10.1. Thu hồi từng access token hoặc grant trong thời gian ngắn

Ví dụ:

- Admin khóa account, access token phải bị chặn trong vài giây.
- Client rút consent, không dùng tiếp token cũ.
- Một thiết bị bị đánh cắp, cần revoke một session/token cụ thể.
- Refresh family bị reuse, cần chặn grant/related tokens theo policy.
- Scope/grant bị rút và RS cần thấy biến đổi sớm.

Khi central state đã là bắt buộc, **opaque reference + introspection** có thể đơn giản hơn JWE cộng denylist/`jti` state và key rotation logic. Nhưng introspection cache/replica lag phải được tính vào SLA.

### 10.2. Ít Resource Servers, cùng trust domain

~~~mermaid
flowchart LR
    BFF[Shop BFF]
    O[Orders API]
    P[Payments API]
    AS[Authorization Server with Token Store]
    BFF -->|Audience-scoped opaque access token| O
    BFF -->|Different audience-scoped access token| P
    O -->|Authenticated introspection| AS
    P -->|Authenticated introspection| AS
~~~

Khi chỉ có vài internal APIs, introspection sẵn có và lượng request vừa phải, vận hành token record thường ít thành phần mới hơn thiết kế phân phối JWE decryption keys cho từng API. Mỗi RS vẫn phải kiểm `aud`, `scope` và tenant/object authorization; đừng phát một token audience quá rộng chỉ để tiết kiệm issuance.

### 10.3. Token metadata thường xuyên đổi theo grant/consent

Nếu ứng dụng phải quan sát grant revoked, tenant membership hoặc client permissions thay đổi, token-state check có lợi. Nhưng **không được nâng scope của token cũ bằng cách sửa metadata mà bỏ grant mới**. Chính sách phải rõ: revoke/reissue token, giới hạn scope theo consent và invalidate caches.

### 10.4. Muốn hạn chế PII trong client-visible tokens

Opaque reference không chứa email/roles/tenant trong token string nếu thiết kế đúng. AS trả metadata tối thiểu tới RS được xác thực. Nó không chặn XSS/malware lấy raw bearer token; khi phù hợp, **BFF giữ access/refresh tokens server-side** và browser chỉ giữ session cookie HttpOnly/Secure/SameSite với CSRF controls.

### 10.5. AS đã có token/grant store

Nếu AS vốn lưu refresh families, OAuth grants, sessions và consent, thêm access-token reference index có thể đơn giản hơn xây JWE encryption/decryption key lifecycle. Đổi lại phải đo storage load, indexes, token TTL cleanup, cache coherence và HA. “Có database” chưa đủ chứng minh introspection sẽ đạt P99 requirement.

## 11. Những lúc JWE có lý do rõ ràng

### 11.1. Recipient phải đọc claims bí mật khi offline

Một bên nhận có key decryption an toàn, cần xử lý self-contained information lúc không kết nối tới AS, có thể dùng JWE theo profile phù hợp. Revocation realtime sẽ khó; phải có expiry, key compromise policy và xác minh issuer/provenance.

### 11.2. Confidentiality theo từng recipient hoặc hợp đồng

Một token/message đi qua nhiều trung gian nhưng chỉ một recipient được phép đọc plaintext có thể cần **JWE object-level encryption**. Opaque reference yêu cầu recipient hỏi AS để lấy metadata; nếu không có đường tin cậy hoặc hợp đồng không cho, opaque không thay thế được JWE.

### 11.3. Đối tác yêu cầu encrypted ID token hoặc UserInfo

OIDC và một số ngành có profiles mã hóa cụ thể. Không thể tự đổi một encrypted ID token/UserInfo JWT thành opaque access token khi giao thức bên nhận đòi JWE. Cần chuẩn `alg`/`enc`, recipient key, issuer signature và correct token purpose theo profile.

### 11.4. Xử lý một chiều hoặc bất đồng bộ

Nếu bên nhận xử lý assertion sau khi không thể introspect, JWE có thể phù hợp. Tuy nhiên không phải mọi encrypted application message đều là OAuth access token; có thể dùng chuẩn message encryption riêng thay vì ép nó thành bearer token.

### 11.5. Lưu lượng lớn, đọc claims tối giản, revocation không cần tức thì

Trong trường hợp đó, **JWT JWS có claims tối thiểu** có thể đơn giản hơn cả opaque lẫn JWE: RS verify local bằng trusted public JWKS, không cần decrypt hoặc introspect mỗi request. **Không tự giới hạn lựa chọn chỉ giữa opaque và encrypted JWT.**

### 11.6. Bảng ngữ cảnh

| Bối cảnh | Ứng viên ưu tiên đánh giá | Điều kiện cần đo |
|---|---|---|
| APIs nội bộ, AS sẵn, muốn revoke nhanh | Opaque + introspection | P99 lookup, AS HA, cache/revoke lag. |
| Chỉ cần không lộ claims trong token string | Opaque + data minimization | Metadata minimization, issuer/RS trust. |
| Nhiều RS với audiences độc lập | Opaque per audience hoặc signed JWT per audience | Token issuance policies, audience isolation. |
| Recipient offline, phải đọc nội dung bí mật | JWE theo profile | Key custody, expiry, issuer validation, offline revocation. |
| Compliance bắt encrypted ID token | JWE/OIDC | Key distribution, algorithm registration, nested validation. |
| Traffic rất lớn, ít PII, TTL ngắn | Minimal JWS | Local verification, token theft and revocation policy. |
| Revoke tức thì trên operation rủi ro cao | State/online authorization bất kể format | End-to-end SLA, caches, consistency. |
| Access token bị đánh cắp | TLS/storage protection + DPoP/mTLS khi phù hợp | Bearer replay tests, client key binding. |

## 12. Cây quyết định: không mã hóa chỉ vì “muốn an toàn”

### 12.1. Các câu hỏi theo thứ tự

~~~mermaid
flowchart TD
    A[Why encrypt this OAuth token?] --> B{Must recipient read claims offline?}
    B -->|Yes| C{Ready for decryption key custody and issuer validation?}
    C -->|Yes| D[Evaluate JWE profile]
    C -->|No| E[Revisit requirements and deployment]
    B -->|No| F{Need hidden claims or centralized revocation?}
    F -->|Yes| G{Reliable AS introspection and token store?}
    G -->|Yes| H[Evaluate opaque reference access token]
    G -->|No| I[Engineer HA, latency and security SLA first]
    F -->|No| J[Evaluate minimal claims signed JWT JWS]
    D --> K[Always check aud, issuer, time, scope, replay]
    H --> K
    J --> K
~~~

Đây là heuristic để trao đổi kiến trúc, **không** thay design review. Nếu vừa cần offline confidentiality vừa đòi revoke tức thì, bạn phải làm rõ SLA vì offline processing và realtime revocation có thể mâu thuẫn.

### 12.2. Requirement phải đo được

| Tiêu chí | Câu hỏi | Cách kiểm thử |
|---|---|---|
| Confidentiality | Ai không được đọc claims? Có cần claims đó trong token? | Data flow, PII audit, Base64URL/decryption checks. |
| Issuer provenance | RS tin issuer/key hoặc introspection endpoint nào? | Wrong-issuer/key-source tests. |
| Authorization | `aud`, `scope`, tenant và object policy nằm đâu? | BOLA/IDOR/cross-audience tests. |
| Revocation | Sau revoke tối đa bao lâu mọi RS từ chối token? | Revoke-to-deny measurement, kể cả cache/failover. |
| Availability | AS/Redis/KMS down thì xác minh ra sao? | Dependency outage drills, HA/bounded cache. |
| Latency | P95/P99 token verification budget bao nhiêu? | Cache hit/miss, network, cryptographic benchmarks. |
| Key custody | Ai có private decrypt key/quyền Decrypt? | KMS/Secret Manager IAM audit, key export denial. |
| Interoperability | OIDC/client/partner đòi format nào? | Contract/conformance tests. |
| Replay | Token bị lấy có dùng lại được không? | TLS/storage/DPoP/mTLS proof tests. |

### 12.3. Không chọn theo khẩu hiệu “stateless”

JWE/JWS self-contained có thể giúp verify local, nhưng **grant, consent, signing/decryption key state, revocation và session state** vẫn tồn tại ở cấp hệ thống. Opaque reference đưa token state vào online path nhưng có thể giảm đáng kể sự phức tạp phân phối private decryption keys. So sánh **tổng chi phí** chứ không chỉ số database queries.

## 13. Authorization Server phát opaque token đúng cách

### 13.1. CSPRNG sinh reference credential

~~~text
randomBytes = CSPRNG(32 bytes)
opaqueToken = BASE64URL_NO_PADDING(randomBytes)
fingerprint = SHA256(UTF8(opaqueToken))

store(fingerprint, approvedTokenMetadata)
send opaqueToken only to authorized client over TLS
~~~

32 bytes random tương ứng 256 bit entropy nếu CSPRNG đúng. Không dùng Base64(user ID), số tự tăng, timestamp+clientId, `Math.random()` hay `java.util.Random` để tạo bearer reference token.

### 13.2. Chỉ lưu fingerprint khi phù hợp

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE oauth_access_token (
    token_hash BYTEA PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject_ref TEXT NOT NULL,
    client_id TEXT NOT NULL,
    audience TEXT NOT NULL,
    scopes TEXT NOT NULL,
    tenant_ref TEXT,
    grant_ref TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX idx_token_grant ON oauth_access_token(grant_ref);
CREATE INDEX idx_token_expiry ON oauth_access_token(expires_at);
~~~

Schema này cố tình đơn giản: production có thể cần audience list, sender binding, token purpose, grant family, unique indexes, transaction isolation, audit và partition/TTL. Với **token high entropy**, SHA-256 fingerprint có thể phù hợp cho lookup theo threat model; cân nhắc HMAC-SHA-256 với server-only key để giảm khả năng correlation từ token dumps trong một số ngữ cảnh. **Hash lookup token khác password hashing**: password cần KDF/salt riêng.

### 13.3. Chỉ ghi metadata đã được grant policy chấp nhận

Token record phải ràng buộc với **client ID được xác thực/đăng ký, subject/service principal đúng loại, approved audience/scope, issuer, token type, issue/expiry, tenant/grant refs, revocation state và confirmation key khi áp dụng**.

Một token random không ngăn scope escalation: nếu AS lưu `scope=admin` trái grant, introspection sẽ trả claim sai qua `active=true`. **AS phải kiểm client/grant/consent/subject/scope/resource trước khi cấp token**.

### 13.4. Server-side active predicate

~~~text
fingerprint = hash(receivedToken)
record = tokenStore.lookup(issuerNamespace, fingerprint)

isActive =
    record exists
    AND record.type == ACCESS
    AND record.revokedAt == null
    AND now < record.expiresAt
    AND now >= record.notBefore when applicable
    AND grant state permits use

if not isActive:
    return {"active": false}

return minimum metadata allowed for authenticated RS
~~~

Không lookup record theo `sub`/`client_id` do request tự khai rồi coi đó là token possession. Expiry phải được kiểm dù cleanup job chưa xóa record; namespace và authorized introspection caller giúp chống cross-issuer confusion/leak.

### 13.5. Backend lưu trữ

| Backend | Điểm mạnh | Rủi ro vận hành |
|---|---|---|
| SQL | Transaction/grant audit rõ, persistence và queries. | P99 lookup, indexes, replicas/lock contention. |
| Redis | Low-latency reference lookup và TTL. | Persistence/eviction, replication lag, failover hồi sinh revoked state. |
| DB + Redis cache | Nguồn sự thật durable với throughput cao. | Invalidation, cache stampede, race/consistency. |
| Provider-managed token store | Bớt custom code. | Phải kiểm cụ thể introspection/revoke semantics và scale. |

**Đổi JWE sang opaque không tự làm hệ thống HA hoặc đủ nhanh.** Cần load tests và recovery drills tương ứng số RS/request thực tế.

## 14. Java 17: tạo opaque token và token fingerprint

### 14.1. CSPRNG và Base64URL

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class OpaqueTokenFactory {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int TOKEN_BYTES = 32;

    private OpaqueTokenFactory() {}

    public static IssuedReference generate() throws Exception {
        byte[] secretBytes = new byte[TOKEN_BYTES];
        RNG.nextBytes(secretBytes);

        String token = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(secretBytes);

        byte[] fingerprint = MessageDigest
            .getInstance("SHA-256")
            .digest(token.getBytes(StandardCharsets.US_ASCII));

        return new IssuedReference(token, fingerprint);
    }

    public record IssuedReference(
        String token,
        byte[] fingerprint
    ) {}
}
~~~

### 14.2. Ranh giới bảo mật của ví dụ

- `generate()` tạo reference credential, **không** tự validate OAuth grant/client/scope/audience hoặc lưu token store.
- Cần DB transaction đảm bảo token metadata đã ghi trước khi trả token và uniqueness/collision handling.
- **Không log `token`** hay lưu dưới dạng plaintext tại RS/AS nếu không cần thiết. Java String không wipe được; hạn chế lifetime/sao chép và bảo vệ heap dumps.
- `fingerprint` dùng làm lookup index; nó không là JWS signature/JWE ciphertext.
- Đây là minh họa ở Java 17; framework AS có thể cung cấp token generator đã bảo trì, nên ưu tiên sử dụng theo nhu cầu.

### 14.3. Phân biệt keys và credentials

~~~text
CSPRNG 32-byte string -> opaque bearer credential
SHA256(token)         -> token-store lookup fingerprint
HMAC(serverKey, token)-> optional keyed fingerprint scheme
AS signing private K  -> JWS issuer signing
JWE recipient key     -> decrypt encrypted token in JWE profile
~~~

Không dùng cùng key material tùy tiện cho fingerprint HMAC, JWT HS256 signing, AES encryption và client authentication. Mỗi purpose cần key usage/rotation/IAM riêng.

### 14.4. Refresh token không chỉ là access token dài hơn

Refresh token cũng thường là opaque random credential, nhưng **chỉ dùng ở AS token endpoint** theo grant, cần refresh-family rotation/reuse detection và client binding. Không đưa refresh token tới RS chỉ vì cả hai cùng là chuỗi random. Đổi AS signing key JWT không tự revoke refresh family.

## 15. Spring Security Resource Server: opaque-token introspection

### 15.1. Cấu hình Spring Boot 3/Spring Security 6 minh họa

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: REPLACE_FROM_SECRET_MANAGER
~~~

`client-secret` ở đây là **placeholder**, không phải secret thật. Với production, dùng secret injection/workload identity/mTLS theo AS profile, cấu hình TLS, timeout và credential rotation. Không commit client secret vào source, image hoặc log. Đây là cách cấu hình phổ biến; phiên bản Spring cụ thể và phương thức client auth cần kiểm lại khi triển khai.

### 15.2. SecurityFilterChain với scope

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerConfiguration {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

`hasAuthority("SCOPE_orders:read")` dựa trên mapping introspected scopes → authorities của provider/framework. **Không đủ kiểm object ownership**. Token dành service principal cũng không được tự xử lý như user identity.

### 15.3. Kiểm issuer, audience và token purpose

Một cấu hình introspection URI chưa chắc tự đáp ứng custom contract như `aud`, `iss`, `exp`, principal type, tenant, DPoP/mTLS binding. Dùng wrapper `OpaqueTokenIntrospector` hoặc policy adapter khi cần, với logic khái niệm:

~~~text
if active != true: REJECT
if issuer != trustedIssuer: REJECT
if audiences exclude expectedResource: REJECT
if tokenType != access-token: REJECT
if required expiry missing or expired: REJECT
if required scope missing: FORBID
if sender-constrained proof invalid: REJECT
if tenant/object unauthorized: FORBID
else: ALLOW
~~~

Không tin claims từ unverified HTTP headers. Nếu AS không cung cấp field RS cần để kiểm policy, phải **thay hợp đồng introspection hoặc fail closed**, không mặc định allow.

### 15.4. Java policy helper minh họa

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class OrdersTokenPolicy {
    private static final String ISSUER = "https://login.example.com";
    private static final String RESOURCE = "orders-api";

    public record Metadata(
        boolean active,
        String issuer,
        Set<String> audiences,
        Set<String> scopes,
        Instant expiresAt,
        boolean isAccessToken
    ) {}

    public static boolean permitsRead(Metadata t, Clock clock) {
        Objects.requireNonNull(t);
        Objects.requireNonNull(clock);
        return t.active()
            && t.isAccessToken()
            && ISSUER.equals(t.issuer())
            && t.audiences() != null
            && t.audiences().contains(RESOURCE)
            && t.scopes() != null
            && t.scopes().contains("orders:read")
            && t.expiresAt() != null
            && t.expiresAt().isAfter(clock.instant());
    }
}
~~~

`Metadata` phải được populate bằng **trusted introspection result**; code này không gọi HTTP, không kiểm tenant/object ACL và không xác minh DPoP/mTLS. Spring adapter thực tế cần test các trường hợp `aud` string/array, `scope` space-delimited, `exp` Unix seconds, missing claims và clock skew.

### 15.5. Phân biệt 401, 403 và outage

- Token inactive/expired → authentication failure, thường Bearer 401/`invalid_token`.
- Token active nhưng thiếu scope → authorization failure, thường 403/`insufficient_scope` nếu theo contract.
- Token hợp lệ nhưng sai tenant/object → business authorization deny.
- AS introspection timeout/5xx → dependency failure, **không cho token qua**; có thể 503 tùy API contract.
- RS client introspection credentials sai (AS 401/403) → lỗi cấu hình service identity, không phải bằng chứng user token sai.
- HTTP 200 introspection **không tự là active**; phải kiểm body.

## 16. Token active vẫn có thể sai tenant hoặc quyền object

### 16.1. BOLA/IDOR với opaque token

~~~text
GET /api/orders/123
Authorization: Bearer <opaque-token>

AS introspection:
  active=true
  sub=user-742
  aud=orders-api
  scope=orders:read
  tenant=tenant-beta

Order 123:
  tenant=tenant-anpha
  owner=user-999
~~~

Nếu Orders chỉ kiểm `active` và scope thì dễ xảy ra **BOLA/IDOR**. Opaque không thay authorization ở business/data layer.

### 16.2. SQL minh họa

~~~sql
SELECT id, tenant_id, owner_user_id, total_amount
FROM orders
WHERE id = :orderId
  AND tenant_id = :trustedTenantId
  AND owner_user_id = :authenticatedUserId;
~~~

Đây là policy owner-only; production có thể có ACL theo team/role. `trustedTenantId` và `authenticatedUserId` phải đến từ verified principal/current policy, **không từ query hoặc header `X-User-Id` tự khai**.

### 16.3. Client Credentials không chứng minh user consent

Một token `client_credentials` có thể đại diện service principal. Endpoint `GET /me` cần user principal phải từ chối service-only access token dù introspection `active=true`. Đừng tự coi `client_id` hay `sub` là chứng cứ user hiện diện/MFA.

### 16.4. Bốn lớp chính sách

~~~text
Credential validity  -> trusted AS introspection
Coarse API privileges -> verified scope/audience and client type
Current tenant roles -> tenant authorization service / DB
Object ownership     -> Orders service / DB
Sender binding       -> DPoP or mTLS proof when required
~~~

Các lớp có thể cache độc lập, nhưng đều có TTL/consistency trade-off. **Opaque reference không tự cập nhật quyền trên từng order** khi membership thay đổi.

## 17. Replay vẫn có thể xảy ra với opaque và JWE

### 17.1. Attacker không cần đọc claims

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Legitimate Client
    participant X as Attacker
    participant RS as Resource Server
    participant AS as Authorization Server
    U->>RS: Valid Bearer opaque token T
    X->>X: Copies T from unsafe storage/log
    X->>RS: Replays T unchanged
    RS->>AS: Authenticated introspection T
    AS-->>RS: active true
    RS-->>X: May return data absent binding/other policy
~~~

Token opaque là credential dù nó không có claims đọc được. JWE bearer cũng có thể bị replay: attacker gửi nguyên ciphertext mà **không cần decrypt**.

### 17.2. Các lớp chống token theft

- TLS, trusted proxy termination; không log `Authorization`, URL chứa token hoặc cookies.
- Browser BFF giữ tokens server-side, session cookie `HttpOnly`/`Secure`/`SameSite` với CSRF controls.
- Token TTL ngắn, scope/audience tối thiểu.
- Refresh-token family rotation/reuse detection và revocation.
- DPoP/mTLS sender constraints khi AS/RS/client cùng hỗ trợ.
- Rate limiting, anomaly monitoring, audit không chứa raw credential.
- Không coi encryption là binding giữa token và client gốc.

### 17.3. DPoP-bound opaque token

AS có thể bind access token với client public key thumbprint. RS phải:

1. Introspect token và lấy confirmation metadata đáng tin.
2. Verify DPoP proof JWT signature và public key theo profile.
3. Kiểm `htu`/`htm`/`iat`/`jti`/nonce khi yêu cầu.
4. Kiểm `ath` ràng buộc proof với access token.
5. So thumbprint proof với token `cnf.jkt`.
6. Kiểm replay freshness/cache phù hợp.

`active=true` không đủ với sender-constrained token. Kẻ tấn công lấy được **cả token lẫn private holder key** vẫn có rủi ro.

### 17.4. mTLS certificate-bound opaque token

Với RFC 8705, access token có thể chứa binding `cnf.x5t#S256`. RS phải kiểm TLS client certificate thật và metadata; không tin `X-Client-Cert` từ public HTTP request khi gateway không bảo vệ identity propagation.

### 17.5. Logout khác revoke

BFF xóa session cookie không mặc nhiên revoke refresh/access tokens ở AS. Nếu muốn vô hiệu một token đã lộ hoặc device session, phải làm rõ logout, RFC 7009 revocation, refresh family invalidation và cache lag.

## 18. JWE đúng chuẩn vẫn đòi validation và key lifecycle

### 18.1. Decrypt không thay issuer verification

Một JWE dùng AEAD che payload đối với người không có key. Nhưng **decrypt success không tự chứng minh AS là issuer** trong mọi trust model, đặc biệt nếu các bên chia symmetric encryption key. Với profile cần issuer authentication, có thể ký JWS rồi mã hóa thành nested JWE:

~~~text
Recipient validates:
  trusted recipient key and JWE alg/enc
  decrypt and AEAD authenticate
  if nested signed JWT: verify trusted issuer JWS signature
  check iss, aud, exp, nbf, type, scope
  check tenant/object authorization
  check revocation/state/sender proof as required
~~~

Không chỉ giải mã rồi dùng `role=admin` mà bỏ issuer, audience hoặc current permission.

### 18.2. Rotation key giải mã khác revoke một credential

Nếu Orders rotate decryption key K1→K2:

- AS cần encrypt token mới cho K2 trusted public recipient key.
- RS có thể tạm giữ khả năng decrypt K1 để đọc JWE cũ, theo bounded transition.
- Khi private K1 compromise, vẫn giữ K1 có thể nguy hiểm tùy encryption/provenance profile.
- Không thể revoke một user/grant riêng chỉ bằng thay shared key K1 mà không ảnh hưởng nhiều tokens khác.
- Multi-recipient JWE và key distribution có thể phức tạp khi mở rộng số RS.

Opaque reference có record state riêng để revoke từng credential, **đổi lại** lookup/AS availability dependency.

### 18.3. Decryption key custody không miễn operation audit

Một RS decrypt JWE có thể giữ private key trong KMS/HSM hoặc protected keystore; phải quản lý IAM, `Decrypt` rights, rotation/backup/DR, rate limit, algorithm/profile, môi trường và side-channel/log exposure. Với opaque introspection, RS cần caller credential để hỏi AS thay vì JWE decryption secret. Đó là **đổi mô hình tin cậy**, không loại bỏ mọi secrets.

### 18.4. Data minimization trước encryption

Nếu AS phát JWE chứa nhiều PII “vì mã hóa được”, RS vẫn decrypt, có thể log/serialize dữ liệu nhạy cảm. Xem xét **bỏ claims không cần thiết**, dùng opaque với metadata tối thiểu hoặc signed JWS nhỏ gọn trước khi chọn JWE.

## 19. Bốn ví dụ kiến trúc: lúc nào đơn giản và lúc nào không?

### 19.1. BFF và APIs cùng tổ chức

~~~mermaid
flowchart LR
    BR[Browser] -->|Secure session cookie| BFF[Shop BFF]
    BFF -->|OAuth token/refresh grant| AS[Authorization Server]
    AS --> TS[Token and grant state store]
    BFF -->|Opaque access token aud orders| ORD[Orders API]
    ORD -->|Authenticated introspection| AS
~~~

Trong kiến trúc này browser không cần thấy access/refresh token nếu BFF quản lý server-side. Opaque access token không tự mang claims; Orders introspect AS và áp object ACL. Lợi ích là AS có state thu hồi rõ, API không cần JWE decryption key. Đổi lại **AS introspection và BFF session store** phải có HA/bảo vệ credentials. Cookie `HttpOnly`/`Secure`/`SameSite`, CSRF/session fixation defenses và XSS controls vẫn cần.

### 19.2. Microservices nội bộ với nhiều audiences

~~~text
Token A: opaque access token, audience=orders-api, scope=orders:read
Token B: opaque access token, audience=payments-api, scope=payments:write

Orders -> validate Token A and its audience
Payments -> validate Token B and its audience
~~~

Không chuyển Token A của Orders sang Payments rồi kỳ vọng Payments introspect `active=true` là đủ. **Token forwarding sai audience vẫn là lỗi**, bất kể format. Nếu cần gọi API khác thay user, cân nhắc Authorization Server cấp token đúng audience hoặc **RFC 8693 token exchange** khi architecture/profile cho phép.

### 19.3. Đối tác bên ngoài Resource Server

Nếu partner không thể duy trì kênh introspection bảo mật với AS, JWS signed JWT ngắn hạn hoặc JWE theo hợp đồng có thể phù hợp. Nếu partner dùng introspection, cần:

- Authenticated client/service identity và permissions riêng cho partner.
- Audience-scoped metadata: không trả tenant/user PII ngoài nhu cầu.
- TLS, network/availability SLA, rate limiting.
- Hợp đồng response fields, cache TTL, error categories và migration.
- Cơ chế revoke/compromise communication và logs đã biên tập.
- Data residency/privacy controls theo tổ chức và quy định liên quan.

Một đối tác có thể yêu cầu **encrypted JWT theo profile**, không thể thay bằng opaque chỉ vì nội bộ thấy đơn giản hơn.

### 19.4. Thiết bị offline hoặc xử lý một chiều

Nếu bên nhận xử lý token sau nhiều giờ **không có kết nối AS**, opaque introspection có thể không khả thi. JWE/JWS self-contained được kiểm tra local có thể là lựa chọn, nhưng **revoke realtime không bảo đảm được khi offline**. Cần khóa/issuer trust pinning, TTL phù hợp, chính sách cập nhật revocation, key compromise và chặn dữ liệu quá nhạy cảm khi thiết bị bị mất.

### 19.5. Public client/mobile

Mobile/SPA không thể bảo mật một client secret như confidential backend. Opaque access token giúp hạn chế claims hiển thị, **không** ngăn app storage compromise. Dùng Authorization Code + PKCE, token lifetime thích hợp, OS secure storage/WebCrypto khi áp dụng, DPoP nếu hệ thống hỗ trợ. Không nhúng RS introspection client secret vào mobile SPA để ứng dụng tự gọi introspection; introspection dành cho caller được AS cấp quyền phù hợp.

## 20. Vận hành opaque reference token không chỉ là “thêm một bảng DB”

### 20.1. Capacity planning

Introspection thường thêm một request nội bộ và ít nhất một trạng thái lookup. Những biến cần đo:

- External request rate theo RS/region/client.
- Cache hit/miss ratio và TTL theo risk class.
- P50/P95/P99 AS introspection latency.
- Primary vs replica reads, write/replication lag.
- Token revocation write throughput và end-to-end propagation.
- Redis/DB CPU/memory/network/connection pools.
- Unknown/inactive token attempts và rate limit behavior.
- Circuit breaker, retry counts, cache stampede khi AS recover.

Không giả định token store đủ nhanh chỉ vì một lookup theo hash có complexity trung bình O(1) hoặc index tìm nhanh; network, connection pool, replication, locks và TLS overhead có thể chiếm phần lớn P99.

### 20.2. Một chuỗi outage cần test

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant RS as Orders API
    participant AS as Introspection Service
    participant ST as Token Store
    C->>RS: Request token T
    RS->>AS: Introspect
    AS->>ST: Read token state
    ST--xAS: Timeout
    AS--xRS: 5xx or timeout
    Note over RS: No trusted active response
    RS-->>C: Protected resource is not returned
~~~

Một team có thể chọn 503 thay vì 401 để phản ánh AS dependency outage. Nhưng **một service error không phải authenticated token acceptance**. Nếu dùng cached active response trước outage, phải tuân expiry và bounded cache policy được duyệt.

### 20.3. Revocation khi nhiều vùng

Nếu AS region A ghi `revoked_at` vào primary DB nhưng RS region B introspect replica đang trễ, RS có thể thấy active cũ. Có thể dùng strong read cho revocation-sensitive endpoints, event invalidation, bounded cache hoặc high-risk online checks. Quan trọng là **đặt target SLA và đo thử**, không tuyên bố “opaque revoke tức thì”.

### 20.4. Kết thúc vòng đời, cleanup và retention

- Expired/revoked records phải không active dù cleanup chưa chạy.
- Tách retention cho token metadata, grant audit, introspection events và security logs.
- Không đưa raw token vào backups/traces; giữ metadata theo privacy/data minimization.
- Nếu có TTL eviction, tránh xóa state revocation quá sớm khiến fallback/restore nhận lại token cũ.
- Đánh giá vacuum/index bloat, partition/archiving, key migration khi DB schema thay đổi.
- Refresh family/consent revocation có dependencies khác access-token record TTL.

### 20.5. Audit và metrics

~~~text
oauth_introspection_total{issuer,resource,result}
oauth_introspection_latency_seconds{issuer,resource}
oauth_introspection_cache_total{resource,result}
oauth_token_revocation_total{issuer,token_class,result}
oauth_revocation_visibility_lag_seconds{resource}
oauth_token_store_read_errors_total{region}
oauth_introspection_auth_failure_total{resource}
oauth_access_denied_total{resource,category}
oauth_sender_binding_failure_total{resource,proof_type}
~~~

Tránh raw token, user ID, `jti`/token hash, subject, attacker-controlled `kid` và high-cardinality tenant IDs trong metric labels. Logs cần redaction và chỉ chứa **safe internal references** theo quyền, không raw credentials.

### 20.6. Truy vết đúng lỗi

Một `401` từ RS có thể do token inactive, audience mismatch, invalid/missing credential, hoặc DPoP proof fail; một `403` có thể do thiếu scope hay object ACL; một `503` có thể do introspection outage. **Không dán nhãn mọi lỗi là “token decrypt failed”** khi dùng opaque reference vì nó không có bước decrypt.

## 21. Threat model: opaque có thể đơn giản hơn nhưng không tự an toàn

| Sai lầm / mối đe dọa | Opaque/JWE bị ảnh hưởng thế nào? | Biện pháp |
|---|---|---|
| **Token opaque entropy yếu** | Attacker đoán reference có hiệu lực. | CSPRNG đủ entropy, length/pattern tests. |
| **Base64 user ID được gọi là opaque** | Dễ đoán, token không phải secret an toàn. | Random credential không phụ thuộc user/sequence. |
| **Raw token lưu ở DB/log** | Lộ bearer credential, có thể replay. | Token fingerprint lookup, secret redaction. |
| **Introspection không xác thực caller** | Token probing/enumeration và lộ metadata. | Caller authentication/authorization, TLS, rate limit. |
| **HTTP 200 bị coi active** | `active=false` vẫn được chấp nhận. | Parse body, require `active===true`. |
| **AS timeout được fail open** | Token vô hiệu/bị đánh cắp được chấp nhận. | Fail closed/bounded cache đã duyệt. |
| **AS trả quá nhiều PII** | RS/client logs lộ user profile. | Metadata minimization và authorized RS scope. |
| **RS bỏ `aud`** | Token Orders dùng tại Payments. | Enforce audience ở mọi RS. |
| **RS bỏ scope/tenant/ACL** | Cross-tenant BOLA/IDOR. | Object-level authorization ở service/DB. |
| **Service token bị coi là user token** | Client Credentials vượt user-only policy. | Principal-type/grant semantics validation. |
| **Positive cache TTL quá dài** | Revoked token còn được nhận. | Bound TTL bằng expiry/risk; đo visibility lag. |
| **Cache key không tách issuer/resource** | Dùng metadata token sai context. | Namespace cache and audience-specific validation. |
| **Cache nhận inactive rồi tự nâng active** | Broken auth khi AS outage. | Fail closed, verified active metadata only. |
| **Replicas stale sau revoke** | Token bị thu hồi vẫn active ở một vùng. | Consistency strategy, canary, end-to-end tests. |
| **Restore DB cũ** | Token revoked bị “hồi sinh”. | Durable revoke state và DR runbook. |
| **Introspection credentials lộ** | Attacker tra token metadata, có thể enumerate. | Secret storage/IAM/mTLS, rotate, scope checks. |
| **HMAC lookup key dùng chung với JWT signing** | Key-reuse/cross-purpose blast radius. | Separate keys/purposes; HMAC optional đúng threat model. |
| **JWE plaintext bị coi đã xác thực issuer** | Attacker/colluding key holder tạo ciphertext giả. | JWS issuer validation/nested profile khi cần. |
| **`alg`/`enc` JWE không allowlist** | Algorithm confusion/downgrade/key misuse. | Strict JOSE profiles/key usage. |
| **JWE decryption key phân rộng** | Lộ nội dung tokens nhiều APIs. | Recipient-specific keys, KMS/HSM/least privilege. |
| **JWE key rotate không có overlap policy** | Tokens cũ không decrypt được hoặc key cũ bị tin quá lâu. | Key lifecycle, expiry/compromise distinction. |
| **JWE token được hiểu là chống replay** | Bearer ciphertext bị dùng lại nguyên vẹn. | TTL, storage/TLS, DPoP/mTLS, revoke. |
| **JWS ký nhưng nghĩ claims bí mật** | Base64URL payload lộ PII. | Data minimization/opaque/JWE khi cần. |
| **ID token gửi làm access token** | Cross-JWT confusion, API cấp sai quyền. | Token type/purpose/`aud` checks. |
| **Refresh token gửi tới RS** | Lộ credential có thể xin token mới. | Refresh token AS-only, client binding/rotation. |
| **Token metadata được sửa nâng scope trái grant** | Introspection hợp thức hóa quyền sai. | Immutable grant ceilings, revoke/reissue, audit. |
| **Introspection error chứa raw token** | Credential lộ qua APM/logs. | Allowlist logging, safe error categories. |
| **DDoS bằng random opaque strings** | Token store/AS bị overwhelm. | Rate limiting, bounded negative cache/connection pools. |
| **DPoP/mTLS binding không được kiểm** | Token copy vẫn replay dù có `cnf`. | Proof/cert binding validation. |
| **Sử dụng encryption thay authorization** | JWE decrypt rồi cho qua mặc dù không có quyền. | Issuer/aud/scope/tenant/object policy. |

### 21.1. Sự cố key compromise khác token theft

- Lộ **một opaque access token** → attacker có thể replay trong phạm vi TTL/scope/audience nếu bearer, giải quyết bằng revoke record/grant và bảo vệ nguồn lộ.
- Lộ **AS JWT signing private key** → attacker có thể ký nhiều JWT giả nếu RS còn trust key; cần emergency issuer-key cutoff/reissue.
- Lộ **JWE decryption private key** → confidentiality của ciphertexts dành cho key đó có thể bị ảnh hưởng; cần đánh giá key custody, ciphertext exposure và migration.
- Lộ **introspection client credential** → attacker có thể truy cập token metadata nếu AS không có controls khác; cần rotate credential/giới hạn query.
- Lộ **refresh token** → có thể xin access tokens mới theo grant nếu không bị revoke/bound, cần refresh family incident response.

**Không thay tất cả các trường hợp bằng một giải pháp “mã hóa token” hoặc “đổi JWT signing key”.**

## 22. Kiểm thử từ issuer đến Resource Server

### 22.1. Test fixtures

~~~text
Issuer: https://login.test.example
Resources: orders-api, payments-api
Client: shop-bff
Subject: user-test-742, tenant-beta
Opaque token T1:
  32 bytes CSPRNG
  active=true
  scope=orders:read
  aud=orders-api
  exp=future
Opaque token T2:
  revoked=true
Opaque token T3:
  expired=true
Opaque token T4:
  active=true
  aud=payments-api

JWE test token J1:
  encrypted for orders recipient test key
  includes signed issuer JWT under nested profile

AS introspection:
  authenticated caller, RFC7662 response
AS revocation:
  authorized client, RFC7009 response
Cache:
  bounded positive TTL and negative TTL
~~~

Fixtures phải dùng **test keys, random tokens và giả lập consent/grants**, tuyệt đối không sử dụng production credentials hay JWT/refresh token thật.

### 22.2. Token validation và purpose tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Valid T1 | RS introspect, audience/scope/expiry đúng. | Chấp nhận authentication, rồi áp ACL. |
| Unknown opaque token | Random high entropy string không có record. | `active=false`, RS reject. |
| Token T2 revoked | AS trả inactive. | RS reject sau policy cache/consistency window. |
| Token T3 expired | `exp` quá khứ. | RS reject dù DB record còn. |
| Wrong audience T4 | Token dành Payments gọi Orders. | RS reject dù `active=true`. |
| Missing required scope | `orders:write` nhưng endpoint read. | Scope deny, không cấp tài nguyên. |
| Wrong issuer | Introspection metadata `iss` không phải trusted AS. | Reject theo contract. |
| Missing issuer/audience | Metadata thiếu field bắt buộc. | Fail closed, không default allow. |
| Missing/invalid `exp` | Contract yêu cầu expiry. | Fail closed, không coi never expire. |
| Refresh token tại RS | Client gửi refresh token trong Bearer header. | Không chấp nhận như access credential. |
| ID token tại RS | Client gửi OIDC ID token. | Reject token purpose/audience. |
| Client-credentials token tại user-only endpoint | Service principal gọi `GET /me`. | Reject dù active. |
| Cross-tenant resource | User Beta đọc Order Anpha. | Object ACL reject. |
| Token revoked, scope cached | Cache stale trong bounds. | Đo cửa sổ và bảo đảm hết hạn đúng SLA. |
| DPoP-bound token không proof | Missing DPoP header. | Reject. |
| DPoP proof key mismatch | Wrong proof key/`ath`. | Reject. |
| mTLS-bound token wrong cert | Peer certificate khác bound fingerprint. | Reject. |

### 22.3. RFC 7662 và RFC 7009 tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Introspection HTTP 200/`active=false` | Token invalid. | RS không coi HTTP 200 là authenticated. |
| Caller introspection thiếu auth | Anonymous request. | AS reject theo policy, không lộ metadata. |
| Caller Orders hỏi token Payments | Token không thuộc audience/permitted metadata. | AS hạn chế response, RS không accept. |
| Introspection HTTP 401/403 | RS client credentials sai. | RS fail closed, phân loại config error. |
| Introspection timeout/5xx | AS unreachable. | Không accept unverified token, policy 503/bounded cache. |
| Token hint sai | `token_type_hint=refresh_token` cho access token. | Không coi hint là grant, xử lý theo AS policy. |
| RFC7009 revoke active token | Authorized caller revoke T1. | Server state inactive, RS eventually rejects. |
| RFC7009 revoke unknown token | Token không tồn tại. | Response semantics không lộ sự tồn tại. |
| Revocation sai client | Client không sở hữu/không được phép revoke. | AS kiểm authorization, không cho revoked-other-client sai policy. |
| Refresh family reuse | R1 cũ bị dùng sau rotation. | Family/reuse policy kích hoạt, không phát token mới trái phép. |
| Multiple AS regions | Revoke region A, introspect B. | Đo propagation và enforce agreed SLA. |
| AS DB restore | Restore snapshot trước revoke. | Không hồi sinh revoked token theo DR policy. |

### 22.4. Cache, load và failure tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Cache hit | Token metadata hợp lệ còn TTL. | Không reintrospect nếu policy cho phép, vẫn kiểm expiry/aud/ACL. |
| Token hết hạn trong cache | `exp` đến trước cache TTL. | Cache entry không được chấp nhận qua expiry. |
| Sliding TTL bug | Repeated cache hits. | Không kéo dài indefinite active state. |
| Negative-cache flood | Nhiều random tokens. | Bounded cache size, rate limiting, AS không quá tải. |
| Cache collision/cross-issuer | Same fingerprint namespace giả định. | Không dùng context của issuer/resource khác. |
| Cache invalidation event lost | Revoke push event bị mất. | TTL/online check vẫn giới hạn stale window. |
| Introspection retry storm | AS 5xx, nhiều RS retry. | Circuit breaker/bulkheads, bounded retries. |
| AS unavailable, cache empty | Không có trusted metadata. | Fail closed, không trả protected content. |
| AS unavailable, positive cache still valid | Policy cho phép bounded stale. | Tôn trọng exp/aud/scope/risk và expiry of cache. |
| Token store replica lag | Revoked state cập nhật chậm. | Đo latency, không vượt risk SLA. |
| High QPS | Thousands of requests per second. | P99, throughput, cache metrics đáp ứng SLO. |

### 22.5. JWE comparison tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| JWS Base64URL decode | Đọc payload từ signed JWT. | Chứng minh JWS không che PII. |
| JWE đúng recipient | Decrypt bằng trusted key K1. | AEAD success rồi kiểm issuer/aud/exp/scope. |
| JWE wrong recipient | K2 không khớp. | Decrypt fail, không fallback arbitrary key. |
| JWE tag tamper | Sửa ciphertext/tag. | Authentication failure. |
| JWE unsupported `alg`/`enc` | Header yêu cầu algorithm ngoài allowlist. | Reject. |
| JWE chỉ được decrypt nhưng issuer giả | Profile yêu cầu nested signed JWS. | Reject vì thiếu/invalid issuer provenance. |
| Nested JWE inner JWT sai audience | Decrypt/signature đúng, aud Payments tại Orders. | Reject. |
| JWE expired | Token quá `exp`. | Reject dù decrypt được. |
| JWE revoked in grant state | JWE self-contained vẫn decrypt. | State/denylist/event check reject theo policy. |
| JWE bearer replay | Attacker gửi nguyên ciphertext. | Không tự chặn, phải có sender binding/revocation. |
| JWE key K1 rotation | Token K1 còn hạn rồi rotate K2. | Bounded overlap hoặc cutoff theo risk, không silent acceptance. |
| JWE decryption key compromised | Recipient private key lộ. | Privacy/key incident plan và trust/key migration. |

## 23. Pseudocode tích hợp: bằng chứng test, không chỉ ví dụ đẹp

### 23.1. Token opaque sinh đúng và không lộ claims

~~~text
test "random reference token does not embed claims":
    approvedGrant = AS.authorize(
        client="shop-bff",
        subject="user-test-742",
        audience="orders-api",
        scope={"orders:read"}
    )
    token = AS.issueOpaqueAccessToken(approvedGrant)

    assert token has enough CSPRNG entropy
    assert token has no encoded sub/email/scope claims
    assert tokenStore.containsFingerprint(hash(token))
    assert tokenStore.doesNotStoreRawToken(token)
    assert logsDoNotContain(token)
    assert metricsDoNotUseTokenAsLabel(token)
~~~

Đây là yêu cầu kiểm theo thiết kế; **không thể chứng minh entropy chỉ bằng regex/độ dài**. Cần unit test generator với entropy source được kiểm soát, code review CSPRNG và test uniqueness/rate phù hợp.

### 23.2. Introspection mới là nguồn trạng thái

~~~text
test "Orders accepts active opaque access token only for Orders":
    T = AS.issueOpaqueAccessToken(
        grant=authorizedUserGrant,
        audience="orders-api",
        scope={"orders:read"}
    )

    response = AS.introspect(
        token=T,
        caller=authenticatedOrdersRS
    )
    assert response.httpStatus == 200
    assert response.body.active == true
    assert response.body.aud contains "orders-api"
    assert response.body.scope contains "orders:read"

    assert ordersRS.acceptsAuthentication(T)
    assert paymentsRS.rejects(T)
    assert ordersRS.rejectsReadOfOtherUsersOrder(T)
~~~

### 23.3. HTTP 200 inactive phải bị từ chối

~~~text
test "HTTP 200 does not mean token active":
    introspectionStub.returns(
        status=200,
        body={"active": false}
    )
    assert ordersRS.rejectsBearerToken("random-unknown-token")
    assert noProtectedContentReturned()
~~~

### 23.4. Revoke-to-deny và cache cửa sổ trễ

~~~text
test "revoke-to-deny meets configured SLA":
    T = AS.issueOpaqueAccessToken(validGrant)
    ordersRS.introspectAndCache(T)
    assert ordersRS.accepts(T)

    revokeAt = fixedClock.now()
    AS.revoke(T, authorizedClient)

    advanceClockWithinCacheTTL()
    observeSecurityDecisionFor(T)

    advanceClockPastBoundedTTLAndPropagation()
    assert ordersRS.rejects(T)
    assert observedRevokeToDeny <= approvedSecuritySLA
    assert cacheNeverExtendsBeyondTokenExpiry()
~~~

**Pseudocode này có một assertion SLA** cần đo trong integration environment thật; không dùng mock clock đơn lẻ để chứng minh mọi replication/region path đạt SLA. Nếu policy yêu cầu reject ngay sau revoke acknowledgement, cần thiết kế online state/strong consistency/invalidation tương ứng, không chỉ TTL.

### 23.5. Outage không thành fail-open

~~~text
test "AS introspection unavailable and no trusted cache":
    introspectionEndpoint.timeout()
    cache.clear()
    response = ordersRS.getProtectedOrder(withToken=T)
    assert response.hasNoProtectedResource()
    assert response.status in configuredFailClosedStatuses
    assert logsContainSafeDependencyErrorOnly()
~~~

### 23.6. DPoP/mTLS bound token không phải plain Bearer

~~~text
test "sender-bound opaque token rejects copied token":
    T = AS.issueDPoPBoundOpaqueToken(clientPublicKeyA)
    assert RS.accepts(T, validProofSignedByPrivateKeyA)
    assert RS.rejects(T, missingProof)
    assert RS.rejects(T, proofSignedByPrivateKeyB)
    assert RS.rejects(T, reusedProofJti)
    assert RS.rejects(T, wrongHtuOrHtmOrAth)
~~~

### 23.7. JWE không thay issuer validation

~~~text
test "JWE decryption is not sufficient for access":
    token = encryptForOrdersRecipient(
        innerClaims={iss:"attacker-issuer",
                     aud:"orders-api",
                     scope:"admin"}
    )
    assert ordersRS.canDecryptWhenKeyMatches(token)
    assert ordersRS.rejectsWithoutTrustedIssuerSignature(token)

test "encrypted bearer token can still be replayed":
    T = AS.issueEncryptedBearerAccessToken()
    attacker = copiedTokenOnlyWithoutDecryptKey()
    assert encryptionAloneDoesNotBindSender(T, attacker)
    assert senderBindingAndRevocationPolicyControlsAcceptance()
~~~

### 23.8. Kết quả tests không thay threat model

Pseudocode không chạy trực tiếp. Một test chỉ verify `active=true` nhưng không kiểm scope/tenant là **thiếu**. Một test JWE chỉ kiểm decrypt success nhưng không kiểm issuer/JWS/purpose cũng **thiếu**. Trước production cần chạy integration tests với **AS/RS thực hoặc test provider, KMS/Secret Manager test keys, client auth, DB/Redis replication, network failures và security telemetry**. Không dùng production refresh tokens/private keys trong fixtures.

## 24. Bài tập tình huống và đáp án giải thích

### 24.1. Bài 1 — “Mã hóa JWT để user không thấy email”

Shop frontend có access JWT chứa `email`, `phone`, `roles`, nhưng Orders API chỉ cần user ID, scope và tenant.

**Hỏi:** Có cần JWE không?

**Đáp án:** Trước tiên **bỏ email/phone và claims không cần thiết**. Nếu mục tiêu chỉ là token không lộ metadata cho client và AS có sẵn token store/introspection, **opaque access token** thường đơn giản hơn JWE. JWE chỉ đáng đầu tư nếu có nhu cầu recipient confidentiality/offline/profile yêu cầu cụ thể.

### 24.2. Bài 2 — “HTTP 200 từ introspection là token hợp lệ”

RS gọi endpoint và nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**Đáp án:** **Từ chối.** RFC 7662 trả HTTP 200 cho introspection request được xử lý thành công, body `active=false` cho biết credential không được nhận. Không kiểm mỗi HTTP status.

### 24.3. Bài 3 — “Revoke opaque nghĩa là mọi request từ chối ngay”

AS đã đánh dấu revoke, nhưng RS cache positive 60 giây.

**Đáp án:** RS có thể tiếp tục chấp nhận trong cửa sổ cache theo thiết kế. Muốn SLA revoke 5 giây, cần giảm TTL, invalidate caches, online check hoặc kiến trúc strong-enough consistency. Phải **đo end-to-end**, không chỉ kiểm DB row `revoked_at`.

### 24.4. Bài 4 — “Nếu AS timeout thì cứ cho qua”

Orders API không introspect được do AS outage, dev thêm code `catch timeout { return active=true; }`.

**Đáp án:** **Sai và nguy hiểm.** Token bị revoke/giả có thể được chấp nhận. Fail closed, có thể trả 503 theo contract; nếu có cache đã xác minh và còn bounded validity thì chỉ dùng theo risk policy. Đầu tư HA/circuit breaker thay fail-open.

### 24.5. Bài 5 — “JWE đã mã hóa thì không bị replay”

Một attacker có JWE Bearer token nhưng không có private decryption key.

**Đáp án:** Họ không cần giải mã. **Replay nguyên ciphertext** vào RS là đủ nếu token vẫn được chấp nhận và không sender-bound. Cần TLS/secure storage, short TTL, revoke, DPoP/mTLS khi phù hợp.

### 24.6. Bài 6 — “Token opaque không cần cryptography”

Đội phát token bằng `base64(userId + currentTime)`, lưu vào DB, gọi là opaque.

**Đáp án:** Không an toàn vì token có thể bị dự đoán. Cần **CSPRNG high entropy**, bảo vệ token trên TLS/storage, fingerprint lookup/DB security và introspection caller authentication. Opaque không cần JWE decryption cho RS, nhưng vẫn cần cryptography ở những lớp khác.

### 24.7. Bài 7 — “Một token active ở mọi API”

Orders và Payments chung AS. AS introspection trả `active=true` cho token `aud=orders-api`; Payments chỉ kiểm active.

**Đáp án:** Payments phải **từ chối** vì sai audience. Resource Server phải kiểm scope/audience/principal/tenant ngay cả khi introspection thành công; issuer không tự cấp toàn quyền cho mọi API.

### 24.8. Bài 8 — “Token opaque giải quyết quyền tenant”

User Beta có `orders:read` nhưng gọi xem order thuộc Anpha.

**Đáp án:** Không. Orders API phải kiểm current tenant membership và object ACL. `active=true` và scope đúng vẫn không cho phép cross-tenant BOLA/IDOR.

### 24.9. Bài 9 — “Partner offline vẫn dùng opaque”

Đối tác xử lý tokens ở nhà máy không có kết nối AS trong nhiều giờ, nhưng cần đọc claims bí mật.

**Đáp án:** Online introspection không đáp ứng. Đánh giá JWE theo recipient profile (và chữ ký/issuer verification khi cần), TTL, key provisioning và offline revocation risk. Không giả định opaque đơn giản ở mô hình disconnected.

### 24.10. Bài 10 — “Dùng JWE thay refresh token store”

AS muốn phát encrypted refresh token rồi không lưu grant state nữa, dù yêu cầu detect refresh reuse.

**Đáp án:** Encryption không tự phát hiện reuse; **refresh rotation/family state** vẫn cần kiểm. Có thể dùng encrypted refresh token theo một profile, nhưng nếu yêu cầu revoke/reuse nhanh, state có thể không tránh được. Opaque refresh token + family record thường dễ audit/thu hồi hơn.

### 24.11. Bài 11 — “Không log raw token mà vẫn debug được không?”

Introspection returns 5xx và đội muốn ghi raw bearer T để tìm record.

**Đáp án:** Dùng **server-only token fingerprint/internal token record reference**, trace ID và error class, không raw T. Metrics aggregate theo issuer/resource/outcome, không dùng token hash/`jti` làm nhãn high-cardinality công khai.

### 24.12. Bài 12 — “JWE decrypt được thì role admin đúng”

RS nhận một JWE có `role=admin`, giải mã AEAD thành công rồi chấp nhận.

**Đáp án:** Decrypt success không tự xác minh issuer/provenance trong mọi scheme. Theo profile, cần nested signed JWT hoặc cơ chế trusted authenticated issuer, `iss`/`aud`/`exp`/scope/purpose và object policy; không tin `role` chỉ vì ciphertext xác thực theo shared recipient key.

### 24.13. Bài 13 — “Mỗi RS giữ cùng key decrypt”

Ba RS chia cùng symmetric JWE decryption key, mỗi RS chỉ được đọc claims dành cho chính nó.

**Đáp án:** Shared key có thể cho bất cứ holder nào decrypt tokens nếu tiếp cận ciphertext, tăng blast radius. Cần audience isolation, recipient-specific key management hoặc cân nhắc opaque introspection với metadata scope theo caller; audit và policy vẫn cần.

### 24.14. Bài 14 — “Chọn định dạng cho một API tài chính”

Ứng dụng có AS HA, token store và payment API nội bộ. Yêu cầu: revoke token sau báo mất thiết bị trong 3 giây, không bộc lộ PII ở token, P99 introspection budget chấp nhận được.

**Đáp án:** **Opaque reference** là ứng viên mạnh, nhưng phải chứng minh revocation visibility ≤ 3 giây **qua mọi cache/region**, caller auth, strong-enough state và load/failover test. Không kết luận đạt SLA chỉ vì token opaque.

### 24.15. Bài 15 — “Signed JWT nhỏ gọn có thể tốt hơn cả hai?”

API có lưu lượng lớn, JWT chỉ chứa `iss`, `aud`, `sub`, `scope`, `exp` ngắn hạn, không có PII nhạy cảm, revocation chấp nhận đến expiry.

**Đáp án:** **JWS signed JWT** với public-key verification local có thể là lựa chọn đơn giản: không cần per-request introspection cũng không cần JWE decryption keys ở RS. Phải kiểm signature/issuer/audience/time/purpose, sender/bearer risk, grant policy và object ACL.

## 25. Checklist chọn và triển khai opaque thay encrypted token

- [ ] Đã xác định rõ cần **token confidentiality** hay chỉ không muốn client đọc claims.
- [ ] Đã loại bớt claims không cần thiết, đặc biệt PII, trước khi chọn JWE/opaque.
- [ ] Phân biệt opaque reference token, JWS signed JWT, JWE encrypted JWT và nested signed+encrypted JWT.
- [ ] Không gọi Base64URL là encryption; JWS không mặc định che payload.
- [ ] Không coi JWE decrypt success là issuer signature/authorization hoàn chỉnh.
- [ ] Có lý do cụ thể nếu yêu cầu JWE: offline recipient, object confidentiality hoặc profile chuẩn/partner.
- [ ] Đánh giá **minimal signed JWT JWS** như phương án thứ ba khi phù hợp.
- [ ] Với opaque reference, token phải sinh từ CSPRNG entropy đủ mạnh, không từ user ID/timestamp/sequence.
- [ ] Token store lookup theo protected fingerprint/reference, không lưu raw token khi không cần.
- [ ] AS token issuance kiểm client/grant/consent/subject/resource/scope/tenant policy trước khi cấp.
- [ ] Opaque access token và refresh token có roles/records/TTL/rotation khác nhau.
- [ ] Introspection endpoint tuân RFC 7662, HTTP POST/form và caller authentication/authorization.
- [ ] HTTP 200 với `active=false` bị từ chối; không coi status 200 là token active.
- [ ] Response inactive không tiết lộ PII/owner/revoke reason trái quyền.
- [ ] AS chỉ trả metadata tối thiểu mà RS cần, có policy theo caller/audience.
- [ ] RS kiểm expected issuer, audience, expiry, token type, scope và principal semantics.
- [ ] RS kiểm current tenant membership, object ownership/ACL; `active=true` không thay BOLA/IDOR protection.
- [ ] Không chấp nhận ID token, client assertion hoặc refresh token thay OAuth access token.
- [ ] RFC 7009 revocation được kiểm authorization và semantics; không lộ token existence ngoài policy.
- [ ] Đã đo **revoke-to-deny SLA** qua caches/replicas/failover, không chỉ đo DB update.
- [ ] Positive cache TTL không vượt token expiry và không tăng indefinite qua cache hits.
- [ ] Negative cache có TTL/size/rate bound, chống random-token cache pollution.
- [ ] Cache key tách issuer/resource/trust domain, không reuse active metadata sai audience.
- [ ] Push revocation events được authenticated/audited, có chiến lược khi event mất/chậm.
- [ ] Khi introspection timeout/401/5xx, không fail open; xác định 401/503/error handling theo contract.
- [ ] Token store/AS introspection có HA, timeout, circuit breaker, bulkheads và capacity planning.
- [ ] Có DR test để revoked tokens không hồi sinh do stale replica/restore.
- [ ] Introspection credentials được quản lý như secrets; không nhúng vào public SPA/mobile.
- [ ] Browser/BFF giữ tokens server-side khi phù hợp; cookie/session/CSRF/XSS protections vẫn áp dụng.
- [ ] Opaque/JWE/JWS Bearer đều có replay risk nếu token string bị đánh cắp.
- [ ] Sender-bound DPoP/mTLS nếu được yêu cầu phải kiểm proof/certificate và token confirmation binding.
- [ ] JWE dùng trusted recipient encryption keys, thuật toán `alg`/`enc` được allowlist.
- [ ] Key management/rotation/decryption/backup của JWE được đánh giá cùng issuer validation.
- [ ] Với nested JWE/JWS, xác minh cả lớp cần thiết, token purpose và OAuth claims.
- [ ] Không dùng một shared JWE decryption key rộng khắp khi privacy/trust boundary không cho phép.
- [ ] Không dùng JWT signing-key rotation như cách revoke một opaque token/grant riêng.
- [ ] Không log raw access/refresh tokens, Authorization headers, private keys hoặc decryption plaintext.
- [ ] Metrics có bounded labels, không dùng token hash/`jti`/attacker `kid` hoặc user PII.
- [ ] Có negative tests wrong issuer/audience/scope, missing claims, revoked/expired token, 401/403/5xx và BOLA.
- [ ] Có failure tests AS outage, positive cache expiry, replication lag, rate-limit và recovery.
- [ ] Có tests JWE decrypt/tag/alg/key rotation, issuer signature và bearer replay.
- [ ] Có kế hoạch bảo mật/availability/latency và documented decision matrix để review lại sau thay đổi quy mô.
- [ ] Khi thiếu chứng cứ token hợp lệ, RS **fail closed** thay vì suy đoán user có quyền.

**Ghi nhớ:** **Opaque token đơn giản hơn encrypted token khi yêu cầu chủ yếu là không để token string lộ claims và muốn AS tập trung kiểm trạng thái/revoke**, nhất là trong trust domain nội bộ có introspection sẵn và độ trễ mạng chấp nhận được. Nó tránh việc phân phối private JWE decryption keys cho nhiều RS, nhưng phải vận hành **token store, authenticated introspection, bounded caches, HA và revocation SLA**. **JWE** phù hợp khi thật sự cần token payload confidentiality đối với recipients được chỉ định, đặc biệt offline hoặc profile bắt buộc; và **JWS tối giản** vẫn là lựa chọn tốt khi không cần mã hóa hay online lookup. Dù chọn gì, **authorization, audience, scope, token purpose, token storage, replay resistance và revocation** không tự biến mất.

## 26. Tài liệu chuẩn và tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client, AS, RS, access/refresh token roles, grants và scopes.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer replay/credential protection, HTTP authorization và error challenges.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, request/response metadata, authenticated introspection caller và inactive token privacy.
- **RFC 7009 — OAuth 2.0 Token Revocation:** authorized client revocation request, token/grant semantics và HTTP response behavior.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** lựa chọn resource/audience phù hợp khi cấp token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** OAuth security, access/refresh token hardening, PKCE, audience và replay.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `at+jwt` token type, standard access token claims và RS validation.
- **RFC 7515 — JSON Web Signature (JWS):** signing input/alg/key, integrity và signature verification.
- **RFC 7516 — JSON Web Encryption (JWE):** key management, `enc`, ciphertext/tag, compact và JSON serializations.
- **RFC 7517 — JSON Web Key (JWK):** key types, public/private parameters, JWKS, `kid`/`use`/`key_ops`.
- **RFC 7518 — JSON Web Algorithms (JWA):** `RSA-OAEP`, `ECDH-ES`, `A256GCM`, JWS signature algorithms và key semantics.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `nbf`, `iat` và token representation.
- **RFC 8725 — JWT Best Current Practices:** algorithm confusion, issuer/audience validation, cross-JWT/token substitution và nested JWT.
- **RFC 8693 — OAuth 2.0 Token Exchange:** đổi token cho resource/actor delegation theo trust policy.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS confirmation/binding của access token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWT, `ath`, `htu`, `htm`, `jti` và sender binding.
- **OpenID Connect Core 1.0 / Discovery 1.0:** ID token/optional encryption, issuer/client metadata và validation profiles.
- **NIST SP 800-57 — Recommendation for Key Management:** decryption/signing key lifecycle, storage, rotation và compromise.
- **NIST SP 800-38D — GCM and GMAC:** AEAD nonce/tag handling nếu dùng JWE AES-GCM.
- **OWASP OAuth 2.0 Cheat Sheet:** authorization/token endpoint, bearer safety, audience/PKCE và token lifecycle.
- **OWASP JSON Web Token Cheat Sheet:** signed/encrypted JWT validation, storage, token theft và revocation.
- **OWASP Cryptographic Storage Cheat Sheet / Key Management Cheat Sheet:** encryption-at-rest, key custody và rotation.
- **OWASP API Security Top 10 — Broken Object Level Authorization:** object/tenant authorization dù token active.
- **Spring Security Reference — OAuth2 Resource Server Opaque Tokens:** introspection configuration, `OpaqueTokenIntrospector`, authorities và error handling.
- **Spring Security Reference — OAuth2 Resource Server JWT:** `NimbusJwtDecoder`, issuer/JWKS validation và signed access tokens.
- **Spring Authorization Server Reference:** OAuth2 access/refresh token issuance, token stores, introspection/revocation và OAuth/OIDC configuration.




