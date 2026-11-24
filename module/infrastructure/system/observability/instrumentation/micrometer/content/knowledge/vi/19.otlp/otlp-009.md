# Phân biệt xuất metric bằng OTLP registry với cấu hình xuất trace

## OTLP là giao thức chung, nhưng metrics và traces là hai tín hiệu riêng

Micrometer cung cấp API đo lường cho ứng dụng Java thông qua Counter, Gauge, Timer, DistributionSummary và các meter khác. Khi cần gửi metrics đến OpenTelemetry Collector hoặc một hệ thống hỗ trợ OpenTelemetry Protocol (OTLP), ứng dụng có thể dùng **Micrometer OTLP registry**. Registry này chuyển các meter thành dữ liệu metrics theo mô hình OTLP và gửi đến endpoint nhận metrics.

Trace có vòng đời và cấu trúc khác. Một trace gồm các span mô tả đường đi của một request hoặc một công việc qua nhiều thành phần. Trong ứng dụng Spring Boot dùng Micrometer Tracing với OpenTelemetry, span được tạo qua Tracer hoặc Observation instrumentation và được gửi bằng một **OTLP trace exporter**.

Cả hai tín hiệu đều có thể đi qua cùng một OpenTelemetry Collector và cùng dùng giao thức OTLP, nhưng chúng không dùng chung một registry hay một cấu hình exporter duy nhất:

- **Metrics:** Micrometer tạo meter, **OtlpMeterRegistry** thu thập và xuất metric data.
- **Traces:** Micrometer Tracing/OpenTelemetry tạo span, OTLP span exporter gửi trace data.
- **Collector:** nhận từng loại tín hiệu và định tuyến qua pipeline metrics hoặc traces riêng.

Chỉ thêm dependency **micrometer-registry-otlp** không tự bật xuất trace. Ngược lại, chỉ cấu hình OTLP trace exporter cũng không làm Counter hoặc Timer của Micrometer được gửi đi. Cần cấu hình riêng cả hai nếu ứng dụng muốn xuất đồng thời metrics và traces.

## Hai pipeline có nhiệm vụ khác nhau

### Pipeline metrics

Metrics là các phép đo được tổng hợp theo tên meter và thuộc tính. Ví dụ:

- Counter đếm số request hoàn tất.
- Gauge quan sát số kết nối đang mở.
- Timer ghi nhận thời lượng request.
- DistributionSummary ghi nhận phân phối kích thước payload.

Micrometer quản lý các meter trong **MeterRegistry**. Với OTLP, registry chuyển số liệu sang cấu trúc metric data và gửi theo chu kỳ xuất. Một điểm dữ liệu metric thường có tên, mô tả, đơn vị, thuộc tính, timestamp và giá trị hoặc aggregation tương ứng.

Metrics thích hợp để trả lời các câu hỏi như:

- Tốc độ request mỗi giây là bao nhiêu?
- Tỷ lệ lỗi đang tăng hay giảm?
- p95 latency của dịch vụ trong vài phút gần đây là bao nhiêu?
- Có bao nhiêu kết nối đang được sử dụng?
- Dung lượng payload thường nằm trong khoảng nào?

### Pipeline traces

Trace mô tả một lần thực thi cụ thể. Một trace có thể chứa nhiều span; mỗi span có trace ID, span ID, parent span ID, thời điểm bắt đầu, thời lượng, thuộc tính, sự kiện và trạng thái.

Trace thích hợp để trả lời:

- Request cụ thể đã đi qua những service nào?
- Thời gian bị tiêu tốn ở bước gọi database hay gọi HTTP?
- Span nào phát sinh exception?
- Một request chậm có đường đi và quan hệ cha-con ra sao?

Trace exporter thường gom span đã hoàn tất thành batch rồi gửi đến collector hoặc backend. Cấu hình batch, queue, timeout và sampling thuộc pipeline trace. Đây là các khái niệm khác với step interval và aggregation temporality của metric registry.

### Bảng đối chiếu

