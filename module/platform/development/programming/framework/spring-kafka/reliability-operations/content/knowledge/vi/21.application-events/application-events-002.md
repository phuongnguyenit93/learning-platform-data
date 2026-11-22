# ConsumerStartedEvent

Trong Spring Kafka, listener container quản lý vòng đời của một hoặc nhiều Kafka consumer: khởi tạo client, tham gia consumer group, thực hiện `poll()`, gọi phương thức listener, quản lý offset và đóng tài nguyên khi dừng. Ngoài việc xử lý record, framework còn phát ra các **application events** để ứng dụng có thể quan sát những chuyển đổi lifecycle quan trọng.

**`ConsumerStartedEvent`** là sự kiện Spring Kafka cho biết một Kafka consumer do listener container quản lý đã bước vào trạng thái hoạt động sau giai đoạn khởi động. Ứng dụng có thể nhận sự kiện này qua Spring `@EventListener` hoặc `ApplicationListener<ConsumerStartedEvent>` để ghi log, đo thời gian khởi động, theo dõi số consumer đang vận hành hoặc phối hợp các tín hiệu sức khỏe.

Điểm quan trọng: **`ConsumerStartedEvent` không bảo đảm consumer đã được gán partition, đã đọc record đầu tiên, đã bắt kịp lag hoặc đã xử lý thành công nghiệp vụ**. Đây là tín hiệu lifecycle **trong cùng JVM**, không phải Kafka record và không thay thế việc kiểm tra readiness, partition assignment hay business progress.

## 1. ConsumerStartedEvent nằm ở đâu trong luồng hoạt động?

Ví dụ một listener nhận sự kiện tạo đơn hàng:

~~~java
@Component
public class OrderCreatedListener {

    private final OrderService orderService;

    public OrderCreatedListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-created-listener",
            groupId = "orders-service",
            topics = "orders.created")
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Spring Kafka tạo listener container cho endpoint `orders-created-listener`. Container khởi động consumer, consumer tham gia group và bắt đầu lấy record từ broker.

~~~text
ApplicationContext khởi động
            |
            v
KafkaListenerEndpointRegistry khởi động container
            |
            v
Kafka consumer thread được tạo/khởi chạy
            |
            v
ConsumerStartingEvent (giai đoạn bắt đầu)
            |
            v
ConsumerStartedEvent (consumer đã khởi động)
            |
            v
poll / group coordination / partition assignment
            |
            v
Nhận record -> gọi @KafkaListener -> ack/commit
~~~

Sơ đồ nhằm phân biệt **startup lifecycle** với các công việc Kafka phía sau. Thứ tự chi tiết giữa khởi tạo consumer, lần `poll()` đầu tiên và một số callback có thể phụ thuộc implementation/phiên bản. Không dùng sơ đồ để khẳng định rằng ngay khi `ConsumerStartedEvent` được phát, partition assignment đã ổn định hoặc consumer đã nhận dữ liệu.

Sự kiện được publish vào **Spring application event infrastructure**. Nó chỉ được nhận bởi những bean/event listener đã đăng ký trong ứng dụng đang phát sự kiện.

## 2. Sự kiện biểu thị điều gì và không biểu thị điều gì?

`ConsumerStartedEvent` hữu ích khi muốn trả lời câu hỏi: “Consumer thread do container quản lý đã bắt đầu hoạt động hay chưa?”

| Có thể sử dụng làm tín hiệu | Không thể kết luận chỉ từ sự kiện |
|---|---|
| Một consumer đã đi qua bước khởi động do Spring Kafka quản lý | Đã được broker assign partition. |
| Ghi nhận mốc start trong lifecycle | Đã đọc được record đầu tiên. |
| Bắt đầu đo thời gian tới khi có assignment/record | Kafka broker và mọi dependency đều healthy. |
| Tăng metric số lượt consumer start | Consumer hiện vẫn còn running vào thời điểm quan sát về sau. |
| Đối chiếu với sự kiện stop và restart | Đã commit offset mới hoặc xử lý hết backlog. |
| Phân tích startup bất thường khi thiếu event | Không có event nghĩa là broker chắc chắn lỗi. |

Một consumer có thể start thành công nhưng chưa được gán partition vì **số consumer nhiều hơn số partition** trong group. Nó cũng có thể start rồi gặp lỗi authentication, deserialization, network hoặc bị stop. Vì vậy không nên đặt `applicationReady=true` chỉ dựa trên việc nhận một `ConsumerStartedEvent`.

