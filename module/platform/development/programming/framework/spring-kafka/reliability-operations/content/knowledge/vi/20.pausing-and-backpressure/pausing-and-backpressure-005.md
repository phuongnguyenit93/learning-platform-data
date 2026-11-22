# Poll khi container đang pause

Trong **Spring Kafka**, một listener container có thể được **pause** để tạm dừng chuyển các Kafka records mới cho phương thức **@KafkaListener** mà không phải dừng hoàn toàn consumer. Điểm quan trọng: **container vẫn tiếp tục gọi KafkaConsumer.poll() khi đang pause**. Những lần poll này giúp consumer duy trì hoạt động với Kafka broker và consumer group; chúng không có nghĩa là listener tiếp tục nhận records mới từ các partitions đã pause.

Hành vi đó là nền tảng của **backpressure**: khi database, HTTP API, thread pool hoặc bộ nhớ đang chịu quá tải, ứng dụng có thể tạm ngừng lấy việc mới trong lúc vẫn cố gắng giữ quyền sở hữu partitions để phục hồi nhanh sau **resume()**.

Ba điều cần phân biệt ngay từ đầu:

1. **pause() không phải stop()**: container vẫn running và vẫn poll.
2. **pause() không phải acknowledgement hoặc offset commit**: records chưa xử lý không tự nhiên được xác nhận.
3. **pause() không lập tức ngắt mọi listener đang chạy**: các records đã được poll trước đó có thể còn được dispatch hoặc giữ lại tùy cấu hình.

Bài học giải thích vòng poll khi pause, lý do giữ group membership, điểm áp dụng pause/resume, điều khiển theo partition, tương tác với ack/transaction/retry và cách vận hành backpressure an toàn.

## 1. Kafka consumer poll bình thường

Một consumer thuộc group thường hoạt động theo vòng:

~~~mermaid
flowchart TD
    A["Container RUNNING"] --> B["KafkaConsumer.poll()"]
    B --> C{"Có records?"}
    C -->|Có| D["Gọi listener"]
    D --> E["Ack / commit theo cấu hình"]
    E --> B
    C -->|Không| F["Tiếp tục vòng poll"]
    F --> B
~~~

Trong một lần poll, Kafka client không chỉ lấy records. Nó cũng tham gia hoạt động liên quan group coordination, assignment, heartbeat state và nhiều xử lý nội bộ. Kafka client có cơ chế heartbeat ở background phù hợp với group protocol, nhưng application vẫn phải tiếp tục gọi poll theo yêu cầu tiến độ.

Đặc biệt, cấu hình **max.poll.interval.ms** giới hạn thời gian consumer được phép ở giữa những lần gọi poll trong mô hình group management thông thường. Nếu listener bị chặn quá lâu trước khi quay lại poll, consumer có thể mất tư cách hoạt động đúng hạn và group rebalance.

Đó là lý do dùng **Thread.sleep() lâu trong listener** để giảm tải không tương đương với pause container.

## 2. Khi gọi container.pause(), điều gì xảy ra?

Spring Kafka cung cấp **MessageListenerContainer.pause()** để yêu cầu pause toàn bộ partitions đang được container quản lý.

Lệnh pause thường được gọi từ controller, scheduler hoặc một service giám sát downstream. Container ghi nhận yêu cầu; consumer thread sẽ áp dụng việc pause ở thời điểm phù hợp trong vòng xử lý.

~~~mermaid
flowchart TD
    A["Consumer đang poll và xử lý"] --> B["Controller gọi pause()"]
    B --> C["Container ghi nhận pause request"]
    C --> D["Consumer thread áp dụng pause"]
    D --> E["Các partitions đã pause"]
    E --> F["poll() vẫn tiếp tục"]
    F --> G["Không dispatch records mới từ partitions đang pause"]
    G --> F
    H["Controller gọi resume()"] --> I["Consumer thread áp dụng resume"]
    I --> J["Poll và dispatch tiếp tục"]
~~~

Một khi pause đã có hiệu lực, KafkaConsumer.poll() vẫn được gọi để consumer không bị coi là đã ngừng poll. Nếu tất cả assigned partitions đều pause, những lần poll tiếp theo thường không trả records mới từ chúng. Nếu chỉ một số partitions pause, poll vẫn có thể trả records của những partitions còn lại.

Pause request có thể đến trong lúc listener đang xử lý records của poll cũ. Do đó phải phân biệt **yêu cầu pause** và **pause thực tế đã được consumer áp dụng**.

## 3. Vì sao phải poll khi tất cả partitions đều pause?

Kafka consumer group cần các members tiếp tục tham gia group management. Nếu consumer thread hoàn toàn dừng poll vì đang chờ downstream, application có nguy cơ vượt **max.poll.interval.ms**, dẫn tới rebalance và chuyển partitions cho consumer khác.

Một ví dụ không tốt:

~~~text
Downstream quá tải
  -> listener sleep 10 phút
  -> không thể quay lại poll trong thời gian đó
  -> max.poll.interval.ms bị vượt
  -> partitions có thể bị revoke/reassign
