# Bổ sung telemetry và đánh giá chi phí trên mỗi request

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao một Java serverless API cần đo request, dependency, retry, dữ liệu truyền và thời gian thực thi.
- Phân biệt metrics, structured logs và distributed traces; chọn đúng tín hiệu cho từng câu hỏi vận hành.
- Thiết kế telemetry theo route và outcome với cardinality có kiểm soát.
- Instrument Java handler/use case bằng Micrometer và OpenTelemetry.
- Theo dõi cold start, latency, lỗi, concurrency, downstream calls, payload bytes và retry.
- Xây dựng mô hình chi phí trên mỗi request từ function compute, invocation, API gateway, database, network và observability.
- Phân bổ chi phí dùng chung cho service hoặc workload bằng driver có thể giải thích.
- Tính cost per attempted request và cost per successful request, rồi dùng số liệu để ưu tiên tối ưu.
- Thiết kế dashboard, alert và quy trình đối chiếu telemetry với billing export.

## 1. Vì sao cần telemetry và unit economics cho serverless API?

Một API serverless có thể tự động mở rộng theo request, nhưng khả năng scale không tự giải thích được điều gì xảy ra bên trong mỗi request. Một endpoint có thể chậm vì cold start, truy vấn database, gọi API đối tác, retry hoặc serialize payload lớn. Hóa đơn có thể tăng dù số request gần như không đổi vì thời gian thực thi tăng, downstream call nhiều hơn, data transfer tăng hoặc log quá chi tiết.

Telemetry cung cấp dữ liệu để trả lời các câu hỏi:

- API có đáp ứng latency mục tiêu không?
- Route nào tạo nhiều lỗi hoặc retry?
- Function mất bao lâu ở cold start và warm execution?
- Dependency nào chiếm phần lớn thời gian của request?
- Mỗi request truyền bao nhiêu byte?
- Chi phí tăng do traffic, do lỗi hay do thay đổi kiến trúc?
- Một giao dịch nghiệp vụ thành công thực sự tốn bao nhiêu?

Unit economics chuyển chi phí tổng thành một đơn vị có ý nghĩa với sản phẩm. Với API, đơn vị đó có thể là một request được chấp nhận, một request hoàn tất thành công, một order được tạo hoặc một tác vụ được xử lý.

### 1.1. Invocation không đồng nghĩa với business request

Một HTTP request có thể tạo nhiều function invocation nếu hệ thống retry hoặc fan-out. Ngược lại, một function invocation có thể xử lý batch gồm nhiều message hoặc nhiều operation.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Client request | Lời gọi từ client đến API | Client gửi POST /orders |
| Function invocation | Một lần runtime gọi function | Lambda/function handler chạy |
| Attempt | Một lần thử xử lý operation | Lần đầu và các lần retry |
| Dependency call | Lời gọi từ function đến service khác | Query database hoặc gọi payment API |
| Successful operation | Kết quả nghiệp vụ hoàn tất đúng | Một order được tạo và commit |
| Billable unit | Đơn vị được provider tính phí | Request, GB-second, GB transfer hoặc log ingestion |

Không dùng số invocation làm mẫu số duy nhất cho mọi phép đo. Nếu một invocation xử lý batch 100 message, cost per invocation và cost per message trả lời hai câu hỏi khác nhau.

### 1.2. Telemetry phải gắn với hành vi nghiệp vụ

Chỉ đo HTTP status chưa đủ. Ví dụ, API trả 200 nhưng một phần nghiệp vụ được đưa vào hàng đợi để xử lý sau. Khi đó cần phân biệt request đã được tiếp nhận với operation đã hoàn thành.

Đặt tên outcome rõ ràng:
- `accepted`: API xác nhận đã nhận yêu cầu.
- `succeeded`: nghiệp vụ đã hoàn tất.
- `rejected`: request không hợp lệ hoặc không được phép.
- `failed`: xử lý thất bại.
- `retrying`: operation đang được thử lại.

Tên và định nghĩa phải nhất quán giữa metric, log, trace và dashboard. Không gọi trạng thái accepted là success nếu sản phẩm cần theo dõi kết quả bất đồng bộ đến cuối workflow.

### 1.3. Mô hình quan sát toàn request

~~~mermaid
flowchart LR
    A[Client] --> B[API Gateway]
    B --> C[Java Function]
    C --> D[Database]
    C --> E[Payment API]
    C --> F[Queue]
    C --> G[Logs / Metrics / Traces]
    G --> H[Dashboard and Cost Model]
~~~

Một request có thể tạo phí ở nhiều điểm. Telemetry cần ghi nhận request ở entry point, các dependency quan trọng và kết quả cuối. Billing export cung cấp chi phí thực tế ở cấp SKU/resource; application telemetry giải thích workload nào tạo ra mức sử dụng đó.

## 2. Ba tín hiệu chính: metrics, logs và traces

Ba loại telemetry bổ sung cho nhau. Chúng không thay thế lẫn nhau.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Điều gì đang tăng/giảm theo thời gian? | Request rate, error rate, p95 latency |
| Structured logs | Điều gì đã xảy ra trong một lần xử lý? | Validation failed, payment timeout |
| Distributed traces | Thời gian đi qua các thành phần nào? | Gateway → function → database → payment API |

### 2.1. Metrics

Metric là số liệu được tổng hợp theo thời gian. Với API serverless, các metric cơ bản gồm:

- Request count theo route, method và outcome.
- Request duration histogram và p50/p95/p99.
- Error count theo loại lỗi hoặc dependency.
- Concurrent executions và throttled requests.
- Cold start count/duration nếu nền tảng cung cấp.
- Downstream latency, timeout và retry count.
- Request/response payload bytes.
- Queue age, batch size và redelivery nếu API khởi tạo xử lý bất đồng bộ.

Dùng histogram/distribution để quan sát percentile. Average latency có thể che giấu một nhóm request rất chậm. Đặt bucket phù hợp với SLO, ví dụ 50 ms, 100 ms, 250 ms, 500 ms, 1 s và 2 s; điều chỉnh theo mục tiêu thực tế.

### 2.2. Structured logs

Log dạng JSON giúp truy vấn và tổng hợp dễ hơn. Một record có thể chứa:

~~~json
{
  "timestamp": "2026-11-17T10:15:30.125Z",
  "level": "INFO",
  "service": "orders-api",
  "environment": "production",
  "route": "POST /orders",
  "outcome": "succeeded",
  "status_code": 201,
  "duration_ms": 84,
  "request_id": "req-7f21",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "dependency_calls": 2,
  "retry_count": 0,
  "request_bytes": 420,
  "response_bytes": 180
}
~~~

