# Đo thời gian send, queue wait và handler execution trong Spring Integration runtime

## 1. Vì sao một con số “message latency” là chưa đủ?

Trong **SPRING_INTEGRATION_RUNTIME**, message đi từ producer qua `MessageChannel`, endpoint, consumer, poller hoặc executor rồi tới handler, message store, transaction, retry và downstream system. Khi người vận hành nói “xử lý một message mất 200 ms”, câu hỏi đầu tiên phải là: **200 ms đo từ đâu đến đâu?**

Ba mốc quan trọng của chương **Hiệu năng → Đo thời gian send, queue wait và handler execution** là:

- **Send duration:** caller mất bao lâu để thực thi `MessageChannel.send(...)` và nhận kết quả hoặc exception?
- **Queue wait / scheduling delay:** message được chấp nhận/đưa vào queue đến lúc consumer bắt đầu xử lý mất bao lâu?
- **Handler execution:** thời gian thực thi code xử lý của handler; có thể đo method body hoặc toàn bộ framework handler invocation tùy điểm đặt probe.

Một flow có `ExecutorChannel` có thể có `send()` rất nhanh nhưng worker queue chờ hàng giây. Một `DirectChannel` có `send()` chậm vì handler chạy **ngay trên thread gửi**. Một `QueueChannel` có thời gian enqueue gần như bằng không khi queue còn chỗ, nhưng poller chỉ lấy message sau một khoảng chờ.

**Không được cộng ba số đo thành end-to-end latency nếu các khoảng thời gian chồng lên nhau.** Với `DirectChannel`, send duration thường **bao trùm** handler execution. Với `QueueChannel`, time từ lúc `preSend` đến handler có thể bao gồm cả lúc sender bị chặn do queue đầy, poller delay và dispatch overhead — không phải thời gian “nằm trong queue” thuần túy.

~~~mermaid
flowchart LR
    P["Producer / gateway"] -->|"send()"| C["MessageChannel"]
    C -->|"admission / enqueue / submit"| Q["Queue hoặc executor"]
    Q -->|"consumer ready"| E["Endpoint"]
    E --> H["Handler method"]
    H --> O["DB / HTTP / output"]
    P -.-> TS["T_send"]
    Q -.-> TW["T_wait"]
    H -.-> TH["T_handler"]
~~~

Bài này xây một mô hình thời gian rõ ràng, hướng dẫn instrument bằng `System.nanoTime()` và Micrometer, đưa ra ví dụ Java 17/Spring Boot có thể chạy thử, rồi hướng dẫn chẩn đoán contention, backlog, transaction, retry, thread và correlation.

## 2. Định nghĩa chính xác các mốc đo

Đặt các mốc sự kiện:

| Mốc | Thời điểm | Nguồn phép đo |
| --- | --- | --- |
| `t0` | Ngay trước caller gọi `send()` | Producer side |
| `t1` | `send()` trả kết quả hoặc throw | Producer side |
| `ta` | Message **được chấp nhận thực sự** vào queue/executor/broker | Admission/enqueue hook hoặc acknowledgement có định nghĩa |
| `td` | Message được dequeue hoặc worker nhận task | Consumer/poller instrumentation |
| `th0` | Handler execution bắt đầu | Handler boundary |
| `th1` | Handler execution kết thúc (thành công hoặc lỗi) | Handler boundary |
| `tc` | Transaction được commit, broker ack hoặc kết quả nghiệp vụ cuối được xác nhận | Durable resource / adapter |

Từ các mốc trên:

\[
T_{\text{send}} = t_1 - t_0
\]

\[
T_{\text{queue wait}} = t_d - t_a
\]

\[
T_{\text{handler}} = t_{h1} - t_{h0}
\]

\[
T_{\text{admission→handler}} = t_{h0} - t_a
\]

\[
T_{\text{end-to-end}} = t_c - t_{\text{ingress}}
\]

Đây là các **định nghĩa logic**, không phải tất cả đều có điểm callback thống nhất trên mọi `MessageChannel` implementation.

### Queue wait không bằng thời gian gửi

Ví dụ một `QueueChannel` còn dung lượng:

~~~text
t0: producer bắt đầu send()
t1: send() trả về sau 0,3 ms
... message nằm trong queue 450 ms ...
td: poller nhận message
th0: handler bắt đầu
th1: handler kết thúc sau 12 ms
~~~

Ta có thể đo `T_send ≈ 0,3 ms`, `T_queue wait ≈ 450 ms` và `T_handler ≈ 12 ms`. Đây là **số giả định minh họa**, không phải benchmark framework. Nếu chỉ nhìn timer của `send()`, sẽ kết luận sai rằng hệ thống rất nhanh trong khi người dùng vẫn chờ gần nửa giây.

### Đo handler body hay toàn bộ endpoint?

Hai định nghĩa có thể khác nhau:

- **Handler method body:** khoảng ngay đầu/cuối code nghiệp vụ do bạn quản lý, chưa chắc bao validation, message conversion, advice, AOP hoặc gửi reply.
- **Integration handler invocation:** khoảng Spring Integration instrument `AbstractMessageHandler` hoặc một endpoint-level observation; có thể gồm wrapper và advice tùy implementation/version.
- **Business completion latency:** có thể kéo dài tới DB commit, HTTP response hoặc broker ack sau handler method return.

Khi tạo dashboard, hãy đặt tên timer phù hợp scope, chẳng hạn `app.handler.body` khác `spring.integration.handler` và `app.order.commit`.

## 3. Loại channel quyết định send() đang đo cái gì

| Channel / ranh giới | `send()` thường chờ gì? | Thời gian sau `send()` | Khi nào suy sai? |
| --- | --- | --- | --- |
| `DirectChannel` | Dispatcher gọi subscriber trên **cùng thread** | Handler có thể đã hoàn tất hoặc ném exception trước khi return | Coi `T_send` chỉ là chi phí enqueue |
| `ExecutorChannel` | Giao dispatch task cho `TaskExecutor` | Worker có thể chưa bắt đầu, còn pending trong executor queue | Coi `send()` thành công là business success |
| `QueueChannel` còn chỗ | Lưu message vào queue | Message chờ `receive()`/poller | Coi enqueue latency là delivery latency |
| `QueueChannel` đầy | Có thể **block** đến khi có chỗ hoặc timeout | Nếu được nhận, consumer vẫn có thể chạy muộn | Đo `send()` chậm nhưng lại đổ cho handler |
| `PublishSubscribeChannel` sync | Thường dispatch tới subscribers đồng bộ | Có thể gồm thời gian nhiều subscribers | Không tính phần đa subscriber/failover |
| Channel dùng broker/network | Tùy implementation và ack policy | Broker queue, consumer lag, redelivery | Coi acknowledgement của producer là consumer commit |

Theo tài liệu Spring Integration, `ExecutorChannel` làm đứt call stack/thread context giữa sender và receiver; một exception ở handler có thể xuất hiện **sau** khi lời gọi `send()` đã trả về. Với `QueueChannel`, nếu queue chưa đầy, `send()` có thể trả về dù chưa có consumer; nếu queue đầy, send có thể block.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as ExecutorChannel
    participant X as TaskExecutor
    participant H as Handler
    P->>C: send(message)
    C->>X: submit dispatch task
    C-->>P: send() returns
    Note over P,H: T_send kết thúc; handler có thể chưa chạy
    X->>H: worker starts
    H->>H: business execution
    H-->>X: returns or throws
~~~

