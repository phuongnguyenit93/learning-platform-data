# Ảnh hưởng của logging, metric và tracing đến số đo hiệu năng

## 1. Vì sao observability làm thay đổi hiệu năng?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT rồi biên dịch thành GraalVM Native Image để đánh giá thời gian khởi động, bộ nhớ và khả năng vận hành. Khi đo các chỉ số này, cần tính cả chi phí của hệ thống quan sát: **logging, metrics và distributed tracing**.

Mỗi lần ghi log có thể định dạng chuỗi, tạo event, ghi stack trace và chuyển dữ liệu tới stdout hoặc file. Mỗi lần cập nhật metric có thể tra cứu meter, cập nhật bộ đếm hoặc histogram. Mỗi span tracing có thể tạo object, lưu context, thêm attributes, truyền trace context và gửi dữ liệu tới collector.

Những chi phí riêng lẻ có thể nhỏ, nhưng chúng được nhân lên theo số request, số log event, số meter series và số span. Trong một dịch vụ có tải cao, observability có thể làm thay đổi:

- CPU và số phép cấp phát bộ nhớ trên mỗi request;
- throughput và latency, đặc biệt ở p95/p99;
- RSS, heap và kích thước hàng đợi của exporter;
- thời gian startup và thời gian readiness;
- network traffic tới log collector, metrics backend và trace collector;
- độ chính xác của benchmark nếu các lần đo dùng cấu hình quan sát khác nhau.

Mục tiêu không phải tắt observability để có số đo đẹp. Mục tiêu là **đo với cấu hình quan sát giống môi trường vận hành, hiểu phần overhead do từng thành phần tạo ra và giữ overhead trong ngân sách chấp nhận được**.

## 2. Ba tín hiệu và các nguồn chi phí

| Tín hiệu | Dữ liệu được ghi nhận | Chi phí thường gặp |
| --- | --- | --- |
| Logging | Sự kiện, thông điệp, context, stack trace | Tạo/format message, serialize, I/O, queue, lưu trữ |
| Metrics | Counter, gauge, timer, histogram | Cập nhật meter, tag lookup, cardinality, bucket và scrape/export |
| Tracing | Span, parent-child relation, attributes, events | Tạo span, context propagation, sampling, queue và export |

~~~mermaid
flowchart LR
    A["Request / background job"] --> B["Application code"]
    B --> L["Logging"]
    B --> M["Metrics"]
    B --> T["Tracing"]
    L --> LC["Log collector"]
    M --> MC["Metrics backend"]
    T --> TC["Trace collector"]
    LC --> S["Storage / analysis"]
    MC --> S
    TC --> S
~~~

Ba tín hiệu có thể dùng chung correlation hoặc trace ID nhưng không có cùng đặc tính. Metrics thường được tổng hợp theo chuỗi thời gian; logs lưu sự kiện chi tiết; traces mô tả đường đi của một operation qua nhiều thành phần. Giảm sampling của tracing không tự giảm số metrics hoặc logs.

## 3. Logging: chi phí tạo event và ghi dữ liệu

### 3.1. Formatting và đánh giá biểu thức

Dùng parameterized logging để tránh format message khi log level không bật:

~~~java
private static final Logger log =
    LoggerFactory.getLogger(InvoiceService.class);

void createInvoice(String invoiceId) {
    log.debug("Creating invoice {}", invoiceId);
}
~~~

Với lời gọi trên, logger có thể trì hoãn việc format message. Tuy nhiên, biểu thức truyền vào method vẫn được Java đánh giá trước khi gọi:

~~~java
log.debug("Invoice details: {}", buildExpensiveSummary(invoice));
~~~

buildExpensiveSummary(invoice) vẫn chạy ngay cả khi DEBUG bị tắt. Nếu việc tạo argument tốn kém, hãy kiểm tra log level trước:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Invoice details: {}", buildExpensiveSummary(invoice));
}
~~~

Không serialize cả object graph hoặc tính toán checksum chỉ để tạo log trong hot path. Log những trường đủ để chẩn đoán, chẳng hạn operation ID, loại thao tác, trạng thái và thời gian xử lý.

