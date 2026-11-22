# Pause listener container

Trong Spring Kafka, **pause listener container** là cơ chế tạm ngừng việc giao thêm record tới listener trong khi container và Kafka consumer vẫn chạy. Ứng dụng có thể gọi `pause()` khi database hoặc API phụ trợ đang quá tải, rồi gọi `resume()` khi hệ thống đủ năng lực tiếp tục xử lý. Đây là một công cụ quan trọng để triển khai **backpressure**: giảm tốc độ nhận đầu vào từ Kafka thay vì để hàng nghìn thao tác đồng loạt gây áp lực lên downstream.

Điểm cần nắm rõ: **pause không phải stop, không phải retry, và không có nghĩa record hiện tại đã được xử lý thành công**. Container còn chạy, thường tiếp tục gọi `poll()` để duy trì consumer group. Những record đã giao tới listener hoặc đã được poll trước khi yêu cầu pause có thể vẫn đang xử lý. Offset và tác động nghiệp vụ phải tiếp tục được quản lý theo ack mode, error handler và transaction hiện hành.

## 1. Vì sao cần pause trong hệ thống có backpressure?

Giả sử topic `orders` nhận 2.000 events/giây. Consumer ghi kết quả vào database, nhưng connection pool chỉ đáp ứng được 500 writes/giây khi database đang gặp sự cố. Nếu listener tiếp tục nhận records mà không điều tiết:

- Số request đang chờ connection tăng, gây timeout hoặc thread starvation.
- Lỗi transient xuất hiện hàng loạt rồi kích hoạt retry, tạo thêm tải.
- Consumer có nguy cơ giữ thread xử lý quá lâu, ảnh hưởng `max.poll.interval.ms`.
- Downstream queue hoặc executor có thể phình to và dẫn đến OOM.
- Record bị chuyển DLT hàng loạt dù chúng có thể thành công sau khi database phục hồi.

Pause cho phép tạm giảm intake ở nguồn, trong khi các records mới vẫn được Kafka broker lưu theo retention policy.

~~~mermaid
flowchart LR
    K["Kafka orders topic"] --> C["Spring Kafka listener container"]
    C --> L["Business listener"]
    L --> DB["Database / HTTP downstream"]
    DB --> M{"Downstream còn capacity?"}
    M -->|Không| P["Yêu cầu pause container"]
    M -->|Có| R["Resume container"]
    P -. "Consumer vẫn poll" .-> C
    R -. "Xử lý tiếp backlog" .-> C
~~~

Đây là backpressure theo kiểu **tạm ngừng nhận đầu vào**. Nó không tự mở rộng database, không chuyển partition cho consumer khác và không tự khôi phục dữ liệu lỗi.

## 2. Pause khác stop ở những điểm nào?

| Tiêu chí | `pause()` | `stop()` |
|---|---|---|
| Container lifecycle | Vẫn đang chạy | Dừng container |
| Consumer poll loop | Tiếp tục poll theo cơ chế container | Kết thúc khi stop hoàn tất |
| Consumer group | Thường giữ membership nhờ tiếp tục poll | Consumer có thể rời group, gây reassignment |
| Partition assignment | Không nhả partition chỉ vì pause | Partition có thể được group gán lại |
| Giao record cho listener | Tạm dừng sau khi pause có hiệu lực | Chấm dứt khi container dừng |
| Tiếp tục | `resume()` | `start()` |
| Mục tiêu | Backpressure hoặc tạm dừng ngắn hạn | Shutdown, deploy, ngừng lifecycle |

Pause không phải cơ chế **failover**. Nếu pod A bị pause nhưng vẫn giữ partition 2, pod B cùng group không tự nhận partition 2 chỉ vì pod A đang pause. Nếu muốn chuyển workload sang member khác, cần xem xét lifecycle/rebalance với chiến lược rõ ràng.

## 3. API pause/resume của MessageListenerContainer

Các listener containers trong Spring Kafka cung cấp API điều khiển:

~~~java
container.pause();
container.resume();

boolean requested = container.isPauseRequested();
boolean effective = container.isConsumerPaused();
~~~

Hai trạng thái này khác nhau:

- `isPauseRequested()` biểu thị đã có yêu cầu pause.
- `isConsumerPaused()` biểu thị consumer đã áp dụng pause; với concurrent container, cần hiểu trạng thái tổng hợp của các child consumers.

