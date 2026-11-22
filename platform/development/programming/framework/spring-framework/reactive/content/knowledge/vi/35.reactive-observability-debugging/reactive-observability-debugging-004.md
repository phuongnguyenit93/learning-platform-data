# Mã tương quan, Reactor Context và tích hợp MDC trong Spring WebFlux

## 1. Mục tiêu và vấn đề cần giải quyết

Một ứng dụng WebFlux thường xử lý nhiều request đồng thời bằng ít thread. Một request có thể bắt đầu trên Netty event-loop, tiếp tục qua **flatMap**, chuyển sang Scheduler khác bằng **publishOn**, gọi WebClient hoặc database reactive rồi quay về ghi HTTP response. Khi phân tích log, các dòng thuộc cùng một request có thể xuất hiện xen giữa log của hàng trăm request khác.

**Correlation ID** (mã tương quan) giúp gắn các log và sự kiện của cùng một thao tác logic. **Reactor Context** giúp mang metadata qua pipeline reactive theo subscription. **MDC (Mapped Diagnostic Context)** giúp đưa metadata vào dòng log thông qua SLF4J/Logback. Ba khái niệm liên quan nhưng **không phải cùng một cơ chế**.

Bài học trình bày:

1. Vì sao ThreadLocal MDC không tự đi theo WebFlux.
2. Context và ContextView gắn với subscriber/subscription như thế nào.
3. contextWrite, deferContextual, transformDeferredContextual và phạm vi nhìn thấy key.
4. Cách sinh/nhận/kiểm tra X-Correlation-ID bằng WebFilter.
5. Tích hợp MDC thủ công bằng scope có finally để không rò dữ liệu qua thread.
6. Micrometer Context Propagation, ThreadLocalAccessor, ContextRegistry và automatic mode.
7. Spring Boot Observability/Micrometer Tracing, traceId, spanId và W3C traceparent.
8. Truyền mã tương quan sang WebClient, message broker và ranh giới bất đồng bộ.
9. Ví dụ Java 17, Spring Boot 4.1.2, WebFlux, logging và WebTestClient.
10. Kiểm thử nhiều request đồng thời, lỗi, timeout, cancellation và context loss.

## 2. Correlation ID là gì?

Correlation ID là một chuỗi định danh một **request hoặc thao tác logic** để người vận hành gom các log có liên quan.

Ví dụ một request qua ba service:

~~~text
Client
  |
  | GET /checkout
  | X-Correlation-ID: req-8f42
  v
API Gateway
  | log: correlationId=req-8f42
  v
Order Service
  | log: correlationId=req-8f42
  v
Inventory Service
    log: correlationId=req-8f42
~~~

Khi tìm correlationId=req-8f42 trong hệ thống lưu log tập trung, kỹ sư có thể xem toàn bộ các sự kiện được gắn cùng định danh.

### 2.1. Những nơi nên xuất hiện mã tương quan

- Request header khi có contract sử dụng X-Correlation-ID.
- Response header để phía gọi gửi mã đó khi báo lỗi.
- Reactor Context của pipeline server.
- Log event hoặc MDC khi thực hiện ghi log.
- Header của downstream HTTP call nếu hợp đồng liên service yêu cầu.
- Metadata của message event, job hoặc callback nếu cần theo dõi xuyên thời gian.
- Error response hoặc diagnostic metadata khi phù hợp chính sách bảo mật.

Header **X-Correlation-ID** phổ biến nhưng không phải một cơ chế distributed tracing được chuẩn hóa thống nhất giữa mọi hệ thống. Cần định nghĩa rõ phạm vi và cách quản lý nó trong API contract.

### 2.2. Một mã dùng cho request hay thao tác nghiệp vụ?

Nếu một người dùng thao tác thanh toán qua nhiều request, có thể cần:

- **requestId** riêng cho từng HTTP request;
- **correlationId** chung cho một workflow;
- **traceId** do tracing system sinh để liên kết spans;
- **business operation ID** bền vững (ví dụ orderId) cho nghiệp vụ.

Đừng dùng lại một loại định danh cho mọi mục đích mà không xem xét cardinality, quyền truy cập, khả năng tái sử dụng và vòng đời.

## 3. Vì sao MDC thông thường dễ bị mất trong Reactor?

MDC của các logging framework Java phổ biến thường dựa trên **ThreadLocal**. Trong servlet stack truyền thống, một request thường được xử lý trên một request thread trong phần lớn vòng đời đồng bộ.

Trong WebFlux:

~~~text
Request A -> reactor-http-nio-1
Request B -> reactor-http-nio-1
Request A -> parallel-2
Request C -> reactor-http-nio-1
Request A -> boundedElastic-3
~~~

Một thread có thể phục vụ nhiều request ở các thời điểm khác nhau, còn một request có thể chuyển qua nhiều thread.

Nếu code dùng:

~~~java
MDC.put("correlationId", "req-A");

return Mono.delay(Duration.ofMillis(20))
    .doOnNext(value -> log.info("processed"));
~~~

dòng log bên trong doOnNext có thể chạy trên thread khác, không thấy giá trị đã set ở thread ban đầu. Tệ hơn, nếu không xóa MDC, giá trị của request A có thể xuất hiện trong log của request B trên thread được tái sử dụng.

**Không bao giờ coi ThreadLocal hoặc MDC là nguồn dữ liệu tương quan đáng tin cậy trong reactive pipeline nếu chưa có cơ chế context propagation.**

### 3.1. Reactor Context giải quyết điều gì?

Reactor Context là tập key-value gắn với **Subscriber** và đi theo subscription. Nó không dựa vào việc các toán tử luôn chạy trên cùng thread.

~~~text
Subscription A
  Context {correlationId=req-A}
  -> map -> publishOn -> flatMap -> WebClient

Subscription B
  Context {correlationId=req-B}
  -> map -> publishOn -> flatMap -> database
~~~

Nhờ vậy, A và B có thể cùng chạy trên một thread nhưng mỗi subscription vẫn giữ đúng thông tin của mình. Đó là cơ sở để mang correlation ID trong Reactor.

## 4. Context và ContextView

Reactor có:

- **reactor.util.context.Context**: API bất biến có thao tác tạo giá trị mới như put, delete, putAll.
- **reactor.util.context.ContextView**: giao diện chỉ đọc qua get, getOrDefault, getOrEmpty, hasKey.

Một Context là cấu trúc key-value có key/value kiểu Object. Nên chọn một key ổn định, tránh xung đột với các thư viện khác.

Ví dụ:

~~~java
public final class CorrelationId {
    public static final String KEY =
        "demo.correlationId";

    private CorrelationId() {}
}
~~~

Dùng cùng key khi ghi và đọc. Với ứng dụng lớn, có thể dùng một object key chuyên biệt hoặc constant namespace rõ ràng thay vì chuỗi ngắn như "id".

### 4.1. Ghi Context bằng contextWrite

~~~java
Mono<String> pipeline =
    Mono.deferContextual(view ->
        Mono.just(view.get(CorrelationId.KEY))
    )
    .contextWrite(ctx ->
        ctx.put(CorrelationId.KEY, "req-123")
    );
~~~

Ở đây contextWrite tạo **Context mới** với key tương quan, không sửa một biến toàn cục.

### 4.2. Đọc Context bằng deferContextual

