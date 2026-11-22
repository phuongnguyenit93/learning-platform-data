# ECDSA và nhóm thuật toán ES256, ES384, ES512

## 1. ECDSA trong hệ sinh thái JWT

Trong **Security - JSON Web Token (JWT)**, một bên phát hành thường cần ký token để bên nhận có thể kiểm tra tính toàn vẹn và nguồn phát hành. Khi token được biểu diễn theo chuẩn **JSON Web Signature (JWS)**, nhóm `ES256`, `ES384`, `ES512` sử dụng **ECDSA (Elliptic Curve Digital Signature Algorithm)**: thuật toán chữ ký số dựa trên đường cong elliptic.

ECDSA là cơ chế khóa công khai:

- **Khóa riêng (private key):** một số nguyên bí mật `d`, dùng để tạo chữ ký.
- **Khóa công khai (public key):** một điểm trên đường cong `Q = dG`, dùng để xác minh chữ ký.
- Bên chỉ có public key có thể xác minh token nhưng không thể tạo chữ ký mới tương ứng với private key trong điều kiện bảo mật thông thường.

Mô hình này phù hợp khi một issuer phát hành JWT cho nhiều API độc lập. Issuer giữ private key; các API nhận public key từ nguồn tin cậy để xác minh. So với HMAC, các API xác minh không cần giữ bí mật có khả năng phát hành token.

Chữ ký ECDSA **không mã hóa JWT**. Trong JWS Compact, header và payload thường chỉ được biểu diễn bằng Base64URL nên người có token có thể đọc claims. Nếu dữ liệu cần được giữ bí mật, hãy giới hạn thông tin đưa vào token hoặc sử dụng cơ chế mã hóa phù hợp như JWE.

Bài thuộc chương **Thuật toán chữ ký** của module **Security - JSON Web Token (JWT)**. Phạm vi gồm nguyên lý ECDSA, ánh xạ ES256/384/512 theo JWA, định dạng chữ ký JWS, quản lý khóa, xác minh và các lỗi triển khai; nội dung không phụ thuộc Java hay framework cụ thể.

## 2. Nền tảng ECDSA

### 2.1. Đường cong elliptic và cặp khóa

ECDSA hoạt động trên một đường cong elliptic được xác định bởi các tham số toán học, trường hữu hạn và một điểm sinh `G` có cấp `n`. Có thể hình dung:

- `d`: khóa riêng, một số nguyên trong khoảng `1 <= d < n`.
- `G`: điểm sinh đã được chuẩn hóa của đường cong.
- `Q = dG`: khóa công khai, tức phép nhân điểm `G` với số nguyên `d`.

Phép toán nhân điểm trên đường cong elliptic có tính một chiều thực tế: biết `G` và `Q` không giúp tìm `d` khi đường cong và kích thước khóa được chọn an toàn. Độ an toàn phụ thuộc vào việc chọn đúng đường cong, sinh khóa tốt và bảo vệ private key.

### 2.2. Cách tạo chữ ký

Với thông điệp `M`, hàm băm `H`, khóa riêng `d`, điểm sinh `G` và cấp `n`, quy trình ECDSA ở mức khái niệm:

```text
z = integer derived from H(M)
choose secret nonce k, where 1 <= k < n
R = kG
r = x-coordinate(R) mod n
s = k^(-1) * (z + r*d) mod n

signature = (r, s)
```

Nếu `r = 0` hoặc `s = 0`, phải chọn nonce khác và tính lại. Nonce `k` là giá trị tạm thời bí mật dùng cho mỗi chữ ký. **Không được tái sử dụng nonce hoặc tạo nonce có thể đoán/thiên lệch**: nếu cùng `k` được dùng để ký hai thông điệp khác nhau, kẻ tấn công có thể suy ra khóa riêng từ các chữ ký.

### 2.3. Cách xác minh chữ ký

Verifier nhận thông điệp, chữ ký `(r,s)` và public key `Q`. Sau khi kiểm tra `1 <= r,s < n`, quy trình khái niệm là:

```text
z  = integer derived from H(M)
w  = s^(-1) mod n
u1 = z*w mod n
u2 = r*w mod n
X  = u1*G + u2*Q
v  = x-coordinate(X) mod n

signature is valid when v == r
```

Đây là mô tả toán học để hiểu nguyên lý, không phải hướng dẫn tự viết primitive mật mã. Thư viện mật mã đáng tin cậy phải xử lý đầy đủ kiểm tra điểm, miền giá trị, phép toán modulo và các chi tiết triển khai.

