# Exception bị xử lý bởi executor trong Spring Application Events

## 1. Vấn đề thực tế: publisher thành công nhưng listener đã lỗi

Khi xử lý Spring Application Events bất đồng bộ, một triệu chứng dễ đánh lừa người vận hành là:

- Code gọi `applicationEventPublisher.publishEvent(event)` chạy hết mà **không nhận exception**.
- Một `@EventListener` đã ném `IllegalStateException` hoặc lỗi truy cập dịch vụ ngoài.
- Log lỗi xuất hiện ở thread của executor, không phải thread xử lý request.
- Trạng thái HTTP hoặc kết quả của publisher vẫn có vẻ thành công.
- Một số listener khác vẫn chạy; một số tác vụ hậu xử lý bị thiếu.

Điều này có thể là **hành vi đúng theo cơ chế truyền exception qua ranh giới thread**, chứ chưa chắc do Spring “nuốt” lỗi.

Ví dụ: người dùng đặt đơn hàng, `OrderPlaced` được publish và listener gửi email chạy trong executor. Nếu email listener ném exception **sau khi task đã được executor chấp nhận**, thread gọi publish thường không thể bắt lỗi đó bằng `try/catch` quanh `publishEvent`. Lỗi phải được quan sát tại **task/listener/executor boundary** thông qua `ErrorHandler`, `Future`, `AsyncUncaughtExceptionHandler` hoặc cơ chế giám sát phù hợp.

**Phân biệt trước tiên:** “Exception bị xử lý bởi executor” có thể chỉ một trong nhiều đường lỗi. Cần xác định **lỗi phát sinh ở bước submit task**, **trong listener đã chạy**, **trong wrapper/decorator** hay **sau khi Future hoàn thành thất bại**.

> **Kết luận cốt lõi:** publisher không ném exception không chứng minh listener thành công. Ngược lại, exception ở listener không luôn có nghĩa transaction của publisher rollback. Phải xác định cơ chế dispatch, handler và ranh giới giao dịch cụ thể.

## 2. Sơ đồ hai tuyến xử lý sự kiện

### 2.1. Mặc định: đồng bộ trên thread phát

Trong Spring Framework, `SimpleApplicationEventMulticaster` mặc định xử lý listener trên calling thread:

```text
HTTP/request thread
  |
  +-- OrderService.placeOrder(...)
       |
       +-- publishEvent(OrderPlaced)
            |
            +-- Listener A thực thi ngay
                 |
                 +-- throws IllegalStateException
                      |
                      v
             exception lan về publishEvent
            |
            X  Listener tiếp theo có thể không được gọi
```

Nếu multicaster **không cấu hình `ErrorHandler`** và một listener đồng bộ ném unchecked exception, publisher thường thấy exception và lời gọi publish bị gián đoạn.

### 2.2. Có executor: listener được submit thành task

```text
Publisher thread                      Worker thread
----------------                      ----------------
publishEvent(OrderPlaced)
  |
  +-- executor.execute(task A) ------> listener A
  |                                       |
  |                                       +-- throws
  |                                             |
  |                                             +--> multicaster ErrorHandler?
  |                                             |       |
  |                                             |       +--> log/suppress/rethrow
  |                                             |
  |                                             +--> executor/UncaughtExceptionHandler
  |                                                  nếu lỗi tiếp tục thoát khỏi task
  |
  +-- executor.execute(task B) ------> listener B
  |
  +-- publishEvent returns
```

Việc submit thành công thường chỉ cho biết **executor đã nhận tác vụ**; nó không phải một acknowledgement rằng listener đã hoàn tất. Với lỗi xảy ra trong worker sau đó, `try/catch` trên publisher thread không thể “đi xuyên” ngược về thread đó.

**Cảnh báo về thứ tự:** executor có thể chạy task A trước, trong hoặc sau khi publisher tiếp tục. Không được viết test dựa trên một thứ tự log cố định nếu chưa có latch hoặc điều kiện đồng bộ.

## 3. Xác định lỗi ở tầng nào

| Vị trí phát sinh | Ví dụ | Ai có thể nhận thấy trực tiếp? | Công cụ chẩn đoán |
| --- | --- | --- | --- |
| **Publisher trước khi dispatch** | Validation trong service ném lỗi | Thread publisher | `try/catch` của caller, transaction test |
| **Executor từ chối submit** | Queue đã đầy, executor đã shutdown | Thread gọi `execute/submit`, trừ cơ chế fallback/rejection riêng | `RejectedExecutionException`/`TaskRejectedException`, queue metrics |
| **Trong listener đồng bộ** | `@EventListener` ném lỗi | Thường publisher nếu không suppress | Stack trace từ `publishEvent`, multicaster `ErrorHandler` |
| **Trong listener được executor chạy** | Service ngoài timeout sau khi task được nhận | Worker/executor hoặc `ErrorHandler` ở task | Error handler, logs, async probe |
| **Trong `@Async void`** | Async-intercepted listener ném lỗi | `AsyncUncaughtExceptionHandler` của `@Async` | Handler của annotation-driven async |
| **Trong `Future/CompletableFuture`** | Task hoàn thành exceptionally | Caller đọc Future hoặc completion callback | `get()`, `join()`, `whenComplete` |
| **Trong `TaskDecorator`/task wrapper** | Context restoration lỗi | Wrapper/executor boundary | Decorator logging, task instrumentation |
| **Sau commit/transport khác** | Relay gửi broker thất bại | Relay/consumer riêng | Outbox, retry, dead-letter monitoring |

Không gộp tất cả thành “executor đã bắt lỗi”. Một `FutureTask` có thể **lưu exception để chờ `Future.get()`**; một `ErrorHandler` có thể **ghi log rồi suppress**; một `Thread.UncaughtExceptionHandler` có thể chỉ thấy lỗi **không được bắt** trên thread. Ba trường hợp có kết quả rất khác nhau.

## 4. Cấu hình thực sự quyết định đường exception

Cơ chế mặc định của Spring Application Events:

- Không khai báo task executor riêng: `SimpleApplicationEventMulticaster` gọi listeners đồng bộ.
- Gán executor vào multicaster: các listener hỗ trợ async execution được submit qua `Executor.execute(...)`.
- Tùy `ApplicationListener.supportsAsyncExecution()`, một số listener không được phép chạy async qua multicaster và vẫn được gọi trên publisher thread, ví dụ loại transaction-synchronized listener.
- `SimpleApplicationEventMulticaster.setErrorHandler(...)` xác định chính sách xử lý **lỗi do listener ném ra**.
- `@Async` là cơ chế AOP/annotation-driven async **riêng**, không giống hoàn toàn với gán executor cho multicaster.
- Một custom multicaster có thể thực hiện logic khác; đừng suy đoán từ tên thread nếu chưa biết implementation.

