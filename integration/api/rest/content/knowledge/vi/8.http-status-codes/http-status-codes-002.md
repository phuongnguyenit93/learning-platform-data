# 200, 201, 202, 204 cho các kết quả thành công khác nhau

## 1. Mục tiêu: trả mã thành công đúng với trạng thái tài nguyên

Trong một **REST API**, các mã HTTP thuộc nhóm **2xx** đều biểu thị yêu cầu đã được xử lý thành công ở mức nào đó, nhưng **200 OK**, **201 Created**, **202 Accepted** và **204 No Content** không có cùng ý nghĩa. Chọn đúng mã giúp ứng dụng khách biết liệu có tài nguyên mới, có dữ liệu cần đọc, công việc mới được nhận để xử lý tiếp, hay thao tác đã hoàn tất mà không có nội dung trả về.

Đây là bài học thuộc chương **Mã trạng thái** của module **INTEGRATION_API_REST**. Trong quá trình thiết kế API dựa trên resource, URI và phương thức HTTP, status code là một phần của **hợp đồng API**, cùng với headers, response body, định dạng lỗi, OpenAPI, xác thực, phân quyền, cache và quy tắc retry/idempotency. Các ví dụ sử dụng Java/Spring MVC; nguyên tắc áp dụng tương tự cho công nghệ khác.

Sau bài này, người học có thể:

- Giải thích được **kết quả thực sự** mà mỗi mã 200, 201, 202, 204 cam kết với client.
- Chọn mã cho GET, POST, PUT, PATCH, DELETE theo tình huống cụ thể, không dựa máy móc vào tên phương thức.
- Thiết kế đúng header **Location**, **ETag**, **Cache-Control**, **Retry-After** khi phù hợp.
- Xây dựng hợp đồng API cho tác vụ xử lý bất đồng bộ và resource theo dõi trạng thái.
- Triển khai response trong Spring và kiểm thử cả status, headers, body lẫn tác dụng nghiệp vụ.
- Tránh lỗi phổ biến như trả 200 cho mọi trường hợp, trả 201 khi chưa tạo tài nguyên, hoặc trả 204 kèm JSON.

**Giới hạn của bài:** chỉ phân tích bốn mã thành công trên. Các mã khác như 400, 401, 403, 404, 409, 412, 422, 429 và 5xx vẫn là phần thiết yếu khi thiết kế lỗi, nhưng không được dùng để thay cho thành công.

## 2. Bản đồ nhanh của bốn mã

| Mã | Tên chuẩn | Ý nghĩa chính | Body của response | Dấu hiệu quan trọng |
| --- | --- | --- | --- | --- |
| **200** | OK | Yêu cầu **đã thành công**; ý nghĩa nội dung tùy phương thức | Thường trả representation; với HEAD không có response body | Không ngầm khẳng định đã tạo tài nguyên mới |
| **201** | Created | Yêu cầu **đã hoàn tất** và tạo **một hoặc nhiều tài nguyên mới** | Có thể chứa representation hoặc mô tả/kết quả việc tạo | **Location** nên chỉ URI tài nguyên chính mới tạo khi thích hợp |
| **202** | Accepted | Yêu cầu **đã được chấp nhận để xử lý**, nhưng xử lý **chưa hoàn tất** | Nên giải thích trạng thái hiện tại và cách kiểm tra tiến độ | Không bảo đảm công việc sau đó sẽ thành công |
| **204** | No Content | Yêu cầu **đã được xử lý thành công**, server **không gửi nội dung response** | **Không có body** | Phù hợp khi client không cần representation trả về |

Hai câu hỏi phân định nhanh:

1. **Yêu cầu đã hoàn tất ở thời điểm gửi phản hồi chưa?** Nếu mới được nhận vào hàng đợi và còn xử lý sau, xem xét **202**. Nếu đã hoàn tất, xem **200 / 201 / 204**.
2. **Nếu đã hoàn tất, có tài nguyên mới không; client có cần representation không?** Tạo xong tài nguyên mới → **201**. Thành công kèm thông tin kết quả → **200**. Thành công nhưng không có nội dung trả về → **204**.

Đây là quy tắc định hướng; HTTP semantics còn phụ thuộc phương thức và hợp đồng tài nguyên cụ thể. **Một POST không nhất thiết phải trả 201, và một DELETE không bắt buộc luôn trả 204.**

## 3. 200 OK: thành công và có kết quả để client sử dụng

### 3.1. Khi nào sử dụng 200?

**200 OK** cho biết yêu cầu đã thành công. Trong REST API thường dùng khi:

- **GET** đọc một tài nguyên hoặc danh sách thành công, bao gồm danh sách rỗng nhưng vẫn có representation.
- **POST** thực hiện thao tác thành công nhưng không tạo tài nguyên mới, hoặc trả kết quả xử lý đã hoàn tất.
- **PUT/PATCH** cập nhật tài nguyên hiện có và muốn trả representation mới.
- **DELETE** hoàn tất và trả thông tin kết quả theo hợp đồng đã thiết kế (trong khi **204** thích hợp nếu không trả body).

Ví dụ đọc một đơn hàng:

~~~http
GET /orders/ord_123 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "ord_123",
  "status": "confirmed",
  "totalAmount": 125000,
  "currency": "VND"
}
~~~

**Lý do chọn 200:** tài nguyên đã tồn tại và server trả representation của nó. Status **200** không nói rằng server vừa tạo mới đơn hàng.

Ví dụ danh sách chưa có phần tử:

~~~http
GET /orders?status=pending&page=0&size=20 HTTP/1.1
Host: api.example.test
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0
}
~~~

Danh sách rỗng không tự động là lỗi **404**. Endpoint danh sách có thể vẫn hợp lệ, và bộ lọc có thể không khớp mục nào. **204** ở đây không sai trong mọi thiết kế nhưng khiến client phải xử lý một dạng response khác thay vì cùng schema danh sách; **200 với mảng rỗng** thường dễ dùng hơn cho hợp đồng phân trang nhất quán.

### 3.2. 200 không đồng nghĩa response bắt buộc là JSON

HTTP xác định ý nghĩa nội dung **200** theo phương thức. **GET** thường chứa representation của tài nguyên; **HEAD** trả cùng lớp thông tin metadata liên quan đến GET nhưng **không có body**. Vì vậy, không được lập quy tắc tuyệt đối “200 luôn có JSON”. Hợp đồng API cần mô tả phương thức, media type và body cụ thể.

Nếu một **GET** thành công mà resource không có trường dữ liệu tùy chọn, có thể trả **200** với representation phù hợp hoặc **204** nếu API cố ý không trả nội dung. Hãy chọn nhất quán, tránh khiến client phải đoán cấu trúc.

### 3.3. 200 với thao tác cập nhật

~~~http
PATCH /profiles/u_42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json

{"displayName":"Lan"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "profile-v7"

{
  "id": "u_42",
  "displayName": "Lan",
  "version": 7
}
~~~

API đã cập nhật xong và cung cấp trạng thái mới để ứng dụng hiển thị. Nếu không cần trả representation, có thể chọn **204** thay cho **200**, tùy hợp đồng.

## 4. 201 Created: thao tác đã tạo xong tài nguyên

### 4.1. Điều kiện dùng 201

**201 Created** có nghĩa yêu cầu **đã được hoàn tất** và tạo một hoặc nhiều tài nguyên mới. Trong REST API, trường hợp điển hình là **POST** đến collection để tạo một resource:

~~~http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Idempotency-Key: order-create-8d1

{
  "productId": "sku_10",
  "quantity": 2
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /orders/ord_123
Content-Type: application/json
ETag: "order-v1"

{
  "id": "ord_123",
  "productId": "sku_10",
  "quantity": 2,
  "status": "created"
}
~~~

Thông điệp hợp đồng:

- Server đã **tạo xong resource đơn hàng** có ID **ord_123**.
- **Location: /orders/ord_123** cho biết URI chính của resource mới, để client có thể gọi GET khi cần.
- Response body **có thể** chứa representation của resource vừa tạo. Body không bắt buộc luôn có; tính cần thiết phụ thuộc API.
- **201** xác nhận việc tạo resource **đã hoàn tất**; không nhất thiết mọi nghiệp vụ liên quan (giao hàng, thanh toán, gửi email) cũng đã hoàn tất.

**Phân biệt resource và quy trình nghiệp vụ:** Có thể tạo xong một đơn hàng ở trạng thái **pending_payment** và trả **201**, dù thanh toán sẽ diễn ra sau. Nếu bản thân việc **tạo đơn** còn đang chờ xử lý trong queue và chưa xác định đơn đã tồn tại, **202** có thể phù hợp hơn. Điều quyết định là server cam kết **điều gì đã hoàn tất**.

### 4.2. Location và Content-Location không giống nhau

Đối với **201**, **Location** xác định URI của tài nguyên chính vừa tạo nếu header được cung cấp. Nếu không có Location, HTTP dùng URI đích của request để nhận diện tài nguyên chính theo ngữ nghĩa thông điệp, nhưng với **POST collection**, URI đích thường là collection chứ không phải resource mới. Vì vậy, thực hành API nên **trả Location rõ ràng** khi client cần truy cập resource mới.

**Content-Location** là header có mục đích khác: liên quan đến định danh của representation được gửi trong body. Không nên dùng Content-Location như một bản sao mù quáng của Location nếu không hiểu ngữ nghĩa.

URI trong **Location** có thể tương đối (như **/orders/ord_123**) hoặc tuyệt đối (như **https://api.example.test/orders/ord_123**) theo HTTP. Khi triển khai qua reverse proxy, cần bảo đảm hostname/scheme công khai chính xác nếu sinh URI tuyệt đối từ request.

### 4.3. PUT có thể trả 201

Không chỉ POST mới tạo resource. Nếu client chọn URI và **PUT** thành công khi resource trước đó chưa tồn tại, kết quả hợp lý là **201**:

~~~http
PUT /user-preferences/u_42 HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"theme":"dark"}
~~~

~~~http
HTTP/1.1 201 Created
Location: /user-preferences/u_42
~~~

Nếu resource đã tồn tại và được thay thế/cập nhật bằng PUT, server có thể trả **200** với representation hoặc **204** nếu không có body. Phương thức **PUT** có tính **idempotent** về trạng thái mong muốn; cùng request lặp lại có thể cho status lần đầu **201** và lần sau **200/204**, mà vẫn không vi phạm idempotency.

### 4.4. 201 không phải mã “server đã nhận request”

Chỉ đưa lệnh tạo vào hàng đợi chưa chứng minh resource đã được tạo. Nếu server trả **201** trước khi có resource thực sự và sau đó job thất bại, client nhận một cam kết sai. Trong trường hợp xử lý bất đồng bộ, hãy xác định rõ **resource nào được tạo đồng bộ** (nếu có) và phần công việc nào còn dang dở; có thể sử dụng **202** với resource trạng thái.

## 5. 202 Accepted: đã nhận để xử lý, chưa xác nhận thành công cuối cùng

### 5.1. Khi nào dùng 202?

**202 Accepted** cho biết server **đã chấp nhận yêu cầu để xử lý**, nhưng **chưa hoàn tất** công việc đó. Hành động có thể được thực hiện sau, thất bại hoặc không được thực hiện nếu điều kiện thay đổi; vì vậy status 202 **không bảo đảm kết quả cuối cùng thành công**.

Phù hợp với công việc như:

- Tạo báo cáo lớn, xuất dữ liệu, xử lý video hoặc ảnh.
- Import một tập tin có hàng trăm nghìn dòng.
- Khởi chạy một workflow có nhiều bước và thời gian chờ dài.
- Gửi yêu cầu xử lý nền qua queue với tracking ID rõ ràng.

Ví dụ yêu cầu tạo báo cáo:

~~~http
POST /reports HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: report-2026-11-18-01

{
  "type": "sales",
  "fromDate": "2026-11-01",
  "toDate": "2026-11-17"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op_900
Retry-After: 5
Cache-Control: no-store
Content-Type: application/json

{
  "operationId": "op_900",
  "status": "queued",
  "statusUrl": "/operations/op_900"
}
~~~

Ở đây **Location** đến resource trạng thái là **quy ước thiết kế API hữu ích**, không phải yêu cầu bắt buộc áp cho mọi response 202. **Retry-After: 5** là gợi ý thời gian trước khi thử kiểm tra lại; client vẫn cần chiến lược backoff có giới hạn. Body nên mô tả trạng thái và cách biết kết quả cuối cùng.

### 5.2. Theo dõi trạng thái qua một resource

Sau khi nhận 202, client lấy trạng thái:

~~~http
GET /operations/op_900 HTTP/1.1
Host: api.example.test
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "operationId": "op_900",
  "status": "running",
  "progressPercent": 45
}
~~~

Khi hoàn tất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "op_900",
  "status": "succeeded",
  "resultUrl": "/reports/rpt_77"
}
~~~

Sau đó:

~~~http
GET /reports/rpt_77 HTTP/1.1
Host: api.example.test
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "rpt_77",
  "status": "ready",
  "downloadUrl": "/reports/rpt_77/file"
}
~~~

