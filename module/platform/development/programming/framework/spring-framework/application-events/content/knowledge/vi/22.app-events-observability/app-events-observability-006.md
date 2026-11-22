# Trace context khi event bất đồng bộ trong Spring Framework

## 1. Vì sao trace có thể “đứt” khi xử lý event trên thread khác?

Trong hệ thống **Spring Framework Application Events**, một event thường được phát từ request HTTP, background job hoặc use case đang mang thông tin quan sát như **trace ID**, **span hiện tại**, **correlation ID**, **baggage** và một số trường **MDC** của logger. Khi listener chạy **đồng bộ trên cùng thread**, các giá trị gắn với **ThreadLocal** thường vẫn có sẵn.

Nhưng nếu Spring dispatch listener sang **thread của executor**, hoặc method listener có **@Async**, thread nhận việc **không tự nhận ThreadLocal** của thread phát event. Hệ quả thường thấy:

- Log của publisher có **traceId/spanId**, log của listener không có hoặc xuất hiện một trace mới không liên quan.
- APM/tracing hiển thị một khoảng trống giữa xử lý request và tác vụ nhận event.
- Không nối được thời gian xử lý, lỗi và các span của cùng một workflow.
- Trường correlation/tenant được lưu bằng ThreadLocal có thể biến mất hoặc, nếu tự copy sai, **rò rỉ giữa các tác vụ** trên thread pool.
- Người vận hành hiểu nhầm là listener chưa chạy, dù thực tế listener vẫn hoàn thành nhưng mất thông tin liên kết.

**Trace context propagation** là quá trình **chụp ngữ cảnh tại điểm gửi việc** và **khôi phục ngữ cảnh phù hợp trong phạm vi xử lý ở thread nhận việc**, rồi **trả lại trạng thái cũ** khi xử lý kết thúc. Trong Spring Framework 6.1+, công cụ hữu ích cho các **TaskExecutor** là **ContextPropagatingTaskDecorator**, kết hợp thư viện **Micrometer Context Propagation**.

Mục tiêu bài học: hiểu chính xác **vì sao context đứt**, **chọn nơi cấu hình propagation**, **kiểm tra bằng một ví dụ Java 17+ chạy được**, và **không nhầm truyền context với tạo span, chuyển transaction hay bảo đảm delivery**.

## 2. Những loại “context” dễ bị nhầm

| Khái niệm | Công dụng | Có tự qua thread pool không? |
| --- | --- | --- |
| **Trace ID** | Nhận diện trace end-to-end gồm nhiều spans | Không nếu chỉ nằm trong ThreadLocal mà không có cơ chế propagation |
| **Span ID / current span** | Nhận diện span hoặc span context hiện tại | Phải có tracer/observation context được capture/restore đúng cách |
| **MDC** (Mapped Diagnostic Context) | Bổ sung trường vào log, thường có traceId, spanId, requestId | Thường là thread-local; không tự truyền sang executor |
| **Correlation ID** | Gắn các thao tác cùng nghiệp vụ/yêu cầu; có thể là field event | Nếu chỉ nằm trong ThreadLocal thì không; nếu là field của payload thì có thể đọc trực tiếp |
| **Baggage** | Metadata được phép truyền theo trace context | Cần propagation được cấu hình; hạn chế kích thước và dữ liệu nhạy cảm |
| **SecurityContext** | Thông tin xác thực/ủy quyền của Spring Security | Cần cơ chế riêng được thiết kế cho security; không mặc định chỉ nhờ tracing decorator |
| **Transaction context** | Transaction manager, resource binding và synchronization | **Không** được chuyển sang worker thread chỉ vì trace context được truyền |
| **Reactor Context** | Context của luồng reactive | Khác ThreadLocal; cần bridge/cơ chế Reactor khi qua ranh giới reactive–imperative |

**Trace ID và correlation ID không hoàn toàn tương đương.** Trace ID do tracer quản lý và có ngữ nghĩa về trace/span hierarchy. Correlation ID là khóa nghiệp vụ hoặc khóa hỗ trợ log, có thể được truyền bằng event payload hoặc header. Một ví dụ sử dụng một String **trace-like ID** chỉ minh họa khả năng truyền ThreadLocal; nó **không tự tạo một distributed trace thật**.

**MDC cũng không phải tracer.** Việc copy một chuỗi **traceId** vào MDC có thể làm log dễ tìm hơn, nhưng nếu không có tracer đang quản lý current span, hệ thống APM chưa chắc có span hay parent-child relationship.

## 3. Mặc định của Spring: event đồng bộ, không tự tách thread

Spring ApplicationContext thường dùng **SimpleApplicationEventMulticaster** để phân phối application events. **Mặc định multicaster dispatch đồng bộ** trên thread của caller; **publishEvent(...)** thường chỉ trả về sau khi các listener đồng bộ đã xử lý xong.

