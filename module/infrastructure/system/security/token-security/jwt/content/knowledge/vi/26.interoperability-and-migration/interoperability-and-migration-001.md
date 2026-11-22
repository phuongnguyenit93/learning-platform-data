# Ma trận thuật toán và kiểu khóa giữa các hệ thống

## 1. Vì sao cần ma trận thuật toán và kiểu khóa?

JSON Web Token (JWT) có thể được phát hành ở một hệ thống và xác minh hoặc giải mã ở một hệ thống khác. Hai bên có thể dùng ngôn ngữ lập trình, thư viện mật mã, hệ điều hành, dịch vụ quản lý khóa và định dạng lưu trữ khóa khác nhau.

Việc cả hai bên đều tuyên bố hỗ trợ JWT chưa đủ để bảo đảm liên thông. Một bên có thể ký bằng ECDSA nhưng xuất chữ ký theo định dạng ASN.1 DER, trong khi JWS yêu cầu chuỗi byte R nối S có độ dài cố định. Một bên có thể cấu hình RSA-PSS với salt length mặc định của thư viện, trong khi JOSE yêu cầu salt length bằng độ dài đầu ra của hash. Một hệ thống khác có thể đọc khóa PEM nhưng hệ thống còn lại trao đổi khóa dưới dạng JWK.

Các khác biệt này có thể làm token hợp lệ ở issuer nhưng bị từ chối ở resource server. Nguy hiểm hơn, việc tự động hạ cấp thuật toán, dùng sai loại khóa hoặc chia sẻ cùng key material cho nhiều mục đích có thể tạo ra lỗ hổng bảo mật.

Một ma trận liên thông cần trả lời:

- Tên thuật toán JOSE chính xác là gì và được dùng ở vị trí alg hay enc?
- Thuật toán đó yêu cầu họ khóa nào, đường cong nào và kích thước khóa bao nhiêu?
- Bên phát hành cần private key hay shared secret; bên nhận cần public key hay cùng secret?
- JWK phải có những tham số nào, và tham số nào tuyệt đối không được công bố?
- Chữ ký hoặc ciphertext được tuần tự hóa theo định dạng nào?
- Thư viện ở cả hai hệ thống có hỗ trợ cùng thuật toán và cùng tham số không?
- Khi chuyển đổi thuật toán hoặc khóa, hai bên duy trì khả năng xác minh trong khoảng thời gian nào?

## 2. Phân biệt thuật toán JWS và JWE trước khi lập ma trận

Tên alg xuất hiện trong cả JWS và JWE, nhưng ý nghĩa không giống nhau.

| Loại token | Header | Ý nghĩa |
| --- | --- | --- |
| JWS (JWT có chữ ký/MAC) | alg | Thuật toán tạo hoặc xác minh chữ ký số/MAC |
| JWE (JWT được mã hóa) | alg | Thuật toán quản lý khóa: mã hóa, bọc hoặc thỏa thuận Content Encryption Key (CEK) |
| JWE | enc | Thuật toán mã hóa nội dung và bảo vệ tính toàn vẹn của ciphertext |

Ví dụ protected header JWS:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

Đây là JWS dùng chữ ký RSA PKCS#1 v1.5 với SHA-256.

Trong khi đó:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Đây là header JWE: RSA-OAEP-256 bảo vệ CEK bằng RSA-OAEP với SHA-256; A256GCM mã hóa nội dung bằng AES-GCM với khóa 256 bit.

Không được lấy ma trận thuật toán ký JWS để suy ra cách dùng khóa của JWE. Ví dụ RS256 và RSA-OAEP-256 đều liên quan đến RSA nhưng thực hiện hai phép toán khác nhau, có tham số và mục đích khác nhau.

## 3. Các họ khóa trong JWK

JSON Web Key (JWK) là định dạng JSON biểu diễn khóa mật mã. Trường kty cho biết họ khóa; crv xác định đường cong hoặc subtype đối với các họ khóa tương ứng.

| kty | Họ khóa | Tham số công khai thường gặp | Tham số private |
| --- | --- | --- | --- |
| oct | Khóa đối xứng dạng octet | Không có trường public tương đương | k chứa secret key |
| RSA | RSA | n (modulus), e (public exponent) | d, thường có p, q, dp, dq, qi |
| EC | Elliptic Curve | crv, x, y | d |
| OKP | Octet Key Pair, dùng cho EdDSA và XDH | crv, x | d |

Các trường có ý nghĩa:

- kty: họ khóa; giá trị phân biệt chữ hoa/chữ thường.
- crv: đường cong hoặc subtype của khóa.
- x, y: tọa độ hoặc public key material theo định nghĩa của họ khóa.
- n, e: modulus và public exponent của RSA.
- d: private key material.
- k: secret key đối xứng.
- use: mục đích công khai của khóa, thường là sig hoặc enc.
- key_ops: các thao tác được phép, như sign, verify, encrypt, decrypt, wrapKey, unwrapKey, deriveKey hoặc deriveBits.
- alg: thuật toán dự kiến dùng với khóa.
- kid: định danh khóa để tìm khóa tương ứng trong JWK Set.

use, key_ops và alg là metadata giúp ràng buộc cách dùng khóa. Chúng không thay thế allowlist và chính sách tin cậy của verifier. RFC 7517 khuyến nghị không dùng use và key_ops cùng lúc; nếu cả hai cùng xuất hiện, chúng phải nhất quán. JWK alg là tùy chọn, nhưng nếu có thì phải khớp với thuật toán được cấu hình cho khóa.

### Ví dụ JWK công khai

Một RSA public JWK:

~~~json
{
  "kty": "RSA",
  "kid": "signing-rsa-2026-01",
  "use": "sig",
  "alg": "RS256",
  "key_ops": ["verify"],
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

Một EC public JWK:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "kid": "signing-ec-2026-01",
  "use": "sig",
  "alg": "ES256",
  "key_ops": ["verify"],
  "x": "base64url-x-coordinate",
  "y": "base64url-y-coordinate"
}
~~~

Các giá trị n, x, y ở ví dụ là placeholder minh họa, không phải khóa có thể sử dụng. Không sao chép private JWK, k của khóa đối xứng hoặc d của khóa bất đối xứng vào public JWKS.

## 4. Ma trận thuật toán chữ ký JWS và họ khóa

Các thuật toán dưới đây được định nghĩa trong JOSE cho JWS. Mỗi thuật toán phải được ràng buộc với đúng họ khóa và tham số của nó.

| JOSE alg | Phép toán | JWK kty | Đường cong / kích thước khóa | Bên ký | Bên xác minh |
| --- | --- | --- | --- | --- | --- |
| HS256 | HMAC-SHA-256 | oct | Secret tối thiểu 256 bit | Shared secret | Cùng shared secret |
| HS384 | HMAC-SHA-384 | oct | Secret tối thiểu 384 bit | Shared secret | Cùng shared secret |
| HS512 | HMAC-SHA-512 | oct | Secret tối thiểu 512 bit | Shared secret | Cùng shared secret |
| RS256 | RSASSA-PKCS1-v1_5 + SHA-256 | RSA | RSA tối thiểu 2048 bit | RSA private key | RSA public key |
| RS384 | RSASSA-PKCS1-v1_5 + SHA-384 | RSA | RSA tối thiểu 2048 bit | RSA private key | RSA public key |
| RS512 | RSASSA-PKCS1-v1_5 + SHA-512 | RSA | RSA tối thiểu 2048 bit | RSA private key | RSA public key |
| PS256 | RSASSA-PSS + SHA-256, MGF1-SHA-256 | RSA | RSA tối thiểu 2048 bit; salt 32 byte | RSA private key | RSA public key |
| PS384 | RSASSA-PSS + SHA-384, MGF1-SHA-384 | RSA | RSA tối thiểu 2048 bit; salt 48 byte | RSA private key | RSA public key |
| PS512 | RSASSA-PSS + SHA-512, MGF1-SHA-512 | RSA | RSA tối thiểu 2048 bit; salt 64 byte | RSA private key | RSA public key |
| ES256 | ECDSA + SHA-256 | EC | P-256 | EC private key | EC public key |
| ES384 | ECDSA + SHA-384 | EC | P-384 | EC private key | EC public key |
| ES512 | ECDSA + SHA-512 | EC | P-521 | EC private key | EC public key |
| Ed25519 | EdDSA với tham số Ed25519 | OKP | crv: Ed25519 | OKP private key | OKP public key |
| Ed448 | EdDSA với tham số Ed448 | OKP | crv: Ed448 | OKP private key | OKP public key |

Các yêu cầu kích thước khóa RSA và HMAC ở trên xuất phát từ JWA. Chính sách triển khai có thể đặt yêu cầu cao hơn theo tiêu chuẩn mật mã và môi trường vận hành.

### HMAC: cùng một secret ở cả hai phía

Với HS256, issuer và mọi verifier đều cần cùng một secret. Bất kỳ bên nào có secret đều có thể tạo chữ ký hợp lệ, vì vậy việc chia sẻ khóa HMAC làm mở rộng số hệ thống có khả năng phát hành token.

Không dùng mật khẩu người dùng hoặc chuỗi dễ nhớ làm secret. Khóa cần được sinh ngẫu nhiên bằng bộ sinh số ngẫu nhiên mật mã và có entropy tối thiểu theo thuật toán. Nếu cấu hình lưu secret dưới dạng Base64, tất cả hệ thống phải thống nhất giải mã Base64 thành cùng một dãy byte trước khi đưa vào HMAC. Dùng chuỗi Base64 như text key thay vì decode nó sẽ tạo ra một khóa khác.

### RSA: private key ký, public key xác minh

Issuer giữ RSA private key. Resource server chỉ cần RSA public key. Cách này phù hợp khi có nhiều verifier độc lập và không muốn cấp quyền ký token cho từng verifier.

JWA yêu cầu RSA key size ít nhất 2048 bit cho RS* và PS*. Public JWK mang n và e; private JWK có thêm d cùng các tham số private. Public key có thể phân phối qua JWKS; private key phải được giữ trong vùng bảo vệ khóa.

### ECDSA: curve phải khớp chính xác với alg

ES256 nghĩa là ECDSA trên NIST P-256 với SHA-256. Nó không phải một tên chung cho mọi đường cong 256 bit. Ví dụ secp256k1 không phải P-256; không thể thay đường cong mà vẫn giữ alg ES256.

### RSA-PSS: cùng họ RSA nhưng tham số khác RS*

PS256 cũng dùng RSA, nhưng dùng RSASSA-PSS thay cho PKCS#1 v1.5. JOSE quy định hash SHA-256, MGF1-SHA-256 và salt length bằng 32 byte. Một thư viện dùng salt length khác có thể ký ra chữ ký không liên thông dù cả hai bên đều hỗ trợ RSA-PSS.

### Ed25519 và Ed448: lưu ý cập nhật thuật toán

RFC 8037 ban đầu đăng ký thuật toán JOSE EdDSA, trong đó curve được xác định qua crv. RFC 9864, ban hành tháng 10/2025, bổ sung các định danh đầy đủ Ed25519 và Ed448, đồng thời đánh dấu định danh polymorphic EdDSA cũ là deprecated trong registry JOSE.

