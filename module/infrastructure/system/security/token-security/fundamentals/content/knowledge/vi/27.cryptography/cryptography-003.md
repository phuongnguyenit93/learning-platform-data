# Signing khác encryption

Trong hệ thống bảo mật dựa trên token, hai từ **signing (ký)** và **encryption (mã hóa)** thường xuất hiện cạnh nhau: JWT có chữ ký, dữ liệu qua HTTPS được mã hóa, refresh token phải lưu an toàn, hoặc access token có thể là **JWS** hay **JWE**. Nhưng hai thao tác này trả lời **hai câu hỏi bảo mật khác nhau**:

- **Signing:** *“Nội dung có bị sửa đổi không, và bằng chứng này có đến từ bên sở hữu khóa ký hợp lệ không?”*
- **Encryption:** *“Ai có thể đọc nội dung?”*

Một JWT **được ký** có thể xác minh là do Authorization Server (AS) phát hành, nhưng nội dung payload **thường vẫn đọc được** bởi bất kỳ ai có token. Một token **được mã hóa** che giấu payload khỏi người không có khóa giải mã, nhưng **việc giải mã được không tự chứng minh user có quyền gọi API**. Trong cả hai trường hợp, Resource Server (RS) còn phải kiểm tra issuer, audience, thời hạn, scope, tenant và quyền trên từng tài nguyên.

Bài **“Signing khác encryption”** thuộc chương **Cryptography** trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là hiểu đúng các thuộc tính mật mã, cấu trúc JWT/JWS/JWE, quản lý khóa, lỗi triển khai và mối liên hệ với access/refresh token, OAuth 2.0/OIDC, lưu trữ, thu hồi, đánh cắp và phát lại token.

> **Ghi nhớ ngay:** **Chữ ký không giấu nội dung. Mã hóa không mặc nhiên xác lập quyền sử dụng token. Base64url không phải mã hóa mật mã.** JWT được xác minh cryptographically cũng chưa đủ để cho phép truy cập API.

## 1. Mô hình tư duy: bảo vệ điều gì?

Giả sử AS cấp một token chứa:

~~~json
{
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1800000900
}
~~~

Người dùng gửi token tới Orders API qua HTTPS. Có ít nhất **năm yêu cầu riêng biệt**:

| Yêu cầu | Câu hỏi | Kỹ thuật/kiểm soát điển hình |
| --- | --- | --- |
| **Integrity – toàn vẹn** | Payload có bị thay đổi từ lúc được bảo vệ? | JWS signature, MAC, AEAD authentication tag |
| **Origin authentication – xác thực nguồn** | Bên nào có khả năng tạo bằng chứng hợp lệ? | Digital signature với khóa issuer, MAC với secret chung và trust policy |
| **Confidentiality – bí mật** | Ai có thể đọc nội dung? | JWE, TLS, AES-GCM, mã hóa lưu trữ theo threat model |
| **Freshness/replay defense** | Credential này có còn được phép dùng, có bị phát lại không? | `exp`, `nbf`, revocation, DPoP/mTLS, one-time code/nonce theo ngữ cảnh |
| **Authorization – phân quyền** | Chủ thể này được làm thao tác nào trên bản ghi nào? | `aud`, `scope`, roles/tenant, ownership, business policy |

**Không nên dùng một cơ chế để suy ra tất cả các yêu cầu.** Signature không che giấu `sub`/PII; encryption không tự ràng buộc quyền; expiry không phòng được token theft trước khi hết hạn.

### 1.1. Ví dụ đơn giản: tài liệu được ký và tài liệu được niêm phong

- **Tài liệu có chữ ký số:** người nhận đọc được nội dung và kiểm tra chữ ký để phát hiện sửa đổi; không có ý nghĩa “nội dung chỉ người nhận đọc được”.
- **Tài liệu trong phong bì mã hóa:** người không có khóa không đọc được nội dung; nếu chỉ mã hóa theo public key người nhận, người nhận chưa chắc biết **ai gửi**, vì người bất kỳ cũng có thể biết public key ấy.
- **Vừa ký vừa mã hóa:** nội dung chỉ người có khóa giải mã đọc được, và khi giải mã có thể kiểm tra chữ ký của bên phát hành theo chính sách tin cậy.

**Ẩn danh, chống chối bỏ và quyền pháp lý** không tự có chỉ vì thuật toán có chữ “signature”; còn phụ thuộc ownership/protection của khóa, chứng thực định danh, audit và pháp luật.

## 2. Phân biệt encoding, hashing, MAC, signing và encryption

Các khái niệm sau dễ bị gọi chung là “mã hóa” nhưng có bảo đảm khác nhau:

| Phép toán | Đầu vào | Đầu ra | Có giữ bí mật nội dung? | Mục đích chính |
| --- | --- | --- | --- | --- |
| **Encoding** (Base64url, hex) | Bytes | Chuỗi biểu diễn | **Không** | Truyền/lưu bytes bằng ký tự thuận tiện |
| **Hash** (SHA-256) | Dữ liệu | Digest | **Không** | Dấu vân tay nội dung; chưa xác thực nguồn |
| **MAC/HMAC** | Dữ liệu + shared secret | Authentication tag | **Không** | Toàn vẹn và xác thực bên biết secret |
| **Digital signature** | Dữ liệu + private signing key | Chữ ký | **Không** | Toàn vẹn và bằng chứng từ khóa ký; public verify |
| **Symmetric encryption** | Plaintext + secret encryption key | Ciphertext | **Có**, theo thuật toán/mode | Giữ bí mật giữa các bên có khóa |
| **Asymmetric encryption / KEM** | Dữ liệu hoặc khóa phiên + public encryption key | Ciphertext / encapsulation | **Có**, khi thiết kế đúng | Mã hóa cho một người nhận giữ private key |
| **AEAD** (AES-GCM) | Plaintext, key, nonce, AAD | Ciphertext + tag | **Có** | Bí mật và phát hiện sửa đổi ciphertext/AAD |

### 2.1. Base64url chỉ là cách biểu diễn bytes

Chuỗi JWT JWS Compact có hình dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Một người có JWT có thể **Base64url-decode phần payload** để đọc JSON mà **không cần khóa ký**. Vì vậy **đừng lưu mật khẩu, private key, mã khôi phục hoặc bí mật kinh doanh trong payload JWS rồi tin rằng đã được giấu**.

### 2.2. Hash không đủ để xác thực issuer

Nếu client nhận JSON và digest `SHA-256(JSON)`, attacker có thể đổi JSON rồi tính digest mới. Chỉ hash **không chứng minh dữ liệu do AS phát hành**. Cần HMAC với secret chung hoặc digital signature với private key issuer và khóa xác minh đáng tin.

### 2.3. HMAC không giống public-key signature

Với **HS256**, bên tạo MAC và bên kiểm tra **cùng biết secret**. Nếu RS có HS256 secret, RS có thể **tạo token có MAC hợp lệ** theo secret ấy. Với **RS256/PS256/ES256**, AS giữ **private signing key**; RS chỉ cần **public verification key**, không thể tạo signature mới nếu không sở hữu private key.

HMAC vẫn có thể phù hợp ở hệ thống nhỏ/trust domain khép kín, nhưng việc chia secret sang nhiều RS làm tăng phạm vi nguy cơ và không có khả năng xác định riêng bên nào đã tạo MAC khi secret bị chia sẻ.

## 3. Digital signing: ký bằng khóa nào, xác minh bằng khóa nào?

Với chữ ký bất đối xứng:

~~~mermaid
flowchart LR
    AS["Authorization Server\nprivate signing key"] -->|"Sign header.payload"| SIG["JWS JWT + signature"]
    SIG --> RS["Resource Server\ntrusted public verification key"]
    RS --> V{"Verify signature,\nissuer và claims?"}
    V -->|"Đạt"| P["Tiếp tục kiểm audience,\ntime, scope, tenant"]
    V -->|"Không đạt"| X["Từ chối token"]
~~~

Hai thao tác mật mã logic:

~~~text
signature = Sign(private_signing_key, signed_bytes)

valid = Verify(public_verification_key, signed_bytes, signature)
~~~

Với JWS Compact, **signed bytes thường là**:

~~~text
BASE64URL(UTF8(protectedHeader))
  + "."
  + BASE64URL(payloadBytes)
~~~

Không phải chỉ ký JSON payload trần rồi bỏ header: protected header chứa thông tin như `alg` phải được ràng buộc cryptographically. Thư viện JOSE phải thực hiện canonical byte handling/serialization đúng tiêu chuẩn; **đừng tự nối JSON bằng một thuật toán tùy ý**.

### 3.1. Chữ ký cung cấp điều gì?

Khi RS chọn **đúng khóa công khai đã được tin cậy của đúng issuer**, cho phép đúng thuật toán và verify thành công, nó có bằng chứng rằng token không bị sửa đổi và được tạo bởi bên có khả năng dùng private signing key tương ứng. Nhưng điều này **không chứng minh**:

- User vẫn đang đăng nhập;
- AS chưa revoke grant hoặc token;
- RS này nằm trong `aud`;
- Token đã có `scope` phù hợp endpoint;
- Dữ liệu đang yêu cầu thuộc tenant/owner đó;
- Client trình token là người được cấp token ban đầu, nếu đây là Bearer token.

### 3.2. Chữ ký không phải “mã hóa bằng private key”

Cụm “RSA ký là encrypt bằng private key, verify là decrypt bằng public key” là **ẩn dụ sai và nguy hiểm** đối với triển khai hiện đại. Chữ ký RSA-PSS/PKCS#1 v1.5 và mã hóa RSA-OAEP là **các scheme khác nhau** với padding, security definitions và API riêng. Không dùng một hàm `Cipher` để giả làm digital signature.

### 3.3. Vẫn cần HTTPS khi token có chữ ký

JWT JWS được ký có thể giữ nguyên chữ ký khi đi qua mạng, nhưng nếu attacker đọc trộm Bearer token, họ vẫn **sao chép và dùng lại chuỗi token** đến khi hết hạn hoặc RS ngăn revoke/replay. TLS bảo vệ transport giữa các hop; signature không giữ bí mật token trên đường truyền.

## 4. Encryption: mã hóa bằng khóa nào, giải mã bằng khóa nào?

Với **symmetric encryption**, bên mã hóa và bên giải mã dùng cùng **secret key**:

~~~text
ciphertext, authentication_tag =
    AEAD_Encrypt(secret_key, nonce, plaintext, associated_data)

plaintext =
    AEAD_Decrypt(secret_key, nonce, ciphertext, tag, associated_data)
~~~

Với **asymmetric encryption**, bên gửi dùng **public encryption key của người nhận**, còn người nhận giải mã bằng **private decryption key**. Khi payload lớn, hệ thống thường dùng **hybrid encryption/envelope encryption**:

~~~text
1. Sinh content-encryption key (CEK) ngẫu nhiên.
2. Mã hóa plaintext bằng CEK và AES-GCM.
3. Bảo vệ CEK bằng RSA-OAEP, ECDH-ES hoặc cơ chế key management phù hợp.
4. Gửi ciphertext/tag/nonce và thông tin CEK đã được bảo vệ.
5. Người nhận khôi phục CEK, verify tag rồi nhận plaintext.
~~~

**Không dùng RSA-OAEP trực tiếp để mã hóa một JWT dài hoặc JSON nhiều KB**: kích thước RSA plaintext bị giới hạn bởi modulus và padding. Dùng hybrid encryption/JWE theo thư viện chuẩn.

### 4.1. Mã hóa không tự xác định người phát hành

Nếu Alice biết **public encryption key của Bob**, Alice có thể mã hóa dữ liệu để Bob đọc. Carol cũng có thể biết khóa công khai ấy và làm tương tự. Vì vậy Bob **không được suy “giải mã được nghĩa là Alice đã gửi”** khi không có bằng chứng nguồn gốc bổ sung.

### 4.2. AES-GCM (AEAD) vừa mã hóa vừa phát hiện sửa đổi

**AES-GCM** là AEAD (*Authenticated Encryption with Associated Data*), nghĩa là ngoài tính bí mật, nó có **authentication tag** để phát hiện ciphertext hoặc AAD bị sửa đổi khi verify đúng.

Điều quan trọng:

- **Nonce/IV phải không bị dùng lại với cùng một AES-GCM key**; reuse có thể phá tính bí mật và toàn vẹn nghiêm trọng.
- **Tag phải được kiểm tra trước khi coi plaintext là đáng tin**; không bỏ qua exception khi tag sai.
- **AAD** không bị mã hóa nhưng được xác thực toàn vẹn, ví dụ thông tin phiên bản/issuer được ràng buộc đúng trong một giao thức.
- AEAD với **shared key** không mặc định chứng minh **một sender duy nhất** trong nhóm tất cả bên giữ key.
- AES-GCM không tự kiểm OAuth issuer, audience, scope hay user authorization.

### 4.3. Mã hóa có thể không đủ nếu không có integrity protection

Những mode/thiết kế encryption không xác thực (ví dụ một số cách dùng AES-CBC không có MAC) có thể bị **tampering, padding-oracle hoặc malleability attacks**. Trong giao thức mới, ưu tiên **AEAD được chuẩn hỗ trợ**, không tự kết hợp encryption và checksum bằng một thiết kế ad hoc.

## 5. Khóa ký và khóa mã hóa là hai vai trò khác nhau

Một token do AS tạo và dành cho RS có thể dùng **hai cặp khóa** khác nhau:

| Khóa | Ai giữ? | Công việc | Ai tuyệt đối không nên có? |
| --- | --- | --- | --- |
| **Issuer private signing key** | AS/KMS/HSM | Tạo JWS signature | Client/RS không được cần để verify |
| **Issuer public verification key** | RS/JWKS tin cậy | Verify JWS | Có thể công khai; phải ràng buộc đúng issuer |
| **Recipient public encryption key** | AS dùng để mã hóa cho RS | Bảo vệ CEK hoặc tạo shared secret | Bản thân public key không phải secret |
| **Recipient private decryption key** | RS được chỉ định | Giải mã JWE/khóa phiên | AS/client không được cần để decrypt |
| **Symmetric CEK** | Bên encrypt và decrypt trong ngữ cảnh JWE | Mã hóa payload với `enc` | Không được log/lộ sang caller |

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Issuer / Authorization Server
    participant RS as Recipient / Resource Server
    Note over AS: Private signing key của AS
    Note over RS: Private decryption key của RS
    AS->>AS: Tạo signed JWT bằng issuer signing key
    AS->>AS: Encrypt signed JWT cho public key của RS
    AS-->>RS: Nested JWE
    RS->>RS: Decrypt JWE bằng private decryption key
    RS->>RS: Verify JWS bằng public signing key của AS
    RS->>RS: Validate iss, aud, exp, scope, rights
~~~

**Không dùng mặc định cùng một RSA key pair cho signing và decryption**. Tách biệt khóa theo mục đích giúp giảm blast radius, phân quyền KMS/HSM, rotation và tránh confusion giữa giao thức. Một số legacy deployments có thể tái sử dụng khóa, nhưng đó cần security review, không phải thiết kế nên khuyến nghị.

## 6. JWS: JSON Web Signature

**JWS (RFC 7515)** mô tả cách bảo vệ nội dung bằng signature/MAC. Trong OAuth, JWT access token được ký thường ở dạng **JWS Compact Serialization** gồm ba phần:

~~~text
<protected-header>.<payload>.<signature>
~~~

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-signing-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "at-unique-id"
}
~~~

**Không suy giá trị `typ` ở ví dụ áp dụng cho mọi JWT**: profile RFC 9068 dùng `at+jwt` để phân biệt access token; ID token, client assertion, DPoP proof có token types/claims khác nhau. RS phải kiểm đúng token profile, không chỉ tìm ba đoạn phân cách bằng dấu chấm.

### 6.1. `kid` và JWKS

RS có thể lấy **public signing keys** qua JWKS được issuer công bố tại endpoint đã tin:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "issuer-signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

`kid` chỉ là **gợi ý chọn key trong JWKS đã ràng buộc với issuer đáng tin**, không phải quyền yêu cầu RS tải khóa từ URL tùy ý. Không tin `jku`, `x5u` hoặc embedded `jwk` do token chưa xác minh chỉ định mà bỏ qua trust policy; đó có thể dẫn đến **key injection/SSRF**.

### 6.2. Những thuật toán JWS thường gặp

| `alg` | Cơ chế | Ai có thể verify? | Lưu ý |
| --- | --- | --- | --- |
| **HS256** | HMAC-SHA-256 | Bên giữ secret chung | Verifier cũng có khả năng tạo MAC |
| **RS256** | RSA PKCS#1 v1.5 signature + SHA-256 | Ai có public key của issuer | Phải đúng scheme và kích thước khóa |
| **PS256** | RSA-PSS + SHA-256 | Ai có public key của issuer | Salt/padding theo JOSE profile |
| **ES256** | ECDSA P-256 + SHA-256 | Ai có public key của issuer | JOSE signature format khác DER mặc định ở nhiều API |
| **EdDSA** | EdDSA signature theo profile JOSE | Ai có public key của issuer | Xác nhận phiên bản thư viện/AS hỗ trợ |
| **`none`** | Unsecured JWT | Không có signature bảo vệ | Không được chấp nhận làm access token yêu cầu chữ ký |

Không có một thuật toán tối ưu cho mọi AS. **Một `alg` chỉ an toàn trong đúng profile, key type, kích thước khóa, trust registry và policy**. Đặc biệt không chọn thuật toán chỉ bằng giá trị header do attacker kiểm soát.

### 6.3. Chữ ký bảo vệ header và payload, không bảo vệ token khi bị sao chép

Attacker không thể tự sửa `scope=orders.read` thành `scope=admin` rồi giữ nguyên signature hợp lệ nếu hệ thống verify đúng. Nhưng attacker **không cần sửa gì** khi đã đánh cắp một Bearer token còn hiệu lực: họ có thể gửi nguyên token ấy tới RS nếu không có sender constraint hoặc revocation.

### 6.4. Chữ ký không cung cấp tính bí mật cho claims

Các claims như `email`, `roles`, `tenant_id` trong JWS có thể bị đọc bởi browser, proxy/log sink hoặc người giữ chuỗi token. Giảm thiểu PII, sử dụng claims cần thiết và giới hạn lifetime là yêu cầu quan trọng, kể cả token được truyền qua TLS.

## 7. JWE: JSON Web Encryption

**JWE (RFC 7516)** cung cấp cách mã hóa nội dung theo JOSE, thường kết hợp key management với content encryption. **JWE Compact Serialization** có năm đoạn:

~~~text
<protected-header>.<encrypted-key>.<iv>.<ciphertext>.<tag>
~~~

Protected header minh họa:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-rs-decrypt-2026-11",
  "cty": "JWT"
}
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| **Protected header** | Metadata như `alg`, `enc`, `kid`; **không được mã hóa**, nhưng được integrity-protected theo JWE |
| **Encrypted key** | CEK đã được bảo vệ theo `alg`; có thể rỗng với một số key-management modes như `dir` |
| **IV** | Nonce/IV cho content-encryption algorithm |
| **Ciphertext** | Nội dung được mã hóa |
| **Tag** | Authentication tag cho authenticated encryption |

**Cả năm vị trí tồn tại trong Compact Serialization**, nhưng một vị trí có thể là chuỗi rỗng tùy mode. Đừng dùng “năm đoạn đều không rỗng” làm điều kiện duy nhất nhận diện JWE.

### 7.1. `alg` của JWE khác `enc`

- **`alg`:** cách quản lý/đóng gói/thỏa thuận **content encryption key (CEK)**, ví dụ `RSA-OAEP-256`, `ECDH-ES`, hoặc `dir`.
- **`enc`:** thuật toán **mã hóa payload** bằng CEK, ví dụ `A256GCM`.

Không nhầm `alg=RS256` trong JWS (ký RSA) với `alg=RSA-OAEP-256` trong JWE (key management bằng RSA-OAEP). **RS256 không phải thuật toán mã hóa dữ liệu.**

### 7.2. JWE dùng thuật toán xác thực nội dung

JWE encryption modes theo chuẩn cung cấp bảo vệ tính toàn vẹn của ciphertext/AAD, nhưng **giải mã JWE thành công không tự xác thực issuer của một JWT bên trong** khi người bất kỳ có thể encrypt cho recipient public key.

### 7.3. JWE không làm claims biến mất với mọi bên

Ciphertext che payload khỏi các hop/bên không có decryption key. **Người nhận có private decryption key vẫn đọc được toàn bộ claims**; nếu bản thân RS hoặc app được cấp khóa giải mã bị compromise, mã hóa không bảo vệ nội dung khỏi chính bên ấy.

### 7.4. Tránh tự triển khai JWE từ primitives

JWE có quy tắc chặt về protected header serialization, authenticated additional data, key management, ECDH parameter validation, ciphertext/tag và nested content types. Trong production nên dùng **JOSE library được kiểm thử, được duy trì**, không tự ghép AES-GCM + RSA-OAEP thành định dạng token riêng rồi gọi nó là “JWE”.

## 8. Nested JWT: vừa signing vừa encryption

Khi cần **cả** bằng chứng phát hành và bí mật claims, có thể dùng **Nested JWT**:

~~~text
Inner JWS:
  issuer signs header.payload

Outer JWE:
  issuer encrypts the entire signed JWT for recipient

