# Mã lỗi và relation trong Spring HATEOAS

Một REST API cần trả lỗi đủ rõ để client biết chuyện gì đã xảy ra và có thể xử lý tiếp theo cách nào. HTTP status cho biết nhóm kết quả ở mức giao thức, nhưng đôi khi chưa giải thích được lỗi nghiệp vụ cụ thể. Ví dụ, 409 Conflict có thể xuất hiện khi đơn hàng đã giao nên không thể hủy, khi tên người dùng đã tồn tại hoặc khi phiên bản dữ liệu bị xung đột. Client cần một định danh lỗi ổn định để phân biệt những trường hợp này.

Trong API dùng Spring HATEOAS, lỗi còn có thể cung cấp các relation dẫn tới tài liệu trợ giúp, trạng thái tài nguyên hoặc bước tiếp theo. Thiết kế tốt cần tách mã lỗi máy đọc được khỏi thông điệp dành cho con người, đồng thời công bố link có semantics rõ ràng. Bài này dùng RFC 9457 Problem Details làm nền tảng, bổ sung mã lỗi riêng của ứng dụng và trình bày cách cung cấp relation cho response lỗi.

## 1. Vì sao cần mã lỗi ngoài HTTP status?

HTTP status mô tả kết quả ở cấp giao thức:

| Status | Ý nghĩa tổng quát | Ví dụ trong API đơn hàng |
| --- | --- | --- |
| 400 Bad Request | Request không hợp lệ về cú pháp hoặc cấu trúc. | JSON không parse được hoặc tham số sai định dạng. |
| 401 Unauthorized | Request thiếu thông tin xác thực hợp lệ. | Access token thiếu hoặc hết hạn. |
| 403 Forbidden | Server hiểu request nhưng từ chối quyền thực hiện. | Người dùng không được phép hủy đơn của người khác. |
| 404 Not Found | Không tìm thấy resource hoặc server không muốn tiết lộ sự tồn tại của nó. | Mã đơn hàng không tồn tại. |
| 409 Conflict | Request xung đột với trạng thái hiện tại của resource. | Đơn đã giao nên không thể hủy. |
| 422 Unprocessable Content | Nội dung request hợp lệ về cú pháp nhưng không xử lý được theo ngữ nghĩa. | Trường ngày giao có giá trị không hợp lệ theo quy tắc nghiệp vụ. |
| 429 Too Many Requests | Client gửi quá nhiều request trong khoảng thời gian nhất định. | Vượt giới hạn tạo đơn. |
| 503 Service Unavailable | Server tạm thời không thể xử lý. | Dịch vụ phụ thuộc đang bảo trì. |

Một status có thể đại diện cho nhiều lỗi khác nhau. Nếu client chỉ kiểm tra 409, nó không thể biết nên yêu cầu người dùng chọn tên khác hay thông báo đơn hàng đã chuyển trạng thái. Mã lỗi nghiệp vụ cung cấp phân loại chi tiết hơn, ví dụ ORDER_ALREADY_SHIPPED hoặc USERNAME_ALREADY_TAKEN.

Mã lỗi không thay thế HTTP status. Hãy dùng status đúng với semantics HTTP, sau đó dùng mã lỗi để định danh nguyên nhân cụ thể trong nhóm status đó.

## 2. RFC 9457 Problem Details

RFC 9457 định nghĩa cấu trúc Problem Details cho HTTP API. Spring Framework hỗ trợ cấu trúc này qua ProblemDetail, ErrorResponse, ErrorResponseException và ResponseEntityExceptionHandler.

Một Problem Details JSON thường có các thành viên:

| Thành viên | Ý nghĩa |
| --- | --- |
| type | URI định danh loại lỗi; đây là định danh chính của problem type. |
| title | Tóm tắt ngắn gọn loại lỗi. |
| status | HTTP status được mô tả trong body. |
| detail | Giải thích cụ thể cho lần xảy ra lỗi này. |
| instance | URI reference định danh lần xảy ra lỗi cụ thể. |

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Không thể hủy đơn hàng đã giao",
  "status": 409,
  "detail": "Đơn hàng đã được chuyển sang trạng thái SHIPPED.",
  "instance": "urn:uuid:8c9a1a9e-83db-4fcb-8d42-6a1d0b2a3f10"
}
~~~

