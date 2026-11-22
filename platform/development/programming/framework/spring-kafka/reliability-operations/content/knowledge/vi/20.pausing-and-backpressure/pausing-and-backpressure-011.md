# Container pause event

## 1. Container pause event là gì?

Trong Spring Kafka, một listener container sở hữu vòng `poll()` của Kafka consumer và gọi phương thức `@KafkaListener` khi có record. Khi ứng dụng cần tạm ngừng nhận thêm công việc, ví dụ database quá tải hoặc hàng đợi xử lý đã gần đầy, ứng dụng có thể yêu cầu **pause listener container** thay vì dừng hẳn consumer.

Sau khi yêu cầu pause được container áp dụng thực tế lên các partition được gán, Spring Kafka phát một **`ConsumerPausedEvent`**. Khi container được resume và việc resume thực sự có hiệu lực, nó phát **`ConsumerResumedEvent`**. Đây là các Spring application events phản ánh trạng thái của listener container; chúng không phải bản tin được gửi vào một Kafka topic.

Ý nghĩa cần nhớ:

- `container.pause()`: **yêu cầu** dừng fetch/delivery thêm dữ liệu cho các partition liên quan.
- `ConsumerPausedEvent`: thông báo container **đã áp dụng** pause lên những partition trong event.
- `container.resume()`: yêu cầu tiếp tục xử lý.
- `ConsumerResumedEvent`: thông báo container đã thực hiện resume.
- Pause không giống stop: container vẫn tồn tại, vẫn giữ quyền tham gia consumer group và thông thường vẫn gọi `poll()` ở trạng thái paused để duy trì group membership.

Container pause events rất hữu ích trong vận hành reliability vì chúng cho phép phân biệt một thao tác điều khiển đã được **yêu cầu** với trạng thái đã **thực sự có hiệu lực**. Nếu chỉ log sau `pause()` rồi nói consumer đã ngừng nhận record hoàn toàn, log có thể sai trong khoảng chuyển tiếp.

## 2. Bối cảnh: backpressure trong consumer

**Backpressure** là việc chủ động giảm hoặc tạm ngừng tốc độ nhận công việc khi downstream chưa xử lý kịp. Với Spring Kafka, downstream có thể là:

- Database connection pool cạn.
- HTTP service chậm hoặc trả 429/503.
- In-memory queue của business worker gần đầy.
- Hệ thống ghi file/object storage đang bị nghẽn.
- CPU/heap của ứng dụng quá cao.
- Công việc nội bộ cần tạm ngừng trong một đợt bảo trì có kiểm soát.

Ví dụ:

~~~text
Kafka topic "orders"                   Spring application
  P0, P1, P2            poll()                  |
     | ---------------------------> @KafkaListener
     |                                    |
     |                                    v
     |                             Database / HTTP API
     |                                    |
     |                             Quá tải tạm thời
     |                                    |
     |                         Backpressure controller
     |                                    |
     |                         container.pause()
     |                                    |
     |                   ConsumerPausedEvent được phát
     |                                    |
     |                Tạm dừng nhận thêm từ partitions
     |                                    |
     |                          Downstream hồi phục
     |                                    |
     |                         container.resume()
     |                                    |
     |                  ConsumerResumedEvent được phát
     |                                    |
     |                          Tiếp tục xử lý
~~~

Một pause có chủ đích giúp ngừng kéo thêm dữ liệu về listener trong thời gian hệ thống giảm tải. Nó **không** làm giảm tốc độ producer đang ghi topic; backlog thường được giữ ở Kafka và consumer lag có thể tăng.

Nếu pause kéo dài quá lâu, topic retention có thể xóa dữ liệu chưa đọc, hoặc độ trễ xử lý vượt SLA. Vì vậy pause nên là biện pháp điều tiết có điều kiện và có kế hoạch resume, không phải cách che một downstream hỏng vô thời hạn.

## 3. Phân biệt pause request và pause event

Một lỗi vận hành thường gặp là coi lệnh `pause()` đồng nghĩa consumer đã dừng ngay tại thời điểm gọi.

Trong Spring Kafka, container có thể nhận lệnh pause từ thread khác với consumer thread. Lệnh này đánh dấu yêu cầu; container áp dụng việc pause ở điểm an toàn của vòng xử lý, thông thường trước một lần `poll()` tiếp theo.

~~~mermaid
sequenceDiagram
    participant O as Operator / controller
    participant C as Listener container
    participant P as Consumer thread
    participant E as Spring event listener

    O->>C: pause()
    Note over C: pause requested = true
    C-->>O: Trả về từ pause()
    P->>P: Hoàn tất phần cần xử lý của lần poll hiện tại
    P->>P: KafkaConsumer.pause(assigned partitions)
    P->>E: Publish ConsumerPausedEvent
    Note over C: consumer actually paused = true
    P->>P: Tiếp tục poll khi paused để giữ membership
    O->>C: resume()
    P->>P: KafkaConsumer.resume(partitions)
    P->>E: Publish ConsumerResumedEvent
    Note over C: consumer paused = false
~~~

Sơ đồ là luồng khái quát; thời điểm xử lý record còn phụ thuộc `pauseImmediate`, listener type và phiên bản Spring Kafka.

### 3.1. isPauseRequested()

`isPauseRequested()` phản ánh có yêu cầu pause ở container hay không. Nó có thể thành true trước khi consumer thread áp dụng lệnh pause.

### 3.2. isConsumerPaused()

`isConsumerPaused()` cho biết container/consumer đã ở trạng thái paused theo cơ chế container. Với concurrent container, ý nghĩa tổng hợp còn phụ thuộc trạng thái các child containers; không nên chỉ nhìn một boolean nếu cần biết chính xác partition nào đã pause.

### 3.3. ConsumerPausedEvent

Event cho biết thao tác pause đã được thực hiện. Khi nhận event, có thể ghi log và cập nhật trạng thái quan sát. Tên topic-partition trong event giúp định vị phạm vi pause tại thời điểm đó.

