# Biểu diễn khóa PEM, DER, JWK và lỗi chuyển đổi

## 1. Vì sao cùng một khóa có nhiều cách biểu diễn?

Một cặp khóa mật mã có thể được lưu, trao đổi và sử dụng dưới nhiều định dạng. Công cụ hệ điều hành, thư viện mật mã, hệ thống quản lý khóa, certificate authority và thư viện JOSE/JWT không phải lúc nào cũng dùng cùng một định dạng đầu vào.

Các tên thường gặp:

- **PEM**: dạng văn bản có nhãn BEGIN/END và phần nội dung Base64.
- **DER**: cách mã hóa ASN.1 dạng nhị phân.
- **PKCS#1**: cấu trúc ASN.1 dành cho khóa RSA.
- **PKCS#8**: cấu trúc đóng gói private key theo cách tổng quát.
- **SEC1**: cấu trúc private key cho elliptic curve.
- **SubjectPublicKeyInfo (SPKI)**: cấu trúc ASN.1 đóng gói public key cùng thông tin thuật toán.
- **X.509 certificate**: chứng thư chứa public key và các thông tin xác thực certificate.
- **JWK**: biểu diễn khóa dưới dạng JSON dành cho JOSE.

Một file có đuôi .pem không nói đủ cấu trúc bên trong. PEM có thể chứa RSA PKCS#1, PKCS#8, SPKI, EC private key hoặc certificate. Tương tự, file .der chỉ cho biết dữ liệu nhị phân; nó không nói dữ liệu đó là private key, public key, certificate hay chữ ký.

Chuyển đổi sai cấu trúc có thể gây lỗi parse, chọn nhầm khóa, mất tham số, thay đổi ý nghĩa byte hoặc làm lộ private key. Với JWT, một lỗi tinh vi khác là chuyển chữ ký ECDSA DER sang JWS mà không đổi sang dạng JOSE quy định.

Bài thuộc chương **Liên thông và di trú** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho JOSE/JWT, PKI và các hệ thống mật mã; không phụ thuộc Java hay framework.

## 2. Phân biệt PEM, DER và ASN.1

### 2.1. ASN.1 mô tả cấu trúc dữ liệu

ASN.1 là ngôn ngữ mô tả cấu trúc dữ liệu có kiểu, ví dụ INTEGER, OBJECT IDENTIFIER, BIT STRING, OCTET STRING, SEQUENCE và các trường có thể tùy chọn.

Một public key không chỉ là một chuỗi byte. Cấu trúc của nó còn cho biết thuật toán hoặc loại khóa, tham số thuật toán như curve OID, thành phần public key và cấu trúc bao ngoài mà giao thức mong đợi.

ASN.1 mô tả cấu trúc; nó không tự quyết định dữ liệu được tin cậy hay không. Việc parse thành công không chứng minh khóa thuộc issuer đáng tin.

### 2.2. DER là encoding nhị phân

DER (Distinguished Encoding Rules) là một tập quy tắc mã hóa ASN.1 theo dạng xác định, có tính canonical. Một cấu trúc ASN.1 có thể có nhiều cách biểu diễn theo BER, nhưng DER đặt ra quy tắc chặt hơn để có biểu diễn duy nhất cho cùng giá trị.

Đặc điểm thường gặp:

- Dữ liệu ở dạng nhị phân.
- Có tag, length và value theo ASN.1.
- Độ dài được mã hóa theo quy tắc DER.
- Không dùng indefinite length như BER.
- INTEGER và các kiểu khác phải có biểu diễn canonical.

DER thường được dùng làm nội dung nhị phân bên trong PEM.

### 2.3. PEM là textual armor

PEM là cách biểu diễn văn bản cho các cấu trúc nhị phân, thường bằng cách Base64-encode DER rồi đặt giữa dòng nhãn:

~~~text
-----BEGIN PUBLIC KEY-----
BASE64_ENCODED_DER_DATA
-----END PUBLIC KEY-----
~~~

Phần BEGIN/END cho biết loại cấu trúc được đóng gói. Phần Base64 chứa bytes của cấu trúc đó. PEM không thay đổi thuật toán hoặc giá trị khóa; nó là lớp biểu diễn để dễ lưu trong file cấu hình, truyền qua hệ thống văn bản và đọc bằng công cụ.

### 2.4. Quan hệ giữa ba khái niệm

~~~text
Logical key
    |
    v
ASN.1 structure
    |
    v
DER binary encoding
    |
    +---- Base64 + BEGIN/END label ----> PEM text
    |
    +---- parse as binary -------------> DER file
~~~

PEM và DER không phải hai thuật toán khóa. Chuyển PEM sang DER thường chỉ bỏ lớp textual armor và giải Base64, nhưng parser vẫn phải kiểm tra nhãn và cấu trúc ASN.1 mong đợi.

### 2.5. Không phải mọi chuỗi Base64 đều là PEM hợp lệ

Một chuỗi Base64 có thể chứa dữ liệu bất kỳ. Nếu decode thành công, điều đó không chứng minh dữ liệu là DER hợp lệ hoặc là loại key cần dùng.

Quy trình parse phải xác định nhãn PEM, kiểu ASN.1 dự kiến, thuật toán và tham số, các thành phần bắt buộc, cũng như dữ liệu thừa hoặc cấu trúc mơ hồ ngoài policy.

## 3. Các PEM label thường gặp và cấu trúc tương ứng

### 3.1. Bảng nhận diện nhanh

| PEM label | Cấu trúc thường tương ứng | Ý nghĩa |
| --- | --- | --- |
| BEGIN PUBLIC KEY | SubjectPublicKeyInfo (SPKI) | Public key tổng quát cùng AlgorithmIdentifier |
| BEGIN RSA PUBLIC KEY | PKCS#1 RSAPublicKey | Public key RSA gồm modulus và public exponent |
| BEGIN PRIVATE KEY | PKCS#8 PrivateKeyInfo / OneAsymmetricKey | Private key đóng gói tổng quát |
| BEGIN ENCRYPTED PRIVATE KEY | PKCS#8 EncryptedPrivateKeyInfo | Private key PKCS#8 được mã hóa bằng password-based encryption |
| BEGIN RSA PRIVATE KEY | PKCS#1 RSAPrivateKey | Private key RSA truyền thống |
| BEGIN EC PRIVATE KEY | SEC1 ECPrivateKey | Private key elliptic curve |
| BEGIN CERTIFICATE | X.509 Certificate | Chứng thư số, trong đó có SPKI |
| BEGIN CERTIFICATE REQUEST | PKCS#10 CSR | Yêu cầu cấp chứng thư |

