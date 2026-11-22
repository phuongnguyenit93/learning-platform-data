# Kích thước khóa, đường cong và ràng buộc tương thích thuật toán

## 1. Vì sao phải xem kích thước khóa và thuật toán cùng nhau?

Trong **Security - JSON Web Token (JWT)**, chữ ký JWS chỉ xác minh được đúng khi bên phát hành và bên nhận thống nhất thuật toán, loại khóa, tham số mật mã và cách biểu diễn dữ liệu. Một khóa có kích thước đủ lớn vẫn có thể không dùng được nếu nó thuộc sai đường cong, sai loại JWK hoặc không tương thích với thuật toán trong protected header.

Khi lựa chọn thuật toán, cần phân biệt bốn khái niệm:

- **Kích thước khóa (key size):** số bit hoặc byte của secret HMAC, mô-đun RSA hoặc khóa trên đường cong.
- **Độ mạnh mật mã (security strength):** mức khó ước tính để phá cơ chế, thường biểu diễn bằng bit an toàn; không nhất thiết bằng số bit của khóa.
- **Kích thước chữ ký (signature size):** số byte của MAC/chữ ký được đưa vào JWS.
- **Khả năng tương thích (compatibility):** profile, thư viện, provider, định dạng khóa, KMS/HSM và mọi verifier có cùng hỗ trợ thuật toán hay không.

Ví dụ, ES512 sử dụng SHA-512 nhưng đường cong là P-521; chữ ký JWS dài 132 byte. RS256 dùng SHA-256 nhưng chữ ký dài theo mô-đun RSA, thường là 256 byte với khóa 2.048 bit. HS256 có MAC dài 32 byte, nhưng khóa vẫn phải được sinh đủ mạnh và có ít nhất 32 byte theo JWA.

Bài thuộc chương **Thuật toán chữ ký** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho JWT/JWS nói chung, không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 2. Phân biệt key size, entropy và signature size

### 2.1. Kích thước khóa không tự nói lên độ mạnh

Một chuỗi 64 ký tự có thể là 64 byte văn bản, 32 byte sau khi giải mã hex hoặc khoảng 48 byte sau khi giải mã Base64 tùy cách biểu diễn. Vì vậy phải xác định **byte thực tế được đưa vào thuật toán**, không chỉ đếm ký tự trong cấu hình.

Với khóa ngẫu nhiên, entropy phụ thuộc nguồn sinh và phân bố. Một khóa 256 bit được tạo đều bằng CSPRNG có thể có khoảng 256 bit entropy; một chuỗi 256 bit được tạo từ mật khẩu yếu không có mức entropy đó.

Với khóa bất đối xứng, số bit của mô-đun RSA hoặc đường cong cũng không bằng số bit an toàn. Ví dụ RSA 2.048 bit có mức an toàn ước tính thấp hơn 2.048 bit; P-256 có mức an toàn xấp xỉ 128 bit.

### 2.2. Kích thước chữ ký là đại lượng khác

Kích thước chữ ký ảnh hưởng trực tiếp đến tổng kích thước JWT, nhưng không thể dùng nó để suy ra mức bảo mật một cách độc lập:

- HMAC: chữ ký MAC có độ dài bằng output của hash.
- RSA: chữ ký có độ dài bằng mô-đun RSA tính theo byte.
- ECDSA: JWS nối hai số nguyên R và S có độ rộng cố định.
- EdDSA: chữ ký có độ dài cố định theo biến thể Ed25519 hoặc Ed448.

Đoạn chữ ký trong JWS Compact còn được Base64URL, nên số ký tự dài hơn số byte chữ ký gốc.

### 2.3. Không tự tăng kích thước để chữa cấu hình sai

Chọn RSA 4.096 bit thay cho 2.048 bit không khắc phục được việc verifier chấp nhận thuật toán không mong muốn, tải public key từ nguồn không tin cậy hoặc bỏ qua audience. Tương tự, dùng HS512 không làm mật khẩu yếu trở thành secret mạnh. Phải sửa đúng nguyên nhân: khóa, profile, nguồn khóa, allowlist hoặc chính sách claims.