~~~java
Mono<String> currentId = Mono.deferContextual(view -> {
    String value = view.getOrDefault(
        CorrelationId.KEY,
        "missing"
    );
    return Mono.just(value);
});
~~~

deferContextual lấy ContextView **khi subscribe**. Nó phù hợp cho source Mono/Flux cần xem metadata của subscriber.

### 4.3. Context không phải Map mutable

~~~java
Context c1 = Context.of("cid", "A");
Context c2 = c1.put("cid", "B");
~~~

c1 vẫn chứa A; c2 là Context mới chứa B. Không dựa vào việc ghi tại một nhánh để thay đổi Context đang được người khác giữ.

### 4.4. contextWrite truyền từ downstream về upstream

Điểm dễ nhầm là data signal đi từ publisher đến subscriber, nhưng Context được đưa vào từ phía subscriber và được nhìn thấy bởi các operator **upstream** của contextWrite.

Ví dụ:

~~~java
Mono<String> value =
    Mono.deferContextual(view ->
        Mono.just(view.get("cid"))
    )
    .contextWrite(ctx -> ctx.put("cid", "req-456"));
~~~

Nguồn deferContextual nằm upstream của contextWrite nên đọc được req-456.

Nếu đặt contextWrite ở một nhánh không nằm downstream của operator cần đọc, key sẽ không xuất hiện ở đó. Cần kiểm tra vị trí trong chain, không chỉ tìm xem toàn file có gọi contextWrite hay chưa.

### 4.5. transformDeferredContextual

Khi một operator ở giữa cần xem ContextView và biến đổi pipeline:

~~~java
Flux<String> enriched = source
    .transformDeferredContextual(
        (flux, view) -> flux.map(value ->
            view.getOrDefault("cid", "missing")
                + ":" + value
        )
    );
~~~

Đây là snippet minh họa: source là Flux<String> của ứng dụng. transformDeferredContextual cho phép phép biến đổi nhận ContextView của mỗi subscription.

### 4.6. Không tự subscribe giữa chain

Sai:

~~~java
Mono.deferContextual(ctx -> {
    auditService.logAsync(ctx.get("cid")).subscribe();
    return nextStep();
});
~~~

Một subscribe() riêng có lifecycle khác, có thể làm mất Reactor Context, tách error/cancel và trở thành side effect không được await.

Đúng hơn là composition:

~~~java
Mono.deferContextual(ctx ->
    auditService.logAsync(ctx.get("cid"))
        .then(nextStep())
);
~~~

Đây là snippet yêu cầu auditService và nextStep phù hợp. Khi đó subscription chính điều phối cả logging và bước tiếp theo.

## 5. Mã tương quan tại ranh giới HTTP

Một WebFlux **WebFilter** có thể:

1. Đọc header X-Correlation-ID từ request.
2. Kiểm tra chính sách trust, định dạng và kích thước.
3. Giữ mã hợp lệ hoặc tạo mã mới.
4. Gắn mã vào response header.
5. Ghi mã vào Reactor Context bằng contextWrite cho downstream pipeline.

Sơ đồ:

~~~text
Request
  |
  v
WebFilter đọc X-Correlation-ID
  |
  +-- hợp lệ --> reuse ID theo chính sách trust
  |
  +-- thiếu/sai --> tạo UUID mới
  |
  v
Response header X-Correlation-ID
  |
  v
chain.filter(exchange)
  |
  v
contextWrite(correlationId)
  |
  v
Controller -> Service -> Reactor operators
~~~

### 5.1. Không tin header tùy ý

Một client bên ngoài có thể tự gửi bất kỳ chuỗi nào. Không ghi nguyên văn giá trị dài hàng megabyte, có CR/LF, token, URL chứa secrets hoặc ký tự điều khiển vào log.

Một chính sách khởi đầu:

- Chỉ chấp nhận ký tự chữ/số ASCII, dấu chấm, gạch dưới và gạch ngang.
- Giới hạn 64 ký tự.
- Khi thiếu hoặc không hợp lệ, tạo UUID mới.
- Không dùng correlation ID làm bằng chứng xác thực hay phân quyền.
- Giải quyết duplicate headers và trust boundary tại gateway.
- Nếu cần ID do hệ thống tự sinh tuyệt đối, luôn sinh mới và chỉ ghi incoming ID vào metadata đã được sanitize.

### 5.2. Trả mã trong response

Response header cho phép người dùng gửi correlation ID cho đội hỗ trợ để tìm log, đặc biệt với lỗi 4xx/5xx. Không cần đưa stack trace hoặc thông tin nội bộ vào error response.

Nếu muốn client JavaScript đọc custom response header trong request CORS, server có thể phải cấu hình Access-Control-Expose-Headers theo chính sách CORS.

### 5.3. WebFilter không nên block

Không gọi database blocking, Thread.sleep hoặc block() để tìm correlation ID. Tạo UUID và regex check là thao tác nhẹ. Nếu cần tra cứu session/identity bất đồng bộ, compose một Mono vào WebFilter chain thay vì chặn event-loop.

## 6. Ghi log có MDC theo phạm vi ngắn

MDC là lớp tiện ích để logging pattern lấy các biến như correlationId, traceId và spanId.

Ví dụ cấu hình Logback pattern:

~~~properties
logging.pattern.level=%5p [cid:%X{correlationId:-}]
~~~

Nếu MDC đã chứa correlationId khi log.info được thực hiện, dòng log có thể trông như:

~~~text
INFO [cid:req-123] processed record
~~~

Nếu chưa có key, phần fallback giúp log hiển thị một giá trị rỗng hoặc dấu gạch tùy cấu hình.

### 6.1. Scope thủ công

Khi đang ở trong một callback có ContextView, có thể tạm gắn MDC:

~~~java
Mono.deferContextual(view -> {
    String cid = view.get(CorrelationId.KEY);

    String previous = MDC.get("correlationId");
    try {
        MDC.put("correlationId", cid);
        log.info("handling request");
    }
    finally {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }

    return Mono.just(cid);
});
~~~

Cách này không giả định ThreadLocal tự đi qua Scheduler. Nó **khôi phục giá trị MDC trước đó** sau lời gọi log trên đúng thread.

MDC.putCloseable cũng có thể giúp xóa key khi đóng scope:

~~~java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlationId", cid)) {
    log.info("handling request");
}
~~~

Tuy nhiên, MDC.putCloseable thường loại bỏ key khi close; nếu thread trước đó đã có cùng key, đừng tự giả định nó tự khôi phục giá trị cũ. Dùng helper lưu/restore nếu cần bảo toàn state.

### 6.2. doOnEach để log theo Signal

Reactor FAQ khuyến nghị một pattern dùng doOnEach kết hợp ContextView trong tín hiệu:

~~~java
Flux<Event> logged = events
    .doOnEach(signal -> {
        if (!signal.isOnNext()) {
            return;
        }

        String cid = signal.getContextView()
            .getOrDefault(
                CorrelationId.KEY,
                "missing"
            );

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", cid)) {
            log.debug("event={}", signal.get());
        }
    });
~~~

Đây là snippet cần Event, events và logger của ứng dụng. Hook đọc ContextView từ Signal thay vì đọc ThreadLocal một cách mù quáng. Scope chỉ mở trong callback log, không nên giữ MDC xuyên một Publisher bất đồng bộ.

### 6.3. doFinally không có ContextView trực tiếp

