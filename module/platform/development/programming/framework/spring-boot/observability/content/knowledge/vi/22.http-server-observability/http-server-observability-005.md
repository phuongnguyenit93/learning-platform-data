# Response status

Một API Spring Boot nhận request tạo đơn hàng. Controller trả HTTP 201 khi tạo thành công, 400 khi dữ liệu đầu vào không hợp lệ, 404 khi không tìm thấy tài nguyên và 500 khi có lỗi ngoài dự kiến. Status code giúp dashboard cho biết request thành công hay gặp lỗi ở phía client/server. Nhưng để observability hữu ích, cần hiểu response status được ghi nhận ở đâu, ảnh hưởng tới metric tag và trace ra sao, và vì sao một response 4xx không nhất thiết đồng nghĩa với một exception.

Bài **Response status** thuộc chương **HTTP server observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Điểm cốt lõi:** HTTP response status mô tả kết quả giao thức của một lần trao đổi HTTP. Observation có thể ghi các key như method, status, outcome, uri và error. Status, outcome và error/exception mang ý nghĩa khác nhau. Một request có thể trả 404 mà không ném exception; ngược lại, exception có thể bị xử lý và response cuối cùng là 400 hoặc 500. Hãy đọc status cùng ngữ cảnh của Observation thay vì suy luận lỗi chỉ từ một tag.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của HTTP response status trong HTTP server observability.
2. Phân biệt status code, outcome, error và exception trong Micrometer Observation.
3. Đọc các low-cardinality key mặc định của HTTP server Observation.
4. Phân loại 1xx, 2xx, 3xx, 4xx và 5xx theo outcome.
5. Hiểu vì sao 4xx không tự động có nghĩa Observation error hoặc exception.
6. Hiểu cách Servlet/WebFlux và Spring MVC xử lý exception ảnh hưởng tới Observation.
7. Truy vấn metrics theo status/outcome và liên kết với traces/logs.
8. Thiết kế custom ObservationConvention mà không làm tăng cardinality.
9. Kiểm thử response thành công, redirect, client error, server error và exception.
10. Điều tra status UNKNOWN, lỗi được handle nhưng thiếu error tag và response bị thay đổi sau filter.

## 2. Response status là gì?

HTTP status code là mã ba chữ số trong response, cho biết kết quả xử lý request ở cấp giao thức. Ví dụ:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/ord-123
~~~

Status 201 diễn đạt rằng request đã tạo resource thành công. Body có thể chứa representation của đơn hàng; Location chỉ vị trí resource mới.

Trong HTTP server observability, response status thường được ghi như một key-value có cardinality thấp để nhóm request thành các nhóm có thể đo lường. Nó giúp trả lời:

- Tỷ lệ request trả 2xx là bao nhiêu?
- Những route nào có nhiều 4xx?
- 5xx tăng bắt đầu từ phiên bản hoặc deployment nào?
- Redirect 3xx có tăng bất thường không?
- Một endpoint đang trả status nào khi latency tăng?

Status không giải thích nguyên nhân chi tiết. Nó chỉ là một tín hiệu trong nhóm metrics, logs và traces.

## 3. Phân biệt status, outcome, error và exception

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| status | HTTP status code thực tế của response | 200, 201, 404, 503 |
| outcome | Nhóm kết quả tổng quát theo status family | SUCCESS, CLIENT_ERROR, SERVER_ERROR |
| error | Lỗi được Observation ghi nhận, thường dựa trên exception/error context | IllegalStateException, none |
| exception | Đối tượng/loại exception xảy ra trong quá trình xử lý | PaymentTimeoutException |
| uri | URI pattern/template của handler | /orders/{orderId} |
| method | HTTP method được gửi | GET, POST, PATCH |

Ví dụ một request có thể là:

~~~text
method = POST
uri = /orders
status = 400
outcome = CLIENT_ERROR
error = none
~~~

Đây có thể là response validation error được controller trả trực tiếp mà không ném exception. Một request khác có thể có:

~~~text
method = GET
uri = /inventory/{sku}
status = 503
outcome = SERVER_ERROR
error = InventoryUnavailableException
~~~

Trong trường hợp này exception có thể đã bubble qua instrumentation boundary và được Observation ghi nhận. Cách ghi error phụ thuộc nơi exception được xử lý và convention của framework.

**Không suy luận error=none chỉ từ status 2xx hoặc error != none chỉ từ status 5xx.** Hãy đọc context và handler behavior.

## 4. Phân loại HTTP status và outcome

Spring Framework/Spring Boot dùng outcome để nhóm status code:

| Status class | Khoảng mã | Outcome thường dùng | Ví dụ |
|---|---:|---|---|
| 1xx Informational | 100–199 | INFORMATIONAL | 100 Continue |
| 2xx Success | 200–299 | SUCCESS | 200 OK, 201 Created, 204 No Content |
| 3xx Redirection | 300–399 | REDIRECTION | 301, 302, 304 |
| 4xx Client Error | 400–499 | CLIENT_ERROR | 400, 401, 403, 404, 409, 429 |
| 5xx Server Error | 500–599 | SERVER_ERROR | 500, 502, 503, 504 |

Outcome giảm số nhóm cần quan sát và giữ cardinality hữu hạn. Status cung cấp chi tiết hơn nhưng vẫn có miền mã hữu hạn theo HTTP.

### 4.1 2xx không chỉ có 200

- 200 OK: request được xử lý và có thể trả representation.
- 201 Created: tạo resource thành công.
- 202 Accepted: đã nhận request nhưng xử lý có thể diễn ra bất đồng bộ.
- 204 No Content: thành công nhưng không có response body.

Khi dashboard chỉ đếm 200, các kết quả thành công 201/202/204 có thể bị bỏ qua. Hãy dùng outcome SUCCESS hoặc nhóm status 2xx.

### 4.2 3xx cần được diễn giải theo API

301/302 có thể là redirect theo luồng điều hướng. 304 Not Modified phục vụ cache validation. 3xx không tự động là lỗi server. Tăng 3xx có thể là hành vi mong đợi nếu ứng dụng dùng redirect; cũng có thể là vòng lặp redirect hoặc route cấu hình sai nếu tỷ lệ bất thường.

### 4.3 4xx có thể là kết quả nghiệp vụ dự kiến

400 có thể là validation failure, 401 là chưa xác thực, 403 là bị từ chối quyền, 404 là không có tài nguyên, 409 là conflict và 429 là rate limited. Chúng thường phản ánh request hoặc chính sách từ chối ở phía client/gateway, không nhất thiết là lỗi nội bộ.

Tùy sản phẩm, 404/409 có thể là kết quả bình thường của use case. Endpoint kiểm tra username tồn tại có thể tạo 404 thường xuyên. Alert cần phân biệt endpoint và tỷ lệ bất thường, không coi mọi 4xx là service failure.

### 4.4 5xx thường cần điều tra service/dependency

500 biểu thị lỗi nội bộ không được xử lý thành response thành công; 502/503/504 thường liên quan gateway, upstream hoặc service unavailable/timeout. Status một mình vẫn không nói chính xác dependency nào lỗi. Cần mở trace và logs cùng service/route/time window.

## 5. HTTP server Observation trong Spring

Spring Framework tạo HTTP server exchange Observation cho Servlet và Reactive applications. Observation tiêu chuẩn thường có tên http.server.requests; khi dùng OpenTelemetry convention, metric/observation naming có thể là http.server.request.duration.

Spring Boot Actuator cấu hình instrumentation cho các stack được hỗ trợ khi có dependency phù hợp. Observation có thể được xử lý bởi handler để tạo Micrometer metrics và/hoặc tracing spans.

Các key-value mặc định thường gồm:

| Key | Cardinality | Nội dung |
|---|---|---|
| error | Low | Tên lớp exception hoặc none nếu không ghi nhận exception |
| method | Low | HTTP method, hoặc none với method không chuẩn/không nhận diện |
| outcome | Low | Nhóm kết quả từ response status |
| status | Low | Raw HTTP status code hoặc UNKNOWN khi chưa tạo được response |
| uri | Low | URI pattern của handler hoặc fallback như NOT_FOUND, REDIRECTION, UNKNOWN |

