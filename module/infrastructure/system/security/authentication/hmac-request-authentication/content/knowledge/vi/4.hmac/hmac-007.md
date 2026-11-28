# HMAC và encryption

Trong hệ thống HTTP API, **HMAC** và **encryption (mã hóa)** thường xuất hiện cùng nhau nhưng có mục tiêu khác nhau. HMAC giúp bên nhận kiểm tra rằng các byte được ký không bị sửa và người tạo chữ ký có quyền truy cập shared secret. Encryption giúp người không có khóa giải mã **không đọc được nội dung**. Nếu gộp hai khái niệm này thành một, thiết kế có thể có chữ ký hợp lệ nhưng lộ thông tin, hoặc có dữ liệu mã hóa nhưng lại chấp nhận request giả mạo và replay.

Bài học thuộc chương **HMAC** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Phạm vi là thiết kế xác thực HTTP request bằng **HMAC với shared secret và canonical request** (method, URI, header và/hoặc body theo hợp đồng ký); hiểu quan hệ của cơ chế này với mã hóa dữ liệu, TLS, xác minh chữ ký, timestamp/nonce chống replay, key rotation, proxy/gateway và phân quyền.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **authentication/integrity** do HMAC cung cấp với **confidentiality** do encryption cung cấp.
2. Giải thích vì sao mã hóa đơn thuần không đủ xác thực request và HMAC đơn thuần không giữ bí mật payload.
3. Phân biệt mã hóa đối xứng, AEAD (ví dụ AES-GCM), TLS và HMAC ở tầng ứng dụng.
4. Thiết kế HTTP request vừa có dữ liệu được mã hóa vừa được xác thực HMAC; quy định rõ dữ liệu nào được ký, mã hóa và được dùng làm AAD.
5. Xử lý đúng ba loại giá trị dễ nhầm: **HMAC key**, **encryption key**, và **nonce/IV**; đồng thời chống replay bằng timestamp/request nonce.
6. Nhận diện rủi ro tại API gateway, proxy, hệ thống quản lý khóa, key rotation và quá trình phân quyền sau xác thực.
7. Viết kiểm thử để phát hiện sửa dữ liệu, gửi lại request, thay metadata, dùng sai key và lỗi giải mã.

## 2. HMAC làm gì, encryption làm gì?

### 2.1. HMAC: kiểm tra tính toàn vẹn và bằng chứng sở hữu shared secret

HMAC là một **message authentication code** dùng khóa bí mật. Bên tạo chữ ký và bên xác minh phải cùng biết khóa HMAC, ký hiệu `K_mac`.

~~~text
tag = HMAC-SHA256(K_mac, canonicalRequestBytes)
~~~

Server tạo lại `canonicalRequestBytes` đúng theo hợp đồng, tính HMAC và so sánh với `tag` do client gửi.

Nếu khóa được bảo vệ và hợp đồng ký đúng, HMAC giúp:

- **Phát hiện thay đổi** các byte đã được đưa vào canonical request.
- Xác minh người tạo chữ ký **có khả năng dùng `K_mac`**.
- Gắn thông điệp đã ký với một `keyId`/principal được server quản lý, khi hệ thống kiểm tra đúng key record.

HMAC **không che giấu nội dung**. Nếu HTTP body là JSON rõ, người quan sát được kết nối không mã hóa vẫn đọc được body dù `X-Signature` hợp lệ.

HMAC cũng **không tự ngăn replay**: ai đó có được request đã ký có thể phát lại nguyên vẹn nếu hệ thống không kiểm tra timestamp/nonce. Nó **không tự cấp quyền** cho principal sử dụng phương thức hoặc tài nguyên nào.

### 2.2. Encryption: bảo vệ nội dung khỏi người không có khóa giải mã

Với mã hóa đối xứng, bên gửi và nhận có một khóa mã hóa `K_enc`:

~~~text
ciphertext = Encrypt(K_enc, plaintext, nonceOrIV, ...)
plaintext  = Decrypt(K_enc, ciphertext, nonceOrIV, ...)
~~~

Mục tiêu chính là **confidentiality**: bên không có khóa không đọc được plaintext từ ciphertext (giả sử thuật toán và triển khai an toàn).

Tuy nhiên, không phải **mọi chế độ mã hóa** đều xác thực ciphertext. Ví dụ, AES-CBC dùng riêng mà không có MAC thích hợp không đem lại cơ chế kiểm tra toàn vẹn đáng tin cậy và có thể chịu các kiểu tấn công sửa ciphertext. Nếu cần cả bí mật và toàn vẹn, ưu tiên **authenticated encryption with associated data (AEAD)** như **AES-GCM** hoặc **ChaCha20-Poly1305**.

### 2.3. Bảng so sánh các lớp bảo vệ

| Cơ chế | Bí mật nội dung | Toàn vẹn/xác thực dữ liệu | Phạm vi bảo vệ | Điều chưa tự giải quyết |
| --- | --- | --- | --- | --- |
| HMAC-SHA256 | Không | Có, cho các byte được ký và khóa chia sẻ | Canonical request theo hợp đồng ứng dụng | Replay, phân quyền, mã hóa dữ liệu |
| Mã hóa không xác thực | Có, nếu dùng đúng | Không bảo đảm | Plaintext được mã hóa | Sửa ciphertext, xác thực nguồn, replay |
| AEAD như AES-GCM | Có | Có, cho ciphertext/associated data theo một khóa | Payload và AAD được quy định | Caller là ai, quyền truy cập, replay ứng dụng |
| HTTPS/TLS hiện đại | Có trên kết nối được bảo vệ | Có ở tầng kết nối | Dữ liệu truyền giữa hai endpoint TLS | Nội dung sau TLS termination, quyền nghiệp vụ |
| HMAC + TLS | Có nhờ TLS | HMAC ở tầng ứng dụng và bảo vệ kết nối nhờ TLS | Canonical request + đường truyền | Replay nếu không có freshness; phân quyền |
| HMAC + mã hóa payload AEAD + TLS | Có trên đường truyền và đối với người không có khóa payload | HMAC cho request; AEAD cho payload và AAD; TLS cho kết nối | Nhiều ranh giới độc lập | Quản lý khóa, replay, authorization, hành vi gateway |

**Không đánh đồng “payload được mã hóa” với “request được xác thực”.** Server có thể giải mã thành công một ciphertext hợp lệ nhưng vẫn chưa biết người gọi có quyền dùng endpoint đó không. Ngược lại, server có thể xác minh HMAC thành công trên JSON thuần nhưng không che được JSON trước một kẻ nghe lén khi truyền qua HTTP không mã hóa.