doFinally nhận SignalType, không nhận Signal chứa ContextView. Nếu cần log correlation ID lúc cancel/error/complete, capture ID bên trong deferContextual rồi truyền vào doFinally:

~~~java
Mono.deferContextual(view -> {
    String cid = view.get(CorrelationId.KEY);

    return process()
        .doFinally(signal ->
            ScopedMdc.run(cid, () ->
                log.info("finished: {}", signal)
            )
        );
});
~~~

Đây là snippet yêu cầu process(), ScopedMdc và logger. Không cố gọi Reactor Context bằng ThreadLocal từ doFinally mà thiếu bridge.

## 7. Tích hợp tự động bằng Micrometer Context Propagation

Micrometer Context Propagation là thư viện nối các cơ chế context khác nhau, chẳng hạn:

- Reactor Context / ContextView.
- ThreadLocal của thư viện imperative.
- MDC hoặc tracing context nếu có ThreadLocalAccessor phù hợp.
- Các task chạy trên Executor khác khi được capture/restore đúng cách.

Các API chính:

| Thành phần | Vai trò |
| --- | --- |
| ThreadLocalAccessor | Đọc/ghi/xóa một ThreadLocal value |
| ContextAccessor | Truy cập một context có cấu trúc key-value |
| ContextRegistry | Lưu registry các accessor |
| ContextSnapshot | Snapshot một tập contextual values |
| ContextSnapshot.Scope | Tạm restore context vào ThreadLocal |
| contextCapture() | Capture những ThreadLocal đã được đăng ký vào Reactor Context |
| Hooks.enableAutomaticContextPropagation() | Bật automatic propagation mode cho subscriptions mới |

**ReactorContextAccessor** do Reactor cung cấp và được nạp qua ServiceLoader khi dependency Micrometer Context Propagation xuất hiện. Không cần viết ReactorContextAccessor tùy biến chỉ để sử dụng Reactor Context.

### 7.1. Chế độ limited và automatic

Theo tài liệu Reactor 3.8 và Spring Boot 4.1:

- **Limited**: propagation tới ThreadLocal có hỗ trợ ở các operator/điểm thích hợp như handle và tap. Không được kỳ vọng mọi operator callback đều tự khôi phục ThreadLocal.
- **Automatic**: Reactor cố gắng restore ThreadLocal cho những accessor đã đăng ký qua nhiều ranh giới operator/Scheduler hơn. Cần bật hook lúc khởi động trước các subscriptions mới.
- Automatic mode không biến mọi thư viện ngoài Reactor thành reactive hoặc tự bao phủ arbitrary raw Thread, CompletableFuture và executor không instrument.

Spring Boot cung cấp property:

~~~properties
spring.reactor.context-propagation=auto
~~~

Giá trị mặc định thường là limited. Bật auto khi ứng dụng có dependency context-propagation phù hợp và đã kiểm tra tác động performance/correctness.

### 7.2. Đăng ký MDC ThreadLocalAccessor

Để bridge một key trong Reactor Context sang MDC, có thể đăng ký accessor:

~~~java
ContextRegistry.getInstance()
    .registerThreadLocalAccessor(
        CorrelationId.KEY,
        () -> MDC.get("correlationId"),
        (String value) ->
            MDC.put("correlationId", value),
        () -> MDC.remove("correlationId")
    );
~~~

Cần dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Khi dùng Spring Boot parent/BOM phù hợp, không cần hardcode version riêng.

Sau khi đăng ký accessor và bật auto, Reactor có thể phục hồi MDC correlationId khi đang thực thi operator callback với Context tương ứng:

~~~java
Mono.deferContextual(view -> {
    log.info("MDC can be restored here with auto mode");
    return Mono.just(view.get(CorrelationId.KEY));
});
~~~

Không đảm bảo đoạn log trên thấy CID nếu thiếu dependency, thiếu accessor, key context không khớp, hook chưa bật, subscription đã tạo trước khi bật hook hoặc code thực thi ngoài Reactor.

### 7.3. Registration và cleanup

Đăng ký accessor **một lần khi application khởi động**, không đăng ký trong mỗi request. Không để nhiều bean cùng register key trùng với nhau một cách vô tình.

Automatic propagation phải đảm bảo xóa ThreadLocal khi Context không có key tương ứng để tránh rò giá trị của request trước trên thread đang được tái sử dụng. Accessor phải có reset/remove đúng.

Nếu ứng dụng đã được instrumentation bởi Micrometer Tracing, **không tự đăng ký thêm accessor trùng key traceId/spanId**; để thư viện tracing quản lý context mà nó sở hữu.

### 7.4. contextCapture khác contextWrite

- **contextWrite**: viết giá trị trực tiếp vào Reactor Context, không cần lấy từ ThreadLocal.
- **contextCapture**: lấy các ThreadLocal đã đăng ký tại thời điểm thích hợp (thường lúc subscribe), đưa vào Reactor Context.
- **ContextSnapshot.captureAll**: capture các giá trị theo registry ở một phạm vi cụ thể.
- **ContextSnapshot.Scope**: restore giá trị trong một scope imperative rồi dọn khi scope kết thúc.

Đối với WebFlux request mới, ưu tiên tạo/sanitize ID trong WebFilter rồi **contextWrite**. Không cần đi vòng qua MDC -> contextCapture nếu đã có chính ID tại HTTP boundary.

### 7.5. @Async và Executor

Khi chuyển từ Reactor sang @Async hoặc arbitrary Executor, Reactor Context có thể không tự truyền qua cơ chế không thuộc Reactor.

Spring Boot 4.1 hỗ trợ:

~~~properties
spring.task.execution.propagate-context=true
~~~

cho auto-configured AsyncTaskExecutor ở trường hợp phù hợp; với executor tự cấu hình, có thể dùng ContextPropagatingTaskDecorator.

Đừng dùng thread inheritance hay static ThreadLocal để thay cơ chế capture/restore. Với job background hoàn toàn tách request, nên tạo một context riêng, không kéo dài vô hạn context của HTTP subscription đã kết thúc.

## 8. Correlation ID, request ID và distributed tracing

Ba khái niệm thường bị trộn:

| Thuộc tính | Correlation ID | Trace ID | Span ID |
| --- | --- | --- | --- |
| Mục đích | Gom log của thao tác | Định danh một distributed trace | Định danh một đơn vị công việc trong trace |
| Nguồn sinh | Gateway hoặc ứng dụng | Tracing SDK/propagator | Tracing SDK cho từng span |
| Tính chuẩn hóa | Theo contract, X-Correlation-ID không chuẩn thống nhất | W3C Trace Context hỗ trợ trace-id | W3C Trace Context hỗ trợ parent-id/span |
| Phạm vi | Request/workflow tùy thiết kế | Hành trình distributed trace | Một span cụ thể |
| Propagation | Header tự định nghĩa | traceparent/tracestate | Thông qua tracing context |

**traceparent** là header của chuẩn W3C Trace Context. Không thay thế traceparent bằng X-Correlation-ID hoặc tự ghép traceId từ UUID tùy ý nếu đã dùng tracing SDK.

### 8.1. Micrometer Tracing trong Spring Boot

Khi cấu hình Micrometer Tracing, Spring Boot có thể đưa traceId và spanId vào MDC và thêm phần correlation theo pattern logging. Ví dụ:

~~~text
[803B448A0489F84084905D3093480352-3425F23BB2432450]
~~~

