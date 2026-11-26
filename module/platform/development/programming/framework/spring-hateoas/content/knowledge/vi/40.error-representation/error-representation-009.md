# Không lộ stack trace

Stack trace rất hữu ích khi lập trình viên tìm nguyên nhân một lỗi, nhưng không phải dữ liệu dành cho client của REST API. Một stack trace có thể để lộ tên package, class, method, phiên bản thư viện, đường dẫn source code, cấu trúc database, địa chỉ service nội bộ hoặc một phần dữ liệu nhạy cảm nằm trong exception message. Nếu trả nguyên stack trace trong HTTP response production, API biến một lỗi vận hành thành nguồn thông tin cho người dò tìm điểm yếu của hệ thống.

Trong Spring HATEOAS, error response vẫn là một representation của API và cần có hợp đồng rõ ràng. Client cần biết status, loại lỗi, mã lỗi ổn định và cách xử lý tiếp theo. Client không cần biết dòng code nào đã ném exception hoặc server đang chạy ở thư mục nào. Hãy gửi thông tin an toàn qua HTTP, đồng thời ghi chi tiết kỹ thuật ở phía server với một mã tương quan để đội vận hành tra cứu.

## Vì sao stack trace không được xuất hiện trong response?

Một exception có thể chứa nhiều thông tin hơn dự kiến:

- Tên class và package tiết lộ framework, module hoặc thư viện đang được dùng.
- Stack frame để lộ cấu trúc source code, tên method và đường dẫn triển khai.
- SQL exception có thể tiết lộ tên bảng, cột, schema hoặc câu truy vấn.
- File exception có thể lộ đường dẫn nội bộ, tên mount hoặc cấu trúc thư mục.
- HTTP client exception có thể chứa hostname, URL nội bộ, port hoặc header.
- Message do thư viện tạo có thể chứa dữ liệu đầu vào, token, email hoặc thông tin cá nhân.
- Dependency version và thông tin runtime có thể giúp kẻ tấn công chọn khai thác đã biết.

Ví dụ response không an toàn:

~~~json
{
  "timestamp": "2026-11-26T10:15:30Z",
  "status": 500,
  "error": "Internal Server Error",
  "message": "could not execute statement; SQL [update orders set status=? where id=?]; relation orders does not exist",
  "exception": "org.springframework.jdbc.BadSqlGrammarException",
  "trace": [
    "org.springframework.jdbc.core.JdbcTemplate.update(JdbcTemplate.java:...)",
    "com.shop.order.OrderRepository.save(OrderRepository.java:87)",
    "com.shop.order.OrderController.approve(OrderController.java:42)"
  ],
  "path": "/api/orders/o-42/approval"
}
~~~

Client không cần SQL, tên class hay stack frame để xử lý lỗi 500. Những chi tiết đó nên được ghi vào log server có kiểm soát truy cập. Response công khai chỉ nên nói rằng server chưa thể xử lý request và cung cấp mã tham chiếu để hỗ trợ.

## Tách thông tin công khai và thông tin nội bộ

Thiết kế hai đầu ra riêng biệt:

| Nơi nhận | Thông tin phù hợp |
| --- | --- |
| HTTP response | HTTP status, problem type, title, detail an toàn, mã lỗi ổn định, request/incident ID và tài liệu công khai nếu có. |
| Server log / observability | Exception đầy đủ, stack trace, nguyên nhân gốc, trace ID, request ID, route và ngữ cảnh kỹ thuật đã được lọc nhạy cảm. |

Ví dụ response an toàn:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: req-7f4b2a

{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Lỗi máy chủ",
  "status": 500,
  "detail": "Máy chủ chưa thể xử lý yêu cầu. Vui lòng thử lại sau.",
  "instance": "urn:uuid:7b7a83a0-2bde-4f62-90aa-8e36dd6c74b4",
  "code": "INTERNAL_ERROR",
  "requestId": "req-7f4b2a"
}
~~~

