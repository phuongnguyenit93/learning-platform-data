# Exception trong async listener của Spring Framework

## Mục tiêu

Khi một method `@EventListener` được đánh dấu thêm `@Async`, Spring chuyển việc xử lý event sang một `TaskExecutor`. Publisher phát event và tiếp tục công việc của mình; listener chạy trên worker thread. Vì listener không còn chạy trong luồng gọi `publishEvent`, exception phát sinh trong lúc xử lý bất đồng bộ không truyền ngược về publisher.

Với async listener có kiểu trả về `void`, Spring cung cấp `AsyncUncaughtExceptionHandler` để nhận các exception không có Future handle. Nếu không cấu hình handler riêng, Spring dùng handler mặc định để ghi log. Cơ chế này giúp quan sát lỗi, nhưng không tự retry, rollback transaction của publisher hoặc lưu công việc để chạy lại sau khi process khởi động.

Bài học này giúp bạn:

- Phân biệt exception của listener đồng bộ và async listener.
- Hiểu exception flow của `@Async` với return type `void` và `Future`.
- Cấu hình `AsyncUncaughtExceptionHandler` bằng `AsyncConfigurer`.
- Ghi log đủ ngữ cảnh mà không làm lộ dữ liệu nhạy cảm.
- Bắt lỗi bên trong listener, phát failure event và thiết kế retry có kiểm soát.
- Phân biệt lỗi khi submit task với lỗi xảy ra trong worker thread.
- Viết ví dụ Java 17/Spring Framework 6.2 chạy được và kiểm thử bằng latch.

## 1. Vì sao exception không quay về publisher?

Với event listener đồng bộ, `publishEvent` gọi listener trong thread hiện tại. Nếu listener ném một runtime exception và exception không được xử lý, lỗi có thể truyền về nơi gọi `publishEvent`.

Khi thêm `@Async`, Spring dùng proxy để submit lời gọi method lên executor. Publisher chỉ thực hiện việc dispatch và submit; worker thread thực hiện phần thân listener sau đó.

Luồng xử lý:

```text
Publisher thread
    |
    | publishEvent(event)
    v
Spring event dispatcher
    |
    | gọi async proxy / submit task
    v
TaskExecutor queue
    |
    | worker thread thực thi
    v
@Async @EventListener method
    |
    +---- hoàn tất bình thường
    |
    +---- ném exception
             |
             v
       Async exception handling
```

Khi listener chạy bất đồng bộ:

- `publishEvent(...)` không chờ phần thân listener hoàn tất.
- Exception phát sinh trong worker thread không được ném ngược về thread đã publish event.
- `try/catch` quanh `publishEvent` không bắt được exception phát sinh sau đó trong listener.
- Publisher không biết listener thành công hay thất bại nếu ứng dụng không xây dựng kênh phản hồi riêng.
- Transaction, ThreadLocal và logging context của publisher không tự động chuyển sang worker thread.

Đây là đặc điểm của xử lý bất đồng bộ, không phải lỗi của event publisher. Nếu nghiệp vụ cần biết kết quả, hãy thiết kế một cơ chế phản hồi rõ ràng như trạng thái công việc, failure event, callback hoặc message result.

## 2. Hai cách xử lý exception theo return type của @Async

Spring phân biệt method `@Async` trả về `void` và method trả về một kiểu `Future`.

| Return type | Exception được xử lý thế nào? | Ai quan sát được? |
|---|---|---|
| `void` | Không có Future để chứa exception; exception được chuyển đến `AsyncUncaughtExceptionHandler` | Handler đã cấu hình; mặc định Spring ghi log |
| `Future<T>` | Exception được lưu trong Future và xuất hiện khi caller gọi `get()` | Caller giữ Future handle |
| `CompletableFuture<T>` | Future hoàn tất exceptionally; có thể xử lý bằng `whenComplete`, `handle` hoặc `exceptionally` | Caller giữ CompletableFuture handle |

### Async method trả về void

Ví dụ:

```java
@Async("eventExecutor")
@EventListener
public void onPaymentRequested(PaymentRequested event) {
    paymentProcessor.process(event); // Có thể ném exception.
}
```

Vì method trả về `void`, không có Future để caller đọc. Spring gọi `AsyncUncaughtExceptionHandler.handleUncaughtException(...)` khi exception thoát khỏi method.

Nếu không cấu hình handler, Spring dùng `SimpleAsyncUncaughtExceptionHandler` mặc định để ghi log exception. Ứng dụng production thường nên cấu hình handler riêng để thêm tên method, loại event, event ID hoặc correlation ID vào log/metric.

### Async method trả về Future

