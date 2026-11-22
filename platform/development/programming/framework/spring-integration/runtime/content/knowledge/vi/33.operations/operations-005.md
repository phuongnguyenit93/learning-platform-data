# Restart endpoint và reconnect producer trong Spring Integration runtime

## 1. Phân biệt restart, reconnect và replay

Trong module **SPRING_INTEGRATION_RUNTIME**, một message flow được điều phối qua `MessageChannel`, endpoint, consumer, poller và executor, rồi đi tới handler, transaction, message store hoặc một hệ thống bên ngoài. Khi kết nối TCP, MQTT hoặc broker bị gián đoạn, người vận hành có thể nói “restart producer”, nhưng câu này chứa **ba hành động có phạm vi khác nhau**:

1. **Restart endpoint:** gọi `stop()` rồi `start()` trên bean có lifecycle, nhằm dừng và mở lại việc nhận/phát message theo contract của component.
2. **Reconnect transport:** tạo lại connection/socket/session của adapter hoặc connection factory, nhiều khi không phải restart toàn endpoint.
3. **Retry hoặc replay logical message:** gửi lại một event đã nhận nhưng chưa có outcome chắc chắn; cần xác định acknowledgement, transaction, message store và idempotency.

Đây là nội dung trực tiếp của chương **Vận hành → Restart endpoint và reconnect producer**. Mục tiêu là vận hành có bằng chứng: chọn đúng đối tượng, kiểm tra trạng thái, xử lý message in-flight, phục hồi connection và xác nhận business outcome, không chỉ gọi một method rồi coi là thành công.

**Nguyên tắc then chốt:** `isRunning() == true` không đồng nghĩa socket đã connected. Socket connected không đồng nghĩa remote peer đã xử lý message. `retryConnection()` không có nghĩa đã replay message bị lỗi trước khi connection mất.

~~~mermaid
flowchart TD
    S["Source / producer"] --> A["Adapter / endpoint"]
    A --> L["Lifecycle: running?"]
    A --> T["Transport: connected?"]
    A --> M["Message outcome: ack/commit?"]
    L --> O["stop() / start()"]
    T --> R["Reconnect policy / retryConnection()"]
    M --> P["Retry / replay + idempotency"]
    O --> V["Validation"]
    R --> V
    P --> V
    V --> H["Healthy processing, không mất/trùng event"]
~~~

Các phần dưới dùng Java 17+, Spring Integration 6.x/7.x, với ghi chú về API thay đổi theo version. Ví dụ TCP cần `spring-integration-ip` và một TCP server test. Bài tập này **không** chạy Gradle hoặc QA học thuật STEP 6.

## 2. “Producer” là inbound producer hay outbound sender?

Trong Spring Integration, inbound adapter thường **produce** message vào channel; outbound handler thì **send** message tới hệ thống khác. Với TCP, có thể có cả inbound adapter chủ động kết nối server để nhận dữ liệu và outbound adapter chủ động tạo client connection khi start.

| Component | Đường đi | Đối tượng quản lý | Recovery thường dùng |
| --- | --- | --- | --- |
| `EventDrivenConsumer` + `DirectChannel` | Channel → handler | Consumer endpoint/subscription | `start()/stop()`, không có socket |
| `SourcePollingChannelAdapter` | Remote source → channel | Poller, message source, session factory | Poller lifecycle và session recovery |
| TCP inbound adapter server mode | TCP peer → inbound channel | Server connection factory/listener | Listener lifecycle và TCP events |
| TCP inbound adapter `client-mode=true` | Client connect tới peer rồi nhận | Client-mode adapter/connection factory | Reconnect client-mode khi running |
| TCP outbound adapter `client-mode=true` | Channel → TCP server | `TcpSendingMessageHandler` và client factory | Scheduler, `retryConnection()` |
| JMS/AMQP listener | Broker → message flow | Listener container/connection factory | Container recovery + ack/requeue |
| MQTT inbound/outbound | Broker ↔ flow | MQTT client/adapters | Paho automatic reconnect hoặc lifecycle |
| HTTP outbound handler | Flow → HTTP API | HTTP client/pool | Request retry, connection pool, không mặc định stop endpoint |

**Không xây một phương thức chung kiểu `allProducers.reconnect()` rồi giả định mọi adapter có cùng API.** Với mỗi flow, trước tiên xác định tên bean thực sự sở hữu connection, endpoint lifecycle, channel và adapter version.

## 3. Ba trục trạng thái cần theo dõi

| Lifecycle | Connection health | Business outcome | Diễn giải |
| --- | --- | --- | --- |
| Stopped | Disconnected | Chưa nhận việc mới | Pause có chủ đích hoặc startup chưa xong |
| Running | Disconnected | Unknown | Endpoint sống nhưng đang mất kết nối; có thể đang retry |
| Running | Connected | Pending | Có socket nhưng message còn trong queue/worker/transaction |
| Running | Connected | Acked/committed | Có chứng cứ logical event hoàn tất |
| Stopping | Có thể còn socket | In-flight | Stop chưa chắc drain toàn bộ việc |
| Running | Flapping | Retrying | Nguy cơ reconnect storm, duplicate và backlog |

Một `TcpSendingMessageHandler.isClientModeConnected()` phản ánh trạng thái client-mode connection tại **thời điểm gọi**, không phải chứng nhận server khỏe trong vài phút tiếp theo. Business completion phải được chứng minh qua reply/ack/commit hoặc một operation test an toàn, không dùng mỗi connection flag.

## 4. Spring lifecycle: start, stop, autoStartup và phase

Nhiều integration endpoint implement `SmartLifecycle` hoặc tương đương qua `AbstractEndpoint`. Những API nền tảng:

~~~java
import org.springframework.context.SmartLifecycle;

// Trong ứng dụng, inject đúng bean endpoint.
SmartLifecycle endpoint = endpointBean;

boolean running = endpoint.isRunning();
boolean autoStart = endpoint.isAutoStartup();
int phase = endpoint.getPhase();

endpoint.stop();
endpoint.start();
~~~

| Operation/property | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `start()` | Bắt đầu lifecycle, subscribe/schedule/listen theo implementation | Không đồng nghĩa connected hoặc delivery complete |
| `stop()` | Yêu cầu endpoint ngừng theo lifecycle | Không mặc định cancel/rollback hết in-flight |
| `isRunning()` | State của component | Không chứng minh throughput, queue rỗng hay downstream khỏe |
| `autoStartup` | Khởi động cùng context refresh hay chờ thao tác khác | Không tự bật khi remote server up trở lại nếu endpoint đã stopped |
| `phase` | Thứ tự startup/shutdown của `SmartLifecycle` | Không thay dependency và transaction boundary |
| `stop(Runnable)` | Callback khi component hoàn thành stop theo contract | Không thay xác nhận DB commit hoặc broker ack |

Với lifecycle processor của Spring, component có phase nhỏ thường khởi động trước phase lớn, dừng theo chiều ngược lại. Nhưng thứ tự còn phụ thuộc bean dependencies và implementation. **Restart endpoint khác restart ApplicationContext/pod**: restart process còn làm mất in-memory queues, cached state hoặc pending tasks nếu không có durability.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Running: autoStartup hoặc start()
    Running --> Stopped: stop()
    Stopped --> Running: start()
    Running --> [*]: context shutdown
    Stopped --> [*]: destroy
~~~

Sơ đồ đơn giản hóa lifecycle; một adapter có thể có các trạng thái nội bộ trung gian như CONNECTING, FAILED, QUIESCING.

## 5. Stop một endpoint ảnh hưởng flow thế nào?

### DirectChannel và EventDrivenConsumer