Không dùng một tên timer chung rồi so sánh trực tiếp `DirectChannel` và `ExecutorChannel` mà không ghi **channel type và ranh giới send**.

## 4. DirectChannel: send duration bao gồm handler

Ví dụ:

~~~java
MessageChannel channel = directChannel;
long started = System.nanoTime();

channel.send(MessageBuilder
        .withPayload("ORD-1")
        .build());

long sendNanos = System.nanoTime() - started;
~~~

Nếu subscriber thực hiện HTTP call 250 ms đồng bộ, `sendNanos` có thể xấp xỉ 250 ms hoặc lớn hơn. Đây không phải vì “channel gửi chậm” mà vì `DirectChannel` trao message bằng **direct invocation**.

Mô hình khoảng thời gian:

~~~text
Producer thread:
t0 [send()
      dispatcher
      [handler body 10 ms]
      reply handling / downstream sync
   ] t1
~~~

`T_handler` nằm **bên trong** `T_send`. Vì vậy nếu `T_send=15 ms` và `T_handler=10 ms`, không được ghi end-to-end là 25 ms. Phần `15 - 10 = 5 ms` có thể là dispatcher/advice/conversion/downstream nếu các khoảng đo nằm khớp và không có concurrent work, nhưng phép trừ không phải một metric đáng tin cậy mặc định.

### Exception có đi ngược sender không?

Trên `DirectChannel`, exception từ handler thường truyền ngược call stack nếu không được `RequestHandlerAdvice`, retry/recoverer hay error handler chặn. Nếu đo bằng:

~~~java
long start = System.nanoTime();
try {
    directChannel.send(message);
}
finally {
    long elapsed = System.nanoTime() - start;
    sendTimer.record(elapsed, TimeUnit.NANOSECONDS);
}
~~~

`finally` ghi duration **cả khi thất bại**, nhưng timer không tự mang nhãn `success/failure`. Muốn dashboard tách outcome, chọn timer theo result/exception trong `catch/finally` hoặc dùng Spring Integration metrics/observation đã có convention.

## 5. ExecutorChannel: tách handoff, executor queue wait và handler

Với `ExecutorChannel`, producer giao task rồi thường trả về sớm. Worker thực hiện handler trên thread executor:

~~~text
sender:
  [MessageChannel.send() ----]                         (T_send)
                         |
                         v
executor:
  [pending task ...........................]            (queue wait)
                                       [dispatch]
worker:
                                          [handler body] (T_handler)
~~~

### Những nguồn làm tăng thời gian chờ

- Worker pool có quá ít threads so với arrival rate.
- Handler blocking HTTP/JDBC, timeout dài hoặc retry/backoff trên worker.
- Executor queue quá lớn, việc mới không bị reject nhưng chờ rất lâu.
- Cấu hình `CallerRunsPolicy` có thể khiến task chạy **trên chính sender thread** khi pool đầy, làm `T_send` tăng đột ngột.
- Task executor cạn connection pool khác, khiến worker “active” nhưng không hoàn thành việc.
- Thread scheduling/GC và lock contention.

Một câu hỏi chẩn đoán hữu ích: **`send` nhanh nhưng handler bắt đầu muộn bao lâu?** Khi đo thấy khoảng đó tăng cùng executor queue depth, hướng điều tra thường là saturation ở worker/queue thay vì channel serializer.

### Không tự mang transaction sang worker

`ExecutorChannel` đổi thread; imperative transaction context kiểu JDBC/JPA thường gắn `ThreadLocal` và không được tự truyền cho handler ở worker thread. Một timer của sender không chứng minh transaction trong handler đã hoàn tất. Cần instrument handler + commit boundary, đồng thời định nghĩa error channel và retry riêng.

## 6. QueueChannel và poller: queue wait phụ thuộc lịch nhận

`QueueChannel` là pollable channel. Với consumer polling, message chỉ được xử lý khi poller gọi `receive()` thành công:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel
    participant S as Poller
    participant H as Handler
    P->>Q: send(M)
    Q-->>P: enqueued
    Note over Q: M nằm chờ trong queue
    S->>Q: receive(timeout)
    Q-->>S: M
    S->>H: handle(M)
    H-->>S: done/error
~~~

Thời gian chờ có thể gồm:

1. Dwell time trong queue;
2. Thời gian tới kỳ poll tiếp theo (`fixedDelay`, `cron`, v.v.);
3. Tài nguyên scheduler/poller thiếu;
4. Poller đang xử lý nhiều messages trước đó (`maxMessagesPerPoll`);
5. Kẹt lock hoặc transaction khi nhận từ persistent message store.

Spring Integration cho phép cấu hình `maxMessagesPerPoll` và `receiveTimeout` cho polling endpoint. `receiveTimeout` là thời gian chờ khi **đang receive** không có message; không phải giới hạn tối đa mà message được phép nằm trong queue.

| Trường hợp | `T_send` | `T_queue wait` / từ enqueue đến receive | `T_handler` |
| --- | --- | --- | --- |
| Queue rỗng, poller đang đợi message | Có thể nhỏ | Có thể rất nhỏ sau enqueue | Theo business work |
| Poller chạy mỗi 1 giây | Có thể nhỏ | Có thể đáng kể do lịch poll | Có thể vẫn nhỏ |
| Queue có 10.000 messages backlog | Có thể nhỏ nếu còn capacity | Có thể rất lớn | Không nhất thiết chậm |
| Queue đầy | Có thể tăng do backpressure/block | Có thể tăng | Có thể chậm hoặc không |
| Persistent JDBC store chậm | Có thể tăng do serialize/store write | Có thể tăng do DB dequeue/lock | Có thể vẫn nhỏ |

**Đừng suy từ message timestamps rằng queue wait là `now - headers.timestamp`.** `MessageHeaders.TIMESTAMP` được sinh khi message được tạo, không phải khi nó được enqueue; message có thể đã qua nhiều endpoint trước đó.

## 7. Thước đo nào có sẵn trong Spring Integration?

### 7.1. Micrometer metrics (không dùng observation)

Spring Integration có metrics support khi có `MeterRegistry`. Trong phần Micrometer Integration của tài liệu:

- `spring.integration.send` với tag `type=channel` mô tả send processing time;
- `spring.integration.send` với tag `type=handler` mô tả handler processing time;
- `spring.integration.receive` với tag `type=channel` dành cho receive count ở pollable channels;
- `spring.integration.channel.queue.size` và `spring.integration.channel.queue.remaining.capacity` dành cho `QueueChannel` khi được đăng ký.

Các meter cụ thể phụ thuộc phiên bản, class có hỗ trợ management và việc có dùng **ObservationRegistry** hay không. Không khẳng định tất cả tên này hiện ra đồng thời trên mọi ứng dụng.

### 7.2. Micrometer Observation (Spring Integration 6.x+)

Từ Spring Integration 6.0, `ObservationRegistry` có thể instrument channel, handler, gateway hoặc inbound source theo convention của framework. Tài liệu hiện hành nêu những timer observation quan trọng:

| Observation name | Đo theo ranh giới | Điều không tự có |
| --- | --- | --- |
| `spring.integration.producer` | Channel `send()`/producer operation được instrument | Không tự đo thời gian queue wait |
| `spring.integration.handler` | Handler invocation được instrument | Không tự chứng minh DB commit |
| `spring.integration.gateway` | Gateway request/reply scope | Không tự tách tất cả internal stages |
| `spring.integration.handler.active`, `*.active` tương ứng | Long-running active operation theo convention | Không biến thành queue dwell metric |

Ví dụ cấu hình (cần import đúng các class):

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "*")
class ObservabilityConfig {

