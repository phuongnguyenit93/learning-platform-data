# Tham số khóa công khai, khóa riêng và khóa đối xứng trong JWK

JSON Web Key (JWK) là định dạng JSON chuẩn hóa để biểu diễn vật liệu khóa mật mã và một số metadata liên quan. Trong hệ thống **Security - JSON Web Token (JWT)**, JWK giúp bên phát hành và bên xác minh trao đổi khóa theo cách độc lập với ngôn ngữ lập trình, nền tảng hoặc framework. Để sử dụng an toàn, cần hiểu rõ từng kiểu khóa có những tham số nào, tham số nào được công bố, tham số nào phải giữ bí mật và cách biểu diễn các giá trị nhị phân.

Bài này thuộc chương **Khóa và JWKS** của module **SECURITY_TOKEN_SECURITY_JWT**. Nội dung tập trung vào cấu trúc vật liệu khóa trong JWK gồm RSA, EC, OKP và khóa đối xứng `oct`, đồng thời làm rõ sự khác nhau giữa JWK công khai, JWK riêng và dữ liệu khóa được phân phối qua JWKS. Phạm vi áp dụng cho bảo mật JWT nói chung, không phụ thuộc Java hay Spring.

## 1. JWK biểu diễn vật liệu khóa như thế nào?

Một JWK là một đối tượng JSON. Trường `kty` xác định họ khóa; các trường còn lại phụ thuộc vào họ đó.

| Họ khóa (`kty`) | Dạng khóa | Tham số công khai điển hình | Tham số bí mật điển hình |
| --- | --- | --- | --- |
| `RSA` | Cặp khóa RSA | `n`, `e` | `d`, `p`, `q`, `dp`, `dq`, `qi`, `oth` |
| `EC` | Cặp khóa đường cong elliptic | `crv`, `x`, `y` | `d` |
| `OKP` | Cặp khóa dạng octet key pair | `crv`, `x` | `d` |
| `oct` | Khóa đối xứng | Không có phần public riêng | `k` |

Các member `kty`, `n`, `e`, `crv`, `x`, `y`, `d`, `k` mô tả **vật liệu khóa**. Các member như `kid`, `use`, `key_ops`, `alg` mô tả định danh hoặc ý định sử dụng. Hai nhóm này có liên quan nhưng không thay thế nhau: khai báo `use: "sig"` không biến một khóa mã hóa thành khóa ký, và `alg: "RS256"` không thể sửa một bộ tham số RSA không hợp lệ.

Một JWK có thể chứa cả phần public và private của cùng một cặp khóa. Ví dụ, private JWK RSA thường chứa `n`, `e` cùng `d` và có thể có các tham số CRT. Khi xuất bản public JWK, chỉ giữ lại các thành phần public cần thiết.

## 2. Quy tắc mã hóa giá trị trong JWK

Các giá trị khóa trong JWK không được đưa vào JSON dưới dạng số thập phân tùy ý hay chuỗi văn bản tùy tiện. JOSE sử dụng **Base64url** để biểu diễn các octet (byte).

Base64url dùng bảng ký tự URL-safe:

- Chữ cái `A-Z`, `a-z`, chữ số `0-9`.
- Hai ký tự thay thế là `-` và `_`.
- Trong biểu diễn JWK chuẩn, không thêm dấu đệm `=` ở cuối.

Ví dụ `AQAB` là Base64url của dãy byte `01 00 01`, thường dùng để biểu diễn số mũ RSA 65537. Đây là ví dụ về cách mã hóa một giá trị, không phải một khóa RSA hoàn chỉnh.

### 2.1. Số nguyên không dấu và chuỗi byte

Không phải mọi tham số JWK đều có cùng quy tắc biểu diễn:

| Dạng dữ liệu | Quy tắc cần nhớ | Ví dụ áp dụng |
| --- | --- | --- |
| `Base64urlUInt` | Số nguyên không dấu được chuyển thành octet theo thứ tự big-endian, bỏ các octet `00` ở đầu theo biểu diễn tối thiểu, rồi mã hóa Base64url. | Các thành phần số nguyên RSA như `n`, `e`, `d`, `p`, `q`, `dp`, `dq`, `qi` và các giá trị `r`, `d`, `t` trong `oth`. |
| Octet string có độ dài xác định | Mã hóa đúng dãy byte theo thứ tự được định nghĩa; độ dài là một phần của biểu diễn và có thể cần giữ byte `00` ở đầu. | Tọa độ EC `x`, `y`; public key OKP `x`; khóa đối xứng `k`. |

