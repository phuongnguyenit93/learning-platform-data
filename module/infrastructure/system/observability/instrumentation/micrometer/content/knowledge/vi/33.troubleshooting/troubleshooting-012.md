# Mất quan hệ quan sát khi đổi luồng hoặc đăng ký reactive

Khi một thao tác chuyển sang thread khác hoặc đi qua Reactor pipeline, trace có thể bị tách thành trace mới, log không còn trace ID, hoặc lời gọi ObservationRegistry.getCurrentObservation() trả về null. Nguyên nhân thường là ứng dụng đang dựa vào ThreadLocal như thể nó là context dùng chung cho toàn bộ tác vụ. ThreadLocal chỉ gắn với thread hiện tại; executor và Reactor có thể chạy phần tiếp theo trên một thread khác.

Micrometer Context Propagation giúp chuyển context giữa các cơ chế lưu trữ. Với code imperative, thư viện chụp và khôi phục ThreadLocal quanh task. Với Reactor, Context là nơi lưu context theo subscription; ThreadLocal chỉ được khôi phục khi operator hoặc chế độ propagation yêu cầu. Muốn giữ quan hệ cha–con, cần truyền đúng Observation cha và quản lý vòng đời Observation theo thời gian thực thi bất đồng bộ.

## 1. Dấu hiệu và nguyên nhân thường gặp

Các triệu chứng thường thấy:

- Log trước khi submit task có trace ID, nhưng log trong executor không có trace ID hoặc span ID.
- Một request tạo nhiều trace gốc thay vì một trace có các span con.
- ObservationRegistry.getCurrentObservation() có giá trị trong controller nhưng trả về null sau publishOn, subscribeOn hoặc CompletableFuture.
- Metric vẫn được ghi, nhưng span không có parent đúng hoặc baggage không xuất hiện ở thread khác.
- Observation kết thúc ngay sau khi method trả về Mono/Flux, trong khi publisher vẫn chưa phát dữ liệu.
- Khi tải cao, log của request này xuất hiện context của request khác do ThreadLocal không được khôi phục hoặc xóa đúng cách.

Không phải mọi trường hợp đều là lỗi propagation. Một Observation có thể không được tạo vì registry là no-op, predicate loại Observation, handler chưa đăng ký hoặc instrumentation chưa được kích hoạt. Hãy kiểm tra cả việc tạo Observation và việc truyền context.

## 2. Phân biệt Observation, Scope, ThreadLocal và Reactor Context

Bốn khái niệm này liên quan với nhau nhưng không thay thế cho nhau:

| Thành phần | Phạm vi sống | Vai trò |
| --- | --- | --- |
| Observation | Từ lúc start đến stop. | Đại diện cho một thao tác được đo; giữ context, metadata, lỗi và quan hệ cha–con. |
| Observation.Scope | Trong một đoạn thực thi đồng bộ trên thread hiện tại. | Đặt Observation thành current để handler có thể gắn span, MDC hoặc context vào ThreadLocal. |
| ThreadLocal | Một thread cụ thể. | Cho phép thư viện đọc context hiện tại mà không phải truyền tham số qua mọi lời gọi. |
| Reactor Context | Một subscription. | Lưu dữ liệu gắn với subscriber, không phụ thuộc thread thực thi. |

Sự khác biệt quan trọng là Observation có thể sống lâu hơn một thread, còn Scope chỉ mở trên thread nơi nó được tạo. Mở scope rồi submit task không khiến scope tự chuyển sang worker thread.

~~~mermaid
flowchart TD
    A[Observation cha] --> B[Scope trên thread yêu cầu]
    B --> C[ThreadLocal current Observation]
    C --> D[Chụp ContextSnapshot]
    D --> E[Executor worker thread]
    E --> F[Khôi phục ThreadLocal trong task]
    A --> G[Reactor Context của subscription]
    G --> H[Scheduler đổi thread]
    H --> I[Khôi phục ThreadLocal theo accessor]
    F --> J[Observation con có parent đúng]
    I --> J
~~~

Khi code chạy đồng bộ, Observation.observe(...) hoặc Observation.scoped(...) thường đủ. Khi code đi qua executor hoặc reactive chain, phải dùng cơ chế propagation phù hợp với loại context đó.

## 3. Vì sao đổi thread làm mất context?

Ví dụ đơn giản:

~~~java
Observation parent = Observation.start("checkout", registry);

try (Observation.Scope scope = parent.openScope()) {
    executor.submit(() -> {
        // Không thể giả định current Observation vẫn là parent.
        log.info("Current Observation on worker: {}",
                registry.getCurrentObservation());
        processPayment();
    });
}
finally {
    parent.stop();
}
~~~

openScope() đặt parent vào ThreadLocal của thread submit task. executor.submit() chỉ chuyển một Runnable/Callable cho worker. Worker có ThreadLocal riêng; nó không tự nhận giá trị của thread gửi task.

