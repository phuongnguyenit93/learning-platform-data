# Signature metadata

Trong xác thực HTTP request bằng HMAC, **signature metadata** là tập thông tin đi kèm request để server biết **chữ ký được tạo theo hợp đồng nào, dùng credential nào và có còn hợp lệ theo thời gian hay không**. Các trường như `keyId`, phiên bản giao thức, thuật toán, timestamp, nonce, phạm vi header được ký và chữ ký thường được đặt trong HTTP header hoặc một cấu trúc xác thực có định dạng rõ ràng.

Tuy nhiên, sự hiện diện của metadata **chưa chứng minh request đã được xác thực**. Kẻ gửi request có thể tự khai bất kỳ `keyId`, timestamp hay tên thuật toán nào. Server chỉ được tin các thông tin đó sau khi **kiểm tra cấu trúc, tra cứu khóa tin cậy, tái tạo canonical request và xác minh HMAC**, sau đó kiểm tra freshness/replay và quyền truy cập.

Bài học thuộc chương **Request signature** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Nội dung tập trung vào cách thiết kế, truyền, chuẩn hóa và kiểm tra signature metadata trong mô hình client–server sử dụng shared secret. Hợp đồng ký có thể bao gồm HTTP method, URI, header hoặc body; ví dụ bên dưới dùng HMAC-SHA256 và một cấu trúc metadata cụ thể để làm rõ toàn bộ luồng.

> **Nguyên tắc:** Signature metadata là dữ liệu do caller cung cấp để server **xác minh** request. Metadata cần được ràng buộc mật mã với canonical request và đối chiếu với chính sách **do server quản lý**. Không được lấy thông tin caller tự khai làm danh tính hoặc quyền truy cập trước bước xác minh.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **metadata của chữ ký** với **chữ ký**, **shared secret**, **canonical request** và **principal** đã xác thực.
2. Giải thích vai trò của `keyId`, `signature version`, `algorithm`, `created`, `expires`, `nonce`, `signed headers`, `audience` và `body digest`.
3. Xây dựng hợp đồng truyền metadata đủ tường minh để các HTTP client/framework khác nhau cho kết quả giống nhau.
4. Chỉ ra trường metadata nào phải được đưa vào chuỗi ký, trường nào do server suy ra và vì sao không thể ký chính giá trị chữ ký theo cách thông thường.
5. Thiết kế trình tự parse, kiểm tra khóa, tính HMAC, timestamp/nonce, key rotation và phân quyền.
6. Kiểm tra metadata khi request đi qua proxy/gateway, bị thay header, header trùng, đổi thuật toán hoặc replay.
7. Viết mã Java xác minh metadata có cấu trúc chặt chẽ và lập ma trận kiểm thử dương/âm.

## 2. Signature metadata là gì?

Ở cấp HTTP, một request được ký có thể gồm ba phần logic:

~~~text
HTTP request
  ├─ Dữ liệu yêu cầu
  │    method, URI, query, headers nghiệp vụ, raw body
  ├─ Signature metadata
  │    version, keyId, algorithm policy, created/expires, nonce,
  │    signedHeaders/audience nếu hợp đồng sử dụng
  └─ Signature value
       HMAC-SHA256(secret, canonicalRequestBytes)
~~~

**Dữ liệu yêu cầu** xác định hành động mà server được yêu cầu thực hiện. **Metadata** giúp chọn đúng contract, credential và kiểm tra tính mới. **Signature value** là kết quả mật mã do client tính.

Một metadata field có thể mang hai vai trò:

- Là **dữ liệu điều khiển bước xác minh**, chẳng hạn `keyId` dùng để tìm secret.
- Là **nội dung cần được bảo vệ bởi chữ ký**, chẳng hạn timestamp, nonce, key ID và version nếu việc sửa chúng làm thay đổi ý nghĩa giao thức.

Điều này không mâu thuẫn: server cần đọc một số field *trước khi* có thể xác minh chữ ký, nhưng phải coi giá trị đã đọc là **chưa đáng tin** cho đến khi HMAC khớp và các điều kiện khác thành công.

### 2.1. Phân biệt các khái niệm

| Khái niệm | Bản chất | Vai trò |
| --- | --- | --- |
| `keyId` | Định danh credential, thường không bí mật | Chọn key record và secret để xác minh |
| Shared secret | Khóa bí mật dùng chung giữa client và verifier | Đầu vào mật mã của HMAC |
| Canonical request | Dãy byte chuẩn hóa từ request và metadata đã định nghĩa | Nội dung được HMAC bảo vệ |
| Signature | Tag HMAC tạo từ secret và canonical bytes | Bên nhận tính lại và so sánh |
| Authenticated principal | Danh tính tin cậy server tạo sau xác thực thành công | Đầu vào cho authorization |
| Authorization policy | Quyền theo principal, action, resource, tenant | Quyết định có thực thi nghiệp vụ hay không |
| Replay state | Bản ghi nonce/request đã chấp nhận | Phát hiện request cũ gửi lại |

Một `keyId` hợp lệ về cú pháp, hoặc một key record tìm thấy trong database, **không tương đương** với một request có chữ ký hợp lệ.

## 3. Những trường signature metadata thường gặp

| Trường logic | Ví dụ | Mục đích | Ghi chú an toàn |
| --- | --- | --- | --- |
| **Protocol/signature version** | `v1` | Chọn phiên bản canonicalization và định dạng thông điệp | Phải được ràng buộc vào chữ ký; server chỉ hỗ trợ phiên bản cho phép |
| **Key identifier** | `partner-a-k3` | Chọn secret và principal mapping ở server | Không phải secret; tra cứu exact match, kiểm tra trạng thái/đích sử dụng |
| **Algorithm** | `hmac-sha256` | Cho biết thuật toán được hỗ trợ theo contract | Không được để client tự chọn thuật toán tùy ý hoặc `none` |
| **Created timestamp** | `1790000000` | Giới hạn tuổi request và hỗ trợ chống replay | Quy định Unix seconds hay milliseconds; được ký |
| **Expiration** | `1790000300` | Mốc hết hiệu lực rõ ràng của chữ ký | Được ký; giới hạn thời gian sống tối đa ở server |
| **Request nonce** | `6bfb21974a08417199273b09ca49a3ec` | Nhận diện mỗi request mới | Được ký; store dùng chung phải ngăn trùng bằng thao tác nguyên tử |
| **Signed headers / components** | `content-type;x-key-id;...` | Công bố những phần HTTP được bao phủ | Server phải có tập field bắt buộc; không cho caller tự bỏ trường quan trọng |
| **Audience / service identifier** | `orders-api` | Ràng buộc request với dịch vụ nhận dự kiến | Phải được ký hoặc được ràng buộc bởi contract/key record tin cậy |
| **Content digest** | `SHA-256(rawBody)` | Ràng buộc body lớn vào canonical request | Bản thân digest không có khóa; chỉ an toàn khi nằm trong HMAC |
| **Signature value** | `Base64URL(HMAC bytes)` | Giá trị server so sánh với tag tự tính | Không phải secret dài hạn; không đưa chính giá trị này vào chuỗi ký |

