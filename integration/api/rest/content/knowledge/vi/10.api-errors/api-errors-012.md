# Thống nhất lỗi từ ứng dụng, security filter và gateway

## 1. Mục tiêu bài học

Trong module **INTEGRATION_API_REST**, người học thiết kế REST API theo **resource, URI, phương thức, mã trạng thái HTTP và hợp đồng dữ liệu rõ ràng**, sau đó áp dụng xác thực, phân quyền, xử lý lỗi, OpenAPI và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Chương **Lỗi API** này giải quyết một vấn đề thường xảy ra khi API đi vào production: lỗi có thể sinh ra ở **nhiều tầng** nhưng client chỉ nên học **một hợp đồng lỗi nhất quán**.

Giả sử API quản lý đơn hàng chạy sau API gateway và dùng Spring Security. Ba yêu cầu sau đều thất bại nhưng xuất phát từ các nơi khác nhau:

- Payload tạo đơn có số lượng âm: **application/controller/validation** phát hiện.
- Bearer token không hợp lệ: **Spring Security filter** từ chối trước khi controller chạy.
- Upstream quá thời gian trả lời: **gateway** tự tạo phản hồi lỗi khi chưa nhận phản hồi ứng dụng.

Nếu tầng ứng dụng trả JSON có **code**, security filter trả chuỗi rỗng còn gateway trả trang HTML, client buộc phải viết ba bộ xử lý khác nhau. Thông tin lỗi, khả năng retry và khả năng hỗ trợ vận hành cũng thiếu nhất quán.

Sau bài học, bạn có thể:

1. Phân biệt lỗi được tạo ở application, security filter và gateway.
2. Thiết kế hợp đồng lỗi chuẩn dựa trên **HTTP Problem Details (RFC 9457)**.
3. Ánh xạ đúng **status HTTP**, **mã lỗi ứng dụng**, chi tiết và header có ý nghĩa.
4. Chuẩn hóa lỗi tại **@RestControllerAdvice**, **AuthenticationEntryPoint/AccessDeniedHandler** và cơ chế phản hồi riêng của gateway.
5. Truyền **request ID/trace ID** xuyên các tầng để xác định nơi xảy ra lỗi.
6. Không làm lộ token, stack trace, thông tin nội bộ hoặc sự tồn tại của tài nguyên trái quyền.
7. Mô tả lỗi trong **OpenAPI**, kiểm thử từng tầng và kiểm thử end-to-end.
8. Thiết kế hành vi client phù hợp cho lỗi không retry, lỗi có thể retry và tình huống chưa rõ kết quả sau timeout.

**Đầu ra kỳ vọng:** một tài liệu quy ước error contract, bảng ánh xạ trạng thái, mẫu triển khai Java/Spring, chính sách gateway và bộ ca kiểm thử có thể dùng trong dự án REST API.

## 2. Hiểu nơi phát sinh lỗi trong đường đi HTTP

Một yêu cầu không đi thẳng từ client vào controller. Trong triển khai thực tế, có nhiều thành phần có thể từ chối yêu cầu hoặc tự tạo phản hồi.

~~~mermaid
flowchart LR
    C[Client] --> G[API Gateway / WAF]
    G --> S[Spring Security filters]
    S --> M[DispatcherServlet / Controller]
    M --> B[Business service]
    B --> D[(Database / Downstream API)]
    G -->|4xx hoặc 5xx do gateway tạo| C
    S -->|401 / 403 trước controller| G
    M -->|Validation hoặc domain error| S
    D -->|Lỗi phụ thuộc| B
    B --> M
~~~

Trong đường đi này:

| Tầng | Trường hợp thường gặp | Công cụ xử lý thích hợp |
| --- | --- | --- |
| **Gateway/WAF** | Không tìm thấy route, vượt rate limit, upstream không sẵn sàng, timeout, chặn chính sách ở edge | Error handler/error response policy của gateway |
| **Security filter** | Thiếu/không hợp lệ token, không đủ scope/quyền để vào endpoint | Spring Security **AuthenticationEntryPoint**, **AccessDeniedHandler**, cơ chế lỗi OAuth2 resource server |
| **Spring MVC** | JSON sai, validation, sai kiểu path/query, lỗi controller, exception nghiệp vụ | **@RestControllerAdvice**, **ResponseEntityExceptionHandler**, Spring MVC exception resolvers |
| **Service/data access** | Trùng khóa, xung đột trạng thái, không tìm thấy resource, downstream lỗi | Chuyển thành lỗi có ý nghĩa ở ranh giới API |
| **Hạ tầng ngoài ứng dụng** | Proxy/TLS/load balancer mất kết nối, lỗi trước khi request tới ứng dụng | Thành phần trực tiếp sinh response; đôi khi không thể trả JSON |

**Nguyên tắc:** mỗi tầng chịu trách nhiệm chuẩn hóa **phản hồi do chính tầng đó tạo**. Application không thể dùng @RestControllerAdvice để kiểm soát chắc chắn một phản hồi 504 mà gateway đã tự trả trước khi chuyển request. Tương tự, exception ném từ một servlet security filter có thể không đi qua Spring MVC exception handler.

Một hợp đồng đồng nhất cần được áp dụng **xuyên các ranh giới**, không chỉ ở controller.

## 3. Chọn khuôn dạng lỗi thống nhất: HTTP Problem Details

**RFC 9457** định nghĩa một cách biểu diễn lỗi của HTTP API thường được trả với media type **application/problem+json**. Các thành viên chuẩn của một problem detail gồm:

| Trường | Vai trò |
| --- | --- |
| **type** | URI-reference định danh **loại vấn đề**; mặc định có thể là about:blank |
| **title** | Mô tả ngắn, ổn định cho loại vấn đề, không phải stack trace |
| **status** | HTTP status code tương ứng với lỗi này |
| **detail** | Mô tả cụ thể có ích cho lần phát sinh này, an toàn để công bố |
| **instance** | URI-reference xác định lần xuất hiện vấn đề, khi thích hợp |

Các trường trên không nhất thiết phải xuất hiện đầy đủ trong mọi response theo RFC, nhưng **hợp đồng dự án có thể yêu cầu tập con ổn định**. Có thể bổ sung extension members để phục vụ ứng dụng.

Ví dụ lỗi validation được application tạo:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-8f21

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Một hoặc nhiều trường dữ liệu không hợp lệ.",
  "instance": "/api/v1/orders",
  "code": "VALIDATION_FAILED",
  "traceId": "req-8f21",
  "violations": [
    {
      "field": "items[0].quantity",
      "message": "Phải lớn hơn 0"
    }
  ]
}
~~~

**code**, **traceId** và **violations** là **extension của hợp đồng API**, không phải trường chuẩn bắt buộc trong RFC 9457. Đội ngũ cần chọn tên, kiểu dữ liệu và quy tắc áp dụng nhất quán giữa các tầng.

### 3.1. Vì sao cần cả HTTP status và application code?

HTTP status trả lời **loại kết quả ở mức giao thức**: 400 request không hợp lệ, 401 chưa xác thực, 403 không được phép, 409 xung đột, 429 bị giới hạn, 503 dịch vụ tạm không sẵn sàng.

**Application code** là mã ổn định cho một vấn đề cụ thể để client có thể xử lý tự động, ví dụ:

- **VALIDATION_FAILED** – dữ liệu đầu vào không hợp lệ.
- **ORDER_ALREADY_PAID** – đơn hàng đã thanh toán, không thể hủy theo quy tắc hiện tại.
- **AUTHENTICATION_REQUIRED** – thiếu thông tin xác thực có thể chấp nhận.
- **ACCESS_DENIED** – không được thực hiện hành động.
- **RATE_LIMITED** – vượt hạn mức.
- **UPSTREAM_TIMEOUT** – upstream không phản hồi đúng thời gian.