## 3. Kích thước khóa và chữ ký của HMAC

### 3.1. Mức tối thiểu theo JWA

Theo **RFC 7518, mục 3.2**, khóa HMAC phải có kích thước ít nhất bằng độ dài đầu ra của hàm băm:

| Thuật toán | Hàm băm | Độ dài MAC | Khóa tối thiểu theo JWA |
| --- | --- | ---: | ---: |
| `HS256` | SHA-256 | 256 bit / 32 byte | 256 bit / 32 byte |
| `HS384` | SHA-384 | 384 bit / 48 byte | 384 bit / 48 byte |
| `HS512` | SHA-512 | 512 bit / 64 byte | 512 bit / 64 byte |

Đây là yêu cầu về kích thước khóa thực tế. Hệ thống nên sinh khóa ngẫu nhiên bằng CSPRNG với entropy tương ứng, không dùng mật khẩu, chuỗi mặc định hoặc giá trị hash của mật khẩu làm secret.

### 3.2. Độ dài secret sau khi giải mã

Ví dụ một khóa HS256 gồm 32 byte ngẫu nhiên có thể được lưu dưới dạng:

| Biểu diễn | Độ dài chuỗi | Byte sau khi giải mã |
| --- | ---: | ---: |
| Hex | 64 ký tự | 32 byte |
| Base64 có padding | 44 ký tự | 32 byte |
| Base64URL không padding | 43 ký tự | 32 byte |

Issuer và verifier phải thống nhất encoding. Nếu một bên dùng 32 byte sau decode, bên kia lại dùng 43 ký tự Base64URL như UTF-8, hai bên thực chất đang dùng hai khóa khác nhau.

### 3.3. Ràng buộc HMAC

- Secret phải đủ độ dài theo HS256/384/512 và có entropy cao.
- Không dùng public key RSA/EC/OKP làm secret HMAC.
- Mọi bên có secret đều có khả năng tạo MAC hợp lệ, nên phân phối secret cũng là phân phối quyền ký.
- Tách secret theo issuer, môi trường, tenant hoặc mục đích khi cần.
- Nếu secret bị lộ, phải thay khóa và xử lý token liên quan; tăng hash từ SHA-256 lên SHA-512 không khắc phục việc lộ secret.

## 4. Kích thước khóa RSA và thuật toán RS/PS

### 4.1. Kích thước mô-đun RSA

JWA yêu cầu khóa RSA dùng với các thuật toán RS và PS có mô-đun **ít nhất 2.048 bit**:

| Mô-đun RSA | Độ dài mô-đun theo byte | Chữ ký RSA nhị phân | Base64URL chữ ký, bỏ padding |
| --- | ---: | ---: | ---: |
| 2.048 bit | 256 byte | 256 byte | 342 ký tự |
| 3.072 bit | 384 byte | 384 byte | 512 ký tự |
| 4.096 bit | 512 byte | 512 byte | 683 ký tự |

Độ dài chữ ký RSA bằng số byte cần thiết để chứa mô-đun, tức làm tròn số bit của mô-đun lên byte gần nhất. Với các kích thước trong bảng, số bit chia hết cho 8 nên số byte tương ứng chính xác.

Mức 2.048 bit là ngưỡng tối thiểu JWA, không phải yêu cầu phù hợp cho mọi thời hạn bảo vệ. Một chính sách có thể yêu cầu 3.072 bit hoặc lớn hơn tùy mức an toàn, tuổi thọ dữ liệu, hiệu năng và tiêu chuẩn tổ chức. Các mức an toàn ước tính của RSA không bằng số bit mô-đun: ví dụ RSA 2.048 bit thường được ước tính khoảng 112 bit an toàn, còn RSA 3.072 bit khoảng 128 bit.

### 4.2. RS và PS dùng loại khóa nào?

`RS256`, `RS384`, `RS512` và `PS256`, `PS384`, `PS512` đều dùng cặp khóa RSA:

