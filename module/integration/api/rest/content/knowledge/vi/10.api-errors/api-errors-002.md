# Problem Details theo RFC 9457

## 1. Bối cảnh: vì sao REST API cần một hợp đồng lỗi chung?

Giả sử một ứng dụng di động gọi REST API tạo đơn hàng. Khi thành công, API trả **201 Created** và tài nguyên vừa tạo. Khi thất bại, nhiều nhóm phát triển lại tự tạo những cấu trúc lỗi khác nhau:

~~~json
{"error": "Bad request"}
~~~

~~~json
{"success": false, "message": "Order invalid", "errorCode": 1001}
~~~

~~~json
{"timestamp": "...", "path": "/orders", "exception": "..."}
~~~

Client phải viết nhiều nhánh xử lý, không biết trường nào ổn định, có trường hợp không xác định được lỗi đến từ ứng dụng hay gateway. Nếu tất cả đều trả **200 OK** kèm một cờ thành công trong JSON, thư viện HTTP, proxy và hệ thống giám sát càng khó xử lý đúng.

**Problem Details for HTTP APIs**, chuẩn hóa bởi **RFC 9457**, cung cấp một định dạng chung để diễn đạt *một vấn đề xảy ra khi xử lý yêu cầu HTTP*. Cốt lõi là giữ nguyên **mã trạng thái HTTP** đúng ngữ nghĩa và bổ sung một đối tượng có cấu trúc để client, người phát triển và hệ thống vận hành hiểu loại vấn đề.

Bài học thuộc chương **Lỗi API** của module **INTEGRATION_API_REST**. Trong hành trình học thiết kế API từ resource, URI, phương thức và mã trạng thái HTTP đến hợp đồng OpenAPI, xác thực, phân quyền, idempotency, phân trang, cache và kiểm thử với Java/Spring, Problem Details là phần hợp đồng lỗi giúp các tầng giao tiếp nhất quán.

Sau bài học, bạn có thể:

- Giải thích RFC 9457 giải quyết vấn đề gì và phân biệt với mã trạng thái HTTP.
- Hiểu đúng năm thành viên chuẩn: **type**, **title**, **status**, **detail**, **instance**.
- Định nghĩa loại lỗi ổn định và các trường mở rộng có chủ đích.
- Chọn phản hồi phù hợp cho lỗi validation, xác thực, phân quyền, xung đột, giới hạn lưu lượng và lỗi nội bộ.
- Triển khai Problem Details trên Spring và mô tả trong OpenAPI.
- Kiểm thử từ status, header, media type đến payload, bảo mật và hành vi client.

## 2. Hình dạng của một phản hồi Problem Details

Ví dụ API từ chối hủy đơn hàng đã được giao:

~~~http
POST /orders/ord-123/cancel HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>

HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7fa9

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn hàng đã được bàn giao nên không thể hủy.",
  "instance": "/problems/occurrences/req-7fa9",
  "code": "ORDER_ALREADY_SHIPPED",
  "requestId": "req-7fa9"
}
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| **409 Conflict** trong HTTP response | Kết quả ở cấp giao thức: thao tác xung đột với trạng thái hiện tại. |
| **Content-Type: application/problem+json** | Cho biết body là một đối tượng Problem Details mã hóa bằng JSON. |
| **type** | Danh tính ổn định của loại vấn đề, giúp client quyết định cách xử lý. |
| **title** | Tóm tắt ngắn của loại vấn đề, dành cho người đọc. |
| **status** | Bản sao mang tính thông tin của mã HTTP, tiện khi body được lưu riêng. |
| **detail** | Giải thích cho lần xảy ra cụ thể, không phải khóa lập trình. |
| **instance** | Định danh một lần xuất hiện của vấn đề, nếu hệ thống cung cấp. |
| **code**, **requestId** | Trường mở rộng do API tự định nghĩa, không thuộc năm thành viên chuẩn. |

Ví dụ dùng URI và ID minh họa. **Không phải tất cả các trường trên đều bắt buộc theo RFC 9457**. Một tổ chức có thể xây dựng hợp đồng nội bộ yêu cầu thêm trường, nhưng phải phân biệt rõ quy tắc riêng với yêu cầu của chuẩn.

Problem Details **không thay thế** HTTP status, header xác thực, điều kiện cập nhật, hướng retry hoặc dữ liệu nghiệp vụ. Nó mô tả lỗi một cách có cấu trúc để client giải thích *vì sao* request không hoàn tất theo kỳ vọng.

## 3. RFC 9457 định nghĩa những gì?

RFC 9457, *Problem Details for HTTP APIs*, kế thừa và thay thế RFC 7807. Chuẩn đưa ra:

1. Mô hình một **problem detail object** gồm các thành viên chuẩn và khả năng mở rộng.
2. Media type **application/problem+json** và **application/problem+xml** cho hai cách biểu diễn.
3. Cách định danh **problem type**, ghi nhận **problem instance**, và mối liên hệ với status HTTP.
4. Các cân nhắc về bảo mật, khả năng mở rộng và việc không lộ thông tin triển khai không cần thiết.

RFC không quy định toàn bộ danh mục lỗi nghiệp vụ của một doanh nghiệp. **ORDER_ALREADY_SHIPPED**, **OUT_OF_STOCK** hay **ACCOUNT_SUSPENDED** là các loại vấn đề do API tự thiết kế. RFC cung cấp khuôn chung để biểu diễn chúng.

Các nguyên tắc nên giữ:

- Phản hồi cuối phải có **status HTTP đúng ngữ nghĩa**. Mã trong body chỉ giúp bổ sung ngữ cảnh.
- Một **problem type** nên mô tả lỗi đủ ổn định để các client xử lý lâu dài.
- Diễn đạt lỗi bằng dữ liệu an toàn, có ích, không trả stack trace hoặc bí mật nội bộ.
- Client phải chịu được những trường chuẩn hoặc trường mở rộng không xuất hiện; không mặc định mọi lỗi server đều có body cùng cấu trúc.

### 3.1. JSON và XML

Biểu diễn JSON là lựa chọn thường gặp trong REST API:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/order-not-found",
 "title":"Order not found","status":404}
~~~

RFC cũng định nghĩa **application/problem+xml** khi API sử dụng XML. Hai media type là các cách biểu diễn của cùng khái niệm, không đồng nghĩa phải hỗ trợ cả hai. API JSON có thể công bố chỉ hỗ trợ **application/problem+json** cho lỗi.

Khi client gửi **Accept**, server cần xử lý thương lượng nội dung phù hợp với những biểu diễn được hỗ trợ. Với phần lớn JSON API, việc dùng cùng một media type lỗi ổn định thường giúp SDK dễ triển khai.