Label là dấu hiệu quan trọng nhưng không thay thế việc parse và kiểm tra nội dung. Không nên đổi chữ RSA trong label thành PUBLIC KEY bằng thao tác sửa text.

### 3.2. PUBLIC KEY và RSA PUBLIC KEY khác nhau

BEGIN PUBLIC KEY thường chứa SPKI. SPKI có AlgorithmIdentifier xác định thuật toán và tham số, cùng BIT STRING chứa public key theo định dạng của thuật toán.

BEGIN RSA PUBLIC KEY chứa cấu trúc PKCS#1 RSAPublicKey, về cơ bản gồm modulus n và public exponent e. Nó không có lớp AlgorithmIdentifier SPKI bao ngoài.

Hai cấu trúc có thể đại diện cùng một RSA public key nhưng byte DER khác nhau. Một parser chỉ chấp nhận SPKI có thể từ chối PKCS#1 trực tiếp.

### 3.3. PRIVATE KEY và RSA PRIVATE KEY khác nhau

BEGIN PRIVATE KEY thường là PKCS#8. Cấu trúc này đóng gói version, AlgorithmIdentifier, private key bytes theo thuật toán và các trường tùy chọn theo phiên bản/format.

BEGIN RSA PRIVATE KEY thường là PKCS#1, chứa các thành phần RSA trực tiếp như n, e, d, p, q và tham số CRT.

PKCS#8 có thể mang nhiều loại private key khác nhau; PKCS#1 là cấu trúc riêng cho RSA.

### 3.4. EC PRIVATE KEY và PRIVATE KEY khác nhau

BEGIN EC PRIVATE KEY thường chứa SEC1 ECPrivateKey. Nó có private scalar và có thể có curve parameters hoặc public point.

BEGIN PRIVATE KEY với EC thường là PKCS#8 bao quanh EC private key và AlgorithmIdentifier. Một số công cụ hoặc thư viện chỉ chấp nhận PKCS#8; một số công cụ hỗ trợ cả SEC1.

Không thể đổi label SEC1 thành PKCS#8 mà không thực hiện chuyển đổi cấu trúc thực sự.

### 3.5. ENCRYPTED PRIVATE KEY

BEGIN ENCRYPTED PRIVATE KEY thường chứa PKCS#8 EncryptedPrivateKeyInfo. Dữ liệu private key được mã hóa và cần passphrase cùng thuật toán KDF/cipher tương ứng để giải mã.

Một PEM truyền thống có thể dùng các header riêng như Proc-Type hoặc DEK-Info để biểu diễn dạng mã hóa cũ. Đây không phải cùng cấu trúc với PKCS#8 EncryptedPrivateKeyInfo.

Không xóa header mã hóa hoặc đổi label để “giải mã” file. Cần dùng parser hiểu đúng format và passphrase.

## 4. Các cấu trúc ASN.1 quan trọng

### 4.1. SubjectPublicKeyInfo

SPKI là cấu trúc phổ biến cho public key:

~~~text
SubjectPublicKeyInfo ::= SEQUENCE {
    algorithm         AlgorithmIdentifier,
    subjectPublicKey  BIT STRING
}
~~~

Trường AlgorithmIdentifier cho biết loại khóa và có thể chứa tham số như curve. BIT STRING chứa phần public key theo định dạng thuật toán.

SPKI thường được dùng trong PEM label BEGIN PUBLIC KEY và trường public key của X.509 certificate.

### 4.2. PKCS#1 RSA public key

~~~text
RSAPublicKey ::= SEQUENCE {
    modulus           INTEGER,
    publicExponent    INTEGER
}
~~~

Trong JWK RSA, hai giá trị này trở thành n và e. ASN.1 INTEGER là số nguyên có dấu theo biểu diễn two's complement; JWK Base64urlUInt là biểu diễn unsigned big-endian. Việc chuyển đổi phải xử lý byte sign-padding chính xác.

### 4.3. PKCS#1 RSA private key

PKCS#1 RSA private key có các thành phần:

~~~text
RSAPrivateKey ::= SEQUENCE {
    version           INTEGER,
    modulus           INTEGER,
    publicExponent    INTEGER,
    privateExponent   INTEGER,
    prime1            INTEGER,
    prime2            INTEGER,
    exponent1         INTEGER,
    exponent2         INTEGER,
    coefficient       INTEGER,
    otherPrimeInfos   OPTIONAL
}
~~~

Mapping thường dùng sang RSA private JWK:

| PKCS#1 | RSA JWK |
| --- | --- |
| modulus | n |
| publicExponent | e |
| privateExponent | d |
| prime1 | p |
| prime2 | q |
| exponent1 | dp |
| exponent2 | dq |
| coefficient | qi |
| otherPrimeInfos | oth nếu triển khai hỗ trợ |

qi trong JWK là inverse của q modulo p. Không tự hoán đổi p và q mà quên tính lại CRT parameters. Nếu key là multi-prime RSA, phải xử lý oth theo chuẩn và kiểm tra thư viện đích có hỗ trợ hay không.

### 4.4. PKCS#8 private key

PKCS#8 đặt private key thuật toán cụ thể trong một wrapper tổng quát:

~~~text
PrivateKeyInfo / OneAsymmetricKey
    version
    privateKeyAlgorithm
    privateKey
    attributes? / publicKey?
~~~

Wrapper cho biết thuật toán; trường privateKey chứa encoding riêng của thuật toán đó. Vì vậy, parse PKCS#8 cần tiếp tục parse cấu trúc private key bên trong, không được xem toàn bộ OCTET STRING là raw scalar.

### 4.5. SEC1 EC private key

SEC1 ECPrivateKey có private scalar và có thể chứa parameters/public key:

~~~text
ECPrivateKey ::= SEQUENCE {
    version        INTEGER,
    privateKey     OCTET STRING,
    parameters     [0] ECParameters OPTIONAL,
    publicKey      [1] BIT STRING OPTIONAL
}
~~~

Private scalar là giá trị số theo curve. Public point có thể được mã hóa theo point format. Khi chuyển sang EC JWK, cần biết curve, độ dài field và cách biểu diễn tọa độ.

