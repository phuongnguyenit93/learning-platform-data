# Hành động khi consumer không phản hồi

Trong **Spring Kafka Reliability Operations**, consumer **không phản hồi** là một tình huống cần điều tra vì Kafka consumer hoặc listener container không tiến hành vòng **poll()** đúng nhịp mong đợi. Tình huống này khác với **idle** (topic không có dữ liệu) và **pause** (container chủ động ngừng nhận record mới nhưng vẫn poll). Nếu một consumer không poll trong thời gian dài, nó có thể không xử lý được records, tăng backlog hoặc mất quyền sở hữu partition sau khi vượt **max.poll.interval.ms**.

Spring Kafka cung cấp **NonResponsiveConsumerEvent** làm tín hiệu phát hiện sớm khi khoảng thời gian từ lần poll gần nhất vượt ngưỡng giám sát. Event này **không tự chứng minh** Kafka broker bị hỏng, không cho biết chính xác thread bị kẹt ở đâu và không tự restart container. Việc phục hồi phải dựa vào nguyên nhân thực tế và trạng thái offset, transaction, side effects.

Nguyên tắc xuyên suốt: **quan sát → phân loại → thu bằng chứng → chọn hành động ít rủi ro nhất → xác nhận dữ liệu và consumer đã phục hồi**. Không biến một warning thành restart loop, cũng không bỏ qua record bằng cách commit offset tùy tiện.

## 1. Bài toán vận hành

Giả sử order-service đang đọc orders.events. Ban đầu consumer xử lý 1.000 events/phút. Một thời điểm, nhóm vận hành quan sát:

- Records vẫn tiếp tục được producer ghi vào Kafka.
- Committed offsets của group không tiến.
- Consumer lag tăng.
- Container có thể vẫn báo trạng thái running.
- Không có log success mới từ @KafkaListener.
- Spring Kafka bắt đầu phát NonResponsiveConsumerEvent.

Cần xác định consumer đang kẹt ở **KafkaConsumer.poll()**, trong **listener nghiệp vụ**, trong **error handler/backoff**, đang **rebalance**, hay đơn giản bị **pause**. Từ đó mới quyết định sửa downstream dependency, giảm tải, restart một listener container hay escalation.

Một hướng xử lý sai có thể khiến records bị giao lại nhiều lần, database bị trừ tiền/giữ tồn kho trùng, Kafka transaction bị abort hoặc cả consumer group liên tục rebalance.

## 2. Phân biệt idle, paused, slow và non-responsive

| Trạng thái | Consumer poll | Listener nhận records | Ý nghĩa |
|---|---|---|---|
| Idle | Thường vẫn poll đều | Không nhận records vì không có dữ liệu | Có thể hoàn toàn bình thường |
| Paused | Thường vẫn poll để giữ membership | Không nhận thêm từ partitions đã pause | Backpressure hoặc bảo trì chủ động |
| Slow listener | Poll tiếp theo bị trễ | Có record đang xử lý lâu | Có thể vượt max.poll.interval.ms |
| Poll stuck | Poll không trở về đúng nhịp | Không dispatch thêm | Nghi vấn network/client/coordinator |
| Rebalance | Poll phối hợp group | Có thể tạm dừng delivery | Cần xem assignment và callback |
| Container stopped | Không tiếp tục poll sau khi stop hoàn tất | Không nhận records | Lifecycle state, không phải idle |

**ListenerContainerIdleEvent** báo container không nhận dữ liệu trong một khoảng thời gian. **NonResponsiveConsumerEvent** liên quan **khoảng không poll bất thường**. Một consumer có thể idle nhiều giờ và vẫn khỏe, vì poll vẫn chạy.

~~~mermaid
flowchart TD
    A["Không thấy record được xử lý"] --> B{"Container RUNNING?"}
    B -->|Không| C["Kiểm tra lifecycle và startup"]
    B -->|Có| D{"Poll vẫn chạy đúng nhịp?"}
    D -->|Có| E{"Paused hoặc không có records?"}
    E -->|Có| F["Idle / backpressure có chủ đích"]
    E -->|Không| G["Kiểm tra lag, retry, deserialize, assignment"]
    D -->|Không| H["Non-responsive / poll gap"]
    H --> I["Thread dump, broker, network, listener duration"]
    I --> J["Recovery có kiểm soát"]
~~~

Đừng kết luận chỉ dựa trên consumer lag. Lag cũng có thể tăng do producers ghi nhanh hơn năng lực xử lý hoặc do pause có chủ đích.

## 3. NonResponsiveConsumerEvent có ý nghĩa gì?

Spring Kafka có cơ chế monitor kiểm tra khoảng thời gian kể từ lần poll của consumer. Khi phát hiện thời gian đó vượt ngưỡng, nó có thể publish **NonResponsiveConsumerEvent**.

Event thường cung cấp những thông tin sau, tùy phiên bản:

- **listenerId**: ID của listener/container được quan sát.
- **timeSinceLastPoll**: thời gian kể từ poll gần nhất, thường tính bằng mili giây.
- **topicPartitions**: các TopicPartition liên quan.
- **consumer**: tham chiếu consumer khi API cung cấp.
- Source/container metadata của Spring application event.

Điểm phải ghi nhớ:

1. Event là **warning signal**; cần kiểm chứng poll metrics và thread state.
2. Event có thể **lặp lại** khi một consumer tiếp tục không phản hồi.
3. Không phải cứ có event là consumer đã rời consumer group.
4. Event không chứng minh có record bị mất hay transaction đã fail.
5. Event không tự stop, seek, commit hay restart.
6. Trong concurrent container, một child consumer có thể lỗi riêng.

Một monitor quan sát khoảng poll dài có thể báo cả khi listener xử lý quá lâu; vì vậy “consumer không poll lại” không đồng nghĩa chắc chắn phương thức poll() bên trong Kafka client đã deadlock.

## 4. Ngưỡng phát hiện: pollTimeout, noPollThreshold, monitorInterval

Các thuộc tính quan trọng:

| Thuộc tính Spring Kafka | Tác dụng |
|---|---|
| pollTimeout | Thời gian một lời gọi poll có thể chờ dữ liệu theo cấu hình container |
| noPollThreshold | Hệ số đánh giá khoảng không poll đáng nghi |
| monitorInterval | Chu kỳ monitor kiểm tra trạng thái consumer |

Ví dụ minh họa:

~~~text
pollTimeout     = 5.000 ms
noPollThreshold = 3.0
monitorInterval = 10 giây

Ngưỡng giám sát tham chiếu: 3 x 5.000 = 15.000 ms.
Vì monitor kiểm tra theo chu kỳ, event có thể phát muộn hơn
thời điểm vừa vượt ngưỡng, không chính xác ở mili giây 15.000.
~~~

Cơ chế Spring Kafka dùng khoảng thời gian từ poll so với noPollThreshold × pollTimeout để xác định bất thường theo phiên bản tương ứng. Các giá trị mặc định có thể thay đổi giữa các thế hệ framework; nên xác minh dependency hiện tại.

**Đây là ngưỡng giám sát của framework, không phải max.poll.interval.ms của Kafka client.** Điều chỉnh monitorInterval chỉ ảnh hưởng lúc phát hiện/cảnh báo, không thay đổi timeout mà consumer group áp dụng.

## 5. Ví dụ cấu hình listener factory

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setMonitorInterval(10);
        factory.getContainerProperties().setNoPollThreshold(3.0f);

        return factory;
    }
}
~~~

Listener cần sử dụng đúng container factory này:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "orderListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        processor.process(event);
    }
}
~~~

Các class OrderEvent và OrderProcessor là ví dụ domain. Khi dùng Spring Boot auto-configuration hoặc nhiều factory khác nhau, kiểm tra listener thực sự được gắn đúng factory.

Đặt ngưỡng quá thấp có thể tạo false positives khi JVM GC pause hoặc listener xử lý lâu nhưng hợp lệ. Ngưỡng quá cao lại khiến phát hiện chậm, có thể sau khi group đã rebalance.

## 6. Lắng nghe event qua @EventListener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPollHealthObserver {

    private static final Logger log =
        LoggerFactory.getLogger(ConsumerPollHealthObserver.class);

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        log.warn(
            "Kafka consumer not responsive: listenerId={}, sincePollMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions()
        );
    }
}
~~~

Phản ứng đầu tiên nên là **logging/metric/diagnostic trigger nhẹ**, không restart ngay. Event callback không nên gọi API monitoring đồng bộ với timeout dài hoặc thực hiện business query nặng.

Tên getter/phạm vi metadata cần tương thích với phiên bản Spring Kafka đang dùng. Nếu cần group ID, instance ID hoặc pause reason, có thể bổ sung từ application config/container observation thay vì tự suy từ event.

## 7. Thread safety của KafkaConsumer

Trong Spring Kafka, consumer thread do listener container quản lý. KafkaConsumer nói chung **không thread-safe** cho việc poll, seek, commit, pause hay resume tùy ý ở những threads khác.

Một NonResponsiveConsumerEvent có thể được publish từ monitor thread. Ngay cả khi event có tham chiếu KafkaConsumer, không nên:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Không an toàn nếu gọi từ thread không sở hữu consumer:
    // event.getConsumer().commitSync();
    // event.getConsumer().seek(...);
}
~~~

Nếu cần điều khiển lifecycle, dùng **MessageListenerContainer** hoặc **KafkaListenerEndpointRegistry**; nếu cần điều khiển partition processing, dùng những API do Spring Kafka container cung cấp.

Đừng giữ raw KafkaConsumer trong singleton để gọi từ REST endpoint phục hồi. Cần tôn trọng consumer thread confinement và transaction/ack ownership.

## 8. IdleEvent, PauseEvent và NonResponsiveEvent