### 4.1. Cấu hình Spring context

Khi muốn listeners bình thường dùng executor:

```java
@Configuration(proxyBeanMethods = false)
class EventConfiguration {

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error -> {
            // Ghi exception thật, đo metric và thực thi chính sách lỗi.
            logger.error("Application event listener failed", error);
        });
        return multicaster;
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("domain-event-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.initialize();
        return executor;
    }
}
```

Đây là **cấu hình minh họa**: cần imports cho Spring annotations, `SimpleApplicationEventMulticaster`, `ThreadPoolTaskExecutor` và logger được định nghĩa trong class. Không phải project chạy độc lập của phần 8. Trong một project thật, cân nhắc để lifecycle Spring quản lý executor qua bean, tránh tự shutdown một executor còn task.

Khai báo bean với tên **`applicationEventMulticaster`** là cách Spring context nhận diện multicaster tùy biến. Chỉ tạo một bean `ThreadPoolTaskExecutor` tùy ý chưa đủ để bảo đảm toàn bộ event listeners sẽ được chạy bằng executor đó.

### 4.2. Lưu ý với listener không hỗ trợ async

Từ Spring Framework 6.1, `ApplicationListener.supportsAsyncExecution()` cho biết listener có thể được gọi async bởi multicaster hay không. Các `TransactionalApplicationListener` không phù hợp với async dispatch trực tiếp của multicaster để bảo toàn cơ chế transaction synchronization.

Vì thế, **cùng một multicaster có executor** vẫn có thể có listener thực thi trên publisher thread. Lỗi của nhóm này có thể lan về publisher nếu handler rethrow/không được cấu hình, khác với lỗi trong task chạy trên pool.

Không khẳng định “chỉ cần setTaskExecutor thì mọi `@TransactionalEventListener` đều chạy trên worker thread”.

## 5. ErrorHandler của multicaster: điểm quan sát quan trọng nhất

`org.springframework.util.ErrorHandler` là interface có phương thức:

```java
void handleError(Throwable t);
```

`SimpleApplicationEventMulticaster.setErrorHandler(...)` dùng handler này khi **listener ném ra `Throwable`**. Luồng khái quát:

```text
invokeListener(listener, event)
   |
   +-- try: gọi listener
   |
   +-- catch Throwable:
          |
          +-- ErrorHandler.handleError(error)
                 |
                 +-- handler trả về bình thường
                 |      -> lỗi listener bị suppress tại đây
                 |
                 +-- handler lại ném exception
                        -> lỗi thoát khỏi task hoặc publisher thread,
                           tùy dispatch thực tế
```

Với handler chỉ ghi log rồi return, publisher thường không nhận exception, và worker task kết thúc **theo quan điểm của executor** mà không còn lỗi ném ra. Điều đó **không làm lại thao tác thất bại**; nó chỉ thay đổi cách lỗi được báo ra ngoài.

### 5.1. LOG_AND_SUPPRESS so với LOG_AND_PROPAGATE

Spring có các tiện ích `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` trong package `org.springframework.scheduling.support`. Chúng biểu diễn hai chính sách phổ biến:

| Chính sách | Hành động | Hệ quả |
| --- | --- | --- |
| **Log + suppress** | Ghi lỗi; không ném lại | Task có thể được xem là completed bình thường; các nơi chỉ theo dõi uncaught exception có thể không thấy lỗi |
| **Log + propagate** | Ghi lỗi; ném lại | Với sync, caller có thể nhận lỗi; với async, exception tiếp tục ra executor/task boundary |
| **Custom handler** | Log/metric/alert/record status, có thể rethrow hoặc không | Phải định nghĩa rõ cách xử lý và bảo đảm idempotency của side effect |
| **Không handler** | Không chặn exception ở multicaster | Sync có thể truyền về publisher; async thoát ra worker/task theo executor |

Các handler kiểu `ErrorHandler` có thể nhận cả `Error`, không chỉ `Exception`. Đừng tùy tiện suppress những lỗi JVM nghiêm trọng như `OutOfMemoryError`; custom error policy phải phân biệt lỗi có thể phục hồi và lỗi không an toàn để tiếp tục.

### 5.2. Một ErrorHandler dùng cho nhiều listener

Ví dụ:

```java
multicaster.setErrorHandler(error -> {
    failureCounter.incrementAndGet();
    logger.error("Event listener failure", error);
});
```

Đây là **đoạn minh họa**, cần biến `multicaster`, `failureCounter` và `logger` được định nghĩa trong ứng dụng. Handler nhận một `Throwable` nhưng **không tự động biết event ID, listener method hay tenant** nào gây lỗi. Nếu cần metadata, có thể:

- Đưa event ID/correlation ID vào logging/tracing context đúng cách.
- Bọc business listener bằng một adapter có tên operation và event metadata.
- Ghi sự kiện lỗi vào monitoring với low-cardinality tags; tránh lấy raw orderId/userId làm metric label.
- Không dựa vào message của exception để phân loại duy nhất: hãy dùng type, error code và context đã được xác thực.

**Đừng tự log full event payload** nếu nó chứa PII, token hoặc dữ liệu nhạy cảm.

## 6. Phân biệt lỗi listener và lỗi executor từ chối nhận task

Hai trường hợp sau thường bị viết nhầm cùng một `catch`:

### Trường hợp A: task được nhận rồi lỗi

```text
publisher
  -> executor.execute(task)  [accepted]
  -> publishEvent returns
worker
  -> listener throws
  -> ErrorHandler/uncaught/future pathway
```

Lỗi này thường không quay về publisher.

### Trường hợp B: task bị từ chối trước khi chạy

```text
publisher
  -> executor.execute(task)
       -> rejected (saturated/shutdown)
       -> rejection policy hoặc fallback theo multicaster implementation
```

Lỗi submit có thể xảy ra **ngay trên publisher thread**. Với Spring `ThreadPoolTaskExecutor`, một trường hợp rejection có thể thể hiện qua `org.springframework.core.task.TaskRejectedException` (liên quan `RejectedExecutionException`), tùy API/configuration.

**Điểm tinh tế:** không khẳng định mọi `RejectedExecutionException` ở multicaster đều được truyền thẳng ra caller. Một số phiên bản/implementation `SimpleApplicationEventMulticaster` bắt `RejectedExecutionException` khi submit và **gọi listener cục bộ trên publisher thread** như biện pháp fallback khi executor ngừng hoạt động. Vì vậy, khi queue đầy hoặc pool shutdown, hành vi thực tế còn phụ thuộc **phiên bản Spring, loại executor và rejection policy**. Cần xem implementation đang dùng và test đúng trường hợp trong ứng dụng.

