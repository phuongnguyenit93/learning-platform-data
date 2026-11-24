# Recipient và key agreement

## 1. Vì sao mã hóa token phải biết chính xác *ai* được giải mã?

Trong chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học **Recipient và key agreement** giải thích cách một **JSON Web Encryption (JWE)** dùng thuật toán quản lý khóa để chỉ những bên nhận phù hợp mới có thể khôi phục **Content Encryption Key (CEK)** rồi giải mã token.

Giả sử Authorization Server (AS) phát một JWT access token chứa những claims chỉ dành cho **Orders API**. Do yêu cầu bí mật, AS cần mã hóa token bằng JWE:

~~~text
Authorization Server                 Orders API
      |                                 |
      |-- biết public key của Orders -->|
      |                                 |-- giữ private key tương ứng
      |
      |-- JWE(ciphertext, key metadata, ...)
      |-------------------------------->|
      |                                 |-- key agreement / unwrap CEK
      |                                 |-- decrypt + authenticate ciphertext
      |                                 |-- validate claims/authorization
~~~

JWE không tự biết “Orders API” chỉ nhờ chuỗi tên trong header. Bên gửi phải chọn **khóa của recipient** từ một nguồn tin cậy và theo chính sách định tuyến/token audience; bên nhận phải **giữ đúng private key hoặc secret** và kiểm ciphertext cùng toàn bộ claims sau khi giải mã.

Ví dụ có hai API:

~~~text
Orders API:  recipient key R_orders
Billing API: recipient key R_billing

AS mã hóa CEK cho R_orders.

Orders API:
    có private R_orders -> mở được CEK -> đọc claims.

Billing API:
    chỉ có private R_billing -> không mở được CEK.
~~~

Điều này giới hạn quyền **đọc nội dung mã hóa** theo khóa của recipient. Tuy nhiên, **giải mã được không đồng nghĩa được phép xử lý request**: Orders API vẫn phải kiểm `iss`, `aud`, `exp`, token type, scope, subject và quyền trên từng order.

> **Nguyên tắc:** *Recipient xác định ai được mở lớp mã hóa; token audience và business authorization xác định token có được dùng ở API và tài nguyên nào.*

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **recipient**, **sender/originator**, **key agreement**, **key transport**, **key wrapping**, **content encryption** và **authentication**.
2. Đọc cấu trúc JWE Compact/JSON Serialization, hiểu `alg`, `enc`, `kid`, `epk`, `apu`, `apv`, `encrypted_key`, `iv`, `ciphertext` và `tag`.
3. Mô tả ECDH-ES: sender dùng ephemeral private key với recipient static public key, recipient dùng static private với ephemeral public; hai bên thu được shared secret và chạy **Concat KDF**.
4. Phân biệt `ECDH-ES` **direct agreement** với `ECDH-ES+A256KW` **agreement + wrapping**.
5. Giải thích khi nào JWE có **một** hay **nhiều recipients**, vì sao JSON General Serialization phù hợp nhiều người nhận còn Compact chỉ hỗ trợ một.
6. So sánh ECDH-ES với `RSA-OAEP-256`, `dir`/shared symmetric secret và các thuật toán quản lý CEK khác.
7. Thiết kế recipient-key registry, key rotation, KMS/HSM, bảo vệ public-key provenance và loại bỏ các thuật toán không được phép.
8. Phân biệt **bảo mật nội dung** và **xác thực người phát hành** trong JWT/OIDC/OAuth 2.0; không nhầm JWE với chữ ký JWS.
9. Kiểm thử cấu hình Java/JWE và các lỗi invalid curve, wrong recipient, stale key, cross-tenant access hoặc decrypt oracle.

## 2. Các vai trò và lớp khóa trong JWE

### 2.1. Ai là originator, ai là recipient?

- **Originator/sender:** bên tạo thông điệp JWE, ví dụ AS khi phát encrypted JWT cho Orders API.
- **Recipient:** bên được thiết kế để giải mã thông điệp, ví dụ Orders API hoặc một Relying Party (RP) nhận encrypted OIDC ID token.
- **Recipient public key:** khóa công khai do recipient đăng ký/phân phối qua kênh đáng tin để sender sử dụng.
- **Recipient private key:** bí mật chỉ recipient hoặc KMS/HSM của recipient có quyền sử dụng.
- **CEK:** khóa đối xứng dùng cho thuật toán mã hóa nội dung `enc`.
- **Key Management Algorithm (`alg`):** cơ chế tạo, thỏa thuận, vận chuyển hoặc bọc CEK để đúng recipient có thể mở.
- **Content Encryption Algorithm (`enc`):** thuật toán mã hóa nội dung và xác minh tính toàn vẹn, ví dụ `A256GCM`.

### 2.2. Hai bước độc lập: quản lý CEK và mã hóa claims

~~~text
                      KEY MANAGEMENT (alg)
               +--------------------------------+
Recipient key ->| Agreement / wrap / transport   |-> CEK dùng cho recipient
               +--------------------------------+
                                                  |
                                                  v
                      CONTENT ENCRYPTION (enc)
               +--------------------------------+
Claims bytes ->| AEAD Encrypt with CEK           |-> ciphertext + tag
               +--------------------------------+
~~~

Ví dụ một JWE có:

~~~json
{
  "alg": "ECDH-ES+A256KW",
  "enc": "A256GCM",
  "kid": "orders-enc-2026-11"
}
~~~

- `ECDH-ES+A256KW`: ECDH tạo khóa bọc CEK; AES Key Wrap bọc CEK.
- `A256GCM`: dùng CEK 256-bit để mã hóa và xác thực **nội dung**.
- `kid`: gợi ý chọn khóa trong một **trusted recipient key set**; không phải chứng cứ sender đáng tin.

**Không đồng nhất `alg` với `enc`.** Thay `A256GCM` không có nghĩa đổi từ ECDH sang RSA; thay `ECDH-ES+A256KW` không tự làm AES-GCM mạnh hơn.

### 2.3. Key Agreement khác Key Transport

| Cơ chế | Ví dụ JOSE | Cách CEK được xử lý |
|---|---|---|
| **Key agreement trực tiếp** | `ECDH-ES` | Sender/recipient cùng suy ra **CEK** từ ECDH + KDF |
| **Agreement + key wrapping** | `ECDH-ES+A256KW` | Hai bên suy ra **KEK**, CEK ngẫu nhiên được bọc bằng KEK |
| **Key encryption / transport** | `RSA-OAEP-256` | Sender tạo CEK rồi mã hóa CEK bằng RSA public key của recipient |
| **Symmetric key wrap** | `A256KW` | CEK được bọc bằng shared symmetric KEK đã phân phối an toàn |
| **Direct shared symmetric** | `dir` | Shared secret trực tiếp làm CEK theo quy tắc thuật toán |

Một token **không thể được giải mã** chỉ vì người nhận biết `alg`/`enc`; họ cần đúng key material và xử lý đúng tất cả các tham số.

### 2.4. Một recipient có thể là một *service*, không nhất thiết một người dùng

Trong token security, recipient thường là:

- **Resource Server** cần đọc JWT access token đã mã hóa.
- **OIDC client/Relying Party** cần đọc encrypted ID token theo registration.
- **BFF** giữ private decryption key; browser chỉ giữ HTTP session cookie.
- **Gateway** có trách nhiệm giải mã đã được kiến trúc cho phép.
- **Một workload/service account** có HSM key để xử lý confidential claims.

Không mặc định người dùng cuối có private key để mở JWE, và đừng phát private decryption key cho SPA/browser chỉ để giải mã token ở frontend nếu kiến trúc yêu cầu bí mật tại server.

## 3. JWE trông như thế nào?

### 3.1. JWE Compact Serialization có năm thành phần

~~~text
BASE64URL(protected header)
    .
BASE64URL(encrypted key)
    .
BASE64URL(iv)
    .
BASE64URL(ciphertext)
    .
BASE64URL(authentication tag)
~~~

Ví dụ về **hình dạng**, không phải token thực:

~~~text
<PROTECTED_HEADER_B64>.<ENCRYPTED_KEY_B64>.<IV_B64>.<CIPHERTEXT_B64>.<TAG_B64>
~~~

Phần thứ hai **có thể rỗng** trong direct key agreement `ECDH-ES` hoặc `dir`, bởi vì không có CEK được bọc rồi vận chuyển trong trường đó.

**Một JWE Compact không hỗ trợ nhiều recipients.** JWE General JSON Serialization mới có trường `recipients` để mô tả nhiều recipient-specific encrypted keys (RFC 7516, mục 7.1–7.2).

### 3.2. JWE Compact và JWS Compact rất dễ bị nhầm

~~~text
JWS Compact:  header.payload.signature
                3 segments

JWE Compact:  protected.encrypted_key.iv.ciphertext.tag
                5 segments
~~~

Đếm segment **chỉ là dấu hiệu định dạng**, không chứng minh token hợp lệ hoặc được phát hành bởi đúng AS. JWT đã giải mã có thể cần xác minh **JWS bên trong** nếu profile dùng nested JWT.

### 3.3. Protected header chứa tham số cần cho xử lý

Ví dụ header cho recipient có EC key P-256:

~~~json
{
  "alg": "ECDH-ES+A256KW",
  "enc": "A256GCM",
  "kid": "orders-key-v4",
  "epk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<EPHEMERAL_PUBLIC_X>",
    "y": "<EPHEMERAL_PUBLIC_Y>"
  }
}
~~~

Header ở dạng JSON trước khi được Base64url encode thành protected header. `epk` là **public**, **không** được chứa ephemeral private key như trường `d`; `kid` giúp recipient tìm đúng private key trong registry.

Đừng ghi nhầm `epk` là “public key lâu dài của sender”: đây là **ephemeral public key được tạo cho key agreement operation**, thông thường thay đổi ở mỗi lần mã hóa.

### 3.4. `encrypted_key` và `ciphertext` khác nhau

Với `ECDH-ES+A256KW`:

~~~text
encrypted_key = Wrap(KEK, CEK)
ciphertext   = Encrypt_A256GCM(CEK, plaintext)
tag          = Authentication tag của A256GCM
~~~

Với `ECDH-ES` trực tiếp:

~~~text
CEK          = ConcatKDF(ECDH shared secret, info for enc)
encrypted_key = empty
ciphertext   = Encrypt_A256GCM(CEK, plaintext)
~~~

Không dùng AES-GCM authentication tag để “chứng minh AS là người gửi”: tag chứng minh tính toàn vẹn dưới CEK, còn việc **ai được phép tạo thông điệp và ai phát hành token** là bài toán xác thực sender và token claims độc lập.

## 4. Recipient không phải `aud`: hai ranh giới bảo mật khác nhau

Giả sử Orders API có private key `R_orders_private`, Billing API có `R_billing_private`.

**Recipient binding:**

~~~text
JWE được mã hóa cho R_orders_public.
Chỉ bên kiểm soát R_orders_private có khả năng mở lớp CEK
(giả định key material chưa bị lộ và thuật toán được dùng đúng).
~~~

**Audience binding:**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "scope": "orders:read",
  "exp": 1893495600
}
~~~

`aud` là claim chỉ ra intended recipient/resource audience **trong semantics của token**. Public key dùng cho JWE lại là **cryptographic decryption recipient**. Một bên có thể được cấp quyền giải mã nhưng **không phải audience hợp lệ** cho nội dung.

### 4.1. Ví dụ đúng và sai

| Tình huống | Có mở được CEK? | Có được chấp nhận access token không? |
|---|---|---|
| Orders giữ private R_orders, `aud=Orders` | Có thể | Chỉ khi chữ ký/claims/quyền còn hợp lệ |
| Orders giữ private R_orders, `aud=Billing` | Có thể | **Không**: sai audience |
| Billing chỉ giữ R_billing, JWE mã hóa cho Orders | Thông thường không | Không |
| Gateway có cả R_orders và R_billing | Có thể mở cả hai | Phải enforce audience và security boundary downstream |
| Attacker chiếm R_orders_private | Có thể mở JWE cho Orders | Không tự có quyền ký token hợp lệ hoặc được cấp quyền trên resource |

Một thiết kế **shared decryption key** cho cả Orders và Billing có thể làm hai services cùng đọc được token. Nếu separation là yêu cầu bảo mật, **tách recipient keys** thay vì chỉ dựa vào việc token có `aud`.

### 4.2. Không coi `kid` là authorization

`kid=orders-key-v4` chỉ là một **key identifier** được parse từ JOSE header. Recipient vẫn phải:

1. Ánh xạ `kid` **trong key registry đã biết và đúng tenant/issuer/context**.
2. Kiểm `alg`, `enc`, curve, key use và key lifecycle status được phép.
3. Không để caller tự chọn private key của tenant khác để thử giải mã.
4. Chỉ trả kết quả cho service/user có thẩm quyền sau khi validate token.

`kid` trong token chưa xác minh **không được dùng để fetch arbitrary JWK URL hoặc truy cập mọi private keys trong KMS**.

## 5. ECDH-ES: hai bên thỏa thuận một bí mật chung mà không gửi private key

**ECDH-ES (Elliptic Curve Diffie–Hellman Ephemeral Static)** là key agreement mechanism được định nghĩa trong **RFC 7518, mục 4.6** và được mở rộng cho các đường cong như X25519 bởi **RFC 8037**.

### 5.1. Những khóa nào được dùng?

**Recipient** (Orders API) có cặp khóa *static*:

~~~text
R_private:  private key dài hạn, bảo vệ ở Orders/KMS/HSM.
R_public:   public key đã đăng ký, AS biết để mã hóa.
~~~

**Sender** (AS) tạo cặp khóa *ephemeral* mới cho **mỗi key agreement operation**:

~~~text
E_private:  ephemeral private key, chỉ dùng tạm khi mã hóa.
E_public:   ephemeral public key, đặt trong JWE header `epk`.
~~~

Các phép tính khái niệm:

~~~text
AS:
    shared secret Z = ECDH(E_private, R_public)

Orders API:
    shared secret Z = ECDH(R_private, E_public)