Không phải mọi giao thức HMAC đều dùng đủ các trường trên. **Tập trường chính xác phải do contract quy định**; không thể ghép ngẫu nhiên metadata từ hai kiểu ký rồi mong hai phía xác minh giống nhau.

### 3.1. Metadata cố định và metadata tùy chọn

Một protocol đơn giản có thể **cố định thuật toán, encoding và tập signed components** trong phiên bản `v1`, nên không cần gửi cả ba thông tin trên mỗi request. Một protocol linh hoạt hơn có thể truyền `algorithm` hoặc `signedHeaders`, nhưng **server vẫn phải kiểm tra chúng theo whitelist và tập bắt buộc**.

Ví dụ, cho phép caller gửi:

~~~http
X-Signed-Headers: x-key-id;x-signature-created
~~~

và vì thế bỏ method, path hoặc body khỏi chữ ký là nguy hiểm nếu các trường bị bỏ ảnh hưởng đến handler. Metadata chỉ có ý nghĩa khi nó đi kèm **chính sách xác minh tối thiểu không thể bị client hạ thấp**.

## 4. Một hợp đồng signature metadata hoàn chỉnh

Để tránh ví dụ mơ hồ, bài học chọn **một contract minh họa** với các quyết định sau:

- Signature protocol: `HMAC-HTTP-V1`.
- Thuật toán: **HMAC-SHA256**, được cố định trong contract và key record phía server.
- Chữ ký: **32 byte**, mã hóa Base64URL **không padding** thành **43 ký tự**.
- `created` và `expires`: số nguyên Unix time **tính theo giây**, dạng thập phân ASCII không có số 0 thừa.
- `nonce`: 16 byte ngẫu nhiên, encode thành **32 ký tự hex chữ thường**; unique trong phạm vi credential và cửa sổ chấp nhận.
- `keyId`: định danh ASCII chính xác với format được quy định.
- Body digest: **SHA-256 của đúng raw body bytes**, viết thành **64 ký tự hex chữ thường**.
- Audience: một ID dịch vụ ổn định `orders-api` do server cấu hình.
- Canonical text: UTF-8, các dòng được nối bằng **LF**, **không có LF cuối**.
- Các trường đã ký: method, canonical path, canonical query, audience, content type, key ID, version, created, expires, nonce và body digest.
- Trạng thái khóa, thời gian hiệu lực, quyền và audience của credential được tra cứu từ key registry do server quản lý.

Các lựa chọn này là **hợp đồng ví dụ của bài học**, không phải chuẩn mặc định cho mọi hệ thống HTTP HMAC.

### 4.1. Request minh họa

~~~http
POST /v1/orders?currency=VND&sku=A%2BB HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Signature-Version: v1
X-Key-Id: partner-a-k3
X-Signature-Created: 1790000000
X-Signature-Expires: 1790000300
X-Signature-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <43-character-base64url-tag>

{"sku":"A+B","quantity":2}
~~~

`<43-character-base64url-tag>` là placeholder; chỉ client có secret mới tính được tag thực tế. Timestamp chỉ phục vụ minh họa, **không dùng request này làm dữ liệu xác thực hiện hành**.

Ở ví dụ này, client không gửi `X-Signature-Algorithm` hoặc `X-Signed-Headers`. Thuật toán và danh sách thành phần ký đã **được cố định bởi v1**, loại bỏ một lựa chọn dễ bị lợi dụng để hạ thấp bảo mật.

### 4.2. Canonical request được ký

Giả sử path/query và `Content-Type` đã được chuẩn hóa chính xác theo contract, canonical text tương ứng là:

~~~text
HMAC-HTTP-V1
POST
/v1/orders
currency=VND&sku=A%2BB
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-signature-version:v1
x-signature-created:1790000000
x-signature-expires:1790000300
x-signature-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-lowercase-hex-characters>
~~~

Phải thay `<64-lowercase-hex-characters>` bằng SHA-256 thật của byte UTF-8 trong body ví dụ. Canonical string có **12 dòng** và **không thêm ký tự xuống dòng cuối**. Khi contract cho phép query trùng tên hoặc header nhiều giá trị, cách giải quyết phải được định nghĩa riêng; tuyệt đối không giả định mỗi thư viện HTTP xử lý giống nhau.

Phía client tính:

~~~text
rawBodyBytes     = exact bytes used as HTTP body
bodyDigest       = SHA-256(rawBodyBytes)
canonicalBytes   = UTF8(canonicalText)
tagBytes         = HMAC-SHA256(K_mac, canonicalBytes)
signatureHeader  = Base64UrlWithoutPadding(tagBytes)
~~~

Phía server cần tạo lại **đúng các byte đó** từ request được nhận tại ranh giới xác minh đã chọn.

### 4.3. Vì sao metadata phải xuất hiện trong canonical request?

Giả sử attacker sửa `X-Signature-Expires` để kéo dài hạn dùng, hoặc sửa `X-Key-Id` để chuyển sang credential khác, nhưng giữ nguyên `X-Signature`. Nếu các field trên được ký, canonical bytes thay đổi, nên HMAC không còn khớp.

Tương tự, thay `X-Signature-Nonce` nhằm né replay store cũng làm tag không hợp lệ. Nếu server cho phép thay nonce hoặc timestamp **mà không thay đổi dữ liệu được HMAC**, lớp chống replay có thể bị vô hiệu hóa.

**Chú ý điểm khác biệt:** `X-Signature` được **so sánh**, nhưng thường **không được đưa vào chính canonical text tạo ra nó**, vì sẽ tạo phụ thuộc vòng. Những metadata còn lại có ảnh hưởng đến ý nghĩa xác thực cần được ký. Danh tính principal và quyền vẫn lấy từ registry phía server, chứ không lấy từ giá trị tự khai của caller.

## 5. Version và algorithm: chống nhầm lẫn giao thức

### 5.1. Signature version dùng để làm gì?

Một trường `X-Signature-Version: v1` nên xác định tập quy tắc đủ rộng:

1. Thuật toán MAC và kiểu encoding signature.
2. Tập field bắt buộc đưa vào canonical request.
3. Thứ tự các field, ký tự phân cách, UTF-8 và cách xử lý chuỗi rỗng.
4. Quy tắc xử lý URI, percent-encoding, query trùng, header lặp, khoảng trắng.
5. Định dạng timestamp, nonce, digest body và mốc hết hạn.
6. Cách chọn audience và ràng buộc credential với chính sách verifier.