Response vẫn đủ để client nhận biết lỗi, hỗ trợ ghi nhận sự cố và liên hệ đội vận hành. Nó không cho biết exception cụ thể, câu SQL hoặc tên method gây lỗi.

Mã lỗi như INTERNAL_ERROR là một phần của hợp đồng API. Hãy giữ mã ổn định qua các lần refactor nội bộ. Không dùng tên Java exception làm mã lỗi công khai vì tên class có thể thay đổi và không phải khái niệm nghiệp vụ.

## Dùng Problem Details của Spring Framework

Spring Framework 6 trở lên hỗ trợ kiểu **ProblemDetail** theo RFC 9457. Đây là mô hình chuẩn hóa lỗi HTTP với các thành phần chính:

| Field | Ý nghĩa |
| --- | --- |
| type | URI định danh loại problem; nên trỏ đến tài liệu mô tả lỗi. |
| title | Tên ngắn, ổn định của loại lỗi. |
| status | HTTP status tương ứng. |
| detail | Giải thích an toàn cho lần xảy ra lỗi cụ thể. |
| instance | URI định danh lần xảy ra lỗi cụ thể. |
| extension members | Thuộc tính bổ sung theo hợp đồng, ví dụ code hoặc requestId. |

Không đưa stack trace vào detail hoặc extension member. Đặc biệt, không thêm trường trace, exception, cause, sql hay debug chỉ để tiện cho client.

Ví dụ tạo problem đơn giản:

~~~java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy đơn hàng được yêu cầu.");

problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"));
problem.setTitle("Không tìm thấy tài nguyên");
problem.setProperty("code", "ORDER_NOT_FOUND");
~~~

Spring MVC có thể serialize ProblemDetail thành response Problem Details. Các thuộc tính bổ sung được đặt qua setProperty(...) được Jackson của Spring xử lý như extension members ở cấp JSON. Hãy thống nhất tên field và ý nghĩa của chúng trong hợp đồng API.

## Xử lý exception tập trung bằng @RestControllerAdvice

Không nên để mỗi controller tự tạo error JSON theo một cách. Một lớp advice tập trung giúp status, content type, mã lỗi và chính sách che giấu thông tin nhất quán.

Ví dụ dưới đây xử lý lỗi nghiệp vụ đã biết, lỗi validation và lỗi không dự kiến. Lỗi không dự kiến được ghi chi tiết ở server nhưng response chỉ có thông tin chung:

~~~java
import java.net.URI;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

@RestControllerAdvice
class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    private final RequestIdProvider requestIdProvider;

    ApiExceptionHandler(RequestIdProvider requestIdProvider) {
        this.requestIdProvider = requestIdProvider;
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng được yêu cầu.");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                "Một hoặc nhiều trường dữ liệu không hợp lệ.");
        problem.setType(URI.create(
                "https://api.example.com/problems/validation-failed"));
        problem.setTitle("Dữ liệu không hợp lệ");
        problem.setProperty("code", "VALIDATION_FAILED");

        return handleExceptionInternal(
                exception, problem, headers, status, request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {

        String requestId = requestIdProvider.currentOrCreate();
        log.error("Unhandled API error requestId={}", requestId, exception);

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Máy chủ chưa thể xử lý yêu cầu. Vui lòng thử lại sau.");
        problem.setType(URI.create(
                "https://api.example.com/problems/internal-error"));
        problem.setTitle("Lỗi máy chủ");
        problem.setInstance(URI.create("urn:uuid:" + UUID.randomUUID()));
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("requestId", requestId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .header("X-Request-Id", requestId)
                .body(problem);
    }
}
~~~

Trong ví dụ, OrderNotFoundException và RequestIdProvider là kiểu do ứng dụng định nghĩa. RequestIdProvider trả về một mã tương quan đã được xác thực định dạng hoặc tự sinh mới. Không đưa exception.getMessage() vào detail, vì message của exception có thể chứa dữ liệu nội bộ.

ResponseEntityExceptionHandler giúp tùy chỉnh các lỗi chuẩn do Spring MVC phát sinh, chẳng hạn lỗi binding và validation, mà vẫn giữ đúng HTTP status. Khi bổ sung handler cho các exception khác, hãy ánh xạ từng nhóm lỗi đã biết sang status phù hợp; handler Exception chỉ là nhánh dự phòng cho lỗi không dự kiến.

Không bắt Throwable để biến mọi tình huống runtime thành một response bình thường. Các lỗi JVM nghiêm trọng như OutOfMemoryError không nên bị xử lý như lỗi nghiệp vụ HTTP thông thường.

## Không trả exception message một cách tự động

Đoạn code sau nguy hiểm:

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> unsafe(Exception exception) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            exception.getMessage());
    return ResponseEntity.internalServerError().body(problem);
}
~~~

