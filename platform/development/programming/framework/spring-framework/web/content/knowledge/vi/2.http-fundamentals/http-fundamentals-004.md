# Mã trạng thái HTTP và ý nghĩa các nhóm 2xx, 3xx, 4xx, 5xx

Mỗi phản hồi HTTP có một **mã trạng thái (status code)** gồm ba chữ số. Mã này cho client biết kết quả xử lý request ở tầng HTTP: thành công, cần hành động tiếp, có vấn đề với request, hay có lỗi phía server. Trong Spring Web, chọn mã trạng thái đúng giúp browser, mobile app, API client, proxy và hệ thống giám sát xử lý phản hồi nhất quán.

## 1. Mục tiêu và cách đọc mã trạng thái

Sau bài học, bạn cần:
- Nhận diện ý nghĩa tổng quát của các nhóm **2xx**, **3xx**, **4xx**, **5xx** và biết nhóm **1xx** là thông tin trung gian.
- Phân biệt những mã thường dùng như `200`, `201`, `202`, `204`, `301`, `302`, `303`, `304`, `307`, `308`, `400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `429`, `500`, `502`, `503` và `504`.
- Chọn status code dựa trên **ý nghĩa của tình huống**, phương thức HTTP, trạng thái tài nguyên và hợp đồng API.
- Trả mã trạng thái bằng `ResponseEntity`, `@ResponseStatus` hoặc xử lý ngoại lệ trong Spring MVC.
- Chẩn đoán lỗi bằng cách đọc **status + headers + body** thay vì chỉ nhìn một chữ số.

Một status code có dạng `xyz`, trong đó chữ số đầu xác định nhóm:

| Nhóm | Tên theo HTTP | Ý nghĩa tổng quát |
| --- | --- | --- |
| 1xx | Informational | Phản hồi trung gian trong lúc trao đổi; chỉ nhắc để có bức tranh đầy đủ. |
| **2xx** | Successful | Request đã được nhận, hiểu và xử lý thành công theo ngữ nghĩa của method/status. |
| **3xx** | Redirection | Client cần thêm bước xử lý, lựa chọn biểu diễn hoặc dùng dữ liệu cache/địa chỉ khác. |
| **4xx** | Client Error | Server cho biết request không thể được đáp ứng trong điều kiện hiện tại; thường liên quan dữ liệu, xác thực, quyền, tài nguyên hay giới hạn phía client. |
| **5xx** | Server Error | Server/gateway không thể hoàn thành một request về nguyên tắc hợp lệ do lỗi hoặc tình trạng phía hạ tầng. |

**Quan trọng:** Status code là **ngữ nghĩa HTTP**, không phải ngoại lệ Java, số dòng lỗi hay một trường tùy ý trong JSON. Ví dụ `HTTP/1.1 404 Not Found` là phản hồi HTTP; chuỗi `"status":404` trong JSON chỉ là dữ liệu ứng dụng nếu server tự định nghĩa. Trong HTTP/2 và HTTP/3, status nằm ở pseudo-header `:status`, không có status-line văn bản kiểu HTTP/1.1.

### Status code, reason phrase, headers và body

Ví dụ phản hồi HTTP/1.1:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

Trong ví dụ:
- `201` là status code để chương trình xử lý.
- `Created` là reason phrase tùy chọn ở HTTP/1.1 để con người đọc; không nên so chuỗi này khi lập trình.
- `Location` cung cấp URI của tài nguyên vừa tạo.
- `Content-Type` cho biết kiểu biểu diễn response body.
- JSON là body ứng dụng; **không phải mã trạng thái thứ hai**.

Status code không cho biết toàn bộ chi tiết lỗi. Cùng một `409 Conflict` có thể có nhiều nguyên nhân nghiệp vụ; client cần đọc body lỗi theo schema API, kèm header liên quan.

## 2. Nhóm 2xx — yêu cầu được xử lý thành công

Nhóm 2xx biểu đạt thành công nhưng **không đồng nghĩa lúc nào cũng đã hoàn tất một công việc nền hoặc có body**.

| Mã | Tên | Khi nào dùng |
| --- | --- | --- |
| **200 OK** | OK | Xử lý thành công; ví dụ GET trả representation, POST trả kết quả xử lý đã hoàn thành. |
| **201 Created** | Created | Request đã hoàn tất và dẫn đến tạo một hay nhiều tài nguyên; thường trả `Location` tới tài nguyên chính mới tạo. |
| **202 Accepted** | Accepted | Request được nhận để xử lý nhưng việc xử lý **chưa hoàn thành**; có thể thành công hoặc thất bại về sau. |
| **204 No Content** | No Content | Xử lý thành công và server không gửi message content; hữu ích sau DELETE hoặc cập nhật không cần body. |
| **206 Partial Content** | Partial Content | Server đáp ứng thành công request lấy một phần representation, thường liên quan `Range`/`Content-Range`. |

### 2.1. 200 OK: thành công và nội dung tùy method

Ví dụ:

~~~http
GET /api/books/42 HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

Khi GET tài nguyên thành công, 200 thường mang representation của tài nguyên. Với POST, 200 cũng có thể hợp lệ nếu server trả kết quả xử lý mà không có ý nghĩa tạo tài nguyên mới. Với HEAD, 200 không đi kèm response content dù có thể có header mô tả representation tương ứng. Vì vậy, không suy luận “200 luôn chứa JSON”.

### 2.2. 201 Created và Location

Nếu POST thực sự **tạo tài nguyên đã tồn tại sau request**, 201 là một lựa chọn phù hợp:

~~~http
HTTP/1.1 201 Created
Location: /api/books/42
Content-Type: application/json

{"id":42,"title":"HTTP"}
~~~

`Location` cho client biết URI của tài nguyên chính vừa tạo. Đây có thể là URI tương đối, được giải quyết theo URI của request. Body là tùy chọn theo hợp đồng API; nó có thể mô tả tài nguyên mới. Đừng trả 201 chỉ vì method là POST: nếu POST thực hiện tìm kiếm hoặc chạy một hành động không tạo tài nguyên, hãy chọn status phản ánh kết quả thật.

### 2.3. 202 Accepted: bất đồng bộ chưa xong

Ví dụ API nhận yêu cầu xuất báo cáo vào hàng đợi:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/report-jobs/abc

{"jobId":"abc","state":"queued"}
~~~

Client có thể gọi URL theo hợp đồng API để hỏi tiến độ. `202` **không cam kết** job sẽ thành công; phản hồi cuối của job phải được truyền đạt qua cơ chế được thiết kế riêng (truy vấn trạng thái, callback, sự kiện...). Đừng dùng 200 với nội dung “đã hoàn thành” khi thực tế hệ thống mới ghi nhận yêu cầu.

### 2.4. 204 No Content: không có body

~~~http
HTTP/1.1 204 No Content

~~~

204 biểu thị xử lý thành công nhưng **không có message content**, nên client không gọi parser JSON trên một body rỗng. Không tự gắn JSON `{}` vào response 204. Một số framework/container loại bỏ body nếu bạn cố gửi; API phải chủ động thiết kế đúng.

### 2.5. 206 Partial Content

Nếu client gửi `Range: bytes=0-99` và server hỗ trợ range request, response có thể trả 206 với `Content-Range` chỉ rõ đoạn dữ liệu thực gửi. 206 **không có nghĩa “thành công một phần về nghiệp vụ”**. Nếu xử lý ba thao tác mà chỉ hai thành công, không tự dùng 206 làm mã chung cho “partial business success”; hãy định nghĩa hợp đồng API thích hợp.

## 3. Nhóm 3xx — điều hướng, lựa chọn hoặc tái sử dụng cache

Các mã 3xx thường bị gọi chung là redirect, nhưng **304 Not Modified không phải lệnh chuyển tới URL mới**.

| Mã | Ý nghĩa chủ yếu | Method sau khi client làm theo `Location` |
| --- | --- | --- |
| **301 Moved Permanently** | Tài nguyên có URI mới lâu dài | Client hiện đại có thể đổi POST thành GET theo lịch sử tương thích; không dựa vào 301 khi bắt buộc giữ method. |
| **302 Found** | Tạm thời có URI khác | Tương tự 301, client có thể đổi POST thành GET theo lịch sử tương thích. |
| **303 See Other** | Xem kết quả ở URI khác, thường sau POST | Với chuyển hướng thông thường, dùng GET hoặc HEAD để truy xuất tài nguyên đích. |
| **304 Not Modified** | Representation đã cache vẫn hợp lệ sau yêu cầu có điều kiện | Không tải response body mới; tái sử dụng bản cache theo quy tắc cache. |
| **307 Temporary Redirect** | Chuyển hướng tạm thời | **Không đổi method** khi tự động chuyển hướng. |
| **308 Permanent Redirect** | Chuyển hướng lâu dài | **Không đổi method** khi tự động chuyển hướng. |

### 3.1. Redirect và Location

Ví dụ di chuyển endpoint trong thời gian chuyển tiếp:

~~~http
HTTP/1.1 308 Permanent Redirect
Location: /api/v2/books/42

~~~

Client có thể gửi lại request tới URI mới, vẫn giữ method và ngữ nghĩa body theo quy tắc của 308. Với POST có side effect, hãy lưu ý chuyện **gửi lại request có thể thực thi lần nữa**; redirect không thay thế cơ chế idempotency trong thiết kế API.

Ví dụ **Post/Redirect/Get** khi ứng dụng có form trình duyệt: POST lưu dữ liệu thành công, server trả 303 cùng `Location: /orders/42`, browser sau đó GET trang kết quả. Cách này giúp tránh chuyện browser refresh trực tiếp gửi lại POST ở trang kết quả.

Không dùng 301/308 một cách tùy tiện cho URL tạm thời vì client/cache có thể ghi nhớ chuyển hướng lâu dài.

### 3.2. 304 Not Modified và cache có điều kiện

Một ví dụ chuẩn với ETag:

~~~http
GET /api/books/42 HTTP/1.1
Host: api.example.test
If-None-Match: "book-v7"

~~~

Nếu server xác định representation hiện tại khớp ETag:

~~~http
HTTP/1.1 304 Not Modified
ETag: "book-v7"

~~~

Client/cache sử dụng representation đã lưu phù hợp thay vì nhận body mới. **304 không chứa message content**, và cũng không nói “tài nguyên chưa từng thay đổi”. Nó chỉ phản ánh kết quả đánh giá điều kiện của request tại thời điểm đó. Nếu cache không có representation tương ứng, 304 riêng lẻ không đủ để dựng dữ liệu.

### 3.3. Redirect API: ba câu hỏi trước khi chọn mã

1. URI mới có **lâu dài** hay chỉ tạm thời? Lâu dài cân nhắc 301/308; tạm thời cân nhắc 302/307.
2. Có cần **giữ nguyên method/body** khi client đi tiếp không? Nếu có, 307/308 diễn đạt rõ hơn.
3. Muốn client **GET một trang/kết quả sau POST**? 303 thường thể hiện chủ đích rõ nhất.

Đừng lẫn chuyển hướng HTTP 3xx với việc Spring MVC trả tên view hay internal forward. Browser chỉ thực hiện request mới khi nhận redirect thật với status và Location thích hợp.

## 4. Nhóm 4xx — request không được đáp ứng

4xx thường hướng client tới việc **thay đổi request, cung cấp quyền phù hợp hoặc chờ điều kiện cho phép**. Từ “Client Error” không có nghĩa mọi lỗi 4xx chắc chắn do lập trình viên frontend gây ra: quy tắc bảo mật, tồn tại tài nguyên và hợp đồng API đều ảnh hưởng.

| Mã | Tên | Tình huống điển hình |
| --- | --- | --- |
| **400 Bad Request** | Bad Request | Request sai cú pháp hoặc không hợp lệ theo cách server không thể/không muốn xử lý. |
| **401 Unauthorized** | Unauthorized | Thiếu hoặc không hợp lệ thông tin xác thực đối với tài nguyên được bảo vệ; phản hồi 401 phù hợp phải có `WWW-Authenticate`. |
| **403 Forbidden** | Forbidden | Server hiểu request nhưng từ chối thực hiện, thường do không đủ quyền. |
| **404 Not Found** | Not Found | Không tìm thấy representation/tài nguyên đích theo cách server sẵn sàng tiết lộ; cũng có thể cố ý che giấu tài nguyên bị cấm. |
| **405 Method Not Allowed** | Method Not Allowed | URI có handler/tài nguyên nhưng method không được hỗ trợ tại đích; response phải có `Allow` liệt kê method hiện được hỗ trợ. |
| **406 Not Acceptable** | Not Acceptable | Server không tìm được representation phù hợp với điều kiện thương lượng nội dung client gửi và từ chối trả loại khác. |
| **408 Request Timeout** | Request Timeout | Server không nhận được request đầy đủ trong thời gian sẵn sàng chờ. |
| **409 Conflict** | Conflict | Request xung đột với trạng thái hiện tại của tài nguyên/hệ thống. |
| **410 Gone** | Gone | Tài nguyên đã không còn và tình trạng mất được biết là có khả năng lâu dài. |
| **412 Precondition Failed** | Precondition Failed | Điều kiện như `If-Match` không thỏa; hay dùng để tránh ghi đè bản cập nhật đồng thời. |
| **413 Content Too Large** | Content Too Large | Nội dung request quá lớn so với mức server chấp nhận. |
| **415 Unsupported Media Type** | Unsupported Media Type | Media type/encoding của request content không được endpoint hỗ trợ. |
| **422 Unprocessable Content** | Unprocessable Content | Content có loại và cú pháp hiểu được nhưng không thể xử lý theo chỉ dẫn/ngữ nghĩa nội dung. |
| **429 Too Many Requests** | Too Many Requests | Client đã gửi quá nhiều request trong khoảng thời gian theo chính sách giới hạn. |

### 4.1. Phân biệt 400, 415 và 422

Một `POST /api/books` nhận JSON:
- Body JSON **sai cú pháp** như `{"title":`: thường trả **400**, vì không deserialize được.
- Client gửi `Content-Type: application/xml` nhưng endpoint chỉ chấp nhận JSON: thường trả **415**.
- JSON hợp lệ và có cấu trúc server hiểu, nhưng vi phạm một quy tắc ngữ nghĩa (ví dụ một giá trị không thể xử lý): **422** có thể phù hợp tùy hợp đồng API. Nhiều API dùng **400** cho validation và vẫn hoàn toàn hợp lý khi quy định nhất quán. Spring MVC không tự động dùng 422 cho mọi lỗi validation.

### 4.2. Phân biệt 401 và 403

- **401:** client chưa cung cấp hoặc cung cấp chứng thực không hợp lệ. Với cơ chế Bearer token, server bảo vệ endpoint có thể trả `WWW-Authenticate: Bearer`, kèm tham số khi thích hợp. HTTP gọi mã này “Unauthorized” nhưng thực tế liên quan **authentication**.
- **403:** server biết request nhưng từ chối thực hiện, ví dụ tài khoản đã xác thực nhưng thiếu quyền quản trị. Việc thêm token cũng không nhất thiết khắc phục.
- **404:** hệ thống bảo mật có thể chủ động dùng 404 thay 403 để tránh tiết lộ tài nguyên được bảo vệ có tồn tại hay không.

Không suy luận chính sách xác thực chỉ từ mã trạng thái của một endpoint chưa biết.

### 4.3. Phân biệt 404, 405 và 410

- `GET /api/books/999` khi không có sách 999: thường là **404**.
- `POST /api/books/42` khi endpoint này chỉ cho GET: thường là **405** (nếu cấu hình routing có route tương ứng và framework nhận diện khác biệt method).
- Tài liệu đã bị xóa vĩnh viễn và server biết điều đó: **410** có thể diễn đạt rõ hơn; không bắt buộc mọi tài nguyên bị xóa phải trả 410.

Một số API dùng 404 cả khi method/path không có route; hãy đối chiếu cấu hình router và `Allow` thay vì đoán.

### 4.4. Phân biệt 409 và 412 khi cập nhật đồng thời

**409 Conflict:** ví dụ người dùng cố tạo tài khoản với username đã tồn tại, hoặc chuyển trạng thái đơn hàng trái với trạng thái hiện tại.

**412 Precondition Failed:** ví dụ client lấy tài nguyên kèm ETag rồi gửi:

~~~http
PUT /api/books/42 HTTP/1.1
Host: api.example.test
If-Match: "book-v7"
Content-Type: application/json

{"title":"Revised"}
~~~

Nếu representation hiện tại có ETag khác, server có thể trả 412, ngăn cập nhật đè lên thay đổi của người khác. 409 diễn tả xung đột tổng quát; 412 nhấn vào **HTTP precondition** đã thất bại.

### 4.5. 429 và Retry-After

429 phù hợp khi client vượt chính sách rate limit; response **có thể** có `Retry-After` hướng dẫn thời điểm thử lại:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

`Retry-After: 60` có nghĩa đợi khoảng 60 giây trước khi retry, theo hướng dẫn của server; không cam kết lần sau chắc chắn thành công. Client cần backoff, giới hạn tốc độ và cân nhắc idempotency trước khi gửi lại request có side effect.

## 5. Nhóm 5xx — server hoặc hạ tầng không hoàn thành request

Các mã 5xx thường báo vấn đề ở phía xử lý request, server hoặc thành phần trung gian. Phía client có thể retry một số trường hợp, nhưng retry mù quáng dễ tạo tác dụng phụ hoặc làm server đang lỗi quá tải hơn.

| Mã | Tên | Ý nghĩa |
| --- | --- | --- |
| **500 Internal Server Error** | Internal Server Error | Server gặp điều kiện bất ngờ và không hoàn thành request; đây là mã tổng quát khi không có status cụ thể thích hợp hơn. |
| **501 Not Implemented** | Not Implemented | Server không hỗ trợ chức năng cần để thực hiện request, ví dụ không nhận biết hoặc không hỗ trợ method ở cấp server. |
| **502 Bad Gateway** | Bad Gateway | Gateway/proxy nhận phản hồi không hợp lệ từ upstream mà nó cần để hoàn thành request. |
| **503 Service Unavailable** | Service Unavailable | Dịch vụ tạm không sẵn sàng, ví dụ quá tải hoặc bảo trì; có thể dùng `Retry-After`. |
| **504 Gateway Timeout** | Gateway Timeout | Gateway/proxy không nhận phản hồi kịp thời từ upstream. |

### 5.1. Phân biệt 500, 502, 503 và 504

Giả sử luồng:

~~~text
Mobile App → API Gateway → Spring Web → Database / Service khác
~~~

- **500:** một lỗi không được xử lý thích hợp trong service Spring có thể trở thành 500. Ví dụ NullPointerException bất ngờ hoặc mã xử lý lỗi bị hỏng; thực tế do bộ xử lý ngoại lệ quyết định.
- **502:** gateway nhận upstream response sai hoặc không hợp lệ và trả Bad Gateway.
- **503:** backend tạm ngừng phục vụ do bảo trì/quá tải, hoặc gateway không có backend khả dụng và sử dụng 503 theo cấu hình.
- **504:** gateway chờ upstream vượt thời gian cho phép.

**Không tự động gọi mọi timeout là 504.** Nếu client kết nối bị ngắt mà không nhận được HTTP response, client thấy lỗi mạng/timeout chứ không có status code. Nếu chính Spring ứng dụng trả lời timeout theo hợp đồng khác, mã còn phụ thuộc cách triển khai.

**501 không phải 405:** nếu method được server hiểu nhưng tài nguyên đích không hỗ trợ method đó, 405 thích hợp hơn; nếu server không hỗ trợ chức năng/method ở mức rộng hơn, 501 có thể thích hợp.

### 5.2. Retry thông minh

Khi 5xx:
1. Ghi nhận status, request ID/tracing ID (nếu có), khoảng thời gian và endpoint.
2. Nếu có `Retry-After`, tôn trọng tín hiệu đó khi phù hợp.
3. Dùng exponential backoff kèm jitter, giới hạn số lần thử và timeout rõ ràng.
4. Chỉ tự động retry những request mà việc gửi trùng **an toàn theo hợp đồng**. GET thường phù hợp; POST tạo giao dịch cần idempotency key hoặc cơ chế chống xử lý trùng trước khi retry.
5. Trên backend, không trả stack trace, access token, SQL chi tiết hay bí mật nội bộ cho client; dùng log/tracing nội bộ để điều tra.

**Status 5xx không chứng minh tác vụ nghiệp vụ chưa xảy ra.** Server có thể đã ghi dữ liệu thành công rồi lỗi khi tạo response; client retry POST mà không kiểm soát trùng có thể tạo hai bản ghi.

## 6. Chọn status cho một API: từ ngữ nghĩa đến quyết định

Bảng dưới đây là các **mẫu thường gặp**, không phải quy tắc bắt buộc theo method. Điều kiện quan trọng nhất vẫn là kết quả thực của request.

| Tình huống API | Mã nên cân nhắc | Lý do |
| --- | --- | --- |
| GET có representation của tài nguyên | 200 | Trả dữ liệu thành công. |
| POST tạo mới và tài nguyên đã được tạo | 201 | Thành công và tạo tài nguyên; gửi Location khi phù hợp. |
| POST nhận job và sẽ xử lý sau | 202 | Mới tiếp nhận, chưa kết luận kết quả cuối. |
| DELETE thành công, không trả body | 204 | Không có nội dung phản hồi. |
| GET có điều kiện, ETag còn phù hợp | 304 | Dùng lại cache; không gửi representation body. |
| GET id không tồn tại | 404 | Không tìm thấy tài nguyên. |
| Request JSON sai cú pháp | 400 | Dữ liệu request không parse được. |
| Request thiếu xác thực cho tài nguyên bảo vệ | 401 | Yêu cầu xác thực với challenge thích hợp. |
| Người dùng thiếu quyền | 403 | Từ chối hành động. |
| POST tạo dữ liệu trùng khóa nghiệp vụ | 409 | Xung đột trạng thái hiện có. |
| If-Match không đúng với bản hiện tại | 412 | HTTP precondition thất bại. |
| Endpoint quá tải tạm thời | 503 | Service chưa sẵn sàng. |

Các phân biệt hữu ích khi thiết kế:
- **200 hay 201?** Chọn 201 nếu request tạo ra tài nguyên và hoàn tất; POST không phải lúc nào cũng dẫn tới 201.
- **200 hay 204?** Chọn dựa trên việc có representation trong body hay không, không dựa vào cảm tính “body ít thông tin”.
- **201 hay 202?** Tài nguyên đã được tạo và xử lý hoàn tất khác với job mới được xếp hàng chờ.
- **400 hay 422?** Cần hợp đồng API rõ ràng cho phân loại lỗi cú pháp và lỗi ngữ nghĩa.
- **409 hay 500?** Xung đột nghiệp vụ dự kiến là 409; lỗi nội bộ bất ngờ có thể là 500.
- **404 hay 204 khi DELETE lần hai?** Cả hai có thể xuất hiện trong các API khác nhau; DELETE idempotent nói về **tác động dự kiến trên tài nguyên**, không bắt buộc mọi lần trả cùng status.

## 7. Trả status trong Spring MVC: ví dụ chạy được

Ví dụ dùng **Java 17+ và Spring Boot 3 với dependency `spring-boot-starter-web`** (bao gồm Spring MVC và JSON serialization thông dụng). Đây là ứng dụng tối giản có thể chạy trong dự án Spring Boot đã cấu hình build; không phải tệp Java độc lập chỉ cần `javac` mà không có thư viện Spring. Đặt toàn bộ mã vào tệp `src/main/java/demo/http/HttpStatusDemoApplication.java`:

~~~java
package demo.http;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class HttpStatusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpStatusDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping("/{id}")
    public ResponseEntity<Book> find(@PathVariable long id) {
        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build(); // 404
        }
        return ResponseEntity.ok(book); // 200 + JSON
    }

    @PostMapping
    public ResponseEntity<Book> create(@RequestBody CreateBook request) {
        if (request.title() == null || request.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "title must not be blank"); // 400
        }

        long id = nextId.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location).body(book); // 201 + Location
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build(); // 404
        }
        return ResponseEntity.noContent().build(); // 204
    }

    record CreateBook(String title) {}
    record Book(long id, String title) {}
}
~~~

**Cách chạy:** với dự án Spring Boot Gradle đã thêm `implementation 'org.springframework.boot:spring-boot-starter-web'`, chạy ứng dụng bằng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. App mặc định thường phục vụ ở `http://localhost:8080` nếu không đổi cấu hình cổng. Ứng dụng mẫu lưu dữ liệu **trong bộ nhớ**, khởi động lại sẽ mất dữ liệu; id tăng từ 1 trong một phiên khởi động mới và phụ thuộc thứ tự request thực tế.

Thử lần lượt bằng `curl` trong terminal có cú pháp shell POSIX (hoặc điều chỉnh quote cho PowerShell):

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -d '{"title":"HTTP Essentials"}'

curl -i http://localhost:8080/api/books/1

curl -i -X DELETE http://localhost:8080/api/books/1

curl -i http://localhost:8080/api/books/1

curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'
~~~

Với ứng dụng **mới khởi động**, không có request khác và lần POST đầu tiên thành công, kết quả được mong đợi:

| Request | Status | Ý nghĩa/body kỳ vọng |
| --- | --- | --- |
| POST tạo sách có title hợp lệ | **201 Created** | `Location: /api/books/1` và JSON `{"id":1,"title":"HTTP Essentials"}`. |
| GET `/api/books/1` | **200 OK** | JSON mô tả sách vừa tạo. |
| DELETE `/api/books/1` | **204 No Content** | Không có response body. |
| GET sách vừa xóa | **404 Not Found** | Body rỗng do cách dựng `ResponseEntity.notFound().build()` trong ví dụ. |
| POST với title rỗng | **400 Bad Request** | Lỗi `ResponseStatusException`; định dạng body lỗi tùy cấu hình Spring Boot. |

Framework/container có thể thêm các header khác, và serialization có thể chịu ảnh hưởng cấu hình. Đây là ví dụ phục vụ **HTTP status semantics**: dùng `ResponseEntity` để chủ động trả status và body. Đừng xây giả định rằng mọi response đều có cùng `Content-Length`, thời gian hay tập header giữa môi trường khác nhau.

### 7.1. Ba cách Spring MVC đặt status

**Cách 1 — `ResponseEntity`:** khi controller cần điều khiển đồng thời status, headers và body:

~~~java
return ResponseEntity.created(URI.create("/api/books/" + id))
                     .body(book);
~~~

**Cách 2 — `@ResponseStatus`:** khi handler có status tương đối cố định:

~~~java
@PostMapping("/ping")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void ping() {
    // Endpoint minh họa: thành công, không có body.
}
~~~

Đoạn này là ví dụ **phương thức controller riêng lẻ**, chỉ hoạt động khi đặt trong một controller Spring MVC có import thích hợp (`@PostMapping`, `@ResponseStatus`, `HttpStatus`); không phải một chương trình Java chạy độc lập. `@ResponseStatus` cũng dùng được trên một số loại exception tùy thiết kế.

**Cách 3 — exception và xử lý tập trung:** ném `ResponseStatusException` để gắn mã tương ứng, hoặc dùng `@RestControllerAdvice` kết hợp `@ExceptionHandler` để biến exception miền nghiệp vụ thành response chuẩn. Chẳng hạn một lỗi `BookConflictException` trong logic nghiệp vụ có thể được map thành 409. Chỉ map những lỗi **có ý nghĩa được định nghĩa**; tránh biến mọi exception thành 200 hoặc 400.

Ở Spring MVC, các resolver và cấu hình exception handling quyết định status thực tế. Spring Security, filter, proxy/gateway và cấu hình error response cũng có thể ảnh hưởng phản hồi. Do đó log trạng thái HTTP thực tế ngoài ranh giới ứng dụng khi cần điều tra.

### 7.2. Body lỗi chuẩn hóa: Problem Details

Trong hệ sinh thái HTTP, định dạng **Problem Details** (RFC 9457, cập nhật RFC 7807) thường dùng media type `application/problem+json` và những trường chuẩn như `type`, `title`, `status`, `detail`, `instance`.

Ví dụ 409 theo hợp đồng minh họa:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/book-conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Book identifier already exists",
  "instance": "/api/books/42"
}
~~~

