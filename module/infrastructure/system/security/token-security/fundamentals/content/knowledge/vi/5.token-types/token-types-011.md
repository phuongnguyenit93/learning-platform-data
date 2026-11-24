# Signed token và encrypted token

## Mục tiêu học tập

Trong chương **Token types** của học phần bảo mật token, hai khả năng thường bị nhầm với nhau là **ký token (signing)** và **mã hóa token (encryption)**. Chúng giải quyết những câu hỏi bảo mật khác nhau:

- **Chữ ký:** nội dung có bị thay đổi và có được tạo bởi bên nắm khóa ký đáng tin cậy không?
- **Mã hóa:** người không có quyền giải mã có đọc được nội dung nhạy cảm không?

Sau bài này, bạn có thể:

1. Phân biệt **JWS (JSON Web Signature)**, **JWE (JSON Web Encryption)** và **JWT (JSON Web Token)**; nhận diện cấu trúc Compact Serialization của từng loại.
2. Giải thích rõ tính **toàn vẹn**, **xác thực nguồn gốc**, **bí mật** và **giới hạn chống phát lại (replay)** của token ký hoặc token mã hóa.
3. Mô tả các thuật toán, khóa và trường header quan trọng như `alg`, `enc`, `kid`, `typ`, `cty`, cũng như những sai lầm lựa chọn khóa.
4. Hiểu mô hình **ký rồi mã hóa (nested JWT)** khi hệ thống cần cả xác thực nguồn phát hành lẫn bảo mật claims.
5. Áp dụng kiểm tra issuer, audience, thời hạn, loại token, scope, trạng thái và quyền trên tài nguyên sau khi xác minh mật mã.
6. Lựa chọn cách bảo vệ phù hợp cho access token, refresh token và ID token trong OAuth 2.0/OIDC, kể cả khi token bị đánh cắp hoặc phát lại.

## 1. Đặt đúng câu hỏi bảo mật

Giả sử Authorization Server cấp access token cho ứng dụng mua hàng. Token có thể chứa `sub=user-123`, `aud=orders-api` và `scope=orders:read`. Hãy xét bốn rủi ro khác nhau:

| Rủi ro | Chữ ký có giúp không? | Mã hóa có giúp không? |
|---|---|---|
| Kẻ tấn công **sửa** scope thành `orders:write` | Có, nếu Resource Server xác minh chữ ký đúng cách. | Mã hóa có xác thực (như JWE với AEAD) giúp phát hiện ciphertext bị chỉnh sửa. |
| Người xem được token muốn **đọc** claims | Không. Payload của JWS thông thường có thể giải mã để đọc. | Có, khi nội dung được mã hóa cho người nhận và khóa giải mã an toàn. |
| Token được ký bởi **issuer không được API tin** | Chữ ký khớp một khóa lạ **chưa đủ**; phải ràng buộc với issuer tin cậy. | Mã hóa cho API không tự chứng minh ai đã phát hành token. |
| Kẻ tấn công **sao chép nguyên token** còn hiệu lực rồi gửi lại | Không tự ngăn replay. | Không tự ngăn replay: ciphertext vẫn có thể được trình như bearer token. |

Điểm mấu chốt: một token có định dạng đẹp, có chữ ký hợp lệ hoặc giải mã thành công **chưa phải là quyết định cho phép truy cập**. API phải hiểu nguồn gốc token, nơi được phép dùng, mục đích của token và quyền đối với hành động đang được yêu cầu.

### Phân biệt ba trục

| Trục | Các dạng | Ý nghĩa |
|---|---|---|
| **Mục đích** | Access token, refresh token, ID token | Token dùng để gọi API, lấy token mới hay thông báo kết quả xác thực OIDC. |
| **Biểu diễn và bảo vệ nội dung** | Opaque token, JWT ký (JWS), JWT mã hóa (JWE), JWT lồng nhau | Token có cấu trúc như thế nào, có chữ ký hoặc có mã hóa hay không. |
| **Cách sử dụng** | Bearer, sender-constrained | Chỉ cần cầm token là có thể trình token hay còn cần bằng chứng sở hữu khóa/chứng chỉ. |

Các trục độc lập. **JWT không có nghĩa là “chỉ ký”**: một JWT có thể được biểu diễn bằng JWS, JWE hoặc kết hợp. **Opaque token** là chuỗi mà phía nhận không tự suy diễn cấu trúc; opaque token **không đồng nghĩa** với JWE hay với token đã được mã hóa.

## 2. JWS, JWE và JWT liên hệ với nhau ra sao?

### JWS: bảo vệ tính toàn vẹn của dữ liệu đã ký

**JWS** là định dạng bảo vệ payload bằng chữ ký số hoặc MAC (Message Authentication Code). Dạng **JWS Compact Serialization** phổ biến có **ba phần**:

~~~text
BASE64URL(Protected Header).BASE64URL(Payload).BASE64URL(Signature)
~~~