Gọi `pause()` không nhất thiết lập tức dừng mọi listener invocation. Container nhận yêu cầu và áp dụng ở điểm an toàn trong chu trình poll/dispatch. Ở thời điểm đó, những record đã poll có thể vẫn còn đang chờ xử lý.

~~~text
T0  poll() trả về records
T1  listener bắt đầu xử lý record A
T2  operator gọi pause()
T3  isPauseRequested() = true
T4  listener có thể hoàn tất record/batch đã giao
T5  consumer thực sự pause partition
T6  isConsumerPaused() = true
T7  poll tiếp tục nhưng không dispatch thêm record paused
T8  operator gọi resume()
T9  consumer tiếp tục xử lý từ vị trí tương ứng
~~~

Vì vậy, hệ thống vận hành cần phân biệt **đã yêu cầu pause** với **đã thực sự pause**. Nếu mục tiêu là thay đổi database schema trong lúc không còn transaction đang chạy, cần theo dõi in-flight work riêng; chỉ thấy `pause()` trả về chưa đủ.

## 4. Consumer vẫn poll khi đã pause

Kafka consumer cần tiếp tục tham gia vòng đời group. Việc gọi `Thread.sleep(120_000)` trong listener để “nghỉ hai phút” không tương đương với pause container. Nếu application không poll trong thời gian quá dài, nó có thể vượt `max.poll.interval.ms` và bị coi là không tiến hành polling phù hợp, dẫn đến rebalance.

Spring Kafka container pause sử dụng khả năng pause/resume của Kafka consumer nhưng vẫn chủ động poll để duy trì membership.

~~~text
RUNNING
  poll -> process -> poll -> process -> poll

PAUSED
  poll -> no records from paused partitions -> poll -> poll

BLOCKED THREAD (không nên dùng thay pause)
  poll -> Thread.sleep quá dài -> không poll kịp
~~~

Pause giúp tránh một nguyên nhân dẫn đến rebalance, nhưng **không bảo đảm consumer group sẽ không bao giờ rebalance**. Network outage, broker/coordinator issues, member join/leave và các tình huống khác vẫn có thể thay đổi partition assignment.

## 5. Định danh listener để điều khiển đúng container

Một listener có `id` ổn định:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-projection")
    public void onMessage(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

`KafkaListenerEndpointRegistry` quản lý các container được tạo thông qua `@KafkaListener`. Registry chỉ chứa containers trong **JVM hiện tại**. Nếu dịch vụ chạy năm pods, gọi registry trên một pod chỉ điều khiển container ở pod đó; muốn pause toàn bộ consumer group cần điều phối tất cả instances liên quan.

Với container được tạo thủ công, ứng dụng có thể giữ reference đến container trực tiếp, thay vì tra theo registry.

## 6. Dịch vụ pause và resume bằng KafkaListenerEndpointRegistry

Ví dụ Java:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaIntakeControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaIntakeControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        require("orders-listener").pause();
    }

    public void resumeOrders() {
        require("orders-listener").resume();
    }

    public String ordersStatus() {
        MessageListenerContainer container = require("orders-listener");

        if (!container.isRunning()) {
            return "STOPPED";
        }
        if (container.isConsumerPaused()) {
            return "PAUSED";
        }
        if (container.isPauseRequested()) {
            return "PAUSE_REQUESTED";
        }
        return "RUNNING";
    }

    private MessageListenerContainer require(String id) {
        MessageListenerContainer container = registry.getListenerContainer(id);
        if (container == null) {
            throw new IllegalArgumentException(
                "Kafka container not registered: " + id
            );
        }
        return container;
    }
}
~~~

Đây là API điều khiển trong application. Nếu expose qua HTTP, actuator hoặc admin command, cần xác thực, phân quyền và audit. Không mở public endpoint cho phép người bất kỳ pause toàn bộ consumer group vì thao tác này có thể làm backlog tăng và vi phạm SLO.

Khi container đang `STOPPED`, gọi `resume()` không thay thế `start()`. `resume` chỉ có ý nghĩa trong cơ chế pause của container đang chạy.

## 7. Yêu cầu pause có thể chưa được áp dụng ngay

Spring Kafka có sự khác biệt giữa thời điểm operator gọi pause và thời điểm consumer thread áp dụng nó:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant C as Listener container
    participant L as Listener
    participant K as Kafka consumer
    K-->>C: Poll records
    C->>L: Xử lý record A
    O->>C: pause()
    Note over C: isPauseRequested = true
    L-->>C: Hoàn tất record đang xử lý
    C->>K: Pause assigned partitions
    Note over C: isConsumerPaused = true
    O->>C: resume()
    C->>K: Resume partitions
