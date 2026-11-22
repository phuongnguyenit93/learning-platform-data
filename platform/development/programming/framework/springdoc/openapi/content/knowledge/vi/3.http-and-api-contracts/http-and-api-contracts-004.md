# Mã trạng thái và ý nghĩa của phản hồi thành công hoặc thất bại

Khi một client gọi API, mã trạng thái HTTP là tín hiệu đầu tiên cho biết máy chủ đã xử lý request đến đâu. Mã này giúp client quyết định có thể dùng dữ liệu trả về, cần sửa request, phải xác thực lại, nên thử lại sau hay cần báo lỗi cho người dùng. Một hợp đồng API tốt vì thế phải mô tả rõ mã trạng thái, nội dung response và điều kiện phát sinh của từng trường hợp.

Trong ứng dụng Spring Boot, controller và tầng xử lý ngoại lệ quyết định phản hồi HTTP thực tế. **springdoc-openapi** giúp đưa các phản hồi đó vào đặc tả OpenAPI để người tích hợp nhìn thấy ngay trong Swagger UI hoặc dùng trong công cụ sinh client, kiểm thử và quản lý hợp đồng. Bài học này tập trung vào cách chọn đúng status code, thiết kế response nhất quán và mô tả chúng bằng OpenAPI.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt các nhóm mã trạng thái HTTP và hiểu ý nghĩa của những mã thường dùng trong REST API.
- Chọn status code phù hợp cho thao tác đọc, tạo, cập nhật, xóa và xử lý bất đồng bộ.
- Thiết kế phản hồi lỗi nhất quán, có thông tin đủ để client xử lý nhưng không làm lộ chi tiết nội bộ.
- Trả status code và header đúng cách từ Spring MVC.
- Mô tả các response thành công, lỗi, schema và header trong OpenAPI bằng springdoc-openapi.
- Kiểm tra hợp đồng tài liệu có khớp với phản hồi HTTP thật của ứng dụng hay không.

## 1. Status code nằm ở đâu trong HTTP response?

Một HTTP response gồm dòng trạng thái, các header và phần nội dung tùy trường hợp:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/products/42
Content-Type: application/json

{
  "id": 42,
  "name": "Bàn phím cơ",
  "price": 1250000
}
~~~

Trong ví dụ này:

- `201 Created` cho biết request đã tạo một tài nguyên mới.
- `Location` chỉ ra URI của tài nguyên vừa được tạo.
- `Content-Type` cho biết định dạng của phần nội dung.
- JSON là biểu diễn tài nguyên mà client có thể sử dụng.

Status code thuộc giao thức HTTP, không phải một trường tùy ý trong JSON. Ví dụ, response `200 OK` với body `{ "success": false }` vẫn được client và proxy hiểu là một HTTP request thành công. Cách biểu diễn như vậy làm client khó xử lý đúng lỗi, vì chúng phải đọc và diễn giải quy ước riêng trong body thay vì dựa vào giao thức.

Hãy dùng status code để diễn đạt kết quả ở cấp HTTP; dùng body để cung cấp dữ liệu hoặc giải thích chi tiết. Body có thể chứa mã lỗi nghiệp vụ như `PRODUCT_NOT_FOUND`, nhưng mã đó bổ sung cho status code chứ không thay thế nó.

## 2. Năm nhóm mã trạng thái

Mã trạng thái có ba chữ số. Chữ số đầu cho biết nhóm kết quả:

| Nhóm | Tên | Ý nghĩa tổng quát | Tình huống thường gặp |
|---|---|---|---|
| 1xx | Informational | Request đang được tiếp tục xử lý | Trao đổi ở mức giao thức |
| 2xx | Success | Request đã được tiếp nhận và xử lý thành công theo ngữ nghĩa của mã | Đọc, tạo, cập nhật hoặc chấp nhận công việc |
| 3xx | Redirection | Client cần thực hiện thêm hành động để hoàn tất request | Chuyển hướng hoặc dùng cache |
| 4xx | Client Error | Request có vấn đề hoặc không thể được đáp ứng trong ngữ cảnh hiện tại | Dữ liệu sai, thiếu xác thực, không đủ quyền |
| 5xx | Server Error | Máy chủ gặp lỗi khi thực hiện một request có vẻ hợp lệ | Lỗi ngoài dự kiến, dịch vụ phụ thuộc không sẵn sàng |

API REST thường gặp nhất các nhóm 2xx, 4xx và 5xx. Nhóm 3xx vẫn quan trọng khi API dùng cache, proxy hoặc chuyển hướng. Nhóm 1xx thường do máy chủ và client HTTP xử lý ở mức giao thức, ít khi cần khai báo như response nghiệp vụ của một endpoint.

Không nên suy luận rằng mọi mã trong cùng một nhóm đều có thể thay thế nhau. `200`, `201`, `202` và `204` đều là 2xx nhưng truyền đạt các trạng thái khác nhau; client có thể dựa vào khác biệt đó để lấy tài nguyên, theo dõi công việc hoặc bỏ qua việc đọc body.

## 3. Các mã thành công thường dùng

### 200 OK — Request đã được xử lý thành công

`200 OK` là mã phổ biến cho thao tác đọc dữ liệu. Máy chủ trả về biểu diễn của tài nguyên hoặc kết quả truy vấn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "name": "Bàn phím cơ"
}
~~~

Các tình huống thường dùng:

- `GET` trả về tài nguyên hoặc danh sách kết quả.
- `PUT` hoặc `PATCH` trả về biểu diễn mới sau khi cập nhật.
- `POST` thực hiện một hành động và trả về kết quả đã hoàn thành, khi không tạo tài nguyên mới theo ngữ nghĩa cần dùng `201`.

Nếu client cần dữ liệu sau thao tác, `200` thường đi kèm body có schema rõ ràng. Với kết quả truy vấn rỗng, có thể trả `200` cùng danh sách rỗng nếu endpoint có nghĩa là truy vấn tập hợp; không nên tự động biến mọi danh sách rỗng thành `404`.

### 201 Created — Đã tạo tài nguyên

Dùng `201 Created` khi request đã tạo một hoặc nhiều tài nguyên mới. Response nên cung cấp cách xác định tài nguyên vừa tạo, thường qua header `Location`, và có thể trả body chứa biểu diễn tài nguyên:

~~~http
HTTP/1.1 201 Created
Location: /api/products/42
Content-Type: application/json

{
  "id": 42,
  "name": "Bàn phím cơ"
}
~~~

`201` đặc biệt phù hợp với `POST /api/products`. Nếu API trả về `201` nhưng không cho client biết tài nguyên mới nằm ở đâu hoặc có mã định danh nào, việc tích hợp sẽ khó hơn. Header `Location` là lựa chọn rõ ràng; body có thể chứa cùng URI hoặc dữ liệu đại diện cho tài nguyên.

### 202 Accepted — Đã nhận yêu cầu, công việc chưa hoàn tất

Dùng `202 Accepted` khi máy chủ đã chấp nhận request để xử lý sau, nhưng chưa hoàn thành công việc tại thời điểm trả response. Ví dụ, client gửi yêu cầu xuất báo cáo lớn và máy chủ đưa công việc vào hàng đợi.

~~~http
HTTP/1.1 202 Accepted
Location: /api/jobs/8f31
Content-Type: application/json

{
  "jobId": "8f31",
  "status": "QUEUED",
  "statusUrl": "/api/jobs/8f31"
}
~~~

`202` không có nghĩa là thao tác chắc chắn sẽ thành công. Hợp đồng nên cho biết client theo dõi trạng thái ở đâu, có thể nhận callback hay không, thời hạn lưu kết quả và cách xử lý khi công việc thất bại. Nếu công việc đã hoàn thành ngay trong request, hãy chọn mã phản ánh kết quả cuối cùng thay vì dùng `202` cho mọi thao tác bất đồng bộ.

### 204 No Content — Thành công, không có body

Dùng `204 No Content` khi request thành công và client không cần nhận phần nội dung response. Ví dụ thường gặp là xóa tài nguyên hoặc cập nhật mà không trả biểu diễn mới:

~~~http
HTTP/1.1 204 No Content
~~~

Một response `204` không được chứa body. Nếu client cần nhận đối tượng sau cập nhật hoặc một thông điệp kết quả, hãy dùng `200` cùng body. Đừng khai báo schema JSON cho response `204` trong OpenAPI.

### Một số mã 2xx khác

- `203 Non-Authoritative Information`: thông tin response đã được biến đổi bởi proxy hoặc bên trung gian; ít dùng trong hợp đồng REST thông thường.
- `205 Reset Content`: báo client đặt lại nội dung hiển thị hoặc trạng thái nhập liệu; hiếm gặp trong API dịch vụ.
- `206 Partial Content`: trả một phần nội dung theo cơ chế range request, thường dùng khi tải tệp lớn.

Chỉ đưa những mã này vào hợp đồng khi endpoint thực sự hỗ trợ ngữ nghĩa tương ứng.

## 4. Các mã chuyển hướng và cache

Nhóm 3xx yêu cầu client thực hiện hành động tiếp theo hoặc sử dụng thông tin cache:

| Mã | Ý nghĩa | Lưu ý khi dùng |
|---|---|---|
| 301 Moved Permanently | Tài nguyên đã chuyển địa chỉ lâu dài | Client có thể cập nhật URI; hành vi với phương thức có thể khác theo client |
| 302 Found | Tạm thời chuyển sang URI khác | Một số client có thể đổi POST thành GET khi theo redirect |
| 303 See Other | Xem kết quả tại URI khác bằng GET | Hữu ích khi chuyển từ thao tác gửi dữ liệu sang trang kết quả |
| 304 Not Modified | Biểu diễn chưa thay đổi so với bản cache | Không trả body; client dùng bản đã lưu |
| 307 Temporary Redirect | Chuyển hướng tạm thời và giữ nguyên phương thức, body | Phù hợp khi phải bảo toàn semantics của request |
| 308 Permanent Redirect | Chuyển hướng lâu dài và giữ nguyên phương thức, body | Tương tự 301 nhưng bảo toàn phương thức |

Với API công khai, chuyển hướng cần được cân nhắc vì client, proxy và thư viện HTTP có chính sách theo redirect khác nhau. Nếu chuyển endpoint, hãy công bố URI mới và thời gian hỗ trợ URI cũ. Với cache, mô tả thêm các header liên quan như `ETag`, `Last-Modified`, `Cache-Control` và `If-None-Match` khi chúng ảnh hưởng đến cách client gọi API.

## 5. Các mã lỗi phía client (4xx)

Nhóm 4xx cho biết request không thể được đáp ứng trong trạng thái hiện tại. Body lỗi nên giải thích vấn đề theo cách client có thể hành động: sửa trường nào, xác thực ra sao, tài nguyên nào không tồn tại hoặc khi nào nên thử lại.

