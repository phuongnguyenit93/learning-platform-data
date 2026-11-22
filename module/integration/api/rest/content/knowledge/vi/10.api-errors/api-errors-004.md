# application/problem+json và thương lượng biểu diễn lỗi

## 1. Vì sao REST API cần một biểu diễn lỗi thống nhất?

Một API quản lý đơn hàng có thể từ chối yêu cầu vì JSON không hợp lệ, thiếu quyền, không tìm thấy đơn, xung đột trạng thái hay hệ thống tạm quá tải. Mã trạng thái HTTP giúp client nhận biết **nhóm kết quả**, nhưng thường không đủ để biết **loại lỗi cụ thể, cách sửa và cách truy vết**. Hai endpoint trả cùng **400 Bad Request** có thể đại diện cho hai nguyên nhân rất khác nhau.

Nếu mỗi nhóm phát triển tự chọn body lỗi, client sẽ gặp những dạng không thống nhất:

~~~json
{"error": "Invalid input"}
~~~

~~~json
{"success": false, "code": 1008, "message": "Email sai"}
~~~

~~~json
{"errors": [{"field": "email", "msg": "required"}]}
~~~

Để client xử lý được tất cả, nhóm phải duy trì nhiều cách phân tích và ánh xạ khác nhau. Khi thay đổi phiên bản API hoặc thêm gateway, tính không nhất quán còn khó kiểm soát hơn.

**Problem Details for HTTP APIs (RFC 9457)** cung cấp một mô hình biểu diễn lỗi chuẩn hóa. Media type JSON của mô hình là **application/problem+json**. Trong module **INTEGRATION_API_REST**, bài học này kết nối **resource, URI, phương thức và mã trạng thái HTTP** với hợp đồng dữ liệu, xác thực/phân quyền, idempotency, OpenAPI và kiểm thử API bằng Java/Spring.

Sau bài học, bạn có thể:

1. Thiết kế response theo **RFC 9457**, hiểu từng trường chuẩn và trường mở rộng.
2. Phân biệt **HTTP status**, **Content-Type** và **Accept** khi client/server thương lượng biểu diễn lỗi.
3. Quyết định cách trả **application/problem+json**, **406 Not Acceptable**, **415 Unsupported Media Type** và các lỗi nghiệp vụ khác.
4. Thiết kế **problem type ổn định**, lỗi validation có cấu trúc và mã nội bộ phục vụ client.
5. Áp dụng mô hình với **Spring Framework 6 / Spring Boot 3**, tài liệu OpenAPI và kiểm thử hợp đồng.
6. Tránh rò rỉ dữ liệu nhạy cảm, lỗi caching, mất header HTTP quan trọng và xử lý sai khi qua proxy.

## 2. RFC 9457 định nghĩa Problem Details như thế nào?

**Problem Details** là mô hình mô tả một vấn đề trong phản hồi HTTP. RFC 9457 thay thế RFC 7807 và chuẩn hóa hai media type:

- **application/problem+json**: biểu diễn JSON.
- **application/problem+xml**: biểu diễn XML theo quy định của đặc tả.

Trong REST API sử dụng JSON, **application/problem+json** thường là lựa chọn thuận tiện. Đây là media type **khác application/json**; hậu tố **+json** cho biết nội dung theo cú pháp JSON, nhưng không đồng nghĩa mọi cơ chế thương lượng sẽ coi hai media type là một.

Phản hồi ví dụ khi đơn hàng đã được giao không cho phép hủy:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-18ab7

{
  "type": "https://api.example.test/problems/order-not-cancellable",
  "title": "Order Cannot Be Cancelled",
  "status": 409,
  "detail": "Đơn hàng đã được bàn giao cho đơn vị vận chuyển.",
  "instance": "/problems/occurrences/req-18ab7",
  "code": "ORDER_NOT_CANCELLABLE",
  "orderStatus": "SHIPPED"
}
~~~

Trong ví dụ, **409** là HTTP status thực tế; body dùng các trường chuẩn **type, title, status, detail, instance** và hai trường mở rộng **code, orderStatus**. Tên miền, request ID và dữ liệu đơn hàng chỉ là ví dụ.

### Năm trường chuẩn

| Trường | Ý nghĩa | Nguyên tắc sử dụng |
|---|---|---|
| **type** | URI reference định danh **loại vấn đề** | Ổn định giữa các lần lỗi cùng loại; có thể liên kết tài liệu |
| **title** | Tiêu đề ngắn, dễ đọc về loại vấn đề | Nhìn chung ổn định theo type, có thể bản địa hóa |
| **status** | Mã trạng thái HTTP dạng số trong body | Chỉ là thông tin hỗ trợ; **HTTP status line mới có thẩm quyền** |
| **detail** | Diễn giải cụ thể cho **lần xảy ra lỗi này** | Dành cho người đọc; không dùng làm khóa xử lý nghiệp vụ |
| **instance** | URI reference định danh **lần xảy ra vấn đề** | Có thể dùng để liên hệ hỗ trợ hoặc truy vết, tránh lộ bí mật |

**Điểm chính xác của đặc tả:** Các trường trên **không phải tất cả đều bắt buộc** đối với mọi Problem Details. Khi thiếu **type**, giá trị mặc định về ngữ nghĩa là **about:blank**. Một tổ chức vẫn có thể quy định trong **hợp đồng riêng** rằng mọi lỗi JSON phải chứa type, title, status để client dễ dự đoán; đó là quy ước của API, không phải bắt buộc phổ quát của RFC 9457.

### Status trong body là thông tin phụ trợ

Nếu server trả **HTTP/1.1 409 Conflict** nhưng body lại chứa **"status": 400**, hai tín hiệu mâu thuẫn. Client nên dùng **HTTP status thực tế** để quyết định lớp lỗi; phía server phải sửa để hai giá trị khớp. RFC cho phép trường status tồn tại vì nội dung đôi khi được lưu hoặc chuyển qua các hệ thống tách khỏi status line, nhưng nó **không thay thế** status code của phản hồi HTTP.

### type và instance khác nhau ở cấp định danh

~~~text
type     = https://api.example.test/problems/order-not-cancellable
           └── Cùng một loại lỗi, xuất hiện ở nhiều yêu cầu

instance = /problems/occurrences/req-18ab7
           └── Một lần xảy ra cụ thể, có thể dùng để truy vết
~~~

Không sinh một **type mới cho mỗi request**, vì như vậy client không thể phân loại theo loại lỗi ổn định. Nếu muốn đánh dấu từng incident, dùng **instance**, **requestId** hoặc **traceId** tùy chính sách. URI của type không bắt buộc phải truy cập được bằng HTTP, nhưng một URL dẫn tới tài liệu giải thích và cách khắc phục thường hữu ích cho người tích hợp.