At recipient:
  decrypt outer JWE
  verify inner JWS signature/issuer/type/claims
  enforce OAuth authorization policy
~~~

~~~mermaid
flowchart TD
    A["Claims: iss, aud, exp, scope"] --> B["JWS ký bằng private key của AS"]
    B --> C["JWE mã hóa inner JWS cho RS"]
    C --> D["RS decrypt bằng private key nhận"]
    D --> E["RS verify JWS bằng public key AS"]
    E --> F{"Claims + rights hợp lệ?"}
    F -->|Có| G["Xử lý API"]
    F -->|Không| H["Từ chối"]
~~~

### 8.1. Vì sao thường sign rồi encrypt?

Với **signed-then-encrypted JWT**, chữ ký issuer nằm **bên trong lớp mã hóa**. Người không có private decryption key không thấy claims/signature của inner JWS; người nhận sau khi giải mã vẫn xác minh được issuer. **RFC 7519** mô tả nested JWT và nêu thứ tự **ký rồi mã hóa** khi cần cả hai.

Việc chọn profile/JWE header `cty=JWT`, token type, số lớp nesting và allowed algorithms phải theo AS/RS contract. **Không tự bỏ verify chữ ký bên trong chỉ vì outer JWE giải mã thành công.**

### 8.2. “Encrypt rồi sign” có giống không?

Một hệ thống cũng có thể ký ciphertext theo một giao thức thiết kế riêng, nhưng độ lộ metadata, người có thể xác minh signature và security properties **không giống mặc định** với nested JWT sign-then-encrypt. Đừng tráo thứ tự tùy tiện: client và RS phải tuân **một profile được chuẩn hóa, có validation rõ**.

### 8.3. Encrypted JWT có thể có chữ ký hoặc không

Một compact JWE chỉ chứa **encrypted claims set** có thể đáp ứng confidentiality/integrity cho encryption context mà không chứa inner JWS. Nếu API yêu cầu bằng chứng **AS đã ký claims**, cần **nested signed JWT** hoặc cơ chế issuer authentication được profile quy định rõ.

## 9. Signing, encryption và token trust model trong OAuth 2.0

| Điểm trao đổi | Signing/encryption có thể xuất hiện | Điều phải kiểm riêng |
| --- | --- | --- |
| **AS → OAuth client** | ID token signed JWS, có thể encrypted theo OIDC contract | Client verify issuer, client audience, nonce/exp khi profile cần |
| **AS → RS qua client** | Signed JWT AT hoặc encrypted/JWE AT; opaque token | RS verify JWT hoặc introspect opaque, aud/scope/type |
| **Client → AS token endpoint** | `private_key_jwt`/HMAC client assertion | AS authenticate client theo registration, aud/exp/jti |
| **Client → RS** | Bearer token qua TLS; DPoP proof ký bằng client key khi áp dụng | RS validate token + sender binding + rights |
| **RS → AS introspection** | HTTPS/mTLS/Basic/JWT client auth | AS xác thực caller, authorize disclosure, trả active |
| **Storage tại client/RS** | Disk/DB encryption, KMS envelope encryption | ACL, TTL, rotation, CSRF/XSS threats, revoke |

**Token được ký hoặc mã hóa chỉ là một mắt xích trong mô hình tin cậy.** Ví dụ JWT có chữ ký đúng nhưng `aud=payments-api` phải bị Orders API từ chối. Một JWE decrypt thành công cũng phải chịu kiểm tra tương tự.

### 9.1. JWT không bắt buộc là signed access token

OAuth 2.0 cho phép access token có dạng opaque hoặc cấu trúc riêng theo issuer. **Không mặc định mỗi chuỗi có ba đoạn là access token JWT hợp lệ**, và cũng không mặc định token opaque yếu hơn. Opaque token có thể cho AS kiểm soát trạng thái qua introspection, nhưng vẫn phải bảo vệ bearer token khỏi bị sao chép.

### 9.2. Refresh token không phải JWT bắt buộc

Refresh token thường là opaque credential lưu ở client để xin access token mới. Nó cũng có thể có cấu trúc khác theo AS, nhưng **không được đưa refresh token vào Orders API** như access token. Signing hoặc encrypting refresh token không thay authorization, client binding, rotation/reuse detection và revocation.

### 9.3. Signing không làm token chống replay

Bearer JWT có thể được gửi lại nhiều request hợp lệ. Nếu bị đánh cắp, attacker cũng có thể gửi lại nguyên token đó. Muốn giảm replay, cần secure transport/storage, TTL/revocation, hoặc sender-constrained tokens (DPoP/mTLS) và đánh giá rủi ro.

## 10. Mối quan hệ giữa TLS, JWS, JWE và mã hóa dữ liệu lưu trữ

**TLS**, **JWS** và **JWE** không phải ba tên gọi khác nhau của cùng một cơ chế:

| Cơ chế | Ranh giới bảo vệ | Có bảo vệ token khi bị sao chép? |
| --- | --- | --- |
| **HTTPS/TLS** | Dữ liệu **trên một kênh kết nối** giữa hai endpoint TLS | Giúp chống nghe lén trên kênh, **không chặn replay** nếu token bị lấy ở endpoint/log |
| **JWS signature** | Header/payload được ký, **bất kể đi qua bao nhiêu hop** | Chống sửa nội dung nhưng **không chặn token copy** |
| **JWE encryption** | Confidentiality của payload tới bên nắm decryption key | Không ngăn người có bản sao JWE gửi lại nếu RS chấp nhận |
| **Encryption at rest** | Dữ liệu ở disk/DB/backups theo vị trí khóa | Không ngăn process hợp lệ hoặc attacker có quyền decrypt lạm dụng |
| **DPoP/mTLS-bound AT** | Token được ràng buộc với sender key/certificate | Giảm token-only replay nếu RS verify proof đúng |

### 10.1. TLS là hop-by-hop ở các điểm termination

Một request:

~~~text
Browser --HTTPS--> CDN/Gateway --mTLS--> BFF --TLS--> API
~~~

Mỗi hop có thể được bảo vệ bằng TLS, nhưng **CDN/Gateway/BFF tại điểm TLS termination có thể đọc Bearer token**. JWS không che token khỏi proxy; JWE có thể giấu payload khỏi các intermediaries không có decryption key, nhưng **chuỗi ciphertext JWE vẫn là một credential** nếu API chấp nhận nó.

### 10.2. Khi nào JWE đáng dùng?

JWE hữu ích khi:

- Payload JWT có thông tin cần được **giấu khỏi các bên trung gian** hoặc client không được đọc;
- Token được chuyển qua nhiều hop không cùng mức tin cậy;
- Một profile OIDC/API yêu cầu encrypted token;
- Có yêu cầu bảo vệ claims **end-to-end tới recipient** ngoài TLS hop-by-hop.

Tuy nhiên, nên đánh giá:

- Ai giữ private decryption key? Nếu mỗi RS cần giải mã, quản lý và rotation keys thế nào?
- Các services/observability có bị mất khả năng định tuyến hoặc debug hợp lệ không?
- Có tăng kích thước header/cookie và latency đáng kể không?
- Nếu chỉ cần một opaque token chứa random ID, liệu introspection có phù hợp hơn không?
- Có thật sự cần nhúng thông tin nhạy cảm vào token, hay có thể **không đưa thông tin ấy vào token**?

**Không mã hóa quá mức để che một thiết kế cấp quyền sai.** Loại bỏ PII không cần thiết khỏi claims thường tốt hơn việc mã hóa tất cả rồi chia khóa giải mã rộng khắp.

### 10.3. Encrypted storage khác encrypted token format

Một refresh token có thể là **opaque string** nhưng được ứng dụng lưu trong database qua **AES-GCM encryption at rest**. Khi gửi tới AS, nó vẫn là opaque refresh token, không tự trở thành JWE. Ngược lại, một JWE có thể vẫn được lưu trong logs sai cách và bị replay khi API chấp nhận nó.

## 11. Chữ ký, MAC và xác thực nguồn: ai thực sự được tin?

Chữ ký không tự chứng minh danh tính pháp lý. **Trust chain** cần tối thiểu:

1. RS có cấu hình issuer tin cậy, ví dụ `https://auth.example.com`.
2. Public verification keys đến từ **JWKS của issuer đã tin**, không phải JWT header tùy ý.
3. `kid`, `alg` được đối chiếu theo **key set và algorithm policy của issuer**.
4. Signed bytes và signature được kiểm đúng JOSE.
5. Claims `iss`, `aud`, `exp`, token type và policy được xét tiếp.

### 11.1. Ví dụ key substitution

Attacker tạo RSA key pair của chính mình, ký JWT chứa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "admin",
  "aud": "orders-api",
  "scope": "orders.delete"
}
~~~

Nếu RS **tải public key từ `jku` do JWT attacker đưa vào** và verify thành công rồi coi `iss` là tin cậy, attacker đã đánh tráo **nguồn khóa**. Chữ ký vẫn đúng về mặt số học, nhưng **khóa thuộc attacker**, không thuộc AS.

**Bài học:** Verify thành công chỉ có ý nghĩa khi **public key và issuer được ràng buộc bằng trust policy độc lập với dữ liệu chưa xác minh**.

### 11.2. HMAC HS256 và key-confusion attack

Một lỗi cổ điển là hệ thống dự kiến RS256 (public key verify) nhưng cho attacker đổi header sang HS256, rồi **dùng public RSA key bytes làm HMAC secret**. Vì public key không bí mật, attacker có thể tạo MAC tương ứng. **Không cho thuật toán tự chọn theo header**, và không dùng key material sai loại.

Các thư viện JOSE hiện đại có kiểm soát key type, nhưng **integration/config vẫn phải khóa danh sách algorithms theo issuer và token profile**.

### 11.3. `alg=none` và unsecured JWT

Một JWT có `alg=none` không cung cấp signature authentication. Nếu API yêu cầu signed JWT access token, phải **từ chối** unsecured token. Không “fallback” để chấp nhận token nếu verify thất bại vì JWKS outage hoặc rotation.

### 11.4. Một token được ký bởi issuer A không có quyền ở issuer B

Khi RS hỗ trợ nhiều issuers, token của issuer A có thể hợp lệ theo khóa A nhưng không có quyền truy cập resource B. **Phải chọn đúng trust domain trước khi tin claims và scope**. Không dùng chung một map `kid` giữa các issuers; `kid` không được bảo đảm duy nhất toàn cầu.

## 12. JWE trust: ai được giải mã và ai được phép tạo JWE?

Giả sử RS công bố public encryption key. **Bất kỳ bên nào biết key có thể mã hóa một plaintext cho RS**. Nếu RS chỉ giải mã rồi cho truy cập dựa trên:

~~~json
{"sub":"admin","scope":"orders.write"}
~~~

