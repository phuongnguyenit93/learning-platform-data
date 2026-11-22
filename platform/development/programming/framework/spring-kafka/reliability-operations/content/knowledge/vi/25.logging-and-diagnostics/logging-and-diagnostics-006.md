# Log group id và listener id

Khi vận hành một ứng dụng Spring Kafka, log “đã nhận record” thường chưa đủ để xác định consumer nào thực sự xử lý dữ liệu. Một topic có thể được nhiều consumer group đọc độc lập; mỗi group lại có nhiều member, listener container và Kafka client. Nếu log chỉ ghi topic và offset, đội vận hành khó biết record thuộc **luồng xử lý nghiệp vụ nào**, container nào đang sở hữu partition, hoặc tại sao một group bị chậm trong khi group khác vẫn hoạt động.

Hai định danh cần phân biệt là **Kafka group id** và **Spring Kafka listener id**. Group ID xác định consumer group trong Kafka, ảnh hưởng partition assignment và committed offsets. Listener ID xác định endpoint/container trong ứng dụng Spring, phục vụ quản lý lifecycle, quan sát event và liên hệ log với listener cụ thể. Ngoài ra còn có **client ID**, **pod/instance ID** và **listener info**; chúng có mục đích riêng và không thể thay thế nhau.

Bài học thuộc chương **Logging và chẩn đoán** của Spring Kafka Reliability Operations. Mục tiêu là thiết kế log có đủ context để điều tra consumer group, listener container, concurrency, rebalance, lag, retry và DLT mà không làm lộ dữ liệu nhạy cảm hoặc tạo metric cardinality quá lớn.

## 1. Phân biệt các loại định danh

| Định danh | Phạm vi | Ai sử dụng? | Vai trò chính |
|---|---|---|---|
| **group.id** | Kafka consumer group | Kafka broker và consumer client | Gom consumer member thành một group; quản lý assignment và committed offsets. |
| **listener id** | Spring application context | Spring Kafka container/registry và ứng dụng | Định danh endpoint/container để log, quản lý lifecycle và liên hệ event. |
| **client.id** | Kafka client instance | Kafka client, broker logs và metrics | Nhận diện một client để quan sát, quota hoặc chẩn đoán. |
| **pod/instance id** | Runtime/deployment | Kubernetes, logging/monitoring | Phân biệt các replica đang chạy cùng service. |
| **listener info** | Metadata do ứng dụng đặt | Spring Kafka message headers/listener | Đính kèm thông tin tùy chỉnh vào record khi listener nhận. |
| **event id** | Nghiệp vụ | Ứng dụng và downstream | Nhận diện cùng một sự kiện qua retry, DLT và replay. |

Ví dụ một service chạy ba replica, mỗi replica có một listener với concurrency bằng hai:

~~~text
Deployment: orders-service
  Pod A
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-a-0
    client.id      = orders-client-a-1

  Pod B
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-b-0
    client.id      = orders-client-b-1

  Pod C
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-c-0
    client.id      = orders-client-c-1
~~~

Tên client ở trên chỉ minh họa. Spring Kafka/Kafka client có thể tạo hoặc thêm suffix cho client ID theo cấu hình concurrency. Điểm chính là **cùng một group ID và listener ID có thể xuất hiện ở nhiều pod**, trong khi client ID cần giúp phân biệt từng Kafka client instance.

## 2. group.id là định danh của Kafka consumer group

Kafka dùng `group.id` để xác định các consumer cùng tham gia một nhóm. Các consumer trong cùng group chia sẻ partition assignment của topic được subscribe. Mỗi group có committed offset riêng.

Ví dụ topic `orders` có ba partition:

~~~text
Topic: orders

partition 0  ------------------+
partition 1  ------------------+----> group.id = orders-validation-v1
partition 2  ------------------+

                              Consumer members:
                                member A
                                member B
~~~

Nếu một group có hai member và ba partition, Kafka assign partition cho các member theo assignor và trạng thái group. Một partition tại một thời điểm chỉ thuộc một consumer member trong cùng group theo mô hình group subscription thông thường.

Một consumer group khác có thể đọc cùng topic độc lập:

~~~text
                    Topic: orders
                    /           \
                   /             \
                  v               v
       group.id = validation   group.id = analytics
          |                         |
          v                         v
    Validate orders            Build reports
    committed offsets riêng    committed offsets riêng
~~~

Điều này có nghĩa:

- Hai service cần **đọc cùng một stream độc lập** thường dùng group ID khác nhau.
- Nhiều replica cùng xử lý một workload thường dùng chung group ID để chia partition.
- Nếu vô tình đổi group ID, Kafka xem đó là một group mới; consumer có thể bắt đầu theo `auto.offset.reset` khi chưa có committed offset.
- Nếu hai listener container dùng chung group ID và subscribe cùng topic, chúng tham gia cùng group và có thể chia việc cho nhau thay vì mỗi listener nhận toàn bộ record.

