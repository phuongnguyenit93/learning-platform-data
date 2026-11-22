# Đồng bộ error contract với exception handler

## 1. Vì sao exception handler và tài liệu phải đồng bộ?

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Error response thường đi qua nhiều lớp: domain/service phát sinh exception, controller advice ánh xạ exception thành HTTP response, rồi REST Docs mô tả status, headers và payload.

Nếu các lớp này không thống nhất, tài liệu dễ sai:
- Service ném OrderNotFoundException nhưng advice trả 500 thay vì 404.
- Error body dùng code ORDER_MISSING trong khi tài liệu ghi ORDER_NOT_FOUND.
- Handler thêm timestamp hoặc correlationId nhưng descriptors không cập nhật.
- Nhiều handler cùng có thể xử lý exception và thứ tự ưu tiên không rõ.
- Validation error và domain error vô tình dùng chung status/code.
- Test chỉ kiểm tra body, bỏ qua status line và Content-Type.

Mục tiêu là có error contract ổn định, được thực thi bởi exception handler và kiểm chứng qua HTTP documentation tests. REST Docs không tự thiết kế error model; nó phát hiện sự lệch nhau giữa response thực tế và descriptor.

## 2. Xác định error contract trước khi viết handler

Một error contract cần xác định:

| Thành phần | Câu hỏi |
| --- | --- |
| HTTP status | Client nhận 400, 404, 409 hay 5xx? |
| Media type | application/problem+json hay schema riêng? |
| Error type/code | Mã ổn định nào để client xử lý? |
| Title/message | Thông điệp tổng quát nào được công bố? |
| Detail | Có đưa chi tiết cho lần xảy ra lỗi không? |
| Field violations | Validation lỗi biểu diễn theo path nào? |
| Correlation ID | Client dùng ID nào để liên hệ support? |
| Retry semantics | Có Retry-After hoặc hướng dẫn retry không? |
| Sensitive data | Field nào tuyệt đối không được trả? |

Ví dụ contract cho đơn hàng không tồn tại:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-Id: req-demo-42
```

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Không tìm thấy đơn hàng",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng ORD-42.",
  "code": "ORDER_NOT_FOUND",
  "correlationId": "req-demo-42"
}
```

HTTP status và field status trong Problem Details nên nhất quán nếu API đưa field này vào body. Code nên ổn định để client xử lý theo chương trình; detail có thể cụ thể cho từng lần xảy ra lỗi. Không dùng exception class name làm public error code vì đó là chi tiết implementation.

## 3. Phân tầng exception: domain error và HTTP error

Không nên để domain/service phụ thuộc HTTP status hoặc Spring MVC response type. Domain layer có thể ném exception có ý nghĩa nghiệp vụ:

```java
public class OrderNotFoundException extends RuntimeException {
    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Service sử dụng exception:

```java
@Service
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Order getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
```

Exception diễn đạt lỗi domain. Controller advice ánh xạ nó sang HTTP status, error code và response representation. Cùng một domain exception có thể được xử lý theo contract HTTP mà không buộc service biết ResponseEntity hay ProblemDetail.

Với lỗi có thể phục hồi hoặc là kết quả nghiệp vụ bình thường, cân nhắc result type thay vì exception. Không dùng exception làm cơ chế điều khiển mọi nhánh thông thường.

## 4. Dùng ProblemDetail trong @RestControllerAdvice

Spring Framework hỗ trợ ProblemDetail để biểu diễn Problem Details. Controller advice có thể ánh xạ domain exception:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đơn hàng " + exception.getOrderId() + ".");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

Standard members gồm type, title, status, detail và instance. Extension members như code có thể được thêm bằng setProperty. Cách serialize extension phụ thuộc cấu hình Spring/Jackson; kiểm tra JSON thực tế trong test.

Nếu cần correlationId, lấy từ request-scoped context hoặc request attribute do filter tạo. Không tạo ID độc lập trong advice nếu response header và log đang dùng nguồn khác.

### 4.1. Dùng schema riêng khi contract đã có

Không phải API nào cũng dùng Problem Details. Với schema riêng:

```java
record ApiError(String code, String message, String correlationId) {}

