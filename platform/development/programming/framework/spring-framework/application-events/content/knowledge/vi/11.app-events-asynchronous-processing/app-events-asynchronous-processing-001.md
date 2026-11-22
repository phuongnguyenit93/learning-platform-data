# @Async trên event listener trong Spring Framework

## 1. Mục tiêu và vị trí của @Async

Trong Spring Framework, một phương thức đánh dấu `@EventListener` có thể nhận sự kiện do `ApplicationEventPublisher.publishEvent(...)` phát ra. Theo mặc định, listener được gọi đồng bộ trên luồng phát sự kiện: nếu listener làm công việc mất nhiều thời gian, lời gọi `publishEvent` có thể phải chờ.

Gắn thêm `@Async` cho phương thức listener cho phép Spring **đưa phần thân phương thức sang executor**, để luồng phát sự kiện không phải chờ toàn bộ công việc của listener đó hoàn tất:

~~~java
@EventListener
@Async("eventExecutor")
public void onOrderCreated(OrderCreated event) {
    // Xử lý trên luồng do eventExecutor cấp.
}
~~~

Mục đích thường gặp: gửi thông báo không bắt buộc trả ngay, xử lý audit phụ trợ, tính toán hậu xử lý, hoặc thực hiện công việc độc lập mà không làm tăng thời gian phản hồi của luồng phát sự kiện. Cần phân biệt **bất đồng bộ** với **xử lý bền vững**: `@Async` chỉ thay đổi nơi chạy code trong cùng JVM, không tự lưu sự kiện, retry sau khi tiến trình chết hoặc bảo đảm xử lý đúng một lần.

Các khái niệm liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| `ApplicationEventPublisher` / `ApplicationContext` | Nhận lời gọi phát sự kiện của ứng dụng |
| `ApplicationEventMulticaster` | Xác định và kích hoạt các listener nhận sự kiện |
| `@EventListener` | Đánh dấu phương thức xử lý loại sự kiện phù hợp |
| `@Async` và cơ chế proxy của Spring | Chặn lời gọi phương thức và gửi phần thân sang executor |
| `@EnableAsync` | Bật xử lý annotation `@Async` trong context |
| `Executor` / `TaskExecutor` | Quản lý việc lên lịch và các luồng thực thi |

**Điểm quan trọng:** chỉ gắn `@Async` mà thiếu cơ chế async hoạt động hoặc gọi phương thức qua sai đường đi có thể khiến code vẫn thực thi đồng bộ.

## 2. Luồng thực thi: từ publishEvent đến executor

Với `@EventListener` thông thường:

~~~text
Luồng phát sự kiện                  Listener
       |                               |
       | publishEvent(event)           |
       +------------------------------>|
       |            chạy handle(event) |
       |<------------------------------+
       | tiếp tục sau publishEvent     |
~~~

Với `@EventListener` kết hợp `@Async` và proxy async hoạt động:

~~~text
Luồng phát sự kiện        Spring event adapter/proxy        eventExecutor
       |                            |                           |
       | publishEvent(event)        |                           |
       +--------------------------->|                           |
       |                  lọc loại event, gọi listener proxy    |
       |                            +---- submit task --------->|
       |                            |                     chạy handle(event)
       |<---------------------------+                           |
       | tiếp tục công việc         |                           | kết thúc sau
~~~

Diễn biến chi tiết:

1. Spring nhận sự kiện qua `publishEvent`, dùng bộ phân phối sự kiện của `ApplicationContext` để chọn listener phù hợp.
2. Hệ thống xử lý `@EventListener` tạo adapter gọi phương thức listener trên bean do Spring quản lý.
3. Khi bean được áp dụng cơ chế `@Async`, lời gọi đi qua proxy; interceptor đưa việc thực thi sang executor đã cấu hình.
4. Phần thân listener chạy trên luồng worker; kết quả công việc có thể đến trước hoặc sau bước tiếp theo của publisher, tùy việc lập lịch.
5. Trường hợp executor từ chối nhận tác vụ hoặc lỗi xảy ra lúc gửi tác vụ là một trường hợp khác với exception được ném **trong** phương thức listener sau khi nó đã chạy bất đồng bộ.

