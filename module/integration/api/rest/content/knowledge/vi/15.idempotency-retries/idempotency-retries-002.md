# GET, PUT, DELETE và phạm vi bảo đảm theo ngữ nghĩa phương thức

Một ứng dụng gửi **PUT /v1/profiles/u-17** để cập nhật tên hiển thị. Server đã ghi dữ liệu thành công, nhưng kết nối mất trước khi client nhận response. Client thử lại cùng request. Nếu API được thiết kế đúng ngữ nghĩa PUT, việc thử lại không tạo thêm một lần cập nhật nghiệp vụ độc lập. Tuy nhiên, response lần thứ hai **có thể khác** response lần đầu; log có thể ghi thêm sự kiện; và nếu có cập nhật cạnh tranh từ người khác, kết quả vẫn cần được xem xét.

Với **GET**, retry thường dễ hơn vì thao tác được yêu cầu chỉ là đọc. Với **DELETE**, retry cũng có thể an toàn về *hiệu ứng dự kiến* dù lần đầu trả 204 và lần sau trả 404. Nhưng nếu DELETE vô tình tạo **yêu cầu hoàn tiền mới ở mỗi lần gọi**, hoặc PUT gửi thông báo thanh toán nhiều lần, mã phương thức HTTP không tự chữa được lỗi đó.

Bài học thuộc chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**. Người học sẽ phân biệt **safe**, **idempotent**, **cacheable** và **exactly-once**, hiểu phạm vi bảo đảm theo HTTP Semantics (RFC 9110), thực hành thiết kế REST API bằng Java/Spring và kiểm thử các tình huống timeout, retry, xung đột cập nhật và tác động ngoài hệ thống.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **idempotency** của phương thức HTTP dựa trên *hiệu ứng dự kiến* lên server, thay vì so sánh nguyên văn response hoặc số lần request đến server.
2. Phân biệt **GET safe + idempotent**, **PUT idempotent nhưng không safe**, và **DELETE idempotent nhưng không safe**; biết điều gì **không được bảo đảm**.
3. Thiết kế GET không làm thay đổi trạng thái nghiệp vụ, PUT đặt trạng thái của resource và DELETE loại bỏ liên kết resource với tác dụng khi retry có thể dự đoán.
4. Phân tích kết quả chưa xác định khi mạng hỏng, gateway trả 504 hoặc client timeout sau khi server đã commit.
5. Kết hợp **ETag**, **If-Match**, trạng thái **412/428**, versioning và điều kiện cập nhật nguyên tử để tránh mất cập nhật khi có nhiều client.
6. Kiểm soát side effect qua email, queue, ERP và cổng thanh toán bằng deduplication/outbox/idempotency key khi cần.
7. Xây dựng chiến lược retry có giới hạn, backoff, jitter, deadline, observability và kiểm thử end-to-end với Spring.

## 2. Ngữ nghĩa idempotent chính xác là gì?

Theo **RFC 9110, §9.2.2**, một request method được coi là **idempotent** khi **hiệu ứng dự kiến** của nhiều request **giống hệt nhau** với hiệu ứng dự kiến của một request. Các phương thức idempotent được HTTP chuẩn hóa bao gồm **PUT, DELETE** và mọi phương thức **safe** (như GET, HEAD, OPTIONS, TRACE).

Có ba cụm từ cần nhớ:

- **Cùng request:** so sánh nhiều lần thực hiện một request có cùng method, target resource và ý định dữ liệu/điều kiện. Thay payload, target URI hoặc precondition có thể làm thay đổi bài toán.
- **Hiệu ứng dự kiến:** trạng thái hoặc hành động mà client yêu cầu theo hợp đồng. Không phải toàn bộ byte log, số request nhận được, latency hoặc mọi tác vụ quan sát nội bộ phải giống nhau.
- **Trên server:** câu hỏi là thực thi lặp có tạo thêm hiệu ứng nghiệp vụ mong muốn hay không. HTTP không bảo đảm toàn bộ hệ thống phân tán xử lý đúng một lần.

Ví dụ công thức trực giác với thao tác đặt giá trị:

\[
f(f(S)) = f(S)
\]

Trong đó \(S\) là trạng thái resource và \(f\) là thao tác được yêu cầu. Nếu \(f\) là “đặt trạng thái profile thành tên *An*”, thực hiện lần hai với cùng dữ liệu không làm tên đổi thêm lần nữa. Nếu \(f\) là “tăng lượt sử dụng lên 1”, lặp hai lần lại tạo hiệu ứng khác một lần.

**Đây chỉ là mô hình hóa ý định trong một trạng thái kiểm soát**, không phải cam kết rằng toàn bộ trạng thái hệ thống, đồng hồ, log và response byte đều bất biến. RFC cho phép server ghi log từng request, lưu lịch sử revision hoặc thực hiện các tác dụng phụ nhất định ngay cả khi method được định nghĩa là idempotent.

### 2.1. Safe, idempotent và cacheable không đồng nghĩa

| Thuộc tính | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| **Safe** | Client có yêu cầu thay đổi trạng thái được quản lý ở origin không? | GET lấy sản phẩm; server có thể ghi access log |
| **Idempotent** | Lặp **cùng request** có cùng hiệu ứng dự kiến như gửi một lần không? | PUT thay thế profile, DELETE loại bỏ item |
| **Cacheable** | Một response có thể lưu và tái sử dụng theo HTTP caching không? | GET catalog có Cache-Control phù hợp |
| **Retryable trong hoàn cảnh cụ thể** | Client có thể gửi lại **bây giờ** mà không vượt rủi ro, deadline hoặc bất biến nghiệp vụ không? | GET có thể retry giới hạn; PUT có precondition cần đối soát |
| **Exactly-once** | Toàn bộ tác động có thật sự được thực hiện đúng một lần xuyên nhiều hệ thống không? | HTTP method tự nó **không** đưa ra bảo đảm này |

**Safe ⇒ idempotent** theo định nghĩa phương thức HTTP, nhưng **idempotent ⇏ safe**. GET safe/idempotent, còn PUT và DELETE idempotent nhưng có chủ đích thay đổi trạng thái.

### 2.2. Bảng ngữ nghĩa phương thức

| Phương thức | Safe | Idempotent | Request content | Điều cần chú ý |
|---|---|---|---|---|
| **GET** | Có | Có | Không có ngữ nghĩa chung được định nghĩa cho GET body | Truy vấn representation; không dùng để thay đổi nghiệp vụ |
| **HEAD** | Có | Có | Không có ngữ nghĩa chung | Tương tự GET nhưng không có response content |
| **PUT** | Không | Có | Representation yêu cầu tạo/thay thế trạng thái target resource | Giữ hiệu ứng dự kiến ổn định khi gửi lại cùng representation |
| **DELETE** | Không | Có | Không có ngữ nghĩa chung được định nghĩa cho DELETE body | Loại bỏ liên kết target resource; xóa mềm/vật lý tùy server |
| **POST** | Không | **Không mặc định** | Xử lý representation theo ngữ nghĩa của target resource | Cần hợp đồng idempotency riêng nếu muốn retry |
| **PATCH** | Không | **Không mặc định** | Tập thay đổi theo patch document đã chọn | Có thể thiết kế operation cụ thể idempotent, nhưng không được mặc định |

Không suy ra “method idempotent ⇒ response luôn giống nhau”, “method safe ⇒ sẽ không có bất kỳ log hoặc metric nào thay đổi”, hoặc “GET ⇒ response được mọi cache lưu”. Những phát biểu này lẫn lộn các lớp bảo đảm.

### 2.3. Tại sao HTTP định nghĩa idempotency?

Mạng có thể ngắt giữa chừng. Client có thể **gửi đủ request nhưng không nhận được response**, khiến nó không biết origin đã thực thi hay chưa. Với một phương thức idempotent, việc lặp **cùng ý định** được thiết kế để không nhân đôi hiệu ứng dự kiến, nhờ đó client có cơ sở cân nhắc **thử lại sau lỗi giao tiếp**.

Tuy nhiên, tự động retry không có nghĩa phải retry mọi lỗi. Client cần quyết định dựa trên deadline, số lần thử, mã HTTP, tình trạng backend, khả năng xung đột và các tác dụng ngoài hệ thống.

## 3. GET: phương thức safe, idempotent, nhưng không hứa dữ liệu giống nhau

**GET** yêu cầu chuyển biểu diễn hiện hành của target resource. Nó là **safe**: theo ngữ nghĩa HTTP, client không yêu cầu thay đổi trạng thái ứng dụng được quản lý ở origin.

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Response lần đầu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-v7"
Cache-Control: public, max-age=30

{"id":"p-42","price":1200000,"stock":12}
~~~

Một giây sau, người quản trị cập nhật giá hoặc khách khác mua hàng. GET lần tiếp theo có thể trả **price/stock/ETag khác**. Điều này **không vi phạm idempotency** của GET: hai lần GET không chủ động làm thay đổi dữ liệu nghiệp vụ vì được gửi.

### 3.1. Điều gì có thể thay đổi khi GET lặp lại?

- **Response body:** dữ liệu có thể đã bị người khác cập nhật.
- **HTTP status:** resource bị xóa giữa hai lần, GET thứ nhất 200 và lần sau 404.
- **Header:** ETag, Date, Cache-Control, Age, trace ID và các metadata có thể thay đổi.
- **Log/metrics:** origin và gateway có thể ghi thêm access log, latency, request count hoặc các tác động nội bộ phụ trợ.

Điều không nên thay đổi là **trạng thái nghiệp vụ do chính ý định đọc yêu cầu**, như trừ tồn kho, chuyển trạng thái đơn hay thu tiền.

### 3.2. Anti-pattern: dùng GET để thực hiện action ghi

Không nên:

~~~http
GET /v1/orders/o-918/cancel HTTP/1.1
GET /v1/wallets/w-7/withdraw?amount=100000 HTTP/1.1
GET /v1/emails/send-confirmation?orderId=o-918 HTTP/1.1
~~~

Vấn đề:

1. Browser, crawler, link preview, prefetcher và proxy có thể gọi GET mà người dùng không chủ động xác nhận.
2. GET là safe nên những thành phần trên có thể tự động hoặc lặp lại request theo chính sách của chúng.
3. Cache có thể phục vụ lại response mà origin không nhận request mới, khiến hành vi “ghi thông qua GET” khó đoán.
4. Một phép thử GET lặp có thể nhân đôi thanh toán, hủy hoặc email, phá vỡ ngữ nghĩa safe.

Hãy mô hình hóa action thành **resource/process** và dùng phương thức phù hợp: POST tạo cancellation request, PUT đặt trạng thái một resource xác định khi hợp đồng cho phép, hoặc DELETE với ý nghĩa loại bỏ resource đích. Việc đặt tên URI kiểu động từ không quyết định ngữ nghĩa; **method + resource contract** mới là trọng tâm.

### 3.3. Ghi log, analytics và bộ đếm xem trang

RFC không yêu cầu GET hoàn toàn không làm server thay đổi bất kỳ byte nào. Server có thể ghi audit access log, metrics hoặc thống kê. Nhưng nếu tính lượt xem là **nghiệp vụ được tính phí/thưởng hoặc kích hoạt một hành động có hiệu lực ngoài ý định đọc**, phải cẩn trọng: một crawler hoặc retry GET có thể làm số liệu đó tăng ngoài dự kiến.