Đó là dạng minh họa từ traceId/spanId, không nhất thiết giống giá trị X-Correlation-ID tùy biến của ứng dụng.

Nếu tracing có sẵn và đủ đáp ứng nhu cầu tìm log, **ưu tiên traceId/spanId do framework quản lý** thay vì xây một hệ truyền ID song song khó bảo trì.

### 8.2. Dependency tracing

Spring Boot 4.1 có hỗ trợ Micrometer Tracing và OpenTelemetry. Tùy exporter, có thể sử dụng starter OpenTelemetry phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Cần cấu hình exporter/collector, sampling và privacy phù hợp môi trường thực tế. Chỉ thêm starter không có nghĩa đã cấu hình một collector có thể nhận spans.

### 8.3. Auto-configured WebClient.Builder

Khi có tracing, nên inject WebClient.Builder do Spring Boot quản lý:

~~~java
@Bean
WebClient downstreamWebClient(
    WebClient.Builder builder
) {
    return builder
        .baseUrl("https://inventory.example")
        .build();
}
~~~

Spring Boot khuyến nghị sử dụng auto-configured WebClient.Builder để tracing propagation interceptor/customizer được áp dụng. Nếu tạo WebClient bằng WebClient.create() trong một vị trí tùy ý, customizer propagation có thể bị bỏ qua.

### 8.4. Cardinality: đừng gắn correlationId vào metric tag

Correlation ID có số giá trị rất lớn. Không thêm nó làm Prometheus label hoặc **low-cardinality metric tag** vì tạo vô số time series.

Định danh chi tiết nên xuất hiện trong log, span attributes với chính sách dữ liệu phù hợp hoặc high-cardinality metadata, không phải dimensions của mọi metric.

## 9. Truyền X-Correlation-ID xuống WebClient

Nếu API downstream yêu cầu cùng correlation header, có thể tạo một ExchangeFilterFunction cho WebClient.

~~~java
@Bean
WebClient inventoryWebClient(
    WebClient.Builder builder
) {
    return builder
        .baseUrl("https://inventory.example")
        .filter((request, next) ->
            Mono.deferContextual(view -> {
                String cid = view.getOrDefault(
                    CorrelationId.KEY,
                    "unavailable"
                );

                ClientRequest outgoing =
                    ClientRequest.from(request)
                        .headers(headers ->
                            headers.set(
                                "X-Correlation-ID",
                                cid
                            )
                        )
                        .build();

                return next.exchange(outgoing);
            })
        )
        .build();
}
~~~

Imports tiêu biểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
~~~

Đây là snippet độc lập về propagation, không thuộc dự án demo chạy ở phần 12.

Những điều cần hiểu:

- Đây là **client-side filter** của WebClient, khác với **WebFilter** nhận inbound request.
- Mono.deferContextual đọc context tại subscription của **outbound request**.
- Không đọc MDC trực tiếp ở interceptor nếu chưa bảo đảm propagation.
- Nếu context thiếu CID, chính sách production cần rõ ràng: tạo ID mới, bỏ header hoặc lỗi. Không dùng giá trị "unavailable" trong hệ thống thực như một ID chung.
- Tracing framework có thể tự truyền traceparent nhưng không mặc nhiên truyền custom X-Correlation-ID; cần filter riêng hoặc baggage propagation theo contract.

### 9.1. Không tự subscribe trong WebFilter hoặc WebClient filter

Nếu gọi downstream bằng một subscribe() riêng rồi return Mono.empty(), context và cancellation có thể không đi cùng pipeline chính. Hãy return Mono<ClientResponse>, Mono<Response> hoặc Flux tương ứng, để Reactor điều phối.

### 9.2. Baggage và tracing

Nếu muốn một metadata nghiệp vụ đi qua distributed tracing, có thể cân nhắc baggage theo chuẩn và thư viện tracing đang sử dụng. Tuy nhiên, baggage có thể được gửi qua network, nên không đưa token, PII, secrets hoặc payload nhạy cảm vào đó.

## 10. Logging khi xảy ra lỗi, retry và cancel

### 10.1. doOnError

~~~java
Mono.deferContextual(view -> {
    String cid = view.getOrDefault(
        CorrelationId.KEY,
        "missing"
    );

    return repositoryCall()
        .doOnError(error ->
            ScopedMdc.run(cid, () ->
                log.error("repository failed", error)
            )
        );
});
~~~

Đây là snippet cần repositoryCall(), ScopedMdc và logger của ứng dụng.

Đừng log cùng stack trace tại mọi tầng khiến một lỗi tạo hàng trăm bản ghi. Chọn nơi phù hợp và log ngắn ở các tầng trung gian.

### 10.2. doFinally và cancellation

doFinally được gọi với SignalType.CANCEL nếu downstream hủy pipeline tại vị trí đó. Nếu muốn log CID khi cancel, capture nó trong deferContextual:

~~~java
Mono.deferContextual(view -> {
    String cid = view.get(CorrelationId.KEY);

    return longRunningWork()
        .doFinally(signal ->
            ScopedMdc.run(cid, () ->
                log.info("lifecycle={}", signal)
            )
        );
});
~~~

Cancellation không đảm bảo remote side effect đã bị rollback, nên không ghi "operation rolled back" chỉ vì SignalType.CANCEL.

### 10.3. Retry và các subscription mới

Retry có thể resubscribe lên upstream. Context viết bên ngoài retry hoặc trong request boundary cần ổn định theo **một logical operation** nếu policy yêu cầu cùng correlation ID qua các attempt.

Ví dụ:

~~~java
Mono.deferContextual(view ->
    retryableCall()
        .retryWhen(retryPolicy)
);
~~~

Đây là snippet cần retryableCall và retryPolicy. Nếu mỗi retry attempt tự tạo UUID khác bên trong defer, log khó ghép về cùng thao tác; giữ một correlation ID ở outer boundary. Nếu muốn phân biệt attempts, thêm attempt number riêng.

### 10.4. Mất context khi dùng Thread/CompletableFuture

Reactor Context không tự nhảy qua mọi ranh giới bên ngoài Reactor. Nếu ứng dụng dùng:

- new Thread(...).
- CompletableFuture.supplyAsync(...).
- ExecutorService không instrument.
- Callback từ thư viện legacy.
- Listener message broker được chạy độc lập.

thì phải truyền ID tường minh hoặc capture/restore qua Micrometer ContextSnapshot. Không chạy một subscribe() ẩn trong callback rồi kỳ vọng có cùng Reactor Context.

## 11. Thiết kế logging production

### 11.1. Log đủ, không log dữ liệu nhạy cảm

Một sự kiện thường nên có:

- Timestamp, log level.
- Service, environment, instance.
- Correlation ID và/hoặc traceId/spanId.
- Route template thay vì raw path chứa dữ liệu cá nhân nếu có thể.
- Method, status, duration.
- Error code và loại exception khi có lỗi.

Không log Authorization, Cookie, password, access token, refresh token, số thẻ, dữ liệu sức khỏe hoặc nội dung request nhạy cảm. Correlation ID cũng phải được validate để tránh log injection.

### 11.2. Định dạng structured JSON

Nếu dùng structured logging, đưa correlationId vào một JSON field riêng, không chỉ nối vào message string. Một bản ghi có thể có:

~~~json
{
  "service": "checkout",
  "level": "INFO",
  "correlationId": "req-abc",
  "event": "inventory_reserved",
  "durationMs": 14
}
~~~