## 5. JWK và JWKS

### 5.1. JWK là gì?

JSON Web Key (JWK) là đối tượng JSON biểu diễn một khóa. Một JWK có trường kty xác định loại khóa và các trường thành phần phù hợp với loại đó.

Ví dụ RSA public JWK:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-2026-01",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-unsigned-modulus>",
  "e": "AQAB"
}
~~~

### 5.2. JWKS là gì?

JWK Set là JSON object có trường keys chứa một mảng JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

JWKS là container cho nhiều JWK; nó không phải một định dạng mã hóa private key độc lập. Endpoint JWKS công khai thường chỉ xuất public key, không được chứa private key material.

### 5.3. Các trường metadata

| Trường | Ý nghĩa |
| --- | --- |
| kty | Key Type, ví dụ RSA, EC, OKP, oct |
| kid | Key ID để chọn khóa |
| use | Mục đích sử dụng, ví dụ sig hoặc enc |
| key_ops | Các thao tác được phép, ví dụ verify |
| alg | Thuật toán JOSE gắn với khóa nếu được khai báo |
| x5c | Chuỗi X.509 certificate dạng Base64 DER |
| x5t | Thumbprint SHA-1 của certificate, Base64URL |
| x5t#S256 | Thumbprint SHA-256 của certificate, Base64URL |
| x5u | URI trỏ tới certificate chain |

Nếu cả use và key_ops cùng xuất hiện, chúng phải nhất quán. Không coi kid, use hoặc alg là bằng chứng chữ ký hợp lệ; verifier vẫn phải kiểm tra policy và cryptographic operation.

### 5.4. JWK public và private

Một RSA public JWK chỉ cần kty, n, e cùng metadata phù hợp. RSA private JWK có thêm d, p, q, dp, dq, qi và có thể oth.

Một EC public JWK có kty, crv, x, y. EC private JWK có thêm d.

OKP public JWK có kty=OKP, crv và x; private JWK có thêm d.

JWK kty=oct chứa symmetric key trong trường k. Đây là secret key, tuyệt đối không xuất bản trên JWKS endpoint công khai.

## 6. Mapping RSA key sang JWK

### 6.1. RSA public key

RSA public key gồm modulus n và public exponent e. JWK biểu diễn hai giá trị bằng Base64URL-encoded unsigned integer:

~~~json
{
  "kty": "RSA",
  "n": "sXch...",
  "e": "AQAB"
}
~~~

AQAB thường biểu diễn số 65537. Không được coi mọi RSA key đều có exponent này; phải lấy giá trị thực từ key.

### 6.2. Base64urlUInt

RFC 7518 định nghĩa Base64urlUInt cho các số nguyên dương của JWK:

1. Biểu diễn số dưới dạng unsigned big-endian octet string.
2. Dùng biểu diễn tối thiểu, không có leading zero octet thừa.
3. Dùng Base64URL encode.
4. Bỏ padding = theo quy tắc Base64URL.

ASN.1 INTEGER lại là signed two's complement. Nếu byte cao nhất của một số dương có bit cao bằng 1, DER thêm byte 00 ở đầu để giữ dấu dương.

Ví dụ khái niệm:

~~~text
DER INTEGER content:
  00 A4 21 ...
  ^^
  sign-protection byte

JWK Base64urlUInt input:
     A4 21 ...
~~~

Chỉ bỏ byte 00 đầu khi parser xác định đó là byte sign-padding của INTEGER dương. Không cắt byte theo phỏng đoán hoặc xóa tất cả leading zero mà không xét kiểu dữ liệu.

### 6.3. RSA private key

Mapping các thành phần:

~~~text
PKCS#1 modulus          -> JWK n
PKCS#1 publicExponent   -> JWK e
PKCS#1 privateExponent  -> JWK d
PKCS#1 prime1           -> JWK p
PKCS#1 prime2           -> JWK q
PKCS#1 exponent1        -> JWK dp
PKCS#1 exponent2        -> JWK dq
PKCS#1 coefficient      -> JWK qi
~~~

Mỗi số nguyên được chuyển theo Base64urlUInt. Không Base64URL encode nguyên file DER hoặc OCTET STRING PKCS#8 rồi gán vào trường d.

### 6.4. Kiểm tra tính nhất quán RSA

Sau khi chuyển đổi:

- Kiểm tra n = p × q với RSA hai prime.
- Kiểm tra d, e và các tham số CRT thỏa quan hệ toán học.
- Kiểm tra dp và dq tương ứng với private exponent modulo p-1 và q-1.
- Kiểm tra qi đúng theo định nghĩa JWK/RFC.
- Tạo public key từ private key và so sánh n, e.
- Thử sign/verify bằng một test vector độc lập.

Không tự sửa tham số sai bằng cách chỉ đổi thứ tự p và q mà không tính lại các giá trị liên quan.

## 7. Mapping EC key sang JWK

### 7.1. EC public key

EC public key gồm curve và điểm public Q = (x, y). EC JWK dùng:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "<base64url-x-coordinate>",
  "y": "<base64url-y-coordinate>"
}
~~~

### 7.2. Curve name và OID

Trong SPKI hoặc SEC1, curve có thể được biểu diễn bằng OID. JWK dùng tên curve JOSE, ví dụ:

| JWK crv | Curve |
| --- | --- |
| P-256 | NIST P-256 / secp256r1 |
| P-384 | NIST P-384 / secp384r1 |
| P-521 | NIST P-521 / secp521r1 |

Không nhầm P-256 với một chuỗi OID hoặc tên curve tùy thư viện. Cần mapping rõ ràng và xác nhận đúng curve.

### 7.3. Độ dài tọa độ cố định

x và y trong EC JWK là octet string có độ dài theo field size của curve:

| Curve | Độ dài x | Độ dài y |
| --- | ---: | ---: |
| P-256 | 32 byte | 32 byte |
| P-384 | 48 byte | 48 byte |
| P-521 | 66 byte | 66 byte |

Nếu số nguyên tọa độ ngắn hơn chiều dài yêu cầu, phải left-pad bằng byte 00 để đủ chiều dài. Không loại bỏ zero đầu của tọa độ như cách xử lý Base64urlUInt RSA.

Đây là khác biệt quan trọng:

- RSA n, e, d là Base64urlUInt với biểu diễn unsigned tối thiểu.
- EC x, y, d dùng độ dài octet theo curve/field, có padding phù hợp.

### 7.4. EC private scalar

EC JWK private key có trường d. Giá trị này phải được mã hóa theo độ dài phù hợp của curve và nằm trong miền scalar hợp lệ. Không lấy toàn bộ SEC1 DER hoặc PKCS#8 privateKey OCTET STRING làm d.

Public point x, y phải tương ứng với private scalar d trên đúng curve. Nếu private structure không có public point, có thể cần derive public point bằng phép toán elliptic curve từ private scalar và curve.

### 7.5. EC point trong SPKI

Public point thường được đặt trong BIT STRING theo point encoding, ví dụ uncompressed point bắt đầu bằng byte 04, tiếp theo là x và y. Byte 04 là tag của uncompressed point, không thuộc riêng tọa độ x hoặc y.

Không cắt chuỗi byte theo độ dài đoán mò. Hãy parse SPKI, xác định curve và point format, kiểm tra point hợp lệ trên curve rồi mới xuất x, y.

## 8. Mapping OKP và symmetric key

### 8.1. OKP

JWK dùng kty=OKP cho các octet key pair như Ed25519:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<base64url-public-key>"
}
~~~

Private JWK có thêm trường d:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<base64url-public-key>",
  "d": "<base64url-private-seed>"
}
~~~

Với Ed25519, public key raw thường dài 32 byte và private seed theo định nghĩa JOSE cũng có độ dài 32 byte. Cấu trúc PKCS#8 có ASN.1 wrapper quanh key bytes; không copy toàn bộ DER hoặc wrapper bytes vào d.

### 8.2. Không nhầm Ed25519 với X25519

Ed25519 dùng cho chữ ký số; X25519 dùng cho key agreement. Cả hai có thể xuất hiện dưới dạng OKP nhưng crv và mục đích khác nhau.

Không dùng public key X25519 để xác minh EdDSA hoặc dùng private key Ed25519 cho key agreement chỉ vì cùng thuộc họ Curve25519.

### 8.3. Symmetric JWK

JWK kty=oct dùng trường k để chứa raw symmetric key bytes:

~~~json
{
  "kty": "oct",
  "alg": "HS256",
  "k": "<base64url-secret>"
}
~~~

Đây là secret. Không đưa JWK oct vào JWKS public. Không log, không gửi cho client không được phép và không lưu trong repository. Với HMAC, các bên xác minh cũng có khả năng ký vì cùng sở hữu secret; điều này khác với public-key signature.

## 9. Certificate X.509, SPKI và x5c

### 9.1. Certificate không phải public key thuần

X.509 certificate chứa issuer và subject, validity period, serial number, SubjectPublicKeyInfo, extensions như Key Usage/Extended Key Usage/Basic Constraints và chữ ký của CA hoặc issuer certificate.

Public key nằm bên trong certificate, nhưng certificate còn mang các assertion về danh tính và trust chain. Trích public key từ certificate không đồng nghĩa đã xác minh certificate chain.

### 9.2. BEGIN CERTIFICATE

PEM label BEGIN CERTIFICATE thường chứa DER-encoded X.509 certificate. Không parse certificate như thể nó là SPKI hoặc PKCS#1 public key.

Muốn lấy public key, cần parse certificate rồi trích SPKI. Đồng thời, nếu nghiệp vụ dựa vào certificate trust, phải xác minh chain, validity, revocation, name constraints và Key Usage theo policy.

### 9.3. JWK x5c

Trường x5c trong JWK là một mảng certificate được mã hóa Base64 chuẩn, mỗi phần tử chứa DER certificate. Nó không dùng Base64URL encoding giống các trường n, e, x, y.

Điều cần nhớ:

- x5c chứa certificate, không phải raw public key.
- Certificate đầu tiên phải tương ứng với public key trong JWK theo profile áp dụng.
- Certificate chain phải được xác minh riêng nếu hệ thống dựa vào PKI trust.
- x5t và x5t#S256 là thumbprint của certificate, không phải JWK thumbprint.

Không chuyển x5c sang n bằng cách Base64 decode. Phải parse certificate và lấy public key từ SPKI.

### 9.4. Certificate Key Usage

Nếu public key đến từ certificate, kiểm tra Key Usage/Extended Key Usage theo mục đích. Certificate dành cho key encipherment hoặc client authentication không tự động phù hợp để ký JWT. Cần đối chiếu với policy issuer và token profile.

## 10. JWK thumbprint và kid

### 10.1. JWK thumbprint

RFC 7638 định nghĩa cách tạo thumbprint từ tập thành viên JWK tối thiểu cần thiết cho từng loại khóa. Các thành viên được canonicalize theo thứ tự và quy tắc xác định, sau đó hash.

Ví dụ, RSA thumbprint dùng các thành viên e, kty, n; EC dùng crv, kty, x, y; OKP dùng crv, kty, x.

Không hash toàn bộ JSON text tùy ý rồi gọi đó là JWK thumbprint. Thứ tự thuộc tính, whitespace hoặc metadata có thể khác nhưng khóa vẫn giống nhau.

### 10.2. kid không nhất thiết là thumbprint

kid là identifier do issuer chọn. Nó có thể được tạo từ thumbprint, nhưng không bắt buộc. Một issuer có thể dùng UUID, version hoặc ID quản lý khóa.

Nếu dùng thumbprint làm kid, dùng thuật toán hash và canonicalization đúng RFC, namespace theo issuer nếu cần, không tái sử dụng identifier cho key material khác và đảm bảo mọi producer/verifier tính giống nhau.

### 10.3. Thumbprint không chứng minh nguồn gốc

Thumbprint giúp nhận diện một public key một cách xác định. Nó không chứng minh key thuộc issuer đáng tin hoặc certificate chain hợp lệ.

Trust vẫn đến từ issuer configuration, JWKS URI đáng tin, TLS, signature verification và policy.

## 11. Base64, Base64URL và các lỗi byte thường gặp

### 11.1. Base64 và Base64URL khác nhau

Base64URL thay hai ký tự:

| Base64 | Base64URL |
| --- | --- |
| + | - |
| / | _ |

JOSE thường bỏ padding = trong Base64URL. PEM thường dùng Base64 chuẩn với padding theo quy tắc textual encoding.

