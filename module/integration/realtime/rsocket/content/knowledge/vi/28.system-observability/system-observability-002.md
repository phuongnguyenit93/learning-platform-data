# Theo dõi độ trễ, lưu lượng, lỗi và số luồng đang hoạt động

## Mục tiêu bài học

Một hệ thống RSocket có thể duy trì nhiều tương tác bất đồng bộ trên một kết nối. Chỉ nhìn số kết nối TCP đang mở không cho biết hệ thống đang xử lý bao nhiêu request, stream nào bị chậm, route nào phát sinh lỗi hoặc consumer nào đang tạo áp lực lên server.

Để vận hành RSocket, cần theo dõi ít nhất bốn nhóm tín hiệu:

- **Độ trễ (latency):** thời gian xử lý request, thời gian tới response đầu tiên và thời lượng của stream.
- **Lưu lượng (traffic):** số request, số payload, số byte và tốc độ phát/nhận dữ liệu.
- **Lỗi (errors):** lỗi kết nối, lỗi SETUP, lỗi decode, lỗi handler, timeout và cancellation.
- **Luồng đang hoạt động (active streams):** số tương tác RSocket hoặc publisher đang được xử lý tại một thời điểm.

Sau bài này, bạn có thể:

- Phân biệt connection, stream, request và payload.
- Chọn metric phù hợp cho latency, traffic, errors và active streams.
- Instrument handler reactive bằng Micrometer Timer, Counter và Gauge.
- Theo dõi request-response, request-stream và request-channel đúng vòng đời.
- Phân biệt metric ở tầng ứng dụng với metric ở tầng protocol/transport.
- Thiết kế dashboard, alert và tag có cardinality an toàn.
- Kết hợp metric, log và distributed tracing để tìm nguyên nhân sự cố.

## Connection, stream, request và payload là các đại lượng khác nhau

RSocket multiplex nhiều stream trên cùng một connection. Vì vậy, một connection không đồng nghĩa với một request hoặc một stream.

| Khái niệm | Ý nghĩa | Metric có thể theo dõi |
|---|---|---|
| Connection | Kênh transport TCP hoặc WebSocket giữa hai peer | Số connection đang mở, số lần kết nối/ngắt |
| Stream | Một interaction RSocket được nhận diện bằng stream ID trong session | Số stream đang hoạt động, thời lượng stream |
| Request | Thông điệp mở đầu interaction hoặc một command nghiệp vụ | Số request theo route và interaction model |
| Payload | Data và metadata được truyền trong frame | Số payload, kích thước payload |
| Frame | Đơn vị giao thức RSocket | Số frame theo loại, byte frame, lỗi protocol |

Một client có thể mở một connection và đồng thời tạo nhiều request-response, request-stream hoặc request-channel. Khi một request-response hoàn tất, connection vẫn có thể tiếp tục phục vụ các stream khác.

Do đó, dashboard chỉ có metric connection count sẽ bỏ lỡ tình trạng một route tạo ra hàng nghìn stream hoặc một stream bị treo quá lâu.

## Bốn nhóm tín hiệu cần theo dõi

~~~mermaid
flowchart TB
    A[RSocket Service] --> B[Latency]
    A --> C[Traffic]
    A --> D[Errors]
    A --> E[Active streams]
    B --> F[Timer / Histogram]
    C --> G[Counter / DistributionSummary]
    D --> H[Counter theo nhóm lỗi]
    E --> I[Gauge / LongTaskTimer]
    F --> J[Dashboard / Alerts]
    G --> J
    H --> J
    I --> J
~~~

### Độ trễ

Latency trả lời câu hỏi một tương tác mất bao lâu. Với RSocket cần phân biệt:

- **Request-response latency:** từ lúc client gửi request hoặc server nhận request đến khi response hoàn tất.
- **Time to first response:** thời gian từ lúc mở request-stream/request-channel đến payload response đầu tiên.
- **Stream duration:** từ lúc subscribe/mở stream đến khi complete, error hoặc cancel.
- **Handler processing time:** thời gian code nghiệp vụ xử lý, có thể ngắn hơn end-to-end latency nếu còn queue, network hoặc serialization.

