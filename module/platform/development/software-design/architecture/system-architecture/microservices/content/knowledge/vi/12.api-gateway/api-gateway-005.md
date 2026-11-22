# Định dạng lỗi và bảo vệ hợp đồng công khai

## 1. Vì sao định dạng lỗi là một phần của kiến trúc API Gateway?

Trong kiến trúc microservices, API Gateway là điểm vào chung cho web, mobile, đối tác hoặc các client khác. Gateway có thể định tuyến đến nhiều dịch vụ, xác thực, giới hạn lưu lượng, kiểm soát truy cập, chuyển đổi giao thức và tổng hợp kết quả. Chính vì vậy, Gateway còn là **ranh giới hợp đồng công khai**: điều mà client được phép biết về hệ thống và có thể dựa vào để xử lý.

Hãy tưởng tượng cùng một ứng dụng bán hàng gọi ba chức năng:

- Catalog Service trả về cấu trúc lỗi gồm code và message khi không tìm thấy sản phẩm.
- Order Service trả về một chuỗi tiếng Anh khi dữ liệu đặt hàng không hợp lệ.
- Payment Service trả về thông báo nội bộ kèm tên exception và câu lệnh SQL khi xảy ra lỗi.

Nếu Gateway chỉ truyền nguyên xi các phản hồi này, client phải hiểu định dạng khác nhau cho từng endpoint. Khi một service đổi framework, đường dẫn, exception hoặc schema, ứng dụng mobile có thể vỡ dù API công khai về mặt nghiệp vụ không thay đổi. Thậm chí lỗi nội bộ có thể vô tình tiết lộ dữ liệu nhạy cảm.

Vì vậy cần thiết kế **public error contract**: một hợp đồng mô tả cách hệ thống công khai lỗi, gồm HTTP status, kiểu lỗi có cấu trúc, mã ổn định, thông điệp cho người dùng, dữ liệu chi tiết được phép lộ, khả năng retry và định danh dùng khi hỗ trợ.

**Nguyên tắc trung tâm:**
1. Client dựa vào các tín hiệu có hợp đồng rõ ràng, không parse câu chữ tự do.
2. Gateway chuyển đổi lỗi từ upstream thành dạng công khai nhất quán khi cần, nhưng không che giấu sai bản chất lỗi.
3. Lỗi có thể được chẩn đoán qua logs/traces nội bộ mà không đưa stack trace hoặc chi tiết hạ tầng ra internet.
4. Hợp đồng lỗi được phiên bản hóa, kiểm thử và thay đổi có kiểm soát như hợp đồng thành công.

Bài học này hướng tới REST/HTTP API với microservices và API Gateway. Các nguyên tắc về mã ổn định, bảo mật, khả năng tương thích và truy vết vẫn có thể áp dụng với GraphQL, gRPC hoặc message-based API, nhưng chi tiết status và envelope cần theo giao thức tương ứng.

## 2. Phân biệt lỗi nghiệp vụ, lỗi giao thức và lỗi hạ tầng

Không nên coi mọi lỗi là một HTTP 500 hoặc mọi trường hợp không đạt mục tiêu nghiệp vụ đều là “server bị lỗi”.

| Nhóm | Ví dụ | Chủ sở hữu ý nghĩa | Cách phản hồi thường gặp |
| --- | --- | --- | --- |
| Dữ liệu đầu vào không hợp lệ | Thiếu trường bắt buộc, kiểu giá trị sai | API contract/service nhận | 400 hoặc 422 theo quy ước đã công bố |
| Xác thực | Không có token, token không hợp lệ | Lớp authentication | 401 với cơ chế challenge phù hợp |
| Phân quyền | Đã xác thực nhưng không có quyền | Chính sách truy cập | 403 hoặc 404 khi cần ẩn tài nguyên theo chính sách |
| Không tìm thấy | Product ID không tồn tại | Service sở hữu tài nguyên | 404 |
| Xung đột nghiệp vụ | Phiên bản đơn cũ, mã đặt chỗ đã bị dùng | Domain service | 409 hoặc 412 tùy cơ chế |
| Giới hạn tần suất | Vượt rate limit/quota | Gateway hoặc quota owner | 429 |
| Dịch vụ tạm không sẵn sàng | Downstream bảo trì, overload | Gateway/upstream | 503, đôi khi 502 tùy lỗi cụ thể |
| Upstream không phản hồi đúng hạn | Gateway hết thời gian đợi upstream | Gateway | 504 khi đúng semantics |
| Lỗi nội bộ không mong đợi | Bug, exception chưa xử lý | Service hoặc Gateway | 500 |
| Kết quả chưa xác định | Payment timeout sau khi gửi request | Service sở hữu operation | Status pending/query outcome theo contract, không tự ghi FAILED |

**Điểm mấu chốt:** lỗi giao tiếp không nhất thiết là thất bại nghiệp vụ cuối cùng. Khi Gateway bị timeout lúc gọi Payment Service, Payment có thể đã xử lý xong nhưng response bị mất. Không tự đổi kết quả thành PAYMENT_FAILED khi chưa xác minh.

### 2.1. Người dùng, client và vận hành cần thông tin khác nhau

Một phản hồi lỗi có ba đối tượng sử dụng:

- **Client application:** cần HTTP status, error code ổn định, dữ liệu field validation có cấu trúc và chỉ dẫn retry.
- **Người dùng:** cần thông báo dễ hiểu, an toàn, có thể bản địa hóa, cùng hành động có thể làm tiếp.
- **Kỹ sư vận hành:** cần traceId/correlationId, upstream, request route, exception, logs và metrics để điều tra.

Không nên cố đưa mọi thông tin kỹ thuật vào một chuỗi message gửi cho người dùng. Ngược lại, một thông báo “Có lỗi xảy ra” không đủ để client phân biệt hết hàng, thiếu quyền hay quá tải.

### 2.2. Lỗi HTTP không phải trạng thái nghiệp vụ

Ví dụ API khởi tạo thanh toán trả HTTP 202 Accepted kèm operationId. Đây có thể là một **phản hồi thành công về việc tiếp nhận công việc**, dù kết quả thanh toán còn PENDING. Khi truy vấn sau đó, operation có thể trả trạng thái nghiệp vụ SUCCEEDED hoặc DECLINED theo schema đã định nghĩa.

Không nên dùng HTTP 500 để biểu diễn một thanh toán bị provider từ chối hợp lệ; cũng không nên trả HTTP 200 chỉ vì hệ thống xử lý được exception và đặt code lỗi trong body. Status HTTP cần phản ánh đúng kết quả xử lý HTTP theo hợp đồng.

## 3. Hợp đồng lỗi công khai gồm những thành phần gì?

Một định dạng lỗi tốt phải trả lời:

1. **HTTP status:** request bị từ chối hoặc thất bại theo loại nào ở tầng HTTP?
2. **Error type / machine code:** client nhận diện một loại lỗi ổn định bằng cách nào?
3. **Human-readable title/detail:** mô tả ngắn gọn cho người đọc, không phải string dùng để nhánh logic.
4. **Instance hoặc operation identifier:** lỗi gắn với request/tài nguyên nào?
5. **Validation details:** trường nào không hợp lệ, lỗi kiểu gì, cách hiển thị?
6. **Retry guidance:** có được thử lại không, khi nào và có yêu cầu idempotency không?
7. **Correlation context:** khi liên hệ hỗ trợ có thể trỏ tới logs/traces mà không tiết lộ hệ thống nội bộ?
8. **Compatibility rules:** trường nào ổn định, trường nào tùy chọn, cách thêm loại lỗi mới ra sao?

Các phần không bắt buộc phải nằm hết trong body. Ví dụ retry có thể được diễn đạt qua **Retry-After** trong header, authentication challenge qua **WWW-Authenticate**, caching qua **Cache-Control**, request tracing qua một header riêng theo chính sách.

## 4. Dùng Problem Details cho HTTP API

Một hướng thông dụng là **Problem Details for HTTP APIs**, chuẩn được mô tả trong RFC 9457 (thay thế RFC 7807). Dạng JSON dùng media type:

~~~http
Content-Type: application/problem+json
~~~

Các thuộc tính lõi của Problem Details gồm:

| Thuộc tính | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| type | URI định danh loại vấn đề | Nếu không có kiểu riêng, mặc định ngầm là about:blank |
| title | Tiêu đề dễ đọc cho loại vấn đề | Không nên dùng để client ra quyết định |
| status | Mã HTTP status liên quan tới vấn đề | Phải nhất quán với status thực tế khi phát phản hồi |
| detail | Giải thích cho lần xảy ra lỗi cụ thể | Không chứa secret/stack trace |
| instance | URI/reference định danh lần xuất hiện vấn đề | Có thể dùng đường dẫn hoặc ID công khai được phép |

Chuẩn cho phép thêm **extension members** theo nhu cầu. Ví dụ errorCode, traceId, invalidParams và retryable có thể được định nghĩa là phần mở rộng trong contract của sản phẩm.