Về toán học:
    hai bên có cùng Z nếu keys/curve/parameters đúng.
~~~

Không bên nào phải gửi private key của mình qua mạng. `epk` là **public** và được gửi cùng JWE.

### 5.2. Sơ đồ luồng ECDH-ES

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant K as Trusted recipient registry
    participant RS as Orders API
    AS->>K: Lấy R_public đúng audience/recipient
    K-->>AS: R_public + keyId + policy
    AS->>AS: Generate fresh E_private/E_public
    AS->>AS: Z = ECDH(E_private, R_public)
    AS->>AS: CEK hoặc KEK = ConcatKDF(Z, JOSE parameters)
    AS->>AS: Encrypt content with CEK
    AS-->>RS: JWE gồm protected header, epk, ciphertext, tag
    RS->>RS: Lookup trusted private R_private
    RS->>RS: Z = ECDH(R_private, E_public)
    RS->>RS: Derive CEK hoặc KEK, decrypt + verify tag
    RS->>RS: Verify signed issuer/token claims + policy
~~~

**ECDH tạo shared secret nhưng bản thân nó không mã hóa payload.** CEK/KEK cần được suy ra qua **Concat KDF**, rồi dùng thuật toán JWE đã thỏa thuận.

### 5.3. Concat KDF: không sử dụng trực tiếp raw ECDH Z

Theo RFC 7518, ECDH-ES trong JOSE sử dụng **Concat KDF với SHA-256**. KDF lấy shared secret Z và những trường ngữ cảnh, trong đó có:

- **AlgorithmID:** tên `enc` ở chế độ direct; tên `alg` ở chế độ key wrapping.
- **PartyUInfo:** metadata bên originator từ `apu` (nếu có).
- **PartyVInfo:** metadata bên recipient từ `apv` (nếu có).
- **SuppPubInfo:** độ dài key cần suy ra tính bằng bit.
- **SuppPrivInfo:** thông thường rỗng trong profile JOSE tương ứng.

Mô tả khái niệm:

~~~text
Derived key = ConcatKDF_SHA256(
    Z,
    AlgorithmID,
    PartyUInfo,
    PartyVInfo,
    keyLengthBits
)
~~~

Đoạn trên **không phải mã thuật toán có thể copy để triển khai**; RFC 7518 quy định cách đóng gói độ dài và dữ liệu bytes một cách chính xác. Ví dụ thay `ConcatKDF` bằng `SHA256(Z)` hoặc một hàm HKDF generic không có đúng JOSE context có thể gây lỗi tương thích và phân tách khóa.

**Dùng thư viện JOSE đã được kiểm tra**, không tự viết Concat KDF/ECDH trên lớp application chỉ vì kết quả “trông giống 32 bytes”.

### 5.4. Khóa ephemeral có tác dụng gì?

AS sinh **E_private/E_public mới** cho mỗi key agreement operation, giúp tránh dùng lặp một sender key tĩnh trong mô hình ECDH-ES và phù hợp yêu cầu RFC 7518.

Điều này **không đồng nghĩa JWE ECDH-ES có forward secrecy hoàn chỉnh**. Nếu một ngày **recipient static private R_private bị lộ**, attacker giữ các JWE cũ chứa `epk` có thể tính lại shared secret Z và giải mã những ciphertext đã thu thập, trong những điều kiện tương ứng.

~~~text
JWE cũ có E_public trong epk.
Sau đó R_private bị lộ.
Attacker tính ECDH(R_private, E_public) -> Z.
Attacker suy ra CEK/KEK theo public JOSE params.
=> Confidentiality của các JWE lưu trước đó có thể bị ảnh hưởng.
~~~

Vì vậy bảo vệ recipient private key, lưu trữ ciphertext, rotation/re-encryption và thời hạn dữ liệu là thiết yếu. Không hứa “ephemeral sender key khiến mọi JWE lịch sử vẫn bí mật nếu recipient key lộ”.

### 5.5. Direct ECDH không xác thực sender

Recipient có R_public, và public key này **có thể được phân phối cho nhiều bên được phép gửi**. Bất kỳ ai có R_public có thể tạo ephemeral key, ECDH shared secret tương ứng và tạo **một JWE giải mã được** cho Orders API.

Điều đó chứng minh **recipient decryptability**, không chứng minh “AS đã phát hành JWT”:

~~~text
Attacker biết Orders API public key.
Attacker tự tạo JWE chứa {"sub":"admin"}.
Orders API giải mã được và AEAD tag hợp lệ.

Nếu Orders API tin claims ngay: NGUY HIỂM.
~~~

Muốn xác thực issuer, có thể dùng **signed JWT (JWS) bên trong encrypted JWE** rồi kiểm chữ ký của JWS, hoặc cơ chế độc lập được profile tin cậy quy định. **JWE encryption/authentication tag không thay xác minh chữ ký phát hành token**.

## 6. `ECDH-ES` direct agreement: CEK được suy ra trực tiếp

Với:

~~~json
{
  "alg": "ECDH-ES",
  "enc": "A256GCM",
  "kid": "orders-enc-v4",
  "epk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<EPHEMERAL_X>",
    "y": "<EPHEMERAL_Y>"
  }
}
~~~

đầu ra Concat KDF là **CEK 256-bit** vì `enc=A256GCM` cần CEK tương ứng. Sender không tạo CEK độc lập rồi wrap; thay vào đó:

~~~text
Z = ECDH(E_private, R_public)

CEK = ConcatKDF(Z,
                AlgorithmID="A256GCM",
                keyLength=256 bits,
                PartyUInfo/PartyVInfo)

IV = fresh IV phù hợp A256GCM
ciphertext, tag = AEAD_Encrypt(CEK, IV, plaintext, AAD)

JWE encrypted_key = empty
~~~

### 6.1. Vì sao segment thứ hai trống?

JWE Compact:

~~~text
protected-header..iv.ciphertext.tag
                  ^^
               empty encrypted_key
~~~

CEK không xuất hiện dưới dạng ciphertext được wrap bởi KEK; hai bên **tự suy ra** cùng CEK từ ECDH/KDF.

**Không nhầm chuỗi rỗng với CEK rỗng.** CEK thực được suy ra có độ dài phù hợp thuật toán, còn phần serialization của `encrypted_key` rỗng theo key agreement mode.

### 6.2. Những điều kiện phải đúng

1. Recipient có private key khớp `kid`/key material được phép.
2. `epk` hợp lệ, đúng curve, là public key và vượt qua kiểm validation.
3. Recipient tính ECDH và Concat KDF đúng theo RFC.
4. `enc` tương thích với độ dài CEK.
5. `iv`, protected header/AAD và tag được xác minh.
6. Plaintext sau decrypt vẫn phải qua **issuer/claim validation** nếu nó là token.

### 6.3. Trường hợp sử dụng

`ECDH-ES` direct thích hợp cho **một recipient** theo các profile/library hỗ trợ, không cần key wrapping riêng. Nhưng khi muốn **một ciphertext dùng chung cho nhiều recipients**, direct agreement khó dùng bởi CEK được suy ra phụ thuộc từng recipient. Khi đó thường chọn **agreement + key wrapping** với CEK chung.

## 7. `ECDH-ES+A256KW`: thỏa thuận KEK, bọc CEK

Trong chế độ này, AS tạo **CEK ngẫu nhiên** để mã hóa content, còn ECDH + Concat KDF tạo **Key Encryption Key (KEK)** dành riêng cho recipient để bọc CEK.

~~~json
{
  "alg": "ECDH-ES+A256KW",
  "enc": "A256GCM",
  "kid": "orders-enc-v4",
  "epk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<EPHEMERAL_X>",
    "y": "<EPHEMERAL_Y>"
  }
}
~~~

### 7.1. Trình tự ở sender

~~~text
1. Generate random CEK, length = 256 bits cho A256GCM.
2. Generate fresh ephemeral EC keypair E.
3. Z = ECDH(E_private, R_public).
4. KEK = ConcatKDF(Z,
                   AlgorithmID="ECDH-ES+A256KW",
                   keyLength=256 bits,
                   PartyUInfo/PartyVInfo).
5. encrypted_key = AES-KW-Wrap(KEK, CEK).
6. ciphertext, tag = A256GCM_Encrypt(CEK, plaintext, AAD, IV).
7. Serialize JWE với `epk`, encrypted_key, iv, ciphertext, tag.
~~~

### 7.2. Trình tự ở recipient

~~~text
1. Parse + validate JWE structure, allowed alg/enc/header.
2. Chọn đúng private R_private từ trusted recipient registry.
3. Verify E_public/epk đúng curve và public-key validity.
4. Z = ECDH(R_private, E_public).
5. KEK = cùng ConcatKDF với AlgorithmID, apu, apv, key length.
6. CEK = AES-KW-Unwrap(KEK, encrypted_key).
7. plaintext = A256GCM_Decrypt(CEK, iv, ciphertext, AAD, tag).
8. Validate signed issuer, audience, expiry, scope, business policy.
~~~

### 7.3. So sánh direct và wrapping

| Thuộc tính | `ECDH-ES` | `ECDH-ES+A256KW` |
|---|---|---|
| KDF output | CEK trực tiếp | KEK 256-bit |
| AlgorithmID trong KDF | `enc` (ví dụ `A256GCM`) | `alg` (`ECDH-ES+A256KW`) |
| CEK do sender tạo random độc lập | Không, CEK suy ra | Có |
| Trường `encrypted_key` | Rỗng | AES-KW wrapped CEK |
| Phù hợp multi-recipient với cùng ciphertext | Không phải lựa chọn tự nhiên | Phù hợp hơn khi mỗi recipient có wrapped CEK |
| Đòi hỏi ECDH recipient key | Có | Có |
| Yêu cầu kiểm sender identity riêng | Có | Có |

**`A256KW` trong tên `alg` là AES Key Wrap dùng cho CEK, không phải `A256GCM` dùng mã hóa plaintext.** Hai thuật toán có mục đích khác nhau.

### 7.4. Vì sao cách này phù hợp nhiều recipients?

Sender có thể:

~~~text
Generate CEK C (một lần)          --> Encrypt plaintext (một lần)
             |
             +--> Wrap C cho Orders với KEK_Orders
             |
             +--> Wrap C cho Billing với KEK_Billing
             |
             +--> Wrap C cho Audit với KEK_Audit
~~~

JWE JSON General Serialization chứa **một ciphertext/tag** và nhiều recipient-specific wrapped CEKs. Mỗi recipient có thể giải CEK **C chung** bằng private key của mình.

Điều này có nghĩa **tất cả recipients được cấp CEK đều đọc cùng plaintext**, không phải mỗi người nhận thấy một phần claims riêng.

## 8. `epk`, `apu`, `apv`, `kid` và các header cần hiểu đúng

### 8.1. `epk` chứa public key ephemeral

Một JWE dùng ECDH-ES **phải** có `epk` và bên nhận phải hiểu/xử lý tham số đó theo RFC 7518.

~~~json
{
  "epk": {
    "kty": "OKP",
    "crv": "X25519",
    "x": "<EPHEMERAL_PUBLIC_X25519_BASE64URL>"
  }
}
~~~

Với `crv=X25519`, đây là JWK dạng **OKP** theo RFC 8037, không phải `kty=EC` và không có cặp tọa độ P-256 `x/y`.

**Không bao giờ gửi** private ephemeral key hoặc recipient private key trong `epk`; nếu header có `d` hay private-key parameters, validator phải từ chối theo profile.

### 8.2. `apu`: Agreement PartyUInfo

`apu` là optional base64url-encoded metadata về originator trong key derivation context:

~~~json
{
  "apu": "c2VuZGVyLUE"
}
~~~

Đây là Base64url của ví dụ “sender-A”, **không phải chữ ký của sender**. Attacker gửi một JWE riêng có thể đặt giá trị `apu` theo ý mình, vì vậy không nên dùng `apu` như bằng chứng **sender authentication** hoặc quyền phát hành token.

### 8.3. `apv`: Agreement PartyVInfo

`apv` là optional base64url-encoded metadata về recipient; nếu dùng, hai bên phải xử lý giống nhau trong KDF:

~~~json
{
  "apv": "b3JkZXJzLWFwaQ"
}
~~~

Ví dụ giải mã thành “orders-api”. Đây là **KDF context**, không phải thay thế recipient key selection hay `aud` claim của JWT.

### 8.4. Không biến `apu`/`apv` thành câu trả lời cho authorization

| Giá trị | Dùng để | Không được suy ra |
|---|---|---|
| `epk` | Public key ephemeral để recipient tính ECDH | Sender đã được xác thực |
| `apu` | KDF PartyUInfo | AS chắc chắn là nguồn phát token |
| `apv` | KDF PartyVInfo | Token được phép dùng ở audience đó |
| `kid` | Tìm ứng viên recipient key trong trusted set | Caller có quyền truy cập private key đó |
| `alg` | Cách tạo/transport/wrap CEK | Đủ bảo vệ plaintext nếu `enc` sai |
| `enc` | Content encryption algorithm | Khóa recipient nào cũng có quyền mở |

Nếu client gửi `apv=admin`, điều đó không cấp role admin. Nếu gửi `kid` của tenant khác, key resolver phải chặn cross-tenant access trước khi thử private key.

### 8.5. Protected vs unprotected JOSE headers

Trong **JWE JSON Serialization**, header có thể gồm:

- **Protected header:** được ràng buộc bởi authentication tag của JWE.
- **Shared unprotected header:** được dùng chung nhưng không được integrity-protected.
- **Per-recipient unprotected header:** riêng recipient nhưng không được integrity-protected.

Các tên header ở ba vị trí phải **không trùng nhau** theo RFC 7516. Với những tham số ảnh hưởng security decision, nên ưu tiên đặt trong **protected header khi profile cho phép**, hiểu rằng per-recipient header trong General JSON thường phục vụ chọn khóa/thuật toán cho từng recipient.

**Không cho phép header không được bảo vệ tự override security policy**, hay dùng một `kid` ở unprotected header làm bằng chứng người gửi có quyền phát hành token.

## 9. Một hay nhiều recipients trong JWE JSON Serialization?

