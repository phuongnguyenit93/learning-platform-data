# Kiểm tra algorithm policy

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **algorithm policy** là tập quy tắc tin cậy do ứng dụng quy định trước khi xử lý token, không phải lựa chọn thuật toán theo ý người gửi.
- Phân biệt **JWE alg (key management algorithm)** với **JWE enc (content encryption algorithm)**, và phân biệt cả hai với **JWS alg (signature/MAC algorithm)**.
- Đọc cấu trúc **JWE Compact Serialization gồm năm phần**; hiểu protected header, encrypted key, IV, ciphertext, authentication tag và vai trò của Additional Authenticated Data (AAD).
- Thiết kế allowlist theo **issuer, token type, audience, recipient, key ID, key use, environment và cặp alg–enc**; thực hiện deny-by-default.
- Nhận diện rủi ro khi cho phép **RSA1_5**, chuyển thuật toán tùy tiện, dùng **alg=dir** sai mô hình khóa, chọn PBES2 dựa trên password yếu, xử lý **zip/crit/jku/jwk/kid** không an toàn.
- Giải thích vì sao **giải mã JWE thành công không chứng minh Authorization Server đã phát token**; cần nguồn xác thực người phát hành, chẳng hạn inner signed JWT trong cấu trúc nested JWT phù hợp.
- Kiểm tra AEAD, tính duy nhất của nonce/IV, key length, authentication tag, protected header và lỗi decryption-oracle.
- Xây dựng pipeline Java/Nimbus JOSE minh họa, negative tests và checklist production cho OAuth 2.0/OIDC token encryption.

## 1. Vì sao token encryption cần algorithm policy?

Giả sử một hệ thống nhận JWT được mã hóa từ một dịch vụ danh tính. Token có thể chứa claims về user, client, audience, scope, thời hạn hoặc thông tin cần giữ bí mật. Resource Server hoặc một bên nhận có quyền giải mã cần bảo đảm:

1. **Thuật toán được chấp nhận trước từ policy nội bộ**, không được chọn hoàn toàn theo header do caller gửi.
2. **Khóa giải mã thuộc đúng recipient và đúng purpose**, không lấy từ nguồn không tin cậy.
3. **Ciphertext và protected header được xác thực toàn vẹn** theo cách mà JWE profile yêu cầu.
4. **Nội dung sau giải mã thực sự do bên phát hành được tin cậy tạo ra**, thay vì chỉ là dữ liệu được mã hóa cho public key mà ai cũng có thể lấy.
5. **Các claims đáp ứng token validation và authorization**, bao gồm issuer, audience, token type, exp, scope, principal, tenant và policy trên tài nguyên.

**Algorithm policy** quyết định ứng dụng được phép dùng các thuật toán và khóa nào trong ngữ cảnh đó. Nó là một phần của **trust boundary**, không phải tùy chọn hiệu năng hay một danh sách thuật toán “càng nhiều càng tốt”.

### Ví dụ về token nhận từ bên ngoài

Một token có protected header:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-decrypt-key-2026-11",
  "cty": "JWT"
}
~~~

Đây là dữ liệu mô tả cách xử lý mà **người gửi có thể tự tạo**. Bên nhận chỉ được thực hiện theo header nếu nó **phù hợp policy đã cấu hình trước** cho Orders, issuer, recipient, key và định dạng token.

Đừng dùng logic:

~~~text
alg = incomingJweHeader.alg
enc = incomingJweHeader.enc
key = findAnyKeyByKid(incomingJweHeader.kid)
decryptUsingWhateverWasRequested(alg, enc, key)
~~~

Thiết kế này biến header không tin cậy thành một lệnh quyết định thuật toán và chọn khóa. Hệ quả có thể là **downgrade, key confusion, resource exhaustion, lộ oracle hoặc nhận sai loại token**.

## 2. JWE và JWS có những thuộc tính khác nhau

**JWS (JSON Web Signature)** cung cấp tính toàn vẹn và chứng thực nguồn dựa trên chữ ký/MAC theo key trust. **JWE (JSON Web Encryption)** mã hóa nội dung và cung cấp bảo vệ toàn vẹn/authenticity của ciphertext theo thuật toán/key profile. Hai cơ chế không tự thay nhau.

| Cơ chế | Header alg có ý nghĩa gì? | Tác dụng chính | Điều không tự bảo đảm |
| --- | --- | --- | --- |
| **JWS HS256** | HMAC-SHA256 để tạo/verify MAC. | Integrity và chứng thực bên biết secret. | Giữ bí mật payload, chống replay, quyền API. |
| **JWS RS256/PS256/ES256** | Thuật toán chữ ký số của issuer. | Integrity và nguồn ký theo private/public key trust. | Mã hóa claims, tự thu hồi token. |
| **JWE RSA-OAEP-256** | Thuật toán quản lý khóa: bảo vệ Content Encryption Key cho recipient. | Chuyển CEK an toàn tới bên nhận có private key phù hợp. | Tự xác thực người gửi là AS. |
| **JWE dir** | Dùng khóa đối xứng đã cấu hình trực tiếp làm CEK. | Bảo vệ nội dung bằng thuật toán enc. | Tự tạo trust anchor hoặc an toàn khi secret phân phối quá rộng. |
| **JWE ECDH-ES** | Key agreement để dẫn xuất khóa theo JOSE. | Thiết lập vật liệu mã hóa cho recipient. | Tự xác thực issuer của claims. |

### Compact JWS: ba phần

~~~text
BASE64URL(protectedHeader)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

### Compact JWE: năm phần

~~~text
BASE64URL(protectedHeader)
.
BASE64URL(encryptedKey)
.
BASE64URL(initializationVector)
.
BASE64URL(ciphertext)
.
BASE64URL(authenticationTag)
~~~

**Một số JWE algorithms như dir có phần encryptedKey rỗng** theo tiêu chuẩn. Không vì thế mà coi token bị cắt thiếu hoặc luôn nguy hiểm; phải kiểm chính xác thuật toán/profile.

JWE cũng có **JSON Serialization**, có thể phục vụ nhiều recipients và cách biểu diễn khác Compact Serialization. Không dùng bộ phân tích năm phần cho mọi biến thể tùy tiện; mỗi endpoint phải công bố chính xác serialization nó hỗ trợ.

## 3. JWE alg và enc phải được kiểm độc lập lẫn theo cặp

Trong JOSE, **alg** của JWE không phải chữ ký như alg của JWS.

### alg: cách cung cấp Content Encryption Key

**Content Encryption Key (CEK)** là khóa dùng để mã hóa nội dung token. Thuật toán **alg** quyết định cách tạo, truyền, bọc hoặc dẫn xuất CEK cho recipient.

Ví dụ:

- **RSA-OAEP-256:** CEK được mã hóa/bọc cho recipient bằng RSA-OAEP với SHA-256 theo JWA.
- **ECDH-ES:** CEK được dẫn xuất theo cơ chế ECDH-ES; trong direct agreement mode, phần encryptedKey rỗng.
- **ECDH-ES+A256KW:** Dùng key agreement rồi key wrapping AES-256-KW để bảo vệ CEK.
- **dir:** Một symmetric key đã được cấu hình trở thành CEK; không có bước wrap CEK độc lập.
- **A256GCMKW:** Một AES-GCM key wrapping algorithm; không phải content encryption A256GCM dù tên tương tự.

### enc: cách mã hóa nội dung

**enc** chỉ thuật toán content encryption, chẳng hạn:

- **A256GCM:** AES-256-GCM, một AEAD algorithm với IV và authentication tag.
- **A128GCM:** AES-128-GCM nếu profile cho phép.
- **A128CBC-HS256/A256CBC-HS512:** Các JOSE authenticated encryption compositions được chuẩn hóa; không mặc định coi chúng là AES-CBC không có MAC. Tuy nhiên không nên bật nếu hệ thống không có nhu cầu/profile và implementation đủ chặt.

### Ví dụ cặp hợp lệ theo một policy giả định

| Recipient/profile | alg được phép | enc được phép | Ghi chú |
| --- | --- | --- | --- |
| Orders confidential JWE | **RSA-OAEP-256** | **A256GCM** | Recipient giữ private RSA decrypt key. |
| Internal BFF symmetric JWE | **dir** | **A256GCM** | Khóa 256-bit riêng cho recipient và purpose. |
| Partner JWE profile có ECDH | **ECDH-ES** | **A256GCM** | Chỉ khi key agreement, curve và JOSE implementation được chấp nhận. |

**Bảng là ví dụ policy**, không phải khuyến nghị tất cả ứng dụng đều hỗ trợ ba cặp. Một hệ thống thực tế có thể **chỉ cho phép đúng một cặp**.

### Cần kiểm cặp, không chỉ hai danh sách riêng

Giả sử policy dự định cho:

~~~text
Allowed pair 1: RSA-OAEP-256 + A256GCM
Allowed pair 2: dir          + A128GCM
~~~

Nếu chỉ kiểm:

~~~text
alg in {RSA-OAEP-256, dir}
AND enc in {A256GCM, A128GCM}
~~~

thì có thể vô tình cho phép **dir + A256GCM** hoặc **RSA-OAEP-256 + A128GCM**, dù chưa được đánh giá trong profile. Hãy kiểm **allowlist của cặp alg–enc**, kết hợp key identity và token purpose.

## 4. Header trước xác thực là dữ liệu không tin cậy

Bên nhận JWE phải đọc header để biết cách xử lý, nhưng **không được nhầm việc đọc header với việc tin header**.

Một attacker có thể tự tạo token chứa:

~~~json
{
  "alg": "dir",
  "enc": "A128GCM",
  "kid": "some-other-key",
  "zip": "DEF"
}
~~~

**Header chỉ được tin cậy về mặt toàn vẹn sau khi token vượt qua bước xác thực mật mã tương ứng.** Trước đó, nó có thể được dùng làm **hint có kiểm soát** để chọn thuật toán/khóa trong tập đã cho phép.

Quy tắc:

1. Kiểm cú pháp/độ dài header, số phần token và giới hạn size.
2. Từ chối tên alg/enc ngoài policy **trước khi** thực hiện thao tác đắt đỏ.
3. Ràng kid với **recipient key registry đã được tin**; không dùng nó như đường dẫn file hay URL.
4. Kiểm key type/key use/key_ops, kích thước, thuật toán được phép, trạng thái revoked.
5. Chỉ sau khi JWE authentication/decryption thành công mới sử dụng plaintext.
6. **Sau giải mã**, còn phải xác thực issuer và claims theo token profile.

### Protected header và AAD

Với JWE Compact, Base64URL-encoded protected header được dùng làm **Additional Authenticated Data (AAD)** trong cơ chế mã hóa có xác thực theo JWE.

