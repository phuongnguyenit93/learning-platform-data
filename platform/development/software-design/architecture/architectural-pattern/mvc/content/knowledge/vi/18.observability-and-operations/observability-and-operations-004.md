# Theo dõi tỷ lệ lỗi kỹ thuật và lỗi nghiệp vụ

Trong ứng dụng MVC, không phải mọi request có kết quả không thành công đều biểu thị hệ thống đang hỏng. Một người dùng có thể gửi biểu mẫu thiếu dữ liệu, cố hoàn thành công việc đã bị hủy hoặc đặt hàng vượt hạn mức. Đây là những kết quả nghiệp vụ được dự kiến và cần được phản hồi rõ ràng. Trong khi đó, database mất kết nối, dịch vụ thanh toán timeout hoặc lỗi lập trình không được xử lý có thể khiến use case không hoàn tất như cam kết. Đây là các lỗi kỹ thuật cần được theo dõi như tín hiệu về độ tin cậy của hệ thống.

Nếu gộp tất cả vào một con số “error rate”, dashboard có thể báo động liên tục khi người dùng nhập sai hoặc ngược lại che khuất lỗi hạ tầng bên trong nhiều response HTTP 200. Cần phân loại kết quả theo ý nghĩa nghiệp vụ và kỹ thuật, xác định mẫu số phù hợp cho từng tỷ lệ, rồi ghi nhận nhất quán tại ranh giới MVC và application service.

## Phân biệt lỗi kỹ thuật và lỗi nghiệp vụ

**Lỗi nghiệp vụ** xảy ra khi request được tiếp nhận và xử lý, nhưng hành động không được chấp nhận theo quy tắc của miền. Ví dụ: số dư không đủ, công việc không ở trạng thái cho phép hoàn thành, người nhận không thuộc dự án hoặc mã giảm giá đã hết hiệu lực. Những trường hợp này thường là kết quả hợp lệ của use case: hệ thống hoạt động đúng khi từ chối hành động.

**Lỗi kỹ thuật** xảy ra khi ứng dụng không thể hoàn thành hành động vì hạ tầng, phụ thuộc hoặc mã nguồn gặp sự cố. Ví dụ: database không khả dụng, connection pool cạn, API đối tác timeout, message broker từ chối kết nối, dữ liệu lưu trữ không đọc được hoặc xuất hiện exception ngoài dự kiến.

Ngoài hai nhóm trên, vận hành thường cần phân biệt thêm lỗi đầu vào, lỗi bảo mật và lỗi vận hành có chủ đích. Các nhóm này có thể được phân loại riêng để tránh làm sai tỷ lệ lỗi kỹ thuật.

| Nhóm kết quả | Ví dụ | Ý nghĩa vận hành |
|---|---|---|
| Thành công | Tạo công việc, thanh toán được xác nhận | Use case hoàn tất theo hợp đồng |
| Từ chối nghiệp vụ | Không đủ số dư, trạng thái không cho phép, vượt hạn mức | Quy tắc miền được áp dụng; thường không phải sự cố hệ thống |
| Đầu vào không hợp lệ | Thiếu trường bắt buộc, ngày không parse được, payload sai schema | Client cần sửa dữ liệu; theo dõi riêng để cải thiện hợp đồng/trải nghiệm |
| Không xác thực/không được phép | Token hết hạn, thiếu quyền trên tài nguyên | Sự kiện bảo mật; cần theo dõi nhưng không gộp mặc định vào lỗi kỹ thuật |
| Lỗi kỹ thuật phụ thuộc | Database, cache, email provider hoặc payment gateway lỗi | Có thể ảnh hưởng tính sẵn sàng và cần điều tra |
| Lỗi không dự kiến | Null pointer, lỗi mapping, invariant bị phá vỡ do bug | Dấu hiệu lỗi phần mềm cần ưu tiên xử lý |

Một lỗi chỉ có thể được phân loại đúng khi biết ngữ cảnh use case. HTTP status code một mình không đủ để kết luận. `409 Conflict` có thể biểu diễn một xung đột nghiệp vụ dự kiến; `404 Not Found` có thể là kết quả bình thường của truy vấn; `400 Bad Request` thường là đầu vào sai; và một API có thể trả HTTP 200 với body mô tả nghiệp vụ bị từ chối. Vì vậy, hãy ghi nhận outcome tại tầng ứng dụng, sau đó ánh xạ sang HTTP ở Controller.

## Vì sao cần theo dõi riêng từng tỷ lệ?

Tỷ lệ lỗi kỹ thuật trả lời câu hỏi: “Trong số những lần hệ thống cố thực hiện use case hoặc xử lý request thuộc phạm vi đo, bao nhiêu lần thất bại do sự cố kỹ thuật?” Đây là chỉ số quan trọng cho độ tin cậy và SLO.

Tỷ lệ từ chối nghiệp vụ trả lời câu hỏi khác: “Trong số những hành động đã được đánh giá theo quy tắc miền, bao nhiêu hành động bị từ chối?” Chỉ số này có thể phản ánh hành vi người dùng, thay đổi chính sách, dữ liệu đầu vào, gian lận hoặc một bất thường của sản phẩm. Nó không tự động có nghĩa hệ thống kém ổn định.

