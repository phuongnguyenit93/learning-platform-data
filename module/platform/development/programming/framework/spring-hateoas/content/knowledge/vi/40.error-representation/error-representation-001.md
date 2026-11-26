# Resource lỗi

REST API cần một cách trả lỗi nhất quán để client hiểu chuyện gì đã xảy ra và quyết định bước tiếp theo. Nếu mỗi controller trả một JSON tùy ý, client phải viết nhiều nhánh xử lý theo từng endpoint. Khi API dùng Spring HATEOAS, representation thành công có thể chứa link để client khám phá tài nguyên và hành động; representation lỗi cũng cần một hợp đồng rõ ràng để client nhận diện loại lỗi, đối chiếu lần xảy ra và tìm cách khôi phục.

Spring Framework hỗ trợ chuẩn **Problem Details for HTTP APIs – RFC 9457** qua các kiểu `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`. Chuẩn này định nghĩa một cấu trúc lỗi dùng chung cho nhiều API. Ứng dụng có thể mở rộng cấu trúc bằng các field riêng như mã lỗi, danh sách lỗi validation, correlation ID hoặc link phục hồi.

Bài học này tập trung vào cách thiết kế resource lỗi trong API Spring HATEOAS: hiểu các field của Problem Details, ánh xạ exception sang HTTP status, cấu hình `@ControllerAdvice`, bổ sung extension properties, công bố link phục hồi an toàn, xử lý lỗi ở client và kiểm thử hợp đồng lỗi.

## 1. Vì sao cần một resource lỗi có cấu trúc?

Giả sử client gọi `GET /api/orders/42`, nhưng đơn hàng không tồn tại. Nếu server chỉ trả:

~~~json
{
  "message": "Not found"
}
~~~

client không biết lỗi thuộc loại nào, có thể xử lý bằng cách nào, hoặc thông báo này có ổn định qua các phiên bản hay không. Một endpoint khác có thể trả `error`, endpoint thứ ba lại trả `description`. Client phải phụ thuộc vào nhiều cấu trúc riêng.

Với Problem Details, server trả một object có các field thống nhất:

~~~json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng được yêu cầu.",
  "instance": "urn:uuid:4f32e2b1-5b8c-4b8f-9f43-55f9f2c0f7d8",
  "code": "ORDER_NOT_FOUND",
  "traceId": "01J8K3M5Q7"
}
~~~

HTTP response đi kèm status `404 Not Found` và media type `application/problem+json`. Client có thể dùng `type` hoặc mã `code` để quyết định cách xử lý, còn `detail` giúp hiển thị thông báo phù hợp.

Problem Details tạo ra một vocabulary chung cho lỗi. Nó không thay thế HTTP status; status code vẫn là tín hiệu giao thức chính để client, proxy và cache xử lý response.

## 2. Các field chuẩn của RFC 9457

RFC 9457 định nghĩa năm field chuẩn. Các field này có thể xuất hiện tùy trường hợp; server không bắt buộc phải điền tất cả.

| Field | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `type` | URI định danh loại vấn đề | Dùng để phân biệt loại lỗi có semantics ổn định |
| `title` | Tóm tắt ngắn loại vấn đề | Thường ổn định theo `type`, có thể được bản địa hóa |
| `status` | HTTP status code được phản ánh trong body | Phải nhất quán với status của HTTP response |
| `detail` | Giải thích cụ thể cho lần xảy ra này | Hướng dẫn người dùng hoặc developer mà không lộ thông tin nội bộ |
| `instance` | URI reference nhận diện lần xảy ra vấn đề | Có thể là occurrence ID duy nhất, không nhất thiết là URL endpoint |

`type` mặc định có thể là `about:blank`, nghĩa là server không cung cấp loại vấn đề cụ thể ngoài HTTP status. Với lỗi nghiệp vụ quan trọng, nên dùng URI ổn định như `https://api.example.com/problems/order-state-conflict` và cung cấp tài liệu giải thích tại URI đó.

`title` mô tả loại lỗi, còn `detail` mô tả lần xảy ra cụ thể. Ví dụ `title` là “Trạng thái đơn hàng không hợp lệ”, còn `detail` là “Đơn hàng 42 đã được duyệt nên không thể hủy”.

`instance` không nên bị nhầm với `type`. `type` định danh một loại lỗi có thể xảy ra nhiều lần; `instance` định danh một occurrence cụ thể. Nếu cần truy vết, có thể tạo `urn:uuid:...` cho mỗi response lỗi.