JWE có ba cách serialization quan trọng:

| Cách biểu diễn | Số recipients | Đặc điểm |
|---|---:|---|
| **Compact JWE** | Một | Năm thành phần phân cách bằng dấu chấm; tiện trao đổi trong HTTP/token field |
| **Flattened JSON JWE** | Một | Object JSON có `header`, `encrypted_key` ở top level |
| **General JSON JWE** | Một hoặc nhiều | Array `recipients`, mỗi recipient có header và encrypted key riêng |

**General JSON** không có nghĩa mỗi recipient đọc một đoạn plaintext khác nhau. Tất cả được cấp quyền mở **cùng CEK và cùng ciphertext**. Đây là điểm quyết định khi gửi token chứa thông tin cá nhân hoặc đặc quyền.

### 9.1. Sơ đồ: mã hóa một lần, wrap CEK nhiều lần

~~~mermaid
flowchart TD
    P[Plaintext token / claims] --> E[A256GCM encrypt bằng CEK C]
    C[CEK C được sinh ngẫu nhiên] --> E
    C --> W1[ECDH + KEK Orders, AES-KW wrap C]
    C --> W2[ECDH + KEK Billing, AES-KW wrap C]
    C --> W3[ECDH + KEK Audit, AES-KW wrap C]
    E --> S[Shared IV + ciphertext + tag]
    W1 --> J[JWE General JSON]
    W2 --> J
    W3 --> J
    S --> J
~~~

Giải pháp này hiệu quả khi **các recipients thực sự đều được phép đọc cùng nội dung**. Nếu Orders chỉ cần `orders:read` và Billing chỉ được đọc trường khác, hãy **tạo hai payload/token riêng**, không gửi một ciphertext chứa toàn bộ dữ liệu cho cả hai rồi hy vọng họ tự bỏ qua thông tin không thuộc quyền.

### 9.2. Hình dạng JWE General JSON nhiều recipients

~~~json
{
  "protected": "<BASE64URL_OF_PROTECTED_HEADER_ENC_A256GCM>",
  "recipients": [
    {
      "header": {
        "alg": "ECDH-ES+A256KW",
        "kid": "orders-enc-v4",
        "epk": {
          "kty": "EC",
          "crv": "P-256",
          "x": "<EPK_ORDERS_X>",
          "y": "<EPK_ORDERS_Y>"
        }
      },
      "encrypted_key": "<WRAPPED_CEK_FOR_ORDERS>"
    },
    {
      "header": {
        "alg": "ECDH-ES+A256KW",
        "kid": "billing-enc-v9",
        "epk": {
          "kty": "EC",
          "crv": "P-256",
          "x": "<EPK_BILLING_X>",
          "y": "<EPK_BILLING_Y>"
        }
      },
      "encrypted_key": "<WRAPPED_CEK_FOR_BILLING>"
    }
  ],
  "iv": "<BASE64URL_IV>",
  "ciphertext": "<BASE64URL_SHARED_CIPHERTEXT>",
  "tag": "<BASE64URL_AUTHENTICATION_TAG>"
}
~~~

**Đây là cấu trúc minh họa, không phải JWE decrypt được**: `protected`, keys, IV, wrapped CEK, ciphertext và tag đều là placeholders. Trong triển khai thật, `protected` là Base64url của protected header hợp lệ chứa `enc=A256GCM`; các yêu cầu JOSE Header union, trùng tên tham số và xử lý AAD phải được thư viện thực hiện.

Lưu ý: `header` bên trong mỗi recipient là **Per-Recipient Unprotected Header** trong RFC 7516, không được integrity-protected như protected header. Đừng đặt những điều kiện authorization quan trọng chỉ dựa vào header đó. Tampering thường khiến key agreement/AEAD verification fail, nhưng điều này không làm header trở thành lời khai danh tính sender.

### 9.3. Sử dụng ephemeral public key cho từng recipient

Đối với ECDH-ES, cần một ephemeral keypair mới cho mỗi key agreement operation. Khi bọc CEK cho Orders và Billing, sender có thể tạo **ephemeral keypair riêng cho từng phép thỏa thuận** và cung cấp `epk` tương ứng trong per-recipient header.

~~~text
Orders:
    E_orders_private + R_orders_public -> Z_orders -> KEK_orders.

Billing:
    E_billing_private + R_billing_public -> Z_billing -> KEK_billing.

CEK C:
    same CEK wrapped independently by both KEKs.
~~~

Không tái sử dụng ephemeral private key một cách vô thức để “tối ưu performance”; cần tuân thủ thư viện và thuật toán chuẩn.

### 9.4. Recipient mismatch và nguyên tắc không trộn keys

Nếu Orders chỉ có `R_orders_private`, nó thử unwrap `encrypted_key` dành cho Billing thì phải thất bại. Một implementation không được thử **mọi private key của tất cả tenants** để tìm khóa nào giải mã được nếu việc đó vượt ranh giới quyền truy cập.

Khuyến nghị:

1. Xác định **expected issuer, tenant, recipient service** từ ngữ cảnh request đáng tin.
2. Từ đó chọn **allowed recipient key set**.
3. Dùng `kid` làm key hint **bên trong tập đã cho phép**, không để token chọn tập key.
4. Giới hạn số recipients/keys được thử; tránh DoS khi payload có hàng nghìn recipient entries.
5. Không trả thông tin key existence hay chi tiết “key tenant B giải mã đúng” cho caller chưa được xác thực.

### 9.5. Multi-recipient có làm “broadcast” được một access token?

Về mật mã, nhiều recipients có thể đọc cùng plaintext. Nhưng **OAuth resource audiences** có thể khác nhau:

~~~text
One JWE plaintext:
    aud = Orders

Recipients:
    Orders, Billing
~~~

Billing có thể decrypt nếu có wrapped CEK, **nhưng phải từ chối** vì `aud` không cho Billing. Muốn token hợp lệ cho nhiều resource servers cần **audience/scope/token profile được AS cấp rõ ràng**, và phải đánh giá nguy cơ token replay/confused deputy. Không thêm recipient Billing như một cách âm thầm mở rộng quyền.

### 9.6. Thêm recipient sau khi phát hành JWE

Về mặt dữ liệu, thêm recipient đòi hỏi có CEK hoặc cơ chế đủ quyền để wrap lại CEK. **Bất kỳ ai có CEK có thể mở plaintext và có khả năng tạo recipient entry mới** theo profile; vì thế quyền CEK cũng là quyền cấp truy cập nội dung.

Không cho phép một service có private key được tự bổ sung recipients không được phê duyệt. Nếu yêu cầu đổi phạm vi chia sẻ, nên có **authorization decision mới, audit và re-encryption/rewrapping workflow** đáng tin.

## 10. Sender authentication: JWE không thay thế JWS

### 10.1. Ai cũng có thể mã hóa tới public recipient key

Nếu Orders API công bố `R_orders_public`, bất kỳ bên nào nhận được public key có thể tạo JWE để Orders mở. Điều đó rất hữu ích vì **sender không cần biết private key**, nhưng cũng có nghĩa:

~~~text
JWE AEAD tag hợp lệ
    => ciphertext không bị thay đổi dưới CEK tương ứng.

JWE decrypt thành công
    => recipient có thể mở nội dung.

JWE decrypt thành công
    != token do AS phát hành hợp lệ.
~~~

Ngay cả với `ECDH-ES+A256KW`, key agreement dùng **ephemeral sender key** không tự xác thực sender lâu dài. `apu` chỉ là KDF context, không phải một chữ ký.

### 10.2. Sign then encrypt cho JWT cần bảo vệ nguồn phát hành

Một mô hình thường được dùng cho **nested JWT**:

~~~text
AS:
    JWT Claims
        |
        v
    JWS = Sign(AS_private_signing_key, claims)
        |
        v
    JWE = Encrypt(Recipient_public_key, JWS)
        |
        v
    Recipient
        |
        v
    Decrypt JWE
        |
        v
    Verify inner JWS signature + issuer + aud + exp + scope
        |
        v
    Business authorization
~~~

Với nested JWT, outer JWE thường dùng header `cty: "JWT"` để biểu diễn payload là JWT khác, theo profile. Hệ thống vẫn phải kiểm **inner signed token** và key issuer từ một trust source độc lập.

### 10.3. Tại sao thứ tự quan trọng?

**Sign then encrypt** cho phép:

- Bên nhận mở ciphertext, biết claims không bị sửa do AEAD.
- Bên nhận kiểm JWS để xác thực issuer đã ký claims.
- Nội dung JWS không lộ cho người quan sát đường truyền chỉ có outer ciphertext.

Nhưng nếu một ứng dụng **decrypt xong bỏ qua verify JWS** thì encryption chỉ che nội dung, không xác thực người phát hành.

Các kiến trúc/profile khác có thể dùng các cơ chế authentication bên ngoài, nhưng phải mô tả rõ trust boundary. Không mặc định tất cả JWE đều chứa JWS bên trong; **JWE không bắt buộc lồng JWS**, và chính profile ứng dụng quyết định yêu cầu.

### 10.4. Phân biệt JWE integrity và OAuth authorization

Sau khi đã decrypt, API vẫn phải kiểm:

- `iss`: Authorization Server đã được cấu hình tin cậy.
- `aud`: tài nguyên/API được phép nhận token.
- `exp`, `nbf`, `iat`: thời hạn hợp lệ, leeway và token lifetime policy.
- `typ`/token profile: đúng access token, không phải ID token/refresh token.
- `scope`/permissions: quyền được cấp.
- `sub`, `client_id`, actor/subject khi dùng token exchange.
- Tenant, resource owner, action và các chính sách nghiệp vụ hiện thời.
- Revocation/key trust khi token/grant/session bị thu hồi.

**Không cho phép một JWE được giải mã thành công biến trực tiếp thành `Authentication` đáng tin trong Spring Security nếu chưa xác minh đúng token profile.**

### 10.5. Trường hợp không cần JWE

Một hệ thống chỉ cần chứng minh token không bị sửa, **không cần giữ bí mật claims với người đang cầm token**, có thể dùng signed JWT/JWS thay vì JWE. Token có thể còn nhạy cảm do là bearer credential, nhưng **mã hóa JWE không tự chữa rò token** và làm phức tạp phân phối private decryption keys.

Nếu AS muốn giữ claims hoàn toàn không thể đọc bởi client và RS phải tra state online, **opaque token + introspection** là một phương án khác. Quyết định phải dựa vào threat model, latency, revocation needs và data minimization chứ không phải “JWE luôn tốt hơn JWT”.

## 11. Chọn curve và validate public key trong ECDH

### 11.1. P-256 và X25519 là hai kiểu key representation khác nhau

**P-256** trong JWK thường có:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "<BASE64URL_X>",
  "y": "<BASE64URL_Y>"
}
~~~

**X25519** theo RFC 8037:

~~~json
{
  "kty": "OKP",
  "crv": "X25519",
  "x": "<BASE64URL_32_BYTE_PUBLIC_KEY>"
}
~~~

Không dùng `kty=EC`, `y` hoặc chữ ký `Ed25519` cho ECDH/X25519. **Ed25519 dùng cho signatures, X25519 dùng cho key agreement**; key types/curve/purpose không được đánh tráo dù đều thuộc họ CFRG.

### 11.2. Bên nhận phải validate `epk`

Những kiểm soát tối thiểu theo thuật toán và thư viện:

1. `epk` hiện diện, parse được, chỉ chứa public key material.
2. `kty`/`crv` nằm trong allowlist, đúng loại private key của recipient.
3. EC point hợp lệ trên đường cong được phê duyệt; không chấp nhận point tùy ý.
4. Với X25519, dùng implementation xử lý đúng các giá trị public không hợp lệ/low-order và kiểm shared secret vô nghĩa như all-zero theo guidance thư viện/curve.
5. Không chấp nhận mismatched key lengths, coordinates hay parameter encoding.
6. Không downgrade từ curve mạnh sang curve legacy theo yêu cầu của token chưa tin cậy.
7. Không để lỗi key validation lộ nội dung private key hoặc chi tiết cryptographic oracle.

**Không tự implement point validation, ECDH hay Concat KDF**. Dùng JOSE/crypto provider có hỗ trợ đầy đủ curve và được kiểm thử với malformed public key fixtures.

### 11.3. Curve negotiation phải được cấu hình trước

Ví dụ receiver policy:

~~~yaml
# Cấu hình ứng dụng minh họa, không phải Spring mặc định.
recipient:
  id: orders-api
  allowed_key_agreement_algorithms:
    - ECDH-ES+A256KW
  allowed_content_encryption_algorithms:
    - A256GCM
  allowed_recipient_curves:
    - P-256
    - X25519
  require_signed_nested_jwt: true
~~~

Chỉ bật **curve mà JWE library, KMS/HSM và platform thực sự hỗ trợ**; không giả định một Java `KeyAgreement` provider hỗ trợ mọi JOSE curve và serialization.

### 11.4. Static recipient private key compromise

Nếu `R_orders_private` bị lộ:

~~~text
Attacker có thể giải mã JWE cũ đã ghi lại và JWE mới
được mã hóa cho cùng key, nếu còn giữ các ciphertext/epk.
~~~

Key rotation sang `R_orders_v5` **không làm ciphertext cũ dưới v4 bí mật trở lại**. Cần:

- Thu hồi/chặn các private key privileges cũ và đánh giá dữ liệu đã lộ.
- Cập nhật registry/JWKS recipient public key v5.
- Chuyển sender sang mã hóa bằng key v5.
- Xử lý ciphertext còn lưu dưới v4 (re-encrypt/rewrap nếu cần, với dữ liệu/token còn sử dụng).
- Kiểm những recipients khác cùng key material hoặc HSM role bị chiếm.

Không nên coi `kid` mới nhưng public/private key bytes giống hệt là key rotation.

## 12. So sánh ECDH-ES với `RSA-OAEP-256`, `dir` và AES-KW

### 12.1. RSA-OAEP: key transport, không phải key agreement