### 4.1. Ví dụ lỗi validation

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-73c10
~~~

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/orders/requests/req-73c10",
  "errorCode": "VALIDATION_ERROR",
  "traceId": "req-73c10",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "code": "MIN_VALUE",
      "message": "Quantity must be at least 1."
    },
    {
      "name": "shippingAddress.postalCode",
      "code": "INVALID_FORMAT",
      "message": "Postal code has an invalid format."
    }
  ]
}
~~~

Trong ví dụ này, **errorCode** là mã hợp đồng ổn định của API; **message** và **detail** có thể được dịch hoặc đổi câu chữ. Client nên dùng invalidParams[].name và code theo quy ước, không parse thông điệp tự do.

Sự lựa chọn 400 hay 422 cho các lỗi validation phụ thuộc contract. Nên phân định nhất quán: 400 thường dùng cho cú pháp/trình bày request không hợp lệ; 422 khi cú pháp hiểu được nhưng nội dung không thể xử lý theo quy tắc đã định. Không bắt buộc mọi API phải dùng 422; quan trọng là mô tả rõ tiêu chí.

### 4.2. Ví dụ tài nguyên không tồn tại

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.com/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "The requested order was not found.",
  "errorCode": "ORDER_NOT_FOUND",
  "traceId": "req-94de2"
}
~~~

Không đưa truy vấn SQL, tên bảng, internal primary key không được phép lộ hoặc địa chỉ của database vào body.

### 4.3. Ví dụ lỗi nội bộ

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-f0be1
~~~

~~~json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "An unexpected error occurred. Please try again later.",
  "errorCode": "INTERNAL_ERROR",
  "traceId": "req-f0be1"
}
~~~

Logs nội bộ có thể ghi stack trace và upstream gây lỗi, nhưng phản hồi ra internet chỉ chứa thông tin cần cho người dùng và việc tìm log. Không nên trả nguyên nội dung exception trong field detail.

### 4.4. Có bắt buộc dùng Problem Details không?

Không. Một tổ chức có thể đang có envelope cũ như:

~~~json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "Order was not found",
    "requestId": "req-94de2"
  }
}
~~~

Nếu contract này đã được nhiều client sử dụng, không nên đổi đột ngột sang application/problem+json chỉ vì một chuẩn mới. Có thể giữ hợp đồng hiện tại trong version đang chạy, chuẩn hóa bổ sung ở version mới hoặc triển khai migration từng bước. **Ổn định hợp đồng đang công khai quan trọng hơn sở thích hình thức.**

Problem Details cũng không yêu cầu body cho mọi trường hợp. Một số tình huống như 204 No Content, HEAD hoặc phản hồi bị kết nối đóng có semantics riêng. Trường hợp authorization challenge có thể cần header; Gateway không nên cố ép một body vào mọi hoàn cảnh bất chấp giao thức.

## 5. Bảng status HTTP thực dụng cho API Gateway

| Status | Ý nghĩa phổ biến | Ghi chú thiết kế |
| --- | --- | --- |
| 400 Bad Request | Request không hợp lệ về cú pháp hoặc contract | Không dùng 500 cho lỗi client gửi dữ liệu sai |
| 401 Unauthorized | Không có hoặc không hợp lệ thông tin xác thực | Với HTTP authentication, dùng WWW-Authenticate theo scheme |
| 403 Forbidden | Đã hiểu request nhưng bị cấm | Không lộ thông tin về quyền nội bộ |
| 404 Not Found | Không tìm thấy hoặc không được phép tiết lộ tài nguyên | Có thể dùng để tránh resource enumeration theo policy |
| 405 Method Not Allowed | Method không hỗ trợ cho resource | Cần header Allow theo HTTP semantics |
| 408 Request Timeout | Server không nhận request đầy đủ kịp thời | Không tự dùng để biểu thị mọi timeout upstream |
| 409 Conflict | Xung đột với trạng thái hiện tại của tài nguyên | Ví dụ trạng thái đơn không cho hủy |
| 412 Precondition Failed | Điều kiện If-Match/If-Unmodified-Since không thỏa | Hữu ích với optimistic concurrency |
| 413 Content Too Large | Body vượt giới hạn | Không lộ giới hạn nội bộ không cần thiết |
| 415 Unsupported Media Type | Content-Type request không được hỗ trợ | Nói rõ format được hỗ trợ nếu an toàn |
| 422 Unprocessable Content | Nội dung hiểu được nhưng không xử lý được | Sử dụng theo contract, không trộn tùy tiện với 400 |
| 429 Too Many Requests | Rate limit/quota áp dụng cho caller | Retry-After nếu có thời gian hợp lý |
| 500 Internal Server Error | Lỗi bất ngờ tại nơi xử lý | Body phải an toàn, có correlation ID |
| 502 Bad Gateway | Gateway nhận phản hồi không hợp lệ từ upstream | Không phải mọi upstream 5xx đều là 502 |
| 503 Service Unavailable | Dịch vụ tạm không sẵn sàng/quá tải | Có thể dùng Retry-After khi phù hợp |
| 504 Gateway Timeout | Gateway hết hạn chờ upstream | Không đồng nghĩa nghiệp vụ upstream đã thất bại |

HTTP status là một phần contract nhưng không đủ để phân biệt mọi tình huống. Ví dụ 409 có thể là ORDER_ALREADY_CANCELLED, VERSION_CONFLICT hoặc INVENTORY_RESERVATION_CONFLICT, mỗi loại có hướng xử lý khác nhau.

### 5.1. Không trả HTTP 200 cho mọi lỗi REST

Một anti-pattern là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": false,
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

Hệ quả có thể là:

- Proxy và cache hiểu nhầm kết quả là thành công.
- Monitoring status-based không nhận diện lỗi.
- SDK mặc định không kích hoạt xử lý lỗi.
- Client phải tự parse body mọi response.
- Observability và SLO bị méo.

Nếu đang duy trì API cũ theo contract đặc biệt, không thay đổi mù. Nhưng với REST HTTP API mới, nên sử dụng status đúng semantics và error body có cấu trúc.

### 5.2. Không dùng 500 cho mọi lỗi nghiệp vụ

Một request đặt hàng thiếu quantity không phải “server hỏng”. Một mã giảm giá đã hết hạn có thể bị từ chối hợp lệ. Một payment provider từ chối thanh toán không mặc định là lỗi 500 của Order API.

Hãy xác định **request có hợp lệ không**, **trạng thái nghiệp vụ hiện tại là gì**, và **hợp đồng API mô tả kết cục nào**.

### 5.3. Không tự biến lỗi upstream thành lỗi client

Gateway có thể gọi Inventory và nhận lỗi kết nối. Client không nhất thiết đã gửi yêu cầu sai; trả 400 dễ khiến client không biết cần retry hoặc báo tình trạng tạm thời. Cần ánh xạ đúng một loại lỗi public, thường thuộc 5xx cho lỗi hệ thống không thể hoàn tất xử lý, hoặc một trạng thái operation pending nếu workflow đã được tiếp nhận bền vững.

## 6. Gateway nên ánh xạ lỗi upstream thế nào?

Ở ranh giới công khai, Gateway biết **endpoint public, route, policy, authentication, rate limit và contract dự kiến**, nhưng domain service mới biết lỗi nghiệp vụ chi tiết. Việc ánh xạ cần tôn trọng hai vai trò.

Một bảng ví dụ:

| Upstream hoặc Gateway quan sát | Phản hồi public gợi ý | Lưu ý |
| --- | --- | --- |
| Catalog trả PRODUCT_NOT_FOUND theo contract | 404 + PRODUCT_NOT_FOUND | Có thể giữ code public ổn định |
| Order trả INVALID_ORDER_ITEMS | 422 + VALIDATION_ERROR hoặc code cụ thể | Quy ước validation rõ |
| Payment trả PAYMENT_DECLINED rõ ràng | Phản hồi theo public payment contract | Không biến thành 500 chỉ vì giao dịch bị từ chối |
| Gateway xác thực token thất bại | 401 + AUTHENTICATION_REQUIRED/INVALID_TOKEN theo chính sách | Kèm challenge thích hợp, tránh leak |
| Gateway chặn quyền | 403 hoặc 404 + public code an toàn | Không lộ thông tin resource không được phép biết |
| Gateway rate limit vượt ngưỡng | 429 + RATE_LIMITED | Có Retry-After nếu hữu ích |
| Gateway timeout chờ service | 504 + UPSTREAM_TIMEOUT | Nêu trạng thái request chưa chắc cuối |
| Gateway không thể kết nối upstream | 502 hoặc 503 theo nguyên nhân/hợp đồng | Không đánh đồng mọi lỗi kết nối |
| Service trả HTML exception không hợp lệ | 502/500 generic public problem | Không phát tán HTML và stack trace |
| Service trả status 500 với mã lỗi nội bộ | 500 public generic | Log correlation để điều tra, không passthrough raw |

