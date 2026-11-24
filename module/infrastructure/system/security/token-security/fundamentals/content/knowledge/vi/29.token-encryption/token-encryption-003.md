# Sign rồi encrypt và encrypt rồi sign

Khi một hệ thống phát hành token cần cả **xác minh nguồn gốc và tính toàn vẹn** lẫn **giữ bí mật nội dung**, hai thao tác mật mã thường xuất hiện cùng nhau: **signing (ký)** và **encryption (mã hóa)**. Tuy nhiên, **thứ tự ghép chúng quan trọng**. Hai biểu thức trông tương đương về mặt ngôn ngữ:

- **Sign rồi encrypt (ký rồi mã hóa):** tạo chữ ký trên nội dung trước, sau đó mã hóa **cả nội dung đã ký** cho người nhận.
- **Encrypt rồi sign (mã hóa rồi ký):** mã hóa nội dung trước, sau đó ký **bản mã** (hoặc một cấu trúc chứa bản mã) để người nhận hoặc một bên được tin cậy có thể xác minh chữ ký bên ngoài.

Trong hệ sinh thái **JOSE/JWT**, hai cấu trúc minh họa là:

~~~text
Sign-then-encrypt (StE):
  JWE( JWS( claims ) )
  outer object: JWE Compact (thường 5 phần)
  inner object: JWS Compact (thường 3 phần)

Encrypt-then-sign (EtS):
  JWS( JWE( claims ) )
  outer object: JWS Compact (thường 3 phần)
  inner object: JWE Compact (thường 5 phần)
~~~

**Cả hai đều có thể được thiết kế an toàn nếu tuân đúng giao thức**, nhưng không cung cấp cùng một cách bộc lộ chữ ký, kiểm tra lớp ngoài và chia sẻ bằng chứng với bên thứ ba. **RFC 7519, mục 11.2**, nêu rằng khi không có yêu cầu ứng dụng ngược lại, thông thường **nên ký thông điệp trước rồi mã hóa kết quả**. Đây là hướng dẫn về thứ tự **nested JWT**, không phải tuyên bố rằng mọi hình thức encrypt-then-sign đều bất hợp lệ hay một công thức tự triển khai có thể thay thế thư viện JOSE.

Bài **“Sign rồi encrypt và encrypt rồi sign”** thuộc chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Ta sẽ liên hệ cách ghép JWS/JWE với trust model giữa **Authorization Server (AS), OAuth/OIDC client và Resource Server (RS)**; cách xác minh JWT, opaque/access/refresh tokens, claims, `scope`, `aud`, lưu trữ, khóa ký/khóa giải mã, thu hồi token và phòng chống đánh cắp/phát lại.

> **Điểm mấu chốt:** **Ký không mã hóa; mã hóa không mặc nhiên xác minh issuer.** Khi dùng nhiều lớp, phải kiểm **tất cả lớp được yêu cầu** và **toàn bộ chính sách token**. Đối với JWT cần cả hai thuộc tính, **signed JWT được đặt bên trong encrypted JWE** thường là thiết kế dễ diễn đạt hơn: người nhận giải mã, xác minh chữ ký issuer, rồi kiểm `iss`, `aud`, `exp`, loại token, `scope` và quyền tài nguyên.

## 1. Trước hết: signing và encryption giải quyết hai mục tiêu khác nhau

Giả sử AS cấp access token để Orders API thực hiện:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "at-unique-42"
}
~~~

Payload trên chỉ minh họa các claims, **không phải JWT có chữ ký thực**. Hệ thống có ít nhất bốn câu hỏi:

| Câu hỏi | Thuộc tính bảo mật | Cơ chế thường dùng |
| --- | --- | --- |
| Các claims có bị thay đổi không? | **Integrity** | JWS signature/MAC, AEAD tag trong phạm vi được xác thực |
| Claims thực sự do AS được tin phát hành? | **Origin authentication** | JWS bằng issuer signing key và public-key trust policy, hoặc issuer authentication profile phù hợp |
| Ai có thể xem `sub`, `scope`, PII? | **Confidentiality** | JWE hoặc giảm dữ liệu nhúng/opaque token; TLS bảo vệ từng hop |
| Token có quyền gọi API **ngay bây giờ**? | **Authorization/freshness** | `iss`, `aud`, `exp`, `nbf`, `scope`, tenant, object ownership, revocation, sender constraint |

Chữ ký **không tự giấu nội dung**. Một access token JWT được bảo vệ bằng JWS Compact có payload Base64url mà ai có chuỗi token cũng có thể decode. Ngược lại, với **public-key encryption** cho khóa của RS, ai biết public encryption key đều có thể mã hóa một thông điệp gửi RS; **decrypt được không chứng minh AS là bên đã tạo plaintext**.

### 1.1. Khi nào chỉ dùng JWS đã đủ?

Nhiều OAuth resource servers nhận **signed JWT access token qua HTTPS**, trong đó claims đủ tối giản và được phép hiển thị cho client/RS. RS kiểm chữ ký issuer, audience, thời hạn, loại token, scope và quyền tài nguyên. **Không phải tất cả access tokens đều cần JWE**.

### 1.2. Khi nào chỉ có JWE chưa đủ?

Giả sử RS công bố public encryption key. Attacker cũng có thể mã hóa một JSON:

~~~json
{
  "sub": "admin",
  "scope": "orders.delete"
}
~~~

RS có thể **giải mã được** JWE ấy bằng private key của mình. Nếu RS coi plaintext vừa giải mã là một access token được AS cấp mà **không kiểm issuer provenance**, attacker đã tự cấp quyền. **Đối với claims cần bằng chứng AS phát hành, giải mã thành công không thay việc xác thực issuer.**

### 1.3. Authenticated encryption cũng không thay authorization

JWE thường dùng content encryption có xác thực (chẳng hạn `A256GCM`), nghĩa là ciphertext và authenticated data được bảo vệ khỏi sửa đổi theo đúng key-management scheme. Nhưng AEAD tag **không tự kiểm** token `aud`, `scope`, expiration, principal, consent hay quyền theo tenant. Tất cả đều là chính sách bắt buộc của tầng nhận token.

## 2. Nền tảng JOSE: JWS, JWE và JWT không phải ba tên gọi thay nhau

| Khái niệm | Ý nghĩa | Compact Serialization | Nội dung có thể đọc bằng Base64url? |
| --- | --- | --- | --- |
| **JWT** (RFC 7519) | Claims set được biểu diễn bằng JWT, có thể signed hoặc encrypted | Phụ thuộc JWS/JWE | Phụ thuộc lớp bảo vệ |
| **JWS** (RFC 7515) | Ký/MAC payload, bảo vệ integrity/origin trong trust context | **3 phần** | **Payload thường đọc được** |
| **JWE** (RFC 7516) | Mã hóa payload theo key management + content encryption | **5 phần** | Header nhìn được, ciphertext không đọc được nếu không có key |
| **Nested JWT** | JWT có một JOSE object bên ngoài và JWT bên trong | Tùy lớp ngoài | Phụ thuộc vị trí mã hóa |

JWS Compact:

~~~text
BASE64URL(protected_header)
.
BASE64URL(payload)
.
BASE64URL(signature_or_mac)
~~~

JWE Compact:

~~~text
BASE64URL(protected_header)
.
BASE64URL(encrypted_key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
~~~

**Không suy từ số phần rằng token đã hợp lệ.** Một chuỗi có ba đoạn có thể là JWS giả chữ ký; một chuỗi có năm đoạn có thể là JWE không decrypt được, key sai hoặc profile bị cấm. Đặc biệt JWE `alg=dir` có thể có **encrypted-key segment rỗng** theo tiêu chuẩn.

### 2.1. JWS `alg` khác JWE `alg`

- `alg=RS256`, `PS256`, `ES256` ở JWS: **signature algorithms** hoặc HMAC tương ứng.
- `alg=RSA-OAEP-256`, `ECDH-ES`, `dir` ở JWE: **key-management algorithms**.
- `enc=A256GCM` ở JWE: **content-encryption algorithm**, không phải signing algorithm.

Ví dụ thường gặp:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-recipient-enc-2026-11",
  "cty": "JWT"
}
~~~

Ở đây AS dùng recipient public key theo RSA-OAEP-256 để bảo vệ **content encryption key (CEK)**, rồi CEK mã hóa **nội dung** bằng AES-256-GCM. Không dùng RSA trực tiếp để mã hóa một payload JWT dài; JWE là một hình thức **hybrid encryption**.

### 2.2. Protected header không bí mật

Cả header JWS lẫn header JWE Compact đều được Base64url-encode, **không tự bị mã hóa**. Với JWE, protected header được ràng buộc toàn vẹn qua authenticated encryption, nhưng `alg`, `enc`, `kid`, `cty` vẫn có thể bị đọc. **Không nhét bí mật, PII hoặc token credentials vào header** chỉ vì bên ngoài là JWE.

## 3. Sign rồi encrypt: cấu trúc `JWE(JWS(claims))`

Quy trình:

1. AS tạo JWT claims đúng profile dành cho RS.
2. AS ký claims bằng **private signing key** của issuer, nhận **JWS Compact**.
3. AS mã hóa **toàn bộ chuỗi JWS** cho recipient bằng **public encryption key** được đăng ký/được tin, nhận **JWE Compact**.
4. Client truyền JWE đến RS qua kênh HTTPS theo token transport policy.
5. RS giải mã JWE bằng **private decryption key** tương ứng, kiểm authentication tag.
6. RS lấy **inner JWS**, xác minh chữ ký bằng **trusted public verification key của AS**.
7. RS kiểm JWT token type, `iss`, `aud`, `exp`, `nbf`, `scope`, tenant, sender binding, revocation và business authorization.

~~~mermaid
flowchart TD
    A["Claims do AS tạo"] --> B["Sign với AS private key"]
    B --> C["Inner JWS\nheader.payload.signature"]
    C --> D["Encrypt cho RS public key"]
    D --> E["Outer JWE\n5 phần"]
    E --> F["Client truyền tới RS qua HTTPS"]
    F --> G["RS decrypt với private key và verify tag"]
    G --> H["RS verify inner JWS bằng public key của AS"]
    H --> I{"Đúng issuer, audience,\nexp, scope, token type, quyền?"}
    I -->|Có| J["Cho phép thao tác"]
    I -->|Không| K["Từ chối"]
~~~

### 3.1. Ví dụ header của inner JWS

~~~json
{
  "alg": "PS256",
  "typ": "at+jwt",
  "kid": "as-signing-2026-11"
}
~~~

**`at+jwt`** được sử dụng cho profile **RFC 9068 JWT access tokens**. Nó giúp phân biệt access token với ID token, JWT client assertion hay DPoP proof, nhưng **không tự thay yêu cầu kiểm issuer/audience/claims**.

### 3.2. Ví dụ header của outer JWE

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "orders-decryption-2026-11"
}
~~~

Outer JWE `cty=JWT` cho người nhận biết nội dung bên trong là một JWT theo nested JWT profile. `kid` của **JWE** dùng chọn **recipient decryption key**, không phải issuer signing key. Trong cùng một token có thể có **hai `kid` khác nhau**, với hai trust domains hoàn toàn khác nhau.

### 3.3. Từ góc nhìn các bên

| Bên | Nhìn được gì? | Làm được gì? |
| --- | --- | --- |
| **AS** | Claims, JWS đã ký, JWE vừa tạo | Ký bằng private AS và encrypt cho public recipient key |
| **OAuth client** | Chuỗi outer JWE + header JWE; thường không thấy plaintext | Chuyển token đúng nơi, có thể **replay nếu là Bearer** |
| **Reverse proxy không có decryption key** | Outer JWE header, kích thước và chuỗi ciphertext | Không đọc inner JWS/claims; vẫn có thể đánh cắp **credential ciphertext** |
| **RS được cấp private decryption key** | Inner JWS sau decrypt | Verify issuer signature, xét claims và quyền |
| **Bên chỉ có public signing key AS** | Không đọc inner JWS nếu không decrypt JWE | Không thể verify inner signature **khi chưa có inner JWS** |

**Lợi thế nổi bật:** không chỉ claims mà **cả chữ ký issuer và inner JWS header** được che khỏi các bên không có khóa giải mã. Nếu mô hình yêu cầu một bên thứ ba có thể verify chữ ký ngay **mà không được xem claims**, cấu trúc này không cho phép họ làm vậy trực tiếp.

### 3.4. Tại sao thứ tự này thường được ưu tiên cho nested JWT?

Nó giữ bằng chứng ký **trên chính plaintext claims** trong một JWS độc lập. Người nhận được phép decrypt có thể lưu/kiểm inner JWS và chứng minh issuer đã ký những claims ấy theo trust policy. Đồng thời lớp encryption bên ngoài giới hạn ai được **nhìn thấy** chứng cứ và dữ liệu.

Không suy rằng bất kỳ bên nào có inner JWS đều có quyền chia sẻ hoặc dùng nó như token ở resource khác: vẫn cần audience, token type và data-handling policy.

## 4. Encrypt rồi sign: cấu trúc `JWS(JWE(claims))`

Một cấu trúc JOSE khác có thể được thiết kế như sau:

1. AS tạo claims và mã hóa chúng thành **inner JWE** dành cho RS.
2. AS ký **toàn bộ serialization của inner JWE** bằng private signing key của mình, tạo **outer JWS**.
3. Client chuyển outer JWS đến RS.
4. RS kiểm **outer JWS signature** bằng trusted public verification key của AS **trước khi giải mã**.
5. Sau khi xác minh signature và outer profile, RS giải mã **inner JWE** bằng private decryption key.
6. RS kiểm claims và quyền API theo profile.