Ví dụ minh họa **cấu trúc**, không phải một token có thể sử dụng:

~~~text
eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.<SIGNATURE_PLACEHOLDER>
       HEADER              PAYLOAD               SIGNATURE
~~~

Payload ở dạng Compact JWS thông thường **không được mã hóa bí mật**; Base64URL chỉ là cách biểu diễn byte dưới dạng ký tự an toàn cho truyền tải. Ai có chuỗi token có thể giải mã phần payload để xem thông tin. Nếu cần giữ bí mật, chỉ chữ ký là chưa đủ.

### JWE: bảo vệ tính bí mật và tính toàn vẹn của nội dung mã hóa

**JWE** chứa dữ liệu được mã hóa; dạng **JWE Compact Serialization** phổ biến có **năm phần**:

~~~text
BASE64URL(Protected Header)
.
BASE64URL(Encrypted Key)
.
BASE64URL(Initialization Vector)
.
BASE64URL(Ciphertext)
.
BASE64URL(Authentication Tag)
~~~

Viết trên một dòng sẽ có dạng:

~~~text
<PROTECTED_HEADER>.<ENCRYPTED_KEY>.<IV>.<CIPHERTEXT>.<TAG>
~~~

Trong một số thuật toán quản lý khóa như `alg=dir`, phần **Encrypted Key có thể rỗng**; vẫn giữ vị trí tương ứng trong chuỗi Compact. Protected Header có thể được quan sát trước khi giải mã, nên JWE **không che giấu toàn bộ metadata**. Kích thước và hình thức token cũng có thể tiết lộ một số thông tin phụ.

JWE sử dụng cơ chế mã hóa có xác thực để phát hiện việc thay đổi nội dung/header được bảo vệ. Tuy nhiên, **việc giải mã thành công không mặc nhiên chứng minh người phát hành là Authorization Server mà API tin cậy**. Ai có khả năng mã hóa bằng khóa công khai của người nhận cũng có thể tạo ciphertext gửi đến người nhận. Cần một cơ chế xác thực nguồn phát hành đáng tin cậy nếu quyết định bảo mật dựa vào nguồn đó.

> **Giới hạn của cách đếm dấu chấm:** “ba phần” và “năm phần” ở trên chỉ mô tả **Compact Serialization** thường dùng. JWS/JWE còn có JSON Serialization, các trường hợp payload đặc biệt và các profile riêng. Đừng coi số phần là cách xác minh một token.

### JWT là tập claims, không phải tên của thuật toán

**JWT** mô tả cách biểu diễn các **claims** (như `iss`, `sub`, `aud`, `exp`) trong cấu trúc JSON được bảo vệ bằng JOSE:

- **Signed JWT:** claims được mang trong một JWS.
- **Encrypted JWT:** claims được mang trong một JWE.
- **Nested JWT:** ví dụ một JWS được đặt bên trong JWE để có cả chữ ký và mã hóa.

JWS/JWE là các cấu trúc bảo vệ dữ liệu tổng quát; **không phải mọi JWS hay JWE đều là JWT**. Trong hệ sinh thái OAuth 2.0/OIDC, dạng nào được chấp nhận phải tuân theo hợp đồng token/profile cụ thể, chứ không phải suy đoán từ hình thức.

## 3. Signed token: chữ ký chứng minh điều gì?

### Chữ ký bảo vệ thông điệp khỏi bị sửa trái phép

Giả sử Authorization Server tạo một access token JWT đã ký:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

Các giá trị thời gian chỉ để minh họa. Để cấp quyền, API **không thể** đọc payload rồi lập tức tin `scope`. API cần xác minh JWS theo khóa và thuật toán tin cậy trước khi sử dụng claims.

Nếu kẻ tấn công thay `orders:read` thành `orders:write` trong payload đã ký, giá trị chữ ký/MAC đã có sẽ không còn khớp. Khi xác minh đúng, API từ chối token bị sửa.

### Chữ ký đối xứng và bất đối xứng

| Cơ chế | Ví dụ thuật toán JWS | Ai tạo được chữ ký/MAC? | Ai xác minh được? | Điều cần lưu ý |
|---|---|---|---|---|
| **MAC đối xứng** | `HS256` | Bên nắm **shared secret**. | Bên nắm chính secret đó. | Mọi bên có secret đều có khả năng tạo MAC; phân phối secret rộng làm yếu ranh giới issuer. |
| **Chữ ký bất đối xứng** | `RS256`, `ES256` | Bên nắm **private signing key**. | Bên có **public verification key** tương ứng. | Public key có thể phổ biến cho nhiều API mà không cho phép chúng ký token mới. |

Với `RS256` hoặc `ES256`, Resource Server chỉ cần **khóa công khai đáng tin cậy** để xác minh, không cần biết private key. Đây là lợi ích khi nhiều API phải kiểm tra access token của cùng Authorization Server.

