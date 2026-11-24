# Mở scope trong thread hiện tại với Micrometer và OpenTelemetry

Trong chương **Context propagation** của module **SPRING_BOOT_OBSERVABILITY**, việc mở scope trong thread hiện tại là cách đưa một **Observation hoặc Span trở thành ngữ cảnh đang hoạt động** trong một đoạn thực thi. Nhờ đó, các lời gọi con có thể lấy ngữ cảnh cha để tạo span liên quan, các thành phần tích hợp có thể bổ sung metadata vào đúng observation và logging integration có thể liên kết log với trace đang xử lý.

Với Spring Boot, Micrometer Observation và Micrometer Tracing cung cấp các API quản lý ngữ cảnh ở mức framework. OpenTelemetry có API context/scope riêng. Dù tên gọi khác nhau, nguyên tắc quan trọng giống nhau: **mở scope khi bắt đầu đoạn công việc cần mang context, đóng scope ngay khi đoạn đó kết thúc**. Scope thường gắn với thread hiện tại; nó không tự chuyển sang executor, thread khác hoặc service downstream.

## 1. Context, current observation và current span

Một request HTTP có thể đi qua controller, service và repository. Khi tracing instrumentation tạo server span, span đó có thể trở thành **current span** trong lúc xử lý request. Custom observation hoặc span con mở scope trong đoạn code của mình; khi kết thúc, ngữ cảnh trước đó được khôi phục.

```text
HTTP request
    |
    v
HTTP server span (current trên request thread)
    |
    +--> controller
           |
           +--> order.confirm observation (mở scope)
                   |
                   +--> inventory.reserve (span/observation con)
                   |
                   +--> payment.authorize (span/observation con)
           |
           +--> sau khi scope order.confirm đóng:
                  HTTP server span lại là current
```

Trong sơ đồ:

- **Context** chứa thông tin cần truyền, chẳng hạn trace ID, span ID, parent relationship và các context values.
- **Current observation/span** là observation hoặc span đang được đặt vào execution context tại thời điểm hiện tại.
- **Scope** là phạm vi tạm thời trong đó context đó được kích hoạt. Đóng scope sẽ khôi phục context đã hoạt động trước khi mở scope.
- **Span lifecycle** là vòng đời của span từ lúc bắt đầu đến lúc kết thúc. Đóng scope không đồng nghĩa kết thúc span.

Một thread có thể lần lượt xử lý nhiều request. Việc mở/đóng scope đúng giúp không để context của request trước “rò” sang công việc kế tiếp trên cùng thread.

## 2. Mở và đóng scope bằng Micrometer Observation

