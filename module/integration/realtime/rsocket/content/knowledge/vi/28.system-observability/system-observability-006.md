# Truyền mã tương quan và ngữ cảnh truy vết qua metadata

Trong hệ thống phân tán, một yêu cầu của người dùng có thể đi qua HTTP gateway, nhiều dịch vụ Spring Boot và một hoặc nhiều RSocket connection. Khi có lỗi hoặc độ trễ bất thường, log của từng dịch vụ thường không đủ để biết các thao tác nào thuộc cùng một yêu cầu. Distributed tracing giải quyết vấn đề này bằng cách gắn các span vào một trace chung và truyền ngữ cảnh truy vết qua ranh giới dịch vụ.

RSocket mang data và metadata riêng biệt. Metadata có thể chứa route, thông tin bảo mật hoặc tracing context. Với Spring `RSocketRequester`, ứng dụng có thể đưa trace context vào một metadata entry trong Composite Metadata và giải mã entry đó ở responder. Bài này tập trung vào cách truyền W3C Trace Context và correlation ID qua RSocket, cách nối với Micrometer Tracing và cách tránh mất context khi chạy reactive.

## 1. Correlation ID, trace ID, span ID và baggage

Các khái niệm này liên quan nhưng không thay thế cho nhau:

| Khái niệm | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| Correlation ID | Mã do ứng dụng hoặc gateway dùng để tìm các log và sự kiện liên quan. | Theo hợp đồng nghiệp vụ hoặc yêu cầu. |
| Trace ID | Định danh toàn bộ một distributed trace. | Dùng chung qua các dịch vụ tham gia trace. |
| Span ID | Định danh một thao tác cụ thể, chẳng hạn một lần gọi RSocket. | Duy nhất cho từng span trong trace. |
| Parent span ID | Span ở phía gọi đã tạo ra thao tác hiện tại. | Liên kết span cha và span con. |
| Baggage | Các thuộc tính ngữ cảnh được truyền cùng trace, ví dụ tenant tier hoặc business region. | Chỉ các field được cho phép propagate. |
| Trace state | Dữ liệu mở rộng theo vendor của hệ thống tracing. | Đi cùng W3C Trace Context. |

Ví dụ một yêu cầu đi qua ba dịch vụ:

~~~text
HTTP Gateway
  traceId = T-100
  spanId  = S-01
       |
       | RSocket request + trace context
       v
Order Service
  traceId = T-100
  spanId  = S-02
  parent  = S-01
       |
       | RSocket request + trace context
       v
Inventory Service
  traceId = T-100
  spanId  = S-03
  parent  = S-02
~~~

Trace ID giữ nguyên trong cùng trace. Mỗi dịch vụ tạo span riêng và đặt span của caller làm parent. Nhờ đó, hệ thống tracing có thể dựng cây hoặc đồ thị thời gian của toàn bộ luồng xử lý.

Correlation ID có thể trùng với một mã nghiệp vụ hoặc được tạo riêng. Không nên tự đặt correlation ID vào trường trace ID nếu nó không tuân theo định dạng và quy tắc của tracing system. Nếu cần tìm theo cả hai, hãy ghi cả correlation ID và trace ID vào log.

## 2. W3C Trace Context

W3C Trace Context chuẩn hóa cách truyền thông tin trace qua các giao thức. Hai field chính là:

- `traceparent`: chứa version, trace ID, parent ID và trace flags.
- `tracestate`: chứa thông tin mở rộng theo vendor, có thể được giữ nguyên hoặc cập nhật theo quy tắc W3C.

Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor-a=opaque-value
~~~

Với phiên bản `00`, `traceparent` có cấu trúc:

| Thành phần | Độ dài | Mục đích |
| --- | --- | --- |
| Version | 2 ký tự hex | Phiên bản định dạng. |
| Trace ID | 32 ký tự hex | Định danh trace, không được toàn số 0. |
| Parent ID | 16 ký tự hex | Span ID của thao tác gọi, không được toàn số 0. |
| Trace flags | 2 ký tự hex | Các cờ trace, bit sampled là cờ thường gặp. |

