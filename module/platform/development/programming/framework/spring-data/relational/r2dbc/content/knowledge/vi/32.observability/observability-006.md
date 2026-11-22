# Truyền mã theo dõi qua ngữ cảnh phản ứng

Trong ứng dụng Spring WebFlux kết hợp Spring Data R2DBC, một request có thể đi qua nhiều lớp và nhiều thread: WebFilter, Controller, Service, Repository, R2DBC driver và các dịch vụ HTTP bên ngoài. Để nối log và lần theo một request xuyên suốt các lớp đó, ứng dụng thường cần một mã tương quan (correlation ID) hoặc thông tin trace (trace ID/span ID).

Ở ứng dụng imperative, thông tin theo request thường được lưu trong ThreadLocal hoặc MDC. Cách này không đủ tin cậy trong reactive pipeline vì một request có thể tiếp tục trên thread khác sau `publishOn`, `flatMap` hoặc một thao tác I/O. Reactor cung cấp **Context** gắn với subscription để truyền metadata theo luồng reactive, độc lập với thread hiện tại.

Trong Spring reactive stack, Reactor Context còn được dùng bởi các cơ chế nền tảng như reactive transaction management và observability. Vì vậy, khi truyền correlation ID, cần thêm giá trị vào Context theo cách giữ nguyên các giá trị đã có; không thay toàn bộ Context hoặc chuyển metadata sang một biến toàn cục. Với logging dựa trên MDC/ThreadLocal, cần cầu nối context propagation phù hợp hoặc đặt MDC trong phạm vi callback đồng bộ.

## 1. Correlation ID và trace ID có mục đích gì?

Hai loại ID thường xuất hiện trong observability:

- **Correlation ID:** mã ứng dụng dùng để liên kết các log hoặc thao tác thuộc cùng một request/workflow. Nó thường được nhận từ HTTP header hoặc được tạo ở edge/service đầu tiên.
- **Trace ID:** định danh một distributed trace gồm nhiều span qua các service. Trace ID thuộc mô hình distributed tracing, thường tuân theo W3C Trace Context hoặc định dạng của tracing system.
- **Span ID:** định danh một đoạn công việc trong trace, ví dụ một HTTP server request, một lời gọi HTTP client hoặc một thao tác database được instrument.

Correlation ID và trace ID có thể được liên kết hoặc trong một hệ thống đơn giản có thể dùng chung một giá trị, nhưng về ý nghĩa chúng không mặc nhiên giống nhau. Trace có quan hệ cha-con và sampling; correlation ID thường chỉ là khóa tìm kiếm log do ứng dụng quản lý.

Ví dụ:

~~~text
HTTP request
  X-Correlation-ID: req-7f2a...
  traceparent: 00-4bf92f...-00f067...-01

Application log:
  correlationId=req-7f2a...
  traceId=4bf92f...
  spanId=00f067...
~~~

Khi dùng Micrometer Tracing hoặc OpenTelemetry, hãy để tracing library quản lý trace/span ID và propagation headers. Không tự tạo trace ID rồi ghi đè thông tin trace đã được tracing system thiết lập.

## 2. Vì sao ThreadLocal không đủ trong reactive?

ThreadLocal lưu giá trị gắn với thread. Trong mô hình reactive, thread xử lý một tín hiệu có thể khác thread đã bắt đầu request:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::toResponse);
~~~

Publisher có thể thực thi các đoạn khác nhau trên các thread khác nhau. Với `flatMap`, nhiều inner publisher có thể chạy đồng thời và các tín hiệu có thể được xử lý bởi những thread khác nhau.

Nếu chỉ làm:

~~~java
MDC.put("correlationId", correlationId);
return service.findSomething();
~~~

giá trị MDC có thể không có ở thread thực hiện callback sau đó. Tệ hơn, thread pool tái sử dụng thread; nếu không xóa MDC đúng cách, request sau có thể nhìn thấy giá trị còn sót từ request trước.

Reactor Context giải quyết bài toán truyền metadata theo subscription thay vì dựa vào thread identity. Context vẫn có thể được đọc khi pipeline đổi thread, miễn thao tác vẫn nằm trong cùng reactive chain và không bị tách thành một subscription độc lập.

## 3. Reactor Context là gì?

Reactor Context là một cấu trúc key/value bất biến gắn với subscriber. Nó thường chứa metadata nhỏ như:

- Correlation ID.
- Trace context hoặc baggage được quản lý bởi tracing integration.
- Thông tin tenant đã được xác thực.
- Security context trong reactive security.
- Transaction resource do Spring quản lý.
- Một số cờ điều khiển nội bộ theo request.

Context không phải một Map mutable dùng chung cho toàn ứng dụng. Các operator tạo phiên bản Context mới khi thêm hoặc thay đổi key. Một subscription có Context riêng, vì vậy hai request đồng thời có thể dùng cùng key nhưng mang giá trị khác nhau.

Ví dụ:

~~~java
static final String CORRELATION_ID = "app.correlationId";

Mono<String> publisher = Mono.deferContextual(context ->
        Mono.just(context.get(CORRELATION_ID))
);

Mono<String> request = publisher.contextWrite(context ->
        context.put(CORRELATION_ID, "req-123")
);
~~~

Khi subscriber chạy, `deferContextual` đọc giá trị từ Context của subscription và phát ra `req-123`.

## 4. Đọc Context bằng deferContextual

`deferContextual` cho phép tạo publisher dựa trên Context có sẵn tại thời điểm subscribe:

~~~java
public Mono<String> currentCorrelationId() {
    return Mono.deferContextual(context -> {
        String id = context.getOrDefault(
                CORRELATION_ID,
                "unknown"
        );
        return Mono.just(id);
    });
}
~~~

Có thể dùng `context.hasKey(...)` trước khi đọc key bắt buộc:

~~~java
return Mono.deferContextual(context -> {
    if (!context.hasKey(CORRELATION_ID)) {
        return Mono.error(
                new IllegalStateException("Correlation ID is missing")
        );
    }

    return Mono.just(context.get(CORRELATION_ID));
});
~~~

Nếu metadata chỉ dùng cho log và có thể không tồn tại trong một số đường gọi nội bộ, `getOrDefault` thường phù hợp. Nếu metadata là điều kiện bắt buộc của nghiệp vụ hoặc bảo mật, hãy xác thực ở ranh giới request và phát lỗi rõ ràng thay vì âm thầm dùng giá trị mặc định.

## 5. Ghi Context bằng contextWrite

`contextWrite` cập nhật Context mà các operator upstream nhìn thấy:

~~~java
Mono<String> result = currentCorrelationId()
        .contextWrite(context ->
                context.put(CORRELATION_ID, "req-456")
        );
~~~

Một điểm dễ nhầm: dữ liệu Context được truyền theo hướng từ downstream subscriber về upstream khi subscription diễn ra. Vì vậy, `contextWrite` thường đặt ở cuối chain để publisher phía trước nó có thể đọc giá trị:

~~~java
return service.findSomething()
        .map(this::toResponse)
        .contextWrite(context ->
                context.put(CORRELATION_ID, correlationId)
        );
~~~

Không cần đặt `contextWrite` ở mọi lớp. Nếu WebFilter đã thêm correlation ID vào Context của request, các publisher được nối đúng cách phía dưới có thể đọc nó.

Khi thêm key, dùng function nhận Context hiện tại:

~~~java
.contextWrite(context -> context.put(CORRELATION_ID, id))
~~~

Tránh thay Context bằng một Context mới không chứa giá trị cũ:

~~~java
// Không nên nếu cần giữ transaction, security hoặc tracing context.
.contextWrite(Context.of(CORRELATION_ID, id))
~~~

Thay toàn bộ Context có thể làm mất transaction resource hoặc metadata do Spring và tracing infrastructure đã gắn vào. Hãy sửa trên Context được truyền vào callback để giữ các key hiện hữu.

## 6. Đưa correlation ID vào Context tại WebFilter

WebFilter là vị trí phù hợp để nhận hoặc tạo correlation ID một lần ở ranh giới HTTP. Filter có thể:

1. Đọc header correlation từ request.
2. Kiểm tra định dạng và độ dài.
3. Tạo ID mới nếu không có hoặc giá trị không hợp lệ.
4. Ghi ID vào response header.
5. Đưa ID vào Reactor Context cho phần xử lý downstream.

Ví dụ:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdWebFilter implements WebFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String CONTEXT_KEY = "app.correlationId";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,128}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String supplied = exchange.getRequest()
                .getHeaders()
                .getFirst(HEADER);

        String correlationId = isValid(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        exchange.getResponse()
                .getHeaders()
                .set(HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(CONTEXT_KEY, correlationId)
                );
    }

    private boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