**Vì sao GET trạng thái trả 200 thay vì tiếp tục trả 202?** Vì request GET **đã thành công khi đọc resource trạng thái hiện tại**, dù công việc mà resource đó mô tả vẫn đang chạy. API cũng có thể dùng lựa chọn khác theo hợp đồng, nhưng cách trên tách rõ **status của HTTP request hiện tại** và **business status của job**.

HTTP không có cơ chế tự thay đổi status của response 202 thành 201 hoặc 500 vào một thời điểm sau khi response đã gửi xong. Client phải truy vấn trạng thái, nhận webhook có xác thực hoặc dùng cơ chế cập nhật được quy định riêng.

### 5.3. Trạng thái cuối phải bao gồm thất bại

Ví dụ job có thể về trạng thái **failed**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "op_900",
  "status": "failed",
  "error": {
    "code": "REPORT_SOURCE_UNAVAILABLE",
    "message": "Không thể đọc nguồn dữ liệu để tạo báo cáo."
  }
}
~~~

Ở đây **GET /operations/op_900** vẫn thành công (**200**) vì client đọc được resource trạng thái. Lỗi **bên trong job** được biểu diễn bằng **status: failed** và thông tin lỗi; không nhất thiết là một HTTP 500 cho request GET đã thành công.

Hợp đồng nên có các trạng thái tối thiểu **queued**, **running**, **succeeded**, **failed** và có thể thêm **cancelled**, thời gian tạo/cập nhật, kết quả, lỗi, thời hạn giữ job. Cần phân quyền để người dùng A không đọc được job của người dùng B.

### 5.4. Khi nào không nên trả 202?

Nếu có thể biết ngay request không hợp lệ hoặc caller không có quyền, hãy trả mã lỗi thích hợp (**400 / 401 / 403 / 422**, theo tình huống), thay vì che giấu lỗi chắc chắn bằng **202**. Chấp nhận một job nên gắn với **việc lưu bền vững thông tin đã nhận** theo yêu cầu hệ thống, không chỉ gọi một hàm enqueue rồi trả 202 mà không biết lệnh có được giữ lại hay không.