    @Bean
    ObservationRegistry observationRegistry(MeterRegistry registry) {
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig()
                .observationHandler(
                    new DefaultMeterObservationHandler(registry));
        return observations;
    }
}
~~~

`DefaultMeterObservationHandler` nằm trong Micrometer core observation package. Đây là cấu hình **minh họa nếu chưa có observation bean khác**; với Spring Boot Actuator, dự án có thể đã có `ObservationRegistry` được auto-configured. Không tạo bean trùng hoặc thay handler tracing sẵn có một cách tùy tiện.

**Rất quan trọng:** tài liệu Spring Integration ghi rằng khi dùng `ObservationRegistry`, các component management **không mặc nhiên được instrument** nếu chưa chọn `observationPatterns`; `"*"` dùng để bật rộng trong môi trường test. Chỉ có registry bean mà không có appropriate `ObservationHandler` cũng **không tự xuất timer tới Prometheus**.

### 7.3. Queue wait không tự động xuất hiện dưới một metric thống nhất

`spring.integration.send` hoặc `spring.integration.producer` không phải tên khác của `queue.wait`. Framework không thể suy thời gian chờ của mọi implementation chỉ từ send timer vì:

- `ExecutorChannel` có queue trong `TaskExecutor`;
- `QueueChannel` có polling consumer với trigger riêng;
- Broker có queue ở server khác và clock khác;
- Message có thể được persist qua restart;
- Có thể có nhiều consumers, priority queue, requeue và redelivery.

Vì vậy nên tạo custom timer **đúng nơi message được enqueue/dequeue** hoặc đặt tên proxy như `admission_to_handler_lag` khi không có hook enqueue chính xác.

## 8. Thiết kế instrumentation không làm sai ý nghĩa latency

Một phương án thực dụng cho flow nội bộ cùng JVM:

1. Producer dùng `System.nanoTime()` trước/sau `send()` để ghi `T_send`.
2. `ChannelInterceptor.preSend()` chèn `perf.preSendNano` ngay trước send.
3. Handler bắt đầu đọc `perf.preSendNano`, ghi một **proxy**: `T_preSend→handlerStart`.
4. Handler đo method body với `Timer.Sample` hoặc `System.nanoTime()` trong `try/finally`.
5. Đo queue size/executor queue depth và poller duration riêng để giải thích thời gian chờ.
6. Khi thật sự cần **queue dwell chính xác**, thêm hook ngay sau enqueue thành công và tại dequeue, hoặc instrument message-store/broker timestamps/ack phù hợp.

### Vì sao preSend timestamp không chính là enqueue timestamp?

~~~text
preSend stamp
    -> serialization / channel interceptor khác
    -> send có thể BLOCK khi queue đầy
    -> actual queue insertion
    -> queue waiting
    -> receive()
    -> handler invocation
~~~

Nếu dùng:

\[
T_{\text{proxy}} = t_{\text{handler start}}-t_{\text{preSend}}
\]

thì `T_proxy` thường bao gồm **send/admission overhead + queue waiting + receive/dispatch overhead**, và có thể bị tăng khi producer bị block trên queue đầy. Đừng đặt nhãn metric là `queue.wait.exact` hoặc coi đây là số nguyên thủy từ broker.

**Tách hai mức quan sát:**

- **Proxy nhẹ:** đủ để phát hiện saturation; đặc biệt hữu ích khi cùng JVM, không cần sửa framework internals.
- **Measurement chính xác:** cần enqueue/dequeue hooks hoặc durable queue/broker metadata với đồng hồ và semantics được xác nhận.

### Lưu ý về đồng hồ

- Dùng `System.nanoTime()` cho **elapsed duration trong cùng JVM**; không so sánh giá trị tuyệt đối hoặc serialize sang một JVM khác.
- Không mang header nanoTime từ producer JVM sang consumer JVM hoặc qua restart: clock origin không tương thích.
- Với broker/multiple nodes, dùng timestamp UTC từ producer/broker và hiệu chỉnh clock skew/NTP, hoặc dùng broker timestamps. Sai số clock giữa nodes có thể lớn hơn `queue wait` cần đo.
- `MessageHeaders.TIMESTAMP` thường là thời điểm tạo message, không đồng nghĩa enqueue.
- Không dùng `System.currentTimeMillis()` để đo thời gian nhỏ trong cùng process khi clock có thể nhảy.
- Đối với negative/giá trị bất thường khi đo từ header, xác minh clock boundary, message age và deployment generation trước khi báo cáo.

## 9. Ví dụ Java 17 + Spring Boot: đo ba thành phần độ trễ

Ví dụ chạy thử bằng Java 17+, Spring Boot, Spring Integration core và Micrometer core. Đặt toàn bộ code vào một file `LatencyMeasurementsApplication.java` thuộc package `demo.integration`.

Mục tiêu:

- Một `ExecutorChannel` có `ThreadPoolTaskExecutor`.
- Một `QueueChannel` có poller.
- Interceptor tạo timestamp `perf.preSendNano` trên hai channel.
- Đo `demo.send`, `demo.preSend_to_handler` (**proxy queue/scheduling delay**), `demo.handler.body`.
- In sample count và mean duration sau khi 24 message đã xử lý.

**Giới hạn có chủ đích:** queue ở đây là in-memory, chỉ chạy **một JVM**, không có broker hay restart; `perf.preSendNano` không được thiết kế để persist/cross-node. Bài này là demo instrument, **không phải benchmark đo số liệu production**.

### 9.1. Code hoàn chỉnh

~~~java
package demo.integration;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableIntegration
public class LatencyMeasurementsApplication {

    static final int PER_CHANNEL = 12;

    public static void main(String[] args) {
        SpringApplication.run(LatencyMeasurementsApplication.class, args);
    }

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean("ordersExecutor")
    ThreadPoolTaskExecutor ordersExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("perf-worker-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(10);
        return pool;
    }

    @Bean("executorOrders")
    MessageChannel executorOrders(
            @Qualifier("ordersExecutor") ThreadPoolTaskExecutor executor) {

        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.addInterceptor(new PreSendNanoInterceptor());
        return channel;
    }

    @Bean("queuedOrders")
    QueueChannel queuedOrders() {
        QueueChannel channel = new QueueChannel(64);
        channel.addInterceptor(new PreSendNanoInterceptor());
        return channel;
    }

    @Bean
    ApplicationRunner benchmark(
            @Qualifier("executorOrders") MessageChannel executor,
            @Qualifier("queuedOrders") MessageChannel queued,
            LatencyHandlers handlers,
            MeterRegistry metrics) {

        return args -> {
            for (int i = 0; i < PER_CHANNEL; i++) {
                sendMeasured(executor, metrics, "executorOrders",
                        "E-" + i);
                sendMeasured(queued, metrics, "queuedOrders",
                        "Q-" + i);
            }

            // Chờ cả hai loại consumer xử lý 24 messages.
            boolean finished = handlers.await(15, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException(
                        "Timed out waiting for handlers");
            }

            for (String channel : List.of(
                    "executorOrders", "queuedOrders")) {

                print(metrics, "demo.send", channel);
                print(metrics, "demo.preSend_to_handler", channel);
                print(metrics, "demo.handler.body", channel);
            }
        };
    }