Trace context không phải dữ liệu xác thực. Không dùng trace ID để cấp quyền, xác định người dùng hoặc làm idempotency key. Caller có thể gửi trace header không hợp lệ hoặc cố tình thay đổi giá trị; tracing implementation phải xác thực cú pháp và áp dụng chính sách sampling riêng.

## 3. RSocket metadata và vị trí đặt trace context

Một RSocket message có data và metadata. Metadata có thể được mã hóa bằng nhiều MIME type độc lập. Với Composite Metadata, một payload metadata có thể chứa nhiều entry, ví dụ:

| Metadata entry | MIME type | Mục đích |
| --- | --- | --- |
| Route | `message/x.rsocket.routing.v0` | Chọn handler ở responder. |
| Authentication | `message/x.rsocket.authentication.v0` | Mang credential theo extension xác thực. |
| Tracing | Theo extension hoặc MIME type ứng dụng | Mang trace context. |
| Correlation | MIME type ứng dụng | Mang mã tương quan riêng của ứng dụng. |

Spring `RSocketRequester.Builder` mặc định dùng Composite Metadata. Vì vậy, route và một hoặc nhiều metadata entry khác có thể cùng tồn tại trên một request.

Trace context thường thuộc về từng interaction, vì vậy nên gắn vào metadata của REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL hoặc REQUEST_FNF tương ứng. Không nên đưa trace context của một request cụ thể vào SETUP rồi dùng lại cho mọi request trên connection.

SETUP và METADATA_PUSH có phạm vi connection-level. Chúng phù hợp với dữ liệu khởi tạo hoặc cập nhật context chung cho connection, nhưng không đại diện cho parent span của từng interaction. Một RSocket connection có thể phục vụ nhiều request đồng thời với trace ID khác nhau.

## 4. RSocket có tracing metadata extension chuẩn nào?

RSocket định nghĩa tracing metadata extension tương thích với Zipkin B3:

<code>message/x.rsocket.tracing-zipkin.v0</code>

RSocket Java cung cấp `TracingMetadata` và `TracingMetadataCodec` để mã hóa/giải mã định dạng này ở mức API protocol. Đây là định dạng B3 của extension RSocket, không phải định dạng W3C `traceparent`.

Có hai hướng triển khai:

1. Nếu các thành phần trong hệ thống đã thống nhất dùng RSocket tracing extension B3, hãy dùng đúng MIME type và codec B3 tương ứng.
2. Nếu hệ thống dùng W3C Trace Context với Micrometer hoặc OpenTelemetry, hãy truyền các field W3C qua một metadata entry đã thống nhất và cấu hình encoder/decoder ở hai phía.

Không đặt dữ liệu W3C `traceparent` vào MIME type Zipkin B3. Hai định dạng có cấu trúc khác nhau. Cũng không giả định `MetadataExtractor` tự giải mã mọi extension tracing; Spring có hỗ trợ routing sẵn, còn metadata tùy chỉnh cần được đăng ký decoder hoặc extractor tương ứng.

## 5. Cấu hình Micrometer Tracing trong Spring Boot

Spring Boot Actuator tích hợp Micrometer Tracing và hỗ trợ tracer như OpenTelemetry hoặc OpenZipkin Brave. Tracer tạo span, propagator mã hóa/giải mã trace context, còn exporter gửi span tới backend như OTLP collector hoặc Zipkin.

Một cấu hình YAML minh họa:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: W3C
    baggage:
      remote-fields:
        - tenant-tier
      correlation:
        fields:
          - tenant-tier

spring:
  reactor:
    context-propagation: auto
~~~

Giải thích:

- `management.tracing.propagation.type: W3C` chọn W3C làm định dạng propagation được tạo và tiêu thụ.
- `sampling.probability: 1.0` hữu ích trong môi trường học tập hoặc test để dễ nhìn thấy mọi trace. Không nên mặc định bật 100% trong production có lưu lượng lớn.
- `baggage.remote-fields` liệt kê các field được phép truyền qua ranh giới dịch vụ.
- `baggage.correlation.fields` đưa baggage đã chọn vào logging context để log có thể hiển thị chúng.
- `spring.reactor.context-propagation: auto` bật chế độ tự động khôi phục context cho Reactor operators khi các accessor tương ứng đã được đăng ký.

Phiên bản Spring Boot và tracer bridge quyết định dependency/exporter cần dùng. Hãy dùng dependency management của Spring Boot để chọn starter Micrometer Tracing và exporter tương thích, không tự ghép các phiên bản Micrometer hoặc OpenTelemetry khác nhau.

Spring Boot có thể tự động propagate tracing qua các client được instrument như `WebClient.Builder` hoặc `RestClient.Builder` do Boot cấu hình. Không nên mặc định điều đó đồng nghĩa mọi lời gọi `RSocketRequester` đều tự mang W3C trace context. Với RSocket, hãy xác minh instrumentation đang dùng hoặc triển khai metadata propagation tường minh như phần tiếp theo.

## 6. Định nghĩa metadata carrier cho W3C

Để truyền W3C context qua Spring RSocket, tạo một kiểu metadata có schema rõ ràng. Ví dụ dùng JSON:

~~~java
public record TraceContextMetadata(
    Map<String, String> fields
) {}
~~~

Đặt MIME type riêng cho ứng dụng:

~~~java
public final class TraceMetadataTypes {

    public static final MimeType TRACE_CONTEXT =
        MimeType.valueOf("application/vnd.example.trace-context+json");

    private TraceMetadataTypes() {
    }
}
~~~

MIME type `application/vnd.example.trace-context+json` là ví dụ do ứng dụng định nghĩa, không phải well-known MIME type của RSocket. Client và server phải thống nhất cùng MIME type, schema JSON và giới hạn kích thước.

Không đổi MIME type mặc định của metadata sang MIME type tùy chỉnh này nếu vẫn cần routing metadata. Hãy giữ Composite Metadata để route và trace context được mã hóa thành hai entry độc lập.

## 7. Trích xuất trace context hiện tại và gửi từ requester

Micrometer `Propagator` có thể inject context vào một carrier bất kỳ. Map là carrier đơn giản để chuyển các field W3C thành JSON metadata:

~~~java
@Component
public class RSocketTraceMetadataFactory {

    private final Tracer tracer;
    private final Propagator propagator;