## 3. Minh họa bằng ba request

### 3.1. Chỉ HMAC, payload còn ở dạng rõ

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a:mac-v2
X-Timestamp: 1790000000
X-Nonce: 4a0b876ee2ba539dbec96ab30f6380a7
X-Signature: <hmac-base64url>

{"account":"acc-01","amount":125000}
~~~

Nếu canonical request ký method, URI, timestamp, nonce, content type và **SHA-256 của raw body bytes**, người sửa body sẽ làm chữ ký sai. Tuy nhiên, `account` và `amount` là plaintext. **HMAC không biến chúng thành ciphertext.**

### 3.2. Chỉ mã hóa, chưa có xác thực request

~~~http
POST /v1/payments HTTP/1.1
Content-Type: application/json

{
  "enc": "A256GCM",
  "encKeyId": "partner-a:enc-v2",
  "iv": "<base64url-iv>",
  "ciphertext": "<base64url-ciphertext-and-tag>"
}
~~~

Nếu thật sự dùng AES-GCM đúng cách, ciphertext và AAD có kiểm tra tag, bên không có khóa khó đọc hoặc sửa payload hợp lệ. Nhưng việc có thể gửi một envelope mã hóa tới API **không đồng nghĩa** có quyền gọi `POST /v1/payments`. Server vẫn cần kiểm tra client/principal, action, tenant và tài nguyên. Đồng thời, envelope hợp lệ vẫn có thể bị **gửi lại** nếu không có cơ chế freshness/replay ở giao thức.

### 3.3. Payload AEAD cộng với HMAC request

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a:mac-v2
X-Timestamp: 1790000000
X-Nonce: 4a0b876ee2ba539dbec96ab30f6380a7
X-Signature: <hmac-over-canonical-request>

{
  "enc": "A256GCM",
  "encKeyId": "partner-a:enc-v2",
  "iv": "<base64url-iv>",
  "ciphertext": "<base64url-ciphertext-and-tag>"
}
~~~

Ở thiết kế minh họa này:

- **AES-GCM** bảo vệ nội dung thanh toán bên trong ciphertext và xác thực ciphertext/AAD.
- **HMAC** bảo vệ các trường của outer HTTP request theo hợp đồng ký, ví dụ method, target URI, timestamp, request nonce và hash của **byte body chứa envelope đã mã hóa**.
- **TLS** bảo vệ request khi truyền giữa các endpoint TLS.
- **Authorization** quyết định principal được phép thanh toán trên tài nguyên/tenant nào.
- **Request nonce + timestamp** giới hạn việc phát lại signed request; **idempotency** xử lý nguy cơ lặp tác vụ thanh toán.

Không phải mọi API đều cần cả HMAC và AEAD. Nếu hệ thống chỉ cần tính bí mật trên đường truyền và xác thực caller, **TLS + HMAC + kiểm tra quyền** có thể đáp ứng. Mã hóa payload thêm một lớp chỉ nên dùng khi có yêu cầu cụ thể như bảo vệ dữ liệu qua một gateway không được phép xem plaintext hoặc bảo vệ dữ liệu khi lưu/trung chuyển.

## 4. TLS cũng là mã hóa, nhưng có ranh giới riêng

HTTPS sử dụng TLS để bảo vệ dữ liệu **trong một kết nối**. Với TLS 1.3, nội dung ứng dụng được bảo vệ bằng cơ chế authenticated encryption; trình duyệt hoặc HTTP client thường xác minh certificate của server theo chính sách tin cậy.

~~~mermaid
flowchart LR
    C[Client] -->|HTTPS / TLS #1| G[API Gateway]
    G -->|HTTPS / TLS #2| B[Backend API]
    B --> DB[(Database)]
~~~

Nếu gateway **terminate TLS**, gateway có thể đọc HTTP body ở dạng rõ; TLS ở chặng client–gateway không còn bảo vệ dữ liệu bên trong gateway. Gateway có thể mở một kết nối TLS khác tới backend, nhưng đây là **hai kết nối với hai ranh giới tin cậy**.

HMAC ở tầng ứng dụng có thể giúp backend kiểm tra sự nhất quán của signed request sau khi đi qua gateway, **nếu hợp đồng canonicalization và proxy rewrite được thiết kế thống nhất**. Mã hóa payload AEAD bằng khóa mà gateway không có có thể giữ plaintext khỏi gateway ngay cả khi gateway kết thúc TLS. Ngược lại, nếu gateway cũng giữ khóa giải mã, lớp payload encryption không tạo ra ranh giới bí mật với gateway.

### 4.1. Khi nào dùng cả HMAC và TLS?

Dùng cả hai thường hợp lý khi:

- Giao tiếp **server-to-server** cần xác minh shared-secret credential ở tầng ứng dụng.
- API có thể đi qua nhiều gateway/proxy, nhưng vẫn muốn ràng buộc một số trường request với credential do backend quản lý.
- Hệ thống muốn ràng buộc body, method, URI, header và thời gian thành một signed request, độc lập với phiên TLS đã tạo.

Tuy vậy, **HMAC không thay thế TLS**: nó không bảo mật nội dung, không xác thực certificate/endpoint của kênh truyền và không tự ngăn kẻ khác đọc các header hay body nhạy cảm. HTTPS vẫn là yêu cầu cơ bản cho HTTP API.

### 4.2. TLS và replay ở cấp ứng dụng

Một kết nối TLS an toàn không bảo đảm không ai **gửi lại một HTTP operation hợp lệ** bằng credential của chính họ hoặc request đã bị lộ ở một thành phần tin cậy bị xâm phạm. Ứng dụng vẫn cần timestamp, nonce và idempotency nếu thao tác có nguy cơ thực thi lặp.

Đặc biệt, những hệ thống có sử dụng TLS 1.3 **early data (0-RTT)** phải đánh giá nguy cơ replay ở lớp đó; không mặc nhiên cho các thao tác thay đổi trạng thái chạy qua early data nếu chưa xử lý tính an toàn.

## 5. Encryption cần tính toàn vẹn: vì sao nên ưu tiên AEAD?

### 5.1. Tránh nhầm “AES” là một giao thức đủ dùng

“AES” là thuật toán mã khối, không phải một định dạng HTTP payload hoàn chỉnh. Cách sử dụng AES còn phụ thuộc mode, IV/nonce, padding và cơ chế kiểm tra toàn vẹn.