type định danh loại lỗi, còn instance định danh một lần xảy ra cụ thể. Nhiều request có thể cùng type nhưng mỗi occurrence có instance khác nhau. Khi không có type, RFC 9457 mặc định dùng about:blank, nghĩa là problem không có semantics bổ sung ngoài HTTP status.

## 3. Phân biệt type URI và mã lỗi ứng dụng

Trong response lỗi có thể xuất hiện cả type và code, nhưng hai trường này cần có vai trò rõ ràng:

- type là định danh chuẩn của problem type theo RFC 9457. Client dùng URI này làm định danh chính.
- code là extension do API định nghĩa, thường là token ngắn như ORDER_ALREADY_SHIPPED, hữu ích cho logging, mapping giao diện hoặc tương thích với hệ thống nội bộ.
- title và detail dành cho con người; client không nên phân tích chuỗi này để quyết định logic.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Không thể hủy đơn hàng đã giao",
  "status": 409,
  "detail": "Đơn hàng đã được chuyển sang trạng thái SHIPPED.",
  "instance": "urn:uuid:8c9a1a9e-83db-4fcb-8d42-6a1d0b2a3f10",
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

Không tạo một mã mới cho mỗi lần request. ORDER_ALREADY_SHIPPED phải ổn định qua nhiều lần xảy ra và không chứa ID đơn hàng, username, timestamp hoặc dữ liệu riêng tư. Thông tin occurrence thuộc instance hoặc các trường correlation riêng.

Nếu API đã chọn type URI làm định danh đủ dùng, không bắt buộc phải thêm code. Nếu thêm code, hãy duy trì mapping một-một hoặc được tài liệu hóa giữa code và type để tránh hai định danh mâu thuẫn.

Nên dùng absolute URI ổn định cho type. Nếu URI dùng HTTP hoặc HTTPS và có thể truy cập, tài liệu tại đó nên giải thích problem type và cách khắc phục. Client không nên tự động gọi type URI trong luồng xử lý thông thường; chỉ công cụ hỗ trợ developer mới nên truy cập khi cần tra cứu.

## 4. Thiết kế taxonomy mã lỗi

Một taxonomy hữu ích thường nhóm mã theo domain hoặc resource, sau đó mô tả điều kiện nghiệp vụ cụ thể:

| Mã lỗi | HTTP status | Ý nghĩa |
| --- | --- | --- |
| ORDER_NOT_FOUND | 404 | Không tìm thấy đơn hàng. |
| ORDER_ALREADY_SHIPPED | 409 | Không thể hủy đơn đã giao. |
| ORDER_VERSION_CONFLICT | 409 | Phiên bản đơn hàng không còn mới nhất. |
| ORDER_INVALID_TRANSITION | 409 | Chuyển trạng thái không hợp lệ. |
| CUSTOMER_SUSPENDED | 403 hoặc 409 tùy semantics | Khách hàng bị tạm khóa nên không thể thực hiện thao tác. |
| VALIDATION_FAILED | 400 hoặc 422 theo hợp đồng | Dữ liệu đầu vào không đạt validation. |
| RATE_LIMIT_EXCEEDED | 429 | Vượt giới hạn request. |

Chọn status dựa trên semantics HTTP, không dựa vào tên mã lỗi. Ví dụ ORDER_ALREADY_SHIPPED thường phù hợp với 409 Conflict vì request xung đột với trạng thái hiện tại của đơn hàng.

Quy tắc đặt mã:

- Viết hoa và dùng dấu gạch dưới để dễ đọc.
- Không đưa thông tin động vào mã.
- Không tái sử dụng mã cũ cho ý nghĩa khác.
- Không phụ thuộc mã vào tên class exception hoặc tên package Java.
- Công bố danh sách mã, status tương ứng và hành vi client nên thực hiện.
- Giữ mã ổn định trong suốt vòng đời API version đã cam kết.

## 5. Dùng ProblemDetail trong Spring Framework

Spring Framework cung cấp ProblemDetail để biểu diễn RFC 9457. Có thể tạo body bằng forStatusAndDetail, đặt type/title/instance và thêm extension member bằng setProperty.

~~~java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Đơn hàng đã được chuyển sang trạng thái SHIPPED."
);

problem.setType(URI.create(
        "https://api.example.com/problems/order-already-shipped"));