Vì vậy, không được áp dụng quy tắc bỏ byte `00` ở đầu cho mọi trường. Với tọa độ EC, độ dài phải tương ứng đầy đủ với kích thước tọa độ của đường cong. Với khóa đối xứng, từng byte là một phần của bí mật và không được tự ý rút gọn.

### 2.2. Tránh mã hóa hai lần

Giả sử hệ thống sinh 32 byte ngẫu nhiên làm HMAC secret. JWK `k` phải là Base64url của **32 byte đó**. Nếu một hệ thống đã có chuỗi Base64url biểu diễn 32 byte mà lại mã hóa chuỗi ký tự ấy thêm lần nữa, kết quả sẽ là một khóa khác với khóa dự định.

Tương tự, không lấy một mật khẩu hoặc chuỗi cấu hình dễ đoán rồi xem chuỗi UTF-8 đó là khóa mật mã đủ mạnh. Vật liệu khóa phải được sinh hoặc dẫn xuất theo cơ chế mật mã phù hợp với thuật toán và chính sách.

## 3. Khóa RSA — `n`, `e` và các tham số private

Với `kty: "RSA"`, JWK mô tả một khóa RSA. Public key cần mô-đun và số mũ công khai; private key có thêm số mũ bí mật và có thể có các thành phần phục vụ phép tính CRT.

### 3.1. Các tham số RSA

| Member | Tên | Ý nghĩa | Công khai hay bí mật? |
| --- | --- | --- | --- |
| `n` | Modulus | Tích của các thừa số nguyên tố RSA; là thành phần chính của public key. | Công khai |
| `e` | Public exponent | Số mũ công khai dùng cùng `n`. Giá trị phổ biến là 65537. | Công khai |
| `d` | Private exponent | Số mũ riêng tương ứng với `n` và `e`; cần cho thao tác ký hoặc giải mã phù hợp. | Bí mật |
| `p` | Prime factor 1 | Một thừa số nguyên tố của `n`. | Bí mật |
| `q` | Prime factor 2 | Thừa số nguyên tố còn lại của RSA hai thừa số. | Bí mật |
| `dp` | First factor CRT exponent | Thành phần số mũ dùng trong tối ưu CRT. | Bí mật |
| `dq` | Second factor CRT exponent | Thành phần số mũ dùng trong tối ưu CRT. | Bí mật |
| `qi` | First CRT coefficient | Hệ số CRT liên quan đến `q` và `p`. | Bí mật |
| `oth` | Other primes info | Thông tin các thừa số bổ sung khi dùng RSA nhiều hơn hai thừa số nguyên tố. | Bí mật |

`n` và `e` là đủ để biểu diễn public key RSA. Không cần biết `d`, `p`, `q` để xác minh chữ ký RSA. Ngược lại, việc có `n` và `e` không cho phép bên nhận tạo chữ ký nếu không có private key.

Khi JWK biểu diễn **private RSA key**, member `d` phải có. Các tham số CRT như `p`, `q`, `dp`, `dq`, `qi` có thể được đưa vào để hỗ trợ phép tính hiệu quả; nếu có, chúng phải nhất quán với cùng một khóa RSA. Không coi việc chỉ có một vài trường CRT rời rạc là một private key hoàn chỉnh.

### 3.2. Ví dụ RSA public JWK

~~~json
{
  "kty": "RSA",
  "kid": "issuer-rsa-public-01",
  "use": "sig",
  "alg": "RS256",
  "n": "<BASE64URL_RSA_MODULUS>",
  "e": "AQAB"
}
~~~

Đây là ví dụ cấu trúc. `n` là placeholder, không phải modulus thật. JWK này chỉ biểu diễn public key, có thể được phân phối trong JWKS để các bên xác minh token ký bằng private key tương ứng.

### 3.3. Ví dụ RSA private JWK

~~~json
{
  "kty": "RSA",
  "kid": "issuer-rsa-private-01",
  "use": "sig",
  "alg": "RS256",
  "n": "<BASE64URL_RSA_MODULUS>",
  "e": "AQAB",
  "d": "<BASE64URL_PRIVATE_EXPONENT>",
  "p": "<BASE64URL_PRIME_P>",
  "q": "<BASE64URL_PRIME_Q>",
  "dp": "<BASE64URL_CRT_EXPONENT_P>",
  "dq": "<BASE64URL_CRT_EXPONENT_Q>",
  "qi": "<BASE64URL_CRT_COEFFICIENT>"
}
~~~