## 3. ES256, ES384 và ES512 theo JWA

**JSON Web Algorithms (JWA), RFC 7518, mục 3.4** định nghĩa nhóm ECDSA cho JWS như sau:

| Giá trị `alg` | Đường cong elliptic | Hàm băm | Độ rộng mỗi số `R` hoặc `S` |
| --- | --- | --- | --- |
| `ES256` | NIST P-256 (secp256r1) | SHA-256 | 32 byte |
| `ES384` | NIST P-384 (secp384r1) | SHA-384 | 48 byte |
| `ES512` | NIST P-521 (secp521r1) | SHA-512 | 66 byte |

**ES512 dùng đường cong P-521**, không phải một đường cong có kích thước 512 bit. Tên ES512 phản ánh việc sử dụng hàm băm SHA-512; đường cong tương ứng được JWA quy định là P-521.

### 3.1. Kích thước chữ ký

Mỗi chữ ký ECDSA gồm hai số nguyên `R` và `S`. JWS quy định mỗi số được biểu diễn bằng số byte cố định theo độ rộng của đường cong, rồi nối hai phần:

```text
signature = I2OSP(R, coordinateWidth)
         || I2OSP(S, coordinateWidth)
```

Trong đó `I2OSP` chuyển số nguyên không dấu thành chuỗi byte big-endian có độ rộng cố định; `||` là phép nối byte.

| Thuật toán | Độ rộng R | Độ rộng S | Chữ ký nhị phân R || S | Base64URL không padding |
| --- | ---: | ---: | ---: | ---: |
| `ES256` | 32 byte | 32 byte | 64 byte | 86 ký tự |
| `ES384` | 48 byte | 48 byte | 96 byte | 128 ký tự |
| `ES512` | 66 byte | 66 byte | 132 byte | 176 ký tự |

Các số nguyên được mã hóa theo độ rộng cố định, vì vậy cần thêm byte `0x00` ở đầu nếu giá trị có ít byte hơn độ rộng quy định. Với P-521, mỗi tọa độ cần 66 byte dù đường cong có 521 bit; các bit cao không sử dụng phải được xử lý theo quy tắc mã hóa của chuẩn.

### 3.2. Độ dài chữ ký không phải độ dài digest

Hậu tố trong tên thuật toán cho biết hàm băm được dùng:

- ES256: SHA-256 cho digest 32 byte.
- ES384: SHA-384 cho digest 48 byte.
- ES512: SHA-512 cho digest 64 byte.

Nhưng độ dài chữ ký JWS được quyết định bởi độ rộng tọa độ của đường cong và luôn gồm hai phần R, S. Vì vậy chữ ký ES512 dài 132 byte, không phải 64 byte. Không thể lấy độ dài digest làm kích thước chữ ký.

## 4. Định dạng chữ ký ECDSA trong JWS: R || S

### 4.1. JWS dùng biểu diễn nhị phân cố định

Một điểm rất quan trọng khi tích hợp ECDSA với JWT là **JWS không lưu chữ ký dưới dạng ASN.1 DER**. JWS yêu cầu nối hai số nguyên R và S thành một chuỗi byte có độ dài cố định:

```text
R = fixed-width unsigned big-endian integer
S = fixed-width unsigned big-endian integer
JWS signature bytes = R || S
```

Ví dụ với ES256:

```text
R: 32 byte
S: 32 byte
signature: 64 byte
JWS segment: BASE64URL(signature)
```

Nhiều API mật mã tổng quát trả chữ ký ECDSA ở dạng **ASN.1 DER**, thường là một SEQUENCE chứa hai INTEGER. DER là định dạng có cấu trúc và độ dài biến thiên; số nguyên dương có bit cao nhất bằng 1 có thể cần thêm byte `0x00` đầu để biểu diễn dấu. Vì thế DER không thể đưa thẳng vào đoạn chữ ký JWS.

Khi dùng API trả DER, lớp tích hợp JOSE phải:

1. Parse DER theo ASN.1 một cách nghiêm ngặt để lấy hai số nguyên R và S.
2. Xác thực chúng là số nguyên không âm, nằm trong miền hợp lệ của đường cong.
3. Mã hóa R và S thành hai chuỗi byte không dấu, big-endian, đúng độ rộng cố định.
4. Nối R với S, rồi Base64URL để tạo đoạn chữ ký JWS.

