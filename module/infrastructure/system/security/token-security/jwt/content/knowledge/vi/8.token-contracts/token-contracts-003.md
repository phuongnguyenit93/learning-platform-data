# Ràng buộc thuật toán, khóa và kiểu JWT được chấp nhận

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Bảo mật JWT ở mức giao thức và hệ thống, không phụ thuộc ngôn ngữ lập trình hay framework.

Khi nhận một JWT, bên tiếp nhận phải xác định được **token được bảo vệ bằng cơ chế nào, khóa nào có quyền tạo hoặc xác minh token, và loại JWT nào được phép xuất hiện tại điểm tiếp nhận đó**. Chỉ nhìn thấy trường **alg** hoặc tìm được một khóa có vẻ phù hợp không đủ để tin token.

Ví dụ, một API có thể nhận JWT ký bằng RSA từ máy chủ định danh. Nếu API lại chấp nhận HMAC bằng chính dữ liệu khóa công khai RSA, kẻ tấn công có thể lợi dụng sự nhầm lẫn giữa loại khóa và thuật toán để tự tạo token. Một rủi ro khác là API chấp nhận mọi dạng JWT từ cùng issuer, khiến ID token, access token hoặc JWT phục vụ nghiệp vụ bị dùng thay thế cho nhau.

Hợp đồng token cần quy định đồng thời:

1. **Kiểu token và cách đóng gói:** JWS, JWE, JWT lồng nhau hay hồ sơ token cụ thể.
2. **Thuật toán được phép:** thuật toán ký/MAC hoặc thuật toán quản lý khóa và mã hóa nội dung.
3. **Khóa được phép:** nguồn khóa tin cậy, loại khóa, mục đích sử dụng, thuật toán gắn với khóa và vòng đời khóa.
4. **Quy tắc xác minh:** cách chọn khóa, kiểm tra header, xác minh chữ ký/giải mã và từ chối token ngoài hợp đồng.

## 1. Phân biệt JWT, JWS và JWE

**JWT (JSON Web Token)** là định dạng biểu diễn một tập claim. JWT có thể được biểu diễn bằng JWS để bảo vệ tính toàn vẹn/xác thực nguồn phát hành, hoặc bằng JWE để mã hóa nội dung. Một số hệ thống dùng JWT lồng nhau, ví dụ ký trước rồi mã hóa.

| Dạng | Mục đích | Compact serialization thường gặp | Điều bên nhận cần làm |
|---|---|---|---|
| **JWS** | Chữ ký số hoặc MAC bảo vệ nội dung | 3 phần phân tách bằng dấu chấm | Xác minh chữ ký/MAC theo thuật toán và khóa được phép |
| **JWE** | Mã hóa và bảo vệ tính toàn vẹn của nội dung | 5 phần phân tách bằng dấu chấm | Kiểm tra thuật toán quản lý khóa, giải mã và xác minh mã xác thực |
| **Nested JWT** | Kết hợp các lớp bảo vệ, chẳng hạn ký rồi mã hóa | Thường là JWE chứa một JWS | Xác minh/giải mã đúng thứ tự và đúng hồ sơ |
| **Unsecured JWT** | JWT không có chữ ký/MAC, dùng alg = none trong JWS | Có thể có 3 phần, phần chữ ký rỗng | Thông thường phải từ chối tại điểm tiếp nhận security token |

Đừng dùng số lượng phần trong chuỗi compact làm căn cứ duy nhất để tin token. Cấu trúc chỉ giúp nhận diện dạng dữ liệu ban đầu; hợp đồng phải quy định chính xác dạng được hỗ trợ và bước xác minh tương ứng.

### 1.1. JWS: chữ ký số và MAC

JWS Compact Serialization có cấu trúc khái niệm:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Chữ ký được tính trên dữ liệu JWS Signing Input theo quy tắc của JWS, không phải trên một chuỗi JSON tùy ý sau khi đã parse rồi serialize lại. Bên xác minh phải sử dụng quy trình chuẩn của thư viện JOSE đáng tin cậy.

JWS có thể dùng:

- **Thuật toán MAC đối xứng** như HS256: bên tạo và bên kiểm tra cùng nắm bí mật.
- **Chữ ký bất đối xứng** như RS256, PS256, ES256 hoặc EdDSA: bên tạo dùng khóa riêng; bên kiểm tra dùng khóa công khai tương ứng.

JWS bảo vệ tính toàn vẹn và xác thực theo mô hình khóa. Nó **không mã hóa payload**. Người có chuỗi JWT thường có thể Base64url-decode header và payload để đọc nội dung.