~~~mermaid
flowchart TD
    A["Claims do AS tạo"] --> B["Encrypt cho RS public key"]
    B --> C["Inner JWE\n5 phần"]
    C --> D["Sign serialization của JWE\nvới AS private key"]
    D --> E["Outer JWS\n3 phần"]
    E --> F["Client truyền tới RS qua HTTPS"]
    F --> G["RS verify outer JWS\nvới public key AS"]
    G --> H["RS decrypt inner JWE\nvà verify encryption tag"]
    H --> I{"Đúng token type, issuer,\naud, exp, scope, quyền?"}
    I -->|Có| J["Cho phép thao tác"]
    I -->|Không| K["Từ chối"]
~~~

### 4.1. Outer JWS có thật sự làm lộ claims không?

**Không nhất thiết.** Trong cấu trúc này, **outer JWS payload là chuỗi inner JWE đã mã hóa**. Ai decode payload của JWS sẽ thấy một chuỗi JWE Compact, **không phải JSON claims nguyên bản**. Nhưng **outer JWS header và chữ ký** có thể nhìn thấy, còn một bên có trusted issuer public key có thể verify **AS đã ký ciphertext ấy** mà không decrypt claims.

### 4.2. Inner JWE bảo vệ những gì?

Inner JWE bảo vệ tính bí mật của claims đối với bên không có recipient decryption key. Nó cũng có authentication tag cho ciphertext/AAD theo profile JWE. **Tuy nhiên, sau khi decrypt, RS chỉ được tin claims nếu kiểm outer JWS issuer signature và binding đúng**; không được lấy inner JWE ra khỏi outer JWS rồi chấp nhận nó riêng như một access token.

### 4.3. Chữ ký bên ngoài chứng minh điều gì?

Outer signature chứng minh **issuer key đã ký serialization ciphertext cụ thể**, không phải một JWS ký trực tiếp trên plaintext JSON claims. Nếu cần cung cấp cho auditor một **chữ ký có thể verify trực tiếp trên nội dung claims không mã hóa**, EtS không có inner plaintext JWS để trao ngay. Có thể cần giữ cả outer JWS và inner JWE cùng quy trình kiểm, hoặc dùng StE tùy yêu cầu evidentiary/protocol.

### 4.4. EtS có phải sai tiêu chuẩn?

Không. JOSE có thể biểu diễn một **JWS chứa JWE** và **RFC 7519** thảo luận cả hai thứ tự. Nhưng khi ứng dụng cần cả bảo vệ chữ ký trên claims và che nội dung, RFC khuyên **thông thường ưu tiên sign-then-encrypt**. Nếu chọn encrypt-then-sign, phải có **profile rõ** cho outer/inner header, thứ tự validation, key trust, token type và cách tránh một lớp bị bypass.

## 5. So sánh trực tiếp hai thứ tự

| Tiêu chí | **Sign rồi encrypt**: JWE(JWS(P)) | **Encrypt rồi sign**: JWS(JWE(P)) |
| --- | --- | --- |
| **Lớp ngoài** | JWE | JWS |
| **Lớp trong** | JWS | JWE |
| **Thứ tự phát hành** | Sign P → encrypt JWS | Encrypt P → sign JWE |
| **Thứ tự xử lý tại RS** | Decrypt → verify signature | Verify signature → decrypt |
| **Claims có bị giấu?** | Có, nhờ outer JWE | Có, nhờ inner JWE |
| **Issuer signature có bị giấu?** | Có, nằm trong JWE | Không, outer signature thấy được |
| **Bên không có decryption key có thể verify issuer signature?** | Không trực tiếp, vì inner JWS bị mã hóa | Có, nếu được tin cậy cấp issuer public key và profile cho phép |
| **Signature gắn trực tiếp plaintext claims?** | Có, inner JWS | Không theo cách đó; outer JWS ký serialized inner JWE |
| **Kiểm issuer trước decryption được không?** | Không bằng inner JWS; có thể xác thực sender qua kênh riêng | Có, qua outer JWS |
| **Lớp nào chứa `cty=JWT`?** | Thường outer JWE | Thường outer JWS |
| **Rủi ro nếu chỉ kiểm lớp ngoài** | JWE decrypt OK nhưng bỏ inner signature | Outer JWS verify OK nhưng bỏ decrypt/claims checks |
| **Khuyến nghị chung RFC 7519** | Thường ưu tiên nếu không có yêu cầu khác | Chỉ chọn khi có mục tiêu/protocol cụ thể |

\(P\) biểu diễn claims plaintext. Bảng minh họa **compact nested JOSE**, không bao quát mọi JWE JSON Serialization/multi-recipient profile.

### 5.1. Không dùng bảng để suy “EtS kém an toàn hơn trong mọi trường hợp”

Độ an toàn phụ thuộc **cryptographic algorithms, key custody, provenance checks, message binding, parser và error handling**. EtS có ưu điểm cho người cần **verify chữ ký bên ngoài trước decrypt**, nhưng có thể không đáp ứng yêu cầu giữ kín **danh tính/ký hiệu của signer** hoặc chữ ký trực tiếp trên claims. StE che chữ ký hơn nhưng RS phải thực hiện decryption an toàn trước khi kiểm inner issuer signature.

### 5.2. Ai xác minh chữ ký được là một quyết định về quyền riêng tư

Nếu doanh nghiệp muốn proxy hoặc auditor kiểm “AS đã ký payload mã hóa này” mà **không có quyền xem `sub` hoặc `scope`**, EtS có thể phù hợp hơn. Nếu chính sách chỉ cho RS nhìn thấy cả claims và bằng chứng ký, StE thường dễ giới hạn thông tin hơn.

### 5.3. Khi nào hai lớp có thể độc lập?

Ở StE, inner JWS là một signed JWT có thể được verifier xử lý riêng **sau khi được decrypt bởi recipient được ủy quyền**. Ở EtS, inner JWE là encrypted claims mà **không mặc nhiên có issuer signature bên trong**; nếu ai tách JWE khỏi outer signature và tái sử dụng, cơ chế provenance có thể mất.

## 6. Tách rạch ròi nguồn phát hành, người nhận và quyền sử dụng

Trong một hệ thống có ba bên:

~~~text
Authorization Server (AS):
  - sở hữu PRIVATE SIGNING KEY
  - chịu trách nhiệm claims/provenance của access token

Orders Resource Server (RS):
  - sở hữu PRIVATE DECRYPTION KEY
  - nhận PUBLIC VERIFICATION KEY của AS từ nguồn tin cậy
  - kiểm access token rồi thực hiện authorization theo resource

OAuth Client:
  - thường chỉ giữ/đưa access token qua HTTPS
  - không cần private signing key AS
  - không cần private decryption key RS
~~~

**Hai cặp khóa bất đối xứng khác nhau** có vai trò khác nhau. Với StE, AS dùng private signing key để ký và recipient public encryption key để mã hóa; RS dùng private decryption key để giải mã và issuer public signing key để verify. Với EtS, cùng cặp vai trò có thể được dùng nhưng thứ tự thao tác và vị trí chữ ký thay đổi.

### 6.1. Recipient authentication khác issuer authentication

- **Issuer authentication:** Chữ ký được xác minh bằng public key của **AS được cấu hình tin cậy**; kiểm `iss`, token type và issuance profile.
- **Recipient binding:** JWE được encrypt cho đúng **public key của Orders RS**, không phải ngẫu nhiên cho key của một service khác; RS kiểm allowed encryption key, `kid`, `alg`, `enc` và context.
- **Authorization:** Chỉ những principal có đúng `scope`, audience, tenant và quyền trên bản ghi mới được xử lý request.

Người có thể decrypt JWE **không tự có quyền** phát JWT của issuer. Ngược lại, một signer có quyền ký token **không nhất thiết có private decryption key** để xem dữ liệu mã hóa cho recipient khác.

### 6.2. Public encryption key không xác thực người gửi

Giả sử attacker biết public encryption key của RS. Họ có thể tạo một **inner JWE hợp lệ về crypto**. Trong StE, token đó vẫn thiếu **inner JWS signature đáng tin**. Trong EtS, attacker cần **outer JWS signature đáng tin**. Một RS chỉ decrypt thành công rồi tạo `Authentication` đã **bỏ qua ranh giới trust quan trọng nhất**.

### 6.3. HMAC/symmetric encryption có miền tin cậy khác

Với `HS256`, cả issuer và verifier biết **MAC secret** nên verifier có khả năng tạo MAC mới. Với JWE `alg=dir`, các bên chia sẻ content-encryption key theo contract; authentication tag bảo vệ integrity dưới shared key nhưng **không chứng minh một người gửi duy nhất** nếu nhiều bên giữ key.

Không thể thay thế hai cặp khóa public/private trong sơ đồ bằng **một secret chung** mà vẫn giữ nguyên mô hình phân quyền/khả năng quy trách nhiệm. Nếu có nhiều RS, việc phát secret HS256 hoặc shared CEK rộng khắp làm tăng blast radius.

## 7. JOSE header: `typ`, `cty`, `alg`, `enc`, `kid`

Việc nhận ra token đang mang **profile nào** quan trọng không kém verify/decrypt.

| Field | Lớp | Vai trò | Kiểm tra bắt buộc theo policy |
| --- | --- | --- | --- |
| **`alg` JWS** | Chữ ký | Chọn signature/MAC algorithm | Allowlist theo issuer/key type; không tin header tự cho phép |
| **`alg` JWE** | Mã hóa | Key management/CEK algorithm | Allowlist, đúng recipient key type/strength |
| **`enc` JWE** | Mã hóa | Content-encryption algorithm | Allowlist và authenticated encryption |
| **`kid` JWS** | Chữ ký | Gợi ý issuer public verification key | Chọn trong JWKS thuộc issuer tin cậy |
| **`kid` JWE** | Mã hóa | Gợi ý recipient decryption key | Chọn trong authorized recipient registry |
| **`typ`** | JOSE | Loại object theo profile, ví dụ `at+jwt` | Explicit type validation; tránh cross-JWT confusion |
| **`cty`** | JOSE | Loại nội dung nằm trong payload (nested `JWT`) | Ràng buộc nesting/expected inner object |
| **`crit`** | JOSE | Critical header extensions | Phải hiểu/xử lý extension, không bỏ qua tùy tiện |
| **`zip`** | JWE | Compression của plaintext trước encryption | Chỉ chấp nhận khi được phép; chống decompression bomb/oracle |

### 7.1. `typ` không phải `cty`

`typ` giúp xác định **JOSE object hiện tại** thuộc loại nào theo application profile. `cty` biểu thị **nội dung bên trong** là một object thuộc loại nào; với nested JWT, RFC 7519 yêu cầu `cty=JWT` trên lớp ngoài theo quy tắc của nested JWT.

Ví dụ StE:

~~~text
Outer JWE header:
  alg = RSA-OAEP-256
  enc = A256GCM
  kid = orders-decryption-key
  cty = JWT

Decrypted inner JWS header:
  alg = PS256
  typ = at+jwt
  kid = auth-signing-key
~~~

Ví dụ EtS:

~~~text
Outer JWS header:
  alg = PS256
  kid = auth-signing-key
  cty = JWT

Verified payload is inner JWE:
  alg = RSA-OAEP-256
  enc = A256GCM
  kid = orders-decryption-key
~~~

**Không tự nhận một outer JWS mang `cty=JWT` thành access token** trước khi giải mã inner JWE và kiểm claims. `cty` là gợi ý xử lý nesting được bảo vệ đúng lớp, không chứng minh claims đã hợp lệ.

### 7.2. Token type cần được xác minh ở đúng tầng

Trong StE, inner JWS có thể mang `typ=at+jwt` cho RFC 9068 access token. Trong EtS, inner JWE có thể là encrypted JWT claims theo profile, và outer JWS có thể có một loại **application-specific signed envelope**, không tự biến payload inner JWE thành profile RFC 9068 nếu không có hợp đồng xử lý cụ thể.

Một hệ thống muốn hỗ trợ cả hai thứ tự phải **khai báo rõ profile nào được phép ở API nào**. Không cho library “đoán” dựa vào số dấu chấm rồi bỏ qua kiểm token substitution.

### 7.3. Không chấp nhận `alg=none` làm chữ ký issuer

Nếu ứng dụng yêu cầu issuer-signed token, `none` không cung cấp integrity/authentication. Không fallback khi JWKS unavailable hoặc chữ ký sai. Cũng không chấp nhận tùy ý `HS256` nếu issuer policy chỉ có `PS256` hoặc `RS256`.

### 7.4. `kid` không trao quyền chọn bất cứ khóa nào

`kid` là identifier, **không phải một bằng chứng trust**. Không tải `jku`/`x5u` do token chưa verify đưa vào để tự bổ sung key, tránh attacker-controlled JWKS và SSRF. Public signing key phải ràng buộc **trusted issuer**, decryption key phải ràng buộc **recipient/purpose**, key rotation phải duy trì proper allowlist.

## 8. Quy trình xác minh StE: giải mã an toàn rồi mới tin inner JWS

Một **Resource Server** nhận JWE(JWS) nên phân tách các trạng thái:

~~~mermaid
flowchart TD
    R["Nhận Bearer outer JWE"] --> F["Kiểm size, compact syntax, allowed type"]
    F --> H["Kiểm protected JWE header:\nalg, enc, cty, kid, crit, recipient"]
    H --> D["Decrypt JWE, verify AEAD tag"]
    D --> P["Parse inner JWS, đúng cấu trúc và nesting depth"]
    P --> S["Kiểm JWS alg/type, trusted issuer key\nVerify signature"]
    S --> C["Validate iss, aud, exp, nbf,\nscope, principal/tenant, revocation"]
    C --> B{"Business authorization đạt?"}
    B -->|Có| A["Cho phép request"]
    B -->|Không| X["Từ chối"]
    D -. "Bad tag, wrong key" .-> X
    S -. "Bad signature, wrong issuer" .-> X
~~~

### 8.1. Không coi decrypt thành công là access token hợp lệ

Kể cả khi AES-GCM tag đúng, việc đó chỉ chứng minh ciphertext/AAD khớp key-management context được sử dụng. Với public-key recipient encryption, **attacker biết public key có thể tạo JWE mới**. Do đó **phải có inner signed JWT hoặc issuer authentication profile rõ**. Nếu parse được JSON rồi skip JWS verify, API đã mở cửa **token forgery**.

