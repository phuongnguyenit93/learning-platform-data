# Tích hợp ngữ cảnh với logging, tracing và cơ chế ngữ cảnh của framework

## Mục tiêu bài học

Trong một ứng dụng Java hiện đại, một request có thể đi qua controller, service, repository, listener bất đồng bộ và hệ thống bên ngoài. Những thông tin như **request ID**, **tenant ID**, **trace ID** và **span ID** cần xuất hiện đúng nơi để đội phát triển có thể đọc log, mở trace và xác định luồng xử lý. Tuy nhiên, mỗi công cụ quản lý ngữ cảnh theo một cơ chế khác nhau.

**`ScopedValue`** trong Java 25 cung cấp một cách truyền dữ liệu chỉ đọc theo chiều caller → callee trong một phạm vi thực thi có giới hạn. Để tích hợp nó đúng cách, cần phân biệt:

- **ScopedValue:** ngữ cảnh thuộc logic ứng dụng, được bind trong dynamic scope.
- **MDC (Mapped Diagnostic Context):** dữ liệu bổ sung cho log, thường gắn với thread hiện tại.
- **Tracing context:** ngữ cảnh trace/span do Micrometer Tracing hoặc OpenTelemetry quản lý.
- **Framework context:** cơ chế riêng của Spring MVC, Spring Async, Reactor, Spring Security hoặc messaging.

Bài **Tích hợp ngữ cảnh với logging, tracing và cơ chế ngữ cảnh của framework** thuộc chương **Ứng dụng ScopedValue** của module **JAVA_VERSION_JAVA25**. Nội dung sử dụng API ScopedValue đã chính thức hóa theo **JEP 506**; các ví dụ không yêu cầu preview flag và không dùng StructuredTaskScope như API production ổn định.

Sau bài này, bạn có thể:

1. Thiết kế một request context bất biến và bind tại ranh giới tiếp nhận request.
2. Đưa request ID từ ScopedValue vào SLF4J MDC mà vẫn khôi phục đúng MDC lồng nhau.
3. Gắn thuộc tính nghiệp vụ vào span hiện hành mà không tự tạo trace ID hoặc thay thế tracing instrumentation.
4. Phối hợp ScopedValue với `ContextPropagatingTaskDecorator` trong Spring để truyền context qua executor.
5. Phân biệt ScopedValue với Reactor Context và cơ chế bảo mật của Spring Security.
6. Kiểm thử context isolation, nested scope, async execution, logging và tracing.
7. Tránh lộ dữ liệu nhạy cảm và tránh phụ thuộc vào cơ chế propagation không được bảo đảm.

> **Phiên bản và phạm vi:** ScopedValue là API final trong Java 25. Ví dụ Spring dùng API ổn định của Spring Framework 6.1 trở lên và Micrometer Context Propagation. Cần dùng Spring Boot BOM tương thích với phiên bản ứng dụng; không tự ghim phiên bản thư viện rời rạc chỉ để chạy ví dụ.

## 1. Vì sao cần tích hợp nhiều cơ chế context?

Giả sử request `POST /orders` có request ID `req-7f2a`, được xử lý qua luồng:

~~~mermaid
flowchart TD
    HTTP["HTTP request<br/>requestId=req-7f2a"] --> FILTER["Request boundary<br/>bind ScopedValue"]
    FILTER --> CTRL["OrderController"]
    CTRL --> SERVICE["OrderService"]
    SERVICE --> REPO["OrderRepository"]
    SERVICE --> ASYNC["Async payment task"]
    ASYNC --> PAYMENT["PaymentHandler"]
    PAYMENT --> KAFKA["Kafka producer"]
    KAFKA --> REMOTE["Downstream service"]
    FILTER -. "request context" .-> LOG["Logs / MDC"]
    SERVICE -. "span attributes" .-> TRACE["Trace backend"]
    ASYNC -. "context propagation" .-> PAYMENT
~~~

Khi điều tra một đơn hàng, đội vận hành thường cần:

- Tìm toàn bộ log có cùng request ID.
- Mở trace của request để xem thời gian ở từng span.
- Xác định task bất đồng bộ có còn thuộc request ban đầu hay đã chạy độc lập.
- Liên kết message gửi sang Kafka với nghiệp vụ tạo ra message đó.
- Tránh việc request sau trên một worker thread nhận nhầm context của request trước.

Không một API đơn lẻ nào đảm nhiệm tất cả việc này. ScopedValue không phải logging framework, MDC không phải distributed tracing, còn trace context không phải kho lưu trạng thái nghiệp vụ.

