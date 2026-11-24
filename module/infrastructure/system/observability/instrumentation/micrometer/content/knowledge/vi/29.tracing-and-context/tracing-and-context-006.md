# Ngữ cảnh hiện hành trên luồng và ranh giới mất ngữ cảnh khi chạy bất đồng bộ

Micrometer Observation thường đặt Observation hiện hành trong một scope gắn với thread đang thực thi. Cách này thuận tiện cho code đồng bộ: các thành phần sâu trong call stack có thể lấy current Observation mà không phải truyền nó qua từng tham số. Nhưng khi công việc chuyển sang thread khác, chẳng hạn qua Executor, @Async, CompletableFuture hoặc Reactor scheduler, thread mới không tự nhận được ThreadLocal của thread gọi.

Nếu không truyền context qua ranh giới bất đồng bộ, log có thể mất request ID, Observation con có thể không còn quan hệ với Observation cha và span có thể bị tách khỏi trace ban đầu. Micrometer Context Propagation cung cấp cơ chế chụp và khôi phục context giữa ThreadLocal, Reactor Context và các loại context khác. Bài học này giải thích nơi context bị mất, cách khôi phục an toàn và cách kiểm thử để tránh rò rỉ context giữa các tác vụ dùng chung thread pool.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao ThreadLocal chỉ gắn với thread hiện tại và không tự đi theo tác vụ bất đồng bộ.
- Nhận biết các ranh giới làm mất current Observation hoặc tracing context.
- Phân biệt context propagation trong cùng tiến trình với trace propagation qua mạng.
- Sử dụng ThreadLocalAccessor, ContextRegistry và ContextSnapshot.
- Bọc ExecutorService bằng ContextExecutorService.
- Cấu hình ContextPropagatingTaskDecorator cho Spring TaskExecutor.
- Sử dụng Reactor Context, contextCapture và automatic context propagation.
- Hiểu việc khôi phục context và dọn ThreadLocal trên thread pool.
- Kiểm thử việc truyền context, khôi phục giá trị cũ và ngăn context rò rỉ.

## 1. Current context thường gắn với thread

Observation có lifecycle riêng, còn Observation.Scope đặt một Observation làm current trong phạm vi thực thi hiện tại. Trong ứng dụng imperative, current Observation thường được quản lý qua ThreadLocal.

Ví dụ một service mở scope:

~~~java
Observation observation = Observation.start(
        "checkout.process",
        observationRegistry
);

try (Observation.Scope scope = observation.openScope()) {
    processPayment();
    createOrder();
} finally {
    observation.stop();
}
~~~

Trong thời gian scope mở, code trên cùng thread có thể gọi:

~~~java
Observation current = observationRegistry.getCurrentObservation();
~~~

và nhận được Observation đang hiện hành. Khi scope đóng, current Observation trước đó được khôi phục.

ThreadLocal giải quyết việc chia sẻ dữ liệu giữa các method chạy trên cùng thread. Nó không phải context gắn với request hoặc task một cách tự động. Khi một tác vụ được chuyển sang thread khác, thread mới có ThreadLocal state riêng.

~~~mermaid
flowchart TD
    A["Thread A: nhận HTTP request"] --> B["Mở Observation scope"]
    B --> C["ThreadLocal = Observation cha"]
    C --> D["Submit task sang Executor"]
    D --> E["Thread B chạy task"]
    E --> F{"Có context propagation?"}
    F -->|"Không"| G["ThreadLocal của B không có Observation cha"]
    F -->|"Có"| H["Khôi phục snapshot trên B"]
    H --> I["Current Observation cha có thể truy xuất"]
    G --> J["Mất parent context / log correlation"]
    I --> K["Tạo Observation con đúng quan hệ"]
~~~

Một số framework có thể tự quản lý context cho một số loại task. Tuy nhiên, không nên giả định mọi Executor, callback hoặc thư viện async đều tự truyền ThreadLocal.

## 2. Vì sao context bị mất khi chạy bất đồng bộ?

Xét luồng gọi:

1. HTTP server nhận request trên thread A.
2. Tracing instrumentation tạo Observation và đặt nó làm current.
3. Ứng dụng submit công việc sang Executor.
4. Executor chạy task trên thread B.
5. Code trên thread B gọi getCurrentObservation().

Nếu chỉ dựa vào ThreadLocal, bước 5 thường trả về null vì thread B không có giá trị đã đặt trên thread A.