Các tác dụng phụ như logs cần được tách khỏi bất biến nghiệp vụ. Nếu yêu cầu thực sự là **ghi một lượt xem có ý nghĩa nghiệp vụ**, có thể dùng POST tạo một sự kiện với idempotency theo event ID thay vì kỳ vọng một GET được gọi đúng một lần.

### 3.4. GET, caching và conditional GET

GET có khả năng cache mạnh nhất trong HTTP; nhưng **cacheable** còn phụ thuộc Cache-Control, status, Vary, quyền và các quy tắc RFC 9111. Response GET có thể trả 304 Not Modified khi client gửi:

~~~http
GET /v1/products/p-42 HTTP/1.1
Host: api.example.test
If-None-Match: "product-v7"
~~~

Nếu representation được chọn chưa thay đổi theo validator, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-v7"
Cache-Control: public, max-age=30

~~~

**304 không có response content** và không làm GET mất tính idempotent. Client/cache phải có representation lưu phù hợp để sử dụng 304. Nếu GET chứa thông tin cá nhân, caching phải thiết kế theo quyền; **GET safe không đồng nghĩa public cache an toàn**.

## 4. PUT: đặt trạng thái target resource bằng representation

**PUT** yêu cầu tạo hoặc thay thế trạng thái của **target resource** bằng trạng thái được định nghĩa bởi representation trong request, theo hợp đồng và các ràng buộc của server.

~~~http
PUT /v1/profiles/u-17 HTTP/1.1
Host: api.example.test
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "displayName": "An",
  "preferredLocale": "vi"
}
~~~

Nếu server chấp nhận representation như một phép thay thế trạng thái profile, gửi **cùng PUT** hai lần có ý định đưa resource về cùng giá trị. Đó là lý do PUT được HTTP quy định là **idempotent**, dù có thể có log/response/metadata phụ trợ khác nhau.

### 4.1. PUT là phép đặt trạng thái, không mặc định là “cộng dồn”

Thiết kế không phù hợp:

~~~http
PUT /v1/counters/c-1 HTTP/1.1
Content-Type: application/json

{"incrementBy":1}
~~~

Nếu server hiểu request này là **tăng counter thêm 1 mỗi lần**, gọi hai lần sẽ tăng 2: đây là **ngữ nghĩa action** không tương thích với ý định PUT idempotent.

Thiết kế khác:

~~~http
PUT /v1/counters/c-1 HTTP/1.1
Content-Type: application/json

{"value":42}
~~~

Nếu hợp đồng là **đặt counter thành 42**, lặp cùng request hướng tới cùng trạng thái. Đối với cập nhật tương đối hoặc action “tăng một đơn vị”, có thể dùng POST tới một resource lệnh/sự kiện có ID riêng và chống trùng.

### 4.2. PUT tạo mới và PUT cập nhật

Nếu target resource **chưa có** và server cho phép PUT tạo resource ở URI đó, thành công có thể trả **201 Created**. Nếu resource đã tồn tại và được thay thế, response thành công **200 OK** hoặc **204 No Content** tùy hợp đồng.

~~~http
PUT /v1/preferences/u-17 HTTP/1.1
Content-Type: application/json

{"theme":"dark"}
~~~

~~~http
HTTP/1.1 201 Created
Location: /v1/preferences/u-17
~~~

Lần tiếp theo gửi **cùng PUT** có thể trả:

~~~http
HTTP/1.1 204 No Content
~~~

**201 rồi 204 không vi phạm idempotency.** Định nghĩa idempotent nói về hiệu ứng dự kiến, không yêu cầu status code hoặc response body mọi lần giống hệt.

### 4.3. Payload đầy đủ hay cập nhật từng phần?

Một PUT đúng thiết kế cần xác định **representation nào được phép thay thế trạng thái**. Nếu contract định nghĩa các thuộc tính bắt buộc, server phải validate; đừng tự biến việc thiếu field thành “cứ giữ nguyên field cũ” mà không có quy tắc công khai.

Ví dụ:

~~~json
{
  "displayName": "An",
  "preferredLocale": "vi",
  "marketingConsent": false
}
~~~

Khi client gửi lại y nguyên, server phải hiểu rõ những thuộc tính bị bỏ qua được xử lý ra sao. Nếu chỉ muốn sửa một phần của resource, **PATCH** thường diễn tả ý định tốt hơn, nhưng PATCH **không mặc định idempotent**. Một PATCH kiểu “đặt theme thành dark” có thể idempotent; kiểu “tăng tổng tiền thêm 10” thì không.

Không cần biến mọi dữ liệu nội bộ của server thành một field public của PUT. Các trường như ID do server cấp, audit timestamp, version, security ownership có thể được quản lý riêng và được xác định rõ là không thể bị client thay đổi.

### 4.4. Version và timestamp có thể đổi khi retry

Server có thể ghi log từng lần PUT hoặc quản lý lịch sử revision. Nhưng với resource được cập nhật liên tiếp, cần cân nhắc tránh **tăng phiên bản hoặc phát sự kiện nghiệp vụ mới vô ích** khi payload thực sự không đổi. Nếu mỗi lần retry lại kích hoạt gửi email, gọi thanh toán hoặc phát “profile-updated” với hệ quả độc lập, hệ thống có thể mất idempotency **ở cấp nghiệp vụ**, ngay cả khi giá trị profile cuối vẫn là “An”.

Một cách thiết kế tốt là kiểm tra trạng thái/phiên bản, phân biệt **no-op** với thay đổi thực và phát sự kiện chỉ khi transition hợp lệ, hoặc bảo vệ consumer bằng deduplication. Đừng dùng tên method PUT để hợp thức hóa tác động ngoài hệ thống lặp không kiểm soát.

## 5. DELETE: cùng ý định loại bỏ resource, response có thể khác nhau

**DELETE** yêu cầu origin **loại bỏ mối liên hệ giữa target resource và chức năng hiện tại** của nó. HTTP không bắt buộc xóa vật lý một hàng database. Server có thể dùng xóa mềm, tombstone, hủy kích hoạt hoặc chuyển sang quá trình xóa bất đồng bộ, miễn là hợp đồng về target resource và trạng thái sau thao tác rõ ràng.

~~~http
DELETE /v1/carts/cart-42/items/item-7 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Nếu việc xóa thành công, server có thể trả:

~~~http
HTTP/1.1 204 No Content
~~~

Sau khi mất response, client gửi lại đúng DELETE. Resource item-7 đã không còn ở collection giỏ hàng. Server có thể trả **404 Not Found**, **410 Gone** nếu có đủ thông tin và chọn công bố, hoặc **204 No Content** nếu contract coi việc “đã không còn tồn tại” là thành công. Các lựa chọn có thể **đều tương thích với idempotency**, miễn tác động dự kiến vẫn là item đó không còn được liên kết trong cart.

### 5.1. 204 và 404 không phải bằng chứng DELETE không idempotent

| Lần gửi | Trạng thái resource trước khi xử lý | Response ví dụ | Hiệu ứng dự kiến sau thao tác |
|---|---|---|---|
| Lần 1 | Item đang tồn tại trong cart | 204 | Item không còn trong cart |
| Lần 2 | Item đã không còn | 404 | Item vẫn không còn trong cart |
| Lần 3 | Item vẫn không còn | 404 | Item vẫn không còn trong cart |

Vì **trạng thái mục tiêu sau các lần gửi lặp tương đương**, phản hồi khác nhau không làm phương thức mất tính idempotent. Không cần bắt mọi DELETE thứ hai trả 204 chỉ để “đúng idempotency”.

### 5.2. DELETE trả 200, 202 hay 204?

Theo ngữ nghĩa HTTP:

- **204 No Content:** tác động xóa đã được thực hiện, không cần response content.
- **200 OK:** tác động xóa đã được thực hiện và trả một biểu diễn mô tả trạng thái/kết quả.
- **202 Accepted:** yêu cầu xóa đã được nhận nhưng chưa hoàn tất xử lý.

Ví dụ xóa bất đồng bộ:

~~~http
DELETE /v1/exports/ex-42 HTTP/1.1
Host: api.example.test

HTTP/1.1 202 Accepted
Location: /v1/deletion-jobs/dj-42
Content-Type: application/json

{"jobId":"dj-42","status":"QUEUED"}
~~~

Để giữ hiệu ứng idempotent, retry cùng DELETE không được **tạo vô số deletion job độc lập** gây tác dụng lặp. Có thể dùng job ID ổn định theo resource/operation hoặc cơ chế dedupe bền vững. Một GET tới resource job cho phép client quan sát tiến độ; **202 không bảo đảm job đã hoàn thành**.

### 5.3. DELETE có thể xóa mềm nhưng vẫn idempotent

Một ứng dụng lưu:

~~~text
document_id = doc-42
deleted = false
~~~

DELETE đặt **deleted=true**. Lần thứ hai thấy đã xóa thì bỏ qua. Nếu hệ thống giữ tombstone và chính sách không phục hồi tự động, trạng thái công khai vẫn “không tồn tại”. Tuy nhiên, nếu mỗi DELETE tự động xóa/hủy thêm một resource khác hoặc cộng số lượng “đã xử lý” có giá trị nghiệp vụ mỗi lần, API có thể gây side effect không phù hợp.

**Xóa mềm** cũng không có nghĩa có thể bỏ qua retention, audit, quyền, bảo vệ dữ liệu và quy trình phục hồi. HTTP chỉ nêu ngữ nghĩa method, không quy định storage engine.

### 5.4. DELETE body không có ngữ nghĩa HTTP chung

Không nên dựa vào body kiểu:

~~~http
DELETE /v1/documents HTTP/1.1
Content-Type: application/json

{"ids":["doc-1","doc-2"]}
~~~

để xác định **những resource cần xóa** trên một API liên thông. Theo RFC 9110, DELETE request content không có ngữ nghĩa chung được xác định và có thể không được các trung gian xử lý nhất quán. Hãy dùng **target URI rõ ràng** cho một resource, hoặc mô hình hóa **POST /v1/deletion-jobs** nhận danh sách ID và trả URI công việc, có idempotency key khi cần.

### 5.5. DELETE có liên quan dữ liệu khác?

Xóa một resource có thể dẫn đến cascade delete, event cho search index, xóa attachment, phát thông báo và cập nhật quota. Nhóm cần lập bảng **hiệu ứng dự kiến** cho toàn nghiệp vụ:

| Hiệu ứng | Khi một DELETE bị lặp | Cách bảo đảm |
|---|---|---|
| Loại resource khỏi collection | Không tạo thêm thay đổi sau lần đầu | Đặt trạng thái/tombstone ổn định |
| Xóa search-index document | Xóa lại cùng ID không gây hại | Consumer xử lý remove idempotent |
| Phát sự kiện DocumentDeleted | Tránh phát một event nghiệp vụ mới mỗi retry khi không có transition | Transactional outbox; event ID |
| Gửi email thông báo xóa | Không gửi nhiều email cho một lần xóa logic nếu nghiệp vụ không muốn | Unique notification job theo deletion ID |
| Gọi dịch vụ thanh toán để hoàn tiền | Không được hoàn tiền trùng | Payment/compensation operation ID + PSP idempotency và đối soát |