~~~

Với Spring Kafka pause:

~~~text
Downstream quá tải
  -> container áp dụng pause
  -> consumer thread tiếp tục poll định kỳ
  -> không lấy thêm records mới từ partitions đã pause
  -> có thể giữ group membership ổn định
  -> resume sau khi downstream phục hồi
~~~

**Pause giảm nguy cơ rebalance do không poll**, nhưng không bảo đảm tuyệt đối consumer không rebalance. Các nguyên nhân như network failure, coordinator restart, member khác rời group, rolling deployment hoặc session timeout vẫn có thể làm assignment thay đổi.

Cũng không được nhầm việc poll tiếp với việc consumer đang xử lý nghiệp vụ. Một consumer có thể poll đều đặn nhưng listener invocation count bằng không trong lúc đã pause.

## 4. KafkaConsumer.pause và Spring container.pause

Kafka client thuần có các API:

~~~java
consumer.pause(partitions);
consumer.resume(partitions);
~~~

Chúng tác động tới fetch của các TopicPartition đang được KafkaConsumer đó assign. Nhưng KafkaConsumer nhìn chung **không thread-safe** để tùy ý gọi từ những threads khác nhau.

Trong Spring Kafka, container sở hữu consumer thread. Vì vậy cách thông thường là:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();
container.resume();
~~~

Ưu điểm của API container:

- Gửi yêu cầu phù hợp với consumer loop do framework quản lý.
- Tránh điều khiển raw KafkaConsumer từ HTTP thread hoặc scheduler.
- Có thể quan sát trạng thái requested/actual.
- Có các pause/resume application events.
- Tương thích hơn với lifecycle của listener, child containers và container concurrency.

Chỉ dùng raw KafkaConsumer.pause() trực tiếp nếu tự viết Kafka consumer loop hoặc ở callback được thiết kế để thao tác trên consumer đúng thread, với hiểu biết rõ về ownership.

## 5. Requested pause khác actual paused

Spring Kafka phân biệt hai giai đoạn:

| Trạng thái | Ý nghĩa |
|---|---|
| **Pause requested** | Application gọi pause(); container đang có yêu cầu tạm dừng |
| **Consumer paused** | Kafka consumer đã được container đặt trạng thái paused thực tế |
| **Resume requested** | Application gọi resume(); container cần hủy pause |
| **Consumer resumed** | Consumer đã áp dụng resume và có thể fetch/dispatch trở lại |

Ví dụ:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();

boolean requested = container.isPauseRequested();
boolean actual = container.isConsumerPaused();
~~~

Ngay sau pause(), kết quả có thể là:

~~~text
isPauseRequested() == true
isConsumerPaused()  == false
~~~

Điều đó không tự chứng minh có lỗi. Container có thể đang xử lý records đã poll hoặc chưa tới điểm áp dụng pause trong consumer thread.

Tương tự, resume() trả về không có nghĩa listener đã nhận record tiếp theo ngay lập tức. Phải chờ container áp dụng resume và Kafka poll có dữ liệu phù hợp.

Với container có concurrency lớn hơn một, trạng thái tổng thể cần được hiểu trong phạm vi các child consumers. Khi cần quan sát từng partition, dùng partition-specific APIs/events của Spring Kafka version hiện hành.

## 6. Điều khiển qua KafkaListenerEndpointRegistry

Một listener có ID ổn định:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-processor"
    )
    public void onOrder(OrderEvent event) {
        service.handle(event);
    }
}
~~~

Service điều khiển:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class OrderConsumerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumerControlService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        findContainer().pause();
    }

    public void resume() {
        findContainer().resume();
    }

    public boolean pauseRequested() {
        return findContainer().isPauseRequested();
    }

    public boolean consumerPaused() {
        return findContainer().isConsumerPaused();
    }

    private MessageListenerContainer findContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener container is not registered"
            );
        }
        return container;
    }
}
~~~

Control service có thể được gọi bởi health manager, một operator API hoặc một backpressure controller. Khi trả HTTP response, có thể báo **PAUSE_REQUESTED** trước, rồi báo **PAUSED** sau khi quan sát actual state. Không trả “đã pause hoàn toàn” ngay khi gọi pause() nếu consumer chưa áp dụng lệnh.

## 7. Pause toàn container và pause từng partition

Spring Kafka có API điều khiển theo TopicPartition trong những phiên bản hỗ trợ:

~~~java
import org.apache.kafka.common.TopicPartition;

MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

TopicPartition partition =
        new TopicPartition("orders.events", 2);

container.pausePartition(partition);

// Sau khi partition này không còn bị backpressure:
container.resumePartition(partition);
~~~

So sánh:

| API | Phạm vi | Trường hợp |
|---|---|---|
| pause() | Toàn bộ partitions của listener container | Database pool quá tải toàn hệ thống |
| resume() | Hủy pause request chung của container | Dependency chung phục hồi |
| pausePartition(tp) | Một TopicPartition | Partition riêng bị throttling |
| resumePartition(tp) | Một TopicPartition | Hot partition đã đủ điều kiện |
| stop() | Dừng lifecycle container | Bảo trì, shutdown hoặc thay cấu hình |

