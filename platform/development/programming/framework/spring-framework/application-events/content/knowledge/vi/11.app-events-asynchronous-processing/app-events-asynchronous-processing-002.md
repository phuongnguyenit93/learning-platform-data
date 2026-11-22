# `@EnableAsync` và proxy method khi xử lý Application Events bất đồng bộ trong Spring Framework

## 1. Bài toán: vì sao gắn `@Async` chưa chắc đã chạy trên thread khác?

Trong Spring Framework, `@Async` đánh dấu một phương thức có thể được thực thi bằng `Executor` ở thread khác. `@EnableAsync` kích hoạt hạ tầng phát hiện và áp dụng cơ chế đó cho các Spring bean trong `ApplicationContext`. Theo mặc định, Spring triển khai bằng **AOP proxy**: lời gọi phải **đi qua proxy** để `@Async` được chặn và đưa vào executor.

Vì vậy, hai đoạn gọi sau có thể có kết quả rất khác nhau:

```java
// Đối tượng được Spring cung cấp, thông qua proxy:
worker.doWork(); // @Async có hiệu lực nếu đây là lời gọi qua proxy.

// Bên trong chính lớp Worker:
this.doWork();   // self-invocation: bỏ qua proxy ở chế độ mặc định.
```

Đây là đoạn mã minh họa; `worker` là bean được lấy từ Spring và `doWork()` là phương thức có `@Async`. `@EnableAsync` **không biến mọi lời gọi Java thông thường thành bất đồng bộ**. Khi gọi nội bộ qua `this`, code thường chạy trực tiếp trên thread hiện tại, dù phương thức đích được đánh dấu `@Async`.

Trong module **Spring Framework Application Events**, vấn đề này đặc biệt quan trọng khi kết hợp:

```java
@Async
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Xử lý ngoài thread phát sự kiện nếu async interceptor được áp dụng.
}
```

Spring thường gọi phương thức `@EventListener` đã đăng ký thông qua bean được quản lý; nếu async proxy đang hoạt động, listener có thể được đưa lên executor. Nhưng một lời gọi nội bộ trực tiếp `this.onOrderCreated(event)` vẫn tuân theo quy tắc proxy: annotation không tự sinh thread.

## 2. Vai trò của từng thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| `@EnableAsync` | Kích hoạt hạ tầng phát hiện lời gọi `@Async` trong context hiện tại. |
| `@Async` | Gắn nhãn cho phương thức hoặc kiểu bean để interceptor đưa lời gọi hợp lệ vào executor. |
| AOP proxy | Đối tượng trung gian nhận cuộc gọi từ bean bên ngoài và áp dụng async advice. |
| `AsyncAnnotationBeanPostProcessor` | Tạo/gắn async interceptor vào Spring bean thích hợp. |
| `Executor` / `TaskExecutor` | Quản lý thread và chạy tác vụ được submit. |
| `ApplicationEventPublisher` | Phát event từ ứng dụng. |
| `@EventListener` | Đăng ký phương thức lắng nghe event; có thể kết hợp `@Async` nếu cần xử lý nền. |
| `ApplicationEventMulticaster` | Phân phối event đến listener tương thích; mặc định đồng bộ nếu không cấu hình executor chung. |

Luồng gọi một phương thức nghiệp vụ có `@Async`:

```text
Client/Publisher thread
        |
        v
Spring bean proxy
        |
        +-- async interceptor -> executor.execute(task)
        |                                 |
        |                                 v
        |                          worker thread chạy method
        v
Caller tiếp tục
```

Luồng gọi nội bộ:

```text
Client -> proxy -> Worker.selfInvocation()
                     |
                     +-- this.doWork()
                           (bỏ qua proxy)
                           chạy ngay trên cùng thread
```

**Thời điểm chạy không bảo đảm chính xác:** gọi qua proxy đưa tác vụ vào executor, nhưng tác vụ có thể bắt đầu trước hoặc sau khi caller thực hiện dòng kế tiếp. Không dựa vào thứ tự các dòng log để khẳng định tính bất đồng bộ. Hãy kiểm tra thread, latch/future hoặc hiệu ứng thực tế.