**Group ID là một phần của delivery behavior**, không chỉ là nhãn để log. Thay đổi group ID có thể làm dữ liệu được đọc lại hoặc bỏ qua tùy trạng thái offset và cấu hình reset.

## 3. listener id là định danh của Spring Kafka endpoint/container

Thuộc tính `id` của `@KafkaListener` xác định listener endpoint/container trong Spring application context. Ứng dụng có thể dùng ID này để:

- Lấy container qua `KafkaListenerEndpointRegistry`.
- Pause/resume hoặc stop/start container theo listener.
- Liên hệ các application event với listener.
- Phân biệt các listener cùng service trong log và dashboard.
- Áp dụng cấu hình vận hành hoặc policy theo endpoint.

Ví dụ:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        groupId = "orders-validation-v1"
    )
    public void onOrderCreated(String payload) {
        orderService.validate(payload);
    }
}
~~~

Trong ví dụ này:

- `orders-validation-v1` là Kafka group ID.
- `orders-created-listener` là Spring listener ID.

Hai giá trị phục vụ hai hệ thống định danh khác nhau. Đổi listener ID để quản lý container không nhất thiết tạo consumer group mới nếu group ID vẫn giữ nguyên. Đổi group ID có thể thay đổi offset namespace và partition assignment dù listener ID không đổi.

**Listener ID nên ổn định và duy nhất trong một Spring application context.** Khi cùng deployment có nhiều pod, việc các pod dùng cùng listener ID là bình thường: mỗi pod có application context riêng. Log phải thêm pod/instance ID để phân biệt các bản chạy.

## 4. Quan hệ giữa @KafkaListener id, groupId và idIsGroup

`@KafkaListener` có các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `id` | ID của listener endpoint/container. |
| `groupId` | Ghi đè group ID cho listener, tương ứng consumer `group.id`. |
| `idIsGroup` | Điều khiển việc dùng `id` làm group ID khi không khai báo `groupId`; mặc định thường là `true`. |
| `clientIdPrefix` | Prefix cho Kafka client ID của listener; hữu ích để phân biệt client và concurrency member. |
| `topics` / `topicPattern` | Topic hoặc pattern listener subscribe. |
| `containerFactory` | Factory tạo listener container. |

Ví dụ khai báo rõ ràng:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    idIsGroup = false,
    clientIdPrefix = "orders-validation-client",
    topics = "orders.created"
)
public void onOrder(String payload) {
    orderService.validate(payload);
}
~~~

Khi `groupId` được chỉ định, đó là group ID listener sử dụng. `idIsGroup` chủ yếu có ý nghĩa khi không cung cấp `groupId`: theo mặc định, listener ID có thể được dùng làm group ID; đặt `idIsGroup = false` để không dùng ID làm group ID và để consumer factory cung cấp group ID theo cấu hình.

Ví dụ muốn group ID lấy từ consumer factory:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    idIsGroup = false,
    topics = "orders.created"
)
public void onOrder(String payload) {
    orderService.validate(payload);
}
~~~

Khi đó cần chắc chắn consumer factory đã có `group.id` phù hợp, ví dụ qua Spring Boot property. Nếu không, consumer có thể không có group ID hợp lệ theo yêu cầu của cấu hình ứng dụng.

**Đừng để `idIsGroup` và `groupId` trở thành cấu hình ngầm không được ghi nhận.** Trong service có nhiều listener, khai báo group ID rõ ràng thường giúp log, vận hành và review dễ hiểu hơn.

## 5. Nguồn cấu hình group ID và thứ tự override

Một ứng dụng Spring Boot có thể cấu hình group ID mặc định cho consumer factory:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-validation-v1
      enable-auto-commit: false
~~~

Một listener cụ thể có thể ghi đè bằng `groupId`:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void onOrder(String payload) {
    // ...
}
~~~

Nếu không có group ID ở annotation, listener dùng group ID từ consumer factory theo quy tắc cấu hình và `idIsGroup`. Cần kiểm tra cả các thuộc tính consumer tùy chỉnh trong factory; không chỉ nhìn `application.yml` nếu ứng dụng có nhiều `ConsumerFactory`.

Một cấu hình khác có thể nằm ở Java:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-validation-v1");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

DefaultKafkaConsumerFactory<String, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props);
~~~

Khi điều tra, ghi lại **group ID hiệu lực** của consumer đang chạy, không suy đoán chỉ từ một file cấu hình. Annotation override, bean factory tùy chỉnh hoặc property theo profile có thể làm giá trị runtime khác giá trị mặc định.

## 6. group.id khác client.id

Hai tên này thường xuất hiện gần nhau trong Kafka logs nhưng có ý nghĩa khác nhau.