thì đó là một thiết kế **thiếu xác thực nguồn phát hành**. Encryption không thay signing; RS phải có **issuer-authenticated claims**, ví dụ inner JWS được AS ký hoặc một cơ chế trusted issuance/authentication theo profile.

### 12.1. JWE với `alg=dir`

Trong chế độ `dir`, **CEK được sử dụng trực tiếp làm symmetric key** do sender và recipient đã chia sẻ theo contract. JWE Compact có **encrypted-key segment rỗng**, nhưng nội dung vẫn có thể được mã hóa/xác thực bằng `enc`.

Vì cả AS và RS cùng biết secret, RS có thể mã hóa một message dùng shared key ấy; không nên xem mã hóa `dir` là chữ ký chứng minh **chỉ riêng AS** đã phát token nếu không có trust boundary khác.

### 12.2. JWE protected header không bí mật

JWE header ở dạng Base64url và có thể được đọc trước khi decrypt; nó chứa thông tin như `alg`, `enc`, `kid` hoặc `cty`. **Không đặt password, bearer secret hoặc PII nhạy cảm trong protected/unprotected header** rồi tin rằng mã hóa JWE che giấu chúng.

### 12.3. Authentication tag không chứng minh issuer

AEAD tag xác thực rằng ciphertext/AAD không bị sửa **theo khóa mã hóa tương ứng**. Với asymmetric encryption cho recipient public key, người gửi khác vẫn có thể tạo ciphertext/tag hợp lệ cho một plaintext do họ chọn. Do đó cần **issuer binding** độc lập nếu plaintext là access-token claims.

### 12.4. Tránh compression oracle và zip bombs

Nếu hệ thống cho phép JWE compression `zip`, việc nén thông tin nhạy cảm trộn với attacker-controlled plaintext có thể tạo rủi ro **length oracle**, và decompression không giới hạn có thể thành **resource exhaustion**. Chỉ cho compression theo profile đã đánh giá và giới hạn kích thước/độ sâu sau decompress.

### 12.5. JWE algorithm/key confusion

Một JWE `alg` chỉ định key management; `enc` chỉ định content encryption. RS cần **allowlist cả hai**, key type/strength, ECDH curve/parameter validation và được phép dùng đúng decryption key. Không thử ngẫu nhiên tất cả khóa/private keys rồi chấp nhận cái đầu tiên decrypt được; hành vi đó có thể tạo oracle và lỗi key separation.

## 13. Java 17: ký và xác minh bằng RSA-PSS

Ví dụ sử dụng **Java 17 standard JCA** để minh họa signing/verification bằng **RSASSA-PSS với SHA-256**. Đây **không phải** JWS Compact Serializer: nó ký trực tiếp bytes của một message do ứng dụng tạo.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Base64;

public final class SigningVsEncryptionSignatureDemo {
    private static final PSSParameterSpec PSS_SHA256 =
        new PSSParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            32, 1
        );

    private SigningVsEncryptionSignatureDemo() {}

    static byte[] sign(byte[] message, PrivateKey issuerPrivate)
            throws Exception {
        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(PSS_SHA256);
        signer.initSign(issuerPrivate);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(
            byte[] message,
            byte[] signature,
            PublicKey trustedIssuerPublic) throws Exception {
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(PSS_SHA256);
        verifier.initVerify(trustedIssuerPublic);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        // Test/demo only: production key nằm ở KMS/HSM/keystore.
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(3072);
        KeyPair issuerKey = gen.generateKeyPair();

        byte[] message = "scope=orders.read"
            .getBytes(StandardCharsets.UTF_8);
        byte[] signed = sign(message, issuerKey.getPrivate());

        System.out.println("Signature Base64url length: "
            + Base64.getUrlEncoder().withoutPadding()
                .encodeToString(signed).length());
        System.out.println("Correct message: "
            + verify(message, signed, issuerKey.getPublic()));

        byte[] tampered = "scope=orders.write"
            .getBytes(StandardCharsets.UTF_8);
        System.out.println("Modified message: "
            + verify(tampered, signed, issuerKey.getPublic()));
    }
}
~~~

Kỳ vọng: message gốc verify **`true`**, message bị sửa đổi verify **`false`**. Bản gốc và message đã thay đổi **đều có thể đọc được** vì ở đây **không có bước encryption**.

### 13.1. Cần hiểu đúng liên hệ với `PS256`

JWS `PS256` sử dụng RSA-PSS với SHA-256 và các quy tắc JOSE tương ứng. Ví dụ đặt SHA-256, MGF1 SHA-256, salt 32 bytes để minh họa scheme. Tuy nhiên **thực hiện một JWS thực** cần đúng **JWS signing input**, header serialization/Base64url, key trust, `typ` và JWT validation theo RFC. Dùng **JOSE library** thay vì tự ghép bytes trong ứng dụng production.

### 13.2. Đừng phát private signing key cho RS

Trong ví dụ, cả hai thao tác chạy trong một process để học. **Kiến trúc thật:** chỉ AS/KMS signer giữ private key, RS verify bằng **public key thuộc issuer đã tin**. Không đưa `issuerKey.getPrivate()` vào cấu hình của mọi microservice để “xác minh nhanh”.

### 13.3. Signature verification không cần nội dung mã hóa

Nhìn vào `message` trước verify không có vấn đề gì về thuật toán; mục đích verify là xác định liệu message có bị sửa và signature có thuộc khóa đã tin. Nếu message có bí mật thì **phải áp confidentiality layer riêng**.

## 14. Java 17: mã hóa/xác thực bằng AES-GCM

Ví dụ sử dụng **AES-256-GCM** để mã hóa một plaintext và xác thực associated data (AAD). Secret key được tạo bằng `KeyGenerator` và IV dài 12 bytes từ `SecureRandom`. Đây là **mẫu nguyên lý AEAD**, không phải JWE serializer.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmExample {
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record Encrypted(
        byte[] iv,
        byte[] ciphertextAndTag
    ) {}

    private AesGcmExample() {}

    static Encrypted encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad) throws Exception {
        byte[] iv = new byte[IV_BYTES];
        RANDOM.nextBytes(iv); // IV mới cho mỗi encryption với cùng key.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_BITS, iv)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new Encrypted(iv, ciphertextAndTag);
    }

    static byte[] decrypt(
            SecretKey key,
            Encrypted encrypted,
            byte[] aad) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_BITS, encrypted.iv())
        );
        cipher.updateAAD(aad);
        // doFinal sẽ throw khi tag/ciphertext/AAD bị sửa.
        return cipher.doFinal(encrypted.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // Test/demo only; dùng key manager trong production.
        KeyGenerator keyGen = KeyGenerator.getInstance("AES");
        keyGen.init(256);
        SecretKey key = keyGen.generateKey();

        byte[] plaintext = "User email: user@example.com"
            .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "resource=orders;version=1"
            .getBytes(StandardCharsets.UTF_8);
        Encrypted encrypted = encrypt(key, plaintext, aad);

        byte[] restored = decrypt(key, encrypted, aad);
        System.out.println("Correct plaintext: "
            + Arrays.equals(plaintext, restored));

        byte[] tampered = encrypted.ciphertextAndTag().clone();
        tampered[0] ^= 1;
        try {
            decrypt(key, new Encrypted(encrypted.iv(), tampered), aad);
            throw new AssertionError("Tampering was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Ciphertext tampering rejected");
        }
    }
}
~~~

**Kỳ vọng:** plaintext giải mã bằng đúng key/IV/AAD cho kết quả ban đầu; ciphertext bị sửa sẽ bị từ chối vì **authentication tag verification** thất bại. Không in plaintext/ciphertext/khóa trong logs ngoài môi trường test minh họa.

### 14.1. IV reuse là lỗi nghiêm trọng

**Không bao giờ dùng lại cùng cặp (AES-GCM key, nonce/IV)**. Sử dụng IV 96-bit sinh ngẫu nhiên là một cách phù hợp trong nhiều hệ thống khi kiểm soát **lượng bản mã dưới mỗi key** và tuân giới hạn an toàn; với hệ thống lưu lượng rất lớn hoặc phân tán, cần chiến lược nonce uniqueness/key rotation được security review. **Không dùng thời gian Unix đơn độc làm IV**.

### 14.2. Tại sao AAD xuất hiện mà không được mã hóa?

AAD cho phép **ràng buộc metadata cần được bảo vệ toàn vẹn** với ciphertext mà không làm metadata ấy bí mật. Nếu bên decrypt cung cấp AAD khác, tag validation thất bại. Trong JWE, protected header được bảo vệ bằng authenticated encryption dưới dạng AAD; **điều đó không khiến protected header trở thành ciphertext**.

### 14.3. AES-GCM là symmetric authenticated encryption, không phải JWS issuer signature

Ai giữ secret AES key có thể mã hóa ciphertext/tag hợp lệ, không chứng minh riêng AS đã phát claims. Nếu hệ thống có nhiều services cùng biết AES key, **không thể quy trách nhiệm một issuer duy nhất** chỉ từ GCM tag. Với OAuth access-token claims cần xác minh nguồn issuer, hãy dùng JWS hoặc một issuer authentication profile được định nghĩa rõ.

### 14.4. Thư viện/token thực tế cần quản lý nhiều thứ hơn

Ví dụ trên không thực hiện:

- Key wrapping/KMS/envelope encryption cho nhiều recipients;
- JWE compact serialization, `alg`/`enc` mapping và JOSE headers;
- Key rotation/KID, key separation và policy trust;
- Nonce-state accounting toàn hệ thống;
- Replay protection, token expiry/revocation hoặc business authorization.

Nếu nhiệm vụ là **phát JWT/JWE**, dùng library JOSE phù hợp thay vì coi `Encrypted` Java record thành token chuẩn.

## 15. RSA-OAEP và encryption key wrapping

Trong **JWE hybrid encryption**, một cơ chế như `RSA-OAEP-256` có thể bảo vệ CEK bằng **public encryption key của RS**, rồi AES-GCM mã hóa payload. Điều này khác hoàn toàn với **RSA-PSS signing**.

Một JCA minh họa cách bọc **một CEK ngắn** bằng RSA-OAEP với SHA-256:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class RsaOaepKeyWrapDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator pairGen = KeyPairGenerator.getInstance("RSA");
        pairGen.initialize(3072);
        KeyPair recipient = pairGen.generateKeyPair();

        KeyGenerator aesGen = KeyGenerator.getInstance("AES");
        aesGen.init(256);
        SecretKey cek = aesGen.generateKey();

        OAEPParameterSpec spec = new OAEPParameterSpec(
            "SHA-256",
            "MGF1",
            MGF1ParameterSpec.SHA256,
            PSource.PSpecified.DEFAULT
        );

        Cipher wrapping = Cipher.getInstance("RSA/ECB/OAEPPadding");
        wrapping.init(Cipher.ENCRYPT_MODE, recipient.getPublic(), spec);
        byte[] encryptedCek = wrapping.doFinal(cek.getEncoded());

        Cipher unwrapping = Cipher.getInstance("RSA/ECB/OAEPPadding");
        unwrapping.init(
            Cipher.DECRYPT_MODE, recipient.getPrivate(), spec);
        byte[] restoredCek = unwrapping.doFinal(encryptedCek);

        System.out.println("CEK recovered: "
            + Arrays.equals(cek.getEncoded(), restoredCek));
    }
}
~~~