Với triển khai mới, ưu tiên định danh cụ thể Ed25519 hoặc Ed448 khi các hệ thống và thư viện hai phía hỗ trợ. Registry JOSE hiện ghi các định danh này ở mức triển khai Optional, vì vậy không được giả định mọi thư viện đều đã hỗ trợ. Trong di trú từ hệ thống đang phát hành EdDSA, cần xác nhận rõ thư viện hiện tại, registry và profile mà đối tác thực sự hỗ trợ; không tự đổi chuỗi alg mà không đổi hoặc kiểm tra hợp đồng thuật toán.

JWK cho các khóa này dùng kty OKP, crv tương ứng và x cho public key. d là private key material. X25519 và X448 là subtype dùng cho key agreement, không phải curve để ký EdDSA.

### none không phải một lựa chọn ký an toàn

none là Unsecured JWS, không có chữ ký/MAC. Không đưa none vào allowlist của access token hoặc ID Token thông thường. Chỉ có thể dùng trong profile đặc biệt đã quy định rõ tính toàn vẹn được bảo đảm bằng cơ chế khác và được tách khỏi luồng xác thực thông thường.

## 5. Ma trận JWK theo họ khóa

| Họ khóa | Public JWK | Private JWK | Dùng với |
| --- | --- | --- | --- |
| oct | Không có public key độc lập | k | HMAC JWS; AES key wrap; direct JWE; các thuật toán đối xứng tương ứng |
| RSA | n, e | n, e, d; có thể thêm p, q, dp, dq, qi | JWS RS*/PS*; JWE RSA key management |
| EC | crv, x, y | Public fields và d | JWS ECDSA; JWE ECDH-ES trên curve được hỗ trợ |
| OKP | crv, x | Public fields và d | Ed25519/Ed448 signatures; X25519/X448 key agreement |

Không phải mọi tổ hợp họ khóa và thuật toán đều hợp lệ. Ví dụ:

- Không dùng RSA JWK cho ES256.
- Không dùng EC P-384 cho ES256.
- Không dùng OKP X25519 làm khóa ký Ed25519.
- Không dùng oct JWK công khai; k là secret.
- Không dùng private JWK để xác minh khi public key là đủ.

## 6. Ma trận thuật toán quản lý khóa JWE

Trong JWE, alg xác định cách CEK được tạo, mã hóa, bọc hoặc thỏa thuận. Nó không phải thuật toán mã hóa nội dung.

| JWE alg | Cơ chế | Họ khóa / material | Phía gửi | Phía nhận |
| --- | --- | --- | --- | --- |
| RSA-OAEP | RSAES-OAEP với bộ tham số mặc định của JOSE | RSA | RSA public key của recipient | RSA private key tương ứng |
| RSA-OAEP-256 | RSAES-OAEP với SHA-256 và MGF1-SHA-256 | RSA | RSA public key của recipient | RSA private key tương ứng |
| A128KW / A192KW / A256KW | AES Key Wrap | oct, lần lượt 128/192/256 bit | Shared wrapping key | Cùng wrapping key |
| dir | Dùng trực tiếp shared key làm CEK | oct, kích thước phải khớp enc | Shared CEK | Cùng CEK |
| ECDH-ES | ECDH-ES + Concat KDF, tạo CEK trực tiếp | EC hoặc OKP key agreement phù hợp | Public key recipient và ephemeral private key | Private key recipient |
| ECDH-ES+A128KW / A192KW / A256KW | ECDH-ES, sau đó dùng khóa dẫn xuất để wrap CEK | EC hoặc OKP key agreement phù hợp | Public key recipient và ephemeral private key | Private key recipient |
| PBES2-HS256+A128KW | PBKDF2-HMAC-SHA-256 rồi AES Key Wrap | Password/passphrase cùng salt và iteration count | Passphrase | Cùng passphrase và tham số |

Với ECDH-ES, JWE thường mang ephemeral public key trong header epk; recipient dùng private key tương ứng để tính cùng shared secret. Phải kiểm tra kty, crv và tính hợp lệ của public key point trước khi thực hiện key agreement.

X25519/X448 có thể được dùng cho ECDH-ES theo RFC 8037. Chúng phục vụ key agreement, không được dùng thay cho Ed25519/Ed448 signing keys. RFC 9864 không deprecate các thuật toán mã hóa polymorphic vì chưa định nghĩa replacement cho chúng; do đó, khi dùng ECDH-ES, hai bên vẫn phải thống nhất curve cụ thể, kiểm tra crv của khóa tĩnh và epk, đồng thời giới hạn curve được phép trong profile.

### enc quyết định CEK cần kích thước nào

| JWE enc | Thuật toán nội dung | Kích thước CEK |
| --- | --- | --- |
| A128GCM | AES-GCM | 128 bit (16 byte) |
| A192GCM | AES-GCM | 192 bit (24 byte) |
| A256GCM | AES-GCM | 256 bit (32 byte) |

Ví dụ với alg dir và enc A256GCM, shared key chính là CEK và phải có đúng 32 byte. Với alg A256KW, wrapping key có 32 byte nhưng CEK được wrap có kích thước do enc quyết định. Hai khóa này có vai trò khác nhau và không được nhầm lẫn.

RSA1_5 là thuật toán quản lý khóa JWE dựa trên RSAES-PKCS1-v1_5. RFC 8725 khuyến nghị tránh các thuật toán mã hóa RSA PKCS#1 v1.5 và ưu tiên RSA-OAEP. Điều này không đồng nghĩa RS256 (thuật toán chữ ký JWS) là RSA1_5; hai thuật toán thuộc hai phép toán khác nhau.

## 7. Các định dạng khóa thường gặp giữa các hệ thống

JWK là định dạng trao đổi khóa của JOSE, còn thư viện mật mã có thể sử dụng các định dạng PEM, DER, PKCS#8 hoặc SubjectPublicKeyInfo (SPKI).

