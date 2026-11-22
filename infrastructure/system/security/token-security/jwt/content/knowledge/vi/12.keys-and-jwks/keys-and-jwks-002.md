# JWK và các thuộc tính `kty`, `kid`, `use`, `key_ops`, `alg`

Trong hệ sinh thái **Security - JSON Web Token (JWT)**, bên phát hành token cần một khóa để tạo chữ ký và bên nhận cần biết **khóa nào được phép dùng để xác minh**. Chuẩn **JSON Web Key (JWK)** mô tả khóa bằng JSON, giúp hệ thống khác ngôn ngữ và nền tảng trao đổi metadata về khóa một cách thống nhất. Khi nhiều JWK được gom trong một tập, chúng tạo thành **JSON Web Key Set (JWKS)**.

Bài này thuộc chương **Khóa và JWKS** của module `SECURITY_TOKEN_SECURITY_JWT`. Nội dung tập trung vào cách hiểu, sử dụng và kiểm tra các thuộc tính **`kty`, `kid`, `use`, `key_ops` và `alg`** trong JWT/JOSE, áp dụng cho hệ thống bảo mật nói chung, không phụ thuộc framework hay ngôn ngữ lập trình.

## 1. Kết quả cần nắm

Sau bài học, người đọc có thể:

1. Phân biệt **JWK**, **JWKS**, **JWT header** và **khóa thực sự được dùng trong phép toán mật mã**.
2. Giải thích năm thuộc tính trọng tâm, phân biệt trường nào mô tả kiểu khóa, định danh, mục đích, thao tác và thuật toán.
3. Đọc một JWK công khai, xác định được tham số nào có thể công bố và tham số nào là bí mật.
4. Phát hiện cấu hình thiếu nhất quán, chẳng hạn `use=enc` nhưng `key_ops=["verify"]`, hoặc JWT yêu cầu `HS256` trong khi khóa được cấp là RSA.
5. Thiết kế cách chọn khóa an toàn từ JWKS, gắn việc chọn khóa với **issuer tin cậy** và chính sách xác minh.

## 2. JWK nằm ở đâu trong quy trình JWT?

Một JWT có chữ ký theo cơ chế JWS thường có ba phần mã hóa Base64url, ngăn cách bởi dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "issuer-a-rsa-2026-02"
}
~~~

Ở đây, `alg` và `kid` là **thông tin trong header do người gửi token cung cấp**, ban đầu phải xem là **chưa đáng tin**. Bên xác minh dùng chúng để tìm ứng viên khóa từ tập khóa đã được tin cậy và kiểm tra thuật toán được phép. Chỉ sau khi xác minh chữ ký và các điều kiện claims, token mới được chấp nhận.

Một **JWK công khai** mô tả ứng viên khóa tương ứng:

~~~json
{
  "kty": "RSA",
  "kid": "issuer-a-rsa-2026-02",
  "use": "sig",
  "alg": "RS256",
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

Đây là ví dụ **minh họa cấu trúc**, không phải RSA public key hợp lệ để đưa vào triển khai. `n` là mô-đun công khai của RSA, `e` là số mũ công khai. JWK này **không có** `d` hoặc tham số private RSA khác.

JWKS là một đối tượng bọc danh sách các JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "issuer-a-rsa-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "issuer-a-ec-2026-03",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<BASE64URL_X_COORDINATE>",
      "y": "<BASE64URL_Y_COORDINATE>"
    }
  ]
}
~~~

JWKS công bố được hai khóa để hỗ trợ nhiều thuật toán, nhiều nhóm token hoặc giai đoạn thay khóa. Các giá trị trong dấu `<...>` chỉ là placeholder, không chứa vật liệu khóa có thể sử dụng. Một JWKS **không tự chứng minh** khóa đáng tin; bên xác minh vẫn phải kiểm tra nơi cung cấp JWKS thuộc đúng issuer đã được cấu hình.

### JWK không đồng nghĩa với khóa công khai

JWK là **định dạng biểu diễn khóa**, có thể biểu diễn:

- Khóa RSA/EC/OKP **chỉ có phần public**: phù hợp để phân phối cho nhiều bên xác minh chữ ký.
- Khóa RSA/EC/OKP có **phần private**: chỉ dành cho môi trường bảo mật, không công bố qua endpoint JWKS công khai.
- Khóa đối xứng `oct` chứa **bí mật dùng chung**: chỉ truyền qua kênh quản lý bí mật được bảo vệ, không đưa lên JWKS công khai.

Nhầm lẫn “JWK là public key” dẫn đến một trong những lỗi nghiêm trọng nhất: xuất bản JWK chứa private key hoặc HMAC secret.

## 3. Bảng định vị năm thuộc tính trọng tâm