- Private key để ký.
- Public key để xác minh.
- `n` là mô-đun và `e` là số mũ công khai trong JWK RSA.

Khác biệt giữa RS và PS là lược đồ chữ ký:

| Nhóm | Lược đồ | Tham số chính |
| --- | --- | --- |
| RS | RSASSA-PKCS1-v1_5 | SHA-256/384/512 theo hậu tố |
| PS | RSASSA-PSS | SHA tương ứng, MGF1 cùng hash và salt length theo JWA |

Không thể dùng chữ ký RS256 để xác minh như PS256. Dù cả hai dùng RSA và SHA-256, padding và quy tắc kiểm tra khác nhau. Verifier phải allowlist chính xác `alg`.

### 4.3. Kích thước RSA và hiệu năng

Khóa RSA lớn hơn thường làm chữ ký dài hơn và tăng chi phí phép toán, đặc biệt phía ký. Xác minh RSA thường có thể tối ưu nhờ public exponent phổ biến, nhưng tải thực tế vẫn phụ thuộc thư viện, phần cứng, KMS/HSM và lưu lượng.

Không chọn mô-đun lớn nhất một cách máy móc. Chọn mức được chính sách cho phép, đáp ứng thời hạn bảo vệ và có thể vận hành trên toàn bộ issuer/verifier.

## 5. Đường cong ECDSA và ràng buộc ES256/384/512

### 5.1. Ánh xạ thuật toán với đường cong

JWA quy định ánh xạ cố định:

| Thuật toán JWS | Đường cong JWK | Hàm băm | Độ rộng tọa độ |
| --- | --- | --- | ---: |
| `ES256` | `P-256` | SHA-256 | 32 byte |
| `ES384` | `P-384` | SHA-384 | 48 byte |
| `ES512` | `P-521` | SHA-512 | 66 byte |

**ES512 dùng P-521**, không phải một đường cong 512 bit. Tên thuật toán phản ánh hàm băm SHA-512; đường cong được JWA chỉ định là P-521.

Mức an toàn ước tính của các đường cong NIST này lần lượt khoảng 128 bit, 192 bit và 256 bit. Đây là mức an toàn, không phải số bit của digest hay số byte chữ ký.

### 5.2. Độ dài chữ ký ECDSA trong JWS

JWS biểu diễn chữ ký ECDSA bằng cách nối hai số nguyên R và S, mỗi số có độ rộng cố định theo đường cong:

| Thuật toán | R | S | Chữ ký raw R||S | Base64URL không padding |
| --- | ---: | ---: | ---: | ---: |
| ES256 | 32 byte | 32 byte | 64 byte | 86 ký tự |
| ES384 | 48 byte | 48 byte | 96 byte | 128 ký tự |
| ES512 | 66 byte | 66 byte | 132 byte | 176 ký tự |

Đây không phải định dạng ASN.1 DER. Nếu thư viện mật mã trả DER, lớp JOSE phải chuyển đổi đúng sang raw fixed-width R||S khi tạo JWS và chuyển ngược lại nếu API xác minh chỉ nhận DER.

### 5.3. Không được tự ý thay đường cong

ES256 chỉ đi với P-256, ES384 với P-384 và ES512 với P-521 theo JWA. Không dùng một khóa P-384 rồi khai báo `alg: ES256`, dù thư viện nền có thể thực hiện ECDSA trên đường cong đó. Verifier phải kiểm tra curve thực tế của public key khớp với thuật toán được cấu hình.

Khóa EC trong JWK dùng `kty: EC`, trường `crv`, `x` và `y`. Public point phải hợp lệ trên đường cong được chọn. Không nhận đường cong tùy ý chỉ vì token cung cấp metadata.

## 6. EdDSA: Ed25519 và Ed448

### 6.1. Đặc điểm và kích thước

Trong JOSE, JWA sử dụng giá trị `alg: EdDSA` cho Ed25519 và Ed448. Đường cong được nhận diện trong JWK qua `crv`:

| Biến thể | JWK crv | Public key | Private seed | Chữ ký |
| --- | --- | ---: | ---: | ---: |
| Ed25519 | Ed25519 | 32 byte | 32 byte | 64 byte |
| Ed448 | Ed448 | 57 byte | 57 byte | 114 byte |

Ed25519 dùng SHA-512 bên trong thiết kế thuật toán; Ed448 dùng SHAKE256. Không suy ra hàm băm từ tên `alg`, vì JWA dùng một tên chung `EdDSA` cho cả hai biến thể.

### 6.2. JWK và ràng buộc loại khóa

Ed25519 và Ed448 thuộc JWK loại `OKP` (Octet Key Pair), không phải `EC`:

| Thuộc tính | Giá trị |
| --- | --- |
| kty | OKP |
| crv | Ed25519 hoặc Ed448 |
| x | Public key |
| d | Private seed; không công bố trong public JWKS |
| JWS alg | EdDSA |

Chữ ký EdDSA là chuỗi byte theo định dạng EdDSA, không phải DER ECDSA và không phải R||S. Không dùng quy trình chuyển đổi DER của ECDSA cho EdDSA.

### 6.3. Khả năng hỗ trợ không đồng nhất

Một hệ thống có thể hỗ trợ Ed25519 nhưng không hỗ trợ Ed448. Cần kiểm tra riêng:

- JOSE library có hỗ trợ JWS `EdDSA` không?
- Crypto provider có hỗ trợ biến thể đường cong cần dùng không?
- Có import/export JWK `OKP` đúng định dạng không?
- KMS/HSM có thể thực hiện ký bằng khóa EdDSA không?
- Gateway và tất cả verifier có thể xác minh cùng biến thể không?

Không coi Ed25519ph hoặc Ed448ph là tương đương với EdDSA chuẩn trong JWS. Phải dùng đúng profile được JWA/JOSE quy định.

## 7. Bảng tổng hợp kích thước và định dạng

| JWS alg | Loại khóa/JWK | Kích thước khóa hoặc tham số chính | Chữ ký nhị phân | Định dạng chữ ký JWS |
| --- | --- | --- | ---: | --- |
| HS256 | Secret | Tối thiểu 32 byte, entropy cao | 32 byte | MAC bytes |
| HS384 | Secret | Tối thiểu 48 byte, entropy cao | 48 byte | MAC bytes |
| HS512 | Secret | Tối thiểu 64 byte, entropy cao | 64 byte | MAC bytes |
| RS256/384/512 | RSA | Modulus tối thiểu 2.048 bit | Bằng modulus theo byte | RSA signature bytes |
| PS256/384/512 | RSA | Modulus tối thiểu 2.048 bit | Bằng modulus theo byte | RSA-PSS signature bytes |
| ES256 | EC / P-256 | Scalar và public point P-256 | 64 byte | Raw R||S |
| ES384 | EC / P-384 | Scalar và public point P-384 | 96 byte | Raw R||S |
| ES512 | EC / P-521 | Scalar và public point P-521 | 132 byte | Raw R||S |
| EdDSA / Ed25519 | OKP / Ed25519 | Seed/public key 32 byte | 64 byte | EdDSA signature octets |
| EdDSA / Ed448 | OKP / Ed448 | Seed/public key 57 byte | 114 byte | EdDSA signature octets |

Bảng giúp ước lượng kích thước và kiểm tra định dạng. Nó không thay thế việc đánh giá entropy, security strength, nguồn khóa và policy.

## 8. Ràng buộc thuật toán với JWK và key metadata

### 8.1. Loại JWK phải khớp

| Họ thuật toán | JWK kty | Trường khóa công khai chính | Ràng buộc |
| --- | --- | --- | --- |
| HS | Không có JWK public tương đương | Secret đối xứng | Không công bố secret trong JWKS |
| RS/PS | RSA | n, e | Modulus đủ lớn; đúng issuer và alg |
| ES | EC | crv, x, y | Curve khớp chính xác thuật toán |
| EdDSA | OKP | crv, x | Ed25519/Ed448 đúng biến thể |