Không dùng decoder Base64 chuẩn cho JWK field hoặc JWS compact segment mà không xử lý đúng Base64URL. Ngược lại, không dùng Base64URL decoder để parse PEM content nếu parser mong đợi Base64 chuẩn.

### 11.2. Padding và độ dài

Base64 chuẩn có thể có = padding. Base64URL trong JOSE thường được biểu diễn không padding. Decoder cần xử lý theo format và từ chối encoding sai quy tắc.

Không tự thêm/bỏ padding bằng chuỗi thao tác không kiểm tra độ dài. Một decoder quá dễ dãi có thể che giấu dữ liệu bị cắt hoặc lỗi truyền tải.

### 11.3. Leading zero không giống nhau ở mọi kiểu

- ASN.1 INTEGER dương có thể có sign-padding 00.
- RSA JWK Base64urlUInt dùng biểu diễn unsigned tối thiểu.
- EC coordinate cần độ dài cố định và có thể phải giữ/pad zero ở đầu.
- Raw Ed25519 key có độ dài cố định theo thuật toán.

Một hàm trim leading zero dùng chung cho mọi loại key có thể làm hỏng EC coordinate hoặc raw key.

### 11.4. Không nhầm DER bytes với Base64 text

Một file PEM là text; DER là binary. Nếu Base64 encode toàn bộ file PEM, kết quả là Base64 của các ký tự BEGIN/END và nội dung Base64, không phải DER key. JWK field phải nhận đúng key component bytes, không phải file container.

## 12. Chữ ký ECDSA DER và chữ ký JWS

### 12.1. Đây là lỗi liên thông rất phổ biến

Nhiều API mật mã trả chữ ký ECDSA ở dạng ASN.1 DER:

~~~text
SEQUENCE {
    INTEGER r
    INTEGER s
}
~~~

Trong khi JWS theo RFC 7515 và RFC 7518 yêu cầu ECDSA signature ở dạng raw fixed-width:

~~~text
R || S
~~~

Hai định dạng chứa cùng giá trị toán học r và s, nhưng byte representation khác nhau. Không thể đặt trực tiếp chữ ký DER vào JWS signature segment.

### 12.2. Độ dài JOSE signature

| JWS algorithm | Curve | Độ dài R | Độ dài S | Tổng chữ ký |
| --- | --- | ---: | ---: | ---: |
| ES256 | P-256 | 32 byte | 32 byte | 64 byte |
| ES384 | P-384 | 48 byte | 48 byte | 96 byte |
| ES512 | P-521 | 66 byte | 66 byte | 132 byte |

Độ dài là cố định theo curve, không theo độ dài INTEGER DER thực tế.

### 12.3. DER INTEGER có thể thêm byte 00

Trong DER, INTEGER là signed. Nếu bit cao nhất của số dương bằng 1, một byte 00 được thêm để biểu diễn số dương.

Ví dụ minh họa:

~~~text
DER INTEGER r:
  02 21 00 A8 ...
        ^^
        sign padding

JOSE R:
  A8 ... (left-padded after valid integer parsing)
~~~

Quy trình chuyển DER sang JOSE:

1. Parse DER SEQUENCE.
2. Xác nhận có đúng hai INTEGER dương r và s.
3. Xác nhận 1 <= r,s < curve_order.
4. Chuyển mỗi số sang unsigned big-endian.
5. Bỏ sign-padding theo quy tắc ASN.1 parser.
6. Left-pad mỗi giá trị tới độ dài cố định của curve.
7. Nối R và S.

Không cắt byte đầu hoặc cuối tùy tiện. Không chấp nhận INTEGER âm, giá trị ngoài miền hoặc DER không canonical.

### 12.4. Chuyển JOSE R||S về DER

Khi thư viện verify ECDSA chỉ nhận DER:

1. Base64URL-decode JWS signature segment.
2. Kiểm tra tổng độ dài đúng với curve.
3. Tách hai nửa R và S có độ dài cố định.
4. Parse mỗi nửa thành unsigned integer.
5. Kiểm tra miền 1..n-1.
6. Mã hóa mỗi giá trị thành ASN.1 positive INTEGER theo DER, thêm sign-padding khi cần.
7. Đóng gói thành DER SEQUENCE.
8. Đưa DER signature vào API verify.

Đây là chuyển đổi encoding, không phải thay đổi chữ ký toán học.

### 12.5. RSA và EdDSA không dùng dạng ECDSA DER

JWS RSA signature segment chứa raw RSA signature octets với độ dài theo modulus. Không bọc nó vào ASN.1 ECDSA SEQUENCE.

Ed25519 signature là raw signature bytes theo thuật toán EdDSA, thường dài 64 byte. Không chuyển thành cặp INTEGER DER.

Phải biết thuật toán JWS trước khi chọn signature encoding adapter.

## 13. Các lỗi chuyển đổi thường gặp

| Lỗi | Nguyên nhân | Triệu chứng |
| --- | --- | --- |
| Đưa PKCS#1 vào parser chỉ nhận SPKI | Nhầm RSA PUBLIC KEY với PUBLIC KEY | Parse error hoặc thiếu algorithm identifier |
| Đổi PEM label bằng sửa text | Không chuyển cấu trúc ASN.1 | ASN.1 parse failure |
| Đưa DER private key vào JWK d | Nhầm container với key component | Key import fail hoặc key sai |
| Dùng Base64 thay Base64URL | Nhầm alphabet/padding | Decode fail hoặc bytes khác |
| Không xử lý RSA INTEGER sign byte | Nhầm signed ASN.1 với unsigned JWK | Modulus/exponent sai |
| Trim zero của EC coordinate | Dùng quy tắc RSA cho EC | Public point sai hoặc import fail |
| Không xác định curve | Mất OID/parameters | Coordinate không khớp độ dài hoặc sai curve |
| Đưa EC DER signature thẳng vào JWS | Nhầm DER SEQUENCE với R||S | Signature verify fail |
| Đưa JWS R||S vào API chỉ nhận DER | Thiếu adapter | ASN.1 decode error |
| Dùng Ed25519 key như X25519 | Nhầm mục đích curve | Operation không tương thích |
| Đưa certificate DER vào trường n | Nhầm certificate với public key | JWK sai cấu trúc |
| Đưa x5c Base64 vào Base64URL decoder | Nhầm encoding | Certificate bytes sai |
| Công bố private JWK | Không phân biệt public/private members | Lộ khả năng ký hoặc giải mã |
| Không kiểm tra cặp public/private | Chỉ kiểm tra parse | Verify fail dù import thành công |
| Mất metadata thuật toán | Chỉ chuyển key bytes | Algorithm/profile mismatch |