## 3. about:blank và problem type riêng

Khi chỉ cần dùng ý nghĩa HTTP chung, **about:blank** là loại vấn đề mặc định:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên được yêu cầu."
}
~~~

Với **about:blank**, title thông thường nên tương ứng với reason phrase của status HTTP (có thể bản địa hóa). Không nên đặt mọi lỗi nghiệp vụ thành about:blank rồi yêu cầu client phân biệt bằng nội dung **detail**, vì detail có thể thay đổi hoặc được dịch.

Khi client cần ứng xử khác nhau, khai báo một **problem type cụ thể**:

| Tình huống | Problem type gợi ý | Client có thể làm gì? |
|---|---|---|
| Đơn không thể hủy ở trạng thái hiện tại | **/problems/order-not-cancellable** | Cập nhật UI, không retry hủy vô hạn |
| Mã giảm giá hết hiệu lực | **/problems/coupon-expired** | Yêu cầu chọn mã khác |
| Có lỗi xác thực đầu vào | **/problems/validation-failed** | Hiển thị lỗi tương ứng từng trường |
| Vượt hạn mức gọi API | **/problems/rate-limit-exceeded** | Giảm tốc độ, xem **Retry-After** |
| Phiên bản resource đã thay đổi | **/problems/version-conflict** | Đọc lại ETag và cân nhắc cập nhật |

Các URI trong bảng là **quy ước thiết kế**; API có thể chọn tiền tố và tên khác. Điều quan trọng là **ổn định, có tài liệu, được version hóa khi thay đổi ý nghĩa**. Không dùng cùng một type cho những lỗi mà client cần xử lý khác nhau, cũng không tạo hàng trăm type cho những khác biệt chỉ có giá trị diễn giải.

### Tài liệu cho một problem type nên có gì?

Một trang loại lỗi hữu ích có thể mô tả:

- **Ý nghĩa nghiệp vụ**, điều kiện phát sinh và status HTTP thường dùng.
- Các **extension member** và schema/đơn vị của từng trường.
- Hành động client được phép làm: sửa payload, xác thực lại, đọc resource, đợi hay liên hệ hỗ trợ.
- Khả năng **retry an toàn** và yêu cầu idempotency nếu thao tác có side effect.
- Ví dụ request/response, giới hạn tiết lộ thông tin và thay đổi tương thích giữa các phiên bản.

Client nên rẽ nhánh trên **type** hoặc một extension **code** đã công bố, không dựa trên việc tìm chuỗi tiếng Việt/tiếng Anh trong detail.

## 4. Extension members và lỗi validation nhiều trường

RFC 9457 cho phép bổ sung các **extension members** ngoài năm trường chuẩn. Chúng có thể là chuỗi, số, object hoặc mảng có cấu trúc phù hợp với dạng JSON. Cần tài liệu hóa tên, giá trị và ý nghĩa của trường mở rộng cho từng problem type.

Ví dụ tạo tài khoản với hai trường không hợp lệ:

~~~http
POST /api/customers HTTP/1.1
Host: api.example.test
Accept: application/problem+json
Content-Type: application/json

{"email":"not-an-email","age":-2}
~~~

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Validation Failed",
  "status": 422,
  "detail": "Có 2 trường dữ liệu không đáp ứng quy tắc nghiệp vụ.",
  "instance": "/problems/occurrences/req-18ab8",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "#/email",
      "code": "EMAIL_FORMAT",
      "detail": "Email không đúng định dạng."
    },
    {
      "pointer": "#/age",
      "code": "MIN_VALUE",
      "detail": "Tuổi phải từ 0 trở lên."
    }
  ]
}
~~~

**errors là một extension do API lựa chọn, không phải trường bắt buộc của RFC 9457.** Có thể dùng tên **invalidParams**, **violations** hoặc tên khác nếu đã thống nhất schema. Trong ví dụ, **pointer** theo cách biểu diễn JSON Pointer dưới dạng fragment chỉ vị trí trong document đầu vào; cần quy định xử lý mảng, trường nested và trường không nằm trong JSON body như query/header.

### Vì sao một response chứa nhiều lỗi vẫn chỉ có một Problem Details?

Status **422** và problem type **validation-failed** mô tả **vấn đề tổng thể của request**, còn mảng errors giải thích từng vi phạm. Cách này giúp một phản hồi không phải bọc hàng chục Problem Details rời rạc rồi buộc client tự suy ra status chung.

Đối với JSON sai cú pháp, server có thể trả **400 Bad Request**, và có thể **không thể xác định JSON Pointer** vì tài liệu không phân tích cú pháp thành công. Với dữ liệu đúng cú pháp nhưng sai quy tắc nghiệp vụ, **422** có thể hợp lý nếu đó là contract; một số API sử dụng **400** cho cả validation. Chọn một chính sách nhất quán và ghi rõ trong OpenAPI.

### Thiết kế extension ổn định

- **code** có thể là mã ổn định cho SDK, ví dụ **VALIDATION_FAILED**, độc lập với ngôn ngữ title/detail.
- **errors** cần schema cố định; không nên lúc là mảng chuỗi, lúc là object tùy controller.
- **requestId/traceId** chỉ nên là định danh không nhạy cảm; không trả thông tin phiên đăng nhập hoặc token.
- Không gửi giá trị đầu vào nhạy cảm trong errors nếu người dùng không cần biết giá trị đó.
- Nếu extension thay đổi nghĩa, cần xem xét tương thích ngược hoặc định danh problem type/version mới.

## 5. Đừng biến Problem Details thành một “status code thứ hai”

HTTP status vẫn là **cơ chế chính** để báo kết quả của request. Problem Details bổ sung giải thích, không được dùng để che giấu trạng thái lỗi dưới **200 OK**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/problem+json

{"status":409,"detail":"Đơn hàng không thể hủy."}
~~~

Đây là **phản mẫu**: HTTP status biểu thị thành công trong khi body biểu thị lỗi. HTTP client, cache, gateway, monitor và chính sách retry có thể xử lý sai. Nếu hủy đơn bị từ chối vì xung đột trạng thái, hãy trả **409 Conflict** với body phù hợp.