| Thuộc tính | Trả lời câu hỏi | Ví dụ | Bắt buộc trong JWK? | Vai trò |
| --- | --- | --- | --- | --- |
| **`kty`** | Khóa này thuộc loại nào? | `RSA`, `EC`, `OKP`, `oct` | **Có** | Xác định họ khóa, định dạng tham số và loại thao tác mật mã khả dụng. |
| **`kid`** | Đây là khóa nào trong tập khóa? | `issuer-a-rsa-2026-02` | Không | Hỗ trợ tìm/chọn khóa, nhất là khi một JWKS có nhiều khóa. |
| **`use`** | Khóa dự kiến phục vụ loại mục đích nào? | `sig`, `enc` | Không | Phân loại mức cao: chữ ký/MAC hoặc mã hóa. |
| **`key_ops`** | Khóa dự kiến được phép dùng cho thao tác nào? | `["verify"]` | Không | Liệt kê thao tác cụ thể, như ký, xác minh, giải mã hoặc dẫn xuất khóa. |
| **`alg`** | Khóa dự kiến được dùng với thuật toán nào? | `RS256`, `ES256` | Không | Gợi tả thuật toán cụ thể dự kiến cho khóa. |

**Điểm cần nhớ:** metadata trong JWK mô tả *ý định sử dụng* và khả năng tương thích. **Nó không tự cấp quyền**, không tạo ra ranh giới tin cậy và không thay thế cấu hình cho phép của ứng dụng. Không có một thuộc tính nào trong bảng, kể cả `kid` hay `alg`, tự bảo đảm chữ ký sẽ hợp lệ.

## 4. `kty` — Loại khóa và hình dạng tham số

`kty` (*Key Type*) là thuộc tính **bắt buộc**. Giá trị của nó quyết định một JWK có dạng tham số nào, đồng thời giúp hệ thống tránh dùng nhầm khóa cho họ thuật toán khác.

| `kty` | Mô tả | Tham số công khai thường thấy | Tham số bí mật cần bảo vệ | Ví dụ thuật toán liên quan |
| --- | --- | --- | --- | --- |
| `RSA` | Cặp khóa RSA | `n`, `e` | `d` và có thể có `p`, `q`, `dp`, `dq`, `qi` | `RS256`, `PS256` |
| `EC` | Cặp khóa elliptic curve | `crv`, `x`, `y` | `d` | `ES256` với `P-256` |
| `OKP` | Cặp khóa octet key pair, ví dụ Ed25519 | `crv`, `x` | `d` | `EdDSA` với Ed25519 (khi profile/thư viện hỗ trợ) |
| `oct` | Khóa đối xứng chứa octet ngẫu nhiên | Không có phần public tách riêng | `k` | `HS256`; các thuật toán mã hóa đối xứng thích hợp |

### 4.1. RSA

Ví dụ JWK public RSA:

~~~json
{
  "kty": "RSA",
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

`n` và `e` là các số nguyên không dấu được biểu diễn theo quy tắc Base64url của JOSE. Chữ ký `RS256` hoặc `PS256` có thể được xác minh bằng phần public, trong khi thao tác ký cần private key tương ứng. Không được đưa `d` hay các yếu tố CRT riêng vào dữ liệu công khai.

### 4.2. EC

Ví dụ public EC:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>"
}
~~~

`crv` xác định đường cong; `x`, `y` là tọa độ public point. Với `ES256`, cấu hình phổ biến là `P-256`. Không thể chỉ nhìn `kty=EC` mà chấp nhận mọi đường cong và mọi thuật toán: verifier phải ràng buộc cả `crv` và `alg` theo chính sách.

### 4.3. OKP

Ví dụ public Ed25519:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<BASE64URL_PUBLIC_KEY>"
}
~~~

`OKP` là họ khóa có định dạng khác EC; `x` biểu diễn public key, còn `d` là private material nếu có. Khi xác minh EdDSA với Ed25519, bên nhận phải kiểm tra đúng đường cong và profile hỗ trợ.

### 4.4. oct

Ví dụ đối tượng JWK **bí mật** chỉ để lưu trong kho riêng:

~~~json
{
  "kty": "oct",
  "kid": "internal-hmac-07",
  "use": "sig",
  "alg": "HS256",
  "k": "<BASE64URL_RANDOM_SECRET>"
}
~~~

`k` là **secret**. Khác với `n`/`e` của RSA, trường này không được phân phối công khai; bất kỳ ai lấy được `k` có thể tạo chữ ký HMAC hợp lệ trong phạm vi các hệ thống tin bí mật đó. Đoạn JSON chỉ minh họa và không chứa secret thật.

### 4.5. Không đủ khi chỉ khớp `kty`

Để nhận biết khóa phù hợp cho một phép toán, cần xác minh **đồng thời**:

~~~text
issuer đáng tin
    + loại khóa (kty)
    + tham số khóa hợp lệ (n/e hoặc crv/x/y hoặc x hoặc k)
    + mục đích và thao tác được phép (use/key_ops nếu có)
    + thuật toán cho phép (alg trong chính sách)
    + chính sách vòng đời / tin cậy của khóa
~~~

Ví dụ, cả `RS256` và `PS256` có thể dùng RSA nhưng đó là **hai thuật toán chữ ký khác nhau**; chỉ nhìn `kty=RSA` không đủ để quyết định cả hai đều được chấp nhận.

## 5. `kid` — Định danh để lựa chọn khóa