Vì vậy, tăng version không chỉ là đổi tên header. Nếu `v2` thay đổi cách ký URL hoặc body digest, client/verifier phải cùng nâng cấp và kiểm thử tương thích.

### 5.2. Algorithm do ai lựa chọn?

**Server cần giữ quyền quyết định thuật toán nào được chấp nhận cho credential và version.** Một header tự khai như:

~~~http
X-Signature-Algorithm: none
~~~

không thể là cơ sở để bỏ xác minh. Ngay cả khi client gửi `hmac-sha1` hoặc một lựa chọn yếu hơn có cú pháp hợp lệ, server phải đối chiếu chính sách và từ chối nếu không được cấp.

Nếu contract muốn truyền algorithm metadata, cần **ký giá trị algorithm đó** và kiểm tra rằng nó khớp với algorithm đã cấu hình trong key registry. Tuy nhiên, “đã ký algorithm” cũng chưa đủ: vì bên có secret có thể ký một giá trị yếu hơn, server không được tự động cho phép bất kỳ thuật toán nào người gọi chọn.

### 5.3. Không đoán thuật toán theo độ dài chữ ký

HMAC-SHA256 có tag đầy đủ 32 byte, HMAC-SHA384 có 48 byte, nhưng không nên viết:

~~~text
if signatureLength == 32:
    algorithm = HmacSHA256
else if signatureLength == 48:
    algorithm = HmacSHA384
~~~

Cách đó trộn hai bước “chọn contract” và “xác minh tag”, khiến chính sách khó kiểm soát. Luồng đúng: **version + key record server-side → algorithm hợp lệ → expected tag length/encoding → verify**.

### 5.4. Signed headers là một chính sách

Nếu giao thức truyền danh sách `signedHeaders`, mỗi tên header cần được chuẩn hóa và danh sách phải có thứ tự/định dạng duy nhất. Tối thiểu server phải áp dụng **mandatory signed components** do chính sách quy định, không cho bỏ method/path/body digest hoặc freshness metadata.

Một phương án an toàn và dễ kiểm thử là **v1 quy định danh sách cố định**, không để request tự điều chỉnh. Khi cần thêm header nghiệp vụ quan trọng, thiết kế thay đổi protocol version, thay vì âm thầm thêm một trường mà client chưa ký.

## 6. Key ID là metadata tra cứu, không phải danh tính được chứng thực

`X-Key-Id` giúp server chọn secret để tính lại HMAC:

~~~mermaid
flowchart LR
    R[Request metadata] --> I[Đọc keyId]
    I --> K[(Key registry)]
    K --> M[Key record: secretRef, status, principal, audience]
    M --> V[Verify HMAC và freshness]
    V --> P[Principal tin cậy]
    P --> A[Authorization]
~~~

Một key record ví dụ:

~~~yaml
keyId: partner-a-k3
principalId: partner-a-service
audience: orders-api
algorithm: HmacSHA256
secretRef: secrets/orders/partner-a/k3
status: ACTIVE
notBefore: "2026-09-01T00:00:00Z"
acceptUntil: "2027-01-01T00:00:00Z"
scope:
  - orders:create
~~~

Đây là mẫu mô tả metadata **phía server**, không phải dữ liệu gửi trực tiếp từ client. `secretRef` là tham chiếu tới secret manager chứ không chứa secret thật.

Quy trình đúng:

1. Đọc `keyId` và kiểm tra cú pháp/độ dài; chỉ cho **một giá trị duy nhất**.
2. Tra cứu exact match trong registry theo namespace do server quy định.
3. Xác minh key record còn hiệu lực, không bị thu hồi, đúng algorithm/version và audience.
4. Lấy secret tương ứng từ nguồn tin cậy để tính HMAC.
5. Chỉ khi HMAC và freshness/replay hợp lệ, tạo principal từ `principalId` của key record.
6. Phân quyền theo action/resource/tenant bằng chính sách phía server.

Không suy principal từ prefix như `partner-a-` trong key ID, hoặc từ header `X-User-Id`/`X-Tenant-Id` do caller tự khai. Một client có secret hợp lệ có thể cố tình ký một request vượt quyền; MAC đúng không tự cấp quyền.

## 7. Timestamp, expiration và nonce: metadata chống replay

HMAC kiểm tra tính toàn vẹn của message, nhưng **một request đã ký vẫn có thể bị phát lại nguyên vẹn**. Signature metadata thường cung cấp `created`, `expires` và `nonce` để server thực hiện lớp kiểm soát riêng.

### 7.1. Created/expires được kiểm tra như thế nào?

Giả sử contract v1 quy định:

~~~text
created = Unix seconds, số nguyên thập phân không dấu
expires = Unix seconds, số nguyên thập phân không dấu
maxLifetime = 300 seconds
maxFutureSkew = 30 seconds
~~~

Server có thể yêu cầu:

~~~text
created <= expires
expires - created <= maxLifetime
created <= serverNow + maxFutureSkew
serverNow <= expires
~~~

Cần dùng phép toán số nguyên tránh overflow và có quy tắc xử lý cụ thể ở biên. Nếu contract không cho duration bằng 0, dùng `created < expires`. Hệ thống phải kiểm tra thời hạn được phép sử dụng của **credential** riêng với thời hạn của **request**: chữ ký còn trong 5 phút nhưng key đã bị thu hồi thì vẫn bị từ chối.

Ví dụ: nếu `created` ghi theo **milliseconds** trong khi server hiểu **seconds**, request có thể bị từ chối hàng loạt. Contract phải quy định rõ đơn vị, timezone (Unix epoch là mốc UTC), format decimal và chính sách clock skew.

### 7.2. Có timestamp chưa có nghĩa đã chống replay

Một attacker có thể gửi lại request nguyên vẹn trong cửa sổ 5 phút. Chữ ký, created và expires vẫn đúng. `X-Signature-Nonce` cần được server ghi nhận một cách an toàn:

~~~text
replayKey = "hmac:" + audience + ":" + keyId + ":" + nonce

putIfAbsent(replayKey, acceptedUntil)   // atomic
  -> new:  tiếp tục xử lý
  -> seen: từ chối replay
~~~

**Điều kiện quan trọng:**

- Client tạo nonce bằng CSPRNG, ví dụ 128 bit ngẫu nhiên mã hóa hex.
- Nonce nằm trong canonical request và được HMAC bảo vệ.
- Store phải **dùng chung giữa các verifier instance**, hỗ trợ ghi nếu chưa có theo thao tác nguyên tử. Kiểm tra rồi ghi tách rời sẽ có race.
- TTL phải che phủ **mọi thời điểm request còn có thể được chấp nhận**. Với expires, có thể tính thời hạn lưu đến hết mốc chấp nhận cộng biên đồng hồ phù hợp; không xóa nonce sớm khi request vẫn còn hạn.
- Không ghi nonce vào store **trước khi xác minh HMAC**, tránh attacker tự chọn nonce để làm bẩn/bão hòa store.
- Khi replay store mất kết nối, API nhạy cảm phải thực thi chính sách **fail closed** hoặc phương án đã được thiết kế an toàn, không âm thầm cho qua mọi nonce.

