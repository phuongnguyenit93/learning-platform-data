# Header không được ký

Trong xác thực HTTP request bằng HMAC, không phải **mọi header xuất hiện trên request đều được chữ ký bảo vệ**. Nếu hợp đồng ký chỉ chọn một tập header, các header còn lại là **header không được ký** (*unsigned headers*): thay đổi giá trị của chúng thường **không làm thay đổi HMAC**, miễn là các thành phần còn lại của canonical request không đổi.

Điều này có thể hoàn toàn hợp lý. Chẳng hạn, một reverse proxy có thể thay `Connection` hoặc `Content-Length`, hệ thống quan sát có thể sinh `X-Request-Id` mới, và một HTTP client có thể thay `User-Agent`. Nhưng nếu ứng dụng lấy một header không được ký để **quyết định tenant, HTTP method hiệu lực, tài nguyên, số tiền, quyền hay idempotency**, thiết kế có thể để kẻ tấn công thay đổi ý nghĩa request mà chữ ký vẫn hợp lệ.

Bài học thuộc chương **Header canonicalization** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng **shared secret và canonical request** gồm method, URI, header hoặc body theo hợp đồng; đồng thời thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Nguyên tắc trọng tâm:** “Header không được ký” không có nghĩa là header đó luôn vô hại. Một header chỉ nên nằm ngoài HMAC khi hệ thống **không tin nó để đưa ra quyết định bảo mật**, hoặc giá trị đó được bảo vệ bởi **một ranh giới tin cậy độc lập** có kiểm soát. Nếu header ảnh hưởng tới ý nghĩa request hoặc chính sách bảo mật, phải **ký nó, loại bỏ nó, suy ra từ server**, hoặc thiết lập và bảo vệ nó tại một thành phần trung gian tin cậy.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **signed headers**, **unsigned headers**, **signature metadata** và các **thành phần request không phải header**.
2. Giải thích tại sao sửa một unsigned header có thể không ảnh hưởng tới HMAC và khi nào đó là rủi ro.
3. Phân loại header: header ứng dụng ảnh hưởng nghiệp vụ, header quan sát/tracing, header framing/connection, header do gateway thêm, và giá trị chữ ký.
4. Thiết kế một hợp đồng ký có **tập header bắt buộc** và chính sách xử lý header ngoài tập.
5. Xử lý đúng tên header không phân biệt hoa/thường, khoảng trắng, giá trị lặp, header trống và sự khác biệt parser giữa client/proxy/server.
6. Viết Java 17 tạo canonical signed headers và xác minh HMAC-SHA256 trong một contract minh họa.
7. Kiểm thử tampering trên unsigned headers, key rotation, timestamp/nonce, gateway, request smuggling và phân quyền.

## 2. Signed header và unsigned header khác nhau như thế nào?

Giả sử client gửi:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Request-Id: req-100
User-Agent: DemoClient/1.0
X-Signature: <base64url-hmac-tag>

{"orderId":"order-42","amount":125000}
~~~

Một hợp đồng ký minh họa quy định HMAC bao gồm **method**, **canonical path**, **canonical query**, **audience**, **Content-Type**, **X-Key-Id**, **X-Timestamp**, **X-Nonce** và **SHA-256 của raw body**. Trong hợp đồng này:

| Thành phần | Có trong canonical request? | Hệ quả |
| --- | --- | --- |
| `POST` | Có | Sửa method làm sai HMAC |
| `/v1/orders` | Có | Sửa path làm sai HMAC |
| Canonical query | Có | Sửa query có ý nghĩa làm sai HMAC |
| `audience:orders-api` | Có | Ràng buộc request với đích do contract/server xác định |
| `Content-Type: application/json` | Có | Sửa content type làm sai HMAC hoặc bị từ chối theo contract |
| `X-Key-Id` | Có | Sửa key ID làm sai HMAC; server tra đúng key record |
| `X-Timestamp`, `X-Nonce` | Có | Sửa freshness metadata làm sai HMAC |
| Raw body SHA-256 | Có | Sửa body làm sai HMAC |
| `X-Request-Id` | **Không** | Thay ID tracing không làm thay đổi HMAC |
| `User-Agent` | **Không** | Thay chuỗi client tự khai không làm thay đổi HMAC |
| `X-Signature` | **Không**, trong canonical bytes của chính chữ ký đó | Là tag cần so sánh, không phải dữ liệu tự ký |
| `Host` | Không, **trong ví dụ cụ thể** | Chỉ an toàn nếu audience và routing được ràng buộc tin cậy; xem mục 6 |

Lưu ý: **Một header được truyền qua HTTPS không tự động trở thành signed header.** TLS có thể bảo vệ header trên một kết nối, nhưng HMAC ở tầng ứng dụng chỉ bảo vệ những byte đã đưa vào canonical request; tại gateway nơi TLS kết thúc, một số header có thể được thay đổi trước khi tới backend.

### 2.1. “Không ký” là một lựa chọn của hợp đồng, không phải đặc tính cố định của header

`User-Agent` thường không được ký, nhưng về mặt kỹ thuật **có thể** đưa nó vào HMAC. `Content-Type` đôi khi không được ký trong protocol khác, nhưng **nên được bảo vệ** nếu nó quyết định cách parser đọc body.

Không có danh sách toàn cầu kiểu “header A luôn ký, header B không bao giờ ký”. Quyết định phải dựa trên:

- **Request semantics:** Header có thay đổi action, resource, body interpretation, tenant, permission hay idempotency không?
- **Ownership:** Giá trị do client quyết định, server suy ra, hay gateway tin cậy thiết lập?
- **Stability:** Header có thể bị HTTP stack/proxy đổi một cách hợp lệ trên đường truyền không?
- **Security boundary:** Backend có kiểm chứng được header từ nguồn tin cậy và từ chối client giả mạo không?
- **Interoperability:** Client và server có thể tái tạo cùng byte canonical của header đó không?

### 2.2. Ví dụ tampering với unsigned header

Client ký request có:

~~~http
X-Request-Id: req-100
X-Signature: <valid-tag>
~~~

Một trung gian đổi thành:

~~~http
X-Request-Id: req-999
X-Signature: <same-valid-tag>
~~~

Nếu `X-Request-Id` không nằm trong canonical request, HMAC **có thể vẫn hợp lệ**. Điều này chấp nhận được nếu `X-Request-Id` chỉ phục vụ logging/tracing và không ảnh hưởng quyết định nghiệp vụ.

Ngược lại, nếu backend sử dụng `X-Request-Id` làm **idempotency key** để kiểm soát “thanh toán chỉ một lần”, attacker có thể thay giá trị header để tạo thao tác trùng trong khi MAC vẫn đúng. Khi đó phải **ký idempotency key** (hoặc chuyển nó vào signed body), đồng thời vẫn cần kho idempotency phía server.

## 3. Các nhóm header thường không được ký

### 3.1. Header chỉ phục vụ quan sát, telemetry

Ví dụ:

- `User-Agent` — mô tả HTTP client, do caller tự khai.
- `X-Request-Id` — correlation ID, **nếu chỉ phục vụ tracing**.
- `traceparent`, `tracestate` — truyền ngữ cảnh distributed tracing.
- Một số header debug nội bộ không ảnh hưởng handler.

Chúng có thể không được ký khi thay đổi chúng **không thay đổi quyền hay kết quả nghiệp vụ quan trọng**.