### 1.1. Chọn đúng nơi lưu từng loại dữ liệu

| Dữ liệu | Nơi quản lý phù hợp | Mục đích |
|---|---|---|
| `requestId`, `tenantId` đã xác thực, locale xử lý | Một record được bind bằng ScopedValue | Context phụ trợ trong call chain của ứng dụng |
| `traceId`, `spanId`, parent span | Micrometer Tracing / OpenTelemetry | Liên kết các span trong một lần thực thi |
| Trường hiển thị trong log | SLF4J MDC | Thêm key-value vào log event |
| Context trong reactive pipeline | Reactor Context | Truyền dữ liệu theo subscriber/pipeline |
| Authentication và authorization | Spring Security context và policy tương ứng | Danh tính, quyền và quyết định bảo mật |
| Event ID và trạng thái giao nhận | Payload/hợp đồng event, publication registry, database | Khử trùng lặp và đối soát nghiệp vụ |

**Nguyên tắc:** chỉ dùng ScopedValue cho thông tin mà các tầng sâu trong cùng một luồng thực thi cần đọc. Các dữ liệu nghiệp vụ ảnh hưởng kết quả method như `orderId`, `amount`, `currency` vẫn nên truyền bằng tham số rõ ràng khi đó là một phần của hợp đồng phương thức.

## 2. Tạo request context bằng ScopedValue

Một record bất biến có thể chứa các trường tương quan được phép dùng trong ứng dụng:

~~~java
package com.example.shop.context;

public record RequestContext(
        String requestId,
        String tenantId,
        String locale
) {}
~~~

Lớp quản lý scope giữ key ở phạm vi riêng:

~~~java
package com.example.shop.context;

import java.util.Objects;
import java.util.Optional;

public final class RequestContextScope {

    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    private RequestContextScope() {}

    public static void runWith(
            RequestContext context,
            Runnable action) {

        Objects.requireNonNull(context);
        Objects.requireNonNull(action);

        ScopedValue.where(CURRENT, context).run(action);
    }

    public static RequestContext current() {
        return CURRENT.get();
    }

    public static Optional<RequestContext> currentOptional() {
        return CURRENT.isBound()
                ? Optional.of(CURRENT.get())
                : Optional.empty();
    }

    public static Runnable wrap(Runnable task) {
        Objects.requireNonNull(task);

        if (!CURRENT.isBound()) {
            return task;
        }

        RequestContext captured = CURRENT.get();

        return () -> ScopedValue.where(CURRENT, captured).run(task);
    }
}
~~~

Lớp này có ba trách nhiệm:

- `runWith` bind context trong lúc callback chạy và tự khôi phục binding khi callback kết thúc.
- `current` yêu cầu phải có binding; nếu không có, `get()` phát sinh `NoSuchElementException`.
- `wrap` chụp context hiện hành tại thời điểm tạo task wrapper, rồi bind lại trong thread thực thi task.

`wrap` là cơ chế truyền context **tường minh do ứng dụng định nghĩa**. Nó không làm ScopedValue tự động kế thừa qua mọi thread hay executor.

### 2.1. Bind ở ranh giới request

Tại ranh giới HTTP, tạo context sau khi đã kiểm tra dữ liệu đầu vào. Ví dụ dưới đây minh họa phần điều phối:

~~~java
package com.example.shop.web;

import com.example.shop.context.RequestContext;
import com.example.shop.context.RequestContextScope;

import java.util.UUID;

public final class RequestEntryPoint {

    public void handle(String suppliedRequestId, String tenantId) {
        String requestId = isAcceptable(suppliedRequestId)
                ? suppliedRequestId
                : UUID.randomUUID().toString();

        RequestContext context =
                new RequestContext(requestId, tenantId, "vi-VN");

        RequestContextScope.runWith(context, () -> {
            // Toàn bộ lời gọi đồng bộ phía dưới nằm trong scope này.
            orderControllerHandle();
        });
    }

    private boolean isAcceptable(String value) {
        return value != null
                && value.matches("[A-Za-z0-9._-]{1,80}");
    }

    private void orderControllerHandle() {
        // Gọi controller/service của ứng dụng.
    }
}
~~~

Đây là ví dụ Java thuần để làm rõ boundary; adapter cho Servlet Filter hoặc WebFlux phải giữ đúng hợp đồng exception và lifecycle của framework. Không dùng nguyên mẫu method này như một Servlet Filter hoàn chỉnh.