Nếu fallback chạy listener đồng bộ, exception của listener có thể lại truyền về publisher khi không có suppressing `ErrorHandler`. Đừng suy luận chỉ từ việc “có executor” rằng mọi lỗi đều tách khỏi caller.

### 6.1. Các chính sách từ chối của ThreadPoolExecutor

| RejectedExecutionHandler | Hành vi Java thường gặp | Rủi ro khi dùng cho event |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Task không được nhận; cách multicast xử lý rejection có thể khác theo phiên bản |
| `CallerRunsPolicy` | Chạy task trên caller thread khi pool còn hoạt động; nếu shutdown thì thường không chạy | Request có thể đột ngột bị chặn; context/transaction/timing khác |
| `DiscardPolicy` | Bỏ task, không nhất thiết ném lỗi | Có thể mất event processing mà publisher vẫn thành công |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue và thử nộp lại task mới | Có thể làm mất việc quan trọng khác, rất khó chẩn đoán |

Đây là các policy của JDK `ThreadPoolExecutor`. Khi cấu hình qua Spring, cần xác nhận executor thực sự dùng policy nào và wrapper có đổi hành vi không.

Không sử dụng `DiscardPolicy` như chiến lược mặc định để “tránh lỗi” với event nghiệp vụ thiết yếu. **Không có exception không có nghĩa task được thực hiện.**

### 6.2. Executor sizing và backpressure

Với `ThreadPoolTaskExecutor`, nên xét:

- `corePoolSize`: số worker duy trì cơ bản.
- `maxPoolSize`: giới hạn worker tối đa.
- `queueCapacity`: số task có thể chờ.
- Task duration/p95/p99: thời gian mỗi listener chiếm worker.
- Tốc độ event đến: đột biến có thể làm queue đầy dù tải trung bình thấp.
- Rejection metrics và shutdown behavior.

Với mô hình `ThreadPoolExecutor` thông thường, task được queue sau khi đạt core threads; executor có thể chỉ tăng thêm threads lên max khi queue không nhận thêm task. Nếu đặt queue quá lớn, bạn có thể không tận dụng `maxPoolSize` theo cách tưởng tượng và tạo backlog lớn.

Chọn bounded executor và có backpressure rõ ràng nếu hệ thống cần kiểm soát tài nguyên; nhưng **bounded không tự tạo retry, delivery guarantee hoặc chính sách lỗi đúng**.

## 7. @Async @EventListener khác executor cấu hình trên multicaster

Hai cách thường gặp:

### 7.1. Chạy async qua multicaster

```java
multicaster.setTaskExecutor(eventExecutor);
multicaster.setErrorHandler(errorHandler);
```

Một listener `@EventListener` thông thường được Spring multicaster gọi trong task executor nếu nó hỗ trợ async. Khi listener ném lỗi, `ErrorHandler` của multicaster là một điểm chặn trực tiếp phù hợp.

### 7.2. Chạy async qua @Async proxy

```java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    sendNotification(event);
}
```

Đây là method minh họa trong bean Spring: cần `@EnableAsync`, bean executor tên `eventExecutor`, `OrderPlaced` và `sendNotification(...)` phù hợp.

Ở đây, annotation-driven async dùng **Spring AOP interceptor/proxy**. Nếu là phương thức `@Async` trả `void` và ném exception sau khi chạy trong worker, handler thích hợp thường là `AsyncUncaughtExceptionHandler` do `AsyncConfigurer` hoặc async configuration cung cấp. Chính sách lỗi này **không đồng nhất** với `SimpleApplicationEventMulticaster.setErrorHandler(...)`.

Nếu đã cấu hình **cả** multicaster executor **và** `@Async` trên listener, có thể tạo thêm một lớp submit/task boundary. Exception do async method `void` ném ra có thể được xử lý bởi async interceptor rồi **không thoát ngược** qua multicaster `ErrorHandler`. Vì vậy đừng coi việc setErrorHandler trên multicaster là cơ chế bao phủ mọi lỗi từ bất kỳ nested async operation nào.

**Thiết kế gọn:** chọn một ranh giới async chính rõ ràng cho từng loại listener, cấu hình monitoring ngay tại ranh giới đó và tránh hai lớp executor không có mục đích.

## 8. Ví dụ Spring Framework 6.2 + Java 17 chạy được, không phụ thuộc timing ngẫu nhiên

Ví dụ sau cố ý không dùng `Thread.sleep(100)` hoặc nhìn log theo may rủi. Nó minh họa:

1. Với multicaster đồng bộ, exception đến publisher.
2. Với multicaster có executor, publisher trả về **trước** khi listener được phép ném lỗi.
3. ErrorHandler ghi nhận rồi suppress lỗi trong worker.
4. Một listener thứ hai vẫn chạy, chứng minh lỗi của task đầu không nhất thiết ngăn task sau.
5. Kiểm thử chờ bằng `CountDownLatch` có timeout, không giả định lịch chạy của OS.

Dự án dùng **JDK 17+**, Maven và **Spring Framework 6.2.12**; chỉ cần module `spring-context`.

### 8.1. Cấu trúc dự án