**Đây là gợi ý, không phải bảng mapping áp dụng cơ học**. Ví dụ 404 của upstream có thể là endpoint nội bộ bị sai đường dẫn (lỗi triển khai), không phải orderId không tồn tại. Gateway không nên truyền 404 ra ngoài nếu ý nghĩa công khai sai.

### 6.1. Không để lỗi hạ tầng chi phối public contract

Thông tin thường không nên rò rỉ:

- Tên host, pod, container, namespace hoặc địa chỉ IP nội bộ.
- Tên service, phiên bản thư viện/framework và đường dẫn file hệ thống.
- Connection strings, tên database, SQL statement và stack trace.
- Access token, API key, session cookie, secret hoặc dữ liệu thẻ.
- Response raw từ upstream không tin cậy, kể cả HTML lỗi proxy.
- Chi tiết về account/resource của người dùng khác.

Một trường debug hữu ích trong logs có thể là lỗ hổng bảo mật nếu đưa vào public error response.

### 6.2. Lỗi được sinh ở Gateway hay service?

**Gateway nên sinh lỗi** khi điều kiện do Gateway quản lý: xác thực ở biên, limit chung, route không hợp lệ, upstream không sẵn sàng hoặc timeout.

**Domain service nên sinh lỗi nghiệp vụ** khi hiểu quy tắc domain: tồn kho không đủ, trạng thái đơn không cho hủy, payment attempt đã đóng, validation nghiệp vụ.

Gateway có thể chuẩn hóa representation và mã lỗi public của service, nhưng tránh tự sao chép toàn bộ quy tắc domain. Nếu mỗi rule chỉ tồn tại ở Gateway, thay đổi domain khó đồng bộ và có nguy cơ hai lớp đưa ra quyết định mâu thuẫn.

### 6.3. Mapping theo contract, không dựa vào string exception

Không nên làm:

~~~text
if upstream.message contains "stock":
    return OUT_OF_STOCK
~~~

Nội dung thông điệp có thể đổi ngôn ngữ, đổi câu, được bọc nhiều lớp hoặc chứa dữ liệu người dùng. Thay vào đó hãy dùng **typed error code nội bộ** đã được chấp thuận, hoặc map từ status/route/context có quy tắc xác định.

Nếu upstream không có contract rõ, Gateway nên trả lỗi public generic và ghi lại nguyên nhân nội bộ, không đoán một business code cụ thể từ free text.

## 7. Thiết kế error code ổn định cho client

Public error code là một phần API contract. Nó cần rõ ý nghĩa, ổn định và có thể tài liệu hóa.

Ví dụ hệ thống có thể chọn:

| errorCode | HTTP status | Client nên làm gì |
| --- | ---: | --- |
| VALIDATION_ERROR | 400/422 theo contract | Highlight field invalidParams |
| ORDER_NOT_FOUND | 404 | Hiển thị không tìm thấy hoặc điều hướng |
| ORDER_STATE_CONFLICT | 409 | Refresh dữ liệu trước khi thử hành động mới |
| VERSION_CONFLICT | 409/412 theo contract | Tải phiên bản mới và retry có kiểm soát |
| PAYMENT_DECLINED | Theo payment contract | Hiển thị phương thức thanh toán khác |
| AUTHENTICATION_REQUIRED | 401 | Bắt đầu login/refresh đúng policy |
| ACCESS_DENIED | 403 | Không tự retry cùng quyền |
| RATE_LIMITED | 429 | Tôn trọng Retry-After/backoff |
| SERVICE_UNAVAILABLE | 503 | Retry có giới hạn nếu thao tác an toàn |
| UPSTREAM_TIMEOUT | 504 | Xác minh operation status nếu có side effect |
| INTERNAL_ERROR | 500 | Báo lỗi chung và correlation ID |

Một mã không nên đổi ý nghĩa âm thầm. Nếu ORDER_NOT_FOUND ban đầu nghĩa là đơn không tồn tại, không đổi thành “thiếu quyền truy cập đơn” mà không xem xét security/compatibility. Khi cần thay đổi semantics, hãy tạo code mới hoặc chiến lược versioning rõ.

### 7.1. Code phục vụ máy, message phục vụ người

Client nên sử dụng:

~~~text
if error.errorCode == "VERSION_CONFLICT":
    refreshOrder()
else if error.errorCode == "RATE_LIMITED":
    applyBackoff(error.retryAfter)
else:
    showGenericError()
~~~

Không nên dùng:

~~~text
if error.detail == "The order has changed since you opened it":
    refreshOrder()
~~~

Nội dung title/detail có thể được biên tập, bản địa hóa hoặc thay đổi vì lý do UX. Client ra quyết định dựa trên **status, code và các trường có hợp đồng ổn định**, không dựa vào câu chữ tiếng Anh.

### 7.2. Có nên cho errorCode chứa tên service?

Tránh mã như INVENTORY_SERVICE_V2_REPOSITORY_TIMEOUT nếu tên hạ tầng không phải một khái niệm public. Mã này làm lộ topology và buộc client phụ thuộc cách tổ chức service.

Thay vào đó, một public API có thể trả SERVICE_TEMPORARILY_UNAVAILABLE hoặc UPSTREAM_TIMEOUT, còn nội bộ logs lưu service, route, cluster và error class.

Với lỗi nghiệp vụ, mã có thể mang tên domain như INVENTORY_OUT_OF_STOCK vì đó là khái niệm có ý nghĩa với client, không phải tên hạ tầng.

## 8. Validation errors và thiết kế đường dẫn trường

Lỗi validation thường chứa nhiều phần tử. Schema cho invalidParams cần ổn định về:

- **name/path:** chỉ ra vị trí dữ liệu không hợp lệ.
- **code:** loại vi phạm có thể dùng trong UI.
- **message:** mô tả dễ hiểu, không phải cơ sở cho logic.
- **metadata tùy chọn:** ví dụ min/max nếu được phép lộ và có hợp đồng.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "errorCode": "VALIDATION_ERROR",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "code": "MIN_VALUE",
      "message": "Quantity must be at least 1.",
      "min": 1
    },
    {
      "name": "shippingAddress.postalCode",
      "code": "REQUIRED",
      "message": "Postal code is required."
    }
  ]
}
~~~

Một tổ chức có thể chọn JSON Pointer như /items/0/quantity thay vì chuỗi items[0].quantity. Cả hai đều có thể sử dụng, nhưng phải **chọn một quy ước, tài liệu hóa escape/index và không đổi tùy service**.

Không bao giờ phản hồi raw value của password, token, số thẻ hoặc dữ liệu nhạy cảm trong invalidParams. Thậm chí việc đưa nguyên input người dùng vào logs cũng cần redaction.

### 8.1. 400 hay 422?

Có thể chọn một trong hai quy ước:

- **400:** dữ liệu thiếu/sai định dạng, cú pháp không hợp lệ, ràng buộc trường không đạt.
- **422:** request parse hợp lệ nhưng nội dung không thể xử lý theo validation đã định nghĩa.

Không nên lúc dùng 400, lúc dùng 422 cho cùng trường hợp chỉ vì các service dùng framework khác nhau. Gateway có thể chuẩn hóa nếu điều đó nằm trong contract. Nhưng khi API đã công khai, chuyển 400 sang 422 cũng có thể làm SDK/client thay đổi hành vi; hãy quản lý như thay đổi hợp đồng.

### 8.2. Không đưa policy nhạy cảm vào validation message

Thông báo như “Username không tồn tại” và “Mật khẩu không đúng” ở bước đăng nhập có thể hỗ trợ account enumeration. Nên dùng lỗi xác thực an toàn theo threat model, ví dụ thông báo thông tin đăng nhập không hợp lệ, và không để thông tin người dùng tồn tại hay không bị suy luận qua status/timing/body.

## 9. Authentication và authorization: giữ đúng semantics và bảo mật

**401 Unauthorized** trong HTTP thường nghĩa request thiếu thông tin xác thực hợp lệ. Nếu sử dụng HTTP authentication scheme, server thường cần trả **WWW-Authenticate** challenge thích hợp theo tiêu chuẩn và cơ chế triển khai.

**403 Forbidden** nghĩa server hiểu request nhưng từ chối cho phép. Người dùng đã đăng nhập vẫn có thể nhận 403 vì thiếu quyền truy cập.

**404 Not Found** có thể được áp dụng khi chính sách bảo mật cần che giấu việc tài nguyên có tồn tại hay không, nhưng phải nhất quán với contract và tránh tạo hành vi suy đoán thông qua các thông tin khác.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/problem+json
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.com/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "errorCode": "AUTHENTICATION_REQUIRED"
}
~~~

Các lỗi xác thực nên tránh phản hồi nội dung token, chi tiết chữ ký, thuật toán nội bộ, lý do chính xác khiến một tài khoản có/không tồn tại, hoặc kết quả policy check nhạy cảm.