Nếu pausePartition(partition 2), **poll vẫn có thể trả records từ partition 0, 1 hoặc partitions khác chưa pause**. Đây là khác biệt quan trọng với pause toàn container.

Partition-level pause và container-level pause có thể cùng tồn tại. Resume một partition không phải lúc nào cũng thắng một yêu cầu global pause đang active. Phải kiểm soát owner của các lệnh để tránh resume sớm.

## 8. Poll khi chỉ một phần partitions bị pause

Ví dụ một consumer được assign partitions P0, P1 và P2:

~~~text
P0: RUNNING
P1: PAUSED
P2: RUNNING
~~~

KafkaConsumer.poll() vẫn được gọi. Theo hành vi pause của Kafka client, P1 không tiếp tục cung cấp records mới trong lúc paused; P0 và P2 vẫn có thể cung cấp records cho listener.

~~~mermaid
flowchart LR
    A["poll()"] --> P0["P0 active"]
    A --> P1["P1 paused"]
    A --> P2["P2 active"]
    P0 --> L["@KafkaListener"]
    P2 --> L
    P1 --> W["Chờ resume"]
~~~

Nếu record từ P1 đã được trả trong poll trước khi partition pause được áp dụng, nó vẫn có thể nằm trong vùng in-flight và được xử lý/giữ lại theo cấu hình.

Không suy ra một partition paused từ việc record rate giảm. Quan sát actual partition paused state/event hoặc diagnostic log của container.

## 9. Records đã poll trước khi pause

Giả sử một poll trả bốn records:

~~~text
orders.events-0, offsets 100, 101, 102, 103
Listener đang xử lý offset 100
Controller gọi pause()
~~~

Kafka client đã trả cả bốn records cho container. Pause được yêu cầu sau đó không làm “thu hồi” các records này khỏi bộ nhớ.

Tùy Spring Kafka version và pause policy:

- Container có thể xử lý hết các records của poll hiện tại rồi mới áp dụng pause.
- Hoặc với **pauseImmediate** được hỗ trợ, container có thể pause sau record đang xử lý và giữ các records còn lại để dispatch khi resume.

Do vậy, ngay sau container.pause(), listener **có thể vẫn được gọi** cho records lấy từ poll trước. Không nên cảnh báo lỗi chỉ vì listener invocation count tăng một vài lần ngay sau request pause.

Để xác nhận actual pause, chờ trạng thái consumer paused hoặc event phản ánh container đã áp dụng pause.

## 10. pauseImmediate

Trong các phiên bản hỗ trợ **ContainerProperties.setPauseImmediate(true)**, có thể thay đổi điểm áp dụng pause để giảm số records tiếp tục được xử lý sau request.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setPauseImmediate(true);

    return factory;
}
~~~

Khi dùng factory này, @KafkaListener cần khai báo containerFactory="ordersFactory" hoặc ứng dụng phải dùng nó làm factory mặc định phù hợp.

So sánh:

| Chế độ | Đặc điểm |
|---|---|
| Pause mặc định | Thường chờ xử lý xong các records còn lại từ poll trước khi pause |
| pauseImmediate=true | Có thể pause sau record hiện tại, giữ records còn lại của poll để xử lý sau resume |

**pauseImmediate không phải interrupt/cancel listener đang chạy**. Nếu listener kẹt trong HTTP call quá lâu, container chưa thể quay về poll loop để áp dụng pause và vẫn có nguy cơ vượt max.poll.interval.ms.

Cần đối chiếu API của Spring Kafka version đang triển khai. Ở các phiên bản cũ, pauseImmediate có thể chưa tồn tại.

## 11. pollTimeoutWhilePaused

Trong các phiên bản Spring Kafka hỗ trợ, **ContainerProperties.setPollTimeoutWhilePaused(long)** điều chỉnh timeout cho poll khi consumer đang pause.

~~~java
factory.getContainerProperties()
        .setPollTimeoutWhilePaused(100L);
~~~

Giá trị minh họa tính bằng mili giây. Một số phiên bản dùng giá trị mặc định khoảng 100 ms khi paused.

Các cấu hình khác nhau:

| Cấu hình | Vai trò |
|---|---|
| pollTimeout | Timeout của poll thông thường |
| pollTimeoutWhilePaused | Timeout của poll khi paused |
| max.poll.interval.ms | Giới hạn thời gian giữa các lần poll |
| heartbeat.interval.ms | Nhịp heartbeat theo group protocol/client |
| session.timeout.ms | Giới hạn session liveness do broker áp dụng |

Timeout poll không đồng nhất với thời gian giữa các poll hoặc thời gian consumer đang pause. Đặt pollTimeoutWhilePaused quá thấp có thể làm poll loop quay quá thường xuyên; quá lớn có thể làm chậm phản hồi resume và ảnh hưởng cơ chế poll theo phiên bản. Nên đo poll-rate, CPU và thời gian áp dụng pause/resume.