Với `alg=RSA-OAEP-256`, sender sinh CEK, **mã hóa CEK** bằng recipient RSA public key; recipient dùng RSA private key để mở CEK:

~~~text
CEK = random content-encryption key
encrypted_key = RSA-OAEP-256-Encrypt(R_public, CEK)
ciphertext = A256GCM-Encrypt(CEK, plaintext)
~~~

Khác ECDH:

- RSA-OAEP không tạo shared secret Z từ hai cặp khóa Diffie–Hellman.
- JWE `encrypted_key` mang CEK mã hóa RSA.
- Các kiểm soát OAEP parameters, key length, padding/oracle và legacy `RSA1_5` phải được review.

**Không chọn `RSA1_5` vì “dễ tương thích”** khi có RSA-OAEP profile an toàn hơn; JWT/JWE libraries phải chặn các đường tấn công padding oracle và downgrade.

### 12.2. `dir`: dùng shared symmetric CEK trực tiếp

Với `alg=dir`, sender/recipient đã có **shared symmetric key**, và key đó là CEK theo profile `enc`:

~~~json
{
  "alg": "dir",
  "enc": "A256GCM"
}
~~~

Không có ECDH ephemeral key hay RSA encrypted CEK. Key distribution phải xảy ra qua trust channel khác trước đó. `dir` có thể đơn giản trong một trust domain, nhưng secret bị chia sẻ mở rộng số bên có khả năng giải mã **và tạo ciphertext hợp lệ**, làm phức tạp sender authentication.

### 12.3. `A256KW` thuần túy

Với `alg=A256KW`, sender và recipient dùng **shared symmetric KEK** để bọc một CEK random. Không có ECDH agreement trong operation này:

~~~text
Pre-shared KEK K
Random CEK C
encrypted_key = AES-KeyWrap(K, C)
~~~

Khác với `ECDH-ES+A256KW`, nơi KEK được **suy ra từ ECDH + KDF cho phép thỏa thuận đó**, không phải một KEK tĩnh được chia sẻ sẵn.

### 12.4. Bảng lựa chọn

| `alg` | Bên gửi cần biết | Bên nhận cần giữ | `encrypted_key` | Cân nhắc |
|---|---|---|---|---|
| `ECDH-ES` | Recipient public key | Recipient private key | Rỗng | Direct agreement; một recipient |
| `ECDH-ES+A256KW` | Recipient public key | Recipient private key | Wrapped CEK | Hữu ích cho nhiều recipients |
| `RSA-OAEP-256` | Recipient RSA public key | RSA private key | RSA-encrypted CEK | Key transport, cần OAEP đúng |
| `A256KW` | Shared KEK | Shared KEK | Wrapped CEK | Chia sẻ secret trước đó |
| `dir` | Shared CEK | Shared CEK | Rỗng | Key chung dùng trực tiếp; quản trị secret nghiêm |

Tất cả đều phải kết hợp với `enc` được cho phép, kiểm ciphertext/tag và xác thực issuer/token profile. **Không chọn thuật toán từ header token một cách không giới hạn**; sender/recipient phải có security policy và capability negotiation tin cậy.

## 13. Recipient-key registry: làm sao AS biết phải mã hóa cho khóa nào?

JWE chỉ an toàn nếu sender lấy **đúng public key của recipient thật**, không phải public key do attacker thay vào request.

### 13.1. Một cấu hình tin cậy

~~~text
Trusted Recipient Registry
    recipientId: orders-api
    tenantId: tenant-a
    expectedAudience: https://orders.example.com
    publicKeyFingerprint: F_Orders_v4
    keyId: orders-enc-v4
    keyUse: enc
    algorithmAllowlist: ECDH-ES+A256KW
    curves: P-256
    lifecycleStatus: ACTIVE
    keyPublicationSource: trusted registration
~~~

AS đưa các thuộc tính từ registration/service policy, không từ HTTP query tự khai:

~~~text
POST /token?recipientPublicKey=<ATTACKER_PUBLIC_KEY>
~~~

Nếu token endpoint cho caller gửi public key tùy ý và AS mã hóa claims nhạy cảm cho key đó, attacker chỉ cần nắm private key tương ứng để đọc. **Tự do chọn recipient là quyền truy cập dữ liệu**, không phải một tham số trang trí.

### 13.2. Các bước chọn key

1. Xác thực client/grant theo OAuth policy.
2. Xác định **resource audience** mà token được cấp cho phép.
3. Tra recipient registration đáng tin tương ứng.
4. Lấy public encryption key đang **ACTIVE** của đúng issuer/tenant/service.
5. Kiểm key purpose (`enc`), algorithm, curve, fingerprint, validity và trạng thái compromise.
6. Tạo JWE bằng thư viện đúng profile; ghi metadata không bí mật.
7. Khi decrypt, RS chọn đúng private key trong **một tập đã được phép**, không thử mọi key trên hệ thống.

Một public key có thể công khai nhưng **nguồn đăng ký nó** vẫn phải đáng tin. Không có gì ngăn attacker tạo một public key P_attacker và tự khai rằng nó là key của Orders API nếu registry không có kiểm soát.

### 13.3. Nguồn key ở OIDC và trong hệ thống nội bộ

Tùy profile/registration, public keys có thể được cung cấp từ:

- Client `jwks` hoặc `jwks_uri` đã đăng ký ở OpenID Provider/OAuth AS.
- Service registry được bảo vệ với key fingerprints/owner và change control.
- KMS/HSM public key export của recipient với attestation/metadata đáng tin.
- Một kênh phân phối certificates/trust bundles được phê duyệt.

Đừng suy rằng **một JWKS endpoint bất kỳ** được caller đưa vào là trusted. Cần ràng buộc endpoint với **đúng recipient/client registration** và xác thực thay đổi khóa. JWKS của issuer dùng **xác minh JWT signature** cũng không mặc nhiên là key set cho recipient **giải mã**.

### 13.4. Key ownership cần rõ

Ví dụ:

| Key | Thuộc ai | Có thể công bố? | Ai được dùng private key? |
|---|---|---|---|
| AS signing K_sign | Authorization Server | Chỉ public verifying key | AS/KMS signer |
| Orders encryption R_orders | Orders API | Public encryption key | Orders/KMS decryptor |
| Billing encryption R_billing | Billing API | Public encryption key | Billing/KMS decryptor |
| Shop OIDC RP encryption R_shop | Relying Party | Public encryption key đã đăng ký | Shop RP backend |
| DPoP holder D1 | OAuth client/device | Public D1 có thể xuất hiện trong proof | Client/device giữ private D1 |

**Không dùng AS signing private key làm decryption key của mọi RS**. Điều đó tăng blast radius và làm lẫn key usage. Một thành phần được phép **verify JWS** không cần private signing key; một thành phần được phép **decrypt JWE** cần private recipient key tương ứng.

## 14. Key rotation và multi-version recipient keys

Mã hóa token thành công hôm nay không có nghĩa recipient key ngày mai vẫn sẵn sàng. **Rotation và disaster recovery** phải phối hợp giữa sender, recipient và những JWE còn sống.

### 14.1. Planned rotation của recipient

~~~text
Ngày 1:
    Orders R_v4 private key ACTIVE.
    AS mã hóa JWE mới cho R_v4 public.

Ngày 2:
    Orders tạo R_v5; đăng ký R_v5 public.
    AS xác minh v5 rồi chuyển encrypt sang v5.
    Orders còn giữ R_v4 private để decrypt JWE v4 chưa hết hạn.

Ngày 3:
    Hết retention/token lifetime của các JWE v4.
    Orders retire R_v4 theo policy.
~~~

Nếu recipient xóa private R_v4 quá sớm, các JWE còn hạn đã mã hóa cho v4 **không tự trở thành decryptable bằng v5**. Key rotation phải xét **lifetime của ciphertext**, không chỉ issuer token TTL.

### 14.2. Emergency recipient key compromise

Nếu `R_v4_private` bị lộ:

1. Ngừng phát JWE mới cho R_v4, cập nhật trusted recipient registry.
2. Cấp R_v5 bằng KMS/HSM hoặc key generation process an toàn.
3. Điều tra những JWE v4 đã bị thu thập/có thể bị decrypt.
4. Quy định với JWE v4 còn hạn: từ chối, cấp token mới hoặc re-encrypt theo chính sách.
5. Không dùng same private material với `kid=v5`.
6. Cân nhắc compromise của service host/KMS role có thể ảnh hưởng cả v5 nếu chưa containment.
7. Kiểm AS/RS/JWE caches không tiếp tục chọn key v4.

**Lưu ý:** xóa R_v4 khỏi registry không thể làm một ciphertext JWE v4 đã bị ghi lại biến mất hoặc ngăn attacker đã có R_v4 private decrypt nó offline. Mục tiêu là ngừng lộ mới và giới hạn hậu quả.

### 14.3. Encrypt-key cache khác sign-key cache

- **Sender key registry/cache**: AS dùng để chọn public recipient key cho JWE mới. Nếu cache stale, AS có thể tiếp tục mã hóa cho R_v4 đã compromise.
- **Recipient private key store**: RS dùng để decrypt token đã phát. Nếu có private v4, cần chính sách có chấp nhận JWE v4 sau emergency không.
- **Issuer signing public key cache**: RS dùng xác minh inner JWS. K1 signing compromise cần distrust riêng, **không liên quan trực tiếp việc R_v4 còn decrypt được**.

Hai vòng đời signing và encryption có thể rotate ở các thời điểm khác nhau; đừng dùng một `kid` namespace duy nhất không có purpose để tra tất cả.

### 14.4. Có thể khôi phục JWE cũ bằng private key mới không?

Thông thường **không**. Nếu R_v4_private mất vĩnh viễn, còn một JWE chỉ mã hóa cho R_v4_public:

~~~text
JWE v4 ciphertext + epk -> cần đúng R_v4_private.
R_v5_private không tạo cùng ECDH shared secret.
~~~

Không giải mã được chỉ vì v5 của cùng service có cùng tên `orders-api`. Nếu nội dung còn cần giữ lâu, thiết kế backup/recovery private recipient keys, hoặc re-encrypt/rewrap khi còn khả năng sử dụng key cũ.

### 14.5. KMS/HSM và quyền sử dụng khóa

Khi recipient private key ở HSM/KMS:

- Workload được cấp quyền dùng đúng **key agreement/decrypt capability** theo thuật toán/provider.
- Không mặc định KMS nào cũng hỗ trợ ECDH-ES/JWE trực tiếp; nhiều nhà cung cấp chỉ hỗ trợ nhóm operation nhất định.
- Nếu KMS không thực hiện ECDH với recipient key non-exportable, có thể cần kiến trúc khác: app-level key trong protected execution environment, `RSA-OAEP-256` nếu được hỗ trợ, hoặc một authorized decryption service.
- Phân tách quyền Sign/Decrypt/KeyAgreement, key publication và key administration.
- Audit key use, deny unexpected tenants/services/regions.

**Không xuất private key từ HSM ra file PEM để “tương thích thư viện” mà không qua security review**; việc này có thể phá mô hình bảo vệ khóa từ đầu.

## 15. OAuth 2.0 và OIDC: nơi JWE recipient thực sự có ý nghĩa

### 15.1. Encrypted JWT access token cho Resource Server

Giả sử AS muốn giữ claims nội bộ như thông tin bảo mật, role hoặc dữ liệu giao dịch không xuất hiện rõ trong token cho client:

~~~text
AS:
    signed JWT access token
        -> encrypt as JWE cho Orders API
        -> giao cho OAuth client như access token.

OAuth client:
    có chuỗi JWE, thường không có private key Orders.

Orders API:
    decrypt JWE
    verify inner signed JWT, issuer, aud, scope, exp...
~~~

Điều này có thể giảm người có khả năng đọc claims, nhưng **client đang cầm token vẫn có thể replay bearer token** nếu RS chỉ yêu cầu Bearer. JWE **không biến bearer token thành sender-constrained token**.

Để chống token theft/replay, xem xét HTTPS, storage, short TTL, `aud`, refresh rotation, DPoP/mTLS sender constraints và revocation policy phù hợp.

### 15.2. Encrypted ID token cho OIDC Relying Party

Một OP có thể hỗ trợ **ID token encryption** theo client registration/profile:

~~~text
OP ký ID token bằng AS/OP signing key.
OP mã hóa signed ID token cho RP public encryption key.
RP backend có private decryption key.
RP decrypt, verify signature + OIDC claims.
~~~

Nếu RP có registered encryption key v4 nhưng OP nhận v5, cần rotation/registration đồng bộ. **JWE recipient của ID token là RP**, còn `aud` bên trong ID token thường là **OIDC client ID** theo profile, không phải Orders API endpoint.

Đừng gửi encrypted ID token như Bearer access token đến Resource Server. Token **đúng recipient** không đồng nghĩa **đúng token type**.

### 15.3. Nested JWT và `cty`

Ví dụ outer JWE header minh họa:

~~~json
{
  "alg": "ECDH-ES+A256KW",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "rp-enc-v5",
  "epk": {
    "kty": "OKP",
    "crv": "X25519",
    "x": "<EPHEMERAL_PUBLIC_X>"
  }
}
~~~

Khi dùng nested JWT, RP/RS cần **decrypt outer JWE và verify inner JWS**. `cty="JWT"` là tín hiệu content type/profile, không là chứng cứ chữ ký hợp lệ.

### 15.4. Opaque token và introspection là phương án khác

Một opaque token có thể là random reference:

~~~text
Client -> Resource Server: opaque T1
Resource Server -> AS introspection: T1
AS -> Resource Server: active, scope, aud, sub... (được bảo vệ)
~~~

Lúc này **không có JWE recipient/key agreement** trong access token string, nếu chính token là opaque random. Confidentiality của introspection response được bảo vệ bằng kênh HTTPS và service authentication; có thể có lớp mã hóa ứng dụng bổ sung tùy thiết kế.

JWE phù hợp khi RS cần giải mã token self-contained mà không tra AS cho mỗi request. Opaque/introspection có thể hỗ trợ revocation sớm hơn, nhưng caching/availability và caller auth cần thiết kế.