`EventDrivenConsumer` có thể subscribe/unsubscribe vào `SubscribableChannel` khi start/stop. Nếu `DirectChannel` chỉ có một subscriber, sau stop việc gửi mới có thể ném `MessageDeliveryException`. Nếu channel còn subscriber khác, message vẫn có thể được dispatch.

**Sai lầm:** stop handler A rồi thấy sender vẫn gửi thành công và kết luận `stop()` không hoạt động. Cần kiểm tra dispatcher có consumer B trên cùng channel không.

### QueueChannel và poller

`QueueChannel` là pollable. Khi polling consumer stopped, producer có thể tiếp tục enqueue, làm queue depth tăng. Nếu queue chỉ in-memory, restart pod sẽ **không biến backlog thành dữ liệu bền vững**. Với `MessageStore` bền vững và transaction đúng, pending messages có thể sống qua restart theo provider contract.

Một poller đã nhận message và đang chạy handler không tự bị rollback chỉ vì lệnh stop đến.

### ExecutorChannel

`send()` thường chỉ giao task cho executor. `stop()` endpoint không mặc nhiên hủy task đã submit. Cần quan sát active workers, pending queue, rejection policy và transaction ở worker thread. Sender có thể đã nhận kết quả send “accepted” trong khi xử lý nghiệp vụ sẽ lỗi sau.

### Inbound adapters và listener containers

Stop inbound adapter nhằm hạn chế **việc mới**, nhưng source-specific ack, session, lease, offset và consumer rebalance phải được đọc theo adapter. Broker có thể redeliver messages chưa ack sau restart; điều này **không phải bug tự thân** nếu contract at-least-once.

## 6. Ví dụ Java 17 chạy được: stop/start một consumer

Đặt toàn bộ code vào file `EndpointRestartDemoApplication.java`, package `demo.integration`. Ví dụ dùng Spring Boot + Spring Integration core, không cần TCP server. Nó chứng minh lifecycle với `DirectChannel` và `EventDrivenConsumer` trước khi đi sâu vào kết nối mạng.

~~~java
package demo.integration;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.endpoint.EventDrivenConsumer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class EndpointRestartDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointRestartDemoApplication.class, args);
    }

    @Bean("orders")
    SubscribableChannel orders() {
        return new DirectChannel();
    }

    @Bean
    AtomicInteger processedCount() {
        return new AtomicInteger();
    }

    @Bean("ordersConsumer")
    EventDrivenConsumer ordersConsumer(
            @Qualifier("orders") SubscribableChannel input,
            AtomicInteger processedCount) {

        MessageHandler handler = message -> {
            int count = processedCount.incrementAndGet();
            System.out.printf(
                "HANDLE #%d payload=%s eventId=%s thread=%s%n",
                count, message.getPayload(),
                message.getHeaders().get("eventId"),
                Thread.currentThread().getName());
        };

        EventDrivenConsumer consumer =
                new EventDrivenConsumer(input, handler);

        consumer.setAutoStartup(false);
        consumer.setPhase(100);
        return consumer;
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("ordersConsumer") EventDrivenConsumer endpoint,
            @Qualifier("orders") MessageChannel orders,
            AtomicInteger processedCount) {

        return args -> {
            System.out.println("INITIAL running=" + endpoint.isRunning());

            endpoint.start();
            System.out.println("STARTED running=" + endpoint.isRunning());
            send(orders, "ORD-101");

            endpoint.stop();
            System.out.println("STOPPED running=" + endpoint.isRunning());

            try {
                send(orders, "ORD-102");
                System.out.println("UNEXPECTED accepted while stopped");
            }
            catch (MessageDeliveryException ex) {
                System.out.println("SEND_WHILE_STOPPED "
                        + ex.getClass().getSimpleName());
            }

            endpoint.start();
            System.out.println("RESTARTED running=" + endpoint.isRunning());
            send(orders, "ORD-103");

            System.out.println("PROCESSED=" + processedCount.get());
            endpoint.stop();
        };
    }

    private static void send(MessageChannel channel, String payload) {
        boolean accepted = channel.send(MessageBuilder
                .withPayload(payload)
                .setHeader("eventId", "evt-" + payload)
                .build());
        if (!accepted) {
            throw new IllegalStateException("Send rejected: " + payload);
        }
    }
}
~~~

Kết quả về mặt logic:

~~~text
INITIAL running=false
STARTED running=true
HANDLE #1 payload=ORD-101 eventId=evt-ORD-101 thread=...
STOPPED running=false
SEND_WHILE_STOPPED MessageDeliveryException
RESTARTED running=true
HANDLE #2 payload=ORD-103 eventId=evt-ORD-103 thread=...
PROCESSED=2
~~~

Giải thích:

1. Bean consumer được tạo nhưng không tự start.
2. `start()` đăng ký subscription vào `DirectChannel`.
3. `ORD-101` được xử lý đồng bộ khi send.
4. `stop()` bỏ subscription; khi channel không còn subscriber, message `ORD-102` không có nơi nhận.
5. `start()` lần nữa cho phép `ORD-103` đi qua.
6. **`ORD-102` không tự được lưu hoặc replay.** `DirectChannel` không phải persistent queue.
7. Counter ở đây chứng minh handler được gọi, **không có nghĩa DB commit hoặc broker ack**.

Nếu có nhiều subscribers, test “send sau stop luôn bị reject” không còn đúng. Nếu channel có executor, việc send accepted cũng không chứng minh handler đã hoàn thành.

## 7. TCP client-mode: cơ chế reconnect thực tế

Theo Spring Integration TCP Adapters và IP Endpoint Reference:

- TCP inbound adapter mặc định ở **server mode**, lắng nghe client. Với `client-mode=true`, inbound adapter dùng client connection factory để chủ động kết nối remote server rồi **nhận** dữ liệu.
- TCP outbound adapter dùng client factory thường kết nối **khi gửi message đầu tiên**. Với `client-mode=true`, adapter cố gắng kết nối khi **start**.
- Client-mode yêu cầu client connection factory có `single-use=false` (dùng socket lâu dài).
- `retry-interval` là khoảng thời gian giữa các lần thử kết nối lại, tính bằng **milliseconds**, và mặc định **60.000 ms** theo bảng thuộc tính IP adapters.
- Adapter dùng `TaskScheduler` để điều phối reconnect; nếu mất kết nối, outbound client-mode có thể kết nối lại qua scheduler hoặc lúc message kế tiếp được gửi.
- Với adapter client-mode **đang running**, có thể gọi `retryConnection()` để yêu cầu thử kết nối ngay; kiểm tra bằng `isClientModeConnected()`.

~~~mermaid
stateDiagram-v2
    [*] --> Stopped
    Stopped --> RunningDisconnected: start()
    RunningDisconnected --> Connecting: retry interval hoặc retryConnection()
    Connecting --> RunningConnected: connect thành công
    Connecting --> RunningDisconnected: connect thất bại
    RunningConnected --> RunningDisconnected: peer đóng socket / lỗi mạng
    RunningConnected --> Stopped: stop()
    RunningDisconnected --> Stopped: stop()
~~~

**Không suy `retryInterval=5s` có nghĩa mọi sự cố phục hồi tối đa 5s.** Connection timeout, DNS, TLS, scheduler, remote overload, phát hiện half-open socket và kiểm tra business readiness đều ảnh hưởng thời gian hồi phục.

### Phân biệt hai hướng kết nối

