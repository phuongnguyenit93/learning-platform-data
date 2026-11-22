# Lỗi trong async listener của Spring Application Events: cơ chế, rollback và xử lý an toàn

## 1. Vì sao lỗi trong async listener là một vấn đề riêng?

Spring Application Events giúp một thành phần publish sự kiện và những listener quan tâm phản ứng với sự kiện ấy. Với cách dispatch đồng bộ thông thường, publisher gọi `publishEvent(...)` và listener xử lý trên cùng luồng thực thi. Khi một listener ném exception chưa được xử lý, exception đó có thể truyền về publisher. Nếu publisher nằm trong transaction phù hợp, lỗi có thể ảnh hưởng đến quyết định commit hoặc rollback.

Khi listener chạy **bất đồng bộ** bằng `@Async` hoặc một executor được cấu hình cho multicaster, quan hệ đó thay đổi: publisher có thể trả về **trước khi** công việc listener kết thúc. Một lỗi phát sinh về sau trong worker không còn mặc nhiên ném ngược vào stack của caller. Một hệ thống chỉ thử `try/catch` quanh `publishEvent(...)` rất dễ tưởng đã bắt mọi lỗi, trong khi tác vụ listener đã thất bại ở thread khác.

Ví dụ nghiệp vụ:

~~~text
OrderService.placeOrder()
        |
        | lưu đơn trong transaction
        | publish(OrderPlaced)
        v
  Async notification listener ------------> Email provider
        |                                       |
        | trả quyền điều khiển                   +-- timeout / 503
        v
  OrderService có thể đã trả về
  và transaction có thể đã commit
~~~

Nếu gửi email chỉ là tác vụ phụ, việc không rollback đơn hàng có thể là mong muốn. Nhưng nếu email là kết quả cần giao chắc chắn, chỉ gắn `@Async` rồi bỏ qua exception là **thiếu một cơ chế khôi phục**. Cần phân biệt lỗi khởi chạy, lỗi thực thi, rollback, retry và độ bền của thông điệp.

**Mục tiêu của bài:** xác định chính xác lỗi nào xuất hiện ở đâu; chọn `AsyncUncaughtExceptionHandler`, multicaster `ErrorHandler` hoặc giám sát `Future` phù hợp; hiểu vì sao exception async không tự rollback publisher; và thiết kế retry/outbox/idempotency cho công việc không được phép thất lạc.

## 2. Ba khái niệm phải tách bạch

### 2.1. Publish không đồng nghĩa hoàn tất

`ApplicationEventPublisher.publishEvent(Object)` gửi event vào cơ chế dispatch của `ApplicationContext`. Nó không phải API xác nhận tác vụ nghiệp vụ đã hoàn tất, càng không phải một cam kết lưu event bền vững. Việc lời gọi publish trả về **không đủ** để kết luận listener async đã thành công.

### 2.2. @Async khác với multicaster có TaskExecutor

Có hai cách thường gặp để xử lý event ngoài thread phát:

1. **`@Async` trên phương thức `@EventListener`:** annotation-driven async support tạo proxy và đưa lời gọi phương thức sang executor được chọn. Với phương thức `void`, lỗi trong phần thân được xử lý qua cơ chế exception của Spring async.
2. **`SimpleApplicationEventMulticaster.setTaskExecutor(...)`:** multicaster có thể tự giao việc gọi listener cho executor. Khi đó đường xử lý lỗi gắn với multicaster, executor và `ErrorHandler` của multicaster. Không phải mọi listener đều được phép chạy async theo cách này; một số listener yêu cầu chạy trên publisher thread.

Hai cơ chế có thể cùng tồn tại, nhưng điều đó làm ranh giới thread và lỗi phức tạp hơn. Đừng cấu hình đồng thời cả hai chỉ vì nghĩ rằng “async hai lần thì nhanh hơn”.

### 2.3. Exception trong worker khác exception khi đưa task vào queue

Phân biệt:

- **Lỗi trước/sát thời điểm publish:** ví dụ code tạo event ném lỗi; lỗi này xảy ra ngay ở publisher.
- **Lỗi khi submit task:** executor đang shutdown hoặc queue đầy; `TaskRejectedException`/`RejectedExecutionException` có thể xuất hiện ở đường lên lịch, tùy executor và cách cấu hình. Một số implementation có chiến lược fallback khi từ chối task; không được giả định mọi rejection luôn được ném theo cùng cách.
- **Lỗi trong thân listener đã được chạy:** ví dụ email gateway trả 503; với `@Async void`, lỗi này không tự trở về `try/catch` quanh publish.
- **Lỗi hậu xử lý/ghi nhận lỗi:** ngay cả error handler cũng có thể gặp lỗi. Do đó chỉ log exception chưa đồng nghĩa công việc đã được phục hồi.

Một bảng so sánh:

| Đường chạy | Exception trong thân handler | Tác động thường thấy lên publisher |
| --- | --- | --- |
| Listener đồng bộ, không có `ErrorHandler` nuốt lỗi | Có thể propagate qua multicaster | Caller có thể bắt được; transaction có thể rollback theo rule |
| Listener `@Async void`, task thực sự được chạy | `AsyncUncaughtExceptionHandler` xử lý exception không bắt trong phương thức | Publisher thường đã trả về; không nhận cùng exception |
| Listener chạy nhờ executor của multicaster | Exception thuộc task/executor hoặc được multicaster `ErrorHandler` xử lý | Thường không propagate từ worker về publisher |
| Submit task thất bại trước khi task chạy | Theo chính sách executor/implementation | Có thể xuất hiện ngay khi publish hoặc được fallback |
| Listener đồng bộ có `ErrorHandler` suppress exception | Handler có thể log và không ném lại | Publisher có thể không thấy lỗi dù listener thất bại |

**Từ “thường” là có chủ đích:** một executor có thể dùng `CallerRunsPolicy` hoặc một multicaster có fallback; đó không còn là cùng hành vi với giao task thành công sang thread khác.

## 3. @Async @EventListener thực sự hoạt động thế nào?

Cấu hình tối thiểu trong ứng dụng Spring cần có bean listener, bật hỗ trợ async và một executor rõ ràng:

~~~java
@Configuration
@EnableAsync
public class EventsConfiguration {
    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.initialize();
        return executor;
    }
}
~~~

Ví dụ trên là **mảnh cấu hình trong một ứng dụng Spring**, không phải tệp Java độc lập; cần import `Configuration`, `EnableAsync`, `Bean` và `ThreadPoolTaskExecutor`. Tên `eventExecutor` dùng cùng `@Async("eventExecutor")`.

~~~java
@Component
public class EmailListener {
    @Async("eventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        emailService.sendOrderConfirmation(event.orderId());
    }
}
~~~

Đây cũng là **mã minh họa**: ứng dụng cần định nghĩa `OrderPlaced`, `emailService`, các import và cấu hình DI. Khi proxy async hoạt động đúng, phần thân `onOrderPlaced` chạy trên executor và publisher không đợi kết quả.

### Điều kiện để @Async được áp dụng đúng

- Có `@EnableAsync` hoặc cấu hình tương đương.
- Phương thức listener được Spring đăng ký trên bean do container quản lý; tự gọi `new EmailListener()` rồi không đăng ký bean sẽ không kích hoạt cơ chế listener.
- Cấu hình proxy phải cho phép intercept phương thức; tránh lớp/phương thức `final` ngăn tạo proxy subclass, private method hoặc những cấu hình không tương thích với proxy.
- Tên executor `eventExecutor` phải khớp bean được sử dụng.
- Khi một phương thức async được gọi **nội bộ từ phương thức khác trên cùng object** bằng `this.someAsyncMethod()`, self-invocation thông thường không đi qua Spring proxy. `@EventListener` được Spring dispatch qua bean listener, nhưng các lời gọi self-invocation khác vẫn cần chú ý.
- Nếu listener đồng thời cần `@Transactional`, nên tách service transaction và kiểm tra thứ tự interceptor, thread và transaction thật.

**Không dùng tên thread như chứng minh duy nhất của async.** Thread name giúp debug nhưng tính đúng phải được kiểm chứng bằng hành vi, executor và test.

## 4. Xử lý exception của @Async void

Với một phương thức `@Async` trả về `void`, caller không có `Future` để đọc lỗi. Spring cung cấp giao diện `AsyncUncaughtExceptionHandler`:

~~~java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
        Throwable ex,
        Method method,
        Object... params
    );
}
~~~

Đây là chữ ký chính, không phải một định nghĩa interface đầy đủ để copy nguyên văn. Handler nhận:

- `ex`: exception hoặc throwable từ thân async method.
- `method`: thông tin method bị lỗi.
- `params`: tham số lời gọi, cần cẩn thận vì có thể chứa dữ liệu nhạy cảm.

Có thể cung cấp handler qua `AsyncConfigurer#getAsyncUncaughtExceptionHandler()`. Nếu không tự cung cấp handler, Spring có cơ chế mặc định để ghi nhận lỗi theo cấu hình logging; **đừng phụ thuộc chỉ vào log mặc định như một chính sách retry**.

Ví dụ handler trong dự án:

~~~java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (ex, method, params) -> {
        logger.error(
            "Async listener failed at {}",
            method.getName(), ex
        );
        metrics.counter("event_listener_failure").increment();
    };
}
~~~

Đoạn này là **mã minh họa**; `logger`, `metrics` cần được cấu hình. Handler ở đây quan sát lỗi nhưng **chưa tự retry, chưa đánh dấu task thất bại trong dữ liệu bền vững và chưa chuyển lỗi về publisher**.

Nếu tác vụ có ý nghĩa nghiệp vụ quan trọng, thiết kế thêm retry, dead-letter, status tracking hoặc một hệ thống delivery bền vững thay vì mặc định “handler đã log = lỗi được xử lý”.