Không gộp các loại này vào một metric duy nhất. Request-stream có thể trả payload đầu tiên nhanh nhưng tiếp tục sống hàng giờ. Nếu chỉ đo thời lượng toàn stream, dashboard sẽ không phản ánh độ trễ mà người dùng cảm nhận khi chờ dữ liệu đầu tiên.

Nên quan sát percentile p50, p95 và p99. Trung bình có thể che khuất một nhóm request chậm. Với histogram, có thể phân tích phân bố và so sánh các route hoặc interaction model có cardinality giới hạn.

### Lưu lượng

Traffic trả lời hệ thống đang nhận và phát bao nhiêu dữ liệu:

- Request bắt đầu mỗi giây.
- Payload inbound/outbound mỗi giây.
- Byte inbound/outbound mỗi giây.
- Số event phát trên mỗi stream.
- Số frame theo loại nếu instrument ở tầng protocol.
- Số request bị từ chối do quota hoặc giới hạn tài nguyên.

Counter thường phù hợp với số sự kiện tích lũy. Khi hiển thị dashboard, xem tốc độ tăng của counter theo khoảng thời gian thay vì chỉ nhìn tổng từ lúc process khởi động.

Timer và DistributionSummary cũng lưu count. Không cần tạo một counter thứ hai cho cùng sự kiện chỉ để đếm số lần đã được Timer ghi nhận.

### Lỗi

Không gom mọi lỗi vào một con số. Nên phân loại theo nguồn:

- Transport: connection reset, connection timeout, WebSocket close bất thường.
- Setup/protocol: SETUP bị từ chối, MIME type không tương thích, frame không hợp lệ.
- Decode/encode: payload hoặc metadata không thể chuyển đổi.
- Application: exception trong handler hoặc service nghiệp vụ.
- Timeout: request không hoàn tất trong SLA.
- Resource/flow control: vượt quota, quá kích thước payload, queue đầy hoặc bị từ chối.
- Cancellation: subscriber chủ động hủy hoặc stream kết thúc do không còn nhu cầu.

Cancellation thường là một tín hiệu vòng đời bình thường, không nên tự động tính là lỗi ứng dụng. Hãy theo dõi riêng để phát hiện client đóng trang, subscriber chậm hoặc stream bị hủy bất thường.

Error rate nên được tính trên số request kết thúc trong cùng phạm vi thời gian. Nếu chỉ nhìn error count tích lũy, không thể so sánh service chạy một giờ với service chạy một tháng.

### Số luồng đang hoạt động

Active streams là số tương tác chưa kết thúc tại một thời điểm. Nó khác với:

- Số connection đang mở.
- Số request đã nhận trong một phút.
- Số thread đang chạy.
- Số subscriber của một Flux bất kỳ.

Có thể theo dõi active interactions ở ranh giới handler hoặc interceptor. Tăng gauge khi publisher được subscribe và giảm khi publisher complete, error hoặc cancel.

Với request-stream dài hạn, active stream có thể cao nhưng bình thường. Điều quan trọng là so sánh với baseline, giới hạn tài nguyên và thời lượng stream. Cần phân biệt stream dự kiến sống lâu với stream bị treo, không phát dữ liệu và không được cancel.

## Thiết lập Micrometer và Spring Boot Actuator

Spring Boot Actuator cung cấp auto-configuration và dependency management cho Micrometer. Thêm Actuator và registry backend mà hệ thống dùng, ví dụ Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Cấu hình endpoint quản lý:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: inventory-rsocket
~~~

Khi registry có mặt trên runtime classpath, Spring Boot có thể tự cấu hình MeterRegistry phù hợp. Endpoint `/actuator/metrics` giúp kiểm tra meter trong môi trường được bảo vệ; `/actuator/prometheus` xuất định dạng để Prometheus scrape khi registry Prometheus được cấu hình.

Không expose endpoint quản lý công khai mà không có bảo vệ mạng và xác thực phù hợp. Nếu ứng dụng dùng một backend khác, thêm registry tương ứng và cấu hình export theo môi trường.

Spring Boot cũng cung cấp các metric JVM và system như heap, garbage collection, thread, CPU và buffer pool. Các metric này giúp giải thích vì sao latency hoặc số stream tăng, ví dụ direct memory tăng, GC pause dài hoặc event-loop/thread pool bị bão hòa.