Ngược lại, một consumer không phát event đến được observer vì event listener chưa đăng ký, multicaster không hoạt động như dự kiến hoặc JVM dừng sớm cũng không đồng nghĩa consumer chắc chắn không từng hoạt động.

## 3. Nhận ConsumerStartedEvent bằng @EventListener

Class sự kiện nằm trong package của Spring Kafka:

~~~java
import org.springframework.kafka.event.ConsumerStartedEvent;
~~~

Một observer đơn giản:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleObserver.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started, source={}, container={}",
                event.getSource(), event.getContainer());
    }
}
~~~

Spring gọi method khi application event thuộc kiểu `ConsumerStartedEvent` được publish. Ví dụ này chỉ ghi log lifecycle; không gọi API `KafkaConsumer` và không can thiệp vị trí offset.

`getSource()` là thuộc tính kế thừa từ Spring `ApplicationEvent`, còn `getContainer()` được cung cấp bởi dòng Kafka events để liên hệ sự kiện với container. Định danh/đối tượng cụ thể phụ thuộc loại container và phiên bản framework. Khi ghi log, nên dùng thông tin container được hỗ trợ rõ ràng thay vì phân tích chuỗi `toString()`.

### 3.1. Sử dụng ApplicationListener

Nếu cần implement interface thay vì annotation:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartListener
        implements ApplicationListener<ConsumerStartedEvent> {

    @Override
    public void onApplicationEvent(ConsumerStartedEvent event) {
        lifecycleMetrics.markConsumerStarted(event);
    }
}
~~~

Cả hai hình thức dùng cơ chế application event của Spring. Chỉ cần một hình thức cho mỗi công việc quan sát; không nên khai báo hai listener cùng tăng một counter nếu không có chủ đích.

### 3.2. Observer an toàn khi monitoring bị lỗi

Một event handler chỉ phục vụ monitoring không nên làm hỏng lifecycle vì hệ thống telemetry chưa sẵn sàng:

~~~java
@EventListener
public void onConsumerStarted(ConsumerStartedEvent event) {
    try {
        lifecycleMetrics.markConsumerStarted(event);
    } catch (RuntimeException exception) {
        log.warn("Could not record consumer start event", exception);
    }
}
~~~

Đây là cơ chế cô lập lỗi **monitoring**. Không áp dụng việc nuốt exception tương tự cho `@KafkaListener` xử lý nghiệp vụ; exception ở listener có thể cần đi qua error handler, retry hoặc transaction rollback.

## 4. Tìm container và listener ID liên quan

Một Spring Boot service có thể chạy nhiều Kafka listeners:

~~~text
orders-created-listener
payments-confirmed-listener
inventory-adjusted-listener
~~~

Nếu mọi `ConsumerStartedEvent` được nhận bởi một observer chung, cần phân biệt listener nào là chủ của consumer vừa start.

Ví dụ kiểm tra kiểu container:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartMetrics {

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        Object containerObject = event.getContainer();

        if (containerObject instanceof MessageListenerContainer container) {
            String listenerId = container.getListenerId();
            recordStart(listenerId);
        }
    }

    private void recordStart(String listenerId) {
        // Ví dụ: ghi counter theo listener ID ổn định.
    }
}
~~~

Với `ConcurrentMessageListenerContainer`, `getContainer()` và `getSource()` có thể liên hệ parent hoặc child theo kiểu event. Nếu cần phân biệt từng child consumer và listener parent, hãy xác nhận cách nhận diện của phiên bản đang dùng bằng integration test, thay vì dựa vào `source.toString()`.

Các ID cần phân biệt:

| ID | Ý nghĩa |
|---|---|
| `@KafkaListener(id = "...")` | Định danh listener endpoint/container trong Spring registry. |
| `groupId` | Consumer group phân chia partition và lưu committed offsets. |
| `client.id` / client ID prefix | Định danh Kafka client, thường hữu ích cho logs và JMX/metrics. |
| Instance/Pod ID | Tiến trình triển khai chứa listener. |
| Child consumer container ID | Định danh một consumer thread khi dùng concurrency. |

Các ID này có thể có giá trị gần giống nhau nhưng không có cùng chức năng. Hãy dùng ID ổn định, cardinality phù hợp cho metric labels; dùng client/instance ID chi tiết trong structured logs khi cần điều tra.

## 5. ConsumerStartedEvent trong concurrent container

`ConcurrentKafkaListenerContainerFactory` có thể tạo listener container với nhiều consumer threads:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Listener dùng factory:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        groupId = "orders-service",
        topics = "orders.created",
        containerFactory = "orderFactory")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Cấu trúc:

~~~text
ConcurrentMessageListenerContainer
            |
            +---- child consumer container 0
            +---- child consumer container 1
            +---- child consumer container 2
~~~

Với concurrency bằng ba, có thể có **nhiều `ConsumerStartedEvent` cho cùng một logical listener endpoint**, tương ứng các consumer thread được khởi động. Event cấp consumer không nhất thiết có số lượng bằng số listener method hoặc số replica ứng dụng.

Ví dụ một topic chỉ có hai partition nhưng listener concurrency ba:

- Ba consumer có thể khởi động.
- Chỉ tối đa hai consumer nhận partition của topic trong cùng consumer group nếu không subscribe thêm topic khác.
- Một consumer có thể không được assign partition dù đã phát `ConsumerStartedEvent`.
- Tăng concurrency vượt số partition không làm một partition được xử lý song song bởi nhiều consumer member cùng group.

**Không dùng số event start để suy ra số partition đang sở hữu.** Cần consumer assignment metrics/callbacks để xác định partition ownership.

### 5.1. Đếm restart mà không đếm trùng

Một consumer có thể start, stop rồi start lại do thao tác vận hành. Nếu dùng counter, mỗi sự kiện mới có thể tăng số lượt start. Nếu dùng gauge “số consumer đang chạy”, cần kết hợp start và stop events, đồng thời có cơ chế reconciliation khi event bị bỏ lỡ.

Ví dụ:

~~~text
t0: child-0 started  -> start counter = 1
t1: child-1 started  -> start counter = 2
t2: child-1 stopped  -> active consumer count cần giảm
t3: child-1 started  -> start counter = 3
~~~

Một counter “start attempts observed” và gauge “current active consumers” là **hai metric khác nhau**. Chỉ tích lũy ConsumerStartedEvent rồi gọi kết quả là active consumer count sẽ sai sau những lần restart hoặc shutdown.

## 6. Phân biệt ConsumerStartingEvent, ConsumerStartedEvent và ConsumerStoppedEvent

Spring Kafka có các application events mô tả những bước khác nhau trong vòng đời consumer.

| Event | Ý nghĩa khái quát | Tình huống sử dụng |
|---|---|---|
| `ConsumerStartingEvent` | Consumer đang bước vào quá trình khởi động. | Đánh dấu bắt đầu vòng startup, đo độ trễ. |
| **`ConsumerStartedEvent`** | Consumer đã khởi động ở cấp lifecycle. | Ghi nhận consumer thread đã chạy. |
| `ConsumerFailedToStartEvent` | Consumer không bắt đầu được theo điều kiện/thời hạn mà container theo dõi. | Điều tra startup failure. |
| `ConsumerStoppingEvent` | Consumer bắt đầu dừng. | Đo thời gian stop, quan sát shutdown. |
| `ConsumerStoppedEvent` | Consumer đã dừng, có thể có reason. | Phân biệt stop bình thường và bất thường. |
| `ContainerStoppedEvent` | Listener container đã dừng. | Quan sát lifecycle cấp container/endpoint. |
| `ListenerContainerIdleEvent` | Listener không nhận record trong khoảng idle threshold. | Theo dõi inactivity, không phải startup failure. |
| `NonResponsiveConsumerEvent` | Container phát hiện consumer không đáp ứng tiêu chí tiến triển/poll. | Chẩn đoán consumer bị chặn hoặc processing chậm. |

Danh sách event và API lấy reason/container có thể khác theo phiên bản Spring Kafka. Không mặc định mọi event trong bảng luôn được phát trong mọi cấu hình.

### 6.1. “Started” không đồng nghĩa “running forever”

`ConsumerStartedEvent` là **event tại một thời điểm**. Consumer có thể stop ngay sau đó do broker auth failure, application shutdown, producer fencing hoặc lỗi khác.

Nếu cần biết trạng thái hiện tại, kết hợp với `ConsumerStoppedEvent`, container `isRunning()` và consumer group/lag metrics. Một event start lịch sử không phải health check liên tục.

### 6.2. “Started” không đồng nghĩa “assigned”

Consumer có thể join group và nhận partition sau khi thread đã start. Nếu muốn đo assignment, hãy sử dụng `ConsumerRebalanceListener` hoặc `ConsumerAwareRebalanceListener` / container assignment APIs phù hợp.

~~~text
Consumer thread started
          |
          v
Kafka poll() / join group
          |
          v
Partition assignment
          |
          v