### 3.4. ConsumerResumedEvent

Event cho biết container đã resume các partition tương ứng. Không suy ra ngay rằng backlog đã hết hoặc listener đã xử lý xong record; resume chỉ mở lại luồng nhận/dispatch theo lịch poll.

| Tín hiệu | Nó chứng minh điều gì? | Nó **không** chứng minh điều gì? |
|---|---|---|
| Gọi `pause()` xong | Đã gửi yêu cầu pause tới container | Consumer đã pause hết tất cả partition |
| `isPauseRequested() == true` | Container có pending pause request | Không còn record đang xử lý |
| `ConsumerPausedEvent` | Pause đã được áp dụng cho partition được báo | Downstream đã hồi phục hay queue đã trống |
| `isConsumerPaused() == true` | Consumer/container đã ở trạng thái pause thực tế | Kafka producer cũng dừng ghi |
| `ConsumerResumedEvent` | Resume đã được áp dụng | Record tiếp theo đã xử lý thành công |
| `container.stop()` | Yêu cầu dừng lifecycle container | Tương đương pause có duy trì membership |

## 4. Spring Kafka phát những event nào?

### 4.1. ConsumerPausedEvent

`ConsumerPausedEvent` được Spring Kafka publish khi container thực sự pause các partition. Event mang thông tin về các partition đã pause và liên hệ tới container là nguồn của sự kiện.

Có thể dùng để:

- Ghi log thời điểm pause hiệu lực.
- Cập nhật trạng thái hiển thị trên dashboard.
- Đếm số lần pause do backpressure.
- Đo khoảng thời gian từ pause đến resume.
- Phân biệt requested state với actual state.

### 4.2. ConsumerResumedEvent

`ConsumerResumedEvent` được publish khi các partition đã pause được resume. Event thường xuất hiện sau một lời gọi `resume()` hoặc sau thao tác tương đương của container.

Có thể dùng để:

- Đánh dấu thời điểm consumer tiếp tục đọc.
- Kết thúc khoảng đo pause duration.
- Xác nhận một quy trình giảm tải đã kết thúc.
- Giám sát tình huống resume request không được thực hiện.

### 4.3. Event cho từng partition

Spring Kafka còn có các event dành cho thao tác pause/resume một partition riêng:

- `ConsumerPartitionPausedEvent`
- `ConsumerPartitionResumedEvent`

Chúng phù hợp khi ứng dụng chủ động gọi `pausePartition(TopicPartition)` và `resumePartition(TopicPartition)`, thay vì pause toàn container.

Cần phân biệt event ở phạm vi container với event của một partition để không tính nhầm “toàn bộ consumer ngừng xử lý” khi chỉ một partition bị pause.

### 4.4. Event nào không phải pause event?

Một số Spring Kafka events khác thể hiện trạng thái riêng:

- `ListenerContainerIdleEvent`: listener container idle theo ngưỡng quan sát; không tự chứng minh container đang bị pause.
- `ListenerContainerNoLongerIdleEvent`: container không còn idle.
- `NonResponsiveConsumerEvent`: dấu hiệu consumer poll không phản hồi trong một số điều kiện theo cơ chế giám sát của Spring Kafka.
- `ConsumerStoppedEvent` / `ContainerStoppedEvent`: lifecycle đã dừng, khác với pause.
- Partition assignment/revocation callbacks: liên quan consumer group rebalance, không phải pause event.

Không kết luận consumer đang paused chỉ vì không có record mới, vì topic có thể thực sự không có dữ liệu hoặc listener container gặp vấn đề khác.

## 5. Cấu hình và nhận event bằng @EventListener

Spring Kafka publish container events qua cơ chế `ApplicationEventPublisher`. Với Spring Boot, có thể dùng một bean nhận event bằng annotation `@EventListener`.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPauseEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.warn(
            "Kafka consumer PAUSED, partitions={}",
            event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
            "Kafka consumer RESUMED, partitions={}",
            event.getPartitions()
        );
    }
}
~~~

Ví dụ trên chỉ quan sát trạng thái. Consumer pause event có tập `TopicPartition` để xác định phạm vi. Tùy phiên bản Spring Kafka, event cũng cung cấp source/container metadata phù hợp để phân biệt listener containers.

**Điểm vận hành:** mặc định một Spring application event listener có thể chạy đồng bộ trên thread publish event. Khi Kafka container publish từ consumer thread, callback `@EventListener` có thể chạy ngay trên consumer thread. Vì vậy callback nên ngắn, không gọi HTTP hoặc database lâu, không chờ latch vô hạn và không làm các thao tác KafkaConsumer nguy hiểm.

Nếu ứng dụng dùng asynchronous `ApplicationEventMulticaster` hoặc `@Async` để nhận events, callback có thể chạy trên thread khác. Khi đó càng không được dùng trực tiếp KafkaConsumer lấy từ event để gọi các phương thức không thread-safe. Hãy sử dụng container-level API như `pause()`/`resume()` qua cơ chế được hỗ trợ.

## 6. Ra lệnh pause/resume qua KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` quản lý các listener containers được tạo cho `@KafkaListener` có ID. Ta có thể tìm container theo ID và yêu cầu pause/resume từ một Spring service.

### 6.1. Khai báo listener có ID

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

ID `orders-listener` giúp các thành phần điều khiển truy xuất đúng listener container. Nếu ứng dụng có nhiều listeners, hãy đặt ID rõ ràng, không dùng một ID giống nhau cho các endpoints.

### 6.2. Service điều khiển container

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaPauseController {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaPauseController(
        KafkaListenerEndpointRegistry registry
    ) {
        this.registry = registry;
    }

    private MessageListenerContainer ordersContainer() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException(
                "Listener container orders-listener does not exist"
            );
        }
        return container;
    }

    public void requestPause() {
        ordersContainer().pause();
    }

    public void requestResume() {
        ordersContainer().resume();
    }

    public boolean isPauseRequested() {
        return ordersContainer().isPauseRequested();
    }

    public boolean isActuallyPaused() {
        return ordersContainer().isConsumerPaused();
    }
}
~~~