Với một service method được gọi trực tiếp qua Spring proxy:

```java
@Async("eventExecutor")
public CompletableFuture<PaymentResult> processAsync(
        PaymentRequested event) {
    PaymentResult result = processor.process(event);
    return CompletableFuture.completedFuture(result);
}
```

Caller có thể giữ handle:

```java
CompletableFuture<PaymentResult> future =
        paymentService.processAsync(event);

future.whenComplete((result, error) -> {
    if (error != null) {
        logger.error("Payment processing failed", error);
    }
});
```

Nếu method ném exception, Future hoàn tất exceptionally. Caller có thể quan sát lỗi bằng callback hoặc `get()`.

Tuy nhiên, khi method được gọi như một async event listener, publisher không nhận được Future của listener từ `publishEvent`. Đừng thiết kế event listener với giả định rằng publisher có thể gọi `get()` hoặc `whenComplete` trên kết quả listener. Nếu cần Future handle, hãy tách công việc sang một async service method và gọi trực tiếp method đó từ thành phần cần theo dõi kết quả.

## 3. AsyncUncaughtExceptionHandler là gì?

`AsyncUncaughtExceptionHandler` là interface của Spring dùng để xử lý exception thoát khỏi method `@Async` có return type `void`.

Interface có method:

```java
void handleUncaughtException(
        Throwable ex,
        Method method,
        Object... params
);
```

Handler nhận ba nhóm thông tin:

- `ex`: exception hoặc throwable đã thoát khỏi method async.
- `method`: method đã thực thi và phát sinh lỗi.
- `params`: các đối số được truyền vào method, thường có event object ở vị trí đầu tiên đối với listener một tham số.

Handler phù hợp cho logging, metric, tracing và gửi cảnh báo. Không nên đặt toàn bộ logic nghiệp vụ phục hồi vào handler vì handler là điểm xử lý lỗi chung cho các async method trả về void, không chỉ riêng event listener.

### Cấu hình qua AsyncConfigurer

Có thể cung cấp custom handler thông qua `AsyncConfigurer` khi bật `@EnableAsync`:

```java
@Configuration
@EnableAsync
class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            logger.error(
                    "Async method {} failed",
                    method.toGenericString(),
                    ex
            );
        };
    }
}
```

`AsyncConfigurer` cũng cho phép cung cấp executor mặc định bằng `getAsyncExecutor()`. Nếu listener cần executor riêng, có thể đặt tên bean và chỉ định bằng `@Async("eventExecutor")`.

Nếu có nhiều nhóm tác vụ với chính sách khác nhau, nên tách executor theo mục đích: ví dụ `eventExecutor`, `emailExecutor` hoặc `reportExecutor`. Handler vẫn có thể là chính sách chung; nếu cần hành vi riêng cho một nghiệp vụ, hãy bắt exception trong listener và gọi component xử lý tương ứng.

## 4. Cấu hình handler có ngữ cảnh event

Một handler hữu ích nên ghi được tên method, loại lỗi và định danh event. Không nên log toàn bộ payload vì event có thể chứa thông tin cá nhân, token hoặc dữ liệu nghiệp vụ nhạy cảm.

Ví dụ:

```java
@Bean
AsyncConfigurer asyncConfigurer() {
    return new AsyncConfigurer() {

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {

            return (ex, method, params) -> {
                Object firstArgument =
                        params.length > 0 ? params[0] : null;

                logger.error(
                        "Async listener failed: method={}, argumentType={}",
                        method.getName(),
                        firstArgument == null
                                ? "none"
                                : firstArgument.getClass().getSimpleName(),
                        ex
                );
            };
        }
    };
}
```

Với một event class có ID, có thể trích xuất ID an toàn bằng cách kiểm tra kiểu cụ thể:

```java
if (firstArgument instanceof PaymentRequested event) {
    logger.error(
            "Payment listener failed: paymentId={}",
            event.paymentId(),
            ex
    );
}
```

Không ép kiểu mọi tham số về một event class cố định nếu handler dùng chung cho nhiều async method. Hãy kiểm tra kiểu trước, hoặc ghi method signature và argument type thay vì giả định.

Nên đưa vào log:

- Tên method và bean/component liên quan.
- Event type và event ID nếu có.
- Correlation ID hoặc trace ID đã được truyền an toàn.
- Exception class, message và stack trace.
- Tên executor/thread khi cần điều tra tình trạng quá tải.

Tránh đưa mật khẩu, access token, dữ liệu thẻ thanh toán hoặc toàn bộ payload vào log.

## 5. Ví dụ chạy được: async listener ném exception và handler nhận lỗi