## 4. Năm thành viên chuẩn và ngữ nghĩa chính xác

### 4.1. type: loại vấn đề

**type** là một **URI reference** nhận diện loại vấn đề. Khi có thể, nên dùng URI ổn định và có tài liệu:

~~~json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404
}
~~~

Client dùng **type** làm một trong các khóa phân nhánh logic:

~~~text
type = .../order-not-found       -> thông báo đơn không tồn tại
type = .../order-state-conflict  -> yêu cầu làm mới trạng thái đơn
type = .../quota-exceeded       -> giảm tần suất hoặc hướng dẫn nâng hạn mức
~~~

URI type **không bắt buộc** phải được truy cập thành công qua HTTP. Tuy nhiên, nếu dùng HTTPS URI có thể truy cập được, trang đó có thể giải thích ý nghĩa, mã HTTP liên quan, cách khắc phục và các trường mở rộng. Một URI không có tài liệu vẫn là định danh loại vấn đề nếu được dùng ổn định.

Nếu **type** không xuất hiện, giá trị mặc định theo chuẩn là **about:blank**. Đây là loại vấn đề chung chỉ dựa trên ngữ nghĩa mã HTTP; nếu ứng dụng muốn phân biệt lỗi nghiệp vụ, cần dùng loại vấn đề riêng.

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404
}
~~~

Trong trường hợp **about:blank**, **title** nên phản ánh reason phrase phù hợp với HTTP status (có thể bản địa hóa). Đừng tạo type mới cho mọi lần request: các sự kiện cùng loại cần có **cùng type**, còn **instance** mới thay đổi theo lần xảy ra.

### 4.2. title: mô tả ngắn của loại vấn đề

**title** là chuỗi mô tả ngắn, dễ đọc và thường **không thay đổi giữa những lần xuất hiện của cùng type**, ngoại trừ bản địa hóa.

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409
}
~~~

Không dùng title làm mã lập trình hoặc nhét thông tin thay đổi theo request vào title như “Đơn ord-123 bị giao lúc 16:20”. Chi tiết của lần xảy ra thuộc **detail**. Nếu title được dịch sang tiếng Việt theo **Accept-Language**, **type** vẫn có thể giữ nguyên.

### 4.3. status: bản sao thông tin của HTTP status

**status** là số nguyên cho biết mã HTTP mà origin server dùng cho lần xảy ra. Nó là một thành viên **advisory**: thông tin hữu ích khi tách body khỏi phản hồi HTTP gốc, nhưng **client HTTP phải dựa vào status thực trên response** để quyết định xử lý ở cấp giao thức.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/order-state-conflict",
 "title":"Order state conflict","status":409}
~~~

Nếu do lỗi ở middleware hoặc chuyển đổi proxy mà HTTP status là **500** trong khi body vẫn ghi **409**, phản hồi đang **mâu thuẫn**. Client không nên tự chuyển sang coi yêu cầu đã thành 409 chỉ vì body; cần ghi nhận sai lệch để chẩn đoán và sửa cách ánh xạ. Hợp đồng bình thường phải giữ hai giá trị đồng nhất.

### 4.4. detail: giải thích của lần xuất hiện

**detail** mô tả vấn đề đang xảy ra, chẳng hạn:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn đã giao nên không thể hủy; vui lòng xem trạng thái mới nhất."
}
~~~

Nội dung detail có thể bản địa hóa, điều chỉnh văn phong, hoặc bị lược bỏ khi có rủi ro lộ dữ liệu. Client **không được parse câu chữ detail** để xác định mã lỗi; nên dùng **type** hoặc trường mở rộng **code** đã công bố.

### 4.5. instance: định danh một lần xuất hiện

**instance** là URI reference định danh một sự kiện lỗi cụ thể. Nó **không nhất thiết** là URI resource mà người dùng vừa gọi và **không bắt buộc** phải có endpoint trả tài liệu.

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "instance": "/problems/occurrences/req-7fa9"
}
~~~

Nếu instance có thể truy xuất được, endpoint đó cũng phải kiểm tra quyền vì hồ sơ lỗi có thể chứa thông tin nhạy cảm. Nhiều API đơn giản dùng một **requestId/traceId** mở rộng và chỉ lưu liên kết tra cứu nội bộ, không xây endpoint công khai theo instance. Tránh đưa token, email, số tài khoản hay nội dung cá nhân vào URI vì URI thường xuất hiện trong log và hệ thống giám sát.

### 4.6. Bảng tổng kết

| Trường | Kiểu JSON | Có bắt buộc trong RFC? | Client nên dùng thế nào? |
| --- | --- | --- | --- |
| **type** | String chứa URI reference | Không; mặc định **about:blank** nếu thiếu. | Định danh loại lỗi có thể xử lý theo hợp đồng. |
| **title** | String | Không. | Hiển thị hoặc hỗ trợ người phát triển; không parse. |
| **status** | Number, mã HTTP | Không. | Thông tin bổ sung; HTTP response status là cơ sở. |
| **detail** | String | Không. | Hiển thị mô tả an toàn cho lần xảy ra. |
| **instance** | String chứa URI reference | Không. | Liên hệ một sự kiện để truy vết hoặc xem chi tiết theo quyền. |

**Có thể thiếu trường** là một phần ngữ nghĩa chuẩn. Nếu API nội bộ muốn luôn có type, title, status thì hãy quy định rõ trong OpenAPI và kiểm thử; đó là ràng buộc của **hợp đồng API cụ thể**, không phải điều kiện mọi phản hồi RFC 9457 phải thỏa.

## 5. Thiết kế problem type ổn định và có tài liệu

Problem type là đơn vị chính để client phân biệt các loại lỗi có cách xử lý khác nhau. Đừng tạo type theo tên class Java hoặc các câu tiếng Việt dễ thay đổi.

Ví dụ một tập type cho hệ thống đơn hàng:

| Type | HTTP status thường đi kèm | Khi nào phát sinh | Hướng xử lý client |
| --- | ---: | --- | --- |
| **/problems/order-not-found** | 404 | ID không tìm thấy hoặc không có representation được phép trả. | Hiển thị không tìm thấy; kiểm tra URI. |
| **/problems/invalid-order** | 422 | JSON hợp lệ nhưng giá trị nghiệp vụ không thể xử lý. | Hiển thị lỗi trường và yêu cầu sửa dữ liệu. |
| **/problems/order-state-conflict** | 409 | Đơn đang ở trạng thái không cho phép hủy. | Làm mới dữ liệu, giải thích trạng thái mới. |
| **/problems/version-conflict** | 412 | If-Match không thỏa khi cập nhật điều kiện. | Tải phiên bản hiện hành, hòa giải thay đổi. |
| **/problems/quota-exceeded** | 429 | Client hoặc tenant vượt giới hạn yêu cầu. | Giảm nhịp gọi, dùng Retry-After nếu có. |
| **/problems/dependency-unavailable** | 503 | Không thể phục vụ tạm thời theo hợp đồng API. | Có thể retry an toàn với backoff. |