## 5. Ví dụ Java 17+ đầy đủ: lỗi async được bắt ở worker, không ở publisher

Ví dụ sử dụng Java 17+, Maven và Spring Framework **6.2.8**. Nó không cần Spring Boot, database hoặc email provider thật.

Ý tưởng:

1. Main publish `OrderPlaced`.
2. Listener `@Async` được giao cho `ThreadPoolTaskExecutor`.
3. Listener chờ `CountDownLatch` để main kịp in `PUBLISH_RETURNED`, giúp output xác định.
4. Main mở latch; listener in `LISTENER...` rồi cố ý ném `IllegalStateException`.
5. Custom `AsyncUncaughtExceptionHandler` in lỗi và đánh dấu hoàn tất.
6. Main quan sát handler hoàn tất và in `MAIN_CONTINUES`, không nhận exception đó bằng `try/catch` của publisher.

### 5.1. Cấu trúc thư mục

~~~text
async-event-failure-demo/
├── pom.xml
└── src/main/java/AsyncEventFailureDemo.java
~~~

### 5.2. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-failure-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>AsyncEventFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. Tệp src/main/java/AsyncEventFailureDemo.java

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventFailureDemo {

    // Hai latch giúp xác nhận đúng thứ tự mà không dùng Thread.sleep.
    private static final CountDownLatch ALLOW_WORKER =
        new CountDownLatch(1);
    private static final CountDownLatch ERROR_HANDLED =
        new CountDownLatch(1);

    public record OrderPlaced(long orderId) { }

    // Không dùng final cho class listener để proxy có thể intercept.
    public static class FailingListener {

        @Async("eventsExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                if (!ALLOW_WORKER.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("gate timeout");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", ex);
            }

            System.out.println(
                "LISTENER order=" + event.orderId()
            );

            // Giả lập lỗi xảy ra SAU khi task đã thực sự chạy.
            throw new IllegalStateException("mail service down");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config implements AsyncConfigurer {

        @Bean("eventsExecutor")
        ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.initialize();
            return executor;
        }

        @Bean
        FailingListener failingListener() {
            return new FailingListener();
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                System.out.println(
                    "ASYNC_ERROR "
                    + ex.getClass().getSimpleName()
                    + " " + ex.getMessage()
                    + " method=" + method.getName()
                );
                ERROR_HANDLED.countDown();
            };
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("PUBLISH");
            context.publishEvent(new OrderPlaced(42L));
            System.out.println("PUBLISH_RETURNED");

            // Mở cổng sau khi publish đã trả về.
            ALLOW_WORKER.countDown();

            if (!ERROR_HANDLED.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Async error was not observed"
                );
            }
            System.out.println("MAIN_CONTINUES");
        }
    }
}
~~~

Chạy tại thư mục dự án với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do **chính chương trình** in ra, theo thứ tự dưới cấu hình ví dụ:

~~~text
PUBLISH
PUBLISH_RETURNED
LISTENER order=42
ASYNC_ERROR IllegalStateException mail service down method=onOrderPlaced
MAIN_CONTINUES
~~~

### 5.4. Phân tích từng dòng

- `PUBLISH`: main chuẩn bị phát event.
- `PUBLISH_RETURNED`: cuộc gọi `publishEvent` trả về sau khi việc lên lịch thành công. Listener có thể đã vào worker nhưng bị chặn ở `ALLOW_WORKER.await(...)` nên chưa thể in log hoặc ném lỗi.
- `LISTENER order=42`: sau khi main mở latch, worker xử lý nội dung.
- `ASYNC_ERROR ...`: `IllegalStateException` từ thân `@Async void` được chuyển đến custom `AsyncUncaughtExceptionHandler`. Handler in tên method và signal `ERROR_HANDLED`.
- `MAIN_CONTINUES`: main chờ **signal do ví dụ tự thiết kế**, không phải exception tự được truyền về. Chính latch khiến chúng ta biết lỗi đã được ghi nhận trước khi thoát chương trình.

**Giới hạn của ví dụ:** không có transaction, không gửi email thật và không chứng minh event được giao bền vững. `CountDownLatch` chỉ phục vụ kiểm thử thứ tự, không phải một cơ chế retry để dùng trực tiếp trong production. Nếu executor từ chối task ở thời điểm submit, chương trình có thể đi vào đường lỗi khác trước khi đạt output trên; ví dụ giả định executor bình thường được khởi tạo và có chỗ nhận task.

Không nên viết `Thread.sleep(100)` rồi kết luận lỗi đã được xử lý. Với test async, dùng latch, future, queue trạng thái hoặc kiểm chứng một outcome có timeout.

## 6. Exception handler nào xử lý loại lỗi nào?

### 6.1. AsyncUncaughtExceptionHandler

Dành cho exception không bắt được từ lời gọi `@Async` có kiểu trả về `void`. Khi proxy async nhận task thành công, thân method chạy ngoài publisher thread và exception được xử lý bởi đường async invocation.