Với `HS256`, secret ký và kiểm tra là cùng một bí mật: một API nắm secret để xác minh cũng về mặt kỹ thuật **có thể tạo MAC hợp lệ**. Vì vậy phải cân nhắc phạm vi phân phối khóa và ranh giới tin cậy.

Không coi chữ ký/MAC là bảo đảm **không thể chối bỏ tuyệt đối**: kết quả còn phụ thuộc loại khóa, quản trị khóa, phân quyền sử dụng, nhật ký và khả năng khóa bị lộ.

### Header của signed JWT

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-key-01",
  "typ": "at+jwt"
}
~~~

- `alg` cho biết thuật toán **được khai báo** để tạo chữ ký/MAC. API phải có **allowlist** thuật toán phù hợp với profile và issuer, không để header token tự quyết định chính sách.
- `kid` gợi ý chọn khóa trong **tập khóa đã tin cậy**; không phải giấy phép tự tải khóa từ một URL hoặc file tùy ý.
- `typ` có thể giúp phân biệt loại token. Giá trị `at+jwt` có ý nghĩa trong profile JWT access token của OAuth 2.0 (RFC 9068); profile khác có thể dùng quy ước riêng.

**Header cũng là dữ liệu đầu vào chưa đáng tin** cho tới khi JWS được xác minh. Hệ thống có thể đọc một số trường để tìm khóa phù hợp, nhưng chỉ trong ranh giới **issuer, JWKS và thuật toán đã được cấu hình**.

### Những điều chữ ký không bảo đảm

1. **Bí mật:** nội dung payload có thể đọc được nếu là JWS thông thường. Không đặt mật khẩu, private key hoặc bí mật khác vào payload.
2. **Issuer đáng tin cậy:** một JWS có chữ ký hợp lệ với **khóa của attacker** vẫn phải bị từ chối nếu API không tin issuer/khóa đó.
3. **Đúng API:** access token `aud=orders-api` không được dùng ở `billing-api` chỉ vì cùng AS đã ký.
4. **Còn hạn/đủ quyền:** chữ ký đúng không thay `exp`, `nbf`, scope, tenant hoặc quyền trên từng đối tượng.
5. **Không bị phát lại:** một bearer token ký hợp lệ có thể bị sao chép và trình lại.

## 4. Encrypted token: nội dung được bảo mật ra sao?

### Hai nhóm thuật toán trong JWE

JWE thường kết hợp **quản lý khóa** để đưa khóa mã hóa nội dung đến người nhận và **mã hóa nội dung có xác thực**:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-api-decryption-key-01",
  "typ": "JWT"
}
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `alg` | Thuật toán quản lý/thoả thuận hoặc bọc khóa mã hóa nội dung. | `RSA-OAEP-256`; hoặc `dir` khi dùng khóa đối xứng trực tiếp. |
| `enc` | Thuật toán mã hóa nội dung có xác thực. | `A256GCM` (AES-GCM với khóa 256 bit). |
| `kid` | Chỉ dẫn chọn khóa thích hợp của **người nhận** trong kho khóa tin cậy. | `orders-api-decryption-key-01`. |
| `iv`, ciphertext, tag | Giá trị khởi tạo, dữ liệu mã hóa và bằng chứng xác thực nội dung. | Các phần tương ứng trong JWE Compact. |

Với `RSA-OAEP-256`, bên phát hành có thể mã hóa khóa mã hóa nội dung (Content Encryption Key, CEK) bằng **public key của Resource Server**. Resource Server dùng **private decryption key** để giải mã CEK, sau đó giải mã ciphertext bằng thuật toán `enc`. Còn với `alg=dir`, hai bên sử dụng khóa đối xứng được chia sẻ theo chính sách.

Chọn các thuật toán được thư viện JOSE và chính sách bảo mật của hệ thống cho phép; **không** chấp nhận mọi `alg`/`enc` từ dữ liệu token. Dùng thư viện có kiểm chứng để xử lý IV, tag, AAD, padding và thứ tự thao tác. Tự triển khai primitives mã hóa rất dễ tạo lỗ hổng.

### JWE bảo vệ và không bảo vệ những gì?

JWE với thuật toán mã hóa có xác thực cung cấp:

- **Tính bí mật của plaintext:** người không có khóa giải mã phù hợp khó đọc claims.
- **Tính toàn vẹn của dữ liệu mã hóa:** sửa ciphertext hoặc nội dung header được bảo vệ khiến bước xác thực thất bại.
- **Khả năng nhắm đến người nhận:** với cơ chế quản lý khóa phù hợp, chỉ người nhận có khóa giải mã mới mở được nội dung.

Tuy nhiên, JWE **không tự chứng minh issuer** trong mọi cấu hình. Ví dụ khóa công khai của API được công bố để AS mã hóa token; attacker cũng có thể mã hóa JSON do họ tạo bằng khóa công khai đó. Resource Server giải mã thành công **chưa đủ** để tin `sub=admin` hoặc `scope=payments:refund`.