### 15.5. JWE encryption không thay consent, audience hoặc scope

Khi AS cấp token cho Orders:

1. Phải kiểm OAuth grant/client có quyền yêu cầu audience/scope đó không.
2. Chọn key Orders **vì audience đã được phê duyệt**, không vì caller tự khai `kid=orders`.
3. Tạo token claims theo authorization decision.
4. Sign/encrypt theo profile, giao token đúng channel.
5. RS decrypt, verify issuer, `aud`, thời hạn, scope và business authorization.

**Nếu sai authorization policy trước khi encrypt, mã hóa tốt không sửa được token bị cấp quá quyền.**

## 16. DPoP và mTLS: key agreement recipient khác sender constraint

Một chủ đề dễ nhầm trong module token security là “có dùng public/private keys thì đã chống được replay”.

### 16.1. JWE recipient encryption

~~~text
Sender encrypt tới R_orders_public.
Recipient dùng R_orders_private để decrypt.

Mục tiêu: confidentiality của token plaintext đối với bên ngoài.
~~~

### 16.2. DPoP sender constraint

~~~text
OAuth client giữ D_client_private.
Client tạo DPoP proof cho HTTP request.
AS/RS kiểm proof, `htm`, `htu`, `jti`, `iat`,
`ath`, key thumbprint binding theo RFC 9449.

Mục tiêu: giảm replay nếu chỉ token string bị đánh cắp.
~~~

DPoP private key thuộc **client/holder**, không phải recipient decryption key của Orders API. DPoP proof sử dụng **digital signature**, không phải ECDH-ES Concat KDF.

### 16.3. mTLS certificate-bound token

Client chứng minh kiểm soát private key tương ứng certificate qua mTLS, và access token có thể được ràng buộc với certificate thumbprint theo RFC 8705. Đây cũng là **sender constraint**, khác việc Orders API giải mã JWE bằng private key riêng.

### 16.4. Có thể kết hợp, nhưng phải kiểm riêng

~~~text
Access token T1:
    JWE encrypted to Orders API (recipient confidentiality)
    inner JWS signed by AS (issuer authenticity)
    sender-constrained via DPoP/mTLS (client proof)
    aud=Orders (resource audience)
    scope=orders:read (delegated permissions)
    owner/tenant checks at Orders (business authorization)
~~~

Các lớp giúp giải quyết **những vấn đề khác nhau**. JWE không thay DPoP; DPoP không thay JWS issuer verification; chữ ký hợp lệ không thay kiểm quyền theo đối tượng.

## 17. Java + Nimbus JOSE + JWT: mã hóa cho một recipient P-256

Trong Java, dùng một thư viện JOSE có hỗ trợ chuẩn để thực hiện **ECDH-ES + Concat KDF + AES-KW + AES-GCM**. Ví dụ dưới đây sử dụng cách đặt tên API của **Nimbus JOSE + JWT**; kiểm tra dependency/version thực tế trước khi tích hợp.

### 17.1. Nguyên tắc nhập key

Sender chỉ lấy **recipient public EC key** từ registry đã xác minh:

~~~java
// Những imports chính của ví dụ:
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.ECDHEncrypter;
import com.nimbusds.jose.crypto.ECDHDecrypter;
import com.nimbusds.jose.jwk.ECKey;
~~~

Một repository key an toàn phải trả `ECKey` công khai của đúng recipient, ví dụ:

~~~java
// Pseudocode: recipientKeys là ứng dụng tự triển khai.
ECKey recipientPublic = recipientKeys.requireTrustedActivePublicECKey(
    "orders-api",
    "tenant-a",
    "orders-enc-v4",
    "ECDH-ES+A256KW",
    "P-256"
).toPublicJWK();
~~~

Không lấy một JWK JSON tùy ý từ HTTP body hoặc đường dẫn trong header token rồi coi đó là public key Orders. **Public key không cần bí mật, nhưng danh tính chủ sở hữu public key phải được xác thực.**

### 17.2. Tạo JWE từ một signed JWT có sẵn

~~~java
// Ví dụ Nimbus API; chuỗi signedJwtCompact phải được tạo từ
// AS issuance policy đáng tin và ký bằng AS private signing key.
String signedJwtCompact = signedTokenIssuer.issueValidatedAccessToken();

JWEHeader jweHeader = new JWEHeader.Builder(
        JWEAlgorithm.ECDH_ES_A256KW,
        EncryptionMethod.A256GCM)
    .keyID("orders-enc-v4")
    .contentType("JWT")
    .build();

JWEObject jwe = new JWEObject(
    jweHeader,
    new Payload(signedJwtCompact));

// Nimbus thực hiện sinh ephemeral key, ECDH, Concat KDF,
// AES Key Wrap và A256GCM theo cấu hình tương thích.
jwe.encrypt(new ECDHEncrypter(
    recipientPublic.toECPublicKey()));

String compactJwe = jwe.serialize();
~~~

Với ECDH-ES, thư viện sẽ tạo/cung cấp `epk` phù hợp trong JOSE header khi mã hóa. **Không tự nhét `epk` từ client tùy ý** rồi thực hiện AES thủ công.

`signedTokenIssuer` và `recipientKeys` trong ví dụ là **thành phần ứng dụng minh họa**, không phải các API của Nimbus hay Spring. Kết quả `compactJwe` là token JWE; **không log nguyên token** vì nó có thể là bearer credential.

### 17.3. Decrypt ở recipient, sau đó verify inner JWS

~~~java
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.crypto.ECDHDecrypter;
import com.nimbusds.jose.jwt.SignedJWT;
import com.nimbusds.jose.jwk.ECKey;

// recipientPrivate là private EC JWK P-256 đã lấy từ protected
// key store của Orders API; không xuất ra logs.
ECKey recipientPrivate =
    protectedKeyStore.requireOwnPrivateECKey("orders-enc-v4");

JWEObject parsedJwe = JWEObject.parse(compactJwe);

// Kiểm allowed alg/enc, keyId/purpose, size limits và
// key lifecycle status TRƯỚC khi dùng private key.
recipientPolicy.requireAllowedHeader(
    parsedJwe.getHeader(),
    "orders-api",
    "ECDH-ES+A256KW",
    "A256GCM");

parsedJwe.decrypt(new ECDHDecrypter(
    recipientPrivate.toECPrivateKey()));

String innerJws = parsedJwe.getPayload().toString();
SignedJWT signedJwt = SignedJWT.parse(innerJws);

// Bắt buộc: xác minh chữ ký thật từ AS issuer trusted keys;
// tiếp đó kiểm typ, iss, aud, exp, nbf, scope và
// business authorization. Đây là pseudocode ứng dụng.
VerifiedAccessToken access =
    issuerJwtVerifier.verifyAccessToken(signedJwt, "orders-api");
authorizationPolicy.requireCanReadOrder(access, orderId);
~~~

**Đừng chỉ gọi `SignedJWT.parse(...)` rồi tin claims:** parse chỉ đọc cấu trúc; `issuerJwtVerifier` phải **xác minh inner JWS signature** và token profile đúng. Nếu application chấp nhận plaintext tự do thay vì yêu cầu nested JWS, attacker có public recipient key có thể mã hóa nội dung bất kỳ để recipient decrypt.

### 17.4. Direct ECDH-ES chỉ đổi `alg`, nhưng semantics khác

~~~java
JWEHeader directHeader = new JWEHeader.Builder(
        JWEAlgorithm.ECDH_ES,
        EncryptionMethod.A256GCM)
    .keyID("orders-enc-v4")
    .contentType("JWT")
    .build();

JWEObject directJwe = new JWEObject(
    directHeader, new Payload(signedJwtCompact));

directJwe.encrypt(new ECDHEncrypter(
    recipientPublic.toECPublicKey()));

String directCompact = directJwe.serialize();
// Dạng: protected-header..iv.ciphertext.tag
~~~

Ở direct mode, thư viện suy ra **CEK trực tiếp** từ ECDH/KDF và `encrypted_key` rỗng. Không được hiểu cùng CEK/KEK với `ECDH-ES+A256KW`, dù cả hai cùng dùng ECDH.

### 17.5. Rủi ro copy ví dụ vào production

Ví dụ minh họa **chưa chứa**:

- Trusted issuer/recipient registry thực sự, key discovery và auto rotation.
- JWT issuance grant/client/consent checks.
- JWE payload size limits, format validation, timeouts và chống decompression bombs.
- Key lifetime status, fail-closed policy và KMS/HSM access controls.
- Token revocation, `jti`/security epochs và replay/sender constraints.
- Error handling không tiết lộ key mismatch hoặc oracle.
- Logging redaction và lifecycle của private keys trong memory.

Đừng coi đây là một Spring Boot app hoàn chỉnh. Nó minh họa **đúng ranh giới sender-public / recipient-private và sau decrypt vẫn verify issuer**.

## 18. Java + Nimbus: X25519 không phải ECKey P-256

X25519 được biểu diễn bằng `OctetKeyPair` trong Nimbus:

~~~java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.X25519Encrypter;
import com.nimbusds.jose.crypto.X25519Decrypter;
import com.nimbusds.jose.jwk.OctetKeyPair;

// Pseudocode registry đảm bảo key type/crv/recipient:
OctetKeyPair recipientXPublic =
    trustedKeyRegistry.getRecipientX25519Public("orders-api")
        .toPublicJWK();

JWEObject jwe = new JWEObject(
    new JWEHeader.Builder(
        JWEAlgorithm.ECDH_ES_A256KW,
        EncryptionMethod.A256GCM)
        .keyID("orders-x25519-v2")
        .contentType("JWT")
        .build(),
    new Payload(signedJwtCompact));

jwe.encrypt(new X25519Encrypter(recipientXPublic));
String token = jwe.serialize();

// Phía Orders, recipientXPrivate được bảo vệ:
OctetKeyPair recipientXPrivate =
    protectedKeyStore.getOwnX25519Key("orders-x25519-v2");

JWEObject received = JWEObject.parse(token);
recipientPolicy.requireAllowedHeader(received.getHeader());
received.decrypt(new X25519Decrypter(recipientXPrivate));

String nestedJwt = received.getPayload().toString();
issuerJwtVerifier.verifySignedAccessToken(nestedJwt);
~~~

Hai classes `X25519Encrypter` và `X25519Decrypter` là JOSE-layer encryption helpers; application abstractions `trustedKeyRegistry`, `protectedKeyStore`, `recipientPolicy`, `issuerJwtVerifier` là pseudocode.

Đừng chuyển `OctetKeyPair` X25519 thành `ECKey P-256`, và đừng tự gán `crv=Ed25519` cho ECDH. Kiểm library/JDK/crypto provider, supported curves và KMS capabilities theo môi trường triển khai.

## 19. Java/Spring Security: đưa JWE vào pipeline xác thực như thế nào?

Spring Security OAuth2 Resource Server thường có cấu hình cho **JWT ký** (JWS) hoặc **opaque token introspection**. Không nên giả định một cấu hình đơn giản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

sẽ tự **giải mã JWE**, chọn recipient key rồi xác minh **nested JWS**. Điều này cần **tích hợp decoder/authentication provider phù hợp** với JWE profile thực tế.

### 19.1. Các bước của một JWE-aware token pipeline

~~~mermaid
flowchart TD
    A[HTTP Authorization: Bearer JWE] --> B[Size / syntax / token type limits]
    B --> C[Trusted recipient key registry + header alg/enc checks]
    C --> D[Decrypt JWE with authorized recipient private key]
    D --> E[Require inner signed JWT for this profile]
    E --> F[Verify JWS signature using trusted issuer keys]
    F --> G[Validate iss, aud, exp, nbf, typ, scope, client/subject]
    G --> H[Revocation / grant-security state per policy]
    H --> I[Action + resource + tenant authorization]
    I --> J[Accept request]
    C --> X[Reject]
    D --> X
    E --> X
    F --> X
    G --> X
    H --> X
    I --> X
~~~

Thứ tự xử lý authorization/security checks có thể được tối ưu bởi implementation, nhưng **không được đánh mất** bất kỳ check bắt buộc nào. Claims từ outer JWE/header chưa được chứng thực không được dùng làm `Authentication` đã xác minh.

### 19.2. Pseudocode một decoder có chính sách chặt

~~~java
// Pseudocode Spring Security adapter, chưa phải thư viện sẵn có.
public Authentication authenticateJweBearer(
        String bearerToken,
        TrustedRequestContext request) {

    tokenLimits.requireBoundedSize(bearerToken);

    ParsedJwe jwe = jweParser.parseStrict(bearerToken);
    RecipientRegistration recipient =
        recipientRegistry.requireForResource(request.resourceId());

    recipientPolicy.requireAllowed(
        recipient,
        jwe.header().alg(),
        jwe.header().enc(),
        jwe.header().kid(),
        jwe.header().epk());

    String nestedSignedJwt =
        jweDecryptionService.decrypt(
            jwe,
            recipient.authorizedPrivateKeyReference());

    VerifiedJwt verified =
        issuerVerifier.verifySignedJwt(
            nestedSignedJwt, request.expectedIssuer());

    tokenValidator.requireAccessTokenProfile(
        verified,
        request.expectedAudience());

    revocationPolicy.requireActiveGrant(verified);
    return principalFactory.fromVerifiedJwt(verified);
}
~~~

`ParsedJwe`, `RecipientRegistration`, `VerifiedJwt`, `jweDecryptionService` và helpers là **pseudocode**; không có nghĩa Spring Security tự cung cấp những types này. Cấu hình production phải xử lý validation errors, timeouts, key recovery và response mapping theo hợp đồng ứng dụng.

### 19.3. Không dùng header JWE để tự xác định issuer

Sai:

~~~java
// SAI: JWT/JWE chưa được verify tự chọn trust root.
String issuer = unverifiedJwe.getHeader().getCustomParam("iss");
KeySet keys = download(issuer + "/jwks");
return trustEverythingDecryptedWith(keys);
~~~

Đúng hướng: **issuer và expected audience** đến từ cấu hình trusted AS/resource registration, hoặc được chọn theo một discovery policy đã xác thực; sau decrypt, inner JWS được kiểm với trust root phù hợp.