Nếu backend đã hoàn tất thao tác và resource mới đã tồn tại, **201** có thể diễn đạt chính xác hơn. Nếu đã tính xong kết quả mà không tạo resource, **200** có thể phù hợp.

## 6. 204 No Content: đã làm xong, không có nội dung response

### 6.1. Khi nào dùng 204?

**204 No Content** nghĩa là server đã xử lý thành công yêu cầu và **không có nội dung bổ sung để gửi trong response body**. Thường dùng khi:

- **DELETE** xóa xong một resource và client không cần representation.
- **PUT/PATCH** đã cập nhật xong, client đã biết trạng thái cần hiển thị.
- Một thao tác POST đã hoàn tất, không tạo resource mới và không có dữ liệu cần trả về, khi hợp đồng cho phép.

Ví dụ xóa một resource:

~~~http
DELETE /bookmarks/bm_123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 204 No Content
~~~

Response kết thúc sau headers, **không có JSON rỗng, không có chuỗi và không có body**. Nếu thao tác xóa **chưa hoàn tất** mà mới được nhận vào queue, hãy xem xét **202**.

Một ví dụ cập nhật xong mà không cần representation:

~~~http
PATCH /profiles/u_42 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json

{"displayName":"Mai"}
~~~

~~~http
HTTP/1.1 204 No Content
ETag: "profile-v8"
~~~

**ETag** có thể giúp client biết phiên bản sau khi cập nhật, mặc dù response không chứa representation. Client có thể dùng một GET riêng khi cần đọc bản đầy đủ.

### 6.2. Những điều không được làm với 204

- **Không gửi JSON** như dấu ngoặc nhọn rỗng **{}**, một mảng rỗng hay thông báo “success”.
- Không thiết lập response như thể có nội dung JSON cần parse; các client được phép coi body là **không tồn tại**.
- Không giả định **204 nghĩa là resource không tồn tại**; đó là mã **thành công**, không phải **404 Not Found**.
- Không dùng 204 để giấu một job **đang xử lý** nếu client cần biết khi nào thực sự hoàn thành.

Nếu client cần nhận thông tin **deletedAt**, số bản ghi đã xử lý, phiên bản mới hoặc thông tin nghiệp vụ khác, **200 với body** có thể phù hợp hơn.

### 6.3. DELETE và tính idempotent

DELETE được định nghĩa là phương thức **idempotent** đối với **tác dụng mong muốn trên server**, không có nghĩa mọi lần gọi phải trả cùng status. Lần đầu xóa có thể trả **204**; lần hai, khi resource đã không còn, API có thể trả **404** hoặc **204** theo hợp đồng và chính sách tránh lộ thông tin. Quan trọng là việc gọi lặp không tạo thêm tác dụng phụ không mong muốn, như thu phí hoặc gửi thông báo trùng.

## 7. Ma trận chọn mã theo phương thức và kết quả

| Request | Tình huống | Mã phù hợp | Lý do |
| --- | --- | --- | --- |
| **GET /orders/123** | Đọc đơn thành công | **200** | Đã trả representation của resource |
| **GET /orders?status=paid** | Danh sách hợp lệ nhưng rỗng | **200** | Collection vẫn có representation rỗng |
| **POST /orders** | Đơn mới đã được tạo | **201** | Resource mới có URI |
| **POST /orders** | Lệnh tạo đơn mới được nhận để xử lý sau | **202** | Chưa cam kết hoàn tất việc tạo |
| **POST /orders/123/price-check** | Tính toán hoàn tất và trả giá dự kiến; không tạo resource | **200** | Có kết quả xử lý |
| **POST /reports** | Job xuất báo cáo còn chạy nền | **202** | Có thể trả resource trạng thái |
| **PUT /settings/u42** | URI chưa tồn tại, tạo mới thành công | **201** | Resource mới đã được tạo |
| **PUT /settings/u42** | Thay thế nội dung resource hiện có, trả bản mới | **200** | Hoàn tất, có body |
| **PUT /settings/u42** | Thay thế xong, không trả body | **204** | Hoàn tất, không có body |
| **PATCH /profiles/u42** | Cập nhật xong, trả bản mới | **200** | Client cần trạng thái sau cập nhật |
| **PATCH /profiles/u42** | Cập nhật xong, không trả body | **204** | Không có representation cần gửi |
| **DELETE /bookmarks/123** | Đã xóa hoàn tất, không trả body | **204** | Thành công, không có nội dung |
| **DELETE /exports/123** | Yêu cầu xóa được nhận, sẽ dọn dữ liệu nền | **202** | Công việc chưa hoàn tất |

Không nên dùng ma trận này như một công thức không có ngoại lệ. Hợp đồng API cần nói rõ **resource gì tồn tại sau request**, **điều gì đã hoàn tất** và **body/headers nào client được kỳ vọng**.

## 8. Trình tự quyết định trong thiết kế API