Nếu ứng dụng dùng Spring Integration và có MeterRegistry, Spring Integration tự cung cấp Micrometer metrics dưới namespace `spring.integration.` Các metric này bổ sung cho metric RSocket do ứng dụng instrument.

### Không giả định mọi metric RSocket đều có sẵn

Actuator tự động cung cấp registry và nhiều metric nền tảng. Điều đó không có nghĩa mọi route RSocket, interaction model, active stream hoặc payload byte đều được tự động đo theo hợp đồng nghiệp vụ.

Hãy kiểm tra metric thực tế của phiên bản Spring Boot, Spring Framework và RSocket Java đang dùng. RSocket Java có module `rsocket-micrometer` và hỗ trợ Micrometer Observation ở một số phiên bản; API và meter cụ thể phụ thuộc phiên bản thư viện. Dù dùng instrumentation protocol, vẫn nên đo latency và kết quả nghiệp vụ tại handler để biết route nào chậm hoặc thất bại.

## Chọn meter type cho từng mục tiêu

| Meter | Dùng để đo | Ví dụ |
|---|---|---|
| Counter | Số sự kiện tích lũy | Request bắt đầu, lỗi, payload phát |
| Timer | Thời lượng và số lần hoàn tất | Request-response latency, stream duration |
| DistributionSummary | Phân bố giá trị số | Kích thước payload theo byte |
| Gauge | Giá trị tại thời điểm hiện tại | Active stream, connection đang mở, queue depth |
| LongTaskTimer | Số tác vụ đang chạy và thời lượng hiện tại | Handler/stream dài hạn |

Timer tự cung cấp count, total time và các thống kê/histogram tùy cấu hình backend. DistributionSummary cũng có count và phân bố giá trị. Hãy tránh đếm lặp cùng một sự kiện bằng nhiều meter không cần thiết.

Gauge nên đọc từ một state object có vòng đời dài như `AtomicInteger`. Không tạo một gauge mới cho mỗi request hoặc giữ gauge trỏ tới object chỉ tồn tại trong một method.

## Instrument request-response bằng Timer và Counter

Ví dụ dưới đây đo thời lượng publisher request-response tại ranh giới handler. Mỗi lần subscribe tạo một sample mới; khi publisher complete, error hoặc cancel, Timer được ghi và active gauge được giảm.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Component
class RSocketInteractionMetrics {

    private final MeterRegistry registry;
    private final AtomicInteger activeInteractions = new AtomicInteger();

    RSocketInteractionMetrics(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder(
                "rsocket.interactions.active",
                activeInteractions,
                AtomicInteger::get
            )
            .description("Số interaction RSocket đang hoạt động tại handler")
            .register(registry);
    }

    <T> Mono<T> observeMono(
            String route,
            String interaction,
            Mono<T> source) {

        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);
            activeInteractions.incrementAndGet();

            registry.counter(
                "rsocket.interactions.started",
                "route", route,
                "interaction", interaction
            ).increment();

            return source
                .doOnError(error -> recordError(route, interaction, error))
                .doFinally(signal -> {
                    activeInteractions.decrementAndGet();
                    sample.stop(
                        Timer.builder("rsocket.interactions.duration")
                            .description("Thời lượng interaction RSocket")
                            .publishPercentileHistogram()
                            .tag("route", route)
                            .tag("interaction", interaction)
                            .tag("outcome", outcome(signal))
                            .register(registry)
                    );
                });
        });
    }

    private void recordError(
            String route,
            String interaction,
            Throwable error) {

        registry.counter(
            "rsocket.interactions.errors",
            "route", route,
            "interaction", interaction,
            "error", classify(error)
        ).increment();
    }

    private String outcome(SignalType signal) {
        if (signal == SignalType.ON_COMPLETE) {
            return "completed";
        }
        if (signal == SignalType.ON_ERROR) {
            return "error";
        }
        if (signal == SignalType.CANCEL) {
            return "cancelled";
        }
        return "other";
    }

    private String classify(Throwable error) {
        if (error instanceof java.util.concurrent.TimeoutException) {
            return "timeout";
        }
        return "application";
    }
}
~~~

Có thể đơn giản hóa bằng cách tạo và giữ sẵn các Timer theo route/interaction nếu danh sách route cố định. Trong ví dụ, builder được đăng ký để minh họa tag và histogram; trong code production nên gom cấu hình meter vào một nơi và tránh tạo cấu hình không nhất quán giữa các lần gọi.