| HTTP status | Tình huống REST API điển hình | Dữ liệu bổ sung có ích |
|---|---|---|
| **400 Bad Request** | JSON sai cú pháp, tham số không hợp lệ ở mức request | Vị trí/số tham số lỗi, code ổn định |
| **401 Unauthorized** | Chưa có credentials hợp lệ | Header **WWW-Authenticate** khi giao thức yêu cầu |
| **403 Forbidden** | Đã xác định người gọi nhưng không có quyền | Thông báo an toàn, không lộ chính sách nhạy cảm |
| **404 Not Found** | Resource không tồn tại hoặc server chọn không tiết lộ sự tồn tại | Mã loại tài nguyên, requestId |
| **405 Method Not Allowed** | Resource không hỗ trợ HTTP method | Header **Allow** bắt buộc với origin server |
| **406 Not Acceptable** | Không có biểu diễn chấp nhận được theo **Accept** và server không dùng biểu diễn mặc định | Có thể không có body nếu client không nhận được loại nào |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ | Trạng thái hiện tại, hành động khắc phục an toàn |
| **412 Precondition Failed** | **If-Match/ETag** không khớp | ETag hiện tại nếu chính sách cho phép |
| **415 Unsupported Media Type** | **Content-Type** request không được hỗ trợ | Các media type request mà API hỗ trợ trong tài liệu |
| **422 Unprocessable Content** | Cú pháp đúng nhưng dữ liệu không xử lý được theo quy tắc | errors theo trường hoặc quy tắc nghiệp vụ |
| **429 Too Many Requests** | Vượt chính sách tốc độ/hạn mức | **Retry-After** khi tính được, code/limitScope |
| **500 Internal Server Error** | Lỗi server không dự kiến | Định danh truy vết, tránh stack trace |
| **502 Bad Gateway** | Gateway nhận phản hồi không hợp lệ từ upstream | Request ID, thông báo tổng quát |
| **503 Service Unavailable** | Dịch vụ tạm không khả dụng hoặc quá tải | **Retry-After** nếu có ước lượng phù hợp |

**Body Problem Details không thay thế các header bắt buộc khác.** Ví dụ: **405** phải có **Allow**; **401** theo HTTP authentication cần **WWW-Authenticate** phù hợp; **429/503** có thể sử dụng **Retry-After**. Không chỉ đưa danh sách phương thức hoặc thời gian đợi vào trường detail rồi bỏ những header cần thiết.

### Một lỗi chỉ có thể được biết sau khi yêu cầu đã vào hệ thống

Khi client gửi một lệnh POST tạo thanh toán và kết nối bị ngắt, client không thể mặc định yêu cầu đã thất bại vì không thấy response. Khi retry, cần **Idempotency-Key** và cách tra cứu trạng thái theo hợp đồng. Problem Details chỉ mô tả **phản hồi server thực sự đã phát**, không giải quyết được mọi trường hợp kết quả không rõ trên mạng.

## 6. Content-Type và Accept: hai câu hỏi khác nhau

Muốn hiểu thương lượng biểu diễn lỗi, cần phân biệt rõ **media type request** và **media type response**.

| Header | Hướng | Câu hỏi |
|---|---|---|
| **Content-Type** trong request | Client → server | “Body tôi gửi là định dạng gì?” |
| **Accept** trong request | Client → server | “Tôi chấp nhận các định dạng response nào?” |
| **Content-Type** trong response | Server → client | “Body phản hồi thực tế có định dạng gì?” |
| **Accept-Language** trong request | Client → server | “Tôi ưu tiên ngôn ngữ diễn giải nào?” |
| **Content-Language** trong response | Server → client | “Nội dung phản hồi được viết bằng ngôn ngữ nào?” |

Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/problem+json, application/json;q=0.8
Accept-Language: vi

{"cartId":"cart-91"}
~~~

Request này **gửi dữ liệu application/json** và **ưu tiên nhận response application/problem+json**, đồng thời chấp nhận application/json với độ ưu tiên thấp hơn. Nó **không yêu cầu** response luôn phải là lỗi: khi thành công, server có thể trả một biểu diễn thành công thuộc tập client chấp nhận; khi thất bại, có thể trả Problem Details theo hợp đồng.

### Không được nhầm +json với application/json

**application/problem+json** là một **media type cụ thể**. Một header **Accept: application/json** không tự động tương đương **Accept: application/problem+json** chỉ vì hai dạng cùng chứa JSON. Tương tự, **Content-Type: application/json** của request không yêu cầu server trả lỗi bằng application/json.

Nếu hệ thống phải phục vụ client cũ chỉ chấp nhận **application/json**, cần quyết định có hỗ trợ một **error envelope application/json** riêng hay cập nhật hợp đồng client để chấp nhận **application/problem+json**. Không nên gửi body Problem Details nhưng gắn nhãn **Content-Type: application/json** một cách tùy tiện rồi cho rằng đã hỗ trợ đầy đủ thương lượng.

## 7. Thương lượng biểu diễn lỗi qua Accept

HTTP hỗ trợ **proactive content negotiation** thông qua header **Accept**, có thể bao gồm các media range và trọng số **q**. Nếu API có nhiều biểu diễn lỗi, server quyết định định dạng từ những lựa chọn hợp lệ mà client chấp nhận.

Ví dụ client:

~~~http
GET /api/orders/not-found HTTP/1.1
Host: api.example.test
Accept: application/problem+json;q=1.0, text/plain;q=0.5

~~~

Server có thể chọn **application/problem+json** vì có mức ưu tiên cao hơn nếu hỗ trợ cả hai định dạng. **q=0** thể hiện media range **không được chấp nhận**, không phải ưu tiên thấp nhưng vẫn được dùng.

### Những mẫu Accept thường gặp

| Accept | Cách hiểu thực dụng |
|---|---|
| **application/problem+json** | Client yêu cầu biểu diễn Problem Details dạng JSON |
| **application/problem+json, application/json;q=0.8** | Cho phép cả hai loại; ưu tiên problem+json nếu được hỗ trợ |
| **application/json** | Chỉ nêu application/json; không tự động bao gồm problem+json |
| `application/*` | Chấp nhận các subtype media type thuộc application, gồm problem+json |
| `*/*` | Chấp nhận các media type nói chung; server có thể chọn mặc định |
| **application/problem+json;q=0** | Không chấp nhận media type problem+json theo phần khai báo đó |
| **application/xml** | Không chấp nhận problem+json theo mặc định |
| **Không có Accept** | Client không thể hiện giới hạn loại response; server có thể chọn biểu diễn mặc định |

**Lưu ý cú pháp:** Trong HTTP Accept chuẩn, media-range phổ biến là `type/subtype`, `type/*` hoặc `*/*`. Một số framework có cách mở rộng cho kiểu như `application/*+json`, nhưng không nên giả định cú pháp đó luôn được mọi server hiểu. Nếu SDK cần Problem Details, cách rõ nhất là khai báo trực tiếp **application/problem+json**.

### Nên ưu tiên định dạng nào?

Một chính sách API JSON có thể là:

1. Với lỗi, ưu tiên **application/problem+json** nếu client chấp nhận và server có thể tạo.
2. Nếu client chỉ chấp nhận **application/json**, dùng **error format application/json** khi API đã có hợp đồng tương thích riêng.
3. Nếu client chấp nhận **text/plain** và API chủ động hỗ trợ dạng này, trả văn bản tối thiểu cho một số lỗi.
4. Nếu không có dạng nào chấp nhận được và server không dùng biểu diễn mặc định, trả **406 Not Acceptable**.

Đây là **chính sách minh họa**, không phải yêu cầu HTTP buộc mọi API phải cung cấp nhiều kiểu body lỗi. Một API chỉ hỗ trợ Problem Details JSON vẫn hợp lệ; khi ấy client phải nêu Accept tương ứng hoặc một wildcard phù hợp.

### Không ép JSON khi client đã từ chối

Ví dụ:

~~~http
GET /api/orders/unknown HTTP/1.1
Host: api.example.test
Accept: application/xml

~~~

Giả sử server **chỉ hỗ trợ response application/problem+json** và không muốn phá giới hạn Accept. Khi resource không tồn tại, server có thể trả **406 Not Acceptable** vì không cung cấp biểu diễn chấp nhận được, và **không có body** nếu không còn media type nào phù hợp. Không tự ý trả **Content-Type: application/problem+json** cho client vừa khai báo chỉ chấp nhận XML rồi nói rằng đã thương lượng thành công.

Nếu server có hỗ trợ **application/problem+xml**, nó có thể trả **404 Not Found** với media type đó và một body Problem Details XML. Trình tự ưu tiên khi **lỗi gốc 404** nhưng **Accept không tương thích** là chính sách cần kiểm thử nhất quán của framework và gateway; không nên giả định mọi stack sẽ cho cùng một status trong trường hợp này.

## 8. 406 khác 415: lỗi lựa chọn response và lỗi đọc request

Hai status này rất dễ bị đảo ngược khi xây API.

### 415 Unsupported Media Type

Client gửi một kiểu body mà endpoint không xử lý:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: text/plain
Accept: application/problem+json

cart=123
~~~

Nếu endpoint chỉ nhận JSON, server có thể trả:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/unsupported-request-format",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "Endpoint này yêu cầu Content-Type: application/json.",
  "code": "UNSUPPORTED_MEDIA_TYPE"
}
~~~

**Lý do là Content-Type request**, không phải vì Accept. Trong ví dụ, client đã chấp nhận problem+json, nên trả body Problem Details là phù hợp.

### 406 Not Acceptable

Client gửi **Accept** không khớp với bất kỳ biểu diễn nào server sẵn sàng trả. Đây là vấn đề **định dạng phản hồi**, không có nghĩa server không đọc được request. Ví dụ client chỉ chấp nhận **application/xml**, trong khi API chỉ xuất JSON và không dùng biểu diễn mặc định.

### Cây quyết định tối giản

~~~mermaid
flowchart TD
    A["Nhận HTTP request"] --> B{"Media type của request body hợp lệ?"}
    B -- "Không" --> C["415 Unsupported Media Type"]
    B -- "Có" --> D["Thực thi routing, validation, auth và nghiệp vụ"]
    D --> E{"Chọn được response media type client chấp nhận?"}
    E -- "Có" --> F["Trả status phù hợp + Content-Type đúng"]
    E -- "Không" --> G["406 Not Acceptable hoặc policy mặc định được công bố"]
    C --> H["Nếu Accept cho phép, mô tả 415 bằng Problem Details"]
~~~

Sơ đồ chỉ minh họa **hai khái niệm thương lượng**. Trong thực tế, server có thể lựa chọn response type **trước khi thực thi controller**, một security filter có thể trả 401/403 trước khi kiểm tra Content-Type, và cách xử lý lỗi 406 có thể do framework quyết định. Điều quan trọng là **không trộn ý nghĩa request-body media type với response Accept**.

## 9. Bản địa hóa title/detail và header Vary

Thông tin để client **lập trình quyết định** cần ổn định; thông tin để **người đọc** có thể được bản địa hóa.

Giả sử client gửi:

~~~http
GET /api/orders/unknown HTTP/1.1
Host: api.example.test
Accept: application/problem+json
Accept-Language: vi

~~~

Server có thể trả:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Content-Language: vi
Vary: Accept, Accept-Language

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không có đơn hàng phù hợp với mã được yêu cầu.",
  "code": "ORDER_NOT_FOUND"
}
~~~

Với cùng type, client gửi **Accept-Language: en** có thể nhận title/detail bằng tiếng Anh; **type** và **code** vẫn ổn định. **Vary: Accept, Accept-Language** là chỉ dẫn cho cache biết biểu diễn thay đổi theo những request headers đó, nếu server thực sự sử dụng chúng để chọn nội dung.

### Lưu ý về cache

Một số mã lỗi, chẳng hạn **404** và **405**, có thể được HTTP cache lưu theo quy tắc cache nếu các điều kiện cho phép; **429** có quy tắc riêng cấm HTTP cache lưu trong RFC 6585. Với lỗi nhạy cảm có thông tin tài khoản, tài liệu, quyền hoặc dữ liệu cá nhân, **Cache-Control: no-store** thường là lựa chọn an toàn.

Không mặc định mọi lỗi đều có cùng khả năng cache. Việc đặt **Vary** không thay thế kiểm soát cache và quyền truy cập, còn **no-store** không thay thế việc tránh lộ dữ liệu nhạy cảm trong body lỗi.

## 10. Bảo mật và quyền riêng tư trong thông báo lỗi

Biểu diễn lỗi là một phần **bề mặt tấn công**. API có thể vô tình tiết lộ thông tin hệ thống dù không trả thành công dữ liệu nghiệp vụ.

| Thông tin | Rủi ro | Hướng xử lý |
|---|---|---|
| Stack trace, tên class, đường dẫn máy chủ | Lộ công nghệ và cấu trúc triển khai | Ghi ở log nội bộ, trả thông báo tổng quát cho client |
| SQL query, tên bảng/cột, connection string | Lộ cấu trúc dữ liệu hoặc bí mật | Không đưa vào detail/extensions |
| Access token, cookie, API key | Lộ credentials | Mask tại log, không echo request headers nhạy cảm |
| Email/số điện thoại của tài khoản khác | Lộ dữ liệu cá nhân | Trả lỗi chung hoặc chỉ dữ liệu người gọi được phép thấy |
| Thông tin resource không có quyền | Cho phép dò tìm tài nguyên | Có thể dùng **404** để không tiết lộ tồn tại, theo chính sách |
| Error code/instance không ổn định | Client khó xử lý và hỗ trợ | Giữ type/code ổn định, instance/requestId không chứa bí mật |