Trong thực tế, nên dùng **URI đầy đủ** như **https://api.example.com/problems/invalid-order** trong payload; bảng trên lược phần host để dễ đọc.

Một type có thể được dùng với hơn một mã HTTP nếu tài liệu và ngữ nghĩa cho phép, nhưng không nên gom các lỗi có hành vi khắc phục khác nhau vào một loại “business-error” chung. Nếu thay đổi **ý nghĩa** problem type theo cách khiến client hiện tại xử lý sai, hãy định nghĩa type mới hoặc kế hoạch tương thích, thay vì âm thầm đổi semantics dưới URI cũ.

### 5.1. Tài liệu cho từng type nên có gì?

Một trang tài liệu problem type hữu ích trả lời:

- Loại vấn đề thể hiện điều kiện nào?
- Các status HTTP có thể đi kèm là gì?
- Client có thể sửa request hay phải thực hiện hành động khác?
- Có được retry không; nếu có, điều kiện, độ trễ, idempotency và giới hạn là gì?
- Những trường mở rộng nào có ý nghĩa và kiểu dữ liệu ra sao?
- Có trường hợp cần phân quyền hoặc che thông tin chi tiết không?
- Mã/type có được duy trì ổn định qua phiên bản API không?

Đừng yêu cầu SDK phải tải trang tài liệu theo URI type **trong lúc xử lý lỗi**. URI là định danh, còn hợp đồng client phải có sẵn qua tài liệu hoặc OpenAPI.

## 6. Trường mở rộng: khi nào cần và cách thiết kế

RFC 9457 cho phép thêm thành viên ngoài năm trường chuẩn. API đơn hàng có thể cần mã lỗi ổn định, danh sách trường validation và dấu vết để hỗ trợ.

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 422,
  "detail": "Một số trường của đơn hàng không hợp lệ.",
  "instance": "/problems/occurrences/req-8b41",
  "code": "ORDER_VALIDATION_FAILED",
  "requestId": "req-8b41",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "reason": "Phải lớn hơn 0"
    },
    {
      "name": "currency",
      "reason": "Không nằm trong danh sách hỗ trợ"
    }
  ]
}
~~~

Ở đây:

- **code**, **requestId** và **invalidParams** là trường **mở rộng tự thiết kế**; RFC không quy định sẵn cấu trúc hay tên này.
- **invalidParams** mô tả một danh sách lỗi trường, mỗi phần tử có **name**, **reason** theo hợp đồng riêng.
- Client có thể dùng **code** để liên kết với hành động nghiệp vụ hoặc bản dịch, nhưng cần phân biệt **code** với **type** và tránh tạo hai mã mâu thuẫn.

RFC khuyến nghị tên trường mở rộng nên bắt đầu bằng chữ cái, sử dụng chữ cái/chữ số/dấu gạch dưới và có ít nhất ba ký tự để dễ tương thích khi biểu diễn qua nhiều định dạng. Dùng tên rõ nghĩa, nhất quán và tránh vô tình trùng với các trường chuẩn.

### 6.1. Thiết kế extension có tính hợp đồng

| Quyết định | Gợi ý |
| --- | --- |
| Kiểu trường | Công bố rõ string, number, boolean, object hoặc array. |
| Mức độ bắt buộc | Nếu chỉ một problem type có **invalidParams**, đừng bắt mọi lỗi khác cung cấp mảng rỗng. |
| Tính ổn định | Không đổi tên hoặc ý nghĩa tùy tiện sau khi SDK đã sử dụng. |
| Dữ liệu nhạy cảm | Dùng tên trường an toàn; không trả lại giá trị mật khẩu, token, số thẻ, query SQL. |
| Bản địa hóa | **reason/detail/title** có thể dịch; **type/code/name** nên ổn định. |
| Tiến hóa | Client cần bỏ qua extension chưa biết; server cần giữ tương thích cho extension đã công bố. |

Nếu API trả lỗi validation của 50 trường, không nhất thiết phải gửi toàn bộ giá trị đầu vào trong response. Chỉ cần chỉ ra trường nào sai và quy tắc công khai nào bị vi phạm. Các lỗi nội bộ của validator không nên lộ qua response.

## 7. Chọn HTTP status phù hợp cho Problem Details

Problem Details **mô tả** lỗi; nó không quyết định thay việc chọn mã HTTP. Trước tiên phải xác định server đã hiểu và xử lý request tới đâu, sau đó chọn status và problem type.

| Tình huống | Status thường phù hợp | Ghi chú |
| --- | ---: | --- |
| JSON lỗi cú pháp, tham số sai định dạng | **400 Bad Request** | Request không thể parse hoặc không hợp lệ theo cấu trúc đã công bố. |
| Thiếu/hết hạn thông tin xác thực | **401 Unauthorized** | Phản hồi 401 phải có **WWW-Authenticate** phù hợp. |
| Có danh tính nhưng không đủ quyền | **403 Forbidden** | Có thể dùng 404 nếu chính sách che sự tồn tại của resource. |
| URI resource đơn lẻ không tồn tại | **404 Not Found** | Collection truy vấn thành công nhưng rỗng thường là **200 []**. |
| Phương thức không được phép ở resource | **405 Method Not Allowed** | Phản hồi phải có header **Allow**. |
| Resource đã ở trạng thái không cho phép thao tác | **409 Conflict** | Ví dụ hủy đơn đã giao. |
| **If-Match/If-None-Match** không thỏa | **412 Precondition Failed** | Không nên thay bằng 409 nếu lỗi thực sự là HTTP precondition. |
| Media type request không hỗ trợ | **415 Unsupported Media Type** | Ví dụ endpoint chỉ nhận JSON nhưng gửi XML. |
| JSON đúng cú pháp nhưng dữ liệu nghiệp vụ không xử lý được | **422 Unprocessable Content** | Một số API chọn 400 cho validation; cần thống nhất hợp đồng. |
| Server yêu cầu precondition nhưng client không gửi | **428 Precondition Required** | Hữu ích khi bắt buộc If-Match cho cập nhật. |
| Vượt rate limit | **429 Too Many Requests** | Có thể kèm **Retry-After**, header hạn mức theo hợp đồng. |
| Lỗi nội bộ ngoài dự kiến | **500 Internal Server Error** | Không trả stack trace chi tiết cho client. |
| Gateway nhận phản hồi upstream không hợp lệ | **502 Bad Gateway** | Có thể do reverse proxy/API gateway phát sinh. |
| Dịch vụ tạm không phục vụ | **503 Service Unavailable** | Có thể kèm **Retry-After**. |
| Gateway chờ upstream quá hạn | **504 Gateway Timeout** | Request phía sau **có thể đã commit**. |