### 19.4. Key disclosure và logging

Khi decryption thất bại, không log:

~~~text
recipient private key bytes
ephemeral private key bytes
raw JWE access token
unwrapped CEK hoặc KEK
plaintext claims chứa dữ liệu nhạy cảm
KMS decrypt response
~~~

Có thể ghi những metadata đã qua classification như `recipientKeyFingerprint`, `alg`, `enc`, reason category, service/region và trace ID. Khi header chưa được xác minh, cần đánh dấu **untrusted metadata** trong audit để tránh injection.

### 19.5. Multipart/multi-recipient JWE và HTTP Bearer

Đừng giả định JWE General JSON Serialization có thể gửi trực tiếp nguyên JSON trong mọi `Authorization: Bearer` workflow; OAuth bearer credential và ứng dụng/client có yêu cầu token format/transport riêng. Nhiều deployments dùng **Compact JWE** cho access tokens một recipient.

Nếu cần multi-recipient JSON JWE, thiết kế **transport, token size, media type, JSON parsing và library support** cụ thể. Không ép một JSON object nhiều dòng vào header qua nối chuỗi hoặc đổi ngầm serialization mà client/RS không hiểu.

## 20. Threat model: những sai lầm làm hỏng recipient confidentiality

Một JWE có AEAD tag hợp lệ vẫn có thể bị thiết kế sai về **recipient selection, issuer authentication, key lifecycle hoặc resource authorization**.

| Lỗi/tấn công | Điều xảy ra | Biện pháp |
|---|---|---|
| **AS lấy recipient public key từ request tự khai** | Attacker đưa key của mình để nhận token nhạy cảm | Trusted recipient registration và policy |
| **Recipient public key bị thay trong registry/JWKS** | Sender mã hóa nội dung cho attacker | Signed/trusted key publication, audit, fingerprint |
| **`kid` được dùng làm quyền truy cập KMS** | Caller thử private key tenant khác | Bind expected recipient/tenant trước khi lookup |
| **JWE decrypt xong tin claims ngay** | Attacker có public key tạo plaintext giả | Verify inner JWS/issuer hoặc trusted sender auth profile |
| **Confuse `aud` và JWE recipient** | API giải mã được token dành audience khác | Explicit `aud` checks sau decrypt |
| **JWE thành bearer nhưng nghĩ đã chống replay** | Token string bị đánh cắp vẫn dùng được | DPoP/mTLS sender constraint và token lifecycle |
| **Dùng ECDH raw Z làm AES key** | Sai KDF/protocol, có thể yếu/dễ lỗi | JOSE Concat KDF implementation |
| **Tái sử dụng ephemeral key sai profile** | Key agreement context/reuse không đáp ứng chuẩn | Fresh ephemeral key mỗi operation |
| **`epk` chứa private `d`** | Rò ephemeral key hoặc parser bỏ kiểm | Public-only JWK validation, reject private params |
| **Không validate public EC point** | Invalid-curve/low-order key attacks | Crypto-provider validation, supported curves |
| **Nhầm X25519 với Ed25519** | Key type/operation sai | `OKP`/`crv`/purpose allowlist |
| **Tự cho phép `alg=dir` fallback** | Bypass recipient ECDH policy | Pin allowed `alg`/`enc` |
| **RSA padding oracle** | Lỗi decrypt chi tiết rò thông tin | JOSE library an toàn, reject legacy insecure modes |
| **Unprotected header override policy** | Chọn sai recipient/algorithm | JOSE union duplicate checks và trusted policy |
| **Multi-recipient chứa tenant không được phép** | Tenant đó mở được toàn bộ plaintext | Enforce recipient authorization trước encrypt |
| **Multi-recipient cùng ciphertext nhưng `aud` khác** | Một recipient đọc được token nhưng không có quyền dùng | Split tokens hoặc audience policy rõ |
| **Private recipient key tái sử dụng đa tenant** | Chiếm một tenant làm lộ token tenant khác | Per-tenant keys hoặc isolation policy |
| **R_v4 bị lộ, sender vẫn cache public v4** | JWE mới tiếp tục bị attacker giải mã | Emergency key rotation + sender cache invalidation |
| **Recipient private key bị xóa sớm** | JWE cũ còn hạn không thể decrypt | Key retention/recovery theo ciphertext lifetime |
| **Static recipient key bị lộ sau 1 năm** | JWE lịch sử lưu lại có thể bị giải mã | Storage minimization, key protection, retention |
| **KMS Agreement role bị lạm dụng** | Attacker tạo shared secrets dù key non-exportable | IAM, HSM auditing, key-use restrictions |
| **Error body phân biệt key đúng/sai** | Decryption/key existence oracle | Generic response, internal redacted audit |
| **JWE quá lớn/`zip` nén dữ liệu độc hại** | Memory/CPU DoS, decompression bomb | Size, depth, compression limits, disable if unnecessary |
| **Header chứa `jku`/`x5u` URL attacker** | SSRF hoặc key-source confusion | Never trust arbitrary header key URLs |
| **JWKS legacy key `use=sig` cho JWE** | Key purpose confusion | `use`/`key_ops`/alg/purpose validation |
| **Không kiểm `crit`** | Bỏ qua critical extension/header semantics | Reject unsupported critical headers |
| **Private key có trong container/browser source** | Mọi người có artifact cũng có khả năng decrypt | KMS/HSM/secure storage, avoid export |
| **Không kiểm business ownership** | Token decrypt + signature đúng nhưng truy cập resource khác tenant | Resource/action/tenant authorization |
| **Lộ plaintext qua tracing/logging** | JWE không bảo vệ token đã decrypt trong hệ thống | Data minimization, redaction, memory controls |
| **CSRF/client auth sai khi xin JWE** | AS phát token cho client sai/unauthorized | OAuth grant/client auth/PKCE và policy |

### 20.1. Public recipient key không phải secret

Attacker có R_public **không tự decrypt** JWE gửi cho R_private. Nhưng attacker có thể tạo JWE gửi đến recipient từ **public key đó**. Vì vậy:

- Confidentiality của nội dung hợp lệ cần private key bảo vệ.
- Authentication của nội dung cần issuer signature hoặc cơ chế trusted sender riêng.
- Authorization của request cần claims đã xác minh và policy nghiệp vụ.

Nhầm ba lớp này là nguồn của rất nhiều sai sót trong token encryption.

### 20.2. Recipient key compromise và decryption oracle khác nhau

**Key compromise:** attacker có R_private hoặc quyền dùng KMS KeyAgreement/Decrypt của recipient.

**Oracle:** attacker không có private key, nhưng có thể gửi JWE tùy ý tới một service rồi khai thác response khác nhau để suy thông tin, xác định key tồn tại hoặc probing cryptographic validity.

Biện pháp gồm:

- Không trả chi tiết “found KID, good ECDH, bad AES tag” cho caller.
- Dùng cryptographic library chống timing/padding oracle và xử lý lỗi có kiểm soát.
- Giới hạn request rate, size, số recipients và số keys được thử.
- Không phản hồi plaintext/claims cho client không có quyền chỉ vì decryption thành công.
- Ghi logs nội bộ redacted để support mà không lộ secrets.

### 20.3. Key substitution trên recipient registry

~~~text
Registry ban đầu:
    Orders -> R_orders_public.

Attacker thay:
    Orders -> R_attacker_public.

AS phát JWT JWE chứa customer data:
    encrypt to R_attacker_public.

Attacker có R_attacker_private:
    decrypt toàn bộ token.
~~~

**Việc AS dùng AES-GCM và ECDH đúng chuẩn không cứu được nếu AS đã chọn sai người nhận.** Đây là identity/trust registration failure.

### 20.4. Multi-recipient mở rộng blast radius

Một encrypted token được phép cả Orders và Audit đọc có nghĩa **compromise private key của bất kỳ recipient nào** có thể lộ plaintext. Nếu các services thuộc nhiều tổ chức/tenant:

1. Đánh giá thật sự có cần chung payload không.
2. Giảm dữ liệu nhạy cảm trong plaintext và số recipients.
3. Dùng token riêng theo audience/tenant khi chia quyền khác nhau.
4. Giới hạn key exposure và quyền giải mã của từng service.
5. Cân nhắc expiration/retention, revocation và incident response.

### 20.5. JWE không bảo vệ token khỏi bên đã được phép đọc

Nếu Orders được phép decrypt, Orders có thể xem plaintext hoặc copy credential trong process memory. JWE không giữ bí mật claims **đối với đúng recipient**. Nếu Orders bị xâm nhập, ciphertext protection ở đường truyền không đủ; cần host/KMS/service identity protection và policy audit.

## 21. Ma trận kiểm thử ECDH-ES, recipient và JWE end-to-end

Test thành công khi “JWE decrypt được” là chưa đủ. Cần chứng minh **đúng recipient giải mã được, recipient sai không giải mã được, issuer thật được xác minh và claims được enforce**.

### 21.1. ECDH-ES và JWE header

| Test | Kết quả mong muốn |
|---|---|
| `ECDH-ES` direct, P-256, A256GCM | Recipient suy ra CEK và decrypt đúng |
| `ECDH-ES+A256KW`, P-256, A256GCM | Recipient suy ra KEK, unwrap CEK và decrypt đúng |
| `ECDH-ES+A256KW`, X25519 | JOSE library nhận đúng `OKP`/`crv` và decrypt |
| JWE thiếu `epk` | Từ chối |
| `epk` chứa trường private `d` | Từ chối theo public-only `epk` policy |
| `epk` có EC point sai curve | Từ chối |
| `epk` low-order/all-zero shared secret ở X25519 | Từ chối theo curve validation implementation |
| `alg` không nằm trong allowlist | Từ chối trước khi dùng private key |
| `enc` sai hoặc không được hỗ trợ | Từ chối |
| Header `alg=ECDH-ES`, `encrypted_key` không rỗng | Từ chối bất nhất |
| Header `alg=ECDH-ES+A256KW`, encrypted key hỏng | Unwrap/decrypt thất bại |
| `kid` trỏ key đúng type nhưng khác curve | Từ chối |
| Header có duplicate parameter giữa protected/unprotected | Từ chối theo JOSE rules |
| Header `crit` không hỗ trợ | Từ chối |
| `apu` thay đổi trong JWE | KDF mismatch/AEAD fail, không dùng làm sender auth |
| `apv` thay đổi trong JWE | KDF mismatch/AEAD fail, không dùng làm audience auth |
| IV hoặc tag A256GCM bị sửa | AEAD decryption thất bại |
| Ciphertext bị thay một byte | AEAD authentication thất bại |
| `zip` compression khiến payload giải nén quá giới hạn | Từ chối bằng resource limits |
| JWE body cực lớn/JSON quá sâu | Từ chối trước expensive crypto |
| Direct JWE `encrypted_key` rỗng | Đúng cấu trúc, không suy CEK rỗng |

### 21.2. Recipient binding và trust source

| Test | Kết quả mong muốn |
|---|---|
| JWE cho Orders với Orders private key | Decrypt được khi đúng profile |
| JWE cho Orders với Billing private key | Decrypt thất bại |
| JWE có `kid` của tenant B khi request tenant A | Không thử private tenant B |
| AS nhận public key tùy ý trong token request | Không dùng làm recipient key nếu chưa registration/authorization |
| Recipient JWKS bị thay bằng attacker public key | Phát hiện trust/publisher mismatch |
| Recipient key `use=sig` trong encryption registry | Từ chối key purpose mismatch |
| Public `kid` trùng nhưng key material khác issuer | Không trộn registry/issuer |
| KMS key access của Orders cho Billing role | Access denied |
| Private Orders key rò vào browser bundle | Security test fail |
| KMS decrypt/quorum role thiếu permission | Fail closed, không fallback secret khác |
| Recipient v4 đã retired, JWE còn hạn theo policy | Có behavior documented (decrypt grace hoặc reject) |
| Recipient v4 compromised, token mới mã hóa cho v4 | Test fail; AS phải chuyển key |
| R_v5 đăng ký nhưng sender cache v4 | Test phát hiện stale recipient key |

### 21.3. Multi-recipient JWE JSON

| Test | Kết quả mong muốn |
|---|---|
| Một CEK wrapped cho Orders và Billing | Cả hai mở cùng plaintext nếu được phép |
| Chỉ Orders recipient entry | Billing không unwrap CEK |
| Delete một recipient entry khỏi JSON | Recipients còn lại vẫn xử lý theo profile; không tự biến thành authorization grant khác |
| Tamper một recipient wrapped CEK | Recipient đó thất bại; không lộ CEK |
| Per-recipient `epk` bị thay | Key derivation/unwrap thất bại |
| General JWE `enc` không nhất quán theo recipients | Từ chối |
| Header names trùng giữa shared và per-recipient | Từ chối |
| Header chứa hàng chục nghìn recipients | Bounded parser/recipient count |
| User xin thêm recipient ngoài approved list | Từ chối authorization |
| JWE decrypted bởi Billing nhưng inner `aud=Orders` | Billing từ chối |
| JSON JWE gửi qua transport chỉ hỗ trợ compact string | Từ chối/negotiation rõ, không parse lỏng |

### 21.4. JWT/OIDC/OAuth và resource authorization

| Test | Kết quả mong muốn |
|---|---|
| Signed JWT được JWE encrypt cho Orders | Decrypt, verify JWS signature và claims đúng |
| Plain JSON claims không ký được JWE encrypt | RS từ chối nếu profile yêu cầu nested JWS |
| Inner JWS signature sai nhưng outer AEAD tag đúng | RS từ chối |
| Inner JWS `iss` lạ | RS từ chối |
| Inner JWT `aud` sai | RS từ chối |
| Inner JWT hết hạn `exp` | RS từ chối |
| Inner ID token dùng như access token | RS từ chối token type/profile |
| Access token có scope `orders:read`, order khác tenant | Từ chối theo object policy |
| Refresh token gửi Bearer tới Orders API | RS từ chối sai credential |
| JWT ký hợp lệ nhưng grant đã revoke | RS tuân revocation state/TTL đã cam kết |
| Token bị sao chép và replay từ client khác | Nếu bearer, rủi ro còn; kiểm sender constraint khi đã cấu hình |
| DPoP proof có key khác token binding | Từ chối |
| AS signing key compromise | JWE decrypt không cứu authenticity; verify issuer trust phải chặn |
| Recipient decryption key compromise | Điều tra JWE cũ bị đọc, rotate và cấp token theo policy |