Ví dụ dưới đây dùng Java 17 và Spring Framework 6.2.8, không cần Spring Boot. Một listener trả về `void`, chạy trên executor riêng và cố ý ném `IllegalStateException`. Custom `AsyncUncaughtExceptionHandler` ghi nhận exception và đánh thức main thread bằng latch để ví dụ có output xác định.

Cấu trúc dự án:

```text
async-listener-exception-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AsyncListenerExceptionDemo.java
```

**pom.xml**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-listener-exception-demo</artifactId>
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
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.AsyncListenerExceptionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/demo/AsyncListenerExceptionDemo.java**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
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

public class AsyncListenerExceptionDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CompletionGate gate = context.getBean(CompletionGate.class);

            System.out.println(
                    "publisher thread: " + Thread.currentThread().getName()
            );

            context.publishEvent(new PaymentRequested(501L));

            if (!gate.awaitStarted(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener did not start");
            }

            System.out.println(
                    "publishEvent returned while listener is still running"
            );

            gate.release();

            if (!gate.awaitHandled(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Async exception handler was not called"
                );
            }
        }
    }

    @Configuration
    @EnableAsync
    static class AppConfig {

        @Bean(name = "eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        CompletionGate completionGate() {
            return new CompletionGate();
        }

        @Bean
        AsyncConfigurer asyncConfigurer(
                CompletionGate gate,
                ThreadPoolTaskExecutor eventExecutor) {

            return new AsyncConfigurer() {

                @Override
                public Executor getAsyncExecutor() {
                    return eventExecutor;
                }

                @Override
                public AsyncUncaughtExceptionHandler
                        getAsyncUncaughtExceptionHandler() {

                    return (ex, method, params) -> {
                        PaymentRequested event =
                                (PaymentRequested) params[0];

                        System.out.printf(
                                "async exception in %s: %s; paymentId=%d%n",
                                method.getName(),
                                ex.getMessage(),
                                event.paymentId()
                        );

                        gate.markHandled();
                    };
                }
            };
        }

        @Bean
        PaymentListener paymentListener(CompletionGate gate) {
            return new PaymentListener(gate);
        }
    }

    record PaymentRequested(long paymentId) {
    }

    static class CompletionGate {
        private final CountDownLatch started = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);
        private final CountDownLatch handled = new CountDownLatch(1);

        void markStarted() {
            started.countDown();
        }

        boolean awaitStarted(long timeout, TimeUnit unit)
                throws InterruptedException {
            return started.await(timeout, unit);
        }

        void waitForRelease() {
            try {
                if (!release.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Release timed out");
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Listener interrupted",
                        ex
                );
            }
        }

        void release() {
            release.countDown();
        }

        void markHandled() {
            handled.countDown();
        }

        boolean awaitHandled(long timeout, TimeUnit unit)
                throws InterruptedException {
            return handled.await(timeout, unit);
        }
    }

    static class PaymentListener {
        private final CompletionGate gate;

        PaymentListener(CompletionGate gate) {
            this.gate = gate;
        }

        @Async("eventExecutor")
        @EventListener
        public void onPaymentRequested(PaymentRequested event) {
            System.out.println(
                    "listener started: payment=" + event.paymentId()
                            + " on " + Thread.currentThread().getName()
            );

            gate.markStarted();
            gate.waitForRelease();

            throw new IllegalStateException("simulated failure");
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout:

```text
publisher thread: main
listener started: payment=501 on event-1
publishEvent returned while listener is still running
async exception in onPaymentRequested: simulated failure; paymentId=501
```

Giải thích:

1. `@EnableAsync` bật xử lý method `@Async` qua Spring proxy.
2. `eventExecutor` là executor có một worker thread với tên bắt đầu bằng `event-`.
3. Listener `onPaymentRequested` trả về `void`, chạy bất đồng bộ và chờ latch trước khi ném exception.
4. `publishEvent` chỉ submit việc xử lý; main thread không chờ phần thân listener hoàn tất.
5. Khi listener ném `IllegalStateException`, Spring chuyển exception đến custom `AsyncUncaughtExceptionHandler`.
6. Handler nhận method và tham số event, in payment ID rồi giảm latch để main thread kết thúc an toàn.

Hai latch `started` và `release` chỉ làm rõ thời điểm publisher và listener chạy. Trong ứng dụng thật, không dùng latch để điều phối nghiệp vụ; dùng cơ chế đồng bộ hoặc trạng thái công việc phù hợp.

## 6. Bắt lỗi ngay trong listener khi cần phản ứng nghiệp vụ

`AsyncUncaughtExceptionHandler` là nơi xử lý lỗi chung. Nếu mỗi loại event có cách phục hồi riêng, listener có thể bắt exception ngay trong method.

Ví dụ listener phát một event thất bại:

```java
@Component
class InvoiceListener {

    private final ApplicationEventPublisher publisher;
    private final InvoiceProcessor processor;

    InvoiceListener(
            ApplicationEventPublisher publisher,
            InvoiceProcessor processor) {
        this.publisher = publisher;
        this.processor = processor;
    }

    @Async("eventExecutor")
    @EventListener
    public void onInvoiceRequested(InvoiceRequested event) {
        try {
            processor.process(event);
        }
        catch (RuntimeException ex) {
            publisher.publishEvent(
                    new InvoiceProcessingFailed(
                            event.invoiceId(),
                            ex.getClass().getSimpleName()
                    )
            );
            throw ex;
        }
    }
}
```

Ở đây listener vừa phát `InvoiceProcessingFailed` để thành phần khác phản ứng, vừa ném lại exception để handler chung ghi nhận lỗi. Nếu không muốn handler chung xử lý lỗi đã được quản lý cục bộ, có thể không ném lại; nhưng khi đó listener phải tự bảo đảm log/metric và trạng thái lỗi đã được ghi nhận.

Failure event nên chứa thông tin tối thiểu như event ID, business ID, loại lỗi và thời điểm. Không nên đưa nguyên stack trace hoặc payload nhạy cảm vào event nghiệp vụ.

Một failure event cũng có thể được nhận bởi một listener khác. Tránh để failure listener ném lại cùng loại event theo vòng lặp vô hạn; xác định rõ chính sách retry và giới hạn số lần thử.

## 7. Retry, idempotency và lưu trạng thái lỗi

Exception handler chỉ nhận biết lỗi. Nó không tự chạy lại listener. Nếu cần retry, hãy xác định chính sách cụ thể:

- **Số lần thử:** giới hạn số lần retry cho mỗi event.
- **Backoff:** tăng khoảng chờ giữa các lần thử để tránh dồn tải lên dependency đang lỗi.
- **Phân loại lỗi:** phân biệt lỗi tạm thời như timeout với lỗi dữ liệu không hợp lệ không thể tự khắc phục.
- **Idempotency:** bảo đảm xử lý lại cùng event không tạo side effect trùng.
- **Trạng thái:** lưu số lần thử, lần thử gần nhất và trạng thái cuối.
- **Dead-letter/manual recovery:** giữ event không xử lý được để điều tra hoặc can thiệp.

Với tác vụ quan trọng cần tồn tại qua restart, executor trong bộ nhớ không đủ. Hãy lưu công việc bền vững bằng transactional outbox hoặc message broker có acknowledgement/retry/dead-letter phù hợp. Consumer vẫn cần idempotency vì message có thể được giao nhiều lần.

Không nên triển khai retry bằng cách gọi đệ quy listener ngay trong exception handler. Cách đó dễ tạo vòng lặp nhanh, không có backoff và khó kiểm soát tải.

## 8. Phân biệt lỗi xử lý với lỗi submit task

Có hai thời điểm lỗi khác nhau:

1. **Lỗi submit:** executor từ chối nhận task, ví dụ queue đầy hoặc executor đã shutdown. Với Spring `ThreadPoolTaskExecutor`, lỗi từ executor bị từ chối thường được bọc thành `TaskRejectedException`; lỗi này có thể xuất hiện ngay trong luồng dispatch khi Spring cố submit listener.
2. **Lỗi thực thi:** task đã được nhận, sau đó listener ném exception trong worker thread. Với listener `void @Async`, lỗi đi qua `AsyncUncaughtExceptionHandler`.

Hai loại lỗi cần quan sát riêng. Error handler của `SimpleApplicationEventMulticaster` xử lý lỗi phát sinh trong quá trình multicaster gọi listener trên thread dispatch; nó không thay thế `AsyncUncaughtExceptionHandler` cho exception xảy ra sau đó trong worker thread.

Để giảm lỗi submit:

- Dùng executor có giới hạn thread và queue.
- Đặt rejection policy phù hợp với yêu cầu hệ thống.
- Theo dõi queue depth, active thread, task rejection và thời gian chờ.
- Không dùng queue không giới hạn để che giấu consumer xử lý chậm.
- Có backpressure hoặc durable queue nếu producer có thể phát nhanh hơn khả năng xử lý.

Nếu executor dùng `CallerRunsPolicy`, task bị từ chối có thể chạy trên thread submit. Điều này thay đổi latency của publisher và có thể làm luồng publish chạy listener trực tiếp trong thời điểm quá tải; chỉ dùng khi hành vi đó được chủ ý chấp nhận.

## 9. Transaction, ThreadLocal và logging context

Async listener chạy trên worker thread, vì vậy không tự kế thừa transaction của thread publisher. Nếu publisher phát event trong một transaction database, listener async có thể bắt đầu xử lý trước khi transaction đó commit.

Nếu listener cần dữ liệu đã commit:

- Dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để ràng buộc thời điểm nhận event.
- Nếu cần ghi dữ liệu trong transaction độc lập sau commit, gọi service dùng `Propagation.REQUIRES_NEW`.
- Nếu công việc không được phép mất sau khi transaction commit, cân nhắc transactional outbox thay vì chỉ dựa vào event callback trong bộ nhớ.

ThreadLocal, MDC và security context cũng không tự truyền sang worker thread. Có thể truyền correlation ID trong event hoặc cấu hình `TaskDecorator`/context propagation cho executor. Chỉ truyền dữ liệu cần thiết và bảo đảm context được dọn sau khi task kết thúc để tránh rò rỉ giữa các task dùng chung thread.

## 10. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng try/catch quanh `publishEvent` để bắt listener exception | Exception xảy ra sau đó trong worker thread | Dùng AsyncUncaughtExceptionHandler hoặc callback |
| Không cấu hình handler cho async void listener | Exception không có Future để caller quan sát | Cấu hình AsyncConfigurer và handler |
| Nghĩ handler tự retry | Handler chỉ nhận exception và metadata | Xây dựng retry có giới hạn, backoff và trạng thái |
| Trả Future từ async listener để publisher lấy kết quả | Event publisher không trả handle của listener | Gọi async service trực tiếp nếu cần Future |
| Dùng return value để phát event tiếp theo | Return-value publishing không được hỗ trợ cho async listener | Inject ApplicationEventPublisher và publish tường minh |
| Nhầm ErrorHandler của multicaster với async handler | Hai handler xử lý lỗi ở hai giai đoạn khác nhau | Dùng đúng handler cho lỗi dispatch và lỗi worker |
| Ghi toàn bộ event payload vào log | Có thể lộ dữ liệu nhạy cảm | Chỉ ghi event ID và metadata an toàn |
| Gọi method @Async qua self-invocation | Lời gọi nội bộ không đi qua proxy | Gọi qua Spring bean proxy |
| Không theo dõi executor rejection | Queue đầy hoặc executor shutdown làm task không được nhận | Theo dõi pool/queue và thiết kế backpressure |
| Giả định transaction/MDC tự truyền | Worker dùng thread khác | Truyền context có chủ đích hoặc dùng TaskDecorator |
| Nuốt exception mà không lưu trạng thái | Hệ thống mất dấu công việc thất bại | Ghi trạng thái, metric và có quy trình phục hồi |

## 11. Checklist triển khai

- [ ] Đã bật `@EnableAsync` và listener được Spring quản lý.
- [ ] Method `@EventListener` được gọi qua proxy, không self-invocation.
- [ ] Đã chọn executor và giới hạn pool/queue phù hợp.
- [ ] Với listener trả `void`, đã cấu hình `AsyncUncaughtExceptionHandler`.
- [ ] Handler ghi method, event ID/type và exception an toàn.
- [ ] Không trông chờ try/catch quanh `publishEvent` bắt được lỗi worker.
- [ ] Đã phân biệt lỗi submit task và lỗi khi listener thực thi.
- [ ] Nếu cần phản ứng nghiệp vụ, listener bắt lỗi và phát failure event rõ ràng.
- [ ] Retry có giới hạn, backoff và idempotency.
- [ ] Không dùng async return value để phát follow-up event.
- [ ] Transaction, ThreadLocal, MDC và security context được truyền có chủ đích.
- [ ] Dùng outbox/broker nếu công việc không được phép mất khi process dừng.

## Kết luận

Exception trong async listener không truyền ngược về publisher vì listener chạy trên executor sau khi event đã được dispatch. Với method `@Async` trả `void`, Spring chuyển lỗi đến `AsyncUncaughtExceptionHandler`; với async service method trả Future được gọi trực tiếp, caller quan sát lỗi qua Future. Handler giúp ghi nhận lỗi nhưng không tự retry, rollback transaction chính hoặc lưu công việc bền vững. Hãy chọn executor có giới hạn, phân biệt lỗi submit và lỗi thực thi, phát failure event khi cần phản ứng nghiệp vụ, và dùng retry/outbox/idempotency cho tác vụ quan trọng.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Asynchronous Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Exception Management with @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [AsyncUncaughtExceptionHandler — Spring Framework 6.2.8 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [AsyncConfigurer — Spring Framework 6.2.8 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)