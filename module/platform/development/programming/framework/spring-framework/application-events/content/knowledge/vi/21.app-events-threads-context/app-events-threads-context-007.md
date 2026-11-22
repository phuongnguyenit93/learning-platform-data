# Context propagation trong executor khi xử lý Spring Application Events

## 1. Vấn đề: event chạy trên thread khác thì ngữ cảnh đi đâu?

Trong Spring Framework, một ứng dụng thường dùng `ApplicationEventPublisher` để gửi sự kiện cho các listener. Mặc định, `SimpleApplicationEventMulticaster` gọi các listener **đồng bộ trên thread phát event**. Vì vậy, những giá trị gắn với thread hiện tại — chẳng hạn request ID đặt trong `ThreadLocal`, logging MDC hoặc một số ngữ cảnh quan sát — thường nhìn thấy được trong listener đồng bộ.

Khi thay `SimpleApplicationEventMulticaster` bằng cấu hình sử dụng `TaskExecutor` bất đồng bộ, hoặc khi một listener được gắn `@Async`, listener có thể chạy ở **thread khác trong pool**. `ThreadLocal` thông thường không tự đi theo tác vụ. Điều này dẫn tới tình trạng:

- Log trong listener không còn `traceId` hoặc `correlationId`, khó nối log từ request gốc.
- Ngữ cảnh quan sát (observation/tracing) bị gián đoạn giữa lúc publish và xử lý event.
- Thông tin dùng cho việc kiểm soát truy cập có thể không hiện diện nếu ứng dụng vô tình dựa vào thread-local security context.
- Nếu cố “sao chép mọi thứ”, thread pool có thể rò dữ liệu từ tác vụ trước sang tác vụ sau, hoặc dùng nhầm transaction đã kết thúc.

**Context propagation** là việc *chụp (capture) những giá trị ngữ cảnh được phép truyền tại thời điểm gửi task, khôi phục (restore) chúng khi task thực thi trên worker thread, rồi dọn/khôi phục trạng thái worker ban đầu trong `finally`*.

Đó là một cơ chế **truyền dữ liệu ngữ cảnh có chọn lọc**, không phải hành động sao chép nguyên trạng request, kết nối database hoặc giao dịch Spring sang một thread khác.

~~~text
Publisher / request thread                     Worker thread từ pool
-------------------------------------------   ---------------------------------
ThreadLocal traceId = "t-42"
    |
    | publishEvent(OrderPlaced)
    |     +-- multicaster.execute(task)
    |             +-- TaskDecorator capture "t-42"
    |             +---------------------------------------------->
    |                                             restore traceId="t-42"
    |                                             @EventListener(...)
    |                                             log kèm traceId
    |                                             finally: restore/clear
    |                                                   |
    |<----------------------------------------------task hoàn tất
    |
    +-- publisher tiếp tục công việc của mình
~~~

Nếu không có cơ chế propagation, task ở worker thường đọc được `ThreadLocal.get() == null`, dù publisher đã gọi `set(...)` trước lúc gửi event.

## 2. Phân biệt bốn loại ngữ cảnh

| Loại | Ví dụ | Vấn đề khi đổi thread | Cách xử lý phù hợp |
| --- | --- | --- | --- |
| **Correlation/logging context** | `requestId`, `traceId`, MDC. | Log downstream thiếu ID hoặc lẫn ID của tác vụ trước. | Truyền snapshot nhỏ, rõ phạm vi; khôi phục/dọn trong `finally`. |
| **Tracing/observation context** | Span hiện tại, Micrometer Observation. | Span trong worker không còn liên kết đúng với publisher. | Micrometer Context Propagation + accessor được đăng ký đúng. |
| **Security context** | Spring Security `SecurityContextHolder`, principal. | Worker có thể không thấy thông tin xác thực. | Truyền có chủ đích bằng công cụ Spring Security hoặc truyền định danh/ủy quyền phù hợp. |
| **Transaction/resource context** | JDBC Connection, JPA EntityManager, Spring transaction synchronization. | Worker không tự tham gia transaction của publisher. | **Không sao chép transaction bằng ThreadLocal**; xác định ranh giới transaction mới hoặc dùng transaction-bound listener đúng cách. |