Không dùng **detail** làm khóa điều khiển logic client vì detail có thể thay đổi theo ngôn ngữ hoặc được làm rõ ở bản phát hành sau. Client nên dựa vào **HTTP status + code + trường dữ liệu ổn định**.

### 3.2. Type URI phải có ý nghĩa

Một **type URI** nên ổn định và có thể liên kết tới tài liệu giải thích lỗi và cách xử lý, ví dụ **https://api.example.test/problems/order-already-paid**. Nếu loại vấn đề chưa có URI riêng, RFC cho phép **about:blank**.

Không dùng chuỗi ngẫu nhiên, trace ID hoặc message có chứa email/token làm type. **instance** định danh sự cố cụ thể, có thể là đường dẫn request đã được làm sạch hoặc URI riêng cho sự kiện lỗi; không tự động ghép query chứa bí mật vào đó.

## 4. Quy ước chuẩn: một hợp đồng xuyên ba tầng

Một hợp đồng thực dụng cho hệ thống REST có thể yêu cầu:

- **Content-Type:** application/problem+json cho các phản hồi lỗi có JSON body.
- **status:** phải phản ánh mã HTTP thực mà tầng đó gửi ra.
- **code:** mã lỗi ổn định bằng chữ hoa và dấu gạch dưới, do danh mục chung quản lý.
- **type/title:** biểu diễn loại lỗi, ổn định và không tiết lộ chi tiết triển khai.
- **detail:** thông tin đủ cho client, tránh đưa stack trace, tên bảng DB, URL nội bộ, chính sách WAF cụ thể.
- **traceId:** cùng mã truy vết tương ứng với request ở gateway, security và application khi có thể.
- **instance:** URI-reference đã lọc thông tin nhạy cảm.
- **violations:** chỉ có cho lỗi kiểm tra từng trường; với lỗi khác có thể bỏ trường.
- **header giao thức:** vẫn giữ **WWW-Authenticate**, **Retry-After**, **Allow** và các header bắt buộc theo từng tình huống.

Ví dụ phân phối trách nhiệm:

| Nơi tạo lỗi | HTTP status | code | Content-Type | Điều kiện bổ sung |
| --- | ---: | --- | --- | --- |
| Application validation | 400 | VALIDATION_FAILED | application/problem+json | Có violations phù hợp |
| Business rule | 409 | ORDER_ALREADY_PAID | application/problem+json | Không lộ trạng thái của đơn ngoài quyền |
| Security filter – thiếu token | 401 | AUTHENTICATION_REQUIRED | application/problem+json | **WWW-Authenticate** phù hợp Bearer |
| Security filter – không đủ quyền | 403 | ACCESS_DENIED | application/problem+json | Không trả chi tiết quyền nội bộ |
| Gateway rate limit | 429 | RATE_LIMITED | application/problem+json | Có thể kèm **Retry-After** |
| Gateway upstream timeout | 504 | UPSTREAM_TIMEOUT | application/problem+json | Không tiết lộ hostname/port nội bộ |
| Gateway upstream unavailable | 503 | SERVICE_UNAVAILABLE | application/problem+json | Retry-After khi có căn cứ thời gian |
| Gateway upstream invalid response | 502 | BAD_GATEWAY | application/problem+json | Ghi nguyên nhân ở log nội bộ |

Đây là **quy ước mẫu**. Từng API phải xác nhận mã lỗi có phù hợp hành vi thực tế, đồng thời không biến mọi exception thành HTTP 500 hoặc mọi lỗi thành HTTP 200.

## 5. Phân biệt đúng HTTP status để không che giấu nguyên nhân

| Mã | Khi phù hợp | Khi không nên dùng |
| --- | --- | --- |
| **400 Bad Request** | JSON sai cú pháp, tham số không parse được, request vi phạm quy tắc nhập liệu đã định | Lỗi DB hoặc gateway timeout |
| **401 Unauthorized** | Chưa có thông tin xác thực hợp lệ | User đã xác thực nhưng thiếu quyền |
| **403 Forbidden** | Người gọi đã xác thực nhưng không được thực hiện | Token đã hết hạn hoặc chưa được cung cấp |
| **404 Not Found** | Resource không tồn tại hoặc được chủ ý che giấu với caller | Lỗi kết nối DB hoặc route upstream không sẵn sàng |
| **405 Method Not Allowed** | Resource không hỗ trợ phương thức; response phải có **Allow** | Validation lỗi của một phương thức có hỗ trợ |
| **409 Conflict** | Trạng thái nghiệp vụ xung đột với thao tác; ví dụ không thể hủy đơn đã thanh toán | Mất kết nối dịch vụ |
| **412 Precondition Failed** | **If-Match** hoặc điều kiện HTTP không được thỏa | Quy tắc trạng thái nghiệp vụ không liên quan điều kiện |
| **415 Unsupported Media Type** | Request dùng media type không được hỗ trợ | JSON hợp lệ nhưng thiếu trường |
| **422 Unprocessable Content** | Server hiểu nội dung và cú pháp nhưng không xử lý được chỉ dẫn theo ngữ nghĩa | Sai cú pháp JSON; cần nhất quán chính sách 400/422 |
| **428 Precondition Required** | API yêu cầu client gửi điều kiện, ví dụ If-Match | ETag đã cung cấp nhưng không khớp; dùng 412 |
| **429 Too Many Requests** | Rate limit/quota request | Sự cố upstream không liên quan giới hạn |
| **500 Internal Server Error** | Lỗi bất ngờ ở ứng dụng, không thể gán an toàn sang lỗi cụ thể | Mọi lỗi do người dùng |
| **502 Bad Gateway** | Gateway/proxy nhận phản hồi không hợp lệ từ upstream hoặc lỗi phù hợp ngữ nghĩa gateway | Timeout chờ upstream được phân loại 504 |
| **503 Service Unavailable** | Dịch vụ tạm không sẵn sàng, quá tải hoặc bảo trì | Sai request của client |
| **504 Gateway Timeout** | Gateway không nhận phản hồi kịp từ upstream | Request client sai dữ liệu hoặc 408 |

**408 Request Timeout** liên quan đến việc server không nhận được request hoàn chỉnh trong thời gian chấp nhận, **không** phải mã mặc định cho timeout của gateway khi đợi upstream; trường hợp sau thường dùng **504**.

**499** có thể xuất hiện trong log của một số proxy để mô tả client đóng kết nối, nhưng không phải status HTTP chuẩn để API công bố như mã lỗi công khai.

**404 do gateway** (không match route) và **404 do application** (không tìm thấy resource) đều có status 404, nhưng có thể phân biệt bằng **code** an toàn như **ROUTE_NOT_FOUND** và **RESOURCE_NOT_FOUND** mà không lộ thông tin nội bộ.

### 5.1. Không đóng gói lỗi thành HTTP 200

Một response như:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":false,"error":"server_failed"}
~~~

làm sai ngữ nghĩa HTTP cho một lần thực thi thất bại. Client, gateway, cache, alert và công cụ APM có thể coi đó là thành công. Với các lỗi thật, trả status phù hợp và Problem Details. Trường hợp xử lý hàng loạt với kết quả từng item là một **hợp đồng operation riêng**, không phải lý do để mọi lỗi API đều dùng 200.

## 6. Lỗi nào được xử lý ở application?