## 14. Chuyển đổi bằng OpenSSL

### 14.1. Xác định loại file trước

Có thể kiểm tra PEM label bằng cách đọc phần đầu file. Sau đó dùng lệnh phù hợp để parse cấu trúc. Không dựa vào extension .pem, .key, .pub hoặc .der để đoán loại dữ liệu.

### 14.2. Export public key dạng SPKI PEM

Từ private key:

~~~bash
openssl pkey -in private-key.pem -pubout -out public-key.pem
~~~

Lệnh pubout xuất public key. Output thông thường dùng SPKI với PEM label BEGIN PUBLIC KEY.

### 14.3. Chuyển SPKI PEM sang DER

~~~bash
openssl pkey -pubin -in public-key.pem -outform DER -out public-key.der
~~~

### 14.4. Chuyển SPKI DER sang PEM

~~~bash
openssl pkey -pubin -inform DER -in public-key.der -pubout -out public-key.pem
~~~

### 14.5. Chuyển private key sang PKCS#8 DER

Với private key đầu vào được OpenSSL hỗ trợ:

~~~bash
openssl pkcs8 -topk8 -nocrypt -in private-key.pem -outform DER -out private-pkcs8.der
~~~

Tùy chọn nocrypt tạo PKCS#8 không mã hóa. File output vẫn là private key nhạy cảm; bảo vệ quyền file và nơi lưu trữ.

Để tạo PKCS#8 PEM được mã hóa, dùng tùy chọn mã hóa và passphrase theo policy của môi trường. Không đặt passphrase trực tiếp trong command line hoặc shell history.

### 14.6. Đọc PKCS#8 DER thành PEM

~~~bash
openssl pkcs8 -inform DER -in private-pkcs8.der -nocrypt -out private-pkcs8.pem
~~~

Nếu file được mã hóa, cần cung cấp passphrase theo cơ chế an toàn mà OpenSSL hỗ trợ.

### 14.7. Chuyển RSA private key PKCS#1 sang PKCS#8

~~~bash
openssl pkcs8 -topk8 -in rsa-private-pkcs1.pem -nocrypt -out rsa-private-pkcs8.pem
~~~

### 14.8. Xuất RSA private key dạng truyền thống PKCS#1

~~~bash
openssl rsa -in rsa-private-pkcs8.pem -traditional -out rsa-private-pkcs1.pem
~~~

Lệnh chỉ áp dụng cho RSA. Không dùng openssl rsa để chuyển EC hoặc OKP key.

### 14.9. Trích public key từ certificate

~~~bash
openssl x509 -in certificate.pem -pubkey -noout -out public-key.pem
~~~

Lệnh trích SPKI public key. Nó không tự xác minh certificate chain, hostname, validity hoặc revocation.

### 14.10. Kiểm tra cấu trúc DER

~~~bash
openssl asn1parse -inform DER -in public-key.der -i
~~~

Lệnh giúp xem cấu trúc ASN.1. Không dùng output này như bằng chứng key thuộc issuer tin cậy.

### 14.11. Kiểm tra key

~~~bash
openssl pkey -in private-key.pem -check -noout
openssl pkey -pubin -in public-key.pem -pubcheck -noout
~~~

Tùy phiên bản OpenSSL và loại key, một số tùy chọn có thể khác. Hãy kiểm tra help của phiên bản đang dùng và chạy trong môi trường test trước khi áp dụng vào pipeline.

### 14.12. OpenSSL không biến mọi key thành JWK bằng đổi format

Các lệnh trên xử lý PEM/DER và cấu trúc khóa. Để tạo JWK/JWKS, cần parser JOSE hoặc công cụ được kiểm chứng hiểu đúng thuật toán và mapping RFC. Không tự lấy output text rồi cắt chuỗi để tạo JSON key.

## 15. Quy trình chuyển đổi an toàn

### 15.1. Bước 1: nhận diện nguồn

Ghi nhận PEM label hoặc loại DER dự kiến, thuật toán và loại key, curve/key size, private hay public, có mã hóa hay không, nguồn phát hành và mục đích sử dụng, key ID hiện tại và token profile liên quan.

Nếu không xác định được cấu trúc, dừng chuyển đổi và xác minh nguồn. Không thử hàng loạt parser trên dữ liệu production không rõ nguồn.

### 15.2. Bước 2: parse nghiêm ngặt

Parser phải xác nhận cấu trúc ASN.1, thuật toán, tham số và thành phần bắt buộc. Từ chối PEM label không phù hợp với nội dung, Base64 lỗi, DER không canonical hoặc bị cắt, dữ liệu thừa ngoài cấu trúc cho phép, key size/curve ngoài policy, private key thiếu tham số bắt buộc và certificate/key material không hợp lệ.

### 15.3. Bước 3: chuẩn hóa public key

Trích public key ở dạng SPKI hoặc key object đã parse. Kiểm tra thuật toán và tham số. Nếu chuyển sang JWK, tạo public members đúng loại key.

Không đưa private members vào JWKS public. Nếu cần private JWK cho một hệ thống nội bộ, lưu trong secret vault/KMS và áp dụng quyền truy cập nghiêm ngặt.

### 15.4. Bước 4: xác minh tính tương đương

Sau khi chuyển đổi:

1. Import key ở định dạng đích.
2. Xuất lại public key theo một định dạng chuẩn.
3. So sánh key material hoặc JWK thumbprint theo RFC.
4. Kiểm tra thuật toán và curve/key size.
5. Thử sign/verify bằng test vector độc lập.
6. Kiểm tra các bên triển khai khác nhau cho cùng kết quả.

Không chỉ so sánh file bytes vì PEM wrapping, DER container hoặc metadata có thể khác dù cùng logical key.

### 15.5. Bước 5: bảo vệ private key trong quá trình chuyển

- Thực hiện trong môi trường có kiểm soát.
- Hạn chế quyền đọc file input/output.
- Không ghi private key vào log, terminal transcript, ticket hoặc chat.
- Không đặt passphrase trong command line.
- Xóa file tạm theo policy và kiểm soát snapshot/backup.
- Ưu tiên HSM/KMS/secret manager cho private key production.
- Chỉ phân phối public key qua JWKS hoặc kênh đã xác thực.