~~~

Với concurrency lớn, nhiều child consumers có thể áp dụng pause ở những thời điểm khác nhau. Nếu cần đo “đã pause toàn bộ”, hãy quan sát trạng thái effective và các application events theo container, không chỉ ghi nhận một lệnh gọi.

Pause cũng không can thiệp một transaction DB đã mở hay một HTTP request đang chạy. Đối với maintenance cần drain in-flight work, hãy đo số thao tác chưa hoàn tất trước khi chuyển sang bước bảo trì.

## 8. Thuộc tính pauseImmediate

Trong các phiên bản Spring Kafka hỗ trợ `ContainerProperties#setPauseImmediate`, có thể yêu cầu pause sau khi xử lý **record hiện tại**, thay vì hoàn tất toàn bộ records từ lần poll trước rồi mới pause.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setPauseImmediate(true);
    return factory;
}
~~~

Với `pauseImmediate = true`, lượng records bắt đầu xử lý sau yêu cầu pause có thể thấp hơn, đặc biệt khi `max.poll.records` lớn.

Tuy nhiên:

- Record đang được listener xử lý không tự bị cancel.
- Pause không làm rollback DB transaction hiện tại.
- Với batch listener, semantics khác record listener vì method có thể nhận nguyên một batch.
- Những records đã fetch vẫn được container quản lý; pause không làm chúng biến mất.

Trước khi dùng, cần đối chiếu API và hành vi với phiên bản Spring Kafka của dự án.

## 9. Pause một partition thay vì toàn bộ container

Có trường hợp chỉ một partition cần chờ, nhưng những partition khác vẫn có thể xử lý. Spring Kafka ở các phiên bản hỗ trợ có API pause/resume ở cấp partition:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container == null) {
    throw new IllegalStateException("orders-listener not found");
}

TopicPartition target = new TopicPartition("orders", 2);

container.pausePartition(target);

// Khi downstream dành cho partition này phục hồi:
container.resumePartition(target);
~~~

Cần lưu ý:

1. Container phải có assignment phù hợp để pause partition dự kiến.
2. Với concurrent container, một child consumer cụ thể sở hữu partition đó.
3. Rebalance có thể làm assignment đổi; cách duy trì/yêu cầu lại pause phụ thuộc API và phiên bản.
4. Nếu business tenant có records nằm trên nhiều partitions, pause một partition không đủ để dừng tenant.
5. Consumer lag của partition paused cần được giám sát riêng.

Không dùng partition pause như một ACL security hoặc một bảo đảm dừng hoàn toàn xử lý business key khi producer có thể gửi cùng key sang nhiều partition do thay đổi partition strategy.

## 10. Tự động backpressure theo downstream health

Một mô hình phổ biến là control loop định kỳ kiểm tra connection pool và queue depth, rồi pause/resume listener:

~~~java
@Component
public class KafkaBackpressureMonitor {

    private final KafkaListenerEndpointRegistry registry;
    private final DependencyCapacityProbe capacityProbe;