`ObservationRegistry` quản lý các observation handlers, convention, predicate và filter. Một custom observation có thể được khởi tạo, bắt đầu, mở scope để trở thành current rồi kết thúc:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class InventoryService {
    private final ObservationRegistry registry;

    public InventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void reserve() {
        Observation observation =
                Observation.createNotStarted("inventory.reserve", registry);

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            // Trong đoạn này, observation là current.
            checkInventory();
            reserveStock();
        } catch (RuntimeException ex) {
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private void checkInventory() {
        // Business logic.
    }

    private void reserveStock() {
        // Business logic.
    }
}
```

Trình tự ở ví dụ:

1. `createNotStarted(...)` tạo observation theo tên ổn định, chưa bắt đầu phép đo.
2. `start()` bắt đầu observation.
3. `openScope()` đặt observation vào scope hiện hành trên thread gọi.
4. Khối `try` thực thi công việc. Các instrumentation tích hợp có thể đọc current observation/span theo context mà registry/tracing bridge hỗ trợ.
5. Khi ra khỏi `try`, `Scope.close()` được gọi tự động nhờ try-with-resources, khôi phục context trước đó.
6. `stop()` kết thúc observation trong `finally` kể cả khi code ném exception.

**Không nhầm `Scope.close()` với `observation.stop()`.** Đóng scope chỉ khôi phục current context; stop kết thúc lifecycle và cho phép các handlers hoàn tất xử lý observation.

### Cách ngắn hơn với observe(...)

Nếu chỉ cần chạy một khối công việc đồng bộ, không cần tự quản lý scope, event hoặc outcome động, có thể dùng:

```java
Observation.createNotStarted("inventory.reserve", registry)
        .observe(() -> {
            checkInventory();
            reserveStock();
        });
```

`observe(...)` quản lý vòng đời observation và scope cho callback theo API của Micrometer, giúp giảm nguy cơ quên đóng scope hoặc stop. Khi cần gắn key-value dựa trên kết quả, xử lý exception tùy biến hoặc kiểm soát thời điểm cụ thể, API thủ công ở ví dụ trước có thể phù hợp hơn.

Nếu muốn ghi kết quả nghiệp vụ, dùng nhãn có tập giá trị hữu hạn như `outcome=reserved/out_of_stock/error`. Không dùng order ID, user ID hoặc exception message nguyên văn làm low-cardinality metric tags.

## 3. Mở scope với Micrometer Tracing

Khi cần làm việc trực tiếp với span thay vì observation, Micrometer Tracing cung cấp `Tracer` và API mở span trong scope:

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

public class PaymentService {
    private final Tracer tracer;

    public PaymentService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void authorize() {
        Span span = tracer.nextSpan()
                .name("payment.authorize")
                .start();
        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            // Span payment.authorize là current trong đoạn này.
            callPaymentProvider();
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }

    private void callPaymentProvider() {
        // Business logic hoặc HTTP client đã instrument.
    }
}
```

`tracer.nextSpan()` thường tạo span dựa trên context hiện tại nếu có, vì vậy nếu code đang chạy trong một server/business span, span mới có thể là span con. `tracer.withSpan(span)` mở một `SpanInScope` để span này trở thành current; đóng scope khôi phục span trước đó. `span.end()` kết thúc lifecycle.

Các kiểu/API của Micrometer Tracing được cung cấp qua bridge tương ứng; dự án phải có tracing implementation đã cấu hình. Nếu không có tracing bridge/provider phù hợp, không nên giả định `Tracer` sẽ luôn tạo recording span hoặc dữ liệu xuất hiện trong backend.

### Tại sao tạo span không tự làm span thành current?

Tách hai bước giúp code chủ động:

- Có thể tạo span và gắn thuộc tính trước khi kích hoạt nó.
- Chỉ một đoạn code cụ thể cần span đó làm context hiện hành.
- Nhiều span có thể được quản lý theo lifecycle khác nhau nhưng chỉ span trong scope mới trở thành current trong execution context.

Nếu gọi span con khi span cha chưa được đặt current hoặc không truyền explicit parent context, quan hệ parent-child có thể không như dự kiến. Vì thế cần mở scope đúng trước lời gọi tạo span con.

## 4. Scope lồng nhau và khôi phục context cha

Một request có thể mở scope A, rồi trong A mở scope B. Khi đóng B, A phải trở lại current; khi đóng A, context ban đầu (ví dụ HTTP server span) được khôi phục.

```java
Observation root = Observation.createNotStarted("order.confirm", registry);
root.start();
try (Observation.Scope rootScope = root.openScope()) {
    // root là current.

    Observation child =
            Observation.createNotStarted("inventory.reserve", registry);
    child.start();
    try (Observation.Scope childScope = child.openScope()) {
        // child là current; root là context cha bên dưới.
        reserveStock();
    } finally {
        child.stop();
    }

    // child scope đã đóng: root trở lại current.
    validateOrder();
} finally {
    // root scope đã đóng: context trước đó trở lại.
    root.stop();
}
```

Sơ đồ khôi phục:

```text
Context ban đầu (ví dụ HTTP span)
        |
        | open root scope
        v
    root = current
        |
        | open child scope
        v
    child = current
        |
        | close child scope
        v
    root = current
        |
        | close root scope
        v
Context ban đầu = current
```

Việc đóng scope theo thứ tự **ngược với thứ tự mở** là nguyên tắc của cấu trúc lồng nhau (LIFO). Try-with-resources giúp thực thi điều này khi cấu trúc code rõ ràng. Không lưu scope rồi đóng ở một callback khác hoặc sau khi thread đã chuyển sang việc khác.

Nếu một đoạn code mở scope B nhưng không đóng, các lời gọi tiếp theo trên thread có thể tiếp tục thấy B là current, khiến span con được gắn sai parent, log correlation sai hoặc thông tin request bị rò sang công việc sau.

## 5. Context khi scope bị đóng và khi span bị kết thúc

Bốn thao tác sau không thể thay thế nhau:

| Thao tác | Tác dụng | Khi nào thực hiện |
| --- | --- | --- |
| `span.start()` / `observation.start()` | Bắt đầu lifecycle | Khi phép đo bắt đầu |
| `tracer.withSpan(span)` / `observation.openScope()` | Đặt context làm current trong phạm vi hiện tại | Bao quanh code cần current context |
| `scope.close()` | Khôi phục current context trước đó | Khi ra khỏi phạm vi |
| `span.end()` / `observation.stop()` | Kết thúc lifecycle và hoàn tất xử lý telemetry | Khi thao tác đo kết thúc |

Một span có thể vẫn chưa end sau khi scope đóng nếu thiết kế lưu lifecycle đến một mốc khác. Nhưng làm như vậy cần quản lý chặt chẽ, vì span chưa kết thúc sẽ chưa được processor/exporter xử lý như span hoàn tất.

Ngược lại, kết thúc span trong khi scope vẫn đang mở có thể khiến code tiếp tục chạy với một span đã end là current. Đây là trạng thái khó diễn giải và dễ tạo lỗi; nên đóng scope trước khi end span theo cấu trúc thông thường:

```java
Span span = tracer.nextSpan().name("inventory.reserve").start();
try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    reserveStock();
} finally {
    span.end();
}
```

Với Observation:

```java
observation.start();
try (Observation.Scope scope = observation.openScope()) {
    reserveStock();
} finally {
    observation.stop();
}
```

Nếu có exception, cần ghi nhận lỗi theo API phù hợp (chẳng hạn `observation.error(ex)` hoặc `span.error(ex)` với bridge tương ứng), sau đó giữ nguyên hành vi exception của nghiệp vụ. Không nuốt lỗi chỉ để span có status đẹp.

## 6. OpenTelemetry Context và Scope khác gì Micrometer?

Trong OpenTelemetry API, một span có thể được đặt thành current bằng `span.makeCurrent()`. API trả về một `io.opentelemetry.context.Scope` mà code cần đóng:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public void reserveWithOtel(Tracer tracer) {
    Span span = tracer.spanBuilder("inventory.reserve").startSpan();
    try (Scope scope = span.makeCurrent()) {
        // Span.current() trả span này trong scope hiện hành.
        reserveStock();
    } catch (RuntimeException ex) {
        span.recordException(ex);
        span.setStatus(io.opentelemetry.api.trace.StatusCode.ERROR);
        throw ex;
    } finally {
        span.end();
    }
}
```

So sánh API:

| Nền tảng | Mở scope | Lấy current context/span | Đóng scope |
| --- | --- | --- | --- |
| Micrometer Observation | `observation.openScope()` | `Observation.currentObservationScope()` hoặc API context/handler phù hợp theo phiên bản | `Observation.Scope.close()` |
| Micrometer Tracing | `tracer.withSpan(span)` | `tracer.currentSpan()` | `Tracer.SpanInScope.close()` |
| OpenTelemetry API | `span.makeCurrent()` | `Span.current()` hoặc `Context.current()` | `io.opentelemetry.context.Scope.close()` |

Không trộn các lớp `Scope` chỉ vì cùng tên. `io.opentelemetry.context.Scope` thuộc OpenTelemetry context, còn `Observation.Scope` thuộc Micrometer Observation. Tracing bridge có thể nối chúng ở tầng tích hợp nhưng code phải dùng đúng kiểu và lifecycle API.

Nếu ứng dụng đã dùng Spring Boot/Micrometer Tracing, ưu tiên Observation hoặc Micrometer Tracer ở code ứng dụng để tránh tự khởi tạo SDK/global context không đồng bộ. Dùng OpenTelemetry API trực tiếp khi dự án đã chọn rõ OTel SDK/agent và có chủ sở hữu pipeline.

## 7. Log correlation khi scope đang hoạt động

Trong phạm vi một span đã được đặt current, logging integration có thể đọc trace context và đưa `traceId`/`spanId` vào MDC. Log có thể trông như sau (minh họa):

```text
orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7 "Reservation started"
orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b8 "Reservation complete"
```

Hai log có cùng Trace ID, nhưng Span ID có thể khác nếu chúng được ghi trong các span khác nhau. Nếu log được ghi ngoài scope, MDC có thể không còn trace/span IDs mong muốn hoặc được khôi phục về parent context.

Không phải cứ mở scope là log tự có ID. Cần tracing bridge, logging integration, MDC scope decoration và pattern/JSON encoder đọc đúng MDC keys. Khi tự xử lý MDC, phải **khôi phục giá trị cũ** trong finally/try-with-resources; không gọi `MDC.clear()` tùy tiện vì có thể xóa metadata do framework hoặc request filter khác đặt.

Log correlation giúp tìm trace cụ thể nhưng Trace ID không phải credential. Không đưa token, cookie, request body hoặc dữ liệu cá nhân vào MDC/attributes; kiểm soát quyền truy cập log/trace backend.

## 8. Mở scope không tự truyền context sang thread khác

Đây là điểm dễ gây lỗi nhất. Scope thường dựa trên context gắn với **thread đang thực thi**. Ví dụ:

```java
try (Observation.Scope scope = observation.openScope()) {
    // Thread HTTP hiện có observation là current.
    CompletableFuture.runAsync(() -> {
        // Thread khác: không giả định observation tự hiện diện ở đây.
        performAsyncWork();
    });
}
```

Callback của `CompletableFuture.runAsync(...)` có thể chạy ở common pool hoặc thread khác, nên current context của thread HTTP không tự động được sao chép. Kết quả có thể là `tracer.currentSpan()` trả về `null`, log thiếu Trace ID hoặc downstream tạo trace mới. Scope của thread gốc vẫn được đóng khi ra khỏi khối `try`; nó không chờ callback hoàn tất.

### Dùng executor có context propagation

Với Spring Framework hỗ trợ `ContextPropagatingTaskDecorator` (ví dụ các phiên bản Spring Framework 6.1+), có thể cấu hình executor để capture/restore context khi task được submit:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean(name = "observedExecutor")
    ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Sau đó phải thật sự dùng executor đã cấu hình:

```java
observedExecutor.execute(() -> {
    // Context đã được decorator khôi phục cho task nếu các
    // ThreadLocalAccessor/tracing integration phù hợp được đăng ký.
    processOrderAsync();
});
```

Chỉ tạo bean executor **không ảnh hưởng** những lời gọi `CompletableFuture.runAsync(task)` không truyền executor, hoặc các pool do thư viện khác tự tạo. Context propagation còn cần các accessor/tracing integration phù hợp; test current span, log correlation và parent-child ở worker thread.

### Cẩn trọng với thời điểm đóng scope gốc

Nếu task async chạy lâu hơn request thread, việc scope gốc đóng không làm task đã capture context mất context ngay lập tức khi decorator hoạt động đúng. Decorator capture giá trị cần truyền tại thời điểm submit và khôi phục nó trong thời gian task chạy, rồi restore context trước đó khi task kết thúc. Nhưng **không được dùng một Span object đã kết thúc** làm parent cho công việc bắt đầu muộn mà không có thiết kế rõ ràng. Với background workflow dài, có thể tạo một trace mới và liên kết span trước bằng links/correlation thích hợp.

## 9. Scope và HTTP/message propagation là hai ranh giới khác nhau

Mở scope giải quyết **current context trong một execution context cục bộ**. Gọi service khác cần **inject/extract trace context vào transport** (ví dụ W3C Trace Context trong header `traceparent`). Hai thao tác phối hợp nhưng không thay thế nhau.

```text
Thread A (orders-service)                Thread B (payment-service)
------------------------                 --------------------------
server span A
  |
  +-- open scope for span B
        |
        +-- HTTP client instrumentation
              |
              +-- inject traceparent --------> extract traceparent
                                                  |
                                                  v
                                           server span C (child)
        |
  close scope
  end span B
```

Nếu dùng HTTP client không được instrument, mở scope không tự viết `traceparent` vào header. Nếu message consumer xử lý ở worker, phải extract context từ message headers và mở scope trước khi xử lý. W3C propagator cần tương thích hai phía; proxy không nên xóa header tracing ngoài chính sách trust boundary.

Một workflow message dài có thể tạo trace mới với span link tới context producer thay vì kéo dài một cây cha–con xuyên thời gian rất lâu. Chọn semantics dựa trên mô hình nghiệp vụ và công cụ backend.

## 10. Các lỗi thường gặp khi mở scope

| Hiện tượng | Nguyên nhân phổ biến | Cách sửa/kiểm tra |
| --- | --- | --- |
| Log trong service không có Trace ID | Không có current span hoặc MDC integration | Kiểm tra tracing bridge, scope và encoder |
| Span con không có parent như mong muốn | Gọi tạo span trước khi mở scope cha | Mở scope cha quanh lời gọi con hoặc truyền explicit context |
| Request sau trên cùng thread mang trace ID cũ | Scope không được đóng khi exception xảy ra | Dùng try-with-resources; kiểm tra mọi nhánh return/throw |
| `tracer.currentSpan()` trả null trong executor | Không propagation context sang thread mới | Dùng executor/decorator hoặc context-aware API |
| Span đã kết thúc nhưng vẫn là current | Gọi `span.end()` trước khi đóng scope | Đóng scope rồi mới end span |
| Scope đóng ở thread khác | Vi phạm lifecycle/context thread-local | Đóng trong cùng phạm vi thực thi đã mở |
| Trace bị tách khi gọi downstream | Mở scope cục bộ nhưng HTTP client không inject context | Instrument client và kiểm tra trace headers |
| Backend không có span dù current span đã đọc được ID | Sampling, exporter/collector hoặc retention | Kiểm tra từng tầng; không suy luận chỉ từ log |
| Metrics vẫn có nhưng traces vắng mặt | Metric handler hoạt động, tracing bị sampled out hoặc bridge lỗi | Kiểm tra sampling, tracing handler/exporter |

**Không nuốt exception để giữ scope.** Try-with-resources đóng scope cả khi code ném lỗi; ghi nhận exception/status phù hợp rồi ném lại theo hợp đồng nghiệp vụ. Nếu dùng finally thủ công, phải bảo đảm đóng scope trước khi end span và không ghi đè exception gốc bằng lỗi cleanup không liên quan.

## 11. Quy trình viết code an toàn

Trước khi mở scope, xác định rõ:

1. **Ai sở hữu lifecycle?** Code tạo span/observation phải chịu trách nhiệm start và stop/end; đừng end span do instrumentation/framework khác sở hữu.
2. **Đoạn nào cần current context?** Chỉ bao quanh code thực sự cần context; không mở scope lâu hơn transaction/request.
3. **Context cha là gì?** Đảm bảo scope cha đã current trước khi tạo span con hoặc gọi instrumentation downstream.
4. **Đóng ở đâu?** Dùng try-with-resources; tránh return/throw trong khi scope chưa được đóng.
5. **Có chuyển thread không?** Nếu có, dùng context propagation rõ ràng; không trông chờ ThreadLocal tự truyền.
6. **Logs có correlation không?** Kiểm tra MDC và pattern, đồng thời khôi phục context cũ.
7. **Signals có xuất không?** Kiểm tra ObservationRegistry handlers, tracing bridge, sampler, exporter và backend.
8. **Metadata có an toàn/cardinality thấp không?** Không gắn Trace ID, order ID hoặc thông tin nhạy cảm vào metric tags.

### Bảng kiểm thử tối thiểu

| Kịch bản | Kỳ vọng |
| --- | --- |
| Mở scope observation trên thread hiện tại | Current observation được đặt trong đoạn code cần đo |
| Mở span con trong scope cha | Trace ID giữ nguyên, Span ID mới, parent đúng |
| Scope lồng nhau A rồi B | Đóng B khôi phục A; đóng A khôi phục context ban đầu |
| Ném exception trong try block | Scope vẫn đóng, span/observation kết thúc, exception tiếp tục truyền |
| Return sớm trong try block | Scope tự đóng nhờ try-with-resources |
| Không có span/observation trước đó | API current có thể trả null/no current; code xử lý đúng |
| Chạy callback trên thread mới không decorator | Không giả định current context được giữ |
| Chạy với executor có context propagation | Context được capture/restore nếu accessor/integration đã cấu hình |
| HTTP downstream được instrument | Trace context được inject/extract và parent-child hợp lệ |
| Sampling loại trace | Context có thể vẫn tồn tại; không bắt buộc có trace ở backend |
| Logging correlation hoạt động | Trace/span fields khớp scope hiện hành và được restore sau khi scope đóng |

## 12. Bài tập tình huống

Một controller mở observation `order.confirm`, sau đó thực hiện:

```java
Observation observation =
        Observation.createNotStarted("order.confirm", registry);
observation.start();
try (Observation.Scope scope = observation.openScope()) {
    log.info("Confirming order");
    CompletableFuture.runAsync(() -> {
        log.info("Persisting order");
        repository.save(order);
    });
} finally {
    observation.stop();
}
```

Ở môi trường thật, log `Confirming order` có Trace ID, còn `Persisting order` không có. Một số database spans xuất dưới trace mới.

**Câu hỏi:** lỗi nằm ở exporter hay ở scope? Vì sao?

**Phân tích tham khảo:**

- Log đầu được ghi trong scope của thread controller nên có thể nhận current trace context.
- `CompletableFuture.runAsync(...)` không dùng executor có context propagation được chỉ định; callback có thể chạy ở thread khác. Scope của controller không tự được chuyển sang thread đó.
- Scope controller đóng ngay sau khi submit callback, không chờ callback hoàn thành. Việc này đúng về lifecycle của request, nhưng callback cần context được capture khi submit nếu muốn tiếp nối trace.
- Nếu callback tạo database observation/span mà không có parent context, tracer có thể tạo trace mới. Log không có Trace ID là bằng chứng phù hợp với mất current context, chưa đủ để kết luận exporter sai.

**Cách sửa:** submit callback qua executor có `ContextPropagatingTaskDecorator` và các context accessor/tracing integration được cấu hình. Hoặc thiết kế background job thành một trace riêng, ghi business correlation/link tới trace request nếu workflow yêu cầu. Sau đó xác minh Trace ID/Span ID, parent-child và log correlation trong worker, rồi mới kiểm tra exporter/collector nếu spans vẫn không xuất.

**Kết luận:** Mở scope trong thread hiện tại là thao tác **kích hoạt context tạm thời**, còn đóng scope là **khôi phục context trước đó**. Nó không tự kết thúc span, không tự inject HTTP headers và không tự truyền context sang thread khác. Với Spring Boot/Micrometer/OpenTelemetry, hãy quản lý scope bằng try-with-resources, lifecycle span riêng biệt, propagation rõ ràng cho executor/message/HTTP và kiểm chứng liên kết metrics–logs–traces để việc điều tra lỗi, độ trễ trên môi trường thực không bị đứt ngữ cảnh.