Khi xác minh, chiều chuyển đổi có thể ngược lại nếu thư viện mật mã chỉ nhận DER: giải mã Base64URL, tách R/S theo độ rộng, tạo biểu diễn mà API yêu cầu, sau đó xác minh bằng đúng đường cong và hàm băm. Thư viện JOSE chuyên dụng thường đã xử lý chuyển đổi này.

### 4.2. Ví dụ về lỗi DER và raw signature

Giả sử một API trả chữ ký ES256 dạng DER có cấu trúc:

```text
SEQUENCE {
  INTEGER R
  INTEGER S
}
```

Độ dài DER thay đổi tùy cách biểu diễn INTEGER. JWS lại yêu cầu đúng 64 byte cho ES256. Nếu đưa toàn bộ DER vào Base64URL và ghép thành JWT, verifier tuân thủ JWA sẽ từ chối vì định dạng và độ dài chữ ký sai.

Đây là một trong những lỗi liên thông phổ biến nhất khi tự kết nối thư viện ECDSA tổng quát với định dạng JOSE. Cần xác nhận API đang trả **DER hay raw R||S**, không chỉ nhìn tên “ECDSA signature”.

## 5. Cách ECDSA được dùng để ký JWT

### 5.1. Ba phần của JWS Compact

JWT có chữ ký dạng JWS Compact gồm:

```text
BASE64URL(UTF8(protectedHeaderJSON))
.
BASE64URL(UTF8(payloadJSON))
.
BASE64URL(signatureBytes)
```

Ví dụ protected header trước khi mã hóa:

```json
{
  "alg": "ES256",
  "typ": "JWT",
  "kid": "issuer-ec-signing-2026-11"
}
```

Ví dụ payload trước khi mã hóa:

```json
{
  "iss": "https://identity.example",
  "sub": "user-123",
  "aud": "orders-api",
  "iat": 1893452400,
  "exp": 1893456000
}
```

Đây là dữ liệu minh họa. `iat` và `exp` là **NumericDate**, tính theo giây từ Unix epoch. `kid` là định danh khóa; `typ` hỗ trợ phân biệt loại token. Header chỉ là dữ liệu chưa xác thực cho đến khi chữ ký hợp lệ.

Base64URL là cách biểu diễn dữ liệu an toàn cho URL, không phải mã hóa bí mật. Người có JWT vẫn có thể giải mã header và payload để đọc nội dung.

### 5.2. Signing input

JWS ký chính xác chuỗi byte tạo từ hai đoạn đầu:

```text
header64  = BASE64URL(UTF8(protectedHeaderJSON))
payload64 = BASE64URL(UTF8(payloadJSON))

signingInput = ASCII(header64 + "." + payload64)
```

Ví dụ ký ES256:

```text
(R, S) = ECDSA_SIGN(
    privateKey_P256,
    signingInput,
    SHA-256
)

signatureBytes = I2OSP(R, 32) || I2OSP(S, 32)
signature64 = BASE64URL(signatureBytes)

jwt = header64 + "." + payload64 + "." + signature64
```

Với ES384, dùng P-384/SHA-384 và độ rộng 48 byte cho R, S. Với ES512, dùng P-521/SHA-512 và độ rộng 66 byte cho mỗi số.

```mermaid
flowchart TD
    H[Protected header JSON] --> HE[UTF-8 và Base64URL]
    P[Payload JSON] --> PE[UTF-8 và Base64URL]
    HE --> I[header64.payload64]
    PE --> I
    I --> S[ECDSA với curve và SHA tương ứng]
    K[Private key EC] --> S
    N[Nonce an toàn cho mỗi lần ký] --> S
    S --> RS[Hai số R và S]
    RS --> RAW[Fixed-width R || S]
    RAW --> B[Base64URL chữ ký]
    I --> T[JWT ba đoạn]
    B --> T
```

### 5.3. Vì sao phải giữ nguyên signing input?

Thứ tự trường JSON, khoảng trắng, cách escape và cách biểu diễn số có thể làm thay đổi byte của header hoặc payload. Do đó verifier phải dùng **nguyên văn hai đoạn Base64URL đầu tiên** của token để dựng signing input; không parse JSON rồi serialize lại để tự tạo chuỗi ký.

Nếu payload bị sửa, signing input thay đổi và chữ ký ECDSA cũ sẽ không còn hợp lệ. Người chỉ có public key không thể tạo chữ ký mới cho nội dung giả mạo.

