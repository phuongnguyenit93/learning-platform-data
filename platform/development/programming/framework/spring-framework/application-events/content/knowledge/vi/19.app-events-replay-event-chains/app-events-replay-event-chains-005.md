# Không dựa vào return value trong `@Async` khi tạo chuỗi Spring Application Events

## 1. Bài toán: từ sự kiện A đến sự kiện B

Một quy trình xử lý đơn hàng thường được chia thành các sự kiện nghiệp vụ:

```text
OrderSubmitted -> OrderValidated -> InvoiceRequested -> InvoiceCreated
```

Trong Spring Framework, phương thức gắn `@EventListener` **đồng bộ** có thể trả về một object khác. Spring lấy kết quả đó và **phát thành Application Event mới**. Tuy nhiên, Spring Framework **không hỗ trợ tính năng phát event tiếp theo bằng return value với asynchronous event listener** (listener sử dụng `@Async` hoặc được gọi bất đồng bộ).

Vì thế, khi muốn một listener async tạo bước kế tiếp, hãy inject `ApplicationEventPublisher` và **chủ động gọi `publishEvent(...)` sau khi tác vụ cần thiết thành công**:

```java
@Async("eventExecutor")
@EventListener
public void onValidated(OrderValidated event) {
    // Hoàn thành phần việc cần thiết trước.
    publisher.publishEvent(new InvoiceRequested(event.orderId()));
}
```

Đây là mã minh họa, yêu cầu bean Spring có field `publisher` được inject, `@EnableAsync`, bean executor `eventExecutor`, cùng các kiểu event do ứng dụng định nghĩa.

**Phân biệt các khái niệm ngay từ đầu:**

| Khái niệm | Đúng nghĩa |
| --- | --- |
| `@EventListener` đồng bộ trả event | Spring có thể coi return value là event mới và publish tiếp |
| `@Async @EventListener` | Listener được xử lý bằng async execution; **không dùng return value để publish event mới** |
| `ApplicationEventPublisher.publishEvent(...)` | API công bố event, return type `void`; không trả kết quả của các listener cho caller |
| `Future`/`CompletableFuture` từ một service `@Async` | Cho phép **caller của method** theo dõi kết quả async; không tự biến kết quả thành Spring Application Event |
| Chaining | Bước A hoàn tất rồi tạo event B, có thể kéo dài thành chuỗi |
| Replay | Phát lại các event đã được lưu; Spring event publisher **không tự lưu lịch sử** |

Spring Application Events là cơ chế truyền thông điệp trong ứng dụng. Dữ liệu Java return, event chaining, thread async, transaction và replay là những cơ chế khác nhau, cần được thiết kế rõ ràng.

## 2. Spring tự phát event từ return value như thế nào?

Xét listener **đồng bộ** sau (mã minh họa, các record do ứng dụng định nghĩa):

```java
public record OrderSubmitted(String id) {}
public record OrderValidated(String id) {}
public record InvoiceRequested(String id) {}

@Component
public class ValidationListener {
    @EventListener
    public OrderValidated validate(OrderSubmitted event) {
        return new OrderValidated(event.id());
    }
}

@Component
public class BillingListener {
    @EventListener
    public InvoiceRequested prepare(OrderValidated event) {
        return new InvoiceRequested(event.id());
    }
}
```

Cần import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener` và các kiểu Spring tương ứng khi đặt code vào ứng dụng. Khi `OrderSubmitted` được publish và Spring đã đăng ký bean/listener:

```text
publishEvent(OrderSubmitted)
   |
   +-- ValidationListener.validate()
       |
       +-- return OrderValidated
           |
           +-- Spring publishEvent(OrderValidated)
               |
               +-- BillingListener.prepare()
                   |
                   +-- return InvoiceRequested
                       |
                       +-- Spring publishEvent(InvoiceRequested)
