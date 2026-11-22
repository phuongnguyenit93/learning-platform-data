# ThreadLocal trong listener của Spring Application Events

## 1. Mục tiêu

`ThreadLocal<T>` lưu một giá trị **riêng cho từng thread**. Trong ứng dụng Spring, nhiều loại ngữ cảnh hoạt động dựa vào thread-bound state: thông tin request, logging MDC, security context ở cấu hình phổ biến, locale, tài nguyên giao dịch và một số dữ liệu tracing.

Khi xử lý Spring Application Events, câu hỏi thường gặp là: **listener có đọc được `ThreadLocal` của nơi gọi `ApplicationEventPublisher.publishEvent(...)` hay không?**

Câu trả lời phụ thuộc vào **listener đang chạy trên thread nào**:

- Với `ApplicationEventMulticaster` mặc định và listener đồng bộ: callback thường chạy **ngay trên thread publish**, nên thấy cùng các `ThreadLocal` hiện hành.
- Nếu listener có `@Async` hoặc multicaster chuyển việc cho một `Executor`: callback chạy trên thread khác, vì vậy **không mặc nhiên mang theo** `ThreadLocal`, MDC, transaction hay request context của publisher.
- Nếu context được truyền thủ công, qua `TaskDecorator`, tracing/security adapter hoặc trong chính payload event: cần nắm rõ **giá trị nào được truyền, khi nào snapshot, khi nào phải dọn**.

Bài học tập trung vào cơ chế thật, ví dụ Java 17+ chạy được và các nguyên tắc thiết kế an toàn. Không coi `ThreadLocal` là một phần của event payload hay một kho lưu trữ toàn cục.

## 2. Bản chất của ThreadLocal

Ví dụ Java thuần:

~~~java
// Minh họa bên trong một class Java:
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public static void work() {
    REQUEST_ID.set("req-17");
    try {
        System.out.println(REQUEST_ID.get()); // req-17
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Điểm cốt lõi:

1. `ThreadLocal` là **một đối tượng làm khóa**, còn giá trị tương ứng gắn với từng `Thread`; hai thread dùng cùng một `ThreadLocal` thường có hai giá trị độc lập.
2. `get()` trả `null` nếu chưa gán giá trị và không có giá trị mặc định được cấu hình qua `withInitial(...)`.
3. `set(...)` gán giá trị của **thread hiện tại**, không gán cho thread khác.
4. `remove()` xóa bản ghi của thread hiện tại, đặc biệt quan trọng với thread pool vì thread sẽ được tái sử dụng.
5. Một `ThreadLocal` không tự truy cập qua tiến trình/JVM khác và cũng không phải transaction/event store.

Một thread pool có thể tái sử dụng cùng worker cho hàng nghìn task. Nếu task trước set `tenantId` hay `userId` mà quên cleanup, task kế tiếp có thể nhìn thấy **dữ liệu cũ thuộc request khác**. Đây không chỉ là vấn đề bộ nhớ, mà còn có thể trở thành lỗi cô lập dữ liệu hoặc quyền truy cập.

`InheritableThreadLocal` là cơ chế khác, có thể truyền giá trị khi tạo **thread con mới**; nó **không phải giải pháp an toàn cho thread pool** vì worker có thể được tạo trước, tái sử dụng và mang snapshot lỗi thời. Đừng bật kế thừa ngữ cảnh một cách mù quáng để sửa lỗi event async.

## 3. Mặc định: listener đồng bộ nhìn thấy ThreadLocal

Trong Spring Framework, `ApplicationContext` sử dụng một `ApplicationEventMulticaster`. Theo mặc định, đó là `SimpleApplicationEventMulticaster` với cách gọi listener **đồng bộ trong thread đang publish**.

~~~text
Thread: http-nio-8080-exec-1
    |
    +-- RequestContext.set("req-17")
    +-- OrderService.placeOrder()
            |
            +-- publisher.publishEvent(OrderPlaced)
                    |
                    +-- @EventListener.onOrderPlaced()
                    |        RequestContext.get() = "req-17"
                    |
                    +-- listener khác (cũng đồng bộ)
    |
    +-- RequestContext.remove()
~~~

Vì callback chạy trên cùng thread, nó có thể truy cập cùng `ThreadLocal` nếu giá trị vẫn tồn tại tại thời điểm callback được gọi. **Không phải Spring đã copy ThreadLocal vào event**; đơn giản là listener dùng **cùng thread đang giữ giá trị**.

Ví dụ minh họa:

~~~java
// Trong một Spring-managed bean, không phải chương trình độc lập.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    String requestId = RequestContext.REQUEST_ID.get();
    logger.info("order={}, request={}", event.orderId(), requestId);
}
~~~

Nếu `OrderPlaced` được publish từ thread không hề set `REQUEST_ID`, callback sẽ nhận `null`. Nếu `@EventListener` bị đổi sang `@Async`, giả định cùng thread không còn đúng.

### Điều kiện quan trọng

- Mặc định đồng bộ **không bảo đảm mọi cấu hình ứng dụng đều đồng bộ**; dự án có thể khai báo bean `applicationEventMulticaster` với một `TaskExecutor`.
- Một method `@EventListener` có `@Async` được chạy thông qua cơ chế async của Spring khi `@EnableAsync` được bật và interception áp dụng.
- Một `ApplicationListener` custom có thể tự gọi executor hay chuyển tiếp công việc sang thread khác dù bước dispatch ban đầu đồng bộ.
- Nếu callback tự tạo task khác, phần công việc trong task **không thừa hưởng** ThreadLocal chỉ nhờ callback ban đầu thấy nó.

### ThreadLocal và transaction đồng bộ

Transaction thread-bound do `PlatformTransactionManager` quản lý thường có tài nguyên/trạng thái gắn với thread, ví dụ qua `TransactionSynchronizationManager`. Listener đồng bộ được gọi **trong transaction của publisher** nếu event được publish từ luồng có transaction đang hoạt động.

Điều này không có nghĩa một listener đồng bộ chạy sau commit. `@EventListener` bình thường chạy **ngay lúc publish**; nếu listener tạo side effect bên ngoài như email, side effect ấy có thể đã xảy ra dù transaction sau đó rollback. Muốn phản ứng theo kết quả transaction, dùng `@TransactionalEventListener` với phase phù hợp.

## 4. Khi listener chạy bất đồng bộ, điều gì thay đổi?

Có hai cơ chế phổ biến, cần phân biệt.

### 4.1. Chỉ một method dùng @Async

~~~java
// Đoạn minh họa: cần @EnableAsync, executor và Spring bean thực.
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    // Chạy trên thread của eventExecutor, không phải publisher.
}
~~~