Ví dụ cần tránh trong một thiết kế mới:

- **AES/ECB**: các khối plaintext giống nhau tạo mẫu ciphertext lặp lại; không phù hợp để mã hóa payload.
- **AES/CBC chỉ với padding**: có tính bí mật trong một số điều kiện nhưng không tự cung cấp xác thực; xử lý lỗi giải mã sai có thể dẫn tới padding oracle.
- **AES/CTR không MAC**: ciphertext có thể bị sửa có chủ đích; không có tag xác thực.
- **Tự gắn HMAC sau khi mã hóa nhưng không quy định rõ IV, metadata, khóa và thứ tự xác minh**: dễ tạo lỗ hổng do thiết kế giao thức.

Lựa chọn điển hình cho một hệ thống mới là **AEAD**: AES-GCM hoặc ChaCha20-Poly1305, với thư viện chuẩn và quy tắc nonce/key được xác định.

### 5.2. AEAD bảo vệ ciphertext và associated data

Với AES-GCM:

~~~text
(ciphertext, tag) = AES-GCM-Encrypt(K_enc, IV, plaintext, AAD)
plaintext         = AES-GCM-Decrypt(K_enc, IV, ciphertext, tag, AAD)
~~~

AEAD cung cấp tính bí mật cho plaintext và xác thực sự toàn vẹn của ciphertext lẫn **AAD (additional authenticated data)**. AAD không được mã hóa nhưng vẫn được ràng buộc bằng tag.

Ví dụ AAD có thể là:

~~~text
AEAD-PAYLOAD-V1
audience:payments-api
method:POST
path:/v1/payments
enc-key-id:partner-a:enc-v2
~~~

AAD có thể gắn ciphertext với endpoint, service audience, phiên bản định dạng và key identifier, giúp giảm nguy cơ ciphertext hợp lệ bị đem dùng ở bối cảnh khác. Cả hai phía phải quy định byte AAD chính xác; nếu một phía thay đổi khoảng trắng hoặc encoding, giải mã xác thực sẽ thất bại.

**Lưu ý:** Tag hợp lệ chứng minh ciphertext được tạo bằng một khóa AEAD tương ứng với AAD; nó **không tự xác minh quyền người dùng**, **không chống replay** và không chứng minh người dùng cụ thể nếu nhiều bên cùng giữ `K_enc`.

### 5.3. Nonce/IV của AES-GCM không phải nonce chống replay

Có hai loại nonce với mục tiêu rất khác nhau:

| Giá trị | Nơi dùng | Bất biến |
| --- | --- | --- |
| `iv` / nonce của AES-GCM | Bước mã hóa/giải mã với `K_enc` | **Không bao giờ được lặp với cùng khóa mã hóa** |
| `X-Nonce` của HTTP HMAC request | Kho replay protection của ứng dụng | Request mới phải dùng nonce mới; server phải ghi nhớ và từ chối nonce đã dùng |
| `X-Timestamp` | Kiểm tra freshness của signed request | Phải nằm trong cửa sổ cho phép theo đồng hồ và contract |

Với AES-GCM, một IV 96 bit là lựa chọn thường dùng. Có thể tạo ngẫu nhiên bằng `SecureRandom` khi quy mô và giới hạn sử dụng phù hợp; với hệ thống tạo khối lượng bản tin lớn cần thiết kế tránh trùng nonce chắc chắn hơn (ví dụ bộ đếm duy nhất theo khóa) và quản lý vòng đời khóa. **Lặp IV dưới cùng một khóa AES-GCM có thể phá nghiêm trọng tính bí mật và xác thực**, không phải chỉ tạo ra hai request giống nhau.

Trong khi đó, request nonce của HMAC có thể được sinh ngẫu nhiên đủ mạnh, ví dụ 128 bit, và được server ghi nhận atomically. Không gộp hai nonce thành một chỉ vì cùng tên “nonce”; chúng thuộc hai giao thức, khóa và quy tắc vòng đời khác nhau.

## 6. HMAC và mã hóa kết hợp theo thứ tự nào?

Đôi khi kiến trúc không sử dụng AEAD mà kết hợp một primitive mã hóa với một MAC riêng. Thứ tự kết hợp rất quan trọng:

| Mẫu | Cách thức | Nhận xét |
| --- | --- | --- |
| Encrypt-then-MAC (EtM) | Mã hóa rồi MAC trên IV, ciphertext và metadata cần bảo vệ | Là phương pháp kết hợp có cơ sở bảo mật khi thiết kế chuẩn, dùng **khóa tách biệt** và xác minh MAC trước khi giải mã |
| MAC-then-Encrypt | Tính MAC trên plaintext rồi mã hóa cả plaintext và MAC | Có thể gặp rủi ro trong một số protocol/mode; không nên tự thiết kế |
| Encrypt-and-MAC | Mã hóa plaintext và MAC riêng trên plaintext | Có thể làm lộ thông tin hoặc tạo sai lệch xác minh tùy cấu trúc; không mặc định an toàn |
| AEAD | Một API mã hóa xác thực ciphertext và AAD | **Ưu tiên cho thiết kế mới** để giảm lỗi khi tự kết hợp primitive |

Nếu phải dùng EtM theo một chuẩn đã được xem xét, cần:

- `K_enc` và `K_mac` **khác nhau**, lý tưởng sinh độc lập hoặc suy dẫn từ key material bằng KDF như HKDF có domain separation rõ.
- MAC bao phủ **IV, ciphertext, key/version ID, algorithm, audience và metadata ảnh hưởng đến xử lý**, với encoding không nhập nhằng.
- Verifier so sánh tag trước bước giải mã; không để các lỗi giải mã khác nhau tạo oracle ra bên ngoài.
- Không tự tạo “format mã hóa an toàn” chỉ bằng việc ghép nối byte không kèm độ dài/phiên bản.

Trong thực hành HTTP request authentication, hai lớp HMAC và AEAD thường có mục đích khác nhau: **AEAD bảo vệ payload**, còn **HMAC chứng thực outer HTTP request** với key ID và canonical request đã thống nhất. Cấu trúc này vẫn cần quản lý khóa và thứ tự xử lý đúng; **không bắt buộc thêm HMAC** chỉ để “tăng an toàn” cho AES-GCM nếu đã có AEAD đủ cho yêu cầu payload.

## 7. Thiết kế HTTP request vừa ký HMAC vừa mã hóa payload