`pause()`/`resume()` ở cấp container là cách phù hợp để các thread điều khiển từ ngoài gửi yêu cầu. Không lấy thẳng `KafkaConsumer` của container rồi gọi `pause()` từ REST controller hoặc scheduler thread; KafkaConsumer có quy tắc thread ownership riêng.

### 6.3. Registry chứa những container nào?

Registry quản lý những containers gắn với Kafka listener endpoints. Nếu ứng dụng tự khai báo một container bean bằng Java mà không tạo từ `@KafkaListener`, container đó có thể được quản lý qua bean/lifecycle khác, không nhất thiết truy xuất được bằng cùng registry ID.

Tìm đúng container trước khi thao tác. Trong môi trường nhiều replica, registry của một JVM chỉ điều khiển listener containers **trong JVM đó**; gọi pause trong Pod A không tự pause Pod B.

## 7. Điều gì xảy ra khi gọi pause()?

Một cách đơn giản để hình dung:

~~~text
1. Backpressure controller thấy queue gần đầy.
2. controller gọi container.pause().
3. Container ghi nhận pause requested.
4. Container đi đến điểm an toàn trong vòng poll.
5. Container gọi pause cho các partition hiện đang được gán.
6. ConsumerPausedEvent được publish.
7. Container tiếp tục poll ở trạng thái paused để giữ group.
8. Sau khi downstream hồi phục, controller gọi resume().
9. Container thực hiện resume.
10. ConsumerResumedEvent được publish.
11. Listener tiếp tục nhận/dispatch record mới.
~~~

Một số lưu ý:

- Pause thường có hiệu lực ở ranh giới poll, không nhất thiết ngay đúng thời điểm người điều khiển gọi method.
- Record đang được listener xử lý không bị hủy hoặc rollback tự động bởi pause.
- Record đã được trả về trong một lần poll trước đó có thể vẫn được container xử lý trước khi pause có hiệu lực.
- Sau resume, consumer có thể nhận nhiều record đang backlog; cần kiểm soát tốc độ downstream thay vì resume liên tục ở mức tải không chịu nổi.

## 8. pauseImmediate và các record đã poll

Theo hành vi container truyền thống, pause được áp dụng sau khi hoàn tất xử lý **toàn bộ record còn lại trong lần poll hiện tại**. Nếu một lần poll đã trả về nhiều record và controller yêu cầu pause giữa chừng, những record chưa xử lý của poll đó có thể vẫn tiếp tục được gửi đến listener trước khi pause hiệu lực.

Từ Spring Kafka 2.9, có thể cấu hình `pauseImmediate` để container pause sau **record đang được xử lý**, thay vì chờ xử lý tất cả record đã trả về từ poll. Các record chưa xử lý trong lần poll có thể được container giữ lại để xử lý sau resume.

Ví dụ cấu hình ở container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setPauseImmediate(true);

    return factory;
}
~~~

Chế độ này hữu ích khi backpressure cần phản ứng nhanh, nhưng có đánh đổi:

- Container phải giữ những record đã fetch nhưng chưa dispatch trong bộ nhớ.
- Record đang xử lý vẫn cần hoàn tất hoặc lỗi theo error handler; pause không cắt ngang service method.
- Batch listener và record listener có các semantics khác nhau về một lần callback.
- Memory và kích thước poll cần được quản lý khi payload lớn.

Không coi `pauseImmediate=true` là khả năng ngắt xử lý ngay lập tức hoặc một transaction cancel. Đó là cấu hình thời điểm container áp dụng pause trong chu trình nhận record.

## 9. Container vẫn poll khi paused để tránh rebalance

Kafka có hai khái niệm khác nhau:

1. Consumer **không nhận thêm record để xử lý** từ partition bị pause.
2. Consumer vẫn phải **giữ group membership** qua liveness/poll contract.

Spring Kafka container được thiết kế để tiếp tục gọi `poll()` khi consumer đang paused, giúp duy trì hoạt động group và tránh một rebalance chỉ vì ứng dụng chủ động tạm ngừng đọc. Kafka consumer có thể xử lý heartbeat/group coordination trong khi không trả thêm record từ các partition paused.

~~~text
Container PAUSED:
    KafkaConsumer.poll()  -> vẫn có thể chạy
    Assigned partitions   -> vẫn thuộc consumer
    Record delivery       -> tạm dừng theo pause scope
    Group membership      -> vẫn được duy trì
    Consumer lag          -> có thể tăng
~~~

Tuy nhiên, **pause không đảm bảo group luôn ổn định** trong mọi sự cố. Nếu JVM bị stop-the-world, consumer thread không thể poll, coordinator không phản hồi hoặc mạng hỏng kéo dài, vẫn có thể xảy ra `session.timeout.ms` hoặc `max.poll.interval.ms` violation.

Vì vậy không dùng pause để che listener đang block vô hạn. Nếu callback business đã bị treo, một yêu cầu pause từ thread khác không làm listener thoát ra để container bắt đầu poll lại.

## 10. Pause không phải stop, unsubscribe hay shutdown

| Thao tác | Tác động dự kiến | Group membership | Điểm cần lưu ý |
|---|---|---|---|
| `container.pause()` | Ngừng nhận thêm từ partition của container khi hiệu lực | Thường duy trì, vì vẫn poll | Có thể còn record đã poll |
| `container.resume()` | Cho phép nhận/dispatch trở lại | Tiếp tục | Không tự giải quyết downstream overload |
| `container.stop()` | Dừng lifecycle listener container | Consumer có thể leave group | Có thể gây rebalance |
| `container.start()` | Khởi động listener container | Join/rejoin group | Assignment có thể thay đổi |
| Kafka `consumer.unsubscribe()` | Hủy subscription của consumer | Không còn membership theo subscription cũ | Không phải API điều khiển backpressure thông thường |
| `pausePartition(tp)` | Chỉ pause một topic-partition | Giữ consumer và các partition khác hoạt động | Cần quản lý trạng thái từng partition |