Inject metrics component vào controller qua constructor, sau đó bọc publisher được trả về:

~~~java
@Controller
class InventoryController {

    private final InventoryService inventoryService;
    private final RSocketInteractionMetrics metrics;

    InventoryController(
            InventoryService inventoryService,
            RSocketInteractionMetrics metrics) {
        this.inventoryService = inventoryService;
        this.metrics = metrics;
    }

    @MessageMapping("inventory.lookup")
    Mono<InventoryView> lookup(InventoryRequest request) {
        return metrics.observeMono(
            "inventory.lookup",
            "request_response",
            inventoryService.find(request.sku())
        );
    }
}
~~~

Timer ở đây đo thời gian từ lúc handler publisher được subscribe tới terminal signal. Nó bao gồm thời gian chờ trong các toán tử reactive nằm trong publisher, nhưng không bao gồm thời gian WebSocket/TCP handshake hoặc thời gian client chờ trước khi gửi request. Nếu cần end-to-end latency, instrument thêm ở client hoặc dùng distributed tracing.

## Theo dõi request-stream và request-channel

Với stream, thời gian tới payload đầu tiên và thời lượng toàn stream là hai đại lượng khác nhau.

Ví dụ wrapper cho Flux đo số interaction đang hoạt động và thời lượng tới terminal signal:

~~~java
<T> Flux<T> observeFlux(
        String route,
        String interaction,
        Flux<T> source) {

    return Flux.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        activeInteractions.incrementAndGet();

        registry.counter(
            "rsocket.interactions.started",
            "route", route,
            "interaction", interaction
        ).increment();

        return source
            .doOnNext(value ->
                registry.counter(
                    "rsocket.payloads.out",
                    "route", route,
                    "interaction", interaction
                ).increment()
            )
            .doOnError(error -> recordError(route, interaction, error))
            .doFinally(signal -> {
                activeInteractions.decrementAndGet();

                sample.stop(
                    Timer.builder("rsocket.interactions.duration")
                        .tag("route", route)
                        .tag("interaction", interaction)
                        .tag("outcome", outcome(signal))
                        .register(registry)
                );
            });
    });
}
~~~

Trong ví dụ, `payloads.out` đếm phần tử được publisher phát ra tại ranh giới đang instrument. Nếu muốn đo payload inbound, đặt bộ đếm ở chiều nhận tương ứng. Số phần tử ở handler không nhất thiết bằng số frame trên wire vì fragmentation, metadata và control frame có thể làm thay đổi số frame.

Để đo time-to-first-item, bắt đầu một Timer.Sample khi subscribe và dừng ở `doOnNext` đầu tiên. Với Flux hoàn tất rỗng hoặc lỗi trước phần tử đầu tiên, cần ghi outcome riêng như `empty` hoặc `error_before_first`; không để sample bị bỏ quên. Stream có thể phát nhiều phần tử nên chỉ ghi time-to-first-item một lần cho mỗi subscription.

Request-channel cần quan sát cả hai chiều:

- Số command client gửi vào server.
- Số event server phát về client.
- Thời gian xử lý từng command nếu cần.
- Thời lượng toàn channel.
- Số channel đang hoạt động và số channel bị cancel.

Đừng chỉ đo số response để suy ra số request đã xử lý. Một request-channel có thể nhận command nhưng không phát response cho từng command, tùy hợp đồng nghiệp vụ.

## Đếm active streams chính xác

Để đếm active interaction ở tầng handler, tăng bộ đếm khi publisher được subscribe và giảm trong `doFinally`. `doFinally` được gọi khi complete, error hoặc cancel, nên đây là vị trí phù hợp để thu hồi bộ đếm.

Các lưu ý:

- Bọc publisher bằng `Mono.defer` hoặc `Flux.defer` để mỗi subscription có một lần tăng/giảm riêng.
- Không tăng counter khi chỉ tạo publisher; publisher có thể chưa bao giờ được subscribe.
- Không giảm counter chỉ ở `doOnComplete`, vì error và cancel cũng phải giảm.
- Không dùng `doOnTerminate` một mình để xử lý cancellation.
- Nếu retry tạo subscription mới, mỗi lần subscribe là một vòng đời mới và phải được đếm nhất quán.
- Giữ state object của Gauge sống cùng bean/application context.