| TCP adapter | `client-mode=false` | `client-mode=true` |
| --- | --- | --- |
| Inbound (nhận data) | Thường server mode lắng nghe | Chủ động kết nối server để nhận |
| Outbound (gửi data) | Client connection khi message đầu tiên được gửi | Chủ động connect tại endpoint start |
| Cấu hình cần thiết ở client-mode | Tùy setup | Client factory, `single-use=false`, retry interval |
| Reconnect thủ công | Không có ý nghĩa chung | `retryConnection()` trên `ClientModeCapable` đang running |

## 8. TCP outbound: cấu hình Java có reconnect

Cần `spring-integration-ip` và TCP peer test đang lắng nghe tại `127.0.0.1:7001`. Mã dưới đặt trong `TcpOutboundConfiguration.java`; đây là **cấu hình hoàn chỉnh cho thành phần outbound** nhưng cần application Spring Boot, serializer tương thích peer và channel `tcpOutboundRequests` trong flow đầy đủ.

~~~java
package demo.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.ip.tcp.TcpSendingMessageHandler;
import org.springframework.integration.ip.tcp.connection.TcpNetClientConnectionFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class TcpOutboundConfiguration {

    @Bean("tcpOutboundRequests")
    MessageChannel tcpOutboundRequests() {
        return new DirectChannel();
    }

    @Bean("tcpClientFactory")
    TcpNetClientConnectionFactory tcpClientFactory() {
        TcpNetClientConnectionFactory factory =
                new TcpNetClientConnectionFactory("127.0.0.1", 7001);
        factory.setSingleUse(false);
        return factory;
    }

    @Bean("tcpOutboundAdapter")
    @ServiceActivator(inputChannel = "tcpOutboundRequests")
    TcpSendingMessageHandler tcpOutboundAdapter(
            TcpNetClientConnectionFactory tcpClientFactory) {

        TcpSendingMessageHandler adapter =
                new TcpSendingMessageHandler();
        adapter.setConnectionFactory(tcpClientFactory);
        adapter.setClientMode(true);
        adapter.setRetryInterval(5_000L); // milliseconds
        return adapter;
    }
}
~~~

Mẫu dependencies trong dự án dùng Spring Boot BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-ip")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**Không gửi payload tùy ý vào TCP peer không rõ framing/codec.** Spring Integration có serializer/deserializer TCP; mặc định phải tương thích protocol cụ thể của server. Connected socket không chứng minh peer giải mã được message.

### Java API để kiểm tra và yêu cầu reconnect

`TcpSendingMessageHandler` triển khai `ClientModeCapable` và có `isClientModeConnected()`, `retryConnection()`.

~~~java
package demo.integration;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.ip.tcp.TcpSendingMessageHandler;
import org.springframework.stereotype.Service;

@Service
class TcpConnectionOperations {

    private final TcpSendingMessageHandler sender;

    TcpConnectionOperations(
            @Qualifier("tcpOutboundAdapter")
            TcpSendingMessageHandler sender) {
        this.sender = sender;
    }

    Map<String, Boolean> connectionSnapshot() {
        return Map.of(
                "running", sender.isRunning(),
                "clientMode", sender.isClientMode(),
                "connected", sender.isClientModeConnected());
    }

    synchronized boolean reconnectIfNeeded() {
        if (!sender.isRunning()) {
            // Đã stop: quản trị endpoint lifecycle trước.
            return false;
        }
        if (!sender.isClientMode()) {
            throw new IllegalStateException("Not a client-mode adapter");
        }
        if (sender.isClientModeConnected()) {
            return true;
        }
        sender.retryConnection();

        // Snapshot tức thời, không đảm bảo attempt đã hoàn tất.
        return sender.isClientModeConnected();
    }
}
~~~

Giá trị trả về `false` **không đủ để kết luận reconnect thất bại hoàn toàn**: attempt có thể đang chạy. Không tạo `while (!connected) retryConnection()` vì nó gây nhiều attempts và tăng tải server. Đợi TCP events hoặc dùng bounded await với interval phù hợp.

### Hai lifecycle layers có thể khác nhau

~~~text
tcpOutboundRequests (channel)
    -> ServiceActivator consumer endpoint (subscription)
    -> TcpSendingMessageHandler (handler + client-mode lifecycle)
    -> TcpNetClientConnectionFactory
    -> TCP peer
~~~

Stop consumer endpoint có thể làm ngừng nhận message mới từ channel, nhưng không mặc định tương đương disconnect socket đang được handler/factory giữ. Reconnect sender không làm consumer đang stopped tự subscribe lại. Runbook phải xác định **đúng bean và layer**.

## 9. TCP XML: outbound và inbound client-mode

Các fragment dưới là **hai cấu hình thay thế**, không phải yêu cầu cả hai adapter chia sẻ một client factory mà chưa xác minh ownership.

### Outbound: kết nối khi start

~~~xml
<int-ip:tcp-connection-factory
        id="outboundClientFactory"
        type="client"
        host="127.0.0.1"
        port="7001"
        single-use="false"/>

<int-ip:tcp-outbound-channel-adapter
        id="tcpOutboundAdapter"
        channel="tcpOutboundRequests"
        connection-factory="outboundClientFactory"
        client-mode="true"
        retry-interval="5000"/>
~~~

### Inbound: client connect để nhận

~~~xml
<int-ip:tcp-connection-factory
        id="inboundClientFactory"
        type="client"
        host="127.0.0.1"
        port="7002"
        single-use="false"/>

<int-ip:tcp-inbound-channel-adapter
        id="tcpInboundClient"
        channel="tcpInboundEvents"
        connection-factory="inboundClientFactory"
        client-mode="true"
        retry-interval="5000"/>
~~~

Cần namespace `int-ip`, channels và codec/remote server đúng hợp đồng; đây không phải file XML standalone. Cả hai dùng `retry-interval` theo **milliseconds**, không phải retry backoff của business handler.

## 10. Control Bus: vận hành bằng message, có kiểm soát

Spring Integration **Control Bus** cho phép gửi command nội bộ để gọi operations được exposure/filter cho phép trên beans. Cú pháp có khác biệt theo phiên bản/tài liệu:

- **Control Bus reference hiện hành**: command payload dạng `beanName.methodName`, arguments được gắn ở header `IntegrationMessageHeaderAccessor.CONTROL_BUS_ARGUMENTS`.
- **Tài liệu cũ dùng SpEL expressions**: như `@beanName.start()` hoặc `@adapter.retryConnection()`.

Ví dụ cú pháp hiện hành:

~~~text
ordersConsumer.stop
ordersConsumer.start
tcpOutboundAdapter.retryConnection
tcpOutboundAdapter.isClientModeConnected
~~~

Tài liệu cũ:

~~~text
@ordersConsumer.stop()
@ordersConsumer.start()
@tcpOutboundAdapter.retryConnection()
@tcpOutboundAdapter.isClientModeConnected()
~~~

**Không dùng hai cú pháp lẫn lộn trong một bản deployment.** Đối chiếu `ControlBusCommandRegistry` và tài liệu version thực tế. Gọi trực tiếp Java bean API trong cùng process có thể đơn giản hơn khi viết code vận hành.

Java DSL minh họa:

~~~java
@Bean
IntegrationFlow controlFlow() {
    return IntegrationFlow.from("controlCommands")
            .controlBus()
            .get();
}
~~~

Cần channel `controlCommands` và imports. Đây là **kênh quản trị có quyền thay đổi trạng thái**, không mở tự do từ HTTP/Kafka/client không tin cậy. Bảo vệ authentication/authorization, allowlist commands, audit và transport. Lệnh trên một pod **không** tự ảnh hưởng endpoints trên các pods khác.

## 11. TCP connection events: quan sát hơn là đoán

Spring Integration IP công bố application events khi connection mở, đóng hoặc lỗi:

| Event | Ý nghĩa |
| --- | --- |
| `TcpConnectionOpenEvent` | Connection đã được mở |
| `TcpConnectionCloseEvent` | Connection đã đóng |
| `TcpConnectionExceptionEvent` | Exception trong một connection |
| `TcpConnectionFailedEvent` | Client không thiết lập được connection |
| `TcpDeserializationExceptionEvent` | Protocol/frame decode lỗi |
| `TcpConnectionFailedCorrelationEvent` | Không tìm thấy connection khớp ID/late reply |

Có thể nhận bằng `@EventListener` trong chính ApplicationContext:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.integration.ip.tcp.connection.TcpConnectionOpenEvent;
import org.springframework.integration.ip.tcp.connection.TcpConnectionCloseEvent;
import org.springframework.integration.ip.tcp.connection.TcpConnectionFailedEvent;
import org.springframework.stereotype.Component;

@Component
class TcpOperationsEvents {

    @EventListener
    public void opened(TcpConnectionOpenEvent event) {
        System.out.println("TCP_OPEN " + event.getConnectionId());
    }

    @EventListener
    public void closed(TcpConnectionCloseEvent event) {
        System.out.println("TCP_CLOSE " + event.getConnectionId());
    }

    @EventListener
    public void failed(TcpConnectionFailedEvent event) {
        System.out.println("TCP_FAILED " + event);
    }
}
~~~

Đây là một bean bổ sung được dùng cùng TCP config. Đừng đưa raw connection ID, IP/credentials hay full exception payload vào metric labels. **Một `TcpConnectionOpenEvent` chỉ cho biết transport mở**, chưa xác minh remote peer nhận thành công event nghiệp vụ.

## 12. Phân biệt reconnect, handler retry và broker redelivery

| Cơ chế | Điều kiện | Tác động | Không tự đảm bảo |
| --- | --- | --- | --- |
| TCP reconnect | Socket mất/chưa tạo được connection | Tạo lại đường truyền | Replay message đã gửi |
| `RequestHandlerRetryAdvice` | Handler throw exception | Lặp lại lời gọi handler | Exactly-once hoặc remote transaction |
| Reactor `retryWhen` | Publisher phát `onError` | Resubscribe publisher | Không lặp side effect |
| Broker redelivery | Message chưa được ack hoặc transaction rollback | Giao lại cùng logical event | Peer ngoài chưa commit |
| Outbox replay | Pending event chưa có confirmed outcome | Gửi lại event dựa trên durable state | Không trùng nếu receiver thiếu idempotency |

Ví dụ nguy hiểm:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Remote peer
    participant D as Receiver DB
    P->>R: send eventId=evt-42
    R->>D: commit order
    Note over P,R: TCP disconnect trước khi response tới client
    P->>P: reconnect socket
    Note over P: Không biết event đã commit chưa
    P->>R: replay evt-42 (giữ nguyên idempotency key)
    R->>D: check inbox/unique eventId
    D-->>R: event đã tồn tại
    R-->>P: return prior outcome, không commit trùng
~~~

Nếu tạo một event ID mới cho lần replay, receiver khó deduplicate. **Transport reconnect không phải exactly-once delivery.** Với outcome không chắc chắn, kiểm tra trạng thái remote/outbox và chỉ retry theo idempotency contract. Đừng mặc định một kết nối TCP đã “write bytes” thì remote DB commit.

## 13. Khi nào nên restart endpoint, khi nào chỉ reconnect?

| Triệu chứng | Hành động ưu tiên | Cần kiểm chứng sau đó |
| --- | --- | --- |
| Endpoint `isRunning=false` do pause, dependencies ready | `start()` đúng bean | Subscription/poll/listener active |
| Endpoint running nhưng TCP client disconnected | Built-in reconnect policy hoặc `retryConnection()` có kiểm soát | Open event, connected state |
| Connected nhưng backlog tăng | Kiểm tra poller/executor/handler/store, không chỉ reconnect | Queue age và completion rate |
| Payload decode fail liên tục | Sửa framing/serializer/schema | Message test đọc đúng |
| Business handler ném lỗi 4xx hoặc invalid data | Retry phân loại lỗi/quarantine | Outcome rõ, không reconnect vòng lặp |
| Credentials/certificate hết hạn | Sửa secret/config, recreate nếu adapter không reload | Authenticated connection và probe |
| Dynamic flow thay đổi cấu trúc | `IntegrationFlowContext` register/stop/destroy đúng contract | Graph mới, không orphan handlers |
| Broker listener bị gián đoạn | Container-specific recovery | Ack, consumer lag, redelivery |
| Process/VM lỗi | Rolling restart có drain và persistence | Không mất backlog hoặc duplicate side effects |

**Thao tác nên ít xâm lấn nhất nhưng đúng nguyên nhân.** Restart toàn bộ process có thể gây mất in-memory state, tăng reconnect load toàn cluster và làm khó điều tra một lỗi socket đơn lẻ.

## 14. Runbook restart an toàn: pause → drain → recover → verify

Một runbook tốt có **điều kiện bắt đầu**, **đối tượng tác động**, **thời hạn**, **tiêu chí thành công** và **rollback**. Với message flow có transaction hoặc broker, đừng bắt đầu bằng `kill -9`/restart pod nếu vẫn còn cách khôi phục connection ở đúng tầng.

~~~mermaid
flowchart TD
    A["Phát hiện lỗi"] --> B["Chụp snapshot trạng thái"]
    B --> C{"Endpoint running?"}
    C -->|Không| D["Kiểm tra pause hợp lệ; chuẩn bị start"]
    C -->|Có| E{"Transport disconnected?"}
    E -->|Có| F["Reconnect policy / bounded retryConnection"]
    E -->|Không| G["Kiểm tra backlog, poller, handler, transaction"]
    D --> H["Pause ingress, drain khi cần"]
    F --> H
    G --> H
    H --> I["Thao tác đã chọn"]
    I --> J["Kiểm tra lifecycle + connection"]
    J --> K["Synthetic message + commit/ack"]
    K --> L{"Đạt điều kiện?"}
    L -->|Có| M["Resume tải dần, theo dõi backlog/duplicates"]
    L -->|Không| N["Escalate / rollback / quarantine"]
~~~

### Trước thao tác: checklist snapshot

| Câu hỏi | Dữ liệu phải ghi |
| --- | --- |
| Instance nào bị ảnh hưởng? | Pod/hostname, deployment version, tenant/partition |
| Bean nào giữ connection? | Handler ID, adapter ID, connection factory name |
| Endpoint nào dừng/start được? | `isRunning()`, `isAutoStartup()`, `phase` |
| Socket/session hiện ra sao? | Connected flag, TCP open/close/failed events |
| Còn message in-flight không? | Worker active, pending replies, transactional records |
| Backlog lưu ở đâu? | `QueueChannel` in-memory hay persistent `MessageStore`/broker |
| Error flow có hoạt động? | `errorChannel`, recovery handler, DLQ/sink |
| Có replay risk không? | Last acked offset/sequence, event IDs, unknown outcomes |
| Remote peer có sẵn sàng? | DNS/TLS/auth, host:port, listener, rate limits |
| Có thay đổi cấu hình gần đây? | Endpoint, serializer, connection pool, secret, timeout |

### Trình tự khi cần graceful restart