| Nội dung | Metrics qua OTLP registry | Traces qua OTLP exporter |
|---|---|---|
| API instrumentation thường dùng | MeterRegistry, Counter, Gauge, Timer, DistributionSummary | ObservationRegistry, Tracer, Span và tracing instrumentation |
| Thành phần xuất | OtlpMeterRegistry | OpenTelemetry SDK span exporter hoặc cấu hình tracing do Spring Boot quản lý |
| Dữ liệu gửi | Metric, data point, attributes, aggregation | ResourceSpans, Span, trace/span ID, parent, events, status |
| Cách thu thập | Registry đọc meter và xuất theo step/chu kỳ | Span được gửi sau khi kết thúc, thường qua batch processor |
| Cấu hình thời gian | Step, temporality, histogram và timeout gửi metrics | Sampling, batch delay, queue, batch size và timeout span export |
| Endpoint OTLP/HTTP | /v1/metrics | /v1/traces |
| Tác động của sampling trace | Không bị sampling trace chi phối | Có thể bị sampling giữ lại hoặc loại bỏ |
| Câu hỏi chính | Hệ thống đang hoạt động ở mức nào? | Một lần thực thi cụ thể đã diễn ra như thế nào? |

## Cấu hình xuất metrics bằng Micrometer OTLP registry

### Dependency cho metrics

Trong dự án Spring Boot dùng Gradle, dependency thường có dạng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Spring Boot dependency management nên quản lý phiên bản Micrometer tương thích với phiên bản Boot đang dùng. Tránh tự ghép các phiên bản Micrometer khác thế hệ nếu không có chủ đích.

Nếu ứng dụng không dùng Spring Boot auto-configuration, có thể tự tạo và quản lý OtlpMeterRegistry bằng OtlpConfig cùng Clock. Khi tự tạo registry, ứng dụng phải quản lý lifecycle, shutdown và việc đóng tài nguyên của registry.

### Cấu hình endpoint metrics

Với Spring Boot có hỗ trợ OTLP metrics export, cấu hình có thể đặt trong application.yml:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        resource-attributes:
          service.name: checkout-service
          service.namespace: commerce
          deployment.environment.name: production
~~~

Các thuộc tính cụ thể và tên property có thể thay đổi theo phiên bản Spring Boot. Hãy đối chiếu reference của phiên bản dự án trước khi áp dụng. URL ở ví dụ dùng OTLP/HTTP và endpoint metrics của Collector.

step quyết định chu kỳ registry gom và xuất dữ liệu. Nó không phải chu kỳ batch của trace exporter và cũng không phải scrape interval của Prometheus. Nếu step là 30 giây, dữ liệu metric được công bố theo các khoảng của registry; backend có thể nhận dữ liệu theo chu kỳ đó.

Micrometer OTLP registry thường dùng OTLP/HTTP với protobuf. Endpoint HTTP metrics thường kết thúc bằng /v1/metrics trên cổng OTLP/HTTP, thường là 4318. Không trỏ HTTP registry vào cổng gRPC 4317 nếu Collector chỉ mở OTLP/gRPC tại cổng đó.

### Đăng ký meter như bình thường

Mã instrumentation vẫn dùng API Micrometer:

~~~java
@Component
public class CheckoutMetrics {

    private final Counter completed;
    private final Timer paymentDuration;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("checkout.orders.completed")
            .description("So don hang da hoan tat")
            .baseUnit("orders")
            .register(registry);

        this.paymentDuration = Timer.builder("checkout.payment.duration")
            .description("Thoi gian xu ly thanh toan")
            .register(registry);
    }

    public void orderCompleted() {
        completed.increment();
    }

    public void recordPayment(Runnable action) {
        paymentDuration.record(action);
    }
}
~~~

Thành phần nghiệp vụ chỉ phụ thuộc MeterRegistry. Registry do Spring Boot cấu hình quyết định cách dữ liệu được xuất. Khi dùng OTLP registry, các meter được chuyển thành metric data; khi dùng registry khác, cùng instrumentation có thể được ánh xạ theo quy ước của backend đó.

Không cần tạo một Counter riêng chỉ để gửi OTLP. Tránh ghi cùng một sự kiện vào nhiều meter song song nếu không có yêu cầu phân tích khác nhau.

## Cấu hình xuất traces qua OTLP

### Dependency cho tracing