Nếu request ID được gửi từ client, cần giới hạn độ dài và ký tự, không đưa chuỗi tùy ý vào log. Request ID chỉ dùng để tương quan; nó **không phải bằng chứng xác thực** và không được dùng thay tenant authorization.

### 2.2. Không bind context quá sớm hoặc quá lâu

Tạo binding ở nơi đã có dữ liệu đáng tin cậy và kết thúc scope khi xử lý request đồng bộ hoàn tất. Tránh:

- Bind context trong static initializer hoặc giữ một Carrier như trạng thái toàn cục.
- Tạo tenant context từ header chưa được xác minh.
- Dùng ScopedValue để lưu session hoặc trạng thái thay đổi qua nhiều request.
- Giữ scope mở trong lúc chờ một tác vụ nền kéo dài nhiều phút.
- Đưa access token, mật khẩu, dữ liệu thẻ hoặc thông tin cá nhân không cần thiết vào context.

Với tác vụ chạy nền sau khi request kết thúc, hãy chụp đúng các trường cần thiết thành một command/event bất biến và truyền chúng theo hợp đồng của tác vụ.

## 3. Tích hợp với logging qua SLF4J MDC

**MDC** cho phép thêm các cặp key-value vào log event. Với SLF4J, MDC được ủy quyền cho logging backend có hỗ trợ (thường là Logback hoặc Log4j). Các giá trị MDC thường gắn với thread hiện hành; ScopedValue không tự đồng bộ sang MDC.

### 3.1. Bridge từ ScopedValue sang MDC

Tạo một helper riêng cho logging:

~~~java
package com.example.shop.logging;

import com.example.shop.context.RequestContext;
import com.example.shop.context.RequestContextScope;
import org.slf4j.MDC;

public final class RequestContextMdc {

    private static final String REQUEST_ID = "requestId";

    private RequestContextMdc() {}

    public static void run(Runnable action) {
        RequestContext context =
                RequestContextScope.currentOptional().orElse(null);

        if (context == null) {
            action.run();
            return;
        }

        String previous = MDC.get(REQUEST_ID);

        try {
            MDC.put(REQUEST_ID, context.requestId());
            action.run();
        } finally {
            if (previous == null) {
                MDC.remove(REQUEST_ID);
            } else {
                MDC.put(REQUEST_ID, previous);
            }
        }
    }
}
~~~

Cách dùng ở boundary:

~~~java
RequestContextScope.runWith(context, () ->
        RequestContextMdc.run(() -> orderService.placeOrder(command)));
~~~

Các log được phát trong lời gọi đồng bộ sẽ có `requestId` trong MDC nếu backend logging đang hỗ trợ MDC.

**Tại sao cần khôi phục giá trị cũ?** Có thể đang tồn tại MDC của một scope bên ngoài. Khi chạy scope lồng nhau, helper phải trả MDC về đúng giá trị trước đó. Chỉ gọi `MDC.remove` ở `finally` có thể xóa nhầm context của caller.

SLF4J có `MDC.putCloseable` để tự remove key khi đóng. Tuy nhiên, closeable này có hành vi **remove key**, không tự khôi phục một giá trị cũ đã có cùng key. Với scope lồng nhau, cách lưu và khôi phục giá trị trước đó như ví dụ trên diễn đạt rõ hơn.

### 3.2. Đưa MDC vào format log

Một cấu hình console đơn giản với Logback có thể dùng:

~~~yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [requestId=%X{requestId}] [traceId=%X{traceId:-}] [spanId=%X{spanId:-}] %logger{36} - %msg%n"
~~~

Các trường `%X{...}` đọc MDC. `requestId` do helper ở trên đưa vào; `traceId` và `spanId` chỉ xuất hiện nếu tracing integration đã đưa chúng vào MDC. Nếu hai trường trace trống, kiểm tra cấu hình logging/tracing của ứng dụng thay vì tự sinh ID giả để làm log trông đầy đủ.

Với Spring Boot và Micrometer Tracing, cấu hình mặc định có thể cung cấp correlation IDs trong log khi tracing được bật. Nếu đã tùy chỉnh pattern hoặc logging backend, hãy xác minh output thực tế; không mặc định rằng mọi backend đều có cùng MDC behavior.

### 3.3. Vì sao MDC không thay thế ScopedValue?

| Câu hỏi | ScopedValue | MDC |
|---|---|---|
| Dùng để đọc context trong code? | Có, qua key và `get()` | Có thể đọc, nhưng chủ yếu dành cho log |
| Tự khôi phục khi scope kết thúc? | Có | Không; ứng dụng/framework phải cleanup hoặc restore |
| Phạm vi mặc định | Dynamic scope của thread | Context của logging backend trên thread |
| Có nên chứa dữ liệu nghiệp vụ phức tạp? | Có thể dùng record phù hợp | Không; MDC chủ yếu là chuỗi nhỏ để log |
| Tự propagate sang executor? | Không với executor tùy ý | Không nếu không có cơ chế propagation |