| Định dạng | Nội dung | Điểm cần lưu ý |
| --- | --- | --- |
| JWK/JWKS | JSON biểu diễn một hoặc nhiều khóa | Các trường số được Base64URL encode theo quy tắc JWK; không phải PEM |
| PEM | Text armor chứa dữ liệu DER | Chỉ là lớp biểu diễn; cần đọc nhãn để biết cấu trúc bên trong |
| DER | Dữ liệu ASN.1 binary | Cùng một khóa có thể có nhiều cấu trúc DER khác nhau |
| PKCS#1 RSA | Cấu trúc RSA public/private key | Dành riêng cho RSA; không đồng nghĩa PKCS#8 |
| PKCS#8 | Cấu trúc private key tổng quát | Có thể chứa nhiều loại private key |
| SPKI / X.509 SubjectPublicKeyInfo | Cấu trúc public key tổng quát | Thường dùng để trao đổi public key trong PEM |
| X.509 certificate | Chứng thư chứa public key và thông tin định danh/chữ ký CA | Certificate không phải private key; phải kiểm tra chain và chính sách tin cậy |

Tên nhãn PEM như BEGIN PRIVATE KEY, BEGIN RSA PRIVATE KEY, BEGIN PUBLIC KEY hoặc BEGIN CERTIFICATE không thể thay thế việc kiểm tra loại khóa và cấu trúc. Một hệ thống cần biết rõ định dạng mà API import/export của thư viện chấp nhận.

### Quy tắc chuyển đổi quan trọng

- JWK RSA dùng n và e dưới dạng Base64urlUInt; loại bỏ octet zero thừa ở đầu modulus nếu thư viện trả về.
- JWK EC dùng crv, x, y với độ dài octet đầy đủ theo curve.
- JWK OKP dùng crv và x theo encoding được định nghĩa cho subtype.
- JWK private cần d; không gửi tham số private ra public JWKS.
- JWK đối xứng dùng k; không công bố k trong JWKS công khai.
- Không Base64URL encode nguyên chuỗi PEM để điền vào trường x, n hoặc k. Mỗi trường biểu diễn key material theo một cấu trúc cụ thể.

## 8. Khác biệt chữ ký ECDSA: DER và JOSE raw signature

Đây là lỗi liên thông thường gặp khi một bên dùng thư viện OpenSSL hoặc API mật mã trả chữ ký ECDSA dạng ASN.1 DER, còn bên kia mong đợi định dạng JWS.

Trong JWS, chữ ký ECDSA là phép nối hai số nguyên không dấu có độ dài cố định:

~~~text
signature = I2OSP(R, coordinate_length) || I2OSP(S, coordinate_length)
~~~

| Thuật toán | Độ dài R | Độ dài S | Tổng chữ ký JWS |
| --- | --- | --- | --- |
| ES256 / P-256 | 32 byte | 32 byte | 64 byte |
| ES384 / P-384 | 48 byte | 48 byte | 96 byte |
| ES512 / P-521 | 66 byte | 66 byte | 132 byte |

P-521 có 521 bit nhưng mỗi số được biểu diễn bằng 66 byte để đủ số bit. Không được bỏ các byte zero ở đầu R hoặc S khi chuyển đổi sang JWS.

DER thường chứa một SEQUENCE gồm hai INTEGER có độ dài biến đổi, có thể có byte zero đầu để biểu diễn số dương. Vì vậy:

- Không gửi DER signature trực tiếp vào phần signature của JWS.
- Khi ký, chuyển DER (r, s) sang hai octet string độ dài cố định rồi nối R || S.
- Khi xác minh, nếu thư viện chỉ nhận DER, tách JWS signature thành R/S, chuyển thành DER INTEGER/SEQUENCE đúng chuẩn trước khi gọi API.
- Kiểm thử các trường hợp R hoặc S bắt đầu bằng byte zero và P-521.

Một số thư viện JOSE đã tự thực hiện chuyển đổi. Không chuyển đổi lần thứ hai nếu thư viện đã trả chữ ký đúng định dạng JWS.

## 9. Khác biệt tham số RSA-PSS

Tên PS256 không chỉ có nghĩa RSA và SHA-256. JOSE quy định:

- RSASSA-PSS.
- Hash SHA-256.
- Mask Generation Function MGF1 với SHA-256.
- Salt length bằng kích thước hash output, tức 32 byte.
- Các tham số khác theo mặc định được chỉ định trong JWA.

Tương tự, PS384 dùng SHA-384/MGF1-SHA-384 với salt 48 byte; PS512 dùng SHA-512/MGF1-SHA-512 với salt 64 byte.

Một số API RSA-PSS cho phép salt length auto, digest, max hoặc số byte cụ thể. Không dùng mặc định của thư viện mà không xác nhận nó khớp JOSE. Một chữ ký PSS được tạo với salt length khác có thể không xác minh được bằng verifier tuân thủ JOSE.

## 10. Phân biệt RS256, RSA-OAEP và các tên dễ nhầm

| Tên | Vị trí | Mục đích | Khóa |
| --- | --- | --- | --- |
| RS256 | JWS alg | Ký/xác minh bằng RSASSA-PKCS1-v1_5 + SHA-256 | Private ký, public xác minh |
| PS256 | JWS alg | Ký/xác minh bằng RSASSA-PSS + SHA-256 | Private ký, public xác minh |
| RSA-OAEP-256 | JWE alg | Mã hóa/giải mã CEK bằng RSA-OAEP | Public mã hóa, private giải mã |
| RSA1_5 | JWE alg | Mã hóa/giải mã CEK bằng RSAES-PKCS1-v1_5 | Public mã hóa, private giải mã |

Không thể thay RS256 bằng RSA-OAEP-256 chỉ vì cả hai cùng dùng RSA key pair. Chúng không tương thích ở cấp phép toán và định dạng token.

## 11. Ma trận hỗ trợ giữa các hệ thống