Tuy vậy, vẫn cần giới hạn kích thước, kiểm tra cú pháp, tránh log injection và không sử dụng dữ liệu tracing tự khai làm identity. Nếu `traceparent` hoặc correlation ID được dùng làm khóa chống trùng lặp tác vụ, nó **không còn là telemetry thuần túy** và phải được ràng buộc hoặc thay bằng một idempotency key chuyên biệt đã ký.

### 3.2. Header liên quan kết nối và hop-by-hop

Trong HTTP/1.1, một số header dùng để quản lý **kết nối cụ thể** thay vì nội dung end-to-end của thao tác. Ví dụ:

| Header | Vai trò điển hình | Cách xử lý khi ký HMAC |
| --- | --- | --- |
| `Connection` | Khai báo tùy chọn kết nối và connection-specific field names | Thường không ký; HTTP parser/gateway vẫn phải kiểm soát đúng |
| `Keep-Alive` | Thông số duy trì kết nối (trong ngữ cảnh HTTP/1.x) | Thường không ký |
| `Transfer-Encoding` | HTTP/1.1 message framing/transfer coding | Không dùng giá trị client tự khai để quyết định trusted body; xử lý framing nghiêm ngặt |
| `TE` | Khả năng transfer coding/trailer theo ngữ cảnh protocol | Xử lý đúng phiên bản HTTP; không xem là signed business metadata |
| `Trailer` | Khai báo trailer fields theo HTTP framing | Nếu trailer ảnh hưởng dữ liệu ứng dụng thì phải có hợp đồng riêng; không mặc định bỏ qua |
| `Upgrade` | Đề nghị thay đổi giao thức trên kết nối | Thường ngoài hợp đồng HMAC REST request |
| `Proxy-Connection` | Header không chuẩn xuất hiện ở một số hệ thống cũ | Không tin; thường từ chối hoặc xử lý tại proxy |
| `Proxy-Authorization` | Credential gửi tới proxy trong ngữ cảnh riêng | Không dùng như credential ứng dụng tại backend |

Một proxy có thể thêm/bỏ một số header theo từng chặng. Vì vậy, ký raw header bytes này từ client đến backend thường **không bền vững**, nhưng **không ký không có nghĩa là bỏ kiểm tra**.

**Đặc biệt:** `Content-Length` là **trường framing** trong HTTP; không nên mô tả mọi trường hợp của nó là hop-by-hop. Proxy có thể tái tính `Content-Length` khi chuyển HTTP/1.1 ↔ HTTP/2, buffer body hoặc thay framing. Một thiết kế HMAC thường không ký raw `Content-Length`, nhưng phải bảo đảm **đúng entity body bytes** được hash và handler xử lý.

### 3.3. Header do proxy thêm và có thể đổi

Ví dụ:

- `Via`, một số thông tin kết nối và chẩn đoán do proxy thêm.
- `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`.
- `X-Original-URI` hoặc `X-Forwarded-Prefix` do cấu hình gateway sử dụng.

Những trường này thường **không thể được client ký theo giá trị cuối cùng** nếu proxy thêm chúng sau khi client tạo HMAC.

Nhưng đây cũng là nhóm nguy hiểm: chúng có thể ảnh hưởng cách backend xác định **IP client, scheme, host, URL gốc hoặc tenant**. Không được tin các giá trị `X-Forwarded-*` do Internet gửi trực tiếp. Gateway phải **xóa hoặc kiểm soát chuỗi header từ nguồn không tin cậy**, thiết lập metadata đáng tin và bảo vệ chặng gateway–backend.

### 3.4. Header ảnh hưởng đàm phán biểu diễn response

Ví dụ `Accept`, `Accept-Language` hoặc `Accept-Encoding` đôi khi không có trong hợp đồng ký request.

Chúng có thể không ký nếu **chỉ ảnh hưởng biểu diễn response theo chính sách server**, không thể thay đổi dữ liệu được phép truy cập. Tuy nhiên:

- Nếu `Accept` quyết định API trả dữ liệu chi tiết hơn, cần đánh giá lại.
- Nếu `Accept-Language` dùng để chọn chính sách nội dung khác nhau, không mặc nhiên coi là vô hại.
- Nếu `Range` hoặc conditional headers ảnh hưởng lượng dữ liệu được trả về hay cập nhật, cần chính sách ký/ủy quyền tương ứng.
- Cache/CDN phải được cấu hình phù hợp (`Vary`, cache key và kiểm soát quyền); HMAC không tự làm cache an toàn.

## 4. Những header **không thể tùy tiện bỏ khỏi chữ ký**

“Header không được ký” là chủ đề học, không phải khuyến nghị **ký càng ít càng tốt**. Nếu một header do caller quyết định có thể thay đổi **ý nghĩa HTTP operation**, phải ràng buộc nó vào HMAC hoặc không cho client sử dụng.

| Header hoặc nhóm header | Nếu không ký có thể xảy ra gì? | Hướng xử lý |
| --- | --- | --- |
| `Content-Type` | Parser chuyển từ JSON sang form/multipart hoặc cách hiểu body khác | Ký và validate đúng MIME type, hoặc ép fixed parser phía server |
| `Content-Encoding` | Gateway/backend giải nén hay diễn giải body theo đường khác | Ký nếu cho phép; đơn giản hơn là từ chối encoding không được hỗ trợ |
| `X-HTTP-Method-Override` | Handler thực thi `DELETE` dù method được ký là `POST` | Từ chối override hoặc ký **effective method** theo contract thống nhất |
| `X-Tenant-Id`, `X-Account-Id` | Đổi tenant/account dùng cho routing/nghiệp vụ | Không tin làm identity; lấy principal/policy từ server, và ký nếu có vai trò tham số |
| `X-Role`, `X-Scope`, `X-Authenticated-User` | Caller tự khai quyền cao hơn | Không cho caller đặt; phải thiết lập tại trust boundary và kiểm chứng |
| `Idempotency-Key` | Đổi khóa để lách chặn xử lý trùng | Ký hoặc đưa vào signed body, cộng với idempotency store |
| `If-Match` | Đổi điều kiện optimistic concurrency của cập nhật | Ký nếu ảnh hưởng semantics của write operation |
| `X-Api-Version`, `X-Feature-Flag` | Chọn phiên bản API hoặc nhánh xử lý khác | Ký hoặc chốt từ policy phía server |
| `Host` / HTTP/2 `:authority` | Có thể quyết định virtual host, tenant hoặc service được route | Ký canonical authority hoặc dùng signed audience đã ràng buộc với routing thực |
| `X-Signature-Version`, `X-Signed-Headers` | Hạ thấp version hoặc bỏ các field quan trọng khỏi chữ ký | Cố định contract hoặc bảo vệ metadata và áp dụng mandatory signed fields |

Một header có thể được bảo vệ **gián tiếp**: ví dụ client không gửi `X-Tenant-Id`, còn backend lấy tenant từ key record đã xác thực. Khi đó không cần ký header ấy vì nó **không được phép làm nguồn dữ liệu cho quyết định**.

Ngược lại, nếu client gửi `X-Tenant-Id` như một **tham số yêu cầu**, việc ký chỉ chứng minh client muốn tenant đó; vẫn cần authorization chứng minh principal **được phép** thao tác trên tenant đó.

### 4.1. Trường hợp nguy hiểm: sửa Content-Type

Giả sử client ký HMAC chỉ trên method, path và body bytes:

~~~http
POST /v1/payments HTTP/1.1
Content-Type: application/json
X-Signature: <valid-tag>