~~~text
Thread HTTP/request                    Event listener mặc định
----------------------------------     -------------------------------
current trace/span = T, S
MDC traceId = T
  |
  +-- publishEvent(OrderCreated)
          |
          +-------------------------> @EventListener on(OrderCreated)
                                      (cùng thread)
                                      current trace/span có thể còn sẵn
                                      MDC cũng là context của thread này
          |
          +-- listener trả về
  |
  +-- request tiếp tục
~~~

Trong cấu hình này, bạn **không cần một TaskDecorator chỉ để đi qua event listener đồng bộ** vì không có ranh giới thread. Tuy nhiên Spring Framework **không mặc định tạo Observation/span cho từng lời gọi @EventListener**; việc cùng thread giữ được context chỉ là có quyền truy cập context hiện tại, không đồng nghĩa có một span listener riêng.

### Khi nào ranh giới thread xuất hiện?

**Trường hợp A — multicaster được cấu hình executor:**

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster multicaster(TaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(eventExecutor);
    return m;
}
~~~

Đây là đoạn minh họa trong Spring configuration. Với **TaskExecutor** thực thi async, nhiều application listeners đủ điều kiện chạy ở thread khác.

**Trường hợp B — listener riêng gắn @Async:**

~~~java
@Async("traceAwareExecutor")
@EventListener
public void on(OrderCreated event) {
    // Method được giao cho executor thay vì luôn chạy trong publisher thread.
}
~~~

Đoạn này cần **@EnableAsync**, Spring-managed bean, executor tên phù hợp, imports và event type. Ở cả hai trường hợp, giá trị ThreadLocal của publisher **không thể được giả định có sẵn** trong listener.

**Ngoại lệ quan trọng:** không phải *mọi* listener đều được phép chạy async khi multicaster có executor. Spring có **ApplicationListener.supportsAsyncExecution()**; ví dụ listener đồng bộ hóa transaction có thể phải chạy trong thread publisher để đăng ký callback đúng transaction. Đừng hiểu cấu hình executor toàn cục là “mọi @TransactionalEventListener đều chạy ngay trên worker”.

## 4. Vì sao ThreadLocal không tự được truyền?

**ThreadLocal<T>** giữ giá trị tương ứng với từng thread. Thread gọi **publishEvent(...)** có thể đang chứa current observation, tracer span hoặc MDC; thread của **ThreadPoolTaskExecutor** là thread khác có vùng ThreadLocal riêng.

~~~text
Publisher thread [http-42]
  ThreadLocal("trace") = trace-abc
  |
  +-- queue event task ----------------------+
                                            |
                              Worker thread [event-1]
                                ThreadLocal("trace") = null
                                @EventListener bắt đầu xử lý
~~~

Khi dùng thread pool, thread xử lý sự kiện còn có thể **được tái sử dụng cho sự kiện tiếp theo**. Nếu code tự đặt giá trị mà không restore/clear trong finally, event B có thể vô tình nhìn thấy dữ liệu của event A. Đây không chỉ là vấn đề log sai; có thể dẫn tới **rò rỉ dữ liệu chéo request/tenant**.

**InheritableThreadLocal** không phải cách sửa an toàn chung: thread pool có thể tạo thread trước request, giữ giá trị kế thừa từ thời điểm tạo và tái sử dụng cho nhiều task. Trace context đúng phải được **capture tại thời điểm schedule một task cụ thể** và **restore trong scope của chính task đó**.

## 5. Giải pháp tiêu chuẩn: ContextPropagatingTaskDecorator

**ContextPropagatingTaskDecorator** (Spring Framework 6.1+) implement **TaskDecorator**. Nó dùng **Micrometer Context Propagation** để capture những context values có **ThreadLocalAccessor** được đăng ký, và restore chúng trong phạm vi thực thi task ở worker.

Mô hình:

~~~text
Publisher thread
  current trace/observation/baggage
  |
  +-- executor.execute(task)
          |
          v
     ContextPropagatingTaskDecorator
          -> capture ContextSnapshot tại scheduling boundary
          -> wrap Runnable
                    |
                    v
               Worker thread
                 -> restore context
                 -> invoke listener
                 -> restore/cleanup previous worker context
~~~

Phụ thuộc cần có nếu dùng chính decorator này:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'io.micrometer:context-propagation:1.1.3'
}
~~~

Đây là **đoạn dependency minh họa**, không phải toàn bộ build file. Ngoài thư viện, **context cần được đăng ký accessor** tương ứng. Với Spring Boot và Micrometer Tracing đã cấu hình, framework/instrumentation thường đăng ký các accessors phù hợp cho Observation/trace context. Với custom ThreadLocal, ứng dụng phải đăng ký accessor riêng nếu muốn snapshot capture được nó.

**Giới hạn:** decorator **không tự tạo span**, **không tự cài tracer/exporter**, **không đưa transaction sang thread mới** và không tự làm cho mọi field MDC được propagate. Nó chỉ chụp/khôi phục các **context sources** mà Micrometer Context Propagation có accessor hỗ trợ. Việc bắt toàn bộ MDC có thể xung đột với tracing-aware MDC management; không đăng ký bừa một MDC accessor thứ hai khi tracer đã có cơ chế cập nhật MDC.