Các mã như **401**, **405** còn yêu cầu header của giao thức: body Problem Details không thể thay thế chúng. Không phải mọi lỗi 4xx đều do người dùng “làm sai”, cũng không phải mọi 5xx đều bắt nguồn từ controller. Gateway có thể tự phát 502/503/504 trước khi request tới ứng dụng.

### 7.1. 400 hay 422?

Ví dụ không parse được JSON:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"quantity":

HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/malformed-json",
 "title":"Malformed JSON","status":400}
~~~

Ví dụ JSON có cấu trúc hợp lệ nhưng số lượng âm:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json

{"items":[{"sku":"SKU-1","quantity":-2}]}

HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/invalid-order",
 "title":"Invalid order","status":422,
 "invalidParams":[{"name":"items[0].quantity","reason":"Phải lớn hơn 0"}]}
~~~

Đây là hai **minh họa request/response nối tiếp**, không phải một khối dữ liệu HTTP truyền đi nguyên văn. 400 và 422 đều cần tài liệu về điều kiện phát sinh; không đưa mọi lỗi validation vào 500.

### 7.2. 401 và 403 khác nhau

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/authentication-required",
 "title":"Authentication required","status":401}
~~~

**401** liên quan đến xác thực chưa hợp lệ và có thử thách xác thực. **403** là từ chối quyền truy cập dù server hiểu yêu cầu. Với resource có chính sách bảo mật đặc biệt, server có thể trả **404** để không xác nhận tài nguyên tồn tại. Phải kiểm tra quyền cho cả request thành công lẫn thông báo lỗi, tránh problem body vô tình tiết lộ resource khác tenant.

### 7.3. 409 và 412 khác nhau

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/order-state-conflict",
 "title":"Order state conflict","status":409,
 "detail":"Không thể hủy đơn đã giao."}
~~~

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/version-conflict",
 "title":"Precondition failed","status":412,
 "detail":"ETag của bản ghi đã thay đổi."}
~~~

Nếu client gửi **PATCH /orders/ord-123** với **If-Match: "v4"** nhưng bản hiện tại là **"v5"**, điều kiện HTTP thất bại: **412** phù hợp. Nếu yêu cầu hợp lệ nhưng không thể hủy vì trạng thái đã SHIPPED, **409** phù hợp. Client không nên tự động retry như nhau cho hai trường hợp: 412 thường đòi đọc lại phiên bản, còn 409 cần quyết định nghiệp vụ.

## 8. Thiết kế phản hồi riêng cho 429 và lỗi tạm thời 5xx

API đặt giới hạn 100 request/phút cho một client. Khi vượt ngưỡng:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/rate-limit-exceeded",
  "title": "Too many requests",
  "status": 429,
  "detail": "Đã vượt giới hạn yêu cầu trong khoảng thời gian hiện tại."
}
~~~

**Retry-After: 30** hướng dẫn chờ khoảng 30 giây trước khi thử lại. Header này cũng có thể dùng ngày HTTP; **không bảo đảm** sau khoảng chờ thao tác chắc chắn thành công. Client cần có backoff, jitter, số lần thử tối đa, kiểm soát ngân sách timeout và chính sách rate limit.

Khi dịch vụ bảo trì hoặc quá tải tạm thời:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 60
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/temporarily-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503
}
~~~

Với **500**, không nên gửi chi tiết nội bộ:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: req-3f8d

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "Không thể xử lý yêu cầu vào lúc này.",
  "requestId": "req-3f8d"
}
~~~

Stack trace, SQL statement, đường dẫn file, tên máy chủ nội bộ và khóa bí mật thuộc phạm vi log/trace được kiểm soát, không phải response công khai.

**Một điều không thể bỏ qua:** nếu client gửi POST tạo thanh toán nhưng thấy **504 Gateway Timeout**, request phía sau có thể đã được xử lý và ghi dữ liệu trước khi gateway hết thời gian chờ. Problem Details không tự tạo idempotency; cần **Idempotency-Key**, cơ chế tra cứu trạng thái hoặc giao thức retry an toàn theo hợp đồng.

## 9. Problem Details và xử lý nhiều lỗi validation

RFC 9457 tập trung mô tả một problem type. Với một request có nhiều trường nhập sai thuộc **cùng loại validation problem**, API có thể đưa danh sách chi tiết vào extension.

~~~json
{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 422,
  "detail": "Có 3 trường cần chỉnh sửa.",
  "invalidParams": [
    {"name": "items[0].quantity", "reason": "Phải lớn hơn 0"},
    {"name": "items[1].sku", "reason": "Mã sản phẩm không hợp lệ"},
    {"name": "shippingAddress.postalCode", "reason": "Không đúng định dạng"}
  ]
}
~~~

**invalidParams** không phải trường chuẩn của RFC. Cần tự quy định:

1. Đường dẫn trường dùng tên JSON, Java Bean property, JSON Pointer hay cú pháp riêng? Hãy chọn một cách và giữ ổn định.
2. Một trường có thể có nhiều lỗi không? Thứ tự lỗi có được bảo đảm không?
3. Lỗi phần tử collection dùng chỉ số tại thời điểm request hay ID ổn định?
4. Lỗi nghiệp vụ không gắn với một trường được trình bày thế nào?
5. Có giới hạn tối đa số lỗi để tránh phản hồi quá lớn hoặc lộ dữ liệu không?

Nếu một request có nhiều loại vấn đề độc lập (ví dụ xung đột quyền, validation và timeout phụ thuộc), không nên tùy tiện ghép thành ba status khác nhau trong một body. Server phải chọn status cuối phản ánh đúng điều kiện ưu tiên xử lý và nêu phần thông tin liên quan an toàn. Các quy trình batch có kết quả từng phần có thể cần mô hình kết quả riêng, không thể mặc định thay thế bằng một Problem Details chứa mọi trạng thái con.

## 10. Tích hợp với pipeline HTTP và các thành phần trung gian

~~~mermaid
flowchart LR
    C[Client / SDK] --> G[API Gateway]
    G --> S[Security Filter]
    S --> V[Parsing / Validation]
    V --> H[Controller / Service]
    H --> D[(Database)]
    G -.->|429 / 502 / 504| R[HTTP response]
    S -.->|401 / 403| R
    V -.->|400 / 415 / 422| R
    H -.->|404 / 409 / 412 / 500| R
    R --> C