**Phản hồi trên là ví dụ do API lựa chọn**, không phải body mặc định bảo đảm từ Spring. Spring Framework 6 có `ProblemDetail` và hỗ trợ xử lý các lỗi theo hướng này; mức tự động xuất body và các trường phụ thuộc cấu hình Spring MVC/Spring Boot cũng như exception resolver. Status ở HTTP response mới là status ở tầng giao thức; trường `status` trong body nhằm cung cấp dữ liệu mô tả lỗi đồng bộ với response.

Giữ message lỗi đủ hữu ích cho client nhưng không tiết lộ stack trace, mật khẩu, query SQL hay token. Với lỗi validation, trả chi tiết lỗi theo schema ổn định để người dùng sửa đúng trường.

## 8. Debug theo mã trạng thái và đường đi request

Khi chẩn đoán API, nên quan sát:

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

- `-i` hiển thị response headers kèm body, trong đó có status-line khi dùng HTTP/1.x.
- `-v` cho biết thêm thông tin kết nối và request do curl tạo.
- DevTools Network, HTTP client hoặc tracing có thể cho biết redirect chain, request/response headers, payload và thời gian thực hiện.

Một trình tự kiểm tra có ích:

1. **Có status code không?** Nếu không, điều tra DNS, TCP/QUIC, TLS, timeout kết nối, proxy và lỗi gửi/nhận; đừng tự gán 500.
2. **2xx nhưng UI vẫn lỗi?** Kiểm tra body có đúng schema, nội dung có thực sự hợp lệ, 204 có bị parse JSON nhầm, 202 có bị coi là “job đã xong” hay không.
3. **3xx?** Đọc `Location` và `Cache-Control`/ETag khi liên quan; phân biệt redirect chain với 304 cache. Kiểm tra method sau chuyển hướng, tránh chuyển POST thành GET ngoài ý muốn.
4. **4xx?** Đọc method, path, query, `Content-Type`, `Accept`, auth, permission, body, ETag/precondition và chính sách rate limit. 400/401/403/404/409 cần hướng xử lý khác nhau.
5. **5xx?** Tra log/tracing server và gateway/upstream. So sánh 500/502/503/504 để xác định nơi xảy ra sự cố; thiết kế retry có giới hạn, idempotency phù hợp.