Ví dụ này minh họa các trường private và **không chứa khóa dùng được**. Tùy dạng khóa RSA và cách biểu diễn, các tham số CRT có thể được cung cấp để tối ưu phép tính. Với RSA nhiều hơn hai thừa số nguyên tố, `oth` chứa các đối tượng thông tin thừa số bổ sung; mỗi đối tượng dùng các member `r`, `d`, `t` theo định nghĩa JWA. Phần lớn triển khai thông thường dùng RSA hai thừa số nên không có `oth`.

**Quy tắc bảo mật:** private JWK RSA phải được bảo vệ như private key. Chỉ xóa `d` mà vẫn để lộ `p`, `q`, `dp`, `dq` hoặc `qi` cũng làm lộ thông tin private và có thể phá vỡ an toàn của khóa. Khi tạo public JWK, chỉ giữ `kty`, `n`, `e` và metadata công khai phù hợp.

### 3.4. Kiểm tra RSA key

Khi nhập hoặc tiêu thụ RSA JWK, cần kiểm tra:

1. `kty` đúng là `RSA`; các trường bắt buộc cho public key là `n` và `e`.
2. `n` và `e` giải mã Base64url thành biểu diễn số nguyên hợp lệ; không có giá trị rỗng hoặc biểu diễn không hợp lệ.
3. Kích thước modulus phù hợp chính sách mật mã. Với chữ ký RSA hiện đại theo JWA, không dùng modulus yếu; mức tối thiểu 2048 bit thường được yêu cầu.
4. `e` hợp lệ theo yêu cầu của thư viện và chính sách; không tự giả định mọi giá trị đều an toàn.
5. Nếu có private material, các tham số phải nhất quán về mặt toán học. Không tự ghép `d` từ một khóa với `n`/`e` của khóa khác.
6. Thuật toán được phép phải tương thích với khóa và policy của verifier. RSA không có nghĩa là tự động chấp nhận mọi thuật toán RSA.

## 4. Khóa EC — `crv`, `x`, `y` và `d`

Với `kty: "EC"`, JWK biểu diễn khóa trên một đường cong elliptic được hỗ trợ. Public key là một điểm trên đường cong; private key là một giá trị vô hướng tương ứng.

| Member | Ý nghĩa | Công khai hay bí mật? |
| --- | --- | --- |
| `crv` | Tên đường cong, ví dụ `P-256`, `P-384`, `P-521`. | Công khai |
| `x` | Tọa độ X của public point. | Công khai |
| `y` | Tọa độ Y của public point. | Công khai |
| `d` | Giá trị private scalar của khóa EC. | Bí mật |

Với private EC JWK, `d` là thành phần private cần có; `x` và `y` vẫn biểu diễn public point tương ứng. Các byte của tọa độ phải giữ độ dài đầy đủ theo curve, còn private scalar được mã hóa theo quy tắc octet của SEC1/JWA.

### 4.1. Ví dụ EC public JWK

~~~json
{
  "kty": "EC",
  "kid": "issuer-ec-p256-public-01",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>"
}
~~~

`crv` xác định đường cong. `x` và `y` cùng xác định public point. Với `ES256`, khóa thường dùng đường cong `P-256`; với `ES384`, dùng `P-384`; với `ES512`, dùng `P-521` theo các định nghĩa thuật toán JOSE.

Tọa độ được mã hóa thành octet string có độ dài đầy đủ theo kích thước của đường cong. Ví dụ, `P-256` có tọa độ dài 32 byte; `P-384` là 48 byte; `P-521` là 66 byte. Không được bỏ các byte `00` đầu tọa độ chỉ vì muốn chuỗi ngắn hơn.

### 4.2. Ví dụ EC private JWK

~~~json
{
  "kty": "EC",
  "kid": "issuer-ec-p256-private-01",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>",
  "d": "<BASE64URL_EC_PRIVATE_SCALAR>"
}
~~~

Private JWK chứa `d` cùng public point `x`, `y`. Các thành phần này phải thuộc cùng một cặp khóa: public point phải tương ứng với private scalar trên đúng đường cong. Nếu chỉ công bố public JWK, loại bỏ `d`.

### 4.3. Kiểm tra EC key

- Chỉ chấp nhận curve có trong danh sách hỗ trợ và được policy cho phép.
- `x` và `y` phải đúng độ dài, giải mã hợp lệ và tạo thành một điểm hợp lệ trên đường cong đã khai báo.
- Từ chối điểm không hợp lệ hoặc điểm ở vô cực; không chỉ kiểm tra rằng JSON có hai chuỗi `x`, `y`.
- `d` phải là private scalar hợp lệ trong miền giá trị của đường cong; public point tính từ `d` phải khớp với `x`, `y`.
- Kiểm tra cặp `crv` và `alg`. Chẳng hạn `P-384` không thể được dùng như khóa `ES256` chỉ vì cả hai đều thuộc `EC`.

