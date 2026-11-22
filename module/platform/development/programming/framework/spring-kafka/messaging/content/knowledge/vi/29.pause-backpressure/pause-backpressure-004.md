# Resume partition cụ thể

Trong một consumer group, một listener container có thể đọc nhiều partition cùng lúc. Khi một partition đang tạo backlog lớn hoặc hệ thống phía sau tạm thời không đủ khả năng xử lý, ứng dụng có thể tạm dừng riêng partition đó và tiếp tục đọc các partition còn lại. Khi năng lực xử lý phục hồi, ứng dụng gọi `resumePartition()` để consumer tiếp tục lấy record từ đúng partition đã tạm dừng.

Spring Kafka cung cấp API `pausePartition(TopicPartition)` và `resumePartition(TopicPartition)` trên `MessageListenerContainer`. API này cho phép điều khiển partition mà không phải dừng toàn bộ listener container. `resumePartition()` là thao tác yêu cầu consumer tiếp tục đọc partition sau khi container xử lý poll tiếp theo; nó không tự commit offset và cũng không chuyển partition sang consumer khác.

## 1. Khi nào cần resume một partition cụ thể?

Giả sử listener `orders-listener` đang đọc bốn partition của topic `orders.events`. Partition 2 có nhiều đơn hàng cần cập nhật vào một hệ thống downstream đang chậm, trong khi các partition khác vẫn xử lý bình thường.

Thay vì pause toàn bộ container, ứng dụng có thể pause riêng `orders.events-2`. Khi downstream xử lý xong backlog, ứng dụng resume partition 2 để tiếp tục đọc.

```text
orders.events
  P0  ---> consumer tiếp tục đọc
  P1  ---> consumer tiếp tục đọc
  P2  ---> PAUSED ---- backlog downstream giảm ----> RESUMED
  P3  ---> consumer tiếp tục đọc
```

Các trường hợp thường gặp:

- Một partition có hàng đợi xử lý bất đồng bộ gần đầy.
- Dịch vụ downstream đang giới hạn tốc độ nhận dữ liệu theo một nhóm key hoặc partition.
- Một partition cần bảo trì hoặc xử lý dữ liệu tồn đọng có kiểm soát.
- Hệ thống muốn áp dụng backpressure theo partition thay vì dừng toàn bộ consumer.

Nếu tất cả partition đều bị ảnh hưởng bởi cùng một dependency đang ngừng hoạt động, pause toàn bộ container có thể phù hợp hơn. Nếu chỉ một partition có backlog, pause/resume theo partition giúp phần còn lại tiếp tục tiến triển.

## 2. Điều kiện và phiên bản API

Các API `pausePartition()`, `resumePartition()`, `isPartitionPauseRequested()` và `isPartitionPaused()` có từ Spring Kafka 2.7. Chúng được cung cấp bởi `MessageListenerContainer` và có thể sử dụng với các container listener tương ứng.

`TopicPartition` xác định chính xác một partition bằng tên topic và số partition:

```java
import org.apache.kafka.common.TopicPartition;

TopicPartition partition = new TopicPartition("orders.events", 2);
```

Partition number bắt đầu từ `0`. Vì vậy, partition số 2 là partition thứ ba của topic.

Partition cần được gán cho consumer thuộc listener container đang điều khiển. Hãy xác định đúng listener ID, topic và partition; không suy luận rằng partition số 2 luôn thuộc một consumer cụ thể vì assignment có thể thay đổi sau rebalance.

## 3. Lấy listener container từ registry

Với listener khai báo bằng `@KafkaListener`, có thể lấy container thông qua `KafkaListenerEndpointRegistry`. Đặt `id` rõ ràng trên annotation để ứng dụng có định danh ổn định khi điều khiển:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Xử lý sự kiện đơn hàng.
    }
}
```

Service điều khiển lấy container bằng ID:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class PartitionControlService {

    private final KafkaListenerEndpointRegistry registry;

    PartitionControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer getContainer(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Unknown Kafka listener: " + listenerId
            );
        }
        if (!container.isRunning()) {
            throw new IllegalStateException(
                    "Kafka listener is not running: " + listenerId
            );
        }
        return container;
    }
}
```