Đây là ví dụ cấu trúc, không phải schema bắt buộc. Log phải hữu ích cho điều tra nhưng tránh ghi token, password, secret, dữ liệu thanh toán hoặc payload cá nhân. Chỉ ghi identifier đã được phê duyệt và có thời hạn retention phù hợp.

### 2.3. Distributed traces

Trace mô tả một request đi qua nhiều thành phần. Mỗi span đại diện cho một đoạn công việc: nhận HTTP request, đọc database, gọi payment API hoặc publish message.

~~~mermaid
flowchart TD
    A[HTTP server span] --> B[Validate and map]
    B --> C[CreateOrder use case]
    C --> D[Database span]
    C --> E[Payment API span]
    C --> F[Publish event span]
~~~

Trace giúp phân biệt function duration với thời gian chờ downstream. Nếu function mất 900 ms nhưng database span chỉ 40 ms và payment span 700 ms, nhóm có hướng điều tra rõ hơn.

Dùng W3C Trace Context (`traceparent`) hoặc propagation format mà nền tảng hỗ trợ để truyền trace context qua HTTP và message. Khi message được xử lý bất đồng bộ, consumer có thể tạo trace mới liên kết với trace gốc bằng span link nếu quan hệ không phải parent-child thông thường.

### 2.4. Không bật mọi telemetry ở mức tối đa

Logs và traces cũng tạo chi phí. Log toàn bộ payload, bật debug liên tục hoặc trace 100% traffic có thể làm hóa đơn tăng nhanh. Chọn mức telemetry theo giá trị điều tra:

- Metrics có thể thu thập thường xuyên với cardinality được kiểm soát.
- Logs ghi sự kiện có ý nghĩa, có sampling hoặc retention theo môi trường.
- Traces lấy mẫu có chiến lược, tăng sampling cho lỗi hoặc request chậm nếu backend hỗ trợ tail sampling.
- Debug log chỉ bật tạm thời, có người chịu trách nhiệm và thời điểm tắt.

## 3. Thiết kế telemetry cho Java serverless API

Trước khi viết instrumentation, xác định một bộ metric và thuộc tính thống nhất. Dùng route template thay cho URL đầy đủ để tránh mỗi ID tài nguyên tạo một time series riêng.

### 3.1. Metric catalog gợi ý

| Metric | Kiểu | Thuộc tính an toàn | Mục đích |
|---|---|---|---|
| `api.server.requests` | Counter | route, method, outcome | Request volume |
| `api.server.duration` | Histogram | route, method, outcome | Latency và SLO |
| `api.server.request.bytes` | Distribution | route | Payload nhận vào |
| `api.server.response.bytes` | Distribution | route | Payload trả ra |
| `api.dependency.duration` | Histogram | dependency, operation, outcome | Downstream latency |
| `api.dependency.calls` | Counter | dependency, outcome | Fan-out và lỗi |
| `api.retry.attempts` | Counter | dependency, reason | Retry amplification |
| `api.cold_start` | Counter | runtime, function | Cold start frequency |
| `api.concurrent.executions` | Gauge/provider metric | function, environment | Capacity |
| `api.business.operations` | Counter | operation, outcome | Kết quả nghiệp vụ |

Tên metric là ví dụ. Nếu dùng OpenTelemetry semantic conventions hoặc Micrometer conventions của tổ chức, hãy thống nhất một chuẩn thay vì tạo hai bộ metric trùng nhau.

### 3.2. Label cardinality

Mỗi tổ hợp label có thể tạo một time series. Không dùng giá trị có vô số khả năng làm label:

- Không dùng `request_id`, `trace_id`, email, user ID hoặc order ID làm metric label.
- Không dùng full URL chứa path parameter.
- Không dùng exception message tự do.
- Không dùng raw SQL hoặc hostname có thể thay đổi theo tenant.

Dùng route template như `/orders/{orderId}` hoặc route name `orders.get`. Identifier duy nhất nên nằm trong trace/log có kiểm soát, không nằm trong label metric.

### 3.3. Phân loại outcome nhất quán

Không gom mọi response 4xx và 5xx thành một outcome duy nhất nếu cần điều tra. Có thể dùng nhóm có cardinality thấp:

- `success`
- `client_error`
- `server_error`
- `timeout`
- `throttled`

Tùy API, `401` hoặc `403` có thể là expected security outcome, còn `429` cần được theo dõi riêng. Định nghĩa SLO theo hành vi sản phẩm, không chỉ theo status class.

### 3.4. Đo request lifecycle

Bắt đầu timer ở entry point và dừng sau khi response hoặc kết quả invocation đã được xác định. Đo thêm các đoạn quan trọng:
- Authentication và authorization.
- Parse/validation.
- Application use case.
- Database query/transaction.
- External API.
- Serialization và response.

Không cộng duration của các span song song như thể chúng là thời gian tuần tự. Request wall-clock duration và tổng dependency duration là hai đại lượng khác nhau.

### 3.5. Đo bytes và số lần gọi

Payload bytes giúp phát hiện request lớn, response phình to và egress tăng. Đếm số dependency call giúp phát hiện N+1 query hoặc fan-out tăng.

Đo ở application layer cho biết payload logic; billing có thể tính thêm header, protocol overhead, retransmission hoặc các loại traffic khác. Đối chiếu application byte metrics với network/billing metrics thay vì coi chúng là cùng một số.

### 3.6. Cold start và warm execution

Cold start thường gồm thời gian khởi tạo runtime, tải artifact, khởi tạo framework và tạo client. Nền tảng có thể cung cấp metric riêng; ưu tiên provider metric làm nguồn chuẩn nếu có.

Có thể ghi nhận first invocation trong một execution environment bằng state chỉ phục vụ chẩn đoán, nhưng không dùng nó làm định nghĩa billing chính xác. Một static flag chỉ quan sát được vòng đời instance mà code đang thấy; platform có thể đo initialization theo cách khác.

### 3.7. Retry và fan-out

Ghi attempt count ở dependency adapter hoặc retry wrapper, không chỉ tại function handler. Nếu SDK tự retry, bật instrumentation/interceptor để đo số attempt thật.

Với một request gọi nhiều dependency, ghi:
- Dependency name đã chuẩn hóa.
- Operation name.
- Attempt count.
- Outcome.
- Duration.
- Payload bytes nếu có.
- Timeout/throttle classification.