### 3.2. Số lượng log event

Một log event có thể tạo chi phí ở nhiều nơi:

1. Ứng dụng tạo message và metadata.
2. Logging framework tạo event và áp dụng filter.
3. Encoder chuyển event sang text/JSON.
4. Appender ghi stdout, file hoặc socket.
5. Collector đọc, parse, enrich và chuyển tiếp.
6. Backend index và lưu trữ.

Ghi một dòng log cho từng item trong vòng lặp lớn có thể biến logging thành nút thắt. Ưu tiên log theo operation hoặc theo batch, kèm số lượng thành công/thất bại và thời gian tổng.

### 3.3. Stack trace và exception

Stack trace hữu ích khi lỗi cần điều tra, nhưng tạo chuỗi lớn và tốn CPU/I/O. Tránh ghi cùng một exception ở mọi layer:

~~~java
try {
    archive.store(document);
}
catch (ArchiveUnavailableException ex) {
    log.warn("Archive operation failed, documentId={}", document.id());
    throw ex;
}
~~~

Ở layer chịu trách nhiệm ghi log cuối cùng, có thể ghi exception cùng stack trace:

~~~java
log.error("Could not persist invoice, operationId={}", operationId, ex);
~~~

Chọn một nơi ghi stack trace cho một lỗi đã được xử lý và truyền qua nhiều layer. Không log rồi nuốt exception nếu nghiệp vụ cần caller biết thao tác thất bại.

### 3.4. Log level và sampling

| Level | Cách dùng | Lưu ý hiệu năng |
| --- | --- | --- |
| ERROR | Lỗi khiến operation thất bại hoặc cần can thiệp | Tránh ghi trùng cùng exception ở nhiều layer |
| WARN | Tình huống bất thường nhưng có thể tiếp tục | Rate-limit lỗi lặp lại nếu cần |
| INFO | Sự kiện nghiệp vụ/vòng đời có giá trị vận hành | Không ghi mọi request ở tải lớn nếu access log đã đảm nhiệm |
| DEBUG | Chi tiết phục vụ điều tra | Tắt hoặc giới hạn ở production; tránh tính toán argument đắt |
| TRACE | Thông tin rất chi tiết | Chỉ bật có mục tiêu và trong thời gian ngắn |

Có thể sample hoặc rate-limit log lặp lại như “dependency unavailable” để tránh log storm. Nhưng không sample tùy tiện audit log, security event hoặc sự kiện cần bảo đảm lưu vết theo yêu cầu nghiệp vụ. Nếu bỏ bớt event, cần có counter cho biết đã suppressed bao nhiêu lần.

### 3.5. Synchronous và asynchronous logging

Appender đồng bộ có thể chặn thread xử lý request khi stdout, file hoặc socket chậm. Async appender chuyển event sang queue và thread ghi riêng, giúp tách I/O khỏi request path.

Async logging cũng có chi phí và đánh đổi:

- cấp phát event và enqueue/dequeue;
- bộ nhớ cho queue;
- contention khi nhiều thread cùng ghi;
- event có thể bị drop khi queue đầy theo discard policy;
- shutdown cần flush queue trong thời gian giới hạn;
- nếu process bị kill đột ngột, event chưa flush có thể mất.

Không mặc định async luôn nhanh hơn. Đo cả trường hợp collector chậm và queue gần đầy. Với log audit quan trọng, chọn chính sách không làm mất dữ liệu theo yêu cầu, hoặc dùng kênh lưu trữ bền vững phù hợp; không phụ thuộc một async queue trong bộ nhớ như kho audit.

### 3.6. Structured logging và MDC

Structured JSON giúp collector parse trường ổn định nhưng encoder phải serialize event. Chỉ đưa các trường cần thiết vào log. Tránh log payload lớn, access token, password, secret hoặc dữ liệu cá nhân.