`kid` (*Key ID*) là một chuỗi định danh **không bắt buộc**, thường xuất hiện ở cả protected header của JWT và JWK trong tập khóa được công bố.

Ví dụ:

~~~text
JWT header:  {"alg":"RS256","kid":"sign-2026-q4"}
JWKS key A:  {"kty":"RSA","kid":"sign-2026-q3", ...}
JWKS key B:  {"kty":"RSA","kid":"sign-2026-q4", ...}

=> Chọn B làm ứng viên để xác minh, rồi tiếp tục kiểm tra.
~~~

`kid` giúp tránh phải thử mù nhiều khóa khi có nhiều public key. Tuy nhiên:

1. **`kid` không phải bằng chứng về danh tính hay sự tin cậy.** Attacker có thể tự đặt `kid` trong header token giả.
2. **Phạm vi tra cứu phải gắn với issuer đã tin cậy.** Hai issuer hoàn toàn có thể cùng dùng chuỗi `kid=key-1`; không được vì chuỗi bằng nhau mà lấy khóa từ issuer khác.
3. **Nên duy nhất trong mỗi JWKS/phạm vi issuer.** Tránh hai khóa đang tin cậy cùng `kid`; cấu hình đụng độ dễ gây chọn sai khóa hoặc khác biệt giữa thư viện.
4. **Không tái sử dụng `kid` cho vật liệu khóa khác.** Khi rotation, tạo khóa mới và `kid` mới để giảm nhầm lẫn cache, lịch sử và log.
5. **So khớp chính xác, có phân biệt hoa thường.** `sign-A` và `sign-a` là hai chuỗi khác nhau. Không tự ý chuẩn hóa, nối/loại tiền tố hoặc diễn giải `kid` thành đường dẫn.
6. **Không dùng `kid` làm đầu vào trực tiếp cho truy vấn, tên file hoặc URL.** Nếu nội bộ cần ánh xạ khóa, sử dụng map/cấu hình và cơ chế xử lý dữ liệu an toàn; chuỗi `kid` có thể đến từ token không đáng tin.

**Khi không có `kid`:** JWK vẫn có thể hợp lệ. Một hệ thống chỉ có một ứng viên khóa được cho phép có thể có chính sách xử lý không cần `kid`. Nhưng nếu nhiều khóa cùng đáp ứng, việc tự thử tất cả hoặc chọn khóa đầu tiên có thể gây sai khác khó kiểm soát. Thiết kế rõ hành vi từ chối/tra cứu theo chính sách.

**Khi gặp `kid` lạ:** không tải lại JWKS vô hạn cho mỗi token. Nếu hệ thống cho phép làm mới từ nguồn đã tin cậy thì phải giới hạn tần suất, có cache và hạn chế DoS. Không được dùng khóa hoặc URL do token tự khai báo để “chữa” lỗi thiếu `kid`.

### `kid` và JWK thumbprint có giống nhau không?

**Không bắt buộc.** `kid` là chuỗi định danh do nhà phát hành quản lý; chuẩn không quy định rằng nó phải là hàm băm của khóa. **JWK Thumbprint** theo RFC 7638 tạo dấu vân tay xác định từ tập thuộc tính bắt buộc của từng kiểu khóa sau khi chuẩn hóa biểu diễn (chẳng hạn `kty`, `n`, `e` với RSA); với khóa đối xứng, tập dữ liệu tính thumbprint có chứa giá trị bí mật `k`, nên không tùy tiện chia sẻ dữ liệu nguồn. Có thể thiết kế `kid` dựa trên thumbprint, nhưng đây là **quyết định triển khai**, không phải hành vi mặc định và thumbprint không tạo ra sự tin cậy đối với một nguồn khóa chưa được xác thực.

## 6. `use` — Mục đích sử dụng ở mức cao

`use` (*Public Key Use*) cho biết **mục đích dự kiến** của khóa. Hai giá trị JOSE thường gặp:

| Giá trị | Ý nghĩa | Trường hợp |
| --- | --- | --- |
| `sig` | Dùng cho chữ ký số hoặc MAC | Ký/xác minh JWS, bao gồm JWT có chữ ký. |
| `enc` | Dùng cho mã hóa | Một số vai trò khóa trong cơ chế JWE/mã hóa. |

Ví dụ public key chuyên xác minh JWS:

~~~json
{
  "kty": "RSA",
  "kid": "token-signing-key-01",
  "use": "sig",
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

Nếu mục tiêu là xác minh JWT có chữ ký và một JWK tự khai báo `use="enc"`, cấu hình đó **không tương thích với mục đích**. Hệ thống nên từ chối sử dụng khóa ấy cho xác minh chữ ký, đồng thời báo lỗi cấu hình/phân phối khóa.

Các giới hạn của `use`:

- `use` là **tùy chọn**. Thiếu `use` không tự làm một JWK sai chuẩn, nhưng chính sách hệ thống có thể yêu cầu trường này.
- `use="sig"` **không nói** khóa được phép *ký*, *xác minh* hay cả hai, cũng không xác định thuật toán cụ thể. Muốn diễn tả thao tác rõ hơn, xem `key_ops`.
- `use="enc"` không chỉ ra thuật toán mã hóa/JWE cụ thể hay quyền decrypt. Không suy đoán các quyền này chỉ từ chuỗi `enc`.
- Không dùng chung một khóa cho mục đích không tương thích chỉ vì có thể thay metadata. Nên tách khóa theo miền tin cậy, giao thức và mục đích.

## 7. `key_ops` — Tập thao tác được dự kiến

`key_ops` (*Key Operations*) là mảng chuỗi, mô tả **các thao tác mật mã** mà khóa được dự định sử dụng. Đây là thông tin chi tiết hơn `use`.

Các giá trị đăng ký trong RFC 7517 bao gồm:

| Giá trị | Thao tác | Ví dụ vai trò |
| --- | --- | --- |
| `sign` | Tạo chữ ký số hoặc MAC | Private key ký JWS; secret HMAC để tạo MAC. |
| `verify` | Xác minh chữ ký số hoặc MAC | Public key xác minh JWS; secret HMAC để kiểm tra MAC. |
| `encrypt` | Mã hóa nội dung dữ liệu | Khóa phục vụ phép mã hóa phù hợp. |
| `decrypt` | Giải mã nội dung dữ liệu | Khóa phục vụ phép giải mã phù hợp. |
| `wrapKey` | Bọc một khóa khác | Vai trò trong key management. |
| `unwrapKey` | Mở bọc một khóa khác | Vai trò trong key management. |
| `deriveKey` | Dẫn xuất khóa | Các cơ chế dẫn xuất khóa được hỗ trợ. |
| `deriveBits` | Dẫn xuất chuỗi bit | Các cơ chế dẫn xuất bit được hỗ trợ. |

Ví dụ dùng `key_ops` để tách vai trò:

~~~json
{
  "kty": "EC",
  "kid": "api-verification-04",
  "key_ops": ["verify"],
  "alg": "ES256",
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>"
}
~~~

JWK trên chỉ chứa public key và dự kiến phục vụ **xác minh**. Một JWK nội bộ mang cả private material có thể có `key_ops=["sign"]`, nhưng không được xuất private material đó trong JWKS công khai.

### 7.1. Quan hệ giữa `use` và `key_ops`

RFC 7517 khuyến nghị **không dùng `use` và `key_ops` cùng trong một JWK** (*SHOULD NOT*), vì có thể làm metadata dư thừa hoặc mâu thuẫn. Nếu cả hai có mặt, thông tin chúng cung cấp **bắt buộc phải nhất quán** (*MUST*).

| `use` | `key_ops` | Nhận xét |
| --- | --- | --- |
| `sig` | `["verify"]` | Về mặt ý nghĩa là nhất quán, nhưng việc khai báo cả hai vẫn không được khuyến nghị. |
| `sig` | `["sign"]` | Nhất quán về loại mục đích, thích hợp với khóa có khả năng ký. |
| `enc` | `["decrypt"]` | Nhất quán về mục đích mã hóa/giải mã. |
| `enc` | `["wrapKey"]` | Nhất quán với mục đích quản lý khóa mã hóa. |
| `enc` | `["verify"]` | **Mâu thuẫn**: thao tác xác minh chữ ký không tương thích mục đích mã hóa. |
| `sig` | `["encrypt"]` | **Mâu thuẫn**: mã hóa không phải chữ ký. |

Khi `key_ops` xuất hiện, các mục trong mảng **không được trùng lặp** theo RFC 7517. Các cơ chế xử lý khóa cũng cần kiểm tra loại khóa có thực sự thực hiện được thao tác đã khai báo: public RSA key chỉ có thể **verify** chứ không thể **sign** chữ ký RSA.

**Lưu ý mô hình quyền:** `key_ops=["verify"]` mô tả dự kiến của khóa; nó không phải ACL của KMS/HSM hay một lệnh cấm mật mã tuyệt đối. Phần mềm vẫn phải cưỡng chế chính sách sử dụng; với private key, hệ thống quản lý khóa mới là nơi giới hạn ai được quyền thực hiện `sign`.

## 8. `alg` — Thuật toán dự kiến cho khóa

`alg` (*Algorithm*) trong JWK là định danh thuật toán JOSE **dự kiến** sử dụng với khóa đó. Trong JWT header, `alg` lại có vai trò khai báo **thuật toán tạo chữ ký/MAC của chính token**. Hai trường cùng tên nhưng ở hai vị trí dữ liệu và **mức tin cậy khác nhau**.

~~~text
JWT header.alg  -> thuật toán mà token khẳng định đã dùng
JWK.alg         -> thuật toán dự kiến sử dụng với khóa
Verifier policy -> danh sách thuật toán thực sự ĐƯỢC PHÉP
~~~

Bên xác minh phải có **chính sách tin cậy độc lập** cho thuật toán. Chỉ khi header token, metadata khóa (nếu có), loại khóa và chính sách xác minh tương thích, verifier mới nên tiến hành phép xác minh.

### 8.1. Một số quan hệ thuật toán và loại khóa

| JWS `alg` | `kty` tương ứng | Ràng buộc đáng chú ý |
| --- | --- | --- |
| `HS256` | `oct` | Secret đối xứng có entropy đủ mạnh, không công khai. |
| `RS256` | `RSA` | Khóa RSA thích hợp và policy cho phép RSASSA-PKCS1-v1_5 + SHA-256. |
| `PS256` | `RSA` | RSA-PSS + SHA-256, cần chính sách và khả năng hỗ trợ tương ứng. |
| `ES256` | `EC` | `crv=P-256`, khóa/đường cong hợp lệ. |
| `ES384` | `EC` | `crv=P-384`, khóa/đường cong hợp lệ. |
| `EdDSA` | `OKP` | Ví dụ `crv=Ed25519` theo JOSE profile tương ứng. |

Sự tương thích không thể suy ra chỉ từ `kty`: `RSA` không có nghĩa mọi `RS*`/`PS*` đều được phép; `EC` cũng không có nghĩa một khóa `P-384` được dùng với `ES256`. Thêm nữa, JWT/JWE còn sử dụng các thuật toán **quản lý khóa** và **mã hóa nội dung** có ý nghĩa riêng; khi phân tích JWT có chữ ký (JWS), không được đánh đồng chúng với `alg` của JWS.

### 8.2. Thuật toán khai báo trong JWK có bắt buộc không?

**Không.** `alg` của JWK là thuộc tính tùy chọn. Nhiều nhà cung cấp JWKS công bố public key mà không ghi `alg`; verifier vẫn có thể xác minh an toàn nếu chính sách issuer/token xác định rõ các thuật toán cho phép và khóa được kiểm tra phù hợp.

Nếu JWK có `alg`, bên xác minh nên kiểm tra nó không mâu thuẫn với thuật toán đã cấu hình và header token. Nhưng **chỉ có `alg="RS256"` ở JWK không đủ để kết luận khóa đáng tin**.

### 8.3. Algorithm confusion và `alg=none`

Một lỗi bảo mật điển hình là tin giá trị `alg` của token như một “lệnh” lựa chọn cơ chế xác minh:

~~~text
Hệ thống kỳ vọng RS256 với RSA public key
           |
Attacker sửa header thành HS256
           |
Verifier lỗi dùng bytes của RSA public key làm HMAC secret
           |
Attacker có public key, có thể tạo HMAC giả
~~~

Đây là **algorithm/key confusion**. Phòng tránh bằng cách cố định thuật toán hoặc allowlist theo issuer/loại token, khóa thuật toán với kiểu khóa phù hợp, và không cho token tự chuyển họ thuật toán.

Với luồng yêu cầu JWT có chữ ký, không được chấp nhận `alg="none"` để bỏ qua phép xác minh. Dạng JWT không bảo vệ chữ ký chỉ có thể được xử lý nếu có cơ chế và ngữ cảnh tin cậy tách biệt, được thiết kế minh thị; không xem đó là lựa chọn dự phòng khi xác minh lỗi.

## 9. Cách phối hợp năm thuộc tính khi xác minh JWT

Một hệ thống nhận JWT có thể dùng quy trình khái niệm sau:

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Đọc header/payload như dữ liệu chưa tin cậy"]
    B --> C{"Issuer có trong cấu hình đáng tin?"}
    C -- Không --> X["Từ chối"]
    C -- Có --> D["Lấy JWKS của issuer đã được cấu hình"]
    D --> E{"kid tìm được ứng viên duy nhất?"}
    E -- Không --> X
    E -- Có --> F{"kty và tham số khóa hợp lệ?"}
    F -- Không --> X
    F -- Có --> G{"use / key_ops nếu có đều phù hợp?"}
    G -- Không --> X
    G -- Có --> H{"alg token, alg khóa và allowlist phù hợp?"}
    H -- Không --> X
    H -- Có --> I{"Chữ ký/MAC hợp lệ?"}
    I -- Không --> X
    I -- Có --> J{"iss, aud, exp, nbf và chính sách token hợp lệ?"}
    J -- Không --> X
    J -- Có --> K["Chấp nhận token"]
~~~

Sơ đồ thể hiện **một chính sách thận trọng có sử dụng `kid`**. Chuẩn JWK không yêu cầu mọi JWT phải có `kid`; nếu hệ thống cho phép token không có `kid`, cần quy tắc tìm khóa rõ ràng và tránh ứng viên mơ hồ.

### 9.1. Ví dụ kiểm tra từng bước

Giả sử API cấu hình sẵn:

~~~text
Trusted issuer: https://issuer.example.test/
Trusted JWKS:  https://issuer.example.test/.well-known/jwks.json
Allowed JWS algorithms: RS256
Expected audience: payments-api
Token class: access token
~~~

JWT nhận được có header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "payments-rsa-17"
}
~~~