~~~text
AAD = ASCII(BASE64URL(UTF8(protectedHeaderJson)))
~~~

Nếu một attacker sửa protected header nhưng giữ IV/ciphertext/tag cũ, verification của authenticated encryption phải thất bại, trừ trường hợp giả mạo mật mã thành công.

Nhưng **AAD không tự xác thực danh tính người tạo token** khi bất kỳ ai đều có thể dùng public encryption key của recipient để tạo một JWE mới với tag hợp lệ. Đây là khác biệt giữa **ciphertext authenticity theo khóa mã hóa** và **issuer origin authentication**.

## 5. Viết policy từ trust boundary, không từ input

Một policy hợp lý cần biết trước:

- **Expected issuer / source:** thực thể nào được phép phát token này?
- **Expected recipient:** service nào thực sự có quyền giải mã?
- **Token purpose/type:** access token, ID token, assertion hay một encrypted internal envelope?
- **Allowed serialization:** Compact JWE, JSON JWE hoặc nested JWT theo profile?
- **Allowed alg–enc pairs:** cụ thể từng cặp.
- **Allowed key identities:** recipient key fingerprint/key handle, issuer, environment và key use.
- **Maximum token/header/plaintext sizes:** chống resource exhaustion.
- **Nested signature requirement:** có buộc inner signed JWT hay sender authentication tương đương không?
- **Compression/critical header rules:** có cho zip, crit hoặc extension không?
- **Expiry/revocation rules:** key rotation, token status, scope, audience và business permission.

Ví dụ policy dạng dữ liệu **nội bộ**, không phải chuẩn JOSE:

~~~yaml
profile: orders-confidential-access-token
recipient: orders-api
expectedIssuer: https://identity.example.test
acceptedSerialization: JWE_COMPACT
allowedPairs:
  - alg: RSA-OAEP-256
    enc: A256GCM
    recipientKeyPurpose: token-decryption
    keyType: RSA
requireNestedSignedJWT: true
innerJwsAlgorithms:
  - PS256
expectedInnerTokenType: at+jwt
expectedAudience: https://orders.example.test/api
allowCompression: false
rejectUnknownCriticalHeaders: true
maxCompactTokenBytes: 16384
maxPlaintextBytes: 8192
~~~

**Các giới hạn số là ví dụ để giải thích**, phải điều chỉnh theo profile và tài nguyên thực tế. Chính sách không được lấy nguyên từ claims hoặc header do client tự khai.

### Tại sao issuer không thể chỉ lấy từ JWE header?

Một JWE được mã hóa cho Orders bằng public key Orders có thể được **bất kỳ bên nào biết public key** tạo ra. Vì vậy tuyên bố issuer trong plaintext **không được tin chỉ vì giải mã thành công**. Cần inner JWS signature của issuer, sender authentication được thiết kế riêng hoặc nguồn provenance tương đương theo protocol.

## 6. Một cấu hình allowlist chặt chẽ

~~~text
PROFILE orders-jwe-at:
  serialization = JWE Compact
  outer alg      = RSA-OAEP-256
  outer enc      = A256GCM
  outer recipient key = Orders decrypt key(s) from trusted registry
  outer cty      = JWT
  zip            = not allowed
  crit           = none unless explicitly supported
  inner format   = JWS signed JWT
  inner JWS alg  = PS256
  inner issuer   = https://identity.example.test
  inner type     = at+jwt
  inner audience = https://orders.example.test/api
  claims         = exp/nbf/iat/scope/client_id/sub per profile
  state          = active token and trusted keys according to policy
~~~

**Deny-by-default:** token không khớp profile thì từ chối. Không có thứ tự “thử RSA, không được thì thử dir, không được thì thử parser khác”.

### Vì sao cần key purpose?

Một private RSA key có thể về mặt định dạng dùng được trong nhiều cơ chế, nhưng hệ thống phải tách:

- **AS signing key:** dùng ký access token/ID token.
- **Orders decryption key:** dùng giải mã JWE dành cho Orders.
- **mTLS private key:** dùng cho TLS client/server authentication.
- **Client assertion key:** dùng private_key_jwt.

Không dùng **AS signing private key** như JWE recipient decrypt key chỉ vì cùng là RSA, trừ khi có profile rõ và security review đặc biệt; tách khóa giảm hậu quả khi một mục đích bị xâm phạm.

## 7. Ví dụ luồng xử lý đúng

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant K as AS Signing Key
    participant RK as Orders Public Encryption Key
    participant C as OAuth Client
    participant RS as Orders Resource Server
    participant REG as Trusted Policy/Key Registry

    AS->>AS: Kiểm grant, scope, audience, token type
    AS->>K: Ký inner JWT bằng issuer signing key
    K-->>AS: Inner JWS
    AS->>RK: Mã hóa inner JWS thành JWE theo allowlist
    RK-->>AS: Outer JWE Compact
    AS-->>C: Encrypted access token
    C->>RS: Token qua HTTPS
    RS->>REG: Lấy policy và recipient trusted key state
    REG-->>RS: Chỉ RSA-OAEP-256 + A256GCM, key đúng purpose
    RS->>RS: Kiểm header alg/enc/kid/cty, kích thước
    RS->>RS: Decrypt/authenticate outer JWE
    RS->>RS: Verify inner JWS từ issuer trusted public key
    RS->>RS: Kiểm iss/aud/typ/exp/scope/permission
    RS-->>C: Response theo quyền hoặc từ chối
~~~

Luồng này dùng **sign-then-encrypt** cho JWT nhạy cảm, là một mẫu thiết kế hữu ích khi cần **confidentiality và issuer authentication**. Không suy rằng mọi JWE trong mọi protocol phải nested JWS; phải theo đúng profile đã thỏa thuận. Nếu chọn mô hình khác, cần có cơ chế đáng tin để xác thực ai đã gửi nội dung.

## 8. RSA-OAEP-256: kiểm policy ở lớp quản lý khóa

Với JWE dùng **RSA-OAEP-256 + A256GCM**, có hai lớp:

1. JWE sinh một **Content Encryption Key (CEK)** 256-bit phù hợp A256GCM.
2. CEK được bọc bằng **RSA-OAEP-256** với public encryption key của recipient; nội dung được mã hóa bằng AES-256-GCM.

~~~text
Issuer / encrypting party:
    CEK <- cryptographic RNG
    IV  <- unique nonce according to GCM policy
    encryptedKey <- RSA-OAEP-256(recipientPublicKey, CEK)
    ciphertext, tag <- AES-256-GCM(CEK, IV, plaintext, protectedHeaderAAD)
    emit Compact JWE

Recipient:
    trusted private key selection under issuer/recipient policy
    CEK <- RSA-OAEP-256-Decrypt(recipientPrivateKey, encryptedKey)
    plaintext <- GCM-Decrypt-and-Verify(CEK, IV, ciphertext, tag, AAD)
    if any step fails: reject uniformly
~~~

Đây là mô hình khái niệm; **không tự triển khai RSA padding, AES-GCM hay JWE serialization** trong application code.

### Những điều phải kiểm

| Điều kiện | Lý do |
| --- | --- |
| **alg chính xác RSA-OAEP-256** | Không tự chấp nhận RSA1_5 hoặc RSA-OAEP variant khác khi policy chỉ cho RSA-OAEP-256. |
| **enc chính xác A256GCM** | CEK length/tag/IV và bảo mật nội dung phải theo profile. |
| **RSA key type và key size** | Không dùng khóa HMAC/EC hoặc RSA key yếu, sai purpose. |
| **Private key recipient** | Chỉ service có quyền decrypt mới dùng, không lẫn signing key AS. |
| **kid thuộc recipient key registry** | Không lấy file/key từ đường dẫn header tự chọn. |
| **Authenticated decryption** | Chỉ sử dụng plaintext sau khi verify authentication tag. |
| **Error handling đồng nhất** | Hạn chế khác biệt lỗi padding/CEK/tag làm decryption oracle. |

### RSA1_5 và padding-oracle risk

JOSE lịch sử định nghĩa **RSA1_5** cho key management, nhưng các triển khai mới nên **tránh chọn** nó vì nguy cơ kiểu Bleichenbacher/padding oracle khi xử lý lỗi không an toàn. Với migration/token cũ, cần threat review và xử lý theo guidance của JOSE/RFC 8725; không mở RSA1_5 mặc định chỉ vì thư viện hỗ trợ.

**RSA-OAEP-256 cũng cần thư viện an toàn, decryption error hygiene và kích thước khóa đúng.** Không tuyên bố chỉ thay một chuỗi alg là đủ để loại mọi side channel.

## 9. ECDH-ES, dir và AES Key Wrap: không trộn các trust models

### ECDH-ES

**ECDH-ES** dựa trên Elliptic Curve Diffie-Hellman và KDF theo JOSE để dẫn xuất keying material. Khóa public/private recipient có thể là EC/OKP theo thuật toán/profile hỗ trợ.

Hai kiểu cần phân biệt:

- **ECDH-ES** direct: derived key được dùng trực tiếp làm CEK theo enc; phần encryptedKey rỗng.
- **ECDH-ES+A256KW**: derived keying material được dùng làm Key Encryption Key để wrap một CEK riêng; phần encryptedKey mang CEK đã được wrap.

Không thay **ECDH-ES+A256KW** bằng **ECDH-ES** chỉ vì hai header cùng chứa chữ ECDH. Cần kiểm đúng curve, key type, ephemeral public key parameters, key derivation và context theo JWA.

**Một JWE ECDH-ES do ai đó tạo cho public key recipient vẫn không tự chứng minh nguồn phát hành claims.** Key agreement bảo vệ cơ chế chia sẻ khóa; inner signed JWT hoặc cơ chế sender authentication tương đương có thể vẫn cần.

### dir: dùng symmetric key trực tiếp làm CEK

Với:

~~~json
{
  "alg": "dir",
  "enc": "A256GCM",
  "kid": "bff-direct-key-v2"
}
~~~

JWE sử dụng **một symmetric key đã được cấu hình** làm CEK, theo kích thước phù hợp enc. Không có encrypted key riêng trong Compact Serialization.

Lưu ý:

- Chỉ chấp nhận dir nếu **đã có shared key đúng purpose và recipient**.
- Với A256GCM, CEK phải đúng kích thước **256 bit**.
- **Không dùng password hoặc chuỗi tự chế** làm CEK rồi coi là đạt bảo mật AES-256.
- AES-GCM nonce/IV không được dùng lại với cùng key; quản lý số lần mã hóa và rotation.
- Khi nhiều service biết key, những service ấy có thể tạo ciphertext/tag hợp lệ; không thể tự chứng minh duy nhất AS là người phát.