    public KafkaBackpressureMonitor(
            KafkaListenerEndpointRegistry registry,
            DependencyCapacityProbe capacityProbe) {
        this.registry = registry;
        this.capacityProbe = capacityProbe;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void reconcile() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        boolean canConsume = capacityProbe.canAcceptMoreWork();

        if (!canConsume && !container.isPauseRequested()) {
            container.pause();
        } else if (canConsume && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

Trong ví dụ:

- `DependencyCapacityProbe` là interface do ứng dụng định nghĩa.
- `@Scheduled` cần scheduling được bật bằng `@EnableScheduling` trong configuration.
- Listener không tự sleep để chờ database.
- Scheduler control không chặn consumer thread.

Control loop production cần **hysteresis**. Ví dụ pause khi downstream queue depth vượt 5.000 trong 10 giây, nhưng chỉ resume khi queue xuống dưới 1.000 liên tục 30 giây. Những ngưỡng này chỉ minh họa; cần đo năng lực thực tế để chọn.

Không đặt cùng một ngưỡng pause và resume rồi để ứng dụng dao động liên tục giữa hai trạng thái. Hiện tượng này gọi là pause/resume flapping và có thể làm throughput khó dự đoán.

## 11. Manual pause và auto pause cần có quyền ưu tiên rõ ràng

Một thiết kế nguy hiểm: operator pause để bảo trì database, nhưng health monitor thấy database “healthy” nên tự gọi resume. Kết quả là intake hoạt động lại trước khi maintenance hoàn tất.

Có thể quản lý các **pause reasons** trong control plane:

~~~text
Pause reasons:
  MANUAL_MAINTENANCE
  DATABASE_OVERLOADED
  DOWNSTREAM_CIRCUIT_OPEN
  RATE_LIMIT_EXCEEDED

Nếu còn ít nhất một active reason -> giữ pause.
Chỉ resume khi tất cả reasons đã được clear.
~~~

Đây là logic orchestration của ứng dụng, không phải một cơ chế idempotent pause-reason có sẵn trong mọi phiên bản Spring Kafka. Cần lưu trạng thái điều khiển ở nơi phù hợp, tránh một scheduler vô tình phủ quyết quyết định của operator.

Với nhiều pods, hệ thống control cần phân phối hoặc đồng bộ lệnh theo instance; một JVM registry không tác động tới các JVM khác.

## 12. Pause không thay thế retry và error handler

Một lỗi nghiêm trọng là bắt exception trong listener, gọi pause, rồi return bình thường:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (DatabaseUnavailableException ex) {
        intakeControl.pauseOrders();
        // Sai nếu return bình thường khi DB write chưa hoàn tất.
    }
}
~~~

Trong tình huống này, container có thể coi record đã xử lý thành công và commit offset. Pause không đảo ngược chuyện đó.

Để thông báo record chưa xử lý xong:

~~~java
@KafkaListener(id = "orders-listener", topics = "orders")
public void handle(OrderEvent event) {
    try {
        orderService.apply(event);
    } catch (DatabaseUnavailableException ex) {
        intakeControl.pauseOrders();
        throw ex; // Đưa lỗi lên Kafka error handling.
    }
}
~~~

Lưu ý: đoạn code là ví dụ; việc tự pause trong lúc error handler muốn retry có thể gây tương tác phức tạp. Cần thống nhất backpressure monitor với cơ chế retry để tránh record lỗi bị giữ vô thời hạn.

Với poison record hoặc payload sai định dạng, pause toàn container thường không thích hợp: record đó không tự trở nên hợp lệ theo thời gian. Hãy phân loại non-retryable và xử lý DLT/quarantine. Pause phù hợp khi **năng lực xử lý tổng thể** của dependency đang thiếu.

## 13. Pause và error-handler backoff

`DefaultErrorHandler` có thể retry một record với `BackOff`. Với khoảng nghỉ dài, Spring Kafka cung cấp cơ chế `ContainerPausingBackOffHandler` ở những phiên bản phù hợp để phối hợp pause/resume container thay vì chỉ giữ consumer thread sleep dài.

Khái niệm:

~~~text
Listener xử lý record A -> exception
    |
    v
Error handler tính backoff
    |
    v
Container-pausing backoff
    |
    +--> Pause container / poll để duy trì membership
    |
    +--> Đến hạn -> resume và retry A
~~~

Đây là **blocking retry được điều phối qua pause**, không phải non-blocking retry topic. Non-blocking retry chuyển record sang Kafka topic khác, có offset mới và có thể làm đảo thứ tự xử lý.

API khởi tạo `ContainerPausingBackOffHandler` phụ thuộc phiên bản Spring Kafka, scheduler và error handler; cần đối chiếu dự án cụ thể. Không thay cơ chế này bằng `Thread.sleep` dài trong listener.

Nếu container vừa có retry backoff pause vừa có manual pause, cần xử lý sở hữu trạng thái pause rõ ràng. Nếu hai nguồn điều khiển gọi resume không phối hợp, consumer có thể tiếp tục intake trong lúc operator vẫn muốn dừng.

## 14. Pause có thể làm consumer lag tăng

Trong khi consumer pause, producer vẫn gửi event vào topic. Backlog có thể tăng:

~~~text
Producer arrival: 2.000 records/giây
Pause duration: 60 giây

Records mới xấp xỉ: 120.000
Consumer lag có thể tăng tương ứng.
~~~

Khi resume, cần tính **backlog drain rate**:

~~~text
Producer tiếp tục: 2.000 records/giây
Consumer sau resume: 3.000 records/giây
Tốc độ giảm backlog: 1.000 records/giây

Backlog 120.000 records cần khoảng 120 giây để bắt kịp
(theo mô hình lý tưởng, không tính overhead và lỗi).
~~~

Nếu downstream chỉ chịu được 2.000 records/giây, resume không thể nhanh chóng làm backlog giảm vì tốc độ vào gần bằng tốc độ xử lý. Cần capacity planning, tách workload, tăng tài nguyên hoặc ưu tiên luồng nghiệp vụ phù hợp.

Lag tăng trong một maintenance pause được phê duyệt có thể là **đúng thiết kế**, nhưng vẫn cần alert nếu duration hoặc backlog vượt ngân sách SLO.

## 15. Retention và nguy cơ mất dữ liệu khi pause lâu

Kafka broker áp dụng retention theo topic, không dựa vào trạng thái pause của consumer. Nếu pause kéo dài nhiều giờ/ngày trong khi topic có retention ngắn, một phần record chưa được tiêu thụ có thể bị xóa trước khi consumer resume.

Cần xem:

- `retention.ms` và `retention.bytes`.
- Tốc độ producer và số lượng partitions.
- Dung lượng disk, replication và khả năng chịu tải Kafka cluster.
- Thời gian pause tối đa theo SLO.
- Tuổi record chưa xử lý và dự báo thời gian bắt kịp.
- Kế hoạch replay/restore nếu retention đã làm mất record.

Đừng hứa rằng pause “không bao giờ gây mất dữ liệu”. Bản thân pause không xóa record, nhưng một backlog quá lâu có thể không còn nằm trong thời gian lưu giữ của Kafka topic.

## 16. Concurrency và child containers

`ConcurrentMessageListenerContainer` có thể tạo nhiều child Kafka consumers. Khi gọi `pause()` ở container cha, Spring Kafka điều phối yêu cầu tới các child consumers.

~~~text
Concurrent container: concurrency = 3
  |
  +-- Child A: partitions 0 và 3
  +-- Child B: partitions 1 và 4
  +-- Child C: partitions 2 và 5

parent.pause()
  -> Yêu cầu pause các child consumers.
~~~

Vì mỗi child poll và xử lý tại thời điểm riêng, trạng thái pause có thể đạt hiệu lực không đồng thời. Để biết tất cả consumer đã pause, dùng trạng thái container tương ứng hoặc application events, không chỉ xem một log từ child A.

Nếu chỉ muốn giảm throughput thay vì ngừng tất cả intake, có thể cân nhắc các chiến lược khác:

- Giới hạn `max.poll.records`.
- Giảm concurrency với kế hoạch rebalance phù hợp.
- Dùng bounded work queue và rate limiter.
- Pause theo partition khi có điều kiện độc lập.
- Chia topics theo mức ưu tiên hoặc SLO.

Việc thay đổi concurrency/assignment có thể gây rebalance; không dùng scale up/down liên tục để mô phỏng pause vài giây.

## 17. Quan sát bằng application events

Spring Kafka phát một số application events liên quan tới pause/resume theo phiên bản, ví dụ `ConsumerPausedEvent` và `ConsumerResumedEvent`. Có thể đăng ký listener để ghi nhận sự kiện:

~~~java
@Component
public class KafkaPauseEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaPauseEventLogger.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info("Kafka consumer paused: {}", event);
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info("Kafka consumer resumed: {}", event);
    }
}
~~~