Nó có thể log, phát metric, gửi alert hoặc ghi nhận trạng thái thất bại. Nhưng tự nó không “ném lại cho bên gọi” và không tự rollback publisher.

### 6.2. SimpleApplicationEventMulticaster.setErrorHandler

Nếu sử dụng multicaster trực tiếp, có thể cấu hình `ErrorHandler`:

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(ex -> {
        // Log/metrics; quyết định suppress hay propagate.
        System.err.println("EVENT_ERROR: " + ex);
    });
    return multicaster;
}
~~~

Đây là ví dụ cấu hình **minh họa** cần import `Bean` và `SimpleApplicationEventMulticaster`. Đặt tên bean đặc biệt `applicationEventMulticaster` thay thế multicaster dùng bởi context trong cấu hình phù hợp.

`ErrorHandler` bao quanh việc **multicaster gọi listener**. Nếu listener được multicaster thực thi đồng bộ, handler có thể suppress hoặc rethrow tùy logic. Nếu multicaster dùng executor, một exception trong worker có thể được handler này ghi nhận tại worker. Tuy nhiên, khi listener method là proxy `@Async` đã lên lịch một công việc `void`, lỗi phát sinh sau đó có thể đã được `AsyncUncaughtExceptionHandler` xử lý **bên trong proxy**, không truyền trở lại multicaster. Khi đó chỉ thêm `setErrorHandler` không thay thế custom async handler.

Một điểm nữa: trong Spring 6.1+, `ApplicationListener.supportsAsyncExecution()` có thể khiến một số listener như transaction-synchronized listener **không được multicaster chuyển sang executor**. Không xem một global executor như cam kết mọi listener đều chạy async.

### 6.3. Nếu muốn thu kết quả và exception bằng Future

Spring `@Async` trên một **service method** có thể trả về `CompletableFuture<T>`. Bên gọi nhận future và quan sát exception qua `join()`, `get()` hoặc `whenComplete(...)`:

~~~java
// Phác thảo: một service được Spring proxy bằng @Async.
@Async("eventsExecutor")
public CompletableFuture<Void> sendEmail(long orderId) {
    emailClient.send(orderId);
    return CompletableFuture.completedFuture(null);
}
~~~

Bên điều phối có thể theo dõi:

~~~java
CompletableFuture<Void> future = emailService.sendEmail(42L);
future.whenComplete((value, error) -> {
    if (error != null) {
        // Ghi nhận lỗi, retry hoặc chuyển trạng thái thất bại.
    }
});
~~~

Hai đoạn trên là mã minh họa trong ứng dụng có `emailClient`, `emailService` và import thích hợp. **Không mặc định đổi phương thức `@EventListener @Async` sang trả về `CompletableFuture` để coi đó là kết quả publish được Spring trả cho caller**: event dispatch không cung cấp API tổng hợp future của tất cả listener. Nếu cần outcome rõ, một orchestration/service async có hợp đồng future hoặc job trạng thái thường dễ kiểm soát hơn.

## 7. Rollback: exception async ảnh hưởng transaction nào?

Đây là khác biệt quan trọng nhất giữa lỗi đồng bộ và bất đồng bộ.

### 7.1. Listener đồng bộ trong cùng transaction

Ví dụ một use case:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    orderRepository.save(createEntity(command));
    publisher.publishEvent(new OrderCreated(command.id()));
}
~~~

Đây là mã phác thảo, cần repository, model và cấu hình transaction. Nếu listener đồng bộ tham gia cùng transaction trên thread này và ném `RuntimeException` không được xử lý, exception có thể truyền ngược, khiến transaction bị đánh dấu rollback theo rule.

Nhưng điều đó **không đúng cho mọi listener**: `@Transactional(propagation = REQUIRES_NEW)`, remote service, executor và exception handler có thể thay đổi ranh giới.

### 7.2. Listener async chạy ở thread khác

Với `@Async`, phần thân listener thường chạy trên một thread khác, **không kế thừa thread-bound imperative transaction** của publisher. Nếu publisher đã commit hoặc đang commit, lỗi email trong worker không thể tự rollback transaction nguồn.

~~~text
Publisher thread (T1)                 Worker thread (không có T1)
-------------------------             --------------------------
BEGIN T1
save order
publish(OrderCreated)
  -> schedule async task ------------> await executor
COMMIT T1                             send email -> failure
return                                async exception handler logs
~~~

Đừng nhầm “publisher và listener chạy trong cùng JVM” với “chúng có cùng transaction”. Giao dịch JDBC/JPA gắn với tài nguyên và thread/context quản lý; Spring không tự chuyển một transaction imperative đang mở sang executor.

### 7.3. @Transactional trên async worker

Một listener hoặc service chạy trên worker có thể có `@Transactional` và transaction manager riêng được cấu hình đúng. Khi được gọi qua proxy trong worker, nó có thể mở **transaction mới** cho những thao tác DB của chính worker.