1. **Xác định đầu vào:** ngừng hoặc hạn chế inbound traffic tại đúng source, tránh tạo backlog vượt capacity. Với broker, dùng pause/stop theo adapter contract, không xóa queue.
2. **Chờ in-flight:** quan sát worker đang chạy, transaction chưa commit, message đang chờ reply, error/retry callbacks; dùng timeout hữu hạn.
3. **Giữ error path:** không dừng recovery consumer quá sớm, vì lỗi cuối cùng có thể vẫn cần được ghi vào DLQ.
4. **Thực hiện can thiệp:** nếu chỉ mất TCP socket, ưu tiên reconnect; nếu endpoint stopped hoặc handler config hỏng, cân nhắc start/stop hoặc rebuild flow đúng API.
5. **Xác minh từng tầng:** lifecycle running, transport connected, test message xử lý đúng và durable outcome đã xác nhận.
6. **Resume theo tốc độ có giới hạn:** poller max messages, listener concurrency hoặc producer rate; theo dõi queue age và failure rate.
7. **Ghi incident timeline:** detect, command, reconnect attempt, first open event, first successful business operation, return to normal throughput.

`stop()` **không phải lệnh rollback**; một message đã commit DB trước khi stop sẽ không bị “đảo ngược”. Ngược lại, một delivery chưa ack có thể được broker giao lại sau start.

## 15. Graceful drain phụ thuộc endpoint boundary

### DirectChannel

Nếu sender đang gọi đồng bộ handler, stop endpoint chỉ thay đổi subscription/lifecycle. Không tự giả định nó interrupt thread đang chạy hoặc undo side effect. Có thể có nhiều subscribers trên cùng channel.

### ExecutorChannel

Một task được executor accept có thể còn nằm trong queue hoặc đang chạy khi operator stop consumer. `isRunning()==false` **không chứng minh executor queue empty**. Khi application shutdown, còn tùy executor policy `waitForTasksToCompleteOnShutdown`, task rejection, cancellation và interruption.

Nếu công việc chỉ lưu trong executor memory, restart process trước khi xử lý sẽ có nguy cơ mất task. Muốn at-least-once processing, thường cần inbound broker/queue store bền vững và transaction/retry nhất quán.

### QueueChannel và PollingConsumer

Stop polling consumer thường ngăn các lần poll mới sau khi stop hoàn tất theo contract, nhưng message đã dequeue/in-flight cần được xử lý theo source transaction. Producer vẫn có thể enqueue và queue depth tăng. Với persistent store, phải xác minh readback qua restart bằng test thực, không chỉ nhìn `QueueChannel.getQueueSize()`.

### TCP outbound

Dừng một consumer endpoint nằm trước `TcpSendingMessageHandler` có thể ngăn message mới đến handler nhưng không đồng nghĩa socket đã được đóng theo ý bạn. Dừng handler hoặc connection factory có thể ảnh hưởng các flows khác nếu chúng dùng chung resource. Kiểm tra bean ownership và gọi **API của đúng đối tượng**.

## 16. Khi nào reconnect quá nhiều gây outage?

**Reconnect storm** xảy ra khi nhiều instances hoặc nhiều message thất bại cùng tạo lại connection với tần suất cao, làm peer quá tải và tiếp tục thất bại.

~~~text
Pod A: connect -> fail -> 1s -> connect -> fail ...
Pod B: connect -> fail -> 1s -> connect -> fail ...
Pod C: connect -> fail -> 1s -> connect -> fail ...
Remote TCP server: backlog accept tăng, quota socket đầy
~~~

Các nguyên nhân phổ biến:

- Retry interval quá ngắn so với thời gian peer phục hồi.
- Nhiều pods start đồng thời trong rolling deployment.
- Mỗi handler failure lại gọi `retryConnection()` dù built-in scheduler đã retry.
- DNS/TLS/auth lỗi permanent nhưng logic vẫn retry vô hạn.
- Load balancer/firewall/NAT đóng idle socket, heartbeat không phù hợp.
- Remote server áp connection quota, exponential retries bị synchronized.
- Framing/serializer sai khiến peer lập tức đóng socket.

### Backoff, cooldown và jitter

Nếu tự viết orchestration reconnect bên ngoài adapter, có thể dùng exponential backoff có ceiling và jitter:

\[
d_n = \min(d_{\max}, d_0 \cdot 2^n) \times (0.5 + 0.5U)
\]

Với `U` phân phối đều trong `[0,1]`. Ví dụ `d0=1s`, `dmax=30s` để tránh nhiều instances cùng retry đúng một thời điểm. **Đây là công thức policy minh họa, không phải thuật toán mặc định của TCP adapter**: `retry-interval` trong Spring Integration TCP là khoảng retry cấu hình, không mặc nhiên exponential backoff.

Nguyên tắc:

- Ưu tiên cơ chế reconnect nội bộ của adapter nếu ổn định.
- Nếu có tự viết coordinator, đảm bảo **không kích hoạt song song** với các attempts nội bộ không cần thiết.
- Một operator chỉ nên trigger bounded manual reconnect sau khi biết trạng thái và nguyên nhân.
- Có retry budget, cooldown và escalation khi vượt số lần thất bại.
- Không retry lỗi credential/serializer bất biến như thể network glitch.
- Với nhiều pods, stagger start và theo dõi connection quota của peer.

## 17. Readiness và liveness khi socket đang disconnected

~~~text
Spring Boot application started
    != Endpoint running
    != TCP connection established
    != Business path ready to commit
~~~

Một adapter client-mode có thể ở trạng thái **running nhưng chưa connected** trong khi scheduler còn thử kết nối. Phân biệt:

| Health indicator | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Liveness | Process có còn hoạt động bình thường? | JVM phục vụ health endpoint, không deadlock |
| Readiness | Instance hiện có thể nhận traffic theo chính sách? | Dependency cần thiết hoặc durable buffering đủ sức |
| Transport status | TCP/broker/session connected? | `isClientModeConnected()` + connection events |
| Business probe | Gửi event an toàn và xác minh outcome được không? | Reply, commit, ack, idempotent test |
| Degraded state | Flow có thể nhận nhưng chưa gửi remote? | Outbox đang giữ backlog và có retention |

Nếu ứng dụng chỉ có thể hoàn thành request khi remote TCP peer còn sống, readiness có thể cần báo not ready. Nếu ứng dụng có queue/outbox bền vững và chấp nhận tạm giữ công việc, có thể báo readiness có điều kiện và transport degraded. Không dùng `isClientModeConnected()` làm **liveness duy nhất**, vì một outage của shared dependency không nhất thiết cần restart mọi pod.

**Cảnh báo:** mọi pods liveness fail vì một remote outage có thể tạo restart loop và reconnect storm nghiêm trọng hơn. Health policy phải dựa vào mục tiêu hệ thống và SLO.

## 18. Metrics cho reconnect và business recovery

| Metric/signal gợi ý | Ý nghĩa | Điểm chú ý |
| --- | --- | --- |
| `integration.endpoint.running` | Lifecycle gauge | Không phản ánh connection khỏe |
| `tcp.connection.open.total` | Số lần socket mở | Phân biệt healthy reconnect với flapping |
| `tcp.connection.close.total` | Số lần socket đóng | So với open theo time window |
| `tcp.connection.failed.total` | Failed connection attempts | Có thể cần phân nhóm lỗi |
| `tcp.connection.active` | Số socket active | Per factory/adapter |
| `producer.reconnect.attempts` | Số lần retry connection | Phân biệt scheduled/manual khi có thể |
| `producer.reconnect.duration` | Detect-to-connected | Không phải message recovery |
| `producer.reconnect.consecutive_failures` | Outage kéo dài | Dùng alert |
| `integration.messages.accepted` | Producer/channel đã nhận | Không đồng nghĩa remote commit |
| `integration.messages.completed` | Có business outcome | Định nghĩa rõ milestone |
| `integration.messages.failed.retried` | Failure/retry rates | Retry storm |
| `queue.depth` / `queue.oldest.age` | Backlog khi consumer paused | Cần bounded retention |
| `executor.active` / `executor.pending` | Worker/task còn chạy | Xác minh drain |
| `outbox.pending` / `dlq.count` | Durability và recovery | Không nên chỉ đọc log |