Exception message thường được viết cho lập trình viên hoặc do thư viện bên dưới tạo ra. Nó có thể chứa SQL, tên bảng, path, URL nội bộ, tham số đầu vào hoặc thông tin xác thực. Ngay cả khi message hiện tại có vẻ vô hại, dependency update có thể làm nội dung thay đổi.

Hãy dùng message công khai cố định hoặc message được chọn từ catalog theo mã lỗi. Nếu cần giải thích chi tiết cho một lỗi validation, chỉ trả tên field API và thông báo đã được kiểm soát; không serialize toàn bộ BindingResult, rejected value hoặc object request.

## Cấu hình Spring Boot để không đưa stack trace vào error attributes

Với Spring Boot, cấu hình error attributes mặc định theo hướng không tiết lộ thông tin:

~~~properties
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false
spring.mvc.problemdetails.enabled=true
~~~

Ý nghĩa:

- **include-stacktrace=never**: không thêm stack trace vào error response do cơ chế error attributes của Boot tạo ra.
- **include-message=never**: không đưa exception message vào error attributes.
- **include-binding-errors=never**: không xuất binding errors chi tiết mặc định.
- **include-exception=false**: không xuất tên exception.
- **problemdetails.enabled=true**: bật hỗ trợ Problem Details tự động cho các exception Spring MVC được hỗ trợ trong các phiên bản Spring Boot tương ứng.

Các thuộc tính này bảo vệ đường xử lý error attributes mặc định của Spring Boot. Chúng không thể ngăn một controller hoặc custom exception handler tự thêm stack trace vào JSON. Vì vậy, vẫn phải rà soát mọi nơi serialize exception và kiểm thử response thực tế.

Không bật include-stacktrace=always hoặc include-message=always trong production. Cấu hình on_param cũng cần tránh trên môi trường công khai: nếu client có thể yêu cầu stack trace qua query parameter, người ngoài có thể chủ động kích hoạt việc rò rỉ.

Nếu bật Problem Details tự động và đồng thời dùng @RestControllerAdvice riêng, hãy xác định rõ lớp nào xử lý từng nhóm exception. Tránh để built-in handler và custom handler tạo hai cấu trúc lỗi khác nhau cho cùng một loại lỗi.

## Giữ stack trace trong log server-side

Không trả stack trace cho client không có nghĩa là bỏ qua nguyên nhân lỗi. Với lỗi không dự kiến, log đầy đủ exception ở server và gắn request ID hoặc trace ID:

~~~java
log.error("Unhandled API error requestId={}", requestId, exception);
~~~

Logger nhận exception ở đối số cuối nên có thể ghi stack trace vào log backend. Chỉ người có quyền vận hành mới được truy cập log; áp dụng retention, phân quyền và quy trình bảo vệ log phù hợp.

Không ghi mù quáng mọi request header, cookie, Authorization header hoặc body. Stack trace an toàn hơn cho client nhưng log vẫn có thể chứa secret hoặc dữ liệu cá nhân nếu exception message được tạo từ dữ liệu đầu vào. Hãy lọc hoặc che các trường nhạy cảm và tránh log token.