Ngoài container-level events, một số phiên bản còn có events cho partition-level pause/resume. Tên event và chi tiết getter cần đối chiếu API đang dùng.

Log vận hành nên bổ sung listener ID, instance ID, nguyên nhân pause, requester, timestamp và thời điểm resume. Nếu muốn biết partition chính xác, đọc event data hoặc container API, không chỉ dựa vào một chuỗi toString.

## 18. Những metrics quan trọng

| Metric | Câu hỏi vận hành |
|---|---|
| Container `isRunning` / `isPauseRequested` / `isConsumerPaused` | Đã stop, đang yêu cầu pause hay đã pause thật? |
| Pause duration | Container có bị quên resume không? |
| Consumer lag theo topic/partition | Backlog tăng bao nhiêu? |
| Oldest unprocessed age | Có sắp vi phạm SLO/retention không? |
| Downstream queue depth | Có cần pause/resume không? |
| DB connection pool utilization | Database đang thiếu capacity? |
| Retry/error/DLT count | Pause có giảm lỗi hay chỉ che lỗi? |
| Pause/resume transitions | Control loop có bị flapping không? |
| Consumer group rebalance count | Group còn ổn định không? |
| End-to-end processing latency | Business event bị trì hoãn bao lâu? |

Một metric `paused=1` không đủ để xác định Kafka đã lỗi. Phải có bối cảnh: pause được yêu cầu bởi hệ thống backpressure hay operator, và trạng thái downstream tương ứng.