| Event | Phạm vi diễn giải |
|---|---|
| ListenerContainerIdleEvent | Không nhận records mới đủ khoảng idle |
| ListenerContainerNoLongerIdleEvent | Có records trở lại sau trạng thái idle |
| NonResponsiveConsumerEvent | Không poll lại theo ngưỡng monitor |
| ConsumerPausedEvent | Container/consumer đã pause |
| ConsumerResumedEvent | Container/consumer đã resume |
| ConsumerStoppedEvent | Consumer đã dừng |
| ConsumerPartitionPausedEvent | Một partition đã pause, nếu phiên bản hỗ trợ |

Ví dụ topic rỗng suốt một giờ nhưng consumer vẫn poll bình thường: có thể có IdleEvent, không nhất thiết NonResponsiveEvent.

Ví dụ consumer đang xử lý một SQL query bị lock wait vô hạn: topic vẫn có records, nhưng listener không quay lại poll, có thể có NonResponsiveEvent.

Một dashboard gom tất cả events thành “consumer offline” sẽ không giúp operator chọn đúng hành động.

## 9. Listener xử lý chậm là nguyên nhân phổ biến

Ví dụ:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) throws Exception {

    // Không có timeout là rủi ro blocking.
    downstreamFuture.get();

    orderService.save(event);
}
~~~

Nếu downstreamFuture không hoàn tất, thread có thể không quay lại poll. Một số nguồn blocking thường gặp:

- HTTP call không có connect/read timeout.
- JDBC query chờ lock/connection pool.
- CompletableFuture.get()/join() không deadline.
- CountDownLatch.await() không timeout.
- Synchronized lock hoặc ReentrantLock deadlock.
- Manual retry bằng Thread.sleep dài.
- Batch chứa quá nhiều records.
- Heavy CPU/GC khiến thread không được lên lịch.

Hướng xử lý: thêm timeout, circuit breaker, bounded executor, giảm transaction duration và đo listener processing latency. Không nên chỉ tăng noPollThreshold để tắt cảnh báo.

## 10. Consumer bị kẹt trong poll hoặc group coordination

Một số nguyên nhân không xuất phát từ business listener:

1. Broker/coordinator unavailable.
2. DNS hoặc TCP connection không ổn định.
3. TLS/SASL authentication thất bại.
4. Network partition hoặc packet loss.
5. Broker quota/throttling.
6. Partition leader changes.
7. Rebalance callbacks quá lâu.
8. Custom interceptor/deserializer blocking.
9. Kafka client/framework version issue.
10. JVM stop-the-world GC hoặc CPU starvation.

Nếu **nhiều consumers ở nhiều services cùng báo** trong cùng thời điểm, kiểm tra broker/network chung trước khi restart hàng loạt ứng dụng.

Nếu chỉ một child consumer trong một JVM bị ảnh hưởng, ưu tiên thread dump, listener processing và partition assignment tương ứng.

## 11. max.poll.interval.ms và heartbeat

Kafka consumer có thể cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

Trong ví dụ, max.poll.interval.ms là 5 phút. Nếu consumer không quay lại poll đúng hạn vì processing quá lâu, consumer group có thể rebalance hoặc transfer partition.

Phân biệt:

| Cấu hình | Chức năng |
|---|---|
| max.poll.interval.ms | Giới hạn thời gian giữa các poll cho tiến độ group membership |
| session.timeout.ms | Giới hạn session liveness theo group protocol |
| heartbeat.interval.ms | Nhịp heartbeat khi phù hợp với protocol |
| pollTimeout | Thời gian đợi một poll của listener container |
| noPollThreshold | Ngưỡng Spring monitor xem poll gap bất thường |
| monitorInterval | Chu kỳ Spring monitor kiểm tra |

Tăng max.poll.interval.ms không chữa deadlock; nó có thể chỉ trì hoãn failover. Tăng noPollThreshold không thay đổi hành vi broker.

## 12. Batch processing gây poll gap

Giả sử poll trả 300 records và mỗi record cần 2 giây:

~~~text
poll() trả 300 records
listener xử lý tuần tự 300 x 2 giây = 600 giây
consumer chưa quay lại poll trước khi batch hoàn tất
~~~

Nếu max.poll.interval.ms là 300 giây, consumer có nguy cơ vượt giới hạn. NonResponsiveConsumerEvent cũng có thể được phát.

Giải pháp:

- Giảm max.poll.records.
- Tối ưu database/API calls.
- Giới hạn thời gian mỗi record.
- Thiết kế batch/scope theo partition khi phù hợp.
- Kiểm thử trường hợp một record lỗi giữa batch.
- Đảm bảo offset không commit vượt record chưa xử lý.
- Dùng idempotency để chịu redelivery sau rollback/rebalance.

Không lấy offset lớn nhất của toàn batch rồi commit khi một số records chưa hoàn tất.

## 13. Database deadlocks và lock waits

Một listener có thể vào database transaction và chờ lock:

~~~text
Kafka record
 -> Spring @Transactional service
 -> UPDATE inventory
 -> Database lock wait
 -> Listener không return
 -> Poll gap tăng
 -> NonResponsiveConsumerEvent