## 3. Problem Details là media type riêng

Một response Problem Details thường dùng:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

`application/problem+json` là media type được định nghĩa cho JSON Problem Details. Nó giúp client nhận biết body là mô tả lỗi theo RFC 9457, thay vì JSON resource thông thường.

Ví dụ đầy đủ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Trạng thái đơn hàng không hợp lệ",
  "status": 409,
  "detail": "Đơn hàng đã được duyệt nên không thể hủy.",
  "instance": "urn:uuid:ca4c4db2-62d0-4db4-ae12-81e1d2b47e9c"
}
~~~

Spring MVC nhận biết `ProblemDetail` và ưu tiên media type `application/problem+json` khi chọn JSON converter. Nếu client gửi `Accept` không tương thích, content negotiation vẫn có thể ảnh hưởng tới response; hãy kiểm thử cả media type lỗi trong API.

Không đổi status HTTP thành `200 OK` chỉ vì body có mô tả lỗi. HTTP status phải phản ánh kết quả request, còn Problem Details cung cấp phần giải thích có cấu trúc.

## 4. Phân biệt lỗi giao thức và lỗi nghiệp vụ

HTTP status nên thể hiện loại kết quả ở mức giao thức. Một số status thường gặp:

| Status | Tình huống thường gặp | Ví dụ |
| --- | --- | --- |
| `400 Bad Request` | Request không đọc hoặc không kiểm tra được | JSON sai cú pháp, thiếu tham số bắt buộc |
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực | Token không hợp lệ hoặc đã hết hạn |
| `403 Forbidden` | Đã xác thực nhưng không được phép | Người dùng không có quyền duyệt đơn |
| `404 Not Found` | Không tìm thấy resource | Đơn hàng không tồn tại hoặc không được phép tiết lộ |
| `405 Method Not Allowed` | HTTP method không được hỗ trợ | Gọi `PUT` vào resource chỉ cho phép `GET` |
| `409 Conflict` | Xung đột với trạng thái hiện tại | Hủy đơn đã được giao |
| `412 Precondition Failed` | Điều kiện HTTP không thỏa mãn | `If-Match` không khớp ETag hiện tại |
| `415 Unsupported Media Type` | Request body dùng media type không hỗ trợ | Gửi XML tới endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Nội dung hợp lệ về cú pháp nhưng không thể xử lý theo semantics | Một tập field hợp lệ về kiểu nhưng vi phạm quy tắc nghiệp vụ |
| `429 Too Many Requests` | Client vượt giới hạn request | Gửi quá nhiều request trong một khoảng thời gian |
| `500 Internal Server Error` | Lỗi không dự kiến ở server | Null pointer hoặc lỗi hạ tầng không được xử lý |
| `503 Service Unavailable` | Server tạm thời không thể phục vụ | Dịch vụ phụ thuộc đang bảo trì |

Không dùng `400` cho mọi loại lỗi. Ví dụ, người dùng đã đăng nhập nhưng không có quyền nên nhận `403`; đơn hàng xung đột trạng thái nên nhận `409`; lỗi bất ngờ của server nên nhận `500`.

Một số response còn cần HTTP header đi kèm. `401` có thể cần `WWW-Authenticate`, `405` cần `Allow`, `429` hoặc `503` có thể cần `Retry-After`. Không bỏ các header này khi tự tạo body lỗi.

## 5. Tạo ProblemDetail trực tiếp

Spring Framework cung cấp `org.springframework.http.ProblemDetail`. Có thể tạo object bằng `forStatusAndDetail(...)`, sau đó thiết lập các field:

~~~java
import java.net.URI;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy đơn hàng được yêu cầu."
);

problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"
));
problem.setTitle("Không tìm thấy đơn hàng");
problem.setInstance(URI.create("urn:uuid:" + UUID.randomUUID()));
problem.setProperty("code", "ORDER_NOT_FOUND");
~~~

`forStatusAndDetail(...)` khởi tạo `status` và `detail`. `setType(...)`, `setTitle(...)` và `setInstance(...)` bổ sung thông tin cho client.

Trong controller hoặc exception handler, trả object này với status tương ứng:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

return ResponseEntity
        .status(problem.getStatus())
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
~~~

Spring Jackson hỗ trợ serialize `ProblemDetail` theo cấu trúc RFC 9457. Trong ứng dụng dùng Spring MVC với Jackson, body sẽ có các field chuẩn và extension properties ở cấp cao nhất.

