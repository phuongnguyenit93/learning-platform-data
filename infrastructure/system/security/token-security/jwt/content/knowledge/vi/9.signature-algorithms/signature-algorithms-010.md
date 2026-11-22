# Chống nhầm lẫn giữa khóa đối xứng và khóa bất đối xứng

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Thuật toán chữ ký  
> **Phạm vi:** Cơ chế chữ ký/MAC của JWT ở mức mật mã và giao thức, không phụ thuộc Java, Spring hay framework cụ thể.

Một JWT có thể được bảo vệ bằng **MAC đối xứng** hoặc **chữ ký số bất đối xứng**. Hai cơ chế đều giúp bên nhận kiểm tra tính toàn vẹn và nguồn tạo token theo mô hình khóa, nhưng cách phân phối khóa và ranh giới tin cậy hoàn toàn khác nhau.

Nếu một hệ thống nhầm public key RSA thành secret HMAC, hoặc để token tự quyết định thuật toán xác minh, kẻ tấn công có thể tạo token giả trong một số cấu hình sai. Lỗi này thường được gọi là **algorithm confusion** hoặc **key confusion**. Vấn đề nằm ở việc verifier không ràng buộc chặt thuật toán với loại khóa và hợp đồng token.

Quy tắc cốt lõi: **thuật toán phải được chọn từ cấu hình tin cậy của verifier; khóa phải được gắn với đúng issuer, đúng thuật toán và đúng mục đích sử dụng.** Header do token gửi lên chỉ là dữ liệu chưa tin cậy, không phải nơi quyết định chính sách mật mã.

## 1. Hai mô hình bảo vệ khác nhau

### 1.1. MAC đối xứng: cùng một bí mật để tạo và kiểm tra

Với HMAC, bên phát hành và bên xác minh cùng nắm một secret. Issuer dùng secret để tạo MAC; verifier dùng chính secret đó để tính lại và so sánh.

~~~text
                  SECRET CHUNG
                 /            \
                v              v
        +---------------+  +---------------+
        | Issuer        |  | Verifier      |
        | Tạo HMAC      |  | Kiểm tra HMAC |
        +---------------+  +---------------+
                |              ^
                | JWT          |
                +-------------->
~~~

Các thuật toán HMAC trong JWA:

| JOSE alg | Hàm băm bên trong | Độ dài secret tối thiểu theo RFC 7518 |
|---|---|---:|
| **HS256** | HMAC-SHA-256 | 256 bit |
| **HS384** | HMAC-SHA-384 | 384 bit |
| **HS512** | HMAC-SHA-512 | 512 bit |

Độ dài tối thiểu ở bảng là yêu cầu của JWA cho khóa HMAC tương ứng. Secret cũng cần được tạo bằng nguồn ngẫu nhiên mật mã đủ mạnh; một chuỗi dài nhưng dễ đoán không trở thành khóa an toàn. Không dùng mật khẩu, chuỗi cấu hình ngắn hoặc dữ liệu công khai làm HMAC secret.

**Hệ quả tin cậy:** bất kỳ bên nào có secret đều có thể tạo một JWT có MAC hợp lệ. Vì vậy, cấp secret cho nhiều API để chúng chỉ “xác minh” token cũng đồng nghĩa trao cho mỗi API khả năng phát hành token giả.

### 1.2. Chữ ký bất đối xứng: private key ký, public key xác minh

Với chữ ký số, issuer giữ private key để ký. Verifier chỉ cần public key tương ứng để kiểm tra chữ ký.

~~~text
        +-------------------+
        | Issuer            |
        | Giữ PRIVATE KEY   |
        | Ký JWT            |
        +-------------------+
                  |
                  | JWT + chữ ký
                  v
        +-------------------+
        | Verifier          |
        | Giữ PUBLIC KEY    |
        | Xác minh chữ ký   |
        +-------------------+
~~~

Các họ thuật toán chữ ký JWS thường gặp:

| JOSE alg | Cơ chế | Khóa ký | Khóa xác minh |
|---|---|---|---|
| **RS256/384/512** | RSASSA-PKCS1-v1_5 với SHA-2 | RSA private key | RSA public key |
| **PS256/384/512** | RSASSA-PSS với SHA-2 | RSA private key | RSA public key |
| **ES256/384/512** | ECDSA với SHA-2 | EC private key | EC public key |
| **EdDSA** | Chữ ký Edwards-curve theo JWA | EdDSA private key | EdDSA public key |

Public key không cho phép tạo chữ ký hợp lệ nếu thuật toán và triển khai được dùng đúng. Có thể phân phối public key tới nhiều verifier mà không trao cho họ quyền phát hành token.

### 1.3. So sánh ranh giới tin cậy

| Tiêu chí | HMAC đối xứng | Chữ ký bất đối xứng |
|---|---|---|
| Khóa tạo token | Secret dùng chung | Private key |
| Khóa kiểm tra | Cùng secret | Public key |
| Verifier có thể tự tạo token? | Có, vì giữ secret | Không, nếu chỉ giữ public key |
| Phân phối khóa | Phải bảo vệ secret ở mọi bên | Public key có thể phân phối rộng qua nguồn tin cậy |
| Hậu quả khi một verifier bị xâm phạm | Secret có thể cho phép giả mạo token ở mọi nơi dùng chung secret | Public key bị lộ không cho phép ký |
| Phù hợp | Ranh giới tin cậy nhỏ, các bên cùng được quyền ký | Một issuer phát hành cho nhiều API/verifier độc lập |

Không có lựa chọn nào tự động an toàn trong mọi hoàn cảnh. Cần chọn theo số lượng bên giữ khóa, mức độ tin cậy giữa chúng, cách lưu trữ và yêu cầu vận hành. Với nhiều resource server chỉ cần xác minh token do một issuer phát hành, chữ ký bất đối xứng thường giúp giới hạn quyền ký ở issuer.

## 2. JWT/JWS header không được quyết định chính sách thuật toán

Một JWS Compact có ba phần:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Header có thể chứa **alg** và **kid**:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-01",
  "typ": "JWT"
}
~~~

Các giá trị trên do bên gửi cung cấp. Trước khi xác minh chữ ký, verifier phải coi chúng là **dữ liệu không đáng tin**. Verifier có thể dùng chúng làm gợi ý chọn ứng viên trong tập cấu hình tin cậy, nhưng không được để chúng mở rộng chính sách.

Ví dụ:

- Nếu contract chỉ cho phép **PS256**, token ghi **RS256** phải bị từ chối.
- Nếu contract chỉ dùng khóa RSA ký, token ghi **HS256** không được khiến verifier chuyển sang HMAC.
- Nếu **kid** không tìm thấy trong JWKS của issuer đã cấu hình, không được tìm khóa trên mạng theo URL do token cung cấp.
- Nếu chữ ký thất bại, không thử một thuật toán hoặc cách diễn giải khóa khác cho tới khi thành công.

### 2.1. Allowlist theo contract

Verifier cần cấu hình trước:

| Thành phần | Ví dụ quy định |
|---|---|
| Issuer | https://id.example.com |
| Profile | OAuth 2.0 JWT access token |
| Thuật toán JWS | Chỉ **PS256** |
| Loại khóa | RSA public key |
| Nguồn khóa | JWKS tin cậy của issuer |
| Mục đích khóa | Chỉ xác minh chữ ký |
| Token không chữ ký | Từ chối |

Allowlist cần gắn với issuer, profile và điểm tiếp nhận. Không dùng một danh sách thuật toán chung quá rộng cho tất cả token của toàn hệ thống nếu các contract có yêu cầu khác nhau.

### 2.2. Không tin giá trị alg chỉ vì thư viện hỗ trợ

Một thư viện JOSE có thể hỗ trợ nhiều thuật toán, nhưng điều đó không có nghĩa ứng dụng được phép chấp nhận tất cả. Việc kiểm tra phải theo cấu hình của ứng dụng:

~~~text
contract = trustedConfiguration.forReceiver(receiver)

header = parseAsUntrusted(token)

if header.alg not in contract.allowedAlgorithms:
    REJECT

key = selectKeyFromTrustedIssuerSet(contract.issuer, header.kid)

if key.algorithmBinding != header.alg:
    REJECT

verifyUsingExactly(header.alg, key)
~~~

Pseudocode mô tả nguyên tắc; không phải API của một thư viện cụ thể. Việc chọn contract phải xuất phát từ endpoint/mục đích đã cấu hình, không lấy từ claim chưa xác minh.

## 3. Algorithm confusion: nhầm RS256 với HS256

### 3.1. Lỗi xảy ra như thế nào?

Giả sử hệ thống được thiết kế để:

- Issuer ký JWT bằng **RS256** với RSA private key.
- API xác minh bằng RSA public key được lấy từ JWKS.

Một triển khai sai có thể đọc **alg** trong header rồi chọn thuật toán theo giá trị đó. Nếu token đổi **alg** thành **HS256** và verifier dùng dữ liệu public key RSA như HMAC secret, public key vốn công khai có thể trở thành bí mật giả định để tính HMAC.

Kẻ tấn công không cần biết RSA private key. Họ chỉ cần biết dữ liệu public key mà verifier dùng nhầm làm secret. Token có thể được tạo MAC hợp lệ theo nhánh HMAC sai cấu hình, dù issuer không hề ký token đó bằng private key.

### 3.2. Minh họa luồng nhầm lẫn

~~~mermaid
flowchart TD
    A[Issuer thật ký RS256 bằng private key] --> B[Verifier được cấu hình nhận RSA public key]
    C[Token giả khai alg = HS256] --> D[Verifier đọc alg từ header chưa tin cậy]
    B --> E{Verifier có ràng buộc key với alg?}
    D --> E
    E -->|Không| F[Dùng public key bytes như HMAC secret]
    F --> G[MAC giả có thể được chấp nhận]
    E -->|Có| H[Từ chối HS256 vì ngoài allowlist]
~~~

Đây là mô hình lỗi khái niệm. Khả năng khai thác cụ thể phụ thuộc cách thư viện nhận khóa và cách ứng dụng chọn thuật toán; nhưng nguyên tắc phòng vệ không thay đổi: không được dùng public key bất đối xứng làm secret HMAC và không để header quyết định thuật toán.

### 3.3. Vì sao chữ ký số không bị phá?

Trong tình huống này, RSA không bị bẻ khóa. Kẻ tấn công lợi dụng **nhánh xác minh sai** của ứng dụng:

1. Hệ thống ban đầu tin RSA public key để xác minh chữ ký.
2. Ứng dụng lại cho token yêu cầu chuyển sang HMAC.
3. Dữ liệu public key bị diễn giải như secret HMAC.
4. Verifier xác minh một MAC do kẻ tấn công tự tạo.

Đây là lỗi phân loại thuật toán/khóa và cấu hình validator, không phải tấn công tìm RSA private key.

### 3.4. Các biến thể nhầm lẫn khác

Ngoài RS256/HS256, cần phòng tránh:

- Một khóa được dùng cho nhiều họ thuật toán dù không được thiết kế cho việc đó.
- Khóa ký bị dùng nhầm làm khóa mã hóa hoặc ngược lại.
- Khóa của issuer A được tra cứu trong bộ khóa issuer B vì **kid** trùng nhau.
- Hệ thống chấp nhận **alg: none** hoặc coi token không chữ ký là token đã xác thực.
- Verifier fallback từ thuật toán mạnh sang thuật toán khác khi xác minh thất bại.
- JWK khai báo **alg**, **use** hoặc **key_ops** không phù hợp nhưng ứng dụng bỏ qua.

## 4. Ràng buộc thuật toán với loại khóa

### 4.1. Quy tắc tương thích cơ bản

