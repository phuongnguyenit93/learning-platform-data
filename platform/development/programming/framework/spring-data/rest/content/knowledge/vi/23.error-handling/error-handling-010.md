# Thông báo an toàn cho máy khách, mã theo dõi và chi tiết dành cho log

## 1. Vì sao cần tách thông báo cho client và log nội bộ?

Khi một request thất bại, hai nhóm người đọc cần những thông tin khác nhau:

- **Client** cần biết request bị từ chối vì lý do gì, có thể sửa dữ liệu hay thử lại hay không, và nên cung cấp mã nào khi liên hệ hỗ trợ.
- **Đội kỹ thuật** cần biết exception thực tế, stack trace, request/trace liên quan, service và bước xử lý đã thất bại để điều tra.

Nếu trả nguyên exception message, SQL, stack trace hoặc tên class nội bộ cho client, API có thể làm lộ cấu trúc hệ thống, tên bảng, đường dẫn file, thông tin kết nối hoặc dữ liệu nhạy cảm. Nếu log chỉ ghi “request failed” mà không có mã theo dõi, đội kỹ thuật lại khó tìm đúng request trong hàng triệu dòng log.

Một thiết kế tốt tách ba loại thông tin:

1. **Error code:** mã ổn định mô tả loại lỗi, ví dụ ORDER_STATE_CONFLICT.
2. **Request/correlation ID:** mã định danh một lần xử lý cụ thể, ví dụ 8f7d...; client có thể gửi mã này cho bộ phận hỗ trợ.
3. **Technical diagnostics:** exception class, stack trace, nguyên nhân gốc, trace/span và ngữ cảnh kỹ thuật chỉ lưu trong hệ thống log/tracing có kiểm soát quyền truy cập.

Error code có thể lặp lại ở nhiều request; request ID phải phân biệt từng lần xảy ra. Trace ID liên kết nhiều span qua các service trong cùng một distributed trace. Ba giá trị này có liên quan nhưng không thay thế nhau.

## 2. Nguyên tắc thiết kế error response

Response lỗi cần có cấu trúc ổn định, dễ đọc bằng máy và không phụ thuộc câu chữ của exception nội bộ.

Nên:

- Giữ HTTP status phản ánh đúng semantics của lỗi.
- Dùng error code ổn định để client xử lý bằng logic.
- Viết message ngắn, an toàn và giúp client biết bước tiếp theo.
- Chỉ trả field validation thực sự cần thiết để sửa request.
- Cung cấp request ID hoặc occurrence ID để hỗ trợ tra cứu.
- Giữ chi tiết debug, stack trace và nguyên nhân database trong log.
- Không yêu cầu client parse chuỗi detail để suy ra loại lỗi.

Không nên:

- Trả exception.getMessage() trực tiếp cho mọi exception.
- Trả stack trace, SQL, tên bảng/cột, hostname, đường dẫn file hoặc connection string.
- Trả access token, cookie, password, secret, dữ liệu cá nhân hoặc nội dung request nhạy cảm.
- Dùng HTTP 200 cho một request thất bại chỉ để đơn giản hóa frontend.
- Để field status trong body khác HTTP status thực tế.

## 3. Dùng Problem Details theo RFC 9457

RFC 9457 định nghĩa định dạng Problem Details cho HTTP API. JSON response dùng media type:

~~~~http
Content-Type: application/problem+json
~~~~

Các member chuẩn:

| Member | Ý nghĩa |
|---|---|
| type | URI nhận diện loại problem; nên ổn định và thuộc quyền kiểm soát của API |
| title | Tóm tắt ngắn về loại problem |
| status | HTTP status code của response |
| detail | Giải thích riêng cho lần xảy ra này, tập trung vào cách client xử lý |
| instance | URI reference nhận diện lần xảy ra problem cụ thể |

Có thể bổ sung extension member như code, requestId hoặc errors khi API định nghĩa rõ semantics của chúng.

Ví dụ một đơn hàng không thể xác nhận do đã được giao:

