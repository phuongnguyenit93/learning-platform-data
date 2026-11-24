# Outcome của HTTP server observation trong Spring Boot

> **Chương:** HTTP server observability  
> **Bài:** Outcome  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần một outcome nhất quán?

Một HTTP server nhận request, chạy controller và service, rồi trả response. Chỉ biết request đã hoàn tất chưa là chưa đủ để vận hành hệ thống. Nhóm phát triển cần biết request kết thúc thành công, bị từ chối theo contract, không tìm thấy tài nguyên, gặp lỗi do dependency hay thất bại vì lỗi nội bộ.

**Outcome** là cách phân loại kết quả của một operation sau khi xử lý. Với HTTP server observability, outcome giúp diễn giải kết quả request để tổng hợp metrics, tìm kiếm traces, xây dashboard và đặt alert.

| HTTP status | Tình huống | Cách hiểu có thể có |
| --- | --- | --- |
| 200 | Truy vấn hoàn tất | Thành công |
| 201 | Tạo tài nguyên | Thành công |
| 204 | Hoàn tất không có body | Thành công |
| 400 | Request sai cấu trúc | Client/input outcome |
| 401/403 | Không xác thực/không được phép | Security/policy outcome |
| 404 | Tài nguyên không tồn tại | Có thể là kết quả nghiệp vụ bình thường |
| 409 | Xung đột trạng thái | Business conflict |
| 429 | Vượt giới hạn | Throttling |
| 500 | Lỗi không dự kiến trên server | Server error |
| 502/503/504 | Gateway/dependency unavailable/timeout | Hạ tầng hoặc dependency error |

Không nên đồng nhất HTTP status với một outcome nghiệp vụ duy nhất. Status code là một phần bằng chứng; nguyên nhân và semantics của operation còn phụ thuộc contract API, exception mapping và cách ứng dụng xử lý lỗi.

~~~mermaid
flowchart TD
  A["HTTP request bắt đầu"] --> B["Server Observation / span"]
  B --> C["Controller và business operation"]
  C --> D{"Operation kết thúc"}
  D -->|"Response bình thường"| E["Đọc status / outcome"]
  D -->|"Exception"| F["Exception handler / error mapping"]
  F --> E
  E --> G["Ghi response status và outcome"]
  G --> H["Stop observation / span"]
  H --> I["Metrics + trace + logs"]
~~~

Log đúng context và outcome không có nghĩa ghi tất cả request headers hoặc toàn bộ object. Chỉ ghi metadata vừa đủ, an toàn và có cardinality phù hợp.

## 2. Outcome nằm ở đâu trong HTTP server observability?

HTTP server observation biểu diễn vòng đời xử lý request đến server. Framework instrumentation thường tạo observation/span khi request đi vào, thu thập thông tin request/response và kết thúc khi server hoàn thành xử lý.

Một HTTP server observation có thể có:
- HTTP method và route template.
- Status code của response.
- Kết quả xử lý hoặc outcome theo convention.
- Exception nếu request thất bại.
- Thời gian xử lý.
- Trace context để nối request với downstream calls.

Trong Spring Boot, Micrometer Observation là lớp instrumentation quan trọng cho nhiều server request. Metrics và tracing handlers có thể nhận cùng Observation context để ghi nhận signals. Key names/tag mapping phụ thuộc Spring Boot/Micrometer version, web stack và convention.

**Outcome không phải HTTP header cần gửi cho client.** Đây là metadata quan sát được tính hoặc suy ra trong server-side lifecycle, sau khi framework biết response hoặc exception.

## 3. Phân biệt outcome, status code và exception

Ba khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| HTTP status code | Server gửi mã nào về client? | 503 |
| Exception | Điều gì đã ném ra trong runtime? | SocketTimeoutException |
| Outcome | Operation được phân loại kết quả thế nào? | success / client_error / server_error |