EC có thể được sử dụng cho chữ ký như ECDSA hoặc cho thỏa thuận khóa như ECDH tùy đường cong, thuật toán và profile. Không suy ra mục đích từ `kty: "EC"` đơn lẻ.

## 5. Khóa OKP — `crv`, `x` và `d`

`OKP` (*Octet Key Pair*) biểu diễn một số loại khóa đường cong có vật liệu khóa dạng octet. Dù có chữ “curve”, dạng JWK này khác `EC`: public key thường được biểu diễn bằng một trường `x`, không có cặp tọa độ `x`/`y`.

| Member | Ý nghĩa | Công khai hay bí mật? |
| --- | --- | --- |
| `crv` | Loại đường cong/nhóm, ví dụ `Ed25519`, `Ed448`, `X25519`, `X448`. | Công khai |
| `x` | Dãy byte của public key. | Công khai |
| `d` | Dãy byte của private key. | Bí mật |

Với private OKP JWK, `d` chứa private key theo định dạng octet được quy định cho curve; `x` là public key tương ứng. Không áp dụng cách diễn giải `x`/`y` của EC cho OKP.

### 5.1. Ví dụ Ed25519 public JWK

~~~json
{
  "kty": "OKP",
  "kid": "issuer-ed25519-public-01",
  "use": "sig",
  "alg": "EdDSA",
  "crv": "Ed25519",
  "x": "<BASE64URL_ED25519_PUBLIC_KEY>"
}
~~~

`Ed25519` là khóa chữ ký; trong JOSE, thuật toán `EdDSA` được dùng cho các đường cong Edwards được hỗ trợ. `X25519` và `X448` phục vụ thỏa thuận khóa, không phải thay thế trực tiếp cho khóa chữ ký Ed25519.

### 5.2. Ví dụ OKP private JWK

~~~json
{
  "kty": "OKP",
  "kid": "issuer-ed25519-private-01",
  "use": "sig",
  "alg": "EdDSA",
  "crv": "Ed25519",
  "x": "<BASE64URL_ED25519_PUBLIC_KEY>",
  "d": "<BASE64URL_ED25519_PRIVATE_KEY>"
}
~~~

Các giá trị `x` và `d` là placeholder. Không lấy một chuỗi seed hoặc private key ở dạng văn bản bất kỳ rồi gán vào `d`; phải tuân theo định dạng octet và quy tắc chuyển đổi của thuật toán.

### 5.3. Kiểm tra OKP key

1. `kty` phải là `OKP` và `crv` phải thuộc tập curve được hỗ trợ.
2. `x` phải có đúng kích thước và cấu trúc byte theo curve.
3. Nếu có `d`, xác minh private material hợp lệ và public key tương ứng phải khớp với `x`.
4. Không dùng `Ed25519` thay cho `X25519`, hoặc ngược lại, chỉ vì cả hai có tên gần giống nhau và cùng họ 25519.
5. Kiểm tra thuật toán: `EdDSA` phục vụ chữ ký; các curve XDH phục vụ thỏa thuận khóa theo cơ chế phù hợp.

## 6. Khóa đối xứng — `kty: "oct"` và member `k`

Khác RSA, EC và OKP, khóa đối xứng chỉ có **một bí mật dùng chung**. Trong JWK, loại khóa này có `kty: "oct"` và member `k` chứa các byte của khóa sau khi mã hóa Base64url.

~~~json
{
  "kty": "oct",
  "kid": "internal-hmac-01",
  "use": "sig",
  "alg": "HS256",
  "k": "<BASE64URL_RANDOM_SECRET>"
}
~~~

`k` không phải public key. Bất kỳ bên nào lấy được giá trị này đều có thể tạo MAC hợp lệ và xác minh MAC. Do đó:

- Không công bố JWK `oct` có chứa `k` tại endpoint JWKS công khai.
- Không đưa `k` vào mã nguồn, log, telemetry, ticket, file cấu hình được chia sẻ hoặc artifact build.
- Phân phối secret qua hệ thống quản lý bí mật có kiểm soát truy cập và kênh bảo mật.
- Sinh secret bằng CSPRNG; không dùng mật khẩu, tên ứng dụng, chuỗi dễ nhớ hay dữ liệu có thể dự đoán.
- Hạn chế số bên được cấp secret. Mỗi verifier có secret cũng có khả năng ký, nên chia sẻ HMAC secret rộng làm tăng phạm vi tin cậy.

### 6.1. Kích thước khóa HMAC