Đoạn code còn có lỗi vòng đời: parent có thể bị stop ngay sau khi submit, trước khi worker hoàn tất. Dù propagation được cấu hình, một task con không nên tiếp tục dùng một parent Observation đã kết thúc. Hãy giữ parent sống đến khi tác vụ bất đồng bộ hoàn tất, hoặc tạo một quan hệ trace mới theo đúng ranh giới nghiệp vụ.

## 4. Context Propagation cung cấp những gì?

Micrometer Context Propagation cung cấp bốn thành phần:

| API | Công việc |
| --- | --- |
| ThreadLocalAccessor | Đọc, khôi phục và xóa một giá trị ThreadLocal theo một key ổn định. |
| ContextAccessor | Đọc và ghi dữ liệu từ một cơ chế context dạng map. |
| ContextRegistry | Đăng ký các accessor để thư viện biết context nào có thể được truyền. |
| ContextSnapshot / ContextSnapshotFactory | Chụp giá trị context tại một thời điểm và khôi phục chúng quanh một đoạn thực thi. |

Reactor tích hợp SPI này từ Reactor Core 3.5.0. Khi có cả reactor-core và io.micrometer:context-propagation, ReactorContextAccessor được nạp qua ServiceLoader; ứng dụng không cần tự đăng ký accessor cho Reactor Context.

Nếu các dependency chưa có sẵn qua Spring Boot starter hoặc BOM, các artifact thường cần gồm:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-core-micrometer</artifactId>
</dependency>
~~~

Reactor Context Propagation SPI có từ Reactor Core 3.5.0; automatic mode có từ Reactor 3.5.3. Hãy dùng Spring Boot/Reactor BOM để chọn các phiên bản tương thích thay vì nâng riêng từng artifact.

Với Micrometer Observation, ObservationThreadLocalAccessor là accessor dựng sẵn để truyền Observation hiện tại. Nếu ứng dụng có ThreadLocal riêng như tenant context hoặc correlation ID tùy biến, cần đăng ký accessor tương ứng. ObservationThreadLocalAccessor được cung cấp qua ServiceLoader trong các bản Micrometer Observation tương thích. Khi dùng ObservationRegistry tự tạo, gọi setObservationRegistry(...) để accessor dùng đúng registry. Spring Boot thường cấu hình registry và accessor trong observability infrastructure của nó; tránh đăng ký thêm một accessor trùng key.

## 5. Truyền context qua ExecutorService

Với code imperative, dùng ContextExecutorService để chụp context lúc submit và khôi phục nó khi task chạy:

~~~java
import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CheckoutAsyncService {

    private final ObservationRegistry registry;
    private final ExecutorService executor;

    public CheckoutAsyncService(ObservationRegistry registry) {
        this.registry = registry;
        ObservationThreadLocalAccessor.getInstance()
                .setObservationRegistry(registry);

        ExecutorService delegate = Executors.newFixedThreadPool(4);
        ContextSnapshotFactory snapshotFactory =
                ContextSnapshotFactory.builder().build();
        this.executor = ContextExecutorService.wrap(
                delegate, snapshotFactory);
    }

    public CompletableFuture<Void> processAsync() {
        Observation parent = Observation.start("checkout", registry);

        CompletableFuture<Void> future;
        try (Observation.Scope scope = parent.openScope()) {
            future = CompletableFuture.runAsync(() -> {
                if (registry.getCurrentObservation() != parent) {
                    throw new IllegalStateException(
                            "Parent Observation was not propagated");
                }

                Observation.createNotStarted("payment.authorize", registry)
                        .observe(this::authorizePayment);
            }, executor);
        }
        catch (RuntimeException exception) {
            parent.error(exception);
            parent.stop();
            throw exception;
        }

        return future.whenComplete((result, error) -> {
            if (error != null) {
                parent.error(error);
            }
            parent.stop();
        });
    }

    private void authorizePayment() {
        // Execute the work measured by the child Observation.
    }
}
~~~

Ở đây, executor phải là ContextExecutorService đã được wrap. Snapshot được chụp khi task được submit trong scope của parent. Callback whenComplete chịu trách nhiệm kết thúc parent sau khi task kết thúc.

Đoạn code trên minh họa nguyên tắc; trong ứng dụng thực tế, hãy quản lý executor như tài nguyên vòng đời ứng dụng, đóng nó khi ứng dụng dừng và tránh tạo executor mới cho mỗi request. Nếu task có nhiều nhánh bất đồng bộ, parent chỉ nên stop khi toàn bộ nhánh thuộc thao tác đó đã hoàn tất.

## 6. Truyền context với Spring @Async

Spring Framework cung cấp ContextPropagatingTaskDecorator từ Spring Framework 6.1. Decorator chụp context khi task được submit và khôi phục ThreadLocal quanh task trên worker thread.

