# Khi token cần confidentiality

## Mục tiêu học tập

Trong chương **Token encryption** của học phần **Token Security Fundamentals**, **confidentiality** (tính bí mật) là thuộc tính bảo vệ **nội dung token không bị các bên không được phép đọc được**. Một JWT được ký đúng và được Resource Server chấp nhận không đồng nghĩa nội dung JWT đang được giấu kín. Người cầm một **JWS Compact** thông thường có thể giải mã Base64URL của payload và đọc các claim như `sub`, `email`, `scope`, `aud`, `tenant_id` mà không cần biết khóa ký.

Ngược lại, mã hóa token cũng **không tự tạo quyền truy cập**: người có bản sao của encrypted bearer access token vẫn có thể gửi **nguyên chuỗi ciphertext** đến Resource Server và được phục vụ nếu token còn hiệu lực và không bị ràng buộc người gửi. Vấn đề bảo vệ bí mật nội dung phải được giải quyết **cùng với** chữ ký/toàn vẹn, issuer, audience, scope, hạn token, lưu trữ, thu hồi và chống replay.

Sau bài này, bạn có thể:

1. Nhận biết **khi nào yêu cầu bảo mật dữ liệu trong claims** thực sự đòi hỏi JWE, khi nào đủ dùng **JWT ký kết hợp TLS**, **opaque token** hoặc **giảm lượng claims**.
2. Phân biệt **Base64URL encoding, JWS signing, JWE authenticated encryption, HTTPS/TLS, mã hóa tại nơi lưu trữ** và **tokenization**.
3. Phân tích **ai có thể nhìn thấy token**, ai có thể giải mã nó và dữ liệu nào vẫn lộ qua metadata hoặc bản ghi log.
4. Giải thích các thành phần **JWE Compact**, `alg` quản lý khóa, `enc` mã hóa nội dung, `kid` chọn khóa recipient, IV, ciphertext, authentication tag.
5. Thiết kế **nested JWT (sign then encrypt)** theo profile phù hợp và kiểm tra cả **JWE decryption/tag, JWS signature, token type, issuer, audience, expiry, scope**.
6. Quản lý khóa giải mã/recipient với JWKS, KMS/HSM, vòng đời khóa, rotation và trường hợp khóa bị lộ.
7. Chọn mô hình cho **OIDC encrypted ID token**, OAuth access token JWT/JWE/opaque, BFF và multi-resource/multi-tenant.
8. Phòng chống **decryption oracle, algorithm downgrade, `zip` compression side channel, SSRF/key substitution, log leakage, ciphertext replay**.
9. Xây dựng ví dụ HTTP, JSON, Java/Nimbus JOSE và cách tích hợp Spring Security theo đúng phạm vi khả năng, cùng ma trận kiểm thử.

## 1. Confidentiality bảo vệ điều gì?

Trong bảo mật token, cần phân biệt **ba thuộc tính**:

| Thuộc tính | Câu hỏi | Cơ chế thường dùng | Cơ chế không tự đáp ứng |
|---|---|---|---|
| **Confidentiality** (bí mật) | Ai có thể đọc payload/claims? | JWE, opaque token + introspection, encryption tại nơi lưu trữ, TLS trên đường truyền. | JWS ký thuần, Base64URL. |
| **Integrity / authenticity** (toàn vẹn/xác thực nguồn) | Token có bị sửa? Có do issuer đúng phát không? | JWS signature/MAC, authenticated encryption trong ngữ cảnh có ràng buộc trusted key/issuer, TLS cho kênh. | Chỉ encode Base64URL, claim tự khai. |
| **Authorization** (phân quyền) | Principal/Client được làm gì trên resource nào? | Validate issuer/audience/type/scope, sender binding, quyền owner/tenant/object. | Chỉ verify JWS hoặc decrypt JWE. |

Ví dụ: một JWT access token dành cho `orders-api` có claim `scope=orders:read` và `sub=user-123`. Nếu Client gửi nó tới API qua HTTPS thì **người nghe lén mạng thông thường** không đọc token trên đường TLS, nhưng Client, proxy chấm dứt TLS, ứng dụng và bất kỳ ai giữ **bản sao token** vẫn có thể **decode** JWS payload.

### Ba mục tiêu dễ bị gộp nhầm

~~~text
Mục tiêu A: Không cho người nghe lén mạng đọc token
  -> HTTPS/TLS và xác minh endpoint certificate.

Mục tiêu B: Không cho thành phần đang giữ chuỗi token
           đọc email/PII/claims bên trong
  -> Mã hóa payload JWE cho recipient được chỉ định,
     hoặc dùng opaque token + tra cứu metadata trong backend.

Mục tiêu C: Không cho attacker dùng bản sao token như quyền truy cập
  -> Giữ token bí mật, scope/audience/TTL, sender-constrained token,
     revocation/RS policy và chống phát lại theo profile.
~~~

**Mục tiêu B và C không đồng nhất.** JWE che payload với người không có khóa, nhưng một encrypted **bearer token** vẫn là credential có thể bị phát lại nguyên văn.

## 2. JWT ký không phải JWT được mã hóa

### JWS Compact Serialization

JWS Compact thường có **ba thành phần**:

~~~text
BASE64URL(protected_header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Header minh họa:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "as-signing-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "exp": 1893456600
}
~~~

**Chữ ký bảo vệ payload khỏi bị sửa mà không bị phát hiện**, nếu verifier xác minh đúng thuật toán, khóa issuer và claims. Nó **không mã hóa** `sub`, `tenant_id` hay `scope`. Dữ liệu Base64URL chỉ là cách biểu diễn byte bằng ký tự URL-safe.

### JWE Compact Serialization

JWE Compact thông thường có **năm thành phần**:

~~~text
BASE64URL(protected_header)
.
BASE64URL(encrypted_key)
.
BASE64URL(initialization_vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
~~~

JWE cho phép người có **recipient decryption key** phù hợp giải mã nội dung, đồng thời kiểm tra authentication tag để phát hiện sửa đổi. JWE protected header vẫn có thể quan sát được dưới dạng Base64URL và phải được xem như input chưa tin cho tới khi các bước xác thực mã hóa hoàn tất.

### So sánh bằng hình dung

~~~mermaid
flowchart LR
    A["Claims gốc"] --> B["JWS: ký"]
    B --> C["Có thể đọc payload; không tự sửa được nếu verify đúng"]
    A --> D["JWE: mã hóa có xác thực"]
    D --> E["Bên không có decryption key không đọc được payload"]
    C --> F["Access control luôn cần validate claims/permissions"]
    E --> F
~~~

**Không lấy số dấu chấm làm cơ chế bảo mật duy nhất**: thư viện phải parse đúng JWS/JWE profile, từ chối định dạng khác với token contract, xử lý detached/nested/multi-recipient formats khi và chỉ khi profile cho phép.

## 3. Khi nào token thực sự cần confidentiality?

Không có quy tắc “mọi token phải mã hóa” hoặc “token đã ký không bao giờ cần mã hóa”. Xem **nội dung**, **những bên sẽ cầm token**, **vòng đời lưu trữ** và **nghĩa vụ riêng tư**.

| Bối cảnh | Nguy cơ nếu JWT chỉ ký | Hướng thiết kế |
|---|---|---|
| **JWT chứa email, thông tin tài khoản, định danh nhạy cảm** | Client/intermediary có thể đọc claim dù không có signing key. | **Giảm claims trước**; nếu vẫn phải giấu khỏi bên cầm chuỗi, dùng JWE/opaque và phân quyền recipient. |
| **Access token đi qua nhiều tầng proxy/gateway** | Bên xử lý token có thể decode identity, role, tenant. | Chỉ đưa claims tối thiểu, tách trust domain, cân nhắc opaque hoặc JWE end-to-end đến đúng RS. |
| **OIDC Client cần nhận ID token được mã hóa** | ID token chứa claims định danh đọc được với Client/điểm quan sát chuỗi. | Cấu hình **encrypted ID token** theo Client registration/OP hỗ trợ; ký rồi mã hóa theo profile. |
| **Multi-tenant RS dùng claims phân vùng nội bộ** | Claim cấu trúc tổ chức, tenant hoặc data classification bị lộ. | Tối thiểu hóa claims; nếu dữ liệu bí mật cần tới RS, mã hóa cho đúng RS và enforce authorization. |
| **Token có thể bị lưu ở telemetry/traces** | Payload JWS có thể bị giải mã về sau từ bản log bị lộ. | **Không log token** là kiểm soát trước tiên; JWE không miễn log redaction. |
| **Backend BFF giữ token và browser chỉ có opaque session cookie** | Browser không cần biết token/claims. | BFF giữ token phía server, cookie `HttpOnly`; JWE có thể không cần trong trust domain này. |
| **Token chỉ mang ID ngẫu nhiên, tra cứu server-side** | Chuỗi không tự lộ claims nội bộ. | Opaque token + secure storage/introspection; vẫn phải bảo vệ vì bearer token có giá trị truy cập. |
| **Chỉ cần chống chỉnh sửa claims** | Không có yêu cầu giấu payload giữa các bên đang giữ token. | JWS signature, trusted issuer/audience/type, TLS và giảm claims. |

### Câu hỏi quyết định quan trọng nhất

> Có bên nào **buộc phải giữ/chuyển tiếp chuỗi token nhưng không được phép biết một hoặc nhiều claims bên trong** không?

Nếu có, hãy xét **JWE cho recipient được chỉ định** hoặc **opaque/reference token**. Nếu không, một **JWS với claims tối thiểu**, TTL hợp lý và TLS có thể đủ cho yêu cầu confidentiality còn lại của hệ thống. Đây là quyết định theo threat model chứ không phải mặc định của chuẩn OAuth 2.0.

## 4. Threat modeling: ai nhìn thấy chuỗi token?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as OAuth Client / BFF
    participant AS as Authorization Server
    participant G as API Gateway
    participant RS as Resource Server
    AS-->>C: Trả access token (JWS, JWE hoặc opaque)
    C->>G: HTTPS Authorization: Bearer token
    G->>RS: Forward token qua kênh được bảo vệ
    RS->>RS: Xác thực token, kiểm tra aud/scope và dữ liệu
    RS-->>C: Response đã được phép
    C-->>B: Dữ liệu tối thiểu cần hiển thị
    Note over C,RS: Ai có token JWS có thể decode claims; JWE giới hạn người đọc payload theo recipient key
~~~

Một token có thể xuất hiện tại:

- **AS**: nơi tạo claims, ký/mã hóa và lưu refresh/grant state.
- **Client**: nơi nhận, lưu, chuyển access token; nếu là SPA direct token, JavaScript có thể nhìn thấy token.
- **BFF/gateway/proxy**: điểm kết thúc TLS, auth interceptors, tracing, HTTP access logs.
- **RS**: bên thực sự kiểm tra token và quyết định quyền truy cập API.
- **Browser extension, malware, XSS, crash dump, backup, debug tooling**: các kênh rò rỉ ngoài thiết kế.

Mã hóa nội dung cho RS **không làm biến mất bản sao token** tại Client/gateway. Những bên đó có thể không đọc claims, nhưng vẫn có thể **gửi lại** chuỗi bearer token hoặc làm lộ nó.

### Phân loại dữ liệu trước khi nhét vào token

| Dữ liệu | Có nên nhét vào access token? | Lưu ý |
|---|---|---|
| `iss`, `aud`, `exp`, `iat`, `client_id` | Thường cần theo token profile. | Không nên coi các trường này là dữ liệu hoàn toàn bí mật; cần validate. |
| `scope`, authority tối thiểu | Khi RS cần ra quyết định. | Không đưa toàn bộ ACL hay tất cả chức danh ngoài nhu cầu. |
| `sub` dạng định danh opaque/pairwise | Có thể cần. | Hạn chế dùng email/số giấy tờ làm subject công khai. |
| Email, số điện thoại, địa chỉ | Thường **không cần** trong access token API. | Dùng UserInfo/backend query với authorization hoặc profile riêng. |
| Số thẻ, medical records, mật khẩu, client secret | **Không đưa vào token** như giải pháp mặc định. | Mã hóa cũng không biến token thành nơi lưu secrets thích hợp. |
| Tenant/organization metadata | Chỉ claim cần thiết. | Nếu nhạy cảm, đánh giá minimization, opaque/JWE; RS vẫn kiểm tra quyền tenant. |
| Full object permissions | Tránh nếu thay đổi thường xuyên hoặc kích thước lớn. | Trạng thái quyền có thể cũ trước `exp`; RS cần object-level checks. |

**Nguyên tắc đầu tiên là data minimization, không phải mã hóa mọi thứ rồi đưa thêm dữ liệu vào token.**

## 5. TLS, encryption at rest và JWE bảo vệ các ranh giới khác nhau

| Lớp bảo vệ | Điều nó che giấu | Điều nó không tự che giấu |
|---|---|---|
| **TLS từ Client tới gateway/RS** | Nội dung HTTP khi đi qua đoạn kết nối TLS. | Gateway kết thúc TLS nhìn thấy request và bearer token. |
| **mTLS** | Bảo vệ kênh và xác thực client certificate theo cấu hình. | Không tự mã hóa nội dung JWT cho bên cầm token; không tự enforce certificate-bound access token. |
| **Database/disk encryption** | Dữ liệu lưu ở thiết bị/tầng storage khi không có key. | Ứng dụng/query/log được cấp quyền đọc dữ liệu đã giải mã. |
| **JWE encrypted token** | Payload JWE với bên **không có recipient decryption key**. | Header metadata, token length, traffic patterns; không chống phát lại bearer. |
| **Opaque token + introspection** | Claims không hiển thị từ chuỗi token ngẫu nhiên. | Người cầm chuỗi có thể trình token nếu cơ chế bearer cho phép. |
| **JWS signed token** | Không che giấu payload; bảo đảm tính toàn vẹn/xác thực nguồn khi verify đúng. | PII trong payload đọc được ngay. |

### Ví dụ TLS termination

~~~text
Browser --HTTPS--> Gateway --HTTPS--> Orders API

JWT JWS:
  Gateway có thể decode claims trong access token.

JWT JWE (recipient Orders API):
  Gateway chỉ thấy JWE header/ciphertext nếu không có key.
  Orders API có private key để decrypt.

Nhưng Gateway vẫn có thể:
  forward ciphertext token;
  ghi nguyên token vào log nếu config sai;
  replay bearer token trong ngữ cảnh token hợp lệ.
~~~

**Chọn JWE không cho phép tắt TLS**. OAuth bearer token, client authentication và revocation/introspection vẫn yêu cầu HTTPS/TLS theo profile và bảo vệ đường truyền.

## 6. JWE hoạt động như thế nào?

JWE dùng cơ chế **key management** để có Content Encryption Key (CEK), sau đó dùng **content encryption có xác thực** (AEAD hoặc cơ chế authenticated encryption do JOSE hỗ trợ) bảo vệ plaintext. Với **JWE Compact Serialization**, năm thành phần được ngăn bằng dấu chấm.

~~~mermaid
flowchart TD
    P["Plaintext JWT hoặc dữ liệu cần mã hóa"] --> E["Authenticated content encryption (enc)"]
    K["CEK theo key-management algorithm (alg)"] --> E
    H["Protected header alg / enc / kid"] --> A["Additional Authenticated Data"]
    A --> E
    E --> C["Ciphertext + authentication tag + IV"]
    K --> EK["Encrypted key hoặc key-agreement output"]
    C --> J["JWE Compact (5 phần)"]
    EK --> J
    H --> J
    J --> D["Recipient decrypt + verify tag theo trusted key/policy"]
~~~

### Protected header minh họa

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-decrypt-2026-11",
  "cty": "JWT"
}
~~~