**Không chuyển từ RSA-OAEP-256 sang dir chỉ vì JWE header đề nghị.** Đây là thay đổi trust model và key possession, không phải điều chỉnh format.

### AES Key Wrap và AES-GCM Key Wrap

Các thuật toán **A128KW/A256KW** và **A128GCMKW/A256GCMKW** là key management algorithms bọc CEK. Chúng khác **enc=A256GCM** dùng mã hóa payload.

Nếu profile hỗ trợ AES-GCM Key Wrap, cần kiểm nonce/tag và JWE header parameters đi kèm, không dùng lại những gì dùng cho content encryption một cách tùy tiện.

### PBES2 và password-derived keys

JOSE cũng định nghĩa những biến thể **PBES2-HS256+A128KW** và tương ứng. Chúng dẫn xuất key từ password dựa trên salt và iteration count. Một endpoint xử lý JWT từ Internet không nên bật PBES2 chỉ vì library có sẵn:

- Mật khẩu entropy thấp tạo bề mặt offline guessing.
- Header iteration count và các tham số KDF có thể bị dùng làm **DoS** nếu chấp nhận tùy ý.
- Cần password policy, giới hạn CPU/iteration, salt length và đánh giá profile riêng.

Với OAuth access token do AS quản lý, **khóa ngẫu nhiên đủ mạnh và thuật toán quản lý khóa được thỏa thuận trước** thường phù hợp hơn cơ chế password-based JWE tự do.

## 10. A256GCM: authentication tag và nonce không phải chi tiết tùy chọn

AES-GCM thuộc nhóm **AEAD: Authenticated Encryption with Associated Data**. Nó bảo vệ:

- **Confidentiality** của plaintext.
- **Integrity của ciphertext và AAD** khi tag được kiểm đúng.

JWE A256GCM có key length 256 bit, GCM IV và authentication tag theo profile. GCM thường sử dụng **96-bit IV** và tag **128 bit** cho JWE AES-GCM algorithms theo JWA.

### Tại sao IV uniqueness quan trọng?

Dùng lại cùng một **(CEK, IV)** với AES-GCM có thể phá nghiêm trọng confidentiality/integrity. Trong JWE, việc CEK được sinh mới cho mỗi token trong nhiều key-management modes giảm rủi ro trùng cặp, nhưng **alg=dir** dùng CEK lặp qua nhiều token nên đặc biệt phải quản lý nonce uniqueness và key rotation.

~~~text
Bad:
    key = fixed-256-bit-key
    iv  = 12 zero bytes
    encrypt token T1
    encrypt token T2 with same key, same iv

Required:
    CEK and IV generated according to the chosen JOSE profile
    never repeat (same CEK, same GCM IV)
    rotate key / enforce message limits
~~~

Không viết IV từ timestamp dễ trùng, PID hoặc counter không được quản lý đồng bộ qua nhiều replicas. Secure random IV có thể phù hợp trong giới hạn số lần dùng đã được tính toán, nhưng không tự bảo đảm không collision nếu sử dụng vô hạn; cần đánh giá nonce strategy theo library/provider.

### Tag phải được kiểm trước khi dùng plaintext

Sai:

~~~text
plaintext = AES_GCM_decryptWithoutCheckingTag(...)
parseClaims(plaintext)
grantAccess()
checkTagLater()
~~~

Đúng:

~~~text
plaintext = AuthenticatedDecrypt(key, IV, ciphertext, AAD, tag)
if decryptOrTagValidationFails:
    REJECT
else:
    parseAndValidateInnerToken(plaintext)
~~~

**Không stream dữ liệu chưa được xác thực vào business logic**. Nếu thư viện hỗ trợ streaming AEAD, phải bảo đảm ứng dụng chưa ra quyết định dựa trên bytes trước khi verify tag hoàn tất.

### AAD bảo vệ header, không xác thực issuer

Một attacker có public encryption key của Orders có thể tự tạo:

~~~text
new protected header
new CEK
new IV
new plaintext claims
new ciphertext + valid GCM tag
~~~

Đó có thể là một JWE **hợp lệ về mặt mã hóa**. Nếu không có inner signature hoặc sender-origin control được thiết kế, Orders không nên tin claims là do AS phát.

## 11. Chính sách chọn khóa: kid, key use, JWKS và issuer

JWE protected header có thể có **kid** (key identifier), nhưng kid là **dữ liệu đầu vào không được tin cậy trước khi xác thực**.

### Key selection an toàn

~~~text
trustedProfile = Orders JWE AT
allowedPairs = {(RSA-OAEP-256, A256GCM)}
trustedRecipientKeyRegistry = Orders decrypt keys
allowedKeyUse = decrypt / enc
allowedIssuer = https://identity.example.test

1. Parse header with strict size/format limits.
2. Verify alg/enc exactly in allowedPairs.
3. Resolve kid only within trustedRecipientKeyRegistry.
4. Enforce algorithm, key type, purpose, status and recipient.
5. Decrypt/authenticate with a trusted private key.
6. Verify issuer origin of inner content and claims.
~~~

**Key ID không phải khóa và cũng không phải authorization**. Dùng kid như chỉ mục trong registry được cấu hình sẵn, không biến nó thành bất kỳ file path/SQL clause/remote URL nào.

Sai:

~~~text
privateKey = readFile("/keys/" + header.kid)
publicKey = download(header.jku)
key = allIssuersGlobalMap[header.kid]
~~~

Những cách này có thể gây path traversal, SSRF, key confusion hoặc nhầm trust boundary.

### Embedded jwk, jku, x5u, x5c

Các JOSE header parameters cho public keys/certificates có profile cụ thể. **Không tin khóa tự khai bên trong token làm trust anchor**. Với JWE, một recipient không nên lấy public key kèm theo token để tùy tiện thiết lập decryption key hoặc xác thực issuer.

Nếu hệ thống hỗ trợ trusted key URLs, URL phải được cấu hình/allowlist từ nguồn đáng tin, với TLS/hostname, no SSRF, issuer/recipient binding, cache và policy nhất quán. Đừng follow HTTP redirects sang host do token điều khiển.

### Key use và key_ops

Một JWK có thể mô tả:

- **use=enc:** key phục vụ encryption/key management.
- **use=sig:** key phục vụ signature.
- **key_ops:** những thao tác như encrypt/decrypt/wrapKey/unwrapKey hoặc sign/verify.

Bên nhận cần bảo đảm metadata, thuật toán, key type và quyền HSM/KMS **không mâu thuẫn**; không dùng AS signing RSA key làm private decrypt key chỉ vì nó kỹ thuật cũng là RSA.

### Key revocation

Một recipient key bị compromise có thể cần được **disable decrypt** và loại khỏi accepted JWE profiles, nhưng việc xóa key cũ sẽ ảnh hưởng **JWE chưa được giải mã**. Một signing key bị compromise cần rút **verification trust** ở RS; đây là hai loại sự cố khác nhau.

## 12. JOSE protected header: typ, cty, crit, zip

### typ: type của token/container

**typ** có thể giúp chỉ ra loại đối tượng theo profile, nhưng không thay kiểm cryptographic hoặc semantic validation. Nếu một hệ thống dự kiến JWE access token, hãy định nghĩa rõ expected outer type và inner type, không dùng typ do caller tự khai như một vé cho phép bỏ bước kiểm.

### cty=JWT trong nested JWT

Khi plaintext JWE chứa một JWT bên trong, outer header thường dùng:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "orders-decrypt-key-v3"
}
~~~

**cty=JWT chỉ là tín hiệu content type được bảo vệ sau JWE authentication**; nó không chứng minh inner payload là JWT đúng chữ ký. Phải thực sự parse, verify inner JWS và kiểm claims.

### crit: critical extensions

JOSE có thể dùng **crit** để liệt kê những header parameters mà bên xử lý phải hiểu. Nếu không hỗ trợ một critical parameter, **phải từ chối** theo quy tắc JOSE, không bỏ qua và vẫn xử lý token.

- Không bật extensions ngoài profile một cách tự động.
- Không tự chấp nhận unrecognized fields trong crit.
- Không coi crit là một nơi để người gửi yêu cầu bypass alg/enc validation.
- Nếu không cho critical extensions, dùng policy đơn giản: reject các token dùng crit.

### zip: compression có thể gây resource exhaustion

Một số JWE profiles hỗ trợ **zip=DEF** để nén plaintext trước khi mã hóa. Compression trước encryption có thể mang rủi ro:

- **Decompression bomb:** ciphertext nhỏ giải nén thành payload rất lớn.
- Chi phí CPU/memory vượt ngân sách dịch vụ.
- Side-channel liên quan kích thước khi nén dữ liệu bí mật cùng dữ liệu attacker có thể điều khiển trong một số threat models.

Nên **từ chối zip trừ khi profile thực sự yêu cầu**. Nếu cho phép, phải giới hạn compressed size, decompressed size, ratio, recursion/processing budget và **chỉ xử lý sau authenticated decryption**.

### Không hợp thức hóa header sau khi parse sai

Một parser gặp JWE malformed không nên thử “sửa” Base64URL, tự thêm phần thiếu, thử JWS rồi thử JWE hoặc bỏ header không hiểu. Xác định serialization và profile từ endpoint, **reject malformed input**.

## 13. Nested JWT: encryption không thay signature

Một cấu trúc phổ biến:

~~~text
Inner Signed JWT:
    JWS protected header: alg=PS256, typ=at+jwt
    claims: iss, sub, aud, exp, scope, client_id
    signature: AS private signing key

Outer Encrypted JWT:
    JWE header: alg=RSA-OAEP-256, enc=A256GCM, cty=JWT
    plaintext: compact inner signed JWT
    encryption recipient: Orders public key
~~~

**Sign-then-encrypt** mang hai mục đích riêng:

- **Inner JWS:** bảo đảm issuer authenticity/integrity theo signing key trust.
- **Outer JWE:** bảo vệ confidentiality của inner signed JWT cho intended recipient và integrity của ciphertext/header.

### Vì sao không chỉ JWE?

Với public-key encryption, public key thường công khai. **Bất kỳ bên nào cũng có thể encrypt dữ liệu cho recipient**. Nếu giải mã xong rồi tin claims iss/sub/scope tự khai, attacker có thể tạo JWE hợp lệ mà không cần private signing key của AS.

### Vì sao không chỉ JWS?

Inner JWS có chữ ký nhưng không giữ claims bí mật. Khi cần hạn chế ai đọc token claims, outer encryption giúp giảm việc client/proxy hoặc người có chuỗi token đọc nội dung.

### Kiểm cả hai lớp

