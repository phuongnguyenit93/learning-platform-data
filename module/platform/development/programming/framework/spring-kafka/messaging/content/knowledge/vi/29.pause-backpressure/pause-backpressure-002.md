# Resume listener container

Trong Spring Kafka, listener container có thể được tạm dừng và tiếp tục mà không cần hủy consumer hoặc rời consumer group. API `pause()` yêu cầu container ngừng nhận thêm record; API `resume()` gỡ yêu cầu đó để consumer tiếp tục xử lý. Đây là cách điều tiết luồng tiêu thụ khi downstream đang quá tải, hàng đợi nội bộ gần đầy hoặc hệ thống cần tạm ngưng xử lý trong một khoảng thời gian.

Pause/resume khác với stop/start. Khi container pause, consumer vẫn thuộc consumer group và container tiếp tục poll để duy trì liveness; các partition được pause không trả record mới cho listener. Khi stop, consumer được đóng và rời group, có thể kích hoạt rebalance. Vì vậy, pause/resume phù hợp cho điều tiết tạm thời, còn stop/start thuộc vòng đời triển khai và vận hành.

Bài học thuộc chương **Pause và backpressure** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Pause và resume trong listener container

Spring Kafka cung cấp API trên listener container:

- `pause()`: yêu cầu pause consumer do container quản lý.
- `resume()`: yêu cầu tiếp tục tiêu thụ.
- `isPauseRequested()`: kiểm tra container có yêu cầu pause hay không.
- `isConsumerPaused()`: kiểm tra consumer thực tế đã pause hay chưa.
- `pausePartition(TopicPartition)`: yêu cầu pause một partition.
- `resumePartition(TopicPartition)`: yêu cầu resume một partition.
- `isPartitionPauseRequested(TopicPartition)` và `isPartitionPaused(TopicPartition)`: kiểm tra trạng thái pause theo partition.

Ví dụ trạng thái:

~~~text
RUNNING
   |
   | pause()
   v
PAUSE REQUESTED
   |
   | consumer thread áp dụng pause
   v
PAUSED
   |
   | resume()
   v
RESUME REQUESTED
   |
   | consumer thread áp dụng resume
   v
RUNNING
~~~

`pause()` và `resume()` là yêu cầu điều khiển container. Consumer API thực tế được gọi trên consumer thread do container quản lý. Ứng dụng có thể yêu cầu pause/resume từ thread quản lý, scheduler hoặc thành phần giám sát mà không trực tiếp gọi KafkaConsumer từ thread ngoài.

## 2. Lấy listener container qua KafkaListenerEndpointRegistry

Listener khai báo ID ổn định để ứng dụng có thể tìm container:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "order-events",
    groupId = "order-service"
)
public void onOrderEvent(OrderEvent event) {
    orderService.process(event);
}
~~~

Inject `KafkaListenerEndpointRegistry` và lấy container theo ID:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

`getListenerContainer(id)` trả về container được đăng ký với ID tương ứng hoặc null nếu không tìm thấy. Trong ứng dụng thực tế, nên kiểm tra null và trạng thái lifecycle trước khi điều khiển.

ID của `@KafkaListener` là khóa để quản lý container. Đừng dựa vào tên class listener hoặc tên topic để suy ra ID; khai báo ID rõ ràng sẽ giúp vận hành và monitoring ổn định hơn.

## 3. Pause/resume khác stop/start

Hai cặp API phục vụ mục đích khác nhau:

| Thao tác | Consumer | Consumer group membership | Rebalance | Mục đích |
| --- | --- | --- | --- | --- |
| pause/resume | Giữ consumer mở; tạm ngừng/tiếp tục nhận record | Giữ membership khi consumer vẫn poll đúng hạn | Thông thường không tạo rebalance chỉ vì pause | Backpressure, bảo trì ngắn, điều tiết tải |
| stop/start | Đóng rồi tạo lại consumer khi start | Rời group rồi tham gia lại | Có thể xảy ra | Shutdown, deploy, thay cấu hình, lifecycle |