@RestControllerAdvice
class LegacyApiExceptionHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handle(OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Không tìm thấy đơn hàng.",
                        RequestIds.current()));
    }
}
```

Nếu API đã công bố envelope này, duy trì schema public hoặc lập migration/versioning có chủ đích. Không đổi schema chỉ để ví dụ giống chuẩn.

## 5. Ánh xạ nhiều exception theo một bảng thống nhất

| Exception/domain condition | HTTP status | Error code |
| --- | --- | --- |
| InvalidRequestException | 400 | INVALID_REQUEST |
| OrderNotFoundException | 404 | ORDER_NOT_FOUND |
| DuplicateOrderException | 409 | ORDER_ALREADY_EXISTS |
| InsufficientStockException | 409 | INSUFFICIENT_STOCK |
| UnauthenticatedException | 401 | UNAUTHENTICATED |
| AccessDeniedException | 403 | FORBIDDEN |
| RateLimitExceededException | 429 | RATE_LIMITED |
| Unexpected exception | 500 | INTERNAL_ERROR |

Đây là mapping ví dụ; status chính xác phụ thuộc semantics API. Lỗi tồn kho có thể dùng 409 hoặc status khác theo contract. Điều quan trọng là mapping nhất quán và có test.

Không trả message nội bộ của mọi exception cho client. Với lỗi 500, trả thông điệp chung và correlation ID; stack trace, SQL, filesystem path và dependency details chỉ ở log có kiểm soát.

## 6. Handler ưu tiên và exception hierarchy

Spring MVC chọn handler phù hợp theo exception type và cấu hình advice. Khi nhiều handler có thể xử lý cùng exception hierarchy, thứ tự advice và độ cụ thể của mapping ảnh hưởng kết quả.

- Dùng handler cụ thể cho domain exception.
- Có fallback handler cho lỗi không dự kiến.
- Định nghĩa rõ thứ tự advice nếu nhiều lớp cùng tham gia.
- Kiểm tra handler của framework, security và validation không bị custom advice che khuất.
- Không biến mọi exception thành 400; lỗi lập trình/dependency thường không phải client error.

Fallback minh họa:

```java
@ExceptionHandler(Exception.class)
ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {
    String correlationId = RequestIds.current();

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "Đã xảy ra lỗi hệ thống. Vui lòng liên hệ bộ phận hỗ trợ.");

    problem.setTitle("Lỗi hệ thống");
    problem.setType(URI.create(
            "https://api.example.com/problems/internal-error"));
    problem.setProperty("code", "INTERNAL_ERROR");
    problem.setProperty("correlationId", correlationId);

    // Ghi exception và correlationId vào log nội bộ có kiểm soát.
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .header("X-Request-Id", correlationId)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
}
```

Không ghi stack trace vào detail. Fallback phải tránh nuốt exception mà framework cần xử lý theo cơ chế riêng. Kiểm tra security filter chain, async errors và lỗi xảy ra trước DispatcherServlet.

## 7. Validation exception và domain exception

Validation lỗi thường đến từ request binding hoặc Bean Validation. Domain exception đến từ quy tắc nghiệp vụ sau khi request qua validation.

| Tình huống | Nhóm lỗi | Ví dụ |
| --- | --- | --- |
| Email sai format | Validation | 400 hoặc 422 theo contract |
| Đơn hàng không tồn tại | Domain | 404 |
| Đơn đã thanh toán nên không thể hủy | Domain/state conflict | 409 |
| Chưa đăng nhập | Authentication | 401 |
| Không đủ quyền | Authorization | 403 |

Không dùng cùng error code VALIDATION_ERROR cho lỗi nghiệp vụ. Client cần phân biệt field nào sai với trạng thái resource nào không cho phép thao tác.

Ví dụ validation payload:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request không hợp lệ",
  "status": 400,
  "code": "VALIDATION_ERROR",
  "violations": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email không đúng định dạng."
    }
  ]
}
```

Response not-found không cần violations. Vì payload shape khác nhau, dùng descriptor/snippet riêng theo error type.

## 8. Tái sử dụng descriptor có kiểm soát

Nếu các error response dùng chung schema Problem Details, có thể tạo helper descriptor cho standard fields:

```java
static FieldDescriptor[] problemDetailFields() {
    return new FieldDescriptor[] {
        fieldWithPath("type").description("URI loại vấn đề"),
        fieldWithPath("title").description("Tiêu đề lỗi"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Chi tiết lỗi"),
        fieldWithPath("instance").optional()
                .description("URI lần xảy ra vấn đề, nếu có")
    };
}
```