### 8.2. Không xử lý claims trước khi verify issuer signature

Sau decrypt, inner JWS payload có thể đọc được bằng Base64url. Nhưng **các claims vẫn là dữ liệu chưa đáng tin** cho tới khi signature, issuer key và JWT profile được kiểm. Không đọc `scope=admin` rồi thực hiện hành động trước khi gọi verifier.

### 8.3. Giới hạn rủi ro decryption oracle

Với StE, RS bắt buộc decrypt trước khi có thể kiểm **inner** issuer signature. Vì vậy **decryption endpoint phải hardened**:

- Giới hạn payload length, nesting depth và các algorithm/key types;
- Rate limit, authentication/context constraints nếu phù hợp;
- Không phản hồi phân biệt quá chi tiết “RSA unwrap sai”, “GCM tag sai” hay “inner signature sai” cho caller không tin;
- Không expose raw plaintext khi bước inner verify thất bại;
- Không decompress payload vượt hạn mức;
- Dùng JOSE library thực hiện authenticated encryption đúng và không trả plaintext chưa xác thực.

**Không coi thứ tự decrypt-before-verify là một bug tự thân**; nó là đặc tính của StE, đòi triển khai decryption an toàn và không dùng dữ liệu trước khi verify inner issuer.

### 8.4. Chính sách lớp ngoài và lớp trong cần độc lập

Outer JWE `kid` chọn recipient key, còn inner JWS `kid` chọn public key của issuer. **Một key đúng ở một lớp không bù được key sai ở lớp còn lại.** Hệ thống phải từ chối nếu:

- Outer JWE được encrypt cho recipient khác;
- Inner JWS dùng issuer không tin cậy;
- Inner JWT là ID token, client assertion hoặc DPoP proof bị dùng thay access token;
- Inner access token sai audience, hết hạn hoặc thiếu scope;
- Token bị revoke theo state policy, dù crypto layers đều đúng.

## 9. Quy trình xác minh EtS: verify outer signature rồi mới decrypt

Với JWS(JWE), thứ tự tối thiểu:

~~~mermaid
flowchart TD
    R["Nhận Bearer outer JWS"] --> F["Kiểm syntax, size, expected outer type"]
    F --> H["Kiểm outer JWS alg, kid, cty\nvà trusted AS public key"]
    H --> V["Verify outer JWS signature"]
    V --> I["Parse payload làm inner JWE"]
    I --> J["Kiểm inner alg, enc, kid,\nrecipient/purpose"]
    J --> D["Decrypt inner JWE, verify tag"]
    D --> C["Validate plaintext claims:\niss, aud, exp, scope, type"]
    C --> B{"Business authorization đạt?"}
    B -->|Có| A["Cho phép"]
    B -->|Không| X["Từ chối"]
    V -. "Bad signature" .-> X
    D -. "Bad ciphertext/tag" .-> X
~~~

### 9.1. Verify signature trước decrypt không phải “chỉ cần verify”

Outer signature xác thực **serialized inner JWE** thuộc issuer key. Nó không nói inner encrypted claims có `aud=orders-api`, `exp` còn hạn hay quyền sở hữu order. Những điều này **chỉ biết sau decrypt**. Nếu middleware trả 200 ngay sau outer signature check thì đó là **authorization bypass**.

### 9.2. Không cho inner JWE đi vòng qua outer JWS

Nếu API hỗ trợ JWS(JWE), một attacker có thể tách inner JWE khỏi outer signature và gửi riêng inner JWE (hoặc nhét nó vào một giao thức khác). **Không chấp nhận inner JWE như một access token được AS cấp** nếu không có một chứng cứ issuer-authenticity tương đương và được profile cho phép.

### 9.3. Ký cái gì chính xác?

JWS signature trên **JWS Signing Input** theo RFC 7515:

~~~text
BASE64URL(UTF8(outer_protected_header))
  + "."
  + BASE64URL(UTF8(inner_JWE_compact_string))
~~~

Đó là **signature trên serialized ciphertext envelope**, không đơn thuần gọi `Sign(ciphertext_segment_only)`. Header, key/version, thuật toán và mọi byte của payload được bảo vệ bởi outer signature theo JWS semantics. **Đừng tự triển khai serialize/canonicalize JSON rồi ký lại bằng một bộ quy tắc khác**.

### 9.4. Bên trung gian kiểm chữ ký không có nghĩa được phép cấp quyền

Một gateway có thể verify outer JWS để sớm từ chối ciphertext giả. Nhưng nếu gateway **không có decryption key**, nó không thể đánh giá đầy đủ `aud`, `scope` hoặc quyền trên dữ liệu nằm trong ciphertext. Điều kiện “gateway đã verify signature” không đủ để downstream RS bỏ token validation/business authorization.

## 10. Nested JWT cần ràng buộc context để chống substitution

Rủi ro lớn không chỉ là thuật toán yếu mà là **dùng một object hợp lệ ở sai nơi**.

### 10.1. ID token ≠ access token

OIDC ID token thường có `aud=client_id` dành cho OIDC client; access token dành cho RS và kiểm audience/resource scope. Một ID token được ký đúng, sau đó mã hóa thành JWE cho một ứng dụng, **không tự trở thành access token**.

### 10.2. JWT client assertion ≠ resource credential

Một JWT client assertion (ví dụ `private_key_jwt`) được ký bằng client key để AS authenticate OAuth client tại token endpoint. Nó có `aud` hướng tới AS/token endpoint; **Orders API không được nhận nó làm Bearer access token**, dù cùng thuật toán ký và số lớp nesting.

### 10.3. DPoP proof JWT ≠ access token

DPoP proof là một JWS chứa `htm`, `htu`, `iat`, `jti`, `ath` và key binding; nó được ký bằng **client proof key**, không phải AS issuer signing key. Mã hóa DPoP proof hoặc bọc outer signature không biến proof thành access token. Nếu RS áp DPoP, vẫn cần xác minh **proof và access token riêng**.

### 10.4. Ngăn cross-tenant và cross-audience

Một JWT hợp lệ cho Payments API hoặc tenant A, dù đã sign/encrypt đúng, **không có quyền** truy cập Orders API hoặc bản ghi tenant B. `aud`, scope và object-level authorization phải được kiểm **sau khi cryptographic layers thành công**.

### 10.5. Tránh “JWT parser chung” bỏ qua type

Một parser có thể nhận bất kỳ chuỗi 3 hoặc 5 phần rồi trả về claims. Điều này nguy hiểm nếu các services dùng **cùng issuer/key** cho ID token, access token và assertions. Cần explicit profile/allowed nesting depth/expected inner type, không dựa vào “ký đúng là đủ”.

## 11. Signing/Encryption có thay OAuth token lifecycle không?

Không. Một nested JWT dù có cả JWS và JWE vẫn là **credential có vòng đời**:

| Khía cạnh | Điều phải xử lý |
| --- | --- |
| **Issuance** | AS chỉ phát token cho grant/client/resource hợp lệ; signer/encrypter keys đúng |
| **Validation** | Verify/decrypt cả hai lớp và claims đúng type/issuer/audience |
| **Expiry** | RS kiểm `exp`/`nbf` và clock policy, không dựa chỉ vào crypto |
| **Authorization** | Scope, tenant, object owner, role/entitlement hiện hành |
| **Storage** | Token là credential nhạy cảm; tránh logs/URLs và XSS/leak |
| **Revocation** | `exp` ngắn, denylist/introspection/session version khi cần |
| **Replay** | Bearer ciphertext vẫn có thể bị sao chép/trình lại; dùng DPoP/mTLS khi phù hợp |
| **Rotation** | Signer key và recipient decryption key có lifecycle độc lập |

### 11.1. Access token có thể vẫn là Bearer dù được mã hóa

Nếu RS chấp nhận nguyên chuỗi JWE hoặc outer JWS như **Bearer credential**, attacker không cần biết claims hay decryption key để **replay chính chuỗi token ấy**. Encryption bảo mật **nội dung**, không làm token copy mất giá trị. Cần HTTPS, storage hygiene, revocation và sender binding theo threat model.

### 11.2. Refresh token không mặc định cần JWE

Refresh token thường là opaque credential do AS quản lý; một số AS dùng token có cấu trúc. Việc ký/mã hóa refresh token không thay **rotation, family reuse detection, client binding, expiry và revocation**. Không gửi refresh token đến RS như access token.

### 11.3. Opaque token cũng có thể bảo mật tốt

Một opaque access token không công khai claims cho client; RS có thể introspect qua RFC 7662 với AS. Đổi lại, hệ thống cần **caller authentication, online trust, caching/availability và revocation semantics**. Không chỉ vì muốn giấu claims mà mặc định phức tạp hóa JWS→JWE khi opaque token + introspection đáp ứng threat model tốt hơn.

## 12. Java 17 với Nimbus JOSE + JWT: tạo StE `JWE(JWS)`

Trong Spring Security/JVM ecosystem, **Nimbus JOSE + JWT** là một thư viện có thể xử lý JOSE/JWS/JWE thay vì tự ghép JSON và primitives mật mã. Ví dụ sau minh họa **issuance** của signed JWT được mã hóa cho một recipient:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.RSAEncrypter;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

public final class SignThenEncryptIssuer {
    private SignThenEncryptIssuer() {}

    public static String issue(
            JWTClaimsSet trustedClaims,
            RSAPrivateKey issuerSigningPrivateKey,
            RSAPublicKey recipientEncryptionPublicKey)
            throws Exception {

        // Lớp 1: AS ký claims -> inner JWS.
        JWSHeader jwsHeader = new JWSHeader.Builder(
                JWSAlgorithm.PS256)
            .type(new JOSEObjectType("at+jwt"))
            .keyID("as-sign-2026-11")
            .build();

        SignedJWT signed = new SignedJWT(jwsHeader, trustedClaims);
        signed.sign(new RSASSASigner(issuerSigningPrivateKey));

        // Lớp 2: mã hóa nguyên JWS cho Orders RS -> outer JWE.
        JWEHeader jweHeader = new JWEHeader.Builder(
                JWEAlgorithm.RSA_OAEP_256, EncryptionMethod.A256GCM)
            .contentType("JWT")
            .keyID("orders-decrypt-2026-11")
            .build();

        JWEObject encrypted = new JWEObject(
            jweHeader,
            new Payload(signed.serialize()));
        encrypted.encrypt(
            new RSAEncrypter(recipientEncryptionPublicKey));

        return encrypted.serialize(); // JWE Compact: 5 phần.
    }
}
~~~

**Phạm vi ví dụ:**

- Đây là ví dụ **chỉ minh họa composition**, giả định hai key đã được cấp từ đúng trust registries; không tự sinh key trong request.
- `trustedClaims` phải được AS tạo sau **OAuth grant/client/resource authorization**; không lấy claims bất kỳ từ request và ký luôn.
- Có `typ=at+jwt` ở inner JWS **không tự chứng minh mọi yêu cầu RFC 9068 đã đạt**; profile phải được validator kiểm riêng.
- Private signing key và private recipient decryption key **không ở cùng một service trong kiến trúc thật**.
- API của Nimbus có thể thay đổi theo version; cần compile/integration test theo dependency của dự án. Không copy snippet để phát token production mà thiếu KMS/HSM, key-size/policy, time/audience/TTL và error handling.

### 12.1. Khi serializing, cái nào là ciphertext?

~~~text
inner = SignedJWT(...).serialize()
  => compact JWS, chứa claims + signature

outer = JWEObject(payload = inner).encrypt(...)
  => compact JWE, payload inner trở thành ciphertext

deliver = outer.serialize()
~~~

Client nhận **outer JWE**, không cần private key để đọc inner signed JWT. Nếu client đơn thuần decode Base64url outer protected header, nó chỉ thấy `alg`, `enc`, `kid`, `cty` và metadata tương ứng.

## 13. Java 17 với Nimbus: xác minh StE an toàn

Resource Server xử lý lớp ngoài trước, lớp trong sau:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

public final class SignThenEncryptResourceServer {
    private SignThenEncryptResourceServer() {}

    public static JWTClaimsSet validateCryptographicEnvelope(
            String outerCompact,
            RSAPrivateKey trustedRecipientPrivate,
            RSAPublicKey trustedIssuerPublic) throws Exception {

        JWEObject outer = JWEObject.parse(outerCompact);
        if (!JWEAlgorithm.RSA_OAEP_256.equals(
                outer.getHeader().getAlgorithm())
                || !EncryptionMethod.A256GCM.equals(
                    outer.getHeader().getEncryptionMethod())
                || !"JWT".equals(outer.getHeader().getContentType())
                || !"orders-decrypt-2026-11".equals(
                    outer.getHeader().getKeyID())) {
            throw new SecurityException("Unapproved JWE profile");
        }

        // Phải kiểm authentication tag; thư viện từ chối khi lỗi.
        outer.decrypt(new RSADecrypter(trustedRecipientPrivate));

        // Sau decrypt mới thấy JWS; dữ liệu chưa đáng tin
        // cho tới khi verify chữ ký issuer.
        SignedJWT inner = SignedJWT.parse(
            outer.getPayload().toString());

        if (!JWSAlgorithm.PS256.equals(
                inner.getHeader().getAlgorithm())
                || inner.getHeader().getType() == null
                || !"at+jwt".equals(
                    inner.getHeader().getType().toString())
                || !"as-sign-2026-11".equals(
                    inner.getHeader().getKeyID())) {
            throw new SecurityException("Unapproved inner JWS");
        }

        if (!inner.verify(new RSASSAVerifier(trustedIssuerPublic))) {
            throw new SecurityException("Untrusted issuer signature");
        }

        // Vẫn chưa được authorize request.
        return inner.getJWTClaimsSet();
    }
}
~~~