## 3. Ví dụ Java 17+ chạy được: event listener, proxy call và self-invocation

Ví dụ độc lập dưới đây dùng Spring Framework 6.2.12, không yêu cầu Spring Boot, database hay web server. Nó cho thấy:

1. `@EventListener @Async("eventExecutor")` được thực thi ở thread `event-*`.
2. Gọi `worker.selfInvocation()` khiến `this.doWork("self")` chạy trên thread caller, vì không đi qua proxy.
3. Gọi `worker.doWork("external")` từ bên ngoài bean, thông qua proxy do Spring trả về, chạy trên executor.

Cấu trúc:

```text
async-event-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncProxyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'async-event-proxy-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.AsyncProxyDemo'
}
```

`src/main/java/demo/AsyncProxyDemo.java`:

```java
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

public class AsyncProxyDemo {

    public record JobQueued(String id) {}

    public static class EventObserver {
        private final CountDownLatch done = new CountDownLatch(1);
        private final AtomicReference<String> runningThread =
                new AtomicReference<>();

        @EventListener
        @Async("eventExecutor")
        public void onJobQueued(JobQueued event) {
            runningThread.set(Thread.currentThread().getName());
            done.countDown();
        }

        public boolean awaitEvent() throws InterruptedException {
            return done.await(5, TimeUnit.SECONDS);
        }

        public String runningThread() {
            return runningThread.get();
        }
    }

    public static class TaskWorker {
        private final AtomicReference<String> selfThread =
                new AtomicReference<>();
        private final AtomicReference<String> externalThread =
                new AtomicReference<>();
        private final CountDownLatch externalDone = new CountDownLatch(1);

        // Method được intercept khi được gọi QUA Spring proxy.
        @Async("eventExecutor")
        public void doWork(String origin) {
            if ("self".equals(origin)) {
                selfThread.set(Thread.currentThread().getName());
            } else if ("external".equals(origin)) {
                externalThread.set(Thread.currentThread().getName());
                externalDone.countDown();
            }
        }

        public void selfInvocation() {
            // Lời gọi nội bộ qua this, không đi qua Spring proxy.
            this.doWork("self");
        }

        public boolean awaitExternal() throws InterruptedException {
            return externalDone.await(5, TimeUnit.SECONDS);
        }

        public String selfThread() {
            return selfThread.get();
        }

        public String externalThread() {
            return externalThread.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        EventObserver eventObserver() {
            return new EventObserver();
        }

        @Bean
        TaskWorker taskWorker() {
            return new TaskWorker();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            EventObserver observer = context.getBean(EventObserver.class);
            TaskWorker worker = context.getBean(TaskWorker.class);
            String callerThread = Thread.currentThread().getName();

            context.publishEvent(new JobQueued("J-1"));
            if (!observer.awaitEvent()) {
                throw new IllegalStateException("Event listener timed out");
            }

            worker.selfInvocation();
            worker.doWork("external");
            if (!worker.awaitExternal()) {
                throw new IllegalStateException("Async worker timed out");
            }

            System.out.println("event used executor: "
                    + observer.runningThread().startsWith("event-"));
            System.out.println("self call used caller: "
                    + callerThread.equals(worker.selfThread()));
            System.out.println("external call used executor: "
                    + worker.externalThread().startsWith("event-"));
        }
    }
}
```

Chạy với **JDK 17+** và Gradle đã được cài sẵn:

```bash
gradle -q run
```

Ba dòng `System.out.println` của chương trình:

```text
event used executor: true
self call used caller: true
external call used executor: true
```

**Giải thích kết quả:**