### 9.1. Tránh leak qua chênh lệch phản hồi

Ngay cả khi body đã generic, kẻ tấn công đôi khi suy luận từ status, response size hoặc độ trễ khác biệt. Hệ thống cần xem xét threat model và các chính sách rate limit, logging, account lockout, challenge phù hợp. Không có một cấu trúc JSON duy nhất có thể giải quyết mọi bài toán side-channel.

## 10. Rate limiting và retry guidance

Rate limiting là trường hợp Gateway thường trực tiếp sở hữu lỗi. Khi vượt hạn mức, Gateway có thể trả 429 và một problem body công khai:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 15
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Please retry later.",
  "errorCode": "RATE_LIMITED",
  "traceId": "req-0d6f1"
}
~~~

**Retry-After** có thể được biểu diễn bằng số giây hoặc một HTTP-date theo semantics của HTTP. Client nên có backoff, jitter, retry budget và giới hạn tổng thời gian. Không nên retry ngay lập tức hàng trăm lần khi nhận 429.

### 10.1. 429 khác 503 thế nào?

- **429:** caller đã vượt một chính sách giới hạn tốc độ/quota; thường liên quan danh tính, key, user, tenant hoặc plan theo quy tắc.
- **503:** dịch vụ tạm không thể phục vụ, ví dụ quá tải hoặc bảo trì; không nhất thiết caller vi phạm quota.

Một Gateway không nên chuyển mọi sự cố upstream sang 429 vì sẽ đổ lỗi sai cho client. Cũng không nên biến 429 thành 500 khiến retry policy và observability bị hiểu sai.

### 10.2. Retryable không đồng nghĩa mọi request đều gửi lại an toàn

Ngay cả khi Gateway trả 503 hoặc 504, một POST có side effect có thể đã được upstream xử lý. Client cần idempotency key hoặc status lookup trước khi replay. Một field retryable=true không nên được hiểu là quyền thử lại vô điều kiện bất kể operation state.

Có thể định nghĩa:

~~~json
{
  "type": "https://api.example.com/problems/upstream-timeout",
  "title": "Request timed out",
  "status": 504,
  "errorCode": "UPSTREAM_TIMEOUT",
  "retryPolicy": "CHECK_OPERATION_STATUS",
  "traceId": "req-d4b82"
}
~~~

retryPolicy là extension minh họa do tổ chức định nghĩa, không phải field chuẩn bắt buộc của RFC 9457. Nó phải có bộ giá trị được tài liệu hóa, ví dụ RETRY_WITH_SAME_KEY, CHECK_OPERATION_STATUS, DO_NOT_RETRY; không khẳng định kết quả nghiệp vụ đã thất bại.

## 11. Trường hợp timeout hoặc kết quả chưa xác định

Một luồng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant O as Order Service
    participant P as Payment Service
    C->>G: POST /orders
    G->>O: Tạo đơn
    O->>P: Charge(paymentId)
    P->>P: Lưu kết quả
    Note over G,P: Gateway hết deadline trước khi có phản hồi
    G-->>C: Timeout hoặc pending theo contract
    P-->>O: PaymentSucceeded đến muộn
    O->>O: Chốt trạng thái đơn
    C->>G: GET /order-operations/{id}
    G->>O: Query status
    O-->>G: CONFIRMED
    G-->>C: Kết quả cuối
~~~

Nếu một thao tác đã được tiếp nhận bền vững và có operationId, API có thể trả 202 Accepted cùng URL tra cứu, thay vì buộc client chờ đến khi toàn bộ quy trình hoàn thành. Nhưng Gateway phải có đủ bằng chứng rằng **operation thực sự đã được tiếp nhận**; không tự trả 202 chỉ vì upstream bị timeout mà không có nguồn trạng thái đáng tin.

Nếu Gateway không biết operation có được tạo hay chưa, phản hồi lỗi công khai phải trung thực về sự không chắc chắn. Client có thể dùng cùng idempotency key hoặc truy vấn theo operationId nếu đã được cấp. Không nên tạo một operation mới cho mỗi network retry.

### 11.1. Deadline propagation

Gateway có thể đặt hạn chờ đầu-cuối; downstream nhận remaining budget thay vì bắt đầu một timeout đầy đủ mới. Ví dụ:

~~~text
Client budget: 2.0 s
Gateway processing elapsed: 0.2 s
Remaining at Order: khoảng 1.8 s
Order validation elapsed: 0.3 s
Remaining at Payment: khoảng 1.5 s
~~~

Các con số chỉ minh họa. Việc hủy HTTP hoặc deadline hết hạn không tự động rollback một lệnh thanh toán đã commit. Hợp đồng lỗi phải phân biệt **response timeout** với **business state**.

## 12. Bảo vệ hợp đồng công khai khi upstream thay đổi

Microservices có thể thay đổi framework, chia tách deployment, dùng database mới hoặc đổi error schema nội bộ. Public API không nên đổi theo từng chi tiết như vậy.

**Anti-corruption layer tại Gateway/BFF** có thể ánh xạ lỗi nội bộ sang public error model:

~~~text
Internal error:
  inventory.v3.InsufficientAvailableUnitsException
  details: internal warehouse, connection, inventory row...

Public error:
  HTTP 409
  errorCode: INVENTORY_NOT_AVAILABLE
  detail: Requested quantity is not currently available.
  traceId: req-abc
~~~

Tuy nhiên, loại lỗi công khai phải phù hợp nghiệp vụ thật. Nếu service không thể truy cập vì database lỗi, Gateway không được trả INVENTORY_NOT_AVAILABLE như thể đã xác nhận hết hàng.

### 12.1. Ma trận mapping có chủ sở hữu

Nên lưu một mapping có kiểm soát gồm:

- Public route và API version.
- Upstream service/operation có thể tạo lỗi.
- Internal typed error hoặc failure classification.
- Public status và errorCode.
- Public detail/title template đã được kiểm soát.
- Retry guidance theo loại operation.
- Security redaction và các extension cho phép.
- Owner của mapping và contract tests.

Khi thêm service mới, nhóm không nên tự đặt một envelope hoàn toàn khác cho client nếu route thuộc cùng public API version.

### 12.2. Chống biến mapping thành logic nghiệp vụ trùng lặp

Gateway không nên tự tính tồn kho, quyết định thẻ bị từ chối hay hủy đơn bằng cách parse một kết quả bất kỳ. Nên để service sở hữu domain quyết định mã lỗi nghiệp vụ nội bộ, sau đó Gateway bảo vệ representation ở biên.

Việc ánh xạ có thể ở Gateway, BFF hoặc trong một thư viện lỗi chung, tùy kiến trúc. **Vị trí không quan trọng bằng ownership rõ và contract nhất quán**.

## 13. Hợp đồng lỗi có versioning và compatibility

Client phụ thuộc cả phản hồi thành công lẫn phản hồi lỗi. Một thay đổi tưởng nhỏ có thể là breaking change.

### 13.1. Những thay đổi thường gây vỡ client

- Đổi HTTP status cho cùng điều kiện mà client có nhánh xử lý riêng.
- Đổi errorCode hoặc nghĩa của code.
- Đổi kiểu dữ liệu của field, ví dụ invalidParams từ array sang object.
- Chuyển từ JSON envelope cũ sang Problem Details mà không có version/migration.
- Xóa một field client dùng hoặc biến field nullable thành bắt buộc theo cách không tương thích.
- Đổi cú pháp của field path từ items[0].quantity sang JSON Pointer mà không công bố.
- Dừng trả Retry-After khiến client retry dồn dập theo policy cũ.
- Đổi header authentication challenge không tương thích với SDK.

### 13.2. Những thay đổi thường có thể tương thích, nhưng phải kiểm tra

- Thêm một optional extension field không thay đổi nghĩa field cũ.
- Thêm một mô tả detail rõ hơn khi client **không** được parse câu chữ.
- Thêm một mã lỗi con nếu client đã có nhánh fallback khi không nhận ra code.
- Thêm tracing header công khai đã được làm sạch.
- Bổ sung ví dụ và tài liệu, không thay đổi wire format.

Không nên tuyên bố mọi field mới đều tương thích tuyệt đối: một số client dùng JSON decoder strict hoặc schema exhaustiveness có thể lỗi với field lạ. Hợp đồng phải quy định client **bỏ qua extension không biết** hay có kiểu mở khác.

### 13.3. Quy tắc thiết kế cho tương thích tiến hóa

1. Client nên có **fallback** cho errorCode chưa biết.
2. Các field bắt buộc và tùy chọn cần được công bố trong OpenAPI/schema.
3. Có thể bổ sung mã mới dưới cùng status khi phù hợp, nhưng không đổi nghĩa mã cũ.
4. Nếu đổi lớn, cân nhắc API version hoặc giai đoạn dual support.
5. Dùng canary/feature flag/monitoring để xem client cũ có lỗi không.
6. Giữ thời gian deprecation theo chính sách hỗ trợ client thực tế.
7. Chốt ownership cho public error catalog và review mọi thay đổi.