Đối với Spring Web, một lỗi do routing/argument conversion xảy ra **trước khi vào business method**, nên breakpoint chỉ trong controller có thể không bắt được. Hãy xem exception handler, filter, security chain, servlet container và proxy khi status bất ngờ.

## 9. Các nhầm lẫn phổ biến

| Quan niệm sai | Cách hiểu đúng |
| --- | --- |
| “2xx nào cũng có response JSON.” | 204 không có content; 202 mới nhận việc; 206 là một phần representation. |
| “POST lúc nào cũng trả 201.” | 201 khi tạo tài nguyên hoàn tất; POST có thể trả 200, 202, 204 hoặc mã lỗi theo ngữ nghĩa. |
| “3xx đều chuyển sang URL khác.” | 304 thông báo dùng lại cache, không phải redirect tới URI khác. |
| “301, 302, 307, 308 chỉ khác số.” | Tính lâu dài và quy tắc giữ/đổi method là khác biệt đáng kể. |
| “401 là đã đăng nhập nhưng thiếu quyền.” | 401 liên quan authentication/challenge; 403 thường là từ chối quyền. |
| “404 chắc chắn tài nguyên không tồn tại.” | Server có thể dùng 404 để không tiết lộ sự tồn tại của tài nguyên bị cấm. |
| “400 và 422 hoàn toàn hoán đổi cho nhau.” | Chúng mang ngữ nghĩa khác; dùng nhất quán với hợp đồng API. |
| “409 là lỗi hệ thống như 500.” | 409 thường biểu đạt xung đột trạng thái mà client có thể xử lý. |
| “5xx nghĩa là thao tác chắc chắn chưa được thực hiện.” | Server có thể đã lưu thay đổi rồi lỗi khi phản hồi; retry cần kiểm soát trùng. |
| “Có timeout thì server đã trả 504.” | Timeout không nhận response HTTP không có status; 504 là phản hồi cụ thể của gateway. |
| “Spring luôn tự trả đúng body lỗi theo tôi nghĩ.” | Status/body phụ thuộc exception resolver, Boot configuration, Security và proxy. |