Trước khi triển khai, lập một ma trận cụ thể cho từng cặp issuer/verifier. Ví dụ:

| Thành phần | Issuer A | Gateway B | API C |
| --- | --- | --- | --- |
| JWS algorithm | RS256 | Verify RS256 | Verify RS256 |
| Key family | RSA | RSA public JWK | RSA public JWK |
| Key size | 3072 bit | 3072 bit | 3072 bit |
| Key format | Private key trong KMS | Public JWKS | Public JWKS |
| JWK kid | rsa-2026-01 | Cache theo kid | Cache theo kid |
| Token profile | Issuer, audience, type cố định | Cùng profile | Cùng profile |
| Signature encoding | JWS RSA signature | JOSE compact | JOSE compact |

Ma trận trên là ví dụ về cách ghi nhận hợp đồng, không phải khuyến nghị bắt buộc dùng RSA 3072 bit. Cần điền giá trị thực tế đã được hai bên xác nhận.

### Các câu hỏi phải xác nhận với đối tác

1. Có hỗ trợ đúng JOSE algorithm identifier hay chỉ hỗ trợ primitive mật mã cùng tên?
2. Có hỗ trợ đúng JWK kty, crv, alg, use và key_ops không?
3. Có hỗ trợ JWKS endpoint, cache TTL, refresh khi gặp kid mới và xử lý key rollover không?
4. Hệ thống chấp nhận public key dưới dạng JWK, PEM, DER hay certificate?
5. ECDSA signature có được chuyển sang định dạng JWS raw R || S không?
6. RSA-PSS có cấu hình được MGF1 hash và salt length theo JOSE không?
7. Secret HMAC được đọc thành raw bytes hay text; Base64 có được decode trước không?
8. Các thuật toán Ed25519/Ed448 mới có được hỗ trợ không; nếu chỉ hỗ trợ EdDSA, profile cũ nào đang được dùng?
9. Có giới hạn key size, curve, token size hoặc số lượng khóa trong JWKS không?
10. Có hỗ trợ cùng token profile, issuer, audience và token type không?

## 12. Quy tắc ràng buộc thuật toán với khóa

RFC 8725 yêu cầu thư viện cho phép caller chỉ định tập thuật toán được hỗ trợ và không dùng thuật toán ngoài tập đó. Mỗi khóa phải được dùng với đúng một thuật toán và điều này phải được kiểm tra khi thực hiện phép toán mật mã.

Một verifier an toàn nên kiểm tra đồng thời:

- alg nằm trong allowlist cấu hình cho issuer và loại token.
- kty khớp với họ khóa mà thuật toán yêu cầu.
- crv khớp với curve/subtype của thuật toán.
- JWK alg, nếu có, khớp với thuật toán được phép.
- use hoặc key_ops, nếu có, cho phép đúng thao tác verify/decrypt/unwrap/derive.
- kid chỉ được dùng để chọn một khóa trong nguồn tin cậy; không làm thay đổi allowlist.
- Khóa không bị dùng lại cho thuật toán hoặc mục đích khác.
- Kích thước khóa và các tham số mật mã đạt yêu cầu của thuật toán.

Không suy ra thuật toán chỉ từ loại khóa. Một RSA key có thể được thư viện dùng cho nhiều phép toán RSA khác nhau, nhưng profile token phải pin chính xác thuật toán được phép. Không dùng cùng một key material cho cả JWS signing và JWE key management chỉ vì cùng họ RSA.

### Tránh algorithm confusion giữa HMAC và RSA

Không dùng RSA public key như HMAC secret. Nếu verifier chấp nhận cả HS256 và RS256 nhưng chọn cách xử lý khóa không chặt chẽ, attacker có thể lợi dụng khác biệt giữa shared secret và public key để tạo chữ ký giả trong một số triển khai lỗi.

Giải pháp:

- Tách hẳn key set và allowlist theo thuật toán.
- Không chuyển đổi RSA public key thành HMAC secret.
- Không tự động thử lần lượt nhiều thuật toán cho cùng một token.
- Mỗi JWK có metadata và chính sách sử dụng riêng.
- Khi chuyển đổi thuật toán, không tái sử dụng byte khóa cũ làm khóa cho thuật toán mới.

## 13. JWKS và phân phối khóa công khai

JWKS là một JSON Web Key Set chứa một hoặc nhiều JWK. Issuer có thể công bố public keys tại endpoint đã được cấu hình trong metadata tin cậy.

Ví dụ:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-2026-01",
      "use": "sig",
      "alg": "RS256",
      "key_ops": ["verify"],
      "n": "base64url-modulus",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "crv": "P-256",
      "kid": "ec-2026-01",
      "use": "sig",
      "alg": "ES256",
      "key_ops": ["verify"],
      "x": "base64url-x",
      "y": "base64url-y"
    }
  ]
}
~~~

Trong triển khai thật, n, x, y phải là key material hợp lệ. Không đưa private parameters hoặc symmetric secret vào public JWKS.

### Vai trò của kid

kid giúp verifier tìm đúng khóa trong tập khóa đã tin cậy. Nó không phải bằng chứng khóa đáng tin và không phải thuật toán. Verifier cần:

- Giới hạn JWKS URI theo issuer/metadata tin cậy.
- Không tải URL tùy ý từ jku hoặc x5u trong token.
- Không dùng kid để truy vấn tùy ý mà không kiểm tra đầu vào.
- Xử lý kid không tồn tại bằng quy trình refresh JWKS có giới hạn, tránh tạo request storm.
- Từ chối nếu có nhiều khóa phù hợp nhưng không thể chọn duy nhất theo chính sách.
- Cache public keys có TTL và cơ chế cập nhật được xác định.