Điểm cuối rất quan trọng: **DELETE resource đơn hàng không được mặc nhiên đồng nghĩa hoàn tiền một lần**. Hoàn tiền là một quy trình nghiệp vụ riêng; phải mô hình hóa nó có trạng thái, mã giao dịch và idempotency xuyên ranh giới dịch vụ.

## 6. Phạm vi bảo đảm: method không đồng nghĩa “exactly once”

Một request HTTP đi qua nhiều tầng:

~~~mermaid
flowchart LR
    C["Client"] --> G["CDN / API Gateway"]
    G --> A["Spring REST API"]
    A --> D[("Database")]
    A --> Q[("Outbox / Queue")]
    Q --> W["Worker"]
    W --> P["ERP / PSP / Email"]
    G -.->|"Timeout / reset / retry"| C
~~~

**Tính idempotent của method** là một quy ước ngữ nghĩa cho yêu cầu từ client tới target resource. Nó không tự hứa:

1. Request chỉ đi qua gateway một lần.
2. Controller chỉ được gọi một lần.
3. Giao dịch database chỉ được bắt đầu một lần.
4. Queue chỉ chứa một event.
5. Email/PSP/ERP không bao giờ nhận message trùng.
6. Response của mọi lần thử là byte-for-byte giống nhau.
7. Không có cập nhật cạnh tranh từ những client khác.
8. Client luôn biết tác động đã thực hiện hay chưa khi mạng thất bại.

### 6.1. Phân biệt at-most-once, at-least-once và idempotency

| Khái niệm | Cách hiểu trong một luồng xử lý | Ý nghĩa thực tế |
|---|---|---|
| **At-most-once attempt** | Không cố ý gửi lại sau khi chưa chắc kết quả | Có thể bỏ sót xử lý nếu request chưa tới server |
| **At-least-once delivery/retry** | Cố gắng gửi lại khi chưa nhận kết quả | Có thể nhận trùng, cần idempotency/dedupe |
| **Idempotent effect** | Thực thi lặp cùng ý định cho kết quả trạng thái dự kiến như một lần | Có thể an toàn về hiệu ứng, dù vẫn có nhiều attempt |
| **Exactly-once end-to-end** | Không mất cũng không nhân đôi tác động xuyên mọi ranh giới | Rất khó; cần protocol, trạng thái bền vững, transaction và đối soát cụ thể |

Trong phần lớn REST API thực tiễn, mục tiêu hữu ích là **at-least-once retry với hiệu ứng nghiệp vụ idempotent và khả năng tra cứu/đối soát**. Không tuyên bố “exactly once” chỉ vì endpoint sử dụng PUT/DELETE hoặc có header Idempotency-Key.

### 6.2. “Cùng request” nhưng có thay đổi từ actor khác

Hãy xét:

~~~text
T1: Client A PUT /preferences/u-17  {"theme":"dark"}
T2: Client B PUT /preferences/u-17  {"theme":"light"}
T3: Client A retry PUT cũ        {"theme":"dark"}
~~~

PUT của A **vẫn là method idempotent khi xét lặp cùng ý định**, nhưng retry tại T3 có thể **ghi đè thay đổi của B**. Đó là **lost update/race**, không phải phản ví dụ cho định nghĩa idempotency.

Nếu client cần đảm bảo không làm mất cập nhật của người khác, phải bổ sung **precondition/versioning** như ETag/If-Match, chứ không dựa vào riêng tính idempotent của PUT.

### 6.3. Hiệu ứng phụ dự kiến và những hệ thống bên ngoài

Một API có thể đặt trạng thái đơn thành **CANCELLED** bằng PUT và sau đó yêu cầu hoàn tiền. Nếu mỗi lần retry lại tạo một payment transaction, tổng trạng thái đơn vẫn CANCELLED nhưng **tác động tài chính không idempotent**. Khi đó hợp đồng nghiệp vụ của API chưa an toàn để retry.

Thiết kế cần làm rõ:

- Trạng thái nào là **resource state** được client yêu cầu?
- Hiệu ứng nào **phải xảy ra đúng một lần theo ý nghĩa nghiệp vụ** (ví dụ một lần hoàn tiền cho một cancellation)?
- Hiệu ứng nào **có thể lặp vô hại** (như xóa lại cùng search index ID)?
- Khi một phụ thuộc timeout, **làm sao biết nó đã thực hiện tác động chưa**?
- Ai chịu trách nhiệm **đối soát** những trạng thái chưa rõ?

Tính idempotent của HTTP method là **điểm khởi đầu** cho thiết kế, không thay cơ chế đồng bộ dữ liệu và giao dịch phân tán.

## 7. Retry khi timeout: phản hồi bị mất không chứng minh thao tác thất bại

Một kịch bản điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    actor C as REST Client
    participant G as Gateway
    participant A as Spring API
    participant D as Database
    C->>G: PUT /profiles/u-17 + representation R
    G->>A: PUT /profiles/u-17 + R
    A->>D: Commit trạng thái R
    D-->>A: Commit thành công
    Note over G,A: Kết nối bị reset trước khi response tới client
    G--xC: Không có response / timeout
    C->>G: Retry cùng PUT và R
    G->>A: PUT /profiles/u-17 + R
    A->>D: Kiểm tra / đặt trạng thái R
    A-->>C: Kết quả phù hợp sau retry
~~~

Client không biết lần đầu đã được thực thi. **Retry một phương thức idempotent có thể là lựa chọn an toàn hơn** so với một POST không có cơ chế chống trùng. Nhưng kể cả với PUT, cần để ý precondition, actor khác có thể đã cập nhật, deadline và side effect không mong muốn.

### 7.1. HTTP 502, 503, 504 nói gì?

| Tình huống | Có thể quan sát | Điều không được kết luận |
|---|---|---|
| Gateway nhận phản hồi upstream không hợp lệ | **502 Bad Gateway** | Không chắc origin chưa thực hiện nghiệp vụ |
| Dịch vụ tạm không phục vụ được | **503 Service Unavailable**, có thể có Retry-After | Không chắc request trước đó chưa commit |
| Gateway chờ upstream quá deadline | **504 Gateway Timeout** | Không chắc PUT/DELETE/POST thất bại |
| Quá quota theo client/key | **429 Too Many Requests** | Không phải tín hiệu mọi retry ngay đều tốt |
| Client gửi request không đầy đủ trong thời gian cho phép | **408 Request Timeout** trong bối cảnh phù hợp | Không được trộn với mọi timeout tại gateway |
| Lỗi DNS/TLS/connection reset tại client | **Có thể không có HTTP status** | Không phải HTTP 500 nếu chưa nhận được response |

Một mã 5xx mô tả **điều kiện lỗi ở hop trả response**, không phải bản ghi trạng thái giao dịch. Với thao tác ghi cần nhận diện outcome chưa rõ bằng **resource ID, request ID hoặc idempotency key**.

### 7.2. RFC 9110 nói gì về retry tự động?

HTTP Semantics giải thích client **có thể** thử lại request với method idempotent khi gặp **lỗi giao tiếp xảy ra trước khi đọc được response**. Proxy **không nên** tự động thử lại phương thức không idempotent; client không nên tự động retry non-idempotent request nếu không có bằng chứng/hợp đồng bảo đảm an toàn.

Đây không phải mệnh lệnh “thấy 500/502/503/504 là retry tất cả GET/PUT/DELETE”. Response đã nhận, rate limiting, Retry-After, điều kiện thay đổi và ngân sách tổng của client vẫn quyết định việc retry có hợp lý hay không.

### 7.3. Retry policy là một hợp đồng vận hành

Một chính sách retry có kiểm soát thường có:

- **Classification:** loại thao tác, HTTP status, transport error và kết quả nghiệp vụ chưa rõ.
- **Exponential backoff + jitter:** giảm retry đồng loạt khi nhiều client gặp sự cố.
- **Max attempts:** số lần thử lại tối đa, tính cả retry tự động của SDK/gateway nếu có thể.
- **Overall deadline:** thời gian cho phép của cả hành trình, không chỉ timeout mỗi lần gọi.
- **Retry budget:** giới hạn tổng tải tăng thêm do retry, đặc biệt khi upstream quá tải.
- **Retry-After:** tôn trọng chỉ dẫn từ server nếu có và còn nằm trong deadline.
- **Circuit breaker / load shedding:** giảm áp lực lên service đang lỗi thay vì giữ vô hạn request.
- **Observability:** phân biệt request attempt với **logical operation** và đo duplicate-suppression.

Nếu một request được tự động thử lại ở **client, gateway và service nội bộ**, tổng số attempt có thể tăng mạnh. Giả sử mỗi trong ba tầng cho phép tổng cộng ba lần gọi gồm lần đầu, trong tình huống xấu nhất có thể có tới \(3 \times 3 \times 3 = 27\) attempt ở downstream cho một logical operation. Ví dụ này là tính giới hạn minh họa, không có nghĩa mọi hệ thống luôn tạo 27 request.

### 7.4. Một ví dụ backoff có jitter

~~~text
Lần gọi đầu: timeout hoặc nhận lỗi được phân loại retryable
Retry 1: chờ khoảng 100–300 ms (jitter)
Retry 2: chờ khoảng 300–700 ms
Retry 3: chỉ gửi nếu còn tổng deadline và retry budget
Hết deadline: trả trạng thái chưa rõ hoặc hướng dẫn tra cứu resource
~~~

Các con số chỉ là ví dụ, phải điều chỉnh theo latency/SLO thực tế. **Không dùng retry vô hạn** và không tăng timeout tùy tiện để che một dependency bị tắc.

### 7.5. Không retry tự động 409/412 như lỗi mạng

**409 Conflict** thường báo xung đột trạng thái nghiệp vụ. **412 Precondition Failed** báo điều kiện If-Match/If-Unmodified-Since không còn đúng. Thử lại **cùng request không thay đổi** thường không giải quyết được xung đột; client cần đọc trạng thái mới, quyết định gộp/sửa dữ liệu hoặc hỏi người dùng.

Không tự đổi ETag cũ thành ETag mới rồi gửi lại cùng payload nếu chưa kiểm tra liệu việc đó có **ghi đè công việc của người khác** hay không.

## 8. ETag và If-Match: bảo vệ PUT/DELETE khi có cập nhật cạnh tranh

**Idempotency** trả lời: “Lặp cùng ý định có nhân đôi hiệu ứng dự kiến không?”. **Optimistic concurrency control** trả lời câu hỏi khác: “Client có đang ghi dựa trên **phiên bản resource** mà nó thật sự đã đọc không?”. Trong REST API có nhiều người chỉnh sửa, cần hiểu cả hai.

### 8.1. Tình huống mất cập nhật

~~~text
10:00:00  A GET /profiles/u-17 -> version 7, displayName=An
10:00:01  B GET /profiles/u-17 -> version 7, displayName=An
10:00:02  B PUT -> version 8, displayName=An Nguyen
10:00:03  A PUT toàn bộ bản cũ -> displayName=An
~~~

Nếu server chấp nhận PUT của A không kiểm tra version, thay đổi của B bị ghi đè. **Cả hai request PUT đều có thể idempotent** khi xét riêng từng request, nhưng hệ thống vẫn mất cập nhật.

### 8.2. GET với ETag, PUT với If-Match

Client lấy biểu diễn và strong ETag:

~~~http
GET /v1/profiles/u-17 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "profile-v7"
Cache-Control: no-store