~~~

**Không phải mọi lỗi đi qua controller.** Phân loại nguồn phát sinh giúp chọn nơi chuẩn hóa response:

| Tầng | Lỗi điển hình | Nơi cấu hình |
| --- | --- | --- |
| API gateway / reverse proxy | 429, 502, 503, 504, lỗi kích thước request. | Gateway policy, reverse proxy error handler, routing. |
| Xác thực / phân quyền | 401, 403. | Security filter, authentication entry point, access denied handler. |
| Parser / content negotiation | 400, 406, 415. | HTTP framework, message converter và exception mapping. |
| Bean validation / domain validation | 400 hoặc 422 theo hợp đồng. | Validation handler và service. |
| Resource/domain service | 404, 409, 412, 428. | Service exception mapping / controller advice. |
| Lỗi không dự kiến | 500. | Global exception handler có log và response an toàn. |

Ứng dụng có thể chuẩn hóa hầu hết response lỗi của mình thành Problem Details, nhưng **gateway hoặc hạ tầng khác vẫn có thể trả HTML, text hoặc body rỗng**. Client phải có phương án fallback; tránh giả định mọi non-2xx đều là JSON.

### 10.1. Caching của phản hồi lỗi

Một số status, ví dụ **404**, có thể được cache theo quy tắc HTTP nếu không có chỉ thị ngăn phù hợp. Thông tin lỗi có thể chứa ID truy vấn, trạng thái quyền hoặc dữ liệu nhạy cảm; nên thiết kế **Cache-Control** theo phạm vi và tính nhạy cảm. Với thông tin cụ thể của tài khoản hoặc phiên đăng nhập, **Cache-Control: no-store** thường là lựa chọn dễ bảo vệ hơn.

Problem Details có **status**, **type** và **instance** không tự làm response “không cache được”. Hành vi cache vẫn phụ thuộc status/header và các quy định HTTP.

### 10.2. Ngôn ngữ và tính ổn định

API có thể đọc **Accept-Language** để trả title/detail tiếng Việt hay tiếng Anh, kèm **Content-Language** nếu phù hợp. **type** và mã extension ổn định; không dịch URI type, code hoặc tên trường validation. Client không nên dùng tiếng Việt/Anh của title làm khóa điều khiển.

## 11. Triển khai bằng Java/Spring: từ exception tới ProblemDetail

Spring Framework 6 và Spring Boot 3 có kiểu **ProblemDetail**, giúp xây dựng phản hồi lỗi theo mô hình RFC. Ví dụ minh họa dưới đây giả định một REST API quản lý đơn hàng; các lớp domain là ví dụ và cần được triển khai ở dự án thực tế.

### 11.1. Lỗi nghiệp vụ có kiểu rõ ràng

~~~java
public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException() {
        super("Order not found");
    }
}

public class OrderStateConflictException extends RuntimeException {
    public OrderStateConflictException() {
        super("Order cannot be changed in current state");
    }
}
~~~

Nên ném exception hoặc trả kiểu kết quả thể hiện lỗi **theo nghĩa nghiệp vụ** (không tồn tại, xung đột trạng thái) thay vì cho domain service biết quá nhiều chi tiết HTTP. Lớp biên API chịu trách nhiệm ánh xạ loại vấn đề đó sang mã HTTP.

### 11.2. Xây dựng ProblemDetail bằng @RestControllerAdvice

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiProblemHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            OrderNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy đơn hàng yêu cầu.");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    @ExceptionHandler(OrderStateConflictException.class)
    public ResponseEntity<ProblemDetail> conflict(
            OrderStateConflictException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Trạng thái hiện tại không cho phép thao tác này.");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-state-conflict"));
        problem.setTitle("Order state conflict");
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Điểm cần chú ý:

- **ResponseEntity.status(...)** đặt đúng HTTP status thực tế.
- **ProblemDetail.forStatusAndDetail(...)** tạo body với status/detail tương ứng.
- **setType(...)** và **setTitle(...)** xác định problem type ổn định.
- **setProperty(...)** thêm extension; trong cơ chế tuần tự hóa ProblemDetail của Spring, các thuộc tính mở rộng được hiển thị như thành viên JSON.
- Tránh lấy **ex.getMessage()** đưa thẳng vào **detail** cho mọi loại exception: exception có thể mang dữ liệu nội bộ hoặc do bên thứ ba tạo.

Ở môi trường thật, các exception như lỗi kết nối database cần log an toàn và trả problem type chung với **500**, không trả đường dẫn máy chủ hoặc câu truy vấn.

### 11.3. Trả danh sách validation errors

Ví dụ handler chọn **422** cho lỗi Bean Validation xảy ra sau khi JSON đã parse:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record InvalidParam(String name, String reason) {}

@RestControllerAdvice
class ValidationProblemHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalid(
            MethodArgumentNotValidException exception) {
        List<InvalidParam> issues = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new InvalidParam(
                        error.getField(),
                        "Giá trị không hợp lệ"))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "Có trường không đáp ứng quy tắc dữ liệu.");
        problem.setType(URI.create(
                "https://api.example.com/problems/invalid-order"));
        problem.setTitle("Invalid order");
        problem.setProperty("invalidParams", issues);

        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Đây là **minh họa mapping tùy chỉnh**. Spring MVC thường trả **400** cho lỗi binding/validation theo mặc định; nếu API chọn **422**, cần thống nhất controller advice, OpenAPI và test. Không phải mọi **MethodArgumentNotValidException** trong mọi endpoint đều phải mang type **invalid-order**: ứng dụng thật nên chọn type theo phạm vi hoặc xây handler chung với quy tắc rõ ràng.

Mẫu trên cố tình dùng lý do validation tổng quát để tránh vô tình echo giá trị nhạy cảm. Với form không nhạy cảm, có thể dùng message từ validator sau khi kiểm soát nội dung, mã hóa output và hạn chế thông tin được trả.

### 11.4. Lỗi 401/403 thuộc Spring Security

Trong Spring Security, nhiều request bị chặn **trước khi vào controller**, nên **@RestControllerAdvice** có thể không được gọi cho 401/403. Cần cấu hình **AuthenticationEntryPoint** và **AccessDeniedHandler** để trả đúng status, header và Problem Details. Với bearer token, một phản hồi **401** phải có **WWW-Authenticate** theo cơ chế xác thực tương ứng.

Không nên coi một handler Exception chung là cách giải quyết mọi lỗi của security filter. Cũng cần kiểm tra khi gateway tự từ chối token hoặc rate-limit: đó là tầng khác với Spring application.

### 11.5. Cách kiểm soát lỗi 500

Global handler có thể ghi log chi tiết nội bộ kèm request/trace ID, nhưng trả body an toàn như:

~~~json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "Hệ thống chưa thể xử lý yêu cầu.",
  "requestId": "req-3f8d"
}
~~~

Khi phát triển có thể cần stack trace, nhưng chỉ log tại hệ thống quan sát có phân quyền; không để chế độ debug hay error page mặc định lộ ra production.

## 12. Mô tả hợp đồng Problem Details bằng OpenAPI 3.1

Định nghĩa một schema chung và tái sử dụng trong từng phản hồi lỗi giúp frontend, SDK và kiểm thử cùng hiểu hợp đồng. Ví dụ rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Đơn hàng được tìm thấy
        '401':
          description: Chưa xác thực hợp lệ
          headers:
            WWW-Authenticate:
              description: Thử thách xác thực phù hợp
              schema:
                type: string
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '403':
          description: Không được phép truy cập
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '404':
          description: Không tìm thấy đơn hàng
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '500':
          description: Lỗi nội bộ không mong đợi
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  schemas:
    Problem:
      type: object
      description: >
        Cấu trúc Problem Details theo RFC 9457.
        Các thành viên chuẩn là tùy chọn theo RFC;
        API có thể ràng buộc thêm tùy từng endpoint.
      properties:
        type:
          type: string
          format: uri-reference
          default: about:blank
        title:
          type: string
        status:
          type: integer
          minimum: 100
          maximum: 599
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
          description: Mã lỗi mở rộng do Orders API định nghĩa
        requestId:
          type: string
          description: Mã tra cứu sự kiện khi được cung cấp
      additionalProperties: true
~~~

**Lưu ý về schema:**

- Không đặt **required: [type, title, status]** nếu mục tiêu là biểu diễn đầy đủ khả năng của RFC 9457; chuẩn không bắt cả ba trường phải hiện diện. Nếu tổ chức yêu cầu chúng, hãy ghi rõ đó là quy định riêng.
- **additionalProperties: true** cho phép extension. Có thể tạo schema con cho problem type **invalid-order** để định nghĩa **invalidParams** chính xác.
- Phản hồi **401** vẫn cần header **WWW-Authenticate**; chỉ có body JSON là chưa đủ.
- Mẫu trên không định nghĩa cấu trúc resource, auth schemes hoặc toàn bộ mã lỗi của mọi endpoint; trong dự án thật hãy khai báo rõ các trường hợp 409/412/422/429/503 tùy thao tác.

## 13. Client nên diễn giải Problem Details như thế nào?

Client phải xử lý **status HTTP trước**, sau đó giải thích body nếu media type và nội dung phù hợp. Không được giả định trường **detail** hay **title** dùng làm mã nghiệp vụ.

### 13.1. Luồng xử lý tham khảo

~~~mermaid
flowchart TD
    A[Nhận HTTP response] --> B{Status thuộc loại thành công?}
    B -->|Có| C[Xử lý representation theo endpoint]
    B -->|Không| D{Content-Type là application/problem+json?}
    D -->|Không| E[Xử lý lỗi dự phòng bằng status/header]
    D -->|Có| F[Parse JSON an toàn]
    F --> G{Body là object hợp lệ?}
    G -->|Không| E
    G -->|Có| H[Đọc type, extensions đã biết]
    H --> I[Xử lý theo status + type + header]
    I --> J[Hiển thị thông tin an toàn và ghi requestId]
~~~

Giả mã:

~~~text
response = send(request)
httpStatus = response.status

if response is successful:
    return parseSuccessfulResource(response)

problem = null
if Content-Type indicates application/problem+json:
    problem = tryParseJsonObject(response.body)

type = problem.type if valid URI reference else "about:blank"
safeMessage = problem.detail or problem.title or genericMessage(httpStatus)

switch httpStatus:
    401: run authentication flow if applicable
    403: report insufficient permission
    409: use documented type/code to guide conflict resolution
    412: refresh resource version and review changes
    429: obey Retry-After when present, apply bounded backoff
    502/503/504: consider retry safety and idempotency first
    default: show safe error and requestId
~~~

Đây là **giả mã diễn giải hợp đồng**, không phải mã nguồn có thể chạy trực tiếp. Nếu type chưa biết, client vẫn phải có cách xử lý theo status. Nếu type bị thiếu, áp dụng ngữ nghĩa **about:blank**; client nên bỏ qua extension không biết để không bị hỏng khi server thêm thuộc tính.

### 13.2. Không retry POST chỉ vì nhận 5xx

Ví dụ gửi **POST /payments** rồi thấy **504**. Có thể dịch vụ thanh toán đã commit và gateway chỉ không nhận được response đúng hạn. Client phải tra cứu bằng ID giao dịch hoặc dùng **Idempotency-Key** và cơ chế chống trùng do server thực thi; nếu gửi lại tùy tiện, có thể trừ tiền hai lần. Problem body giúp client biết đó là gateway timeout, nhưng **không chứng minh kết quả giao dịch nghiệp vụ**.

### 13.3. Hiển thị cho người dùng và thông tin dành cho hỗ trợ

Một UI có thể hiển thị:

> Không thể hủy đơn hàng vì đơn đã được bàn giao. Vui lòng tải lại trạng thái đơn. Mã hỗ trợ: req-7fa9.

UI không nên hiển thị nguyên **instance URI**, stack trace hay đối tượng JSON kỹ thuật cho người dùng cuối. Đường hỗ trợ có thể dùng requestId để tìm log nội bộ, trong khi logic ứng dụng dùng type/code để quyết định hướng xử lý.

## 14. Bảo mật, riêng tư và khả năng vận hành

### 14.1. Thông tin nào không nên xuất hiện?

| Dữ liệu | Rủi ro nếu trả qua Problem Details | Thay thế |
| --- | --- | --- |
| Stack trace, tên class nội bộ | Lộ cấu trúc hệ thống, thư viện và luồng xử lý. | Ghi trong log bảo vệ; trả loại lỗi chung. |
| SQL và thông tin kết nối DB | Lộ schema, câu truy vấn, hostname, credential. | Lỗi 500 an toàn và requestId. |
| Token, cookie, API key | Có thể bị đánh cắp, tái sử dụng. | Không echo; che/redact từ đầu vào tới log. |
| Thông tin khách hàng khác tenant | Vượt ranh giới phân quyền. | Kiểm tra authorization trước khi mô tả resource. |
| Dữ liệu cá nhân trong instance URI | URI thường được ghi vào access log, tracing và proxy. | Dùng opaque requestId/instance không chứa PII. |
| Message nguyên văn từ upstream | Có thể lộ chi tiết hoặc chứa nội dung không đáng tin cậy. | Ánh xạ sang message an toàn do API kiểm soát. |