Ví dụ, một cửa hàng có thể có 12% yêu cầu thanh toán bị từ chối vì thẻ không hợp lệ hoặc ngân hàng không chấp thuận. Nếu cổng thanh toán và ứng dụng hoạt động bình thường, đây có thể là tỷ lệ nghiệp vụ. Nhưng nếu 8% yêu cầu timeout khi gọi cổng thanh toán, đó là lỗi kỹ thuật cần được điều tra.

Một dashboard nên trình bày các chỉ số riêng:

- tỷ lệ lỗi kỹ thuật theo request và theo use case;
- tỷ lệ từ chối nghiệp vụ theo use case và mã lý do;
- tỷ lệ lỗi đầu vào;
- tỷ lệ lỗi xác thực/phân quyền;
- tỷ lệ hoàn tất thành công;
- số lần thử và số kết quả cuối cùng nếu có retry.

## Xác định mẫu số trước khi tính tỷ lệ

Một tỷ lệ chỉ có ý nghĩa khi tử số và mẫu số được định nghĩa rõ. Không dùng cùng một mẫu số cho mọi loại lỗi nếu các nhóm request có phạm vi khác nhau.

### Tỷ lệ lỗi kỹ thuật ở cấp HTTP

Một định nghĩa phổ biến là:

\[
\text{Tỷ lệ lỗi kỹ thuật HTTP} =
\frac{\text{Request thất bại do lỗi kỹ thuật}}{\text{Request thuộc phạm vi đo}}
\times 100\%
\]

Mẫu số có thể loại trừ health check, request bị hủy bởi client hoặc route tĩnh nếu chúng không thuộc SLO của sản phẩm. Quy tắc loại trừ phải được ghi rõ và áp dụng nhất quán. Không nên xem mọi response 5xx là lỗi duy nhất hoặc mọi response 4xx là vô hại; cần phân loại theo nguyên nhân.

### Tỷ lệ lỗi kỹ thuật ở cấp use case

Với một use case như `submit_order`, có thể tính:

\[
\text{Tỷ lệ lỗi kỹ thuật use case} =
\frac{\text{Lần thực thi use case kết thúc vì lỗi kỹ thuật}}{\text{Tổng lần thực thi use case được ghi nhận}}
\times 100\%
\]

Một HTTP request có thể gọi nhiều use case, hoặc một use case có thể được gọi từ nhiều adapter. Vì vậy, tỷ lệ theo request và tỷ lệ theo use case là hai phép đo khác nhau; không thay thế hoặc cộng chúng với nhau.

### Tỷ lệ từ chối nghiệp vụ

\[
\text{Tỷ lệ từ chối nghiệp vụ} =
\frac{\text{Lần thực thi bị từ chối bởi quy tắc nghiệp vụ}}{\text{Lần thực thi được đánh giá theo quy tắc đó}}
\times 100\%
\]

Mẫu số cần phản ánh đúng các lần use case đã đến bước đánh giá quy tắc. Ví dụ, nếu đo tỷ lệ từ chối thanh toán do không đủ hạn mức, không nên đưa các request bị chặn ở bước xác thực hoặc lỗi parse JSON vào mẫu số. Nếu mẫu số quá rộng, tỷ lệ sẽ khó diễn giải.

### Ví dụ bằng số

Giả sử trong 10.000 lần gửi đơn hàng:

| Kết quả | Số lần |
|---|---:|
| Hoàn tất thành công | 8.900 |
| Bị từ chối do quy tắc nghiệp vụ | 700 |
| Lỗi kỹ thuật | 250 |
| Đầu vào không hợp lệ | 100 |
| Bị từ chối xác thực/phân quyền | 50 |
| **Tổng** | **10.000** |

Nếu tính trên toàn bộ lần gửi, tỷ lệ lỗi kỹ thuật là 2,5%; tỷ lệ từ chối nghiệp vụ là 7%. Hai tỷ lệ trả lời hai câu hỏi khác nhau. Nếu telemetry xác định chỉ có 9.650 lần thực sự đi đến bước đánh giá quy tắc, tỷ lệ từ chối nghiệp vụ là khoảng 7,25% (700 / 9.650). Mẫu số 9.650 phải đến từ counter/sự kiện tại đúng ranh giới đó; không tự suy ra nó từ tổng request nếu chưa biết các lỗi kỹ thuật xảy ra ở giai đoạn nào.

## Xây dựng mô hình phân loại outcome

Nên chuẩn hóa outcome thành một tập giá trị nhỏ và ổn định. Ví dụ:

```java
public enum ExecutionOutcome {
    SUCCESS,
    BUSINESS_REJECTED,
    INVALID_INPUT,
    UNAUTHENTICATED,
    FORBIDDEN,
    TECHNICAL_ERROR
}
```

Mã lý do nên là một enum hoặc mã ổn định khác, không dùng message exception tự do:

```java
public enum FailureCode {
    INSUFFICIENT_FUNDS,
    INVALID_TASK_STATE,
    QUOTA_EXCEEDED,
    DATABASE_UNAVAILABLE,
    PAYMENT_PROVIDER_TIMEOUT,
    UNEXPECTED_ERROR
}
```

Không phải mọi ứng dụng cần đúng các enum này. Hãy định nghĩa taxonomy theo miền và quy ước chung của hệ thống. Điều quan trọng là các outcome loại trừ nhau tại một ranh giới đo cụ thể, có ý nghĩa ổn định qua các phiên bản và có thể tổng hợp.

### Không phân loại chỉ dựa trên exception class chung

Một `RuntimeException` có thể đại diện cho lỗi kỹ thuật, lỗi nghiệp vụ do ứng dụng dùng exception để từ chối, hoặc bug không dự kiến. Ngược lại, lỗi nghiệp vụ có thể được biểu diễn bằng kiểu kết quả thay vì exception. Vì vậy, không nên viết một quy tắc đơn giản như “mọi exception là lỗi kỹ thuật” hoặc “mọi HTTP 4xx là lỗi nghiệp vụ”.

Hãy dùng kiểu lỗi miền có mã ổn định, exception hạ tầng đã được adapter chuẩn hóa và một nhánh fallback cho lỗi không dự kiến. Việc phân loại cần diễn ra nơi ứng dụng hiểu ý nghĩa của lỗi.

## Ghi nhận outcome tại ranh giới Application Service

Application service biết use case bắt đầu và kết thúc thế nào. Đây là nơi phù hợp để ghi nhận kết quả thực thi nghiệp vụ. Controller có thể đo request HTTP; repository hoặc adapter có thể đo lỗi kỹ thuật riêng của dependency; nhưng không nên để nhiều tầng cùng tăng một counter cho cùng một lần thực thi use case.

Ví dụ dùng Micrometer `Counter`:

```java
@Service
public class SubmitOrderService {
    private final OrderRepository orderRepository;
    private final MeterRegistry meterRegistry;

    public SubmitOrderService(
            OrderRepository orderRepository,
            MeterRegistry meterRegistry) {
        this.orderRepository = orderRepository;
        this.meterRegistry = meterRegistry;
    }

    public OrderId submit(SubmitOrderCommand command) {
        String outcome = "success";
        String reason = "none";

        try {
            Order order = Order.submit(command.customerId(), command.lines());
            orderRepository.save(order);
            return order.id();
        } catch (BusinessRuleViolation ex) {
            outcome = "business_rejected";
            reason = ex.code().metricKey();
            throw ex;
        } catch (PersistenceUnavailableException ex) {
            outcome = "technical_error";
            reason = "database";
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "technical_error";
            reason = "unexpected";
            throw ex;
        } finally {
            Counter.builder("mvc.usecase.executions")
                    .tag("use_case", "submit_order")
                    .tag("outcome", outcome)
                    .tag("reason", reason)
                    .register(meterRegistry)
                    .increment();
        }
    }
}
```

Đây là ví dụ minh họa; `BusinessRuleViolation`, `PersistenceUnavailableException`, `Order`, `OrderRepository` và `SubmitOrderCommand` là kiểu của ứng dụng cần được định nghĩa. Adapter persistence nên chuẩn hóa lỗi kết nối hoặc database không khả dụng thành `PersistenceUnavailableException`. Không phân loại mọi `DataAccessException` thành lỗi kỹ thuật một cách máy móc: lỗi unique constraint, optimistic-lock conflict hoặc dữ liệu vi phạm ràng buộc có thể cần được ánh xạ thành kết quả nghiệp vụ riêng. `metricKey()` phải trả về một giá trị cố định từ danh sách mã đã duyệt. Không dùng `ex.getMessage()` làm tag. Trong ứng dụng thực tế, nên tập trung phân loại exception qua một mapper/policy dùng chung nếu có nhiều use case, tránh các `catch` không nhất quán.

Counter trên đếm mỗi lần use case kết thúc đúng một lần. Nếu service ném lỗi lên Controller, `finally` vẫn ghi nhận outcome. Không tăng thêm một counter “use case failed” ở `@ControllerAdvice` cho cùng sự kiện; exception handler có thể ghi log/trace hoặc metric HTTP ở một ranh giới khác với tên và ý nghĩa riêng.

### Nếu dùng kiểu Result thay vì exception

Một số ứng dụng biểu diễn từ chối nghiệp vụ bằng kết quả tường minh:

```java
public sealed interface SubmitOrderResult {
    record Accepted(OrderId orderId) implements SubmitOrderResult {}
    record Rejected(FailureCode code) implements SubmitOrderResult {}
}
```

Application service có thể trả `Rejected(INSUFFICIENT_FUNDS)` như một outcome bình thường, sau đó metric ghi `business_rejected`. Lỗi database hoặc timeout vẫn có thể được ném dưới dạng exception kỹ thuật hoặc biểu diễn bằng nhánh lỗi riêng. Dù chọn exception hay Result, taxonomy cần nhất quán và Controller không được tự suy đoán ý nghĩa nghiệp vụ từ message.