JWK có thể chứa metadata như `kid`, `use`, `key_ops`, `alg`. Những trường này hỗ trợ lựa chọn và giới hạn mục đích sử dụng, nhưng verifier vẫn cần policy tin cậy của riêng mình. `alg` trong JWK hoặc JWT không tự chứng minh khóa hợp lệ.

### 8.2. Ràng buộc theo thuật toán

~~~text
HS256 -> HMAC secret, key >= 32 bytes
RS256 -> RSA key, modulus >= 2048 bits
PS256 -> RSA key, modulus >= 2048 bits, PSS parameters per JWA
ES256 -> EC key on P-256
EdDSA -> OKP key on Ed25519 or Ed448
~~~

Không dùng một khóa cho nhiều thuật toán chỉ vì cùng họ toán học. Ví dụ RSA key có thể về mặt toán học tham gia cả RS và PS, nhưng hệ thống nên gắn key ID với thuật toán/mục đích được phép và tránh tái sử dụng khóa chéo thuật toán nếu policy không yêu cầu. Điều này giảm nguy cơ algorithm confusion và đơn giản hóa rotation/audit.

### 8.3. kid và nguồn khóa

`kid` chỉ là định danh để tra khóa trong tập khóa đã được cấu hình tin cậy. Verifier cần:

1. Xác định issuer theo policy cho phép.
2. Tra `kid` trong JWKS/key set của issuer đó.
3. Kiểm tra loại JWK và curve/modulus.
4. Kiểm tra `alg` được allowlist và khớp metadata khóa.
5. Xác minh chữ ký.
6. Kiểm tra claims như `iss`, `aud`, `exp`, `nbf` và quyền.

Không dùng `kid` làm URL, đường dẫn tệp hoặc truy vấn không kiểm soát. Không tải `jku`/`x5u` tùy ý do header chưa xác thực cung cấp.

## 9. Các lớp tương thích cần kiểm tra

### 9.1. Profile và hợp đồng giao thức

Một thuật toán có trong RFC chưa chắc được profile tích hợp cho phép. Kiểm tra:

- Profile JWT/JWS hoặc OIDC có cho phép `alg` này không?
- Issuer có công bố thuật toán ký tương ứng cho đúng loại token không?
- Client, RP, API hoặc đối tác có cấu hình allowlist phù hợp không?
- Chính sách tổ chức hoặc chứng nhận có giới hạn key size, curve hay thuật toán không?
- Có yêu cầu tương thích với hệ thống cũ không?

Trong OpenID Connect, các thuộc tính metadata hỗ trợ thuật toán có thể khác nhau theo loại thông điệp, chẳng hạn ID Token, UserInfo hoặc Request Object. Không suy ra hỗ trợ cho mọi token chỉ từ một trường metadata.

### 9.2. JOSE library và crypto provider

Tách riêng hai tầng:

| Tầng | Cần xác nhận |
| --- | --- |
| JOSE/JWT library | Có parse, sign và verify JWS với đúng alg không? Có xử lý JWK/JWKS không? |
| Crypto provider | Có primitive HMAC/RSA-PSS/ECDSA/EdDSA và curve cần thiết không? |
| Key import/export | Có hiểu đúng PEM, DER, JWK, raw seed hoặc key handle không? |
| Signature encoding | Có xử lý RSA bytes, ECDSA raw R||S và EdDSA octets đúng chuẩn không? |
| Runtime/OS | Phiên bản runtime, provider và image production có hỗ trợ không? |

Thư viện mật mã hỗ trợ ECDSA không có nghĩa JOSE layer tự động chuyển DER sang raw R||S. Provider hỗ trợ Ed25519 không chứng minh JWT library đã hỗ trợ `alg: EdDSA`.

### 9.3. KMS/HSM và quản lý khóa

Kiểm tra đúng khả năng của dịch vụ quản lý khóa:

- HMAC: hỗ trợ tạo MAC với đúng SHA và độ dài khóa?
- RSA: hỗ trợ đúng kích thước modulus và RSASSA-PKCS1-v1_5 hoặc PSS?
- PSS: có cấu hình được MGF1 hash và salt length theo JWA không?
- ECDSA: hỗ trợ đúng P-256/P-384/P-521 và định dạng chữ ký trả về?
- EdDSA: hỗ trợ đúng Ed25519/Ed448, ký và xác minh?
- Key không export được: JOSE library có tích hợp được qua key handle hoặc remote signing API không?

Một KMS hỗ trợ RSA signing không có nghĩa nó hỗ trợ PSS hoặc mọi tham số PSS. Một HSM hỗ trợ Ed25519 không nhất thiết hỗ trợ Ed448.

### 9.4. Gateway, proxy và mọi verifier

Liệt kê toàn bộ đường đi của JWT:

~~~text
Issuer -> API Gateway -> Reverse Proxy -> Service A -> Service B
             |                              |
             +---------- JWKS --------------+
~~~

Mỗi thành phần có thể xác minh token cần cùng hiểu thuật toán, key type, curve, signature encoding và policy. Một service hỗ trợ ES256 nhưng gateway chỉ hỗ trợ RS256 vẫn làm request thất bại trước khi tới service.

## 10. Lỗi tương thích thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HS256 báo khóa quá ngắn | Secret thực tế sau decode dưới 32 byte | Kiểm tra encoding và sinh lại khóa ngẫu nhiên đủ dài |
| HS512 dùng secret 32 byte | Không đáp ứng mức tối thiểu 64 byte của JWA | Sinh secret mới đủ 64 byte entropy cao |
| RS/PS bị từ chối | RSA modulus dưới 2.048 bit hoặc sai key | Kiểm tra modulus và key pair |
| RS256 không xác minh được như PS256 | Lược đồ PKCS#1 v1.5 khác PSS | Cấu hình đúng alg và tham số |
| ES256 với key P-384 | Curve không khớp thuật toán | Dùng P-256 hoặc chọn thuật toán/profile phù hợp |
| ES512 cấu hình P-512 | Nhầm hậu tố SHA-512 với curve | ES512 dùng P-521 |
| ECDSA signature sai độ dài | Đưa DER vào JWS thay vì raw R||S | Chuyển đổi đúng theo JWA hoặc dùng JOSE library |
| EdDSA không import được key | Nhầm kty EC với kty OKP, sai crv hoặc provider | Dùng JWK OKP và xác nhận biến thể |
| Ed25519 chạy, Ed448 lỗi | Chỉ hỗ trợ một curve | Kiểm tra riêng Ed448 ở mọi tầng |
| Chữ ký đúng nhưng verifier từ chối | Allowlist, issuer, audience hoặc key mapping không khớp | Phân biệt lỗi mật mã và lỗi policy |
| Gateway và service có kết quả khác nhau | Khác phiên bản library, provider, JWKS cache hoặc policy | Kiểm thử chéo và chuẩn hóa cấu hình |

## 11. Quy trình đánh giá và kiểm thử tương thích

### 11.1. Lập ma trận thuật toán

Với mỗi thuật toán dự kiến dùng, ghi rõ:

| Hạng mục | Giá trị cần xác nhận |
| --- | --- |
| JWS alg | Giá trị chính xác |
| Key type | Secret, RSA, EC hoặc OKP |
| Key size/curve | Độ dài hoặc đường cong bắt buộc |
| Hash/padding | SHA, PKCS#1 v1.5, PSS, ECDSA hoặc EdDSA |
| Signature encoding | MAC bytes, RSA bytes, raw R||S hoặc EdDSA octets |
| JWK metadata | kty, crv, n, e, x, y, kid |
| Profile | Thuật toán có được phép trong giao thức không |
| Implementations | JOSE library, crypto provider, KMS/HSM |
| Verifiers | Gateway, API, partner và dịch vụ trung gian |

### 11.2. Kiểm thử dương tính