Trong hệ thống chỉ có người gửi/nhận đáng tin và dùng khóa đối xứng riêng, tính xác thực từ cơ chế quản lý khóa có thể tham gia vào mô hình tin cậy. Nhưng nếu cần xác minh rõ **chữ ký của issuer**, hãy thiết kế cơ chế ký độc lập hoặc sử dụng **nested JWT** theo hợp đồng, tránh suy luận chung rằng “giải mã được tức token do AS phát hành”.

### Tại sao đã có HTTPS vẫn có trường hợp cần JWE?

**TLS** bảo vệ kênh giữa các đầu nối TLS, thường giúp tránh bên ngoài đọc token trên đường truyền. **JWE** bảo vệ plaintext của token ở **cấp đối tượng** đối với bên không có khóa giải mã, kể cả khi token được chuyển qua nhiều hop hoặc hệ thống trung gian có thể nhìn thấy chuỗi token.

Ví dụ gateway chuyển token tới `orders-api`: nếu token là JWE mã hóa cho `orders-api`, gateway có thể chuyển tiếp mà không đọc được claims. Đổi lại, gateway sẽ khó tự quyết định theo các claims bên trong nếu không có cơ chế xác minh riêng; kiến trúc phải xác định rõ ai là bên được giải mã và ai chịu trách nhiệm cấp quyền.

Mã hóa token **không thay thế TLS**. Metadata JWE và kích thước token có thể vẫn nhìn thấy; token có thể bị trộm từ log, trình duyệt hoặc bộ nhớ và được **phát lại nguyên ciphertext** nếu vẫn là bearer token.

## 5. Signed, encrypted và nested JWT: so sánh nhanh

| Tiêu chí | **JWT ký (JWS)** | **JWT mã hóa (JWE)** | **Ký rồi mã hóa (nested JWT)** |
|---|---|---|---|
| Claims có thể đọc trực tiếp từ chuỗi token? | Thường có, sau Base64URL decode. | Không, cần khóa giải mã. | Không, phải giải mã lớp ngoài trước. |
| Phát hiện sửa đổi trái phép? | Có, nếu xác minh chữ ký/MAC. | Có, nếu giải mã có xác thực đúng. | Có ở cả lớp ngoài và chữ ký lớp trong. |
| Chứng minh issuer đã ký claims? | Có điều kiện: chữ ký phải được xác minh bằng khóa thuộc issuer tin cậy. | Không mặc nhiên, chỉ nhờ ciphertext. | Có, khi xác minh JWS bên trong bằng khóa tin cậy. |
| Số phần trong Compact Serialization | 3 | 5 | Lớp ngoài 5, plaintext là JWS 3 phần. |
| Quyền đọc claims tại Resource Server | Bên có token thường đọc được. | Bên có khóa giải mã phù hợp. | Bên giải mã được lớp ngoài. |
| Tự chống token theft/replay? | Không. | Không. | Không. |

Kết luận thực tế: **ký** giúp API xác minh nội dung do issuer đáng tin phát hành không bị sửa; **mã hóa** giúp giữ kín claims đối với bên thiếu khóa; **kết hợp** khi cần cả hai. Nhưng cả ba vẫn phải đi qua quy trình **kiểm tra token và phân quyền** trước khi API phục vụ dữ liệu.

## 6. Nested JWT: khi cần vừa xác minh nguồn vừa giữ kín nội dung

Với yêu cầu bảo mật claims và chứng minh issuer đã ký, một thiết kế thường gặp là **ký trước, mã hóa sau** (*sign-then-encrypt*):

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant Client as Client
    participant API as Resource Server
    AS->>AS: Tạo claims + kiểm tra chính sách cấp token
    AS->>AS: Ký claims thành JWS bằng private signing key
    AS->>AS: Mã hóa toàn bộ JWS thành JWE cho API
    AS-->>Client: JWE access token
    Client->>API: Gửi access token qua HTTPS
    API->>API: Xác thực và giải mã JWE với khóa nhận
    API->>API: Xác minh JWS bên trong với khóa issuer
    API->>API: Kiểm tra iss, aud, exp, scope, trạng thái và quyền
    API-->>Client: Chỉ trả dữ liệu được phép
~~~

Mã giả minh họa **quy trình**, không phải API của một thư viện cụ thể:

~~~text
# Authorization Server
claims = issueAuthorizedClaims(subject, client, audience, scopes, ttl)
signedJwt = JWS.sign(claims, asSigningPrivateKey, approvedSigningAlg)
encryptedJwt = JWE.encrypt(
    signedJwt,
    resourceServerEncryptionPublicKey,
    approvedKeyManagementAlg,
    approvedContentEncryptionAlg
)
return encryptedJwt

# Resource Server
outer = parseAndValidateJweEnvelope(receivedToken, localJwePolicy)
signedJwt = JWE.decryptAndAuthenticate(outer, rsDecryptionPrivateKey)
claims = JWS.verify(signedJwt, trustedIssuerSigningKeys, allowedSigningAlgs)
requireValidIssuerAudienceTypeLifetimeAndStatus(claims, rsPolicy)
requireGrantedScopeAndResourceAuthorization(claims, requestedAction, resource)
~~~