    private static void sendMeasured(
            MessageChannel channel, MeterRegistry metrics,
            String name, String payload) {

        Message<String> message = MessageBuilder
                .withPayload(payload)
                .setHeader("eventId", "evt-" + payload)
                .build();

        long started = System.nanoTime();
        boolean accepted = false;

        try {
            accepted = channel.send(message, 1_000L);
            if (!accepted) {
                throw new IllegalStateException(
                        "Send timed out: " + name);
            }
        }
        finally {
            long elapsed = System.nanoTime() - started;
            metrics.timer("demo.send",
                    "channel", name,
                    "outcome", accepted ? "success" : "failure")
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }

    private static void print(
            MeterRegistry metrics, String meter, String channel) {

        Timer timer = metrics.find(meter)
                .tag("channel", channel)
                .timer();

        if (timer == null) {
            System.out.printf("%s %s: NO_SAMPLES%n", meter, channel);
            return;
        }

        System.out.printf(
                "%s %s: count=%d mean=%.3fms max=%.3fms%n",
                meter, channel,
                timer.count(),
                timer.mean(TimeUnit.MILLISECONDS),
                timer.max(TimeUnit.MILLISECONDS));
    }
}

final class PreSendNanoInterceptor implements ChannelInterceptor {

    static final String HEADER = "perf.preSendNano";

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        // Trước channel admission, chưa chắc đã enqueue xong.
        return MessageBuilder.fromMessage(message)
                .setHeader(HEADER, System.nanoTime())
                .build();
    }
}

@MessageEndpoint
class LatencyHandlers {

    private final MeterRegistry metrics;
    private final CountDownLatch done =
            new CountDownLatch(LatencyMeasurementsApplication.PER_CHANNEL * 2);

    LatencyHandlers(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @ServiceActivator(inputChannel = "executorOrders")
    public void handleExecutor(Message<String> input) {
        handle("executorOrders", input);
    }

    @ServiceActivator(
            inputChannel = "queuedOrders",
            poller = @Poller(fixedDelay = "50", maxMessagesPerPoll = "8"))
    public void handleQueue(Message<String> input) {
        handle("queuedOrders", input);
    }

    private void handle(String channel, Message<String> message) {

        // Đọc stamp trước khi bắt đầu phần business body.
        Long preSend = message.getHeaders().get(
                PreSendNanoInterceptor.HEADER, Long.class);

        if (preSend != null) {
            long lag = System.nanoTime() - preSend;

            if (lag >= 0) {
                metrics.timer("demo.preSend_to_handler",
                        "channel", channel)
                    .record(lag, TimeUnit.NANOSECONDS);
            }
        }

        long handlerStart = System.nanoTime();
        String outcome = "success";

        try {
            // Mô phỏng I/O 10ms mà không busy-spin CPU.
            LockSupport.parkNanos(
                    TimeUnit.MILLISECONDS.toNanos(10));
        }
        catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        }
        finally {
            metrics.timer("demo.handler.body",
                    "channel", channel,
                    "outcome", outcome)
                .record(System.nanoTime() - handlerStart,
                        TimeUnit.NANOSECONDS);

            done.countDown();
        }
    }

    boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return done.await(timeout, unit);
    }
}
~~~

### 9.2. Chạy với dependency nào?

Mẫu Gradle tương ứng với **Spring Boot BOM** mà dự án lựa chọn:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("io.micrometer:micrometer-core")
}
~~~

Mẫu này chưa gồm build file đầy đủ/plugin; đặt trong dự án Spring Boot đã khai báo Java 17 và plugin/dependency management thích hợp. Nếu Spring Boot auto-configure một `MeterRegistry` qua Actuator, tránh tạo thêm bean trùng trong ứng dụng thật; có thể dùng registry hiện hữu thay `SimpleMeterRegistry`.

**Trong STEP 4, đây là mã để học và thử nghiệm, chưa chạy Gradle/Content QA.** Trước khi đưa vào project cụ thể cần pin version và chạy integration test, đặc biệt nếu ứng dụng dùng Spring Integration 7.x/Boot khác đời.

### 9.3. Dự kiến đọc kết quả

Ví dụ chương trình có thể in:

~~~text
demo.send executorOrders: count=12 mean=...ms max=...ms
demo.preSend_to_handler executorOrders: count=12 mean=...ms max=...ms
demo.handler.body executorOrders: count=12 mean=...ms max=...ms
demo.send queuedOrders: count=12 mean=...ms max=...ms
demo.preSend_to_handler queuedOrders: count=12 mean=...ms max=...ms
demo.handler.body queuedOrders: count=12 mean=...ms max=...ms
~~~

Các số thực **phụ thuộc máy, thread scheduling, timer precision, tốc độ poller**. Không gán một giá trị cố định cho mean/max và không suy từ 12 message rằng đã có benchmark đáng tin cậy.

Kỳ vọng xu hướng:

- `demo.send` trên `ExecutorChannel` nhỏ khi pool chưa bão hòa; nếu queue đầy/rejection thì có thể fail.
- `demo.send` trên `QueueChannel` nhỏ khi còn capacity; có thể block khi đầy.
- `demo.preSend_to_handler` trên `QueueChannel` có thể lớn do polling interval/backlog.
- `demo.handler.body` ở hai đường gần cùng workload (10 ms mô phỏng), nhưng khác nhau do scheduler.

### 9.4. Vì sao dùng `CountDownLatch`?

Một `ExecutorChannel` trả về trước khi handler hoàn tất. Nếu in Timer ngay sau `send()`, sẽ có sample handler **chưa kịp ghi**. `CountDownLatch` đảm bảo demo chờ mọi handler được gọi và đo xong trước khi in count. Không dùng `Thread.sleep(2000)` rồi hy vọng mọi task luôn xong trên máy CI chậm.

**Giới hạn:** `CountDownLatch.countDown()` xảy ra trong `finally` của body. Nếu message bị chặn ngay trước khi vào method (ví dụ conversion/advice error), `done` có thể không về 0, timeout là tín hiệu cần điều tra error path. Với flow transaction/outbound side effect, “handler đã countDown” chưa chắc là business commit thành công.

## 10. Cải thiện độ chính xác phép đo queue wait

### 10.1. Dùng preSend stamp là proxy

Trong ví dụ, `preSend` được thực hiện **trước** khi queue chính thức nhận message. Vì vậy `demo.preSend_to_handler` đo **admission-to-handler proxy**, không phải queue residency chính xác.

Nếu mục tiêu là capacity planning, proxy có ích khi:

- Cả producer và handler nằm cùng JVM;
- Queue không thường xuyên đầy;
- Tính toán so sánh giữa các lần deploy dùng cùng một điểm đo;
- Có queue depth và scheduler metrics để giải thích sự biến động.

### 10.2. Dùng hook enqueue/dequeue thực

Để có `T_queue_wait` đúng theo định nghĩa `td - ta`, hãy đo:

- `ta`: lúc queue/store/broker **xác nhận ghi nhận thành công**;
- `td`: lúc consumer thực sự **lấy item khỏi queue**;
- Cùng một logical message ID nối hai timestamps;
- Với nhiều JVM, đồng hồ/clock skew được kiểm soát hoặc backend cung cấp thời điểm cùng nguồn.

Ví dụ pseudo-code cho queue instrumented:

~~~java
// Sơ đồ API do ứng dụng tự thiết kế, KHÔNG phải API QueueChannel.
void onEnqueueCommitted(String eventId, long monotonicNow) {
    enqueueTimes.put(eventId, monotonicNow);
}

void onDequeued(String eventId, long monotonicNow) {
    Long started = enqueueTimes.remove(eventId);
    if (started != null) {
        timer.record(monotonicNow - started,
                TimeUnit.NANOSECONDS);
    }
}
~~~