~~~mermaid
flowchart TD
    A[Request đã qua kiểm tra và được chấp nhận về mặt hợp đồng] --> B{Xử lý đã hoàn tất?}
    B -->|Chưa| C[202 Accepted: trả trạng thái / đường theo dõi job]
    B -->|Rồi| D{Có tài nguyên mới đã tạo?}
    D -->|Có| E[201 Created: URI resource mới, body tùy chọn]
    D -->|Không| F{Có kết quả / representation cần trả?}
    F -->|Có| G[200 OK: representation hoặc kết quả]
    F -->|Không| H[204 No Content: không có body]
~~~

Sơ đồ áp dụng cho các ví dụ CRUD và job phổ biến, không thay thế việc hiểu semantics của từng phương thức. Ví dụ **HEAD** thành công có thể là **200** dù không trả body vì đó là quy tắc phương thức, không phải cứ không có body thì phải dùng **204**.

Khi thiết kế, hãy viết một **câu cam kết** cho mỗi response:

- **200:** “Yêu cầu này thành công; đây là kết quả hiện tại”.
- **201:** “Tài nguyên này đã được tạo; có thể truy cập qua URI này”.
- **202:** “Chúng tôi đã nhận công việc; đây là cách theo dõi nó”.
- **204:** “Thao tác này đã hoàn tất; không có nội dung bổ sung”.

## 9. Headers, cache và idempotency liên quan

### 9.1. Location

- Đặc biệt hữu ích với **201** để client tìm tài nguyên mới.
- Với **202**, có thể trỏ tới **operation/status resource** theo quy ước API.
- Không tự coi Location là bằng chứng job đã hoàn tất; **202** và **201** có cam kết khác nhau.

### 9.2. ETag và cập nhật có điều kiện

**ETag** định danh phiên bản của representation và có thể hỗ trợ tránh ghi đè khi hai client cập nhật cùng tài nguyên. Ví dụ:

~~~http
GET /profiles/u_42 HTTP/1.1
Host: api.example.test
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "profile-v7"

{"id":"u_42","displayName":"Lan"}
~~~

Client gửi cập nhật có điều kiện:

~~~http
PATCH /profiles/u_42 HTTP/1.1
Host: api.example.test
If-Match: "profile-v7"
Content-Type: application/merge-patch+json

{"displayName":"Mai"}
~~~

Nếu ETag còn phù hợp và server cập nhật xong, trả **200** hoặc **204**. Nếu ETag không khớp và precondition thất bại, mã thích hợp là **412 Precondition Failed**. Vì thế mã 2xx phải đi cùng chính sách kiểm soát đồng thời, không chỉ thiết kế JSON đẹp.

### 9.3. Cache-Control

Không mặc định mọi response **200** đều nên được cache. Các HTTP cache có những quy tắc riêng về phương thức, mã và metadata; một số response thành công, đặc biệt **200** và **204**, có thể được phép cache theo quy tắc heuristic nếu điều kiện phù hợp.

Với dữ liệu cá nhân, token, operation status hoặc thông tin thay đổi nhanh, nên thiết kế chỉ thị cache rõ ràng, ví dụ:

~~~http
Cache-Control: private, no-store
~~~

Với dữ liệu công khai và ít thay đổi, có thể dùng **Cache-Control**, **ETag** và conditional GET theo hợp đồng. Không chọn cache chỉ dựa vào việc response là 200 hay 204; xác định tính nhạy cảm, phạm vi người dùng, tính mới và cách invalidation.

### 9.4. Idempotency khi client retry

Một timeout khiến client không biết POST ban đầu đã được xử lý hay chưa. Nếu gửi lại và server tạo đơn mới lần nữa, có thể phát sinh đơn trùng. Với những API tạo resource hoặc tạo job quan trọng, có thể hỗ trợ **Idempotency-Key** như một phần hợp đồng ứng dụng:

1. Client tạo khóa ổn định cho một **ý định nghiệp vụ**.
2. Server lưu khóa, phạm vi người dùng và fingerprint request cùng kết quả xử lý theo chính sách được thiết kế.
3. Nếu client retry cùng khóa và payload hợp lệ, server trả lại kết quả tương ứng hoặc cho theo dõi cùng operation, tránh tạo thêm tác dụng phụ.
4. Nếu cùng khóa nhưng payload khác, server trả lỗi xung đột theo hợp đồng; cần có TTL/lifecycle và ràng buộc an toàn khi lưu khóa.

Với POST tạo đơn đã thành công, lần retry có thể được trả cùng **201**, **Location** và body theo chính sách idempotency của API; với job nhận xử lý, có thể trả cùng **202** và operation ID. Không coi idempotency là tính chất mặc định của POST.

### 9.5. Retry-After cho công việc nền

**Retry-After** có thể được dùng khi trả **202** để gợi ý thời gian kiểm tra trạng thái, nhưng không phải cam kết job sẽ hoàn thành đúng thời gian đó. Client nên giới hạn số lần poll, tăng khoảng đợi khi cần và tôn trọng giới hạn tốc độ API.

## 10. Triển khai minh họa với Java và Spring MVC

Đoạn mã dưới đây tập trung vào **hợp đồng HTTP và cách trả status**. Các interface/service và DTO là ví dụ; kiểm tra validation, phân quyền, transaction, lưu idempotency key và xử lý exception cần được hoàn thiện trong ứng dụng thực.