MDC/correlation ID giúp liên kết log với request và trace. Khi dùng executor hoặc asynchronous processing, cần bảo đảm context được truyền và xóa đúng cách; context rò rỉ giữa các request vừa sai dữ liệu vừa tạo chi phí không cần thiết.

## 4. Metrics: chi phí meter, tag và cardinality

### 4.1. Counter, gauge, timer và histogram

Micrometer cung cấp các loại meter phổ biến:

- Counter đếm số sự kiện;
- Gauge quan sát giá trị tại thời điểm đọc;
- Timer đo thời gian và số lần thực hiện;
- Distribution summary đo phân bố của giá trị;
- Histogram phân nhóm số đo vào các bucket.

Việc cập nhật một counter thường nhẹ, nhưng tổng chi phí tăng theo số meter, số tag combination, histogram bucket và tần suất scrape/export.

### 4.2. Cardinality là nguồn chi phí lớn

Mỗi tổ hợp metric name và tag values có thể tạo một time series riêng. Nếu thêm tag có hàng triệu giá trị như userId, requestId, email hoặc URL thô, số series có thể tăng rất nhanh.

Ví dụ không nên dùng:

~~~java
Counter.builder("billing.request")
    .tag("customerId", customerId)
    .tag("requestId", requestId)
    .register(registry)
    .increment();
~~~

Các tag này tạo một meter series cho từng tổ hợp giá trị. Dùng tag có miền giá trị nhỏ và ổn định:

~~~java
Counter.builder("billing.request")
    .tag("operation", "create-invoice")
    .tag("outcome", "success")
    .register(registry)
    .increment();
~~~

Nếu cần tra cứu theo request/customer cụ thể, dùng trace/log attributes có kiểm soát và tuân thủ chính sách dữ liệu; không biến chúng thành metric labels.

### 4.3. Timer có thể tạo nhiều series

Timer có thể xuất count, total time, max và histogram buckets tùy registry/configuration. Khi bật percentile histogram, mỗi tag combination có thể tạo thêm nhiều series. Vì vậy, cardinality của tag nhân với số bucket sẽ ảnh hưởng mạnh tới storage và scrape payload.

Chỉ bật histogram/percentile cho metric thật sự cần phân tích phân bố latency. Xác định bucket phù hợp với SLO thay vì bật histogram cho mọi meter.

### 4.4. Đặt giới hạn cardinality

Có thể dùng MeterFilter để giới hạn tag values của một meter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricLimits() {
        return registry -> registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                "billing.request",
                "operation",
                20,
                MeterFilter.deny()
            )
        );
    }
}
~~~

Ví dụ dùng API Micrometer; xác nhận dependency và version thực tế của dự án. Đây là hàng rào bổ sung. Thiết kế tag cardinality thấp từ đầu vẫn là biện pháp chính.

Có thể thêm common tags ổn định:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CommonMetricsTagsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config()
            .commonTags("application", "billing-service");
    }
}
~~~

Không đưa environment-specific secret, hostname ngẫu nhiên hoặc request ID vào common tags. Common tag được gắn lên nhiều meter nên ảnh hưởng phạm vi rộng.

### 4.5. Ví dụ đo thời gian bằng Timer

Nên tạo meter ổn định và tái sử dụng thay vì tạo tên/tag động cho từng request:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;
import java.util.function.Supplier;

@Component
class InvoiceMetrics {

    private final MeterRegistry registry;
    private final Timer successTimer;
    private final Timer failureTimer;

    InvoiceMetrics(MeterRegistry registry) {
        this.registry = registry;
        successTimer = Timer.builder("billing.invoice.create")
            .description("Time to create an invoice")
            .tag("outcome", "success")
            .register(registry);

        failureTimer = Timer.builder("billing.invoice.create")
            .description("Time to create an invoice")
            .tag("outcome", "failure")
            .register(registry);
    }

    <T> T record(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(registry);
        try {
            T result = operation.get();
            sample.stop(successTimer);
            return result;
        }
        catch (RuntimeException | Error ex) {
            sample.stop(failureTimer);
            throw ex;
        }
    }
}
~~~