~~~

Điều tra:

- DB deadlock logs/lock wait timeout.
- SQL slow query và indexes.
- Connection pool active/waiting.
- Thứ tự lấy khóa nhất quán giữa services.
- Concurrent records cùng aggregate/key.
- Transaction duration.
- Rollback trước retry.
- Database isolation level và retry budget.

Nếu database đã rollback một deadlock, retry có giới hạn có thể hợp lý. Nếu thread chờ vô hạn do cấu hình thiếu timeout, restart Kafka consumer không thay thế việc sửa SQL/transaction.

## 14. Rebalance callbacks có thể chặn poll

ConsumerRebalanceListener hoặc callbacks khác trong group coordination không nên thực hiện remote work vô hạn:

~~~java
@Override
public void onPartitionsRevoked(
        Collection<TopicPartition> partitions) {

    // Rủi ro nếu remote service bị outage.
    remoteCheckpointService.flushBlocking();
}
~~~

Nên giữ callback ngắn, có timeout và semantics rõ về state/offset ownership. Rebalance liên tục có thể do nhiều members restart, max.poll.interval expiry, network instability hoặc scaling.

Nếu consumer không poll do callback bị kẹt, cần xử lý callback chứ không chỉ tăng pollTimeout.

## 15. Container pause khác non-responsive

Khi **container.pause()** được áp dụng, Spring Kafka thường tiếp tục **poll()** để duy trì consumer group, trong khi không dispatch dữ liệu mới từ paused partitions. Đây là công cụ backpressure đúng khi consumer thread còn khỏe.

~~~text
DOWNSTREAM OVERLOAD:
container.pause() -> consumer tiếp tục poll -> no new work
container.resume() -> nhận records trở lại

THREAD DEADLOCK:
controller gọi pause() -> consumer thread không quay lại
actual pause có thể chưa được áp dụng
non-responsive vẫn xảy ra
~~~

Pause request không ngắt một listener đang bị block. Muốn chẩn đoán, quan sát isPauseRequested(), isConsumerPaused(), poll metrics và listener duration.

Không dùng Thread.sleep dài trong listener thay cho container pause; sleep làm chậm lần poll kế tiếp.

## 16. Retry, BackOff và error handler

Trong listener thông thường, **DefaultErrorHandler** quản lý retry và recovery khi listener lỗi. Một cấu hình BackOff dài hoặc custom handler chặn consumer thread có thể làm poll gap tăng.

Cần kiểm tra:

1. Loại exception gây retry.
2. Số attempts và tổng BackOff.
3. Error handler đang seek/redeliver hoặc giữ records?
4. Có cơ chế container-pause backoff khi delay dài không?
5. DLT recoverer và producer có hoạt động không?
6. Failed record có lặp vô hạn không?
7. AckMode và offset recovery đúng policy không?

Nếu dùng **@RetryableTopic**, main, retry và DLT listeners có thể là containers riêng. NonResponsiveConsumerEvent từ một retry container không tự chứng minh main consumer group cũng bị stuck.

Không bắt mọi exception rồi return bình thường chỉ để container tiến offset. Điều đó có thể khiến record bị xem là xử lý thành công dù nghiệp vụ chưa hoàn tất.

## 17. Thu thập thread dump

Khi consumer bị nghi stuck và JVM còn sống, thread dump là bằng chứng hữu ích. Các lệnh công cụ JDK tham khảo:

~~~text
jcmd <pid> Thread.print
jstack <pid>
~~~

Đây là ví dụ công cụ vận hành, **không phải lệnh cần chạy trong STEP 4**. Trong container image nhỏ có thể không cài jcmd/jstack.

Thu thập vài snapshot cách nhau một khoảng ngắn để xem thread có tiến triển hay dừng cố định. Đối chiếu với CPU, GC pause, thread states, lock owners, JDBC/HTTP timeouts và logs theo timestamp.

Thread dump có thể chứa chi tiết nhạy cảm. Lưu theo incident ID và chính sách bảo mật, không thu quá thường xuyên trên toàn fleet.

## 18. Hành động đầu tiên sau event

Một response an toàn:

~~~mermaid
flowchart TD
    A["NonResponsiveConsumerEvent"] --> B["Log / metric / firstSeen"]
    B --> C{"Poll tự phục hồi trong cửa sổ quan sát?"}
    C -->|Có| D["Ghi nhận transient"]
    C -->|Không| E["Kiểm tra running, paused, lag, assignment"]
    E --> F{"Có broker/DB/network outage chung?"}
    F -->|Có| G["Khắc phục dependency"]
    F -->|Không| H["Thread dump và listener diagnostics"]
    H --> I{"Có thể sửa blocker?"}
    I -->|Có| J["Sửa timeout/lock/dependency"]
    I -->|Không| K["Cân nhắc restart có giới hạn"]
    K --> L["Verify poll, offsets, processing, duplicate"]
~~~