**Đây là tên metric gợi ý cho instrumentation**, không phải danh sách meters mặc định của framework. Spring Integration hỗ trợ Micrometer Observation ở những components được instrument, nhưng TCP events thường cần `ApplicationListener`/`@EventListener` và metric code của ứng dụng.

### Metric cardinality

Không đưa raw connection ID, event ID, payload, customer ID hoặc exception message tùy ý vào metric labels. Chọn tags cardinality thấp: endpoint ID (có danh sách cố định), adapter type, direction, outcome, exception class giới hạn và deployment region. Connection IDs/event IDs nên ghi vào structured logs/traces theo chính sách bảo mật.

### Hai độ trễ cần đo tách biệt

- **Detect-to-connected:** từ lúc phát hiện mất transport đến lúc có connection mới.
- **Detect-to-first-successful-business-event:** từ sự cố đến khi message có kết quả nghiệp vụ thật sau phục hồi.

Trường hợp connected sau 2 giây nhưng queue 50.000 messages và downstream xử lý chậm thì business recovery có thể mất hàng phút. Không gộp hai chỉ số dưới tên `reconnect_time`.

## 19. Quan sát error path khi reconnect

Một hệ thống có thể có nhiều cách biểu diễn lỗi:

| Lỗi | Nơi xuất hiện | Cách kiểm tra |
| --- | --- | --- |
| TCP connect failed | `TcpConnectionFailedEvent` / logs adapter | Event listener, remote endpoint |
| TCP established then closed | `TcpConnectionCloseEvent` | Connection ID, time window |
| TCP decode error | `TcpDeserializationExceptionEvent` | Framing/codec và bytes |
| Handler sync throw qua DirectChannel | Exception ở caller | Call stack, transaction outcome |
| Handler async throw qua executor | Error handler/`ErrorMessage` tùy config | `errorChannel`/DLQ |
| Broker listener redelivery | Container/adapter và broker | Ack, delivery ID, committed offsets |
| External API business failure | Handler response/exception | Response semantics, retry classification |

**TCP connection event không đồng nghĩa Spring Messaging `ErrorMessage`.** `ErrorMessage` là một message chứa Throwable; được tạo ở những error-publishing boundaries được hỗ trợ. Socket event là một `ApplicationEvent` từ integration IP. Một outage có thể tạo cả hai, nhưng chúng không có cùng contract, không cùng thông tin và không tự kết nối với nhau.

Khi phân loại lỗi, giữ:

- `eventId` ổn định qua retries.
- `correlationId` cho aggregator/splitter và trace.
- Connection factory/adapter name.
- Retry attempt number và type, nếu thực sự đo được.
- Error class, root cause, stage và timestamp.
- Durable message status (pending/committed/DLQ).

## 20. Transaction, retry và idempotency sau restart

Giả sử producer ghi một message vào TCP socket, remote peer đã xử lý và commit DB, nhưng response bị mất do connection reset. Producer nhìn thấy lỗi nên retry sau reconnect:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Remote handler
    participant D as Remote DB
    P->>R: SEND eventId=evt-101
    R->>D: INSERT + COMMIT
    D-->>R: Success
    Note over P,R: TCP disconnect trước response
    P->>P: Reconnect succeeded
    P->>R: RETRY eventId=evt-101
    R->>D: INSERT có idempotency key evt-101?
    D-->>R: Already processed / return prior outcome
    R-->>P: Confirmed
~~~

Nếu event ID đổi giữa attempts, receiver không thể phát hiện đó là cùng logical event chỉ dựa vào transport. Biện pháp thiết kế:

1. **Outbox phía sender:** lưu event durable và state pending/confirmed; không xóa chỉ vì bytes đã write.
2. **Inbox/idempotency phía receiver:** unique key cho logical event; xử lý trùng trả lại prior outcome khi thích hợp.
3. **Transaction đúng ranh giới:** DB commit và broker ack được phối hợp theo mô hình phù hợp; TCP không tự tham gia JDBC transaction hai phía.
4. **Retry có giới hạn:** transient network errors có thể retry, permanent schema/auth errors nên quarantine/escalate.
5. **Reconciliation:** khi outcome unknown, có cơ chế tra cứu trạng thái remote thay vì resend mù.
6. **Replay giữ correlation:** không dùng `MessageHeaders.ID` mới sinh thay stable logical ID.

Không hứa “exactly-once” chỉ nhờ `retryConnection()` và `RequestHandlerRetryAdvice`; hiệu quả cuối cùng phụ thuộc giao thức ứng dụng và side-effect store.

## 21. MQTT/JMS/AMQP/SFTP có reconnect semantics khác TCP

| Adapter | Recovery surface | Điều cần xác minh |
| --- | --- | --- |
| TCP client-mode | `ClientModeCapable.retryConnection()`, scheduler | `single-use=false`, TCP events, framing |
| MQTT Paho v3/v5 | `MqttConnectOptions`/`MqttConnectionOptions` và adapter lifecycle | Automatic reconnect, subscriptions, QoS, delivery events |
| JMS listener | Listener container/session/connection factory | Recovery interval, transaction, session state |
| AMQP RabbitMQ | Listener container, connection factory | Consumer restart, acks/requeue, broker policy |
| SFTP/FTP polling | Session factory, cache, source poller | Session recreation, remote listing, file filters |
| HTTP outbound | Client pool/request retry | Timeouts, idempotency, response status |
| JDBC polling | DataSource/transaction manager | DB reconnect, row locks, poller state |

Tài liệu MQTT hiện hành nêu `MqttConnectionFailedEvent`, `MqttMessageSentEvent`, `MqttMessageDeliveredEvent`, `MqttMessageNotDeliveredEvent`, `MqttSubscribedEvent` tùy adapter và mode. Với MQTT v5, tài liệu hướng dẫn xem xét bật `MqttConnectionOptions.setAutomaticReconnect(true)`; nếu không, một số tình huống cần restart inbound adapter có chủ đích. **Không lấy API của TCP áp lên MQTT**.

Với remote file và JDBC, “producer reconnect” thực tế có thể là **khôi phục `MessageSource.receive()`** và session pool/connection pool, không phải TCP long-lived adapter. Nếu error nằm ở poller, restart poller khi remote system vẫn down sẽ chỉ lặp lỗi; xác định root cause trước.

## 22. Dynamic IntegrationFlow và rolling deployment

Spring Integration cung cấp `IntegrationFlowContext` cho flow đăng ký động:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(dynamicFlow)
                .id("tenantOrdersFlow")
                .autoStartup(false)
                .register();

registration.start();
// ... theo dõi flow, message và connections ...
registration.stop();
// Drain pending work nếu yêu cầu.
registration.destroy();
~~~

Đây là snippet, cần bean `flowContext` và `dynamicFlow` hợp lệ. **`stop()` khác `destroy()`**: stop giữ registration để start lại, destroy tháo flow và dependent beans theo contract. Nếu chỉ socket cần reconnect, không tự hủy rồi tạo lại cả flow.

Khi rolling deployment:

- Start downstream infrastructure/consumer readiness trước khi mở inbound traffic.
- Chỉ drain một số pods mỗi đợt; không làm cả cụm mất connection đồng thời.
- Kiểm tra serializers, protocol version, TLS và secrets giữa bản cũ/mới.
- Quan sát pending messages, group store, broker offsets và lock ownership.
- Dùng cùng logical event ID qua các versions để deduplicate replay.
- Cần central runbook điều phối, vì Control Bus/JMX command trên một ApplicationContext không tự tác động tới contexts khác.

