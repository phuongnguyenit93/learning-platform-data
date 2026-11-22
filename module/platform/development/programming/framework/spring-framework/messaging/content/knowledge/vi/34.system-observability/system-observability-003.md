# Theo dõi kết nối, phiên, subscription và consumer

Trong hệ thống messaging, một kết nối đang mở chưa chắc có message đang chạy; một subscription đang tồn tại chưa chắc đang nhận dữ liệu; và một consumer đang sống chưa chắc xử lý kịp lượng message được gửi tới. Muốn quan sát đúng, cần tách riêng vòng đời transport connection, phiên giao thức, stream/subscription, quá trình xử lý message và hàng đợi phía broker.

Spring cung cấp nhiều lớp quan sát thông qua Micrometer, Spring Boot Actuator, Spring Integration và các callback của RSocket. Một phần metric được tự động ghi nhận khi có đúng dependency và cấu hình; các trạng thái riêng của ứng dụng như số phiên RSocket đang hoạt động, số stream đang mở hoặc consumer lag cần được instrument tại nơi ứng dụng thực sự nhìn thấy vòng đời đó.

## 1. Phân biệt connection, session, subscription và consumer

Các khái niệm này liên quan với nhau nhưng không thể dùng thay thế cho nhau.

| Khái niệm | Ý nghĩa | Câu hỏi vận hành cần trả lời |
|---|---|---|
| Transport connection | Kênh truyền vật lý hoặc logic như TCP, WebSocket, kết nối tới broker | Có bao nhiêu kết nối đang mở? Kết nối có thường xuyên bị đóng hoặc tạo lại không? |
| Protocol session | Trạng thái giao thức gắn với một kết nối hoặc được duy trì qua cơ chế resume | Phiên còn hợp lệ không? Có resume thành công hay bị từ chối không? |
| Subscription / stream | Một luồng Reactive Streams hoặc một tương tác RSocket đang nhận dữ liệu | Có bao nhiêu stream đang chạy? Stream kết thúc, lỗi hay bị cancel? |
| Consumer | Thành phần nhận và xử lý message, ví dụ MessageHandler, @JmsListener hoặc subscriber | Consumer xử lý bao nhiêu message? Độ trễ, lỗi và backlog ra sao? |
| Queue / backlog | Message đang chờ consumer hoặc chưa được xác nhận | Queue có tăng liên tục không? Message cũ nhất đã chờ bao lâu? |

### 1.1. Một connection có thể chứa nhiều stream

RSocket hỗ trợ multiplexing và các interaction model như request-response, request-stream, request-channel và fire-and-forget. Một transport connection có thể mang nhiều request/stream độc lập. Vì vậy:

- Số TCP/WebSocket connection không phải số stream đang hoạt động.
- Một session có thể có nhiều subscription hoặc request đồng thời.
- Một stream có thể phát ra nhiều message.
- Một connection còn mở không chứng minh rằng consumer đang xử lý dữ liệu.
- Khi connection bị ngắt, session có thể được resume nếu hai bên còn giữ đủ trạng thái và implementation hỗ trợ.

Trong RSocket, backpressure truyền qua biên mạng. Requester điều khiển demand và responder phải tôn trọng lượng demand đó. Khi stream không tiến triển, cần kiểm tra cả phía phát, phía nhận, demand và tài nguyên xử lý thay vì chỉ xem trạng thái socket.

### 1.2. Phân biệt session của RSocket và JMS

Trong RSocket, session thường được dùng để nói về trạng thái của một kết nối giao thức và khả năng resume. Trong Jakarta JMS, Session là một API object quản lý việc tạo message, producer, consumer và transaction/acknowledgment theo cấu hình. Hai khái niệm có vòng đời và semantics khác nhau.

Khi đặt tên metric, nên dùng tên rõ như rsocket.connection.active, rsocket.session.active hoặc jms.listener.process để tránh gộp nhầm các lớp.

## 2. Metrics, logs và distributed tracing

Ba loại tín hiệu quan sát bổ sung cho nhau:

- **Metrics** cho biết xu hướng tổng thể: số connection, throughput, latency, error rate, queue depth và mức sử dụng tài nguyên. Dùng để tạo dashboard, cảnh báo và theo dõi SLO.
- **Logs** ghi sự kiện cụ thể: connection đã đóng vì lý do gì, message nào bị từ chối, consumer nào gặp exception. Dùng correlation ID hoặc message ID để tìm một luồng xử lý cụ thể.
- **Distributed traces** nối các bước xử lý của một message qua producer, broker, consumer và các service downstream. Trace giúp xác định thời gian bị tiêu tốn ở đâu.

Micrometer Observation cung cấp một API để instrument một hoạt động một lần, sau đó ObservationHandler có thể tạo metrics và traces. Observation có thể ghi thời gian, trạng thái lỗi và các thuộc tính ngữ cảnh.

Các meter thường dùng:

| Meter | Dùng để đo | Ví dụ |
|---|---|---|
| Counter | Số sự kiện tích lũy | Số message xử lý thành công, số connection mở, số lỗi |
| Gauge | Giá trị tại thời điểm quan sát | Số connection hiện tại, subscription đang hoạt động, queue size |
| Timer | Thời gian và số lần một thao tác hoàn tất | Thời gian publish hoặc xử lý message |
| LongTaskTimer | Thời gian và số thao tác vẫn đang chạy | Stream dài hạn hoặc consumer task chưa kết thúc |
| DistributionSummary | Phân bố một giá trị số | Payload size, batch size, số message trong một batch |

Counter thường tăng đơn điệu trong suốt vòng đời process. Gauge có thể tăng và giảm. Timer lưu cả số lần ghi nhận và phân bố thời gian; khi theo dõi latency nên quan tâm percentile/histogram hoặc SLO bucket thay vì chỉ nhìn giá trị trung bình.

## 3. Metric cần theo dõi ở từng lớp

### 3.1. Transport connection

Theo dõi:

- Số connection đang mở.
- Tổng connection được tạo và đóng trong khoảng thời gian.
- Thời gian sống của connection.
- Số lần reconnect, connect timeout và handshake failure.
- Số disconnect theo nhóm nguyên nhân.
- Tỷ lệ connection bị đóng bất thường.
- Số connection đang chờ hoặc đang được thiết lập nếu transport cung cấp thông tin đó.

Một dashboard chỉ có số connection hiện tại có thể bỏ sót hiện tượng reconnect liên tục. Hãy ghép gauge connection active với counter opened/closed và timer connection lifetime. Nếu số connection active ổn định nhưng số opened/closed tăng nhanh, hệ thống có thể đang churn connection.

Đối với pool hoặc broker client, theo dõi thêm connection đang dùng, connection idle, số request đang chờ connection và thời gian chờ lấy connection. Không gộp pool connection với logical session ở tầng messaging.

### 3.2. Protocol session

Với RSocket, theo dõi:

- Số session logic đang hoạt động.
- Số lần session được thiết lập mới.
- Số lần resume thành công và thất bại.
- Số session hết hạn hoặc bị từ chối.
- Tuổi session và số lần reconnect trên một session.
- Số lần keepalive timeout hoặc lỗi protocol nếu implementation cung cấp.

Resume là cơ chế giữ trạng thái giao thức qua một số lần transport gián đoạn. Nếu connection mới resume được session cũ, không nên tính nó như một session logic hoàn toàn mới. Cần có định danh session nội bộ để phân biệt connection generation và logical session, nhưng không đưa định danh riêng từng phiên vào metric tag.

### 3.3. Subscription và stream

Theo dõi:

- Số subscription đang hoạt động.
- Số subscription được tạo, hoàn tất, lỗi và bị cancel.
- Thời gian sống của subscription.
- Thời gian từ subscribe tới phần tử đầu tiên.
- Số message phát ra và số message được xử lý.
- Số stream không phát dữ liệu trong khoảng thời gian dài.
- Demand/backpressure, buffer hoặc queue nội bộ nếu implementation có thể đo.
- Số stream bị hủy khi connection đóng hoặc consumer ngừng hoạt động.

Đối với RSocket request-stream và request-channel, phân biệt stream đang mở với message đang được truyền. Một subscription có thể tồn tại lâu nhưng không có message mới vì producer đang idle, requester không yêu cầu thêm demand hoặc nguồn đang bị backpressure.

### 3.4. Consumer và message processing

Ở phía consumer, theo dõi:

- Số message nhận và số message xử lý xong.
- Processing duration và thời gian chờ trước khi bắt đầu xử lý.
- Số lỗi theo nhóm nguyên nhân.
- Số lần redelivery, retry, acknowledgment và reject nếu broker cung cấp.
- Số message chuyển vào dead-letter queue (DLQ).
- Số consumer đang hoạt động và concurrency thực tế.
- Queue depth, oldest message age và consumer lag.
- Batch size, số message mỗi lần poll và số lần poll không có message.

Đừng chỉ đếm message đã nhận. Message được nhận nhưng chưa được xử lý, xử lý lỗi hoặc chưa được ACK có trạng thái khác nhau. Hãy xác định chính xác điểm mà mỗi counter được tăng.

### 3.5. Executor và tài nguyên xử lý

Consumer bất đồng bộ thường phụ thuộc executor hoặc scheduler. Theo dõi:

- Active threads và pool size.
- Queue size và remaining capacity.
- Số task bị từ chối.
- Thời gian task chờ trong queue.
- Task execution duration.
- CPU, heap, garbage collection và thread utilization.

Nếu queue của executor tăng trong khi active threads luôn đạt giới hạn, consumer có thể thiếu concurrency hoặc handler đang chậm. Nếu task bị reject, cần kiểm tra queue capacity và chính sách từ chối.

## 4. Những gì Spring đã instrument sẵn

Không phải mọi ứng dụng Spring Messaging đều tự có cùng một bộ metric. Khả năng quan sát phụ thuộc module, loại component, dependency và cấu hình.

### 4.1. Spring Framework Observation cho JMS

Spring Framework tích hợp Jakarta JMS instrumentation của Micrometer khi dependency io.micrometer:micrometer-jakarta9 có trên classpath. Hai observation chính là:

- jms.message.publish: thời gian gửi message tới destination, thường qua JmsTemplate.
- jms.message.process: thời gian ứng dụng xử lý message đã nhận, thường qua MessageListener hoặc phương thức @JmsListener.

Hiện tại không có observation mặc định jms.message.receive để đo thời gian chờ nhận message. Thời gian xử lý được đo riêng sau khi message đã được nhận.

Các observation JMS có low-cardinality keys như error, messaging.destination.temporary và messaging.operation. Các giá trị conversation ID, destination name và message ID là high-cardinality keys; chúng phù hợp với trace hơn là metric tags.

### 4.2. Cấu hình ObservationRegistry cho JMS