Ví dụ với executor tự cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean
    TaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("checkout-async-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Phương thức @Async cần sử dụng đúng executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
class NotificationService {

    @Async("applicationTaskExecutor")
    public CompletableFuture<Void> sendReceipt() {
        deliverReceipt();
        return CompletableFuture.completedFuture(null);
    }

    private void deliverReceipt() {
        // Send or queue the receipt.
    }
}
~~~

Với Spring Boot 4.x, executor do Boot tự cấu hình có thể bật propagation bằng:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Với executor tự cấu hình, hãy gắn ContextPropagatingTaskDecorator trực tiếp vào executor đó. Cấu hình property và auto-configuration có thể khác giữa các dòng Spring Boot; kiểm tra tài liệu của đúng phiên bản đang dùng. Spring Boot 3.x có thể cần cấu hình decorator thủ công cho executor được dùng bởi @Async.

ContextPropagatingTaskDecorator có chi phí chụp và khôi phục context. Nếu executor chạy hàng triệu task rất nhỏ, đo overhead trong tải thực tế và chỉ truyền các giá trị cần thiết.

## 7. Đăng ký accessor cho ThreadLocal tùy biến

Context Propagation chỉ truyền những giá trị có accessor đã đăng ký. Ví dụ ứng dụng có một tenant context:

~~~java
public final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void set(String tenant) {
        CURRENT.set(tenant);
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

Đăng ký accessor:

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ThreadLocalAccessor;

public final class TenantThreadLocalAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "application.tenant";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return TenantContext.get();
    }

    @Override
    public void setValue(String value) {
        TenantContext.set(value);
    }

    @Override
    public void setValue() {
        TenantContext.clear();
    }
}
~~~

Đăng ký một lần lúc khởi động:

~~~java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantThreadLocalAccessor());
~~~

setValue() không tham số phải xóa giá trị hiện tại. Nếu bỏ qua thao tác này, worker thread có thể giữ tenant cũ sau khi task kết thúc và tái sử dụng thread cho request khác.

Không đăng ký lại cùng accessor nhiều lần ở mỗi request. Key phải ổn định và không xung đột với key của thư viện khác. Không truyền mật khẩu, token truy cập hoặc payload nhạy cảm chỉ vì chúng đang có trong ThreadLocal.

## 8. Observation và Tracing dùng accessor nào?

Đối với Observation hiện tại, Micrometer cung cấp:

~~~java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;

ObservationThreadLocalAccessor.getInstance()
        .setObservationRegistry(observationRegistry);
~~~

Accessor này giúp Context Propagation khôi phục Observation hiện tại từ Reactor Context hoặc snapshot. Trong ứng dụng Spring Boot, hãy dùng ObservationRegistry do Boot quản lý và tránh tự tạo registry thứ hai không có các handler đã cấu hình.

Micrometer Tracing còn có accessor riêng cho một số trường hợp:

- ObservationAwareSpanThreadLocalAccessor để truyền span được tạo thủ công, không thuộc vòng đời của Observation.
- ObservationAwareBaggageThreadLocalAccessor để truyền baggage do ứng dụng tạo.

Hai accessor tracing này không thay thế ObservationThreadLocalAccessor. Chỉ đăng ký chúng khi ứng dụng thật sự dùng span/baggage thủ công và theo hướng dẫn của phiên bản Micrometer Tracing đang dùng.

## 9. Reactor Context là nguồn context theo subscription

Reactor Context gắn với subscriber, không gắn với thread. Scheduler có thể chuyển signal sang thread khác mà giá trị trong Context vẫn đi theo subscription.

contextWrite ghi một giá trị vào Context:

~~~java
Mono<String> pipeline =
        Mono.deferContextual(contextView ->
                Mono.just(contextView.get("request.id")))
            .publishOn(Schedulers.parallel())
            .contextWrite(context -> context.put("request.id", "req-42"));

String requestId = pipeline.block();
~~~

contextWrite có hướng lan truyền ngược về phía upstream: operator đứng phía trước contextWrite trong chuỗi có thể đọc giá trị được ghi. Nó không phải một biến mutable dùng chung cho các operator downstream.

Ví dụ:

~~~java
Mono.deferContextual(contextView ->
        Mono.just(contextView.getOrDefault("tenant", "missing")))
    .contextWrite(context -> context.put("tenant", "shop-a"));
~~~

Operator deferContextual nằm upstream của contextWrite, nên đọc được shop-a. Nếu đặt contextWrite ở vị trí khác, hãy vẽ lại thứ tự operator và xác định subscriber context được truyền về đâu.

## 10. contextWrite và contextCapture khác nhau thế nào?

| Operator | Nguồn dữ liệu | Mục đích |
| --- | --- | --- |
| contextWrite | Giá trị do code cung cấp trực tiếp. | Đặt Observation, tenant hoặc correlation data vào Reactor Context. |
| contextCapture | ThreadLocal tại thời điểm subscription. | Chụp các giá trị đã đăng ký accessor và đưa chúng vào Reactor Context. |