### 5.1. Với ApplicationEventMulticaster có executor

~~~java
@Configuration
class EventMulticasterConfig {

    @Bean
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster eventMulticaster(
            ThreadPoolTaskExecutor eventExecutor) {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
~~~

Đây là **config snippet**, cần các Spring imports. Trong bean **ThreadPoolTaskExecutor** do Spring quản lý, container thường tự gọi lifecycle initialization và destruction. Trong production phải cân nhắc pool size, queue capacity, reject policy, timeout và shutdown. Cấu hình này có phạm vi rộng: nó ảnh hưởng đến những listeners đủ điều kiện xử lý async trên toàn context.

### 5.2. Với từng @Async @EventListener

Khi chỉ một vài listeners cần chạy async, có thể dùng executor được chỉ định:

~~~java
@Configuration
@EnableAsync
class AsyncEventConfig {

    @Bean("traceAwareExecutor")
    ThreadPoolTaskExecutor traceAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("trace-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Và listener:

~~~java
@Component
class EmailEventListener {

    @Async("traceAwareExecutor")
    @EventListener
    public void on(OrderConfirmed event) {
        // Current observation/trace context được khôi phục nếu có
        // Micrometer accessor và tracing configuration phù hợp.
    }
}
~~~

Đây đều là **đoạn minh họa** phải bổ sung imports, event type và bean wiring. **@EnableAsync** là cần thiết cho cơ chế xử lý **@Async** qua Spring proxy. Đừng kỳ vọng annotation hoạt động trên object tự tạo bằng **new**, hoặc khi gọi method annotated từ cùng class qua self-invocation bỏ qua proxy.

**Khuyến nghị:** chọn **một boundary thực thi** cho event: hoặc multicaster gửi tới một executor, hoặc listener cụ thể được @Async. Cấu hình cả hai mà không tính đến double scheduling làm đường đi context, lỗi và shutdown khó hiểu hơn.

## 6. Ví dụ hoàn chỉnh Java 17+: kiểm chứng propagation qua event listener async

Ví dụ sau chạy với **Spring Framework 6.2.9**, **Micrometer Context Propagation 1.1.3**, **JDK 17+**, **Gradle 8.x**. Nó cố ý dùng một **ThreadLocal chứa correlation ID mô phỏng trace** để bạn thấy rõ cơ chế capture/restore mà không cần cài tracing backend hay network.

**Đây là minh họa truyền context, không phải distributed trace hoàn chỉnh:** String **trace-42** không phải W3C trace ID, không có Span exporter hay parent/child spans. Sau demo, phần tiếp theo chỉ ra cách áp dụng với Micrometer Tracing thực sự.

### 6.1. Cấu trúc

~~~text
async-event-trace-demo/
  build.gradle
  src/main/java/demo/AsyncEventTraceDemo.java
~~~

Nội dung **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'io.micrometer:context-propagation:1.1.3'
}

application {
    mainClass = 'demo.AsyncEventTraceDemo'
}
~~~

### 6.2. Mã nguồn chạy được

Nội dung **src/main/java/demo/AsyncEventTraceDemo.java**:

~~~java
package demo;

import io.micrometer.context.ContextRegistry;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventTraceDemo {

    // Chuỗi minh họa trace-like correlation ID, KHÔNG phải Tracer thực.
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record WorkRequested(String id) {}

    public static final class Probe {
        private final ConcurrentHashMap<String, String> seen =
                new ConcurrentHashMap<>();
        private final ConcurrentHashMap<String, Boolean> onEventThread =
                new ConcurrentHashMap<>();
        private final CountDownLatch done = new CountDownLatch(2);

        @EventListener
        public void on(WorkRequested event) {
            String id = TRACE_ID.get();
            seen.put(event.id(), id == null ? "missing" : id);
            onEventThread.put(
                    event.id(),
                    Thread.currentThread().getName().startsWith("event-"));
            done.countDown();
        }

        public void awaitEvents() throws InterruptedException {
            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("event listener timed out");
            }
        }

        public String traceFor(String id) {
            return seen.get(id);
        }

        public boolean wasAsync(String id) {
            return Boolean.TRUE.equals(onEventThread.get(id));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        SimpleApplicationEventMulticaster eventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {
            SimpleApplicationEventMulticaster m =
                    new SimpleApplicationEventMulticaster();
            m.setTaskExecutor(eventExecutor);
            return m;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }
    }

    private static String display(String value) {
        return value == null ? "missing" : value;
    }

    public static void main(String[] args) throws Exception {
        // Micrometer cần biết CÁCH đọc/đặt/xóa ThreadLocal tự tạo.
        ContextRegistry.getInstance().registerThreadLocalAccessor(
                "demo.trace-id", TRACE_ID);

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Probe probe = context.getBean(Probe.class);
            var plainExecutor = Executors.newSingleThreadExecutor();

            try {
                TRACE_ID.set("trace-42");

                // Không có propagation: thread khác không thấy TRACE_ID.
                String raw = CompletableFuture.supplyAsync(
                        TRACE_ID::get, plainExecutor)
                        .get(5, TimeUnit.SECONDS);
                System.out.println("plain executor: " + display(raw));

                // Executor của event multicaster CÓ TaskDecorator.
                context.publishEvent(new WorkRequested("A"));

                TRACE_ID.remove();
                context.publishEvent(new WorkRequested("B"));

                // Chờ cả hai event để stdout độc lập thứ tự scheduling.
                probe.awaitEvents();

                System.out.println("listener A trace: "
                        + probe.traceFor("A"));
                System.out.println("listener A async: "
                        + probe.wasAsync("A"));
                System.out.println("listener B trace: "
                        + probe.traceFor("B"));
                System.out.println("publisher cleared: "
                        + display(TRACE_ID.get()));
            }
            finally {
                TRACE_ID.remove();
                plainExecutor.shutdownNow();
            }
        }
        finally {
            ContextRegistry.getInstance().removeThreadLocalAccessor(
                    "demo.trace-id");
        }
    }
}
~~~

Lệnh chạy tại thư mục **async-event-trace-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình tự in ra** (bỏ qua log khác của Gradle hoặc Spring nếu môi trường tự thêm):

~~~text
plain executor: missing
listener A trace: trace-42
listener A async: true
listener B trace: missing
publisher cleared: missing
~~~

### 6.3. Giải thích chính xác

1. **ContextRegistry** được đăng ký một **ThreadLocalAccessor** cho **TRACE_ID** bằng key **demo.trace-id** trước khi tạo ApplicationContext.
2. **plainExecutor** không có context propagation. Khi main thread đặt **trace-42**, thread của plainExecutor vẫn không có giá trị này, nên dòng đầu in **missing**.
3. **eventExecutor** là một Spring-managed **ThreadPoolTaskExecutor** có **ContextPropagatingTaskDecorator**. Ở thời điểm **context.publishEvent(WorkRequested("A"))**, nó capture ThreadLocal hiện tại của publisher.
4. Listener **Probe.on(...)** chạy trên thread tên bắt đầu bằng **event-**; decorator restore **trace-42** trong phạm vi task A nên recorder thấy đúng chuỗi.
5. Main thread xóa **TRACE_ID** rồi publish event B. Task B không có trace ID; worker đã được restore về trạng thái trước đó sau task A, vì vậy **listener B trace: missing**. Điều này minh họa việc tránh rò rỉ ThreadLocal giữa tasks.
6. **CountDownLatch** đợi listener xử lý cả A và B, rồi main mới in kết quả. Vì các listener không tự in ra stdout, thứ tự các dòng cố định ngay cả khi scheduler thay đổi thời điểm thực thi.
7. **ContextRegistry.removeThreadLocalAccessor(...)** được gọi sau khi context đóng, dọn đăng ký mẫu của demo. Executor Spring-managed sẽ được dọn theo lifecycle container.

**Kiểm tra kỳ vọng của demo:** nếu bỏ dòng **executor.setTaskDecorator(new ContextPropagatingTaskDecorator())**, event A không còn được bảo đảm thấy **trace-42**. Demo cố tình không có tracer thực để chỉ ra propagation không phải là chức năng của Java ThreadLocal tự thân.

**Một hạn chế có chủ ý:** demo không đưa dữ liệu qua HTTP hoặc broker, không có sampling/OTLP exporter. Nó chỉ chứng minh cơ chế cần thiết để một **registered context value** đi qua ranh giới thread.

## 7. Áp dụng cho trace/span thực sự với Micrometer Tracing

Khi ứng dụng dùng **Spring Boot Actuator + Micrometer Observation/Tracing** đã cấu hình, luồng quan sát thường gồm:

~~~text
HTTP server request
  -> observation/span cha được tạo
  -> current Observation/Span trong thread request
  -> publisher.publishEvent(OrderPlaced)
  -> executor với ContextPropagatingTaskDecorator
  -> event listener có thể nhận current trace context
  -> có thể tạo một Observation/span con để đo xử lý event
  -> log MDC có thể chứa traceId/spanId theo tracer configuration
~~~

Điều kiện:

- Có **tracing bridge/provider** phù hợp (ví dụ Micrometer Tracing bridge sang OpenTelemetry hoặc Brave), sampling và exporter nếu muốn thấy trace trên APM.
- Các accessors dành cho **current Observation/trace context** đã được đăng ký đúng vào **Micrometer ContextRegistry**.
- **Executor thực sự chạy listener** có task decorator; không chỉ tạo một bean decorator nhưng lại dùng executor khác.
- Listener cần một **Observation/span mới nếu muốn biểu diễn một operation riêng**. Propagation chỉ mang **parent/current context** qua thread boundary; nó không tự tạo một span **event.consume**.

Ví dụ **snippet trong Spring Boot có ObservationRegistry**:

~~~java
@Component
public class TracedBusinessListener {
    private final ObservationRegistry observationRegistry;

    public TracedBusinessListener(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    @Async("traceAwareExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        Observation.createNotStarted(
                "business.order.placed.listener", observationRegistry)
                .observe(() -> process(event));
    }

    private void process(OrderPlaced event) {
        // Đọc event và xử lý bước nhỏ, không dựa vào transaction caller.
    }
}
~~~

Đoạn trên **không phải file độc lập**; cần imports **io.micrometer.observation.Observation**, **ObservationRegistry**, Spring annotations, **OrderPlaced**, executor có propagation, **@EnableAsync** và cấu hình tracing/observability phù hợp. Khi tracing được kết nối với ObservationRegistry, observation có thể tạo span riêng trong trace hiện tại. Trong demo nhỏ không có tracer, chỉ sử dụng Observation không bảo đảm APM nhận được span.

Khi kiểm tra trace ID từ tracer thực:

~~~java
Span current = tracer.currentSpan();
String traceId = current == null
        ? "no-active-span"
        : current.context().traceId();
~~~

Đây là **snippet minh họa** yêu cầu **io.micrometer.tracing.Tracer** và **Span** từ Micrometer Tracing, cùng bean tracer do ứng dụng cấu hình. Nó là API đọc **trace ID thực**, khác với ThreadLocal String của demo.

### 7.1. Cần trace liền mạch hay một span con?

Nếu listener chỉ cần log cùng trace, việc **khôi phục current context** đã giúp correlation. Nếu muốn đo duration/error của bước handler một cách độc lập, tạo một **span/Observation con**. Khi đó trace ID có thể giữ nguyên, còn span ID của operation mới **khác parent span ID**.

**Đừng assert rằng span ID phải giống nhau giữa publisher và listener** trong mọi kiến trúc. Mục tiêu đúng thường là **cùng trace ID và quan hệ parent/child hợp lệ** theo tracing backend. Một event được publish sau khi request đã kết thúc vẫn có thể cần mô hình async span/link thích hợp; semantics phụ thuộc instrumentation.

### 7.2. MDC không phải điểm tích hợp duy nhất

Logger có thể lấy **traceId/spanId** từ MDC được tracer quản lý. Không nên chỉ cấu hình **MDC.put("traceId", ...)** rồi giả định tracer đã nắm được parent context. Ngoài ra không đăng ký một **Slf4jThreadLocalAccessor** copy toàn bộ MDC khi stack tracing đã đăng ký accessor quản lý MDC theo Observation; việc có **hai accessors cùng thay đổi MDC** có thể gây xung đột/corruption ngữ cảnh. Nếu cần một custom correlation ID khác, cân nhắc đưa ID vào event field hoặc đăng ký accessor riêng có phạm vi rõ.

## 8. Khác biệt giữa global async multicaster và @Async listener

| Thuộc tính | Multicaster có task executor | @Async("traceAwareExecutor") |
| --- | --- | --- |
| Phạm vi | Các listener được phép chạy async trên toàn context | Chỉ method/class được chú thích và gọi qua Spring proxy |
| Nơi đặt decorator | Executor được truyền cho **SimpleApplicationEventMulticaster.setTaskExecutor(...)** | Executor được chọn bởi tên/qualifier của **@Async** |
| Thread publisher | Thường không chờ listeners async hoàn tất | Thường không chờ method async hoàn tất |
| Giá trị ThreadLocal tự động có? | Không, trừ khi executor được trang bị propagation | Không, trừ khi executor được trang bị propagation |
| Listener không hỗ trợ async | Có thể vẫn chạy trên publisher thread | Cơ chế annotation/proxy áp dụng tùy listener và hợp đồng |
| Hành vi exception | Exception của listener trên worker không tự truyền về publisher | Exception của void async method không tự truyền về publisher |
| Thứ tự hoàn tất | Không chắc nếu nhiều tasks/threads | Không chắc nếu nhiều tasks/threads |
| Return value @EventListener tạo next event | Dựa vào listener adapter và hỗ trợ sync; không dùng return để thiết kế chain async | **Không hỗ trợ** publication bằng giá trị trả về của async listener |
| Transaction propagation | Không truyền transaction của caller sang worker | Không truyền transaction của caller sang worker |

**Lưu ý:** Có những transaction-synchronized listeners cố ý phải chạy ở thread phát event để đăng ký callback. Điều này không có nghĩa phần code nghiệp vụ ở phase sau commit được quyền dùng lại transaction cũ. Luôn phân biệt **đăng ký callback**, **thread chạy handler** và **transaction thực sự khả dụng**.

## 9. Không truyền TransactionContext cùng trace context

Một nhầm lẫn nguy hiểm:

> “Đã dùng ContextPropagatingTaskDecorator nên @Transactional ở publisher cũng được truyền vào async listener.”

**Sai.** Transaction imperative trong Spring thường dùng **TransactionSynchronizationManager** và resources gắn với thread. Trace propagation không chuyển transaction connection/rollback boundary sang worker thread.

~~~text
Publisher thread
  @Transactional
  save(order)
  publishEvent(OrderPlaced)
         |
         +--> Async listener trên worker
                  -> có thể thấy trace/correlation context
                  -> KHÔNG tự ở trong DB transaction của publisher
  commit / rollback theo transaction gốc
~~~

Nếu listener cần thao tác DB, nó phải có transaction riêng qua service thích hợp (ví dụ service **@Transactional** được gọi qua Spring proxy). Nếu phản ứng phải chỉ chạy khi publisher transaction commit thành công, cần cân nhắc **@TransactionalEventListener(phase=AFTER_COMMIT)** hoặc **transactional outbox**.

**@TransactionalEventListener** đăng ký callback theo transaction khi event được publish; không mặc định tự tạo một durable queue. Khi chạy ở phase hậu commit, cần cẩn thận nếu muốn ghi DB thay đổi mới: thường phải có transaction mới (**REQUIRES_NEW**) để commit độc lập. Với event quan trọng không được mất sau crash, outbox vẫn thích hợp hơn callback memory-only.

Nếu message được xử lý trên thread khác nhưng transaction của publisher rollback, trace context vẫn có thể được truyền, khiến log “cùng trace” dù business transaction thất bại. **Trace correlation không phải business consistency**.

## 10. Trong hệ thống phân tán: qua message broker không dùng ThreadLocal trực tiếp

**ContextPropagatingTaskDecorator** giải quyết ranh giới **TaskExecutor trong một JVM**. Khi event rời process qua Kafka, RabbitMQ, JMS, HTTP hoặc gRPC, không có chung ThreadLocal; phải dùng **distributed context propagation** phù hợp giao thức.

Thông thường:

1. Producer có trace/span context hiện tại.
2. Propagator **inject** context vào message headers/carrier (ví dụ W3C **traceparent**, **tracestate** và baggage được cho phép).
3. Broker vận chuyển message; nó không tự biến Java ThreadLocal thành headers.
4. Consumer **extract** context từ headers.
5. Consumer mở span/Observation thích hợp và xử lý message trong scope đó.
6. Mỗi hop giữ correlation/trace relationships, đồng thời ghi kết quả, lỗi và retry theo semantics đúng.

~~~text
service A / publisher
   current trace/span
       |
       +-- inject headers { traceparent, tracestate, baggage? }
                       |
                       v
                   message broker
                       |
                       v
service B / consumer
       extract headers
       -> start consumer Observation/span
       -> process event
       -> close scope and finish span
~~~

**Không serialize nguyên object Span, Tracer hoặc SecurityContext** vào message. Chỉ truyền các headers tiêu chuẩn/được kiểm soát, hạn chế baggage chứa thông tin nhạy cảm, áp dụng chính sách trust với headers nhận từ bên ngoài và không giả định mọi hệ thống ở downstream đều giữ cùng sampling decision.

Trong Spring Boot và hệ sinh thái messaging, có thể có instrumentation tự động cho HTTP/messaging tùy starter và cấu hình. Nếu không thấy trace xuyên broker, trước tiên kiểm tra **inject/extract headers** và consumer instrumentation, không chỉ TaskDecorator của event multicaster.

## 11. Truyền context không đồng nghĩa đảm bảo thực thi

Một async event listener có trace chính xác vẫn có thể:

- Bị executor từ chối do pool/queue đầy.
- Chưa kịp chạy khi application shutdown.
- Ném exception mà publisher không nhận.
- Bị process kill giữa chừng.
- Nhận duplicate event sau retry nếu event được gửi qua broker.
- Tạo side effect trước khi DB transaction của publisher commit.

Vì vậy cần tách ba câu hỏi:

| Câu hỏi | Cơ chế thường dùng |
| --- | --- |
| **Log và span của listener có cùng trace/correlation không?** | Context propagation, Observation/Tracing, MDC integration |
| **Task có được chạy và xử lý lỗi không?** | Executor policy, exception handler, monitoring, retry |
| **Task không được mất sau crash và phải xử lý nhất quán?** | Persistent queue/outbox, idempotency, transaction boundaries |

Nếu ứng dụng cần đảm bảo phát event sau commit, cân nhắc **transactional outbox** hoặc một cơ chế bền vững. **@Async** và **ContextPropagatingTaskDecorator** không thay thế việc này.

## 12. Các rủi ro về thời gian, lifecycle và performance

### 12.1. Snapshot được capture khi schedule

Với TaskDecorator, context được capture tại **thời điểm task được giao cho executor**. Nếu publisher thay đổi ThreadLocal ngay sau **publishEvent(...)**, task được decorate vẫn dùng snapshot đã capture tại thời điểm schedule. Đây là lý do demo A có **trace-42** dù main xóa ThreadLocal trước khi worker có thể chạy.

**Đừng truyền object mutable lớn bằng custom ThreadLocalAccessor** rồi mong snapshot là deep copy bất biến. Nếu context value là một object mutable, snapshot có thể chỉ giữ reference. Chọn dữ liệu nhỏ/immutable hoặc có cơ chế copy an toàn.

### 12.2. Scope khôi phục và tránh rò rỉ

Một implementation propagation đúng phải **khôi phục/clear context** sau khi task kết thúc, kể cả khi listener ném exception. Micrometer ContextSnapshot cung cấp scope phục hồi; tránh tự dùng **MDC.setContextMap(...)** mà không lưu và restore trạng thái trước đó.

Nếu tự viết TaskDecorator cho custom data:

~~~java
TaskDecorator decorator = runnable -> {
    String captured = MY_CONTEXT.get();
    return () -> {
        String previous = MY_CONTEXT.get();
        try {
            if (captured == null) {
                MY_CONTEXT.remove();
            } else {
                MY_CONTEXT.set(captured);
            }
            runnable.run();
        } finally {
            if (previous == null) {
                MY_CONTEXT.remove();
            } else {
                MY_CONTEXT.set(previous);
            }
        }
    };
};
~~~

Đây là **snippet minh họa** cần biến **MY_CONTEXT** và imports; chỉ phù hợp với một ThreadLocal được kiểm soát. Với tracing thực (Observation, Span, baggage, MDC), ưu tiên **ContextPropagatingTaskDecorator** và accessors đã được tích hợp, không tự xây lại toàn bộ trace propagation.

### 12.3. Context propagation có chi phí

Snapshot/capture/restore tạo overhead. Theo Javadoc Spring, decorator đặc biệt hữu ích khi thực thi trên thread khác nhưng không nên mặc định dùng cho hàng triệu tasks cực nhỏ mà không đo lường. Đo latency, queue wait, CPU/allocations, sampling và số lượng fields cần propagate.

Một **trace ID** giúp truy vết; nó không chữa nghẽn executor. Nên monitor active threads, queue depth, rejection count, handler duration, error count và thời gian shutdown.

## 13. Kiểm thử đúng trace propagation

### 13.1. Kiểm thử hai ranh giới

Một integration test nên kiểm tra:

1. Khi listener **đồng bộ**, current trace context vẫn có sẵn theo publisher thread nếu instrumentation đang active.
2. Khi listener được dispatch lên **executor trần**, context ThreadLocal chỉ có ở publisher và thường thiếu ở worker.
3. Khi executor được gắn **ContextPropagatingTaskDecorator** và accessor tương ứng, correlation ID/trace ID đúng trên worker.
4. Sau task A, task B không tự mang context của A nếu publisher không có trace.
5. Khi listener ném exception, context vẫn được restore, không làm bẩn task tiếp theo.
6. Với **@Async("traceAwareExecutor")**, kiểm tra executor thực sự được Spring chọn và listener chạy trên worker.
7. Với Micrometer Tracing thật, kiểm tra cùng **trace ID** và quan hệ spans đúng, không áp đặt same span ID.
8. Với message broker, kiểm tra **traceparent injection/extraction**; TaskDecorator trong process không đủ.
9. Kiểm tra error/retry/shutdown ngoài propagation: task bị từ chối, listener lỗi, caller không chờ, duplicate.
10. Kiểm tra privacy: baggage/headers không chứa mật khẩu, token hoặc thông tin người dùng ngoài whitelist.

### 13.2. Dùng CountDownLatch hoặc công cụ chờ có điều kiện

Async listener có thể chạy trước hoặc sau khi **publishEvent(...)** trả về; không viết test kiểu “Thread.sleep(100)” rồi kết luận trace đã truyền. Ví dụ mục 6 dùng **CountDownLatch** và **ConcurrentHashMap** để xác nhận kết quả sau khi listener hoàn tất, loại bỏ phụ thuộc scheduling.

Nếu test trace thực, sử dụng tracing test handler/exporter hoặc in-memory span collector phù hợp để kiểm tra **span relationships**. Test không nên chỉ khớp chuỗi log nếu tracing backend có sampling/filters khác nhau.

### 13.3. Điều cần xác nhận trong dashboard/APM

Với trace ví dụ **checkout-submit**, kiểm tra:

- Publisher/request span có trace ID hợp lệ.
- Async listener operation có trace ID liên kết với publisher theo cấu hình.
- Span listener (nếu được tạo) có name rõ, duration, status/error và parent/link hợp lý.
- Logs của listener có correlation đúng; không có trường traceId của request trước do thread reuse.
- Với sampling, không coi thiếu span được export là chắc chắn không chạy code; đối chiếu metrics/logs.
- Retry và redelivery có thể tạo **attempt spans** khác nhau, nhưng vẫn được gắn với workflow/business ID.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ **@Async tự copy MDC/trace** | Listener chạy nhưng log không có trace | Executor có propagation, tracer/accessors được cấu hình |
| Cấu hình decorator trên executor không được dùng | Không thay đổi gì | Xác nhận đúng executor của multicaster hoặc **@Async** qualifier |
| Dùng **InheritableThreadLocal** với thread pool | Dữ liệu sai/stale hoặc rò rỉ giữa request | Capture tại scheduling boundary, restore theo scope |
| Copy **traceId** string rồi nghĩ có distributed tracing | Log giống nhau nhưng không có span hierarchy | Dùng tracer/Observation, propagator và instrumentation |
| Đăng ký MDC accessor trùng với tracing integration | Gây xung đột MDC/context | Kiểm tra accessors có sẵn; chỉ thêm những gì cần thiết |
| Tưởng decorator truyền luôn **@Transactional** | Listener tưởng đang ở transaction cũ | Transaction riêng và AFTER_COMMIT/outbox khi cần |
| Dùng @TransactionalEventListener + @Async không hiểu thời điểm | Nhầm đăng ký callback với handler execution | Tách transaction phase, async executor và kết quả commit |
| Propagate toàn bộ baggage, user secrets | Privacy/security risk, headers quá lớn | Whitelist fields, redact và đặt giới hạn |
| Bỏ quên scope cleanup trong custom decorator | Worker thread giữ context của request trước | try/finally restore trước/sau task |
| Không chờ listener trong test | Test flaky hoặc kết luận sai | CountDownLatch/Awaitility, in-memory trace exporter |
| Cho rằng đúng trace thì event không mất | Async task vẫn có thể bị kill/drop | Queue/outbox, retry, idempotency |
| Quên broker header propagation | Trace đứt giữa microservices | W3C propagation inject/extract ở producer/consumer |
| Dùng một span chung cho mọi việc mà không đặt span riêng | Không thấy thời gian handler | Tạo Observation/span cho bước cần đo |
| Quá nhiều context fields và decorator ở mọi microtask | Overhead latency/allocations | Đo benchmark, giảm fields, chọn boundaries quan trọng |
| Chỉ đọc MDC nhưng tracer chưa được cài | Có chuỗi traceId “giả”, dashboard không có trace | Xác minh Micrometer Tracing bridge và exporter |

## 15. Checklist triển khai production

Trước khi triển khai một async event listener, hãy trả lời:

1. **Event được xử lý đồng bộ hay bất đồng bộ?** Multicaster executor hay **@Async**?
2. **Executor thực tế có ContextPropagatingTaskDecorator không?** Có dùng đúng tên/qualifier và bean không?
3. **Trace/Observation/ThreadLocal accessors đã được đăng ký chưa?** Không mặc định mọi MDC key tự được capture.
4. **Trace là context thực từ tracer hay chỉ correlation ID dạng String?** Hai thứ khác nhau.
5. **Có tạo Observation/span riêng cho handler khi cần quan sát latency không?**
6. **Khi thread pool tái sử dụng thread, context cũ có được restore/clear trong finally không?**
7. **Có phụ thuộc transaction của publisher không?** Nếu có, thiết kế lại transaction boundary.
8. **Có đi qua broker/HTTP không?** Nếu có, phải inject/extract trace headers; TaskDecorator chưa đủ.
9. **Có bảo vệ baggage/metadata nhạy cảm không?** Whitelist, giới hạn dung lượng, không log toàn payload.
10. **Nếu executor từ chối, listener lỗi hoặc process chết, nghiệp vụ có phục hồi được không?** Dùng monitoring/outbox/queue phù hợp.
11. **Đã kiểm thử async một cách deterministic chưa?** Có latch, trace exporter test và so sánh trace relationship?
12. **Có đo overhead và queue behavior không?** Tránh thêm decorator/tracing vào mọi tác vụ siêu nhỏ mà không có mục đích.

**Kết luận:** Khi Spring event listener chạy trên thread khác, **ThreadLocal/MDC/current span không tự được mang theo**. Trong Spring Framework, hãy gắn **ContextPropagatingTaskDecorator** vào **TaskExecutor thực sự chạy listener** và cung cấp **Micrometer Context Propagation accessors** phù hợp; với tracing thật còn cần **Micrometer Tracing/instrumentation** và có thể tạo span riêng cho listener. **Context propagation chỉ giữ liên kết quan sát**, không chuyển transaction và không bảo đảm task được thực thi bền vững.

### Tài liệu chính thức

- Spring Framework 6.2 — *Observability Support, Application Events and @EventListener*: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework 6.2.9 Javadoc — *ContextPropagatingTaskDecorator*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework 6.2.9 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — *Asynchronous Event Listeners*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Micrometer Context Propagation — *Purpose*: https://docs.micrometer.io/context-propagation/reference/purpose.html
- Micrometer Context Propagation — *Usage*: https://docs.micrometer.io/context-propagation/reference/usage.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