### 400 Bad Request — Request không hợp lệ

Dùng `400` cho request sai định dạng, thiếu cấu trúc bắt buộc hoặc có tham số không thể phân tích. Ví dụ:

- JSON không hợp lệ hoặc sai kiểu dữ liệu.
- Query parameter không chuyển đổi được sang kiểu mong đợi.
- Thiếu trường bắt buộc theo hợp đồng.
- Request không đáp ứng quy tắc validation mà API quy định trả về `400`.

Nên trả lỗi chỉ rõ trường hoặc vị trí gây lỗi. Không đưa nguyên stack trace hay dữ liệu nhạy cảm của request vào response.

### 401 Unauthorized — Chưa xác thực hợp lệ

Dùng `401` khi request thiếu thông tin xác thực, token hết hạn hoặc thông tin xác thực không hợp lệ. Tên chuẩn có chữ “Unauthorized”, nhưng ý nghĩa thực tế là client chưa được xác thực. Theo HTTP, response `401` phải có ít nhất một challenge trong header `WWW-Authenticate` để chỉ ra cơ chế xác thực được hỗ trợ.

Client có thể cần đăng nhập hoặc làm mới token rồi gửi lại request. Đừng dùng `401` chỉ vì người dùng đã đăng nhập nhưng không có quyền thực hiện hành động; trường hợp đó thường là `403`.

### 403 Forbidden — Đã xác thực nhưng không được phép

Dùng `403` khi máy chủ hiểu request và danh tính đã được xác thực, nhưng chính sách quyền không cho phép thao tác. Ví dụ người dùng có token hợp lệ nhưng thiếu quyền `product:write`.

Thông báo có thể nêu quyền cần có hoặc hướng liên hệ quản trị viên, nhưng không tiết lộ cấu trúc phân quyền nội bộ nếu điều đó tạo rủi ro. Một số hệ thống cố ý trả `404` thay cho `403` để không tiết lộ sự tồn tại của tài nguyên; nếu chọn chính sách đó, cần áp dụng nhất quán và mô tả hành vi công khai.

### 404 Not Found — Không tìm thấy tài nguyên

Dùng `404` khi URI không trỏ đến tài nguyên hiện có hoặc API không muốn tiết lộ rằng tài nguyên đó tồn tại. Ví dụ `GET /api/products/9999` khi mã sản phẩm không tồn tại.

Đối với endpoint danh sách, không tìm thấy phần tử phù hợp thường được biểu diễn bằng `200` cùng danh sách rỗng. `404` dành cho tài nguyên hoặc đường dẫn không tồn tại theo ngữ nghĩa của endpoint.

### 405 Method Not Allowed — Phương thức không được hỗ trợ

Dùng `405` khi đường dẫn tồn tại nhưng không hỗ trợ phương thức HTTP mà client gửi. Theo HTTP, response cần có header `Allow` liệt kê các phương thức được hỗ trợ, ví dụ `Allow: GET, HEAD`.

Trong Spring MVC, việc định tuyến request thường tự xử lý tình huống phương thức không được ánh xạ. Khi kiểm thử, hãy xác nhận status code và header thực tế qua cấu hình ứng dụng, proxy và bộ xử lý ngoại lệ.

### 406 Not Acceptable — Không có biểu diễn phù hợp

Dùng `406` khi máy chủ không thể tạo response phù hợp với các định dạng client yêu cầu trong header `Accept`. Ví dụ client chỉ chấp nhận XML trong khi API chỉ cung cấp JSON. Hãy mô tả các media type được hỗ trợ để client gửi `Accept` phù hợp.

### 409 Conflict — Xung đột với trạng thái hiện tại

Dùng `409` khi request hợp lệ về cấu trúc nhưng không thể hoàn tất vì xung đột với trạng thái tài nguyên hoặc dữ liệu. Ví dụ:

- Tạo người dùng với email đã tồn tại.
- Chuyển đơn hàng sang trạng thái không cho phép theo quy trình nghiệp vụ.
- Cập nhật gây xung đột với một thay đổi đồng thời.

Response nên giải thích xung đột và hướng xử lý có thể thực hiện. Với cập nhật đồng thời dùng ETag hoặc điều kiện HTTP, `412 Precondition Failed` có thể diễn đạt chính xác hơn khi điều kiện `If-Match` không còn đúng.

### 410 Gone — Tài nguyên đã bị loại bỏ

Dùng `410` khi máy chủ biết tài nguyên từng tồn tại nhưng đã bị loại bỏ vĩnh viễn. `404` phù hợp khi máy chủ không xác nhận được tài nguyên có tồn tại hay không; `410` cung cấp tín hiệu rõ hơn rằng client không nên tiếp tục tìm tài nguyên tại URI cũ.

### 412 Precondition Failed — Điều kiện request không thỏa

Dùng `412` khi một điều kiện được gửi qua header request không được đáp ứng. Trường hợp phổ biến là cập nhật có điều kiện với `If-Match` và ETag: client đọc phiên bản ETag cũ, một client khác cập nhật trước, nên máy chủ từ chối cập nhật để tránh ghi đè dữ liệu mới.

### 415 Unsupported Media Type — Định dạng nội dung không được hỗ trợ

Dùng `415` khi định dạng phần body không được endpoint hỗ trợ, thường do `Content-Type` không phù hợp. Ví dụ endpoint chỉ nhận `application/json` nhưng client gửi `text/plain`. Cần phân biệt `415` với `406`: một mã liên quan đến định dạng request gửi lên, mã còn lại liên quan đến định dạng response client chấp nhận.

