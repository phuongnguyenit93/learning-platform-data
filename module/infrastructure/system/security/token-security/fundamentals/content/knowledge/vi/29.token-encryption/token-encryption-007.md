# Validation thứ tự chữ ký và mã hóa

Một API nhận chuỗi JWT đã **mã hóa**. Sau khi giải mã được payload, API thấy `sub=user-123`, `scope=payments.approve` và `exp` còn hạn rồi lập tức cấp quyền. Sai lầm ở đây là đánh đồng **giải mã thành công** với **xác nhận token do authorization server đáng tin cậy phát hành**. Khi một resource server sử dụng **JWE với public encryption key**, bất cứ bên nào biết public key đó cũng có thể tạo một JWE hợp lệ về mặt mã hóa; chỉ vì JWE được giải mã và authentication tag đúng **không chứng minh ai đã phát token**. Nếu token profile yêu cầu JWT có chữ ký ở bên trong, server còn phải xác minh **JWS inner signature**.

Vấn đề đảo ngược cũng xảy ra: một hệ thống nhận **JWS bọc bên ngoài JWE**, verify JWS rồi **đọc quyền truy cập từ protected header** mà không giải mã, hoặc giải mã nhưng không kiểm mục đích/audience của JWT bên trong. Chữ ký và mã hóa bảo vệ **những ranh giới khác nhau**; **thứ tự validation phụ thuộc thứ tự cấu trúc bảo vệ trên wire và hợp đồng token**.

Bài thuộc chương **Token encryption** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Trọng tâm là cách nhận diện và validate **sign-then-encrypt** và **encrypt-then-sign**, cấu trúc **nested JWT/JWS/JWE**, quản lý khóa ký/khóa giải mã, chống token confusion, bảo vệ token OAuth 2.0/OIDC, các ca kiểm thử Java/Nimbus JOSE và quy trình triển khai resource server. Bối cảnh bao gồm **JWT, opaque token, access token, refresh token, ID token**, claims, scope, audience, thời hạn, lưu trữ, thu hồi và phòng chống replay.

> **Nguyên tắc:** Không cấp quyền từ bất kỳ payload nào cho đến khi đã kiểm đúng **mọi lớp bảo vệ mật mã mà profile yêu cầu**, xác minh **nguồn khóa**, **mục đích token**, **issuer/audience**, **thời gian**, **scope/quyền** và **trạng thái thu hồi**.

## 1. Xác định hai mục tiêu: authenticity và confidentiality

Token có thể cần những đặc tính khác nhau:

| Mục tiêu | Cơ chế điển hình | Bảo đảm | Không tự bảo đảm |
|---|---|---|---|
| **Integrity và issuer authentication** | JWS chữ ký bất đối xứng hoặc MAC trong trust domain thích hợp. | Nội dung ký không bị sửa; signature khớp khóa mà verifier đã **tin**. | Giấu payload, đúng audience, quyền thao tác, không bị replay. |
| **Confidentiality** | JWE với thuật toán mã hóa được phép. | Bên không có decryption key không đọc được plaintext. | Token do issuer tin cậy tạo nếu ai cũng mã hóa được bằng public key. |
| **Authenticated encryption integrity** | JWE AEAD như `A256GCM`. | Ciphertext/protected AAD được phát hiện nếu bị sửa, theo key và nonce hợp lệ. | Danh tính issuer độc lập với recipient/public-key encryption. |
| **Token authorization** | `iss`, `aud`, `scope`, type, `exp`, ownership/tenant policy. | Token đúng ngữ cảnh cho request. | Tính toàn vẹn nếu bỏ qua các bước mật mã. |
| **Revocation/replay control** | Grant status, denylist, introspection, DPoP/mTLS, TTL. | Hạn chế sử dụng tiếp/bản sao theo thiết kế. | Tự đến từ JWS/JWE mà không có thêm policy. |

**JWS không mã hóa**: payload của JWS Compact có thể đọc được qua Base64URL decode. **JWE không mặc nhiên là chữ ký của AS**: JWE xác thực nội dung bằng cơ chế mã hóa, nhưng có thể không xác thực được **issuer** nếu khóa mã hóa thuộc recipient hoặc public.

Nếu hệ thống chỉ cần giữ kín JWT mà không cần xác thực issuer theo JWS, có thể có **JWE-only profile hợp lệ** được định nghĩa rõ, đặc biệt khi bên phát và bên nhận có một trust boundary khác. Tuy nhiên, **không tự coi JWE-only là một access token hợp lệ của OAuth**; phải tuân thủ đúng token profile và cơ chế xác thực nguồn.

## 2. JWS, JWE, JWT và opaque token

**JWS (RFC 7515)** biểu diễn dữ liệu có chữ ký hoặc MAC; **JWE (RFC 7516)** biểu diễn dữ liệu mã hóa; **JWT (RFC 7519)** là biểu diễn tập claims được bảo vệ bằng JOSE theo profile.

| Định dạng | Compact Serialization thông thường | Dữ liệu bên ngoài thấy gì? |
|---|---|---|
| **JWS Compact** | 3 đoạn: `protected.payload.signature` | Header và payload Base64URL, chữ ký ở đoạn 3. |
| **JWE Compact** | 5 đoạn: `protected.encrypted_key.iv.ciphertext.tag` | Header mã hóa, key/IV/ciphertext/tag; plaintext không hiển thị. |
| **Nested JWT sign → encrypt** | **Outer JWE 5 đoạn**, plaintext sau giải mã là **inner JWS 3 đoạn**. | Nhìn ngoài chủ yếu thấy JWE header, chưa thấy JWS claims. |
| **Nested JWT encrypt → sign** | **Outer JWS 3 đoạn**, JWS payload chứa **inner JWE**. | Nhìn ngoài thấy JWS header và serialized JWE đã ký. |
| **Opaque access token** | Chuỗi không nhất thiết theo JWS/JWE. | RS thường phải introspect/kiểm state với AS; không suy dạng bằng dấu chấm. |

**Số đoạn chỉ là gợi ý hình thức, không phải bằng chứng hợp lệ**. Token giả có thể cố tình chứa đúng ba hoặc năm đoạn. Cần parse chặt, kiểm thuật toán/khóa và đúng profile.

### Những tên khóa dễ nhầm

- **Signing key:** AS/OP sử dụng private key để tạo JWS; RP/RS có trusted public key để verify.
- **Encryption key:** recipient có decryption private key (hoặc symmetric secret); issuer có encryption public key (hoặc secret).
- **Key management algorithm `alg` trong JWE:** cách xác lập/bao bọc content-encryption key, ví dụ `RSA-OAEP-256`.
- **Content encryption algorithm `enc` trong JWE:** ví dụ `A256GCM`.
- **JWS `alg`:** thuật toán chữ ký/MAC, ví dụ `RS256`.

**JWE `alg` không phải JWS `alg`**. Đừng dùng cùng enum/allowlist để quyết định cả hai.

## 3. “Ký rồi mã hóa” (sign-then-encrypt): mô hình phổ biến

Thứ tự tạo token:

1. Issuer tạo JWT claims hợp lệ cho một token profile.
2. Issuer **ký** claims thành **inner JWS Compact** bằng signing key của mình.
3. Issuer **mã hóa nguyên chuỗi JWS** đó thành **outer JWE Compact** bằng key/thuật toán dành cho recipient.
4. Client chuyển outer JWE tới bên nhận, thường qua HTTPS.

```text
claims JSON
    |
    v
JWS.sign(issuer_private_signing_key)
    |
    v
inner JWS Compact: H1.P1.S1
    |
    v
JWE.encrypt(recipient_encryption_key, plaintext=H1.P1.S1)
    |
    v
outer JWE Compact: H2.EK.IV.CIPHERTEXT.TAG
```

Thứ tự **validate ở recipient** là chiều ngược của việc bọc:

1. Parse **outer JWE** theo cấu trúc và policy được cho phép.
2. Chọn **recipient decryption key đáng tin**; từ chối thuật toán/extension ngoài hợp đồng.
3. **Giải mã và xác minh JWE authenticated-encryption tag** (không xuất plaintext cho business logic nếu integrity check fail).
4. Xác minh plaintext đúng dạng **inner JWS** mà profile mong đợi.
5. Chọn trusted **issuer signing public key** từ cấu hình/JWKS và **verify JWS signature**.
6. Sau khi verify, kiểm **typ/token purpose, iss, aud, exp, nbf, iat, scope** và những claims bắt buộc.
7. Kiểm subject, client, tenant, object ownership và revocation theo policy.
8. Chỉ sau đó mới tạo authenticated principal và cho phép operation.

```mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant CLIENT as OAuth Client
    participant RS as Resource Server
    participant KEYS as Trusted key stores/JWKS
    AS->>AS: Claims -> JWS signed bằng issuer private key
    AS->>AS: Encrypt inner JWS thành outer JWE cho RS
    AS-->>CLIENT: Nested JWT outer JWE
    CLIENT->>RS: Authorization: Bearer outer JWE
    RS->>KEYS: Resolve recipient decrypt key theo policy
    RS->>RS: Parse JWE, decrypt và verify AEAD tag
    RS->>KEYS: Resolve issuer verify key trusted
    RS->>RS: Parse inner JWS, verify signature
    RS->>RS: Check typ/iss/aud/exp/scope/revocation
    RS-->>CLIENT: Response theo authorization
```

Đây là **mô hình khuyến nghị thường gặp cho nested JWT**, phù hợp nguyên tắc trong RFC 7519 §11.2 về **sign then encrypt** khi cần cả chữ ký và mã hóa. Nhưng từng token profile **có thể quy định cấu trúc khác**; đừng chấp nhận thêm cấu trúc chỉ vì thư viện xử lý được.

## 4. Vì sao recipient phải giải mã trước rồi mới verify inner signature?

Vì **inner JWS bị mã hóa thành ciphertext**, recipient chưa có bytes JWS để xác minh chữ ký. Xử lý đúng:

```text
Outer JWE (5 segments)
      |
      |  Resolve recipient key + allowed JWE alg/enc
      v
Decrypt and CHECK authentication tag
      |
      v
Plaintext = inner JWS (3 segments)
      |
      |  Resolve issuer signing public key + allowed JWS alg
      v
Verify inner JWS signature
      |
      v
Validate JWT claims + API authorization
```