Với JWT lồng nhau, protected header lớp ngoài thường có `cty: "JWT"` để biểu thị rằng payload là một JWT khác; kiểu `typ`/`cty` và các giá trị cụ thể phụ thuộc profile. Ví dụ **JWE protected header**:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-api-decryption-key-01",
  "cty": "JWT"
}
~~~

Cần kiểm tra **cả lớp ngoài và lớp trong**. Sau khi giải mã JWE, không được tự coi JSON bên trong đã đáng tin; phải xác minh JWS và claims theo profile mong đợi. Nếu ứng dụng yêu cầu cả ký lẫn mã hóa thì token chỉ có JWS hoặc chỉ có JWE **không được tự động chấp nhận như một phương án dự phòng**.

Một số thiết kế có thể **mã hóa trước rồi ký**, nhưng ý nghĩa về việc ai nhìn thấy chữ ký, thành phần nào có thể kiểm chứng và thứ tự xử lý khác đi. Hãy chọn thứ tự và cấu trúc theo giao thức/profile có hỗ trợ, tránh tự ghép tùy tiện rồi coi đó là tương đương.

## 7. Khóa ký, khóa giải mã và ranh giới tin cậy

Một hệ thống nhiều dịch vụ có thể có **hai cặp khóa bất đối xứng riêng**:

~~~text
Authorization Server
  signing private key  ---> Tạo JWS
  signing public key   ---> Resource Servers xác minh JWS (ví dụ qua JWKS)

Orders API
  encryption public key ---> Authorization Server dùng để mã hóa JWE
  decryption private key ---> Orders API dùng để giải mã JWE
~~~

**Private signing key** và **private decryption key** có nhiệm vụ khác nhau, không nên hoán đổi. Với HMAC hoặc mã hóa đối xứng, việc chia sẻ khóa đòi hỏi mô hình tin cậy riêng vì nhiều bên có thể sở hữu cùng secret.

Các nguyên tắc quản trị khóa:

1. **Nguồn khóa tin cậy:** issuer/JWKS URL và khóa giải mã phải được xác định từ cấu hình đáng tin, không tự nhận URL khóa từ `jku` hoặc `x5u` trong token chưa xác minh.
2. **Giới hạn thuật toán:** allowlist `alg`/`enc` được phép, kiểm tra loại và kích thước khóa phù hợp. Không chấp nhận `alg: none` khi chính sách đòi chữ ký; ngăn nhầm thuật toán đối xứng/bất đối xứng.
3. **`kid` là gợi ý tra cứu, không phải đường dẫn tùy ý:** chỉ chọn khóa trong tập đã đăng ký cho đúng issuer hoặc đúng người nhận; giới hạn việc tải lại JWKS để tránh bị lạm dụng.
4. **Quyền tối thiểu:** chỉ AS có quyền dùng khóa ký riêng; chỉ dịch vụ nhận được giải mã mới có private decryption key. Cân nhắc KMS/HSM tùy yêu cầu.
5. **Luân chuyển khóa:** duy trì giai đoạn giao thoa hợp lý khi token cũ còn hiệu lực; có phương án thu hồi khóa và phản ứng nếu khóa bị lộ.
6. **Không lộ dữ liệu nhạy cảm:** tuyệt đối không ghi private key, shared secret, token thật hoặc plaintext JWE vào log/trace/ticket hỗ trợ.

JWKS là cơ chế công bố **khóa công khai** để xác minh JWS; không đưa khóa riêng vào JWKS công khai. Việc có thể tải một public key từ internet **không có nghĩa** API nên tin issuer sử dụng khóa đó.

### Key rotation có làm token cũ mất hiệu lực ngay?

Không mặc định. Với JWS, API có thể vẫn xác minh token cũ nếu khóa xác minh cũ còn trong tập khóa tin cậy. Với JWE, token đã mã hóa bằng public key cũ cần private key tương ứng để giải mã, trừ khi hệ thống chủ động vô hiệu hóa. Xóa khóa ngay có thể làm token hợp lệ không dùng được; giữ khóa quá lâu có thể kéo dài rủi ro. Phải phối hợp **TTL, trạng thái thu hồi, kỳ luân chuyển khóa và sự cố khóa** theo yêu cầu hệ thống.

## 8. Kiểm tra signed/encrypted access token tại API

Dù token đã được ký, mã hóa hay lồng nhau, Resource Server vẫn cần nhiều bước trước khi cấp quyền.