Pause không xóa offset và không reset consumer position. Khi resume, consumer tiếp tục từ vị trí hiện tại theo committed position và các record đã fetch nhưng chưa xử lý tùy semantics container.

Stop đóng consumer và giải phóng tài nguyên. Khi start, consumer tham gia group và nhận assignment theo coordinator; partition có thể được giao cho member khác trong thời gian đó.

Không dùng stop/start như nút backpressure thông thường nếu mục tiêu chỉ là tạm ngưng tiêu thụ. Việc liên tục rời/vào group gây rebalance và tăng chi phí điều phối.

## 4. Pause có dừng poll và heartbeat không?

Pause listener container không đồng nghĩa dừng consumer thread. Container vẫn tiếp tục gọi `poll()` theo vòng lặp để duy trì hoạt động và membership; các partition đang pause không trả record mới cho listener.

Điều này quan trọng vì Kafka consumer cần được poll trong giới hạn `max.poll.interval.ms`. Nếu chỉ pause container đúng cách, container vẫn poll và consumer có thể tiếp tục giữ membership trong group.

Tuy nhiên, nếu listener đang chạy lâu hoặc thread bị block trước khi container có thể poll lần tiếp theo, pause không giải quyết được việc vượt `max.poll.interval.ms`. Pause cũng không ngắt listener đang thực thi và không dừng một HTTP request hoặc database query đã bắt đầu.

Cần phân biệt:

- Pause: yêu cầu consumer không nhận record mới từ partition đã pause.
- Poll: vòng lặp consumer vẫn tiếp tục chạy để duy trì liveness.
- Heartbeat: Kafka client duy trì group membership theo cơ chế poll/heartbeat của phiên bản client.
- Listener execution: công việc đang chạy không bị pause cưỡng bức.

Không gọi trực tiếp `KafkaConsumer.pause()` hoặc `KafkaConsumer.resume()` từ thread quản lý ứng dụng. Consumer không thread-safe; hãy dùng API của listener container.

## 5. Khi nào yêu cầu pause có hiệu lực?

`pause()` được yêu cầu từ thread ứng dụng nhưng việc gọi consumer pause được thực hiện trên consumer thread. Vì vậy, pause không nhất thiết cắt ngang ngay poll hiện tại hoặc listener invocation đang chạy.

Theo hành vi container thông dụng, yêu cầu pause được áp dụng ở ranh giới poll tiếp theo. Những record đã được poll có thể vẫn đang chờ dispatch hoặc xử lý. Với record listener, container có thể tiếp tục giao các record đã nhận từ poll hiện tại trước khi trạng thái pause có hiệu lực hoàn toàn; với batch listener, batch hiện tại thường đã được chuyển vào một lần invocation.

Một số phiên bản Spring Kafka có tùy chọn `pauseImmediate` để thay đổi thời điểm container tạm dừng việc giao các record đã poll, ví dụ dừng sau record hiện tại thay vì chờ xử lý hết dữ liệu của poll. Hãy kiểm tra API và semantics của phiên bản đang dùng trước khi bật tùy chọn này.

Do đó, queue backpressure phải tính đến lượng record in-flight và dữ liệu đã được poll. Không đặt high watermark bằng đúng sức chứa tối đa của queue nếu listener vẫn có thể nhận thêm record trước khi pause được áp dụng.

## 6. Resume listener container

Khi điều kiện khiến container pause đã được giải quyết, gọi `resume()` trên đúng container:

~~~java
public void resumeOrders() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container == null) {
        throw new IllegalStateException(
            "Không tìm thấy listener ordersListener"
        );
    }

    container.resume();
}
~~~

Sau khi resume, consumer thread áp dụng trạng thái resume và tiếp tục nhận record ở các poll kế tiếp. Không cần tạo lại container hoặc consumer group.

Có thể kiểm tra trạng thái yêu cầu và trạng thái consumer thực tế:

~~~java
public ListenerPauseStatus status(String listenerId) {
    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        return ListenerPauseStatus.NOT_FOUND;
    }

    if (container.isConsumerPaused()) {
        return ListenerPauseStatus.PAUSED;
    }

    if (container.isPauseRequested()) {
        return ListenerPauseStatus.PAUSE_REQUESTED;
    }

    return ListenerPauseStatus.RUNNING;
}
~~~

`isPauseRequested()` và `isConsumerPaused()` phản ánh hai thời điểm khác nhau. Có thể pause đã được yêu cầu nhưng consumer thread chưa áp dụng; monitoring nên thể hiện trạng thái trung gian thay vì báo đã pause hoàn toàn ngay khi method được gọi.

## 7. Pause và resume theo từng partition

Khi chỉ một partition có vấn đề, có thể dùng API partition-level thay vì pause toàn bộ listener container.

Ví dụ:

~~~java
public void pausePartition(
        String listenerId,
        TopicPartition topicPartition) {

    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        throw new IllegalArgumentException(
            "Không tìm thấy listener " + listenerId
        );
    }

    container.pausePartition(topicPartition);
}

public void resumePartition(
        String listenerId,
        TopicPartition topicPartition) {

    MessageListenerContainer container =
        registry.getListenerContainer(listenerId);

    if (container == null) {
        throw new IllegalArgumentException(
            "Không tìm thấy listener " + listenerId
        );
    }

    container.resumePartition(topicPartition);
}
~~~

Partition-level pause hữu ích khi một key/partition có downstream lỗi, dữ liệu cần điều tra hoặc tốc độ xử lý khác các partition còn lại. Các partition khác vẫn có thể tiếp tục xử lý.

Cần theo dõi assignment và rebalance. Partition chỉ được tiêu thụ bởi member đang sở hữu assignment; sau rebalance, trạng thái pause và quyền sở hữu partition phải được quan sát lại. Không giả định một partition luôn thuộc cùng child consumer hoặc cùng pod.

## 8. ConcurrentMessageListenerContainer và nhiều consumer

Khi listener có concurrency lớn hơn một, Spring Kafka tạo một `ConcurrentMessageListenerContainer` quản lý nhiều child container, mỗi child container có consumer riêng.

Ví dụ:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Nếu gọi `pause()` trên container cha lấy từ registry, yêu cầu pause áp dụng cho các consumer do container đó quản lý. Gọi `resume()` sẽ yêu cầu resume toàn bộ container theo lifecycle của nó.

Với pause partition, Spring Kafka tìm consumer đang quản lý partition đó. Assignment có thể thay đổi khi rebalance; cần xử lý trường hợp partition chưa được assign cho member hiện tại.

Không nên lấy child container ID bằng cách tự ghép hậu tố nếu không cần thiết. Dùng container cha và API quản lý được hỗ trợ để tránh phụ thuộc cấu trúc nội bộ của concurrent container.

## 9. Backpressure là gì và vì sao cần pause/resume?

Backpressure là cơ chế điều tiết tốc độ producer/consumer giữa các thành phần để hệ thống phía sau không bị quá tải. Trong Kafka consumer, một listener có thể nhận record nhanh hơn tốc độ database, HTTP API hoặc worker pool xử lý.

Nếu tiếp tục nhận dữ liệu trong khi downstream chậm:

- Queue nội bộ tăng liên tục.
- Memory có thể cạn.
- Request downstream timeout hoặc bị rate limit.
- Thread pool và connection pool bị chiếm hết.
- Độ trễ xử lý tăng và consumer lag có thể tăng theo.
- Khi process crash, dữ liệu chưa được xử lý có thể phải đọc lại.

Pause/resume cho phép listener container tạm dừng nhận thêm record khi hệ thống gần quá tải và tiếp tục khi backlog nội bộ giảm.