Với ứng dụng mobile, phiên bản cũ có thể tồn tại lâu sau release; việc đổi hợp đồng cần quan sát vòng đời client, không chỉ phiên bản backend mới nhất.

## 14. OpenAPI và schema cho lỗi

OpenAPI nên khai báo response lỗi như khai báo response thành công. Ví dụ một thành phần schema có thể biểu diễn Problem Details với extension ổn định.

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    post:
      responses:
        "201":
          description: Order created
        "422":
          description: Invalid order input
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/PublicProblem"
        "409":
          description: Order state conflict
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/PublicProblem"
        "429":
          description: Too many requests
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/PublicProblem"
        "500":
          description: Internal error
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/PublicProblem"
components:
  schemas:
    PublicProblem:
      type: object
      required: [type, title, status, errorCode]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
          format: int32
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        errorCode:
          type: string
        traceId:
          type: string
        invalidParams:
          type: array
          items:
            type: object
            required: [name, code]
            properties:
              name:
                type: string
              code:
                type: string
              message:
                type: string
~~~

Đây là một đoạn ví dụ có tính minh họa, chưa phải đặc tả API đầy đủ. Các schema của Problem Details thường có khả năng mở rộng extension members; cần chốt cách client xử lý field lạ. Header như Retry-After, WWW-Authenticate và RateLimit fields nếu dùng cũng phải tài liệu hóa.

### 14.1. Một nguồn sự thật cho catalog lỗi

Có thể duy trì danh mục code công khai với:

| Trường | Ví dụ |
| --- | --- |
| errorCode | ORDER_STATE_CONFLICT |
| HTTP status | 409 |
| type URI | /problems/order-state-conflict |
| Ý nghĩa | Không thể thực hiện action với state đơn hiện tại |
| Khả năng retry | Không retry y nguyên; tải state mới |
| Chủ sở hữu | Order API |
| Public fields | orderId nếu được phép, traceId |
| Thông điệp | Có thể được bản địa hóa |
| Ngày đưa vào | Phiên bản hợp đồng cụ thể |
| Chính sách thay đổi | Có deprecation và migration nếu breaking |

Tài liệu, test fixtures và mã xử lý nên được đồng bộ bằng quy trình quản lý API, tránh mỗi team cập nhật một bản copy.

## 15. Bảo vệ thông tin nhạy cảm trong lỗi

Lỗi thường bị xem nhẹ hơn dữ liệu thành công, nhưng có thể tiết lộ thông tin còn nhạy cảm hơn:

- Stack trace chỉ ra framework và phiên bản có lỗ hổng.
- SQL error lộ tên bảng, cột, dữ liệu cá nhân hoặc query.
- Lỗi auth cho biết account có tồn tại.
- Thông báo từ payment provider chứa mã giao dịch hoặc thông tin cá nhân.
- Gateway echo lại full request URI có access token trong query string.
- Headers debug cho biết tên host hoặc topology nội bộ.

### 15.1. Redaction ở mọi tầng

Không chỉ Gateway cần lọc. Cần:

1. Domain service phân loại những field được đưa ra public.
2. Gateway có allowlist các extension/header được phép.
3. Logs/tracing có chính sách ẩn secret/PII.
4. Error response có Cache-Control phù hợp với mức nhạy cảm.
5. Hệ thống giám sát không xuất bản raw request/response chứa dữ liệu cần bảo vệ.

Nếu Gateway nhận raw upstream error không tin cậy, không nên copy nguyên error body hay headers ra ngoài. Một số header như Set-Cookie, Server, Via, debug metadata hoặc nội dung đặc thù có thể cần chính sách proxy riêng; phải phân biệt header tiêu chuẩn cần giữ và header nội bộ cần chặn.

### 15.2. Nguyên tắc thông tin tối thiểu

Public response nên cho client đủ dữ liệu để làm đúng thao tác tiếp theo, nhưng không để lộ chi tiết không cần thiết. Ví dụ người dùng thiếu quyền với một đơn hàng không nhất thiết được thấy tên người sở hữu đơn, tenant nội bộ hay role policy bị thiếu.

Thông điệp chung cùng traceId có thể phù hợp với lỗi bất ngờ. Với lỗi validation, nên chỉ rõ trường và quy tắc **được phép công khai** để người dùng sửa.

### 15.3. TraceId có thể được công khai không?

Một correlation ID ngẫu nhiên, không mang thông tin cá nhân và không trao quyền truy cập thường hữu ích cho hỗ trợ. Nhưng không nên đưa full internal tracing metadata, sampling flags nhạy cảm hoặc các định danh chứa thông tin cấu trúc hệ thống ra public một cách thiếu kiểm soát.

Tùy thiết kế, public requestId có thể được ánh xạ nội bộ tới traceId, giúp người dùng cung cấp mã hỗ trợ mà không tiết lộ toàn bộ tracing context.

## 16. Error contract trong hệ thống nhiều tầng Gateway và BFF

Một hệ thống có thể có Edge Gateway, BFF cho mobile và các service bên trong. Khi nhiều tầng đều có khả năng bọc lỗi, dễ xảy ra “nested error”:

~~~json
{
  "error": {
    "code": "BFF_FAILED",
    "details": {
      "error": {
        "code": "ORDER_FAILED",
        "details": {
          "error": "SQL constraint violation..."
        }
      }
    }
  }
}
~~~

Hậu quả là khó đọc, rò rỉ nội bộ và client phụ thuộc topology. Thay vào đó nên xác định một **public error representation** tại điểm biên cuối cùng và một mô hình lỗi nội bộ có thể map.

Ví dụ:

~~~text
Order Service
  Internal: OrderStateConflict(reason=ALREADY_SHIPPED)

BFF
  Domain mapping: ORDER_STATE_CONFLICT

API Gateway
  Public HTTP 409 + Problem Details
  ErrorCode: ORDER_STATE_CONFLICT
  traceId: req-123
~~~

Không bắt buộc Gateway phải map lại mọi lỗi đã chuẩn. Nếu upstream đã là một public API component đáng tin và schema đã được chấp thuận, có thể pass-through có kiểm soát. Tuy nhiên Gateway vẫn phải bảo vệ thông tin nhạy cảm và hợp đồng tổng thể.

### 16.1. Ai nên quyết định HTTP status?

Với lỗi nghiệp vụ, domain service có thể có ý nghĩa nội bộ như ORDER_ALREADY_PAID. Public API owner chọn status theo endpoint và contract. Với lỗi rate limit, routing, authentication ở edge, Gateway là owner tự nhiên.

Nếu hai service cùng dùng internal code NOT_FOUND nhưng một bên nghĩa dữ liệu không tồn tại, bên còn lại nghĩa upstream route bị sai, mapping không thể chỉ dựa trên từ NOT_FOUND. Cần thêm **operation context** và typed failure classification.

## 17. Xử lý lỗi trong Java/Spring Boot

Spring Framework 6 và Spring Boot 3 hỗ trợ **ProblemDetail**, có thể dùng để tạo response theo Problem Details. Ví dụ controller advice:

~~~java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PublicErrorHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException ex) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.NOT_FOUND);

        problem.setType(URI.create(
            "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Order not found");
        problem.setDetail("The requested order was not found.");
        problem.setProperty("errorCode", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> handleUnexpected(
            Exception ex) {

        String publicRequestId = UUID.randomUUID().toString();

        // Log chi tiết exception chỉ ở hệ thống nội bộ,
        // cùng requestId hoặc trace context liên quan.
        ProblemDetail problem =
            ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR);

        problem.setType(URI.create(
            "https://api.example.com/problems/internal-error"));
        problem.setTitle("Internal server error");
        problem.setDetail(
            "An unexpected error occurred. Please try later.");
        problem.setProperty("errorCode", "INTERNAL_ERROR");
        problem.setProperty("traceId", publicRequestId);

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(problem);
    }
}
~~~

Đoạn mã chỉ minh họa cách tạo response; không phải toàn bộ cơ chế bảo mật, logging và tracing. Trong hệ thống thực tế:

- Tạo requestId sớm tại request filter/Gateway, truyền xuyên các tầng và log cùng ID; không sinh mã khác ở nhiều nơi không có liên kết.
- Có handler riêng cho validation, authentication, authorization, rate limit, known business exceptions.
- Response Content-Type và serialization phải được cấu hình/kiểm thử đúng dạng application/problem+json nếu áp dụng.
- Exception bất ngờ phải log với cơ chế redaction; tránh ghi request body chứa secret.
- Không dùng ex.getMessage() trực tiếp làm public detail.
- Không map mọi Exception thành 500 nếu HTTP framework cần giữ những lỗi do contract tạo ra (ví dụ 405 hoặc 415).
- Với Spring Security, authentication/access denied có thể đi qua filter chain và cần error handlers phù hợp, không chỉ @RestControllerAdvice.
- Exception mapping ở Gateway phải xử lý cả lỗi xảy ra **trước** khi request tới controller.