| Đặc điểm | group.id | client.id |
|---|---|---|
| Đại diện cho | Consumer group | Một Kafka client instance |
| Dùng cho | Assignment, group membership và offset | Metrics, logs, quota/diagnostics |
| Nhiều member dùng chung? | Có, đó chính là một group. | Thông thường cần phân biệt từng client instance để dễ quan sát. |
| Thay đổi có thể tác động | Tạo group/offset namespace mới, thay assignment. | Thay tên nhận diện/metric; không tự tạo group mới. |
| Nên chứa pod ID? | Thường không, nếu các replica cần cùng group. | Có thể dùng pod/instance suffix. |

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-validation-v1
      client-id: orders-validation-client
~~~

Nếu có nhiều consumer client trong cùng ứng dụng, cần bảo đảm client ID có thể phân biệt khi xem metrics/logs. Spring Kafka có thể thêm suffix cho concurrency theo cấu hình; hãy kiểm tra tên runtime thực tế thay vì giả định chuỗi cuối cùng luôn đúng bằng prefix.

Không đặt group ID thành `orders-validation-pod-a`, `orders-validation-pod-b` nếu mục tiêu là các pod chia sẻ cùng một workload. Làm như vậy tạo các group độc lập và mỗi group có thể đọc lại toàn bộ stream theo offset của riêng nó.

## 7. Quy ước đặt tên ổn định

Tên ID tốt giúp người trực sự cố hiểu ngay service và luồng xử lý. Một quy ước có thể dùng:

~~~text
group.id:
  <domain>-<purpose>-v<generation>

listener id:
  <topic-or-domain>-<handler>-listener

client.id prefix:
  <service>-<consumer-role>-client

pod/instance:
  <deployment-pod-name>
~~~

Ví dụ:

| Loại | Tên ví dụ | Lý do |
|---|---|---|
| group ID | `orders-validation-v1` | Thể hiện domain và workload; ổn định qua các replica. |
| listener ID | `orders-created-listener` | Nhìn vào log biết endpoint xử lý orders.created. |
| client ID prefix | `orders-validator-client` | Nhóm metrics/log của Kafka client. |
| pod ID | `orders-service-7c9d8-p2x4m` | Phân biệt instance thực tế. |

Không nên đưa build number hoặc pod ID vào group ID nếu không có chủ đích tạo group mới. Nếu mỗi lần deploy lại đổi group ID, ứng dụng có thể tạo group mới, bỏ lại committed offsets cũ và đọc từ vị trí được quyết định bởi `auto.offset.reset`.

Nếu cần migration sang group ID mới, phải có kế hoạch rõ ràng về:
- Offset bắt đầu của group mới.
- Record có thể được xử lý lại.
- Tác động lên side effect và idempotency.
- Thời điểm chuyển traffic và dừng group cũ.
- Khả năng rollback về group trước.

## 8. Log group ID và listener ID trong listener method

Một log hữu ích cần định danh luồng xử lý cùng vị trí record:

~~~java
private static final String GROUP_ID = "orders-validation-v1";
private static final String LISTENER_ID = "orders-created-listener";

@KafkaListener(
    id = LISTENER_ID,
    groupId = GROUP_ID,
    topics = "orders.created"
)
public void onOrder(ConsumerRecord<String, String> record) {
    log.info(
        "Kafka record received: groupId={}, listenerId={}, " +
        "topic={}, partition={}, offset={}, key={}",
        GROUP_ID,
        LISTENER_ID,
        record.topic(),
        record.partition(),
        record.offset(),
        record.key());

    orderService.validate(record.value());
}
~~~

Các trường nên có:
- `groupId`: group nào đang xử lý record.
- `listenerId`: endpoint/container nào đang nhận record.
- `topic`, `partition`, `offset`: vị trí chính xác trong Kafka.
- `key`: chỉ ghi nếu key không chứa dữ liệu nhạy cảm.
- `eventId`: định danh nghiệp vụ nếu có.
- `pod`/`instance`: replica nào thực sự thực hiện.
- `attempt`/`deliveryAttempt`: lần giao nếu error handler cung cấp metadata phù hợp.

Trong ví dụ, hằng số Java được khai báo cùng annotation để tránh log một group ID khác với group ID listener thực sự sử dụng. Nếu group ID đến từ profile/environment, hãy inject cùng một configuration property vào annotation và logging component, tránh hard-code hai giá trị khác nhau.

**ConsumerRecord không tự mang group ID trong Kafka record gốc.** Group ID là metadata của consumer group, không phải một field mà producer phải thêm vào mỗi message. Vì vậy, đừng nhầm `record.headers()` với group ID hiệu lực.

## 9. Dùng MDC để group ID và listener ID xuất hiện trong mọi log

Nếu mọi log trong một listener invocation cần có group ID và listener ID, có thể đưa chúng vào **Mapped Diagnostic Context (MDC)**:

~~~java
private static final String GROUP_ID = "orders-validation-v1";
private static final String LISTENER_ID = "orders-created-listener";

@KafkaListener(
    id = LISTENER_ID,
    groupId = GROUP_ID,
    topics = "orders.created"
)
public void onOrder(ConsumerRecord<String, String> record) {
    try (MDC.MDCCloseable group =
                 MDC.putCloseable("kafka.group.id", GROUP_ID);
         MDC.MDCCloseable listener =
                 MDC.putCloseable("kafka.listener.id", LISTENER_ID)) {

        MDC.put("kafka.topic", record.topic());
        MDC.put("kafka.partition", Integer.toString(record.partition()));
        MDC.put("kafka.offset", Long.toString(record.offset()));

        try {
            log.info("Start processing order");
            orderService.validate(record.value());
            log.info("Order processed");
        } finally {
            MDC.remove("kafka.topic");
            MDC.remove("kafka.partition");
            MDC.remove("kafka.offset");
        }
    }
}
~~~

Import chính:

~~~java
import org.slf4j.MDC;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
~~~

`MDC.putCloseable(...)` giúp gỡ các key tương ứng khi đóng scope. Các key topic/partition/offset được remove trong `finally` để không rò rỉ sang record kế tiếp trên cùng consumer thread.

Kafka listener thread thường được tái sử dụng. Nếu đặt MDC mà không cleanup, log của record sau có thể mang offset hoặc group ID cũ, làm điều tra incident sai lệch.

Có thể chuẩn hóa một helper:

~~~java
public final class KafkaLogContext implements AutoCloseable {

    public KafkaLogContext(
            String groupId,
            String listenerId,
            String topic,
            int partition,
            long offset) {

        MDC.put("kafka.group.id", groupId);
        MDC.put("kafka.listener.id", listenerId);
        MDC.put("kafka.topic", topic);
        MDC.put("kafka.partition", Integer.toString(partition));
        MDC.put("kafka.offset", Long.toString(offset));
    }

    @Override
    public void close() {
        MDC.remove("kafka.group.id");
        MDC.remove("kafka.listener.id");
        MDC.remove("kafka.topic");
        MDC.remove("kafka.partition");
        MDC.remove("kafka.offset");
    }
}
~~~

Sử dụng:

~~~java
try (KafkaLogContext ignored = new KafkaLogContext(
        GROUP_ID,
        LISTENER_ID,
        record.topic(),
        record.partition(),
        record.offset())) {

    orderService.validate(record.value());
}
~~~

Helper là code minh họa; ứng dụng cần cân nhắc cách bảo toàn MDC context có sẵn nếu có nhiều lớp cùng ghi các key. Một lựa chọn là dùng `MDC.putCloseable` riêng cho từng key và scope lồng nhau.

## 10. Cấu hình logging pattern

Với Logback, có thể đưa MDC keys vào pattern:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId} groupId=%X{kafka.group.id} listenerId=%X{kafka.listener.id} topic=%X{kafka.topic} partition=%X{kafka.partition} offset=%X{kafka.offset} - %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là ví dụ cấu hình Logback. Nếu dự án dùng JSON encoder hoặc structured logging, hãy đưa các MDC keys thành field riêng thay vì ghép thành một chuỗi khó truy vấn.

Một dòng log sau khi cấu hình có thể trông như:

~~~text
2026-11-15 18:30:12.123 INFO [KafkaListenerEndpointContainer#0-0-C-1]
traceId=4bf92f... groupId=orders-validation-v1
listenerId=orders-created-listener topic=orders.created
partition=2 offset=1875 - OrderListeners - Start processing order
~~~

Tên thread là ví dụ minh họa. Đừng dựa vào tên thread để suy ra group ID hoặc listener ID; hãy log các định danh riêng.

## 11. Đưa group ID vào listener header khi cần

Trong một số phiên bản Spring Kafka, `KafkaHeaders.GROUP_ID` có thể được dùng để nhận group ID trong method argument khi listener adapter cung cấp header đó. Cần kiểm tra API của version đang dùng:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void onOrder(
        ConsumerRecord<String, String> record,
        @Header(KafkaHeaders.GROUP_ID) String groupId) {

    log.info("Processing with groupId={}", groupId);
}
~~~

Import:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
~~~

Nếu version hoặc adapter không cung cấp header này, không cố đọc group ID từ `ConsumerRecord`. Dùng cấu hình listener đã biết hoặc metadata consumer được framework hỗ trợ. Với các listener có group ID khác nhau, nên có một configuration object chứa mapping rõ ràng thay vì đoán từ topic.

Một lựa chọn chẩn đoán khác là inject consumer qua header `KafkaHeaders.CONSUMER` ở phiên bản hỗ trợ và đọc `consumer.groupMetadata().groupId()` **trong listener thread**. Consumer object không thread-safe; không lưu nó vào singleton hoặc truyền sang executor để sử dụng sau khi method kết thúc.

## 12. listenerInfo không phải listener id

Spring Kafka có khái niệm **listener info** có thể được cấu hình trên container properties và đưa vào record headers theo API phiên bản hỗ trợ. Đây là metadata do ứng dụng đặt, không đồng nghĩa `@KafkaListener(id=...)` và cũng không phải Kafka group ID.

Ví dụ:

~~~java
factory.getContainerProperties()
       .setListenerInfo("orders-validation-pipeline");
~~~

Listener có thể nhận metadata này qua `KafkaHeaders.LISTENER_INFO` nếu cấu hình/version hỗ trợ:

~~~java
public void onOrder(
        ConsumerRecord<String, String> record,
        @Header(KafkaHeaders.LISTENER_INFO) String listenerInfo) {

    log.info("listenerInfo={}", listenerInfo);
}
~~~

Phân biệt:

| Giá trị | Nguồn | Mục đích |
|---|---|---|
| `@KafkaListener(id=...)` | Annotation endpoint | Quản lý container và định danh listener. |
| `groupId` | Annotation hoặc consumer factory | Kafka group membership và offset. |
| `listenerInfo` | `ContainerProperties` | Metadata tùy chỉnh đưa tới listener/message. |

Không đưa secret, token hoặc dữ liệu cá nhân vào listener info. Vì nó có thể được đưa vào message header hoặc log tùy cách dùng, hãy giới hạn nội dung và kiểm soát việc truyền qua retry/DLT.

## 13. Tìm listener container bằng listener id

`KafkaListenerEndpointRegistry` cho phép lấy container theo listener ID. Đây là một lý do thực tế để listener ID phải ổn định:

~~~java
@Service
public class OrderListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener orders-created-listener not found");
        }

        container.pause();
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener orders-created-listener not found");
        }

        container.resume();
    }
}
~~~

Import chính:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;
~~~

Registry được quản lý trong Spring application context hiện tại. Trong deployment nhiều pod, gọi registry trên pod A **không điều khiển container trong pod B**. Nếu cần thao tác toàn deployment, phải điều phối lệnh tới các instance hoặc dùng desired-state/control plane.

Khi listener có concurrency, registry thường trả về container cha tương ứng listener; child container quản lý consumer thread riêng. Đừng giả định listener ID bằng child container ID hoặc một partition cụ thể.

## 14. Dùng listener id khi xử lý application events

Spring Kafka phát nhiều event chứa thông tin container/listener. Ví dụ `NonResponsiveConsumerEvent`, idle event, pause/resume event hoặc stopped event có thể cung cấp listener ID theo API tương ứng.

Ví dụ:

~~~java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Non-responsive consumer: listenerId={}, elapsedMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped: listenerId={}, reason={}",
            event.getListenerId(),
            event.getReason());
    }
}
~~~

Các import và event field cụ thể có thể khác theo phiên bản Spring Kafka; kiểm tra class API đang dùng trước khi copy code vào dự án. Ví dụ minh họa mục tiêu chính là **listener ID giúp liên hệ event với endpoint/container**. Group ID và pod ID cần được log bổ sung nếu event không cung cấp trực tiếp.

Một event listener nên làm việc nhanh: ghi log, cập nhật metric hoặc enqueue thông tin cho incident handler. Không thực hiện HTTP call dài hoặc database transaction đồng bộ trong callback phát event.

## 15. Log group/listener trong retry và DLT

Khi listener xử lý lỗi, cùng một event có thể xuất hiện qua nhiều attempt hoặc topic:

~~~text
orders.created
    |
    v
orders-created-listener
    |
    +-- attempt 1: exception
    |
    v
retry topic / blocking retry
    |
    +-- attempt 2: exception
    |
    v
DLT
~~~

Trong log cần phân biệt:
- **Group ID của consumer đang đọc topic hiện tại.** Consumer group đọc retry topic có thể khác group đọc topic chính.
- **Listener ID của endpoint hiện tại.** Retry/DLT listener có thể là một endpoint khác.
- **Original topic/partition/offset** của record nguồn.
- **Current topic/partition/offset** của lần giao hiện tại.
- **Delivery attempt/recovery metadata** theo error handler.
- **Event ID** ổn định để nhận diện cùng một nghiệp vụ.

Ví dụ structured log:

~~~json
{
  "event": "kafka_record_recovered",
  "groupId": "orders-retry-v1",
  "listenerId": "orders-retry-listener",
  "topic": "orders-retry-1000",
  "partition": 1,
  "offset": 902,
  "originalTopic": "orders.created",
  "originalPartition": 2,
  "originalOffset": 1875,
  "eventId": "order-4821-created",
  "attempt": 3
}
~~~

