# Phân biệt lỗi kỹ thuật và lỗi nghiệp vụ

## 1. Vì sao phải phân biệt hai nhóm lỗi?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tài liệu lỗi**, các bài kiểm thử HTTP không chỉ mô tả response thành công mà còn cần ghi lại những trường hợp API từ chối request hoặc không thể hoàn tất xử lý. Tài liệu lỗi tốt giúp client biết họ cần sửa request, thay đổi luồng nghiệp vụ hay thử lại sau sự cố hệ thống.

Hai nhóm lỗi thường gặp:

- **Lỗi nghiệp vụ (business/domain error):** request hợp lệ về cú pháp và có thể đã được xác thực, nhưng không thỏa quy tắc domain. Ví dụ: không đủ hạn mức, đơn hàng đã giao nên không thể hủy, tài khoản bị khóa theo chính sách hoặc sản phẩm không còn khả dụng.
- **Lỗi kỹ thuật (technical/infrastructure error):** hệ thống không thể xử lý do hạ tầng, dependency hoặc lỗi triển khai. Ví dụ: database không truy cập được, service bên ngoài timeout, message broker ngừng hoạt động hoặc xuất hiện exception ngoài dự kiến.

Client xử lý hai nhóm theo cách khác nhau. Lỗi nghiệp vụ thường cần hiển thị cho người dùng hoặc điều chỉnh hành động; lỗi kỹ thuật có thể cần retry có kiểm soát, circuit breaker, fallback hoặc thông báo thử lại sau.

Trong Spring REST Docs, mỗi nhóm lỗi nên có test và snippet riêng. Test xác nhận HTTP status, header và payload lỗi thực tế; descriptor xác minh cấu trúc response để tài liệu không mô tả một error contract chưa được triển khai.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Với WebTestClient hoặc REST Assured, nguyên tắc kiểm tra tương tự dù API gửi request khác nhau.

## 2. Phân loại lỗi theo nguồn gốc và khả năng khắc phục

| Tiêu chí | Lỗi nghiệp vụ | Lỗi kỹ thuật |
| --- | --- | --- |
| Nguồn gốc | Quy tắc domain hoặc trạng thái tài nguyên | Hạ tầng, dependency, cấu hình hoặc bug |
| Request | Có thể hợp lệ về cú pháp | Có thể hợp lệ nhưng xử lý bị gián đoạn |
| Cách khắc phục | Thay đổi dữ liệu/hành động hoặc chờ điều kiện nghiệp vụ | Retry có kiểm soát, fallback hoặc xử lý sự cố |
| Ví dụ | INSUFFICIENT_BALANCE, ORDER_ALREADY_SHIPPED | DATABASE_UNAVAILABLE, UPSTREAM_TIMEOUT |
| HTTP status thường gặp | 400, 403, 404, 409, 422 tùy semantics | 500, 502, 503, 504 tùy nguyên nhân và vai trò gateway |
| Retry | Thường không retry nguyên request nếu điều kiện chưa đổi | Có thể retry nếu thao tác an toàn và lỗi tạm thời |

Không phân loại chỉ dựa vào tên exception. Cùng một exception kỹ thuật có thể được chuyển thành response khác tùy contract; cùng một lỗi nghiệp vụ có thể có nhiều HTTP status hợp lý tùy semantics. Hãy chọn status theo ý nghĩa HTTP và tài liệu hóa nhất quán.

Ví dụ lỗi nghiệp vụ:

- ORDER_ALREADY_SHIPPED: đơn hàng đã chuyển sang trạng thái không cho phép hủy.
- INSUFFICIENT_STOCK: số lượng tồn kho không đủ.
- ACCOUNT_SUSPENDED: tài khoản bị tạm khóa theo chính sách.
- DUPLICATE_RESOURCE: tài nguyên có khóa nghiệp vụ duy nhất đã tồn tại.

Ví dụ lỗi kỹ thuật:

- DATABASE_UNAVAILABLE: ứng dụng không kết nối được database.
- PAYMENT_PROVIDER_TIMEOUT: nhà cung cấp thanh toán không phản hồi đúng hạn.
- MESSAGE_BROKER_UNAVAILABLE: không thể gửi message tới broker.
- UNEXPECTED_ERROR: lỗi không dự kiến, cần điều tra bằng log/trace nội bộ.

Tên error code nên ổn định và không phụ thuộc class exception hoặc thông tin triển khai nội bộ. Client dựa vào code để quyết định luồng xử lý; con người đọc message để hiểu tình huống.

## 3. Chọn HTTP status phù hợp

| Status | Khi nào phù hợp |
| --- | --- |
| 400 Bad Request | Request không hợp lệ hoặc không thể phân tích |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực |
| 403 Forbidden | Đã xác thực nhưng không được phép thực hiện |
| 404 Not Found | Không tìm thấy tài nguyên hoặc endpoint |
| 409 Conflict | Xung đột với trạng thái hiện tại của tài nguyên |
| 422 Unprocessable Content | Nội dung được hiểu nhưng không thể xử lý theo quy tắc áp dụng |
| 429 Too Many Requests | Client vượt giới hạn request |
| 500 Internal Server Error | Lỗi không dự kiến trong xử lý của server |
| 502 Bad Gateway | Gateway/proxy nhận phản hồi không hợp lệ từ upstream |
| 503 Service Unavailable | Service tạm thời không thể phục vụ |
| 504 Gateway Timeout | Gateway/proxy không nhận được phản hồi upstream đúng hạn |

Không ánh xạ mọi lỗi nghiệp vụ thành 400 hoặc mọi lỗi kỹ thuật thành 500 một cách máy móc:

- Hủy đơn hàng đã giao có thể là 409 Conflict vì trạng thái hiện tại xung đột với hành động.
- Thiếu quyền có thể là 403 Forbidden.
- Không tìm thấy order có thể là 404 Not Found.
- Dependency tạm thời không khả dụng có thể là 503 Service Unavailable.
- Timeout khi ứng dụng đóng vai trò gateway có thể là 504 Gateway Timeout.

HTTP status và error code bổ sung cho nhau: status cho biết lớp kết quả giao thức; error code cho biết tình huống cụ thể trong contract của API.

## 4. Thiết kế error response ổn định

Với Spring Framework 6+, có thể dùng Problem Details theo RFC 9457. Media type chuẩn là application/problem+json. Ví dụ:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Không thể hủy đơn hàng",
  "status": 409,
  "detail": "Đơn hàng đã được giao.",
  "instance": "/api/orders/9001",
  "code": "ORDER_ALREADY_SHIPPED"
}
```

| Field | Ý nghĩa |
| --- | --- |
| type | URI định danh loại problem; nên ổn định |
| title | Tóm tắt ngắn gọn loại problem |
| status | HTTP status tương ứng |
| detail | Giải thích tình huống cụ thể cho response này |
| instance | URI tham chiếu tới lần xảy ra problem |
| code | Extension field do API định nghĩa để client xử lý ổn định |

code là extension của API, không phải field bắt buộc trong RFC 9457. Nên dùng code ổn định như ORDER_ALREADY_SHIPPED; không dùng tên class như OrderAlreadyShippedException làm public contract.

### Tách thông tin cho client và thông tin nội bộ

Public response nên chứa thông tin đủ để client hiểu và xử lý: error code ổn định, message không tiết lộ dữ liệu nhạy cảm, field validation bị lỗi nếu phù hợp và request/trace identifier để liên hệ bộ phận hỗ trợ.

Không đưa vào response công khai:

- Stack trace hoặc tên class exception.
- SQL query, tên bảng, schema hoặc connection string.
- Host nội bộ, IP private, tên pod/container hoặc topology.
- Token, cookie, secret hoặc thông tin xác thực.
- Nội dung exception từ dependency chưa được kiểm soát.

Chi tiết kỹ thuật nên ghi vào log/trace có kiểm soát truy cập. Response có thể cung cấp requestId để đội vận hành tìm log tương ứng.

## 5. Xây dựng business error trong Spring

### 5.1. Exception thuộc domain

```java
public class OrderAlreadyShippedException extends RuntimeException {
    public OrderAlreadyShippedException() {
        super("Order has already been shipped");
    }
}