Đừng tạo backpressure bằng cách Thread.sleep(pollTimeoutWhilePaused) trong listener. Lúc sleep, consumer thread không thực hiện poll.

## 12. max.poll.interval.ms: pause giúp gì và không giúp gì?

Giả sử:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 200
~~~

max.poll.interval.ms bằng năm phút. Nếu listener mất hơn năm phút để xử lý một poll, nó có thể không quay lại poll đúng hạn dù controller đã gửi pause request từ thread khác.

Pause hiệu quả nếu:

- Listener hoàn tất công việc hiện tại.
- Container consumer thread tiếp tục chạy.
- Pause được áp dụng trong vòng poll tiếp theo.
- Các lần poll sau đó vẫn được thực hiện định kỳ.

Pause không giải quyết trực tiếp:

- Deadlock trong listener.
- HTTP client không có timeout.
- Blocking Future.get() vô hạn.
- Batch quá lớn khiến xử lý trước lần poll kế tiếp vượt giới hạn.
- Consumer thread bị starvation nghiêm trọng.

Biện pháp bổ sung gồm giới hạn max.poll.records, giảm thời gian xử lý mỗi record, đặt timeouts, circuit breakers, kiểm soát in-flight jobs và dùng acknowledgement đúng semantics nếu có async processing.

## 13. Poll-rate vẫn tăng khi listener không nhận record

Trong trạng thái toàn bộ partitions đã pause:

~~~text
Container RUNNING: true
Pause requested: true
Consumer paused: true
Poll calls: tiếp tục
New data delivery: không có từ paused partitions
Listener processing: không gọi thêm sau khi drained/held in-flight
Consumer lag: có thể tăng khi producers tiếp tục gửi
~~~

Một dashboard chỉ xem **poll-rate** có thể thấy consumer “vẫn đang hoạt động” nhưng không hiểu vì sao **records-consumed-rate** giảm về không. Điều này là hành vi dự kiến của pause.

Ngược lại, **records-consumed-rate=0** không chứng minh consumer paused; topic có thể không có records hoặc container chưa được assign partitions.

Muốn chẩn đoán chính xác, kết hợp poll metrics, pause requested/actual state, assigned partitions, consumer lag và listener processing metrics.

## 14. Pause có commit offset không?

Không. **Pause không phải Kafka offset acknowledgement**.

Offset commit phụ thuộc container AckMode, tình trạng listener đã xử lý thành công hay chưa, manual ack và transaction manager nếu có.

Ví dụ:

~~~text
Poll nhận offsets 100, 101, 102
Listener đã xử lý thành công 100
Controller gọi pause()
~~~

Khi đó:

- Offset 100 có thể được ack/commit theo AckMode.
- Offsets 101, 102 có thể được xử lý trước pause hoặc giữ lại theo pauseImmediate.
- Nếu 101 và 102 chưa xử lý, chúng không được tự xem là đã hoàn tất chỉ vì container paused.
- Nếu listener manual ack, những acknowledgement còn pending phải theo policy của container.
- Nếu có Kafka transaction, pause không gọi commitTransaction hoặc sendOffsetsToTransaction thay listener.

Không gọi Consumer.commitSync() từ thread tùy ý để “đẩy offset” khi pause. Nó có thể vi phạm threading và làm checkpoint vượt records chưa xử lý.

## 15. Manual acknowledgement và async processing

Một anti-pattern:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.handle(event));
    // Method đã return nhưng async task chưa hoàn tất.
}
~~~

Nếu container coi return bình thường là xử lý thành công, offset có thể được ack/commit trước khi task thực sự thành công. Khi task lỗi, Kafka không nhất thiết giao lại event.

Pause không tự ngăn vấn đề này.

Khi dùng async processing:

1. Chỉ ack record sau khi side effect hoàn tất bền vững.
2. Dùng manual acknowledgment hoặc async listener support theo version.
3. Bảo đảm ack/offset ordering theo partition.
4. Theo dõi in-flight count và bounded executor queue.
5. Pause khi in-flight vượt high watermark.
6. Resume khi in-flight giảm dưới low watermark.
7. Khi shutdown/rebalance, xử lý pending tasks và offsets an toàn.

Spring Kafka có tính năng **asyncAcks** trong một số phiên bản: nó hỗ trợ acknowledgements ngoài thứ tự trong một poll và có cơ chế tạm pause nhận thêm dữ liệu khi cần. Không trộn thủ công nhiều lớp pause với asyncAcks nếu chưa hiểu rõ ownership của pause và khi nào container có thể resume.

## 16. Backpressure bằng hysteresis

Hệ thống có thể pause khi backlog cao và resume khi backlog thấp:

~~~text
executor queue capacity = 1000
PAUSE_AT  = 800
RESUME_AT = 300
~~~