### 1.2. JWE: mã hóa nội dung

JWE Compact Serialization có năm phần:

~~~text
BASE64URL(protected header)
.
BASE64URL(encrypted key)
.
BASE64URL(initialization vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication tag)
~~~

Header JWE có hai nhóm thuật toán quan trọng:

- **alg:** thuật toán/phương thức quản lý hoặc thiết lập khóa mã hóa nội dung (key management).
- **enc:** thuật toán mã hóa nội dung (content encryption).

Ví dụ:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "recipient-encryption-2026-01"
}
~~~

Đây là header minh họa, không phải token thực. Bên nhận cần giới hạn cả **alg** lẫn **enc** theo hợp đồng, kiểm tra khóa phù hợp, rồi giải mã và xác minh authentication tag.

JWE mã hóa cho người nắm khóa giải mã, nhưng **không tự động chứng minh danh tính người gửi** trong mọi mô hình. Ví dụ, nếu bất kỳ ai cũng có thể mã hóa bằng khóa công khai của người nhận, việc giải mã thành công không chứng minh nội dung do issuer được tin cậy tạo ra. Khi cần cả bí mật nội dung và xác thực issuer, thường dùng JWT lồng nhau với JWS bên trong JWE theo đúng hồ sơ đã thống nhất.

## 2. Ràng buộc thuật toán được chấp nhận

### 2.1. Thuật toán phải do hợp đồng quyết định

Header JOSE có thể chứa **alg**, nhưng header đến từ người gửi và phải được coi là dữ liệu **chưa tin cậy** trước khi xác minh. Bên tiếp nhận cần cấu hình trước tập thuật toán cho từng issuer, loại token và điểm tiếp nhận.

Ví dụ, hợp đồng access token của API có thể quy định:

~~~yaml
token_profile: oauth2-jwt-access-rfc9068
jws:
  allowed_algorithms:
    - PS256
    - RS256
  reject_unsecured: true
~~~

Đây là cấu hình khái niệm. Hệ thống thực tế cần chọn thuật toán theo tiêu chuẩn, khả năng tương thích và chính sách mật mã của mình; không nên sao chép một danh sách mẫu mà không đánh giá.

Nguyên tắc:

- **Allowlist thuật toán cụ thể.** Không chấp nhận mọi giá trị **alg** mà thư viện có thể xử lý.
- **Từ chối thuật toán ngoài hợp đồng**, kể cả khi token có chữ ký có vẻ hợp lệ.
- **Không chấp nhận none** cho access token hoặc security token cần chữ ký/MAC.
- **Gắn mỗi khóa với thuật toán phù hợp.** Không dùng cùng một khóa tùy tiện cho nhiều họ thuật toán hoặc nhiều mục đích.
- **Không tự động hạ cấp** sang thuật toán yếu hơn khi xác minh thất bại.
- Nếu dùng JWE, quản lý allowlist riêng cho **alg** (key management) và **enc** (content encryption).

### 2.2. Các họ thuật toán JWS thường gặp

| Giá trị JOSE | Họ thuật toán | Mô hình khóa | Lưu ý hợp đồng |
|---|---|---|---|
| **HS256**, **HS384**, **HS512** | HMAC với SHA-256/384/512 | Bí mật đối xứng dùng chung | Mọi bên giữ bí mật đều có khả năng tạo MAC/token |
| **RS256**, **RS384**, **RS512** | RSASSA-PKCS1-v1_5 với SHA-256/384/512 | Khóa RSA riêng/công khai | Khóa RSA phải đáp ứng yêu cầu kích thước và chính sách hiện hành |
| **PS256**, **PS384**, **PS512** | RSASSA-PSS với SHA-256/384/512 | Khóa RSA riêng/công khai | Cần hỗ trợ đúng tham số PSS theo JWA |
| **ES256**, **ES384**, **ES512** | ECDSA với SHA-2 | Khóa elliptic curve | Đường cong phải khớp đúng thuật toán; kiểm tra chữ ký theo encoding JOSE |
| **EdDSA** | Chữ ký Edwards-curve theo JOSE | Khóa EdDSA riêng/công khai | Chỉ dùng khi hồ sơ và các bên hỗ trợ cùng thuật toán/đường cong tương ứng |

Tên thuật toán không phải lựa chọn tùy ý. Ví dụ, **ES256** gắn với P-256 và SHA-256 theo JWA; không thể thay bằng một đường cong khác chỉ vì thư viện hỗ trợ ECDSA. **EdDSA** trong JOSE được định nghĩa qua hồ sơ thuật toán tương ứng, không đồng nghĩa mọi triển khai EdDSA đều tương thích với nhau.