Không log cùng một exception nhiều lần ở mọi tầng. Chọn một ranh giới xử lý lỗi không dự kiến để ghi stack trace đầy đủ; các tầng khác có thể truyền exception hoặc ghi event ngắn gọn với cùng request ID.

## Dùng request ID và trace ID để tra cứu

Client cần một mã tham chiếu có thể gửi cho đội hỗ trợ. Request ID nên được tạo ở gateway hoặc filter đầu vào, đưa vào logging context và trả về qua response header. Nếu request không có mã hợp lệ, server tự sinh mã mới. Không sao chép nguyên giá trị header do client cung cấp mà không kiểm tra độ dài và ký tự hợp lệ.

Một filter đơn giản minh họa việc gắn request ID vào MDC:

~~~java
import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestIdFilter extends OncePerRequestFilter {

    static final String HEADER = "X-Request-Id";
    static final String MDC_KEY = "requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY);
        }
    }
}
~~~

Ví dụ tạo request ID mới cho mỗi request để tránh tin cậy dữ liệu do client tự gửi. Trong hệ thống có gateway hoặc tracing infrastructure, có thể dùng trace context đã được xác thực và chuẩn hóa thay cho việc tạo ID độc lập. Phải xóa MDC trong finally để thread của servlet pool không mang ID của request trước sang request sau.

RequestIdProvider trong ví dụ advice nên đọc cùng giá trị MDC_KEY mà filter đã đặt; nếu không có request context, provider có thể tạo ID mới. Đặt filter trước Spring Security filter chain (ví dụ với order phù hợp như trong snippet) nếu muốn cả lỗi authentication/authorization cũng có request ID trong header và log.

Request ID và trace ID có vai trò khác nhau: request ID định danh một request trong hợp đồng hỗ trợ; trace ID nối các span qua nhiều service. Có thể đưa một hoặc cả hai vào log, nhưng không đưa toàn bộ trace/span metadata hoặc thông tin nội bộ vào error body.

## Những lỗi xảy ra trước controller

@RestControllerAdvice chỉ xử lý exception trong phạm vi cơ chế xử lý của Spring MVC. Một số lỗi xảy ra trước khi request đến controller:

- Authentication filter từ chối credential.
- Authorization filter chặn request.
- CSRF filter từ chối request.
- Gateway hoặc reverse proxy trả lỗi.
- Servlet container hoặc network layer phát sinh lỗi.

Các trường hợp này không nhất thiết đi qua controller advice. Hãy cấu hình AuthenticationEntryPoint và AccessDeniedHandler của Spring Security để dùng cùng Problem Details factory hoặc cùng chính sách response:

~~~java
http.exceptionHandling(errors -> errors
        .authenticationEntryPoint(problemAuthenticationEntryPoint)
        .accessDeniedHandler(problemAccessDeniedHandler));
~~~

AuthenticationEntryPoint thường trả 401 cho request chưa xác thực; AccessDeniedHandler trả 403 cho người đã xác thực nhưng không đủ quyền. Hai handler cần tránh trả exception message hoặc stack trace. Nếu gateway sở hữu lỗi upstream, gateway cũng phải áp dụng chính sách tương tự.

## Error representation và Spring HATEOAS

Error response vẫn có thể cung cấp thông tin điều hướng hữu ích, nhưng chỉ nên công bố link an toàn và có ý nghĩa với client. Ví dụ problem type có URI tài liệu công khai, hoặc một error contract riêng có relation help trỏ đến hướng dẫn xử lý.

Với ProblemDetail theo RFC 9457:

- Dùng type URI để định danh loại lỗi và trỏ đến tài liệu công khai.
- Dùng code extension để client nhận diện lỗi ổn định.
- Dùng requestId để người dùng gửi mã tra cứu cho bộ phận hỗ trợ.
- Chỉ thêm extension như retryAfter hoặc fieldErrors khi có hợp đồng rõ ràng và dữ liệu an toàn.
- Không thêm stackTrace, exceptionClass, internalUrl hoặc debugContext.

