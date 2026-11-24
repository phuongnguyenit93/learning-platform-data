# Key dùng cho encryption

Giả sử Authorization Server (AS) phát **access token** cho Payroll API. Token chứa `sub`, `aud`, `scope`, `exp` và một số thông tin nội bộ mà doanh nghiệp không muốn xuất hiện dưới dạng plaintext trong hệ thống trung gian. Một giải pháp là **mã hóa token** trước khi gửi tới Resource Server (RS). Nhưng câu hỏi quan trọng hơn “dùng AES hay RSA?” là: **ai giữ khóa nào, khóa được dùng để làm gì, bên nào có thể giải mã, khi thay khóa thì token cũ ra sao, và mã hóa có đủ để chứng minh issuer không?**

Đó là nội dung bài **“Key dùng cho encryption”** thuộc chương **Token encryption** của module **Security Token Security Fundamentals**. Bài học tập trung vào **khóa mã hóa trong vòng đời token OAuth 2.0/OIDC**, đặc biệt là **JSON Web Encryption (JWE)**, quản lý **Content Encryption Key (CEK)** và **Key Encryption Key (KEK)**, mô hình tin cậy AS–client–RS, KMS/HSM, xoay khóa, giới hạn quyền giải mã, phòng chống lộ khóa, token theft và replay.

**Tư tưởng xuyên suốt:** *Khóa mã hóa bảo vệ tính bí mật của thông tin trong token; khóa ký bảo vệ tính xác thực và toàn vẹn theo danh tính bên ký. Hai mục tiêu có liên quan nhưng không thay thế nhau.* Dù token đã được mã hóa, RS vẫn phải kiểm **issuer, audience, expiry, scope và quyền truy cập dữ liệu**, đồng thời thiết kế **revocation và sender-binding** khi threat model yêu cầu.

## 1. Bắt đầu từ nhu cầu: mã hóa token để bảo vệ điều gì?

JWT thường được dùng dưới dạng **JWS (JSON Web Signature)**. Payload JWS được **Base64URL encode**, *không phải mã hóa bí mật*. Ai sở hữu token có thể đọc phần payload, dù không thể sửa nó mà vẫn giữ chữ ký hợp lệ.

~~~text
JWS compact (thường có 3 phần):
  BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)

Nội dung payload có thể đọc được sau Base64URL decode.
Chữ ký giúp kiểm tính toàn vẹn và issuer key, KHÔNG che nội dung.
~~~

**JWE (JSON Web Encryption)** dùng để **mã hóa nội dung** cho một hoặc nhiều bên nhận được phép giải mã theo thuật toán/quản lý khóa phù hợp. Một JWE ở compact serialization thường có **5 phần**:

~~~text
BASE64URL(protected-header).
BASE64URL(encrypted-key).
BASE64URL(initialization-vector).
BASE64URL(ciphertext).
BASE64URL(authentication-tag)
~~~

Trong một số thuật toán (ví dụ `alg=dir`), trường `encrypted-key` ở compact JWE **có thể rỗng** vì CEK đã được cung cấp trực tiếp. **Không suy ra JWE hỏng chỉ vì segment đó rỗng**; trình giải mã phải kiểm đúng `alg`/`enc` đã cho phép.

### Khi nào mã hóa access token có ích?

| Tình huống | Rủi ro chính | Mã hóa giúp gì? | Mã hóa không giải quyết gì? |
|---|---|---|---|
| Token đi qua proxy/gateway có thể ghi log header | Claims nhạy cảm bị đọc từ token | Che payload nếu proxy không giữ khóa giải mã | Proxy vẫn có thể đánh cắp **chuỗi bearer token** và dùng lại |
| Client nhận token nhưng chỉ API đích cần đọc claims | Client không nên biết dữ liệu riêng của RS | AS mã hóa cho RS, client giữ token dạng opaque đối với chính mình | Client vẫn có thể forward/replay token nếu là Bearer |
| Multi-tenant service | Lộ claims tenant nếu trộn trust boundary | Key separation có thể thu hẹp phạm vi lộ | Không tự giải quyết phân quyền tenant/object |
| Token lưu trong storage/backup | Người đọc được bản sao storage xem nội dung | Encryption at rest/JWE hỗ trợ confidentiality | Không thay access control, TTL, revoke, backup retention |
| Token phát ở mạng nội bộ dùng TLS | Bị đọc trên đường truyền | TLS đã bảo vệ kênh; JWE còn che nội dung tại bên trung gian | JWE không thay TLS authentication/transport |

**Không mặc định mọi access token phải là JWE.** Một **opaque token** do AS phát cũng có thể che claims đối với client và RS sử dụng introspection; một **JWS** ngắn, tối giản claims, qua TLS cũng có thể đủ với một số threat models. Chọn token format dựa trên **bên nào cần đọc gì, thẩm quyền kiểm token và thời hạn thu hồi**, không vì “mã hóa càng nhiều càng tốt”.

## 2. Phân biệt signing key, encryption key, CEK và KEK

Đây là phần dễ nhầm nhất khi vận hành một Authorization Server.

| Khóa / đối tượng | Tác dụng chính | Ai cần có? | Có nên chia sẻ rộng không? |
|---|---|---|---|
| **Signing private key** | Ký JWS để bên nhận xác minh nguồn phát và tính toàn vẹn | AS/issuer giữ bí mật | **Không**; RS chỉ cần public verification key |
| **Verification public key** | Xác minh chữ ký JWS | RS/RP có thể lấy từ trusted JWKS | **Có thể công khai** theo thiết kế |
| **CEK — Content Encryption Key** | Mã hóa **plaintext của một JWE** bằng thuật toán `enc` | Bên thực hiện content encryption và bên giải mã sau khi lấy/khôi phục CEK | **Không**; thường được sinh mới cho mỗi JWE |
| **KEK — Key Encryption Key** | Bọc/mở CEK bằng key wrap hoặc key management | AS/RS hoặc KMS/HSM tùy topology | Bảo vệ nghiêm, dùng key handles/policy |
| **Recipient public encryption key** | AS dùng để mã hóa/đóng gói CEK gửi cho RS | AS cần public key đáng tin | **Có thể công khai**, nhưng phải xác minh nguồn và purpose |
| **Recipient private decryption key** | RS giải mã CEK/JWE | RS hoặc KMS/HSM được ủy quyền | **Không** phát cho client/gateway không cần giải mã |
| **Direct symmetric encryption key** | Với `alg=dir`, cùng khóa là CEK để mã hóa và giải mã | AS và RS có quyền tương ứng | **Rất hạn chế**: ai giữ khóa có thể giải mã và tạo bản mã được xác thực |
| **Token storage encryption key** | Mã hóa refresh/access token lưu ở client/BFF database | Client/BFF hoặc KMS | Khác key mã hóa JWE ở tầng giao thức |

**CEK khác KEK:** CEK dùng trong **content encryption** (ví dụ AES-256-GCM); KEK dùng để **bảo vệ việc chuyển giao/lưu CEK** (ví dụ RSA-OAEP-256 hoặc AES Key Wrap). Đây là mô hình **envelope encryption**.

### Vì sao không dùng cùng key cho mọi mục đích?

Một key dùng đồng thời để:

- Ký access token.
- Mã hóa refresh token trong database.
- Giải mã JWE access token.
- Mã hóa log, cookie hoặc email.

... sẽ làm phạm vi thiệt hại của một lần lộ khóa rất lớn, khó rotation và dễ tạo lỗi **key/algorithm confusion**. Cần tách key theo **purpose, issuer, recipient, môi trường, tenant (nếu cần) và thời hạn**.

**Ví dụ quy ước tên key (chỉ là nhãn quản trị, không phải bí mật):**

~~~text
as-prod / access-token-signing / sig-v4
rs-payroll-prod / access-token-decryption / enc-v3
bff-payroll-prod / refresh-token-at-rest / store-v2
rs-invoice-prod / access-token-decryption / enc-v6
~~~

Không biến tên key thành một chứng cứ bảo mật. **Phân quyền KMS/HSM** mới quyết định workload nào được phép `Encrypt`, `Decrypt`, `WrapKey`, `UnwrapKey` hoặc ký.

## 3. JWE có hai nhóm thuật toán: `alg` và `enc`

JWE protected header thường có hai tham số riêng:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "payroll-enc-2026-11",
  "typ": "at+jwt",
  "cty": "JWT"
}
~~~

Đây là **protected header minh họa** của một **nested JWS-in-JWE access token** trong profile tương ứng. Một token không nested sẽ có requirements khác; `cty=JWT` dùng khi payload bên trong là JWT khác. `typ=at+jwt` có thể biểu diễn profile access token khi hệ thống áp dụng **RFC 9068**, nhưng phải xác minh đúng profile được AS/RS thỏa thuận.

| Header | Vai trò | Lưu ý |
|---|---|---|
| **`alg`** | Cách quản lý/vận chuyển CEK: direct, key wrapping, key agreement... | Không phải thuật toán mã hóa payload |
| **`enc`** | Thuật toán mã hóa xác thực **nội dung** JWE | Chọn từ allowlist phù hợp, ví dụ `A256GCM` |
| `kid` | Gợi ý khóa để resolver tìm đúng key version | **Không phải chứng thực**: attacker có thể sửa header trước khi xác minh |
| `typ` | Kiểu token/protocol profile | Không chỉ dựa tên typ để xác định token hợp lệ |
| `cty` | Content type của payload; `JWT` khi nested JWT | Với nested JWT, kiểm đúng các lớp theo profile |

### Thuật toán `alg` thường gặp

| `alg` | Cơ chế | Ai có khóa và tác động thiết kế |
|---|---|---|
| **`dir`** | CEK là khóa đối xứng đã được chia sẻ trực tiếp | AS và RS phải giữ cùng secret đúng kích thước; rotation/phân quyền phải chặt |
| **`A256KW`** | AES Key Wrap với KEK đối xứng để bọc CEK | Giữ KEK bí mật; content dùng CEK riêng |
| **`RSA-OAEP-256`** | RSA-OAEP với SHA-256 để mã hóa/đóng gói CEK | AS dùng public key RS; RS giữ private key |
| **`ECDH-ES`** | ECDH key agreement để xác lập CEK trực tiếp theo chuẩn | AS tạo ephemeral key; RS cần private recipient key |
| **`ECDH-ES+A256KW`** | ECDH tạo key wrapping key rồi bọc CEK | Hỗ trợ key agreement và content key separation |