```

Đây là tính năng riêng của listener method, được mô tả trong Javadoc của `@EventListener` và tài liệu Spring Framework. Khi method đồng bộ trả một `Collection` hoặc mảng các event object, Spring có thể công bố **mỗi phần tử thành một event riêng**.

```java
@EventListener
public List<Object> onValidated(OrderValidated event) {
    return List.of(
            new InvoiceRequested(event.id()),
            new StockReservationRequested(event.id()));
}
```

Đây là mã minh họa; cần định nghĩa `StockReservationRequested` và import `java.util.List`. Với method trả `void` hoặc `null`, không có event tiếp theo được tạo **từ return value**.

**Cảnh báo:** `publishEvent(A)` vẫn là một lời gọi **`void`**. Caller không nhận `OrderValidated` làm kết quả phương thức. Framework sử dụng giá trị return **bên trong event dispatch**, không phải một giao thức request–response.

Cách return-event đồng bộ phù hợp với chuỗi ngắn, nhanh, không yêu cầu thread riêng. Một chuỗi quá dài có thể trở thành các lời gọi publish lồng nhau, làm tăng độ trễ và khiến ranh giới xử lý khó theo dõi.

## 3. Vì sao cơ chế return value không hoạt động với `@Async`?

Spring dùng `@EnableAsync` và async advice/proxy để đưa lời gọi `@Async` vào `Executor`. Caller có thể nhận lại quyền điều khiển **trước khi phần thân listener xử lý xong**:

```text
Thread publisher
  |
  +-- publishEvent(EventA)
       |
       +-- lời gọi tới bean proxy listener @Async
            |
            +-- submit task vào Executor
            |
            +-- trả điều khiển cho event dispatch
  |
  +-- caller tiếp tục làm việc

Worker thread
  |
  +-- listener @Async xử lý EventA
  +-- publishEvent(EventB) tường minh
```

Đường gọi này không có một event return thông thường sẵn có ở thời điểm dispatch. Spring nêu rõ trong phần **Asynchronous Listeners**: không hỗ trợ xuất bản event tiếp theo bằng **return value** của listener async; cần inject publisher và tự publish.

Đừng viết:

```java
@Async
@EventListener
public InvoiceRequested onValidated(OrderValidated event) {
    return new InvoiceRequested(event.id());
}
```

Đây là **phản ví dụ**. `@Async` method thông thường chỉ hỗ trợ `void` hoặc `Future` (bao gồm `CompletableFuture`) làm return type, chứ không phải một kiểu event bất kỳ. Trong cơ chế proxy, một method `@Async` return `InvoiceRequested` có thể phát sinh lỗi do kiểu return không hợp lệ; điều quan trọng là **không được kỳ vọng event được Spring tự phát ra**.

Cũng đừng đổi thành:

```java
@Async
@EventListener
public CompletableFuture<InvoiceRequested> onValidated(
        OrderValidated event) {
    return CompletableFuture.completedFuture(
            new InvoiceRequested(event.id()));
}
```

Đây **không phải** mẫu nối chuỗi event được Spring bảo đảm. `CompletableFuture` diễn đạt một giá trị hoàn thành của lời gọi async, **không tạo hợp đồng** rằng event infrastructure sẽ đợi future rồi publish nội dung của nó như một event mới.

Mẫu đúng với listener async:

```java
@Async("eventExecutor")
@EventListener
public void onValidated(OrderValidated event) {
    InvoiceRequested next = new InvoiceRequested(event.id());
    publisher.publishEvent(next);
}
```

`void` mô tả chính xác rằng listener không trả kết quả nghiệp vụ cho event dispatcher; bước phát sự kiện mới được **thể hiện rõ trong code**.

## 4. Ví dụ Java 17+ chạy được: một bước return đồng bộ và một bước publish async

Ví dụ dùng **Spring Framework 6.2.12**, JDK 17+, Gradle 8+. Không cần Spring Boot hay cơ sở dữ liệu.

Luồng được minh họa:

```text
JobSubmitted
    |
    +-- @EventListener đồng bộ
          return JobValidated
                |
                +-- @Async @EventListener
                      xử lý trên eventExecutor
                      gọi publisher.publishEvent(JobIndexed)
                           |
                           +-- @EventListener nhận JobIndexed