~~~mermaid
flowchart TD
    A["Nhận Compact JWE từ HTTP request"] --> B{"Outer alg+enc đúng allowlist?"}
    B -->|Không| X["REJECT"]
    B -->|Có| C{"Recipient key, kid, use, status đúng?"}
    C -->|Không| X
    C -->|Có| D["JWE authenticated decryption"]
    D --> E{"Tag/decryption hợp lệ?"}
    E -->|Không| X
    E -->|Có| F{"Nested JWS đúng format/profile?"}
    F -->|Không| X
    F -->|Có| G{"JWS alg/key trust và signature đúng?"}
    G -->|Không| X
    G -->|Có| H{"iss, aud, typ, exp, scope, grant/permission đúng?"}
    H -->|Không| X
    H -->|Có| I["ALLOW theo authorization policy"]
~~~

**Không cho caller chọn thứ tự lớp hoặc bỏ inner signature** bằng cách sửa header. Nếu endpoint yêu cầu nested JWT, plaintext không phải signed JWT thì reject.

## 14. Algorithm confusion và downgrade trong JWE

Một số anti-pattern:

### Cho phép thuật toán ngoài profile qua header

~~~text
if header.alg == "RSA-OAEP-256":
    use RSA decrypt key
else if header.alg == "dir":
    use fallbackSharedSecret
else:
    tryLegacyCipher
~~~

Nếu Orders chỉ được phép RSA-OAEP-256 + A256GCM, mọi nhánh còn lại phải **từ chối**, không fallback sang secret tiện dùng hoặc thuật toán “legacy” chưa được duyệt.

### Dùng JWS alg=none để bỏ issuer signature

Một attacker có thể tạo outer JWE hợp lệ cho Orders, chứa plaintext JSON hoặc unsigned JWT và hy vọng Orders chỉ kiểm JWE rồi cấp quyền.

**Nếu policy yêu cầu inner signed JWT, phải reject inner alg=none hoặc không có chữ ký.** JWS alg=none và JWE alg=dir là hai điều **khác hoàn toàn**; đừng cấm nhầm mọi JWE dir vì nghĩ nó tương đương unsigned JWS. Ngược lại, cũng không cho phép unsigned JWS chỉ vì JWE ngoài dùng authenticated encryption.

### Sử dụng khóa sai purpose

- HMAC signing secret cho HS256 **không phải** CEK A256GCM mặc định.
- Private RSA key của issuer ký PS256 **không tự là** Orders RSA decryption key.
- Public JWK lấy từ JWS issuer JWKS không tự trở thành recipient key.
- Key có cùng kid nhưng thuộc issuer/environment khác **không được chọn**.

### Hỗ trợ “all algorithms” khi library làm được

Khả năng thư viện hỗ trợ 20 thuật toán không phải lý do bật 20 thuật toán. Cấu hình càng rộng tăng attack surface, số test cần thiết và khả năng hình thành một cặp alg/enc không được review.

**Thiết kế đúng thường chấp nhận số ít cặp được kiểm thử rất kỹ**, thay vì thử mọi tổ hợp và hy vọng decryption fail nếu nguy hiểm.

## 15. Thứ tự kiểm tra algorithm policy khi xử lý token

Một pipeline an toàn có thể chia thành các lớp:

~~~text
INPUT BOUNDARY
  1. HTTPS, kích thước request, Authorization header và rate limit.
  2. Strict parse JWE serialization, số phần, Base64URL và header size.

POLICY BOUNDARY
  3. Load policy được server cấu hình cho endpoint và recipient.
  4. Check exact pair (alg, enc) in allowlist.
  5. Reject unsupported zip/crit/cty/typ/extensions.
  6. Resolve kid in trusted recipient-key registry, check key type/use/status.

CRYPTOGRAPHIC BOUNDARY
  7. Authenticated JWE decryption với key đúng recipient.
  8. Fail closed nếu RSA key management/GCM authentication thất bại.
  9. Chỉ sau bước 8 mới đọc plaintext.

ISSUER BOUNDARY
  10. Nếu profile yêu cầu nested JWT, parse inner signed JWS.
  11. Check inner JWS alg + trusted issuer signing key.
  12. Verify inner signature và token type/profile.

AUTHORIZATION BOUNDARY
  13. Check iss, aud, exp, nbf, claims bắt buộc.
  14. Check scope, client, subject, tenant, grant/revocation.
  15. Check sender proof nếu token là sender-constrained.
  16. Check resource-level permissions trước khi trả dữ liệu.
~~~

### “Kiểm alg/enc trước khi decrypt” có nghĩa gì?

Header cần được đọc trong trạng thái **chưa xác thực** để chọn handler và key. Điều an toàn là dùng nó **chỉ để so với allowlist và chọn một key đã tin**, không dùng để quyết định mở rộng trust.

Sau khi decryption/authentication thành công, protected header được bảo vệ về tính toàn vẹn trong JWE. Nhưng việc ciphertext được tạo hợp lệ **không tự chứng minh nó do AS phát**. Do đó bước issuer verification ở lớp trong không thể bỏ qua nếu profile yêu cầu.

### Kiểm thời gian và state ở đâu?

Các claims như **exp, nbf, aud, scope** nằm trong plaintext; chúng chỉ được dùng sau khi JWE authenticated decryption thành công, và nếu cần, sau khi inner JWS signature được xác minh.

Đừng cho outer header chứa một trường scope hoặc user_id để quyết định quyền trước khi kiểm. Header phù hợp thuật toán cũng không làm nội dung hợp lệ.

## 16. Java JCA: ví dụ AES-GCM để hiểu AEAD

Đây là ví dụ **AES-GCM thuần túy** minh họa IV, AAD, ciphertext và tag. Nó **không phải mã hoàn chỉnh tạo/đọc JWE**: JWE yêu cầu serialization, key management và header format theo RFC 7516/7518.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmUnderstandingDemo {

    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random);
        SecretKey cek = generator.generateKey();

        byte[] iv = new byte[IV_BYTES];
        random.nextBytes(iv);

        // AAD minh họa: thực tế JWE xác định exact protected header bytes.
        byte[] aad = "example-protected-header"
                .getBytes(StandardCharsets.US_ASCII);

        byte[] plaintext = "example-private-token-claims"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encryption = Cipher.getInstance("AES/GCM/NoPadding");
        encryption.init(
                Cipher.ENCRYPT_MODE, cek,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        encryption.updateAAD(aad);

        // JCA doFinal trả ciphertext nối tag với provider tương ứng.
        byte[] cipherWithTag = encryption.doFinal(plaintext);

        Cipher decryption = Cipher.getInstance("AES/GCM/NoPadding");
        decryption.init(
                Cipher.DECRYPT_MODE, cek,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        decryption.updateAAD(aad);

        byte[] recovered = decryption.doFinal(cipherWithTag);

        if (!Arrays.equals(plaintext, recovered)) {
            throw new SecurityException("Authenticated decryption failed");
        }

        System.out.println("AES-GCM self-test PASS");

        // Không in raw key, plaintext token hoặc ciphertext production.
    }
}
~~~

### Giới hạn của ví dụ

- **KeyGenerator** sinh CEK demo bằng provider JCA, không tự xây JWE protected header.
- **AAD** của JWE Compact phải là exact Base64URL-encoded protected header theo RFC 7516, không phải chuỗi ví dụ.
- Với JWE, thư viện JOSE chịu trách nhiệm **tách tag, IV, ciphertext và key management** đúng cấu trúc compact.
- Dùng lại cùng CEK/IV trong GCM là sai nghiêm trọng; demo chỉ chạy **một lần mã hóa**.
- Với decryption, một lỗi **AEADBadTagException** hoặc lỗi cryptographic phải là kết quả **từ chối**, không trả plaintext chưa xác thực.
- Nếu một hệ thống dùng **alg=dir** để mã hóa lượng rất lớn, cần chính sách IV uniqueness/message limits và rotation, không suy rằng random 12-byte IV đủ an toàn mãi mãi.
- Không đặt key AES trong source code, query string, JWT header hoặc shared logs.

### Vì sao không tự ghép JWE từ AES-GCM demo?

Dù AES-GCM hoàn chỉnh ở cấp primitive, JWE còn có:

- CEK wrapping/agreement algorithm.
- Protected header với alg/enc/kid/cty/parameters.
- JWE AAD chính xác và Base64URL encoding.
- Key type/key use policy và recipient identity.
- Error handling, format/size validation và nested JWT.

**Dùng thư viện JOSE đã được kiểm thử** thay vì tự viết Compact JWE serializer.

## 17. Nimbus JOSE + JWT: nested sign-then-encrypt minh họa

Ví dụ sau mô tả một mô hình **PS256 signed access token bên trong JWE RSA-OAEP-256 + A256GCM**. Nó giả định caller đã có đúng khóa từ **trusted AS/recipient key stores**.

### Phát hành: AS ký JWT trước, rồi mã hóa cho Orders

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

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

public final class NestedTokenIssuerDemo {

    public static String issue(
            JWTClaimsSet authorizedClaims,
            RSAPrivateKey asSigningKey,
            RSAPublicKey ordersEncryptionKey) throws Exception {

        SignedJWT inner = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.PS256)
                        .type(new JOSEObjectType("at+jwt"))
                        .keyID("as-signing-key-v3")
                        .build(),
                authorizedClaims
        );

        // Claims phải được AS kiểm grant/scope/audience trước đó.
        inner.sign(new RSASSASigner(asSigningKey));

        JWEObject outer = new JWEObject(
                new JWEHeader.Builder(
                        JWEAlgorithm.RSA_OAEP_256,
                        EncryptionMethod.A256GCM
                )
                        .keyID("orders-decrypt-key-v3")
                        .contentType("JWT")
                        .build(),
                new Payload(inner.serialize())
        );

        outer.encrypt(new RSAEncrypter(ordersEncryptionKey));
        return outer.serialize();
    }
}
~~~

**Mã ví dụ** không tự tạo claims từ user input; tham số authorizedClaims chỉ được phép đến từ **AS issuance policy đã kiểm client/grant/resource/scope**. Không cho client trực tiếp gửi một JWTClaimsSet chứa scope mong muốn rồi signing service ký tùy ý.

### Bên nhận: kiểm outer policy trước, decrypt rồi verify inner

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Date;

import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

public final class NestedTokenRecipientDemo {

    private static final String ISSUER =
            "https://identity.example.test";

    private static final String ORDERS_AUDIENCE =
            "https://orders.example.test/api";