**Tránh dùng `RSA1_5`** (RSAES-PKCS1-v1_5) trong thiết kế JWE mới vì các rủi ro padding oracle; không nới allowlist để chấp nhận thuật toán lạc hậu chỉ vì token cũ chưa được di chuyển. `RSA-OAEP` bản cũ dùng SHA-1 có thể không phù hợp security policy mới; ưu tiên bộ thuật toán được thỏa thuận hiện đại và được thư viện hỗ trợ.

### Thuật toán `enc` thường gặp

| `enc` | Ý nghĩa | Yêu cầu vận hành |
|---|---|---|
| **`A128GCM`** | AES-128-GCM authenticated encryption | CEK 128-bit, nonce/IV độc nhất trên cùng key |
| **`A256GCM`** | AES-256-GCM authenticated encryption | CEK 256-bit, thường IV 96-bit, tag xác thực 128-bit theo JWE profile |
| **`A128CBC-HS256` / `A256CBC-HS512`** | Kết hợp AES-CBC và HMAC theo thuật toán JWE đã quy định | Phải dùng thư viện JOSE an toàn; không tự ráp CBC + HMAC |

Trong triển khai mới, **AES-GCM qua JOSE/JCA library đã được kiểm thử** thường là lựa chọn hợp lý khi policy và compatibility cho phép. **Đừng tự thiết kế scheme encryption riêng** từ AES-CBC, tự nối tag hoặc không kiểm tag.

### `alg` không thể thay `enc`

~~~text
Header: alg = RSA-OAEP-256
        enc = A256GCM

Ý nghĩa:
  AS sinh CEK phù hợp A256GCM.
  AS dùng RSA-OAEP-256 với public key recipient để bọc CEK.
  AS dùng CEK mã hóa JWT content bằng A256GCM.
  RS dùng private key mở CEK, rồi giải mã AEAD content.
~~~

Đừng gọi `RSA-OAEP-256` là “thuật toán mã hóa toàn bộ payload JWT”. Trong JWE phổ biến, RSA **bảo vệ CEK**; nội dung dài được mã hóa bằng **symmetric authenticated encryption**.

## 4. Cách CEK và KEK đi qua vòng đời một JWE

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant KMS as Key Service / KMS
    participant Client as OAuth Client
    participant RS as Payroll API
    AS->>AS: Tạo access-token claims và áp profile
    AS->>AS: Ký JWT bằng signing key (nếu nested JWS)
    AS->>AS: Sinh CEK ngẫu nhiên cho JWE
    AS->>KMS: Wrap CEK bằng key quản lý recipient
    KMS-->>AS: Encrypted CEK / key-agreement output
    AS->>AS: AEAD encrypt payload với CEK, IV và protected AAD
    AS-->>Client: Compact JWE (5 segments)
    Client->>RS: Authorization: Bearer <encrypted-access-token>
    RS->>RS: Kiểm JOSE protected header và key policy
    RS->>KMS: Unwrap/decrypt CEK bằng private/KEK key
    KMS-->>RS: CEK hoặc plaintext theo thiết kế KMS
    RS->>RS: AEAD decrypt + kiểm authentication tag
    RS->>RS: Verify nested signature nếu profile yêu cầu
    RS->>RS: Kiểm iss, aud, exp, nbf, scope và quyền nghiệp vụ
    RS-->>Client: Trả kết quả nếu mọi kiểm tra đạt
~~~

Sơ đồ mô tả **mô hình envelope encryption**, không bắt buộc KMS phải xuất CEK raw vào ứng dụng: KMS/HSM có thể **thực hiện cryptographic operation và trả handle/plaintext theo security boundary của sản phẩm**. Nếu CEK cần xuất hiện trong RAM, phải bảo vệ thời gian sống, không log và tránh copy không cần thiết.

### Các bước kỹ thuật với `RSA-OAEP-256` + `A256GCM`

1. RS tạo cặp khóa encryption, giữ **private key** trong KMS/HSM/keystore được bảo vệ.
2. RS/tenant công bố **public encryption key** qua kênh được AS tin cậy; ánh xạ đúng issuer, recipient và `kid`.
3. AS sinh **CEK ngẫu nhiên 256-bit** dùng cho content cipher `A256GCM`.
4. AS bọc CEK bằng **public key RS** theo `RSA-OAEP-256`.
5. AS sinh **IV/nonce** đúng profile, mã hóa content bằng CEK/AES-GCM và gắn **protected header vào AAD**.
6. AS trả JWE cho client; client không có private key nên **không được đọc claims**.
7. RS dùng private key để mở CEK; kiểm **authentication tag**, decode claims, kiểm JWT/JWS bên trong nếu có và toàn bộ security policy.

**Đừng giải mã JWE tại API gateway rồi forward claims thô qua header không được bảo vệ**, trừ khi kiến trúc có trust boundary rõ, mTLS giữa gateway/backend, header stripping/rewriting và chính sách phân quyền/kiểm integrity. Nếu không, attacker có thể tự đưa header `X-User-Role: admin` vào backend.

## 5. Direct symmetric key (`alg=dir`): đơn giản nhưng phạm vi tin cậy lớn

Khi `alg=dir`, AS và RS dùng một khóa đối xứng đã chia sẻ trực tiếp làm CEK. Với `enc=A256GCM`, khóa cần có **256 bit (32 byte)**.

~~~json
{
  "alg": "dir",
  "enc": "A256GCM",
  "kid": "shared-as-payroll-v3"
}
~~~

Ưu điểm:

- Không cần RSA/ECDH key management cho mỗi token.
- Encryption/decryption nhanh và dễ phối hợp trong môi trường kiểm soát tốt.
- Ít overhead của wrapped CEK.

Nhược điểm lớn:

- **Mọi nơi giữ shared secret có thể giải mã token**. Với AEAD direct, bên giữ cùng key còn có khả năng **tạo ciphertext/tag hợp lệ**; do đó encryption không thay thế **chữ ký của AS** làm bằng chứng issuer.
- Chia sẻ secret qua quá nhiều RS/tenant làm tăng blast radius và khó tách quyền.
- Rotation phải phối hợp cả AS và RS; khi một RS bị compromise, secret dùng chung có thể ảnh hưởng các RS khác.
- Khóa không thể công bố như public JWKS. `kty=oct` chứa secret, không được xuất public qua endpoint.

### Khi nào `dir` hợp lý?

Một hệ thống nội bộ nhỏ với **một AS và một RS**, có secret distribution chặt, key versioning, AEAD library đúng và threat model chấp nhận shared-secret boundary. Ngay cả vậy, nếu cần chứng minh chỉ AS phát access token, có thể cần **JWS bên trong JWE** hoặc một cơ chế origin-authentication rõ ràng.

### Khi nào nên tránh shared-secret?

- Nhiều tổ chức/tenant không có chung trust boundary.
- Một RS không được phép tạo token có vẻ như do AS phát.
- Có nhu cầu công bố encryption key cho AS nhưng giữ private decryption key độc quyền tại RS.
- Cần rotation độc lập ở từng recipient, security team kiểm quyền KMS/HSM theo workload.

Trong các trường hợp này, **public-key encryption/key agreement** cho recipient có thể tạo ranh giới tin cậy dễ quản lý hơn.

## 6. Asymmetric recipient key: public để mã hóa, private để giải mã

Với `RSA-OAEP-256` hoặc cơ chế ECDH-ES phù hợp, **recipient RS** giữ private key, **AS dùng public key đã được xác minh** để mã hóa/bọc CEK.

~~~text
AS:
  trusted recipient public encryption key (RS Payroll)
  AS signing private key (chỉ dùng cho signing)

Client:
  encrypted access token (Bearer)
  KHÔNG có Payroll private decryption key

Payroll RS:
  Payroll private decryption key / KMS decrypt permission
  AS public verification key (nếu signed JWT nested)
~~~

### Hai loại public key không hoán đổi tùy ý

| Public key | Dùng cho | Private key tương ứng ở đâu? |
|---|---|---|
| **AS signing public key** | RS xác minh **chữ ký AS** trên JWS | **AS** giữ signing private key |
| **RS encryption public key** | AS **mã hóa CEK cho RS** | **RS/KMS** giữ decryption private key |

Một JWKS có thể chứa nhiều JWKs cho các mục đích khác nhau, nhưng **`kid` và `use`/`key_ops` không thể tự thay trust relationship và algorithm allowlist**. RS/AS phải chọn key theo **issuer, recipient, purpose, alg và registration**, không chọn “bất cứ key nào trùng `kid`”.

### Key pair và quyền truy cập KMS

Lý tưởng, RS có quyền **Decrypt/Unwrap** qua một key handle, nhưng không có quyền **ExportPrivateKey**. AS có public recipient key được phân phối tin cậy, không được đọc private key RS. Client cuối không cần biết private key.

Một attacker chiếm client có thể lấy chuỗi bearer token, nhưng **không giải mã nội dung** nếu không có recipient key. Dù vậy, attacker vẫn có thể **replay token** tại Payroll API nếu RS chấp nhận Bearer và token còn hạn. Mã hóa confidentiality **không phải sender-constraining**.

## 7. Protected header, `kid` và nguy cơ key confusion

Để giải mã JWE, thư viện thường xem header để biết chọn khóa nào. Đây là điểm đầu vào có thể bị attacker kiểm soát **trước khi kiểm authenticated encryption tag**.

### `kid` là gợi ý tra khóa, không phải quyền

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "payroll-key-v3"
}
~~~

Một RS nên:

1. Chỉ chọn khóa từ **key ring cấu hình trước** cho Payroll RS/issuer/profile.
2. So `alg`/`enc` với **allowlist**, loại bỏ thuật toán không được hỗ trợ dù header đề nghị.
3. Giới hạn độ dài/format của `kid` và chống path traversal, SQL injection, remote URL injection nếu resolver dùng nó làm lookup.
4. Không dùng `jku`/`x5u`/`jwk` trong token để tự fetch key hay chấp nhận key công khai mới khi chưa có trust policy.
5. Kiểm **AEAD tag** và, nếu có nested JWT, chữ ký/issuer/audience trước khi tin bất kỳ claim nào.