Ví dụ này tập trung vào việc tìm container và xác nhận lifecycle. Một container được khai báo trực tiếp thành bean thay vì tạo từ `@KafkaListener` có thể cần được inject và điều khiển trực tiếp, không nhất thiết xuất hiện trong registry.

## 4. Pause và resume đúng partition

Khi cần tạm dừng partition, gọi `pausePartition()`. Khi điều kiện backpressure đã hết, gọi `resumePartition()` với cùng `TopicPartition`:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class OrderPartitionController {

    private final KafkaListenerEndpointRegistry registry;

    OrderPartitionController(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pausePartition(int partitionNumber) {
        MessageListenerContainer container = requireContainer("orders-listener");
        TopicPartition partition = new TopicPartition("orders.events", partitionNumber);
        container.pausePartition(partition);
    }

    public void resumePartition(int partitionNumber) {
        MessageListenerContainer container = requireContainer("orders-listener");
        TopicPartition partition = new TopicPartition("orders.events", partitionNumber);
        container.resumePartition(partition);
    }

    private MessageListenerContainer requireContainer(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);
        if (container == null || !container.isRunning()) {
            throw new IllegalStateException(
                    "Listener is missing or stopped: " + listenerId
            );
        }
        return container;
    }
}
```

Trong thực tế, nên nhận topic và partition từ metadata đã được kiểm tra thay vì để API công khai nhận một số partition tùy ý. Cũng nên giới hạn listener ID được phép điều khiển để một request quản trị không vô tình pause nhầm luồng dữ liệu.

## 5. Pause request khác với paused thực tế

`pausePartition()` là yêu cầu được gửi tới listener container. Container xử lý yêu cầu trên consumer thread ở ranh giới poll; vì vậy trạng thái không nhất thiết đổi ngay trong cùng thời điểm gọi method.

Hai API giúp phân biệt trạng thái:

| API | Ý nghĩa |
|---|---|
| `isPartitionPauseRequested(partition)` | Đã có yêu cầu pause partition này |
| `isPartitionPaused(partition)` | Partition đã thực sự được pause |

Ví dụ kiểm tra:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.MessageListenerContainer;

MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");
if (container == null) {
    throw new IllegalStateException("orders-listener was not found");
}

TopicPartition partition = new TopicPartition("orders.events", 2);

container.pausePartition(partition);

boolean requested = container.isPartitionPauseRequested(partition);
boolean paused = container.isPartitionPaused(partition);
```

Ngay sau khi gọi `pausePartition()`, `requested` có thể là `true` trong khi `paused` vẫn là `false`. Sau khi consumer xử lý poll tiếp theo và pause có hiệu lực, `isPartitionPaused()` mới phản ánh trạng thái thực tế.

Sau khi gọi `resumePartition()`, hãy theo dõi sự kiện resumed hoặc kiểm tra `isPartitionPaused()` cho tới khi trả về `false`. Không xem việc method trả về là bằng chứng partition đã bắt đầu nhận record mới.

## 6. Resume partition trong ConcurrentMessageListenerContainer