**Không**:

- Base64URL decode riêng đoạn ciphertext rồi xem nó là JSON claims.
- Tin các claims “nội suy” từ JWE protected header hoặc query parameters.
- Decrypt xong rồi cấp quyền mà **bỏ qua inner JWS**.
- Chấp nhận `JWS.parse()` thành công như bằng chứng chữ ký hợp lệ.
- Tin `kid` trong JWE để tìm signing key của issuer — **kid của outer JWE thường định danh decryption key**.
- Ghi plaintext/token vào logs để debug lỗi decryption.

Mã hóa cho recipient và chữ ký của issuer có thể sử dụng **hai bộ khóa và hai trust domains hoàn toàn khác**.

## 5. Cấu trúc outer JWE và inner JWS

Ví dụ **outer JWE protected header** khi mã hóa bằng RSA key transport và AES-GCM:

```json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "rs-decrypt-2026-11",
  "cty": "JWT"
}
```

Ví dụ **inner JWS protected header**:

```json
{
  "alg": "RS256",
  "kid": "issuer-sign-2026-11",
  "typ": "at+jwt"
}
```

Ví dụ **inner JWT payload** sau khi verify:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "iat": 1795410000,
  "nbf": 1795410000,
  "exp": 1795410900,
  "jti": "access-reference-123"
}
```

Đây là **dữ liệu minh họa**, không phải token hoặc khóa thật.

### Ý nghĩa riêng của các trường

| Trường | Vị trí | Diễn giải an toàn |
|---|---|---|
| Outer `alg=RSA-OAEP-256` | JWE header | Thuật toán quản lý/bao khóa cho decryption key của recipient. |
| Outer `enc=A256GCM` | JWE header | Thuật toán mã hóa nội dung có authentication tag. |
| Outer `kid=rs-decrypt…` | JWE header | Hint chọn **recipient private decryption key** trong trusted key store. |
| Outer `cty=JWT` | JWE header | Profile báo plaintext là **nested JWT**; một nhãn phải được thực thi. |
| Inner `alg=RS256` | JWS header | Thuật toán chữ ký issuer mà verifier cho phép. |
| Inner `kid=issuer-sign…` | JWS header | Hint chọn trusted **issuer public verification key**. |
| Inner `typ=at+jwt` | JWS header | Explicit typing cho access JWT theo profile khi áp dụng. |
| Inner `iss` | JWT claims | Issuer thực tế cần khớp trusted issuer config. |
| Inner `aud` | JWT claims | Orders API phải được liệt kê đúng audience. |

**`cty=JWT` không chứng minh tự thân plaintext là JWT hợp lệ**, cũng không chứng minh chữ ký đúng. Sau decrypt cần parse + verify inner layer theo policy.

## 6. JWE Compact: năm đoạn và authentication tag

JWE Compact Serialization có dạng:

```text
BASE64URL(UTF8(protected_header))
.
BASE64URL(encrypted_key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
```

Với JWE AEAD (như `A256GCM`), protected header tham gia làm **Authenticated Additional Data (AAD)** theo quy tắc JWE, vì vậy sửa các giá trị được bảo vệ sẽ khiến authentication tag không còn hợp lệ.

**Quan trọng:** Ở thời điểm chưa giải mã/xác minh tag, protected header vẫn là **input do caller kiểm soát** để parser lựa chọn code path. Chỉ dùng nó để so với allowlist và chọn **key trong trust store của recipient**; không coi `alg`, `kid`, `cty` là authority không cần xác minh.

### Với `RSA-OAEP-256 + A256GCM`

- Content được mã hóa đối xứng bằng CEK và AES-GCM.
- CEK được mã hóa/bao bọc cho **RSA public key của recipient** theo thuật toán được chỉ định.
- Recipient dùng private decryption key mở CEK, sau đó AES-GCM verify tag và giải mã.
- Issuer signing key **không nằm trong bước RSA-OAEP decryption**; nó được dùng verify **inner JWS** sau đó.

Đừng nhầm `alg=RSA-OAEP-256` với `alg=RS256`: đây là hai họ thao tác mật mã khác nhau.

## 7. Tại sao JWE decrypt + tag đúng không chứng minh issuer?

Giả sử Orders API công bố RSA **public encryption key** trên metadata cho AS gửi encrypted JWT. Public key không bí mật; một bên khác có thể sử dụng public key đó để tạo ciphertext được mã hóa hợp lệ cho Orders API.

Nếu API làm:

```text
JWE.decrypt(...); // Authentication tag valid
claims = parseJSON(plaintext);
if (claims.scope == "orders.approve") {
    allow();
}
```

thì bên tạo JWE bằng public encryption key có thể đặt claims giả, trừ khi có **cơ chế issuer authenticity bổ sung** được token profile yêu cầu và RS thực thi.

### Phòng vệ đúng cho nested JWT sign → encrypt

- Yêu cầu plaintext phải là **JWS signed JWT** hợp lệ theo profile.
- Verify inner JWS bằng public signing key **thuộc issuer đáng tin**, không bằng key do JWE payload/header tự công bố.
- Reject `alg=none`, algorithm confusion và key injection.
- Check issuer/audience/token type/scope/time/revoke.

**Không khẳng định mọi JWE-only đều không hợp lệ.** Nếu một hệ thống có cơ chế nguồn phát được xác thực khác, hoặc dùng symmetric authenticated-encryption trong trust boundary đã định nghĩa và profile cho phép JWE-only, yêu cầu sẽ khác. Vấn đề là **không tự suy nguồn phát từ phép giải mã bằng recipient private key trong public-key encryption**.

## 8. “Mã hóa rồi ký” (encrypt-then-sign): cấu trúc ngược

Một profile khác có thể yêu cầu:

1. Tạo claims/token payload cần mã hóa.
2. Mã hóa thành **inner JWE** cho recipient.
3. Ký **chuỗi JWE** bằng issuer signing key, tạo **outer JWS**.
4. Gửi JWS tới recipient.

```text
claims JSON
    |
    v
JWE.encrypt(recipient_key)
    |
    v
inner JWE Compact: H2.EK.IV.CIPHERTEXT.TAG
    |
    v
JWS.sign(issuer_private_signing_key, payload=innerJweCompact)
    |
    v
outer JWS Compact: H1.P1.S1
```

Ở recipient, **verify outer JWS trước khi decrypt inner JWE**:

```mermaid
flowchart TD
    I[Receive outer JWS] --> H[Parse protected header under strict policy]
    H --> K[Resolve issuer verification key from trusted source]
    K --> S{Verify outer JWS signature?}
    S -- No --> DENY[Reject]
    S -- Yes --> N{Payload is required nested JWE?}
    N -- No --> DENY
    N -- Yes --> D[Decrypt inner JWE and validate AEAD tag]
    D --> A{JWE alg/enc/recipient binding valid?}
    A -- No --> DENY
    A -- Yes --> C[Validate claims, type, audience, time, scope]
    C --> O[Apply revocation and object authorization]
```

**Không đảo ngược trình tự này** bằng cách cố decrypt toàn bộ chuỗi outer JWS như JWE. Phải biết **profile/serialization bên ngoài** trước.

### Một số khác biệt với sign-then-encrypt

| Tiêu chí | Sign → Encrypt | Encrypt → Sign |
|---|---|---|
| Outer Compact | JWE 5 đoạn | JWS 3 đoạn |
| First crypto operation ở recipient | JWE decrypt + AEAD tag | JWS signature verify |
| Second crypto operation | Inner JWS signature verify | Inner JWE decrypt + AEAD tag |
| Ai có thể verify issuer signature trước decrypt? | Không, trừ khi có cơ chế bổ sung. | Verifier có issuer public key có thể verify outer JWS mà không có decryption key. |
| Có thể tiết lộ issuer/kid ngoài ciphertext? | Outer header thường nói về recipient encryption key; issuer inner JWS được che. | Outer JWS header/signature metadata có thể lộ issuer key ID/profile. |
| Phù hợp JWT nested thông thường? | Thường được khuyến nghị khi cần cả chữ ký và mã hóa, trừ profile khác. | Chỉ chấp nhận khi hợp đồng token định nghĩa và threat model cho phép. |

**Không biến sự khác nhau thành quy tắc “cái nào tuyệt đối an toàn hơn”.** Phải dùng **thứ tự chính xác đã được issuer/recipient thống nhất**, đúng cấu trúc JOSE và threat model.

## 9. Không tự động chấp nhận cả hai thứ tự

Một điểm nguy hiểm là triển khai:

```text
try { decryptOuterJweThenVerifyInnerJws(); }
catch { try { verifyOuterJwsThenDecryptInnerJwe(); } }
if (anyPathSucceeds) accept();
```

Cách “thử mọi format cho đến khi một cái đúng” có thể tạo:

- **Downgrade**: attacker chọn profile ít bước validation hơn.
- **Type confusion**: ID token và access token dùng chung key nhưng khác mục đích.
- **Ambiguous validation**: một đường có kiểm `aud`, đường khác bỏ.
- **Algorithm confusion**: một đường dùng HMAC, đường khác dùng RSA, không có policy nhất quán.
- **Resource exhaustion**: thử decryption/signature nhiều lần trên input giả lớn.

### Chính sách nên là

```text
orders-api:
    accepted_profile: nested JWT sign-then-encrypt
    outer_format: JWE Compact
    outer_alg: RSA-OAEP-256
    outer_enc: A256GCM
    outer_cty: JWT
    inner_format: JWS Compact
    inner_alg: RS256
    inner_typ: at+jwt
    trusted_issuer: https://id.example.test
    expected_audience: orders-api
```

Những lựa chọn này do **server config/registration** xác định, **không lấy từ token header để tự mở rộng accepted formats**.

## 10. Validation phải ràng buộc issuer, recipient và resource

Một nested JWT có thể bảo vệ hai mối quan hệ độc lập:

- **Encryption recipient:** ai có quyền giải mã ciphertext?
- **Issuer signing:** ai đã phát token được tin?
- **OAuth audience:** API/client nào được phép dùng token?
- **OAuth client/grant:** token được cấp theo grant nào, phạm vi nào?

Ví dụ:

```text
Signing issuer:     https://id.example.test
JWS signing kid:    issuer-rsa-2026-11
JWE recipient:      orders-api
JWE recipient kid:  orders-decrypt-2026-11
JWT audience:       orders-api
Client ID:          orders-web
Scope:              orders.read
```

**Khóa decryption đúng không thay thế `aud` đúng.** Một JWE được mã hóa cho Orders API nhưng inner JWT có `aud=payments-api` vẫn phải bị từ chối.

Tương tự, inner JWS có chữ ký đúng của issuer nhưng **được mã hóa cho recipient khác** không được giải mã bằng “khóa thử chung”; mỗi recipient key ring phải độc lập theo tenant/trust boundary.

## 11. `cty`, `typ` và nested-JWT typing

Theo JWT/JWE profile:

- `cty=JWT` trong outer JOSE header thường được dùng **chỉ ra payload là nested JWT**, và trong trường hợp nesting JWT được yêu cầu theo RFC 7519.
- `typ` giúp **explicitly type** token, ví dụ `at+jwt` trong RFC 9068 JWT access token profile.
- Với sign → encrypt, outer JWE `cty=JWT` báo payload sau decrypt là nested JWT; inner JWS có thể có `typ=at+jwt` theo profile.
- Với encrypt → sign, outer JWS có thể đặt `cty=JWT` khi payload là nested JWT JWE; **header type/cty cụ thể phải theo profile đã đăng ký**.
- Header `typ`/`cty` được bảo vệ mật mã theo lớp JOSE tương ứng **sau khi chữ ký/tag được xác minh**; trước đó chúng chỉ là dữ liệu chưa tin.

**Một token có `cty=JWT` không chứng minh plaintext thật sự là JWS/JWE hợp lệ.** Phải parse và verify inner JWT. **Một token có `typ=at+jwt` cũng không tự chứng minh đó là access token dùng được tại RS** nếu không kiểm `iss`, `aud`, `scope` và authorization.

### Ví dụ tấn công confusion

OP phát ID token JWT ký đúng bằng một public key mà resource server cũng biết. Attacker bọc ID token vào một JWE mã hóa cho Orders API. Nếu RS chỉ decrypt và verify signature rồi **bỏ kiểm token purpose/audience**, ID token có thể bị chấp nhận nhầm như access token.

Chống lỗi này bằng token profile validation **cho từng lớp cần thiết**; không coi việc mã hóa thêm một ID token là chuyển nó thành access token.

## 12. Thời điểm được đọc claims như dữ liệu đáng tin

Một triển khai thường cần parse header/claims sơ bộ để định tuyến key. Nhưng **parse ≠ validate**.

| Giai đoạn | Có thể dùng dữ liệu cho việc gì? | Không được làm |
|---|---|---|
| Nhận raw compact token | Giới hạn size, định dạng, route/profile đã cấu hình. | Cấp quyền theo payload. |
| Parse outer header chưa auth | So allowlist, chọn recipient key đã biết; hạn chế kích thước/charset. | Fetch key từ URL caller chỉ định, đổi policy. |
| Sau decrypt + AEAD tag đúng | Parse inner JWS, chuẩn bị verify bằng trusted issuer key. | Tin inner claims làm identity khi signature chưa verify. |
| Sau inner JWS verify đúng | Đọc claims để validate type/issuer/audience/time. | Cho qua claims sai hoặc token revoked. |
| Sau claims + authorization | Tạo principal/permit operation. | Trả raw token hoặc private data vào logs. |

Với encrypt → sign, tương ứng **outer signature verify** phải xong trước khi lấy inner JWE để giải mã. Việc kiểm loại JOSE và key source vẫn phải theo server policy.

## 13. Key management và thuật toán: đừng trộn khóa ký, khóa mã hóa

| Loại | Ví dụ thuật toán | Khóa dùng | Vai trò |
|---|---|---|---|
| JWS signing | `RS256` | Issuer RSA private key. | Phát chữ ký. |
| JWS verification | `RS256` | Trusted issuer RSA public key. | Verify chữ ký. |
| JWE key management | `RSA-OAEP-256` | Recipient RSA public/private key. | Bao/mở content-encryption key. |
| JWE content encryption | `A256GCM` | Content-encryption key. | Encrypt/decrypt + authentication tag. |
| JWS MAC | `HS256` | Shared secret. | Integrity theo secret chia sẻ. |
| JWE symmetric direct | `dir` với `A256GCM` | Key đối xứng được bảo vệ. | Encrypted content trong shared-secret boundary. |

**JWS `kid` và JWE `kid` có thể có giá trị khác nhau**, vì hai key rings khác nhau. Không lấy private JWE decryption key làm JWS verification key hay ngược lại.

### Algorithm allowlist

Một contract có thể cho phép:

```text
Outer JWE:
  allowed key management alg = RSA-OAEP-256
  allowed content enc = A256GCM

Inner JWS:
  allowed signature alg = RS256
  trusted issuer = https://id.example.test
```

Tránh dùng `RSA1_5` legacy hoặc các thuật toán không đạt baseline, tránh `alg=none` ở inner JWS và không tự fallback sang bất kỳ thuật toán nào thư viện hỗ trợ. **Quy tắc chính xác do policy và profile quyết định**.

## 14. JWE authenticated-encryption: integrity tag không được bỏ

**AES-GCM** bảo vệ confidentiality và integrity của ciphertext/AAD, nếu key/nonce được quản lý đúng. Khi `tag` hoặc protected header bị sửa, decryption phải fail.

Rủi ro khi tự triển khai:

- Trả plaintext trước khi **xác thực tag** rồi đưa nó vào business logic.
- Bắt exception tag failure và trả về JSON claims từ bộ nhớ/cache trước đó.
- Dùng lại GCM IV/nonce với cùng CEK trong cách phát hành không an toàn.
- Dùng crypto “AES/ECB” hoặc CBC không có authentication/JOSE composition chuẩn.
- Bỏ qua `crit` hoặc unsupported JWE headers.
- Tin outer header chứa `jku`/`x5u` và fetch arbitrary key.
- Phản hồi khác biệt chi tiết theo lỗi key/format tạo information oracle.

### Quy tắc xử lý khi lỗi

- **Authentication tag fail:** reject toàn bộ token; không giải quyết bằng inner signature verification.
- **Wrong recipient key:** reject hoặc dùng đúng key trong trusted key ring theo header/key policy.
- **Unsupported `alg`/`enc`:** reject, không downgrade.
- **Malformed IV/tag lengths:** reject trước khi cấp tài nguyên quá lớn.
- **Decryption key unavailable:** fail closed; không chấp nhận ciphertext như claims.

**Dùng JOSE library uy tín**, không tự ghép AES-GCM/CBC và RSA rồi gọi đó là JWE.

## 15. Chống encryption oracle, key confusion và key injection

JWE decryption liên quan private key/secret, vì vậy là một bề mặt tấn công riêng.

| Lỗi | Tác động | Bảo vệ |
|---|---|---|
| Decryption error quá chi tiết. | Lộ thông tin phân biệt key/format/tag, hỗ trợ oracle attack. | Phản hồi lỗi chuẩn hóa, telemetry nội bộ có kiểm soát. |
| Dùng `kid` làm file path. | Path traversal/đọc khóa không phép. | Map issuer/recipient → allowed keys, strict identifier. |
| Cho token chọn `jku` tùy ý. | SSRF và attacker-controlled key source. | Pin key source, không fetch URL tùy ý. |
| Thử tất cả decrypt keys khi sai `kid`. | CPU DoS và cross-tenant key confusion. | Bounded trusted key selection. |
| Chấp nhận `alg=dir` khi profile yêu cầu RSA-OAEP. | Đổi trust boundary sang shared-secret ngoài ý muốn. | Algorithm/profile allowlist. |
| Dùng private JWE key thay signing key. | Sai vai trò và khả năng bỏ qua issuer authentication. | Separate key stores/key purpose. |
| Unauthenticated plaintext dùng trước tag verify. | Parser/authorization xử lý dữ liệu bị sửa. | Verify AEAD trước khi tin plaintext. |
| Log ciphertext, decrypted JWT, key material. | Lộ token nhạy cảm hoặc dữ liệu cá nhân. | Redaction, reference IDs và least privilege. |

### Tránh nested-depth DoS

Nếu profile yêu cầu **outer JWE → inner JWS**, parser phải từ chối **inner JWE lần nữa** hoặc các lớp lồng thêm không được đăng ký. Một attacker có thể gửi nesting lặp liên tục để ép nhiều phép RSA/decompression/JSON parses. Đặt giới hạn độ sâu, kích thước, số keys, thời gian xử lý và reject profile không phù hợp.

## 16. Validation claims vẫn là điều kiện độc lập

Sau khi hoàn thành toàn bộ crypto chain, RS phải validate đúng OAuth 2.0/OIDC context.

| Kiểm tra | Vì sao cần? |
|---|---|
| `iss` | Chỉ nhận token do AS/OP thuộc trusted issuer phát hành. |
| `aud` | Token dành cho **resource server này**, không API khác. |
| `exp` | Từ chối token hết hạn dù signature/encryption hợp lệ. |
| `nbf`, `iat` | Chặn token chưa có hiệu lực hoặc tuổi/issued-at bất thường theo policy. |
| `typ`/token-use | Không dùng ID token hay refresh token làm API access token. |
| `scope`/`scp` | Quyền được cấp phải đủ cho operation, so khớp tokenized scope. |
| `client_id`/`azp` | Đúng ngữ cảnh OAuth client/authorized party theo token profile. |
| `sub`/tenant/owner | Chủ thể được phép truy cập đối tượng nghiệp vụ. |
| `jti`/grant status | Revoke/replay policy khi cần. |
| `cnf` + DPoP/mTLS proof | Nếu sender-constrained token, kiểm caller giữ đúng khóa. |

### Mã hóa không khắc phục audience confusion

Một JWE được mã hóa cho Orders API có thể chứa inner JWT được issuer ký **cho Payments API**. Decryption key là của Orders API, signature của issuer cũng có thể đúng, nhưng `aud=payments-api` ⇒ Orders API phải từ chối.

### Signature không khắc phục token bị đánh cắp

Một bearer nested JWT bị sao chép nguyên vẹn vẫn decrypt/verify thành công nếu recipient key và issuer key hợp lệ. Vì vậy phải có TTL, revoke status/denylist và sender-bound tokens khi áp dụng; JOSE crypto **không tự chặn replay**.

## 17. Với ID token OIDC cần kiểm thêm gì?

OIDC ID token dùng để chứng minh kết quả **authentication tại RP**, không phải access token dành cho RS. Nếu OP và RP dùng encrypted ID token profile:

- RP giải mã JWE bằng **decryption key của mình** theo registered algorithms.
- Nếu nested signed ID token thì RP phải verify inner JWS bằng **OP signing key đáng tin**.
- Kiểm `iss`, `aud` chứa RP client ID, `azp` khi áp dụng.
- Kiểm `exp`, `iat`, `nonce` khi đã yêu cầu trong Authentication Request.
- Kiểm `auth_time` nếu `max_age`/authentication freshness yêu cầu.
- Kiểm `at_hash`/`c_hash` khi flow/profile yêu cầu.
- Không gửi ID token đã giải mã sang Orders API để sử dụng như bearer access token.

**Không tự giả định mọi encrypted ID token đều luôn có inner JWS**, vì profile/registration có thể khác; việc chấp nhận hay không phải theo **OIDC client registration và thuật toán đã thương lượng**, không theo “decrypt được là đủ”.

## 18. Với opaque access token và refresh token thì sao?

**Opaque access token** có thể không mang JWS/JWE Compact. RS nên dùng **RFC 7662 Token Introspection** hoặc cơ chế status tin cậy:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic INTROSPECTION_CLIENT_AUTH_PLACEHOLDER

token=OPAQUE_ACCESS_TOKEN_PLACEHOLDER&token_type_hint=access_token
```

Response mẫu:

```json
{
  "active": true,
  "iss": "https://id.example.test",
  "aud": "orders-api",
  "scope": "orders.read",
  "sub": "user-123",
  "exp": 1795410900
}
```

Ở đây RS **không tự decrypt-and-verify JWS** trên opaque string. Nó phải xác thực endpoint/introspection caller qua TLS và client authentication, kiểm `active`/audience/scope/tenant/token type theo response policy. Positive cache có thể làm chậm revoke.

**Refresh token** dùng ở token endpoint để cấp access token mới theo grant; không dùng tại resource API. Nếu một hệ thống tự định nghĩa encrypted refresh token, **AS là bên được phép giải mã và kiểm trạng thái grant**, không phải Orders API. Việc refresh token rotation/reuse detection cần chính sách riêng, không bị giải quyết chỉ bằng JWE+JWS.

## 19. Điều gì xảy ra khi token bị revoke hoặc issuer rotate keys?

Chữ ký và mã hóa vẫn có thể đúng đối với token đã bị revoke; phải có cơ chế status enforcement khi yêu cầu.

| Sự kiện | Tác động mật mã | Cần thêm gì? |
|---|---|---|
| User logout local. | Không làm JWS/JWE bytes thay đổi. | Xóa session/credentials và revoke theo policy. |
| AS revoke refresh grant. | Nested access JWT cũ vẫn decrypt/verify. | RS denylist/introspection/grant status hoặc chờ TTL. |
| Issuer rotate signing K1 → K2. | Inner JWS mới dùng K2; token cũ K1 có thể vẫn valid. | Trusted issuer JWKS overlap và key retirement. |
| Recipient rotate decryption D1 → D2. | Outer JWE mới dùng D2; ciphertext D1 cũ cần D1 nếu còn hạn. | Decryption key ring overlap, reissue/re-encrypt hoặc invalidate. |
| Issuer signing private K1 compromised. | Attacker có thể tạo inner JWS giả K1. | Emergency signer disable và trusted verification key removal. |
| Recipient private D1 compromised. | Ciphertexts mã hóa cho D1 có thể bị giải mã bởi attacker. | Emergency decryption key rotation, exposure review và reissuance. |

**Signing-key rotation và encryption-key rotation là hai quy trình riêng**. Một hệ thống nên inventory theo `issuer signing kid` và `recipient encryption kid`, với owner/retirement riêng.

## 20. Tại sao thứ tự validation cần là một “hợp đồng”, không phải suy đoán?

Token profile cần mô tả chính xác:

- **Outer serialization**: JWE Compact hay JWS Compact.
- **Inner serialization**: JWS/JWE/JWT JSON theo profile, có hay không nested.
- **Số lớp** được phép, chẳng hạn đúng hai.
- **Allowed algorithms** riêng cho JWE `alg`/`enc` và JWS `alg`.
- **Nguồn decryption key**, issuer signature verification key.
- **`typ`/`cty` expected values**.
- **Issuer/audience/client/tenant** của token dùng cho API.
- **Required claims** và validation rules.
- **Revocation/sender-constraint/replay policy**.
- **Hành vi lỗi**: reject khi thiếu bất kỳ lớp bắt buộc nào.

```yaml
accepted-token-profile:
  outer: JWE-compact
  order: sign-then-encrypt
  outer-alg: RSA-OAEP-256
  outer-enc: A256GCM
  outer-cty: JWT
  inner: JWS-compact
  inner-alg: RS256
  inner-typ: at+jwt
  trusted-issuer: https://id.example.test
  audience: orders-api
  nesting-depth: 2
```

Đây là **configuration minh họa**, không phải properties chuẩn có sẵn của Spring Security. Không copy YAML rồi giả định Spring tự hỗ trợ nested JWE.

## 21. Java 17 + Nimbus JOSE: sign rồi encrypt, sau đó decrypt rồi verify

Ví dụ dưới đây minh họa **nested JWT sign-then-encrypt** bằng thư viện `com.nimbusds:nimbus-jose-jwt`. Nó tạo **test RSA keys trong bộ nhớ** để bài học tự chạy, không sử dụng private key production.

Thiết kế mẫu:

- Issuer sở hữu **private signing key** `issuerSign`.
- Orders API sở hữu **private decryption key** `ordersDecrypt`.
- Issuer biết **public encryption key** của Orders API.
- Orders API biết **public signing key** của issuer qua trust configuration/JWKS đã thẩm định.
- Outer JWE: `RSA-OAEP-256` + `A256GCM`, `cty=JWT`.
- Inner JWS: `RS256`, `typ=at+jwt`.
- Sau khi kiểm cả hai lớp, RS kiểm issuer/audience/expiry/scope.

```java
import com.nimbusds.jose.EncryptionMethod;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWEAlgorithm;
import com.nimbusds.jose.JWEHeader;
import com.nimbusds.jose.JWEObject;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.Payload;
import com.nimbusds.jose.crypto.RSADecrypter;
import com.nimbusds.jose.crypto.RSAEncrypter;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Date;
import java.util.UUID;

public final class SignThenEncryptDemo {

    private static final String ISSUER = "https://id.example.test";
    private static final String AUDIENCE = "orders-api";
    private static final String ISSUER_SIGN_KID = "issuer-sign-1";
    private static final String RECIPIENT_ENC_KID = "orders-decrypt-1";

    private SignThenEncryptDemo() {}

    // Demo issuer: ký JWT trước rồi mã hóa nguyên JWS Compact.
    public static String issue(
            RSAPrivateKey issuerSigningPrivate,
            RSAPublicKey recipientEncryptionPublic) throws Exception {

        Date now = new Date();
        Date expires = new Date(now.getTime() + 600_000L);

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(ISSUER)
            .subject("user-123")
            .audience(AUDIENCE)
            .issueTime(now)
            .notBeforeTime(now)
            .expirationTime(expires)
            .jwtID(UUID.randomUUID().toString())
            .claim("scope", "orders.read")
            .build();

        SignedJWT innerJws = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(ISSUER_SIGN_KID)
                .type(new JOSEObjectType("at+jwt"))
                .build(),
            claims);

        innerJws.sign(new RSASSASigner(issuerSigningPrivate));

        JWEObject outerJwe = new JWEObject(
            new JWEHeader.Builder(
                JWEAlgorithm.RSA_OAEP_256,
                EncryptionMethod.A256GCM)
                .keyID(RECIPIENT_ENC_KID)
                .contentType("JWT")
                .build(),
            new Payload(innerJws.serialize()));

        outerJwe.encrypt(new RSAEncrypter(recipientEncryptionPublic));
        return outerJwe.serialize();
    }

    // Demo recipient: cryptographic chain rồi claims.
    // Private decrypt key và public issuer key là TRUSTED INPUTS
    // được cấp qua cấu hình/kho khóa, không lấy từ JWT header.
    public static JWTClaimsSet accept(
            String compactJwe,
            RSAPrivateKey trustedRecipientDecryptionKey,
            RSAPublicKey trustedIssuerSigningPublicKey) throws Exception {

        JWEObject outer = JWEObject.parse(compactJwe);

        if (!JWEAlgorithm.RSA_OAEP_256.equals(
                outer.getHeader().getAlgorithm())
                || !EncryptionMethod.A256GCM.equals(
                    outer.getHeader().getEncryptionMethod())
                || !"JWT".equals(outer.getHeader().getContentType())
                || !RECIPIENT_ENC_KID.equals(
                    outer.getHeader().getKeyID())) {
            throw new SecurityException("Invalid JWE profile");
        }

        // Nimbus kiểm authentication tag khi decrypt JWE.
        // Nếu lỗi, dừng xử lý và KHÔNG parse business claims.
        outer.decrypt(new RSADecrypter(trustedRecipientDecryptionKey));

        SignedJWT inner = SignedJWT.parse(
            outer.getPayload().toString());

        if (!JWSAlgorithm.RS256.equals(
                inner.getHeader().getAlgorithm())
                || !new JOSEObjectType("at+jwt").equals(
                    inner.getHeader().getType())
                || !ISSUER_SIGN_KID.equals(
                    inner.getHeader().getKeyID())) {
            throw new SecurityException("Invalid JWS profile");
        }

        if (!inner.verify(
                new RSASSAVerifier(trustedIssuerSigningPublicKey))) {
            throw new SecurityException("Invalid issuer signature");
        }

        JWTClaimsSet claims = inner.getJWTClaimsSet();
        Date current = new Date();

        if (!ISSUER.equals(claims.getIssuer())
                || !claims.getAudience().contains(AUDIENCE)
                || claims.getExpirationTime() == null
                || !claims.getExpirationTime().after(current)
                || (claims.getNotBeforeTime() != null
                    && claims.getNotBeforeTime().after(current))
                || !"orders.read".equals(
                    claims.getStringClaim("scope"))) {
            throw new SecurityException("Invalid token claims");
        }

        return claims;
    }

    public static void main(String[] args) throws Exception {
        // Chỉ dùng ephemeral test keys trong DEMO.
        RSAKey issuerSign = new RSAKeyGenerator(2048)
            .keyID(ISSUER_SIGN_KID).generate();
        RSAKey ordersDecrypt = new RSAKeyGenerator(2048)
            .keyID(RECIPIENT_ENC_KID).generate();

        String nested = issue(
            issuerSign.toRSAPrivateKey(),
            ordersDecrypt.toRSAPublicKey());

        JWTClaimsSet verified = accept(
            nested,
            ordersDecrypt.toRSAPrivateKey(),
            issuerSign.toRSAPublicKey());

        System.out.println(verified.getAudience());
        // [orders-api]
    }
}
```

### Điều đoạn mã làm đúng ở mức minh họa

- **Ký trước**, đưa **chuỗi SignedJWT hoàn chỉnh** vào JWE plaintext.
- Trước khi decrypt, kiểm outer JWE header đúng thuật toán/content type/key ID mong đợi.
- Dùng recipient private key để decrypt JWE, thư viện xử lý tag.
- **Parse inner JWS sau khi decrypt**; kiểm `alg`, `typ`, `kid` và verify bằng **public issuer key**.
- **Chỉ lấy claims sau khi chữ ký được verify** và kiểm issuer/audience/expiry/scope.

### Điều demo chưa phải production

- Các khóa được tạo trong cùng phương thức `main` để đơn giản; production phải tách issuer signer và RS recipient, dùng **KMS/HSM/JWKS trust**.
- Demo chỉ có **một trusted issuer/recipient key**. Hệ thống thật có multiple keys/rotation cần resolver theo issuer + key ID + algorithm + key status.
- Validation chưa đầy đủ `iat`, max-age, token subtype, `jti` revoke, token audience/list policy, tenant/owner, delegated consent và step-up.
- Kiểm scope một giá trị cố định để minh họa; production parse các scopes đã được cấp thành tập quyền, không dùng substring match.
- Demo không kiểm policy `crit`/unsupported headers, max token size, limits nesting, errors/log redaction, network trust hay các dạng JWE khác.
- Code chỉ nên dùng với các phiên bản Nimbus JOSE hỗ trợ API tương ứng; quản lý dependency qua build/BOM đã được kiểm chứng.
- **Không dùng kết quả `accept()` làm authorization cuối cùng** nếu chưa có đối chiếu đối tượng, tenant, revocation và token type/profile đầy đủ.

**Đặc biệt:** Thư viện verify thành công một chữ ký chỉ có ý nghĩa khi public issuer key **đã được tin cậy từ trước**. Thay `trustedIssuerSigningPublicKey` bằng public key lấy từ `jwk`/`jku` trong token sẽ phá ranh giới này.

## 22. Java/Nimbus: encrypt-then-sign và validation đảo lại

Với một profile định nghĩa **outer JWS → inner JWE**, quy trình mã hóa và ký sẽ đảo:

```java
// Pseudocode biểu diễn các bước, không phải toàn bộ implement:
String innerJwe = encryptionService.encryptClaimsForRecipient(
    claims, trustedRecipientPublicKey, allowedJweProfile);

// Outer JWS signature ký đúng bytes của serialized inner JWE.
String outerJws = issuerSigner.signPayload(
    innerJwe, trustedIssuerSigningPrivateKey, allowedJwsProfile);
```

Recipient:

```java
// Pseudocode: không tin payload trước outer JWS verification.
VerifiedPayload signedPayload =
    issuerVerifier.verifyOuterJws(
        outerJws,
        trustedIssuerSigningKeySet,
        allowedOuterJwsProfile);

String innerJwe = signedPayload.asRequiredNestedJwe();
VerifiedPlaintext plaintext =
    recipientDecryptor.decryptAndAuthenticate(
        innerJwe,
        trustedRecipientKeySet,
        allowedInnerJweProfile);

JwtClaims claims = claimsParser.parseStrict(plaintext);
claimsValidator.validate(claims, expectedIssuer, expectedAudience);
authorizationService.enforce(claims, request);
```

Trong trường hợp này, **không được bỏ outer JWS verify**, và outer signed content phải bao gồm **chính xác serialized JWE bytes** mà recipient sau đó dùng. Không ký một representation rồi giải mã một representation khác do attacker tác động.

**Không dùng đoạn pseudo này để “hỗ trợ cả hai format tự động”**. Chỉ bật encrypt-then-sign khi token profile/trust contract có yêu cầu.

## 23. Spring Security Resource Server: đừng giả định hỗ trợ JWE nested tự động

Spring Security có decoder JWT phổ biến như `NimbusJwtDecoder`, thường cấu hình cho **JWT JWS có chữ ký** theo `issuer-uri`/`jwk-set-uri`. Nó **không nên được giả định là tự xử lý mọi outer JWE Compact và inner JWS nested JWT** chỉ vì cấu hình JWT resource server.

Ví dụ cấu hình JWS thông thường:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://id.example.test"
```

**Không đủ cho nested-JWE profile.** Cần chọn một trong các cách rõ ràng:

1. **AS và RS giao tiếp opaque token + RFC 7662 introspection** nếu kiến trúc ưu tiên server-side token validity, không cần RS tự decrypt nested JWT.
2. **Custom decoder/adapter** bên RS thực thi đúng JWE decrypt → inner JWS verify → claims validation rồi mới tạo Spring Security `Authentication`.
3. **Gateway token processing** đáng tin cậy, giao tiếp với RS bằng một identity assertion mới có authentication/integrity, không chỉ chuyển raw user headers.
4. **AS token-exchange/token format contract** phát JWS phù hợp bên nhận nếu việc dùng JWE không thật sự cần thiết.

Một mẫu adapter để minh họa ranh giới:

```java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;

public final class NestedJweJwtDecoder implements JwtDecoder {

    private final NestedTokenValidationService validator;

    public NestedJweJwtDecoder(NestedTokenValidationService validator) {
        this.validator = validator;
    }

    @Override
    public Jwt decode(String bearerToken) throws JwtException {
        // Service phải:
        // 1. enforce configured outer JWE profile and trusted keys;
        // 2. decrypt JWE + verify authentication tag;
        // 3. enforce inner JWS type/alg/issuer-key profile;
        // 4. verify JWS signature;
        // 5. validate claims: iss, aud, exp, nbf, scope, etc;
        // 6. apply token revocation policy as required.
        // Không được tạo Jwt từ unverified payload.

        VerifiedNestedToken verified =
            validator.decryptVerifyAndValidate(bearerToken);

        // Pseudocode result: header map của signed inner JWT
        // và claims đã được validate.
        return new Jwt(
            bearerToken,
            verified.issuedAt(),
            verified.expiresAt(),
            verified.verifiedSignedHeaders(),
            verified.verifiedClaims());
    }
}

// NestedTokenValidationService và VerifiedNestedToken
// là interface/domain types do hệ thống TỰ định nghĩa.
// Đoạn code chưa triển khai validator.
```

**Đây là thiết kế API minh họa**, chưa phải Spring bean production. `JwtDecoder` nhận bearer token dạng outer JWE; service phải bảo đảm toàn bộ chain đã được validate trước khi tạo `Jwt`. Sau đó Spring vẫn cần map authorities từ claims và enforce endpoint/tenant/object authorization. Khi parser không hợp lệ, lỗi nên được ánh xạ thành `JwtException`/`invalid_token` phù hợp, không làm rò plaintext hay key details.

### Khi dùng WebFlux hoặc gateway

Nếu kiến trúc dùng Spring WebFlux, chọn decoder/adapter tương ứng reactive, không copy servlet config vào reactive context. Nếu Gateway decrypt thay RS, **phải có trust contract chống header spoofing và bảo vệ traffic giữa gateway–RS**; không nhận plain `X-User-Role` từ Internet sau khi gateway “đã verify”.

## 24. Key rotation với hai lớp khóa

Nested JWT sign → encrypt thường có hai `kid`:

```text
Outer JWE:
  kid = orders-decrypt-D1

Inner JWS:
  kid = issuer-sign-S1
```

Hai cặp khóa có thể rotate **độc lập**:

| Đối tượng | Khi thay D1 → D2 | Khi thay S1 → S2 |
|---|---|---|
| Outer JWE | Ciphertext mới mã hóa cho public D2; recipient cần D2 private key. | Có thể không đổi recipient encryption key. |
| Inner JWS | Có thể vẫn ký S1 nếu issuer chưa đổi signing key. | JWT mới ký S2; issuer JWKS công bố trusted S2. |
| RS decrypt trust | Có thể giữ D1 trong bounded overlap để decrypt token cũ. | Không tự ảnh hưởng. |
| RS signature trust | Không tự ảnh hưởng. | Có thể giữ S1 public verify-only cho token cũ nếu key sạch. |
| Khi D1 private bị lộ | Có nguy cơ confidentiality, cần response về exposure. | Không giải quyết bằng chỉ đổi S1. |
| Khi S1 private bị lộ | Không tự bị lộ D1. | Có nguy cơ forged JWT, cần RS ngừng tin S1. |

### Phối hợp rollout

- Prepublish **recipient public D2** để issuer có thể mã hóa token mới cho đúng recipient.
- Prepublish **issuer public S2** ở trusted JWKS để RS có thể verify inner JWS S2 sau decrypt.
- Đảm bảo AS và RS có một khoảng overlap đã tính riêng cho D1 và S1.
- Tính theo max token lifetime + bounded skew + propagation, không dùng một thời hạn cố định cho mọi key.
- Nếu private signing key compromised, **không dùng normal grace cho S1**.
- Nếu recipient private decryption key compromised, cần xem xét ciphertext cũ có thể bị lộ plaintext; key rollover không xóa dữ liệu đã bị sao chép.

**Decryption-key rotation không phải JWT signature-key rotation**. Một error `kid` trên outer JWE thường cần kiểm decryption key ring, còn error `kid` trên inner JWS cần kiểm issuer signing JWKS.

## 25. Không để claims chưa xác minh điều khiển lựa chọn khóa

Một cạm bẫy tinh vi: service muốn biết tenant/issuer để chọn decrypt key. Nó cố gắng đọc `tenant_id` từ inner JWT trước khi decrypt/verify hoặc lấy header `kid` từ outer JWE để truy cập bất kỳ tenant key.

Thiết kế an toàn cần:

- Route/API xác định trước **recipient/trust domain** từ cấu hình đáng tin.
- Chọn decryption key trong **allowed key ring** của recipient đó; outer `kid` chỉ là hint bị giới hạn.
- Sau decrypt, chọn issuer verify keys từ **trusted issuer allowlist**. Nếu cần đọc inner `iss` trước verification để routing, dùng nó **chỉ làm hint trong allowlist cố định**; sau verify kiểm `iss` chính xác.
- Chỉ sau khi verify toàn bộ chain mới cho claims `tenant_id`/`sub` tác động authorization.
- Multi-tenant: account owner/issuer/tenant binding ở server-side, không tin URL/query/header do caller tự ghi.

### Ví dụ sai

```text
client gửi header X-Tenant=finance
outer JWE kid=finance-key
server dùng X-Tenant để chọn private key bất kỳ
decrypt rồi coi inner claims là đã trusted
```

Đây là nguy cơ cross-tenant key lookup/authorization. Không dùng header user-controlled làm authority để chọn trust domain.

## 26. Chống cross-JWT confusion và profile substitution

Một OP có thể phát các JWT sau, đôi khi bằng cùng signing key:

- **ID token** cho RP xác thực người dùng.
- **Access token** cho RS.
- **Logout Token** cho RP Back-Channel Logout.
- **Client assertion** cho OAuth client authentication.
- **Security event token** theo profile riêng.

Nếu RS chỉ thấy inner JWS chữ ký hợp lệ và outer JWE decrypt được, nó có thể vô tình chấp nhận **nhầm mục đích**.

| Dữ liệu | Nhận tại Orders API? | Vì sao |
|---|---|---|
| Encrypted **JWT access token** `aud=orders-api`, `typ=at+jwt` đúng profile. | Có thể. | Cần thêm scope/object/revoke checks. |
| Encrypted **OIDC ID token** `aud=orders-web-client`. | **Không.** | Audience và token purpose dành RP. |
| Encrypted **Logout Token** với `events` logout. | **Không.** | Là security event, không phải API credential. |
| **Refresh token** dùng như bearer access. | **Không.** | Chỉ AS token endpoint xử lý theo grant. |
| JWT do issuer khác ký nhưng mã hóa cho Orders. | **Không.** | Outer encryption không hợp thức hóa issuer. |
| Access JWT có audience Payments nhưng mã hóa cho Orders. | **Không.** | Wrong audience. |

**Explicit typing** theo RFC 8725/RFC 9068 cùng **mutually exclusive validation rules** cho mỗi token kind giúp giảm confusion. Chỉ kiểm inner `typ` mà bỏ `aud`/claims vẫn không đủ.

## 27. Nested JWT và replay/thời hạn

Mã hóa và chữ ký **không làm Bearer token thành one-time token**.

Khi attacker lấy nguyên outer JWE còn hạn:

1. Họ không cần đọc plaintext để **phát lại nguyên ciphertext** nếu có đường gửi tới recipient.
2. RS vẫn decrypt JWE và verify inner JWS thành công.
3. Nếu có quyền của bearer, request có thể được chấp nhận trừ khi đã revoke hoặc có sender constraints.

### Những biện pháp riêng

- Access-token lifetime ngắn, kiểm `exp` chính xác.
- `aud` và `scope` tối thiểu, subject/tenant/object authorization.
- Không log raw JWE, JWS hoặc Authorization header.
- Token revocation/denylist/grant-state check theo risk policy.
- DPoP/mTLS sender-constrained token nếu profile hỗ trợ, RS kiểm proof đúng.
- Với ID token, sử dụng `nonce` và authentication flow binding theo OIDC khi có.

**JWE ciphertext che payload nhưng không ngăn người giữ bản sao dùng lại Bearer token.**

## 28. Error handling: không biến service thành oracle

Thứ tự crypto tạo nhiều loại lỗi:

| Lỗi | Phản ứng phía client | Telemetry nội bộ không chứa secret |
|---|---|---|
| Unsupported outer JWE `alg`/`enc` | `401 invalid_token` hoặc lỗi tương ứng theo API. | `OUTER_ALG_REJECTED`. |
| JWE key không tồn tại trong trusted ring | Reject. | `RECIPIENT_KEY_NOT_FOUND`, normalized key reference. |
| JWE authentication tag sai | Reject. | `JWE_AUTH_FAILURE`. |
| Plaintext không phải inner JWS như profile | Reject. | `INNER_FORMAT_REJECTED`. |
| Inner JWS signature sai | Reject. | `INNER_SIGNATURE_INVALID`. |
| Inner issuer/audience/type/time sai | Reject. | `CLAIMS_VALIDATION_FAILED` với reason code. |
| Token đúng crypto nhưng thiếu scope | Thường `403 insufficient_scope` theo contract. | `ACCESS_DENIED_SCOPE`. |
| Token/grant bị revoke | Reject. | `TOKEN_REVOKED`. |

**Không trả lỗi riêng biệt chứa nội dung khóa, decryption plaintext, key source details hay raw token.** Khi cần phân biệt 401 và 403 theo OAuth Bearer error semantics, phải không làm rò thông tin nhạy cảm. Bảo vệ logs/APM/traces và giới hạn request frequency.

### Availability không được thay security

Nếu decryption key store hoặc JWKS tạm không sẵn sàng, **không bỏ một lớp kiểm** để tránh outage. Có thể dùng cached trust keys được bảo vệ và KMS HA theo chính sách; nếu không kiểm đủ, fail closed.

## 29. Ma trận kiểm thử “Validation thứ tự chữ ký và mã hóa”

Giả định chính:

- Orders API chỉ chấp nhận **outer JWE Compact → inner JWS Compact** (sign-then-encrypt).
- Outer JWE profile: `alg=RSA-OAEP-256`, `enc=A256GCM`, `cty=JWT`.
- Inner JWS profile: `alg=RS256`, `typ=at+jwt`, trusted issuer `https://id.example.test`.
- Audience bắt buộc: `orders-api`; GET cần `orders.read`, POST approve cần `orders.approve`.
- Recipient private decryption key và issuer public signing key đến từ **trusted stores**.
- Một tập tests riêng kiểm **encrypt-then-sign profile** được cấu hình tách biệt; không làm Orders API tự chấp nhận hai thứ tự.

### 29.1. Cấu trúc và thứ tự thao tác

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| V01 | Outer JWE hợp lệ chứa inner JWS hợp lệ, claims đúng. | Decrypt/tag verify → JWS verify → claims/auth pass. |
| V02 | Outer JWE có 5 đoạn nhưng tag bị sửa. | Reject trước khi dùng plaintext. |
| V03 | Outer JWE đúng tag nhưng plaintext là JSON unsigned claims. | Reject vì thiếu inner JWS bắt buộc. |
| V04 | Outer JWE đúng tag, plaintext là inner JWS đã sửa payload. | Reject inner signature. |
| V05 | Outer JWE chứa inner JWS có `alg=none`. | Reject, không fallback unsigned. |
| V06 | Outer JWE chứa inner JWS có thuật toán không trong allowlist. | Reject. |
| V07 | Outer JWE dùng `RSA-OAEP-256`/`A256GCM`, inner JWS RS256, token chuẩn. | Pass crypto và các policy riêng. |
| V08 | Gửi trực tiếp JWS Compact không mã hóa đến endpoint yêu cầu nested JWE. | Reject wrong outer format. |
| V09 | Gửi JWE Compact chỉ chứa claims không signed, nhưng `cty=JWT`. | Reject missing inner signing layer. |
| V10 | Gửi outer JWS chứa inner JWE đến endpoint sign-then-encrypt. | Reject wrong nesting order. |
| V11 | Endpoint encrypt-then-sign được cấu hình riêng, nhận outer JWS hợp lệ. | Verify outer JWS **trước** inner JWE decrypt. |
| V12 | Endpoint encrypt-then-sign nhận outer JWS bị sửa signature. | Reject trước decryption. |
| V13 | Endpoint encrypt-then-sign outer JWS đúng, inner JWE tag sai. | Reject inner JWE decryption/authentication. |
| V14 | Endpoint encrypt-then-sign outer JWS đúng nhưng plaintext claims sai `aud`. | Reject claims dù cả crypto layers pass. |
| V15 | Thử fallback hai profile khi profile chính fail. | Reject; không tự nới accepted formats. |
| V16 | Inner JWE lồng thêm JWE ngoài cấu trúc đã đăng ký. | Reject excessive/unsupported nesting. |
| V17 | JWE JSON Serialization gửi tới endpoint chỉ cho Compact. | Reject wrong serialization. |
| V18 | Một đoạn Compact JWE trống/sai dấu chấm. | Reject malformed serialization. |
| V19 | Dấu Base64URL không hợp lệ hoặc JSON header không parse được. | Reject trước cấp quyền. |
| V20 | Hai headers có field mâu thuẫn/duplicate `alg`. | Reject ambiguous policy input. |

### 29.2. Thuật toán, decryption, signature và key trust

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| V21 | Outer JWE khai `alg=RSA1_5` nhưng policy chỉ RSA-OAEP-256. | Reject algorithm downgrade. |
| V22 | Outer JWE khai `alg=dir` trong RSA-OAEP-256-only profile. | Reject. |
| V23 | Outer JWE khai `enc=A128CBC-HS256` khi policy chỉ A256GCM. | Reject unsupported content encryption. |
| V24 | Outer JWE AES-GCM IV hoặc tag bị sửa. | Reject authenticated decryption. |
| V25 | Outer JWE protected header được sửa một byte. | Reject tag/format mismatch. |
| V26 | Outer JWE dùng recipient public key không thuộc Orders API. | Orders private key không decrypt được; reject. |
| V27 | Outer `kid` là issuer signing key ID. | Reject wrong recipient key, không cross-use keys. |
| V28 | Inner `kid` là recipient decryption key ID. | Reject wrong issuer signing key selection. |
| V29 | Inner JWS ký bằng private key attacker. | Reject khi verify bằng issuer public key tin cậy. |
| V30 | Inner JWS có issuer signing `kid` unknown. | Controlled issuer JWKS refresh hoặc reject, không tải attacker key. |
| V31 | Outer JWE `kid` chứa path traversal. | Strict lookup; không file access theo token. |
| V32 | Inner JWS có `jku` trỏ domain attacker. | Không fetch/trust attacker JWKS. |
| V33 | Outer JWE có `jku` hoặc `x5u` dẫn tới mạng nội bộ. | SSRF policy chặn. |
| V34 | Inner JWS header `alg=HS256` khi chỉ cho RS256. | Reject algorithm confusion. |
| V35 | Outer JWE có `cty=JWT` nhưng decrypted payload không phải JWT. | Reject; content type không phải proof. |
| V36 | Inner JWS `typ=JWT` khi profile yêu cầu `at+jwt`. | Reject theo explicit-type policy. |
| V37 | JWS chữ ký đúng nhưng public key thuộc issuer B, token khai issuer A. | Reject cross-issuer trust. |
| V38 | Duplicate `kid` giữa issuer A/B. | Resolver ràng buộc issuer, không global key fallback. |
| V39 | Recipient private key D1 bị compromise. | Incident test bắt buộc key rotation/exposure review, không coi JWS ký là bí mật. |
| V40 | Issuer private signing key S1 bị compromise. | Chặn trust S1 ở RS; JWE encryption không sửa issuer forgery. |

### 29.3. Claims, scope, type, revocation và replay

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| V41 | Outer JWE/inner JWS đều hợp lệ nhưng `iss` sai. | Reject. |
| V42 | Crypto hợp lệ, `aud=payments-api` tại Orders API. | Reject wrong audience. |
| V43 | Crypto hợp lệ, token đã `exp`. | Reject expired. |
| V44 | Crypto hợp lệ, `nbf` ở tương lai. | Reject not yet valid. |
| V45 | Crypto hợp lệ, `iat` quá xa trong tương lai theo token-age policy. | Reject hoặc xử lý theo policy chặt. |
| V46 | Crypto hợp lệ, GET cần `orders.read` nhưng scope thiếu. | Deny insufficient_scope. |
| V47 | Crypto hợp lệ, POST cần `orders.approve` nhưng chỉ có read. | Deny. |
| V48 | Crypto hợp lệ, order thuộc tenant khác. | Deny object/tenant authorization. |
| V49 | Inner là ID token hợp lệ có `aud=orders-web-client`. | Reject token type/audience tại API. |
| V50 | Inner là Logout Token được mã hóa cho Orders API. | Reject wrong token purpose. |
| V51 | Encrypted refresh token gửi như Bearer access token. | Reject tại RS. |
| V52 | JWT token còn hạn nhưng `jti`/grant đã revoked. | RS reject theo revocation policy. |
| V53 | Nested Bearer token bị copy nguyên vẹn và replay. | Crypto vẫn pass; test sender-bound/revoke/TTL policy riêng. |
| V54 | DPoP-bound access token không có DPoP proof. | RS reject dù nested crypto pass. |
| V55 | mTLS-bound access token dùng certificate khác. | RS reject binding mismatch. |
| V56 | OIDC ID token `nonce` sai khi RP đã yêu cầu nonce. | RP reject login. |
| V57 | Token có `scope=orders.read-all`, route cần `orders.read`. | Không substring match; deny. |
| V58 | Token encrypted cho Orders nhưng `aud` thực tế là Payments. | Reject; encryption recipient không thay audience. |
| V59 | Token ký bởi trusted issuer nhưng `client_id` không được phép cho audience/profile. | Deny theo issuer/client policy. |
| V60 | Opaque token giả có ba dấu chấm được gửi tới JWT endpoint. | Không dựa vào dấu chấm; reject format/profile. |

### 29.4. Khả dụng, vận hành và bảo mật xử lý

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| V61 | Recipient decryption key D2 được rotate, token cũ D1 còn hạn. | Normal bounded overlap theo policy hoặc controlled reissue; không dùng sai key. |
| V62 | Issuer signing key S2 được rotate, inner JWT S1 còn hạn. | Trusted issuer JWKS S1+S2 trong normal overlap. |
| V63 | Issuer ký S2 nhưng RS chưa nạp S2. | Controlled refresh; fail closed nếu chưa có trusted key. |
| V64 | Decryption key store outage. | Fail closed hoặc trusted cache/policy; không bỏ decrypt. |
| V65 | Issuer JWKS outage khi inner `kid` unknown. | Reject, không bỏ signature. |
| V66 | JWE ciphertext kích thước rất lớn. | Request size/nesting limits, tránh CPU/memory DoS. |
| V67 | Inner JWT chứa JSON nesting rất sâu hoặc duplicate critical claims. | Reject strict parser, không ambiguous accept. |
| V68 | JWE `zip` làm plaintext phình to. | Reject unsupported compression hoặc limit expansion. |
| V69 | JWE authentication tag sai, server vẫn đọc cached claims. | Security test fail; không fallback cached principal. |
| V70 | Backend trả raw decryption exception về client. | Security test fail; normalize error. |
| V71 | Logs/telemetry chứa full JWE, inner JWS hoặc private keys. | Security/redaction test fail. |
| V72 | Gateway decrypt rồi chuyển user identity qua header không authenticated. | Security test fail; yêu cầu trusted assertion/channel. |
| V73 | Spring Security Test `jwt()` pass route mà decoder chưa decrypt JWE. | Không coi là nested-crypto integration test. |
| V74 | Test JWE crypto pass nhưng token scope/tenant logic chưa chạy. | E2E auth test fail; không đánh dấu đủ validation. |
| V75 | AS revoke token, RS vẫn cho qua do cache trạng thái. | Đo revoke lag; không coi crypto pass là active. |
| V76 | GCM IV bị reuse trái policy trên cùng CEK. | Crypto issuance test fail; kiểm nonce management. |
| V77 | Gửi payload có nested depth vượt giới hạn. | Reject trước recursive processing. |
| V78 | Gửi hàng loạt unknown key IDs để kích JWKS/decrypt-key lookup. | Bounded lookup/rate limits, không DoS. |
| V79 | Sai recipient tenant nhưng key ID giống tenant khác. | Reject cross-tenant key lookup. |
| V80 | Normal key rotation bị chuyển sang compromised key incident. | Dừng overlap không an toàn, loại trust và kiểm mọi RS. |

### Tầng kiểm thử phải tách

- **Crypto unit:** JWE tag verification, inner JWS signature, wrong key/algorithm, tamper từng đoạn, structured parsing.
- **Profile integration:** sign → encrypt và encrypt → sign như **hai hợp đồng tách biệt**, `cty`/`typ`/nesting-depth enforcement.
- **OAuth/RS integration:** issuer, audience, scope, exp/nbf, type confusion, tenant/owner, DPoP/mTLS và revoke.
- **OIDC/RP integration:** encrypted/signed ID token, client audience, nonce, time/hash claims theo flow.
- **Key-management:** signing JWKS và recipient decryption key rotation độc lập, caches, emergency compromise.
- **Resilience:** JWKS/KMS downtime, unknown kid floods, size limits, compression bombs và rate limits.
- **Forensics/privacy:** normalized errors, no raw token/key logs, tracing boundaries.

**Phải có ít nhất một bài kiểm thử end-to-end với outer JWE thật và inner JWS thật**, sử dụng **test keys tách issuer/recipient**; chỉ mock `Jwt` hoặc claims không chứng minh thứ tự xác minh mật mã đúng.

## 30. Runbook phát hành nested JWT an toàn

Một AS phát sign-then-encrypt access JWT nên:

1. **Xác định token profile** và đối tượng nhận: issuer, client, RS audience, loại token.
2. **Xây claims tối thiểu**: `iss`, `sub` khi có user, `aud`, `exp`/`iat`, `scope`/`client_id` theo profile.
3. **Ký inner JWS** bằng private signing key đúng issuer, algorithm allowlist và `kid`.
4. **Mã hóa toàn bộ inner JWS** với public encryption key của recipient được AS tin/đăng ký; không nhận arbitrary public key từ client request.
5. Đặt outer `alg`/`enc`/`cty`/`kid` theo JOSE profile.
6. Kiểm output JWE serialization, IV/CEK randomness và library integrity.
7. Phát token qua **TLS**, không đưa raw token vào logs/URLs/referrer.
8. Lưu grant/token reference để hỗ trợ revoke, audit và key rotation.
9. Monitor thuật toán và key version của từng token class mà không log ciphertext/claims.

Với encrypt-then-sign, issuer phải **đổi rõ profile**: mã hóa trước rồi ký serialized JWE, không chỉ thêm chữ ký ở một tầng không nhất quán. **Không phát nhiều format không có agreement** vì recipient dễ bị downgrade.

## 31. Runbook resource server nhận nested JWT

### Trước khi đưa vào production

- [ ] Có một **accepted outer format** và thứ tự bảo vệ được xác định theo API.
- [ ] Có trusted issuer và trusted recipient decryption key store.
- [ ] Có allowlist riêng outer JWE `alg`/`enc` và inner JWS `alg`.
- [ ] Có `cty`/`typ`/key ID/token profile policy.
- [ ] Có size/nesting-depth/critical-header limits.
- [ ] Có unit/integration tests với token được ký/mã hóa thật.
- [ ] Có revocation, audience, scope, tenant/owner authorization.
- [ ] Có key rotation/runbook và giải pháp khi KMS/JWKS lỗi.
- [ ] Có logging redaction và error normalization.

### Khi xử lý một request

- [ ] Reject oversized/unexpected token form sớm.
- [ ] Resolve outer decryption key trong trusted recipient key ring.
- [ ] Decrypt + verify outer JWE authentication tag.
- [ ] Verify inner signature bằng issuer trusted signing key.
- [ ] Validate inner token type, `iss`, `aud`, `exp`/`nbf` và scope.
- [ ] Enforce revoke/sender constraints/object authorization.
- [ ] Chỉ lúc đó mới tạo principal và cho phép API operation.
- [ ] Không cache unverified claims hoặc raw plaintext vào telemetry.

### Khi xảy ra lỗi

- [ ] Dừng tại lớp lỗi; không fallback sang unsigned/unencrypted token.
- [ ] Không thử thứ tự mã hóa/ký khác khi profile không cho phép.
- [ ] Không trả plaintext/private key/kid trust details cho caller.
- [ ] Dùng error code thống nhất cho invalid token; alert ở kênh nội bộ.
- [ ] Nếu key compromise, dùng emergency trust removal chứ không nới thuật toán.

## 32. Các tình huống thực hành

### Tình huống A — Giải mã đúng, nhưng inner JWT không có chữ ký

Một nhà tích hợp mã hóa JSON claims trực tiếp bằng RSA public key của Orders API. API decrypt thành công, AES-GCM tag đúng và nhận `role=ADMIN`.

**Câu hỏi:** Có chấp nhận theo nested sign-then-encrypt profile không?

> **Không.** JWE authentication tag chỉ chứng minh ciphertext hợp lệ theo cơ chế mã hóa, không chứng minh issuer đã ký claims. Profile yêu cầu **inner JWS signature**; thiếu JWS là token sai định dạng bảo mật.

### Tình huống B — Inner JWS đúng, outer JWE gửi sai recipient

Issuer ký access JWT đúng `aud=orders-api` nhưng mã hóa bằng Payments API public key.

**Câu hỏi:** Orders có được lấy private key Payments dùng chung để decrypt không?

> **Không** nếu trust contract không cho phép. Recipient decryption key là ranh giới riêng. Phải phát token bằng key của Orders hoặc sử dụng cơ chế token exchange/registered recipients theo chính sách.

### Tình huống C — Ký rồi mã hóa, API verify “outer signature” trước

Token hợp lệ là JWE 5 đoạn chứa inner JWS. Developer gọi `SignedJWT.parse(outerToken)` trước.

**Câu hỏi:** Vấn đề ở đâu?

> Định dạng outer là JWE, không có outer JWS để verify. Phải **decrypt outer JWE + check tag**, sau đó mới parse/verify inner JWS. Không tự “chữa” bằng cách bỏ signature.

### Tình huống D — Mã hóa rồi ký, API decrypt trước

Một token được profile encrypt-then-sign có outer JWS 3 đoạn. API cố decrypt raw chuỗi outer như JWE.

**Câu hỏi:** Đúng thứ tự xử lý không?

> **Không.** Outer JWS phải được verify với trusted issuer key trước; payload đã verify mới là serialized inner JWE để decrypt. Không dùng sign-then-encrypt parser cho profile khác.

### Tình huống E — ID token bị bọc trong JWE của API

OP ký ID token đúng, attacker (hoặc client thiếu kiểm soát) mã hóa nó cho Orders API; RS giải mã và thấy cùng `sub`.

**Câu hỏi:** Có phải access token không?

> **Không.** ID token hướng tới RP client, không phải resource server. API phải kiểm token type/profile và audience, không cho việc mã hóa làm thay mục đích sử dụng.

### Tình huống F — Bearer JWE bị sao chép

Attacker không đọc được ciphertext nhưng có bản sao nguyên vẹn của JWE access token còn hạn.

**Câu hỏi:** Có cần phá mã để gọi API không?

> **Không.** Với Bearer token, chỉ cần gửi nguyên bản tới RS nếu không có sender constraints. JWS/JWE vẫn có thể valid. Cần bảo vệ storage, revoke, TTL, scope/audience và DPoP/mTLS khi áp dụng.

### Tình huống G — Issuer signing key rotate, recipient decryption key không đổi

AS chuyển S1 → S2, Orders giữ decryption D1. Token mới JWE decrypt được nhưng inner JWS có `kid=S2` không tìm thấy.

**Câu hỏi:** Cần kiểm ở đâu?

> **Issuer signing JWKS** và signed-key grace/prepublication, **không phải** recipient decryption key D1. Hai key rings độc lập.

### Tình huống H — Recipient private key D1 bị lộ

Orders API bị lộ private decryption key D1 nhưng issuer signing key S1 vẫn an toàn.

**Câu hỏi:** Có bảo đảm JWT còn bí mật không?

> **Không.** Bất kỳ ai có D1 và bản sao ciphertext mã hóa cho D1 có thể đọc plaintext, gồm inner JWT. Cần emergency decryption-key rotation, reissue tokens, exposure assessment và tiếp tục kiểm issuer JWS signature. Chỉ thay S1 không xóa khả năng decrypt dữ liệu cũ đã sao chép.

### Tình huống I — Gateway đã giải mã, microservice tin `X-User-Role`

Gateway xử lý nested JWT rồi gửi header `X-User-Role: ADMIN` đến service nội bộ. Internet client cũng có thể tự đặt header này trên đường đi khác.

**Câu hỏi:** Thiếu bảo vệ gì?

> Thiếu **identity assertion/channel binding** từ gateway tới RS. Cần ngăn header spoofing, giới hạn ingress, xác thực mutual service identity và ký/chứng thực assertion nếu qua trust boundary; không lấy header user-controlled thay việc verify token.

### Tình huống J — Tag fail nhưng hệ thống trả claims đã cache

Một JWE bị sửa tag nhưng hệ thống lấy claims cũ theo `jti` cache và cho qua.

**Câu hỏi:** Có thể chấp nhận không?

> **Không.** JWE không được xác thực, token hiện tại phải bị reject. Unverified ciphertext/header không được dùng làm key để khôi phục một principal mà bypass required crypto chain.

## 33. Tự đánh giá

1. JWS và JWE khác nhau ở tính chất bảo mật nào?
2. Tại sao Base64URL decode hoặc decrypt thành công không đồng nghĩa issuer đã ký?
3. Một sign-then-encrypt JWT có outer/inner format gì?
4. Vì sao recipient phải decrypt outer JWE rồi mới verify inner JWS?
5. Với encrypt-then-sign, thao tác crypto nào phải đứng đầu?
6. Những trường nào của outer JWE header khác inner JWS header?
7. `alg` trong JWE khác `alg` của JWS ở vai trò gì?
8. Vì sao `cty=JWT` không tự chứng minh inner JWT hợp lệ?
9. Tại sao `typ=at+jwt` và `aud` đều cần kiểm?
10. Khi RSA public encryption key công khai, ai có thể tạo ciphertext mã hóa hợp lệ cho recipient?
11. Khi nào JWE-only được phép dùng, và cần profile/issuer-auth guarantee nào?
12. Vì sao không thể “thử cả hai thứ tự” trên cùng một endpoint?
13. Tại sao `kid` của outer JWE không được dùng để chọn issuer signing key?
14. Những nguy cơ từ `jku`/`x5u`/unknown `kid` là gì?
15. JWE authentication tag cần được xác minh trước khi xử lý gì?
16. Nested JWT có tự ngăn Bearer replay hay token theft không?
17. Signing-key rotation và decryption-key rotation khác nhau ở ảnh hưởng?
18. Spring `issuer-uri` mặc định có đủ xử lý nested JWE không?
19. OIDC ID token có thể được dùng như access token nếu inner JWS đúng và outer JWE decrypt được không?
20. Những end-to-end tests nào chứng minh đúng thứ tự ký/mã hóa và đúng resource authorization?

## 34. Ghi nhớ

- **Thứ tự validation là chiều ngược của cách bọc bảo vệ**: sign → encrypt thì recipient **decrypt JWE/tag rồi verify JWS**; encrypt → sign thì **verify outer JWS rồi decrypt inner JWE**.
- **Không tự động nhận cả hai thứ tự**. Token profile, outer format, key/algorithm allowlists và nested depth phải được cấu hình rõ.
- **JWE confidentiality + integrity không mặc nhiên chứng minh AS phát token**, nhất là khi public encryption key của recipient có thể được mọi người dùng để mã hóa.
- **Inner issuer JWS signature phải được verify bằng trusted issuer public key** nếu profile yêu cầu.
- **`cty=JWT`/`typ=at+jwt` là tín hiệu profile phải được validate**, không phải quyền cấp truy cập tự thân.
- **Khóa issuer ký và khóa recipient giải mã là hai trust boundaries**; `kid`/`alg`/JWKS không được trộn hoặc tải từ URL do attacker điều khiển.
- **Không dùng claims trước khi tất cả lớp bảo vệ bắt buộc đã được xác minh**. Parsing không phải authentication.
- **Crypto pass vẫn phải kiểm `iss`, `aud`, `exp`, `nbf`, type, `scope`, tenant/owner, revocation và sender proof**.
- **ID token dành cho RP, access token dành cho RS**; mã hóa ID token không biến nó thành bearer access token.
- **Opaque token dùng introspection/status**, không áp JOSE parser bằng cách đoán số dấu chấm.
- **Nested JWT vẫn có thể bị replay khi bị sao chép nguyên vẹn**; TLS, storage, scope/audience, TTL, revoke và DPoP/mTLS là các lớp bổ sung.
- **Spring Security JWT decoder thông thường không được mặc định coi là nested JWE validator**; cần triển khai theo profile và test crypto thật.
- **Khi key compromise hoặc JWKS/KMS lỗi, fail closed**; không bỏ signature, decryption tag hoặc nhận token dạng khác để tránh 401.
- **Không log outer JWE, inner JWS, plaintext claims nhạy cảm hay private keys**.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact Serialization, signing input, protected header và signature validation.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Compact, `alg`/`enc`, authentication tag, encryption/decryption.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): JWS signing và JWE key management/content encryption algorithms.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và §11.2 **Signing and Encryption Order**.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): issuer signing keys, recipient public/private keys, `kid`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): validate all cryptographic operations, explicit typing, algorithm/key confusion, mutually exclusive JWT rules.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `at+jwt`, issuer/audience/scope, RS access-token validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): trusted issuer và JWKS discovery.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token theft, replay, refresh-token rotation và sender constraints.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer transport, `invalid_token`, `insufficient_scope`, token leakage.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): opaque token/status/revocation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): encrypted/signed ID tokens, registration/validation, issuer/audience/nonce.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained access tokens.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, trusted issuer/JWKS và claims validation.
- [Nimbus JOSE + JWT documentation](https://connect2id.com/products/nimbus-jose-jwt): JOSE/JWT parsing, JWS signing/verification và JWE encryption/decryption APIs.
