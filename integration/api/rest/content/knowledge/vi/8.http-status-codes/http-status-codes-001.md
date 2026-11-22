# Nhóm 1xx, 2xx, 3xx, 4xx, 5xx và trách nhiệm diễn giải

## 1. Vì sao mã trạng thái HTTP là một phần của hợp đồng REST API?

Một REST API không chỉ trả về JSON. Mỗi phản hồi HTTP có **mã trạng thái** (*status code*) cho biết kết quả xử lý ở cấp giao thức. Client, trình duyệt, proxy, gateway, bộ nhớ đệm, công cụ giám sát và các thư viện HTTP thường dựa vào mã này để quyết định tiếp tục, hiển thị thông tin, chuyển hướng, dùng dữ liệu đã lưu hay thử lại yêu cầu.

Trong module **INTEGRATION_API_REST**, người học thiết kế API dựa trên resource, URI, phương thức HTTP và hợp đồng dữ liệu. Hiểu đúng mã trạng thái là nền tảng cho phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương.

Xét một API đơn hàng:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Authorization: Bearer <access-token>

{"customerId":"c-17","items":[{"sku":"p-2","quantity":2}]}
~~~

Khi đơn hàng được tạo ngay, phản hồi hợp lý có thể là:

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-123
Content-Type: application/json

{"id":"ord-123","status":"PENDING"}
~~~

Mã **201** cho client biết một tài nguyên mới đã được tạo; **Location** cho biết nơi truy cập tài nguyên đó. Nếu server luôn trả **200 OK** cho cả lỗi xác thực, dữ liệu sai và sự cố nội bộ, client và hạ tầng sẽ khó phân biệt các tình huống, retry sai, ghi log sai và giám sát sai.

Mục tiêu của bài học:

- Phân loại được năm nhóm **1xx, 2xx, 3xx, 4xx, 5xx** theo ý nghĩa giao thức.
- Chọn đúng mã trạng thái theo phương thức, resource và kết quả xử lý.
- Phân biệt trách nhiệm giữa **server, client và trung gian HTTP** khi phát sinh hoặc diễn giải một mã.
- Thiết kế payload lỗi nhất quán, cache và retry an toàn; mô tả hợp đồng bằng OpenAPI.
- Kiểm thử không chỉ phần body mà cả status, header và hành vi khi lỗi.

## 2. Mã trạng thái nằm ở đâu trong phản hồi HTTP?

Trong HTTP/1.1, status xuất hiện trong dòng đầu của phản hồi. HTTP/2 và HTTP/3 biểu diễn status bằng trường giả **:status**, thay vì dòng trạng thái dạng văn bản; **ý nghĩa mã vẫn như nhau**.

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng được yêu cầu.",
  "instance": "/orders/ord-999"
}
~~~

Ba chữ số đầu của mã xác định nhóm. Phần tên như **Not Found** là *reason phrase* mang tính mô tả trong HTTP/1.1; client cần dựa vào **mã số**, không so khớp chuỗi lý do. Trong HTTP/2 và HTTP/3, reason phrase không nằm trong status theo dạng HTTP/1.1.

**Status không thay thế body và header:**

- Status cho biết loại kết quả ở cấp HTTP.
- Header cung cấp thông tin như **Location**, **Allow**, **ETag**, **WWW-Authenticate**, **Retry-After**, **Cache-Control**.
- Body trình bày resource hoặc thông tin lỗi có cấu trúc, khi loại phản hồi cho phép có body.

Ví dụ, **401** đi cùng thử thách xác thực trong **WWW-Authenticate**; **405** phải nêu các phương thức hiện được hỗ trợ qua **Allow**; **201** có thể kèm **Location** để định danh tài nguyên mới; **304** không có nội dung phản hồi và dùng để kiểm tra cache.

## 3. Bức tranh tổng quan năm nhóm

| Nhóm | Tên thường gọi | Ý nghĩa chính | Ví dụ |
| --- | --- | --- | --- |
| **1xx** | Informational | Thông tin tạm thời; trao đổi HTTP đang tiếp diễn. | 100 Continue, 101 Switching Protocols, 103 Early Hints |
| **2xx** | Successful | Yêu cầu đã được server tiếp nhận và xử lý thành công theo ngữ nghĩa của mã. | 200 OK, 201 Created, 202 Accepted, 204 No Content |
| **3xx** | Redirection | Cần hành động bổ sung để hoàn tất truy xuất, hoặc phản hồi hỗ trợ tái sử dụng bản cache. | 301, 302, 303, 304, 307, 308 |
| **4xx** | Client Error | Server không thể hoặc không muốn thực hiện yêu cầu vì vấn đề gắn với yêu cầu hoặc chính sách áp dụng cho client. | 400, 401, 403, 404, 409, 412, 422, 429 |
| **5xx** | Server Error | Server hoặc trung gian gặp lỗi hay không thể thực hiện yêu cầu hợp lệ trong điều kiện hiện tại. | 500, 502, 503, 504 |

Đây là **phân loại giao thức**, không phải phán quyết ai “có lỗi” về mặt tổ chức. Ví dụ **429 Too Many Requests** thuộc 4xx dù giới hạn lưu lượng do server thiết lập; **504 Gateway Timeout** có thể do gateway phát ra khi dịch vụ phía sau không trả lời đúng hạn. Chẩn đoán nguyên nhân cần thêm log, trace và thông tin từng hop.

Một request HTTP thông thường có **một phản hồi cuối cùng** (*final response*). Một số phản hồi **1xx** có thể xuất hiện trước nó. Client cần xử lý các phản hồi tạm thời mà không xem chúng là kết quả cuối cùng của thao tác.

## 4. Nhóm 1xx: thông tin trong khi xử lý

Nhóm **1xx Informational** mô tả trạng thái tạm thời trong quá trình trao đổi HTTP. Không dùng nhóm này để biểu đạt “đã tạo thành công” hay “nghiệp vụ đang chờ xử lý” theo kiểu endpoint thông thường.

| Mã | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **100 Continue** | Client có thể tiếp tục gửi phần thân yêu cầu sau khi gửi headers, trong luồng có cơ chế **Expect: 100-continue**. | Upload lớn, tránh gửi body khi server đã biết sẽ từ chối sớm. |
| **101 Switching Protocols** | Server đồng ý chuyển giao thức theo cơ chế Upgrade phù hợp. | Ví dụ quá trình nâng cấp từ HTTP/1.1 sang WebSocket. |
| **102 Processing** | Server đã nhận và đang xử lý, chưa có phản hồi cuối; gắn với các mở rộng như WebDAV. | Tác vụ WebDAV có xử lý lâu; ít dùng trong REST API thông thường. |
| **103 Early Hints** | Gợi ý sớm các resource có thể tải trước trong khi server chuẩn bị phản hồi cuối. | Gợi ý preload tài nguyên trên web. |