Sau đó bổ sung extension fields theo loại lỗi. Cần tự định nghĩa helper ghép array hoặc dùng cách ghép phù hợp Java:

```java
responseFields(
    concat(
        problemDetailFields(),
        new FieldDescriptor[] {
            fieldWithPath("code").description("Mã lỗi ổn định"),
            fieldWithPath("correlationId")
                    .description("Mã truy vết request")
        }
    )
)
```

Đây là minh họa ý tưởng; concat không phải helper mặc định của Spring REST Docs. Tránh abstraction quá tổng quát che khuất schema từng error type. Nếu optional fields khác nhau, descriptor riêng dễ đọc và an toàn hơn.

## 9. MockMvc test phải đi qua exception handler thật

Để kiểm chứng mapping, test nên dùng controller advice thật. Đừng chỉ mock response body rồi gọi document vì cách đó không kiểm tra exception mapping.

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderErrorDocumentationTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(WebApplicationContext context,
               RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentsOrderNotFound() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "ORD-42")
                        .accept(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404))
                .andDo(document("orders-get-not-found",
                        responseFields(
                                fieldWithPath("type").description("URI loại vấn đề"),
                                fieldWithPath("title").description("Tiêu đề lỗi"),
                                fieldWithPath("status").description("HTTP status"),
                                fieldWithPath("detail").description("Chi tiết lỗi"),
                                fieldWithPath("code").description("Mã lỗi"),
                                fieldWithPath("correlationId").optional()
                                        .description("Mã truy vết nếu có")
                        )));
    }
}
```

Ví dụ giả định application context chứa controller, service, advice và fixture cho order không tồn tại. Với standalone setup, phải đăng ký advice và các converter/validator cần thiết. Mục tiêu là exception thật đi qua handler thật trước khi REST Docs ghi response.

## 10. Kiểm tra status, headers và body

Error contract không chỉ là JSON body. Test cần xác minh status, media type, header và field:

```java
mockMvc.perform(get("/api/orders/{id}", "ORD-42"))
    .andExpect(status().isNotFound())
    .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.status").value(404))
    .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
```

Sau đó document những thành phần cần công bố:

```java
.andDo(document("orders-get-not-found",
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type của error response"),
        headerWithName("X-Request-Id")
            .description("Mã dùng để tra cứu request")
    ),
    responseFields(
        fieldWithPath("type").description("URI loại vấn đề"),
        fieldWithPath("title").description("Tiêu đề lỗi"),
        fieldWithPath("status").description("HTTP status"),
        fieldWithPath("detail").description("Chi tiết lỗi"),
        fieldWithPath("code").description("Mã lỗi ổn định"),
        fieldWithPath("correlationId").optional()
            .description("Mã truy vết trong error body nếu có")
    )
))
```

Không mô tả header optional nếu implementation bảo đảm luôn có; cũng không khai báo bắt buộc khi contract cho phép vắng mặt. Descriptor phải theo behavior thực.

## 11. Đồng bộ error code và message

Error code là identifier cho client logic; message/detail là nội dung giải thích. Không yêu cầu client parse message vì message có thể được bản địa hóa hoặc chỉnh sửa.

| Code | Ý nghĩa ổn định | Message có thể thay đổi? |
| --- | --- | --- |
| ORDER_NOT_FOUND | Không có order với ID yêu cầu | Có |
| ORDER_ALREADY_EXISTS | Order trùng khóa nghiệp vụ | Có |
| INSUFFICIENT_STOCK | Không đủ tồn kho | Có |
| VALIDATION_ERROR | Request không hợp lệ | Có |
| INTERNAL_ERROR | Lỗi hệ thống không dự kiến | Có |

Trong tài liệu, mô tả code như giá trị ổn định và detail như thông tin dành cho người đọc. Không đưa class name, SQL message hoặc stack trace vào error body public.

Nếu code thay đổi, đó là thay đổi contract cần review/versioning. Test nên assert code chính xác để phát hiện thay đổi ngoài ý muốn.

## 12. Lỗi không đi qua ControllerAdvice

Không phải tất cả lỗi đều đi qua RestControllerAdvice. Một số lỗi phát sinh trước controller:

- Authentication/authorization filter.
- Gateway hoặc reverse proxy.
- Request parsing và message converter.
- Servlet container hoặc network layer.
- Rate limiter hoặc API management layer.

Chỉ test controller advice chưa đủ để khẳng định mọi error response có cùng schema. Xác định boundary API và viết integration test cho lỗi client thực sự nhìn thấy. Nếu gateway tạo 429, tài liệu contract gateway cần bằng chứng riêng.

Với Spring Security, authentication entry point và access denied handler thường chịu trách nhiệm tạo response 401/403. Đồng bộ schema ở đó với controller advice hoặc mô tả rõ khác biệt. Không để cùng API trả hai envelope khác nhau mà không có lý do.

## 13. Tích hợp Asciidoctor và CI

Tổ chức snippet theo operation và error outcome:

```adoc
= Order API