Metric `rsocket.interactions.active` trong ví dụ là số publisher đang hoạt động tại ranh giới handler. Nó không phải số stream protocol ở toàn bộ transport. Nếu cần đếm stream ở tầng RSocket, instrument responder/requester interceptor hoặc API protocol tương ứng của phiên bản RSocket Java.

Connection count cũng cần được đo riêng từ vòng đời connection. Không cộng active stream với connection count vì hai đại lượng không cùng đơn vị.

## Theo dõi traffic và kích thước payload

Có thể dùng Counter cho số payload và DistributionSummary cho kích thước payload đã encode:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;

DistributionSummary payloadSize = DistributionSummary
    .builder("rsocket.payload.size")
    .baseUnit("bytes")
    .description("Kích thước payload tại ranh giới ứng dụng")
    .tag("direction", "out")
    .register(registry);

Counter payloadsOut = registry.counter(
    "rsocket.payloads.out",
    "route", "inventory.lookup"
);

void recordEncodedPayload(byte[] encoded) {
    payloadsOut.increment();
    payloadSize.record(encoded.length);
}
~~~

`encoded.length` ở đây là số byte Data đã encode theo ví dụ. Nếu cần wire bytes, phải đo ở transport/protocol layer và tính cả frame header, metadata, fragmentation và control frame. Không gọi kích thước object Java hoặc độ dài chuỗi trước serialization là wire bytes.

Các chỉ số traffic hữu ích:

| Metric | Đơn vị | Dùng để |
|---|---|---|
| Request started | request/second | Lưu lượng tương tác mới |
| Payload count | payload/second | Tốc độ event/message |
| Payload size | bytes | Phân bố kích thước dữ liệu |
| Wire bytes in/out | bytes/second | Băng thông thực tế |
| Frame count by type | frames/second | Hiểu tải protocol |
| Rejected requests | requests/second | Phát hiện quota hoặc saturation |

Nếu không có protocol-level instrumentation, hãy đặt tên metric theo đúng ranh giới đo, ví dụ `application_payload_bytes`, không đặt tên `network_bytes`.

## Phân loại lỗi và tính error rate

Một metric lỗi hữu ích cần có route, interaction model và nhóm lỗi có tập giá trị hữu hạn:

~~~java
registry.counter(
    "rsocket.interactions.errors",
    "route", "inventory.lookup",
    "interaction", "request_response",
    "error", "timeout"
).increment();
~~~

Các nhóm lỗi gợi ý:

| Nhóm | Ví dụ |
|---|---|
| `transport` | Connection reset, WebSocket closed |
| `setup` | SETUP bị từ chối, MIME type không khớp |
| `decode` | JSON hoặc metadata không giải mã được |
| `timeout` | Hết thời gian chờ |
| `application` | Exception trong service nghiệp vụ |
| `resource_limit` | Payload quá lớn, quota hoặc queue đầy |

Không đưa thông điệp exception tự do vào tag. Thông điệp thường chứa dữ liệu biến đổi và có thể làm tăng số time series. Hãy phân loại thành nhóm cố định, còn stack trace và chi tiết lỗi để trong log.

Error rate:

```text
error rate = số interaction kết thúc bằng lỗi / tổng interaction kết thúc
```

Tính trên cùng cửa sổ thời gian và cùng phạm vi route/interaction. Có thể theo dõi riêng cancellation rate; không tự động gộp cancel vào application error nếu cancellation là hành vi bình thường của subscriber.

## Tránh cardinality explosion

Metric tag được dùng để phân nhóm time series. Nếu tag có vô số giá trị, backend sẽ phải lưu và xử lý quá nhiều series.

Tag thường an toàn khi giá trị có tập hữu hạn:

- `route`: route đã đăng ký trong ứng dụng.
- `interaction`: request_response, fire_and_forget, request_stream, request_channel.
- `transport`: tcp, websocket.
- `outcome`: completed, error, cancelled.
- `error`: nhóm lỗi cố định.
- `service` hoặc `region`: tập giá trị được quản lý.

Không dùng các giá trị sau làm metric tag:

- Stream ID hoặc connection ID.
- Request ID, correlation ID hoặc trace ID.
- User ID, email, tenant ID tùy ý.
- URL/path có biến hoặc route do người dùng tự tạo.
- Exception message hoặc payload content.

Các giá trị có cardinality cao vẫn hữu ích trong trace và log. Dùng trace ID để tìm một request cụ thể, rồi xem metric theo route/interaction để hiểu xu hướng chung.

## Dashboard vận hành RSocket

Một dashboard nên trả lời các câu hỏi theo thứ tự:

1. Service có đang nhận request không?
2. Request rate và payload rate đang tăng hay giảm?
3. p95/p99 latency có vượt SLA không?
4. Error rate tăng ở route hoặc interaction nào?
5. Active streams có tăng bất thường không?
6. Connection count, queue depth, CPU, heap, direct memory và event-loop có dấu hiệu bão hòa không?

Gợi ý bố cục:

| Panel | Nội dung |
|---|---|
| Traffic | Request/s, payload/s, bytes/s theo chiều |
| Latency | p50/p95/p99 request-response, time-to-first-item, stream duration |
| Errors | Error rate theo route và nhóm lỗi; cancellation riêng |
| Active | Active interactions, active connections, stream duration |
| Saturation | Queue depth, CPU, heap/direct memory, GC pause, thread/event-loop |
| Dependency | Latency và lỗi của database/service mà handler gọi |

Đừng chỉ vẽ một đường active streams. Hãy đặt cạnh traffic, latency và error rate để biết số stream tăng do tải hợp lệ hay do stream bị giữ quá lâu.

## Alert theo hành vi, không chỉ theo ngưỡng tuyệt đối

Một số cảnh báo thường dùng:

- p95 request-response latency vượt SLA liên tục trong một cửa sổ thời gian.
- Error rate tăng trên một ngưỡng và có đủ số request để tránh cảnh báo từ mẫu quá nhỏ.
- Active stream tăng liên tục trong khi request rate giảm hoặc stream duration tăng.
- Connection reset hoặc SETUP failure tăng đột biến.
- Queue depth hoặc pending request tăng liên tục.
- Direct memory, heap hoặc GC pause tiến gần giới hạn vận hành.
- Không có traffic ngoài khung bảo trì đối với service vốn phải nhận request liên tục.

Ví dụ biểu thức PromQL minh họa:

~~~promql
sum(rate(rsocket_interactions_started_total[5m]))
~~~

Tính tốc độ request bắt đầu trên toàn service.

~~~promql
sum(rate(rsocket_interactions_errors_total[5m]))
/
sum(rate(rsocket_interactions_duration_seconds_count[5m]))
~~~

Ước lượng tỷ lệ lỗi trên số interaction đã kết thúc trong cùng khoảng thời gian. Tên metric thực tế phụ thuộc naming convention của registry và backend; kiểm tra `/actuator/prometheus` trước khi đưa biểu thức vào alert.

Với histogram duration, p95 có thể được tính theo bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(rsocket_interactions_duration_seconds_bucket[5m])
  )
)
~~~

Chỉ dùng truy vấn histogram khi timer đã publish histogram buckets và backend nhận được các series tương ứng.

## Kết hợp metric, log và distributed tracing

Ba loại telemetry phục vụ ba câu hỏi khác nhau:

| Telemetry | Câu hỏi | Ví dụ |
|---|---|---|
| Metric | Vấn đề xảy ra thường xuyên đến mức nào? | p99 latency tăng ở route inventory.lookup |
| Log | Một lần xử lý cụ thể đã xảy ra điều gì? | Timeout khi gọi inventory database |
| Trace | Thời gian bị tiêu tốn ở service/span nào? | 20 ms ở gateway, 900 ms ở database |

Micrometer Observation có thể tạo metric và span từ cùng một instrumentation khi ObservationRegistry được cấu hình handler phù hợp. Khi instrument code, hãy ghi nhận lỗi và dừng Observation đúng vòng đời; chỉ các low-cardinality key được dùng làm meter tags.

Ví dụ Observation bao quanh một thao tác nghiệp vụ:

~~~java
import io.micrometer.observation.ObservationRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Mono;

Mono<InventoryView> find(
        String sku,
        ObservationRegistry observationRegistry) {

    return inventoryRepository.find(sku)
        .name("rsocket.inventory.lookup")
        .tap(Micrometer.observation(observationRegistry));
}
~~~

