# Tài liệu lỗi

Một REST API cần mô tả cả response thành công lẫn response lỗi. Với API dùng Spring HATEOAS, client thường khám phá resource và hành động qua link; khi request thất bại, client vẫn cần một hợp đồng ổn định để hiểu lỗi, hiển thị thông báo phù hợp và quyết định bước tiếp theo.

Hợp đồng lỗi tốt phải tách **HTTP status**, **loại lỗi**, **thông tin của lần xảy ra cụ thể** và **hướng xử lý**. RFC 9457 định nghĩa Problem Details for HTTP APIs với media type application/problem+json. Spring Framework cung cấp ProblemDetail, ErrorResponse và ResponseEntityExceptionHandler để xây dựng response theo định dạng này.

Trong API hypermedia, thuộc tính type của Problem Details là URI nhận diện loại lỗi và có thể dẫn tới tài liệu mô tả lỗi. Có thể bổ sung link help bằng HTTP Link header nếu client cần điều hướng tới hướng dẫn. Response lỗi vẫn phải giữ HTTP status chính xác và không tiết lộ chi tiết nội bộ.

## Vì sao API cần tài liệu lỗi?

Nếu server chỉ trả một chuỗi như Something went wrong, client không thể phân biệt lỗi xác thực, dữ liệu không hợp lệ, trạng thái xung đột hay sự cố tạm thời. Client có thể retry một request không thể thành công, hoặc bỏ qua lỗi tạm thời có thể phục hồi.

Tài liệu lỗi giúp:

- Client phân loại lỗi bằng mã và loại lỗi ổn định.
- Người dùng nhận được thông báo có ý nghĩa.
- Client biết khi nào cần đăng nhập lại, sửa dữ liệu hoặc tải lại resource.
- Hệ thống hỗ trợ có thể tra cứu tài liệu từ một URI ổn định.
- Team API giữ cách biểu diễn lỗi nhất quán giữa controller.
- Test và monitoring có thể nhóm lỗi theo loại thay vì phân tích chuỗi message.

Không nên tạo một loại lỗi riêng cho mọi câu chữ hoặc mọi bản ghi. Hãy tạo loại lỗi theo ngữ nghĩa nghiệp vụ có thể được client xử lý khác nhau.

## Problem Details theo RFC 9457

RFC 9457 thay thế RFC 7807 và chuẩn hóa một object JSON mô tả lỗi HTTP. Các thành viên chuẩn gồm:

| Member | Ý nghĩa |
| --- | --- |
| type | URI định danh loại lỗi; nếu vắng mặt thì mặc định là about:blank |
| title | Tóm tắt ngắn gọn, ổn định cho loại lỗi |
| status | HTTP status của lần xảy ra lỗi; chỉ mang tính thông tin, status trong HTTP response mới là giá trị có thẩm quyền |
| detail | Giải thích cụ thể cho lần xảy ra này, hướng tới client/người dùng |
| instance | URI reference nhận diện lần xảy ra lỗi cụ thể |

Ví dụ:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Đơn hàng được yêu cầu không tồn tại hoặc không khả dụng.",
  "instance": "/orders/8d8c5c7b-2a5e-4f7e-a8e2-0c1d2e3f4a5b",
  "code": "ORDER_NOT_FOUND",
  "traceId": "01J8Q2D9G4M7K3"
}
~~~

code và traceId là extension members do API định nghĩa. RFC 9457 cho phép mở rộng object bằng các member bổ sung. Client nên dựa vào type hoặc code ổn định để xử lý; không nên phân tích detail vì nội dung này có thể thay đổi hoặc được bản địa hóa.

status trong body không thay thế HTTP status line. Nếu body ghi 404 nhưng response thực tế là 200, client và intermediary sẽ xử lý theo 200; server phải bảo đảm hai giá trị nhất quán.

## Chọn type URI ổn định

Mỗi loại lỗi có một URI nhận diện. URI này nên có thể truy cập được và trỏ tới trang tài liệu giải thích lỗi:

| Type URI | Code | HTTP status | Ý nghĩa |
| --- | --- | --- | --- |
| /problems/order-not-found | ORDER_NOT_FOUND | 404 | Không tìm thấy đơn hàng hoặc resource không khả dụng |
| /problems/order-state-conflict | ORDER_STATE_CONFLICT | 409 | Trạng thái hiện tại không cho phép thao tác |
| /problems/validation-error | VALIDATION_FAILED | 400 hoặc 422 theo hợp đồng | Một hay nhiều trường không hợp lệ |
| /problems/insufficient-scope | INSUFFICIENT_SCOPE | 403 | Principal đã xác thực nhưng thiếu quyền |
| /problems/rate-limit-exceeded | RATE_LIMIT_EXCEEDED | 429 | Client gửi request vượt giới hạn |