contextCapture chụp giá trị tại thời điểm subscribe, không phải thời điểm tạo publisher. Đây là lý do nó hữu ích khi một lời gọi imperative bên ngoài tạo reactive pipeline rồi subscribe trong lúc scope còn mở.

Khi đang ở trong reactive chain của WebFlux, thường nên đưa Observation vào Reactor Context trực tiếp thay vì mở ThreadLocal scope rồi gọi contextCapture. Publisher có thể được tạo trước và subscribe sau; vì vậy hãy phân biệt rõ assembly time và subscription time.

## 11. Hai chế độ propagation của Reactor

Reactor có hai chế độ khi Micrometer Context Propagation hiện diện:

| Chế độ | Operator khôi phục ThreadLocal | Cách bật |
| --- | --- | --- |
| Limited/default | Chủ yếu trong handle và tap, nếu Context có dữ liệu được capture hoặc ghi trực tiếp. | Mặc định trong Reactor. |
| Automatic | Trên các operator trong reactive chain khi chuyển thread. | Hooks.enableAutomaticContextPropagation() hoặc cấu hình Spring Boot. |

Chế độ limited có chi phí thấp hơn và phạm vi khôi phục hẹp hơn. Nếu chỉ một đoạn code cần đọc ThreadLocal, dùng handle hoặc tap phù hợp có thể đủ. Các operator như map và doOnNext không tự động được đảm bảo có ThreadLocal trong limited mode.

Chế độ automatic khôi phục ThreadLocal qua các ranh giới thread trong chain. Nó cần được bật trước khi tạo subscription; bật hook sau khi một publisher đã subscribe không làm thay đổi subscription cũ.

Trong automatic mode, Reactor phải dọn ThreadLocal khi context không có key tương ứng. Việc dọn này ngăn thread được tái sử dụng mang context của subscriber trước sang subscriber tiếp theo. Không tự viết code đặt ThreadLocal thủ công bên trong operator rồi để nó tồn tại sau callback.

## 12. Bật automatic propagation trực tiếp trong Reactor

Với ứng dụng không dùng Spring Boot:

~~~java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Hooks;

public final class ReactorContextConfiguration {

    public static void enable(ObservationRegistry registry) {
        ObservationThreadLocalAccessor.getInstance()
                .setObservationRegistry(registry);
        Hooks.enableAutomaticContextPropagation();
    }
}
~~~

Gọi cấu hình này một lần trong giai đoạn khởi động, trước khi ứng dụng tạo subscription. Cần có io.micrometer:context-propagation trên runtime classpath và các phiên bản Reactor/Micrometer tương thích.

Không gọi Hooks.enableAutomaticContextPropagation() trong mỗi request. Đây là hook toàn cục cho Reactor, không phải tùy chọn riêng cho một publisher.

## 13. Bật propagation trong Spring Boot

Spring Boot cung cấp property để chọn chế độ Reactor:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Giá trị mặc định thường là limited. Đặt auto nếu ứng dụng cần ThreadLocal được khôi phục xuyên suốt reactive chain. Kiểm tra tài liệu của phiên bản Spring Boot vì property và auto-configuration có thể khác giữa các dòng phiên bản.

Với @Async dùng executor auto-configured, Spring Boot 4.x hỗ trợ opt-in:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Với executor tự cấu hình, gắn ContextPropagatingTaskDecorator vào chính executor đó. Cấu hình Reactor automatic mode không tự động cấu hình mọi executor imperative trong ứng dụng.

## 14. Đọc ThreadLocal trong limited mode

Khi chưa bật automatic mode, handle và tap có thể khôi phục ThreadLocal từ Reactor Context nếu context propagation có mặt và giá trị đã được capture/ghi vào Context:

~~~java
Mono<String> pipeline =
        Mono.delay(Duration.ofMillis(10))
            .handle((value, sink) -> {
                Observation current = registry.getCurrentObservation();
                log.info("Current observation in handle: {}", current);
                sink.next("done");
            })
            .contextWrite(context ->
                    context.put(ObservationThreadLocalAccessor.KEY, parent));
~~~

Nếu cần đọc giá trị trong map hoặc doOnNext ở limited mode, đọc trực tiếp từ ContextView qua deferContextual hoặc transformDeferredContextual, hoặc đổi sang automatic mode sau khi đánh giá overhead.

Không giả định registry.getCurrentObservation() luôn khác null trong mọi callback reactive. Nếu code cần context, hãy xác định rõ nó đọc từ Reactor Context hay ThreadLocal đã được khôi phục.

## 15. Tạo Observation cho một reactive pipeline

Nếu mục tiêu là quan sát toàn bộ vòng đời của Mono/Flux, dùng tích hợp reactor-core-micrometer:

~~~java
import io.micrometer.observation.ObservationRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Order> observedOrder =
        orderRepository.findById(orderId)
            .name("orders.lookup")
            .tag("source", "repository")
            .publishOn(Schedulers.parallel())
            .map(this::enrich)
            .tap(Micrometer.observation(observationRegistry));
~~~

Micrometer.observation(registry) tạo Observation cho vòng đời reactive sequence. name(...) đặt tên sequence; tag(...) thêm low-cardinality tag. Cần dependency io.projectreactor:reactor-core-micrometer tương thích với Reactor Core.

Micrometer.observation(...) và Micrometer.metrics(...) phục vụ mục đích khác nhau. Observation phù hợp khi cần một vòng đời quan sát có thể tạo Timer, span hoặc các hành vi handler khác. Metrics tap cung cấp các meter cho tín hiệu và trạng thái của sequence.

Nếu publisher đã được framework instrument, kiểm tra trước khi gắn thêm tap để tránh quan sát trùng.

## 16. Đưa Observation cha vào Reactor Context

Khi publisher được tạo bên trong một Observation cha và cần giữ quan hệ cha–con, đưa parent vào Context bằng accessor key:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> childWork(Observation parent) {
    return Mono.fromCallable(() -> "payment-authorized")
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(context ->
                    context.put(ObservationThreadLocalAccessor.KEY, parent));
}
~~~

Nếu automatic propagation được bật, các operator ở phía upstream của contextWrite có thể thấy parent qua ThreadLocal. Trong limited mode, chỉ các operator hỗ trợ khôi phục ThreadLocal mới được đảm bảo. Dù ở chế độ nào, code vẫn có thể đọc parent trực tiếp qua deferContextual.

Không dùng ThreadLocal để lưu parent thay cho Reactor Context. Reactor Context đi theo subscriber và tránh phụ thuộc vào thread được chọn để chạy signal.

## 17. Tạo Observation con từ parent trong reactive chain

Nếu cần tạo Observation con thủ công, đọc parent từ ContextView và gắn parent tường minh:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> authorize(
        ObservationRegistry registry,
        Mono<String> paymentCall) {

    return Mono.deferContextual(contextView -> {
        Observation parent = contextView.getOrDefault(
                ObservationThreadLocalAccessor.KEY, null);

        Observation child = Observation.createNotStarted(
                "payment.authorize", registry);

        if (parent != null) {
            child.parentObservation(parent);
        }

        child.start();

        return paymentCall
                .subscribeOn(Schedulers.boundedElastic())
                .doOnError(error -> child.error(error))
                .doFinally(signalType -> child.stop())
                .contextWrite(context ->
                        context.put(ObservationThreadLocalAccessor.KEY, child));
    });
}
~~~

deferContextual trì hoãn việc tạo child đến lúc subscribe, khi parent context của subscriber đã có sẵn. parentObservation(parent) tạo liên kết cha–con rõ ràng kể cả khi child được tạo trong callback mà ThreadLocal không có parent.

doFinally chạy khi publisher complete, error hoặc cancel, nên child được stop trong mọi đường kết thúc. Nếu dùng doOnError, hãy báo lỗi cho Observation trước khi stop. Không gọi stop() ngay sau khi method trả Mono; lúc đó công việc reactive chưa chạy xong.

Ví dụ này dùng Mono để tập trung vào vòng đời một thao tác. Với Flux, xác định rõ Observation bao phủ toàn bộ stream hay từng item. Tạo một Observation cho mỗi phần tử có thể làm số span và meter tăng rất nhanh.

## 18. Không dùng Observation.observe() để bọc publisher rồi trả ra ngoài

Đây là lỗi vòng đời phổ biến:

~~~java
public Mono<Order> findOrder(String id) {
    return Observation.createNotStarted("order.lookup", registry)
            .observe(() -> orderRepository.findById(id));
}
~~~

observe(...) thực hiện start, mở scope, gọi supplier, đóng scope và stop khi supplier trả về. Supplier trên chỉ trả một đối tượng Mono; nó không chờ các signal của publisher. Vì vậy Observation kết thúc trước khi truy vấn reactive thực sự chạy.

Đối với publisher, dùng tap(Micrometer.observation(registry)), hoặc tạo Observation trong defer/deferContextual rồi stop trong doFinally.

## 19. Kiểm thử context qua scheduler

Một test nên xác minh cả context trong callback và việc context được dọn sau khi pipeline kết thúc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Hooks;
import reactor.core.scheduler.Schedulers;

class ReactorObservationPropagationTest {