### 17.1. Validation handler

Một validation handler có thể thu field errors từ framework, đổi field path sang quy ước public và trả problem body:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "errorCode": "VALIDATION_ERROR",
  "invalidParams": [
    {
      "name": "quantity",
      "code": "MIN_VALUE",
      "message": "Must be at least 1."
    }
  ]
}
~~~

Không nên phát tán tên class Java như MethodArgumentNotValidException hoặc tên constraint nội bộ không ổn định trực tiếp cho client. Nếu có nhãn trường localization, xử lý ở lớp hiển thị hoặc theo contract của API.

### 17.2. API Gateway khác controller advice ở đâu?

Một Gateway thường không có controller Java cho mọi endpoint. Lỗi có thể phát sinh trong route matching, filter, proxy upstream, circuit breaker hoặc rate limit. Cần error translator ở pipeline Gateway tương ứng, vẫn tuân public schema.

Nếu dùng Spring Cloud Gateway, Envoy, NGINX hoặc một managed API gateway, khả năng viết/error transform sẽ khác nhau. Không nên dựa vào một @RestControllerAdvice ở downstream để kỳ vọng tự xử lý được timeout do gateway sinh ra.

## 18. Xử lý response của upstream theo cách có thể kiểm soát

Một Gateway có thể áp dụng đường xử lý:

~~~mermaid
flowchart TD
    A["Nhận request từ client"] --> B["Auth / policy / rate limit"]
    B --> C{"Gateway từ chối?"}
    C -- "Có" --> D["Sinh public problem theo contract"]
    C -- "Không" --> E["Gọi upstream theo deadline"]
    E --> F{"Upstream trả kết quả?"}
    F -- "Success" --> G["Trả success response đúng contract"]
    F -- "Known domain error" --> H["Map typed error sang public code/status"]
    F -- "Invalid/internal response" --> I["Sanitize -> generic public problem"]
    F -- "Timeout / connect failure" --> J["Phân loại gateway error, không đoán business outcome"]
    D --> K["Gắn requestId, headers an toàn, metrics"]
    H --> K
    I --> K
    J --> K
~~~

Trong pipeline này, success và lỗi phải được quan sát nhất quán qua status code, trace và metrics. Khi response body upstream quá lớn hoặc không parse được, Gateway phải có giới hạn bộ nhớ, timeout và fallback an toàn; không ép parse vô hạn gây quá tải.

### 18.1. Fallback khi upstream response không đúng schema

Nếu downstream trả HTML error page hoặc cấu trúc JSON khác dự kiến, Gateway không nên truyền raw body về client. Nên dùng generic public problem và log nội bộ về route/trace. Đây là lý do cần **contract test giữa Gateway và upstream**, không chỉ giữa client và Gateway.

### 18.2. Fallback không được bịa business outcome

Nếu Payment Service không phản hồi, Gateway không được tự nói PAYMENT_DECLINED hoặc PAYMENT_SUCCEEDED. Một generic UPSTREAM_TIMEOUT/UNKNOWN trạng thái giao tiếp cùng hướng dẫn kiểm tra operation là trung thực hơn. Với nghiệp vụ có state tracking, BFF hoặc Order workflow có thể cung cấp trạng thái PENDING an toàn.

## 19. Tài liệu hóa khả năng retry và idempotency

Client thường cần biết lỗi nào có thể thử lại. Tuy nhiên retryability phụ thuộc cả **loại lỗi** và **loại operation**.

Ví dụ:

- GET sản phẩm bị 503: thường có thể retry có budget.
- POST tạo đơn bị 504: có thể đã tạo đơn; chỉ retry an toàn khi dùng cùng idempotency key hoặc có cách query status.
- 422 validation: sửa request, không retry nguyên payload.
- 409 state conflict: lấy trạng thái mới trước khi gửi action khác.
- 429: tôn trọng Retry-After và chính sách rate limit.
- 401: xác thực lại theo flow, tránh vòng lặp refresh token.
- 403: không tự tăng số lần retry để vượt quyền.

Có thể duy trì một bảng public retry policy:

| errorCode | Retry mặc định | Điều kiện |
| --- | --- | --- |
| VALIDATION_ERROR | Không | Sửa dữ liệu |
| ACCESS_DENIED | Không | Quyền phải thay đổi |
| RATE_LIMITED | Có giới hạn | Theo Retry-After/backoff |
| SERVICE_UNAVAILABLE | Có điều kiện | Chỉ operation replay-safe |
| UPSTREAM_TIMEOUT | Có điều kiện | Query operation hoặc dùng cùng idempotency key |
| VERSION_CONFLICT | Không retry mù | Refresh state và kiểm tra action |
| INTERNAL_ERROR | Tùy operation | Không tự thử lại side effect chưa rõ |

Bảng cần tài liệu hóa cùng endpoint, không tuyên bố “mọi 5xx đều retry”.

### 19.1. Idempotency-Key trong hợp đồng public

Nếu API hỗ trợ idempotency cho POST, hãy công bố rõ:

- Phạm vi khóa theo tenant/account/operation.
- Khóa giữ qua bao nhiêu lần retry.
- Cùng key với payload khác được xử lý thế nào.
- Trạng thái khi request đầu vẫn đang chạy.
- Thời gian retention key.
- Cách query kết quả sau client timeout.

Một header chỉ có tên Idempotency-Key không tự đảm bảo chống trùng; service sở hữu operation phải thực thi cơ chế bền vững và concurrency-safe.

## 20. Một dạng response cho lỗi không có nghĩa một thông điệp cho mọi người

Về UX, client có thể dùng mã lỗi để hiển thị thông điệp địa phương:

~~~text
ORDER_NOT_FOUND -> "Không tìm thấy đơn hàng"
RATE_LIMITED -> "Bạn thao tác quá nhanh, vui lòng thử lại sau"
INTERNAL_ERROR -> "Hệ thống đang gặp sự cố, hãy thử lại sau"
~~~

Thông điệp được quản lý trong ứng dụng hoặc nguồn localization có thể thay đổi mà không đổi public errorCode.

Nếu server trả detail theo Accept-Language, cần đảm bảo các trường máy đọc vẫn ổn định và tránh để nội dung detail trở thành định danh logic. Tránh đưa dữ liệu người dùng chưa được escape vào UI thông qua thông điệp lỗi để giảm nguy cơ injection.

### 20.1. Mã lỗi nên có vòng đời rõ

Có thể phân loại error codes:

- **Public stable:** client được phép dùng để xử lý.
- **Public generic:** chỉ phục vụ hiển thị; không cần client nhánh nhiều.
- **Internal diagnostic:** chỉ xuất hiện trong logs/tracing, không gửi ra ngoài.

Nếu một internal code được đưa công khai qua nhiều bản release, nó có thể trở thành hợp đồng thực tế, dù tài liệu chưa ghi. Do đó cần điều khiển phản hồi ngay từ đầu.

## 21. Kiểm thử hợp đồng lỗi

Một lỗi format đẹp trong một test unit chưa chứng minh Gateway bảo vệ được contract. Cần kiểm tra ở nhiều cấp:

### 21.1. Unit tests

- Domain exception → public status/code/body đúng.
- Validation converter tạo field path và code đúng.
- Lỗi không biết → INTERNAL_ERROR an toàn.
- Không có ex.message, stack trace, SQL hoặc secret trong response.
- Header Retry-After, WWW-Authenticate có khi phù hợp.
- Content-Type đúng.
- Field optional bị lược bỏ hoặc tồn tại đúng hợp đồng.

### 21.2. Contract tests Gateway ↔ downstream

- Upstream trả known typed error và Gateway map ổn định.
- Upstream đổi message nhưng giữ code; public không đổi logic.
- Upstream trả 404 do route sai; Gateway không suy ra ORDER_NOT_FOUND.
- Upstream trả HTML lỗi; Gateway dùng generic problem.
- Upstream trả payload sai schema; Gateway có fallback an toàn.
- Upstream timeout; Gateway trả 504/response phù hợp và không khẳng định operation failed.
- Header nội bộ/secret không lọt qua proxy.

### 21.3. Contract tests public API ↔ clients

- Mỗi endpoint lỗi được khai báo trong OpenAPI.
- Client có fallback khi thấy errorCode chưa biết.
- Client không parse title/detail.
- Client xử lý 400/401/403/404/409/422/429/5xx theo semantics.
- Client tôn trọng Retry-After và có retry budget.
- Mobile cũ không crash khi có field optional mới.
- Schema type/status/detail/invalidParams đúng định dạng đã công bố.

### 21.4. Security tests