- `@EnableAsync` đăng ký hạ tầng async của Spring. Cả `EventObserver` và `TaskWorker` đều là bean được context tạo; các phương thức `@Async` công khai đủ điều kiện nhận proxy.
- `context.publishEvent(...)` đi qua Spring event infrastructure. Phương thức listener được gọi thông qua bean Spring và có `@Async("eventExecutor")`, nên phần xử lý chạy trong executor đã đặt tên.
- `selfInvocation()` là cuộc gọi từ bên ngoài qua bean, nhưng bên trong phương thức đó, `this.doWork("self")` gọi trực tiếp lên đối tượng đích. Không có async interceptor tại điểm gọi nội bộ, nên thread bằng thread của caller.
- `worker.doWork("external")` đi qua proxy; interceptor submit tác vụ vào executor, nên tên thread bắt đầu bằng `event-`.
- `CountDownLatch` dùng để **chờ xác nhận tác vụ xong**, không dựa vào `Thread.sleep()` hoặc thứ tự log dễ thay đổi. Có timeout rõ ràng; nếu executor bị từ chối hoặc tác vụ không chạy kịp, ví dụ sẽ báo lỗi thay vì chờ vô hạn.
- Getter dùng để đọc trạng thái của bean thay vì truy cập trực tiếp field trên đối tượng proxy; qua proxy lớp, trạng thái của wrapper và target không nên được giả định trùng nhau.

`JobQueued` là Java record, không cần kế thừa `ApplicationEvent`. Spring hỗ trợ phát object payload; listener `@EventListener` vẫn nhận đúng kiểu payload.

## 4. Proxy hoạt động ra sao, và self-invocation làm mất `@Async` như thế nào?

`@EnableAsync` mặc định dùng `AdviceMode.PROXY`. Trong chế độ này, async interceptor chỉ chạy khi lời gọi có đường đi qua proxy. Ví dụ một bean:

```java
@Service
public class ReportService {

    public void createReport() {
        sendNotificationAsync(); // Gọi nội bộ: không kích hoạt @Async.
    }

    @Async
    public void sendNotificationAsync() {
        // Vẫn có thể chạy đồng bộ nếu bị gọi bằng this.
    }
}
```

Đây là **đoạn minh họa**, cần khai báo `@EnableAsync`, import annotation và cấu hình executor trong ứng dụng. Nếu `createReport()` được gọi qua proxy, nội dung `createReport()` vẫn thực thi trên đối tượng target; từ đó `sendNotificationAsync()` được gọi bằng `this`, vì vậy không chạm lại async proxy.

Các tình huống thường làm proxy không can thiệp:

- **Self-invocation:** `this.asyncMethod()` hoặc gọi trực tiếp `asyncMethod()` từ một phương thức khác cùng instance.
- **Đối tượng không được Spring quản lý:** `new ReportService()` là object thông thường, không được Spring gắn async proxy.
- **Phương thức `private`:** proxy mode không thể intercept lời gọi phương thức private từ bên ngoài như một phương thức bean công khai.
- **Phương thức hoặc lớp `final` khi cần subclass-based proxy:** proxy CGLIB không thể override phương thức final hoặc kế thừa lớp final.
- **Đang ở giai đoạn constructor / khởi tạo nội bộ:** proxy có thể chưa sẵn sàng, không thiết kế async bằng cách tự gọi method `@Async` trong constructor hay `@PostConstruct`.
- **Gọi qua kiểu/interface không được proxy expose:** trong cấu hình JDK dynamic proxy, cần gọi thông qua interface thích hợp; không giả định có thể cast proxy sang implementation.
- **Chưa bật `@EnableAsync` trong `ApplicationContext` chứa bean:** `@Async` không tự kích hoạt hạ tầng, và context cha/con có phạm vi cấu hình riêng.

Phân biệt hai chiến lược proxy:

| Kiểu proxy | Điều kiện điển hình | Lưu ý |
| --- | --- | --- |
| JDK dynamic proxy | Bean có interface phù hợp và proxy được cấu hình dùng interface | Caller làm việc qua interface mà proxy expose; không thể intercept self-invocation. |
| CGLIB subclass proxy | Bean cần proxy theo lớp, ví dụ lớp không có interface phù hợp | Không thể override final method và không thể kế thừa final class; cũng không xử lý self-invocation theo proxy mode. |

