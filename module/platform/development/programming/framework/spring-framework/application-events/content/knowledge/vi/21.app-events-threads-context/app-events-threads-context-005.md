# ContextPropagatingTaskDecorator trong Spring Application Events

## 1. Mục tiêu

`ContextPropagatingTaskDecorator` là lớp trong Spring Framework (từ **Spring 6.1**) để bọc các task trước khi chạy ở một thread khác, giúp giữ những giá trị context được Micrometer Context Propagation hỗ trợ. Nó đặc biệt hữu ích khi `@EventListener` hoặc `@Async @EventListener` chuyển việc từ thread phát event sang một `TaskExecutor`.

Trong một ứng dụng thực tế, request có thể mang trace ID, correlation ID, logging MDC, observation context hoặc `ThreadLocal` tự định nghĩa. Với listener đồng bộ mặc định, callback thường chạy ngay trong publisher thread và nhìn thấy context thread-bound đó. Khi listener chạy bất đồng bộ, worker thread **không tự có** các giá trị ấy.

Decorator giúp **capture context tại thời điểm task được submit** rồi **restore trong phạm vi worker thực thi task**, nhưng không tự copy mọi `ThreadLocal`; bạn cần accessor tương ứng. Nó cũng **không** tự truyền giao dịch JDBC/JPA, không bảo đảm gửi event thành công và không tự biến async thành sync.

Sau bài này bạn sẽ:

- Phân biệt `ThreadLocal`, `TaskDecorator`, `ContextRegistry`, `ThreadLocalAccessor`, `ContextSnapshot` và `ContextSnapshotFactory`.
- Gắn `ContextPropagatingTaskDecorator` vào đúng executor sử dụng cho application events.
- Viết Java 17+ Spring Framework demo với hai executor, chứng minh rõ có/không có context propagation.
- Hiểu cơ chế snapshot, restore, isolation, MDC/observation, security/transaction và Reactor Context.
- Biết các lỗi thường gặp và cách kiểm thử thread-pool reuse, context leak, overhead.

## 2. Tại sao listener async mất ThreadLocal?

Các biến `ThreadLocal<T>` liên kết **một giá trị với từng thread**:

~~~java
// Minh họa trong một class Java.
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

public static void handleRequest() {
    TRACE_ID.set("trace-17");
    try {
        System.out.println(TRACE_ID.get()); // trace-17
    } finally {
        TRACE_ID.remove();
    }
}
~~~

Trên thread khác, `TRACE_ID.get()` thông thường trả `null` trừ khi thread đó đã tự có giá trị hoặc một cơ chế nào đó truyền nó qua.

Spring Application Events dùng `ApplicationEventMulticaster`. Với `SimpleApplicationEventMulticaster` mặc định, các listener đồng bộ chạy cùng thread với `publishEvent(...)`:

~~~text
thread request-handler
    |
    +-- TRACE_ID = trace-17
    +-- publisher.publishEvent(OrderCreated)
            |
            +-- @EventListener đồng bộ
            |       TRACE_ID = trace-17
            |
            +-- @Async @EventListener
                    |
                    +-- executor queue
                    +-- worker thread
                            TRACE_ID = null nếu không propagate
~~~

Vì vậy **listener đồng bộ nhìn thấy ThreadLocal không có nghĩa event payload chứa ThreadLocal**. Nó chỉ chạy trên cùng thread đang giữ giá trị đó. Nếu ứng dụng cấu hình một `applicationEventMulticaster` dùng executor, ngay cả listener không gắn `@Async` cũng có thể chạy trên worker.

`InheritableThreadLocal` không phải giải pháp phù hợp cho thread pool: nó kế thừa lúc tạo thread con, trong khi worker thường tồn tại từ trước và tái sử dụng cho nhiều request. Cần capture/restore **theo từng task**.

## 3. Những thành phần quan trọng