Không suy ra thứ tự các dòng log giữa publisher và listener chỉ từ vị trí gọi `publishEvent`. Spring không có bảo đảm rằng task đã khởi chạy trước khi `publishEvent` trả về, cũng không có bảo đảm task sẽ chờ đến khi publisher trả về mới bắt đầu.

## 3. Điều kiện để @Async thực sự hoạt động

### Bật annotation bằng @EnableAsync

Với Spring Framework thuần, cách rõ ràng nhất là thêm `@EnableAsync` vào một lớp cấu hình được đăng ký trong context:

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // Các bean cho listener và executor.
}
~~~

`@EnableAsync` kích hoạt hạ tầng xử lý `@Async`. Trong ứng dụng Spring Boot, có thể dùng cùng annotation; việc Boot tự tạo executor không đồng nghĩa mọi phương thức có `@Async` đều tự động chạy async nếu chưa bật hạ tầng tương ứng.

### Listener phải là Spring bean

Phương thức `@EventListener` phải nằm trong bean được Spring quản lý, chẳng hạn bean được trả về từ `@Bean` hoặc lớp `@Component` nằm trong phạm vi component scan. Lớp tự tạo bằng `new` bên ngoài context không tự trở thành listener được đăng ký và không được Spring tạo proxy async.

### Lời gọi phải đi qua proxy

Trong chế độ proxy thông dụng của `@EnableAsync`, Spring chỉ có thể đánh chặn các lời gọi đi qua proxy:

~~~java
@Service
public class NotificationService {

    public void dispatch() {
        sendLater(); // Tự gọi trong cùng đối tượng: không qua proxy async.
    }

    @Async("eventExecutor")
    public void sendLater() {
        // Không tự động chạy async khi gọi bằng this.sendLater().
    }
}
~~~

Đoạn trên minh họa **lỗi self-invocation**, không phải một ứng dụng chạy độc lập. Giải pháp thông thường là tách công việc async sang bean khác và gọi bean ấy, hoặc để Spring gọi phương thức `@EventListener` thông qua adapter và bean proxy đã được đăng ký đúng. Đừng trông đợi `@Async` có hiệu lực trên phương thức `private`, phương thức không thể được proxy phù hợp hoặc đối tượng tự tạo ngoài Spring.

### Chọn executor rõ ràng

Khai báo `@Async("eventExecutor")` để chọn đúng bean executor, thay vì phụ thuộc vào cách Spring tự chọn executor mặc định:

~~~java
@Bean(name = "eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("events-");
    return executor;
}
~~~

Khi đăng ký qua `@Bean`, Spring quản lý việc khởi tạo và đóng executor. Nếu tự tạo `ThreadPoolTaskExecutor` để dùng ngoài vòng đời bean, cần chủ động quản lý `initialize()` và shutdown.

## 4. Ví dụ Java 17 chạy được: listener chạy trên worker thread

Ví dụ dùng **Spring Framework 6.2.8**, Maven và Java 17, không phụ thuộc Spring Boot. Một record là payload sự kiện; `@EventListener` nhận record đó; `@Async("eventExecutor")` xử lý trên pool có tên luồng bắt đầu bằng `events-`.

Dự án:

~~~text
async-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncEventsDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-listener-demo</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/AsyncEventsDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncEventsDemo {

    public static void main(String[] args) throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderListener listener = context.getBean(OrderListener.class);

            // Spring hỗ trợ publish cả payload không kế thừa ApplicationEvent.
            context.publishEvent(new OrderCreated("ORD-42"));

            // Chờ có giới hạn để minh họa/kiểm thử async một cách xác định.
            if (!listener.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener did not complete");
            }

            System.out.println("worker thread: "
                    + listener.workerThread().startsWith("events-"));
            System.out.println("order id: " + listener.lastOrderId());
        }
    }

    public record OrderCreated(String orderId) {
    }

    @Configuration
    @EnableAsync
    public static class AppConfig {

        @Bean(name = "eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("events-");
            return executor;
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }
    }

    public static class OrderListener {

        private final CountDownLatch finished = new CountDownLatch(1);
        private volatile String lastOrderId;
        private volatile String workerThread;

        @EventListener
        @Async("eventExecutor")
        public void onOrderCreated(OrderCreated event) {
            try {
                lastOrderId = event.orderId();
                workerThread = Thread.currentThread().getName();
            } finally {
                finished.countDown();
            }
        }

        public boolean await(long timeout, TimeUnit unit)
                throws InterruptedException {
            return finished.await(timeout, unit);
        }

        public String lastOrderId() {
            return lastOrderId;
        }

        public String workerThread() {
            return workerThread;
        }
    }
}
~~~