### Không phơi bày nguyên nhân nội bộ của lỗi 500

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-a72e

{
  "type": "https://api.example.test/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Yêu cầu chưa thể hoàn tất. Vui lòng thử lại sau.",
  "instance": "/problems/occurrences/req-a72e",
  "code": "INTERNAL_ERROR"
}
~~~

Log ở server nên ghi **requestId/traceId**, exception, dependency và stack trace với quyền truy cập phù hợp. Client gửi requestId cho bộ phận hỗ trợ để liên hệ sự cố; không cần nhận stack trace. Nếu nghiệp vụ có tiền hoặc side effect, hướng dẫn retry phải dựa trên **idempotency và tra cứu trạng thái**, không chỉ trên mã 500.

### CORS khi JavaScript cần đọc Problem Details

Nếu frontend nằm ở origin khác, phản hồi lỗi cũng phải được gửi qua chính sách **CORS** phù hợp để JavaScript đọc status và body. Trình duyệt có thể ẩn nội dung phản hồi khi policy CORS không cho phép, khiến frontend chỉ thấy lỗi mạng/CORS. Điều này không đồng nghĩa API chưa phát response.

Không dùng CORS làm cơ chế authorization. Request thật vẫn phải được xác thực và phân quyền, kể cả khi preflight đã thành công. Nếu client cần đọc header không thuộc nhóm exposed mặc định, chẳng hạn **Retry-After** hoặc **X-Request-ID**, hãy cấu hình **Access-Control-Expose-Headers** theo nhu cầu được phép.

## 11. Sơ đồ luồng xử lý lỗi trong API

Một pipeline hợp lý tách **phát hiện lỗi** khỏi **biểu diễn lỗi**:

~~~mermaid
flowchart TD
    C["Client / SDK"] --> G["Gateway / WAF / Security"]
    G --> R["Routing + parse Content-Type"]
    R --> V["Validation + AuthZ + Application"]
    V --> E["Exception / ErrorResponse / Domain outcome"]
    E --> M["Error mapping<br/>HTTP status + problem type + extensions"]
    M --> N["Content negotiation<br/>Accept, Accept-Language"]
    N --> J["Serializer<br/>problem+json / lựa chọn hỗ trợ"]
    J --> C
    G -. "Có thể tạo 401/403/429/503 trước controller" .-> M
    E -. "exception, trace ID, context an toàn" .-> L["Structured logs + metrics"]
    M -. "status, type, requestId" .-> L
~~~

Các trường hợp do **gateway** trả 429/503 hoặc security filter trả 401/403 có thể **không đi qua controller exception handler**. Muốn toàn API thống nhất Problem Details, cần phối hợp cấu hình giữa **gateway, security, framework và ứng dụng**.

### Bảng ánh xạ exception sang hợp đồng

| Nguồn lỗi | HTTP status tham khảo | Problem type / extension |
|---|---|---|
| JSON parser không đọc được payload | **400** | invalid-json |
| Dữ liệu hợp lệ về cú pháp nhưng sai quy tắc | **400** hoặc **422** theo contract | validation-failed, errors |
| Token thiếu hoặc không hợp lệ | **401** | unauthenticated, WWW-Authenticate phù hợp |
| Không có quyền truy cập | **403** hoặc **404** theo chính sách tiết lộ | forbidden / not-found |
| Resource không tồn tại | **404** | order-not-found |
| Hành động không hợp lệ theo trạng thái | **409** | order-not-cancellable |
| ETag cũ khi update | **412** | version-conflict |
| Quota đã hết | **429** | rate-limit-exceeded, Retry-After nếu biết |
| Dependency tạm không khả dụng | **503** hoặc **502** theo trách nhiệm gateway | service-unavailable, requestId |
| Lỗi không lường trước | **500** | internal-error, requestId |

Không nên để mọi exception tùy ý thành **400**, bởi điều đó khiến lỗi lập trình hoặc lỗi dữ liệu ở server bị che khuất và gây hiểu nhầm trách nhiệm của client.

## 12. Triển khai trong Spring Framework 6 / Spring Boot 3

Spring Framework 6 cung cấp **ProblemDetail**, **ErrorResponse** và **ResponseEntityExceptionHandler** hỗ trợ mô hình Problem Details. Bên cạnh đó, **@RestControllerAdvice** có thể ánh xạ exception nghiệp vụ sang status và body.

### 12.1. Ví dụ xử lý xung đột nghiệp vụ và validation

Ví dụ dưới minh họa một lớp advice dùng cho Spring MVC. Nó giả định ứng dụng có exception **OrderConflictException** được ném từ service khi trạng thái đơn không cho phép thao tác.

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

class OrderConflictException extends RuntimeException {
    OrderConflictException(String message) {
        super(message);
    }
}

@RestControllerAdvice
public class ApiProblemAdvice extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ProblemDetail> onOrderConflict(
            OrderConflictException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.getMessage());
        problem.setType(URI.create(
                "https://api.example.test/problems/order-conflict"));
        problem.setTitle("Order Conflict");
        problem.setProperty("code", "ORDER_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "Một hoặc nhiều trường không hợp lệ.");
        problem.setType(URI.create(
                "https://api.example.test/problems/validation-failed"));
        problem.setTitle("Validation Failed");
        problem.setProperty("code", "VALIDATION_FAILED");

        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "detail", Objects.toString(
                                error.getDefaultMessage(),
                                "Giá trị không hợp lệ")))
                .toList();
        problem.setProperty("errors", errors);

        return ResponseEntity.status(status)
                .headers(headers)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

**Phạm vi ví dụ:** Đây là handler mô tả **cách dựng ProblemDetail** khi ứng dụng đã xác định client chấp nhận **application/problem+json**. Đoạn code cố định Content-Type để minh họa media type của bài học; khi đưa vào production cần bổ sung/kiểm tra **content negotiation** của toàn bộ pipeline cho các client chỉ chấp nhận XML, text hoặc application/json. Không nên coi ví dụ là một bộ xử lý Accept hoàn chỉnh.

Trong ứng dụng thực tế:

- Đổi domain/URI problem type sang địa chỉ tài liệu của tổ chức.
- Không đưa raw exception message ra response nếu nó có thể chứa chi tiết nội bộ; exception domain nên cung cấp thông điệp đã kiểm soát.
- Dùng **MessageSource** hoặc cơ chế tương đương để bản địa hóa title/detail khi cần.
- Với lỗi validation từ JSON body, có thể tạo **JSON Pointer** từ cấu trúc request; ví dụ code dùng tên field đơn giản.
- Các exception như **HttpMessageNotReadableException**, **HttpMediaTypeNotSupportedException**, **NoHandlerFoundException** hoặc security exception cần được phân loại đúng trong pipeline; không phải tất cả đều đi qua method này.