Nếu mục tiêu là tạm giảm tải vài giây hoặc vài phút, pause/resume thường phù hợp hơn stop/start vì tránh churn do join/leave group không cần thiết.

Nếu cần bảo trì dài, ngắt kết nối hạ tầng hoặc rollout, stop/start và lifecycle orchestration có thể phù hợp hơn. Tránh dùng pause vô hạn như một cơ chế thay thế vận hành deployment.

## 11. Pause toàn container và pause từng partition

Spring Kafka hỗ trợ pause/resume ở hai phạm vi khác nhau.

### 11.1. Toàn listener container

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

container.pause();
~~~

Lệnh này áp dụng yêu cầu pause trên các child consumers của container tương ứng. Với `ConcurrentMessageListenerContainer`, có thể có nhiều child containers, mỗi child sở hữu tập partition riêng.

Khi từng child thực sự pause, event có thể được publish tương ứng; không nên giả định một lệnh pause toàn concurrent container luôn tạo chính xác một Spring event.

### 11.2. Một partition riêng

Ví dụ muốn pause riêng `orders-2`:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

TopicPartition partition = new TopicPartition("orders", 2);

container.pausePartition(partition);
~~~

Khi muốn tiếp tục:

~~~java
container.resumePartition(
    new TopicPartition("orders", 2)
);
~~~

Với các phiên bản hỗ trợ APIs này, có thể dùng `isPartitionPauseRequested(tp)` và `isPartitionPaused(tp)` để phân biệt yêu cầu và trạng thái thực tế.

Khi partition pause có hiệu lực, Spring có thể publish `ConsumerPartitionPausedEvent`; khi resume có hiệu lực, publish `ConsumerPartitionResumedEvent`.

### 11.3. Khi nào pause từng partition?

Điều tiết từng partition hữu ích khi:

- Một partition có key nóng gây áp lực bất thường.
- Downstream chỉ gặp vấn đề với dữ liệu của một tenant được định tuyến chủ yếu vào một partition.
- Muốn tạm dừng một phân vùng để xử lý incident, trong khi những phân vùng khác vẫn tiếp tục.
- Một partition đang chờ external dependency nhưng các partition khác độc lập.

Tuy nhiên, nếu mọi partition cùng dùng một database pool đang cạn, pause từng partition có thể không đủ; cần điều tiết phạm vi container hoặc toàn instance.

### 11.4. Rebalance thay đổi partition ownership

Khi group rebalance, một partition có thể chuyển child consumer hoặc instance. Trạng thái pause yêu cầu ở container cũ không đồng nghĩa tự động được áp dụng trên consumer mới theo một business policy phân tán.

Nếu backpressure là chính sách cần tồn tại qua reassignment, phải có cơ chế áp dụng policy dựa trên assignment mới, hoặc một controller/coordination store mà các instance cùng hiểu. Không giả định event pause từ một pod điều khiển toàn bộ consumer group.

## 12. Bắt cả partition pause events

Nếu ứng dụng có cả pause container và pause theo partition, có thể quan sát riêng:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionPauseLogger {

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.warn("A Kafka partition was paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("A Kafka partition was resumed: {}", event);
    }
}
~~~

Ví dụ log toàn bộ event để tránh phụ thuộc vào một method accessor cụ thể trên các phiên bản Spring Kafka khác nhau. Khi cần tách topic/partition hoặc container ID ra thành structured fields, dùng accessor mà phiên bản đang sử dụng cung cấp.

Không nhầm event “một partition pause” với “mọi partition của consumer pause”. Dashboard cần có phạm vi rõ ràng, chẳng hạn `scope=container` hoặc `scope=partition`.

## 13. Backpressure controller theo ngưỡng queue

Một chiến lược phổ biến là dùng **high-watermark** để pause và **low-watermark** để resume.

Ví dụ:

- Queue capacity: 1.000 công việc.
- Khi queue size đạt 800: yêu cầu pause.
- Khi queue size giảm xuống 300: yêu cầu resume.

Khoảng cách giữa hai ngưỡng tạo **hysteresis**, tránh hệ thống bật/tắt pause liên tục khi queue dao động quanh một ngưỡng duy nhất.

~~~text
Queue size
  1000 |             capacity
   800 |----- PAUSE threshold -----------
       |        /------ paused
   300 |----- RESUME threshold ----------
       |                    \--- resumed
     0 +--------------------------------> Time
~~~

### 13.1. Bộ điều khiển minh họa

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class QueueBackpressureController {

    private static final int PAUSE_AT = 800;
    private static final int RESUME_AT = 300;

    private final KafkaListenerEndpointRegistry registry;
    private final WorkQueueMetrics queueMetrics;
    private final AtomicBoolean pauseRequested =
        new AtomicBoolean(false);

    public QueueBackpressureController(
        KafkaListenerEndpointRegistry registry,
        WorkQueueMetrics queueMetrics
    ) {
        this.registry = registry;
        this.queueMetrics = queueMetrics;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void regulate() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        int pending = queueMetrics.pendingCount();

        if (pending >= PAUSE_AT &&
                pauseRequested.compareAndSet(false, true)) {
            container.pause();
        } else if (pending <= RESUME_AT &&
                pauseRequested.compareAndSet(true, false)) {
            container.resume();
        }
    }
}
~~~

Để dùng `@Scheduled` cần bật Spring scheduling phù hợp, ví dụ `@EnableScheduling`. `WorkQueueMetrics` là abstraction minh họa do ứng dụng cung cấp để đo số công việc đang chờ; không phải một class mặc định của Spring Kafka.