Không auto restart ngay lần đầu nếu thiếu evidence. Một GC pause hay downstream timeout ngắn có thể tự phục hồi và restart sẽ gây rebalance không cần thiết.

## 19. Event listener không nên làm recovery đồng bộ

Một handler có thể chỉ enqueue observation:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class NonResponsiveConsumerHandler {

    private static final Logger log =
        LoggerFactory.getLogger(NonResponsiveConsumerHandler.class);

    private final ConsumerRecoveryCoordinator coordinator;

    public NonResponsiveConsumerHandler(
            ConsumerRecoveryCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @EventListener
    public void onEvent(NonResponsiveConsumerEvent event) {

        String listenerId = event.getListenerId();
        long sincePollMs = event.getTimeSinceLastPoll();

        log.warn(
            "Kafka poll gap: listenerId={}, sincePollMs={}",
            listenerId, sincePollMs
        );

        coordinator.observe(listenerId, sincePollMs);
    }
}
~~~

ConsumerRecoveryCoordinator là domain component do ứng dụng triển khai. observe phải nhanh: ghi metric/update state hoặc enqueue **một job có giới hạn**. Không thực hiện restart, HTTP request hoặc database work kéo dài ngay trong event callback.

## 20. Recovery state machine

Có thể mô hình hóa:

~~~text
HEALTHY
  |
  +-- NonResponsiveConsumerEvent --> SUSPECT
                                    |
                                    +-- poll restored --> HEALTHY
                                    |
                                    +-- sustained stall --> DIAGNOSING
                                                            |
                                                            +-- dependency outage --> WAIT_DEPENDENCY
                                                            |
                                                            +-- listener blocked --> FIX_OR_CANCEL
                                                            |
                                                            +-- stuck container --> RESTART_REQUESTED
                                                                                     |
                                                                                     +-- success --> HEALTHY
                                                                                     |
                                                                                     +-- failed --> MANUAL_REVIEW
~~~

Đây là trạng thái ứng dụng, không phải enum sẵn của Spring Kafka.

Một coordinator production cần single-flight cho từng listener, cooldown, max attempts, audit trail, phân loại outage chung và xác nhận health sau restart.

Một loạt events từ cùng monitor không được sinh ra một loạt restart jobs.

## 21. Tìm container bằng KafkaListenerEndpointRegistry

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public MessageListenerContainer find(String id) {
        return registry.getListenerContainer(id);
    }

    public void inspect(String id) {
        MessageListenerContainer container = find(id);

        if (container == null) {
            return;
        }

        boolean running = container.isRunning();
        boolean requested = container.isPauseRequested();
        boolean paused = container.isConsumerPaused();

        // Ghi log/metric cho running, requested, paused.
    }
}
~~~

Với concurrency lớn hơn một, event có thể mang child listener ID. Registry thường quản lý logical listener container, nên cần mapping ID và child container phù hợp. Không tự strip suffix tùy tiện rồi restart nhầm nhiều containers.

Một child consumer bị kẹt không tự động đòi restart toàn service.

## 22. Điều kiện cho phép restart

Một restart có thể hợp lý khi:

- Poll gap kéo dài và consumer không tự phục hồi.
- Thread dump/metrics cho thấy trạng thái stuck.
- Broker/downstream không ở outage chung không thể giải quyết bằng restart.
- In-flight work có thể rollback/reconcile.
- Consumer được thiết kế idempotent.
- Không có restart khác đang chạy.
- Cooldown/restart budget cho phép.
- Có cách xác minh assignment, poll và business processing sau restart.

Không nên restart khi container đang shutdown/deploy, stop cũ chưa hoàn tất, side effects không thể xác định hoặc root cause vẫn là một broker outage toàn cluster.

**Restart là hành động phục hồi có điều kiện, không phải semantics mặc định của NonResponsiveConsumerEvent.**

## 23. Stop/start theo lifecycle

MessageListenerContainer cung cấp lifecycle API. Ví dụ phác thảo:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {

    container.stop(() -> {
        restartExecutor.execute(() -> {

            if (!container.isRunning()
                    && recoveryPolicy.mayRestart("ordersListener")) {
                container.start();
            }
        });
    });
}
~~~

restartExecutor và recoveryPolicy là domain components minh họa. Production cần single-flight, cooldown, shutdown guard, log và error handling.

Không gọi stop(); start(); liên tiếp rồi mặc định stop hoàn thành ngay. Lifecycle có thể bất đồng bộ; consumer thread có thể đang ở blocking state.

Nếu stop không hoàn tất, escalate; không start một consumer mới trên cùng state không rõ ràng hoặc ép thread.stop().

## 24. Stop container không phải restart JVM