Ví dụ minh họa một luồng **100 Continue**:

~~~http
PUT /uploads/file-7 HTTP/1.1
Host: api.example.com
Content-Length: 10485760
Expect: 100-continue

HTTP/1.1 100 Continue

... client tiếp tục gửi 10 MiB dữ liệu ...

HTTP/1.1 201 Created
Location: /uploads/file-7
~~~

Ví dụ chỉ mô tả thứ tự tương tác, không phải một bản ghi TCP nguyên văn. Nếu server từ chối dựa trên header, server có thể trả phản hồi cuối mà không gửi **100**. Không phải client hoặc reverse proxy nào cũng trình bày 1xx giống nhau.

**Phân biệt quan trọng:** khi một yêu cầu tạo báo cáo đã được chấp nhận nhưng chạy nền chưa xong, nên cân nhắc **202 Accepted**, không dùng **102 Processing** làm hợp đồng công việc bất đồng bộ. **102** chỉ là thông báo tạm thời của một lần trao đổi HTTP; **202** là kết quả cuối nói rằng yêu cầu đã được chấp nhận để xử lý tiếp.

## 5. Nhóm 2xx: thành công, nhưng thành công theo cách nào?

| Mã | Ý nghĩa | Chọn khi |
| --- | --- | --- |
| **200 OK** | Yêu cầu thành công; biểu diễn tài nguyên hoặc kết quả xử lý có thể nằm trong body tùy phương thức. | GET một resource/danh sách, PUT/PATCH thành công có trả representation, POST thao tác trả kết quả không tạo resource mới theo hợp đồng. |
| **201 Created** | Yêu cầu đã được thực hiện và tạo một hoặc nhiều tài nguyên. | POST tạo đơn; PUT tới URI mới được tạo. |
| **202 Accepted** | Yêu cầu đã được chấp nhận để xử lý, **chưa hoàn tất** và có thể cuối cùng thất bại. | Tạo báo cáo nền, nhập dữ liệu lớn, công việc trong queue. |
| **204 No Content** | Thành công, không có nội dung phản hồi. | DELETE thành công; PUT/PATCH thành công khi client không cần body. |
| **206 Partial Content** | Trả một phần nội dung theo Range request hợp lệ. | Tải từng đoạn file/media. |
| **207 Multi-Status** | Biểu diễn nhiều kết quả riêng trong một phản hồi, thuộc mở rộng WebDAV. | Tác vụ WebDAV; không nên mặc định dùng cho batch REST tùy ý. |

### 5.1. Cặp phương thức và mã trả về

| Yêu cầu | Kết quả | Mã thường phù hợp |
| --- | --- | --- |
| GET /orders/ord-123 | Tìm thấy đơn; trả representation. | **200** |
| GET /orders?status=PENDING | Không có đơn nào; trả danh sách rỗng. | **200** với **[]**, không mặc định **404** |
| POST /orders | Tạo đơn mới và hoàn thành tại thời điểm đáp ứng. | **201** với Location |
| POST /exports | Chấp nhận job xuất dữ liệu, job còn xử lý. | **202** với đường theo dõi trạng thái |
| PUT /profiles/u-1 | Cập nhật tài nguyên đã tồn tại; trả body mới. | **200** |
| PUT /profiles/u-1 | Cập nhật thành công, không trả body. | **204** |
| PUT /profiles/u-1 | Tạo resource mới tại URI đó. | **201** |
| PATCH /orders/ord-123 | Cập nhật thành công, trả trạng thái đơn mới. | **200** |
| DELETE /orders/ord-123 | Xóa thành công, không trả body. | **204** |
| GET /files/f-1 với Range hợp lệ | Trả một đoạn được yêu cầu. | **206** với Content-Range |

**GET danh sách rỗng** vẫn truy xuất thành công một tập hợp nên thường trả **200** và danh sách rỗng. **GET tài nguyên đơn lẻ không tồn tại** thường trả **404**. Đây là khác biệt giữa resource collection và resource item.

### 5.2. 201 Created và Location

~~~http
HTTP/1.1 201 Created
Location: /orders/ord-123
Content-Type: application/json
ETag: "order-v1"

{"id":"ord-123","status":"PENDING"}
~~~

**Location** xác định nơi truy cập tài nguyên mới trong ví dụ. Với API có URI tạo tài nguyên rõ ràng, header này giúp client biết resource được tạo ở đâu. Đừng trả **201** chỉ vì “đã gọi POST”; POST có thể thực hiện thao tác không tạo resource.

### 5.3. 202 Accepted cho xử lý bất đồng bộ

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-47
Content-Type: application/json
Retry-After: 5

{"jobId":"job-47","state":"QUEUED"}
~~~

Client có thể gọi:

~~~http
GET /jobs/job-47 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json

{"jobId":"job-47","state":"FAILED","reason":"SOURCE_UNAVAILABLE"}
~~~

**200** ở lần GET thứ hai nói rằng **truy xuất tài nguyên job thành công**, không khẳng định công việc nghiệp vụ đã thành công. Trạng thái nghiệp vụ của job nằm trong trường **state**; muốn retry job hay thao tác tiếp cần tuân theo hợp đồng của API. **202** không phải lời hứa rằng công việc nền chắc chắn hoàn tất.

### 5.4. 204 No Content và body

Phản hồi **204** không mang nội dung phản hồi. Nếu API muốn trả JSON kết quả, chọn **200** hoặc mã khác thích hợp. Không trả:

~~~http
HTTP/1.1 204 No Content
Content-Type: application/json

{"success":true}
~~~

Đây là thiết kế sai vì body mâu thuẫn với ngữ nghĩa **204**. Tương tự, phản hồi cuối của yêu cầu **HEAD** không chứa body, dù status có thể là 200, 404 hoặc mã thích hợp khác.

## 6. Nhóm 3xx: chuyển hướng và xác thực lại cache

| Mã | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **300 Multiple Choices** | Có nhiều representation hoặc đích có thể chọn. | Ít dùng trong REST API thông thường. |
| **301 Moved Permanently** | Resource có URI mới mang tính lâu dài. | Một số user agent lịch sử có thể đổi POST thành GET khi chuyển hướng; không dựa vào việc giữ nguyên method. |
| **302 Found** | Resource tạm có URI khác. | Cũng có lịch sử chuyển POST sang GET. |
| **303 See Other** | Hướng dẫn client truy xuất resource khác bằng GET (hoặc HEAD). | Phù hợp sau POST để chuyển tới trang/trạng thái kết quả. |
| **304 Not Modified** | Điều kiện truy xuất cache cho biết representation đã lưu vẫn sử dụng được. | **Không trả body**; chỉ có ý nghĩa trong request có điều kiện phù hợp. |
| **307 Temporary Redirect** | Chuyển hướng tạm và **giữ nguyên phương thức** request. | Phù hợp khi không muốn POST tự đổi thành GET. |
| **308 Permanent Redirect** | Chuyển hướng lâu dài và **giữ nguyên phương thức** request. | Cân nhắc caching và client cũ khi thay URI lâu dài. |