### 13.1. Chưa có bước nào cấp quyền API ở đây

Hàm chỉ kiểm **một cấu hình nested envelope cụ thể**. Phải bổ sung JWT claim validation, max token lifetime, issuer/audience, scope/tenant, sender constraints và revocation. Đặc biệt, đầu vào `trustedIssuerPublic` phải lấy từ **trusted issuer/JWKS registry**, không từ unverified token `jku` hoặc embedded `jwk`.

### 13.2. Mẫu hard-code `kid` chỉ phục vụ minh họa

Ở production, key rotation có thể có **active key K2 và retired verify-only key K1**. Verifier phải chọn **đúng key từ allowed key set theo issuer/purpose/`kid`**, có thể chấp nhận cả K1/K2 trong overlap, nhưng không thử arbitrary keys của các issuers khác. Tương tự recipient có thể giữ private decryption keys E1 (retired decrypt-only) và E2 (active) trong một khoảng thời gian.

### 13.3. `getType()` có thể thiếu

Trong triển khai xử lý đầu vào không tin cậy, cần **null guard** rõ ràng trước khi dereference header field; không để `NullPointerException` trở thành error/trace oracle. Điều kiện trong ví dụ đã kiểm `getType() == null` trước khi gọi `toString()`. Có thể tách kiểm này thành hàm riêng:

~~~java
var innerType = inner.getHeader().getType();
if (innerType == null
        || !"at+jwt".equals(innerType.toString())) {
    throw new SecurityException("Invalid access token type");
}
~~~

Ví dụ dài ở trên ưu tiên minh họa thứ tự xử lý, **chưa phải library wrapper hardened hoàn chỉnh**. Các fields, cấu trúc nesting, token sizes và loại key vẫn phải được policy validator kiểm.

### 13.4. Không dựa vào exception type để tiết lộ nội dung

Ở API public, lỗi RSA unwrap, GCM bad tag, inner JWS parse hoặc inner signature fail đều nên dẫn tới **deny** và thông báo ngắn phù hợp token error contract; không trả plaintext, private `kid` internals hoặc stack trace cho caller. Audit backend có thể lưu **reason category** đã giảm nhạy cảm.

## 14. Java 17 với Nimbus: tạo EtS `JWS(JWE)`

Với EtS, inner JWE chứa encrypted claims và outer JWS chứa **serialized JWE** làm payload:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.JWSObject;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.RSAEncrypter;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;

public final class EncryptThenSignIssuer {
    private EncryptThenSignIssuer() {}

    public static String issueEnvelope(
            JWTClaimsSet trustedClaims,
            RSAPrivateKey issuerSigningPrivateKey,
            RSAPublicKey recipientEncryptionPublicKey)
            throws Exception {

        // Lớp 1: ciphertext về mặt JOSE.
        JWEHeader encHeader = new JWEHeader.Builder(
                JWEAlgorithm.RSA_OAEP_256, EncryptionMethod.A256GCM)
            .keyID("orders-decrypt-2026-11")
            .build();

        JWEObject inner = new JWEObject(
            encHeader,
            new Payload(trustedClaims.toString()));
        inner.encrypt(
            new RSAEncrypter(recipientEncryptionPublicKey));

        // Lớp 2: ký nguyên compact JWE làm JWS payload.
        JWSHeader signHeader = new JWSHeader.Builder(
                JWSAlgorithm.PS256)
            .contentType("JWT")
            .keyID("as-sign-2026-11")
            .build();

        JWSObject outer = new JWSObject(
            signHeader,
            new Payload(inner.serialize()));
        outer.sign(new RSASSASigner(issuerSigningPrivateKey));

        return outer.serialize(); // JWS Compact: 3 phần.
    }
}
~~~

**Quan trọng:** Đoạn này minh họa **một application-specific EtS envelope**, không tự là một RFC 9068 JWT access token profile được mọi Resource Servers hỗ trợ. Hai phía phải thống nhất cách phân loại EtS, claims serialization, `typ`/`cty` và allowed algorithms. Nếu thư viện/framework của RS chỉ nhận signed JWT access token thông thường, **nó sẽ không tự lấy claims từ inner JWE**.

### 14.1. Không được ký plaintext đã bị sửa “sau khi decrypt” mà bỏ outer context

Issuer ký **inner JWE Compact Serialization**. Một consumer không thể decrypt, serialize lại JSON claims theo format tùy ý rồi dùng signature của outer JWS để verify plaintext ấy; **chữ ký không được tạo trên plaintext**.

### 14.2. Encrypt trước rồi ký có ưu điểm gì?

Một gateway được phép verify public issuer signature có thể kiểm outer JWS trước khi phải chuyển payload tới RS có decryption key. Gateway **không cần thấy nội dung**; nhưng cũng **không được suy mình đã xác minh claims hoặc quyền**.

## 15. Java 17 với Nimbus: xác minh EtS đúng thứ tự

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;

import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSObject;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.JWTClaimsSet;

public final class EncryptThenSignResourceServer {
    private EncryptThenSignResourceServer() {}

    public static JWTClaimsSet validateCryptographicEnvelope(
            String outerCompact,
            RSAPublicKey trustedIssuerPublic,
            RSAPrivateKey trustedRecipientPrivate) throws Exception {

        JWSObject outer = JWSObject.parse(outerCompact);
        if (!JWSAlgorithm.PS256.equals(
                outer.getHeader().getAlgorithm())
                || !"JWT".equals(
                    outer.getHeader().getContentType())
                || !"as-sign-2026-11".equals(
                    outer.getHeader().getKeyID())) {
            throw new SecurityException("Unapproved outer JWS");
        }

        // Outer issuer signature: verify TRƯỚC decrypt.
        if (!outer.verify(
                new RSASSAVerifier(trustedIssuerPublic))) {
            throw new SecurityException("Untrusted issuer signature");
        }

        JWEObject inner = JWEObject.parse(
            outer.getPayload().toString());
        if (!JWEAlgorithm.RSA_OAEP_256.equals(
                inner.getHeader().getAlgorithm())
                || !EncryptionMethod.A256GCM.equals(
                    inner.getHeader().getEncryptionMethod())
                || !"orders-decrypt-2026-11".equals(
                    inner.getHeader().getKeyID())) {
            throw new SecurityException("Unapproved inner JWE");
        }

        inner.decrypt(new RSADecrypter(trustedRecipientPrivate));

        // JSON claims mới được đọc sau verify outer signature
        // VÀ decrypt/verify tag inner JWE.
        return JWTClaimsSet.parse(inner.getPayload().toString());
    }
}
~~~

### 15.1. EtS không cho phép bỏ kiểm plaintext claims

Chữ ký outer và AES-GCM tag inner **đều đúng** vẫn chưa chứng minh user được truy cập Orders API. Sau khi hàm trả `JWTClaimsSet`, phải kiểm `iss` đúng AS, `aud` đúng Orders API, `exp`/`nbf`, scope, revocation và object-level authorization.

### 15.2. Khẳng định nguồn bằng key lẫn claims

Nếu header outer dùng AS key K1 nhưng plaintext claim `iss` viết issuer B, **không coi B đã phát token**. Issuer identity phải được ràng buộc với **actual trusted outer signer** và được so sánh với claim trong plaintext. Chữ ký xác minh đúng key A không hợp thức hóa `iss=B`.

### 15.3. Không trộn EtS verifier và StE verifier tùy tiện

Một RS chỉ cho phép StE phải từ chối outer JWS chứa JWE nếu profile chưa hỗ trợ. Nếu RS hỗ trợ cả hai, nên **phân luồng rõ theo allowed profile và endpoints**, không thử decrypt rồi sign, sign rồi decrypt, plaintext JWT và opaque token liên tục cho tới khi một nhánh “thành công”. Những fallback mơ hồ tạo nguy cơ **algorithm confusion và cross-format token substitution**.

## 16. Java: kiểm claims sau khi cả hai lớp mật mã đạt

Một validator dùng chung cho các kết quả đã được **trusted cryptographic verifier** xác minh có thể được thiết kế như sau. Đây vẫn là **mẫu policy**; profile RFC 9068 và token storage/revocation còn cần xử lý riêng.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import com.nimbusds.jwt.JWTClaimsSet;

public final class OrdersClaimsPolicy {
    private static final String ISSUER =
        "https://auth.example.com";
    private static final String AUDIENCE =
        "https://api.example.com/orders";
    private static final Duration MAX_LIFETIME =
        Duration.ofMinutes(15);
    private static final Duration SKEW =
        Duration.ofSeconds(30);

    private OrdersClaimsPolicy() {}

    /** Chỉ gọi sau khi SIGNATURE và ENCRYPTION layers đã verify. */
    public static void validate(JWTClaimsSet claims, Instant now) {
        if (!ISSUER.equals(claims.getIssuer())) {
            throw new SecurityException("Invalid issuer");
        }
        if (claims.getAudience() == null
                || !claims.getAudience().contains(AUDIENCE)) {
            throw new SecurityException("Invalid audience");
        }

        Date issuedAt = claims.getIssueTime();
        Date notBefore = claims.getNotBeforeTime();
        Date expiresAt = claims.getExpirationTime();

        if (issuedAt == null || expiresAt == null) {
            throw new SecurityException("Missing required time claim");
        }
        Instant iat = issuedAt.toInstant();
        Instant exp = expiresAt.toInstant();

        if (!exp.isAfter(now.minus(SKEW))) {
            throw new SecurityException("Expired token");
        }
        if (iat.isAfter(now.plus(SKEW))) {
            throw new SecurityException("Token issued in future");
        }
        if (notBefore != null
                && notBefore.toInstant().isAfter(now.plus(SKEW))) {
            throw new SecurityException("Token not yet active");
        }
        if (!exp.isAfter(iat)
                || Duration.between(iat, exp).compareTo(
                    MAX_LIFETIME) > 0) {
            throw new SecurityException("Disallowed token lifetime");
        }
    }
}
~~~

**Điều chưa được thực hiện trong mẫu trên:** kiểm `scope`/authorities, `typ`, grant/principal, `client_id`, tenant, owner, revocation/denylist, DPoP/mTLS sender constraint và các RFC 9068 profile claims khác. Ngoài ra, một ứng dụng có thể chọn **clock skew nhỏ hơn hoặc bằng 0** tùy SLA; 30 giây chỉ là ví dụ. Nên tận dụng framework validators chuẩn thay vì thay toàn bộ bằng custom code.

### 16.1. Lỗi trong claim validator không nên để lộ crypto details

Response API có thể là `401 invalid_token` khi token không được chấp nhận hoặc `403 insufficient_scope` khi principal đã xác thực nhưng thiếu quyền theo contract; đừng gửi nguyên JWT, key IDs, inner claims, stack traces hoặc sai khác decrypt/signature để attacker thăm dò.

### 16.2. Authorization trên object là kiểm tra khác

Một token đạt hai lớp mật mã và `scope=orders.read` chưa có nghĩa được xem mọi order:

~~~sql
SELECT id, total, status
FROM orders
WHERE id = :requested_order_id
  AND tenant_id = :verified_authorized_tenant;
~~~

`:verified_authorized_tenant` phải đến từ principal/entitlement đã kiểm, không lấy từ một `X-Tenant-Id` header caller có thể giả. Chống **Broken Object Level Authorization** cần business policy và data-layer enforcement.

## 17. Quản lý khóa khi dùng cả signing và encryption

Một token StE hoặc EtS có thể phụ thuộc **hai cặp khóa và hai lịch rotation**:

~~~text
AS:
  signing private key Ksign-active
  signing public keys Ksign-active + Ksign-retired trên JWKS

Orders RS:
  recipient private decryption key Kenc-active
  recipient retired decrypt-only key Kenc-old (nếu còn JWE cũ)

AS cần biết:
  registered recipient PUBLIC encryption key

RS cần biết:
  trusted issuer PUBLIC signing keys
~~~

### 17.1. Signing-key rotation

Giả sử AS chuyển từ **S1** sang **S2**:

1. Publish public signing key **S2** đến issuer JWKS trước cutover.
2. Chờ RS/clients nhận S2 theo refresh/rollout policy.
3. AS ngừng ký mới bằng private **S1**, bắt đầu ký bằng **S2**.
4. RS tiếp tục verify inner/outer JWS ký S1 trong **overlap** nếu token còn hạn và key không bị compromise.
5. Sau *actual last S1 issuance + max token lifetime + clock/operations margin*, ngừng tin S1.

Đối với StE, S1/S2 thuộc **inner JWS**. Đối với EtS, S1/S2 thuộc **outer JWS**. **Ký bằng key nào không thay đổi recipient decryption key**, trừ khi hệ thống chủ động rotate đồng thời.

### 17.2. Encryption-key rotation

Giả sử Orders RS chuyển từ recipient encryption/decryption pair **E1** sang **E2**:

1. RS chuẩn bị private decryption key **E2** an toàn trong KMS/HSM.
2. AS nhận/đăng ký **public encryption key E2** qua trust registry đã xác thực.
3. AS bắt đầu encrypt JWE mới cho E2.
4. RS giữ private **E1** ở trạng thái **decrypt-only** cho các JWE cũ còn hạn.
5. Sau khi ciphertext/token E1 không còn phải được chấp nhận, ngừng decrypt và archive/destroy E1 theo policy.

**Không xóa E1 quá sớm chỉ vì S1 đã retired**. Chữ ký và mã hóa có thời hạn, đối tượng sử dụng và điểm bắt đầu cutover khác nhau.

### 17.3. Hai key IDs khác nhau có thể xuất hiện trong một token

~~~text
StE:
  Outer JWE kid=orders-enc-E2
  Inner JWS kid=auth-sign-S1

EtS:
  Outer JWS kid=auth-sign-S2
  Inner JWE kid=orders-enc-E1
~~~

Các kết hợp trên **có thể hợp lệ trong overlap** nếu key policies cho phép. Không đánh dấu token invalid chỉ vì `kid` signing và `kid` decryption không cùng “phiên bản tháng 11”. Ngược lại, không tự chấp nhận key cũ khi trust state đã chuyển sang **DISABLED** do compromise.