**Giới hạn:** đây chỉ là một phần *key management* của hybrid encryption; chưa sinh AES-GCM ciphertext/tag, chưa tạo JWE headers, chưa ràng buộc issuer/token. Trong production, private encryption key phải được bảo vệ bởi HSM/keystore và JOSE library xử lý đúng `RSA-OAEP-256` theo spec.

### 15.1. Không coi RSA-OAEP là digital signature

Các bytes sau `wrapping.doFinal()` là **encrypted key**, không phải signature. Bất kỳ ai biết `recipient.getPublic()` có thể tạo encrypted CEK mới; chỉ người giữ private decryption key có thể khôi phục CEK.

### 15.2. Vì sao không mã hóa toàn bộ payload bằng RSA?

RSA-OAEP giới hạn kích thước plaintext và tốn tài nguyên hơn symmetric encryption. Hybrid encryption dùng RSA/ECDH để bảo vệ **khóa phiên nhỏ**, AES-GCM để bảo vệ **nội dung lớn**. Đó là vai trò `alg` vs `enc` trong JWE.

## 16. `alg`, `enc`, `kid`, `typ`, `cty`: đọc JOSE header đúng cách

| Header field | Ngữ cảnh | Ý nghĩa | Cạm bẫy |
| --- | --- | --- | --- |
| **`alg` trong JWS** | Signed JWT | Thuật toán signature/MAC | Đừng tin giá trị header để tự đổi allowlist |
| **`alg` trong JWE** | Encrypted JWT | Key management/CEK agreement | Không phải JWS signing alg |
| **`enc`** | JWE | Content encryption algorithm | Phải allowlist với `alg` |
| **`kid`** | JWS/JWE | Key identifier để chọn khóa được tin | Không có tính duy nhất toàn cục, không tự tạo trust |
| **`typ`** | JOSE object | Loại token theo profile, ví dụ `at+jwt` | Tránh cross-JWT/token substitution |
| **`cty`** | Nested content | Kiểu payload bên trong, ví dụ `JWT` | Không thay verify inner JWS |
| **`crit`** | JOSE header | Critical extensions phải hiểu/xử lý | Không bỏ qua extension lạ rồi tiếp tục xử lý |
| **`jku`/`x5u`** | Header metadata | URL liên quan key/certificate | Không tải URL tùy ý từ token chưa verify |
| **`zip`** | JWE | Compression option | Có rủi ro oracle/DoS nếu dùng không kiểm soát |

**Cách phòng lỗi chung:** mỗi token profile có **issuer, recipient/resource, allowed alg/enc, key set, token type, claims policy** độc lập. Không dùng “một JWT parser chung” rồi tự xác định loại token dựa trên chuỗi payload sau khi đã tin quyền.

### 16.1. Cross-JWT confusion: token đúng chữ ký, sai mục đích

Một hệ thống có:

- **ID token**: `aud=oidc-client-id`, kết quả user authentication;
- **Access token**: `aud=orders-api`, `scope=orders.read`;
- **JWT client assertion**: `iss=sub=client_id`, `aud=token-endpoint`;
- **DPoP proof JWT**: `htm`, `htu`, `jti`, `ath` và public key;
- **Refresh token**: không dùng tại RS như access token.

Nếu API chỉ verify “chữ ký thuộc AS” rồi cho phép truy cập, nó có thể nhận nhầm **ID token làm access token** hoặc JWT assertion làm resource credential. Phải **explicitly type-check** theo profile (ví dụ RFC 9068 và RFC 8725) và validate đúng audience.

### 16.2. Algorithm allowlist là cấu hình trust

Nếu issuer A sử dụng `RS256` cho access token, RS không được tự động chấp nhận `HS256`, `ES256`, `none` khi token đưa header khác. Khi rotate RSA key, thường thay **key trong tập allowed algorithm**, không mở toàn bộ supported algorithms của thư viện.

### 16.3. Key use/key operations cần khớp mục đích

JWK metadata `use=sig` hoặc `use=enc`, `key_ops` và key type là tín hiệu chính sách; phải kiểm cùng registry đáng tin. Một public encryption key được đăng ký cho JWE **không nên được lựa chọn để verify JWS** chỉ vì `kid` trùng.

## 17. Chọn signing hay encryption theo dữ liệu và threat model

| Nhu cầu | Cơ chế thường cần | Vì sao |
| --- | --- | --- |
| RS kiểm JWT do AS cấp, payload không chứa bí mật | JWS + TLS | Xác thực nguồn/toàn vẹn, truyền an toàn |
| Giấu claims khỏi bên trung gian nhưng RS vẫn cần issuer signature | Nested JWS trong JWE + TLS | Confidentiality tới recipient và verify inner signature |
| Giữ refresh token trong database | Mã hóa at rest/secret management + TTL/revoke | Token là credential nhạy cảm, không mặc định cần JWE |
| Client gửi access token qua mạng | HTTPS + token storage protection | Ngăn nghe lén trong transport; signing không đủ |
| Token bị sao chép từ logs | Redaction, revocation, TTL, sender constraint | Ký/mã hóa payload không loại bỏ khả năng replay token |
| Bảo vệ PII không cần phát tới client | Giảm claims hoặc opaque AT + AS lookup | Data minimization mạnh hơn “encrypt mọi thứ” |
| Nonrepudiation/audit trên dữ liệu nghiệp vụ | Digital signature + PKI/identity/audit theo yêu cầu | Không suy từ HMAC chia sẻ khóa |
| Xác thực message giữa hai services biết shared secret | HMAC/AEAD theo protocol | Chỉ có ý nghĩa nếu secret/key domain được kiểm soát |

### 17.1. Không mã hóa “để chống tăng scope”

Nếu token JWS đã verify signature và claims chính xác, attacker **không thể sửa scope mà giữ chữ ký hợp lệ**. Mã hóa thêm thường **không giúp chống sửa scope** bằng một thuộc tính mới, nhưng có thể giấu scope/claims khỏi người không được phép đọc. **Tăng scope trái phép** thường xuất phát từ token-validation bug, key confusion hoặc authorization bug, không phải vì thiếu JWE.

### 17.2. Không ký “để che email”

Email trong JWS payload có thể bị đọc; nếu không muốn tiết lộ, hãy **không đưa email vào token**, dùng opaque token hoặc mã hóa cho đúng recipient theo policy. Giữ PII trong JWT với tuổi thọ dài còn tạo rủi ro khi token bị sao chép/log.

### 17.3. Đánh giá performance và vận hành

Signing/verification bất đối xứng, decryption RSA/ECDH và symmetric AES-GCM có chi phí khác nhau. Nhưng **không nên chọn HS256 chỉ vì nhanh hơn RS256** nếu điều đó buộc chia signing secret tới mọi microservice. Key distribution/trust, blast radius và security requirements quan trọng hơn micro-benchmark đơn lẻ.

## 18. Key management: nơi giữ khóa quan trọng hơn tên thuật toán

Một chữ ký rất mạnh vẫn trở nên vô nghĩa nếu private signing key bị sao chép từ container image hoặc được gắn trong Git repository. Tương tự, JWE khó bảo vệ payload nếu private decryption key được phân phối tràn lan cho mọi component.

| Key/credential | Nơi lưu phù hợp | Quyền cần hạn chế | Rủi ro khi lộ |
| --- | --- | --- | --- |
| Private JWS signing key của issuer | KMS/HSM/keystore có ACL và audit | **Sign**, rotate, disable | Attacker có thể phát JWT có chữ ký hợp lệ |
| Public JWS verification key | Trusted issuer JWKS | Chỉ được dùng để **verify** theo issuer/alg | Public key không phải secret; **key-trust injection** mới nguy hiểm |
| Private JWE decryption key của RS | KMS/HSM/keystore bảo vệ tại recipient | **Decrypt/unwrap**, rotate | Claims ciphertext cũ và mới có thể bị giải mã |
| Public JWE encryption key của recipient | Registry/JWKS tin cậy | Encrypt/wrap theo recipient đúng | Public không phải bí mật; cần tránh key substitution |
| AES-GCM CEK | Memory phiên, wrapped/managed key material | Encrypt/decrypt nội dung liên quan | Attacker có thể decrypt và tạo ciphertext/tag |
| HS256/HMAC secret | Secret manager cho trust domain giới hạn | Generate/verify MAC theo policy | Bất kỳ bên giữ secret có thể làm giả MAC |
| DPoP client private key | Secure keystore phía client khi có | Sign proof đúng request | Token + key bị lộ có thể bị replay |
| mTLS private key | Certificate/PKI manager | TLS client authentication | Mạo danh sender nếu certificate còn tin |

### 18.1. Không gửi private signing key qua JWKS

JWKS dùng cho Resource Servers thường chứa **public verification keys** và metadata liên quan, không được xuất `d`, `p`, `q` hoặc các tham số private RSA/EC key ra Internet. Cần kiểm tra pipeline publish JWKS để không đưa private JWK lên endpoint public.

### 18.2. Khóa encryption không phải khóa signing

Cho cùng một tenant, nên phân biệt key IDs và key purposes:

~~~text
issuer-2026-11-sign-rs256   -> private sign tại AS, public verify tại RS
orders-2026-11-enc-oaep   -> public encrypt tại AS, private decrypt tại RS
storage-2026-11-aes-gcm   -> key tại KMS/storage envelope
~~~

Tên khóa chỉ là minh họa. **Đừng lấy public key để verify JWS rồi vì cùng `kid` mà dùng nó như encryption key** hoặc cho phép private JWE key ký token. Mọi key operation phải thuộc trust boundary đã thiết kế.

### 18.3. Rotation signing key có tác động gì?

~~~text
Thời điểm T1: JWT A ký với kid=issuer-old
Thời điểm T2: AS bắt đầu ký JWT B với kid=issuer-new
Thời điểm T3: RS tin cả old/new trong overlap có kiểm soát
Thời điểm T4: Sau expiry/token policy, RS ngừng tin old
~~~

**Đổi signing key không tự làm JWT cũ hết hiệu lực** nếu RS vẫn tin khóa cũ. Nếu old private key bị compromise, phải có **emergency trust withdrawal/denylist/cutover** và theo dõi JWKS caching. Không thể giả định xóa key khỏi JWKS sẽ vô hiệu ngay token ở mọi RS.

### 18.4. Rotation encryption key có tác động gì?

