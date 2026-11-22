# RSA PKCS#1 v1.5 và nhóm thuật toán RS256, RS384, RS512

## 1. Vai trò của chữ ký RSA trong JWT

Trong **Security - JSON Web Token (JWT)**, một trường hợp sử dụng phổ biến là hệ thống phát hành JWT phải chứng minh rằng nội dung token chưa bị sửa và thực sự do một bên sở hữu **khóa ký hợp lệ** tạo ra. Khi JWT được biểu diễn dưới dạng **JSON Web Signature (JWS)**, nhóm thuật toán `RS256`, `RS384`, `RS512` thực hiện việc này bằng cơ chế **RSA với lược đồ chữ ký RSASSA-PKCS1-v1_5**.

Đặc điểm quan trọng nhất của nhóm RS là dùng **mật mã bất đối xứng**:

- **Khóa riêng (private key):** bên phát hành giữ bí mật và dùng để **ký** token.
- **Khóa công khai (public key):** các bên được tin cậy về nguồn gốc khóa có thể dùng để **xác minh** chữ ký.
- Người chỉ có khóa công khai có thể kiểm tra chữ ký nhưng không thể từ đó tạo ra chữ ký RSA hợp lệ cho thông điệp mới trong điều kiện bảo mật thông thường.

Nhờ tách quyền ký và quyền xác minh, một nhà cung cấp định danh có thể phát hành JWT cho nhiều API độc lập mà không cần chia sẻ khóa riêng. Tuy nhiên, **chữ ký RSA không mã hóa JWT**: payload của JWS thông thường vẫn đọc được sau khi giải mã Base64URL. Nếu cần che giấu nội dung, phải chọn thiết kế dữ liệu và cơ chế mã hóa phù hợp, chẳng hạn JWE.

**Phạm vi:** bài thuộc chương **Thuật toán chữ ký** của module **Security - JSON Web Token (JWT)**, tập trung vào chuẩn mật mã, định dạng JWS, quản trị khóa, xác minh và các rủi ro triển khai. Mọi ví dụ mang tính độc lập với ngôn ngữ lập trình và framework.

## 2. RSA và lược đồ RSASSA-PKCS1-v1_5

### 2.1. Nền tảng của cặp khóa RSA

RSA sử dụng cặp khóa toán học liên quan với nhau. Ở mức khái niệm:

- **Khóa công khai** gồm mô-đun `n` và số mũ công khai `e`.
- **Khóa riêng** chứa thông tin cần thiết để thực hiện phép toán ký, thường gồm `d` cùng các tham số tối ưu tính toán; các tham số đó phải được bảo vệ như bí mật.
- Chữ ký được tính với khóa riêng; kết quả được kiểm chứng với khóa công khai tương ứng.

Độ an toàn của RSA dựa vào việc tạo cặp khóa đúng chuẩn, kích thước mô-đun đủ lớn, bảo vệ khóa riêng và triển khai lược đồ chữ ký chính xác. Không nên tự hiện thực toán học RSA, tự tạo padding hoặc tự kiểm tra các byte cấu trúc chữ ký bằng mã ứng dụng thông thường.

Một nhầm lẫn hay gặp là xem chữ ký RSA như thao tác “mã hóa hash bằng khóa riêng”. Cách diễn đạt này thiếu chính xác và dễ dẫn tới triển khai sai. **RSASSA-PKCS1-v1_5 là lược đồ chữ ký đã được định nghĩa đầy đủ**, gồm hàm băm, mã hóa thông điệp theo chuẩn, phép toán RSA và quy tắc kiểm tra nghiêm ngặt.

### 2.2. PKCS#1 v1.5 dùng cho chữ ký là gì?

**PKCS#1** là họ tiêu chuẩn định nghĩa các cơ chế liên quan đến RSA. Phần **RSASSA-PKCS1-v1_5** quy định cách tạo và xác minh *chữ ký số*. Đây là cơ chế khác với **RSAES-PKCS1-v1_5** dùng cho *mã hóa RSA*; không được đồng nhất hai loại chỉ vì cùng có cụm “PKCS#1 v1.5”.

Với thông điệp byte `M`, thuật toán băm `H` và kích thước mô-đun RSA bằng `k` byte, bước mã hóa phục vụ chữ ký có dạng khái niệm:

~~~text
digest = H(M)
T      = DER_Encode(DigestInfo(hashAlgorithm, digest))
EM     = 0x00 || 0x01 || PS || 0x00 || T

PS     = các byte 0xFF liên tiếp, dài ít nhất 8 byte
length(EM) = k byte
~~~