JWKS của issuer cung cấp:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "payments-rsa-17",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "payments-rsa-16",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_OLDER_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Quy trình:

1. Xác định issuer nằm trong tập đã tin cậy. Có thể dùng claim `iss` chưa xác minh làm **gợi ý tìm cấu hình issuer đã biết**, nhưng tuyệt đối không vì nó mà tin một issuer/JWKS mới.
2. Tìm `kid="payments-rsa-17"` chỉ trong JWKS của issuer tương ứng. Chọn **một** khóa.
3. Kiểm tra `kty="RSA"` và tham số public RSA hợp lệ; khóa không thuộc danh sách bị thu hồi hoặc hết chính sách tin cậy.
4. Kiểm tra `use="sig"` (hoặc `key_ops` tương thích nếu được công bố); kiểm tra `alg="RS256"` trong JWK, header và policy.
5. Xác minh chữ ký RSA-SHA256 trên dữ liệu JWS gốc. Không dùng payload đã parse/re-serialize thay cho signing input chuẩn.
6. **Sau khi chữ ký hợp lệ**, kiểm tra `iss` chính xác, `aud=payments-api`, thời gian `exp`/`nbf`, loại token và điều kiện phân quyền.

Nếu JWT thay `alg` thành `HS256`, phải **từ chối trước** bước xác minh vì thuật toán ngoài allowlist và không tương thích `kty=RSA`.