    public RSocketTraceMetadataFactory(
            Tracer tracer,
            Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

    public <T> Mono<T> withClientSpan(
            String operation,
            Function<TraceContextMetadata, Mono<T>> exchange) {

        return Mono.defer(() -> {
            Span clientSpan = tracer.nextSpan()
                .name(operation)
                .kind(Span.Kind.CLIENT)
                .start();

            Map<String, String> fields = new LinkedHashMap<>();
            propagator.inject(
                clientSpan.context(),
                fields,
                (carrier, key, value) -> carrier.put(key, value)
            );

            TraceContextMetadata metadata =
                new TraceContextMetadata(Map.copyOf(fields));

            return Mono.defer(() -> exchange.apply(metadata))
                .doOnError(clientSpan::error)
                .doFinally(signal -> clientSpan.end());
        });
    }
}
~~~

Factory tạo một client span mới cho từng interaction, dùng span hiện tại làm parent nếu context đã được khôi phục trong Reactor. Vì span được tạo bên trong `Mono.defer`, parent được đọc tại thời điểm subscription; cấu hình Context Propagation ở phần 10 giúp khôi phục context trong các Reactor callback. Nếu ứng dụng tắt context propagation hoặc thiếu accessor tương ứng, hãy kiểm tra parent span trong test để tránh vô tình tạo trace root mới. Propagator quyết định field nào cần inject theo propagation format đã cấu hình. Với W3C, các field có thể gồm `traceparent`, `tracestate` và baggage được bật/cho phép.

Gửi metadata trên từng request:

~~~java
Mono<OrderView> getOrder(
        RSocketRequester requester,
        RSocketTraceMetadataFactory traceMetadata,
        UUID orderId) {

    return traceMetadata.withClientSpan("orders.get", context -> {
        RSocketRequester.RequestSpec request = requester
            .route("orders.get")
            .data(new GetOrder(orderId));

        if (!context.fields().isEmpty()) {
            request = request.metadata(
                context,
                TraceMetadataTypes.TRACE_CONTEXT
            );
        }

        return request.retrieveMono(OrderView.class);
    });
}
~~~

Ví dụ giả định `RSocketStrategies` của requester đã có JSON encoder. Client span được tạo theo subscription, được inject vào metadata và kết thúc khi interaction complete, error hoặc cancel. Nếu không có span cha hiện tại, tracer tạo một trace mới.

Không lưu trace metadata hoặc span của request trước trong một field của singleton requester hoặc connection dùng chung, vì nhiều request đồng thời có thể thuộc các trace khác nhau. Với `Flux`, triển khai wrapper tương tự bằng `Flux.defer(...)`, `doOnError(...)` và `doFinally(...)`.

## 8. Đăng ký decoder metadata ở responder

Spring `MetadataExtractor` chuyển metadata serialized thành các cặp tên/giá trị có thể truy cập như header trong `@MessageMapping`. Cần đăng ký MIME type tùy chỉnh và kiểu Java tương ứng.

~~~java
@Configuration
public class RSocketMetadataConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders ->
                encoders.add(new Jackson2JsonEncoder()))
            .decoders(decoders ->
                decoders.add(new Jackson2JsonDecoder()))
            .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    TraceMetadataTypes.TRACE_CONTEXT,
                    TraceContextMetadata.class,
                    "traceContext"
                )
            )
            .build();
    }
}
~~~

Trong Spring Boot, có thể tùy chỉnh strategies đã auto-configure bằng cơ chế customizer phù hợp với phiên bản Boot đang dùng. Ví dụ trên minh họa đầy đủ encoder, decoder và metadata extractor trong một builder; nếu thay thế bean mặc định, hãy giữ lại các codec nghiệp vụ mà ứng dụng cần.

Sau khi đăng ký, handler có thể nhận metadata:

~~~java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;
    private final RemoteTraceSpanFactory spanFactory;

    public OrderRSocketController(
            OrderService orderService,
            RemoteTraceSpanFactory spanFactory) {
        this.orderService = orderService;
        this.spanFactory = spanFactory;
    }

    @MessageMapping("orders.get")
    Mono<OrderView> getOrder(
            GetOrder request,
            @Header(name = "traceContext", required = false)
            TraceContextMetadata metadata) {

        return spanFactory.withRemoteParent(
            "orders.get",
            metadata,
            () -> orderService.findById(request.orderId())
        );
    }
}
~~~

Ở đây `RemoteTraceSpanFactory` là adapter của ứng dụng chịu trách nhiệm extract parent context, tạo server span và quản lý lifecycle trong reactive pipeline. Phần sau giải thích những điểm cần chú ý khi triển khai adapter này; không nên để controller tự parse chuỗi `traceparent`.

## 9. Tạo server span từ metadata nhận được

Micrometer `Propagator.extract(...)` đọc carrier và trả về `Span.Builder` đã mang parent context nếu dữ liệu hợp lệ. Có thể tạo span mới từ builder:

~~~java
Span createServerSpan(
        TraceContextMetadata metadata,
        String operationName) {

    if (metadata == null || metadata.fields().isEmpty()) {
        return tracer.nextSpan()
            .name(operationName)
            .kind(Span.Kind.SERVER)
            .start();
    }

    Span.Builder parent = propagator.extract(
        metadata.fields(),
        (carrier, key) -> carrier.get(key)
    );

    return parent
        .name(operationName)
        .kind(Span.Kind.SERVER)
        .start();
}
~~~