### 17.4. Private signing key và private decryption key cần tách quyền

| Workload | Quyền nên có | Không nên có |
| --- | --- | --- |
| **AS issuer** | KMS **Sign** bằng active signing key; lấy public recipient encryption key | Export recipient private decryption key |
| **Orders RS** | KMS **Decrypt/Unwrap** bằng recipient key; đọc issuer public JWKS | KMS **Sign** bằng AS private signing key |
| **Key custodians/security** | Approve rotation/distrust, audit permissions | Tự động có quyền export private keys |
| **OAuth client** | Lưu/truyền access token đúng cách | AS private signer hoặc RS private decrypt key |

Với KMS/HSM, một API `Sign`/ `Decrypt` có thể được cấp mà không cho export key material. Chỉ cấp đúng operation, có audit, quy định key deletion/backup và hạn chế những service có thể gọi key-operation endpoints.

### 17.5. Compromised signing key và compromised decryption key khác hậu quả

- **Lộ private signing key:** Attacker có thể tạo JWS/outer signature hợp lệ cho forged tokens. Cần **emergency distrust** signer key trên RS, không chờ normal overlap.
- **Lộ private decryption key:** Attacker có thể đọc nội dung JWE đã thu thập (kể cả quá khứ nếu có ciphertext) dùng key đó. Cần rotation và đánh giá **confidentiality breach**; nếu attacker chỉ có decryption key, họ **không tự có AS signing capability**.
- **Lộ cả hai:** Có thể vừa forged issuer evidence, vừa giải mã token; tác động kết hợp nghiêm trọng và cần cô lập trust domain.

**Không thể “mã hóa lại JWT cũ” để xóa dữ liệu attacker đã giải mã được sau khi private key lộ.** Key rotation phòng tiếp tục lộ dữ liệu mới nhưng không khôi phục confidentiality của bản sao quá khứ.

## 18. Encryption không thay TLS hoặc bảo vệ nơi lưu token

Giả sử:

~~~text
Browser -> HTTPS -> API gateway -> mTLS -> Orders RS
               outer JWE token trong Authorization header
~~~

JWE có thể giữ claims kín khỏi gateway nếu gateway không giữ recipient decryption key. Nhưng **gateway vẫn nhìn được toàn chuỗi JWE token**; nếu bị log hoặc sao chép, attacker có thể trình lại ciphertext như Bearer token.

### 18.1. Phân biệt TLS và JWE

| Cơ chế | Bảo vệ | Không giải quyết |
| --- | --- | --- |
| **TLS/HTTPS** | Confidentiality/integrity giữa hai TLS endpoints | Token trong logs/memory sau termination, compromised endpoints |
| **JWE** | Confidentiality của JOSE plaintext cho recipient | Bearer replay, quyền tài nguyên, lỗi key custody |
| **JWS** | Signature/integrity theo trusted issuer key | Giấu payload hoặc chống replay của nguyên token |
| **Disk/DB encryption** | Storage media/backups theo key boundary | App bị compromise có quyền decrypt, JWT validation |
| **DPoP/mTLS binding** | Hạn chế token-only replay khi proof/cert được kiểm | Grant đã bị revoke, business authorization |

### 18.2. Không lưu token trong URL

Sai:

~~~http
GET /download?access_token=<outer-JWE-compact> HTTP/1.1
Host: reports.example.com
~~~

Token có thể nằm trong access logs, browser history, referer hoặc analytics. **Dù nội dung JWE không đọc được, toàn chuỗi vẫn là credential**. Ưu tiên transport đúng OAuth profile, ví dụ `Authorization: Bearer` qua HTTPS; với DPoP phải gửi đúng proof/header tương ứng.

### 18.3. Quy tắc lưu access/refresh token

Ứng dụng backend/BFF có thể giữ tokens server-side và browser nhận cookie session `HttpOnly`, `Secure`, `SameSite` theo risk/CSRF model. Native apps dùng OS secure storage. Public SPAs phải đánh giá XSS, persistent storage và refresh-token policies. **Encrypting JWT không biến `localStorage` thành chỗ an toàn tuyệt đối** và không phòng attacker thực thi JavaScript trong origin.

### 18.4. Giới hạn kích thước HTTP header/cookie

Nested JWS/JWE tạo overhead:

- Hai JOSE headers, key IDs và các Base64url encodings;
- Chữ ký JWS;
- JWE encrypted key, IV và authentication tag;
- Có thể có chứng chỉ/x5c/JWK metadata (tránh nhúng không cần thiết).

Một access token trở nên lớn có thể vượt giới hạn `Authorization` header ở gateway, CDN hoặc service mesh, gây `400`, `431 Request Header Fields Too Large` hoặc lỗi proxy. **Đo serialized length thực trên đường triển khai**, không suy “claims JSON chỉ 200 bytes nên token chắc chắn nhỏ”.

### 18.5. Không tăng tính bảo mật bằng nén vô điều kiện

Một số JWE có `zip` nhưng **compression cùng dữ liệu bí mật và dữ liệu attacker-controlled** có thể mở rủi ro length oracle; decompression không giới hạn tạo DoS. Khi nested token đã đủ lớn, ưu tiên **giảm claims**, opaque token/introspection hoặc thiết kế protocol khác trước khi bật compression.

## 19. Token revocation và replay sau sign/encrypt

**Không thay đổi**: nếu token là Bearer credential, attacker giữ chuỗi outer JOSE có thể gửi lại nhiều lần trong lifetime hợp lệ.

### 19.1. JWT có chữ ký và mã hóa vẫn không tự biết đã bị revoke

AS có thể revoke grant/refresh token lúc 10:05 nhưng Orders RS đã nhận JWT trước đó với `exp=10:15`. Nếu RS chỉ verify/decrypt offline, JWT vẫn có thể được chấp nhận đến khi hết hạn. JWE hoặc thêm chữ ký bên ngoài **không mang tin tức revoke mới**.

Các cơ chế bổ sung có thể gồm:

- Access token TTL ngắn phù hợp threat model;
- Denylist theo trusted issuer + token `jti`/HMAC fingerprint;
- Session/grant version được RS kiểm từ authority đáng tin;
- RFC 7662 introspection hoặc online authorization cho resource nhạy cảm;
- Event-driven revocation propagation có kiểm soát consistency/cache/partition;
- DPoP/mTLS sender-constrained access tokens để giảm replay nếu chỉ token bị copy.

### 19.2. Refresh token rotation là chuyện khác

Refresh token dùng tại AS/token endpoint, thường có rotation/reuse detection và client binding riêng. Dù refresh token được JWS/JWE bảo vệ, **old rotated refresh token** vẫn cần được AS từ chối theo state/family policy. Không suy vì JWT có `jti` nên access token cũng chỉ được dùng một lần.

### 19.3. Sender constraint và nested JWT

Nếu access token có sender confirmation claim `cnf` và DPoP/mTLS binding theo profile, RS phải thực thi **proof/certificate check riêng** sau khi đã xác minh token:

~~~text
Nested access token validated cryptographically
  + correct aud/scope/time
  + DPoP proof signature, htm, htu, iat, jti, ath
  + token cnf.jkt matches DPoP key
  + replay cache and nonce policy
  + tenant/resource authorization
    -> may allow request
~~~

**Decrypting JWE không phải sender proof**. Người cầm ciphertext có thể không có quyền đọc claims, nhưng nếu token vẫn là Bearer, họ vẫn có thể trình token. Sender-constrained tokens làm rõ **ai có thể sử dụng token**, không chỉ ai có thể **đọc claims**.

### 19.4. Key rotation không phải revoke token

Normal rotation chuyển active signing key S1→S2 và recipient decryption key E1→E2 thường vẫn giữ khả năng verify/decrypt token cũ. **Thu hồi khẩn cấp** private signer key hoặc token compromise cần quy trình distrust/denylist riêng, không nhầm với việc chỉ đổi key cho issuance mới.

## 20. An toàn trước lỗi decrypt/verify và các dạng oracle

Một attacker có thể gửi hàng nghìn token có header/ciphertext tùy ý và quan sát:

~~~text
Response A: RSA padding invalid
Response B: GCM tag invalid
Response C: Signature invalid for K1
Response D: Audience invalid, user exists
Response E: 200
~~~

Nếu API để lộ lỗi khác nhau về message/timing/status, attacker có thể khai thác **format, key selection, padding/decryption oracles, user enumeration** hoặc resource exhaustion.

### 20.1. Fail closed theo từng lớp

~~~text
STe:
  bad JWE alg/key/tag -> deny
  bad inner JWS signature -> deny
  invalid claims -> deny
  revoked token -> deny

EtS:
  bad outer JWS signature -> deny
  bad inner JWE alg/key/tag -> deny
  invalid claims -> deny
  revoked token -> deny
~~~

Không có nhánh:

~~~java
// MẪU SAI — KHÔNG SỬ DỤNG:
try {
    validateNestedToken(token);
} catch (Exception error) {
    return allowForAvailability();
}
~~~

Nếu KMS/HSM/JWKS unavailable, ứng dụng có thể trả dependency error (`503`) hoặc token error theo contract, nhưng **không cho phép hành động cần kiểm token khi các bước bắt buộc chưa thành công**.

### 20.2. Cần giới hạn các lựa chọn parser

Cho một endpoint, hãy xác định:

- **Allowed outer type** (JWE StE hoặc JWS EtS), không tự nhận mọi serialization;
- Allowed inner object type/nesting depth;
- Allowed `alg`, `enc`, curves, key IDs và key strengths;
- Maximum token byte length, decompressed size, JSON nesting/depth, header size;
- Maximum key lookup/refresh attempts;
- Không tải arbitrary external URLs trong JOSE header;
- Không log raw token, decrypt plaintext hay private key vào lỗi/traces.

### 20.3. Thời điểm xác minh quan trọng

**StE:** Không đọc/áp claims trước **decrypt + inner signature verification**. Có thể phải decrypt trước khi xác thực issuer, nên cần hardened decryption path.

**EtS:** Verify **outer signature** trước khi decrypt; không tin inner plaintext cho đến khi decryption tag và claims validation đạt. Không gọi một method `signatureVerified()` rồi tự dựng security principal.

### 20.4. Xử lý lỗi dành cho client và logs

| Tình trạng | Quyết định bảo mật | Ghi nhận nội bộ |
| --- | --- | --- |
| Bad outer/inner signature | Từ chối token | `signature_invalid`, known issuer alias |
| Bad JWE auth tag/decryption | Từ chối token | `decrypt_failed`, recipient key alias |
| Unsupported alg/enc/cty | Từ chối token | `profile_not_allowed` |
| Wrong `aud`/expired | Từ chối token | `audience_mismatch`/`expired` |
| Valid token nhưng thiếu scope | Từ chối resource action | `insufficient_scope` |
| KMS/JWKS unavailable | Fail closed | `crypto_dependency_unavailable` |
| Revocation state unavailable khi bắt buộc | Fail closed | `revocation_state_unavailable` |

**Không trả raw `kid` do attacker đặt làm metric label** hoặc tiết lộ “private key E1 tồn tại nhưng decrypt sai”. Internal logs cần redaction, correlation ID không phải credential và retention phù hợp.

## 21. Vận hành qua gateway, BFF và nhiều Resource Servers

Giả sử một token phải đi qua:

~~~text
Browser / Mobile Client
        |
      HTTPS
        v
API Gateway
        |
       mTLS
        v
Orders Resource Server
        |
        v
Orders Database
~~~

### 21.1. Với StE, gateway thường không verify inner JWS được

Gateway không có decryption key của RS sẽ không thấy inner signed JWT. Nó có thể kiểm **TLS, rate limits, token syntax/size, client certificate, route** hoặc dùng một authority khác nếu kiến trúc có. Nó **không nên gắn “token verified”** khi chưa kiểm inner issuer signature/claims.

Nếu gateway cần xác minh claims chính xác trước khi route, cân nhắc opaque token/introspection, trusted token exchange hoặc kiến trúc gateway được cấp quyền decrypt (có trade-off riêng) thay vì chia RS private decryption key tùy tiện.

### 21.2. Với EtS, gateway verify outer JWS nhưng không có full authorization

Gateway có thể xác minh outer issuer signature, giảm traffic rác đến decryption service. Nhưng không thấy audience/scope nếu claims nằm trong inner JWE. Nó không có đủ dữ liệu để quyết định user được xem order nào. **Orders RS phải decrypt, validate claims và kiểm quyền tài nguyên**.

### 21.3. Nếu gateway và RS đều có private decryption key?

Đó là một **trust expansion**: cả gateway lẫn RS có thể đọc claims. Cần xác định ai được phép đọc PII/claims, quyền truy cập KMS, audit, isolation và re-encryption/token exchange. **Không chia private key chỉ để “debug dễ hơn”**.

### 21.4. Một token cho hai Resource Servers?

Nếu AS encrypt JWE cho public key Orders RS, Payments RS không có private key Orders và **không giải mã được**. Nếu nghiệp vụ cần nhiều recipients, có thể xem xét **JWE JSON Serialization với nhiều recipients** hoặc **phát riêng token theo audience/resource**. Không tự cho rằng một JWE Compact có thể được giải mã bởi mọi services có public JWKS issuer.

Trong OAuth, **resource indicators** và audience-scoped tokens thường giúp giảm token misuse hơn việc phát một token có `aud` quá rộng rồi đưa decryption key cho nhiều RS.

### 21.5. Cached authorization không được vượt `exp`

Một gateway/RS có thể cache kết quả xác minh hoặc introspection, nhưng cache không được làm token có hiệu lực vượt `exp`/revocation SLA. Không coi “outer JWS verify lần đầu” là một server-side session vô hạn cho mọi request sau.

### 21.6. Độ trễ và khả năng mở rộng

StE và EtS đều phát sinh:

- Xử lý JOSE hai lớp;
- RSA/ECDH key operations và AES-GCM tag verification;
- JWKS/public-key caching và KMS private-key access;
- Tăng bytes của token so với JWS đơn.

**Không chọn thứ tự chỉ dựa trên micro-benchmark**: kiểm cả threat model, nơi cấp quyền decrypt, key lifecycle, latency, failure domains, cache behavior và operational recovery. Khi cần confidentiality nhưng hệ thống phải xử lý hàng triệu requests mỗi giây, có thể cân nhắc opaque token/gateway/BFF architecture hoặc local decryption protected by HSM policy tùy yêu cầu.

## 22. Những sai lầm thường gặp khi kết hợp sign và encrypt

### 22.1. “JWT đã ký thì payload được giấu”

**Sai.** JWS Compact thường có payload Base64url đọc được; cần giảm claims hoặc áp confidentiality layer như JWE theo đúng recipient profile.

### 22.2. “JWE decrypt thành công nghĩa là AS chắc chắn ký token”

**Sai khi JWE dùng public-key encryption cho RS.** Bất kỳ ai biết recipient public encryption key có thể tạo một JWE hợp lệ về crypto. Phải verify **inner JWS của StE** hoặc **outer JWS của EtS** theo issuer trust policy.

### 22.3. “StE chỉ cần decrypt, không cần verify inner signature”

**Lỗ hổng token forgery.** Attacker có thể encrypt JSON claims tự chọn cho public key của RS; JWE decrypt thành công nhưng inner JWS không thuộc AS.

### 22.4. “EtS chỉ cần verify outer signature là có quyền API”

**Sai.** Outer signature ở EtS ký ciphertext envelope. Phải decrypt inner JWE và validate issuer/audience/time/scope/tenant/quyền.

### 22.5. “Hai thứ tự giống nhau vì đều có chữ ký và bản mã”

**Sai.** Khác thứ tự processing, nơi chữ ký lộ ra, khả năng verify trước decrypt và bằng chứng ký plaintext/ciphertext. Không tráo chuỗi thao tác tùy tiện mà bỏ qua profile.

### 22.6. “Encrypt rồi sign nghĩa là ký riêng ciphertext segment”

**Không đúng cho JWS(JWE) Compact như bài mô tả.** JWS ký `BASE64URL(outer_header).BASE64URL(serialized_inner_JWE)`. **Header và serialization** của outer JWS là một phần signing input.

### 22.7. “Base64url encoding là encryption”

**Sai.** Decode JWS payload không cần khóa; decode outer JWS trong EtS chỉ cho inner JWE ciphertext. Phải phân biệt encoding với crypto decryption.

### 22.8. “AES-GCM tag chứng minh issuer”

**Không mặc định.** Tag xác thực ciphertext/AAD theo key-management context. Với public-key encryption, người bất kỳ có public key recipient vẫn có thể tạo ciphertext/tag hợp lệ; cần issuer signature/trust.

### 22.9. “Dùng lại cùng AES-GCM nonce/key không sao vì payload đã signed”

**Sai nghiêm trọng.** Key/nonce reuse trong GCM có thể phá bí mật và integrity, kể cả payload bên trong có chữ ký. Phải bảo đảm nonce uniqueness theo encryption key.

### 22.10. “Có `kid` thì đó là khóa tin cậy”

**Sai.** `kid` chỉ gợi ý chọn key trong **trusted key set đúng issuer/recipient**. Không tải arbitrary `jku`/`x5u` từ JWT chưa verify.

### 22.11. “Chọn `alg` theo header rồi cho library tự xử lý”

**Sai.** `alg` và `enc` cần allowlist theo profile; không chấp nhận `none`, HS/RS confusion, weak/unapproved algorithms hoặc keys sai type.

### 22.12. “Một public/private key pair dùng cả ký và giải mã để tiết kiệm”

**Không nên mặc định.** Ký issuer và decrypt recipient là **hai key purposes khác nhau**, với quyền vận hành và nguy cơ compromise khác nhau. Tách keys theo cryptographic use và trust boundary.

### 22.13. “Mọi RSA có thể encrypt payload JWT trực tiếp”

**Sai.** RSA-OAEP có giới hạn plaintext. JWE dùng **CEK + AES-GCM** hoặc content-encryption mode tương ứng cho dữ liệu; RSA/ECDH quản lý khóa.

### 22.14. “`cty=JWT` tự chứng minh nested JWT hợp lệ”

**Sai.** `cty` giúp định tuyến parser, không làm inner signature/claims/trust tự đúng. Phải kiểm actual nested structure và token profile.

### 22.15. “Nếu inner JWE có thể decrypt thì bỏ outer JWS cũng được”

**Sai với EtS profile yêu cầu outer signature.** Tách lớp ngoài có thể làm mất issuer-authenticated provenance, mở lỗ hổng nhập claims tùy ý.

### 22.16. “Một inner JWS StE dùng được ở mọi audience sau khi decrypt”

**Sai.** JWS đã ký có `aud`, `typ`, `scope` và issuer policy; ngay cả khi giải mã hợp lệ, không dùng token Orders vào Payments.

### 22.17. “Nested JWT được mã hóa thì không cần HTTPS”

**Sai.** Ciphertext outer vẫn có thể bị **replay** khi bị đánh cắp; TLS bảo vệ transport và các header/cookie/metadata khác. Dùng HTTPS ở mọi hop.

### 22.18. “JWE token không thể bị đánh cắp vì attacker không đọc được claims”

**Sai.** Đối với Bearer token, chỉ cần **sở hữu chuỗi ciphertext credential** là có thể trình token nếu không có sender constraint/revocation.

### 22.19. “Dùng nested JWT là thu hồi token được ngay”

**Sai.** RS verify offline không thể biết revocation mới nếu không kiểm state. Cần TTL, denylist, introspection, grant/session version và fail-closed policy tương ứng.

### 22.20. “Một framework JWT decoder tự hỗ trợ mọi JWE/JWS nesting”

**Sai.** Spring Security JWT decoder phổ biến kiểm **signed JWT JWS**. Để nhận JWE(JWS) hoặc JWS(JWE), cần tích hợp JOSE processing và authentication converter có kiểm toàn bộ layers. Không coi JWT parse thành công là accepted access token.

### 22.21. “Khi KMS/JWKS lỗi, cho phép JWT cũ để tránh mất uptime”

**Nguy hiểm.** Nếu không xác minh được key/trust theo policy bắt buộc, phải **fail closed** hoặc dùng cache còn hiệu lực đã được duyệt; không tự allow claims từ token chưa verify.

### 22.22. “Signing key rotation là encryption key rotation”

**Sai.** AS signer S1→S2 và recipient decryption E1→E2 có lịch độc lập. StE/EtS token có thể đồng thời mang signing `kid=S1` và recipient `kid=E2` hợp lệ trong overlap.

### 22.23. “JWE có `alg=dir` nghĩa là payload không được mã hóa”

**Sai.** `dir` là direct use of shared CEK; JWE payload vẫn được mã hóa theo `enc`, với encrypted-key segment rỗng trong Compact.

### 22.24. “Encrypt nhiều lớp càng tốt, không cần giới hạn nesting”

**Sai.** Unbounded nesting/recursion, huge headers và compression có thể gây DoS và format confusion. Chỉ nhận đúng số lớp và serialization đã định nghĩa.

## 23. Các tình huống thực tế để chọn thứ tự

**Tình huống A — AS phát access token cho Orders RS, client không được thấy claims.**

AS ký claims bằng private signing key, rồi mã hóa inner JWS cho public encryption key Orders. Client chuyển JWE đến RS.

**Phân tích:** StE **JWE(JWS)** phù hợp khi cần giấu cả signed payload khỏi client; RS decrypt rồi verify issuer signature, xét audience/scope/expiry. Không dùng JWE nếu một opaque access token/introspection đáp ứng mục tiêu đơn giản hơn.

**Tình huống B — Gateway chỉ được kiểm AS đã ký payload, không được xem `sub`/scope.**

Gateway có trusted AS public verification key nhưng không có Orders private decryption key.

**Phân tích:** EtS **JWS(JWE)** có thể cho gateway verify outer JWS trên ciphertext trước khi chuyển xuống RS. Gateway **không được cho phép order action** vì chưa thấy plaintext claims.

**Tình huống C — RS chỉ decrypt StE rồi đọc `scope=orders.write`.**

Attacker dùng public key RS tạo JWE bao một JWS tự ký `scope=orders.write`.

**Phân tích:** Nếu RS bỏ verify inner issuer signature, attacker có thể tự cấp quyền. Cần verify trusted AS signing key sau decrypt, không chỉ parse payload.

**Tình huống D — RS chỉ verify outer EtS rồi trả về dữ liệu.**

Outer JWS signature đúng nhưng inner claims đã hết hạn hoặc `aud=payments-api`.

**Phân tích:** Signature trên ciphertext không thay plaintext token validation. RS phải decrypt inner JWE rồi kiểm claims và business authorization.

**Tình huống E — Trình tự JOSE bị client đảo ngược.**

AS gửi StE outer JWE, nhưng RS giả định outer JWS và cố đọc claims qua JWS parser.

**Phân tích:** Phải từ chối lỗi profile, không fallback thử mọi biến thể cho tới khi một parser chấp nhận. Định nghĩa endpoint/allowed outer types rõ.

**Tình huống F — Client giữ bản sao encrypted access token từ logs.**

Attacker lấy JWE Compact, không đọc được claims, nhưng trình `Authorization: Bearer <JWE>` tới Orders RS.

**Phân tích:** Nếu token Bearer còn active, RS vẫn có thể chấp nhận. Cần redaction, TTL, revoke và sender-constrained token nếu phù hợp.

**Tình huống G — Signing private key AS bị lộ.**

Attacker ký được inner JWS (StE) hoặc outer JWS (EtS) tùy profile, rồi encrypt cho public key RS.

**Phân tích:** Compromise issuer signing key tạo khả năng forged tokens. Phải emergency distrust key và audit acceptance, không chỉ rotate recipient encryption key.

**Tình huống H — Recipient decryption private key RS bị lộ.**

Attacker đọc được các bản sao JWE được encrypt cho key đó nhưng chưa có AS signing private key.

**Phân tích:** Confidentiality breach nghiêm trọng; cần rotate E1→E2 và đánh giá dữ liệu đã lộ. Nhưng chỉ có decryption key **không tự tạo issuer signature hợp lệ** nếu signer key an toàn.

**Tình huống I — RS rotate E1 sang E2, bỏ E1 khi JWT cũ còn hạn.**

Một access token được encrypt bằng E1 chưa quá `exp` nhưng RS không decrypt được.

**Phân tích:** Cần **decrypt-only overlap** hoặc chủ động reissue/expire token E1 theo contract. JWE key rotation khác public JWS verification-key overlap.

**Tình huống J — AS rotate signing S1 sang S2, RS giữ cả public keys.**

Token mới S2 và token cũ S1 (còn hạn) được xử lý cùng lúc.

**Phân tích:** Đây có thể là normal rotation. Kiểm `kid` trong trusted issuer key set, `exp` và profile; không chấp nhận S1 nếu đã bị emergency distrust.

**Tình huống K — Attacker đặt `jku=https://attacker.example/jwks` trong outer JWS.**

Ứng dụng tự tải khóa từ URL header rồi verify.

**Phân tích:** Key-injection/SSRF. Chỉ dùng trusted issuer JWKS URI/registry và bounded refresh; `kid`/ `jku` do token khai không mở trust mới.

**Tình huống L — Attacker tạo JWE `enc` không nằm allowlist.**

Parser thư viện có hỗ trợ thuật toán đó nhưng ứng dụng chưa review.

**Phân tích:** Từ chối theo algorithm policy, dù decrypt library có thể xử lý. Không bật một thuật toán chỉ vì runtime đã support.

**Tình huống M — ID token ký hợp lệ được bọc nested JWE.**

Ứng dụng gửi ID token đến Orders API; RS decrypt/verify signature thành công.

**Phân tích:** Không phải access token. RS phải kiểm token type/`aud=orders-api`/scope; ID token `aud=client_id` dùng cho OIDC client, không thay OAuth access token.

**Tình huống N — Claims chứa PII lớn, token vượt gateway header limit.**

JWT JWS dài được bọc JWE, tổng serialized token vượt mức header được hỗ trợ.

**Phân tích:** Dùng data minimization, opaque token hoặc phân quyền qua backend lookup; không bật compression vô điều kiện, giảm nesting cần thiết và kiểm kích thước trước deploy.

**Tình huống O — Một JWE được tạo cho Orders nhưng gửi Payments API.**

Payments không có private decryption key Orders; attacker thử dùng Orders key ID qua header.

**Phân tích:** Phải từ chối recipient mismatch. Nếu Payments có thể decrypt bằng key dùng chung, **vẫn phải từ chối** nếu `aud` không cho Payments. Không dùng chung key một cách tùy tiện.

**Tình huống P — Issuer ký inner JWS, nhưng client khác được phát token dành cho user A.**

Token `sub=user-A`, `aud=orders-api` và scope hợp lệ nhưng caller có quyền đối tượng khác.

**Phân tích:** JOSE chỉ bảo đảm cryptographic claims; RS vẫn cần authorization trên order/tenant và context. Token theft có thể xảy ra ngay cả khi signer và encryption keys an toàn.

**Tình huống Q — EtS outer signature được gateway verify, backend bỏ kiểm vì “gateway đã xác thực”.**

Backend nhận plaintext sau một decryption component trung gian, không có chứng cứ authenticated delegation và dùng `X-User-Id` do caller có thể tự đặt.

**Phân tích:** Gateway-to-backend trust phải xác thực và ràng buộc principal/claims, có thể bằng mTLS/signed internal assertion hoặc verification end-to-end. Không tin headers do client chèn.

**Tình huống R — JWE decrypt rồi giải nén dữ liệu không giới hạn.**