| Họ thuật toán | JWK kty | Khóa được phép | Không được làm |
|---|---|---|---|
| HS256/384/512 | oct | Secret đối xứng đủ mạnh | Dùng RSA/EC public key làm HMAC secret |
| RS256/384/512 | RSA | RSA private để ký, public để xác minh | Dùng secret HMAC hoặc EC key |
| PS256/384/512 | RSA | RSA private/public theo vai trò | Tự đổi sang PKCS#1 v1.5 hoặc HMAC |
| ES256/384/512 | EC | Curve và tham số đúng với thuật toán | Dùng curve khác hoặc RSA key |
| EdDSA | OKP | Khóa/curve EdDSA được JOSE hỗ trợ | Diễn giải khóa thành RSA, EC hoặc HMAC |

JWK **kty** chỉ là một phần của việc kiểm tra. Verifier còn phải kiểm tra curve, tham số khóa, thuật toán, mục đích và nguồn gốc của khóa.

### 4.2. Các trường JWK cần đối chiếu

| Trường | Ý nghĩa | Quy tắc kiểm tra |
|---|---|---|
| **kty** | Họ khóa | Phải phù hợp với thuật toán đã cấu hình |
| **alg** | Thuật toán khóa được dự kiến sử dụng, nếu có | Phải tương thích với contract; không tự tạo niềm tin nếu nguồn JWK không tin cậy |
| **use** | Mục đích tổng quát, như sig hoặc enc | Khóa xác minh chữ ký phải dành cho signature |
| **key_ops** | Các thao tác được phép, như verify hoặc sign | Không sử dụng khóa cho thao tác ngoài danh sách |
| **kid** | Định danh khóa | Chỉ có ý nghĩa trong phạm vi issuer/JWKS đã tin cậy |
| **crv** | Đường cong của khóa EC/OKP | Phải đúng với thuật toán |
| **n**, **e** | Tham số RSA công khai | Kiểm tra cấu trúc và chất lượng khóa |
| **x**, **y** | Tọa độ EC công khai | Kiểm tra curve và điểm hợp lệ |
| **d** | Thành phần riêng của khóa | Không được xuất hiện trong JWKS công khai; phải bảo vệ như bí mật |

Các metadata JWK không thay thế việc xác minh nguồn khóa. Một attacker có thể tự tạo JWK và tự khai **alg: RS256**; verifier chỉ được dùng khóa đến từ nguồn đã được ủy quyền cho issuer.

### 4.3. Tách biệt khóa theo mục đích

Nên duy trì ranh giới riêng cho:

- Khóa ký access token và khóa ký ID token nếu chính sách/profile yêu cầu tách.
- Khóa ký và khóa mã hóa.
- Khóa của từng issuer.
- Khóa production, staging và development.
- Khóa của từng miền tin cậy hoặc tenant khi mô hình yêu cầu.

Không dùng chung một secret HMAC giữa nhiều dịch vụ độc lập nếu các dịch vụ không được phép phát hành token. Với chữ ký bất đối xứng, chỉ issuer giữ private key; verifier chỉ nhận public key.

## 5. Lựa chọn HMAC hay chữ ký bất đối xứng

### 5.1. Khi HMAC có thể phù hợp

HMAC có thể phù hợp khi:

- Issuer và verifier nằm trong cùng một ranh giới tin cậy nhỏ.
- Mọi bên nắm secret đều được phép tạo token có MAC hợp lệ.
- Có cơ chế phân phối, lưu trữ và luân chuyển secret an toàn.
- Số lượng verifier nhỏ và được quản lý chặt.
- Có quy trình thu hồi secret khi một bên bị xâm phạm.

Trước khi chọn HMAC, hãy trả lời: **nếu một verifier bị chiếm quyền, attacker có thể tạo token được tất cả verifier khác chấp nhận không?** Nếu câu trả lời là có và điều đó không thể chấp nhận, mô hình khóa đối xứng có thể không phù hợp.

