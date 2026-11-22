# Chỉ định executor bằng qualifier trong Spring Framework Application Events

## 1. Bài toán và mục tiêu

Giả sử một ứng dụng phát sự kiện `OrderPlaced` khi đơn hàng được tạo. Nhiều listener cùng quan tâm sự kiện này nhưng có tính chất tải khác nhau:

- **Email listener** gửi thư xác nhận, thường chờ I/O mạng và có thể bị giới hạn tốc độ bởi nhà cung cấp.
- **Audit listener** ghi dấu vết nghiệp vụ, nên có tài nguyên riêng để không bị email chậm kéo theo.
- **Metrics listener** cập nhật số liệu, thường là tác vụ rất ngắn và có thể cần một chính sách xử lý khác.

Spring hỗ trợ `@EventListener` để đăng ký listener, `@Async` để thực thi listener bất đồng bộ, và cho phép `@Async("...")` chọn một executor cụ thể theo **tên bean** hoặc **qualifier**. Mục tiêu của bài học là biết đăng ký nhiều executor, gắn đúng executor cho từng event listener, kiểm chứng luồng thực thi, và xử lý các vấn đề về quá tải, lỗi và transaction.

Một executor là nơi tiếp nhận và thực thi task. Với `ThreadPoolTaskExecutor`, task được chạy bởi các luồng trong pool theo cấu hình; nó không phải hàng đợi thông điệp bền vững, không tự cung cấp retry hay đảm bảo xử lý đúng một lần.

## 2. Phân biệt các vai trò

| Thành phần | Công dụng | Ví dụ |
| --- | --- | --- |
| `ApplicationEventPublisher` | Công bố sự kiện tới Spring context | `publisher.publishEvent(new OrderPlaced("O-42"))` |
| `@EventListener` | Đánh dấu phương thức nhận một loại sự kiện | `@EventListener public void onOrder(OrderPlaced e)` |
| `@EnableAsync` | Bật hạ tầng Spring xử lý `@Async` | Trên class `@Configuration` |
| `@Async` | Yêu cầu thực thi phương thức bất đồng bộ | `@Async` hoặc `@Async("mailExecutor")` |
| `Executor` / `TaskExecutor` | Thực thi task trên luồng được quản lý | `ThreadPoolTaskExecutor` |
| `@Bean("mailExecutor")` | Đặt tên cho bean executor | Listener có thể chọn `"mailExecutor"` |
| `@Qualifier("auditLane")` | Gắn định danh qualifier cho bean | Listener có thể chọn `"auditLane"` |
| `ApplicationEventMulticaster` | Chọn và phân phối các listener phù hợp | `SimpleApplicationEventMulticaster` |

Điểm thường nhầm là **`@Qualifier` không tự biến một phương thức thành bất đồng bộ**. `@Qualifier` cung cấp một định danh để Spring tìm bean. Với event listener, cần `@Async("auditLane")` để chỉ rõ pool mà listener phải dùng.

## 3. Cách chỉ định executor theo tên bean hoặc qualifier

### 3.1. Chọn theo tên bean

Ta đăng ký một executor có tên `mailExecutor`:

```java
@Bean("mailExecutor")
public ThreadPoolTaskExecutor mailExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("mail-");
    return executor;
}
```

Listener chọn bean này bằng:

```java
@Async("mailExecutor")
@EventListener
public void sendOrderEmail(OrderPlaced event) {
    // Xử lý trên mailExecutor.
}
```

Spring tìm executor bằng định danh `mailExecutor`. Một bean được Spring quản lý, thay vì executor tạo mới trong listener, cho phép cấu hình, tái sử dụng và quản lý vòng đời thống nhất.

### 3.2. Chọn theo qualifier khác tên bean

Một executor có thể mang **tên bean** và **qualifier** khác nhau:

```java
@Bean("auditThreadPool")
@Qualifier("auditLane")
public ThreadPoolTaskExecutor auditThreadPool() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("audit-");
    return executor;
}
```

Listener có thể viết:

```java
@Async("auditLane")
@EventListener
public void writeAudit(OrderPlaced event) {
    // Chọn bean auditThreadPool thông qua qualifier auditLane.
}
```