Một high-cardinality field có thể có giá trị URL đầy đủ như http.url; field này dành cho trace theo convention tương ứng, không phải metric tag mặc định. Đừng dùng raw URL làm metric dimension.

Key chính xác tùy convention đang dùng và phiên bản Spring Framework. Khi chọn OpenTelemetry semantic convention, tên/mapping có thể khác convention Micrometer mặc định. Tham khảo Spring Framework Observability và Spring Boot Metrics documentation.

## 6. Status và metrics

HTTP server Observation thường tạo timer metric để đo thời gian xử lý request. Một meter như http.server.requests có thể được nhóm theo method, uri, status, outcome và error.

Ví dụ query conceptual:

~~~text
http.server.requests{
  method="POST",
  uri="/orders",
  status="201",
  outcome="SUCCESS"
}
~~~

Tên metric/labels thực tế phụ thuộc registry và naming convention. Prometheus thường chuyển dấu chấm thành dấu gạch dưới, còn OTLP có thể giữ tên theo quy tắc export tương ứng.

### 6.1 Vì sao nên đo cả status lẫn outcome?

- status giúp xem cụ thể 401, 404, 429, 500, 503.
- outcome giúp gom nhóm SUCCESS, CLIENT_ERROR, SERVER_ERROR.
- error giúp phân biệt request có exception được ghi nhận hay không.
- uri giúp xác định route template nào có vấn đề.

Khi tạo dashboard cấp cao, outcome dễ đọc và bền hơn. Khi điều tra, drill down theo status và route cụ thể.

### 6.2 Không dùng raw URL làm tag

Không tạo tag theo URL có ID:

~~~text
uri="/orders/ord-1001"
uri="/orders/ord-1002"
uri="/orders/ord-1003"
~~~

Hãy dùng route template:

~~~text
uri="/orders/{orderId}"
~~~

Metric time series cardinality là tích số khả năng của từng dimension. Nếu thêm userId, requestId, full URL hoặc query string, số series có thể tăng gần như theo số request, làm tăng memory, storage và query cost.

### 6.3 Status code có cardinality hữu hạn nhưng vẫn cần kiểm soát

HTTP status có miền hữu hạn, tuy nhiên custom application response codes hoặc arbitrary tags có thể làm tăng cardinality. Không tạo status tag từ chuỗi tự do; luôn lấy từ response status hợp lệ và tránh thêm key khác chứa message/error text.

## 7. Status không đồng nghĩa với Observation error

Đây là điểm quan trọng nhất khi đọc HTTP server metrics.

Spring Framework Servlet instrumentation thường ghi Observation là error khi exception bubble tới observation filter, và với một số server errors do Spring MVC tự xử lý, như 5xx được render thông qua ProblemDetail. Các lỗi 4xx và exception được xử lý bởi @ExceptionHandler thường không tự động được ghi là Observation error. Framework cho phép ứng dụng chủ động đánh dấu error trong ObservationContext khi cần.

| Tình huống | HTTP status | Exception | Observation error có thể có? |
|---|---:|---|---|
| Controller trả bad request | 400 | Không | Thường không |
| Validation exception được @ExceptionHandler xử lý thành 400 | 400 | Có nhưng đã handle | Thường không tự động |
| Resource không tồn tại, trả 404 | 404 | Có thể không | Thường không |
| IllegalStateException bubble khỏi controller | 500 | Có | Có |
| Handler xử lý exception và trả 500 ProblemDetail | 500 | Có nhưng đã handle | Theo Spring MVC behavior/convention, có thể được ghi nhận cho server error |
| Request kết thúc trước khi response được tạo | UNKNOWN | Có thể có | Phụ thuộc exception path |

Các quy tắc cụ thể khác nhau theo Servlet/WebFlux, Spring Framework version, exception resolver và custom filter. Không áp bảng này máy móc khi có custom instrumentation.