Việc lựa chọn cần dựa trên tiêu chuẩn và khả năng triển khai ở cả bên phát hành lẫn bên nhận. Hãy ưu tiên thuật toán hiện được khuyến nghị trong hồ sơ bảo mật áp dụng, đồng thời kiểm thử khả năng tương thích trước khi triển khai.

### 2.3. Tránh nhầm lẫn thuật toán và hạ cấp

Một lỗi thiết kế nghiêm trọng là để token quyết định thuật toán tùy ý. Ví dụ:

~~~text
NGUY HIỂM:
    đọc alg từ header
    nếu thư viện hỗ trợ alg thì thử xác minh bằng khóa đang có
    nếu thất bại thì thử thuật toán khác hoặc cách diễn giải khóa khác

AN TOÀN HƠN:
    lấy contract từ điểm tiếp nhận/issuer được cấu hình
    kiểm tra alg thuộc allowlist của contract
    lấy khóa được gắn với đúng issuer, alg và mục đích
    xác minh đúng một cơ chế theo hợp đồng
    từ chối nếu không khớp
~~~

Đặc biệt, không dùng khóa công khai RSA làm bí mật HMAC. Nếu hệ thống phát hành token bằng RSA nhưng bên nhận nhầm khóa RSA công khai thành secret cho **HS256**, kẻ tấn công có thể tự tạo MAC bằng dữ liệu công khai đó trong một số thiết kế xác minh sai.

RFC 8725 yêu cầu ứng dụng giới hạn thuật toán được phép và bảo đảm khóa được sử dụng đúng với thuật toán tương ứng. Quy tắc này giúp ngăn algorithm confusion và các dạng hạ cấp.

### 2.4. Thuật toán JWE có hai lớp

| Header | Vai trò | Ví dụ |
|---|---|---|
| **alg** | Cách thiết lập/chuyển/gói khóa mã hóa nội dung | **RSA-OAEP-256**, **ECDH-ES**, **dir** |
| **enc** | Cách mã hóa nội dung bằng khóa nội dung | **A128GCM**, **A256GCM**, **A128CBC-HS256** |

Chỉ cho phép các cặp **alg + enc** mà hợp đồng và triển khai đã hỗ trợ. Không kiểm tra **alg** rồi bỏ qua **enc**. Với chế độ yêu cầu xác thực, phải xác minh authentication tag; nếu xác thực thất bại thì từ chối toàn bộ token, không trả payload một phần cho tầng nghiệp vụ.

## 3. Ràng buộc loại khóa và mục đích sử dụng

### 3.1. Khóa đối xứng và bất đối xứng

| Đặc điểm | Khóa đối xứng (MAC/mã hóa trực tiếp) | Khóa bất đối xứng (chữ ký số) |
|---|---|---|
| Bí mật | Cả bên tạo và bên kiểm tra cùng giữ secret | Chỉ bên ký giữ private key |
| Xác minh | Cần secret dùng để tạo MAC | Bên nhận dùng public key |
| Phạm vi tin cậy | Mỗi bên có secret có thể tạo token hợp lệ | Bên chỉ có public key không thể tạo chữ ký |
| Phân phối | Phải phân phối và bảo vệ secret cho các bên được phép | Có thể phân phối public key qua nguồn tin cậy |
| Rủi ro khi lộ | Lộ secret có thể cho phép giả mạo token | Lộ public key không cho phép ký; lộ private key có thể cho phép giả mạo |

Với nhiều API độc lập cần xác minh token do một issuer phát hành, chữ ký bất đối xứng thường giúp giới hạn quyền phát hành: API chỉ cần public key, còn private key được giữ ở bên phát hành. Nếu dùng HMAC, mọi API được cấp secret đều có khả năng tự tạo token có MAC hợp lệ; cần đánh giá rõ ranh giới tin cậy và số lượng bên nắm secret.

### 3.2. Loại khóa phải khớp thuật toán

JOSE/JWK có các loại khóa và tham số khác nhau:

| JWK field / loại | Ý nghĩa | Kiểm tra cần thiết |
|---|---|---|
| **kty: RSA** | Khóa RSA | Kiểm tra modulus/exponent và mục đích; chỉ dùng với thuật toán RSA phù hợp |
| **kty: EC** | Khóa elliptic curve | Kiểm tra **crv** và tọa độ; curve phải khớp thuật toán |
| **kty: OKP** | Khóa Octet Key Pair, dùng cho một số đường cong hiện đại như Ed25519 | Kiểm tra **crv**, thuật toán và hỗ trợ của hồ sơ |
| **kty: oct** | Khóa đối xứng dạng octet | Bí mật phải đủ độ mạnh và chỉ dùng cho mục đích được phép |