Đây là phần tạo span từ remote parent. Với request có metadata hợp lệ, trace ID tiếp tục được giữ nguyên và server span có span ID mới. Nếu metadata thiếu hoặc không hợp lệ, propagator/tracer có thể tạo một trace mới hoặc context rỗng theo implementation.

Một reactive adapter cần đảm bảo:

1. Span được tạo khi subscription bắt đầu, tránh tạo span mỗi lần publisher được khai báo nhưng không được subscribe.
2. Span kết thúc khi publisher complete, error hoặc cancel.
3. Exception được gắn vào span trước khi kết thúc.
4. Current span/MDC được khôi phục đúng trong các callback reactive cần log.
5. Hai subscription đồng thời không dùng chung span hoặc baggage mutable.

Ví dụ phần lifecycle cơ bản:

~~~java
Mono<OrderView> withRemoteParent(
        String operation,
        TraceContextMetadata metadata,
        Supplier<Mono<OrderView>> action) {

    return Mono.defer(() -> {
        Span span = createServerSpan(metadata, operation);

        return Mono.defer(action)
            .doOnError(span::error)
            .doFinally(signal -> span.end());
    });
}
~~~

Đoạn này minh họa việc tạo span theo subscription, ghi nhận lỗi và luôn kết thúc span. Để các log bên trong pipeline nhìn thấy span hiện tại, adapter còn cần tích hợp với Observation/Reactor Context của ứng dụng. Không giữ `Tracer.SpanInScope` mở quanh lúc tạo publisher rồi đóng ngay sau khi trả `Mono`; các operator có thể chạy sau đó trên thread khác.

## 10. Giữ trace context qua Reactor và thread switch

Micrometer Tracing thường dùng `ThreadLocal` để cung cấp current span cho code imperative và logging MDC. Reactor có thể chuyển execution giữa nhiều thread, vì vậy `ThreadLocal` không tự động theo publisher qua mọi operator.

Spring Boot tích hợp Micrometer Context Propagation. Thuộc tính:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

cho phép tự động khôi phục các giá trị context có accessor tương ứng khi Reactor operators chạy. Với các executor tùy chỉnh hoặc `@Async`, cần cấu hình `ContextPropagatingTaskDecorator` hoặc cơ chế tương ứng để context không bị mất khi chuyển thread.

Một số nguyên tắc khi viết adapter:

- Dùng Reactor Context làm nguồn context trong reactive pipeline.
- Dùng Micrometer Context Propagation hoặc tracing instrumentation tương thích để khôi phục current span khi callback chạy.
- Scope ThreadLocal chỉ nên mở trong một đoạn callback đồng bộ và phải đóng ngay sau callback.
- Không chia sẻ `SpanInScope` qua nhiều thread hoặc giữ nó mở suốt vòng đời một Flux.
- Tạo child span theo từng interaction; không gán cùng một span object cho nhiều request đồng thời.

Ví dụ, nếu chỉ cần log trong một callback đồng bộ do ứng dụng kiểm soát, có thể mở scope tại chính callback:

~~~java
doOnNext(order -> {
    try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
        log.debug("Order loaded: {}", order.id());
    }
})
~~~

Scope chỉ áp dụng cho đoạn log đồng bộ đó. Nó không tự động đưa span vào mọi operator upstream hoặc downstream. Hãy kiểm thử log correlation sau `publishOn`, `subscribeOn` và các ranh giới executor.

## 11. Truyền correlation ID riêng qua metadata

Một ứng dụng có thể cần correlation ID theo hợp đồng riêng, ví dụ mã ticket từ HTTP caller hoặc ID của một luồng xử lý nghiệp vụ. Không bắt buộc correlation ID phải là trace ID.

Tạo metadata riêng:

~~~java
public record CorrelationMetadata(String correlationId) {}

public final class CorrelationMetadataTypes {
    public static final MimeType CORRELATION =
        MimeType.valueOf("application/vnd.example.correlation+json");

    private CorrelationMetadataTypes() {
    }
}
~~~