Với HMAC, secret không được công bố trong JWKS công khai. Nếu các verifier cần cùng secret, phải phân phối qua kênh quản lý secret riêng và kiểm soát từng bên nhận.

## 14. Di trú từ HS256 sang RS256

Một tình huống phổ biến là chuyển từ HMAC dùng chung secret sang chữ ký bất đối xứng để chỉ issuer giữ quyền ký, còn các resource server chỉ cần public key.

### Trước khi di trú

~~~text
Issuer A:
  HS256 secret = shared-secret

Gateway B:
  HS256 secret = shared-secret

API C:
  HS256 secret = shared-secret
~~~

Mọi thành phần có secret đều có thể ký token. Khi một resource server bị xâm nhập, secret có thể bị lấy và dùng để giả mạo token cho toàn hệ thống.

### Sau khi di trú

~~~text
Issuer A:
  RSA private key -> signs RS256
  Public JWK -> publishes JWKS

Gateway B:
  RSA public key -> verifies RS256

API C:
  RSA public key -> verifies RS256
~~~

Resource server không còn cần private signing key. Việc xâm nhập một verifier không tự động cung cấp khả năng phát hành token giả.

### Các giai đoạn chuyển đổi

1. **Kiểm kê:** xác định issuer, verifier, token profile, secret đang dùng, TTL access token, refresh token và các hệ thống có thể ký.
2. **Chọn mục tiêu:** thống nhất RS256 hoặc thuật toán bất đối xứng khác được cả hai phía hỗ trợ; xác định key size, JWK fields, kid và profile.
3. **Tạo key pair mới:** tạo RSA private key trong KMS/HSM hoặc kho khóa được kiểm soát; không chuyển shared secret cũ thành private key.
4. **Phân phối public key:** công bố public JWK qua JWKS tin cậy và triển khai verifier hỗ trợ RS256 trước khi issuer bắt đầu phát token mới.
5. **Mở cửa sổ tương thích:** verifier tạm thời chấp nhận token HS256 cũ và RS256 mới, nhưng mỗi thuật toán phải gắn với key riêng và allowlist rõ ràng.
6. **Chuyển issuer:** phát hành token mới chỉ với RS256; không tiếp tục phát token HS256 trong giai đoạn cuối.
7. **Chờ token cũ hết hiệu lực:** giữ khả năng xác minh HS256 trong khoảng tối đa bằng TTL token cũ cộng clock skew và độ trễ triển khai/cache đã xác định.
8. **Ngừng HS256:** loại secret cũ khỏi verifier, xóa cache liên quan và thu hồi secret theo quy trình quản lý khóa.
9. **Theo dõi:** đo số token theo từng alg/kid, lỗi xác minh và hệ thống vẫn phát token cũ.

Không bật allowlist chung quá rộng chỉ để hoàn tất di trú. Nếu một token có alg RS256, verifier chỉ chọn RSA public key được gắn với RS256; không thử HMAC nếu xác minh RSA thất bại.

## 15. Di trú giữa RS256 và PS256 hoặc ECDSA

Đổi RS256 sang PS256 không chỉ là đổi chuỗi alg. Cả hai dùng RSA nhưng primitive, tham số và khả năng hỗ trợ của thư viện có thể khác.

Đổi RSA sang ECDSA cần:

- Tạo key pair EC mới trên curve đúng với ES256, ES384 hoặc ES512.
- Phân phối JWK có kty EC, crv, x, y.
- Kiểm tra ECDSA signature encoding R || S.
- Kiểm tra thư viện hỗ trợ curve và kích thước signature tương ứng.
- Cấu hình allowlist riêng cho thuật toán mới.

Trong thời gian chuyển đổi, verifier có thể xác minh cả thuật toán cũ và mới nếu profile cho phép, nhưng phải giữ key binding riêng. Không tái sử dụng một key pair cho hai thuật toán chỉ để giảm số lượng khóa.

## 16. Quy trình xoay vòng khóa

Xoay vòng khóa ký thường cần thời gian chồng lấp giữa public key cũ và mới:

1. Tạo key pair mới với thuật toán đã thống nhất.
2. Công bố public key mới trong JWKS với kid mới.
3. Chờ các verifier tải và cache public key mới.
4. Chuyển issuer sang ký bằng private key mới.
5. Giữ public key cũ đủ lâu để xác minh token cũ còn hạn, cộng clock skew và độ trễ phân phối.
6. Xác nhận không còn token hợp lệ được ký bằng khóa cũ.
7. Gỡ public key cũ khỏi JWKS và thu hồi private key cũ theo quy trình.

Nếu khóa cũ bị xâm phạm, không áp dụng cửa sổ chồng lấp thông thường một cách máy móc. Cần chính sách ứng phó sự cố, thu hồi token và cập nhật verifier khẩn cấp theo phạm vi ảnh hưởng.

### Thời gian chồng lấp cần tính như thế nào?

~~~text
old_key_retention =
    maximum_old_token_lifetime
  + maximum_clock_skew
  + JWKS_cache_and_propagation_margin
~~~

Đây là công thức lập kế hoạch, không phải giá trị mặc định. Nếu có refresh token hoặc token được lưu trữ lâu hơn access token, cần tính riêng loại token đó. Không giữ public key cũ vô thời hạn nếu không còn nhu cầu xác minh.