~~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-Id: 8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11
~~~~

~~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order cannot be confirmed",
  "status": 409,
  "detail": "This order has already been shipped. Refresh the order before continuing.",
  "instance": "urn:uuid:8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11",
  "code": "ORDER_STATE_CONFLICT",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

Client có thể dùng status để hiểu nhóm lỗi, code để chọn hành vi cụ thể và requestId để cung cấp cho support. detail là nội dung dành cho người đọc; không nên dùng nó làm protocol machine-readable.

instance nhận diện một occurrence cụ thể. Có thể dùng URI hoặc URN như urn:uuid:<id> nếu API không cung cấp endpoint tra cứu occurrence. Không đặt stack trace hoặc đường dẫn log vào instance.

## 4. Chọn HTTP status và error code nhất quán

HTTP status mô tả kết quả ở mức giao thức; error code mô tả nguyên nhân ở mức ứng dụng.

| HTTP status | Tình huống thường gặp | Ví dụ error code |
|---|---|---|
| 400 Bad Request | JSON malformed, binding thất bại hoặc request không hợp lệ | MALFORMED_REQUEST |
| 401 Unauthorized | Thiếu hoặc không có thông tin xác thực hợp lệ | AUTHENTICATION_REQUIRED |
| 403 Forbidden | Đã xác thực nhưng không được phép thực hiện thao tác | ACCESS_DENIED |
| 404 Not Found | Resource không tồn tại hoặc không được công bố cho caller | RESOURCE_NOT_FOUND |
| 409 Conflict | Thao tác xung đột với trạng thái hiện tại | ORDER_STATE_CONFLICT |
| 412 Precondition Failed | Điều kiện như If-Match không thỏa | PRECONDITION_FAILED |
| 422 Unprocessable Content | Request parse được nhưng dữ liệu không qua validation theo contract API | VALIDATION_FAILED |
| 429 Too Many Requests | Vượt giới hạn request | RATE_LIMIT_EXCEEDED |
| 500 Internal Server Error | Lỗi bất ngờ phía server | INTERNAL_ERROR |
| 503 Service Unavailable | Service tạm thời không sẵn sàng | SERVICE_UNAVAILABLE |

Đây là bảng định hướng, không phải quy tắc ép mọi ứng dụng phải dùng đúng một status cho mọi lỗi. Ví dụ, validation có thể trả 400 theo contract hiện có; hãy chọn một cách và giữ nhất quán. Khi response cho biết có thể thử lại, cân nhắc Retry-After với khoảng thời gian hợp lý.

Không biến mọi lỗi thành 500. Lỗi do client gửi dữ liệu sai, thiếu quyền hoặc xung đột trạng thái cần status phù hợp để client và proxy có thể xử lý đúng.

## 5. Những gì an toàn để trả về client

Thông tin có thể trả về tùy loại lỗi và chính sách dữ liệu:

- HTTP status và error code ổn định.
- Message ngắn giải thích hành động không thể thực hiện.
- Tên field bị lỗi và mã constraint, nếu không tiết lộ dữ liệu nhạy cảm.
- Giá trị giới hạn hoặc định dạng được phép, nếu hữu ích và an toàn.
- Request ID để bộ phận hỗ trợ tra cứu.
- Hướng xử lý tiếp theo, ví dụ tải lại resource hoặc đăng nhập lại.

Thông tin thường chỉ nên nằm trong log nội bộ:

- Stack trace đầy đủ và cause chain.
- SQL, tên schema/table, câu query đã bind.
- Đường dẫn file, thư mục tạm, hostname và cấu hình nội bộ.
- Tên class implementation hoặc package nội bộ.
- Access token, refresh token, cookie, password, API key và secret.
- Toàn bộ request body nếu có PII, thông tin thanh toán hoặc dữ liệu bí mật.
- Thông tin của người dùng hoặc tenant khác.

Ví dụ, thay vì trả:

~~~~json
{
  "message": "org.postgresql.util.PSQLException: duplicate key value violates unique constraint users_email_key at UserRepository.save(UserRepository.java:87)"
}
~~~~

hãy trả một lỗi nghiệp vụ ổn định:

~~~~json
{
  "type": "https://api.example.com/problems/email-already-registered",
  "title": "Email is already registered",
  "status": 409,
  "detail": "Use another email address or sign in to the existing account.",
  "code": "EMAIL_ALREADY_REGISTERED",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

Log nội bộ có thể ghi nguyên nhân unique constraint cùng request ID để kỹ thuật điều tra. Client không cần biết tên constraint hoặc tên repository.

## 6. Request ID, correlation ID và trace ID khác nhau thế nào?

| Giá trị | Phạm vi | Mục đích |
|---|---|---|
| Error code | Một loại lỗi | Client nhận diện lỗi và chọn hành vi |
| Request ID | Một HTTP request hoặc một lần xử lý | Tra cứu request cụ thể trong log |
| Correlation ID | Một luồng công việc có thể đi qua nhiều request/service | Liên kết các log event cùng một hoạt động |
| Trace ID | Một distributed trace | Nhóm các span qua nhiều service |
| Span ID | Một đơn vị công việc trong trace | Xác định một bước cụ thể trong trace |

Trong một ứng dụng đơn giản, request ID và correlation ID đôi khi được dùng chung. Trong hệ thống nhiều service, trace ID phù hợp để liên kết các span; request ID vẫn hữu ích để hỗ trợ một request tại API boundary.

Không dùng error code làm request ID. Ví dụ VALIDATION_FAILED có thể xuất hiện hàng nghìn lần, trong khi một request ID chỉ đại diện một occurrence.

Không xem request ID hoặc trace ID là credential. Biết mã này không được cấp quyền đọc log, truy cập resource hay lấy dữ liệu nội bộ.

## 7. Tạo và trả request ID

Nếu hệ thống chưa dùng tracing, có thể tạo request ID ở một servlet filter và đặt nó vào response header. Ví dụ:

~~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-Id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        MDC.put(ATTRIBUTE, requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(ATTRIBUTE);
        }
    }
}
~~~~

Ví dụ trên luôn tạo ID ở server. Nếu hệ thống cần nhận ID từ API gateway, chỉ chấp nhận header do gateway đáng tin cậy ghi đè; kiểm tra độ dài và ký tự hợp lệ, không cho phép newline hoặc control character. Không tin một giá trị tùy ý từ Internet rồi đưa thẳng vào log.

Đảm bảo filter chạy cho các request cần theo dõi và nằm trong thứ tự phù hợp với security/error handling. Nếu ứng dụng dùng async servlet hoặc executor, MDC không tự động luôn được truyền qua thread khác; cần cơ chế context propagation hoặc tracer phù hợp.

Nếu đã có Micrometer Tracing, ưu tiên dùng trace context do tracing system quản lý thay vì tự tạo một trace ID cạnh tranh. Có thể giữ request ID riêng cho API support và dùng traceId/spanId cho distributed tracing.

## 8. Đưa request ID vào ProblemDetail

Spring Framework hỗ trợ ProblemDetail cho RFC 9457. Có thể tạo một response có error code và request ID:

~~~~java
import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiProblemHandler {

    @ExceptionHandler(OrderStateConflictException.class)
    public ResponseEntity<ProblemDetail> handleOrderConflict(
            OrderStateConflictException exception,
            HttpServletRequest request) {

        String requestId = (String) request.getAttribute(
                RequestIdFilter.ATTRIBUTE
        );

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "This order cannot be changed in its current state."
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-state-conflict"
        ));
        problem.setTitle("Order state conflict");
        problem.setInstance(URI.create("urn:uuid:" + requestId));
        problem.setProperty("code", "ORDER_STATE_CONFLICT");
        problem.setProperty("requestId", requestId);

        return ResponseEntity.status(problem.getStatus())
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~~