~~~mermaid
flowchart TD
    A[Kafka records] --> B[Listener container]
    B --> C[Bounded work queue]
    C --> D[Worker pool]
    D --> E[Database hoặc HTTP service]
    C --> F{Queue đạt high watermark?}
    F -->|Có| G[Pause container]
    G --> H[Workers tiếp tục drain queue]
    H --> I{Queue xuống low watermark?}
    I -->|Có| J[Resume container]
    J --> B
~~~

Pause/resume là tín hiệu điều khiển luồng tiêu thụ. Nó không thay thế queue bounded, giới hạn concurrency, retry hoặc idempotency.

## 10. High watermark và low watermark

Không nên pause/resume tại cùng một ngưỡng. Nếu queue dao động quanh một giá trị, container có thể pause rồi resume liên tục, tạo hiện tượng flapping.

Dùng hai ngưỡng:

- High watermark: khi queue đạt hoặc vượt ngưỡng, yêu cầu pause.
- Low watermark: chỉ resume khi queue giảm xuống dưới ngưỡng thấp hơn.

Ví dụ queue có sức chứa 1.000 công việc:

| Trạng thái | Điều kiện | Hành động |
| --- | --- | --- |
| RUNNING | Queue từ 0 đến dưới 800 | Tiếp tục nhận record. |
| PAUSE REQUESTED | Queue đạt 800 | Gọi pause container. |
| PAUSED | Queue còn cao hơn 300 | Tiếp tục drain queue, không nhận thêm. |
| RESUME REQUESTED | Queue xuống 300 hoặc thấp hơn | Gọi resume container. |

Ngưỡng phải tính cả record đã poll, listener đang chạy và công việc đang được đưa vào queue. Với nhiều partition hoặc nhiều consumer, queue capacity tổng thể có thể khác queue riêng của từng worker.

Nên bổ sung thời gian ổn định tối thiểu hoặc cooldown nếu tải thay đổi nhanh. Đừng dùng sleep trong listener để chờ queue giảm vì nó chặn consumer thread và có thể gây vấn đề poll interval.

## 11. Mẫu BackpressureController

Ví dụ controller theo dõi queue depth và điều khiển listener container:

~~~java
@Service
@RequiredArgsConstructor
public class BackpressureController {

    private static final int HIGH_WATERMARK = 800;
    private static final int LOW_WATERMARK = 300;

    private final KafkaListenerEndpointRegistry registry;

    public void updateQueueDepth(int queueDepth) {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            return;
        }

        if (queueDepth >= HIGH_WATERMARK
                && !container.isPauseRequested()) {
            container.pause();
            return;
        }

        if (queueDepth <= LOW_WATERMARK
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

Đây là khung minh họa. Trong production, queue depth nên lấy từ queue thực tế hoặc metric đáng tin cậy; controller cần được gọi khi depth thay đổi hoặc từ một scheduler nhẹ.

Cần phân biệt pause requested và consumer paused. Nếu có nhiều nguồn cùng điều khiển container, một nguồn có thể gọi resume trong khi nguồn khác vẫn cần pause. Hãy quản lý pause reason hoặc dùng một state coordinator để chỉ resume khi tất cả điều kiện pause đã được gỡ.

## 12. Tránh nhiều thành phần điều khiển pause xung đột

Một listener có thể cần pause vì nhiều lý do:

- Queue nội bộ đã gần đầy.
- Downstream database đang bảo trì.
- Rate limit của HTTP API bị chạm.
- Quản trị viên yêu cầu tạm ngừng.
- Circuit breaker đang mở.

Nếu mỗi thành phần gọi trực tiếp `pause()` và `resume()`, một thành phần có thể resume container trong khi lý do pause khác vẫn còn.

Dùng một coordinator lưu tập hợp pause reason:

~~~java
public enum PauseReason {
    QUEUE_FULL,
    DOWNSTREAM_UNAVAILABLE,
    RATE_LIMIT,
    OPERATOR_REQUEST
}
~~~

Quy tắc:

1. Khi có bất kỳ pause reason nào, container phải pause.
2. Khi tất cả pause reason đã được gỡ, container mới được resume.
3. Cập nhật state phải thread-safe.
4. Log lý do pause/resume và thời điểm thay đổi.
5. Khi ứng dụng restart, xác định lại trạng thái từ health/queue thực tế vì pause state trong memory không bền vững.

Đừng để một boolean chung bị ghi đè bởi nhiều luồng điều khiển độc lập. Tập hợp reason giúp giải thích tại sao container đang pause và tránh resume quá sớm.
## 13. Event quan sát trạng thái pause/resume

Spring Kafka phát application event khi consumer thực tế pause hoặc resume. Các event thường dùng gồm:

- `ConsumerPausedEvent`: consumer của container đã được pause.
- `ConsumerResumedEvent`: consumer của container đã được resume.
- `ConsumerPartitionPausedEvent`: partition đã được pause.
- `ConsumerPartitionResumedEvent`: partition đã được resume.

Có thể lắng nghe bằng Spring event listener:

~~~java
@Component
@Slf4j
public class KafkaContainerEventListener {

    @EventListener
    public void onConsumerPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: {}", event);
    }

    @EventListener
    public void onConsumerResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: {}", event);
    }