### 9.2. Pseudocode độc lập nền tảng

~~~text
function validateJwt(token, trustedConfiguration):
    header, untrustedClaims = parseWithoutTrust(token)
    issuerConfig = trustedConfiguration.lookupIssuer(untrustedClaims.iss)
    if issuerConfig is null:
        reject("untrusted issuer")

    if header.alg not in issuerConfig.allowedJwsAlgorithms:
        reject("disallowed algorithm")

    keys = loadTrustedJwks(issuerConfig.jwksUri)
    candidates = keys.matchKidWithinIssuer(header.kid)
    key = requireUniqueAndTrustedCandidate(candidates)

    if not isCompatibleKeyTypeAndParameters(key, header.alg):
        reject("incompatible key")
    if key.use exists and key.use != "sig":
        reject("wrong key purpose")
    if key.key_ops exists and "verify" not in key.key_ops:
        reject("verification not permitted")
    if key.alg exists and key.alg != header.alg:
        reject("algorithm mismatch")
    if not verifyCryptographicSignature(token, key, header.alg):
        reject("invalid signature")

    claims = parseVerifiedClaims(token)
    validateIssuerAudienceTimeTokenTypeAndPermissions(claims, issuerConfig)
    accept(claims)
~~~

Pseudocode mang tính **minh họa thiết kế**. Trong thực tế, sử dụng thư viện JOSE/JWT được duy trì và cấu hình thuật toán, issuer, audience và key resolver rõ ràng, tránh tự hiện thực thuật toán mật mã.

## 10. Các ví dụ đúng/sai dễ gây nhầm lẫn

### Tình huống A — Sai `use`