problem.setTitle("Không thể hủy đơn hàng đã giao");
problem.setInstance(URI.create("urn:uuid:" + UUID.randomUUID()));
problem.setProperty("code", "ORDER_ALREADY_SHIPPED");
~~~

Với Jackson được Spring cấu hình cho Problem Details, các extension trong properties được serialize thành các thuộc tính cấp cao nhất của JSON. Vì vậy code xuất hiện cùng type, title, status và các thành viên chuẩn.

instance cần định danh occurrence. Có thể dùng URI dạng urn:uuid: nếu client chỉ cần một mã tham chiếu duy nhất; nếu cung cấp URI có thể truy cập để xem chi tiết occurrence, hãy bảo vệ endpoint đó theo chính sách bảo mật. Không dùng đường dẫn resource chung làm instance nếu nó không phân biệt được từng lần lỗi.

## 6. Xử lý exception tập trung bằng @RestControllerAdvice

Không nên tạo Problem Details khác nhau ở từng controller. Một exception handler tập trung giúp giữ status, type, code và định dạng ổn định:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderAlreadyShippedException.class)
    ResponseEntity<ProblemDetail> handleOrderAlreadyShipped(
            OrderAlreadyShippedException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Đơn hàng đã được giao nên không thể hủy."
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-already-shipped"));
        problem.setTitle("Không thể hủy đơn hàng đã giao");
        problem.setInstance(URI.create("urn:uuid:" + UUID.randomUUID()));
        problem.setProperty("code", "ORDER_ALREADY_SHIPPED");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Ví dụ giả định OrderAlreadyShippedException là exception nghiệp vụ được service ném ra. Controller không cần biết cách tạo JSON lỗi; nó chỉ gọi use case và để exception handler chuyển lỗi thành HTTP response.

Trong ứng dụng thực tế, có thể dùng ResponseEntityExceptionHandler làm base class để xử lý các exception MVC chuẩn, sau đó bổ sung handler cho exception nghiệp vụ. Spring MVC cũng cung cấp ErrorResponse để exception đóng gói status, headers và ProblemDetail body.

## 7. Giữ status HTTP và status trong body nhất quán

Response có hai nơi thể hiện status:

- HTTP status line, ví dụ 409 Conflict.
- Thành viên status trong Problem Details body.

Hai giá trị phải nhất quán. Khi tạo ProblemDetail bằng forStatus hoặc forStatusAndDetail, status được đặt từ đối số. Khi tạo ResponseEntity, hãy dùng cùng status đó:

~~~java
return ResponseEntity.status(problem.getStatus())
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
~~~

Không trả HTTP 200 với body có status: 409. Client, proxy, monitoring và retry policy dựa vào HTTP status thực tế; body chỉ bổ sung chi tiết.

## 8. Mã lỗi validation và danh sách lỗi theo field

Một request có thể có nhiều validation error. RFC 9457 cho phép problem type định nghĩa extension member, ví dụ errors, chứa danh sách lỗi theo vị trí trong request.

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Dữ liệu gửi lên không hợp lệ",
  "status": 422,
  "detail": "Có hai trường cần được sửa.",
  "instance": "urn:uuid:4e4cfa3a-95c4-4d74-bd7b-2e0e4e16c770",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "code": "EMAIL_INVALID",
      "pointer": "#/email",
      "detail": "Email không đúng định dạng."
    },
    {
      "code": "QUANTITY_OUT_OF_RANGE",
      "pointer": "#/quantity",
      "detail": "Số lượng phải lớn hơn 0."
    }
  ]
}
~~~

pointer có thể dùng JSON Pointer để chỉ vị trí trong request body. Client nên dùng code để xác định loại lỗi và pointer để gắn thông báo vào field tương ứng. Không yêu cầu client phân tích detail, vì thông điệp có thể được dịch hoặc chỉnh sửa.

Nếu API dùng 400 Bad Request cho validation, hãy giữ status đó nhất quán trong contract. Nếu chọn 422 Unprocessable Content, tài liệu cần giải thích rõ trường hợp nào dùng 422 và test phải khóa semantics đó.

## 9. Mã lỗi phải ổn định, thông điệp có thể thay đổi

Client có thể dùng mã lỗi để chọn hành vi:

~~~java
switch (problem.code()) {
    case "ORDER_ALREADY_SHIPPED" ->
            showMessage("Đơn hàng đã được giao.");
    case "ORDER_VERSION_CONFLICT" ->
            reloadOrder();
    case "VALIDATION_FAILED" ->
            showFieldErrors(problem.errors());
    default ->
            showGenericError();
}
~~~

Ví dụ minh họa logic phía client. Mã lỗi là token ổn định; nội dung hiển thị có thể đến từ localization resource của client hoặc từ title/detail đã được server bản địa hóa.

Không dùng câu thông báo làm khóa logic. Thay đổi dấu câu, ngôn ngữ hoặc cách diễn đạt không nên buộc client phát hành lại. Cũng không đưa stack trace, tên class, SQL, hostname nội bộ hoặc thông tin xác thực vào detail.

## 10. Relation trong response lỗi có tác dụng gì?

Một response lỗi vẫn có thể giúp client điều hướng hoặc khắc phục vấn đề. Relation có thể dẫn tới:

- help: hướng dẫn người dùng hoặc client xử lý loại lỗi.
- describedby: tài liệu mô tả problem type hoặc cấu trúc lỗi.
- Relation mở rộng có URI tuyệt đối: tài nguyên nghiệp vụ riêng của API, ví dụ quy trình khiếu nại hoặc yêu cầu hỗ trợ.

Relation cho biết ý nghĩa của link; href cho biết đích đến. Không đặt tên relation theo tên method Java hoặc tên controller nếu client cần hiểu semantics lâu dài.

Ví dụ response có thể công bố link tới tài liệu lỗi bằng HTTP Link header:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Link: <https://docs.example.com/problems/order-already-shipped>; rel="describedby"
Link: <https://support.example.com/orders>; rel="help"
~~~

RFC 9457 không bắt buộc một cấu trúc link cụ thể trong Problem Details body. Link header dùng Web Linking để công bố relation mà không thay đổi cấu trúc chuẩn của application/problem+json.

## 11. Thêm Link header bằng Spring

Có thể thêm nhiều link relation vào response lỗi qua HttpHeaders:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_PROBLEM_JSON);
headers.add(HttpHeaders.LINK,
        "<https://docs.example.com/problems/order-already-shipped>; rel=\"describedby\"");
headers.add(HttpHeaders.LINK,
        "<https://support.example.com/orders>; rel=\"help\"");

return ResponseEntity.status(HttpStatus.CONFLICT)
        .headers(headers)
        .body(problem);
~~~

Mỗi header Link có một target URI và relation. Hãy dùng relation đã đăng ký khi semantics phù hợp; với relation riêng của API, dùng URI tuyệt đối để tránh xung đột tên. Đảm bảo các URI tài liệu ổn định và không chứa token hoặc thông tin người dùng.

Khi dùng Link header, client cần đọc response headers. Nếu muốn link nằm trong JSON body để client chỉ cần parse body, hãy định nghĩa extension member có schema rõ ràng và giữ schema đó ổn định.

## 12. Khi nào nên dùng extension links trong Problem Details?

Một API có thể định nghĩa extension member links:

~~~json
{
  "type": "https://api.example.com/problems/payment-required",
  "title": "Cần hoàn tất thanh toán",
  "status": 409,
  "code": "PAYMENT_REQUIRED",
  "links": [
    {
      "rel": "payment",
      "href": "https://api.example.com/orders/o-42/payment",
      "title": "Mở quy trình thanh toán"
    },
    {
      "rel": "help",
      "href": "https://docs.example.com/problems/payment-required",
      "title": "Hướng dẫn thanh toán"
    }
  ]
}
~~~

Đây là extension do ứng dụng định nghĩa, không phải thành viên chuẩn bắt buộc của RFC 9457. Tài liệu API cần mô tả kiểu dữ liệu, cardinality, quy tắc relation và cách client xử lý link chưa biết. Client phải bỏ qua extension mà nó không hiểu để API có thể bổ sung thông tin trong tương lai.

Nếu cần dùng link trong header và body, tránh để hai nơi công bố các URI mâu thuẫn. Chọn một nguồn chính hoặc định nghĩa rõ mục đích từng nơi.

## 13. Phân biệt Problem Details với HAL error representation

application/problem+json và application/hal+json là hai media type có mục tiêu khác nhau:

| Media type | Cấu trúc chính | Cách công bố link |
| --- | --- | --- |
| application/problem+json | RFC 9457: type, title, status, detail, instance và extensions. | Có thể dùng HTTP Link header hoặc extension links do API định nghĩa. |
| application/hal+json | HAL: payload, _links và có thể có _embedded. | Dùng link relation trong _links. |

ProblemDetail không tự biến thành HAL representation chỉ vì ứng dụng có Spring HATEOAS. Nếu response dùng application/problem+json, không tự ý thêm _links rồi giả định client hiểu semantics HAL. Nếu API muốn error body theo HAL, hãy định nghĩa một RepresentationModel riêng và công bố media type HAL một cách nhất quán.

Ví dụ model lỗi theo HAL:

~~~java
class HalApiError extends RepresentationModel<HalApiError> {

    private final String code;
    private final String title;
    private final String detail;

    HalApiError(String code, String title, String detail) {
        this.code = code;
        this.title = title;
        this.detail = detail;
    }

    public String getCode() { return code; }
    public String getTitle() { return title; }
    public String getDetail() { return detail; }
}
~~~

Controller có thể thêm link help bằng Spring HATEOAS Link builder rồi trả HalApiError với status HTTP phù hợp và MediaTypes.HAL_JSON. Đây là một error contract riêng của ứng dụng; nó không tự động là RFC 9457 Problem Details. Hãy chọn một media type làm hợp đồng rõ ràng cho client.

## 14. Chọn relation phù hợp và tránh lạm dụng self

Relation phải mô tả mục đích của link trong ngữ cảnh response lỗi:

| Relation | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| help | Hướng dẫn cách xử lý lỗi. | Trang hướng dẫn hoàn tất thanh toán. |
| describedby | Tài liệu mô tả cấu trúc hoặc loại lỗi. | Tài liệu problem type ORDER_ALREADY_SHIPPED. |
| about | Resource là chủ thể được nói tới bởi response/link. | Resource đơn hàng liên quan tới lỗi. |
| URI relation riêng | Hành động hoặc tài nguyên đặc thù của domain. | https://api.example.com/rels/request-review. |

Không dùng self cho trang trợ giúp chỉ vì đó là link duy nhất. self phải trỏ tới chính resource được biểu diễn. Problem Details instance đã định danh occurrence; nếu occurrence có endpoint riêng, hãy công bố link relation rõ ràng tới endpoint đó.

Không đặt relation retry nếu link không thực sự mô tả một request có thể lặp lại. Với lỗi tạm thời, HTTP Retry-After có thể phù hợp hơn để chỉ thời điểm client nên thử lại.

## 15. Mã lỗi và relation cho lỗi có thể khắc phục

Một error response hữu ích không chỉ nói request thất bại mà còn giúp client khám phá bước tiếp theo. Ví dụ thanh toán chưa hoàn tất:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Link: <https://api.example.com/orders/o-42/payment>; rel="https://api.example.com/rels/payment"
Link: <https://docs.example.com/problems/payment-required>; rel="help"

{
  "type": "https://api.example.com/problems/payment-required",
  "title": "Cần hoàn tất thanh toán",
  "status": 409,
  "detail": "Đơn hàng chưa được thanh toán.",
  "instance": "urn:uuid:cb0d8a80-3c3a-42f4-9d8d-7c9a8f3e47f0",
  "code": "PAYMENT_REQUIRED"
}
~~~

Client có thể dựa vào code hoặc type để nhận diện vấn đề, rồi theo relation payment để tiếp tục. Server vẫn phải kiểm tra quyền và trạng thái khi client gọi link đó; việc công bố link không phải là authorization.

Nếu không có hành động nào phù hợp, không cần tạo link giả. Một response lỗi chỉ nên công bố những relation có đích đến và semantics thực sự hữu ích.

## 16. Không tiết lộ thông tin nhạy cảm trong lỗi

Error representation thường được ghi log ở client, gateway và hệ thống quan sát. Chỉ công bố dữ liệu cần thiết để client hiểu và khắc phục vấn đề:

- Không trả stack trace hoặc tên class exception.
- Không trả SQL, câu lệnh database hoặc cấu trúc schema nội bộ.
- Không trả token, secret, password hoặc thông tin xác thực.
- Không để detail tiết lộ sự tồn tại của tài khoản nếu chính sách bảo mật yêu cầu che giấu.
- Không đưa PII vào type, code hoặc URL relation.
- Không cho endpoint instance truy xuất log nội bộ mà thiếu authorization.

Mã lỗi nên mô tả loại vấn đề, không mô tả dữ liệu của người dùng. Nếu cần correlation ID, dùng một định danh opaque và không thể suy ra thông tin nhạy cảm.

## 17. Bản địa hóa title và detail

title và detail là văn bản dành cho con người, vì vậy có thể được bản địa hóa theo Accept-Language. type và code phải ổn định bất kể ngôn ngữ.

Ví dụ hai response có thể khác nội dung hiển thị nhưng cùng định danh:

~~~json
{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Không thể hủy đơn hàng đã giao",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

~~~json
{
  "type": "https://api.example.com/problems/order-already-shipped",
  "title": "Cannot cancel a shipped order",
  "status": 409,
  "code": "ORDER_ALREADY_SHIPPED"
}
~~~

Nếu representation thay đổi theo Accept-Language, cache HTTP cần phân biệt biến thể phù hợp, thường qua Vary: Accept-Language. Không dịch code hoặc đổi URI type theo locale.

## 18. Kiểm thử mã lỗi và Problem Details bằng MockMvc

Kiểm thử phải khóa HTTP status, content type, type URI và code:

~~~java
mockMvc.perform(post("/orders/{id}/cancel", shippedOrderId)
        .with(user("buyer-7").roles("CUSTOMER"))
        .with(csrf())
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isConflict())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/order-already-shipped"))
    .andExpect(jsonPath("$.status").value(409))
    .andExpect(jsonPath("$.code").value("ORDER_ALREADY_SHIPPED"))
    .andExpect(jsonPath("$.instance").isNotEmpty());
~~~

Test giả định người dùng có quyền gọi thao tác nhưng đơn đã giao, để lỗi đến từ business state chứ không phải authorization. Nếu thiếu CSRF token hoặc principal không có quyền, request có thể bị từ chối trước khi exception nghiệp vụ được xử lý.

Không chỉ kiểm tra detail bằng chuỗi dài nếu thông điệp có thể được bản địa hóa. Hãy ưu tiên type, status và code cho contract assertion.

## 19. Kiểm thử relation trong Link header

MockMvc có thể xác nhận response lỗi công bố relation đúng:

~~~java
import java.util.Collection;

import static org.assertj.core.api.Assertions.assertThat;

mockMvc.perform(post("/orders/{id}/cancel", shippedOrderId)
        .with(user("buyer-7").roles("CUSTOMER"))
        .with(csrf())
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isConflict())
    .andExpect(result -> {
        Collection<String> links =
                result.getResponse().getHeaders(HttpHeaders.LINK);
        assertThat(links).anyMatch(value ->
                value.contains("rel=\"describedby\""));
        assertThat(links).anyMatch(value ->
                value.contains("rel=\"help\""));
    });
~~~

Test dùng AssertJ để kiểm tra từng giá trị Link header; cách này hoạt động cả khi container giữ nhiều header riêng biệt. Với kiểm thử chặt hơn, parse từng Link header thành relation và target thay vì chỉ tìm substring.

Kiểm tra cả href để bảo đảm relation dẫn tới đúng tài liệu. Không dùng hostname production cố định trong test nếu ứng dụng chạy sau reverse proxy; có thể kiểm tra URI path hoặc dùng base URL cấu hình cho môi trường test.

## 20. Kiểm thử extension links và client fallback

Nếu API định nghĩa links trong Problem Details body, test cần xác nhận:

- Mỗi link có rel và href hợp lệ.
- Relation bắt buộc tồn tại khi problem type tương ứng.
- Client bỏ qua relation hoặc extension chưa biết.
- URI đích không chứa token hoặc dữ liệu nhạy cảm.
- Link không được công bố nếu hành động không khả dụng.

Consumer test nên mô phỏng một response có thêm extension mới để xác nhận client cũ vẫn đọc được type, status và code. RFC 9457 yêu cầu consumer bỏ qua extension member mà nó không nhận biết, giúp problem type có thể mở rộng mà không làm hỏng client.

## 21. Kiểm thử mã lỗi cho từng nhóm status

Nên có bảng contract test cho các trường hợp phổ biến:

| Kịch bản | Status | Type/code cần kiểm tra |
| --- | --- | --- |
| Đơn không tồn tại | 404 | order-not-found / ORDER_NOT_FOUND |
| Đơn đã giao | 409 | order-already-shipped / ORDER_ALREADY_SHIPPED |
| Version cũ | 409 | order-version-conflict / ORDER_VERSION_CONFLICT |
| Validation lỗi | 422 | validation-failed / VALIDATION_FAILED |
| Không đủ quyền | 403 | Type/code theo chính sách authorization |
| Quá giới hạn | 429 | rate-limit-exceeded / RATE_LIMIT_EXCEEDED |
| Dịch vụ tạm ngừng | 503 | service-unavailable / SERVICE_UNAVAILABLE |

Không bắt buộc mọi lỗi đều có mã riêng nếu HTTP status đã đủ diễn đạt. Hãy ưu tiên mã cho những trường hợp client cần xử lý khác nhau hoặc đội vận hành cần phân loại ổn định.

## 22. Những lỗi thiết kế thường gặp

**Dùng HTTP status làm mã lỗi duy nhất.** Một status có thể đại diện nhiều tình huống nghiệp vụ; thêm code ổn định khi client cần phân biệt.

**Dùng title hoặc detail làm khóa logic.** Văn bản có thể thay đổi hoặc được dịch; client nên dùng type/code.

**Dùng code thay cho type URI.** RFC 9457 định nghĩa type URI là định danh chính của problem type. Code chỉ nên là extension bổ sung.

**Tạo code mới cho mỗi occurrence.** Code phải định danh loại lỗi; instance mới định danh lần xảy ra.

**Trả status trong body khác HTTP status.** Đồng bộ hai giá trị để client, proxy và monitoring xử lý đúng.

**Đưa stack trace vào detail.** Chỉ trả thông tin giúp client khắc phục; chi tiết nội bộ ghi ở server log.

**Nhầm type URI với link relation.** type định danh problem type; relation mô tả ý nghĩa của một link.

**Nhét _links vào application/problem+json mà không định nghĩa contract.** Dùng Link header hoặc extension links có schema rõ ràng; nếu cần HAL, hãy chọn HAL representation riêng.

**Dùng relation không đúng semantics.** help và describedby phải trỏ tới tài liệu phù hợp; link action chỉ xuất hiện khi hành động thực sự khả dụng.

**Không test lỗi sau authorization.** Test cần thiết lập principal và CSRF phù hợp để chắc chắn lỗi được tạo ở đúng tầng.

## 23. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng error contract cho API đơn hàng:

1. Tạo taxonomy gồm ORDER_NOT_FOUND, ORDER_ALREADY_SHIPPED, ORDER_VERSION_CONFLICT và VALIDATION_FAILED.
2. Chọn HTTP status và type URI ổn định cho từng problem type.
3. Dùng ProblemDetail và @RestControllerAdvice để tạo response application/problem+json.
4. Thêm extension member code và instance duy nhất cho mỗi occurrence.
5. Tạo validation extension chứa code và JSON Pointer cho từng field.
6. Thêm describedby và help relation bằng HTTP Link header.
7. Nếu cần link trong body, định nghĩa extension links và tài liệu hóa schema.
8. Nếu API chọn HAL error, tạo RepresentationModel riêng và công bố application/hal+json nhất quán.
9. Dùng MockMvc kiểm tra status, media type, type, code, instance và relation.
10. Kiểm thử client bỏ qua extension chưa biết và không phân tích title/detail.
11. Xác nhận error body không tiết lộ stack trace, SQL, token hoặc dữ liệu cá nhân.
12. Viết tài liệu problem type có thể truy cập và mô tả cách client khắc phục lỗi.

Bạn đã nắm được cách thiết kế mã lỗi và relation khi có thể phân biệt HTTP status, problem type URI, application error code và occurrence instance; tạo response Problem Details nhất quán; công bố link trợ giúp bằng relation đúng semantics; và kiểm thử contract để client xử lý lỗi mà không phụ thuộc vào câu thông báo hoặc chi tiết triển khai nội bộ.

## Tài liệu tham khảo chính thức

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Framework – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
- [IANA – Link Relation Types](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