## 6. Phát hành và xác minh JWT bằng ECDSA

### 6.1. Quy trình phát hành

1. Chọn thuật toán từ cấu hình issuer, ví dụ ES256; không để token tự chọn thuật toán ký.
2. Lấy private key đúng đường cong theo JWA: P-256 cho ES256, P-384 cho ES384, P-521 cho ES512.
3. Tạo header với `alg` cố định và `kid` tương ứng khóa.
4. Tạo claims cần thiết như `iss`, `sub`, `aud`, `iat`, `exp` và quyền tối thiểu.
5. Tạo signing input từ hai đoạn Base64URL.
6. Ký bằng ECDSA với hàm băm tương ứng và nonce được tạo an toàn.
7. Chuyển kết quả thành raw R||S đúng độ rộng JWA, Base64URL và ghép JWT.

Mã giả:

```text
function issueJwt(claims, signerConfig):
    require signerConfig.algorithm in {ES256, ES384, ES512}
    require signerConfig.privateKey.curve ==
            curveFor(signerConfig.algorithm)

    header = {
        "alg": signerConfig.algorithm,
        "typ": "JWT",
        "kid": signerConfig.keyId
    }

    header64 = BASE64URL(UTF8(JSON_SERIALIZE(header)))
    payload64 = BASE64URL(UTF8(JSON_SERIALIZE(claims)))
    signingInput = ASCII(header64 + "." + payload64)

    (R, S) = ECDSA_SIGN(
        signerConfig.privateKey,
        signingInput,
        hashFor(signerConfig.algorithm),
        secureNonceGeneration
    )

    width = coordinateWidth(signerConfig.algorithm)
    rawSignature = I2OSP(R, width) || I2OSP(S, width)

    return header64 + "." + payload64 + "." + BASE64URL(rawSignature)
```

Mã giả mô tả logic định dạng, không phải khuyến nghị tự triển khai ECDSA hoặc tự sinh nonce.

### 6.2. Quy trình xác minh

1. Giới hạn kích thước token và parse JWS Compact thành đúng ba đoạn.
2. Parse protected header nhưng coi là dữ liệu chưa xác thực. Kiểm tra `alg` thuộc allowlist của verifier.
3. Xác định đường cong đúng với thuật toán và tìm public key từ tập khóa đã được tin cậy cho issuer.
4. Kiểm tra public key là điểm hợp lệ trên đúng đường cong; kiểm tra `kid`, issuer, mục đích sử dụng và thuật toán được phép.
5. Dựng signing input bằng nguyên văn `header64.payload64`.
6. Giải mã chữ ký Base64URL; xác nhận độ dài đúng 64, 96 hoặc 132 byte theo thuật toán.
7. Tách hai phần R và S, kiểm tra miền giá trị, rồi xác minh ECDSA bằng đúng curve và SHA tương ứng.
8. Chỉ sau khi chữ ký hợp lệ mới kiểm tra claims và quyết định cấp quyền.

Mã giả:

```text
function verifyJwt(token, policy, trustedKeySet):
    (header64, payload64, signature64) = parseThreeSegmentsStrictly(token)
    header = parseProtectedHeader(BASE64URL_DECODE(header64))

    require header.alg in policy.allowedAlgorithms
    require header.alg in {ES256, ES384, ES512}
    require no unsupported critical header parameters

    curve = curveFor(header.alg)
    publicKey = trustedKeySet.find(
        issuer = policy.expectedIssuer,
        kid = header.kid,
        algorithm = header.alg
    )

    require publicKey exists
    require publicKey.type == EC
    require publicKey.curve == curve
    require publicKey is trusted for this issuer and purpose
    require publicKey is a valid point on curve

    rawSignature = BASE64URL_DECODE(signature64)
    width = coordinateWidth(header.alg)
    require length(rawSignature) == 2 * width

    R = OS2IP(rawSignature[0:width])
    S = OS2IP(rawSignature[width:2*width])
    require 1 <= R < curve.order
    require 1 <= S < curve.order

    signingInput = ASCII(header64 + "." + payload64)
    require ECDSA_VERIFY(
        publicKey,
        signingInput,
        (R, S),
        hashFor(header.alg)
    )

    claims = parseAndValidateJson(BASE64URL_DECODE(payload64))
    require claims.iss == policy.expectedIssuer
    require claims.aud contains policy.expectedAudience
    require claims.exp is valid and now < claims.exp
    require claims.nbf absent or now >= claims.nbf
    require token type, subject, scopes and other policy checks pass

    return claims
```