### 10.1. Tạo, đọc, cập nhật và xóa đơn hàng

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    // Resource mới được tạo và lưu thành công => 201
    @PostMapping
    public ResponseEntity<OrderDto> create(@Valid @RequestBody CreateOrderRequest request) {
        OrderDto created = service.create(request);
        URI location = URI.create("/orders/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    // Đọc resource hiện hữu => 200
    @GetMapping("/{id}")
    public ResponseEntity<OrderDto> get(@PathVariable String id) {
        return ResponseEntity.ok(service.get(id));
    }

    // Cập nhật xong và muốn trả trạng thái mới => 200
    @PatchMapping("/{id}")
    public ResponseEntity<OrderDto> update(
            @PathVariable String id,
            @Valid @RequestBody UpdateOrderRequest request) {
        OrderDto updated = service.update(id, request);
        return ResponseEntity.ok(updated);
    }

    // Xóa xong, không có nội dung trả về => 204
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

**Những ràng buộc phải bổ sung trong triển khai thật:** xác thực và phân quyền theo đơn hàng; validate số lượng và loại dữ liệu; xử lý không tìm thấy tài nguyên; transaction khi tạo; chính sách idempotency; cập nhật có điều kiện khi cần; ánh xạ lỗi nghiệp vụ thành status 4xx/5xx phù hợp. Tên phương thức **create** không tự làm cho **201** đúng: service phải thực sự tạo resource trước khi trả.

**Lưu ý với PUT tạo mới:** nếu dùng endpoint PUT cho một resource do client định danh, service cần cho biết tài nguyên **vừa được tạo** hay **đã tồn tại** để controller chọn **201** hoặc **200/204** đúng ngữ nghĩa.

### 10.2. Nhận yêu cầu tạo báo cáo để xử lý nền

~~~java
@RestController
@RequestMapping("/reports")
public class ReportController {
    private final ReportJobService service;

    public ReportController(ReportJobService service) {
        this.service = service;
    }

    // Job được ghi nhận bền vững; xử lý chính sẽ diễn ra sau => 202
    @PostMapping
    public ResponseEntity<OperationAcceptedDto> requestReport(
            @Valid @RequestBody CreateReportRequest request) {
        OperationDto operation = service.enqueue(request);
        URI statusUri = URI.create("/operations/" + operation.id());

        return ResponseEntity.accepted()
                .location(statusUri)
                .header(HttpHeaders.RETRY_AFTER, "5")
                .body(new OperationAcceptedDto(operation.id(), "queued", statusUri.toString()));
    }
}
~~~

Resource trạng thái ở endpoint riêng:

~~~java
@RestController
@RequestMapping("/operations")
public class OperationController {
    private final ReportJobService service;

    public OperationController(ReportJobService service) {
        this.service = service;
    }

    // GET hiện trạng công việc đã thành công => 200,
    // dù job vẫn queued/running hoặc đã failed.
    @GetMapping("/{id}")
    public ResponseEntity<OperationDto> getStatus(@PathVariable String id) {
        return ResponseEntity.ok(service.getOperation(id));
    }
}
~~~

Dòng **service.enqueue(request)** cần tạo/lưu đủ trạng thái để client có thể theo dõi job; không được trả **202** nếu chính quá trình tiếp nhận đã thất bại. Một job có thể kết thúc **failed** về nghiệp vụ, và client quan sát điều đó bằng GET operation.

### 10.3. DTO và service contract minh họa

~~~java
public record CreateOrderRequest(String productId, int quantity) {}
public record UpdateOrderRequest(String status) {}
public record OrderDto(String id, String status) {}

public interface OrderService {
    OrderDto create(CreateOrderRequest request);
    OrderDto get(String id);
    OrderDto update(String id, UpdateOrderRequest request);
    void delete(String id);
}

public record CreateReportRequest(String type, String fromDate, String toDate) {}
public record OperationAcceptedDto(String operationId, String status, String statusUrl) {}
public record OperationDto(String id, String status, String resultUrl) {}

public interface ReportJobService {
    OperationDto enqueue(CreateReportRequest request);
    OperationDto getOperation(String id);
}
~~~

Các record minh họa tối giản, **không phản ánh đầy đủ validation, security và state machine**. Nếu service trả resource chưa tạo/không tồn tại hoặc có race condition giữa queue và database, controller có status đúng trên giấy nhưng hợp đồng API vẫn sai.

## 11. Kiểm thử hợp đồng HTTP

Chỉ assert “request không ném exception” là chưa đủ. Hãy kiểm tra **status**, **headers**, **body**, và **side effects**. Với Spring, có thể dùng MockMvc cho controller và integration test cho transaction, database và queue.

### 11.1. Các kiểm thử tối thiểu

| Kịch bản | Status dự kiến | Điều cần kiểm chứng |
| --- | --- | --- |
| GET đơn hàng hợp lệ | **200** | Content-Type và body đúng resource/ID |
| GET danh sách không có phần tử | **200** | Schema phân trang, items = [] |
| POST tạo đơn hoàn tất | **201** | Location đúng, resource truy xuất được, không nhân đôi nếu retry cùng idempotency key |
| PUT tạo resource mới tại URI cụ thể | **201** | Resource được tạo và Location đúng nếu cung cấp |
| PUT/PATCH cập nhật và trả representation | **200** | Body phản ánh trạng thái đã lưu |
| DELETE hoàn tất, không trả body | **204** | Response không có body; resource không còn theo hợp đồng |
| PATCH cập nhật hoàn tất, không trả body | **204** | Body rỗng; ETag được cập nhật nếu hợp đồng dùng |
| POST xử lý báo cáo nền | **202** | Operation ID và status URL hợp lệ; job được lưu bền vững |
| GET trạng thái job đang chạy | **200** | Body có status = running; quyền đọc đúng |
| Job xử lý thất bại | GET operation **200** | Body có status = failed và error rõ ràng |
| Cập nhật dùng ETag cũ | **412** | Không ghi đè dữ liệu mới |
| Payload sai hoặc token không có quyền | **4xx** tương ứng | Không trả 202/201 giả tạo |

### 11.2. Ví dụ assert MockMvc

~~~java
// Minh họa các assertion khi đã cấu hình mockMvc và service cho từng test.

mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"productId\":\"sku_10\",\"quantity\":2}"))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", "/orders/ord_123"))
    .andExpect(jsonPath("$.id").value("ord_123"));

