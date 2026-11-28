# HMAC-SHA384

**HMAC-SHA384** là thuật toán tạo mã xác thực thông điệp (message authentication code, MAC) dựa trên **HMAC** và hàm băm **SHA-384**. Trong xác thực HTTP request, client sử dụng shared secret để tính HMAC-SHA384 trên các byte của **canonical request**; server chọn đúng secret, tái tạo cùng các byte rồi xác minh chữ ký. Nếu chữ ký hợp lệ, server có bằng chứng rằng request đã được tạo bởi một bên có quyền sử dụng secret và những trường đã ký không bị sửa trong quá trình truyền.

Bài học thuộc chương **Hash algorithm** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Phạm vi ứng dụng là xác thực HTTP request với hợp đồng ký gồm method, URI, header và/hoặc body, đồng thời cần chống replay bằng timestamp/nonce, hỗ trợ key rotation, kiểm thử qua proxy/gateway và tách bạch **authentication** với **authorization**.

> **Điểm mấu chốt:** SHA-384 là hàm băm *không có khóa*; HMAC-SHA384 là MAC *có khóa bí mật*. HMAC-SHA384 tạo tag **48 byte (384 bit)**, nhưng không tự mã hóa dữ liệu, chống replay hoặc cấp quyền cho request.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `SHA-384(message)` với `HMAC-SHA384(key, message)`, giải thích khi nào dùng mỗi cơ chế.
2. Mô tả cấu trúc HMAC trên SHA-384, kích thước block/hash, cách xử lý khóa và dạng biểu diễn tag.
3. Dùng Java JCA với `Mac.getInstance("HmacSHA384")` để tạo/xác minh tag, bao gồm so sánh chữ ký đúng cách.
4. Xây dựng hợp đồng canonical HTTP request có version, xác định các byte nào được ký và quy tắc mã hóa cần thống nhất.
5. Thiết kế quy trình kiểm tra key ID, timestamp, nonce, quyền của principal và key rotation quanh bước HMAC.
6. Kiểm thử bằng vector chuẩn và các request cố tình bị sửa, bị phát lại, có header mơ hồ hoặc đi qua gateway.
7. Đánh giá khi nào HMAC-SHA384 thực sự phù hợp thay vì mặc nhiên thay thế HMAC-SHA256 bằng tag dài hơn.

## 2. SHA-384 và HMAC-SHA384 khác nhau ở đâu?

### 2.1. SHA-384: hàm băm không có khóa

SHA-384 nhận một thông điệp byte `M` và tạo digest 384 bit:

~~~text
digest = SHA-384(M)
~~~

SHA-384 thuộc họ SHA-2, sử dụng cấu trúc dựa trên SHA-512 với giá trị khởi tạo riêng và đầu ra được rút gọn còn 384 bit. Các thuộc tính quan trọng:

| Thuộc tính của SHA-384 | Giá trị |
| --- | --- |
| Độ dài digest | 384 bit = **48 byte** |
| Độ dài block đầu vào của hàm băm | 1024 bit = **128 byte** |
| Hex chữ thường của digest đầy đủ | **96 ký tự hex** |
| Base64URL không padding của 48 byte | **64 ký tự** |
| Có sử dụng shared secret? | **Không** |
| Có cung cấp MAC/xác thực client? | **Không** |

SHA-384 hữu ích để tính **body digest** trước khi đưa vào canonical request. Tuy nhiên, bất kỳ ai biết body đều có thể tính lại digest tương ứng. Nếu chỉ yêu cầu client gửi `SHA-384(body)`, kẻ tấn công có thể sửa body rồi tính lại hash; đó **không phải xác thực**.

### 2.2. HMAC-SHA384: MAC có khóa

HMAC-SHA384 bổ sung một secret `K`:

~~~text
tag = HMAC-SHA384(K, M)
~~~

Trong giao thức xác thực request, `M` thường không phải riêng body mà là **chuỗi byte canonical request**, bao gồm mọi trường HTTP quan trọng theo hợp đồng ký. Chỉ bên biết `K` mới có thể tạo tag hợp lệ cho thông điệp mới, với giả định khóa bí mật và triển khai giao thức an toàn.

| Tiêu chí | SHA-384 | HMAC-SHA384 |
| --- | --- | --- |
| Đầu vào | Message bytes | Secret key + message bytes |
| Đầu ra | Digest 48 byte | MAC tag 48 byte |
| Người không có secret có thể tự tạo đầu ra? | Có | Về mặt thực tế, không thể giả mạo tag hợp lệ nếu HMAC và khóa an toàn |
| Bảo vệ toàn vẹn khi attacker có thể sửa cả message/hash? | Không | Có, đối với các byte đã ký |
| Chứng minh sở hữu shared secret? | Không | Có điều kiện, sau khi verifier kiểm tra đúng tag |
| Mã hóa plaintext? | Không | Không |
| Chống replay? | Không | Không tự làm được |

**Phân biệt ba tên gần giống:**

~~~text
SHA-384(rawBodyBytes)              -> digest không có khóa
HMAC-SHA384(K_mac, canonicalBytes) -> MAC tag có khóa
HMAC-SHA256(K_mac, canonicalBytes) -> MAC tag có khóa, dùng SHA-256 thay vì SHA-384
~~~

Thuật toán cho **body digest** và thuật toán cho **MAC** là hai quyết định protocol độc lập. Ví dụ có thể ký bằng HMAC-SHA384 trong khi canonical request chứa `body-sha256`. Nếu chọn `body-sha384` như bài này minh họa, cần nói rõ ở contract; server và client không được tự suy ra từ tên MAC.

## 3. Cấu trúc mật mã của HMAC-SHA384

### 3.1. HMAC sử dụng hai vòng băm

HMAC được định nghĩa theo cấu trúc:

~~~text
HMAC(K, M) =
    H((K' XOR opad) || H((K' XOR ipad) || M))
~~~

Trong đó:

- `H` là SHA-384.
- `M` là thông điệp byte cần xác thực.
- `K'` là khóa đã được xử lý thành một block 128 byte.
- `ipad` là byte `0x36` lặp trên toàn bộ block.
- `opad` là byte `0x5c` lặp trên toàn bộ block.
- `XOR` là phép XOR trên byte; `||` là phép nối byte.

Với SHA-384, **block size là 128 byte**, không phải 48 byte. Hai kích thước này có mục đích khác nhau: 128 byte dùng cho bước xử lý khóa và pad của HMAC, 48 byte là độ dài digest/tag kết quả.