Đây là mã giả mô tả các kiểm tra chính. Trong triển khai thật, hãy dùng thư viện JOSE/JWT đã được kiểm chứng để xử lý Base64URL, JSON, curve point validation, chuyển đổi raw signature và phép xác minh. Nếu loại token yêu cầu `exp`, phải từ chối khi claim vắng mặt; xử lý NumericDate theo giây UTC và chỉ chấp nhận clock skew nhỏ theo chính sách.

### 6.3. Chữ ký hợp lệ chưa đủ để cấp quyền

| Kiểm tra | Câu hỏi | Ví dụ từ chối |
| --- | --- | --- |
| Chữ ký ECDSA | Nội dung có được ký bằng private key tương ứng public key tin cậy? | Payload bị sửa, chữ ký sai hoặc curve không khớp |
| `iss` | Token do issuer nào phát hành? | Issuer không được tin cậy |
| `aud` | Token dành cho dịch vụ nào? | Token dành cho API khác |
| `exp`, `nbf` | Token có hiệu lực tại thời điểm hiện tại? | Hết hạn hoặc chưa đến thời điểm hiệu lực |
| Loại token | Đây có đúng loại credential mà endpoint yêu cầu? | ID token bị dùng thay access token |
| Scope/role | Chủ thể có quyền thực hiện thao tác? | Thiếu quyền truy cập tài nguyên |

Ví dụ, token ES256 có chữ ký hợp lệ nhưng `aud` là `orders-api` không được chấp nhận tại `billing-api` nếu API này yêu cầu audience riêng.

## 7. Quản lý khóa EC và JWK/JWKS

### 7.1. Sinh và bảo vệ khóa

- Sinh khóa bằng thư viện mật mã đáng tin cậy và nguồn ngẫu nhiên an toàn; chọn đúng đường cong được JWA yêu cầu.
- Bảo vệ private key trong KMS, HSM hoặc secret manager phù hợp; giới hạn quyền ký theo nguyên tắc ít quyền nhất.
- Không đưa private key vào source code, Git, log, URL, payload JWT hoặc cấu hình công khai.
- Tách khóa theo môi trường, issuer, tenant hoặc mục đích khi cần.
- Có quy trình luân chuyển và xử lý khi nghi ngờ private key bị lộ.
- Giám sát hoạt động ký và hạn chế người/dịch vụ có thể sử dụng private key.

### 7.2. JWK cho khóa Elliptic Curve

**JSON Web Key (JWK)** mô tả khóa EC bằng các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `kty` | Loại khóa, phải là `EC` |
| `crv` | Tên đường cong: `P-256`, `P-384` hoặc `P-521` |
| `x` | Tọa độ X của public point, Base64URLUInt |
| `y` | Tọa độ Y của public point, Base64URLUInt |
| `d` | Thành phần private key; không được công bố trong public JWKS |
| `kid` | Định danh khóa |
| `use` | Mục đích, thường là `sig` |
| `alg` | Thuật toán dự kiến, nếu có |

Ví dụ public JWK minh họa:

```json
{
  "kty": "EC",
  "crv": "P-256",
  "kid": "issuer-ec-signing-2026-11",
  "use": "sig",
  "alg": "ES256",
  "x": "<base64url-x-coordinate>",
  "y": "<base64url-y-coordinate>"
}
```

Các giá trị tọa độ chỉ là placeholder. Public JWK chỉ cần `kty`, `crv`, `x`, `y` cùng metadata tùy chọn. Thành phần `d` là bí mật và không được xuất hiện trong public JWKS.

**JWKS (JSON Web Key Set)** là tập hợp các JWK, thường được issuer công bố tại endpoint HTTPS đã được cấu hình tin cậy. Verifier phải gắn key set với đúng issuer; không được để header chưa xác thực tự chọn URL tải public key.

### 7.3. Luân chuyển khóa

Một quy trình rotation có kế hoạch:

1. Tạo cặp khóa EC mới trên đúng đường cong và bảo vệ private key.
2. Công bố public JWK mới trong JWKS để verifier có thời gian cập nhật.
3. Trong thời gian chuyển tiếp, giữ public key cũ và mới; issuer chuyển sang ký bằng private key mới và gắn `kid` mới.
4. Chờ token ký bằng khóa cũ hết hạn, cộng clock skew/độ trễ được phép.
5. Gỡ public key cũ khỏi verifier/JWKS và xử lý private key cũ theo chính sách.