Fetch records
          |
          v
Business processing
~~~

Đây là các mốc riêng. Startup event cho biết mốc đầu, không thể thay thế các mốc sau.

## 7. Theo dõi partition assignment đúng cách

Nếu ứng dụng chỉ nên được coi “sẵn sàng xử lý” khi sở hữu ít nhất một partition, `ConsumerStartedEvent` không đủ. Có thể quan sát assignment qua rebalance callback:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String> myListenerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {
                @Override
                public void onPartitionsAssigned(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    assignmentObserver.recordAssigned(partitions);
                }

                @Override
                public void onPartitionsRevokedBeforeCommit(
                        Consumer<?, ?> consumer,
                        Collection<TopicPartition> partitions) {
                    assignmentObserver.recordRevoked(partitions);
                }
            });

    return factory;
}
~~~

Ví dụ minh họa việc nhận assignment/revocation; các interface callback và override được hỗ trợ phụ thuộc phiên bản Spring Kafka. Nếu listener có concurrency cao, observer cần gắn assignment với **consumer member/container cụ thể**, không ghi một danh sách global rồi giả định nó đại diện cho toàn bộ group.

Callback rebalance có thể chạy trên consumer thread. Không thực hiện HTTP/DB blocking dài, không chia sẻ `KafkaConsumer` giữa threads và không tự thay đổi assignment ngoài hợp đồng callback.

Một ứng dụng có thể không sở hữu partition vào một thời điểm nhưng vẫn hoàn toàn healthy nếu Kafka group có nhiều consumer hơn partition. Vì vậy, điều kiện readiness “có ít nhất một assignment” cũng cần tùy chỉnh theo topology.

## 8. Đo startup latency bằng sự kiện lifecycle

Có thể dùng mốc ConsumerStarting và ConsumerStarted để đo thời gian framework đưa consumer thread tới trạng thái started.

Ví dụ các mốc:

~~~text
T0: container.start() được gọi
T1: ConsumerStartingEvent
T2: ConsumerStartedEvent
T3: partitions assigned
T4: nhận record đầu tiên
T5: xử lý record đầu tiên thành công
~~~

Các khoảng thời gian mang ý nghĩa khác nhau:

- **T2 - T1:** giai đoạn consumer lifecycle startup.
- **T3 - T2:** thời gian tới assignment, phụ thuộc Kafka group coordination.
- **T4 - T3:** thời gian tới record đầu tiên, phụ thuộc topic có dữ liệu hay không.
- **T5 - T4:** thời gian xử lý nghiệp vụ đầu tiên.

Chỉ đo tới T2 rồi gọi đó là “ready to process records” có thể gây hiểu nhầm. Consumer có thể chưa có assignment hoặc topic không có record.

Để tính latency đúng trong concurrent container, cần liên kết các events theo **cùng một child consumer**, không lấy ConsumerStartingEvent của child A trừ ConsumerStartedEvent của child B.

### 8.1. Không dùng wall clock cho mọi phép đo

Trong Java, nếu đo duration trong cùng process, `System.nanoTime()` thích hợp hơn `System.currentTimeMillis()` vì nó là monotonic clock cho đo thời gian trôi qua. Nếu cần correlation với logs từ các process khác, timestamp UTC vẫn hữu ích, nhưng chênh lệch đồng hồ giữa máy có thể làm phép đo wall-clock sai.

Ứng dụng có thể giữ một map tạm theo consumer identity để đo startup duration. Map cần loại bỏ entry khi consumer stop hoặc startup failure để tránh rò rỉ memory khi instance restart liên tục.

## 9. Application event handler chạy trên thread nào?

Spring application events được gửi qua `ApplicationEventMulticaster`. Với cấu hình đồng bộ mặc định, event handler thường được chạy trong **thread đã publish event**. Với listener lifecycle Spring Kafka, thread này có thể là consumer/container thread.

Nếu ứng dụng cấu hình `SimpleApplicationEventMulticaster` với executor, event handler có thể chạy bất đồng bộ. Khi đó thứ tự xử lý và thread ownership có thể khác.

Vì vậy, `@EventListener` nhận `ConsumerStartedEvent` nên:

- Thực hiện ít việc và trả về nhanh.
- Chỉ ghi log, metric hoặc cập nhật trạng thái in-memory gọn nhẹ.
- Tránh HTTP request không timeout hoặc database query lâu.
- Không gọi `poll()`, `commitSync()`, `seek()` hoặc `close()` trên `KafkaConsumer` từ một thread bất kỳ.
- Không gọi `container.stop()` rồi chờ đồng bộ theo cách có thể chặn chính consumer đang khởi động.
- Không giả định event listener chạy trên thread riêng để thực hiện mọi công việc nặng.