Dùng ScopedValue làm nguồn dữ liệu context của ứng dụng và MDC như một **projection dành riêng cho logging**. Không nên coi MDC là nơi lưu context chính rồi để các tầng nghiệp vụ đọc trực tiếp từ đó.

## 4. Tích hợp với distributed tracing

Tracing trả lời câu hỏi: *một lần thực thi đã đi qua những span nào, mỗi span mất bao lâu và lỗi xuất hiện ở đâu?* Tracing context do Micrometer Tracing hoặc OpenTelemetry quản lý; ứng dụng nên dùng API tương ứng để gắn thuộc tính nghiệp vụ vào span đang hoạt động.

### 4.1. Gắn request ID vào span hiện hành bằng OpenTelemetry

Ví dụ dùng OpenTelemetry API:

~~~java
package com.example.shop.tracing;

import com.example.shop.context.RequestContext;
import com.example.shop.context.RequestContextScope;
import io.opentelemetry.api.trace.Span;

public final class RequestTraceAttributes {

    private RequestTraceAttributes() {}

    public static void addRequestAttribute() {
        RequestContext context =
                RequestContextScope.currentOptional().orElse(null);

        if (context == null) {
            return;
        }

        Span span = Span.current();

        if (span.getSpanContext().isValid()) {
            span.setAttribute("app.request.id", context.requestId());
        }
    }
}
~~~

Gọi helper khi request span đã được tạo:

~~~java
RequestContextScope.runWith(context, () -> {
    RequestTraceAttributes.addRequestAttribute();
    orderService.placeOrder(command);
});
~~~

`Span.current()` lấy span hiện hành từ OpenTelemetry Context. Nếu không có span hợp lệ, helper không cố tạo trace mới. Việc tạo span, parent-child relationship, sampling và export thuộc trách nhiệm của tracing instrumentation/SDK.

**Không tạo trace ID bằng UUID trong ScopedValue.** Trace ID và span ID phải do tracing system quản lý. `requestId` là ID ứng dụng để tra cứu request; nó có thể xuất hiện như span attribute, nhưng không thay trace ID.

### 4.2. Dùng Micrometer Tracing khi ứng dụng theo Spring Boot

Nếu ứng dụng dùng Micrometer Tracing, có thể thêm tag cho span hiện hành qua `Tracer`:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

public final class MicrometerRequestTags {

    private final Tracer tracer;

    public MicrometerRequestTags(Tracer tracer) {
        this.tracer = tracer;
    }

    public void addRequestId(String requestId) {
        Span span = tracer.currentSpan();

        if (span != null) {
            span.tag("app.request.id", requestId);
        }
    }
}
~~~

Chọn **một API tracing phù hợp với stack đang dùng**. Không cần tạo một span thủ công chỉ để ghi request ID nếu instrumentation đã tạo span server. Nếu cần một span cho thao tác nghiệp vụ riêng, dùng API của tracer và đóng span đúng lifecycle.

### 4.3. Giữ trace context và application context riêng biệt

| Giá trị | Ví dụ | Ai sở hữu |
|---|---|---|
| `requestId` | `req-7f2a` | Ứng dụng |
| `traceId` | Chuỗi trace theo chuẩn tracing | Micrometer/OpenTelemetry |
| `spanId` | ID của một span trong trace | Micrometer/OpenTelemetry |
| `eventId` | UUID ổn định của một event | Hợp đồng event |
| `correlationId` | ID gom một quy trình nghiệp vụ dài | Hợp đồng ứng dụng/tích hợp |

Một request có thể tạo nhiều event; một event có thể được retry sau khi trace gốc đã kết thúc. Do đó, **không dùng traceId làm eventId** và không yêu cầu mọi lần retry phải có cùng traceId. Hãy liên kết các lần xử lý bằng eventId/correlationId, còn trace phản ánh một lần thực thi cụ thể.

## 5. Spring Framework: truyền context qua executor bất đồng bộ

Khi chuyển từ thread request sang thread của executor, binding ScopedValue hiện tại không tự động xuất hiện trong worker thread. MDC và một số tracing context cũng là thread-local, nên cần propagation phù hợp.