Trong Spring Boot, tracing dựa trên Micrometer Tracing và bridge đến OpenTelemetry có thể dùng các dependency sau:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Bộ dependency này phục vụ pipeline trace. Nó không thay thế micrometer-registry-otlp khi ứng dụng cũng cần xuất metrics bằng OTLP.

Spring Boot có thể tự cấu hình Tracer, OpenTelemetry SDK và exporter khi classpath cùng property phù hợp. Chi tiết auto-configuration và tên property phụ thuộc phiên bản Boot. Với ứng dụng tự quản lý OpenTelemetry SDK, cần tạo span exporter, batch span processor và tracer provider theo lifecycle riêng.

### Cấu hình endpoint traces

Ví dụ cấu hình Spring Boot có hỗ trợ OTLP tracing:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
  tracing:
    sampling:
      probability: 0.1
~~~

endpoint chỉ nơi gửi span. sampling.probability điều khiển tỷ lệ trace được lấy mẫu trong cấu hình sampler tương ứng. Sampling ảnh hưởng lượng trace được xuất; nó không có nghĩa metrics cũng chỉ được gửi theo cùng tỷ lệ.

Không đặt endpoint trace thành /v1/metrics, và không đặt endpoint metrics thành /v1/traces. Hai đường dẫn nhận hai loại payload khác nhau. Nếu dùng OTLP/gRPC thay cho OTLP/HTTP, phải cấu hình exporter và Collector cùng transport; không chỉ thay cổng trong URL HTTP.

### Tạo span qua instrumentation

Khi tracing được cấu hình, span có thể được tạo thủ công hoặc thông qua Observation instrumentation. Ví dụ dùng Tracer theo API Micrometer Tracing:

~~~java
@Service
public class PaymentProcessor {

    private final Tracer tracer;

    public PaymentProcessor(Tracer tracer) {
        this.tracer = tracer;
    }

    public void process() {
        Span span = tracer.nextSpan().name("payment.process").start();
        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            callPaymentGateway();
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }

    private void callPaymentGateway() {
        // Goi cong thanh toan.
    }
}
~~~

Đoạn mã minh họa vòng đời span: tạo, đưa vào scope để context được truyền trong phạm vi xử lý, ghi nhận lỗi nếu có và kết thúc span. Exporter gửi span sau khi span kết thúc theo cơ chế batch.

Trong ứng dụng Spring Boot, ưu tiên instrumentation tự động hoặc Observation API khi phù hợp để context propagation và quan hệ parent-child được duy trì qua các lời gọi. Không tạo span thủ công cho mọi thao tác nhỏ nếu instrumentation tự động đã tạo span tương đương.

## Endpoint và transport của OTLP

### OTLP/HTTP

OTLP/HTTP thường dùng cổng 4318. Các đường dẫn signal phổ biến:

| Signal | Đường dẫn HTTP |
|---|---|
| Metrics | /v1/metrics |
| Traces | /v1/traces |
| Logs | /v1/logs |

Mỗi endpoint nhận payload theo schema signal tương ứng. Metrics registry gửi metric data đến /v1/metrics; trace exporter gửi span data đến /v1/traces.

### OTLP/gRPC

OTLP/gRPC thường dùng cổng 4317. Exporter gRPC gửi các request theo service/method của OTLP, không dùng đường dẫn HTTP /v1/metrics hoặc /v1/traces như transport HTTP.

Một số exporter và registry chỉ hỗ trợ một transport cụ thể. Micrometer OTLP registry cần được cấu hình theo transport mà implementation của nó hỗ trợ; không suy luận rằng mọi thành phần có chữ OTLP đều hỗ trợ cả HTTP và gRPC.

### Tránh nhầm cổng và đường dẫn

Các lỗi cấu hình thường gặp:

- Gửi HTTP protobuf đến cổng gRPC.
- Gửi trace payload đến endpoint metrics.
- Gửi metric payload đến endpoint traces.
- Cấu hình exporter dùng TLS nhưng Collector chỉ mở plaintext, hoặc ngược lại.
- Dùng endpoint nội bộ của Collector từ container khác nhưng lại trỏ localhost.
- Thiếu path /v1/metrics hoặc /v1/traces khi exporter yêu cầu endpoint đầy đủ.

Hãy xác nhận transport, host, port, TLS, path và authentication headers của cả phía gửi lẫn Collector.