### 422 Unprocessable Content — Nội dung hiểu được nhưng không thể xử lý

Dùng `422` khi cú pháp và định dạng request hợp lệ nhưng nội dung không thể xử lý theo ngữ nghĩa. Ví dụ JSON hợp lệ nhưng một tổ hợp giá trị vi phạm quy tắc nghiệp vụ phức tạp.

Một API có thể chọn `400` cho toàn bộ lỗi validation hoặc tách `400` cho request không phân tích được và `422` cho nội dung không thỏa điều kiện nghiệp vụ. Cả hai cách đều có thể dùng được nếu được quy định rõ, nhất quán và thể hiện trong tài liệu. Tránh dùng `400` và `422` lẫn lộn cho cùng một loại lỗi.

### 429 Too Many Requests — Vượt giới hạn tần suất

Dùng `429` khi client gửi quá nhiều request trong một khoảng thời gian. Response nên hướng dẫn thời điểm thử lại, thường bằng `Retry-After`, và có thể kèm thông tin giới hạn còn lại nếu chính sách cho phép.

Client không nên lặp request liên tục ngay sau `429`. Hãy chờ theo hướng dẫn, áp dụng exponential backoff và jitter nếu cần, đồng thời tôn trọng giới hạn dùng chung giữa các request.

## 6. Các mã lỗi phía máy chủ (5xx)

Nhóm 5xx cho biết máy chủ không thể hoàn tất một request có vẻ hợp lệ do lỗi trong quá trình xử lý hoặc phụ thuộc hệ thống.

| Mã | Ý nghĩa | Khi nào dùng |
|---|---|---|
| 500 Internal Server Error | Lỗi nội bộ ngoài dự kiến | Ngoại lệ không được xử lý hoặc lỗi không phân loại cụ thể |
| 501 Not Implemented | Máy chủ không hỗ trợ chức năng cần thiết | Chức năng hoặc phương thức chưa được triển khai |
| 502 Bad Gateway | Gateway nhận response không hợp lệ từ upstream | Reverse proxy hoặc gateway gọi dịch vụ phía sau |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng | Bảo trì, quá tải hoặc phụ thuộc tạm ngừng |
| 504 Gateway Timeout | Gateway không nhận được phản hồi kịp thời từ upstream | Dịch vụ phía sau vượt thời gian chờ |

`500` nên là mã dự phòng cho lỗi không dự kiến, không phải cách trả lời chung cho mọi trường hợp. Nếu client gửi dữ liệu sai thì dùng 4xx; nếu một dịch vụ phụ thuộc tạm thời không sẵn sàng, `503` hoặc `502` có thể mô tả đúng hơn tùy vai trò của máy chủ.

Với `503`, có thể gửi `Retry-After` nếu máy chủ biết thời điểm phù hợp để client thử lại. Không trả stack trace, tên lớp nội bộ, câu SQL, đường dẫn file, secret hoặc thông tin kết nối trong body lỗi. Ghi chi tiết kỹ thuật vào log nội bộ có kiểm soát và trả về mã tham chiếu để đội hỗ trợ tra cứu.

## 7. Chọn status code nhất quán cho từng thao tác REST

Bảng sau là điểm khởi đầu cho một API quản lý sản phẩm. Mã thực tế phụ thuộc nghiệp vụ, nhưng cần thống nhất trong toàn bộ dịch vụ:

| Thao tác | Thành công thường dùng | Lỗi thường gặp |
|---|---|---|
| `GET /api/products/{id}` | `200` | `400`, `401`, `403`, `404`, `500` |
| `GET /api/products` | `200`, kể cả danh sách rỗng | `400`, `401`, `403`, `500` |
| `POST /api/products` | `201` và `Location` | `400` hoặc `422`, `401`, `403`, `409`, `500` |
| `PUT /api/products/{id}` | `201` nếu tạo tài nguyên mới; `200` nếu trả representation sau cập nhật; `204` nếu không có body | `400`, `401`, `403`, `404`, `409`, `412`, `500` |
| `PATCH /api/products/{id}` | `200` hoặc `204` tùy response | `400`, `401`, `403`, `404`, `409`, `412`, `422`, `500` |
| `DELETE /api/products/{id}` | `204` nếu xóa xong và không trả body; có thể dùng `200` nếu trả kết quả | `401`, `403`, `404`, `409`, `500` |
| `POST /api/reports` tạo tác vụ dài | `202` và thông tin theo dõi | `400`, `401`, `403`, `429`, `500`, `503` |

Một số nguyên tắc lựa chọn:

- Dùng `201` khi tài nguyên mới đã được tạo, không chỉ vì HTTP method là `POST`.
- Dùng `202` khi công việc đã được chấp nhận nhưng kết quả chưa hoàn tất.
- Dùng `204` khi thành công và không có body.
- Dùng `404` cho tài nguyên không tồn tại; danh sách rỗng thường vẫn là `200`.
- Dùng `409` cho xung đột trạng thái nghiệp vụ; dùng `412` khi điều kiện HTTP như ETag không thỏa.
- Chọn một quy ước rõ ràng cho validation, chẳng hạn `400` hoặc `422`, rồi áp dụng đồng nhất.

Không có một bảng status code duy nhất đúng với mọi nghiệp vụ. Điều quan trọng là chọn theo semantics HTTP, giải thích các trường hợp đặc thù và duy trì cùng quy ước giữa các endpoint.