```

Ứng dụng kiểm tra bằng `CountDownLatch` và `AtomicReference` thay vì dùng `Thread.sleep()` hoặc dựa vào thứ tự log giữa các thread.

### 4.1. Cấu trúc dự án

```text
spring-event-chain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncEventChainDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-chain-demo'
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
    mainClass = 'demo.AsyncEventChainDemo'
}
```

### 4.2. `src/main/java/demo/AsyncEventChainDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncEventChainDemo {

    public record JobSubmitted(String jobId) {}

    public record JobValidated(String jobId) {}

    public record JobIndexed(String jobId) {}

    public static class ValidationListener {
        private final AtomicReference<String> validatedId =
                new AtomicReference<>();

        // Listener đồng bộ trả về event để Spring publish tiếp.
        @EventListener
        public JobValidated onSubmitted(JobSubmitted event) {
            validatedId.set(event.jobId());
            return new JobValidated(event.jobId());
        }

        public String validatedId() {
            return validatedId.get();
        }
    }

    public static class AsyncIndexingListener {
        private final ApplicationEventPublisher publisher;
        private final AtomicReference<String> threadName =
                new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);

        public AsyncIndexingListener(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        // Không return event: tự publish từ worker thread.
        @Async("eventExecutor")
        @EventListener
        public void onValidated(JobValidated event) {
            try {
                threadName.set(Thread.currentThread().getName());
                publisher.publishEvent(new JobIndexed(event.jobId()));
            } finally {
                finished.countDown();
            }
        }

        public boolean awaitFinished() throws InterruptedException {
            return finished.await(5, TimeUnit.SECONDS);
        }

        public String threadName() {
            return threadName.get();
        }
    }

    public static class IndexedObserver {
        private final AtomicReference<String> indexedId =
                new AtomicReference<>();
        private final CountDownLatch observed = new CountDownLatch(1);

        @EventListener
        public void onIndexed(JobIndexed event) {
            indexedId.set(event.jobId());
            observed.countDown();
        }

        public boolean awaitObserved() throws InterruptedException {
            return observed.await(5, TimeUnit.SECONDS);
        }

        public String indexedId() {
            return indexedId.get();
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
        ValidationListener validationListener() {
            return new ValidationListener();
        }

        @Bean
        AsyncIndexingListener asyncIndexingListener(
                ApplicationEventPublisher publisher) {
            return new AsyncIndexingListener(publisher);
        }

        @Bean
        IndexedObserver indexedObserver() {
            return new IndexedObserver();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ValidationListener validation =
                    context.getBean(ValidationListener.class);
            AsyncIndexingListener async =
                    context.getBean(AsyncIndexingListener.class);
            IndexedObserver indexed =
                    context.getBean(IndexedObserver.class);

            context.publishEvent(new JobSubmitted("J-42"));

            if (!async.awaitFinished()) {
                throw new IllegalStateException(
                        "Async event listener did not finish");
            }
            if (!indexed.awaitObserved()) {
                throw new IllegalStateException(
                        "Follow-up event was not observed");
            }

            System.out.println("sync returned event: "
                    + "J-42".equals(validation.validatedId()));
            System.out.println("async used executor: "
                    + async.threadName().startsWith("event-"));
            System.out.println("explicit follow-up received: "
                    + "J-42".equals(indexed.indexedId()));
        }
    }
}
```

### 4.3. Chạy và kiểm tra

Với JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng do ứng dụng in ra:

```text
sync returned event: true
async used executor: true
explicit follow-up received: true
```

Gradle hay Spring có thể in log khác tùy cấu hình. Ba dòng trên là kết quả kiểm tra trực tiếp bằng `System.out.println`, không phải toàn bộ terminal output.

**Phân tích:**

1. `AnnotationConfigApplicationContext` tạo các bean và xử lý các phương thức `@EventListener`. Spring cho phép publish Java record như một payload event mà không bắt buộc record kế thừa `ApplicationEvent`.
2. Khi `JobSubmitted("J-42")` được publish, listener `ValidationListener.onSubmitted` đồng bộ trả `JobValidated`. Spring tự phát event mới từ return value đó.
3. Lời gọi `AsyncIndexingListener.onValidated` đi qua Spring bean proxy nhờ `@EnableAsync`; async interceptor submit phần thân method vào `eventExecutor`.
4. Worker thread có tiền tố `event-` chạy phương thức `void` và **chủ động phát `JobIndexed`**. Đó là điểm duy nhất trong listener async tạo event kế tiếp.
5. `IndexedObserver` là listener thường. Khi nó nhận `JobIndexed` phát trong worker thread, listener này có thể thực thi **trên chính thread worker** theo multicaster đồng bộ mặc định.
6. `CountDownLatch` bảo đảm hai bước async và nhận event cuối đã hoàn tất trước khi in kết quả. `AtomicReference` giúp quan sát giá trị an toàn giữa các thread. Chương trình **không suy luận** từ thứ tự chạy ngẫu nhiên giữa publisher và executor.
7. Không có `@Async` trên phương thức của `IndexedObserver`, nên event cuối không tự động được đưa sang một executor khác. Muốn đổi điều đó phải cấu hình rõ ràng.

Đây là ví dụ một lần chạy với một job. Nếu xử lý nhiều job, mỗi job cần cơ chế hoàn thành và correlation riêng; không nên dùng chung một latch cố định cho toàn bộ traffic production.

## 5. `CompletableFuture` hữu ích nhưng không tự biến thành event chain

Một method service được gọi qua async proxy có thể trả về `Future<T>` hoặc `CompletableFuture<T>`:

```java
@Async("eventExecutor")
public CompletableFuture<IndexResult> buildIndex(String jobId) {
    IndexResult result = index(jobId);
    return CompletableFuture.completedFuture(result);
}
```

Đây là **đoạn minh họa**; cần bean Spring khác chứa method, `IndexResult` và `index(...)` do ứng dụng định nghĩa, `@EnableAsync` và executor hợp lệ. Caller nhận future của lời gọi qua proxy và có thể phối hợp với `thenAccept`, `whenComplete` hoặc `join`.

Nếu muốn tạo event kế tiếp sau khi service async thành công, có thể để một listener đồng bộ kích hoạt service rồi gắn callback **chủ động publish**:

```java
@EventListener
public void onValidated(JobValidated event) {
    indexService.buildIndex(event.jobId())
            .thenAccept(result ->
                    publisher.publishEvent(
                            new JobIndexed(result.jobId())))
            .exceptionally(error -> {
                recordFailure(event.jobId(), error);
                return null;
            });
}
```

Đây là **mã minh họa**, không phải chương trình độc lập: `indexService` là bean có method async, `publisher` được inject, `JobIndexed`/`IndexResult` đã được định nghĩa và `recordFailure(...)` do ứng dụng triển khai.

Điều cần phân biệt:

- Phương thức `onValidated` nhận event, **trả `void`**, không dùng return-value chaining.
- `buildIndex` là một **service method async**, không phải cơ chế trả event của `@EventListener`.
- Callback `thenAccept` **tường minh** gọi `publisher.publishEvent(...)`. Nếu service thất bại, callback thành công không chạy.
- Callback của `CompletableFuture` có thể chạy trên thread hoàn tất future; nếu muốn executor riêng cho bước callback, dùng `thenAcceptAsync(..., executor)`.
- `exceptionally` phải có logic thực sự theo dõi lỗi, retry hoặc đưa vào dead-letter path; chỉ log rồi nuốt lỗi có thể làm tác vụ mất.
- Cách này vẫn là **in-memory processing**, không tự bền vững qua crash.

Không thiết kế `@Async @EventListener` trả `CompletableFuture<NextEvent>` rồi mặc định chờ Spring unwrap future để publish `NextEvent`. Tài liệu Framework không bảo đảm hành vi đó.

## 6. Khi nào event mới được xem là đã xảy ra?

Một event nên phản ánh **mốc nghiệp vụ thực sự đạt được**, không chỉ một task đã được enqueue. Nếu event `ImageReady` được phát ngay sau khi submit việc resize ảnh, nhưng ảnh vẫn chưa tạo xong, consumer có thể bắt đầu dùng một tài nguyên chưa tồn tại.

Đường xử lý an toàn hơn:

```text
ImageUploaded
    |
    +-- @Async resizeImage()
         |
         +-- file resize thành công / dữ liệu đã lưu
                |
                +-- publisher.publishEvent(ImageReady)
                        |
                        +-- listener gửi notification
```

Phát event mới **sau khi** side effect liên quan thành công. Nếu xử lý thất bại, đừng phát một event có tên “đã thành công”. Có thể phát `ImageProcessingFailed` theo một policy lỗi rõ ràng hoặc ghi failure state để retry.

Nếu dùng future như mục 5, sự kiện B cần được phát trong callback hoàn thành thành công, không ở ngay sau lúc gọi service async:

```java
CompletableFuture<IndexResult> future =
        indexService.buildIndex(event.jobId());

// Sai ý nghĩa nếu gọi publish ngay ở đây khi index chưa xong.
// Đúng: publish bên trong callback hoàn tất thành công.
future.thenAccept(result ->
        publisher.publishEvent(new JobIndexed(result.jobId())));
```

Mã trên là minh họa cho thời điểm phát, không phải class đầy đủ. Mục tiêu không phải **dùng hay không dùng return value nói chung**: `CompletableFuture` có thể là kết quả hữu ích của service. Điều phải tránh là **dựa vào return của async event listener để Spring tự nối chuỗi event**.

## 7. Đừng dựa vào thứ tự hoàn thành của nhiều listener async

Nếu một event A có hai listener:

```java
@Async("eventExecutor")
@EventListener
public void generateReport(ReportRequested event) {
    // Tạo file báo cáo.
}

@Async("eventExecutor")
@EventListener
public void sendReportEmail(ReportRequested event) {
    // Không được giả định file báo cáo đã tồn tại.
}
```

Đây là mã minh họa. Hai listener có thể chạy trên hai thread khác nhau. `@Order` (nếu cấu hình) có thể liên quan tới **thứ tự gọi/submit**, nhưng không biến các tác vụ async thành một chuỗi hoàn thành tuần tự.

Nếu email phải đi sau khi file báo cáo đã được tạo, thiết kế theo **sự kiện kết quả**:

```text
ReportRequested
    |
    +-- async generate report
           |
           +-- publish ReportGenerated
                  |
                  +-- send email
```

`ReportGenerated` có ý nghĩa rằng bước trước đã hoàn thành. Một chain có nhiều listener async cần thêm correlation (`requestId`, `eventId`, `aggregateId`), thứ tự theo business key và idempotency. Không coi “event được publish trước” nghĩa là “mọi handler của nó đã xử lý xong trước”.

## 8. Exception trong listener async không trả về publisher

Với listener đồng bộ mặc định, exception có thể lan theo stack gọi `publishEvent()` tùy multicaster/error handler. Nhưng một exception xảy ra trong **worker thread** của listener `@Async void` **không tự được gửi lại publisher thread**.

Spring có `AsyncUncaughtExceptionHandler` để xử lý uncaught exception của async method `void`:

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, parameters) ->
                System.err.println(
                        "Async failed: " + method.getName()
                                + " / " + error.getMessage());
    }
}
```

Đây là đoạn minh họa, cần import `Configuration`, `EnableAsync`, `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`. Trong production hãy dùng structured logging, metrics, alert và cơ chế retry/compensation thật sự.

Các trường hợp lỗi:

| Vị trí lỗi | Hệ quả có thể xảy ra | Cách theo dõi |
| --- | --- | --- |
| Listener đồng bộ ném runtime exception | Có thể làm publisher nhận exception | Error handler và test kết quả publish |
| Async listener `void` ném exception khi chạy task | Publisher có thể đã trả về bình thường; event B chưa được phát | `AsyncUncaughtExceptionHandler`, logs, metrics, retry |
| Executor từ chối nhận task | Lỗi có thể xảy ra lúc dispatch/submit | Cấu hình queue/rejection policy, capacity monitoring |
| B được publish nhưng consumer B lỗi | Chain tổng thể chưa hoàn tất dù bước A xong | Quan sát từng stage và state |
| Process chết trước khi A publish B | Event B có thể mất | Persisted work / transactional outbox |
| Retry khiến B được publish nhiều lần | Side effect trùng | Dedupe bằng `eventId`, idempotency |

**`publishEvent(A)` trả về không chứng minh listener async A đã thành công**. Tương tự, một `CompletableFuture` hoàn tất ở service A không chứng minh listener của event B đã xử lý xong, trừ khi chương trình có cơ chế hoàn tất rõ ràng.

## 9. Proxy `@Async` và self-invocation

Trong chế độ mặc định, `@EnableAsync` áp dụng async interceptor thông qua Spring proxy. Nếu một bean gọi method async **của chính nó** bằng `this`, cuộc gọi sẽ bỏ qua proxy và không được tự động đưa vào executor.

```java
@Service
public class WorkflowWorker {

    public void start(JobValidated event) {
        this.processAsync(event); // Self-invocation: bỏ qua proxy.
    }

    @Async("eventExecutor")
    public void processAsync(JobValidated event) {
        // Có thể chạy đồng bộ khi gọi theo cách trên.
    }
}
```

Đây là mã minh họa, cần import `Service`, `Async`, các event type và executor. Giải pháp dễ hiểu là tách method async sang **Spring-managed bean khác** và inject bean đó, hoặc dùng `@Async @EventListener` để event infrastructure gọi qua bean proxy phù hợp như ví dụ runnable mục 4.

Hai khái niệm độc lập:

1. Proxy phải có hiệu lực để `@Async` thật sự đổi thread.
2. **Dù proxy hoạt động đúng, return value event chaining vẫn không được hỗ trợ cho async listener.**

Không thể sửa quy tắc số 2 chỉ bằng cách thay đổi executor hoặc cấu hình class-based proxy.

## 10. Transaction, commit và event tiếp theo

Giả sử service phát event A trong một transaction:

```java
@Transactional
public void submitOrder(String id) {
    orderRepository.save(createOrder(id));
    publisher.publishEvent(new OrderSubmitted(id));
}
```

Đây là đoạn minh họa, với `orderRepository` và `createOrder(...)` do ứng dụng định nghĩa. Nếu listener A là `@Async @EventListener`, worker thread có thể bắt đầu xử lý **trước khi transaction publisher commit**. Sau đó transaction publisher có thể rollback, trong khi listener đã phát B hoặc gửi email.

Các hệ quả cần tránh:

- Worker thread không tự mang theo JDBC/JPA transaction của thread publisher.
- Listener async đọc DB có thể chưa nhìn thấy record chưa commit.
- Event B có thể được phát trước khi dữ liệu A được lưu bền vững.
- JPA entity/lazy proxy truyền vào async event có thể phụ thuộc persistence context đã hết hiệu lực.
- Exception của listener async không tự rollback transaction gốc.

Nếu B **chỉ nên có sau khi A commit**, hãy cân nhắc:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    publisher.publishEvent(new OrderValidated(event.id()));
}
```

Đây là minh họa, cần `@EnableAsync`, executor, Spring-managed bean và các import transaction-event. Với transaction imperative đang hoạt động, `@TransactionalEventListener` đăng ký callback cho pha `AFTER_COMMIT`. Khi commit thành công, callback kích hoạt lời gọi listener; phần việc async có thể publish B tường minh.

Lưu ý:

- `AFTER_COMMIT` xác định **thời điểm**, không tạo retry hay persistence cho event.
- Worker thread không tự thừa hưởng transaction gốc. Nếu cần ghi DB từ worker, hãy mở transaction mới theo ranh giới service phù hợp.
- Nếu B được phát khi worker thread **không có transaction**, một `@TransactionalEventListener` theo B mặc định có thể không được gọi vì không có transaction để gắn callback. Nếu B phải gắn commit của bước mới, phát B **bên trong** transaction mới đó.
- Nếu process chết sau khi transaction của A commit nhưng trước khi B được phát, chuỗi có thể bị mất bước. Khi yêu cầu bền vững, cần outbox/queue.

### Transactional outbox

Với quy trình quan trọng, nên cân nhắc:

```text
Transaction T1
  +-- cập nhật đơn hàng
  +-- ghi outbox event A
  +-- COMMIT
        |
        +-- outbox worker đọc A đã commit
              +-- xử lý bước A
              +-- lưu kết quả / outbox event B
              +-- commit bước riêng
                    |
                    +-- broker/worker tiếp tục event B