### 15.6. Bước 6: di trú và rotation

Nếu chuyển định dạng mà không đổi key material, kid và trust metadata cần được quản lý nhất quán. Nếu đồng thời thay key material, dùng kid mới và thực hiện rotation có overlap theo policy.

Không tái sử dụng kid cho một key khác chỉ vì file mới có cùng tên.

## 16. PEM/DER/JWK trong quy trình phát hành và xác minh JWT

### 16.1. Issuer

Issuer có thể giữ private key trong KMS/HSM hoặc key store bảo vệ. Thư viện ký có thể nhận key object hoặc một định dạng private key được hỗ trợ, sau đó tạo JWS compact token.

~~~text
Private key (protected)
       |
       v
Signing operation
       |
       v
JWT / JWS

Public key
       |
       v
JWK public representation
       |
       v
JWKS endpoint
~~~

Không đưa private key vào JWKS công khai. Không cần công bố private PEM hoặc private JWK cho resource server.

### 16.2. Resource server

Resource server tải JWKS từ issuer đã tin cậy, parse public JWK, chọn key theo kid và xác minh chữ ký. Key format chuyển đổi phải giữ đúng thuật toán và key material.

Nếu thư viện chỉ nhận PEM/DER, có thể chuyển public JWK thành key object rồi xuất SPKI PEM/DER hoặc dùng API import JWK. Không được tạo PEM bằng cách Base64URL decode trường n rồi thêm label PUBLIC KEY; RSA SPKI còn cần ASN.1 wrapper và AlgorithmIdentifier.

### 16.3. Các lớp dữ liệu cần phân biệt

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| Key material | RSA n/e/d hoặc EC d/x/y | Giá trị mật mã |
| ASN.1 structure | PKCS#1, PKCS#8, SPKI, SEC1 | Cấu trúc đóng gói key |
| Encoding | DER | Mã hóa ASN.1 thành bytes |
| Textual armor | PEM | Base64 + label |
| JOSE representation | JWK/JWKS | JSON representation cho key |
| Signature representation | JWS signature segment | Byte format do thuật toán JOSE quy định |

Một lỗi liên thông thường xảy ra khi nhầm một lớp với lớp khác, ví dụ lấy toàn bộ DER container làm key material hoặc dùng chữ ký DER thay chữ ký JWS raw.

## 17. Kiểm thử tương thích giữa các thư viện và nền tảng

### 17.1. Kiểm thử import/export

Với mỗi loại key cần hỗ trợ:

- Import PEM PKCS#8.
- Import RSA PKCS#1 nếu profile yêu cầu.
- Import EC SEC1 nếu profile yêu cầu.
- Import SPKI public key.
- Parse X.509 certificate và trích SPKI.
- Parse JWK/JWKS.
- Export lại JWK hoặc SPKI.
- So sánh public key thumbprint.

Ghi rõ format nào là bắt buộc và format nào chỉ hỗ trợ để tương thích legacy.

### 17.2. Kiểm thử sign/verify cross-format

Tạo key test một lần, export qua các format và dùng nhiều implementation:

~~~text
Key fixture
   |
   +--> PEM / PKCS#8
   |
   +--> DER / PKCS#8
   |
   +--> SPKI public
   |
   +--> JWK public/private (test only)
            |
            v
      Implementation A signs
            |
            v
      Implementation B verifies
            |
            v
      Implementation C verifies
~~~

Kiểm tra cả chiều ngược lại: token được ký bởi implementation B phải được A/C xác minh. Dùng message và test vectors cố định để kết quả có thể tái lập.

### 17.3. Kiểm thử ECDSA đặc biệt

Với ES256/ES384/ES512:

- Chữ ký DER từ crypto API phải được chuyển sang R||S trước khi tạo JWS.
- Chữ ký JWS R||S phải được chuyển sang DER nếu API verify yêu cầu DER.
- Kiểm tra độ dài chính xác 64/96/132 byte.
- Kiểm tra trường hợp INTEGER DER có sign-padding.
- Kiểm tra trường hợp R hoặc S cần left-padding.
- Từ chối signature length sai hoặc scalar ngoài miền.

### 17.4. Kiểm thử sai định dạng

Tạo fixture lỗi:

- PEM label đúng nhưng Base64 hỏng.
- PEM label không khớp ASN.1 structure.
- DER bị cắt hoặc có trailing bytes.
- PKCS#1 đưa vào parser SPKI.
- PKCS#8 encrypted với passphrase sai.
- RSA JWK có leading zero sai quy tắc.
- EC coordinate thiếu padding hoặc sai độ dài.
- Curve OID không hỗ trợ.
- Ed25519 và X25519 bị tráo.
- JWK public chứa private fields ngoài policy.
- x5c dùng nhầm Base64URL.
- ECDSA DER signature được đặt trực tiếp vào JWS.

Kết quả mong đợi là reject rõ ràng, không fallback sang parse lỏng lẻo hoặc tự sửa dữ liệu không có căn cứ.

## 18. Ma trận tương thích định dạng

| Nguồn | Đích | Điều kiện quan trọng |
| --- | --- | --- |
| RSA PKCS#1 private PEM | PKCS#8 private PEM | Giữ đúng n/e/d/p/q và CRT parameters |
| RSA PKCS#8 DER | RSA private key object | Parse wrapper và inner key structure |
| RSA SPKI DER | RSA public JWK | Parse AlgorithmIdentifier, lấy n/e, Base64urlUInt |
| RSA PKCS#1 public DER | SPKI DER | Thêm wrapper AlgorithmIdentifier đúng |
| EC SEC1 PEM | EC JWK | Xác định curve, scalar d, point x/y |
| EC SPKI DER | EC JWK | Parse curve OID và public point |
| Ed25519 PKCS#8 | OKP JWK | Lấy đúng seed/public raw bytes, không dùng wrapper DER |
| X.509 certificate | Public JWK | Trích SPKI; kiểm tra certificate trust riêng |
| JWK RSA public | SPKI PEM | Tạo ASN.1 SPKI wrapper, không chỉ Base64 decode n |
| JWK EC public | SPKI DER | Tạo AlgorithmIdentifier và EC point encoding |
| JWS ECDSA R||S | Crypto API DER | Parse fixed-width halves và encode ASN.1 DER |
| Crypto API ECDSA DER | JWS R||S | Parse INTEGERs, validate range, left-pad và concatenate |