KafkaConsumer không thread-safe cho các thao tác sử dụng thông thường. Các chức năng cần thao tác consumer nên sử dụng callback/manager API được Spring Kafka hỗ trợ và chạy đúng thread.

### 9.1. Nếu cần thực hiện công việc bất đồng bộ

Một observer có thể đẩy một thông báo nhẹ tới hệ thống nội bộ để worker khác xử lý:

~~~java
@EventListener
public void onStarted(ConsumerStartedEvent event) {
    lifecycleQueue.offer(new ConsumerLifecycleMarker(
            "CONSUMER_STARTED",
            System.currentTimeMillis()));
}
~~~

Đây là ví dụ khái niệm với `lifecycleQueue` và `ConsumerLifecycleMarker` do ứng dụng định nghĩa. Nó **không** đồng nghĩa cần lập một thread riêng cho mỗi event, cũng không đảm bảo thông báo được lưu bền vững.

Nếu lifecycle signal là điều kiện để thực hiện một thao tác bắt buộc, hãy dùng cơ chế lưu trữ/điều phối phù hợp thay vì phụ thuộc vào queue in-memory có thể mất khi JVM crash.

## 10. ConsumerStartedEvent và autoStartup

Một `@KafkaListener` thường được start khi application context khởi động, tùy cấu hình container/registry. Nếu cần trì hoãn start cho tới khi một dependency sẵn sàng, có thể dùng `autoStartup = "false"`.

Ví dụ:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        groupId = "orders-service",
        topics = "orders.created",
        autoStartup = "false")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Sau khi ứng dụng đã khởi động và đã hoàn tất việc kiểm tra dependency, có thể lấy container từ registry rồi gọi `start()`:

~~~java
@Service
public class OrdersConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean startOrdersConsumer() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            return false;
        }

        if (!container.isRunning()) {
            container.start();
        }
        return true;
    }
}
~~~

`start()` là yêu cầu bắt đầu lifecycle; không nên mặc định rằng trước khi method trả về đã có partition assignment hay đã xử lý record.

Nếu có observer `ConsumerStartedEvent`, ứng dụng có thể ghi nhận khi consumer thực sự vượt qua bước khởi động sau yêu cầu này. Nhưng không dùng event để thay thế callback/metric cho bước “đã được assign partition”.

### 10.1. Startup phụ thuộc dependency

Ví dụ hệ thống phải load schema/cache hoặc xác nhận database migration trước khi nhận Kafka events. Có thể dùng startup orchestration với `autoStartup=false`, gọi start khi dependency sẵn sàng.

Tuy nhiên, cần tránh “dependency chưa sẵn sàng” khiến ứng dụng ở trạng thái chờ vô hạn. Hãy đặt timeout, retry policy và alert. Nếu instance khác đang xử lý cùng consumer group, khi listener này chưa start thì broker có thể phân phối partition cho các members khác.

## 11. ConsumerStartedEvent và Spring Boot readiness

Không nên đơn giản viết:

~~~text
Nếu nhận ConsumerStartedEvent:
    readiness = UP
~~~

Điều này chỉ chứng minh đã có một sự kiện start. Một worker có thể start consumer nhưng không kết nối broker, không nhận assignment hoặc không xử lý được record do downstream database lỗi.

Với ứng dụng có nhiều listeners, readiness nên xét rõ listener nào là bắt buộc:

| Tình huống | Cách đánh giá phù hợp |
|---|---|
| Một listener quan trọng phải chạy | Kết hợp container state và error/assignment monitoring. |
| Consumer group có nhiều members hơn partitions | Không coi member idle là thất bại tự động. |
| Một listener optional dừng | Có thể chỉ cảnh báo, không hạ toàn bộ readiness. |
| Broker không khả dụng | Theo dõi Kafka client/group health và tiến độ poll. |
| Downstream DB lỗi | Business processing SLO/health kiểm tra DB, không phụ thuộc startup event. |

**Liveness** cũng khác readiness. Nếu consumer chưa nhận event start vì broker chậm, không nên khởi động lại JVM liên tục theo một điều kiện thiếu căn cứ; vòng restart có thể làm group rebalance nhiều hơn và chậm phục hồi.

Spring Boot `ApplicationReadyEvent` là sự kiện ứng dụng hoàn tất quá trình khởi động ở cấp Boot, không đồng nghĩa từng Kafka consumer đã được assign partition hoặc hoàn tất xử lý nghiệp vụ.