Khi `@Async` được áp dụng, Spring schedule method qua executor. `publishEvent` **không đợi logic bất đồng bộ hoàn tất**. Giá trị `ThreadLocal` của publisher **không tự truyền sang worker**.

Nếu async listener ném exception, nó không tự lan về caller của `publishEvent`; với async `void` method, cần quan sát lỗi qua `AsyncUncaughtExceptionHandler` hoặc cơ chế monitoring phù hợp. Không giả định thay đổi trong async listener vẫn đang ở transaction của publisher.

### 4.2. Thay ApplicationEventMulticaster bằng executor

Một ứng dụng có thể cấu hình bean tên đặc biệt `applicationEventMulticaster`:

~~~java
// Minh họa cấu hình, cần bean Executor eventExecutor tương ứng.
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        Executor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Khi đó multicaster có thể schedule các listener cho phép thực thi bất đồng bộ lên executor. Listener `@EventListener` vốn không đặt `@Async` cũng có thể chạy ở worker thread, nên **không được suy ra cùng thread chỉ bằng cách nhìn method không có `@Async`**.

**Ngoại lệ quan trọng:** không phải mọi listener đều có thể được tách thread. Các `ApplicationListener` khai báo `supportsAsyncExecution() == false` vẫn được xử lý trên thread phát event; các listener transaction-synchronized là trường hợp tiêu biểu. Không nên cấu hình multicaster async toàn cục rồi mặc định mọi transaction-bound event listener được schedule theo cùng một cách.

### 4.3. Hệ quả khi chuyển thread