| Hành động | Tình huống phù hợp | Rủi ro |
|---|---|---|
| Chờ kèm alert | Transient GC/network stall | Có thể tăng SLA nếu chờ quá lâu |
| Sửa dependency | DB/HTTP/broker outage | Chưa chắc cứu thread đã deadlock |
| Pause/resume | Backpressure khi poll vẫn chạy | Không cứu thread đã bị block |
| Restart listener container | Một consumer stuck có thể thay thế | Rebalance, redelivery, transactions abort |
| Restart application instance | JVM/runtime state không phục hồi được | Ảnh hưởng nhiều listeners |
| Rolling restart service | Config/runtime lỗi toàn fleet | Có thể tạo thundering herd |
| Manual reconciliation | Side effect/commit outcome bất định | Cần operator và domain expertise |

Ưu tiên phạm vi nhỏ nhất có thể phục hồi an toàn. Liveness probe không nên kill pod chỉ vì consumer lag tăng; điều đó có thể biến downstream overload thành restart storm.

## 25. Offset, duplicate và idempotency

Restart có thể khiến records chưa commit được giao lại. Ví dụ consumer đã cập nhật database rồi crash trước khi Kafka offset commit. Khi group nhận lại record, side effect có thể được thực hiện thêm lần nữa nếu không bảo vệ.

Một giải pháp thường dùng là inbox:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
@Transactional
public void processIdempotently(OrderEvent event) {

    boolean first = processedEvents.insertIfAbsent(
        "orders-service", event.eventId()
    );

    if (!first) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Ví dụ cần domain repositories và unique constraint thực. Marker và side effect phải commit trong cùng database transaction.

Nếu gọi external API, dùng idempotency key ổn định. Nếu thay đổi DB và publish Kafka, cân nhắc outbox. Không reset offset sang latest để né một stuck record; có thể bỏ dữ liệu chưa xử lý.

## 26. Transactional listener cần thận trọng hơn

Với transactional Kafka listener container, container có thể commit Kafka output và input offsets trong cùng Kafka transaction. Khi listener lỗi, transaction abort; **AfterRollbackProcessor** có thể seek/redeliver hoặc đưa failed record sang recovery theo cấu hình.

Khi non-responsive, cần kiểm tra:

- Transaction timeout.
- Producer fencing và transactional.id.
- Consumer group generation/rebalance.
- Transaction commit/abort result.
- Kafka input offset đã được đưa vào transaction chưa.
- Downstream read_committed visibility.
- DLT/recovery publication success.
- Database/API side effects ngoài Kafka transaction.

Không tự gọi commitSync() để tiến offset trong transactional pipeline. Điều đó có thể phá atomicity của Kafka-to-Kafka processing.

Sau restart, dữ liệu có thể redeliver; Kafka EOS không đồng nghĩa external side effects chỉ chạy một lần.

## 27. Async processing không bảo đảm correctness chỉ vì poll đều

Một anti-pattern:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
    // Listener return trước khi async task thực sự hoàn tất.
}
~~~

Container có thể xem callback return bình thường là đã xử lý record, tùy AckMode. Nếu async task thất bại sau offset commit, sự kiện có nguy cơ mất cơ hội redelivery.

Cần:

1. Bounded executor queue và max in-flight.
2. Ack only after durable processing success.
3. Offset ordering theo partition.
4. Pause/resume bằng flow control khi queue cao/thấp.
5. Xử lý rebalance/shutdown khi tasks còn chạy.
6. Idempotency khi task được gọi lại.
7. Tránh gọi KafkaConsumer từ worker thread.

NonResponsiveConsumerEvent đo poll responsiveness, **không chứng minh business processing đúng**. Một poll-rate khỏe có thể đi kèm side effects chưa hoàn tất nếu async semantics sai.

## 28. Metrics quan trọng

| Metric | Mục đích |
|---|---|
| Non-responsive event count | Tần suất poll gap bị cảnh báo |
| Time since last poll | Độ dài nghi vấn stuck |
| Poll-rate, poll-latency | Kiểm tra vòng poll |
| Listener processing p95/p99 | Xem business processing có kéo dài |
| max.poll.interval violations | Group membership risk |
| Rebalance count | Assignment churn |
| Container running/paused | Lifecycle và backpressure |
| Partition assignments | Consumer còn sở hữu partition không |
| Consumer group lag | Input backlog |
| Oldest unprocessed age | SLA business |
| Database pool waiters | DB saturation |
| HTTP timeout/error rate | Downstream reliability |
| JVM GC pause/CPU | Runtime stall |
| Transaction abort/fencing | Transactional health |
| Recovery/DLT backlog | Failed records chưa phục hồi |
| Restart count/outcome | Auto recovery hiệu quả hay không |

Một số tên là **metric gợi ý**, không phải tất cả có sẵn mặc định từ Spring Kafka. Phân biệt Kafka client JMX/Micrometer với custom application observations.

Không dùng event ID, offset, key hoặc exception message làm metric tags vì cardinality cao.

## 29. Structured logging

Ví dụ:

~~~text
event=kafka_consumer_non_responsive
service=orders-service
instance=orders-pod-3
listener_id=ordersListener-1
group_id=orders-service
time_since_last_poll_ms=48000
poll_timeout_ms=5000
monitor_interval_s=10
no_poll_threshold=3.0
container_running=true
pause_requested=false
consumer_paused=false
assigned_partition_count=2
~~~