Khi `@KafkaListener` dùng `concurrency` lớn hơn một, Spring Kafka tạo `ConcurrentMessageListenerContainer` làm container cha và nhiều container con. Mỗi consumer con sở hữu assignment riêng.

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        concurrency = "3"
)
public void consume(String payload) {
    process(payload);
}
```

Có thể lấy container cha từ registry và gọi `pausePartition()` hoặc `resumePartition()` trên container đó. Spring Kafka điều phối yêu cầu tới consumer con đang sở hữu partition được chỉ định.

Không giả định `orders.events-2` luôn thuộc consumer có suffix `-2` hoặc child container index 2. Kafka partition assignor quyết định assignment và có thể thay đổi sau rebalance. Nếu cần quan sát sâu, dùng assignment và client ID metrics để xác định consumer con hiện đang sở hữu partition.

## 7. Partition pause không giống container pause

Spring Kafka cung cấp cả `pause()`/`resume()` để điều khiển toàn bộ container và `pausePartition()`/`resumePartition()` để điều khiển một partition:

| API | Phạm vi | Khi nào dùng |
|---|---|---|
| `pause()` | Tất cả partition được container quản lý | Toàn bộ listener cần tạm dừng nhận record |
| `resume()` | Tiếp tục tất cả partition đã pause ở container | Toàn bộ listener đã sẵn sàng xử lý lại |
| `pausePartition(tp)` | Một partition cụ thể | Chỉ một partition có backlog hoặc cần giới hạn tốc độ |
| `resumePartition(tp)` | Một partition cụ thể | Partition đó đã đủ điều kiện tiếp tục |

Pause partition không chuyển assignment sang consumer khác. Partition vẫn thuộc consumer group member đang giữ nó; consumer tiếp tục poll để duy trì hoạt động group nhưng không lấy thêm record từ partition đã pause. Các partition khác được gán cho consumer vẫn có thể tiếp tục được đọc.

Do partition vẫn được giữ assignment, lag của partition đó có thể tăng trong thời gian pause. Đây là hành vi backpressure có chủ đích; cần theo dõi lag và thời gian pause để tránh giữ partition quá lâu.

## 8. Pause/resume không tự commit offset

Pause hoặc resume chỉ điều khiển việc lấy record. Nó không thay đổi committed offset và không tự xác nhận các record đã xử lý.

Offset vẫn được quản lý theo acknowledgement mode và transaction configuration của listener container:

- Record đã xử lý xong trước khi pause có thể được commit theo `AckMode`.
- Record đã được poll hoặc đã đưa vào hàng đợi xử lý trước khi pause có thể vẫn còn đang in-flight.
- Khi partition resume, consumer tiếp tục đọc theo vị trí hiện tại và committed offset theo cơ chế Kafka/Spring Kafka.
- Nếu xử lý bất đồng bộ, phải bảo đảm commit không vượt qua record chưa hoàn tất.

Không gọi `commitSync()` hoặc tự thay đổi offset chỉ vì đã pause partition. Nếu cần replay, reset offset hoặc seek, hãy dùng cơ chế riêng và hiểu rõ tác động tới tiến độ của consumer group.

## 9. Pause có hiệu lực ở ranh giới poll

`pausePartition()` là thread-safe và việc pause thực tế được thực hiện trên consumer thread trước lần `poll()` tiếp theo. Tương tự, `resumePartition()` có hiệu lực sau poll theo vòng đời container.

Điều này có một hệ quả quan trọng: pause không hủy lời gọi listener đang chạy và không thu hồi các record đã được poll trước khi pause có hiệu lực. Nếu một lần poll đã trả về nhiều record của cùng partition, container có thể còn phải xử lý các record đang nằm trong kết quả poll đó theo cấu hình listener.

Với batch listener hoặc xử lý bất đồng bộ, cần tính đến lượng record đã nhận trước khi pause. Pause ngăn nhận thêm dữ liệu ở các poll tiếp theo; nó không tự làm rỗng queue hoặc hủy task đã submit.

## 10. Dùng pause/resume để tạo backpressure theo partition

Một cách phổ biến là theo dõi độ sâu hàng đợi xử lý cho từng partition. Khi queue vượt high watermark, pause partition tương ứng. Khi queue giảm xuống low watermark, resume partition.

Ví dụ:

```java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class PartitionBackpressureController {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionBackpressureController.class);

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;

    PartitionBackpressureController(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void onQueueDepth(
            String listenerId,
            TopicPartition partition,
            int queueDepth
    ) {
        MessageListenerContainer container = requireRunningContainer(listenerId);

        if (queueDepth >= HIGH_WATERMARK
                && !container.isPartitionPauseRequested(partition)
                && !container.isPartitionPaused(partition)) {
            container.pausePartition(partition);
            log.warn("Pause requested: partition={}, queueDepth={}", partition, queueDepth);
        } else if (queueDepth <= LOW_WATERMARK
                && (container.isPartitionPauseRequested(partition)
                    || container.isPartitionPaused(partition))) {
            container.resumePartition(partition);
            log.info("Resume requested: partition={}, queueDepth={}", partition, queueDepth);
        }
    }

    private MessageListenerContainer requireRunningContainer(String listenerId) {
        MessageListenerContainer container = registry.getListenerContainer(listenerId);
        if (container == null || !container.isRunning()) {
            throw new IllegalStateException("Listener is missing or stopped: " + listenerId);
        }
        return container;
    }
}
```

Ví dụ giả định queue depth được đo riêng cho từng `TopicPartition` và một component giám sát gọi `onQueueDepth()` khi độ sâu queue thay đổi. High watermark 800 và low watermark 300 chỉ là con số minh họa, cần chọn theo dung lượng queue và tốc độ xử lý thực tế.

Hai ngưỡng khác nhau tạo hysteresis: hệ thống không liên tục pause/resume khi queue dao động quanh một giá trị. Có thể bổ sung thời gian ổn định tối thiểu, cooldown hoặc giới hạn số lần chuyển trạng thái để tránh thrashing.

High watermark nên thấp hơn giới hạn cứng của queue đủ nhiều để dành chỗ cho record đã được poll trong batch hiện tại và task đã submit nhưng chưa hoàn tất. Nếu queue chỉ còn một vài chỗ trống khi gửi pause request, các record đang in-flight vẫn có thể làm queue vượt giới hạn trước khi pause có hiệu lực.

## 11. Backpressure cần phối hợp với hàng đợi và xử lý bất đồng bộ

Nếu listener nhận record rồi submit task vào executor, pause partition khi queue đầy là một phần của giải pháp. Cần thiết kế toàn bộ pipeline:

1. Queue phải có giới hạn dung lượng; queue vô hạn chỉ che giấu tình trạng downstream không theo kịp.
2. Theo dõi queue depth theo partition hoặc theo luồng nghiệp vụ để biết chính xác partition nào gây áp lực.
3. Khi đạt high watermark, yêu cầu pause partition trước khi tiếp tục nhận thêm nhiều batch.
4. Chờ task đang chạy hoàn tất và queue giảm xuống low watermark.
5. Resume partition sau khi hệ thống có đủ capacity.
6. Giới hạn số task in-flight và xử lý lỗi task trước khi xác nhận offset.

Nếu nhiều partition dùng chung một queue toàn cục, có thể khó xác định partition nào cần pause. Nếu queue thuộc một partition, có thể ánh xạ trực tiếp `TopicPartition` với queue đó.

Không commit offset ngay sau khi submit task nếu task chưa hoàn tất và nghiệp vụ yêu cầu xử lý thành công mới được xác nhận. Nếu task hoàn tất không theo thứ tự, phải có cơ chế quản lý offset theo thứ tự liên tục đã xử lý của từng partition; không commit vượt qua một record còn pending.

## 12. Theo dõi pause/resume bằng application events

Spring Kafka phát event khi consumer pause hoặc resume một partition:

- `ConsumerPartitionPausedEvent` được phát khi partition thực sự được pause.
- `ConsumerPartitionResumedEvent` được phát khi partition được resume.

Các event này có từ Spring Kafka 2.7 và hữu ích để ghi log, cập nhật dashboard hoặc xác nhận thao tác backpressure đã có hiệu lực.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;

@Component
class PartitionPauseEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(PartitionPauseEventObserver.class);

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resumed: {}", event);
    }
}
```