public void cancelOrder(Order order) {
    if (order.isShipped()) {
        throw new OrderAlreadyShippedException();
    }
    order.cancel();
}
```

Exception biểu diễn quy tắc domain; controller advice chịu trách nhiệm chuyển nó thành HTTP response. Không để service phụ thuộc vào MockMvc hoặc Spring REST Docs.

### 5.2. Chuyển thành ProblemDetail

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderAlreadyShippedException.class)
    ResponseEntity<ProblemDetail> handleOrderAlreadyShipped(
            OrderAlreadyShippedException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Đơn hàng đã được giao nên không thể hủy."
        );
        problem.setType(URI.create(
            "https://api.example.test/problems/order-state-conflict"
        ));
        problem.setTitle("Không thể hủy đơn hàng");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "ORDER_ALREADY_SHIPPED");

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

Ví dụ minh họa cách ánh xạ exception sang response. Trong ứng dụng thật, có thể tập trung mapping trong một advice và dùng message source nếu cần đa ngôn ngữ. Không trả nguyên message từ exception nếu nó có thể chứa dữ liệu nội bộ.

## 6. Xử lý technical error

Technical error thường không nên để lộ nguyên nhân chi tiết ra client. Ví dụ dependency timeout:

```java
@ExceptionHandler(UpstreamTimeoutException.class)
ResponseEntity<ProblemDetail> handleUpstreamTimeout(
        UpstreamTimeoutException exception,
        HttpServletRequest request) {

    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau."
    );
    problem.setType(URI.create(
        "https://api.example.test/problems/dependency-unavailable"
    ));
    problem.setTitle("Dịch vụ tạm thời không khả dụng");
    problem.setInstance(URI.create(request.getRequestURI()));
    problem.setProperty("code", "UPSTREAM_UNAVAILABLE");
    problem.setProperty("requestId", requestIdFromContext());

    log.error("Upstream dependency timed out, requestId={}",
        requestIdFromContext(), exception);

    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(problem);
}
```

Client nhận message có thể hành động, không nhận stack trace. Log nội bộ giữ exception và context cần điều tra. Retry chỉ phù hợp khi thao tác an toàn, có giới hạn và không gây thực hiện trùng. Có thể trả Retry-After nếu API có chính sách retry rõ ràng.

Không chuyển mọi exception thành 503. Bug lập trình hoặc trạng thái không dự kiến thường cần 500; 503 phù hợp khi service tạm thời không thể phục vụ.

## 7. Kiểm thử và tài liệu hóa business error bằng MockMvc

Giả sử endpoint DELETE order trả Problem Details khi đơn đã giao:

```json
{
  "type": "https://api.example.test/problems/order-state-conflict",
  "title": "Không thể hủy đơn hàng",
  "status": 409,
  "detail": "Đơn hàng đã được giao nên không thể hủy.",
  "instance": "/api/orders/9001",
  "code": "ORDER_ALREADY_SHIPPED"
}
```

Test xác nhận status, content type, error code và các field:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderErrorDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void documentsOrderAlreadyShipped() throws Exception {
        doThrow(new OrderAlreadyShippedException())
            .when(orderService).cancel(9001L);

        mockMvc.perform(delete("/api/orders/{id}", 9001)
                .accept(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON
            ))
            .andExpect(jsonPath("$.code").value("ORDER_ALREADY_SHIPPED"))
            .andDo(document("orders-cancel-already-shipped",
                responseFields(
                    fieldWithPath("type").description("URI định danh loại problem"),
                    fieldWithPath("title").description("Tiêu đề lỗi"),
                    fieldWithPath("status").description("HTTP status"),
                    fieldWithPath("detail").description("Giải thích lỗi"),
                    fieldWithPath("instance").description("URI của request gây lỗi"),
                    fieldWithPath("code").description("Mã lỗi nghiệp vụ ổn định")
                )
            ));
    }
}
```