Các trường phụ như group ID, pause reason và assignment có thể phải bổ sung từ config/container. Đây không phải format log mặc định.

Nên thêm firstSeen, lastSeen và incident ID để gom các events liên tiếp. Không log payload hoặc credentials. Nếu cần truy vết record đang xử lý, dùng structured tracing với topic/partition/offset có kiểm soát.

## 30. Giảm nhiễu và chống restart storm

Một consumer stuck có thể phát nhiều NonResponsiveConsumerEvent trong vài phút. Nếu mỗi event đều tạo pager hoặc restart, sẽ gây alert storm và rebalance churn.

Chính sách hợp lý:

- Group alerts theo service + instance + listener ID.
- Phân severity theo **thời gian stuck + lag + business SLA**.
- Dùng cooldown giữa recovery attempts.
- Single-flight: một recovery job cho một container.
- Correlate broker/DB outages chung.
- Không restart toàn fleet khi cluster cùng lỗi.
- Giới hạn max restart attempts rồi escalate.
- Xác minh poll/throughput trở lại mới kết thúc incident.

Nếu đã restart vài lần nhưng không cải thiện, hãy tạm dừng tự động restart và điều tra sâu hơn. Một consumer stuck liên tục thường phản ánh root cause chưa được xử lý.

## 31. Integration test phát NonResponsiveConsumerEvent

Dùng EmbeddedKafka hoặc Testcontainers khi cần chứng minh monitor và consumer container tương tác thực tế:

1. Tạo topic/group test riêng.
2. Cấu hình pollTimeout, monitorInterval và noPollThreshold.
3. Đợi container nhận assignment.
4. Cho listener chờ trên một latch **có timeout hữu hạn**.
5. Chờ NonResponsiveConsumerEvent qua polling assertion có timeout.
6. Kiểm tra listener ID và timeSinceLastPoll.
7. Release latch trong finally để test không treo.
8. Xác nhận consumer quay lại poll.
9. Gửi record tiếp theo và kiểm tra processing/offset theo policy.
10. Cleanup container và test resources.

Test listener block thể hiện **poll gap do processing**. Nó không chứng minh mọi event là lỗi KafkaConsumer.poll() nội bộ.

## 32. Test idle, pause và stuck riêng biệt

Nên có các test đối chiếu:

**Idle:** để topic không có data, bật ListenerContainerIdleEvent, quan sát consumer vẫn poll. Không kỳ vọng NonResponsiveConsumerEvent chỉ vì traffic rỗng.

**Pause:** gọi container.pause(), đợi actual paused state, xác nhận poll tiếp tục nhưng không dispatch records mới từ paused partitions. Resume và xác nhận records được xử lý.

**Stuck:** chặn listener trong test có timeout, xác nhận poll gap tăng và monitor event được phát. Release block rồi kiểm tra recovery.

**Rebalance:** thay đổi group membership trong test phù hợp, xác nhận listener container xử lý assignment lại và không commit vượt record chưa hoàn thành.

**Transactional:** gây lỗi khi listener đang trong Kafka transaction, xác minh abort/AfterRollbackProcessor và record được giao lại hoặc recover đúng policy.

Các tests dùng assertion có timeout; không dựa duy nhất vào Thread.sleep cố định hoặc container.isRunning().

## 33. Runbook production

**Phát hiện**

1. Ghi lại listener ID, service instance, group ID, topics/partitions.
2. Lấy timeSinceLastPoll, firstSeen và số events lặp.
3. Kiểm tra poll-rate, listener duration, lag và recent deployments.
4. Xác định một consumer hay nhiều groups cùng ảnh hưởng.

**Phân loại**

5. Kiểm tra running/paused state.
6. Kiểm tra group assignment, rebalance, broker/network health.
7. Kiểm tra database locks/pool, HTTP timeouts và JVM GC/CPU.
8. Thu thread dump nếu stall kéo dài.
9. Kiểm tra error handler BackOff và transaction state.
10. Xác định poll stuck, business processing block hay dependency outage.

**Phục hồi**

11. Sửa root cause trước nếu có thể.
12. Đợi tự phục hồi có giới hạn khi sự cố transient.
13. Nếu cần restart, dùng đúng container với cooldown/single-flight.
14. Chờ stop hoàn tất rồi mới start.
15. Không reset offsets hoặc commit thủ công để bỏ record.
16. Nếu stop không hoàn tất, transaction outcome không rõ hoặc external side effect rủi ro, escalate.

**Xác minh**

17. Container có assignment và poll-rate ổn định.
18. Listener success rate tăng, group lag giảm.
19. Kiểm tra DLT/retry backlog và transactional commits.
20. Đối chiếu duplicate side effects theo event ID/inbox.
21. Ghi root cause và action items ngăn tái diễn.

## 34. Khi stop container không hoàn tất

Một thread deadlock hoặc blocking call vô hạn có thể khiến stop container không hoàn tất. Trong trường hợp đó:

- Không start một container mới ngay trên cùng object khi stop chưa xong.
- Không dùng Thread.stop() để ép luồng chết.
- Không xóa committed offsets/Kafka local files.
- Không commitSync() từ arbitrary thread.
- Thu thread dump, GC/CPU/network logs.
- Xác định external side effect có thể đã commit không.
- Escalate sang restart application instance nếu runbook cho phép.
- Với nhiều replicas, tránh kill đồng loạt.
- Sau failover, kiểm tra rebalance, transaction recovery và idempotency.

KafkaConsumer.wakeup() có semantics ngắt poll trong những trường hợp được Kafka API hỗ trợ, nhưng Spring Kafka container sở hữu consumer lifecycle. Không mặc định gọi wakeup trên consumer từ event handler ngoài thread để chữa mọi tình huống.

## 35. Những sai lầm thường gặp

**Coi idle là non-responsive.** Topic rỗng vẫn có thể poll bình thường.

**Restart ngay khi event đầu tiên xuất hiện.** Có thể tạo unnecessary rebalance.

**Chỉ tăng noPollThreshold.** Che warning, không chữa deadlock.

**Tăng max.poll.interval.ms vô hạn.** Không sửa blocking call và có thể trì hoãn failover.

**Dùng Thread.sleep() lâu trong listener để giảm tải.** Làm poll trễ; nên dùng container pause khi phù hợp.

**Gọi KafkaConsumer.commit/seek/pause ở event thread.** Không tôn trọng threading.

**Gọi stop(); start(); liên tiếp.** Có race lifecycle, chưa chờ stop completion.

**Không thu thread dump trước recovery.** Mất bằng chứng nguyên nhân.

**Restart lặp vô hạn.** Có thể gây incident nặng hơn.

**Tự commit offset để bỏ qua record lỗi.** Gây mất dữ liệu nghiệp vụ.

**Nuốt listener exception.** Container có thể ack/commit dù xử lý thất bại.

**Không có idempotency.** Restart/rebalance gây duplicate side effects.

**Không phân biệt transactional listener.** Có thể phá atomic Kafka offsets/output.

**Restart tất cả pods khi chỉ một child consumer stuck.** Gây group churn không cần thiết.

**Liveness probe fail theo consumer lag.** Có thể biến backpressure thành crash loop.

## 36. Checklist trước production

**Phát hiện**

- [ ] Cấu hình monitorInterval/noPollThreshold/pollTimeout được hiểu rõ.
- [ ] NonResponsiveConsumerEvent được lắng nghe bằng handler nhẹ.
- [ ] Dashboard phân biệt idle, paused, slow và stuck.
- [ ] Có poll-rate và listener processing metrics.
- [ ] Alerts có deduplication và severity theo SLA.

**Bảo vệ xử lý**

- [ ] HTTP/DB calls có timeout hữu hạn.
- [ ] max.poll.interval.ms phù hợp listener duration.
- [ ] max.poll.records/batch size được kiểm soát.
- [ ] Async processing ack khi hoàn tất.
- [ ] Consumer side effects idempotent.
- [ ] Không commit offsets phá transaction semantics.

**Recovery**

- [ ] Có runbook thread dump và broker/network diagnosis.
- [ ] Recovery coordinator có single-flight, cooldown và max attempts.
- [ ] Mapping child listener ID tới container đúng.
- [ ] Stop/start chờ lifecycle completion.
- [ ] Có manual review khi stop thất bại.
- [ ] Sau restart xác minh assignment, poll, lag và processing.
- [ ] Có kế hoạch rollback/reconcile transactions và external side effects.

**Testing**

- [ ] Có test NonResponsiveConsumerEvent do listener block.
- [ ] Có test idle khác non-responsive.
- [ ] Có test pause vẫn poll.
- [ ] Có test batch processing dài và max.poll.interval.
- [ ] Có test restart không gây duplicate side effects.
- [ ] Có test broker outage/rebalance và escalation.

## 37. Kết luận

**Hành động khi consumer không phản hồi** phải bắt đầu bằng **chẩn đoán**, không phải restart. Spring Kafka cung cấp NonResponsiveConsumerEvent để cảnh báo poll gap theo monitorInterval, noPollThreshold và pollTimeout. Nhưng cùng một event có thể phát sinh từ listener xử lý quá lâu, Kafka client/network, rebalance, JVM GC hoặc downstream đang kẹt.

Khi có sự cố, cần phân biệt idle/pause với poll không tiến, thu metrics và thread dump, sửa root cause nếu có thể, và chỉ restart container có điều kiện với cooldown, ownership và lifecycle rõ ràng. Sau restart, bắt buộc kiểm tra partition assignment, consumer lag, committed offsets, retry/DLT và side effects ngoài Kafka.

Một consumer chỉ thực sự phục hồi khi **poll loop tiến đều, records được xử lý đúng, offsets không bỏ qua công việc chưa hoàn tất và không tạo duplicate nghiệp vụ không kiểm soát**.