    @EventListener
    public void onPartitionPaused(ConsumerPartitionPausedEvent event) {
        log.info("Kafka partition paused: {}", event);
    }

    @EventListener
    public void onPartitionResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resumed: {}", event);
    }
}
~~~

Các event hữu ích để ghi metric và xác nhận consumer đã áp dụng yêu cầu pause/resume. Không coi việc gọi `container.pause()` là bằng chứng consumer đã pause; dùng event hoặc trạng thái `isConsumerPaused()` để theo dõi thực tế.

Event có thể được phát từ luồng xử lý container. Handler nên ngắn, không thực hiện truy vấn chậm hoặc chờ HTTP call đồng bộ. Nếu cần gửi telemetry ra ngoài, chuyển sang executor phù hợp và tránh làm block consumer thread.

## 14. Resume khi queue đã giảm tải

Controller cần nhận được tín hiệu queue đã giảm xuống dưới low watermark. Có thể gọi từ worker sau khi hoàn tất công việc hoặc từ scheduler đọc metric queue.

Ví dụ phương thức cập nhật:

~~~java
public void onWorkCompleted(int remainingQueueDepth) {
    backpressureController.updateQueueDepth(remainingQueueDepth);
}
~~~

Nếu queue được cập nhật đồng thời bởi nhiều worker, cần lấy depth theo cách thread-safe. Với queue không hỗ trợ snapshot chính xác, hãy dùng metric gần đúng có chủ đích và ngưỡng đủ rộng để tránh flapping.

Một cách tổ chức khác là để controller sở hữu cả queue và trạng thái pause. Khi worker lấy item ra, controller cập nhật depth và quyết định có resume hay không. Cách này tránh nhiều component tự tính và cập nhật trạng thái khác nhau.

Không resume chỉ vì một worker hoàn tất. Hãy kiểm tra queue đã xuống dưới low watermark và mọi pause reason đã được gỡ.

## 15. Những record đã poll và queue nội bộ

Pause ngăn việc nhận record mới ở các poll tiếp theo, nhưng không xóa dữ liệu đã được poll. Đây là điểm rất quan trọng khi kết hợp listener với queue hoặc worker pool.

Giả sử một poll trả về 200 record. Khi queue vượt high watermark ở record thứ 50, container có thể vẫn phải hoàn tất việc dispatch các record còn lại từ poll đó trước khi pause có hiệu lực, tùy listener mode và cấu hình pause immediate. Nếu queue chỉ còn chỗ cho 10 record, các record còn lại có thể làm queue vượt capacity.

Cách thiết kế:

- Dùng bounded queue có capacity dự phòng cho dữ liệu in-flight.
- Đặt high watermark thấp hơn capacity thực tế.
- Giới hạn `max.poll.records` để kiểm soát kích thước poll.
- Giới hạn concurrency của worker pool và số tác vụ đang chạy.
- Theo dõi số record đang được listener xử lý ngoài queue.
- Xem xét pause immediate nếu phiên bản và listener mode hỗ trợ, sau khi kiểm thử.