Trong response thực tế, dùng URI tuyệt đối:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Không thể thực hiện thao tác ở trạng thái hiện tại",
  "status": 409,
  "detail": "Đơn hàng đã được giao nên không thể hủy.",
  "code": "ORDER_STATE_CONFLICT"
}
~~~

Giữ type ổn định qua các lần triển khai. Nếu nội dung hướng dẫn được cập nhật, URI vẫn có thể trỏ tới tài liệu mới. Chỉ tạo type mới khi ngữ nghĩa lỗi thay đổi đến mức client cần xử lý khác. Không nhúng ID bản ghi, timestamp hoặc message cụ thể vào type.

about:blank phù hợp khi server chỉ muốn dùng ý nghĩa mặc định của HTTP status mà không định nghĩa một loại lỗi riêng. Khi API cần hướng dẫn cụ thể, hãy cấp một type URI riêng.

## Tách loại lỗi khỏi lần xảy ra lỗi

type và title mô tả loại lỗi chung. detail và instance mô tả lần xảy ra cụ thể.

- type: một URI ổn định, ví dụ https://api.example.com/problems/order-state-conflict.
- title: tiêu đề chung, ví dụ Không thể thực hiện thao tác ở trạng thái hiện tại.
- detail: giải thích an toàn cho request cụ thể, ví dụ đơn hàng đã được giao.
- instance: định danh lần xảy ra, có thể là URI request hoặc URI occurrence riêng.
- traceId: mã tương quan để tra log, do hệ thống định nghĩa.

Không đưa stack trace, câu SQL, tên bảng, đường dẫn file, host nội bộ, access token hoặc thông tin xác thực vào detail. Nếu cần điều tra, trả traceId để đội vận hành tìm log có kiểm soát.

Không dùng instance như nơi chứa stack trace hay message. Nó là định danh occurrence, không phải phần mô tả lỗi.

## Phân loại HTTP status và cách client xử lý

Status phải phản ánh bản chất lỗi ở tầng HTTP. Một bảng quy ước giúp server và client thống nhất:

| Status | Trường hợp thường gặp | Hướng xử lý phía client |
| --- | --- | --- |
| 400 Bad Request | JSON sai cú pháp, tham số hoặc cấu trúc request không hợp lệ | Sửa request theo tài liệu |
| 401 Unauthorized | Thiếu token, token hết hạn hoặc không hợp lệ | Xác thực lại; kiểm tra WWW-Authenticate |
| 403 Forbidden | Đã xác thực nhưng thiếu quyền hoặc scope | Không retry cùng credential; yêu cầu quyền phù hợp |
| 404 Not Found | Resource không tồn tại hoặc được che giấu theo chính sách | Kiểm tra URI hoặc quay lại collection |
| 409 Conflict | Trạng thái resource xung đột với hành động | Tải lại resource và khám phá link hiện tại |
| 412 Precondition Failed | Điều kiện như If-Match không còn đúng | Tải representation mới rồi quyết định lại |
| 422 Unprocessable Content | Nội dung đúng cú pháp nhưng không đáp ứng quy tắc nghiệp vụ | Hiển thị lỗi trường hoặc yêu cầu sửa dữ liệu |
| 429 Too Many Requests | Vượt rate limit | Chờ theo Retry-After nếu được cung cấp |
| 500 Internal Server Error | Lỗi không dự kiến ở server | Không lặp vô hạn; retry có giới hạn nếu thao tác an toàn |
| 503 Service Unavailable | Server hoặc dependency tạm thời không sẵn sàng | Tôn trọng Retry-After, retry có backoff nếu phù hợp |

401 và 403 không đồng nghĩa: 401 là vấn đề xác thực, 403 là principal đã được xác thực nhưng không được phép thực hiện thao tác. 409 thường mô tả xung đột trạng thái nghiệp vụ; 412 mô tả điều kiện HTTP mà client đã gửi không còn đúng.

Chọn 400 hay 422 cho validation theo hợp đồng API và giữ nhất quán. 400 thường dùng cho request không hợp lệ nói chung; 422 phù hợp khi server hiểu cú pháp và nội dung nhưng không thể xử lý chỉ vì lỗi ngữ nghĩa hoặc quy tắc nghiệp vụ.