Trong Spring MVC, các lỗi thường được đưa tới exception resolver khi đã vào luồng xử lý servlet/controller. Có thể gom logic ở **@RestControllerAdvice**, kết hợp với **ResponseEntityExceptionHandler** để bao phủ các lỗi MVC có sẵn.

Ví dụ phân loại:

| Nguồn lỗi | Ví dụ exception/điều kiện | Phản hồi gợi ý |
| --- | --- | --- |
| Bean Validation | **MethodArgumentNotValidException** với @Valid @RequestBody | 400 + VALIDATION_FAILED |
| Tham số đường dẫn | ID không thể chuyển sang UUID | 400 + INVALID_PARAMETER |
| Request JSON sai | **HttpMessageNotReadableException** | 400 + MALFORMED_JSON |
| Resource không tồn tại | Domain **OrderNotFoundException** | 404 + ORDER_NOT_FOUND |
| Xung đột nghiệp vụ | Domain **OrderAlreadyPaidException** | 409 + ORDER_ALREADY_PAID |
| ETag không khớp | Điều kiện If-Match không được thỏa | 412 + PRECONDITION_FAILED |
| Lỗi không dự đoán | NullPointerException/bug | 500 + INTERNAL_ERROR với thông điệp chung |
| DB hoặc downstream lỗi | Kết nối/sự cố có thể retry | 503/502/504 hoặc 500 theo vai trò và chính sách thực tế |

Không nên để class name như **DataIntegrityViolationException** hoặc thông điệp từ JDBC xuất hiện trực tiếp trong response. Chuyển các lỗi dự đoán được thành domain exception với mã lỗi ổn định; đối với lỗi không dự đoán, log chi tiết ở server và trả thông điệp công khai an toàn.

**Phạm vi của @RestControllerAdvice:** nó xử lý exception được Spring MVC chuyển qua resolver. Exception ở security filter, gateway, container hoặc xảy ra sau khi response đã commit có thể nằm ngoài khả năng của advice.

## 7. Ví dụ hợp đồng dùng chung trong Java/Spring

Ví dụ sau phù hợp với **Java 17+**, **Spring Boot 3 / Spring Framework 6** và JSON. Để có cùng hình dạng ở MVC và security filter, ta dùng một **DTO riêng** theo RFC 9457, với các extension thống nhất. Spring có lớp **ProblemDetail** tích hợp; lựa chọn DTO ở đây minh họa việc chia sẻ chính xác một serializer giữa các tầng.

### 7.1. DTO và factory

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Locale;

@JsonInclude(JsonInclude.Include.NON_EMPTY)
public record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String instance,
        String code,
        String traceId,
        List<Violation> violations) {}

public record Violation(String field, String message) {}

@Component
public class ApiProblems {
    public ApiProblem create(
            HttpStatus status,
            String code,
            String title,
            String safeDetail,
            HttpServletRequest request,
            List<Violation> violations) {

        String type = "https://api.example.test/problems/"
                + code.toLowerCase(Locale.ROOT).replace('_', '-');

        // Trace ID đã được middleware xác thực/sinh và gắn vào attribute.
        String traceId = (String) request.getAttribute("traceId");

        return new ApiProblem(
                type,
                title,
                status.value(),
                safeDetail,
                request.getRequestURI(),
                code,
                traceId,
                violations);
    }
}
~~~

**Ghi chú về mã mẫu:**

- Với Java, mỗi **public top-level type** thường nằm ở tệp riêng; đoạn trên gộp để dễ đọc bài học. Khi đưa vào ứng dụng, tách **ApiProblem**, **Violation** và **ApiProblems** thành các tệp phù hợp.
- Bộ **code** phải xuất phát từ danh mục do server kiểm soát; không ghép chuỗi người dùng tùy ý vào type URI.
- **request.getRequestURI()** là ví dụ instance; nếu đường dẫn chứa thông tin nhạy cảm, hãy thay bằng route template hoặc URI sự cố đã làm sạch.
- Attribute **traceId** chỉ là quy ước ví dụ; middleware/tracing phải đặt giá trị đáng tin và truyền nhất quán.
- **@JsonInclude(NON_EMPTY)** làm các extension tùy chọn có thể vắng mặt trong JSON; trường chuẩn nào được yêu cầu bởi hợp đồng vẫn cần bảo đảm hiện diện.

### 7.2. @RestControllerAdvice cho lỗi nghiệp vụ

~~~java
@RestControllerAdvice
public class ApiExceptionAdvice {
    private final ApiProblems problems;

    public ApiExceptionAdvice(ApiProblems problems) {
        this.problems = problems;
    }

    @ExceptionHandler(OrderAlreadyPaidException.class)
    public ResponseEntity<ApiProblem> handlePaidOrder(
            OrderAlreadyPaidException ex,
            HttpServletRequest request) {

        HttpStatus status = HttpStatus.CONFLICT;
        ApiProblem body = problems.create(
                status,
                "ORDER_ALREADY_PAID",
                "Order cannot be cancelled",
                "Đơn hàng đã thanh toán và không thể hủy theo thao tác này.",
                request,
                List.of());

        return ResponseEntity.status(status)
                .contentType(MediaType.parseMediaType("application/problem+json"))
                .header("Cache-Control", "no-store")
                .body(body);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiProblem> handleNotFound(
            OrderNotFoundException ex,
            HttpServletRequest request) {

        HttpStatus status = HttpStatus.NOT_FOUND;
        ApiProblem body = problems.create(
                status,
                "ORDER_NOT_FOUND",
                "Order not found",
                "Không tìm thấy đơn hàng trong phạm vi được phép truy cập.",
                request,
                List.of());

        return ResponseEntity.status(status)
                .contentType(MediaType.parseMediaType("application/problem+json"))
                .body(body);
    }
}
~~~

Các import Java/Spring liên quan đến **@ExceptionHandler**, **ResponseEntity** và **MediaType** được lược bỏ để tập trung vào thiết kế. Hai class exception là ví dụ domain exception do ứng dụng định nghĩa.

**Chỉ có hai handler này chưa bao phủ hết MVC.** Cần chuẩn hóa thêm lỗi parsing, validation, route/method, content type và unexpected exception. Trong Spring MVC có thể mở rộng **ResponseEntityExceptionHandler** để xử lý các lỗi framework, áp dụng factory chung và không vô tình biến lỗi 400/405/415 đã được framework nhận diện thành 500.

### 7.3. Lỗi validation có danh sách trường

Một lỗi kiểm tra dữ liệu có thể trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Dữ liệu yêu cầu không hợp lệ.",
  "instance": "/api/v1/orders",
  "code": "VALIDATION_FAILED",
  "traceId": "req-8f21",
  "violations": [
    {"field":"items[0].quantity","message":"Phải lớn hơn 0"},
    {"field":"shippingAddress.city","message":"Không được để trống"}
  ]
}
~~~

Không đưa nguyên giá trị người dùng đã nhập vào violations nếu có thể chứa mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân. Nếu dùng **defaultMessage** từ Bean Validation, cần rà soát nội dung template và placeholder để tránh vô tình hiển thị giá trị bị từ chối.

Lỗi validation có thể được chuẩn hóa từ **MethodArgumentNotValidException**, **ConstraintViolationException**, lỗi parse JSON và lỗi chuyển đổi kiểu tham số. Tuy nhiên, các nhóm lỗi có ngữ nghĩa khác nhau nên không nhất thiết phải cùng một code: **MALFORMED_JSON** và **VALIDATION_FAILED** có thể giúp client xử lý rõ hơn.

## 8. Vì sao security filter cần cơ chế riêng?