Spring Framework cung cấp **`ContextPropagatingTaskDecorator`** từ Spring Framework 6.1. Decorator này hỗ trợ khôi phục context được đăng ký qua Micrometer Context Propagation, đặc biệt hữu ích với logging context và observation context. Tuy nhiên, nó **không tự hiểu ScopedValue** chỉ vì ứng dụng có JDK 25.

Ta cần kết hợp hai bước:

1. Chụp RequestContext hiện tại và bind lại trong task bằng `RequestContextScope.wrap`.
2. Dùng `ContextPropagatingTaskDecorator` để chuyển những context khác có accessor phù hợp, ví dụ observation/tracing/logging.

### 5.1. Ghép decorator cho Spring TaskExecutor

~~~java
package com.example.shop.configuration;

import com.example.shop.context.RequestContextScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean
    TaskDecorator applicationContextTaskDecorator() {
        ContextPropagatingTaskDecorator micrometer =
                new ContextPropagatingTaskDecorator();

        return task -> micrometer.decorate(
                RequestContextScope.wrap(
                        () -> RequestContextMdc.run(task)));
    }

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor(
            TaskDecorator applicationContextTaskDecorator) {

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("shop-async-");
        executor.setTaskDecorator(applicationContextTaskDecorator);
        return executor;
    }
}
~~~

Trong ví dụ, `RequestContextScope.wrap(...)` được gọi khi task được đưa vào executor, lúc context của caller còn khả dụng. Wrapper chụp record hiện hành; khi task chạy trên worker, nó bind lại record rồi gọi `RequestContextMdc.run(task)` để đưa request ID vào MDC của chính worker và khôi phục MDC cũ sau khi task kết thúc. Lớp decorator Micrometer bao ngoài hỗ trợ khôi phục những context khác có accessor được đăng ký.

Khai báo task:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PaymentAsyncService {

    @Async("applicationTaskExecutor")
    public void capturePayment(String orderId) {
        // Có thể đọc RequestContextScope.current() nếu task
        // được submit khi caller đang ở trong scope hợp lệ.
        String requestId =
                RequestContextScope.current().requestId();

        // Gọi gateway và ghi log/tracing theo context.
    }
}
~~~

Đây là ví dụ tích hợp. Trong dự án thực, xác minh đúng executor được `@Async` sử dụng; một decorator đặt trên bean không được task gọi tới thì không có tác dụng. Với task được submit ngoài request scope, wrapper giữ nguyên hành vi không có binding; code worker nên xử lý trường hợp thiếu context nếu đó là một tình huống hợp lệ.

### 5.2. Spring Boot auto-configured executor

Spring Boot có property hỗ trợ context propagation cho `AsyncTaskExecutor` do Boot tự cấu hình:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Property này phục vụ context propagation của framework/Micrometer theo phiên bản Spring Boot tương ứng. Nó không thay thế wrapper riêng cho ScopedValue trong ví dụ trên. Nếu ứng dụng tự tạo executor, cần gắn `ContextPropagatingTaskDecorator` vào executor thực tế.

### 5.3. Chi phí và giới hạn

Context snapshot và decorator có overhead khi capture/restore. Với task rất nhỏ hoặc khối lượng cực lớn, hãy đo trên workload thực và chỉ propagate các context cần thiết. Không đưa toàn bộ MDC, baggage hoặc object request lớn sang worker thread.

Nếu worker cần dữ liệu nghiệp vụ sau khi request kết thúc, thiết kế command bất biến có trường rõ ràng thường dễ kiểm soát hơn việc giữ nguyên toàn bộ request context.

## 6. Reactor và Spring WebFlux: dùng Reactor Context cho reactive pipeline

Trong reactive application, một chuỗi `Mono`/`Flux` có thể chuyển thread nhiều lần. **Reactor Context** là cơ chế ngữ cảnh theo subscriber/pipeline; không nên gọi `ScopedValue.get()` từ một operator chạy ở thread khác và kỳ vọng binding vẫn có mặt.

Nếu bắt đầu reactive pipeline trong một scope ScopedValue, chụp record và đưa nó vào Reactor Context một cách tường minh:

~~~java
import reactor.core.publisher.Mono;

public final class ReactiveOrderService {

    public static final Object REQUEST_CONTEXT_KEY =
            RequestContext.class;

    public Mono<String> handle(String orderId) {
        RequestContext captured = RequestContextScope.current();

        return Mono.deferContextual(view -> {
            RequestContext context =
                    view.get(REQUEST_CONTEXT_KEY);

            return Mono.just(
                    "request=" + context.requestId()
                    + ", order=" + orderId);
        }).contextWrite(context ->
                context.put(REQUEST_CONTEXT_KEY, captured));
    }
}
~~~