1. Sinh/import khóa đúng loại và kích thước.
2. Ký token bằng issuer thực tế.
3. Xác minh token bằng thư viện độc lập.
4. Kiểm tra JWK/JWKS và lựa chọn khóa theo `kid`.
5. Kiểm tra độ dài chữ ký sau Base64URL decode.
6. Kiểm tra rotation: public key mới được phân phối trước khi issuer ký bằng private key mới.
7. Chạy trên runtime, container, KMS/HSM và gateway production.

### 11.3. Kiểm thử âm tính

- Sửa header hoặc payload: chữ ký phải thất bại.
- Dùng key không khớp hoặc key không tin cậy: phải thất bại.
- Khai báo `alg` khác với allowlist: phải bị từ chối.
- Dùng curve không khớp ES256/384/512: phải bị từ chối.
- Dùng RSA key dưới 2.048 bit cho RS/PS: không được cấu hình để chấp nhận.
- Dùng ECDSA DER trong JWS thay raw R||S: phải bị từ chối.
- Dùng Ed448 với verifier chỉ hỗ trợ Ed25519: phải thất bại có kiểm soát, không fallback.
- Gửi token hết hạn, sai issuer hoặc audience: phải bị từ chối dù chữ ký hợp lệ.

### 11.4. Benchmark trong môi trường thật

Đo thời gian ký/xác minh, throughput, độ trễ p95/p99, CPU, bộ nhớ, kích thước JWT, độ trễ KMS/HSM và chi phí cập nhật JWKS. Thực hiện với đúng thư viện, provider, runtime và phần cứng dự kiến chạy production.

Không dùng benchmark primitive đơn lẻ để kết luận hệ thống có thể triển khai. Luồng end-to-end còn có cache, mạng, key lookup, parse JSON và kiểm tra claims.

## 12. Quy trình chọn thuật toán theo ràng buộc

~~~mermaid
flowchart TD
    A[Xác định issuer và verifier] --> B{Verifier có được phép ký?}
    B -->|Có| C{HMAC secret đủ entropy và phân phối an toàn?}
    C -->|Có| D[Đánh giá HMAC]
    C -->|Không| E[Đánh giá chữ ký bất đối xứng]
    B -->|Không| E
    E --> F{Profile cho phép thuật toán nào?}
    F --> G[Chọn RSA / EC / OKP theo policy]
    G --> H{Key size và curve khớp JWA?}
    H -->|Không| I[Chọn lại key hoặc thuật toán]
    H -->|Có| J{JOSE, provider, KMS và verifier hỗ trợ?}
    J -->|Không| K[Nâng cấp hoặc chọn phương án tương thích]
    J -->|Có| L[Kiểm thử chéo và rotation]
    D --> L
    I --> L
    K --> L
    L --> M[Triển khai có giám sát]
~~~

Trình tự ra quyết định:

1. Xác định quyền ký và quyền xác minh của từng thành phần.
2. Xác định profile giao thức và danh sách thuật toán được phép.
3. Chọn loại khóa và thuật toán phù hợp với mô hình tin cậy.
4. Kiểm tra kích thước khóa, entropy và curve theo JWA.
5. Kiểm tra định dạng JWK, signature encoding và nguồn khóa.
6. Kiểm tra thư viện, provider, KMS/HSM, gateway và mọi verifier.
7. Chạy test vector, test chéo, test âm tính và benchmark.
8. Hoàn thiện rotation, thu hồi, rollback và giám sát.

Nếu một tầng quan trọng chưa hỗ trợ, trạng thái phù hợp là **chưa sẵn sàng**. Không nới lỏng allowlist hoặc bỏ kiểm tra key type để làm token “chạy được”.

## 13. Checklist trước khi đưa vào production