Spring Security xử lý nhiều yêu cầu **trước khi controller được gọi**. Ví dụ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant F as Security Filter Chain
    participant M as Spring MVC
    C->>G: GET /api/v1/orders + token hết hạn
    G->>F: Forward request
    F->>F: Token validation failed
    F-->>G: 401 + WWW-Authenticate + Problem Details
    G-->>C: Giữ status, headers và JSON
    Note over M: Controller không được gọi
~~~

Trong Spring Security:

- **AuthenticationEntryPoint** giải quyết trường hợp cần bắt đầu/quay lại xác thực, thường dẫn tới **401** với Bearer-protected API.
- **AccessDeniedHandler** giải quyết trường hợp principal đã xác thực nhưng không đủ quyền, thường dẫn tới **403**.
- OAuth2 resource server còn có đường xử lý authentication failure riêng trong **BearerTokenAuthenticationFilter**. Khi tùy biến, phải kiểm thử cả token vắng mặt, không hợp lệ và hết hạn; không giả định @RestControllerAdvice sẽ chặn được tất cả.
- Với tài nguyên không cho phép tiết lộ sự tồn tại, một số kiểm tra theo resource có thể chủ động trả **404** theo chính sách, nhưng không được làm sai mô hình xác thực/phân quyền.

### 8.1. Giữ header WWW-Authenticate

Theo HTTP authentication và Bearer token usage, một API yêu cầu Bearer token phải trả thử thách xác thực (**WWW-Authenticate**) phù hợp khi gửi 401. Một phản hồi 401 đã chuẩn hóa có thể có dạng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-91a2

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "Cần thông tin xác thực hợp lệ để truy cập API.",
  "instance": "/api/v1/orders",
  "code": "AUTHENTICATION_REQUIRED",
  "traceId": "req-91a2"
}
~~~

Với token không hợp lệ, challenge có thể bao gồm tham số **error="invalid_token"** theo quy tắc Bearer authentication. Khi tùy chỉnh body, **không làm mất** các header do cơ chế bảo mật chuẩn tạo ra và không lộ token hoặc nguyên nhân nội bộ chi tiết.

### 8.2. Ví dụ writer dùng chung cho security handler

~~~java
@Component
public class SecurityProblemHandlers {
    private final ObjectMapper mapper;
    private final ApiProblems problems;

    private final BearerTokenAuthenticationEntryPoint bearerEntryPoint =
            new BearerTokenAuthenticationEntryPoint();

    private final BearerTokenAccessDeniedHandler bearerAccessDenied =
            new BearerTokenAccessDeniedHandler();

    public SecurityProblemHandlers(ObjectMapper mapper, ApiProblems problems) {
        this.mapper = mapper;
        this.problems = problems;
    }

    public AuthenticationEntryPoint entryPoint() {
        return (request, response, exception) -> {
            // Giữ challenge Bearer đúng với loại authentication failure.
            bearerEntryPoint.commence(request, response, exception);
            writeProblem(
                    request, response, HttpStatus.UNAUTHORIZED,
                    "AUTHENTICATION_REQUIRED", "Authentication required",
                    "Cần thông tin xác thực hợp lệ.");
        };
    }

    public AccessDeniedHandler deniedHandler() {
        return (request, response, exception) -> {
            // Cho handler chuẩn thiết lập status/headers cần thiết.
            bearerAccessDenied.handle(request, response, exception);
            writeProblem(
                    request, response, HttpStatus.FORBIDDEN,
                    "ACCESS_DENIED", "Access denied",
                    "Bạn không có quyền thực hiện yêu cầu này.");
        };
    }

    private void writeProblem(
            HttpServletRequest request,
            HttpServletResponse response,
            HttpStatus status,
            String code,
            String title,
            String safeDetail) throws IOException {

        if (response.isCommitted()) {
            // Log nội bộ: không thể thay một response đã bắt đầu gửi.
            return;
        }

        response.setStatus(status.value());
        response.setContentType("application/problem+json");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        ApiProblem body = problems.create(
                status, code, title, safeDetail, request, List.of());
        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

Đây là **mẫu cho Servlet-based Spring Security**. Các import tương ứng từ Spring Security OAuth2 Resource Server, Jakarta Servlet và Jackson cần được bổ sung. Việc delegate cho handler chuẩn trước khi ghi JSON giúp giữ **WWW-Authenticate**; nếu tùy chỉnh status hoặc challenge nâng cao, phải kiểm thử tương thích RFC 6750.

### 8.3. Gắn handler vào SecurityFilterChain

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        SecurityProblemHandlers errors) throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth
            .authenticationEntryPoint(errors.entryPoint())
            .accessDeniedHandler(errors.deniedHandler())
            .jwt(Customizer.withDefaults()))
        .exceptionHandling(exceptions -> exceptions
            .authenticationEntryPoint(errors.entryPoint())
            .accessDeniedHandler(errors.deniedHandler()));

    return http.build();
}
~~~

Tùy cách cấu hình thực tế, Spring Security có nhiều authentication failure path khác nhau. **Phải test cả challenge của BearerTokenAuthenticationFilter lẫn exception handling authorization** qua request HTTP thật. SecurityFilterChain không tự chuẩn hóa lỗi được tạo ở API gateway phía trước.

**Lưu ý quan trọng:** một 401 do gateway tự sinh vì thiếu API key không được tự động đi qua Spring Security của ứng dụng; gateway phải tạo cùng hợp đồng tại chính nó.

## 9. API gateway: chuẩn hóa những lỗi do gateway tự tạo

API gateway có thể dùng **Spring Cloud Gateway**, Envoy, NGINX, Kong hoặc nền tảng cloud khác. Công nghệ và API cấu hình khác nhau, nhưng mục tiêu của hợp đồng lỗi giống nhau.

Các trường hợp gateway thường tự quyết định phản hồi:

1. **Không match route:** trả 404 với code như ROUTE_NOT_FOUND, không lộ danh sách route nội bộ.
2. **Rate limit:** trả 429 với RATE_LIMITED và có thể thêm Retry-After.
3. **Upstream không sẵn sàng/đang bảo trì:** trả 503 và code SERVICE_UNAVAILABLE khi phù hợp.
4. **Upstream trả phản hồi không hợp lệ:** có thể trả 502 BAD_GATEWAY.
5. **Upstream timeout:** trả 504 UPSTREAM_TIMEOUT.
6. **WAF/chính sách ở edge từ chối:** có thể trả 403 với mã an toàn, tránh công bố luật phát hiện hoặc thông tin bảo vệ.
7. **CORS/preflight không được phép:** trả phản hồi theo chính sách gateway; cần tránh biến lỗi CORS thành một trang HTML khó truy vết.

Ví dụ gateway trả 504:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7b20

{
  "type": "https://api.example.test/problems/upstream-timeout",
  "title": "Upstream timeout",
  "status": 504,
  "detail": "Dịch vụ tạm thời không phản hồi kịp. Vui lòng thử lại sau.",
  "instance": "/api/v1/orders",
  "code": "UPSTREAM_TIMEOUT",
  "traceId": "req-7b20"
}
~~~

**Gateway không nên chuyển tiếp thông tin nội bộ** như hostname private, địa chỉ IP backend, tên cluster, stack trace, số lượng pod hoặc lỗi TLS chi tiết vào response công khai.

### 9.1. Khi nào giữ response upstream, khi nào thay bằng problem?