    @Test
    void restoresObservationAcrossSchedulerBoundary() {
        ObservationRegistry registry = ObservationRegistry.create();
        ObservationThreadLocalAccessor.getInstance()
                .setObservationRegistry(registry);
        Hooks.enableAutomaticContextPropagation();

        Observation parent = Observation.start("request", registry);
        AtomicReference<Observation> seen = new AtomicReference<>();

        try {
            Mono.just("value")
                    .publishOn(Schedulers.parallel())
                    .doOnNext(value ->
                            seen.set(registry.getCurrentObservation()))
                    .contextWrite(context ->
                            context.put(
                                    ObservationThreadLocalAccessor.KEY,
                                    parent))
                    .block();

            assertThat(seen.get()).isSameAs(parent);
            assertThat(registry.getCurrentObservation()).isNull();
        }
        finally {
            parent.stop();
            Hooks.disableAutomaticContextPropagation();
        }
    }
}
~~~

Hook của Reactor là cấu hình toàn cục, vì vậy trong test suite lớn hãy bật một lần ở cấu hình test chung thay vì bật/tắt cạnh tranh giữa các test chạy song song. Test minh họa ở trên phù hợp khi chạy độc lập; nếu suite khác cũng phụ thuộc hook, dùng lifecycle chung của test environment.

## 20. Kiểm thử limited mode với handle

Nếu ứng dụng giữ chế độ limited, kiểm tra callback handle có được khôi phục context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Test
void restoresObservationInsideHandleInLimitedMode() {
    ObservationRegistry registry = ObservationRegistry.create();
    ObservationThreadLocalAccessor.getInstance()
            .setObservationRegistry(registry);

    Observation parent = Observation.start("request", registry);
    AtomicReference<Observation> seen = new AtomicReference<>();

    try {
        Mono.just("value")
                .publishOn(Schedulers.parallel())
                .handle((value, sink) -> {
                    seen.set(registry.getCurrentObservation());
                    sink.next(value);
                })
                .contextWrite(context ->
                        context.put(
                                ObservationThreadLocalAccessor.KEY,
                                parent))
                .block();

        assertThat(seen.get()).isSameAs(parent);
        assertThat(registry.getCurrentObservation()).isNull();
    }
    finally {
        parent.stop();
    }
}
~~~

Test này giả định không bật automatic mode trong test process. Nếu automatic hook đã được bật bởi test khác, hãy tách test context hoặc xác minh chế độ một cách rõ ràng.

## 21. Kiểm thử contextCapture từ imperative caller

Khi một imperative caller mở scope rồi subscribe publisher, contextCapture() có thể chụp Observation hiện tại vào Reactor Context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Test
void capturesCurrentObservationAtSubscriptionTime() {
    ObservationRegistry registry = ObservationRegistry.create();
    ObservationThreadLocalAccessor.getInstance()
            .setObservationRegistry(registry);

    Observation parent = Observation.start("request", registry);
    AtomicReference<Observation> seen = new AtomicReference<>();

    try (Observation.Scope scope = parent.openScope()) {
        Mono.just("value")
                .publishOn(Schedulers.parallel())
                .handle((value, sink) -> {
                    seen.set(registry.getCurrentObservation());
                    sink.next(value);
                })
                .contextCapture()
                .block();

        assertThat(seen.get()).isSameAs(parent);
    }
    finally {
        parent.stop();
    }
}
~~~

contextCapture() chụp ở subscription, nên scope phải còn mở tại thời điểm block() hoặc subscribe() thực hiện subscription. Không tạo publisher trong scope rồi đóng scope trước khi subscription bắt đầu và kỳ vọng giá trị cũ vẫn được chụp.

## 22. Đọc context bằng deferContextual thay vì ThreadLocal

Nếu code chỉ cần đọc dữ liệu từ reactive chain, đọc trực tiếp Reactor Context thường rõ ràng hơn:

~~~java
Mono<String> tenantAwareCall =
        Mono.deferContextual(contextView -> {
            String tenant = contextView.get("tenant");
            return customerRepository.findByTenant(tenant);
        })
        .contextWrite(context -> context.put("tenant", "shop-a"));
~~~

Không cần bật automatic propagation chỉ để đọc một giá trị đã có trong Context. Dùng ThreadLocal restoration khi một thư viện imperative hiện hữu cần truy cập current context qua API ThreadLocal.

## 23. Kiểm tra quan hệ cha–con, không chỉ kiểm tra trace ID

Một trace ID xuất hiện ở log không chứng minh quan hệ cha–con đúng. Kiểm tra thêm:

- Span con có parent span ID trỏ đến span cha dự kiến.
- Span cha chưa bị kết thúc trước khi công việc con hoàn tất nếu thiết kế yêu cầu quan hệ lồng nhau.
- Span con được tạo trong đúng Observation/trace context.
- Baggage có mặt trên worker khi accessor đã đăng ký.
- Không có span mới không mong muốn tại ranh giới scheduler hoặc executor.

Nếu chỉ thấy trace ID nhưng span ID khác, đó có thể là quan hệ child hợp lệ. Nếu trace ID thay đổi và trace mới bắt đầu, parent context có thể đã mất hoặc một instrumentation component đang tạo root span.