responseFields(...) tạo response-fields.adoc. Có thể thêm responseHeaders(...) để mô tả header quan trọng như Content-Type hoặc Retry-After nếu response thực sự trả header đó.

Với Spring Boot 3.4+ có thể dùng @MockitoBean; ở các phiên bản cũ hơn, @MockBean là cách thường gặp. Chọn annotation phù hợp với phiên bản Spring Boot của dự án.

## 8. Tài liệu hóa technical error

Technical error nên có operation ID riêng và payload public ổn định:

```java
@Test
void documentsDependencyUnavailable() throws Exception {
    doThrow(new UpstreamTimeoutException())
        .when(paymentService).charge(any());

    mockMvc.perform(post("/api/payments")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"orderId": 9001, "amount": 89.5}
                """)
            .accept(MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"))
        .andDo(document("payments-upstream-unavailable",
            responseFields(
                fieldWithPath("type").description("URI định danh loại problem"),
                fieldWithPath("title").description("Tiêu đề lỗi"),
                fieldWithPath("status").description("HTTP status"),
                fieldWithPath("detail").description("Thông báo cho client"),
                fieldWithPath("instance").description("URI request"),
                fieldWithPath("code").description("Mã lỗi kỹ thuật ổn định"),
                fieldWithPath("requestId").description("Mã tra cứu log hỗ trợ")
            )
        ));
}
```

Test không nên kỳ vọng payload chứa tên exception, stack trace hoặc thông tin endpoint nội bộ. Có thể bổ sung assertion:

```java
andExpect(jsonPath("$.stackTrace").doesNotExist())
andExpect(jsonPath("$.sql").doesNotExist())
```

Trong dự án thực tế, chọn field nhạy cảm phù hợp với error schema của ứng dụng. Assertion giúp ngăn thay đổi vô tình làm lộ thông tin trong response.

## 9. Validation error là contract riêng

Validation error thường là lỗi request, không nên đánh đồng với technical error. Ví dụ payload:

```json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường không hợp lệ.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email không đúng định dạng"
    }
  ]
}
```

Descriptor:

```java
responseFields(
    fieldWithPath("type").description("URI loại problem"),
    fieldWithPath("title").description("Tiêu đề lỗi"),
    fieldWithPath("status").description("HTTP status"),
    fieldWithPath("detail").description("Tóm tắt lỗi validation"),
    fieldWithPath("code").description("Mã lỗi validation"),
    fieldWithPath("errors[]").description("Danh sách lỗi theo field"),
    fieldWithPath("errors[].field").description("Tên field không hợp lệ"),
    fieldWithPath("errors[].code").description("Mã lỗi của field"),
    fieldWithPath("errors[].message").description("Thông báo lỗi của field")
)
```

Nếu API cho phép danh sách errors rỗng hoặc có cấu trúc khác giữa lỗi object và lỗi field, mô tả đúng schema thực tế. Có thể dùng subsectionWithPath(...) khi chỉ muốn mô tả errors như một nhóm; nếu client cần đọc từng lỗi field thì mô tả chi tiết.

## 10. Phân biệt lỗi trong tài liệu API

| Operation ID | HTTP status | Nhóm | Ý nghĩa |
| --- | --- | --- | --- |
| orders-cancel-already-shipped | 409 | Nghiệp vụ | Trạng thái đơn không cho phép hủy |
| orders-find-not-found | 404 | Nghiệp vụ/tài nguyên | Không tìm thấy đơn hàng |
| products-create-validation-failed | 400 hoặc 422 theo contract | Validation | Payload không thỏa validation |
| payments-upstream-unavailable | 503 | Kỹ thuật | Dependency tạm thời không khả dụng |
| orders-unexpected-error | 500 | Kỹ thuật | Lỗi server không dự kiến |