Gửi cả trace context và correlation metadata:

~~~java
RSocketRequester.RequestSpec request = requester
    .route("orders.get")
    .metadata(traceMetadata, TraceMetadataTypes.TRACE_CONTEXT)
    .metadata(
        new CorrelationMetadata(correlationId),
        CorrelationMetadataTypes.CORRELATION
    )
    .data(new GetOrder(orderId));

return request.retrieveMono(OrderView.class);
~~~

Hai metadata entry có MIME type riêng và cùng tồn tại trong Composite Metadata. Ở responder, đăng ký cả hai kiểu với `MetadataExtractor` rồi đọc bằng `@Header` tương ứng.

Nếu correlation ID được sinh ở gateway, hãy kiểm tra format và giới hạn độ dài. Không dùng giá trị caller gửi trực tiếp làm metric tag vì số lượng giá trị có thể không giới hạn. Nếu correlation ID không tồn tại, gateway có thể tạo UUID hoặc dùng ID nghiệp vụ đã được xác thực theo quy tắc của hệ thống.

## 12. Baggage: truyền ngữ cảnh nghiệp vụ có kiểm soát

Baggage là các field đi cùng trace để dịch vụ phía sau có thêm ngữ cảnh. Ví dụ:

- Tenant tier: `standard` hoặc `premium`.
- Region: `ap-southeast`.
- Business channel: `mobile` hoặc `partner`.

Baggage có thể được tạo bằng Micrometer `Tracer` và propagate nếu W3C propagation cùng các field remote được cấu hình. Ví dụ:

~~~java
try (BaggageInScope baggage =
        tracer.createBaggageInScope("tenant-tier", "premium")) {
    return orderService.process(command);
}
~~~

Trong reactive code, không giả định scope imperative ở ví dụ trên tồn tại qua mọi thread switch. Hãy dùng Reactor Context/Context Propagation để khôi phục context tại thời điểm xử lý.

Cấu hình allowlist baggage:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
        - business-region
      correlation:
        fields:
          - tenant-tier
~~~

Chỉ truyền field thật sự cần ở dịch vụ downstream. Không đưa mật khẩu, access token, email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân vào baggage. Baggage có thể đi qua nhiều dịch vụ và xuất hiện trong log hoặc trace backend.

Không dùng `tracestate` để lưu các thuộc tính nghiệp vụ tùy ý. Theo W3C, `tracestate` dành cho thông tin mở rộng của tracing vendor; baggage phù hợp hơn cho các thuộc tính ứng dụng được cho phép propagate.

## 13. Correlation ID trong log

Spring Boot kết hợp Micrometer Tracing có thể thêm `traceId` và `spanId` vào MDC. Log có thể chứa cả hai để truy vấn:

~~~text
2026-11-22T10:15:31.120Z INFO
[traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7]
OrderService - Loading order 42
~~~

Nếu ứng dụng dùng correlation ID riêng, thêm field đó vào log pattern hoặc MDC bằng một accessor có vòng đời rõ ràng. Luôn xóa/khôi phục giá trị khi scope kết thúc để request sau trên cùng thread không nhận nhầm context.

Một log event hữu ích thường có:

| Field | Dùng để |
| --- | --- |
| service.name | Xác định dịch vụ phát log. |
| traceId | Tìm toàn bộ trace. |
| spanId | Tìm một thao tác cụ thể. |
| correlationId | Tìm theo hợp đồng ứng dụng hoặc ticket. |
| route | Biết interaction RSocket nào được gọi. |
| interactionModel | Phân biệt request-response, stream, channel hoặc FNF. |
| outcome | Thành công, lỗi, timeout hoặc cancellation. |

Không ghi nguyên payload hoặc toàn bộ metadata nếu có thể chứa thông tin nhạy cảm.

## 14. Sampling và cardinality

Tracing tạo dữ liệu nhiều hơn metrics. Sampling giúp kiểm soát chi phí lưu trữ và export:

- Dùng sampling probability cao trong môi trường local/test để dễ kiểm tra propagation.
- Dùng sampling phù hợp lưu lượng production và chính sách quan sát của tổ chức.
- Tôn trọng trace flags nhưng không để caller bên ngoài tùy ý buộc hệ thống phải ghi mọi trace.
- Với lỗi nghiêm trọng, có thể dùng tail-based sampling ở collector nếu kiến trúc hỗ trợ.

Không thêm trace ID, span ID, correlation ID hoặc user ID làm label metric. Các giá trị này có cardinality cao, khiến time-series tăng nhanh. Hãy để chúng ở log và trace; metric nên dùng tag có tập giá trị nhỏ như route template, interaction model, status hoặc service name.

## 15. Bảo mật và giới hạn metadata

Trace context giúp liên kết yêu cầu nhưng cũng có thể bị lạm dụng hoặc làm lộ thông tin:

- Xác thực cú pháp traceparent, giới hạn độ dài metadata và từ chối payload quá lớn.
- Không tin trace ID hoặc correlation ID như danh tính người dùng.
- Không dùng baggage để truyền credential hoặc dữ liệu cá nhân.
- Chỉ cho phép các baggage field trong allowlist.
- Không phản chiếu toàn bộ metadata nhận được vào log hoặc HTTP response.
- Áp dụng sampling policy tại service tin cậy, đặc biệt ở ranh giới public ingress.
- Dùng TLS cho RSocket TCP và WSS cho WebSocket khi dữ liệu đi qua mạng không tin cậy.
- Xem xét xóa hoặc restart trace context tại trust boundary nếu cần tránh liên kết trace từ bên ngoài vào hệ thống nội bộ.

Trace context không phải bí mật và không nên chứa dữ liệu nhạy cảm. `tracestate` cũng có thể mang thông tin vendor; hãy giới hạn những gì được phép propagate ra ngoài.

## 16. Kiểm thử trace propagation qua RSocket

Kiểm thử cần xác nhận trace ID được giữ nguyên, span ID được tạo mới và metadata của hai request đồng thời không bị trộn:

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Có parent span | Tạo span ở requester rồi gọi route RSocket | Metadata chứa traceparent hợp lệ. |
| Server nhận metadata | Gửi request có TraceContextMetadata | Extractor tạo header `traceContext` đúng kiểu. |
| Parent-child relation | Responder tạo server span từ metadata | Trace ID giữ nguyên; span ID mới và parent là span phía gọi. |
| Không có current span | Gọi RSocket từ tác vụ không có tracing context | Request không mang metadata rỗng; responder tạo trace mới hoặc xử lý theo policy. |
| Metadata không hợp lệ | Gửi traceparent sai độ dài hoặc ID toàn số 0 | Propagator bỏ qua context không hợp lệ; không làm request nghiệp vụ crash ngoài policy. |
| Hai request đồng thời | Gửi hai interaction thuộc hai trace khác nhau trên cùng connection | Metadata và span không bị trộn giữa hai request. |
| Thread switch | Dùng `publishOn` hoặc executor | Log/span context được khôi phục đúng nếu context propagation đã cấu hình. |
| Baggage allowlist | Gửi field được phép và field không được phép | Chỉ field đã cấu hình được propagate. |
| Sampling | Chạy với probability thấp/cao | Trace được export theo chính sách sampler, không làm thay đổi route hoặc payload nghiệp vụ. |
| Correlation ID riêng | Gửi hai correlation ID khác nhau | Log của mỗi interaction giữ đúng correlation ID. |