Với JmsTemplate tự tạo, đặt ObservationRegistry vào template. Với listener container, cấu hình registry trên DefaultJmsListenerContainerFactory đang được @JmsListener sử dụng.

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsObservabilityConfiguration {

    @Bean
    JmsTemplate observedJmsTemplate(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setObservationRegistry(observationRegistry);
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

Đây là cấu hình mẫu cho ứng dụng tự khai báo các bean JMS. Trong Spring Boot, các bean JmsTemplate và phương thức @JmsListener được hỗ trợ auto-instrumentation khi dependency và cấu hình cần thiết có mặt. Nếu ứng dụng có nhiều listener container factory, hãy xác nhận từng @JmsListener đang tham chiếu đúng factory đã cấu hình.

### 4.3. Spring Boot Actuator và Micrometer

Spring Boot tự cấu hình MeterRegistry và registry exporter tương ứng khi dependency được khai báo. Một số instrumentation thường có sẵn:

- JVM metrics: memory, buffer pool, garbage collection và thread utilization.
- System/process metrics: CPU, file descriptor, uptime và disk.
- ThreadPoolTaskExecutor và ThreadPoolTaskScheduler metrics khi underlying ThreadPoolExecutor có sẵn.
- JMS metrics cho JmsTemplate và @JmsListener.
- Các instrumentation khác như HTTP client/server và datasource tùy stack.

Endpoint /actuator/metrics dùng để kiểm tra các meter đã đăng ký và xem giá trị hiện tại. Đây là công cụ chẩn đoán, không phải metrics backend để scrape trong production. Hãy xuất metrics tới Prometheus hoặc registry/backend đã chọn. Khi dùng Prometheus registry, có thể expose endpoint Prometheus theo cấu hình Actuator và bảo vệ endpoint theo chính sách truy cập của hệ thống.

### 4.4. Spring Integration metrics cho channel và handler

Khi Spring Integration có MeterRegistry, các component phổ biến kế thừa AbstractMessageChannel, AbstractMessageHandler và AbstractMessageSource được instrument tự động.

Các meter thường gặp:

| Meter | Thành phần | Ý nghĩa |
|---|---|---|
| spring.integration.send | MessageChannel | Thời gian send, có tag type=channel |
| spring.integration.receive | Pollable MessageChannel | Số message receive và kết quả |
| spring.integration.send | MessageHandler | Thời gian xử lý handler, có tag type=handler |
| spring.integration.receive | MessageSource | Số message được source cung cấp |
| spring.integration.channels | Gauge | Số MessageChannel trong application |
| spring.integration.handlers | Gauge | Số MessageHandler trong application |
| spring.integration.sources | Gauge | Số MessageSource trong application |
| spring.integration.channel.queue.size | Gauge | QueueChannel hiện có bao nhiêu message |
| spring.integration.channel.queue.remaining.capacity | Gauge | QueueChannel còn bao nhiêu chỗ trống |

Các metric channel/handler thường có tag name là component name, result là success/failure và exception là none hoặc tên class exception. Với QueueChannel, queue size tăng liên tục và remaining capacity giảm là tín hiệu consumer đang không theo kịp producer.

Các metric trên thuộc Spring Integration và các component được hỗ trợ; không nên giả định mọi MessageChannel tùy biến trong spring-messaging đều tự đăng ký các meter này.

## 5. Quan sát RSocket connection, session và stream

Spring Framework cung cấp RSocketRequester, RSocketMessageHandler, @MessageMapping và @ConnectMapping. RSocket hỗ trợ các interaction model bất đồng bộ và backpressure, nhưng ứng dụng cần chọn đúng điểm instrument để đo vòng đời kết nối và stream.

### 5.1. Theo dõi connection setup

@ConnectMapping xử lý SETUP frame khi bắt đầu một RSocket connection và các METADATA_PUSH tiếp theo. Vì vậy, nó là callback cấp connection, không phải callback cho từng message request. Nếu dùng nó để ghi nhận connection, phải phân biệt setup ban đầu với metadata push để không tăng connection count nhiều lần.

Nếu dùng Spring Integration RSocket, ServerRSocketConnector phát RSocketConnectedEvent khi client kết nối. Connector cũng có thể giữ RSocketRequester của client trong registry theo khóa được cấu hình bằng clientRSocketKeyStrategy. Event này hữu ích để ghi nhận connection đã được thiết lập và liên kết với client logic.

RSocketConnectedEvent là tín hiệu kết nối. Để duy trì gauge connection active chính xác, cần gắn thêm xử lý vào vòng đời close/dispose của RSocket hoặc transport tương ứng để giảm gauge khi connection kết thúc. Không giữ gauge active chỉ bằng cách tăng ở event connect mà không có đường giảm khi close.

### 5.2. Tách connection generation và logical session

Với Resume, một logical session có thể tồn tại qua lần thay transport connection. Nên thiết kế các metric riêng:

- rsocket.connections.active: số transport connection đang mở.
- rsocket.connections.opened: tổng connection đã được thiết lập.
- rsocket.connections.closed: tổng connection đã đóng.
- rsocket.sessions.active: số logical session đang hoạt động.
- rsocket.sessions.resumed: số lần resume thành công.
- rsocket.sessions.resume.failed: số lần resume thất bại.
- rsocket.sessions.expired: số session hết hạn.

Tên trên là metric do ứng dụng tự định nghĩa, không phải tên meter mặc định của Spring. Cần cập nhật session gauge theo trạng thái logic và tránh đếm một lần resume thành một session mới nếu session cũ vẫn được khôi phục.

### 5.3. Theo dõi subscription và stream

Ở phía requester, mỗi lần subscribe vào Flux có thể tạo một request stream hoặc một luồng tiêu thụ dữ liệu. Có thể dùng Flux.defer để tăng active subscription khi có subscriber thật và doFinally để giảm khi stream complete, error hoặc cancel.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

final class RSocketSubscriptionMetrics {

    private final MeterRegistry registry;
    private final AtomicInteger active = new AtomicInteger();

    private final Counter received;
    private final Counter completed;
    private final Counter failed;
    private final Counter cancelled;
    private final Timer duration;

    RSocketSubscriptionMetrics(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder(
                "app.rsocket.subscriptions.active",
                this.active,
                AtomicInteger::get)
            .description("Active RSocket stream subscriptions")
            .register(registry);

        this.received = Counter.builder("app.rsocket.subscription.messages")
                .tag("transport", "rsocket")
                .register(registry);

        this.completed = Counter.builder("app.rsocket.subscription.completed")
                .tag("transport", "rsocket")
                .register(registry);

        this.failed = Counter.builder("app.rsocket.subscription.failed")
                .tag("transport", "rsocket")
                .register(registry);

        this.cancelled = Counter.builder("app.rsocket.subscription.cancelled")
                .tag("transport", "rsocket")
                .register(registry);

        this.duration = Timer.builder("app.rsocket.subscription.duration")
                .tag("transport", "rsocket")
                .register(registry);
    }

    Flux<String> observe(Flux<String> source) {
        return Flux.defer(() -> {
            this.active.incrementAndGet();
            Timer.Sample sample = Timer.start(this.registry);

            return source
                    .doOnNext(item -> this.received.increment())
                    .doFinally(signal -> {
                        this.active.decrementAndGet();
                        sample.stop(this.duration);

                        if (signal == SignalType.ON_COMPLETE) {
                            this.completed.increment();
                        }
                        else if (signal == SignalType.ON_ERROR) {
                            this.failed.increment();
                        }
                        else if (signal == SignalType.CANCEL) {
                            this.cancelled.increment();
                        }
                    });
        });
    }
}
~~~

Đây là component minh họa cho subscription phía ứng dụng, không tự động đo mọi stream trong RSocket server. Gọi observe() tại nơi tạo hoặc trả Flux cho requester. Flux.defer bảo đảm active chỉ tăng khi có subscription thực sự; doFinally chạy khi complete, error hoặc cancel nên active được giảm đúng một lần cho mỗi subscription.

Nếu một Flux được subscribe nhiều lần, mỗi lần là một subscription riêng và được đo riêng. Hãy cân nhắc semantics của cold/hot publisher để tránh vô tình tạo thêm subscriber chỉ vì instrumentation.

### 5.4. Backpressure và stream không tiến triển

RSocket dùng Reactive Streams demand. Requester có thể yêu cầu thêm message; responder phải tôn trọng demand. Khi stream không tiến triển, theo dõi:

- Số subscription active và tuổi subscription.
- Số message phát ra và số message xử lý xong.
- Thời gian từ subscribe tới phần tử đầu tiên.
- Demand/requested amount nếu có thể instrument ở publisher hoặc protocol layer.
- Buffer size, queue depth và executor saturation.
- Số cancellation và terminal signal.

Một subscription active lâu không nhất thiết là lỗi: event stream có thể được thiết kế để tồn tại liên tục. Cần kết hợp tuổi subscription với thời gian không có message, expected heartbeat, demand và SLO của route để phát hiện stream bị kẹt.

## 6. Cardinality: không đưa định danh từng message vào metric tag

Một metric có thể có nhiều chuỗi thời gian nếu mỗi tag nhận quá nhiều giá trị. Đây là vấn đề cardinality.

Các tag thường có cardinality thấp:

- application, environment, region.
- transport: tcp, websocket, jms.
- interaction: request-response, request-stream, request-channel, fire-and-forget.
- outcome: success, error, cancelled.
- error.category: timeout, unavailable, validation, authentication.
- consumer group hoặc destination template nếu số lượng được giới hạn.

Các giá trị thường có cardinality cao:

- sessionId, connectionId, clientId riêng lẻ.
- messageId, correlationId, traceId.
- userId, email hoặc tenantId nếu số lượng lớn.
- URL/path có giá trị động.
- timestamp hoặc payload value.

Đưa ID riêng của mỗi message hoặc session vào metric tag có thể tạo hàng trăm nghìn hoặc hàng triệu time series, làm tăng bộ nhớ, chi phí lưu trữ và truy vấn. Hãy giữ các ID này trong log hoặc trace. Metric dùng các nhóm hữu hạn để trả lời câu hỏi tổng thể.

Với Micrometer Observation, low-cardinality key values được đưa vào metrics; high-cardinality key values phù hợp với traces. Đây là cách phân tách có chủ đích để giữ metric ổn định.

## 7. Truyền tracing context qua message

Một request thường đi qua nhiều thread và có thể qua broker hoặc service khác. Nếu tracing context không được truyền trong message headers, trace sẽ bị đứt thành nhiều phần độc lập.

Spring Integration có cơ chế observation propagation trên channel và consumer. Khi bật observation trên cả channel và consumer, thông tin tracing được ghi vào message headers trước khi message được chuyển sang consumer thread hoặc lưu trữ; consumer khôi phục thông tin đó để tạo child Observation.

Đối với JMS, publish observation có thể truyền tracing information qua message headers và process observation ở listener khôi phục context cho xử lý message. Với các adapter hoặc custom channel, cần kiểm tra cấu hình observation propagation thực tế.

Một trace hữu ích nên cho thấy:
1. Producer tạo và gửi message.
2. Broker nhận và giữ message.
3. Consumer nhận message.
4. Consumer bắt đầu xử lý.
5. Các lời gọi downstream trong quá trình xử lý.
6. Consumer hoàn tất, lỗi hoặc ACK/reject.

Không dùng trace thay cho metric. Trace giúp tìm nguyên nhân của một message chậm; metric cho biết tỷ lệ message chậm có đang tăng trên toàn hệ thống hay không.

## 8. Dashboard và cảnh báo

Một dashboard vận hành có thể chia thành các nhóm:

| Nhóm | Biểu đồ nên có | Dấu hiệu cần điều tra |
|---|---|---|
| Connection | Active, opened/closed rate, reconnect, lifetime | Connection churn, reconnect spike, active giảm đột ngột |
| Session | Active session, resume success/failure, expired | Resume thất bại tăng, session hết hạn sớm |
| Subscription | Active streams, started/completed/error/cancel, duration | Stream active tăng nhưng không phát dữ liệu |
| Consumer | Process rate, processing latency, error rate, redelivery | Throughput giảm, latency tăng, DLQ tăng |
| Backlog | Queue depth, oldest message age, consumer lag | Queue tăng liên tục hoặc message chờ quá lâu |
| Executor | Active threads, pool size, queue size, rejected tasks | Worker bão hòa, task bị từ chối |
| JVM/process | Heap, GC pause, CPU, threads, uptime | Áp lực tài nguyên trùng với suy giảm xử lý |

Cảnh báo nên dựa trên SLO và hành vi nền của hệ thống, không dùng một ngưỡng cố định cho mọi ứng dụng. Ví dụ:

- Queue age vượt mục tiêu xử lý trong một khoảng thời gian liên tục.
- Consumer error rate hoặc DLQ rate vượt ngưỡng.
- Active connection giảm bất thường trong khi request rate vẫn cao.
- Reconnect/resume failure tăng đột biến.
- Executor queue tăng liên tục và rejected task xuất hiện.
- Subscription tồn tại lâu hơn giới hạn nghiệp vụ hoặc không có progress dù vẫn có demand.

Không cảnh báo chỉ vì active subscription lớn nếu hệ thống được thiết kế với nhiều stream dài hạn. Cần so sánh với baseline, tải đầu vào và số message thực sự được xử lý.

## 9. Chẩn đoán theo triệu chứng

### 9.1. Connection active ổn định nhưng message throughput bằng không

Kiểm tra subscription có còn active không, consumer có được đăng ký đúng route không, publisher có còn phát dữ liệu không và requester có cấp demand không. Với RSocket, connection sống không có nghĩa stream đang tiến triển.

### 9.2. Connection opened/closed tăng nhanh

Kiểm tra network reset, load balancer timeout, keepalive, connection pool, broker restart và retry policy. Ghép log theo thời điểm và transport endpoint để xác định nguyên nhân. Không đưa connection ID riêng lẻ vào metric tag.

### 9.3. Subscription active tăng nhưng completion giảm

Có thể stream dài hạn là thiết kế bình thường, hoặc stream bị treo. Kiểm tra subscription age, last item time, demand, backpressure, cancellation và resource cleanup. Nếu stream lỗi nhưng không kết thúc, kiểm tra publisher có giữ subscription mà không phát tín hiệu terminal hay không.

### 9.4. Consumer lag hoặc queue age tăng

So sánh incoming rate với processed rate. Kiểm tra concurrency, executor queue, processing duration, downstream latency, redelivery và lỗi lặp lại. Nếu consumer bị chậm do dependency downstream, tăng số worker có thể làm dependency quá tải nặng hơn.

### 9.5. JMS publish tốt nhưng process chậm

So sánh jms.message.publish với jms.message.process và metric broker về queue depth/oldest message age. Publish timer đo thời gian gửi; process timer đo thời gian xử lý trong ứng dụng. Thời gian message nằm trong broker cần metric phía broker hoặc timestamp enqueue/receive do ứng dụng ghi nhận.

### 9.6. Metric connection active không giảm khi client đã ngắt

Kiểm tra close/dispose signal có được nối vào code giảm gauge không. Bảo đảm mỗi connection chỉ giảm đúng một lần, kể cả khi đồng thời nhận callback close và error. Dùng một handle có cờ atomic để tránh decrement lặp.

## 10. Kiểm thử instrumentation

Instrumentation cũng cần được kiểm thử như logic ứng dụng.

- Connection mở làm opened counter tăng và active gauge tăng một.
- Connection đóng làm closed counter tăng và active gauge giảm một.
- Callback đóng lặp lại không làm active gauge âm.
- Resume cùng logical session không bị tính nhầm thành một session mới.
- Mỗi subscription thực tế tăng active đúng một lần.
- Complete, error và cancel đều giảm active.
- Message counter chỉ tăng khi phần tử thực sự đi qua subscription.
- Consumer processing timer dừng cả khi handler thành công và khi ném exception.
- Metric tags chỉ dùng các giá trị hữu hạn.
- Trace context được truyền qua executor/channel và consumer thread.
- Khi ApplicationContext đóng, listener container, connection và executor được giải phóng.

Có thể dùng SimpleMeterRegistry để kiểm tra meter trong unit test. Với reactive stream, StepVerifier giúp xác nhận complete/error/cancel và đọc lại gauge/counter sau khi stream kết thúc. Với broker thật, dùng integration test để xác nhận ACK, redelivery, queue depth và consumer lifecycle.

## 11. Checklist triển khai production

- [ ] Định nghĩa rõ connection, logical session, stream/subscription và consumer.
- [ ] Theo dõi active connection cùng opened/closed rate và lifetime.
- [ ] Theo dõi session resume, timeout và expiration nếu sử dụng RSocket Resume.
- [ ] Theo dõi subscription start, active, complete, error, cancel và duration.
- [ ] Theo dõi consumer throughput, processing latency, failures, redelivery và DLQ.
- [ ] Theo dõi queue depth, oldest message age và consumer lag từ broker hoặc adapter tương ứng.
- [ ] Bật Spring Boot Actuator/Micrometer và cấu hình exporter tới metrics backend.
- [ ] Bật ObservationRegistry cho JMS template và listener container nếu cần instrumentation.
- [ ] Bật Spring Integration metrics cho channel/handler/source khi dùng các component tương ứng.
- [ ] Instrument RSocket lifecycle tại connector/transport và không nhầm connect callback với disconnect callback.
- [ ] Propagate tracing context qua message headers, channel và consumer.
- [ ] Không đưa sessionId, connectionId, messageId hoặc traceId vào metric tags.
- [ ] Đặt dashboard và alert dựa trên SLO, backlog và tiến độ xử lý.
- [ ] Kiểm thử close lặp, resume, stream cancel, consumer failure và cleanup.

## Tài liệu tham khảo

- Spring Framework Reference — Observability Support, JMS messaging instrumentation: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework Reference — RSocket, interaction models và @ConnectMapping: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot Reference — Actuator Metrics, JMS metrics và task executor metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Integration Reference — Metrics and Management, channel/handler/source meters và QueueChannel gauges: https://docs.spring.io/spring-integration/reference/metrics.html
- Spring Integration Reference — RSocket Support, RSocketConnectedEvent và requester registry: https://docs.spring.io/spring-integration/reference/rsocket.html
- Micrometer Reference — Observation Components, ObservationHandler và low/high cardinality: https://docs.micrometer.io/micrometer/reference/observation/components.html