| Header | Vai trò | Lưu ý |
|---|---|---|
| **`alg`** | Thuật toán key management/CEK protection, ví dụ `RSA-OAEP-256`. | **Khác** `alg=RS256` dùng ký JWS. |
| **`enc`** | Thuật toán content encryption, ví dụ `A256GCM`. | Phải được allowlist đúng profile, không chọn tùy header. |
| **`kid`** | Gợi ý chọn recipient decryption key trong key store thích hợp. | Không phải bằng chứng key thuộc issuer tin cậy. |
| **`cty`** | Content type, ví dụ `JWT` cho nested JWT theo profile. | Không thay kiểm tra inner JWS/type/claims. |
| **`zip`** | Tùy chọn nén plaintext trước mã hóa khi hỗ trợ. | Cần đánh giá compression side-channel; mặc định không bật. |

### Về `encrypted_key`

Với `RSA-OAEP-256`, CEK có thể được mã hóa bằng public key recipient; private key recipient dùng giải mã CEK. Nhưng **không phải mọi JWE `alg` tạo encrypted_key nonempty**: chẳng hạn `dir` hoặc một số dạng key agreement trực tiếp có thể để phần đó rỗng theo chuẩn. Không dùng số byte của phần này để quyết định token có hợp lệ; thư viện JOSE phải parse đúng thuật toán/profile.

### GCM authentication tag có ý nghĩa gì?

AES-GCM bảo vệ tính bí mật và phát hiện sửa đổi ciphertext/AAD dưới **CEK** đúng, nếu nonce/key usage và các giả định được tuân thủ. Header protected được đưa vào **authenticated data** trong JWE Compact; vì thế attacker không thể đổi `alg`, `enc`, `kid` mà vẫn giữ tag hợp lệ một cách tùy ý.

Tuy vậy, **trước khi tag được verify**, không tin các giá trị header; chúng chỉ được dùng để chọn **trong allowlist/recipient keys đã đăng ký**.

## 7. Các lựa chọn JWE `alg` và `enc`

### `alg`: quản lý khóa

| Thuật toán JOSE | Ý nghĩa khái quát | Lưu ý triển khai |
|---|---|---|
| **`RSA-OAEP-256`** | Mã hóa/bao bọc CEK cho recipient có RSA public key. | Chọn key size/security policy thích hợp; recipient giữ private key. |
| **`ECDH-ES`** | Thỏa thuận khóa elliptic-curve trực tiếp theo profile. | Phải kiểm tra curve, ephemeral public key, key derivation. |
| **`ECDH-ES+A256KW`** | ECDH-ES sinh key-encryption key để wrap CEK. | Format/curve/KDF/recipient support phải phù hợp. |
| **`dir`** | CEK được dùng trực tiếp từ khóa đối xứng đã chia sẻ theo cơ chế. | Không công bố shared secret; phân phối/rotate khó trong môi trường nhiều bên. |
| **`A256KW`** | AES Key Wrap bảo vệ CEK. | Cần key-encryption key bí mật và quản lý vòng đời riêng. |

`RSA1_5` (RSAES-PKCS1-v1_5) xuất hiện trong registry lịch sử nhưng mang rủi ro **padding-oracle/decryption-oracle** nếu triển khai yếu. Đối với thiết kế mới, ưu tiên thuật toán key management hiện đại được profile/policy chấp thuận, không bật `RSA1_5` để tăng “tương thích” vô điều kiện.

### `enc`: mã hóa nội dung có xác thực

| Thuật toán JOSE | Vai trò | Cẩn trọng |
|---|---|---|
| **`A128GCM`** | AES-GCM 128-bit CEK. | Quản lý nonce/IV an toàn; tag phải được verify. |
| **`A256GCM`** | AES-GCM 256-bit CEK. | CSPRNG/non-reuse nonce theo scheme; key management an toàn. |
| **`A128CBC-HS256`** | AES-CBC kết hợp HMAC theo đặc tả JWE, không phải CBC đơn thuần. | Không tự lắp CBC/HMAC hoặc bỏ MAC; chỉ dùng nếu profile/implementation phù hợp. |
| **`A256CBC-HS512`** | AES-CBC kết hợp HMAC theo JWA profile. | Cẩn trọng side channels và thông điệp lỗi; cân nhắc AEAD như GCM khi phù hợp. |

### Tránh tự tạo “JWT encryption algorithm”

Không nên:

~~~text
base64(plaintext + shared_secret)
AES-ECB(secret, jwt)
encrypt(jwt) rồi bỏ authentication tag
AES-CBC với fixed IV và không xác thực ciphertext
JWS signature bị coi là "encryption"
~~~

**Dùng thư viện JOSE đã được kiểm thử**, cấu hình rõ `alg`/`enc` và key type/length. Không viết lại crypto primitives hoặc dựng ciphertext format tùy hứng.

## 8. JWE che nội dung, không che mọi metadata

JWE Compact protected header thường **không được mã hóa**. Người nhìn thấy chuỗi JWE vẫn có thể suy:

- Token là JWE, có bao nhiêu phân đoạn; `alg`, `enc`, `kid` nếu đặt trong protected header.
- Kích thước tương đối của ciphertext, từ đó có thể suy **độ dài plaintext** gần đúng.
- Thời điểm token được phát/gửi, tần suất request và endpoint sử dụng.
- Nơi xuất hiện token trong log/telemetry nếu ứng dụng cấu hình sai.
- Một số metadata protocol ở HTTP/TLS hoặc gateway đã được cấp quyền quan sát.

### Tránh PII trong header

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "user-123@example.test"
}
~~~

Đây là **anti-pattern**: dù payload được mã hóa, `kid` đã làm lộ email. Chọn identifier khóa **opaque**, không chứa user/account/tenant secrets không cần thiết. Nếu có thông tin multi-tenant nhạy cảm, đừng tự nhét vào unencrypted JOSE header rồi tin rằng JWE đã giấu toàn bộ.

### Compression side channel

Nếu nén plaintext có **attacker-controlled data** gần secrets trước khi mã hóa, độ dài ciphertext có thể tiết lộ tương quan về secrets trong một số threat models. Vì vậy:

- Không bật `zip` chỉ để giảm token size khi chưa đánh giá rò rỉ độ dài.
- Tránh trộn bí mật và input attacker trong cùng compression context.
- Nếu cần tối ưu kích thước, **giảm claims/đổi opaque token** thường rõ ràng hơn.
- Giới hạn kích thước message sau giải nén để chống decompression bombs nếu profile cho nén.

## 9. Khi nào chọn opaque token thay JWE?

**Opaque access token** thường chỉ là một chuỗi ngẫu nhiên không mang claims đọc được. RS có thể hỏi AS qua **RFC 7662 Token Introspection** hoặc tra trạng thái đáng tin theo hợp đồng.

~~~text
Client giữ:
  access_token = "opaque_random_value"

Resource Server:
  POST /introspect token=<OPAQUE_ACCESS_TOKEN>
  AS (sau RS authentication/authorization) trả active, aud, scope, sub...
~~~

### Ví dụ introspection response

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456600
}
~~~

**Bên Client chỉ thấy chuỗi opaque, không phải claims.** Tuy nhiên một RS có quyền gọi introspection vẫn có thể xem metadata được AS trả; phải cấp quyền RS phù hợp và tránh trả thông tin ngoài nhu cầu.

### So sánh lựa chọn

| Tiêu chí | JWS access token | JWE/nested JWT access token | Opaque access token |
|---|---|---|---|
| Claims trong chuỗi đọc được bởi người có token? | **Có** với JWS payload thông thường. | **Không**, nếu mã hóa đúng và không có key. | **Không có claims đọc trực tiếp** từ chuỗi ngẫu nhiên. |
| RS tự verify offline? | Thường có với public JWKS. | Có thể nếu RS có decryption key và các verification keys cần thiết. | Thường cần introspection/lookup. |
| Độ phức tạp khóa | Signing key/JWKS. | Signing và encryption/recipient keys, thêm key lifecycle. | Token state/introspection server và quyền hỏi. |
| Thu hồi nhanh | Cần denylist/state hoặc TTL ngắn nếu offline. | **Tương tự** nếu RS tự decrypt/verify offline. | Có thể qua introspection/state, tùy cache latency. |
| Token size | Thường ngắn hơn JWE tương đương. | Thường dài hơn do encrypted key, IV, tag và nested token. | Thường ngắn, độ dài tùy thiết kế. |
| Đối tượng cầm token có thể replay? | Có nếu bearer và chưa bị chặn. | **Có**, ciphertext vẫn là bearer credential. | **Có**, chuỗi opaque vẫn là bearer credential. |