Chỉ dùng map/timestamp nanoTime nếu enqueue và dequeue trong **cùng JVM**, không persist qua restart. Với queue có priority/retry/requeue, phải xác định mỗi lần enqueue có một **delivery attempt ID** hay dùng logical event ID: một event có thể vào queue nhiều lần. Cần cleanup map khi timeout/cancel để tránh memory leak.

### 10.3. Tại sao `postSend` cũng chưa đủ?

Một `ChannelInterceptor.postSend()` được gọi sau khi `send()` hoàn tất, nhưng consumer có thể **đã dequeued** message trước lúc callback chạy. Nếu cố gắn timestamp vào message lúc `postSend`, message immutable đã nằm trong queue với headers cũ. Một `ConcurrentHashMap<messageId, timestamp>` cập nhật sau `send()` vẫn có race: consumer có thể tìm timestamp trước khi producer kịp đặt.

Muốn đo queue residency chính xác, cần ràng buộc thời điểm với **cơ chế enqueue/dequeue có synchronization hợp lệ**, không chỉ một interceptor đặt sai vị trí.

### 10.4. Broker và message store

- **Kafka:** record timestamp không mặc định là thời điểm broker đã admit; tùy `CreateTime` hoặc `LogAppendTime`, producer send callback và consumer offset/time.
- **RabbitMQ:** publisher confirms, delivery properties và consumer ack có nghĩa riêng; thời điểm producer được confirm không đồng nghĩa consumer bắt đầu.
- **JDBC queue:** có thể lưu `enqueued_at` cùng row và đo `dequeued_at` khi consumer claim/receive, nhưng phải xét transaction commit và clock.
- **Redis/store khác:** phải instrument đúng operation write/read và TTL/recovery, không giả định adapter đã xuất queue wait.

Những ví dụ trên giải thích semantics chung; implementation cụ thể và broker settings phải được kiểm tra bằng đúng driver/adapter/version.

## 11. Đo handler execution bằng Micrometer Timer

Micrometer `Timer` phù hợp để ghi latency và số operations. Có thể dùng:

~~~java
Timer handlerTimer = Timer.builder("app.handler.execution")
    .description("Business method execution time")
    .tag("handler", "shipping")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(50),
        Duration.ofMillis(200))
    .register(meterRegistry);

handlerTimer.record(() -> processShipment(message));
~~~

Snippet cần import `io.micrometer.core.instrument.Timer`, `java.time.Duration` và bean `meterRegistry`, `processShipment(message)` của ứng dụng. Khi method throw, `Timer.record` vẫn ghi thời gian nhưng muốn tách outcome cần thêm chính sách tags/counter.

Để phân biệt thành công/thất bại:

~~~java
long start = System.nanoTime();
String result = "success";

try {
    processShipment(message);
}
catch (RuntimeException ex) {
    result = "failure";
    throw ex;
}
finally {
    meterRegistry.timer("app.handler.execution",
            "handler", "shipping",
            "result", result)
        .record(System.nanoTime() - start, TimeUnit.NANOSECONDS);
}
~~~

Không đưa `eventId`, raw `correlationId`, `customerId`, payload hoặc exception message làm metric tags vì **cardinality rất cao**. Dùng các nhãn giới hạn như `handler`, `channel`, `result` và `exception.class` (được kiểm soát tập giá trị).

### `Timer.Sample`

Một API tiện lợi:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);

try {
    processShipment(message);
}
finally {
    sample.stop(meterRegistry.timer(
            "app.handler.execution", "handler", "shipping"));
}
~~~

`Timer.Sample` dựa vào clock của registry và thích hợp cho duration của một operation. Không đặt `Timer.Sample` vào headers đi qua broker/store nếu nó không được thiết kế để serialize và dùng xuyên process.

### Histogram và percentiles

Micrometer hỗ trợ:

- **Count / total time:** số invocation và tổng thời gian.
- **Mean:** tổng duration / count.
- **Max:** giá trị quan sát trong một cửa sổ/tùy registry.
- **Client-side percentiles** (`publishPercentiles`) theo meter ID, thường không thể gộp chính xác giữa instances.
- **Percentile histograms** (`publishPercentileHistogram`) cho backend hỗ trợ aggregate buckets (ví dụ Prometheus); query `histogram_quantile(...)` trên buckets được cộng phù hợp.

**Không lấy `p95(send) + p95(wait) + p95(handler)` làm `p95(end-to-end)`.** Percentiles là đặc tính phân bố, các samples không nhất thiết tương ứng cùng một message, và các khoảng có thể chồng nhau.

## 12. Đo end-to-end latency với event identity

Một request có thể đi qua:

~~~mermaid
flowchart LR
    G["Gateway ingress"] --> Q["QueueChannel"]
    Q --> P["Poller"]
    P --> H["Handler"]
    H --> DB["Database commit"]
    DB --> OUT["Reply / acknowledgement"]
~~~

Nếu SLA là “từ message vào hệ thống đến khi order commit trong DB”, điểm kết thúc phải là **sau commit**. Nếu SLA là “từ gateway request đến khi client nhận response”, điểm kết thúc là gateway reply/HTTP response.

Đo end-to-end bằng spans/trace context hoặc một application-specific timer tại đúng boundary. Với một transaction:

~~~text
handler method returns
   -> transaction interceptor commits
   -> message broker ack
~~~

Số `T_handlerBody` không bao gồm bước commit/ack nếu method đã trả trước. Observation của endpoint cũng không mặc nhiên là “transaction committed”. Test bằng DB/broker thực mới xác nhận được milestone.

### `eventId` và `correlationId` phục vụ việc gì?

- `eventId`: nhận dạng **logical event**, ổn định khi retry/replay.
- `correlationId`: nối các messages cùng workflow hoặc aggregator group.
- `deliveryAttemptId`: phân biệt những lần giao lại nếu cần đo queue wait theo attempt.
- `traceId`: nối các spans giữa process.
- `MessageHeaders.ID`: ID của một Message instance, có thể đổi khi được dựng lại.

Dùng các ID này để liên kết **logs/traces**, không làm metric tags cho time series. Nếu event được retry nhiều lần, hãy xác định SLA đo theo **first ingress** hay **final successful attempt**.

## 13. Little’s Law, capacity và backlog

Với hệ thống **ổn định** theo khoảng quan sát đủ đại diện, Little’s Law:

\[
L = \lambda W
\]

Trong đó:

- `L`: số work items trung bình trong hệ thống/queue đang xét;
- `λ`: throughput hoàn thành trung bình;
- `W`: thời gian lưu trú **trung bình** trong phạm vi đó.

Ví dụ một queue ổn định xử lý 200 message/s và thời gian đợi trung bình 0,5 s có:

\[
L \approx 200 \times 0{,}5 = 100 \text{ message}
\]

Đây không có nghĩa p95 wait bằng 0,5 s, cũng không đúng nguyên xi khi arrival vượt service rate và queue **đang tăng không ngừng**.

Nếu arrival là 300 message/s nhưng consumer hoàn tất tối đa 200/s trong giai đoạn quá tải:

~~~text
Backlog growth ≈ 300 - 200 = 100 messages/s
Sau 60 giây ≈ 6.000 messages tồn thêm nếu không có drop/backpressure.
~~~

Con số trên là mô hình định lượng minh họa, chưa tính retry, priority và những nguồn chuyển trạng thái khác.

### Ước lượng worker cần thiết