### 6.1. Chuyển hướng không phải lúc nào cũng an toàn để theo tự động

Giả sử client gửi POST kèm body đến một endpoint cần chuyển địa chỉ. **307/308** chỉ dẫn client giữ nguyên phương thức và nội dung khi gửi lại tại đích. Với **301/302**, hành vi đổi POST thành GET đã tồn tại trong nhiều client; nếu ứng dụng phụ thuộc việc giữ nguyên POST, chọn mã có ngữ nghĩa rõ ràng và kiểm tra client thực tế.

Trong API có xác thực, phải cân nhắc phạm vi truyền Authorization/cookie khi đổi host. Không để tham số do người dùng kiểm soát trở thành **open redirect** dẫn tới domain không đáng tin cậy; kiểm tra chặt danh sách host/URI hợp lệ.

### 6.2. 304 Not Modified không có nghĩa “resource không tồn tại”

~~~http
GET /products/p-10 HTTP/1.1
If-None-Match: "product-v8"

HTTP/1.1 304 Not Modified
ETag: "product-v8"
Cache-Control: private, max-age=60
~~~

Client hoặc cache đã có representation với ETag phù hợp nên có thể tiếp tục dùng bản đó theo quy tắc cache. Server **không gửi lại toàn bộ JSON**. Ngược lại, nếu resource không tồn tại, cần cân nhắc **404**, không dùng **304**.

Điều kiện cache phụ thuộc phương thức, validator và thông tin cache theo tiêu chuẩn HTTP. Không phải response 2xx hay 3xx nào cũng tự động được cache; cần thiết kế **Cache-Control**, ETag hoặc Last-Modified phù hợp với mức nhạy cảm dữ liệu và hành vi cập nhật.

## 7. Nhóm 4xx: vấn đề với yêu cầu, điều kiện hoặc quyền truy cập

Đây là nhóm phổ biến nhất trong hợp đồng lỗi API. Cần phân biệt lỗi cú pháp, lỗi xác thực, quyền, trạng thái resource, điều kiện cập nhật và hạn mức.

| Mã | Ý nghĩa | Ví dụ và cách dùng |
| --- | --- | --- |
| **400 Bad Request** | Server không thể xử lý request vì cú pháp hoặc cấu trúc request không hợp lệ. | JSON không parse được, định dạng tham số không hợp lệ. |
| **401 Unauthorized** | Thiếu hoặc không có thông tin xác thực hợp lệ cho tài nguyên cần bảo vệ. | Không có bearer token hoặc token hết hạn; server gửi WWW-Authenticate phù hợp. |
| **403 Forbidden** | Server hiểu request nhưng từ chối thực hiện. | Người dùng đã đăng nhập nhưng không có quyền sửa đơn của tenant khác. |
| **404 Not Found** | Không tìm thấy representation hiện tại của resource, hoặc server không muốn tiết lộ sự tồn tại. | GET /orders/khong-ton-tai. |
| **405 Method Not Allowed** | Resource tồn tại nhưng phương thức không được hỗ trợ tại đích. | POST tới endpoint chỉ cho GET; response có header Allow. |
| **406 Not Acceptable** | Không có representation thỏa điều kiện Accept. | Client chỉ nhận định dạng mà server không thể trả. |
| **408 Request Timeout** | Server không nhận được request đầy đủ trong thời gian chờ. | Client gửi request quá chậm; cần phân biệt với gateway timeout. |
| **409 Conflict** | Yêu cầu xung đột với trạng thái hiện tại của resource. | Hủy đơn đã giao, tạo resource trùng ràng buộc nghiệp vụ. |
| **410 Gone** | Resource đã không còn khả dụng và tình trạng này được biết là lâu dài. | Một tài nguyên đã bị loại bỏ có chủ đích. |
| **412 Precondition Failed** | Điều kiện do client gửi (như If-Match) không thỏa. | ETag không còn khớp khi cập nhật đồng thời. |
| **413 Content Too Large** | Nội dung yêu cầu vượt giới hạn cho phép. | Upload lớn hơn ngưỡng hệ thống. |
| **415 Unsupported Media Type** | Định dạng nội dung không được hỗ trợ. | Gửi XML tới endpoint chỉ nhận JSON. |
| **416 Range Not Satisfiable** | Phạm vi byte yêu cầu không thể đáp ứng. | Range vượt kích thước resource. |
| **422 Unprocessable Content** | Media type được hiểu, cú pháp đúng nhưng nội dung không thể xử lý theo chỉ dẫn của nó. | Quantity âm trong đơn hàng nếu hợp đồng chọn 422 cho lỗi validation ngữ nghĩa. |
| **428 Precondition Required** | Server yêu cầu client gửi điều kiện trước khi thao tác. | Bắt buộc If-Match khi PATCH để ngăn lost update. |
| **429 Too Many Requests** | Client đã gửi quá nhiều request trong một khoảng hoặc phạm vi giới hạn. | Rate limit theo API key, tenant hoặc IP; có thể gửi Retry-After. |
| **431 Request Header Fields Too Large** | Tổng hoặc một trường header vượt giới hạn. | Cookie/header quá lớn. |
| **451 Unavailable For Legal Reasons** | Không cung cấp tài nguyên vì lý do pháp lý. | Hạn chế theo luật có thể áp dụng. |

Không cần sử dụng mọi mã trong ứng dụng. Hợp đồng nên nhất quán, có tài liệu về mã nào phát sinh và nội dung lỗi để client xử lý. Các mã hiếm hơn cần dùng đúng khi thực sự có ngữ nghĩa tương ứng.

### 7.1. 400 và 422: cú pháp so với nội dung có nghĩa

Ví dụ:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"quantity":
~~~

Body JSON bị cắt, không parse được; **400 Bad Request** phù hợp.

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"sku":"p-2","quantity":-3}
~~~

JSON có thể parse, nhưng số lượng âm vi phạm quy tắc đơn hàng. **422 Unprocessable Content** là lựa chọn rõ ràng; nhiều API cũng chuẩn hóa lỗi validation vào **400**, miễn được mô tả và áp dụng nhất quán. Nếu nội dung hợp lệ nhưng xung đột trạng thái hệ thống (ví dụ số lượng sản phẩm không còn đủ theo thời điểm xử lý), cân nhắc **409 Conflict** và mô tả quy tắc cụ thể.

Không nên biến mọi lỗi nghiệp vụ thành **500**; server vẫn hoạt động bình thường khi từ chối một yêu cầu không hợp lệ.