## 10. Bài tập tự kiểm tra và giải thích

**Bài 1.** API `POST /payments` nhận yêu cầu, gửi xử lý vào hàng đợi nhưng chưa biết kết quả thanh toán. Nên trả 201 hay 202?

**Bài 2.** Client GET một tài liệu với `If-None-Match` và server thấy ETag không thay đổi. Status phù hợp là gì? Có body JSON tài liệu mới không?

**Bài 3.** Client có token hợp lệ nhưng thiếu quyền xóa sách. Nên trả 401 hay 403? Nếu token không hợp lệ thì sao?

**Bài 4.** Gateway không nhận phản hồi upstream kịp thời. Phân biệt 500, 502, 503, 504: mã nào mô tả đúng nhất?

**Bài 5.** Client POST JSON có cú pháp hợp lệ nhưng trùng khóa unique, API muốn client xử lý xung đột. Nên trả 409 hay 500?

**Bài 6.** DELETE một bản ghi thành công và server không cần trả representation. Status hợp lý là gì? Nếu DELETE cùng URI lần nữa trả 404 thì có phá vỡ idempotency của DELETE không?

### Đáp án

1. **202 Accepted**: xử lý chưa kết thúc; phải có cơ chế theo dõi kết quả cuối ngoài status này.
2. **304 Not Modified** khi đáp ứng điều kiện cache phù hợp; không gửi body representation mới.
3. **403 Forbidden** khi có xác thực hợp lệ nhưng thiếu quyền; **401 Unauthorized** cùng challenge thích hợp khi thiếu/sai xác thực. Chính sách bảo mật có thể cố ý dùng 404 để che giấu sự tồn tại.
4. **504 Gateway Timeout**; 500 là lỗi server chung, 502 là upstream phản hồi không hợp lệ, 503 là dịch vụ tạm không sẵn sàng.
5. **409 Conflict** diễn đạt xung đột trạng thái dự kiến; tránh báo 500 cho lỗi nghiệp vụ đã biết.
6. **204 No Content** phù hợp. Lần sau có thể trả 404: tính idempotent mô tả tác động dự kiến của việc gọi lặp, không bắt buộc status hai lần phải giống hệt.

## 11. Tổng kết kiến thức cốt lõi

Khi thiết kế API Spring Web, hãy đi từ **kết quả thật của request** đến status: **2xx** thể hiện thành công (bao gồm đã tạo, mới chấp nhận, không có body), **3xx** thể hiện điều hướng/cache, **4xx** thể hiện request không thể đáp ứng theo điều kiện hiện tại, và **5xx** biểu thị lỗi server hoặc trung gian. Sau đó chọn header và body khớp ngữ nghĩa của status, đặc biệt `Location` với 201/3xx, `WWW-Authenticate` với 401, `Allow` với 405 và `Retry-After` với 429/503 khi áp dụng. Trong Spring MVC, dùng `ResponseEntity`, status annotation và xử lý ngoại lệ để phản hồi nhất quán; luôn xác minh status/headers/body thực tế từ HTTP client.

**Tài liệu đối chiếu:** RFC 9110 (HTTP Semantics), RFC 9111 (HTTP Caching), RFC 9112 (HTTP/1.1), RFC 9457 (Problem Details) và tài liệu Spring Framework Web MVC về `ResponseEntity`, `@ResponseStatus`, `ProblemDetail`.