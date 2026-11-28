# Kiểm thử context propagation

> **Chương:** Kiểm thử  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Vì sao phải kiểm thử context propagation?

Trong ứng dụng Spring Boot, context thường chứa những thông tin giúp liên kết một request với các operation phát sinh từ nó:

- Trace ID và span ID để nối các span trong cùng một trace.
- Observation context để tiếp tục đo lường một operation.
- MDC values để log có correlation ID.
- Tenant, locale hoặc security context do ứng dụng quản lý.
- Baggage được cấu hình để truyền metadata qua các process.

Ở luồng đồng bộ, những giá trị này có thể nằm trong `ThreadLocal`. Khi công việc chuyển sang thread khác, `ThreadLocal` của thread mới không tự nhận giá trị từ thread gọi. Với reactive pipeline, context thường nằm trong Reactor `Context`; nó cũng không đồng nhất với `ThreadLocal`.

Trong Spring Modulith, một event có thể được xử lý bởi `@ApplicationModuleListener`. Listener này chạy bất đồng bộ sau khi transaction phát event commit. Nếu context không được truyền qua executor, listener có thể mất trace liên quan tới request gốc. Nếu context không được khôi phục đúng cách, thread pool còn có nguy cơ giữ lại dữ liệu của request trước và làm nhiễm request tiếp theo.

Mục tiêu của bài là xây dựng các kiểm thử chứng minh context được truyền đúng, được khôi phục sau task và không rò rỉ giữa các request.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt context propagation qua thread, Reactor pipeline và HTTP boundary.
2. Viết kiểm thử cho `ThreadLocalAccessor` và `ContextSnapshot`.
3. Kiểm tra `ContextPropagatingTaskDecorator` trên thread pool thực.
4. Kiểm thử trace ID qua `@Async` và `@ApplicationModuleListener`.
5. Dùng Spring Modulith `@ApplicationModuleTest` và `Scenario` để kiểm thử event bất đồng bộ.
6. Kiểm tra W3C `traceparent` khi gọi HTTP downstream.
7. Kiểm tra context propagation trong Reactor.
8. Phát hiện context leakage, race condition và các kiểm thử tạo false positive.

## 2. Những ranh giới cần kiểm thử

Context propagation không phải một thao tác duy nhất. Mỗi ranh giới có cơ chế và hợp đồng riêng:

| Ranh giới | Context trước khi chuyển | Cơ chế truyền | Điều cần xác minh |
|---|---|---|---|
| Thread A → thread B | ThreadLocal | Context Snapshot, task decorator | Giá trị được khôi phục trong task |
| Request → async executor | Observation/trace context | Micrometer Context Propagation | Trace ID được giữ, scope được đóng |
| Module A → async event listener | Transactional event và trace context | Event listener + executor | Listener thuộc trace đúng sau commit |
| Reactor → imperative code | Reactor Context | Context Propagation accessor | ThreadLocal được khôi phục trong operator |
| Service A → service B | Trace context | W3C Trace Context qua HTTP headers | Downstream nhận đúng trace ID |

Có ba khái niệm không nên nhầm lẫn:

- **Context propagation:** đưa các giá trị context qua ranh giới thực thi.
- **Trace propagation:** truyền trace context giữa các service, thường qua header như `traceparent`.
- **Business event delivery:** đảm bảo event được listener nhận và xử lý theo transaction/publication policy.

Một test event listener hoàn tất không tự chứng minh trace context đã được truyền. Ngược lại, cùng trace ID cũng không chứng minh listener đã hoàn tất nghiệp vụ. Cần assertion riêng cho từng hợp đồng.

## 3. Thiết kế test contract trước khi viết test

Trước tiên, xác định những điều test phải chứng minh:

| Hợp đồng | Assertion nên có |
|---|---|
| Giá trị context được truyền | Worker đọc đúng giá trị từ caller |
| Snapshot được chụp đúng thời điểm | Thay đổi context sau khi submit không thay đổi snapshot đã chụp |
| Context của worker được khôi phục | Sau task, worker trở về giá trị trước khi chạy task |
| Không rò rỉ giữa task | Task tiếp theo không nhìn thấy context của task trước |
| Context vẫn đúng khi task lỗi | Cleanup/restore vẫn diễn ra khi exception được ném |
| Trace được nối | Trace ID ở downstream giống trace ID của parent |
| Span có quan hệ đúng | Span ID có thể khác, nhưng parent/child hoặc link phải đúng |
| Event listener được chạy | Listener hoàn tất sau transaction commit |
| HTTP propagation hoạt động | Request downstream có header trace context hợp lệ |

Một trace thường chứa nhiều span. Vì vậy, khi kiểm thử tracing, **so sánh trace ID**, không yêu cầu span ID của listener phải bằng span ID của request. Listener hoặc module instrumentation có thể tạo một child span với span ID mới trong cùng trace.

Không nên chỉ kiểm tra tên thread. Thread khác tên không chứng minh context đã được truyền, còn thread có cùng tên cũng không chứng minh context bị mất.

## 4. Chuẩn bị dependencies kiểm thử

Với Gradle, ví dụ dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Spring Modulith test starter cung cấp hỗ trợ kiểm thử application module và `Scenario`. Các dependency Micrometer Context Propagation, Spring Framework và tracing bridge thường đã có trong runtime graph nếu ứng dụng bật observability; hãy giữ version được quản lý bởi BOM tương thích.

Các test tracing cần có một implementation của Micrometer Tracing, chẳng hạn OpenTelemetry bridge. Nếu chỉ dùng Observation mà không cấu hình tracer, hãy kiểm tra observation lifecycle bằng test handler thay vì giả định luôn có trace ID.

## 5. Kiểm thử ThreadLocalAccessor và ContextSnapshot

Micrometer Context Propagation sử dụng các abstraction:

- `ThreadLocalAccessor` đọc, đặt và reset một giá trị `ThreadLocal`.
- `ContextRegistry` đăng ký các accessor.
- `ContextSnapshot` giữ một snapshot context.
- `ContextSnapshotFactory` tạo snapshot từ các accessor đã đăng ký.

Ứng dụng có `ThreadLocal` riêng, ví dụ tenant context, cần đăng ký accessor tương ứng. Thư viện không tự động truyền mọi ThreadLocal tùy ý chỉ vì đã thêm Context Propagation.

Ví dụ holder:

~~~java
final class TenantContext {

    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    static String get() {
        return TENANT.get();
    }

    static void set(String tenant) {
        TENANT.set(tenant);
    }

    static void clear() {
        TENANT.remove();
    }
}
~~~

Accessor cho holder:

~~~java
import io.micrometer.context.ThreadLocalAccessor;

final class TenantThreadLocalAccessor implements ThreadLocalAccessor<String> {