JSON trên là minh họa, không phải stdout của ứng dụng demo. Logging implementation tùy Spring Boot/Logback và logging pipeline.

### 11.3. Không nhầm Context với logging verbosity

Reactor Context là storage metadata, không tự ghi log. MDC chứa giá trị cho logging framework, không tự sinh trace. Micrometer tracing là hệ riêng tạo/propagate spans.

Có thể dùng cả ba nếu hiểu ownership: Context làm nguồn sự thật cho custom ID, MDC chỉ là adapter cho logger, Tracer sở hữu traceId/spanId.

## 12. Ví dụ hoàn chỉnh Java 17 / Spring Boot 4.1.2

Dự án WebFlux sau minh họa:

- Sinh hoặc xác thực X-Correlation-ID trong một **WebFilter**.
- Ghi cùng ID vào response header.
- Đưa ID vào Reactor Context bằng contextWrite.
- Đọc ID bằng Mono.deferContextual sau một async boundary.
- Log qua MDC scope có finally để không rò giá trị trên thread dùng chung.
- Dùng WebTestClient kiểm tra ID giữ nguyên qua HTTP và nhiều requests đồng thời.
- Không yêu cầu Micrometer Context Propagation tự động, giúp hiểu cách triển khai thủ công trước khi dùng bridge.

### 12.1. Cấu trúc

~~~text
webflux-correlation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/correlation/
    │   │   ├── CorrelationApplication.java
    │   │   ├── CorrelationId.java
    │   │   ├── CorrelationIdWebFilter.java
    │   │   ├── ScopedMdc.java
    │   │   ├── CorrelationService.java
    │   │   └── CorrelationController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/correlation/
            ├── CorrelationIntegrationTest.java
            └── ScopedMdcTest.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-correlation-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý phiên bản Spring WebFlux, Reactor, Netty, SLF4J và test dependencies tương thích. Chương trình không cần một Servlet Filter.

### 12.3. CorrelationApplication.java

~~~java
package com.example.correlation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }
}
~~~

### 12.4. CorrelationId.java

~~~java
package com.example.correlation;

public final class CorrelationId {

    public static final String KEY =
        "demo.correlationId";

    public static final String HEADER =
        "X-Correlation-ID";

    public static final String MDC_KEY =
        "correlationId";

    private CorrelationId() {}
}
~~~

Ba constants giúp tránh lỗi gõ khác tên Context key, HTTP header và MDC key.

### 12.5. CorrelationIdWebFilter.java

~~~java
package com.example.correlation;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class CorrelationIdWebFilter
        implements WebFilter {

    private static final Pattern SAFE_ID = Pattern.compile(
        "[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
    );

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst(CorrelationId.HEADER);

            String id =
                incoming != null
                    && SAFE_ID.matcher(incoming).matches()
                    ? incoming
                    : UUID.randomUUID().toString();

            // Must be set before response gets committed.
            exchange.getResponse().getHeaders().set(
                CorrelationId.HEADER,
                id
            );

            // Context is applied to the upstream subscription
            // represented by chain.filter(exchange).
            return chain.filter(exchange)
                .contextWrite(context ->
                    context.put(CorrelationId.KEY, id)
                );
        });
    }
}
~~~

Ý nghĩa:

1. Filter được đặt sớm trong outer WebFilterChain.
2. Một ID được chọn theo request/subscription.
3. ID hợp lệ gồm tối đa 64 ký tự theo SAFE_ID.
4. ID thiếu/sai được thay bằng UUID.
5. Response header được gắn trước khi response commit.
6. contextWrite đưa ID vào Reactor Context cho controller/service downstream.
7. Không dùng static ThreadLocal, không gọi block(), không tự subscribe().

**Lưu ý production:** kiểm soát duplicate X-Correlation-ID headers, độ dài header tổng và reverse proxy trust boundary. Nếu chỉ gateway được phép chọn ID, service nên tin header đến từ gateway đã xác thực và tái sinh ID với các request đi vòng qua gateway.

### 12.6. ScopedMdc.java

~~~java
package com.example.correlation;

import org.slf4j.MDC;

public final class ScopedMdc {

    private ScopedMdc() {}

    public static void run(
        String correlationId,
        Runnable action
    ) {
        String previous = MDC.get(CorrelationId.MDC_KEY);

        try {
            MDC.put(CorrelationId.MDC_KEY, correlationId);
            action.run();
        }
        finally {
            if (previous == null) {
                MDC.remove(CorrelationId.MDC_KEY);
            }
            else {
                MDC.put(
                    CorrelationId.MDC_KEY,
                    previous
                );
            }
        }
    }
}
~~~

Khác với việc set MDC ở đầu HTTP request rồi hy vọng dữ liệu di chuyển qua mọi thread, helper mở MDC scope **ngay tại chỗ ghi log**. Nó lưu và khôi phục giá trị trước đó dù action ném exception.

### 12.7. CorrelationService.java

~~~java
package com.example.correlation;

import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class CorrelationService {

    private static final Logger log =
        LoggerFactory.getLogger(
            CorrelationService.class
        );

    public Mono<String> readAfterAsyncHop() {
        return Mono.delay(Duration.ofMillis(15))
            .flatMap(ignored ->
                Mono.deferContextual(context -> {
                    String id = context.get(
                        CorrelationId.KEY
                    );

                    ScopedMdc.run(id, () ->
                        log.info(
                            "Service step after async hop"
                        )
                    );

                    return Mono.just(id);
                })
            );
    }
}
~~~

Mono.delay thường phát trên Reactor Scheduler thay vì giả định giữ nguyên Netty event-loop. deferContextual vẫn đọc đúng ID từ subscription. ScopedMdc chỉ tồn tại trong lời gọi log và được dọn trong finally.

Nếu thêm một doOnNext(log.info) sau Mono.delay nhưng không có bridge, MDC có thể trống; đó là lý do ví dụ chủ động mở scope tại log point.

### 12.8. CorrelationController.java