### Tấn công key substitution minh họa

~~~text
Attacker supplies JWE header:
  kid = https://attacker.invalid/my-key.json

UNSAFE decryptor:
  tải key từ kid URL bất kỳ
  chọn thuật toán theo header không có allowlist
  tin claims khi decrypt thành công

SAFER decryptor:
  kid chỉ index key ring nội bộ cho trusted recipient
  alg/enc pinned by registration/policy
  unknown key -> reject, no remote fetch
~~~

**Decryption thành công chưa đủ để kết luận “token được AS phát hợp lệ”**, nhất là khi content encryption key được dùng chung giữa nhiều bên. Nếu token profile yêu cầu issuer authentication, kiểm **JWS signature bên trong JWE** hoặc cơ chế mật mã tương đương với thẩm quyền nguồn phát được định nghĩa rõ.

### JWKS công khai không được chứa symmetric secret

~~~json
{
  "kty": "RSA",
  "kid": "payroll-enc-public-v3",
  "use": "enc",
  "alg": "RSA-OAEP-256",
  "n": "<public-modulus-redacted>",
  "e": "AQAB"
}
~~~

Đây là **JWK public key minh họa**. Không bao gồm `d`/`p`/`q` private RSA parameters. Với symmetric JWK `{"kty":"oct","k":"..."}`, trường `k` là **secret key material** và **không được** publish qua JWKS không được bảo vệ.

### Key rotation và `kid`

`kid` phải giúp phân biệt các **key versions** đang active/decrypt-only/retired; không coi nó là một mật khẩu. Khi key mới được phát hành, AS bắt đầu dùng `kid` mới, nhưng RS có thể cần giữ private key cũ một thời gian **để giải mã JWE chưa hết hạn**. Phần retention này sẽ được phân tích riêng ở mục rotation.

## 8. AES-GCM: nonce, authentication tag và key reuse

**AES-GCM** là chế độ **Authenticated Encryption with Associated Data (AEAD)**. Nó bảo vệ cả:

1. **Confidentiality:** người không có CEK không đọc được plaintext.
2. **Integrity/authenticity theo khóa đối xứng:** người không có CEK không thể tạo ciphertext/tag hợp lệ với xác suất thực tế hữu dụng khi triển khai đúng.

Nhưng **GCM không chứng minh danh tính AS** nếu nhiều thực thể cùng biết CEK. “Người có thể tạo ciphertext hợp lệ” và “AS là issuer được RS tin cậy” là hai khái niệm riêng.

### Nonce/IV phải duy nhất với mỗi CEK

Trong profile JWE `A256GCM`, IV thông thường là **96 bit (12 byte)** và authentication tag **128 bit (16 byte)** theo định nghĩa JOSE. **Tái sử dụng cùng IV dưới cùng một key trong GCM là sai lầm nghiêm trọng**, có thể phá tính bí mật và tính toàn vẹn.

~~~text
CEK = random 256-bit key K1

JWE #1:
  IV = N1
  Ciphertext, tag = AES-GCM(K1, N1, payload1, AAD1)

JWE #2:
  IV = N2, with N2 != N1 under K1
  Ciphertext, tag = AES-GCM(K1, N2, payload2, AAD2)

NEVER:
  reuse K1 + N1 for two different encryption operations
~~~

### Sinh IV ngẫu nhiên có phải bảo đảm 100% duy nhất?

Không. IV 96-bit sinh bằng **CSPRNG** làm xác suất trùng rất nhỏ ở mức sử dụng phù hợp, nhưng không biến tính độc nhất thành chứng minh toán học. Với số lượng mã hóa rất lớn **dưới cùng key**, birthday collision risk tăng. Chính sách phải giới hạn số operation per key, theo chuẩn/khuyến nghị của thư viện và security team; khi throughput cao có thể dùng nonce allocation/counter scheme được thiết kế đúng, hoặc **CEK mới cho mỗi token** trong envelope encryption để giảm rủi ro IV reuse trên cùng key.

**Không dùng timestamp, user ID, request ID tự khai hoặc một hằng số như `000000000000` làm IV** nếu không có thiết kế bảo đảm uniqueness thật sự. Một timestamp có thể trùng ở các worker phát token đồng thời.

### Authentication tag là bắt buộc

RS phải **từ chối ciphertext nếu tag không hợp lệ**. Không trả plaintext giải mã dở dang, không “thử bỏ qua lỗi GCM”, không tự xử lý exception theo cách tiết lộ từng byte plaintext.

~~~text
Authenticated Decryption:
  parse JOSE header
  choose trusted key by policy
  recover CEK
  verify AES-GCM tag and protected AAD
  only if authenticated -> release plaintext to JWT parser
~~~

JOSE protected header được đưa vào **Additional Authenticated Data (AAD)**, giúp phát hiện thay đổi header sau mã hóa. Nhưng trước khi tag được kiểm, **không dùng header như một quyết định authorization**; resolver được phép tham khảo header để tìm khóa trong allowlist có giới hạn.

### Encryption không thay được TLS

JWE có thể che claims khỏi một số hệ thống trung gian, nhưng **TLS vẫn cần thiết** để bảo vệ token bearer trên đường truyền, chống MITM, xác thực server endpoint và bảo vệ credential khác. Một attacker không đọc được JWE payload vẫn có thể **copy nguyên JWE và replay** nếu RS nhận Bearer.

## 9. Nested JWS-in-JWE: vừa xác minh nguồn phát vừa che claims

Với **signed then encrypted** (ký trước, mã hóa sau), AS:

1. Tạo JSON JWT claims (issuer, subject, audience, scope, expiration...).
2. Ký JWT thành **JWS compact** bằng **AS signing key**.
3. Đặt JWS compact vào JWE payload, set `cty=JWT` theo nested JWT profile.
4. Mã hóa JWE cho recipient bằng **recipient encryption key/CEK–KEK flow**.
5. RS giải mã JWE, sau đó **xác minh chữ ký JWS bên trong** bằng AS verification key đã tin cậy.
6. RS kiểm token profile và authorization.

~~~mermaid
flowchart TD
    Claims["AS: JWT claims iss/aud/sub/scope/exp"] --> Sign["AS sign -> JWS (signature)"]
    Sign --> Enc["AS encrypt JWS payload -> JWE (confidentiality)"]
    Enc --> Send["Client carries encrypted access token"]
    Send --> Dec["RS decrypt JWE with recipient key"]
    Dec --> Verify["RS verify inner JWS with AS signing public key"]
    Verify --> Policy["RS check iss/aud/exp/scope, sender binding and data permissions"]
    Policy --> Result["Allow or deny API request"]
~~~

### Tại sao decrypt thành công không chứng minh issuer?

Giả sử cả AS và RS cùng giữ một **direct symmetric key**. RS có thể tạo ciphertext/tag hợp lệ vì nó giữ cùng key. Nếu payload không có chữ ký hoặc issuer authentication khác, một thành phần bị compromise giữ key có thể tạo token có vẻ hợp lệ để RS khác chấp nhận. Ký JWS bằng **AS-only signing key** tạo một lớp bằng chứng nguồn phát riêng biệt.

Tuy nhiên, nested signing phải được thiết kế đúng: **kiểm JWS bằng key và algorithm đã pin cho issuer**, không dùng key do plaintext hoặc JWE header tự chỉ định; kiểm `iss`, `aud`, `typ`/profile, `exp`, `nbf` và những ràng buộc bổ sung.

### Khi nào chỉ encryption có thể đủ?

Trong một protocol riêng có **một key-ownership boundary** và integrity/authentication contract đủ mạnh, AEAD có thể là một phần của cơ chế xác thực nguồn gửi. Nhưng **không áp dụng suy luận này mặc định cho OAuth/OIDC JWT access token**: phải tuân profile token được AS/RS thống nhất. Với **RFC 9068 JWT access tokens**, các quy tắc ký/validation của profile vẫn cần thực hiện; mã hóa được thêm để bảo vệ confidentiality, không xóa yêu cầu profile đã quy định.

### Dấu hiệu token substitution

~~~text
Attack:
  AS signed ID token (aud = client-web)
  Attacker presents it as API access token

Even if JWE decrypts and inner JWS verifies:
  RS MUST reject wrong token type/purpose/audience.

Other attack:
  JWE encrypted for Invoice API forwarded to Payroll API

Payroll:
  should not have Invoice recipient key;
  reject if unexpected key, issuer, audience or profile.
~~~

**Mã hóa đúng đích có thể hỗ trợ audience isolation**, nhưng **không thay phép kiểm `aud`**. Một RS có thể được cấp nhiều key vì yêu cầu vận hành, và token có thể có nhiều recipients trong JWE JSON serialization; chính sách authorization vẫn quyết định token có dành cho API đó hay không.

## 10. Phân phối khóa: JWKS, KMS, HSM và secret manager

Khóa không an toàn chỉ vì “được lưu trong môi trường production”. Phải xác định **đường đi của key material, ai được gọi operation nào, audit và cách rotation**.

### Bốn mô hình lưu trữ/quản lý

| Mô hình | Phù hợp | Rủi ro/điểm cần kiểm |
|---|---|---|
| **Environment variable/plain config secret** | Demo/lab hoặc môi trường hạn chế | Có thể lộ qua process dump, debug, deployment manifest, CI log; tránh hardcode |
| **Secret manager** | Phân phối symmetric key/credential được kiểm soát | IAM/ACL, versioning, lease/rotation, audit, vùng nhớ ứng dụng |
| **KMS** | Encrypt/decrypt/wrap/unwrap qua key handle và IAM | Quyền service, quota/latency, key policy, outage, ciphertext/key version semantics |
| **HSM** | Khóa private/KEK cần hạn chế export và thao tác crypto trong phần cứng | Khả năng thuật toán, throughput, cluster HA, key recovery và audit |

Public encryption key có thể được công bố qua **trusted JWKS, pinned certificate hoặc registration metadata**, nhưng hệ thống phải kiểm **origin, trust anchor, key purpose/algorithm**. Một public key đến từ attacker **không phải** recipient key đáng tin chỉ vì có format RSA JWK hợp lệ.