### 7.1 Vì sao 404 không nhất thiết là exception?

Spring MVC có thể không tìm thấy handler và hoàn tất request với 404. Đây là status trả về cho client. Observation có thể dùng URI fallback NOT_FOUND; error vẫn có thể là none nếu không có exception được ghi nhận.

### 7.2 Vì sao validation 400 có thể không tăng error tag?

MethodArgumentNotValidException có thể được Spring xử lý và chuyển thành response 400. Vì exception không bubble ra ngoài observation boundary, error tag có thể là none. Nhưng status vẫn là 400 và outcome vẫn là CLIENT_ERROR.

Nếu business/SLO cần đo validation rejects, hãy dùng metric nghiệp vụ riêng hoặc chủ động ghi nhận theo observation context/convention, thay vì giả định exception tag sẽ tự có.

### 7.3 5xx được xử lý vẫn có thể được đánh dấu

Spring Framework có logic để server errors được framework xử lý (bao gồm ProblemDetail trong Spring MVC) vẫn có thể được ghi nhận là Observation error. Một handler có thể bắt exception, tạo response JSON gọn gàng nhưng vấn đề vẫn là server-side failure.

Với WebFlux hoặc custom exception handling, xác minh behavior bằng test trên phiên bản cụ thể.

## 8. Ví dụ Controller trả các response status

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    ResponseEntity<OrderView> create(@RequestBody CreateOrder command) {
        OrderView created = orderService.create(command);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> find(@PathVariable String id) {
        return orderService.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/validate")
    ResponseEntity<Void> validate(@RequestBody CreateOrder command) {
        if (command.items().isEmpty()) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

Đây là ví dụ minh họa; service, DTO và validation đã được giản lược. POST thành công trả 201. GET không có resource trả 404. Endpoint validate trả 400 mà không cần ném exception, do đó status/outcome vẫn thể hiện client error dù error tag có thể none.

## 9. Custom exception handling và status

Một controller advice có thể ánh xạ exception thành status response:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderConflictException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    ProblemDetail handleConflict(OrderConflictException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setTitle("Order conflict");
        problem.setDetail("The requested order state is not valid.");
        return problem;
    }
}
~~~

HTTP status 409 cho client biết xung đột. Nhưng vì exception được xử lý tại advice, observation filter có thể không thấy exception bubble. Nếu cần error measurement riêng, ghi nhận lỗi nghiệp vụ rõ ràng trong Observation hoặc meter chuyên biệt.

Không đưa exception message tùy ý vào response detail, log hoặc span nếu có thể chứa SQL, token hoặc dữ liệu người dùng.

### 9.1 Đừng đánh dấu mọi 4xx là application failure

Alert trên outcome CLIENT_ERROR có thể hữu ích khi theo dõi chất lượng API, nhưng nó không phải lúc nào cũng là pager cho đội service. Endpoint public có traffic bot tạo 404/401; 429 có thể chứng minh rate limit hoạt động. Xây alert theo route, status, baseline và SLO của API.

### 9.2 Đừng bỏ qua 5xx chỉ vì exception đã handled

Một @ExceptionHandler có thể biến lỗi downstream thành response 503. Điều đó tốt cho API contract, nhưng platform vẫn cần nhận biết lỗi server. Hãy kiểm tra error convention, log severity, trace status và metric status/outcome để không mất tín hiệu.

## 10. Status trong traces và logs

Traces thường giữ span cho HTTP server exchange, với attributes mô tả method, route, status code và thông tin liên quan. Span status trong tracing data model có khái niệm riêng với HTTP status code. Một span có thể có HTTP status attribute 404 nhưng span status vẫn là UNSET theo instrumentation convention; đừng giả định mọi 4xx phải set span status ERROR.

Log level là quyết định của logging policy, không phải phép ánh xạ cứng từ HTTP status:
- 404 có thể là INFO/DEBUG nếu là luồng nghiệp vụ thường gặp.
- 401/403 có thể cần security audit phù hợp nhưng không ghi credential.
- 429 có thể là WARN nếu rate limit bất thường hoặc INFO nếu chính sách vận hành.
- 5xx thường cần ERROR/WARN tùy nơi phát log; tránh tạo nhiều error logs cho cùng một lỗi đã được xử lý.

Đưa traceId/spanId vào logs để correlation nếu context propagation và logging integration được cấu hình. Log có thể có route template và status, nhưng không ghi raw URL chứa secret/query.

## 11. Tùy chỉnh status tags bằng ObservationConvention

Micrometer Observation cho phép tùy chỉnh low-cardinality key-values bằng ObservationConvention. Có thể thay đổi quy tắc gắn metadata nhưng phải giữ semantics ổn định.

Spring Framework có DefaultServerRequestObservationConvention với context ServerRequestObservationContext. Khi custom, nên kế thừa hoặc decorate logic mặc định để giữ các key cần thiết.

Ví dụ khai báo convention mặc định minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.ServerRequestObservationConvention;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;

@Configuration
class HttpObservationConfiguration {

    @Bean
    ServerRequestObservationConvention serverObservationConvention() {
        return new DefaultServerRequestObservationConvention();
    }
}
~~~

Đây là cách khai báo convention mặc định minh họa; khi custom thật, triển khai convention phù hợp và trả low-cardinality values đã chuẩn hóa. Spring Framework có extension points khác nhau cho Servlet và Reactive stacks; xác nhận đúng interface mà stack đang dùng.

### 11.1 Ví dụ thêm business outcome hữu hạn

Nếu cần biết request bị từ chối do policy, hãy thêm key như business.result với tập giá trị nhỏ:
- accepted
- validation_rejected
- conflict
- rate_limited

Không dùng exception message hoặc error detail làm tag. Với custom convention, dùng context để suy ra status/outcome an toàn và chỉ thêm field nếu giá trị bounded.

### 11.2 Không ghi đè status thành business result

Giữ status là HTTP status thực tế. Nếu API trả 409 Conflict nhưng business result là inventory_unavailable, status vẫn 409; business.result là key khác. Không thay status=409 bằng inventory_unavailable vì sẽ phá semantics và query conventions.

## 12. Status UNKNOWN và response chưa được tạo

Một số request thất bại trước khi response hoàn chỉnh được tạo, ví dụ connection bị đóng, container abort, exception xảy ra sớm hoặc handler không hoàn tất response. Khi đó instrumentation có thể ghi status là UNKNOWN vì không có response status để đọc.

UNKNOWN không phải HTTP status code hợp lệ từ response; nó là fallback trong Observation metadata để biểu đạt không thu thập được status. Hãy điều tra:

- Exception có bubble qua observation filter không?
- Response đã được commit chưa?
- Client có ngắt kết nối trước khi server hoàn tất không?
- Filter/interceptor có kết thúc observation đúng lifecycle không?
- Server stack có cung cấp response status cho instrumentation không?

Đừng thêm UNKNOWN làm status code trong business logic hoặc trả UNKNOWN cho client.

## 13. Response status và response commitment

Trong Servlet stack, response có thể được commit trước khi filter cuối cùng đọc status; trong streaming/reactive response, status và body lifecycle có thể hoàn tất ở các thời điểm khác nhau. Nếu application/filter thay đổi status sau khi response đã commit, HTTP server không thể gửi status mới như một response bình thường.

Ví dụ:
- Controller chọn 200 rồi streaming body ném exception giữa chừng.
- Filter ghi response body/flush trước khi exception handler thay status.
- Client hủy connection khi server vẫn đang ghi response.
- Error dispatch tạo error response thứ hai hoặc sửa metadata sau khi observation scope đã đóng.

Khi kiểm tra trace/metric, phân biệt response status server thực sự gửi với exception phát sinh trong quá trình stream. Một request có thể bắt đầu với status 200 nhưng stream lỗi sau khi headers đã commit; status HTTP vẫn 200 nhưng span/exception event có thể ghi nhận lỗi stream tùy instrumentation.

## 14. Kiểm thử response status

Không chỉ test controller response; cần xác nhận observability signal cũng phản ánh kết quả mong đợi.

| Scenario | Status mong đợi | Outcome mong đợi |
|---|---:|---|
| Tạo order thành công | 201 | SUCCESS |
| Request validation không hợp lệ | 400 | CLIENT_ERROR |
| Không có resource | 404 | CLIENT_ERROR |
| Redirect | 302 | REDIRECTION |
| Conflict | 409 | CLIENT_ERROR |
| Dependency unavailable | 503 | SERVER_ERROR |
| Lỗi chưa tạo được response | UNKNOWN trong Observation nếu phù hợp | Không phải HTTP response code |

### 14.1 Test Observation bằng test registry

Có thể dùng SimpleMeterRegistry và ObservationRegistry trong test để xác minh timer/meter được tạo. Cấu trúc test minh họa:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpResponseStatusObservationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsCreatedStatus() throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType("application/json")
                        .content(validOrderJson()))
                .andExpect(status().isCreated());

        Timer timer = meterRegistry.find("http.server.requests")
                .tag("method", "POST")
                .tag("status", "201")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

Imports, DTO fixtures, controller và metric name/tag convention cần khớp ứng dụng thực tế. Với OTel semantic convention hoặc custom ObservationConvention, meter name/tag names có thể khác. Không copy test như contract cố định cho mọi stack.

### 14.2 Kiểm tra handled exception

Viết test cho @ExceptionHandler trả 400 và 500:
- Xác nhận HTTP status.
- Xác nhận status/outcome metadata.
- Xác nhận error tag behavior theo framework version.
- Nếu nghiệp vụ yêu cầu 4xx validation được tính là error riêng, kiểm tra custom observation/business metric đã được ghi nhận.

### 14.3 Kiểm tra không có cardinality bùng nổ

Gửi nhiều request tới /orders/{id} với IDs khác nhau và xác nhận metric URI vẫn là route template, không phải full path. Kiểm tra số meter IDs không tăng theo số order ID.

## 15. Điều tra dashboard: 5xx tăng nhưng error tag thấp

**Tình huống:** Dashboard cho thấy status=500 tăng nhưng error vẫn là none ở phần lớn requests.

1. Chọn traces/logs đại diện theo cùng route và time window.
2. Kiểm tra controller/advice có bắt exception rồi trả 500 không.
3. Xác định exception có bubble đến observation filter không.
4. Kiểm tra stack Servlet hay WebFlux và version Spring Framework.
5. Kiểm tra custom ObservationConvention/Filter có thay đổi error key không.
6. Xem log có exception stack/cause đã được ghi nhận không.
7. Nếu 500 là business-controlled error không có exception, thêm business error/outcome metric riêng thay vì ép error tag từ status.
8. Nếu 500 là server failure đã handle, cấu hình ghi nhận exception vào context theo extension point đúng và test lại.

Status tag vẫn là nguồn tin cậy cho HTTP response class; error tag chỉ phản ánh lỗi được Observation ghi nhận.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| 404 tăng nhưng error tag vẫn none | Not-found response không cần exception hoặc framework handle | Xem status/outcome; phân loại 404 theo route |
| 400 validation không hiện exception | @ExceptionHandler xử lý exception | Nếu cần, ghi business validation metric/Observation riêng |
| 500 có status nhưng không có error class | Exception đã được handle hoặc custom convention không thêm error | Kiểm tra handler/context và chủ động ghi nhận khi cần |
| status=UNKNOWN | Response chưa tạo hoặc không đọc được status | Kiểm tra exception/commit/stream lifecycle |
| Dashboard chỉ thấy 200 | Query filter loại 201/202/204 | Query theo outcome hoặc status family |
| 3xx bị alert như server error | Query/threshold gộp status không đúng | Tách outcome theo semantics API |
| 4xx tăng do bot/consumer | Traffic hoặc client behavior thay đổi | Phân tích route/source/rate limit, không pager mọi 4xx |
| 5xx tăng nhưng error tag không tăng | Handled exception/ProblemDetail/convention khác | Test framework path và custom ObservationContext |
| Trace span không có status ERROR dù HTTP 404 | HTTP status attribute và span status khác nhau | Dùng HTTP attributes và tracing semantic conventions |
| Metric cardinality tăng theo ID | Raw URI/user/request ID trở thành tag | Dùng URI template và bounded values |
| Status trong access log khác metric | Reverse proxy sửa response hoặc log layer khác | So sánh status tại từng hop |
| Streaming trả 200 nhưng trace có exception | Headers đã commit rồi body stream lỗi | Điều tra stream lifecycle/client disconnect |
| Jersey tag khác Spring MVC tag | Stack instrumentation/convention khác | Kiểm tra JerseyObservationConvention và server stack |

## 17. Bài tập tự kiểm tra

**Bài 1 — status vs outcome.** API trả 429. status và outcome là gì? Có mặc định phải có exception không?

**Bài 2 — status vs error.** Controller trả 404 trực tiếp mà không ném exception. Vì sao error có thể là none?

**Bài 3 — handled exception.** Validation exception được @ExceptionHandler chuyển thành 400. Vì sao Observation không nhất thiết ghi exception error? Cách đo validation failure có chủ đích?

**Bài 4 — 5xx ProblemDetail.** Một exception được Spring MVC xử lý thành 503 ProblemDetail. Tại sao vẫn cần bảo đảm Observation đánh dấu server error?

**Bài 5 — UNKNOWN.** Khi nào Observation có status UNKNOWN? Nó có phải HTTP status gửi tới client không?

**Bài 6 — Cardinality.** Vì sao không dùng raw URL /orders/12345 làm metric tag trong khi status 404 là bounded?

**Bài 7 — Streaming.** Controller trả 200 rồi streaming body phát sinh exception. Vì sao status cuối cùng có thể vẫn là 200 và trace vẫn ghi lỗi?

**Bài 8 — Dashboard.** 5xx tăng nhưng error tag phần lớn none. Lập thứ tự điều tra và nêu vì sao không nên chỉ dựa vào error tag.

### Gợi ý trả lời

1. status=429, outcome=CLIENT_ERROR; không bắt buộc có exception.
2. 404 là kết quả HTTP, không nhất thiết có exception được ghi nhận.
3. Exception đã được xử lý bên trong MVC, không bubble tới observation filter. Dùng low-cardinality business metric/Observation cho validation_rejected nếu cần.
4. Response vẫn biểu thị server failure dù exception được biến thành ProblemDetail; nếu mất error signal, việc điều tra exception khó hơn.
5. Khi response chưa được tạo/không đọc được status; UNKNOWN là fallback Observation, không phải mã HTTP response.
6. ID mỗi order tạo nhiều series; route template /orders/{id} giữ dimension bounded.
7. Headers đã commit nên không thể đổi status; exception xảy ra trong stream có thể được ghi riêng vào span/event.
8. Xem traces/logs, controller advice, exception propagation, stack/framework convention, custom filter; status phản ánh response, error phản ánh exception được ghi nhận.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): HTTP server observations, KeyValues, low/high cardinality và Servlet exception handling.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): HTTP server metrics, outcome/status tags và customization.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation, metrics/tracing integration và conventions.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, ObservationContext, handlers và conventions.
- [Micrometer — Observation API](https://docs.micrometer.io/micrometer/reference/observation/components.html): Observation conventions, handlers và key-values.
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/): HTTP request/response attributes và status semantics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa chuẩn của HTTP status codes.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail và xử lý REST API errors.

**Ghi nhớ:** Response status cho biết kết quả HTTP; outcome gom status thành nhóm; error/exception mô tả lỗi được Observation ghi nhận. Một 400/404 có thể không có exception error, còn exception đã handle vẫn có thể cần được ghi nhận nếu là server failure. Dùng status và route template cho metrics, mở traces/logs để biết nguyên nhân, kiểm thử cả handled/unhandled exceptions và không dùng raw URL hoặc dữ liệu tự do làm metric tags.