    @Override
    public Object key() {
        return "tenant";
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

Một unit test kiểm tra snapshot giữ giá trị tại thời điểm capture:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.context.Scope;
import org.junit.jupiter.api.Test;

class ContextSnapshotTests {

    @Test
    void capturesAndRestoresTenantContext() {
        ContextRegistry registry = new ContextRegistry();
        registry.registerThreadLocalAccessor(new TenantThreadLocalAccessor());

        ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .build();

        TenantContext.set("tenant-42");
        ContextSnapshot snapshot = factory.captureAll();

        TenantContext.set("tenant-99");

        try (Scope ignored = snapshot.setThreadLocals()) {
            assertEquals("tenant-42", TenantContext.get());
        }

        assertEquals("tenant-99", TenantContext.get());
        TenantContext.clear();
    }
}
~~~

Test này chứng minh snapshot đã giữ giá trị `tenant-42`. Khi scope đóng, giá trị trước khi mở scope (`tenant-99`) được khôi phục.

Nên dùng registry riêng trong unit test để tránh làm thay đổi global registry của các test khác. Nếu đăng ký accessor vào `ContextRegistry.getInstance()`, phải unregister trong cleanup để không làm test phụ thuộc thứ tự chạy.

## 6. Kiểm thử ContextPropagatingTaskDecorator trên thread pool

Kiểm thử trên cùng một thread có thể che giấu lỗi propagation. Hãy dùng executor có worker thread riêng và tái sử dụng worker để phát hiện context leakage.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

class TaskDecoratorTests {

    @Test
    void propagatesContextAndRestoresWorkerThread() throws Exception {
        ContextRegistry registry = new ContextRegistry();
        registry.registerThreadLocalAccessor(new TenantThreadLocalAccessor());

        ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .build();

        ContextPropagatingTaskDecorator decorator =
                new ContextPropagatingTaskDecorator(factory);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicReference<String> observed = new AtomicReference<>();

        try {
            executor.submit(() -> TenantContext.set("worker-before")).get();

            TenantContext.set("tenant-42");
            Runnable decorated = decorator.decorate(
                    () -> observed.set(TenantContext.get())
            );
            TenantContext.clear();

            String afterTask = executor.submit(() -> {
                decorated.run();
                return TenantContext.get();
            }).get();

            assertEquals("tenant-42", observed.get());
            assertEquals("worker-before", afterTask);
        } finally {
            TenantContext.clear();
            executor.shutdownNow();
        }
    }
}
~~~

Trong test, worker được đặt sẵn `worker-before`. Caller tạo snapshot với `tenant-42` và decorator bọc task. Khi task chạy, worker nhìn thấy `tenant-42`; sau khi task kết thúc, worker trở về `worker-before`.

Đây là assertion quan trọng đối với thread pool: task phải nhận context của caller, nhưng không được để lại context đó trong worker sau khi hoàn tất.

### 6.1. Thêm kiểm thử task thất bại

Có thể bổ sung test dùng một task ném exception bên trong decorator. Sau khi Future hoàn tất với exception, submit một task khác lên cùng single-thread executor và xác nhận worker không còn thấy context của task lỗi.

Điều này kiểm tra cleanup trong nhánh exception. Không chỉ kiểm thử đường chạy thành công vì exception là một trong các nguyên nhân dễ để lại trạng thái thread-local sai.

### 6.2. Kiểm thử hai request đồng thời

Dùng hai task có context khác nhau, ví dụ `tenant-A` và `tenant-B`, rồi đồng bộ bằng latch/barrier để chúng thực thi chồng lấn. Mỗi task phải đọc đúng tenant của mình.

Test này phát hiện việc dùng một biến mutable dùng chung thay cho context được scope theo thread. Tránh dùng sleep để tạo race condition; dùng latch, barrier hoặc primitive đồng bộ có timeout.

## 7. Cấu hình executor cần được kiểm thử

`ContextPropagatingTaskDecorator` bọc task và dùng Context Snapshot để khôi phục context trong lúc task chạy. Decorator chỉ có tác dụng khi được gắn vào executor thực sự thực thi task.

### 7.1. Spring Boot 4.x với executor auto-configured

Với `AsyncTaskExecutor` do Spring Boot auto-configure, có thể bật context propagation:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Property này opt-in propagation cho task execution của auto-configured executor. Giá trị mặc định là false.

### 7.2. Spring Boot 3.5 hoặc executor tự cấu hình

Tài liệu Boot 3.5 hướng dẫn đăng ký `ContextPropagatingTaskDecorator` trên executor. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncExecutionConfiguration {

    @Bean("taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Trong ví dụ này, `taskExecutor` là executor được Spring chọn cho `@Async` theo quy tắc executor bean. Nếu ứng dụng có nhiều executor hoặc khai báo `AsyncConfigurer`, phải xác định rõ executor nào xử lý listener và gắn decorator vào đúng executor đó.

Nếu tự tạo executor trên Boot 4.x, property dành cho executor auto-configured không tự cấu hình executor tùy chỉnh. Hãy gắn decorator trực tiếp như ví dụ.

### 7.3. Những gì phải kiểm tra ở wiring

- `@EnableAsync` đã được bật trong application configuration.
- `@ApplicationModuleListener` thực sự được xử lý qua async executor.
- Executor có decorator đang được dùng bởi listener.
- Không có `AsyncConfigurer` hoặc bean `taskExecutor` khác làm đổi executor được chọn.
- Custom ThreadLocal đã đăng ký accessor.
- Executor không bị thay bằng direct/synchronous executor trong test.

Một test chỉ kiểm tra bean decorator tồn tại chưa đủ. Cần thực thi task trên executor thật và quan sát giá trị trong thread khác.

## 8. Kiểm thử trace qua @ApplicationModuleListener

`@ApplicationModuleListener` là shortcut cho async transactional event listener: listener chạy sau transaction commit và trong transaction riêng. Vì vậy đây là ranh giới phù hợp để kiểm tra trace context từ module phát event sang module nhận event.

Ví dụ listener trong module `notification`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;
import org.springframework.modulith.events.ApplicationModuleListener;

@Component
class NotificationListener {

    private final Tracer tracer;
    private final AtomicReference<String> lastTraceId = new AtomicReference<>();

    NotificationListener(Tracer tracer) {
        this.tracer = tracer;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        Span current = tracer.currentSpan();
        lastTraceId.set(current == null ? null : current.context().traceId());
    }

    String lastTraceId() {
        return lastTraceId.get();
    }

    void clear() {
        lastTraceId.set(null);
    }
}
~~~

Test theo module:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;
import org.springframework.test.context.TestPropertySource;
import java.time.Duration;

@ApplicationModuleTest
@TestPropertySource(properties = "spring.task.execution.propagate-context=true")
class NotificationModuleTests {

    @Autowired
    NotificationListener listener;

    @Autowired
    Tracer tracer;

    @Test
    void propagatesTraceToAsyncModuleListener(Scenario scenario) {
        listener.clear();

        Span parent = tracer.nextSpan()
                .name("test.order-completed")
                .start();

        try (Tracer.SpanInScope ignored = tracer.withSpan(parent)) {
            scenario.publish(new OrderCompleted("order-42"))
                    .andWaitAtMost(Duration.ofSeconds(5))
                    .andWaitForStateChange(listener::lastTraceId)
                    .andVerify(traceId ->
                            assertThat(traceId)
                                    .isEqualTo(parent.context().traceId())
                    );
        } finally {
            parent.end();
        }
    }
}
~~~

Ví dụ dùng property Boot 4.x cho auto-configured executor. Với Boot 3.5, cấu hình executor của test bằng `ContextPropagatingTaskDecorator` như phần trước và bảo đảm listener sử dụng executor đó.

`Scenario` chạy event publication trong transaction callback để transactional listener được kích hoạt sau commit. API chờ trạng thái listener thay đổi, nên test không cần dùng `Thread.sleep` hoặc đoán thời gian xử lý.

Test so sánh trace ID của listener với trace ID parent. Nếu listener tạo child span, span ID có thể khác; điều quan trọng là nó vẫn thuộc cùng trace.

Nếu listener cập nhật database, cần cleanup dữ liệu test. Transaction do `Scenario` tạo để kích hoạt event không đồng nghĩa mọi side effect của listener sẽ tự rollback cùng transaction test.

### 8.1. Kiểm tra trường hợp không có parent span

Thêm một scenario khác không mở parent span, rồi xác nhận listener không nhận trace ID cũ từ test trước. Nếu instrumentation tạo root span mới cho listener, trace ID có thể khác và không null; assertion cần kiểm tra không tái sử dụng trace ID cũ.

Kết hợp với test ThreadLocal accessor để kiểm tra tenant/request context thực sự không có giá trị trong trường hợp caller không cung cấp context.

## 9. Kiểm thử HTTP trace propagation

Context propagation trong cùng process khác với trace propagation giữa hai service. Với HTTP, client instrumentation phải inject W3C Trace Context headers, thường là `traceparent` và có thể có `tracestate`.

Một kiểm thử HTTP nên:

1. Tạo parent span trong test.
2. Gọi HTTP client được Spring Boot auto-configure, ví dụ `RestClient.Builder` hoặc `WebClient.Builder`.
3. Nhận request bằng mock HTTP server.
4. Đọc header `traceparent`.
5. Parse header theo định dạng W3C.
6. So sánh trace ID trong header với trace ID của parent span.

Định dạng `traceparent` phiên bản 00 có dạng:

~~~text
00-<32-hex-trace-id>-<16-hex-parent-id>-<2-hex-flags>
~~~

Trace ID phải khớp parent trace. Parent ID trong header thường là span ID được inject cho outbound operation, không nhất thiết bằng span ID của span server ban đầu nếu client instrumentation tạo client span.

Dùng builder được Spring Boot auto-configure để bảo đảm tracing instrumentation được áp dụng. Nếu tự tạo HTTP client không qua builder đó, test có thể phát hiện header propagation bị mất.

Không chỉ kiểm tra header tồn tại. Hãy kiểm tra version, độ dài, ký tự hex và trace ID. Header sai định dạng hoặc chứa trace ID khác vẫn là lỗi propagation.

## 10. Kiểm thử Reactor context propagation

Trong WebFlux, Reactor `Context` là nguồn context chính cho reactive chain. ThreadLocal không tự động được khôi phục trong mọi operator.

Spring Boot hỗ trợ cấu hình:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Để kiểm thử reactive propagation:

- Đăng ký accessor cho ThreadLocal cần truyền.
- Đưa giá trị vào Reactor Context.
- Chạy operator cần đọc ThreadLocal.
- Dùng `StepVerifier` để xác nhận operator nhìn thấy giá trị mong đợi.
- Kiểm tra ThreadLocal được khôi phục/clear sau khi pipeline hoàn tất.

Một ví dụ minh họa test:

~~~java
@Test
void restoresTenantFromReactorContext() {
    Mono<String> result = Mono.defer(() ->
            Mono.just(TenantContext.get())
    ).contextWrite(context ->
            context.put("tenant", "tenant-42")
    );

    StepVerifier.create(result)
            .expectNext("tenant-42")
            .verifyComplete();
}
~~~

Test này chỉ chứng minh được propagation khi ứng dụng bật chế độ Reactor phù hợp và accessor key khớp với key trong Reactor Context. Nếu test chạy trong cấu hình mặc định khác production, nó có thể tạo kết quả sai lệch.

Không dựa vào việc một pipeline tình cờ chạy trên cùng thread. Hãy dùng scheduler chuyển thread trong một test riêng nếu mục tiêu là xác minh propagation qua scheduler boundary.

## 11. Kiểm thử Observation và trace lifecycle

Nếu ứng dụng dùng Micrometer Observation, có thể kiểm tra:

- Observation được bắt đầu và kết thúc.
- Observation scope được mở trong task.
- Context hiện tại được khôi phục khi listener chạy.
- Error được gắn vào observation/span tương ứng.
- Observation không còn current sau khi task kết thúc.

Với test cần xác minh tên observation, key-value hoặc lifecycle handler, dùng test observation registry/handler của Micrometer. Với test tracing end-to-end, dùng tracer test hoặc tracing bridge đã cấu hình và so sánh trace ID/parent relationship.

Không chỉ assert một observation được tạo. Cần xác nhận observation thuộc đúng request, có parent hợp lệ và kết thúc khi task hoàn tất.

## 12. Negative tests: kiểm tra context không bị rò rỉ

Các test âm thường tìm ra lỗi mà happy-path không phát hiện.

| Tình huống | Kết quả mong đợi |
|---|---|
| Caller không có tenant context | Worker không nhận tenant từ request trước |
| Caller đổi tenant sau khi submit | Task dùng snapshot tại thời điểm submit |
| Task ném exception | Context worker được khôi phục |
| Hai task chạy đồng thời | Mỗi task chỉ thấy context của mình |
| Worker thread được tái sử dụng | Task tiếp theo không thấy context task trước |
| Listener chạy khi không có parent span | Không nối nhầm vào trace trước |
| HTTP client không có current span | Không tự gắn trace ID cũ vào request |
| Reactor chain kết thúc | ThreadLocal không bị giữ lại trên scheduler thread |

Một test quan trọng là tái sử dụng cùng một single-thread executor:

1. Submit task A với tenant `tenant-A`.
2. Chờ A hoàn tất.
3. Submit task B mà caller không có tenant context.
4. Xác nhận B không đọc được `tenant-A`.
5. Submit task C với `tenant-C`.
6. Xác nhận C đọc đúng `tenant-C`.

Nếu task B nhìn thấy tenant A, worker thread đã bị nhiễm context.

## 13. Các lỗi kiểm thử thường gặp

### 13.1. Dùng executor chạy đồng bộ

`SyncTaskExecutor` hoặc executor chạy task ngay trên caller thread không tạo thread boundary. Test có thể pass dù propagation hoàn toàn chưa được cấu hình.

Dùng thread pool hoặc executor thực sự chạy task trên worker thread.

### 13.2. Dùng Thread.sleep

Sleep chỉ đoán rằng task đã chạy. Nó làm test chậm và flaky. Dùng Future, CountDownLatch, Awaitility hoặc Spring Modulith Scenario với timeout rõ ràng.

### 13.3. Chỉ kiểm tra span ID

Child span phải có span ID riêng. Kiểm tra trace ID và parent relationship; không bắt buộc span ID của child giống parent.

### 13.4. Bỏ qua exception path

Context có thể được khôi phục khi task thành công nhưng bị rò rỉ nếu task ném exception. Hãy kiểm tra cả hai nhánh.

### 13.5. Không reset ThreadLocal sau test

ThreadLocal là trạng thái mutable. Luôn reset trong `finally` hoặc lifecycle cleanup. Với global ContextRegistry, unregister accessor đã đăng ký trong test.

### 13.6. Test listener trước khi transaction commit

`@ApplicationModuleListener` là transactional event listener chạy sau commit. Nếu test bọc toàn bộ test method trong transaction và transaction không commit, listener có thể không chạy. Dùng Spring Modulith `Scenario` hoặc transaction template để kiểm soát commit.

### 13.7. Dùng nhầm executor

Ứng dụng có thể có nhiều executor. Decorator được gắn vào executor A không giúp listener chạy trên executor B. Kiểm tra tên bean, `AsyncConfigurer`, qualifier và executor thực tế.

### 13.8. Cho rằng mọi ThreadLocal đều tự truyền

Chỉ các context có accessor phù hợp mới được Context Propagation quản lý. Đăng ký accessor cho context riêng của ứng dụng; không dùng một biến static mutable làm context toàn cục.

### 13.9. Dùng trace exporter như assertion duy nhất

Trace backend có sampling, export delay và network failure. Unit/integration test nên xác minh context tại nơi thực thi bằng tracer hoặc probe trực tiếp; kiểm tra exporter/backend là một test vận hành riêng.

## 14. Quy trình kiểm thử trong CI

Một pipeline có thể chia test theo chi phí và phạm vi:

| Tầng | Test | Khi chạy |
|---|---|---|
| Unit | ContextSnapshot, ThreadLocalAccessor, decorator | Mỗi commit |
| Component | Custom executor và async service | Mỗi commit |
| Module integration | `@ApplicationModuleTest` + `Scenario` | Mỗi thay đổi liên quan module/event |
| Application integration | Trace qua nhiều module và transaction | Pull request hoặc CI chính |
| HTTP integration | Kiểm tra traceparent qua client/server | Pull request hoặc CI chính |
| Reactive integration | Reactor context qua scheduler | Khi service có WebFlux/reactive |
| Operational smoke | Export trace tới Collector/backend test | Pipeline môi trường tích hợp |

Đặt timeout cho mọi async assertion. Dùng thread pool có kích thước nhỏ trong test để tăng khả năng tái sử dụng worker và phát hiện leakage. Luôn đóng executor, server giả lập và transaction resource trong cleanup.

Khi test thất bại, log tối thiểu nên có:

- Test case và module.
- Thread caller và worker.
- Trace ID mong đợi và trace ID thực tế.
- Context key đang được kiểm tra.
- Executor bean được dùng.
- Event ID hoặc business correlation ID không nhạy cảm.

Không log access token, thông tin cá nhân hoặc toàn bộ baggage nếu các giá trị đó có thể nhạy cảm.

## 15. Checklist trước khi merge

- [ ] Test chạy qua thread boundary thật.
- [ ] Context accessor được đăng ký cho ThreadLocal riêng.
- [ ] Snapshot capture đúng giá trị tại thời điểm submit.
- [ ] Context worker được khôi phục sau task.
- [ ] Task exception không để lại context trên worker.
- [ ] Hai task đồng thời không đọc nhầm context của nhau.
- [ ] Async executor thực tế được gắn ContextPropagatingTaskDecorator hoặc bật property phù hợp.
- [ ] `@ApplicationModuleListener` được kiểm thử sau transaction commit.
- [ ] Scenario có timeout và cleanup dữ liệu phát sinh.
- [ ] Trace ID của listener khớp parent trace khi propagation được bật.
- [ ] Test chấp nhận child span có span ID khác parent.
- [ ] HTTP client inject W3C traceparent hợp lệ.
- [ ] Reactor context được kiểm thử nếu ứng dụng dùng reactive pipeline.
- [ ] Global registry/accessor được cleanup sau test.
- [ ] Executor, latch, server và resource đều được đóng.
- [ ] Không dùng sleep hoặc executor đồng bộ để giả lập async behavior.

## 16. Ghi nhớ

- Context propagation phải được kiểm thử tại ranh giới thực thi: thread, Reactor, HTTP và async event listener.
- Context Propagation không tự truyền mọi ThreadLocal; ứng dụng cần đăng ký `ThreadLocalAccessor` cho context riêng.
- `ContextPropagatingTaskDecorator` phải được gắn vào đúng executor và scope phải được khôi phục sau task.
- Với Spring Boot 4.x, `spring.task.execution.propagate-context` bật propagation cho auto-configured executor; executor tùy chỉnh cần decorator.
- Với Spring Boot 3.5, tài liệu hướng dẫn đăng ký decorator trên executor.
- `@ApplicationModuleListener` chạy bất đồng bộ sau transaction commit; dùng `Scenario` để kiểm thử event một cách xác định.
- So sánh trace ID và quan hệ parent/child, không yêu cầu span ID của child giống parent.
- Kiểm tra cả context leakage, exception path và worker thread reuse để tránh lỗi chỉ xuất hiện khi tải thực tế.

## Tài liệu tham khảo

1. [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Context propagation cho async executor và Reactor trong Boot hiện hành.
2. [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html) — ContextPropagatingTaskDecorator và propagation trong Boot 3.5.
3. [Spring Framework — ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html) — Cách decorator wrap task và phục hồi logging/observation context.
4. [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html) — ThreadLocalAccessor, ContextRegistry, ContextSnapshot và các context boundary.
5. [Micrometer Context Propagation — Examples](https://docs.micrometer.io/context-propagation/reference/usage.html) — Ví dụ đăng ký accessor và capture/restore ThreadLocal.
6. [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html) — @ApplicationModuleTest, Scenario và kiểm thử transactional asynchronous event handling.
7. [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — @ApplicationModuleListener, transaction và async event handling.
8. [W3C Trace Context](https://www.w3.org/TR/trace-context/) — Định dạng traceparent/tracestate và quy tắc truyền trace context giữa services.