Timer.Sample cho phép chọn timer sau khi biết kết quả. Trong ứng dụng thực tế, cần xác định có tính thời gian chờ dependency hay không và tránh đo trùng cùng một operation ở nhiều layer. Đối với metric được dùng thường xuyên, giữ meter reference ổn định như ví dụ.

## 5. Scrape và export metrics

### 5.1. Pull model

Với Prometheus, ứng dụng thường cung cấp endpoint scrape. Ví dụ Spring Boot Actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

Cần dependency Prometheus registry tương ứng với Spring Boot/Micrometer version:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Scrape quá thường xuyên hoặc trả payload quá lớn có thể tăng CPU và network. Đặt scrape interval theo nhu cầu quan sát và capacity backend; không dùng interval cực ngắn để bù cho metric có ý nghĩa quá chậm.

### 5.2. Push model và exporter queue

Với OTLP hoặc registry push, ứng dụng cần serialize và gửi metric qua network. Export theo batch có thể giảm số request nhưng dùng queue và bộ nhớ. Khi backend chậm hoặc mất kết nối, queue có thể đầy và metric bị drop.

Theo dõi thời gian export, queue size, số lần drop, số meter/time series, payload size, lỗi kết nối và retry của exporter.

Không để exporter đồng bộ chặn request path. Dùng cơ chế batching/asynchronous export được thư viện hỗ trợ và đặt timeout/shutdown flush có giới hạn.

## 6. Tracing: chi phí span và context propagation

### 6.1. Một request tạo nhiều span

Một HTTP request có thể tạo span ở server, controller, service, HTTP client, database và message broker. Nếu tạo span thủ công ở mọi method, trace có thể phình lớn mà không thêm thông tin hữu ích.

Chỉ instrument các ranh giới có ý nghĩa:

- request vào/ra;
- gọi dependency;
- transaction hoặc operation nghiệp vụ quan trọng;
- publish/consume message;
- tác vụ nền có correlation với request.

Tránh tạo span cho getter, vòng lặp nhỏ hoặc method nội bộ quá thường xuyên. Nếu framework đã tự instrument HTTP client hoặc database, không tạo span thủ công trùng lặp cho cùng một lời gọi.

### 6.2. Sampling

Sampling quyết định span nào được ghi và export. Head sampling thường quyết định sớm khi trace bắt đầu; parent-based sampling kế thừa quyết định từ parent để giữ trace nhất quán.

Ví dụ Spring Boot với Micrometer Tracing:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Giá trị 0.1 là xác suất lấy mẫu 10% cho trace root theo cấu hình này; child spans thường theo quyết định của parent. Sampling giảm span được ghi/export, nhưng không loại bỏ mọi chi phí instrumentation và context propagation.

Với OpenTelemetry SDK, có thể cấu hình parent-based trace ID ratio sampler qua environment:

~~~bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
~~~

Chỉ cấu hình theo một stack tracing thống nhất. Nếu Spring Boot đang quản lý Micrometer Tracing, kiểm tra bridge/exporter đang dùng trước khi thêm một OpenTelemetry SDK độc lập có thể tạo hai pipeline trùng lặp.

Tail sampling tại collector có thể giữ lại trace lỗi hoặc trace chậm sau khi xem toàn bộ trace, nhưng collector phải buffer trace và tiêu tốn thêm bộ nhớ. Nó không có nghĩa ứng dụng không phải gửi span đến collector.

### 6.3. Batch span processor và export

Export span đồng bộ ngay khi kết thúc mỗi span có thể làm request thread chờ network. Batch processor gom span và gửi ở background:

- giảm số lần gọi exporter;
- tách phần lớn I/O khỏi request thread;
- cần queue và worker thread;
- có thể drop span khi queue đầy;
- cần flush khi shutdown trong giới hạn thời gian.

Theo dõi queue saturation, export errors, dropped spans và shutdown flush. Không tăng queue vô hạn để che một collector không đủ capacity.

### 6.4. Attributes và baggage