## Spring ProblemDetail

Spring Framework cung cấp ProblemDetail trong package org.springframework.http. Jackson tích hợp với Spring có thể serialize các member chuẩn và extension properties thành JSON.

Ví dụ tạo Problem Details cho đơn hàng không tồn tại:

~~~java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Đơn hàng được yêu cầu không tồn tại hoặc không khả dụng."
        );

        problem.setType(URI.create(
            "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .header(
                HttpHeaders.LINK,
                "<https://api.example.com/problems/order-not-found>; rel=\"help\""
            )
            .body(problem);
    }
}
~~~

ProblemDetail giữ các member chuẩn; setProperty thêm extension như code. Ví dụ cũng thêm HTTP Link header với relation help, trỏ tới tài liệu loại lỗi. Client có thể dùng type làm định danh máy đọc và Link header để khám phá trang hướng dẫn.

HTTP Link header là một link theo Web Linking; response application/problem+json không tự trở thành HAL. Nếu API muốn đặt _links trong body Problem Details, đó là extension riêng và cần được tài liệu hóa rõ ràng. Không giả định mọi HAL client có thể xử lý nó như một HAL document.

## Ánh xạ exception nghiệp vụ

Exception nghiệp vụ nên được chuyển thành loại lỗi có ngữ nghĩa ổn định. Ví dụ xung đột trạng thái:

~~~java
@ExceptionHandler(OrderStateConflictException.class)
ResponseEntity<ProblemDetail> handleOrderStateConflict(
        OrderStateConflictException exception,
        HttpServletRequest request) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Đơn hàng đã thay đổi và không thể thực hiện thao tác này."
    );

    problem.setType(URI.create(
        "https://api.example.com/problems/order-state-conflict"));
    problem.setTitle("Xung đột trạng thái đơn hàng");
    problem.setInstance(URI.create(request.getRequestURI()));
    problem.setProperty("code", "ORDER_STATE_CONFLICT");

    return ResponseEntity.status(HttpStatus.CONFLICT)
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
~~~

detail nên nói đủ để client hiểu bước tiếp theo nhưng không tiết lộ thông tin nội bộ. Nếu API muốn client tải lại đơn hàng, có thể mô tả hành động đó trong trang tài liệu lỗi hoặc cung cấp URI resource hiện tại dưới dạng extension đã được định nghĩa. Không đưa một link retry chung nếu request lặp lại chắc chắn vẫn thất bại.

Với exception có thể xảy ra ở nhiều controller, giữ mapping trong một @RestControllerAdvice dùng chung thay vì lặp logic trong từng endpoint.

## Xử lý lỗi validation

Lỗi validation thường cần chỉ ra trường nào sai. RFC 9457 cho phép extension members; API có thể định nghĩa errors là danh sách vi phạm:

~~~json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường cần được kiểm tra lại.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "Min"
    },
    {
      "field": "shippingAddress.postalCode",
      "code": "Pattern"
    }
  ]
}
~~~

Giữ errors là một extension có schema ổn định. field xác định đường dẫn trường trong request; code là mã validation máy đọc. Nếu cần message bản địa hóa, có thể thêm message nhưng client không nên dựa vào câu chữ đó để rẽ nhánh logic.

Ví dụ tùy chỉnh ResponseEntityExceptionHandler trong Spring MVC:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class ValidationProblemHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Map<String, String>> errors =
            exception.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of(
                    "field", error.getField(),
                    "code", Objects.requireNonNullElse(
                        error.getCode(), "invalid")
                ))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status,
            "Một hoặc nhiều trường cần được kiểm tra lại."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/validation-error"));
        problem.setTitle("Dữ liệu không hợp lệ");
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("errors", errors);

        headers.setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        return handleExceptionInternal(
            exception, problem, headers, status, request);
    }
}
~~~

Đoạn code minh họa xử lý MethodArgumentNotValidException từ Bean Validation trên request body. Các loại validation khác như constraint trên method parameter hoặc lỗi binding có thể phát sinh exception khác; hãy xác định rõ phạm vi và override/handle tương ứng nếu API muốn cùng một schema.

ResponseEntityExceptionHandler đã xử lý nhiều exception chuẩn của Spring MVC. Override method phù hợp giúp giữ nguyên cơ chế xử lý header và status của framework trong khi tùy chỉnh body.

## Bật Problem Details trong Spring Boot