~~~mermaid
flowchart TD
    A["Nhận access token"] --> B{"Đúng định dạng/loại token theo profile?"}
    B -- Không --> X["401 / từ chối"]
    B -- Có --> C{"Mã hóa? Cần giải mã?"}
    C -- Có --> D["Xác thực & giải mã JWE bằng khóa được phép"]
    D --> E{"Có JWS bên trong theo chính sách?"}
    E -- Có --> F["Xác minh JWS với khóa ký của issuer tin cậy"]
    E -- Không --> G["Kiểm tra cơ chế xác thực nguồn do profile quy định"]
    C -- Không --> F
    F --> H{"iss / aud / exp / nbf / mục đích / trạng thái đúng?"}
    G --> H
    H -- Không --> X
    H -- Có --> I{"scope và quyền với tài nguyên đủ?"}
    I -- Không --> Y["403 / từ chối"]
    I -- Có --> Z["Cho phép thao tác hợp lệ"]
~~~

*Sơ đồ mô tả các nhánh khả dĩ; mỗi Resource Server phải định nghĩa trước những dạng token được chấp nhận. Khi chính sách đòi nested JWT, không cho phép bỏ qua xác minh JWS bên trong hoặc chuyển sang nhánh yếu hơn.*

### Claims là dữ liệu phân quyền chỉ sau xác minh

Các điều kiện thường gặp:

| Thuộc tính | Kiểm tra tại Resource Server |
|---|---|
| **Nguồn phát hành / `iss`** | Có đúng issuer được cấu hình tin cậy cho loại token này? |
| **Đối tượng nhận / `aud`** | API hiện tại có nằm trong audience đã cấp không? |
| **Mục đích / token type** | Đây có thực sự là **access token** dành cho API này, không phải ID/refresh token? |
| **Hiệu lực / `exp`, `nbf`** | Đang trong khoảng hiệu lực và trạng thái phiên/thu hồi đáp ứng chính sách? |
| **`scope` / permission** | Token có được cấp phạm vi thao tác tương ứng không? |
| **`sub`, client, tenant, resource** | Chủ thể có quyền làm hành động này trên bản ghi này không? |
| **Proof ràng buộc người gửi, nếu cần** | DPoP/mTLS proof có khớp request và token theo cấu hình? |

Ví dụ, token được ký và mã hóa hoàn hảo, nhưng `aud=billing-api`, thì `orders-api` vẫn phải **từ chối**. Token có `scope=orders:read` cũng không tự cho phép đọc đơn thuộc tenant khác. **Mật mã chứng minh dữ liệu và nguồn theo mô hình đã chọn; authorization quyết định thao tác được phép.**

Mã giả:

~~~text
handle(GET /orders/{id}, request):
    token = parseBearerHeader(request)
    if token absent or malformed:
        return 401

    claims = verifyTokenAccordingToTrustedPolicy(token)
        # Nếu chỉ cho signed JWT: xác minh JWS
        # Nếu chỉ cho nested JWT: giải mã JWE và xác minh JWS bên trong
        # Với opaque token: introspection/tra cứu theo hợp đồng khác
    if claims invalid, expired, wrong issuer, audience or token type:
        return 401

    if senderProofRequired and not verifySenderProof(request, token):
        return 401
    if "orders:read" not in claims.scopes:
        return 403

    order = loadOrder(id)
    if order missing:
        return 404
    if not canReadOrder(claims.subject, claims.tenant, order):
        return 403  # hoặc 404 theo chính sách che giấu tài nguyên

    return 200 with authorized fields
~~~

Đối với **401 Unauthorized**, API có thể trả `WWW-Authenticate: Bearer` với thông tin phù hợp khi token thiếu hoặc không hợp lệ. Với token hợp lệ nhưng không đủ scope, **403 Forbidden** thường phù hợp, có thể kèm lỗi `insufficient_scope` theo quy tắc bearer token. Không trả về plaintext token hoặc chi tiết khóa trong response.

## 9. Các sai lầm cần tránh

| Sai lầm | Vì sao nguy hiểm? | Cách làm phù hợp |
|---|---|---|
| “JWS có chữ ký nên payload là bí mật.” | Base64URL không bảo vệ bí mật. | Không chứa dữ liệu nhạy cảm không cần thiết; cân nhắc JWE nếu phải bảo mật claims. |
| “JWE giải mã được là token đáng tin.” | Kẻ khác có thể mã hóa cho khóa công khai của người nhận. | Xác thực nguồn issuer bằng cơ chế được thiết kế, ví dụ JWS bên trong. |
| “Đã có JWE/JWS thì không cần HTTPS.” | Kênh HTTP còn nguy cơ nghe lén metadata, chiếm token, tấn công trên đường truyền. | Luôn dùng TLS cùng bảo vệ token ở cấp đối tượng khi cần. |
| “Chữ ký `alg=none` vẫn là token JWT bình thường.” | Chấp nhận dạng không bảo vệ khi policy yêu cầu chữ ký có thể dẫn tới giả mạo. | Chỉ chấp nhận thuật toán/profile được cấu hình rõ ràng. |
| “`kid` cho phép chọn bất kỳ file hoặc URL.” | Dễ bị dẫn đến khóa của attacker hoặc lỗi truy cập tài nguyên. | Chỉ tra trong tập khóa tin cậy, kiểm soát nguồn và quyền. |
| “Token JWE mã hóa cho API A thì API B cũng dùng được.” | Sai người nhận và có thể mở rộng ranh giới quyền. | Gắn audience và khóa nhận với API đích; kiểm tra `aud` sau xác minh. |
| “Nếu xác minh nested JWT lỗi thì thử coi JWE là đủ.” | Tạo **downgrade** sang cấu hình yếu hơn. | Từ chối khi một lớp bảo vệ bắt buộc thất bại. |
| “JWT ký hoặc mã hóa tự chống replay.” | Bearer token vẫn dùng lại được nguyên giá trị. | Bảo vệ token, TTL/scope hẹp, thu hồi và DPoP/mTLS khi cần. |
| “Một access token có thể chuyển tiếp đến mọi microservice.” | Đánh mất ranh giới audience, dễ bị token substitution. | Cấp token đúng dịch vụ hoặc dùng token exchange được kiểm soát. |
| “Thấy `scope=admin` là cho phép mọi dữ liệu.” | Scope không thay kiểm tra quyền trên tài nguyên. | Kiểm tra owner, tenant, permission và nghiệp vụ tại API. |