Theo Spring, giá trị `value` của `@Async` được dùng để tìm executor có **bean name** hoặc **qualifier** tương ứng. Với ví dụ trên, `@Async("auditThreadPool")` cũng có thể chọn cùng executor theo bean name. Các đoạn ở mục này minh họa từng phần; một chương trình hoàn chỉnh nằm ở mục 5.

### 3.3. Không nhầm `@Qualifier` khi tiêm dependency

Đoạn sau chỉ điều khiển **dependency injection**:

```java
public OrderService(@Qualifier("auditLane") Executor executor) {
    this.executor = executor;
}
```

Việc một service có field `executor` được tiêm từ `auditLane` không khiến các phương thức `@EventListener` của service tự chạy trên pool đó. Nếu muốn Spring tự gửi lời gọi listener sang pool, hãy đặt `@Async("auditLane")` trên phương thức listener. Nếu muốn tự nộp task qua `executor.execute(...)` thì đó là cơ chế điều phối thủ công, với vòng đời và xử lý lỗi khác.

## 4. Điều kiện để cơ chế hoạt động

- **Bật `@EnableAsync`** trong cấu hình thực sự được nạp vào `ApplicationContext`. Spring thuần không tự kích hoạt `@Async` chỉ vì tồn tại annotation.
- **Tạo executor là Spring bean** và chọn đúng tên/qualifier. Với `ThreadPoolTaskExecutor` khai báo bằng `@Bean`, Spring gọi các callback vòng đời cần thiết để khởi tạo pool.
- **Đăng ký listener là Spring bean** và bảo đảm lời gọi đi qua cơ chế proxy của Spring. Ở proxy mode mặc định, gọi nội bộ như `this.someAsyncMethod()` không đi qua proxy.
- **Dùng phương thức có thể proxy**: ví dụ dùng class không `final` và phương thức `public`, tránh những cấu trúc khiến Spring không thể áp dụng advice bất đồng bộ.
- **Đừng phụ thuộc vào thứ tự hoàn thành** giữa các listener async. Mỗi pool có lịch chạy riêng; có thể không có thứ tự kết quả giống thứ tự đăng ký listener.
- **Kiểm tra quá tải**: executor có thể từ chối task nếu đã bận và hàng đợi đầy. "Async" không đồng nghĩa với "không bao giờ lỗi".

Ở cấu hình thường gặp, event multicaster vẫn phân phối listener trên luồng publisher. Khi adapter gọi một listener `@Async("mailExecutor")` trên Spring proxy, proxy gửi công việc sang `mailExecutor`. Vì vậy mã gọi `publishEvent` thường không đợi phần thân listener hoàn tất.

```text
publishEvent(OrderPlaced)
      |
      v
ApplicationEventMulticaster
      |
      +-- @EventListener + @Async("mailExecutor")
      |        |
      |        +--> mailExecutor --> mail-* threads
      |
      +-- @EventListener + @Async("auditLane")
               |
               +--> auditThreadPool --> audit-* threads
```

## 5. Ví dụ Java 17 + Maven chạy được

Ứng dụng sau tạo hai listener cho cùng một `OrderPlaced`:

1. `sendEmail` chọn executor qua **tên bean** `mailExecutor`.
2. `recordAudit` chọn executor qua **qualifier** `auditLane` của bean có tên `auditThreadPool`.

Chương trình dùng `CountDownLatch` để đợi cả hai listener và `ConcurrentHashMap` để nhận kết quả từ các luồng. Đầu ra không dựa vào thứ tự thực thi của hai pool.

**Cấu trúc thư mục**

```text
qualified-event-executors/
├── pom.xml
└── src/main/java/example/QualifiedEventExecutorsDemo.java
```