Attributes giúp phân tích trace nhưng cũng có chi phí serialize, truyền qua network và lưu ở backend. Chỉ thêm trường hữu ích như operation, dependency, outcome hoặc version.

Không thêm token, password, nội dung request, dữ liệu cá nhân hoặc payload lớn vào span. Baggage được truyền xuyên service có thể làm tăng kích thước header và được sao chép qua nhiều hop; chỉ dùng khi có nhu cầu cụ thể và kiểm soát danh sách key.

## 7. Kết hợp logs, metrics và traces

Ba tín hiệu có thể liên kết bằng trace ID và span ID:

- log có trace ID giúp mở đúng trace;
- trace có attributes mô tả dependency và operation;
- metrics cho thấy xu hướng tổng thể, latency và error rate.

Không cần đưa trace ID vào metric tag. Trace ID có cardinality gần như mỗi request một giá trị và sẽ làm time series tăng không kiểm soát.

Ví dụ log có correlation:

~~~java
log.info(
    "Invoice created, invoiceId={}, outcome={}",
    invoiceId,
    "success"
);
~~~

Khi tracing bridge tích hợp MDC, trace/span IDs có thể được thêm tự động vào log pattern. Xác minh cấu hình logging thực tế; không tự tạo ID mới ở mỗi layer nếu đã có trace context.

Một lỗi có thể tạo một metric counter tăng, một span có status ERROR và exception event, cùng một log error ở layer chịu trách nhiệm. Tránh ghi cùng stack trace ở controller, service, adapter và global exception handler.

## 8. Cấu hình observability cho benchmark

Để đo overhead, tạo các cấu hình có thể lặp lại:

| Cấu hình | Logging | Metrics | Tracing | Mục đích |
| --- | --- | --- | --- | --- |
| Baseline | Tắt log không cần thiết | Tắt/không instrument | Tắt | Ước lượng chi phí ứng dụng tối thiểu |
| Logs | Cấu hình production | Tắt | Tắt | Đo chi phí log và appender |
| Metrics | Tối thiểu | Bật | Tắt | Đo meter update và scrape/export |
| Tracing | Tối thiểu | Tắt hoặc giữ baseline cố định | Bật sampling đã chọn | Đo span/context/export |
| Production-like | Cấu hình thực tế | Cấu hình thực tế | Sampling thực tế | Đo overhead tổng hợp gần production |

Khi so sánh từng tín hiệu, giữ các tín hiệu còn lại cố định. Nếu vừa bật JSON logging, histogram, tracing 100% và đổi exporter cùng lúc, không thể xác định phần overhead đến từ đâu.

Baseline chỉ dùng để phân rã chi phí. Quyết định release phải dựa trên production-like configuration, vì hệ thống thực tế vẫn cần quan sát để vận hành.

## 9. Phương pháp đo hiệu năng

### 9.1. Đo startup riêng với steady state

Ghi ít nhất hai mốc:

- **Startup-to-ready:** từ lúc process bắt đầu đến khi readiness endpoint báo sẵn sàng.
- **Time-to-first-useful-request:** thời gian tới khi request nghiệp vụ đầu tiên hoàn thành.

Observability có thể làm startup tăng do khởi tạo logger, registry, exporter, DNS/TLS hoặc gửi resource attributes. Không để exporter phải kết nối thành công tới backend mới cho phép ứng dụng phục vụ request nếu thiết kế không yêu cầu điều đó.

Đo cả thời gian shutdown/flush nếu log và trace cần được gửi hết khi process dừng. Flush phải có timeout để shutdown không treo vô hạn.

### 9.2. Đo steady state

Với cùng workload, ghi nhận:

- requests/second hoặc operations/second;
- latency p50, p95, p99;
- error rate và timeout;
- CPU utilization;
- RSS và heap;
- allocation rate/GC nếu runtime cung cấp;
- network bytes tới collector;
- số log event, meter series và spans được export;
- số event/span bị drop.

Không chỉ nhìn average latency. Logging/export queue bị nghẽn hoặc histogram/cardinality tăng thường thể hiện rõ hơn ở tail latency và memory.