== Lấy đơn hàng

=== Thành công
include::{snippets}/orders-get-success/http-response.adoc[]

=== Không tìm thấy
include::{snippets}/orders-get-not-found/http-response.adoc[]
include::{snippets}/orders-get-not-found/response-fields.adoc[]

=== Xung đột khi hủy
include::{snippets}/orders-cancel-conflict/http-response.adoc[]
include::{snippets}/orders-cancel-conflict/response-fields.adoc[]
```

Build cần chạy documentation tests trước Asciidoctor. CI nên fail nếu exception handler trả sai status/media type, error code không khớp contract, payload có field chưa được mô tả, correlation ID/header/body không nhất quán, snippet identifier trùng hoặc Asciidoctor include file không tồn tại.

Có test fallback 500 để bảo đảm response không chứa exception message nội bộ, trong khi log nội bộ vẫn giữ thông tin điều tra.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Domain exception trả 500 | Chưa có handler cụ thể | Thêm mapping và test status |
| Error code không khớp tài liệu | Mapping rải rác | Tập trung code và assert |
| Body status khác HTTP status | Handler đặt status/body độc lập | Dùng cùng mapping và kiểm tra cả hai |
| Validation và domain error dùng chung code | Schema thiếu phân loại | Tách error type/code |
| Advice không được gọi trong MockMvc | Setup không đăng ký advice/context | Dùng application context hoặc setControllerAdvice |
| Handler tổng quát che handler cụ thể | Hierarchy/ordering không rõ | Mapping cụ thể và test precedence |
| 401/403 khác schema | Security filter xử lý trước MVC | Đồng bộ entry point/access denied handler |
| responseFields báo thiếu field | Descriptor không theo response | Đồng bộ DTO/advice/descriptors |
| Field mới không bị phát hiện | Relaxed descriptors quá rộng | Dùng strict cho contract ổn định |
| Stack trace lộ trong body | Fallback trả exception message | Trả message chung, log nội bộ |
| Body đúng nhưng header sai | Chỉ assert JSON | Kiểm tra status, Content-Type, headers |
| Gateway error không có ID | Lỗi xảy ra trước application | Đưa contract vào gateway và test boundary |

## 15. Bài thực hành

Dùng API Order với lỗi not-found, conflict và validation:

1. Tạo domain exceptions OrderNotFoundException và OrderAlreadyCancelledException.
2. Xác định bảng mapping exception → HTTP status → error code.
3. Viết RestControllerAdvice trả Problem Details hoặc schema lỗi đã chọn.
4. Bảo đảm status trong body khớp HTTP status và error code ổn định.
5. Tạo MockMvc test dùng application context thật để exception đi qua advice.
6. Assert status, Content-Type, response header correlation ID và error body.
7. Dùng responseFields(...) mô tả từng error type; giữ strict mode cho contract public.
8. Thêm test fallback 500, xác nhận không lộ stack trace hoặc exception message.
9. Nếu dùng Spring Security, test riêng 401/403 từ entry point và access denied handler.
10. Include error snippets vào Asciidoctor; chạy documentation tests trước render.
11. Cố ý đổi error code trong handler để xác nhận test contract fail.
12. Review generated diff như thay đổi API contract, không chỉ thay đổi nội dung tài liệu.

**Tiêu chí hoàn thành:** bạn phân tầng domain exception và HTTP error mapping; đồng bộ controller advice, status, media type, error code và payload; kiểm chứng bằng MockMvc qua handler thật; tài liệu hóa response headers/fields; và đưa contract verification vào Asciidoctor/CI.

## Tài liệu tham khảo

- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): ánh xạ exception trong Spring MVC.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse và xử lý lỗi REST.
- [Spring REST Docs — Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/response-fields.html): mô tả và kiểm tra response payload fields.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): chuẩn error representation cho HTTP API.