### 7.2. 401 và 403: xác thực khác phân quyền

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Content-Type: application/problem+json

{"title":"Authentication required","status":401}
~~~

- **401:** client cần cung cấp hoặc làm mới thông tin xác thực hợp lệ; tên “Unauthorized” dễ gây nhầm nhưng ý nghĩa thực tế gắn với **authentication**. Server phát 401 phải có thử thách xác thực tương ứng trong **WWW-Authenticate**.
- **403:** server từ chối quyền truy cập ngay cả khi đã hiểu yêu cầu; gửi lại cùng credentials thường không giúp. Có thể áp dụng cho client không được phép, bất kể trạng thái xác thực cụ thể.
- **404 thay vì 403:** một số hệ thống muốn che giấu sự tồn tại của resource nhạy cảm. Đây phải là quyết định bảo mật và hợp đồng nhất quán, không được để thông điệp body, timing hoặc endpoint phụ vô tình tiết lộ tài nguyên.

### 7.3. 405 và 501: sai phương thức hay server chưa hỗ trợ?

Nếu server nhận biết phương thức nhưng không cho phép trên resource cụ thể, trả **405 Method Not Allowed** kèm **Allow**:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
Content-Type: application/problem+json

{"title":"Method not allowed","status":405}
~~~

Nếu server không nhận biết hoặc không hỗ trợ chức năng cần thiết của phương thức trên toàn server, **501 Not Implemented** có thể phù hợp. Đây không phải cách đổi mọi lỗi phương thức sang 5xx; endpoint không cho POST thường là 405.

### 7.4. 409 và 412: hai trường hợp đồng thời khác nhau

**409 Conflict:** thao tác không phù hợp với trạng thái resource:

~~~http
POST /orders/ord-123/cancel HTTP/1.1

HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"title":"Order cannot be cancelled","status":409,
 "detail":"Đơn đã bàn giao cho đơn vị vận chuyển."}
~~~

**412 Precondition Failed:** client gửi điều kiện cập nhật nhưng điều kiện không còn đúng:

~~~http
PATCH /orders/ord-123 HTTP/1.1
If-Match: "order-v5"
Content-Type: application/merge-patch+json

{"deliveryNote":"Gọi trước khi giao"}

HTTP/1.1 412 Precondition Failed
ETag: "order-v6"
~~~

Giả sử client đọc phiên bản v5, nhưng server đã chuyển lên v6. Điều kiện **If-Match** thất bại và trả **412** giúp client không vô tình ghi đè thay đổi của người khác. Với API bắt buộc conditional update, thiếu hẳn **If-Match** có thể dẫn đến **428 Precondition Required**. Nếu dùng một cơ chế version nghiệp vụ khác thay vì HTTP conditional headers, có thể cần 409 theo hợp đồng; đừng đánh đồng hai cơ chế.

### 7.5. 404, 410 và danh sách rỗng

- **404:** GET resource theo ID không tìm thấy, chưa chắc biết resource đã bị xóa vĩnh viễn.
- **410:** resource từng tồn tại và server biết nó đã không còn khả dụng theo cách lâu dài; có thể phù hợp với API tài nguyên đã ngừng cung cấp.
- **200 + []:** truy vấn collection hợp lệ nhưng không có phần tử nào. Không đánh đồng collection rỗng với URI không tồn tại.
- **DELETE resource không tồn tại:** trả 404 hoặc 204 có thể đều là hợp đồng được cân nhắc; tính *idempotent* của DELETE nói về hiệu ứng của nhiều lần gọi, không bắt buộc status của mọi lần giống nhau. Ghi rõ lựa chọn API.

## 8. Nhóm 5xx: lỗi ở server hoặc trung gian

| Mã | Ý nghĩa | Khi nào sử dụng |
| --- | --- | --- |
| **500 Internal Server Error** | Server gặp tình huống bất ngờ khiến không thể thực hiện request. | Lỗi xử lý chưa được phân loại, exception không dự kiến. |
| **501 Not Implemented** | Server không hỗ trợ chức năng cần để xử lý yêu cầu. | Không nhận biết hoặc không hỗ trợ phương thức/chức năng HTTP. |
| **502 Bad Gateway** | Gateway/proxy nhận phản hồi không hợp lệ từ upstream khi đang phục vụ yêu cầu. | Reverse proxy gặp phản hồi upstream hỏng hoặc không hợp lệ. |
| **503 Service Unavailable** | Server tạm thời không thể xử lý vì quá tải hoặc bảo trì. | Dịch vụ đang tạm ngừng, thiếu capacity; có thể gửi Retry-After. |
| **504 Gateway Timeout** | Gateway/proxy không nhận phản hồi kịp thời từ upstream. | API gateway timeout khi gọi service phụ thuộc. |
| **507 Insufficient Storage** | Server không đủ khả năng lưu trạng thái cần thiết để hoàn tất yêu cầu (mã từ WebDAV). | Tình huống lưu trữ đặc thù khi semantics phù hợp. |

### 8.1. 500, 502, 503 và 504 không thay thế nhau

Xét request:

~~~mermaid
flowchart LR
    C[Client] --> G[API Gateway]
    G --> O[Orders Service]
    O --> D[(Database)]
~~~

- Nếu **Orders Service** gặp lỗi ngoài dự kiến ở logic nội bộ, phản hồi cuối có thể là **500**.
- Nếu **Gateway** nhận được phản hồi upstream không hợp lệ theo giao thức khi đóng vai trò gateway, nó có thể phát **502**.
- Nếu **Gateway** chờ **Orders Service** quá thời gian cấu hình, nó có thể phát **504**.
- Nếu server chủ động không phục vụ tạm thời do maintenance hoặc quá tải, **503** có thể phù hợp; **Retry-After** có thể gợi ý khi nào thử lại.

Phân biệt các mã theo **đối tượng phát sinh** và **nguyên nhân quan sát được**. Ví dụ, timeout DB trong một ứng dụng không tự động có nghĩa ứng dụng phải trả **504**: 504 mô tả tình huống của một server đang hoạt động với vai trò gateway/proxy và không nhận phản hồi kịp từ upstream. Trong hệ thống nhiều tầng, mã cuối cùng có thể do gateway thay vì controller ứng dụng phát ra.

### 8.2. 503 và Retry-After

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 60
Content-Type: application/problem+json

{"title":"Service temporarily unavailable","status":503}
~~~

**Retry-After: 60** gợi ý client chờ tối thiểu khoảng 60 giây trước khi gửi lại yêu cầu, theo hợp đồng và chiến lược retry. Header này cũng có thể mang thời điểm HTTP-date. Nó không bảo đảm sau 60 giây dịch vụ chắc chắn khỏe lại; client vẫn cần giới hạn retry, timeout, backoff và ngân sách gọi.