### 5.2. Khi chữ ký bất đối xứng phù hợp hơn

Chữ ký bất đối xứng thường phù hợp khi:

- Một issuer phát hành token cho nhiều resource server.
- Verifier thuộc nhiều nhóm vận hành hoặc miền tin cậy khác nhau.
- Verifier chỉ cần quyền xác minh, không được phép ký.
- Public key có thể phân phối qua JWKS hoặc cơ chế trust được quản lý.
- Cần giới hạn tác động khi một resource server bị xâm phạm.

Private key phải được bảo vệ ở issuer, tốt nhất qua KMS/HSM hoặc kho khóa có kiểm soát truy cập phù hợp. Public key có thể phân phối, nhưng vẫn phải xác minh đúng nguồn và đúng issuer.

### 5.3. Bảng quyết định

| Câu hỏi | Nếu câu trả lời là “Có” | Hướng xem xét |
|---|---|---|
| Mọi verifier có được quyền tự phát hành token không? | Có | HMAC có thể phù hợp nếu ranh giới tin cậy rõ |
| Verifier phải chỉ có quyền xác minh? | Có | Chữ ký bất đối xứng |
| Có nhiều API độc lập? | Có | Ưu tiên đánh giá chữ ký bất đối xứng |
| Không thể phân phối secret an toàn tới mọi bên? | Có | Chữ ký bất đối xứng |
| Hệ thống nhỏ, cùng chủ sở hữu, secret được bảo vệ tốt? | Có | HMAC có thể là lựa chọn hợp lý |
| Cần giảm phạm vi ảnh hưởng khi một verifier bị lộ? | Có | Chữ ký bất đối xứng với private key tập trung |

Không chọn thuật toán chỉ dựa trên tốc độ benchmark. Chi phí vận hành khóa, phân phối secret, quyền ký và hậu quả khi lộ khóa thường quan trọng hơn.

## 6. Quy tắc cấu hình verifier an toàn

### 6.1. Chọn thuật toán từ cấu hình tin cậy

Một cấu hình minh họa:

~~~yaml
contract_id: orders-access-v1
issuer: "https://id.example.com"
accepted_format: JWS_COMPACT
allowed_algorithms:
  - PS256
key_source:
  type: trusted_jwks
  issuer_bound: true
required_key:
  kty: RSA
  use: sig
  operation: verify
  algorithm_binding: PS256
reject:
  - none
  - HS256
  - unsupported_algorithm
  - key_type_mismatch
  - unknown_critical_header
~~~

Đây là ví dụ khái niệm, không phải schema chuẩn. Danh sách **PS256** chỉ minh họa một lựa chọn. Hệ thống thực tế phải dùng thuật toán được profile và chính sách mật mã cho phép.

### 6.2. Chọn khóa trong đúng không gian issuer

Quy trình:

1. Endpoint chọn contract từ cấu hình tin cậy.
2. Contract xác định issuer và nguồn JWKS.
3. Header **kid** được dùng để tìm ứng viên trong JWKS của issuer đó.
4. Kiểm tra khóa có đúng **kty**, **alg**, **use**, **key_ops**, curve/kích thước không.
5. Chỉ xác minh bằng thuật toán được contract cho phép.
6. Nếu không tìm thấy khóa, refresh JWKS theo chính sách giới hạn; nếu vẫn không có, từ chối.

Không tìm khóa toàn cục chỉ theo **kid**. Hai issuer có thể vô tình dùng cùng một kid; định danh khóa phải nằm trong ngữ cảnh issuer và bộ khóa tin cậy.

### 6.3. Không có fallback thuật toán

Khi xác minh thất bại:

- Không thử HS256 nếu RS256/PS256 thất bại.
- Không dùng public key như HMAC secret.
- Không chuyển từ JWS sang JWE hoặc ngược lại.
- Không bỏ qua chữ ký để tiếp tục kiểm tra claim.
- Không tự tải khóa từ **jku**, **x5u** hoặc URL chưa được tin cậy.
- Không chấp nhận **none** như một cách khắc phục lỗi cấu hình.