Trong ví dụ, exception chỉ được dùng để xác định loại lỗi. Nội dung exception không được trả trực tiếp. Nếu exception chứa thông tin nội bộ, có thể ghi nó vào log theo policy ở phần sau.

ProblemDetail có thể mang extension property như code và requestId. Khi dùng Jackson theo cấu hình Spring Framework, các property extension được serialize ở cấp JSON object.

Đảm bảo requestId luôn có giá trị trước khi tạo ProblemDetail. Nếu filter không chạy ở một đường xử lý đặc biệt, dùng một occurrence ID mới làm fallback và bảo đảm ID đó cũng xuất hiện trong log.

## 9. Xử lý lỗi chuẩn của Spring MVC

Với Spring MVC, có thể trả ProblemDetail hoặc ErrorResponse từ method @ExceptionHandler hoặc controller method.

Trong Spring Boot, có thể bật Problem Details cho các exception web dựng sẵn bằng:

~~~~properties
spring.mvc.problemdetails.enabled=true
~~~~

Spring MVC cung cấp ResponseEntityExceptionHandler để xử lý các exception web chuẩn. Ứng dụng có thể mở rộng class này và bổ sung handler cho exception nghiệp vụ riêng, hoặc dùng @ControllerAdvice theo cấu trúc phù hợp với ứng dụng.

Ví dụ handler cho exception nghiệp vụ có thể trả ProblemDetail như phần trước. Với lỗi binding/validation, hãy giữ field path và mã constraint hữu ích nhưng không đưa raw value nhạy cảm vào response.

Không giả định bật property Problem Details tự động chuẩn hóa mọi exception của mọi thư viện. Hãy kiểm tra các exception của Spring MVC, Spring Security, Spring Data REST, persistence layer và custom service bằng integration test.

## 10. Lưu ý riêng với Spring Data REST

Spring Data REST có exception handling riêng cho repository exporter. API hiện hành cung cấp RepositoryRestExceptionHandler, là một @ControllerAdvice dành cho Spring Data REST controllers.

Điều này có hai hệ quả:

1. Một custom @RestControllerAdvice dùng cho controller MVC thông thường không nên được giả định là đã thay thế toàn bộ error handling của repository exporter.
2. Nếu cần một error contract thống nhất cho repository resources, phải kiểm tra exception resolver và handler thực tế của Spring Data REST trong phiên bản đang dùng.

RepositoryRestConfigurer có extension point configureExceptionHandlerExceptionResolver(ExceptionHandlerExceptionResolver). Có thể dùng điểm cấu hình này để tùy chỉnh exception resolver theo API của release train. Ví dụ khung:

~~~~java
@Configuration
public class RepositoryRestErrorConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureExceptionHandlerExceptionResolver(
            ExceptionHandlerExceptionResolver resolver) {

        // Đăng ký hoặc cấu hình resolver/handler phù hợp
        // với phiên bản Spring Data REST đang sử dụng.
    }
}
~~~~

Method trên nhận resolver mặc định của Spring Data REST; cách đăng ký handler cụ thể phụ thuộc resolver và phiên bản. Không sao chép cấu hình của Spring MVC vào đây mà chưa kiểm tra thứ tự và phạm vi handler.

Nếu cần custom endpoint nhưng vẫn muốn dùng cấu hình, message converters và exception handling của Spring Data REST, cân nhắc @RepositoryRestController thay vì một controller MVC hoàn toàn độc lập. Kiểm tra tài liệu overriding response handlers của phiên bản ứng dụng.

Với repository event validator, validation exception và lỗi persistence, hãy kiểm thử response thực tế. Đừng cho rằng tất cả đều trả application/problem+json chỉ vì ứng dụng đã bật spring.mvc.problemdetails.enabled.

## 11. Trả lỗi validation mà không lộ dữ liệu

Client cần biết field nào cần sửa. Có thể định nghĩa extension errors:

~~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields need correction.",
  "code": "VALIDATION_FAILED",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11",
  "errors": [
    {
      "field": "email",
      "code": "Email",
      "message": "Enter a valid email address."
    },
    {
      "field": "quantity",
      "code": "Positive",
      "message": "Quantity must be greater than zero."
    }
  ]
}
~~~~

Các error item nên chứa:

- Tên field hoặc JSON pointer.
- Mã lỗi ổn định, ví dụ NotBlank, Size hoặc mã domain riêng.
- Message an toàn và có thể được quốc tế hóa.

Không nhất thiết trả giá trị client đã gửi. Ví dụ không trả password, token, số thẻ hoặc toàn bộ object bị từ chối. Nếu API có nhu cầu hiển thị giá trị lỗi, hãy giới hạn rõ loại field được phép và cân nhắc masking.

Không để frontend phải phân tích câu tiếng Anh/tiếng Việt để biết field nào lỗi. Dùng field và code cho logic, message cho người dùng đọc.

## 12. Ghi log chi tiết dành cho kỹ thuật

Log server cần đủ ngữ cảnh để điều tra mà không ghi dữ liệu nhạy cảm.

Một log event có cấu trúc có thể gồm:

| Field | Ví dụ | Mục đích |
|---|---|---|
| timestamp | thời điểm UTC | Sắp xếp sự kiện |
| service | people-api | Xác định service |
| environment | production | Xác định môi trường |
| requestId | UUID | Tìm request từ mã client cung cấp |
| traceId / spanId | ID tracing | Liên kết các service và span |
| method | PATCH | HTTP method |
| route | /people/{id} | Route template, tránh log query string nhạy cảm |
| status | 409 | HTTP status |
| errorCode | ORDER_STATE_CONFLICT | Loại lỗi |
| exceptionType | class exception | Chẩn đoán nội bộ |
| durationMs | 38 | Thời gian xử lý |
| actorId | ID đã được policy cho phép | Ngữ cảnh người gọi nếu cần |

Ví dụ với SLF4J:

~~~~java
log.warn(
    "API request rejected requestId={} errorCode={} route={} status={}",
    requestId,
    "ORDER_STATE_CONFLICT",
    "/orders/{id}/confirm",
    409,
    exception
);
~~~~

Với lỗi bất ngờ 5xx, ghi exception cùng stack trace ở log nội bộ:

~~~~java
log.error(
    "Unexpected API failure requestId={} traceId={} route={}",
    requestId,
    traceId,
    routeTemplate,
    exception
);
~~~~

Chọn log level theo bản chất:

- Validation hoặc lỗi client dự kiến: thường INFO hoặc WARN tùy volume và policy.
- Business conflict lặp lại: WARN hoặc metric/counter; tránh tạo lượng stack trace lớn.
- Lỗi bất ngờ phía server: ERROR kèm exception.
- Debug chi tiết: chỉ bật có kiểm soát, không để lộ dữ liệu bí mật.

Log lỗi một lần ở ranh giới phù hợp. Nếu service, repository, filter và exception handler đều ghi cùng một stack trace, một request có thể tạo nhiều log event trùng lặp và làm khó điều tra.

## 13. Spring Boot và correlation ID trong log

Spring Boot tích hợp Micrometer Tracing có thể thêm correlation ID vào log mặc định. Correlation ID được xây dựng từ traceId và spanId trong MDC.

Ví dụ cấu hình Logback:

~~~~properties
logging.pattern.correlation=[%X{traceId:-},%X{spanId:-}]
~~~~

Log có thể hiển thị dạng:

~~~~text
[803B448A0489F84084905D3093480352,3425F23BB2432450] ERROR ...
~~~~

Spring Boot cũng hỗ trợ tùy chỉnh format correlation qua logging.pattern.correlation. Nếu dùng Micrometer Tracing, không cần tự tạo trace ID bằng UUID để thay thế trace context.