### 21.5. Tự động hóa cross-library interoperability

Không chỉ test encrypt/decrypt trong cùng một instance thư viện:

1. Generate keypair P-256/X25519 bằng **fixtures riêng** phù hợp provider.
2. Tạo JWE test bằng library A và giải bằng library B có cùng JOSE profile.
3. Kiểm `epk`, `apu`/`apv`, `alg`, `enc` và `encrypted_key` length.
4. Test direct `ECDH-ES` và wrapping `ECDH-ES+A256KW` riêng.
5. Kiểm General JSON multi-recipient nếu cả hai libraries hỗ trợ.
6. Gửi malformed JWE header, invalid EC points và corrupt AEAD tag.
7. Tích hợp nested signed JWT issuer validation với public AS signing key độc lập.
8. Test token audiences, scope, tenant/object ownership và revocation.
9. Test encrypted token size trong HTTP gateway, proxy/header limits.
10. Kiểm logs/metrics không chứa plaintext, recipient private key hoặc raw bearer token.

**Không dùng private keys hoặc tokens production trong test vectors.** RFC 7516/7518/8037 có các test examples; chọn fixtures có kiểm soát và xác minh compatibility theo version của thư viện.

## 22. Tình huống suy luận thực tế

### Tình huống A — AS chọn key từ query của client

Client yêu cầu access token và gửi `recipient_jwk` do chính nó tạo, tự khai là key Orders API. AS mã hóa claims chứa customer data theo key đó.

**Câu hỏi:** Thuật toán ECDH-ES đúng có làm token an toàn không?

**Trả lời:** Không. Attacker giữ private key tương ứng có thể mở token. AS phải chọn recipient từ **trusted client/resource registration** sau authorization, không từ key tự khai.

### Tình huống B — Recipient key và audience khác nhau

Orders API giải mã được JWE nhưng plaintext JWT có `aud=https://billing.example.com`.

**Câu hỏi:** Có được đọc order vì đã decrypt thành công không?

**Trả lời:** Không. Recipient decryption chỉ chứng minh khả năng mở ciphertext. Orders API phải từ chối token sai `aud`, kể cả chữ ký issuer hợp lệ.

### Tình huống C — Attacker tự tạo JWE được giải mã thành công

Attacker có public encryption key của Orders và tự mã hóa JSON `{"role":"admin"}`. AEAD tag đúng.

**Câu hỏi:** Có phải AS đã phát hành token?

**Trả lời:** Không. Public key là public; attacker có thể mã hóa gửi recipient. Nếu profile yêu cầu JWT, RS phải kiểm inner signed JWS từ AS và mọi claims/authorization.

### Tình huống D — ECDH direct không có `encrypted_key`

Một JWE Compact chứa `protected..iv.ciphertext.tag`, tức hai dấu chấm liên tiếp sau protected header.

**Câu hỏi:** Có chắc JWE hỏng không?

**Trả lời:** Không. Với `alg=ECDH-ES` direct, `encrypted_key` được biểu diễn rỗng; CEK được suy ra từ ECDH/Concat KDF. Với `ECDH-ES+A256KW`, wrapped CEK thường phải hiện diện.

### Tình huống E — Sử dụng `SHA256(Z)` thay Concat KDF

Dev dùng ECDH lấy 32 bytes rồi hash thành AES key, bỏ qua AlgorithmID, PartyUInfo và PartyVInfo.

**Câu hỏi:** Có tương thích JWE chuẩn không?

**Trả lời:** Không. JOSE ECDH-ES yêu cầu Concat KDF với các tham số được định nghĩa trong RFC 7518. Dùng JOSE library hỗ trợ ECDH-ES thay vì tự tạo KDF.

### Tình huống F — `epk` bị thiếu

Orders nhận `alg=ECDH-ES+A256KW`, nhưng header không có ephemeral public key `epk`.

**Câu hỏi:** Có nên thử một public key mặc định?

**Trả lời:** Không. `epk` phải có và được validate theo profile. Chọn fallback key tùy tiện làm hỏng key agreement và có thể mở cửa cho key confusion.

### Tình huống G — `epk` chứa private `d`

Một JWE header chứa `epk.d`, là ephemeral private key bytes.

**Câu hỏi:** Có nên chỉ bỏ qua trường này?

**Trả lời:** Không. `epk` phải là **public JWK**. Private fields trong header vi phạm mô hình secrecy; cần reject theo policy, không log raw header chứa secret.

### Tình huống H — Curve P-256 và X25519 bị trộn

RS giữ P-256 private key, JWE khai `epk` là `kty=OKP, crv=X25519`.

**Câu hỏi:** Có thể tự chuyển dữ liệu giữa hai curve?

**Trả lời:** Không. Key agreement yêu cầu đúng algorithm/curve/key type. Từ chối mismatch; không tự ép X25519 thành P-256 hoặc nhầm với Ed25519 signature keys.

### Tình huống I — `apu` được dùng làm danh tính AS

Một JWE có `apu` giải mã ra `trusted-issuer`, controller vì thế bỏ xác minh chữ ký JWT bên trong.

**Câu hỏi:** Sai ở đâu?

**Trả lời:** `apu` là KDF context do originator của JWE đặt. Nó không tự xác thực sender. Cần verify inner JWS/issuer hoặc cơ chế sender authentication đáng tin khác.

### Tình huống J — `apv=orders-api` và `aud=billing-api`

JWE chứa `apv=orders-api` và RSA/EC recipient key đúng Orders, nhưng JWT trong đó có `aud=billing-api`.

**Câu hỏi:** `apv` có sửa được audience không?

**Trả lời:** Không. `apv` là PartyVInfo cho KDF, không thay `aud` claims. Orders phải reject sai audience.

### Tình huống K — Static recipient private key lộ sau một năm

Attacker đã lưu các JWE phát năm trước với `epk`; hôm nay chiếm được `R_orders_private`.

**Câu hỏi:** Các ciphertext cũ có được bảo vệ nhờ sender ephemeral key không?

**Trả lời:** Không đảm bảo. ECDH ephemeral-static không cung cấp forward secrecy đối với việc recipient static private bị lộ: attacker có thể tính lại shared secrets từ private R và `epk` đã lưu.

### Tình huống L — Đổi `kid` nhưng giữ nguyên recipient private key

Orders đổi `kid=orders-v4` thành `orders-v5`, fingerprint public key giữ nguyên.

**Câu hỏi:** Đã rotate encryption key thật chưa?

**Trả lời:** Chưa. Cryptographic key material vẫn là một; nếu v4_private bị lộ, attacker vẫn decrypt JWE mã hóa cho v5 khi dùng cùng vật liệu.

### Tình huống M — Recipient private v4 bị xóa quá sớm

AS đã chuyển encrypt sang v5, nhưng client còn giữ access token JWE v4 chưa hết hạn.

**Câu hỏi:** Orders có chắc decrypt được token cũ bằng v5_private không?

**Trả lời:** Không. Cần key version retention trong thời gian token/ciphertext còn được chấp nhận hoặc có phương án cấp token mới/reauthorization phù hợp.

### Tình huống N — Multi-recipient thêm Audit ngoài policy

AS tạo JWE JSON có recipients Orders, Billing và Audit; plaintext chứa toàn bộ customer PII mà Audit không được phép đọc.

**Câu hỏi:** Có thể nói Audit chỉ nhận “encrypted_key”, chưa thấy plaintext nên vẫn an toàn không?

**Trả lời:** Không. Nếu Audit có private recipient key, nó unwrap CEK và đọc **toàn bộ plaintext chung**. Không thêm recipient ngoài authorization policy.

### Tình huống O — Multi-recipient nhưng claims khác audience

Orders và Billing cùng mở một JWE; inner JWT có `aud=Orders`.

**Câu hỏi:** Billing có được xử lý payment action không?

**Trả lời:** Không. Billing có thể đọc plaintext nhưng không phải intended audience. Để cấp quyền nhiều API, AS phải quyết định và biểu diễn audience/scope hợp lệ; thường nên phát token riêng.

### Tình huống P — Sender lưu CEK để thêm recipient sau

Một service đã decrypt JWE, giữ CEK và tự wrap cho một recipient ngoài tổ chức.

**Câu hỏi:** Vấn đề?

**Trả lời:** Người có CEK có khả năng mở nội dung và chia quyền đọc. Tự thêm recipient là một quyết định data-sharing/authorization, không phải thao tác kỹ thuật trung tính.

### Tình huống Q — `dir` được bật như fallback cho ECDH

JWE khai `alg=dir`, ứng dụng vốn yêu cầu ECDH-ES vẫn decrypt bằng một global symmetric secret.

**Câu hỏi:** Có an toàn không?

**Trả lời:** Không nếu trái recipient policy. Fallback có thể bỏ qua key isolation hoặc mở rộng trust. Chỉ chấp nhận `alg`/`enc` được phê duyệt và key phù hợp.

### Tình huống R — RSA-OAEP bị gọi là key agreement

Dev nói RSA-OAEP và ECDH-ES đều “hai bên thỏa thuận Z”.

**Câu hỏi:** Đúng không?

**Trả lời:** Không. RSA-OAEP trong JWE **mã hóa CEK** bằng public key của recipient. ECDH-ES **tính shared secret Z** từ khóa hai bên rồi chạy Concat KDF.

### Tình huống S — Signer bị lộ, recipient key vẫn an toàn

AS signing private key bị compromise, recipient R_orders_private vẫn ở HSM. Attacker có thể ký JWS giả rồi mã hóa nó cho R_orders_public.

**Câu hỏi:** JWE có ngăn token giả không?

**Trả lời:** Không. JWE che plaintext, nhưng không sửa vấn đề issuer signing trust. Orders phải distrust signing key đã lộ và kiểm issuance/key policy theo incident response.

### Tình huống T — Recipient key lộ, signer vẫn an toàn

R_orders_private bị lộ nhưng AS signing key vẫn bảo vệ. Attacker đọc được các JWE Orders đã thu thập.

**Câu hỏi:** Có tự ký được JWT mới không?

**Trả lời:** Không chỉ từ recipient private key. Sự cố chính là **confidentiality của JWE**; cần rotate recipient key, điều tra dữ liệu và không nhầm với issuer signing compromise.

### Tình huống U — `jku` trong header trỏ server attacker

Một JWT/JWE mang `jku=https://attacker.example/jwks.json`, app tải key ở đó để decrypt/verify.

**Câu hỏi:** Rủi ro?

**Trả lời:** Key-source confusion/SSRF. Không để untrusted JOSE header chọn trust root; dùng trusted issuer/recipient registry và giới hạn network fetch.

### Tình huống V — Java Spring chỉ có `issuer-uri`

Dev cấu hình Spring Security Resource Server `jwt.issuer-uri` rồi gửi JWE Compact vào Authorization header.

**Câu hỏi:** Có chắc Spring tự ECDH-decrypt và verify nested JWT không?

**Trả lời:** Không. Phải xây/đăng ký decoder/provider phù hợp với encrypted token profile và recipient key, rồi verify inner JWT. `issuer-uri` đơn lẻ không thay tích hợp JWE.

### Tình huống W — Decrypt thành công nhưng tag bị bỏ qua

Một custom decryptor trả plaintext trước khi xác minh A256GCM tag.

**Câu hỏi:** Hậu quả?

**Trả lời:** Có thể trả dữ liệu bị sửa hoặc mở đường cho oracle. AEAD authentication phải pass **trước khi sử dụng plaintext**, không chấp nhận partial plaintext từ lỗi crypto.

### Tình huống X — JWE có 20.000 recipients

API nhận một JSON JWE rất lớn và thử hàng nghìn private keys trước khi trả 401.

**Câu hỏi:** Đây có thể là tấn công gì?

**Trả lời:** Resource-exhaustion/DoS. Giới hạn kích thước payload, JSON depth, số recipients, số keys/attempts và timeout; chọn key từ trusted context trước crypto.

### Tình huống Y — ID token được mã hóa cho RP nhưng gửi sang API

Một RP decrypt ID token, rồi frontend dùng chính ID token để gọi Orders API.

**Câu hỏi:** Vì sao phải từ chối?

**Trả lời:** ID token dành cho **OIDC authentication** ở RP. Nó không phải OAuth access token cho Orders; token type/audience phải được kiểm độc lập với việc decrypt thành công.

### Tình huống Z — Bearer JWE bị đánh cắp

Attacker đánh cắp access token dạng JWE nhưng không có recipient private key. Orders API nhận Bearer JWE và decrypt như thường lệ.

**Câu hỏi:** Attacker có thể sử dụng token không?

**Trả lời:** Có thể nếu token là **bearer** và còn hiệu lực; attacker không cần đọc claims để replay credential. JWE confidentiality không thay sender constraint, TLS, storage và revocation.

## 23. Playbook: recipient encryption key bị lộ hoặc không giải mã được

Key agreement sự cố có thể là **confidentiality incident** (recipient private key bị lộ), **availability incident** (recipient key bị mất/KMS outage) hoặc **trust registration incident** (sender chọn public key giả). Mỗi loại cần hành động khác nhau.

### 23.1. Bước 1 — Xác định chính xác tình trạng

| Tín hiệu | Điều cần phân biệt |
|---|---|
| Orders trả lỗi decrypt sau rollout | Sai key version/curve/alg/JWKS cache, hay private key unavailable? |
| R_orders_private có trong CI artifact | Private material đã lộ tới đâu, có bản sao? |
| KMS key non-exportable nhưng role bị chiếm | Attacker có quyền chạy KeyAgreement/Decrypt trên KMS không? |
| Public key Orders bị thay trong registry | Token nào đã bị AS mã hóa cho key của attacker? |
| AS mới encrypt v5 nhưng RS chỉ có v4 | Không tương thích rollout, không nhất thiết là compromise |
| JWE được decrypt nhưng inner JWS verify fail | Sai issuer signing trust/forgery hay token corrupted? |
| JWE A256GCM tag fail | Key/IV/AAD/ciphertext/tag mismatch hoặc tamper; không trả plaintext |