**Quan trọng:** ví dụ trên là điểm bắt đầu cho một instance đơn giản, không phải một state machine production hoàn chỉnh. `pauseRequested` thể hiện quyết định của controller, không phải trạng thái thực tế của consumer. Sau khi có `ConsumerPausedEvent` hoặc `ConsumerResumedEvent`, vẫn cần xác nhận event phản ánh đúng listener container và các partition cần điều khiển.

### 13.2. Cần có safety margin

Khi controller đo queue size = 800 và yêu cầu pause, một số record đã được poll hoặc công việc đang chạy có thể tiếp tục được thêm vào queue trước khi pause thật sự có hiệu lực.

Vì vậy high-watermark phải **thấp hơn capacity** đủ xa để chứa phần inflight:

~~~text
Queue capacity = 1.000
Pause at       =   800
Safety margin  =   200 jobs
~~~

Margin cần dựa trên `max.poll.records`, concurrency, số replica, batch size, latency của scheduler và số task được submit trong khoảng chuyển tiếp. Không chọn 800/300 máy móc nếu workload có batch lớn hoặc burst cao.

### 13.3. Đảm bảo điều kiện resume có thể xảy ra

Nếu controller pause vì queue đầy nhưng worker xử lý queue đã chết, queue size sẽ không giảm về low-watermark. Container có thể paused rất lâu.

Cần thêm health checks, alert, timeout theo SLO và cơ chế operator can thiệp. Không tự resume vô điều kiện khi database còn down chỉ để tránh một trạng thái “paused”; làm vậy có thể tái tạo overload.

## 14. Event callback không phải chỗ thực hiện nghiệp vụ nặng

Một lỗi phổ biến:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    database.recalculateLargeReport(); // Có thể block rất lâu
}
~~~

Nếu callback chạy đồng bộ trên consumer thread, lệnh này có thể giữ consumer không quay lại poll đúng hạn. Thay vì quan sát pause, event listener vô tình gây thêm `max.poll.interval.ms` violation hoặc làm group mất ổn định.

Cách an toàn hơn:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {
    metrics.counter("kafka.consumer.pause.events").increment();
    log.info("Consumer paused partitions={}", event.getPartitions());
}
~~~

Các công việc nặng nên được chuyển đến một service/scheduler quản lý độc lập, có timeout và queue bền vững khi cần. Nếu dispatch bất đồng bộ, vẫn cần quản lý ordering, thread safety và lifecycle; không gọi trực tiếp KafkaConsumer từ event consumer thread khác.

## 15. Sử dụng event như xác nhận trạng thái

Giả sử một REST API vận hành gọi `container.pause()` và trả về ngay.

Nếu API trả:

~~~json
{
  "status": "PAUSED"
}
~~~

ngay sau lệnh gọi mà không kiểm tra trạng thái thực tế, nó có thể nói sai. Thời điểm đó container mới nhận yêu cầu.

Một API phù hợp hơn có thể trả:

~~~json
{
  "desiredState": "PAUSED",
  "observedState": "RUNNING",
  "note": "Pause requested; not yet observed"
}
~~~

Sau khi nhận `ConsumerPausedEvent` hoặc xác nhận `isConsumerPaused()`, trạng thái quan sát mới chuyển thành `PAUSED`.

Một state machine tối thiểu:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> PAUSE_REQUESTED: pause()
    PAUSE_REQUESTED --> PAUSED: ConsumerPausedEvent
    PAUSED --> RESUME_REQUESTED: resume()
    RESUME_REQUESTED --> RUNNING: ConsumerResumedEvent
    PAUSE_REQUESTED --> RESUME_REQUESTED: resume() before pause applied
    RESUME_REQUESTED --> PAUSE_REQUESTED: pause() before resume applied
~~~

Đây là mô hình khái niệm. Nếu xảy ra stop, rebalance, consumer loss, startup failure hoặc nhiều child containers, trạng thái thực tế có thể cần thêm nhánh và tracking theo partition.

### 15.1. ConcurrentMessageListenerContainer

Khi `concurrency > 1`, một parent container có nhiều child consumers. Một child có thể pause xong trước child khác. Nếu dashboard muốn báo toàn bộ group local là paused, cần xác nhận tất cả child containers/partitions liên quan đã pause, không lấy event đầu tiên làm xác nhận tổng thể.

### 15.2. Lọc event đúng container

Spring application events có thể được nhận bởi nhiều beans trong cùng ApplicationContext. Khi một ứng dụng có nhiều `@KafkaListener`, handler quan sát sẽ nhận events từ các containers khác nhau.

Cần lọc theo source/container ID hoặc một mapping xác định từ event đến container tương ứng của phiên bản Spring Kafka đang dùng. Nếu không, pause của listener `payments` có thể bị dashboard diễn giải nhầm thành pause của `orders`.

### 15.3. Event đồng bộ và bất đồng bộ

Nếu multicaster xử lý events đồng bộ, thứ tự callback quan sát thường gần với publish order trong consumer thread. Nếu chuyển sang multicaster bất đồng bộ, việc event đến consumer UI/monitor có thể lệch thứ tự do scheduling.

Vì vậy hệ thống cần đối chiếu **desired state**, **observed state** và trạng thái container hiện tại, không dựa vào timestamp event một cách mù quáng để kết luận state cuối cùng.

## 16. Điều gì xảy ra với record đã được fetch?

### 16.1. Record đang xử lý không tự biến mất

Pause ngăn nhận/dispatch thêm record theo phạm vi, nhưng không tự rollback một database transaction đang thực thi.

~~~text
Consumer poll nhận offsets 20, 21, 22
  |
  +-- listener xử lý 20
  |
  +-- controller gọi pause()
  |
  +-- container có thể xử lý tiếp 21, 22
      trước khi pause thực tế có hiệu lực
~~~

Đó là lý do cần hiểu thời điểm pause và `pauseImmediate`.

### 16.2. Retained records và memory

Với một số chế độ container, các record đã poll nhưng chưa dispatch có thể được giữ lại trong memory cho đến khi resume. Kích thước memory phụ thuộc record size, `max.poll.records`, concurrency và lỗi/retry đang diễn ra.