Với Spring Boot MVC, có thể bật hỗ trợ Problem Details tự động cho một số lỗi framework bằng cấu hình:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Tính năng này giúp các exception MVC được xử lý theo định dạng Problem Details. Exception nghiệp vụ riêng vẫn cần mapping phù hợp để có type, code, detail và extension theo hợp đồng API. Nếu đã có @ControllerAdvice tùy chỉnh, cần kiểm tra thứ tự xử lý và tránh hai handler cạnh tranh cho cùng exception.

Nếu ứng dụng tự xây response lỗi, hãy luôn trả đúng Content-Type: application/problem+json và HTTP status tương ứng. Không serialize ProblemDetail thành application/hal+json chỉ vì endpoint bình thường trả HAL.

## ErrorResponse và ErrorResponseException

Spring Framework có ErrorResponse để biểu diễn lỗi HTTP cùng ProblemDetail và HTTP headers. Nhiều exception framework triển khai interface này. ResponseEntityExceptionHandler dùng cơ chế đó để chuyển lỗi framework thành response.

Với exception nghiệp vụ, ErrorResponseException là một lựa chọn khi muốn exception mang theo status, headers và ProblemDetail:

~~~java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;

class OrderNotFoundException extends ErrorResponseException {

    OrderNotFoundException() {
        super(
            HttpStatus.NOT_FOUND,
            createProblem(),
            null
        );
    }

    private static ProblemDetail createProblem() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Đơn hàng được yêu cầu không tồn tại hoặc không khả dụng."
        );
        problem.setType(URI.create(
            "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return problem;
    }
}
~~~

Khi dùng ErrorResponseException, Spring MVC có thể xử lý nó thông qua ErrorResponse infrastructure. Nếu cần bổ sung instance, trace ID hoặc Link header theo request, có thể tùy chỉnh handler hoặc dùng @ExceptionHandler riêng như ví dụ trước. Chọn một cơ chế mapping nhất quán để không vô tình serialize cùng lỗi theo hai schema khác nhau.

Hai ví dụ OrderNotFoundException ở trên minh họa hai lựa chọn thay thế. Nếu exception kế thừa ErrorResponseException, không cần giữ thêm handler riêng cho cùng exception trừ khi muốn chủ động ghi đè cách framework tạo response.

## Tài liệu lỗi có thể khám phá qua hypermedia

Trong response lỗi, type là điểm bắt đầu chuẩn để client tìm tài liệu. Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Xung đột trạng thái đơn hàng",
  "status": 409,
  "detail": "Đơn hàng đã được giao nên không thể hủy.",
  "code": "ORDER_STATE_CONFLICT"
}
~~~

Tài liệu tại URI type nên mô tả:

- Ý nghĩa và phạm vi của lỗi.
- Những điều kiện thường làm lỗi xuất hiện.
- HTTP status và code được trả về.
- Các extension members và kiểu dữ liệu.
- Việc client nên làm tiếp theo.
- Có nên retry hay cần tải lại resource.
- Ví dụ response hoàn chỉnh.

Nếu muốn cung cấp link trợ giúp trực tiếp trong response, HTTP Link header có thể dùng relation help:

~~~http
Link: <https://api.example.com/problems/order-state-conflict>; rel="help"
~~~

type và relation help có thể trỏ cùng một trang. type thuộc Problem Details body và định danh loại lỗi; help là link HTTP tùy chọn giúp client khám phá tài liệu. Client không nên phụ thuộc vào help nếu hợp đồng đã quy định type là nguồn tài liệu chuẩn.

Không quảng bá link thực hiện hành động bị từ chối như thể nó chắc chắn khả dụng. Ví dụ response 403 không nên chứa link approve nếu principal hiện tại thiếu quyền duyệt. Nếu client cần biết hành động hợp lệ, hãy tải representation của resource sau khi xác thực hoặc cấp quyền phù hợp.

## Mẫu nội dung cho trang tài liệu từng lỗi

Một trang tài liệu cho type URI nên có cấu trúc dễ tra cứu:

| Mục | Nội dung |
| --- | --- |
| Tên lỗi | Tiêu đề ngắn, ổn định |
| Type URI | URI định danh chính thức |
| HTTP status | Status được trả về |
| Code | Mã máy đọc, ví dụ ORDER_STATE_CONFLICT |
| Điều kiện | Khi nào server phát sinh lỗi |
| Nguyên nhân phổ biến | Trạng thái, quyền hoặc dữ liệu khiến request thất bại |
| Cách xử lý | Sửa request, tải lại resource, đăng nhập hoặc liên hệ hỗ trợ |
| Retry | Có thể retry không, cần chờ bao lâu và điều kiện nào phải thay đổi |
| Extensions | Schema các trường bổ sung trong Problem Details |
| Ví dụ | Request và response minh họa |