Token không thỏa mãn contract phải bị từ chối. Nếu contract cần thay đổi, phải thực hiện thay đổi có phiên bản và kiểm thử.

## 7. Những điểm riêng của từng họ thuật toán

### 7.1. HMAC

- Secret phải được sinh ngẫu nhiên mật mã và đủ độ dài theo thuật toán.
- Tất cả bên giữ secret đều có quyền tạo MAC hợp lệ.
- Secret không được công bố trong JWKS công khai.
- Không dùng secret chung cho nhiều issuer hoặc môi trường nếu không có chủ đích và kiểm soát rõ.
- So sánh MAC phải dùng cơ chế so sánh an toàn theo thư viện mật mã, tránh tự viết phép so sánh có thể làm lộ thông tin qua timing.

### 7.2. RSA: RS256 và PS256

- RS256 dùng RSASSA-PKCS1-v1_5 với SHA-256.
- PS256 dùng RSASSA-PSS với SHA-256 theo tham số của JWA.
- Cả hai dùng RSA private key để ký và public key để xác minh.
- RFC 7518 yêu cầu modulus RSA tối thiểu 2048 bit cho các thuật toán RSA trong JWA.
- Không coi RS256 và PS256 có thể thay thế tùy ý; thuật toán được chọn phải khớp contract và key policy.

### 7.3. ECDSA: ES256, ES384 và ES512

- Mỗi thuật toán gắn với curve và hash cụ thể theo JWA.
- ES256 dùng P-256/SHA-256; ES384 dùng P-384/SHA-384; ES512 dùng P-521/SHA-512.
- Khóa EC phải có curve và tham số hợp lệ.
- JWS biểu diễn chữ ký ECDSA theo dạng nối cố định hai số nguyên **R || S**; định dạng này khác ASN.1 DER thường gặp ở một số API mật mã. Nên dùng thư viện JOSE xử lý encoding, không tự chuyển đổi tùy tiện.

### 7.4. EdDSA

- JOSE định nghĩa EdDSA qua các đường cong được profile tương ứng hỗ trợ, như Ed25519 và Ed448.
- Khóa phải có đúng loại **OKP** và curve tương ứng.
- Không coi mọi triển khai EdDSA hoặc mọi khóa Edwards là tự động tương thích.
- Chỉ bật khi issuer, verifier và thư viện đều hỗ trợ đúng thuật toán theo JWA/RFC 8037.

## 8. Kiểm thử chống nhầm lẫn khóa và thuật toán

Một bộ kiểm thử tốt cần chứng minh token hợp lệ được nhận và token có dấu hiệu nhầm lẫn bị từ chối.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| A01 | RS256 đúng issuer, đúng RSA key, đúng audience | Có thể chấp nhận sau các kiểm tra khác |
| A02 | Token khai HS256 trong contract chỉ cho RS256/PS256 | Từ chối |
| A03 | Public key RSA bị đưa vào nhánh HMAC | Từ chối; không có nhánh diễn giải khóa này |
| A04 | HMAC token dùng secret không thuộc issuer/contract | Từ chối |
| A05 | Token dùng alg none | Từ chối |
| A06 | PS256 token nhưng verifier chỉ cho RS256 | Từ chối |
| A07 | RSA key được dùng cho ES256 | Từ chối vì sai loại khóa |
| A08 | EC key có curve không khớp ES algorithm | Từ chối |
| A09 | OKP key/curve không được profile hỗ trợ | Từ chối |
| A10 | JWK có alg hoặc use không khớp contract | Từ chối |
| A11 | kid trùng giữa hai issuer | Chỉ tìm trong JWKS của issuer được chọn; không dùng nhầm key |
| A12 | kid không có trong JWKS sau refresh giới hạn | Từ chối |
| A13 | Chữ ký thất bại với thuật toán đã chọn | Từ chối; không thử thuật toán khác |
| A14 | Verifier chỉ có public key bị lộ | Không thể tạo chữ ký hợp lệ |
| A15 | Một verifier giữ HMAC secret bị xâm phạm | Đánh giá khả năng giả mạo token ở mọi nơi dùng chung secret |