ProblemDetail không tự biến extension property thành HAL _links. Nếu API muốn trả error representation dạng HAL có _links, hãy định nghĩa một representation riêng kế thừa RepresentationModel và tài liệu hóa media type/hợp đồng đó. Không trộn tùy tiện hai định dạng application/problem+json và application/hal+json trong cùng response.

Một link help có thể dẫn đến trang tài liệu giải thích lỗi. Không đặt token, session ID hoặc URL quản trị nội bộ trong link. Link hướng dẫn cũng không nên tiết lộ resource mà người gọi không có quyền xem.

## Content negotiation cho lỗi

Nếu API dùng Problem Details, hãy thống nhất media type application/problem+json cho error response. Client có thể gửi Accept: application/hal+json cho response thành công; khi xảy ra lỗi, server vẫn cần một error contract được tài liệu hóa và nhất quán.

Không trả HTML error page hoặc trang whitelabel trong khi client mong đợi JSON. Kiểm thử cả request có Accept application/problem+json và request API thông thường để chắc chắn lỗi không làm lộ trang debug của container.

HTTP status phải phản ánh bản chất lỗi:

| Tình huống | Status thường dùng | Thông tin công khai |
| --- | --- | --- |
| Request không hợp lệ | 400 | Mã lỗi và mô tả validation an toàn. |
| Chưa xác thực | 401 | Thông tin challenge phù hợp, không có stack trace. |
| Không đủ quyền | 403 | Thông báo truy cập bị từ chối. |
| Không tìm thấy resource | 404 | Mã lỗi tài nguyên không tồn tại. |
| Xung đột trạng thái | 409 | Trạng thái hiện tại không cho phép thao tác. |
| Lỗi không dự kiến | 500 | Thông báo chung và request ID. |
| Dịch vụ phụ thuộc tạm thời không khả dụng | 503 | Thông báo thử lại sau; Retry-After nếu phù hợp. |

Không trả status 200 chỉ vì đã serialize được một object lỗi. Client, proxy và monitoring dựa vào status code để xử lý retry, circuit breaker và phân loại lỗi.

## Kiểm thử để bảo đảm stack trace không lọt ra ngoài

Kiểm thử không chỉ xác nhận status 500. Hãy kiểm tra body không chứa các trường hoặc chuỗi nội bộ, content type đúng và request ID có mặt.

Ví dụ MockMvc:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorDisclosureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void unexpectedFailureDoesNotExposeInternalDetails() throws Exception {
        mockMvc.perform(get("/api/test/fail")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isInternalServerError())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(header().exists("X-Request-Id"))
                .andExpect(jsonPath("$.type").exists())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.requestId").exists())
                .andExpect(content().string(not(containsString("stackTrace"))))
                .andExpect(content().string(not(containsString("java.lang."))))
                .andExpect(content().string(not(containsString("SQLException"))))
                .andExpect(content().string(not(containsString("password"))));
    }
}
~~~

Endpoint /api/test/fail là endpoint chỉ dành cho test, chủ động ném exception có message chứa chuỗi nhạy cảm. Không tạo endpoint chẩn đoán tương tự trong production. Có thể dùng controller test riêng hoặc mock service để kích hoạt lỗi mà không thêm route vào ứng dụng triển khai.

Nên có thêm các kiểm thử:

- Lỗi nghiệp vụ đã biết trả đúng status và mã lỗi, không lộ message nội bộ.
- Validation error không serialize rejected value hoặc toàn bộ object request.
- Lỗi 401/403 từ Spring Security cũng dùng error format an toàn.
- Response không chứa trace, exception, cause, stackTrace, SQL hoặc file path.
- Request ID giống nhau trong header và body, đồng thời xuất hiện trong log.
- Cấu hình production không bật include-stacktrace, include-message hoặc include-exception.
- Accept không phù hợp không làm response rơi về HTML debug page.