Ví dụ ý tưởng:

~~~java
@Service
public class ProjectionWriter {

    @Transactional
    public void updateFor(OrderCreated event) {
        // Ghi projection trong transaction của worker.
        // Không chia sẻ transaction T1 của publisher.
    }
}
~~~

Listener `@Async` có thể gọi `projectionWriter.updateFor(event)` qua bean proxy. Transaction của projection có thể rollback khi xử lý projection lỗi, **nhưng không rollback order đã commit trước đó**. Tách service như vậy giúp tránh self-invocation và thứ tự interceptor khó kiểm chứng.

### 7.4. @TransactionalEventListener và @Async

`@TransactionalEventListener` cho phép gắn công việc với một phase của transaction, thường là `AFTER_COMMIT`. Khi kết hợp:

~~~java
@Async("eventsExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderCreated event) {
    notificationService.send(event);
}
~~~

Đây là mã minh họa đặt trong bean Spring, cần import, executor, `OrderCreated` và `notificationService`. **Transaction synchronization được đăng ký theo event/transaction ở publisher context**, còn thân method có thể được giao sang executor **sau khi transaction commit**. Vì thế:

- Nếu transaction nguồn rollback, listener phase `AFTER_COMMIT` không chạy.
- Nếu có commit, listener được phép bắt đầu; exception worker **không làm commit đã xảy ra trở thành rollback**.
- Nếu publish ngoài transaction, listener mặc định **không chạy**, trừ khi sử dụng `fallbackExecution=true` với chủ ý rõ.
- Nếu worker cần ghi database, dùng transaction riêng; không coi resource của transaction nguồn còn là transaction để commit thêm.
- Nếu process chết giữa commit và task hoàn tất, công việc vẫn có thể bị mất.

**Sau commit ≠ giao tin cậy.** Khi notification hoặc tích hợp ngoài không được mất, cần lưu công việc bền vững.

## 8. Đường lỗi khi executor quá tải hoặc shutdown

Một async listener có thể thất bại **trước khi thân phương thức bắt đầu**. Ví dụ:

- Thread pool đã đạt giới hạn, queue đầy.
- Executor đang shutdown.
- Cấu hình tên executor không tìm thấy bean phù hợp.
- Proxy/annotation async cấu hình sai khiến lời gọi không chạy như dự kiến.
- Task bị hủy hoặc bị timeout theo một policy bên ngoài.

Trong một số executor, submit thất bại sẽ ném `TaskRejectedException` hoặc `RejectedExecutionException` tại đường gọi; với một số multicaster/handler, có thể có fallback hoặc logging thay vì cùng một cách ném exception. Vì vậy **đừng dựa vào một kỳ vọng chung rằng mọi rejection sẽ vào `AsyncUncaughtExceptionHandler`**: handler này dành cho exception trong phương thức `@Async void` đã được thực thi, không phải một API bao trùm mọi lỗi scheduling.

### Ví dụ chính sách executor

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setThreadNamePrefix("event-");
executor.initialize();
~~~

Đây là mã minh họa cấu hình, không phải một công thức capacity tối ưu cho mọi ứng dụng. Cần đo tải thực tế, thời gian gọi downstream, độ lớn burst và giới hạn tài nguyên.

Với job không được phép mất, queue **trong RAM** của executor cũng không bền vững qua process crash. Nếu cần backpressure, retry có lịch hoặc phục hồi sau restart, cân nhắc message broker/outbox/job storage và consumer có chính sách idempotency.

### Tác động của shutdown

`ContextClosedEvent` xảy ra trong quá trình context đóng. Khi đó, executor và các dependency có thể cũng đang dừng. Đừng lập kế hoạch “cứ publish một async event lúc close rồi chắc chắn flush hết dữ liệu” trừ khi có chính sách shutdown được kiểm thử. Những hành động dọn dẹp bắt buộc nên đặt ở lifecycle bean thích hợp như `SmartLifecycle` hoặc `@PreDestroy`, có timeout và thứ tự rõ ràng.

## 9. Retry, idempotency và trạng thái thất bại

Nếu async listener gọi dịch vụ bên ngoài thất bại, cách khôi phục phụ thuộc bản chất công việc:

| Công việc | Chính sách thường hợp lý |
| --- | --- |
| Log chẩn đoán phụ, không bắt buộc | Ghi lỗi/metrics, có thể bỏ qua |
| Cập nhật read model có thể rebuild | Retry có kiểm soát, idempotency, khả năng rebuild |
| Gửi email xác nhận | Bền vững hóa ý định gửi, retry và chống gửi trùng |
| Cập nhật thanh toán/kho | Command và trạng thái workflow, dedup, compensation khi cần |
| Audit bắt buộc không được mất | Ghi audit/outbox trong transaction hoặc lưu trữ bền vững |