Với nhiều pods, đo theo instance/container hoặc phân tích toàn consumer group. Event ID nên nằm trong log/trace; không dùng event ID làm metric label do cardinality quá lớn.

## 19. Pause không có nghĩa không còn in-flight work

Một số tác động vẫn có thể xảy ra sau khi operator yêu cầu pause:

- Listener đang xử lý record hoặc batch đã nhận.
- HTTP request đã gửi sang downstream.
- Database transaction đã mở.
- Async task được submit bởi listener.
- Manual ack đang chờ thực hiện.
- Kafka transaction đang xử lý output.

Nếu cần maintenance an toàn, hãy kết hợp:

1. Yêu cầu pause.
2. Đợi trạng thái effective pause.
3. Đo số in-flight operations.
4. Đợi in-flight về 0 hoặc xử lý timeout/drain theo chính sách.
5. Thực hiện thay đổi.
6. Kiểm tra downstream capacity.
7. Resume có kiểm soát.

Không nhầm pause với một transactional barrier có thể rollback hoặc hủy công việc đã bắt đầu.

## 20. Offset và manual acknowledgment

Ví dụ listener dùng manual acknowledgment:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    containerFactory = "manualAckListenerFactory")
public void onMessage(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment ack) {

    orderService.apply(record.value());
    ack.acknowledge();
}
~~~

Acknowledgment chỉ nên xảy ra sau khi side effect bắt buộc hoàn tất theo semantics nghiệp vụ. Pause trước/sau một ack không tự thay đổi ý nghĩa của `ack.acknowledge()`.

Nếu listener đã báo thành công nhưng DB write chưa commit, Kafka offset có thể được xác nhận quá sớm. Ngược lại, nếu DB write commit rồi Kafka offset chưa commit, record có thể được giao lại. Cần idempotency hoặc inbox cho DB write.

Đối với container transaction, pause không tự commit/abort transaction đang mở. Kafka offset, output và rollback vẫn theo transaction manager cùng error-handling flow đã cấu hình.

## 21. Phân biệt pause với lỗi một record

| Tình huống | Hướng phù hợp |
|---|---|
| Database connection pool cạn diện rộng | Pause hoặc điều tiết container; monitor để resume |
| API downstream báo rate limit kéo dài | Backpressure, rate limiter, cân nhắc pause |
| Một JSON payload hỏng | Non-retryable classification và DLT/quarantine |
| Một event vi phạm quy tắc nghiệp vụ | Error handler theo loại lỗi, không pause mọi event |
| Lỗi mạng ngắn vài trăm milliseconds | Retry/backoff nhỏ có thể đơn giản hơn pause |
| Maintenance database có kiểm soát | Pause và drain in-flight trước maintenance |
| Muốn nhả partitions cho pod khỏe hơn | Stop/rebalance theo kế hoạch, không chỉ pause |
| Retry chờ nhiều phút, vẫn muốn topic gốc tiến | Xem retry topic/workflow riêng và ordering tradeoff |

Pause phù hợp nhất khi **khả năng tiếp nhận luồng công việc** của consumer hoặc downstream đang thay đổi. Nó không phải công cụ duy nhất cho mọi trường hợp retry.

## 22. Runbook: container bị pause nhưng không tiến offset

1. Xác định container đã `STOPPED` hay còn `RUNNING`.
2. Kiểm tra `isPauseRequested()` và `isConsumerPaused()`.
3. Kiểm tra parent container, child consumer và partition-level pause.
4. Tìm nguồn phát yêu cầu: operator, backpressure monitor, retry backoff handler hoặc application code.
5. Kiểm tra scheduler/resume task vẫn hoạt động.
6. Kiểm tra downstream health và ngưỡng hysteresis.
7. Xác nhận pod/instance nào đang sở hữu partitions và có bị rebalance không.
8. Kiểm tra log pause/resume events, lag và timestamp của yêu cầu.
9. Nếu downstream đã phục hồi, clear đúng pause reason và gọi resume từ control plane.
10. Xác nhận record mới được xử lý và lag bắt đầu giảm.