JSON là schema log minh họa. Header metadata chính xác phụ thuộc recoverer và phiên bản. Đừng mặc định mọi DLT consumer dùng group ID hoặc listener ID của listener gốc; đó có thể là một luồng tiêu thụ riêng.

Nếu retry dùng cùng consumer group hay một group khác, điều đó ảnh hưởng assignment và offset. Hãy cấu hình rõ ràng và log **group thực tế đang đọc retry topic**, thay vì chỉ ghi group ID của luồng ban đầu.

## 16. Group ID và listener ID khi có nhiều listener

Một ứng dụng có thể có nhiều listener:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void validateOrder(String payload) {
    // ...
}

@KafkaListener(
    id = "payments-created-listener",
    groupId = "payments-risk-v1",
    topics = "payments.created"
)
public void evaluatePayment(String payload) {
    // ...
}
~~~

Ở đây hai listener có ID và group ID khác nhau. Log cần giúp phân biệt chúng ngay cả khi cùng chạy trong một pod.

Một trường hợp khác là hai listener cùng subscribe topic và dùng cùng group ID:

~~~java
@KafkaListener(
    id = "orders-handler-a",
    groupId = "orders-shared-v1",
    topics = "orders"
)
public void handleA(String payload) {
    // ...
}

@KafkaListener(
    id = "orders-handler-b",
    groupId = "orders-shared-v1",
    topics = "orders"
)
public void handleB(String payload) {
    // ...
}
~~~

Hai endpoint sẽ tham gia cùng consumer group theo cấu hình subscription và container; chúng không tự tạo hai bản sao độc lập của toàn bộ stream. Nếu nghiệp vụ cần cả hai handler nhận mọi record, dùng group ID độc lập hoặc một mô hình fan-out phù hợp.

**Không dùng listener ID để suy luận group ID khi annotation có override.** Luôn xem group ID hiệu lực trong cấu hình hoặc runtime metadata.

## 17. Group ID và client ID trong Kafka logs

Kafka broker/client logs thường có các thông tin như group ID, member ID, client ID, generation hoặc coordinator. Khi group rebalance, log có thể thể hiện:
- Member join/leave.
- Partition assignment/revocation.
- Heartbeat hoặc poll timeout.
- Commit offset thất bại.
- Consumer bị fence hoặc coordinator unavailable.

Để đối chiếu với log ứng dụng, nên giữ một mapping ổn định:

~~~text
service       = orders-service
pod           = orders-service-7c9d8-p2x4m
group.id      = orders-validation-v1
listener.id   = orders-created-listener
client.id     = orders-validation-client-0
topic         = orders.created
partition     = 2
offset        = 1875
~~~

Kafka broker không nhất thiết biết Spring listener ID vì đây là metadata phía ứng dụng. `client.id` và group ID mới là các thông tin Kafka client có thể đưa vào log/protocol theo tình huống. Vì vậy, muốn liên hệ broker logs với Spring container, phải ghi listener ID trong ứng dụng và dùng cùng pod/client ID để nối các nguồn log.

## 18. Log level hỗ trợ chẩn đoán

Khi điều tra listener lifecycle hoặc consumer group, có thể tăng log level có giới hạn:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
    org.springframework.kafka.config: DEBUG
    org.apache.kafka.clients.consumer: INFO
~~~

Mức `DEBUG` có thể tạo nhiều log khi traffic lớn; chỉ bật trong thời gian điều tra và cân nhắc mức log trên từng pod. Với sự cố group coordination, có thể cần tăng mức log Kafka client có mục tiêu theo phiên bản, nhưng không nên bật toàn bộ package `org.apache.kafka` ở `TRACE` lâu dài.

Log level không thay thế metric:
- Log cung cấp chi tiết một lần assignment, error hoặc record.
- Metric cho xu hướng lag, throughput, rebalance và failure rate.
- Trace liên kết các bước xử lý trong nhiều service.
- Group ID/listener ID là khóa tương quan để ghép các nguồn đó.

## 19. Thiết kế structured log

Một record log nên có các field ổn định, có ý nghĩa và giới hạn cardinality phù hợp:

| Field | Loại dữ liệu | Gợi ý |
|---|---|---|
| `service` | Service name | Tên ứng dụng. |
| `instance` | Pod/host | Giá trị runtime, phân biệt replica. |
| `groupId` | Kafka group | Ổn định theo workload. |
| `listenerId` | Spring endpoint | Ổn định theo listener. |
| `clientId` | Kafka client | Hữu ích để liên hệ client metrics/logs. |
| `topic` | Topic | Tên topic. |
| `partition` | Integer | Partition đang xử lý. |
| `offset` | Long | Vị trí record. |
| `eventId` | Business identifier | Dùng cho audit/deduplication, không nên làm metric label nếu cardinality lớn. |
| `attempt` | Integer | Số lần giao/retry nếu có metadata chính xác. |
| `traceId` | Trace identifier | Liên hệ distributed trace, không thay event ID. |
| `outcome` | Enum | `success`, `failure`, `recovered`, `dlt`. |