~~~json
{
  "kty": "RSA",
  "kid": "verify-me",
  "use": "enc",
  "alg": "RS256",
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

Khóa có kiểu RSA và ghi `RS256` nhưng `use="enc"` lại mô tả mục đích mã hóa. Không chấp nhận JWK này để xác minh JWS; cần xử lý sai lệch metadata tại nơi quản trị khóa.

### Tình huống B — `use` và `key_ops` mâu thuẫn

~~~json
{
  "kty": "EC",
  "use": "enc",
  "key_ops": ["verify"],
  "crv": "P-256",
  "x": "<BASE64URL_X_COORDINATE>",
  "y": "<BASE64URL_Y_COORDINATE>"
}
~~~

`use=enc` và `key_ops=["verify"]` mâu thuẫn. Theo RFC 7517, khi cùng xuất hiện chúng **phải nhất quán**. Không chọn khóa này để xác minh chữ ký.

### Tình huống C — Sai họ thuật toán

~~~text
JWT header.alg = "HS256"
JWK.kty        = "RSA"
Verifier policy = ["RS256"]
~~~

JWT đòi HMAC nhưng khóa được cấu hình là RSA và policy chỉ chấp nhận RSA-SHA256. Kết quả phải là **từ chối**, tuyệt đối không dùng public RSA làm HMAC secret.

### Tình huống D — `kid` đúng nhưng khóa thuộc issuer khác

~~~text
Issuer A JWKS: kid = "main-key" -> public key A
Issuer B JWKS: kid = "main-key" -> public key B
JWT claim iss = Issuer B
API chỉ tin Issuer A
~~~

Dù cùng `kid`, API **không được** lấy public key B để xác minh nếu issuer B không nằm trong cấu hình tin cậy. `kid` chỉ có ý nghĩa khi tra cứu **bên trong phạm vi nguồn khóa đáng tin**.

### Tình huống E — `key_ops` không khớp vai trò

~~~json
{
  "kty": "RSA",
  "kid": "key-with-wrong-operation",
  "key_ops": ["sign"],
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

JWK này chỉ chứa phần public RSA nhưng lại khai báo thao tác `sign` cần private key. Metadata không phù hợp với phần khóa đang có. Bên xác minh JWS không được xem `["sign"]` là quyền `verify`.

### Tình huống F — `alg` bị bỏ trống

~~~json
{
  "kty": "RSA",
  "kid": "rs-public-05",
  "use": "sig",
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

JWK này **không sai chuẩn chỉ vì không có `alg`**. Tuy nhiên verifier phải biết trước issuer được phép dùng thuật toán nào, ví dụ chỉ `RS256`; không nên suy đoán rằng mọi thuật toán RSA đều hợp lệ.

## 11. Liên quan đến rotation và phân phối JWKS

Khi đổi khóa ký, issuer thường công bố nhiều JWK một thời gian:

~~~text
K1: kid=jwt-sign-01   use=sig   alg=RS256  -> ngừng ký, còn xác minh
K2: kid=jwt-sign-02   use=sig   alg=RS256  -> khóa đang ký
~~~

Nhờ `kid`, verifier biết token cũ cần K1 và token mới cần K2. Nhưng một khóa xuất hiện trong JWKS **không có nghĩa** nó vẫn đang được dùng để ký. Các giai đoạn “đang ký”, “chỉ xác minh”, “đã thu hồi” phải được quản trị qua chính sách và hệ thống quản lý khóa; năm thuộc tính đang học không đủ để biểu diễn toàn bộ vòng đời hoặc tình trạng thu hồi.

Nếu private key bị lộ, chỉ loại public key khỏi JWKS có thể chưa chặn ngay việc xác minh tại các consumer còn cache. Cần cơ chế làm mới cache/cấm khóa khẩn cấp, và khi cần từ chối tất cả token ký bằng khóa bị lộ dù chưa đến `exp`.

## 12. Metadata khác cần biết khi đọc JWK

Ngoài năm thuộc tính chính, các member sau thường gặp:

| Thuộc tính | Vai trò | Cảnh báo |
| --- | --- | --- |
| `n`, `e` | Public RSA modulus/exponent. | Phải kiểm tra định dạng và kích thước khóa. |
| `crv`, `x`, `y` | Thông tin đường cong và điểm public cho EC. | Phải tương thích với thuật toán. |
| `crv`, `x` | Thông tin public của OKP. | Không nhầm với EC point. |
| `d` | Thành phần private của RSA/EC/OKP. | Không công bố trong JWKS public. |
| `k` | Bí mật đối xứng của `oct`. | Không công bố trong JWKS public. |
| `x5c` | Chuỗi chứng chỉ X.509 liên quan khóa. | Phải xác minh chuỗi, quan hệ khóa và gốc tin cậy theo chính sách; không mặc nhiên tin vì chứng chỉ được đính kèm. |
| `x5u` | URL nơi có chứng chỉ X.509. | Không fetch tùy ý URL từ token hoặc nguồn chưa tin cậy; phòng SSRF. |
| `x5t`, `x5t#S256` | Thumbprint chứng chỉ X.509 theo SHA-1 hoặc SHA-256. | Không tự chứng minh bên phát hành đáng tin. |

Đặc biệt:

- **`jku` và `jwk` là các tham số có thể xuất hiện trong JWS header**, không phải quyền tự chọn nguồn tin cậy. `jku` có thể chỉ tới JWKS; `jwk` có thể nhúng trực tiếp khóa. Không coi khóa hoặc địa chỉ do attacker cung cấp là đáng tin chỉ vì JWT mang theo chúng.
- Việc nhận nhiều trường JSON trùng tên như hai `kid` hoặc hai `alg` có thể tạo sai khác giữa các parser. RFC 7517 có quy định xử lý duplicate member names; lựa chọn an toàn và dễ kiểm soát là **từ chối dữ liệu có tên member trùng lặp** trong parser đầu vào.
- JWKS có thể chứa JWK không thuộc kiểu/thuật toán mà consumer hỗ trợ. Bỏ qua khóa không hỗ trợ theo chính sách, không tự thêm thuật toán mới vào allowlist.
- Không lấy riêng một `kid` từ hai nguồn khác nhau rồi coi chúng tương đương; khóa phải được kiểm soát theo **issuer + nguồn khóa + mục đích + thuật toán**.

## 13. Các quy tắc vận hành và bảo mật

### Đối với bên công bố JWK/JWKS

- Sinh khóa bằng cơ chế mật mã đáng tin; không dùng secret đoán được cho `oct`.
- Giữ private key và `k` trong hệ thống quản lý bí mật; xuất public key khi cần xác minh bởi bên ngoài.
- Duy trì `kid` duy nhất và ổn định cho từng vật liệu khóa; cập nhật `kid` khi thay khóa.
- Tách khóa ký và khóa mã hóa khi chính sách cho phép; tránh metadata `use`/`key_ops` mâu thuẫn.
- Chỉ công bố tham số và thuật toán thực sự dùng được; kiểm tra dữ liệu JWKS trước khi phát hành.
- Công bố khóa mới trước khi bắt đầu ký khi rotation, và xử lý khóa cũ theo thời hạn token/cơ chế thu hồi.

### Đối với bên xác minh JWT

- Cấu hình issuer, endpoint JWKS, audience, loại token và thuật toán cho phép từ nguồn tin cậy.
- Kiểm tra `kty` và tham số theo thuật toán; `use`/`key_ops`/`alg` nếu có phải tương thích chính sách.
- Giới hạn `kid` trong JWKS của đúng issuer; không dùng token tự chỉ định URL tải khóa.
- Xác minh chữ ký trước khi tin claims; sau đó vẫn kiểm tra `iss`, `aud`, `exp`, `nbf` và yêu cầu nghiệp vụ.
- Có TTL/giới hạn cache và rate limit khi tải lại JWKS; hỗ trợ loại khóa khẩn cấp.
- Ghi log lỗi xác minh, `kid` và issuer ở mức phù hợp, **không ghi nguyên JWT nhạy cảm hoặc private key**.

## 14. Bài tập tự kiểm tra

### Bài 1 — Nhận biết khóa

Cho JWK:

~~~json
{
  "kty": "oct",
  "kid": "shared-hs256-03",
  "alg": "HS256",
  "key_ops": ["sign", "verify"],
  "k": "<BASE64URL_SECRET>"
}
~~~

**Câu hỏi:** Có được đưa JWK này lên endpoint JWKS công khai cho các API xác minh không?

**Đáp án:** Không. `kty=oct` và `k` biểu diễn bí mật đối xứng; bên nào biết bí mật sẽ có khả năng tạo MAC hợp lệ. Muốn các API độc lập chỉ được xác minh, có thể dùng chữ ký bất đối xứng và phân phối public key.

### Bài 2 — Phân biệt metadata và chính sách

Một JWT ghi `alg="ES256"`, JWK ghi `kty="EC"` và `alg="ES256"`, trong khi policy của API chỉ cho phép `RS256`.

**Đáp án:** Từ chối JWT. Dù metadata có vẻ tương thích về kiểu khóa/thuật toán, **chính sách của verifier** mới quyết định thuật toán được phép.

### Bài 3 — Trường tùy chọn

Một public JWK có `kty="RSA"`, `n`, `e` và `kid`, nhưng thiếu `use`, `key_ops`, `alg`.

**Đáp án:** Không mặc nhiên là JWK sai chuẩn. Các trường trên là tùy chọn. Verifier vẫn cần chính sách xác định thuật toán, issuer và mục đích token, đồng thời có thể áp dụng yêu cầu metadata chặt hơn theo quy định riêng.

### Bài 4 — Đụng `kid`

Trong một JWKS có hai public key RSA khác nhau cùng `kid="current"`. Một JWT mang `kid="current"`.

**Đáp án:** Cấu hình mơ hồ. Trong một hệ thống kiểm soát chặt chẽ nên từ chối ứng viên không duy nhất, cảnh báo nhà phát hành và sửa `kid` để phân biệt vật liệu khóa. Không tự chọn khóa đầu tiên hoặc đổi thuật toán để thử cho đến khi xác minh thành công.

## 15. Checklist đọc nhanh một JWK

- [ ] **`kty`:** Có tồn tại, được hỗ trợ và phù hợp phép toán không?
- [ ] **Tham số khóa:** Public/private material có đúng định dạng, mức an toàn và ranh giới công bố không?
- [ ] **`kid`:** Có thể tìm đúng một khóa trong **đúng issuer/JWKS tin cậy** không?
- [ ] **`use`:** Nếu có, có mô tả đúng mục đích chữ ký (`sig`) hoặc mã hóa (`enc`) không?
- [ ] **`key_ops`:** Nếu có, đã liệt kê thao tác phù hợp và không trùng lặp chưa?
- [ ] **`use` + `key_ops`:** Nếu đồng thời có mặt, có nhất quán không?
- [ ] **`alg`:** Nếu có, có tương thích `kty`, tham số, JWT header và allowlist không?
- [ ] **Nguồn tin cậy:** Khóa có thực sự xuất phát từ nguồn đã cấu hình và chưa bị thu hồi không?
- [ ] **JWT:** Sau xác minh chữ ký, đã kiểm tra issuer, audience, thời gian và yêu cầu cấp quyền chưa?

## 16. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): định nghĩa `kty`, `kid`, `use`, `key_ops`, `alg` và cấu trúc JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và các kiểu tham số JWK.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, chữ ký JWS và các tham số `alg`, `kid`, `jwk`, `jku`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims cần xác minh.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): rủi ro thuật toán/khóa, kiểm tra thuật toán và quy tắc xác minh JWT an toàn.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): tính dấu vân tay cho JWK.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): kiểu khóa `OKP` và EdDSA trong JOSE.

**Ghi nhớ:** `kty` cho biết **loại khóa**; `kid` giúp **chọn khóa**; `use` cho biết **mục đích**; `key_ops` mô tả **thao tác**; `alg` mô tả **thuật toán dự kiến**. Muốn xác minh JWT an toàn, phải đặt cả năm thuộc tính trong **ngữ cảnh issuer, JWKS và chính sách tin cậy**, rồi xác minh chữ ký **và** claims liên quan.