**Nếu mục tiêu duy nhất là không tiết lộ claims cho Client**, opaque token có thể đơn giản hơn JWE khi RS/AS đã hỗ trợ introspection và tradeoff network/availability chấp nhận được.

## 10. Đừng để JWT trở thành kho chứa PII

Ngay cả JWE cũng không nên thành nơi lưu hồ sơ người dùng đầy đủ:

~~~text
Access token chỉ cần:
  iss, aud, sub, exp, scope tối thiểu
  (và claims khác theo access-token profile)

Không cần:
  danh sách 2000 đơn hàng
  địa chỉ thanh toán đầy đủ
  số định danh cá nhân
  toàn bộ chính sách RBAC/ACL của tổ chức
  refresh token hoặc client secret lồng vào claims
~~~

### Rủi ro của claims chứa dữ liệu động

Claims được chụp tại thời điểm phát hành. Dù được mã hóa, một role/permission hoặc tenancy claim có thể **lỗi thời** trước thời điểm `exp` khi user bị đổi quyền. Resource Server phải kiểm tra chính sách cấp quyền phù hợp, đặc biệt với nghiệp vụ nhạy cảm.

### Mẫu thiết kế

~~~text
Access token:
  subject opaque
  audience một API
  scope tối thiểu
  thời hạn ngắn
  optional grant/version identifier

Resource Server:
  verify token
  kiểm tra owner/tenant/object trong backend
  chỉ truy vấn PII cần thiết sau khi authorization cho phép
~~~

Đây là chiến lược **data minimization + least privilege**, thường đem lại lợi ích cả khi **không dùng JWE**.

## 11. Nested JWT: ký trước, mã hóa sau

Nếu một bên cần **cả** xác minh token do issuer đáng tin phát hành **và** giấu nội dung khỏi người không phải recipient, kiến trúc phổ biến là:

1. AS/OP tạo claims đúng profile.
2. AS/OP tạo **JWS** bằng **private signing key của issuer**.
3. AS/OP lấy **public encryption key của recipient đã đăng ký**.
4. AS/OP tạo **JWE** chứa toàn bộ JWS dưới dạng plaintext cần mã hóa.
5. Recipient dùng private decryption key, kiểm tra JWE tag và nhận lại **inner JWS**.
6. Recipient **verify JWS signature** bằng public signing key của issuer đáng tin.
7. Recipient **validate token profile, issuer, audience, thời gian, nonce/scope** và các quy tắc cần thiết.

### Sơ đồ

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server / OP
    participant Enc as JWE Encrypter
    participant C as Recipient Client / RS
    AS->>AS: Build minimal validated claims
    AS->>AS: Sign JWS with AS private signing key
    AS->>Enc: Inner compact JWS
    Enc->>Enc: Fetch recipient public encryption key from trusted registration
    Enc-->>C: Outer compact JWE, cty=JWT
    C->>C: Select trusted recipient private decryption key
    C->>C: Decrypt + verify JWE authentication tag
    C->>C: Verify inner JWS with trusted AS public signing key
    C->>C: Validate iss/aud/type/exp/nonce/scope as appropriate
    C-->>AS: Processing outcome (logical)
~~~

### Hai khóa không được nhầm

| Lớp | Private key thuộc ai? | Public key dùng ở đâu? | `kid` ở đâu? |
|---|---|---|---|
| **Inner JWS ký** | Issuer/AS/OP. | Recipient verifier lấy từ trusted **issuer JWKS**. | Inner JWS header chọn **signing key AS**. |
| **Outer JWE mã hóa** | Recipient giữ **private decryption key**. | Issuer lấy từ **recipient/client key registration**. | Outer JWE header chọn **recipient encryption key**. |

**Lý do phải verify inner signature:** nếu public encryption key của recipient được công bố, **bất kỳ ai có public key cũng có thể tạo một JWE hợp lệ về mặt mã hóa** cho recipient. Decrypt và tag-verify thành công **không tự chứng minh rằng AS đã phát token đó**. JWS bên trong phải cung cấp xác thực issuer theo hợp đồng.

### Header và cấu trúc

Inner JWS header:

~~~json
{
  "alg": "PS256",
  "kid": "as-signing-key-v5",
  "typ": "at+jwt"
}
~~~

Outer JWE protected header:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-api-encryption-v2",
  "cty": "JWT"
}
~~~

`cty=JWT` biểu thị nội dung nested JWT theo cách dùng JOSE, nhưng **không có quyền thay thế kiểm tra định dạng và chữ ký thực tế**. Nếu profile yêu cầu signed + encrypted, một JWE plaintext chỉ chứa unsigned claims phải bị từ chối.

### Thứ tự và profile

JWS và JWE cho phép các bố cục khác nhau tùy giao thức. **Ký rồi mã hóa** là mô hình thường được dùng và là cách OIDC mô tả encrypted ID token. Không tự giả định mọi ứng dụng/JWT phải nested theo thứ tự này; cần theo **profile/registration thực tế**, xác minh đúng mọi lớp.

## 12. OIDC encrypted ID token

OpenID Connect có thể hỗ trợ **ID token được mã hóa** khi Relying Party đăng ký các thuật toán phù hợp. Điều này hữu ích khi ID token chứa thông tin user không nên bị các thành phần trung gian đọc được.

### Registration metadata minh họa

~~~json
{
  "client_id": "shop-web",
  "id_token_signed_response_alg": "PS256",
  "id_token_encrypted_response_alg": "RSA-OAEP-256",
  "id_token_encrypted_response_enc": "A256GCM",
  "jwks_uri": "https://shop.example.test/.well-known/jwks.json"
}
~~~

Đây là **Client registration metadata minh họa**, không phải phản hồi của provider cụ thể. Các tên thuộc tính/giá trị phải theo OIDC Dynamic Client Registration và profile của OP đang sử dụng. OP không được lấy `jwks_uri` recipient từ **callback query hoặc JWT header tùy ý** khi gửi token nhạy cảm.

### Vai trò các khóa

~~~text
OP ký ID token:
  OP private signing key
  kid=op-signing-2026-11

OP mã hóa signed ID token:
  Recipient public encryption key từ registration của shop-web
  kid=shop-idtoken-decrypt-v2

shop-web nhận JWE:
  Decrypt bằng private key của shop-web (v2)
  Verify inner signed JWT bằng OP trusted signing keys
  Validate iss, aud=shop-web, exp, iat, nonce/azp khi áp dụng
~~~

### Không dùng ID token thay access token

ID token **xác nhận sự kiện authentication cho RP**; không phải bearer access credential dành cho API. Dù đã mã hóa và signed đúng, Resource Server Orders vẫn phải **từ chối** ID token có `aud=shop-web` khi API yêu cầu access token `aud=orders-api` và profile phù hợp.

### Tác động đến Client

- RP phải có private decryption key được bảo vệ, đủ thuật toán và key size.
- OP phải biết public encryption key **đúng Client** trước khi phát JWE.
- Khi Client xoay decryption key, cần pre-register key mới và điều phối key overlap/TTL để không làm mất khả năng giải mã.
- Ứng dụng phải **xóa plaintext ID token khỏi log/telemetry**, kể cả log sau decrypt.
- Chỉ mã hóa ID token không tự thu hồi OP SSO session, refresh token hay các OAuth grants.

## 13. OAuth access token được mã hóa

OAuth 2.0 **không bắt buộc access token là JWT hay JWE**. Với một access token được thiết kế là encrypted JWT cho Resource Server cụ thể, AS và RS phải có **hợp đồng rõ**:

~~~text
AS:
  phát signed access JWT với iss/aud/scope/exp/type đúng profile;
  bọc thành JWE cho public key của orders-api;
  đưa outer JWE ciphertext cho Client.

Client:
  lưu và chuyển tiếp token;
  không được giải mã nếu không có recipient private key;
  vẫn phải bảo vệ chuỗi token vì nó là bearer credential.

Orders API:
  nhận JWE;
  dùng private decryption key để decrypt;
  verify inner JWS issuer/signature;
  validate aud=orders-api, type, exp, scope;
  authorize owner/tenant/object và trạng thái revocation nếu cần.
~~~

### Lưu ý về JWT access-token profile

Nếu hệ thống dùng **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, hãy giữ các quy tắc của profile cho **signed JWT access token** khi xây dựng lớp inner JWT. Việc đặt nó vào JWE cần được xác định bởi **hợp đồng token format/nesting** mà các bên liên quan hỗ trợ; không được xem mã hóa là ngoại lệ cho phép bỏ validate `typ`, `iss` hoặc `aud`.

### Một token cho nhiều Resource Server?

Nếu token phải phục vụ nhiều RS nhưng được mã hóa cho **một** recipient:

- Chỉ RS có private key tương ứng giải mã được.
- RS thứ hai không thể decrypt chỉ vì có cùng `scope` hoặc `iss`.
- Chia sẻ **private decryption key cho tất cả RS** có thể làm mất ý nghĩa giới hạn recipient.
- Cân nhắc **token riêng cho mỗi resource/audience**, hoặc kiến trúc opaque + introspection/token exchange theo nhu cầu.
- JWE JSON Serialization có thể hỗ trợ nhiều recipient nhưng **giao thức/API phải hỗ trợ đúng serialization**; không mặc định OAuth bearer endpoint hay Spring decoder hiểu định dạng đó.

**Tách token theo audience/resource** thường tạo ranh giới rõ hơn việc “một JWE cho mọi API” và giảm blast radius khi một RS bị xâm nhập.

## 14. BFF: có nhất thiết phải dùng JWE không?

Trong kiến trúc **Backend for Frontend**, browser thường chỉ có **opaque session cookie HttpOnly** còn access/refresh token được lưu tại BFF:

~~~text
Browser:
  __Host-shop_session=<RANDOM_SESSION_ID>

BFF:
  access token cho orders-api
  refresh token của user/client
  client credentials bảo vệ ở backend

AS / Orders API:
  dùng OAuth token đúng profile
~~~

Nếu BFF và Orders API cùng miền tin cậy, claims trong token chỉ chứa thông tin tối thiểu và mọi kết nối đã được bảo vệ bằng TLS, **JWE có thể không bổ sung lợi ích tương xứng với độ phức tạp**. Nếu token đi qua bên trung gian **không được phép đọc claims** hoặc policy yêu cầu confidentiality end-to-end đến Orders, có thể cần JWE hoặc opaque token.

### Hai mục tiêu riêng

| Mục tiêu | Biện pháp thường ưu tiên |
|---|---|
| Không để JavaScript browser đọc OAuth tokens | BFF + server token storage + HttpOnly session cookie. |
| Không để gateway/Client cầm token đọc claims | Opaque token hoặc JWE cho recipient chỉ định. |
| Không để attacker replay session cookie | Session ID bảo vệ, Secure/SameSite/CSRF, server invalidation, TLS và giám sát. |
| Không để attacker replay stolen access token | Sender-binding (DPoP/mTLS), TTL, revocation/RS checks, secret hygiene. |

**JWE không thay thế session/cookie security**, cũng không cho phép lưu refresh token trực tiếp trong JavaScript vì token ấy “đã mã hóa”.

## 15. Mã hóa không làm access token ngừng là bearer

Một access token có thể là một **JWE ciphertext dài**:

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ENCRYPTED_ACCESS_TOKEN>
~~~

Resource Server sẽ **giải mã và xác minh token**. Nhưng nếu attacker sao chép nguyên chuỗi `<ENCRYPTED_ACCESS_TOKEN>`, attacker không cần biết plaintext để **trình lại** token đến cùng endpoint.

### Replay trước và sau khi token bị đánh cắp

~~~mermaid
sequenceDiagram
    participant C as Client hợp lệ
    participant X as Attacker có bản sao ciphertext
    participant RS as Resource Server
    C->>RS: Bearer JWE access token
    RS->>RS: Decrypt + verify; authorise
    RS-->>C: 200 nếu được phép
    X->>RS: Replay nguyên chuỗi Bearer JWE
    RS->>RS: Cùng token vẫn có thể decrypt/verify
    RS-->>X: Có thể được phục vụ nếu không có sender binding/revocation
    Note over X,RS: Không cần biết các claims để replay một bearer token