- Lỗi auth không tiết lộ account enumeration.
- Lỗi 403/404 không rò thông tin tài nguyên của người khác.
- Không phản chiếu bearer token, cookies hoặc thông tin thẻ.
- Không có stack trace hoặc internal hostname trong 5xx.
- Không trả raw upstream body chứa thông tin nhạy cảm.
- Correlation ID không mang thông tin riêng tư.
- Error response không được cache công khai trái ý muốn.

### 21.5. Fault-injection tests

- Downstream ngắt kết nối giữa request.
- Timeout khi upstream đã commit operation.
- DNS hoặc TLS failure ở một route.
- Gateway bị rate limit.
- Circuit breaker mở và đóng lại.
- Upstream trả body không parse được hoặc body vượt giới hạn.
- Khi dependency hồi phục, client retry không tạo trùng side effect.

**Kết quả cần kiểm tra không chỉ là status HTTP**: còn phải xác minh dữ liệu, operation state, audit và business invariant khi lỗi liên quan giao dịch.

## 22. Observability: lỗi công khai phải truy tìm được nguyên nhân nội bộ

Mục đích của correlation ID là giúp nối một lỗi client nhìn thấy với log và trace trong hệ thống.

Một dòng log có cấu trúc có thể gồm:

~~~json
{
  "requestId": "req-94de2",
  "traceId": "trace-abc123",
  "routeId": "orders-public-api",
  "upstreamService": "orders",
  "internalError": "DbConnectionPoolExhausted",
  "publicStatus": 503,
  "publicErrorCode": "SERVICE_UNAVAILABLE",
  "durationMs": 840
}
~~~

Đây là ví dụ nội bộ, không phải body gửi ra client. Trong production, log cần tuân thủ chính sách bảo mật và tránh các trường chứa secret hoặc PII. Nếu routeId hoặc upstreamService là nhạy cảm theo threat model, chỉ lưu trong hệ thống quan sát đã phân quyền.

### 22.1. Metrics nên theo dõi

| Chỉ số | Mục đích |
| --- | --- |
| Public 4xx theo route/errorCode | Nhận biết validation/auth/quota và trải nghiệm client |
| Public 5xx theo route/errorCode | Phát hiện lỗi hạ tầng và thay đổi |
| Gateway ↔ upstream status mapping | Tìm sai khác giữa lỗi nội bộ và public |
| Upstream connect/read timeout | Chẩn đoán network/deadline |
| Rate-limit reject rate | Quota/công suất |
| Error translation failures | Schema nội bộ không được hỗ trợ |
| Unknown public error codes | Client/contract đang lệch |
| p95/p99 response latency | Tương quan với lỗi và retry |
| Pending business operations | Không bỏ quên tác vụ đã nhận nhưng chưa chốt |
| Duplicate side effects | Phát hiện retry gây lỗi nghiệp vụ |

Khi tính SLO, phải định nghĩa rõ các lỗi 4xx nào do client và có nằm trong mẫu success rate hay không. Không được “giấu” lỗi 5xx bằng chuyển sang 200 chỉ để dashboard xanh.

### 22.2. Sampling trace khi có lỗi

Một số hệ thống tracing dùng sampling nên không phải request nào cũng có đầy đủ trace. Nếu trả public traceId, cơ chế logs/correlation cần đủ để hỗ trợ ngay cả khi trace chi tiết không được thu thập. Không hứa người dùng cung cấp ID là chắc chắn tìm được toàn bộ traces nếu retention/sampling không bảo đảm.

## 23. Caching, proxy và các hệ quả ít để ý

HTTP status và headers có tác động tới CDN/proxy/cache:

- Trả 200 khi thực tế rate-limited có thể dẫn đến cache/lưu trữ nhầm.
- Một số 404 có thể cache theo chính sách mặc định hoặc explicit; API nhạy cảm cần chính sách rõ.
- Public error chứa dữ liệu người dùng nên cân nhắc Cache-Control: no-store.
- Không tùy tiện thay đổi status làm mất semantics của conditional request như 304 hoặc 412.
- Không copy headers upstream bừa bãi vì có thể chứa Set-Cookie hoặc debug metadata.

Nếu lỗi từ API user-specific có thể bị cache chung cho nhiều người, đây là vấn đề bảo mật và correctness. Chính sách cache phải phù hợp cả URL, authorization, Vary và headers do Gateway quản lý.

## 24. GraphQL và gRPC có khác gì?

Các nguyên tắc ổn định code, bảo mật và phân loại retry vẫn đúng nhưng cách biểu diễn khác REST.

### 24.1. GraphQL

GraphQL thường biểu diễn errors trong response có cấu trúc, đôi khi HTTP status 200 vì request GraphQL đã được xử lý ở tầng protocol. Không nên ép cùng quy tắc REST 4xx/5xx lên mọi GraphQL response. Thay vào đó, công bố rõ GraphQL errors[].extensions.code, path, khả năng partial data, auth handling và chính sách logging.

Cần phân biệt lỗi transport/protocol với lỗi resolver và lỗi nghiệp vụ. Tránh lộ stack traces qua errors[].extensions.

### 24.2. gRPC

gRPC có hệ status codes riêng như INVALID_ARGUMENT, NOT_FOUND, PERMISSION_DENIED, UNAVAILABLE, DEADLINE_EXCEEDED. Một Gateway chuyển gRPC sang REST cần mapping có xét ngữ nghĩa, không chỉ đổi số.

Ví dụ DEADLINE_EXCEEDED khi client không nhận kết quả không chứng minh một side effect chưa xảy ra. Nếu Gateway chuyển sang HTTP 504 cần giữ contract về trạng thái chưa xác định và cách tra cứu operation.

### 24.3. Event/message APIs

Message handlers thường không có HTTP response trực tiếp. Cần typed failure, retry policy, DLQ, idempotency và status event có schema ổn định. Không phát stack trace nội bộ trong event công khai cho đối tác. Lỗi khi xử lý message không tự là lỗi của người đã gửi message nếu schema hợp lệ nhưng downstream bị quá tải.

## 25. Một ví dụ đầy đủ cho hệ thống đặt hàng

Giả sử public endpoint là POST /orders. Gateway xác thực client, chuyển đến Order Service, và Order gọi Inventory cùng Payment.

### Tình huống A — Thiếu trường quantity

Order trả typed validation error. Gateway trả 422 theo contract:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "errorCode": "VALIDATION_ERROR",
  "invalidParams": [
    {
      "name": "items[0].quantity",
      "code": "REQUIRED",
      "message": "Quantity is required."
    }
  ],
  "traceId": "req-a101"
}
~~~

Client highlight trường; không retry cùng payload.

### Tình huống B — Tồn kho không đủ

Inventory xác minh tồn kho thiếu và trả domain error. Order quyết định không thể đặt và Gateway trả public code INVENTORY_NOT_AVAILABLE theo business contract. Đây là lỗi nghiệp vụ rõ, không phải timeout.

Client có thể đề xuất giảm quantity hoặc chọn sản phẩm khác.

### Tình huống C — Payment provider chậm

Order đã lưu operationId nhưng kết quả payment chưa rõ. Nếu contract hỗ trợ xử lý bất đồng bộ, client có thể nhận 202 + operationId với trạng thái PENDING, rồi query status. Nếu Gateway thực sự không biết operation đã được tạo hay chưa, nó phải trả lỗi giao tiếp trung thực thay vì bịa payment declined.

### Tình huống D — Gateway quá tải

Gateway trả 503 hoặc chính sách tương ứng, có thể kèm Retry-After. Không chuyển lỗi này thành VALIDATION_ERROR hoặc đổ lỗi cho client khi request hợp lệ.

### Tình huống E — Service thay đổi schema lỗi nội bộ

Order Service nâng framework và thay exception text. Gateway vẫn trả cùng public code/status và schema nếu contract không đổi. Contract test phát hiện nếu lỗi mới không được map, rồi áp dụng generic fallback an toàn cho các trường hợp chưa nhận diện.

## 26. Quy trình thiết lập error contract cho một tổ chức

**Bước 1 — Xác định public API surface:** Các endpoint/version nào có client bên ngoài? Ai là API owner?

**Bước 2 — Chọn representation:** Problem Details hoặc envelope hiện hành, trường bắt buộc/tùy chọn, Content-Type, header liên quan.

**Bước 3 — Chuẩn hóa status semantics:** Chốt bảng 400/401/403/404/409/422/429/5xx và trường hợp đặc biệt theo domain.

**Bước 4 — Thiết kế public error catalog:** Code ổn định, type URI, trạng thái, mô tả, retry guidance, owner.

**Bước 5 — Thiết kế internal-to-public mapping:** Phân loại lỗi trước, map theo route/operation và typed code; generic fallback cho lỗi không biết.

**Bước 6 — Chính sách bảo mật:** Allowlist trường, redaction, auth handling, cache, headers và secrets.

**Bước 7 — Viết OpenAPI/contracts:** Dùng schemas thống nhất; document examples cho lỗi chính và optional extensions.