Không gộp mọi lỗi vào một operation error-response. Mỗi response variant có thể khác status, headers và fields. Tách operation ID giúp Asciidoctor include đúng ví dụ và giúp client hiểu khi nào từng lỗi xảy ra.

## 11. Include error snippets trong Asciidoctor

Ví dụ file src/docs/asciidoc/errors.adoc:

```asciidoc
= API Errors
:toc: left

== Hủy đơn hàng đã giao

=== HTTP response
include::{snippets}/orders-cancel-already-shipped/http-response.adoc[]

=== Response fields
include::{snippets}/orders-cancel-already-shipped/response-fields.adoc[]

== Dependency thanh toán không khả dụng

=== HTTP response
include::{snippets}/payments-upstream-unavailable/http-response.adoc[]

=== Response fields
include::{snippets}/payments-upstream-unavailable/response-fields.adoc[]
```

Attribute snippets phải trỏ tới thư mục gốc generated snippets. Operation ID trong include phải trùng với ID truyền vào document(...). Test cần chạy trước task Asciidoctor để snippet tồn tại.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Business error trả 500 | Exception domain chưa được map trong controller advice. | Ánh xạ exception sang status và Problem Details phù hợp. |
| Technical error trả 400 | Dùng chung handler cho mọi exception. | Phân loại lỗi theo nguồn gốc và semantics HTTP. |
| Client không phân biệt được lỗi | Chỉ có message tự do, không có error code ổn định. | Bổ sung extension code có contract rõ. |
| Response lộ stack trace hoặc SQL | Trả trực tiếp exception detail. | Redact response; giữ chi tiết trong log nội bộ. |
| Test không tạo response-fields snippet | Chưa gọi responseFields(...) hoặc response body sai schema. | Kiểm tra operation và payload thực tế. |
| Test lỗi vì thiếu field | Descriptor bắt buộc không có trong response variant. | Tách descriptor theo variant hoặc optional nếu contract cho phép. |
| Test bỏ sót lỗi mới | Dùng relaxedResponseFields quá rộng. | Giữ strict cho error schema chính và thu hẹp relaxed scope. |
| Asciidoctor không tìm thấy snippet | Sai operation ID hoặc outputDir. | Kiểm tra generated-snippets và include path. |

## 13. Bài thực hành

Tạo API Orders và Payments với các tình huống:

1. Hủy đơn đã giao trả 409 và code ORDER_ALREADY_SHIPPED.
2. Không tìm thấy đơn trả 404 và code ORDER_NOT_FOUND.
3. Payload validation thất bại trả 400 hoặc 422 theo contract, kèm danh sách field errors.
4. Payment provider timeout trả 503 và code UPSTREAM_UNAVAILABLE.

Thực hiện:

1. Tạo domain exception cho lỗi hủy đơn và exception mô phỏng timeout.
2. Dùng @RestControllerAdvice để chuyển lỗi thành Problem Details.
3. Viết MockMvc test xác nhận status, Content-Type, error code và response fields.
4. Kiểm tra response kỹ thuật không chứa stack trace, SQL hoặc secret.
5. Tạo operation ID riêng cho từng error variant.
6. Include HTTP response và response-fields snippets vào Asciidoctor.
7. Chạy clean test và dựng tài liệu; kiểm tra ví dụ lỗi phản ánh đúng contract hiện tại.

**Tiêu chí hoàn thành:** phân biệt được business/domain error, technical error và validation error; chọn HTTP status theo semantics; thiết kế error code ổn định; không rò rỉ thông tin nội bộ; sinh snippet lỗi bằng test và include được trong tài liệu.

## 14. Tài liệu tham khảo

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
