# ExecutorSubscribableChannel với xử lý trực tiếp hoặc qua Executor

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vị trí của `ExecutorSubscribableChannel` trong Spring Messaging.
- Phân biệt dispatch trực tiếp trên thread gửi với dispatch thông qua `Executor`.
- Hiểu vì sao một message được chuyển đến tất cả subscriber đã đăng ký.
- Đọc đúng ý nghĩa của kết quả `send()`, thứ tự xử lý và exception trong hai chế độ.
- Cấu hình executor có giới hạn bằng `ThreadPoolTaskExecutor`.
- Dùng `ChannelInterceptor` và `ExecutorChannelInterceptor` đúng vòng đời.
- Nhận biết giới hạn về transaction, context, back-pressure và độ bền khi xử lý trên executor.

## 1. ExecutorSubscribableChannel là gì?

`ExecutorSubscribableChannel` nằm trong package:

~~~java
org.springframework.messaging.support.ExecutorSubscribableChannel
~~~

Đây là implementation của `SubscribableChannel`. Một `SubscribableChannel` duy trì danh sách các `MessageHandler` đã đăng ký; khi channel nhận message, nó gọi các handler đó.

Điểm đặc trưng của `ExecutorSubscribableChannel` là **gửi message đến từng subscriber**. Channel có hai cách dispatch:

- Không cấu hình executor: gọi handler trực tiếp trên thread đang gọi `send()`.
- Có cấu hình executor: tạo một task cho từng subscriber và gửi task qua executor được cung cấp.

~~~text
Producer
   |
   | send(message)
   v
ExecutorSubscribableChannel
   |
   +---- Subscriber A
   |
   +---- Subscriber B
   |
   +---- Subscriber C

Không có Executor:
  A -> B -> C được gọi trên thread gửi

Có Executor:
  task A -> Executor
  task B -> Executor
  task C -> Executor
~~~

Vì gửi đến tất cả subscriber, một message có thể kích hoạt nhiều handler. Đây là điểm cần nhớ khi so sánh với channel có cơ chế chọn một consumer.

## 2. Chế độ trực tiếp: xử lý trên thread gửi

Dùng constructor không tham số:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();
~~~

Hoặc truyền `null` làm executor:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(null);
~~~

Khi producer gọi `send(message)`, channel duyệt các subscriber và chạy task của từng subscriber ngay trên thread gọi. Vì vậy:

1. Handler bắt đầu trước khi `send()` trả về.
2. Các handler được gọi lần lượt trong cùng thread.
3. Thời gian chạy của các handler cộng vào thời gian của lời gọi `send()`.
4. Exception từ handler có thể truyền ngược về producer thông qua `send()`.
5. Nếu một handler ném exception, lượt dispatch đồng bộ có thể dừng tại handler đó và các subscriber phía sau không được gọi trong lượt gửi này.

Ví dụ:

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();

channel.subscribe(message ->
        System.out.println("Audit: " + message.getPayload()));

channel.subscribe(message ->
        System.out.println("Metrics: " + message.getPayload()));

channel.send(MessageBuilder.withPayload("ORD-1001").build());
~~~

Kết quả:

~~~text
Audit: ORD-1001
Metrics: ORD-1001
~~~

Hai subscriber đều nhận cùng message. Chúng chạy đồng bộ trên thread gửi; producer chỉ tiếp tục sau khi các handler hoàn tất hoặc có exception làm gián đoạn lượt dispatch.

### Khi nào dùng chế độ trực tiếp?

Chế độ này phù hợp khi:

- Handler nhẹ và cần hoàn tất ngay trong luồng hiện tại.
- Muốn exception từ handler được quan sát ngay tại nơi gọi `send()`.
- Cần một luồng thực thi đơn giản, dễ debug.
- Không muốn thêm executor và chi phí chuyển thread.

Không nên dùng khi handler thực hiện I/O chậm, gọi API ngoài hoặc xử lý CPU nặng làm kéo dài request thread. Một handler chậm sẽ làm chậm producer và các handler được gọi sau nó.

## 3. Chế độ qua Executor

Truyền một đối tượng triển khai `java.util.concurrent.Executor`:

~~~java
Executor executor = Executors.newFixedThreadPool(4);

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);
~~~

Khi `send(message)` được gọi, channel tạo một task cho mỗi subscriber rồi gọi `executor.execute(task)`. Executor quyết định task chạy ở thread nào và vào thời điểm nào.

Với thread pool nhiều worker:

- Các subscriber có thể xử lý đồng thời.
- Producer thường không phải chờ handler hoàn tất.
- Thứ tự hoàn tất không được bảo đảm.
- Executor có thể xếp task vào queue, tạo thread mới hoặc từ chối task theo cấu hình.

Cần phân biệt `Executor` với một thread pool cụ thể. Giao diện `Executor` không bảo đảm chạy bất đồng bộ: một implementation có thể thực thi task ngay trên thread gọi. Ví dụ `Runnable::run` là executor đồng bộ:

~~~java
Executor directExecutor = Runnable::run;

ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(directExecutor);
~~~

Vì vậy, hành vi thread phụ thuộc implementation executor thực tế, không chỉ phụ thuộc việc constructor có nhận tham số hay không.

### Ý nghĩa của send() khi có Executor

Với executor chạy bất đồng bộ, `send()` thường trả về sau khi các task đã được gửi cho executor, trước khi các handler hoàn tất.

`send()` không trả về `Future` của từng subscriber và không cung cấp một kết quả tổng hợp cho biết tất cả handler đã xử lý thành công. Giá trị `true` không phải xác nhận nghiệp vụ rằng mọi subscriber đã hoàn tất xử lý.

Nếu producer cần biết kết quả của công việc bất đồng bộ, hãy thiết kế một cơ chế phản hồi riêng như callback, future do ứng dụng quản lý, reply message hoặc trạng thái lưu trong hệ thống nghiệp vụ.

## 4. So sánh hai chế độ

| Tiêu chí | Không có Executor | Có Executor bất đồng bộ |
|---|---|---|
| Thread chạy handler | Thread gọi `send()` | Thread do executor quyết định |
| Thời điểm chạy | Ngay trong lời gọi gửi | Sau khi task được executor nhận, có thể chạy ngay hoặc muộn hơn |
| Quan hệ với `send()` | `send()` chờ handler chạy xong | `send()` thường không chờ handler hoàn tất |
| Subscriber | Gửi đến từng subscriber | Tạo task riêng cho từng subscriber |
| Đồng thời | Các handler chạy lần lượt | Có thể chạy song song nếu executor có nhiều worker |
| Thứ tự hoàn tất | Theo lượt gọi tuần tự | Không bảo đảm khi chạy song song |
| Exception handler | Có thể truyền về nơi gọi `send()` | Thường xuất hiện trong task/thread của executor |
| Tài nguyên | Dùng thread hiện tại | Dùng thread, queue và tài nguyên của executor |
| Back-pressure | Handler chậm trực tiếp làm chậm producer | Phụ thuộc queue, pool và chính sách từ chối task |

Cấu hình executor một thread vẫn dùng dispatch qua executor, nhưng các task được xử lý lần lượt trên một worker. Executor nhiều thread cho phép xử lý song song, đổi lại phải tính đến race condition và thứ tự hoàn tất.

## 5. Cấu hình bằng Java Configuration

Trong ứng dụng Spring, có thể đăng ký channel và executor thành bean. `ThreadPoolTaskExecutor` là implementation của Spring cho phép cấu hình thread pool, queue và vòng đời shutdown.

~~~java
package demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    public ExecutorSubscribableChannel directOrdersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("messaging-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public ExecutorSubscribableChannel asyncOrdersChannel(
            ThreadPoolTaskExecutor messagingExecutor) {
        return new ExecutorSubscribableChannel(messagingExecutor);
    }
}
~~~

Các điểm cần hiểu:

- `directOrdersChannel` dùng thread gửi.
- `asyncOrdersChannel` dùng `messagingExecutor`.
- `corePoolSize` là số thread lõi.
- `maxPoolSize` là giới hạn số thread tối đa.
- `queueCapacity` giới hạn số task chờ trong queue.
- `threadNamePrefix` giúp nhận biết worker trong log và thread dump.
- `waitForTasksToCompleteOnShutdown` và `awaitTerminationSeconds` hỗ trợ shutdown có trật tự.

Spring quản lý lifecycle của bean `ThreadPoolTaskExecutor`; không cần tự gọi `initialize()` trong phương thức `@Bean`. Khi inject channel theo kiểu, ứng dụng có hai bean cùng kiểu `ExecutorSubscribableChannel`; hãy dùng `@Qualifier` hoặc tên bean để chọn đúng channel.

Ví dụ:

~~~java
@Component
public class OrderPublisher {

    private final ExecutorSubscribableChannel channel;