Một exception có thể được bắt và chuyển thành response hợp lệ. Ví dụ service gọi payment gateway timeout, nhưng business contract cho phép tạo payment pending. Ứng dụng có thể trả 202 Accepted sau khi lưu công việc vào queue. Exception vẫn là sự kiện cần theo dõi ở dependency span hoặc log, nhưng HTTP server request có thể hoàn tất thành công theo contract.

Ngược lại, server có thể trả 500 mà không có exception được ném lên framework, ví dụ code chủ động tạo response 500. Nếu instrumentation chỉ dựa vào exception, outcome sẽ thiếu thông tin; cần xét cả response status.

### 3.1. Một ví dụ cụ thể

~~~java
@PostMapping("/payments")
public ResponseEntity<PaymentAccepted> submit(
        @RequestBody PaymentRequest request) {
    try {
        PaymentAccepted accepted = paymentService.submit(request);
        return ResponseEntity.accepted().body(accepted);
    } catch (PaymentGatewayTimeoutException ex) {
        PaymentAccepted pending = paymentService.enqueueForLater(request);
        return ResponseEntity.accepted().body(pending);
    }
}
~~~

Trong ví dụ, exception của dependency được xử lý. Server gửi 202 vì công việc đã được nhận để xử lý sau. Không nên đánh dấu HTTP server operation là lỗi chỉ vì một exception nội bộ đã xảy ra rồi được xử lý theo contract. Tuy nhiên payment client span hoặc metric riêng vẫn có thể ghi nhận timeout.

## 4. HTTP status class và cách phân loại outcome

HTTP status được chia thành 1xx, 2xx, 3xx, 4xx và 5xx. Đây là phân loại giao thức hữu ích, nhưng không phải lúc nào cũng thể hiện đúng sức khỏe nghiệp vụ.

| Status class | Ý nghĩa giao thức | Ví dụ |
| --- | --- | --- |
| 1xx | Informational | 100 Continue |
| 2xx | Success response | 200, 201, 202, 204 |
| 3xx | Redirection | 301, 302, 304 |
| 4xx | Client error | 400, 401, 403, 404, 409, 429 |
| 5xx | Server error | 500, 502, 503, 504 |

Các convention tracing có thể sử dụng status code, exception và loại span để đặt status/error attributes. Tuy nhiên, **không tự gán một taxonomy outcome vào Micrometer/Spring Boot nếu chưa kiểm tra convention của phiên bản đang dùng**.

Ví dụ:
- HTTP server request trả 404 có thể là phản hồi đúng contract.
- HTTP client nhận 404 từ dependency có thể là lỗi cho operation client tùy contract.
- 429 có thể chỉ ra rate limiting có chủ đích, không phải bug.
- 503 do bảo trì có thể là trạng thái phục vụ có kiểm soát.
- 500 thường cần điều tra, nhưng có thể do exception đã được map tại boundary.

Outcome nên là tập phân loại nhỏ và ổn định, như success, client_error, server_error, timeout hoặc rejected. Nếu cần chi tiết, dùng status code hoặc span/log attributes ở signal phù hợp.

## 5. Spring Boot tạo HTTP server Observation như thế nào?

Với ứng dụng Spring MVC/WebFlux có Actuator và instrumentation tương ứng, Spring Boot có thể tự động tạo server observations cho request. Observation thường có tên convention do framework định nghĩa và được xử lý bởi ObservationHandlers đã cấu hình.

~~~mermaid
sequenceDiagram
  participant Client
  participant Servlet as Web stack
  participant Obs as ObservationRegistry
  participant MH as Metrics handler
  participant TH as Tracing handler
  Client->>Servlet: HTTP request
  Servlet->>Obs: Start server observation
  Obs->>MH: Start timing / tags
  Obs->>TH: Start server span
  Servlet->>Servlet: Controller + service
  Servlet->>Obs: Response / exception context
  Obs->>MH: Stop and record
  Obs->>TH: End span / set status
  Servlet-->>Client: HTTP response
~~~

Để pipeline hoạt động, cần đúng dependencies và configuration. Nếu thiếu tracing bridge, metrics có thể vẫn được tạo nhưng không có server spans theo tracing integration mong muốn. Nếu thiếu registry/exporter, observation có thể được tạo nhưng dữ liệu không tới backend tương ứng.