Trong test, dùng một exception có message cố ý chứa marker như SECRET_MARKER hoặc INTERNAL_SQL để chứng minh marker không xuất hiện trong response. Có thể dùng LogCaptor hoặc appender test để xác nhận stack trace được ghi server-side với request ID, nhưng không cần đưa log nội bộ vào assertion body.

## Những lỗi thường gặp

| Cách làm sai | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Trả exception.getMessage() trong detail | Message có thể chứa SQL, path hoặc dữ liệu đầu vào. | Dùng thông điệp công khai được kiểm soát. |
| Thêm stack trace vào extension field | Lộ class, method, dependency và source path. | Chỉ ghi stack trace trong log server. |
| Bật include-stacktrace=always | Error endpoint tiết lộ internals. | Đặt never trong production và kiểm thử cấu hình. |
| Chỉ dùng @RestControllerAdvice cho mọi lỗi | Lỗi filter/gateway có thể đi theo đường khác. | Cấu hình Security handlers và gateway error policy. |
| Trả tên Java exception làm error code | Hợp đồng phụ thuộc implementation và dễ thay đổi. | Dùng mã lỗi công khai ổn định. |
| Log toàn bộ request header/body | Có thể lưu token, cookie hoặc dữ liệu cá nhân. | Log có chọn lọc và che dữ liệu nhạy cảm. |
| Không có request ID | Khó tra cứu sự cố khi response chỉ có thông báo chung. | Sinh mã tương quan và đưa vào log/response. |
| Trộn Problem Details với HAL không có hợp đồng | Client không biết cách parse error links. | Chọn media type và schema lỗi rõ ràng. |

## Quy trình xử lý lỗi an toàn

Khi một exception xảy ra, luồng xử lý nên như sau:

1. Xác định nhóm lỗi và HTTP status phù hợp.
2. Với lỗi đã biết, tạo ProblemDetail theo mã lỗi công khai.
3. Với lỗi không dự kiến, sinh hoặc lấy request ID đã chuẩn hóa.
4. Ghi exception và stack trace vào log server-side có kiểm soát.
5. Tạo body chỉ gồm type, title, status, detail an toàn, instance và extension được cho phép.
6. Trả application/problem+json cùng request ID nếu hợp đồng quy định.
7. Kiểm thử body không chứa stack trace, exception message hoặc dữ liệu nội bộ.

## Nguyên tắc thiết kế

- Không bao giờ serialize exception, cause hoặc stack trace trực tiếp vào response production.
- Không dùng exception message làm detail nếu chưa được kiểm tra và chuyển đổi thành thông tin công khai.
- Dùng ProblemDetail/RFC 9457 để chuẩn hóa lỗi và giữ mã lỗi ổn định.
- Ghi stack trace server-side, có request ID/trace ID và kiểm soát quyền truy cập log.
- Đặt Spring Boot error inclusion settings ở chế độ không tiết lộ.
- Tùy chỉnh lỗi framework qua ResponseEntityExceptionHandler và lỗi nghiệp vụ qua @RestControllerAdvice.
- Cấu hình AuthenticationEntryPoint và AccessDeniedHandler cho lỗi phát sinh trong security filter chain.
- Chỉ công bố link tài liệu hoặc recovery link an toàn; không đưa credential hay internal URL vào error representation.
- Giữ error media type và HTTP status nhất quán.
- Kiểm thử cả response body, headers, security errors và log correlation.

Không lộ stack trace là một phần của thiết kế hợp đồng lỗi, không chỉ là một cấu hình tắt debug. Spring ProblemDetail giúp API trả thông tin có cấu trúc; @RestControllerAdvice tập trung hóa việc ánh xạ exception; Spring Boot error settings ngăn error attributes mặc định tiết lộ internals; logging và request ID vẫn giúp đội vận hành tìm nguyên nhân. Khi giữ ranh giới rõ giữa response công khai và log nội bộ, API vừa hữu ích cho client vừa hạn chế rò rỉ thông tin hệ thống.