### Tấn công phát lại đối với JWE

Một access token **bearer** được mã hóa có thể rất khó đọc và khó sửa, nhưng kẻ đánh cắp **không cần giải mã** để trình token:

~~~text
Client hợp lệ  --(JWE access token còn hạn)--> Orders API
        |
        +-- token bị sao chép từ log hoặc thiết bị
                       |
Attacker ----------(cùng JWE ciphertext)----> Orders API
~~~

Nếu API chỉ kiểm tra rằng token hợp lệ và chưa bị thu hồi, request từ attacker vẫn có thể được chấp nhận trong phạm vi quyền token. Muốn giảm khả năng dùng lại **chính bản sao token**, cân nhắc cơ chế ràng buộc người gửi như **DPoP (RFC 9449)** hoặc **mTLS certificate-bound access token (RFC 8705)**, cùng bảo vệ khóa tương ứng. `jti` nếu có cũng không tự phát hiện replay nếu không có cơ chế theo dõi phù hợp.

## 10. Lựa chọn thiết kế trong OAuth 2.0/OIDC

Hãy bắt đầu từ **mô hình đe dọa** và thỏa thuận giữa Authorization Server với Resource Server, thay vì chọn JWE chỉ vì cảm giác “mã hóa chắc chắn an toàn hơn”.

### Trường hợp A — Access token JWT ký cho nhiều Resource Server

Nếu API cần xác minh cục bộ, có kết nối tin cậy với issuer và token không chứa claims bí mật, **JWS dùng chữ ký bất đối xứng** có thể là lựa chọn phù hợp. AS giữ private signing key; Resource Servers xác minh qua public key đáng tin. Mỗi API vẫn kiểm tra audience, scope, hạn dùng, trạng thái và quyền tài nguyên.

### Trường hợp B — Claims phải được giữ kín đối với thành phần trung gian

Nếu có lý do bảo mật để giấu claims khỏi client hoặc gateway chuyển tiếp, có thể sử dụng **JWE mã hóa cho API đích**. Nếu API phải biết chắc issuer đã ký claims, có thể dùng **nested JWT ký rồi mã hóa**. Đánh đổi là quản lý khóa giải mã, chi phí xử lý, độ dài token, khó kiểm tra bằng tay và mô hình vận hành phức tạp hơn.

### Trường hợp C — API muốn quản lý trạng thái token tập trung

**Opaque access token** và introspection có thể phù hợp khi trạng thái thu hồi cần được tra cứu ở nguồn phát hành. Opaque token không buộc phải là JWT mã hóa; API nhận chuỗi cần kiểm tra qua cơ chế tin cậy. Dù vậy, cache introspection vẫn tạo độ trễ thu hồi và việc tra cứu vẫn phải kiểm tra audience, scope.

### Trường hợp D — OIDC ID token

**ID token** là JWT dùng để thông báo kết quả xác thực người dùng **cho client**, thường được ký và có thể được mã hóa theo cấu hình/profile OIDC. Việc ký/mã hóa không làm nó trở thành access token; Resource Server không được chấp nhận ID token thay access token chỉ vì cùng định dạng JWT.

### Trường hợp E — Refresh token

**Refresh token** được client dùng ở **token endpoint** để xin access token mới, không phải để gọi API nghiệp vụ. Nơi phát hành có thể dùng chuỗi opaque hoặc cơ chế biểu diễn riêng. Cần bảo vệ thời hạn, nơi lưu, rotation/ràng buộc người gửi và khả năng thu hồi, nhưng không nên suy diễn rằng refresh token nhất thiết là JWS hoặc JWE.

## 11. Tình huống tự kiểm tra

**Tình huống 1.** Một JWS có payload `{"role":"admin"}`, nhưng API không xác minh chữ ký trước khi đọc role. Token có an toàn không?