### Tách quyền theo service principal

~~~text
AS service account:
  can read verified RS public encryption keys
  can sign with AS access-token signing handle
  can encrypt/wrap CEK to approved recipients
  cannot export RS private decryption key

Payroll RS service account:
  can unwrap/decrypt for Payroll encryption key
  can read AS public signing keys
  cannot sign token as AS
  cannot decrypt Invoice-only tokens

Invoice RS service account:
  can decrypt Invoice encryption key
  cannot decrypt Payroll-only tokens
~~~

Áp dụng **least privilege và separation of duties** để một compromise không biến thành mất bí mật toàn bộ tokens.

### KMS key alias khác key version

Ví dụ:

~~~text
Alias:     payroll-jwe-decrypt-current
Version:   key-2026-10
New:       key-2026-11

AS encrypt new JWE to key-2026-11.
RS keeps key-2026-10 in decrypt-only state
until all valid JWE referencing it have expired.
~~~

Một alias có thể trỏ key hiện tại, nhưng **token cũ thường đã mã hóa cho key version cụ thể**. Nếu alias bị trỏ sang key mới và key cũ bị xóa ngay, RS có thể không giải mã được token chưa hết `exp`. Cần **versioned keyring** và retirement schedule.

### Backup và disaster recovery

Nếu private encryption key bị mất vĩnh viễn, **không thể giải mã các JWE đã phát** cho key đó, trừ khi có recipient khác/key backup phù hợp. Để khôi phục:

- Dùng **KMS/HSM HA và backup/recovery được quản trị**, phù hợp chính sách key export.
- Kiểm DR diễn tập việc giải mã token cũ và rotation giữa region.
- Không xuất private key plaintext chỉ để “backup dễ dàng”.
- Có quy trình thu hồi/tái cấp token hợp lệ khi cần bỏ key do incident.

Không tạo single point of failure bằng một file `private.pem` duy nhất ở một pod.

## 11. Key separation theo issuer, resource, tenant và environment

Để xác định key scope, hãy đi theo mô hình tin cậy:

~~~text
Issuer (AS) -> token class -> recipient (RS) -> environment
               -> tenant/policy boundary (khi cần) -> key version
~~~

| Chiều phân vùng | Vì sao quan trọng? | Ví dụ |
|---|---|---|
| **Environment** | Không cho test/staging decrypt production token | `payroll-prod-v3` khác `payroll-test-v2` |
| **Recipient/RS** | Chỉ API đúng đích đọc được claims | Payroll key khác Invoice key |
| **Issuer/trust domain** | Tránh nhầm key từ hai OP/AS | AS-A token không tự được AS-B RS tin |
| **Token purpose** | Không dùng refresh token key như access token JWE key | Key at-rest refresh khác JWE access token |
| **Tenant** | Hạn chế blast radius ở môi trường isolation cao | Key tenant A khác tenant B khi policy cần |
| **Key version** | Rotation mà vẫn giải mã token còn hạn | `enc-v3` active, `enc-v2` decrypt-only |
| **Algorithm use** | Tránh key-confusion và reuse chéo primitive | Signing key khác encryption key |

**Không nhất thiết mỗi user phải có một key riêng.** Per-user key có thể tăng độ phức tạp, phân phối, rotation và availability không tương xứng. Chọn granularity dựa trên **asset sensitivity, trust boundary, compliance và blast-radius SLO**.

### Per-audience JWE

Nếu Invoice API và Payroll API dùng **private decryption keys riêng**, AS có thể mã hóa cho từng recipient tương ứng; đây là một lớp giảm quyền đọc của API không liên quan. Nhưng nếu token được cấp `aud=payroll-api` và AS lại mã hóa cho Invoice API vì key mapping sai, decryption thành công ở Invoice **không cho phép** nó bỏ qua claim audience. Luôn kiểm **`aud` exact match** với chính RS.

### Token không có user thì key có khác không?

Grant `client_credentials` tạo service identity; access token có thể không có user subject. Quyết định encryption key dựa vào **recipient trust boundary và token profile**, không phụ thuộc phải có `sub` của end user. Không chia sẻ key với mọi microservice chỉ vì token là M2M.

## 12. Key lifecycle: từ tạo, kích hoạt đến hủy an toàn

Một encryption key có vòng đời quản trị riêng, không phải chỉ một dòng `kid`.

~~~mermaid
stateDiagram-v2
    [*] --> GENERATED: CSPRNG/KMS tạo key
    GENERATED --> REGISTERED: Public key / trust metadata đã đăng ký
    REGISTERED --> ACTIVE: AS bắt đầu encrypt bằng key version mới
    ACTIVE --> DECRYPT_ONLY: Dừng phát JWE mới với key này
    DECRYPT_ONLY --> RETIRED: Không còn token hợp lệ/khả năng cần giải mã
    RETIRED --> DESTROYED: Xóa theo policy và phê duyệt
    ACTIVE --> COMPROMISED: Phát hiện nghi lộ/vi phạm
    DECRYPT_ONLY --> COMPROMISED: Phát hiện nghi lộ
    COMPROMISED --> QUARANTINED: Cấm sử dụng, thay key và điều tra
    QUARANTINED --> DESTROYED: Theo incident/retention policy
    DESTROYED --> [*]
~~~

Đây là **mô hình vận hành minh họa**, không phải state machine bắt buộc của JWE. Không phải KMS nào cũng có trạng thái `DECRYPT_ONLY` nguyên bản; có thể thực hiện bằng policy của AS/RS và key alias/permissions.

### Lộ trình rotation có thứ tự

1. **Tạo key version mới** bằng KMS/HSM/CSPRNG đủ mạnh.
2. **Đăng ký và phân phối public/recipient key** tới AS theo kênh tin cậy; nếu symmetric, phân phối secret bằng IAM/secret manager an toàn.
3. **Triển khai khả năng decrypt mới ở RS** trước hoặc đồng thời với việc AS chuyển encrypt; xác minh bằng test vector.
4. **Chuyển AS sang encrypt bằng key mới** (new `kid`); dừng tạo token bằng key cũ.
5. **Giữ key cũ trong decrypt-only state** tới khi mọi token còn hợp lệ liên quan qua expiry/grace/clock skew đều đã hết và các yêu cầu vận hành được xử lý.
6. **Gỡ public/active routing và retire key cũ**, dọn cache key material, giới hạn quyền decrypt cũ.
7. **Audit/verify** không còn phát token bằng key cũ, thông báo các consumers và hoàn tất destruction theo policy.

### Cách ước lượng retention key cũ

Giả sử:

~~~text
T_rotate = 12:00
Max access-token remaining lifetime at rotation = 15 phút
Clock skew + propagation + processing budget = 2 phút

Keep decrypt-only old key until at least 12:17
if token policy and service recovery contracts allow.
~~~

Con số 17 phút là **ví dụ**, không phải mặc định chuẩn. Nếu có **refresh token mã hóa bằng chính key đó, token dài hạn, encrypted backups hoặc queue messages**, retention có thể khác nhiều; nên **không dùng cùng key** để tránh một key bị giữ hàng tháng chỉ vì mục đích khác.

### Rotation không giống revocation

Chuyển AS sang encryption key mới **không tự làm token đã phát bằng key cũ hết hạn/thu hồi**. Nếu RS vẫn giữ key cũ, token cũ vẫn có thể được decrypt; nếu bỏ key cũ sớm, token có thể bị từ chối do **không giải mã được** ngay cả khi `exp` chưa tới. Đó là **key decommissioning policy**, không đồng nghĩa AS/RS đã thực thi OAuth token revocation.

Nếu mục tiêu là thu hồi token bị đánh cắp, cần thêm **revoke state/introspection/denylist/sender constraint** theo chính sách; key rotation có thể là bước trong incident nhưng không thay revocation.

## 13. Nếu encryption key bị lộ: điều gì thực sự bị ảnh hưởng?

**Không phải mọi sự cố key leak đều có cùng hậu quả.** Hãy phân biệt key bị lộ và ai có quyền dùng nó.

| Sự cố | Kẻ tấn công có thể làm gì? | Điều chưa được tự kết luận |
|---|---|---|
| **Lộ RS private decryption key** | Giải mã các JWE đã thu được mã hóa cho key đó, trong phạm vi thuật toán/trust contract | Không tự có AS signing private key, không tự ký JWS hợp lệ |
| **Lộ direct symmetric key (`dir`)** | Giải mã và có thể tạo ciphertext/tag hợp lệ dưới cùng key | Nếu nested JWS bắt buộc, vẫn không ký được JWS AS hợp lệ |
| **Lộ AS signing private key** | Có thể giả chữ ký JWS phù hợp key/alg | Không tự có recipient private decryption key để đọc mọi JWE |
| **Lộ public encryption key RS** | Bên khác có thể mã hóa dữ liệu gửi cho RS | Không giải mã được JWE nếu private key vẫn bí mật |
| **Lộ CEK của một JWE** | Giải mã nội dung JWE cụ thể; có thể tạo nội dung AEAD hợp lệ với key đó | Không tự giải mã được toàn bộ JWE khác nếu chúng dùng CEK riêng |
| **Lộ shared KEK** | Có thể mở nhiều wrapped CEKs bị thu thập trong phạm vi key đó | Không tự qua được issuer signature/authorization nếu RS kiểm đúng |
| **Lộ access token ciphertext, không lộ key** | Có thể **replay Bearer token** nếu RS chấp nhận | Không nhất thiết đọc được claims nội bộ |
| **KMS decrypt permission bị lạm dụng** | Có thể gọi API giải mã cho ciphertext được phép, kể cả khi key không exportable | Không nên coi “không xuất được key” là hết mọi rủi ro |

### Phân loại mức độ sự cố

**Confidentiality incident:** Key bị lộ giúp attacker đọc token lịch sử trong logs, queues, backups hoặc network captures mà trước đó chưa đọc được. Mã hóa **không thể làm cho các bản ciphertext đã bị thu thập trở lại bí mật** sau khi private key/KEK bị lộ.