Nếu private key bị lộ, cần ngừng tin tưởng khóa đó, đánh giá token bị ảnh hưởng và thu hồi phiên/token liên quan theo cơ chế hệ thống. Tạo khóa mới nhưng vẫn chấp nhận public key cũ không giải quyết được việc kẻ tấn công tiếp tục ký token giả.

### 7.4. Ràng buộc kid, curve và alg

`kid` chỉ là chỉ mục tra cứu. Verifier phải ràng buộc khóa được chọn với issuer, mục đích, đường cong và thuật toán:

- ES256 chỉ đi với P-256.
- ES384 chỉ đi với P-384.
- ES512 chỉ đi với P-521.

Không chấp nhận khóa EC có đường cong tùy ý hoặc tự chuyển sang đường cong khác chỉ vì token khai báo `alg`. Không dùng `kid` làm tên file/đường dẫn hoặc URL không kiểm soát. Không tải `jku` hay `x5u` tùy ý từ header do người gửi token kiểm soát; hành vi này có thể dẫn đến thay thế khóa hoặc SSRF.

## 8. Nonce, tính ngẫu nhiên và an toàn triển khai

### 8.1. Nonce ECDSA là bí mật tạm thời

Nonce `k` cần được bảo vệ nghiêm ngặt như một bí mật dùng một lần:

- Không được tái sử dụng cùng một `k` cho hai thông điệp.
- Không được tạo nonce từ timestamp, bộ đếm dễ đoán, PRNG thông thường hoặc dữ liệu do người dùng kiểm soát.
- Không được để nonce có phân bố thiên lệch hoặc rò rỉ qua log, lỗi, bộ nhớ hay kênh thời gian.
- Sử dụng cơ chế tạo nonce đã được thư viện mật mã kiểm chứng.

Nếu cùng nonce `k` ký hai digest khác nhau, hai phương trình chữ ký có thể cho phép suy ra `k`, sau đó tính được private key `d`. Vì vậy lỗi nonce có thể phá vỡ hoàn toàn bảo mật của khóa, dù thuật toán băm và đường cong đều mạnh.

### 8.2. ECDSA xác định theo RFC 6979

RFC 6979 mô tả cách sinh nonce ECDSA **xác định** từ private key và digest bằng HMAC, loại bỏ phụ thuộc vào nguồn ngẫu nhiên trong mỗi lần ký. Cách này có thể giảm rủi ro do RNG yếu nếu được triển khai đúng, nhưng không có nghĩa ứng dụng nên tự viết bộ sinh nonce.

Dù dùng nonce ngẫu nhiên hay xác định, cần thư viện mật mã đáng tin cậy, bảo vệ private key và kiểm tra khả năng tương thích của hệ thống. Với PSS, salt ngẫu nhiên có vai trò khác; không nhầm salt của RSA-PSS với nonce ECDSA.

### 8.3. Kiểm tra public point và triển khai an toàn

Verifier phải đảm bảo public key là một điểm hợp lệ trên đúng đường cong, không nằm ngoài trường hữu hạn và không vi phạm các điều kiện của curve. Thư viện chuẩn cần kiểm tra tọa độ, điểm vô cực, miền giá trị R/S và các điều kiện liên quan trước khi chấp nhận chữ ký.

Các phép toán dùng private key cũng cần chống rò rỉ side-channel, đặc biệt timing và phân tích công suất trong môi trường có khả năng quan sát. Không tự triển khai phép nhân điểm hoặc phép toán modulo cho ứng dụng nghiệp vụ.

### 8.4. Tính không duy nhất của chữ ký

Với một số cách biểu diễn ECDSA, nếu `(R,S)` là chữ ký hợp lệ thì `(R, n-S)` cũng có thể hợp lệ về mặt toán học. Do đó không nên giả định mỗi thông điệp chỉ có một chuỗi chữ ký duy nhất. Không tự áp đặt quy tắc low-S hoặc chuẩn hóa chữ ký ngoài quy định của giao thức nếu các bên chưa thống nhất; hãy để thư viện JOSE xử lý theo chuẩn.

Nếu hệ thống cần thu hồi hoặc chống phát lại, nên dựa vào claims/định danh phiên như `jti`, trạng thái phiên và chính sách thời hạn, thay vì chỉ băm chuỗi JWT để suy ra danh tính duy nhất của một chữ ký.