Không tạo thêm filter hoặc interceptor thủ công cho mọi request trước khi kiểm tra built-in instrumentation; làm vậy có thể tạo observation/span trùng.

## 6. Outcome và HTTP server metrics

HTTP server metrics thường đo số request và thời lượng xử lý theo các chiều như method, outcome, status và URI template, tùy instrumentation/version.

Một meter thường gặp trong hệ sinh thái Spring là:

~~~text
http.server.requests
~~~

Các tag phổ biến có thể bao gồm:
- method: GET, POST, PUT…
- status: 200, 404, 500…
- uri: route template đã chuẩn hóa.
- outcome: nhóm kết quả HTTP theo convention.
- exception: loại exception hoặc giá trị none/unknown tùy convention.

Tag names và values thực tế cần kiểm tra tại endpoint Actuator metrics hoặc registry đang chạy.

Ví dụ PromQL khái niệm:

~~~text
Tổng request:
  sum(rate(http_server_requests_seconds_count[5m]))

Tỷ lệ server response 5xx:
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
~~~

Đây là ví dụ; metric name và suffix phụ thuộc exporter/registry. Với Prometheus, Timer có thể được expose thành count, sum và histogram buckets tùy cấu hình.

### 6.1. Outcome tag hỗ trợ dashboard ra sao?

Một outcome tag ổn định giúp so sánh tỷ lệ thành công/lỗi mà không phải viết nhiều bộ lọc status code ở mỗi dashboard.

~~~text
outcome="SUCCESS"
outcome="CLIENT_ERROR"
outcome="SERVER_ERROR"
~~~

Đây chỉ là ví dụ taxonomy. Spring Boot/Micrometer convention có thể cung cấp giá trị outcome khác. Không giả định các chuỗi trên là giá trị mặc định của mọi version.

Metrics nên có cardinality thấp. Không đưa request ID, user ID, raw URL hoặc exception message vào tag. Route cần là template như /orders/{id}, không phải path thực tế /orders/987654.

## 7. Outcome trên trace/span

Server span giúp quan sát thời gian và kết quả của một request. Khi request kết thúc, tracing instrumentation có thể ghi HTTP status attributes, exception event và span status theo semantic conventions.

Ví dụ span attributes:

~~~text
span.kind = SERVER
http.request.method = POST
http.route = /orders
http.response.status_code = 503
service.name = order-service
~~~

Với semantic conventions HTTP hiện hành, tên thuộc tính đã được chuẩn hóa qua các phiên bản; hệ thống cũ có thể dùng key legacy. Khi đọc trace, kiểm tra convention version và không giả định mọi backend hiển thị cùng một tên field.

Span status ERROR nên phản ánh operation thực sự thất bại theo semantics tracing. Không tự set ERROR cho mọi 4xx nếu đó là hành vi hợp lệ của API. Một request validation thất bại có thể là expected client outcome; một 404 có thể là business result. Tùy convention và policy, span status có thể khác HTTP status class.

### 7.1. Exception event và status

Nếu exception thoát khỏi server instrumentation, framework có thể ghi exception event và error status. Nếu exception được xử lý, handler có thể không coi server operation là thất bại. Trong custom code, nếu tự ghi exception lên span, cần tránh ghi lặp với built-in instrumentation.

Không đánh dấu span ERROR chỉ để dashboard có số liệu. Hãy chọn đúng nơi phát ra outcome và giữ cho metrics, trace status và log severity phản ánh cùng semantics.

## 8. Outcome và exception handler