### 12.2. Cấu hình Problem Details của Spring Boot

Các phiên bản Spring Boot 3 có hỗ trợ tích hợp Problem Details cho các exception MVC, thường được kích hoạt qua cấu hình sau khi phù hợp với phiên bản ứng dụng:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Tùy **phiên bản Spring Boot, cấu hình WebFlux/Spring MVC và các advice/filter tùy biến**, hành vi mặc định, danh sách exception được map và media type chọn ra có thể khác nhau. Cần kiểm tra phiên bản thật và test response qua cả tầng gateway/security. Không nên giả định chỉ bật một property thì mọi exception nghiệp vụ, authentication failure và gateway error đều tự động thành Problem Details.

### 12.3. Lỗi tại Spring Security

**401/403** có thể được trả từ **filter chain** trước khi request đi tới controller. Với Spring Security, cần cấu hình **AuthenticationEntryPoint** cho lỗi xác thực và **AccessDeniedHandler** cho lỗi phân quyền nếu muốn chúng cũng xuất Problem Details.

Đồng thời:

- Với **401**, giữ header **WWW-Authenticate** thích hợp với cơ chế HTTP authentication đang dùng.
- Với **403**, tránh tiết lộ chi tiết về quyền hoặc resource không được phép xem.
- Dùng cùng bộ problem type/code với controller, nhưng không lạm dụng việc trả 200 kèm body lỗi.
- Kiểm thử cả request có và không có credentials, token hết hạn, quyền thiếu và CORS preflight.

### 12.4. ErrorResponse và xử lý framework

Spring cung cấp **ErrorResponse** cho nhiều lỗi ở tầng web, liên kết status, headers và ProblemDetail. **ResponseEntityExceptionHandler** có thể dùng làm nền để tùy chỉnh các trường hợp MVC phổ biến. Nếu thêm advice của riêng mình, cần kiểm tra thứ tự ưu tiên, khả năng bắt trùng exception và những header mà handler mặc định cung cấp.

Một lỗi **405 Method Not Allowed** vẫn cần **Allow** trong response; lỗi **415** không nên bị biến thành 500 vì thiếu converter; lỗi **406** không nên bị xử lý bằng cách **ép response application/problem+json bất kể Accept**.

## 13. Tài liệu hợp đồng trong OpenAPI 3.1

Ví dụ rút gọn mô tả **Problem Details** cho một endpoint tạo đơn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders:
    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [cartId]
              properties:
                cartId:
                  type: string
      responses:
        '201':
          description: Đơn đã được tạo
        '400':
          description: Request sai cú pháp hoặc validation
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '409':
          description: Xung đột trạng thái đơn
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '415':
          description: Request Content-Type không được hỗ trợ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '406':
          description: Không chọn được response representation phù hợp
          # Không buộc JSON body nếu client không chấp nhận JSON.
components:
  schemas:
    ApiProblem:
      type: object
      description: >
        Profile Problem Details của API; ngoài các trường chung
        có thể có extension errors cho validation.
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        errors:
          type: array
          items:
            type: object
            properties:
              field:
                type: string
              detail:
                type: string
~~~

Ở đây, **required: [type, title, status]** là **profile do API này tự quy định**; RFC 9457 không yêu cầu cả ba trường luôn tồn tại. Khi API hỗ trợ XML hoặc text/plain, khai báo thêm các media type đó dưới content cho những response tương ứng. Nếu **406** có thể không có body, không nên mô tả chắc chắn nó luôn trả application/problem+json.

### Hợp đồng cần xác định ngoài schema

- **Accept được hỗ trợ** cho success và error, cùng lựa chọn khi Accept vắng mặt.
- **Request Content-Type** mà từng endpoint cho phép, kể cả charset/format nếu có ràng buộc.
- **Problem type/code** ổn định và các extension cho từng loại lỗi.
- Mã trạng thái và header như **Allow**, **WWW-Authenticate**, **Retry-After**, **ETag** khi thích hợp.
- Cách **localization** và xử lý lỗi không có biểu diễn phù hợp.
- Quy tắc **versioning** khi thêm hoặc đổi nghĩa một problem type/extension.

## 14. Kiểm thử HTTP, thương lượng và tính nhất quán

### 14.1. Kiểm tra một Problem Details thực tế

~~~bash
curl -i \
  -H 'Accept: application/problem+json' \
  https://api.example.test/api/orders/unknown
~~~

Khi resource không tồn tại và request đã qua xác thực theo policy, kỳ vọng ví dụ là:

- HTTP status **404**.
- **Content-Type: application/problem+json**.
- Body có **type/title/status** theo contract đã chọn; status body **404**.
- Không lộ stack trace, token, SQL hoặc dữ liệu đơn của người khác.
- Nếu trả instance/requestId, có thể liên hệ chúng với log nội bộ an toàn.

### 14.2. Kiểm tra thương lượng Accept

~~~bash
curl -i \
  -H 'Accept: application/problem+json' \
  https://api.example.test/api/orders/unknown

curl -i \
  -H 'Accept: application/json' \
  https://api.example.test/api/orders/unknown

curl -i \
  -H 'Accept: application/xml' \
  https://api.example.test/api/orders/unknown

curl -i \
  -H 'Accept: application/problem+json;q=0, text/plain;q=1' \
  https://api.example.test/api/orders/unknown
~~~

Các lệnh kiểm tra **những trường hợp khác nhau**, không đặt kỳ vọng tất cả đều phải trả 404 JSON. Phản hồi chính xác phụ thuộc tập media type API hỗ trợ và chính sách negotiation đã công bố. Nếu API không hỗ trợ text/plain/XML và không muốn gửi mặc định trái Accept, các request tương ứng có thể nhận **406**. Mục tiêu là **không trả nội dung trái hợp đồng rồi để client đoán**.

### 14.3. Kiểm tra 415 và validation

~~~bash
curl -i -X POST \
  -H 'Accept: application/problem+json' \
  -H 'Content-Type: text/plain' \
  --data 'cartId=123' \
  https://api.example.test/api/orders

curl -i -X POST \
  -H 'Accept: application/problem+json' \
  -H 'Content-Type: application/json' \
  --data '{"cartId":""}' \
  https://api.example.test/api/orders
~~~

Lệnh thứ nhất dùng **Content-Type request không được hỗ trợ** và nên được xét theo **415** nếu endpoint chỉ nhận JSON. Lệnh thứ hai hợp lệ về cú pháp JSON nhưng có thể sai validation; API có thể trả **400 hoặc 422** theo contract. Luôn dùng **môi trường thử nghiệm** hoặc endpoint bảo đảm không tạo dữ liệu ngoài ý muốn.