## 9. Lỗi triển khai và rủi ro thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng sai đường cong với `alg` | Chữ ký không tương thích hoặc verifier chọn sai tham số | Ràng buộc ES256/P-256, ES384/P-384, ES512/P-521 |
| Nhầm ES512 với curve 512 bit | Cấu hình khóa sai | Nhớ ES512 dùng P-521 và SHA-512 |
| Gửi DER thay vì raw R||S | JWS signature sai độ dài/định dạng | Chuyển đổi ASN.1 DER sang fixed-width R||S |
| Tách R/S sai độ rộng hoặc signed integer | Chữ ký không xác minh được hoặc dữ liệu bị diễn giải sai | Dùng số nguyên không dấu, big-endian, độ rộng chuẩn |
| Tái sử dụng hoặc đoán được nonce | Có thể lộ private key | CSPRNG hoặc nonce xác định theo chuẩn qua thư viện đáng tin cậy |
| Tin `alg` do token khai báo | Cho phép thuật toán ngoài chính sách hoặc algorithm confusion | Allowlist thuật toán phía verifier |
| Chấp nhận public key/curve tùy ý | Có thể xác minh bằng khóa do attacker kiểm soát | Chỉ chọn khóa từ tập tin cậy và ràng buộc curve |
| Không kiểm tra public point và miền R/S | Có thể dẫn đến lỗi xác minh hoặc tấn công vào triển khai | Dùng thư viện chuẩn với kiểm tra đầu vào nghiêm ngặt |
| Chỉ kiểm tra chữ ký, bỏ qua claims | Token hết hạn hoặc sai audience vẫn được chấp nhận | Kiểm tra `iss`, `aud`, `exp`, `nbf`, loại token và quyền |
| Nghĩ chữ ký làm payload bí mật | Claims vẫn đọc được từ Base64URL | Không đưa dữ liệu nhạy cảm vào JWS; dùng JWE nếu cần |
| Nghĩ ECDSA tự ngăn replay | Bearer token hợp lệ có thể bị gửi lại | Thời hạn ngắn, audience, thu hồi và kiểm soát phiên |

### 9.1. Algorithm confusion

Giả sử một verifier dự kiến chỉ nhận ES256 nhưng lại cho phép thuật toán từ nhiều họ khóa mà không kiểm tra kiểu khóa. Kẻ tấn công có thể tìm cách khiến hệ thống diễn giải dữ liệu khóa không đúng mục đích hoặc dùng một cơ chế xác minh ngoài chính sách.

Biện pháp phòng tránh:

1. Cấu hình allowlist thuật toán tại verifier.
2. Ràng buộc thuật toán với loại khóa và đường cong chính xác.
3. Gắn khóa với issuer và mục đích sử dụng.
4. Không để header chưa xác thực tự chọn nguồn khóa hoặc cơ chế xác minh.

### 9.2. Lỗi chữ ký luôn 64 byte trong ES256

Một số thư viện trả DER, một số thư viện trả raw R||S. Nếu tích hợp nhầm định dạng, chữ ký có thể dài hơn hoặc ngắn hơn 64 byte và verifier từ chối. Khi chẩn đoán, hãy kiểm tra:

- Đoạn chữ ký đã giải mã có đúng 64 byte cho ES256, 96 byte cho ES384 hoặc 132 byte cho ES512 không?
- R và S có được tách theo đúng độ rộng không?
- Các số có được mã hóa không dấu, big-endian và thêm byte 0 ở đầu khi cần không?
- Signing input có đúng nguyên văn `header64.payload64` không?
- Key có đúng đường cong và issuer không?

Không khắc phục bằng cách bỏ qua xác minh, chấp nhận mọi đường cong hoặc tự cắt byte để ép độ dài.

## 10. Khi nào nên chọn ES256, ES384 hoặc ES512?

**Tình huống A — Một issuer cần phát token cho nhiều API.** ECDSA phù hợp với mô hình issuer giữ private key còn API chỉ giữ public key để xác minh. ES256 thường là lựa chọn thực dụng nếu chính sách cho phép và các bên hỗ trợ P-256.

**Tình huống B — Chính sách yêu cầu SHA-384 hoặc SHA-512.** Chọn ES384 hoặc ES512 theo JWA và xác nhận mọi verifier hỗ trợ đúng curve, hash và định dạng chữ ký.