Không dùng queue vô hạn rồi hy vọng pause sẽ bảo vệ memory. Pause có độ trễ áp dụng và không thể thu hồi record đã fetch.

## 16. Ack và độ bền của công việc bất đồng bộ

Một lỗi phổ biến là listener đưa record vào in-memory queue rồi return ngay:

~~~java
@KafkaListener(topics = "order-events", groupId = "order-workers")
public void onOrderEvent(OrderEvent event) {
    workQueue.offer(event);
}
~~~

Nếu container commit offset khi listener return, Kafka có thể coi record đã xử lý dù worker chưa hoàn tất. Nếu process crash, item còn trong memory có thể mất trong khi offset đã tiến.

Pause/resume không sửa được vấn đề durability này. Cần xác định rõ thời điểm record được xem là đã được nhận trách nhiệm xử lý:

- Nếu xử lý đồng bộ trong listener, để listener return sau khi công việc bền vững hoàn tất.
- Nếu handoff sang queue, chỉ xác nhận offset sau khi công việc được lưu bền vững hoặc đã hoàn tất theo contract.
- Nếu dùng manual acknowledgment cho worker bất đồng bộ, cấu hình AckMode và async acknowledgment đúng phiên bản; kiểm thử thứ tự ack, rebalance và shutdown.
- Nếu cần queue bền vững, dùng Kafka topic khác, database inbox/outbox hoặc durable work queue thay cho in-memory queue.

Không gọi acknowledgment ngay sau khi enqueue vào queue RAM nếu ứng dụng không chấp nhận mất công việc khi process restart.

## 17. Pause và max.poll.interval.ms

Pause container không thay thế việc kiểm soát thời gian xử lý listener. Kafka consumer phải tiếp tục poll trong giới hạn cấu hình; nếu listener block quá lâu và consumer không poll kịp, group có thể xem member là không còn hoạt động và rebalance.

Cần theo dõi:

- `max.poll.interval.ms`: giới hạn thời gian giữa các lần poll.
- `max.poll.records`: số record tối đa trả về trong một poll.
- Thời gian listener xử lý record/batch.
- Queue depth và số công việc in-flight.
- Thời gian pause thực tế và khoảng thời gian chờ resume.

Nếu listener thực hiện xử lý đồng bộ quá lâu, tăng max.poll.interval.ms có thể là một phần giải pháp nhưng không thay thế tối ưu công việc hoặc giới hạn batch. Nếu dùng worker pool bất đồng bộ, phải thiết kế acknowledgment và giới hạn in-flight riêng.

Trong trạng thái pause đúng cách, container tiếp tục poll để giữ consumer sống. Nhưng một thread bị kẹt trong listener không thể thực hiện vòng poll chỉ vì ứng dụng đã gọi pause từ thread khác.

## 18. Pause khi downstream lỗi hoặc circuit breaker mở

Pause/resume có thể phối hợp với circuit breaker để giảm áp lực lên dependency đang lỗi.

Ví dụ luồng điều khiển:

1. Circuit breaker phát hiện tỷ lệ lỗi hoặc timeout vượt ngưỡng.
2. Backpressure coordinator thêm pause reason DOWNSTREAM_UNAVAILABLE.
3. Container pause và không nhận thêm record mới.
4. Worker hiện tại hoàn tất hoặc thất bại theo timeout/retry policy.
5. Circuit breaker chuyển sang trạng thái half-open và cho phép probe.
6. Khi dependency phục hồi, coordinator gỡ pause reason.
7. Nếu không còn pause reason khác, container resume.

Không pause tất cả consumer một cách mù quáng nếu chỉ một downstream hoặc một loại event bị ảnh hưởng. Có thể tách listener theo workload hoặc pause partition phù hợp nếu topology cho phép.