{
  "id": "u-17",
  "displayName": "An",
  "preferredLocale": "vi"
}
~~~

Sau khi người dùng sửa, client gửi:

~~~http
PUT /v1/profiles/u-17 HTTP/1.1
Host: api.example.test
Content-Type: application/json
If-Match: "profile-v7"
Authorization: Bearer <access-token>

{
  "displayName": "An Nguyen",
  "preferredLocale": "vi"
}
~~~

**If-Match** yêu cầu server chỉ áp dụng thay đổi khi biểu diễn hiện tại thỏa **strong comparison** với entity tag đã gửi (ngoại trừ những điều kiện đặc biệt được chuẩn quy định). Khi điều kiện đúng, có thể trả:

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
~~~

**Lưu ý chuẩn quan trọng:** RFC 9110 chỉ cho phép gửi validator như ETag trong response thành công của PUT khi dữ liệu biểu diễn từ request được lưu **không qua chuyển đổi**, và validator đại diện cho representation mới đó. Trong ví dụ này, GET có trường ID do server bổ sung nên response PUT **không gửi ETag**; client có thể GET lại để lấy ETag của biểu diễn mới. Không mặc định luôn được gửi validator sau PUT khi server có xử lý/chuẩn hóa representation.

Nếu resource đã chuyển sang version 8 do người khác ghi và client vẫn dùng ETag "profile-v7", server thường trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/version-conflict",
  "title": "Resource version has changed",
  "status": 412,
  "code": "VERSION_CONFLICT",
  "detail": "Reload the resource before attempting an update."
}
~~~

Client phải lấy representation hiện tại, xem có cần gộp thay đổi hay không, rồi mới quyết định gửi bản cập nhật mới.

### 8.3. Replay của một PUT có If-Match có thể trả 412

Một khác biệt tinh tế:

~~~text
Lần 1: PUT + If-Match:"profile-v7" -> server cập nhật thành v8
          Response 204 bị mất trên mạng.
Lần 2: Retry PUT + If-Match:"profile-v7"
          Điều kiện không còn đúng; thường nhận 412.
~~~

Điều này **không có nghĩa PUT không idempotent**. Precondition ngăn việc ghi lại khi resource đã đổi, và trạng thái client cần được **đối soát**. Nếu client nhận 412 sau một lần timeout, có thể chính lần trước đã thành công, hoặc người khác đã sửa resource. **412 một mình không phân biệt hai nguyên nhân.**

Quy tắc hữu ích:

1. Lấy lại resource qua GET nếu được phép.
2. So sánh với trạng thái mong muốn và đọc version mới.
3. Nếu trạng thái đã phù hợp, coi logical operation có thể đã hoàn tất, nhưng **không suy ra chắc chắn tác dụng phụ khác đã thành công** khi chưa có cơ chế đối soát.
4. Nếu trạng thái khác, thực hiện quy trình giải quyết xung đột; không “bỏ If-Match cho dễ”.

RFC 9110 cho phép một số tình huống có thể trả **2xx khi server đã xác minh thay đổi yêu cầu đã được thực hiện**, nhưng hành vi đó có điều kiện chặt chẽ. Không viết client mặc định phải nhận cùng 204 cho lần retry có precondition cũ.

### 8.4. Khi nào trả 428 Precondition Required?

Nếu API quy định mọi cập nhật phải có điều kiện để chống mất cập nhật:

~~~http
PUT /v1/profiles/u-17 HTTP/1.1
Content-Type: application/json

{"displayName":"An Nguyen","preferredLocale":"vi"}
~~~

server có thể trả **428 Precondition Required** khi thiếu header điều kiện theo policy. Trong khi đó, **412** nói điều kiện **đã được gửi nhưng không được thỏa**. **409 Conflict** dùng cho xung đột nghiệp vụ không nhất thiết do HTTP precondition.

Đừng nhầm các mã này với **429 Too Many Requests** hoặc lỗi retryable tạm thời. Không tự động retry một request 428 bằng cách đoán ETag.

### 8.5. If-Match cho DELETE

Ví dụ muốn xóa tài liệu chỉ khi phiên bản còn là v4:

~~~http
DELETE /v1/documents/doc-42 HTTP/1.1
Host: api.example.test
If-Match: "document-v4"
Authorization: Bearer <access-token>
~~~

Nếu người khác đã cập nhật tài liệu lên v5, server có thể trả **412** mà không xóa. Nếu tài liệu đã bị xóa, status có thể là **404/410** theo hợp đồng. Khi client retry DELETE với điều kiện cũ, nó không được giả định “404 = chưa xóa được”; cần phân biệt resource không còn tồn tại, lỗi phân quyền bị che giấu và trạng thái hệ thống chưa rõ.

### 8.6. Kiểm tra điều kiện phải gắn với commit

Một anti-pattern:

~~~text
1. SELECT current_version FROM profile WHERE id = ?
2. Nếu version khớp, gọi nhiều service rồi chờ.
3. UPDATE profile SET ... WHERE id = ?   (không kiểm lại version)
~~~

Giữa bước 1 và 3, một client khác có thể ghi thành công. Kiểm tra phiên bản ở controller **không đủ**. Cần transaction/optimistic locking hoặc thao tác so sánh và cập nhật nguyên tử ở tầng dữ liệu, ví dụ về mặt ý tưởng:

~~~sql
UPDATE profiles
SET display_name = :display_name,
    preferred_locale = :preferred_locale,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, cần xác định resource không tồn tại, không được phép truy cập hoặc version không khớp theo chính sách API. **Không trả 204 thành công** nếu không có thay đổi được áp dụng mà hợp đồng yêu cầu thay thế trạng thái.

Với DELETE có điều kiện, dùng tương tự một thao tác nguyên tử để xóa/đánh dấu xóa theo ID + version, rồi phát event qua một cơ chế không mất thông tin sau commit (ví dụ transactional outbox).

### 8.7. If-None-Match: * và tạo resource

Ngoài If-Match, client có thể dùng **If-None-Match: \*** để yêu cầu tạo resource **chỉ khi chưa có biểu diễn hiện tại** tại URI đó, theo điều kiện HTTP:

~~~http
PUT /v1/user-settings/u-17 HTTP/1.1
Host: api.example.test
If-None-Match: *
Content-Type: application/json

{"theme":"dark"}
~~~

Nếu đã có resource, điều kiện sẽ không thỏa và server có thể trả 412. Đây là cách hữu ích tránh tình trạng một request tạo resource ghi đè tài nguyên đang tồn tại, nhưng **không thay thế** validation và authorization.

## 9. Side effect, event và tích hợp ngoài hệ thống: lũy đẳng ở đâu?

Một PUT/DELETE có thể là “một lần thay đổi trạng thái” ở database nhưng gây nhiều hiệu ứng phụ không mong muốn khi request bị lặp hoặc worker phát lại event.

### 9.1. Phân biệt business transition và request attempt

Giả sử PUT thay đổi trạng thái một cấu hình:

~~~http
PUT /v1/alerts/a-19 HTTP/1.1
Content-Type: application/json

{"enabled":true}
~~~

Thiết kế đáng tin cậy:

- Nếu alert đang disabled, transaction chuyển sang enabled và tạo **một event AlertEnabled** với ID ổn định.
- Nếu alert đã enabled và cùng dữ liệu, không tạo một business transition độc lập nữa.
- Request log có thể ghi hai attempt; đó là quan sát khác với một event nghiệp vụ.
- Nếu event phải đi qua queue, consumer xử lý idempotent theo eventId/transitionId.

Thiết kế dễ lỗi:

~~~text
Mỗi lần PUT enabled=true
  -> gửi email "Alert was enabled"
  -> tạo một invoice fee
  -> cập nhật external CRM bằng lệnh "increment"
~~~

Những tác động tương đối hoặc có phí này có thể lặp nhiều lần dù resource cuối vẫn **enabled=true**. Cần dùng ID thao tác, idempotency ở downstream, hoặc tách các hành động thành resource với trạng thái riêng.

### 9.2. Transactional outbox cho event sau commit

Một cách hạn chế lỗi “database đã commit nhưng quên phát event” là ghi **resource state + outbox event** trong cùng transaction:

~~~mermaid
sequenceDiagram
    participant A as Spring API
    participant D as Database
    participant W as Outbox Publisher
    participant Q as Queue
    participant C as Consumer
    A->>D: BEGIN
    A->>D: UPDATE resource theo version/transition
    A->>D: INSERT outbox(eventId, resourceId, eventType)
    A->>D: COMMIT
    D-->>A: Commit thành công
    W->>D: Đọc outbox chưa phát
    W->>Q: Publish(eventId)
    Q->>C: Deliver eventId
    C->>C: Dedupe + áp dụng hiệu ứng
    Note over W,Q: Publish có thể bị lặp khi retry
~~~

Outbox không bảo đảm **exactly-once delivery**: publisher có thể gửi lại nếu mất ack sau publish. Consumer cần **idempotent effect** hoặc bảng inbox/deduplication. Nếu tác động là chuyển tiền hoặc gửi thông báo, cần thêm quy tắc idempotency ở hệ thống đích và khả năng đối soát.

### 9.3. Idempotency-Key là một hợp đồng khác

Một số API quy định header:

~~~http
Idempotency-Key: operation-6f0d
~~~

để nhận diện **logical operation**, đặc biệt hữu ích cho POST tạo resource hoặc hành động có tác động tài chính. Nhưng header này **không tự áp dụng** nếu server không triển khai:

- Khóa duy nhất theo phạm vi (user/tenant/route/operation).
- Dấu vân tay payload để phát hiện dùng lại key với nội dung khác.
- Trạng thái **IN_PROGRESS / COMPLETED / FAILED / UNKNOWN** hoặc mô hình tương đương.
- Ghi bền vững key, kết quả và liên kết tới resource/giao dịch.
- TTL, retention, xử lý cạnh tranh và trả kết quả cho request trùng.
- Cơ chế đối soát với PSP/ERP khi upstream timeout.

Không cần bắt mọi GET có Idempotency-Key: GET đã safe/idempotent theo method và thêm header có thể làm cache key/quan sát phức tạp không cần thiết. Với PUT/DELETE, key vẫn có thể hữu ích **để giữ kết quả nghiệp vụ hoặc chống side effect** trong những hệ thống cần kiểm soát tốt hơn ngữ nghĩa method.

### 9.4. Không dùng “dedupe 5 phút” rồi tuyên bố bảo đảm vĩnh viễn

Nếu client mất mạng 10 phút rồi retry trong khi idempotency key đã hết hạn sau 5 phút, server có thể xem đó là một operation mới. TTL là một phần **của hợp đồng**; phải chọn theo thời gian retry, luồng khách hàng, thời gian giữ transaction và ràng buộc nghiệp vụ. Với thanh toán, thường cần **business transaction ID bền vững và reconciliation**, không chỉ một cache key ngắn hạn.

### 9.5. Idempotency cũng liên quan đến external systems