| Loại ngữ cảnh | Cùng thread mặc định | Sang executor/worker |
| --- | --- | --- |
| `ThreadLocal<String>` tùy biến | Có thể đọc giá trị hiện tại | Không tự copy |
| SLF4J MDC | Thường cùng map ngữ cảnh của thread | Không tự copy trong cấu hình chung |
| `SecurityContextHolder` kiểu `MODE_THREADLOCAL` | Có thể đọc security context | Cần cơ chế context propagation được thiết kế |
| `RequestContextHolder` | Có thể thấy request attributes | Không tự mang sang worker; request còn phải hợp lệ |
| `LocaleContextHolder` | Có thể thấy locale thread-bound | Cần capture/restore nếu thật sự cần |
| `TransactionSynchronizationManager` | Có thể thấy tài nguyên transaction hiện tại | **Không được copy transaction thread-bound** |
| Reactor Context trong reactive flow | Không tương đương ThreadLocal | Cần cơ chế truyền context của Reactor |

Những giá trị này có thể khác theo từng cấu hình ứng dụng. Đặc biệt với Spring Security, cách lưu `SecurityContext` có thể được cấu hình khác chế độ thread-local mặc định; hãy dùng cơ chế chính thức thay vì giả định cấu hình toàn cục.

## 5. Ví dụ Java 17+ chạy được: sync thấy ThreadLocal, async không thấy

Ví dụ dùng Spring Framework 6.2.12 với `@EnableAsync` và một `ThreadPoolTaskExecutor`. Không cần web server, cơ sở dữ liệu hay Spring Boot.

Kịch bản:

1. Publisher set `ThreadLocal` là `"request-7"`.
2. Publisher tạo event chứa `traceId="trace-7"` **tường minh** và gọi `publishEvent`.
3. Listener đồng bộ đọc được `ThreadLocal` của publisher.
4. Listener async chạy ở worker; trước khi tự bind, `ThreadLocal.get()` trả `null`.
5. Listener async lấy `traceId` từ event và tự set ngữ cảnh trong `try/finally`, rồi `remove()`.
6. Publisher cũng cleanup trong `finally`. Chương trình chờ bằng `CountDownLatch` nên stdout có thứ tự xác định, không phụ thuộc timing của worker.

Cấu trúc:

~~~text
threadlocal-listener-demo/
├── pom.xml
└── src/main/java/demo/ThreadLocalListenerDemo.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>threadlocal-listener-demo</artifactId>
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