### 7.3. Nonce và idempotency giải quyết hai vấn đề khác nhau

Giả sử client gửi `POST /payments`, bị timeout và retry:

- Gửi lại **cùng signed request**: nonce trùng, replay gate phải từ chối bản sau.
- Tạo **request mới với timestamp/nonce/chữ ký mới**, nhưng cùng lệnh thanh toán: cả hai có thể hợp lệ ở lớp HMAC.

Vì vậy, giao dịch thanh toán/đơn hàng cần thêm **idempotency key hoặc event ID** được ràng buộc với request/principal, cùng lưu trạng thái nghiệp vụ để tránh thực thi lặp. Nonce chặn **replay của signed request**; idempotency chặn **tác động nghiệp vụ lặp**.

## 8. Signed headers và body digest: metadata về phạm vi được bảo vệ

### 8.1. Không thể ký “một phần tùy ý” mà vẫn kỳ vọng bảo vệ toàn request

Giả sử server ký **chỉ body**:

~~~text
HMAC(secret, SHA256(body))
~~~

Nếu method và path không được ký, attacker có thể giữ body/signature nhưng đổi `POST /v1/orders` sang endpoint khác mà handler hiểu theo ý nghĩa khác. Do đó, phải bảo vệ những trường quyết định **đích đến và hành động**.

Một số phần quan trọng:

- HTTP method và target URI.
- Query parameters ảnh hưởng đến target, tenant hoặc tham số nghiệp vụ.
- Header `Content-Type` nếu parser khác nhau theo MIME type.
- Key ID, signature version, created/expires, nonce và audience.
- Body digest từ **đúng raw bytes** mà handler xử lý, hoặc canonical representation được protocol định nghĩa.
- Header ảnh hưởng quyền như tenant, idempotency, người dùng ủy quyền hoặc routing; tốt hơn là lấy principal từ server nếu được.

### 8.2. Digest body không phải MAC

~~~text
bodyDigest = SHA-256(rawBodyBytes)
mac = HMAC-SHA256(secret, canonicalTextWithBodyDigest)
~~~

Kẻ tấn công có thể tự tính một SHA-256 mới cho body đã sửa. Giá trị digest chỉ có ý nghĩa toàn vẹn có khóa khi nó được **đặt trong canonical request đã được HMAC ký**.

Nếu body là JSON, các biểu diễn sau có thể biểu thị cùng dữ liệu nhưng có byte khác:

~~~json
{"sku":"A+B","quantity":2}
~~~

~~~json
{"quantity":2,"sku":"A+B"}
~~~

Vì vậy, nếu ký raw body digest thì client phải gửi **chính byte body đã hash** và verifier phải hash byte tương ứng tại điểm xác minh. Không nên parse rồi serialize JSON trước khi kiểm tra trừ khi protocol định nghĩa một chuẩn canonical JSON riêng được triển khai nhất quán.

### 8.3. Header lặp, thiếu hoặc tự đổi dấu cách

HTTP cho phép header name không phân biệt chữ hoa/thường, nhưng các framework/proxy có thể xử lý giá trị lặp khác nhau. Ví dụ:

~~~http
X-Key-Id: partner-a-k3
X-Key-Id: partner-b-k7
~~~

Nếu verifier chọn giá trị đầu còn middleware định tuyến hoặc principal layer chọn giá trị cuối, có thể xuất hiện **parser differential**. Cách đơn giản là contract yêu cầu một giá trị duy nhất, từ chối header trùng và header chứa biểu diễn mơ hồ. Không mặc nhiên kết luận `request.getHeader(name)` đã phát hiện được mọi trường hợp lặp.

Tương tự, header `X-Signature-Created` có cả `1790000000` và `1790000300` phải bị từ chối. Không parse “giá trị nào cũng được” hoặc âm thầm trim/trộn nếu điều đó không có trong contract.

## 9. Java 17: kiểm tra metadata và HMAC-SHA256

Để triển khai, nên **tách parse metadata**, **canonicalize request**, **verify HMAC** và **authorize** thành những bước có hợp đồng rõ. Ví dụ sau dùng Java JCA để xác minh một protocol `v1` đơn giản như mục 4.

### 9.1. Đọc đúng một giá trị header

Interface ở ví dụ yêu cầu adapter HTTP bên ngoài trả về **toàn bộ các giá trị** của header cùng tên. Adapter cần tự phát hiện request chứa các tên header khác case, header đã bị proxy gộp, ký tự điều khiển hoặc encoding bất thường.

~~~java
import java.util.List;

public interface HeaderValues {
    // name là lowercase; adapter phải trả về mọi giá trị của header này.
    List<String> values(String lowercaseName);
}

public final class SignatureHeaderReader {
    private SignatureHeaderReader() {}

    public static String exactlyOne(
            HeaderValues headers, String lowercaseName) {
        List<String> values = headers.values(lowercaseName);

        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException("Invalid signature metadata");
        }

        String value = values.get(0);
        if (value == null || value.isEmpty()
                || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Invalid signature metadata");
        }

        return value;
    }
}
~~~

Đây là **hợp đồng của adapter**, chưa phải cách parse wire HTTP hoàn chỉnh. Gateway/backend cần cùng quy tắc với duplicate headers và phải từ chối các giá trị bị gộp không xác định được ranh giới. Mỗi field còn phải được validate theo **format riêng**, không chỉ kiểm tra nonempty.

### 9.2. Parse metadata có format cố định

Code dưới đây cố định version và cú pháp của `keyId`, `created/expires`, `nonce` và chữ ký. Nó không tra secret hay đọc thời gian thực; caller chịu trách nhiệm kiểm tra freshness và key registry.

~~~java
import java.util.regex.Pattern;