## 23. Kiểm thử endpoint restart bằng JUnit

Từ ví dụ mục 6, có thể xây context test riêng (không chạy `ApplicationRunner` minh họa) và assert:

~~~java
@Test
void consumerCanStopAndRestart() {
    endpoint.stop();
    assertFalse(endpoint.isRunning());

    endpoint.start();
    assertTrue(endpoint.isRunning());

    assertTrue(orders.send(MessageBuilder
            .withPayload("ORD-T1")
            .setHeader("eventId", "evt-T1")
            .build()));

    assertEquals(1, processedCount.get());
    endpoint.stop();
}
~~~

Đây là **JUnit fragment**, cần inject bean `endpoint`, `orders`, `processedCount` và JUnit imports, đồng thời reset counter/trạng thái trước test. Khi `DirectChannel` dispatch đồng bộ, assertion được kiểm tra ngay sau `send()` hợp lý.

Negative test khi channel chỉ có một subscriber:

~~~java
endpoint.stop();

assertThrows(MessageDeliveryException.class, () ->
        orders.send(MessageBuilder
                .withPayload("ORD-STOPPED")
                .build()));
~~~

Nếu có subscriber thứ hai hoặc channel type khác, **không** assert như thể `send()` luôn throw. Test đúng topology, behavior và durable outcome của ứng dụng.

## 24. Fault injection TCP reconnect: test bằng evidence

Dùng một TCP test server có thể start/stop và nhận payload theo framing/serializer thật:

1. Start server test và outbound client-mode adapter.
2. Đợi `TcpConnectionOpenEvent` hoặc condition `isClientModeConnected()` với timeout hữu hạn.
3. Gửi event `evt-ok-1`, xác minh peer đã nhận và xử lý theo contract.
4. Tắt server hoặc chủ động đóng connection.
5. Đo thời điểm `TcpConnectionCloseEvent`/`TcpConnectionFailedEvent`; xác nhận adapter **vẫn running**.
6. Start server lại; để scheduler reconnect hoặc trigger **một** `retryConnection()` theo runbook.
7. Đợi open event hoặc connected flag; **không dùng `Thread.sleep(5000)` làm assertion duy nhất**.
8. Gửi event `evt-ok-2`; xác minh outcome theo peer/application-level contract.
9. Gửi event lúc disconnect để tạo outcome unknown; chỉ retry theo stable `eventId` và kiểm tra dedup.
10. Kiểm tra connections/threads không leak sau nhiều lần lặp.

Snippet cấu trúc với Awaitility và TCP fixture tự viết:

~~~java
// Pseudo integration test: cần tcpSender bean và testTcpServer fixture.
assertTrue(tcpSender.isRunning());

await().atMost(Duration.ofSeconds(10))
        .until(tcpSender::isClientModeConnected);

testTcpServer.closeConnections();

await().atMost(Duration.ofSeconds(10))
        .until(() -> !tcpSender.isClientModeConnected());

testTcpServer.restart();
tcpSender.retryConnection();

await().atMost(Duration.ofSeconds(10))
        .until(tcpSender::isClientModeConnected);
~~~

Cần imports Awaitility/Duration/JUnit và TCP server test fixture. Đây **không phải test độc lập chạy ngay** vì fixture được giả định. Trong trường hợp connection tự phục hồi nhanh, trạng thái disconnected có thể quá ngắn làm assertion flake; nên lưu và await **connection events** hoặc giữ server down đủ lâu theo test.

Cần thêm một assertion **send/response/commit** sau reconnect. Kiểm tra socket connected một mình không chứng minh business recovery.

## 25. Timeout, interval và thời gian phục hồi

Một recovery cycle có thể chia:

\[
T_{\text{recovery}} \approx
T_{\text{detect}} +
T_{\text{wait for retry}} +
T_{\text{connect}} +
T_{\text{validate}} +
T_{\text{resume}}
\]

Đây là **mô hình phân tích**, các khoảng có thể chồng lấp theo implementation. `retry-interval=5000 ms` chỉ liên quan lịch attempts, không bảo đảm `T_recovery <= 5 s`.

| Thành phần | Nguyên nhân trễ | Chỉ số nên đo |
| --- | --- | --- |
| Detect | TCP half-open/idle timeout | Last successful I/O → close/failed event |
| Wait retry | `retryInterval`/scheduler bận | Disconnect → reconnect attempt |
| Connect | DNS, TCP handshake, TLS/auth, server queue | Attempt → open/fail |
| Validate | Health/business probe, peer warm-up | Connected → first valid reply |
| Resume | Queue backlog, poller/worker limit, DB pool | First successful event → normal throughput |

Đừng nhầm **connection recovered** với **throughput recovered**. Một TCP socket có thể mở sau 2 giây nhưng pending queue 20.000 events cần nhiều phút để drain.

## 26. Bảng chẩn đoán production

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra ưu tiên |
| --- | --- | --- |
| Endpoint running nhưng TCP disconnected | Peer down, network, TLS/DNS, scheduler chưa thử | TCP failed/close events, remote health |
| `retryConnection()` trả về nhưng status false | Attempt chưa hoàn tất hoặc fail | Open/failed events và deadline |
| Endpoint restart nhưng không có message | Source rỗng, channel sai, consumer chưa subscribe | Integration graph, poller/handler state |
| Socket connected nhưng payload fail | Framing/serializer/schema mismatch | Raw protocol test, deserialization events |
| Send accepted nhưng peer không commit | Async handoff, disconnect, lost ack | End-to-end reply/ack/business state |
| Sau restart message trùng | Redelivery khi ack chưa commit | eventId, inbox, outbox |
| Restart process làm mất backlog | In-memory queue/task executor | Store durability, shutdown policy |
| TCP OPEN/CLOSE liên tục | LB idle timeout, peer quota, server restart | Event rate, keepalive, peer logs |
| Nhiều pods cùng lỗi sau deploy | Wrong credentials/protocol và synchronized reconnect | Config diff, rollout coordination |
| Poller running nhưng không có output | Receive timeout, session failure, handler errors | Poller metrics, MessageSource logs |
| ErrorMessage có nhưng caller send thành công | Async boundary | errorChannel, worker transaction |
| MQTT connected nhưng chưa subscribe | Subscription chưa khôi phục | MqttSubscribedEvent, session/QoS |
| Readiness fail toàn cluster vì remote outage | Health policy ràng buộc sai | Liveness/readiness/degraded state |

### Quy trình debug thực địa

1. Xác định **đúng bean ID/flow ID/pod**.
2. Ghi snapshot lifecycle/connection/message state **trước** can thiệp.
3. Phân biệt transport failure với schema, handler, queue saturation và transaction.
4. Kiểm tra remote availability, network, TLS, DNS, credentials và config mới.
5. Chọn reconnect socket, endpoint start/stop, flow re-registration hoặc rolling restart theo nguyên nhân.
6. Quan sát attempts có giới hạn và error events; tránh retry song song vô hạn.
7. Chứng minh sau recovery bằng **synthetic business event** có outcome và ack/commit.
8. Theo dõi backlog, retries, duplicates, resource leaks sau khi resume.
9. Ghi incident timeline, thay đổi config và điều kiện rollback.

## 27. Tình huống thực tế: peer TCP restart khi gửi order

Một service gửi order qua outbound TCP client-mode. Peer restart ngay lúc đang nhận order `evt-42`; phía gửi không biết peer đã commit hay chưa.

**Cách làm sai:**