```text
executor-event-failure/
├── pom.xml
└── src/main/java/demo/ExecutorEventFailureDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executor-event-failure</artifactId>
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
                <configuration>
                    <mainClass>demo.ExecutorEventFailureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ExecutorEventFailureDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

public final class ExecutorEventFailureDemo {

    public static final class OrderEvent extends ApplicationEvent {
        private final String orderId;

        public OrderEvent(String orderId) {
            super(orderId);
            this.orderId = orderId;
        }

        public String orderId() {
            return orderId;
        }
    }

    private static void synchronousExample() {
        var multicast = new SimpleApplicationEventMulticaster();

        multicast.addApplicationListener(
                new ApplicationListener<OrderEvent>() {
                    @Override
                    public void onApplicationEvent(OrderEvent event) {
                        throw new IllegalStateException("sync failure");
                    }
                });

        try {
            multicast.multicastEvent(new OrderEvent("O-SYNC"));
        } catch (IllegalStateException ex) {
            System.out.println("SYNC_CAUGHT=" + ex.getMessage());
        }
    }

    private static void asynchronousExample() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "event-worker"));

        try {
            CountDownLatch allowFailure = new CountDownLatch(1);
            CountDownLatch errorSeen = new CountDownLatch(1);
            CountDownLatch otherListenerSeen = new CountDownLatch(1);
            AtomicReference<String> recordedFailure = new AtomicReference<>();

            var multicast = new SimpleApplicationEventMulticaster();
            multicast.setTaskExecutor(executor);

            multicast.setErrorHandler(error -> {
                recordedFailure.set(
                        error.getClass().getSimpleName() + ":"
                        + error.getMessage());
                errorSeen.countDown();
                // Return normally: suppress the exception at this boundary.
            });

            multicast.addApplicationListener(
                    new ApplicationListener<OrderEvent>() {
                        @Override
                        public void onApplicationEvent(OrderEvent event) {
                            try {
                                if (!allowFailure.await(5, TimeUnit.SECONDS)) {
                                    throw new IllegalStateException(
                                            "publisher did not release task");
                                }
                            } catch (InterruptedException interrupted) {
                                Thread.currentThread().interrupt();
                                throw new IllegalStateException(
                                        "listener interrupted", interrupted);
                            }
                            throw new IllegalStateException(
                                    "async failure " + event.orderId());
                        }
                    });

            multicast.addApplicationListener(
                    new ApplicationListener<OrderEvent>() {
                        @Override
                        public void onApplicationEvent(OrderEvent event) {
                            otherListenerSeen.countDown();
                        }
                    });

            multicast.multicastEvent(new OrderEvent("O-ASYNC"));
            System.out.println("ASYNC_PUBLISH_RETURNED");
            allowFailure.countDown();

            if (!errorSeen.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("ErrorHandler did not observe failure");
            }
            if (!otherListenerSeen.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Other listener did not run");
            }

            System.out.println("ERROR_HANDLER=" + recordedFailure.get());
            System.out.println("OTHER_LISTENER_RAN=true");
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        synchronousExample();
        asynchronousExample();
    }
}
```

Lệnh chạy từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng **do chính chương trình in**, không kể log phụ thuộc môi trường:

```text
SYNC_CAUGHT=sync failure
ASYNC_PUBLISH_RETURNED
ERROR_HANDLER=IllegalStateException:async failure O-ASYNC
OTHER_LISTENER_RAN=true
```

### 8.2. Vì sao đầu ra ổn định?

1. `synchronousExample()` dùng multicaster không có executor và không có ErrorHandler. Listener ném `IllegalStateException("sync failure")`; lời gọi `multicastEvent(...)` ở cùng thread nên `catch` bên ngoài bắt được.
2. `asynchronousExample()` dùng một `ExecutorService` có worker riêng. Task listener đầu tiên không được phép ném lỗi cho đến khi `allowFailure` được giải phóng.
3. Publisher gọi `multicastEvent(...)`, in `ASYNC_PUBLISH_RETURNED` **rồi mới** gọi `allowFailure.countDown()`. Nhờ đó, lỗi của listener chắc chắn xảy ra **sau** dòng publisher đã trả về.
4. Khi listener ném `IllegalStateException`, `SimpleApplicationEventMulticaster` gọi `ErrorHandler`; handler ghi lại loại và message, count down latch, rồi return mà không rethrow.
5. Listener còn lại chạy nhờ task executor; hai latch có timeout xác nhận cả ErrorHandler và listener thứ hai đã hoàn thành bước quan sát.
6. Chỉ sau khi hai latch được thỏa, main mới in hai dòng cuối. Do đó output không phụ thuộc chuyện worker được scheduler chạy nhanh hay chậm.
7. Khối `finally` shutdown executor để không giữ thread sau demo. `shutdownNow()` chỉ là cleanup khi demo kết thúc; ứng dụng production cần graceful shutdown theo đúng nghiệp vụ.

### 8.3. Những gì demo không chứng minh

- Nó **không** chạy một Spring ApplicationContext thực; ví dụ dùng trực tiếp `SimpleApplicationEventMulticaster` để cô lập hành vi lỗi của dispatch.
- Nó **không** gửi message ra broker, không bảo đảm retry/durability.
- Nó **không** mô phỏng `@Async` annotation hoặc `FutureTask.submit()`, nên không minh họa handler của các cơ chế đó bằng execution.
- Nó chỉ chứng minh một ErrorHandler custom **suppress** lỗi. Nếu thay bằng handler rethrow, worker exception path sẽ khác, dù publisher đã trả về.
- Nó không dùng transaction/database; không có ý nghĩa rollback.

Nếu muốn tích hợp vào app Spring, đưa executor/error handler vào bean có tên `applicationEventMulticaster` như phần 4 và viết integration test riêng.

## 9. Khi executor tự xử lý exception: execute khác submit

Đây là phần gây hiểu nhầm lớn khi xem `ThreadPoolTaskExecutor` hoặc JDK `ExecutorService`.

### 9.1. execute(Runnable)

Với `Executor.execute(Runnable)`, một task trực tiếp ném unchecked exception có thể thoát ra worker thread. Tùy executor implementation, exception có thể được ghi qua log, `afterExecute` hoặc `UncaughtExceptionHandler`; worker thread có thể bị thay thế.

```java
executor.execute(() -> {
    throw new IllegalStateException("execute failed");
});
```

Đây là snippet minh họa. Lỗi không tự truyền ngược về dòng `execute(...)` của thread khác nếu task đã được nhận và chạy async. Nhưng nếu rejection xảy ra ngay khi submit, `execute(...)` vẫn có thể ném lỗi ở caller.

### 9.2. submit(Runnable/Callable)

Với `ExecutorService.submit(...)`, lỗi do task ném thường được giữ trong đối tượng `Future`:

```java
Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("submit failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
    // original là lỗi được ném trong Callable/Runnable.
}
```

Đây là snippet, cần import `Future`, `ExecutionException` và `executor` được định nghĩa; `future.get()` có thể ném `InterruptedException` nên caller phải xử lý hoặc khai báo. Trong ví dụ `submit failed`, thông thường `future.get()` ném `ExecutionException` chứa nguyên nhân `IllegalStateException`.

**Không dùng `execute()` và `submit()` như đồng nghĩa về cách lỗi lộ ra.** Nếu không ai giữ Future hoặc gọi `get()`/completion handler, một lỗi bị lưu trong Future có thể không xuất hiện ở nơi bạn đang quan sát.

### 9.3. CompletableFuture

Với `CompletableFuture`:

```java
CompletableFuture<Void> task = CompletableFuture.runAsync(
        () -> sendEmail(),
        executor);

task.whenComplete((ignored, error) -> {
    if (error != null) {
        logger.error("Async email failed", error);
    }
});
```