public record SignatureMetadata(
        String version,
        String keyId,
        long created,
        long expires,
        String nonce,
        String signature) {

    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9_-]{8,80}");
    private static final Pattern EPOCH =
            Pattern.compile("(0|[1-9][0-9]{0,18})");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");
    private static final Pattern SIGNATURE =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    public static SignatureMetadata parse(HeaderValues headers) {
        String version = SignatureHeaderReader.exactlyOne(
                headers, "x-signature-version");
        String keyId = SignatureHeaderReader.exactlyOne(
                headers, "x-key-id");
        String created = SignatureHeaderReader.exactlyOne(
                headers, "x-signature-created");
        String expires = SignatureHeaderReader.exactlyOne(
                headers, "x-signature-expires");
        String nonce = SignatureHeaderReader.exactlyOne(
                headers, "x-signature-nonce");
        String signature = SignatureHeaderReader.exactlyOne(
                headers, "x-signature");

        if (!"v1".equals(version)
                || !KEY_ID.matcher(keyId).matches()
                || !EPOCH.matcher(created).matches()
                || !EPOCH.matcher(expires).matches()
                || !NONCE.matcher(nonce).matches()
                || !SIGNATURE.matcher(signature).matches()) {
            throw new IllegalArgumentException("Invalid signature metadata");
        }

        try {
            return new SignatureMetadata(
                    version, keyId,
                    Long.parseLong(created),
                    Long.parseLong(expires),
                    nonce, signature);
        } catch (NumberFormatException invalidTimestamp) {
            throw new IllegalArgumentException(
                    "Invalid signature metadata", invalidTimestamp);
        }
    }
}
~~~

Quy ước ở đây yêu cầu **nonce hex chữ thường** và signature Base64URL không padding. Với format chữ ký khác, cần đổi version/contract và bộ kiểm thử; không nới lỏng parser tùy ý sau khi đưa vào production.