~~~

Ví dụ dùng pattern giới hạn ký tự và chiều dài để tránh header bất thường hoặc log injection. Chính sách thực tế có thể chọn luôn tạo UUID ở server thay vì tin ID từ client. Nếu chấp nhận ID bên ngoài, cần xác định client nào được phép cung cấp và không dùng giá trị đó làm bằng chứng xác thực.

Response header được đặt trước khi response commit. Nếu ứng dụng đã có filter khác thiết lập correlation ID, cần thống nhất một nguồn tạo ID và thứ tự filter để không ghi đè qua lại.

## 7. Vì sao nên validate correlation header?

Correlation ID thường được ghi vào log và có thể xuất hiện trong response hoặc trace. Không nên chấp nhận chuỗi tùy ý không giới hạn:

- Chuỗi quá dài có thể làm phình log và header.
- Ký tự xuống dòng có thể gây log injection nếu được ghi không an toàn.
- Giá trị chứa thông tin cá nhân hoặc bí mật có thể bị lưu ở nhiều hệ thống.
- Client có thể cố tình dùng cùng ID cho nhiều request để làm nhiễu điều tra.

Một chiến lược phổ biến là:

- Giới hạn độ dài, ví dụ tối đa 128 ký tự.
- Chỉ chấp nhận tập ký tự đơn giản.
- Tạo UUID mới khi thiếu hoặc sai định dạng.
- Không đưa token, email, tên hoặc dữ liệu nghiệp vụ vào ID.
- Có thể ghi nhận riêng việc header đầu vào không hợp lệ bằng metric/log đã làm sạch.

Correlation ID là metadata để truy vết, không phải secret, session token hay authorization credential.

## 8. Đọc correlation ID ở Service

Service có thể đọc Context khi thật sự cần metadata:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return Mono.deferContextual(context -> {
        String correlationId = context.getOrDefault(
                CorrelationIdWebFilter.CONTEXT_KEY,
                "unknown"
        );

        log.info("Creating order, correlationId={}", correlationId);

        return orderRepository.save(toOrder(command));
    });
}
~~~

Tuy nhiên, không cần đọc Context ở mọi method chỉ để ghi log. Có thể dùng logging/tracing integration tự động để gắn metadata. Nếu Service cần correlation ID để gọi hệ thống ngoài hoặc ghi audit, hãy cân nhắc truyền một request/workflow context rõ kiểu qua tham số thay vì làm mọi domain method phụ thuộc vào Reactor Context.

Reactor Context phù hợp cho cross-cutting metadata; dữ liệu nghiệp vụ cần thiết cho tính đúng đắn nên xuất hiện trong command hoặc tham số tường minh.

## 9. Gắn correlation ID vào log bằng MDC

SLF4J MDC thường dựa trên ThreadLocal. Reactor Context không tự động đồng bộ với MDC nếu chưa bật cơ chế context propagation phù hợp.

Một cách thủ công là đọc Context và đặt MDC chỉ trong phạm vi callback đồng bộ đang ghi log:

~~~java
return orderRepository.findById(orderId)
        .doOnNext(order ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            "unknown"
                    );
                    return Mono.fromRunnable(() -> {
                        try (var ignored = MDC.putCloseable(
                                "correlationId", id)) {
                            log.info("Order loaded: {}", order.id());
                        }
                    });
                }).subscribe()
        );
~~~

Đoạn trên **không nên dùng** vì callback `doOnNext` tạo subscription độc lập bằng `subscribe()`; nó tách công việc khỏi pipeline gốc. Cần tránh kiểu này.

Một cách quan sát đúng trong pipeline là dùng `doOnEach` và `Signal.getContextView()`:

~~~java
return orderRepository.findById(orderId)
        .doOnEach(signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            String id = signal.getContextView().getOrDefault(
                    CorrelationIdWebFilter.CONTEXT_KEY,
                    "unknown"
            );

            try (var ignored = MDC.putCloseable("correlationId", id)) {
                log.info("Order loaded: {}", signal.get().id());
            }
        });
~~~

MDC chỉ tồn tại trong callback đồng bộ ghi log đó rồi được khôi phục/xóa khi đóng scope. Không giả định MDC vẫn tồn tại ở callback tiếp theo hoặc trên thread khác.