| Ranh giới | Tình huống retry | Biện pháp |
|---|---|---|
| **REST API → DB** | Mất response sau commit | Version/unique constraint/transaction |
| **DB → event bus** | Publisher mất ack | Transactional outbox + eventId |
| **Event bus → worker** | Event được gửi lại | Inbox/dedupe + trạng thái xử lý bền vững |
| **Worker → ERP** | Lệnh reserve hàng timeout | Reservation ID ổn định + query/đối soát |
| **Worker → PSP** | Request refund timeout sau khi tiền đã được xử lý | Payment/refund ID, idempotency của PSP và reconciliation |
| **Worker → email provider** | Không nhận ack | Notification ID hoặc đánh dấu trạng thái; xác định mức lặp chấp nhận được |

Các kỹ thuật trên là **mẫu thiết kế**, không tự bảo đảm an toàn nếu nhà cung cấp không hỗ trợ hoặc cơ chế dedupe chỉ lưu trong RAM của một instance.

## 10. Java/Spring: triển khai GET, PUT, DELETE có contract rõ ràng

**Spring MVC** cung cấp các annotation **@GetMapping, @PutMapping, @DeleteMapping** để ánh xạ phương thức HTTP. Tuy nhiên, framework **không thể tự bảo đảm idempotency nghiệp vụ**. Controller cần chọn đúng method và giao cho service một contract giữ bất biến: bảo vệ quyền, kiểm tra version nguyên tử và tránh lặp side effect.

Ví dụ sau minh họa một API **profile**. Dùng Java 17, Spring Framework 6 và các interface service được giả định đã triển khai; không đưa logic database/phân quyền giả tạo vào controller chỉ để ví dụ trông như ứng dụng hoàn chỉnh.

### 10.1. DTO và service contract

~~~java
import jakarta.validation.constraints.NotBlank;

record ProfileView(
        String id,
        String displayName,
        String preferredLocale,
        long version) {}

record ProfileReplacement(
        @NotBlank String displayName,
        @NotBlank String preferredLocale) {}

interface ProfilesService {
    // Trả lỗi phù hợp khi không tồn tại hoặc không được phép đọc.
    ProfileView getVisible(String id);

    // Kiểm tra quyền + If-Match + version nguyên tử trong tầng lưu trữ.
    void replaceIfCurrent(
            String id, ProfileReplacement replacement, String ifMatch);

    // Chỉ xóa đúng target resource/version; không nhân đôi side effect.
    void deleteIfCurrent(String id, String ifMatch);
}
~~~

**ProfileReplacement** phải là representation cập nhật **toàn bộ những field client được phép thay thế** theo hợp đồng. Các trường quản lý bởi server như ID, owner và audit metadata không được phép thay đổi theo request body.

### 10.2. Controller

~~~java
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/v1/profiles")
class ProfilesController {
    private final ProfilesService service;

    ProfilesController(ProfilesService service) {
        this.service = service;
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ProfileView> get(@PathVariable String id) {

        ProfileView current = service.getVisible(id);
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .eTag("\"profile-v" + current.version() + "\"")
                .body(current);
    }

    @PutMapping(
            value = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> replace(
            @PathVariable String id,
            @Valid @RequestBody ProfileReplacement replacement,
            @RequestHeader(
                value = HttpHeaders.IF_MATCH,
                required = false
            ) String ifMatch) {

        requirePrecondition(ifMatch);
        service.replaceIfCurrent(id, replacement, ifMatch);
        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(
            @PathVariable String id,
            @RequestHeader(
                value = HttpHeaders.IF_MATCH,
                required = false
            ) String ifMatch) {

        requirePrecondition(ifMatch);
        service.deleteIfCurrent(id, ifMatch);
        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }

    private static void requirePrecondition(String ifMatch) {
        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "If-Match header is required");
        }
    }
}
~~~

Ở ví dụ này:

- **GET** chỉ truy vấn dữ liệu đã được phân quyền, trả ETag để client có thể sử dụng khi cập nhật. Không có thao tác nghiệp vụ thay đổi profile.
- **PUT** yêu cầu representation thay thế các field được phép cập nhật; **DELETE** yêu cầu xóa target resource.
- Hai phương thức ghi yêu cầu **If-Match** để giảm mất cập nhật; nếu thiếu, trả **428**.
- **Service** thực hiện kiểm tra quyền, định dạng ETag, strong comparison và cập nhật nguyên tử; nếu điều kiện không thỏa, trả **412** theo hợp đồng.
- **no-store** phù hợp với profile cá nhân; API không dựa vào HTTP cache để giữ trạng thái phiên bản.
- Response thành công của PUT/DELETE dùng **204**; không gửi body JSON kèm 204.

**Không nên đơn giản so sánh hai chuỗi header bằng equals** khi xây service: If-Match có cú pháp cho nhiều entity tag, dấu sao và weak tag; cần đánh giá điều kiện theo ngữ nghĩa HTTP, hoặc quy định/validate rõ phạm vi header API hỗ trợ mà vẫn trả lỗi hợp lý. **ETag** ở ví dụ dựa trên version nên phải bảo đảm version đổi khi mọi byte representation được bảo vệ thay đổi; nếu representation được tùy biến theo ngôn ngữ/quyền/encoding, thiết kế validator phải phù hợp hơn.

**Lưu ý:** các đoạn code chỉ là mẫu phần giao diện. Để chạy cần thêm repository, xác thực, phân quyền, validation/error handler, dữ liệu thử và service implementation. Không tự triển khai ghi database dưới controller bằng nhiều bước không transaction.

### 10.3. Service nên xử lý no-op và tranh chấp thế nào?

Pseudo-flow cho PUT:

~~~text
1. Xác thực principal, kiểm tra quyền WRITE trên profile ID.
2. Parse và kiểm tra If-Match bằng strong comparison.
3. Transaction:
     - Tìm profile và version hiện tại trong phạm vi quyền.
     - Nếu điều kiện không đúng: 412 hoặc response đặc biệt khi RFC cho phép.
     - Nếu representation đã giống yêu cầu: có thể no-op.
     - Nếu khác: cập nhật có điều kiện theo version (CAS).
     - Chỉ khi có transition thực, ghi outbox event nếu cần.
4. Commit, trả 204 nếu thành công.
~~~

Pseudo-flow cho DELETE:

~~~text
1. Xác thực principal, kiểm tra quyền DELETE.
2. Kiểm tra resource có còn tồn tại và If-Match có thỏa không.
3. Trong transaction, xóa mềm/vật lý có điều kiện theo version.
4. Nếu có transition mới sang "deleted", ghi outbox event một lần.
5. Commit và trả 204; lần retry trên resource không còn có thể 404/410.
~~~

Nếu gặp tranh chấp khi cập nhật, service nên phân loại **404/403/412** theo hợp đồng bảo mật đã duyệt. Có những API cố tình trả **404 thay vì 403** để không tiết lộ resource thuộc người khác; đừng để kiểm tra version tự làm lộ sự tồn tại của dữ liệu bí mật.

### 10.4. Một SQL conditional update chỉ minh họa cơ chế nguyên tử

~~~sql
UPDATE profiles
   SET display_name = :name,
       preferred_locale = :locale,
       version = version + 1
 WHERE id = :profile_id
   AND tenant_id = :authorized_tenant_id
   AND version = :expected_version
   AND deleted = FALSE;
~~~

Nếu **affected_rows = 1** thì thao tác cập nhật theo version đã thắng trong một database có cơ chế transaction thích hợp. Nếu bằng 0, phải xác định **not found, forbidden, deleted hoặc version mismatch** theo policy; không được mặc nhiên trả 204.

Một **optimistic-lock version** ở database phải được gắn nhất quán với ETag client nhận. Nếu server tính ETag từ nhiều bảng hoặc có representation khác theo locale, việc chỉ so version của một hàng có thể chưa đủ.

### 10.5. Dùng @Transactional và @Version có tự giải quyết hết không?

**@Transactional** có thể tạo ranh giới commit/rollback ở database, còn **@Version** trong JPA hỗ trợ optimistic locking cho entity được quản lý. Chúng hữu ích, nhưng không tự:

- Chuyển exception optimistic lock thành HTTP **412** đúng hợp đồng If-Match.
- Kiểm tra quyền trên resource trong mọi luồng.
- Giữ transaction qua một PSP/ERP HTTP call không có transaction chung.
- Dedupe event trong queue hoặc bảo đảm gửi email đúng một lần.
- Phân biệt response bị mất với lệnh chưa chạy.

Sử dụng chúng như **một phần** của thiết kế, rồi kiểm tra tác dụng ngoài database và khả năng đối soát.

## 11. Khi nào nên dùng POST, PATCH thay cho PUT/DELETE?

Để hiểu giới hạn của GET/PUT/DELETE, phải biết trường hợp **không phù hợp** với ba method này.

### 11.1. Tạo resource ở URI server cấp

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-70

{"cartId":"cart-70"}
~~~

Server chọn ID đơn mới và trả **201 Created + Location**. POST **không mặc định idempotent**: nếu client retry mà server không hỗ trợ key hoặc constraint khác, có thể tạo hai đơn. Cần tài liệu hóa idempotency key, status truy vấn và khả năng đối soát.

Nếu client được quyền xác định URI resource và request thể hiện **trạng thái cần có** của tài nguyên đó, **PUT** có thể phù hợp hơn:

~~~http
PUT /v1/user-settings/u-17 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"theme":"dark"}
~~~

### 11.2. Cập nhật một phần bằng PATCH

~~~http
PATCH /v1/profiles/u-17 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "profile-v7"

{"preferredLocale":"en"}
~~~

Một patch kiểu **đặt giá trị cụ thể** có thể được thiết kế idempotent, nhưng HTTP **không quy định mọi PATCH đều idempotent**. Với JSON Patch, operation như **add** vào một vị trí mảng hoặc move có thể không an toàn khi phát lại nếu không có điều kiện. Client cần hiểu chính **patch format và contract cụ thể**.

### 11.3. Action tương đối và command resource

Nếu thao tác là **tăng điểm, trừ tiền, gửi lại thông báo, hoàn tiền hoặc thêm một đơn vị tồn**, không nên đặt nó vào GET hoặc ngụy trang thành PUT với payload **incrementBy**.

Có thể tạo một resource hành động:

~~~http
POST /v1/refund-requests HTTP/1.1
Content-Type: application/json
Idempotency-Key: refund-order-918-v1

{
  "orderId": "o-918",
  "amount": 120000,
  "currency": "VND"
}
~~~

Server tạo **refund request** với mã/trạng thái bền vững và kiểm soát trùng. Client theo dõi **GET /v1/refund-requests/{id}** để biết kết quả, kể cả khi request ban đầu timeout.

### 11.4. Bảng chọn method theo ý định

| Nhu cầu | Method thường phù hợp | Lý do và lưu ý retry |
|---|---|---|
| Xem resource hiện tại | **GET** | Safe/idempotent; response có thể thay đổi theo thời gian |
| Xem metadata không tải body | **HEAD** | Safe/idempotent; không có response content |
| Thay thế trạng thái resource đích | **PUT** | Idempotent về ý định; cân nhắc If-Match và side effect |
| Loại bỏ resource đích | **DELETE** | Idempotent về ý định; xử lý xóa mềm, 404/410 và event trùng |
| Tạo resource với ID server cấp | **POST** | Không mặc định idempotent; cần key khi retry nguy hiểm |
| Sửa một phần theo patch document | **PATCH** | Tùy patch semantics; If-Match thường hữu ích |
| Tạo yêu cầu hoàn tiền, gửi email | **POST** đến action/job resource | Mô hình trạng thái công việc và dedupe logical operation |