| Tình huống | Cách xử lý đề xuất |
| --- | --- |
| Application trả 409 với Problem Details hợp lệ | **Giữ nguyên status, header và body**; không tạo lỗi 502 mới |
| Application trả 401 với Bearer challenge hợp lệ | Giữ semantics và **WWW-Authenticate** |
| Gateway tự phát sinh 429 | Tạo Problem Details bằng gateway policy chung |
| Gateway tự phát sinh 504 | Tạo Problem Details; log lỗi upstream nội bộ |
| Upstream trả lỗi 500 với HTML không đúng contract | Có thể chuẩn hóa tại gateway nếu chính sách xác định rõ; ghi nhận nguồn và không làm sai mã |
| Response upstream đã streaming một phần | Không thể luôn thay bằng JSON an toàn; đóng kết nối/ghi log theo khả năng transport |

**Không viết một filter mù quáng chuyển mọi response có status 4xx/5xx thành 500 chung.** Việc đó làm mất phân biệt lỗi nghiệp vụ, lỗi xác thực và lỗi hạ tầng.

Một số gateway không cho phép can thiệp body của mọi lỗi (hoặc việc sửa body cần buffering lớn). Khi đó cần ưu tiên **chuẩn hóa lỗi gateway có thể tạo**, phân định những giới hạn thực tế và kiểm thử tại edge.

### 9.2. Ví dụ quy tắc gateway độc lập nhà cung cấp

~~~yaml
gateway_error_policy:
  content_type: application/problem+json
  trace_header: X-Request-Id
  sanitize_instance_query: true
  generated_errors:
    no_route:
      http_status: 404
      code: ROUTE_NOT_FOUND
    rate_limit:
      http_status: 429
      code: RATE_LIMITED
      retry_after: when_known
    upstream_unavailable:
      http_status: 503
      code: SERVICE_UNAVAILABLE
    upstream_invalid_response:
      http_status: 502
      code: BAD_GATEWAY
    upstream_timeout:
      http_status: 504
      code: UPSTREAM_TIMEOUT
  preserve_upstream_problem_responses: true
~~~

Đây là **pseudoconfiguration để mô tả chính sách**, không phải YAML có thể copy trực tiếp vào Spring Cloud Gateway, NGINX hay Kong. Mỗi gateway có cách thiết lập error handler, filter order, timeout, header và response template riêng.

Với **Spring Cloud Gateway dùng WebFlux**, lỗi phát sinh trong gateway thuộc pipeline reactive; một **ErrorWebExceptionHandler** hoặc cơ chế xử lý lỗi WebFlux tương ứng có thể được dùng để tạo cùng contract. Không áp dụng nguyên xi **@RestControllerAdvice của Spring MVC Servlet** vào gateway WebFlux mà không hiểu pipeline và các lỗi tự tạo ở filter trước handler.

## 10. Request ID, trace ID và tương quan xuyên các tầng

Một error contract nhất quán về mặt JSON vẫn khó hỗ trợ nếu không biết lỗi xuất phát từ request nào. Cần thiết kế **mã tương quan** xuyên gateway, security và ứng dụng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant S as Security
    participant A as Application
    participant L as Logging/Tracing
    C->>G: POST /orders
    G->>G: Tạo/kiểm tra request ID
    G->>S: X-Request-Id: req-8f21
    S->>A: Giữ context req-8f21
    A->>L: Log domain conflict + req-8f21
    A-->>S: 409 Problem Details + traceId
    S-->>G: Giữ response
    G-->>C: 409 + X-Request-Id: req-8f21
~~~

Có thể dùng **W3C Trace Context (traceparent)** với hệ tracing phân tán. Tuy nhiên, **trace ID** và **request ID** có thể là hai khái niệm khác nhau; đừng đặt tên traceId cho một UUID tự sinh rồi khẳng định nó là trace ID chuẩn nếu hệ thống không dùng distributed tracing.

Một thiết kế có thể:

- Sinh **X-Request-Id** ở trusted edge nếu client không cung cấp mã phù hợp.
- Nếu nhận mã từ client, kiểm tra định dạng, độ dài và chính sách tin cậy; không cho phép header injection hoặc giá trị cực dài.
- Truyền request ID vào request context, log và response header của các tầng.
- Nếu có tracing, ghi trace ID chuẩn và liên kết request ID với span/trace trong logs.
- Dùng **MDC** trong xử lý đồng bộ; với async/reaction cần truyền context có chủ đích vì thread-local không tự đi xuyên tất cả tác vụ.
- Đảm bảo gateway tự tạo 429/504 vẫn có request ID, ngay cả khi application chưa chạy.
- Khi nhiều retry, phân biệt request attempt ID và logical operation/idempotency key để truy vết đầy đủ.

**Không tin vô điều kiện X-Forwarded-For, X-Forwarded-Host hoặc trace headers** từ internet. Chỉ dùng chúng theo cấu hình trusted proxy và chính sách xác thực ranh giới.

## 11. Chuẩn hóa thông tin lỗi mà vẫn bảo mật

Thông tin lỗi hữu ích cho client không nhất thiết là thông tin đủ chi tiết để debug server. Cần chia thành hai vùng:

| Response công khai | Log/tracing nội bộ |
| --- | --- |
| Mã lỗi ổn định | Exception class, stack trace có kiểm soát |
| Mô tả thân thiện, không chứa bí mật | Tên service, span, DB error đã xử lý dữ liệu nhạy cảm |
| Request ID / trace ID | Correlation, operation ID, upstream dependency |
| Violation chỉ gồm tên trường và thông điệp an toàn | Validation rule và context phục vụ chẩn đoán |
| Gợi ý retry thích hợp | Retry count, circuit breaker state, timeout breakdown |

Tuyệt đối tránh đưa các dữ liệu sau vào response lỗi: access token, refresh token, cookie, mật khẩu, API key, khóa bí mật, SQL raw chứa thông tin cá nhân, stack trace, đường dẫn filesystem nhạy cảm, tên bảng nội bộ hoặc dữ liệu của tenant khác.

**404 vs 403:** đối với tài nguyên không được quyền nhìn thấy, một API có thể trả 404 để không tiết lộ sự tồn tại. Quy tắc này phải được áp dụng tại application/resource authorization và nhất quán với các endpoint đọc, ghi, tìm kiếm; không để response detail vô tình lộ “đơn hàng thuộc tenant B”.

**401 vs 403:** client không nên retry refresh token vô hạn với 403. 401 thuộc cơ chế authentication; 403 thuộc authorization và chính sách truy cập. Cần giữ header challenge ở 401.

**429/503:** có thể dùng **Retry-After** khi biết thời điểm/độ trễ nên retry. Không đưa thời gian retry tùy tiện khiến tất cả client đồng loạt dội tải trở lại.

## 12. Ngữ nghĩa retry và tình huống kết quả chưa rõ

Một lỗi từ gateway không luôn chứng minh server ứng dụng **chưa thực thi hành động**. Ví dụ client POST tạo đơn, gateway timeout sau khi ứng dụng đã commit, rồi trả **504**. Retry POST với payload tương tự có thể tạo đơn trùng nếu không có idempotency.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Application
    participant D as Database
    C->>G: POST /orders + Idempotency-Key K
    G->>A: Forward
    A->>D: Commit order
    D-->>A: OK
    G-->>C: 504 do timeout chờ
    Note over C: Không biết thao tác đã commit hay chưa
    C->>G: Retry cùng K
    G->>A: Forward cùng K
    A->>D: Tra logical operation K
    D-->>A: Order đã tạo
    A-->>C: Trả kết quả trước đó
~~~

Để retry có kiểm soát:

- **GET/HEAD** và các thao tác idempotent có thể retry theo chính sách khi gặp lỗi tạm thời, nhưng cần giới hạn, backoff và timeout.
- **POST** có tác dụng tạo/thanh toán cần **Idempotency-Key** hoặc cơ chế dedup nghiệp vụ được server triển khai, đặc biệt khi timeout/504 khiến outcome chưa rõ.
- **409/412** thường yêu cầu đọc lại trạng thái hoặc giải quyết điều kiện trước khi retry, không nên retry y nguyên vô hạn.
- **400/422** cần sửa input; retry cùng payload không giải quyết vấn đề.
- **401** cần luồng xác thực phù hợp; **403** cần điều chỉnh quyền/chính sách, không refresh token vô hạn.
- **429/503** có thể retry sau Retry-After hoặc exponential backoff với jitter và giới hạn tổng thời gian.
- **502/504** là tín hiệu lỗi trung gian, nhưng với phương thức thay đổi trạng thái, client phải giải quyết **uncertain outcome** trước khi gửi lại không kiểm soát.

**Error response là tín hiệu, không phải cơ chế đảm bảo exactly-once.** Tính an toàn khi retry phải được thiết kế tại operation và tầng dữ liệu.

## 13. Ví dụ xuyên suốt: cùng endpoint, ba nguồn lỗi

Giả sử client gọi:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>
X-Request-Id: req-8f21

{"items":[{"sku":"SKU-1","quantity":2}]}
~~~

### Tình huống A – Lỗi do ứng dụng

Request xác thực hợp lệ nhưng đơn đã thanh toán, không cho hủy hoặc thao tác trạng thái tương đương. Controller/service phát hiện domain conflict:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-Id: req-8f21

{
  "type": "https://api.example.test/problems/order-already-paid",
  "title": "Order cannot be changed",
  "status": 409,
  "detail": "Đơn hàng hiện không cho phép thao tác này.",
  "instance": "/api/v1/orders/o-100/cancellations",
  "code": "ORDER_ALREADY_PAID",
  "traceId": "req-8f21"
}
~~~

Ví dụ response này thuộc endpoint **cancellation** tương ứng để minh họa lỗi nghiệp vụ; đối với POST tạo đơn ban đầu, tình huống validation có thể trả **400 VALIDATION_FAILED**. Mục tiêu của ví dụ là so sánh **hình dạng lỗi** giữa các tầng, không gán lỗi hủy đơn vào request tạo đơn.

### Tình huống B – Lỗi do security filter

Bearer token thiếu hoặc hết hạn; controller không được gọi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Content-Type: application/problem+json
X-Request-Id: req-8f22

{
  "type": "https://api.example.test/problems/authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "Cần đăng nhập hoặc cung cấp token hợp lệ.",
  "instance": "/api/v1/orders",
  "code": "AUTHENTICATION_REQUIRED",
  "traceId": "req-8f22"
}
~~~

### Tình huống C – Lỗi do gateway

Upstream quá thời gian chờ, gateway tự phát sinh response:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
X-Request-Id: req-8f23

{
  "type": "https://api.example.test/problems/upstream-timeout",
  "title": "Upstream timeout",
  "status": 504,
  "detail": "Hệ thống tạm không thể hoàn tất yêu cầu trong thời gian quy định.",
  "instance": "/api/v1/orders",
  "code": "UPSTREAM_TIMEOUT",
  "traceId": "req-8f23"
}
~~~

Ba tình huống có **cùng khung RFC 9457 và cùng cách đọc của client**, nhưng status, code, thông điệp và các header giao thức vẫn phản ánh đúng nguyên nhân.

## 14. OpenAPI 3.1: công bố một schema lỗi dùng lại

Một API cần khai báo lỗi theo operation thay vì chỉ có một response "default" mơ hồ. Mẫu sau định nghĩa **ApiProblem** và dùng lại ở nhiều status code:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [items]
              properties:
                items:
                  type: array
                  minItems: 1
                  items:
                    type: object
                    required: [sku, quantity]
                    properties:
                      sku:
                        type: string
                      quantity:
                        type: integer
                        minimum: 1
      responses:
        '201':
          description: Đơn hàng đã được tạo
          headers:
            Location:
              schema:
                type: string
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Forbidden'
        '409':
          $ref: '#/components/responses/Conflict'
        '429':
          $ref: '#/components/responses/TooManyRequests'
        '503':
          $ref: '#/components/responses/Unavailable'
        '504':
          $ref: '#/components/responses/GatewayTimeout'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
          minimum: 400
          maximum: 599
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        traceId:
          type: string
        violations:
          type: array
          items:
            type: object
            required: [field, message]
            properties:
              field:
                type: string
              message:
                type: string
    # Mỗi response lỗi tham chiếu cùng schema.
  responses:
    BadRequest:
      description: Request không hợp lệ
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Unauthorized:
      description: Thiếu xác thực hợp lệ
      headers:
        WWW-Authenticate:
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Forbidden:
      description: Không có quyền
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Conflict:
      description: Xung đột trạng thái
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    TooManyRequests:
      description: Vượt rate limit
      headers:
        Retry-After:
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Unavailable:
      description: Dịch vụ tạm không sẵn sàng
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    GatewayTimeout:
      description: Upstream quá thời gian
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
~~~

Điểm cần nhớ:

- **required** trong schema trên là **yêu cầu của dự án**, không phải danh sách tất cả thành viên bắt buộc do RFC 9457 quy định.
- Nếu có type URI mặc định **about:blank**, schema vẫn nên cho phép giá trị đó.
- OpenAPI không tự tạo body thống nhất ở filter/gateway; triển khai và kiểm thử phải đảm bảo hành vi.
- Mã **504** chỉ phát sinh khi có gateway/proxy trong đường đi và lỗi tương ứng; tài liệu hóa theo thực tế triển khai.
- Có thể dùng nhiều loại problem với extension riêng, nhưng các trường chuẩn và code cần giữ hợp đồng ổn định.

## 15. Kiểm thử từng tầng và end-to-end

Kiểm thử chỉ controller với MockMvc chưa bảo đảm 401 và 504 qua edge có cùng schema. Cần ba mức kiểm tra:

1. **Application tests:** MockMvc/integration test cho validation, domain conflict, missing resource và MVC framework errors.
2. **Security filter tests:** chạy **SecurityFilterChain thật** với token thiếu, invalid, expired, thiếu scope và truy cập sai resource.
3. **Gateway/end-to-end tests:** đi qua endpoint public hoặc gateway test harness; tạo lỗi route, rate limit, timeout và upstream unavailable.

### 15.1. Ma trận test tối thiểu

| ID | Đường thử | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- | --- |
| E01 | Application | JSON sai cú pháp | 400, MALFORMED_JSON, application/problem+json |
| E02 | Application | @Valid thất bại | 400, VALIDATION_FAILED, violations an toàn |
| E03 | Application | Không tìm thấy resource | 404, code đúng, không lộ dữ liệu tenant khác |
| E04 | Application | Xung đột trạng thái nghiệp vụ | 409, code ổn định, detail có ích |
| E05 | MVC framework | Gọi method không được hỗ trợ | 405 và **Allow**, body chuẩn nếu có |
| E06 | Security | Không có token | 401, **WWW-Authenticate**, JSON chuẩn |
| E07 | Security | Bearer token hết hạn | 401, challenge phù hợp, không lộ token |
| E08 | Security | Đã xác thực nhưng thiếu quyền | 403, ACCESS_DENIED |
| E09 | Security + application | Gọi resource tenant khác | 403/404 theo policy, không lộ nội dung |
| E10 | Gateway | Không tìm thấy route | 404, ROUTE_NOT_FOUND, trace ID |
| E11 | Gateway | Vượt rate limit | 429, RATE_LIMITED, Retry-After nếu hợp đồng có |
| E12 | Gateway | Upstream không sẵn sàng | 503 hoặc mã đã định, JSON chuẩn |
| E13 | Gateway | Upstream trả phản hồi không hợp lệ | 502, BAD_GATEWAY |
| E14 | Gateway | Chờ upstream quá timeout | 504, UPSTREAM_TIMEOUT |
| E15 | End-to-end | Application trả 409 qua gateway | Giữ status/body và các header phù hợp |
| E16 | End-to-end | 401 qua gateway | Không làm mất **WWW-Authenticate** |
| E17 | End-to-end | App lỗi bất ngờ | 500, không có stack trace/secret |
| E18 | End-to-end | Có trace/request ID | Header và body liên kết đúng với logs |
| E19 | End-to-end | Query có token nhạy cảm | Không xuất hiện trong instance/detail/log công khai |
| E20 | End-to-end | 504 sau khi POST đã commit | Retry dùng idempotency; không tạo đơn trùng |