## 6. Xử lý exception tập trung bằng @ControllerAdvice

Không nên tạo body lỗi riêng trong từng controller. `@ControllerAdvice` cho phép tập trung hóa cách chuyển exception thành response:

~~~java
import java.net.URI;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@ControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception,
            HttpServletRequest request
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng được yêu cầu."
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setInstance(URI.create(
                "urn:uuid:" + UUID.randomUUID()
        ));
        problem.setProperty("code", "ORDER_NOT_FOUND");
        problem.setProperty("requestPath", request.getRequestURI());

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Ví dụ giả định ứng dụng có `OrderNotFoundException`. Handler chuyển exception nghiệp vụ thành `404` và một problem type ổn định. `requestPath` là extension tùy chọn để hỗ trợ chẩn đoán; không dùng nó thay cho `instance`.

`detail` được viết cho client và người dùng, không nên lấy trực tiếp message exception nếu message đó có thể chứa SQL, tên bảng, đường dẫn file, token hoặc dữ liệu nội bộ.

Nếu có nhiều controller hoặc module, có thể chia nhỏ advice bằng `basePackages`, `basePackageClasses` hoặc `assignableTypes`, nhưng nên giữ một vocabulary lỗi thống nhất cho toàn API.

## 7. Dùng ResponseEntityExceptionHandler cho lỗi Spring MVC

Spring MVC có nhiều exception được tạo tự động: sai kiểu tham số, body không đọc được, method không hỗ trợ, validation thất bại hoặc media type không được hỗ trợ. `ResponseEntityExceptionHandler` là base class xử lý các exception MVC này bằng response RFC 9457. `ApiExceptionHandler` ở mục trước đã mở rộng class này, nên cùng một advice có thể xử lý exception domain bằng `@ExceptionHandler` và xử lý exception framework bằng các handler có sẵn.

Base class xử lý các exception Spring MVC và `ErrorResponseException`. Ứng dụng có thể override các method bảo vệ như `handleMethodArgumentNotValid(...)` để tùy chỉnh response. Nếu chỉ cần xử lý một số exception domain và không cần chuẩn hóa các exception MVC tích hợp sẵn, `@ControllerAdvice` thông thường cũng có thể trả `ProblemDetail` trực tiếp.

## 8. Bật Problem Details trong Spring Boot

Spring Boot có thể tự cấu hình xử lý Problem Details cho các exception Spring MVC có sẵn:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Khi bật thuộc tính này, Boot đăng ký một `ResponseEntityExceptionHandler` để trả lỗi framework theo RFC 9457. Điều này hữu ích khi muốn chuẩn hóa lỗi như method không hỗ trợ, body không đọc được hoặc validation.

Nếu cần tùy chỉnh một exception framework cụ thể, có thể tạo `@ControllerAdvice` riêng. Cần bảo đảm advice tùy chỉnh được ưu tiên trước handler tự động của Boot (handler mặc định có order `0`). Nếu tự cung cấp một bean `ResponseEntityExceptionHandler`, Boot sẽ không tạo handler mặc định tương ứng.

Không nên vừa bật auto-configuration vừa khai báo nhiều handler cùng bắt một exception mà không kiểm tra thứ tự. Hãy quyết định rõ một nơi chịu trách nhiệm xử lý từng loại exception.

## 9. Chuẩn hóa lỗi validation

Khi request body vi phạm Bean Validation, Spring MVC có thể ném `MethodArgumentNotValidException`. Nên trả một problem type chung, kèm danh sách field lỗi có cấu trúc:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.context.request.WebRequest;

@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException exception,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request
) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status,
            "Một hoặc nhiều trường dữ liệu không hợp lệ."
    );

    problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"
    ));
    problem.setTitle("Dữ liệu không hợp lệ");
    problem.setProperty("code", "VALIDATION_FAILED");

    List<Map<String, String>> errors =
            exception.getBindingResult().getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", error.getCode() == null
                                    ? "invalid"
                                    : error.getCode()
                    ))
                    .toList();

    problem.setProperty("errors", errors);

    return handleExceptionInternal(
            exception,
            problem,
            headers,
            status,
            request
    );
}
~~~

Đây là method override của `ResponseEntityExceptionHandler`. `handleExceptionInternal(...)` giữ cơ chế xử lý chung của Spring và dùng lại HTTP headers được cung cấp.