### 5.2. src/main/java/demo/ThreadLocalListenerDemo.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadLocalListenerDemo {

    // Dữ liệu thread-bound chỉ dành cho luồng hiện tại.
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    // Event mang correlation/trace value tường minh, độc lập với thread.
    public record JobRequested(String eventId, String traceId) {}

    public static final class State {
        final AtomicReference<String> syncSeen = new AtomicReference<>();
        final AtomicReference<String> asyncBefore = new AtomicReference<>();
        final AtomicReference<String> asyncBound = new AtomicReference<>();
        final CountDownLatch asyncDone = new CountDownLatch(1);
    }

    public static final class SyncListener {
        private final State state;

        public SyncListener(State state) {
            this.state = state;
        }

        @EventListener
        public void handle(JobRequested event) {
            state.syncSeen.set(
                    "local=" + REQUEST_ID.get()
                    + ", payload=" + event.traceId());
        }
    }

    public static final class AsyncListener {
        private final State state;

        public AsyncListener(State state) {
            this.state = state;
        }

        @Async("listenerExecutor")
        @EventListener
        public void handle(JobRequested event) {
            try {
                // Thread khác, nên không nhận ThreadLocal của publisher.
                state.asyncBefore.set(String.valueOf(REQUEST_ID.get()));

                // Chủ động bind dữ liệu từ event cho đoạn xử lý cần context.
                REQUEST_ID.set(event.traceId());
                state.asyncBound.set(REQUEST_ID.get());
            } finally {
                // Thread pool tái sử dụng worker, nên bắt buộc dọn.
                REQUEST_ID.remove();
                state.asyncDone.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class Config {
        @Bean
        public State state() {
            return new State();
        }

        @Bean
        public SyncListener syncListener(State state) {
            return new SyncListener(state);
        }

        @Bean
        public AsyncListener asyncListener(State state) {
            return new AsyncListener(state);
        }

        @Bean
        public ThreadPoolTaskExecutor listenerExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("event-worker-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            State state = context.getBean(State.class);
            REQUEST_ID.set("request-7");
            try {
                context.publishEvent(new JobRequested("event-1", "trace-7"));

                if (!state.asyncDone.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Async listener did not finish");
                }

                // Chỉ in sau khi cả 2 listener đã hoàn tất:
                // không phụ thuộc thứ tự scheduling của executor.
                System.out.println("sync: " + state.syncSeen.get());
                System.out.println(
                        "async-before: local=" + state.asyncBefore.get());
                System.out.println(
                        "async-bound: local=" + state.asyncBound.get());
            } finally {
                REQUEST_ID.remove();
            }

            System.out.println(
                    "publisher-cleanup: local=" + REQUEST_ID.get());
        }
    }
}
~~~

Chạy ở thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ThreadLocalListenerDemo
~~~

Bốn dòng do chương trình tự in ra:

~~~text
sync: local=request-7, payload=trace-7
async-before: local=null
async-bound: local=trace-7
publisher-cleanup: local=null
~~~

Spring/Maven có thể in log khác tùy môi trường; bốn dòng trên là phần output có thứ tự xác định trong `main`.

### 5.3. Tại sao output đúng?

- `REQUEST_ID.set("request-7")` chạy ở thread của main.
- Listener `SyncListener` không có `@Async`, và multicaster mặc định chạy đồng bộ nên `REQUEST_ID.get()` là `request-7`.
- `AsyncListener` được schedule sang worker. `ThreadLocal` thường không tự chuyển giữa hai thread, nên trước khi bind, `get()` trả `null`.
- `trace-7` nằm **trong payload của event**, không phụ thuộc thread. Listener lấy nó để tự bind context trong phạm vi xử lý và xóa trong `finally`.
- `CountDownLatch` đảm bảo main đợi listener async hoàn tất. Main in kết quả sau `publishEvent` và sau latch, vì vậy output không phụ thuộc listener async chạy trước hay sau listener sync.
- Sau `finally` ở publisher, giá trị ThreadLocal trên main cũng bị xóa; giá trị trên worker đã được xóa riêng. Không có bước nào giả định `remove()` trên main sẽ xóa giá trị trên worker.

Ví dụ đặt một listener async và một listener đồng bộ, không thay multicaster toàn cục. Nếu ứng dụng thay multicaster bằng executor, cả cấu trúc dispatch và cơ chế chờ có thể khác, nên cần kiểm thử cấu hình thực tế.

## 6. Cách 1 — Truyền dữ liệu cần thiết trong chính event

Với dữ liệu như `traceId`, `correlationId`, `tenantId` ở mức định danh, `locale` hoặc khóa aggregate, giải pháp rõ ràng nhất thường là **đưa giá trị cần thiết vào event envelope**:

~~~java
// Minh họa payload; không mang trực tiếp HTTP session hay mutable entity.
public record OrderSubmitted(
        String eventId,
        String correlationId,
        String tenantId,
        long orderId
) {}
~~~

Listener có thể đọc các giá trị đó bất kể thread hiện tại là gì:

~~~java
// Minh họa trong Spring bean.
@Async("eventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    auditService.record(
            event.tenantId(), event.orderId(), event.correlationId());
}
~~~

Ưu điểm: explicit contract, dễ test, có thể đưa qua broker nếu cần, không dựa vào một `ThreadLocal` vô hình. Nhưng cũng có rủi ro: **đừng cho rằng tenantId trong event tự động cấp quyền truy cập**. Listener phải kiểm tra authorization/tenant boundary theo thiết kế ứng dụng, nhất là với event đến từ nguồn không tin cậy.

Không nhét toàn bộ `SecurityContext`, `HttpServletRequest`, session, `EntityManager`, JDBC `Connection` hoặc `RequestAttributes` đang sống vào event. Chúng thường có vòng đời/ngữ nghĩa thread riêng, chứa dữ liệu nhạy cảm hoặc không an toàn khi chuyển thread.

## 7. Cách 2 — Capture và restore một ThreadLocal bằng TaskDecorator

Nếu thư viện bên dưới thực sự cần một `ThreadLocal` (ví dụ một logger cũ yêu cầu requestId ngầm), có thể dùng `TaskDecorator` để **chụp snapshot tại thời điểm submit** rồi bind lại trong worker trong phạm vi task.

Đoạn dưới minh họa một `ThreadLocal<String>` tùy biến, không phải giải pháp tổng quát để copy transaction:

~~~java
// Minh họa trong cấu hình đã có ThreadLocal<String> REQUEST_ID.
// Cần import org.springframework.core.task.TaskDecorator.

TaskDecorator requestIdDecorator() {
    return task -> {
        // Chụp giá trị trên thread submit task.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(captured);
                }
                task.run();
            } finally {
                // Restore nếu executor tái sử dụng thread.
                if (previous == null) {
                    REQUEST_ID.remove();
                } else {
                    REQUEST_ID.set(previous);
                }
            }
        };
    };
}
~~~