| Thành phần | Nhiệm vụ |
| --- | --- |
| `TaskDecorator` | Giao diện Spring nhận `Runnable` và trả một `Runnable` đã bọc |
| `ContextPropagatingTaskDecorator` | Dùng factory Micrometer để chụp và restore context trên worker |
| `ContextRegistry` | Lưu danh sách accessor biết cách đọc/ghi các loại context |
| `ThreadLocalAccessor<V>` | Đọc, set và clear một `ThreadLocal` cụ thể |
| `ContextAccessor` | Truy cập context có cấu trúc dạng map-like, chẳng hạn Reactor Context |
| `ContextSnapshot` | Bản chụp của các giá trị context được lựa chọn |
| `ContextSnapshotFactory` | Tạo snapshot theo registry và chính sách capture |
| `ThreadPoolTaskExecutor` | Executor Spring hỗ trợ `setTaskDecorator(...)` |

Quy trình cơ bản:

~~~text
publisher thread
  ThreadLocal traceId=A
       |
       +-- execute(task)
               |
               +-- decorator.decorate(task)
               |       ContextSnapshot capture=A
               |
             task queue
               |
             worker thread
               +-- mở snapshot scope -> traceId=A
               +-- chạy listener/task
               +-- đóng scope -> restore trạng thái worker
~~~

Snapshot được capture lúc **submit**, không phải lúc worker bắt đầu. Ví dụ publisher đổi `traceId` từ A sang B sau khi submit task 1, task 1 vẫn dùng snapshot A; task 2 được submit khi giá trị là B sẽ dùng snapshot B.

### Constructor và dependency

API của Spring Framework 6.2:

~~~java
// Dùng ContextSnapshotFactory mặc định.
new ContextPropagatingTaskDecorator();

// Chỉ định ContextSnapshotFactory tường minh.
new ContextPropagatingTaskDecorator(snapshotFactory);
~~~

Thư viện `io.micrometer:context-propagation` phải có trong classpath. Chỉ thêm decorator không tự nhận biết `ThreadLocal` tùy biến. Phải có `ThreadLocalAccessor` đăng ký vào đúng `ContextRegistry`.

Theo Spring Javadoc, capture và restore tạo **overhead**, không nên bật vô điều kiện cho khối lượng rất lớn các task cực nhỏ.

## 4. Cấu hình executor có decorator

Ví dụ cấu hình trong Spring:

~~~java
// Minh họa: @Bean trong @Configuration, chưa phải file độc lập.
@Bean("propagatingExecutor")
ThreadPoolTaskExecutor propagatingExecutor(ContextRegistry registry) {
    ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
            .contextRegistry(registry)
            .build();

    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("event-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator(factory));
    return executor;
}
~~~

Spring container sẽ initialize bean executor theo lifecycle. Nếu tự tạo `ThreadPoolTaskExecutor` ngoài container, cần `initialize()` trước khi dùng và `shutdown()` sau khi hoàn thành.

Method listener muốn dùng executor này:

~~~java
// Minh họa Spring bean, cần @EnableAsync trong cấu hình.
@Async("propagatingExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Có thể đọc các ThreadLocal đã được accessor capture.
}
~~~

**Phải gắn decorator vào executor thật sự được `@Async("...")` chọn.** Một executor khác của ứng dụng sẽ không nhận được propagation chỉ vì có một bean decorator nằm đâu đó trong container.

## 5. Ví dụ Java 17+ hoàn chỉnh

Ta xây dựng ứng dụng Spring Framework 6.2.12 không có web server. Hai async listeners cùng nhận `ProbeEvent`, nhưng dùng hai executor:

- `plainExecutor` không decorator: worker không nhận custom ThreadLocal.
- `propagatingExecutor` gắn `ContextPropagatingTaskDecorator` với `ContextSnapshotFactory` trỏ đến registry chứa custom accessor.

Publisher phát hai event với `TRACE_ID` khác nhau (`trace-one` và `trace-two`). `CountDownLatch` đợi đủ bốn callback trước khi in. Mỗi executor có một worker thread để thấy việc tái sử dụng thread không làm giữ giá trị của event trước.

Cấu trúc:

~~~text
context-propagation-events/
├── pom.xml
└── src/main/java/demo/ContextPropagationEventsDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-propagation-events</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.3</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/ContextPropagationEventsDemo.java`

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.context.ThreadLocalAccessor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ContextPropagationEventsDemo {

    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record ProbeEvent(String name) {}

    public static final class Results {
        final Map<String, String> seen = new ConcurrentHashMap<>();
        final CountDownLatch done = new CountDownLatch(4);

        public void record(String listener, ProbeEvent event, String value) {
            seen.put(listener + "-" + event.name(), String.valueOf(value));
            done.countDown();
        }

        public String value(String key) {
            return seen.get(key);
        }
    }

    public static class PlainListener {
        private final Results results;

        public PlainListener(Results results) {
            this.results = results;
        }

        @Async("plainExecutor")
        @EventListener
        public void on(ProbeEvent event) {
            results.record("plain", event, TRACE_ID.get());
        }
    }

    public static class PropagatingListener {
        private final Results results;

        public PropagatingListener(Results results) {
            this.results = results;
        }

        @Async("propagatingExecutor")
        @EventListener
        public void on(ProbeEvent event) {
            results.record("propagated", event, TRACE_ID.get());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public Results results() {
            return new Results();
        }

        @Bean
        public ContextRegistry contextRegistry() {
            ContextRegistry registry = new ContextRegistry();

            registry.registerThreadLocalAccessor(
                new ThreadLocalAccessor<String>() {
                    @Override
                    public Object key() {
                        return "demo.trace-id";
                    }

                    @Override
                    public String getValue() {
                        return TRACE_ID.get();
                    }

                    @Override
                    public void setValue(String value) {
                        TRACE_ID.set(value);
                    }

                    @Override
                    public void setValue() {
                        TRACE_ID.remove();
                    }
                });
            return registry;
        }

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("plain-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean("propagatingExecutor")
        public ThreadPoolTaskExecutor propagatingExecutor(
                ContextRegistry registry) {
            ContextSnapshotFactory factory =
                    ContextSnapshotFactory.builder()
                            .contextRegistry(registry)
                            .build();

            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("propagating-");
            executor.setTaskDecorator(
                    new ContextPropagatingTaskDecorator(factory));
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean
        public PlainListener plainListener(Results results) {
            return new PlainListener(results);
        }

        @Bean
        public PropagatingListener propagatingListener(Results results) {
            return new PropagatingListener(results);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Results results = context.getBean(Results.class);

            try {
                TRACE_ID.set("trace-one");
                context.publishEvent(new ProbeEvent("one"));

                TRACE_ID.set("trace-two");
                context.publishEvent(new ProbeEvent("two"));
            } finally {
                TRACE_ID.remove();
            }

            if (!results.done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async listeners timed out");
            }

            System.out.println("plain-one=" + results.value("plain-one"));
            System.out.println("propagated-one="
                    + results.value("propagated-one"));
            System.out.println("plain-two=" + results.value("plain-two"));
            System.out.println("propagated-two="
                    + results.value("propagated-two"));
            System.out.println("publisher-after=" + TRACE_ID.get());
        }
    }
}
~~~

Chạy từ thư mục có `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextPropagationEventsDemo
~~~

Năm dòng do chương trình tự in (ngoài log Spring/Maven nếu có):

~~~text
plain-one=null
propagated-one=trace-one
plain-two=null
propagated-two=trace-two
publisher-after=null
~~~

### 5.3. Vì sao kết quả xác định?

1. Publisher set `TRACE_ID="trace-one"`, publish event `one`.
2. Plain executor chuyển callback sang thread worker khác, nơi custom ThreadLocal chưa được set, nên `plain-one=null`.
3. Propagating executor capture `trace-one` qua `ThreadLocalAccessor` khi submit task. Trong scope của worker, listener đọc được `trace-one`.
4. Publisher đổi `TRACE_ID` thành `trace-two` rồi publish event `two`. Snapshot mới chụp giá trị mới; vì vậy `propagated-two=trace-two` ngay cả nếu worker chạy sau khi publisher đã xóa ThreadLocal.
5. `ContextPropagatingTaskDecorator` khôi phục context của worker khi task kết thúc; worker thread có thể được tái sử dụng.
6. Main gọi `TRACE_ID.remove()` trong `finally` để dọn **thread publisher**.
7. `CountDownLatch` chờ bốn callback; `ConcurrentHashMap` cung cấp nơi lưu kết quả thread-safe. Main in theo thứ tự cố định, không suy đoán lịch chạy của executor.

**Lưu ý:** chương trình không đo chính xác timestamp/latency, không yêu cầu worker bắt đầu trước khi publisher đổi context. Điều được kiểm chứng là snapshot **theo từng lần submit** chứ không phải tham chiếu sống tới ThreadLocal trên main.

## 6. Dùng decorator với ApplicationEventMulticaster tùy chỉnh

Ngoài `@Async`, bạn có thể cấu hình bean tên `applicationEventMulticaster` để chuyển các listener cho phép async execution sang executor:

~~~java
// Minh họa trong Spring @Configuration, không phải chương trình độc lập.
@Bean(name = "applicationEventMulticaster")
public SimpleApplicationEventMulticaster multicaster(
        ThreadPoolTaskExecutor propagatingExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(propagatingExecutor);
    return m;
}
~~~

Executor phải có decorator. Với cấu hình này, một `@EventListener` **không có `@Async`** vẫn có thể chạy trên worker, tùy `supportsAsyncExecution()` của listener. Do đó, không được kết luận thread của callback chỉ bằng annotation trên method.

**Điểm đặc biệt:** các listener yêu cầu chạy trên publisher thread (`ApplicationListener.supportsAsyncExecution()==false`), chẳng hạn listener gắn transaction synchronization, không được chuyển async chỉ bởi multicaster executor. Không dùng cấu hình global async để cố “copy transaction” sang worker; transaction cần được xử lý theo lifecycle riêng.

Chuyển tất cả event sang async còn làm thay đổi thứ tự hoàn thành listener, đường lan truyền exception và thời điểm startup/shutdown. Khi chỉ một handler cần async, `@Async("propagatingExecutor")` thường dễ khoanh vùng hơn.

## 7. Registry, snapshot và restore chi tiết

### 7.1. Đăng ký custom ThreadLocal

Micrometer cần biết **key**, cách đọc, cách set và cách xóa một ThreadLocal. Accessor trong ví dụ:

~~~java
// Minh họa những method của ThreadLocalAccessor<String>.
@Override
public Object key() {
    return "demo.trace-id";
}

@Override
public String getValue() {
    return TRACE_ID.get();
}

@Override
public void setValue(String value) {
    TRACE_ID.set(value);
}

@Override
public void setValue() {
    TRACE_ID.remove();
}
~~~

Nếu quên đăng ký accessor hoặc factory dùng **một registry khác**, custom ThreadLocal sẽ không được capture. Khi dùng `ContextSnapshotFactory.builder().contextRegistry(registry).build()`, phải bảo đảm `registry` này thực sự có accessor cho những context mong muốn.

Với observation/MDC được framework tích hợp, accessor có thể được đăng ký tự động hoặc thông qua integration tương ứng, nhưng **không mặc định suy ra mọi logging backend và mọi custom key đều có accessor**.

### 7.2. Snapshot không phải live link

~~~text
t0: Thread A TRACE_ID = trace-one
t1: submit(task-one) => snapshot(trace-one)
t2: Thread A TRACE_ID = trace-two
t3: submit(task-two) => snapshot(trace-two)
t4: Thread A remove()
t5: Thread B run(task-one) => thấy trace-one
t6: Thread B run(task-two) => thấy trace-two
~~~

Đây là **snapshot của giá trị lúc capture**. Nếu một context chứa reference tới mutable object, không có nghĩa decorator tự deep-copy object đó. Tránh đưa object mutable lớn, HTTP request/session hay resource database đang sống qua ranh giới thread.

### 7.3. Restore và thread-pool reuse

Sau khi task chạy, scope propagation cần **khôi phục trạng thái worker trước đó**. Nếu worker ban đầu không có giá trị, giá trị đã bind sẽ được xóa; nếu worker có giá trị riêng trước đó, scope phải restore giá trị phù hợp.

Đây là điều rất quan trọng với thread pool: quên dọn có thể khiến task cho tenant A làm task tenant B đọc nhầm correlation/security context của A. Khi tự viết `TaskDecorator`, luôn dùng `try/finally` để restore; với Micrometer, `ContextSnapshot.Scope` xử lý vòng đời bind/restore.

Cẩn thận với chính sách **missing key/clearMissing** trong `ContextSnapshotFactory`. Không giả định một context thiếu giá trị trên publisher sẽ tự xóa mọi ThreadLocal có sẵn trên worker ở mọi cấu hình; cần test cả chiều “có giá trị” và “không có giá trị”.

## 8. MDC, observation, security và transaction

### Logging MDC / Micrometer Observation

MDC và tracing/observation thường chứa thông tin correlation trong thread-bound state. `ContextPropagatingTaskDecorator` chủ yếu hữu ích ở đây: trace/span/MDC được truyền sang worker khi có accessor và integration tương ứng.

Nhưng một dòng log có `tenantId=tenant-7` trong MDC **không chứng minh quyền truy cập** tenant đó. MDC phục vụ quan sát; security/tenant authorization vẫn phải được xác minh bằng nguồn tin cậy.

### Spring Security

`SecurityContextHolder` thường dùng ThreadLocal ở chiến lược mặc định. Để async task sử dụng danh tính principal theo một chính sách rõ ràng, Spring Security có các cơ chế như `DelegatingSecurityContextAsyncTaskExecutor`. Không giả định `ContextPropagatingTaskDecorator` tự copy toàn bộ SecurityContext; các context nhạy cảm cần quyết định cách truyền, vòng đời và thời hạn quyền sử dụng.

### Transaction synchronization

`TransactionSynchronizationManager` có thể lưu JDBC Connection, EntityManager và trạng thái transaction trên publisher thread. **Không đăng ký accessor để sao chép nguyên các resource giao dịch đó sang worker**. Một transaction không trở thành thread-safe chỉ nhờ copy ThreadLocal.

Nếu listener async phải ghi DB, tạo transaction **riêng trên worker**, chẳng hạn gọi một Spring service `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua proxy khi phù hợp. Nếu chỉ muốn xử lý sau commit, dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`, nhưng đó là cơ chế **transaction-bound event**, không phải propagation của decorator.

`@TransactionalEventListener` mặc định bỏ qua event publish ngoài transaction nếu `fallbackExecution=false`; decorator không khắc phục được việc không có transaction trong thread phát event.

### HTTP request / locale

`RequestContextHolder` và `LocaleContextHolder` có thể giữ context gắn với request/thread. Đừng truyền nguyên `HttpServletRequest` hoặc session vào task chạy lâu sau khi request kết thúc; request-scoped bean có thể không còn hợp lệ. Truyền ID, locale, correlation hoặc dữ liệu đã xác minh trong event khi cần.

### Reactive

Với `ReactiveTransactionManager` và pipeline Reactor, ngữ cảnh thường nằm trong **Reactor Context**, không chỉ `ThreadLocal`. Micrometer Context Propagation có cơ chế bridge giữa các loại context khi cấu hình đúng. Không dùng copy ThreadLocal như một cách thay thế transaction context của Reactor.

## 9. Khi nào nên dùng, khi nào không?

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Truyền trace/observation/MDC qua `@Async` executor | `ContextPropagatingTaskDecorator` với accessor đúng |
| Truyền ID nghiệp vụ, aggregate ID, tenant ID đã validate | Field tường minh trong event payload |
| Ghi dữ liệu ở async listener | Mở transaction riêng theo semantics nghiệp vụ |
| Chuyển security context sang worker | Cơ chế propagation chuyên dụng của Spring Security |
| Luồng reactive | Reactor Context và adapter phù hợp |
| Phát integration event bền vững qua crash | Outbox, broker, retry, idempotency; decorator không giải quyết |
| Hàng triệu task rất ngắn mỗi giây | Benchmark overhead trước khi bật decorator rộng rãi |

Javadoc của Spring cảnh báo chi phí context capture/restore có thể không phù hợp với số lượng rất lớn task cực nhỏ. Cần cân bằng nhu cầu correlation với throughput, latency, phân bổ thread và số accessor đã đăng ký.

Không cho rằng decorator tự bảo đảm task được thực thi, event được gửi lại hoặc listener hoàn tất. Task có thể bị reject nếu executor quá tải, có thể fail hoặc bị shutdown trước khi chạy; cần cơ chế xử lý lỗi và monitoring tương ứng.

## 10. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Quên dependency Micrometer context-propagation | Thiếu API ContextSnapshot | Thêm dependency tương thích |
| Tạo decorator nhưng quên custom ThreadLocalAccessor | Worker vẫn đọc null | Đăng ký accessor vào đúng ContextRegistry |
| Gắn decorator vào executor khác với `@Async` đang dùng | Context vẫn mất | Kiểm tra qualifier tên executor và multicaster |
| Sử dụng `InheritableThreadLocal` cho thread pool | Giá trị cũ hoặc không đúng lần submit | Capture theo task và restore đúng |
| Nghĩ decorator tự copy SecurityContext/transaction | Mất context hoặc truy cập sai resource | Chọn propagation phù hợp, không copy transaction |
| Coi MDC là nguồn phân quyền | Rủi ro lộ dữ liệu giữa tenant | Phân quyền bằng nguồn xác thực riêng |
| Dùng mutable request/session trong context snapshot | Object hết vòng đời hoặc bị sửa song song | Dùng ID/snapshot dữ liệu tường minh |
| Không cleanup khi task hoàn thành | Rò ThreadLocal giữa các request | Micrometer scope hoặc try/finally |
| Dựa vào `@Order` cho thứ tự hoàn thành async | Race condition | Latch, Future, workflow rõ ràng |
| Quên kiểm tra task bị reject/timeout | Thiếu xử lý sự kiện | Giới hạn queue, log và error handling |
| Nghĩ decorator là message queue có retry | Event có thể mất nếu process chết | Outbox / durable messaging khi cần |

## 11. Kiểm thử và vận hành

### Test đúng crossing-thread

1. Dùng executor thực có worker thread, không thay bằng `SyncTaskExecutor` khi muốn kiểm thử việc mất context.
2. Publish hai event với hai `TRACE_ID` khác nhau; kiểm tra worker có decorator nhận đúng snapshot theo từng lần submit.
3. Đợi bằng `CountDownLatch` hoặc Future có timeout, không dựa vào `Thread.sleep`.
4. Test task thứ hai trên **cùng worker** để phát hiện stale context và lỗi restore.
5. Test trường hợp publisher **không có** ThreadLocal và chính sách clearMissing phù hợp.
6. Mô phỏng exception trong task, xác nhận context worker được restore và lỗi được ghi nhận.
7. Test cả `@Async` và multicaster executor tùy thiết kế thực tế.
8. Nếu truyền security context, test nhiều principal/tenant và lúc quyền bị thu hồi.

### Metrics nên quan sát

Theo dõi số task pending, executor rejection, tỷ lệ callback thất bại, thời gian queue, số log thiếu correlation ID, shutdown behavior và latency trước/sau khi bật decorator. Tránh chữa lỗi bằng cách set một trace ID mặc định chung cho mọi task; điều đó che mất quan hệ nhân quả thật.

## 12. Checklist cuối

1. Listener có chạy khác thread với publisher không? Do `@Async` hay multicaster executor?
2. Decorator được gắn vào **đúng executor** chưa?
3. Dependency `context-propagation` và các accessor cần thiết đã có chưa?
4. Factory dùng **đúng ContextRegistry** đã đăng ký accessor chưa?
5. Context snapshot được capture tại điểm submit task chưa?
6. Scope đã restore/clear worker context, kể cả khi callback lỗi chưa?
7. Có dùng payload tường minh cho dữ liệu nghiệp vụ thay vì lệ thuộc ThreadLocal không?
8. Có tránh copy transaction resources và request/session đang sống sang thread khác không?
9. Có kiểm thử hai request/tenant liên tiếp trên cùng thread pool không?
10. Overhead capture/restore đã được đo với khối lượng task thực tế chưa?

**Kết luận:** `ContextPropagatingTaskDecorator` là công cụ truyền **context đã có accessor** qua ranh giới thread bằng Micrometer. Để sử dụng đúng trong Spring Application Events, hãy gắn vào executor thực sự chạy listener, capture theo từng lần submit và bảo đảm restore sau task. Giữ business data trong event, giữ transaction và authorization ở đúng ranh giới; không dùng decorator thay thế cơ chế messaging bền vững.

## Tài liệu chính thức

- Spring Framework 6.2 — Javadoc ContextPropagatingTaskDecorator: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework 6.2 — Observability và Application Events: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Micrometer Context Propagation — Purpose: https://docs.micrometer.io/context-propagation/reference/purpose.html
- Micrometer Context Propagation — Usage: https://docs.micrometer.io/context-propagation/reference/usage.html