    public static JWTClaimsSet decryptAndVerify(
            String compactJwe,
            RSAPrivateKey ordersDecryptionKey,
            RSAPublicKey trustedIssuerSigningPublicKey)
            throws Exception {

        JWEObject jwe = JWEObject.parse(compactJwe);
        JWEHeader outer = jwe.getHeader();

        if (!JWEAlgorithm.RSA_OAEP_256.equals(
                outer.getAlgorithm())) {
            throw new SecurityException("Unsupported JWE alg");
        }

        if (!EncryptionMethod.A256GCM.equals(
                outer.getEncryptionMethod())) {
            throw new SecurityException("Unsupported JWE enc");
        }

        if (!"orders-decrypt-key-v3".equals(outer.getKeyID())
                || !"JWT".equals(outer.getContentType())
                || outer.getCompressionAlgorithm() != null
                || outer.getCriticalParams() != null) {
            throw new SecurityException("JWE header violates policy");
        }

        // ordersDecryptionKey phải được chọn từ trusted registry,
        // ràng với recipient, use=enc, key type, status và kid.
        jwe.decrypt(new RSADecrypter(ordersDecryptionKey));

        // KHÔNG đọc plaintext nếu JWE decryption/tag thất bại.
        SignedJWT inner = SignedJWT.parse(
                jwe.getPayload().toString()
        );

        if (!JWSAlgorithm.PS256.equals(
                inner.getHeader().getAlgorithm())) {
            throw new SecurityException("Unsupported inner JWS alg");
        }

        if (!"at+jwt".equals(
                inner.getHeader().getType() == null
                    ? null : inner.getHeader().getType().toString())) {
            throw new SecurityException("Wrong token type");
        }

        // Trusted public key phải được chọn theo issuer/key policy,
        // không lấy từ untrusted jku hoặc embedded jwk.
        if (!inner.verify(new RSASSAVerifier(
                trustedIssuerSigningPublicKey))) {
            throw new SecurityException("Invalid issuer signature");
        }

        JWTClaimsSet claims = inner.getJWTClaimsSet();

        if (!ISSUER.equals(claims.getIssuer())
                || !claims.getAudience().contains(ORDERS_AUDIENCE)
                || claims.getExpirationTime() == null
                || !claims.getExpirationTime().after(new Date())) {
            throw new SecurityException("Invalid JWT claims");
        }

        // PHẢI bổ sung: nbf/iat, inner kid/key status,
        // required claims, scope, client, tenant, sender proof,
        // revocation và business authorization.
        return claims;
    }
}
~~~

### Điều gì vẫn cần làm trước production?

- Khóa recipient private và issuer public không thể là tham số do HTTP caller tùy ý chọn.
- Inner **kid** cũng cần allowlist/trusted key selection; ví dụ chỉ dùng một issuer public key cố định để dễ học.
- Kiểm **outer/inner size, parse depth, critical params, token type, time/clock skew, audience cardinality** và profile claims.
- **Decrypt success không thay việc verify inner signature.**
- API cần kiểm scope/permission, không chỉ return claims rồi coi là authorized.
- Quản lý key rotation, revocation, KMS/HSM, cache và retry.
- Handle lỗi thành một response thống nhất, không tiết lộ “đúng key nhưng tag sai” hay thông tin riêng về recipient.
- Nimbus/JOSE phiên bản thực tế có thể khác về APIs và supported algorithms; cần compile/test theo dependency của dự án khi tích hợp.
- Một hệ thống có thể sử dụng nested format khác nếu hợp đồng quy định; ví dụ chỉ mô tả một cách triển khai an toàn, không phải giao thức OAuth bắt buộc.

## 18. Spring Security và ứng dụng token encryption

Spring Security Resource Server thường được dùng để xác minh **signed JWT access tokens (JWS)** hoặc introspect opaque tokens. **Không mặc định cho rằng cấu hình JWT decoder chỉ với jwk-set-uri sẽ tự giải mã JWE.**

Nếu service cần nhận encrypted JWT:

1. Có một **JWE processing layer** nhận, parse, so exact alg–enc policy và decrypt với recipient key.
2. Layer đó chỉ tạo **inner signed JWT** khi decryption/tag validation thành công.
3. Một **JWT signature validator** độc lập kiểm issuer signing key, alg, token type và claims.
4. Resource Server kiểm scope, tenant/resource permission và revocation/sender-binding.
5. Mọi trường hợp lỗi trả về phản hồi xác thực phù hợp, không trả claims chưa xác thực.

~~~text
HTTP Bearer JWE
    -> JWE Policy Gate
    -> Authenticated Decrypt
    -> Extract inner Signed JWT
    -> JWT Issuer Signature and Claims Validation
    -> Granted Authorities / Resource Policy
    -> HTTP result
~~~

### Tách trách nhiệm thư viện

- **JOSE library:** crypto/serialization của JWE/JWS, không tự chọn business authorization.
- **Issuer metadata/JWKS source:** trusted key discovery theo config.
- **Recipient key manager:** KMS/HSM private decrypt key và key status.
- **OAuth/JWT validator:** token type, issuer, audience, thời gian và claims.
- **Authorization layer:** scope, ownership, tenant, action.
- **Incident/revocation layer:** token/grant/key state, SLO, audit.

Không dùng một decoder “accept any token” rồi tùy token header quyết định JWE hay JWS để giảm công việc cấu hình. **Endpoint phải định nghĩa token profile trước**, chứ không để attacker thương lượng thuật toán bằng input.

## 19. Decryption error và phòng decryption oracle

Một cơ chế decryption có thể thất bại ở nhiều điểm:

- Invalid Compact JWE format/Base64URL.
- Unsupported alg/enc hoặc sai cặp allowlist.
- Unknown kid/recipient key.
- RSA-OAEP unwrapping error.
- AES-GCM authentication tag mismatch.
- Invalid compressed payload.
- Inner JWT parse/signature/claims failure.

### Không lộ khác biệt lỗi nhạy cảm cho caller

Một API có thể log nội bộ loại lỗi ở mức được phép, nhưng không nên trả cho attacker thông điệp quá chi tiết như:

~~~text
"RSA padding almost correct"
"CEK unwrap succeeded but authentication tag wrong"
"Recipient key version 3 exists and decryption reached payload"
~~~

Những khác biệt dễ quan sát theo nội dung response, status hoặc timing có thể góp phần tạo **chosen-ciphertext/decryption oracle** trong những thiết kế yếu.

### Phản hồi bên ngoài

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Đây là mẫu phản hồi tùy context. Có thể dùng 400/401 tùy API contract và loại lỗi, nhưng tránh biến lỗi cryptographic thành thông tin giúp attacker phân biệt trạng thái private key hoặc payload. Hệ thống nội bộ nên có **correlation ID** để điều tra mà không đưa raw token/CEK/private key vào logs.

### Giới hạn tài nguyên trước decryption

- Giới hạn kích thước request, header, encryptedKey, ciphertext và số phần.
- Giới hạn thời gian/CPU cho RSA/EC operations và số lần thử.
- Không iterate toàn bộ key registry để decrypt với mọi private key nếu kid không rõ.
- Không cho zip decompression trước authenticated decryption.
- Rate-limit caller, network path và lỗi invalid_token.
- Không cache plaintext/token ở nơi không được bảo vệ.

**Fail closed** không có nghĩa chặn mọi log/monitoring. Cần telemetry đủ điều tra, nhưng không lộ dữ liệu giúp khai thác oracle.

## 20. Rotation và revocation của khóa mã hóa

Token encryption thường sử dụng ít nhất hai loại khóa nếu áp dụng nested JWT:

1. **Issuer signing key** dùng ký inner JWS.
2. **Recipient decryption key** dùng giải mã outer JWE.

Hai khóa có vòng đời, quyền truy cập và tác động khác nhau.

### Rotate recipient encryption key

Ví dụ Orders đổi từ recipient key E-old sang E-new.

~~~text
Before:
    AS encrypts JWE using public E-old
    Orders decrypts using private E-old

During rollover:
    AS learns trusted public E-new
    Orders can decrypt accepted E-old and E-new if policy allows

After switch:
    AS encrypts only to E-new
    Orders retains E-old decrypt ability for bounded lifetime
    then retires E-old securely
~~~

Khác signing-key rotation, khi chuyển public encryption key, **bên gửi** cần nhận public E-new để encrypt token mới; **bên nhận** phải có private E-new tương ứng. Nếu AS chuyển quá sớm, Orders chưa có private key mới sẽ không giải mã được và hệ thống có thể outage.

### Chỉ chấp nhận những key versions đã duyệt

Một policy có thể cho phép hai recipient keys trong giai đoạn rollover:

~~~yaml
allowedRecipientKeys:
  - keyId: orders-enc-v3
    alg: RSA-OAEP-256
    enc: A256GCM
    state: ACTIVE
  - keyId: orders-enc-v2
    alg: RSA-OAEP-256
    enc: A256GCM
    state: DECRYPT_OLD_ONLY
~~~

Đây là config nội bộ minh họa. **Không thêm một RSA key bất kỳ vào registry vì JWE header nêu kid đó.**

### Nếu private decryption key bị lộ

Attacker có E-old private key có thể giải mã những JWE đã lưu/copy được mã hóa cho E-old. **Rotate E-old sang E-new không xóa nội dung plaintext attacker đã đọc**, cũng không tự bảo đảm confidentiality của ciphertext lịch sử.

Cần:

- Dừng encrypt mới cho E-old.
- Rà soát exposure của ciphertext trong logs, queues, storage và traffic capture.
- Chuyển sang E-new sạch với ACL/HSM/KMS phù hợp.
- Rút/giới hạn decrypt permission E-old khi chính sách cho phép.
- Đánh giá khả năng phải re-encrypt dữ liệu lưu trữ, refresh/reissue token và thông báo incident.
- Xem xét **mức ảnh hưởng quá khứ**, vì confidentiality đã mất với ciphertext được thu thập.

**Đừng nhầm revoke decryption key với revoke JWT signing key.** Một key bị lộ cho phép attacker **đọc ciphertext**; key ký bị lộ có thể cho phép attacker **giả issuer**. Tùy môi trường, cả hai có thể cùng ảnh hưởng.

### Cẩn trọng khi xóa E-old

Nếu token còn hạn được AS encrypt cho E-old, xóa private E-old quá sớm có thể gây hàng loạt lỗi decrypt. Nhưng khi E-old đã bị compromise, tiếp tục cho E-old hoạt động để tránh outage có thể trái security policy. Chọn theo risk và kế hoạch chuyển đổi có kiểm soát.

## 21. Algorithm policy cho key stores và HSM/KMS

Một HSM/KMS có thể hỗ trợ nhiều key types/algorithms. Nhưng **permission được phép gọi Decrypt** không đồng nghĩa một service được phép giải mã mọi token hoặc mọi key handle trong tổ chức.

### Ma trận quyền