## Ghi nhận lỗi kỹ thuật ở adapter và hạ tầng

Adapter biết lỗi nào phát sinh khi giao tiếp với hệ thống ngoài. Ví dụ, payment adapter có thể phân loại timeout, HTTP 429, HTTP 5xx, lỗi xác thực credential và lỗi từ chối thanh toán do ngân hàng. Các nhóm này không nên bị gộp vào một `RuntimeException` không có ngữ nghĩa.

```java
public enum DependencyFailure {
    TIMEOUT,
    UNAVAILABLE,
    RATE_LIMITED,
    AUTHENTICATION_CONFIG,
    INVALID_RESPONSE
}
```

Application service quyết định lỗi dependency ảnh hưởng thế nào đến use case. Ví dụ, email thông báo có thể được xếp hàng retry và không làm thất bại đăng ký; payment authorization có thể là điều kiện bắt buộc để đơn hàng chuyển trạng thái. Cùng một lỗi timeout ở hai use case có thể tạo ra outcome cuối cùng khác nhau.

Metric adapter nên theo dõi riêng dependency, operation và nhóm lỗi có số lượng giá trị hữu hạn. Ví dụ `dependency=payment_provider`, `operation=authorize`, `failure=timeout`. Không dùng hostname động, URL có token, customer ID hoặc nội dung response làm tag.

## Không đánh đồng HTTP status với phân loại nghiệp vụ

HTTP status code mô tả kết quả ở giao thức; taxonomy outcome mô tả kết quả use case. Controller hoặc exception handler ánh xạ từ một sang bên kia theo hợp đồng API.

| Outcome nội bộ | HTTP status có thể dùng | Lưu ý |
|---|---|---|
| Thành công khi tạo tài nguyên | 201 | Có thể trả `Location` |
| Thành công khi xử lý đồng bộ | 200 hoặc 204 | Tùy response contract |
| Đầu vào sai | 400 hoặc 422 | Chọn nhất quán theo API contract |
| Chưa xác thực | 401 | Với API có thể kèm `WWW-Authenticate` |
| Không đủ quyền | 403 hoặc 404 theo chính sách che giấu tài nguyên | Không tiết lộ dữ liệu ngoài quyền |
| Từ chối do trạng thái/tài nguyên xung đột | 409 | Không có nghĩa hệ thống bị lỗi kỹ thuật |
| Dependency/hệ thống không khả dụng | 503 hoặc 502 trong một số trường hợp | Chọn theo vai trò của ứng dụng và giao thức |
| Lỗi không dự kiến | 500 | Không trả stack trace hoặc chi tiết nội bộ |

Ví dụ, nếu người dùng gọi `POST /tasks/42/complete` khi công việc đã bị hủy, Controller có thể trả 409 cùng mã `TASK_STATE_INVALID`. Đây là business rejection. Nếu database mất kết nối trong cùng thao tác, ứng dụng có thể trả 503 hoặc 500 theo chính sách, đồng thời ghi nhận technical error. Cả hai request có thể không thành công từ góc nhìn người dùng, nhưng cần được đếm khác nhau.

## Ánh xạ lỗi tập trung trong Spring MVC

`@ControllerAdvice` giúp chuyển lỗi ứng dụng thành HTTP response thống nhất. Hãy dùng mã lỗi ổn định và thông điệp công khai đã được kiểm soát; không đưa message nội bộ hoặc stack trace trực tiếp ra client.

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BusinessRuleViolation.class)
    ResponseEntity<ProblemDetail> handleBusinessRule(
            BusinessRuleViolation ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.publicMessage());
        problem.setTitle("Không thể thực hiện thao tác");
        problem.setProperty("code", ex.code().name());
        problem.setProperty("category", "business");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

    @ExceptionHandler(PersistenceUnavailableException.class)
    ResponseEntity<ProblemDetail> handleStorageFailure() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau.");
        problem.setTitle("Không thể hoàn tất yêu cầu");
        problem.setProperty("code", "DEPENDENCY_UNAVAILABLE");
        problem.setProperty("category", "technical");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