Không đưa credential, full URL có query secret hoặc nội dung nhạy cảm vào span attribute.

## 4. Instrument Java code với Micrometer và OpenTelemetry

Nên dùng instrumentation tự động của runtime/framework khi có thể, sau đó bổ sung custom telemetry cho khái niệm nghiệp vụ mà auto-instrumentation không biết. Tránh tạo một tracer/metric exporter riêng nếu platform agent đã cung cấp SDK hoặc collector chuẩn.

### 4.1. Đo request bằng Micrometer

Ví dụ dưới đây minh họa cách đo request ở application adapter. Metric tags chỉ chứa route template, method và outcome có cardinality thấp.

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.function.Supplier;

public final class ApiTelemetry {

    private final MeterRegistry registry;

    public ApiTelemetry(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T recordRequest(
            String route,
            String method,
            long requestBytes,
            Supplier<T> operation) {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.get();
        } catch (ClientInputException exception) {
            outcome = "client_error";
            throw exception;
        } catch (RuntimeException exception) {
            outcome = "server_error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("api.server.duration")
                    .tag("route", route)
                    .tag("method", method)
                    .tag("outcome", outcome)
                    .register(registry));

            registry.counter(
                    "api.server.requests",
                    "route", route,
                    "method", method,
                    "outcome", outcome).increment();

            DistributionSummary.builder("api.server.request.bytes")
                    .tag("route", route)
                    .register(registry)
                    .record(requestBytes);
        }
    }

    public void recordResponseBytes(String route, long responseBytes) {
        DistributionSummary.builder("api.server.response.bytes")
                .tag("route", route)
                .register(registry)
                .record(responseBytes);
    }
}
~~~

Các class exception trong ví dụ là kiểu application minh họa. Trong ứng dụng thực tế, phân loại exception phải dựa trên contract API. Không biến mọi exception thành `server_error`: validation, authorization, throttling và dependency timeout có thể cần outcome riêng.

Đo response bytes sau khi serializer tạo payload hoặc tại HTTP adapter, nơi biết chính xác byte được gửi. Không dùng độ dài Java String thay cho byte length nếu encoding là UTF-8 hoặc payload đã nén.

### 4.2. Đo dependency call và retry

Có thể bọc outbound port hoặc HTTP client bằng decorator:

~~~java
public final class TimedPaymentGateway implements PaymentGateway {

    private final PaymentGateway delegate;
    private final MeterRegistry registry;

    public TimedPaymentGateway(
            PaymentGateway delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public PaymentResult charge(PaymentCommand command) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return delegate.charge(command);
        } catch (PaymentTimeoutException exception) {
            outcome = "timeout";
            throw exception;
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("api.dependency.duration")
                    .tag("dependency", "payment")
                    .tag("operation", "charge")
                    .tag("outcome", outcome)
                    .register(registry));

            registry.counter(
                    "api.dependency.calls",
                    "dependency", "payment",
                    "operation", "charge",
                    "outcome", outcome).increment();
        }
    }
}
~~~

Nếu retry được triển khai ở HTTP client hoặc SDK, decorator bên ngoài có thể chỉ thấy một logical call. Hãy instrument retry interceptor hoặc wrapper để đếm từng attempt. Có thể dùng metric `api.retry.attempts` với tag `dependency` và `reason` như `timeout`, `throttle`, `connection_reset`.

Đặt giới hạn retry và timeout rõ ràng. Retry vô hạn làm tăng request count, function duration, dependency charge và network usage. Nếu client đã retry, gateway cũng retry hoặc consumer redelivery, hãy xác định từng tầng để tránh nhân số attempt ngoài dự kiến.

### 4.3. Tạo span với OpenTelemetry