### 9.3. Kiểm soát phép đo

1. Dùng cùng binary/dependency version và cấu hình ứng dụng.
2. Dùng cùng dataset, request mix, concurrency và thời lượng tải.
3. Khởi động collector/backend tương đương cho các lần chạy có observability.
4. Đo nhiều lần và so sánh median/phân bố, không chọn lần chạy tốt nhất.
5. Tách thời gian build native khỏi startup runtime.
6. Với JVM, kiểm soát warm-up/JIT và ghi rõ heap settings.
7. Với native executable, ghi OS/CPU, libc, container limit và RSS.
8. Giữ scrape interval, sampling ratio và log level cố định.

RSS của JVM và native executable không phản ánh cùng một cấu trúc bộ nhớ. Báo cáo rõ RSS, heap và giới hạn container thay vì so một con số đơn lẻ mà không nêu ngữ cảnh.

## 10. Ví dụ tính overhead tương đối

Giả sử cùng workload đo được:

| Cấu hình | Throughput | p95 latency | RSS |
| --- | ---: | ---: | ---: |
| Baseline | 8.000 req/s | 24 ms | 180 MB |
| Logs | 7.700 req/s | 27 ms | 188 MB |
| Metrics | 7.850 req/s | 25 ms | 184 MB |
| Tracing 10% | 7.760 req/s | 26 ms | 186 MB |
| Production-like | 7.420 req/s | 31 ms | 198 MB |

Đây là số liệu giả định để minh họa cách trình bày, không phải kết quả benchmark của Spring Boot hay GraalVM. Trong ví dụ, production-like throughput thấp hơn baseline khoảng 7,25%; p95 tăng 7 ms; RSS tăng 18 MB.

Không nên cộng đơn giản overhead của logs, metrics và tracing để dự đoán tổng overhead. Chúng có thể chia sẻ CPU, queue, memory allocator và I/O; khi chạy cùng lúc, tác động có thể tương tác hoặc khuếch đại.

## 11. Quan sát riêng trên Native Image

### 11.1. Instrumentation phải tương thích native

Native Image dùng closed-world analysis. Thư viện logging, metrics, tracing hoặc exporter có thể cần reflection/resource/proxy metadata. Ưu tiên version thư viện đã công bố native support/reachability metadata và xác minh bằng native build cùng runtime test.

Kiểm tra:

- logging provider và cấu hình được tìm thấy trong executable;
- exporter có thể khởi tạo và kết nối khi runtime;
- resource như logging config, certificate và service descriptor có mặt;
- proxy/reflection cần thiết có hints phù hợp;
- native library phụ thuộc vào exporter/transport có đúng OS/CPU/ABI.

### 11.2. Không chụp cấu hình môi trường vào image heap

Endpoint collector, credential, log destination, sampling ratio và truststore thường là cấu hình theo môi trường. Đọc chúng từ runtime property/environment hoặc secret store. Không khởi tạo client, mở socket hoặc đọc secret trong static initializer chạy ở build time.

Nếu thay đổi cấu hình runtime mà native executable vẫn dùng giá trị máy build, kiểm tra class initialization và cách cấu hình được bind. Không áp dụng --initialize-at-run-time cho toàn bộ package logging/tracing theo phỏng đoán; tìm class initializer cụ thể và sửa phạm vi cần thiết.

### 11.3. Java agent và native executable

Java agent thường gắn vào JVM qua -javaagent lúc khởi chạy. Native executable không chạy như một JVM process thông thường, vì vậy không thể giả định một Java agent dùng cho JVM sẽ tự hoạt động với binary native.

Với native image, ưu tiên instrumentation qua thư viện/API được hỗ trợ, Spring/Micrometer integration, hoặc cơ chế build-time/native instrumentation mà vendor công bố. Kiểm tra tài liệu đúng version cho từng agent/exporter trước khi đưa vào pipeline.

### 11.4. Shutdown và flush