```

Ví dụ dùng `ProblemDetail` của Spring Framework 6+. Mã thực tế cần import và điều chỉnh status theo hợp đồng hệ thống. Handler lỗi kỹ thuật nên log exception ở phía server với trace ID, nhưng response không nên chứa tên bảng, câu SQL, hostname nội bộ hoặc thông tin xác thực.

Metric use case nên được ghi tại application service; `@ControllerAdvice` chịu trách nhiệm ánh xạ giao thức và có thể ghi metric HTTP theo outcome response. Tránh tăng cùng một bộ đếm lỗi use case ở cả hai nơi.

## Thiết kế metric cho lỗi và từ chối

Một bộ metric nhỏ nhưng có định nghĩa rõ thường hữu ích hơn hàng chục counter trùng lặp.

| Metric gợi ý | Ý nghĩa | Tag có thể dùng |
|---|---|---|
| `mvc.usecase.executions` | Số lần use case kết thúc theo outcome | `use_case`, `outcome`, `reason` chuẩn hóa |
| `mvc.dependency.failures` | Số lỗi khi gọi dependency | `dependency`, `operation`, `failure` |
| `mvc.validation.rejections` | Số lần request bị từ chối do validation | `form` hoặc `endpoint` cố định, `field_group` chuẩn hóa |
| `mvc.security.denials` | Số lần request bị từ chối do quyền | `endpoint`/`policy` cố định, `reason` chuẩn hóa |
| `http.server.requests` | Số request và thời gian theo HTTP | method, URI template, status/outcome theo cấu hình |

Tên metric cụ thể cần tuân theo quy ước của dự án và backend. Micrometer có thể chuyển tên metric sang dạng khác khi export, ví dụ dấu chấm thành dấu gạch dưới và thêm hậu tố counter tùy registry. Hãy kiểm tra tên thực tế trên endpoint metrics trước khi viết dashboard/query.

### Cardinality và dữ liệu nhạy cảm

Tag metric phải có số lượng giá trị hữu hạn. Những tag thường phù hợp gồm `outcome=success|business_rejected|technical_error`, `reason=quota_exceeded|invalid_state|database` và `use_case=submit_order|complete_task`.

Không dùng các giá trị sau làm tag:

- user ID, email, số điện thoại, tenant ID hoặc customer ID;
- exception message, stack trace hoặc nội dung request;
- SQL thô, bind parameter, tên tệp hoặc URL có query string;
- mã giao dịch duy nhất hoặc provider request ID;
- giá trị do client tự nhập có thể có số lượng vô hạn.

Những dữ liệu này vừa tạo cardinality cao vừa có nguy cơ làm lộ thông tin. Nếu cần tìm một giao dịch cụ thể, dùng log/trace đã kiểm soát quyền truy cập và retention, không dùng metric tag.

## Tính tỷ lệ từ counter

Giả sử backend Prometheus export các counter Micrometer thành metric có hậu tố `_total`. Tỷ lệ lỗi kỹ thuật của một use case có thể được tính bằng:

```promql
sum(rate(mvc_usecase_executions_total{
  use_case="submit_order",
  outcome="technical_error"
}[5m]))
/
clamp_min(sum(rate(mvc_usecase_executions_total{
  use_case="submit_order"
}[5m])), 1)
```

Query minh họa dùng `rate()` để tính tốc độ tăng counter trong cửa sổ 5 phút và `clamp_min` để tránh chia cho 0. Tên metric thực tế phụ thuộc cấu hình registry/exporter. Nếu muốn tỷ lệ theo số lần thử cuối cùng thay vì mọi attempt, cần xác định cách ghi nhận retry trước khi xây query.

Tỷ lệ từ chối nghiệp vụ có thể dùng cùng counter nhưng lọc `outcome="business_rejected"`. Hãy đặt tên panel rõ ràng, ví dụ “Tỷ lệ lỗi kỹ thuật” và “Tỷ lệ từ chối nghiệp vụ”, không đặt chung “Error rate” nếu người xem không biết tử số bao gồm những gì.

### Không trộn attempt với kết quả cuối cùng

Một request có thể thử lại dependency nhiều lần. Nếu mỗi lần retry đều được tính là một lần thực thi use case, tỷ lệ lỗi có thể bị phóng đại hoặc làm sai mẫu số. Nên tách:

- số lần thực thi use case;
- số lần gọi dependency/attempt;
- số lần retry;
- kết quả cuối cùng của use case;
- số công việc được đưa vào hàng đợi xử lý sau.

Ví dụ, một lần `submit_order` gọi payment provider ba lần: hai lần timeout tạm thời, lần cuối thành công. Metric dependency ghi hai timeout và một success; metric use case ghi một lần thành công nếu hợp đồng use case chỉ có một lần thực thi. Nếu request cuối cùng thất bại, use case ghi một technical error. Cách ghi nhận phải được thống nhất để dashboard không đếm một lần hành động thành nhiều lần thất bại.

## Tỷ lệ lỗi theo route và theo use case

Một endpoint có thể gọi nhiều use case hoặc một use case có thể được dùng từ nhiều endpoint. Hãy giữ hai góc nhìn:

- **HTTP route:** giúp phát hiện endpoint có tỷ lệ 5xx, timeout hoặc lỗi giao thức tăng.
- **Use case:** giúp phát hiện hành động nghiệp vụ nào gặp lỗi kỹ thuật hoặc bị từ chối bất thường, bất kể adapter gọi nó.

Ví dụ, `POST /api/orders` và `POST /checkout` có thể cùng gọi `submit_order`. Nếu chỉ đo route, nhóm vận hành phải so sánh hai biểu đồ để nhận ra cùng một use case đang lỗi. Metric use case làm lộ vấn đề chung; metric route vẫn cần để thấy tác động ở từng kênh.

Không cộng số request route với số lần use case để tạo một tỷ lệ tổng hợp. Một request có thể không gọi use case nào, gọi một use case hoặc gọi nhiều use case. Chọn đúng đơn vị quan sát trước khi tổng hợp.

## Dashboard theo từng loại kết quả

Dashboard nên tách độ tin cậy kỹ thuật khỏi hành vi nghiệp vụ:

| Khu vực | Biểu đồ/chỉ số | Mục đích |
|---|---|---|
| Độ tin cậy HTTP | Request rate, 5xx rate, timeout, p95/p99 theo route | Nhìn tác động trực tiếp của hệ thống web |
| Use case | Executions, success rate, technical error rate theo use case | Xác định hành động ứng dụng bị ảnh hưởng |
| Business rejection | Rejection rate theo mã lý do và use case | Phát hiện thay đổi hành vi hoặc chính sách |
| Validation | Số lỗi đầu vào theo form/endpoint và nhóm trường | Tìm hợp đồng khó hiểu hoặc UX gây lỗi |
| Security | 401/403, denial theo policy và xu hướng bất thường | Theo dõi truy cập bị từ chối và dấu hiệu lạm dụng |
| Dependency | Timeout, 429, 5xx và latency theo provider | Xác định dịch vụ ngoài gây lỗi |
| Retry/async | Attempt, retry, queue depth và job cuối cùng | Phát hiện retry storm hoặc backlog |

Có thể hiển thị tỷ lệ từ chối nghiệp vụ cạnh số lượng hành động thành công để người vận hành hiểu bối cảnh. Tuy nhiên, không dùng tỷ lệ từ chối cao làm cảnh báo sự cố ngay lập tức nếu nghiệp vụ vốn có nhiều trường hợp từ chối bình thường.

## Cảnh báo lỗi kỹ thuật và bất thường nghiệp vụ

### Cảnh báo kỹ thuật

Alert kỹ thuật nên gắn với tác động đến khả năng hoàn tất request hoặc SLO:

- tỷ lệ lỗi kỹ thuật của use case quan trọng vượt ngưỡng trong một cửa sổ ổn định;
- HTTP 5xx tăng cùng lúc với p95/p99 tăng;
- database timeout hoặc connection pool pending tăng;
- dependency quan trọng có tỷ lệ timeout/5xx cao;
- số lỗi không dự kiến tăng đột ngột;
- queue backlog hoặc tuổi công việc chờ vượt giới hạn.

Với SLO, có thể dùng error budget và burn rate để xác định tốc độ tiêu hao ngân sách lỗi. Alert nên liên kết đến dashboard, trace mẫu, log có cùng trace ID và runbook xử lý.

### Theo dõi bất thường nghiệp vụ

Business rejection thường không cần page trực ca. Nhưng thay đổi bất thường có thể báo hiệu một vấn đề sản phẩm hoặc tích hợp:

- tỷ lệ `INSUFFICIENT_FUNDS` tăng đột ngột do dữ liệu hoặc luồng thanh toán;
- `QUOTA_EXCEEDED` tăng sau khi thay đổi cấu hình hạn mức;
- `INVALID_TASK_STATE` tăng sau khi phát hành UI mới;
- tỷ lệ coupon hết hạn tăng do cache hoặc đồng bộ thời gian;
- tỷ lệ từ chối của một nhóm tenant thay đổi khác thường.

Những cảnh báo này có thể gửi đến nhóm sản phẩm, nghiệp vụ hoặc đội vận hành theo mức độ. Trước khi kết luận có bug, cần xem thay đổi lưu lượng, chiến dịch, chính sách, phân khúc người dùng và dữ liệu đầu vào.

### Tránh alert gây nhiễu

- Không page cho từng lần người dùng nhập sai một trường.
- Không cảnh báo chỉ vì một mã business rejection có số lượng cao nếu đó là hành vi bình thường.
- Không gộp lỗi xác thực, validation và dependency thành một tỷ lệ không có định nghĩa.
- Dùng ngưỡng theo baseline, cửa sổ thời gian và số lượng tối thiểu để tránh mẫu số quá nhỏ.
- Với tỷ lệ thấp nhưng hậu quả lớn, theo dõi cả số tuyệt đối và tỷ lệ.

## Log và trace cho từng loại lỗi

Metric cho biết tần suất; log và trace giúp giải thích từng sự kiện. Khi ghi lỗi, nên có các trường:

- tên use case hoặc route template;
- outcome và mã lỗi chuẩn hóa;
- trace ID/correlation ID;
- dependency hoặc operation liên quan nếu có;
- thời gian, môi trường và instance;
- trạng thái retry hoặc attempt nếu cần.

Với business rejection thông thường, có thể ghi log ở mức `INFO` hoặc metric mà không cần stack trace. Không log stack trace cho mọi lần người dùng nhập sai hoặc vi phạm quy tắc bình thường; điều đó tạo nhiễu và tăng chi phí.

Với lỗi kỹ thuật, log exception ở mức phù hợp và giữ stack trace phía server. Với lỗi không dự kiến, cần đủ ngữ cảnh để điều tra nhưng không đưa token, mật khẩu, session ID, dữ liệu cá nhân hoặc payload nhạy cảm vào log.

Trace có thể đánh dấu span theo outcome và error type. Tuy nhiên, không thêm message hoặc ID người dùng vào span attribute có cardinality cao. Nếu business rejection là kết quả được dự kiến, hãy cân nhắc biểu diễn nó như outcome/attribute thay vì đánh dấu toàn bộ distributed trace là lỗi hệ thống; cách đánh dấu phải nhất quán với quy ước tracing của đội.

## Xử lý retry đúng với loại lỗi

Không phải lỗi nào cũng nên retry:

| Loại lỗi | Retry có phù hợp? | Lý do |
|---|---|---|
| Validation không hợp lệ | Không | Dữ liệu cần được sửa |
| Business rule rejection | Thường không | Thử lại cùng dữ liệu thường vẫn bị từ chối |
| Không đủ quyền | Không | Cần thay đổi quyền hoặc danh tính hợp lệ |
| Timeout/lỗi mạng tạm thời | Có điều kiện | Chỉ retry khi thao tác an toàn hoặc có idempotency |
| HTTP 429/503 từ dependency | Có điều kiện | Tôn trọng `Retry-After`, backoff và giới hạn retry |
| Lỗi cấu hình/credential | Không retry liên tục | Cần sửa cấu hình hoặc secret |
| Bug không dự kiến | Không tự retry mặc định | Có thể lặp lỗi, tăng tải và che giấu nguyên nhân |

Retry cần exponential backoff, jitter, deadline và giới hạn số lần. Với thao tác ghi như tạo thanh toán, dùng idempotency key hoặc cơ chế chống xử lý trùng. Nếu không, một timeout không rõ kết quả có thể khiến request được thực hiện hai lần.

Theo dõi cả attempt và kết quả cuối cùng để nhận ra retry storm. Một dependency có thể có tỷ lệ thành công cuối cùng cao nhưng số lần retry tăng mạnh, làm tăng tải và kéo dài latency.

## Kiểm thử phân loại và metric

Kiểm thử cần xác minh lỗi được phân loại đúng, counter chỉ tăng đúng một lần và response HTTP phù hợp.

### Unit test phân loại outcome

Nếu dùng mapper, có thể kiểm thử bảng ánh xạ:

| Lỗi | Outcome kỳ vọng | Reason kỳ vọng |
|---|---|---|
| `BusinessRuleViolation(QUOTA_EXCEEDED)` | `business_rejected` | `quota_exceeded` |
| `PersistenceUnavailableException` | `technical_error` | `database` |
| Payment timeout đã chuẩn hóa | `technical_error` | `payment_timeout` |
| Lỗi validation | `invalid_input` | `validation` |
| Lỗi không dự kiến | `technical_error` | `unexpected` |

Không dựa vào nội dung message để phân loại. Test nên dùng mã lỗi ổn định và xác minh mọi nhánh được bao phủ.

### Kiểm thử Counter với SimpleMeterRegistry

Micrometer cung cấp `SimpleMeterRegistry` để kiểm thử metric trong bộ nhớ:

```java
class SubmitOrderServiceTest {
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final OrderRepository repository = mock(OrderRepository.class);
    private final SubmitOrderService service =
            new SubmitOrderService(repository, registry);