Không log:
- Password, SASL secret, TLS private key hoặc access token.
- Payload đầy đủ khi có thông tin cá nhân/tài chính.
- Header chứa credential hoặc baggage không được kiểm soát.
- Event ID, order ID hoặc user ID thành metric labels vô hạn.
- Group ID được tạo động từ từng request.

Một log có đủ context giúp tìm đúng consumer mà không cần mở payload.

## 20. Metric labels: group ID và listener ID có phù hợp không?

Group ID và listener ID thường có cardinality tương đối thấp nếu được đặt tên ổn định, nên có thể dùng làm metric labels trong nhiều hệ thống. Nhưng vẫn cần kiểm soát số lượng listener/group và tránh tạo ID mới theo mỗi deployment/request.

Ví dụ metric ứng dụng:
- `app.kafka.listener.records.processed`
- `app.kafka.listener.processing.duration`
- `app.kafka.listener.errors`
- `app.kafka.listener.rebalances`
- `app.kafka.listener.nonresponsive.events`

Các tên trên là ví dụ instrumentation, không phải tên metric mặc định bắt buộc của Spring Kafka.

Labels có thể gồm:
- `group_id`
- `listener_id`
- `topic` (nếu số topic được quản trị)
- `outcome`
- `application`

Không đưa `partition`, `offset`, `event_id`, `order_id`, `trace_id` hoặc payload vào metric label nếu có thể tạo hàng triệu giá trị. Những trường này phù hợp hơn với logs hoặc traces.

Khi nhiều pod dùng cùng group ID/listener ID, metric tổng hợp có thể gộp theo workload; thêm `instance` khi cần chẩn đoán replica, nhưng nhớ giới hạn số series theo số pod.

## 21. Dùng group ID/listener ID khi điều tra lag

Lag thường được quan sát theo consumer group và topic-partition. Nếu chỉ nhìn topic, không thể biết group nào đang chậm vì nhiều group có committed offset riêng.

Ví dụ:

~~~text
Topic: orders, partition 2

group.id = orders-validation-v1
  committed offset = 1800
  log end offset   = 2000
  lag              = 200

group.id = orders-analytics-v1
  committed offset = 1950
  log end offset   = 2000
  lag              = 50
~~~

Group validation đang chậm hơn analytics. Để xác định listener nào chịu trách nhiệm, đối chiếu group ID với listener ID và pod/assignment logs.

Lệnh kiểm tra group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-validation-v1
~~~

Nếu cần xem member và assignment, dùng option phù hợp với phiên bản Kafka CLI:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-validation-v1 \
  --members --verbose
~~~

CLI hiển thị thông tin group, member, offset và lag theo khả năng phiên bản; **nó không tự biết Spring listener ID**. Muốn ánh xạ partition owner tới listener, ghép với log/metrics của ứng dụng.

## 22. Các lỗi đặt tên và cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi pod xử lý lại toàn bộ topic | Group ID có pod suffix, khiến mỗi pod là group độc lập. | Dùng group ID chung cho workload cần chia partition. |
| Đổi listener ID làm consumer bắt đầu đọc lại | `idIsGroup=true` và group ID không khai báo nên ID được dùng làm group ID. | Khai báo group ID rõ ràng hoặc đặt `idIsGroup=false` khi dùng factory group ID. |
| Hai listener không nhận đủ mỗi listener một bản record | Cùng group ID và subscribe topic nên chia assignment. | Dùng group ID riêng nếu cần fan-out độc lập. |
| Không tìm thấy container trong registry | Dùng sai listener ID hoặc listener chưa đăng ký/đang cấu hình không tạo container. | Kiểm tra `@KafkaListener(id=...)` và application context. |
| Log của các pod không phân biệt được | Chỉ log group ID và listener ID, thiếu instance/pod. | Thêm pod/instance ID và client ID. |
| Broker logs không tìm được listener ID | Listener ID là metadata Spring phía ứng dụng. | Log cả listener ID và client ID/group ID để nối nguồn. |
| Metric có quá nhiều series | Dùng event ID, offset hoặc partition động làm labels. | Chuyển dữ liệu chi tiết sang logs/traces. |
| Log record sau mang offset record trước | MDC không được cleanup trên consumer thread tái sử dụng. | Dùng scope/try-finally và remove MDC keys. |
| Retry/DLT log mang group không đúng | Dùng group của listener gốc thay vì group đang đọc retry/DLT. | Log group hiệu lực của từng endpoint. |

## 23. Runbook: Không biết listener nào đang tiêu thụ một partition

Giả sử Kafka CLI cho biết `orders-2` đang thuộc một member của group `orders-validation-v1`, nhưng đội ứng dụng chưa xác định listener nào đang xử lý.