Nếu một handler có **thời gian chiếm worker** trung bình `S=50 ms`, mỗi worker lý tưởng hoàn thành khoảng 20 tasks/s. Để giữ 200 tasks/s cần ít nhất khoảng 10 workers **trong mô hình không có overhead/contestion**.

Tăng lên hơn 10 workers vẫn có thể thất bại nếu:

- DB connection pool chỉ có 5 connections;
- Cùng một `LockRegistry` key làm critical section tuần tự;
- Broker/remote API rate limit;
- Retry multiplier làm số attempts gấp ba;
- Workload p99 rất dài hoặc heap/GC làm scheduler pause.

Do đó nên đo `handler body duration`, executor active/queued, queue wait và downstream saturation **cùng lúc**.

## 14. Đọc percentiles đúng để tìm nơi nghẽn

| Tình huống | `T_send` | `T_preSend→handler` | `T_handler` | Hướng điều tra |
| --- | --- | --- | --- | --- |
| DirectChannel + slow HTTP | Cao | Không phải thước đo queue phù hợp | Cao | HTTP/downstream |
| ExecutorChannel pool đầy | Có thể thấp hoặc fail | Cao | Bình thường | Worker saturation, queue |
| QueueChannel poller chạy thưa | Thấp | Cao | Bình thường | Poll interval, maxMessagesPerPoll |
| QueueChannel capacity đầy | Cao do block | Có thể cao | Bình thường | Backpressure, backlog |
| Handler chậm do DB lock | Có thể cao ở DirectChannel | Có thể cao ở async backlog | Cao | DB lock/transaction |
| Redis/JDBC message store chậm | Có thể cao | Có thể cao | Bình thường | Store I/O, serializer |
| Retry/backoff dài trong handler | Tùy channel | Backlog tăng | Tùy điểm đặt timer | Retry policy/attempts |
| Nhiều event chung correlation | Tùy channel | Tăng | Có thể tăng | Aggregator LockRegistry contention |

**Đừng so sánh p95 giữa hai timer lấy trên các tập message khác nhau** và kết luận trực tiếp nguyên nhân. Cùng khoảng load, cùng version, cùng label scope và thống nhất sampling/retention mới có giá trị.

### Head-of-line blocking

Một queue FIFO có một consumer: một message xử lý 5 s có thể khiến các message nhỏ phía sau chờ, dù handler body của chúng chỉ 5 ms. Lúc đó:

~~~text
message A: handler=5000ms
message B: wait=5000ms, handler=5ms
message C: wait=5005ms, handler=5ms
~~~

Tăng concurrency có thể giảm head-of-line blocking nếu messages độc lập; nhưng với aggregator/correlation group có state chung, phải bảo vệ thứ tự và locking. Đừng mở concurrency vô hạn khi downstream giữ state.

## 15. Threading, transaction, retry và lỗi khi đo

### 15.1. Thread boundary

| Ranh giới | Điều xảy ra | Hệ quả instrumentation |
| --- | --- | --- |
| `DirectChannel` | Thường cùng thread producer-handler | Có thể measure đồng bộ; send duration bao handler |
| `ExecutorChannel` | Handler chạy trong worker thread | Stamp/trace context phải đi theo message hoặc qua propagation |
| `QueueChannel` + poller | Handler chạy trong poller task | Admission và handler nằm ở các thời điểm khác nhau |
| Reactive publisher | `publishOn`/`subscribeOn` thay scheduler | Context Reactor, lazy subscription, nonblocking |
| Broker | Khác process/node | Không dùng System.nanoTime header qua nodes |

MDC/ThreadLocal thông thường **không tự xuyên** mọi asynchronous boundary. Dùng message headers, Micrometer Observation context propagation hoặc Reactor Context phù hợp; nếu cần đo cross-process, truyền `traceId`/`eventId` và đo theo broker timestamps hoặc traces.

### 15.2. Transaction

`@Transactional` kiểu imperative gắn thread. Một `ExecutorChannel` đổi thread khiến transaction của sender không tự bao handler. Nếu queue nhận xong nhưng handler rollback, message có được requeue hay không phụ thuộc **transaction của nguồn/poller, ack policy và store**.

Ví dụ đo:

~~~text
t0 send start
t1 QueueChannel stored message
t2 poller receives
t3 handler starts
t4 handler returns
t5 transaction commits
t6 broker ack
~~~

Nếu mục tiêu của SLA là durable completion, đo tới `t5`/`t6`; handler body timer chỉ tới `t4`.

### 15.3. Retry và recovery

Khi `RequestHandlerRetryAdvice` thực thi ba attempts, cần xác định:

- Timer bọc **toàn advice** hay từng attempt riêng?
- Backoff có nằm trong `T_handler` không?
- Có re-enqueue message giữa attempts không?
- Nếu exception được recovery callback nuốt, outcome được ghi là success hay recovered?
- Sự kiện bị replay từ broker có ID/timestamps cũ hay mới?
- Retry vào error channel có bị tính như một handler execution khác không?

Dùng hai thước đo khi cần:

~~~text
app.handler.attempt.duration    // mỗi lần xử lý nghiệp vụ
app.handler.logical.duration    // toàn bộ retry/recovery boundary
~~~

Với một logical event có ba attempts, `attempt.count` có thể là 3 trong khi `logical.count` là 1. Đừng lấy số lần timer của endpoint làm số message **duy nhất** đã xử lý.

### 15.4. ErrorMessage

Nếu handler throw trên `ExecutorChannel` hay poller, error handler có thể publish `ErrorMessage`. Lỗi xảy ra **sau** khi `send()` của producer đã ghi thành công, nên `demo.send` vẫn có outcome success theo nghĩa **handoff accepted**.

Muốn báo cáo outcome nghiệp vụ, phải lấy từ handler/recovery/commit. Một `ErrorMessage` chỉ là message mang exception; nó không tự chứng minh nguồn đã rollback hoặc được ghi vào DLQ bền vững.

## 16. Tracing và message history hỗ trợ phân tích khoảng chờ

Tại môi trường production, custom latency timers nên kết hợp:

- **Distributed trace:** spans cho inbound → queue boundary → handler → DB/API, với traceId nối cross-process.
- **Message history:** liệt kê tracked components qua `history` header, có timestamp ở mỗi hop.
- **Executor/poller metrics:** queue depth, active workers, task rejection, poll duration.
- **Message store metrics:** write/read duration, oldest pending message age.
- **Business event state:** eventId, correlation, transaction commit và idempotency.

**Message history timestamp gap không tự là queue wait chính xác.** Hai history entries có thể cách nhau lâu do poller, retry, I/O hoặc thread scheduling. History là bản đồ đường đi, không phải profiler thời gian handler.

### Span hierarchy và queue duration

Một span publisher đo `send()` sẽ kết thúc trước span handler ở async flow. Nếu chúng không có context propagation đúng, traces có thể bị tách thành hai cây. Khi cần quan sát “time in queue”, dùng **span/event timestamp** được tạo tại enqueue/dequeue theo contract, không tính từ thời điểm log tùy ý.

Đối với cross-node telemetry, đồng hồ UTC có thể lệch và exporter có batch delay; cần phân biệt **event timestamps** với thời điểm backend nhận telemetry.

## 17. Benchmark đáng tin cậy khác demo console

Demo mục 9 chỉ tạo 24 messages và chạy một lần; nó minh họa phép đo, không thể kết luận throughput/p99.

Quy trình benchmark tốt hơn:

1. **Khởi động và warm-up** JVM, JIT, caches, connection pools trước khi thu sample.
2. Xác định **workload**: payload sizes, tỷ lệ CPU/I/O, hot correlation keys, số messages/s.
3. Đo arrival rate **bên ngoài** và throughput commit/complete **thực**.
4. Thu các latency distributions theo cùng time window: send, queue wait, handler, end-to-end.
5. Ghi CPU usage, GC, heap, thread count, executor queue, DB/Redis connection pool.
6. Tách steady state với ramp-up/ramp-down; đừng gộp cả hai rồi lấy mean.
7. Chạy nhiều lần, giữ nguyên hardware/limits, pin versions và config.
8. Thử cả **open-loop** (arrival không đợi response) và **closed-loop** (client đợi completion) tùy traffic production.
9. Ghi lỗi, timeouts, retries, rejects, dropped messages — không chỉ các requests thành công.
10. Có tiêu chí kết thúc: SLA/SLO và nguồn dữ liệu đủ để điều tra sai lệch.

### Coordinated omission

Nếu load generator chỉ gửi request mới **sau khi request cũ hoàn tất**, khi hệ thống dừng/GC, nó **không gửi** những messages lẽ ra đã đến trong khoảng tắc. Latency samples có thể trông tốt hơn tình hình production. Với arrival rate thực tế độc lập, cần mô phỏng open-loop và xem queue backlog/tail latency. Micrometer có cơ chế pause detection phù hợp một số trường hợp, nhưng không thay thế mô hình tải đúng.

### Rủi ro overhead instrumentation

- Thêm một header mới trên mọi message làm tăng allocations/serialization.
- Capture `System.nanoTime()` thường nhẹ nhưng logging đồng bộ mỗi message có thể rất đắt.
- Histogram buckets và high-cardinality tags có chi phí memory và số time series.
- AOP/advice và tracing hooks có thể thay đổi timing; cần đo overhead của việc bật instrumentation.
- Một `SimpleMeterRegistry` lưu metrics trong process, không phải một exporter backend production.
- Thời gian từ tracer span start/stop có thể khác handler body nếu span bao converter/advice/reply.

## 18. Những lỗi đo lường thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `send()` nhanh nên “xử lý message nhanh” | Với async channel, chỉ handoff thành công | Đo từ enqueue/receive tới handler và completion |
| `send()` chậm chắc do queue | DirectChannel có thể chạy handler sync | Kiểm tra channel type, handler body |
| Lấy `MessageHeaders.TIMESTAMP` làm enqueue time | Timestamp thường khi tạo message | Instrument điểm enqueue thực |
| Mang `System.nanoTime()` header qua Kafka hoặc restart | Đồng hồ monotonic khác JVM | Dùng clocks/backend timestamps và điều chỉnh skew |
| Gọi `preSend` stamp là queue wait chính xác | Stamp trước enqueue/blocking | Gọi là admission-to-handler proxy |
| Dùng `postSend` map làm bằng chứng queue dwell | Consumer có thể dequeue trước postSend | Hook atomic enqueue/dequeue |
| `p95(send)+p95(wait)+p95(handler)=p95(total)` | Percentile không cộng tuyến tính, intervals có thể overlap | Đo end-to-end trực tiếp |
| Dùng `Thread.sleep()` trong async integration test | Flaky, vừa chậm vừa thiếu đảm bảo | `CountDownLatch`, `QueueChannel.receive(timeout)`, Awaitility |
| Chỉ đo success | Bỏ sót timeout/retry/reject và failed queue dwell | Ghi outcome/failures có cardinality thấp |
| Timer count coi là unique messages | Retry/duplicate làm count tăng | Thêm logical eventId và attempt counts riêng |
| Chỉ có ObservationRegistry đã có Prometheus timer | Chưa có ObservationHandler/exporter/pattern | Kiểm tra wiring metrics/traces |
| In từng full payload để debug latency | Log I/O làm thay đổi throughput | Structured sampling, metrics, traceId |
| Dùng average thay p99 | Tail latency có thể rất lớn | Histogram/percentiles, service-level buckets |
| Chỉ nhìn executor active threads | Workers có thể chờ lock/DB connection | Đo lock wait, DB pool, queue age |
| Thay capacity không kiểm tra durability | Queue đầy/đổ tràn hoặc restart mất messages | Bounded queue + backpressure/store/policy |

## 19. Kiểm thử các phép đo không bị flake

### Test 1: xác minh đúng số samples

Sau khi demo chạy xong 12 messages cho mỗi channel:

~~~java
Timer executorBody = registry.find("demo.handler.body")
        .tag("channel", "executorOrders")
        .tag("outcome", "success")
        .timer();

assertNotNull(executorBody);
assertEquals(12L, executorBody.count());
~~~

Đây là **JUnit assertion bổ sung**, cần tham chiếu tới `registry` của ứng dụng và imports JUnit thích hợp. Nó chứng minh handler đã ghi samples, không chứng minh mọi message đã commit một giao dịch bên ngoài.

### Test 2: `send()` khác handler execution

Trong test `ExecutorChannel`, dùng `CountDownLatch` để giữ một handler chưa hoàn thành:

~~~java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(1);

// Handler test:
MessageHandler blocking = message -> {
    started.countDown();

    try {
        if (!release.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out in test");
        }
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted", ex);
    }
    finally {
        finished.countDown();
    }
};
~~~

Đây là fragment cho một test harness đã gắn `blocking` vào `ExecutorChannel` với `TaskExecutor` phù hợp. Test gửi message rồi xác nhận `send()` đã return trong khi `finished` vẫn chưa hoàn tất, sau đó `release.countDown()` và `finished.await(...)`. Không test bằng cách so hai duration cố định theo milliseconds.

**Cẩn thận:** nếu executor cấu hình `CallerRunsPolicy`, handler có thể được chạy trên sender thread khi pool đầy. Khi đó `send()` cũng block; bài test phải dùng executor còn capacity và rejection policy rõ ràng.

### Test 3: queue wait và lịch poll

Dùng `QueueChannel` có capacity cố định, gửi message khi consumer **chưa start**, đợi/khởi động poller theo điều khiển test, rồi xác minh message vẫn trong queue và handler được gọi sau. Đo admission-to-handler proxy và chỉ assert **tính hợp lệ/đúng chiều**, không assert đúng một số milliseconds phụ thuộc scheduler.

### Test 4: failure, retry và telemetry

Tạo handler ném exception một số attempts trước khi thành công. Đếm:

- `send` accepted/failure theo channel;
- Handler attempts và kết quả cuối;
- ErrorMessage/recovery nếu cấu hình;
- Transaction rollback/commit trong backing DB;
- Retry backoff, queue age và tail latency.

Không kỳ vọng mọi timer count bằng nhau: chúng đo **những scope khác nhau**.

## 20. SLO, dashboard và alert cho một flow thực tế

Ví dụ flow nhận order và ghi DB:

~~~text
HTTP/JMS source → QueueChannel → Poller → Handler → JDBC commit
~~~

Một dashboard tốt có ít nhất:

| Nhóm | Chỉ số | Mục đích |
| --- | --- | --- |
| Ingress | accepted/s, rejected/s | Tải đầu vào và backpressure |
| Send | p50/p95/p99 `T_send`, failures | Producer đang bị block/throw không |
| Queue | pending count, oldest age, p95 queue lag | Có backlog và consumer lag không |
| Handler | p50/p95/p99 body execution, attempts, failures | Business work có chậm không |
| End-to-end | p95/p99 từ ingress đến commit/ack | SLA người dùng thực sự |
| Runtime | executor active/queued/rejected, poller duration | Thread/scheduler saturation |
| Dependencies | DB pool wait, query latency, HTTP duration | Bottleneck phía dưới |
| Reliability | retries, dead-letter, redelivery, duplicates | Latency có đi kèm mất dữ liệu không |
| Correlation | group size/age, lock wait/hold | Aggregator bị hot key hoặc deadlock không |