{"amount":100}
~~~

Kẻ tấn công hoặc proxy thay `Content-Type` thành `application/x-www-form-urlencoded` trong khi giữ body bytes. HMAC vẫn có thể đúng nếu content type không được ký, nhưng lớp parser ứng dụng có thể thay đổi cách xử lý hoặc trả lỗi.

Đây không phải lý do để **mặc định ký mọi header**, mà là lý do phải bảo vệ những header thay đổi parser/ngữ nghĩa. Với endpoint chỉ chấp nhận JSON, cách đơn giản là **ký Content-Type và kiểm tra chính xác giá trị được phép**.

### 4.2. Method override: chữ ký đúng, hành động sai

~~~http
POST /v1/orders/42 HTTP/1.1
X-HTTP-Method-Override: DELETE
X-Signature: <tag-over-POST-and-path>
~~~

Nếu verifier chỉ ký HTTP method là `POST` nhưng router thực thi hành động `DELETE` vì header override, HMAC không bảo vệ **effective action**. Giải pháp an toàn là vô hiệu hóa method override ở API HMAC, hoặc thiết kế signed effective-method contract được cả verifier/router áp dụng.

Không dùng bước “HMAC trên method gốc, authorization trên method đã override” mà không đối chiếu hai cách hiểu.

### 4.3. Conditional request và Range

`If-Match`, `If-Unmodified-Since`, `Range` và các conditional headers có thể ảnh hưởng thao tác được thực thi hoặc response. Nếu endpoint dựa vào các header đó để quyết định **cập nhật có điều kiện** hoặc **phạm vi dữ liệu được tiết lộ**, hãy đánh giá rủi ro và ký chúng khi chúng là đầu vào có ý nghĩa bảo mật.

Nếu API không hỗ trợ conditional/range behavior, có thể **từ chối các header tương ứng** thay vì ký chúng.

## 5. Tại sao `X-Signature` thường không được ký?

Chữ ký HMAC được tạo như sau:

~~~text
canonicalBytes = Canonicalize(method, URI, selectedHeaders, bodyDigest, ...)
signature = HMAC-SHA256(sharedSecret, canonicalBytes)
~~~

Nếu đưa **chính giá trị `X-Signature`** vào `canonicalBytes` rồi lại yêu cầu tính `X-Signature` từ canonical bytes đó, sẽ xuất hiện **phụ thuộc vòng**: muốn tính signature cần biết signature.

Do đó các giao thức HMAC thông thường **loại chính trường mang tag ra khỏi dữ liệu ký**. Server đọc `X-Signature` để decode và so sánh với tag tự tính.

Điều này **không** có nghĩa được bỏ qua việc validate:

- Yêu cầu đúng một giá trị `X-Signature`, không chấp nhận header trùng.
- Kiểm tra cú pháp Base64URL và độ dài tag theo thuật toán/version.
- Không chấp nhận chữ ký bị cắt hoặc encode theo nhiều cách không được protocol cho phép.
- So sánh tag byte bằng cơ chế an toàn như `MessageDigest.isEqual` sau khi decode và kiểm tra độ dài.
- Không lộ chi tiết khóa/nonce qua response; không log full signed request nếu có nguy cơ replay.

### 5.1. Signature metadata khác signature value

Các trường như `X-Key-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature-Version` hoặc `X-Signed-Headers` là **metadata**. Nhiều trường trong đó **phải nằm trong canonical request** vì attacker có thể sửa chúng để đổi khóa, né chống replay hoặc hạ thấp phạm vi bảo vệ.

Bản thân `X-Signature` là **kết quả** để xác minh, thường không được ký bởi chính HMAC đó. Hai loại không được nhầm lẫn.

## 6. Host, authority và audience: một trường hợp cần phân tích riêng

`Host` của HTTP/1.1 và `:authority` trong HTTP/2 có thể được thay đổi hoặc ánh xạ tại proxy/gateway. Một số API có nhiều hostname cùng trỏ về một backend:

~~~text
api.partner.example.test -> Gateway -> orders-api
orders.internal.test     -> Backend -> orders-api
~~~

Nếu client ký raw `Host: api.partner.example.test` nhưng backend nhận `Host: orders.internal.test`, HMAC sẽ sai trừ khi contract xác định cách canonical authority hoặc điểm xác minh phù hợp.

Để tránh phụ thuộc vào hostname có thể rewrite, một hợp đồng có thể ký **audience ổn định**, ví dụ:

~~~text
audience:orders-api
~~~

Nhưng **không được chỉ ký chuỗi `orders-api` rồi mặc nhiên bỏ qua routing**. Verifier phải kiểm tra:

1. Credential/key record được phép sử dụng với audience `orders-api`.
2. Gateway/router đã chọn đúng service mà verifier coi là `orders-api`.
3. Request không thể bị chuyển đến service/tenant khác chỉ nhờ sửa `Host` hoặc `:authority` không được ký.
4. Nếu ứng dụng dùng hostname để chọn tenant, hostname phải được ràng buộc đáng tin qua signed canonical authority, trusted routing context hoặc policy server-side.

**Kết luận:** Có thể không ký raw `Host` trong một contract có audience ổn định, nhưng không được để nó trở thành kênh đổi đối tượng xử lý ngoài phạm vi đã xác minh.

## 7. Framing/transport header không được ký vẫn phải được kiểm tra

Một lỗi rất nguy hiểm là nghĩ: “`Content-Length` và `Transfer-Encoding` không nằm trong HMAC, nên verifier không cần quan tâm chúng”.

Điều này sai vì các header framing quyết định **HTTP parser thấy body bắt đầu và kết thúc ở đâu**. Nếu front proxy và backend phân tích độ dài request khác nhau, có thể dẫn đến **HTTP request smuggling** hoặc desynchronization, ngay cả khi HMAC được triển khai đúng cho các request bình thường.

Ví dụ rủi ro ở HTTP/1.1:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Length: 5
Transfer-Encoding: chunked
X-Signature: <illustrative-tag>
~~~

Đây là một **ví dụ cấu trúc không nhất quán**, không phải request hợp lệ để dùng. Những tổ hợp framing mơ hồ phải bị chặn/chuẩn hóa theo quy tắc HTTP tại điểm nhận, không chuyển thẳng qua các parser có behavior khác nhau.

### 7.1. Ranh giới byte của body digest

Nếu protocol ký:

~~~text
body-sha256 = SHA-256(applicationBodyBytes)
~~~

cần định nghĩa rõ `applicationBodyBytes` là gì. Với HTTP/1.1 chunked transfer coding, chunk-size lines và các byte framing **không phải cùng thứ với entity content bytes** mà ứng dụng xử lý. Với HTTP/2, body truyền qua DATA frames chứ không dùng cùng framing của HTTP/1.1.

Một lựa chọn thông thường là ký **bytes của body nội dung mà verifier và handler cùng nhìn thấy sau khi HTTP framing được xử lý đúng**, trước các phép parse/transform không thuộc hợp đồng. Nếu `Content-Encoding` cho phép nén, phải xác định digest được tính **trước hay sau giải nén** và ai được phép biến đổi.

Chỉ khi mọi bên thống nhất những byte đó, HMAC body digest mới ràng buộc chính xác request payload.

### 7.2. Header trailer