**Không đưa stack trace, secret, SQL hay token vào body 5xx.** Thông tin chi tiết phục vụ chẩn đoán nên lưu an toàn trong log/trace với correlation ID; client nhận mã lỗi ổn định và mô tả không làm lộ dữ liệu nhạy cảm.

## 9. Chọn status theo kết quả thực tế, không theo tên endpoint

Một cách phân tích request REST là:

~~~mermaid
flowchart TD
    A[Yêu cầu đến API] --> B{Xác thực hợp lệ?}
    B -->|Thiếu / không hợp lệ| C[401 + WWW-Authenticate]
    B -->|Có, hoặc endpoint công khai| D{Được phép truy cập?}
    D -->|Không| E[403 hoặc 404 để che tồn tại]
    D -->|Có| F{Cú pháp / media type hợp lệ?}
    F -->|Sai cú pháp| G[400]
    F -->|Media type không hỗ trợ| H[415]
    F -->|Hợp lệ| I{Đủ điều kiện xử lý?}
    I -->|Validation ngữ nghĩa lỗi| J[422 hoặc 400 theo hợp đồng]
    I -->|Xung đột trạng thái| K[409]
    I -->|If-Match không khớp| L[412]
    I -->|Được xử lý| M{Kết quả?}
    M -->|Đã tạo resource| N[201 + Location]
    M -->|Chấp nhận xử lý nền| O[202]
    M -->|Có representation| P[200]
    M -->|Không có body| Q[204]
~~~

Sơ đồ là **khung quyết định cho các tình huống phổ biến**, không bao trùm 1xx, 3xx, 404/405/406/429 hay lỗi 5xx. Thứ tự xác thực và kiểm tra body cũng có thể khác tùy thiết kế an toàn; server có thể dùng 404 để che resource hoặc từ chối sớm vì giới hạn dung lượng/tần suất. Điều cần giữ là **status khớp đúng điều đã xảy ra và hợp đồng công bố**.

**Ví dụ về một thao tác kiểm tra đơn:**

| Trường hợp | Mã gợi ý | Lý do |
| --- | --- | --- |
| GET /orders/42, resource tồn tại | 200 | Truy xuất thành công |
| GET /orders/42, không tìm thấy | 404 | Resource theo ID không tồn tại |
| GET /orders?customerId=1, tập rỗng | 200 | Collection được truy vấn thành công |
| POST /orders tạo resource mới | 201 | Tạo thành công; Location chỉ tới đơn mới |
| POST /orders được đưa vào queue và chưa xử lý | 202 | Đã chấp nhận, chưa hoàn tất |
| POST /orders, JSON sai cú pháp | 400 | Request không parse được |
| POST /orders, thiếu quyền tạo đơn | 403 | Hành động bị từ chối |
| POST /orders, vi phạm trạng thái đơn đang tồn tại | 409 | Xung đột trạng thái |
| PATCH /orders/42 với ETag cũ | 412 | Điều kiện cập nhật thất bại |
| API gateway không nhận phản hồi upstream đúng hạn | 504 | Timeout khi đóng vai trò gateway |

## 10. Ai có trách nhiệm phát và diễn giải status?

HTTP là giao thức xuyên nhiều tầng. Cần phân biệt **nơi quyết định status**, **nơi phát ra phản hồi cuối** và **nơi diễn giải hành động tiếp theo**.

| Vai trò | Trách nhiệm chính | Sai sót thường gặp |
| --- | --- | --- |
| **Ứng dụng/API origin** | Chọn mã từ kết quả nghiệp vụ và điều kiện giao thức; trả header/body nhất quán; không lộ bí mật. | Luôn trả 200 rồi giấu lỗi trong JSON; trả 500 cho lỗi validation. |
| **Framework/middleware** | Xử lý parsing, negotiation, authentication, authorization, method routing và exception mapping. | Định nghĩa lỗi ở controller nhưng quên lỗi trước controller do security filter/gateway tạo. |
| **Gateway/reverse proxy/load balancer** | Áp giới hạn, định tuyến, xử lý upstream và có thể tự phát 4xx/5xx. | 502/504 bị hiểu nhầm là lỗi do controller tạo; đổi status làm mất ngữ nghĩa. |
| **Client/SDK** | Kiểm tra status và header, diễn giải payload đúng hợp đồng, xử lý redirect/cache/auth/retry hợp lý. | Chỉ parse JSON rồi nhìn trường success; retry mọi 5xx/POST vô hạn. |
| **Cache/CDN** | Thực hiện chính sách cache, điều kiện ETag, thời hạn và invalidation phù hợp. | Cache dữ liệu nhạy cảm hoặc trả dữ liệu cũ không đúng yêu cầu nghiệp vụ. |
| **Monitoring/operations** | Đo tỷ lệ 4xx/5xx, độ trễ, phân bổ theo route, upstream và nguyên nhân. | Xem mọi 4xx là lỗi server; không phân biệt status do proxy phát. |

### 10.1. Một status code chưa đủ cho client

Client cần đọc thêm header và nội dung hợp đồng:

- **201 + Location:** lấy URI tài nguyên mới để GET hoặc liên kết.
- **202 + đường dẫn job:** theo dõi trạng thái nền; không giả định kết quả cuối đã thành công.
- **301/308 + Location:** xem xét hướng chuyển và bảo mật trước khi làm theo.
- **304 + ETag/cache metadata:** giữ hoặc cập nhật bản cache theo quy tắc HTTP.
- **401 + WWW-Authenticate:** quyết định cung cấp/làm mới chứng thực, tránh vòng lặp login vô hạn.
- **405 + Allow:** biết phương thức nào được chấp nhận.
- **412:** tải phiên bản mới, hòa giải thay đổi; không ghi đè mù.
- **429/503 + Retry-After:** hoãn và giới hạn số lần gửi lại.

**Mã status là tín hiệu chung của giao thức; quyết định UX và nghiệp vụ là trách nhiệm của client theo hợp đồng API.** Ví dụ, khi GET một job trả 200 nhưng trường state là FAILED, client phải hiển thị công việc thất bại dù truy vấn HTTP thành công.

### 10.2. Khi proxy thay đổi mã status

Nếu client nhận 504, có thể gateway đã hết thời gian chờ trong khi ứng dụng upstream vẫn tiếp tục xử lý. Request ghi **có thể đã commit** dù client thấy lỗi. Không được suy luận “504 nghĩa là nghiệp vụ chắc chắn thất bại”. Đối với POST thanh toán hoặc tạo đơn, client cần idempotency key hoặc phương thức tra cứu trạng thái giao dịch trước khi gửi lại.