### 15.2. Ví dụ MockMvc cho lỗi nghiệp vụ

~~~java
@Test
void paidOrderUsesProblemContract() throws Exception {
    mvc.perform(post("/api/v1/orders/o-100/cancellations")
            .header("Authorization", "Bearer " + validTestToken)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{}"))
        .andExpect(status().isConflict())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json")))
        .andExpect(jsonPath("$.status").value(409))
        .andExpect(jsonPath("$.code").value("ORDER_ALREADY_PAID"))
        .andExpect(jsonPath("$.type").exists())
        .andExpect(jsonPath("$.traceId").exists());
}
~~~

Đây là **mẫu kiểm thử**: cần controller, fixture dữ liệu, auth test setup và middleware tạo traceId tương ứng. Test phải giữ Spring Security filter thực hoặc có test riêng cho filter chain; không giả định MockMvc không bật security có thể xác minh 401/403.

### 15.3. Kiểm tra hợp đồng tự động

Có thể triển khai một bộ **contract assertions dùng chung** cho mọi response lỗi:

- Actual HTTP status bằng giá trị **status** trong body.
- **Content-Type** là application/problem+json khi có problem body.
- **type/title/code** tồn tại đúng schema và ổn định theo loại lỗi.
- **traceId** trong body khớp request context/response header khi quy định.
- Không có trường debug như stackTrace, exceptionClass, internalUrl, sql.
- Header chuyên biệt không bị mất (WWW-Authenticate, Retry-After, Allow).
- Validation field errors không chứa rejected value nhạy cảm.
- Client có thể parse cùng một DTO cho lỗi từ application, security và gateway.

Nên chạy các assertions này trong CI đối với các ví dụ lỗi điển hình ở từng tầng, và có **một vài bài kiểm thử end-to-end** tại môi trường gần production để phát hiện edge config bị lệch.

## 16. Quan sát, vận hành và SLO liên quan đến lỗi

Một hợp đồng nhất quán giúp client nhưng còn phải giúp đội vận hành phân loại nguyên nhân. Cần nhìn thấy **lỗi xuất phát ở đâu**:

| Metric/Log | Ý nghĩa |
| --- | --- |
| HTTP response count theo status/family | Đo 4xx/5xx ở edge và app |
| Error count theo **code** | Phân biệt validation, auth, quota, upstream |
| Error origin: gateway/security/application | Biết tầng sinh lỗi để giao việc |
| Trace/span, request ID | Theo request xuyên dịch vụ |
| Dependency latency, timeout, retries | Chẩn đoán 502/503/504 |
| Auth rejected/forbidden | Nhìn xu hướng lỗi xác thực và phân quyền |
| Rate-limited requests | Đo giới hạn và noisy client |
| Problem response schema violations | Phát hiện hồi quy hợp đồng lỗi |

Các thông số dạng **code/status/origin** có cardinality hạn chế thường phù hợp làm nhãn metric. Không đặt toàn bộ **detail**, raw URL có ID, user email hoặc request ID vào nhãn time-series vì dễ gây cardinality quá cao và lộ thông tin.

SLO cần dựa trên trải nghiệm người dùng và phân biệt lỗi được quy cho hệ thống với input/client errors. Không mặc định mọi 4xx là “hệ thống khỏe”: 401 tăng đột ngột có thể cho biết lỗi cấu hình token, 429 tăng mạnh có thể phản ánh quota không phù hợp. Đồng thời, không cộng mọi validation 400 vào server availability error budget nếu SLO chỉ tính request hợp lệ.

## 17. Triển khai thay đổi error contract mà không làm vỡ client

Nếu API cũ đang trả nhiều cấu trúc lỗi khác nhau, không nên thay ngay mà không kiểm kê client. Một lộ trình an toàn:

1. **Inventory:** thu thập các dạng lỗi đang có từ controller, filter, gateway, framework default và SDK client.
2. **Chốt taxonomy:** bảng status/code/type, thông điệp, headers, khả năng retry và chính sách bảo mật.
3. **Mã dùng chung:** phát hành DTO/factory/schema cùng bộ contract test cho ứng dụng.
4. **Security:** cấu hình AuthenticationEntryPoint, AccessDeniedHandler và Bearer token failure path.
5. **Gateway:** chuẩn hóa các lỗi tự sinh và giữ nguyên upstream Problem Details hợp lệ.
6. **Trace:** triển khai request/trace ID và kiểm thử propagation.
7. **Canary:** so sánh tỷ lệ lỗi, parsing của client, hành vi retry và traffic ở các đường error.
8. **Công bố:** cập nhật OpenAPI, SDK, tài liệu migration và contract changelog.
9. **Giám sát:** cảnh báo schema drift, status mismatch, mất header và lỗi parse trong client.

Nếu client cũ không chấp nhận **application/problem+json**, cần kế hoạch tương thích hoặc versioning rõ. Không thể bảo đảm không breaking change chỉ vì schema mới “đúng chuẩn hơn”.

### 17.1. Cổng chấp nhận trước production

Một đợt chuyển đổi error contract có thể chỉ được phát hành khi:

- Không còn endpoint quan trọng trả **200** cho lỗi thật.
- Application, security và gateway cùng khung lỗi và cùng tên extension.
- 401 còn **WWW-Authenticate**; 405 còn **Allow**; 429/503 áp Retry-After theo hợp đồng.
- Không phát hiện response leak token, stack trace, SQL hoặc nội dung tenant khác.
- E2E test bao phủ 401, 403, validation 400, conflict 409, gateway 429, 503, 504.
- Trace/request ID truy vết được từ một problem response tới log tương ứng.
- Client retry chính xác theo status/code và có idempotency cho các thao tác nhạy cảm.
- Có kế hoạch rollback/canary nếu client hiện hữu không tương thích.

## 18. Bài thực hành thiết kế và tích hợp

**Bối cảnh:** hệ thống thương mại điện tử có **API Gateway → Spring Security → Spring REST API → Order service → Database**. Ba nhóm phát triển đang dùng ba dạng lỗi khác nhau:

- Team API trả **{"errorCode":"ORDER_INVALID","message":"..."}** với HTTP 200.
- Security filter trả 401 với body trống.
- Gateway trả HTML khi rate limit hoặc upstream timeout.

Yêu cầu sản phẩm:

- Mobile và web parse lỗi theo một schema.
- Không lộ stack trace/SQL/token; có trace ID để hỗ trợ.
- Client phân biệt lỗi sửa input, lỗi quyền và lỗi được phép retry.
- Cập nhật OpenAPI và có kiểm thử tích hợp trên đường đi thật.

### 18.1. Nhiệm vụ A – Thiết kế hợp đồng (25 điểm)

Định nghĩa một **ApiProblem** theo RFC 9457 với type/title/status/detail/instance và các extension **code, traceId, violations**. Chọn quy tắc bắt buộc và optional. Viết ví dụ JSON cho validation 400, authentication 401, business conflict 409, rate limit 429 và gateway timeout 504.

Nêu quy tắc bảo vệ thông tin nhạy cảm trong detail và violations.

### 18.2. Nhiệm vụ B – Ánh xạ các tầng (25 điểm)

Vẽ sơ đồ đường đi request. Chỉ ra handler cụ thể cho Spring MVC, Spring Security và gateway. Giải thích vì sao @RestControllerAdvice không bao phủ lỗi gateway và chưa chắc xử lý lỗi security filter.

Bảo đảm 401 giữ WWW-Authenticate và 429 có thể giữ Retry-After.

### 18.3. Nhiệm vụ C – Ứng dụng và client (25 điểm)

Với các status **400, 401, 403, 409, 429, 503, 504**, hãy đề xuất cách UI/SDK phản ứng. Mô tả điều gì xảy ra khi **POST /orders** đã commit nhưng gateway trả 504, và cách sử dụng Idempotency-Key hoặc operation status để tránh tạo đơn trùng.

### 18.4. Nhiệm vụ D – Kiểm thử và vận hành (25 điểm)

Thiết kế ít nhất 10 test: application validation, lỗi nghiệp vụ, token thiếu/hết hạn, user thiếu quyền, route không có, rate limit, gateway timeout, kiểm tra trace ID, header không bị mất và response không chứa bí mật.

Chọn ba metric và hai alert có thể chỉ ra nơi phát sinh lỗi, cùng một chiến lược phát hành từng bước cho client hiện có.

### 18.5. Hướng giải tham khảo

Một phương án hợp lý:

| Nguồn | Loại lỗi | Status | code | Client xử lý |
| --- | --- | ---: | --- | --- |
| Application | Validation | 400 | VALIDATION_FAILED | Hiển thị lỗi trường, sửa dữ liệu |
| Security | Chưa xác thực | 401 | AUTHENTICATION_REQUIRED | Đăng nhập/làm mới xác thực theo chính sách |
| Security | Thiếu quyền | 403 | ACCESS_DENIED | Không retry token vô hạn, hiển thị quyền |
| Application | Đơn không thể đổi trạng thái | 409 | ORDER_ALREADY_PAID | Đọc lại tình trạng và giải thích |
| Gateway | Rate limit | 429 | RATE_LIMITED | Đợi Retry-After/backoff |
| Gateway | Service không sẵn sàng | 503 | SERVICE_UNAVAILABLE | Retry có giới hạn |
| Gateway | Timeout | 504 | UPSTREAM_TIMEOUT | Kiểm tra outcome/idempotency trước khi POST lại |

Dùng một schema JSON chung nhưng **giữ chính xác status và các header giao thức**. Tạo request ID ở gateway, truyền xuyên service, đưa vào body và response header. Security dùng entry point/denied handler cùng writer; application dùng advice/factory; gateway tạo body giống schema cho lỗi do chính nó phát sinh.

Lưu ý **400/409 không phải mọi trường hợp đều retryable**, và **504 không có nghĩa DB đã rollback**. Điểm chấm sẽ ưu tiên khả năng giải thích ngữ nghĩa và kiểm thử đúng thay vì chỉ viết nhiều mã Java.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ chuẩn hóa @RestControllerAdvice | 401/403/429/504 vẫn khác schema | Xử lý tại security và gateway |
| Luôn trả 500 cho mọi lỗi | Client không biết sửa request hay retry | Ánh xạ status theo ngữ nghĩa |
| Trả 200 với success=false | Phá HTTP semantics, sai monitoring | Trả lỗi thật ở status |
| Ghi toàn bộ exception.message vào detail | Lộ SQL, hostname, thông tin nội bộ | Mapping safeDetail có kiểm soát |
| Thay 401 bằng JSON nhưng mất WWW-Authenticate | Sai hợp đồng auth và client khó xử lý | Giữ challenge của Bearer auth |
| Thay mọi upstream 4xx/5xx ở gateway | Che lỗi nghiệp vụ hoặc header quan trọng | Giữ upstream problem hợp lệ |
| Dùng cùng code cho mọi 4xx | Client không phân biệt hành động | Taxonomy code cụ thể, ổn định |
| Dùng detail để điều khiển client | Dễ vỡ khi đổi ngôn ngữ | Dùng code/status/field ổn định |
| Gộp 502/503/504 thành một mã | Chẩn đoán và retry sai | Giữ ngữ nghĩa gateway chính xác |
| Tin mọi trace header từ client | Nguy cơ injection và tương quan sai | Validate hoặc sinh lại tại trusted edge |
| Đưa requestId vào nhãn metric | Cardinality cao | Dùng log/tracing; metric dùng code/status/origin |
| Retry POST sau 504 không có dedup | Tạo đơn/trả tiền trùng | Idempotency key hoặc operation status |
| Không test đường HTTP thật qua gateway | Sai khác giữa local test và production | Có E2E test tại edge |
| Đổi schema ngay không xét client cũ | SDK/web/mobile không parse được | Kiểm kê client, canary, versioning |

## 20. Checklist tổng kết

- [ ] Tôi xác định được lỗi do ứng dụng, security filter và gateway tạo ra.
- [ ] Tôi chọn một schema Problem Details với type/title/status/detail/instance.
- [ ] Tôi phân biệt extension code, traceId, violations với trường chuẩn RFC 9457.
- [ ] Tôi dùng status HTTP chính xác, không trả 200 cho lỗi thật.
- [ ] Tôi không để 401 mất WWW-Authenticate hoặc 405 mất Allow.
- [ ] Tôi xử lý lỗi domain/validation bằng Spring MVC advice phù hợp.
- [ ] Tôi xử lý authentication/authorization bằng cơ chế Spring Security thích hợp.
- [ ] Tôi chuẩn hóa lỗi gateway tại chính gateway và giữ upstream problem hợp lệ.
- [ ] Tôi có request ID/trace ID đáng tin và không để lộ dữ liệu nhạy cảm.
- [ ] Tôi phân biệt khả năng retry của 400, 401, 403, 409, 429, 503 và 504.
- [ ] Tôi có chiến lược idempotency khi POST có thể đã commit trước timeout.
- [ ] OpenAPI mô tả status, schema, header và security nhất quán.
- [ ] Tôi kiểm thử riêng từng tầng và end-to-end qua gateway.
- [ ] Tôi đo status/code/origin và kiểm soát client compatibility khi phát hành.

**Ghi nhớ:** Hợp đồng lỗi REST API là một phần của kiến trúc hệ thống. Application, security filter và gateway có thể khác công nghệ, nhưng phản hồi công khai nên có **cấu trúc thống nhất, status đúng nghĩa, header giao thức đầy đủ và mã truy vết rõ ràng**. Khi client hiểu lỗi và đội vận hành tìm được nguyên nhân, việc mở rộng, bảo mật và kiểm thử API trở nên đáng tin cậy hơn.

### Tài liệu chuẩn nên tra cứu

- **RFC 9457 – Problem Details for HTTP APIs:** các thành viên problem detail, type URI và extension.
- **RFC 9110 – HTTP Semantics:** status code, authentication challenges và Retry-After.
- **RFC 6750 – OAuth 2.0 Bearer Token Usage:** Bearer challenge và phản hồi lỗi auth.
- **OpenAPI Specification 3.1:** schemas, responses, headers, security schemes.
- **Spring Framework 6 / Spring Security 6:** ProblemDetail, ResponseEntityExceptionHandler, AuthenticationEntryPoint, AccessDeniedHandler, OAuth2 Resource Server.