**404 thay cho 403** đôi khi được dùng để không xác nhận sự tồn tại của tài nguyên nhạy cảm. Nếu chọn cách này, body Problem Details không được nói “đơn hàng có thật nhưng thuộc người khác”. Mã lỗi và thời gian phản hồi cũng cần được đánh giá để tránh lộ thông tin ngoài ý muốn.

### 14.2. Quan sát end-to-end

Để điều tra lỗi hiệu quả, log và trace nên chứa:

- HTTP method và **route template** (tránh log toàn bộ path có PII).
- HTTP status quan sát tại gateway và status từ origin nếu đo được.
- **type** hoặc **code** của Problem Details.
- Request/correlation ID, trace ID, service, môi trường và thời điểm.
- Tốc độ lỗi và độ trễ theo endpoint, tenant hoặc nhóm client ở mức được phép.
- Dấu hiệu retry, idempotency key đã được xử lý an toàn và vị trí thất bại.

Không đưa toàn bộ body lỗi vào log mặc định nếu body có thông tin cá nhân. Hãy kiểm soát quyền truy cập, thời hạn giữ và mức sampling. Dashboard nên phân biệt **409/412** (xung đột dự kiến) với **500/502/503/504** (sự cố hệ thống) và **429** (giới hạn lưu lượng); gom mọi non-2xx vào một biểu đồ duy nhất có thể che khuất nguyên nhân.

### 14.3. Tính tương thích qua phiên bản

- Giữ ổn định URI **type** khi ngữ nghĩa còn giữ nguyên.
- Có thể thêm trường mở rộng mới nếu client được thiết kế bỏ qua trường lạ.
- Không đổi một **code** cũ từ “thiếu quyền” sang “giới hạn lưu lượng” dưới cùng mã.
- Nếu thay đổi cấu trúc **invalidParams**, cần kế hoạch phiên bản hoặc hợp đồng tương thích.
- Không buộc client parse **detail** vì nội dung có thể thay đổi theo bản dịch.
- Tài liệu OpenAPI và test nên phản ánh các response do security filter và gateway có thể phát ra.

## 15. Kiểm thử hợp đồng Problem Details

Một bài kiểm thử không chỉ đối chiếu chuỗi JSON; phải kiểm tra **status, header, media type, nội dung và không có tác dụng phụ sai**.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| P01 | GET ID đơn không tồn tại | **404**, Content-Type **application/problem+json**, type **order-not-found**. |
| P02 | POST JSON sai cú pháp | **400**, không trả stack trace, không tạo resource. |
| P03 | POST trường quantity âm | **422** hoặc **400** đúng hợp đồng, extension invalidParams hợp lệ. |
| P04 | Không có bearer token | **401**, **WWW-Authenticate** phù hợp, body không lộ thông tin tài khoản. |
| P05 | User A truy cập đơn của tenant B | **403** hoặc **404** theo chính sách; body không xác nhận thông tin nhạy cảm. |
| P06 | POST hủy đơn đã giao | **409**, type ổn định; resource không bị sửa. |
| P07 | PATCH với ETag cũ | **412**, resource không bị ghi đè. |
| P08 | Vượt rate limit | **429**, xử lý Retry-After nếu có; body theo hợp đồng. |
| P09 | Upstream không phản hồi đúng hạn | **504** từ gateway; client có fallback nếu không có Problem Details. |
| P10 | Lỗi nội bộ ngoài dự kiến | **500**, thông điệp an toàn, có requestId nếu được quy định. |
| P11 | Đổi ngôn ngữ Accept-Language | Title/detail có thể đổi; type/code ổn định. |
| P12 | Server thêm extension mới | SDK cũ bỏ qua trường lạ và vẫn xử lý theo status/type. |
| P13 | Body thiếu type/title/detail | SDK fallback đúng ngữ nghĩa type mặc định và status HTTP. |
| P14 | Body status khác HTTP status | Hệ thống phát hiện sai hợp đồng; client ưu tiên status thực. |
| P15 | HTTP 204 hoặc 304 | Không có body; không cố parse Problem Details. |

### 15.1. Ví dụ kiểm thử Spring MockMvc

Giả sử có endpoint GET /orders/{id}, lớp handler đã cấu hình và bộ test sử dụng Spring MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.springframework.http.MediaType;

mockMvc.perform(get("/orders/{id}", "missing-order"))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/order-not-found"))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.title").value("Order not found"));
~~~

Ví dụ giả định endpoint chấp nhận ID dạng chuỗi **missing-order** và có thể tới handler không tìm thấy. Nếu controller nhận UUID, một chuỗi ID không đúng định dạng sẽ lỗi trước tầng tra cứu, dẫn tới 400 theo hợp đồng; test phải dùng một UUID hợp lệ nhưng chưa tồn tại. Với API có Spring Security, cung cấp danh tính thử hợp lệ để request đi qua kiểm tra xác thực trước khi test 404.

### 15.2. Kiểm tra lỗi validation

~~~java
mockMvc.perform(
        post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"items\":[{\"sku\":\"SKU-1\",\"quantity\":-2}]}"))
    .andExpect(status().isUnprocessableEntity())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/invalid-order"))
    .andExpect(jsonPath("$.invalidParams").isArray());
~~~

Test trên chỉ phù hợp nếu các trường khác của payload đã hợp lệ hoặc validator vẫn tạo problem type chung; trong hệ thống thật nên dùng dữ liệu mẫu đầy đủ hợp đồng. Nếu chọn 400 cho validation, sửa kỳ vọng cho nhất quán.

Đối với 401/403, cần integration test qua security filter và những đường do gateway chặn. **MockMvc chỉ thấy phản hồi trong phạm vi Spring**, không tự xác nhận API gateway luôn trả Problem Details hoặc xử lý đúng status khi upstream lỗi.

### 15.3. Kiểm thử SDK và khả năng tương thích

Ngoài kiểm thử server, kiểm thử client với các trường hợp:

1. Response **application/problem+json** có đầy đủ và thiếu từng field chuẩn.
2. Body là HTML/plain text do gateway phát, JSON lỗi cú pháp, body rỗng.
3. Có tham số trên Content-Type như **application/problem+json; charset=utf-8**.
4. **type** chưa biết và extension mới xuất hiện.
5. Title/detail bản địa hóa nhưng code/type giữ nguyên.
6. 429/503 có Retry-After; retry phải dừng theo giới hạn.
7. 504 sau POST đã commit: thử lại phải dùng idempotency hoặc endpoint tra cứu, không tạo tác dụng phụ hai lần.

## 16. Bài tập thực hành: chuẩn hóa lỗi của hệ thống đặt hàng

### 16.1. Đề bài