Nếu cần mọi log trong cả call stack đều tự có correlation ID, hãy dùng Micrometer Context Propagation hoặc tracing integration thay vì tự thêm `doOnEach` vào mọi publisher.

## 10. Micrometer Context Propagation và ThreadLocalAccessor

Micrometer Context Propagation cung cấp cơ chế bridge giữa các context mechanism, ví dụ Reactor Context và ThreadLocal. Một `ThreadLocalAccessor` mô tả cách đọc, ghi và xóa một giá trị ThreadLocal; context snapshot có thể khôi phục các giá trị đó khi callback chạy trên thread khác.

Ý tưởng:

~~~text
Reactor Context
    correlationId = req-123
          |
          v
Context Propagation
          |
          v
ThreadLocal / MDC
    correlationId = req-123
          |
          v
Synchronous log statement
          |
          v
Restore / clear ThreadLocal
~~~

Khi dùng MDC, có thể đăng ký accessor phù hợp hoặc dùng integration do tracing/logging stack cung cấp. Tránh tự viết accessor nếu ứng dụng đã có bridge của Micrometer Tracing, Brave, OpenTelemetry hoặc thư viện logging.

Context propagation phải khôi phục trạng thái ThreadLocal trước đó và xóa giá trị khi không còn scope. Nếu chỉ đặt MDC mà không dọn dẹp, thread pool có thể rò metadata giữa các request.

## 11. Bật automatic context propagation của Reactor

Reactor có hỗ trợ tích hợp Micrometer Context Propagation. Ở các phiên bản Reactor hỗ trợ API này, có thể bật automatic context propagation:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Hooks;

@Configuration
public class ReactorContextConfiguration {

    @PostConstruct
    public void enableContextPropagation() {
        Hooks.enableAutomaticContextPropagation();
    }
}
~~~

API và hành vi phụ thuộc phiên bản Reactor Core và Micrometer Context Propagation. Cần kiểm tra version do Spring Boot quản lý và tài liệu tương ứng trước khi thêm cấu hình. Automatic mode có thể tạo thêm chi phí khi capture/restore ThreadLocal; chỉ bật khi ứng dụng cần bridge đó và đã đo tác động.

Trong Spring Boot, một số phiên bản cung cấp thuộc tính cấu hình cho chế độ context propagation của Reactor. Tên thuộc tính và giá trị hợp lệ phụ thuộc phiên bản Boot; hãy kiểm tra configuration metadata của dự án thay vì sao chép một property từ phiên bản khác.

Automatic propagation không thay thế việc đặt correlation ID vào Reactor Context. Nó chỉ giúp khôi phục các giá trị đã được đăng ký/đưa vào context theo cơ chế hỗ trợ.

## 12. contextCapture và context propagation

Micrometer Context Propagation có thể capture các ThreadLocal đã đăng ký thành snapshot. Reactor cung cấp operator `contextCapture()` trong các phiên bản tích hợp tương ứng để đưa snapshot vào Context khi subscribe.

Mô hình khái niệm:

~~~java
Mono<Result> result = service.execute()
        .contextCapture();
~~~

Điều này hữu ích khi một thư viện imperative đã đặt metadata trong ThreadLocal trước lúc tạo subscription và ứng dụng muốn capture nó vào Reactor Context.

Đối với WebFlux, hướng ưu tiên thường là đưa metadata từ request vào Reactor Context ở WebFilter, rồi dùng propagation bridge cho những đoạn code cần ThreadLocal/MDC. Không dựa vào việc một ThreadLocal được đặt ở thread nhận HTTP sẽ luôn còn nguyên khi pipeline chạy.

## 13. Tracing với Micrometer Observation và Micrometer Tracing

Correlation ID do ứng dụng quản lý là một lớp metadata. Distributed tracing nên dùng framework chuyên dụng:

- **Micrometer Observation:** API quan sát hoạt động, có thể tạo metrics và tracing handler.
- **Micrometer Tracing:** abstraction cho trace/span và propagation.
- **OpenTelemetry hoặc Brave bridge:** backend/tracer cụ thể.
- **W3C Trace Context:** chuẩn truyền trace qua HTTP headers như `traceparent` và tùy chọn `tracestate`.

Spring Boot Actuator và Micrometer Tracing có thể tự instrument một số ranh giới framework khi các dependency/configuration phù hợp được thêm vào. Không giả định mọi lệnh R2DBC hoặc mọi query SQL đều có span tự động; mức hỗ trợ phụ thuộc phiên bản, driver và instrumentation được cấu hình.