Ở đây:

- `captured` được đọc trong lúc code còn nằm trong ScopedValue scope.
- `contextWrite` đưa record sang Reactor Context.
- `deferContextual` đọc context từ subscriber khi pipeline thực thi, không đọc ScopedValue trên worker thread.

Spring Boot có cấu hình context propagation cho Reactor theo phiên bản, chẳng hạn `spring.reactor.context-propagation=auto`, để hỗ trợ các context được đăng ký trong hệ sinh thái Micrometer. Điều này không có nghĩa Reactor tự động kế thừa mọi ScopedValue. Nếu cần chuyển một giá trị ScopedValue vào reactive pipeline, hãy thực hiện bước capture/write như trên.

**Không chuyển tùy tiện toàn bộ Servlet request object vào Reactor Context.** Chỉ đưa những giá trị nhỏ, bất biến và cần thiết cho pipeline.

## 7. Spring Security và các context nhạy cảm

Request context thường có `tenantId`, nhưng không nên coi `tenantId` là một cơ chế bảo mật. Việc một tenant ID tồn tại trong ScopedValue không chứng minh người gọi có quyền truy cập tenant đó.

Với xác thực và phân quyền:

- Để Spring Security quản lý `SecurityContext` theo cơ chế chính thức của framework.
- Với async security execution, dùng các abstraction propagation do Spring Security cung cấp và kiểm tra cấu hình executor thực tế.
- Không sao chép access token, credential hoặc toàn bộ `Authentication` vào MDC để log.
- Không tạo một `ScopedValue<Authentication>` rồi coi nó thay thế authorization checks.
- Khi dùng tenant ID trong application context, chỉ tạo sau khi identity và quyền truy cập đã được xác minh.

**Tách hai nhiệm vụ:** ScopedValue có thể mang metadata đã được xác thực để code không phải truyền qua nhiều tầng; Spring Security vẫn là nơi quyết định danh tính và quyền thực hiện hành động.

## 8. Đi qua HTTP hoặc message broker

ScopedValue chỉ quản lý binding trong JVM/thread và dynamic scope. Nó không serialize context sang process khác. Khi gọi downstream service hoặc gửi Kafka message, có hai nhóm dữ liệu riêng:

| Dữ liệu cần truyền | Cơ chế |
|---|---|
| Trace context | OpenTelemetry/Micrometer instrumentation inject/extract propagation headers, thường theo W3C Trace Context |
| Application correlation | Header hoặc field trong hợp đồng message/API, ví dụ `correlationId` hoặc `eventId` |
| ScopedValue object | Không truyền trực tiếp; chuyển thành các field nhỏ trong DTO/event nếu thực sự cần |
| Authentication | Cơ chế xác thực của giao thức và security framework, không copy tùy tiện từ ScopedValue |

Với OpenTelemetry, propagation thường do instrumentation đảm nhiệm. Khi cần thủ công, sử dụng Propagators API và header carrier theo chuẩn, không tự tạo header `traceId` riêng. Trace context qua một ranh giới tin cậy phải được kiểm soát; không coi baggage từ bên ngoài là dữ liệu đáng tin.

### 8.1. Retry sau restart

Một event được phát lúc 09:00 có thể được retry lúc 11:00 sau khi service restart. ScopedValue scope của HTTP request ban đầu đã kết thúc, thread và trace gốc không còn hoạt động.

Khi retry:

- Dùng lại **eventId** của cùng một event.
- Giữ correlation ID nếu quy trình nghiệp vụ cần liên kết.
- Tạo trace/span cho lần thực thi mới theo tracing instrumentation.
- Không cố khôi phục một ScopedValue binding đã hết vòng đời.
- Consumer phải idempotent theo eventId hoặc khóa nghiệp vụ phù hợp.

Đây là lý do context ứng dụng, event identity và trace identity phải được thiết kế độc lập.

## 9. Kiểm thử tích hợp context

Kiểm thử một hàm `get()` là chưa đủ. Các lỗi thường xuất hiện ở nested scope, executor reuse, exception path và ranh giới reactive/messaging.

