# Giới hạn chuyển listener sang bất đồng bộ khi cần bảo đảm thứ tự — Spring Boot 3.3

## 1. Mục tiêu và thông điệp chính

Trong Spring Boot, `ApplicationEventPublisher` cho phép một thành phần phát event và nhiều listener phản ứng với event đó. Mặc định, với `SimpleApplicationEventMulticaster` không được cấu hình executor khác, listener được gọi **đồng bộ trong thread của bên phát event**. Có thể sử dụng `@Async` hoặc một `TaskExecutor` để xử lý event bất đồng bộ, nhưng bước chuyển này làm thay đổi quan trọng về **thứ tự, thời điểm hoàn tất, exception, transaction và startup readiness**.

**Trọng tâm:** `@Order(10)` trước `@Order(20)` có thể kiểm soát **thứ tự gọi/dispatch các listener trong một cơ chế hỗ trợ ordering**, nhưng **không bảo đảm listener thứ nhất đã xử lý xong trước listener thứ hai** khi công việc được chuyển sang thread khác. Nếu bước B thật sự cần kết quả đã được commit từ bước A, phải diễn đạt quan hệ phụ thuộc và điều phối hoàn tất một cách tường minh — không chỉ thêm annotation `@Order`.

Sau bài này bạn sẽ:

- Phân biệt **thứ tự phát event**, **thứ tự gọi listener**, **thứ tự bắt đầu xử lý**, **thứ tự hoàn thành** và **thứ tự commit**.
- Hiểu `@EventListener`, `ApplicationListener`, `@Order`, `@Async`, `@EnableAsync`, `SimpleApplicationEventMulticaster` và `TaskExecutor`.
- Phân tích vì sao event listener đồng bộ thường có thứ tự dễ dự đoán hơn, còn async có thể chạy song song, kết thúc ngược thứ tự, làm thay đổi cách báo lỗi.
- Hiểu các ngoại lệ liên quan `TransactionalApplicationListener`, `@TransactionalEventListener`, bootstrap events và readiness.
- Chạy ví dụ Java 21 / Spring Boot 3.3 với đồng bộ, bất đồng bộ và `CountDownLatch` để kiểm chứng bằng quan sát có kiểm soát, thay vì suy luận từ log ngẫu nhiên.
- Biết dùng pipeline tuần tự, future composition, outbox hoặc queue có bảo đảm ordering khi bài toán nghiệp vụ đòi hỏi.

## 2. Mặc định event listener hoạt động thế nào?

### 2.1. Luồng xử lý đồng bộ

Một publisher gọi:

```java
publisher.publishEvent(new PaymentAccepted("payment-123"));
```

Nếu các listener phù hợp đang được xử lý đồng bộ, luồng khái niệm là:

```text
Thread xử lý nghiệp vụ
  |
  +-- publishEvent(PaymentAccepted)
        |
        +-- listener A (order = 10)
        |     +-- làm việc A
        |     +-- A trả về bình thường
        |
        +-- listener B (order = 20)
        |     +-- làm việc B
        |     +-- B trả về bình thường
        |
        +-- publishEvent(...) trả về
  |
  +-- Câu lệnh tiếp theo của publisher
```

Trường hợp này **listener A đã hoàn thành việc xử lý đồng bộ của nó** trước khi container gọi listener B. `publishEvent` cũng chỉ trả về sau khi mọi synchronous listener có liên quan hoàn tất thành công, trừ khi có lỗi khiến quá trình gọi bị ngắt.

Phát biểu trên có điều kiện quan trọng: các callback phải **thật sự đồng bộ**, dùng multicaster mặc định hoặc executor đồng bộ, listener A không chỉ giao việc cho thread khác rồi trả về, và đang xét **một lượt publish trong một thread**. Nếu nhiều publisher đồng thời, nhiều application contexts, nested events, hoặc listener tự tạo async task, thứ tự tổng quát cần phân tích riêng.

### 2.2. Bốn loại “thứ tự” khác nhau

| Khái niệm | Câu hỏi | `@Order` đủ hay chưa? |
| --- | --- | --- |
| **Dispatch order** | Multicaster chọn/gọi A trước B? | Có thể hỗ trợ qua `@Order` / `Ordered` |
| **Start order** | Code nghiệp vụ A thật sự bắt đầu chạy trước code B? | Không được bảo đảm khi executor có nhiều thread |
| **Completion order** | A xử lý xong, cập nhật tài nguyên xong rồi B mới kết thúc? | Không bảo đảm bởi `@Order` khi async |
| **Commit / durability order** | Transaction của A commit bền vững trước B đọc dữ liệu? | Cần ràng buộc transaction, lưu trữ và protocol riêng |

Chính vì bốn ý nghĩa khác nhau này, lời nói “đã có `@Order` nên các listener chạy đúng thứ tự” là thiếu chính xác. Phải nói rõ **đúng thứ tự nào** và **trong điều kiện nào**.

### 2.3. `@Order` hoạt động ở đâu?

Ví dụ khai báo hai listener đồng bộ:

```java
@Component
class PaymentListeners {

    @EventListener
    @Order(10)
    public void reserveInventory(PaymentAccepted event) {
        // Xử lý dự trữ hàng.
    }

    @EventListener
    @Order(20)
    public void sendConfirmation(PaymentAccepted event) {
        // Xử lý thông báo.
    }
}
```