`@EnableAsync(proxyTargetClass = true)` yêu cầu kiểu class-based proxy khi dùng `AdviceMode.PROXY`, nhưng **không sửa lỗi self-invocation**. Chọn JDK hay CGLIB không tự thay đổi quy tắc đó. Phạm vi ảnh hưởng của cấu hình proxy có thể thay đổi theo cách Spring hợp nhất auto-proxy settings trong phiên bản và môi trường dự án; kiểm tra với phiên bản thực tế.

### Cách sửa self-invocation được khuyến nghị: tách sang bean khác

```java
@Service
public class NotificationWorker {
    @Async("eventExecutor")
    public void sendAsync(String orderId) {
        // Xử lý bất đồng bộ.
    }
}

@Service
public class OrderService {
    private final NotificationWorker notificationWorker;

    public OrderService(NotificationWorker notificationWorker) {
        this.notificationWorker = notificationWorker;
    }

    public void completeOrder(String orderId) {
        // Các bước nghiệp vụ...
        notificationWorker.sendAsync(orderId); // Gọi qua bean Spring được inject.
    }
}
```

Đây là **mã minh họa gồm hai Spring-managed bean**; cần import `@Service`, `@Async`, bật `@EnableAsync`, và định nghĩa bean executor tên `eventExecutor`. Đưa công việc async sang bean khác giúp lời gọi xuyên qua bean proxy và khiến trách nhiệm rõ ràng. Trong hệ thống thật, định nghĩa rõ transaction, lỗi và thời điểm gọi trước/sau commit.

Các cách khác tồn tại nhưng cần cân nhắc kỹ:

- Inject proxy của chính bean vào chính nó, hoặc lấy bean từ `ApplicationContext`, có thể khiến phụ thuộc vòng/cấu trúc khó hiểu; chỉ dùng khi thật sự có lý do.
- `AopContext.currentProxy()` cần bật expose-proxy và khiến nghiệp vụ phụ thuộc Spring AOP; không phải hướng mặc định.
- `@EnableAsync(mode = AdviceMode.ASPECTJ)` có thể áp dụng advice kể cả lời gọi nội bộ nếu đã cấu hình `spring-aspects` và compile-time/load-time weaving. Chỉ đổi `mode` mà không có weaving thì không đủ; đây là cơ chế khác với proxy mode.

## 5. `@EnableAsync` chọn executor như thế nào?

Đối với phương thức `@Async` không chỉ định tên executor, Spring dùng executor cấu hình cho async support nếu có (ví dụ thông qua `AsyncConfigurer`). Nếu không cấu hình tường minh, Spring tìm `TaskExecutor` duy nhất trong context, hoặc `Executor` có tên `taskExecutor`; nếu không tìm thấy, hạ tầng Spring Framework có thể dùng `SimpleAsyncTaskExecutor` làm fallback. Trong Spring Boot, auto-configuration có thể tạo executor mặc định tùy phiên bản/cấu hình; cần kiểm tra bean thực tế đang được dùng.

**Không nên để chính sách thread phụ thuộc ngẫu nhiên vào bean được auto-configure.** Trong ứng dụng cần kiểm soát tải, hãy định nghĩa executor và chọn rõ bằng `@Async("eventExecutor")`:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("event-");
        return executor;
    }
}
```

Đây là phần cấu hình độc lập theo mẫu (cần import `Configuration`, `EnableAsync`, `Bean`, `ThreadPoolTaskExecutor`); ví dụ runnable đầy đủ ở mục 3.

Các thông số chính:

- `corePoolSize`: số thread cốt lõi.
- `maxPoolSize`: giới hạn thread tối đa; với `ThreadPoolTaskExecutor`, mức độ sử dụng `maxPoolSize` phụ thuộc kích thước/hành vi queue.
- `queueCapacity`: số tác vụ có thể chờ; đặt quá lớn có thể tích tụ độ trễ và bộ nhớ.
- `threadNamePrefix`: hỗ trợ phân biệt thread xử lý event trong log và khi debug.
- Rejection policy, shutdown và timeout: phải được thiết kế cho trường hợp hệ thống quá tải hoặc đóng ứng dụng.

`SimpleAsyncTaskExecutor` không tương đương một thread pool có queue hữu hạn và policy rõ ràng. Khi cần kiểm soát tải production, ưu tiên executor được quản lý với giới hạn, metric, chính sách từ chối và xử lý lỗi.

`@Async("eventExecutor")` là tên/qualifier của executor bean. Có thể dùng nhiều executor cho nhóm tác vụ khác nhau (ví dụ email, indexing), nhưng đừng tạo pool vô hạn hoặc nhân đôi executor không cần thiết.

## 6. `@Async @EventListener` khác với executor ở `SimpleApplicationEventMulticaster`

Có **hai cơ chế độc lập** để thay đổi cách listener được gọi:

**Cách A: Bất đồng bộ ở từng listener bằng proxy method**

```java
@EventListener
@Async("eventExecutor")
public void onOrderCreated(OrderCreated event) {
    // Phương thức listener cụ thể được @Async interceptor xử lý.
}
```

Cần `@EnableAsync`. Một số listener vẫn đồng bộ, chỉ listener có `@Async` chuyển sang executor. Đoạn code là minh họa, `OrderCreated` do ứng dụng định nghĩa.

**Cách B: Bất đồng bộ tại multicaster**

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
```