Các ranh giới thường gặp:

| Ranh giới | Vì sao context có thể mất |
| --- | --- |
| ExecutorService.submit() | Runnable được chạy trên thread pool khác |
| CompletableFuture.*Async() | Callback có thể chạy trên common pool hoặc executor khác |
| Spring @Async | Method được thực thi bởi AsyncTaskExecutor |
| ScheduledExecutorService | Tác vụ chạy trên scheduler thread |
| Reactor publishOn/subscribeOn | Operator có thể chạy trên thread khác |
| Callback của HTTP client | Callback được gọi trên event-loop hoặc callback thread |
| Message listener | Message được xử lý bởi consumer thread khác |
| Event listener bất đồng bộ | Event handler chạy trên executor riêng |

Context có thể mất theo hai cách:

- Code không còn nhìn thấy current Observation hoặc ThreadLocal values.
- Code tạo Observation mới nhưng không tìm thấy parent context, khiến trace bị đứt quan hệ cha-con.

Ngoài ra, thread pool tái sử dụng thread. Nếu một tác vụ đặt ThreadLocal rồi không dọn sạch, tác vụ kế tiếp có thể nhìn thấy dữ liệu của tác vụ trước. Đây là context leak và có thể làm sai log, trace hoặc thông tin tenant.

### InheritableThreadLocal không giải quyết đúng bài toán thread pool

InheritableThreadLocal sao chép giá trị khi thread con được tạo. Thread pool thường tạo thread trước khi request đến và tái sử dụng chúng cho nhiều tác vụ. Vì vậy, giá trị không được sao chép tại thời điểm submit và có thể trở nên cũ hoặc sai.

Không dùng InheritableThreadLocal như cơ chế propagation mặc định cho Executor. Cần chụp context tại thời điểm submit và khôi phục nó quanh lúc thực thi task.

## 3. Phân biệt context propagation và trace propagation qua mạng

Hai khái niệm có liên quan nhưng xử lý hai ranh giới khác nhau.

**Context propagation trong tiến trình** chuyển context giữa các cơ chế nội bộ như ThreadLocal, Reactor Context và executor task. Micrometer Context Propagation hỗ trợ việc này bằng accessor và snapshot.

**Trace propagation qua mạng** truyền trace context qua HTTP, messaging hoặc RPC giữa các process. Micrometer Tracing dùng propagator để inject và extract các header như W3C traceparent hoặc B3.

| Tiêu chí | In-process context propagation | Cross-process trace propagation |
| --- | --- | --- |
| Ranh giới | Thread, executor, reactive operator | HTTP, RPC, message broker |
| Dữ liệu thường gặp | Current Observation, MDC, request context | Trace ID, span ID, baggage được phép truyền |
| Cơ chế | ThreadLocalAccessor, ContextSnapshot, Reactor Context | Propagator, SenderContext, ReceiverContext, headers |
| Thư viện chính | micrometer-context-propagation | Micrometer Tracing bridge và propagator |
| Lỗi điển hình | Task async không thấy parent Observation | Service nhận request tạo trace mới thay vì nối vào trace cha |

Context Propagation không tự gửi trace header qua HTTP. Ngược lại, việc HTTP client đã inject traceparent không bảo đảm callback chạy trên thread khác vẫn có current Observation. Cần cấu hình đúng cả hai ranh giới khi ứng dụng sử dụng chúng.

## 4. Các thành phần của Micrometer Context Propagation

Thư viện `io.micrometer:context-propagation` cung cấp các abstraction sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| ThreadLocalAccessor | Đọc, đặt và xóa một giá trị ThreadLocal |
| ContextAccessor | Đọc và ghi dữ liệu từ một context dạng map |
| ContextRegistry | Quản lý các accessor được hỗ trợ |
| ContextSnapshot | Giữ các giá trị context đã chụp và khôi phục chúng |
| ContextSnapshotFactory | Tạo snapshot từ các accessor và context đã đăng ký |
| ContextSnapshot.Scope | Khôi phục trạng thái trước đó khi đóng scope |

Luồng tổng quát:

~~~mermaid
flowchart LR
    A["ThreadLocal / Reactor Context"] --> B["ThreadLocalAccessor / ContextAccessor"]
    B --> C["ContextRegistry"]
    C --> D["ContextSnapshotFactory"]
    D --> E["ContextSnapshot"]
    E --> F["Executor / callback / operator"]
    F --> G["Khôi phục context trong scope"]
    G --> H["Chạy task"]
    H --> I["Đóng snapshot scope"]
    I --> J["Khôi phục trạng thái trước task"]
~~~

Snapshot chỉ chứa những giá trị mà accessor có thể đọc tại thời điểm capture. Nếu một ThreadLocal không có accessor tương ứng, Context Propagation không biết cách đọc hoặc khôi phục nó.

Khi task kết thúc, scope của snapshot khôi phục các giá trị trước đó trên thread đích. Nếu thread đích trước đó không có giá trị, accessor sẽ được gọi để xóa giá trị vừa khôi phục. Điều này ngăn dữ liệu của task hiện tại rò rỉ sang task kế tiếp.

## 5. Đăng ký ThreadLocalAccessor cho context riêng

Framework có thể cung cấp accessor cho Observation, tracing hoặc logging. Với ThreadLocal do ứng dụng tự tạo, cần triển khai ThreadLocalAccessor.

Ví dụ một request context đơn giản:

~~~java
public final class RequestContextHolder {

    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    private RequestContextHolder() {
    }

    public static String get() {
        return REQUEST_ID.get();
    }

    public static void set(String requestId) {
        REQUEST_ID.set(requestId);
    }

    public static void clear() {
        REQUEST_ID.remove();
    }
}
~~~

Accessor tương ứng:

~~~java
import io.micrometer.context.ThreadLocalAccessor;

public final class RequestIdThreadLocalAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "app.requestId";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return RequestContextHolder.get();
    }

    @Override
    public void setValue(String value) {
        RequestContextHolder.set(value);
    }

    @Override
    public void setValue() {
        RequestContextHolder.clear();
    }
}
~~~

Ba thao tác có ý nghĩa rõ ràng:

- `key()` trả về khóa nhận diện context.
- `getValue()` đọc giá trị trên thread hiện tại.
- `setValue(value)` khôi phục giá trị đã capture.
- `setValue()` không tham số xóa ThreadLocal khi snapshot không có giá trị tương ứng hoặc khi cần khôi phục trạng thái rỗng.

Khóa phải ổn định và không trùng với accessor khác. Accessor cần xử lý cả việc đặt giá trị lẫn xóa giá trị; nếu chỉ có set mà không có clear, thread pool có nguy cơ giữ lại dữ liệu cũ.

Không đăng ký ThreadLocal chứa password, access token, session secret hoặc dữ liệu cá nhân nếu không có yêu cầu rõ ràng và chính sách bảo vệ phù hợp. Context propagation có thể đưa dữ liệu đến nhiều thread và callback hơn dự kiến.

## 6. Chụp và khôi phục context bằng ContextSnapshot

Sau khi đăng ký accessor, có thể tạo ContextSnapshotFactory và capture các giá trị hiện hành:

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

ContextRegistry contextRegistry = new ContextRegistry();
contextRegistry.registerThreadLocalAccessor(
        new RequestIdThreadLocalAccessor()
);

ContextSnapshotFactory snapshotFactory =
        ContextSnapshotFactory.builder()
                .contextRegistry(contextRegistry)
                .clearMissing(true)
                .build();
~~~

Trong ví dụ này, `clearMissing(true)` yêu cầu snapshot xóa các ThreadLocal đã đăng ký nhưng không có giá trị trong snapshot khi mở scope. Khi scope đóng, giá trị trước đó của worker thread được khôi phục. Tùy chính sách ứng dụng, có thể để mặc định `false` nếu muốn giữ nguyên các ThreadLocal không có trong snapshot; với context request hoặc tenant trên thread pool, cần cân nhắc rõ hành vi này.

Tại thread gọi, đặt request ID và capture snapshot:

~~~java
RequestContextHolder.set("req-42");

ContextSnapshot snapshot = snapshotFactory.captureAll();
~~~

Khôi phục snapshot quanh một đoạn code:

~~~java
try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
    System.out.println(RequestContextHolder.get()); // req-42
}
~~~

Khi scope đóng, giá trị trước đó trên thread hiện tại được khôi phục. Nếu thread không có request ID trước đó, ThreadLocal sẽ được xóa.

Snapshot là ảnh chụp tại thời điểm capture. Nếu request ID thay đổi sau khi capture, snapshot không tự cập nhật. Hãy capture tại đúng ranh giới submit hoặc thực thi cần truyền context.