Không phải mọi `ThreadLocal` đều nên truyền. Một `requestId` bất biến có thể an toàn để phục vụ truy vết, nhưng một đối tượng request mutable, resource đang mở hoặc thông tin xác thực hết hiệu lực có rủi ro lớn hơn.

Với ứng dụng reactive, **Reactor Context** lại là một cơ chế khác: dữ liệu đi theo subscriber/subscription của pipeline. Chuyển thông tin giữa Reactor Context và một executor Java thông thường cần cầu nối có chủ đích; không thể giả định một `ThreadLocal` tự nhận được mọi giá trị từ Reactor Context.

## 3. Hai cơ chế async khác nhau trong Spring Application Events

Có hai cách phổ biến khiến event listener chạy bất đồng bộ. Chúng có điểm cấu hình khác nhau.

### 3.1. TaskExecutor của ApplicationEventMulticaster

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
~~~

*Đây là đoạn mã tích hợp Spring; cần các import `@Bean`, `@Qualifier`, `TaskExecutor` và `SimpleApplicationEventMulticaster`. Bean tên chính xác `applicationEventMulticaster` để Spring dùng multicaster được cấu hình.*

Ở chế độ mặc định, multicaster dùng cơ chế tương đương `SyncTaskExecutor` và gọi listener ngay trên thread publisher. Khi được cấp async executor, nó có thể gửi **từng listener** vào executor.

Từ Spring Framework 6.1, `ApplicationListener` có phương thức `supportsAsyncExecution()`. Những listener báo **không hỗ trợ chạy bất đồng bộ tại mức multicaster**, điển hình listener có ràng buộc transaction, vẫn được gọi trên thread phát event để có cơ hội đăng ký transaction synchronization. Vì vậy không nên kết luận mọi listener đều chuyển sang executor chỉ vì multicaster có `setTaskExecutor(...)`.

### 3.2. @Async trên phương thức @EventListener

~~~java
@Component
class NotificationListener {

    @Async("eventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Phương thức được proxy đưa lên executor đã chọn.
    }
}
~~~

*Đoạn minh họa; cần có bean `eventExecutor`, kích hoạt `@EnableAsync` và khai báo `OrderPlaced`. Đây không phải chương trình độc lập.*

`@Async` thường dựa trên proxy và một executor được chọn theo tên/qualifier. Nếu chỉ đặt decorator lên executor của **multicaster** nhưng `@Async("anotherExecutor")` lại chạy ở executor **khác**, context vẫn có thể bị mất ở chặng thứ hai. Hãy xác định **task thực tế được submit vào executor nào** và cấu hình propagation ở đó.

**Điểm phân biệt:** đa luồng ở multicaster và bất đồng bộ do `@Async` là hai lớp điều phối khác nhau. Không dùng đồng thời cả hai vô tội vạ, vì thread hop, quản lý lỗi và thứ tự có thể phức tạp thêm.

## 4. ThreadLocal và vấn đề tái sử dụng thread

`ThreadLocal<T>` cho phép mỗi thread có một giá trị riêng:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

TRACE_ID.set("trace-42");
try {
    // Chỉ thread hiện hành mặc định đọc được TRACE_ID.get().
} finally {
    TRACE_ID.remove();
}
~~~

*Đoạn code minh họa đặt trong một lớp/phương thức Java thông thường.*

`ThreadPoolTaskExecutor` tái sử dụng các worker thread. Vì vậy có hai lỗi tương phản:

**Mất context:** publisher ở thread A gọi `TRACE_ID.set("trace-42")`, nhưng worker B chưa hề được gán giá trị; listener đọc `null`.

**Rò context:** worker B đã được gán `trace-41` bởi một task trước. Nếu task không xóa/khôi phục trong `finally`, task mới có thể đọc nhầm `trace-41`. Điều này đặc biệt nguy hiểm khi context mang dữ liệu định danh người dùng hoặc tenant.

`InheritableThreadLocal` không phải giải pháp tổng quát: nó chỉ kế thừa theo điều kiện khi **tạo thread con**, trong khi executor thường dùng thread đã tạo từ trước. Nó còn có thể gây rò ngữ cảnh qua thread được tái sử dụng. Java virtual thread cũng không tự sửa vấn đề propagation qua mọi ranh giới bất đồng bộ.

## 5. TaskDecorator: capture tại lúc submit, restore tại lúc chạy