Đây là đoạn cấu hình minh họa, cần import `Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `ThreadPoolTaskExecutor`. Bean phải có **tên chính xác** `applicationEventMulticaster` để Spring context dùng thay multicaster mặc định. Cấu hình executor ở multicaster không đòi hỏi mỗi method phải có `@Async`, và nó không được điều khiển bởi `@EnableAsync`. Trong Spring 6.1+, `ApplicationListener.supportsAsyncExecution()` cho phép một số listener yêu cầu chạy trên thread publisher; do đó **không phải mọi listener** đều được chuyển qua pool.

Không nên bật cả executor ở multicaster lẫn `@Async` trên mọi listener một cách máy móc: có thể xảy ra thêm bước handoff giữa thread pool, làm khó theo dõi latency, trace và vòng đời tác vụ. Cân nhắc chọn một cơ chế chủ đạo theo phạm vi muốn áp dụng.

| Tiêu chí | `@Async @EventListener` | Multicaster gắn `TaskExecutor` |
| --- | --- | --- |
| Phạm vi | Theo từng phương thức được annotate và proxy được áp dụng | Theo cơ chế dispatch của multicaster, có xét khả năng hỗ trợ async của listener |
| Điều kiện chính | `@EnableAsync`, Spring-managed bean, lời gọi đi qua async proxy | Multicaster custom có executor và listener cho phép async dispatch |
| Quy tắc self-invocation | Phải lưu ý; lời gọi trực tiếp trong cùng bean bỏ qua proxy | Không phụ thuộc `@Async` proxy khi multicaster tự đưa listener lên executor |
| Transaction context | Không tự truyền sang worker thread | Không tự truyền sang worker thread |
| Theo dõi lỗi | Theo cơ chế `@Async`, handler/future | Theo executor và `ErrorHandler` của multicaster |

## 7. Transaction và ngữ cảnh thread: lỗi thường gặp khi xử lý event nền

Giả sử service có `@Transactional` phát một sự kiện ngay sau `repository.save(order)`:

```java
@Transactional
public void placeOrder(Order order) {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
```

Nếu listener là `@Async @EventListener`, nó có thể bắt đầu xử lý **trước khi transaction của publisher commit**. Vì chạy trên thread khác:

- Transaction JDBC/JPA gắn thread của publisher không tự truyền sang thread xử lý event.
- Truy vấn bằng connection khác có thể chưa nhìn thấy bản ghi chưa commit; tùy isolation, có thể thấy dữ liệu cũ.
- Listener async ném lỗi không tự rollback transaction của publisher; producer có thể đã commit hoặc chưa commit.
- `SecurityContext`, MDC, `RequestContextHolder` và `ThreadLocal` khác không tự được truyền theo. Nếu cần, dùng `TaskDecorator`/cơ chế context propagation có phạm vi kiểm soát.
- Không chuyển thẳng entity JPA còn lazy-loading/session-bound sang async listener rồi giả định nó luôn truy cập được dữ liệu.

Nếu công việc chỉ được chạy **sau khi commit** thành công, cân nhắc:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommitted(OrderPlaced event) {
    // Việc xử lý sẽ được gọi theo pha AFTER_COMMIT,
    // sau đó @Async có thể đưa thực thi sang executor.
}
```

Đây là đoạn minh họa trong Spring-managed bean; cần `@EnableAsync`, `@Async`, `@TransactionalEventListener`, `TransactionPhase`. Với sự kiện phát trong transaction imperative, `@TransactionalEventListener` đăng ký callback giao dịch; mặc định listener không chạy nếu không có transaction (trừ khi cấu hình `fallbackExecution = true`). Khi cần ghi DB từ thread async, hãy mở transaction riêng nếu nghiệp vụ yêu cầu, ví dụ gọi một service khác có `@Transactional`, thay vì dựa vào transaction đã commit của publisher.

**Sau commit chưa có nghĩa là đảm bảo giao hàng:** sự kiện vẫn nằm trong bộ nhớ; process chết giữa commit và xử lý async có thể làm mất tác vụ. Nghiệp vụ yêu cầu giao hàng chắc chắn cần transactional outbox, broker bền vững, idempotency và retry.

## 8. Giá trị trả về, exception và giám sát lỗi

Phương thức `@Async` thông thường hỗ trợ `void`, `Future<T>` hoặc `CompletableFuture<T>` theo quy tắc async của Spring. Với `@Async @EventListener`, thường dùng **`void`**, vì cơ chế event listener bất đồng bộ **không hỗ trợ tự phát một event tiếp theo bằng giá trị trả về** như listener đồng bộ. Nếu muốn phát event tiếp theo, inject `ApplicationEventPublisher` và chủ động gọi `publishEvent(...)` trong xử lý async.

Đối với method async trả `void`, ngoại lệ không quay trở lại trực tiếp caller đã phát event; có thể cấu hình `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
class AsyncErrorConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) ->
                System.err.println(
                        "Async failed in " + method.getName() + ": " + error);
    }
}
```

Đây là đoạn cấu hình minh họa; cần import `Configuration`, `EnableAsync`, `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`. Handler ví dụ in lỗi, nhưng production nên có log cấu trúc, metrics, alerting và chính sách xử lý nghiệp vụ. Khi async method trả `Future`/`CompletableFuture`, caller có thể quan sát thất bại qua kết quả bất đồng bộ phù hợp. Với `@EventListener` void, publisher không nhận lại kết quả xử lý.

Nếu `Executor` từ chối việc submit tác vụ, lỗi có thể xuất hiện **ngay lúc gọi proxy/dispatch**, khác với lỗi bên trong method chạy trên worker thread. Cần kiểm thử riêng cả hai loại lỗi; việc một lần `publishEvent()` trả về không phải bằng chứng mọi tác vụ đã được xử lý thành công.

`@Order` hoặc thứ tự đăng ký event listener chỉ có thể ảnh hưởng thứ tự dispatch/submit phù hợp. Trong executor chạy nhiều thread, thứ tự tác vụ **hoàn tất** không được bảo đảm, và không nên dùng side effect phụ thuộc vào thứ tự đó trừ khi có thiết kế tuần tự hóa riêng.

## 9. Kiểm thử `@EnableAsync` và proxy method đúng cách

Các tình huống kiểm thử nên có:

1. **Bật/tắt hạ tầng:** với `@EnableAsync` trong context, gọi method `@Async` qua bean proxy và xác nhận tác vụ chạy trên thread mong đợi; thiếu enablement thì không nên mặc định kỳ vọng bất đồng bộ.
2. **External vs self-invocation:** dùng hai đường gọi trong ví dụ mục 3 để phát hiện lỗi `this.asyncMethod()`.
3. **Event listener:** phát object bằng `publishEvent(...)`, chờ latch/future của listener rồi kiểm tra kết quả. Không dùng `Thread.sleep(50)` để đoán tác vụ xong.
4. **Lỗi trong tác vụ:** cho listener ném exception, kiểm tra handler/log/future; xác minh lỗi không vô tình bị xem là thành công.
5. **Quá tải executor:** đặt queue/pool nhỏ trong test riêng, submit nhiều tác vụ có thể chặn có kiểm soát và xác nhận chính sách rejection.
6. **Ranh giới transaction:** phát event trong một transaction chưa commit; xác nhận listener async không phụ thuộc vào dữ liệu chưa commit, đồng thời kiểm tra AFTER_COMMIT nếu dùng listener gắn transaction.
7. **Shutdown:** xác nhận tác vụ đang chạy được xử lý hoặc hủy có chủ đích trong giới hạn thời gian mong muốn.

Hãy dùng các điều kiện quan sát ổn định như `CountDownLatch`, `CompletableFuture`, Awaitility, các giá trị thread hoặc trạng thái DB. Tên thread `"event-"` trong ví dụ chỉ để dễ kiểm tra, không phải hợp đồng chung của Spring.

## 10. Các lỗi cấu hình và cách xử lý nhanh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Có `@Async` nhưng vẫn chạy trên caller thread | Chưa bật `@EnableAsync`, không có Spring proxy hoặc self-invocation | Bật đúng context, lấy bean từ Spring, tách method async sang bean riêng |
| `@Async` chạy khi gọi từ controller nhưng không chạy khi gọi nội bộ | `this.method()` bỏ qua proxy | Gọi sang bean khác hoặc chọn cơ chế interception có chủ đích |
| Không tìm thấy bean theo implementation class | Proxy JDK chỉ expose interface | Inject theo interface hoặc cấu hình class proxy phù hợp |
| `@Async` trên `private`/`final` không có tác dụng | Proxy không thể intercept/override | Đưa method công khai, có thể proxy sang service bean phù hợp |
| Listener async không đọc được dữ liệu vừa lưu | Publisher chưa commit; transaction/context không truyền | Dùng AFTER_COMMIT, truyền ID và mở transaction riêng khi cần |
| Mất log/trace, security context trong thread mới | Context gắn thread chưa được truyền | Cấu hình propagation có kiểm soát, tránh sao chép bừa toàn bộ trạng thái |
| Exception không xuất hiện ở caller | Lỗi chạy trên worker thread | Dùng `AsyncUncaughtExceptionHandler`, result future, log/metrics |
| Thứ tự event không ổn định | Thread pool chạy song song | Thiết kế idempotent; nếu cần tuần tự, dùng hàng đợi/partition/order chuyên dụng |
| Pool ngừng nhận tác vụ | Queue đầy, executor đã shutdown | Theo dõi saturation/rejection, quy hoạch capacity và shutdown |
| `@Async` trên listener không phát event từ return value | Giới hạn của async event listener | Gọi `ApplicationEventPublisher.publishEvent(...)` rõ ràng |

## 11. Hướng chọn thiết kế

Dùng `@EnableAsync` + `@Async` khi chỉ **một số** tác vụ hoặc event listener cần chạy nền và bạn muốn kiểm soát riêng executor của chúng. Dùng executor trong `ApplicationEventMulticaster` khi muốn chiến lược dispatch mang tính tập trung, nhưng phải tôn trọng listener không hỗ trợ async. Dùng `@TransactionalEventListener(AFTER_COMMIT)` cho yêu cầu chạy sau commit; bổ sung `@Async` khi thật sự cần xử lý trên thread khác. Khi tính bền vững và giao nhận là yêu cầu nghiệp vụ, hãy dùng outbox/broker thay vì dựa hoàn toàn vào một lời gọi async trong bộ nhớ.

Nguyên tắc để kiểm tra code khi review: **Ai gọi method? Lời gọi có đi qua Spring bean proxy không? Executor nào thực thi? Transaction đã commit chưa? Ngoại lệ được báo ở đâu?** Trả lời rõ năm câu này sẽ loại bỏ phần lớn lỗi do hiểu sai `@EnableAsync` và proxy.

Tài liệu chính thức:

- [Spring Framework — Task Execution and Scheduling, `@Async`, executor và exception](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ApplicationContext Events, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — AOP proxying and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