Có thể bọc Runnable trực tiếp:

~~~java
ContextSnapshot snapshot = snapshotFactory.captureAll();

executor.execute(snapshot.wrap(() -> {
    processRequest();
}));
~~~

`snapshot.wrap(...)` tạo Runnable có scope khôi phục context trước khi chạy và dọn dẹp sau khi Runnable kết thúc, kể cả khi code ném exception.

## 7. Bọc ExecutorService bằng ContextExecutorService

Nếu nhiều task dùng cùng ExecutorService, có thể bọc executor một lần:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import io.micrometer.context.ContextExecutorService;

ExecutorService delegate = Executors.newFixedThreadPool(4);

ExecutorService contextAwareExecutor =
        ContextExecutorService.wrap(delegate, snapshotFactory);
~~~

ContextExecutorService capture ThreadLocal values khi task được submit và khôi phục chúng khi task chạy. Ví dụ:

Overload nhận `ContextSnapshotFactory` ở trên capture ThreadLocal values. Nếu cần capture thêm dữ liệu từ một context object khác, dùng overload nhận `Supplier<ContextSnapshot>` và gọi `snapshotFactory.captureAll(contextObject)` trong supplier.

~~~java
RequestContextHolder.set("req-42");

Future<String> future = contextAwareExecutor.submit(
        RequestContextHolder::get
);

String requestId = future.get(); // req-42
~~~

Sau khi task kết thúc, snapshot scope khôi phục trạng thái ThreadLocal trước đó của worker thread. Khi không có request context trong lần submit kế tiếp, task tiếp theo không được nhìn thấy request ID của task trước.

Có thể dùng cùng executor cho CompletableFuture:

~~~java
RequestContextHolder.set("req-42");

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                RequestContextHolder::get,
                contextAwareExecutor
        );
~~~

Luôn truyền executor đã bọc vào các method async cần propagation. Các method như `supplyAsync(supplier)` hoặc `thenApplyAsync(function)` không nhận executor có thể chạy trên ForkJoinPool.commonPool(), nằm ngoài wrapper đã cấu hình.

### Vòng đời của executor

Executor wrapper có cùng vòng đời quản lý với executor gốc. Khi ứng dụng dừng, hãy shutdown executor theo cơ chế quản lý tài nguyên của ứng dụng. Không tạo một thread pool mới cho mỗi request.

Overhead của capture và restore tăng theo số accessor và số task. Với task rất nhỏ hoặc lưu lượng cao, hãy đo chi phí thực tế và chỉ propagate những context cần thiết.

## 8. Dùng ContextPropagatingTaskDecorator trong Spring

Spring Framework cung cấp `ContextPropagatingTaskDecorator` từ Spring Framework 6.1. Decorator này chụp context khi task được schedule và khôi phục context trong lúc task chạy.

Với ThreadPoolTaskExecutor tự cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator()
        );
        return executor;
    }
}
~~~

TaskDecorator bọc Runnable trước khi executor thực thi. Khi task kết thúc, snapshot scope khôi phục context trước đó trên worker thread.

Nếu dùng Spring Boot với AsyncTaskExecutor auto-configured, phiên bản Boot hiện hành cung cấp property:

~~~properties
spring.task.execution.propagate-context=true
~~~

Property này bật propagation cho task execution do auto-configured executor quản lý. Nếu ứng dụng tự tạo executor, hãy gắn ContextPropagatingTaskDecorator vào executor đó; chỉ khai báo một bean TaskDecorator không đảm bảo mọi executor tùy chỉnh đều tự sử dụng nó.

Với Spring Boot 3.x, kiểm tra tài liệu phiên bản cụ thể. Các phiên bản trước khi có property trên thường cần cấu hình TaskDecorator trực tiếp. ContextPropagatingTaskDecorator yêu cầu Spring Framework 6.1 trở lên.

### Khi dùng @Async

Ví dụ:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    @Async("applicationTaskExecutor")
    public CompletableFuture<Void> sendNotification() {
        // Current Observation và context đã được executor khôi phục.
        sendEmail();
        return CompletableFuture.completedFuture(null);
    }

    private void sendEmail() {
        // Gửi email
    }
}
~~~