**Giải thích:** Không. Attacker có thể tự mã hóa payload bất kỳ. API phải xác minh chữ ký, issuer, audience và các điều kiện khác trước khi dùng claims.

**Tình huống 2.** Một JWE được mã hóa bằng public key của `orders-api`, API giải mã thành công JSON `{"scope":"orders:write"}` nhưng không có bằng chứng issuer đáng tin cậy. Có cấp quyền ghi không?

**Giải thích:** Không. Việc giải mã không chứng minh ai đã tạo token. Nếu hợp đồng yêu cầu AS ký, phải xác minh JWS hoặc nguồn phát hành bằng cơ chế đủ tin cậy trước khi phân quyền.

**Tình huống 3.** Một nested JWT giải mã được, JWS bên trong có chữ ký hợp lệ, nhưng `aud=billing-api`. `orders-api` có được chấp nhận không?

**Giải thích:** Không. Token không được cấp cho API này; chữ ký và mã hóa không thay được audience.

**Tình huống 4.** JWS chứa `sub=user-123` và `scope=orders:read`. Order được yêu cầu thuộc `tenant-b`, trong khi principal thuộc `tenant-a`. API có được trả dữ liệu không?

**Giải thích:** Không, trừ khi có cơ chế ủy quyền liên tenant hợp lệ và được kiểm tra rõ. Scope là một lớp, không thay object-level authorization.

**Tình huống 5.** Một JWE bearer token bị sao chép nguyên ciphertext nhưng vẫn còn hạn. Kẻ tấn công có thể gửi lại không?

**Giải thích:** Có thể. Mã hóa làm khó đọc nội dung, không ngăn việc trình lại nguyên token. Cần bảo vệ token, thu hồi, TTL phù hợp và cơ chế sender-constrained khi rủi ro yêu cầu.

**Tình huống 6.** Do luân chuyển khóa, API không tìm thấy `kid` trong JWKS đã cấu hình. API có nên tải khóa từ một URL lạ được cung cấp trong header JWS để tiếp tục xác minh?

**Giải thích:** Không. Có thể làm mới JWKS từ endpoint **đã cấu hình tin cậy** trong giới hạn được phép; nếu vẫn không xác minh được thì từ chối. Không tự mở rộng tập nguồn khóa theo gợi ý không đáng tin.

## Checklist trước khi đưa vào production

1. **Xác định yêu cầu:** cần chứng minh issuer, giữ bí mật claims, hay cả hai? Access token có thực sự cần chứa dữ liệu nhạy cảm không?
2. **Chọn profile cụ thể:** quy định signed JWS, encrypted JWE, nested JWT hoặc opaque token cho từng API; không nhận token sai loại hoặc tự hạ cấp khi lớp bảo vệ lỗi.
3. **Giới hạn JOSE:** allowlist `alg`/`enc`, kiểm tra cấu trúc/độ dài đầu vào, `kid`/nguồn khóa tin cậy, bảo vệ xử lý lỗi và tài nguyên giải mã; hạn chế giải nén nếu profile cho phép `zip`.
4. **Phân tách khóa:** private signing key thuộc issuer; private decryption key thuộc đúng người nhận; chỉ công bố public keys được phép và quản lý rotation/compromise.
5. **Xác minh claims:** sau bước mật mã, bắt buộc đối chiếu issuer, audience, thời hạn, token purpose, scope, principal và tenant theo hợp đồng.
6. **Phân quyền ở Resource Server:** kiểm tra action, object ownership, role/permission và trạng thái tài nguyên ở mỗi request; không tin frontend.
7. **Bảo vệ vòng đời:** HTTPS, không đưa token vào URL/log, lưu trữ phù hợp, TTL, refresh rotation, thu hồi và kiểm tra quyền thay đổi.
8. **Chống sử dụng lại:** hiểu JWT ký/mã hóa không tự chống replay; đánh giá DPoP/mTLS và bảo vệ khóa nếu cần ràng buộc người gửi.
9. **Kiểm thử tình huống từ chối:** chữ ký sai, tag JWE sai, issuer không tin, algorithm không cho phép, audience sai, token hết hạn, thiếu scope, sai tenant, token sai loại và yêu cầu bị phát lại.

## Ghi nhớ

**Signed token** (thường là JWS) bảo vệ **toàn vẹn** và có thể giúp xác thực **nguồn phát hành** khi xác minh bằng khóa tin cậy; **encrypted token** (thường là JWE) bảo vệ **bí mật** và tính toàn vẹn của plaintext mã hóa. Khi cần cả hai thuộc tính với bằng chứng issuer rõ ràng, có thể sử dụng **nested JWT ký rồi mã hóa**. Cả chữ ký lẫn mã hóa **không tự xác minh audience, scope, quyền trên tài nguyên hay ngăn bearer token bị phát lại**. Quyết định cuối thuộc về Resource Server và chính sách vòng đời token.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