Các thuộc tính JWK liên quan:

- **alg:** thuật toán mà khóa được dự kiến dùng, nếu được khai báo.
- **use:** mục đích tổng quát như **sig** (chữ ký) hoặc **enc** (mã hóa).
- **key_ops:** thao tác được phép như **sign**, **verify**, **encrypt**, **decrypt** hoặc thao tác phù hợp khác.
- **kid:** định danh khóa trong phạm vi bộ khóa/issuer; thường dùng để chọn ứng viên.
- **kty**, **crv** và các tham số khóa: xác định họ và cấu trúc khóa.

Các thuộc tính này phải được kiểm tra nhất quán với chính sách của ứng dụng. Không coi việc JWK tự khai **use**, **key_ops** hoặc **alg** là đủ để tin khóa nếu nguồn JWK không đáng tin. Một khóa không nên vừa được sử dụng cho chữ ký vừa cho mã hóa chỉ vì định dạng cho phép biểu diễn cả hai.

### 3.3. Yêu cầu chất lượng khóa

**Khóa RSA:** RFC 7518 đặt mức tối thiểu 2048 bit cho các thuật toán RSA trong JWA. Chính sách thực tế có thể yêu cầu cao hơn theo vòng đời dữ liệu và tiêu chuẩn tổ chức.

**Khóa HMAC:** secret cần đủ entropy và có độ dài tối thiểu phù hợp với hàm băm; RFC 7518 quy định khóa HMAC không ngắn hơn độ dài đầu ra của hash tương ứng. Không dùng mật khẩu người dùng, chuỗi dễ đoán hoặc secret được hard-code trong mã nguồn.

**Khóa EC/OKP:** phải dùng đường cong/nhóm được chuẩn tương ứng hỗ trợ, tham số hợp lệ và thư viện mật mã đã được kiểm chứng. Không tự tạo tham số khóa hoặc tự triển khai phép toán đường cong.

**Khóa mã hóa:** cần độ mạnh, kích thước và cách sinh khóa phù hợp với thuật toán **alg/enc**. Với AES-GCM, nonce/IV phải tuân thủ yêu cầu duy nhất theo khóa và quy tắc của chế độ mã hóa; không tái sử dụng nonce sai cách.

### 3.4. Tách biệt khóa theo mục đích và môi trường

Nên tách khóa theo:

- **Issuer:** khóa của issuer A không tự động dùng cho issuer B.
- **Môi trường:** production, staging, development có bộ khóa và trust store riêng.
- **Mục đích:** ký access token, ký ID token, ký token nghiệp vụ và mã hóa JWE nên có ranh giới khóa rõ.
- **Thuật toán:** một khóa chỉ được gắn với thuật toán/phạm vi sử dụng đã định.
- **Tenant hoặc miền tin cậy:** tách khóa khi mô hình vận hành và rủi ro yêu cầu.

Không dùng cùng một secret HMAC cho nhiều dịch vụ hoặc nhiều môi trường nếu điều đó làm mở rộng phạm vi giả mạo. Không chia sẻ private key phát hành cho các API chỉ có nhiệm vụ xác minh.

## 4. Chọn và phân phối khóa an toàn

### 4.1. JWKS và nguồn khóa tin cậy

Một issuer thường công bố các khóa công khai qua **JWKS (JSON Web Key Set)**. Ví dụ cấu trúc rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là dữ liệu minh họa, không phải khóa thực. JWKS phải được lấy từ **nguồn đã gắn với issuer tin cậy** thông qua cấu hình/discovery an toàn. Không lấy URL JWKS tùy ý từ JWT chưa xác minh rồi tải về và dùng ngay.

Khi nhận JWT có **kid**, bên xác minh có thể dùng nó để tìm khóa ứng viên trong JWKS đã tin cậy. Tuy nhiên:

- **kid không phải bí mật và không phải bằng chứng khóa hợp lệ.** Kẻ gửi token có thể tự đặt giá trị này.
- **kid chỉ có ý nghĩa trong phạm vi issuer/bộ khóa.** Không tìm khóa toàn cục chỉ dựa vào kid.
- Nếu không tìm thấy kid, có thể làm mới JWKS theo chính sách có giới hạn; không được chuyển sang nguồn khóa do token chỉ định.
- Nếu nhiều khóa cùng kid hoặc dữ liệu khóa không nhất quán, từ chối hoặc xử lý theo chính sách lỗi rõ ràng; không chọn tùy tiện.
- Kiểm tra khóa đúng **kty**, **alg**, **use**, **key_ops**, đường cong/kích thước và trạng thái.