Có thể dùng Micrometer test tracer hoặc exporter in-memory để kiểm tra span và quan hệ parent. Với integration test RSocket, dùng client/server thật để xác nhận metadata qua encoder, Composite Metadata, MetadataExtractor và handler.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Trace dừng ở requester | Không gửi trace metadata hoặc instrumentation không hỗ trợ RSocket. | Kiểm tra request metadata và cấu hình Propagator. |
| Server tạo trace mới thay vì child span | Extractor không nhận được traceparent hoặc metadata MIME type sai. | Kiểm tra Composite Metadata, decoder và tên header. |
| Route không được gọi sau khi thêm trace metadata | Builder đã đổi metadata MIME type khỏi Composite Metadata. | Giữ MIME type Composite Metadata mặc định. |
| Log không có traceId sau publishOn | ThreadLocal không được khôi phục trong reactive callback. | Cấu hình Context Propagation và kiểm thử accessor. |
| Trace của request A xuất hiện ở request B | Lưu metadata/span trong field dùng chung hoặc mutable singleton. | Tạo carrier/span theo từng subscription/request. |
| Baggage không tới dịch vụ đích | Field chưa nằm trong remote-fields hoặc propagation format không tương thích. | Cấu hình allowlist và kiểm tra Propagator.fields(). |
| Trace ID xuất hiện trong metric label | Dùng high-cardinality identifier làm tag. | Chuyển sang log/trace và giữ metric tag có cardinality thấp. |
| Tracing extension không tương thích W3C | Gửi traceparent trong MIME type Zipkin B3. | Dùng đúng B3 codec hoặc MIME type tùy chỉnh cho W3C. |

## 18. Checklist triển khai

- [ ] Chọn một propagation format thống nhất, ví dụ W3C hoặc B3.
- [ ] Phân biệt correlation ID, trace ID, span ID và baggage.
- [ ] Giữ Composite Metadata để route và tracing entry cùng tồn tại.
- [ ] Truyền trace context theo từng interaction, không dùng SETUP làm parent cho mọi request.
- [ ] Nếu dùng W3C qua Spring RSocket, đăng ký MIME type và decoder tùy chỉnh.
- [ ] Dùng Micrometer Propagator để inject/extract thay vì tự parse traceparent.
- [ ] Tạo span mới ở responder và giữ parent context đúng.
- [ ] Kết thúc span khi complete, error hoặc cancel.
- [ ] Cấu hình Reactor Context Propagation cho callback chạy qua nhiều thread.
- [ ] Chỉ propagate baggage đã allowlist và không chứa dữ liệu nhạy cảm.
- [ ] Không dùng trace ID hoặc correlation ID làm metric label.
- [ ] Kiểm thử request đồng thời, thread switch, invalid metadata và sampling.

## 19. Ghi nhớ

- Correlation ID phục vụ tìm log theo hợp đồng ứng dụng; trace ID và span ID phục vụ distributed tracing.
- W3C Trace Context dùng `traceparent` và `tracestate`; baggage mang các thuộc tính ứng dụng được phép propagate.
- RSocket Composite Metadata cho phép route, authentication, tracing và metadata ứng dụng cùng tồn tại.
- RSocket có tracing metadata extension tương thích Zipkin B3; định dạng này khác W3C Trace Context.
- Với W3C qua Spring RSocket, cần metadata MIME type và decoder được cấu hình rõ ràng nếu không có instrumentation chuyên biệt.
- Truyền trace context ở metadata của từng interaction; connection dùng chung có thể phục vụ nhiều trace song song.
- Dùng Micrometer `Propagator` để inject/extract carrier và tạo server span từ parent context.
- Reactor Context Propagation giúp khôi phục context qua thread switch; không giữ ThreadLocal scope qua toàn bộ publisher.
- Baggage cần allowlist, giới hạn kích thước và không chứa credential hoặc dữ liệu cá nhân.
- Để trace ID và span ID trong log/trace, không đưa chúng vào metric label có cardinality cao.

## Tài liệu tham khảo

- [W3C — Trace Context Recommendation](https://www.w3.org/TR/trace-context/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability và Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework — RSocket và Composite Metadata](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Micrometer Tracing — Propagator API](https://docs.micrometer.io/tracing/reference/api.html)
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [RSocket Java — TracingMetadataCodec API](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/metadata/TracingMetadataCodec.html)
- [RSocket — Protocol Extensions](https://github.com/rsocket/rsocket)