Giả sử hệ thống đối tác thanh toán gửi yêu cầu tới `payments-api`. Gateway cần định tuyến request theo path nhưng không được đọc thông tin tài khoản trong body. Backend sở hữu cả khóa xác minh HMAC và khóa giải mã payload.

### 7.1. Phân loại dữ liệu

| Trường | Ai cần đọc? | Giải pháp minh họa |
| --- | --- | --- |
| HTTP method và path | Gateway, backend | Để rõ; ràng buộc vào canonical HMAC |
| Host/audience | Gateway, backend | Để rõ phần định tuyến; ràng buộc service audience ổn định vào HMAC/AAD |
| `X-Key-Id` | Verifier | Để rõ; là định danh khóa HMAC và được đưa vào canonical HMAC |
| `X-Timestamp` / `X-Nonce` | Verifier | Để rõ; được ký HMAC và kiểm tra freshness/replay |
| `encKeyId` | Backend giải mã | Để trong envelope; được HMAC bảo vệ qua body hash; kiểm tra chính sách chọn khóa |
| `iv` và `ciphertext` | Backend; gateway có thể chuyển tiếp | Để trong envelope; `iv` không bí mật nhưng phải có đúng format |
| `accountNo`, `amount` trong plaintext | Backend nghiệp vụ | Mã hóa bằng AEAD; giải mã sau xác thực thích hợp |
| Principal/tenant/scope | Verifier và authorization | Lấy từ key record/policy phía server; không tin header do client tự khai |

### 7.2. Envelope mã hóa minh họa

Backend nhận một JSON envelope:

~~~json
{
  "version": "payload-v1",
  "enc": "A256GCM",
  "encKeyId": "partner-a:enc-v2",
  "iv": "<base64url-12-byte-iv>",
  "ciphertext": "<base64url-encrypted-bytes-and-gcm-tag>"
}
~~~

Ở đây `ciphertext` là kết quả chứa ciphertext và tag theo cách API Java/AEAD quy ước. Mọi bên cần thống nhất cách đóng gói tag, IV, mã hóa Base64URL và payload bytes. Giá trị giữa `<...>` chỉ là placeholder, không phải ciphertext hợp lệ.

Client có thể tuần tự:

1. Tạo plaintext JSON theo định dạng nghiệp vụ và encode UTF-8.
2. Lấy encryption key từ cấu hình an toàn; tạo IV **không trùng** với khóa đó.
3. Dùng AES-GCM cùng AAD đã định nghĩa để mã hóa plaintext thành ciphertext + tag.
4. Serialize envelope một lần thành raw UTF-8 bytes của HTTP body.
5. Tính `SHA-256(rawBodyBytes)` và tạo canonical HMAC request gồm method, URI, header cần bảo vệ, `keyId`, timestamp, request nonce, audience và body hash.
6. Tính `HMAC-SHA256(K_mac, canonicalRequestBytes)`, encode chữ ký theo đúng protocol, đặt vào `X-Signature`.
7. Gửi request qua **HTTPS**.

Bước 4 và 5 đặc biệt quan trọng: nếu client ký body được serialize lần thứ nhất nhưng HTTP library gửi bản serialize lần thứ hai khác byte, chữ ký có thể sai dù JSON tương đương về dữ liệu.

### 7.3. Canonical request minh họa

Giả sử contract chọn UTF-8 và LF, query đã chuẩn hóa theo quy tắc xác định, body hash lowercase hex của raw bytes:

~~~text
HMAC-REQUEST-V1
POST
/v1/payments
audience:payments-api
content-type:application/json
x-key-id:partner-a:mac-v2
x-timestamp:1790000000
x-nonce:4a0b876ee2ba539dbec96ab30f6380a7
body-sha256:<64-hex-digest-of-envelope-body>
~~~

Cả hai phía phải thỏa thuận **thứ tự dòng, dấu phân cách, encoding, đường dẫn percent-encoded, header lặp, xử lý giá trị rỗng và dấu xuống dòng cuối**. `<64-hex-digest-of-envelope-body>` phải được thay bằng digest thật. Các trường trong body như `iv` và `encKeyId` được HMAC bảo vệ gián tiếp thông qua **body hash**.

Nếu API cần ràng buộc ciphertext với một tài nguyên, ví dụ `/v1/payments/tx-123`, cần đưa path/audience vào canonical HMAC và/hoặc AAD theo thiết kế đã được xem xét. Không để verifier xác thực một biểu diễn path trong khi backend xử lý theo path khác do proxy decode hoặc rewrite.

### 7.4. Thứ tự xử lý ở backend

Một phương án có ranh giới tin cậy rõ ràng:

~~~mermaid
flowchart TD
    A[Nhận HTTP request] --> B[Giới hạn kích thước, kiểm tra format]
    B --> C[Tra cứu keyId HMAC và trạng thái]
    C --> D[Timestamp trong cửa sổ?]
    D -->|Không| X[Từ chối]
    D -->|Có| E[Tạo canonical request từ raw body]
    E --> F[HMAC hợp lệ?]
    F -->|Không| X
    F -->|Có| G[Đăng ký request nonce nguyên tử]
    G -->|Trùng| X
    G -->|Mới| H[Kiểm tra quyền sơ bộ của principal]
    H -->|Không| X
    H -->|Có| I[Giải mã AEAD bằng enc key phù hợp và AAD]
    I -->|Tag sai| X
    I -->|Đúng| J[Kiểm tra quyền theo tài nguyên trong plaintext]
    J -->|Không| X
    J -->|Có| K[Kiểm tra idempotency và nghiệp vụ]
    K --> L[Thực thi handler]
~~~

Một số hệ thống phải giải mã trước để biết action/resource chi tiết; khi đó phải kiểm soát phân quyền và giới hạn tài nguyên sau giải mã, trước mọi tác động nghiệp vụ. Quy tắc không thay đổi: **không tin principal trước khi xác thực và không xử lý nghiệp vụ trước khi authorization**.

Key ID dùng cho HMAC và key ID dùng cho encryption **không mặc nhiên là cùng một định danh**. Server phải kiểm tra encryption key có được phép sử dụng bởi principal và audience đã xác thực. Không để client tự chọn một `encKeyId` của tenant khác rồi khiến server giải mã hoặc trả plaintext tùy ý.

## 8. Java 17: mã hóa AES-GCM và kiểm tra HMAC

Đoạn mã minh họa dùng API chuẩn Java (JCA/JCE). Nó tập trung vào **hai primitive riêng**: AES-GCM cho payload; HMAC-SHA256 cho canonical request. Ví dụ không bao gồm HTTP parser, hệ thống cấp phát khóa, timestamp/nonce store hoặc authorization.