Để trace được truyền qua HTTP client, dùng các builder được Spring Boot auto-configure như RestClient.Builder, WebClient.Builder hoặc RestTemplateBuilder. Tự tạo client thủ công có thể làm mất automatic trace propagation nếu không cấu hình instrumentation tương ứng.

Nếu dùng async executor, message queue hoặc scheduler, kiểm tra context propagation để trace ID không bị mất hoặc rò sang task khác. MDC là thread-local context; không nên tự copy tùy tiện mà không dọn dẹp sau khi xử lý.

## 14. Log redaction và chống log injection

Log là một kho dữ liệu nhạy cảm. Cần kiểm soát cả nội dung lẫn cách đưa dữ liệu vào log.

- Không ghi Authorization, Cookie, Set-Cookie, password, API key, refresh token hoặc secret.
- Không ghi nguyên request body nếu có PII hoặc dữ liệu thanh toán.
- Mask hoặc loại bỏ email, số điện thoại, địa chỉ và định danh cá nhân khi không cần thiết.
- Tránh log query string có thể chứa token hoặc thông tin riêng tư.
- Không ghi nguyên header do client kiểm soát nếu chưa lọc.
- Chuẩn hóa newline/control character để dữ liệu đầu vào không giả mạo thêm log line.
- Giới hạn độ dài các giá trị log.
- Phân quyền truy cập log và đặt retention phù hợp.
- Không đưa stack trace lên endpoint hỗ trợ công khai.

Ví dụ nguy hiểm:

~~~~java
log.error("Request failed: " + request.getHeader("X-Request-Id"));
~~~~

Nếu header chứa newline, dữ liệu có thể làm sai cấu trúc log ở formatter không an toàn. Dùng structured logging hoặc placeholder, kiểm tra/chuẩn hóa giá trị và ưu tiên request ID do server tạo.

Một request ID không phải bí mật, nhưng vẫn cần giới hạn định dạng để tránh log injection và log flooding.

## 15. Dùng mã theo dõi khi trao đổi với bộ phận hỗ trợ

Client có thể nhận response:

~~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: 8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11
~~~~

~~~~json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Unexpected server error",
  "status": 500,
  "detail": "The request could not be completed. Contact support and provide the request ID.",
  "code": "INTERNAL_ERROR",
  "requestId": "8f7d8d5e-6e16-4bb0-9f3e-1a42dfe49c11"
}
~~~~

Khi khách hàng liên hệ hỗ trợ, họ cung cấp:

- Request ID.
- Thời điểm xảy ra và timezone.
- Endpoint hoặc thao tác họ đang thực hiện.
- HTTP status và error code.
- Mô tả ngắn các bước tái hiện, nếu phù hợp.

Nhân viên hỗ trợ dùng request ID để tìm log event và trace. Không yêu cầu khách hàng gửi access token, cookie, password hoặc toàn bộ dữ liệu cá nhân để debug.

Nếu hệ thống dùng trace ID làm mã hỗ trợ, hãy thống nhất cách hiển thị và chính sách chia sẻ. Một request ID riêng thường dễ dùng hơn cho API support; trace ID có thể giữ trong observability platform.

## 16. Kiểm thử error contract và logging

Kiểm thử không chỉ xác nhận status. Cần xác nhận body an toàn và có thể liên kết với log.

### Kiểm thử ProblemDetail

~~~~java
mockMvc.perform(post("/orders/42/confirm")
        .accept("application/problem+json"))
    .andExpect(status().isConflict())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON
    ))
    .andExpect(jsonPath("$.type").value(
            "https://api.example.com/problems/order-state-conflict"
    ))
    .andExpect(jsonPath("$.status").value(409))
    .andExpect(jsonPath("$.code").value(
            "ORDER_STATE_CONFLICT"
    ))
    .andExpect(jsonPath("$.requestId").isNotEmpty());
~~~~

### Kiểm tra bảo mật nội dung response

Xác nhận response không chứa:

- java.lang.* hoặc tên exception nội bộ.
- stackTrace, cause, SQL hoặc connection string.
- Authorization header, cookie, password hoặc secret.
- Raw request body có dữ liệu nhạy cảm.