Cần quan sát heap/GC và không dựa vào pause như cơ chế xử lý batch vô hạn. Nếu memory queue đã gần tràn, gọi pause quá muộn vẫn có thể khiến ứng dụng OOM trước khi pause có hiệu lực.

### 16.3. Offset commit vẫn theo quy tắc xử lý thành công

Pause không có nghĩa container được phép commit offsets của record chưa xử lý. Những record đã xử lý xong có thể được commit theo AckMode, còn record inflight hoặc chưa xử lý phải được quản lý nhất quán.

Nếu listener tự dùng executor thread và trả về trước khi task hoàn tất, container có thể commit sớm theo listener-return semantics; pause event không sửa được lỗi này.

## 17. Tương tác với retry, error handler và DLT

Pause/backpressure và retry/error handling giải quyết hai mục tiêu khác nhau:

- **Pause/backpressure**: hạn chế nhận thêm workload mới khi downstream quá tải.
- **Retry**: quyết định cách thử lại record xử lý lỗi.
- **DLT/recovery**: chuyển record không xử lý được sang đường phục hồi.

Ví dụ database chậm:

1. Một record xử lý thất bại với timeout.
2. `DefaultErrorHandler` quyết định retry theo BackOff.
3. Một controller thấy database connection pool đang bão hòa và gọi `pause()`.
4. Container phải phối hợp retry của record lỗi với trạng thái pause khi đến poll boundary.
5. Khi downstream hồi phục và controller gọi `resume()`, container tiếp tục dispatch theo retry/ack semantics.

Pause không thay thế error handler. Không nên bắt exception trong listener rồi trả về như thành công chỉ để “giảm lỗi” trong lúc container paused.

### 17.1. Blocking retry vẫn có thể chặn poll

Nếu listener hoặc error handler đang block lâu trên consumer thread, container có thể chưa tới điểm áp dụng pause. Cần giới hạn thời gian của listener, BackOff và downstream calls; pause là cơ chế điều tiết, không phải ngắt một blocking operation đang chạy.

### 17.2. Non-blocking retry khác pause

Với non-blocking retry, record lỗi được gửi sang retry topic và tiếp tục xử lý sau delay. Pause tạm dừng consumer của một container/topic subscription; nó không tự tạo retry topic, không di chuyển record sang DLT và không hẹn lịch thử lại.

Nếu cần retry dài mà topic gốc vẫn tiến, cân nhắc retry topic; nếu cần dừng nhận thêm do overload chung, cân nhắc pause. Hai chiến lược có phạm vi khác nhau và cần theo dõi riêng.

## 18. Multi-instance: pause ở JVM này không pause JVM khác

Giả sử nhóm `orders-service` chạy ba pod:

~~~text
orders-service group
  Pod A: Listener container A
  Pod B: Listener container B
  Pod C: Listener container C
~~~

Nếu một REST endpoint trong Pod A gọi:

~~~java
registry.getListenerContainer("orders-listener").pause();
~~~

nó chỉ ảnh hưởng container của **Pod A**. Pod B và Pod C tiếp tục đọc những partition của chúng. Đối với lỗi database dùng chung, điều này có thể làm tải vẫn quá cao.

Muốn pause cả service, cần một control plane hoặc cấu hình chia sẻ để từng instance áp dụng policy ở local container:

~~~text
Shared policy: orders-consumption = PAUSE
    |
    +-- Pod A -> local container.pause()
    +-- Pod B -> local container.pause()
    +-- Pod C -> local container.pause()
~~~

Để tránh trạng thái không đồng nhất, hệ thống điều khiển cần quan sát xác nhận từ mỗi instance, xử lý pod restart/rebalance và có cơ chế khi một pod offline.

Không giả định Kafka group coordinator truyền “pause command” giữa các members. Kafka pause là thao tác của consumer/client, không phải một trạng thái group được Kafka tự phân phối.

## 19. Mối quan hệ với rebalance và partition assignment

Trong lúc container paused, consumer vẫn có thể tham gia rebalance nếu:

- Một member khác join hoặc rời group.
- Topic thay đổi partition count.
- Broker/group coordinator cần thay đổi assignment.
- Consumer bị session timeout hoặc poll interval violation.
- Hệ thống thay đổi group protocol hoặc membership.

Sau rebalance, tập partition được gán có thể khác. Do đó event `ConsumerPausedEvent` trước đó mô tả partition đã pause **tại thời điểm event**, không phải một hợp đồng bất biến rằng những partition đó mãi thuộc container.

Khi nhận assignment mới, chính sách backpressure cần được áp dụng phù hợp cho partition mới nếu container vẫn có pause request. Cần xem trạng thái yêu cầu lẫn assignment mới, nhất là khi dùng pausePartition trên một danh sách partition cụ thể.

### 19.1. Pause và heartbeat

Thông thường container vẫn poll để duy trì group membership; vì vậy chủ động pause không tự khiến session timeout. Nhưng nếu JVM bị freeze hoặc network hỏng, group vẫn có thể rebalance.

### 19.2. Pause và commit sau revoke

Consumer mất quyền sở hữu partition không nên tự commit offset của partition như thể nó vẫn là owner. Cần bảo vệ side effect qua idempotency và quản lý task inflight khi rebalance xảy ra.

### 19.3. Lỗi không có event resume

Nếu container bị stop khi đang paused hoặc partition được reassigned, không nên giả định mọi `ConsumerPausedEvent` đều có `ConsumerResumedEvent` tương ứng trong cùng vòng đời. Dashboard có thể cần ghi nhận `ContainerStoppedEvent` hoặc trạng thái container mới để không hiển thị paused mãi.

## 20. Monitoring cho container pause events

Những chỉ số nên theo dõi:

| Metric / log | Mục đích |
|---|---|
| Pause requested count | Số lần controller đề nghị pause |
| ConsumerPausedEvent count | Số lần container thực hiện pause |
| Resume requested count | Số lần đề nghị resume |
| ConsumerResumedEvent count | Số lần resume thực tế |
| Pause duration | Độ dài khoảng pause hiệu lực |
| Time from request to event | Độ trễ áp dụng pause/resume |
| Paused partition count | Phạm vi các partition tạm dừng |
| Consumer lag theo partition | Đánh giá backlog tăng khi paused |
| Downstream queue utilization | Tín hiệu kích hoạt backpressure |
| Database pool usage / API latency | Xác nhận downstream hồi phục |
| JVM heap/GC | Phát hiện retained records hoặc memory pressure |
| Rebalance count / commit failures | Phân biệt pause với mất membership |

Không phải mọi metric đều được Spring Kafka xuất sẵn dưới đúng tên này. Các metric pause duration hoặc request-to-event latency có thể cần instrumentation ứng dụng riêng.

### 20.1. Metric có cardinality an toàn

Gắn nhãn như application, listener ID, topic, pause reason và outcome. Không dùng event ID hoặc business key làm metric labels vì giá trị có thể tăng không giới hạn.

Ghi topic-partition cụ thể vào structured logs/traces khi điều tra incident. Nếu số partition rất lớn, cân nhắc aggregation trong metrics để tránh cardinality quá cao.

### 20.2. Tránh nhầm lag tăng với lỗi pause

Khi consumer paused, producer vẫn tiếp tục ghi Kafka. Lag tăng là điều có thể dự đoán. Alert nên xét:

- Pause có phải chủ động không?
- Queue/downstream đã hồi phục nhưng container vẫn paused?
- Lag có vượt thời hạn xử lý hoặc retention không?
- Pause duration có vượt SLO?
- Có dấu hiệu consumer crash hoặc không poll thay vì paused hợp lệ?

Lag cao không tự kết luận cơ chế pause bị lỗi, nhưng pause kéo dài vô hạn cũng không phải trạng thái được chấp nhận mặc định.

## 21. Quy trình vận hành khi cần pause

Một runbook ngắn:

1. Xác định listener ID, group ID, instance và topic-partitions.
2. Xác nhận nguyên nhân backpressure bằng queue, DB latency, HTTP error hoặc memory.
3. Ghi nhận baseline lag và processing rate.
4. Yêu cầu `container.pause()` hoặc `pausePartition(tp)` đúng scope.
5. Xác nhận `isPauseRequested()` để biết lệnh đã được chấp nhận.
6. Chờ/quan sát `ConsumerPausedEvent` hoặc trạng thái actual paused của container.
7. Theo dõi health, lag, retention budget và downstream trong khi paused.
8. Khi downstream đủ headroom, yêu cầu resume.
9. Xác nhận `ConsumerResumedEvent` và actual paused state trở về false.
10. Theo dõi tốc độ giảm lag, lỗi listener và backpressure tái diễn.
11. Nếu resume thất bại hoặc container stopped, điều tra lifecycle/rebalance, không lặp resume vô hạn.
12. Ghi nhận lý do, người vận hành, thời gian pause và kết quả vào incident log.

Khi tạm dừng do bảo trì có kiểm soát, cần một tiêu chí **hết hạn pause** hoặc cơ chế cảnh báo nếu công việc bị để quên quá lâu. Không tự động resume trái với yêu cầu an toàn khi downstream chưa sẵn sàng.

## 22. Kiểm thử container pause events

Để xác nhận hành vi, nên dùng test Kafka broker hoặc môi trường tích hợp có topic/group riêng. Nội dung cần kiểm thử là lifecycle, không chỉ kiểm tra method `pause()` có thể gọi được.

### 22.1. Pause một listener

1. Tạo topic thử với vài partition và một `@KafkaListener` có ID rõ ràng.
2. Gửi một vài record và xác nhận listener đã nhận.
3. Gọi `container.pause()` từ một controller/test thread.
4. Xác nhận `isPauseRequested()` trở thành true.
5. Chờ `ConsumerPausedEvent` hoặc `isConsumerPaused()` true.
6. Gửi thêm record.
7. Xác nhận listener không tiếp tục dispatch record mới trong khoảng đã pause hiệu lực (có tính đến các record đã poll trước đó).
8. Gọi `container.resume()`.
9. Xác nhận `ConsumerResumedEvent` hoặc trạng thái paused trở về false.
10. Xác nhận các record chờ được xử lý và offset tiến theo policy.

### 22.2. Pause trong lúc còn record đã poll

1. Tăng `max.poll.records` để một poll trả nhiều record.
2. Cho listener xử lý từng record có delay có kiểm soát.
3. Yêu cầu pause giữa chừng.
4. Quan sát số record tiếp tục được xử lý trước event pause.
5. Thử lại với `pauseImmediate=true` ở phiên bản hỗ trợ.
6. Đối chiếu thời điểm event và record inflight.

### 22.3. Pause từng partition

1. Tạo topic có ít nhất hai partition.
2. Gọi `pausePartition()` cho một partition.
3. Chờ partition pause event.
4. Gửi record đến cả partition paused và không paused.
5. Xác nhận partition khác vẫn xử lý.
6. Resume partition đã pause và xác nhận dữ liệu được xử lý tiếp.

### 22.4. Multi-instance và rebalance

1. Chạy hai consumer instances trong cùng group.
2. Pause container của một instance.
3. Xác nhận instance khác không tự bị pause.
4. Tạo một rebalance có kiểm soát.
5. Ghi nhận assignment mới và trạng thái pause tương ứng.
6. Xác nhận backpressure policy vẫn đúng sau reassignment.

### 22.5. Tránh test chỉ bằng sleep cố định

Lệnh `pause()` được áp dụng bất đồng bộ so với caller. Vì vậy trong test nên chờ một trạng thái/callback có timeout, ví dụ dùng CountDownLatch, Awaitility hoặc polling trên `isConsumerPaused()`. Sleep một số mili-giây cố định dễ tạo test flaky trên CI.