Chạy từ thư mục `async-listener-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncEventsDemo
~~~

Hai dòng do chương trình in, khi executor được khởi tạo và listener hoàn thành bình thường:

~~~text
worker thread: true
order id: ORD-42
~~~

**Vì sao kết quả xác định được?** Phương thức listener lưu tên luồng bắt đầu bằng `events-` và mã đơn hàng, sau đó gọi `CountDownLatch.countDown()`. Luồng main dùng `await` trước khi đọc hai giá trị. Vì vậy, thứ tự kiểm tra được điều khiển bằng tín hiệu hoàn tất thay vì dựa vào `Thread.sleep(...)` hay tốc độ máy. `@EventListener` có thể nhận record `OrderCreated` qua cơ chế payload event, dù record không kế thừa `ApplicationEvent`.

**Điều ví dụ không khẳng định:** không có bảo đảm listener hoàn tất trước khi `publishEvent` trả về; chính vì vậy main phải đợi. Đây là mẫu minh họa xác định cho một sự kiện, không phải thiết kế lưu bền sự kiện hay kiểm thử khả năng chịu tải.

## 5. Chọn executor và quản lý tài nguyên

Có hai con đường thường gặp:

1. Dùng `@Async("eventExecutor")`: listener đó được đưa vào executor chỉ định; các listener khác có thể tiếp tục xử lý đồng bộ.
2. Dùng `@Async` không có tên: Spring chọn executor theo cấu hình `AsyncConfigurer`/bean thích hợp hoặc cơ chế dự phòng; lựa chọn có thể thay đổi theo cấu hình ứng dụng.

Với ứng dụng có nhiều nhóm công việc, tên executor riêng giúp phân tách tải: `paymentNotificationExecutor`, `auditExecutor`, `reportExecutor`... Không nhất thiết tạo một pool cho mỗi listener; việc nhóm theo loại tài nguyên và mức ưu tiên thường dễ quản trị hơn.

Các tham số thiết yếu:

| Tham số | Tác động |
|---|---|
| `corePoolSize` | Số luồng lõi |
| `maxPoolSize` | Giới hạn số luồng khi pool cần mở rộng |
| `queueCapacity` | Số tác vụ có thể chờ trong hàng đợi |
| `threadNamePrefix` | Giúp nhận dạng worker trong log và thread dump |
| Chính sách từ chối | Hành vi khi pool/hàng đợi hết khả năng nhận việc |
| Shutdown policy | Cách xử lý tác vụ tồn đọng khi ứng dụng đóng |

Trong `ThreadPoolExecutor`, khi hàng đợi chưa đầy, pool có thể tiếp tục đưa tác vụ vào hàng đợi thay vì tạo ngay luồng đến `maxPoolSize`; do đó chỉ nâng `maxPoolSize` mà giữ queue quá lớn chưa chắc cải thiện tốc độ xử lý. Cần đo latency, độ dài queue, số task bị từ chối và thời gian xử lý theo tải thực tế.

Nếu executor từ chối `submit`, lỗi có thể xảy ra ngay trên luồng đang phát sự kiện. Vì vậy câu “exception của async listener không bao giờ tới publisher” **chỉ đúng với lỗi bên trong phần thân listener đã được chạy bất đồng bộ**, không phải mọi lỗi lập lịch.

## 6. Exception và AsyncUncaughtExceptionHandler

Một phương thức `@EventListener @Async` có kiểu trả về `void` là dạng phổ biến. Khi phần thân listener ném exception, publisher thông thường đã rời đường gọi trực tiếp; `try/catch` bao quanh `publishEvent` không bắt được lỗi xảy ra sau đó trong worker.

~~~java
try {
    publisher.publishEvent(new OrderCreated("ORD-42"));
} catch (RuntimeException ex) {
    // Không bắt được lỗi phát sinh muộn trong phần thân listener @Async.
    // Nhưng vẫn có thể gặp lỗi đồng bộ khi submit task hoặc từ listener khác.
}
~~~

Spring cung cấp `AsyncUncaughtExceptionHandler` để xử lý exception không được trả về từ phương thức async kiểu `void`. Có thể cài qua `AsyncConfigurer`:

~~~java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorsConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            System.err.println("Async method failed: "
                    + method.getName() + " - " + error.getMessage());
        };
    }
}
~~~

Đây là **mẫu cấu hình riêng**, cần đăng ký vào context; không dán nguyên lớp vào cùng tệp demo mà không tổ chức lại package/import. Trong sản phẩm, dùng logger và hệ thống quan sát lỗi, có thể bổ sung cơ chế retry/queue phù hợp. Handler mặc định có thể ghi log lỗi, nhưng không tạo bảo đảm rằng tác vụ đã được xử lý lại thành công.

Không nhầm `AsyncUncaughtExceptionHandler` của lời gọi `@Async` với `ErrorHandler` của `SimpleApplicationEventMulticaster`. Chúng bắt lỗi ở những lớp khác nhau:

- `AsyncUncaughtExceptionHandler` xử lý exception không có kênh trả kết quả từ phần thân phương thức async kiểu `void`.
- `SimpleApplicationEventMulticaster.setErrorHandler(...)` xử lý exception khi multicaster gọi listener qua đường multicast. Khi lời gọi listener đã đi qua proxy và trả về sau bước enqueue, lỗi xuất hiện muộn trong worker có thể nằm ngoài phạm vi đó.

Đối với công việc phải thành công, handler chỉ ghi log là chưa đủ: cần trạng thái, retry có giới hạn, idempotency và theo dõi các trường hợp thất bại.

## 7. Giới hạn trả về giá trị và việc phát sự kiện tiếp theo

Với `@EventListener` **đồng bộ**, Spring cho phép handler trả về một object hoặc collection để tự phát sự kiện tiếp theo. Cơ chế này **không được hỗ trợ cho listener bất đồng bộ `@Async`**.

Không viết theo kỳ vọng sau:

~~~java
// KHÔNG dùng để tự phát sự kiện tiếp theo trong async listener.
@EventListener
@Async("eventExecutor")
public OrderProcessed onOrderCreated(OrderCreated event) {
    return new OrderProcessed(event.orderId());
}
~~~

Nếu muốn phát thêm sự kiện sau khi công việc async hoàn thành, chủ động inject `ApplicationEventPublisher` và gọi `publishEvent` tại thời điểm phù hợp:

~~~java
public class AsyncOrderHandler {

    private final ApplicationEventPublisher publisher;

    public AsyncOrderHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    @Async("eventExecutor")
    public void onOrderCreated(OrderCreated event) {
        // Hoàn tất một bước xử lý.
        publisher.publishEvent(new OrderProcessed(event.orderId()));
    }
}
~~~

Đoạn trên là **mã minh họa cần tích hợp**: `OrderCreated` và `OrderProcessed` là các loại sự kiện của ứng dụng; `AsyncOrderHandler` phải được đăng ký làm Spring bean. `publishEvent` mới phát từ worker thread, nên listener của `OrderProcessed` có thể chạy trên chính worker đó nếu chúng đồng bộ; cần cẩn thận với vòng lặp event, lỗi và phụ thuộc giữa các bước.

## 8. @Async có thay thế executor của ApplicationEventMulticaster không?

Không. Hai cách cấu hình tác động ở các lớp khác nhau.

| Tiêu chí | `@Async` trên `@EventListener` | Executor trên `SimpleApplicationEventMulticaster` |
|---|---|---|
| Phạm vi | Chọn từng phương thức listener | Ảnh hưởng các listener cho phép async qua multicaster |
| Cơ chế | Async method proxy/interceptor của Spring | Multicaster lập lịch lời gọi `ApplicationListener` |
| Bật bằng | `@EnableAsync` và annotation | Bean `applicationEventMulticaster` có `setTaskExecutor` |
| Xử lý lỗi | Chủ yếu qua cơ chế async method | `ErrorHandler` của multicaster, executor |
| Listener đồng bộ còn lại | Không bị `@Async` của listener khác làm đổi chế độ | Có thể được dispatch async nếu listener hỗ trợ |
| Gắn với transaction | Cần xét pha transaction và ngữ cảnh worker | Listener transaction có thể từ chối async |

Ví dụ cấu hình multicaster (mã cấu hình minh họa, khác cách `@Async` của bài):

~~~java
@Bean(name = "applicationEventMulticaster")
public ApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Khi dùng ví dụ này, phải import đúng `ApplicationEventMulticaster` và `SimpleApplicationEventMulticaster`, đăng ký bean executor cùng context và đánh giá hành vi mọi listener liên quan. Từ Spring 6.1, `ApplicationListener.supportsAsyncExecution()` cho phép một listener yêu cầu chạy trên luồng phát, chẳng hạn listener đồng bộ theo transaction; cấu hình executor ở multicaster không cưỡng ép tất cả listener sang worker.

Đối với bài toán **chỉ một vài listener cần chạy async**, `@Async` trên đúng listener và một executor được đặt tên thường là lựa chọn dễ hiểu hơn.

## 9. @TransactionalEventListener, giao dịch và ngữ cảnh luồng

Bất đồng bộ làm phát sinh ranh giới luồng thực thi. Những gì gắn với luồng phát thường không tự động đi theo sang worker, ví dụ:

- Spring transaction synchronization và transaction-bound resources.
- `ThreadLocal` do ứng dụng tự đặt, request context hoặc security context nếu chưa có cơ chế truyền ngữ cảnh.
- Mã truy vết và MDC trong logging, khi chưa cấu hình propagation.
- Persistence context/session đang thuộc giao dịch của luồng khác.

Đặc biệt, `@EventListener @Async` không có nghĩa “chỉ xử lý khi transaction đã commit”. Publisher có thể phát event khi transaction còn đang chạy; worker bắt đầu trước commit, không thấy dữ liệu mới, hoặc transaction bên phát có thể rollback sau đó.

Nếu nghiệp vụ phải chờ commit, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Có thể thiết kế công việc async xảy ra **sau pha commit**, nhưng phải hiểu rằng phần xử lý trên worker diễn ra trong ngữ cảnh luồng riêng, không tự mang transaction của publisher sang:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Async("eventExecutor")
public void afterOrderCommitted(OrderCreated event) {
    // Công việc bất đồng bộ được khởi phát sau callback AFTER_COMMIT.
    // Nếu cần thao tác DB, hãy dùng transaction phù hợp ở luồng worker.
}
~~~

Đoạn này cần `OrderCreated`, transaction management thực tế và executor đã cấu hình. `@TransactionalEventListener` mặc định không chạy nếu không có transaction phù hợp, trừ khi cấu hình `fallbackExecution = true`. Khi chuyển qua worker, chỉ chuyển dữ liệu cần thiết (chẳng hạn ID và snapshot đủ dùng); tránh dựa vào lazy-loaded entity hoặc đối tượng giao dịch của luồng phát. Đối với thao tác cần sự kiện bền vững qua crash/rollback, hãy cân nhắc transactional outbox và message broker.

## 10. @Order không bảo đảm thứ tự hoàn thành async

Giả sử hai listener cùng nhận một sự kiện:

~~~java
@Order(1)
@EventListener
@Async("eventExecutor")
public void updateSearchIndex(OrderCreated event) {
    // Có thể hoàn thành sau listener khác.
}

@Order(2)
@EventListener
@Async("eventExecutor")
public void notifyDashboard(OrderCreated event) {
    // Có thể hoàn thành trước listener @Order(1).
}
~~~

`@Order` chủ yếu liên quan thứ tự gọi listener khi dispatch, **không phải thứ tự hoàn tất phần thân async**. Nếu bước B bắt buộc phụ thuộc kết quả của bước A, đừng dùng hai listener async độc lập kèm `@Order` để biểu diễn quan hệ đó. Thay vào đó, đặt chúng trong cùng workflow có thứ tự, dùng cơ chế đồng bộ rõ ràng, hoặc phát event tiếp theo khi A thật sự hoàn tất.

Với nhiều event cùng loại, listener cũng có thể xử lý đồng thời và hoàn tất đảo thứ tự; cần khóa/idempotency/partition theo khóa nghiệp vụ nếu thứ tự là yêu cầu bắt buộc.

## 11. Kiểm thử listener async đáng tin cậy

Một kiểm thử chỉ thực hiện:

~~~java
publisher.publishEvent(event);
verify(service).sendMessage();
~~~

có thể thất bại ngẫu nhiên nếu `verify` chạy trước worker, hoặc tạo false confidence nếu test context vô tình không bật `@EnableAsync` và code lại chạy đồng bộ.

Nên kiểm tra các tín hiệu có ý nghĩa:

1. Context bật `@EnableAsync` và có đúng executor mà listener dùng.
2. Sự kiện được phát bằng `ApplicationEventPublisher` hoặc context thực, listener được đăng ký.
3. Trạng thái đầu ra đúng khi **listener đã hoàn tất**; dùng `CountDownLatch` như demo, `CompletableFuture` ở lớp dịch vụ, hoặc thư viện chờ theo điều kiện.
4. Kiểm tra exception, chính sách retry, timeout và tác vụ bị từ chối khi các yêu cầu đó quan trọng.
5. Nếu ứng dụng yêu cầu không chạy trên publisher thread, kiểm tra tên/ID thread hoặc cơ chế đồng bộ đo được, không chỉ thêm `Thread.sleep` rồi suy đoán.

`CountDownLatch.await(timeout, unit)` giúp test có giới hạn thời gian rõ ràng. Trong chương trình thật, có thể dùng completion signal khác; đừng giữ luồng xử lý HTTP chờ task async chỉ để biến việc xử lý trở lại đồng bộ.

## 12. Tình huống thực tế và quyết định thiết kế

**Tình huống A — Gửi email thông báo sau khi tạo đơn hàng.** Service tạo đơn và phát `OrderCreated`. Một listener `@Async` gọi dịch vụ gửi email. Nếu email chỉ là tiện ích, độ trễ được tách khỏi request. Nhưng nếu gửi thất bại, cần log/tracking và chiến lược retry tùy yêu cầu; `@Async` không tự lưu email chờ gửi.

**Tình huống B — Ghi dấu vết kiểm toán bắt buộc.** Nếu audit là điều kiện phải thành công cùng transaction, đẩy phần ghi duy nhất sang một listener `@Async` có thể đánh mất tính nhất quán. Hãy xác định ranh giới giao dịch và cơ chế ghi bền trước khi chọn chạy async.

**Tình huống C — Xử lý cập nhật cache.** Listener async có thể làm mới cache mà không chặn publisher. Nhưng nếu request tiếp theo phải đọc trạng thái mới ngay lập tức, chế độ eventual consistency có thể không đáp ứng; phải công bố rõ hợp đồng nhất quán dữ liệu.

**Tình huống D — Nhiều event đến dồn dập.** Executor có giới hạn luồng và queue; khi đầy, publish có thể gặp lỗi submit hoặc mất tác vụ nếu code nuốt lỗi. Cần theo dõi backlog, chọn rejection policy, điều tiết tốc độ và thiết kế cơ chế chịu lỗi.

## 13. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| Listener vẫn chạy trên thread publisher | Thiếu `@EnableAsync`, bean không được Spring quản lý, gọi self-invocation | Kiểm tra cấu hình context, proxy, tên thread |
| Listener không được gọi | Bean không đăng ký, `@EventListener` không đúng kiểu event, sai context | Kiểm tra bean và kiểu payload |
| `@Async("...")` báo không có executor | Sai tên bean executor hoặc cấu hình chưa nạp | Xác nhận bean tên được dùng |
| Publisher không thấy lỗi listener | Exception xảy ra trong worker | Cấu hình `AsyncUncaughtExceptionHandler`, log/metrics |
| Listener không đọc được dữ liệu DB mới | Worker chạy trước commit hoặc không có cùng transaction | Dùng đúng pha transaction và transaction riêng |
| Dòng log mất trace/request ID | MDC/ThreadLocal không tự chuyển luồng | Dùng `TaskDecorator` hoặc cơ chế propagation phù hợp |
| Tác vụ xử lý chậm, hàng đợi tăng | Pool thiếu tài nguyên, việc block I/O, queue quá lớn | Đo thời gian, năng lực xử lý, queue và tải |
| Lúc tắt ứng dụng còn việc chưa hoàn thành | Đóng context khi task vẫn còn chạy | Định nghĩa chính sách shutdown, chờ/cấp cơ chế bền nếu cần |
| Hai listener chạy đảo thứ tự | `@Order` không đồng nghĩa thứ tự hoàn tất async | Thiết kế chuỗi phụ thuộc rõ ràng |
| Event bị xử lý trùng | Publisher phát nhiều lần, listener trùng, retry không idempotent | Gắn event ID và thiết kế xử lý lặp an toàn |

Khi chẩn đoán, ghi kèm `eventId`, loại event, tên listener, tên luồng, thời điểm enqueue/bắt đầu/kết thúc và kết quả xử lý. Tách rõ **đã phát event**, **đã nhận task**, **đã bắt đầu chạy** và **đã hoàn tất thành công**; đó là bốn trạng thái khác nhau.

## 14. Những nguyên tắc cần nhớ

- `@EventListener` chọn phương thức nhận đúng sự kiện; `@Async` đưa phần xử lý của phương thức ấy sang executor khi hạ tầng/proxy hoạt động.
- Phải bật `@EnableAsync`, dùng listener là Spring bean, và ưu tiên executor có tên để cấu hình có thể kiểm chứng.
- `publishEvent` trả về không chứng minh listener async đã hoàn tất; dùng tín hiệu kết quả hoặc theo dõi trạng thái riêng.
- Exception trong phần thân `void @Async` không tự lan về publisher; xử lý qua `AsyncUncaughtExceptionHandler` và cơ chế giám sát, đồng thời lưu ý lỗi enqueue là một trường hợp khác.
- Listener async không tự phát event mới bằng giá trị `return`; gọi `ApplicationEventPublisher.publishEvent` một cách tường minh nếu cần.
- Transaction, ThreadLocal, MDC và trật tự hoàn tất không tự được bảo toàn khi đổi luồng.
- `@Async` hữu ích cho xử lý nền trong một tiến trình Spring; yêu cầu lưu bền, retry, bảo đảm giao hàng và khôi phục sau crash cần cơ chế bổ sung.

### Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext events, asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Task execution and @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Javadoc 6.2.8 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Javadoc — @EventListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html)