Nếu RS thay private decryption key và xóa key cũ **trước khi JWE đã phát hết hạn**, nó sẽ không decrypt được JWE cũ, trừ khi có cơ chế re-encryption/versioning. Rotation encryption key cần:

1. Đăng ký public encryption key mới với AS;
2. Bắt đầu encrypt token mới bằng key mới sau khi recipient sẵn sàng;
3. Giữ khả năng decrypt token cũ trong overlap theo TTL/security policy;
4. Thu hồi key cũ có kiểm soát, đặc biệt khi compromise;
5. Không cho phép “fallback decrypt bằng bất kỳ private key nào tìm được” mà thiếu recipient/key policy.

### 18.5. Key compromise không đồng nghĩa user đã revoke grant

Nếu **signing key bị lộ**, attacker có thể tạo token giả ngoài AS. Nếu **decryption key bị lộ**, attacker có thể đọc ciphertext nhưng chưa chắc tạo issuer signature. Nếu **HMAC secret bị lộ**, attacker có thể tạo MAC của token trong trust domain. Hướng ứng phó khác nhau: rút signing trust/rotate, đổi encryption key/re-encrypt khi cần, hoặc thay shared MAC secret và kiểm tra tokens đã cấp.

## 19. Spring Security: xác minh signed JWT access token

Với **Spring Boot 3 / Spring Security 6**, một Resource Server có thể xác minh signed JWT access token bằng issuer/JWKS đáng tin. Ví dụ cấu hình (các giá trị cụ thể phụ thuộc AS):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

Đây là cách khai báo nguồn issuer. **Không phải mọi validation theo nghiệp vụ đều tự có**: cần kiểm tra audience, token type/profile, scope/authority mapping, tenant và object authorization theo chính sách API.

### 19.1. Ví dụ cấu hình JWT decoder với audience validation

~~~java
import java.util.List;
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

final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {
    private static final String ORDERS_AUDIENCE =
        "https://api.example.com/orders";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audience = jwt.getAudience();
        if (audience != null && audience.contains(ORDERS_AUDIENCE)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));
    }
}

@Configuration
public class OrdersJwtSecurityConfiguration {
    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/oauth2/jwks")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                    "https://auth.example.com"),
                new OrdersAudienceValidator()
            )
        );
        return decoder;
    }
}
~~~

Mẫu code này cố ý **giới hạn thuật toán ký được cho phép** và kiểm **issuer/audience**. Nếu AS dùng PS256/ES256 thay vì RS256, cấu hình phải đổi đúng theo **issuer policy**; không nhận mọi thuật toán vì thư viện hỗ trợ.

**Cần bổ sung theo profile:** type header `at+jwt` (RFC 9068), đúng principal/grant type, `scope`, `exp`/`nbf`, tenant/ownership và revocation. JWKS URL phải lấy từ **trusted issuer configuration**, không từ unverified token header.

### 19.2. Phân quyền tuyến API vẫn cần thiết

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersRoutesSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**`SCOPE_orders.read`** là authority mapping thường dùng bởi Spring Security khi token response/claims phù hợp, nhưng mapping có thể cần cấu hình theo AS. Không sử dụng display text “Xem đơn hàng” thay authority kỹ thuật. Mọi endpoint còn phải xác minh quyền **với đúng đối tượng dữ liệu**.

### 19.3. Spring Resource Server không tự decrypt JWE

Một **JWT decoder** thông thường dành cho signed JWS JWT **không nên được giả định hỗ trợ JWE Compact**. Nếu issuer gửi **encrypted JWT**, phải có một tầng **trusted JOSE decryption** và **verify inner signature/type/claims** theo profile, tích hợp decoder/validator cụ thể và kiểm thử thư viện. Không “Base64url-decode JWE” như JWS hoặc tự bỏ tag verification.

### 19.4. Signed JWT offline và revocation

Spring JWT decoder có thể xác minh chữ ký/issuer/expiry ngoại tuyến qua JWKS; nếu admin vừa thu hồi user/session/grant, JWT cũ vẫn có thể pass trừ khi RS kiểm tra **denylist, session/grant version, introspection hoặc online policy**. Đây là vấn đề trạng thái, không phải thiếu một thuật toán mã hóa.

## 20. Những sai lầm khiến cryptography bị dùng sai mục đích

### 20.1. “JWT có 3 phần trông khó đọc nên đã được encrypt”

**Sai.** JWS Compact chứa Base64url header/payload; decode được không cần khóa. Signature vẫn có thể hợp lệ nhưng payload không bí mật.

### 20.2. “Thêm chữ ký giúp giấu email/password trong token”

**Sai.** Chữ ký chỉ bảo vệ toàn vẹn/xác thực nguồn, không phải confidentiality. Không đưa password/secret vào claims; hạn chế PII hoặc dùng JWE/opaque token khi thực sự cần.

### 20.3. “JWE decrypt được nên AS chắc chắn đã phát”

**Sai nếu chỉ dùng recipient public key encryption.** Người bất kỳ có public key có thể tạo encrypted content. Phải kiểm issuer-authenticated proof, ví dụ inner JWS signature với key issuer.

### 20.4. “AES-GCM encrypt xong không cần kiểm tag”

**Sai.** Nếu không verify authentication tag, không thể tin plaintext. Ciphertext/AAD bị chỉnh sửa phải làm decrypt thất bại.

### 20.5. “Cùng AES key và nonce vẫn an toàn vì payload khác”

**Sai nghiêm trọng.** AES-GCM key/nonce reuse có thể phá bảo mật; phải có nonce uniqueness strategy.

### 20.6. “HMAC secret có thể public như RSA verification key”

**Sai.** Nếu secret HS256 lộ cho attacker, họ có thể tạo MAC/token giả. Public JWS verification key không cho phép ký bằng khóa issuer tương ứng.

### 20.7. “RSA signing là private-key encryption”

**Sai.** Digital signature schemes (RSASSA-PSS/RS256) và encryption schemes (RSA-OAEP) có mục đích/API/padding/security properties khác nhau.

### 20.8. “`kid` trong JWT quyết định public key nào cũng được tin”

**Sai.** Key phải nằm trong **trust registry của issuer đã xác minh** và algorithm/profile được cho phép; header không thể tự mở quyền truy cập JWKS của attacker.

### 20.9. “Thấy `alg` nào thì thư viện hỗ trợ alg đó”

**Sai.** Thuật toán được chọn theo policy cho issuer/token type, không theo header do attacker điều khiển. Từ chối `none` và cross-algorithm confusion.

### 20.10. “JWT signature hợp lệ thì Orders API được quyền”

**Sai.** Token có thể dành cho Payments API, thiếu `scope`, hết session/revoke hoặc user không có quyền trên order/tenant.

### 20.11. “Encrypt token qua JWE sẽ ngăn attacker dùng bản sao token”

**Sai.** Nếu JWE vẫn được nhận như một Bearer credential, người giữ ciphertext có thể trình nguyên token. Cần TLS/redaction, TTL/revocation và sender constraint nếu rủi ro đòi hỏi.

### 20.12. “TLS có nên JWS/JWE là thừa”

**Không luôn đúng.** TLS bảo vệ từng kết nối; JWS bảo vệ toàn vẹn token qua nhiều hops và chứng minh issuer. JWE có thể giấu claims khỏi trung gian. Việc kết hợp phụ thuộc trust boundaries.

### 20.13. “`alg=dir` nghĩa là không mã hóa”

**Sai.** Trong JWE, `dir` nói CEK là khóa symmetric dùng trực tiếp; payload vẫn được mã hóa theo `enc`, và encrypted-key segment có thể rỗng.

### 20.14. “Chỉ cần AES-CBC encrypt; hash ciphertext đủ chống sửa”

**Sai** nếu hash không có khóa và mode thiếu integrity. Ưu tiên AEAD hoặc construction đã được đánh giá, không tự sáng tạo encrypt-then-checksum.

### 20.15. “Đổi signing key sẽ revoke mọi token cũ ngay”

**Sai.** RS có thể vẫn cache public key cũ. Signing-key rotation, revocation và JWKS trust update phải có runbook khác nhau.

### 20.16. “JWE payload không xem được nên có thể bỏ kiểm JWT type”

**Sai.** JWE có thể chứa ID token, access token, assertion hoặc data bất kỳ. Decrypt xong vẫn cần xác minh token type, issuer, audience/expiry/scope.

### 20.17. “DPoP proof ký đúng thì access token có thể chưa cần verify”

**Sai.** DPoP proof xác minh sender/HTTP request binding, không thay validation của access token, grant, scope/tenant hoặc revocation.

## 21. Ví dụ lỗi token substitution giữa OAuth 2.0 và OIDC

Giả sử OP phát một **ID token JWS**:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "reports-web",
  "exp": 1800000900
}
~~~

Nếu Orders API chỉ:

~~~text
verifySignature(token, issuerPublicKey) == true
~~~

thì ID token có thể vượt qua phép verify signature. Nhưng **ID token không phải access token dành cho Orders API** và `aud=reports-web` khác `aud=orders-api`.

**Điều đúng cần kiểm:**

~~~text
1. JWT signature và algorithm policy hợp lệ.
2. Issuer chính xác.
3. Token type/profile được cho phép cho API.
4. Audience là Orders API.
5. exp/nbf/clock policy.
6. Access token có scope cần thiết.
7. User/service principal có quyền tenant/object.
8. Revocation/sender binding theo policy.
~~~

**Không có bước “giải mã token” nào tự sửa được lỗi type confusion này.** Vấn đề là token validation và authorization, không phải confidentiality.

## 22. Chống replay: ký và mã hóa chưa đủ

Một Bearer token đã ký:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid-signed-jwt>
~~~

có thể được gửi nhiều lần **hợp lệ**. Nếu attacker lấy được chuỗi token từ logs hoặc device memory, họ có thể gửi **đúng bytes ấy** cho đến khi token hết hạn hoặc bị revoke. Nếu token là JWE, attacker cũng có thể gửi **đúng ciphertext/JWE compact string** mà không cần biết payload.

### 22.1. Phòng chống theo nhiều lớp

- **HTTPS/TLS:** không để token lộ khi truyền giữa các hops.
- **Storage protection:** tránh XSS, log leakage, local storage không phù hợp, secrets trong URL.
- **Short-lived access token:** giảm cửa sổ mất token.
- **Refresh token rotation/sender constraint:** phát hiện reuse của rotated refresh token hoặc giới hạn attacker.
- **DPoP/mTLS-bound access token:** yêu cầu sender proof/certificate tương ứng ở RS.
- **Revocation/denylist/introspection:** chặn token sau sự kiện compromise theo SLA.
- **Authorization checks:** scope, audience, tenant, owner ở mọi request.
- **Telemetry:** phát hiện patterns bất thường mà không log token plaintext.