JWA yêu cầu kích thước khóa HMAC tối thiểu bằng kích thước đầu ra của hàm băm tương ứng:

| Thuật toán | Hàm băm | Kích thước khóa tối thiểu |
| --- | --- | --- |
| `HS256` | SHA-256 | 256 bit (32 byte) |
| `HS384` | SHA-384 | 384 bit (48 byte) |
| `HS512` | SHA-512 | 512 bit (64 byte) |

Độ dài chuỗi Base64url nhìn thấy không phải số bit của khóa. Phải giải mã `k` để kiểm tra số byte thực tế. Không dùng chuỗi ký tự dài nhưng entropy thấp làm secret.

### 6.2. Khóa đối xứng cho mã hóa

JWK `oct` cũng có thể biểu diễn khóa cho thuật toán mã hóa hoặc quản lý khóa, ví dụ một số thuật toán AES. Kích thước cần khớp chính xác thuật toán: chẳng hạn các thuật toán AES-128, AES-192, AES-256 đòi hỏi khóa tương ứng 128, 192, 256 bit. Không lấy yêu cầu độ dài của HMAC áp dụng cho AES hoặc ngược lại.

## 7. Bảng so sánh public material và private material

| `kty` | Phần public cần để xác minh/nhận diện khóa | Phần private phải bảo vệ | Có thể công bố trong JWKS công khai? |
| --- | --- | --- | --- |
| `RSA` | `n`, `e` | `d`, `p`, `q`, `dp`, `dq`, `qi`, `oth` | Có, chỉ với public material |
| `EC` | `crv`, `x`, `y` | `d` | Có, chỉ với public material |
| `OKP` | `crv`, `x` | `d` | Có, chỉ với public material |
| `oct` | Không có public counterpart | `k` | Không công bố secret |

### 7.1. Vì sao public key có thể phân phối rộng?

Với chữ ký bất đối xứng, private key tạo chữ ký còn public key xác minh chữ ký. Bên xác minh có thể biết public key mà không có khả năng tính ra private key một cách khả thi nếu thuật toán và kích thước khóa được chọn đúng. Điều này cho phép nhiều API xác minh token mà không cần giữ bí mật có khả năng phát hành token.

### 7.2. Vì sao khóa đối xứng cần ranh giới tin cậy chặt hơn?

Với HMAC, cùng một secret được dùng để tạo và kiểm tra MAC. Mỗi hệ thống cần xác minh đều phải có bí mật đó, do vậy cũng có khả năng ký. Nếu một verifier bị xâm nhập, attacker có thể lấy secret để giả mạo token trong phạm vi issuer và thuật toán liên quan. Đây là khác biệt kiến trúc quan trọng giữa HMAC và chữ ký bất đối xứng.

### 7.3. Public JWK không phải lúc nào cũng đồng nghĩa “an toàn để tin”

Public key không phải bí mật, nhưng nguồn gốc của nó vẫn cần được xác thực. Attacker có thể tạo cặp khóa riêng và công khai public key của mình. Nếu verifier lấy public key đó từ nguồn không đáng tin, token giả có thể được xác minh thành công về mặt mật mã.

Vì vậy, verifier phải lấy JWK từ JWKS/metadata của issuer đã được cấu hình tin cậy, xác thực HTTPS và kiểm tra chính sách issuer. `kid`, `alg`, `x5c` hoặc một URL trong JWT không tự tạo ra niềm tin.

## 8. JWK công khai, private JWK và JWKS

### 8.1. Public JWK

Public JWK chỉ chứa tham số công khai cần cho thao tác của bên nhận. Ví dụ:

~~~json
{
  "kty": "EC",
  "kid": "signing-p256-2026-04",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>"
}
~~~

Đây là dạng phù hợp để đưa vào JWKS phục vụ xác minh chữ ký. Không có `d`.

### 8.2. Private JWK

Private JWK chứa cả phần public và private của khóa bất đối xứng, hoặc chứa secret `k` của khóa đối xứng. JSON JWK **không tự mã hóa hay bảo vệ** các member bí mật. Việc chuyển private JWK qua mạng, ghi vào file hoặc lưu trong database phải có cơ chế bảo vệ riêng.

Nếu hệ thống dùng HSM/KMS hoặc dịch vụ quản lý khóa, private key có thể không xuất được dưới dạng JWK. Ứng dụng chỉ được cấp quyền gọi thao tác ký; public JWK có thể được xuất để các bên khác xác minh. Không nên buộc phải xuất private key chỉ để đáp ứng định dạng trao đổi.

### 8.3. JWKS công khai