~~~

### Biện pháp giảm replay

1. Giữ token khỏi log, URL, crash dumps, browser history, telemetry và nguồn không tin cậy.
2. **Access token TTL ngắn** và refresh token bảo vệ riêng.
3. **Audience/scope/resource** càng hẹp càng phù hợp.
4. **DPoP-bound token (RFC 9449)** hoặc **mTLS certificate-bound token (RFC 8705)** khi threat model yêu cầu và các bên hỗ trợ.
5. **Revocation state/introspection/denylist** nếu cần cắt token trước `exp`.
6. **Object-level authorization** vẫn cần kiểm tra principal, tenant và bản ghi được yêu cầu.

**Không tự khẳng định “JWE chống replay”.** AEAD tag chống chỉnh sửa ciphertext, **không tự ngăn phát lại chính ciphertext hợp lệ**.

## 16. Refresh token nên lưu bí mật, không phải nhét thêm trong JWE access token

**Refresh token** cho phép Client xin access token mới tại token endpoint. Trong nhiều hệ thống nó là opaque credential ngẫu nhiên được AS quản lý; ở một số triển khai nó có thể mang cấu trúc nội bộ hoặc được AS mã hóa.

### Các quy tắc

- Không gửi refresh token tới Resource Server.
- Không đặt refresh token bên trong access token hoặc ID token như một claim để tiện truyền.
- Không đưa refresh token vào URL, browser log, HTML, analytics, HTTP request tracing.
- Confidential Client/BFF giữ refresh token trong server-side protected storage, có encryption at rest/ACL và rotation theo chính sách.
- Native/public Client cần các biện pháp refresh token rotation hoặc sender-constraining theo profile/BCP, cùng secure storage thích hợp.
- **Revoke refresh token/token family** khi user disconnect hoặc bị phát hiện reuse theo policy.
- Nếu refresh token được **mã hóa bên trong** bởi AS, Client vẫn phải coi toàn bộ chuỗi ciphertext là **bí mật có khả năng sử dụng**.

### Phân biệt “mã hóa nội dung refresh token” với “bảo vệ refresh token”

~~~text
AS phát opaque/random R, lưu hash/verifier server-side:
  Client không đọc được claims vì chuỗi không chứa claims.
  Nếu attacker có R, vẫn có thể thử đổi token theo binding/policy.

AS phát self-contained encrypted R:
  Client không đọc được payload của R nếu thiếu decrypt key.
  Nếu attacker có R, vẫn có thể thử đổi token tại AS.
~~~

Vì vậy, confidentiality **không thay** Client binding, replay/reuse detection và revocation. Khi xác minh token type tại AS, **không dựa vào dạng chuỗi năm phần để cho rằng mọi JWE đều là access token**.

## 17. Recipient trust: ai được cầm khóa giải mã?

JWE chỉ đạt confidentiality nếu **private decryption key không nằm ở những bên vốn không được phép đọc nội dung**.

### Key ownership

| Key | Chủ sở hữu | Có thể công khai? | Sử dụng |
|---|---|---|---|
| AS JWS signing **private** key | AS/KMS/HSM. | Không. | Ký token. |
| AS JWS signing **public** JWK | Trusted issuer JWKS. | Có. | RP/RS verify signature. |
| Recipient JWE encryption **public** key | Client/RS, đăng ký với AS. | Có nếu profile cho phép. | AS mã hóa cho recipient. |
| Recipient JWE decryption **private** key | Recipient/keystore/HSM. | **Không.** | Recipient decrypt token. |
| Symmetric JWE direct key | Các bên được phép trao đổi bí mật. | **Không.** | Content encryption/key management theo profile. |

### Ví dụ trust mistake

~~~text
API Gateway không được phép đọc claims Orders.

Sai:
  AS mã hóa JWE cho public key của Gateway.
  Gateway decrypt và forward plaintext JWT tới Orders API.

Đúng theo mục tiêu confidentiality end-to-end:
  AS mã hóa JWE cho public key của Orders API.
  Gateway chỉ forward ciphertext nếu kiến trúc cho phép.
  Orders giữ private key, decrypt và verify đúng profile.
~~~

Mô hình “đúng” chỉ áp dụng nếu **Orders thực sự là recipient có khả năng decrypt** và hệ thống không thiết kế gateway làm trusted security enforcement point cần đọc claims. Nếu Gateway phải enforce scope/audience, bạn cần **lựa chọn kiến trúc khác có chủ ý**, không chia private key vô tội vạ.

### Không tự chọn recipient qua request chưa tin

AS không được chấp nhận `recipient_jwks_uri` tùy ý từ browser/callback/token request rồi mã hóa ID token chứa PII cho public key attacker. Public encryption keys phải đến từ **registration/metadata được xác thực và chính sách** của đúng Client/RS.

## 18. Quản lý `kid` và key rotation cho JWE

Một JWE protected header có thể có:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-decrypt-v3"
}
~~~

`kid` gợi ý chọn **recipient key version**; không phải bằng chứng nguồn token. Khi rotate:

~~~mermaid
flowchart TD
    A["Recipient tạo decryption key pair B"] --> B["Đăng ký/công bố public encryption key B đáng tin"]
    B --> C["Issuer biết B và được phép dùng B"]
    C --> D["Issuer mã hóa JWE mới với B, kid=B"]
    D --> E["Recipient giữ private A + B trong overlap cần thiết"]
    E --> F["Token mã hóa cho A hết hạn/được revoke"]
    F --> G["Retire/delete private A theo key policy"]
~~~

### Rotation khó hơn chỉ thay khóa ký

Nếu **mất private key giải mã cũ**, những JWE còn hiệu lực mã hóa cho khóa cũ có thể **không thể decrypt**. Với signing key rotation, verifier chỉ cần public key cũ trong overlap; với JWE, recipient cần **private decryption key cũ** trong khoảng cần xử lý dữ liệu/token cũ (nếu không có phương án reissue).

### Planned vs compromised key

| Trường hợp | Phương án |
|---|---|
| **Planned rotation** | Pre-register public B, issuer chuyển encrypt sang B, giữ private A có giới hạn cho token cũ, retire sau TTL/retention. |
| **Private decryption key A bị lộ** | Dừng phát cho A, rotate B, đánh giá các JWE cũ đã lộ nội dung, revoke/reissue token/grant và cắt tin private A theo threat model. |
| **Mất hoàn toàn private A** | Không thể giải mã JWE A còn lưu; cần kế hoạch token reissuance/session recovery, không tắt tag validation. |
| **Trùng `kid` A/B** | Không chọn khóa tùy ý; mỗi key material version có ID rõ, namespace theo recipient/profile. |

**Key leak có thể làm mất confidentiality của những ciphertext đã bị lưu lại**: nếu attacker đã thu thập JWE và sau đó lấy private decryption key, có thể giải mã các bản ghi lịch sử tương ứng, tùy thuật toán/key agreement. Không tuyên bố mọi JWE RSA-OAEP có forward secrecy như một phiên TLS 1.3.

## 19. Confidentiality xuyên miền tin cậy và multi-tenant

Giả sử một nền tảng phục vụ:

~~~text
Tenant A:
  RS = orders-tenant-a
  JWE recipient key = encrypt-A

Tenant B:
  RS = orders-tenant-b
  JWE recipient key = encrypt-B
~~~

Nếu AS mã hóa token Tenant A cho key B vì cache key thiếu tenant/client/audience, có thể **làm lộ claims cho recipient không được phép**. Chọn khóa mã hóa phải gắn với **trusted recipient registration, audience/resource, tenant/trust boundary**, không chỉ `kid` chung.

### Những invariant

1. **Recipient ID và public encryption key** từ trusted registration.
2. **AS issuer ID** và signing key từ AS key registry riêng.
3. **`kid`** trong outer JWE được xét trong đúng recipient key set; inner JWS `kid` trong đúng issuer signing key set.
4. **`aud`** của inner JWT phải nhắm Resource Server/Client đúng.
5. Một key dùng chung nhiều tenants chỉ khi chia sẻ trust boundary **đã được phê duyệt**, với rủi ro bị lộ/chuyển tenant được chấp nhận.
6. Tenant trong claims không thay **authorization dựa trên dữ liệu nguồn**.
7. Không coi “giải mã được” là bằng chứng request được phép đọc dữ liệu của tenant đó.

### Nhiều recipient

Nếu muốn JWE cho nhiều recipient, không mặc định có thể nối nhiều giá trị `kid` vào một JWE Compact. **JWE JSON Serialization** hỗ trợ biểu diễn có nhiều recipients theo chuẩn JOSE, nhưng cần những bên nhận hỗ trợ đúng format/profile. Với OAuth access token, đơn giản hóa thường bằng **token cho một audience/recipient** hoặc opaque token/introspection.

## 20. Encrypt-then-store khác với JWE token format

**Mã hóa token ở database** có thể dùng envelope encryption/AES-GCM/secret manager ở storage layer dù token bên ngoài là JWS hoặc opaque:

~~~text
BFF nhận refresh token R:
  token type = opaque
  cleartext R chỉ xuất hiện tạm thời trong trusted process
  KMS encrypt/data key bảo vệ R lưu trong database

Khi cần refresh:
  BFF được cấp quyền decrypt đúng record R
  gọi token endpoint qua TLS
  xóa plaintext references theo khả năng môi trường
~~~

Đó là **encryption at rest**, không biến R thành một **JWE** trong wire format.

### Hai lớp mã hóa có thể cùng tồn tại

| Lớp | Encryption object | Ai decrypt? |
|---|---|---|
| **JWE** | Nội dung self-contained token trao đổi giữa hệ thống. | Recipient đúng theo JOSE key/profile. |
| **Database envelope encryption** | Bytes của token/record đang lưu trong database. | Backend đã được cấp quyền KMS/data key. |

Ngay cả khi token là JWE ciphertext, **không coi nó vô hại nếu bị lộ**: ciphertext vẫn có thể là bearer credential. Có thể tiếp tục mã hóa **cả chuỗi token ở nơi lưu** nhằm giảm rò rỉ credential từ database backups, theo threat model.

### Operational storage hygiene

- Tách khóa KMS cho token storage khỏi JWE recipient decryption key khi vai trò khác nhau.
- Key rotation và data re-encryption tại storage không nhất thiết đồng bộ với JOSE `kid`/token rotation.
- Giới hạn IAM/ACL cho bảng tokens, telemetry, backups và khóa KMS.
- Không dùng encryption at rest làm lý do log plaintext refresh/access tokens.
- Có kế hoạch xóa/retention, incident response và audit khi token store bị truy cập trái phép.

## 21. Java/Nimbus JOSE: ký access JWT rồi mã hóa thành JWE

Ví dụ này minh họa **issuer (AS)** phát **nested access JWT** cho Orders API:

- **Inner JWS** ký bằng RSA private signing key của AS theo `PS256`.
- **Outer JWE** mã hóa bằng RSA public encryption key của Orders theo `RSA-OAEP-256` và `A256GCM`.
- Hai cặp khóa **khác nhau**, thuộc hai vai trò khác nhau.
- Keys được cung cấp qua **trusted KMS/keystore/registration**; không sinh key tạm trong request và không hardcode private keys.

### Mã minh họa với Nimbus JOSE + JWT

~~~java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.RSAEncrypter;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Date;
import java.util.List;

final class EncryptedAccessTokenIssuer {
    private final RSAPrivateKey trustedAsSigningPrivateKey;
    private final RSAPublicKey registeredOrdersEncryptionPublicKey;

    EncryptedAccessTokenIssuer(
            RSAPrivateKey trustedAsSigningPrivateKey,
            RSAPublicKey registeredOrdersEncryptionPublicKey) {
        this.trustedAsSigningPrivateKey = trustedAsSigningPrivateKey;
        this.registeredOrdersEncryptionPublicKey =
                registeredOrdersEncryptionPublicKey;
    }