Attacker tạo encrypted compressed payload có tỷ lệ nén rất cao để gây cạn RAM.

**Phân tích:** Giới hạn input/decompressed size, supported `zip`, nesting depth và resource budget; không nhận bất kỳ inner type nào tùy ý.

**Tình huống S — Key quản lý dùng chung HS256 secret giữa các RS.**

Một verifier có shared secret MAC và có thể tạo chữ ký/MAC giống issuer.

**Phân tích:** Không có public-only verifier với HS256. Cân nhắc asymmetric JWS khi cần nhiều trust domains và signing chỉ thuộc AS.

**Tình huống T — User logout và AS revoke refresh token nhưng access JWE còn hạn.**

RS verify/decrypt access token offline, không kiểm revoke state.

**Phân tích:** Nested token không tự biết logout. Cần TTL ngắn, denylist/introspection/session version hoặc policy khác để có guarantee thu hồi cụ thể.

**Tình huống U — Outer JWT `cty=JWT` nhưng nội dung không có inner JOSE đúng.**

Attacker dùng header đúng nhưng payload ngẫu nhiên/hàng trăm lớp mã hóa lồng nhau.

**Phân tích:** Header không phải bằng chứng cấu trúc; parser phải kiểm nesting/profile/size và từ chối sai format.

**Tình huống V — Một auditor cần chữ ký trực tiếp trên claims đã giải mã.**

Auditor có thể decrypt được JWE, nhưng outer EtS signature chỉ trên serialized ciphertext, không có signed plaintext artifact.

**Phân tích:** Cân nhắc StE hoặc một cơ chế chứng thực plaintext được thiết kế cho audit. Không dùng outer ciphertext signature và khẳng định nó ký trực tiếp JSON claims.

## 24. Đừng nhầm thứ tự nested JWT với “encrypt-then-MAC” ở tầng primitives

Trong tài liệu mật mã, cụm **Encrypt-then-MAC (EtM)** thường nói tới một cách **kết hợp symmetric encryption và Message Authentication Code**: mã hóa plaintext trước, sau đó MAC ciphertext theo construction được chứng minh an toàn. Nó là khái niệm khác với câu hỏi **“JWS nằm trong JWE hay JWE nằm trong JWS?”** ở tầng JOSE application objects.

### 24.1. Tại sao hai vấn đề khác nhau?

| Câu hỏi | Tầng primitive AE | Tầng token JOSE |
| --- | --- | --- |
| Ta cần bí mật và toàn vẹn ciphertext? | Dùng AEAD/EtM construction phù hợp | JWE `enc` sử dụng content-encryption scheme đã xác thực |
| Ta cần bằng chứng issuer AS phát claims? | MAC/shared-key auth hoặc digital signature theo trust model | JWS được verify với trusted issuer signing key |
| Thứ tự ký/mã hóa là gì? | Thứ tự encrypt/MAC primitive theo security proof | StE JWE(JWS) hoặc EtS JWS(JWE) |
| Ai có thể verify chữ ký trước decrypt? | Phụ thuộc key sharing | EtS có outer JWS; StE có inner JWS bị mã hóa |

**Không suy:** “Encrypt-then-MAC là tốt nên mọi JWT phải là Encrypt-then-Sign”. Đây là hai bài toán khác nhau. JWE với AES-GCM **đã** dùng authenticated encryption để bảo vệ ciphertext. Ta còn quyết định **đặt JWS issuer signature ở đâu** trong cấu trúc nested token.

### 24.2. Không tự ghép AES-CBC và chữ ký tùy ý

Một thiết kế tự mã hóa AES-CBC rồi ký vài trường JSON mà bỏ IV/algorithm/version khỏi dữ liệu đã xác thực có thể gặp **malleability, padding oracle hoặc cross-protocol confusion**. Dùng **JOSE library và approved algorithms**, không sáng tạo token format riêng chỉ vì hiểu hai thứ tự.

### 24.3. Không dựa vào chữ ký bên ngoài để sửa lỗi GCM nonce reuse

Nếu inner JWE dùng AES-GCM và cùng **(key, IV/nonce)** được dùng lại, confidentiality/integrity có thể bị phá nghiêm trọng. Outer signature EtS có thể giúp RS từ chối ciphertext không có chữ ký AS, nhưng **không tự làm AES-GCM nonce reuse an toàn** hoặc giữ bí mật plaintext đã rò. Key/nonce lifecycle vẫn là yêu cầu riêng.

## 25. Quy trình lựa chọn đúng thiết kế

Thay vì bắt đầu bằng “cứ ký rồi encrypt”, hãy bắt đầu bằng **threat model và quyền của từng bên**:

~~~mermaid
flowchart TD
    A["Token phục vụ ai?\nAS, client, RS và gateway"] --> B{"Claims có cần giấu khỏi\nclient/hops trung gian?"}
    B -->|Không| C["Signed JWT JWS + TLS\nhoặc opaque token"]
    B -->|Có| D{"Cần chính một bên không decrypt\nverify issuer signature trước?"}
    D -->|Không| E["Ưu tiên StE:\nJWE(JWS(claims))"]
    D -->|Có| F["Cân nhắc EtS:\nJWS(JWE(claims)) với profile riêng"]
    C --> G["Kiểm audience, type,\nexpiry, scope, authorization"]
    E --> G
    F --> G
    G --> H{"Token theft, revoke,\nlarge headers, key custody?"}
    H --> I["TTL/revocation, TLS,\nsender binding, KMS, logging, tests"]
~~~

### 25.1. Nếu cần signed claims nhưng không cần giấu nội dung

**JWS signed JWT** là giải pháp đơn giản hơn. Đừng áp JWE chỉ vì cho rằng token nào “càng nhiều crypto càng an toàn”. Cần tối giản claims, sử dụng HTTPS và validators chính xác.

### 25.2. Nếu cần giấu claims khỏi client nhưng không muốn quản lý recipient private keys ở nhiều RS

Cân nhắc **opaque token + introspection**, BFF/central token exchange hoặc một **trusted gateway** có ranh giới decrypt/authorization rõ. Thay token format có thể là lựa chọn kiến trúc hợp lý hơn nested JWT.

### 25.3. Nếu chọn StE

- Inner JWS phải có issuer signature và token type đúng.
- Outer JWE phải được encrypt cho **đúng recipient**, bảo vệ AEAD tag.
- RS phải **decrypt rồi verify inner JWS** trước khi tin claims.
- Hạn chế decrypt oracle/DoS, không lộ plaintext khi signature sai.
- Ràng buộc toàn bộ key IDs, profiles, algorithms và token authorizations.

### 25.4. Nếu chọn EtS

- Inner JWE chứa claims được mã hóa cho đúng recipient.
- Outer JWS ký **serialization của inner JWE**, không phải plaintext trần.
- RS/gateway verify outer issuer signature **trước decrypt**.
- RS vẫn phải decrypt inner JWE, kiểm tag và claims/authorization.
- Không cho dùng inner JWE riêng như một issuer-authenticated access token.
- Có application profile và compatibility tests rõ ràng; không tự suy hỗ trợ RFC 9068 ở mọi framework.

### 25.5. Với nhiều tenants/resources

Ưu tiên access token có audience/resource rõ, không chia recipient private keys rộng. Nếu token cần nhiều recipients, đánh giá **JWE JSON Serialization** hoặc phát token theo từng resource/recipient; không ngầm xem JWE Compact một recipient là multi-recipient. Không dùng cùng token cho nhiều API khi `aud` không phù hợp.

## 26. Ma trận kiểm thử bảo mật StE và EtS

| Test case | Kỳ vọng |
| --- | --- |
| StE được phát bằng JWS signing key và JWE recipient key đúng | RS decrypt/verify, sau đó xét claims |
| StE inner JWS signature hợp lệ, outer JWE sai tag | Từ chối |
| StE outer JWE decrypt thành công, inner JWS signature sai | Từ chối |
| StE outer JWE decrypt thành công, inner JWS là attacker key | Từ chối issuer trust |
| StE outer JWE decrypt thành công, inner JWS không có signature (`none`) | Từ chối |
| StE outer JWE nhận inner object không phải JWS | Từ chối nesting/profile |
| StE inner JWS `typ=at+jwt` bị thiếu khi profile bắt buộc | Từ chối |
| StE inner JWS ký bằng retired key trong normal overlap | Chỉ được nhận nếu policy còn trust và token hợp lệ |
| StE inner JWS ký bằng compromised key đã distrust | Từ chối dù token còn `exp` |
| StE JWE được encrypt cho key khác Orders | Orders từ chối recipient mismatch |
| StE JWE bị đổi `kid`, `alg` hoặc `enc` | Không cho bypass; crypto/policy phải từ chối |
| StE JWE `cty` sai khi profile yêu cầu JWT | Từ chối |
| StE JWE decrypt lỗi RSA-OAEP | Không lộ chi tiết oracle hoặc plaintext |
| StE JWE decrypt lỗi GCM tag | Từ chối, không xử lý inner JSON |
| EtS outer JWS signature hợp lệ và inner JWE decrypt hợp lệ | Xét claims/authorization tiếp |
| EtS outer JWS signature sai | Từ chối **trước khi decrypt** |
| EtS outer JWS ký bởi issuer chưa tin | Từ chối |
| EtS outer JWS payload bị sửa một byte của inner JWE | Signature verification thất bại |
| EtS outer JWS `cty` sai/thiếu theo profile | Từ chối |
| EtS outer JWS alg ngoài allowlist | Từ chối |
| EtS inner JWE sai encryption key | Từ chối sau outer signature |
| EtS inner JWE GCM tag sai nhưng outer signature hợp lệ | Từ chối |
| EtS inner JWE được tách khỏi outer JWS và gửi độc lập | Không chấp nhận như access token theo EtS profile |
| EtS outer signature đúng nhưng plaintext claims sai `iss` | Từ chối |
| EtS outer signature đúng nhưng plaintext claims hết `exp` | Từ chối |
| EtS outer signature đúng nhưng claims `aud` sai | Từ chối |
| StE/EtS đúng crypto nhưng thiếu `scope` | Từ chối resource action |
| StE/EtS đúng crypto, `scope` đúng, tenant sai | Từ chối object authorization |
| StE/EtS chứa ID token gửi tới Orders API | Từ chối token type/audience |
| StE/EtS chứa JWT client assertion thay access token | Từ chối token purpose |
| StE/EtS chứa DPoP proof làm access token | Từ chối proof/token confusion |
| JWT `alg=none` xuất hiện trong lớp yêu cầu chữ ký | Từ chối |
| RSA signing public key được dùng sai làm HS256 secret | Key/alg confusion không được phép |
| JWT `jku` trỏ tới attacker-hosted JWKS | Không tải URL không tin, từ chối |
| Trùng `kid` giữa signing issuer A và B | Không chọn key sai trust domain |
| Trùng `kid` giữa JWS signing và JWE recipient | Không trộn key roles |
| AS signing S1→S2, RS chưa prefetch S2 | Deployment test phát hiện trước cutover |
| RS nhận token ký S1 trong overlap hợp lệ | Chỉ nhận theo trust policy và `exp` |
| RS nhận token ký S1 sau emergency distrust | Từ chối trên mọi nodes |
| RS rotate decryption E1→E2, JWE cũ E1 còn hạn | Decrypt-only overlap hoạt động |
| E1 private key xóa trước khi ciphertext cũ hết hạn | Lifecycle test thất bại |
| HMAC secret bị lộ nhưng vẫn được verifier tin | Threat/incident review fail |
| AES-GCM IV reuse cùng key | Crypto/security test fail |
| JWE `zip` giải nén thành payload khổng lồ | Kích thước giới hạn và từ chối |
| Nested payload tạo 20 tầng JWE/JWS | Từ chối vượt allowed depth |
| Token lớn hơn max HTTP header | Load/deployment test fail, cần thiết kế lại |
| KMS unavailable ở bước decrypt | Fail closed, không allow |
| JWKS unavailable khi chưa biết signing key | Fail closed, không skip signature |
| Opaque token được gửi tới endpoint chỉ nhận nested JWT | Từ chối format/profile; không fallback tùy ý |
| Token JWT được sign/encrypt hợp lệ nhưng đã revoke | Từ chối theo revocation policy/SLA |
| Bearer JWE bị copy và gửi lại trước expiry | Test xác nhận cần sender constraint/revocation nếu risk cao |
| DPoP-bound AT thiếu proof hoặc `ath` sai | Từ chối |
| mTLS-bound AT thiếu cert tương ứng | Từ chối |
| Gateway verify outer EtS nhưng RS bỏ authorization | Integration test **không được pass** |
| Plaintext inner claims xuất hiện trong gateway logs dù gateway không decrypt | Privacy test thất bại |
| Token/private keys xuất hiện trong application logs | Security review fail |
| HTTP (không TLS) truyền outer JWE Bearer | Security transport policy từ chối |
| 401 vs 403/503 được trả không lộ internals | Error contract đúng; truy cập vẫn bị từ chối |

### 26.1. Unit test cho tầng JOSE

Tạo **test-only keys** trong môi trường cô lập. Test:

1. Issue StE/EtS theo key registry test và serialize đúng lớp ngoài.
2. Verify/decrypt theo thứ tự yêu cầu và so expected claims.
3. Thử wrong recipient key, wrong issuer key, tampered ciphertext/tag, tampered signature.
4. Thử missing/incorrect `cty`, `typ`, `alg`, `enc`, `kid`.
5. Thử unknown `jku`, malformed inner object, vượt max nesting depth, huge payload.

**Không dùng private keys production trong unit test fixtures**, không log raw token/key khi assert thất bại.

### 26.2. Integration tests AS/RS

1. AS phát token sau khi kiểm đúng grant/client/scope/audience.
2. RS nhận đúng outer JOSE format; decrypt/verify hết các lớp.
3. RS kiểm claims/time/token type và quyền trên order/tenant.
4. Đổi issuer signing key, recipient encryption key **độc lập**.
5. Mô phỏng JWKS/KMS outage và kiểm fail closed.
6. Mô phỏng token theft/replay và revoke.
7. Kiểm gateway/broker/tracing không lộ inner claims/private keys.