Đây là snippet minh họa, cần `CompletableFuture`, `executor`, `sendEmail()` và `logger`. Task thất bại khiến future hoàn thành exceptionally. `join()` thường ném `CompletionException`, còn `get()` ném `ExecutionException`. Completion callback có thể bị gọi trên thread hoàn thành task hoặc một thread khác tùy API; đừng đặt giả định về MDC/transaction nếu chưa có propagation.

**Điều quan trọng:** `SimpleApplicationEventMulticaster` thông dụng submit listener qua `Executor.execute(...)`, nhưng một listener có thể **tự tạo Future** ở bên trong. Khi đó multicaster ErrorHandler không tự biết exception của Future được xử lý bất đồng bộ về sau.

## 10. UncaughtExceptionHandler, afterExecute và TaskDecorator

### 10.1. Thread.UncaughtExceptionHandler chỉ thấy lỗi không bị chặn

Một thread factory có thể gắn handler:

```java
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "event-worker");
    thread.setUncaughtExceptionHandler((t, error) ->
            logger.error("Uncaught in " + t.getName(), error));
    return thread;
};
```

Đây là cấu hình minh họa; cần `ThreadFactory`, `logger` và executor tạo thread từ factory. Handler này **không** quan sát được lỗi nếu:

- Multicaster `ErrorHandler` đã suppress.
- `@Async void` interceptor đã giao lỗi cho `AsyncUncaughtExceptionHandler` mà không ném lại.
- `FutureTask` giữ lỗi để `get()` báo về sau.
- Listener tự catch lỗi rồi không ghi nhận gì.

Vì vậy, **đã cấu hình UncaughtExceptionHandler không có nghĩa bắt được mọi event failure**.

### 10.2. ThreadPoolExecutor.afterExecute

JDK `ThreadPoolExecutor.afterExecute(Runnable, Throwable)` cung cấp hook kiểm tra task sau khi chạy. Với task từ `submit`, tham số `Throwable` có thể là `null` dù task đã lỗi, vì `FutureTask` bắt exception nội bộ. Theo mẫu JDK, cần kiểm tra xem `Runnable` có phải `Future<?>` và gọi `get()` khi đã hoàn tất.

```java
@Override
protected void afterExecute(Runnable runnable, Throwable failure) {
    super.afterExecute(runnable, failure);

    if (failure == null && runnable instanceof Future<?> future) {
        try {
            future.get();
        } catch (CancellationException ex) {
            failure = ex;
        } catch (ExecutionException ex) {
            failure = ex.getCause();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    if (failure != null) {
        reportTaskFailure(failure);
    }
}
```

Đây là **override minh họa** trong subclass `ThreadPoolExecutor`, cần imports `Future`, `CancellationException`, `ExecutionException` và một phương thức `reportTaskFailure`. Nó không phải class độc lập hay một cấu hình bắt buộc. Với cancellation, policy về mức độ cảnh báo có thể khác lỗi thực thi. Nếu runnable chưa kết thúc tại hook thì việc gọi `get()` có thể chờ; trong `afterExecute` của executor chuẩn, task vừa chạy xong, nhưng vẫn phải xử lý interruption.

Dù có hook này, bạn **không thấy lỗi listener đã được multicaster ErrorHandler suppress**, bởi lúc tới executor task không còn ném exception.

### 10.3. TaskDecorator

`ThreadPoolTaskExecutor.setTaskDecorator(...)` thường dùng để truyền MDC/tracing context hoặc wrap một `Runnable`. Nó có thể ghi nhận lỗi trong một plain `execute` wrapper:

```java
executor.setTaskDecorator(task -> () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        logger.error("Executor task failed", ex);
        throw ex;
    }
});
```

Đây là đoạn cấu hình minh họa; cần `executor` và `logger` đã khởi tạo. Nó không thay cho listener ErrorHandler: thứ tự wrapper và cơ chế catching quyết định decorator có thấy exception hay không.

Spring Javadoc lưu ý `TaskDecorator` quan sát exception khác nhau giữa `execute` và `submit`: trong đường `submit`, decorator có thể nhận một `FutureTask` không ném lỗi ra bên ngoài, do đó `catch` trong wrapper **không bắt được lỗi đã được Future giữ lại**.

Đừng chọn decorator chỉ với mục tiêu “bắt mọi exception” mà bỏ qua semantics của Future hoặc ErrorHandler.

## 11. @Async void và AsyncUncaughtExceptionHandler

Khi Spring `@Async` xử lý một phương thức trả `void`, caller không có `Future` để đọc lỗi. Spring hỗ trợ:

```java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
            Throwable ex, Method method, Object... params);
}
```

Đoạn trên mô tả hợp đồng API; `AsyncUncaughtExceptionHandler` thuộc `org.springframework.aop.interceptor` và `Method` thuộc `java.lang.reflect`.