`DigestInfo` chứa định danh thuật toán băm và giá trị băm, được biểu diễn theo DER với cấu trúc ASN.1 được tiêu chuẩn quy định. Sau khi xây dựng `EM`, lược đồ dùng phép toán RSA với khóa riêng để tạo chữ ký. Bên xác minh thực hiện phép toán khóa công khai rồi đối chiếu **chính xác** cấu trúc và giá trị mã hóa mong đợi theo tiêu chuẩn.

Điều này có những hệ quả thực tế:

1. Padding và cấu trúc `DigestInfo` là **thành phần bắt buộc của chữ ký**; chỉ kiểm tra xem một phần hash có xuất hiện trong kết quả RSA là không đủ.
2. Bộ xác minh cần từ chối padding sai, độ dài sai hoặc cấu trúc DER không hợp lệ; xác minh lỏng lẻo từng gây ra các lỗi giả mạo chữ ký RSA trong thực tế.
3. Với cùng khóa riêng, cùng signing input và cùng thuật toán băm, RSASSA-PKCS1-v1_5 có tính **xác định**: chữ ký được tạo ra giống nhau. Đây không phải là bằng chứng rằng một JWT không thể bị phát lại.
4. Nếu kích thước khóa không đủ để chứa phần mã hóa được yêu cầu, phép ký không hợp lệ. Vì vậy phải dùng khóa RSA đáp ứng yêu cầu của tiêu chuẩn và chính sách hệ thống.

**Quy tắc triển khai:** sử dụng thư viện mật mã/JOSE đã được kiểm chứng để gọi trực tiếp lược đồ `RSASSA-PKCS1-v1_5` với hàm băm phù hợp. Không tự tạo `DigestInfo`, padding hoặc phép lũy thừa mô-đun trong mã xác thực JWT.

## 3. RS256, RS384, RS512 khác nhau như thế nào?

Theo **JSON Web Algorithms (JWA, RFC 7518)**, ba giá trị `alg` sau đều dùng **RSASSA-PKCS1-v1_5**; điểm khác nhau là hàm băm SHA-2:

| `alg` của JWS | Lược đồ chữ ký | Hàm băm | Độ dài digest |
| --- | --- | --- | --- |
| `RS256` | RSASSA-PKCS1-v1_5 | SHA-256 | 256 bit = 32 byte |
| `RS384` | RSASSA-PKCS1-v1_5 | SHA-384 | 384 bit = 48 byte |
| `RS512` | RSASSA-PKCS1-v1_5 | SHA-512 | 512 bit = 64 byte |

**Mỗi thuật toán trên yêu cầu khóa RSA có mô-đun ít nhất 2.048 bit theo RFC 7518, mục 3.3.** Đây là mức tối thiểu của JWA, không nhất thiết là lựa chọn phù hợp cho mọi thời hạn bảo vệ hoặc chính sách tổ chức. Hệ thống có thể yêu cầu khóa 3.072 bit hoặc lớn hơn theo nhu cầu và khuyến nghị mật mã hiện hành.

### 3.1. Độ dài chữ ký không bằng độ dài SHA

Một điểm dễ nhầm là hậu tố `256`, `384`, `512` **không xác định kích thước chữ ký RSA**. Với RSASSA-PKCS1-v1_5, độ dài chữ ký bằng **độ dài mô-đun RSA tính theo byte**, bất kể hàm băm nào trong nhóm RS được sử dụng với cùng cặp khóa.

| Kích thước mô-đun RSA | Chữ ký nhị phân | Đoạn chữ ký Base64URL không padding |
| --- | --- | --- |
| 2.048 bit | 256 byte | 342 ký tự |
| 3.072 bit | 384 byte | 512 ký tự |
| 4.096 bit | 512 byte | 683 ký tự |

Các kích thước trên giả định mô-đun có số bit đúng như ghi trong bảng. Khi dùng **cùng khóa RSA 2.048 bit**, cả RS256, RS384 và RS512 đều cho chữ ký dài **256 byte**, mặc dù SHA-256, SHA-384 và SHA-512 có độ dài digest khác nhau.

Đổi `RS256` thành `RS512` **không tự tăng kích thước khóa RSA**, không giải quyết nguy cơ khóa riêng bị lộ và không thay thế việc kiểm tra claims. Lựa chọn thuật toán phải dựa trên chính sách mật mã, khả năng tương thích và mô hình đe dọa tổng thể.

### 3.2. Phân biệt nhóm RS và PS

JWS còn định nghĩa nhóm `PS256`, `PS384`, `PS512`, sử dụng **RSASSA-PSS**. Cả nhóm RS và PS đều là chữ ký RSA, nhưng **cơ chế padding khác nhau**, nên chữ ký RS256 không được kiểm tra như PS256 và ngược lại. PSS sử dụng thành phần ngẫu nhiên trong quá trình ký; PKCS#1 v1.5 cho chữ ký xác định với cùng thông điệp.