### 14.4. Ma trận contract test

| Trường hợp | Kiểm tra chính |
|---|---|
| Không có Accept | Media type mặc định đã công bố |
| Accept problem+json | Problem Details JSON đúng schema |
| Accept application/json | Không mặc định coi application/json là problem+json |
| Accept wildcard | Chọn một biểu diễn được hỗ trợ |
| Accept có q=0 | Không gửi media type bị từ chối |
| Không có media type phù hợp | Chính sách **406**/fallback nhất quán |
| Request Content-Type sai | **415**, không nhầm với 406 |
| JSON sai cú pháp | 400 với problem type phù hợp |
| Nhiều lỗi validation | Mảng errors có schema ổn định; status theo contract |
| Authentication/authorization | 401/403 đúng và không lộ thông tin |
| Phương thức không hỗ trợ | 405 giữ **Allow** |
| Quota/thời gian chờ | 429 giữ **Retry-After** khi có |
| Lỗi không dự kiến | 500 được che chi tiết nội bộ, có requestId |
| Accept-Language thay đổi | type/code ổn định, title/detail đúng locale nếu hỗ trợ |
| Đi qua gateway | Status, Content-Type, headers và problem body không mâu thuẫn |
| Frontend cross-origin | CORS cho phép đọc Problem Details khi được phép |

### 14.5. Ví dụ MockMvc kiểm tra contract

Một phần test theo Spring MVC:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProblemContractTest {
    @Autowired MockMvc mvc;

    @Test
    void missingOrderUsesProblemJson() throws Exception {
        mvc.perform(get("/api/orders/missing")
                  .accept(MediaType.APPLICATION_PROBLEM_JSON))
           .andExpect(status().isNotFound())
           .andExpect(content().contentTypeCompatibleWith(
                   MediaType.APPLICATION_PROBLEM_JSON))
           .andExpect(jsonPath("$.status").value(404))
           .andExpect(jsonPath("$.type").exists());
    }
}
~~~

Test này giả định ứng dụng có endpoint **GET /api/orders/{id}** và xử lý 404 thành Problem Details. Với Spring Security, cần thiết lập authentication hoặc mock user đúng chính sách để test đi đến controller. Đây là **bài mẫu contract test**, không phải test được chạy trong quá trình viết tài liệu; đường dẫn và cơ chế xác thực cần điều chỉnh theo ứng dụng thực.

Đừng viết test chỉ so sánh một thông điệp detail cố định bằng tiếng Việt; hãy kiểm tra **HTTP status, media type, type/code, schema và header bắt buộc**. Với nội dung bản địa hóa, có thể kiểm tra thêm Content-Language và một vài trường ngôn ngữ đại diện.

## 15. Các lỗi thiết kế thường gặp

| Phản mẫu | Vì sao gây lỗi | Cách sửa |
|---|---|---|
| Trả **200** với body chứa status lỗi | HTTP stack và client coi là thành công | Trả status HTTP thực tế, body Problem Details phù hợp |
| Luôn trả **application/json** nhưng body theo RFC 9457 | Media type không mô tả chính xác dạng biểu diễn | Dùng **application/problem+json** khi client chấp nhận; công bố fallback riêng nếu cần |
| Nghĩ **Accept: application/json** tự bao gồm problem+json | Client/server có thể chọn sai định dạng | Khai báo media type cụ thể hoặc wildcard hợp lệ |
| Ép problem+json cho mọi Accept | Vi phạm mong đợi negotiation của client | Cấu hình negotiation, hỗ trợ định dạng khác hoặc 406 |
| Dùng 415 khi client chỉ Accept XML | Nhầm request Content-Type với response Accept | Dùng **406** cho lỗi chọn response |
| Dùng 406 khi client POST text/plain vào endpoint JSON | Nhầm response negotiation với request parsing | Dùng **415** |
| Mỗi request có problem type mới | Client không phân loại theo loại lỗi | Giữ type ổn định, dùng instance cho từng occurrence |
| Chỉ có detail làm định danh lỗi | Văn bản có thể dịch/thay đổi | Dùng type hoặc extension code ổn định |
| 500 kèm stack trace hoặc SQL | Lộ chi tiết nội bộ và có thể lộ bí mật | Trả thông báo tổng quát và requestId; log an toàn ở server |
| Dùng một body chung cho mọi lỗi validation | Client không biết trường nào cần sửa | Dùng extension errors được tài liệu hóa |
| Bỏ **WWW-Authenticate**, **Allow**, **Retry-After** | Mất ngữ nghĩa HTTP/khả năng phục hồi | Giữ header tương ứng theo mã status |
| Bỏ qua lỗi từ gateway/security | Controller trả JSON chuẩn nhưng 401/429 lại HTML | Chuẩn hóa xử lý ở mọi lớp với cùng contract |
| Dùng cache chung cho lỗi có dữ liệu riêng | Có nguy cơ lộ nội dung người dùng | Kiểm tra Cache-Control/Vary và chính sách chia sẻ cache |
| Bắt mọi exception rồi trả 400 | Che lỗi server thành lỗi client | Mapping rõ domain/client/server exception |

## 16. Bài tập tình huống: API đơn hàng đa ngôn ngữ

Một hệ thống bán hàng công bố:

- **GET /api/orders/{id}** để đọc đơn; người không có quyền không được biết đơn có tồn tại.
- **POST /api/orders** nhận **Content-Type: application/json**; API dùng **422** cho validation đúng cú pháp nhưng vi phạm quy tắc nghiệp vụ.
- **PATCH /api/orders/{id}** dùng **If-Match** để tránh ghi đè phiên bản cũ.
- **DELETE /api/orders/{id}** có thể gặp lỗi không cho phép hủy vì đã giao hàng (**409**).
- Client mới chấp nhận **application/problem+json**; client cũ chỉ gửi **Accept: application/json**.
- UI hỗ trợ tiếng Việt và tiếng Anh, có một API gateway có thể trả **429** khi quá hạn mức.
- Hệ thống dùng **Spring Boot 3** với controller, Spring Security và gateway.

### Yêu cầu thực hành

1. Đề xuất ít nhất **sáu problem type** phù hợp, mỗi loại có status và một trường extension hữu ích nếu cần.
2. Viết **Problem Details 422** cho payload có email sai và địa chỉ nhận hàng rỗng; chỉ rõ schema của mảng errors.
3. Viết phản hồi **409** khi xóa đơn đã giao hàng, phân biệt **type** và **instance**.
4. Giải thích cách xử lý **Accept: application/json** của client cũ: có thể chuyển client, cung cấp fallback hay phản hồi 406 trong điều kiện nào?
5. So sánh request sai **Content-Type: text/plain** với request có **Accept: application/xml** khi API chỉ xuất JSON.
6. Xác định cách bảo đảm **401/403 từ Security** và **429 từ gateway** dùng định dạng nhất quán với lỗi controller.
7. Đề xuất ít nhất **tám contract test** bao gồm localization, authentication, status/header, negotiation và nội dung 500 được che.