| Thành phần | Quyền cần thiết | Không nên có |
| --- | --- | --- |
| **AS token issuer** | Lấy trusted recipient public encryption key và ký inner JWT. | Đọc private decrypt key của Orders. |
| **Orders token processor** | Decrypt bằng đúng recipient key/alg được cấu hình. | Dùng private signing key AS hoặc decrypt keys của Payments. |
| **Payments processor** | Decrypt bằng key Payments. | Dùng key Orders chỉ vì kid giống nhau. |
| **KMS administrator** | Tạo/rotate/disable theo approval. | Mặc định xem plaintext token hoặc quyền phát token. |
| **Security responder** | Emergency revoke/rotate theo incident policy. | Bỏ audit hoặc cho mọi caller decrypt bằng key cũ. |
| **Untrusted HTTP caller** | Trình token theo API contract. | Chỉ định arbitrary key handles hoặc mở thêm alg. |

### Key handle là tham chiếu, không phải authority

Không viết một API như:

~~~json
{
  "jwe": "ENCRYPTED_TOKEN_PLACEHOLDER",
  "kms_key_handle": "any-key-in-production"
}
~~~

rồi để caller quyết định key cần decrypt. **Server phải chọn key từ recipient policy**. Key handle có thể xuất hiện trong cấu hình nội bộ nhưng không nên mở cho caller tùy ý yêu cầu.

### KMS Sign/Decrypt và algorithm policy

Có KMS yêu cầu caller gửi **algorithm ID**; có KMS tự chọn theo key metadata. Bất kể provider:

- Enforce đúng **allowed alg/enc pair** trước khi gọi KMS.
- Kiểm key type, purpose, issuer/recipient, key state và environment.
- Không chấp nhận fallback RSA1_5 nếu RSA-OAEP-256 lỗi.
- Không cho caller đổi từ asymmetric key management sang symmetric dir.
- Kiểm lỗi decrypt trước khi parse plaintext, không ghi CEK vào logs.
- Đo KMS errors/latency/unauthorized decrypt calls và áp rate limiting.

**Algorithm policy của ứng dụng và key policy của KMS phải bổ trợ nhau.** Một bên cấu hình đúng nhưng bên còn lại cho phép key misuse vẫn có thể gây sự cố.

## 22. Token lifecycle: encryption không giải quyết expiration hay revocation

Một JWE được giải mã thành công vẫn có thể là credential:

- **Quá hạn**.
- **Chưa có hiệu lực** (nbf tương lai).
- **Sai audience**.
- **Thiếu scope**.
- **Đã revoke**.
- **Được cấp cho client/tenant khác**.
- **Bị copy và phát lại** nếu là Bearer.
- **Có signature đúng nhưng AS đã cấp quyền sai do bug issuance policy**.

### Bearer replay

Giả sử attacker copy nguyên Compact JWE từ log:

~~~text
JWE: integrity tag valid
inner signed JWT: signature valid
exp: not expired
aud: Orders
scope: orders:read
~~~

Attacker không cần biết plaintext hoặc khóa giải mã để **gửi nguyên chuỗi Bearer token** tới Orders. Nếu Orders chấp nhận bearer token và không có sender proof, nó có thể cấp cùng quyền cho attacker.

**Encryption không ngăn token theft hoặc replay.**

Các biện pháp bổ trợ:

- TLS cho các hop liên quan.
- Không đưa token vào URL, logs, exception messages, analytics.
- Access token TTL ngắn, scope và audience tối thiểu.
- Quyền trên tài nguyên/tenant ở RS.
- Token revocation/introspection/denylist khi cần chặn trước exp.
- DPoP hoặc mTLS certificate-bound tokens theo profile nếu sender-constraining cần thiết.
- Refresh token rotation và client credential security để tránh attacker xin token mới.

### Opaque token

Một opaque AT có thể là chuỗi ngẫu nhiên/reference token, không phải JWE Compact. Không ép mọi opaque token qua JWE parser. RS có thể introspect token theo RFC 7662, kiểm active, aud, scope và các điều kiện bảo mật phù hợp.

### Refresh token

Refresh token không mặc định là JWT/JWE. Nó thường chỉ dùng ở AS token endpoint và cần quản lý riêng: storage, rotation/reuse detection, grant/session binding và revocation.

Một hệ thống có thể mã hóa RT để lưu hoặc vận chuyển, nhưng **JWE encryption không tự thay refresh grant validation**.

### OIDC ID token

OIDC ID token dành cho Relying Party, không tự là OAuth AT. Nếu ID token được encrypted, RP vẫn cần kiểm issuer, audience=client_id, nonce/azp/auth_time khi áp dụng, chữ ký hoặc cơ chế profile yêu cầu.

**Đừng để Resource Server nhận ID token chỉ vì nó decrypt được bằng một key nào đó.**

## 23. Những tình huống vận hành và lỗi policy

### Case A — Client tự chọn alg=dir thay RSA-OAEP-256

Orders chỉ hỗ trợ RSA-OAEP-256 + A256GCM. Attacker gửi header alg=dir, enc=A256GCM để hy vọng service dùng một secret nội bộ làm CEK.

**Đúng:** reject trước decryption vì **cặp alg–enc không nằm trong allowlist**. Không thử secret fallback hoặc đoán key theo kid.

### Case B — Cho cả hai thuật toán nhưng thiếu pair binding

Policy có hai cặp:

~~~text
profile X: RSA-OAEP-256 + A256GCM
profile Y: dir + A128GCM
~~~

Verifier chỉ kiểm alg trong {RSA-OAEP-256, dir} và enc trong {A256GCM, A128GCM}, rồi chấp nhận dir+A256GCM dù chưa kiểm.

**Đúng:** dùng **exact allowed pairs** với key identity/purpose theo từng profile, không lấy cross product của hai danh sách.

### Case C — Inner JWT không ký

Attacker có public encryption key Orders, tự tạo JWE hợp lệ chứa JSON:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "admin",
  "scope": "orders:approve"
}
~~~

Orders giải mã được thành công.

**Đúng:** nếu profile yêu cầu inner signed JWT, reject vì không có **issuer JWS signature**. Public-key encryption cho recipient không chứng minh ai tạo plaintext.

### Case D — RSA1_5 legacy enabled

Một service bị cấu hình tự thử RSA1_5 khi RSA-OAEP-256 decrypt không thành công, và lỗi được trả chi tiết theo padding.

**Rủi ro:** tăng attack surface chosen-ciphertext/oracle và dùng một thuật toán key management ngoài policy.

**Đúng:** không fallback; từ chối alg ngoài allowlist và thống nhất lỗi externally. Nếu tồn tại legacy client thực sự cần migration, xử lý trong một profile riêng có security review và deadline ngừng dùng.

### Case E — zip=DEF làm phình plaintext

Attacker gửi JWE hợp lệ theo một profile có zip=DEF, payload nén rất nhỏ nhưng giải nén thành nhiều MB/GB.

**Đúng:** reject zip nếu không cần. Nếu hỗ trợ, giới hạn kích thước sau giải nén, CPU và memory; chỉ decompress sau authenticated decryption.

### Case F — kid trỏ sang khóa của Payments

Orders và Payments cùng đặt kid=key-v2 nhưng private keys khác nhau. Một resolver tìm theo global kid map và đưa key Payments cho Orders.

**Đúng:** key lookup ràng với **recipient, environment, key purpose và trusted registry**. Không chọn dựa trên kid toàn cục.

### Case G — JWE decrypt đúng nhưng issuer sai

Orders giải mã một nested JWE hợp lệ, inner JWS có signature đúng của một AS khác mà Orders không tin.

**Đúng:** reject vì expectedIssuer không khớp, dù cả hai lớp crypto đều chạy thành công với những keys khác nhau.

### Case H — GCM IV reuse khi alg=dir

Hai AS replicas dùng cùng symmetric CEK và tự tạo một IV counter bắt đầu từ zero khi startup. Hai replicas có thể dùng cùng (key, IV).

**Rủi ro:** catastrophic AES-GCM nonce reuse; confidentiality và integrity có thể mất.

**Đúng:** dùng JOSE library/nonce generation strategy được review cho concurrency/replicas, message limits và rotation; không tự ghép IV từ timestamp hoặc local counter thiếu phối hợp.

### Case I — KMS decrypt thành công nhưng access token đã bị revoke

Orders decrypt JWE, inner signature đúng và exp còn hạn, nhưng token jti/grant đã revoked.

**Đúng:** áp **token revocation state/introspection/denylist** theo policy. Algorithm policy và AES-GCM không tự biết token còn active không.

### Case J — Outer encrypt key rotation bị lệch

AS bắt đầu encrypt bằng recipient E-new trước khi Orders phân phối private E-new; mọi request mới lỗi invalid_token.

**Đúng:** phối hợp prepublish/recipient readiness, chỉ activate encryption-to-E-new sau khi Orders có thể decrypt, theo kế hoạch rollback an toàn. Không nới alg hoặc bỏ tag verification để xử lý outage.

### Case K — Debug log lộ Compact JWE

Một team cho rằng JWE ciphertext không nhạy cảm nên ghi nguyên token vào access log. Attacker lấy chuỗi JWE và phát lại tới Orders.

**Đúng:** coi **raw Bearer JWE cũng là credential**. Redact authorization headers, không log token string, kiểm truy cập logs và xử lý token/grant liên đới.

### Case L — Key compromised nhưng token vẫn decrypt

Private E-old bị lộ. Operator chỉ chuyển AS encrypt sang E-new và tuyên bố sự cố xong.

**Không đủ:** attacker có thể giải mã ciphertext JWE cũ đã lưu. Phải điều tra lịch sử dữ liệu đã bị thu thập, các nơi lưu ciphertext, khả năng reissue/re-encrypt và bảo vệ token confidentiality về sau.

### Case M — JWE JSON và Compact parser confusion

Một endpoint chỉ được phép Compact JWE nhưng thư viện tự thử JSON Serialization khi Compact parse fail, dẫn đến code path xử lý headers không được review.

**Đúng:** endpoint xác định serialization được phép, parser strict và fail closed. Các JSON Serialization variants chỉ được bật trong profile riêng có kiểm thử tương ứng.

## 24. Observability, audit và policy drift

Để phát hiện cấu hình algorithm policy bị nới lỏng hoặc khóa sai purpose, có thể theo dõi:

~~~text
JWE_REJECT_UNSUPPORTED_ALG
JWE_REJECT_UNSUPPORTED_ENC
JWE_REJECT_DISALLOWED_ALG_ENC_PAIR
JWE_REJECT_WRONG_RECIPIENT_KEY
JWE_REJECT_UNTRUSTED_KID
JWE_REJECT_UNSUPPORTED_CRIT
JWE_REJECT_ZIP_POLICY
JWE_AUTHENTICATION_TAG_FAILURE
JWE_KMS_DECRYPT_DENIED
JWE_KMS_DECRYPT_ERROR
JWE_INNER_JWS_SIGNATURE_INVALID
JWE_INNER_ISSUER_MISMATCH
JWE_INNER_AUDIENCE_MISMATCH
JWE_INNER_TOKEN_TYPE_MISMATCH
JWE_DECRYPTION_RATE_LIMITED
JWE_KEY_ROTATION_READINESS_FAILURE
JWE_POLICY_CONFIG_VERSION_MISMATCH
~~~

Các tên chỉ là ví dụ metrics nội bộ, không phải các error codes JOSE chuẩn.

### Nên đo gì?

- Tỷ lệ reject theo **alg/enc pair**, không chỉ alg riêng.
- Request size, token size, CPU/decrypt latency và rate-limit events.
- Unknown kid và key-use mismatch theo recipient.
- Decryption/tag failures nhưng **không tiết lộ chi tiết secret-bearing errors cho caller**.
- Inner JWS signature và semantic failures.
- Tỷ lệ traffic dùng recipient encryption key cũ/mới trong rollout.
- KMS unauthorized decrypt, key state, rotation và audit events.
- Deployment drift: một replica chấp nhận alg ngoài policy trong khi các replica khác từ chối.

### Audit record gợi ý

~~~text
timestamp
requestId / correlationId
service, environment, profile_id
policy_version
recipient_key_id / trusted fingerprint
outer alg, outer enc (sau lọc về known names)
result category, latency, error code
inner issuer/audience validation result (không copy claims thô)
change/incident ID nếu có
~~~

**Không log raw JWE/JWS, CEK, private key, HMAC secret, full plaintext claims hoặc Authorization header**. Cần giới hạn retention và quyền xem telemetry vì metadata vẫn có thể gắn với hoạt động user/tenant.

### Policy drift cần có kiểm soát

Một service mới rollout hoặc một version thư viện mới có thể **tự bật thêm algorithms** theo defaults. Nên có:

1. Policy được review/versioned trong configuration management.
2. Startup tests và integration tests bảo đảm allowlist không thay đổi ngoài change.
3. Canary tests trên từng replica/zone.
4. Alert nếu phát hiện algorithm pair ngoài profile xuất hiện trong accepted traffic.
5. Rollback có kiểm soát, không đưa RSA1_5/dir/zip vào làm giải pháp tạm thời không phê duyệt.

**Cấu hình algorithm policy là một phần của security posture**, cần review như thay đổi IAM hoặc key custody, không coi là thay đổi parser nhỏ.

## 25. Negative tests cho algorithm policy

Các kiểm thử cần chạy trên **test keys, synthetic claims và môi trường được ủy quyền**. Không dùng private key production hoặc raw token của người dùng làm fixtures công khai.

| Test | Đầu vào hoặc điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **Allowed pair** | RSA-OAEP-256 + A256GCM, recipient key đúng. | JWE authenticated decryption thành công; tiếp tục kiểm inner JWT. |
| **Unexpected RSA-OAEP** | Policy chỉ cho RSA-OAEP-256, token dùng RSA-OAEP. | Từ chối alg ngoài exact pair. |
| **RSA1_5 downgrade** | Token dùng RSA1_5. | Từ chối theo profile an toàn. |
| **alg=dir downgrade** | RSA-only recipient nhận dir. | Từ chối trước decryption. |
| **alg=none trong JWE** | Header khai một alg không hỗ trợ. | Từ chối, không coi như plaintext. |
| **JWS alg=none bên trong** | Outer JWE hợp lệ chứa unsigned inner JWT. | Từ chối vì thiếu issuer signature. |
| **Unknown alg** | Key management algorithm không được allowlist. | Từ chối, không fallback. |
| **Unknown enc** | Content encryption method không được cho phép. | Từ chối. |
| **Cross-product pair** | Cả alg và enc riêng lẻ trong danh sách nhưng cặp không được duyệt. | Từ chối exact-pair validation. |
| **Swap enc strength** | A256GCM đổi thành A128GCM ngoài policy. | Từ chối, không tự nới profile. |
| **Wrong key type** | RSA-OAEP-256 với oct/EC key. | Từ chối key-type mismatch. |
| **Wrong key use** | AS signing RSA key được chỉ tới như recipient decrypt key. | Từ chối key-purpose violation. |
| **Wrong recipient** | Token mã hóa cho Payments gửi Orders. | Orders từ chối, không thử Payments key. |
| **Wrong environment** | JWE staging gửi production. | Production từ chối recipient/issuer/profile. |
| **Kid thuộc tenant khác** | Cùng kid, registry global có key của tenant khác. | Không cross-tenant key selection. |
| **Unknown kid** | Header kid không nằm trong recipient registry. | Từ chối, không fallback to all keys. |
| **Kid alias wrong material** | Header nêu kid nhưng fingerprint khác key đã đăng ký. | Từ chối. |
| **Kid path traversal** | kid chứa đường dẫn/SQL fragment. | Không đọc file, không injection. |
| **Untrusted jku** | JWE header trỏ URL keys do attacker quản lý. | Không fetch/tin URL đó. |
| **Untrusted embedded jwk** | Header mang key tự khai. | Không dùng làm trust anchor. |
| **Wrong key status** | Recipient decrypt key bị revoke/disabled. | Không decrypt ngoài policy. |
| **JWE malformed 4 parts** | Thiếu authentication tag segment. | Strict parse fail. |
| **JWE malformed 6 parts** | Thừa segment. | Strict parse fail. |
| **Invalid Base64URL** | Header/ciphertext chứa bytes không hợp lệ theo encoding. | Từ chối. |
| **Oversized header** | Protected header cực lớn. | Giới hạn trước parse/decrypt. |
| **Oversized ciphertext** | JWE lớn vượt profile. | Từ chối hoặc rate-limit trước cryptographic work. |
| **Too many nested layers** | JWE chứa nhiều nested JWE/JWS không được profile cho phép. | Từ chối parse depth. |
| **Unexpected JSON serialization** | Compact-only endpoint nhận JWE JSON. | Từ chối. |
| **Unsupported crit** | Header crit chứa extension không hiểu. | Từ chối. |
| **zip not allowed** | Header zip=DEF trong profile không compression. | Từ chối. |
| **zip bomb** | Payload hợp lệ nhưng giải nén quá giới hạn. | Từ chối theo size/CPU/memory budget. |
| **Modified protected header** | Sửa enc/kid sau khi JWE được tạo. | Header/policy hoặc AEAD authentication fail. |
| **Modified encrypted key** | Flip bit trong wrapped CEK. | Decryption/authentication fail. |
| **Modified IV** | Flip bit trong IV. | AEAD decryption/tag fail. |
| **Modified ciphertext** | Flip bit ciphertext. | AEAD authentication fail. |
| **Modified tag** | Flip bit authentication tag. | AEAD authentication fail. |
| **Truncated tag** | Tag thiếu bytes. | Strict JWE/AES-GCM validation fail. |
| **Empty encryptedKey with RSA** | RSA-OAEP-256 nhưng encryptedKey rỗng. | Từ chối format/key unwrap. |
| **Non-empty encryptedKey with dir** | dir profile nhưng có wrapped key bất thường. | Từ chối theo JOSE rules. |
| **GCM wrong key length** | A256GCM nhưng CEK không đủ 256 bit. | Từ chối, không tự pad/truncate. |
| **GCM nonce reuse** | dir cùng CEK/IV được dùng lại. | Encryption tests/design review phát hiện và sửa. |
| **GCM tag checked late** | Business layer xử lý plaintext trước verify tag. | Test phải phát hiện, cấm sử dụng trước authentication. |
| **RSA padding error detail** | Caller quan sát nhiều error messages cho decrypt failures. | Unified invalid_token, không lộ oracle details. |
| **RSA error timing distinction** | Thời gian xử lý khác biệt đủ đáng kể theo failure class. | Review/mitigate side channel với library/controls. |
| **ECDH wrong curve** | Public ephemeral key sai curve/profile. | Từ chối, không tùy biến curve. |
| **ECDH missing epk** | JWE ECDH-ES thiếu tham số bắt buộc. | Từ chối. |
| **ECDH invalid public point** | epk không hợp lệ. | Cryptographic validation fail. |
| **ECDH-ES vs ECDH-ES+A256KW** | Header đổi key-management mode. | Từ chối nếu ngoài allowed pair/profile. |
| **PBES2 password guessing** | Password-derived JWE ngoài profile. | Từ chối, không tự nhận password user nhập. |
| **PBES2 excessive p2c** | Request đặt iteration count cực lớn. | Giới hạn/từ chối trước KDF DoS. |
| **Nested plaintext JSON** | Outer JWE hợp lệ nhưng inner không phải signed JWT. | Từ chối, không tự dựng claims. |
| **Inner bad signature** | Inner JWS có claims đúng nhưng signature giả. | Từ chối issuer authentication. |
| **Inner wrong alg** | Issuer PS256-only nhưng JWS dùng HS256/RS256/none. | Từ chối algorithm policy ở inner. |
| **Inner untrusted kid** | JWS chọn public key ngoài issuer trust set. | Từ chối. |
| **Inner wrong issuer** | Signature hợp lệ từ AS khác. | Từ chối. |
| **Inner wrong audience** | AT Payments được mã hóa cho Orders. | Orders từ chối aud. |
| **Inner wrong typ** | ID token được đưa làm access token. | Từ chối profile/type. |
| **Inner expired exp** | Token quá hạn. | Từ chối. |
| **Inner nbf future** | Token chưa có hiệu lực. | Từ chối. |
| **Inner scope thiếu** | orders:read token gọi approve. | Từ chối authorization. |
| **Inner cross-tenant** | Token hợp lệ nhưng order thuộc tenant khác. | Từ chối business permission. |
| **Inner revoked jti** | JWT còn hạn nhưng đã revoke. | Từ chối theo token state policy. |
| **Bearer JWE replay** | Gửi lại nguyên token đã copy. | Phơi bày replay risk; áp sender-binding/revocation theo profile. |
| **DPoP required but missing** | Bound access token không có DPoP proof. | Từ chối. |
| **DPoP key mismatch** | Proof ký bởi key khác cnf. | Từ chối. |
| **KMS decrypt unauthorized** | Service không có quyền Decrypt gọi KMS. | IAM/policy từ chối, audit. |
| **KMS timeout** | Decrypt service unreachable. | Fail closed, không thử key ngoài registry. |
| **Rotate E-new too early** | AS encrypt E-new trước Orders readiness. | Canary/test phát hiện và dừng rollout. |
| **Retired E-old** | Token cũ dùng key không còn được chấp nhận. | Từ chối theo key lifecycle policy. |
| **Policy drift** | Một replica cho phép dir+A256GCM ngoài profile. | Deployment/security test phát hiện mismatch. |
| **Logging raw JWE** | Access logger ghi Authorization header. | DLP/secret scanner phát hiện, redaction. |
| **JWE decrypted without signature** | Outer AEAD hợp lệ nhưng không có issuer origin auth. | Từ chối nếu profile yêu cầu nested signed JWT. |