Khi native process nhận SIGTERM, ứng dụng cần đóng exporter và flush dữ liệu còn trong batch queue theo lifecycle được hỗ trợ. Đặt timeout hữu hạn và kiểm thử cả shutdown bình thường lẫn termination trong container.

Không đợi collector vô hạn. Nếu collector không khả dụng, ứng dụng cần dừng đúng thời hạn deployment cho phép và ghi nhận số event/span bị mất nếu có thể.

## 12. Kiểm thử overhead và lỗi của observability pipeline

Không chỉ đo trường hợp collector khỏe. Hãy kiểm tra:

- collector chậm hoặc unavailable;
- log stdout/file bị nghẽn;
- async log queue đầy;
- metrics scrape payload lớn;
- span exporter queue đầy;
- DNS/TLS lỗi khi exporter kết nối;
- shutdown khi còn event chưa flush;
- sampling ratio thay đổi;
- high-cardinality tag bị từ chối hoặc giới hạn.

Ứng dụng không nên mất khả năng xử lý request chỉ vì backend observability tạm thời unavailable. Cần queue giới hạn, timeout, retry có giới hạn và drop policy rõ ràng cho telemetry. Chính sách với audit/business event phải được thiết kế riêng.

### 12.1. Kiểm tra log volume

Tạo tải có kiểm soát và so sánh số event theo level, byte log trên mỗi request, số stack trace, số event suppressed, CPU và latency khi appender đồng bộ/asynchronous, queue depth và dropped event.

### 12.2. Kiểm tra metrics cardinality

Đếm series theo metric name và tag combination. Gửi request với nhiều user/request ID khác nhau rồi xác nhận số series không tăng theo số request. Theo dõi scrape duration, payload size và backend ingestion.

### 12.3. Kiểm tra tracing sampling

Gửi workload có parent/child calls, lỗi và request chậm. Xác nhận child spans giữ trace context của parent, sampling ratio được áp dụng theo policy, error status/attributes có mặt ở trace được giữ lại, exporter queue không tăng không giới hạn và trace ID không xuất hiện như metric tag.

## 13. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| CPU tăng mạnh khi bật DEBUG | Message/argument đắt, log quá nhiều hoặc serialize object lớn | Giảm log hot path, guard argument và giới hạn level |
| p99 tăng khi stdout chậm | Appender đồng bộ chặn request thread | Đo async appender, queue và collector; đặt overflow policy rõ |
| RSS tăng theo thời gian | Async queue/exporter queue tích tụ hoặc cardinality tăng | Theo dõi queue, drop count, meter series và exporter |
| Prometheus scrape chậm | Quá nhiều series/bucket hoặc endpoint scrape quá thường xuyên | Giảm cardinality, chọn histogram cần thiết và điều chỉnh scrape interval |
| Metrics backend tăng chi phí lưu trữ | Tag có giá trị gần như duy nhất cho mỗi request | Bỏ request/user ID khỏi metric tags |
| Trace export làm request chậm | Export đồng bộ hoặc collector/network chậm | Dùng batch processor, timeout và queue giới hạn |
| Trace thiếu child spans | Context propagation bị đứt hoặc sampling không nhất quán | Kiểm tra executor/reactive context và parent-based sampler |
| JVM hoạt động nhưng native thiếu logging provider | Service descriptor/resource/reachability metadata thiếu | Kiểm tra dependency metadata và native output |
| Native không kết nối được collector | DNS, TLS, CA hoặc endpoint runtime sai | Kiểm tra truststore, hostname và runtime config |
| Native dùng sampling ratio của máy build | Cấu hình bị chụp ở build time hoặc bind sai | Đưa cấu hình về runtime và kiểm tra class initialization |
| Dữ liệu mất khi shutdown | Queue chưa flush hoặc timeout quá ngắn | Kiểm tra lifecycle, flush timeout và termination grace period |

## 14. Quy trình thực hành đo overhead

Giả sử dịch vụ billing có HTTP endpoint tạo hóa đơn và gọi archive service.

**Bước 1 — xác định workload**