- [ ] Đã xác định issuer, verifier, trust boundary và quyền ký.
- [ ] Đã chọn alg được profile và chính sách cho phép.
- [ ] HMAC secret có đủ entropy và tối thiểu 32/48/64 byte theo HS256/384/512.
- [ ] RSA modulus đạt tối thiểu 2.048 bit và đáp ứng chính sách.
- [ ] ES256/384/512 dùng đúng P-256/P-384/P-521.
- [ ] EdDSA dùng đúng OKP Ed25519/Ed448 và đã xác nhận hỗ trợ riêng từng biến thể.
- [ ] kty, crv, alg, kid và key purpose khớp với nhau.
- [ ] Signature encoding đúng chuẩn JWS.
- [ ] Private key/secret được bảo vệ trong hệ thống quản lý khóa.
- [ ] Public JWKS đến từ issuer/endpoint đã được tin cậy.
- [ ] JOSE library, crypto provider, KMS/HSM, gateway và mọi verifier đã được kiểm tra.
- [ ] Đã chạy test vector và test chéo signer-verifier.
- [ ] Đã kiểm thử token sai chữ ký, sai key, sai thuật toán và sai claims.
- [ ] Đã có kế hoạch rotation, overlap, thu hồi và xử lý lộ khóa.
- [ ] Đã benchmark trên môi trường gần production.

## 14. Những hiểu lầm phổ biến

**“Key size bằng security strength.”** Sai. RSA 2.048 bit có mức an toàn ước tính khoảng 112 bit; P-256 có mức an toàn khoảng 128 bit.

**“ES512 dùng đường cong 512 bit.”** Sai. ES512 dùng P-521 và SHA-512.

**“Chữ ký dài hơn luôn an toàn hơn.”** Sai. Độ dài chữ ký phụ thuộc thuật toán và định dạng; nó không thay thế entropy, key custody hoặc verifier policy.

**“Mọi thuật toán RSA đều dùng chung một cách padding.”** Sai. RSASSA-PKCS1-v1_5 và RSASSA-PSS khác nhau.

**“EdDSA chỉ có một kích thước khóa.”** Sai. Ed25519 và Ed448 có kích thước public key, seed và chữ ký khác nhau.

**“Có thể thay curve mà không đổi thuật toán.”** Sai. JWA ánh xạ ES256/384/512 tới curve cụ thể.

**“Thư viện hỗ trợ primitive nghĩa là hệ thống hỗ trợ JWS.”** Sai. Còn phải kiểm tra JOSE, JWK, provider, KMS/HSM và mọi verifier.

**“Public key không bí mật nên nguồn nào cũng dùng được.”** Sai. Nguồn và tính toàn vẹn của public key quyết định verifier đang tin ai.

## 15. Câu hỏi tự kiểm tra

1. Phân biệt key size, entropy, security strength và signature size.
2. HS256, HS384 và HS512 yêu cầu secret tối thiểu bao nhiêu byte?
3. Vì sao chữ ký RS256 có độ dài bằng mô-đun RSA tính theo byte?
4. RS256 và PS256 dùng cùng loại khóa nhưng khác nhau ở điểm nào?
5. Vì sao ES512 dùng P-521? Chữ ký JWS ES512 có bao nhiêu byte?
6. Phân biệt JWK EC và OKP; mỗi loại chứa những trường public key nào?
7. Vì sao không thể suy ra hỗ trợ Ed448 từ việc thư viện hỗ trợ Ed25519?
8. Những tầng nào cần kiểm tra trước khi đưa thuật toán vào production?
9. Nếu chữ ký hợp lệ nhưng audience sai, verifier phải xử lý thế nào?
10. Vì sao tăng key size không sửa được lỗi nguồn JWKS không tin cậy hoặc allowlist quá rộng?

## 16. Tiêu chuẩn và tài liệu tham khảo

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104), cấu trúc HMAC và xử lý khóa.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), JWS Compact, signing input và chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), loại khóa và metadata JWK/JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), các mục 3.2 đến 3.5 về HS, RS, ES, PS.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032), Ed25519 và Ed448.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037), EdDSA và OKP trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), khuyến nghị lựa chọn thuật toán, ràng buộc khóa và xác minh token.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final), hướng dẫn quản lý khóa và mức an toàn tương đương.