**Forgery/integrity incident:** Với shared direct AEAD key hoặc key dùng sai mục đích, attacker có thể tạo ciphertext hợp lệ. Khi nội dung còn phải có **AS JWS signature hợp lệ**, khả năng giả claims sẽ được hạn chế bởi việc attacker **không** có AS signing private key.

**Availability incident:** Nếu KMS disable/delete key sai thời điểm, RS có thể không giải mã được token hợp lệ, gây outage diện rộng. Incident response cần cân bằng containment với **khả năng cấp lại token và khôi phục các phiên hợp lệ**.

### Kế hoạch phản ứng

1. **Cách ly quyền sử dụng key**: khóa IAM principal, thay credential, chặn decrypt/wrap khi cần.
2. Xác định **key version, issuer, recipients, token classes, thời gian** và nơi ciphertext/backup đã xuất hiện.
3. Tạo version mới ở KMS/HSM, **phân phối đúng thứ tự** để AS mã hóa bằng key mới và RS giải mã được.
4. Nếu signing key bị lộ, xử lý như một **issuer compromise**: thay signing key, RS cập nhật trust/revocation/denylist, xem xét token đã cấp.
5. Nếu encryption key bị lộ, xem xét **bảo mật dữ liệu claims lịch sử**; rotation chỉ bảo vệ ciphertext phát về sau, **không thu hồi tính bí mật của dữ liệu cũ**.
6. Phối hợp **OAuth grant/token revocation** nếu access/refresh token đã bị lấy, có replay hoặc cần chặn phiên.
7. Kiểm audit KMS operations, token issuance, RS acceptance và log leakage; tuyệt đối không dán raw keys/tokens vào ticket.
8. Đo lại thời gian revoke propagation, key propagation và phiên bị ảnh hưởng; kiểm lại backup/DR policy.

## 14. Java 17: AES-GCM bằng JCA để hiểu CEK và IV

Đoạn code sau **chỉ minh họa authenticated encryption của một payload byte array**, không tự tạo JWE compact và không thay JOSE/JWT implementation. Nó giúp làm rõ vai trò của CEK, IV, ciphertext và tag.

~~~java
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

final class AesGcmExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int IV_BYTES = 12;       // 96-bit IV
    private static final int TAG_BITS = 128;      // 128-bit tag

    record Sealed(byte[] iv, byte[] ciphertextAndTag) {}

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static Sealed encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] associatedData) throws Exception {

        byte[] iv = new byte[IV_BYTES];
        RNG.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(associatedData);

        // Trong JCA, doFinal trả ciphertext || tag.
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new Sealed(iv, ciphertextAndTag);
    }

    static byte[] decrypt(
            SecretKey key,
            Sealed sealed,
            byte[] associatedData) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, sealed.iv()));
        cipher.updateAAD(associatedData);

        // Sai key, IV, AAD, ciphertext hoặc tag phải fail.
        return cipher.doFinal(sealed.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        SecretKey cek = newAes256Key();
        byte[] payload =
            "training-only-sensitive-claims".getBytes(
                StandardCharsets.UTF_8);
        byte[] aad =
            "trusted-context:payroll-api".getBytes(
                StandardCharsets.UTF_8);

        Sealed message = encrypt(cek, payload, aad);
        byte[] decrypted = decrypt(cek, message, aad);

        if (!Arrays.equals(payload, decrypted)) {
            throw new IllegalStateException("Unexpected result");
        }
        Arrays.fill(decrypted, (byte) 0);
        Arrays.fill(payload, (byte) 0);
    }

    private AesGcmExample() {}
}
~~~

### Điều gì phải thay đổi nếu triển khai thật?

- **Không tự tạo JWE bằng cách nối IV/ciphertext/tag thủ công.** JWE có protected header, `alg`, `enc`, key management, Base64URL và AAD semantics chuẩn. Dùng **Nimbus JOSE+JWT/jose4j** hoặc thư viện JOSE được bảo trì, thay vì dùng ví dụ JCA làm OAuth token parser.
- `newAes256Key()` sinh một **CEK trong bộ nhớ** để minh họa; production nên quản lý encryption/wrapping theo KMS/HSM và entropy chuẩn. Không lưu key raw vào source hoặc console.
- IV 12 byte sinh ngẫu nhiên có collision probability nhỏ khi usage phù hợp nhưng **không tự bảo đảm uniqueness tuyệt đối**. Với throughput lớn và key được tái sử dụng, cần key lifetime/nonce management đúng chuẩn.
- `cipher.updateAAD` ràng buộc dữ liệu phụ; AAD **không được tin nếu do caller tự khai**. Trong JWE, JOSE library có quy tắc protected header AAD riêng.
- `record Sealed` chứa `byte[]` mutable; ví dụ không xử lý secure memory/defensive copy. Production tránh trả raw key/secret ra quá nhiều lớp và sao chép ngoài ý muốn.
- Khi decrypt, phải **xử lý AEAD tag failure là thất bại**, không trả plaintext. Không log exception kèm key/ciphertext/claims nhạy cảm.
- `Arrays.fill` giúp giảm thời gian một số byte array tồn tại nhưng **không bảo đảm xóa mọi bản sao trong JVM/JCA/GC**, đặc biệt với immutable `String`/key handles.

### Kiểm tra tamper detection

~~~text
Encrypt(P, CEK, IV, AAD) -> C || TAG

Attempt A: Decrypt(C, CEK, same IV, same AAD) -> P
Attempt B: Decrypt(C modified, CEK, IV, AAD) -> FAIL
Attempt C: Decrypt(C, wrong CEK, IV, AAD) -> FAIL
Attempt D: Decrypt(C, CEK, wrong IV, AAD) -> FAIL
Attempt E: Decrypt(C, CEK, IV, wrong AAD) -> FAIL
~~~

Nếu bất kỳ attempt B–E được ứng dụng **bỏ qua lỗi để dùng plaintext**, hệ thống đã phá yêu cầu authenticated encryption.

## 15. Java/Nimbus JOSE: minh họa JWE RSA-OAEP-256 + A256GCM

Một ví dụ gần hơn với JWE thật có thể sử dụng **Nimbus JOSE+JWT**. Mã sau giả định:

- `recipientPublicKey` là **RSA public key của RS đã được xác minh** theo registration, không lấy từ HTTP request.
- `recipientPrivateKey` là private key tương ứng từ trusted keystore hoặc KMS integration. Trong hệ thống HSM non-exportable, thay `RSADecrypter` bằng adapter crypto phù hợp để không phải export private key.
- `signedJwtCompact` là **JWS đã được AS ký hợp lệ** theo token profile riêng.
- `expectedKid`, issuer, recipient và algorithms được cấu hình, không đọc tùy ý từ token.

~~~java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSAEncrypter;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

final class PayrollJweCodec {
    static String encryptForPayroll(
            String signedJwtCompact,
            RSAPublicKey recipientPublicKey,
            String trustedRecipientKid) throws Exception {

        JWEHeader header = new JWEHeader.Builder(
                JWEAlgorithm.RSA_OAEP_256,
                EncryptionMethod.A256GCM)
            .keyID(trustedRecipientKid)
            .contentType("JWT")
            .build();

        JWEObject jwe = new JWEObject(
            header, new Payload(signedJwtCompact));

        jwe.encrypt(new RSAEncrypter(recipientPublicKey));
        return jwe.serialize();
    }

    static String decryptForPayroll(
            String compactJwe,
            RSAPrivateKey recipientPrivateKey,
            String expectedKid) throws Exception {

        JWEObject jwe = JWEObject.parse(compactJwe);
        JWEHeader header = jwe.getHeader();

        // Header chưa được xác thực tại bước này:
        // chỉ dùng nó để CHẶN cấu hình không được phép và
        // chọn trusted local key.
        if (!JWEAlgorithm.RSA_OAEP_256.equals(header.getAlgorithm()) ||
            !EncryptionMethod.A256GCM.equals(
                header.getEncryptionMethod()) ||
            !expectedKid.equals(header.getKeyID()) ||
            !"JWT".equals(header.getContentType())) {
            throw new SecurityException("Unexpected JWE profile");
        }

        jwe.decrypt(new RSADecrypter(recipientPrivateKey));
        // AEAD tag đã phải được xác minh trước khi trả plaintext.
        return jwe.getPayload().toString();
    }

    private PayrollJweCodec() {}
}
~~~

**Quan trọng:** `decryptForPayroll()` chỉ trả **chuỗi JWS bên trong**. Caller vẫn phải:

1. Parse JWS bằng library tin cậy.
2. **Xác minh JWS signature/algorithm** bằng signing key AS đúng issuer, không dùng `kid` từ header để tự tải remote key.
3. Kiểm profile/token purpose, `iss`, `aud=payroll-api`, `exp`, `nbf`, `scope`, `client_id/sub` và business authorization.
4. Nếu token là **DPoP/mTLS-bound**, kiểm proof/chứng chỉ caller riêng tại request.
5. Kiểm revocation/introspection/denylist nếu policy yêu cầu; mã hóa không thay việc thu hồi.

**Đoạn mã chỉ để học giao thức**, không phải implementation production: nó không triển khai trust-store, key lifecycle, protected `typ`, strict parser limits, timeout, cache, KMS adapter, error masking hoặc secure audit. Không thực hiện `RSAPrivateKey` từ raw bytes trong code nếu KMS/HSM cho phép decrypt non-exportable.

### Vì sao RS không thể tin `kid` tùy ý?

Một attacker có thể thay header `kid` và khiến RS thử một key khác. Việc decrypt sẽ thất bại khi khóa không khớp, nhưng nếu resolver cho `kid` quyết định **URL, filesystem path, algorithm hoặc tenant** từ input chưa xác thực, có thể tạo SSRF/confusion trước khi verify AEAD. Do đó, resolver chỉ map **(trusted issuer, recipient, profile, kid)** vào **local allowed keyring**, rồi kiểm tag/chữ ký và các claims.

### JWE compact và nhiều recipient

JWE **Compact Serialization** chỉ biểu diễn **một recipient**. JWE **JSON Serialization** có thể hỗ trợ nhiều recipients với recipient-specific key management data và shared encrypted content. Điều đó **không tự** biến một token thành “dùng được ở mọi API”; mỗi RS vẫn phải là intended recipient và kiểm `aud`/scope. Đừng dùng multi-recipient JWE để vô tình cho mọi microservice đọc claims mà chỉ một API cần biết.