    String issueExample(String subject) throws Exception {
        Date now = new Date();
        Date expiresAt = new Date(now.getTime() + 5 * 60_000L);

        // Claims thật phải được AS tạo từ trusted grant/client policy.
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer("https://auth.example.test")
                .subject(subject)
                .audience(List.of("orders-api"))
                .issueTime(now)
                .expirationTime(expiresAt)
                .claim("client_id", "shop-web")
                .claim("scope", "orders:read")
                .build();

        SignedJWT signed = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.PS256)
                        .type(new JOSEObjectType("at+jwt"))
                        .keyID("as-signing-v5")
                        .build(),
                claims);
        signed.sign(new RSASSASigner(trustedAsSigningPrivateKey));

        JWEObject encrypted = new JWEObject(
                new JWEHeader.Builder(
                        JWEAlgorithm.RSA_OAEP_256,
                        EncryptionMethod.A256GCM)
                        .keyID("orders-encryption-v2")
                        .contentType("JWT")
                        .build(),
                new Payload(signed.serialize()));

        encrypted.encrypt(
                new RSAEncrypter(registeredOrdersEncryptionPublicKey));
        return encrypted.serialize();
    }
}
~~~

### Các điểm không được copy nguyên vào production

1. Ví dụ không tự thực hiện toàn bộ **OAuth token issuance/authorization grant validation**, consent, refresh-token rules, revocation, client binding hay tenant policy.
2. `subject` trong code chỉ dùng để minh họa; **không** lấy subject/role/scope từ request của Client rồi ký không kiểm chứng.
3. Các ID `as-signing-v5`, `orders-encryption-v2` phải được ánh xạ tới **key versions đúng trong trusted registry**, không dùng chuỗi user nhập.
4. RSA private key của AS và public encryption key của Orders phải được quản lý/kiểm tra tương ứng; **không** để recipient chọn URL public key tùy ý.
5. Không gọi `signed.serialize()` vào log; biến `signed` chứa **inner JWS có claims đọc được** trong AS memory.
6. Ví dụ dùng Nimbus API theo phong cách thư viện JOSE phổ biến; version/dependency cụ thể cần được kiểm thử. HSM sign/CEK management có thể cần signer/encrypter khác.
7. Việc chọn `PS256` và `RSA-OAEP-256/A256GCM` chỉ là **một cấu hình được kiểm soát**, không phải bảo đảm mọi AS/RS hỗ trợ mặc định.
8. Nếu hệ thống áp dụng RFC 9068, đảm bảo **toàn bộ claims bắt buộc và token-type profile** được phát hành; không coi đoạn demo là implementation đầy đủ của RFC.

### Tại sao không chỉ JWE các claims?

Với public encryption key, attacker cũng có thể tạo ciphertext JWE cho Orders nếu biết public key. **Chữ ký JWS bên trong** ràng buộc nội dung với AS/private signing key sau khi decrypt. Đó là lý do ví dụ **không bỏ bước ký**.

## 22. Java/Nimbus JOSE: decrypt rồi verify inner JWS

Resource Server nhận ciphertext, cần **fail closed** nếu thuật toán, key, authentication tag hoặc signature không đúng. Trong thực tế, nên dùng library + trusted key resolver và đầy đủ claim/token-type validators.

### Ví dụ thuật toán cố định với trusted keys

~~~java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.text.ParseException;
import java.time.Clock;
import java.util.Date;

final class OrdersEncryptedAccessTokenValidator {
    private static final String TRUSTED_ISSUER =
            "https://auth.example.test";
    private static final String REQUIRED_AUDIENCE = "orders-api";

    private final RSAPrivateKey ordersRecipientPrivateKey;
    private final RSAPublicKey asTrustedSigningPublicKey;
    private final Clock clock;

    OrdersEncryptedAccessTokenValidator(
            RSAPrivateKey ordersRecipientPrivateKey,
            RSAPublicKey asTrustedSigningPublicKey,
            Clock clock) {
        this.ordersRecipientPrivateKey = ordersRecipientPrivateKey;
        this.asTrustedSigningPublicKey = asTrustedSigningPublicKey;
        this.clock = clock;
    }

    JWTClaimsSet decryptAndVerify(String compactJwe)
            throws ParseException, JOSEException {

        // Token length/format limits, trusted issuer and key selection
        // should be configured upstream in a production implementation.
        JWEObject outer = JWEObject.parse(compactJwe);
        if (!JWEAlgorithm.RSA_OAEP_256.equals(
                    outer.getHeader().getAlgorithm())
                || !EncryptionMethod.A256GCM.equals(
                    outer.getHeader().getEncryptionMethod())
                || !"orders-encryption-v2".equals(
                    outer.getHeader().getKeyID())
                || !"JWT".equals(
                    outer.getHeader().getContentType())) {
            throw new SecurityException("Rejected token format");
        }

        // Never release plaintext or claims if decrypt/tag check fails.
        outer.decrypt(new RSADecrypter(ordersRecipientPrivateKey));
        SignedJWT inner = SignedJWT.parse(outer.getPayload().toString());
        if (!JWSAlgorithm.PS256.equals(inner.getHeader().getAlgorithm())
                || !new JOSEObjectType("at+jwt")
                        .equals(inner.getHeader().getType())
                || !"as-signing-v5".equals(inner.getHeader().getKeyID())
                || !inner.verify(
                        new RSASSAVerifier(asTrustedSigningPublicKey))) {
            throw new SecurityException("Rejected token signature");
        }

        JWTClaimsSet claims = inner.getJWTClaimsSet();
        Date now = Date.from(clock.instant());
        if (!TRUSTED_ISSUER.equals(claims.getIssuer())
                || !claims.getAudience().contains(REQUIRED_AUDIENCE)
                || claims.getExpirationTime() == null
                || !claims.getExpirationTime().after(now)
                || (claims.getNotBeforeTime() != null
                    && claims.getNotBeforeTime().after(now))) {
            throw new SecurityException("Rejected access token claims");
        }
        return claims;
    }
}
~~~

### Cảnh báo bắt buộc đối với ví dụ

Đây là **ví dụ giáo dục với hai trusted keys cố định**; không phải JWT validator đầy đủ để dùng nguyên trạng production:

- Production cần **resolver** cho trusted recipient `kid` và issuer signing `kid`, với rotation/cache/algorithm pinning và ambiguity protection.
- Cần **issuer, audience, token type, expiration, `nbf`, `iat`, `jti`, Client binding, scope, tenant, revocation state và sender proof** theo profile; code chỉ minh họa một phần.
- Clock skew nên do policy quyết định. Mẫu dùng thời gian hiện tại không cộng/trừ leeway; không áp dụng máy móc cho mọi hệ thống.
- Cần xử lý null claims, malformed tokens, max token size, parsing depth, exception classification, memory/CPU budget.
- Nếu ký với **JWT access token RFC 9068**, cần enforce những claims/validators bắt buộc của profile và reject nested JWT sai kiểu, không chỉ mỗi `typ`.
- Token được giải mã ra JWS vẫn có thể chứa PII; **không log plaintext/JWS/claims thô**.
- Nếu access token là DPoP-/mTLS-bound, verifying inner JWS chưa chứng minh người đang gọi có khóa tương ứng.
- Nếu không cần xử lý claims trong ứng dụng, không nên tự gọi decrypt để “debug” hoặc xuất token dưới dạng plaintext cho người dùng.

### Chống giải mã giả/Oracle

Đừng trả lỗi ra Client theo dạng:

~~~text
400 "RSA private key không khớp"
400 "AES-GCM tag sai"
400 "Inner JWS đúng nhưng user email=alice@example.test"
400 "Có một user hợp lệ nhưng scope thiếu"
~~~

Đây là **information disclosure**. Resource Server nên trả phản hồi authentication failure đồng nhất/phù hợp profile ở bề mặt công khai, trong khi **log server-side** chỉ ghi reason code không chứa secrets, đi cùng metric/alert. Không tạo timing/oracle qua các nhánh giải mã tự viết.

## 23. Spring Security: không nhầm JwtDecoder thông thường với JWE

Spring Security Resource Server với cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

thường phục vụ **JWT/JWS signature verification**, không mặc nhiên tự **decrypt JWE**, chọn recipient private key và verify nested JWS theo toàn bộ profile. Nếu AS chuyển access token từ JWS sang JWE, Client/RS **phải có thiết kế rõ ràng**; chỉ thay metadata issuer hoặc khai báo JWKS không tự biến decoder thành JWE processor.

### Kiến trúc wrapper hợp lệ

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWE"] --> B["Custom trusted JWE processor"]
    B --> C{"JWE alg/enc/kid và auth tag đúng?"}
    C -- Không --> X["Reject authentication"]
    C -- Có --> D["Inner compact JWS"]
    D --> E["Trusted Spring JWT decoder / JOSE verifier"]
    E --> F{"Inner signature + typ/iss/aud/exp/claims đúng?"}
    F -- Không --> X
    F -- Có --> G["Scope/authority mapping + method authorization"]
    G --> H{"Owner/tenant/object permission đúng?"}
    H -- Không --> X
    H -- Có --> I["Permit request"]
~~~

Một adapter tùy biến có thể đưa **inner JWS** đã được giải mã an toàn qua `JwtDecoder` kiểm tra issuer/JWKS/audience, rồi trả đối tượng `Jwt`. Trong production, cần bảo đảm adapter thực sự nằm trên **đường xác thực của mọi API endpoint**, cấu hình SecurityFilterChain phù hợp, không có filter chain nào nhận raw JWE làm JWT signed thông thường hoặc bỏ qua signature.

### Gợi ý interface

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;

// Pseudointerface: chưa phải @Bean/SecurityFilterChain hoàn chỉnh.
final class EncryptedJwtDecoderAdapter implements JwtDecoder {
    private final JwtDecoder trustedInnerJwtDecoder;
    private final TrustedJweProcessor jweProcessor;

    EncryptedJwtDecoderAdapter(
            JwtDecoder trustedInnerJwtDecoder,
            TrustedJweProcessor jweProcessor) {
        this.trustedInnerJwtDecoder = trustedInnerJwtDecoder;
        this.jweProcessor = jweProcessor;
    }

    @Override
    public Jwt decode(String encryptedAccessToken) {
        String signedInnerJwt =
                jweProcessor.decryptAndRequireSignedInnerJwt(
                        encryptedAccessToken);
        return trustedInnerJwtDecoder.decode(signedInnerJwt);
    }
}
~~~

`TrustedJweProcessor` là **interface khái niệm chưa triển khai**; đây **không phải snippet copy-paste chạy được**. Nó phải pin `alg`/`enc`/recipient keys, verify tag, giới hạn input và reject invalid nesting. `trustedInnerJwtDecoder` phải pin trusted issuer, key source/algorithm, audience, type, expiry và claims; application vẫn cần scope/tenant/owner authorization. Nếu dùng Spring OAuth2 Client hay OIDC login, **encrypted ID token support** có integration riêng với OP/Client registration và thư viện sử dụng; không lấy resource-server adapter này thay nguyên hệ thống OIDC Client.

### Khi không muốn custom cryptography pipeline

Cân nhắc **opaque access token + introspection** hoặc token format mà Spring/RS chính thức hỗ trợ. Sự đơn giản về crypto parser, cache/key lifecycle và vận hành là một tiêu chí bảo mật hợp lệ, không phải sự “thiếu hiện đại”.

## 24. Decryption oracle và lỗi triển khai mã hóa

**Decryption oracle** là hệ thống vô tình tiết lộ thông tin qua câu trả lời hoặc thời gian xử lý khi nhận ciphertext do attacker chỉnh sửa. Ví dụ rủi ro kinh điển gồm RSA PKCS#1 v1.5 padding oracle, AES-CBC padding/error oracle, hoặc phân nhánh quá chi tiết trước khi xác minh tag.

### Cách phòng thủ