OpenTelemetry Java API có thể tạo span thủ công cho một use case hoặc dependency chưa được auto-instrument:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class CreateOrderTracing {

    private final Tracer tracer;
    private final CreateOrderUseCase useCase;

    public CreateOrderTracing(
            Tracer tracer,
            CreateOrderUseCase useCase) {
        this.tracer = tracer;
        this.useCase = useCase;
    }

    public CreateOrderResult execute(CreateOrderCommand command) {
        Span span = tracer.spanBuilder("orders.create")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("app.operation", "create_order");
            span.setAttribute("app.item_count", command.items().size());

            return useCase.create(command);
        } catch (RuntimeException exception) {
            span.recordException(exception);
            span.setStatus(StatusCode.ERROR);
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

Phần này tạo span nội bộ cho use case. HTTP server instrumentation thường đã tạo server span. Không tạo thêm server span thủ công nếu auto-instrumentation đã tạo một span tương đương, vì trace sẽ bị đếm trùng.

### 4.4. Truyền trace context

- Giữ W3C Trace Context hoặc format chuẩn đã chọn.
- Propagate context qua HTTP client và message metadata.
- Khi consumer chạy bất đồng bộ, liên kết trace theo semantics của message.
- Ghi `trace_id` và `span_id` trong structured logs nếu backend chưa tự liên kết.
- Không dùng trace ID làm metric label.
- Không tự tạo correlation ID mới ở mỗi tầng nếu đã có request/trace context hợp lệ.

Nếu một request gọi service ngoài tổ chức, chỉ truyền trace context khi chính sách bảo mật và đối tác cho phép. Trace context có thể tiết lộ cấu trúc hệ thống hoặc liên kết hoạt động giữa các dịch vụ.

### 4.5. Đo cold start

Ưu tiên metric nền tảng như initialization duration, cold start count hoặc startup latency. Nếu runtime không cung cấp metric, có thể ghi nhận lần invocation đầu tiên của execution environment bằng một cờ chỉ phục vụ quan sát:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeLifecycleMetric {

    private static final AtomicBoolean FIRST_INVOCATION =
            new AtomicBoolean(true);

    public boolean markFirstInvocation() {
        return FIRST_INVOCATION.compareAndSet(true, false);
    }
}
~~~

Cờ này chỉ đánh dấu invocation đầu tiên mà instance Java hiện tại quan sát được. Nó không phải nguồn đo cold start chính xác cho mọi nền tảng, không đại diện cho mọi lần initialize của provider và không được dùng để tính hóa đơn. Không lưu request-specific data trong static field.

### 4.6. Logging an toàn trong Java

Dùng logger dạng structured logging hoặc JSON encoder. Một log event nên có service, environment, route, outcome, duration, request ID và trace ID. Dùng allowlist cho field được ghi.

Không log:
- Authorization header, cookie, API key hoặc secret.
- Toàn bộ request/response body theo mặc định.
- Dữ liệu thẻ, tài khoản, định danh cá nhân hoặc thông tin nhạy cảm.
- SQL bind values nếu chứa dữ liệu người dùng.
- URL có query parameter chứa token.

Nếu cần điều tra payload, dùng sampling có kiểm soát, masking và thời gian bật giới hạn. Kiểm tra log ở cả application lẫn platform vì một request có thể bị ghi hai lần.

## 5. Từ telemetry đến dashboard và SLO

Dashboard cần phản ánh các câu hỏi vận hành. Một dashboard có hàng trăm metric nhưng không giúp xác định route, dependency hoặc cost driver sẽ ít hữu ích.

### 5.1. Dashboard API overview

Nên có các panel:
- Request rate theo route.
- Success/rejection/error rate.
- p50, p95 và p99 duration.
- Throttled request và concurrency.
- Cold start count/duration.
- Request/response bytes.
- Dependency latency và error rate.
- Retry attempts và queue age.
- Cost estimate per request và cost per successful operation.

Giữ bộ lọc theo service, environment, region và version. Chỉ thêm tenant hoặc customer nếu số lượng nhỏ, được phép và cần thiết; nếu cardinality lớn, dùng log query hoặc cost report riêng.

### 5.2. SLO và error budget

Ví dụ SLO:
- 99,9% request hợp lệ hoàn tất dưới 500 ms trong cửa sổ 30 ngày.
- 99,95% operation tạo order được xử lý thành công trong 24 giờ.
- Tỷ lệ lỗi do dependency dưới một ngưỡng đã thống nhất.

SLO phải định nghĩa rõ population, loại request bị loại trừ và cách tính. Không tính request bị client hủy như lỗi server nếu contract không quy định như vậy. Với async workflow, đo thời gian từ accepted đến terminal outcome, không chỉ thời gian HTTP trả 202.

### 5.3. Alert theo triệu chứng và nguyên nhân

Ưu tiên alert về:
- Error rate tăng.
- p95/p99 vượt SLO.
- Throttling hoặc concurrency saturation.
- Queue age vượt ngưỡng.
- Retry ratio tăng đột biến.
- Dependency timeout.
- Cost per successful operation tăng.
- NAT/data transfer/log ingestion tăng bất thường.

Alert theo triệu chứng giúp biết người dùng bị ảnh hưởng; alert theo nguyên nhân giúp khoanh vùng. Không gửi alert cho mọi exception đơn lẻ nếu tỷ lệ và tác động chưa vượt ngưỡng.

### 5.4. Tách metric platform và application

Platform metric có thể cho biết invocation, duration, memory, throttling và concurrency. Application metric cho biết route, outcome nghiệp vụ, dependency và payload. Cần giữ hai góc nhìn để tránh suy diễn từ metric runtime sang hành vi sản phẩm.

Ví dụ, function invocation thành công không có nghĩa payment đã được capture. Một function trả lỗi do validation có thể vẫn là hành vi đúng và không nên tính như server failure.

## 6. Mô hình chi phí trên mỗi request

Serverless billing thường gồm nhiều dòng chi phí. Cấu trúc cụ thể phụ thuộc provider, runtime, region, tier và dịch vụ đi kèm. Mô hình dưới đây dùng để phân tích và phân bổ; giá thực tế phải lấy từ billing export hoặc pricing calculator của đúng nền tảng.

### 6.1. Nhóm chi phí trực tiếp

| Thành phần | Driver thường dùng | Ví dụ |
|---|---|---|
| Function request/invocation | Số invocation hoặc request | 1 lần handler được gọi |
| Function compute | Memory × duration hoặc đơn vị compute của provider | 512 MiB chạy 180 ms |
| Provisioned/minimum capacity | Thời gian capacity được giữ | Provisioned concurrency hoặc minimum instances |
| API gateway | Request, data processing hoặc tier | 1 request qua API Gateway |
| Database/cache | Query, read/write, capacity hoặc compute | Một lần đọc và ghi |
| External API | Request, transaction hoặc license | Một lần gọi payment provider |
| Network | GB egress, NAT processing, cross-zone/region | 20 KB response và downstream payload |
| Logs/traces/metrics | Ingestion, retention, query hoặc sample volume | 1 KB log và một số span |
| Queue/event | Request, message, operation hoặc data transfer | Publish và consume event |
| Retry | Attempt bổ sung ở function và dependency | Một request được thử lại |

Function compute có thể được tính theo memory/duration, vCPU-second, request, execution time hoặc mô hình khác. Một số provider tính theo GB-second và số request; một số plan có grant miễn phí hoặc minimum charge. Đừng dùng cùng một công thức cho mọi nền tảng.

### 6.2. Chi phí trực tiếp và chi phí dùng chung

Tách thành:

\[
C_{\text{total}} =
C_{\text{direct}} + C_{\text{shared}}
\]

Trong đó:

- `C_direct`: chi phí gắn trực tiếp với API/service, như function, gateway, database request và egress đo được.
- `C_shared`: chi phí tài nguyên dùng chung, như NAT Gateway, VPC connector, private endpoint, observability platform, shared database baseline hoặc provisioned capacity.

Một NAT dùng chung cho nhiều service không nên được gán toàn bộ vào một API nếu API chỉ dùng một phần. Cần quy tắc allocation có thể giải thích và áp dụng nhất quán.

### 6.3. Công thức tổng quát

Có thể mô hình hóa:

\[
C_{\text{direct}} =
C_{\text{invocation}} +
C_{\text{compute}} +
C_{\text{gateway}} +
C_{\text{dependency}} +
C_{\text{network}} +
C_{\text{observability}} +
C_{\text{retry}}
\]

\[
C_{\text{service}} =
C_{\text{direct}} + \alpha C_{\text{shared}}
\]

\[
C_{\text{per successful operation}} =
\frac{C_{\text{service}}}{N_{\text{successful operations}}}
\]

Trong đó \(\alpha\) là phần chi phí shared được phân bổ cho service. Tổng phần phân bổ của các service phải bằng tổng chi phí shared trong cùng scope và kỳ.

### 6.4. Ước tính function compute

Với mô hình GB-second, phép tính khái niệm:

\[
GBs = Memory_{GB} \times Duration_{seconds} \times Invocations
\]

\[
C_{\text{compute}} = GBs \times Price_{\text{GB-second}}
\]

Memory phải đổi sang GB theo đơn vị bảng giá. Duration dùng thời gian billable theo provider, có thể có quy tắc làm tròn hoặc mức tối thiểu. Một số runtime/plan tính CPU, memory, request và concurrency theo mô hình khác.

Với provisioned concurrency hoặc minimum instances, tính riêng chi phí capacity được giữ ngay cả khi không có request. Đây có thể là khoản lớn nếu API có traffic thấp nhưng cần latency ổn định.

### 6.5. Tính chi phí retry

Nếu một request có trung bình \(a\) attempts, số lần function/dependency xử lý có thể cao hơn số request gốc:

\[
N_{\text{attempts}} = N_{\text{requests}} \times a
\]

Đây là phép xấp xỉ khi attempts trung bình được đo theo cùng population. Với retry lồng nhau ở client, gateway, function SDK và message broker, phải đo từng tầng; không nhân các retry ratio một cách máy móc nếu các population khác nhau.

Retry có thể làm tăng:
- Invocation và compute duration.
- Database read/write.
- External API transaction.
- Network bytes và NAT processing.
- Log/trace volume.
- Queue operation và redelivery.

### 6.6. Cost per request và cost per successful operation

Hai chỉ số hữu ích:

\[
C_{\text{per attempt}} =
\frac{C_{\text{service}}}{N_{\text{attempts at the measured boundary}}}
\]

\[
C_{\text{per accepted request}} =
\frac{C_{\text{service}}}{N_{\text{accepted client requests}}}
\]

\[
C_{\text{per successful operation}} =
\frac{C_{\text{service}}}{N_{\text{successful business operations}}}
\]

Nếu một request được chấp nhận nhưng workflow thất bại, nó vẫn tiêu tốn compute/network. Vì vậy cost per successful operation thường cao hơn cost per accepted request khi success rate thấp hoặc retry tăng.

Mẫu số của cost per attempt phải chỉ rõ boundary: function invocation, message delivery hay dependency call. Không so sánh hai con số dùng population khác nhau. Nếu API trả 202 và xử lý trong queue, hãy đo cả chi phí tiếp nhận lẫn chi phí hoàn tất workflow. Không chia cost của toàn workflow cho số HTTP 202 nếu muốn biết cost để hoàn tất operation.

## 7. Ví dụ tính cost per successful operation

Giả sử một Java API chạy trong một tháng có số liệu tổng hợp sau. Đây là số giả định để minh họa phương pháp, không phải báo giá của bất kỳ cloud provider nào.

### 7.1. Volume và giả định

| Driver | Giá trị giả định |
|---|---:|
| Client requests được API chấp nhận | 5.000.000 |
| Function invocations sau retry | 5.200.000 |
| Business operations hoàn tất thành công | 4.850.000 |
| Memory trung bình | 512 MiB = 0,5 GiB |
| Duration billable trung bình | 180 ms = 0,18 giây |
| Compute price minh họa | 0,00001667 USD/GB-second |
| Invocation price minh họa | 0,20 USD/1 triệu invocation |
| API gateway price minh họa | 1,00 USD/1 triệu request |

### 7.2. Ước tính compute và invocation

GB-second:

\[
0,5 \times 0,18 \times 5.200.000
= 468.000\ GB\text{-}seconds
\]

Chi phí compute:

\[
468.000 \times 0,00001667
\approx 7,80\ USD
\]

Chi phí invocation:

\[
5,2 \times 0,20 = 1,04\ USD
\]

Gateway xử lý 5 triệu client request:

\[
5 \times 1,00 = 5,00\ USD
\]

### 7.3. Tổng hợp các khoản chi phí

Giả sử billing export và allocation nội bộ cho thấy:

| Khoản phí | Chi phí tháng |
|---|---:|
| Function compute | 7,80 USD |
| Function invocation | 1,04 USD |
| API gateway | 5,00 USD |
| Database/cache | 20,00 USD |
| Network egress và data processing biến đổi theo request | 4,00 USD |
| Logs, metrics và traces | 2,50 USD |
| Phần NAT/endpoint dùng chung phân bổ cho API | 120,00 USD |
| Phần observability platform dùng chung | 30,00 USD |
| **Tổng chi phí được phân bổ** | **190,34 USD** |

Trong ví dụ này, hai khoản shared đã được phân bổ cho API theo chính sách nội bộ; không phải toàn bộ hóa đơn shared infrastructure của tổ chức. Dòng network 4 USD là phần usage biến đổi được gán trực tiếp; 120 USD là phần baseline/shared NAT và endpoint đã phân bổ, không tính lặp cùng một SKU.

Cost per accepted request:

\[
190,34 / 5.000.000
= 0,000038068\ USD
\]

Tương đương khoảng 0,0381 USD cho 1.000 request được chấp nhận.

Cost per successful business operation:

\[
190,34 / 4.850.000
\approx 0,000039245\ USD
\]

Tương đương khoảng 0,0392 USD cho 1.000 operation thành công.

Khoảng chênh giữa hai chỉ số phản ánh việc có request đã được chấp nhận nhưng không hoàn tất thành công. Khi success rate giảm hoặc retry tăng, cost per successful operation có thể tăng ngay cả khi cost per accepted request ít thay đổi.

### 7.4. Diễn giải kết quả

Trong ví dụ này, function compute chỉ chiếm một phần nhỏ của tổng chi phí. Hai khoản shared network và observability chiếm phần lớn. Tối ưu memory của function có thể không tạo ra thay đổi đáng kể bằng việc phân bổ NAT chính xác, giảm traffic qua NAT hoặc giảm log ingestion.

Đừng kết luận chỉ từ một tháng. So sánh nhiều kỳ, điều chỉnh theo volume và mix request, đồng thời kiểm tra đơn giá/tier có thay đổi không.

## 8. Phân bổ chi phí dùng chung và FinOps

Billing export thường ghi nhận chi phí ở cấp account, project, subscription, resource hoặc SKU. Một API có thể dùng NAT, database, gateway, log workspace và tracing backend chung với nhiều service. Cần có cách phân bổ để team hiểu phần chi phí mình tạo ra.

### 8.1. Tag và label

Gắn metadata cho resource hỗ trợ tagging:

- `service`: tên service hoặc API.
- `team`: team chịu trách nhiệm.
- `environment`: dev, staging, production.
- `cost-center`: mã trung tâm chi phí.
- `region`: region triển khai.
- `managed-by`: repository hoặc IaC owner.
- `version`: deployment version nếu hữu ích.

Không phải managed service nào cũng hỗ trợ tag đầy đủ. Khi thiếu tag, kết hợp resource ID, project/account, subnet, route, log group và deployment metadata.

### 8.2. Chọn allocation driver

| Shared resource | Driver phù hợp có thể dùng | Lưu ý |
|---|---|---|
| NAT Gateway | Bytes processed theo service/subnet | Dùng flow logs hoặc network telemetry |
| Private endpoint | Bytes hoặc request đến endpoint | Có thể cần phân bổ phí hourly theo số consumer |
| Shared database | Query units, read/write, storage hoặc connection usage | Đừng chỉ dùng request count nếu query khác độ nặng |
| Log workspace | Ingested bytes theo service/log group | Tách debug log và audit log |
| Trace backend | Span count hoặc ingested GB | Sampling rate ảnh hưởng volume |
| Shared gateway | Request count và data processed | Route có payload size khác nhau |
| Provisioned capacity | Reserved capacity hoặc peak concurrency share | Có thể cần kết hợp baseline và peak usage |

### 8.3. Công thức phân bổ theo usage

Một công thức đơn giản:

\[
C_{\text{service}} =
C_{\text{shared pool}} \times
\frac{Usage_{\text{service}}}{Usage_{\text{all consumers}}}
\]

Ví dụ NAT dùng chung xử lý 1.000 GB trong tháng. API A tạo 300 GB, API B tạo 500 GB và API C tạo 200 GB. Nếu phân bổ toàn bộ phí processing theo bytes, API A nhận 30%, API B 50%, API C 20%.

Phí hourly có thể phân bổ theo cùng driver nếu đó là quy tắc tổ chức chọn, nhưng phải công bố rõ. Nếu một service yêu cầu NAT luôn sẵn sàng dù không có traffic, có thể phân bổ baseline theo capacity/ownership thay vì chỉ theo bytes.

### 8.4. Showback và chargeback

- **Showback:** báo cáo cho team biết họ đang tiêu thụ và tạo chi phí nào.
- **Chargeback:** chuyển chi phí đã phân bổ vào ngân sách hoặc cost center của team.

Trước khi chargeback, cần xác minh mapping resource, owner, usage driver và xử lý late-arriving billing data. Không coi allocation nội bộ là số tiền provider trực tiếp charge cho team.

### 8.5. Đối chiếu billing với application telemetry

Dùng billing export để xác định chi phí thực tế theo SKU/usage type. Dùng metrics/logs/traces để giải thích workload. Đối chiếu theo cùng time window và scope:

1. Chọn account/project/subscription, region và service.
2. Lọc các SKU liên quan đến function, gateway, network, database và observability.
3. Lấy invocation, duration, memory, bytes và request count từ provider/application metrics.
4. So sánh volume với billing quantity, lưu ý GB/GiB và quy tắc rounding.
5. Xác định resource shared và allocation driver.
6. Ghi nhận sai lệch, ví dụ log ingestion hoặc NAT traffic không được application đo trực tiếp.
7. Cập nhật mô hình unit cost và giải thích biến động.

Billing data có thể đến trễ và được điều chỉnh sau kỳ. Đánh dấu báo cáo là estimated hay finalized để tránh so sánh số chưa chốt với hóa đơn cuối.

## 9. Khác biệt giữa các cloud provider

Các provider dùng tên dịch vụ và cách tính khác nhau. Hãy map telemetry chung của ứng dụng với metric và billing export tương ứng.

### 9.1. AWS Lambda và API Gateway

Những driver cần kiểm tra:
- Lambda requests và duration/memory GB-second.
- Architecture/runtime và các hệ số tính giá liên quan.
- Provisioned concurrency nếu bật.
- Ephemeral storage vượt phần bao gồm nếu áp dụng.
- API Gateway request/data processing và cache nếu có.
- CloudWatch Logs ingestion, retention và metric charges.
- X-Ray hoặc OpenTelemetry trace export.
- NAT Gateway, VPC endpoint và data transfer.
- Downstream DynamoDB, RDS, SQS, EventBridge hoặc external API.

Lambda platform metrics cho biết invocation, duration, errors, throttles và concurrency. Application telemetry bổ sung route, business outcome và dependency. Không suy ra cost per business operation chỉ từ Lambda duration.

### 9.2. Google Cloud Functions / Cloud Run functions

Những driver cần kiểm tra:
- Request, CPU/memory allocation và duration theo execution model/region.
- Minimum instances hoặc minimum capacity nếu cấu hình.
- Networking qua VPC connector hoặc Direct VPC egress.
- Cloud Logging ingestion/retention.
- Cloud Trace/Monitoring và sampling.
- Cloud NAT, Private Service Connect và data transfer.
- Chi phí database, Pub/Sub, Eventarc và dịch vụ downstream.

Cloud Run functions sử dụng nền tảng Cloud Run cho execution. Cần kiểm tra đúng generation, region, CPU/memory, concurrency và billing model thay vì dùng một mức giá chung cho mọi function.

### 9.3. Azure Functions

Những driver cần kiểm tra:
- Consumption executions và execution time/memory theo plan.
- Flex Consumption, Premium hoặc Dedicated plan nếu dùng.
- Always-ready instances hoặc prewarmed capacity nếu cấu hình.
- Application Insights/Log Analytics ingestion và retention.
- NAT Gateway, Private Endpoint, VNet integration và egress.
- Storage account, queue và downstream services.

Azure Functions có nhiều hosting plan. Một workload chuyển từ Consumption sang Premium có thể thay đổi đáng kể phần fixed/minimum capacity. So sánh theo plan thực tế và region.

### 9.4. Chuẩn hóa mô hình thay vì chuẩn hóa đơn giá

Giữ một schema nội bộ chung cho:
- Requests accepted/succeeded/failed.
- Function invocations và attempts.
- Compute quantity.
- Gateway request count.
- Database/dependency operations.
- Network bytes và transfer class.
- Logs/traces ingestion.
- Shared resource allocation.

Sau đó map SKU và billing quantity của từng provider vào schema này. Không so sánh trực tiếp đơn giá GB-second giữa các nền tảng nếu runtime, CPU allocation, concurrency, rounding và included grants khác nhau.

## 10. Tối ưu chi phí dựa trên telemetry

Chỉ tối ưu khi biết cost driver. Một thay đổi có thể giảm compute nhưng làm tăng retry hoặc network egress.

### 10.1. Giảm duration có ích

- Tối ưu query và thêm index phù hợp.
- Giảm số round trip tới database và external API.
- Tái sử dụng HTTP client/connection pool khi runtime cho phép.
- Tránh khởi tạo SDK/framework nặng trong mỗi request.
- Giảm serialize/deserialize không cần thiết.
- Dùng batch hoặc cache khi semantics cho phép.
- Giảm payload response.

Đo trước và sau theo cùng route, volume, payload mix và success rate. Giảm duration không có ý nghĩa nếu tỷ lệ lỗi tăng hoặc request bị xử lý thiếu.

### 10.2. Điều chỉnh memory và CPU

Tăng memory có thể tăng CPU hoặc network throughput tùy provider. Function có thể chạy ngắn hơn và tổng GB-second thậm chí giảm, dù mức memory cao hơn. Hãy benchmark một số cấu hình và so sánh:
- Duration p50/p95.
- Memory utilization.
- GB-second hoặc billable compute.
- Error/timeout rate.
- Cold start.
- Cost per successful operation.

Không tối ưu memory dựa trên average duration duy nhất.

### 10.3. Giảm downstream fan-out và retry

- Tránh N+1 database calls.
- Gộp API call khi có bulk endpoint.
- Dùng timeout theo dependency.
- Retry có budget, backoff và jitter.
- Dùng circuit breaker cho dependency mất ổn định.
- Đặt concurrency limit để không tạo retry storm.
- Dùng queue/DLQ cho công việc có thể xử lý bất đồng bộ.
- Bảo đảm idempotency khi redelivery.

Nếu downstream API chậm, tăng function concurrency có thể làm chi phí và áp lực dependency tăng cùng lúc. Theo dõi concurrency, retry ratio và dependency latency để quyết định.

### 10.4. Kiểm soát logs và traces

- Giảm log lặp lại ở mỗi layer.
- Không log payload lớn nếu không có yêu cầu.
- Chọn retention theo môi trường và loại log.
- Dùng sampling cho trace thành công, giữ trace lỗi/slow request theo policy.
- Tránh export cùng trace qua nhiều agent/collector.
- Kiểm tra log level sau mỗi deployment.
- Đặt budget cho observability ingestion.

Không giảm telemetry tới mức mất khả năng điều tra incident hoặc chứng minh audit. Giữ security/audit logs theo chính sách bắt buộc và tối ưu các log chẩn đoán có volume lớn.

### 10.5. Cân nhắc fixed capacity

Provisioned concurrency/minimum instances có thể giảm cold start và cải thiện latency nhưng thêm chi phí capacity. Chỉ bật khi SLO hoặc traffic pattern chứng minh cần thiết. So sánh:
- Phần request thực sự được hưởng lợi.
- Mức giảm p95/p99 và cold start.
- Capacity idle.
- Cost per successful operation.
- Thời gian trong ngày có traffic thấp.

### 10.6. Tối ưu network theo destination

Phân loại traffic đến managed service, public API, database private và region khác. Private endpoint có thể giảm NAT hoặc public exposure nhưng có phí endpoint. Dùng signed URL/object storage cho file lớn nếu API không cần proxy bytes qua function. Đặt function gần dependency chính nếu phù hợp với latency, data residency và DR.

## 11. Cost attribution theo route và sản phẩm

Một API có thể có nhiều route với mức tiêu thụ rất khác nhau. Route health-check có thể gần như không gọi dependency; route tạo order có thể gọi database, payment và publish event. Nếu chia tổng chi phí theo số request đồng đều, kết quả sẽ sai lệch khi payload, duration và fan-out khác nhau.

### 11.1. Driver cho route-level allocation

Có thể xây dựng weight cho từng route từ:
- Function compute quantity theo route hoặc request duration × memory.
- Dependency operations và mức sử dụng database.
- Network bytes theo route/dependency.
- Log bytes và trace spans.
- Retry attempts.
- Gateway request count.

Một mô hình nội bộ:

\[
Weight_{\text{route}} =
w_c Compute_{\text{route}} +
w_d Dependency_{\text{route}} +
w_n Network_{\text{route}} +
w_o Observability_{\text{route}}
\]

\[
C_{\text{route}} =
C_{\text{service}} \times
\frac{Weight_{\text{route}}}{\sum Weight_{\text{all routes}}}
\]

Các hệ số \(w_c, w_d, w_n, w_o\) là trọng số nội bộ. Nếu billing export đã có chi phí trực tiếp theo resource hoặc SKU, dùng số thực đó trước; weight chủ yếu giúp phân bổ shared cost hoặc chi phí chưa thể gắn trực tiếp.

### 11.2. Tránh độ chính xác giả

Không phải mọi cloud bill đều cung cấp chi phí theo từng HTTP route. Một số SKU chỉ ghi ở cấp function, gateway, log group hoặc network resource. Vì vậy:
- Gắn chi phí trực tiếp nơi provider hỗ trợ.
- Phân bổ phần shared bằng driver được công bố.
- Ghi rõ số liệu nào là actual và số liệu nào là estimated.
- Giữ lại phần unallocated nếu chưa có dữ liệu tốt.
- Không ép mọi đồng chi phí vào route bằng một tỷ lệ thiếu căn cứ.

Cost attribution là mô hình quản trị. Nó phải giải thích được và đối chiếu được với tổng hóa đơn.

### 11.3. Theo dõi unit economics theo phiên bản

Gắn deployment version vào logs/traces và báo cáo cost window. Có thể so sánh trước/sau release:
- Cost per successful operation.
- Duration và memory.
- Dependency calls/operation.
- Retry ratio.
- Payload bytes.
- Success rate.

Không dùng version hoặc commit hash làm metric label nếu tạo cardinality quá lớn. Dùng deployment metadata, log query hoặc dashboard annotation để lọc phiên bản.

## 12. Điều tra biến động chi phí

Khi chi phí tăng, trước tiên xác định dòng bill nào tăng. Sau đó nối billing quantity với telemetry và thay đổi gần thời điểm phát sinh.

### 12.1. Quy trình điều tra

1. Xác định SKU, usage type và resource có mức tăng.
2. So sánh quantity và unit price để biết tăng do volume hay do giá/tier.
3. Kiểm tra request count, function invocation, duration và memory.
4. Kiểm tra retry ratio, downstream calls, timeout và queue redelivery.
5. Kiểm tra bytes, NAT processing, cross-zone/region transfer.
6. Kiểm tra log ingestion, trace sampling và retention.
7. Xem deployment, cấu hình concurrency, route hoặc VPC thay đổi.
8. Phân bổ phần shared theo driver và xác định owner.
9. Đề xuất tối ưu, sau đó đo lại SLO và cost per successful operation.

### 12.2. Ví dụ các dấu hiệu

| Dấu hiệu | Nguyên nhân có thể | Dữ liệu cần kiểm tra |
|---|---|---|
| Invocation tăng nhanh hơn client request | Retry, batch split hoặc event redelivery | Attempt count, trigger metrics |
| Duration tăng nhưng request count ổn định | Downstream chậm hoặc cold start | Trace spans, dependency latency |
| Network cost tăng nhưng bytes response ổn định | Retry, NAT path hoặc downstream payload | NAT metrics, flow logs, dependency bytes |
| Logs cost tăng đột biến | Debug log, duplicate logger hoặc payload logging | Ingestion bytes, log level, deployment |
| Cost per success tăng | Success rate giảm, retry tăng hoặc request mix thay đổi | Outcome, retries, route mix |
| Gateway cost tăng | Request count hoặc data processing tăng | Gateway metrics và access logs |
| Database cost tăng | N+1 query, query nặng hoặc retry | Query metrics, calls/request, connection count |

### 12.3. Budget và anomaly alert

Đặt budget hoặc alert theo:
- Tổng cost của service/environment.
- Cost per 1.000 accepted request.
- Cost per 1.000 successful operation.
- Function compute quantity và invocation.
- NAT/data transfer.
- Logs/traces ingestion.
- Retry ratio và dependency operations.

Alert theo xu hướng và ngưỡng phù hợp với workload. Với batch hoặc traffic mùa vụ, dùng forecast có tính lịch. Không báo incident chỉ vì hóa đơn tăng theo traffic dự kiến; kiểm tra cost per unit trước.

## 13. Checklist production

- [ ] Có định nghĩa rõ client request, invocation, attempt và successful business operation.
- [ ] Có metric request count, duration histogram và outcome theo route template.
- [ ] Có platform metrics về invocation, duration, memory, concurrency và throttling.
- [ ] Có dependency latency, calls, timeout và retry attempts.
- [ ] Có request/response bytes và network usage khi cần.
- [ ] Có structured logs với request ID và trace ID.
- [ ] Không ghi secret, credential, payload nhạy cảm hoặc dữ liệu cá nhân không cần thiết.
- [ ] Có distributed tracing và context propagation qua HTTP/message.
- [ ] Không tạo metric label cardinality cao.
- [ ] Không tạo span trùng với auto-instrumentation.
- [ ] Có dashboard p50/p95/p99, error rate, retries và queue age.
- [ ] SLO phân biệt accepted request với successful business operation.
- [ ] Cost model bao gồm function, gateway, dependency, network và observability.
- [ ] Shared cost có allocation driver và phần unallocated được công khai.
- [ ] Cost per accepted request và cost per successful operation có mẫu số rõ.
- [ ] Billing export được đối chiếu với telemetry cùng time window.
- [ ] Giá minh họa không bị nhầm với đơn giá provider hiện hành.
- [ ] Có budget/anomaly alert và owner xử lý.
- [ ] Có quy trình so sánh cost/SLO trước và sau deployment.
- [ ] Có policy sampling, retention và log level theo môi trường.

## 14. Tự kiểm tra

**Câu 1.** Metrics, logs và traces khác nhau như thế nào?

**Gợi ý trả lời:** Metrics cho biết xu hướng và mức độ như request rate, error rate, latency. Logs mô tả sự kiện cụ thể của một lần xử lý. Traces cho thấy request đi qua các thành phần nào và thời gian ở mỗi span.

**Câu 2.** Vì sao không nên dùng request ID làm metric label?

**Gợi ý trả lời:** Request ID gần như duy nhất cho mỗi request, tạo cardinality rất lớn và làm tăng chi phí lưu trữ/truy vấn metrics. Request ID phù hợp với logs hoặc traces có kiểm soát.

**Câu 3.** Vì sao cost per successful operation có thể tăng dù cost per accepted request gần như không đổi?

**Gợi ý trả lời:** Success rate giảm khiến số operation hoàn tất ít hơn trong khi chi phí đã phát sinh cho request thất bại vẫn còn. Retry và dependency work bổ sung cũng có thể làm cost tăng.

**Câu 4.** Tại sao application byte metric có thể khác billing quantity của network?

**Gợi ý trả lời:** Application đo payload ở lớp ứng dụng. Billing có thể tính header, protocol overhead, retransmission, chiều traffic khác hoặc quy tắc đo riêng của provider. Cần đối chiếu thay vì coi hai số giống nhau.

**Câu 5.** Phân bổ phí NAT dùng chung theo request count có luôn hợp lý không?

**Gợi ý trả lời:** Không. Các route có thể truyền lượng byte rất khác nhau. Phân bổ theo bytes/subnet hoặc flow telemetry thường phản ánh usage tốt hơn; phí baseline có thể cần driver capacity/ownership riêng.

**Bài tập tình huống:** Một Java API có 5 triệu request mỗi tháng. Sau một lần release, số client request gần như không đổi nhưng function invocation tăng 18%, p95 latency tăng từ 220 ms lên 800 ms, network cost tăng 35% và log ingestion tăng gấp đôi. Hãy đề xuất kế hoạch điều tra và cách cập nhật cost per successful operation.

**Gợi ý:** So sánh client request với invocation/attempt để tìm retry hoặc event redelivery. Dùng trace để tìm dependency span chậm và kiểm tra concurrency/throttling. Đối chiếu NAT/flow logs với dependency bytes để tìm đường truyền hoặc fan-out tăng. Kiểm tra log level, duplicate logger và payload logging. Lấy billing export để phân biệt quantity với đơn giá; sau đó tính lại cost trên số operation thành công. Chỉ triển khai tối ưu khi đo được ảnh hưởng đến SLO và có thể so sánh cùng request mix.

## Kết luận

Telemetry cho serverless API cần kết hợp platform metrics, application metrics, structured logs và distributed traces. Metrics cho biết xu hướng; logs và traces giải thích request cụ thể, dependency, retry và payload. Cost per request phải tính cả function, gateway, database, network, retries và observability; chi phí shared cần allocation driver minh bạch. Cost per successful operation kết nối hóa đơn với kết quả sản phẩm, giúp ưu tiên tối ưu dựa trên số liệu. Đối chiếu billing export với telemetry và theo dõi SLO trước/sau mỗi thay đổi để bảo đảm tiết kiệm chi phí không làm giảm chất lượng dịch vụ.