Gắn decorator vào `ThreadPoolTaskExecutor` của **chính executor được listener sử dụng**:

~~~java
// Minh họa tại nơi xây dựng executor:
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(2);
executor.setQueueCapacity(32);
executor.setTaskDecorator(requestIdDecorator());
return executor;
~~~

Khi chạy trong Spring, bean executor được khởi tạo theo lifecycle container. Snapshot phải được lấy trước khi task chuyển thread; logic restore/remove trong `finally` giúp không để context của task cũ rò sang task kế tiếp.

**Giới hạn:** TaskDecorator có thể bọc một execution callback chứ không nhất thiết là `Runnable` gốc của người dùng. Error handling cần thiết kế riêng, nhất là với `FutureTask`. Không dùng decorator để “copy nguyên transaction” hoặc vượt quyền kiểm tra an ninh; một transaction trên một connection/thread không thể trở thành transaction hợp lệ trên thread khác chỉ vì copy vài ThreadLocal.

### Context propagation có sẵn

Spring Framework hỗ trợ tích hợp với **Micrometer Context Propagation** và `ContextPropagatingTaskDecorator` khi dependency/context accessor được cấu hình phù hợp. Đây là hướng nên cân nhắc khi cần truyền observability/MDC context một cách có hệ thống qua executor. Nó có thêm chi phí capture/restore, nên cần lựa chọn chỗ sử dụng hợp lý. Đừng tự khẳng định mọi loại ThreadLocal tùy biến đều tự được mang theo: phải có cơ chế/accessor tương ứng.