1. **Chỉ hỗ trợ `alg`/`enc` được profile/recipient đăng ký**; không downgrade từ RSA-OAEP sang RSA1_5 theo header.
2. Ưu tiên thư viện JOSE được bảo trì có **AEAD/tag validation** và xử lý lỗi phù hợp.
3. Không giải mã/parse/use plaintext nếu **authentication tag hoặc các kiểm tra mật mã bắt buộc chưa qua**.
4. Chỉ dùng **recipient private keys tin cậy**; không lấy local filesystem/KMS key name trực tiếp từ `kid` user khai.
5. **Giới hạn kích thước token**, số recipients, JSON nesting, compression/decompression size và CPU.
6. **Không nêu lý do chi tiết** về padding/tag/key trong HTTP error cho caller trái phép.
7. Bảo vệ **rate limiting và anomaly detection** cho hàng loạt ciphertext lỗi.
8. Định nghĩa behavior khi KMS/HSM unavailable: **fail closed** theo security policy, không trả claims chưa xác minh.
9. Test invalid tag, truncated IV, wrong key, changed header, unsupported alg/enc và malformed nested JWT.

### JWE AEAD tag là cần thiết nhưng chưa đủ

~~~text
Attacker thay một bit của ciphertext:
  AES-GCM tag verification -> phải fail.

Attacker gửi nguyên ciphertext hợp lệ đã đánh cắp:
  Tag vẫn đúng; token còn có thể được chấp nhận nếu bearer.

Attacker mã hóa JWE mới bằng recipient public key:
  Tag có thể đúng, nhưng inner JWS của trusted issuer không có.
  -> Phải reject vì source authentication không hợp lệ.
~~~

Đừng trộn ba trường hợp trên thành một thông báo “JWE luôn an toàn”.

## 25. Algorithm agility và JOSE header không tin cậy

### Một allowlist minh họa

~~~yaml
# Pseudoconfig cho security architecture, KHÔNG phải Spring schema.
token_profile: orders-encrypted-access-token
trusted_issuer: https://auth.example.test
required_audience: orders-api
required_inner_type: at+jwt
outer_jwe:
  accepted_key_management_algorithms: [RSA-OAEP-256]
  accepted_content_encryption_algorithms: [A256GCM]
  recipient_key_store: orders-protected-keystore
inner_jws:
  accepted_signature_algorithms: [PS256]
  signing_key_source: trusted-issuer-jwks
require_nested_signed_jwt: true
~~~

**Từng dòng là policy mô hình, không phải config có hiệu lực nếu chỉ đưa vào application.yml**. Phải được thư viện JWE/JWS/RS security filter thực thi. Và policy **phải phù hợp registration/capabilities thực tế**, không tùy tiện bật một thuật toán mới.

### Những fallback phải cấm

| Điều xảy ra | Fallback nguy hiểm | Hành vi đúng |
|---|---|---|
| Không decrypt được với key đúng `kid` | Thử mọi private key tenant khác. | Chỉ lookup đúng recipient/policy, reject nếu không đủ. |
| JWE `alg=RSA1_5` | Bật RSA1_5 để không lỗi. | Reject nếu ngoài allowlist; migration có kiểm soát. |
| JWE `enc` không hỗ trợ | Bỏ tag hoặc parse ciphertext như Base64. | Reject token, không cho phép claims chưa xác minh. |
| Inner JWS `alg=none` | “Outer JWE đã bảo vệ rồi”. | Reject khi profile yêu cầu signed inner JWT. |
| Inner JWS issuer sai | Dùng `iss` trong inner token để tự tìm issuer khác. | Chỉ trusted issuer, exact claims validation. |
| Header `jku`/`x5u` lạ | Fetch public key attacker qua URL. | Không trust URL/header ngoài policy. |
| Gateway không giải mã được JWE | Cho qua API không authentication. | Fail closed hoặc chọn kiến trúc khác được phê duyệt. |
| Resource Server thấy JWE của Client khác | Chia private decryption key cross-client. | Đúng recipient/audience, token exchange/opaque nếu cần. |

### Key confusion trong nested JWT

Outer JWE `kid` chọn khóa giải mã ở **Resource Server/Client recipient**; inner JWS `kid` chọn public signing key ở **issuer JWKS**. Chúng không được dùng chung map `keysByKid` thiếu namespace. Lý tưởng:

~~~text
recipientDecryptionKeys[(recipient_id, enc_alg, kid)]
trustedIssuerSigningKeys[(issuer, token_profile, sig_alg, kid)]
~~~

**Không có quan hệ “outer kid bằng inner kid thì token đáng tin hơn”**. Trùng tên key giữa hai miền cũng không phải bằng chứng bảo mật.

## 26. Revocation, expiry và incident response cho encrypted token

JWE access token có **vòng đời token** giống những access token khác: nó được phát, lưu/truyền, xác minh, hết hạn hoặc bị thu hồi theo cơ chế được hỗ trợ. **Mã hóa payload không tự tạo trạng thái revocation.**

### Ba trường hợp

| Sự cố | Biện pháp chính | Điều cần nhớ |
|---|---|---|
| **Bearer JWE bị sao chép** | Revoke access/refresh/grant theo AS policy; RS denylist/introspection/TTL; khóa sender proof nếu liên quan. | Attacker có thể replay mà không decrypt. |
| **Recipient private decryption key bị lộ** | Rotate recipient key, dừng phát ciphertext cho key cũ, đánh giá JWE lịch sử và giới hạn recipient trust. | Token ciphertext đã thu thập trước đó có thể bị đọc lại. |
| **Issuer private signing key bị lộ** | Stop signer, rotate signing key, invalidate JWKS caches/trust, đánh giá token giả đã phát. | JWE không ngăn attacker tạo JWS giả nếu đã có signing key. |
| **Refresh token bị lộ** | Revoke token family/grant theo policy, kiểm tra reuse/new token issuance. | Encrypt access token không bảo vệ refresh token đã bị lộ. |
| **HSM/KMS key không truy cập được** | Quy trình availability/fail-closed và phục hồi có quản trị. | Không bỏ decryption/tag/signature checks để duy trì API 200. |

### 200 OK không có nghĩa JWT đã chết ở mọi RS

Nếu Client gửi **RFC 7009 revocation** và AS trả 200, chưa thể kết luận mọi RS offline đã biết JWE token tương ứng bị revoke. Với **self-contained encrypted JWT**, RS có thể decrypt+verify offline đến `exp` nếu không có revocation state. Phải đo **RS propagation latency** hoặc thiết kế denylist/state check khi cần cắt quyền sớm.

### Cắt quyền của một user không đồng nghĩa rotate JWE recipient key

JWE recipient key có thể giải mã hàng triệu token của nhiều users. Khi user logout/disconnect, xử lý **session/token/grant** của user; không gỡ recipient private key toàn API nếu không có sự cố về key. Ngược lại, **compromised recipient key** là sự cố rộng hơn một user và có thể đòi reissue/re-encrypt nhiều tokens.

### Runbook khi bị lộ plaintext claims

1. Xác định nguồn lộ: JWS payload, log, decoded token, application APM, backup, data leak hoặc key compromise.
2. Phân loại claims nhạy cảm và **những bên đã thấy**, kể cả Client/gateway, không chỉ attacker bên ngoài.
3. Nếu chỉ log JWS claims, sửa **data minimization/log redaction**; JWE có thể là kiểm soát bổ sung nhưng không thay log hygiene.
4. Nếu lộ bearer credential còn hạn, kích hoạt **revocation/RS policy** phù hợp.
5. Nếu lộ private decryption key, rotate và đánh giá **ciphertext đã lưu trong quá khứ**; bảo vệ kế hoạch key backup/retention.
6. Nếu lộ signing private key, hành động ở **issuer trust/JWS verification layer**, không chỉ thay JWE `kid`.
7. Theo dõi audit ở mức metadata, tránh tái xuất secrets khi điều tra.

## 27. Quan sát vận hành và chỉ số đúng nghĩa

Không nên ghi plaintext token chỉ để phân tích lỗi JWE. Hệ thống có thể đo bằng **mã lỗi đã phân loại và identifier không nhạy cảm**:

~~~json
{
  "event": "token.validation",
  "profile": "orders-encrypted-access-token",
  "trusted_issuer": "https://auth.example.test",
  "recipient_key_version": "orders-encryption-v2",
  "outer_alg": "RSA-OAEP-256",
  "outer_enc": "A256GCM",
  "inner_sig_alg": "PS256",
  "result": "rejected",
  "reason": "invalid_audience",
  "correlation_id": "token-check-42"
}
~~~

Đây là **audit mẫu**. Các trường `outer_alg`, `outer_enc` và `kid` từ token chưa xác minh chỉ là **claimed values** cho tới khi cryptographic verification hoàn tất; phải escape/limit/normalize, không để attacker gửi chuỗi tùy ý thành metric labels. `recipient_key_version` chỉ được ghi sau khi server thực sự xác định key version từ registry đáng tin.

### Metrics hữu ích

| Metric | Ý nghĩa | Cảnh báo |
|---|---|---|
| **JWE decrypt success/failure by recipient key version** | Phát hiện sai key, rotate chưa đồng bộ, ciphertext lỗi. | Không log ciphertext hoặc private key. |
| **Invalid AEAD tag count** | Phát hiện tampering/probing hoặc sự cố transport. | Không mô tả nguyên nhân tag chi tiết cho caller. |
| **Inner JWS signature rejection** | Sai trusted issuer/signing key hoặc token giả. | Không fallback unsigned. |
| **Unsupported `alg`/`enc` count** | Giao thức lệch hoặc attacker thử downgrade. | Không tự thêm thuật toán cũ vô hạn. |
| **Plaintext claims access audit** | Ai được phép decrypt token? | Giới hạn quyền truy cập, không log claim values thừa. |
| **KMS/HSM decrypt latency/error** | Dependency availability và capacity. | Không fail-open. |
| **Token length / request rejection** | JWE lớn gây giới hạn HTTP/proxy và DoS. | Không cho token quá lớn làm cạn memory. |
| **Recipient key retirement coverage** | Có RS/Client còn cần private key cũ? | Không hủy key quá sớm trong planned rotation. |
| **AS issuance by token profile/recipient key** | Có issuer nào còn phát ciphertext cho key đã retired? | Không nhầm alias với immutable version. |
| **RS authorization denied after decrypt** | Token crypto đúng nhưng thiếu aud/scope/owner/tenant. | Đây là kiểm soát mong muốn, không phải lỗi mã hóa. |

### Vì sao metric “100% JWE decrypt success” chưa đủ?

Nếu verifier chỉ decrypt và không verify inner JWS/issuer/audience, attacker có thể tạo **JWE mới bằng recipient public key** chứa thông tin tự khai; metric decrypt success vẫn đẹp. Vì vậy phải có **separate signature, claims, token-type và authorization metrics**.

## 28. Ma trận kiểm thử confidentiality và token encryption

Giả sử AS tin cậy `https://auth.example.test` phát nested JWT access token cho `orders-api`: inner JWS `PS256` với signing key AS, outer JWE `RSA-OAEP-256` / `A256GCM` với public recipient key Orders. Client giữ chuỗi token và gọi Orders qua HTTPS. Tất cả test nên dùng **test keys, test accounts, fixture data**, không dùng token thực/PII thật.