Không nên thực hiện retry vô hạn trong `while(true)` của listener: nó giữ thread pool, có thể làm nghẽn mọi event khác. Thay vào đó, chọn giới hạn attempt, backoff, jitter, phân loại lỗi transient/permanent, dead-letter/quarantine và giám sát.

### 9.1. Tại sao retry cần idempotency?

Giả sử worker gọi email provider thành công nhưng timeout trước khi nhận response. Handler ghi “failure” rồi retry; khách có thể nhận **hai email**. Một database check theo event ID, provider idempotency key hoặc trạng thái công việc có thể giảm trùng, nhưng phải thiết kế atomicity/khả năng retry phù hợp.

Thông tin nên có trong event/job:

- `eventId` hoặc `jobId` ổn định cho cùng một fact/công việc.
- `aggregateId` hoặc business key.
- `correlationId`/`causationId` để truy lỗi xuyên các bước.
- `attempt` và thời điểm retry; không đổi event ID mỗi lần giao lại cùng fact.
- Mã loại lỗi và trạng thái xử lý không làm lộ dữ liệu nhạy cảm.

Một `Set<UUID>` trong singleton chỉ chống trùng trong một JVM còn sống; không đủ khi nhiều pod, restart hoặc outbox dispatcher chạy song song.

### 9.2. Transactional outbox

Khi event cần được giao đi ngay cả khi process chết, **transactional outbox** là một mô hình phổ biến:

~~~text
T1 BEGIN
  INSERT order
  INSERT outbox(eventId, type=OrderCreated, payload, state=PENDING)
T1 COMMIT
             |
             v
Outbox dispatcher -> broker / worker
                     retry, backoff, dedup
~~~

Order và bản ghi outbox cùng commit hoặc cùng rollback. Dispatcher đọc bản ghi đã commit, gửi và cập nhật trạng thái. Consumer idempotent vì giao lại có thể xảy ra. Outbox giải quyết **cửa sổ mất việc giữa database commit và phát thông điệp**, nhưng không tạo “exactly once end-to-end” một cách tự động.

Listener `@Async` thuần túy là cơ chế chạy công việc trên executor, không thay thế outbox, message broker hoặc hệ thống job bền vững.

## 10. Bắt lỗi ở đâu để không che mất tín hiệu thất bại?

Một listener có thể bắt exception có chủ đích khi tự quyết định chính sách:

~~~java
@Async("eventsExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    try {
        externalClient.notify(event.orderId());
    } catch (TransientGatewayException ex) {
        retryQueue.enqueue(event.eventId());
        metrics.counter("notification_retry_queued").increment();
    }
}
~~~

Đây là đoạn **minh họa**, cần có `externalClient`, `retryQueue`, `metrics`, `TransientGatewayException` và `OrderCreated` trong hệ thống. Chỉ phù hợp nếu `retryQueue.enqueue(...)` thực sự đảm bảo công việc được lưu theo contract. Nếu queue cũng thất bại, cần xử lý/truyền lỗi để hệ thống biết việc giao công việc chưa hoàn tất.

Không nên viết:

~~~java
try {
    sendEmail();
} catch (Exception ignored) {
    // Im lặng: ứng dụng không biết công việc thất bại.
}
~~~

Một catch-all nuốt lỗi có thể làm log và metric báo thành công giả. Phân loại lỗi:

- **Lỗi tạm thời:** network timeout, 503, rate limit; có thể retry có giới hạn.
- **Lỗi nghiệp vụ cố định:** địa chỉ không hợp lệ, trạng thái không cho phép; có thể chuyển sang failed/quarantine.
- **Lỗi coding/configuration:** NPE, missing bean, mapping sai; thường cần alert và sửa phần mềm, không retry vô hạn.

Đừng dựa vào exception class một cách tuyệt đối; downstream API phải có mã lỗi/hợp đồng đủ rõ để quyết định khả năng retry.

## 11. Logs, metrics và tracing

Một async listener thất bại có thể nằm ngoài trace HTTP ban đầu, nên cần ghi nhận **quan hệ nhân quả**. Log có cấu trúc nên chứa:

- `eventType`, `eventId`, `aggregateId`.
- `correlationId`, `causationId` nếu workflow có nhiều bước.
- `listenerName`, `executorName`, `threadName`.
- `attempt`, `durationMs`, `status` (success/failure/retry_scheduled).
- `errorClass` và mã lỗi có kiểm soát.
- `traceId`/`spanId` nếu có distributed tracing đúng cách.

Ví dụ:

~~~text
event=OrderCreated id=e-42 corr=order-42 listener=EmailListener phase=async attempt=1 status=failed error=GATEWAY_TIMEOUT
event=OrderCreated id=e-42 corr=order-42 listener=EmailListener phase=retry attempt=2 status=scheduled
~~~

**Không đưa event ID/order ID làm label của metrics** như Prometheus counter vì tạo cardinality lớn. Tên metric tự định nghĩa có thể là `app_event_listener_failures_total{listener="email",error="timeout"}`, các giá trị label hữu hạn. ID chi tiết thuộc logs/traces.