~~~java
package com.example.correlation;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public final class CorrelationController {

    private final CorrelationService service;

    public CorrelationController(
        CorrelationService service
    ) {
        this.service = service;
    }

    @GetMapping(
        value = "/api/correlation",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> correlation() {
        return service.readAfterAsyncHop();
    }
}
~~~

Endpoint trả lại chính ID từ Reactor Context sau khi chuyển Scheduler. Mục đích là kiểm tra propagation, không phải API nghiệp vụ.

### 12.9. application.properties

~~~properties
spring.application.name=webflux-correlation-demo
server.port=8080

logging.pattern.level=%5p [cid:%X{correlationId:-}]
~~~

Trong ví dụ, MDC chỉ được set scoped trong service. Các log của framework ở những vị trí khác có thể không có cid; đó là hành vi có chủ đích của **manual mode**, không phải lỗi của WebFilter.

### 12.10. ScopedMdcTest.java

~~~java
package com.example.correlation;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.*;

class ScopedMdcTest {

    @Test
    void restoresPreviousMdcValue() {
        String oldValue = MDC.get(
            CorrelationId.MDC_KEY
        );

        try {
            MDC.put(
                CorrelationId.MDC_KEY,
                "outer"
            );

            ScopedMdc.run("inner", () ->
                assertEquals(
                    "inner",
                    MDC.get(CorrelationId.MDC_KEY)
                )
            );

            assertEquals(
                "outer",
                MDC.get(CorrelationId.MDC_KEY)
            );
        }
        finally {
            if (oldValue == null) {
                MDC.remove(CorrelationId.MDC_KEY);
            }
            else {
                MDC.put(
                    CorrelationId.MDC_KEY,
                    oldValue
                );
            }
        }
    }

    @Test
    void removesKeyWhenInitiallyMissing() {
        String previous = MDC.get(
            CorrelationId.MDC_KEY
        );

        try {
            MDC.remove(CorrelationId.MDC_KEY);

            ScopedMdc.run("temporary", () ->
                assertEquals(
                    "temporary",
                    MDC.get(CorrelationId.MDC_KEY)
                )
            );

            assertNull(
                MDC.get(CorrelationId.MDC_KEY)
            );
        }
        finally {
            if (previous == null) {
                MDC.remove(CorrelationId.MDC_KEY);
            }
            else {
                MDC.put(
                    CorrelationId.MDC_KEY,
                    previous
                );
            }
        }
    }

    @Test
    void cleansUpEvenWhenLoggingActionThrows() {
        MDC.remove(CorrelationId.MDC_KEY);

        assertThrows(
            IllegalStateException.class,
            () -> ScopedMdc.run(
                "temporary",
                () -> {
                    throw new IllegalStateException(
                        "simulated"
                    );
                }
            )
        );

        assertNull(MDC.get(CorrelationId.MDC_KEY));
    }
}
~~~

Test xác minh MDC không giữ dữ liệu request cũ sau khi log action hoàn tất hoặc ném lỗi.

### 12.11. CorrelationIntegrationTest.java

~~~java
package com.example.correlation;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorrelationIntegrationTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void preservesValidIncomingIdAcrossAsyncHop() {
        EntityExchangeResult<String> result =
            client.get()
                .uri("/api/correlation")
                .header(
                    CorrelationId.HEADER,
                    "req-123"
                )
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult();

        assertEquals(
            "req-123",
            result.getResponseHeaders().getFirst(
                CorrelationId.HEADER
            )
        );
        assertEquals(
            "req-123",
            result.getResponseBody()
        );
    }

    @Test
    void generatesUuidWhenHeaderIsMissing() {
        EntityExchangeResult<String> result =
            client.get()
                .uri("/api/correlation")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult();

        String id = result.getResponseHeaders()
            .getFirst(CorrelationId.HEADER);

        assertNotNull(id);
        assertEquals(
            id,
            result.getResponseBody()
        );

        UUID.fromString(id);
    }

    @Test
    void rejectsUntrustedHeaderValue() {
        EntityExchangeResult<String> result =
            client.get()
                .uri("/api/correlation")
                .header(
                    CorrelationId.HEADER,
                    "value with spaces"
                )
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult();

        String id = result.getResponseHeaders()
            .getFirst(CorrelationId.HEADER);

        assertNotNull(id);
        assertNotEquals(
            "value with spaces",
            id
        );
        UUID.fromString(id);
        assertEquals(id, result.getResponseBody());
    }

    @Test
    void concurrentRequestsDoNotMixContext() {
        WebClient webClient = WebClient.builder()
            .baseUrl(
                "http://localhost:" + port
            )
            .build();

        Flux<Integer> checked = Flux.range(1, 24)
            .flatMap(index -> {
                String id = "req-" + index;

                return webClient.get()
                    .uri("/api/correlation")
                    .header(CorrelationId.HEADER, id)
                    .retrieve()
                    .toEntity(String.class)
                    .map((ResponseEntity<String> response) -> {
                        assertEquals(
                            id,
                            response.getHeaders().getFirst(
                                CorrelationId.HEADER
                            )
                        );
                        assertEquals(
                            id,
                            response.getBody()
                        );

                        return index;
                    });
            }, 8);

        StepVerifier.create(checked)
            .expectNextCount(24)
            .verifyComplete();
    }
}
~~~

Bốn integration tests chứng minh:

1. ID hợp lệ giữ nguyên giữa inbound header, response header và Reactor Context sau async hop.
2. Khi thiếu header, server tạo UUID và cùng một giá trị đi xuyên pipeline.
3. Header không hợp lệ bị thay bằng UUID.
4. Nhiều request đồng thời vẫn giữ ID độc lập, không dùng chung ThreadLocal.

Lưu ý: Test chỉ xác minh **response và context values**, không xác minh format từng dòng log thực tế. ScopedMdcTest kiểm tra behavior của helper; để kiểm tra logging event, có thể bổ sung test appender phù hợp Logback.

### 12.12. Chạy test và server

Yêu cầu Java 17+ và Maven:

~~~bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
~~~

Gọi với ID do client cung cấp:

~~~bash
curl -i \
  -H "X-Correlation-ID: req-123" \
  http://localhost:8080/api/correlation
~~~

Response kỳ vọng gồm:

~~~text
HTTP/1.1 200 OK
X-Correlation-ID: req-123
Content-Type: text/plain;charset=UTF-8

req-123
~~~

Thứ tự header và định dạng Content-Type có thể khác; điều cần kiểm tra là status 200, response header X-Correlation-ID và body cùng là req-123.

Gọi không có ID:

~~~bash
curl -i http://localhost:8080/api/correlation
~~~

Response chứa một UUID mới ở header và body. Không hardcode UUID này vì giá trị được sinh ngẫu nhiên cho request.

Kiểm tra ID không hợp lệ:

~~~bash
curl -i \
  -H "X-Correlation-ID: contains spaces" \
  http://localhost:8080/api/correlation
~~~

Server sẽ tạo UUID thay vì đưa nguyên giá trị chứa khoảng trắng vào log. Không dùng ký tự CR/LF trực tiếp trong câu lệnh thử vì HTTP client có thể từ chối header trước khi request đến server.

## 13. Mở rộng demo sang automatic MDC bridge

Ví dụ manual mode giúp hiểu chính xác cách Context và MDC hoạt động. Khi cần nhiều log statement ở các toán tử khác nhau mà không muốn mở scope thủ công tại từng chỗ, có thể bật propagation.

### 13.1. Thêm dependency

Trong pom.xml, thêm:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Trong application.properties:

~~~properties
spring.reactor.context-propagation=auto
~~~

### 13.2. Cấu hình accessor

Thêm một class cấu hình minh họa:

~~~java
package com.example.correlation;

import io.micrometer.context.ContextRegistry;
import jakarta.annotation.PostConstruct;

import org.slf4j.MDC;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MdcPropagationConfiguration {

    @PostConstruct
    void registerAccessor() {
        ContextRegistry.getInstance()
            .registerThreadLocalAccessor(
                CorrelationId.KEY,
                () -> MDC.get(
                    CorrelationId.MDC_KEY
                ),
                (String value) -> MDC.put(
                    CorrelationId.MDC_KEY,
                    value
                ),
                () -> MDC.remove(
                    CorrelationId.MDC_KEY
                )
            );
    }
}
~~~

Đây là **một lựa chọn mở rộng**; nó không bắt buộc để dự án gốc compile/chạy. Sau khi thêm dependency và config, Spring Boot có thể bật automatic mode sớm, đồng thời accessor được đăng ký lúc startup trước khi phục vụ requests.

### 13.3. Đọc log trong operator

Sau khi bridge hoạt động, callback của Reactor có thể đọc MDC tương ứng với giá trị trong Context:

~~~java
Mono.delay(Duration.ofMillis(10))
    .doOnNext(value ->
        log.info("MDC auto-propagated")
    );
~~~

Không có gì đảm bảo giá trị correlationId hiện diện nếu gọi đoạn này **ngoài** subscription có Context key. Không biến một phép gọi log độc lập thành request-bound context.

### 13.4. Kiểm thử automatic mode

Thêm test trong ứng dụng khởi động với property auto:

- Header req-A được phản ánh ở MDC trong Reactor callback.
- Header req-B đồng thời không xuất hiện trong log của A.
- Callback sau khi thoát scope không giữ MDC của request đã kết thúc.
- Khi Context không có key, accessor reset xóa MDC thay vì giữ giá trị cũ.
- Không có exception hoặc deadlock khi retry, cancel, publishOn.

Không chỉ bật property rồi tuyên bố mọi ThreadLocal được truyền đi: accessor, key mapping và ranh giới subscription vẫn quyết định kết quả.

## 14. Kiểm thử Reactor Context ở cấp unit

Nếu không muốn khởi động HTTP server, có thể dùng StepVerifier trực tiếp:

~~~java
Mono<String> pipeline =
    Mono.deferContextual(view ->
        Mono.just(view.get(CorrelationId.KEY))
    )
    .publishOn(Schedulers.boundedElastic())
    .contextWrite(ctx ->
        ctx.put(CorrelationId.KEY, "unit-1")
    );

StepVerifier.create(pipeline)
    .expectNext("unit-1")
    .verifyComplete();
~~~

Snippet cần Reactor Test, Schedulers và CorrelationId. publishOn chuyển downstream execution; Context vẫn thuộc subscription.

### 14.1. Kiểm tra isolation

~~~java
Mono<String> template =
    Mono.deferContextual(view ->
        Mono.just(view.get(CorrelationId.KEY))
    );

Mono<String> a = template.contextWrite(
    Context.of(CorrelationId.KEY, "A")
);

Mono<String> b = template.contextWrite(
    Context.of(CorrelationId.KEY, "B")
);
~~~

A và B là hai pipelines có Context riêng. Test từng pipeline hoặc zip/flatMap có concurrency để xác minh không bị trộn.

### 14.2. Kiểm tra missing key

Nếu context key phải luôn có, dùng view.get(key) để fail fast thay vì âm thầm trả "missing". Với ID tùy chọn, getOrDefault có thể phù hợp. Đừng dùng một fallback chung cho mọi request ở production vì nó khiến log của nhiều request bị ghép vào cùng một mã.

### 14.3. Kiểm tra order của contextWrite

Thiết kế test đặt contextWrite ở trước/sau một operator đọc context, để phân biệt hiệu ứng theo phía upstream. Khi pipeline được compose bằng transform, flatMap, publishOn, defer và contextWrite, cần biết đúng subscription boundary.

## 15. Hiểu rõ những ranh giới context loss

### 15.1. subscribe() thủ công

~~~java
public Mono<Void> handle() {
    service.call().subscribe();
    return Mono.empty();
}
~~~

Đây là **anti-pattern** trong WebFlux request handler: subscription mới không được compose với request lifecycle; context propagation/error/cancel có thể bị mất.

Thay bằng:

~~~java
public Mono<Void> handle() {
    return service.call().then();
}
~~~

### 15.2. CompletableFuture và raw thread

Một Runnable trong CompletableFuture.supplyAsync hoặc ExecutorService không mặc nhiên nhìn thấy Reactor Context. Có thể truyền correlation ID như argument:

~~~java
Mono.deferContextual(view -> {
    String id = view.get(CorrelationId.KEY);

    return Mono.fromCallable(
        () -> blockingLegacyCall(id)
    ).subscribeOn(Schedulers.boundedElastic());
});
~~~

Đây là snippet cần blockingLegacyCall; ít nhất nó truyền ID tường minh và cô lập blocking work. Với nhiều contextual values, xem Micrometer ContextSnapshot và ContextPropagatingTaskDecorator.

### 15.3. Message brokers và asynchronous jobs

Một event có thể được xử lý sau nhiều phút hoặc trên process khác, không còn HTTP Reactor Context ban đầu. Nếu business contract yêu cầu correlation, thêm metadata có cấu trúc vào message headers. Listener phía nhận tạo một Context mới dựa trên metadata đã validate.

Không capture cả request object hoặc SecurityContext chứa secrets vào message chỉ để giữ log correlation.

### 15.4. Reactor Context và Spring Security

ReactiveSecurityContextHolder cũng dùng Reactor Context để lưu SecurityContext. Không ghi đè toàn bộ Context bằng một Context mới chỉ chứa correlation ID nếu việc đó làm mất keys do Spring Security, tracing và các thư viện khác quản lý.

An toàn hơn là:

~~~java
.contextWrite(context ->
    context.put(CorrelationId.KEY, id)
)
~~~

thay vì thay toàn bộ Context hoặc dùng một cơ chế tùy biến không merge metadata. Đây là một trong những lý do nên dùng contextWrite(Function).

## 16. Truy vấn log và observability

Với một correlation ID được trả cho client:

1. Người dùng gửi ID từ error response hoặc response header.
2. Tìm trong hệ thống log theo field correlationId.
3. Sắp theo timestamp và phân nhóm service.
4. Kết hợp traceId/spanId nếu có distributed tracing.
5. Đối chiếu HTTP status, latency, exception và downstream dependency.
6. Tìm các đoạn timeout, retry hoặc request bị cancel.
7. Không nhầm event duplicate/retry với request mới nếu workflow dùng chung ID.

### 16.1. Đo thêm metrics nào?

- Request count theo route template và status.
- Latency p50/p95/p99.
- Error rate theo dependency và exception category.
- Retry count, timeout count, cancellation count.
- Tracing sampling rate và exporter queue health.
- Log ingestion delay hoặc dropped log count.

**Không thêm correlation ID vào metric label** vì cardinality không kiểm soát được.

### 16.2. Log correlation khi trace không được sample

Tracing system có thể sample một phần requests. Khi một trace không được export, correlation ID nội bộ vẫn hữu ích cho log tìm kiếm nếu chính sách log retention cho phép. Tuy nhiên, không nên tăng log volume không kiểm soát cho mọi request chỉ để thay thế một hệ tracing thiếu cấu hình.