**Tình huống C — Muốn chữ ký ngắn hơn RSA.** ECDSA với P-256 tạo chữ ký raw 64 byte; P-384 là 96 byte và P-521 là 132 byte. Điều này thường nhỏ hơn chữ ký RSA với mô-đun 2.048 bit (256 byte), nhưng hiệu năng và hỗ trợ phần cứng/thư viện còn tùy môi trường.

**Tình huống D — Tích hợp hệ thống cũ chỉ hỗ trợ RSA.** Có thể cần RS/PS để tương thích. Không chuyển thuật toán chỉ bằng cách sửa `alg`; issuer và verifier phải cùng hỗ trợ đường cong, khóa và biểu diễn chữ ký.

**Tình huống E — Cần chữ ký ổn định cho cùng một thông điệp.** ECDSA ngẫu nhiên có thể tạo nhiều chữ ký khác nhau. Nếu cần nonce xác định, dùng triển khai hỗ trợ phương pháp chuẩn như RFC 6979; đừng tự tạo nonce.

**Tình huống F — Cần giấu payload.** ES256/384/512 chỉ ký dữ liệu. Cần JWE hoặc giải pháp mã hóa phù hợp nếu claims phải bí mật.

## 11. Những hiểu lầm phổ biến

**“ES512 dùng đường cong 512 bit.”** Sai. JWA quy định ES512 dùng P-521 và SHA-512.

**“Chữ ký ES256 luôn dài 32 byte vì SHA-256 dài 32 byte.”** Sai. Chữ ký gồm R và S, mỗi phần 32 byte, tổng cộng 64 byte.

**“DER và R||S là hai cách viết giống nhau.”** Sai. DER là cấu trúc ASN.1 có độ dài biến thiên; JWS yêu cầu nối hai số nguyên fixed-width.

**“Cùng một JWT ký ECDSA luôn tạo cùng chữ ký.”** Không nhất thiết. Với nonce ngẫu nhiên, chữ ký có thể khác nhau ở mỗi lần ký. Cả hai vẫn có thể hợp lệ.

**“Nonce không cần bảo vệ vì không phải private key.”** Sai. Nonce ECDSA tái sử dụng hoặc bị lộ có thể làm lộ private key.

**“Public key có thể lấy từ bất kỳ URL nào trong header.”** Sai. Nguồn khóa phải được cấu hình và xác thực tin cậy; header chưa xác thực không được điều khiển việc tải khóa tùy ý.

**“Chữ ký hợp lệ là đủ để truy cập.”** Sai. Phải kiểm tra issuer, audience, thời gian, loại token, quyền và chính sách của API.

## 12. Câu hỏi tự kiểm tra

1. ECDSA khác RSA ở cách biểu diễn khóa và cơ chế tạo chữ ký như thế nào?
2. ES256, ES384 và ES512 dùng các đường cong và hàm băm nào?
3. Vì sao ES512 dùng P-521 dù tên thuật toán kết thúc bằng 512?
4. JWS biểu diễn chữ ký ECDSA thành R||S như thế nào? Vì sao DER không thể đưa trực tiếp vào token?
5. Vì sao nonce ECDSA phải được bảo vệ và không được tái sử dụng?
6. Một token ES256 có chữ ký hợp lệ nhưng `aud` sai có được chấp nhận không?
7. Public JWK của EC cần những trường nào? Trường nào tuyệt đối không được công bố?
8. Khi rotation, vì sao verifier cần nhận public key mới trước khi issuer bắt đầu ký bằng private key mới?
9. Tại sao không nên giả định một thông điệp chỉ có một chữ ký ECDSA hợp lệ?

## 13. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), cấu trúc JWS Compact, signing input và biểu diễn chữ ký.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), đặc biệt **mục 3.4** quy định ES256, ES384, ES512 và định dạng R||S.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), biểu diễn khóa EC và JWKS.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), cấu trúc JWT và registered claims.
- [RFC 6979 — Deterministic Usage of the Digital Signature Algorithm (DSA) and Elliptic Curve Digital Signature Algorithm (ECDSA)](https://www.rfc-editor.org/rfc/rfc6979), phương pháp tạo nonce ECDSA xác định.
- [FIPS 186-5 — Digital Signature Standard (DSS)](https://csrc.nist.gov/pubs/fips/186-5/final), tiêu chuẩn chữ ký số và ECDSA.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), khuyến nghị về xác minh thuật toán, nguồn khóa và kiểm tra ngữ cảnh token.