### 8.1. Hàm AES-GCM và HMAC

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class HmacAndEncryption {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int GCM_IV_BYTES = 12;       // 96-bit IV
    private static final int GCM_TAG_BITS = 128;      // 128-bit tag
    private static final int HMAC_SHA256_BYTES = 32;  // 256-bit MAC

    private HmacAndEncryption() {}

    public record EncryptedPayload(byte[] iv, byte[] ciphertextAndTag) {}

    public static EncryptedPayload encrypt(
            SecretKey encryptionKey, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {

        // Đảm bảo IV duy nhất cho từng lần mã hóa dưới cùng một khóa.
        // Ở hệ thống có lưu lượng cao cần chính sách quản lý nonce chuyên biệt.
        byte[] iv = new byte[GCM_IV_BYTES];
        RNG.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey,
                new GCMParameterSpec(GCM_TAG_BITS, iv));
        cipher.updateAAD(aad);

        return new EncryptedPayload(iv, cipher.doFinal(plaintext));
    }

    public static byte[] decrypt(
            SecretKey encryptionKey, EncryptedPayload payload, byte[] aad)
            throws GeneralSecurityException {

        if (payload.iv().length != GCM_IV_BYTES) {
            throw new GeneralSecurityException("Invalid payload");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, encryptionKey,
                new GCMParameterSpec(GCM_TAG_BITS, payload.iv()));
        cipher.updateAAD(aad);

        // Cipher.doFinal() kiểm tra tag; lỗi tag làm quá trình thất bại.
        return cipher.doFinal(payload.ciphertextAndTag());
    }

    public static String signCanonicalRequest(
            SecretKey hmacKey, byte[] canonicalRequest)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey);
        byte[] signature = mac.doFinal(canonicalRequest);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(signature);
    }

    public static boolean verifyCanonicalRequest(
            SecretKey hmacKey,
            byte[] canonicalRequest,
            String signatureBase64Url)
            throws GeneralSecurityException {

        if (signatureBase64Url == null) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signatureBase64Url);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        // Chỉ chấp nhận 32 byte trong Base64URL không padding.
        if (supplied.length != HMAC_SHA256_BYTES
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(signatureBase64Url)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey);
        byte[] expected = mac.doFinal(canonicalRequest);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Cách dùng đúng:** `encryptionKey` và `hmacKey` phải là **hai khóa khác nhau được cấp phát có kiểm soát**, đúng thuật toán; `aad` và `canonicalRequest` phải được xây dựng từ **các byte theo hợp đồng được định nghĩa rõ**. Ví dụ gọi `encrypt` sau đó gửi IV/ciphertext + tag; verifier phải kiểm tra HMAC trên **body thực nhận**, so sánh tag AES-GCM lúc giải mã và không trả plaintext nếu tag sai.

Trong code trên, `MessageDigest.isEqual` chỉ được gọi sau khi decode và kiểm tra độ dài signature. Các so sánh định dạng/Base64URL là kiểm tra cú pháp, không phải so sánh bí mật. Request không hợp lệ cần nhận thông báo lỗi xác thực tổng quát ở tầng HTTP.

### 8.2. Sinh khóa khác nhau cho hai mục đích

Trong môi trường thử nghiệm, có thể dùng API sinh khóa an toàn:

~~~java
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

// Ví dụ cấp khóa thử nghiệm; production cần secret manager/KMS và rotation.
KeyGenerator aesKeyGen = KeyGenerator.getInstance("AES");
aesKeyGen.init(256);
SecretKey encryptionKey = aesKeyGen.generateKey();

KeyGenerator hmacKeyGen = KeyGenerator.getInstance("HmacSHA256");
hmacKeyGen.init(256);
SecretKey hmacKey = hmacKeyGen.generateKey();
~~~

Không dùng một chuỗi mật khẩu dễ đoán làm cả `K_enc` lẫn `K_mac`. Nếu hệ thống bắt buộc suy dẫn nhiều khóa từ cùng một root key, nên dùng **KDF chuẩn** như HKDF và tách ngữ cảnh (purpose/audience/version) rõ ràng. Không lấy `SHA256(secret)` rồi tùy tiện cắt thành nhiều khóa và coi đó là key management đầy đủ.

### 8.3. Cách tạo hash raw body phục vụ HMAC

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

byte[] rawEnvelopeBody = /* byte UTF-8 chính xác sẽ gửi qua HTTP */ null;

byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(rawEnvelopeBody);
String bodyHashHex = HexFormat.of().formatHex(digest);
~~~

Dòng khai báo `rawEnvelopeBody` là placeholder để minh họa; trong chương trình thật, phải gán byte body thực tế trước khi tính digest. Server cần hash **đúng các byte mà verifier nhận được tại ranh giới đã chọn**. Không hash chuỗi JSON được parse rồi serialize lại nếu protocol đang ký raw bytes.

HMAC cũng có thể ký trực tiếp raw body thay vì hash, nhưng phải định nghĩa ranh giới, độ dài và thứ tự trường. Hash body trong canonical request giúp mô tả protocol gọn, nhưng **SHA-256(body) tự nó không phải MAC**: bảo mật đến từ HMAC trên canonical request có chứa body hash.

## 9. Ba loại khóa và kế hoạch rotation

Trong một API kết hợp HMAC và payload encryption thường có:

| Khóa/định danh | Chức năng | Ai được biết? | Khi rotation |
| --- | --- | --- | --- |
| `K_mac` / `macKeyId` | Tính và xác minh HMAC của canonical request | Client được cấp credential và verifier tin cậy | Tạo key ID mới, chuyển client, thu hồi key cũ |
| `K_enc` / `encKeyId` | Mã hóa và giải mã payload | Sender/recipient được phép đọc plaintext | Tạo encryption key ID mới, xác định chính sách giải mã dữ liệu cũ |
| TLS session keys | Bảo vệ một kết nối TLS | Hai TLS endpoint | Do TLS handshake/phiên kết nối quản lý |

Không nên tái sử dụng một shared secret để làm cả khóa HMAC và khóa AES-GCM. Việc tách purpose giúp giảm phụ thuộc giữa các primitive, kiểm soát quyền truy cập và có thể rotate độc lập.

### 9.1. Ví dụ rotation tách biệt