Global exception handler thường map exception thành HTTP response. Mapping này ảnh hưởng trực tiếp đến status code server observation nhìn thấy.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("The requested order does not exist.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(DependencyUnavailableException.class)
    public ResponseEntity<ProblemDetail> handleUnavailable(
            DependencyUnavailableException ex) {
        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("A dependency is temporarily unavailable");
        problem.setDetail("Please retry later.");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
~~~

HTTP observation thường thấy status cuối sau khi exception handler xử lý. Vì vậy:
- OrderNotFoundException map thành 404; đây có thể là expected client/business outcome.
- DependencyUnavailableException map thành 503; thường là availability signal cần alert/điều tra.
- Không phải exception nào cũng nên log ERROR hoặc đánh span ERROR theo cùng một quy tắc.
- Error handler cần giữ response an toàn, không lộ stack trace hoặc internal details.

Nếu handler trả response 200/202 sau khi xử lý thành công, outcome HTTP server nên được hiểu theo response cuối và contract. Exception nội bộ vẫn có thể được ghi nhận ở dependency instrumentation/metrics/logs.

## 9. Tùy biến ObservationConvention

Khi built-in convention chưa cung cấp metadata cần thiết, Micrometer cho phép dùng ObservationConvention để tùy biến tên hoặc key-values cho observation tương ứng, tùy extension point web stack và phiên bản Spring Boot.

Ví dụ convention khái niệm:

~~~java
public class CustomServerObservationConvention
        implements ServerRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        KeyValues values = KeyValues.of(
                KeyValue.of("api.version", "v1"));

        int status = context.getResponse() == null
                ? 0
                : context.getResponse().getStatus();

        return values.and(
                KeyValue.of("response.family", statusFamily(status)));
    }

    private String statusFamily(int status) {
        if (status >= 200 && status < 300) return "2xx";
        if (status >= 400 && status < 500) return "4xx";
        if (status >= 500 && status < 600) return "5xx";
        return "other";
    }
}
~~~

Đây là ví dụ minh họa API convention; constructor, context type, interface package và cách đăng ký bean phụ thuộc Spring Boot/Micrometer version và web stack. Đối chiếu API thực tế của dự án trước khi dùng nguyên code.

### 9.1. Chỉ thêm low-cardinality metadata

Convention nên phát ra giá trị hữu hạn:
- response.family: 2xx, 4xx, 5xx, other.
- api.version: v1, v2.
- operation: create, read, update, delete.
- outcome: success, rejected, error theo taxonomy đã định nghĩa.

Không phát ra exception message, request URL nguyên bản có ID, user ID/order ID, SQL query có literal hoặc stack trace. Low-cardinality values có thể trở thành metric labels; giá trị động theo từng request có thể tạo hàng triệu time series.

## 10. Phân biệt outcome kỹ thuật và outcome nghiệp vụ

Một operation có thể thành công về HTTP nhưng bị từ chối theo nghiệp vụ. Ngược lại, HTTP 4xx có thể là kết quả được dự kiến.

Ví dụ:
- Đăng nhập sai password: HTTP 401, request được xử lý đúng contract nhưng authentication không thành công.
- Tìm đơn không tồn tại: HTTP 404, có thể là expected business result.
- Tạo đơn không đủ hàng: HTTP 409 hoặc 422 tùy API, là business rejection.
- Inventory service timeout: HTTP 503 hoặc response fallback, tùy contract.
- NullPointerException: thường dẫn đến HTTP 500 và là server defect.

Nếu dashboard chỉ phân loại 2xx là success và 4xx/5xx là failure, cần ghi rõ đây là **HTTP success ratio**, không phải business success ratio. Nếu nghiệp vụ cần tỷ lệ đơn được chấp nhận, tạo metric domain riêng như accepted, rejected, pending; không suy từ status code đơn thuần.

### 10.1. Đo riêng business outcome

~~~java
Counter accepted = registry.counter(
        "orders.submission",
        "outcome", "accepted");
Counter rejected = registry.counter(
        "orders.submission",
        "outcome", "rejected");
~~~

Đây là custom domain metrics. Chỉ dùng label có tập giá trị hữu hạn. HTTP server request metric vẫn ghi status riêng; business counter đo kết quả nghiệp vụ.

## 11. Async request và outcome cuối cùng