Log nên có ít nhất request ID/trace ID, HTTP method, route dạng template, status phát từ origin, status quan sát tại gateway, upstream duration, error code nội bộ và thời gian. Không đưa token, dữ liệu cá nhân hoặc toàn body nhạy cảm vào log.

## 11. Thiết kế lỗi có cấu trúc với Problem Details

Để client xử lý lỗi nhất quán, có thể dùng định dạng **Problem Details for HTTP APIs** theo **RFC 9457**, với media type **application/problem+json**.

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-Id: req-7ad

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn hàng đã giao nên không thể hủy.",
  "instance": "/orders/ord-123/cancel",
  "code": "ORDER_ALREADY_SHIPPED",
  "requestId": "req-7ad"
}
~~~

Ý nghĩa chính:

- **type:** định danh loại vấn đề; có thể dẫn tới tài liệu giải thích và cách xử lý.
- **title:** tóm tắt ngắn, ổn định cho loại lỗi.
- **status:** bản sao mã HTTP để tiện đọc nội dung, **không thay thế status thực của phản hồi**.
- **detail:** mô tả tình huống cụ thể, phù hợp với người dùng hoặc developer.
- **instance:** định danh lần xảy ra hoặc đối tượng lỗi theo cách API quy định.
- **code/requestId:** trường mở rộng riêng phục vụ xử lý chương trình và tra cứu sự cố.

Không dùng message tiếng Việt có thể thay đổi làm khóa điều khiển logic client. Hãy đưa **code/type ổn định** vào hợp đồng; nội dung detail có thể được bản địa hóa. Không đưa thông tin triển khai nội bộ, stack trace, cấu trúc DB, token hoặc dữ liệu cá nhân không cần thiết ra ngoài.

### 11.1. Lỗi validation nhiều trường

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 422,
  "detail": "Dữ liệu đơn hàng chưa hợp lệ.",
  "invalidParams": [
    {"name": "items[0].quantity", "reason": "Phải lớn hơn 0"},
    {"name": "currency", "reason": "Không hỗ trợ mã tiền tệ này"}
  ]
}
~~~

**invalidParams** là trường mở rộng minh họa, không phải field bắt buộc trong Problem Details. Nếu ứng dụng chọn 400 cho loại validation này, cần sửa cả status line, trường status và tài liệu hợp đồng cho thống nhất.

## 12. Retry, idempotency và cache liên quan trực tiếp tới mã status

### 12.1. Không retry theo nhóm mã một cách máy móc

| Kết quả | Hành động client thường hợp lý | Điều kiện cần kiểm tra |
| --- | --- | --- |
| **200/201/204** | Ghi nhận thành công theo ngữ nghĩa thao tác. | Lưu Location/ETag nếu có, không parse body của 204. |
| **202** | Theo dõi trạng thái xử lý nền. | Có endpoint polling/webhook, giới hạn tần suất. |
| **304** | Dùng representation đã cache theo quy tắc. | Có bản cache và validator tương ứng. |
| **400/422** | Sửa request theo thông tin validation. | Không retry y nguyên liên tục. |
| **401** | Thực hiện luồng xác thực hợp lệ. | Tránh refresh token vòng lặp vô hạn. |
| **403/404/409/412** | Xử lý quyền, resource, conflict hoặc phiên bản. | Không tự động retry với cùng dữ liệu khi không có thay đổi. |
| **429** | Backoff/rate limit, cân nhắc Retry-After. | Hạn mức theo user, tenant hoặc client. |
| **500/502/503/504** | Có thể retry có giới hạn sau khi xác định tính an toàn. | Phải cân nhắc thao tác đã commit, idempotency và Retry-After. |

Nếu kết nối mất hoặc gateway timeout, client có thể **không biết** server đã xử lý request chưa. Với lệnh tạo đơn hoặc thanh toán, retry tự động có thể tạo trùng tác dụng phụ.

**Idempotency key** là một cách thiết kế hợp đồng cho POST nhạy cảm:

~~~http
POST /payments HTTP/1.1
Idempotency-Key: pay-req-7ad
Content-Type: application/json

{"orderId":"ord-123","amountMinor":199900}
~~~

Server cần lưu quan hệ giữa key, phạm vi client, payload và kết quả theo chính sách. Khi client gửi lại cùng key và cùng thao tác, server trả kết quả tương ứng mà không thực hiện thanh toán lần hai; cùng key nhưng nội dung khác cần bị phát hiện và xử lý nhất quán (ví dụ 409 theo hợp đồng). Cơ chế khóa/lưu kết quả, thời hạn lưu key, xử lý request đồng thời và bảo mật dữ liệu đều cần được thiết kế cụ thể.

**Idempotent ở phương thức HTTP** không đồng nghĩa mọi lần gọi có cùng response status: DELETE nhiều lần có thể trả 204 rồi 404. Điều quan trọng là hiệu ứng dự kiến của những lần gọi giống nhau không làm thay đổi trạng thái ngoài lần đầu theo ngữ nghĩa idempotency.

### 12.2. Cache đúng với ngữ nghĩa HTTP

- **GET/HEAD** là phương thức chủ đạo trong cache; phản hồi tùy status, header và quy định bộ nhớ đệm.
- **ETag/If-None-Match** giúp server trả 304 khi representation chưa thay đổi.
- **Cache-Control: private** giới hạn cache riêng cho một client; **no-store** chỉ dẫn không lưu phản hồi, đặc biệt phù hợp với dữ liệu nhạy cảm khi cần.
- **404** và một số status khác có thể được cache theo quy tắc HTTP, kể cả theo heuristic trong điều kiện thích hợp. Nếu resource có thể xuất hiện ngay sau đó, cần chủ động cấu hình cache để tránh 404 cũ còn hiệu lực.
- **401/403** liên quan thông tin người dùng; phải kiểm tra chính sách cache và Authorization để tránh chia sẻ phản hồi giữa người dùng/tenant.

Đừng chỉ gắn 200 cho mọi response để “CDN cache dễ hơn”. Cache phụ thuộc nhiều yếu tố; status sai sẽ phá ngữ nghĩa client và làm khó chẩn đoán.

## 13. Thực hành với Java/Spring: status ở controller và lớp xử lý lỗi

### 13.1. Controller trả 201, 200, 404 và 204