| # | Kịch bản kiểm thử | Kết quả kỳ vọng | Ý nghĩa |
|---|---|---|---|
| 1 | JWS access token chỉ ký bị decode Base64URL | Payload nhìn thấy được; signature vẫn cần verify. | JWS không bảo mật claims. |
| 2 | JWE hợp lệ bị xem bằng Base64URL decoder | Chỉ metadata header/ciphertext, không đọc được inner claims khi thiếu key. | JWE confidentiality. |
| 3 | JWE hợp lệ với đúng recipient key và inner signature hợp lệ | Decrypt, verify và validate claims rồi xét quyền. | Luồng chuẩn. |
| 4 | JWE encrypted cho Client khác, Orders không có private key | Reject, không chọn key tenant khác. | Recipient isolation. |
| 5 | JWE header khai `alg` ngoài allowlist | Reject trước/sau parse policy; không downgrade. | Algorithm pinning. |
| 6 | JWE header khai `enc` ngoài allowlist | Reject, không thử giải mã không xác thực. | Content encryption policy. |
| 7 | JWE `RSA1_5` nhưng policy chỉ `RSA-OAEP-256` | Reject. | Legacy algorithm protection. |
| 8 | JWE `kid` đúng nhưng ciphertext được tạo cho key khác | Decrypt/tag thất bại, reject. | Key material binding. |
| 9 | JWE header `kid` không tồn tại | Không thử mọi private key, reject theo policy. | Unknown key selection. |
| 10 | JWE recipient `kid` trùng với tenant B | Không lấy khóa tenant B nếu request thuộc tenant A. | Multi-tenant isolation. |
| 11 | Attacker sửa một bit ciphertext | Tag verification failure. | Tamper detection. |
| 12 | Attacker sửa JWE protected header `alg`/`kid` | Không vượt policy/tag validation. | Protected header integrity. |
| 13 | Attacker sửa/loại JWE authentication tag | Reject, không xuất plaintext. | AEAD mandatory tag. |
| 14 | JWE IV bị thiếu hoặc malformed | Reject; không tạo IV cố định bù vào. | Nonce/format validation. |
| 15 | Mã hóa hai messages với reused GCM IV/key cố ý trong test | Test phát hiện vi phạm thiết kế, không dùng production. | AEAD nonce safety. |
| 16 | JWE plaintext chỉ là unsigned JSON claims | Reject nếu profile yêu cầu signed inner JWT. | Source authentication. |
| 17 | Attacker dùng public key Orders tạo JWE chứa inner JWS tự ký | Reject inner JWS signature. | Public-key encryptability. |
| 18 | Outer JWE decrypt đúng, inner JWS `alg=none` | Reject. | Nested JWT signature. |
| 19 | Outer JWE decrypt đúng, inner JWS ký bởi issuer khác | Reject theo trusted issuer/signing keys. | Issuer trust. |
| 20 | Inner JWS signature đúng nhưng `iss` sai | Reject. | Issuer claims validation. |
| 21 | Inner JWS có `aud=billing-api` gửi Orders | Reject. | Audience validation. |
| 22 | ID token `aud=shop-web` được bọc JWE và gửi Orders | Reject do token purpose/audience. | Cross-JWT confusion. |
| 23 | Inner JWT hết `exp` dù decrypt/signature đúng | Reject. | Expiry. |
| 24 | Inner JWT có `nbf` trong tương lai | Reject theo clock-skew policy. | Time validation. |
| 25 | JWT đúng issuer/audience nhưng thiếu `orders:read` | Reject thao tác đọc. | Scope enforcement. |
| 26 | JWT đúng scope nhưng order thuộc tenant B | Reject trừ khi có quyền cross-tenant rõ ràng. | Object authorization. |
| 27 | JWE đã bị đánh cắp và replay nguyên văn | Thử chứng minh bearer replay vẫn có thể xảy ra nếu không sender-bound. | Confidentiality != PoP. |
| 28 | Encrypted access token còn hạn sau revoke refresh token | Test RS revocation state/TTL, không mặc định chết ngay. | Revocation semantics. |
| 29 | Opaque token không có JWS header được gửi vào JWE decoder | Reject hoặc định tuyến theo trusted token-profile contract. | Format separation. |
| 30 | Opaque token introspection trả `active=false` | RS từ chối. | Opaque revocation. |
| 31 | Gateway không có recipient private key cố decode JWE | Không đọc claims; không bỏ qua authentication của RS. | Trust boundary. |
| 32 | Gateway ghi nguyên Bearer JWE vào access log | Test **FAIL**: log credential dù ciphertext. | Credential hygiene. |
| 33 | App ghi inner decrypted JWS hoặc claims vào error log | Test **FAIL**: rò rỉ PII. | Post-decryption leakage. |
| 34 | JWE header `kid` chứa email user | Test **FAIL** confidentiality header metadata. | Sensitive header. |
| 35 | `zip` bật với secret và attacker-chosen data | Test threat model/length leak, không mặc định cho phép. | Compression side channel. |
| 36 | JWE ciphertext oversized hoặc compressed bomb | Bounded parser/size reject, không exhaustion. | Availability security. |
| 37 | Decryption/key error phản hồi chi tiết padding/tag | Test **FAIL**: error uniformity cần sửa. | Oracle prevention. |
| 38 | Attacker gửi hàng nghìn ciphertext invalid | Rate limit/monitor; không làm HSM hết tải. | Abuse resistance. |
| 39 | JWE header `jku` trỏ attacker host | Không tự trust/fetch ngoài recipient/issuer policy. | Key substitution / SSRF. |
| 40 | JWE `kid` bị dùng như KMS ARN từ caller | Bị từ chối/truy vấn registry allowlisted. | Confused deputy. |
| 41 | AS mã hóa cho public key chưa đăng ký của Client | Reject issuance/registration error. | Recipient trust. |
| 42 | Planned recipient key rotation A→B, public B công bố trước | Token B decrypt được, A còn theo overlap. | Safe key rotation. |
| 43 | Private recipient key A bị hủy trước khi JWE A hết hạn | Token A lỗi decrypt; phát hiện kế hoạch thiếu. | Key retirement window. |
| 44 | Private recipient key A bị lộ | Incident rotate, đánh giá ciphertext lịch sử, reissue/revoke. | Confidentiality breach. |
| 45 | AS signing key bị lộ nhưng recipient key không lộ | Kiểm tra inner JWS trust, chặn key cũ theo incident. | Authenticity compromise. |
| 46 | OIDC RP registration yêu cầu encrypted ID token, OP trả plain JWS | RP phải xử lý theo hợp đồng/profile, không lặng lẽ nới policy. | OIDC integration. |
| 47 | RP encrypted ID token giải mã nhưng không kiểm tra `nonce` khi flow cần | Test **FAIL**: OIDC transaction binding. | Authentication semantics. |
| 48 | Client Credentials grant token bị mã hóa, client secret còn lộ | Attacker vẫn có thể xin token mới; cần rotate/disable credential. | Client security. |
| 49 | DPoP-bound encrypted access token với proof key sai | RS từ chối theo `cnf.jkt` và proof validation. | Sender binding. |
| 50 | mTLS-bound encrypted access token với certificate sai | RS từ chối dù JWE/JWS hợp lệ. | Certificate binding. |
| 51 | Hai API chia sẻ private decrypt key dù cần cách ly recipient | Kiểm thử trust boundary/khuyến nghị key tách. | Blast radius. |
| 52 | Spring Resource Server nhận JWE với JWT decoder mặc định | Phải có adapter JWE đã kiểm soát hoặc chọn token format phù hợp. | Framework capability. |
| 53 | Adapter decrypt rồi bỏ qua inner `typ`/`aud` | Test **FAIL**, bổ sung validators. | Token-purpose protection. |
| 54 | KMS/HSM decrypt unavailable | Fail closed, rõ availability policy; không trả claims chưa verify. | Dependency failure. |
| 55 | Logs/metrics nhận `alg`/`kid` cực dài từ header lạ | Không có high-cardinality/log injection. | Telemetry safety. |
| 56 | Multi-tenant Key Registry lấy public key từ Client B theo A's request | Test **FAIL**, binding recipient registration phải đúng. | Encryption-to-wrong-recipient. |

### Phân nhóm kết quả

Không đủ nếu một bộ test chỉ kiểm tra **“decryption success”**. Các nhóm cần tách:

1. **Confidentiality tests:** JWS payload đọc được, JWE payload không đọc được khi thiếu key, không lộ PII trong header/log.
2. **Cryptographic integrity tests:** wrong key/tag/header, inner JWS invalid, algorithm/key confusion.
3. **Token validation tests:** type, issuer, audience, lifetime, nonce/scope, revoked/inactive state.
4. **Authorization tests:** user/client/tenant/object/resource policy.
5. **Operational tests:** rotation, cache, key outage, performance/size limits, telemetry.
6. **Compromise/replay tests:** stolen bearer ciphertext, Client credential theft, sender-bound tokens và incident response.

## 29. Tình huống tự luyện

**Tình huống A — JWS đã ký, sao email vẫn đọc được?** API dùng `RS256` và HTTPS, nhưng Client copy JWT vào một công cụ decode rồi thấy `email`/`tenant_id`. Có phải chữ ký lỗi?

**Giải thích:** Không. Chữ ký JWS không che payload. Nếu Client không nên biết các claims ấy, phải **giảm claims, chuyển opaque token hoặc JWE cho đúng recipient**. HTTPS bảo vệ đường truyền, không che nội dung đối với người đang giữ token.

**Tình huống B — Token được mã hóa nên có thể đặt trong URL?** Developer nói Bearer JWE không thể đọc nên có thể đặt `access_token` ở query string cho tiện. Có đúng?

**Giải thích:** Không. Chuỗi ciphertext vẫn là credential có thể replay. URL xuất hiện ở browser history, access log, proxy và analytics. Dùng HTTP `Authorization` header qua TLS, tránh credential trong URL.

**Tình huống C — Gateway không có private key.** Client gửi encrypted access token cho Orders API qua gateway. Gateway không đọc được `scope`. Có phải thiết kế sai?

**Giải thích:** Không nhất thiết. Nếu mục tiêu là giấu claims khỏi gateway, đó là đúng yêu cầu confidentiality; nhưng nếu gateway **phải làm authorization** thì kiến trúc cần đổi: trusted introspection, token riêng cho gateway, hoặc RS làm authorization. Không nên chia private key cho gateway mà không thay trust model.

**Tình huống D — Public key bị công khai.** Orders công bố public encryption key trong JWK. Attacker dùng nó tạo JWE chứa `role=admin`. Orders giải mã thành công. Có được cấp quyền?

**Giải thích:** Không. Public encryption key **ai cũng có thể dùng để mã hóa**. Orders phải verify **inner JWS signature của trusted AS** và mọi claims/authorization.

**Tình huống E — Token là JWE nhưng được phát lại.** Attacker sao chép toàn bộ encrypted bearer token còn hạn, không có private decrypt key. API có thể phục vụ attacker không?

**Giải thích:** Có thể nếu token chỉ là bearer và RS chưa revoke, không sender-constrained. JWE giữ bí mật nội dung, **không ngăn replay nguyên ciphertext**.

**Tình huống F — Token chứa medical record.** Team mã hóa JWT rồi đưa cả kết quả xét nghiệm trong access token vì “đã AES-GCM”. Có phù hợp?

**Giải thích:** Thường không. Hãy **tối thiểu hóa claims**, chỉ giữ subject/scope/audience và cho RS truy vấn dữ liệu sau authorization. Encryption không thay chính sách bảo vệ dữ liệu hay vòng đời/retention.

**Tình huống G — Mã hóa JWE bằng key Client không đáng tin.** Browser cho nhập một URL JWKS rồi OP dùng để mã hóa ID token của user. Rủi ro?

**Giải thích:** Attacker có thể cung cấp public key của họ; OP sẽ gửi ciphertext mà attacker giải mã được. Public encryption key phải gắn với **trusted Client registration** và chính sách phù hợp.

**Tình huống H — Nhầm `alg`.** Một JWE có `alg=RSA-OAEP-256`, `enc=A256GCM`. Developer cho rằng `RSA-OAEP-256` là thuật toán ký JWT. Vì sao sai?

**Giải thích:** Trong JWE, `alg` là **key management algorithm**, còn `enc` là content encryption. Với JWS, `alg` lại là signature/MAC algorithm. Hai mục đích khác nhau.

**Tình huống I — Inner JWS không hợp lệ.** JWE decrypt được nhưng JWS bên trong ký bằng private key của issuer khác. Có nên tin vì outer tag đã đúng?

**Giải thích:** Không. AEAD tag chỉ chứng minh toàn vẹn ciphertext dưới CEK; inner signature/issuer phải đúng trusted AS theo profile.

**Tình huống J — Private decrypt key bị mất.** Sau rotation, Orders xóa private key A ngay nhưng AS vẫn phát JWE cho public A ở một region. Điều gì xảy ra?

**Giải thích:** Orders không giải mã được token A; cần điều phối prepublication, vùng triển khai, TTL/overlap và chỉ retire A sau khi issuance và token lifetime đã được xử lý.

**Tình huống K — Private decrypt key bị lộ.** Attacker có hàng nghìn JWE ciphertext từng thu thập rồi lấy được private key A. Chỉ đổi `kid` có giải quyết được không?