~~~text
Client A:
  macKeyId: client-A:mac-v3     -> HMAC secret v3
  encKeyId: client-A:enc-v2     -> AES-GCM encryption key v2

Registry server:
  mac-v2  -> RETIRING (chỉ xác minh trong overlap)
  mac-v3  -> ACTIVE
  enc-v1  -> DECRYPT_ONLY (nếu cần đọc dữ liệu đã lưu)
  enc-v2  -> ACTIVE
~~~

Một API có dữ liệu **chỉ đi qua mạng và không lưu lâu dài** có thể thu hồi khóa giải mã cũ theo lịch khác API lưu ciphertext trong database. Nếu ciphertext cũ phải tiếp tục đọc được, không thể xóa khóa giải mã trước khi re-encrypt hoặc xử lý retention. Với HMAC request, khóa cũ nên được ngừng chấp nhận chữ ký sau thời gian overlap; nếu nghi lộ khóa, cần thu hồi ngay theo quy trình ứng phó sự cố.

Đừng để client tự yêu cầu `alg=none`, một thuật toán yếu hơn hoặc một key ID thuộc tenant khác. Các lựa chọn khóa/thuật toán được giới hạn bởi **key record và policy phía server**. Một encryption key ID tồn tại không chứng minh client có quyền dùng key đó.

### 9.2. Lộ khóa HMAC khác lộ khóa mã hóa

- **Lộ `K_mac`:** attacker có thể tạo signed request mới trong phạm vi credential đó, dù không có quyền giải mã payload riêng.
- **Lộ `K_enc`:** attacker có thể đọc nội dung ciphertext nào họ thu thập được với khóa đó; nếu có thể mã hóa, họ cũng có khả năng tạo payload AEAD hợp lệ, nhưng vẫn cần vượt lớp HMAC nếu API yêu cầu.
- **Lộ cả hai:** attacker có thể vừa tạo signed request, vừa mã hóa/giải mã payload, chịu giới hạn của authorization, server controls và xử lý replay/idempotency.
- **Lộ TLS endpoint/gateway:** nội dung đã terminate TLS có thể bị đọc; payload AEAD vẫn bảo vệ thông tin nếu gateway không có encryption key và không bị lộ ở lớp khác.

Điều này cho thấy quản lý khóa quan trọng tương đương việc chọn thuật toán. Secret manager, quyền truy cập tối thiểu, audit, rotation, không log secret và chính sách backup/recovery cần được thiết kế ngay từ đầu.

## 10. Proxy/gateway ảnh hưởng thế nào khi có cả HMAC và mã hóa?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant V as HMAC Verifier / Backend
    participant E as Payload Decryptor
    participant A as Authorization

    C->>G: HTTPS, signed request + AEAD envelope
    Note over G: TLS có thể terminate tại đây
    G->>V: Forward method, URI, signed headers, raw body
    V->>V: Canonicalize và verify HMAC
    V->>V: Kiểm tra timestamp + nonce dùng chung
    V->>E: Chuyển envelope và trusted context
    E->>E: Kiểm tra encKeyId, IV, AAD, GCM tag
    E->>A: Principal + plaintext nghiệp vụ
    A-->>V: Quyết định quyền trên action/resource/tenant
    V-->>C: Kết quả HTTP
~~~

Các lỗi phổ biến:

1. **Gateway parse rồi serialize JSON envelope:** body bytes khác client đã ký; HMAC thất bại. Nếu verifier ký JSON theo ngữ nghĩa, hợp đồng cần một chuẩn canonical JSON cụ thể; cách đơn giản hơn thường là **ký raw body bytes** ổn định.
2. **Gateway rewrite path:** client ký `/api/v1/payments` nhưng backend nhận `/v1/payments`. Cần chốt điểm xác minh hoặc định nghĩa path được ký và audience ổn định.
3. **Header trùng/biến đổi:** gateway gộp `X-Key-Id`, `X-Nonce` hoặc `X-Timestamp` khác cách backend parse. Verifier nên từ chối request mơ hồ.
4. **Gateway giải nén hoặc giải mã payload:** Nếu proxy cần đọc plaintext, ranh giới tin cậy thay đổi; không coi gateway là blind forwarder. Nếu gateway được phép đọc, hãy quy định rõ việc xác minh và ủy quyền cho gateway.
5. **Gateway retry request:** cùng `X-Nonce` phải bị từ chối sau lần xác thực đầu tiên; retry với request nonce mới cần idempotency nghiệp vụ để tránh hai lần thanh toán.
6. **Gateway truyền principal bằng header:** phải xóa header tự khai từ Internet và bảo vệ kênh gateway–backend; HMAC xác minh ở gateway không cho phép backend tin một `X-Authenticated-Principal` chưa được bảo đảm.

**Kiểm thử tích hợp** phải sử dụng đường đi HTTP thực với gateway/WAF/service mesh, không chỉ unit test AES hoặc HMAC riêng lẻ.

## 11. Không có cơ chế nào thay thế authorization

HMAC có thể chứng minh request được ký bằng shared secret của client A. AES-GCM có thể xác minh payload do bên giữ encryption key tạo. TLS có thể xác thực peer của kết nối. **Không lớp nào tự quyết định client A được thực hiện thao tác gì trên tài nguyên cụ thể.**

Ví dụ client A gửi signed request chứa AEAD envelope và plaintext sau giải mã là:

~~~json
{
  "tenantId": "tenant-B",
  "account": "account-of-B",
  "amount": 125000
}
~~~

HMAC và tag AES-GCM có thể đều hợp lệ. Nếu key record ánh xạ đến `tenant-A`, backend phải từ chối do vượt quyền. Nguồn sự thật về tenant và scope đến từ **principal/key registry/policy phía server**, không phải trường tự khai trong body, dù body có được mã hóa hoặc ký.

Ngoài authorization, hệ thống thanh toán còn cần kiểm tra giới hạn số tiền, state machine, idempotency, concurrency và audit. Chữ ký/mã hóa không xác minh tính hợp lý của giao dịch.

## 12. Các nhầm lẫn thường gặp

### 12.1. “Dữ liệu đã ký thì người khác không đọc được”

Sai. HMAC không mã hóa. Ai có quyền quan sát HTTP body dạng rõ vẫn có thể đọc nó; cần TLS và/hoặc mã hóa payload theo threat model.

### 12.2. “Đã HTTPS thì không cần bảo mật request nữa”

Không hoàn toàn. HTTPS bảo vệ kết nối, nhưng API vẫn cần xác thực caller, phân quyền và chống lặp nghiệp vụ. HMAC là một phương án ứng dụng để xác thực request, không phải yêu cầu bắt buộc của mọi API HTTPS.