Với request async hoặc streaming, thời điểm response được commit và thời điểm nghiệp vụ hoàn tất có thể khác nhau. Ví dụ server trả 202 Accepted khi đã enqueue job, nhưng job xử lý sau đó thất bại. HTTP request outcome là accepted; job execution outcome là failed.

~~~mermaid
sequenceDiagram
  participant Client
  participant API
  participant Queue
  participant Worker
  Client->>API: POST /reports
  API->>Queue: Enqueue job
  API-->>Client: 202 Accepted
  Worker->>Worker: Generate report
  Worker-->>Queue: Job failed
  Note over API,Worker: HTTP request accepted, job outcome failed
~~~

Không sửa HTTP server outcome thành ERROR chỉ vì job thất bại sau khi response hoàn tất. Tạo Observation/metrics/logs riêng cho background job, propagate context qua message nếu hỗ trợ, và liên kết job với request bằng trace context hoặc correlation key phù hợp.

Với streaming/SSE, response có thể mở lâu trước khi client ngắt kết nối. Xác định outcome theo lifecycle mà framework/server instrumentation thực sự quan sát. Client disconnect không nhất thiết là lỗi ứng dụng; phân biệt cancellation, normal completion và server exception.

## 12. Outcome, retries và dependency failures

Một server request có thể có nhiều dependency attempts. Ví dụ client gọi inventory ba lần: hai lần timeout, lần thứ ba thành công. Server response cuối là 200, nhưng dependency spans cho thấy hai retry failures.

~~~text
HTTP server observation:
  status = 200
  outcome = success

Inventory client observations:
  attempt 1 = timeout
  attempt 2 = timeout
  attempt 3 = success
~~~

Không gộp dependency outcomes thành một HTTP server outcome. Mỗi span/observation phản ánh một operation riêng. Nếu retry thành công nhưng latency tăng, metrics latency và retry counters giúp tìm vấn đề dù server request vẫn trả thành công.

Nếu mọi retry thất bại và server trả 503, server observation phản ánh response cuối, còn client spans phản ánh chi tiết các lần thử.

## 13. Security và cardinality khi ghi outcome

Outcome thường phù hợp làm low-cardinality dimension khi được chuẩn hóa. Nhưng việc đưa status, exception và route vào metrics/traces cần giới hạn.

**Nên dùng:** status code/status family theo convention; route template; outcome từ tập hữu hạn; exception type đã chuẩn hóa nếu policy cho phép; service/version/resource identity.

**Không nên dùng:** raw URL path chứa resource ID, query string, raw exception message, username/email/token, request/response body hoặc outcome value khác nhau theo mỗi request.

Exception message có thể chứa SQL, URL, user input hoặc thông tin hạ tầng. Không đưa nguyên văn vào outcome tag. Nếu cần chi tiết, dùng log/trace event có redaction và retention phù hợp.

## 14. Kiểm tra outcome bằng Actuator và backend

Một quy trình kiểm chứng đi từ request thực tế đến metrics và trace.

### Bước 1 — tạo response test

Gửi request test để nhận 2xx thành công, 4xx validation/not found/business conflict, 5xx từ dependency giả lập lỗi hoặc exception handler, và 202 async rồi job lỗi sau đó.

### Bước 2 — kiểm tra metrics endpoint

~~~http
GET /actuator/metrics/http.server.requests
~~~

Tên meter và tag có thể thay đổi theo version/instrumentation. Xem available tags và phép đo tương ứng thay vì đoán. Endpoint Actuator cần được bảo vệ; không mở rộng exposure không cần thiết trên production.

### Bước 3 — kiểm tra trace

Mở trace tương ứng và xem server span kind, route, response status, span status, exception events, trace/span IDs và client/dependency spans.

### Bước 4 — đối chiếu logs

Tìm log bằng trace ID/span ID nếu logging correlation hoạt động. Xác nhận log severity/message phản ánh đúng lỗi, không duplicate và không lộ dữ liệu.

### Bước 5 — so sánh business outcome

Đối chiếu custom business counter với HTTP status metrics. Ví dụ 401/404 có thể tăng nhưng service không nhất thiết suy giảm; 503 tăng thường cần điều tra availability. Dashboard phải đặt tên rõ HTTP error rate hay business rejection rate.