JWKS là một JSON object chứa mảng `keys`. Ví dụ:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sign-rsa-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "sign-ec-2026-02",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<BASE64URL_X_COORDINATE>",
      "y": "<BASE64URL_Y_COORDINATE>"
    }
  ]
}
~~~

JWKS công khai có thể chứa nhiều public key để hỗ trợ rotation, nhiều thuật toán hoặc nhiều nhóm token. Khi phân phối JWKS:

- Chỉ đưa public material của khóa bất đối xứng.
- Không đưa `d`, `p`, `q`, `dp`, `dq`, `qi`, `oth` hoặc `k` bí mật.
- Không công bố JWK `oct` chứa secret.
- Phân phối qua HTTPS và gắn endpoint với issuer đã được cấu hình.
- Có thể giữ public key cũ trong giai đoạn chuyển tiếp để xác minh token còn hiệu lực, nhưng phải quản lý thời điểm ngừng tin cậy.
- Dùng cache/TTL và cơ chế làm mới hợp lý; khi khóa bị lộ phải có đường thu hồi khẩn cấp cho verifier.

## 9. Quan hệ giữa tham số vật liệu khóa và thuật toán

Một kiểu khóa có thể hỗ trợ nhiều thuật toán, nhưng không phải mọi thuật toán đều tương thích với mọi tham số.

| Thuật toán | Kiểu khóa | Các tham số cần chú ý |
| --- | --- | --- |
| `HS256`, `HS384`, `HS512` | `oct` | `k` có đủ độ dài và entropy theo yêu cầu. |
| `RS256`, `RS384`, `RS512` | `RSA` | `n`, `e`; private key tương ứng để ký. |
| `PS256`, `PS384`, `PS512` | `RSA` | `n`, `e`; kiểm tra policy cho RSA-PSS. |
| `ES256` | `EC` | `crv: "P-256"`, `x`, `y`. |
| `ES384` | `EC` | `crv: "P-384"`, `x`, `y`. |
| `ES512` | `EC` | `crv: "P-521"`, `x`, `y`. |
| `EdDSA` | `OKP` | Curve Edwards được hỗ trợ, ví dụ `Ed25519` hoặc `Ed448`. |

Các thuật toán JWE có thể dùng khóa theo vai trò khác như key wrapping, key agreement hoặc content encryption. Không dùng bảng JWS trên để suy ra cấu hình cho JWE.

Verifier phải có allowlist thuật toán từ cấu hình tin cậy. Không để `alg` trong JWT tự quyết định cách diễn giải cùng một chuỗi byte khóa. Một public RSA key không được biến thành HMAC secret chỉ vì token khai báo `HS256`; một khóa EC trên `P-384` không tự phù hợp với `ES256`.

## 10. Nguồn khóa và chuyển đổi từ định dạng khác

Trong thực tế, khóa có thể được sinh trong HSM/KMS, được nhập từ hệ thống quản lý khóa, hoặc được chuyển đổi từ định dạng PEM/DER. JWK là **định dạng biểu diễn**, không phải thuật toán sinh khóa và cũng không phải cơ chế bảo vệ private key.

Khi chuyển đổi:

1. Xác định chính xác loại khóa và thuật toán nguồn.
2. Dùng thư viện mật mã/JOSE đáng tin để parse PEM/DER hoặc giao diện KMS.
3. Chuyển từng thành phần theo quy tắc của `kty`; không tự cắt chuỗi PEM hoặc chuyển byte bằng thao tác chuỗi văn bản.
4. Xác minh public parameters tạo ra giống public key nguồn; nếu có private material, kiểm tra cặp khóa.
5. Xóa hoặc bảo vệ bản trung gian chứa private material sau chuyển đổi.
6. Nếu chỉ cần xác minh, chỉ xuất public JWK; không chuyển private key ra khỏi HSM/KMS.

Đối với khóa không thể export, dịch vụ ký có thể giữ khóa trong HSM/KMS và chỉ cung cấp public JWK. Bên xác minh không cần private JWK để kiểm tra chữ ký.

## 11. Kiểm tra tính hợp lệ của JWK trước khi sử dụng

Không nên chỉ parse JSON thành công rồi xem khóa là hợp lệ. Quy trình kiểm tra cần có nhiều lớp:

### Lớp 1 — Cấu trúc và kiểu dữ liệu

- JSON hợp lệ, không có member trùng tên gây khác biệt giữa parser.
- `kty` tồn tại và thuộc loại được hỗ trợ.
- Các member bắt buộc của kiểu khóa có mặt và có kiểu dữ liệu đúng.
- Chuỗi Base64url được giải mã đúng, không có ký tự lạ hoặc dữ liệu rỗng bất thường.