## 19. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dựa vào extension file | .pem/.der không chỉ cấu trúc | Kiểm tra label và parse ASN.1 |
| Đổi label bằng sửa text | Không chuyển cấu trúc | Dùng converter hiểu PKCS format |
| Nhầm SPKI và PKCS#1 | Hai ASN.1 wrapper khác nhau | Xác định parser yêu cầu loại nào |
| Nhầm PKCS#8 và PKCS#1 | Wrapper tổng quát so với RSA-specific | Chuyển đổi cấu trúc rõ ràng |
| Nhầm SEC1 và PKCS#8 | EC private format khác nhau | Parse đúng curve/AlgorithmIdentifier |
| Decode Base64 nhưng không validate DER | Chỉ kiểm tra lớp encoding | Parse ASN.1 và kiểm tra cấu trúc |
| Dùng Base64URL cho PEM | Nhầm hai alphabet | Chọn decoder theo format |
| Cắt byte zero đầu tùy tiện | Không hiểu INTEGER/coordinate | Dùng quy tắc riêng cho từng key type |
| Đưa certificate làm public key | Nhầm X.509 và SPKI | Trích SPKI từ certificate |
| Đưa private JWK vào JWKS public | Không lọc private members | Chỉ publish public projection |
| Đưa JWK raw fields thành PEM trực tiếp | Thiếu ASN.1 wrapper | Dùng key importer/exporter chuẩn |
| ECDSA signature không verify | DER và R||S bị tráo | Chuyển encoding đúng RFC |
| Private key không khớp public | Chuyển sai component | Derive và so sánh public key |
| Mất curve/algorithm metadata | Chỉ lưu bytes | Bảo toàn AlgorithmIdentifier/profile |
| Chuyển key mà đổi kid không chủ đích | Metadata không nhất quán | Quản lý kid theo key material và issuer |

## 20. Checklist di trú PEM/DER/JWK

### 20.1. Nhận diện

- [ ] Đã xác định chính xác PEM label hoặc DER structure.
- [ ] Đã xác định thuật toán, key type, curve/key size.
- [ ] Đã phân biệt private key, public key và certificate.
- [ ] Đã xác định key có mã hóa hay không.
- [ ] Đã xác định thư viện đích yêu cầu SPKI, PKCS#1, PKCS#8 hay JWK.

### 20.2. Chuyển đổi

- [ ] ASN.1 được parse nghiêm ngặt.
- [ ] RSA Base64urlUInt được encode đúng.
- [ ] EC coordinate có độ dài/padding đúng.
- [ ] Curve OID được mapping đúng sang JWK crv.
- [ ] OKP Ed25519 không bị nhầm X25519.
- [ ] JWK private members không bị đưa vào public JWKS.
- [ ] x5c dùng Base64 DER, không dùng Base64URL.
- [ ] ECDSA DER signature được chuyển thành JWS R||S và ngược lại khi cần.
- [ ] Public key sau chuyển đổi khớp key nguồn.

### 20.3. Bảo vệ

- [ ] Private key không xuất hiện trong log, ticket hoặc repository.
- [ ] File tạm có quyền truy cập hạn chế.
- [ ] Passphrase không nằm trong command line hoặc shell history.
- [ ] Private key production ở KMS/HSM/secret storage phù hợp.
- [ ] JWKS public chỉ chứa public key.
- [ ] Có kế hoạch rotation và quản lý kid.

### 20.4. Tương thích

- [ ] Sign/verify cross-implementation thành công.
- [ ] Test vectors được lưu để tái lập.
- [ ] Các lỗi format bị reject rõ ràng.
- [ ] Certificate chain được kiểm tra riêng nếu sử dụng x5c.
- [ ] Tài liệu format đầu vào/đầu ra của từng hệ thống đã được ghi nhận.

## 21. Câu hỏi tự kiểm tra

1. PEM và DER khác nhau ở lớp nào?
2. Vì sao file có đuôi .pem chưa đủ để xác định cấu trúc key?
3. BEGIN PUBLIC KEY khác BEGIN RSA PUBLIC KEY như thế nào?
4. PKCS#1, PKCS#8 và SEC1 dùng cho những cấu trúc nào?
5. Vì sao ASN.1 INTEGER dương có thể bắt đầu bằng byte 00?
6. RSA JWK n khác EC JWK x ở quy tắc padding ra sao?
7. Vì sao không thể lấy toàn bộ PKCS#8 DER làm JWK d?
8. JWK x5c dùng Base64 hay Base64URL?
9. JWK thumbprint khác kid như thế nào?
10. Vì sao ECDSA DER signature không thể đặt trực tiếp vào JWS?
11. ES256, ES384 và ES512 có độ dài chữ ký JOSE bao nhiêu?
12. Vì sao Ed25519 và X25519 không thể dùng thay nhau?
13. Khi trích public key từ X.509 certificate, còn phải xác minh điều gì?
14. Những bước nào cần thực hiện để chứng minh key không thay đổi sau chuyển đổi?

## 22. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468), textual encoding và PEM labels.
- [RFC 5208 — PKCS #8: Private-Key Information Syntax Specification](https://www.rfc-editor.org/rfc/rfc5208), cấu trúc PrivateKeyInfo.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958), OneAsymmetricKey và cập nhật định dạng private key package.
- [RFC 8017 — PKCS #1: RSA Cryptography Specifications](https://www.rfc-editor.org/rfc/rfc8017), RSA public/private key structures và thuật toán RSA.
- [RFC 5480 — Elliptic Curve Cryptography Subject Public Key Information](https://www.rfc-editor.org/rfc/rfc5480), EC SPKI và curve identifiers.
- [RFC 5915 — Elliptic Curve Private Key Structure](https://www.rfc-editor.org/rfc/rfc5915), SEC1 EC private key encoding.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), JWS compact serialization và signature representation.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), JWK/JWKS và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), Base64urlUInt, RSA/EC JWK và ECDSA JOSE signature format.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638), canonical JWK thumbprint.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037), OKP, EdDSA và X25519 trong JOSE.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), X.509 certificate và certificate path validation.
- [OpenSSL Documentation](https://docs.openssl.org/), công cụ parse, kiểm tra và chuyển đổi key format.