## 12. ConsumerStartedEvent và partition count

Số consumer đang chạy và số partition của topic tạo giới hạn xử lý song song.

Ví dụ:

~~~text
Topic orders.created có 4 partitions
Group orders-service có 6 consumers

Consumer A -> p0
Consumer B -> p1
Consumer C -> p2
Consumer D -> p3
Consumer E -> không có assignment
Consumer F -> không có assignment
~~~

Cả E và F có thể đã start consumer thread, mặc dù không có partition để xử lý trong group hiện tại.

Khi tăng `concurrency` hoặc scale replica, số `ConsumerStartedEvent` có thể tăng trong khi throughput không đổi nếu đã đạt giới hạn số partition. Ngược lại, hot partition có thể tạo lag dù nhiều consumer đều báo started.

Vì vậy, production metrics nên tách bạch:

- Consumer thread starts.
- Active/assigned partitions.
- Records consumed per member/partition.
- Processing latency và error rate.
- Consumer lag per partition.
- Rebalance rate/duration.

## 13. Start event không phải sự kiện Kafka broker

Một Kafka broker không biết hoặc không phát `ConsumerStartedEvent` tới application. Đây là **sự kiện của Spring Kafka**, do listener container đưa vào Spring application event mechanism.

Hệ quả:

- Một microservice khác không tự nhận event này qua Kafka.
- Không có Kafka topic, partition hoặc offset của event lifecycle.
- Không thể replay lại `ConsumerStartedEvent` sau JVM crash.
- Application event listener có thể không được gọi nếu bean chưa đăng ký hoặc context gặp lỗi trước khi phát event.
- Nếu cần audit xuyên tiến trình, phải chủ động xuất metric/log hoặc publish một domain event riêng với semantics và durability phù hợp.

Không nên publish một Kafka record “consumer started” trong chính `@EventListener` rồi xem nó là tín hiệu durable tuyệt đối. Nếu producer chưa sẵn sàng hoặc broker không thể kết nối lúc startup, thao tác publish có thể thất bại; điều này còn làm phức tạp lifecycle.

## 14. Start, stop và restart

Các chu kỳ đời sống có thể diễn ra:

~~~text
Container START
     |
     +---- ConsumerStartingEvent
     +---- ConsumerStartedEvent
     |
     v
RUNNING -> poll / process / commit
     |
     v
Container STOP
     |
     +---- ConsumerStoppingEvent
     +---- ConsumerStoppedEvent
     +---- ContainerStoppedEvent (theo lifecycle container)
     |
     v
STOPPED
     |
     +---- start lại, consumer thread mới
     +---- ConsumerStartedEvent có thể xuất hiện lần nữa
~~~

Các events về stop/start không nhất thiết xuất hiện theo cùng một thứ tự cứng trong mọi trường hợp concurrent container và event multicaster; sơ đồ chỉ thể hiện các giai đoạn chính.

Nếu ứng dụng sử dụng start/stop thủ công, nên kiểm tra cả trạng thái `isRunning()` và lệnh callback (nếu cần). Consumer thread mới có thể được tạo sau restart, ngay cả khi logical listener ID giữ nguyên.

Một consumer có thể chết đột ngột hoặc JVM bị hard kill, nên không thể dựa vào việc có đủ cặp started/stopped events để tự suy ra số consumer active trong production. Gauge nên được đối soát với trạng thái container hiện tại hoặc metrics từ broker/client.

## 15. Trường hợp ConsumerStartedEvent không xuất hiện

Khi một listener không chạy mà observer không thấy start event, đừng kết luận nguyên nhân ngay. Hãy điều tra theo tầng:

1. **Listener có được đăng ký?** Xem `@EnableKafka`/Spring Boot autoconfiguration, component scanning, `KafkaListenerEndpointRegistry`.
2. **Auto-start có bật?** Kiểm tra `autoStartup` và lifecycle phase.
3. **Container có được yêu cầu start?** Nếu `autoStartup=false`, phải có code/admin action gọi start.
4. **Factory/consumer config có hợp lệ?** Kiểm tra bootstrap servers, serializer/deserializer, group ID, topic.
5. **Consumer có fail lúc khởi động?** Tìm `ConsumerFailedToStartEvent`, Kafka client logs và exception.
6. **Observer đã đăng ký?** `@EventListener` phải nằm trong bean thuộc application context nhận event.
7. **Event multicaster có bị tùy biến?** Kiểm tra xử lý async, executor shutdown hoặc event listener lỗi.
8. **Có đủ partition không?** Thiếu partition không giải thích trực tiếp việc không có start event nhưng có thể làm consumer không xử lý record.
9. **Consumer đã start rồi stop rất nhanh?** Đối chiếu `ConsumerStoppedEvent` và container logs.
10. **Context/Pod bị dừng trước khi start?** Kiểm tra Spring Boot startup failure và orchestrator logs.