## Cấu hình OpenTelemetry Collector nhận cả metrics và traces

Collector có thể mở cả OTLP/gRPC và OTLP/HTTP:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Ví dụ dùng debug exporter để minh họa dữ liệu Collector nhận được. Trong môi trường production, thay bằng exporter phù hợp với backend metrics và backend traces đang triển khai.

Collector có một receiver OTLP nhưng định nghĩa hai pipeline độc lập:

- Pipeline metrics xử lý metric data.
- Pipeline traces xử lý span data.

Có thể dùng chung receiver và một số processor, nhưng mỗi pipeline vẫn phải khai báo exporter đích tương ứng. Việc Collector nhận được metrics không chứng minh pipeline traces đã được cấu hình; tương tự, trace đi qua Collector không chứng minh metrics exporter đang gửi dữ liệu.

Nếu backend metrics và traces khác nhau, cấu hình exporter ở từng pipeline theo backend đích. Cũng cần kiểm tra Collector có bật đúng receiver protocol, port và network interface.

## Resource attributes và metric tags không giống nhau

### Resource attributes mô tả nguồn phát

Resource attributes định danh thực thể phát ra telemetry, ví dụ:

- service.name: tên dịch vụ.
- service.namespace: namespace của dịch vụ.
- service.instance.id: định danh instance.
- deployment.environment.name: môi trường triển khai.

Các thuộc tính này gắn với resource trong OTLP và có thể áp dụng cho nhiều metric hoặc span được phát từ cùng resource.

### Meter tags mô tả chiều đo

Tag của Micrometer trở thành thuộc tính gắn với meter hoặc data point. Ví dụ:

~~~java
Counter.builder("checkout.orders.completed")
    .tag("payment_method", "card")
    .tag("outcome", "success")
    .register(registry);
~~~

payment_method và outcome mô tả chiều phân loại của số đơn hàng. Chúng không thay thế service.name hay service.instance.id.

Không đưa trace_id, span_id, request ID hoặc user ID vào metric tag. Các giá trị này thường có cardinality rất cao. Nếu cần liên kết một metric với trace, hãy dùng cơ chế exemplar khi registry/backend hỗ trợ và được cấu hình, hoặc dùng correlation ID trong log/trace context.

### Cấu hình resource cho metrics không tự cấu hình resource cho traces

Metrics registry và OpenTelemetry SDK trace exporter có thể có cấu hình resource riêng. Đặt service.name trong resource attributes của metrics không đảm bảo span exporter cũng nhận cùng giá trị. Hãy cấu hình resource identity nhất quán ở cả hai pipeline hoặc dùng cơ chế auto-configuration chung của framework nếu phiên bản hỗ trợ.

Nếu metrics hiển thị service là checkout-service nhưng traces hiển thị service khác hoặc không có service.name, truy vấn tương quan và điều hướng trong backend sẽ khó sử dụng.

## Temporality của metrics và batch của traces

### Metrics: step và aggregation temporality

OTLP metrics có thể biểu diễn dữ liệu theo cumulative hoặc delta aggregation temporality. Cumulative mang giá trị tích lũy từ điểm bắt đầu của chuỗi; delta mang phần thay đổi trong một khoảng thu thập.

Micrometer OTLP registry có cấu hình liên quan đến aggregation temporality và chu kỳ step. Giá trị mặc định phụ thuộc phiên bản và cấu hình registry. Hãy kiểm tra OtlpConfig hoặc property tương ứng của phiên bản đang sử dụng và xác nhận Collector/backend hiểu temporality đó.

Không giả định mọi backend OTLP đều xử lý delta và cumulative giống nhau. Nếu pipeline chuyển đổi temporality, cần xác minh quy tắc reset, start timestamp và cách backend tạo rate hoặc tổng hợp.

### Traces: batch và sampling

Trace exporter không dùng step để tích lũy count/sum. Span được tạo trong lúc thao tác chạy, sau đó hoàn tất và được chuyển tới exporter. Batch span processor gom nhiều span trước khi gửi để giảm overhead.

Các cấu hình tracing thường liên quan đến:

- Sampling probability hoặc sampler policy.
- Batch schedule delay.
- Kích thước batch tối đa.
- Queue capacity.
- Export timeout và retry behavior.
- Resource attributes và propagation format.

Không dùng step của metrics registry để điều khiển thời điểm gửi span. Không dùng sampling probability của traces để giải thích vì sao Counter hoặc Timer bị thiếu dữ liệu.

### Metrics không bị sampling trace loại bỏ

Metrics thường là phép đo tổng hợp và được xuất theo chu kỳ registry. Sampling trace có thể chỉ giữ lại một phần request để giảm chi phí lưu trace, nhưng điều đó không có nghĩa chỉ những request được lấy trace mới được tính vào Counter hoặc Timer.

Nếu instrumentation dùng chung Observation để tạo cả metric và span, handler metrics và handler tracing vẫn có cấu hình xử lý riêng. Cần phân biệt sampling của tracing với cách meter ghi nhận và export dữ liệu.

## Kết hợp metrics và traces để điều tra sự cố

Metrics cho biết vấn đề đang xảy ra ở phạm vi dịch vụ hoặc nhóm request. Traces giúp đi sâu vào một lần thực thi cụ thể.

Một quy trình điều tra thường có dạng:

1. Dashboard metrics phát hiện p95 latency hoặc error rate tăng.
2. Chọn service, operation, region hoặc outcome có bất thường.
3. Dùng trace backend để tìm các trace tương ứng với khoảng thời gian và service đó.
4. Mở trace chậm để xác định span tiêu tốn thời gian hoặc phát sinh lỗi.
5. Đối chiếu với log có trace ID/span ID nếu cần chi tiết sự kiện.
6. Sau khi xử lý, theo dõi metrics để xác nhận xu hướng đã trở lại bình thường.

Không nên biến trace ID thành metric tag để tạo liên kết. Cách đó có thể tạo một time series cho mỗi trace. Dùng exemplar hoặc khả năng liên kết metrics-traces của backend khi có hỗ trợ; nếu không, dùng log và trace context.

Cũng cần lưu ý metrics và traces có thể đến backend ở thời điểm khác nhau. Metrics export theo step, traces export theo batch và sampling. Khi điều tra một cửa sổ thời gian ngắn, độ trễ export và retention của từng backend có thể khiến dữ liệu xuất hiện không đồng thời.

## Kiểm thử riêng hai cấu hình

### Kiểm thử metrics registry

Có thể kiểm tra MeterRegistry và endpoint metrics:

- Meter được đăng ký với đúng tên, unit và tag.
- Counter tăng đúng sau sự kiện.
- Timer ghi nhận count và total time.
- OTLP registry gửi request đến endpoint /v1/metrics.
- Resource attributes và metric attributes xuất đúng.
- Temporality, step và histogram được backend nhận như dự kiến.
- Lỗi kết nối metrics được ghi log hoặc quan sát qua health/diagnostic phù hợp.

Dùng registry hoặc HTTP sender giả lập trong test để kiểm tra payload nếu cần. Không chỉ xác nhận ứng dụng khởi động thành công; registry có thể chưa gửi được dữ liệu nếu endpoint hoặc transport sai.

### Kiểm thử trace exporter

Trace pipeline cần các kiểm thử khác:

- Instrumentation tạo span với tên và thuộc tính đúng.
- Parent-child relationship và context propagation được giữ qua các lời gọi.
- Span được kết thúc cả khi có exception.
- Sampler giữ hoặc loại span theo policy.
- Batch processor gửi span đến endpoint /v1/traces.
- Resource attributes và status của span được backend nhận.
- Queue, timeout và exporter failure được xử lý theo cấu hình.

Một test xác nhận Counter xuất hiện ở metrics endpoint không chứng minh trace exporter hoạt động. Một test thấy span trong Collector cũng không chứng minh OTLP metrics registry đang gửi dữ liệu.

### Kiểm tra Collector và backend

Ở tầng tích hợp, kiểm tra cả hai pipeline:

| Kiểm tra | Metrics | Traces |
|---|---|---|
| Receiver nhận đúng signal | Có metric data point | Có span |
| Resource identity | service.name, instance, environment | service.name, instance, environment |
| Thuộc tính | Meter tags/data point attributes | Span attributes |
| Định tuyến | Pipeline metrics | Pipeline traces |
| Exporter đích | Backend metrics | Backend traces |
| Lỗi gửi | Registry/metric exporter | Span exporter/batch processor |