## 8. Thiết kế cấu trúc response lỗi

Một response lỗi tốt nên có cấu trúc ổn định. Client có thể đọc mã lỗi để quyết định hành động và đọc thông điệp để hiển thị hoặc ghi log. Ví dụ:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Dữ liệu gửi lên không hợp lệ",
  "details": {
    "name": "Tên sản phẩm không được để trống",
    "price": "Giá phải lớn hơn 0"
  },
  "timestamp": "2026-11-20T10:30:00Z",
  "path": "/api/products",
  "traceId": "01J..."
}
~~~

Ý nghĩa các trường:

| Trường | Mục đích |
|---|---|
| `code` | Mã lỗi ổn định để client xử lý theo chương trình |
| `message` | Giải thích ngắn gọn cho người dùng hoặc lập trình viên tích hợp |
| `details` | Chi tiết theo trường hoặc nguyên nhân, nếu có |
| `timestamp` | Thời điểm máy chủ ghi nhận lỗi |
| `path` | Đường dẫn request liên quan |
| `traceId` | Mã tương quan để tìm log nội bộ, nếu hệ thống có hỗ trợ |

Không nên buộc client phân tích câu chữ trong `message` để quyết định logic, vì thông điệp có thể được biên tập hoặc dịch. Hãy dùng `code` làm định danh ổn định. Với lỗi validation, trả danh sách hoặc map chi tiết theo trường giúp giao diện chỉ đúng vị trí cần sửa.

Body lỗi cần tránh:

- Stack trace, tên package, câu SQL, tên bảng hoặc đường dẫn nội bộ.
- Token, mật khẩu, thông tin xác thực, dữ liệu cá nhân không cần thiết.
- Nội dung request nguyên vẹn nếu request có thể chứa bí mật.
- Thông điệp khác cấu trúc giữa các endpoint khiến client phải viết nhiều nhánh xử lý.

### Dùng Problem Details

HTTP có định dạng Problem Details được chuẩn hóa trong RFC 9457. Các trường phổ biến gồm `type`, `title`, `status`, `detail` và `instance`; API có thể thêm extension member cho mã lỗi hoặc thông tin validation. Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Request không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường không đáp ứng quy tắc kiểm tra.",
  "instance": "/api/products",
  "code": "VALIDATION_FAILED",
  "errors": {
    "name": "Tên sản phẩm không được để trống"
  }
}
~~~

Problem Details thường được gửi với media type `application/problem+json`. Dùng một định dạng lỗi chuẩn giúp các client và công cụ chung có thể hiểu các trường cơ bản; extension như `code` và `errors` cung cấp ngữ nghĩa riêng của API. Nếu chọn Problem Details, hãy duy trì cách dùng nhất quán và mô tả chính xác media type cùng schema trong OpenAPI.

## 9. Trả status code từ Spring Boot

Trong Spring MVC, status code có thể được quyết định bằng `@ResponseStatus`, `ResponseEntity` hoặc exception handler. Chọn cách thể hiện phù hợp với độ linh hoạt cần có.

### Dùng @ResponseStatus cho kết quả cố định

Khi một endpoint luôn trả cùng status code, có thể khai báo trực tiếp:

~~~java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Spring trả `201 Created` cho kết quả của phương thức. Cách này ngắn gọn khi không cần tùy chỉnh header response. Nếu cần `Location`, cache header hoặc status phụ thuộc kết quả xử lý, hãy dùng `ResponseEntity`.

### Dùng ResponseEntity khi cần điều khiển response

`ResponseEntity<T>` cho phép xác định status, header và body:

~~~java
@PostMapping
public ResponseEntity<ProductResponse> create(
        @Valid @RequestBody CreateProductRequest request) {

    ProductResponse created = productService.create(request);
    URI location = URI.create("/api/products/" + created.id());

    return ResponseEntity.created(location).body(created);
}