Method @Async chỉ được propagation nếu executor được chọn có decorator hoặc được bật cấu hình tương ứng. Nếu method sử dụng một executor khác, hãy kiểm tra executor đó riêng.

## 9. Observation context và Micrometer Tracing

Observation.Scope thường làm current Observation có thể truy xuất trên thread. Để current Observation được khôi phục qua executor, cần có accessor tương ứng trong ContextRegistry.

Trong ứng dụng Spring Boot, các tích hợp observability được hỗ trợ có thể cấu hình context propagation cho Observation. Với ứng dụng tự lắp ghép registry, hãy xác nhận Observation accessor đã được đăng ký và trỏ tới ObservationRegistry mà ứng dụng sử dụng.

Trong các phiên bản Micrometer yêu cầu gắn registry vào accessor singleton, có thể cấu hình như sau trước khi capture context:

~~~java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;

ObservationThreadLocalAccessor.getInstance()
        .setObservationRegistry(observationRegistry);
~~~

API và yêu cầu khởi tạo accessor phụ thuộc phiên bản Micrometer và cách tích hợp. Spring Boot có thể đã cấu hình phần này; không đăng ký lặp hoặc tạo accessor mới nếu framework đã quản lý nó.

Micrometer Tracing còn có context riêng cho span và baggage. Các span được quản lý bởi Observation và span được tạo thủ công có thể có yêu cầu accessor khác nhau. Nếu tự tạo span hoặc baggage, tham khảo tracing bridge để đăng ký accessor tương ứng, chẳng hạn ObservationAwareSpanThreadLocalAccessor hoặc ObservationAwareBaggageThreadLocalAccessor.

Không mặc định rằng đăng ký một request ID accessor sẽ tự truyền cả Observation, Span, Baggage và MDC. Mỗi loại context cần accessor hoặc integration phù hợp.

### Không giữ Scope của thread gọi mở trong lúc worker chạy

Không làm như sau:

~~~java
Observation.Scope scope = observation.openScope();

executor.submit(() -> {
    // Không đóng scope của thread gọi từ thread worker.
    process();
});
~~~

Scope được mở trên thread gọi và phải đóng trên thread đó. ContextSnapshot hoặc TaskDecorator tạo scope khôi phục riêng trên thread worker. Hai scope có vòng đời độc lập.

Cách phù hợp là:

~~~java
try (Observation.Scope scope = observation.openScope()) {
    contextAwareExecutor.submit(() -> process());
}
~~~

Scope trên thread gọi đóng ngay sau khi submit hoàn tất. Executor wrapper capture context tại thời điểm submit và mở scope tương ứng trong worker thread.

## 10. Reactor Context là nguồn context của reactive pipeline

Reactive pipeline không gắn với một thread cố định. Một operator có thể chạy trên thread khác sau publishOn(), subscribeOn() hoặc một async boundary.

Reactor cung cấp Context gắn với subscription. Context là cấu trúc immutable, được đọc qua ContextView và truyền qua các operator theo quy tắc của Reactor. Với reactive code, nên dùng Reactor Context để lưu dữ liệu theo subscription thay vì dựa vào ThreadLocal như nguồn context chính.

Ví dụ:

~~~java
private static final String REQUEST_ID = "requestId";

Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get(REQUEST_ID))
).contextWrite(context ->
        context.put(REQUEST_ID, "req-42")
);
~~~

Dù pipeline đổi thread, giá trị trong Reactor Context vẫn thuộc subscription và có thể được đọc qua deferContextual().

Micrometer Context Propagation giúp chuyển đổi giữa Reactor Context và ThreadLocal. Khi có cả `reactor-core` và `io.micrometer:context-propagation`, Reactor tự đăng ký ReactorContextAccessor thông qua ServiceLoader.

## 11. Reactor có hai chế độ khôi phục ThreadLocal

Reactor hỗ trợ hai chế độ tích hợp với Micrometer Context Propagation:

| Chế độ | Hành vi |
| --- | --- |
| Limited/default mode | Khôi phục ThreadLocal trong một số operator như handle và tap khi context đã được capture |
| Automatic mode | Khôi phục ThreadLocal xuyên các operator và ranh giới thread dựa trên Reactor Context |

### Limited mode và contextCapture()

Nếu cần chụp ThreadLocal ở thời điểm subscribe rồi đưa giá trị vào Reactor Context, dùng contextCapture():

~~~java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "missing"))
).contextCapture();
~~~