Nếu backend dùng giá trị trailer để kiểm tra checksum, trạng thái hay quyền, không thể mặc nhiên coi chúng vô hại chỉ vì không nằm trong tập header ban đầu. Protocol phải **cấm trailer ảnh hưởng semantics** hoặc định nghĩa rõ cách ràng buộc các trailer được phép vào chữ ký. Gateway/HTTP version có thể thay đổi cách truyền trailer, nên cần test ở từng hop.

## 8. Canonicalization và header không được ký

### 8.1. Tập signed headers cố định

Một thiết kế dễ kiểm chứng là **HMAC-REQUEST-V1** có signed headers bắt buộc:

~~~text
content-type
x-key-id
x-timestamp
x-nonce
~~~

Bên cạnh đó ký các thành phần ngoài header:

~~~text
method
canonical-path
canonical-query
audience
body-sha256
~~~

Các header như `User-Agent`, `X-Request-Id`, `traceparent`, `Accept-Encoding` và `Connection` **không được chèn vào canonical request V1**.

Một canonical request minh họa:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders

audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-lowercase-hex-characters>
~~~

Quy ước cụ thể:

- Đầu vào dùng **UTF-8**; các dòng nối bằng LF, **không có LF cuối**.
- Dòng query ở ví dụ rỗng, nhưng vẫn có một dòng trống giữ đúng cấu trúc.
- Tên signed header được chuyển thành **chữ thường ASCII**.
- Protocol cố định **thứ tự dòng**; server không dựa vào thứ tự header trên wire.
- `Content-Type` phải là `application/json` trong ví dụ này; các header token khác phải theo format đã định nghĩa.
- `<64-lowercase-hex-characters>` là placeholder cho SHA-256 thật của raw body bytes.
- `X-Signature` mang HMAC tag nhưng **không nằm trong canonical bytes**.
- `audience:orders-api` do contract/key registry tin cậy xác định; server đối chiếu nó với service đang nhận.

Đây là một **hợp đồng minh họa**, không phải định dạng chuẩn áp dụng cho mọi API HMAC.

### 8.2. Vì sao không ký “tất cả header HTTP”?

Header có thể được HTTP stack/proxy thêm, bỏ hoặc đổi theo từng kết nối. Nếu ký tất cả:

- `Content-Length` có thể thay khi request được buffer hoặc đổi protocol version.
- `Connection` không phải metadata end-to-end ổn định.
- `User-Agent` có thể thay khi một HTTP library được nâng cấp.
- Tracing IDs có thể do gateway sinh ra sau thời điểm client ký.
- Request có thể qua nhiều hop TLS termination, HTTP/1.1 và HTTP/2.

Ký tất cả header tạo **tính mong manh** mà không chắc tăng bảo mật. Cách đúng là **ký tập nhỏ nhưng đủ bảo vệ ý nghĩa request**, đồng thời xác định chính sách nghiêm ngặt cho những header còn lại.

### 8.3. Tên header không phân biệt hoa/thường

Hai tên:

~~~http
Content-Type: application/json
content-type: application/json
~~~

có cùng tên trường theo semantics HTTP. Khi canonicalize, nên đưa về `content-type`. Tuy nhiên, nếu **cả hai cùng xuất hiện trong một request**, chúng tạo **header trùng** và có thể khiến proxy/framework gộp hoặc chọn giá trị khác nhau.

Với signed header dạng đơn trị như `X-Key-Id`, `X-Timestamp`, `X-Nonce` và `Content-Type` trong ví dụ, **từ chối mọi trường hợp lặp hoặc nhập nhằng**. HTTP adapter phải giữ được thông tin về giá trị lặp trước khi canonicalizer quyết định.

### 8.4. Khoảng trắng quanh giá trị

~~~http
X-Key-Id: partner-a-k3
X-Key-Id:  partner-a-k3
X-Key-Id: partner-a-k3  
~~~

Một số thư viện bỏ optional whitespace (OWS), một số giữ nó trong chuỗi đọc. Protocol có thể quy định **trim OWS SP/HTAB một cách xác định trước khi ký**, hoặc yêu cầu giá trị canonical chặt chẽ như ví dụ Java dưới đây. Dù chọn cách nào, client, gateway và verifier phải thực hiện cùng quy tắc.

Không được cắt khoảng trắng **bên trong** giá trị một cách tùy tiện nếu nó có ý nghĩa, chẳng hạn trong quoted strings. Reject CR/LF và obsolete line folding để tránh request/header injection.

## 9. Quy tắc đối với unsigned headers

Một hợp đồng có tập signed headers cố định vẫn cần quyết định cách xử lý **header khác**. Không nên mặc định “không ký tức cho phép mọi giá trị”.

Có ba nhóm chính:

| Nhóm | Ví dụ | Chính sách phù hợp |
| --- | --- | --- |
| **Unsigned nhưng được phép dùng cho mục đích không bảo mật** | `User-Agent`, tracing/correlation IDs | Cho phép có giới hạn, parse an toàn, không dùng cho quyền/idempotency |
| **Unsigned nhưng thuộc lớp vận chuyển/proxy** | `Connection`, framing headers, `Via` | Do HTTP parser/proxy xử lý chặt theo protocol, không đưa thành input đáng tin cho business |
| **Có thể thay đổi semantics/bảo mật** | Method override, tenant, role, idempotency, content encoding | **Bắt buộc ký**, hoặc **từ chối**, hoặc **suy ra tại nguồn tin cậy** |

Đặc biệt, một header không được ký có thể **được attacker thêm vào**, không chỉ sửa giá trị đã có. Để bảo vệ business handlers, hệ thống nên có một chính sách “**deny-or-ignore unsupported semantic headers**” tại gateway/HTTP filter.

### 9.1. Không dùng unsigned header làm nguồn xác thực người dùng

Ví dụ nguy hiểm:

~~~http
POST /v1/orders HTTP/1.1
X-Authenticated-User: administrator
X-Signature: <valid-tag-for-other-fields>
~~~

Nếu backend tin `X-Authenticated-User` do client tự gửi, attacker có thể tự đặt giá trị khác trong khi HMAC vẫn đúng. Ngay cả khi `X-Authenticated-User` **được ký bởi client**, điều đó chỉ chứng minh client có secret đã ký lời khai ấy, chứ không chứng minh họ thật sự là administrator.

Danh tính phải đến từ **credential/key record đã xác thực hoặc assertion của gateway được tin cậy**. Nếu gateway dùng header để truyền principal tới backend, nó phải xóa mọi giá trị từ Internet, bảo vệ chặng nội bộ và cho backend biết nguồn đáng tin.

### 9.2. Không dùng unsigned header để điều khiển rate limit đáng tin cậy

Nếu rate limiter dùng `X-Forwarded-For` từ client chưa được kiểm chứng làm “IP thật”, attacker có thể thay IP để lách giới hạn. Gateway cần xác định địa chỉ nguồn dựa trên **chuỗi proxy được tin cậy**, làm sạch `Forwarded/X-Forwarded-*` do caller tự khai, rồi truyền metadata nguồn cho service qua kênh bảo vệ.

Ở cấp HMAC, principal được xác thực từ secret có thể là một khóa rate limit tốt hơn địa chỉ IP tự khai.

## 10. Java 17: canonicalize đúng signed headers, loại unsigned headers

Mã minh họa sử dụng Java 17 và JCA. Hợp đồng:

- Chỉ endpoint `POST /v1/orders` có body JSON.
- Signed headers: `Content-Type`, `X-Key-Id`, `X-Timestamp`, `X-Nonce`.
- `Content-Type` phải đúng chuỗi canonical `application/json`.
- `keyId`, timestamp và nonce có format ASCII cố định.
- Không dùng `User-Agent`, `X-Request-Id`, `traceparent`, `Connection` hoặc `Content-Length` trong canonical bytes.
- `Host` không được ký trực tiếp **chỉ vì contract ký audience ổn định và server bắt buộc kiểm tra routing/audience riêng**.
- Signature dùng HMAC-SHA256, Base64URL không padding của 32 byte (43 ký tự).

**Ranh giới tin cậy của ví dụ:** Interface `HeaderValues` phải trả lại **mọi giá trị** của một header, kể cả header cùng tên khác chữ hoa/thường. Không dùng adapter đã gộp/làm mất thông tin header trùng trước khi xác minh.

### 10.1. Đọc các signed headers bắt buộc

~~~java
import java.util.List;
import java.util.regex.Pattern;

public final class SignedHeaderV1 {
    public interface HeaderValues {
        // lowerCaseName luôn là ASCII lowercase.
        // Adapter phải trả về TOÀN BỘ giá trị (kể cả duplicate).
        List<String> values(String lowerCaseName);
    }

    public record Fields(
            String contentType, String keyId,
            String timestamp, String nonce) {}

    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,80}");
    private static final Pattern TIMESTAMP =
            Pattern.compile("(0|[1-9][0-9]{0,18})");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private SignedHeaderV1() {}

    private static String exactlyOne(
            HeaderValues headers, String lowerCaseName) {
        List<String> values = headers.values(lowerCaseName);
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException("Invalid signed header");
        }

        String value = values.get(0);
        if (value == null || value.isEmpty()
                || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Invalid signed header");
        }
        return value;
    }

    public static Fields read(HeaderValues headers) {
        String contentType = exactlyOne(headers, "content-type");
        String keyId = exactlyOne(headers, "x-key-id");
        String timestamp = exactlyOne(headers, "x-timestamp");
        String nonce = exactlyOne(headers, "x-nonce");

        // Contract ví dụ: không trim/không chuyển case các VALUE.
        // HTTP adapter cần chuyển về một dạng ổn định hoặc từ chối
        // input mà các thành phần khác có thể parse khác.
        if (!"application/json".equals(contentType)
                || !KEY_ID.matcher(keyId).matches()
                || !TIMESTAMP.matcher(timestamp).matches()
                || !NONCE.matcher(nonce).matches()) {
            throw new IllegalArgumentException("Invalid signed header");
        }

        return new Fields(contentType, keyId, timestamp, nonce);
    }
}
~~~

**Lưu ý:** `SignedHeaderV1.read` kiểm tra cú pháp/độ lặp, **không xác thực key ID**. Server còn phải tra exact key record, kiểm tra status/audience/algorithm/notBefore/acceptUntil rồi lấy secret. Header value do caller gửi vẫn chưa đáng tin trước khi MAC khớp.

Trong production, bộ chuyển đổi HTTP adapter cần giữ **giá trị thực sau parsing được thống nhất với wire format**, từ chối obs-fold, header trùng và các dạng gộp nhiều giá trị mơ hồ. Với signed headers dạng token như trên, dấu phẩy/khoảng trắng ngoài cú pháp sẽ bị regex từ chối.