Tên thuật toán trong header JWT cần khớp **chính xác** lược đồ được bộ xác minh cấu hình. “RSA với SHA-256” còn thiếu thông tin nếu không biết hệ thống dùng PKCS#1 v1.5 hay PSS.

## 4. Chữ ký RS được gắn vào JWT như thế nào?

### 4.1. JWS Compact Serialization

JWT có chữ ký ở dạng JWS Compact thường gồm ba đoạn:

~~~text
BASE64URL(UTF8(protectedHeaderJSON))
.
BASE64URL(UTF8(payloadJSON))
.
BASE64URL(signatureBytes)
~~~

Ví dụ header **trước khi mã hóa**:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-q4"
}
~~~

Ví dụ payload **trước khi mã hóa**:

~~~json
{
  "iss": "https://issuer.example",
  "sub": "user-123",
  "aud": "inventory-api",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Các giá trị chỉ dùng để minh họa. `iat` và `exp` là **NumericDate**, biểu diễn giây từ Unix epoch, không phải mili giây. `typ` cho biết loại token mong đợi, còn `kid` là mã nhận diện khóa; cả hai không thay thế việc xác minh chữ ký và áp dụng chính sách JWT.

**Base64URL** chỉ mã hóa dữ liệu thành chuỗi ký tự an toàn cho URL, **không cung cấp tính bí mật**. Trong JWS Compact, ký tự `-` và `_` thay cho `+` và `/` của Base64 thông thường; bỏ dấu đệm `=` ở cuối từng đoạn.

### 4.2. Chính xác dữ liệu nào được ký?

Với JWT thông dụng sử dụng JWS Compact, signing input được tạo từ **hai đoạn đầu đã mã hóa**, gồm dấu chấm ở giữa:

~~~text
header64 = BASE64URL(UTF8(protectedHeaderJSON))
payload64 = BASE64URL(UTF8(payloadJSON))

signingInput = ASCII(header64 + "." + payload64)

signatureBytes = RSASSA_PKCS1_V1_5_SIGN(
    privateKey,
    signingInput,
    SHA-256
)

jwt = header64 + "." + payload64 + "." + BASE64URL(signatureBytes)
~~~

Khi chọn `RS384` hoặc `RS512`, dùng lần lượt SHA-384 hoặc SHA-512 trong lược đồ chữ ký. **Không chỉ ký payload JSON**, không tự băm rồi coi digest là chữ ký, và không đưa Base64URL đã giải mã vào hàm xác minh khi tiêu chuẩn yêu cầu chuỗi signing input.

~~~mermaid
flowchart TD
    H[Protected header JSON] --> HE[UTF-8 và Base64URL]
    P[Payload JSON] --> PE[UTF-8 và Base64URL]
    HE --> I[header64.payload64]
    PE --> I
    I --> S[RSASSA-PKCS1-v1_5 với SHA-2]
    PR[Khóa riêng của issuer] --> S
    S --> B[Base64URL của chữ ký]
    I --> T[JWT ba đoạn]
    B --> T
    T --> V[Verifier với khóa công khai tin cậy]
~~~

**Lưu ý về biểu diễn JSON:** thay đổi thứ tự trường, khoảng trắng hoặc cách escape có thể thay đổi các byte được ký dù dữ liệu JSON mang cùng ý nghĩa. Vì vậy bên xác minh phải lấy **nguyên văn hai đoạn Base64URL từ token nhận được**, rồi nối lại bằng dấu chấm để xác minh, thay vì parse rồi serialize JSON và tự dựng lại token.

### 4.3. Vì sao sửa payload không thể giữ nguyên chữ ký?

Giả sử JWT ký hợp lệ chứa `"sub": "user-123"`. Một người quan sát có thể giải mã payload, sửa thành `"sub": "admin"` và tạo lại đoạn Base64URL. Nhưng signing input đã thay đổi. Nếu không có khóa riêng tương ứng, người đó không thể tạo chữ ký RS256 mới hợp lệ; bộ xác minh dùng khóa công khai đáng tin cậy sẽ từ chối token bị sửa.

Điểm khác với HMAC (`HS256`, `HS384`, `HS512`) là **dịch vụ giữ khóa công khai RSA chỉ có quyền xác minh**; không tự nhiên có quyền ký token mới. Đây là lý do nhóm RS thường phù hợp khi một issuer phục vụ nhiều hệ thống xác minh độc lập.

## 5. Thiết kế kiến trúc phát hành và xác minh

### 5.1. Ranh giới giữa issuer và các dịch vụ sử dụng JWT

Hãy xét hệ thống gồm một **Identity Provider** và hai API: Inventory API, Billing API.

1. Identity Provider sinh và bảo vệ cặp khóa RSA.
2. Identity Provider dùng **private key** để phát hành JWT với `alg: RS256`.
3. Inventory API và Billing API nhận **public key** từ một nguồn đã được cấu hình tin cậy, chẳng hạn JWKS của issuer.
4. Mỗi API xác minh chữ ký và kiểm tra **audience** của chính mình: token dành cho Inventory API không được chấp nhận tại Billing API chỉ vì chữ ký hợp lệ.

~~~mermaid
flowchart LR
    Issuer[Issuer / Identity Provider]
    Secret[(RSA private key)]
    Public[(Trusted RSA public key)]
    Api1[Inventory API]
    Api2[Billing API]
    Client[Client]

    Secret -->|Ký JWT| Issuer
    Issuer -->|Phát token| Client
    Client -->|Bearer JWT| Api1
    Client -->|Bearer JWT| Api2
    Public -->|Xác minh chữ ký| Api1
    Public -->|Xác minh chữ ký| Api2
~~~

Việc một API chấp nhận JWT còn phụ thuộc loại token, issuer, thời hạn, phạm vi quyền và chính sách truy cập. **Xác minh chữ ký chỉ chứng minh được phần mật mã**: token khớp với một khóa ký trong tập tin cậy.

### 5.2. Phát hành token bằng khóa riêng

Quy trình phát hành đề xuất:

1. Chọn thuật toán JWS dựa trên **cấu hình bên phát hành**, ví dụ cố định `RS256`.
2. Chọn cặp khóa RSA hợp lệ: mô-đun đủ kích thước; khóa riêng được quản trị và lưu trữ an toàn.
3. Tạo protected header với `alg` đã định và `kid` tương ứng khóa ký đang dùng.
4. Tạo claims phù hợp, như `iss`, `sub`, `aud`, `iat`, `exp`, quyền hạn; tránh đặt dữ liệu bí mật không cần thiết vào token.
5. Tạo signing input từ hai đoạn Base64URL như mục 4; ký bằng **RSASSA-PKCS1-v1_5 + đúng hàm SHA-2**.
6. Trả JWT đã ghép ba đoạn qua một kênh truyền được bảo vệ, thường là HTTPS.

**Mã giả minh họa**:

~~~text
function issueJwt(claims, signerConfig):
    require signerConfig.algorithm in {RS256, RS384, RS512}
    require signerConfig.rsaKeyBits >= 2048

    header = {
        "alg": signerConfig.algorithm,
        "typ": "JWT",
        "kid": signerConfig.keyId
    }

    header64 = BASE64URL(UTF8(JSON_SERIALIZE(header)))
    payload64 = BASE64URL(UTF8(JSON_SERIALIZE(claims)))
    signingInput = ASCII(header64 + "." + payload64)

    rawSignature = RSASSA_PKCS1_V1_5_SIGN(
        signerConfig.privateKey,
        signingInput,
        hashFor(signerConfig.algorithm)
    )

    return header64 + "." + payload64 + "." + BASE64URL(rawSignature)
~~~

Mã giả nhấn mạnh thứ tự xử lý, không thay thế thư viện JOSE/JWT đã được kiểm chứng.

### 5.3. Xác minh token bằng khóa công khai

Một quy trình xác minh chặt chẽ cần:

1. Kiểm tra giới hạn kích thước và định dạng token ba phần; từ chối Base64URL hoặc JSON không hợp lệ, header chứa tham số quan trọng (`crit`) không hiểu.
2. Parse header nhưng xem nó là **dữ liệu chưa xác thực** cho tới khi chữ ký được kiểm chứng. So `alg` với danh sách thuật toán **cho phép từ cấu hình phía verifier**.
3. Chọn public key đã được tin cậy cho đúng issuer, loại token và thuật toán. `kid` chỉ hỗ trợ tra khóa trong tập đã quản trị; tuyệt đối không dùng làm đường dẫn hoặc URL bất kỳ.
4. Xác minh chữ ký bằng **đúng RSASSA-PKCS1-v1_5 và đúng hàm băm**. Kiểm tra độ dài chữ ký và tính hợp lệ của phép xác minh bằng thư viện mật mã tiêu chuẩn.
5. **Sau khi chữ ký hợp lệ**, kiểm tra `iss`, `aud`, `exp`, `nbf`, loại token, giới hạn thời gian sống, `sub`, scopes/roles và chính sách phân quyền theo ngữ cảnh.
6. Chỉ cấp quyền nếu toàn bộ điều kiện cần thiết đều đạt.

~~~text
function verifyJwt(token, verificationPolicy, trustedKeySet):
    (header64, payload64, signature64) = parseThreeSegmentsStrictly(token)
    header = parseProtectedHeader(BASE64URL_DECODE(header64))

    require header.alg in verificationPolicy.allowedAlgorithms
    require header.alg in {RS256, RS384, RS512}
    require no unsupported critical header parameters

    publicKey = resolveTrustedPublicKey(
        trustedKeySet,
        verificationPolicy.expectedIssuer,
        header.kid,
        header.alg
    )

    require publicKey exists
    require publicKey.type == RSA
    require publicKey.modulusBits >= 2048
    require publicKey is authorized for this algorithm and issuer

    signingInput = ASCII(header64 + "." + payload64)
    signatureBytes = BASE64URL_DECODE(signature64)

    require RSASSA_PKCS1_V1_5_VERIFY(
        publicKey,
        signingInput,
        signatureBytes,
        hashFor(header.alg)
    )

    claims = parseAndValidateJson(BASE64URL_DECODE(payload64))
    require claims.iss == verificationPolicy.expectedIssuer
    require claims.aud contains verificationPolicy.expectedAudience
    require claims.exp is valid and now < claims.exp
    require claims.nbf absent or now >= claims.nbf
    require token type, subject, scope and other policy checks pass

    return claims
~~~

Mã giả giả định một trường hợp **JWT access token** bắt buộc có `exp`. Chuẩn JWT không buộc mọi loại JWT phải có tất cả các claims; điều kiện nào bắt buộc là **chính sách của bên nhận**. Hệ thống thật cần xử lý đúng dạng `aud` là chuỗi hoặc mảng, NumericDate theo giây UTC, sai lệch đồng hồ nhỏ nếu cho phép, claim trùng lặp và các loại token khác nhau.

Việc đọc một số thông tin header hoặc issuer *chưa xác thực* để xác định **các khóa ứng viên trong tập đã tin cậy** có thể cần thiết, nhưng không được cho thông tin đó quyền chọn nhà cung cấp khóa tùy ý hoặc quyết định phân quyền trước khi chữ ký hợp lệ.

## 6. Quản lý khóa RSA và JWKS

### 6.1. Bảo vệ private key

Khóa riêng là tài sản nhạy cảm nhất của issuer:

- Sinh khóa với thư viện/CSPRNG và bộ sinh khóa RSA đáng tin cậy; dùng mô-đun tối thiểu 2.048 bit theo JWA và đáp ứng chính sách dài hạn của tổ chức.
- Lưu khóa riêng trong **KMS, HSM hoặc secret manager** nếu kiến trúc cho phép; giảm số lượng tiến trình và con người có quyền đọc hoặc sử dụng khóa.
- Không đưa private key vào mã nguồn, kho Git, build artifact công khai, log, payload JWT hoặc cấu hình được phát cho verifier.
- Tách khóa theo môi trường, issuer, mục đích sử dụng hoặc tenant khi cần. Không dùng cùng một khóa riêng cho mọi hệ thống mà không có lý do thiết kế rõ ràng.
- Kiểm soát quyền ký, giám sát thao tác quản trị khóa và có quy trình thu hồi/luân chuyển khi nghi ngờ lộ khóa.

Khóa riêng có thể ở các định dạng đóng gói khác nhau, ví dụ **PKCS#8** (thường có PEM `BEGIN PRIVATE KEY`) hoặc cấu trúc **PKCS#1 RSA private key** (thường có PEM `BEGIN RSA PRIVATE KEY`). Khóa công khai thường được trao đổi bằng **SubjectPublicKeyInfo** (PEM `BEGIN PUBLIC KEY`) hoặc JWK. Những định dạng biểu diễn này khác **lược đồ chữ ký RSASSA-PKCS1-v1_5**; không nên suy ra thuật toán JWS chỉ từ nhãn PEM.

### 6.2. Chia sẻ public key bằng JSON Web Key

**JSON Web Key (JWK)** là định dạng JSON mô tả khóa mật mã. Public JWK cho RSA thường có các thuộc tính:

| Trường JWK | Ý nghĩa |
| --- | --- |
| `kty` = `RSA` | Loại khóa là RSA |
| `n` | Mô-đun RSA, mã hóa Base64URLUInt |
| `e` | Số mũ công khai RSA, mã hóa Base64URLUInt |
| `kid` | Mã nhận diện khóa để hỗ trợ lựa chọn và luân chuyển |
| `alg` | Thông tin thuật toán dự kiến, nếu được cung cấp |
| `use` = `sig` | Mục đích sử dụng: ký/xác minh, nếu được cung cấp |

Ví dụ minh họa **không phải khóa thật và không dùng được để xác minh**:

~~~json
{
  "kty": "RSA",
  "kid": "signing-key-2026-q4",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

`e = AQAB` là cách Base64URLUInt biểu diễn số mũ công khai phổ biến 65537. Trường `n` trong ví dụ chỉ là placeholder. **Public JWK không được chứa thông số khóa riêng** như `d`, `p`, `q`, `dp`, `dq`, `qi`.

**JWKS (JSON Web Key Set)** là tập các JWK, thường được issuer công bố qua endpoint HTTPS đã biết và được cấu hình tin cậy. Việc public key công khai **không tự làm nó đáng tin**: verifier phải biết key set đến từ đúng issuer và không bị thay thế bằng nguồn do người gửi token chỉ định.

### 6.3. `kid`, nguồn khóa và chống thay thế khóa

`kid` nằm trong protected header nhưng **chưa đáng tin khi mới parse**. Verifier có thể dùng nó như chỉ số tìm kiếm trong tập khóa đã được tin cậy; đồng thời ràng buộc khóa với issuer, thuật toán, loại token và mục đích sử dụng.

Các trường header tham chiếu khóa như `jku` hoặc `x5u` không nên khiến hệ thống tải URL tùy ý do token cung cấp: hành vi đó có thể cho phép dùng khóa của kẻ tấn công hoặc dẫn đến **SSRF**. Nếu thiết kế có dùng nguồn từ xa, chỉ dùng endpoint đã được cấu hình/phê duyệt, xác thực TLS, kiểm soát redirect, caching và chính sách truy cập mạng.

Một giá trị `kid` không cần độc nhất trên toàn Internet. Có thể có hai issuer cùng dùng `kid: current`; vì vậy phải xác định **không gian tin cậy của issuer** trước khi tra khóa. Đừng chỉ so `kid` giữa các hệ thống rồi cho rằng khóa nào có cùng tên cũng hợp lệ.

### 6.4. Quy trình luân chuyển khóa RSA

Ví dụ issuer có khóa cũ `key-2026-q3` và sắp dùng `key-2026-q4`:

1. Tạo cặp khóa mới, kiểm tra yêu cầu mật mã và triển khai **public key mới** đến các verifier tin cậy (qua JWKS hoặc phân phối cấu hình).
2. Trong giai đoạn chuyển tiếp, verifier chấp nhận chữ ký bởi **cả khóa cũ và khóa mới** theo chính sách; issuer chuyển sang **ký token mới bằng khóa riêng mới**, gắn `kid` mới.
3. Chờ các token hợp lệ ký bằng khóa cũ hết hạn, tính thêm khoảng cho độ trễ đồng bộ hoặc sai lệch đồng hồ được chấp nhận; sau đó gỡ public key cũ khỏi các bộ xác minh.
4. Thu hồi quyền sử dụng và hủy hoặc lưu trữ khóa riêng cũ theo chính sách.

Đây là **rotation có kế hoạch**. Khi khóa riêng bị lộ hoặc nghi ngờ bị lộ, không thể chỉ chờ token cũ hết hạn: cần **ngừng tin tưởng khóa bị lộ**, đánh giá phạm vi ảnh hưởng và xử lý thu hồi token/phiên theo quy trình sự cố. Public key cũ bị loại bỏ khỏi verifier sẽ khiến chữ ký bằng khóa tương ứng không còn được chấp nhận, kể cả token vốn chưa hết hạn.

## 7. Các rủi ro và lỗi triển khai thường gặp

| Rủi ro / lỗi | Hệ quả | Phòng tránh |
| --- | --- | --- |
| Tin `alg` từ header mà không áp dụng allowlist | Có thể chấp nhận `none`, thuật toán yếu hoặc loại thuật toán không đúng chính sách | Cố định thuật toán được phép theo issuer/ứng dụng và khóa |
| Trộn RSA với HMAC không kiểm tra loại khóa | **Algorithm confusion**: một số triển khai sai có thể diễn giải public key như secret HMAC | Không dùng chung cơ chế khóa cho các họ thuật toán; xác minh ràng buộc `alg`, loại khóa, mục đích |
| Nhầm `RS256` với `PS256` | Hai bên dùng lược đồ padding khác nhau nên xác minh thất bại, hoặc triển khai kiểm tra sai | Cấu hình rõ tên JWS `alg` và đúng lược đồ mật mã |
| Xác minh PKCS#1 v1.5 lỏng lẻo | Padding hoặc `DigestInfo` bất thường có thể bị chấp nhận | Dùng thư viện triển khai kiểm tra theo chuẩn, từ chối mã hóa không hợp lệ |
| Khóa RSA quá ngắn hoặc sinh không an toàn | Nguy cơ yếu về mật mã hoặc vi phạm yêu cầu JWA | Dùng tối thiểu 2.048 bit, ưu tiên kích thước theo chính sách an toàn hiện hành |
| Lấy public key từ URL do token khai báo | Cho phép kẻ tấn công chọn khóa hoặc gây SSRF | Chỉ chấp nhận endpoint và tập khóa đã được cấu hình tin cậy |
| Dùng `kid` làm tên tệp/đường dẫn SQL trực tiếp | Có thể gây lộ dữ liệu, injection, path traversal hoặc chọn sai khóa | Tra cứu `kid` trong tập định danh khóa hợp lệ, ràng buộc với issuer |
| Parse rồi serialize JSON trước khi kiểm tra chữ ký | Signing input khác byte gốc, token hợp lệ bị từ chối | Dùng nguyên văn hai đoạn Base64URL của token |
| Chỉ xác minh chữ ký, bỏ qua `aud`/`iss`/`exp` | Token hết hạn hoặc phát cho dịch vụ khác vẫn được chấp nhận | Kiểm tra claims, loại token và phân quyền sau khi xác minh |
| Cho rằng JWT có chữ ký là nội dung bí mật | Header/payload JWS có thể được đọc | Tránh đưa bí mật vào payload; dùng mã hóa khi cần |
| Cho rằng RSA loại bỏ replay | Bearer token bị đánh cắp vẫn có thể dùng lại | TLS, thời hạn hợp lý, audience cụ thể, thu hồi và biện pháp ràng buộc token theo nhu cầu |

**Trường hợp minh họa về algorithm confusion:** một hệ thống dự kiến xác minh `RS256` bằng public key nhưng lại cho phép `HS256` và đưa cùng dữ liệu public key vào hàm HMAC như secret. Kẻ tấn công biết public key có thể tạo MAC `HS256` rồi gửi token tự ký. Bộ xác minh lỗi có nguy cơ chấp nhận token này. Cách ngăn chặn là **không chọn cơ chế kiểm tra dựa chỉ trên giá trị `alg` do token khai báo**; thuật toán, kiểu khóa và nguồn khóa phải bị ràng buộc bởi chính sách tin cậy.

**Trường hợp minh họa về sai đối tượng nhận:** issuer phát JWT cho `aud: inventory-api`, chữ ký RS256 chính xác. Billing API vẫn phải từ chối token nếu chính sách của mình yêu cầu `aud: billing-api`. RSA chỉ chứng minh chữ ký, không tự xác định quyền truy cập.

## 8. Cách chẩn đoán khi chữ ký RS không hợp lệ

Khi một JWT được phát hành nhưng verifier báo chữ ký sai, kiểm tra lần lượt các nhóm vấn đề sau:

1. **Thuật toán:** header là `RS256`, `RS384` hay `RS512`? Verifier có sử dụng đúng SHA-2 và **PKCS#1 v1.5**, không phải RSA-PSS không?
2. **Đúng cặp khóa:** public key có thực sự khớp private key dùng ký không? `kid` đã trỏ đúng phiên bản khóa chưa? Key set đã đồng bộ khi rotation chưa?
3. **Định dạng và byte ký:** signing input có đúng `header64.payload64` nhận được không? Có tự thêm padding Base64, chuẩn hóa JSON, đổi encoding hoặc ký trên payload đã giải mã không?
4. **Định dạng chữ ký:** chữ ký trong JWT là Base64URL của **dãy byte chữ ký RSA có kích thước bằng mô-đun**; không phải ASN.1 DER chứa cặp số như một số họ chữ ký khác.
5. **Ràng buộc xác minh:** thuật toán, issuer, mục đích khóa và trạng thái khóa có được cho phép không? Xác minh mật mã có thể thành công nhưng token vẫn thất bại ở bước `aud`, `exp`, `nbf` hay chính sách khác.

**Không** khắc phục bằng cách bỏ qua xác minh chữ ký, chấp nhận mọi `alg`, tự động tải khóa từ header hoặc tắt kiểm tra thời hạn. Hãy phân biệt rõ lỗi **mật mã** với lỗi **chính sách token**.

## 9. Chọn RS256, RS384, RS512 trong tình huống thực tế

**Tình huống 1 — Một issuer phát token cho nhiều API độc lập.** Nhóm RS phù hợp khi issuer cần giữ bí mật khóa riêng và API chỉ cần public key để xác minh. `RS256` là lựa chọn phổ biến nếu đáp ứng chính sách bảo mật và khả năng tương thích.

**Tình huống 2 — Chính sách yêu cầu SHA-384 hoặc SHA-512.** `RS384` hoặc `RS512` cung cấp hàm băm tương ứng, nhưng phải chắc chắn tất cả thành phần hỗ trợ đúng thuật toán và cặp khóa đạt yêu cầu. Không dựa vào hậu tố lớn hơn để bỏ qua quản trị khóa.

**Tình huống 3 — Cần token ngắn.** Với khóa RSA 2.048 bit, riêng chữ ký đã dài khoảng 342 ký tự Base64URL. Cả ba thuật toán RS có cùng kích thước chữ ký trên cùng khóa; đổi RS512 về RS256 **không làm chữ ký ngắn đi** nếu kích thước mô-đun giữ nguyên. Cần đánh giá yêu cầu về đường truyền hoặc thiết kế token, và có thể cân nhắc nhóm chữ ký khác khi phù hợp.

**Tình huống 4 — Muốn dùng RSA-PSS.** Cần chọn đúng nhóm **PS**, vì RS và PS khác lược đồ mã hóa chữ ký. Việc chuyển thuật toán yêu cầu phối hợp issuer, verifier, key policy, tài liệu tích hợp và kiểm thử tương thích.

**Tình huống 5 — Muốn ẩn claims trong JWT.** RS256/384/512 chỉ cung cấp tính toàn vẹn và xác thực nguồn theo chữ ký; cần dùng phương án hạn chế thông tin trong token hoặc mã hóa như JWE khi yêu cầu bảo mật nội dung.

## 10. Những hiểu lầm cần tránh

**“RS512 tạo chữ ký dài gấp đôi RS256.”** Sai khi dùng cùng cặp khóa RSA. Phần số trong tên RS chỉ hàm băm. Độ dài chữ ký phụ thuộc kích thước mô-đun RSA.

**“Có public key là có thể tạo JWT mới hợp lệ.”** Sai trong mô hình chữ ký RSA an toàn. Public key dùng để xác minh; private key tương ứng mới dùng để ký.

**“Nếu public key tải được qua HTTPS thì chắc chắn là khóa đúng.”** Chưa đủ. Cần thiết lập tin cậy với đúng issuer, đúng endpoint/key set và chính sách phù hợp; HTTPS chỉ bảo vệ kết nối tới endpoint đã chọn.

**“JWT có chữ ký RSA thì thông tin được mã hóa.”** Sai. JWS chứa payload có thể giải mã Base64URL. Chữ ký bảo đảm phát hiện thay đổi không hợp lệ, không che giấu nội dung.

**“Ký hợp lệ thì token phải được cấp quyền.”** Sai. Verifier cần kiểm tra thời gian, issuer, audience, loại token, quyền và mọi điều kiện nghiệp vụ cần thiết.

**“PKCS#1 v1.5 luôn giống nhau dù dùng ký hay mã hóa.”** Sai. RSASSA-PKCS1-v1_5 dành cho chữ ký khác với RSAES-PKCS1-v1_5 dành cho mã hóa. Cần phân biệt chính xác lược đồ.

## 11. Câu hỏi tự kiểm tra

1. Vì sao kiến trúc nhiều API độc lập thường thuận lợi khi issuer dùng RSA thay vì chia sẻ một khóa HMAC?
2. RS256, RS384 và RS512 khác nhau ở bước nào của lược đồ chữ ký? Nếu dùng cùng RSA 2.048 bit, chữ ký của chúng dài bao nhiêu byte?
3. Signing input của JWS Compact gồm những byte nào? Tại sao không nên serialize lại payload JSON trước khi xác minh?
4. Tại sao bộ xác minh phải ràng buộc thuật toán, loại khóa và issuer, thay vì tin tuyệt đối vào trường `alg` hoặc `kid` trong header?
5. JWT có chữ ký RSA hợp lệ nhưng hết hạn hoặc có `aud` sai có được chấp nhận không?
6. Phân biệt `RS256` với `PS256` và giải thích vì sao không được dùng lẫn bộ xác minh chữ ký.
7. Trong một đợt luân chuyển khóa, vì sao JWKS thường cần công bố song song khóa cũ và khóa mới?
8. Nếu private key của issuer bị lộ, việc đổi `RS256` thành `RS512` có đủ để xử lý sự cố không? Vì sao?

## 12. Tiêu chuẩn và tài liệu tham khảo

- [RFC 8017 — PKCS #1: RSA Cryptography Specifications Version 2.2](https://www.rfc-editor.org/rfc/rfc8017), đặc biệt các mục về **RSASSA-PKCS1-v1_5** và **EMSA-PKCS1-v1_5**.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), định dạng JWS Compact, protected header và signing input.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), đặc biệt **mục 3.3** quy định `RS256`, `RS384`, `RS512` và yêu cầu khóa RSA tối thiểu.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), biểu diễn JWK/JWKS và metadata khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), cấu trúc token và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), các khuyến nghị về xác minh thuật toán, quản lý khóa, cross-JWT confusion và kiểm tra ngữ cảnh.