Với `ConcurrentMessageListenerContainer`, event có thể được phát từ child container; event cũng cung cấp tham chiếu tới container cha. Nên ghi listener ID, topic và partition để đối chiếu sự kiện với queue depth, consumer lag và client ID.

Không chỉ ghi log lúc gửi yêu cầu. Event pause/resume xác nhận trạng thái thực tế của consumer, còn `isPartitionPauseRequested()` cho biết yêu cầu đã được đăng ký.

## 13. Quy trình resume partition an toàn

Khi downstream phục hồi, có thể áp dụng trình tự sau:

1. Xác định đúng listener ID và `TopicPartition` đang bị pause.
2. Kiểm tra listener container vẫn chạy và partition còn thuộc assignment phù hợp.
3. Xác nhận queue depth đã xuống dưới low watermark trong khoảng thời gian ổn định.
4. Gọi `resumePartition(topicPartition)`.
5. Theo dõi `ConsumerPartitionResumedEvent` hoặc trạng thái `isPartitionPaused()` chuyển về `false`.
6. Quan sát record rate, queue depth và consumer lag để xác nhận partition đang tiến triển.
7. Nếu queue lại vượt high watermark, pause lại theo cùng chính sách.

Nếu partition đã được revoke do rebalance, consumer cũ không còn là chủ sở hữu. Sau khi assignment thay đổi, cần xác định container/consumer hiện tại sở hữu partition trước khi điều khiển tiếp. Không giữ một giả định cố định về consumer con sau rebalance.