Khi consumer không nhận record nhưng `ConsumerStartedEvent` vẫn xuất hiện, điều tra partition assignment, group state, lag và topic có dữ liệu hay không trước khi cho rằng listener logic đã hỏng.

## 16. Monitoring và metric design

Một structured log hữu ích:

~~~text
event_type=ConsumerStartedEvent
service=orders-worker
listener_id=orders-created-listener
instance_id=orders-worker-3
consumer_start_time=2026-11-15T17:00:00Z
~~~

`consumer_start_time`, `service` và `instance_id` là fields do ứng dụng/telemetry thêm vào, **không phải** tất cả đều là thuộc tính built-in của event. Timestamp trên chỉ minh họa.

Các metrics có thể triển khai:

| Metric | Ý nghĩa | Lưu ý |
|---|---|---|
| Consumer start count | Tổng số lượt consumer start. | Dùng counter, không dùng làm active gauge. |
| Consumer startup duration | Độ trễ từ starting tới started. | Ghép cùng consumer identity, dùng monotonic timer. |
| Listener running gauge | Trạng thái container ở thời điểm quan sát. | Đối soát khi event bị bỏ lỡ. |
| Assigned partition count | Số partition mà consumer đang sở hữu. | Tính từ assignment, không từ start event. |
| Consumer lag per partition | Backlog cần xử lý. | Không thể suy từ event started. |
| Rebalance count/duration | Tần suất thay đổi ownership. | Dùng group/rebalance telemetry. |
| Consumer stop reason count | Phân loại dừng trong phiên bản hỗ trợ. | Quan sát cùng ConsumerStoppedEvent. |
| First successful processing latency | Thời gian từ startup tới event đầu tiên xử lý xong. | Cần mốc business processing riêng. |

Metric labels nên dùng service/topic/listener ID có cardinality hợp lý. Không dùng event ID, Kafka offset hoặc một client ID không giới hạn trong mọi metric nếu backend monitoring khó lưu trữ.

## 17. Integration test nhận ConsumerStartedEvent

Unit test gọi thẳng `onConsumerStarted(...)` chỉ kiểm tra code observer, không chứng minh Spring Kafka thực sự phát sự kiện. Integration test nên khởi tạo Spring context và một listener container thật, có thể dùng Embedded Kafka hoặc Kafka Testcontainers.

Để test deterministic, chọn listener `autoStartup=false` và gọi start **sau khi event probe được khởi tạo**, tránh bỏ lỡ event ngay trong lúc context đang khởi động.

Ví dụ probe:

~~~java
@Component
public class ConsumerStartedProbe {