MDC và ThreadLocal không tự đi theo mọi thread; dùng `TaskDecorator`, tracing context propagation hoặc truyền metadata trong event/job theo chính sách. Không truyền trực tiếp JPA persistence context, transaction hoặc thông tin bí mật sang executor.

## 12. Testing: kiểm chứng cả đường thành công và thất bại

Một bài test async đáng tin phải kiểm tra **kết quả cuối**, không chỉ việc `publishEvent(...)` không ném exception.

| Test case | Kỳ vọng |
| --- | --- |
| Event hợp lệ, listener thành công | Outcome được lưu/xác nhận; publisher không chờ trừ khi contract nói vậy |
| Worker ném `RuntimeException` | Async error handler/monitor nhận được; publisher không tự nhận lỗi worker |
| Executor từ chối task | Chính sách scheduling failure được thực thi rõ; không đánh dấu “đã xử lý” |
| Listener bỏ quên `@EnableAsync` | Test phát hiện chạy đồng bộ hoặc startup/config sai |
| Có nhiều listener, một listener lỗi | Xác nhận ảnh hưởng đến các listener khác theo dispatch mode |
| Publisher đang trong transaction rollback | Worker không được giả định có cùng T1; after-commit handler không chạy nếu T1 rollback |
| `@Async @Transactional` worker lỗi | Transaction của worker có thể rollback, transaction publisher không bị đảo ngược |
| Process dừng sau T1 commit | Outbox/job bền vững có thể phục hồi; async queue RAM không đủ |
| Retry sau timeout downstream | Không tạo side effect trùng nếu có idempotency |
| Nhiều instance cùng consume | Khóa dedup/quy tắc xử lý liên instance hoạt động |
| Replay event lịch sử | Không chạy lại hành động nguy hiểm chỉ vì rebuild projection |
| Shutdown executor có task đang chạy | Chính sách graceful shutdown/timeout được kiểm chứng |

### 12.1. Không dùng Thread.sleep để đoán

Một test dùng `Thread.sleep(100)` rồi kiểm tra biến có thể flaky do scheduling và tải CI. Ví dụ hoàn chỉnh ở mục 5 dùng **hai CountDownLatch có timeout**, giúp phân biệt “publish đã trả về” và “async exception đã đi tới handler”.

Với kiểm thử tích hợp có database, không nên kết luận commit/rollback chỉ từ việc listener đã in log. Hãy để transaction thực sự kết thúc rồi query dữ liệu ở ranh giới thích hợp. Nếu test tự được bọc bởi `@Transactional` và cuối test rollback, kết quả có thể khác khi chạy request production.

### 12.2. Test tách đường submit và đường xử lý

Để kiểm tra executor rejection, tạo executor/queue nhỏ và có phương thức kiểm soát task đang chiếm thread, rồi đo chính sách khi submit quá capacity. Test đó **khác** test ném exception trong worker. Nếu library/executor sử dụng fallback sang caller thread, assert đúng fallback thay vì cứng nhắc mong một `RejectedExecutionException`.

### 12.3. Test lỗi không mất công việc

Nếu yêu cầu của hệ thống là “mỗi order được tạo sẽ sinh một lần xử lý notification dù có crash”, test phải bao gồm:

1. Commit đơn và outbox trong một transaction.
2. Giả lập crash hoặc dừng dispatcher trước khi xử lý.
3. Restart dispatcher và đọc lại bản ghi pending.
4. Thực hiện retry nếu lần đầu thất bại.
5. Kiểm tra kết quả, trạng thái outbox và idempotency key.
6. Thử duplicate delivery để bảo đảm không gửi trùng ngoài ý định.

Một unit test của `@Async` không thay thế được loại integration test này.

## 13. Các sai lầm thường gặp