Một test cần cleanup trạng thái pause cuối cùng; nếu dùng chung consumer group giữa các test, nhớ resume hoặc stop container đúng lifecycle để test sau không bị ảnh hưởng.

## 23. Các lỗi thiết kế thường gặp

**Gọi pause() rồi lập tức coi consumer đã paused:** đây chỉ là yêu cầu; cần event hoặc actual state.

**Nghe ConsumerPausedEvent nhưng bỏ qua partitions/source:** ứng dụng nhiều containers có thể hiển thị sai trạng thái.

**Nhầm ConsumerPausedEvent với ListenerContainerIdleEvent:** idle không đồng nghĩa bị pause.

**Cho rằng pause dừng Kafka producer:** producer vẫn ghi; lag có thể tăng.

**Cho rằng pause tương đương stop:** container paused thường vẫn poll và duy trì group membership.

**Chờ handler kết thúc ngay sau pause():** record đang xử lý không bị cancel.

**Không dự phòng record đã poll:** queue có thể tiếp tục tăng trong khoảng chuyển tiếp.

**Gọi trực tiếp KafkaConsumer.pause() từ thread ngoài:** KafkaConsumer không thread-safe; dùng container-level API.

**Đặt logic database nặng trong @EventListener:** callback đồng bộ có thể chặn consumer thread.

**Bật @Async rồi truy cập KafkaConsumer từ event:** consumer không được thao tác tùy ý trên thread khác.

**Chỉ một pod pause và cho rằng cả group pause:** registry điều khiển local instance.

**Không resume khi downstream hồi phục:** tạo backlog kéo dài và nguy cơ retention.

**Không dùng hysteresis:** queue dao động nhỏ cũng làm pause/resume liên tục.

**Dùng pause thay error handler:** record lỗi vẫn cần retry/recovery/DLT.

**Dùng pause để sửa listener blocking quá lâu:** container có thể không tới poll boundary để áp dụng pause.

**Đánh dấu record xử lý thành công dù task nền chưa hoàn tất:** offset có thể commit sớm; pause event không khắc phục.

**Cho rằng event resume luôn đến sau event pause:** stop, rebalance hoặc lifecycle đổi có thể phá kỳ vọng một cặp event hoàn hảo.

## 24. Bảng quyết định nhanh

| Bối cảnh | Công cụ phù hợp | Xác nhận cần quan sát |
|---|---|---|
| Database dùng chung đang quá tải | Pause container ở các instance liên quan | `ConsumerPausedEvent`, lag, DB headroom |
| Chỉ một partition nóng | `pausePartition(tp)` | Partition pause event, các partition khác vẫn tiến |
| Cần tạm dừng ngắn nhưng giữ group membership | `container.pause()` | Actual paused và heartbeat/group stability |
| Cần ngừng hẳn listener khi deploy | `container.stop()` và lifecycle orchestration | Stopped event, group reassignment |
| Queue có high/low watermark | Backpressure controller + hysteresis | Queue capacity, pause duration, resume |
| Muốn dừng ngay sau record hiện tại | `pauseImmediate=true` nếu hỗ trợ | Inflight records và memory retained |
| Record bị lỗi nghiệp vụ | `DefaultErrorHandler` / retry / DLT | Retry attempts và recovery outcome |
| Muốn delay retry dài mà topic chính vẫn tiến | Retry topic cho record listener khi phù hợp | Retry lag, DLT, ordering |
| Muốn xác nhận pause thực sự có hiệu lực | `ConsumerPausedEvent` hoặc `isConsumerPaused()` | Đúng container và partition scope |
| Muốn biết listener đang idle hay pause | Phân biệt idle events với pause events | Trạng thái container và assignment |

## 25. Nguyên tắc vận hành trong production

- Dùng `KafkaListenerEndpointRegistry` và container-level `pause()/resume()` để điều khiển listener, không thao tác KafkaConsumer từ thread ngoài.
- Phân biệt **desired pause request** với **observed actual pause**; dùng `ConsumerPausedEvent` và `ConsumerResumedEvent` để ghi nhận chuyển trạng thái.
- Với concurrent containers, theo dõi trạng thái các child consumers và partitions, không coi event đầu tiên là toàn bộ group đã pause.
- Phân biệt pause toàn container với pause từng partition; dùng event đúng scope.
- Hiểu rằng pause không hủy record đang xử lý và có thể chưa ngăn record đã được poll.
- Nếu cần phản ứng nhanh, cân nhắc `pauseImmediate` cùng giới hạn memory cho retained records.
- Giữ listener event callbacks ngắn để không chặn consumer thread.
- Dùng high/low watermarks và safety margin để hạn chế oscillation và tránh queue overflow.
- Theo dõi consumer lag, pause duration, DB/HTTP headroom và retention trong thời gian paused.
- Đảm bảo có điều kiện resume, cảnh báo pause quá lâu và phương án recovery khi container stop/rebalance.
- Trong ứng dụng nhiều replica, thiết kế điều khiển phân tán nếu cần pause toàn service.
- Không dùng pause thay thế error handler, idempotency, Kafka offset correctness hay transaction boundary.
- Kiểm thử request-to-event timing, record inflight, rebalance và resume trên môi trường tích hợp.

**Kết luận:** `ConsumerPausedEvent` và `ConsumerResumedEvent` giúp Spring Kafka báo cho ứng dụng biết thời điểm listener container thực sự áp dụng hoặc gỡ bỏ pause. Đây là tín hiệu quan trọng khi xây dựng backpressure đáng tin cậy: tránh báo trạng thái quá sớm, quan sát đúng phạm vi partition và kiểm soát độ dài thời gian tạm dừng. Nhưng pause vẫn là một điều khiển vòng đời tiêu thụ dữ liệu, không phải lời hứa rằng mọi side effect đã dừng, mọi record đã commit hay group sẽ không bao giờ rebalance.