## 24. Kiểm tra baggage và span tạo thủ công

Observation và span không hoàn toàn đồng nhất. Một span có thể được tạo thủ công bằng Tracer mà không có Observation tương ứng. Trong trường hợp đó, ObservationThreadLocalAccessor một mình có thể chưa đủ để truyền span hoặc baggage.

Với Micrometer Tracing, đăng ký các accessor phù hợp:

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.contextpropagation.ObservationAwareBaggageThreadLocalAccessor;
import io.micrometer.tracing.contextpropagation.ObservationAwareSpanThreadLocalAccessor;

ContextRegistry contextRegistry = ContextRegistry.getInstance();

contextRegistry.registerThreadLocalAccessor(
        new ObservationAwareSpanThreadLocalAccessor(observationRegistry, tracer));

contextRegistry.registerThreadLocalAccessor(
        new ObservationAwareBaggageThreadLocalAccessor(observationRegistry, tracer));
~~~

Các constructor và cách khởi tạo cụ thể phụ thuộc phiên bản Micrometer Tracing. Hãy dùng accessor được bridge Brave hoặc OpenTelemetry cung cấp và không tự copy trace ID thành một ThreadLocal tùy biến.

Việc Boot đã cấu hình Observation propagation không có nghĩa mọi baggage tự tạo bằng Tracer API cũng được đăng ký. Nếu baggage mất sau khi đổi thread, kiểm tra riêng ObservationAwareBaggageThreadLocalAccessor và đăng ký nó theo tài liệu Micrometer Tracing của phiên bản đang dùng.

## 25. Những lỗi thường gặp khi dùng Reactor Context

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Chỉ mở Observation.Scope trước publishOn | Thread sau scheduler không có current Observation. | Đưa Observation vào Reactor Context và bật chế độ propagation phù hợp. |
| Nghĩ subscribeOn/publishOn tự truyền ThreadLocal | Context biến mất sau đổi thread. | Dùng Context Propagation; scheduler chỉ quyết định nơi chạy. |
| Đặt contextWrite sai vị trí | deferContextual không thấy key. | Nhớ contextWrite tác động ngược về upstream. |
| Dùng contextCapture trước khi có scope | Context snapshot không có Observation. | Mở scope tại subscription hoặc dùng contextWrite trực tiếp. |
| Bật hook sau khi publisher đã subscribe | Subscription cũ không có propagation tự động. | Bật hook ở startup trước khi tạo subscription. |
| Dùng limited mode nhưng đọc ThreadLocal trong map | Callback không có current Observation. | Đọc ContextView hoặc dùng handle/tap, hoặc chọn auto mode. |
| Tạo child trước khi lấy parent context | Child trở thành root span. | Dùng deferContextual và parentObservation(parent). |
| Stop Observation ngay khi trả Mono | Timer/span kết thúc quá sớm. | Stop trong doFinally hoặc dùng Micrometer.observation. |
| Giữ scope mở xuyên reactive pipeline | Scope đóng sai thread hoặc ThreadLocal rò rỉ. | Scope chỉ bao quanh callback đồng bộ; dùng Reactor Context giữa các signal. |
| Chỉ truyền Observation nhưng quên baggage accessor | Trace ID có nhưng baggage mất. | Đăng ký accessor span/baggage cần thiết. |
| Accessor không xóa ThreadLocal | Request sau nhận context cũ. | Implement setValue() không tham số để clear/remove. |
| Tạo nhiều Observation cho mỗi item | Span count và overhead tăng mạnh. | Chọn ranh giới đo: toàn stream hay từng item. |

## 26. Quy trình chẩn đoán từng bước

Khi quan hệ Observation bị mất, kiểm tra theo thứ tự:

1. **Xác minh Observation được tạo.** Kiểm tra registry có no-op không, predicate có loại nó không và handler có được đăng ký không.
2. **Xác định ranh giới đổi context.** Tìm Executor, @Async, CompletableFuture, subscribeOn, publishOn, flatMap, callback hoặc message listener.
3. **Xác định context carrier.** Code đang dùng ThreadLocal, Reactor Context, hay context riêng của framework?
4. **Kiểm tra accessor.** Observation, span, baggage và ThreadLocal tùy biến đã có accessor tương ứng chưa?
5. **Kiểm tra chế độ propagation.** Reactor đang ở limited hay auto? Spring Boot property có đúng không? Hook đã bật trước subscription chưa?
6. **Kiểm tra vị trí capture/write.** contextCapture() có chạy khi scope còn mở không? contextWrite() có nằm ở vị trí mà upstream operator đọc được không?
7. **Kiểm tra parent-child.** Observation con được tạo khi parent hiện diện hay đã gắn parentObservation(parent) tường minh?
8. **Kiểm tra lifecycle.** Parent và child có bị stop quá sớm hoặc quên stop khi cancel/error không?
9. **Kiểm tra cleanup.** ThreadLocal có được khôi phục giá trị cũ và xóa khi Context không có key không?
10. **Kiểm tra tải và hiệu năng.** Nếu bật automatic propagation, đo CPU/latency/throughput và allocation dưới tải đại diện.