### 26.3. Chạy negative tests sau mỗi lần thay library

JOSE parsers có thể thay behavior giữa versions, nhất là `typ`/`cty`, supported algorithms, key selection và JSON serialization. Khi upgrade Nimbus/Spring, test **cả token hợp lệ và token bị cố ý làm hỏng**. Không chỉ test “login vẫn được”.

### 26.4. Concurrency/scale tests

Thử nhiều RS nodes và KMS versions đồng thời:

- Load K1/K2 signing public keys, E1/E2 recipient private keys;
- JWKS cache refresh staggered, KMS failover;
- Unknown `kid` spam gây refresh storms;
- Large token/headers qua CDN, proxy, service mesh;
- Revocation propagation delay và stale authorization caches.

**Metric cần đo là yêu cầu có được cấp phép đúng sau khi hoàn tất mọi lớp và business policy**, không chỉ tỷ lệ decrypt thành công.

## 27. Checklist production: sign rồi encrypt và encrypt rồi sign

1. **Mô tả trust boundaries:** Ai là issuer, ai là recipient, client/gateway nào được xem claims, service nào được quyền ký/giải mã?
2. **Chọn profile có chủ đích:** Nếu không có yêu cầu đặc biệt, với nested JWT cần cả hai thuộc tính thường ưu tiên **JWE(JWS(claims))** theo RFC 7519; không đảo thứ tự tùy tiện.
3. **Định nghĩa outer/inner format:** StE outer JWE + inner JWS; EtS outer JWS + inner JWE; giới hạn nesting depth.
4. **Ràng buộc `typ`/`cty`:** Nested JWT phải được phân loại rõ; access token, ID token, assertion, DPoP proof không thay nhau.
5. **Algorithm allowlist độc lập:** JWS `alg`, JWE `alg` và `enc` đúng profile, key types và lengths; không nhận `none` làm signed access token.
6. **Không tin token tự cung cấp nguồn khóa:** Issuer public keys từ JWKS/registry tin cậy; recipient private key từ KMS/keystore được ủy quyền; không arbitrary `jku`/ `x5u`.
7. **Phân tách signing và decryption keys:** AS private signer không sang RS; RS private decrypt key không phát cho OAuth client/gateway tùy tiện.
8. **StE bắt buộc đủ hai lớp:** Decrypt outer JWE, kiểm tag; sau đó verify inner JWS bằng AS public key và validate claims.
9. **EtS bắt buộc đủ hai lớp:** Verify outer JWS trước, sau đó decrypt inner JWE, kiểm tag và validate claims.
10. **Không chấp nhận lớp đã tách khỏi envelope:** Inner JWE của EtS không có issuer signature nếu dùng một mình; inner JWS của StE chỉ dùng nơi profile/audience cho phép.
11. **JWS Signing Input chính xác:** Dùng JOSE library; không tự ký plaintext/ciphertext segment rồi gọi đó là JWS Compact.
12. **JWE AEAD đúng:** Nonce/IV unique theo key, tag được verify, AAD/protected header integrity, key management hợp lệ.
13. **Không tự implement JWE crypto:** Dùng thư viện được duy trì, review algorithms/crit/zip/key selection và known security advisories.
14. **Token claims tối giản:** Không nhúng password, raw client secret, private key, recovery code; cân nhắc opaque token hoặc backend lookup cho PII.
15. **Issuer/recipient binding chính xác:** Public encryption key của đúng RS; public verification key của đúng AS; kiểm issuer claim thuộc actual trusted signer.
16. **Resource authorization đầy đủ:** `iss`, `aud`, `exp`, `nbf`, `scope`, principal/client identity, tenant, row-level ownership và business policy.
17. **Max lifetime có kiểm soát:** Không để attacker có key compromised tạo JWT `exp` vô hạn; validator enforce upper bounds theo issuer profile.
18. **Bảo vệ Bearer token qua TLS:** Encryption của claims không ngăn sao chép/replay outer credential; không đưa token vào URL/logs.
19. **Refresh token policy tách biệt:** Secure storage, rotation, reuse detection, revoke family/consent/grant; không dùng refresh token ở RS.
20. **Sender constraint khi cần:** DPoP/mTLS binding và replay checks theo RFC; nested JWE không thay proof.
21. **Revocation SLA rõ:** JWT offline không tự biết revoke; dùng TTL/denylist/introspection/version và fail-closed policy nếu yêu cầu.
22. **Signing-key rotation:** Prepublish S2, chuyển ký mới, giữ S1 verify-only đủ horizon, emergency distrust khi compromise.
23. **Recipient encryption-key rotation:** Encrypt mới bằng E2, decrypt-only E1 đủ hạn, xử lý dữ liệu quá khứ khi E1 lộ.
24. **Gateway không tự suy quyền:** Verify outer EtS có thể lọc ciphertext giả, nhưng RS vẫn phải decrypt/validate quyền.
25. **Giới hạn tài nguyên:** Max token/header/claims size, nesting depth, decompressed bytes, cryptographic operation budgets và rate limits.
26. **Kiểm soát lỗi crypto:** Bad signature/tag/issuer/profile phải deny; không expose private key internals hoặc plaintext trong exception.
27. **Không fail open vì availability:** JWKS/KMS/revocation dependency lỗi không biến thành token accepted; response `503` nếu phù hợp API contract.
28. **Privacy/observability:** Không log raw access token, refresh token, inner JWS/JWE plaintext, private JWK, full DPoP proof hoặc user PII.
29. **Versioned deployment profiles:** Khi thay serialization/order, deploy producer và consumers theo rollout, không hỗ trợ fallback không được kiểm soát.
30. **Kiểm cả happy path và attack path:** Wrong recipient, wrong signer, tag tampering, outer stripping, token substitution, JWT expiry, key compromise và replay.
31. **Chứng minh compatibility:** Spring/Nimbus version thực tế có parser/validator cho đúng nested token; không dựa vào default JWT decoder cho encrypted token.
32. **Đánh giá lại nếu phức tạp quá mức:** Một signed JWT đơn giản hoặc opaque token + introspection có thể đáp ứng mục đích với ít key/risks hơn.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Trong `JWE(JWS(claims))\), khi RS nhận token, cần xử lý bước nào trước?

**Trả lời:** Kiểm profile outer JWE, **decrypt và verify AEAD tag** bằng đúng recipient key, sau đó **verify inner JWS** bằng trusted issuer signing public key. Tiếp theo kiểm claims/authorization.

**Câu 2.** Trong `JWS(JWE(claims))\), vì sao RS có thể kiểm issuer signature trước khi decrypt?

**Trả lời:** Issuer signature là **lớp ngoài**, ký serialized inner JWE. RS/gateway có issuer public key có thể verify outer JWS mà chưa cần recipient private decryption key. Nhưng chưa thể xác thực quyền nằm trong encrypted claims.

**Câu 3.** Với StE, OAuth client không đọc được claims. Có phải client cũng không thể dùng token không?

**Trả lời:** Không. Nếu token vẫn là **Bearer**, client hoặc attacker giữ nguyên outer JWE có thể trình nó tới RS mà không cần decrypt. Confidentiality và possession/replay là hai thuộc tính khác nhau.

**Câu 4.** Với EtS, một gateway verify outer signature thành công. Có được coi user đã có `scope=orders.write`?

**Trả lời:** Chưa. Gateway mới biết AS key đã ký serialized ciphertext. RS còn phải decrypt, validate `iss/aud/exp/scope`, status và business authorization.

**Câu 5.** Tại sao sign-then-encrypt thường được RFC 7519 ưu tiên?

**Trả lời:** Nó giữ JWS signature **trên chính plaintext claims** trong lớp mã hóa; bên decrypt được có thể verify signed JWT và lớp ngoài giữ kín claims/chữ ký khỏi bên không được phép. Tuy nhiên yêu cầu ứng dụng khác có thể khiến EtS phù hợp.

**Câu 6.** StE outer JWE decrypt thành công, inner JWS tự ký bởi attacker. Có hợp lệ không?

**Trả lời:** **Không.** Public-key encryption không xác thực issuer. RS phải từ chối vì inner signature không thuộc trusted AS signing key.

**Câu 7.** EtS outer JWS signature đúng nhưng JWE inner decrypt sai tag. Có hợp lệ không?

**Trả lời:** **Không.** Cả outer provenance và inner decryption/integrity đều bắt buộc. Không chuyển sang đọc plaintext chưa xác thực.

**Câu 8.** Nếu AS ký claims rồi encrypt bằng public key của Payments RS, Orders RS có thể dùng token đó không?

**Trả lời:** Không nếu Orders không phải recipient/không có allowed decryption key; và kể cả Orders decrypt được do key sharing, `aud`/resource authorization vẫn phải ngăn token dành cho Payments.

**Câu 9.** `alg=RSA-OAEP-256` và `enc=A256GCM` trong JWE có vai trò gì?

**Trả lời:** `RSA-OAEP-256` quản lý/đóng gói **CEK**, `A256GCM` mã hóa và xác thực payload bằng CEK. Chúng **không** là thuật toán ký JWS.

**Câu 10.** Signing key bị compromise nhưng encryption private key vẫn an toàn. Cần hành động gì?

**Trả lời:** Emergency distrust signing key trên các verifiers, cắt quyền ký, rotate key và đánh giá forged tokens. Không thể chỉ đổi recipient encryption key để khôi phục issuer authenticity.

**Câu 11.** Recipient private decryption key bị lộ nhưng signing key AS vẫn an toàn. Rủi ro chính là gì?

**Trả lời:** **Confidentiality** của JWE được encrypt cho key ấy, kể cả bản sao quá khứ đã bị thu thập. Attacker không tự làm giả AS signature nếu không có signing key, nhưng token theft/replay và data exposure vẫn cần ứng phó.

**Câu 12.** Vì sao nested JWT không thay token revocation?

**Trả lời:** Signature và ciphertext là dữ liệu đã tạo ở issuance; nếu AS revoke grant sau đó, RS offline không tự nhận tín hiệu mới. Cần status lookup/event/denylist hoặc token expiry theo guarantee.

**Câu 13.** Bên thứ ba muốn thấy bằng chứng AS ký ciphertext nhưng không biết claims. Thiết kế nào thuận tiện hơn?

**Trả lời:** EtS có outer JWS, nên bên có trusted AS public key có thể verify signature trên inner JWE serialization mà không decrypt. **Không có nghĩa** bên ấy được phép cấp quyền API.

**Câu 14.** Vì sao không thể chỉ trích outer `kid` mà biết key dùng cho cả signing và encryption?

**Trả lời:** StE outer `kid` thường là recipient **encryption** key; inner JWS có issuer signing `kid`. EtS thì outer signing `kid`, inner encryption `kid`. Key roles và trust registries khác nhau.

**Câu 15.** Một Spring Resource Server chỉ dùng `issuer-uri` và signed JWT decoder có tự nhận encrypted nested JWT không?

**Trả lời:** Không được giả định. Cần kiểm khả năng hỗ trợ của thư viện và cấu hình tầng JOSE decrypt/verify trước khi tích hợp chính sách Spring Security.

## 29. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Nested JWT, security considerations; **mục 11.2** về thứ tự ký/mã hóa.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact, signing input, protected headers và signature verification.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Compact, `alg`, `enc`, CEK, IV/tag, protected header và recipient key.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, `kid`, `use`, `key_ops` và key trust.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Approved JOSE algorithm identifiers, RSA-OAEP, AES-GCM và signature algorithms.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Explicit typing, allowed algorithms, key confusion, cross-JWT substitution.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Access-token `typ`/issuer/audience/expiry/scope và resource server validation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS/RS/client roles, access/refresh token lifecycle và grants.
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Trusted issuer discovery, JWKS URI metadata.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): Resource/audience-specific token issuance.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Revoking refresh/access tokens; ảnh hưởng khác key rotation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Active token check, RS caller authentication, caching and privacy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials và transport; encryption không ngăn credential replay.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Token theft, refresh-token protections, sender constraints.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, `ath` và sender binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): Certificate-bound access tokens và client authentication.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): AES-GCM IV uniqueness và authenticated encryption.
- [NIST SP 800-57 Part 1 Rev. 5 — Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): Key purposes, cryptoperiod, custody, rotation và compromise response.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Signed/encrypted ID tokens, issuer/audience/`nonce` validation.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JOSE/JWS/JWE Java library và documentation.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Signed JWT resource server configuration, issuer/JWKS, validators.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): Introspection alternative for opaque/reference tokens.
- [OWASP JWT for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT hardening, token storage and security pitfalls.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): Encryption, key custody, rotation và implementation hygiene.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): JWT validity không thay resource ownership kiểm tra.

**Ghi nhớ:** **Sign rồi encrypt** tạo **JWE(JWS(claims))**: issuer **ký chính claims** trước rồi mã hóa cả signed JWT cho recipient; RS **decrypt outer JWE, verify inner JWS** và sau đó kiểm quyền. **Encrypt rồi sign** tạo **JWS(JWE(claims))**: issuer **mã hóa claims** rồi ký serialized ciphertext; RS **verify outer JWS, decrypt inner JWE** và sau đó kiểm quyền. Thứ tự khác nhau về **ai nhìn được chữ ký, ai có thể verify trước decrypt và chữ ký ràng buộc plaintext hay ciphertext**. Với nested JWT cần cả hai mục tiêu, RFC 7519 thông thường ưu tiên **sign-then-encrypt** trừ khi ứng dụng có yêu cầu khác. Dù chọn hướng nào, token chỉ được chấp nhận khi **mọi lớp mật mã, issuer, audience, token type, expiry, scope, tenant, revocation và business authorization** đều đạt; JWE không thay TLS, không tự ngăn Bearer replay và không thay chính sách quản lý khóa.