Spring cung cấp interface `org.springframework.core.task.TaskDecorator`:

~~~java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
~~~

*Chữ ký rút gọn để giải thích API; không cần định nghĩa lại interface của Spring.*

Executor có hỗ trợ decorator, như `ThreadPoolTaskExecutor`, gọi `decorate(...)` khi chuẩn bị thực thi task. Ta có thể xây dựng cơ chế truyền một `ThreadLocal` tùy chỉnh:

~~~java
static TaskDecorator captureTraceId() {
    return task -> {
        // Chạy lúc task được submit, thường trên thread của publisher.
        String captured = TRACE_ID.get();

        return () -> {
            // Chạy trên worker thread; giữ trạng thái cũ để tránh rò.
            String previous = TRACE_ID.get();
            try {
                if (captured == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(captured);
                }

                task.run();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    };
}
~~~

*Đoạn code đặt trong lớp có biến `TRACE_ID` và import `TaskDecorator`. Ví dụ đầy đủ bên dưới.*

Có bốn chi tiết quyết định:

1. **Capture tại thời điểm submit:** lấy snapshot khi producer còn giữ context, không đọc muộn ở worker và nhầm giá trị đã thay đổi.
2. **Restore trước khi thực hiện task:** listener có thể truy cập `TRACE_ID` trong phạm vi chạy.
3. **Cleanup trong `finally`:** bảo đảm cả khi listener ném exception, worker không còn giá trị của request vừa xử lý.
4. **Khôi phục trạng thái cũ:** nếu task được chạy lồng nhau hoặc worker có context hợp lệ bên ngoài, không xóa sai giá trị mà outer scope đang dùng.

Không nên viết decorator như sau:

~~~java
task -> () -> {
    TRACE_ID.set(TRACE_ID.get()); // Sai: đọc worker, không capture publisher!
    task.run();                   // Sai thêm: không cleanup.
};
~~~

Đây chỉ là anti-pattern. Nó không chuyển bất cứ giá trị nào từ publisher và không dọn context.

## 6. Ví dụ Java 17+ chạy được: listener trước và sau propagation

Ví dụ dùng **Spring Framework 6.2.9**, Java 17+ và Maven. Nó tạo hai `ApplicationContext` tách biệt, mỗi context có `SimpleApplicationEventMulticaster` sử dụng `ThreadPoolTaskExecutor`:

- Lần một **không** có `TaskDecorator`: worker không nhìn thấy `ThreadLocal` của publisher.
- Lần hai **có** decorator: worker nhận bản chụp `trace-42` và khôi phục trạng thái sau khi chạy.

`CountDownLatch` giúp chương trình chờ listener hoàn tất trước khi đọc kết quả, thay vì đoán bằng `Thread.sleep(...)`. Giá trị `null` trong stdout là chuỗi mô tả được tạo có chủ đích, không phải lỗi format.

### 6.1. Cấu trúc

~~~text
event-context-demo/
├── pom.xml
└── src/main/java/EventContextDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

`src/main/java/EventContextDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventContextDemo {

    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record WorkRequested(String jobId) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public WorkListener workListener() {
            return new WorkListener();
        }
    }

    public static class WorkListener {

        private final CountDownLatch done = new CountDownLatch(1);
        private volatile String observedTraceId;

        @EventListener
        public void onWork(WorkRequested event) {
            String value = TRACE_ID.get();
            observedTraceId = (value == null ? "null" : value);
            done.countDown();
        }

        public String awaitObservation() throws InterruptedException {
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Event listener timed out");
            }
            return observedTraceId;
        }
    }

    private static TaskDecorator traceDecorator() {
        return task -> {
            String captured = TRACE_ID.get();

            return () -> {
                String oldValue = TRACE_ID.get();
                try {
                    if (captured == null) {
                        TRACE_ID.remove();
                    } else {
                        TRACE_ID.set(captured);
                    }

                    task.run();
                } finally {
                    if (oldValue == null) {
                        TRACE_ID.remove();
                    } else {
                        TRACE_ID.set(oldValue);
                    }
                }
            };
        };
    }

    private static void runCase(boolean enablePropagation)
            throws InterruptedException {

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");

        if (enablePropagation) {
            executor.setTaskDecorator(traceDecorator());
        }
        executor.initialize();

        try {
            try (var context = new AnnotationConfigApplicationContext()) {
                context.register(Config.class);

                // Tên bean bắt buộc để Spring chọn multicaster tùy biến.
                context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster =
                            new SimpleApplicationEventMulticaster();
                        multicaster.setTaskExecutor(executor);
                        return multicaster;
                    });

                context.refresh();

                TRACE_ID.set("trace-42");
                try {
                    context.publishEvent(new WorkRequested("job-7"));

                    // Listener chạy async: đồng bộ bằng latch.
                    String value = context.getBean(WorkListener.class)
                            .awaitObservation();

                    String mode = enablePropagation ? "WITH" : "WITHOUT";
                    System.out.println(mode + " decorator: " + value);
                } finally {
                    TRACE_ID.remove();
                }
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        runCase(false);
        runCase(true);
    }
}
~~~

Lệnh chạy (tại thư mục chứa `pom.xml`):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventContextDemo
~~~

Stdout do chương trình in ra, không tính log riêng của Maven:

~~~text
WITHOUT decorator: null
WITH decorator: trace-42
~~~

### 6.2. Phân tích kết quả

- `TRACE_ID.set("trace-42")` chạy trên thread gọi `publishEvent(...)`, không phải trên thread của `event-worker-*`.
- Multicaster được cấu hình `setTaskExecutor(executor)` nên listener `@EventListener` nhận `WorkRequested` được submit như một tác vụ bất đồng bộ.
- **Không decorator:** worker không tự có ThreadLocal của publisher; `TRACE_ID.get()` trả `null`.
- **Có decorator:** lúc submit, `traceDecorator()` capture `trace-42`. Khi tác vụ chạy, decorator đặt giá trị đó vào ThreadLocal của worker; listener đọc được `trace-42`.
- Listener báo hoàn thành qua `CountDownLatch`, nhờ đó main không phụ thuộc vào tốc độ thread pool.
- Khối `finally` trong decorator dọn/khôi phục context. `try-with-resources` đóng `AnnotationConfigApplicationContext`, còn `executor.shutdown()` giải phóng worker thread.

Chương trình cố ý chỉ xử lý **một application event ở mỗi lượt** nên không cần áp đặt thứ tự giữa nhiều listener async. Nó cũng không sử dụng transaction hoặc Spring Security, tránh nhầm lẫn propagation của trace ID với propagation của tài nguyên khác.

## 7. Spring ContextPropagatingTaskDecorator và Micrometer

Từ Spring Framework **6.1**, Spring có `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. Nó dùng cơ chế **Micrometer Context Propagation**, hữu ích để truyền một số giá trị như logging/observation context khi task chạy ở thread khác.

Trong Spring Framework 6.2, đoạn cấu hình tích hợp có thể viết:

~~~java
@Configuration
class EventExecutorConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("events-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

*Đây là đoạn **cấu hình tích hợp**, không phải ví dụ Maven độc lập: cần import `@Configuration`, `@Bean`, `@Qualifier`, `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator` và `SimpleApplicationEventMulticaster`. Trên classpath cần thư viện `io.micrometer:context-propagation` tương thích; với Spring Boot nên ưu tiên dependency management của Boot.*

**Không có nghĩa nó tự động sao chép mọi ThreadLocal.** Micrometer truyền các context mà thư viện nhận biết thông qua các `ThreadLocalAccessor`/`ContextAccessor` được đăng ký. Với `ThreadLocal` tùy biến của ứng dụng, cần cung cấp accessor phù hợp nếu muốn sử dụng decorator chuẩn thay vì tự viết thủ công. Việc MDC có được chuyển đầy đủ hay không cũng phụ thuộc logging stack và accessor thực tế.

Cơ chế ở mức khái niệm:

~~~text
Publisher thread                           Worker thread
Micrometer ContextSnapshot                ContextSnapshot.Scope
  | capture registered contexts               | restore registered values
  +------------------------------------------>| task.run()
                                              | finally: close Scope
                                              | restore previous worker context
~~~

Các ưu điểm:

- Có thể quản lý nhiều loại context qua cùng cơ chế snapshot.
- Dễ tích hợp với Micrometer Observation/tracing nếu cấu hình đúng.
- Giảm nguy cơ viết sai logic `try/finally` cho mỗi `ThreadLocal` tự định nghĩa.

Các giới hạn:

- Chỉ những dữ liệu có accessor/hạ tầng tương ứng mới được chuyển.
- Capture/restore có chi phí CPU và bộ nhớ; không nên gắn một bộ snapshot lớn cho hàng triệu task quá nhỏ nếu chưa đo hiệu năng.
- Không biến dữ liệu mutable không an toàn thành thread-safe.
- Không tự truyền `EntityManager`, JDBC connection hoặc transaction đang hoạt động.

Spring hỗ trợ `CompositeTaskDecorator` khi cần phối hợp nhiều decorator; vẫn cần xác định thứ tự set/clear và tránh đặt chồng nhiều giải pháp copy cùng một context khiến giá trị bị ghi đè.

## 8. Logging MDC: giải pháp riêng cho hệ thống có SLF4J

Một số ứng dụng sử dụng `org.slf4j.MDC` để đưa `traceId`, `requestId` vào định dạng log:

~~~text
2026-11-11 14:00:00 INFO [trace-42] OrderPlaced received
2026-11-11 14:00:01 INFO [trace-42] Order email scheduled
~~~

*Các timestamp là ví dụ minh họa, không phải stdout từ chương trình ở phần 6.*

Nếu chưa dùng Micrometer propagation hoặc muốn điều khiển MDC trực tiếp, có thể xây dựng `TaskDecorator` với snapshot của MDC:

~~~java
TaskDecorator mdcDecorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }

            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
};
~~~

*Đây là đoạn minh họa cần `java.util.Map`, `org.slf4j.MDC` và `org.springframework.core.task.TaskDecorator`; phải có SLF4J/logging implementation thích hợp. Không phải đoạn mã chạy độc lập.*

Vì sao dùng `getCopyOfContextMap()`? Bởi vì ta muốn capture **bản sao dữ liệu logging hiện tại** ở thời điểm submit, không chia sẻ một map mutable sống giữa publisher và worker.

**Lưu ý:** MDC không phải storage bảo mật. Đừng đưa access token, mật khẩu hoặc thông tin nhạy cảm vào MDC chỉ để “truyền context” vì log có thể ghi hoặc xuất dữ liệu đó ngoài ý muốn.

## 9. SecurityContext: propagation không tương đương ủy quyền

Spring Security thông thường lưu `SecurityContext` của thread trong `SecurityContextHolder`. Với một task được đẩy sang executor, worker có thể không nhận được authentication của publisher.

Spring Security cung cấp các wrapper như `DelegatingSecurityContextExecutor` hoặc `DelegatingSecurityContextAsyncTaskExecutor` để chuyển security context trong những tình huống phù hợp. Khi dùng chúng:

1. Chọn đúng security context muốn chuyển (context cố định hay context tại lúc submit).
2. Kiểm tra task thật sự sử dụng executor đã được bọc; `@Async` có thể chọn một bean khác.
3. Giới hạn quyền và thời gian sống của context; không vô tình biến tác vụ chạy lâu thành nhiệm vụ có quyền vĩnh viễn của người dùng ban đầu.
4. Khôi phục/dọn trạng thái sau khi task hoàn tất để tránh rò principal sang task khác.
5. Nếu công việc chạy sau request quá lâu hoặc sau khi quyền của người dùng đã thay đổi, cân nhắc dùng service account/ủy quyền riêng thay vì duy trì đối tượng authentication cũ.

**Không sao chép `SecurityContextHolder` bằng `ThreadLocal` tự định nghĩa rồi mặc định coi đó là cơ chế bảo mật đầy đủ.** Các tác động của phân quyền, hủy phiên và timeout phải được thiết kế rõ theo yêu cầu nghiệp vụ.

## 10. Vì sao không propagation Spring transaction bằng cách copy ThreadLocal?

Đây là cảnh báo quan trọng nhất khi thảo luận context propagation trong Spring events.

Với giao dịch imperative (JDBC/JPA), Spring sử dụng `org.springframework.transaction.support.TransactionSynchronizationManager` để liên kết resource và transaction synchronization với **thread hiện tại**. Nếu một service đang trong `@Transactional` rồi phát event, listener đồng bộ có thể chạy khi transaction đó đang hoạt động. Khi listener được chuyển sang thread khác:

- Worker không tự tham gia transaction của publisher.
- Bắt một `ThreadLocal` trỏ tới transaction state hoặc JDBC connection rồi gắn vào worker không an toàn: transaction/resource có vòng đời, thread-safety và quy tắc commit/rollback riêng.
- Thread publisher có thể hoàn tất/rollback transaction trước khi worker xử lý xong.
- Đoạn code chạy ngoài transaction có thể có hành vi `LazyInitializationException` hoặc nhìn thấy dữ liệu khác với kỳ vọng.

**Không tạo một “transaction decorator” bằng cách copy `TransactionSynchronizationManager` từ A sang B.** Đây không phải cơ chế được Spring thiết kế để share transaction JDBC/JPA đồng thời giữa threads.

Nếu listener async cần ghi dữ liệu vào DB, hãy chủ động tạo **transaction mới ở worker**, ví dụ tách phần xử lý sang một Spring service có `@Transactional` được gọi qua proxy phù hợp. Nếu yêu cầu chỉ phản ứng khi transaction ban đầu commit thành công, dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` với thiết kế xử lý sau commit phù hợp và, khi cần bền vững, transactional outbox.

Một nuance quan trọng từ Spring Framework 6.1: transaction-synchronized listener báo không hỗ trợ việc **multicaster** tùy ý đẩy toàn bộ callback sang thread khác (`supportsAsyncExecution() == false`). Nhưng phương thức xử lý có `@Async` hoặc tác vụ nó tự submit vẫn có thể chuyển sang executor; đừng kết luận transaction cũ vì thế đi theo task.

Với **reactive transaction** sử dụng `ReactiveTransactionManager`, context chủ yếu đi theo Reactor subscriber context thay vì JDBC thread-local. Nếu cần xử lý reactive transaction event, cơ chế phù hợp là pipeline/`TransactionalEventPublisher`, không phải copy các ThreadLocal Java bằng decorator.

## 11. Capture lifecycle, cleanup và thông tin nhạy cảm

Một decorator tốt không chỉ “đặt giá trị được truyền” mà còn phải xử lý vòng đời dữ liệu:

| Thời điểm | Thực hành đúng |
| --- | --- |
| Trước khi submit | Capture snapshot nhỏ, bất biến hoặc được sao chép phòng vệ. |
| Khi worker bắt đầu | Lưu trạng thái cũ của worker rồi restore snapshot cần thiết. |
| Khi listener chạy | Chỉ dùng giá trị cần cho log/tracing hoặc kiểm soát đã được thiết kế. |
| Khi listener thành công | Hoàn tất và trả trạng thái worker về như trước. |
| Khi listener lỗi | Vẫn cleanup bằng `finally`, đồng thời báo/ghi nhận lỗi theo policy. |
| Khi task bị hủy trước lúc chạy | Tránh lưu reference tới payload/context lớn hoặc chứa bí mật trong queue quá lâu. |
| Khi ứng dụng shutdown | Đóng executor theo lifecycle, chờ task cần thiết hoặc đặt chính sách hủy rõ. |

Đừng đặt cả `HttpServletRequest` vào một `ThreadLocal` để chuyển qua worker: request/response có vòng đời gắn với luồng HTTP; task chạy muộn có thể dùng object đã hết hiệu lực hoặc giữ tài nguyên ngoài ý muốn. Nếu cần dữ liệu, **trích xuất các trường cần thiết**, chẳng hạn correlation ID, mã tenant được xác thực và dữ liệu nghiệp vụ bất biến.

Nếu context được ghi vào log hoặc telemetry, cần tuân thủ chính sách riêng tư và phân quyền. Metadata phục vụ truy vết không nên chứa số thẻ, mật khẩu hay token nguyên văn.

## 12. Kiểm thử context propagation và concurrency

Bộ kiểm thử tối thiểu nên chứng minh cả **đúng ngữ cảnh** lẫn **không rò ngữ cảnh**:

1. Một listener đồng bộ đọc được request ID khi publisher và listener chạy cùng thread.
2. Listener async trên executor không trang trí **không** ngầm có custom ThreadLocal từ publisher.
3. Executor với decorator đúng capture request ID tại thời điểm submit và restore lúc chạy.
4. Hai sự kiện từ hai request khác nhau có ID khác nhau; worker không dùng nhầm ID của request trước.
5. Sau khi listener ném exception, worker đã cleanup để task kế tiếp không thấy context cũ.
6. Khi publisher không có context, decorator xử lý đúng trường hợp `null`/absent thay vì “giữ lại” dữ liệu của worker.
7. Khi task chạy lồng nhau, trạng thái trước task được khôi phục chính xác.
8. Nếu có Spring Security, kiểm thử đúng principal/authority theo semantics mong muốn và không rò tenant.
9. Nếu dùng Micrometer, kiểm tra accessor/Observation thật sự được đăng ký; có dependency mà không có accessor phù hợp có thể vẫn mất custom ThreadLocal.
10. Đảm bảo transaction không bị chia sẻ sai giữa thread; listener async mở giao dịch riêng khi nghiệp vụ yêu cầu.

Trong test async, dùng `CountDownLatch`, `CompletableFuture`, `Awaitility` hoặc các điều kiện đồng bộ có timeout. Không dùng `Thread.sleep(100)` rồi giả định executor đã chạy xong, vì nó gây test chập chờn trên CI.

Về thứ tự: ngay cả khi context propagation hoạt động, **nó không bảo đảm thứ tự xử lý event** giữa nhiều worker. Nếu nghiệp vụ cần ordering, phải cấu hình queue/partition/serial executor hoặc điều phối trên mức nghiệp vụ. Propagation chỉ giải quyết **ngữ cảnh của task**, không thay đổi semantics scheduling.

## 13. Xử lý lỗi và quan sát hệ thống

Khi listener chạy bất đồng bộ, exception thường xảy ra trên worker thay vì đi thẳng về người gọi `publishEvent(...)`. Điều đó ảnh hưởng cách báo lỗi:

- Với async multicaster, cân nhắc `SimpleApplicationEventMulticaster.setErrorHandler(...)` để quan sát lỗi listener được dispatch qua multicaster; không nuốt lỗi không có metric hoặc log.
- Với `@Async`, quản lý exception thông qua `AsyncUncaughtExceptionHandler` cho các method `void`, hoặc `Future`/`CompletableFuture` khi signature thích hợp.
- `TaskDecorator` chủ yếu được thiết kế để wrap task và context; đừng giả định nó luôn nhìn thấy exception từ mọi `FutureTask` vì wrapper có thể giữ exception trong future.
- Nếu yêu cầu retry sau lỗi, Spring Application Events không tự là durable queue; cần cơ chế retry/idempotency rõ ràng và, nếu không được phép mất sự kiện, cân nhắc outbox/broker.
- Khi log, ghi correlation ID, tên event, handler, thời điểm, kết quả và exception type; tránh log toàn bộ payload nhạy cảm.

Một quy trình chẩn đoán khi log listener không có trace:

~~~text
Log ở publisher có traceId?
  |
  +-- Không -> nguồn trace đã thiếu; kiểm tra request/filter/tracing trước.
  |
  +-- Có
       |
       +-- Listener sync trên cùng thread?
       |       |
       |       +-- Có -> kiểm tra lifecycle đặt/xóa ThreadLocal.
       |       +-- Không -> xác định executor đang chạy listener.
       |
       +-- Decorator có gắn vào executor thực sự?
       |       |
       |       +-- Không -> cấu hình đúng bean.
       |       +-- Có
       |             |
       |             +-- Accessor/snapshot có capture giá trị đó?
       |             +-- Decorator có restore rồi cleanup?
       |             +-- Có thêm hop @Async hoặc scheduler khác?
       |
       +-- Có truy cập resource/transaction từ publisher?
               |
               +-- Có -> thiết kế lại transaction boundary, KHÔNG copy connection.
~~~

## 14. Những lỗi phổ biến

1. **Cho rằng `@Async` tự mang mọi ThreadLocal sang worker.** Nó chỉ chuyển cách thực thi; context propagation cần cấu hình riêng.
2. **Trang trí sai executor.** Multicaster dùng `eventExecutor` nhưng `@Async` lại dùng một executor khác; context vẫn mất.
3. **Capture trong worker thay vì publisher.** Worker chỉ thấy giá trị riêng của nó; phải capture trước lúc task chạy.
4. **Không restore/cleanup trong `finally`.** Thread pool giữ dữ liệu của task trước, có thể rò thông tin người dùng hoặc tenant.
5. **Dùng `InheritableThreadLocal` như giải pháp cho pool.** Nó không ổn định với thread được tái sử dụng.
6. **Cho rằng `ContextPropagatingTaskDecorator` tự truyền mọi thứ.** Chỉ context có accessor/hạ tầng tương ứng mới được hỗ trợ.
7. **Copy `TransactionSynchronizationManager` hoặc JDBC Connection sang thread khác.** Không thay thế được transaction management đúng cách và có thể gây sai lệch nghiêm trọng.
8. **Chia sẻ mutable request/entity giữa các worker.** Context metadata không làm các đối tượng đó thread-safe.
9. **Không có timeout và error handling.** Caller có thể đã trả kết quả nhưng listener async thất bại âm thầm.
10. **Cho rằng có trace ID thì có bảo đảm delivery.** Tracing không tự cung cấp queue, retry, exactly-once hay rollback.
11. **Log thông tin xác thực nhạy cảm trong MDC.** Propagation làm tăng số nơi dữ liệu nhạy cảm xuất hiện; chỉ ghi metadata tối thiểu.
12. **Giả định một listener transaction-bound sẽ luôn được multicaster chuyển sang pool.** Spring có cơ chế không hỗ trợ async ở mức multicaster cho transaction-synchronized listener.

## 15. Bài tập tự kiểm tra

**Câu 1.** Vì sao `ThreadLocal.set("trace-42")` trong controller không bảo đảm một `@EventListener` chạy ở thread pool đọc được giá trị đó?

**Đáp án:** `ThreadLocal` thuộc từng thread, không tự sao chép từ publisher sang worker trong executor. Cần propagation có chủ đích.

**Câu 2.** `TaskDecorator.decorate(...)` nên capture giá trị vào thời điểm nào?

**Đáp án:** Khi task được chuẩn bị/submit trên thread có context gốc. Runnable trả về sẽ restore giá trị đó khi worker thực sự chạy.

**Câu 3.** Vì sao cần `finally` kể cả khi listener thành công ở hầu hết lần gọi?

**Đáp án:** Worker thread được dùng lại. Nếu listener lỗi hoặc task kết thúc bất thường mà không cleanup, context cũ có thể rò sang task sau.

**Câu 4.** Có thể dùng `ContextPropagatingTaskDecorator` để đưa JDBC transaction của controller sang listener chạy trên thread khác không?

**Đáp án:** Không. Propagation dùng cho những context có accessor như logging/tracing, không bảo đảm an toàn khi sao chép transaction/resource gắn với thread và transaction manager.

**Câu 5.** Multicaster dùng `eventExecutor` nhưng listener ghi `@Async("mailExecutor")`. Đặt decorator trên executor nào?

**Đáp án:** Cần xem các thread hop thực tế; chỉ decorator trên `eventExecutor` có thể chưa đủ. Task được `@Async` gửi vào `mailExecutor` cũng cần propagation thích hợp.

**Câu 6.** Nếu một custom ThreadLocal chưa được đăng ký `ThreadLocalAccessor`, việc thêm thư viện Micrometer Context Propagation có chắc truyền được nó không?

**Đáp án:** Không. Phải có accessor hoặc một cơ chế capture/restore tường minh cho giá trị đó.

**Câu 7.** Propagation bảo đảm điều gì, và không bảo đảm điều gì?

**Đáp án:** Nó giúp task nhận đúng các giá trị ngữ cảnh được chọn và cleanup an toàn. Nó **không** bảo đảm thứ tự event, commit transaction, retry, durable delivery hay bảo mật nếu authority/identity được thiết kế sai.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): listener đồng bộ mặc định, cấu hình `SimpleApplicationEventMulticaster`, `@Async` và context.
- [Spring Framework Reference — Observability: Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html): propagate observation/log context qua executor bằng `ContextPropagatingTaskDecorator`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `TaskDecorator` và `@Async`.
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): executor, mặc định đồng bộ và ngoại lệ `supportsAsyncExecution`.
- [Spring Framework 6.2 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): capture/restore context cho worker, chi phí thực thi.
- [Spring Framework 6.2 Javadoc — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html): decorator wrap `Runnable` và lưu ý về exception trong `Future`.
- [Micrometer Context Propagation](https://micrometer.io/docs/contextPropagation): `ContextSnapshot`, `ThreadLocalAccessor` và đăng ký context accessor.