Đây là **đoạn minh họa**, cần định nghĩa `PaymentAccepted` và imports `@Component`, `@EventListener`, `@Order`. Với synchronous multicaster, cùng một event và không có lỗi, listener order 10 được gọi trước order 20. Nhưng thiết kế “send confirmation” phụ thuộc vào “reserve inventory” thông qua thứ tự event listener vẫn có thể gây liên kết ngầm; trong nghiệp vụ quan trọng, nên có một service điều phối rõ ràng và một trạng thái giao dịch kiểm chứng được.

Với cùng order value hoặc các listener không gắn order, đừng mặc định thứ tự dựa vào tên class, file hoặc thời điểm component scan.

## 3. Chuyển sang bất đồng bộ làm thay đổi điều gì?

### 3.1. `@Async` trên `@EventListener`

Khi một listener dùng `@Async`, lời gọi tới listener có thể được Spring proxy chuyển sang executor khác:

```java
@Component
class NotificationListener {

    @Async("eventExecutor")
    @EventListener
    @Order(20)
    public void notifyCustomer(PaymentAccepted event) {
        // Được thực thi bởi eventExecutor khi @EnableAsync có hiệu lực.
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Cần `@EnableAsync` và bean `Executor` có tên `eventExecutor`. `@Async` thường hoạt động qua Spring proxy, do đó self-invocation (một phương thức tự gọi phương thức `@Async` trong cùng object) không kích hoạt async advice như lời gọi đi qua proxy.

Ở async setup:

```text
Thread publish:
  publishEvent(event)
    +-- gửi tác vụ listener A vào executor
    +-- gửi tác vụ listener B vào executor
  return

Thread executor-1: listener A ──────────────── hoàn tất
Thread executor-2:      listener B ─── hoàn tất
```

Có thể B bắt đầu và kết thúc **trước khi A hoàn tất**, dù A có `@Order(10)` và B có `@Order(20)`. Tùy scheduling, ngay cả việc B bắt đầu trước A cũng có thể xảy ra. `@Order` lúc này chỉ tham gia **thứ tự dispatch/enqueue phù hợp với multicaster**, không phải một phép `join()` giữa hai task.

Không suy luận “`publishEvent` trả về” thành “listener đã hoàn thành”. Đồng thời, **không bảo đảm** publisher luôn trả về thành công khi dispatch sang executor: executor bị shutdown, quá tải hoặc từ chối task có thể phát sinh `TaskRejectedException` ngay lúc submit.

### 3.2. Executor ở cấp ApplicationEventMulticaster

Spring Framework có thể cấu hình `SimpleApplicationEventMulticaster` với `setTaskExecutor(...)`. Mặc định, nếu không chỉ định executor async, listeners chạy trong thread của publisher. Khi gắn executor async, **nhiều listener đủ điều kiện** được chuyển sang executor; ảnh hưởng có thể lan rộng tới nhiều event/listener trong context.

Cần phân biệt:

- **`@Async` trên một listener**: bất đồng bộ hóa đường thực thi của phương thức listener được Spring AOP intercept; các listener khác không tự bị chuyển sang async chỉ vì một listener có `@Async`.
- **Executor trên `applicationEventMulticaster`**: lựa chọn async ở **cấp multicaster**, có thể thay đổi hành vi của một tập listener rộng hơn, kể cả các event framework phát trong context.
- **Tự gọi executor/CompletableFuture trong listener**: listener có thể trả về sớm dù bản thân callback vẫn được multicaster gọi đồng bộ; một lớp async khác đã được tạo bên trong.

Tránh vô tình áp dụng hai lớp async (multicaster async cộng `@Async` trên method) khi không thực sự cần: việc submit qua nhiều executor càng khiến ordering, error handling và shutdown khó quan sát.

### 3.3. `ApplicationListener.supportsAsyncExecution()` từ Spring 6.1

Không phải **mọi** listener đều có thể chuyển sang thread khác bằng cấu hình multicaster. Trong Spring Framework 6.1, `ApplicationListener` có phương thức `supportsAsyncExecution()`. Listener trả `false` phải được gọi trong thread publisher, dù multicaster được cấu hình async.

Trường hợp quan trọng: **`TransactionalApplicationListener`** (cơ sở của cơ chế transactional event listening) không hỗ trợ để toàn bộ bước đăng ký transaction synchronization bị dời sang executor tùy ý. Phần callback **đích** xử lý sau transaction vẫn có thể có logic async theo cấu hình riêng, nhưng bước tương tác với transaction gốc phải đúng thread context.

Ví dụ listener cần giữ invocation đồng bộ:

```java
public final class StrictListener implements ApplicationListener<DomainEvent> {

    @Override
    public boolean supportsAsyncExecution() {
        return false;
    }

    @Override
    public void onApplicationEvent(DomainEvent event) {
        // Callback phải được multicaster gọi trên thread publisher.
    }
}
```

Đây là **minh họa** với `DomainEvent` là subclass của `ApplicationEvent`; cần imports `org.springframework.context.ApplicationListener` và định nghĩa event class. Phương thức trên áp dụng cho listener instance triển khai interface trong Spring 6.1. **Nó không tự biến tất cả listener khác thành đồng bộ**, và cũng không ngăn code bên trong listener tự tạo task async.

### 3.4. Tác dụng lên startup và readiness

Spring Boot phát các event như `ApplicationStartedEvent`, `ApplicationReadyEvent` trong vòng đời `SpringApplication.run(...)`. Nếu một ready listener chỉ **giao việc async** rồi trả về, Boot có thể hoàn thành startup mà công việc đó vẫn còn chạy.

Không được hiểu:

```text
ApplicationReadyEvent published
    => mọi async listener đã kết thúc
    => cache/broker/external API đã sẵn sàng