## 15. Những lỗi thường gặp khi thiết kế outcome

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Mọi 4xx bị alert như server failure | Không hiểu API contract | Tách client/business outcomes khỏi 5xx |
| 404 làm error rate tăng mạnh | Lookup miss hợp lệ | Định nghĩa HTTP/API SLI riêng |
| Exception có nhưng server outcome là success | Exception được catch/fallback và response 2xx | Quan sát dependency riêng |
| Server trả 500 nhưng span không ERROR | Custom response hoặc convention khác | Kiểm tra response mapping |
| Metrics cardinality tăng | Raw URL, ID hoặc exception message thành tag | Chuẩn hóa route/outcome |
| Outcome tag thiếu | Convention/custom filter không chạy hoặc context thiếu response | Kiểm tra lifecycle/instrumentation |
| Async job thất bại nhưng request metrics success | Request kết thúc 202 trước khi job chạy | Tạo job observation riêng |
| Client disconnect bị đếm là server error | Không phân biệt cancellation | Kiểm tra server stack semantics |
| Retry lỗi nhưng request cuối thành công bị coi là failure | Gộp dependency span với server span | Theo dõi từng operation |
| Dashboard status và outcome không khớp | Convention/version hoặc mapping khác | Kiểm tra actual tags |
| Không thấy metrics | Registry/exporter hoặc endpoint thiếu | Kiểm tra meter registration |
| Exception/log/span ghi outcome khác nhau | Mỗi tầng phân loại độc lập | Định nghĩa taxonomy và ownership |

### Quy trình điều tra

1. Xác định server observation đang đo request.
2. Xem response status cuối sau exception mapping.
3. Xem exception được xử lý/fallback hay không.
4. Kiểm tra dependency spans và retry attempts.
5. Kiểm tra outcome/status tags thực tế.
6. Kiểm tra span status/events theo convention.
7. Đối chiếu application logs và business metrics.
8. Chỉnh taxonomy/dashboard theo API contract, không chỉ theo tên exception.

## 16. Tình huống thực tế: HTTP success và business outcome

**Bối cảnh:** order-service phục vụ POST /orders. Nhiều request trả 409 khi sản phẩm hết hàng; đây không phải lỗi server. Một số request trả 503 do inventory dependency unavailable.

### Bước 1 — giữ HTTP status metrics

Metrics server request ghi nhận 2xx, 409 và 503 theo status/outcome convention. Điều này cho thấy response mà client nhận được.

### Bước 2 — tạo business metric

Thêm metric domain cho accepted, rejected vì out-of-stock và pending. Các label values hữu hạn, không chứa product ID/customer ID.

~~~text
orders.submission{outcome="accepted"}
orders.submission{outcome="rejected"}
orders.submission{outcome="pending"}
~~~

### Bước 3 — theo dõi dependency operation

Inventory client observation ghi timeout, retry count và latency. Server request trả 503 khi không thể hoàn tất theo contract.

### Bước 4 — xây dashboard riêng

- HTTP availability: tỷ lệ response 5xx hoặc request thất bại theo SLI.
- Business conversion: accepted / submission attempts.
- Dependency health: timeout/error rate của inventory client.
- Latency: HTTP server duration và dependency duration.

### Bước 5 — kiểm chứng

Gửi request out-of-stock và request inventory timeout. Xác nhận 409 không bị coi là server defect, 503 được phản ánh như availability failure, business rejected tăng ở trường hợp out-of-stock, dependency timeout metric tăng ở trường hợp timeout, trace cho thấy đúng operation.

**Bài học:** HTTP outcome, business outcome và dependency outcome trả lời các câu hỏi khác nhau. Dashboard tốt cần đặt tên đúng cho từng tỷ lệ.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân loại status và outcome

Tạo endpoint trả 200, 201, 202, 400, 401, 404, 409, 429, 500 và 503. Quan sát response status, metrics tags và server span. Xác định status nào là expected theo API contract và status nào báo availability/technical failure.