mockMvc.perform(get("/orders/ord_123"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value("ord_123"));

mockMvc.perform(delete("/orders/ord_123"))
    .andExpect(status().isNoContent())
    .andExpect(content().string(""));

mockMvc.perform(post("/reports")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"type\":\"sales\",\"fromDate\":\"2026-11-01\","
                + "\"toDate\":\"2026-11-17\"}"))
    .andExpect(status().isAccepted())
    .andExpect(header().string("Location", "/operations/op_900"))
    .andExpect(jsonPath("$.status").value("queued"));
~~~

Bài test controller này chứng minh **cấu trúc HTTP response** với service được giả lập. Để chứng minh hành vi thật cần integration test: sau **201** GET được resource, sau **202** job tồn tại và chuyển trạng thái, retry không tạo trùng, sau **204** kết quả đã được lưu và response không có nội dung.

### 11.3. Ví dụ OpenAPI 3

Một endpoint tạo resource và một endpoint nhận job nên có response contract **khác nhau**:

~~~yaml
paths:
  /orders:
    post:
      summary: Tạo đơn hàng đồng bộ
      responses:
        "201":
          description: Đơn hàng đã được tạo
          headers:
            Location:
              description: URI của đơn hàng mới
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "400":
          description: Payload không hợp lệ
  /reports:
    post:
      summary: Yêu cầu tạo báo cáo bất đồng bộ
      responses:
        "202":
          description: Công việc đã được chấp nhận, chưa hoàn tất
          headers:
            Location:
              description: URI theo dõi operation
              schema:
                type: string
            Retry-After:
              description: Gợi ý số giây trước khi kiểm tra lại
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OperationAccepted"
~~~

Khi khai báo response **204** trong OpenAPI, **không khai báo body content** cho status đó. Với **200**, chọn schema theo representation thực tế. Ngoài 2xx, hợp đồng cần khai báo các lỗi quan trọng kèm định dạng lỗi thống nhất, ví dụ theo **Problem Details for HTTP APIs** khi phù hợp.

## 12. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Luôn trả **200** cho mọi thành công | Client không biết có resource mới hay job còn đang chạy | Phân biệt hoàn tất, tạo mới, nhận xử lý và không có body |
| Trả **201** ngay khi enqueue tạo resource | Resource có thể chưa tồn tại; client GET theo Location bị lỗi | Dùng **202** với operation nếu việc tạo chưa hoàn tất |
| Trả **202** để che lỗi xác thực hoặc payload | Client tin job đã được nhận dù chắc chắn không hợp lệ | Validate/authz trước, trả 4xx phù hợp |
| Trả **204** rồi gửi body **{}** | Vi phạm semantics No Content; client/proxy có thể xử lý khác | Không ghi body; dùng 200 nếu cần trả representation |
| Trả **201** mà không có URI ổn định cho resource mới | Client khó truy xuất hoặc kiểm tra tài nguyên | Thiết kế resource ID và Location rõ ràng |
| Dùng **200** với body status = "error" khi request đã thất bại | Client không dựa vào HTTP semantics để phân biệt lỗi | Dùng mã lỗi thực sự cho request thất bại; riêng job status là resource cần hiểu đúng |
| Trả **202** nhưng không có cách theo dõi | Client không biết khi nào hoàn tất hoặc thất bại | Cấp operation ID, status URL, trạng thái và expiration |
| Dùng **204** cho DELETE chỉ mới xếp hàng | Client tưởng xóa đã hoàn tất | Dùng 202 khi chờ xử lý; 204 khi đã hoàn tất |
| Không có idempotency cho POST quan trọng | Timeout + retry có thể tạo trùng | Thiết kế idempotency key, transaction và kiểm thử retry |
| Đặt Cache-Control tùy tiện trên tài nguyên cá nhân | Dữ liệu nhạy cảm bị cache không phù hợp | Chọn cache policy theo độ nhạy, quyền truy cập và freshness |