    private final BlockingQueue<ConsumerStartedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        events.offer(event);
    }

    public ConsumerStartedEvent await(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Các imports chính gồm `java.time.Duration`, `java.util.concurrent.BlockingQueue`, `LinkedBlockingQueue` và `TimeUnit`.

Listener kiểm thử:

~~~java
@KafkaListener(
        id = "startup-test-listener",
        groupId = "startup-test-group",
        topics = "startup.test",
        autoStartup = "false")
public void onTestMessage(String payload) {
    // Không cần record thật để quan sát consumer lifecycle.
}
~~~

Test:

~~~java
@SpringBootTest
class ConsumerStartedEventIT {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    ConsumerStartedProbe probe;

    @Test
    void startingContainerPublishesConsumerStartedEvent()
            throws Exception {

        MessageListenerContainer container =
                registry.getListenerContainer("startup-test-listener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();

        ConsumerStartedEvent event =
                probe.await(Duration.ofSeconds(30));

        assertThat(event).isNotNull();

        container.stop();
    }
}
~~~

Test cần có broker/topic thật cùng cấu hình Kafka consumer hợp lệ. Nếu application context chứa nhiều listeners, probe nên **lọc event theo container identity** hoặc chỉ bật một listener liên quan; nếu không, một sự kiện của listener khác có thể tạo false positive.

Test chỉ xác nhận start event, không cần gửi record. Nếu muốn xác nhận consumer đã nhận partition, phải có assertion khác dựa trên assignment.

### 17.1. Test concurrency

Chạy listener có `concurrency=3` trên topic đủ partition; quan sát sự kiện của các child consumers. Đặt timeout hữu hạn, tránh giả định event order và số lượng cứng khi consumer restart hoặc test chạy song song.

Tách ba assertion:

1. Container đã nhận lệnh start và ở trạng thái running.
2. Các consumer lifecycle events phù hợp đã được phát.
3. Consumer group đã có assignment theo topology mong đợi.

### 17.2. Test stop và restart

Một kịch bản:

~~~text
Start container -> nhận ConsumerStartedEvent
Stop container -> chờ stop callback/ConsumerStoppedEvent
Start lại -> nhận ConsumerStartedEvent lần tiếp theo
~~~

Lưu ý làm sạch queue của probe giữa các pha để không nhận event cũ. Hãy kiểm tra trạng thái container, thay vì chỉ đếm tổng số event rồi kết luận đã restart đúng.

### 17.3. Test lỗi khởi động

Một số trường hợp cần test riêng:

- Consumer factory có cấu hình sai.
- Authentication/authorization không hợp lệ.
- Container bị shutdown trong khi đang start.
- Topic không tồn tại khi cấu hình không cho tạo topic tự động.
- Listener được cấu hình `autoStartup=false` và không có lệnh start.

Không phải mọi lỗi đều tạo `ConsumerFailedToStartEvent` giống nhau. Hãy kết hợp event với exception/log và container state theo phiên bản framework đang dùng.

## 18. Những sai lầm thường gặp

- **Đánh đồng start event với partition assigned:** consumer có thể started nhưng không có partition.
- **Coi start event là readiness tuyệt đối:** broker, database và business processing có thể chưa sẵn sàng.
- **Đếm start events như số consumer active hiện tại:** consumer có thể stop/restart nhiều lần.
- **Đếm events như số replica:** một replica có thể có nhiều consumer threads.
- **Dùng event để commit offset hoặc thao tác KafkaConsumer từ thread không đúng:** event listener không phải offset-management callback.
- **Blocking HTTP/database trong @EventListener:** có thể kéo dài quá trình consumer start.
- **Giả định event luôn được xử lý đồng bộ và đúng thứ tự:** event multicaster có thể được tùy biến.
- **Dựa vào event in-memory như một audit log bền vững:** JVM crash làm mất dấu vết chưa xuất.
- **Dùng getSource().toString() làm khóa metric lâu dài:** format chuỗi debug không phải API contract.
- **Không phân biệt listener ID, group ID và client ID:** dẫn đến dashboard gán sai owner.
- **Chỉ test listener method mà không start container thật:** không xác nhận event lifecycle.
- **Test auto-start nhưng đăng ký observer quá muộn:** có thể bỏ lỡ event.
- **Không làm sạch probe queue trước test restart:** assertion vô tình nhận event cũ.
- **Tự động restart liên tục khi thiếu event:** có thể khiến group rebalances nhiều hơn mà không sửa root cause.

## 19. Thiết kế sử dụng ConsumerStartedEvent trong production

Một thiết kế quan sát tối giản:

~~~text
ConsumerStartedEvent
        |
        v
Spring lifecycle observer
        |
        +---- structured log
        +---- consumer startup counter
        +---- startup-duration metric
        +---- cập nhật dấu mốc lifecycle trong memory
        |
        +---- đối chiếu với:
               ConsumerStoppedEvent
               KafkaListenerEndpointRegistry state
               partition assignment
               consumer lag / processing throughput
               deployment & restart signals
~~~

Hãy coi `ConsumerStartedEvent` là một **mốc bắt đầu**, không phải bằng chứng hoàn tất toàn bộ startup hay dữ liệu đã được xử lý. Nếu cần khẳng định service có thể nhận record, phối hợp với trạng thái container, group assignment và health của dependency. Nếu cần khẳng định record được xử lý bền vững, kiểm tra business side effects, committed offsets và transaction semantics.

Khi được dùng đúng, **ConsumerStartedEvent** giúp hệ thống Spring Kafka nhìn rõ startup lifecycle, đo độ trễ khởi động và phân biệt lỗi khởi động consumer với các vấn đề Kafka group hoặc nghiệp vụ xảy ra sau đó. Event handler nên gọn, tránh can thiệp trực tiếp vào consumer và luôn được đặt trong một chiến lược giám sát rộng hơn gồm logs, metrics, rebalance callbacks và dữ liệu broker thực tế.