### 22.2. Phân biệt `jti` của access token và DPoP proof

`jti` trong JWT access token thường giúp nhận diện token/denylist; **không làm access token thành one-time credential**. `jti` trong DPoP proof cần được kiểm tra chống replay trong cửa sổ theo RFC 9449. **Hai ngữ nghĩa khác nhau**, dù cùng tên claim.

### 22.3. Refresh token reuse không thể giải quyết bằng “ký refresh token”

Rotated refresh token cũ khi bị gửi lại cần được AS nhận diện là **reuse** và xử lý family/revoke theo policy. Dù refresh token có chữ ký hoặc được mã hóa, AS vẫn cần quản lý **trạng thái rotation/consumption** để quyết định token nào còn có quyền đổi token mới.

## 23. Tình huống thực tế: cần ký, mã hóa hay cả hai?

**Tình huống A — Orders API nhận signed JWT với `scope=orders.read`.**

Resource Server kiểm chữ ký RS256 bằng public key của issuer; claims không chứa PII nhạy cảm, token chỉ đi qua HTTPS.

**Đánh giá:** JWS + TLS có thể phù hợp nếu đáp ứng threat model. RS vẫn kiểm issuer/audience/expiry/scope/tenant; JWE không phải điều kiện bắt buộc để token hợp lệ.

**Tình huống B — JWT chứa email, địa chỉ giao hàng và lịch sử mua sắm.**

Ứng dụng gửi token qua nhiều hệ thống giám sát hoặc lưu trong nơi dễ trích xuất.

**Đánh giá:** JWS **không che claims**. Ưu tiên **giảm claims** hoặc opaque token; chỉ cân nhắc JWE khi cần bảo vệ nội dung end-to-end tới đúng recipient. Không đưa thông tin không cần vào token ngay từ đầu.

**Tình huống C — API dùng Base64url-decode rồi tin `role=admin`.**

Attacker tự tạo `header.payload.signature` với payload `role=admin`, nhưng không có signature issuer hợp lệ.

**Đánh giá:** Decode không phải verify. RS phải xác minh signature/key/issuer và đúng token profile trước khi đọc claims làm authority.

**Tình huống D — API verify JWS hợp lệ nhưng thiếu audience check.**

Token được AS cấp cho Payments API, nhưng Orders API cũng cho phép vì `iss` và signature đúng.

**Đánh giá:** Lỗ hổng **token substitution/cross-resource**. Ký không thay `aud` validation.

**Tình huống E — RS decrypt được JWE do attacker tạo.**

Attacker dùng public encryption key của RS và tạo JWE chứa `sub=admin`, `scope=orders.delete`. RS decrypt thành công và tin plaintext.

**Đánh giá:** JWE confidentiality/integrity không tự chứng minh issuer. Cần inner signed JWT/issuer authentication theo profile và authorization.

**Tình huống F — Hai services cùng giữ HS256 secret.**

Service A chỉ cần verify, nhưng lại có shared MAC secret và có thể tạo JWT giả mạo issuer B.

**Đánh giá:** Trust boundary bị mở rộng. Cân nhắc asymmetric signing để RS chỉ có public verification keys; nếu dùng HS256 phải giới hạn secret domain và quyền.

**Tình huống G — Kẻ xấu sửa JWE ciphertext một byte.**

RS chạy AES-GCM decryption nhưng bắt `AEADBadTagException` rồi vẫn xử lý plaintext tạm.

**Đánh giá:** Bỏ qua tag là lỗi nghiêm trọng. Decryption thất bại phải từ chối toàn bộ message, không cho xử lý partial plaintext.

**Tình huống H — AES-GCM nonce bị tái sử dụng sau restart.**

Một service dùng counter IV reset về 0 khi app restart, cùng key được dùng lâu dài.

**Đánh giá:** Nonce reuse dưới cùng key có thể phá confidentiality/integrity. Cần thiết kế nonce uniqueness qua restart/multi-instance hoặc key lifecycle phù hợp; không dùng counter volatile mà không persist.

**Tình huống I — Một signing key bị lộ trong container image.**

Attacker lấy private key và phát JWT có signature hợp lệ cho tới khi RS ngừng tin key.

**Đánh giá:** Đây là **issuer signing-key compromise**, nghiêm trọng hơn lộ một access token. Thu hồi key/trust, thay khóa, rà soát tokens và propagation; không chỉ sửa JWT claims.

**Tình huống J — Một JWE decrypt key bị lộ.**

Attacker có bản sao các encrypted tokens được lưu trước đó.

**Đánh giá:** Payload đã mã hóa bằng key lộ có thể mất confidentiality. Cần rotate/thu hồi decryption key, đánh giá **backward exposure**; key rotation không xóa bản sao ciphertext attacker đã giữ.

**Tình huống K — Browser gửi ID token vào API.**

ID token có signature hợp lệ của OP nhưng `aud=browser-client`.

**Đánh giá:** RS phải từ chối vì **sai token purpose và audience**; signing và encryption đều không thay điều kiện OAuth.

**Tình huống L — Access token JWE bị sao chép từ log.**

Attacker không đọc được claims nhưng có thể gửi nguyên chuỗi JWE như Bearer token.

**Đánh giá:** Confidentiality của claims không ngăn replay. Cần redact logs, token TTL, revoke và sender constraint khi phù hợp.

**Tình huống M — JWKS endpoint được lấy từ `jku` trong JWT chưa verify.**

Attacker tự ký JWT bằng khóa họ nắm rồi trỏ `jku` đến JWKS của attacker.

**Đánh giá:** Key-trust injection/SSRF; RS chỉ nhận public keys từ registry/JWKS của issuer **đã cấu hình tin cậy**.

**Tình huống N — JWE và JWS dùng cùng một RSA key pair.**

AS và RS chia sẻ quyền truy cập private key vì muốn vừa ký vừa giải mã.

**Đánh giá:** Key separation bị vi phạm về mặt thiết kế, làm tăng blast radius. Nên tách issuer signing key và recipient decryption key; không cho RS có private signing key.

**Tình huống O — Chỉ xem `alg` và `kid` là cho phép vào hệ thống.**

Một token không có `aud`, `exp` hay scope phù hợp vẫn được cho truy cập vì thư viện báo signature đúng.

**Đánh giá:** JOSE verification và OAuth resource authorization là **hai lớp độc lập**; phải validate claims/profile và quyền tài nguyên.

**Tình huống P — AS rotate signing key, RS cache JWKS quá lâu.**

RS vẫn tin key cũ đã bị thu hồi vì compromise.

**Đánh giá:** Rotation không tự làm token invalid; cần chính sách JWKS cache, emergency trust withdrawal, revoke và khả năng cách ly RS stale.

## 24. Một quy trình quyết định trước khi chọn JWS hay JWE

Khi thiết kế một token mới, hãy lần lượt đặt câu hỏi:

~~~mermaid
flowchart TD
    A["Token dành cho ai? Xác định issuer, client, RS"] --> B{"RS cần kiểm nguồn issuer?\nCần toàn vẹn claims?"}
    B -->|Có| C["JWS/issuer authentication theo profile"]
    B -->|Không| D["Xem lại trust model và use case"]
    C --> E{"Có claims phải giữ bí mật\nngoài TLS hops?"}
    E -->|Không| F["Signed JWT + TLS hoặc opaque token"]
    E -->|Có| G["Giảm claims trước;\nnếu cần, nested JWS → JWE"]
    F --> H["Validate type, iss, aud,\ntime, scope và resource rights"]
    G --> H
    H --> I{"Lo token theft/replay/revoke?"}
    I -->|Có| J["Storage, TTL, DPoP/mTLS,\nrefresh rotation, revoke/introspect"]
    I -->|Không| K["Giám sát và risk review"]
~~~

**Chú ý:** nhánh “Không cần issuer signature” không có nghĩa “mã hóa là đủ” cho mọi loại token. Một opaque access token được RS introspect có thể dựa vào **AS state lookup** thay vì public-key signature; đó là một trust model khác, cần định nghĩa rõ.

### 24.1. Câu hỏi riêng cho hệ thống có nhiều recipients

- Token có thể được đọc bởi client không, hay chỉ dành cho RS?
- Nếu chỉ một RS có quyền đọc, **public encryption key** của RS được đăng ký ở đâu?
- Nếu có hai RS khác nhau, một JWE compact recipient hay multi-recipient JWE JSON Serialization có phù hợp profile không?
- AS phân quyền theo resource/audience thế nào khi token được mã hóa?
- Có cần thay key recipient và re-issue tokens khi một RS bị compromise?
- Ai có quyền đọc thông tin trong JWT khi troubleshoot? Có quy trình support không làm lộ secret không?

### 24.2. Câu hỏi riêng cho high-risk APIs

Một giao dịch hoàn tiền có thể cần **signed access token, encrypted storage, step-up authentication và online authorization**. JWE không tự giải quyết việc user bị mất role, còn JWS không tự biết revocation. **Đánh giá nhiều lớp thay vì tăng thuật toán mật mã để thay authorization**.

## 25. Kiểm thử signing và encryption theo nhiều tầng