Đây là hysteresis: tránh queue dao động quanh cùng một threshold và khiến container pause/resume liên tục.

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> PAUSE_REQUESTED: backlog >= 800
    PAUSE_REQUESTED --> PAUSED: pause applied
    PAUSED --> PAUSED: poll continues
    PAUSED --> RESUME_REQUESTED: backlog <= 300
    RESUME_REQUESTED --> RUNNING: resume applied
~~~

Chọn threshold dựa vào executor queue, memory, database pool và khả năng downstream. Ví dụ 800/300 chỉ có tính minh họa, không phải giá trị khuyến nghị cho mọi workload.

## 17. Ví dụ backpressure controller

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class BackpressureController {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;
    private final AtomicBoolean requested = new AtomicBoolean();

    public BackpressureController(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void updateQueueDepth(int pendingTasks) {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        if (pendingTasks >= HIGH_WATERMARK
                && requested.compareAndSet(false, true)) {
            container.pause();
        } else if (pendingTasks <= LOW_WATERMARK
                && requested.compareAndSet(true, false)) {
            container.resume();
        }
    }
}
~~~

Code trên chỉ minh họa phần **điều khiển pause/resume**; nó không thay thế cơ chế acknowledgement của asynchronous business processing.

AtomicBoolean tránh phát lặp request cùng một lý do. Nếu nhiều nguyên nhân pause có thể cùng tồn tại, boolean này **không đủ**: cần một bộ quản lý pause reasons hoặc state machine chung.

## 18. Nhiều nguyên nhân pause cùng lúc

Ví dụ:

~~~text
Pause reason A: DATABASE_POOL_EXHAUSTED
Pause reason B: PAYMENT_API_RATE_LIMIT
~~~

Khi database pool phục hồi nhưng payment API vẫn rate limit, container phải tiếp tục paused. Nếu controller A gọi resume() mà không kiểm tra B, consumer sẽ nhận thêm records và tạo lỗi.

Một flow-control service nên quản lý tập lý do:

~~~text
pauseReasons = {DATABASE_POOL, PAYMENT_API}
DATABASE_POOL resolved
pauseReasons = {PAYMENT_API}
=> remain paused

PAYMENT_API resolved
pauseReasons = {}
=> request resume
~~~

Với multiple partitions, lý do pause toàn cục và lý do pause riêng từng partition nên được quản lý riêng. Khi operator dùng pause thủ công, health manager không nên tự resume khi dependency phục hồi mà bỏ qua yêu cầu operator.

Nếu hệ thống cần survive restart, xác định trạng thái pause nào chỉ là điều kiện runtime và trạng thái pause nào là maintenance intent cần được lưu bền vững.

## 19. Pause/resume application events

Spring Kafka có các events quan sát quá trình pause/resume trong những phiên bản hỗ trợ:

- **ConsumerPausedEvent**
- **ConsumerResumedEvent**
- **ConsumerPartitionPausedEvent**
- **ConsumerPartitionResumedEvent**

Ví dụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPauseEvents {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed partitions={}",
                event.getPartitions()
        );
    }
}
~~~

Biến log cần được khai báo bởi class (ví dụ SLF4J). Event có thể được phát trong bối cảnh consumer thread khi event multicaster đồng bộ. Không gọi HTTP, database hoặc thao tác blocking nặng trong event callback.

Event cho thấy actual transition; nguyên nhân pause có thể do application controller quản lý và cần gắn vào structured logs/metrics riêng.

## 20. Pause và rebalance

Khi pause, consumer có thể giữ assignment ổn định vì vẫn poll; nhưng rebalance vẫn có thể xảy ra do nguyên nhân khác.

Ví dụ:

- Một replica khác join group.
- Rolling deployment khiến một member rời group.
- Coordinator hoặc network gián đoạn.
- Session timeout.
- Thay đổi partition metadata/assignment.

Với pause theo partition, assignment sau rebalance có thể khác trước. Cần xác nhận trạng thái pause của từng TopicPartition trong assignment mới theo API/version đang dùng.

Quy trình vận hành:

1. Theo dõi partition assigned/revoked events hoặc container assignment.
2. Kiểm tra pause reasons vẫn còn hiệu lực.
3. Xác nhận actual pause với assigned partitions mới.
4. Đảm bảo in-flight tasks của partitions bị revoke được xử lý/huỷ đúng policy.
5. Không tự resume chỉ vì rebalance đã hoàn tất nếu downstream chưa phục hồi.

Trong consumer group lớn, một partition có thể thuộc child container khác sau rebalance; không nên dựa vào tham chiếu KafkaConsumer cũ để quản lý pause.

## 21. Pause so với stop, idle, seek và retry