## 16. Token sau decrypt: issuer, audience, scope và quyền dữ liệu

Giả sử Payroll RS giải mã JWE rồi xác minh JWS, nhận payload:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "payroll-api",
  "client_id": "payroll-web",
  "scope": "payslip:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900,
  "jti": "payslip-token-illustrative-001"
}
~~~

Đây là **claims minh họa**, không phải JWT đã ký.

| Cần kiểm | Ví dụ | Tại sao JWE không thay được kiểm tra? |
|---|---|---|
| **`iss`** | `https://auth.example.test` | Key dùng mã hóa có thể có nhiều bên biết; issuer phải được chứng minh theo token profile |
| **`aud`** | `payroll-api` | Token giải mã được nhưng có thể dành cho API khác nếu key mapping sai |
| **`exp`/`nbf`** | Token còn trong lifetime hợp lệ | Ciphertext vẫn giải mã được sau khi JWT hết hạn |
| **`scope`** | `payslip:read` | Mã hóa không cấp thêm quyền |
| **`sub`/`client_id`** | User hoặc service identity theo grant | Không giả định `client_credentials` là end user |
| **`jti`/grant status** | ID token/grant | Có thể cần denylist/introspection theo revoke policy |
| **Object-level authorization** | Payroll record của chính user/tenant | Đúng token vẫn không cho đọc mọi bản ghi |

### Sai lầm phân quyền sau decryption

~~~text
BAD:
  if decryptSucceeded:
      return allPayrollRecords()

CORRECT:
  if decryptSucceeded AND innerSignatureVerified
     AND iss/aud/exp/scope/purpose valid
     AND user/service has access to requested payroll object:
      return only permitted data
~~~

Với **opaque access token**, RS thường dùng **RFC 7662 introspection** thay vì decrypt claims cục bộ. Đừng cố decrypt một opaque reference token không có JWE format; hai profile có kiến trúc khác nhau.

### ID token, access token và refresh token có key requirements khác nhau

- **ID token** dành cho RP/client để xác minh authentication; nếu được mã hóa theo OIDC registration, recipient và key choices thuộc RP profile, **không tự chuyển sang RS**.
- **Access token** dành cho một hoặc nhiều RS được phép; AS và RS thống nhất format, recipient public key, signed/encrypted layers và audience validation.
- **Refresh token** là credential ở client/AS. Thường được lưu **bảo vệ at rest** và chỉ dùng tại token endpoint, không cần giả định mọi refresh token đều có JWE format.

Không dùng cùng RSA private key hoặc symmetric secret cho tất cả token classes vì chúng có **thẩm quyền, vòng đời và rủi ro** khác nhau.

## 17. Mã hóa token khi lưu trữ: một bài toán khóa khác

**Encryption of the token value at rest** và **encrypting token payload into JWE** là hai lớp khác nhau:

~~~text
JWE encryption:
  AS protects claims for intended RS/RP recipient.
  Recipient needs decryption key.

Token-at-rest encryption:
  BFF/mobile/backend encrypts stored raw access/refresh token.
  Store needs ciphertext, key version and protected key handling.
  Runtime decrypts token value before using it at AS/RS.
~~~

### BFF lưu refresh token

Một BFF có thể dùng **envelope encryption**:

1. Sinh DEK/CEK ngẫu nhiên cho record hoặc theo policy.
2. Dùng AEAD để mã hóa refresh token, gắn **AAD** với trusted record metadata như client registration, tenant và record ID.
3. Dùng KMS KEK bọc DEK rồi lưu **encryptedDEK + IV + ciphertext + tag + keyVersion**.
4. BFF với IAM phù hợp gọi KMS Unwrap/Decrypt và dùng refresh token ở token endpoint qua TLS.
5. Khi user logout/revoke, xóa token reference, revoke token/grant ở AS theo chính sách và xử lý retention backups.

**KMS encryption at rest không thay refresh token rotation/reuse detection**, cũng không làm credential an toàn nếu một attacker có cả **database read + KMS decrypt permission**. Phải bảo vệ secrets, IAM, workload identities, network và audit đồng thời.

### Tại sao không đặt CEK vào cùng database dưới dạng plaintext?

~~~text
WRONG:
  db.refresh_token_ciphertext = AES-GCM(key=K, token)
  db.encryption_key_plaintext  = K

Threat:
  DB dump gives both ciphertext AND encryption key.
~~~

Với envelope encryption, **wrapped CEK** có thể lưu cạnh ciphertext, còn **KEK/root key** được bảo vệ bởi KMS/HSM/IAM riêng. Điều này giúp giảm tác hại của **DB-only compromise**, nhưng **không bảo vệ trước compromise của workload đã có quyền decrypt**.

### Runtime memory và key cache

- Hạn chế lifetime plaintext token/key trong RAM, không viết logs/crash dumps khi không cần.
- Nếu cache CEK/plaintext token để giảm KMS latency, đặt TTL/capacity, bảo vệ memory và audit; không tạo cache vô hạn.
- Không chia sẻ raw symmetric key qua message queue hoặc unprotected Redis.
- Với mobile app, Secure Enclave/Keystore/Keychain có thể hữu ích nhưng **không đồng nghĩa app có thể giữ confidential client secret an toàn như backend**.
- Không dùng password người dùng làm AES key trực tiếp; nếu profile cần password-based encryption, phải dùng KDF và chuẩn được review, đồng thời hiểu nguy cơ offline guessing.

### Mã hóa token không phải token hashing

Nếu muốn lưu **reference token identifier để tra cứu** mà server không bao giờ cần khôi phục plaintext token, có thể dùng hash/HMAC theo threat model. Nếu client cần **lấy lại nguyên refresh token** để gửi token endpoint, hashing một chiều **không thể thay encryption at rest**. Lựa chọn tùy việc service có cần phục hồi bí mật hay chỉ so khớp.

## 18. KMS outage, latency và observability cho encryption keys

Mã hóa đúng nhưng hệ thống không còn hoạt động khi KMS tạm ngừng cũng có thể trở thành một vấn đề lớn. Tuy nhiên, **không được khắc phục outage bằng cách bỏ qua decryption/tag/signature validation**.

### Các tình huống availability

| Sự cố | Hậu quả | Phản ứng an toàn |
|---|---|---|
| **KMS không thể unwrap CEK** | RS không giải mã được JWE | Fail closed; trả lỗi dịch vụ phù hợp, không tự tin claims chưa decrypt |
| **KMS quota/429** | Độ trễ tăng, token validation queue dồn | Rate limit, backoff/jitter, connection pooling và capacity planning |
| **KMS IAM bị thay sai** | Workload mất quyền decrypt hoặc có quá nhiều quyền | Rollback IAM qua quy trình có audit, không dùng admin credential hardcode |
| **Key version bị disable sớm** | Token cũ vẫn còn `exp` nhưng không decrypt được | Retention/version policy, staged rotation và rollback đã thiết kế |
| **Public key RS chưa phân phối** | AS phát JWE mã hóa bằng key cũ/sai | Trusted key registry, rollout phối hợp, health check |
| **AS đổi `alg` bất ngờ** | RS không hỗ trợ hoặc policy từ chối | Contract/algorithm allowlist, migration rõ ràng |
| **RS key cache hết hạn khi KMS down** | Không thể decrypt token mới | Cache key handle/CEK hợp lệ **nếu được phép**; không mở rộng TTL trái security policy |
| **Multi-region KMS thiếu key replica** | Region B không giải mã được JWE region A | Kiểm replica/DR và recipient topology, không export key tạm |
| **Compromise key đang active** | Confidentiality mất hoặc risk giả ciphertext | Incident response, key rotation, token revocation khi cần |

### Cache decryption result có nên không?

Một số RS định cache **kết quả xác minh token** để giảm chi phí decrypt/JWS verification. Cần nhớ:

- Cache có thể chứa **claims nhạy cảm ở dạng plaintext**, dù token khi truyền là JWE.
- Key cache phải phân vùng theo **trusted issuer, recipient, policy version và token identity**, không dùng raw token string làm metric label.
- **Result đã giải mã không có nghĩa token mãi hợp lệ**: phải kiểm `exp`/`nbf`, revoke state, scope/authorization và sender proof khi gọi API.
- Nếu chính sách revoke yêu cầu kiểm introspection/denylist mỗi request hoặc TTL ngắn, một cache token-validation quá lâu có thể phá SLO.
- Nếu decrypt thành công nhưng nested JWS signature sai, **không lưu cache claims** hoặc đưa vào security context.

### Metrics an toàn

| Metric | Ý nghĩa | Không làm |
|---|---|---|
| `jwe_decrypt_success_total` | Số token giải mã hợp lệ theo profile | Không log plaintext token |
| `jwe_decrypt_failure_total` | Sai key/alg/IV/tag, malformed JWE | Không trả error chi tiết như padding oracle |
| `jwe_key_version_in_use` | Độ phủ rollout/rotation key | Không dùng raw secret hoặc unbounded `kid` làm label |
| `jwe_unsupported_algorithm_total` | Token gửi `alg`/`enc` ngoài allowlist | Không tự downgrade thuật toán |
| `kms_unwrap_duration_seconds` | Độ trễ unwrap/decrypt | Không đưa key material vào trace |
| `kms_permission_denied_total` | Sai IAM hoặc attack | Audit principal/operation có quyền truy cập |
| `jwe_old_key_decrypt_total` | Số JWE còn dùng key decrypt-only | Dùng để lập kế hoạch retirement, không dừng key sớm theo cảm tính |
| `token_validation_failure_by_reason` | Wrong issuer/aud/scope/exp/signature | Tránh token ID/subject PII thành label |
| `key_rotation_rollback_total` | Sự cố thay key | Không sử dụng key cũ mãi sau khi biết compromise |

### Error masking và crypto oracles

Một RS **không nên phản hồi caller**:

~~~text
RSA private key matched but OAEP padding invalid!
AES-GCM tag failed at byte 13!
Unknown key 'payroll-enc-v2' still exists in KMS!
Nested JWS signature failed but subject was admin!
~~~