| Test case | Kỳ vọng |
| --- | --- |
| JWS JWT do issuer đúng ký, payload không đổi | Signature verify thành công |
| Chỉ đổi `scope=orders.read` thành `orders.write` | Signature verify thất bại |
| Chỉ đổi `alg` từ RS256 sang HS256 | Từ chối algorithm/key mismatch |
| JWS `alg=none` | Từ chối unsigned AT |
| JWS ký bằng private key attacker | Từ chối vì public key không thuộc trusted issuer |
| JWT `jku` trỏ URL attacker | Không tải arbitrary JWKS, không tin key |
| Token issuer A nhưng key/claims issuer B | Từ chối cross-issuer |
| Trùng `kid` giữa hai issuers | Không chọn key sai trust domain |
| JWS thiếu `exp` khi profile yêu cầu | Từ chối |
| JWS đúng chữ ký nhưng sai `aud` | RS từ chối |
| ID token JWS gọi Orders API | RS từ chối sai purpose/audience |
| DPoP proof JWS được đưa thay access token | RS từ chối cross-token type |
| JWS payload chứa PII nhạy cảm | Security review yêu cầu giảm claims/JWE phù hợp |
| JWT compact Base64url-decode được | Không xem decode là verification/confidentiality |
| HS256 secret bị lộ tới RS không tin | Threat model báo token forgery risk |
| RSA-PSS signature đúng message | JCA verify true |
| RSA-PSS signature với message đã sửa | JCA verify false |
| RSA private key dùng làm Cipher thay Signature | Kiểm thử API usage thất bại |
| AES-GCM encrypt/decrypt đúng key/IV/AAD | Trả plaintext ban đầu |
| AES-GCM ciphertext thay một bit | Tag verification từ chối |
| AES-GCM tag thay đổi | Tag verification từ chối |
| AES-GCM AAD khác | Tag verification từ chối |
| AES-GCM wrong key | Tag verification từ chối |
| AES-GCM IV bị reuse với cùng key | Crypto/security test fail theo nonce policy |
| JWE `alg=RSA-OAEP-256`, `enc=A256GCM` đúng | Recipient decrypt theo trusted profile |
| JWE sai `enc` hoặc algorithm ngoài allowlist | Từ chối |
| JWE được mã hóa bởi attacker cho public key RS | Không coi là issuer-authenticated token |
| JWE protected header chứa thông tin nhạy cảm | Privacy/security review fail |
| JWE `alg=dir` với encrypted-key segment rỗng | Parser xử lý đúng profile, không mặc định token sai |
| JWE bị sửa ciphertext/tag/IV/AAD | Decrypt/verification thất bại |
| JWE `zip` payload phình to khi decompress | Giới hạn kích thước, từ chối |
| Nested JWT sign rồi encrypt | RS decrypt **và** verify inner JWS |
| Nested JWT decrypt đúng nhưng inner signature sai | RS từ chối |
| Nested JWT inner `aud` sai | RS từ chối |
| Nested JWT sai `cty`/token profile | Từ chối theo allowed nesting policy |
| Private encryption key RS bị lộ | Test incident key rotation/exposure handling |
| Signing key AS bị lộ | Test key distrust + JWKS cache invalidation |
| Token gửi qua HTTP không TLS | Security test fail |
| Token JWE bị copy và dùng lại như Bearer | Test cho thấy encryption không tự chống replay |
| DPoP-bound token không có proof hợp lệ | RS từ chối |
| Refresh token cũ bị replay sau rotation | AS xử lý reuse/token family theo policy |
| Token đã bị revoke nhưng signed JWT còn hạn | RS xử lý theo revocation SLA thực tế |
| Spring decoder chỉ check signature không check audience | Integration test thất bại |
| Scope đúng nhưng tenant/owner sai | API từ chối object-level authorization |
| Raw token/private key xuất hiện trong logs | Security review fail |

### 25.1. Unit tests cho JCA snippets

**Signature unit tests:**

1. Ký một message bằng private signing key của issuer.
2. Verify bằng đúng public key → `true`.
3. Verify bằng public key không cùng cặp → `false`.
4. Thay một byte trong message hoặc signature → `false`.
5. Kiểm signature **không làm plaintext bị giấu**.

**AES-GCM unit tests:**

1. Sinh CEK và IV ngẫu nhiên theo policy.
2. Encrypt rồi decrypt với đúng key/IV/AAD → plaintext giống ban đầu.
3. Thay AAD/ciphertext/tag → không nhận plaintext.
4. Mô phỏng IV collision/restart để kiểm nonce allocator có fail policy.
5. Kiểm ciphertext/CEK không bị ghi vào logs.

### 25.2. Integration tests với AS và RS

1. AS phát signed JWS access token bằng private key đăng ký.
2. RS chọn public key từ **trusted issuer JWKS** và verify đúng `alg`.
3. Gọi API đúng/sai audience, token type, scope và tenant.
4. Rotate signing keys; kiểm cache và overlap.
5. Nếu AS phát JWE, RS giải mã bằng đúng decryption key rồi verify inner signature/claims.
6. Thử JWT do attacker tự ký, `jku` giả, HS/RS confusion và `alg=none`.
7. Thử token theft/replay và revoke theo TTL/denylists/introspection.

**Không dùng production private keys hoặc tokens trong test fixtures.** Key material phục vụ test phải cô lập; không in private JWK hay encrypted private key passphrase vào CI logs.

## 26. Checklist production: Signing khác encryption

1. **Xác định security property:** integrity/origin vs confidentiality vs freshness/authorization; không dùng thuật ngữ “mã hóa” để chỉ Base64url.
2. **Biết token format:** JWS 3 phần, JWE compact 5 phần; hiểu empty encrypted-key segment ở các mode hợp lệ.
3. **Có trusted issuer:** public verification key từ JWKS/registry đã tin, không nhận `jku`/`jwk` tùy ý của token.
4. **Khóa thuật toán theo profile:** JWS `alg`, JWE `alg`+`enc`, đúng key type/size và token purpose.
5. **Từ chối unsecured JWT:** `alg=none` không hợp lệ với signed access-token policy.
6. **Tránh HS/RS confusion:** không dùng RSA public key bytes làm HMAC secret; cân nhắc tách public verification khỏi signing quyền hạn.
7. **Không chia private signing key cho RS:** chỉ issuer/KMS signer được ký; RS dùng public key verify.
8. **Phân tách signing và encryption keys:** quyền key_ops, `use`, IDs, registry và rotation độc lập.
9. **JWE có authenticated encryption:** kiểm GCM tag, ràng buộc AAD, nonce uniqueness, limits và key management an toàn.
10. **Nested JWT khi cần cả hai:** sign then encrypt theo profile, decrypt rồi verify inner signature và claims.
11. **Không tự làm JOSE:** sử dụng thư viện được duy trì, review serialization, algorithms, `crit`, `zip` và size limits.
12. **JWT claims không chứa secret:** giảm PII, không nhúng password, private keys, recovery tokens hoặc dữ liệu không cần.
13. **TLS ở mọi hop:** certificate/hostname verification, kiểm proxy termination, không tin TLS thay all token protections.
14. **Bảo vệ nơi lưu:** secret manager/KMS/HSM/OS keystore, access control, TTL, backups, rotation, logs redaction.
15. **Key rotation có runbook:** signing key trust/JWKS cache khác với JWE decryption-key overlap.
16. **Phân biệt access/ID/refresh/proof:** enforce token type/profile, issuer, audience, expiry, `scope`, principal type.
17. **RS xác minh quyền:** tenant, ownership, entitlement và business rules; signature/decryption thành công chưa phải allow.
18. **Có revocation policy:** JWT signing không tự phản ánh revoke; chọn TTL ngắn, denylist/introspection/session version theo SLA.
19. **Chống replay:** DPoP/mTLS binding khi phù hợp, refresh token rotation, telemetry; không coi access-token `jti` là one-time mặc định.
20. **Thử lỗi thực:** tampering, key substitution, tag failure, invalid audience/type, missing claims, key compromise và outages.
21. **Không fail open:** decrypt/verify/signature/JWKS/introspection errors phải từ chối theo contract, không chuyển thành anonymous success.
22. **Thông tin cho developer chính xác:** “signed” ≠ “encrypted” ≠ “authorized”; bảo vệ secrets ngay cả khi token có mã hóa.

## 27. Câu hỏi tự kiểm tra và bài tập phân tích

**Câu 1.** Một JWT JWS `RS256` có payload chứa email. Người nhận không có private signing key có đọc được email không?

**Trả lời:** Có, nếu họ có token: payload Base64url có thể decode. Không thể **giả mạo chữ ký issuer** nếu không có private key (giả định crypto/trust đúng), nhưng signing không giấu email.

**Câu 2.** Nếu attacker tạo JWE dùng public encryption key của Orders API, liệu Orders API có biết token đến từ AS không?

**Trả lời:** Không chỉ nhờ decryption. Cần issuer-authenticated claims (ví dụ inner JWS signature) và OAuth token validation đúng profile.

**Câu 3.** Một token signed JWT đúng issuer, hết hạn sau 30 phút, bị user revoke lúc phút thứ 5. RS offline chỉ kiểm signature/`exp` có biết revoke ngay không?

**Trả lời:** Không. Cần denylist, session/grant state, introspection/event hoặc chờ `exp`, theo SLA.

**Câu 4.** Trong JWE `alg=RSA-OAEP-256`, `enc=A256GCM`, thuật toán nào bảo vệ CEK và thuật toán nào mã hóa payload?

**Trả lời:** `RSA-OAEP-256` bảo vệ CEK theo key-management scheme; `A256GCM` mã hóa/xác thực payload.

**Câu 5.** Một server có cùng AES-GCM key và IV cho hai messages. Nếu tags vẫn được tạo, có an toàn không?

**Trả lời:** Không. Reuse cặp key/nonce ở GCM là lỗi nghiêm trọng, có thể phá bí mật/toàn vẹn; tag không cứu thiết kế nonce sai.

**Câu 6.** RS kiểm được ID token có signature hợp lệ từ OP, vậy có được chấp nhận làm access token không?

**Trả lời:** Không. ID token dành cho OIDC client, phải phân biệt profile/type/audience; RS chỉ chấp nhận access token đúng resource và quyền.

**Câu 7.** DPoP-bound JWT có cần xác minh chữ ký của issuer không?

**Trả lời:** Có. Sender proof không thay signature/issuer/audience/expiry/scope validation của access token; còn cần kiểm DPoP proof, key binding và HTTP request binding.

**Câu 8.** Có thể ngăn replay Bearer JWE chỉ bằng cách mã hóa payload mạnh hơn không?

**Trả lời:** Không. Attacker không cần decrypt để trình lại cùng chuỗi credential. Phải bảo vệ token, giới hạn lifetime, revoke hoặc sender-constrain theo threat model.

## 28. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, signed/encrypted JWT và nested JWT.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): ký/MAC, protected header, signature verification, compact serialization.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): key management, content encryption, IV/tag, protected header và nested payload.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE, `alg`, `enc`, RSA-OAEP và AES-GCM.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm allowlist, cryptographic validation và cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token type/issuer/audience/claims validation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client/AS/RS roles, access và refresh token lifecycle.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): sender-constrained tokens, token theft/replay và OAuth hardening.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials và transport security.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque/reference token status và caller authentication.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và giới hạn hiệu lực access tokens.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof JWT và sender binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và certificate-bound access tokens.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA trong JOSE theo profile tương ứng.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): signed/encrypted ID token, issuer/audience/nonce và OIDC authentication.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): authenticated encryption GCM và nonce requirements.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, JWK retrieval và validators.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): token validity khác quyền trên đối tượng.

**Ghi nhớ:** **Signing và encryption không thể thay thế nhau.** **JWS** ký/MAC để kiểm **toàn vẹn và bằng chứng từ khóa đã tin**, nhưng claims thường **đọc được**. **JWE** mã hóa để giữ **bí mật payload** tới người nhận có khóa, cùng bảo vệ toàn vẹn theo AEAD, nhưng **decrypt thành công không mặc nhiên chứng minh issuer hoặc quyền OAuth**. Khi cần cả hai, dùng profile **signed JWT trong encrypted JWE**; luôn tách khóa ký/giải mã, kiểm `alg`/`enc`/`kid` theo trust policy, bảo vệ khóa và token. Cuối cùng, Resource Server vẫn phải xác minh **issuer, audience, token type, thời hạn, scope, tenant, quyền trên tài nguyên**, cũng như revocation và chống replay theo yêu cầu hệ thống.