| Cơ chế | Có tiếp tục poll? | Ảnh hưởng chính |
|---|---|---|
| **pause()** | Có, khi container thread hoạt động | Ngừng fetch/dispatch records mới từ paused partitions |
| **resume()** | Có | Cho phép xử lý trở lại |
| **stop()** | Không còn poll sau khi dừng xong | Dừng container, consumer rời lifecycle hiện tại |
| **Idle** | Có | Poll nhưng topic/assignment không có records |
| **seek()** | Có nếu container chạy | Thay đổi vị trí đọc partition |
| **DefaultErrorHandler retry** | Theo cơ chế retry/backoff của container | Giao lại failed record, không đồng nghĩa global pause |
| **@RetryableTopic** | Retry containers riêng | Chuyển record lỗi sang retry topics |

Pause thường tốt cho backpressure tạm thời. Stop phù hợp với shutdown hoặc bảo trì. Seek dùng cho replay/offset recovery có kiểm soát; pause không tự tua lại offset.

Nếu sử dụng non-blocking retry topics, pause main listener không mặc nhiên pause toàn bộ retry-topic listener containers và DLT consumers. Cần xác định những container nào cùng dùng downstream đang quá tải.

## 22. Tác động tới consumer lag

Khi consumer đang pause, producers vẫn có thể tiếp tục ghi Kafka. Committed offset không tiến qua records chưa xử lý, nên **consumer lag tăng**.

Điều này là hệ quả được chấp nhận khi bảo vệ downstream, nhưng cần giới hạn theo SLA:

- Pause ngắn vài giây: backlog có thể được drain nhanh.
- Pause vài phút: lag/oldest record age tăng, cần monitor.
- Pause hàng giờ: có thể ảnh hưởng retention và SLA nghiệp vụ.

Khi resume, một consumer có thể drain backlog rất nhanh rồi lại làm quá tải downstream. Cần rate limiting, bounded processing, high/low watermarks và điều chỉnh max.poll.records/concurrency dựa trên sức chịu tải.

Không dùng pause để che một lỗi permanent mà không có owner hoặc alert. Pause giúp mua thời gian, không làm biến mất số records cần xử lý.

## 23. Pause trong transactional listener

Với Kafka-aware transactional listener container, transaction boundary do container và KafkaTransactionManager quản lý. Pause không tự:

- Commit hoặc abort Kafka transaction.
- Commit consumer offsets trong transaction.
- Rollback database transaction.
- Xóa output record đã gửi.
- Thay thế AfterRollbackProcessor.

Nếu listener đang xử lý trong Kafka transaction và controller yêu cầu pause, transaction hiện tại vẫn cần kết thúc theo normal/exception path trước khi container có thể áp dụng pause ở điểm phù hợp.

Khi listener ném exception, transaction abort và AfterRollbackProcessor có thể điều phối seek/redelivery/recovery. Pause không sửa một failed transaction và không được dùng thay exception handling.

Với database transaction bên trong listener, giữ transaction ngắn để consumer thread nhanh chóng trở lại poll. Một transaction DB bị deadlock hoặc lock wait dài sẽ không được giải quyết bằng cách pause khi listener đã bị kẹt.

## 24. Khi nào pause không đủ để chống quá tải?

Một tình huống:

~~~text
poll đã trả 500 records
listener đẩy 500 jobs vào executor
queue đã đầy
controller gọi pause
~~~

Pause ngừng nhận records mới sau khi áp dụng, nhưng **không hủy 500 jobs đã được dispatch**.

Hệ thống vẫn có thể OOM hoặc làm quá tải database nếu:

- Queue không giới hạn.
- Có nhiều Kafka listeners khác cũng gửi việc vào cùng executor.
- Listener trả về trước khi công việc bất đồng bộ hoàn tất rồi ack quá sớm.
- Các jobs không có timeout/circuit breaker.
- Downstream không có capacity cap.

Biện pháp bổ sung gồm bounded queue, limiter in-flight, idempotency, manual/async ack đúng framework, retry/backoff và đo transaction duration. Với dữ liệu cần ordering, phải đặc biệt cẩn thận không commit vượt offset chưa xử lý.

## 25. Monitoring khi container pause

Một dashboard hữu ích cần kết hợp:

| Metric | Ý nghĩa |
|---|---|
| pause_requested | Application đã yêu cầu pause |
| consumer_paused | Consumer đã pause thực tế |
| pause_duration | Thời gian đã ngừng nhận việc |
| pause_reason | Lý do backpressure/maintenance |
| poll_rate | Vòng poll còn hoạt động |
| records_consumed_rate | Lượng records thực nhận |
| consumer_lag | Backlog trong Kafka |
| oldest_unprocessed_age | Độ trễ của record cũ nhất |
| listener_processing_duration | Có listener đang block không |
| executor_queue_depth | Backlog trong ứng dụng |
| database_pool_waiters | Thời gian chờ DB connection |
| rebalance_count | Consumer group có biến động |

Các tên metric pause_* ở đây là **custom metric gợi ý**, không phải tên metric mặc định bắt buộc của Spring Kafka. Hãy phân biệt số liệu application, Spring container và Kafka client JMX/Micrometer.

Chỉ dùng tags có cardinality hữu hạn như service, listener ID, topic, environment và pause reason. Không đưa event ID, offset hoặc customer ID vào metric tags.

## 26. Log hữu ích để chẩn đoán