Khi tracing đã quản lý trace context, không tự ghi đè trace ID bằng correlation ID. Nếu cần liên kết hai giá trị, ghi correlation ID như một span/log attribute đã được kiểm soát.

## 14. Propagate correlation ID qua WebClient

Khi Service gọi một HTTP service khác, có thể chuyển correlation ID qua header. Dùng WebClient filter đọc Reactor Context tại thời điểm subscribe:

~~~java
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public class CorrelationWebClientFilter {

    public static ExchangeFilterFunction propagate() {
        return (request, next) ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            null
                    );

                    if (id == null) {
                        return next.exchange(request);
                    }

                    ClientRequest updated = ClientRequest.from(request)
                            .headers(headers ->
                                    headers.set(
                                            CorrelationIdWebFilter.HEADER,
                                            id
                                    )
                            )
                            .build();

                    return next.exchange(updated);
                });
    }
}
~~~

Đăng ký filter:

~~~java
@Bean
WebClient webClient(WebClient.Builder builder) {
    return builder
            .filter(CorrelationWebClientFilter.propagate())
            .build();
}
~~~

Nếu ứng dụng dùng distributed tracing, để tracing instrumentation tự quản lý `traceparent`. Correlation header riêng có thể được truyền bổ sung nếu các service cần dùng nó để tìm log.

Không gửi correlation ID hoặc baggage tùy ý tới mọi host bên ngoài. Chỉ propagate qua các dependency tin cậy và tránh gửi dữ liệu nhạy cảm.

## 15. Propagate trace context theo chuẩn W3C

W3C Trace Context định nghĩa header chính:

- `traceparent`: chứa version, trace ID, parent span ID và trace flags.
- `tracestate`: tùy chọn, chứa thông tin vendor-specific.

Một header ví dụ có dạng:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Không tự parse rồi dựng lại header này trong ứng dụng nếu đang dùng Micrometer Tracing/OpenTelemetry. Tracing propagator phải chịu trách nhiệm validate, tạo span con và inject/extract đúng chuẩn.

Khi một request đi vào service, instrumentation trích xuất context từ header. Khi gọi service khác, client instrumentation tạo child span và inject context tương ứng. Trace ID được giữ xuyên suốt, còn span ID thay đổi theo từng đoạn công việc.

## 16. Truyền metadata qua nhiều lớp Service

Nếu một method cần correlation ID chỉ để log, đọc Reactor Context tại điểm log hoặc dùng logging bridge. Nếu ID là input nghiệp vụ, truyền bằng tham số:

~~~java
public Mono<Order> createOrder(
        CreateOrderCommand command,
        String requestId) {

    log.info("Creating order, requestId={}", requestId);
    return orderRepository.save(toOrder(command));
}
~~~

Không biến Reactor Context thành nơi chứa mọi tham số. Context phù hợp cho metadata xuyên suốt và cross-cutting concerns; tham số tường minh giúp thể hiện dependency nghiệp vụ, dễ kiểm thử và không phụ thuộc runtime context.

## 17. Reactor Context và transaction context cùng tồn tại

Spring reactive transaction management lưu transaction resource trong Reactor Context. Vì vậy, việc thêm correlation ID phải giữ các key đã tồn tại:

~~~java
return transactionalOperator.transactional(
        orderRepository.save(order)
)
.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, correlationId)
);
~~~

Không thay Context bằng một instance chỉ chứa correlation ID. Nếu làm mất transaction resource, repository có thể không còn tham gia transaction mong muốn; các context khác như security hoặc observation cũng có thể bị ảnh hưởng.

Khi dùng nhiều `contextWrite`, thứ tự operator và key trùng nhau có thể làm giá trị được ghi đè. Đặt key có namespace rõ ràng, chỉ một nơi chịu trách nhiệm tạo correlation ID và tránh ghi đè ở các lớp bên dưới.

## 18. Context trong flatMap và các publisher lồng nhau

Các operator Reactor được nối trong cùng subscription có thể truy cập Context của subscriber:

~~~java
return orderRepository.findById(orderId)
        .flatMap(order ->
                Mono.deferContextual(context -> {
                    String id = context.getOrDefault(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            "unknown"
                    );

                    log.info(
                            "Loading customer for order, correlationId={}",
                            id
                    );

                    return customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer));
                })
        );