### 9.3. Kiểm tra thời gian và xác minh tag

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class SignatureV1Crypto {
    private SignatureV1Crypto() {}

    public static boolean validTimeWindow(
            SignatureMetadata meta,
            long serverNowSeconds,
            long maxLifetimeSeconds,
            long maxFutureSkewSeconds) {
        long created = meta.created();
        long expires = meta.expires();

        // Giới hạn Unix seconds vào miền không âm và kiểm tra phép trừ an toàn.
        if (created < 0 || expires < created
                || maxLifetimeSeconds < 1 || maxFutureSkewSeconds < 0) {
            return false;
        }
        if (expires - created > maxLifetimeSeconds) {
            return false;
        }

        // Viết lại để không cộng now + skew gây overflow.
        if (created > serverNowSeconds
                && created - serverNowSeconds > maxFutureSkewSeconds) {
            return false;
        }

        return serverNowSeconds <= expires;
    }

    public static String sha256BodyHex(byte[] rawBody)
            throws GeneralSecurityException {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        return HexFormat.of().formatHex(hash);
    }

    // method/path/query/contentType đã được canonicalize đúng contract.
    // Chúng không được chứa LF hoặc CR và phải có encoding thống nhất.
    public static byte[] canonicalBytes(
            SignatureMetadata meta,
            String method,
            String canonicalPath,
            String canonicalQuery,
            String contentType,
            byte[] rawBody) throws GeneralSecurityException {

        String canonical = String.join("\n",
                "HMAC-HTTP-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + contentType,
                "x-key-id:" + meta.keyId(),
                "x-signature-version:" + meta.version(),
                "x-signature-created:" + meta.created(),
                "x-signature-expires:" + meta.expires(),
                "x-signature-nonce:" + meta.nonce(),
                "body-sha256:" + sha256BodyHex(rawBody));

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static boolean verifyTag(
            SecretKey hmacKey, byte[] canonicalBytes, String presented)
            throws GeneralSecurityException {

        // Đã xác thực format 43 ký tự ở bước parse metadata.
        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(presented);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(presented)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey);
        byte[] expected = mac.doFinal(canonicalBytes);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Giới hạn của ví dụ Java:**

- `canonicalBytes` nhận path/query/content type **đã được chuẩn hóa ở một lớp khác**, theo đúng quy tắc đã ký. Các tham số đầu vào đó **không được chứa CR/LF**; phương thức và path/query phải được kiểm tra bằng parser đáng tin.
- `validTimeWindow` minh họa logic expiry trong miền timestamp thực tế. Ở production cần áp dụng giới hạn timestamp được hỗ trợ, đồng bộ đồng hồ, policy time skew và xử lý số học overflow nếu cho phép timestamp gần giới hạn `long`. Ngoài ra cần kiểm tra thời hạn của **khóa**.
- `verifyTag` chỉ xác minh MAC. Nó **không** tra key record, chống replay, tạo principal hoặc kiểm tra quyền.
- Signature là dữ liệu public của request, nhưng có thể bị attacker dùng để replay; không tự động log toàn bộ chữ ký/nonce/request nhạy cảm.
- Các exception/response phải được ánh xạ thành lỗi xác thực thống nhất; không trả thông tin chi tiết về secret hay trạng thái key ID cho bên ngoài.

### 9.4. Luồng tích hợp vào server

~~~text
1. Kiểm tra request size, method, URI và header structure
2. Đọc chính xác một bộ signature metadata và validate format
3. Từ keyId -> key record (secret, principal, status, audience, algorithm)
4. Kiểm tra key còn hiệu lực và contract v1 được phép cho credential
5. Kiểm tra created/expires theo đồng hồ và policy server
6. Canonicalize cùng method/path/query/header/body bytes client đã ký
7. Tính HMAC-SHA256 và so sánh với chữ ký đã nhận
8. Ghi (audience, keyId, nonce) bằng thao tác nguyên tử nếu chưa tồn tại
9. Tạo principal tin cậy từ key record
10. Authorize principal đối với action/resource/tenant
11. Kiểm tra idempotency và nghiệp vụ trước khi thực thi
~~~

Tùy hệ thống, một số kiểm tra quyền sơ bộ có thể thực hiện trước khi xử lý body lớn; nhưng tuyệt đối **không thực hiện tác động nghiệp vụ** trước khi đã xác thực và phân quyền đầy đủ.

## 10. Metadata trong quá trình key rotation

Một client thường giữ **nhiều credential version** trong khoảng chuyển khóa:

~~~text
clientId: partner-a
principalId: partner-a-service

keyId: partner-a-k2  -> secret v2, RETIRING
keyId: partner-a-k3  -> secret v3, ACTIVE
~~~

`X-Key-Id` là metadata giúp verifier chọn **đúng một record**. Quy trình thường gồm:

1. Cấp `keyId` mới, secret mới và record với cùng principal/audience được xét duyệt.
2. Phân phối secret an toàn cho client; triển khai record mới đến các verifier.
3. Client chuyển sang gửi `X-Key-Id: partner-a-k3` và ký bằng secret v3.
4. Server chấp nhận k2/k3 trong khoảng chuyển tiếp hữu hạn theo trạng thái riêng của mỗi khóa; quan sát tần suất dùng key ID.
5. Hết thời gian chuyển tiếp, thu hồi k2 và vô hiệu hóa cache ở mọi node.
6. Nếu nghi lộ secret, ưu tiên thu hồi ngay theo quy trình ứng phó; không duy trì overlap thông thường.

**Một thay đổi quan trọng:** Nếu key ID bị đổi nhưng chữ ký vẫn giữ từ secret cũ, verifier phải từ chối. Khi rotation, **metadata mới phải được ký cùng canonical request mới**.

Không nên thay secret dưới cùng một `keyId` rồi yêu cầu server “thử cả hai khóa đến khi HMAC đúng”. Cách đó làm mơ hồ credential, giảm khả năng truy vết và tạo lỗi đồng bộ cache.

### 10.1. Thu hồi khóa và thời hạn của chữ ký

Đừng nhầm hai loại hết hạn:

- `X-Signature-Expires`: request cụ thể hết hạn.
- `keyRecord.acceptUntil` hoặc trạng thái `REVOKED`: credential dùng để ký bị giới hạn hoặc thu hồi.

Ngay cả khi `X-Signature-Expires` chưa tới, request ký bằng key đã bị thu hồi **phải bị từ chối theo chính sách thu hồi**. Cache key record cần có cơ chế invalidation/TTL phù hợp, nếu không verifier có thể còn chấp nhận key cũ.

## 11. Proxy/gateway: metadata có thể bị biến đổi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant V as HMAC Verifier
    participant N as Nonce Store
    participant A as Authorization

    C->>G: HTTPS + signature metadata + raw body
    Note over G: Có thể terminate TLS/rewrite request
    G->>V: Forward theo contract
    V->>V: Parse metadata, key lookup, canonicalize
    V->>V: Verify signature và freshness
    V->>N: Atomic putIfAbsent(keyId, nonce)
    N-->>V: Nonce mới hoặc trùng
    V->>A: Trusted principal + request
    A-->>V: Allow / deny
    V-->>C: HTTP response
~~~

Những tình huống đặc biệt:

| Tình huống | Tác động lên signature metadata | Biện pháp |
| --- | --- | --- |
| Gateway bỏ `X-Key-Id` | Verifier không thể chọn secret | Cấu hình forward header cần thiết và test tích hợp |
| Gateway sửa `X-Signature-Created` | HMAC sai hoặc freshness bị diễn giải khác | Không đổi signed metadata; từ chối header mơ hồ |
| Gateway gộp header lặp | Hai phía có thể đọc key ID/nonce khác nhau | Từ chối duplicates ngay ở ranh giới HTTP tin cậy |
| Gateway rewrite path/query | Canonical bytes server khác client | Chốt điểm xác minh và URI contract, test end-to-end |
| Gateway parse/serialize body | Body hash đổi dù nội dung JSON tương đương | Ký và xác minh đúng raw bytes hoặc chuẩn canonical JSON được định nghĩa |
| Gateway thay `Host` | Đích nội bộ khác authority bên ngoài | Ràng buộc audience ổn định hoặc authority theo policy |
| Gateway retry request | Cùng nonce có thể bị phát lại | Replay store dùng chung; idempotency nghiệp vụ riêng |
| Gateway gửi header principal | Backend có thể tin nhầm dữ liệu caller tự khai | Gateway xóa header định danh ngoài rồi thiết lập principal qua kênh tin cậy |
| Các region lệch cache key | Rotation/revocation cho kết quả không nhất quán | Quản lý hiệu lực credential và cache invalidation xuyên vùng |

### 11.1. Xác minh ở gateway hay backend?

- **Verifier ở gateway:** gateway kiểm tra signature metadata trên request ở ranh giới thống nhất, tạo principal. Backend chỉ được tin principal qua kết nối/kênh được bảo vệ và từ gateway đã xác thực. Gateway phải loại header `X-Authenticated-Principal` do Internet tự gửi trước khi tạo header nội bộ mới.
- **Verifier ở backend:** hợp đồng canonical phải mô tả request **sau những biến đổi cho phép** của proxy, hoặc gateway phải giữ nguyên những byte/trường đã ký. Không xác minh dựa trên URI khác URI mà router dùng để chọn handler.

Ở cả hai cách, `X-Forwarded-*`/`Forwarded` do client Internet tự gửi không được coi là nguồn tin mặc định. Cần xây chuỗi tin cậy rõ ràng từ các proxy được phép và test với request mơ hồ như `%2F`, query trùng tên, header trùng, khoảng trắng khác nhau.

## 12. Phân biệt xác thực chữ ký với phân quyền

Ví dụ một credential có `keyId = partner-a-k3` được liên kết với principal `partner-a-service` thuộc `tenant-A`. Client ký hợp lệ request:

~~~http
DELETE /v1/tenants/tenant-B/orders/order-912 HTTP/1.1
X-Key-Id: partner-a-k3
X-Signature-Version: v1
X-Signature-Created: 1790000000
X-Signature-Expires: 1790000300
X-Signature-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag-for-this-request>
~~~

Nếu client thực sự có secret A, HMAC có thể đúng, timestamp/nonce mới cũng có thể hợp lệ. Nhưng principal tenant A **không mặc nhiên có quyền xóa order của tenant B**.

**Authentication** trả lời: “Request này có chữ ký khớp credential nào và còn hợp lệ theo contract không?”. **Authorization** trả lời: “Principal đó có được phép làm action này trên resource này trong tenant này không?”. Signature metadata không thay thế scope, RBAC/ABAC, kiểm tra ownership, hạn mức hoặc kiểm tra hợp lệ nghiệp vụ.

Ngay cả khi client đưa `X-Tenant-Id: tenant-B` vào metadata rồi ký nó, sự kiện “client có thể ký trường tenant-B” vẫn **không tạo ra quyền tenant-B**. Policy phía server phải quyết định dựa trên principal đã xác thực.

## 13. Các lỗi thiết kế signature metadata thường gặp

### 13.1. Metadata không được ký

`created`, `expires`, `nonce` và `keyId` được parse nhưng không nằm trong canonical bytes. Attacker có thể sửa chúng để tác động tới freshness hoặc chọn secret mà không thay đổi MAC. Thiết kế phải ràng buộc mọi metadata làm thay đổi ý nghĩa giao thức; ví dụ contract ở mục 4 ký tất cả.

### 13.2. Chấp nhận thuật toán do request tự chọn

Một header `X-Signature-Algorithm: none` hoặc tự chọn thuật toán cũ có thể làm hạ chuẩn xác thực nếu server không kiểm tra chính sách. Khóa thuật toán theo version/key record, không dùng trực tiếp giá trị do caller gửi.

### 13.3. Tự tin tưởng signedHeaders list

Nếu verifier chấp nhận bất kỳ danh sách nào client tự khai, client có thể ký chỉ timestamp mà bỏ body, path hoặc action. Server phải định nghĩa thành phần bắt buộc và kiểm tra danh sách đúng protocol.

### 13.4. Header trùng hoặc nhiều cách decode

`X-Key-Id` lặp, header chứa CR/LF, Unicode kỳ lạ hoặc hai cách percent-decode URI có thể khiến verifier và handler hiểu khác nhau. Cần validate cấu trúc và từ chối đầu vào mơ hồ trước khi ký/xác minh.

### 13.5. Timestamp có chữ ký nhưng không có nonce store

Trong cửa sổ còn hạn, kẻ lấy được signed request có thể gửi lại nhiều lần. Phải có replay store nguyên tử dùng chung và TTL che phủ toàn thời gian chấp nhận.

### 13.6. Nonce store ghi trước bước MAC

Attacker không có secret vẫn có thể gửi hàng triệu nonce giả, gây lấp bộ nhớ hoặc chặn request hợp lệ nếu namespace bị đoán. Chỉ đánh dấu nonce khi request đã vượt qua xác minh MAC và kiểm tra freshness.

### 13.7. Ký body qua serializer khác body thực gửi

Hai bản JSON tương đương ngữ nghĩa có thể khác byte. Bên ký và bên nhận cần cùng raw body representation; đặc biệt kiểm thử middleware/Gateway thực tế.

### 13.8. Lấy quyền từ key ID hoặc header tự khai

`keyId` là đường dẫn tra credential; sau xác thực phải lấy principal và permissions từ registry phía server. Không suy quyền từ prefix tên hoặc từ body/header có nội dung do client tự quyết.

### 13.9. Lộ metadata và secret qua log

Key ID, nonce, signature và các signed headers có thể xuất hiện trong trace/log. Dù key ID thường không bí mật, **signature có thể bị dùng để replay trong cửa sổ thời gian**, nên tránh ghi toàn bộ signed request và secret vào log mở. Audit nên lưu ID đã được chuẩn hóa, mã lỗi và thông tin đủ điều tra với retention/access control phù hợp.

### 13.10. Không ràng buộc audience

Một credential chung cho nhiều dịch vụ có thể khiến request ký cho `orders-api` được chuyển sang `billing-api` nếu path và field trùng ý nghĩa. Ràng buộc audience/service ID bằng contract được ký và metadata credential do server quản lý; tránh chia sẻ secret trên nhiều dịch vụ nếu không cần.

## 14. Ma trận kiểm thử signature metadata

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Request đúng | Version, keyId, timestamp, nonce, body/signature phù hợp | MAC đúng, freshness mới; tiếp tục authorization |
| Thiếu version | Bỏ `X-Signature-Version` | Từ chối theo v1 |
| Version lạ | Đổi `v1` sang `v9` | Từ chối; không fallback mù quáng |
| Key ID không tồn tại | Gửi ID cú pháp hợp lệ nhưng không có record | Lỗi xác thực tổng quát |
| Đổi key ID sau khi ký | `partner-a-k3` thành ID khác | Từ chối |
| Algorithm downgrade | Thêm `alg=none` hoặc đề nghị MAC yếu | Không ảnh hưởng policy; từ chối nếu contract không cho |
| Timestamp sai đơn vị | Gửi milliseconds thay seconds | Từ chối do format/window |
| Timestamp tương lai | `created` vượt ngưỡng cho phép | Từ chối |
| Hạn sống quá dài | `expires-created > maxLifetime` | Từ chối dù MAC đúng |
| Hết hạn | `serverNow > expires` | Từ chối |
| Đổi expires sau khi ký | Tăng expires, giữ signature cũ | Từ chối do MAC sai |
| Đổi nonce sau khi ký | Thay `X-Signature-Nonce` | Từ chối do MAC sai |
| Replay nguyên request | Gửi hai lần cùng nonce | Chỉ bản đầu được qua replay gate |
| Replay đồng thời | Hai request cùng nonce đến nhiều node | Tối đa một request qua store atomically |
| Nonce store unavailable | Mô phỏng mất kết nối | Không bypass replay policy an toàn |
| Header key ID trùng | Hai `X-Key-Id` hoặc khác case | Từ chối input mơ hồ |
| Header signature trùng | Hai `X-Signature` | Từ chối |
| Signature sai encoding | Dấu `=` không cho phép, ký tự không phải Base64URL | Từ chối |
| Signature sai độ dài | Ít hơn 32 byte hoặc hơn 32 byte | Từ chối theo v1 |
| Đổi body | Sửa một byte trong JSON | Từ chối MAC |
| Đổi method/path/query | Sửa trường được ký | Từ chối MAC |
| Signed headers không đủ | Bỏ body/header bắt buộc trong biến thể cho client chọn | Từ chối theo tập bắt buộc |
| Key bị thu hồi | MAC đúng bằng secret cũ | Từ chối do trạng thái key |
| Key rotate overlap | Cả k2/k3 có record đang được cho phép | Mỗi ID xác minh bằng đúng secret của nó |
| Cache revocation | Thu hồi key trong registry và thử ở các node | Không chấp nhận quá thời hạn revoke policy |
| Audience sai | Credential orders dùng cho billing | Từ chối dù có thể tạo MAC |
| Gateway rewrite | Proxy đổi path/query/body trong tuyến thực tế | Verifier/handler thống nhất ý nghĩa hoặc từ chối |
| Header principal giả | Caller thêm `X-Authenticated-Principal: admin` | Không ảnh hưởng principal do verifier tạo |
| Đúng chữ ký, sai tenant | Partner A sửa dữ liệu tenant B | Authentication có thể đúng, authorization từ chối |
| Retry nghiệp vụ | Request mới nonce mới nhưng cùng event/order ID | Idempotency không cho thực hiện lặp |

Kiểm thử nên xác nhận **chuỗi byte canonical kỳ vọng**, **key ID/algorithm đã chọn**, **request được xử lý bởi handler nào** và **kết quả authorization**. Nếu chỉ test `HMAC(secret, text)` trong unit test sẽ bỏ sót nhiều lỗi signature metadata phát sinh ở HTTP parser và proxy.

## 15. Tình huống thực tế: ký callback cập nhật đơn hàng

Một nền tảng thương mại điện tử nhận callback từ nhiều đối tác. Mỗi đối tác được cấp credential HMAC; một callback đi qua API gateway trước khi đến service đơn hàng.

**Tình huống A: đối tác dùng sai đồng hồ.** Client gửi created theo milliseconds, server mong seconds. Signature có thể khớp nếu cả client và server ký đúng chuỗi đó, nhưng freshness phải từ chối theo contract. Đội vận hành cần metric cho `invalid_timestamp` và hướng dẫn đồng bộ đồng hồ, không tự nới cửa sổ lên nhiều ngày.

**Tình huống B: đối tác thay version.** Client cũ ký theo v1 nhưng đặt `X-Signature-Version: v2`. Server phải chọn v2 một cách có kiểm soát và MAC sẽ không khớp, hoặc từ chối do credential chưa cho phép v2. Không “thử mọi phiên bản” để tìm cái nào khớp.

**Tình huống C: gateway retry callback.** Request thứ hai giữ nguyên nonce và chữ ký. Replay store đã ghi nonce từ lần đầu nên bản thứ hai bị từ chối; nếu đối tác retry với nonce mới, event ID trong body và idempotency store đảm bảo không cập nhật trùng.

**Tình huống D: key rotation.** Partner A chuyển từ `partner-a-k2` sang `partner-a-k3`, trong khoảng overlap cả hai record tồn tại. Verifier chọn một key record theo key ID, kiểm tra trạng thái và đúng principal, không dò mọi secret. Sau khi k2 bị thu hồi, request dùng k2 phải bị từ chối kể cả expires còn thời gian.

**Tình huống E: vượt quyền tenant.** Partner A có MAC đúng nhưng body chứa `tenantId=tenant-B`. Phân quyền dựa trên principal/tenant phía server từ chối. Một chữ ký hợp lệ bảo vệ sự toàn vẹn của lời **yêu cầu**, không cấp quyền thực hiện nội dung yêu cầu.

## 16. Bài tập tự thực hành

### Bài tập 1: Thiết kế contract

Hãy định nghĩa một contract ký HMAC cho endpoint:

~~~http
POST /v1/transactions?channel=partner HTTP/1.1
Content-Type: application/json

{"transactionId":"tx-01","amount":120000}
~~~

Nêu rõ các metadata field, cách encode signature, khóa/canonical version, query normalization, signed headers, raw body digest và cách server tìm principal. So sánh hai cách: contract cố định signed components và contract cho client gửi danh sách `signedHeaders`.

### Bài tập 2: Chống replay

Giả sử v1 cho phép request sống tối đa 5 phút, đồng hồ client có thể lệch trước server 30 giây. Thiết kế kiểm tra created/expires và cách tính TTL replay key sao cho nonce không bị xóa khi chữ ký còn được chấp nhận. Giải thích vì sao cache local trên mỗi instance không đủ trong cluster.

### Bài tập 3: Kiểm thử gateway

Thiết lập giả lập client → reverse proxy → verifier. Gửi lần lượt request có query trùng, path `%2F`, header `X-Key-Id` lặp, JSON body thay đổi khoảng trắng và request được retry. Ghi lại canonical bytes và đảm bảo handler cuối cùng không xử lý một request khác ý nghĩa với request đã xác minh.

### Bài tập 4: Kiểm tra quyền

Một `keyId` của tenant A có MAC đúng khi gọi `DELETE /v1/tenants/B/orders/1`. Hãy chỉ ra phần nào **authentication** cần xác minh, phần nào **authorization** phải từ chối và thông tin tenant nào được coi là nguồn sự thật.

## 17. Checklist triển khai signature metadata

- [ ] Chỉ định protocol/version rõ ràng, có bộ quy tắc canonical request nhất quán.
- [ ] Key ID là định danh credential; secret/algorithm/status/audience/principal được quản lý phía server.
- [ ] Không dùng thuật toán hoặc signed components do caller tự chọn mà không có whitelist/chính sách bắt buộc.
- [ ] Mỗi metadata field có tên header, format, encoding, giới hạn độ dài và quy tắc duplicate riêng.
- [ ] Created/expires/nonce/key ID/version có ảnh hưởng xác thực được ràng buộc vào HMAC.
- [ ] Chữ ký được so sánh sau decode/kiểm tra đúng encoding và tag length; giá trị signature không nằm trong canonical bytes.
- [ ] Canonical request bao gồm method, URI, audience, header và body digest đủ bảo vệ ý nghĩa request.
- [ ] Timestamp/expiry theo đơn vị thống nhất; nonce ngẫu nhiên mạnh, lưu nguyên tử ở shared store với TTL che phủ cửa sổ.
- [ ] Retry và idempotency được xử lý độc lập với nonce chống replay.
- [ ] Key rotation cấp key ID mới, có giới hạn overlap, revoke và cache invalidation.
- [ ] Gateway, proxy và handler thống nhất URI/header/body; header principal tự khai bị loại bỏ ở ranh giới tin cậy.
- [ ] HTTPS/TLS bảo vệ kết nối; log tránh lộ secret, plaintext nhạy cảm hoặc full signed request có thể replay.
- [ ] Phân quyền dựa trên principal/action/resource/tenant phía server trước khi xử lý nghiệp vụ.
- [ ] Có positive/negative tests cho version, key ID, thời gian, nonce, encoding, body, proxy, rotation và quyền.

## 18. Câu hỏi tự kiểm tra

1. **Signature metadata có phải chữ ký không?** Không. Metadata mô tả cách xác minh và bối cảnh; chữ ký là MAC tag được tính từ secret và canonical bytes.
2. **`keyId` đúng có đồng nghĩa client đã xác thực không?** Không. Server phải xác minh tag với secret của key ID và kiểm tra freshness.
3. **Tại sao phải ký `created`, `expires` và `nonce`?** Để việc sửa các giá trị chống replay làm chữ ký không hợp lệ.
4. **Tại sao thường không ký chính `X-Signature`?** Vì signature là kết quả của phép tính trên canonical request; đưa giá trị kết quả vào chính thông điệp tạo nó tạo phụ thuộc vòng.
5. **Version có thể chỉ đổi tên từ `v1` sang `v2` không?** Không nên. Version phải ràng buộc bộ quy tắc, thuật toán, encoding và các thành phần ký.
6. **Nếu client tự bỏ `path` khỏi signedHeaders mà HMAC vẫn đúng thì request có an toàn không?** Không, nếu path ảnh hưởng handler. Server phải bắt buộc ký thành phần liên quan tới mục tiêu bảo vệ.
7. **Vì sao timestamp và expiry không thay nonce store?** Vì cùng signed request có thể bị gửi lại nhiều lần trước khi expires.
8. **Vì sao ký body digest chưa đủ chống gian lận tenant?** Body có thể chứa yêu cầu vượt quyền nhưng vẫn được client có secret ký hợp lệ. Authorization phải kiểm tra quyền phía server.
9. **Vì sao proxy có thể làm signature sai?** Vì proxy thay path, query, header hoặc raw body, tạo canonical bytes khác client đã ký.
10. **Làm sao cập nhật secret trong key rotation mà không gây nhầm lẫn?** Cấp key ID mới, lưu record riêng, chuyển client, quan sát overlap và thu hồi ID cũ có kiểm soát.

**Kết luận:** **Signature metadata** xác định credential, contract, thời gian sống, nonce và phạm vi được ký của một HTTP request. Thiết kế đúng đòi hỏi metadata được parse chặt chẽ, phần ảnh hưởng bảo mật được ràng buộc vào canonical HMAC, các chính sách thuật toán/khóa nằm ở server, replay được ngăn bằng store nguyên tử và principal được kiểm tra quyền trước nghiệp vụ. Chỉ từ sự hiện diện của một bộ header chữ ký, server chưa thể kết luận request hợp lệ hoặc được phép thực hiện.