Trang tài liệu type URI nên được giữ ổn định và có thể truy cập độc lập với phiên đăng nhập API nếu nội dung không nhạy cảm. Không yêu cầu client phải gọi API nghiệp vụ để đọc tài liệu lỗi.

## Mô tả response lỗi trong OpenAPI

OpenAPI cần khai báo các response lỗi có thể xảy ra, media type application/problem+json, schema và ví dụ. Có thể định nghĩa schema dùng chung:

~~~yaml
components:
  schemas:
    Problem:
      type: object
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
        code:
          type: string
        traceId:
          type: string
        errors:
          type: array
          items:
            type: object
            properties:
              field:
                type: string
              code:
                type: string
~~~

Khai báo response cho endpoint hủy đơn:

~~~yaml
paths:
  /orders/{id}/cancellation:
    post:
      responses:
        "204":
          description: Đơn hàng đã được hủy
        "401":
          description: Chưa xác thực hoặc token không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "403":
          description: Principal không có quyền hủy đơn
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "404":
          description: Không tìm thấy đơn hàng
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "409":
          description: Trạng thái đơn hàng không cho phép hủy
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
~~~

Schema có thể khai báo thêm extension riêng cho validation hoặc rate limit. Đừng đánh dấu mọi member là bắt buộc nếu API không bảo đảm luôn cung cấp chúng; các member chuẩn của Problem Details có thể vắng mặt theo RFC. Với từng response, cung cấp ví dụ type, title, status và code cụ thể để client hiểu được loại lỗi.

## Retry và hướng phục hồi

Tài liệu lỗi nên nói rõ client cần retry hay thay đổi request:

| Lỗi | Có nên retry ngay? | Hành động phù hợp |
| --- | --- | --- |
| 400 / 422 | Không | Sửa dữ liệu hoặc cấu trúc request |
| 401 | Không với token cũ | Làm mới credential hoặc đăng nhập lại |
| 403 | Không với cùng quyền | Yêu cầu quyền; không lặp request vô ích |
| 404 | Thường không | Kiểm tra URI hoặc quay về collection |
| 409 | Không trước khi làm mới state | GET resource, đọc link hiện tại rồi quyết định |
| 412 | Không với validator cũ | Tải representation mới và gửi precondition mới |
| 429 | Có thể sau thời gian chờ | Tôn trọng Retry-After và giới hạn retry |
| 500 / 503 | Có thể có điều kiện | Backoff, jitter, giới hạn số lần và chỉ retry thao tác an toàn |

Không retry POST thay đổi trạng thái một cách mù quáng. Nếu API hỗ trợ Idempotency-Key, tài liệu phải giải thích phạm vi key, thời gian lưu và cách server xử lý request lặp. Retry phải xét idempotency của method, trạng thái nghiệp vụ và khả năng request trước đã được xử lý dù response bị mất.

Với 409 trong API HATEOAS, client thường nên tải lại resource rồi khám phá các link được công bố theo trạng thái mới. Link cũ trong cache không bảo đảm hành động vẫn khả dụng.

## Bảo mật khi trả lỗi

Response lỗi là một bề mặt có thể làm lộ dữ liệu. Hãy áp dụng các quy tắc:

- Không trả stack trace hoặc exception class cho client.
- Không đưa SQL, schema database, đường dẫn nội bộ hoặc hostname private vào detail.
- Không phản hồi giá trị bí mật, token, cookie hoặc nội dung nhạy cảm của request.
- Không tiết lộ resource có tồn tại hay không nếu chính sách yêu cầu che giấu; có thể dùng 404 nhất quán.
- Không đưa dữ liệu người dùng khác vào validation errors.
- Dùng trace ID ngẫu nhiên hoặc mã tương quan không chứa thông tin cá nhân.
- Ghi chi tiết kỹ thuật ở log có kiểm soát, gắn với trace ID và áp dụng retention phù hợp.

Thông báo cần đủ hữu ích để client hành động nhưng không cung cấp thêm dữ liệu cho người gọi trái phép. Với lỗi xác thực, giữ header WWW-Authenticate cần thiết theo cơ chế bảo mật.

## Kiểm thử hợp đồng Problem Details