**HATEOAS** có thể đưa các link relation tới các thao tác tiếp theo, nhưng một link HAL tự nó không nói method/payload. Client vẫn cần tài liệu relation hoặc affordance đủ rõ để biết khi nào dùng POST, PUT hay DELETE.

## 12. Retry ở Java client: đánh giá method, deadline và response

Khi dùng Java HttpClient, RestClient hoặc WebClient, SDK có thể có retry policy tùy cấu hình. **Không bật retry mù cho mọi method và status.** Trước hết nên viết rõ các quy tắc:

1. Xác định request **có thể retry về hiệu ứng nghiệp vụ** hay không.
2. Phân biệt **transport failure** (không có HTTP response) với **HTTP 5xx** đã nhận.
3. Nếu là **412/409**, không retry mà phải giải quyết xung đột.
4. Nếu **429/503** có Retry-After, cân nhắc chỉ dẫn này trong tổng deadline.
5. Giới hạn số attempt, backoff có jitter và không mất trace/correlation ID.
6. Với PUT/DELETE có If-Match, khi xảy ra timeout hoặc 412 sau retry cần **GET đối soát** chứ không tự xóa điều kiện.

### 12.1. Pseudocode retry có điều kiện

~~~text
function executeWithPolicy(request, overallDeadline):
    if request.method is POST/PATCH and no operation-level idempotency:
        return sendOnce(request)

    attempt = 0
    while now < overallDeadline and attempt < maxAttempts:
        attempt += 1
        try:
            response = send(request, remainingDeadline)
        catch networkErrorBeforeResponse:
            if not safeToRetry(request):
                return UNKNOWN_OUTCOME
            if not hasRetryBudget():
                return UNKNOWN_OUTCOME
            sleep(backoffWithJitter(attempt))
            continue

        if response.status in [409, 412, 428]:
            return NEEDS_RECONCILIATION_OR_NEW_PRECONDITION

        if response.status is success:
            return response

        if response.status in [429, 502, 503, 504]
           and safeToRetry(request) and hasRetryBudget():
            delay = honorRetryAfterOrBackoff(response, attempt)
            if delay > remainingDeadline:
                return response
            sleep(delay)
            continue

        return response

    return UNKNOWN_OR_FAILED_AS_DEFINED_BY_CONTRACT
~~~

Đây là **pseudocode chính sách**, không phải hàm copy-paste cho Java production. Việc xếp 502/503/504 vào nhóm *có thể cân nhắc retry* không có nghĩa luôn nên thử lại. **safeToRetry(request)** phải kiểm tra tác động ngoài hệ thống, request body có tái gửi được không, idempotency key, điều kiện If-Match và chính sách route.

### 12.2. Request body có thể tái gửi không?

Một số HTTP client dùng body từ stream **chỉ đọc được một lần**. Dù method là PUT, nếu retry gửi body đã bị tiêu thụ hoặc khác byte, đây **không còn là cùng request**. Đảm bảo body publisher/stream có thể tạo lại cùng representation hoặc dùng buffer an toàn trong giới hạn bộ nhớ và kích thước.

Với upload lớn, PUT có thể truyền dữ liệu hàng trăm MB; retry từ đầu có thể gây chi phí cao hoặc vượt deadline. Cân nhắc resumable upload/resource phần, checksum, ETag và giao thức hoàn tất upload phù hợp với dịch vụ, không dựa vào một retry mặc định.

### 12.3. Đừng coi 412 sau timeout là lỗi mạng tạm thời

Nếu một PUT đầu tiên đã áp dụng thành công nhưng response bị mất, retry với **cùng If-Match cũ** có thể nhận 412. Client không nên retry liên tiếp 412. Thay vào đó:

~~~text
PUT với If-Match v7 -> timeout
PUT retry cùng If-Match v7 -> 412
GET lại resource -> thấy trạng thái đã mong muốn ở v8
=> Có thể xác nhận trạng thái hiện tại đạt mục tiêu.
=> Nếu nghiệp vụ có effect ngoài (thanh toán, email), kiểm tra theo operation ID.
~~~

Nếu GET lại thấy trạng thái **khác** mong muốn, cần hiển thị conflict/gộp thay đổi hoặc hỏi người dùng. Không tự ghi đè bản mới để “buộc PUT thành công”.

### 12.4. Retry-After là chỉ dẫn, không phải bảo đảm

Server có thể gửi:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Cache-Control: no-store
~~~

hoặc Retry-After dưới dạng HTTP-date. Nếu client chỉ còn **5 giây** trong deadline, không hợp lý để chờ 30 giây và giữ giao diện treo. Có thể kết thúc luồng đồng bộ và cung cấp cách kiểm tra lại/trạng thái chờ. Thời gian retry được chọn phải nằm trong **ngân sách tổng**, không cộng timeout vô hạn qua nhiều tầng.

### 12.5. Lưu ý về retry tại gateway và SDK

Một SDK có thể thử lại PUT khi mất kết nối. API gateway cũng có thể thử lại kết nối tới target mới, còn backend HTTP client lại tự retry ERP. Nếu không biết có bao nhiêu tầng retry:

- Một lần người dùng bấm nút có thể tạo nhiều attempt.
- Hệ thống quá tải có thể chịu thêm retry storm.
- Log từ nhiều tầng làm khó phân biệt request gốc và các lần phát lại.
- Thao tác không thực sự idempotent ở downstream có thể bị nhân đôi.

Nên chọn **một hoặc một số tầng được kiểm soát** chịu trách nhiệm retry, có chung deadline/trace metadata và kiểm thử số attempt tối đa.

## 13. OpenAPI: ghi rõ method, điều kiện và phản hồi khi retry

OpenAPI giúp SDK biết method và schema, nhưng **không tự chứng minh backend idempotent**. Hãy tài liệu hóa If-Match, ETag, response 412/428 và hành vi khi resource không còn.

Ví dụ OpenAPI 3.0.3 rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Profile API
  version: 1.0.0
paths:
  /v1/profiles/{id}:
    parameters:
      - in: path
        name: id
        required: true
        schema:
          type: string
    get:
      summary: Read the current profile representation
      responses:
        '200':
          description: Profile representation
          headers:
            ETag:
              description: Strong validator for the selected representation
              schema:
                type: string
                example: '"profile-v7"'
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProfileView'
        '404':
          description: Profile not found or not disclosed
    put:
      summary: Replace the writable profile fields if version matches
      description: >
        PUT is idempotent as to its intended effect. If the response is
        lost, retry may yield 412 because a previous attempt succeeded.
        Clients should fetch the current resource to reconcile.
      parameters:
        - in: header
          name: If-Match
          required: true
          schema:
            type: string
            example: '"profile-v7"'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProfileReplacement'
      responses:
        '204':
          description: Replacement completed, no response content
        '412':
          description: ETag precondition not satisfied
        '428':
          description: If-Match precondition required by policy
        '404':
          description: Profile not found or not disclosed
    delete:
      summary: Delete the profile resource if version matches
      parameters:
        - in: header
          name: If-Match
          required: true
          schema:
            type: string
      responses:
        '204':
          description: Target resource was deleted
        '404':
          description: Resource absent or not disclosed
        '412':
          description: If-Match failed
        '428':
          description: If-Match required
components:
  schemas:
    ProfileReplacement:
      type: object
      required: [displayName, preferredLocale]
      properties:
        displayName:
          type: string
          minLength: 1
        preferredLocale:
          type: string
          example: vi
    ProfileView:
      allOf:
        - $ref: '#/components/schemas/ProfileReplacement'
        - type: object
          required: [id, version]
          properties:
            id:
              type: string
            version:
              type: integer
              format: int64
~~~

Trong API thật cần mô tả thêm **security schemes**, 400/401/403, lỗi Problem Details, giới hạn trường, quy tắc lưu dữ liệu và mapping authorization. Với 204, **không** khai báo response content. Đối với GET có dữ liệu riêng, tài liệu hóa Cache-Control phù hợp; **ETag không ngầm cho phép shared cache**.

### 13.1. Tài liệu idempotency phải có ví dụ retry

Đừng chỉ viết mô tả “PUT is idempotent” rồi kết thúc. Nên công bố:

- PUT thay thế trường nào, trường nào server quản lý?
- Cùng body nhưng If-Match cũ sẽ trả mã gì sau lần ghi thành công?
- Response mất sau commit thì client tra cứu bằng cách nào?
- DELETE lần hai trả 204 hay 404/410 theo hợp đồng?
- Cần giữ Idempotency-Key cho operation nào dù method là PUT/DELETE?
- Có các action/cascade/worker nào cần dedupe hoặc đối soát?
- Có giới hạn retry, Retry-After hoặc rate limit theo chính sách nhà cung cấp không?

Khi các câu trả lời này rõ ràng, client mới có đủ thông tin để thực hiện retry **theo nghiệp vụ**, không chỉ theo tên phương thức.

## 14. Kiểm thử: chứng minh idempotent effect, không chỉ đếm status code

Kiểm thử hiệu quả nhất cần so sánh **trạng thái và hiệu ứng sau một lần** với **trạng thái/hiệu ứng sau nhiều lần của cùng logical request**. Đừng chỉ assert “response thứ hai cũng là 204” rồi tuyên bố đạt idempotency.

### 14.1. Ma trận kiểm thử đề xuất

| Kịch bản | Thực hiện | Bằng chứng mong đợi |
|---|---|---|
| **GET lặp** | GET resource 10 lần | Không có thao tác nghiệp vụ ghi do GET; response có thể khác do cập nhật ngoài |
| **GET qua crawler/prefetch** | Crawler theo link GET tới resource | Không tạo đơn, trừ tồn hoặc gửi email |
| **GET conditional** | GET với If-None-Match đúng | Có thể 304 không có body, không thay đổi dữ liệu |
| **PUT lặp vô điều kiện** | PUT cùng target/body hai lần với API cho phép | Trạng thái mong muốn cuối tương đương một lần; side effect không nhân đôi |
| **PUT tạo mới** | PUT cùng URI/body hai lần, server cho phép tạo | Có thể 201 rồi 200/204; chỉ một resource logic |
| **PUT stale If-Match** | Client B cập nhật sau khi A GET; A gửi version cũ | 412, không ghi đè cập nhật của B |
| **PUT timeout sau commit** | Mô phỏng response bị mất sau DB commit rồi retry cùng If-Match | Lần retry có thể 412; GET đối soát đúng; không tạo hiệu ứng ngoài trùng |
| **DELETE lặp** | DELETE cùng target nhiều lần | Resource không còn; lần sau có thể 404/410/204 theo contract |
| **DELETE stale If-Match** | Resource đổi version trước khi DELETE | 412; resource không bị xóa nhầm |
| **Thiếu precondition** | PUT/DELETE không If-Match khi policy yêu cầu | 428, không thay đổi resource |
| **Dữ liệu sai** | PUT payload không hợp lệ | 400/422 theo hợp đồng, không ghi thay đổi một phần |
| **Authorization** | GET/PUT/DELETE resource của tenant khác | Không lộ dữ liệu hoặc cho phép thay đổi; không dùng cache chia sẻ sai |
| **Side effect duplicate** | Retry PUT/DELETE sau khi event đã commit | Không tạo nhiều refund/email nghiệp vụ cho cùng transition |
| **Outbox replay** | Publisher gửi lại cùng eventId | Consumer không nhân đôi tác dụng |
| **ERP/PSP timeout** | Upstream hoàn tất nhưng ack bị mất | Query/đối soát theo operation ID; không tạo giao dịch trùng |
| **Retry storm** | Nhiều client retry khi 503 | Backoff/jitter/rate limit không làm hệ thống sập thêm |
| **Concurrent PUT** | Nhiều client ghi với cùng version | Tối đa một update thành công ở phiên bản đó; các bên còn lại xử lý conflict |