Một cấu hình mẫu:

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncEventConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            logger.error("Async listener failed: " + method.getName(), error);
        };
    }
}
```

Đây là snippet minh họa, cần imports của Spring và logger. Nó không tạo một event executor cố định; bạn có thể cấu hình `getAsyncExecutor()` hoặc bean executor riêng.

Đối với `@Async` method trả `Future` hoặc `CompletableFuture`, caller có đường nhận kết quả thất bại từ Future; lỗi có thể **không đi qua AsyncUncaughtExceptionHandler** như `void` method. Do đó, lựa chọn return type ảnh hưởng trực tiếp tới cách kiểm thử và vận hành lỗi.

### Hai điểm dễ nhầm

- `AsyncUncaughtExceptionHandler` không phải `SimpleApplicationEventMulticaster.setErrorHandler`.
- Với `@Async @EventListener void`, exception có thể được async interceptor xử lý **sau khi lời gọi listener proxy đã trả về** cho multicaster. Multicaster ErrorHandler không thể quan sát trực tiếp lỗi chạy trong task phía sau nếu lỗi đã được xử lý ở async layer.

Trong thiết kế event listener, thường không cần một listener `@Async` trả Future chỉ để publisher đợi Future: event publishing contract không cung cấp Future theo cách đó. Nếu nghiệp vụ cần kết quả đồng bộ và quyết định tiếp theo dựa trên kết quả, một service method hoặc command/result API rõ ràng thường hợp lý hơn.

## 12. Vì sao lỗi chỉ xuất hiện trên worker thread?

Giả sử log có dạng:

```text
http-nio-8080-exec-4 INFO  Order placed: O-100
domain-event-3       ERROR Event listener failed
java.lang.IllegalStateException: SMTP unavailable
```

Một số nguyên nhân hợp lý:

1. Publisher chỉ submit event listener task, không đợi kết quả.
2. Listener ném exception trên executor thread.
3. Multicaster ErrorHandler log rồi suppress, hoặc executor/JVM logging ghi lỗi không bắt được.
4. HTTP request đã trả kết quả thành công trước thời điểm lỗi hiện ra.
5. Context MDC và traceId không được propagate, nên log worker không có thông tin request ban đầu.

**Không kết luận rằng executor đã tự retry hoặc Spring đã tự rollback.** Thông thường Spring Application Events là cơ chế trong tiến trình, không có queue bền vững và retry tự động theo business semantics.

### Đừng chỉ nhìn HTTP status

HTTP 200/201 có thể có nghĩa bước **đặt đơn** thành công, trong khi bước **gửi email** bất đồng bộ thất bại. Điều này có thể là đúng thiết kế nếu email là side effect không quyết định transaction chính.

Ngược lại, nếu thành công của nghiệp vụ **phải** phụ thuộc vào email hoặc một bước ngoài, trả 200 trước khi bước đó hoàn tất có thể trái contract. Phải thiết kế lại đồng bộ/transaction/orchestration thay vì chỉ thêm log vào ErrorHandler.

### Đừng chỉ nhìn log “published”

`logger.info("Event published")` ngay sau `publishEvent(...)` trong async mode chỉ chứng minh **hành động publish/submit đã đi qua đoạn code đó**, không chứng minh tất cả listeners thành công. Đặt log tương ứng ở listener sau khi hoàn thành side effect; nếu cần durability, lưu trạng thái xử lý bền vững.

## 13. Logging, tracing và thông tin ngữ cảnh

Khi listener chạy trên executor khác thread, ThreadLocal thường **không được truyền tự động**:

- Spring Security `SecurityContextHolder` của request thread.
- TenantContext tự cài đặt.
- MDC dùng cho request ID / traceId / spanId.
- Transaction context gắn với thread.
- Thread-local custom của ứng dụng.

Nếu listener lỗi và log mất trace ID, lỗi có thể trông như “không thuộc request nào”. Spring Framework có `ContextPropagatingTaskDecorator` cùng Micrometer Context Propagation để hỗ trợ việc truyền một số context đã cấu hình qua executor.

Ví dụ cấu hình ý tưởng:

```java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

Đây là snippet, cần Spring Framework 6.1+, Micrometer Context Propagation phù hợp và bean `ThreadPoolTaskExecutor`. Nó không bảo đảm mọi security/tenant context tự truyền: phải xét registry/accessors, version, policy và ranh giới tin cậy.

**Quan trọng:** việc truyền context cho logging không đồng nghĩa an toàn để chạy mọi thao tác dưới quyền của request cũ. Với event bất đồng bộ chạy sau khi quyền người dùng đã thay đổi, consumer phải dùng identity/tenant metadata đã kiểm chứng và policy riêng, không coi ThreadLocal là giấy phép.

### Metadata tối thiểu hữu ích cho lỗi

Một domain event có thể mang:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String tenantId,
        String correlationId) {
}
```

Đây là record minh họa. `eventId` định danh occurrence, `orderId` gắn fact với aggregate, `tenantId` cần được producer xác thực ở source nghiệp vụ, `correlationId` nối workflow. Không đưa JWT/access token hoặc toàn bộ `Authentication` vào event chỉ để “giữ context”.

Trong ErrorHandler, nếu cần log event ID cụ thể, nên đặt phần logging quan sát sát handler có thông tin event hoặc dùng wrapper/adapter; ErrorHandler nhận `Throwable`, không tự có event metadata. Bảo vệ PII và cardinality của metrics.

## 14. Giao dịch và exception async: không được giả định rollback

Tình huống phổ biến:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(...);
    applicationEventPublisher.publishEvent(
            new OrderPlaced(order.getId()));
}
```

Đây là pseudocode ứng dụng, không thuộc project chạy ở phần 8. Nếu publisher dùng async multicaster:

1. Transaction của `placeOrder` nằm ở publisher thread.
2. Listener async có thể bắt đầu trước khi transaction được commit hoặc sau khi commit, tùy scheduling.
3. Exception của listener thường không truyền về publisher để tự kích hoạt rollback transaction gốc.
4. Async listener không mặc nhiên có cùng transaction context; truy cập dữ liệu vừa lưu có thể thấy trạng thái chưa commit hoặc thiếu tùy isolation/database.
5. Sau khi original transaction commit, callback lỗi không thể “đảo ngược” commit chỉ bằng cách ném exception ở worker.

Với `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, Spring đồng bộ hóa callback với transaction phase; nhưng callback này có semantics riêng và không mặc nhiên trở thành async chỉ do cấu hình multicaster executor.

Dùng after-commit cho side effect chỉ hợp lệ sau commit, nhưng **không coi after-commit callback là queue bền vững**. Process crash vẫn có thể mất việc nếu chỉ dựa trên event trong bộ nhớ. Với nghiệp vụ quan trọng, xem xét transactional outbox, broker có ack/retry/dead-letter và idempotent consumer.

### Khi nào cần trả lỗi cho publisher?

Nếu việc xử lý listener là điều kiện bắt buộc để kết luận lệnh thành công, cần một contract rõ ràng:

- Gọi trực tiếp service đồng bộ và nhận kết quả/exception.
- Dùng workflow có trạng thái và kết quả xử lý (pending/succeeded/failed).
- Dùng orchestration/saga nếu các bước phân tán và không có một transaction chung.

Không thể lấy exception của một task async đã chạy xong về “quá khứ” của HTTP request chỉ bằng cách thêm `catch` quanh `publishEvent(...)`.

## 15. Chính sách lỗi: không phải suppress là đã giải quyết

Một quyết định `ErrorHandler` cần dựa vào độ quan trọng của event:

| Loại công việc | Ví dụ | Chính sách khuyến nghị |
| --- | --- | --- |
| Telemetry best effort | Metric phụ, analytics không trọng yếu | Có thể log + count + suppress theo SLO; vẫn đo failure |
| Notification có thể thử lại | Gửi email, webhook | Lưu trạng thái, retry có giới hạn, idempotency, alert |
| Cập nhật projection quan trọng | Read model, materialized view | Durable queue/outbox, retry/dead-letter, offset/progress |
| Bước giao dịch bắt buộc | Kiểm tra tồn kho trước xác nhận đơn | Đừng ẩn trong best-effort async event; dùng contract đồng bộ/transaction |
| Audit tuân thủ | Ghi lịch sử bắt buộc | Chọn thiết kế bền vững và khả năng chứng minh, không chỉ log |
| Tác vụ có lỗi dữ liệu | Event payload không hợp lệ | Ghi failure có cấu trúc, cách ly poison event, không retry vô hạn |

**Suppress** có nghĩa “không để exception tiếp tục lan ra từ listener”, không có nghĩa “thành công”. Phải có metric và cách quyết định sự kiện đó có được retry hay cần xử lý thủ công.

Một lỗi có thể dẫn đến ít nhất ba trạng thái:

```text
EVENT_ACCEPTED
      |
      +--> HANDLED_SUCCESS
      |
      +--> HANDLED_FAILED_RETRYABLE
      |
      +--> HANDLED_FAILED_TERMINAL