Ví dụ:

~~~text
event=consumer_pause_requested
service=orders-service
listener_id=ordersListener
reason=DATABASE_POOL_SATURATED
queue_depth=850
pause_requested=true
consumer_paused=false
~~~

Sau khi actual pause:

~~~text
event=consumer_paused
listener_id=ordersListener
assigned_partitions=6
polling_continues=true
consumer_paused=true
~~~

Sau resume:

~~~text
event=consumer_resumed
listener_id=ordersListener
reason=ALL_PAUSE_REASONS_CLEARED
paused_duration_ms=12000
~~~

Log là format minh họa. Khi thấy poll-rate tăng nhưng listener throughput bằng không, kiểm tra pause state và reason trước khi kết luận consumer gặp lỗi. Khi thấy lag tăng, xác định pause là chủ động hay container đang stalled do network/authorization/thread blocking.

## 27. Integration test: container vẫn poll trong pause

Để kiểm tra semantics thực, dùng Kafka broker từ EmbeddedKafka hoặc Testcontainers và một consumer group test riêng.

Quy trình:

1. Tạo topic và khởi động listener container.
2. Đợi listener được assign partition.
3. Gửi một record hợp lệ và xác nhận listener xử lý.
4. Gọi container.pause().
5. Đợi isConsumerPaused() hoặc ConsumerPausedEvent.
6. Gửi thêm một record vào partition đã pause.
7. Trong khoảng pause, xác nhận listener chưa xử lý record mới (sau khi loại trừ records in-flight).
8. Quan sát poll metrics hoặc instrumentation cho thấy poll loop vẫn hoạt động.
9. Xác nhận group membership không bị mất chỉ vì đang pause trong test ổn định.
10. Gọi container.resume().
11. Đợi actual resumed state.
12. Xác nhận record gửi khi pause được xử lý sau resume.
13. Xác minh acknowledgement/offset commit theo policy.
14. Cleanup consumer group/topic fixtures.

Không chỉ kiểm tra container.isRunning(): running chưa chứng minh poll rate. Nếu mục tiêu là chứng minh poll thật sự tiếp tục, cần quan sát Kafka client poll metrics hoặc instrumentation phù hợp.

Test nên dùng polling assertions có timeout, không dựa vào Thread.sleep cố định làm điều kiện thành công.

## 28. Integration test: pauseImmediate và records đã poll

Một test riêng cần điều phối lúc pause request xuất hiện giữa một poll chứa nhiều records:

~~~text
Poll trả offsets 100, 101, 102, 103
Listener bắt đầu offset 100
Test yêu cầu pause trong lúc offset 100 đang xử lý
~~~

Với pause mặc định, container có thể xử lý hết records của poll trước khi actual pause. Với pauseImmediate trên phiên bản hỗ trợ, pause có thể có hiệu lực sau record hiện tại và giữ các records còn lại tới lúc resume.

Các assertions:

- Listener không bị interrupt không kiểm soát.
- Actual pause state xuất hiện theo policy.
- Records không bị mất.
- Không ack vượt records chưa hoàn thành.
- Sau resume, các records còn lại được xử lý theo semantics phù hợp.
- Không tạo side effect trùng không chủ đích.

Khi concurrency lớn hơn một, cần theo dõi từng child container và partition tương ứng; đừng suy luận chỉ từ số invocation tổng.

## 29. Integration test: pausePartition

Với topic có ít nhất hai partitions:

1. Đợi container được assign P0 và P1 phù hợp.
2. pausePartition(P0).
3. Đợi partition P0 actual paused.
4. Gửi record A vào P0 và record B vào P1.
5. Xác minh B vẫn được xử lý.
6. Xác minh A chưa được xử lý trong khi P0 paused.
7. resumePartition(P0).
8. Xác minh A được xử lý.
9. Kiểm tra offset và ordering theo partition.

Mục tiêu chứng minh **poll vẫn hoạt động cho các partitions chưa pause**, không phải chỉ quan sát container-level paused state.

## 30. Runbook pause/resume production

Khi downstream quá tải và cần tạm dừng Kafka listener:

1. Xác định service, listener ID, consumer group và assigned partitions.
2. Kiểm tra consumer lag, oldest record age, processing duration và in-flight count.
3. Xác định cần global pause hay partition-specific pause.
4. Xác nhận đây là backpressure tạm thời, không phải shutdown.
5. Ghi pause reason và owner.
6. Gọi container.pause() hoặc pausePartition(tp) qua registry.
7. Chờ requested/actual paused state phù hợp.
8. Quan sát records đã fetch trong poll cũ còn đang xử lý không.
9. Xác nhận poll loop tiếp tục và không phát sinh rebalance bất thường.
10. Theo dõi lag, pause duration, downstream health và recovery metrics.
11. Khi dependency phục hồi, xóa đúng pause reason.
12. Chỉ request resume nếu không còn reason khác.
13. Chờ actual resumed state và kiểm tra listener invocation/throughput.
14. Theo dõi tốc độ drain lag, tránh retry storm và tái quá tải.
15. Ghi thời gian pause, nguyên nhân và hành động để điều chỉnh threshold.