### 3.2. Xử lý khóa đầu vào

HMAC hỗ trợ khóa có nhiều độ dài:

1. Nếu khóa dài **hơn 128 byte**, tính `SHA-384(K)` để được 48 byte.
2. Nếu khóa ngắn hơn 128 byte, đệm thêm các byte `0x00` cho đủ 128 byte.
3. Dùng block khóa đó với `ipad` và `opad` trong công thức HMAC.

Điều này là phần định nghĩa thuật toán, **không có nghĩa nên sử dụng mật khẩu ngắn hoặc dễ đoán**. Với API server-to-server, nên cấp khóa ngẫu nhiên đủ mạnh, ví dụ **32 byte từ CSPRNG**, qua secret manager hoặc quy trình cấp credential an toàn. Khóa HMAC không cần dài đúng 48 byte mới có thể dùng với SHA-384.

~~~mermaid
flowchart TD
    K[Shared secret K] --> N[Chuẩn hóa K thành block 128 byte]
    M[Canonical request bytes M] --> I
    N --> I[Inner: SHA-384 của K' XOR ipad nối M]
    I --> O[Outer: SHA-384 của K' XOR opad nối inner digest]
    N --> O
    O --> T[HMAC tag 48 byte]
~~~

Trong Java, **không cần tự triển khai ipad/opad**. Dùng API HMAC của thư viện mật mã chuẩn để tránh lỗi xử lý khóa, byte order và padding.

### 3.3. Vì sao không viết `SHA384(secret || request)`?

Một phép nối đơn giản như:

~~~text
badTag = SHA-384(secret || canonicalRequest)
~~~

**không tương đương HMAC**. Các cách ghép secret/message trực tiếp không có bảo đảm thiết kế tương tự HMAC, và tùy cấu trúc hàm băm có thể tạo điều kiện cho các kiểu tấn công như length extension hoặc lỗi nhập nhằng thông điệp.

Đừng thay HMAC bằng SHA-384 có thêm secret ở đầu/cuối chuỗi, hoặc dùng `hashCode()` của Java. Thuật toán chuẩn cần được khởi tạo qua `Mac.getInstance("HmacSHA384")`.

## 4. HMAC-SHA384 bảo vệ điều gì và còn thiếu điều gì?

Giả sử verifier nhận một canonical request byte `M` và tag `T`. Việc kiểm tra thành công có ý nghĩa **tag khớp với secret đã được chọn cho chính `M`**. Từ đó có thể kết luận những trường *được ký* chưa bị sửa mà không làm sai HMAC, nếu secret chưa bị lộ.

Những giới hạn quan trọng:

| Thuộc tính | HMAC-SHA384 có tự bảo đảm? | Cần thêm gì? |
| --- | --- | --- |
| Toàn vẹn của byte đã ký | Có | Canonicalization phải đầy đủ và thống nhất |
| Bằng chứng sở hữu shared secret | Có, có điều kiện | Tra cứu `keyId` tin cậy, bảo vệ và phân tách khóa |
| Bí mật thông điệp | **Không** | HTTPS/TLS; mã hóa payload nếu threat model yêu cầu |
| Request chưa từng được gửi | **Không** | Timestamp, nonce và replay store nguyên tử |
| Client được phép sửa một đơn hàng | **Không** | Authorization theo principal/action/resource/tenant |
| Chống chối bỏ giữa client và server | **Không** | Chữ ký bất đối xứng theo yêu cầu pháp lý/chứng cứ phù hợp |
| Ngăn lạm dụng từ client có secret thật | **Không** | Rate limit, quota, kiểm soát nghiệp vụ, audit |
| Giữ hệ thống sẵn sàng | **Không** | Giới hạn body/header, timeout, bảo vệ lookup/nonce store |

HMAC-SHA384 **không mạnh lên theo cách giải quyết tất cả các vấn đề trên** chỉ nhờ tag 384 bit. Nếu canonical request bỏ sót `tenantId` mà handler sử dụng, attacker có thể thay trường đó mà HMAC vẫn đúng. Nếu một partner có khóa hợp lệ nhưng truy cập tài nguyên tenant khác, verifier phải **xác thực khóa thành công rồi phân quyền từ chối**.

## 5. Định dạng chữ ký và hợp đồng thuật toán

### 5.1. Đầu ra 48 byte có nhiều cách biểu diễn

HMAC-SHA384 sinh ra **48 byte nhị phân**. Để đưa vào HTTP header có thể dùng:

| Biểu diễn | Độ dài tag đầy đủ | Ví dụ sử dụng |
| --- | --- | --- |
| Byte gốc | 48 byte | Giao thức nhị phân nội bộ |
| Hex chữ thường | 96 ký tự | Debug/test vector, protocol quy định hex |
| Base64 chuẩn | 64 ký tự | Header theo contract chọn Base64 chuẩn |
| Base64URL không padding | 64 ký tự | Header HTTP gọn và ổn định |

Vì 48 chia hết cho 3, Base64URL của HMAC-SHA384 đầy đủ tự nhiên có **64 ký tự và không cần dấu `=`**. Tuy nhiên, **Base64 chuẩn và Base64URL là hai bảng ký tự khác nhau** (ví dụ `+`, `/` so với `-`, `_`). Hai phía phải thống nhất một encoding duy nhất.

**Ví dụ contract:** `X-Signature` chứa `Base64URL-NoPadding(HMAC-SHA384(secret, canonicalBytes))`. Verifier yêu cầu đúng **64 ký tự Base64URL** và 48 byte sau decode; chữ ký bị cắt hoặc thêm padding phải bị từ chối nếu giao thức không cho phép.

### 5.2. Có nên rút ngắn tag không?

Một số protocol định nghĩa tag HMAC được cắt bớt để giảm kích thước. Việc cắt tag cần được **ấn định rõ thuật toán, số byte, phạm vi bảo mật và chính sách chấp nhận**; không cho client tự yêu cầu “kiểm tra chỉ 8 byte đầu”. Với API HTTP thông thường, **ưu tiên dùng đầy đủ 48 byte** để tránh phức tạp và bất đồng độ dài.

Không so sánh `startsWith(...)`, không cho “partial match”, và không tự thử cả HMAC-SHA256/HMAC-SHA384 theo độ dài signature. Nếu cần hỗ trợ hai thuật toán để di trú, phải dùng **protocol/key version được server kiểm soát**, với whitelist và lịch thu hồi minh bạch.

### 5.3. So sánh HMAC-SHA256, HMAC-SHA384 và HMAC-SHA512

| Thuộc tính | HMAC-SHA256 | HMAC-SHA384 | HMAC-SHA512 |
| --- | --- | --- | --- |
| Hash nền | SHA-256 | SHA-384 | SHA-512 |
| Hash block size | 64 byte | 128 byte | 128 byte |
| Tag đầy đủ | 32 byte | **48 byte** | 64 byte |
| Hex tag đầy đủ | 64 ký tự | **96 ký tự** | 128 ký tự |
| Base64URL không padding | 43 ký tự | **64 ký tự** | 86 ký tự |
| Java JCA | `HmacSHA256` | `HmacSHA384` | `HmacSHA512` |

Không nên suy ra rằng tag 48 byte tạo ra “384 bit bảo mật hiệu dụng” độc lập với entropy của secret, mô hình đe dọa và cách quản lý khóa. Độ dài tag ảnh hưởng đến xác suất đoán trúng tag; sức mạnh thực tế còn bị giới hạn bởi **độ mạnh khóa, cách cấp phát secret, bảo mật endpoint và thiết kế protocol**.

HMAC-SHA256 đã có mức an toàn rất cao cho phần lớn API thông thường. Có thể chọn HMAC-SHA384 khi đáp ứng tiêu chuẩn/cấu hình đã thống nhất, yêu cầu tương thích hoặc định hướng thuật toán của tổ chức. Hiệu năng tùy CPU, JCA provider và tải thực tế; cần benchmark trên môi trường đích thay vì cho rằng SHA-384 luôn nhanh hoặc chậm hơn SHA-256.

## 6. Thiết kế canonical HTTP request dùng HMAC-SHA384

**Canonical request** là dãy byte chuẩn mà client ký và server tái tạo. Với HMAC-SHA384, khác biệt một byte trong dữ liệu đã ký sẽ làm tag thay đổi theo kỳ vọng mật mã. Vì vậy, phần khó nhất thường không phải hàm `Mac` mà là thống nhất **exact bytes** của HTTP request.

### 6.1. Các thành phần phải được quyết định trước

Một hợp đồng ký cần định nghĩa:

| Thành phần | Ví dụ quy tắc bắt buộc |
| --- | --- |
| Phiên bản | Prefix cố định `HMAC-REQUEST-V1`; không chấp nhận phiên bản không hỗ trợ |
| MAC algorithm | `HmacSHA384`; không để người gọi chỉ định `alg=none` |
| Method | Dùng method đã xác minh; format viết hoa chuẩn được contract quy định |
| URI path | Đường dẫn raw/canonical, percent-encoding, dấu slash, dot segment, Unicode |
| Query | Sort theo quy tắc byte xác định; giữ hay từ chối tham số trùng; `+` và `%20` |
| Audience | Định danh service ổn định, tránh dùng nhầm cùng credential ở API khác |
| Signed headers | Danh sách tên chuẩn hóa, format khoảng trắng, header lặp và thứ tự |
| `keyId` | Một ID duy nhất để chọn đúng secret, ràng buộc trong canonical request |
| `timestamp` | Đơn vị (ví dụ Unix seconds), định dạng, cửa sổ chấp nhận |
| `nonce` | Cú pháp, entropy, phạm vi duy nhất và TTL chống replay |
| Body digest | Dùng SHA-384 hay SHA-256; hash **đúng raw body bytes** ở ranh giới ký |
| Byte encoding | UTF-8, LF `\n`, dấu phân cách, có/không LF cuối |
| Signature encoding | Ví dụ Base64URL không padding của **48 byte** HMAC |

Cùng một JSON có thể được serialize với thứ tự trường khác nhau, thêm whitespace hoặc chuyển Unicode escapes. Nếu protocol hash raw body bytes, việc parse/serialize lại JSON ở gateway hoặc server trước khi tính hash sẽ làm sai chữ ký.

### 6.2. Request ví dụ

Giả sử contract quyết định ký method, path, query đã canonicalize, audience, `Content-Type`, `X-Key-Id`, `X-Timestamp`, `X-Nonce` và SHA-384 của raw UTF-8 body:

~~~http
POST /v1/orders?currency=VND&item=a%2Bb HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a:mac-v3
X-Timestamp: 1790000000
X-Nonce: 4a0b876ee2ba539dbec96ab30f6380a7
X-Signature: <base64url-of-48-byte-hmac>

{"sku":"A+B","quantity":2}
~~~

Giá trị timestamp và signature ở đây chỉ để minh họa protocol, **không phải credential/request có thể sử dụng trực tiếp**.

Canonical string minh họa (mỗi dòng nối bằng **LF**, **không có LF cuối**) là:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
currency=VND&item=a%2Bb
audience:orders-api
content-type:application/json
x-key-id:partner-a:mac-v3
x-timestamp:1790000000
x-nonce:4a0b876ee2ba539dbec96ab30f6380a7
body-sha384:<96-lowercase-hex-of-raw-body>
~~~

Thay `<96-lowercase-hex-of-raw-body>` bằng đúng 96 ký tự hex của:

~~~text
SHA-384(UTF8('{"sku":"A+B","quantity":2}'))
~~~

Đây là phép hash **trên raw body bytes**, không phải HMAC. Sau đó:

~~~text
canonicalBytes = UTF8(canonicalString)
rawTag         = HMAC-SHA384(K_mac, canonicalBytes)
X-Signature    = Base64URLWithoutPadding(rawTag)
~~~

Với request không có body, contract có thể dùng SHA-384 của dãy byte rỗng. Không dùng chuỗi chữ `"null"` hay JSON `{}` thay cho body rỗng nếu contract không quy định vậy.

### 6.3. Vì sao cần ký cả key ID và audience?

**`X-Key-Id`** chỉ là định danh giúp server chọn secret, **không phải secret**. Đưa `keyId` vào canonical bytes ràng buộc request với chính credential được công bố. **Audience** ràng buộc request với đích sử dụng cụ thể để tránh dùng chung khóa giữa nhiều dịch vụ dẫn đến phát lại hoặc xác minh sai bối cảnh.

Ví dụ, key của `orders-api` không nên được dùng để ký request cho `billing-api` ngay cả khi hai service tình cờ có endpoint cùng đường dẫn. Phía server nên lưu `keyId → secretRef, principal, audience, status, validity` và kiểm tra tất cả metadata trước khi cho phép request đi tiếp.

## 7. Quy trình ký ở client và xác minh ở server

### 7.1. Phía client

~~~mermaid
flowchart TD
    A[Tạo HTTP request] --> B[Chọn keyId và secret HMAC-SHA384]
    B --> C[Tạo timestamp và nonce mới]
    C --> D[Chốt exact raw body bytes]
    D --> E[Tính SHA-384 body digest]
    E --> F[Canonicalize method, URI, headers, audience, digest]
    F --> G[HMAC-SHA384 của canonical bytes]
    G --> H[Base64URL 48-byte tag và gửi HTTPS]
~~~

Client nên giữ nguyên các byte đã hash khi HTTP library thực sự gửi request. Không nên tính digest trên đối tượng JSON rồi để một serializer khác tự quyết định byte của body.

### 7.2. Phía server

~~~mermaid
flowchart TD
    R[Nhận HTTP request] --> V[Kiểm tra cấu trúc/giới hạn đầu vào]
    V --> K[Tra cứu chính xác keyId và secret đang hiệu lực]
    K --> T[Kiểm tra timestamp trong cửa sổ cho phép]
    T --> C[Tạo canonical request từ byte tại verifier]
    C --> M[Tính HMAC-SHA384 bằng secret của keyId]
    M --> Q{Tag 48 byte có khớp?}
    Q -->|Không| X[Từ chối xác thực]
    Q -->|Có| N{Nonce mới? Atomically store}
    N -->|Trùng| X
    N -->|Mới| P[Tạo principal tin cậy]
    P --> A{Được phép trên action/resource/tenant?}
    A -->|Không| F[Từ chối phân quyền]
    A -->|Có| B[Idempotency, validation và business handler]
~~~

Quy tắc an toàn:

1. **Kiểm tra format sớm:** method/URI, kích thước body, header lặp, `keyId`, timestamp, nonce và signature phải thỏa contract.
2. **Tra key record theo exact `keyId`:** kiểm tra trạng thái, thuật toán, audience và thời hạn; không dò tất cả secret đến khi có tag khớp.
3. **Dùng đúng canonical bytes:** từ cùng biểu diễn method/path/query/header/body như client; kiểm tra cả digest body đã ký.
4. **Từ chối nếu tag sai:** chỉ chấp nhận tag đúng độ dài 48 byte và đúng encoding; thực hiện so sánh byte an toàn.
5. **Chống replay sau xác minh MAC:** nonce phải được ghi với thao tác “set if absent” nguyên tử trong kho chia sẻ giữa các instance; không được “check rồi insert” tách rời.
6. **Tạo principal và phân quyền:** principal đến từ key record/server policy, không đến từ header tự khai. Kiểm tra action, resource, tenant và scope trước nghiệp vụ.

HMAC-SHA384 không tự chống replay. Timestamp được ký chỉ giới hạn tuổi request. Nếu cho phép timestamp trong khoảng `±300 giây`, cùng một request vẫn có thể được gửi lại nhiều lần trong cửa sổ đó; nonce store phải chặn. TTL nonce cần che phủ **toàn bộ khoảng thời gian timestamp còn được chấp nhận**: dùng TTL đúng 300 giây từ lần nhận đầu có thể quá ngắn khi request được nhận sớm. Nên tính TTL dựa trên thời hạn cuối của timestamp hoặc dùng ít nhất khoảng hai lần cửa sổ cộng biên dự phòng tùy chính sách.

Nếu nonce store không sẵn sàng, API nhạy cảm cần có chính sách fail closed; không tự bypass lớp chống replay để “duy trì” hoạt động. Retry hợp lệ với timestamp/nonce mới vẫn có thể lặp tác động nghiệp vụ nên cần cơ chế idempotency riêng.

## 8. Java 17: HMAC-SHA384 bằng JCA

Java cung cấp provider API chuẩn:

- `Mac.getInstance("HmacSHA384")` để tính HMAC.
- `MessageDigest.getInstance("SHA-384")` để tính body hash không có khóa.
- `SecretKeySpec(secret, "HmacSHA384")` cho secret đã được cấp phát.
- `Base64.getUrlEncoder().withoutPadding()` để encode tag.
- `MessageDigest.isEqual(expected, supplied)` để so sánh tag byte sau khi validate độ dài.

### 8.1. Ví dụ hoàn chỉnh về primitive và canonical bytes

Mã sau định nghĩa **một định dạng canonical cố định để minh họa**. Đầu vào `canonicalPath`, `canonicalQuery` và header values phải đã được kiểm tra/chuẩn hóa theo hợp đồng ở tầng HTTP; đừng xem hàm nối chuỗi này là parser HTTP production.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha384Request {
    private static final Pattern SIGNATURE_FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{64}");
    private static final int TAG_BYTES = 48;

    private HmacSha384Request() {}

    // SHA-384 dùng cho raw body bytes, KHÔNG phải MAC.
    public static String bodySha384Hex(byte[] rawBody)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-384")
                .digest(rawBody);
        return HexFormat.of().formatHex(digest);
    }

    // Định dạng minh họa, chỉ sử dụng các giá trị ĐÃ canonicalize.
    // Hợp đồng: UTF-8, dấu xuống dòng LF và không có LF cuối.
    public static byte[] canonicalRequest(
            String method,
            String canonicalPath,
            String canonicalQuery,
            String audience,
            String contentType,
            String keyId,
            long timestampSeconds,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:" + audience,
                "content-type:" + contentType,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestampSeconds,
                "x-nonce:" + nonce,
                "body-sha384:" + bodySha384Hex(rawBody));

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] computeTag(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA384");
        mac.init(new SecretKeySpec(secret, "HmacSHA384"));
        return mac.doFinal(canonicalBytes);
    }

    public static String sign(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        byte[] tag = computeTag(secret, canonicalBytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag);
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes, String signature)
            throws GeneralSecurityException {
        if (signature == null
                || !SIGNATURE_FORMAT.matcher(signature).matches()) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != TAG_BYTES) {
            return false;
        }

        byte[] expected = computeTag(secret, canonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Các ranh giới cố ý của ví dụ:**

- Hàm `canonicalRequest` là bước **định dạng byte cuối cùng**, không thay thế quy trình chống request smuggling, kiểm tra header trùng, chuẩn hóa percent-encoding/path/query và body buffering.
- `verify` chỉ kiểm tra **HMAC**. Nó chưa lấy secret theo `keyId`, chưa xét trạng thái khóa, timestamp, nonce và quyền truy cập. Không cho phép business handler chỉ dựa vào `verify(...) == true`.
- Secret cần là random bytes đủ mạnh, được bảo vệ trong kho khóa; không tạo từ password dễ đoán hoặc hardcode vào source.
- Mã không log secret, tag gốc hay plaintext nhạy cảm; production cần giới hạn tài nguyên, lỗi ra ngoài nhất quán và giám sát.
- Nếu cần xử lý body streaming lớn, có thể hash body theo từng chunk bằng `MessageDigest.update`. Kết quả hash phải ứng với **đúng dãy byte được gửi hoặc đã quy định ở điểm xác minh**.

### 8.2. Vì sao không dùng `String.equals` cho tag?

Tag HMAC là dữ liệu mật mã. So sánh các chuỗi theo thời gian phụ thuộc vị trí khác nhau có thể tạo kênh rò rỉ timing trong những điều kiện nhất định. Trong Java, sau khi đã decode và kiểm tra độ dài hợp lệ, dùng `MessageDigest.isEqual` để so sánh tag byte kỳ vọng với tag nhận.

Cần **cố định encoding và độ dài** trước khi so sánh; không được chấp nhận thêm ký tự `=`, chữ ký cắt ngắn hoặc nhiều cách diễn giải cùng một tag nếu contract chỉ cho Base64URL 64 ký tự.

## 9. Vector kiểm thử chuẩn theo RFC 4231

**Known-answer test** là cách xác nhận thư viện tạo đúng HMAC-SHA384 trước khi kiểm thử các phần HTTP/canonicalization. RFC 4231 có các vector cho HMAC-SHA-224/256/384/512.

**Test case 1** của HMAC-SHA384:

~~~text
Key (hex)       = 0b lặp lại 20 byte
Data (ASCII)    = Hi There

Expected HMAC-SHA384 (hex, 48 byte) =
afd03944d84895626b0825f4ab46907f
15f9dadbe4101ec682aa034c7cebc59c
faea9ea9076ede7f4af152e8b2fa9cb6
~~~

Ba dòng kết quả phải **nối liền** thành chuỗi hex 96 ký tự, không thêm newline. Khóa test 20 byte là dữ liệu của vector chuẩn, **không phải khuyến nghị về độ dài secret production**.

Có thể tự kiểm tra primitive bằng Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

byte[] testKey = new byte[20];
Arrays.fill(testKey, (byte) 0x0b);

byte[] testData = "Hi There".getBytes(StandardCharsets.US_ASCII);
String actualHex = HexFormat.of().formatHex(
        HmacSha384Request.computeTag(testKey, testData));

String expectedHex =
        "afd03944d84895626b0825f4ab46907f"
      + "15f9dadbe4101ec682aa034c7cebc59c"
      + "faea9ea9076ede7f4af152e8b2fa9cb6";

if (!actualHex.equals(expectedHex)) {
    throw new AssertionError("HMAC-SHA384 test vector mismatch");
}
~~~

Khi vector chuẩn PASS mà signature HTTP vẫn sai, nguyên nhân thường nằm ở **canonical bytes, encoding, body hash, secret version, proxy hoặc header parsing**, chứ không phải công thức HMAC.

### 9.1. Vector HMAC chưa thay thế kiểm thử HTTP

RFC 4231 chỉ xác minh primitive HMAC trên thông điệp byte xác định. Nó **không kiểm tra** cách framework đọc URI, raw query, header, body hoặc cách gateway rewrite request.

Để xác nhận giao thức HTTP, hai phía nên có thêm **cross-language test vectors** gồm:

- Request HTTP gốc, quy tắc canonicalization và canonical string kỳ vọng.
- SHA-384 body digest kỳ vọng.
- Key ID và secret thử nghiệm (chỉ dùng trong test).
- HMAC tag Base64URL kỳ vọng.
- Kết quả chấp nhận/từ chối của từng biến thể request.

Đặc biệt, cần so sánh **canonical bytes** của Java client với verifier ở server trước khi điều tra vì sao HMAC tag khác nhau.

## 10. Quản lý khóa, key ID và key rotation với HMAC-SHA384

HMAC-SHA384 cần **shared secret** mà cả client và server đều có quyền sử dụng. Khi key bị lộ, attacker có thể tạo request mới có tag hợp lệ. Chuyển từ SHA-256 sang SHA-384 không khắc phục được sự cố lộ khóa.

### 10.1. Key record gắn thuật toán vào credential

Một bản ghi ở server có thể chứa:

~~~yaml
keyId: partner-a:mac-v3
principalId: partner-a-service
audience: orders-api
environment: production
macAlgorithm: HmacSHA384
secretRef: secrets/orders/partner-a/mac-v3
status: ACTIVE
notBefore: "2026-11-01T00:00:00Z"
acceptUntil: "2027-02-01T00:00:00Z"
permissions:
  - orders:create
~~~

Đây là cấu trúc **minh họa**; `secretRef` không phải secret thật. Server tìm bản ghi bằng ID chính xác, kiểm tra trạng thái, thời hạn, audience và thuật toán đã được cấp. Client không được tự chọn thuật toán thông qua header để làm server chuyển sang thuật toán yếu/không được cấu hình.

Nên:

- Cấp một credential riêng cho mỗi client/workload, môi trường và audience khi phù hợp.
- Tạo secret ngẫu nhiên bằng CSPRNG (ví dụ 256 bit hoặc hơn theo chính sách), không dùng chuỗi đoán được.
- Lưu secret trong secret manager/HSM hoặc cơ chế an toàn tương đương; giới hạn quyền đọc và audit.
- Không ghi secret vào Git, log, trace, URL hay response.
- Hạn chế khả năng cùng một khóa bị dùng ở nhiều dịch vụ khác nhau; nếu bất khả kháng phải ràng buộc audience và principal rõ ràng.

### 10.2. Rotation không nên đổi secret dưới cùng một key ID

Ví dụ trong giai đoạn rotation:

~~~text
principal: partner-a-service

keyId: partner-a:mac-v2  -> HmacSHA384, RETIRING, secret version 2
keyId: partner-a:mac-v3  -> HmacSHA384, ACTIVE,   secret version 3
~~~

Quy trình:

1. Cấp secret mới và **key ID mới**; tạo record v3 với phạm vi quyền/audience đã xét duyệt.
2. Phân phối v3 an toàn; triển khai registry và cache đồng bộ trên mọi verifier.
3. Chuyển client sang ký bằng v3, theo dõi request còn dùng v2.
4. Giới hạn thời gian overlap; sau đó thu hồi v2 và vô hiệu hóa bản cache cũ.
5. Khi nghi key v2 lộ, ưu tiên thu hồi theo phương án ứng phó sự cố, không giữ overlap chỉ vì thuận tiện.

Nếu cần **di trú HMAC-SHA256 sang HMAC-SHA384**, nên tạo record/credential/version tương ứng và kiểm soát rõ thuật toán trên server. Không “thử HMAC-SHA256 nếu HMAC-SHA384 thất bại” như một fallback tự do, vì điều đó làm phức tạp policy và có thể dẫn đến downgrade.

### 10.3. HMAC không tạo bằng chứng chống chối bỏ

Client và server **cùng biết secret**, nên cả hai về nguyên tắc đều có khả năng tạo tag HMAC hợp lệ. Khi cần chứng minh độc lập cho bên thứ ba “chỉ client cụ thể có thể ký thông điệp”, cần xem xét chữ ký số bất đối xứng và mô hình quản lý private key phù hợp. HMAC-SHA384 không thay thế được yêu cầu này chỉ vì tag dài hơn.

## 11. Proxy/gateway và rủi ro sai khác canonicalization

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Reverse proxy / API Gateway
    participant V as HMAC verifier
    participant A as Business API

    C->>G: HTTPS request + keyId + timestamp + nonce + HMAC-SHA384 tag
    Note over G: Có thể terminate TLS và rewrite URI/header/body
    G->>V: Request đã được chuyển tiếp
    V->>V: Tạo lại canonical request
    V->>V: Verify HMAC-SHA384 + chống replay
    V->>A: Principal tin cậy + request
    A->>A: Authorization và xử lý nghiệp vụ
    A-->>C: HTTP response
~~~

Trong thực tế, proxy/gateway có thể:

- Đổi path prefix (`/api/v1/orders` thành `/v1/orders`) hoặc xử lý `%2F` và `%2e` khác client.
- Gộp query trùng tên, đổi thứ tự query, giải nghĩa `+` thành dấu cách.
- Thêm, bỏ hoặc hợp nhất header, kể cả `Host`, `X-Forwarded-*`, `X-Key-Id`.
- Decode/chuyển mã body, giải nén hoặc serialize lại JSON.
- Retry hoặc route request sang backend khác trong lúc nonce store chưa đồng bộ.

Các biến đổi này có thể khiến request hợp lệ bị từ chối. Nghiêm trọng hơn, nếu verifier xác minh theo một cách parse nhưng router/handler xử lý theo cách khác, có nguy cơ **xác thực một request nhưng thực thi ý nghĩa khác**.

### 11.1. Hai mô hình xác minh

| Điểm xác minh | Điều kiện |
| --- | --- |
| Tại gateway | Gateway kiểm tra HMAC trên request ở ranh giới đã định nghĩa, tạo principal tin cậy; backend chỉ nhận principal qua kênh nội bộ được bảo vệ, header định danh từ client phải bị xóa |
| Tại backend | Request được proxy chuyển tiếp theo đúng byte/biểu diễn mà canonical contract đã chọn; path rewrite và body transformation phải được xác định và kiểm thử |

Cả hai mô hình đều cần xác định **audience của request**, xử lý header trùng/mơ hồ nhất quán và tránh tin `X-Forwarded-*` do client Internet tự khai. Nếu gateway đã terminate TLS, một kết nối TLS thứ hai tới backend bảo vệ chặng tiếp theo; HMAC **không mã hóa body**.

### 11.2. Lỗi điển hình

Client ký:

~~~text
POST
/v1/orders/item%2Fspecial
~~~

Gateway decode path thành:

~~~text
/v1/orders/item/special
~~~

Nếu verifier dùng raw path còn router dùng path đã decode, hai thành phần có thể không đồng ý về tài nguyên. Không nên sửa lỗi bằng cách “thử cả hai path cho đến khi HMAC đúng”. Thay vào đó, cần chốt một quy tắc canonical duy nhất và **từ chối encoding không thể xử lý thống nhất**.

## 12. Authentication và authorization vẫn tách biệt

Ví dụ một partner có credential HMAC-SHA384 hợp lệ với principal `partner-A`. Request sau có HMAC đúng:

~~~http
DELETE /v1/tenants/tenant-B/orders/order-99 HTTP/1.1
X-Key-Id: partner-A:mac-v3
X-Timestamp: 1790000000
X-Nonce: 4a0b876ee2ba539dbec96ab30f6380a7
X-Signature: <base64url-of-48-byte-hmac>
~~~

Đúng MAC có thể chứng minh request đến từ bên có `partner-A:mac-v3` và các byte đã ký còn nguyên. Nó **không chứng minh partner-A có quyền xóa đơn của tenant B**. Server phải ánh xạ key ID tới principal đã xác thực và kiểm tra scope, tenant, resource ownership và business policy.

Không dùng một header tự khai như `X-Tenant-Id` hoặc `X-User-Id` để quyết định quyền chỉ vì request được HMAC ký. Nếu client A có khóa thật, client A vẫn có thể **chủ động ký thông tin tự khai sai**. Nên dùng tenant và quyền được lưu tại server làm nguồn sự thật.

## 13. Lỗi triển khai HMAC-SHA384 thường gặp

### 13.1. Nhầm HMAC với hash thường

~~~text
# Sai về mục đích authentication:
SHA-384(canonicalRequest)

# Đúng về primitive MAC:
HMAC-SHA384(secret, canonicalRequest)
~~~

Thêm SHA-384 body digest mà không HMAC trên canonical request vẫn không xác thực nguồn gửi.

### 13.2. Tính sai số byte tag

HMAC-SHA384 **48 byte**, không phải 384 byte. Nếu protocol dùng hex sẽ là **96 ký tự**, Base64URL không padding là **64 ký tự**. Độ dài sai phải bị từ chối; không so sánh phần đầu chuỗi hoặc tự cắt đến độ dài tương đương SHA-256.

### 13.3. Secret yếu hoặc dùng lại ở nhiều client

Nếu secret là password dễ đoán hoặc bị hardcode trong mobile/web client public, attacker có thể lấy khóa và tạo tag hợp lệ. Dùng credential riêng cho server-to-server, quản lý lifecycle và thu hồi.

### 13.4. Không ký trường có ảnh hưởng đến nghiệp vụ

Nếu verifier chỉ ký body nhưng router dùng path/query để quyết định đối tượng, attacker có thể thay URI mà tag vẫn đúng. Cần đưa mọi phần quyết định ý nghĩa request vào contract ký hoặc suy ra từ principal tin cậy.

### 13.5. Không chống replay

Một signed request bị capture vẫn có tag HMAC-SHA384 hợp lệ sau khi gửi lại. Cần timestamp đã ký, nonce đủ entropy và kho lưu nonce nguyên tử giữa các node. Không đồng nhất nonce mật mã với idempotency của thanh toán/đơn hàng.

### 13.6. Chấp nhận thuật toán dựa trên input của client

Không cho request tự tuyên bố `alg=HmacSHA256`/`none` rồi server làm theo. Thuật toán được chọn từ contract/key record server-side; nếu hỗ trợ nhiều phiên bản phải có quy tắc lựa chọn và ngày thu hồi.

### 13.7. Canonicalization theo object đã parse

JSON serializer, URL decoder hoặc HTTP library có thể thay đổi byte. Hash `rawBodyBytes` đúng hợp đồng; nếu muốn canonical JSON thì phải dùng chuẩn canonicalization được quy định, không dùng `toString()` của object.

### 13.8. Dùng HMAC thay TLS

HMAC không che nội dung body/header và không xác thực endpoint TLS. Vẫn phải dùng HTTPS cho các chặng mạng cần bảo vệ, quản lý secret an toàn và không log nội dung nhạy cảm.

### 13.9. Lộ thông tin khi trả lỗi

Response như “key ID hợp lệ nhưng signature sai” có thể giúp dò credential. Có thể dùng một mã lỗi xác thực chung ở bên ngoài, đồng thời thu thập metric nội bộ phân biệt `unknown_key`, `bad_signature`, `expired_timestamp`, `replayed_nonce` hoặc `revoked_key` mà không lộ secret.

## 14. Ma trận kiểm thử HMAC-SHA384 cho HTTP request

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| RFC 4231 vector | Key 0x0b × 20, message `Hi There` | Tag hex đúng 96 ký tự theo vector |
| Full tag length | Ký bằng HMAC-SHA384 | Output 48 byte, Base64URL 64 ký tự |
| Chữ ký đúng | Secret, method, URI, header, body nhất quán | Verifier chấp nhận MAC; tiếp tục freshness/authorization |
| Chữ ký HMAC-SHA256 | Gửi 32-byte tag tới contract HMAC-SHA384 | Từ chối do algorithm/tag length không khớp |
| Sửa một byte body | Sửa `quantity` nhưng giữ tag cũ | Từ chối vì body digest/canonical MAC thay đổi |
| Sửa method | `POST` thành `DELETE` | Từ chối nếu method được ký |
| Sửa path/query | Thay target hoặc query được ký | Từ chối |
| Sửa `X-Key-Id` | Tráo credential ID sau khi ký | Từ chối |
| Sửa `X-Timestamp` / `X-Nonce` | Đổi header mà giữ tag cũ | Từ chối |
| Timestamp ngoài cửa sổ | Request quá cũ/quá xa tương lai | Từ chối trước khi nghiệp vụ |
| Replay nguyên request | Gửi lại cùng nonce sau khi request được chấp nhận | Từ chối lần sau |
| Concurrent replay | Hai node nhận cùng nonce đồng thời | Tối đa một request vượt qua nonce gate |
| Nonce store mất kết nối | Giả lập lỗi store | Fail closed theo chính sách API nhạy cảm |
| Header trùng | Hai `X-Key-Id` hoặc `X-Timestamp` | Từ chối request mơ hồ |
| Query trùng/encoded | `a=1&a=2`, `%2F`, `+`, Unicode | Contract xử lý nhất quán hoặc từ chối |
| Gateway rewrite | Request thật đi qua proxy có rewrite | Verifier và router dùng cùng ý nghĩa request |
| Khóa đã thu hồi | MAC đúng với key revoked | Từ chối theo trạng thái credential |
| Rotation hai ID | v2/v3 trong overlap hợp lệ | Mỗi ID dùng đúng secret, log/audit phân biệt |
| Sai audience | Dùng khóa orders cho billing | Từ chối dù tag có thể tính được |
| Đúng MAC, sai tenant | Partner A đụng tài nguyên tenant B | Authentication có thể đúng; authorization từ chối |
| Signature bị cắt / padding | 40 ký tự, 64 ký tự cộng dấu `=`, ký tự không phải Base64URL | Từ chối theo protocol |
| Body rất lớn | Vượt max body/timeouts | Từ chối sớm, không cạn RAM/CPU |

**Phạm vi kiểm thử:** primitive HMAC, canonicalization, HTTP verifier, key registry, nonce store, authorization và tuyến client–proxy–backend. Không coi việc vector mật mã PASS là bằng chứng toàn bộ giao thức đã an toàn.

## 15. Tình huống thực hành: nâng cấp webhook từ HMAC-SHA256 lên HMAC-SHA384

Một hệ thống nhận webhook từ nhiều đối tác đang sử dụng `HmacSHA256`. Một số consumer mới được cấp `HmacSHA384` theo chính sách tích hợp. Các webhook đi qua gateway, sau đó backend cập nhật trạng thái đơn hàng.

**Mục tiêu:** hỗ trợ HMAC-SHA384 với chữ ký Base64URL 64 ký tự, không bỏ qua replay protection, không nhầm secret hay tenant, và có cơ chế di trú rõ ràng.

### 15.1. Phương án triển khai

1. Định nghĩa **contract version** cho HMAC-SHA384, ví dụ `HMAC-REQUEST-V2`, quy định field canonical và body hash rõ ràng.
2. Cấp `keyId` mới gắn với `macAlgorithm=HmacSHA384` và secret ngẫu nhiên; lưu `principalId`, `audience`, `status` và `validity` trong registry.
3. Client tính canonical request V2, dùng JCA hoặc thư viện tương ứng để tính tag 48 byte, encode Base64URL.
4. Verifier đọc `keyId`, chọn đúng key record và protocol version được cấp, tạo canonical bytes, xác minh tag 48 byte.
5. Chỉ sau khi MAC và timestamp hợp lệ mới atomically ghi nonce; lấy principal từ registry và kiểm tra quyền cập nhật order thuộc partner.
6. Gateway được cấu hình không biến đổi các byte đã ký ngoài quy tắc cho phép; chạy test end-to-end cho path, query và body.
7. Di trú consumer cũ có kiểm soát; không thử nhiều thuật toán theo cách opportunistic. Kết thúc overlap thì thu hồi credential/protocol cũ theo lịch.

### 15.2. Những tình huống cần trả lời

**Tình huống A:** Request dùng `HmacSHA384` nhưng header chữ ký chỉ có 43 ký tự Base64URL.  
**Phân tích:** 43 ký tự thường tương ứng tag HMAC-SHA256 32 byte. Trong contract HMAC-SHA384 đầy đủ, phải từ chối. Không tự đoán thuật toán chỉ từ signature.

**Tình huống B:** Ký bằng SHA-384 body digest nhưng server dùng SHA-256 body digest.  
**Phân tích:** HMAC tag không khớp vì canonical bytes khác nhau. Không phải bug của SHA-384/HMAC mà là **khác hợp đồng ký**.

**Tình huống C:** Gateway thay đổi thứ tự thuộc tính JSON sau khi client ký.  
**Phân tích:** Nếu ký raw body hash, chữ ký sai. Phải kiểm thử tuyến truyền thực và giữ exact byte body đã định nghĩa.

**Tình huống D:** Request có HMAC-SHA384 hợp lệ, nhưng nonce đã xuất hiện trước đó.  
**Phân tích:** Từ chối replay. HMAC đúng chỉ nói request không bị sửa so với byte đã ký; không nói request chưa từng gửi.

**Tình huống E:** Credential HMAC-SHA384 của tenant A ký request cập nhật đơn tenant B.  
**Phân tích:** Xác thực credential thành công vẫn phải bị **authorization** từ chối.

## 16. Câu hỏi tự kiểm tra

1. **HMAC-SHA384 tạo tag bao nhiêu byte?**  
   **48 byte**. Tag hex là 96 ký tự, Base64URL không padding là 64 ký tự.

2. **SHA-384 có block size bao nhiêu?**  
   **128 byte**, dù digest chỉ dài 48 byte. Trong HMAC, ipad/opad áp dụng trên block 128 byte.

3. **Vì sao `SHA384(secret || message)` không nên dùng thay HMAC-SHA384?**  
   Đó là cấu trúc khác không có bảo đảm giao thức HMAC; phải dùng thuật toán HMAC chuẩn.

4. **Có bắt buộc body digest phải SHA-384 khi MAC là HMAC-SHA384?**  
   Không. Contract có thể chọn body SHA-256 hoặc SHA-384 độc lập với MAC; phải thống nhất rõ giữa hai phía.

5. **Một tag 48 byte hợp lệ có chứng minh request còn mới không?**  
   Không. Cần timestamp đã ký, nonce và kho chống replay nguyên tử.

6. **HMAC-SHA384 có thể dùng thay TLS để giấu thông tin đơn hàng không?**  
   Không. HMAC không mã hóa body. Cần HTTPS/TLS và mã hóa payload khi yêu cầu riêng.

7. **Vì sao hai hệ thống cùng tính HmacSHA384 mà ra tag khác?**  
   Có thể khác secret, UTF-8/LF, URI/query/header canonicalization, body bytes, timestamp, nonce hoặc contract version.

8. **Key ID tồn tại và HMAC đúng có đồng nghĩa client được phép xóa dữ liệu tenant khác không?**  
   Không. Đây là quyết định authorization dựa trên principal và tài nguyên.

## 17. Checklist triển khai thực tế

- [ ] Ghi rõ `HmacSHA384` là MAC algorithm và tag đầy đủ **48 byte**.
- [ ] Cố định Base64URL không padding 64 ký tự hoặc một encoding duy nhất khác đã công bố.
- [ ] Cấp secret đủ ngẫu nhiên, quản lý bằng secret manager, phân tách theo client/audience/môi trường.
- [ ] Key ID trỏ đến credential, principal, thuật toán, trạng thái, hiệu lực và scope được server quản lý.
- [ ] Canonical request có version, method, path, query, header, audience, key ID, timestamp, nonce và body digest cần thiết.
- [ ] SHA-384 body digest tính từ đúng raw body bytes; mọi dấu phân cách, UTF-8/LF và xử lý header trùng được quy định.
- [ ] Verifier dùng `Mac.getInstance("HmacSHA384")`, kiểm tra tag length/encoding và so sánh byte an toàn.
- [ ] Timestamp được ràng buộc vào chữ ký; nonce mới được lưu atomically trong shared replay store với TTL đủ dài.
- [ ] Có idempotency nghiệp vụ riêng cho retry; không để retry gây tác động kép.
- [ ] Proxy/gateway, parser HTTP và router cùng diễn giải request; kiểm thử xuyên lớp với các biến thể encoding.
- [ ] Dùng HTTPS/TLS, rate limit, giới hạn kích thước/thời gian và log không lộ secret.
- [ ] Key rotation cấp ID mới, có overlap hữu hạn và thu hồi/cache invalidation rõ ràng.
- [ ] Principal được xác thực phải trải qua authorization trên action/resource/tenant trước khi handler chạy.
- [ ] Có known-answer tests theo RFC 4231 và negative/end-to-end tests cho signature, replay, rotation, gateway.

## 18. Tài liệu tham khảo tiêu chuẩn

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Định nghĩa cấu trúc HMAC tổng quát với `ipad` và `opad`.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512.** Cung cấp vector kiểm thử tham chiếu, trong đó có test case dùng `Hi There`.
- **NIST FIPS 180-4 — Secure Hash Standard (SHS).** Đặc tả SHA-2 bao gồm SHA-384.
- **NIST FIPS 198-1 — The Keyed-Hash Message Authentication Code (HMAC).** Tài liệu tham chiếu về thuật toán HMAC.

**Kết luận:** HMAC-SHA384 là **HMAC dùng SHA-384** với tag 48 byte. Nó giúp bảo vệ tính toàn vẹn và xác thực quyền sở hữu shared secret đối với **đúng những byte được ký**, nhưng an toàn của HTTP request còn phụ thuộc vào canonicalization, khóa, timestamp/nonce, gateway và phân quyền. Khi triển khai bằng Java, hãy dùng thuật toán JCA chuẩn, thống nhất encoding/contract, kiểm thử vector RFC 4231 và xác minh toàn bộ tuyến HTTP trước khi sử dụng trong nghiệp vụ.