**Bước 1 — Xác nhận group.** Chạy lệnh describe consumer group và ghi lại group ID, member/client ID, host và partition assignment.

**Bước 2 — Tìm pod.** Đối chiếu client ID, host hoặc member metadata với pod/instance trong Kubernetes và log aggregation.

**Bước 3 — Tìm listener ID.** Tra structured logs của pod tại cùng thời điểm, tìm `groupId=orders-validation-v1`, `topic=orders`, `partition=2` và listener ID.

**Bước 4 — Kiểm tra container.** Xác nhận listener ID có trong `KafkaListenerEndpointRegistry`, container đang running hay paused, và concurrency thực tế.

**Bước 5 — Đối chiếu cấu hình.** Kiểm tra `@KafkaListener(id, groupId, idIsGroup, clientIdPrefix)` và consumer factory để biết group ID runtime đến từ đâu.

**Bước 6 — Kiểm tra lag/processing.** So sánh committed offset, throughput, listener errors, retry/DLT và dependency latency.

**Bước 7 — Khắc phục đúng endpoint.** Nếu cần pause/resume, gọi container theo listener ID ở đúng instance/owner hoặc qua control plane toàn deployment.

**Bước 8 — Xác nhận.** Theo dõi assignment mới, logs có định danh rõ và offset tiến trở lại.

Không kết luận listener ID từ group ID bằng cách cắt chuỗi hoặc suy đoán naming convention; quan hệ này phải được ghi rõ trong cấu hình/logging.

## 24. Runbook: Consumer group mới xuất hiện sau deployment

Một deployment có thể vô tình tạo group mới nếu group ID được suy ra từ listener ID hoặc property thay đổi.

1. So sánh group ID thực tế trước/sau deployment trong Kafka CLI và logs.
2. Kiểm tra annotation `groupId`, `idIsGroup`, consumer factory default và profile/environment.
3. Xác định group mới đã có committed offset chưa; nếu chưa, kiểm tra `auto.offset.reset`.
4. Đánh giá liệu group mới đang đọc lại toàn bộ dữ liệu hoặc bắt đầu từ offset mới nhất.
5. Nếu đổi group ID không chủ đích, sửa cấu hình để khôi phục group ID cũ theo kế hoạch; tránh chạy hai group đồng thời gây side effect trùng.
6. Nếu migration group ID là có chủ đích, xác định start offset, replay semantics, idempotency và thời điểm dừng group cũ.
7. Theo dõi lag và business effects ở cả group cũ/mới trong giai đoạn chuyển tiếp.

**Đừng xóa group cũ hoặc reset offset ngay khi thấy group mới.** Trước hết phải hiểu dữ liệu nào đã được xử lý, consumer nào còn active và hệ thống có khả năng replay an toàn không.

## 25. Checklist triển khai

- [ ] Mỗi listener có `id` ổn định và duy nhất trong application context.
- [ ] Mỗi workload có group ID được đặt theo nghiệp vụ và ổn định qua các replica.
- [ ] `@KafkaListener.groupId` và consumer factory default có quy tắc override rõ ràng.
- [ ] Hiểu `idIsGroup` và không để listener ID vô tình tạo group ID mới.
- [ ] `client.id`/`clientIdPrefix` giúp phân biệt Kafka client instances.
- [ ] Log có group ID, listener ID, instance/pod, topic, partition và offset.
- [ ] MDC keys được cleanup để không rò rỉ giữa các record.
- [ ] Retry/DLT log ghi group ID và listener ID của endpoint đang thực sự đọc topic đó.
- [ ] Event/registry operations dùng listener ID, không nhầm với group ID.
- [ ] Metric labels có cardinality được kiểm soát.
- [ ] Không log credential, payload nhạy cảm hoặc metadata không cần thiết.
- [ ] Có runbook ánh xạ Kafka group member/client ID tới pod và listener container.
- [ ] Có kế hoạch rõ ràng trước khi đổi group ID hoặc replay dữ liệu.

## 26. Kết luận

**Group ID và listener ID trả lời hai câu hỏi khác nhau.** Group ID cho biết Kafka consumer thuộc nhóm nào, chia partition và lưu committed offset ra sao. Listener ID cho biết endpoint/container nào trong Spring application đang thực hiện công việc và là khóa để quản lý container hoặc liên hệ application events.

Khi log cả hai cùng với client ID, pod/instance, topic-partition-offset và event ID, đội vận hành có thể nối Kafka group metadata với Spring listener logs mà không nhầm lẫn định danh. Đặt tên ổn định, khai báo group ID rõ ràng, cleanup MDC và kiểm soát metric cardinality giúp việc điều tra rebalance, lag, retry và DLT nhanh hơn, đồng thời tránh thay đổi group ngoài ý muốn làm ảnh hưởng delivery behavior.