Một response validation có thể trông như sau:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường dữ liệu không hợp lệ.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "Email"
    },
    {
      "field": "quantity",
      "code": "Positive"
    }
  ]
}
~~~

Không đưa giá trị bị từ chối (`rejectedValue`) vào response một cách mặc định. Giá trị đó có thể là mật khẩu, token, dữ liệu cá nhân hoặc nội dung nhạy cảm. Nếu cần hiển thị giá trị đầu vào, hãy lọc theo field allowlist và chính sách bảo mật.

## 10. Mở rộng ProblemDetail bằng properties

RFC 9457 cho phép thêm extension members ngoài năm field chuẩn. Spring `ProblemDetail` cung cấp `setProperty(...)` và `getProperties()` để lưu các field đó:

~~~java
problem.setProperty("code", "ORDER_STATE_CONFLICT");
problem.setProperty("traceId", traceId);
problem.setProperty("retryable", false);
~~~

Với Jackson integration của Spring, map `properties` được serialize thành các field cấp cao nhất:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Trạng thái đơn hàng không hợp lệ",
  "status": 409,
  "detail": "Đơn hàng đã được duyệt nên không thể hủy.",
  "code": "ORDER_STATE_CONFLICT",
  "traceId": "01J8K3M5Q7",
  "retryable": false
}
~~~

Nên thiết kế extension có tên ổn định, kiểu dữ liệu rõ ràng và tài liệu hóa. Client không nên phụ thuộc vào một field debug tạm thời hoặc message tự do.

Một số extension thường hữu ích:

| Extension | Mục đích |
| --- | --- |
| `code` | Mã lỗi máy đọc được, ổn định qua ngôn ngữ |
| `traceId` | Liên kết response với log/tracing |
| `errors` | Danh sách lỗi validation |
| `retryable` | Gợi ý liệu client có thể thử lại theo policy |
| `links` | Các link phục hồi theo vocabulary do API định nghĩa |

`retryable` chỉ là gợi ý nghiệp vụ; client vẫn phải xem HTTP method, idempotency, `Retry-After` và chính sách retry. Không retry POST không idempotent chỉ vì extension này có giá trị `true`.

## 11. Gắn link phục hồi cho resource lỗi

API dùng hypermedia có thể giúp client phục hồi từ một số lỗi bằng cách công bố link tới resource liên quan. Ví dụ khi hủy đơn hàng thất bại do trạng thái đã thay đổi, problem có thể cung cấp link để đọc trạng thái hiện tại.

Problem Details không định nghĩa sẵn cấu trúc HAL `_links`. Có thể thêm một extension `links` theo vocabulary riêng của API:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

import java.net.URI;
import java.util.List;
import java.util.Map;

URI currentOrderUri = linkTo(OrderController.class)
        .slash(orderId)
        .toUri();

problem.setProperty("links", List.of(
        Map.of(
                "rel", "https://api.example.com/rels/current-order",
                "href", currentOrderUri.toString()
        )
));
~~~

Response có thể chứa:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Trạng thái đơn hàng không hợp lệ",
  "status": 409,
  "detail": "Đơn hàng đã được duyệt nên không thể hủy.",
  "links": [
    {
      "rel": "https://api.example.com/rels/current-order",
      "href": "https://api.example.com/api/orders/42"
    }
  ]
}
~~~

`links` ở ví dụ này là extension riêng của API, không phải HAL `_links` và không tự động được Spring HATEOAS serialize như một `RepresentationModel`. Server dùng `WebMvcLinkBuilder` để dựng target URI; client cần được tài liệu hóa cách đọc extension này.

Chỉ công bố link mà người gọi được phép truy cập. Lỗi `403` không nên vô tình tiết lộ link tới resource nhạy cảm; lỗi `404` cũng không nên đưa link xác nhận sự tồn tại của resource mà người dùng không được biết.

Không phải lỗi nào cũng cần link phục hồi. `400` do JSON sai cú pháp thường không có resource đích để điều hướng. `409` có thể có link tới trạng thái hiện tại; `401` có thể cần cơ chế xác thực; `429` cần `Retry-After` hơn là một link action.

## 12. Problem Details và HAL là hai hợp đồng khác nhau

Spring HATEOAS thường serialize resource thành HAL với cấu trúc `_links` và có thể có `_embedded`. Problem Details dùng media type `application/problem+json` với các field chuẩn như `type`, `title`, `status`, `detail` và `instance`.