## 17. Lỗi thường gặp và troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| MDC trống sau publishOn | ThreadLocal không tự truyền qua Scheduler | Đọc Reactor Context rồi mở MDC scope hoặc cấu hình propagation |
| Request A xuất hiện CID của B | Không xóa ThreadLocal trên shared thread | try/finally restore, accessor reset hoặc automatic mode đúng |
| ContextView không thấy key | contextWrite đặt sai vị trí | Kiểm tra upstream/downstream trong chain |
| ID chỉ có ở controller, service mất | Service chạy trong subscribe riêng | Return Mono/Flux composition, không tự subscribe |
| Log không có CID dù response header có | Header không tự set MDC | Scoped MDC logging hoặc bridge |
| Bật auto nhưng MDC vẫn trống | Thiếu context-propagation hoặc ThreadLocalAccessor/key | Kiểm tra dependency, registry và startup order |
| Auto propagation vẫn mất ở raw Thread | Thread ngoài Reactor không được instrument | Truyền ID tường minh hoặc ContextSnapshot |
| Nhiều requests có cùng CID "missing" | Dùng fallback chung như ID thật | Sinh UUID ở inbound boundary |
| Header chứa chuỗi quá dài | Trust input không có validation | Giới hạn size/charset và duplicate headers |
| Log injection | Cho phép CR/LF và control chars | Validate ID, sanitize logs |
| Tracing có traceId nhưng downstream thiếu | WebClient được tạo ngoài Boot builder | Inject auto-configured WebClient.Builder |
| X-Correlation-ID không đi xuống service khác | W3C tracing không tự mang custom header | Client filter hoặc baggage contract |
| MDC traceId bị thay sai | Tự register duplicate accessor | Để Micrometer Tracing sở hữu tracing context |
| Métrics Prometheus nổ cardinality | Gắn CID vào label | Chỉ dùng low-cardinality labels |
| doFinally thiếu context | Hook nhận SignalType, không có ContextView | Capture ID trong deferContextual |
| CORS client không đọc được header | Header chưa expose | Expose X-Correlation-ID theo chính sách CORS |
| Không thấy CID trong async job | Job tách khỏi HTTP subscription | Chuyển metadata và khởi tạo context mới |
| Source không subscribe | Code dùng cache/side effect ở assembly | Kiểm tra lazy assembly và subscription |
| MDC scope không restore giá trị trước | Chỉ remove khi close | Lưu previous và restore trong finally |
| Lỗi ở test concurrent hiếm gặp | Dùng static ThreadLocal làm request context | Dùng Reactor Context và concurrency test |

## 18. Checklist triển khai

Trước khi đưa correlation logging vào production:

1. Xác định correlation ID khác requestId/traceId như thế nào.
2. Có chính sách nguồn sinh ID và trust boundary?
3. ID được validate charset và độ dài?
4. Header response được đặt trước khi commit?
5. WebFilter ghi đúng key vào Reactor Context?
6. ContextView được đọc tại subscription time?
7. contextWrite có đúng vị trí upstream visibility?
8. Không dùng MDC ThreadLocal làm nguồn sự thật trong WebFlux?
9. MDC scope có finally restore giá trị cũ?
10. Có phân biệt manual MDC và automatic bridge?
11. ThreadLocalAccessor được register một lần, có reset?
12. Spring Boot context propagation auto chỉ bật khi có dependency và đã test?
13. Có bảo đảm tracing exporter và sampling phù hợp?
14. Outbound WebClient dùng Boot builder nếu cần trace propagation?
15. Custom X-Correlation-ID có được propagate rõ ràng?
16. Không log secrets/PII, token hoặc raw credentials?
17. Không dùng CID làm metric label?
18. Có test nhiều requests đồng thời và sau thread hop?
19. Có test missing/invalid header và không mất context khi lỗi?
20. Có test cancellation, timeout và asynchronous boundary cần thiết?

## 19. Bài tập thực hành

**Bài 1 — Context cơ bản:** dùng Mono.deferContextual và contextWrite để truyền CID qua Mono.delay.

**Bài 2 — Thứ tự Context:** di chuyển contextWrite qua operator khác nhau và giải thích vì sao có/không thấy key.

**Bài 3 — WebFilter:** thêm X-Correlation-ID response header và xác minh bằng curl.

**Bài 4 — Validation:** thử ID có khoảng trắng, chuỗi quá 64 ký tự và thiếu header; xác minh UUID mới.

**Bài 5 — Scoped MDC:** mở scope với một giá trị cũ, chạy log, xác minh giá trị cũ được restore.

**Bài 6 — Exception cleanup:** cố tình ném exception trong ScopedMdc.run và chứng minh không rò ThreadLocal.

**Bài 7 — Nhiều request:** gọi đồng thời 100 request với các CID khác nhau, kiểm tra header/body không bị trộn.

**Bài 8 — Reactor logging:** dùng doOnEach và signal.getContextView để ghi log các onNext.

**Bài 9 — doFinally:** log CID lúc cancel bằng cách capture trong deferContextual.

**Bài 10 — Micrometer accessor:** đăng ký ThreadLocalAccessor cho MDC và bật spring.reactor.context-propagation=auto, so sánh với manual mode.

**Bài 11 — contextCapture:** set MDC ở code imperative, dùng accessor/contextCapture và kiểm tra Reactor Context nhận được giá trị.

**Bài 12 — WebClient propagation:** thêm ExchangeFilterFunction gửi X-Correlation-ID và kiểm tra bằng một downstream mock server.

**Bài 13 — Tracing:** thêm Micrometer Tracing và exporter phù hợp, quan sát traceId/spanId trong log, xem traceparent khi gọi downstream.

**Bài 14 — Context loss:** dùng CompletableFuture/raw executor, giải thích vì sao mất CID rồi sửa bằng ContextSnapshot.

**Bài 15 — Security:** đưa Reactor Context có CID cùng ReactiveSecurityContextHolder trong một request, đảm bảo không mất SecurityContext.

**Bài 16 — Metrics:** kiểm tra instrumentation không dùng CID làm metric tag, thay bằng route/status/service.

**Bài 17 — Log retrieval:** từ một X-Correlation-ID do server trả, tìm chuỗi log trên nhiều service và phân biệt nó với traceId.

## 20. Ghi nhớ

**Correlation ID** liên kết log của một request hoặc thao tác logic. **Reactor Context** lưu và truyền metadata theo subscription, bền vững khi pipeline chuyển thread. **MDC** là adapter ThreadLocal cho logger, không tự an toàn khi dùng trong WebFlux.

Hãy sinh hoặc validate ID tại HTTP boundary, lưu trong Context bằng **contextWrite**, đọc bằng **deferContextual**, rồi mở MDC scope ngắn tại log statement hoặc dùng **Micrometer Context Propagation** với ThreadLocalAccessor đã đăng ký. Dọn ThreadLocal đúng cách để không lộ ID giữa requests.

Trong Spring Boot, **spring.reactor.context-propagation=auto** bật automatic mode cho Reactor khi dependency/config phù hợp. Nếu ứng dụng đã có Micrometer Tracing, ưu tiên traceId/spanId do tracing framework quản lý; nó khác custom X-Correlation-ID. Dùng auto-configured WebClient.Builder để không bỏ qua instrumentation/tracing propagation.

## 21. Tài liệu tham khảo

- Reactor Core Reference — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor Core Reference — Context Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Reactor Core Reference — FAQ: MDC in Reactive Sequences: https://projectreactor.io/docs/core/release/reference/faq.html
- Reactor Core API — Mono.deferContextual: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core API — Flux.doOnEach and transformDeferredContextual: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Micrometer Context Propagation — Purpose: https://docs.micrometer.io/context-propagation/reference/purpose.html
- Micrometer Context Propagation — Usage: https://docs.micrometer.io/context-propagation/reference/usage.html
- Micrometer ContextRegistry Javadoc: https://javadoc.io/doc/io.micrometer/context-propagation/latest/io/micrometer/context/ContextRegistry.html
- Spring Boot Reference — Observability and Context Propagation: https://docs.spring.io/spring-boot/4.1/reference/actuator/observability.html
- Spring Boot Reference — Tracing and Log Correlation: https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
- Spring Framework Reference — WebFlux WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework Reference — WebClient Filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry — Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- Spring Boot 4.1.2 Release (October 23, 2026): https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/