@DeleteMapping("/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}

@PostMapping("/reports")
public ResponseEntity<JobResponse> createReport(@RequestBody ReportRequest request) {
    JobResponse job = reportService.submit(request);
    URI statusUri = URI.create("/api/jobs/" + job.id());

    return ResponseEntity.accepted()
        .location(statusUri)
        .body(job);
}
~~~

Đoạn mã minh họa cần các kiểu DTO, service và import phù hợp trong dự án. Các builder có ý nghĩa rõ ràng: `created(...)` tạo response 201 kèm Location, `noContent()` tạo 204 không body, và `accepted()` tạo 202.

### Xử lý lỗi tập trung bằng @RestControllerAdvice

Không nên lặp lại logic chuyển exception thành response trong mọi controller. Có thể tạo một `@RestControllerAdvice` để ánh xạ ngoại lệ thành status code và schema lỗi thống nhất:

~~~java
public record ApiError(
    String code,
    String message,
    Map<String, String> details,
    Instant timestamp
) {}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(ProductNotFoundException ex) {
        ApiError body = new ApiError(
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm",
            Map.of(),
            Instant.now()
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(DuplicateProductException.class)
    public ResponseEntity<ApiError> handleConflict(DuplicateProductException ex) {
        ApiError body = new ApiError(
            "PRODUCT_ALREADY_EXISTS",
            "Sản phẩm đã tồn tại",
            Map.of(),
            Instant.now()
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

Ví dụ đã lược bỏ import và định nghĩa exception để tập trung vào cách ánh xạ. Trong ứng dụng thật, handler validation cũng cần chuyển lỗi trường thành cấu trúc `details` phù hợp. Không nên trả trực tiếp `ex.getMessage()` cho mọi ngoại lệ vì nội dung có thể chứa chi tiết kỹ thuật hoặc dữ liệu nhạy cảm.

Với Spring Framework 6 trở lên, có thể cân nhắc `ProblemDetail` để trả Problem Details theo chuẩn. Ví dụ:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ProblemDetail handleNotFound(ProductNotFoundException ex) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy sản phẩm được yêu cầu."
    );
    problem.setTitle("Không tìm thấy tài nguyên");
    problem.setProperty("code", "PRODUCT_NOT_FOUND");
    return problem;
}
~~~

`ProblemDetail` có thể được dùng trực tiếp trong Spring MVC; kiểm tra cấu hình và phiên bản framework để bảo đảm media type cùng extension member được xuất đúng. Nếu dự án dùng Spring Boot 2 hoặc Spring Framework cũ, kiểu này có thể không có sẵn và cần một DTO lỗi riêng.

## 10. Mô tả status code trong OpenAPI bằng springdoc-openapi

OpenAPI mô tả response theo từng thao tác trong thuộc tính `responses`. Mỗi response có mã trạng thái hoặc khóa `default`, mô tả bắt buộc (`description`) và có thể chứa:

- `content`: media type và schema của body.
- `headers`: header được trả về, ví dụ `Location`, `Retry-After` hoặc `ETag`.
- `links`: quan hệ đến thao tác khác trong tài liệu.

Trong Spring, các annotation của OpenAPI thường dùng để mô tả phản hồi:

| Annotation | Vai trò |
|---|---|
| `@ApiResponse` | Mô tả một status code và response tương ứng |
| `@ApiResponses` | Gom nhiều `@ApiResponse` trên một thao tác |
| `@Content` | Khai báo media type và nội dung response |
| `@Schema` | Chỉ định schema của body |
| `@ExampleObject` | Cung cấp ví dụ payload |
| `@Header` | Mô tả header response |

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(summary = "Lấy sản phẩm theo mã")
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "401",
            description = "Thiếu hoặc không hợp lệ thông tin xác thực"
        )
    })
    public ProductResponse getById(@PathVariable long id) {
        return productService.getById(id);
    }

    @PostMapping
    @Operation(summary = "Tạo sản phẩm")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Đã tạo sản phẩm",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Dữ liệu request không hợp lệ",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        ),
        @ApiResponse(
            responseCode = "409",
            description = "Sản phẩm đã tồn tại",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    })
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse created = productService.create(request);
        URI location = URI.create("/api/products/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}
~~~

Đây là ví dụ minh họa; cần thay `ProductResponse`, `ApiError`, DTO và service bằng kiểu của ứng dụng. Annotation `@ApiResponse` mô tả hợp đồng, còn `ResponseEntity` và exception handler mới quyết định response HTTP thực tế. Khai báo `404` trong OpenAPI không tự khiến controller trả `404`; ngược lại, handler trả `404` nhưng không có mô tả phù hợp sẽ khiến tài liệu thiếu thông tin.

### Mô tả response không có body

Với endpoint xóa trả `204`, khai báo response và bỏ `content`:

~~~java
@DeleteMapping("/{id}")
@ApiResponse(responseCode = "204", description = "Đã xóa sản phẩm")
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy sản phẩm",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
public ResponseEntity<Void> delete(@PathVariable long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

Response `204` không khai báo schema body. Swagger UI có thể hiển thị rằng thao tác thành công nhưng không có nội dung trả về.

### Mô tả header response

Với `201 Created`, có thể khai báo header `Location` để người dùng hợp đồng biết URI tài nguyên mới được trả ở đâu. Annotation `@Header` nằm trong package `io.swagger.v3.oas.annotations.headers`:

~~~java
@ApiResponse(
    responseCode = "201",
    description = "Đã tạo tài nguyên",
    headers = @Header(
        name = "Location",
        description = "URI của tài nguyên vừa được tạo",
        schema = @Schema(type = "string", format = "uri")
    ),
    content = @Content(
        schema = @Schema(implementation = ProductResponse.class)
    )
)
~~~

Tương tự, với `429` hoặc `503`, hãy mô tả `Retry-After` nếu API thực sự trả header đó. Không khai báo header chỉ vì muốn client sử dụng; mã nguồn phải tạo ra header tương ứng.

### Mô tả Problem Details

Nếu API dùng Problem Details, hãy chỉ rõ media type và schema response:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Request không hợp lệ",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
~~~

Nếu API có các extension như `code` hoặc `errors`, hãy dùng schema riêng hoặc cơ chế tùy biến OpenAPI để thể hiện các trường bổ sung. Không giả định rằng schema lớp `ProblemDetail` mặc định đã mô tả đầy đủ mọi extension mà ứng dụng thêm vào.

### Tái sử dụng mô tả lỗi

Nhiều endpoint có chung các phản hồi `400`, `401`, `403` hoặc `500`. Có thể định nghĩa response tái sử dụng trong `components.responses` rồi tham chiếu từ các thao tác. Khi dùng annotation, có thể dùng `@ApiResponse(ref = "...")` theo cú pháp tham chiếu OpenAPI phù hợp; hoặc dùng bean `OpenApiCustomizer` để bổ sung response chung cho các operation.

Việc thêm response dùng chung cần phản ánh đúng phạm vi endpoint. Không gắn `401` cho endpoint công khai không yêu cầu xác thực, cũng không gắn `404` cho mọi endpoint nếu thao tác đó không có khả năng phát sinh tình huống này. Tài liệu càng nhiều response không liên quan thì client càng khó hiểu hợp đồng thật.

## 11. Phân biệt status code, schema và security trong tài liệu

Ba lớp thông tin này bổ sung cho nhau:

| Thành phần | Câu hỏi mà nó trả lời |
|---|---|
| Status code | Request đã thành công, bị từ chối hay gặp lỗi ở đâu? |
| Response schema | Body có cấu trúc và kiểu dữ liệu nào? |
| Security requirement | Client cần xác thực bằng cách nào để gọi thao tác? |

Ví dụ, một endpoint cần JWT có thể khai báo `security` requirement, mô tả `401` cho trường hợp thiếu hoặc sai token, `403` cho trường hợp không đủ quyền và `200` cho kết quả thành công. Schema của `200` là `ProductResponse`, trong khi schema lỗi có thể là `ApiError` hoặc `ProblemDetail`.

Đừng nhầm `401` và `403` với nhau trong tài liệu. Đừng mô tả lỗi xác thực chỉ bằng một đoạn text không có status code. Đồng thời, security scheme của OpenAPI chỉ mô tả yêu cầu đối với client; Spring Security vẫn phải thực thi xác thực và phân quyền trong ứng dụng.

## 12. Client nên xử lý và thử lại như thế nào?

Status code là đầu vào để client chọn hành động. Một số quy tắc thực tế:

- Với `2xx`, đọc body theo schema đã công bố; riêng `204` thì không cố phân tích JSON.
- Với `400` hoặc `422`, hiển thị lỗi validation và cho phép người dùng sửa dữ liệu.
- Với `401`, thực hiện quy trình đăng nhập hoặc làm mới token nếu được hỗ trợ; tránh lặp vô hạn khi thông tin xác thực không còn hợp lệ.
- Với `403`, thông báo không đủ quyền hoặc hướng người dùng đến quản trị viên; không gửi lại cùng request liên tục.
- Với `404`, kiểm tra URI hoặc cập nhật trạng thái giao diện nếu tài nguyên đã bị xóa.
- Với `409` hoặc `412`, tải lại trạng thái mới nhất và yêu cầu người dùng giải quyết xung đột khi cần.
- Với `429` hoặc `503`, tuân thủ `Retry-After`; nếu không có header, áp dụng backoff có giới hạn.
- Với `500`, chỉ thử lại khi thao tác có thể lặp an toàn hoặc có cơ chế idempotency phù hợp.

HTTP phân biệt phương thức an toàn và idempotent. `GET`, `HEAD`, `OPTIONS` và `TRACE` được định nghĩa là safe (TRACE thường bị tắt trên các API ứng dụng); `PUT` và `DELETE` là idempotent theo semantics HTTP; `POST` thường không idempotent. Một request idempotent có thể được gửi lại mà không làm thay đổi kết quả dự kiến ngoài lần đầu, nhưng điều đó không có nghĩa mọi lần gửi lại đều miễn phí hoặc không có side effect ngoài hợp đồng.

Đối với thao tác tạo tài nguyên qua `POST`, nếu client có thể mất kết nối sau khi máy chủ đã tạo thành công nhưng trước khi nhận response, gửi lại có thể tạo bản ghi trùng. Nếu nghiệp vụ yêu cầu retry an toàn, hãy thiết kế idempotency key hoặc cơ chế tra cứu kết quả trước khi thử lại. Ghi rõ hành vi này trong hợp đồng.

## 13. Kiểm tra response thật và tài liệu OpenAPI

Một endpoint có thể trả đúng status code ở local nhưng tài liệu vẫn mô tả sai. Ngược lại, Swagger UI có thể hiển thị đủ các response nhưng code không thực sự tạo ra chúng. Hãy kiểm tra cả hai phía.

### Kiểm tra bằng HTTP client

Ví dụ tạo tài nguyên:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Bàn phím cơ","price":1250000}'
~~~

Kiểm tra status `201`, header `Location`, `Content-Type` và body. Sau đó thử request thiếu tên, giá không hợp lệ, token không hợp lệ và mã sản phẩm không tồn tại để xác nhận các response lỗi. `curl -i` hiển thị cả status line lẫn header nên phù hợp để kiểm tra hợp đồng HTTP.

### Kiểm tra bằng Spring MockMvc

Với ứng dụng Spring MVC, MockMvc có thể xác minh status code, header và body:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void createReturns201AndLocation() throws Exception {
        given(productService.create(any()))
            .willReturn(new ProductResponse(42L, "Bàn phím cơ", 1250000));

        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Bàn phím cơ","price":1250000}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", endsWith("/api/products/42")))
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

Ví dụ dùng cú pháp Java text block và các matcher của Spring Test cùng Mockito; cần bổ sung import và cấu hình test phù hợp với phiên bản Spring Boot của dự án. Có thể viết thêm test cho `204` không body, `404` với schema lỗi, `409` do xung đột và `400` do validation.

### Kiểm tra đặc tả được sinh ra

Mở `/v3/api-docs` hoặc endpoint nhóm tương ứng và kiểm tra phần `paths`. Một operation nên có các response cần thiết:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'
        '404':
          description: Không tìm thấy sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        '401':
          description: Thiếu hoặc không hợp lệ thông tin xác thực
~~~

Đây là đoạn YAML rút gọn minh họa cấu trúc response; tài liệu thực tế có thể chứa thêm `operationId`, parameters, security và components. Dùng OpenAPI validator hoặc linter để phát hiện lỗi cấu trúc, sau đó kiểm tra nội dung quan trọng bằng test tự động hoặc review.

Một ma trận đối chiếu hữu ích:

| Kiểm tra | Trong mã nguồn | Trong OpenAPI | Khi gọi thật |
|---|---|---|---|
| Tạo thành công | `ResponseEntity.created(...)` | `201` và schema thành công | `201`, Location và body đúng |
| Không tìm thấy | Exception handler trả `404` | `404` và schema lỗi | `404` cùng payload lỗi |
| Xóa thành công | `noContent()` | `204`, không content | `204`, không body |
| Quá giới hạn | Bộ giới hạn trả `429` | `429` và Retry-After nếu có | `429` cùng header đã công bố |

Nếu một ô không khớp, hãy sửa implementation hoặc hợp đồng theo hành vi được thống nhất, sau đó chạy lại kiểm tra. Không để tài liệu hứa một status code mà ứng dụng không trả, hoặc ứng dụng trả một loại lỗi mà client không được hướng dẫn cách xử lý.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Luôn trả `200` và đưa lỗi vào body | Client, gateway và monitoring hiểu nhầm request thành công | Dùng status code đúng semantics và schema lỗi ổn định |
| Trả `201` nhưng không có cách xác định tài nguyên mới | Client khó lấy hoặc liên kết tài nguyên | Trả `Location` và/hoặc representation có định danh |
| Trả `204` kèm JSON | Vi phạm semantics của response không nội dung | Dùng `200` nếu cần body; nếu `204`, bỏ body |
| Dùng `404` cho danh sách rỗng | Client hiểu nhầm endpoint hoặc tài nguyên không tồn tại | Trả `200` với danh sách rỗng khi collection tồn tại |
| Dùng `401` cho mọi lỗi quyền | Client không biết cần đăng nhập hay xin thêm quyền | Phân biệt xác thực `401` và phân quyền `403` |
| Dùng `500` cho dữ liệu đầu vào sai | Client khó sửa request và hệ thống ghi nhận sai loại lỗi | Trả `400` hoặc `422` theo quy ước |
| Tài liệu có response nhưng code không tạo ra | Client tích hợp theo hợp đồng sai | Test status, header và body thực tế |
| Code trả lỗi nhưng OpenAPI không mô tả | Swagger UI và client generator thiếu thông tin | Bổ sung `@ApiResponse` hoặc customizer phù hợp |
| Trả stack trace trong body | Rò rỉ cấu trúc và thông tin nội bộ | Dùng error code, thông điệp an toàn và trace ID |
| Thử lại mọi lỗi ngay lập tức | Tăng tải và có thể tạo dữ liệu trùng | Xử lý theo status, idempotency và backoff |

## 15. Bài thực hành

Xây dựng hoặc chọn một API quản lý sản phẩm có các endpoint đọc, tạo, cập nhật và xóa. Hoàn thành lần lượt:

1. Lập bảng status code cho từng endpoint, gồm thành công và các lỗi dự kiến.
2. Quyết định quy ước validation dùng `400`, `422` hay cả hai; ghi rõ điều kiện.
3. Tạo schema lỗi chung với `code`, `message`, `details` và thời điểm phát sinh.
4. Dùng `ResponseEntity` để trả `201` cùng `Location`, `204` không body và `202` cho một tác vụ nền.
5. Tạo `@RestControllerAdvice` ánh xạ lỗi không tìm thấy thành `404`, lỗi trùng dữ liệu thành `409` và lỗi validation theo quy ước.
6. Dùng springdoc-openapi khai báo response cho các mã quan trọng cùng schema và header.
7. Mở Swagger UI, xác nhận response hiển thị đúng; tải `/v3/api-docs` và chạy validator.
8. Viết test xác minh status, header và body cho cả thành công lẫn thất bại.
9. Gửi request thật bằng HTTP client để đối chiếu kết quả với đặc tả.
10. Thử một trường hợp `429` hoặc `503` và mô tả cách client nên chờ trước khi retry.

### Tiêu chí hoàn thành

- [ ] Mỗi endpoint có status code thành công phản ánh đúng kết quả thực tế.
- [ ] `201`, `202` và `204` được dùng đúng semantics; response `204` không có body.
- [ ] Các lỗi phổ biến được phân biệt hợp lý giữa `400`, `401`, `403`, `404`, `409`, `422` và `5xx`.
- [ ] Body lỗi có schema ổn định và không tiết lộ chi tiết nội bộ.
- [ ] Header quan trọng như `Location`, `WWW-Authenticate` hoặc `Retry-After` được mô tả khi API sử dụng.
- [ ] OpenAPI liệt kê đúng response, media type và schema cho từng endpoint.
- [ ] Test xác minh status code, header và body; kết quả khớp với tài liệu.
- [ ] Client có hướng dẫn rõ cho retry, xác thực lại và xử lý xung đột.

## Tiếp tục học

Sau bài này, hãy kết hợp status code với mô tả request/response schema, chuẩn hóa lỗi bằng Problem Details, khai báo security requirement và kiểm thử hợp đồng trong CI. Khi một endpoint thay đổi hành vi, hãy cập nhật đồng thời controller hoặc exception handler, đặc tả OpenAPI và test để người dùng API luôn nhận được cùng một thông điệp từ cả ba nơi.