```

Outbox giúp công việc cần xử lý tiếp **được lưu cùng thay đổi nghiệp vụ**, nhưng không tự bảo đảm exactly-once. Consumer vẫn cần idempotency, retry/backoff, trạng thái và quan sát lỗi.

## 11. Chaining không phải replay

Trong nhóm **Phát lại và chuỗi event**, cần phân biệt:

- **Chaining:** A dẫn tới B, B dẫn tới C khi từng bước hoàn tất.
- **Republishing:** listener chủ động gửi tiếp một event, có thể cùng loại hoặc loại mới.
- **Replay:** phát lại event đã được **lưu bền vững** từ event store, broker có retention, outbox hoặc nguồn lưu khác.

`ApplicationEventPublisher` tiêu chuẩn không lưu lịch sử event, không tạo queue bền vững và không tự replay sau restart. Đổi sang `@Async` cũng không biến event thành một thông điệp persistent.

Nếu phải xử lý lại một event cũ:

1. Event phải được lưu cùng payload đủ để tái lập ý nghĩa nghiệp vụ.
2. Có `eventId` hoặc khóa dedupe để tránh side effect trùng.
3. Có version/sequence và chính sách xử lý khi event cũ đến sau event mới.
4. Phân biệt **retry bước A** với **phát event B mới** để không sinh bão sự kiện.
5. Có trạng thái xử lý, metrics, backoff, dead-letter/compensation và chính sách recovery.

Một return value của listener đồng bộ chỉ tiện cho **dispatch trong bộ nhớ**, không thay thế những yêu cầu trên.

## 12. Tránh chu kỳ vô hạn và bão event

Một listener đồng bộ trả về event cùng loại có thể gọi lại chính listener đó:

```java
@EventListener
public SameEvent onSameEvent(SameEvent event) {
    return event;
}
```

Đây là **phản ví dụ**; `SameEvent` là event do ứng dụng định nghĩa. Khi không có điều kiện dừng, một event có thể tạo ra chuỗi lồng nhau vô tận và dẫn đến lỗi stack/deep recursion.

Với async listener tự publish event cùng loại, một vòng lặp tương tự có thể tạo ra **bão task trên executor**, queue đầy, memory tăng hoặc làm tắc thread pool. Dù không dùng return value, cycle vẫn tồn tại nếu thiết kế state machine sai.

Các biện pháp:

- Dùng tên event là **mốc nghiệp vụ đã xảy ra**: `ImageProcessed`, `InvoiceIssued`, thay vì luôn dùng `SomethingChanged`.
- Định nghĩa bước chuyển state hợp lệ và điều kiện dừng.
- Có correlation ID, `eventId`, `parentEventId`, số hop/TTL và giới hạn retry.
- Xử lý trùng an toàn theo idempotency key.
- Kiểm soát queue capacity, thread pool, timeout và rejection policy.
- Đưa quy trình dài/phức tạp sang workflow engine hoặc một orchestrator có trạng thái khi phù hợp.

## 13. Checklist kiểm thử

Các test có giá trị:

1. **Listener đồng bộ trả event:** phát A, xác minh listener B nhận đúng event do method A return.
2. **Async explicit publish:** phát A, để listener A async tự publish B, chờ B bằng latch/future/Awaitility có timeout.
3. **Không dùng sleep để đoán:** tránh `Thread.sleep(50)` vì dễ flake trên CI.
4. **Không có return chaining trong async:** xem xét chữ ký method; không đặt kỳ vọng event B được publish từ return của `@Async @EventListener`.
5. **Async exception:** gây lỗi trước khi B được publish, xác minh B không xuất hiện và failure được ghi nhận.
6. **Executor rejection:** bão hòa pool/queue trong test kiểm soát; xác minh error policy.
7. **Ordering:** phát nhiều event, kiểm tra B có thể hoàn tất khác thứ tự A; dùng sequencing nếu nghiệp vụ cần.
8. **Rollback:** phát A trong transaction rồi rollback; listener `AFTER_COMMIT` không được phát B.
9. **Trùng lặp/replay:** phát lại A, kiểm tra idempotency và tránh B bị xử lý hai lần.
10. **Shutdown:** dừng context khi còn task; kiểm tra pool và cách bảo đảm không mất việc bắt buộc.

### Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Listener `@Async` trả B nhưng B không xuất hiện | Async return-value chaining không được hỗ trợ | Đổi listener thành `void`, chủ động `publisher.publishEvent(B)` |
| `@Async` method trả object event thường và lỗi khi gọi | Return type không thuộc `void`/`Future` | Đúng chữ ký `@Async`; dùng publisher để phát event |
| `CompletableFuture<B>` xong nhưng B không được publish | Future result không tự biến thành Application Event | Tự đăng ký callback `thenAccept` gọi publisher |
| `publishEvent(A)` xong nhưng B chưa có | Listener A chạy trên executor | Chờ completion/event B với cơ chế rõ ràng |
| Listener vẫn chạy trên caller thread | Thiếu `@EnableAsync`, không qua proxy hoặc self-invocation | Sửa bean/proxy/executor, tách bean |
| B được phát trước commit của A | Async listener chạy khi T1 còn mở | Dùng `AFTER_COMMIT` hoặc outbox theo yêu cầu |
| Exception worker không tới publisher | Exception xảy ra ở thread khác | Async exception handler, logs/metrics |
| Event B lặp lại nhiều lần | Retry, duplicate delivery, cycle | `eventId`, idempotency, state machine |
| B đến không đúng thứ tự | Nhiều worker thread, không bảo đảm completion order | Version/order theo aggregate key |
| Crash làm mất event tiếp theo | Chỉ dùng event trong bộ nhớ | Persisted queue/outbox/worker |

## 14. Nguyên tắc áp dụng

Để xây dựng chuỗi Spring Application Events:

- **Listener đồng bộ, chuỗi ngắn:** có thể return event mới; đó là tính năng hợp lệ của `@EventListener`.
- **Listener `@Async`:** luôn xem việc phát event tiếp theo là **hành động rõ ràng**, gọi `ApplicationEventPublisher.publishEvent(...)` sau khi công việc liên quan đã thành công.
- **Service `@Async` trả `CompletableFuture`:** dùng future để phối hợp và quan sát kết quả cho caller, rồi **tự publish** trong callback nếu cần; không nhầm với return value của listener.
- **Cần A đã commit trước B:** `AFTER_COMMIT`/outbox, không phát B từ một transaction chưa chắc thành công.
- **Cần bảo đảm xử lý qua crash:** persistent outbox, queue/broker hoặc workflow engine, cùng retry và idempotency.
- **Cần thứ tự hoặc tránh vòng lặp:** thiết kế state machine, event ID, aggregate version và giới hạn số bước.

**Kết luận:** `@Async` điều khiển nơi công việc được thực thi, không phải một cơ chế “trả event mới cho Spring”. Để nối chuỗi một cách đúng nghĩa và dễ kiểm thử, hãy publish event tiếp theo **tường minh** từ listener async, đồng thời thiết kế lỗi, thứ tự, transaction và độ bền theo yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework 6.2 — `@EventListener`, return value và asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — `@Async` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — AOP proxying và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