    public OrderPublisher(
            @Qualifier("asyncOrdersChannel")
            ExecutorSubscribableChannel channel) {
        this.channel = channel;
    }

    public void publish(String orderId) {
        channel.send(MessageBuilder.withPayload(orderId).build());
    }
}
~~~

Cấu hình này không cần `@EnableAsync`. `@Async` là cơ chế proxy method invocation riêng; `ExecutorSubscribableChannel` dispatch các `MessageHandler` đã subscribe thông qua executor được truyền vào constructor.

## 6. Ví dụ Java 17 hoàn chỉnh: quan sát thread và thời điểm send() trả về

Ví dụ dùng Spring Framework 6.2.18 và JDK 17. Chương trình tạo một channel trực tiếp và một channel dùng single-thread executor. Một latch giữ handler bất đồng bộ ở trạng thái chờ để quan sát rằng `send()` có thể trả về trước khi handler hoàn tất.

Cấu trúc thư mục:

~~~text
executor-subscribable-channel-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ExecutorSubscribableChannelDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executor-subscribable-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
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

Tệp `src/main/java/demo/ExecutorSubscribableChannelDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class ExecutorSubscribableChannelDemo {

    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        Message<String> message =
                MessageBuilder.withPayload("ORD-1001").build();

        // Chế độ trực tiếp: handler chạy trên thread gọi send().
        ExecutorSubscribableChannel directChannel =
                new ExecutorSubscribableChannel();

        directChannel.subscribe(incoming ->
                System.out.printf(
                        "direct handler on caller=%s, payload=%s%n",
                        Thread.currentThread() == caller,
                        incoming.getPayload()
                ));

        boolean directSent = directChannel.send(message);
        System.out.println("direct send returned=" + directSent);

        // Chế độ Executor: handler chạy trên worker thread.
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "message-worker")
        );

        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch allowHandlerToFinish = new CountDownLatch(1);
        CountDownLatch handlerFinished = new CountDownLatch(1);

        try {
            ExecutorSubscribableChannel executorChannel =
                    new ExecutorSubscribableChannel(executor);

            executorChannel.subscribe(incoming -> {
                System.out.printf(
                        "executor handler on caller=%s, payload=%s%n",
                        Thread.currentThread() == caller,
                        incoming.getPayload()
                );

                handlerStarted.countDown();

                try {
                    if (!allowHandlerToFinish.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Timed out waiting for the main thread"
                        );
                    }
                    System.out.println("executor handler completed");
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
                finally {
                    handlerFinished.countDown();
                }
            });

            boolean executorSent = executorChannel.send(message);

            if (!handlerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not start");
            }

            System.out.println(
                    "executor send returned before handler completed="
                            + executorSent
            );

            allowHandlerToFinish.countDown();

            if (!handlerFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler did not finish");
            }
        }
        finally {
            allowHandlerToFinish.countDown();
            executor.shutdown();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ExecutorSubscribableChannelDemo
~~~

Kết quả stdout:

~~~text
direct handler on caller=true, payload=ORD-1001
direct send returned=true
executor handler on caller=false, payload=ORD-1001
executor send returned before handler completed=true
executor handler completed
~~~

Cách đọc kết quả:

1. Handler trực tiếp chạy trên cùng thread với `main`.
2. Handler dùng executor chạy trên thread `message-worker`.
3. Handler bất đồng bộ báo đã bắt đầu rồi chờ latch.
4. Main thread quan sát `send()` đã trả về trong khi handler vẫn đang chờ.
5. Main thread mở latch, sau đó handler mới hoàn tất.

Ví dụ này cố ý dùng `CountDownLatch` để chứng minh quan hệ thời gian. Trong ứng dụng thực tế, không nên dùng latch để điều phối message production/consumption nếu không có nhu cầu đồng bộ rõ ràng.

## 7. Một message được gửi đến nhiều subscriber

`ExecutorSubscribableChannel` là channel broadcast theo danh sách subscriber. Mỗi subscriber nhận cùng message đầu vào. Khi có executor, channel tạo task riêng cho từng subscriber.

~~~java
ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel(executor);

MessageHandler auditHandler = message ->
        audit(message.getPayload());

MessageHandler metricsHandler = message ->
        recordMetric(message.getPayload());

channel.subscribe(auditHandler);
channel.subscribe(metricsHandler);

channel.send(MessageBuilder.withPayload("ORD-1001").build());
~~~

Hai handler đều được gọi. Nếu executor có nhiều worker, chúng có thể chạy đồng thời. Vì vậy:

- Không dựa vào thứ tự hoàn tất để thiết lập phụ thuộc nghiệp vụ giữa subscriber.
- Không để nhiều subscriber đồng thời sửa cùng một mutable object nằm trong payload.
- Nếu handler B phải chạy sau kết quả của handler A, hãy tạo flow hoặc orchestration thể hiện quan hệ đó rõ ràng.
- Nếu một message chỉ nên được một consumer trong nhóm nhận, hãy chọn channel có semantics point-to-point phù hợp.

### So sánh với các channel dễ nhầm

| Channel | Module | Phân phối message | Hỗ trợ executor |
|---|---|---|---|
| `ExecutorSubscribableChannel` | Spring Messaging | Tất cả subscriber | Có, qua constructor |
| `DirectChannel` | Spring Integration | Chọn một subscriber cho mỗi message | Không phải cơ chế executor mặc định của channel |
| `PublishSubscribeChannel` | Spring Integration | Tất cả subscriber | Có thể cấu hình TaskExecutor |
| `ExecutorChannel` | Spring Integration | Chọn một subscriber cho mỗi message | Có TaskExecutor |

Tên `ExecutorSubscribableChannel` và `ExecutorChannel` khá giống nhau nhưng semantics phân phối khác nhau. Đọc đúng package và contract của channel trước khi thay thế implementation.

## 8. Exception và xử lý lỗi

### Không có Executor

Trong chế độ trực tiếp, handler được gọi trong thread gửi. Nếu handler ném `MessagingException`, exception có thể truyền về caller. Exception khác có thể được Spring bọc trong `MessageDeliveryException`.

Điều này giúp producer nhận lỗi ngay, nhưng cũng khiến một handler lỗi có thể làm lời gọi gửi thất bại và ngăn các subscriber tiếp theo được gọi trong lượt dispatch.

~~~java
try {
    channel.send(message);
}
catch (MessageDeliveryException ex) {
    // Ghi log, chuyển lỗi hoặc xử lý tại nơi gọi.
}
~~~

### Có Executor

Với executor bất đồng bộ, exception của handler xảy ra trong task chạy trên worker thread. Caller của `send()` thường không nhận được exception đó vì `send()` đã trả về trước khi task hoàn tất.

Cần có chiến lược quan sát và xử lý lỗi phù hợp:

- Bắt exception trong handler khi cần ghi nhận lỗi nghiệp vụ hoặc tạo error event.
- Dùng logging và metrics có correlation ID để theo dõi từng message.
- Cấu hình executor và chính sách uncaught exception phù hợp.
- Nếu cần retry, hãy triển khai retry có giới hạn và có idempotency ở tầng nghiệp vụ.
- Nếu cần phản hồi producer về kết quả xử lý, dùng reply/callback hoặc trạng thái xử lý riêng.

Không nên xem việc executor nhận task là bằng chứng handler đã thành công.

### Khi executor từ chối task

Một executor có thể từ chối task khi đã shutdown hoặc đã hết capacity theo chính sách rejection. Cần hiểu hành vi của implementation Spring đang dùng: trong source hiện hành, `ExecutorSubscribableChannel` bắt `RejectedExecutionException` và chạy task đó trực tiếp trên thread gửi như một fallback. Vì vậy, khi pool quá tải hoặc đang shutdown, handler có thể bất ngờ chạy trên thread producer và làm `send()` kéo dài.

Executor cũng có thể được cấu hình với `CallerRunsPolicy`, tự chạy task trên thread gửi khi bị từ chối. Hãy kiểm thử chính sách thực tế của phiên bản và executor đã chọn; không dựa vào việc mọi handler luôn chạy trên worker thread.

## 9. ChannelInterceptor và ExecutorChannelInterceptor

Spring Messaging cung cấp hai mức interceptor có vòng đời khác nhau.

### ChannelInterceptor

`ChannelInterceptor` quan sát hoặc thay đổi message ở cấp channel, với các callback như:

- `preSend`: trước khi channel gửi message.
- `postSend`: ngay sau khi channel thực hiện send.
- `afterSendCompletion`: sau khi toàn bộ thao tác send hoàn tất hoặc có lỗi.

Với channel dùng executor, các callback quanh `send()` thuộc luồng gửi. Vì vậy `postSend` và `afterSendCompletion` có thể chạy trước khi subscriber hoàn tất xử lý bất đồng bộ.

### ExecutorChannelInterceptor

`ExecutorChannelInterceptor` mở rộng `ChannelInterceptor` và bổ sung callback theo từng subscriber:

- `beforeHandle`: chạy bên trong task, ngay trước khi gọi handler.
- `afterMessageHandled`: chạy bên trong task sau khi handler kết thúc, kể cả khi handler ném exception.

Có thể dùng interceptor này để thiết lập và dọn dẹp context gắn với worker thread, ví dụ MDC hoặc context tùy chỉnh:

~~~java
public class WorkerContextInterceptor
        implements ExecutorChannelInterceptor {

    @Override
    public Message<?> beforeHandle(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler) {
        // Thiết lập context cho subscriber hiện tại.
        return message;
    }

    @Override
    public void afterMessageHandled(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler,
            Exception ex) {
        // Dọn context của worker thread.
    }
}
~~~

Nếu `beforeHandle` trả về `null`, handler tương ứng sẽ không được gọi. Nếu cần dọn tài nguyên, đặt logic trong `afterMessageHandled` và bảo đảm trạng thái context được khôi phục ngay cả khi có exception.

## 10. Thread context và transaction

Chuyển xử lý sang executor đồng nghĩa handler có thể chạy trên thread khác. Không giả định các dữ liệu gắn với thread producer tự động xuất hiện trên worker:

- `ThreadLocal` và MDC không tự được sao chép.
- Security context cần cơ chế truyền context phù hợp nếu ứng dụng yêu cầu.
- Transaction gắn với thread hiện tại không tự chuyển sang worker thread.
- Request-scoped state hoặc context của framework có thể không còn khả dụng.

Nếu handler cần transaction database, hãy tạo transaction tại ranh giới xử lý của handler, ví dụ gọi một service được quản lý bởi Spring với `@Transactional`. Đừng dựa vào transaction của thread đã gọi `send()`.

Có thể dùng `TaskDecorator` của `ThreadPoolTaskExecutor` để sao chép và khôi phục một số context như MDC. Với security context, dùng cơ chế tích hợp của Spring Security thay vì tự copy đối tượng bảo mật một cách tùy tiện.

## 11. Back-pressure, ordering và giới hạn độ bền

### Queue và pool capacity

Executor thường dùng queue để giữ task đang chờ. Nếu producer tạo task nhanh hơn tốc độ worker xử lý, queue sẽ tăng.

Nên cấu hình rõ:

- Core pool size và maximum pool size.
- Queue capacity hữu hạn.
- Rejection policy.
- Thread naming và metrics.
- Shutdown timeout và cách xử lý task còn tồn đọng.

Queue không giới hạn có thể tích lũy task cho đến khi cạn heap. Queue quá nhỏ có thể khiến task bị từ chối thường xuyên. Cần chọn theo thời gian xử lý, tốc độ producer, số subscriber và tài nguyên thực tế.

### Ordering

Khi không có executor, handler được gọi lần lượt trên thread gửi. Khi dùng executor nhiều worker, thứ tự hoàn tất có thể khác thứ tự submit.

Nếu nghiệp vụ yêu cầu thứ tự:

- Dùng executor một thread cho luồng cần tuần tự.
- Dùng khóa hoặc partition theo business key khi cần song song giữa các nhóm nhưng tuần tự trong từng nhóm.
- Thiết kế handler idempotent và kiểm tra version/sequence nếu message có thể đến lệch thứ tự.

Không dùng một executor nhiều thread chung rồi giả định message của cùng một order luôn hoàn tất theo thứ tự gửi.

### Không phải durable messaging

`ExecutorSubscribableChannel` và queue nội bộ của executor nằm trong process hiện tại. Chúng không cung cấp:

- Lưu message bền vững qua restart.
- Redelivery từ broker.
- Dead-letter queue.
- Replay event.
- Giao tiếp giữa các JVM hoặc service.

Nếu ứng dụng dừng khi task còn nằm trong executor queue, task có thể bị mất tùy shutdown policy. Khi cần durable delivery, retry qua broker hoặc trao đổi giữa các process, dùng RabbitMQ, Kafka, JMS hoặc transport phù hợp. Executor chỉ quyết định cách chạy handler trong ứng dụng.

## 12. Lỗi thường gặp

1. **Cho rằng constructor có Executor luôn tạo thread mới.** Executor có thể chạy đồng bộ; kiểm tra implementation được truyền vào.
2. **Cho rằng send() đợi handler hoàn tất trong mọi trường hợp.** Với executor bất đồng bộ, send thường chỉ đợi việc submit task.
3. **Cho rằng một message chỉ tới một subscriber.** ExecutorSubscribableChannel gọi từng subscriber đã đăng ký.
4. **Nhầm với Spring Integration ExecutorChannel.** ExecutorChannel chọn một subscriber cho mỗi message; ExecutorSubscribableChannel gửi tới tất cả subscriber.
5. **Dùng pool không giới hạn.** Task backlog có thể làm tăng heap và độ trễ; cấu hình queue capacity hữu hạn.
6. **Dựa vào thứ tự hoàn tất khi chạy nhiều worker.** Các handler có thể chạy song song và hoàn tất lệch thứ tự.
7. **Chờ exception bất đồng bộ ở caller.** Exception có thể xuất hiện trong worker thread sau khi send đã trả về.
8. **Không xử lý rejection hoặc shutdown.** Task có thể chạy fallback trên caller thread hoặc chịu chính sách từ chối của executor.
9. **Giả định transaction và ThreadLocal được truyền sang worker.** Chúng gắn với thread và cần cơ chế truyền context riêng.
10. **Dùng channel như broker bền vững.** Executor queue ở trong bộ nhớ process; không có durability hoặc replay.
11. **Để subscriber phụ thuộc lẫn nhau nhưng dispatch song song.** Tạo một flow tuần tự hoặc orchestration rõ ràng nếu thứ tự là yêu cầu nghiệp vụ.
12. **Bỏ qua cleanup trong interceptor.** Context hoặc tài nguyên gắn với worker phải được khôi phục ngay cả khi handler lỗi.

## 13. Checklist lựa chọn và vận hành

- [ ] Xác định tất cả subscriber có cần nhận cùng một message hay không.
- [ ] Chọn xử lý trực tiếp nếu handler nhẹ và caller cần chờ kết quả.
- [ ] Chọn executor nếu cần tách thời gian xử lý khỏi thread gửi.
- [ ] Kiểm tra executor có thực sự bất đồng bộ hay có thể chạy task inline.
- [ ] Đặt core pool size, max pool size và queue capacity hữu hạn.
- [ ] Chọn rejection policy và kiểm tra hành vi fallback của phiên bản Spring đang dùng.
- [ ] Xác định cách ghi log và xử lý exception từ worker.
- [ ] Dùng ExecutorChannelInterceptor cho context gắn với từng subscriber khi cần.
- [ ] Thiết kế thứ tự xử lý và tính idempotent cho các handler song song.
- [ ] Tạo transaction tại service xử lý trên worker nếu cần.
- [ ] Theo dõi active threads, queue depth, rejected tasks, processing time và lỗi handler.
- [ ] Chọn broker nếu cần durability, replay, retry bền vững hoặc giao tiếp liên tiến trình.

## 14. Kết luận

`ExecutorSubscribableChannel` là một `SubscribableChannel` của Spring Messaging, gửi mỗi message đến tất cả subscriber đã đăng ký. Constructor không tham số chạy handler trên thread gửi; constructor nhận `Executor` giao việc dispatch cho executor. Chế độ trực tiếp dễ quan sát lỗi và thứ tự nhưng làm producer chờ handler. Chế độ executor tách việc xử lý khỏi producer nhưng đòi hỏi quản lý pool, queue, exception, ordering và context. Hãy nhớ đây là dispatch trong process; khi cần lưu message bền vững hoặc giao tiếp giữa các service, phải dùng transport phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2.18 Javadoc: ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html) — semantics gửi đến tất cả subscriber và hai constructor.
- [Spring Framework 6.2.18 Javadoc: SubscribableChannel](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/SubscribableChannel.html) — đăng ký và hủy đăng ký MessageHandler.
- [Spring Framework 6.2.18 Javadoc: ExecutorChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html) — callback trước và sau khi từng subscriber xử lý message trong executor task.
- [Spring Framework Reference 6.2: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html) — TaskExecutor, ThreadPoolTaskExecutor, queue capacity và rejection policy.
- [Spring Framework Javadoc: ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — cấu hình và quản lý thread pool.
- [Spring Framework source: ExecutorSubscribableChannel](https://github.com/spring-projects/spring-framework/blob/main/spring-messaging/src/main/java/org/springframework/messaging/support/ExecutorSubscribableChannel.java) — cách submit task cho từng subscriber và fallback khi executor từ chối.