- cố định request mix, concurrency và dataset;
- ghi rõ tỷ lệ success/error;
- chọn thời lượng đủ để quan sát steady state;
- chạy trên cùng OS/CPU và resource limit.

**Bước 2 — tạo baseline**

- tắt log debug/trace không cần thiết;
- không bật tracing hoặc exporter ngoài;
- giữ logic nghiệp vụ và dependency như nhau;
- đo startup, throughput, p95/p99, CPU và RSS.

**Bước 3 — bật logging production-like**

- dùng log level và format dự kiến triển khai;
- giữ collector/appender cùng điều kiện;
- đo log bytes/request, queue, CPU và latency.

**Bước 4 — bật metrics**

- dùng meter names và tag cardinality dự kiến;
- bật histogram chỉ cho metric cần thiết;
- chạy scrape/export với interval thật;
- đo series count, scrape duration, payload và RSS.

**Bước 5 — bật tracing**

- chọn sampling ratio dự kiến;
- dùng batch export và collector tương đương;
- tạo trace có HTTP/database/client spans;
- đo spans/request, queue, export latency và p99.

**Bước 6 — bật toàn bộ observability**

Chạy lại cùng workload. So sánh kết quả tổng hợp với từng cấu hình riêng để phát hiện tương tác giữa các tín hiệu.

**Bước 7 — lặp lại trên native executable**

Build native từ cùng source/dependency và cấu hình AOT tương ứng. Chạy cùng workload, collector, sampling và log level. Ghi riêng thời gian native build; không gộp nó vào startup time.

**Bước 8 — fault test**

Làm chậm hoặc dừng collector, tăng log volume, tạo nhiều request nhưng giữ metric tags ổn định, rồi kiểm tra queue, drop, latency và khả năng phục hồi.

## 15. Checklist trước khi công bố số đo

- [ ] Đã ghi rõ cấu hình logging, metrics và tracing trong từng lần đo.
- [ ] Log hot path không format hoặc serialize dữ liệu lớn khi không cần.
- [ ] Async logging có queue giới hạn, overflow policy và shutdown behavior rõ.
- [ ] Audit/security events không bị sample ngoài chính sách.
- [ ] Metric tags có cardinality thấp và ổn định.
- [ ] Histogram/percentile chỉ bật ở metric cần thiết.
- [ ] Scrape interval và exporter batching được ghi nhận.
- [ ] Tracing sampling ratio và sampler type được ghi nhận.
- [ ] Span export dùng batch/timeout/queue giới hạn phù hợp.
- [ ] Trace ID không được dùng làm metric label.
- [ ] Không log hoặc export secret, credential hay payload nhạy cảm.
- [ ] Đã đo startup-to-ready và time-to-first-useful-request riêng.
- [ ] Đã đo throughput, p50/p95/p99, CPU, RSS, queue và drop count.
- [ ] JVM warm-up và native build/startup được tách biệt.
- [ ] Cùng workload và collector được dùng khi so sánh.
- [ ] Native executable đã được kiểm tra provider, resource, TLS và shutdown flush.
- [ ] Đã kiểm tra collector unavailable và queue saturation.

**Ghi nhớ:** logging, metrics và tracing đều có chi phí CPU, memory, I/O và network. Cardinality cao, log event quá dày, histogram không cần thiết và span export đồng bộ có thể làm sai lệch số đo hoặc ảnh hưởng latency. Hãy đo từng tín hiệu riêng, đo lại cấu hình production-like, rồi lặp lại trên native executable với cùng workload và điều kiện triển khai.

## Tài liệu tham khảo

- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, Actuator metrics và cấu hình registry.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling và tích hợp exporter.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): meter types, registry, filters, timers và cardinality.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling và cách giảm lượng trace được export.
- [OpenTelemetry — Batch Span Processor](https://opentelemetry.io/docs/specs/otel/trace/sdk/): span processor, batching và SDK behavior.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): synchronous/asynchronous appenders và queue behavior.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata cho reflection, resource và service loading trong native executable.