### Gợi ý đáp án

| Loại lỗi | Status gợi ý | Problem type | Extension hữu ích |
|---|---:|---|---|
| Đơn không tồn tại hoặc không được phép tiết lộ | 404 | **/problems/order-not-found** | code |
| Payload không đáp ứng validation | 422 | **/problems/validation-failed** | errors |
| Đơn đã giao nên không hủy được | 409 | **/problems/order-not-cancellable** | orderStatus |
| If-Match không khớp | 412 | **/problems/version-conflict** | code, currentVersion nếu được phép |
| Chưa xác thực | 401 | **/problems/unauthenticated** | code và WWW-Authenticate |
| Vượt hạn mức gateway | 429 | **/problems/rate-limit-exceeded** | code và Retry-After |
| Phương thức không hỗ trợ | 405 | **about:blank** hoặc type riêng | Allow |
| Lỗi ngoài dự kiến | 500 | **/problems/internal-error** | requestId |

Ví dụ 422:

~~~json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "detail": "Có 2 trường cần sửa.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"pointer": "#/email", "code": "EMAIL_FORMAT",
     "detail": "Email không đúng định dạng."},
    {"pointer": "#/shippingAddress", "code": "REQUIRED",
     "detail": "Địa chỉ giao hàng là bắt buộc."}
  ]
}
~~~

Ví dụ 409:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-cancellable",
  "title": "Order Cannot Be Cancelled",
  "status": 409,
  "detail": "Đơn hàng đã được giao và không thể hủy.",
  "instance": "/problems/occurrences/req-83bf",
  "code": "ORDER_NOT_CANCELLABLE",
  "orderStatus": "DELIVERED"
}
~~~

**Client cũ chỉ Accept application/json:** Không mặc định cho rằng client chấp nhận problem+json. Một lộ trình tương thích có thể hỗ trợ envelope application/json riêng, kèm tài liệu và thời hạn chuyển đổi; hoặc cập nhật SDK/client để khai báo Accept cho problem+json. Nếu server không cung cấp định dạng hợp lệ mà client chấp nhận và không dùng fallback mặc định, **406** là tình huống có thể xảy ra.

**Sai Content-Type** liên quan **415**; **không có response type theo Accept** liên quan **406**. Với **401**, cấu hình AuthenticationEntryPoint đúng; với **429** do gateway tạo, áp dụng template lỗi và header thống nhất ngay tại gateway. Cần test đường request thật qua các tầng này thay vì chỉ test controller.

**Contract test nên có:** 404 không rò rỉ resource; 422 hai lỗi theo schema; 409 type/code/instance; 412 đúng precondition; 401/WWW-Authenticate; 429/Retry-After; Accept không tương thích; request Content-Type sai; Accept-Language vi/en; 500 che stack trace; và lỗi từ gateway có media type phù hợp.

### Rubric tự đánh giá

| Tiêu chí | Điểm tối đa | Dấu hiệu đạt |
|---|---:|---|
| Hiểu RFC 9457 và type/title/status/detail/instance | 25 | Phân biệt type với instance, status body với HTTP |
| Thương lượng biểu diễn lỗi | 25 | Phân biệt Accept/Content-Type, problem+json/JSON, 406/415 |
| Ánh xạ HTTP và bảo mật | 20 | Status và header đúng; tránh lộ dữ liệu |
| Spring/OpenAPI/contract test | 20 | Mô tả được xử lý đa tầng và cách kiểm chứng |
| Ứng xử client và tương thích | 10 | Có chiến lược chuyển đổi cho client cũ |

## 17. Checklist trước khi công bố hợp đồng lỗi API

- [ ] Response lỗi dùng **HTTP status thật**, không trả 200 với body status lỗi.
- [ ] API xác định **application/problem+json** là một media type riêng và mô tả Accept được hỗ trợ.
- [ ] Có chính sách cho **Accept vắng mặt, q-value, wildcard, media type không phù hợp**.
- [ ] Không nhầm **406** (response representation) với **415** (request Content-Type).
- [ ] Các trường chuẩn của RFC 9457 được hiểu đúng; trường nào bắt buộc là **quy ước profile của API**, không suy ra từ RFC.
- [ ] **type/code** ổn định theo loại lỗi; **instance/requestId** đại diện cho lần lỗi cụ thể.
- [ ] Title/detail dành cho người đọc; client không phân loại bằng nội dung detail.
- [ ] Extension validation có schema rõ, không chứa dữ liệu nhạy cảm, không thay đổi hình dạng tùy endpoint.
- [ ] Mapping 400/401/403/404/405/406/409/412/415/422/429/500/503 nhất quán với nghiệp vụ.
- [ ] Các header **WWW-Authenticate, Allow, Retry-After** được giữ khi cần; không thay bằng trường body.
- [ ] CORS, **Cache-Control**, **Vary** và localization được kiểm thử khi áp dụng.
- [ ] Lỗi 500 không phơi bày stack trace, SQL, token, dữ liệu người dùng hay cấu hình nội bộ.
- [ ] **Spring Security, gateway, Spring MVC và controller** thống nhất về trạng thái, media type và problem type.
- [ ] OpenAPI mô tả các response lỗi và extension; việc triển khai được kiểm chứng bằng contract tests.
- [ ] Có kế hoạch tương thích với client cũ và cách xử lý khi client không chấp nhận Problem Details.

**Điểm cần nhớ:** **application/problem+json** chuẩn hóa **cấu trúc mô tả lỗi**, còn **mã trạng thái HTTP** nói request thành công hay thất bại và **Accept/Content-Type** quyết định định dạng mà hai bên gửi và nhận. Một REST API có hợp đồng lỗi tốt phải giữ đồng thời ba yếu tố: **ngữ nghĩa HTTP chính xác, biểu diễn được thương lượng nhất quán và thông tin đủ hữu ích nhưng an toàn**.

### Tài liệu nền để tra cứu

- **RFC 9457 — Problem Details for HTTP APIs:** type, title, status, detail, instance, extension members và media type.
- **RFC 9110 — HTTP Semantics:** status codes, Accept, Content-Type, Content-Language, Vary và content negotiation.
- **RFC 9111 — HTTP Caching:** quy tắc kiểm soát cache và shared cache.
- **Spring Framework 6 Reference Documentation:** ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler.
- **OpenAPI Specification 3.1:** response content theo media type và schema lỗi.