### 12.3. “AES-GCM có tag rồi, không cần bất kỳ xác thực client nào”

Không thể suy ra như vậy. AEAD tag xác minh payload với khóa AEAD, nhưng không tự quyết định principal được phép gọi API nào; nếu nhiều client cùng có khóa, tag không phân biệt họ. Có thể thiết kế hệ thống dùng AEAD như một phần credential, nhưng vẫn cần định nghĩa rõ danh tính, audience, freshness và quyền. HMAC ứng dụng là một lựa chọn tùy kiến trúc.

### 12.4. “HMAC và AES dùng chung một secret cũng được”

Không nên. Hai primitive có ngữ nghĩa và vòng đời riêng, nên cấp khóa độc lập hoặc dùng KDF chuẩn có context/purpose tách biệt. Dùng chung key bytes làm tăng rủi ro sai thiết kế hoặc khó rotate từng cơ chế.

### 12.5. “IV AES-GCM là nonce chống replay của HTTP”

Sai. IV bảo đảm an toàn cho lần mã hóa dưới một khóa. Request nonce cần **được server ghi nhớ và từ chối gửi lại** trong cửa sổ chấp nhận. Có IV mới không chứng minh nghiệp vụ chưa thực thi trước đó.

### 12.6. “Mã hóa body rồi HMAC body là đủ cho cả request”

Chưa đủ nếu method, path, query, header, key ID, timestamp, nonce hoặc audience ảnh hưởng đến xử lý nhưng không được ký hoặc ràng buộc bằng metadata đáng tin. Phải xác định **canonical request** đúng phạm vi.

### 12.7. “Chỉ kiểm tra HMAC sau khi giải mã payload cũng như nhau”

Thứ tự có thể thay đổi theo thiết kế chuẩn và ranh giới thực tế, nhưng việc giải mã trước khi xác minh request có thể tạo thêm rủi ro tiêu tốn tài nguyên hoặc phản hồi lỗi khác nhau. Với mô hình HMAC bao phủ ciphertext envelope, thường có lợi khi **xác minh HMAC trước** rồi mới giải mã AEAD; dù vậy, vẫn phải kiểm tra tag AEAD trước khi dùng plaintext và chỉ xử lý nghiệp vụ sau authorization.

### 12.8. “Có SHA-256 của body thì đã xác thực”

Sai. SHA-256 không có secret; attacker có thể sửa body rồi tính lại hash. Chỉ khi body hash được ràng buộc bên trong **HMAC của canonical request** có khóa bí mật, việc thay body mới làm chữ ký không hợp lệ.

## 13. Ma trận kiểm thử HMAC và encryption

| Kiểm thử | Cách thực hiện | Kỳ vọng |
| --- | --- | --- |
| HMAC đúng, payload AEAD đúng | Ký canonical request đúng với body mã hóa hợp lệ | Có thể xác thực và giải mã; vẫn kiểm tra replay/quyền |
| Sửa ciphertext sau khi ký | Đổi một byte trong ciphertext của HTTP body | HMAC sai nếu body được ký; tag AEAD cũng sẽ sai nếu vẫn thử giải mã |
| Sửa IV sau khi ký | Thay IV trong envelope | HMAC sai; nếu không có HMAC thì tag AEAD phải không hợp lệ |
| Sửa method/path | Đổi `POST` thành `GET` hoặc đổi route | HMAC sai theo contract; hoặc request bị từ chối do không hợp lệ |
| Sửa `encKeyId` | Chọn key ID khác với ciphertext ban đầu | Body HMAC sai; kể cả khi HMAC mới hợp lệ, server còn phải kiểm tra quyền dùng key |
| Sửa `X-Key-Id` | Giữ chữ ký, đổi credential ID | Từ chối xác thực |
| Sai AAD | Mã hóa đúng nhưng phía giải mã dùng audience/path khác | AES-GCM từ chối do tag không khớp |
| Sai AES-GCM tag | Làm hỏng tag hoặc ciphertext | Không trả plaintext cho handler |
| Trùng IV dưới cùng key | Mô phỏng cơ chế sinh IV lỗi | Phải bị phát hiện bởi kiểm thử/giám sát hoặc thiết kế cấp IV, không coi thành công giải mã là an toàn |
| Không có TLS | Dùng plain HTTP trong môi trường yêu cầu HTTPS | Bị gateway/server từ chối hoặc tự động redirect theo policy phù hợp, không truyền secret/payload nhạy cảm trên kênh rõ |
| Timestamp ngoài cửa sổ | Gửi request có chữ ký đúng nhưng quá cũ/quá xa tương lai | Từ chối freshness |
| Nonce HTTP dùng lại | Gửi lại nguyên signed request | Lần sau bị từ chối replay bằng shared nonce store |
| Nonce race hai instance | Gửi song song cùng nonce tới các node | Tối đa một request qua replay gate |
| Retry với nonce mới | Gửi cùng payment ID/event ID có chữ ký mới | Idempotency chặn xử lý trùng tác vụ |
| Sai tenant | Client A ký/mã hóa đúng request cho tài nguyên B | Xác thực có thể đúng; authorization phải từ chối |
| HMAC key revoked | Ký bằng key ID cũ sau thu hồi | Bị từ chối trên mọi verifier |
| Encryption key revoked | Yêu cầu giải mã bằng key đã bị cấm dùng | Bị từ chối theo policy, không tự fallback sang key khác |
| Gateway thay body bytes | Proxy parse/serialize lại envelope | Xác minh thất bại hoặc contract xác minh tại biên phù hợp, không bỏ kiểm tra |
| Header trùng/khác case | Lặp `X-Nonce`, `X-Key-Id` hoặc biến đổi whitespace | Bị từ chối nếu mơ hồ; client/server cùng quy tắc canonicalization |
| Envelope quá lớn | Gửi body/IV/ciphertext vượt giới hạn | Bị từ chối sớm, không gây cạn tài nguyên |
| Lỗi oracle | Gửi key sai, tag sai, HMAC sai để đo response | Lỗi ra ngoài nhất quán, không lộ plaintext hoặc trạng thái chi tiết của key |

Những test này cần được chạy cả ở đơn vị primitive, lớp HTTP verifier và tuyến end-to-end đi qua gateway thật. Một test chỉ chứng minh AES-GCM encrypt/decrypt vòng tròn được chưa đủ để bảo đảm HMAC, replay hay quyền nghiệp vụ.