1. **Đặt try/catch quanh publish rồi tưởng đã bắt lỗi async:** exception xảy ra sau ở thread khác không tự đi vào catch đó.
2. **Chỉ gắn @Async, không bật @EnableAsync hoặc cấu hình proxy sai:** listener có thể chạy đồng bộ ngoài dự định.
3. **Dùng final/private/self-invocation khiến proxy không can thiệp như mong muốn:** kiểm tra cơ chế proxy thật.
4. **Chỉ cấu hình ErrorHandler của multicaster:** chưa chắc xử lý exception trong thân `@Async void` đã được async interceptor bắt.
5. **Coi AsyncUncaughtExceptionHandler là hệ thống retry:** nó chỉ xử lý exception theo policy mình viết, không tự lưu job hay phát lại.
6. **Tin rằng worker lỗi sẽ rollback transaction đã commit:** rollback chỉ áp dụng trong ranh giới transaction tương ứng.
7. **Cho rằng @TransactionalEventListener(AFTER_COMMIT) là durable queue:** không chống được process crash sau commit.
8. **Bỏ qua lỗi khi submit task:** executor có thể reject trước khi listener chạy; đây là một đường thất bại riêng.
9. **Dùng retry vô hạn ngay trong listener:** chiếm thread và có thể gây event storm.
10. **Không có idempotency:** timeout sau thành công khiến retry tạo side effect trùng.
11. **Bắt Exception rồi bỏ qua:** gây tình trạng báo thành công giả, không có alert hay trạng thái xử lý.
12. **Lấy tên thread làm bằng chứng duy nhất:** cần kiểm tra executor, timing và outcome.
13. **Không quản lý shutdown:** nhiệm vụ còn trong queue có thể bị bỏ dở khi context đóng.
14. **Mặc định MDC, SecurityContext và transaction tự được kế thừa:** các ngữ cảnh thread-bound cần truyền hoặc khởi tạo phù hợp; không copy transaction.
15. **Không phân biệt error handler logging với business recovery:** log thành công không xác nhận email, projection hoặc payment đã được xử lý.
16. **Cho rằng @Order bảo đảm thứ tự hoàn tất async:** annotation có thể sắp thứ tự dispatch, không bảo đảm hoàn tất task.
17. **Trả event từ async listener rồi mong Spring publish tự động:** với listener async, cần publish event tiếp tường minh.
18. **Không có correlation ID:** khó xác định tác vụ async thất bại thuộc request/aggregate nào.

## 14. Bài tập tự kiểm tra

1. Vì sao `try { publisher.publishEvent(event); } catch (...)` thường không bắt được lỗi ở thân `@Async void`?
2. `AsyncUncaughtExceptionHandler` và `SimpleApplicationEventMulticaster.setErrorHandler` khác nhau ở lớp nào của pipeline?
3. Executor hết capacity ngay lúc submit. Lỗi này có nhất thiết đi vào `AsyncUncaughtExceptionHandler` không?
4. Publisher đã commit đơn, async listener gửi email thất bại. Có thể rollback đơn bằng cách ném `RuntimeException` trong worker không?
5. Một async worker có `@Transactional`; transaction của nó có phải transaction đã mở trong publisher không?
6. `@TransactionalEventListener(AFTER_COMMIT)` bảo đảm điều gì khi publisher rollback? Nó có bảo đảm notification được gửi trước khi process dừng không?
7. Vì sao `CompletableFuture` hữu ích khi muốn theo dõi kết quả async service, nhưng không biến `publishEvent` thành một lời gọi trả future kết quả của tất cả listener?
8. Nếu email provider đã gửi nhưng response timeout, retry thiếu idempotency gây hậu quả gì?
9. Vì sao test `Thread.sleep(100)` không chắc chắn bằng latch có timeout?
10. Một tác vụ bắt buộc không được mất sau commit cần thêm gì ngoài `@Async @EventListener`?
11. Khi có nhiều pod, vì sao một `Set` lưu trong singleton không đủ để deduplicate event?
12. Listener được gọi async lúc context đang đóng có thể gặp những vấn đề nào?

**Gợi ý trả lời:** (1) task lỗi sau khi publisher đã trả về; (2) async method interceptor vs multicaster listener invocation; (3) không, lỗi scheduling có đường riêng; (4) không, transaction nguồn đã hoàn tất; (5) không, worker có transaction riêng khi được tạo đúng; (6) không chạy khi rollback, nhưng không bảo đảm durability; (7) Future thuộc service có return type chứ không phải cơ chế tổng hợp event listener; (8) gửi trùng; (9) scheduling không có thời gian cố định; (10) outbox/job bền vững, retry/idempotency/monitoring; (11) bộ nhớ cục bộ mất khi restart, không đồng bộ giữa pod; (12) task rejection, dependency/connection/executor đang dừng.

## 15. Tóm tắt

Lỗi trong async listener có hai đặc trưng: **không còn chung call stack với publisher** và **không tự chia sẻ transaction nguồn**. Vì vậy:

- Listener đồng bộ và listener async có đường lan truyền exception khác nhau.
- Với `@Async void`, quan sát exception qua `AsyncUncaughtExceptionHandler`, không chờ try/catch của publisher.
- Với executor của multicaster, hiểu `setErrorHandler`, khả năng chuyển thread và chính sách executor; không trộn lẫn hai tầng lỗi.
- Xử lý riêng lỗi submit task và lỗi bên trong worker.
- `@TransactionalEventListener(AFTER_COMMIT)` ràng buộc thời điểm theo commit, nhưng không đảm bảo việc giao công việc bền vững.
- Dùng retry có giới hạn, idempotency và outbox/job storage khi công việc là bắt buộc.
- Kiểm thử async bằng trạng thái kết quả và synchronization đáng tin, không bằng sleep ngẫu nhiên.

## Tài liệu tham khảo

- Spring Framework Reference — *Application Events, Asynchronous Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Task Execution and Scheduling, Exception Management with @Async*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *AsyncUncaughtExceptionHandler*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html
- Spring Framework 6.2.8 Javadoc — *AsyncConfigurer*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