Nếu container không running hoặc không có assigned partitions, pause/resume có thể không tạo ra hiệu quả như mong đợi. Kiểm tra lifecycle và errors trước khi gửi lệnh lặp.

## 31. Những hiểu nhầm thường gặp

**Pause sẽ ngừng poll.** Không đúng: Spring Kafka container vẫn poll để giữ hoạt động với consumer group.

**Pause là stop.** Không đúng: stop kết thúc lifecycle; pause vẫn giữ container running.

**Gọi pause() xong không còn listener callback.** Records của poll trước có thể tiếp tục xử lý, tùy pauseImmediate.

**pauseImmediate sẽ ngắt listener hiện tại.** Không: nó chỉ thay đổi điểm pause sau record hiện tại.

**Poll-rate vẫn cao thì pause thất bại.** Poll tiếp tục là hành vi mong đợi; phải kiểm tra actual paused state.

**Lag tăng là dấu hiệu pause không hiệu quả.** Lag tăng có thể là hệ quả bình thường khi tạm ngừng consume.

**Pause sẽ commit offsets.** Pause không ack/commit hộ listener.

**Dùng Thread.sleep lâu thay pause.** Có thể vượt max.poll.interval.ms và gây rebalance.

**KafkaConsumer.pause có thể gọi từ bất kỳ thread nào.** Không: KafkaConsumer có các ràng buộc threading; dùng container API.

**Pause một partition đồng nghĩa pause cả consumer.** Những partitions khác vẫn có thể fetch/deliver records.

**Pause main listener tự động pause retry-topic consumers.** Mỗi listener container có lifecycle riêng.

**Resume luôn có callback ngay lập tức.** Có thể không có records, còn partition pause hoặc assignment thay đổi.

**Pause bảo đảm không bao giờ rebalance.** Vẫn có thể rebalance do group/network/lifecycle khác.

**Pause giải quyết toàn bộ async overload.** In-flight tasks đã dispatch vẫn tồn tại; cần bounded capacity và ack đúng.

## 32. Checklist triển khai

**Container lifecycle**

- [ ] Listener ID ổn định và có registry để điều khiển.
- [ ] Phân biệt pause requested và actual paused.
- [ ] Có cách quan sát pause/resume events.
- [ ] Biết phiên bản hỗ trợ pauseImmediate và pollTimeoutWhilePaused.
- [ ] Phân biệt pause global và pause từng TopicPartition.

**Poll và group management**

- [ ] max.poll.interval.ms phù hợp thời gian listener processing.
- [ ] Không sleep/block consumer thread vô hạn.
- [ ] Biết poll tiếp tục khi paused và có metric để quan sát.
- [ ] Rebalance vẫn được xử lý đúng.
- [ ] Không dùng poll-rate đơn lẻ làm bằng chứng xử lý dữ liệu.

**Backpressure và offset**

- [ ] Có high/low thresholds và tránh flapping.
- [ ] Có bounded queues và giới hạn in-flight.
- [ ] Không ack trước khi async work hoàn tất.
- [ ] Không commit vượt offset chưa xử lý.
- [ ] Pause reasons được quản lý tập trung.
- [ ] Có logic khôi phục sau resume/restart.

**Vận hành**

- [ ] Dashboard có pause duration, reason, consumer lag và throughput.
- [ ] Có alert cho pause kéo dài hoặc SLA record age bị vượt.
- [ ] Có integration test global pause, partition pause, pauseImmediate.
- [ ] Có test resume và xử lý records gửi trong lúc pause.
- [ ] Có test listener blocking để phân biệt pause với max.poll.interval expiry.

## 33. Kết luận

**Poll khi container đang pause** là cơ chế để Spring Kafka ngừng nhận thêm việc từ Kafka partitions một cách có kiểm soát trong khi **vòng KafkaConsumer.poll() vẫn tiếp diễn**. Vì vậy consumer có thể thường xuyên duy trì group membership và tiếp tục xử lý nhanh sau resume, thay vì gây rebalance chỉ vì ứng dụng tạm dừng nhận dữ liệu.

Để dùng đúng, hãy phân biệt **pause request** với **actual paused state**, hiểu rằng records đã nằm trong poll trước có thể còn in-flight, và rằng **pauseImmediate** không ngắt listener đang chạy. Pause không tự ack, commit offset, rollback transaction hay làm biến mất consumer lag. Nó cũng không thay thế việc thiết kế bounded queues, idempotency, timeout và retry.

Trong production, hãy điều khiển pause/resume qua Spring Kafka container, quan sát poll-rate cùng trạng thái pause và listener throughput, dùng hysteresis cùng pause reasons để tránh resume sớm, và kiểm thử actual behavior với Kafka broker. Nhờ đó hệ thống có thể thực hiện backpressure **mà không biến việc tạm ngừng nhận records thành việc dừng cả consumer group**.