Chỉ riêng thao tác pause partition không làm consumer rời group hoặc kích hoạt rebalance. Consumer vẫn poll để duy trì group membership; partition vẫn được giữ assignment cho tới khi có thay đổi membership hoặc assignment khác.

## 14. Kiểm thử pause/resume partition

Nên có integration test với Kafka broker hoặc embedded broker để kiểm tra hành vi thực tế của container:

- Gửi record vào ít nhất hai partition.
- Pause một partition và xác nhận partition đó không nhận thêm record mới sau khi pause có hiệu lực.
- Xác nhận partition còn lại vẫn tiếp tục được xử lý.
- Resume partition đã pause và xác nhận consumer tiếp tục đọc record.
- Kiểm tra `ConsumerPartitionPausedEvent` và `ConsumerPartitionResumedEvent`.
- Kiểm tra `isPartitionPauseRequested()` và `isPartitionPaused()` ở các thời điểm tương ứng.
- Xác nhận pause không gây rebalance chỉ vì partition bị pause.
- Xác nhận offset vẫn được commit theo `AckMode` và không vượt qua task bất đồng bộ chưa hoàn tất.
- Chạy test với `concurrency` lớn hơn một để kiểm tra parent/child container và assignment.

Không nên chỉ mock `MessageListenerContainer` rồi kết luận backpressure hoạt động đúng. Mock phù hợp để kiểm tra controller có gọi đúng API; integration test mới xác minh poll, event và hành vi consumer với partition thực.

## 15. Những nhầm lẫn thường gặp

1. **Gọi `resumePartition()` trên sai listener ID.** Partition có thể thuộc một container khác; phải xác định đúng endpoint.
2. **Cho rằng method trả về nghĩa là partition đã resume.** Yêu cầu được xử lý ở ranh giới poll; hãy theo dõi event hoặc trạng thái thực tế.
3. **Nhầm partition pause với container pause.** `resumePartition()` chỉ tiếp tục một partition, còn `resume()` tác động phạm vi container.
4. **Cho rằng pause chuyển partition sang consumer khác.** Partition vẫn giữ assignment trong group; lag có thể tăng trong thời gian pause.
5. **Cho rằng pause tự commit offset.** Offset vẫn tuân theo AckMode/transaction configuration.
6. **Cho rằng pause hủy record đã poll.** Record in-flight hoặc đã được đưa vào queue vẫn cần xử lý theo thiết kế.
7. **Gọi trực tiếp `KafkaConsumer.resume()` từ thread nghiệp vụ.** Consumer không thread-safe; dùng API thread-safe của listener container.
8. **Resume khi queue vẫn cao.** Backpressure sẽ mất tác dụng và queue có thể đầy lại ngay.
9. **Dùng một ngưỡng duy nhất cho pause/resume.** Queue dao động quanh ngưỡng có thể gây pause/resume liên tục; nên dùng high/low watermark.
10. **Không xử lý rebalance.** Assignment có thể đổi; cần xác định lại container đang sở hữu partition.

`resumePartition()` cho phép khôi phục việc đọc một partition mà không phải resume toàn bộ listener container. Hãy dùng `KafkaListenerEndpointRegistry` để tìm đúng container, tạo `TopicPartition` chính xác, theo dõi yêu cầu và trạng thái thực tế, rồi chỉ resume khi downstream đã đủ capacity. Khi kết hợp high/low watermark, queue hữu hạn, offset handling đúng thứ tự và application events, pause/resume theo partition trở thành cơ chế backpressure có thể quan sát và vận hành an toàn.

Tài liệu chính thức: [Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html) và [MessageListenerContainer API](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/listener/MessageListenerContainer.html).