### Lớp 2 — Tham số theo từng họ khóa

- **RSA:** `n`, `e` hợp lệ; kích thước modulus đáp ứng chính sách; private parameters nhất quán nếu có.
- **EC:** `crv` được phép; tọa độ đúng độ dài và tạo thành public point hợp lệ; private scalar tương ứng với public point.
- **OKP:** `crv` đúng; `x`/`d` có kích thước và định dạng đúng; cặp public/private khớp nhau.
- **oct:** `k` có độ dài và entropy đáp ứng thuật toán; chỉ được xử lý trong vùng bí mật.

### Lớp 3 — Chính sách sử dụng

- `use`, `key_ops`, `alg` nếu xuất hiện phải nhất quán và tương thích.
- Thuật toán nằm trong allowlist; kiểu khóa và curve phù hợp.
- Khóa đúng mục đích: ký/xác minh hay mã hóa/thỏa thuận khóa.
- Không sử dụng khóa hết hạn tin cậy, bị thu hồi hoặc thuộc môi trường/issuer khác.

### Lớp 4 — Nguồn gốc và vòng đời

- JWK đến từ issuer/JWKS đã được cấu hình tin cậy.
- Endpoint được bảo vệ bằng HTTPS và không bị thay đổi ngoài quy trình.
- `kid` được tìm trong phạm vi issuer tương ứng; không trùng lặp gây mơ hồ.
- Cache được cập nhật theo chính sách rotation; có thể chặn khóa khẩn cấp.

Một khóa có tham số toán học hợp lệ vẫn có thể không được tin cậy nếu nguồn gốc không đáng tin. Ngược lại, khóa từ endpoint đúng cũng cần kiểm tra định dạng, thuật toán và trạng thái trước khi dùng.

## 12. Lưu trữ và bảo vệ private material

Private key và secret đối xứng phải được bảo vệ xuyên suốt quá trình sinh, lưu trữ, sử dụng, sao lưu, luân chuyển và hủy.

- Ưu tiên HSM/KMS hoặc secret manager có kiểm soát truy cập. Hạn chế xuất private material ở dạng thô.
- Phân quyền theo nguyên tắc tối thiểu: dịch vụ xác minh bất đối xứng chỉ cần public key; dịch vụ ký chỉ được quyền dùng khóa cần thiết.
- Mã hóa dữ liệu lưu trữ và bản sao lưu; kiểm soát ai có thể khôi phục hoặc export khóa.
- Không ghi private JWK, `d`, `p`, `q`, `k` hoặc token nhạy cảm vào log.
- Kiểm toán thao tác tạo, export, rotate, cấp quyền ký, thu hồi và hủy.
- Xác định cách xử lý bản sao, snapshot, backup và môi trường dự phòng khi hủy khóa.
- Khi private key bị lộ, thu hồi khả năng ký và ngừng tin cậy public key tương ứng ở các verifier; chỉ xóa file private key khỏi một máy là chưa đủ.

**Private JWK không phải một container được mã hóa.** Nếu lưu JSON có các member bí mật trên đĩa hoặc truyền qua mạng, phải bảo vệ bằng cơ chế bên ngoài như mã hóa, kiểm soát truy cập và kênh truyền an toàn.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao nguy hiểm hoặc sai | Cách xử lý |
| --- | --- | --- |
| Đưa RSA `d` hoặc tham số CRT vào JWKS công khai | Làm lộ private key, cho phép tạo chữ ký hoặc giải mã trái phép. | Chỉ xuất `n`, `e` và metadata public phù hợp. |
| Đưa EC `d` vào public JWK | Lộ private scalar của cặp khóa EC. | Loại bỏ `d` khỏi public JWK. |
| Đưa OKP `d` vào JWKS | Lộ private key EdDSA/XDH. | Chỉ công bố `crv`, `x` và metadata public. |
| Đưa `oct.k` lên endpoint công khai | Bên nhận có thể tạo MAC hợp lệ. | Phân phối secret qua secret manager/kênh bảo mật riêng. |
| Coi Base64url là mã hóa bảo mật | Base64url chỉ là biểu diễn, ai cũng có thể giải mã. | Bảo vệ private material bằng cơ chế mã hóa và phân quyền. |
| Mã hóa chuỗi Base64url thêm một lần | Tạo vật liệu khóa khác với byte ban đầu. | Base64url đúng một lần từ octet gốc. |
| Cắt byte `00` đầu của EC coordinate | Làm sai độ dài và thay đổi biểu diễn điểm. | Giữ độ dài cố định theo curve. |
| Dùng `x` của OKP như tọa độ EC | Nhầm hai cấu trúc JWK khác nhau. | Diễn giải theo `kty` và `crv`. |
| Dùng `Ed25519` thay `X25519` | Nhầm khóa chữ ký với khóa thỏa thuận. | Kiểm tra đúng curve và mục đích thuật toán. |
| Dùng một `kid` cho khóa mới và cũ | Cache/consumer có thể chọn nhầm hoặc dữ liệu trở nên mơ hồ. | Gán `kid` mới cho vật liệu khóa mới. |
| Tin public key chỉ vì nó nằm trong JWK | JWK không chứng minh nguồn gốc khóa. | Gắn với issuer và JWKS đã tin cậy. |
| Dùng RSA public key như HMAC secret | Tạo lỗ hổng algorithm/key confusion. | Allowlist thuật toán và ràng buộc `alg` với `kty`. |