| Đặc điểm | HAL resource | Problem Details |
| --- | --- | --- |
| Media type | `application/hal+json` | `application/problem+json` |
| Mục đích | Biểu diễn resource và quan hệ hypermedia | Mô tả một lần xảy ra lỗi HTTP |
| Link | `_links` theo HAL | Không định nghĩa sẵn; có thể thêm extension |
| Embedded resource | `_embedded` | Không có field chuẩn tương đương |
| Nhận diện loại | Media type và relation/profile | `type` URI |

Không nên đổi body Problem Details thành HAL chỉ để có `_links` nếu client đã dựa vào RFC 9457. Nếu muốn error representation dạng HAL riêng, cần định nghĩa rõ media type và hợp đồng riêng, đồng thời hỗ trợ content negotiation. Trong phần lớn API, giữ Problem Details làm định dạng lỗi chuẩn và thêm extension links khi cần sẽ đơn giản hơn.

## 13. Không để lộ thông tin nội bộ trong lỗi

Error response là dữ liệu gửi ra ngoài ranh giới server. Không đưa các thông tin sau vào `detail`, extension hoặc link:

- Stack trace, tên class nội bộ hoặc câu lệnh SQL.
- Đường dẫn file, hostname nội bộ, tên container hoặc topology hạ tầng.
- Access token, session ID, API key hoặc secret.
- Giá trị mật khẩu và dữ liệu nhạy cảm bị validation từ chối.
- Thông tin xác thực hoặc quyền của người dùng khác.
- Message exception chưa được kiểm tra từ thư viện hoặc database.

Với lỗi `500`, client nên nhận thông báo tổng quát cùng `traceId`. Log phía server có thể lưu exception và stack trace để điều tra, liên kết bằng cùng correlation ID. Không gửi stack trace cho client ở production.

Với lỗi `404` hoặc `403`, cân nhắc chính sách che giấu sự tồn tại của resource. Cùng một endpoint không nên trả nội dung khác nhau theo cách vô tình tiết lộ ID hợp lệ, owner hoặc tenant.

## 14. Bản địa hóa title và detail

`title` và `detail` dành cho con người nên có thể được bản địa hóa. Spring `ErrorResponse` hỗ trợ message codes, còn `ResponseEntityExceptionHandler` có thể dùng `MessageSource` để phân giải nội dung.

Mã lỗi máy đọc được như `ORDER_NOT_FOUND` nên giữ ổn định giữa các ngôn ngữ. Client nên dựa vào `type` hoặc `code` để quyết định logic; không so sánh chuỗi `detail` đã được dịch.

Ví dụ một bộ message properties:

~~~properties
problemDetail.title.com.example.OrderNotFoundException=Không tìm thấy đơn hàng
problemDetail.com.example.OrderNotFoundException=Không tìm thấy đơn hàng được yêu cầu.
~~~

Tên message code cụ thể phụ thuộc exception class và cấu hình của ứng dụng. Với custom exception, có thể triển khai `ErrorResponse` hoặc cung cấp `MessageSource` entries tương ứng.

Không dịch `type` URI hoặc machine code theo ngôn ngữ. Những giá trị đó là định danh của hợp đồng API.

## 15. Client xử lý Problem Details

Client nên đọc `Content-Type` và HTTP status trước, sau đó parse body nếu media type là `application/problem+json`. Logic nghiệp vụ nên dựa vào `type` hoặc `code`, không phụ thuộc `detail`.

Với Spring `RestClient`, có thể đọc body lỗi thành `ProblemDetail` từ `RestClientResponseException`:

~~~java
import org.springframework.http.ProblemDetail;
import org.springframework.web.client.RestClientResponseException;

try {
    return restClient.get()
            .uri(orderUri)
            .retrieve()
            .body(OrderDto.class);
} catch (RestClientResponseException exception) {
    ProblemDetail problem =
            exception.getResponseBodyAs(ProblemDetail.class);

    if (problem != null
            && "https://api.example.com/problems/order-state-conflict"
                    .equals(problem.getType().toString())) {
        // Làm mới trạng thái resource trước khi cho người dùng thử lại.
    }

    throw exception;
}
~~~

Trong ứng dụng thực tế, cần xử lý trường hợp response body rỗng, không phải Problem Details hoặc không giải mã được. Không giả định mọi proxy hay dịch vụ trung gian đều trả đúng media type.

Client không nên retry mọi `5xx` hoặc `409` một cách mù quáng. Hãy xem status, `type`, `Retry-After`, tính idempotent của method và trạng thái nghiệp vụ.