**Tệp `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>qualified-event-executors</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.QualifiedEventExecutorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/example/QualifiedEventExecutorsDemo.java`**

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class QualifiedEventExecutorsDemo {

    public record OrderPlaced(String orderId) {}

    public static final class ExecutionEvidence {
        private final CountDownLatch finished = new CountDownLatch(2);
        private final Map<String, String> threads =
                new ConcurrentHashMap<>();

        public void record(String key, String threadName) {
            threads.put(key, threadName);
            finished.countDown();
        }

        public void waitForBoth() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for event listeners");
            }
        }

        public String getThread(String key) {
            return threads.get(key);
        }
    }

    // Không đánh dấu final vì bean này được Spring proxy cho @Async.
    public static class OrderListeners {
        private final ExecutionEvidence evidence;

        public OrderListeners(ExecutionEvidence evidence) {
            this.evidence = evidence;
        }

        @Async("mailExecutor")
        @EventListener
        public void sendEmail(OrderPlaced event) {
            evidence.record("mail:" + event.orderId(),
                    Thread.currentThread().getName());
        }

        @Async("auditLane")
        @EventListener
        public void recordAudit(OrderPlaced event) {
            evidence.record("audit:" + event.orderId(),
                    Thread.currentThread().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean
        public ExecutionEvidence executionEvidence() {
            return new ExecutionEvidence();
        }

        @Bean
        public OrderListeners orderListeners(ExecutionEvidence evidence) {
            return new OrderListeners(evidence);
        }

        @Bean("mailExecutor")
        public ThreadPoolTaskExecutor mailExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("mail-");
            return executor;
        }

        @Bean("auditThreadPool")
        @Qualifier("auditLane")
        public ThreadPoolTaskExecutor auditThreadPool() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("audit-");
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String publisherThread = Thread.currentThread().getName();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderPlaced("ORD-42"));

            ExecutionEvidence evidence =
                    context.getBean(ExecutionEvidence.class);
            evidence.waitForBoth();

            String mailThread = evidence.getThread("mail:ORD-42");
            String auditThread = evidence.getThread("audit:ORD-42");

            System.out.println("mail chọn đúng pool: "
                    + (mailThread != null
                            && mailThread.startsWith("mail-")));
            System.out.println("audit chọn bằng qualifier: "
                    + (auditThread != null
                            && auditThread.startsWith("audit-")));
            System.out.println("cả hai khác luồng phát: "
                    + (!publisherThread.equals(mailThread)
                            && !publisherThread.equals(auditThread)));
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Ba dòng chuẩn do ứng dụng in**, không tính log công cụ nếu có:

```text
mail chọn đúng pool: true
audit chọn bằng qualifier: true
cả hai khác luồng phát: true
```

Cách đối chiếu: `mailThread` có tiền tố `mail-`, `auditThread` có tiền tố `audit-` và cả hai đều khác `publisherThread`. Đây là kiểm tra hành vi chạy trên luồng thực, không đơn thuần dựa vào annotation trong mã nguồn.

`CountDownLatch` có thời hạn 10 giây. Nếu listener không hoàn thành, chương trình ném lỗi timeout, không báo ba dòng thành công. `ConcurrentHashMap` an toàn khi hai task cùng ghi kết quả, còn latch đảm bảo `main` đợi đủ hai lần `record`. `ThreadPoolTaskExecutor` được Spring quản lý và đóng khi context đóng.

Payload `OrderPlaced` là một Java `record`, không kế thừa `ApplicationEvent`. Spring hỗ trợ `publishEvent(Object)` và có thể bọc payload trong `PayloadApplicationEvent`; phương thức `@EventListener` vẫn nhận `OrderPlaced` trực tiếp.

## 6. Khi có nhiều executor, Spring chọn thế nào?

### 6.1. `@Async("...")` chọn đích tường minh

Khi ghi `@Async("mailExecutor")`, Spring tra cứu executor theo tên bean hoặc qualifier tương ứng; cách này được ưu tiên hơn lựa chọn executor mặc định của async support. Vì vậy, một ứng dụng có nhiều pool vẫn có thể gắn chính xác pool theo từng listener.

Nếu đổi bean `mailExecutor` thành `emailPool`, phải cập nhật annotation tương ứng hoặc cung cấp qualifier/alias nhất quán; không nên mặc định Spring tự chọn pool có tên "gần giống".

### 6.2. `@Async` không có tên dùng cơ chế mặc định

Khi không ghi value:

```java
@Async
@EventListener
public void handleEvent(OrderPlaced event) {
    // Dùng executor mặc định của cơ chế async Spring.
}
```

Spring dùng quy tắc chọn executor mặc định (có thể được cung cấp qua `AsyncConfigurer`; nếu không có thì các quy tắc tìm bean executor của framework được áp dụng). Trong ứng dụng có nhiều pool, đừng dựa vào suy đoán về pool được chọn; khai báo executor mặc định rõ ràng hoặc gắn qualifier cụ thể cho listener.

Đây là một **mẫu cấu hình minh họa** khi cần default, không được trộn nguyên xi vào ví dụ mục 5 nếu chưa cung cấp bean `generalExecutor`:

```java
@Configuration
@EnableAsync
class AsyncDefaults implements AsyncConfigurer {
    private final Executor defaultExecutor;

    AsyncDefaults(@Qualifier("generalExecutor") Executor executor) {
        this.defaultExecutor = executor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return defaultExecutor;
    }
}
```

Đoạn này cần import `java.util.concurrent.Executor`, `AsyncConfigurer`, các annotation Spring và cần có bean executor tương ứng. Một listener có `@Async("auditLane")` vẫn chọn theo qualifier riêng thay vì sử dụng giá trị mặc định của `AsyncConfigurer`.

### 6.3. Chỉ định `@Async` cấp lớp

`@Async("mailExecutor")` có thể đặt trên lớp để áp dụng cho các phương thức thuộc phạm vi hỗ trợ của Spring; annotation `@Async("auditLane")` đặt ở một phương thức riêng có thể ghi đè lựa chọn ở cấp lớp. Với event listener phục vụ nhiều nhiệm vụ, khai báo từng phương thức thường giúp người đọc thấy rõ mỗi luồng công việc dùng pool nào.

### 6.4. So với executor cấp multicaster

`SimpleApplicationEventMulticaster#setTaskExecutor(...)` cấu hình cách multicaster gửi các lời gọi listener đủ điều kiện sang executor. Đây là lựa chọn **cấp phân phối sự kiện**, khác với `@Async("...")` lựa chọn theo từng phương thức.

| Cách cấu hình | Phạm vi | Cần `@EnableAsync`? |
| --- | --- | --- |
| `@Async("mailExecutor")` trên event listener | Một phương thức listener | Có, trong cấu hình Spring thuần |
| `@Async` không có value | Một phương thức listener, dùng mặc định | Có |
| `SimpleApplicationEventMulticaster#setTaskExecutor(executor)` | Những listener được multicaster cho phép chạy async | Không phụ thuộc `@EnableAsync` để dùng executor của multicaster |

Việc đồng thời cấu hình executor ở multicaster và `@Async` trên listener có thể tạo hai tầng dispatch; chỉ làm khi có lý do cụ thể, đã hiểu trách nhiệm mỗi tầng. Trong Spring 6.1+, listener ràng buộc transaction có thể yêu cầu thực hiện phần đăng ký callback trên luồng publisher; multicaster phải tôn trọng `supportsAsyncExecution()` khi chọn listener để chạy bất đồng bộ.

## 7. Cấu hình pool theo tải nghiệp vụ

`ThreadPoolTaskExecutor` thường dùng ba tham số:

- `corePoolSize`: số luồng lõi.
- `maxPoolSize`: số luồng tối đa khi cần mở rộng.
- `queueCapacity`: số task chờ trong hàng đợi. Khi các luồng lõi đang bận, công việc có thể xếp hàng trước khi tạo thêm luồng ngoài mức lõi.

Ví dụ cấu hình `corePoolSize = 2`, `maxPoolSize = 8`, `queueCapacity = 100` không có nghĩa tám task lập tức chạy song song. Một queue lớn có thể giữ nhiều task chờ trong khi pool chưa mở rộng lên mức tối đa; phải đo tải và thời gian chờ thực tế.

| Loại công việc | Điều cần cân nhắc | Chính sách gợi ý |
| --- | --- | --- |
| Email, HTTP, I/O | Timeout, giới hạn dịch vụ ngoài | Pool riêng, giới hạn luồng và queue |
| Tính toán CPU | Tranh chấp tài nguyên xử lý | Pool phù hợp năng lực CPU |
| Audit quan trọng | Không mất dữ liệu khi dừng ứng dụng | Lưu bền vững/outbox; executor chỉ để thực thi |
| Công việc ngắn | Độ trễ thấp và chi phí context switch | Pool vừa phải, quan sát queue và active tasks |

Một pool quá tải có thể từ chối nộp task; khi đó Spring có thể ném `TaskRejectedException` tại thời điểm gửi công việc. Cần tách lỗi **gửi task** khỏi lỗi **bên trong listener**. Không giải quyết quá tải bằng cách tăng queue không giới hạn mà không hiểu tác động đến bộ nhớ và độ trễ.

Đặt `threadNamePrefix` rõ ràng giúp quan sát: `mail-*` khác `audit-*` trong log và thread dump. Trong production cũng nên theo dõi active threads, queue size, task rejects và thời gian thực thi.

## 8. Exception trong listener bất đồng bộ

Với một phương thức listener trả về `void` và có `@Async`:

- Nếu code trong listener ném exception khi đã chạy trên executor, exception **không tự động truyền về** phương thức gọi `publishEvent`.
- Spring có `AsyncUncaughtExceptionHandler` để xử lý exception của phương thức `@Async` trả về `void`; mặc định lỗi thường được log.
- Nếu executor không tiếp nhận được task, lỗi **rejection** có thể xuất hiện trên đường dispatch trước khi phần thân listener bắt đầu; không được nhầm hai trường hợp.
- Không thể dựa vào giá trị trả về của một async `@EventListener` để tự động publish sự kiện tiếp theo. Nếu cần sự kiện mới, inject `ApplicationEventPublisher` và gọi `publishEvent(...)` tường minh.

Đoạn dưới minh họa cấu hình error handler trong một class `AsyncConfigurer`:

```java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, args) ->
            System.err.println("Async listener failed: "
                    + method.getName() + ": " + error.getMessage());
}
```

Để đưa vào ứng dụng thật cần class cấu hình đầy đủ, các import tương ứng và log/giám sát phù hợp; đây không phải chương trình standalone. Nếu tác vụ quan trọng, nên có định danh sự kiện, chính sách retry/idempotency và nơi ghi lại thất bại. Việc chỉ log lỗi không giúp task tự chạy lại.

## 9. Transaction, thứ tự và dữ liệu luồng

### 9.1. Listener async có thể chạy trước commit

Nếu một service `@Transactional` phát `OrderPlaced` trong transaction, listener `@EventListener @Async("mailExecutor")` có thể bắt đầu xử lý trên luồng mail **trước khi transaction commit**. Nếu transaction sau đó rollback thì email vẫn có thể đã gửi.

Với xử lý phải đợi commit, cân nhắc:

```java
// Đoạn minh họa tích hợp bên trong một Spring bean.
// Cần @EnableAsync và transaction manager hoạt động thực tế.
@Async("mailExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendEmailAfterCommit(OrderPlaced event) {
    // Chỉ bắt đầu sau khi transaction phát event commit thành công.
}
```

Mã trên cần import `@Async`, `@TransactionalEventListener` và `TransactionPhase`, không phải ví dụ biên dịch độc lập. `@TransactionalEventListener` mặc định là `AFTER_COMMIT` và mặc định `fallbackExecution = false`, nên nếu phát ngoài transaction thì listener **không chạy**. Cơ chế đăng ký callback phase vẫn phải gắn với transaction ở luồng publisher; bản thân công việc async không tự mang transaction đó sang một luồng mới.

### 9.2. Executor không làm task bền vững

Một task đang nằm trong bộ nhớ của `ThreadPoolTaskExecutor` có thể mất khi process dừng đột ngột. `AFTER_COMMIT` giúp chọn thời điểm xử lý nhưng không tự đảm bảo delivery đáng tin cậy. Với email/hóa đơn có yêu cầu không mất, có thể áp dụng **transactional outbox** cùng worker/broker, retry và idempotency.

### 9.3. Không kỳ vọng context tự truyền

Các luồng executor không mặc định mang cùng transaction `ThreadLocal`, security context hay MDC với luồng publish. Đưa `orderId`/`eventId` vào payload; nếu cần chuyển thông tin bối cảnh luồng, dùng giải pháp propagation/`TaskDecorator` được thiết kế rõ ràng. Một listener được chọn đúng executor vẫn có thể thiếu thông tin mà code phụ thuộc ngầm vào `ThreadLocal`.

### 9.4. Đừng phụ thuộc thứ tự hoàn thành listener

Hai listener của cùng một event được gửi đến hai pool có thể hoàn thành theo thứ tự khác nhau. `@Order` có thể ảnh hưởng thứ tự gọi listener trong phân phối, nhưng không đảm bảo thời điểm **hoàn thành** công việc async. Khi tác vụ B buộc phải chạy sau A, hãy dùng workflow/service có phụ thuộc rõ ràng hoặc một hàng đợi phù hợp.

## 10. Kiểm thử và chẩn đoán

Ma trận kết quả của ví dụ mục 5:

| Listener | `@Async` value | Bean được chọn | Tên luồng kỳ vọng |
| --- | --- | --- | --- |
| `sendEmail` | `mailExecutor` | `mailExecutor` | Bắt đầu bằng `mail-` |
| `recordAudit` | `auditLane` | `auditThreadPool` có `@Qualifier("auditLane")` | Bắt đầu bằng `audit-` |

Một phép thử hợp lý cần xác nhận **hai listener đều nhận event**, cả hai hoàn thành trước khi kiểm tra, và mỗi listener chạy trên đúng pool. `CountDownLatch` kèm timeout là một cách phù hợp; chỉ dùng `Thread.sleep` tùy ý có thể tạo test chập chờn.

Các tình huống nên kiểm thử thêm:

1. Đổi qualifier thành tên không tồn tại: xác nhận lỗi cấu hình hoặc dispatch được báo rõ.
2. Bỏ `@EnableAsync` trong một fixture riêng: chứng minh hành vi khác với thực thi qua executor.
3. Đổi `queueCapacity` nhỏ và chạy nhiều task: kiểm tra rejection/backpressure theo chính sách.
4. Một listener ném exception: xác nhận handler/log nhận lỗi và không xem đó là kết quả hoàn thành thành công.
5. Phát sự kiện trong transaction commit và rollback: phân biệt `@EventListener` với `@TransactionalEventListener`.
6. Tắt context khi task chưa hoàn thành: xác định chính sách chờ shutdown hoặc lưu công việc chưa xong theo yêu cầu hệ thống.

### Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Listener chạy trên luồng publisher | Quên `@EnableAsync`, lời gọi bypass proxy, bean không do Spring quản lý | Kiểm tra cấu hình, proxy và cách gọi |
| Không tìm được executor | Giá trị trong `@Async("...")` sai tên/qualifier hoặc bean không đúng loại | Kiểm tra tên bean, `@Qualifier` và kiểu `Executor` |
| Listener không chạy | `@EventListener` không được đăng ký, event type sai hoặc điều kiện không thỏa | Kiểm tra context và khai báo listener |
| Task bị từ chối | Pool quá tải, hàng đợi đầy, executor đã shutdown | Xác định giới hạn pool, rejection policy và phương án retry |
| Log lỗi ở executor nhưng publisher không thấy exception | Exception từ phần thân listener `void` async | Dùng `AsyncUncaughtExceptionHandler` và observability |
| Hành vi khác nhau giữa môi trường | Cấu hình executor mặc định thay đổi, bean name/qualifier đổi | Chọn executor tường minh và kiểm tra cấu hình khi khởi động |
| Email được gửi dù transaction rollback | `@EventListener` async chạy trước commit | Cân nhắc `@TransactionalEventListener(AFTER_COMMIT)` và outbox |
| Log thiếu correlation ID | Context dạng `ThreadLocal` không được tự truyền | Mang ID trong event và cấu hình propagation khi cần |

## 11. Checklist áp dụng

- Xác định tải, độ trễ, độ quan trọng và yêu cầu isolation cho mỗi nhóm listener.
- Khai báo pool dưới dạng Spring bean có tên/qualifier rõ ràng.
- Bật `@EnableAsync` và dùng listener bean có thể được Spring proxy.
- Ghi `@Async("beanNameOrQualifier")` ở listener cần chọn executor riêng.
- Đặt tiền tố tên luồng để chứng minh và giám sát pool được dùng.
- Kiểm thử cả trường hợp bình thường, quá tải, lỗi callback và shutdown.
- Xem xét transaction boundary, retry, idempotency và độ bền của công việc nếu có tác dụng phụ quan trọng.

**Ghi nhớ:** `@Qualifier` là định danh dùng để tìm bean executor; `@Async("qualifier")` là cơ chế cho một phương thức event listener lựa chọn executor đó. Dùng các pool riêng giúp cô lập loại công việc, nhưng độ tin cậy của xử lý bất đồng bộ còn phụ thuộc quản lý lỗi, transaction, khả năng tiếp nhận task và lưu trữ bền vững.

## Tài liệu chính thức

- [Spring Framework — Task Execution and Scheduling: Executor Qualification with @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ApplicationContext Events: Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc — @Async trong Spring 6.2](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