Các trường hợp trên cần được chạy trên **môi trường có dữ liệu test kiểm soát**, có thể dùng stub/fault injection cho gateway, queue và PSP. Không giả định đơn vị test của controller đã chứng minh transaction/database/cross-service effects.

### 14.2. Cách kiểm chứng “cùng hiệu ứng”

Định nghĩa những điều cần đo:

- **Resource state:** giá trị field và trạng thái xóa sau mỗi attempt.
- **Entity count:** số profile/order/job thực sự được tạo; không tăng ngoài yêu cầu.
- **Business events:** số transition event duy nhất, không phải tổng số event delivery.
- **External transaction:** số payment/refund đã được PSP xác nhận, không chỉ số HTTP call.
- **Audit/observability:** phân biệt **attempt count** và **logical operation count**.
- **Concurrency:** không có lost update khi If-Match được áp dụng nguyên tử.

Một hệ thống có thể ghi **3 access logs** cho 3 lần retry và vẫn idempotent; nhưng nếu cũng tạo **3 refund transactions**, nó không còn an toàn về hiệu ứng nghiệp vụ.

### 14.3. Ví dụ kiểm tra HTTP contract bằng MockMvc

Giả sử ứng dụng đã có **ProfilesController**, ProfilesService triển khai đúng điều kiện If-Match và fixture profile **u-17** cho người dùng test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileHttpSemanticsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void getReturnsAValidatorForTheResource() throws Exception {
        mvc.perform(get("/v1/profiles/u-17"))
                .andExpect(status().isOk())
                .andExpect(header().exists("ETag"));
    }

    @Test
    void putWithoutRequiredIfMatchIsRejected() throws Exception {
        mvc.perform(put("/v1/profiles/u-17")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayName":"An","preferredLocale":"vi"}
                    """))
                .andExpect(status().isPreconditionRequired());
    }

    @Test
    void deleteWithoutRequiredIfMatchIsRejected() throws Exception {
        mvc.perform(delete("/v1/profiles/u-17"))
                .andExpect(status().isPreconditionRequired());
    }
}
~~~

Đây là **mẫu tích hợp** chứ chưa phải bộ test độc lập có thể chạy: cần cấu hình security/principal, fixture, database giả lập hoặc service bean phù hợp. Tình huống PUT/DELETE lặp, lost update, timeout sau commit và event dedupe phải có **test giao dịch** và **fault injection** riêng.

Nếu Spring Security hoặc một filter trả 401/403 trước khi request tới controller, test phải cấu hình principal hợp lệ để kiểm thử nhánh 428. Không sửa test bằng cách tắt mọi authorization rồi tưởng rằng logic production đã được chứng minh.

### 14.4. Kiểm thử concurrency với hai client

~~~text
Arrange:
  Resource profile/u-17 có ETag "profile-v7"

Client A:
  GET -> v7
Client B:
  GET -> v7

Concurrent actions:
  A PUT If-Match: v7 -> displayName: "An"
  B PUT If-Match: v7 -> displayName: "Binh"

Assert:
  Chỉ một thao tác chuyển trạng thái từ v7 thành v8.
  Thao tác kia bị từ chối bằng 412 theo hợp đồng.
  Resource cuối có dữ liệu của thao tác đã thắng.
  Không có hai business events độc lập với cùng version v7.
~~~

Nếu server dùng **SELECT version rồi UPDATE không có điều kiện** và thiếu cơ chế khóa đúng, cả hai request có thể cùng thấy v7 rồi ghi đè. Test concurrency phải phát hiện race đó; unit test tuần tự thường không tìm ra.

### 14.5. Kiểm thử mất response sau commit

Một bài kiểm thử có giá trị cao:

1. Client gửi PUT có request ID/If-Match.
2. Test proxy cho request đi qua, server commit thành công, sau đó **cố ý cắt response**.
3. Client chỉ quan sát timeout, không được “nhìn lén” trạng thái DB trước khi quyết định.
4. Client retry theo policy, có thể nhận 412.
5. Client GET resource để xác minh trạng thái, rồi kiểm tra số event/email/refund liên quan.
6. Assert **không có hiệu ứng nghiệp vụ nhân đôi**, và outcome chưa rõ đã có cách đối soát.

Lưu ý: không mô phỏng tình huống này bằng cách cho controller ném exception **trước** transaction; như vậy chưa thử được rủi ro khó nhất là **commit rồi mất response**.

### 14.6. Kiểm thử với gateway và service mesh

HTTP client trực tiếp vào Spring có thể chỉ gửi một request, còn gateway có thể retry vì reset hoặc 502/503. Cần đo:

- **Số attempt ở từng hop** cho cùng operation ID.
- Retry có giữ nguyên method, URI, body, If-Match và idempotency metadata không.
- Có tầng nào bỏ If-Match, đổi request body, tự retry POST không an toàn hoặc phát lại stream lỗi không.
- Các endpoint ghi có đi qua cache/proxy khác biệt giữa staging và production không.
- Tổng deadline và retry budget có được tôn trọng khi nhiều thành phần cùng thất bại không.

Một trace tốt có **logical operation ID** để nhóm request thuộc cùng ý định và **attempt ID** riêng cho từng lần truyền. Không gắn orderId/userId trực tiếp vào metric labels có cardinality cao.

## 15. Bài tập tình huống: giỏ hàng, hồ sơ và hoàn tiền

Một doanh nghiệp có bốn endpoint đang được đề xuất:

~~~text
A. GET    /v1/loyalty-points/u-17/add?points=5
B. PUT    /v1/profiles/u-17
          Body: {"displayName":"An","preferredLocale":"vi"}
C. DELETE /v1/carts/cart-42/items/item-7
D. DELETE /v1/orders/o-918
          Side effect: hoàn toàn bộ số tiền cho đơn
~~~

Client mobile có mạng không ổn định; gateway có thể timeout sau 10 giây, trong khi database hoặc PSP tiếp tục xử lý. Hai nhân viên đôi khi chỉnh cùng một profile.

### 15.1. Câu hỏi cần trả lời

1. Endpoint **A** vi phạm ngữ nghĩa nào? Vì sao crawler, prefetch hoặc retry GET có thể làm tăng điểm ngoài dự kiến?
2. Endpoint **B** có ý định idempotent không? Nếu hai người sửa profile cùng lúc, PUT một mình đã chống mất cập nhật chưa?
3. Endpoint **C** có thể trả **204 lần đầu, 404 lần sau** mà vẫn idempotent không? Nếu DELETE gửi notification, phải xử lý gì?
4. Endpoint **D** có bảo đảm chỉ hoàn tiền một lần chỉ vì dùng DELETE không? Hãy đề xuất resource/hợp đồng khác.
5. Nếu B trả 204 nhưng response bị mất, client retry với **If-Match phiên bản cũ** và nhận 412, client nên làm gì?
6. Với D, PSP đã hoàn tiền nhưng API timeout. Client được phép gửi lại một refund request với key mới không?
7. Hãy đề xuất ba metric phân biệt **request attempts**, **logical operations** và **successful refunds**.
8. Hãy viết tối thiểu sáu test để chứng minh hiệu ứng của A–D khi có retry hoặc cạnh tranh.

### 15.2. Gợi ý lời giải

**A — không phù hợp GET:** API dùng GET để **cộng điểm**, tức client yêu cầu thay đổi trạng thái. Điều này trái với **safe semantics**; gọi hai lần cũng có hiệu ứng cộng hai lần nên không idempotent. Nên mô hình hóa **POST /v1/loyalty-adjustments** hoặc resource transaction với adjustmentId/idempotency key, xác thực quyền và kiểm soát trùng.

**B — PUT đặt trạng thái:** nếu server xem payload là representation thay thế các field có thể ghi, cùng PUT có hiệu ứng dự kiến như một lần. Nhưng hai client vẫn có thể ghi đè. Trả ETag khi GET; yêu cầu **If-Match** khi PUT; so version nguyên tử trong transaction; khi stale trả **412**.

**C — DELETE resource:** lần đầu 204 và lần sau 404/410 theo contract **không vi phạm idempotency**; item vẫn không có trong cart. Nếu event **ItemRemoved** chỉ nên phát một lần, tạo event khi có transition thực và consumer dedupe. Access log có thể ghi nhiều attempt.

**D — hoàn tiền không tự an toàn:** DELETE resource đơn hàng có thể được lặp, nhưng **refund** là một side effect tài chính độc lập. Nên dùng **POST /v1/refund-requests** tạo một refund operation có ID, trạng thái, số tiền, idempotency key, unique business constraint và query status; client không tạo key mới chỉ vì response mất.

**B retry với If-Match cũ:** 412 có thể xảy ra vì PUT đầu đã thành công hoặc actor khác ghi. Client GET để đối soát trạng thái và ETag, không bỏ điều kiện để “ép” cập nhật. Nếu có workflow phụ phải theo dõi operation ID.

**PSP timeout:** kiểm tra transaction/refund ID qua PSP hoặc hệ thống đối soát; dùng lại key đã thống nhất nếu PSP hỗ trợ retry, không gửi một refund mới với key mới khi chưa biết kết quả cũ.

**Metric gợi ý:** tổng HTTP request attempts theo route/method/status, tổng logical operations theo operation ID và tổng unique refund transactions được PSP xác nhận/đối soát. Tránh dùng các chuỗi dữ liệu cá nhân làm metric label.

### 15.3. Thử thay đổi một giả định

Giả sử endpoint B cập nhật profile và mỗi lần PUT cũng gửi một email “Hồ sơ vừa thay đổi”. Khi client retry sau timeout, profile vẫn giống như ý định ban đầu, nhưng email bị gửi hai lần. Hãy phân tích:

- Đây là lỗi ở **ngữ nghĩa resource**, **side effect nghiệp vụ** hay cả hai?
- Có thể kiểm tra **đã thay đổi thực sự** rồi phát email một lần không?
- Nếu event qua queue có thể phát lại, cần consumer dedupe theo khóa nào?
- Nếu email provider không có API idempotency, nhóm phải chấp nhận mức duplicate nào và dùng quy trình gì để giảm rủi ro?

Trọng tâm không phải thay PUT bằng POST ngay lập tức, mà là **xác định logical operation và những hiệu ứng phải ổn định khi retry**.

## 16. Các nhầm lẫn và anti-pattern thường gặp

### 16.1. “Idempotent nghĩa là response phải giống hệt nhau”

**Sai:** PUT tạo resource có thể trả 201 lần đầu và 204 lần sau; DELETE có thể trả 204 rồi 404. GET có thể trả 200 rồi 404 vì một actor khác đã xóa resource.

**Đúng:** so sánh **hiệu ứng dự kiến** của nhiều lần thực thi cùng request với một lần, không chỉ so sánh status/body.

### 16.2. “GET không được ghi bất cứ byte nào vào server”

**Sai:** server có thể ghi access log, metric và các quan sát phụ trợ khi GET. Nhưng GET không được dùng để yêu cầu chuyển trạng thái nghiệp vụ mà client phải chịu trách nhiệm.

**Đúng:** giữ GET **safe về ý định của client**; các tác dụng phụ không mong muốn như thu tiền, hủy đơn, tăng điểm có giá trị nghiệp vụ không được kích hoạt chỉ do đọc.

### 16.3. “PUT luôn có hiệu ứng exactly once”

**Sai:** có thể có nhiều lần gọi service, retry HTTP, nhiều log, worker message trùng hoặc side effect phát lại. PUT chỉ có ngữ nghĩa **idempotent về hiệu ứng dự kiến**.

**Đúng:** thiết kế outbox, dedupe, transaction, business ID và reconciliation phù hợp khi cần bảo đảm ở ranh giới ngoài HTTP.

### 16.4. “DELETE lần hai trả 404 là sai idempotency”

**Sai:** sau lần xóa đầu, resource không tồn tại; trả 404 ở lần sau vẫn có cùng hiệu ứng cuối.

**Đúng:** tài liệu hóa policy response và hướng dẫn client về cách xác minh resource đã xóa, đặc biệt nếu request trước đó timeout.

### 16.5. “Có If-Match thì retry sẽ luôn thành công”

**Sai:** sau PUT đầu tiên, ETag cũ không còn khớp, nên lần retry có thể trả 412 ngay cả khi lần đầu đã commit.

**Đúng:** If-Match bảo vệ **cập nhật cạnh tranh**, còn retry sau timeout cần **đối soát trạng thái** hoặc operation ID khi kết quả có side effect khác.

### 16.6. “Nếu API dùng PUT, cứ bỏ If-Match để tránh 412”

**Sai:** bỏ precondition có thể ghi đè thay đổi của người khác. Một retry xảy ra sau khi client B đã sửa resource sẽ biến “idempotent về một request” thành **lost update** trong workflow thực tế.

**Đúng:** GET lại và giải quyết xung đột; chỉ đưa ra quyết định cập nhật mới khi có căn cứ nghiệp vụ.

### 16.7. “Gateway timeout nghĩa là server không làm gì”

**Sai:** backend có thể commit trước/sau khi gateway trả 504. Với PSP, tiền có thể đã được xử lý dù client nhận lỗi.

**Đúng:** xem kết quả là **chưa xác định** cho đến khi có bằng chứng từ trạng thái resource, transaction log và hệ thống phụ thuộc.

### 16.8. “Đọc được mã 5xx là đủ để retry”

**Sai:** 500 có thể do bug không phục hồi bằng retry; 503 do quá tải có thể xấu hơn nếu nhiều client retry ngay; 409/412 cần xử lý xung đột.

**Đúng:** kết hợp **method semantics + operation contract + lỗi cụ thể + deadline + retry budget**, có backoff/jitter và tôn trọng Retry-After.

### 16.9. “@PutMapping/@DeleteMapping tự bảo đảm tính đúng”

**Sai:** Spring chỉ ánh xạ request vào handler; code trong handler/service vẫn có thể cộng dồn, gửi email mỗi lần, ghi DB không nguyên tử hoặc không kiểm tra quyền.

**Đúng:** kiểm thử trạng thái và side effect trong điều kiện nhiều request song song, timeout và retry xuyên gateway.

### 16.10. “Một idempotency key trong RAM là đủ”

**Sai:** process restart, scale sang instance khác hoặc cache hết hạn có thể làm mất thông tin về logical operation đã xử lý.

**Đúng:** dùng cơ chế bền vững, khóa duy nhất được enforce, transaction/unique constraint và quy trình đối soát với external system; TTL là phần của hợp đồng.

### 16.11. “PUT chỉ là POST đổi tên”

**Sai:** PUT có ngữ nghĩa liên quan **target resource** và representation được đặt vào trạng thái mới, còn POST yêu cầu target xử lý representation theo semantics riêng. Một lệnh tăng counter hoặc tạo nhiều job không tự thành idempotent chỉ vì dùng PUT.

**Đúng:** chọn method theo ý định và mô hình resource. Nếu action không phải đặt/xóa trạng thái resource, hãy cân nhắc POST với cơ chế chống trùng.

### 16.12. “Client có thể retry body stream bất kỳ”

**Sai:** request body có thể là stream không phát lại được, hoặc một lần retry tạo payload khác do timestamp/nonce thay đổi. Khi đó không còn là cùng request để áp dụng suy luận idempotency.

**Đúng:** bảo đảm representation cần retry có thể tái tạo ổn định, hoặc dùng protocol upload/job phù hợp.

## 17. Checklist thiết kế REST API có retry an toàn

- [ ] Method phản ánh đúng **ý định resource**: GET đọc, PUT đặt/thay thế trạng thái, DELETE loại bỏ target.
- [ ] Đã phân biệt **safe**, **idempotent**, **cacheable** và **exactly-once** trong tài liệu kiến trúc.
- [ ] GET/HEAD không có side effect nghiệp vụ làm thay đổi trạng thái do hành động đọc.
- [ ] PUT định nghĩa rõ representation thay thế trường nào, validation và quyền của client.
- [ ] DELETE xác định target resource, xóa mềm/vật lý, response 200/202/204 và hành vi khi retry.
- [ ] Không giả định DELETE/GET request body có ngữ nghĩa chung để quyết định resource.
- [ ] Đã xác định **hiệu ứng dự kiến** và toàn bộ side effect ngoài DB đối với PUT/DELETE.
- [ ] Nếu client có thể ghi cạnh tranh, có ETag/If-Match hoặc cơ chế đồng thời phù hợp.
- [ ] Kiểm tra version và cập nhật/xóa **nguyên tử** ở tầng lưu trữ, không chỉ ở controller.
- [ ] Client hiểu **412/428** và không tự xóa precondition hay retry liên tục lỗi conflict.
- [ ] Client không suy từ 502/503/504 rằng transaction chắc chắn thất bại.
- [ ] Có cơ chế xác minh outcome sau timeout: GET resource, operation ID, idempotency key và reconciliation.
- [ ] Các lệnh PSP/ERP/refund/email có ID bền vững, dedupe và xử lý duplicate delivery khi cần.
- [ ] Retry có max attempts, timeout, overall deadline, exponential backoff/jitter và retry budget.
- [ ] Chính sách Retry-After và load shedding không làm quá tải tăng thêm.
- [ ] Retry ở SDK/gateway/service được phối hợp để tránh nhân số attempt qua nhiều tầng.
- [ ] Request body cần retry có thể tái gửi mà không đổi semantics hoặc mất dữ liệu.
- [ ] OpenAPI ghi status 201/200/204, 409/412/428, điều kiện và ví dụ retry đúng.
- [ ] Có test GET safe, PUT repeat, DELETE repeat, timeout-after-commit, concurrent write và replay event.
- [ ] Log/trace phân biệt **attempt ID** và **logical operation ID** mà không rò dữ liệu cá nhân.

## 18. Bảng tổng kết: lặp một lần hay nhiều lần?

| Trường hợp | Kết quả khi lặp | Idempotent theo ngữ nghĩa? | Ghi chú quan trọng |
|---|---|---|---|
| GET lấy sản phẩm | Đọc lại dữ liệu hiện tại | **Có** | Response có thể khác nếu resource đổi |
| GET tăng điểm | Cộng điểm nhiều lần | **Không đúng contract GET safe** | Phải đổi method/mô hình hành động |
| PUT đặt theme=dark | Theme vẫn là dark | **Có** nếu contract đặt trạng thái | Cần bảo vệ side effect và cập nhật cạnh tranh |
| PUT incrementBy=1 | Tổng tăng thêm mỗi lần | **Không phù hợp ngữ nghĩa idempotent của PUT** | Cân nhắc POST command resource |
| PUT với If-Match v7 | Lần 1 có thể 204, lần 2 412 | **Vẫn có** về hiệu ứng dự kiến | 412 cần đối soát, không đồng nghĩa lần 1 thất bại |
| DELETE item giỏ hàng | Lần 1 204, lần 2 404 | **Có** | Trạng thái cuối item không còn |
| DELETE gọi refund không chống trùng | Hoàn tiền hai lần | **Không an toàn về nghiệp vụ** | Cần refund resource, operation ID và PSP dedupe |
| POST tạo đơn với key đã bảo đảm | Trả về cùng logical order theo contract | **Có thể idempotent ở cấp ứng dụng** | POST không mặc định idempotent theo HTTP |
| PATCH set theme=dark | Có thể giữ kết quả khi lặp | **Có thể** | Phụ thuộc format/operation, không mặc định |
| PATCH tăng điểm thêm 1 | Tăng nhiều lần | **Không** nếu không có dedupe/điều kiện | Không tự động retry |

Điều phân biệt một API tốt không phải số lượng method được gắn nhãn idempotent, mà là khả năng giải thích **khi request bị lặp, đâu là trạng thái cuối được phép, side effect nào cần chống trùng, và client biết cách nào để xác minh**.

## 19. Tài liệu chuẩn tham khảo

- **RFC 9110 — HTTP Semantics, §9.2.1 và §9.2.2**: định nghĩa safe và idempotent; https://www.rfc-editor.org/rfc/rfc9110.html
- **RFC 9110 — GET, PUT, DELETE**: định nghĩa method, representation và ý nghĩa của target resource; https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3
- **RFC 9110 — Conditional Requests**: If-Match, If-None-Match, ETag và preconditions; https://www.rfc-editor.org/rfc/rfc9110.html#section-13
- **RFC 6585 — Additional HTTP Status Codes**: 428 Precondition Required và 429 Too Many Requests; https://www.rfc-editor.org/rfc/rfc6585.html
- **RFC 9111 — HTTP Caching**: cache và revalidation với GET; https://www.rfc-editor.org/rfc/rfc9111.html
- **RFC 5789 — PATCH Method for HTTP**: ngữ nghĩa PATCH và sự phụ thuộc vào patch document; https://www.rfc-editor.org/rfc/rfc5789.html
- **RFC 9457 — Problem Details for HTTP APIs**: phản hồi lỗi có cấu trúc như 409/412/428; https://www.rfc-editor.org/rfc/rfc9457.html
- **Spring Framework — Spring MVC annotated controllers**: hỗ trợ @GetMapping, @PutMapping, @DeleteMapping và ResponseEntity; https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- **Spring Framework — ETag và conditional requests**: hỗ trợ điều kiện HTTP, cache validation và header response; https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- **OpenAPI Specification**: mô tả operation, requestBody, headers và status; https://spec.openapis.org/oas/latest.html

**Kết luận:** **GET** safe và idempotent vì client chỉ yêu cầu đọc; **PUT** idempotent khi đặt/thay thế trạng thái của target resource; **DELETE** idempotent vì việc yêu cầu loại bỏ lại cùng resource không làm thay đổi hiệu ứng dự kiến so với một lần. Nhưng HTTP **không hứa response giống nhau, không hứa exactly-once và không tự ngăn cập nhật cạnh tranh hoặc side effect trùng**. Thiết kế REST API an toàn khi retry cần kết hợp **ngữ nghĩa method, precondition nguyên tử, operation identity, đối soát, retry budget và kiểm thử dưới sự cố thực tế**.