## 27. Chọn cách propagation theo tình huống

| Tình huống | Cách phù hợp |
| --- | --- |
| Code đồng bộ trong một thread | Observation.observe(...) hoặc Observation.scoped(...). |
| ExecutorService / CompletableFuture | ContextExecutorService.wrap(...) hoặc ContextSnapshot.wrap(...). |
| Spring @Async | ContextPropagatingTaskDecorator trên executor; dùng property nếu Boot auto-config hỗ trợ. |
| Reactive code chỉ cần truyền dữ liệu | Reactor Context và contextWrite. |
| Imperative caller bắt đầu reactive subscription | contextCapture() khi scope còn mở, hoặc ghi Context tường minh. |
| Reactive chain cần ThreadLocal trong nhiều operator | Automatic context propagation. |
| Chỉ cần ThreadLocal trong handle/tap | Limited/default mode có thể đủ. |
| Đo toàn bộ reactive sequence | tap(Micrometer.observation(registry)). |
| Tạo Observation con trong reactive chain | deferContextual + parentObservation(parent) + doFinally. |

## 28. Cân nhắc hiệu năng và bảo mật

Context propagation có chi phí. Mỗi lần chuyển thread hoặc chạy operator có thể cần chụp, đọc, khôi phục và dọn context. Automatic mode tiện lợi nhưng không mặc định là nhanh nhất cho mọi pipeline.

Nên:

- Chỉ đăng ký accessor cho context thực sự cần truyền.
- Đo overhead bằng tải và số operator gần với production.
- Dùng Reactor Context trực tiếp khi có thể, tránh đọc ThreadLocal không cần thiết.
- Giữ task và callback ngắn; không đưa I/O blocking vào event loop.
- Đảm bảo accessor xóa ThreadLocal khi giá trị không tồn tại.
- Giữ vòng đời parent/child rõ ràng và dừng Observation đúng tín hiệu.

Tránh:

- Dùng InheritableThreadLocal để thay cho context propagation trong thread pool.
- Copy toàn bộ MDC hoặc mọi ThreadLocal tùy tiện mà không kiểm soát key.
- Đưa access token, session secret hoặc dữ liệu cá nhân vào context dùng cho log/tracing.
- Bật hook toàn cục từ code chạy theo request.
- Mở một Observation scope trên một thread rồi đóng scope trên thread khác.
- Dùng block() trong WebFlux event loop để kiểm tra hoặc “giữ” context.

## 29. Checklist trước khi phát hành

- [ ] Đã xác định chính xác ranh giới đổi thread hoặc subscription.
- [ ] Đã phân biệt Observation, Scope, ThreadLocal và Reactor Context.
- [ ] Đã đăng ký accessor cho Observation và các ThreadLocal tùy biến cần thiết.
- [ ] Executor imperative đã được wrap hoặc có TaskDecorator.
- [ ] Reactor Context có key Observation khi reactive chain cần parent.
- [ ] Đã chọn limited hay automatic mode dựa trên yêu cầu thực tế.
- [ ] Hook hoặc Spring Boot property được bật trước subscription.
- [ ] contextCapture chỉ dùng khi subscription cần chụp ThreadLocal hiện có.
- [ ] contextWrite được đặt đúng phía upstream của operator cần đọc.
- [ ] Observation con được liên kết với parent đúng cách.
- [ ] Publisher không bị bọc bằng Observation.observe() theo cách stop trước khi stream chạy xong.
- [ ] Observation được stop trên complete, error và cancel.
- [ ] ThreadLocal được khôi phục và xóa để không rò rỉ giữa request.
- [ ] Đã kiểm tra trace ID, span ID, parent span ID và baggage.
- [ ] Đã đo overhead propagation trong tải gần production.

Mất quan hệ quan sát khi đổi thread thường xuất phát từ việc dùng ThreadLocal vượt quá phạm vi của thread. Với executor, dùng snapshot/decorator để khôi phục context quanh task. Với Reactor, đặt dữ liệu vào Reactor Context và chỉ khôi phục ThreadLocal khi cần. Khi tạo Observation con, giữ parent rõ ràng và quản lý stop theo vòng đời bất đồng bộ. Ba bước đó giúp trace, log và metrics cùng mô tả đúng một thao tác xuyên suốt các thread và operator.

## Tài liệu tham khảo

- [Micrometer Observation - Instrumentation and Context Propagation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer Context Propagation - Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation - Examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Tracing - Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Project Reactor - Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Project Reactor - Exposing Reactor Metrics and Observations](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [Spring Boot - Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework - ContextPropagatingTaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