Nếu downstream đang lỗi vĩnh viễn do dữ liệu sai, pause toàn container chỉ làm lag tăng mà không giải quyết nguyên nhân. Với lỗi record cụ thể, dùng retry hữu hạn, DLT và xử lý poison record.

## 19. Pause/resume qua API quản trị

Có thể expose thao tác pause/resume qua một service quản trị nội bộ hoặc actuator endpoint tùy kiến trúc ứng dụng. Nếu làm vậy:

- Chỉ cho phép principal có quyền vận hành phù hợp.
- Không public endpoint điều khiển consumer ra Internet.
- Validate listener ID và partition trước khi thao tác.
- Ghi audit log gồm actor, lý do, thời gian và trạng thái trước/sau.
- Có timeout hoặc cảnh báo nếu listener pause quá lâu.
- Cung cấp thao tác resume an toàn khi operator quên gỡ pause.
- Không trả thành công chỉ vì đã gửi yêu cầu; phân biệt REQUESTED với APPLIED.

Ví dụ service có thể cung cấp hai operation pause và resume, còn controller REST chỉ kiểm tra quyền và gọi service. Không để controller trực tiếp truy cập KafkaConsumer.

## 20. Pause state và vòng đời ứng dụng

Pause state do listener container quản lý trong runtime. Nó không phải cấu hình bền vững trong Kafka broker. Khi process restart, container mới khởi động theo lifecycle và cấu hình ban đầu; ứng dụng phải đánh giá lại có cần pause dựa trên queue, dependency health hoặc trạng thái điều khiển bên ngoài.

`resume()` không phải là `start()`. Nếu container đã stop, resume không khởi động consumer. Hãy kiểm tra `isRunning()` và dùng lifecycle start/stop đúng mục đích.

Khi shutdown:

- Ngừng nhận công việc mới theo lifecycle.
- Chờ listener/worker đang chạy trong thời gian grace period phù hợp.
- Xử lý acknowledgment theo contract.
- Không đánh dấu queue RAM là đã hoàn tất nếu công việc chưa bền vững.
- Để container đóng consumer có trật tự.

Khi startup, dựng queue/worker trước khi listener nhận record; nếu downstream chưa sẵn sàng, có thể giữ container ở trạng thái pause sau khi khởi động hoặc điều khiển theo readiness. Phải có cơ chế resume khi dependency sẵn sàng.

## 21. Theo dõi và cảnh báo pause lâu

Pause quá lâu làm consumer lag tăng và có thể khiến SLA xử lý không đạt. Monitoring nên có:

- Trạng thái container: running, pause requested, paused.
- Thời điểm pause và thời lượng pause.
- Lý do pause đang còn hiệu lực.
- Queue depth, queue capacity và số worker in-flight.
- Consumer lag theo group/topic/partition.
- Số lần pause/resume trong một khoảng thời gian.
- Downstream latency, error rate và circuit breaker state.
- Partition-level pause state nếu sử dụng.
- Số record đã poll nhưng chưa hoàn tất.

Đặt cảnh báo khi container pause vượt thời gian dự kiến, queue không giảm dù đã pause hoặc consumer lag tăng quá ngưỡng. Nếu pause/resume diễn ra liên tục, xem lại high/low watermark và tốc độ worker thay vì tăng tần suất polling trạng thái.

## 22. Kiểm thử pause và resume

Integration test nên xác nhận trạng thái consumer và record delivery với Kafka thật hoặc Embedded Kafka phù hợp phiên bản.

Các kịch bản:

1. Start listener container và xác nhận record được xử lý.
2. Gọi pause và chờ consumer thực sự paused.
3. Gửi thêm record trong lúc pause và xác nhận listener chưa xử lý chúng.
4. Gọi resume và xác nhận record đang chờ được xử lý tiếp.
5. Pause một partition và xác nhận partition khác vẫn tiếp tục.
6. Dùng concurrent container và xác nhận pause toàn container áp dụng cho các child consumer.
7. Gọi pause trong khi poll hiện tại còn record và xác nhận số record in-flight phù hợp cấu hình.
8. Gọi resume khi container đang stop và xác nhận nó không tự start.
9. Mô phỏng queue đạt high watermark rồi giảm xuống low watermark; xác nhận không flapping.
10. Kiểm tra listener handoff sang queue không commit offset trước khi công việc bền vững theo contract.
11. Restart application khi pause và xác nhận startup policy khôi phục trạng thái mong muốn.
12. Theo dõi event ConsumerPausedEvent/ConsumerResumedEvent nếu ứng dụng dùng chúng.