Không lập tức suy “KMS bị hack” chỉ từ một AES-GCM tag failure; nhưng cũng không bỏ qua dấu hiệu key compromise chỉ vì decrypt thỉnh thoảng vẫn thành công.

### 23.2. Bước 2 — Contain credential và nguồn public key

Nếu **recipient private key bị lộ**:

1. Thu hồi/quarantine key role hoặc tắt decrypt/key agreement capability bị chiếm.
2. Xác định key fingerprint, issuer/tenant/recipients dùng chung và khoảng exposure.
3. Tạo recipient key v5 mới bằng quy trình đáng tin; không chỉ đổi `kid`.
4. Bảo vệ source đăng ký public key, cập nhật đúng AS/senders.
5. Dừng encrypt JWE mới cho key v4 đã compromise.
6. Xem dữ liệu trong các JWE v4 đã phát có thể bị attacker giải mã offline.
7. Đánh giá token/session/grant reuse hoặc access token theft cùng thời điểm.

Nếu chỉ **public recipient key bị substitute**:

- Khôi phục trusted key registry và change approval.
- Xác định khoảng thời gian AS encrypt cho attacker public key.
- Xem các token/claims được phát trong khoảng đó đã lộ hay chưa.
- Không coi việc “đổi lại JWKS” làm biến ciphertext cũ mất khả năng giải mã bằng attacker private key.

### 23.3. Bước 3 — Recovery khi private key bị mất nhưng không compromise

~~~text
Recipient v4 private unavailable.
    |
    +--> Có KMS/HSM-native recovery/DR replica?
    |        -> Restore capability đúng key v4 theo policy.
    |
    +--> Không recover v4?
             -> Activate v5 public/private pair.
             -> AS encrypt JWE mới cho v5.
             -> JWE v4 cũ không thể mở nếu thiếu v4 private.
             -> Có thể yêu cầu OAuth clients xin token mới,
                hoặc phục hồi từ backup nếu được phép.
~~~

Với access token ngắn hạn, chấp nhận yêu cầu **reauthorization/refresh và cấp JWE mới** có thể khả thi. Với ciphertext lưu dài hạn chứa dữ liệu không có bản gốc, mất decryption key có thể nghiêm trọng hơn và cần backup/recovery chuyên biệt.

**Không gửi private key của service khác cho Orders** để bypass outage, nếu làm vậy phá authorization/isolation model.

### 23.4. Bước 4 — Kiểm issuer và resource authorization sau recovery

Test có kiểm soát:

~~~text
JWE v5 valid + signed inner JWT đúng:
    decrypt PASS, signature PASS, audience PASS.

JWE v4 khi v4 compromised:
    reject theo incident key policy.

JWE v5 malformed epk hoặc tag:
    reject trước khi dùng plaintext.

JWE v5 inner JWS của attacker:
    decrypt có thể PASS, signature FAIL.

JWE v5 inner JWS aud Billing:
    decrypt có thể PASS, audience FAIL.

JWE v5 inner JWT đúng nhưng order tenant khác:
    decrypt/signature PASS, authorization FAIL.
~~~

Một `HTTP 200` ở JWKS/registry hoặc một lần `KMS Decrypt PASS` chưa đủ chứng minh mọi API instances phục hồi đúng.

### 23.5. Bước 5 — Giám sát propagation và key usage

Các chỉ số có thể gồm:

~~~text
recipient_key_version_used_by_sender
recipient_key_version_supported_by_rs
last_recipient_registry_sync_age
jwe_decrypt_failures_by_alg_enc_key_version
jwe_wrong_recipient_rejections
jwe_inner_jws_invalid_signature
key_agreement_kms_calls_by_principal
key_rotation_and_revocation_lag
compromised_decryption_key_usage_attempts
cross_tenant_key_lookup_denials
~~~

Phân tách **confidentiality state** và **availability state**. Một RS vẫn decrypt JWE v4 có thể gây rủi ro nếu v4 compromised; ngược lại, từ chối v4 có thể là điều đúng theo emergency policy và cần kiểm UX/token reissue.

### 23.6. Bước 6 — Điều tra tác động dữ liệu

Với recipient private key bị lộ, điều tra:

- Dữ liệu claims được JWE mã hóa cho key đó.
- Những access/ID tokens còn sống, token đã bị replay, granted scopes.
- JWE cũ nằm trong logs, browser history, storage, packet captures hoặc backups.
- Khả năng attacker đã lưu ciphertext và giải mã sau khi lấy key.
- Các services/tenants dùng lại key material.
- Những dữ liệu đã bị tải hoặc chia sẻ và nghĩa vụ bảo mật tương ứng.

**Rotate không hoàn tác plaintext đã bị đọc.** Cần response theo dữ liệu/người dùng, không chỉ thay metadata.

## 24. Checklist thiết kế recipient và key agreement

### 24.1. Recipient và issuance

1. **Xác định intended recipient:** RS, RP/BFF hoặc service đã được đăng ký tin cậy.
2. **Chọn key theo grant/audience:** không lấy public key tùy ý từ client request.
3. **Tách ranh giới:** JWE recipient không thay `aud`, token type, scope hoặc quyền theo resource/tenant.
4. **Key ownership:** sender chỉ cần public key; private recipient key được bảo vệ bởi đúng service/HSM.
5. **Key purpose:** dùng `enc` key cho JWE, `sig` key cho JWS; không trộn key types/issuers.

### 24.2. JOSE algorithms và header

6. **Pin `alg`/`enc`:** chỉ cho profile được phê duyệt; không fallback sang `dir`/legacy RSA vì header tự khai.
7. **ECDH-ES direct:** Concat KDF suy ra CEK, `encrypted_key` rỗng.
8. **ECDH-ES+A256KW:** Concat KDF suy ra KEK, AES Key Wrap bọc CEK, `encrypted_key` có dữ liệu.
9. **Fresh ephemeral key:** mỗi key agreement operation tạo ephemeral key theo RFC.
10. **`epk` public-only:** không có private `d`, key type/curve hợp lệ.
11. **Curve validation:** P-256/OKP X25519 đúng format, kiểm invalid public keys/low-order và provider.
12. **KDF parameters:** `apu`/`apv` optional nhưng phải xử lý đúng Base64url/context; không dùng làm sender identity.
13. **Header integrity:** phân biệt protected/per-recipient unprotected; kiểm duplicate JOSE header names và `crit`.
14. **Algorithm confusion:** `alg`, `enc`, key type và purpose phải nhất quán với receiver policy.

### 24.3. Nhiều recipients và sender trust

15. **Compact vs General JSON:** Compact một recipient; General JSON có thể có nhiều recipients.
16. **Shared plaintext:** tất cả recipients mở cùng content; không dùng để chia nhiều mức quyền khác nhau.
17. **Recipient allowlist:** chỉ thêm key/tenant/service được phép.
18. **Key wrapping:** dùng CEK chung và recipient-specific wrapping đúng profile cho multi-recipient.
19. **Issuer authentication:** decrypt thành công không chứng minh AS đã ký; verify nested JWS hoặc sender auth theo profile.
20. **Content type:** với nested JWT, kiểm `cty`/token profile và inner JWT signature.
21. **No arbitrary JWKS:** không fetch trust roots từ `jku`/`x5u` do token tự khai.

### 24.4. Token lifecycle và vận hành

22. **Recipient key rotation:** lưu các private key versions cần decrypt JWE còn hạn, hoặc tổ chức reissue có kiểm soát.
23. **Key compromise:** dừng encrypt cho key lộ, không cho new key trùng material; điều tra JWE cũ có thể đã lộ.
24. **Static-key exposure:** không hứa ECDH-ES có forward secrecy trước compromised recipient static private.
25. **KMS/HSM:** đánh giá KeyAgreement/Decrypt support, role permissions, audit và provider-specific recovery.
26. **Bearer replay:** dùng DPoP/mTLS khi cần, TTL, revocation/refresh rotation và storage.
27. **JSON/HTTP size limits:** giới hạn recipients, payload, decompression, key lookup attempts.
28. **Generic error responses:** không lộ key existence/crypto oracle cho caller.
29. **Redaction:** không log raw JWE bearer token, plaintext, CEK/KEK hoặc private keys.
30. **Interoperability:** thử P-256/X25519, direct/wrapping, wrong-key/curve, nested JWS, audiences/tenants và nhiều providers.

### 24.5. Chọn nhanh key management cho một recipient

~~~mermaid
flowchart TD
    A[Cần mã hóa token cho recipient?] --> B{Recipient dùng public-key cryptography?}
    B -- Có --> C{Hỗ trợ ECDH-ES trong JOSE/KMS?}
    C -- Có --> D{Một recipient hay nhiều recipients?}
    D -- Một --> E[ECDH-ES hoặc ECDH-ES+KW theo profile]
    D -- Nhiều --> F[General JWE + CEK chung, wrap riêng cho recipient]
    C -- Không --> G[RSA-OAEP-256 nếu profile/provider cho phép]
    B -- Không --> H{Có shared symmetric key quản lý an toàn?}
    H -- Có --> I[dir hoặc AES-KW theo threat model]
    H -- Không --> J[Thiết kế key provisioning/opaque token thay thế]
    E --> K[Verify issuer/signature + token claims + business policy]
    F --> K
    G --> K
    I --> K
    J --> K
~~~

Không có một thuật toán đúng cho mọi hệ thống: lựa chọn phụ thuộc **key infrastructure, recipient count, data sensitivity, interoperability, policy và recovery plan**. Quan trọng là khóa thuộc đúng người nhận, `alg` và `enc` an toàn, và người nhận kiểm issuer/authorization sau decrypt.

### 24.6. Nhớ nhanh trong một phút

~~~text
Recipient:
    Bên có private key/secret để mở nội dung JWE.

aud:
    Resource audience được token cho phép; khác recipient key.

alg:
    Cách tạo/thỏa thuận/transport/wrap CEK.

enc:
    Cách mã hóa và xác thực plaintext bằng CEK.

ECDH-ES:
    Sender ephemeral private + Recipient static public -> Z.
    Recipient static private + Sender ephemeral public -> Z.
    Concat KDF -> CEK.

ECDH-ES+A256KW:
    Concat KDF -> KEK.
    AES Key Wrap(KEK, random CEK).

epk:
    Ephemeral PUBLIC key, không chứa private key.

apu/apv:
    KDF context, không tự chứng minh sender/audience.

General JWE multi-recipient:
    Một ciphertext, nhiều wrapped CEKs, cùng plaintext.

JWE decrypt PASS:
    Chưa chứng minh issuer hoặc quyền nghiệp vụ.

JWE bearer token:
    Vẫn có nguy cơ replay nếu bị đánh cắp.
~~~

**Kết luận:** Trong JWE, **recipient** là bên được phép mở lớp mật mã; **key agreement** như ECDH-ES giúp sender và recipient suy ra CEK hoặc KEK mà không trao đổi private keys. `ECDH-ES` trực tiếp suy ra CEK; `ECDH-ES+A256KW` suy ra KEK để bọc CEK ngẫu nhiên, thích hợp hơn khi cần nhiều recipients cùng đọc một ciphertext. `epk`, `apu`, `apv` và `kid` giúp xử lý phép thỏa thuận/chọn key nhưng **không tự chứng minh sender, audience hay quyền truy cập**. Trong OAuth 2.0/OIDC, JWE cần được đặt đúng trong chuỗi tin cậy: sender chọn public key đã đăng ký, recipient giữ private key được bảo vệ, giải mã có kiểm AEAD, xác minh issuer/JWS khi profile yêu cầu và tiếp tục kiểm `aud`, token type, scope, revocation, action và resource. **Mã hóa đúng cho recipient không thay thế xác thực và phân quyền.**

## Tài liệu tham khảo

- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Compact và General/Flattened JSON Serialization, protected/per-recipient headers, encrypted_key, IV, ciphertext, tag.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): ECDH-ES trực tiếp, ECDH-ES+A128/192/256KW, Concat KDF, `epk`, `apu`, `apv`, RSA-OAEP, `dir`, AES-KW và `enc`.
- [RFC 8037 — CFRG ECDH and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): `OKP` keys, X25519/X448 cho ECDH-ES và EdDSA signatures.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): `kty`, `kid`, `use`, `key_ops`, public/private material và JWK Set.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): sender/issuer signature và protected header.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, nested JWT, `iss`, `aud`, `exp`, `cty`.
- [RFC 7638 — JWK Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): fingerprint nhận diện public key material.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm allowlist, issuer/audience validation, confusion attacks và token types.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT claims/profile và audience.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS, RS, client, grant, access/refresh tokens.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token theft, audience restriction, sender constraints và refresh security.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens, client proofs và replay.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens và OAuth client authentication.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque tokens, active state và cache.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC ID token validation và encrypted ID token requirements.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): client registration, JWKS và ID token encryption metadata.
- [Nimbus JOSE + JWT API — ECDHEncrypter](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/crypto/ECDHEncrypter.html): Java ECDH JWE sender support.
- [Nimbus JOSE + JWT API — ECDHDecrypter](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/crypto/ECDHDecrypter.html): Java ECDH JWE recipient support.
- [Nimbus JOSE + JWT API — X25519Encrypter](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/crypto/X25519Encrypter.html): X25519 JWE encryption.
- [Nimbus JOSE + JWT API — X25519Decrypter](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/crypto/X25519Decrypter.html): X25519 JWE decryption.
- [Spring Security Reference — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/public signing key validation; ứng dụng encrypted JWT cần tích hợp decoder phù hợp.
- [OWASP JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT handling, key management và token misuse.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): phân phối khóa, lifecycle, key compromise và key use separation.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): mã hóa, khóa, AEAD và secret storage.