    @Test
    void countsBusinessRejectionOnce() {
        assertThatThrownBy(() -> service.submit(commandExceedingQuota()))
                .isInstanceOf(BusinessRuleViolation.class);

        verifyNoInteractions(repository);

        Counter counter = registry.get("mvc.usecase.executions")
                .tag("use_case", "submit_order")
                .tag("outcome", "business_rejected")
                .tag("reason", "quota_exceeded")
                .counter();

        assertThat(counter.count()).isEqualTo(1.0);
    }
}
```

Đây là phác thảo test; `commandExceedingQuota()` cần tạo dữ liệu khiến Model hoặc policy từ chối trước khi lưu. `verifyNoInteractions` xác minh repository không được gọi sau khi quy tắc đã từ chối. Không mock entity đang kiểm thử; chỉ mock port hoặc dependency ở ranh giới. Cũng cần test trường hợp thành công, lỗi database và lỗi không dự kiến.

### Kiểm thử HTTP mapping

Với MockMvc, gửi request gây business rejection và xác minh response `409` có mã lỗi ổn định; gửi request gây lỗi hạ tầng và xác minh response kỹ thuật không lộ stack trace. Kiểm tra metric HTTP và metric use case theo đúng ranh giới, tránh đếm trùng cùng một lần thực thi.

### Kiểm thử mẫu số và retry

- request validation bị từ chối có được đưa vào mẫu số use case hay không theo định nghĩa đã chọn;
- health check và request ngoài SLO được loại trừ đúng cách;
- một use case gọi dependency nhiều lần do retry vẫn chỉ tạo một kết quả cuối cùng ở counter use case;
- dependency counter ghi nhận từng attempt theo đúng chính sách;
- business rejection không làm tăng technical error counter;
- lỗi kỹ thuật không bị phân loại thành business rejection do message hoặc HTTP status.

### Kiểm thử dashboard/query

Với Prometheus hoặc backend tương tự, kiểm tra query dùng đúng tên metric export, label và cửa sổ thời gian. Thử trường hợp không có dữ liệu hoặc mẫu số bằng 0 để panel không hiển thị NaN hoặc cảnh báo giả. Kiểm tra tổng số outcome có khớp tổng lần thực thi theo định nghĩa không.

## Những sai lầm thường gặp

- **Gộp mọi response không thành công vào một error rate:** business rejection làm nhiễu SLO kỹ thuật. Tách outcome theo ý nghĩa.
- **Coi mọi 4xx là lỗi người dùng:** một số 4xx có thể do lỗi hợp đồng hoặc cấu hình; cần phân loại nguyên nhân.
- **Coi mọi exception là lỗi kỹ thuật:** exception có thể được dùng cho từ chối nghiệp vụ. Dùng mã lỗi và taxonomy rõ ràng.
- **Coi mọi business rejection là bug:** hệ thống có thể đang áp dụng đúng quy tắc. Theo dõi bất thường theo baseline.
- **Không định nghĩa mẫu số:** tỷ lệ thay đổi theo cách lọc request. Ghi rõ đơn vị và điều kiện đưa vào mẫu số.
- **Đếm một lỗi ở nhiều tầng:** counter use case tăng ở service và exception handler cùng lúc. Chọn một ranh giới sở hữu phép đếm.
- **Dùng exception message làm tag:** cardinality cao và có thể chứa dữ liệu nhạy cảm. Dùng mã lỗi cố định.
- **Gộp retry với lần thực thi cuối cùng:** tỷ lệ bị phóng đại. Tách attempt, retry và outcome cuối.
- **Retry business rejection:** tăng tải mà không giải quyết nguyên nhân. Chỉ retry lỗi tạm thời và thao tác an toàn.
- **Chỉ xem tỷ lệ mà không xem số tuyệt đối:** tỷ lệ trên mẫu nhỏ có thể dao động mạnh. Hiển thị cả count và rate.
- **Alert mọi mã từ chối:** tạo nhiễu cho trực ca. Alert bất thường có ý nghĩa và định tuyến đến nhóm phù hợp.
- **Trả chi tiết exception cho client:** có thể lộ cấu trúc nội bộ. Ánh xạ sang mã và thông điệp công khai.

## Quy trình triển khai theo dõi outcome

Khi thêm metric cho một chức năng MVC, hãy thực hiện theo trình tự:

1. **Xác định đơn vị đo:** HTTP request, lần thực thi use case, dependency attempt hay job bất đồng bộ.
2. **Định nghĩa taxonomy:** thành công, business rejection, validation, security denial, technical error và các nhóm cần thiết.
3. **Xác định mẫu số:** điều kiện một request/use case được đưa vào tập đo; quy định loại trừ.
4. **Chuẩn hóa mã lý do:** dùng enum hoặc mã ổn định, không dựa trên message tự do.
5. **Chọn ranh giới ghi nhận:** use case ghi outcome cuối; adapter ghi lỗi dependency; web layer ghi HTTP response.
6. **Thiết kế metric/tag:** tên ổn định, cardinality thấp, không chứa ID hoặc dữ liệu nhạy cảm.
7. **Ánh xạ HTTP:** Controller/exception handler chuyển lỗi nội bộ thành status và response theo hợp đồng.
8. **Định nghĩa retry:** phân biệt lỗi tạm thời với business rejection, dùng idempotency khi cần.
9. **Xây dashboard/alert:** tách độ tin cậy kỹ thuật và xu hướng nghiệp vụ; có cả count và rate.
10. **Kiểm thử:** xác minh phân loại, counter, mẫu số, retry, response và query dashboard.

## Câu hỏi tự đánh giá

1. Vì sao business rejection không mặc định là lỗi kỹ thuật?
2. Một HTTP 409 có thể là kết quả nghiệp vụ bình thường trong trường hợp nào?
3. Tỷ lệ lỗi kỹ thuật ở cấp request khác gì tỷ lệ lỗi ở cấp use case?
4. Mẫu số của tỷ lệ từ chối nghiệp vụ nên bắt đầu ở bước nào?
5. Vì sao không thể phân loại mọi exception thành technical error?
6. Ranh giới nào nên ghi counter kết quả cuối cùng của use case?
7. Làm thế nào tách số lần retry khỏi số lần thực thi use case?
8. Vì sao exception message và user ID không nên là metric tag?
9. Khi nào business rejection tăng cần được cảnh báo cho nhóm sản phẩm?
10. Cần kiểm thử những gì để bảo đảm business rejection không làm tăng technical error rate?

Theo dõi riêng lỗi kỹ thuật và lỗi nghiệp vụ giúp đội phát triển hiểu đúng tình trạng ứng dụng MVC. Application service ghi nhận outcome cuối cùng của use case; adapter ghi nhận lỗi khi giao tiếp với dependency; Controller ánh xạ kết quả thành HTTP response. Khi taxonomy, mẫu số và ranh giới đo được định nghĩa rõ, dashboard có thể phản ánh độ tin cậy kỹ thuật mà không nhầm lẫn với những lần hệ thống từ chối hành động theo đúng quy tắc nghiệp vụ.