## 14. Ví dụ tổng hợp: phát hành JWT và xác minh

Giả sử một issuer phát hành access token bằng `RS256`.

**Phía issuer:**

1. Sinh cặp khóa RSA theo chính sách.
2. Lưu private material (`d` và các tham số private liên quan) trong HSM/KMS hoặc kho khóa được bảo vệ.
3. Dùng private key để ký JWT.
4. Công bố public JWK chỉ chứa `kty`, `n`, `e`, `kid` và metadata cần thiết.

**JWKS công khai:**

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "access-signing-2026-04",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

**JWT header minh họa:**

~~~json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "access-signing-2026-04"
}
~~~

**Phía API xác minh:**

1. Chọn issuer từ cấu hình đã tin cậy và lấy JWKS tương ứng.
2. Tìm public JWK theo `kid` trong tập khóa của issuer đó.
3. Kiểm tra `kty=RSA`, tham số `n`/`e`, mục đích và thuật toán được phép.
4. Xác minh chữ ký bằng public key.
5. Sau khi chữ ký hợp lệ, kiểm tra `iss`, `aud`, `exp`, `nbf`, loại token và quyền truy cập.

API không cần nhận `d`, `p`, `q` hoặc bất kỳ private parameter nào. Nếu một JWK public trong JWKS lại chứa các trường này, cần xem đó là sự cố công bố vật liệu bí mật.

## 15. Checklist khi thiết kế hoặc review JWK

**Cấu trúc khóa**

- [ ] `kty` được hỗ trợ và đúng với loại vật liệu khóa.
- [ ] Các member bắt buộc có mặt, đúng kiểu dữ liệu và giải mã Base64url hợp lệ.
- [ ] RSA có `n`/`e`; EC có `crv`/`x`/`y`; OKP có `crv`/`x`; `oct` có `k`.
- [ ] Tham số private tương ứng với public material và đúng cùng một cặp khóa.
- [ ] Kích thước khóa, curve và độ dài secret phù hợp chính sách.

**Công bố**

- [ ] Public JWKS chỉ chứa public material của khóa bất đối xứng.
- [ ] Không có RSA private parameters, EC/OKP `d` hoặc `oct.k` trong JWKS công khai.
- [ ] Private JWK được bảo vệ vì JSON không tự mã hóa nội dung.
- [ ] Secret đối xứng được phân phối riêng qua kênh quản lý bí mật.

**Sử dụng**

- [ ] `alg`, `use`, `key_ops` nhất quán với kiểu khóa và policy.
- [ ] `kid` duy nhất trong phạm vi issuer và được dùng để tra cứu đúng JWKS.
- [ ] Nguồn khóa đã được tin cậy; khóa chưa bị thu hồi.
- [ ] Có kế hoạch rotation, cache refresh, thu hồi khẩn cấp và hủy khóa.

## 16. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK/JWKS và các member chung.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): tham số khóa RSA, EC, oct và thuật toán JOSE.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): khóa OKP và thuật toán EdDSA/XDH trong JOSE.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cách sử dụng khóa trong chữ ký JWS.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành xác minh JWT an toàn và phòng tránh nhầm lẫn thuật toán.

**Ghi nhớ:** `RSA` công bố `n`/`e` và giữ bí mật các thành phần private; `EC` công bố `crv`/`x`/`y` và giữ `d`; `OKP` công bố `crv`/`x` và giữ `d`; `oct` giữ bí mật `k` vì không có public counterpart. Base64url chỉ biểu diễn byte, không bảo vệ bí mật. Chỉ phân phối public material qua nguồn JWKS đã được tin cậy và quản lý private material trong toàn bộ vòng đời khóa.