**Giải thích:** Không. Phải rotate **key material**, dừng encrypt bằng A, đánh giá ciphertext cũ, áp dụng revocation/reissue và xử lý lộ claims. Đổi tên ID không thay key.

**Tình huống L — Encrypted access token đã revoke?** AS nhận revoke refresh token và trả 200; RS có JWE access token còn 10 phút và chỉ decrypt/verify offline. Nó có từ chối ngay?

**Giải thích:** Không mặc định. Phải có RS state/denylist/introspection hoặc TTL chấp nhận được, vì encryption không cung cấp revocation state.

**Tình huống M — BFF lưu token mã hóa trong database.** BFF encrypt một opaque refresh token bằng KMS trước khi ghi DB. Chuỗi gửi tới AS có phải JWE không?

**Giải thích:** Không nhất thiết. Đây là **encryption at rest**; BFF phải decrypt storage value để gửi đúng opaque refresh token trong OAuth request. JWE là một token/message format JOSE riêng.

**Tình huống N — ID token được mã hóa nhưng không kiểm tra `nonce`.** RP decrypt/verify signature nhưng bỏ qua `nonce` đã gửi trong authorization request. Có an toàn?

**Giải thích:** Không nếu flow/profile yêu cầu nonce. Encryption không thay OIDC transaction binding, issuer, audience hoặc checks chống code/token substitution.

**Tình huống O — Nhiều Resource Server.** AS phát một JWE cho public key Orders, Client gửi cùng token tới Billing. Billing có thể dùng luôn?

**Giải thích:** Không nếu không có recipient key và audience phù hợp. Nên cấp token riêng cho resource hoặc thiết kế token exchange/opaque introspection, không chia private key giữa các API tùy tiện.

**Tình huống P — Lộ signing key nhưng không lộ decryption key.** Attacker có private signing key của AS và public encryption key của Orders. Có thể tạo token giả vừa ký vừa mã hóa?

**Giải thích:** Có thể. Nếu RS vẫn tin signing key bị lộ, attacker có thể tạo inner JWS giả và encrypt cho Orders. Phải rotate/retire signing key và cập nhật verifier trust/caches; không dựa vào JWE để giải quyết signing-key compromise.

**Tình huống Q — `zip` để làm nhỏ token.** Team bật compression cho JWT có secret và input do attacker kiểm soát, thấy ciphertext length thay đổi. Cần làm gì?

**Giải thích:** Đánh giá compression side channels và thông tin bị lộ qua độ dài; mặc định tránh nén dữ liệu nhạy cảm trộn với input attacker, cân nhắc giảm claims/opaque token.

**Tình huống R — Spring chỉ cấu hình issuer-uri.** Resource Server đang verify signed JWT, AS chuyển sang nested JWE rồi API trả 401. Có nên tắt xác thực để chạy tiếp?

**Giải thích:** Không. Decoder JWT thường không tự decrypt JWE; cần triển khai adapter JWE được review và inner JWS validation hoặc chọn token format/opaque introspection được hỗ trợ. Không fail-open.

## 30. Bảng quyết định: cần JWE, opaque token hay JWS?

### Quy trình lựa chọn

~~~mermaid
flowchart TD
    A["Cần truyền credential cho API/RP"] --> B{"Claims chứa dữ liệu nhạy cảm không cần thiết?"}
    B -- Có --> C["Loại bỏ/giảm claims trước"]
    B -- Không --> D["Xác định các bên giữ chuỗi token"]
    C --> D
    D --> E{"Một bên phải giữ token nhưng không được đọc payload?"}
    E -- Không --> F["JWS tối thiểu + TLS có thể phù hợp"]
    E -- Có --> G{"AS/RS hỗ trợ opaque token + introspection an toàn?"}
    G -- Có --> H["Cân nhắc opaque token; đo cache/availability"]
    G -- Không --> I["Cân nhắc JWE cho recipient tin cậy"]
    I --> J["Khi cần issuer authenticity: ký JWS rồi mã hóa JWE"]
    F --> K["Bảo vệ token, enforce iss/aud/scope/exp/revocation"]
    H --> K
    J --> K
    K --> L["Threat model sender binding, key lifecycle, data privacy"]
~~~

### Bốn câu hỏi buộc phải trả lời trước khi viết code

1. **Ai được phép đọc claims?** AS, Client, RP, Gateway, RS, telemetry, support operator hay external partner? Nếu chưa định nghĩa recipient/trust boundary, không thể chọn khóa JWE đúng.
2. **Claims nào thật sự cần được nhúng?** Nếu không cần, **xóa chúng** thay vì áp dụng JWE chỉ để che dữ liệu đã không nên xuất hiện.
3. **Ai chịu trách nhiệm xác thực issuer và phân quyền?** Decrypt JWE không đủ; phải có inner signature/trust model, token profile và business authorization.
4. **Nếu mất một khóa hoặc AS/RS tạm lỗi, hệ thống làm gì?** Key rotation, outage, reissue, cache, revocation và incident cần được thiết kế ngay từ đầu.

### Ví dụ lựa chọn theo tình huống

| Hệ thống | Yêu cầu | Phương án nên cân nhắc | Lý do |
|---|---|---|---|
| API nội bộ chỉ cần `sub` opaque, `scope`, `aud` | Không có yêu cầu ẩn claims khỏi các RS tin cậy. | **JWS + TLS** với claims tối thiểu. | Đơn giản, public-key verification nhanh. |
| API cần chặn access token nhanh và không cho Client xem claims | RS có introspection service. | **Opaque + introspection**, cache TTL phù hợp. | Claims ở AS; revocation state tập trung hơn. |
| Một Client/Proxy giữ token nhưng không được đọc dữ liệu nhạy cảm mà RS cần | Chỉ RS có quyền đọc. | **Nested JWS trong JWE** cho recipient RS. | Giữ confidentiality tới recipient và xác thực issuer bằng inner JWS. |
| OIDC RP yêu cầu ID token encrypted | OP và RP có registration/key lifecycle phù hợp. | **OIDC encrypted ID token** theo profile. | Bảo vệ claims định danh khỏi bên không có Client decryption key. |
| BFF không muốn browser cầm token | BFF giữ token server-side. | **BFF session cookie HttpOnly**; token format chọn riêng. | Không cần mã hóa để “gửi OAuth token xuống browser” nếu browser không nhận nó. |
| Nhiều RS độc lập phải truy cập token, không chia decryption keys | Tách trust boundary/khác audience. | **Token riêng per-resource hoặc opaque**. | Giảm chia sẻ private key và cross-resource confusion. |
| Worker service bị lộ client secret | Kẻ tấn công có thể xin token mới. | **Disable/rotate client credential** và xử lý grants/tokens. | JWE không ngăn dùng client secret bị đánh cắp. |

### Giới hạn của bài toán chọn token format

Tất cả những lựa chọn trên vẫn cần tuân thủ **OAuth 2.0/OIDC profile thực tế** của Authorization Server, Client registration và Resource Server. Không tự đổi định dạng access token giữa JWS/JWE/opaque khi các bên chưa được cập nhật và kiểm thử. Một hệ thống có thể dùng **JWS cho ID token**, **opaque access token** và **opaque refresh token** cùng lúc; không có lý do mọi loại token bắt buộc cùng định dạng mã hóa.

## Checklist triển khai confidentiality cho token

1. **Nêu mục tiêu rõ:** cần giấu payload khỏi ai, trong luồng nào; tách confidentiality khỏi integrity, authentication, authorization và replay.
2. **Giảm claims trước:** không đưa mật khẩu, secrets, PII không cần thiết hay toàn bộ ACL vào token.
3. **Phân biệt định dạng:** Base64URL/JWS không mã hóa; JWE mã hóa payload; opaque token không mang claims đọc trực tiếp.
4. **Không bỏ TLS:** mọi token, Client authentication, JWKS/metadata, token endpoint, introspection và revocation chạy qua transport đúng policy.
5. **Chọn recipient:** public encryption key phải thuộc đúng Client/Resource Server đã đăng ký đáng tin, không lấy từ request/header tùy ý.
6. **Dùng authenticated encryption:** pin JWE `alg`/`enc` được hỗ trợ, verify tag, không tự viết crypto hoặc bật RSA1_5/CBC không phù hợp.
7. **Khi cần issuer authenticity, ký trước rồi mã hóa:** inner JWS có trusted issuer signature; outer JWE chỉ tới recipient được chỉ định.
8. **Kiểm tra cả hai lớp:** outer key/alg/enc/tag và inner alg/signature/issuer/audience/type/time/nonce/scope theo profile.
9. **Không trộn keys:** AS signing private key, recipient decryption private key, Client assertion key, DPoP/mTLS key và storage KMS key có trách nhiệm khác nhau.
10. **`kid` không là secret/trust anchor:** chọn trong đúng namespace issuer/recipient, tránh duplicate/mutable alias/trust from attacker input.
11. **Phân tích bề mặt metadata:** JWE header và token length vẫn lộ; không dùng PII làm `kid` và không bật `zip` vô điều kiện.
12. **Ngăn decryption oracle:** lỗi uniform ở API, giới hạn request/CPU, rate limit, không lộ plaintext khi tag/signature fail.
13. **Bảo vệ storage/log:** ciphertext JWE cũng là credential; không log bearer token, decrypt claims, private keys hay client secrets.
14. **Giới hạn bearer replay:** TTL, audience/scope, revocation/denylist/introspection, DPoP/mTLS theo threat model.
15. **Phân biệt access/refresh/ID token:** refresh token chỉ tới AS, ID token cho RP, access token cho đúng RS và profile.
16. **Multi-tenant đúng nguồn tin cậy:** issuer/client/recipient/audience/tenant khác nhau; key không được chọn nhầm qua ID trùng.
17. **Plan key rotation:** pre-register public key mới, đồng bộ issuer, giữ old private decrypt key trong overlap hợp lệ, retire theo TTL/retention.
18. **Xử lý compromised key:** private decryption leak và signing-key leak có hậu quả khác; có runbook revoke/reissue/purge cache.
19. **Hiểu support của framework:** Spring JWT decoder JWS thông thường không tự trở thành JWE decoder; dùng adapter được review hoặc opaque introspection.
20. **Kiểm thử cả trường hợp sai:** wrong key, wrong recipient, invalid tag, malicious header, unsigned inner token, bad audience, stale claims, replay, outage.
21. **Kiểm tra object-level authorization:** dù decrypt/signature đúng, RS vẫn phải kiểm tra chủ sở hữu/tenant/quyền trên từng tài nguyên.
22. **Audit trung thực:** “đã mã hóa” không có nghĩa “không thể sao chép” hoặc “không ai ngoài người dùng đọc được”; chỉ mô tả đúng phạm vi trust và key holders.

## Ghi nhớ

**Token cần confidentiality khi có người phải giữ/chuyển tiếp token nhưng không được phép đọc dữ liệu trong payload**, hoặc khi profile/chính sách yêu cầu bảo vệ claims khỏi các bên không phải recipient. **JWS ký token không mã hóa claims**: Base64URL có thể decode. **JWE mã hóa payload** cho recipient có private decryption key và dùng authenticated encryption, nhưng vẫn để lộ một số header/độ dài và **không chống bearer replay**. Khi cần cả confidentiality và xác thực issuer, một mẫu quan trọng là **ký JWS bằng private key của AS, sau đó mã hóa JWS trong JWE bằng public encryption key của recipient; recipient decrypt và verify inner signature rồi kiểm tra issuer, audience, token type, expiry, nonce/scope và quyền owner/tenant**. Hãy ưu tiên **giảm claims, opaque token/introspection hoặc BFF** nếu chúng đạt mục tiêu đơn giản hơn. JWE không thay HTTPS, secure storage, log redaction, refresh-token rotation, revocation, sender binding hay business authorization. **Khóa giải mã bị lộ có thể làm mất bí mật của ciphertext đã thu thập; khóa ký bị lộ có thể cho phép tạo token giả** — phải quản lý hai vòng đời và xử lý sự cố tách biệt.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [OpenID Connect Core 1.0 — ID Tokens, signing and encryption](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html)
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Nimbus JOSE + JWT — Documentation](https://connect2id.com/products/nimbus-jose-jwt)