Thông báo quá cụ thể có thể tạo **oracle** để đo trạng thái key, thuật toán hoặc plaintext, đồng thời lộ hạ tầng nội bộ. Với caller, ưu tiên một lỗi token không hợp lệ phù hợp profile; phân tích chi tiết được giữ trong **secure audit** và các metrics đã khử nhạy cảm.

## 19. Ma trận kiểm thử khóa mã hóa và JWE access token

Thiết lập giả định:

~~~text
Authorization Server issuer: https://auth.example.test
Payroll Resource Server:     payroll-api
Invoice Resource Server:     invoice-api

Nested token:
  inner JWS: AS signing key sig-v4
  outer JWE: RSA-OAEP-256 + A256GCM
  recipient key: payroll-enc-v3
  token aud: payroll-api
  token scope: payslip:read
  token exp: issued_at + 900 seconds

Keyring:
  payroll-enc-v3 ACTIVE
  payroll-enc-v2 DECRYPT_ONLY
  invoice-enc-v5 separate recipient
~~~

| Ca kiểm thử | Thiết lập/đầu vào | Kết quả kỳ vọng |
|---|---|---|
| **JWE hợp lệ** | Token dùng supported `alg`/`enc`, đúng key, tag và inner JWS | RS decrypt rồi verify toàn bộ claims và quyền |
| **JWS đơn thuần** | 3 compact segments, không phải JWE | Không ép decrypt JWE; dùng đúng token parser/profile |
| **JWE compact hợp lệ** | 5 segments, `RSA-OAEP-256` + `A256GCM` | Parse theo JWE chuẩn |
| **JWE `dir`** | Encrypted-key segment rỗng như profile | Parse đúng `alg=dir` khi được phép, không coi là hỏng |
| **JWE sai segment count** | 4 hoặc 6 segments | Từ chối |
| **Header không hợp lệ** | JSON malformed/duplicate critical fields | Từ chối theo parser policy |
| **`alg` ngoài allowlist** | `RSA1_5` hoặc thuật toán bất ngờ | Từ chối, không thử fallback |
| **`enc` ngoài allowlist** | Thuật toán yếu/không hỗ trợ | Từ chối |
| **`alg=none`** | Attacker đưa tên thuật toán ký vào JWE | Từ chối, không coi là JWE encryption |
| **`kid` không có trong keyring** | Key ID lạ | Từ chối, không remote-fetch |
| **`kid` chứa URL** | `https://attacker.invalid/key` | Không HTTP fetch/SSRF, chỉ lookup trusted map |
| **`jku`/`x5u` do attacker chỉ định** | Header trỏ tới attacker key store | Không tự dùng làm trust source |
| **Wrong recipient key** | Payroll token mã hóa cho Invoice key | Payroll không thể decrypt/không được dùng key chéo |
| **Wrong recipient audience** | JWE decrypt được nhưng `aud=invoice-api` | Payroll từ chối |
| **Wrong issuer** | JWS ký từ issuer khác/`iss` sai | Payroll từ chối |
| **Wrong token type** | ID token được mã hóa và gửi Payroll RS | Từ chối, không nhầm ID/access token |
| **Valid AEAD, invalid JWS** | JWE decrypt thành công nhưng inner signature sai | Từ chối |
| **Missing inner signature** | Profile yêu cầu nested JWS nhưng plaintext claims | Từ chối |
| **Ciphertext tampered** | Đổi một byte ciphertext | AEAD tag failure, không lộ plaintext |
| **Tag tampered** | Đổi authentication tag | Từ chối |
| **IV tampered** | Đổi IV | Từ chối |
| **AAD/header tampered** | Đổi protected header `kid`/`enc` | Không vượt kiểm authenticated encryption |
| **Wrong CEK** | Unwrap sai key hoặc ciphertext không khớp | Từ chối, không retry lung tung |
| **AES-GCM IV reused** | Hai lần encrypt khác plaintext cùng K/IV trong test harness | Security test fail; sinh mới/rotation policy |
| **CEK size sai** | 128-bit key cho `A256GCM` | Từ chối/throw, không cắt/nối key tùy tiện |
| **RSA key quá yếu** | Public key không đạt key-size/security policy | Từ chối trước khi phát token |
| **RSA OAEP policy sai** | AS/RS dùng hash/profile không khớp | Từ chối, không fallback về RSA1_5 |
| **Asymmetric public key bị thay** | AS sử dụng key không thuộc RS registration | Chặn issuance, kiểm key provenance |
| **Symmetric secret lộ** | Attacker có `dir` key, tạo AEAD ciphertext giả | Inner JWS verification vẫn chặn giả issuer |
| **Signing key lộ** | Attacker ký inner JWT hợp lệ | Incident response thay key/RS trust/revoke, không dựa chỉ encryption |
| **Public key bị công bố** | RSA encryption public JWK được đọc | Bình thường; không cho phép suy private key |
| **Symmetric JWK bị public** | `kty=oct` cùng secret `k` trong JWKS public | Security violation, rotate/contain |
| **Private RSA parameter bị public** | JWK chứa `d`/`p`/`q` | Critical incident, loại bỏ/rotate và điều tra |
| **Key confusion signature/encryption** | Dùng cùng key purpose không đúng | Từ chối theo `use`/`key_ops`/alg/trust |
| **Tenant key mix-up** | Tenant A token giải bằng key tenant B | Từ chối, không fallback sang mọi tenant keys |
| **Staging key ở prod** | Token được mã hóa bằng test key | Prod từ chối |
| **Rotation: old decrypt-only** | Token hợp lệ còn hạn dùng `enc-v2` | RS có thể decrypt trong retention window |
| **Rotation: new active** | AS bắt đầu `enc-v3` | RS decrypt được ngay sau rollout |
| **Rotation: old retired** | Token cũ đã hết hạn | RS không nhận token, key có thể retire theo policy |
| **Disable key sớm** | `enc-v2` bị xóa khi token còn hợp lệ | Availability test phát hiện lỗi; rollback/cấp lại token |
| **Compromise encryption key** | KMS key bị lộ, attacker có captured JWE | Đánh giá confidentiality lịch sử, rotation không tự xóa leak |
| **Token expired** | JWE tag/JWS đúng nhưng `exp` quá hạn | Từ chối |
| **Token not-before** | `nbf` trong tương lai | Từ chối theo clock policy |
| **Insufficient scope** | `scope=payslip:read` nhưng cần `payroll:approve` | Từ chối quyền, mã hóa không tạo scope |
| **Cross-tenant record** | Token đúng nhưng yêu cầu payslip người khác | Từ chối theo object-level policy |
| **Bearer token replay** | Attacker copy chuỗi JWE ciphertext | RS vẫn có nguy cơ chấp nhận nếu chưa revoke/binding |
| **DPoP proof thiếu** | Token bound nhưng request không có proof | Từ chối dù JWE decrypt thành công |
| **mTLS cert sai** | Token ràng buộc cert khác | Từ chối |
| **Revoked JWT còn `exp`** | RS chỉ kiểm JWT offline | Đo risk/SLO; cần revoke mechanism nếu muốn chặn sớm |
| **Opaque token** | Token không có JWE structure | Không cố giải mã, introspect theo contract |
| **KMS outage** | Không unwrap CEK, không có cache được phép | Fail closed, không đọc claims giả |
| **KMS permission denied** | Workload thiếu quyền decrypt | Alert/IAM remediation, không bật admin key hardcode |
| **KMS latency quá cao** | Key service throttling | Backoff, capacity planning; không skip crypto |
| **HTTP/log token leak** | Raw JWE/refresh token trong traces | Log redaction test fail, dù payload đã mã hóa |
| **DB ciphertext + wrapped CEK** | Data leak chỉ có database dump | Attacker không có KEK/KMS decrypt permission thì không phục hồi plaintext |
| **DB ciphertext + plaintext key** | Storage giữ cả hai cùng chỗ | Security test fail, thiết kế envelope/key isolation |
| **Backup restore** | RS/KMS restore sau disaster | Có thể decrypt token hợp lệ theo policy, không export private key bừa |
| **Stale validation cache** | RS cache đã decrypt claims quá hạn/revoked | Không cho phép, TTL/revoke policy được kiểm |

### Test key rotation phải chạy trên nhiều phiên bản

~~~text
Phase A:
  AS encrypt with enc-v2
  RS decrypt enc-v2

Phase B (prepare):
  RS accepts enc-v2 and enc-v3
  AS still encrypts enc-v2

Phase C (cutover):
  AS encrypts enc-v3 only
  RS accepts enc-v2 for existing valid tokens, and enc-v3

Phase D (retirement):
  No valid enc-v2 tokens remain per policy
  RS removes enc-v2 decrypt permission

Assertions:
  No valid token is unintentionally rejected during Phase C.
  No new token is produced with enc-v2 after cutover.
  Compromised key causes security incident path, not ordinary rollout.
~~~

### Test cạnh tranh Key ID khi deploy nhiều replica

~~~text
AS-1 starts using kid=enc-v3.
RS-1 already has enc-v3 public/private key metadata.
RS-2 still only has enc-v2.

Outcome:
  RS-2 rejects otherwise-valid JWE; production outage.

Mitigation:
  Roll out RS decrypt capability to ALL required regions/replicas first,
  verify readiness, then switch AS issuance.
~~~

Một rollout **xanh** về độ trễ nhưng **đỏ** về token decrypt failures vẫn không được xem là thành công. Cần canary và metrics key-version-specific, không đưa token secrets vào metrics.

## 20. Tình huống thực hành: Payroll API và Invoice API

Một hệ thống có:

~~~text
Authorization Server:
  issuer=https://auth.example.test
  signing key = as-sig-v4 (AS-only private key)

Payroll Resource Server:
  audience=payroll-api
  encryption key = payroll-enc-v3 (RS private, AS public)
  required scope for payslip GET = payslip:read

Invoice Resource Server:
  audience=invoice-api
  encryption key = invoice-enc-v5 (RS private, AS public)

Client:
  payroll-web receives encrypted Bearer token.
  Token payload is JWS signed by AS, then encrypted as JWE.
~~~