~~~text
Connection reset -> restart tất cả pods -> gửi lại toàn bộ batch
~~~

Hậu quả có thể gồm reconnect storm, mất in-memory tasks, duplicate orders và không có cách xác định event nào đã xử lý.

**Runbook phù hợp:**

1. Từ TCP events xác nhận mất transport, không phải invalid business payload.
2. Giảm ingress hoặc đảm bảo outbox/queue còn capacity.
3. Để scheduler client-mode reconnect; nếu cần dùng `retryConnection()` **một lần** và audit.
4. Đợi connected rồi thực hiện probe thực, không chỉ nhìn `isRunning`.
5. Truy các `eventId` pending/unknown từ durable store.
6. Nếu có API tra cứu trạng thái peer, ưu tiên reconciliation trước khi resend.
7. Retry event với **same idempotency key** và backoff có giới hạn.
8. Kiểm tra committed, pending, DLQ, duplicate suppression và backlog.
9. Resume tải tăng dần, lưu metrics recovery time và incident timeline.

Ngay cả khi broker transaction rollback, remote TCP peer có thể đã commit, nên **transaction một phía không đủ để loại duplicate**. Thiết kế idempotent receiver hoặc business reconciliation là bắt buộc nếu nghiệp vụ đòi hỏi.

## 28. Bộ bài tập thực hành

1. Chạy `EndpointRestartDemoApplication`; xác nhận `ORD-101`/`ORD-103` được xử lý, `ORD-102` không tự replay.
2. Tạo thêm subscriber vào `DirectChannel`, stop consumer chính rồi quan sát việc gửi vẫn có thể thành công.
3. Đổi flow sang `QueueChannel` + `PollingConsumer`; stop poller, đo queue depth, restart và kiểm tra drain.
4. Dùng `ExecutorChannel` + handler chờ latch; gọi stop khi handler in-flight và đối chiếu `isRunning` với actual task completion.
5. Cấu hình TCP client-mode outbound với local TCP test server, quan sát open/close events.
6. Đổi `retry-interval` từ 5.000 sang 30.000 ms trong test và đo detect-to-connected.
7. Giữ adapter running, tắt server, gọi **một lần** `retryConnection()`, đo attempts và kết quả.
8. So sánh TCP inbound server mode với inbound client-mode trong một test topology hợp lệ.
9. Dùng `@EventListener` ghi timeline `TcpConnectionOpenEvent`, `TcpConnectionCloseEvent`, `TcpConnectionFailedEvent`.
10. Chọn Control Bus syntax theo version đang chạy, gửi command nội bộ với audit/allowlist.
11. Mô phỏng TCP peer commit trước khi socket mất; replay same eventId và kiểm tra inbox dedup.
12. Kết hợp `RequestHandlerRetryAdvice` với TCP reconnect và giới hạn số attempts để tránh retry storm.
13. Test broker redelivery sau consumer stop; so sánh acknowledged vs unacknowledged messages.
14. Dùng MQTT v5 automatic reconnect tùy version, xác minh subscription được khôi phục sau outage.
15. Với persistent `QueueChannel` hoặc message store, restart process rồi đọc lại pending messages.
16. Mô phỏng TCP peer trả payload sai framing; giải thích vì sao reconnect không sửa được.
17. Viết readiness indicator có `healthy`, `degraded`, `not ready` tùy durability contract.
18. Chạy 3 instances và server down; ghi concurrent reconnect attempts; thử staggered recovery.
19. Gắn Micrometer counters vào TCP events, không dùng connectionId làm metric tag.
20. Soạn runbook có điều kiện bắt đầu, thao tác, rollback, xác minh và escalation.

### Câu hỏi tự kiểm tra

- `start()/stop()` khác `retryConnection()` ở tầng nào?
- Vì sao một TCP adapter running vẫn có thể disconnected?
- Khi nào TCP outbound tạo connection ngay khi start, khi nào chờ send đầu tiên?
- Tại sao client-mode cần `single-use=false`?
- `retry-interval` có phải giới hạn thời gian khôi phục tối đa không?
- Reconnect có replay message mà peer đã nhận một phần không?
- Vì sao `isClientModeConnected()==true` chưa chứng minh business outcome?
- Nếu socket đóng sau khi peer đã commit, retry cần giữ thông tin nào?
- `EventDrivenConsumer.stop()` có stop connection factory được handler dùng chung không?
- `QueueChannel` in-memory có đảm bảo sống qua process restart không?
- Vì sao broker redelivery và TCP reconnect có thể tạo duplicate?
- Control Bus trên một pod có điều khiển toàn cluster không?
- Khi nào cần `IntegrationFlowContext.destroy()` thay vì endpoint restart?
- TCP connection event và Spring `ErrorMessage` khác nhau ra sao?

## 29. Checklist production

- Có inventory endpoint IDs, flow IDs, connection factory owner, input/output/error channels theo instance.
- Tách lifecycle state, connection status và business outcome thành các signals khác nhau.
- Dùng client-mode reconnect API đúng contract, chỉ khi adapter đang running.
- Có bounded retry interval, timeout, cooldown, chống reconnect thundering herd.
- Không retry permanent credentials/serializer errors như lỗi mạng tạm thời.
- Ghi TCP/broker/MQTT events, retries, connection health và reconnection timeline.
- Error/recovery consumers vẫn sẵn sàng khi drain producer/inbound source.
- In-memory queues và executor pending tasks có shutdown policy; nếu cần durability thì dùng persistent storage.
- Broker ack/transaction/outbox/inbox/idempotency được kiểm chứng riêng.
- Có probe đảm bảo **message processing hoàn tất**, không chỉ socket connected.
- Control Bus/JMX write access giới hạn quyền và có audit.
- Rolling restart theo nhóm, đủ thời gian drain và giảm tải remote.
- Runbook có rollback/escalation và điều kiện dừng retry khi lỗi kéo dài.
- Đã thử fault injection: peer down/up, half-open socket, serializer mismatch, unknown outcome và duplicate replay.
- Có dashboard theo dõi backlog, p95/p99 processing latency, retry và time-to-first-business-success.

## 30. Nguồn tham khảo chính thức

- [Spring Integration — TCP Adapters](https://docs.spring.io/spring-integration/reference/ip/tcp-adapters.html): inbound/outbound client mode, reconnect và retry interval.
- [Spring Integration — TCP Endpoint Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): `client-mode`, `single-use`, `retry-interval` và default.
- [Spring Integration — TCP Connection Events](https://docs.spring.io/spring-integration/reference/ip/tcp-events.html): open/close/failed/exception/correlation events.
- [Spring Integration — TCP Connection Factories](https://docs.spring.io/spring-integration/reference/ip/tcp-connection-factories.html): ownership, connection caching/failover và serializers.
- [Spring Integration Javadoc — ClientModeCapable](https://docs.spring.io/spring-integration/docs/5.5.17/api/org/springframework/integration/ip/tcp/connection/ClientModeCapable.html): `isClientModeConnected()` và `retryConnection()`.
- [Spring Integration Javadoc — TcpSendingMessageHandler](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/ip/tcp/TcpSendingMessageHandler.html): handler lifecycle và client-mode setter/API.
- [Spring Integration — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): managed operations, command registry và security.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): sync/async/pollable boundary.
- [Spring Integration — Source Polling Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): poller lifecycle và pause semantics.
- [Spring Integration — Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): `IntegrationFlowContext` registration, start/stop/destroy.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channel và async error handling.
- [Spring Integration — MQTT Support](https://docs.spring.io/spring-integration/reference/mqtt.html): Paho reconnect và MQTT events.
- [Spring Framework — Lifecycle / SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): start/stop, phase và dependency ordering.