Trong limited mode, Reactor khôi phục ThreadLocal trong các operator hỗ trợ như handle và tap. Các callback khác không tự động nhìn thấy ThreadLocal đã capture. Vì vậy, code reactive nên đọc trực tiếp Reactor Context khi có thể.

### Automatic mode

Có thể bật automatic context propagation khi ứng dụng khởi động:

~~~java
Hooks.enableAutomaticContextPropagation();
~~~

Trong Spring Boot, có thể cấu hình:

~~~properties
spring.reactor.context-propagation=auto
~~~

Automatic mode áp dụng cho các subscription mới sau khi hook được bật. Vì vậy, nên bật từ giai đoạn khởi động ứng dụng, trước khi tạo subscription cần propagation.

Automatic mode khôi phục ThreadLocal từ Reactor Context khi callback chạy. Khi một key không có trong Context, accessor tương ứng có thể được gọi để xóa ThreadLocal trên thread hiện tại. Việc dọn dẹp này ngăn giá trị của subscription trước rò sang subscription sau khi thread được tái sử dụng.

Automatic mode có chi phí. Nó có thể ảnh hưởng hiệu năng tùy số operator, số accessor và đặc điểm pipeline. Hãy benchmark dưới tải gần với production trước khi bật toàn ứng dụng.

### Ghi trực tiếp vào Reactor Context

Nếu giá trị được tạo trong reactive pipeline, dùng contextWrite() để đưa nó vào Context:

~~~java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just("request=" + context.get("requestId"))
).contextWrite(context ->
        context.put("requestId", "req-42")
);
~~~

Nếu giá trị bắt đầu từ ThreadLocal ở imperative code và cần có trong Reactor Context tại subscription, contextCapture() có thể capture các ThreadLocal đã đăng ký accessor. Khi dùng automatic mode cùng blocking terminal operator, Reactor có thể capture context tự động theo cơ chế của phiên bản; không thêm contextCapture() một cách máy móc nếu không cần.

## 12. Ranh giới callback và CompletableFuture

CompletableFuture có các callback đồng bộ và bất đồng bộ:

- thenApply() thường chạy trên thread hoàn tất stage trước đó hoặc thread đăng ký callback tùy trạng thái stage.
- thenApplyAsync() chạy callback trên executor được chỉ định hoặc common pool mặc định.
- whenComplete() có thể chạy trên thread hoàn tất stage.
- whenCompleteAsync() chuyển callback sang executor.

Nếu callback cần current Observation hoặc ThreadLocal context, hãy chỉ định executor đã bọc:

~~~java
CompletableFuture.supplyAsync(
        this::loadOrder,
        contextAwareExecutor
).thenApplyAsync(
        this::calculateTotal,
        contextAwareExecutor
).thenApplyAsync(
        this::createInvoice,
        contextAwareExecutor
);
~~~

Không giả định callback đồng bộ luôn chạy trên thread gốc. Một stage có thể hoàn tất trước khi callback được đăng ký; khi đó callback có thể chạy ngay trên thread đăng ký. Thiết kế đúng nên dựa vào context explicit hoặc executor wrapper, không dựa vào suy đoán thread.

Với callback do thư viện bên ngoài gọi, kiểm tra thread và executor contract của thư viện. Nếu không kiểm soát được executor, có thể capture ContextSnapshot ở thời điểm đăng ký callback rồi wrap callback bằng snapshot.

## 13. Context propagation không thay thế việc tạo Observation con

Propagation đưa context hiện hành sang thread đích để duy trì parent relationship. Nó không tự tạo Observation cho mọi task.

Ví dụ:

~~~java
contextAwareExecutor.submit(() ->
        Observation.createNotStarted(
                "order.persist",
                observationRegistry
        ).observe(this::persistOrder)
);
~~~

Executor wrapper khôi phục parent context. Observation con được tạo bên trong worker sẽ có cơ hội nhận parent Observation hiện hành và tạo quan hệ đúng.

Nếu chỉ khôi phục request ID hoặc MDC mà không khôi phục Observation/Span, log có thể có request ID nhưng trace vẫn bị đứt. Nếu chỉ khôi phục Observation mà không đăng ký accessor cho MDC riêng của ứng dụng, log có thể thiếu request ID. Hãy xác định chính xác loại context cần truyền.

## 14. Kiểm thử context propagation và ngăn rò rỉ

Một test tốt nên xác nhận ba trạng thái:

1. Task nhận được context đã capture.
2. Khi task kết thúc, worker thread trở về trạng thái trước đó.
3. Task kế tiếp không có context không nhìn thấy dữ liệu của task trước.

Ví dụ với JUnit và một executor đơn luồng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import org.junit.jupiter.api.Test;

class ContextPropagationTest {

    @Test
    void propagatesContextAndClearsItAfterTask() throws Exception {
        ContextRegistry registry = new ContextRegistry();
        registry.registerThreadLocalAccessor(
                new RequestIdThreadLocalAccessor()
        );

        ContextSnapshotFactory factory =
                ContextSnapshotFactory.builder()
                        .contextRegistry(registry)
                        .clearMissing(true)
                        .build();

        ExecutorService delegate = Executors.newSingleThreadExecutor();
        ExecutorService executor =
                ContextExecutorService.wrap(delegate, factory);

        try {
            RequestContextHolder.set("req-42");

            String propagated = executor.submit(
                    RequestContextHolder::get
            ).get(5, TimeUnit.SECONDS);

            assertThat(propagated).isEqualTo("req-42");

            RequestContextHolder.clear();

            String nextTaskValue = executor.submit(
                    RequestContextHolder::get
            ).get(5, TimeUnit.SECONDS);

            assertThat(nextTaskValue).isNull();
        } finally {
            RequestContextHolder.clear();
            executor.shutdown();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Executor đơn luồng giúp hai task dùng lại cùng một worker thread. Task thứ hai được submit khi thread gọi không còn request ID; kết quả null xác nhận task đầu không để lại context trên worker.

### Kiểm thử current Observation

Với Spring context đã cấu hình Observation propagation, có thể tạo Observation cha, mở scope trên thread gọi và submit task qua executor đã propagation. Trong worker, kiểm tra:

~~~java
Observation current = observationRegistry.getCurrentObservation();
assertThat(current).isSameAs(parentObservation);
~~~

Sau khi task kết thúc, kiểm tra thread gọi vẫn giữ parent trong scope của nó. Sau khi đóng scope, current Observation trên thread gọi phải trở về giá trị trước đó.

Test này cần Observation ThreadLocalAccessor được đăng ký trên ContextRegistry đang dùng. Nếu ứng dụng có tracing bridge, kiểm tra thêm current span và parent span ID bằng test tracer hoặc exporter thử nghiệm.

### Kiểm thử Reactor

Dùng StepVerifier để kiểm tra giá trị trong Reactor Context và ThreadLocal được khôi phục ở operator phù hợp. Test cả limited mode lẫn automatic mode theo cấu hình production. Nếu bật hook toàn cục, hãy đảm bảo test không phụ thuộc thứ tự chạy và không làm rò hook sang test khác; có thể dùng hook cleanup phù hợp sau test nếu phiên bản Reactor hỗ trợ.

## 15. Chẩn đoán khi context bị mất

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| getCurrentObservation() trả null trong worker | Observation ThreadLocal chưa được propagation | Kiểm tra accessor và executor wrapper |
| Log mất request ID sau @Async | Executor không có TaskDecorator | Kiểm tra AsyncTaskExecutor và TaskDecorator |
| Task B thấy request ID của task A | ThreadLocal không được clear hoặc restore | Kiểm tra ThreadLocalAccessor.setValue() không tham số |
| Trace bị tách parent-child sau CompletableFuture | Callback chạy trên executor không được bọc | Truyền context-aware executor cho mọi async stage |
| Reactor operator thấy Context nhưng ThreadLocal null | Đang ở limited mode hoặc operator không hỗ trợ restore | Dùng deferContextual hoặc cấu hình automatic mode |
| Reactor tự động propagation không hoạt động | Hook bật sau khi subscription đã tạo | Bật hook lúc khởi động |
| Context có ở thread gọi nhưng không ở task | Snapshot capture sai thời điểm | Capture tại thời điểm submit |
| Custom ThreadLocal không được truyền | Chưa đăng ký ThreadLocalAccessor | Đăng ký accessor đúng ContextRegistry |
| Observation có nhưng baggage mất | Chưa đăng ký baggage accessor phù hợp | Kiểm tra Micrometer Tracing configuration |
| Hiệu năng giảm sau khi bật automatic mode | Chi phí capture/restore ở nhiều operator | Benchmark và giới hạn context cần truyền |

## 16. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ ThreadLocal tự truyền qua thread pool | Worker không thấy context | Dùng Context Propagation |
| Dùng InheritableThreadLocal với pool | Thread có thể giữ context cũ hoặc không nhận context mới | Capture tại thời điểm submit |
| Capture snapshot quá sớm | Task nhận giá trị đã cũ | Capture sát thời điểm submit |
| Chỉ cài accessor nhưng không đăng ký | Context Propagation không biết cách đọc giá trị | Đăng ký accessor vào ContextRegistry |
| Accessor không có thao tác clear | Context task trước rò sang task sau | Implement setValue() không tham số |
| Đóng Observation.Scope từ worker | Vi phạm thread ownership | Scope thread gọi và scope snapshot ở worker độc lập |
| Dùng common pool mặc định | Callback chạy ngoài executor đã bọc | Truyền context-aware executor |
| Chỉ propagation request ID | Trace vẫn có thể mất parent | Propagate Observation/Span accessor phù hợp |
| Dùng ThreadLocal làm nguồn context chính trong Reactor | Context biến mất khi scheduler đổi thread | Dùng Reactor Context |
| Bật automatic propagation mà không đo hiệu năng | Tăng chi phí trên pipeline nhiều operator | Benchmark và chỉ bật khi cần |
| Nghĩ context propagation tự gửi trace header | Trace không nối qua process | Cấu hình tracing propagator riêng |

## 17. Checklist triển khai

Trước khi đưa async context propagation vào production, hãy xác nhận:

1. Đã xác định context nào cần truyền: Observation, Span, baggage, MDC hay request metadata?
2. Mỗi ThreadLocal cần truyền có ThreadLocalAccessor tương ứng không?
3. Accessor đã được đăng ký trên đúng ContextRegistry chưa?
4. Snapshot được capture tại đúng thời điểm submit chưa?
5. ExecutorService hoặc TaskExecutor có wrapper/decorator không?
6. Mọi CompletableFuture async stage quan trọng có dùng executor đã bọc không?
7. Spring @Async đang dùng đúng AsyncTaskExecutor có propagation không?
8. Reactive pipeline có dùng Reactor Context làm nguồn context chính không?
9. Automatic context propagation có được bật trước subscription mới không?
10. Context được khôi phục và dọn sạch sau mỗi task không?
11. Test đã xác nhận task kế tiếp không thấy dữ liệu task trước chưa?
12. Trace propagation qua HTTP/RPC đã được cấu hình riêng chưa?
13. Overhead của propagation đã được đo dưới tải dự kiến chưa?

## Kết luận

Current Observation và nhiều context quan sát khác thường gắn với thread hiện tại. Khi công việc chuyển qua Executor, @Async, CompletableFuture hoặc Reactor scheduler, ThreadLocal không tự đi theo tác vụ. Micrometer Context Propagation giải quyết ranh giới này bằng ThreadLocalAccessor, ContextRegistry và ContextSnapshot; Executor wrapper hoặc TaskDecorator capture context khi submit và khôi phục nó quanh lúc task chạy.

Với reactive code, hãy dùng Reactor Context làm nguồn context theo subscription và chỉ khôi phục ThreadLocal khi có nhu cầu tương thích. Luôn đóng scope để khôi phục trạng thái trước đó, đăng ký accessor có thao tác clear và kiểm thử việc tái sử dụng thread. Context propagation trong tiến trình cũng cần được cấu hình riêng với trace propagation qua mạng. Khi các ranh giới này được xử lý đúng, log, Observation và span có thể giữ mối liên hệ xuyên suốt cả luồng đồng bộ lẫn bất đồng bộ.

## Tài liệu tham khảo

- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html) — ThreadLocalAccessor, ContextAccessor, ContextRegistry và ContextSnapshot.
- [Micrometer Context Propagation — Usage](https://docs.micrometer.io/context-propagation/reference/usage.html) — đăng ký accessor, capture snapshot và khôi phục ThreadLocal.
- [Micrometer Observation — Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html) — truyền Observation qua Executor và ranh giới reactive.
- [Project Reactor — Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html) — Reactor Context, contextCapture, limited mode và automatic mode.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — cấu hình propagation cho @Async, AsyncTaskExecutor và Reactor.
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html) — TaskDecorator khôi phục Observation và logging context cho task.
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html) — accessor cho span và baggage.