### 4.2. Quản lý JWKS cache

Cache JWKS giúp giảm độ trễ và tải nguồn khóa, nhưng phải có giới hạn:

1. Dùng HTTPS và xác thực nguồn theo cấu hình issuer.
2. Tôn trọng cache policy phù hợp; giới hạn thời gian giữ khóa cũ và thời gian chờ làm mới.
3. Khi gặp **kid** mới, chỉ làm mới theo cơ chế có kiểm soát; giới hạn tần suất để tránh bị lạm dụng gây request flood.
4. Không xóa ngay khóa cũ trong giai đoạn luân chuyển bình thường nếu còn token hợp lệ đã ký bằng khóa đó.
5. Khi khóa bị xâm phạm, ưu tiên vô hiệu hóa khẩn cấp theo quy trình sự cố, kể cả khi điều đó làm token đang còn hạn bị từ chối.

Không có một thời gian cache chung phù hợp cho mọi hệ thống. Thời hạn phải cân bằng giữa khả năng nhận khóa mới, khả năng thu hồi khóa cũ, độ sẵn sàng và rủi ro của token.

### 4.3. Luân chuyển khóa (key rotation)

Một quy trình luân chuyển khóa ký thông thường:

~~~mermaid
flowchart LR
    A[Khóa cũ đang ký] --> B[Công bố public key mới]
    B --> C[Bên nhận tải và xác nhận khóa mới]
    C --> D[Issuer bắt đầu ký bằng khóa mới]
    D --> E[Token cũ vẫn được xác minh bằng khóa cũ trong thời hạn cho phép]
    E --> F[Token cũ hết hạn hoặc hết giai đoạn chuyển tiếp]
    F --> G[Loại public key cũ khỏi JWKS]
~~~

Các nguyên tắc:

- **Công bố trước khi sử dụng:** bên nhận cần có cơ hội lấy khóa công khai mới trước khi token mới xuất hiện.
- **Chuyển tiếp có kiểm soát:** trong giai đoạn overlap, cả khóa cũ và mới có thể được chấp nhận theo chính sách.
- **Thời gian overlap có căn cứ:** dựa trên thời hạn token tối đa, cache JWKS, độ lệch đồng hồ và lịch phát hành.
- **Xóa khóa cũ đúng lúc:** không giữ vô thời hạn, vì khóa cũ tiếp tục mở rộng tập chữ ký được chấp nhận.
- **Sự cố khác luân chuyển bình thường:** nếu private key bị lộ, không chờ token hết hạn như lịch rotation thông thường; cần thu hồi và đánh giá token đã phát hành.

### 4.4. Lưu trữ và kiểm soát truy cập

Private key và secret ký token cần được bảo vệ bằng cơ chế phù hợp với mức độ nhạy cảm, chẳng hạn HSM, KMS hoặc kho bí mật được kiểm soát truy cập. Tối thiểu:

- Giới hạn danh tính/dịch vụ được quyền ký hoặc giải mã.
- Tách quyền quản trị khóa khỏi quyền vận hành ứng dụng khi khả thi.
- Ghi nhận sự kiện tạo, sử dụng, luân chuyển và thu hồi khóa.
- Có sao lưu/khôi phục phù hợp, nhưng không tạo bản sao secret không kiểm soát.
- Không ghi private key, HMAC secret hoặc plaintext token nhạy cảm vào log.
- Có quy trình xử lý khi khóa bị lộ, mất hoặc nghi bị sử dụng trái phép.

## 5. Xác định đúng kiểu JWT được phép

### 5.1. Kiểu token phải gắn với điểm tiếp nhận

JWT là định dạng chung, không tự nói mọi dịch vụ đều có thể dùng nó. Bên nhận cần xác định token profile cho từng chức năng:

| Điểm tiếp nhận | Kiểu/hồ sơ dự kiến | Dạng bảo vệ | Từ chối |
|---|---|---|---|
| OAuth resource server | JWT access token theo RFC 9068 | JWS theo hồ sơ | ID token, reset token, JWE hoặc kiểu khác nếu hồ sơ không cho phép |
| OIDC relying party | ID token theo OpenID Connect | Theo yêu cầu OIDC | Access token dùng thay ID token; ID token cấp cho client khác |
| Account recovery | Token khôi phục theo hợp đồng riêng | JWT/JWS hoặc opaque token theo thiết kế | Access token, ID token, token không đúng giao dịch |
| Dịch vụ nhận dữ liệu bí mật | JWE hoặc nested JWT theo hợp đồng | JWE, có thể chứa JWS | JWS plaintext nếu yêu cầu bảo mật nội dung |