### 9.1. Kiểm tra MDC được khôi phục đúng

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class RequestContextMdcTests {

    @Test
    void restoresPreviousMdcValue() {
        MDC.put("requestId", "outer");

        try {
            RequestContext context =
                    new RequestContext("inner", "tenant-a", "vi-VN");

            RequestContextScope.runWith(context, () ->
                    RequestContextMdc.run(() ->
                            assertEquals("inner", MDC.get("requestId"))));

            assertEquals("outer", MDC.get("requestId"));
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Test xác nhận helper không xóa context của scope bên ngoài. Trong suite thực tế, cũng cần kiểm tra trường hợp trước đó không có MDC value.

### 9.2. Kiểm tra task wrapper trên thread khác

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class ScopedTaskPropagationTests {

    void propagatesCapturedRequestContext() throws Exception {
        var context = new RequestContext(
                "req-async", "tenant-a", "vi-VN");

        try (ExecutorService executor =
                     Executors.newSingleThreadExecutor()) {

            RequestContextScope.runWith(context, () -> {
                Runnable wrapped = RequestContextScope.wrap(() ->
                        assertEquals(
                                "req-async",
                                RequestContextScope.current().requestId()));

                Future<?> future = executor.submit(wrapped);

                try {
                    future.get();
                } catch (Exception ex) {
                    throw new RuntimeException(ex);
                }
            });
        }
    }
}
~~~

Ví dụ dùng `ExecutorService` và try-with-resources theo Java hiện đại. Wrapper được tạo **bên trong scope**, do đó đã capture context trước khi submit. Nếu tạo wrapper khi không có binding, worker không tự có request context.

### 9.3. Ma trận kiểm thử cần có

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| C1 | Gọi log trong cùng request scope | MDC chứa request ID đúng |
| C2 | Nested ScopedValue scope | MDC và binding khôi phục giá trị ngoài |
| C3 | Callback ném exception | MDC được restore, ScopedValue hết binding đúng |
| C4 | Submit task trong scope qua wrapper | Worker đọc đúng context đã capture |
| C5 | Submit task khi không có context | Worker không nhận context của task trước |
| C6 | Dùng executor một thread xử lý hai request liên tiếp | Không có request ID bị rò rỉ |
| C7 | Có tracing instrumentation | Span hiện hành hợp lệ và có custom attribute được phép |
| C8 | Không có span hiện hành | Code không tự tạo trace giả hoặc ném lỗi ngoài dự kiến |
| C9 | Chạy Reactor pipeline trên scheduler khác | Context được đọc từ Reactor Context, không phụ thuộc thread |
| C10 | Gọi downstream HTTP/Kafka | Trace headers được instrumentation truyền; correlation ID theo hợp đồng |
| C11 | Replay event sau restart | Event ID ổn định, trace lần replay có thể mới |
| C12 | Request có tenant ID không hợp lệ | Boundary từ chối hoặc xử lý theo policy trước khi bind |

Đối với kiểm thử propagation, cần kiểm tra **thread thực thi thực tế**. Test chạy trên cùng thread không chứng minh executor hoặc reactive pipeline đã được cấu hình đúng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Log có request ID ở controller nhưng mất ở async task | MDC là context theo thread; task chuyển thread | Propagate MDC qua Micrometer/Spring hoặc bridge lại trong worker |
| ScopedValue không đọc được trong worker | Executor không tự kế thừa binding | Chụp context và dùng wrapper để bind trong task |
| Request sau có request ID cũ | MDC không được restore/remove đúng | Dùng try/finally và test executor reuse |
| Trace ID trống nhưng request ID có | Tracing chưa tạo span hoặc logging pattern chưa nhận MDC trace fields | Kiểm tra instrumentation, sampler, exporter và log pattern |
| Có hai trace cho cùng một event retry | Mỗi lần xử lý là một execution mới | Liên kết bằng eventId/correlationId, không ép traceId giống nhau |
| ContextPropagatingTaskDecorator không chuyển ScopedValue | Decorator khôi phục các context có accessor; ScopedValue cần wrapper riêng | Kết hợp `RequestContextScope.wrap` |
| Reactor operator không đọc được ScopedValue | Pipeline đổi thread và dùng Reactor Context | Capture trước khi vào pipeline, ghi vào Reactor Context |
| MDC lộ tenant hoặc token | Đưa dữ liệu nhạy cảm vào log context | Chỉ ghi ID được phép, che/redact và giới hạn quyền |
| Tracing context bị đứt qua Kafka | Producer/consumer không inject/extract propagation headers | Bật instrumentation và kiểm tra headers thực tế |
| Dùng ScopedValue làm security context | Nhầm metadata với authentication/authorization | Giữ Spring Security làm nguồn quyết định bảo mật |
| Dùng mutable object trong context chia sẻ nhiều thread | Binding ổn định nhưng object vẫn mutable | Dùng immutable record hoặc đồng bộ truy cập |

### 10.1. Đừng tạo một “context tổng” chứa mọi thứ

Một record gồm request ID, tenant, trace ID, span ID, access token, toàn bộ HTTP headers và đối tượng request có vẻ tiện, nhưng gây ra nhiều vấn đề:

- Vòng đời dữ liệu quá dài hoặc khó kiểm soát.
- Dữ liệu nhạy cảm bị truyền vào nơi không cần thiết.
- Các module phụ thuộc vào một object khổng lồ.
- Trace ID/span ID bị trùng lặp với tracing system.
- Mutable request object có thể bị sửa từ nhiều thread.

Giữ `RequestContext` nhỏ, bất biến và chỉ chứa metadata ứng dụng cần đọc. Các công cụ logging, tracing, security và messaging tiếp tục quản lý context thuộc miền trách nhiệm của chúng.

## 11. Checklist triển khai production

Trước khi đưa tích hợp vào production, xác minh:

- **Java version:** dùng JDK 25+; `ScopedValue` là API final theo JEP 506, không cần preview flag.
- **Boundary:** context được tạo sau validation/authentication và bind trong scope có giới hạn.
- **Immutability:** record và các trường trong context không chứa state mutable không kiểm soát.
- **Logging:** MDC chỉ chứa các trường được phép; nested value được restore trong `finally`.
- **Tracing:** trace/span ID do Micrometer/OpenTelemetry sở hữu; request ID chỉ là thuộc tính tương quan.
- **Async:** executor thực tế có decorator; ScopedValue được capture/rebind riêng; các accessor Micrometer cần thiết đã được đăng ký.
- **Reactive:** Reactor Context được dùng cho pipeline; không gọi ScopedValue sau thread switch nếu chưa có binding riêng.
- **Security:** Spring Security giữ trách nhiệm authentication/authorization; không log credential.
- **Messaging:** trace propagation và correlation ID có hợp đồng riêng; retry giữ eventId.
- **Testing:** có test exception, thread reuse, nested scope, async và missing context.
- **Performance:** đo overhead của snapshot/decorator và kích thước context theo workload thật.
- **Operations:** log/trace có retention, access control và redaction phù hợp.

## 12. Bài thực hành tổng hợp

Xây dựng một ứng dụng nhỏ có endpoint `POST /orders` và một tác vụ thanh toán bất đồng bộ:

1. Tại request boundary, tạo `RequestContext(requestId, tenantId, locale)` sau khi kiểm tra đầu vào.
2. Bind context bằng `RequestContextScope.runWith`.
3. Bridge request ID vào MDC để log của controller/service/repository có thể tìm kiếm.
4. Khi có span hiện hành, gắn `app.request.id` vào span bằng Micrometer hoặc OpenTelemetry API.
5. Submit payment task qua Spring `ThreadPoolTaskExecutor` có decorator kết hợp ScopedValue wrapper và Micrometer context propagation.
6. Nếu một phần xử lý dùng Reactor, chuyển record vào Reactor Context trước khi pipeline chuyển scheduler.
7. Gửi một event ra broker với eventId ổn định; để tracing instrumentation inject/extract W3C context.
8. Giả lập một lần retry sau khi request gốc kết thúc, rồi đối chiếu eventId/correlationId và trace mới.
9. Viết test chứng minh MDC được restore, worker không nhận nhầm context, và không log token/credential.

**Sản phẩm nghiệm thu:** sơ đồ context flow, mã RequestContextScope, helper MDC, cấu hình executor, một ví dụ span attribute, một reactive Context example, kết quả test C1–C12 và một trace/log đã loại thông tin nhạy cảm. Người học phải giải thích được giá trị nào do ScopedValue sở hữu, giá trị nào do framework sở hữu và cách chúng được liên kết.

## Tài liệu tham khảo chính thức

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): trạng thái final của ScopedValue trong Java 25 và mô hình truyền context.
- [Java SE 25 API — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding theo thread, dynamic scope, rebinding và giới hạn inheritance.
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): decorator hỗ trợ khôi phục logging/observation context qua task executor.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): context propagation, async executor và reactive pipeline.
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): ThreadLocalAccessor, ContextAccessor, ContextRegistry và ContextSnapshot.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing context và tích hợp với Micrometer Observation.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền trace context qua process và protocol.
- [OpenTelemetry Java API — Span](https://opentelemetry.io/docs/languages/java/api/): truy cập span hiện hành và thêm attributes.
- [SLF4J — MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html): put, get, remove, putCloseable và context theo thread.