## 16. Kiểm thử error representation bằng MockMvc

Kiểm thử nên xác nhận cả HTTP status, media type và các field quan trọng trong body:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(ApiExceptionHandler.class)
class OrderErrorRepresentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsProblemDetailsWhenOrderDoesNotExist() throws Exception {
        when(orderService.getOrder(42L))
                .thenThrow(new OrderNotFoundException(42L));

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON
                ))
                .andExpect(jsonPath("$.type").value(
                        "https://api.example.com/problems/order-not-found"
                ))
                .andExpect(jsonPath("$.title").value("Không tìm thấy đơn hàng"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.instance").exists());
    }
}
~~~

Test giả định `OrderController`, `OrderService`, `OrderNotFoundException` và `ApiExceptionHandler` đã được cấu hình trong test context. Có thể import advice rõ ràng bằng `@Import(ApiExceptionHandler.class)` nếu slice test không tự quét được bean đó.

Ngoài trường hợp not found, nên có test cho:

- Validation trả đúng problem type và danh sách lỗi.
- JSON sai cú pháp trả `400` với body Problem Details.
- Method không hỗ trợ giữ status `405` và header `Allow`.
- Request không xác thực giữ `401` và header `WWW-Authenticate` khi cần.
- Lỗi quyền truy cập trả `403` mà không lộ resource nhạy cảm.
- Lỗi bất ngờ trả `500` với thông báo tổng quát và trace ID, không có stack trace.
- `409` có link phục hồi khi có thể và link đó không vượt quyền.
- `Accept` không tương thích được xử lý đúng theo content negotiation.

## 17. Những lỗi thường gặp

**Trả lỗi với status `200 OK`.** Body có field `error` không biến response thành lỗi HTTP. Hãy dùng status phù hợp.

**Dùng một JSON schema khác nhau ở mỗi controller.** Chuẩn hóa bằng Problem Details và advice dùng chung.

**Dùng `detail` làm mã lỗi.** `detail` có thể thay đổi hoặc được dịch. Dùng `type` và extension `code` ổn định.

**Đặt `instance` bằng type URI.** `type` định danh loại vấn đề; `instance` định danh lần xảy ra cụ thể.

**Đưa exception message thô ra client.** Chuyển sang thông báo an toàn và lưu chi tiết ở log server.

**Để HTTP status khác field `status`.** Giữ hai giá trị nhất quán.

**Mất các header HTTP quan trọng.** Giữ `WWW-Authenticate`, `Allow`, `Retry-After` và các header do exception cung cấp.

**Dùng `_links` rồi gọi đó là HAL dù response là Problem Details.** Nếu thêm link, tài liệu hóa rõ extension riêng hoặc định nghĩa một media type khác.

**Công bố link phục hồi mà client không có quyền truy cập.** Áp dụng authorization trước khi thêm link và kiểm tra lại quyền khi client theo link.

**Đưa giá trị nhạy cảm vào lỗi validation.** Chỉ trả field và mã lỗi an toàn; không phản chiếu mật khẩu hoặc rejected value.

**Retry request không an toàn dựa trên một flag tùy chỉnh.** Kiểm tra HTTP method, idempotency, status và `Retry-After`.

## 18. Ghi nhớ

Resource lỗi trong REST API nên có hợp đồng ổn định. RFC 9457 cung cấp các field `type`, `title`, `status`, `detail` và `instance`, cùng khả năng mở rộng bằng extension members. Spring Framework hiện thực chuẩn này qua `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`; Spring Boot có thể bật xử lý lỗi MVC tự động bằng `spring.mvc.problemdetails.enabled`.

Trong API Spring HATEOAS, error representation có thể cung cấp link phục hồi như một extension có tài liệu riêng. Link không thay thế HTTP status hoặc authorization. Giữ `application/problem+json` cho Problem Details, không nhầm extension links với HAL `_links`, và chỉ công bố target mà client được phép truy cập.

Kiểm thử cả status, media type, body, headers và khả năng bảo mật của error response. Client nên dùng `type` hoặc machine code để xử lý, còn `detail` để hiển thị cho con người. Cách làm này giúp client cũ và mới xử lý lỗi nhất quán khi API phát triển.

## Tài liệu tham khảo

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework Reference – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework API – ProblemDetail](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework API – ErrorResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework API – ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot Reference – Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring HATEOAS Reference – Link building](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