Một nhóm phát triển đang vận hành ba endpoint:

- **POST /orders** tạo đơn hàng với bearer token.
- **PATCH /orders/{id}** chỉnh sửa ghi chú đơn với header If-Match.
- **POST /orders/{id}/cancel** hủy đơn nếu chưa giao.

Hệ thống hiện có các phản hồi thiếu nhất quán:

~~~json
{"error":"BAD_DATA","message":"quantity must be positive"}
~~~

~~~json
{"success":false,"statusCode":200,"message":"order already shipped"}
~~~

~~~json
{"exception":"java.sql.SQLException","detail":"connection to db01 failed"}
~~~

Gateway còn trả 504 khi orders-service quá chậm, nhưng SDK hiện luôn gọi **response.json()** và cố đọc **message** cho mọi lỗi.

Yêu cầu:

1. Chọn HTTP status và problem type phù hợp cho lỗi quantity âm, hủy đơn đã giao và lỗi nội bộ DB.
2. Viết Problem Details cho từng tình huống, có extension cần thiết mà không lộ thông tin nhạy cảm.
3. Định nghĩa trường **invalidParams** để UI hiển thị lỗi theo field.
4. Thiết kế fallback khi lỗi đến từ gateway và body không phải Problem Details.
5. Viết kế hoạch kiểm thử bảo đảm **PATCH với If-Match cũ** không ghi đè dữ liệu.
6. Giải thích vì sao chỉ đổi JSON mà giữ HTTP **200** cho lỗi không giải quyết được vấn đề.

### 16.2. Một lời giải tham khảo

**Validation:** nếu JSON đúng cú pháp nhưng quantity âm, chọn **422 Unprocessable Content** cho hợp đồng này:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 422,
  "invalidParams": [
    {"name":"items[0].quantity","reason":"Phải lớn hơn 0"}
  ]
}
~~~

**Xung đột trạng thái:** đơn SHIPPED không được hủy, chọn **409 Conflict**:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

**Lỗi nội bộ:** database mất kết nối, trả **500 Internal Server Error** với thông tin chung:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "requestId": "req-9d11"
}
~~~

**Gateway timeout:** nếu gateway phát **504** mà body không đúng media type, SDK vẫn xử lý theo HTTP status và thông báo chung, ghi requestId nếu có. Nếu đây là POST tạo đơn, client kiểm tra trạng thái hoặc retry với **Idempotency-Key** theo hợp đồng để tránh tạo trùng.

**PATCH với If-Match cũ:** trước khi PATCH, client GET resource và nhận ETag **"order-v3"**. Một request khác cập nhật lên **"order-v4"**. Khi client gửi If-Match **"order-v3"**, API trả **412 Precondition Failed** cùng problem type **version-conflict**; dữ liệu v4 không bị ghi đè. Test phải xác nhận cả response và trạng thái resource còn nguyên.

Nếu giữ **HTTP 200** với body **success: false**, HTTP client/gateway có thể hiểu request thành công, bỏ qua nhánh lỗi, cache hoặc báo cáo metric sai; client vẫn cần biết từng cấu trúc tùy tiện. Việc dùng status đúng đi kèm Problem Details mới tạo hợp đồng xuyên tầng.

### 16.3. Câu hỏi mở rộng

- Nếu API hỗ trợ tiếng Việt và tiếng Anh, những field nào có thể dịch? Field nào cần ổn định cho client?
- Nếu một tài nguyên không tồn tại hoặc thuộc tenant khác, cùng một problem type có thể được dùng để che sự tồn tại không? Cần kiểm soát điều gì trong body?
- Nếu client thấy response HTTP **503** nhưng body status là **500**, nên dựa vào mã nào để quyết định retry ở cấp HTTP?
- Nếu endpoint xóa thành công trả **204**, có nên kèm Problem Details để nói “xóa thành công” không?

**Gợi ý:** title/detail có thể dịch, type/code ổn định; chính sách che resource phải nhất quán và không rò dữ liệu; HTTP status thực được ưu tiên; phản hồi 204 không mang body và không cần payload lỗi.

## 17. Checklist trước khi công bố hợp đồng lỗi

- [ ] Status HTTP phản ánh đúng kết quả, không trả 200 cho lỗi nghiệp vụ hoặc hệ thống.
- [ ] Content-Type là **application/problem+json** cho phản hồi lỗi JSON theo hợp đồng.
- [ ] Nắm rõ năm thành viên chuẩn và các giá trị mặc định; không nhận nhầm extension là thành viên RFC bắt buộc.
- [ ] Problem type dùng URI ổn định, có tài liệu ý nghĩa, status và cách xử lý.
- [ ] Title là tóm tắt của loại lỗi; detail là thông tin lần xảy ra, không dùng câu chữ làm mã logic.
- [ ] Status trong body nhất quán với HTTP status, nhưng client ưu tiên mã HTTP thực tế.
- [ ] Instance/requestId dùng để truy vết an toàn, không chứa PII hoặc token.
- [ ] Extension như **code** và **invalidParams** có schema, phạm vi, quy tắc version và xử lý trường chưa biết.
- [ ] Lỗi parse, validation, auth, permission, conflict, precondition, rate limit và internal được phân biệt.
- [ ] **401** có WWW-Authenticate; **405** có Allow; 429/503 cung cấp Retry-After khi hợp lý.
- [ ] Lỗi do security filter và gateway được xem xét, client có fallback với body rỗng/HTML/không hợp lệ.
- [ ] Không trả stack trace, SQL, secret, thông tin hạ tầng nội bộ hoặc dữ liệu tenant khác.
- [ ] Cache-Control và Content-Language được đặt theo tính nhạy cảm và hợp đồng localization.
- [ ] OpenAPI mô tả reusable Problem schema và các response error thực tế của endpoint.
- [ ] Spring exception handlers/validation/security mapping và contract tests trả cùng ngữ nghĩa.
- [ ] Client không parse title/detail để quyết định; retry xét thêm idempotency và trạng thái giao dịch.
- [ ] Monitoring phân biệt status theo route/hop và ghi requestId/type để điều tra, không lộ body nhạy cảm.

**Điểm cốt lõi:** RFC 9457 giúp API diễn đạt **loại vấn đề** bằng **type**, mô tả bằng **title/detail**, bổ sung **status/instance** khi hữu ích và mở rộng thông tin theo hợp đồng riêng. **HTTP status và các header giao thức vẫn quyết định ý nghĩa của phản hồi**; Problem Details giúp client và người vận hành hiểu, xử lý và theo dõi lỗi nhất quán. Giá trị lớn nhất đến từ việc áp dụng cùng quy tắc trên ứng dụng, framework, security, gateway, OpenAPI và bộ kiểm thử.