Ví dụ dùng module `reactor-core-micrometer` tương thích với phiên bản Reactor đang chạy. Toán tử `tap` gắn Observation vào vòng đời subscription của publisher, vì vậy thời gian được ghi tới khi sequence complete, error hoặc cancel. Có thể dùng Observation handler để xuất metric, span hoặc cả hai. Nếu chỉ gọi `Observation.observe(() -> publisher)`, thời gian có thể chỉ bao quanh việc tạo publisher thay vì lúc publisher kết thúc.

Không đưa trace ID thành metric tag. Trace backend đã có cơ chế tra cứu theo trace ID.

## Theo dõi RSocket và các dependency phía sau

Một handler có thể phản hồi chậm vì database, cache, service khác hoặc queue, không phải vì RSocket transport. Hãy instrument các ranh giới dependency:

- Thời gian chờ connection pool.
- Query latency và timeout database.
- Outbound RSocket latency tới service đích.
- Queue depth và consumer lag.
- Retry count và số lần circuit breaker mở.
- Serialization/deserialization time nếu payload lớn.

Ví dụ, nếu handler p99 tăng cùng lúc database p99 tăng, vấn đề có thể nằm ở storage. Nếu database ổn định nhưng active streams và queue depth tăng, hãy kiểm tra demand, cancellation và downstream consumer.

## Kiểm thử instrumentation

Không chỉ kiểm tra endpoint metrics có tồn tại. Hãy kiểm tra vòng đời và giá trị:

1. Một request-response thành công làm tăng request count và ghi một Timer.
2. Một request lỗi tăng error counter với nhóm lỗi cố định.
3. Một request bị cancel giảm active gauge và được ghi outcome cancelled.
4. Một Flux đang hoạt động làm active gauge tăng.
5. Flux complete/error/cancel đều làm active gauge trở về giá trị ban đầu.
6. Hai subscription cùng dùng một publisher được đếm thành hai vòng đời độc lập nếu source cho phép.
7. Request-stream ghi time-to-first-item một lần và stream duration khi kết thúc.
8. Payload size được đo sau serialization nếu metric mang ý nghĩa encoded bytes.
9. Tag chỉ dùng tập giá trị hữu hạn.
10. Metric export hoạt động qua registry backend trong môi trường test.

Dùng `SimpleMeterRegistry` trong unit test để kiểm tra Counter, Timer và Gauge. Với Prometheus hoặc backend thật, có integration test để xác nhận tên meter và bucket được export đúng.

## Checklist quan sát hệ thống

Trước khi triển khai RSocket production, hãy trả lời:

1. Có metric riêng cho connection và active stream không?
2. Request-response latency có được đo ở ranh giới rõ ràng không?
3. Request-stream có time-to-first-item và stream duration không?
4. Traffic count có phân biệt request, payload và wire frame không?
5. Payload size được đo trước hay sau serialization?
6. Error được phân nhóm và cancellation được theo dõi riêng chưa?
7. Active gauge có giảm trong complete, error và cancel không?
8. Route/interaction tags có cardinality giới hạn không?
9. Dashboard có traffic, latency, errors, active và saturation không?
10. Alert có dựa trên rate/percentile và đủ số mẫu không?
11. Log và trace có correlation context để điều tra một request không?
12. Có kiểm thử instrumentation khi lỗi, timeout và cancel không?

Độ trễ, lưu lượng, lỗi và số luồng đang hoạt động tạo thành góc nhìn cơ bản về sức khỏe RSocket. Dùng Timer cho thời lượng, Counter cho sự kiện, Gauge cho trạng thái hiện tại và phân biệt rõ metric ở tầng ứng dụng với metric protocol. Khi kết hợp chúng với log, trace và chỉ số JVM, đội vận hành có thể nhận ra route chậm, lỗi tăng, stream bị giữ lâu và điểm nghẽn phía sau trước khi ảnh hưởng lan rộng.

## Tài liệu tham khảo

- [Spring Boot Reference: Metrics and Micrometer](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference: Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Framework Reference: Observability support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Micrometer Reference: Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Reference: Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference: Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Reactor Reference: Micrometer metrics and Observation](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [RSocket Java repository and rsocket-micrometer module](https://github.com/rsocket/rsocket-java)