**Câu 1. Payroll Client có được đọc `sub`/`scope` trực tiếp từ access token JWE không?**

Không nếu client không giữ private recipient key/CEK. Client có thể **sử dụng token như opaque bearer string** để gọi Payroll API. Claims được giải mã ở RS theo trust contract.

**Câu 2. Vì sao AS dùng public key Payroll mà không dùng public signing key của AS để encrypt?**

Vì **recipient Payroll RS** cần giữ private decryption key. **AS signing public key** phục vụ RS xác minh JWS do AS ký, không phải recipient encryption key; dùng sai purpose gây key confusion.

**Câu 3. Nếu token mã hóa bằng `RSA-OAEP-256` và `A256GCM`, thuật toán nào trực tiếp mã hóa claims?**

`A256GCM` là content encryption với CEK. `RSA-OAEP-256` được dùng để bảo vệ/chuyển giao CEK bằng public recipient key.

**Câu 4. Payroll API decrypt JWE thành công nhưng inner JWS có chữ ký sai. Có cho phép không?**

**Không.** GCM tag hợp lệ chỉ bảo vệ nội dung theo encryption key; token profile yêu cầu xác minh **chữ ký issuer** và claims. Decrypt thành công không tự đủ.

**Câu 5. Payroll API decrypt token nhưng thấy `aud=invoice-api`. Có cho phép không?**

**Không.** Audience xác định resource đích; không bỏ check chỉ vì RS có private key giải mã.

**Câu 6. Nếu attacker copy nguyên JWE ciphertext và gửi đúng Payroll API, mã hóa có ngăn họ không?**

**Không chắc.** Bearer token bị copy có thể được RS chấp nhận trong thời hạn và quyền của token. Cần giới hạn TTL/audience/scope, revoke và sender-constraining bằng DPoP/mTLS nếu threat model yêu cầu.

**Câu 7. AS rotate sang `payroll-enc-v4`, có thể xóa private key v3 ngay không?**

**Không nên** nếu JWE chưa hết hạn còn dùng v3. RS giữ v3 trong **decrypt-only retention window** theo expiry/grace/DR policy; không phát JWE mới bằng v3.

**Câu 8. Private encryption key v3 bị lộ; rotate sang v4 có làm các bản JWE v3 lưu trong log trở lại bí mật không?**

**Không.** Attacker có ciphertext + key v3 có thể giải mã dữ liệu cũ. Rotation bảo vệ dữ liệu **mới**, còn sự cố cũ cần đánh giá dữ liệu, log retention, revocation và pháp lý nếu phù hợp.

**Câu 9. Có thể công bố JWK `kty=oct` chứa field `k` trên public JWKS không?**

**Không.** `k` là symmetric secret. Public JWKS chỉ được công bố những key components được phép công khai (ví dụ RSA public `n`/`e`), không private/symmetric material.

**Câu 10. Nếu KMS down, có được tạm bỏ bước decrypt và tin payload JWT được client gửi riêng trong header không?**

**Không.** Client-controlled claims không đáng tin và không được thay authenticated decryption/JWS verification. Có thể báo service unavailable hoặc dùng cache decision còn hợp lệ theo security policy, không fail open.

**Câu 11. Refresh token ở BFF được mã hóa bằng KMS at rest, còn access token JWE dùng key Payroll. Chúng có phải cùng key không?**

**Không cần và không nên mặc định dùng chung.** Token-at-rest key bảo vệ storage của BFF; recipient JWE key bảo vệ nội dung access token dành cho Payroll RS. Khác owner, purpose, IAM, expiry và rotation.

**Câu 12. Tại sao cần cả `exp` và key retirement policy?**

`exp` giới hạn thời hạn RS chấp nhận token **sau khi được giải mã/verify**; key retirement quyết định RS **còn khả năng giải mã ciphertext lịch sử** hay không. Hai quy tắc phải được phối hợp nhưng không đồng nhất.

## 21. Checklist sử dụng encryption key cho token ở production

1. **Xác định threat model:** Cần che claims khỏi ai (browser/client, proxy, logs, storage, RS khác), và mã hóa có thực sự giải quyết rủi ro đó?
2. **Đúng token format:** JWE, JWS, opaque token và encrypted-at-rest token được phân biệt; không coi Base64URL hay JWS signature là encryption?
3. **Đúng key purpose:** Signing private key, CEK, KEK, recipient public/private key và storage encryption key được tách rõ?
4. **Key length/alg policy:** JWE `alg`/`enc` được allowlist theo profile; ưu tiên cơ chế hiện đại, không tự downgrade sang RSA1_5/weak alg?
5. **CEK đủ entropy:** CEK sinh ngẫu nhiên đúng kích thước và không reuse trái policy?
6. **AES-GCM IV an toàn:** IV/nonce được cấp đúng profile, không reuse với cùng CEK; authentication tag luôn kiểm?
7. **Header trust:** `kid` chỉ lookup trusted keyring, không tự fetch remote URL từ `jku/x5u` hoặc tin header chưa được verify?
8. **AS signing vs RS encryption:** Public signing key của AS không bị nhầm với public encryption key của RS?
9. **Nested JWT nếu cần:** Khi profile yêu cầu nguồn phát đã ký, RS verify inner JWS sau AEAD decrypt, không tin plaintext đơn thuần?
10. **Issuer/audience đúng:** RS kiểm `iss`, `aud`, token class/purpose và profile, không coi decrypt thành công là đủ?
11. **Authorization độc lập:** RS kiểm `scope`, `exp`/`nbf`, `sub`/`client_id`, tenant, owner/object, role và nghiệp vụ?
12. **Sender-binding theo threat model:** Bearer JWE vẫn có thể replay; nếu dùng DPoP/mTLS thì phải kiểm proof/cert mỗi request?
13. **KMS/HSM/secret manager phù hợp:** Key material không hardcode, private key non-exportable khi có thể, operation IAM chặt, audit và quota?
14. **Public/private JWK an toàn:** Không publish symmetric `k` hoặc RSA private `d`/`p`/`q`; metadata `use`/`key_ops` đúng purpose?
15. **Key separation hợp lý:** Tách environment, recipient, issuer, token purpose, tenant (nếu cần), tránh dùng một secret mọi nơi?
16. **Rotation có staging:** RS hỗ trợ decrypt key mới trước khi AS bắt đầu phát token; cũ chuyển decrypt-only, không xóa sớm?
17. **Retention từ token lifetime:** Key cũ được giữ đủ với `exp`/clock skew/DR; refresh/storage key có vòng đời riêng?
18. **Incident response:** Lộ encryption key gây rủi ro confidentiality lịch sử; thay key không tự thu hồi plaintext đã lộ?
19. **Revocation không bị nhầm:** Key rotation/disable khác OAuth token/grant revocation; RS vẫn cần introspection/denylist nếu muốn revoke sớm?
20. **Lỗi mật mã fail closed:** Unsupported alg, wrong kid, unwrap/tag/JWS failure và KMS outage không được thành allow?
21. **Không tạo crypto oracle:** Không trả chi tiết OAEP/tag/key lookup cho caller; audit nội bộ được bảo vệ?
22. **Key/cache/storage có TTL:** Raw key/CEK, decrypted claims và access/refresh token không tồn tại lâu hơn cần thiết, không log và không share bừa?
23. **Availability/DR được kiểm:** Multi-region KMS, replica rollout, key recovery, backup và disaster recovery có test decrypt đúng policy?
24. **Test âm tính đầy đủ:** Tamper ciphertext/header/IV/tag, weak alg, wrong issuer/aud, token expired, replay, cross-tenant, key compromise và rollout race?

**Ghi nhớ:** **Encryption key dùng để giới hạn ai đọc được nội dung token; signing key dùng để xác minh ai phát token theo profile.** Trong JWE, **`alg` quản lý CEK**, còn **`enc` mã hóa nội dung**; các mô hình `RSA-OAEP-256`/`ECDH-ES`/`dir` tạo ra các trust boundary khác nhau. CEK/KEK cần phân quyền và vòng đời rõ trong KMS/HSM, AEAD phải kiểm tag và không reuse IV với cùng key, còn `kid` không phải bằng chứng tin cậy. Sau giải mã, RS vẫn phải kiểm **chữ ký nếu profile yêu cầu, issuer, audience, scope, thời hạn, quyền dữ liệu và trạng thái revoke**. Mã hóa bảo vệ confidentiality, **không tự ngăn bearer token theft/replay**.

### Chuẩn và tài liệu tham khảo

- **RFC 7516 — JSON Web Encryption (JWE):** JWE Protected Header, Compact/JSON Serialization, encrypted key, IV, ciphertext, authentication tag và nội dung AAD.
- **RFC 7518 — JSON Web Algorithms (JWA):** `alg` key management (ví dụ `dir`, `RSA-OAEP-256`, `ECDH-ES`) và `enc` content encryption (ví dụ `A256GCM`).
- **RFC 7517 — JSON Web Key (JWK):** key types, `kid`, `use`, `key_ops`, public/private/symmetric key material và JWKS.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `sub`, `exp`, `nbf`, `iat`, nested JWT và token validation.
- **RFC 7515 — JSON Web Signature (JWS):** issuer signature, protected headers và JOSE signature verification.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm allowlisting, key confusion, token substitution và JWT validation.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token type, signing/validation profile và encryption khi theo contract.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access/refresh token purpose, client/AS/RS roles và trust boundaries.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token theft/replay và authorization header transport.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token validation, `active` và revocation propagation.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token/grant revocation, độc lập với thay encryption key.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth tokens, refresh token, replay và client/resource boundaries.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained access tokens ngoài encryption.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication và certificate-bound tokens.
- **OpenID Connect Core 1.0:** encrypted ID token, signing/encryption registration context và phân biệt ID token/access token.
- **NIST SP 800-38D:** Galois/Counter Mode (GCM), authenticated encryption, IV uniqueness và operational limits.
- **NIST SP 800-57 Part 1:** key management lifecycle, rotation, cryptoperiod và key protection principles.
- **OWASP Cryptographic Storage Cheat Sheet, Key Management Cheat Sheet và OAuth 2.0 Cheat Sheet:** key custody, separation, secrets storage, token handling và crypto misuse prevention.