```

Các suy luận này không đúng. Nếu một bước bắt buộc phải hoàn tất **trước ready**, hãy dùng runner hoặc startup coordinator với completion/timeout rõ ràng; chỉ xử lý bằng async listener rồi hy vọng `@Order` là không đủ.

**Lưu ý với bootstrap events:** một số event đầu tiên của Spring Boot được phát **trước khi `ApplicationContext` tồn tại**. Bean `applicationEventMulticaster` do context quản lý không thay thế toàn bộ cơ chế phát sớm đó. Early listeners phải được đăng ký theo cơ chế của `SpringApplication` (chẳng hạn `addListeners` hoặc metadata phù hợp), không phải chỉ gắn `@Component` và mong bắt được `ApplicationStartingEvent`.

## 4. Bảo đảm gì khi listener vẫn đồng bộ?

Nếu hai listeners dùng cùng event, mặc định multicaster đồng bộ, có order khác nhau, không nested publish, và không tự tạo bất đồng bộ, có thể kỳ vọng:

1. Spring chọn listener A (order 10) trước B (order 20).
2. A được gọi rồi hoàn tất bình thường.
3. B được gọi rồi hoàn tất bình thường.
4. Lời gọi `publishEvent(...)` trả về.

Đây là bảo đảm **trong một lần gọi publish**, không phải serial hóa tất cả publisher threads.

### 4.1. Concurrent publishers

Nếu hai HTTP requests đồng thời gọi `publishEvent(event1)` và `publishEvent(event2)`, mỗi request có thể chạy listeners của event nó trên thread riêng. Vì vậy:

```text
Request-1: A(event1) -> B(event1)
Request-2: A(event2) -> B(event2)
```

Hai chuỗi **có thể xen kẽ** trên các thread. Synchronous multicaster không phải global event queue có một thứ tự duy nhất cho tất cả requests.

### 4.2. Nested event publication

Nếu listener A khi xử lý event X lại gọi `publishEvent(eventY)` đồng bộ, listeners của Y có thể chạy **trước khi A xử lý xong X**. Bởi vậy cấu trúc callback có thể lồng nhau:

```text
publish(X)
  A(X) bắt đầu
    publish(Y)
      C(Y)
    publish(Y) trả về
  A(X) kết thúc
  B(X)
```

`@Order` của X không phải thứ tự tổng thể giữa mọi callback của X và Y.

### 4.3. Thread context khi chuyển async

Khi callback được chuyển thread, các dữ liệu thread-local thường không tự đi theo:

- Transaction đang gắn với thread publisher.
- Security context tùy môi trường/cách cấu hình.
- MDC/tracing correlation IDs nếu không có context propagation.
- Request-scoped data, locale, class-loader hoặc resources gắn thread.
- Các lock hoặc ThreadLocal state mà business code ngầm sử dụng.

Một `TaskDecorator` hoặc context-propagating executor có thể giúp truyền **một số** context phù hợp, nhưng **không nên** copy trực tiếp transaction thread-local sang worker để giả vờ đó là cùng transaction. Với tác vụ async, cần thiết kế ranh giới transaction riêng và trao đổi dữ liệu qua payload bất biến/ID.

## 5. Ví dụ hoàn chỉnh — Java 21 và Spring Boot 3.3.13

Chương trình minh họa hai cơ chế trong **cùng một ứng dụng non-web**:

- **SyncSignal:** hai `@EventListener` đồng bộ có `@Order(10)` và `@Order(20)`. `publishEvent` trả về sau khi cả hai đã xử lý.
- **AsyncSignal:** hai listener `@Async("eventExecutor")` cũng có `@Order` nhưng chạy trên thread pool có **2 worker**. Listener thứ nhất được giữ lại bằng `CountDownLatch`, listener thứ hai có thể hoàn thành trước. Chương trình **chủ động phối hợp bằng latch có timeout** để chứng minh vấn đề thay vì dựa vào `Thread.sleep(...)`.
- **Ready event:** mốc Boot phát khi `ApplicationRunner` hoàn tất, không được dùng làm bằng chứng cho những async tasks chưa được chờ.

### 5.1. Cấu trúc dự án

```text
listener-order-demo/
├── pom.xml
└── src/main/java/com/example/listeners/
    ├── ListenerOrderApplication.java
    ├── Signals.java
    ├── AsyncConfiguration.java
    ├── SyncHandlers.java
    ├── AsyncHandlers.java
    ├── DemoRunner.java
    └── ReadyObserver.java
```

### 5.2. Maven

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>listener-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 sử dụng Spring Framework 6.1 và tương thích JDK 21. Ví dụ chỉ cần starter cơ bản, không có database hay web server.

### 5.3. Định nghĩa hai payload events

Tệp `src/main/java/com/example/listeners/Signals.java`:

```java
package com.example.listeners;

record SyncSignal(String id) {
}