~~~

Context được đọc trong publisher con vì nó thuộc cùng subscription chain. Không cần truyền correlation ID bằng biến static hoặc ThreadLocal.

Nếu một publisher con được subscribe độc lập bằng `subscribe()`, nó không tự động kế thừa Context của subscription cha. Tránh tự subscribe trong Service; hãy trả publisher và ghép bằng `flatMap`, `concatMap`, `then` hoặc operator phù hợp.

## 19. Context không tự truyền sang CompletableFuture hoặc raw thread

Reactor Context chỉ được bảo đảm trong các publisher được nối theo semantics của Reactor. Nếu chuyển sang:

- `new Thread(...)`.
- `CompletableFuture.supplyAsync(...)`.
- Một Executor không tích hợp context propagation.
- Callback của thư viện không reactive.

thì metadata không tự động xuất hiện ở đó.

Nếu phải tích hợp API imperative, hãy dùng Micrometer Context Propagation và executor/task decorator phù hợp, hoặc truyền metadata tường minh qua tham số. Không dựa vào ThreadLocal hiện tại còn tồn tại ở thread thực thi.

Ví dụ ý tưởng với executor có context-aware wrapper:

~~~java
// Pseudocode: cách bọc Executor tùy phiên bản Micrometer/Spring.
Executor contextAwareExecutor =
        ContextExecutorService.wrap(delegateExecutor, contextSnapshotFactory);
~~~

Tên API và cách tạo snapshot cần theo đúng version Micrometer Context Propagation. Nếu không có integration, truyền correlation ID tường minh là lựa chọn đơn giản và dễ kiểm soát.

## 20. Correlation ID trong log structured

Log dạng key/value dễ tìm kiếm hơn log văn bản không cấu trúc:

~~~text
timestamp=2026-11-15T10:00:00Z
level=INFO
service=order-service
correlationId=req-7f2a
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
operation=createOrder
orderId=9001
message="Order saved"
~~~

Khi dùng Logback MDC, có thể khai báo pattern chứa `%X{correlationId}`:

~~~xml
<pattern>%d %-5level [%X{correlationId}] %logger - %msg%n</pattern>
~~~

Pattern chỉ hiển thị giá trị nếu MDC đã được bridge/populate đúng lúc log được ghi. Việc thêm pattern không tự đọc Reactor Context.

Structured logging có thể dùng JSON encoder và đưa correlationId/traceId thành field riêng. Không dùng ID có cardinality cao làm metric label; correlation ID phù hợp cho log và trace lookup.

## 21. Propagate correlation ID tới R2DBC/database log

Correlation ID trong Reactor Context không tự động trở thành SQL comment, session variable hoặc field trong database server log. Để nối log ứng dụng với database, có một số lựa chọn:

- Dùng distributed tracing instrumentation cho R2DBC/driver nếu stack hỗ trợ.
- Ghi query span với trace ID và thông tin database operation.
- Dùng database session/application name nếu driver/database hỗ trợ và có cách đặt theo connection an toàn.
- Dùng tracing proxy hoặc query instrumentation được hỗ trợ.

Không nối correlation ID từ client vào SQL text bằng string concatenation. Cách đó có thể làm query cache kém hiệu quả, tạo rủi ro injection và khiến SQL log chứa dữ liệu không kiểm soát.

Nếu dùng session variable, cần nhớ connection được tái sử dụng trong pool. Giá trị phải được đặt và reset đúng cách trước khi connection trả về pool; nếu không, request sau có thể thừa hưởng metadata của request trước. Hãy ưu tiên cơ chế instrumentation chính thức và kiểm thử với pool thực tế.

## 22. Correlation ID không phải authorization hoặc tenant isolation

Correlation ID là metadata quan sát. Không dùng nó để:

- Xác định người dùng đã đăng nhập.
- Cấp quyền truy cập resource.
- Chọn tenant database mà không xác thực tenant.
- Làm idempotency key duy nhất cho nghiệp vụ nếu không có semantics phù hợp.
- Chứng minh request đến từ một service đáng tin cậy.

Nếu Context chứa tenant ID hoặc security principal, giá trị đó phải đến từ cơ chế xác thực/ủy quyền đáng tin cậy. Không tin một header `X-Tenant-ID` do client tự gửi mà không xác minh quyền truy cập.