MockMvc có thể xác nhận status, media type và các member quan trọng:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(ApiProblemHandler.class)
class OrderProblemTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsDocumentedProblemWhenOrderDoesNotExist()
            throws Exception {

        mockMvc.perform(get("/orders/{id}", UNKNOWN_ORDER_ID)
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                "https://api.example.com/problems/order-not-found"))
            .andExpect(jsonPath("$.title").value(
                "Không tìm thấy đơn hàng"))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }
}
~~~

Test cần cấu hình mock cho các dependency của OrderController và dùng ID không tồn tại theo dữ liệu test. UNKNOWN_ORDER_ID là hằng của test suite. Nếu handler bổ sung Link: ...; rel="help", có thể xác nhận thêm header().string(HttpHeaders.LINK, containsString("rel=\"help\"")).

Kiểm thử validation:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import org.springframework.http.MediaType;

mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_PROBLEM_JSON)
        .content("""
            {
              "quantity": 0
            }
            """))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.type").value(
        "https://api.example.com/problems/validation-error"))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.errors[0].field").value("quantity"));
~~~

Ngoài body, hãy kiểm tra:

- HTTP status line khớp member status.
- Content-Type là application/problem+json.
- type và code ổn định giữa các lần chạy.
- 401 giữ WWW-Authenticate khi cần.
- 429/503 giữ Retry-After nếu server công bố.
- 500 không làm lộ stack trace hoặc thông tin nội bộ.
- Client có gửi Accept cho application/problem+json hoặc server công bố rõ cách xử lý khi Accept chỉ nêu media type thành công.

## Các lỗi thường gặp khi tài liệu hóa lỗi

- Chỉ trả message tự do: client không thể phân loại ổn định.
- Dùng một type cho nhiều ngữ nghĩa: client không biết cần sửa dữ liệu hay tải lại resource.
- Đưa chi tiết nội bộ vào detail: có thể làm lộ cấu trúc hệ thống.
- Không đồng bộ HTTP status và body status: client, proxy và log có thể hiểu khác nhau.
- Dùng detail làm mã lỗi: câu chữ thay đổi hoặc bản địa hóa sẽ phá logic client.
- Nhầm 401 với 403: khiến client refresh token hoặc yêu cầu quyền sai cách.
- Coi application/problem+json là HAL: hai media type có hợp đồng khác nhau.
- Thêm _links tùy ý mà không mô tả: client không biết extension đó có ngữ nghĩa gì.
- Không công bố retry semantics: client retry vô hạn hoặc bỏ lỡ lỗi tạm thời.
- Tạo type URI không ổn định: client lưu logic theo URI thay đổi qua từng release.
- Không mô tả lỗi trong OpenAPI: người tích hợp chỉ biết response thành công.
- Cho rằng link cũ vẫn có hiệu lực: endpoint vẫn phải kiểm tra quyền và trạng thái khi nhận request.

## Checklist cho tài liệu lỗi

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| HTTP status | Status có phản ánh đúng lỗi HTTP không? |
| Media type | Response có dùng application/problem+json không? |
| Type URI | Type có ổn định và có trang tài liệu không? |
| Title/detail | Title có ổn định; detail có an toàn và hữu ích không? |
| Extensions | Code, errors, traceId có schema được công bố không? |
| HATEOAS | Có type URI hoặc help link để khám phá tài liệu không? |
| Retry | Client biết khi nào retry, chờ bao lâu hoặc tải lại resource không? |
| Security | Response có tránh tiết lộ stack trace và dữ liệu nhạy cảm không? |
| OpenAPI | Từng endpoint đã khai báo các response lỗi có thể xảy ra chưa? |
| Tests | Status, media type, type, code và extensions đã được kiểm thử chưa? |

Tài liệu lỗi là một phần của hợp đồng REST API. Dùng RFC 9457 Problem Details để biểu diễn lỗi nhất quán, dùng type URI làm định danh ổn định và điểm đến của tài liệu, còn code cùng extension members để cung cấp dữ liệu máy đọc. Trong Spring, ProblemDetail, @RestControllerAdvice và ResponseEntityExceptionHandler giúp triển khai hợp đồng này. Với Spring HATEOAS, hãy giúp client khám phá hướng dẫn lỗi qua type URI hoặc help link, nhưng luôn giữ HTTP status chính xác, bảo vệ thông tin nội bộ và kiểm tra lại quyền/trạng thái ở endpoint.

## Tài liệu tham khảo

- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [Spring Framework – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework API – ProblemDetail](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework API – ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot – Error Handling](https://docs.spring.io/spring-boot/reference/web/servlet.html)