### 5.2. Header typ và hồ sơ token

JOSE header có thể chứa **typ** để chỉ kiểu nội dung. Ví dụ:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-2026-01"
}
~~~

Với hồ sơ OAuth 2.0 JWT Access Token theo RFC 9068, giá trị **typ** được quy định là **at+jwt**; dạng media type đầy đủ **application/at+jwt** cũng được chấp nhận theo quy tắc tương thích của hồ sơ. Không tự áp đặt giá trị này cho mọi JWT hoặc mọi loại access token ngoài hồ sơ đó.

**typ** giúp phân biệt kiểu đối tượng nhưng không thay thế kiểm tra **iss**, **aud**, chữ ký, thời hạn và quyền. Một giá trị chung như **JWT** không đủ để chứng minh đây là access token. Với token tùy chỉnh, có thể dùng claim purpose riêng, nhưng phải quy định chính xác claim đó và kiểm tra sau xác minh.

### 5.3. Các kiểu dữ liệu và header cần xử lý rõ

| Thành phần | Ý nghĩa | Chính sách khuyến nghị |
|---|---|---|
| **typ** | Kiểu đối tượng/media type của JOSE | Khớp profile đã cấu hình; không suy diễn quyền từ typ |
| **cty** | Content type của nội dung được bảo vệ, có thể dùng trong nested JWT | Kiểm tra theo profile khi có sử dụng; nested JWT cần quy tắc rõ |
| **crit** | Danh sách extension header bắt buộc phải hiểu | Chỉ chấp nhận khi mọi extension được hỗ trợ và xử lý đúng; nếu không thì từ chối |
| **kid** | Gợi ý định danh khóa | Chỉ chọn khóa trong nguồn tin cậy, không coi là bằng chứng |
| **jku / x5u** | URI tham chiếu nguồn khóa/chứng thư trong một số JOSE header | Không tải tùy ý từ token chưa xác minh; chỉ hỗ trợ khi profile quy định nguồn tin cậy |
| **zip** | Thông tin nén trong JWE theo một số profile | Chỉ chấp nhận khi có nhu cầu, giới hạn tài nguyên và đánh giá rủi ro |

Không được bỏ qua header **crit** nếu có extension chưa hỗ trợ. Theo quy tắc JOSE, bên nhận không hiểu một extension được đánh dấu critical thì phải từ chối đối tượng. Tránh tự diễn giải extension chưa được định nghĩa.

### 5.4. Nested JWT: quy định rõ thứ tự lớp bảo vệ

Khi cần chữ ký issuer và bí mật payload, một mẫu phổ biến là **ký JWT trước rồi mã hóa JWS bên trong JWE**:

~~~text
Claims
  |
  v
JWS (ký bằng private key của issuer)
  |
  v
JWE (mã hóa cho bên nhận)
  |
  v
Token chuyển tới bên nhận
~~~

Bên nhận giải mã JWE, sau đó xác minh JWS bên trong theo issuer, audience, thuật toán và khóa của hợp đồng. Thứ tự lớp và loại nested JWT phải theo profile được thống nhất; không tự thử nhiều cách giải mã/xác minh khác nhau cho tới khi một cách tình cờ thành công.

## 6. Ví dụ hợp đồng thuật toán, khóa và kiểu token

Ví dụ dưới đây mô tả một API chỉ nhận JWT access token được issuer xác định ký bằng khóa RSA. Đây là cấu hình khái niệm:

~~~yaml
contract_id: orders-access-v1
receiver: orders-api
issuer: "https://id.example.com"
audience: "https://api.orders.example.com"
token_profile: "oauth2-jwt-access-rfc9068"

accepted_representation:
  format: JWS
  serialization: compact
  nested_jwt: false
  unsecured_jwt: false

signature:
  allowed_algorithms:
    - PS256
    - RS256
  key_source:
    type: trusted_jwks
    uri: "https://id.example.com/.well-known/jwks.json"
  required_key_use: sig
  required_key_type: RSA
  key_must_match_algorithm: true

header_policy:
  accepted_typ:
    - at+jwt
    - application/at+jwt
  unknown_critical_headers: reject
  arbitrary_key_urls: reject

claims_policy:
  require_issuer_match: true
  require_audience_match: true
  require_exp: true
  require_nbf_when_profile_requires: true
  required_scope_for_read: "orders:read"

key_lifecycle:
  jwks_cache: "bounded"
  rotation: "publish-before-use"
  compromised_key: "revoke-immediately"