### SLO phải có điểm bắt đầu/kết thúc rõ

Ví dụ (chỉ minh họa):

- `p95(end-to-end accepted→DB commit) < 500 ms`;
- `p99(queue admission→consumer start) < 100 ms` trong steady state;
- `99,9%` accepted messages có outcome cuối trong 30 giây;
- `rejected messages` được theo dõi và có retry/dead-letter policy.

Nếu không định nghĩa “accepted”, “consumer start” và “commit” bằng các event chính xác, dashboard có thể đẹp nhưng SLO không thể kiểm chứng.

### Chẩn đoán theo thứ tự

1. **Phạm vi:** metric đang tính từ đâu đến đâu? Channel sync hay async?
2. **Triệu chứng:** send p99, queue lag p99, handler p99 cái nào tăng trước?
3. **Saturation:** queue depth, executor occupancy, poller interval, DB pool.
4. **Dependencies:** API latency, lock registry, message store read/write, GC.
5. **Failures:** retry attempts, timeout, channel rejection, errorChannel.
6. **Data correctness:** broker ack, DB commit, duplicate/replayed events.
7. **Can thiệp:** sửa đúng nút thắt (backpressure, worker pool, SQL, concurrency, batch/poller).
8. **Đo lại:** cùng workload và time windows, có rollback plan nếu lỗi tăng.

## 21. Bài thực hành

1. **DirectChannel:** gắn handler mô phỏng I/O 100 ms, đo send duration và handler body; giải thích vì sao chúng chồng lên nhau.
2. **ExecutorChannel:** dùng chương trình mục 9, tăng `PER_CHANNEL` và giảm pool size; đo `preSend_to_handler` và saturation.
3. **QueueChannel:** thay `fixedDelay` từ 50 ms thành 500 ms; xem queue lag và throughput thay đổi.
4. **Backpressure:** giảm queue capacity xuống 2, gửi nhiều messages; ghi send blocked/rejected và số message đã được xử lý.
5. **CallerRunsPolicy:** thay executor rejection policy rồi gây saturation; quan sát lúc nào sender thread thực thi handler.
6. **Handler body:** tăng simulated work từ 10 ms lên 100 ms; đo handler duration và queue backlog.
7. **Poller:** thay `maxMessagesPerPoll`, ghi cùng lúc backlog, completion rate và error rate.
8. **Queue wait semantics:** thay interceptor `preSend` bằng hook enqueue/dequeue trong test queue do ứng dụng kiểm soát; so sánh proxy với dwell time thực.
9. **Timer:** thêm histogram/SLO buckets; xem p95/p99 khi một nhóm messages rất chậm.
10. **Retry:** làm handler lỗi hai attempts rồi thành công; so sánh attempt timer và logical operation timer.
11. **Transactions:** ghi DB sau handler; đo tới commit, cố tình rollback và kiểm tra end-to-end outcome.
12. **Executor error:** cho handler throw sau khi send accepted, kiểm tra vì sao `send` vẫn có outcome success nhưng handler timer/report failure.
13. **Message store:** đổi QueueChannel in-memory sang persistent implementation trên môi trường test; kiểm tra khi restart, message age và header serialization.
14. **Cross-node:** đưa producer và consumer sang hai JVM rồi thử đọc `System.nanoTime` header; phân tích vì sao duration không hợp lệ.
15. **Metrics cardinality:** cố ý tag mỗi eventId lên timer trong môi trường test, quan sát số meter IDs tăng; thay bằng channel/outcome tags.
16. **Trace:** dùng Micrometer Observation và tracing để xác minh context propagation qua executor.
17. **Hot correlation key:** thêm aggregator với nhiều messages cùng correlationId; đo lock wait, group age và throughput.
18. **Load test:** so sánh một closed-loop generator với open-loop arrival ở cùng advertised rate; tìm coordinated omission.
19. **Operational dashboard:** dựng 4 hàng: send p95, queue lag p95, handler p95 và end-to-end p95; bổ sung success/error/retry rates.
20. **Runbook:** mô phỏng queue wait p99 tăng nhưng handler body giữ nguyên; viết quy trình tìm nguyên nhân không sửa sai DB.

### Câu hỏi tự kiểm tra

- Vì sao `DirectChannel.send()` có thể lâu bằng handler?
- Vì sao `ExecutorChannel.send()` trả thành công chưa chắc handler đã xong?
- Với QueueChannel đầy, `T_send` có thể tăng mà `T_handler` không đổi không?
- `preSend` stamp chính xác tới thời điểm queue admission chưa? Vì sao?
- Tại sao `postSend` lưu timestamp vào map vẫn có race?
- `MessageHeaders.TIMESTAMP` khác enqueue timestamp ở điểm nào?
- Có thể dùng `System.nanoTime()` xuyên hai JVM hoặc restart không?
- Tại sao `p95(send) + p95(wait)` không phải p95 của tổng?
- Little’s Law dùng **mean** hay **p99** queue wait?
- Nếu handler có ba retry attempts, timer ở advice ngoài có nhất thiết ba samples không?
- Observation Registry có mặc định xuất timers không?
- Làm sao chứng minh business commit sau khi handler method đã return?

## 22. Checklist trước khi chuyển QA

- Đã định nghĩa rõ `T_send`, `T_queue_wait`, `T_handler`, `T_end-to-end`.
- Chọn metric names và scope đúng với `DirectChannel`/`ExecutorChannel`/`QueueChannel`.
- Không gán preSend-to-handler proxy là queue residency chính xác.
- Có sample duration cho cả success và failure.
- Dùng `System.nanoTime` chỉ trong cùng JVM, không persist xuyên restart/broker.
- Micrometer metrics/Observation patterns và handlers được cấu hình đúng.
- Có queue depth, worker pool và poller metrics để diễn giải queue lag.
- Đo latency distribution và percentiles theo cùng workload/time window.
- Không cộng các p95 hoặc những khoảng duration chồng nhau.
- Retry/transaction/ack/idempotency được kiểm chứng tại boundary nghiệp vụ.
- Không dùng eventId hoặc payload làm metric labels.
- Async tests dùng latch/receive timeout, không sleep cố định.
- Có cảnh báo backpressure, retry storm và lost-message risk.
- Benchmarks được đánh dấu minh họa nếu chưa chạy trên đúng hạ tầng.
- Không chạy STEP 6/Gradle/Python ở bước authoring này.

## 23. Nguồn tham khảo chính thức

- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): `spring.integration.send`, `spring.integration.receive`, Observation API và conventions cho producer/handler.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, QueueChannel, ExecutorChannel và blocking semantics.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): QueueChannel capacity, executor dispatch và boundary transaction.
- [Spring Integration — Message Endpoints / Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): `maxMessagesPerPoll`, `receiveTimeout`, scheduling và transaction support.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): queue persistence, MessageGroupStore và durability.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): errorChannel, exception flow qua async boundary.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): history header và tracked component timestamps.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer.record`, `Timer.Sample`, duration units.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): client percentiles, percentile histograms và SLO buckets.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): registry, observation handler và context.
- [Spring Framework — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html): `send(message)` và `send(message, timeout)`.
- [Spring Framework — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html): `preSend`, `postSend` và `postReceive` callbacks.