## 17. Các lỗi liên thông thường gặp

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Dùng sai alg cho JWS/JWE | Token bị từ chối hoặc giải mã sai | Xác định đúng vị trí alg và loại JOSE object |
| Dùng RS256 thay cho RSA-OAEP-256 | Nhầm ký với mã hóa CEK | Chọn thuật toán theo phép toán cần thực hiện |
| Dùng RSA public key làm HMAC secret | Có thể dẫn đến algorithm confusion | Tách key family và allowlist |
| Secret HMAC khác byte do Base64/text handling | HMAC verification thất bại | Chuẩn hóa cách giải mã và byte sequence |
| HMAC secret yếu | Có thể brute-force offline khi token bị lộ | Sinh secret ngẫu nhiên đủ entropy |
| RSA key nhỏ hơn yêu cầu | Một số thư viện từ chối hoặc chính sách không đạt | Dùng RSA tối thiểu 2048 bit theo JWA |
| PS256 salt length không đúng | Chữ ký không xác minh được | Cố định SHA-256, MGF1-SHA-256 và salt 32 byte |
| ECDSA signature DER thay vì raw R || S | Chữ ký sai độ dài hoặc verify thất bại | Chuyển đổi theo JWS serialization |
| ES256 nhưng dùng secp256k1 | Curve mismatch | Dùng đúng P-256 hoặc thuật toán đăng ký riêng |
| EdDSA polymorphic được dùng trong hệ thống mới | Khác biệt negotiation/curve support | Đánh giá RFC 9864 và hỗ trợ Ed25519/Ed448 cụ thể |
| Công bố private JWK hoặc secret oct | Lộ khả năng ký/giải mã | Chỉ công bố public keys |
| kid không khớp giữa token và JWKS | Không tìm được khóa | Quản lý kid duy nhất, cập nhật JWKS trước khi ký |
| JWKS cache quá lâu | Token dùng khóa mới bị từ chối | Đặt TTL, refresh và rollover window |
| Cùng key material dùng nhiều thuật toán | Tăng rủi ro confusion và vi phạm key separation | Một khóa cho một thuật toán/mục đích |
| Thử mọi thuật toán khi verify thất bại | Tạo fallback và algorithm confusion | Chọn đúng thuật toán từ profile allowlist |
| Dùng cùng token profile cho mọi audience | Cross-JWT confusion | Ràng buộc issuer, audience, typ và profile |

## 18. Bộ kiểm thử liên thông giữa hai hệ thống

Kiểm thử phải thực hiện theo cả hai chiều khi cả hai bên có trách nhiệm phát hành và xác minh:

| Bài kiểm thử | Hệ thống A | Hệ thống B | Kỳ vọng |
| --- | --- | --- | --- |
| Ký và xác minh JWS | Ký token | Xác minh token | B chấp nhận đúng token |
| Ký và xác minh chiều ngược | Ký token | Xác minh token | A/B thống nhất nếu cả hai đều là issuer được tin cậy |
| Public JWK import | Xuất JWK | Import JWK | Cùng public key fingerprint |
| JWKS rollover | Công bố key mới | Refresh JWKS | B xác minh token có kid mới |
| RSA PKCS#1 v1.5 | RS256 | RS256 | Chữ ký hợp lệ |
| RSA-PSS | PS256 | PS256 | Salt/MGF1/hash đúng JOSE |
| ECDSA P-256 | ES256 | ES256 | Signature 64 byte, verify thành công |
| ECDSA P-384/P-521 | ES384/ES512 | Cùng thuật toán | Signature đúng độ dài và verify thành công |
| Ed25519/Ed448 | Thuật toán cụ thể | Cùng thuật toán | Chỉ chấp nhận nếu cả hai hỗ trợ cùng identifier và key subtype |
| HMAC | HS256 | HS256 | Hai bên dùng đúng cùng byte secret |
| Key mismatch | Token ký bằng key A | Verify bằng key B | Từ chối |
| Algorithm mismatch | Token RS256 | Chỉ cho phép ES256 | Từ chối |
| Curve mismatch | Token ES256 với key P-384 | Verify | Từ chối |
| Key operation mismatch | JWK chỉ có key_ops verify | Thử ký | Không cho phép ký |
| Public/private separation | Public JWKS | Kiểm tra nội dung | Không có private parameters hoặc secret |

### Kiểm thử âm bắt buộc

- Token dùng alg ngoài allowlist.
- Token có kid không tồn tại.
- JWKS có hai khóa trùng kid và không thể chọn duy nhất.
- JWK có kty hoặc crv không khớp alg.
- JWK alg, use hoặc key_ops mâu thuẫn với chính sách.
- Token được ký bằng private key khác với public key công bố.
- Chữ ký ECDSA dùng DER trong khi verifier yêu cầu raw JWS.
- RSA-PSS dùng salt length sai.
- Token HS256 được gửi đến verifier chỉ cho phép RS256.
- Token RS256 được gửi đến verifier chỉ cho phép HS256.
- JWE dùng enc không được hỗ trợ hoặc CEK sai kích thước.
- ECDH-ES nhận curve hoặc ephemeral public key không hợp lệ.
- JWKS endpoint lỗi, key mới chưa được cache hoặc cache đã stale.

## 19. Dùng test vector chuẩn và kiểm thử theo hành vi

Không nên chỉ kiểm thử bằng token do cùng một thư viện tạo và xác minh. Cách đó có thể che giấu lỗi tuần tự hóa vì hai phía cùng mắc một giả định.

Nên:

1. Dùng test vectors trong RFC liên quan cho JWS, JWE, JWA và JWK.
2. Ký token bằng implementation A rồi xác minh bằng implementation B.
3. Ký bằng B rồi xác minh bằng A nếu cả hai được phép phát hành.
4. So sánh public key bằng JWK thumbprint hoặc fingerprint đã chuẩn hóa, không so sánh chuỗi PEM thô.
5. Kiểm thử các giá trị biên như byte zero đầu của RSA modulus, R/S có byte zero đầu và salt length RSA-PSS.
6. Kiểm thử rollover trong điều kiện cache, clock skew và nhiều node.
7. Lưu lại test vectors bất biến để chạy regression sau khi nâng cấp thư viện.

Một test vector cần ghi rõ:

- JOSE object type: JWS, JWE hoặc nested JWT.
- alg, enc, typ và các header liên quan.
- JWK public key và key fingerprint.
- Key family, curve, key size và encoding.
- Signing input hoặc ciphertext đầu vào.
- Signature/tag kỳ vọng.
- Kết quả chấp nhận/từ chối.

Không đưa private key hoặc shared secret production vào bộ test. Dùng test keys riêng, không có quyền truy cập dữ liệu thật.

## 20. Checklist trước khi kết nối hai hệ thống

- [ ] Hai bên thống nhất loại token: JWS, JWE hay nested JWT.
- [ ] Hai bên thống nhất vị trí và ý nghĩa của alg/enc.
- [ ] Có allowlist thuật toán theo issuer, audience và token profile.
- [ ] Mỗi khóa được gắn với đúng một thuật toán và mục đích.
- [ ] kty, crv, key size và key operations khớp thuật toán.
- [ ] Thống nhất định dạng khóa trao đổi: JWK/JWKS, PEM, DER, PKCS#8 hoặc certificate.
- [ ] Public JWKS không chứa private key hoặc symmetric secret.
- [ ] HMAC secret được sinh đủ entropy và phân phối qua secret manager.
- [ ] ECDSA dùng đúng raw signature R || S của JWS.
- [ ] RSA-PSS dùng đúng MGF1 hash và salt length.
- [ ] Ed25519/Ed448 được thống nhất theo identifier hiện hành; có kế hoạch tương thích nếu còn EdDSA cũ.
- [ ] kid, JWKS cache, refresh và key rollover đã được thử nghiệm.
- [ ] Issuer, audience, token type và claims profile được xác minh độc lập với thuật toán.
- [ ] Có positive tests, negative tests và test vectors liên thông giữa implementation khác nhau.
- [ ] Có kế hoạch di trú và thời điểm loại bỏ thuật toán/khóa cũ.

## 21. Sơ đồ quy trình tích hợp và di trú

~~~mermaid
flowchart TD
    A[Kiểm kê issuer, verifier và token profile] --> B[Chọn JOSE algorithm và key family]
    B --> C[Đối chiếu kty, crv, key size và encoding]
    C --> D{Hai phía hỗ trợ cùng profile?}
    D -- Không --> E[Chọn phương án tương thích hoặc nâng cấp]
    E --> B
    D -- Có --> F[Tạo key mới và công bố public JWK/JWKS]
    F --> G[Triển khai verifier và cache key mới]
    G --> H[Chạy test vectors hai chiều]
    H --> I{Tất cả kiểm thử đạt?}
    I -- Không --> J[Phân tích mismatch alg/key/encoding/parameters]
    J --> C
    I -- Có --> K[Issuer chuyển sang ký bằng key mới]
    K --> L[Giữ key cũ trong cửa sổ tương thích có giới hạn]
    L --> M[Theo dõi kid, alg và lỗi xác minh]
    M --> N[Token cũ hết hạn hoặc bị thu hồi]
    N --> O[Ngừng thuật toán/key cũ và hoàn tất di trú]
~~~

## 22. Nguyên tắc cần ghi nhớ

1. alg của JWS là thuật toán chữ ký/MAC; alg của JWE là thuật toán quản lý CEK; enc của JWE là thuật toán mã hóa nội dung.
2. Chọn thuật toán đồng thời với họ khóa, curve, kích thước khóa và định dạng chữ ký.
3. HS* dùng oct shared secret; RS*/PS* dùng RSA; ES* dùng EC P-256/P-384/P-521; Ed25519/Ed448 dùng OKP tương ứng.
4. X25519/X448 phục vụ key agreement, không phải khóa ký EdDSA.
5. RFC 9864 đã deprecated JOSE identifier polymorphic EdDSA; khi triển khai mới, đánh giá identifier cụ thể Ed25519/Ed448 và khả năng hỗ trợ của các bên.
6. ECDSA JWS dùng raw R || S có độ dài cố định, không phải DER SEQUENCE.
7. RSA-PSS phải khớp hash, MGF1 và salt length do JOSE quy định.
8. JWK use, key_ops, alg và kid cần nhất quán với allowlist; metadata không thay thế kiểm tra mật mã.
9. Không công bố private JWK hoặc secret đối xứng trong public JWKS.
10. Một khóa chỉ nên được dùng cho một thuật toán và mục đích; không tái sử dụng key material khi di trú.
11. Không tự động thử nhiều thuật toán hoặc fallback khi xác minh thất bại.
12. Di trú cần cửa sổ tương thích có giới hạn, test vectors liên thông và thời điểm loại bỏ khóa cũ.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS và chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): cấu trúc JWE, alg, enc và CEK.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWKS, kty, use, key_ops, alg và kid.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JWS/JWE và ánh xạ thuật toán với key type.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): tạo thumbprint để nhận diện public key đã chuẩn hóa.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): OKP, Ed25519/Ed448 và X25519/X448 trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, key binding, algorithm confusion và thực hành triển khai.
- [RFC 9864 — Fully-Specified Algorithms for JOSE and COSE](https://www.rfc-editor.org/rfc/rfc9864): identifier đầy đủ Ed25519/Ed448 và trạng thái deprecated của identifier polymorphic.
- [IANA JOSE Algorithms Registry](https://www.iana.org/assignments/jose): trạng thái và yêu cầu triển khai hiện hành của các thuật toán JOSE.

**Kết luận:** Liên thông JWT phụ thuộc vào việc hai hệ thống thống nhất đồng thời JOSE algorithm, họ khóa, curve, tham số mật mã, cách tuần tự hóa và hợp đồng token. Hãy lập ma trận trước khi tích hợp, ràng buộc mỗi khóa với một thuật toán, kiểm thử bằng test vectors độc lập và di trú qua một cửa sổ tương thích có giới hạn.