## 14. Tình huống thực tế: webhook mang dữ liệu nhạy cảm

Một đối tác gửi webhook giao dịch gồm số tài khoản và trạng thái thanh toán. Hệ thống có API gateway ở vùng biên, backend xử lý thanh toán và hàng đợi nội bộ.

**Yêu cầu giả định:**

- Chỉ đối tác có credential được cấp mới gửi webhook được chấp nhận.
- Gateway cần định tuyến request nhưng không được đọc số tài khoản.
- Kết nối từ Internet phải dùng HTTPS.
- Một webhook bị phát lại không được tạo giao dịch trùng.
- Đối tác chỉ cập nhật giao dịch thuộc tenant của mình.

**Thiết kế đề xuất:**

1. Cấp riêng `macKeyId/K_mac` để ký HTTP request, `encKeyId/K_enc` để mã hóa payload, quản lý độc lập và rotate có kiểm soát.
2. Đối tác tạo body AEAD envelope; AAD ràng buộc `payment-webhook`, version và audience.
3. Đối tác tạo canonical HMAC gồm `POST`, URI, audience, ID khóa MAC, timestamp, request nonce và hash **raw envelope body**.
4. Gateway chỉ forward body theo hợp đồng, không parse/serialize; backend xác minh HMAC và chống replay trên shared nonce store.
5. Backend kiểm tra encryption key thuộc đúng principal/audience, giải mã AES-GCM, xác minh tag và kiểm tra tenant/order/event.
6. Handler áp dụng idempotency theo event ID, cập nhật giao dịch theo transaction và ghi audit không lộ secret/plaintext nhạy cảm.

**Nhận xét:** Nếu gateway được phép đọc toàn bộ nội dung theo thiết kế, payload AEAD giữa client và backend có thể không cần thiết. Nếu gateway không được phép đọc, AES-GCM cung cấp một ranh giới bí mật bổ sung mà TLS terminate ở gateway không thể cung cấp. HMAC đảm nhiệm việc xác thực request bất kể quyết định mã hóa payload.

## 15. Câu hỏi tự kiểm tra

1. **Tại sao HMAC hợp lệ không bảo vệ tính bí mật của JSON body?**  
   Vì HMAC chỉ sinh MAC từ thông điệp và khóa bí mật; nó không thay plaintext bằng ciphertext.

2. **Vì sao AES-CBC thuần không nên coi là xác thực payload?**  
   Vì encryption không mặc nhiên đem lại tính toàn vẹn; cần authenticated encryption hoặc một kết hợp MAC có cơ sở bảo mật.

3. **Khác nhau giữa request nonce và AES-GCM IV là gì?**  
   Request nonce dùng để phát hiện request được gửi lại; IV bảo đảm không lặp nonce dưới cùng encryption key cho an toàn mật mã AES-GCM.

4. **Một request có AES-GCM tag đúng có chắc được phép cập nhật tài nguyên của tenant khác không?**  
   Không. Tag là kiểm tra toàn vẹn/xác thực ciphertext với khóa AEAD; authorization quyết định quyền thao tác.

5. **Vì sao phải HMAC cả method, URI và body hash nếu payload đã mã hóa?**  
   Vì encryption payload không tự ràng buộc toàn bộ ý nghĩa request; method, URI, header và body cần được gắn với credential theo contract.

6. **Tại sao gateway TLS termination có thể là lý do mã hóa payload riêng?**  
   TLS chỉ bảo vệ tới endpoint chấm dứt kết nối. Payload encryption tới backend giúp gateway không có khóa không đọc được dữ liệu.

7. **Có nên dùng cùng secret cho HMAC-SHA256 và AES-GCM không?**  
   Không nên. Cần khóa tách biệt theo purpose hoặc key derivation chuẩn với domain separation và rotation rõ ràng.

8. **Nếu nonce HTTP đã dùng, chữ ký và tag AES-GCM vẫn đúng thì server làm gì?**  
   Từ chối replay; validity của chữ ký/tag không xóa yêu cầu freshness.

## 16. Checklist triển khai

- [ ] Threat model chỉ rõ ai có thể xem plaintext, ai có secret HMAC, ai có encryption key, và proxy nào terminate TLS.
- [ ] Dùng HTTPS/TLS cho chặng mạng cần bảo vệ; không coi HMAC là công cụ mã hóa.
- [ ] Đã chọn đúng mục tiêu: xác thực request bằng HMAC, bí mật payload bằng AEAD khi cần, hoặc cả hai theo ranh giới tin cậy.
- [ ] Hợp đồng ký định nghĩa method, URI, header, audience, timestamp, nonce, key ID và body hash ở cấp byte, có version.
- [ ] Đã quyết định ký raw body hoặc chuẩn canonical JSON thực sự; không phụ thuộc thứ tự serializer ngẫu nhiên.
- [ ] AEAD dùng thuật toán được hỗ trợ an toàn, IV/nonce **không trùng theo từng encryption key**, tag và AAD được kiểm tra trước khi dùng plaintext.
- [ ] HMAC key và encryption key tách riêng, quản lý bằng secret manager, có key ID, trạng thái, audience và rotation.
- [ ] Server dùng timestamp cửa sổ hợp lý, request nonce ngẫu nhiên và kho chống replay atomically trên toàn bộ instance.
- [ ] Authorization kiểm tra principal, tenant, action và resource sau xác thực; nghiệp vụ có idempotency khi cần.
- [ ] Gateway/backend thống nhất canonicalization; không tin header principal do client tự khai; test qua đường truyền thật.
- [ ] Giới hạn body/header/IV, xử lý lỗi đồng nhất, không log secret hoặc plaintext nhạy cảm.
- [ ] Có ma trận kiểm thử tampering, sai tag, sai HMAC, replay, rotation, proxy rewrite và vượt quyền.

**Kết luận:** **HMAC xác thực các byte đã ký; encryption giữ bí mật plaintext; AEAD kết hợp mã hóa với xác thực ciphertext; TLS bảo vệ kết nối.** Khi dùng chúng cùng nhau cho HTTP request, phải quy định chính xác dữ liệu được ký và mã hóa, tách khóa và nonce theo mục đích, bảo vệ ranh giới gateway, chống replay và tiếp tục phân quyền dựa trên principal đáng tin. Một chữ ký đúng và một ciphertext giải mã được vẫn chưa đủ để quyết định rằng thao tác nghiệp vụ được phép thực hiện.