~~~

Các tên thuộc tính trong YAML là mô hình diễn đạt, không phải schema tiêu chuẩn. Giá trị **PS256/RS256** chỉ là lựa chọn minh họa; một triển khai cụ thể nên chọn tập thuật toán nhỏ nhất đáp ứng nhu cầu và khả năng tương thích.

Nếu API cần nhận JWE thay vì JWS, phải khai báo rõ dạng JWE, các **alg + enc** cho phép, khóa giải mã và yêu cầu xác thực issuer. Không mở rộng hợp đồng bằng cách chấp nhận cả JWS lẫn JWE một cách tự động.

## 7. Quy trình xác minh an toàn

~~~mermaid
flowchart TD
    A[Nhận token] --> B[Chọn contract theo điểm tiếp nhận]
    B --> C[Phân tích cấu trúc và header chưa tin cậy]
    C --> D{Dạng token nằm trong allowlist?}
    D -->|Không| X[Từ chối]
    D -->|Có| E{typ và critical headers hợp lệ?}
    E -->|Không| X
    E -->|Có| F{alg/enc thuộc allowlist của contract?}
    F -->|Không| X
    F -->|Có| G[Chọn khóa từ issuer và nguồn tin cậy]
    G --> H{Khóa khớp loại, thuật toán, mục đích?}
    H -->|Không| X
    H -->|Có| I[Xác minh JWS hoặc giải mã/xác thực JWE]
    I --> J{Bảo vệ mật mã hợp lệ?}
    J -->|Không| X
    J -->|Có| K[Kiểm tra issuer, audience, thời hạn và profile claims]
    K --> L{Toàn bộ hợp đồng hợp lệ?}
    L -->|Không| X
    L -->|Có| M[Kiểm tra scope và quyền tài nguyên]
    M --> N{Được phép thao tác?}
    N -->|Không| X
    N -->|Có| O[Tiếp tục xử lý yêu cầu]
~~~

Trình tự thực tế có thể khác đôi chút ở các bước phân tích không tạo tác dụng phụ, nhưng **không cấp quyền dựa trên dữ liệu chưa xác minh**. Với JWE, phải hoàn tất xác thực mã hóa trước khi chuyển plaintext cho xử lý nghiệp vụ. Với nested JWT, phải thực hiện đủ từng lớp bảo vệ theo đúng thứ tự.

Pseudocode khái niệm:

~~~text
validateJwtAt(receiver, token):
    contract = trustedRegistry.contractFor(receiver)
    reject nếu contract không tồn tại

    parsed = parseStructureAsUntrusted(token)
    reject nếu định dạng không thuộc contract.acceptedRepresentation

    reject nếu typ không phù hợp profile
    reject nếu có crit extension không được hỗ trợ

    nếu dạng là JWS:
        reject nếu alg không thuộc contract.allowedJwsAlgorithms
        key = findKeyOnlyInTrustedIssuerSet(contract.issuer, parsed.kid)
        reject nếu key không khớp kty/alg/use/key_ops/profile
        verify JWS bằng đúng alg và key
    nếu dạng là JWE:
        reject nếu alg hoặc enc không thuộc allowlist
        key = findDecryptionKeyOnlyInTrustedStore(contract, parsed.kid)
        decrypt và xác minh authentication tag
        nếu nested JWT được yêu cầu: xác minh lớp bên trong theo profile

    kiểm tra iss, aud, exp, nbf và claims bắt buộc
    kiểm tra scope, quyền tài nguyên và trạng thái nghiệp vụ
    ACCEPT chỉ khi mọi điều kiện của cùng contract đều đạt
~~~

Khi không tìm thấy khóa hoặc xác minh thất bại, trả kết quả từ chối an toàn. Không thử một thuật toán khác, một issuer khác, một URL khóa khác hoặc một loại token khác chỉ để làm token vượt qua.

## 8. Tình huống lỗi và cách xử lý