### 10.2. Tạo canonical request và xác minh HMAC

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacHeaderVerifierV1 {
    private HmacHeaderVerifierV1() {}

    public static byte[] canonicalBytes(
            String method,
            String canonicalPath,
            String canonicalQuery,
            SignedHeaderV1.Fields fields,
            byte[] rawBody) throws GeneralSecurityException {

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        String bodyHash = HexFormat.of().formatHex(digest);

        // method/path/query được canonicalize và validate ở lớp riêng.
        // Chúng không được chứa CR/LF hoặc dấu phân cách mơ hồ.
        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + fields.contentType(),
                "x-key-id:" + fields.keyId(),
                "x-timestamp:" + fields.timestamp(),
                "x-nonce:" + fields.nonce(),
                "body-sha256:" + bodyHash);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static String sign(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(canonicalBytes));
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes,
            String signature) throws GeneralSecurityException {

        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(signature)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(canonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Ở `canonicalBytes`, **không hề có các tham số `User-Agent` hoặc `X-Request-Id`**; chúng không ảnh hưởng tag HMAC. Đó là hành vi **có chủ đích**. Nếu backend bắt đầu dùng `X-Request-Id` làm idempotency key, cần thay contract và ký header đó hoặc dùng một trường khác đã được ký.

### 10.3. Thử thay đổi unsigned header

Giả sử đã có hai request chỉ khác:

~~~http
User-Agent: DemoClient/1.0
~~~

và:

~~~http
User-Agent: DemoClient/2.0
~~~

Nếu các signed fields và raw body giữ nguyên, `canonicalBytes(...)` và `sign(...)` trong ví dụ cho **cùng tag**. Điều này chứng minh `User-Agent` không được HMAC bảo vệ, chứ không chứng minh `User-Agent` có nguồn gốc đáng tin.

Để tránh nhầm với chống replay, hãy kiểm thử tampering ở **cấp primitive/canonical bytes** hoặc dùng một signed request mới, chưa bị ghi nonce. Khi chạy toàn bộ middleware, request thứ hai với **cùng nonce** phải bị từ chối dù HMAC vẫn đúng.

### 10.4. Kiểm tra freshness, key rotation và phân quyền nằm ngoài helper

Code trên chưa hoàn chỉnh để nhận request production. Luồng đầy đủ cần:

1. Nhận request trong giới hạn kích thước/header count và kiểm tra framing.
2. Parse signed header duy nhất, validate các giá trị.
3. Tra `keyId` theo exact match, kiểm tra key record/algorithm/audience/trạng thái.
4. Lấy secret tin cậy, canonicalize method/path/query/signed headers/raw body.
5. Verify HMAC bằng tag đúng format và so sánh byte an toàn.
6. Kiểm tra timestamp ở cửa sổ chấp nhận.
7. Ghi nonce **nguyên tử** vào shared replay store; từ chối nonce trùng.
8. Tạo principal từ key record và authorize theo action/resource/tenant.
9. Áp dụng idempotency/rate limits/validation nghiệp vụ trước khi handler thực thi.

Có thể kiểm tra freshness format và window **trước khi tính HMAC** để tiết kiệm chi phí, nhưng không ghi nonce vào store dựa trên dữ liệu chưa được xác thực.

## 11. Nếu protocol truyền danh sách `SignedHeaders` thì sao?

Một số giao thức không cố định danh sách header; client gửi metadata liệt kê những header đã ký. Ví dụ:

~~~http
X-Signed-Headers: content-type;x-key-id;x-timestamp;x-nonce
~~~

Đây là một thiết kế khả thi nhưng có thêm những yêu cầu bảo mật:

- Chuẩn hóa tên header sang lowercase ASCII, tách và sắp xếp theo quy tắc có version.
- Không chấp nhận tên trùng, tên rỗng, header không tồn tại hoặc header không thể canonicalize.
- Danh sách `SignedHeaders` phải được **ràng buộc vào nội dung ký**.
- Server có **mandatory signed components** không thể bị client xóa: method, URI, freshness, key ID, body digest và các header liên quan semantics.
- Không tự cho phép header tùy ý bị loại khỏi chữ ký chỉ vì caller bỏ nó trong danh sách.
- Mọi header mới mà handler bắt đầu dùng cho quyền hoặc nghiệp vụ phải đi kèm **đánh giá lại contract**.

### 11.1. Tấn công hạ thấp phạm vi ký

Client gửi:

~~~http
X-Signed-Headers: x-key-id;x-timestamp
X-Tenant-Id: tenant-B
Content-Type: application/json
X-Signature: <hmac-over-only-two-headers>
~~~

Nếu server xác minh theo đúng danh sách do caller tự khai mà không yêu cầu ký body, method, path hay tenant header, nó có thể chấp nhận một request bị sửa đáng kể. Đó là lỗi **thiết kế tập ký**, không phải lỗi HMAC-SHA256.

**Cách khắc phục:** Định nghĩa tập tối thiểu từ phía server. Client có thể chọn ký **thêm** header, nhưng không thể bỏ các thành phần bắt buộc. Với API đơn giản, danh sách cố định theo version thường dễ triển khai hơn.

## 12. Proxy/gateway và sự thay đổi unsigned headers

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant G as API Gateway / Proxy
    participant V as HMAC Verifier
    participant A as Authorized Handler

    C->>G: HTTPS + signed fields + unsigned headers
    Note over G: TLS termination / framing / tracing headers
    G->>V: Forward request, có thể thay một số unsigned headers
    V->>V: Parse signed fields và key record
    V->>V: Canonicalize HMAC, verify tag, timestamp/nonce
    V->>A: Trusted principal + validated request
    A->>A: Authorization rồi nghiệp vụ
~~~

Tại gateway, nên phân biệt:

**Nhóm được thay đổi hợp lệ:** tracing/correlation fields, `Connection`, message framing phù hợp HTTP protocol, thông tin proxy phù hợp chính sách. Những thay đổi này không làm sai HMAC nếu chúng ngoài signed set và không thay đổi signed semantics/body bytes.

**Nhóm không được thay đổi tùy tiện:** `Content-Type` (nếu ký), `X-Key-Id`, `X-Timestamp`, `X-Nonce`, method, path, query và raw body đã ký. Việc thay đổi cần bị từ chối hoặc dùng một giao thức ký lại có ranh giới tin cậy khác, không lặng lẽ bỏ xác minh.

**Nhóm phải được thiết lập lại tin cậy:** `X-Authenticated-Principal`, `X-Forwarded-*` hoặc original URI headers nếu backend cần chúng. Gateway cần xóa dữ liệu client tự gửi, tạo dữ liệu tin cậy và bảo vệ nó tới backend.

### 12.1. Verifier ở gateway

Nếu gateway xác minh HMAC từ Internet:

- Kiểm tra mọi signed field **trước khi rewrite** không được contract cho phép.
- Tạo principal và context đáng tin sau xác thực.
- Chỉ cho backend tin principal từ gateway qua authenticated internal channel.
- Đảm bảo routing/handler cuối cùng tương ứng với method, URI và audience đã ký.
- Không đưa các unsigned headers từ client vào quyết định quyền của backend.

### 12.2. Verifier ở backend

Nếu backend xác minh:

- Gateway phải giữ nguyên semantics và canonical representation của signed fields.
- Nếu gateway thay header ngoài tập ký, backend không được coi header đó là thông tin xác thực của client.
- Nếu proxy thêm metadata bắt buộc cho routing, phải có một **trust mechanism riêng** giữa gateway và backend, không sử dụng trực tiếp unsigned header tự khai.
- HTTP/2 ↔ HTTP/1.1 có thể thay framing/`Host`; cần kiểm thử qua các protocol version thực tế.
- Không dùng signature fallback để “thử ký cả header trước và sau proxy” mà không có contract version và policy rõ ràng.

## 13. Rủi ro đặc biệt: header không được ký nhưng ảnh hưởng authorization

Ví dụ một client sở hữu secret của tenant A:

~~~http
POST /v1/orders HTTP/1.1
X-Key-Id: partner-a-k3
X-Tenant-Id: tenant-B
X-Signature: <valid-hmac-for-other-fields>

{"orderId":"order-42"}
~~~

Nếu `X-Tenant-Id` không được ký, nó có thể bị sửa mà HMAC vẫn đúng. Nhưng ngay cả nếu nó **được ký bởi client A**, server vẫn không được mặc nhiên cho phép A thao tác trên B.

**Authentication** chứng minh request được ký bằng credential nào, còn **authorization** quyết định principal của credential đó có quyền trên tenant/resource/action cụ thể không.

Một thiết kế tốt là:

- `keyId` trỏ đến `principalId` và tenant/scope do server quản lý.
- Nếu tenant là tham số nghiệp vụ, có thể nằm trong signed URI/body/header để bảo vệ tính toàn vẹn của **yêu cầu**.
- Server vẫn so sánh tenant được yêu cầu với những tenant principal được phép truy cập.
- Không cho caller quyết định principal bằng header như `X-Authenticated-User`, dù header đó có được ký theo một cách nào.

Một nguyên tắc tương tự áp dụng cho các header `X-Scope`, `X-Role`, `X-Is-Admin` và `X-Internal-Request`: **client tự khai giá trị không thể tạo quyền.**

## 14. Replay, key rotation và unsigned headers

### 14.1. Replay vẫn cần timestamp và nonce đã ký

HMAC hợp lệ không chứng minh request chưa từng được gửi. Với signed metadata:

~~~text
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
~~~

Server kiểm tra timestamp trong cửa sổ cho phép và ghi nonce vào shared replay store với thao tác **atomic put-if-absent**, chỉ **sau khi HMAC đúng**. TTL của nonce phải bao phủ **toàn bộ thời gian request có thể còn được chấp nhận**.

Một unsigned `X-Request-Id` **không được dùng thay nonce chống replay**. Kẻ tấn công có thể đổi request ID mà giữ nguyên HMAC, hoặc retry bằng request mới. Với thanh toán, idempotency nghiệp vụ vẫn cần dù nonce đã được kiểm soát.

### 14.2. Key rotation và tập signed headers

Trong rotation:

~~~text
keyId: partner-a-k2 -> secret v2, RETIRING
keyId: partner-a-k3 -> secret v3, ACTIVE
~~~

Server tra exact `keyId` để lấy secret, algorithm, audience và status. **Tập signed headers không được vô tình thay đổi** chỉ vì đổi secret. Nếu muốn thêm `Idempotency-Key` hoặc `Content-Encoding` vào các signed fields, nên:

1. Ban hành phiên bản contract ký rõ ràng.
2. Cấp hoặc gắn protocol version với credential/key record.
3. Có test vectors client/server.
4. Thiết lập giai đoạn chuyển tiếp hữu hạn và giới hạn algorithm/header policy được phép.
5. Thu hồi contract/credential cũ theo kế hoạch; không “thử tất cả danh sách header” đến khi HMAC khớp.

Nếu secret bị lộ, attacker có thể tạo HMAC hợp lệ cho request mới. Tăng số header ký không sửa được sự cố lộ khóa; cần **thu hồi, cấp lại và xử lý sự cố credential**.

## 15. Ma trận kiểm thử signed và unsigned headers

Ma trận nên được chạy từ **unit test canonicalizer** tới **HTTP integration test qua gateway**.

| Test | Thay đổi hoặc cấu hình | Kỳ vọng |
| --- | --- | --- |
| HMAC cơ bản | Signed headers, method, path, body đúng | MAC khớp, tiếp tục freshness/authorization |
| Đổi `User-Agent` | Thay 1.0 thành 2.0, các signed fields không đổi | **Tag không đổi**; không dùng User-Agent làm identity |
| Đổi `X-Request-Id` | Thay correlation ID | **Tag không đổi** nếu chỉ dùng cho tracing |
| Đổi `traceparent` | Thay trace context | **Tag không đổi** nếu không ảnh hưởng security/business |
| Thêm unsigned telemetry header | Thêm `X-Debug-Trace` được phép | Không thay HMAC, vẫn giới hạn kích thước/giá trị |
| Đổi `Content-Type` | JSON thành loại khác | HMAC sai hoặc contract từ chối |
| Đổi `X-Key-Id` | Dùng ID credential khác | Từ chối |
| Đổi `X-Timestamp` | Đổi thời gian đã ký | HMAC sai |
| Đổi `X-Nonce` | Đổi nonce đã ký | HMAC sai |
| Sửa body | Đổi byte JSON | HMAC sai do body digest |
| Sửa method/path/query | Đổi thành phần đã ký | HMAC sai |
| Thêm `X-Tenant-Id` unsigned | Caller tự chọn tenant khác | Header bị bỏ qua/từ chối làm identity; authorization dựa server |
| Thêm `X-Authenticated-User` | Caller khai admin | Không được nâng quyền; gateway loại bỏ hoặc backend từ chối |
| Thêm method override | `X-HTTP-Method-Override: DELETE` | Từ chối nếu contract không hỗ trợ |
| Thêm `Idempotency-Key` unsigned | Dùng làm business idempotency | Test phải phát hiện thiết kế sai; bổ sung ký trước khi sử dụng |
| Header `X-Key-Id` lặp | Hai giá trị cùng tên | Từ chối |
| Tên header khác case, bị lặp | `X-Key-Id` và `x-key-id` | Từ chối thay vì chọn một |
| Signed header trống | `X-Timestamp:` | Từ chối |
| Khoảng trắng ngoài contract | Giá trị ký có OWS khác client | Từ chối hoặc canonicalize đúng quy tắc thống nhất |
| CR/LF/obs-fold | Header line folding hoặc injection | Từ chối input mơ hồ |
| Tag sai độ dài/encoding | Chữ ký cắt ngắn, padding không được phép | Từ chối |
| Framing mơ hồ | `Content-Length` và `Transfer-Encoding` xung đột | HTTP parser/gateway từ chối trước nghiệp vụ |
| HTTP/2 ↔ HTTP/1.1 | Proxy tái tạo framing và authority | Chỉ thay phần được phép; canonical HMAC và routing khớp |
| Gateway sửa `Host` | Backend host khác host ngoài | Đúng audience/routing policy hoặc từ chối |
| Caller giả `X-Forwarded-For` | Đặt IP tùy ý | Không chi phối trusted source IP/rate limit |
| Key bị thu hồi | Tag tính đúng bằng secret revoked | Từ chối |
| Timestamp hết hạn | Tag vẫn đúng nhưng request cũ | Từ chối freshness |
| Replay nguyên request | Gửi lại cùng nonce | Lần sau bị từ chối tại nonce store |
| Replay đồng thời | Hai instance cùng nonce | Tối đa một request vượt replay gate |
| Đúng MAC, sai tenant | Principal A yêu cầu tài nguyên B | Authorization từ chối |

**Chú ý khi test tampering:** Một request được gửi lần hai với cùng timestamp/nonce có thể bị replay gate từ chối **dù tag HMAC vẫn giống nhau**. Muốn chứng minh một unsigned header không ảnh hưởng tag, cần so sánh **canonical bytes/MAC ở cấp primitive**; muốn kiểm thử end-to-end, phải phân biệt rõ “HMAC hợp lệ” với “request được chấp nhận sau replay check”.

### 15.1. Golden test cho canonical bytes

Với cùng request mẫu, lưu test fixture gồm:

- Method, canonical path/query.
- Những header được ký và thứ tự canonical.
- Danh sách unsigned headers được phép.
- SHA-256 của raw body bytes.
- Toàn bộ canonical bytes UTF-8.
- HMAC tag Base64URL dùng secret test.
- Test vector sau khi đổi từng signed/unsigned header.

Golden tests nên chạy cả ở client và verifier, giúp phát hiện bất đồng khi HTTP library hoặc gateway được nâng cấp.

## 16. Tình huống thực tế: ký webhook qua API gateway

Một đối tác ký webhook cập nhật trạng thái thanh toán. Gateway nhận HTTPS, thêm `X-Request-Id` và `traceparent` rồi chuyển tiếp đến backend. Backend dựa vào `X-Key-Id` để xác thực partner và dùng JSON body để cập nhật giao dịch.

### 16.1. Yêu cầu

- Gateway được phép thay telemetry headers.
- Backend phải phát hiện sửa method, path, query, JSON body hoặc metadata xác thực.
- `X-Tenant-Id` do Internet tự khai không được coi là principal/tenant đáng tin.
- `Content-Type` phải là JSON đúng contract.
- Mỗi signed request chỉ được chấp nhận một lần trong cửa sổ timestamp.
- Không có route/handler hoặc policy nào phụ thuộc vào header chưa được ràng buộc tin cậy.

### 16.2. Thiết kế

1. Contract cố định `HMAC-REQUEST-V1` với signed method, URI, audience, `Content-Type`, `X-Key-Id`, `X-Timestamp`, `X-Nonce` và raw body digest.
2. `X-Signature` chỉ mang tag Base64URL, không tự được ký.
3. `User-Agent`, `X-Request-Id` và tracing headers được phép thay đổi nhưng chỉ dùng cho observability; không dùng làm idempotency key hoặc principal.
4. Gateway validate framing/header mơ hồ, loại bỏ các header principal do Internet gửi và chuyển tiếp signed fields theo contract.
5. Backend xác minh HMAC bằng secret từ key registry, kiểm tra timestamp và nonce atomically.
6. Backend lấy principal/tenant được phép từ key record, giải quyết idempotency và authorization trên giao dịch.
7. Tổ chức test qua gateway để chứng minh telemetry thay đổi không phá chữ ký, còn sửa `Content-Type` hoặc body thì bị từ chối.

### 16.3. Phân tích sự cố giả định

**Sự cố A:** HMAC thất bại sau khi gateway đổi `User-Agent`.  
**Đánh giá:** Nếu contract thực sự không ký `User-Agent`, việc đổi header này **không phải nguyên nhân trực tiếp**. Cần so sánh canonical bytes, body digest, path/query và signed headers trước/sau gateway.

**Sự cố B:** Một yêu cầu có HMAC hợp lệ nhưng được thực thi ở tenant khác.  
**Đánh giá:** Có thể một header như `X-Tenant-Id`/`X-Forwarded-Host` chưa được bảo vệ vẫn tác động tới routing/authorization. Cần xem lại trust boundary và nguồn xác định tenant, không chỉ thay thuật toán HMAC.

**Sự cố C:** Proxy thay `Content-Length`, nhưng HMAC vẫn hợp lệ.  
**Đánh giá:** Điều này có thể bình thường nếu body bytes cuối cùng được verifier và handler nhìn thấy không đổi. Tuy nhiên vẫn cần bảo đảm HTTP framing đúng và không có request smuggling.

**Sự cố D:** Retry webhook cùng signature, thay `X-Request-Id` mới.  
**Đánh giá:** HMAC vẫn có thể đúng vì correlation ID không ký. Nhưng nonce HMAC đã dùng phải bị từ chối; idempotency của webhook event còn bảo vệ khỏi gửi lại bằng signed request mới.

## 17. Bài tập thực hành

### Bài tập 1 — Phân loại signed/unsigned headers

Với endpoint `POST /v1/payments`, hãy phân loại `Content-Type`, `Content-Length`, `X-Key-Id`, `X-Nonce`, `User-Agent`, `Idempotency-Key`, `X-Tenant-Id` và `X-HTTP-Method-Override`. Với mỗi header, trả lời: **nó có ảnh hưởng semantics không, ai sở hữu nó, có cần ký không, và nếu không ký thì cần kiểm soát gì khác?**

### Bài tập 2 — Tampering test

Tạo một request đã ký có `X-Request-Id` và `User-Agent` không được ký. Tính tag gốc; sửa hai header này rồi tính lại canonical bytes và HMAC. So sánh với kết quả sửa `Content-Type` hoặc `X-Nonce`.

### Bài tập 3 — Phát hiện header trùng

Thiết lập một HTTP adapter trả về cả hai giá trị cho `X-Key-Id` nếu request chứa:

~~~http
X-Key-Id: partner-a-k3
x-key-id: partner-b-k1
~~~

Chứng minh `SignedHeaderV1.read(...)` từ chối thay vì chọn giá trị đầu/cuối. Thử thêm whitespace, CR/LF và giá trị rỗng.

### Bài tập 4 — Gateway/HTTP protocol

Cho request qua gateway HTTP/2 → HTTP/1.1; so sánh `Host`, `:authority`, `Content-Length`, framing và raw body bytes. Chứng minh audience/key record cùng chọn đúng service và các signed fields không bị đổi ngoài contract.

### Bài tập 5 — Đánh giá idempotency và phân quyền

Backend đang dùng unsigned `X-Request-Id` để chặn tạo hai giao dịch. Hãy thiết kế lại để dùng `Idempotency-Key` đã ký hoặc event ID nằm trong body đã ký, có server-side idempotency store. Sau đó giải thích vì sao ký `X-Tenant-Id` vẫn không cấp quyền truy cập tenant B cho client A.

## 18. Checklist triển khai

- [ ] Contract HMAC có version, khai báo tập header **bắt buộc được ký** và các thành phần method/URI/body digest.
- [ ] Mỗi header được chọn vì ảnh hưởng request semantics, không vì tiện triển khai.
- [ ] Những header không được ký có mục đích cụ thể; không dùng dữ liệu tự khai đó làm principal, quyền hoặc idempotency.
- [ ] `X-Signature` được xử lý như tag để verify, không đưa vào chính canonical text tạo nó.
- [ ] `X-Key-Id`, timestamp, nonce và protocol metadata ảnh hưởng xác thực phải được ràng buộc và kiểm tra.
- [ ] Signed header names lowercase ASCII; thứ tự và giá trị canonical có quy tắc rõ, gồm OWS và giá trị rỗng.
- [ ] Reject duplicate/ambiguous headers, CR/LF, obs-fold và các định dạng không có trong contract.
- [ ] `Content-Type`/`Content-Encoding` được ký hoặc cố định/từ chối nếu ảnh hưởng parser.
- [ ] Không cho method-override, tenant/role/client principal headers tự khai vượt qua trust boundary.
- [ ] Message framing (`Content-Length`, `Transfer-Encoding`, HTTP/2 frames) được parser/gateway xử lý nghiêm ngặt; body digest đúng byte ứng dụng xử lý.
- [ ] `Host`/`:authority`, routing và audience được ràng buộc theo một chính sách đáng tin.
- [ ] Gateway xóa header định danh/forwarded không tin cậy; bảo vệ kết nối và context tới backend.
- [ ] Signed timestamp/nonce đi cùng replay store atomically, TTL đủ dài, policy an toàn khi store lỗi.
- [ ] Key ID tra đúng secret/algorithm/audience; rotation, revocation và cache invalidation có quy trình.
- [ ] Authorization kiểm tra principal/action/resource/tenant, không suy quyền từ request headers.
- [ ] Golden tests cho signed header canonicalization và tampering tests xác minh unsigned headers không làm thay MAC.
- [ ] End-to-end tests qua HTTP/1.1, HTTP/2, reverse proxy, API gateway và framework thật.

## 19. Câu hỏi tự kiểm tra

1. **Header không được ký có nghĩa header đó đã được HMAC bảo vệ không?** Không. Chỉ các trường nằm trong canonical request mới được HMAC ràng buộc.
2. **Thay `User-Agent` có phải luôn làm signature sai không?** Không. Nếu `User-Agent` nằm ngoài signed set và các signed fields giữ nguyên, HMAC không đổi.
3. **Vì sao `X-Signature` thường không nằm trong nội dung được ký?** Vì nó là kết quả HMAC; đưa chính kết quả vào đầu vào tạo nó dẫn đến phụ thuộc vòng.
4. **Có nên để `X-Timestamp`/`X-Nonce` không ký không?** Không, nếu chúng dùng cho freshness/replay. Chúng phải được ràng buộc mật mã với request.
5. **Tại sao có thể không ký `Content-Length` nhưng vẫn phải kiểm tra framing?** Vì transport/framing có thể thay đổi qua proxy, còn parser differential có thể gây request smuggling.
6. **`X-Request-Id` không ký có phù hợp làm idempotency key không?** Không, nếu giá trị có thể bị sửa mà HMAC không đổi; cần trường đã được ràng buộc và store nghiệp vụ.
7. **Vì sao không được tự tin `X-Forwarded-For` từ Internet?** Nó do caller có thể khai giả; chỉ tin chuỗi proxy được cấu hình/đảm bảo.
8. **Có thể để `Host` không ký không?** Có trong contract có audience/routing tin cậy; nhưng không được để thay Host dẫn tới service/tenant khác ngoài phạm vi xác minh.
9. **Khi signer và verifier ký đúng nhưng handler đọc unsigned `X-Tenant-Id`, nguy cơ gì?** Handler có thể xử lý tenant khác với danh tính/quyền đã xác thực.
10. **Ký cả `X-Tenant-Id` có đủ để client A truy cập tenant B không?** Không. HMAC bảo vệ lời yêu cầu; authorization quyết định quyền trên B.
11. **Khi client sửa unsigned telemetry header và gửi lại nguyên request, vì sao vẫn bị từ chối?** Có thể HMAC đúng nhưng nonce trùng khiến replay gate từ chối.
12. **Vì sao fixed signed header list giúp an toàn hơn danh sách do client tự quyết?** Vì server không cho client bỏ những thành phần bắt buộc bảo vệ semantics/freshness.

**Kết luận:** **Header không được ký vẫn là dữ liệu không được HMAC bảo vệ**, dù nó xuất hiện cạnh các header đã ký trong cùng HTTP request. Chỉ nên để các header có tác dụng phụ trợ, được phép biến đổi, hoặc được thiết lập qua ranh giới tin cậy riêng nằm ngoài canonical signature. Header ảnh hưởng identity, action, resource, body interpretation, replay hay idempotency phải được bảo vệ, suy ra từ server hoặc bị từ chối. Thiết kế an toàn dựa vào **hợp đồng signed fields đủ mạnh, canonicalization nhất quán, gateway được kiểm soát, chống replay, quản lý khóa và phân quyền độc lập**.