### 8.1. Kiểm thử cấu hình, không chỉ kiểm thử token

Ngoài test vector, cần kiểm tra cấu hình:

- Allowlist có đúng với contract không?
- Mỗi key entry có ràng buộc thuật toán và mục đích không?
- Có vô tình bật cả HMAC và RSA cho cùng một endpoint không?
- Secret HMAC có bị phân phối tới verifier không cần quyền ký không?
- Public key có được lấy từ JWKS của đúng issuer không?
- Có đường fallback khi xác minh thất bại không?
- Có chấp nhận token không chữ ký hoặc token sai profile không?

Kiểm thử phải chạy trên đúng cấu hình phát hành và xác minh sẽ triển khai. Một test unit riêng lẻ không chứng minh cấu hình production đã an toàn.

## 9. Quản lý vòng đời khóa

### 9.1. Luân chuyển khóa bất đối xứng

1. Tạo key pair mới trong kho khóa được kiểm soát.
2. Công bố public key mới qua JWKS tin cậy.
3. Cho verifier cập nhật/cache khóa mới.
4. Issuer bắt đầu ký bằng private key mới và **kid** mới.
5. Duy trì khóa cũ trong giai đoạn overlap có giới hạn để xác minh token cũ còn hạn.
6. Gỡ public key cũ sau khi token cũ hết hạn và giai đoạn chuyển tiếp kết thúc.

Nếu private key bị lộ, không chờ lịch rotation bình thường. Thu hồi khẩn cấp, đánh giá token đã phát hành và cập nhật tất cả verifier.

### 9.2. Luân chuyển secret HMAC

HMAC yêu cầu issuer và mọi verifier cùng chuyển sang secret mới:

- Tạo secret mới đủ mạnh và phân phối qua kênh quản lý bí mật.
- Có thể hỗ trợ hai secret trong giai đoạn chuyển tiếp nếu contract cho phép và mỗi secret được định danh rõ.
- Issuer bắt đầu tạo MAC bằng secret mới.
- Verifier ngừng chấp nhận secret cũ sau khi token cũ hết hạn hoặc theo lịch thu hồi.
- Nếu một verifier bị xâm phạm, đánh giá toàn bộ hệ thống dùng chung secret đó.

Không công bố HMAC secret trong JWKS công khai. Cần bảo vệ secret ở tất cả bên giữ nó; chỉ một bên bị lộ cũng có thể ảnh hưởng toàn bộ miền dùng chung.

### 9.3. Không tái sử dụng key ID một cách gây nhầm lẫn

**kid** không phải định danh toàn cục. Hãy tránh tái sử dụng kid trong cùng issuer khi khóa mới có ý nghĩa khác, hoặc đảm bảo resolver xử lý namespace và thời gian hiệu lực rõ ràng. Không dùng một kid để tham chiếu cả khóa HMAC lẫn RSA hoặc cả khóa ký và khóa mã hóa trong cùng contract.

## 10. Quy trình xác minh an toàn tổng hợp

~~~mermaid
flowchart TD
    A[Nhận JWT tại endpoint] --> B[Chọn contract từ cấu hình tin cậy]
    B --> C[Parse header như dữ liệu chưa tin cậy]
    C --> D{alg thuộc allowlist?}
    D -->|Không| X[Từ chối]
    D -->|Có| E[Chọn key trong nguồn tin cậy của issuer]
    E --> F{Key đúng issuer, kty, alg và use?}
    F -->|Không| X
    F -->|Có| G{Key role đúng?}
    G -->|Không| X
    G -->|Có| H[Xác minh bằng đúng thuật toán]
    H --> I{Chữ ký hợp lệ?}
    I -->|Không| X
    I -->|Có| J[Kiểm tra iss, aud, typ, claims và thời gian]
    J --> K{Contract hợp lệ?}
    K -->|Không| X
    K -->|Có| L[Kiểm tra scope và quyền tài nguyên]
    L --> M{Được phép?}
    M -->|Không| X
    M -->|Có| N[Chấp nhận cho đúng mục đích]