```

Đây chỉ là mô hình trạng thái ứng dụng, không phải state machine Spring cung cấp sẵn. Nếu cần biết outcome lâu dài, hãy lưu nó ở nơi bền vững thay vì suy ra từ việc publisher không ném exception.

## 16. Kiểm thử ErrorHandler và executor đúng cách

### 16.1. Dùng latch để tránh test chập chờn

Test đồng bộ:

```java
assertThrows(IllegalStateException.class,
        () -> multicast.multicastEvent(new OrderEvent("O-1")));
```

Đoạn này là JUnit snippet, giả định `multicast` không có async executor/ErrorHandler suppress và listener ném `IllegalStateException`.

Test async:

```java
CountDownLatch errorObserved = new CountDownLatch(1);
AtomicReference<Throwable> failure = new AtomicReference<>();

multicast.setErrorHandler(error -> {
    failure.set(error);
    errorObserved.countDown();
});

multicast.multicastEvent(new OrderEvent("O-2"));

assertTrue(errorObserved.await(5, TimeUnit.SECONDS));
assertInstanceOf(IllegalStateException.class, failure.get());
```

Đoạn trên là **test snippet**, cần JUnit, java.concurrent imports, multicaster có executor và listener lỗi, không phải ví dụ chạy độc lập. Latch dùng timeout để test fail rõ khi handler không chạy; `AtomicReference` giữ nguyên exception thay vì dựa vào log.

### 16.2. Kiểm tra cả lỗi và side effect

Đừng chỉ assert handler đã được gọi. Một test thực tế nên kiểm tra:

- Đã gọi đúng listener hoặc worker?
- Exception type/message/cause có đúng nguồn?
- Có vô tình thực thi side effect **một phần** trước khi exception xảy ra?
- Lỗi đã được log/metric/record chưa?
- Có retry hay không, chính sách backoff/deduplication thế nào?
- Listener khác vẫn được xử lý theo thiết kế hay bị chặn?
- Cần cancel hoặc shutdown task còn lại không?
- Publisher nhận exception hay không theo đúng async/sync contract?
- Có leakage ThreadLocal/tracing context sang task tiếp theo không?

Nếu một listener đã gửi email rồi ném exception trước khi ghi trạng thái, retry có thể gửi **hai email**. ErrorHandler đúng kỹ thuật vẫn không thay thế idempotency của business operation.

### 16.3. Test reject và CallerRuns riêng

Để kiểm tra queue saturation, hãy cấu hình executor rất nhỏ, giữ worker bằng `CountDownLatch`, điền queue đến capacity rồi submit thêm task. Test phải có timeout và cleanup để không treo CI.

Sau đó đo:

- `AbortPolicy`: rejection có xảy ra và multicaster xử lý ra sao theo phiên bản?
- `CallerRunsPolicy`: listener có chạy trên publisher thread và ảnh hưởng latency?
- `DiscardPolicy`: task có bị mất mà không được báo lỗi?
- Pool shutdown: executor/multicaster có fallback, ném lỗi hay bỏ task?

Không xây test dựa vào `Thread.sleep(50)`. Dùng latch, counters, thread identity và chính sách executor được khai báo rõ.

### 16.4. Test submit/Future

Với task được submit trả Future, kiểm tra:

```java
Future<?> future = executor.submit(
        () -> { throw new IllegalStateException("boom"); });

ExecutionException ex = assertThrows(
        ExecutionException.class,
        future::get);