### Sáu kiểm tra tối thiểu cho mỗi release

~~~text
1. Unsupported alg or enc -> REJECT before decrypt.
2. Allowed alg and allowed enc but disallowed pair -> REJECT.
3. Wrong kid/recipient key/purpose -> REJECT.
4. Valid decrypt but invalid/missing inner JWS -> REJECT.
5. Valid nested token but wrong iss/aud/exp/scope -> REJECT.
6. Valid token in intended scope -> authorize only per resource policy.
~~~

## 26. Checklist triển khai production

1. **Profile:** Endpoint xác định rõ loại token và JWE serialization được phép?
2. **Outer alg:** Có allowlist key management algorithm chính xác?
3. **Outer enc:** Có allowlist content encryption method chính xác?
4. **Pair binding:** Policy kiểm exact alg–enc pairs thay vì cross product?
5. **Key type:** RSA/EC/OKP/oct phù hợp mỗi thuật toán?
6. **Key purpose:** Encryption keys không bị dùng lẫn AS signing/mTLS/logging keys?
7. **Recipient:** Key được chọn theo trusted recipient registry và environment?
8. **kid:** Chỉ dùng làm hint/lookup trong registry, không làm đường dẫn/URL/tin cậy?
9. **jku/jwk/x5u:** Không tin key source do token tự chỉ định?
10. **Key status:** Có kiểm active/retired/revoked và version của recipient key?
11. **Algorithm downgrade:** Không tự fallback từ RSA-OAEP-256 sang RSA1_5 hoặc dir?
12. **PBES2:** Không mở password-based JWE ngoài policy và resource bounds?
13. **AEAD:** Có dùng content encryption có authentication tag được kiểm đúng?
14. **IV/nonce:** Có bảo đảm uniqueness theo CEK, concurrent replicas và message limits?
15. **CEK:** Có kích thước, entropy, lifecycle phù hợp alg/enc?
16. **AAD:** Protected header được xác thực đúng bytes theo JWE?
17. **crit:** Unsupported critical extensions bị từ chối?
18. **zip:** Compression bị tắt hoặc có size/CPU/decompression safeguards?
19. **cty:** Nested-JWT profile bắt buộc inner signed token khi yêu cầu?
20. **Inner JWS:** Có allowlist JWS signature algorithm, trusted issuer keys?
21. **Issuer:** iss được xác thực sau signature; outer JWE không được coi là chứng cứ issuer?
22. **Audience:** aud khớp chính xác resource intended recipient?
23. **Token type:** Không lẫn ID token, access token, refresh token và assertions?
24. **Time:** exp/nbf/iat được xử lý theo profile/clock skew?
25. **Scope:** Endpoint kiểm scope chính xác và quyền tối thiểu?
26. **Business permission:** Có tenant/ownership/record-level authorization?
27. **Revocation:** Có token/grant/key revocation khi rủi ro yêu cầu?
28. **Replay:** Bearer JWE không bị xem là tự chống replay; có sender proof khi cần?
29. **TLS:** Giao tiếp qua TLS với hostname/certificate policy?
30. **Input limits:** Có giới hạn token/header/ciphertext/plaintext size và parse depth?
31. **Parser:** Không tự sửa token malformed hoặc fallback giữa formats vô hạn?
32. **Errors:** Decryption/key unwrap/tag errors không lộ oracle details?
33. **KMS:** Quyền Decrypt/Sign/Generate/Disable được tách theo service identity?
34. **Rotation:** Có kế hoạch E-old/E-new, issuer/recipient readiness và rollback an toàn?
35. **Compromise:** Có playbook lộ private decryption key, đánh giá ciphertext lịch sử?
36. **Observability:** Có metrics unsupported pair, unknown kid, tag fail, inner signature fail?
37. **Log hygiene:** Không log raw JWE/JWS, CEK, private key hoặc plaintext claims nhạy cảm?
38. **Policy drift:** Mọi replica dùng cùng reviewed config/version, không tự bật thuật toán?
39. **Negative tests:** Có tamper tests ở header/encryptedKey/IV/ciphertext/tag?
40. **Review:** Thuật toán/parameters/profiles tuân RFC 7516/7518 và chính sách hiện hành?

## 27. Bài tập tự kiểm tra algorithm policy

### Bài tập 1 — Cặp thuật toán bị nới lỏng

Một profile có allowed pairs:

~~~text
RSA-OAEP-256 + A256GCM
dir + A128GCM
~~~

Nhưng code kiểm alg và enc độc lập bằng hai sets, nên token dùng dir+A256GCM cũng được đưa qua decryption.

**Câu hỏi:** Lỗi ở đâu?

**Phân tích:** Đây là lỗi **pair binding**. Hai tập allowlist riêng tạo cross product của tổ hợp, có thể mở những cặp chưa được phê duyệt. Phải lưu allowlist theo **cặp gắn với key profile và recipient**, không cho tự trộn.

### Bài tập 2 — JWE thành công nhưng thiếu chữ ký

Một attacker lấy public key mã hóa của Orders và tạo JWE với inner claims sub=admin, scope=orders:approve. Orders decrypt thành công bằng private key thật.

**Câu hỏi:** Có nên cấp quyền không?

**Phân tích:** Không. Public-key encryption bảo vệ thông điệp cho recipient nhưng **bất kỳ bên nào biết public key có thể encrypt**. Orders phải kiểm nguồn phát hành đáng tin như inner signed JWT theo profile, rồi kiểm aud, exp và permission.

### Bài tập 3 — JWE có tag sai nhưng parser đã dùng claims

Một developer stream plaintext từ AES-GCM decrypt vào JSON parser, gọi business logic rồi mới kiểm tag khi doFinal hoàn tất.

**Câu hỏi:** Tại sao không an toàn?

**Phân tích:** Nội dung chưa được xác thực đã tác động quyết định ứng dụng. Phải đợi authenticated decryption/tag verification **thành công hoàn toàn** trước khi sử dụng plaintext.

### Bài tập 4 — RSA-OAEP-256 key rotation

AS dùng public E-new để encrypt, Orders mới có private E-old. Token mới bị từ chối với unknown kid.

**Câu hỏi:** Có nên cho Orders “try any key” hoặc tắt validation không?

**Phân tích:** Không. Cần rollback/rollout plan được duyệt, phân phối private E-new và trusted key metadata đến Orders trước activation. Chỉ thử keys thuộc **recipient registry có trạng thái rõ ràng**, không brute-force mọi private key.

### Bài tập 5 — Token JWE bị sao chép

Một Compact JWE raw được tìm thấy trong access log. Attacker không có private decryption key. Token còn hạn và bearer.

**Câu hỏi:** Encryption có chặn attacker sử dụng token không?

**Phân tích:** Không. Attacker có thể **replay nguyên Bearer token**; không cần giải mã để sử dụng. Phải coi raw JWE là credential cần redaction, cân nhắc revoke và sender-constraining tùy risk.

### Bài tập 6 — JWS alg và JWE alg bị nhầm

Một bộ lọc đọc outer JWE header có alg=RSA-OAEP-256 rồi cho rằng issuer đã dùng RSA-OAEP-256 để ký JWT.

**Câu hỏi:** Bộ lọc sai ở đâu?

**Phân tích:** **JWE alg là key management**; JWS alg ở inner signed JWT mới quy định signature algorithm. Hai lớp có trust anchors và validators khác nhau. Cần verify cả outer JWE và inner JWS, không dùng một giá trị alg cho cả hai.

### Cây quyết định kiểm JWE

~~~mermaid
flowchart TD
    A["Nhận encrypted token"] --> B{"Đúng serialization/size policy?"}
    B -->|Không| X["DENY"]
    B -->|Có| C{"(alg,enc) trong allowed pairs?"}
    C -->|Không| X
    C -->|Có| D{"Recipient key/kid/purpose/status tin cậy?"}
    D -->|Không| X
    D -->|Có| E{"JWE authenticated decryption đạt?"}
    E -->|Không| X
    E -->|Có| F{"Profile yêu cầu inner signed JWT?"}
    F -->|Có| G{"JWS signature/issuer/typ hợp lệ?"}
    G -->|Không| X
    G -->|Có| H["Validate semantic claims"]
    F -->|Không| I["Xác thực nguồn gốc theo profile khác"]
    I --> H
    H --> J{"aud, time, scope, permission, state đạt?"}
    J -->|Không| X
    J -->|Có| K["ALLOW trong quyền được cấp"]
~~~

## Kết luận

**Kiểm tra algorithm policy** là một yêu cầu cốt lõi khi ứng dụng nhận token được mã hóa. Header của JWE mô tả thuật toán nhưng **không được phép tự quyết định những thuật toán, keys hoặc trust anchors mà ứng dụng sẽ chấp nhận**.

Những nguyên tắc cần giữ:

- **JWE alg** là cơ chế key management; **JWE enc** là content encryption; **JWS alg** là cơ chế chữ ký/MAC của lớp ký. Không trộn ba ý nghĩa.
- Kiểm **exact allowlist của cặp alg–enc**, ràng với recipient, key type, purpose, issuer/trust domain và token profile.
- Dùng **authenticated encryption** đúng cách: CEK/IV/tag/AAD theo JOSE, không dùng plaintext trước khi xác minh tag và không reuse GCM nonce cùng key.
- **Decrypt JWE thành công không tự chứng minh issuer đã phát token**, đặc biệt với public-key encryption. Nếu profile yêu cầu, phải verify inner signed JWT.
- Không fallback sang RSA1_5, dir, password-based JWE, unknown key source, zip hoặc JOSE extensions chỉ vì thư viện có hỗ trợ.
- Sau cryptographic validation vẫn phải kiểm **iss, aud, typ, exp, scope, client/principal, revocation, sender proof và business permission**.
- Encryption bảo vệ **confidentiality**, không tự ngăn **Bearer token theft/replay**.
- Cần **key lifecycle, KMS ACL, unified error handling, kiểm thử downgrade/tamper và observability** để duy trì policy qua deployments.

Một hệ thống token bảo mật không chỉ “giải mã được JWT”; nó chỉ **chấp nhận đúng loại token, đúng thuật toán và key đã được tin, đúng nguồn phát hành, đúng audience và đúng quyền**.

### Tài liệu tham khảo

- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final)
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)