~~~

Pseudocode:

~~~text
verifyJwt(receiver, compactToken):
    contract = trustedContracts.forReceiver(receiver)
    reject nếu contract không tồn tại

    header = parseHeaderAsUntrusted(compactToken)
    reject nếu header.alg không thuộc contract.allowedAlgorithms
    reject nếu token format/type không thuộc contract

    key = trustedKeySet(contract.issuer).find(header.kid)
    reject nếu key không tồn tại
    reject nếu key.kty/alg/use/key_ops không khớp contract
    reject nếu key role không phù hợp với thuật toán

    verify signature using exactly contract algorithm and key
    reject nếu chữ ký không hợp lệ

    validate issuer, audience, required claims and time
    validate scope and resource authorization
    ACCEPT
~~~

Không sử dụng claim để cấp quyền trước khi chữ ký được xác minh. Không thử thuật toán khác nếu bước xác minh thất bại.

## 11. Checklist chống nhầm lẫn khóa

**Mô hình khóa**

- [ ] Đã quyết định rõ HMAC hay chữ ký bất đối xứng cho từng contract.
- [ ] Đã xác định những bên nào được phép tạo token và những bên nào chỉ được xác minh.
- [ ] Nếu dùng HMAC, mọi bên giữ secret đều được tin cậy như một bên có quyền ký.
- [ ] Nếu dùng chữ ký số, private key chỉ nằm ở issuer; verifier chỉ cần public key.

**Ràng buộc thuật toán**

- [ ] Thuật toán được lấy từ allowlist cấu hình, không lấy quyền quyết định từ header.
- [ ] Không chấp nhận **none** hoặc thuật toán ngoài contract.
- [ ] Không fallback giữa HMAC, RSA, EC, EdDSA hoặc thuật toán khác.
- [ ] JWE **alg/enc** được quản lý riêng nếu hệ thống có dùng JWE.

**Ràng buộc khóa**

- [ ] Khóa khớp **kty**, **crv**, **alg**, **use**, **key_ops** và mục đích.
- [ ] Không dùng RSA public key làm HMAC secret.
- [ ] **kid** được tra cứu trong JWKS của đúng issuer.
- [ ] Không tải khóa từ URL tùy ý trong token.
- [ ] Có kiểm soát chất lượng, lưu trữ, rotation và thu hồi khóa.

**Kiểm thử và vận hành**

- [ ] Có test chống RS256/HS256 algorithm confusion.
- [ ] Có test sai loại khóa, sai issuer, kid lạ và khóa bị thu hồi.
- [ ] Đã kiểm tra cấu hình thực tế không bật thuật toán ngoài ý muốn.
- [ ] Secret/private key không xuất hiện trong log, repository hoặc JWKS công khai.
- [ ] Có kế hoạch ứng phó khi secret/private key bị lộ.

**Điều cần nhớ:** HMAC dùng một bí mật chung nên mọi verifier giữ secret đều có thể tạo token. Chữ ký bất đối xứng tách quyền ký và quyền xác minh: issuer giữ private key, verifier giữ public key. Algorithm confusion xảy ra khi hệ thống để token hoặc cách diễn giải khóa sai làm thay đổi cơ chế xác minh. Hãy ràng buộc **contract → thuật toán → loại khóa → issuer → mục đích**, và từ chối mọi tổ hợp không được cấu hình rõ.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cấu trúc JWS và quy trình chữ ký/MAC.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): Loại khóa, tham số và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS, RS, PS, ES và các thuật toán JOSE; yêu cầu khóa tương ứng.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Ràng buộc thuật toán, khóa và phòng tránh algorithm confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Ví dụ profile access token sử dụng chữ ký và yêu cầu xác minh.