Ví dụ rút gọn với Spring MVC/Spring Boot (các lớp OrderService, OrderView và CreateOrderRequest giả định đã có):

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderView order = service.create(request);
        URI location = URI.create("/orders/" + order.id());
        return ResponseEntity.created(location).body(order);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(@PathVariable UUID id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable UUID id) {
        service.deleteIfPresent(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ, **POST** trả **201** và Location, **GET** trả **200** hoặc **404**, **DELETE** trả **204** theo chính sách xóa idempotent. Nếu quy tắc hệ thống yêu cầu báo 404 khi xóa một resource không tồn tại, cần sửa service/controller và tài liệu phù hợp. Trường **id** là UUID trong ví dụ; payload thực tế có thể dùng định danh khác.

### 13.2. Ánh xạ lỗi nghiệp vụ sang ProblemDetail

Spring Framework hỗ trợ **ProblemDetail** trong các phiên bản hiện đại. Ví dụ:

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> conflict(OrderConflictException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.CONFLICT,
                        "Trạng thái hiện tại không cho phép thao tác này.");
        problem.setTitle("Order state conflict");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-state-conflict"));
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

Trong hệ thống thật, cần thống nhất mapping cho validation, lỗi parse body, resource không tồn tại, conflict, thiếu điều kiện cập nhật và lỗi không mong đợi. Các phản hồi **401/403** có thể do lớp **Spring Security** xử lý trước khi request tới controller; muốn body nhất quán phải cấu hình **AuthenticationEntryPoint/AccessDeniedHandler** và kiểm tra gateway nếu có.

Không nên bắt mọi exception rồi trả **200** với JSON chứa trường error. Lỗi không phân loại phải được ghi lại ở nơi phù hợp và có response 5xx an toàn; lỗi nghiệp vụ được biết trước cần ánh xạ thành 4xx đúng ngữ nghĩa.

### 13.3. Mô tả status trong OpenAPI

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    post:
      summary: Tạo đơn hàng
      responses:
        "201":
          description: Đơn hàng được tạo
          headers:
            Location:
              description: URI của đơn hàng mới
              schema:
                type: string
                format: uri-reference
        "400":
          description: Request không hợp lệ
        "401":
          description: Thiếu hoặc sai thông tin xác thực
        "409":
          description: Xung đột với trạng thái hiện tại
        "422":
          description: Nội dung đơn hàng không xử lý được
        "429":
          description: Vượt giới hạn gọi API
        "500":
          description: Lỗi server không mong đợi
~~~

Đây là **trích đoạn minh họa phần responses**, chưa phải đặc tả API đầy đủ: production còn cần requestBody, schemas, securitySchemes, content cho từng body và các mã có thể phát từ proxy. OpenAPI nên mô tả những phản hồi mà client cần xử lý; đừng chỉ khai báo 200 trong khi API có quy tắc xác thực, phân quyền và conflict.

## 14. Kiểm thử hợp đồng status và header

### 14.1. Ma trận kiểm thử

| Kịch bản | Yêu cầu | Kỳ vọng cần kiểm |
| --- | --- | --- |
| Truy vấn resource tồn tại | GET /orders/id-hợp-lệ | 200, JSON hợp schema, Content-Type đúng |
| Không tìm thấy item | GET /orders/id-không-có | 404, Problem Details nếu được định nghĩa |
| Danh sách rỗng | GET /orders?status=NONE | 200, body là collection rỗng |
| Tạo đơn | POST /orders hợp lệ | 201, Location hợp lệ, resource GET được |
| Job chạy nền | POST /exports | 202, thông tin truy vấn trạng thái |
| Xóa xong | DELETE /orders/id | 204, **không có body** |
| Không xác thực | GET endpoint bảo vệ không có token | 401, WWW-Authenticate phù hợp |
| Không đủ quyền | GET/PATCH resource khác tenant | 403 hoặc 404 theo chính sách đã định |
| Phương thức bị từ chối | POST vào resource chỉ đọc | 405 và Allow |
| Media type sai | POST với Content-Type không hỗ trợ | 415 |
| ETag cũ | PATCH kèm If-Match cũ | 412, trạng thái resource không bị ghi đè |
| Validation | POST quantity âm | 422 hoặc 400 đúng tài liệu |
| Rate limit | Gửi quá ngưỡng kiểm thử | 429, backoff/Retry-After nếu áp dụng |
| Upstream timeout | Mô phỏng gateway chờ quá hạn | 504 tại gateway, log/trace chỉ rõ nguồn |
| Dịch vụ bảo trì | Kiểm thử chế độ ngưng phục vụ | 503, Retry-After nếu có |
| Kiểm tra cache | GET kèm If-None-Match trùng | 304, không gửi body, cache tái sử dụng đúng |

### 14.2. Ví dụ curl và Spring MockMvc

~~~bash
# -i hiển thị status line và headers để xác minh hợp đồng.
curl -i https://api.example.com/orders/ord-123

# Gửi điều kiện cache; kỳ vọng 304 nếu ETag còn khớp.
curl -i -H 'If-None-Match: "order-v1"' \
  https://api.example.com/orders/ord-123
~~~

Ví dụ test Spring MVC tối giản:

~~~java
mockMvc.perform(
        post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"customerId\":\"c-17\",\"items\":[{\"sku\":\"p-2\",\"quantity\":2}]}"))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"));

mockMvc.perform(get("/orders/{id}", missingOrderId))
    .andExpect(status().isNotFound());
~~~

**Lưu ý:** ví dụ MockMvc giả định service chấp nhận SKU và customerId đã cung cấp, đồng thời endpoint được cấu hình cho phép request thử; khi có Spring Security, test cần bổ sung thông tin xác thực hợp lệ. Cần bổ sung kiểm tra body/schema, 401/403, 409/412, 429, cache và integration test đi qua security filter/gateway. MockMvc kiểm tra controller/lớp Spring, nhưng không tự thay thế thử nghiệm proxy, CDN và mạng production.

### 14.3. Kiểm thử hành vi, không chỉ kiểm tra ba chữ số

Một API trả 201 nhưng thiếu resource thực tế, hoặc trả 202 rồi không có cách biết job hoàn tất, vẫn là thiết kế kém dù mã số đúng. Bộ kiểm thử nên xác nhận:

1. Header quan trọng và body tương thích mã; 204/304 không có body.
2. Thực thể mới đọc được từ Location; đường dẫn trả về không chứa host không tin cậy.
3. Từ 401, client nhận được thử thách xác thực; từ 403, quyền bị từ chối đúng tenant.
4. Concurrent update với ETag cũ không làm mất sửa đổi đã commit.
5. Retry sau timeout không tạo đơn hoặc thanh toán trùng.
6. Cache và conditional GET sử dụng đúng ETag/Cache-Control.
7. Lỗi do gateway phát sinh được đo ở đúng hop và được client xử lý theo contract.

## 15. Những phản mẫu cần tránh

| Phản mẫu | Tác hại | Cách sửa |
| --- | --- | --- |
| Luôn trả 200, lỗi nằm trong body | SDK, proxy, metric và logic retry không biết lỗi giao thức. | Dùng 4xx/5xx đúng ngữ nghĩa, thêm mã lỗi nghiệp vụ ổn định. |
| Dùng 500 cho mọi validation | Báo sai rằng server lỗi; retry có thể vô ích. | Phân biệt parse, validation, permission và conflict bằng 4xx. |
| Trả 401 khi đã xác thực nhưng thiếu quyền | Client có thể liên tục refresh token mà không giải quyết được. | Phân biệt 401 xác thực và 403 phân quyền. |
| Trả 404 cho collection rỗng | Client hiểu nhầm collection endpoint không tồn tại. | Trả 200 với collection rỗng khi truy vấn hợp lệ. |
| Dùng 201 cho POST chưa xong | Client tưởng tài nguyên đã sẵn sàng. | Dùng 202 và đường theo dõi cho job chạy nền. |
| Dùng 204 kèm JSON | Vi phạm ngữ nghĩa không có content. | Chọn 200 nếu phải trả body. |
| Trả 409 cho ETag không khớp nhưng hợp đồng dùng If-Match | Mất khả năng hiểu chuẩn điều kiện HTTP. | Trả 412 cho precondition thất bại. |
| Gateway timeout, client retry POST vô hạn | Tạo trùng tài nguyên/tác dụng thanh toán. | Idempotency key, tra cứu trạng thái, retry có giới hạn. |
| Cache mọi status theo cùng TTL | Lộ dữ liệu nhạy cảm hoặc giữ 404/200 quá lâu. | Thiết kế Cache-Control và validator theo loại tài nguyên. |
| Status đúng nhưng body lỗi chứa stack trace | Lộ nội bộ, dữ liệu nhạy cảm. | Problem Details an toàn và log/trace nội bộ. |

## 16. Tình huống thực hành: API đặt hàng đa tầng

Một ứng dụng di động gọi API đặt hàng qua gateway. Server dùng Spring; việc tạo đơn được xử lý đồng bộ, còn xuất hóa đơn điện tử chạy nền. Tất cả endpoint yêu cầu bearer token. API có ETag trên đơn và rate limit theo user.

Hãy chọn mã cho các tình huống sau trước khi xem lời giải:

1. Người dùng chưa đăng nhập gọi GET /orders/ord-1.
2. Người dùng đã đăng nhập gọi GET đơn của tenant khác mà chính sách không che tồn tại.
3. GET /orders?status=PAID không tìm thấy đơn nào.
4. POST /orders tạo mới, trả về ID.
5. POST /orders/ord-1/invoice yêu cầu xuất hóa đơn, hệ thống đặt công việc vào queue.
6. PATCH /orders/ord-1 với If-Match là ETag của phiên bản cũ.
7. POST /orders gửi số lượng âm với JSON hợp lệ.
8. Client gọi API vượt hạn mức tạm thời.
9. Gateway gọi order-service bị timeout, không nhận kết quả.
10. GET /orders/ord-1 có If-None-Match trùng ETag hiện tại.

**Gợi ý đáp án và trách nhiệm diễn giải:**

| # | Mã | Lý do và hành động client |
| --- | --- | --- |
| 1 | **401** | Cần xác thực; đọc WWW-Authenticate và thực hiện luồng đăng nhập/token. |
| 2 | **403** | Có danh tính nhưng không có quyền; không retry với cùng quyền. |
| 3 | **200** | Collection rỗng là kết quả truy vấn hợp lệ; trả []. |
| 4 | **201** | Resource được tạo; Location trỏ đến resource vừa tạo. |
| 5 | **202** | Job nền đã nhận, chưa xong; theo dõi job. |
| 6 | **412** | If-Match không thỏa; tải phiên bản mới và hòa giải trước khi sửa lại. |
| 7 | **422** | Nội dung cú pháp đúng nhưng không xử lý được; 400 cũng có thể phù hợp nếu hợp đồng validation nhất quán. |
| 8 | **429** | Giảm tốc độ, backoff; dùng Retry-After nếu server cung cấp. |
| 9 | **504** | Gateway không nhận phản hồi kịp; kiểm tra trạng thái giao dịch trước khi retry lệnh ghi. |
| 10 | **304** | Representation đã cache còn hợp lệ theo điều kiện; không nhận lại body. |

Một ca nâng cao: lần POST tạo đơn thứ nhất đã commit nhưng gateway trả 504; lần thứ hai client gửi cùng **Idempotency-Key**. Kết quả cuối phải không tạo đơn thứ hai. API có thể trả cùng kết quả được lưu của lần đầu theo chính sách, trong đó status phản ánh kết quả đã ghi nhận. Đừng dựa vào 504 để kết luận lần ghi đầu không thành công.

## 17. Checklist thiết kế và đánh giá mã trạng thái

- [ ] Mỗi endpoint có danh sách status theo phương thức và kết quả thực tế, được ghi trong OpenAPI.
- [ ] 1xx được hiểu là thông tin tạm thời; không nhầm với 202 cho xử lý nền.
- [ ] GET item, GET collection rỗng, POST tạo mới, PUT/PATCH, DELETE có status phù hợp.
- [ ] Không trả body cho 204 hoặc 304; response 201 và 202 có thông tin cần để tiếp tục tương tác.
- [ ] Chuyển hướng 301/302/303/307/308 được chọn với hiểu biết về method và bảo mật.
- [ ] 401 kèm WWW-Authenticate; 403 phản ánh quyền; 405 kèm Allow.
- [ ] Lỗi parse, media type, validation, conflict và precondition được phân biệt rõ.
- [ ] Lỗi 5xx được phân loại theo nguồn phát sinh, tránh ghi đè status do gateway mà không có lý do.
- [ ] Payload lỗi có cấu trúc, mã lỗi ổn định, không làm lộ thông tin nhạy cảm.
- [ ] Retry có backoff/giới hạn; các thao tác ghi nhạy cảm có cách chống trùng và tra cứu trạng thái.
- [ ] Cache, ETag, Cache-Control và quyền truy cập được kiểm thử cùng nhau.
- [ ] Monitoring phân biệt 4xx/5xx theo route và hop; có trace để tìm nguyên nhân.
- [ ] Test xác minh status, header, body, hành vi resource, tính nhất quán và bảo mật thay vì chỉ so mã số.

**Điểm cốt lõi:** **1xx** thông báo tiến trình trao đổi; **2xx** diễn tả cách thành công; **3xx** điều hướng hoặc hỗ trợ cache; **4xx** chỉ ra yêu cầu không thể thực hiện trong điều kiện hiện tại; **5xx** chỉ ra lỗi hoặc sự bất khả dụng phía server/trung gian. **Server chịu trách nhiệm chọn và phát mã đúng ngữ nghĩa; client chịu trách nhiệm diễn giải status, header và hợp đồng; gateway và cache có thể tham gia hoặc tạo phản hồi.** Chỉ khi cả các tầng cùng tôn trọng những ngữ nghĩa này, REST API mới có thể được sử dụng, kiểm thử, mở rộng và vận hành một cách đáng tin cậy.