assertInstanceOf(IllegalStateException.class, ex.getCause());
```

Đây là snippet JUnit, cần `ExecutorService`, `Future`, `ExecutionException` và assertions. Không giả định `Thread.UncaughtExceptionHandler` được gọi cho lỗi đã nằm trong `FutureTask`.

## 17. Debug nhanh khi "lỗi biến mất"

Một quy trình chẩn đoán có thể áp dụng trực tiếp trên dự án Spring:

**Bước 1 — Xác định publisher và event type.** Tìm vị trí `publishEvent(...)`; ghi rõ event xảy ra trong request, scheduler hay transaction phase nào.

**Bước 2 — Tìm multicaster thực.** Có bean `applicationEventMulticaster` không? Có `SimpleApplicationEventMulticaster.setTaskExecutor(...)` và `setErrorHandler(...)` không?

**Bước 3 — Kiểm tra listener.** Có `@EventListener`, `@Async`, `@TransactionalEventListener` hoặc handler tự chạy `CompletableFuture` không? Đây là những đường exception khác nhau.

**Bước 4 — Xác định nơi task được gửi.** Có một hay nhiều executor? Thread name, pool state, queue size, rejection policy, number of active threads và pending tasks thế nào?

**Bước 5 — Tìm điểm chặn lỗi.** Lỗi bị catch trong listener? Multicaster ErrorHandler log/suppress? AsyncUncaughtExceptionHandler? Future completion? TaskDecorator? UncaughtExceptionHandler? Executor afterExecute?

**Bước 6 — Quan sát mã lỗi gốc.** Dùng exception type, stack trace, causal chain. Nếu log chỉ chứa `error.getMessage()`, bạn có thể mất nguyên nhân và call path cần để debug.

**Bước 7 — Kiểm tra transaction.** Publisher đã commit hay đang trong transaction? Listener có chạy trước commit? Lỗi listener có liên quan business transaction hay chỉ là side effect?

**Bước 8 — Kiểm tra outcome.** Side effect có hoàn thành một phần không? Có trạng thái FAILED/PENDING bền vững hay chỉ dòng log?

**Bước 9 — Kiểm tra duplicate/retry.** Có thể publisher đã retry, executor đã fallback caller-runs hoặc consumer lặp lại? Tính idempotency của listener đã bảo đảm chưa?

**Bước 10 — Tạo test tái hiện.** Test sync và async riêng bằng latch, assert handler được gọi/không gọi, test rejection và shutdown nếu liên quan.

### Bảng triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cần kiểm tra |
| --- | --- | --- |
| Publisher thành công, listener log lỗi ở worker | Async task được nhận rồi ném exception | Executor + ErrorHandler |
| Publisher không bắt được lỗi nhưng handler tăng counter | Handler đã suppress lỗi | Policy handler và business outcome |
| Không có lỗi nào trong log, side effect thiếu | `FutureTask` giữ lỗi, `DiscardPolicy` bỏ task, listener catch/suppress | Future, rejection, logging |
| Lỗi xuất hiện trong caller dù đã set executor | Sync-only listener, CallerRunsPolicy hoặc fallback sau rejection | Thread identity, version, policy |
| Lỗi xuất hiện ở AsyncUncaughtExceptionHandler | `@Async void` method lỗi | AsyncConfigurer/annotation proxy |
| Future hoàn thành exceptionally, không có uncaught log | Exception được lưu trong Future | `get()`, completion callbacks |
| Listener thứ hai vẫn chạy khi listener đầu lỗi | Async per-listener tasks hoặc suppress handler | Không suy luận rằng tất cả task thành công |
| Không nhận transaction context trên worker | Thread-local transaction không tự propagate | Transaction boundary, event phase |
| Log lỗi thiếu traceId | MDC/tracing context chưa propagate | TaskDecorator, Context Propagation |
| Có duplicate side effect sau retry | Handler thiếu idempotency/outcome | Dedupe key, retry strategy |
| Shutdown thỉnh thoảng gây xử lý event trên caller | Executor bị reject và multicaster có fallback | Source/version, shutdown plan |

## 18. Các anti-pattern cần tránh

1. **Chỉ bắt exception quanh `publishEvent(...)` rồi tin toàn bộ listener an toàn.** Đúng với một số lỗi sync/submit, không phải lỗi task async đã được nhận.
2. **Thiết lập ErrorHandler chỉ `return` mà không log/metric.** Biến lỗi xử lý thành im lặng hoàn toàn.
3. **Cho rằng `ErrorHandler` của multicaster bắt cả exception trong `CompletableFuture` tự tạo ở listener.** Lỗi nằm ở Future layer khác.
4. **Cho rằng `@Async void` luôn ném về publisher.** Phải xem `AsyncUncaughtExceptionHandler`.
5. **Dùng `Thread.UncaughtExceptionHandler` để bắt tất cả lỗi task.** `FutureTask` và handler suppress có thể ngăn exception thoát khỏi Runnable.
6. **Cho rằng executor queue đầy luôn ném lỗi.** Rejection handler có thể chạy caller hoặc âm thầm discard.
7. **Cho rằng executor rejection luôn được truyền ra khỏi multicaster.** Một số implementation/phiên bản có fallback chạy listener trên caller.
8. **Không phân biệt error lúc submit và error lúc xử lý.** Dẫn đến sai hướng điều tra.
9. **Dùng `DiscardPolicy` cho sự kiện nghiệp vụ quan trọng.** Mất việc mà caller vẫn thành công.
10. **Dùng unbounded queue để “không có rejection”.** Có thể tích backlog, gây memory pressure và shutdown kéo dài.
11. **Log raw event chứa secrets/PII.** Khắc phục lỗi vận hành nhưng gây lỗi bảo mật.
12. **Không dọn MDC/tenant ThreadLocal ở worker.** Tác vụ sau có thể dùng nhầm context.
13. **Bỏ qua ranh giới transaction.** Lỗi async không có nghĩa DB đã rollback.
14. **Retry mà không idempotent.** Side effect có thể đã thực hiện một phần trước khi lỗi.
15. **Không có timeout trong test async.** CI có thể treo khi task không chạy.
16. **Dùng `Thread.sleep(...)` thay điều kiện hoàn tất.** Test flake khi máy chậm.
17. **Cho rằng Spring Application Events là một broker có durable retry.** Mặc định chỉ là dispatch trong process/context.
18. **Cấu hình đồng thời multicaster executor và `@Async` mà không biết exception đi qua handler nào.** Tạo nhiều lớp ngắt mạch khó chẩn đoán.
19. **Giấu exception gốc bằng `throw new RuntimeException("error")` không giữ cause.** Mất stacktrace, làm khó root-cause analysis.
20. **Lẫn lộn “listener đã nhận event” với “side effect của listener đã thành công”.** Cần đo outcome thực tế.

## 19. Checklist vận hành

Trước khi kết luận “exception đã được xử lý bởi executor”, hãy trả lời:

- [ ] Multicaster đang đồng bộ hay có `setTaskExecutor(...)`?
- [ ] Listener đang dùng `@Async` hay tự tạo `Future` ở bên trong?
- [ ] Lỗi xảy ra tại `execute/submit` hay sau khi worker đã bắt đầu?
- [ ] `ErrorHandler` của multicaster có log/suppress/rethrow?
- [ ] `AsyncUncaughtExceptionHandler` có được cấu hình cho `@Async void`?
- [ ] Có `Future.get()/join()/whenComplete()` để quan sát task failure?
- [ ] `TaskDecorator` và `Thread.UncaughtExceptionHandler` có thấy đúng loại lỗi này không?
- [ ] Pool có bounded queue, rejection policy và shutdown behavior rõ ràng?
- [ ] Listener nào không hỗ trợ async execution?
- [ ] Lỗi có được log kèm stack trace và event correlation an toàn?
- [ ] Có metric riêng cho accepted/failed/rejected/retried/succeeded?
- [ ] Event có thể mất sau process crash không? Có cần outbox/broker?
- [ ] Consumer có idempotency nếu retry không?
- [ ] Transaction semantics có được bảo toàn đúng yêu cầu?
- [ ] Test có latch/timeout và xác minh exception ở đúng ranh giới?

**Tóm tắt:** Exception trong Spring event listener có thể đi qua nhiều tầng. Với listener được executor chạy, lỗi sau khi task đã được nhận **không mặc nhiên quay về thread gọi `publishEvent()`**. `SimpleApplicationEventMulticaster.ErrorHandler` quyết định cách xử lý lỗi listener ngay tại dispatch; `@Async void` dùng `AsyncUncaughtExceptionHandler`; còn các task `submit`/`Future` có thể giữ lỗi tới lúc lấy kết quả. Lỗi submit/rejection là một đường khác, đôi khi gây caller-runs/fallback. Hệ thống cần ghi nhận **outcome, stacktrace và context**, thiết kế retry/idempotency phù hợp, thay vì coi một publisher trả về bình thường là bằng chứng mọi listener thành công.

## Tài liệu tham khảo

- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — ApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework — Observability and Application Events](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [JDK 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [JDK 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