record AsyncSignal(String id) {
}
```

Hai `record` là **package-private**, hợp lệ khi đặt chung một file `Signals.java`. Đây là payload objects, không cần extends `ApplicationEvent`: Spring có thể nhận object truyền qua `publishEvent(Object)` và bọc nó trong `PayloadApplicationEvent` khi cần. Listener có thể khai báo trực tiếp tham số record type.

### 5.4. Lớp main

Tệp `src/main/java/com/example/listeners/ListenerOrderApplication.java`:

```java
package com.example.listeners;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ListenerOrderApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ListenerOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // Đóng context sau khi runner kết thúc để executor được cleanup.
        try (ConfigurableApplicationContext context = app.run(args)) {
            // Không cần gọi publish ở đây: DemoRunner sẽ thực hiện.
        }
    }
}
```

Ứng dụng không mở cổng HTTP. `ApplicationRunner` được Boot gọi khi `app.run(args)` diễn ra; `try-with-resources` đóng context sau khi `run` trả về.

### 5.5. Cấu hình executor cho @Async

Tệp `src/main/java/com/example/listeners/AsyncConfiguration.java`:

```java
package com.example.listeners;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {

    @Bean("eventExecutor")
    public ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
```

`@EnableAsync` bật Spring's async method interception. Executor có **2 worker**, vì vậy hai listeners có khả năng xử lý song song. Queue capacity 16 giới hạn các tác vụ đang chờ; trong production cần định nghĩa thêm rejection policy, metrics, saturation handling và timeout phù hợp thay vì dùng một pool không giới hạn.

**Không nhầm:** bean executor có tên `eventExecutor` **không tự biến tất cả event listeners thành async**. Demo chỉ chuyển các phương thức có `@Async("eventExecutor")` sang executor. `SyncHandlers` vẫn xử lý đồng bộ.

### 5.6. Hai listeners đồng bộ có thứ tự

Tệp `src/main/java/com/example/listeners/SyncHandlers.java`:

```java
package com.example.listeners;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class SyncHandlers {

    @EventListener
    @Order(10)
    public void first(SyncSignal event) {
        System.out.println("SYNC first");
    }

    @EventListener
    @Order(20)
    public void second(SyncSignal event) {
        System.out.println("SYNC second");
    }
}
```

`SyncHandlers` **không có `@Async`**, và demo không tùy biến global multicaster. Vì thế khi `SyncSignal` được publish từ runner, callback được thực thi trong thread của publisher, theo thứ tự `@Order`.

### 5.7. Hai listeners async và latches để chứng minh đảo thứ tự hoàn tất

Tệp `src/main/java/com/example/listeners/AsyncHandlers.java`:

```java
package com.example.listeners;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AsyncHandlers {

    private final CountDownLatch firstEntered = new CountDownLatch(1);
    private final CountDownLatch allowFirstToFinish = new CountDownLatch(1);
    private final CountDownLatch firstFinished = new CountDownLatch(1);
    private final CountDownLatch secondFinished = new CountDownLatch(1);

    @Async("eventExecutor")
    @EventListener
    @Order(10)
    public void first(AsyncSignal event) {
        firstEntered.countDown();

        try {
            if (!allowFirstToFinish.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("first handler timed out");
            }
            System.out.println("ASYNC first finished");
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("first handler interrupted", ex);
        }
        finally {
            firstFinished.countDown();
        }
    }

    @Async("eventExecutor")
    @EventListener
    @Order(20)
    public void second(AsyncSignal event) {
        System.out.println("ASYNC second finished");
        secondFinished.countDown();
    }

    public void verifyAndRelease() throws InterruptedException {
        // Chờ cả việc first bắt đầu và second đã hoàn thành.
        boolean firstStarted = firstEntered.await(10, TimeUnit.SECONDS);

        try {
            if (!firstStarted || !secondFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("async listeners not scheduled");
            }

            if (firstFinished.getCount() != 1) {
                throw new IllegalStateException("first already finished unexpectedly");
            }

            System.out.println("CHECK: second completed while first waits");
        }
        finally {
            // Giải phóng first ngay cả khi kiểm tra thất bại.
            allowFirstToFinish.countDown();
        }

        if (!firstFinished.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("first did not finish");
        }
    }
}
```

Hai phương thức `first` và `second` là `public`, được gọi thông qua Spring bean proxy, không phải self-invocation. Vì executor có hai threads, `second` có thể kết thúc trong khi `first` đang chờ latch. `verifyAndRelease()` đợi và kiểm tra bằng timeout, nên demo không chỉ dựa vào thời gian ngủ không xác định.

Lưu ý: `@Async` với return type `void` không tự chuyển exception của listener về thread gọi `publishEvent`; production phải có `AsyncUncaughtExceptionHandler`, logging, monitoring và chính sách retry hoặc failure phù hợp. Demo chỉ dùng latch để chứng minh ordering trong happy path, không phải một thư viện đồng bộ cho production.

### 5.8. Runner phát cả sync và async events

Tệp `src/main/java/com/example/listeners/DemoRunner.java`:

```java
package com.example.listeners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class DemoRunner implements ApplicationRunner {

    private final ApplicationEventPublisher publisher;
    private final AsyncHandlers asyncHandlers;

    public DemoRunner(
            ApplicationEventPublisher publisher,
            AsyncHandlers asyncHandlers) {
        this.publisher = publisher;
        this.asyncHandlers = asyncHandlers;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("SYNC publish");
        publisher.publishEvent(new SyncSignal("demo"));
        System.out.println("SYNC returned");

        System.out.println("ASYNC publish");
        publisher.publishEvent(new AsyncSignal("demo"));
        System.out.println("ASYNC returned");

        asyncHandlers.verifyAndRelease();
        System.out.println("RUNNER finished");
    }
}
```

`DemoRunner` được gọi sau khi context refresh. Nó cố ý **đợi async handlers bằng latch trước khi trả về**, nên `RUNNER finished` và ready event chỉ xuất hiện sau khi first và second kết thúc **trong ví dụ này**. Nếu bỏ lời gọi `verifyAndRelease()`, sự kiện ready có thể được phát trong lúc listener async chưa xử lý xong.

### 5.9. Quan sát ApplicationReadyEvent

Tệp `src/main/java/com/example/listeners/ReadyObserver.java`:

```java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyObserver {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("BOOT ready");
    }
}
```

Listener này **đồng bộ** và chỉ in sau khi Boot đã gọi xong runner. Nếu runner không chờ async tasks, `BOOT ready` **không chứng minh** những task ấy đã hoàn tất. Cách làm đúng phải xuất phát từ chính sách readiness và điều kiện cần đạt.

### 5.10. Lệnh chạy

Cài JDK 21 và Maven; từ thư mục `listener-order-demo`:

```bash
java -version
mvn -version
mvn package
java -jar target/listener-order-demo-0.0.1-SNAPSHOT.jar
```

Có thể thay `mvn package` và chạy JAR bằng `mvn spring-boot:run`. Log thực tế còn banner và thông báo Spring Boot; dưới đây là **những dòng do ví dụ in**, không phải stdout đầy đủ.

**Thứ tự đồng bộ được xác định:**

```text
SYNC publish
SYNC first
SYNC second
SYNC returned
```

**Các quan hệ có kiểm soát trong phần async:**

- `ASYNC publish` có trước lời gọi `publishEvent(new AsyncSignal(...))`.
- `ASYNC returned` được in sau khi lời gọi publish đã submit callbacks, **không có nghĩa hai callbacks đã kết thúc**.
- Dòng `ASYNC second finished` xuất hiện trước `CHECK: second completed while first waits`.
- Dòng `CHECK: second completed while first waits` xuất hiện trước `ASYNC first finished`, vì runner chỉ giải phóng latch sau khi in dòng kiểm tra.
- `ASYNC first finished` xuất hiện trước `RUNNER finished`.
- `RUNNER finished` xuất hiện trước `BOOT ready`, do runner hoàn thành trước `ApplicationReadyEvent`.

**Không cam kết một thứ tự stdout tuyệt đối** giữa `ASYNC returned` với `ASYNC second finished`: các threads có thể được scheduling khác nhau. Cũng không dùng việc `first` có `@Order(10)` để suy luận `first` sẽ **hoàn tất** trước `second` có `@Order(20)` — demo cố ý cho thấy điều ngược lại.

Nếu bạn chuyển executor xuống một thread, hai async callbacks có thể bị tuần tự hóa trong cùng executor, nhưng đây là một đặc tính cục bộ của queue/worker, không tự trở thành bảo đảm transaction order, global order giữa nhiều publisher, hoặc giữa nhiều service instances.

## 6. Hai cách bật async và hệ quả về phạm vi

### 6.1. Cách nên ưu tiên khi chỉ một listener được phép async

Dùng `@EnableAsync`, một executor có capacity giới hạn và `@Async("eventExecutor")` trên **chính phương thức listener** mà bạn muốn làm nền. Không cần thay đổi `applicationEventMulticaster` của toàn context.

Điều này giảm rủi ro vô tình chuyển các framework listeners, startup events hoặc transactional listeners sang thread khác. Tuy nhiên, listener async vẫn cần quản lý exception, context propagation, retry và shutdown.

### 6.2. Cách cấu hình global multicaster: cân nhắc kỹ

**Đoạn sau là lựa chọn thay thế, không đưa chung vào demo mục 5**, vì nó thay đổi ngữ nghĩa của toàn bộ event multicaster trong context:

```java
@Configuration(proxyBeanMethods = false)
class GlobalEventMulticasterConfig {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster eventMulticaster(
            @Qualifier("eventExecutor") java.util.concurrent.Executor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
```

Để dùng, cần import `@Configuration`, `@Bean`, `@Qualifier` và `org.springframework.context.event.SimpleApplicationEventMulticaster`, cùng bean `eventExecutor` hợp lệ. Đây là **đoạn bổ sung trong ứng dụng Spring**, không chạy độc lập.

Các lưu ý:

- Tên bean phải là **`applicationEventMulticaster`**, theo quy ước của `AbstractApplicationContext`.
- Multicaster có executor có thể dispatch các listener đủ điều kiện bất đồng bộ **trong toàn context**, không chỉ domain event của bạn.
- Listener có `supportsAsyncExecution() == false` vẫn phải được invoke trong thread publisher.
- Các event được phát rất sớm trước khi context tồn tại không thể mặc định chịu tác động của bean multicaster được tạo trong context.
- Exception xử lý trong worker có thể không truyền lại publisher; có thể cấu hình `setErrorHandler(...)` để logging/suppress/propagate theo yêu cầu, nhưng error handler **không phải** cơ chế rollback transaction gốc.
- Thay đổi global multicaster có thể ảnh hưởng startup, shutdown và listener của thư viện khác. Chỉ bật khi đã kiểm kê các listener mà ứng dụng **thật sự** sử dụng và có test phù hợp.

### 6.3. Dùng executor một thread có giải quyết toàn bộ bài toán thứ tự không?

**Không.** Single-thread executor có thể chạy **những task được đưa vào đúng queue đó** một cách tuần tự theo chính sách executor, nhưng không bảo đảm:

- Tất cả event trong ứng dụng đều đi qua queue ấy.
- Sự kiện được publish từ nhiều thread sẽ có thứ tự nghiệp vụ tuyệt đối.
- Listener đồng bộ và transactional listener đều chạy trên worker đó.
- Sự kiện ở process khác hay Kafka/RabbitMQ partition khác cùng thứ tự.
- Cập nhật dữ liệu của A đã được commit trước khi B đọc.
- Việc retry, timeout, shutdown, task rejection không làm thay đổi quan sát.

Single-thread executor còn có nguy cơ bottleneck, backlog và head-of-line blocking. Nó có thể là công cụ triển khai phù hợp trong một phạm vi hẹp, nhưng không thay thế hợp đồng dữ liệu hoặc một state machine có thứ tự.

## 7. Transaction và @TransactionalEventListener: giới hạn quan trọng

### 7.1. Event có thể được phát bên trong transaction

Giả sử:

```java
@Transactional
public void acceptPayment(String id) {
    repository.markPaid(id);
    publisher.publishEvent(new PaymentAccepted(id));
}
```

Đây là **minh họa kiến trúc**, không phải chương trình độc lập; cần repository và event. `publishEvent` chạy **trong lời gọi method có transaction**, nhưng thời điểm callback được xử lý phụ thuộc vào loại listener.

- Listener đồng bộ `@EventListener` thường chạy trong thread publisher và có thể thấy transaction đang active.
- Listener `@Async` chạy trên thread khác không tự kế thừa transaction thread-local; nó có thể đọc dữ liệu trước khi transaction của publisher commit.
- Listener `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` đăng ký callback gắn với transaction; xử lý được kích hoạt sau khi transaction commit thành công theo phase đã chọn.

**Không dùng `@Order` để bảo đảm listener async thấy dữ liệu đã commit.** Đây là bài toán ranh giới transaction và tính nhất quán dữ liệu, không phải một vấn đề thứ tự callback đơn thuần.

### 7.2. `@TransactionalEventListener` và multicaster async

Spring Framework 6.1 quy định transactional listener **không cho multicaster chuyển phần transaction-synchronization registration ra thread khác**: `TransactionalApplicationListener.supportsAsyncExecution()` trả `false`. Khi transaction hoàn tất, target callback mới được xử lý theo phase.

Điều này **không có nghĩa** mọi target callback của `@TransactionalEventListener` mãi mãi không thể async: nếu dùng async proxy trên phương thức xử lý sau commit, phần công việc đích có thể chạy bất đồng bộ. Khi đó lại phải cân nhắc thread context, exception handling, completion order và dữ liệu sau commit.

Một event được publish ngoài transaction có thể không kích hoạt transactional listener nếu không bật fallback execution phù hợp. Không dùng transactional listeners như một cách thay thế thiếu suy xét cho startup/domain event thông thường.

### 7.3. Khi công việc không được phép mất

Một listener in-memory async không phải một durable queue. Nếu JVM chết sau khi publisher đã commit DB nhưng trước khi async task xử lý xong, tác vụ có thể bị mất.

Với công việc có yêu cầu không mất và cần đúng thứ tự theo một business key, cân nhắc:

1. **Transactional outbox**: ghi trạng thái nghiệp vụ và bản ghi event/outbox trong cùng database transaction.
2. Một worker/publisher riêng đẩy event vào broker hoặc xử lý theo cơ chế có replay.
3. **Ordering theo key** (ví dụ `orderId` hoặc `customerId`) qua partition hoặc serialized workflow phù hợp; không hứa global ordering giữa mọi key.
4. Consumer **idempotent**, quản lý retries, duplicate và trạng thái đã xử lý.
5. Theo dõi độ trễ, backlog, poison messages và dead-letter policy.

Đây là một **kiến trúc bổ sung cho bài toán nghiệp vụ phân tán**, không phải tính năng tự xuất hiện khi thêm `@Async` hoặc `@Order`.

## 8. Khi cần bảo đảm A hoàn thành trước B, nên thiết kế ra sao?

### 8.1. Nếu A và B thuộc cùng một nghiệp vụ và phải tuần tự: gọi tường minh

Thay vì hai listener độc lập cùng nhận một event và phụ thuộc thứ tự:

```java
public void handleBusinessFlow(PaymentAccepted event) {
    inventoryService.reserve(event.paymentId());
    confirmationService.sendAfterReservation(event.paymentId());
}
```

Đây là **đoạn minh họa**; cần có `PaymentAccepted` record với `paymentId()`, các service tương ứng, handling transaction, timeout và chính sách gửi thông báo. Cách này làm rõ “send confirmation phụ thuộc reserve thành công” và dễ đặt trong workflow/service. Không dựa vào hai listener đang vô tình có order 10/20.

### 8.2. Nếu muốn async nhưng vẫn bắt buộc A xong trước B: compose future

Ví dụ Java 21:

```java
CompletableFuture<Void> flow =
        CompletableFuture.runAsync(() -> reserveInventory(paymentId), executor)
                .thenRunAsync(() -> sendConfirmation(paymentId), executor);

flow.orTimeout(10, TimeUnit.SECONDS).join();
```

Đây là **đoạn minh họa, không độc lập**; cần imports `CompletableFuture`, `TimeUnit`, biến `executor`, `paymentId` và hai methods. `thenRunAsync` chỉ chạy sau khi stage đầu thành công. `join()` chờ completion (hoặc ném exception), có timeout bằng `orTimeout`.

Nếu không muốn chặn request thread, **không gọi `join()` tại đó**; hãy trả future hoặc để một workflow/worker quản lý completion và báo trạng thái. `CompletableFuture.allOf(A, B)` chỉ đợi cả hai hoàn thành, **không** bắt B đợi A. `thenCompose` dùng khi stage A trả về một future mới cần ghép tiếp.

**Chú ý:** việc A đã hoàn thành về mặt `CompletableFuture` chưa chắc transaction của A đã commit nếu bạn tự hoàn thành future quá sớm. Đảm bảo completion signal phản ánh đúng transaction/protocol hoàn tất mà B cần.

### 8.3. Nếu chỉ muốn order các listener đồng bộ

Nếu listeners thật sự độc lập nhưng cần thứ tự callback để log/audit nhẹ, có thể dùng synchronous `@EventListener` + `@Order`. Giữ callback nhanh, có timeout cho I/O, và đo thời gian xử lý vì nó chặn thread của publisher.

Nếu kết quả B phụ thuộc sâu vào A, một orchestrator hoặc dependency rõ ràng vẫn dễ maintain hơn.

### 8.4. Nếu cần bảo đảm thứ tự giữa nhiều JVM/service

Sắp xếp listener trong **một** `ApplicationContext` không có ý nghĩa ràng buộc trên các node khác. Dùng queue/stream có ordering theo business key, state machine, sequence number, outbox/transaction log và consumer idempotency. Cần nêu rõ mong muốn là per-key FIFO, causal order, hay total order; những yêu cầu đó có chi phí và ranh giới khác nhau.

## 9. Exception, cancellation, timeout và shutdown

### 9.1. Đồng bộ: exception thường quay về publisher

Với `SimpleApplicationEventMulticaster` mặc định và không cấu hình error handler nuốt lỗi, exception runtime từ một listener đồng bộ có thể lan về publisher và làm gián đoạn multicasting. Nếu `publishEvent` được gọi từ startup code, nó có thể làm startup thất bại; nếu được gọi trong transaction, tác động rollback phụ thuộc loại exception và transaction configuration.

Không dùng việc listener làm thất bại transaction làm cơ chế bảo đảm “event exactly once”. Cần phân biệt transaction của DB với side effect ngoài DB.

### 9.2. Async: exception không còn theo cùng đường

Với `@Async` method trả `void`, exception thường không truyền trực tiếp về publisher; có thể được xử lý bằng `AsyncUncaughtExceptionHandler`. Với executor đặt trên multicaster, `setErrorHandler` hoặc executor's error handling quyết định cách ghi nhận lỗi. Trong cả hai trường hợp, publisher có thể đã đi tiếp hoặc trả response thành công.

Do đó phải có:

- Logging gắn event ID và trace ID.
- Metrics/số lượng thành công/thất bại.
- Chính sách retry hữu hạn, delay/backoff, deduplication.
- Xử lý task rejection hoặc pool saturation.
- Bảo đảm payload đủ dữ liệu để xử lý an toàn sau khi thread publisher đã kết thúc.
- Policy shutdown/drain nếu không muốn mất tác vụ nền.

### 9.3. Thứ tự dưới retry

A có thể fail và retry muộn hơn, trong khi B đã thành công. Nếu mục tiêu là “không xử lý B trước A thành công”, không thể chỉ xếp hàng theo `@Order`. Cần một workflow state (PENDING_A, A_DONE, B_DONE), queue có khóa, hoặc explicit acknowledgment từ A trước khi giải phóng B.

### 9.4. Shutdown và event late

Trong quá trình đóng context, executor có thể ngừng nhận task mới. Nếu listener publish/submit vào pool đang shutdown, task có thể bị từ chối. Đừng giả định mọi event ở shutdown đều được xử lý xong; dùng lifecycle management và stop/drain protocol phù hợp, đặc biệt với consumer hay job quan trọng.

## 10. Những sai lầm thường gặp

| Nhận định/cách làm | Vì sao sai hoặc thiếu | Thay thế |
| --- | --- | --- |
| `@Async` + `@Order(1)` và `@Order(2)` bảo đảm thứ tự hoàn tất | Executor có thể chạy song song, task chậm kết thúc muộn | Compose futures hoặc workflow tuần tự |
| `publishEvent` trả về là xong hết công việc | Async listener thường chỉ mới được submit | Theo dõi future/ack/state hoặc đợi completion có giới hạn |
| Tăng priority/order để giải quyết read-before-commit | Transaction và thread context không theo `@Order` | AFTER_COMMIT/outbox hoặc transaction boundary tường minh |
| Đổi multicaster toàn cục để giảm latency mà không kiểm thử | Ảnh hưởng nhiều listeners và sự kiện khác | Ưu tiên async chọn lọc; kiểm thử startup/transaction |
| Đặt executor một thread rồi tuyên bố có total ordering toàn hệ thống | Chỉ tuần tự hóa queue cục bộ | Xác định key/partition/protocol ở tầng durable |
| Trong listener `@Async`, return đối tượng để tự phát event tiếp | Async listener method không dùng return value để publish tiếp | Inject `ApplicationEventPublisher` và phát tường minh |
| `@TransactionalEventListener` sẽ bị multicaster async đẩy khỏi transaction gốc | Bước đăng ký transactional synchronization phải chạy trong publisher thread | Hiểu `supportsAsyncExecution() == false` |
| Listener mới gắn `@Component` sẽ bắt bootstrap event trước tạo context | Bean listener chưa tồn tại ở mốc sớm | Đăng ký qua `SpringApplication.addListeners` nếu cần |
| Event async thừa hưởng transaction, MDC, request scope | Thread-local không tự đi qua executor | Payload bất biến, context propagation có chủ đích |
| Tăng số threads là giải quyết mọi lỗi event | Tạo race, backlog, contention, lỗi trùng dữ liệu | Bounded concurrency, idempotency, ordering theo nhu cầu |
| Có `ApplicationReadyEvent` tức mọi async listener đều xong | Ready theo startup lifecycle không `join` các listener async | Runner/coordinator chờ task thiết yếu |
| Test dùng `Thread.sleep(100)` rồi kết luận đúng thứ tự | Scheduling khác nhau theo máy và tải | Latches/barriers/future completion và assertions |

## 11. Checklist quyết định dùng đồng bộ hay bất đồng bộ

**Giữ đồng bộ** khi tất cả các điều kiện sau phù hợp: callback ngắn, chi phí thấp, cần phản hồi lỗi ngay cho publisher, thứ tự callback trong một lần publish là yêu cầu có chủ đích, không có I/O lâu, và không gây cản trở tuyến xử lý request/startup.

**Dùng async** khi công việc có thể chạy độc lập, publisher không cần biết completion ngay, có chính sách khi task thất bại, dữ liệu đủ để xử lý ngoài thread/transaction, executor có giới hạn và giám sát, không cần dựa vào thứ tự hoàn tất giữa các listeners.

**Cần orchestration thay vì chỉ event ordering** khi B phải xảy ra sau A được commit, có retry hoặc failure độc lập, kết quả phải tồn tại qua restart, cần ordering giữa nhiều requests/instances, hoặc cần bảo đảm trước readiness. Khi đó, dùng service coordinator, future chain, transaction/outbox, message queue với key/partition hoặc state machine tùy nhu cầu.

### Câu hỏi tự kiểm

1. Cần đảm bảo “A được gọi trước B” hay “A đã commit thành công trước khi B bắt đầu”?
2. Đang xét một event hay nhiều event publish đồng thời?
3. Có listener nào tự submit task background dù multicaster mặc định đồng bộ?
4. Có `@Transactional`, MDC, SecurityContext, request scope hay ThreadLocal cần xử lý?
5. Khi A thất bại, B có được chạy không? Ai quyết định và báo lỗi về đâu?
6. Nếu ứng dụng restart giữa hai bước, trạng thái nào giúp tiếp tục an toàn?
7. Nếu executor bị bão hòa, event có thể bị từ chối hay có backpressure?
8. Nếu đây là bước startup thiết yếu, ai đợi completion trước `ApplicationReadyEvent`?

## 12. Bài tập thực hành

1. Giải thích bốn khái niệm dispatch, start, completion và commit order. `@Order` tác động trực tiếp đến khái niệm nào?
2. Chạy demo Maven và chỉ ra phần stdout **bắt buộc theo thứ tự** với `SyncSignal`.
3. Vì sao `ASYNC second finished` có thể xuất hiện trước `ASYNC first finished` dù annotation lần lượt là `@Order(20)` và `@Order(10)`?
4. Vì sao demo dùng `CountDownLatch` và timeout thay vì cố tạo race bằng `Thread.sleep(500)`?
5. Bỏ lệnh `asyncHandlers.verifyAndRelease()` trong runner. Dự đoán thứ tự tương đối của `BOOT ready` với các dòng async; vì sao không có bảo đảm hoàn tất?
6. Thay `setCorePoolSize(2)` bằng 1. Giải thích thay đổi hành vi và tại sao test dùng latch có thể timeout khi worker đầu tiên bị chặn. Sau thí nghiệm, khôi phục hai workers.
7. Nếu A và B là hai HTTP requests publish event đồng thời với synchronous multicaster, có được đảm bảo mọi callback của request A trước request B không?
8. Đổi `@Async` trên hai handlers thành đồng bộ. Dự đoán tác dụng của `@Order` và khả năng deadlock trong demo dùng latch.
9. Tạo một listener triển khai `ApplicationListener` với `supportsAsyncExecution()` trả `false`. Cơ chế multicaster async đối xử với nó thế nào?
10. Vì sao `@TransactionalEventListener` cần đăng ký transaction synchronization trên publisher thread?
11. Nếu listener A ghi DB trong transaction của publisher, listener B `@Async` có chắc đọc thấy dữ liệu đó không?
12. Sửa flow nghiệp vụ bằng `thenRunAsync` để chỉ chạy B sau A thành công; bổ sung timeout, logging và chính sách retry phù hợp.
13. Dùng `CompletableFuture.allOf(A, B)` có ép thứ tự A trước B không? Vì sao?
14. Với event xử lý hóa đơn quan trọng, tại sao cần outbox, idempotency và ordering theo `invoiceId` thay cho `@Order` trên listeners local?
15. Nêu ba lý do executor một thread vẫn không tạo được ordering tuyệt đối cho hệ thống phân tán.
16. Viết một startup runner chờ cache warm-up hoàn tất và ném exception khi timeout, để tránh báo ready giả.

**Tiêu chí đạt:** hiểu rõ các giới hạn khi chuyển listener sang async, không đồng nhất `@Order` với thứ tự hoàn tất hoặc commit, biết cách cấu hình executor có kiểm soát và thiết kế một workflow thực sự đáp ứng yêu cầu ordering.

## 13. Tài liệu chính thức

- Spring Framework 6.1 — `SimpleApplicationEventMulticaster` (executor, error handler, sync default, async support): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.1 — `@EventListener` (async limitations, ordering): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.1 — `TransactionalApplicationListener`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
- Spring Framework — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Task Execution and `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Boot 3.3 — Application events and listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