Dùng latch, Awaitility hoặc điều kiện trạng thái có timeout. Tránh sleep cố định vì thời điểm pause được áp dụng phụ thuộc consumer thread và poll cycle. Test nên phân biệt pause requested với consumer paused thực tế.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Gọi pause nhưng listener vẫn nhận thêm vài record | Record đã được poll trước khi pause có hiệu lực | Tính in-flight, giảm max.poll.records hoặc kiểm tra pauseImmediate |
| Gọi resume nhưng listener không chạy | Container đang stop, listener ID sai hoặc consumer chưa áp dụng resume | Kiểm tra registry, isRunning và trạng thái pause |
| Consumer rời group khi pause lâu | Consumer thread bị block hoặc poll không tiếp tục | Kiểm tra listener duration và max.poll.interval.ms |
| Queue vẫn tăng sau khi pause | Record in-flight hoặc listener vẫn enqueue dữ liệu đã poll | Dùng queue bounded và dự phòng poll batch |
| Công việc mất sau restart | Listener đã commit offset sau khi enqueue vào RAM | Dùng durable handoff/manual ack đúng semantics |
| Container resume quá sớm | Nhiều thành phần điều khiển pause độc lập | Dùng pause reason coordinator |
| Pause/resume liên tục | Dùng một watermark hoặc ngưỡng quá sát | Dùng high/low watermark và cooldown |
| Pause toàn container ảnh hưởng partition khỏe | Dùng pause thay vì partition-level pause | Pause đúng partition nếu phù hợp |
| Pause state mất sau deploy | State chỉ tồn tại trong runtime | Khôi phục theo policy từ health/queue/control store |
| Không thấy metric pause thực tế | Chỉ ghi log lúc gọi API | Theo dõi consumer pause/resume events và trạng thái thực tế |

## 24. Checklist vận hành

Trước khi đưa pause/resume vào production, hãy xác nhận:

1. Listener có ID ổn định để registry tìm đúng container.
2. Dùng API container thay vì gọi KafkaConsumer từ thread ngoài.
3. Phân biệt pause/resume với stop/start.
4. Hiểu pause có hiệu lực theo poll cycle và record in-flight.
5. Queue có giới hạn capacity và high watermark có khoảng dự phòng.
6. Có low watermark thấp hơn high watermark.
7. Có coordinator khi nhiều lý do cùng yêu cầu pause.
8. Consumer thread vẫn poll và listener không block quá lâu.
9. max.poll.interval.ms và max.poll.records phù hợp workload.
10. Acknowledgment không được thực hiện trước khi công việc đạt durability contract.
11. Partition-level pause được dùng khi chỉ một partition cần điều tiết.
12. Concurrent container được quản lý qua container cha hoặc API phù hợp.
13. Pause/resume event và duration được quan sát.
14. Có cảnh báo khi pause quá lâu hoặc lag tăng.
15. Startup/shutdown policy xác định cách khôi phục pause state.
16. Integration test cover pause, resume, in-flight records, queue và restart.

`resume()` tiếp tục tiêu thụ trên listener container đã được pause; nó không tạo consumer mới và không thay thế lifecycle start. Kết hợp pause/resume với queue bounded, high/low watermark và pause reason coordinator giúp điều tiết tải mà vẫn giữ consumer trong group. Để tránh mất công việc, cần tính đến record đã poll, acknowledgment, thread xử lý và độ bền của queue trước khi dùng pause làm cơ chế backpressure.