Không chỉ kiểm tra bằng một chuỗi cố định; nên có test cho các exception đại diện như lỗi database, timeout và lỗi từ service bên ngoài.

### Kiểm tra liên kết request với log

- Request ID trong response header trùng request ID trong ProblemDetail.
- Cùng request ID xuất hiện trong log event liên quan.
- Trace ID/span ID được ghi khi tracing context có mặt.
- Một lỗi không tạo nhiều stack trace trùng lặp ngoài ý muốn.
- MDC được dọn sau request và không rò ID sang request tiếp theo.
- Request ID đầu vào không hợp lệ không được ghi thẳng vào log.
- Với Spring Data REST, test riêng endpoint repository và custom RepositoryRestController để xác nhận exception handler thực tế.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client nhìn thấy stack trace | Trả trực tiếp exception hoặc bật error detail quá rộng | Dùng ProblemDetail/message an toàn và log exception riêng |
| Support không tìm thấy request | Response không có request ID hoặc ID không được log | Tạo ID ở filter, trả header và ghi cùng ID trong log |
| Error code thay đổi theo exception message | Dùng message làm mã lỗi | Định nghĩa error code ổn định |
| HTTP status khác status trong JSON | Handler tự tạo body nhưng không đồng bộ response status | Dùng một nguồn status và test cả hai |
| Response MVC theo RFC 9457 nhưng repository REST không theo | Spring Data REST có exception handler riêng | Kiểm tra RepositoryRestExceptionHandler và resolver |
| Trace ID mất ở downstream service | HTTP client không được instrument hoặc context không propagate | Dùng builder auto-configured và kiểm tra tracing |
| MDC chứa ID của request trước | Không remove MDC trong finally hoặc context propagation sai | Dọn MDC và test thread reuse |
| Log chứa token/PII | Log toàn bộ request/header/body hoặc exception message không lọc | Redact theo allowlist và hạn chế dữ liệu |
| Một lỗi sinh quá nhiều stack trace | Nhiều lớp cùng log exception | Chọn một ranh giới log chính |
| Client gửi request ID giả mạo | Tin header tùy ý từ Internet | Tạo ID server-side hoặc chỉ tin gateway đã xác thực |
| Không tìm thấy log theo ID | Log aggregator không index field requestId | Dùng structured logging và index field cần tra cứu |
| 500 trả message quá chung chung | Không có mã theo dõi hoặc hướng liên hệ support | Thêm code và requestId an toàn |

## 18. Kết luận

Error response dành cho client cần ổn định, có HTTP status đúng, error code rõ ràng và message giúp xử lý tiếp. RFC 9457 Problem Details cung cấp các member type, title, status, detail và instance; có thể mở rộng bằng code, requestId và danh sách lỗi field. Phần detail nên hướng dẫn client sửa request hoặc liên hệ hỗ trợ, không chứa stack trace hay thông tin debug.

Request ID giúp tra một lần xử lý cụ thể; traceId/spanId liên kết công việc qua nhiều service; error code nhận diện loại lỗi. Trong Spring Boot, Micrometer Tracing có thể đưa correlation ID từ MDC vào log. Spring MVC hỗ trợ ProblemDetail qua exception handler; Spring Data REST có exception handling riêng nên cần xác nhận resolver và response contract trên repository endpoint thực tế.

Log nội bộ cần ghi đủ exception, stack trace và ngữ cảnh đã được lọc, trong khi response công khai chỉ chứa thông tin an toàn. Không log token, secret, raw body nhạy cảm hoặc dữ liệu không cần thiết. Hãy kiểm thử cả HTTP status, ProblemDetail, request ID trong response, khả năng tìm log và việc không rò rỉ dữ liệu nội bộ.

## Tài liệu tham khảo

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot — Tracing and Logging Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Data REST — RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/5.2/customizing/overriding-sdr-response-handlers.html)