**Bước 8 — Xây thư viện/middleware phù hợp:** Dùng code chung cho serialization, traceId và map known errors, không trói mọi domain vào một exception class chung.

**Bước 9 — Kiểm thử theo nhiều tầng:** Unit, Gateway-upstream contracts, consumer tests, security, fault injection.

**Bước 10 — Vận hành và thay đổi:** Metrics, errorCode drift, SLA/SLO, deprecation và quy trình thay đổi breaking.

Một shared library hữu ích khi có quy ước chung, nhưng không nên biến Gateway thành nơi duy nhất quyết định tất cả logic nghiệp vụ.

## 27. Các sai lầm cần tránh

1. **Trả HTTP 200 với body chứa success=false cho mọi lỗi REST.** Làm hỏng semantics HTTP, cache, metrics và SDK.
2. **Trả mọi lỗi bằng 500.** Khiến client không phân biệt input invalid, auth, conflict, rate limit hay sự cố thật.
3. **Copy raw upstream body ra public.** Có thể lộ stack trace, SQL, hostname, token hoặc dữ liệu người khác.
4. **Dùng ex.getMessage() làm detail công khai.** Chuỗi exception thường không được thiết kế cho người dùng hoặc security boundary.
5. **Dùng message để client ra quyết định.** Localization và chỉnh nội dung sẽ phá logic.
6. **Đặt public code theo class/framework.** Kết dính client với công nghệ nội bộ.
7. **Đổi errorCode hoặc status mà không quản lý tương thích.** Client cũ có thể ngừng hoạt động.
8. **Bỏ qua Retry-After và retry budget.** Client có thể gây retry storm.
9. **Coi upstream timeout là business failure.** Dễ tạo thanh toán hoặc đơn trùng.
10. **Gộp 401 và 403 bất chấp semantics.** Làm sai cơ chế xác thực và xử lý quyền.
11. **Không có fallback cho lỗi không biết.** Gateway có thể trả HTML hoặc lỗi nội bộ không thể parse.
12. **Đưa mọi error nội bộ vào public catalog.** Mở rộng bề mặt tấn công và gây compatibility burden không cần thiết.
13. **Không test invalidParams schema.** Web/mobile không biết field nào cần sửa.
14. **Không bảo vệ caching của error response nhạy cảm.** Rủi ro rò dữ liệu qua proxy/CDN.
15. **Chỉ test lỗi phát sinh trong controller.** Gateway, reverse proxy và authentication filter cũng có thể tạo lỗi.
16. **Không ghi traceId hoặc requestId có thể tra cứu.** Hỗ trợ khó tìm nguyên nhân.
17. **Cho phép client cũ crash khi thấy code lạ.** Public API khó tiến hóa an toàn.
18. **Dùng ErrorCode RETRYABLE cho mọi 5xx.** Có thể phát sinh side effect trùng.
19. **Gateway tự đoán domain error từ chuỗi text.** Dễ map sai khi ngôn ngữ/schema đổi.
20. **Không thống nhất type/status/errorCode trong logs và responses.** Quan sát và debugging trở nên mơ hồ.

## 28. Bài tập thực hành

### Bài tập A — Chuẩn hóa lỗi của ba service

Catalog trả:
~~~json
{"error":"missing product","id":"P01"}
~~~

Order trả:
~~~json
{"code":"ERR_ORDER_STATE","message":"cannot cancel"}
~~~

Payment trả:
~~~json
{"exception":"SQLTimeoutException","sql":"SELECT ..."}
~~~

Hãy thiết kế một public error envelope và mapping cho các tình huống tương ứng. Chỉ rõ loại thông tin nào **không được** đưa ra ngoài. Đặt errorCode ổn định và chính sách retry.

### Bài tập B — Chuyển đổi API cũ sang Problem Details

Một ứng dụng mobile cũ luôn nhận HTTP 200 và trường errorCode trong body. Đề xuất kế hoạch migration sang HTTP status đúng và application/problem+json mà không làm hỏng ứng dụng chưa cập nhật. Nêu việc versioning, feature rollout, compatibility tests và deprecation.

### Bài tập C — Trả 404 hay 403?

Người dùng A gọi GET /orders/{id} với id của người dùng B. Hãy thảo luận khi nào nên trả 403 và khi nào có thể dùng 404 để tránh tiết lộ tài nguyên. Nêu rủi ro enumeration, logging và contract consistency.

### Bài tập D — Gateway timeout sau payment

Client gửi POST /payments với idempotency key; Payment có thể đã xử lý nhưng Gateway trả 504. Hãy thiết kế errorCode, retry guidance, status lookup và cách client hiển thị trạng thái chưa xác định. Không được kết luận payment thất bại chỉ từ timeout.

### Bài tập E — Contract test tự động

Viết ít nhất năm test cases bảo đảm:
- public schema đúng;
- unknown error được sanitize;
- 429 có hướng dẫn retry;
- 401 có challenge;
- client cũ xử lý mã mới;
- error body không lộ secret hoặc topology.

## 29. Tự kiểm tra kiến thức

1. Vì sao định dạng lỗi là một phần của hợp đồng công khai, không chỉ là vấn đề UI?
2. API Gateway nên tự phát sinh những loại lỗi nào?
3. Domain service nên sở hữu loại lỗi nào?
4. RFC 9457 Problem Details có những field lõi gì?
5. errorCode khác title và detail ở chỗ nào?
6. Khi nào 400 khác 422 theo contract?
7. 401, 403 và 404 có vai trò bảo mật khác nhau ra sao?
8. Gateway nhận upstream 404 có nên luôn trả public 404 không?
9. Vì sao 504 không chứng minh giao dịch thanh toán thất bại?
10. Client nên phản ứng với 429 như thế nào?
11. Tại sao không trả raw exception message trong response?
12. Thay errorCode hoặc status có thể là breaking change như thế nào?
13. Cách xử lý public error code chưa biết ở client?
14. Khi API dùng Problem Details, Content-Type nào thường áp dụng?
15. Vì sao traceId không nên chứa dữ liệu riêng tư hoặc topology?
16. Contract test Gateway-upstream cần kiểm tra điều gì khi upstream đổi schema?
17. Một error response có thể gây leak qua caching ra sao?
18. GraphQL/gRPC khác REST ở biểu diễn lỗi như thế nào?
19. Khi nào nên trả 202/PENDING thay vì một kết quả nghiệp vụ giả?
20. Hãy nêu một trường hợp generic public error phù hợp hơn một thông điệp chi tiết.

## 30. Checklist triển khai

- [ ] API có một error representation đã công bố và Content-Type phù hợp.
- [ ] HTTP status phản ánh đúng semantics của lỗi.
- [ ] Public errorCode/type ổn định, có tài liệu và owner.
- [ ] Client không parse title/detail để ra quyết định.
- [ ] Validation fields có schema đường dẫn thống nhất.
- [ ] Authentication challenge, authorization và status được xử lý đúng.
- [ ] Rate limit có 429 và Retry-After khi thích hợp.
- [ ] 5xx/timeout không tự biến thành business failure.
- [ ] Retry policy có idempotency/status lookup cho side effects.
- [ ] Unknown upstream errors được chuyển thành generic public problem an toàn.
- [ ] Không gửi stack trace, SQL, hostname, token, PII qua response.
- [ ] Public requestId/traceId đủ hỗ trợ điều tra và không lộ secret.
- [ ] Headers, cookies, cache và proxy policy được kiểm soát.
- [ ] Schema OpenAPI có lỗi phổ biến, examples và optional fields.
- [ ] Có quy tắc tương thích, deprecation và versioning.
- [ ] Contract test kiểm tra Gateway, service, client và auth filters.
- [ ] Fault tests cho upstream timeout, 502/503/504 và response sai schema.
- [ ] Metrics quan sát cả public status, errorCode và upstream cause.
- [ ] Không thay đổi format lỗi hiện hữu mà thiếu kế hoạch migration.

## 31. Kết luận

**API Gateway phải bảo vệ hợp đồng công khai, không phơi bày ngẫu nhiên lỗi của các microservices phía sau.** Một public error contract tốt có status HTTP đúng, mã ổn định cho client, mô tả rõ nhưng an toàn, các trường mở rộng được tài liệu hóa, chính sách retry hợp lệ và định danh truy vết đủ dùng.

Problem Details là một lựa chọn chuẩn hóa hữu ích, nhưng không quan trọng bằng việc giữ đúng semantics và tương thích của API đã phát hành. Gateway nên ánh xạ lỗi nội bộ theo typed contract, có generic fallback cho lỗi không biết, không đoán trạng thái nghiệp vụ từ timeout và không cho chi tiết hạ tầng rò qua body hoặc headers.

Khi error codes, schema, mapping, security, versioning và contract tests được thiết kế cùng nhau, nhóm có thể thay đổi các service nội bộ mà web/mobile/đối tác vẫn nhìn thấy **một hợp đồng đáng tin cậy, ổn định và có thể xử lý tự động**.