## 13. Bài tập thực hành

Hãy thiết kế REST API cho hệ thống thư viện điện tử có các resource **books**, **bookmarks** và **exports**. Các trường hợp sau có thể cần status khác nhau:

1. GET danh sách sách với bộ lọc, không có kết quả.
2. POST tạo sách mới, đã lưu trong DB và được cấp ID.
3. POST yêu cầu xuất dữ liệu lịch sử mượn sách, cần khoảng 2 phút xử lý.
4. GET trạng thái export khi job vẫn đang chạy.
5. GET trạng thái export khi job thất bại vì thiếu dữ liệu đầu vào.
6. PATCH đổi tiêu đề sách, trả lại representation sau cập nhật.
7. PATCH đổi tiêu đề sách, không muốn trả body.
8. DELETE bookmark đã hoàn tất ngay.
9. DELETE export cũ, chỉ mới ghi nhận yêu cầu xóa vào queue.
10. PUT đặt cấu hình đọc tại URI do client chọn: lần đầu resource chưa tồn tại, lần hai đã tồn tại.

### Yêu cầu đầu ra

Với mỗi tình huống, hãy viết:

- Phương thức và URI theo resource.
- Status **200 / 201 / 202 / 204** phù hợp, cùng lời giải thích về **điều server đã cam kết**; nếu có trường hợp thất bại thì chọn mã lỗi tương ứng.
- Những headers cần thiết, đặc biệt Location, ETag, Retry-After và Cache-Control khi phù hợp.
- Ví dụ response body, hoặc ghi rõ **không có body**.
- Một test kiểm chứng status, header, payload và hành vi phía server.

Với endpoint export bất đồng bộ, mô tả chu trình **queued → running → succeeded/failed**, resource trạng thái, cách client poll/backoff, thời hạn tồn tại và quyền đọc operation theo user. Với POST tạo sách, mô tả retry khi client mất kết nối sau khi server đã tạo resource và cách dùng **Idempotency-Key**.

### Gợi ý đáp án về mã

| Tình huống | Mã chính | Giải thích ngắn |
| --- | --- | --- |
| 1 | **200** | Collection hợp lệ và trả danh sách rỗng |
| 2 | **201** | Tài nguyên sách mới đã tạo, có Location |
| 3 | **202** | Nhận việc xuất dữ liệu, xử lý tiếp sau |
| 4 | **200** | Đọc resource operation thành công, dù job đang chạy |
| 5 | **200** cho GET operation | Trạng thái nghiệp vụ failed nằm trong body; khác với lỗi HTTP của lần GET |
| 6 | **200** | Cập nhật xong, trả representation |
| 7 | **204** | Cập nhật xong, không trả body |
| 8 | **204** | Xóa xong, không trả body |
| 9 | **202** | Chỉ nhận yêu cầu xóa, chưa hoàn tất |
| 10 | **201** khi tạo mới, **200/204** khi thay thế | PUT có thể tạo mới hoặc cập nhật, tùy resource đã tồn tại |

**Điều kiện đạt:** Không đánh đồng thành công của **HTTP request** với thành công của **công việc bất đồng bộ**; không trả **201** khi resource chưa được tạo; không gửi body trên **204**; và có kiểm thử idempotency/đọc lại resource cho các tình huống cần chứng minh trạng thái.

## 14. Checklist review và tài liệu tham khảo

Trước khi phê duyệt một endpoint có 2xx, hỏi:

1. **Resource nào** được đọc, tạo, cập nhật, xóa hoặc bắt đầu xử lý?
2. Tại thời điểm trả response, việc đó **đã hoàn tất hay chỉ được chấp nhận**?
3. Nếu có tài nguyên mới, **201 + Location** có chỉ đúng URI resource không?
4. Nếu còn xử lý nền, **202** có cung cấp operation ID, status URL, trạng thái và cơ chế theo dõi không?
5. Nếu trả **204**, response có thực sự **không có body**?
6. Nếu trả **200**, representation/schema và media type có đúng với hợp đồng không?
7. Hệ thống có xử lý **retry**, mất kết nối, idempotency, race condition và concurrency không?
8. Có kiểm tra **authorization**, dữ liệu nhạy cảm và cache trước khi cho client truy xuất resource/job không?
9. OpenAPI có khai báo đúng status, headers, schema và các lỗi không?
10. Test có kiểm tra trạng thái **thực tế phía server**, không chỉ HTTP status, hay chưa?

Để kiểm chứng ngữ nghĩa tiêu chuẩn, tham khảo **RFC 9110 (HTTP Semantics)**: các mục mô tả **200 OK**, **201 Created**, **202 Accepted**, **204 No Content**; đồng thời đối chiếu hợp đồng OpenAPI và tài liệu Spring Framework phù hợp với phiên bản đang dùng.

Điểm mấu chốt: **200** nói “đã thành công và đây là kết quả”; **201** nói “đã tạo tài nguyên mới”; **202** nói “đã nhận để xử lý, chưa hoàn tất”; **204** nói “đã hoàn tất, không có nội dung trả về”. Chọn mã theo **cam kết thực tế của server**, để client có thể phản ứng đúng mà không phải đoán.