| Tình huống | Nguy cơ | Xử lý đúng |
|---|---|---|
| Token khai **alg: none** | Không có chữ ký/MAC bảo vệ | Từ chối với security token yêu cầu xác thực mật mã |
| Token khai **HS256**, API chỉ cấu hình RS256 | Algorithm confusion/hạ cấp | Từ chối vì thuật toán ngoài allowlist |
| Khóa RSA công khai bị dùng như HMAC secret | Kẻ tấn công có thể tự tạo MAC trong triển khai sai | Ràng buộc kty/alg, không dùng chung khóa giữa họ thuật toán |
| **kid** không tồn tại trong JWKS | Token dùng khóa không được công bố hoặc đang có lỗi rotation | Làm mới JWKS theo giới hạn; nếu vẫn không có thì từ chối |
| **kid** trùng hoặc khóa không nhất quán | Chọn nhầm khóa | Từ chối hoặc áp dụng quy tắc xử lý xung đột đã định nghĩa |
| JWKS URL do token chỉ định | SSRF hoặc tin nguồn khóa của kẻ tấn công | Không tải URL tùy ý; dùng nguồn gắn với issuer đã tin |
| Token có **typ** không đúng | Dùng nhầm ID/access/business token | Từ chối theo token profile |
| JWE có **enc** không được hỗ trợ | Giải mã sai hoặc dùng cấu hình ngoài chính sách | Từ chối; không thử enc khác |
| JWE giải mã nhưng không xác minh được issuer | Nhầm bí mật nội dung với xác thực nguồn phát hành | Yêu cầu chữ ký/nested JWS nếu hợp đồng cần xác thực issuer |
| **crit** có extension lạ | Bỏ qua semantics bắt buộc của JOSE | Từ chối |
| Khóa cũ đã bị thu hồi nhưng vẫn được cache | Chấp nhận chữ ký từ khóa bị xâm phạm | Cơ chế refresh/thu hồi khẩn cấp và giới hạn cache |
| Private key ký token bị lộ | Kẻ tấn công phát hành token giả | Thu hồi khóa, đánh giá token đã phát hành, luân chuyển và xử lý sự cố |

## 9. Checklist kiểm soát hợp đồng

**Thuật toán**

- [ ] Hợp đồng quy định rõ allowlist JWS và/hoặc cặp JWE **alg + enc**.
- [ ] Từ chối **none**, thuật toán ngoài danh sách và các cơ chế hạ cấp.
- [ ] Mỗi khóa chỉ được dùng với thuật toán và mục đích phù hợp.
- [ ] Không có fallback tự động giữa HMAC, RSA, EC, EdDSA hoặc giữa JWS/JWE.

**Khóa**

- [ ] Nguồn khóa được gắn với issuer tin cậy; không lấy khóa từ URL tùy ý trong token.
- [ ] Kiểm tra **kty**, **crv**, **alg**, **use**, **key_ops**, **kid** và chất lượng khóa.
- [ ] Private key/secret được bảo vệ, giới hạn quyền sử dụng và không ghi vào log.
- [ ] Có quy trình JWKS cache, rotation, thu hồi bình thường và thu hồi khẩn cấp.
- [ ] Tách khóa giữa issuer, môi trường và mục đích khi cần.

**Kiểu token**

- [ ] Điểm tiếp nhận chỉ nhận dạng JWT/JWS/JWE/nested JWT đã khai báo.
- [ ] Token profile và **typ** được kiểm tra đúng chuẩn áp dụng.
- [ ] Xử lý **crit**, **cty** và các header extension theo hợp đồng.
- [ ] ID token, access token và token nghiệp vụ không bị dùng thay thế.
- [ ] Nếu dùng JWE, đã phân biệt bảo mật nội dung với xác thực danh tính issuer.

**Xác minh và vận hành**

- [ ] Header/payload chưa xác minh không được dùng để cấp quyền.
- [ ] Issuer, audience, thời gian, scope và quyền tài nguyên vẫn được kiểm tra đầy đủ.
- [ ] Có kiểm thử âm tính cho sai thuật toán, sai loại khóa, kid lạ, sai typ, token không có chữ ký và khóa bị thu hồi.
- [ ] Log đủ thông tin chẩn đoán nhưng không làm lộ token, secret hoặc dữ liệu nhạy cảm.

**Điều cần nhớ:** Thuật toán xác định cách bảo vệ token; khóa xác định ai có thể tạo, xác minh, mã hóa hoặc giải mã; token profile xác định loại JWT nào được dùng tại một điểm tiếp nhận. Hợp đồng chỉ an toàn khi ba yếu tố này **được ràng buộc với nhau** và mọi trường hợp ngoài chính sách đều bị từ chối.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cấu trúc JWS, protected header và xác minh chữ ký/MAC.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): Cấu trúc JWE, quản lý khóa và mã hóa nội dung.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): Định dạng khóa và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Các thuật toán JWS/JWE và yêu cầu khóa.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA và các thuật toán đường cong liên quan trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Giới hạn thuật toán, ràng buộc khóa, xác minh issuer/audience và ngăn nhầm lẫn loại JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Hồ sơ JWT access token và kiểu **at+jwt**.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và quy tắc xác minh dành cho relying party.