Với Spring Security, dùng các wrapper chính thức như `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế propagation tương thích với security setup của ứng dụng. Tránh tự truyền một `SecurityContext` mutable qua nhiều task hoặc dựa vào `InheritableThreadLocal` trong thread pool.

## 8. ThreadLocal trong transaction-bound listener

Cần phân biệt ba trường hợp:

| Listener | Thời điểm xử lý | Thread/transaction cần lưu ý |
| --- | --- | --- |
| `@EventListener` đồng bộ | Ngay khi publish | Thường cùng publisher thread, có thể thấy transaction đang hoạt động |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback theo completion của transaction | Được gắn vào transaction tại lúc publish, chạy sau khi commit thành công |
| `@Async @EventListener` | Task ở executor | Không tự tham gia transaction hoặc ThreadLocal của publisher |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Sau mốc commit, thân listener có thể được schedule async | Không còn được suy ra transaction context của publisher ở worker |

Ví dụ:

~~~java
// Minh họa trong Spring-managed bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    // Công việc chỉ chạy sau commit thành công.
    // Không giả định transaction cũ có thể được commit lần nữa.
}
~~~

Quan trọng:

- `@TransactionalEventListener` đăng ký synchronization khi event được publish **trong transaction**; mặc định event ngoài transaction không được xử lý (`fallbackExecution=false`).
- Sau commit, một số resource cũ vẫn có thể còn bound trong giai đoạn completion callback; nếu callback cần ghi DB mới, hãy dùng transaction độc lập (ví dụ `REQUIRES_NEW` qua proxy) hoặc đưa ghi chép vào transaction ban đầu nếu cần atomicity.
- Trộn `@TransactionalEventListener` và `@Async` không làm worker nhận lại transaction đã commit. Chỉ truyền dữ liệu nghiệp vụ cần thiết trong event và mở transaction riêng nếu tác vụ async phải ghi DB.
- Khi dùng `SimpleApplicationEventMulticaster` với executor toàn cục, các listener báo `supportsAsyncExecution()==false` (gồm những listener gắn transaction synchronization) vẫn phải được đăng ký trên thread phát event để thấy transaction đúng. Phần callback/ủy quyền công việc sau đó là một vấn đề tách biệt.

**Cảnh báo:** sao chép tài nguyên của `TransactionSynchronizationManager` từ thread cũ sang thread mới là cách làm nguy hiểm. Có thể khiến cùng JDBC Connection/EntityManager được dùng đồng thời, sai isolation và không có transaction semantics đúng. Không truyền thread-bound transaction qua decorator.

### Reactive khác ThreadLocal

Với `ReactiveTransactionManager`, ngữ cảnh giao dịch thường nằm trong **Reactor Context**, không phải ThreadLocal kiểu thread-bound transaction thông thường. Spring Framework 6.1+ hỗ trợ transactional event listener cho reactive transaction khi event mang đúng transaction context, chẳng hạn thông qua `TransactionalEventPublisher`. Không áp dụng giải pháp copy ThreadLocal của ứng dụng blocking cho pipeline reactive.

## 9. MDC, SecurityContext, RequestContext và lifecycle

### MDC và tracing

SLF4J MDC là một trường hợp phổ biến của logging context theo thread. Khi listener chạy đồng bộ, log thường có cùng requestId/traceId với publisher. Khi listener chạy async, MDC có thể trống hoặc chứa dữ liệu do task trước để lại nếu cleanup sai.

Các lựa chọn:

1. Đưa `traceId` vào event và gắn MDC cục bộ trong listener bằng `try/finally`.
2. Dùng TaskDecorator/context propagation đã cấu hình phù hợp trên executor.
3. Trong hệ thống phân tán, dùng trace context tiêu chuẩn của tracing library thay vì tự nối string ThreadLocal giữa các service.

MDC không phải nguồn thông tin tin cậy để xác nhận danh tính người dùng hoặc chọn tenant để ghi dữ liệu. Nó chỉ phục vụ quan sát/log theo cấu hình.

### SecurityContext

`SecurityContextHolder` có các chiến lược lưu context khác nhau; trong Spring Security phổ biến, chiến lược mặc định dùng ThreadLocal. Khi chuyển thread, security context có thể mất. Nếu tác vụ cần hành động với quyền của principal, dùng cơ chế propagation được kiểm soát của Spring Security và xác định **thời điểm quyền đó còn hợp lệ**. Không ghi cả authentication/token nhạy cảm vào một domain event chỉ để listener nhận được.

### RequestContextHolder và request attributes

Một HTTP request có vòng đời giới hạn. Ngay cả khi copy được `RequestAttributes` sang worker, request có thể đã kết thúc khi task thực thi; truy cập request-scoped bean lúc đó có thể lỗi hoặc không an toàn. Tách dữ liệu cần thiết (ID, locale, thông tin đã được validate) ngay lúc publish thay vì giữ reference tới request sống.

### Cleanup khi dùng thread pool

Mọi đoạn `set(...)` nên có `try/finally` kèm `remove()` hoặc restore giá trị cũ:

~~~java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(event.traceId());
    process(event);
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
~~~

Nếu code tự thay đổi ThreadLocal trong listener đồng bộ mà **không khôi phục**, nó có thể gây ảnh hưởng tới phần còn lại của request trên **cùng publisher thread**, không chỉ tới task kế tiếp trong thread pool. Vì vậy cleanup/restore quan trọng ở cả chế độ đồng bộ lẫn bất đồng bộ.

## 10. Các lỗi thường gặp

| Hiểu sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “Event tự mang ThreadLocal của publisher” | Listener async nhận null hoặc dữ liệu khác | Payload tường minh hoặc propagation có kiểm soát |
| “Không có @Async nghĩa là luôn cùng thread” | Multicaster có thể được cấu hình executor | Kiểm tra cấu hình applicationEventMulticaster |
| “Bật @Async vẫn ở transaction ban đầu” | Data access thiếu transaction hoặc nhìn sai dữ liệu | Mở transaction riêng, hoặc dùng transaction-bound event phase |
| “Dùng InheritableThreadLocal là đủ với thread pool” | Worker kế thừa snapshot cũ hoặc không kế thừa | Không dùng như cơ chế propagation cho pool |
| “Copy toàn bộ TransactionSynchronizationManager qua worker” | Tranh chấp resource và transaction sai | Không copy transaction; truyền dữ liệu và mở transaction mới |
| “MDC là định danh bảo mật” | Tin vào dữ liệu chỉ dành cho logging | Kiểm tra security/tenant boundary độc lập |
| “Set ThreadLocal xong không cần remove” | Rò thông tin giữa các task/request | try/finally, remove hoặc restore |
| “ThreadLocal trong request giữ mãi được” | Async chạy sau khi request hết hiệu lực | Snapshot giá trị cần thiết vào event |
| “@Order bảo đảm listener async hoàn thành theo thứ tự” | Race condition khi executor schedule | Đồng bộ hóa workflow bằng Future/latch hoặc cơ chế orchestration |
| “TaskDecorator tự sao chép mọi loại context” | Thiếu accessor hoặc copy nhầm dữ liệu | Chọn đúng decorator/accessor; kiểm tra test thực tế |

## 11. Kiểm thử các tình huống quan trọng

### Test listener đồng bộ

1. Set `ThreadLocal` trên thread test, publish event.
2. Kiểm tra listener đồng bộ đã đọc đúng giá trị.
3. Gọi `remove()`, publish event khác rồi xác nhận listener đọc `null`.
4. Kiểm tra listener không ghi đè context của caller hoặc có logic restore đầy đủ.

### Test listener bất đồng bộ

1. Bật `@EnableAsync` và executor thực, không thay bằng `SyncTaskExecutor` nếu mục tiêu là kiểm tra mất context.
2. Publish event có `correlationId` tường minh.
3. Dùng `CountDownLatch` hoặc `CompletableFuture` để đợi task hoàn tất có timeout; **không dựa vào `Thread.sleep`**.
4. Khẳng định worker không có ThreadLocal của publisher khi chưa cấu hình propagation.
5. Bật decorator và khẳng định chỉ những giá trị được capture thực sự xuất hiện trong worker.
6. Cho worker xử lý hai tác vụ dùng context khác nhau trên **cùng một pool thread**, kiểm tra task thứ hai không thấy dữ liệu task thứ nhất.
7. Mô phỏng listener ném exception, kiểm tra logging/metrics/handler và việc cleanup vẫn diễn ra.

### Test transaction và security

- Publish event trong `@Transactional`, so sánh callback đồng bộ với `@TransactionalEventListener(AFTER_COMMIT)` ở nhánh commit/rollback.
- Với async listener, xác minh không đọc transaction cũ bằng cách `TransactionSynchronizationManager.isActualTransactionActive()` trên worker (đừng nhầm có/không có tài nguyên bound).
- Nếu cần security context, kiểm tra cả đường thiếu context, quyền bị thu hồi và nhiều user/tenant dùng chung executor.
- Với reactive pipeline, test Reactor Context thay vì dựa vào ThreadLocal gắn theo thread name.

## 12. Checklist thiết kế

1. Listener có thực sự chạy trên publisher thread không? Có `@Async` hay multicaster executor không?
2. Dữ liệu trong ThreadLocal có cần thiết cho business logic hay chỉ để logging?
3. Giá trị nào nên đưa trực tiếp vào **event payload** để tránh phụ thuộc ngầm?
4. Nếu cần propagation, snapshot được capture **trước khi chuyển thread** chưa?
5. Có `finally` để restore/remove trên worker và publisher không?
6. Có nhầm ThreadLocal của MDC/request/security với transaction context không?
7. Transaction cần mở mới, hay callback nên chạy theo phase `AFTER_COMMIT`?
8. Executor/thread pool có giới hạn queue, timeout, error handler và giám sát không?
9. Test đã chứng minh không lộ dữ liệu qua các task dùng chung thread chưa?
10. Reactive pipeline có dùng context propagation đúng mô hình Reactor không?

**Kết luận:** Với Spring Application Events, `ThreadLocal` trong listener phụ thuộc **thread thực thi**, không phụ thuộc tên event. Listener đồng bộ mặc định nhìn thấy các giá trị thread-bound của publisher; listener bất đồng bộ không tự có chúng. Ưu tiên truyền **dữ liệu cần thiết một cách tường minh trong event**; chỉ dùng `TaskDecorator`/cơ chế propagation chuyên dụng cho ngữ cảnh phù hợp, tuyệt đối không copy transaction đang sống giữa thread và luôn cleanup để tránh rò ngữ cảnh.

## Tài liệu chính thức

- Spring Framework 6.2 — Application Events và asynchronous listeners: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Observability cho Application Events, ThreadLocal và context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — TaskDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html
- Spring Framework 6.2 — Async execution: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