Nếu application restart, trạng thái pause điều khiển từ memory có thể thay đổi. Với maintenance có quy trình nhiều instance, cần xác định pause state có phải được lưu bền vững hay được dựng lại từ control plane sau restart.

## 23. Runbook: backlog tăng sau pause

1. Đo ingress rate, consumer processing rate và backlog.
2. Kiểm tra topic retention và dung lượng Kafka.
3. Tính thời gian dự kiến để bắt kịp theo throughput net.
4. Xác nhận database/API đã phục hồi đủ capacity.
5. Resume có kiểm soát; tránh tất cả pods cùng đẩy tải tối đa ngay lập tức.
6. Theo dõi DB connection pool, HTTP 429/503, error handler retry và DLT.
7. Kiểm tra key skew/hot partition nếu một partition tụt hậu dù concurrency cao.
8. Nếu cần phục hồi sau retention, dùng quy trình replay/restore có audit.
9. Không reset consumer offsets chỉ để làm dashboard lag về 0.
10. Điều chỉnh ngưỡng backpressure và SLO để tránh lặp lại outage.

Một lỗi cần tránh: resume khi dependency chưa phục hồi làm listener thất bại, rồi monitor lại pause, tạo vòng lặp pause/resume gây tải dao động.

## 24. Những sai lầm thường gặp

**Gọi trực tiếp KafkaConsumer.pause từ thread quản trị:** KafkaConsumer không thread-safe. Khi dùng Spring listener container, hãy dùng API pause/resume của container.

**Dùng Thread.sleep dài trong listener:** Có thể ảnh hưởng poll interval và rebalance. Pause container cho phép poll loop tiếp tục.

**Cho rằng pause áp dụng ngay:** Records đã poll và in-flight work có thể còn chạy. Cần phân biệt requested/effective.

**Nuốt exception sau khi pause:** Container có thể commit offset của record chưa hoàn tất. Cần propagate exception hoặc xử lý ack/retry đúng.

**Dùng pause thay DLT:** Poison record không tự hợp lệ sau một khoảng nghỉ. Cần phân loại lỗi permanent.

**Kỳ vọng partition chuyển sang member khác:** Pause không chủ động nhả assignment. Stop hoặc rebalance mới có thể thay đổi ownership.

**Một pod resume, tưởng cả group resume:** Registry là phạm vi JVM. Cần quan sát tất cả instances.

**Không có giới hạn pause duration:** Backlog có thể vượt SLO hoặc retention; cần alert và ownership.

**Auto resume ghi đè manual maintenance:** Cần ưu tiên các pause reasons hoặc control plane thống nhất.

## 25. Checklist triển khai

- [ ] Sử dụng `MessageListenerContainer.pause()/resume()`.
- [ ] Có `@KafkaListener(id = ...)` ổn định để điều khiển đúng container.
- [ ] Phân biệt yêu cầu pause với pause đã có hiệu lực.
- [ ] Cân nhắc `pauseImmediate` khi cần dừng bắt đầu xử lý records sớm hơn.
- [ ] Không nhầm pause container với pause partition hoặc stop container.
- [ ] Consumer poll tiếp tục để duy trì group membership.
- [ ] Không dùng `Thread.sleep` trong listener để thay pause.
- [ ] Không nuốt exception hoặc ack record chưa xử lý thành công.
- [ ] Có error handler và DLT cho record không thể xử lý.
- [ ] Có control loop với hysteresis và pause-reason ownership rõ ràng.
- [ ] Có giám sát pause duration, lag, retention và downstream capacity.
- [ ] Có cách điều khiển tất cả pods và theo dõi effective state.
- [ ] Có runbook drain in-flight trước maintenance.
- [ ] Resume theo năng lực thực tế và theo dõi backlog drain.

**Kết luận:** Pause listener container là cơ chế backpressure hiệu quả trong Spring Kafka khi downstream tạm thời không đủ capacity. Thay vì dừng consumer group, container giữ poll loop hoạt động và tạm dừng dispatch records sau khi pause có hiệu lực. Thiết kế đúng phải phân biệt pause requested/effective, theo dõi in-flight work, giới hạn thời gian pause và phối hợp resume với health của dependency. Với records đã thất bại, các trách nhiệm về offset, retry, transaction, DLT và idempotency vẫn phải được xử lý độc lập; pause không tự thay thế chúng.