### Bài tập B — exception mapping

Tạo OrderNotFoundException map thành 404 và InventoryUnavailableException map thành 503. Dùng RestControllerAdvice tạo response. Xác minh server observation thấy status cuối và phân biệt exception event/log với HTTP outcome. Tránh log stack trace trùng.

### Bài tập C — fallback

Tạo dependency call timeout nhưng service fallback và trả 202. Xác minh server request outcome theo response accepted, trong khi client span/metric riêng vẫn phản ánh timeout.

### Bài tập D — async job

Tạo endpoint enqueue công việc và trả 202. Cho background job thất bại sau đó. Tạo observation riêng cho job và xác minh HTTP request outcome vẫn accepted trong khi job outcome là failed.

### Bài tập E — cardinality

Rà soát metric tags. Thay raw URI bằng route template; thay exception message bằng exception type/category; thay order ID bằng outcome hữu hạn. Đo số series trước/sau.

### Bài tập F — dashboard

Xây bốn panel: HTTP status/outcome, business accepted/rejected, dependency error/retry, latency. Viết alert cho server 5xx tăng mà không cảnh báo chỉ vì business 404/409 hợp lệ.

### Câu hỏi tự kiểm tra

1. Outcome khác HTTP status code như thế nào?
2. Exception được catch và fallback có nhất thiết làm server request thất bại không?
3. Vì sao 404 hoặc 409 có thể là expected business outcome?
4. Observation handler dùng lifecycle nào để ghi metrics và spans?
5. HTTP server metrics thường cần những chiều nào?
6. Vì sao route template tốt hơn raw URL?
7. Khi exception handler map lỗi thành 503, server observation thấy response nào?
8. Span status ERROR có tương đương mọi HTTP 4xx/5xx không?
9. HTTP request trả 202 nhưng job fail sau đó thì đo outcome thế nào?
10. Retry dependency thất bại nhưng request cuối thành công cần được biểu diễn ra sao?
11. Làm sao phân biệt HTTP success rate và business success rate?
12. Vì sao exception message không phù hợp làm metric tag?
13. Cách kiểm tra outcome qua Actuator và trace backend?
14. Khi nào nên dùng custom ObservationConvention?
15. Làm thế nào tránh duplicate instrumentation và duplicate error events?

**Tiêu chí hoàn thành:** giải thích outcome/status/exception; hiểu HTTP server observation lifecycle; kiểm tra metrics/span attributes; phân biệt HTTP và business outcome; xử lý fallback/async/retry; dùng cardinality thấp; xác minh qua Actuator, traces và logs.

## 18. Ghi nhớ

- Outcome phân loại kết quả operation; HTTP status mô tả response theo giao thức; exception mô tả tình huống runtime. Chúng liên quan nhưng không đồng nghĩa.
- HTTP server Observation theo dõi request lifecycle và có thể cung cấp status, route, duration, error context cho metrics/tracing handlers.
- Không xem mọi 4xx là server defect. 401, 404, 409 hoặc 429 có thể là kết quả được API dự kiến.
- Exception được catch/fallback có thể không làm HTTP request thất bại; dependency operation vẫn cần được quan sát riêng.
- Dùng route template và outcome values hữu hạn cho metrics; không đưa raw URL, IDs hoặc exception message vào tags.
- HTTP success rate không phải business success rate. Tạo business metrics riêng khi cần đo accepted/rejected/pending.
- Request trả 202 và background job thất bại cần hai observations/outcomes riêng.
- Dùng Actuator metrics, trace span status/events và logs để đối chiếu kết quả. Kiểm tra convention/version thay vì giả định tag names.
- Custom ObservationConvention chỉ nên thêm metadata thực sự cần, low-cardinality và tương thích web stack.
- Định nghĩa outcome theo API contract, giữ ownership rõ và không tạo span/metric trùng.

## Tài liệu tham khảo

- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — HTTP](https://opentelemetry.io/docs/specs/semconv/http/)
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