Nên có một kiểm thử end-to-end gửi ít nhất một metric và một span qua Collector, sau đó xác nhận chúng đến đúng backend hoặc exporter thử nghiệm.

## Những sai lầm thường gặp

**Chỉ thêm micrometer-registry-otlp và kỳ vọng có trace.** Dependency này phục vụ metrics. Trace cần Micrometer Tracing/OpenTelemetry và trace exporter tương ứng.

**Chỉ cấu hình trace endpoint và kỳ vọng Counter được gửi.** Trace exporter không thay thế MeterRegistry. Cần cấu hình OTLP metrics registry riêng.

**Dùng chung endpoint /v1/metrics và /v1/traces.** Hai signal có payload và đường dẫn riêng. Cấu hình sai path sẽ khiến Collector từ chối request hoặc không nhận được dữ liệu mong muốn.

**Nhầm OTLP/HTTP với OTLP/gRPC.** Cổng, transport và cách cấu hình endpoint khác nhau. Phải thống nhất giữa exporter và Collector.

**Dùng step metrics để cấu hình batch span.** Step thuộc metric registry; batch delay và queue thuộc trace processor.

**Nghĩ trace sampling làm giảm Counter.** Sampling điều khiển span được giữ lại. Metrics được ghi nhận theo instrumentation và registry riêng.

**Cho rằng resource attributes của metrics tự áp dụng cho traces.** Hai pipeline có thể có resource configuration riêng. Kiểm tra service.name ở cả hai signal.

**Đưa trace ID vào metric tag.** Cardinality tăng rất lớn. Dùng exemplar hoặc log/trace correlation.

**Cho rằng Collector có một pipeline chung cho mọi signal.** Receiver có thể dùng chung, nhưng pipeline metrics và traces cần processor/exporter được cấu hình theo từng loại dữ liệu.

**Chỉ kiểm tra một signal.** Metrics và traces có dependency, endpoint, lifecycle và lỗi export riêng. Kiểm thử độc lập và end-to-end cả hai.

## Checklist triển khai OTLP metrics và traces

Trước khi triển khai, hãy xác minh:

1. Ứng dụng có dependency micrometer-registry-otlp nếu cần xuất metrics không?
2. Ứng dụng có bridge Micrometer Tracing/OpenTelemetry và OTLP trace exporter nếu cần xuất traces không?
3. Metrics endpoint có đúng /v1/metrics và trace endpoint có đúng /v1/traces không?
4. Exporter và Collector có cùng transport HTTP hoặc gRPC không?
5. Collector đã mở receiver và pipeline riêng cho metrics và traces chưa?
6. Resource attributes, đặc biệt service.name, có nhất quán ở cả hai signal không?
7. Metric tags có cardinality thấp và không chứa trace ID không?
8. Step và temporality của metrics có phù hợp với backend không?
9. Sampling, batch, queue và timeout của traces có phù hợp với tải không?
10. Có phân biệt metric export interval với trace batch schedule không?
11. Kiểm thử có xác nhận metrics và traces riêng biệt không?
12. Kiểm thử end-to-end có xác nhận cả hai signal đi qua Collector đến đúng backend không?

## Kết luận

OTLP là giao thức vận chuyển chung cho nhiều loại telemetry, nhưng metrics và traces vẫn là hai pipeline riêng. Micrometer OTLP registry xuất meter data từ MeterRegistry đến endpoint metrics; trace exporter gửi span do Micrometer Tracing/OpenTelemetry tạo đến endpoint traces.

Hãy cấu hình riêng dependency, endpoint, transport và lifecycle cho từng signal. Metrics cần quan tâm đến step, aggregation temporality, meter tags và histogram; traces cần quan tâm đến sampling, span context, batch processor và queue. Collector có thể nhận cả hai nhưng phải định tuyến qua pipeline metrics và traces phù hợp. Kiểm thử độc lập rồi kiểm thử end-to-end cả hai tín hiệu sẽ giúp xác nhận hệ thống quan sát hoạt động đầy đủ.