Correlation ID có thể do client cung cấp để hỗ trợ hỗ trợ kỹ thuật, nhưng server cần validate và có thể thay bằng ID nội bộ. Nó không được dùng làm secret.

## 23. Context và nhiều request đồng thời

Một lợi ích quan trọng của Reactor Context là mỗi subscription có metadata riêng. Ví dụ:

~~~java
Mono<String> readId = Mono.deferContextual(context ->
        Mono.just(context.get(CorrelationIdWebFilter.CONTEXT_KEY))
);

Mono<String> first = readId.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, "request-A")
);

Mono<String> second = readId.contextWrite(context ->
        context.put(CorrelationIdWebFilter.CONTEXT_KEY, "request-B")
);

return Mono.zip(first, second);
~~~

Hai publisher có thể chạy đồng thời mà không ghi đè correlation ID của nhau. Điều này khác với một biến static mutable hoặc ThreadLocal được dùng sai cách.

Không lưu request ID vào field mutable của singleton Service:

~~~java
// Không an toàn cho request đồng thời.
private String currentCorrelationId;
~~~

Singleton service được nhiều request dùng chung. Một request có thể ghi đè giá trị của request khác.

## 24. Xử lý request nội bộ không có WebFilter

Một số publisher được gọi từ scheduler, message listener hoặc test chứ không đi qua HTTP WebFilter. Khi đó có thể không có correlation ID.

Chọn chính sách rõ:

- Tạo workflow ID ở consumer boundary.
- Dùng message ID làm correlation key nếu phù hợp.
- Truyền ID từ scheduled job hoặc batch execution.
- Dùng giá trị fallback chỉ cho log nếu ID không bắt buộc.

Không giả định mọi reactive publisher đều bắt đầu từ HTTP request. Nên có một thành phần tại mỗi entry point tạo hoặc nhận metadata tương ứng.

## 25. Correlation ID qua message broker

Khi phát message, có thể đưa correlation ID vào message header hoặc metadata của event:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlationId", correlationId)
        .build();
~~~

Ví dụ dùng Spring Messaging abstraction; cách gửi header thực tế phụ thuộc broker binder/producer API.

Consumer đọc header và đưa ID vào Reactor Context của pipeline xử lý:

~~~java
public Mono<Void> handle(
        OrderCreated event,
        String correlationId) {

    return process(event)
            .contextWrite(context ->
                    context.put(
                            CorrelationIdWebFilter.CONTEXT_KEY,
                            correlationId
                    )
            );
}
~~~

Nếu dùng distributed tracing, broker instrumentation có thể propagate trace context theo header chuẩn của tracing system. Không chỉ truyền correlation ID mà bỏ qua traceparent nếu cần nối distributed trace qua message.

## 26. Kiểm thử Reactor Context bằng StepVerifier

Có thể kiểm tra publisher nhìn thấy giá trị Context:

~~~java
Mono<String> publisher = Mono.deferContextual(context ->
        Mono.just(context.get("test.correlationId"))
);

StepVerifier.create(
                publisher.contextWrite(context ->
                        context.put("test.correlationId", "test-123")
                )
        )
        .expectAccessibleContext()
        .contains("test.correlationId", "test-123")
        .then()
        .expectNext("test-123")
        .verifyComplete();
~~~

Test này xác nhận Context được thiết lập và đọc trong cùng subscription. Nó không chứng minh MDC hoặc trace backend đã được cấu hình đúng.

## 27. Kiểm thử WebFilter với WebTestClient

Kiểm tra request thiếu correlation header:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Correlation-ID");
~~~

Kiểm tra header hợp lệ được giữ lại:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .header("X-Correlation-ID", "test-request-42")
        .exchange()
        .expectHeader()
        .valueEquals("X-Correlation-ID", "test-request-42");
~~~

Kiểm tra header không hợp lệ:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .header("X-Correlation-ID", "bad value\nfor-log")
        .exchange()
        .expectHeader()
        .valueMatches(
                "X-Correlation-ID",
                "[A-Za-z0-9._-]{1,128}"
        );
~~~

Trong test thực tế, endpoint có thể cần authentication hoặc fixture dữ liệu. Cũng nên xác minh Service/HTTP client nhận đúng Context ID, không chỉ response header được echo.

## 28. Kiểm thử không rò Context giữa request

Gửi nhiều request đồng thời với correlation ID khác nhau rồi xác minh:

- Mỗi response trả đúng ID của request đó.
- Log của request A không chứa ID của request B.
- WebClient call từ A gửi ID A.
- Publisher con trong cùng request giữ đúng Context.
- Request không có ID được tạo giá trị riêng.

Một test dùng hai publisher độc lập có thể xác nhận Context riêng:

~~~java
Mono<String> currentId = Mono.deferContextual(context ->
        Mono.just(context.get("correlationId"))
);

Mono<String> requestA = currentId.contextWrite(context ->
        context.put("correlationId", "A")
);

Mono<String> requestB = currentId.contextWrite(context ->
        context.put("correlationId", "B")
);

StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(tuple -> {
            assertEquals("A", tuple.getT1());
            assertEquals("B", tuple.getT2());
        })
        .verifyComplete();
~~~

## 29. Các lỗi thường gặp

1. **Chỉ đặt MDC ở đầu request.** Callback có thể chạy trên thread khác và không thấy giá trị.
2. **Dùng ThreadLocal làm nguồn context chính trong reactive flow.** Thread không đại diện cho subscription.
3. **Gọi subscribe() để đọc Context trong callback.** Tạo subscription tách rời và mất context của luồng gốc.
4. **Thay toàn bộ Reactor Context bằng Context.of(...).** Có thể làm mất transaction/security/observation context.
5. **Đặt contextWrite ở vị trí không hiểu rõ phạm vi.** Operator upstream có thể không nhìn thấy giá trị mong muốn.
6. **Dùng biến mutable singleton cho request ID.** Request đồng thời có thể ghi đè lẫn nhau.
7. **Không xóa MDC sau khi log.** Thread pool có thể rò ID sang request sau.
8. **Tự tạo trace ID và ghi đè traceparent.** Làm đứt distributed trace hoặc sai quan hệ span.
9. **Cho client gửi correlation ID không giới hạn.** Có thể gây log injection hoặc log/header quá lớn.
10. **Coi correlation ID là thông tin xác thực.** ID chỉ phục vụ quan sát, không cấp quyền.
11. **Giả định R2DBC server log tự có correlation ID.** Cần instrumentation hoặc cơ chế database-specific.
12. **Giả định Context tự đi vào CompletableFuture/raw thread.** Cần context propagation hoặc truyền tham số.
13. **Bật automatic propagation mà không xem chi phí/version.** Hành vi và API phụ thuộc Reactor/Micrometer version.
14. **Propagate metadata nhạy cảm tới mọi dịch vụ ngoài.** Chỉ gửi trường cần thiết qua dependency tin cậy.

## Quy tắc lựa chọn nhanh

- Dùng Reactor Context cho metadata xuyên suốt một reactive subscription.
- Tạo/validate correlation ID ở WebFilter hoặc entry point tương ứng.
- Dùng `contextWrite(context -> context.put(...))` để thêm key mà giữ Context hiện tại.
- Dùng `deferContextual` để đọc giá trị tại thời điểm subscribe.
- Không dùng ThreadLocal/MDC làm nguồn sự thật cho reactive flow.
- Dùng MDC bridge hoặc Micrometer Context Propagation khi cần log tự động trên thread khác.
- Để Micrometer Tracing/OpenTelemetry quản lý trace ID, span ID và W3C trace headers.
- Propagate correlation ID qua WebClient/message header chỉ tới dependency tin cậy.
- Không gọi subscribe() độc lập để đọc Context; nối publisher vào chain hiện tại.
- Giữ correlation metadata tách biệt với authorization và dữ liệu nghiệp vụ.
- Kiểm thử Context, WebFilter, MDC propagation và request đồng thời.

Reactor Context là cơ chế phù hợp để truyền correlation metadata qua ứng dụng WebFlux và Spring Data R2DBC vì nó gắn với subscription thay vì thread. Hãy tạo hoặc xác thực correlation ID ở entry point, thêm nó bằng `contextWrite`, đọc bằng `deferContextual` và giữ nguyên Context hiện tại để transaction/security/tracing metadata không bị mất. Khi cần đưa giá trị vào MDC hoặc code imperative, dùng Micrometer Context Propagation hoặc bridge có cleanup đúng cách. Với distributed tracing, để tracing library quản lý trace/span và W3C headers; correlation ID chỉ là khóa liên kết log. Cách này giúp theo dõi request qua các lớp reactive mà không phụ thuộc vào thread cụ thể hoặc làm rò metadata giữa các request đồng thời.
