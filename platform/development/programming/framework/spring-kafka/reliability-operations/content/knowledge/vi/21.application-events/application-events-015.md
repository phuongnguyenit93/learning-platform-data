# Listener ID và condition để lọc event

Trong Spring Kafka, listener container không chỉ nhận message từ Kafka rồi gọi @KafkaListener. Nó còn phát ra các **Spring Application Events** phản ánh trạng thái vận hành: consumer bắt đầu hoặc dừng, container idle, partition được pause/resume, consumer không phản hồi poll đúng kỳ vọng, v.v.

Một ứng dụng có thể có hàng chục Kafka listeners cùng phát events vào **ApplicationContext**. Nếu mọi event handler đều phản ứng với mọi container, việc theo dõi sẽ nhiễu, alert nhầm hoặc một tác vụ điều khiển có thể tác động sai listener. Để giải quyết, Spring Kafka cung cấp thông tin **listener ID** trong các container events; Spring Framework cung cấp thuộc tính **condition** của **@EventListener** để lọc event trước khi gọi handler.

Bài học trong chương **Application events** của **Spring Kafka Reliability Operations** tập trung vào:

- Thiết lập listener ID ổn định và hiểu nó khác consumer group ID như thế nào.
- Đọc listener ID từ Application Events của Spring Kafka.
- Dùng **@EventListener(condition = "...")** với Spring Expression Language (SpEL) để chỉ nhận event của listener cần quan tâm.
- Xử lý đúng khi listener có concurrency lớn hơn một, dẫn đến child containers và listener IDs có hậu tố.
- Phân biệt lọc bằng annotation với kiểm tra trong Java code.
- Tránh xử lý event sai thread, tránh alert giả và điều khiển sai container trong production.

## 1. Spring Kafka Application Events là gì?

Một Kafka listener container là thành phần Spring quản lý vòng đời Kafka consumer và việc gọi listener. Trong quá trình hoạt động, nó có thể publish events qua Spring **ApplicationEventPublisher**. Các bean trong cùng ApplicationContext có thể nhận những events đó bằng @EventListener.

~~~mermaid
flowchart LR
    K["Kafka broker"] --> C1["Container orders-consumer"]
    K --> C2["Container payments-consumer"]
    C1 --> A["Spring ApplicationEventPublisher"]
    C2 --> A
    A --> E1["@EventListener idle handler"]
    A --> E2["@EventListener pause handler"]
    A --> E3["@EventListener lifecycle handler"]
~~~

Cách xử lý này tách nghiệp vụ consume message khỏi phần quan sát hoạt động container. Ví dụ:

- Listener xử lý order records bình thường.
- Container bắt đầu idle do không có records.
- Spring Kafka publish ListenerContainerIdleEvent.
- Một @EventListener nhận event và cập nhật trạng thái quan sát.

Application events là events **nội bộ Spring application**. Chúng **không mặc định là Kafka records** được gửi lên một topic và không phải cơ chế giao tiếp bền vững xuyên các service.

### 1.1 Một số loại event hữu ích

| Event | Tình huống tiêu biểu | Cách dùng vận hành |
|---|---|---|
| ListenerContainerIdleEvent | Không có records trong khoảng idle đã cấu hình | Quan sát listener đang idle |
| ListenerContainerNoLongerIdleEvent | Listener có records trở lại sau idle | Xác nhận luồng tiêu thụ hoạt động lại |
| ConsumerPausedEvent | Consumer đã pause partitions | Ghi nhận trạng thái backpressure |
| ConsumerResumedEvent | Consumer resume partitions | Xác nhận hoạt động tiêu thụ trở lại |
| ConsumerStartedEvent | Consumer container thread đã khởi động | Theo dõi vòng đời |
| ConsumerStoppedEvent | Consumer dừng vì một lý do | Cảnh báo shutdown bất thường |
| NonResponsiveConsumerEvent | Poll lâu bất thường so với ngưỡng theo dõi | Điều tra consumer bị chặn |
| ConsumerPartitionPausedEvent | Một partition được pause | Quan sát điều tiết theo partition |
| ConsumerPartitionResumedEvent | Một partition được resume | Quan sát trạng thái partition |

Danh sách khả dụng và các accessor có thể khác giữa các phiên bản Spring Kafka. Chỉ đăng ký event types thực sự có trong dependency của dự án, không áp dụng API mới cho version cũ.

### 1.2 Không phải event nào cũng là lỗi

ListenerContainerIdleEvent **không tự chứng minh Kafka bị hỏng**. Topic có thể hợp lệ nhưng không có record mới. ConsumerPausedEvent có thể là kết quả của một lệnh pause do operator chủ động thực hiện. ConsumerStoppedEvent có thể xuất hiện trong rolling deployment bình thường.

Handler cần hiểu cả **event type**, **listener ID**, **nguyên nhân** và **ngữ cảnh vận hành** trước khi tạo alert hoặc hành động tự động.

## 2. Listener ID dùng để làm gì?

Với @KafkaListener, thuộc tính **id** định danh listener endpoint/container trong Spring.

~~~java
@Component
public class OrdersListener {

    @KafkaListener(
        id = "orders-projection",
        topics = "orders.created",
        groupId = "orders-projection-group"
    )
    public void onOrder(OrderCreated event) {
        // Business processing.
    }
}
~~~

Ở đây:

- **orders-projection** là ID của @KafkaListener endpoint trong ứng dụng.
- **orders.created** là Kafka topic nguồn.
- **orders-projection-group** là Kafka consumer group ID.

Một tác dụng thiết thực của listener ID là truy xuất container trong **KafkaListenerEndpointRegistry**:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-projection");
~~~

Nếu không đặt ID chủ động, Spring có thể sinh ID dựa trên cách đăng ký endpoint/container. ID tự sinh khó duy trì ổn định qua refactor và không phù hợp để làm contract cho monitoring hoặc routing events.

### 2.1 Listener ID, group ID và client ID khác nhau

| Thuộc tính | Mục đích | Có dùng thay listener ID khi lọc Spring events? |
|---|---|---|
| @KafkaListener.id | Định danh endpoint/container trong Spring | Có, là cơ sở định danh |
| @KafkaListener.groupId | Kafka consumer group quản lý partition assignment và offsets | Không mặc định |
| @KafkaListener.clientIdPrefix | Prefix tạo Kafka consumer client.id | Không mặc định |
| Topic name | Dữ liệu Kafka consumer subscribe | Không mặc định |
| Event listenerId | ID trong Application Event do container phát | Dùng để lọc; có thể có child suffix |

Kafka **group ID** thường giống nhau giữa nhiều pods và consumers cùng chia tải. Listener ID được dùng để phân biệt endpoints trong một application context; event của một child consumer có thể chứa ID mở rộng từ parent.

### 2.2 Cẩn thận với idIsGroup

Trong Spring Kafka, @KafkaListener.id có thể được dùng làm consumer group ID khi không cung cấp groupId riêng và thuộc tính **idIsGroup** giữ giá trị mặc định true.

Ví dụ:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders.created"
)
public void onOrder(OrderCreated event) {
    // ...
}
~~~

Nếu không có cấu hình groupId rõ ràng, group.id thực tế có thể thành **orders-projection**, thay vì giá trị group.id trong ConsumerFactory như developer tưởng.

Cách dễ đọc và ít gây nhầm lẫn:

~~~java
@KafkaListener(
    id = "orders-projection",
    topics = "orders.created",
    groupId = "orders-projection-group"
)
~~~

Hoặc khi chủ đích dùng group ID từ consumer factory, cấu hình idIsGroup=false theo API và phiên bản đang sử dụng.

**Đổi listener ID không nên vô tình làm đổi Kafka group ID**. Một group ID mới có thể tạo committed-offset namespace mới, dẫn đến replay hoặc skip records tùy auto.offset.reset và trạng thái offsets.

## 3. Event có listenerId như thế nào?

Spring Kafka container events thường cung cấp accessor **getListenerId()**, cho biết container/listener đã phát event.

Ví dụ handler quan sát idle:

~~~java
@Component
public class KafkaIdleLogger {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaIdleLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Kafka listener idle: listenerId={}, idleTime={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

Method này nhận mọi ListenerContainerIdleEvent trong ApplicationContext mà nó được đăng ký, bất kể event thuộc orders, payments hay inventory.

Nếu cùng ứng dụng có ba listeners:

~~~text
orders-projection
payments-settlement
inventory-sync
~~~

Một handler không lọc có thể nhận idle events từ cả ba. Nếu handler dùng event đó để alert theo SLA của orders, nó sẽ tạo alert sai cho payments hoặc inventory.

### 3.1 Listener ID có thể khác ID trong annotation

Với concurrency=1, listenerId của một event có thể tương đương ID endpoint. Với **ConcurrentMessageListenerContainer**, Spring Kafka thường tạo nhiều child containers và định danh child bằng hậu tố, ví dụ:

~~~text
Parent @KafkaListener id:
  orders-projection

Child container identifiers:
  orders-projection-0
  orders-projection-1
  orders-projection-2
~~~

Đây là một quy ước phổ biến, không nên hardcode giả định suffix trong mọi custom container hoặc mọi phiên bản. Cần quan sát **giá trị event.getListenerId() thực tế** trên runtime.

Nếu filter chỉ so sánh equality với chuỗi orders-projection, nó có thể bỏ qua child events có hậu tố.

### 3.2 Lọc theo container là lọc theo nguồn

Listener ID xác định **container phát event**, không nhất thiết Kafka topic, Kafka partition hay record cụ thể.

Một container có thể subscribe nhiều topics. Một group có thể có nhiều containers. Một container concurrency > 1 có thể gồm nhiều child consumers.

Nếu cần lọc theo partition hoặc loại lỗi, phải dùng metadata tương ứng hoặc business logic bổ sung. Lọc listener ID một mình không đủ để kết luận partition nào đang lỗi.

## 4. @EventListener(condition) xử lý ở đâu?

Spring Framework cung cấp **condition** trên @EventListener. Condition là một biểu thức **Spring Expression Language (SpEL)**, được đánh giá trước khi gọi listener method.

Nếu condition trả về false, Spring **không gọi method đó** cho event tương ứng.

Ví dụ đơn giản:

~~~java
@Component
public class OrdersIdleEvents {

    @EventListener(
        condition = "#root.event.listenerId == 'orders-projection'"
    )
    public void onOrdersIdle(ListenerContainerIdleEvent event) {
        // Chỉ xử lý event có listenerId bằng orders-projection.
    }
}
~~~

Ở đây:

- Spring chọn method vì kiểu tham số là ListenerContainerIdleEvent.
- SpEL đọc listenerId từ event.
- Method chỉ chạy nếu điều kiện đúng.

Đây là **hai tầng lọc**: tầng **event type** và tầng **event property**. Condition không khiến Spring Kafka ngừng publish event; nó chỉ quyết định handler này có được gọi hay không.

### 4.1 SpEL có thể truy cập event

Trong expression của Spring @EventListener, event có thể được truy cập qua root object, ví dụ **#root.event**, hoặc các cú pháp event/argument được hỗ trợ bởi Spring Framework version hiện hành.

Ví dụ:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-')"
)
public void onIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

Dùng #root.event trong ví dụ nhằm làm rõ expression đang tham chiếu **event được phát**, không phải biến Java local của method.

Nếu sử dụng biểu thức dựa trên tên parameter, ví dụ #event, cần chú ý cấu hình giữ tên tham số lúc compile và semantics của Spring Framework version. Với tên param được compile thiếu metadata, biểu thức theo tên có thể không hoạt động như mong đợi. Root event hoặc argument index thường rõ ràng hơn trong ví dụ dùng chung.

### 4.2 Condition nên ngắn và không có side effect

SpEL filter được đánh giá trong quá trình dispatch Application Event. Không dùng condition để:

- Thực hiện HTTP request.
- Gọi database.
- Thay đổi trạng thái container.
- Tăng/giảm metric hoặc gửi Kafka record.
- Chạy logic nặng, có thể block consumer event thread.

Hãy dùng condition để lọc nhanh trên metadata bất biến, rồi làm phần xử lý chính trong method.

## 5. Ví dụ lọc ListenerContainerIdleEvent theo ID

Giả sử chỉ muốn theo dõi idle của orders-projection.

### 5.1 Lọc equality

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener(
        condition = "#root.event.listenerId == 'orders-projection'"
    )
    public void handle(ListenerContainerIdleEvent event) {
        log.warn(
            "Orders consumer idle: listenerId={} idleMs={}",
            event.getListenerId(),
            event.getIdleTime()
        );
    }
}
~~~

Equality phù hợp khi event.listenerId chính xác là orders-projection và không có suffix. Nếu listener container có concurrency và child IDs, equality có thể bỏ sót events.

### 5.2 Lọc bằng startsWith

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void handle(ListenerContainerIdleEvent event) {
        log.info(
            "Orders idle from child container: {}",
            event.getListenerId()
        );
    }
}
~~~

Predicate này nhận cả orders-projection và orders-projection-0, -1, -2. Tuy nhiên, nó cũng nhận một ID như **orders-projection-v2**.

Vì vậy, startsWith cần **quy tắc đặt tên tránh trùng prefix** hoặc một predicate chặt hơn.

### 5.3 Predicate theo suffix child numeric

Nếu ứng dụng sử dụng convention cụ thể parent ID + dấu gạch ngang + số, có thể viết:

~~~java
@EventListener(
    condition =
        "#root.event.listenerId == 'orders-projection' " +
        "|| #root.event.listenerId matches '^orders-projection-[0-9]+$'"
)
public void onIdle(ListenerContainerIdleEvent event) {
    // Chỉ nhận parent và các child ID theo convention đã chọn.
}
~~~

Biểu thức minh họa cách dùng SpEL **matches** cho regular expression. Hãy đối chiếu IDs runtime và Spring expression parsing với phiên bản thực tế trước khi dùng pattern làm contract lâu dài.

Dùng regex phức tạp trong annotation có thể khó bảo trì; khi logic nhiều nhánh hoặc cần cấu hình động, chuyển sang lọc bằng Java code thường dễ hơn.

## 6. Bật idle event để có event mà lọc

Không thể chỉ khai báo @EventListener rồi mong ListenerContainerIdleEvent luôn xuất hiện. Container cần được cấu hình khoảng **idleEventInterval** thích hợp.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties()
           .setIdleEventInterval(10_000L);

    return factory;
}
~~~

Ví dụ minh họa khoảng 10 giây. Thời điểm chính xác và tần suất phát event còn phụ thuộc poll, container scheduler và Spring Kafka version.

### 6.1 Idle không tương đương failure

Listener idle có thể xảy ra khi:

- Producer không có event mới.
- Topic hoạt động nhưng lưu lượng thấp.
- Consumer đã đọc đến log end.
- Consumer đang paused.
- Partition assignment thay đổi.
- Consumer có vấn đề thực sự khiến records không tới listener.

Idle event đơn lẻ chưa đủ để alert severity cao. Nên đối chiếu producer rate, consumer lag, assignment, pause status, poll metrics và các chỉ số business freshness.

### 6.2 Idle duration là metadata, không phải bằng chứng mất dữ liệu

Nếu event.getIdleTime() cho biết listener idle bao lâu, đó là một số liệu quan sát. Nó không chứng minh Kafka broker không có records, cũng không có nghĩa consumer đã ngừng poll.

Với service chỉ nhận đơn hàng theo mùa hoặc theo lịch, idle vài phút có thể hoàn toàn bình thường. Với hệ thống liên tục nhận giao dịch, idle đột ngột có thể là tín hiệu điều tra.

## 7. Lọc pause/resume events theo listener

Spring Kafka có thể publish **ConsumerPausedEvent** và **ConsumerResumedEvent** khi consumer được pause/resume theo lifecycle.

~~~java
@Component
public class OrdersPauseMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
            "Orders Kafka consumer paused: id={}, partitions={}",
            event.getListenerId(),
            event.getPartitions()
        );
    }

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
            "Orders Kafka consumer resumed: id={}, partitions={}",
            event.getListenerId(),
            event.getPartitions()
        );
    }
}
~~~

Với concurrent container, có thể có một event tương ứng mỗi child/consumer hoặc những partition được pause. Đừng suy ra **toàn bộ listener đã pause** chỉ vì nhận một ConsumerPausedEvent.

### 7.1 Pause requested khác consumer paused

Khi ứng dụng gọi container.pause(), đây là một **yêu cầu**. Container áp dụng pause ở điểm thích hợp trên consumer thread. Nếu bật pauseImmediate, pause có thể có hiệu lực sau record hiện tại; nếu không, container có thể đợi xử lý xong records của poll.

Do đó:

- Một lời gọi container.pause() return không đồng nghĩa consumer đã paused ngay.
- ConsumerPausedEvent là một tín hiệu về việc pause thực tế.
- Với concurrency > 1, các child có thể pause ở những thời điểm khác nhau.
- Nếu cần trạng thái parent, dùng API như isConsumerPaused() theo container/version thích hợp và quan sát đủ children.

### 7.2 Không dùng event pause làm lệnh pause lặp

Một handler ConsumerPausedEvent được gọi vì container đã pause; nó thường nên **ghi nhận trạng thái**, không gọi container.pause() một lần nữa vô điều kiện.

Tương tự, một handler ConsumerResumedEvent không nên gửi resume lặp lại trong vòng tuần hoàn.

## 8. Lọc lifecycle events

Application events còn giúp quan sát consumer khởi động và dừng. Ví dụ:

~~~java
@Component
public class OrdersLifecycleMonitor {

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Orders consumer started: {}", event.getListenerId());
    }

    @EventListener(
        condition = "#root.event.listenerId.startsWith('orders-projection')"
    )
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
            "Orders consumer stopped: {}, reason={}",
            event.getListenerId(),
            event.getReason()
        );
    }
}
~~~

Đoạn code minh họa các event types và accessor trên dòng Spring Kafka tương ứng. Nếu version đang dùng có API hoặc enum lý do dừng khác, cần điều chỉnh imports/methods.

### 8.1 Không cảnh báo mọi stop là sự cố

Một consumer có thể dừng vì:

- Application shutdown.
- Rolling deployment.
- User/operator stop.
- Authentication hoặc authorization problem.
- Error nghiêm trọng.
- Các nguyên nhân khác do framework định nghĩa.

Phải kết hợp **reason**, trạng thái deployment và expected lifecycle. Nếu không, mỗi lần deploy có thể tạo một alarm “consumer crashed” dù đó là shutdown bình thường.

### 8.2 Phân biệt lifecycle của container và consumer

Một @KafkaListener có thể tương ứng parent ConcurrentMessageListenerContainer và nhiều child consumer instances. ConsumerStartedEvent có thể được phát ở cấp child. Số events có thể lớn hơn số annotation @KafkaListener.

Khi tính toán healthy instance count, không dùng “một event = một listener annotation”. Cần group theo listener ID, child consumer client ID và assignment phù hợp.

## 9. Condition theo event type và listenerId

Method argument trong @EventListener là filter theo **class của event**. Condition là filter theo **metadata của instance**.

Ví dụ cùng một ApplicationContext có ba loại event:

~~~text
ListenerContainerIdleEvent(listenerId=orders-projection-0)
ConsumerPausedEvent(listenerId=orders-projection-0)
ConsumerStoppedEvent(listenerId=payments-collector-0)
~~~

Handler sau chỉ nhận idle events thuộc orders:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-projection')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

Nó không nhận ConsumerPausedEvent của orders, vì kiểu method parameter không khớp.

Nếu muốn quan sát nhiều event types, có thể tạo nhiều methods với cùng predicate hoặc gom logic vào một service thông thường.

### 9.1 Không nhầm @EventListener(condition) với @KafkaListener filter

Spring Kafka còn có **RecordFilterStrategy** và cơ chế filter records trước khi business listener xử lý. Đây là thứ khác:

| Kỹ thuật | Lọc loại dữ liệu nào? |
|---|---|
| @EventListener(condition) | Spring Application Events, ví dụ ConsumerPausedEvent |
| RecordFilterStrategy | Kafka ConsumerRecord nhận từ broker |
| @KafkaListener(topics, topicPattern) | Kafka topics listener subscribe |
| Kafka consumer assignment | Partitions thuộc consumer trong group |
| @KafkaListener(groupId) | Consumer group offsets và phân phối partitions |

@EventListener(condition) không làm Kafka broker gửi ít records hơn; nó chỉ giảm các **event handler invocations** không liên quan.

## 10. Condition với null và defensive filtering

Một số application events có thể đến từ custom containers hoặc các phiên bản framework khác nhau. Nếu handler được khai báo cho một event base type rộng, không nên giả định mọi event đều có listenerId không null.

Một condition null-safe:

~~~java
@EventListener(
    condition =
        "#root.event.listenerId != null " +
        "&& #root.event.listenerId.startsWith('orders-projection')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    // ...
}
~~~

Với SpEL, toán tử && sẽ đánh giá logic boolean có short-circuit theo semantics của biểu thức, giúp tránh gọi startsWith khi listenerId null.

### 10.1 Nếu condition không match nhưng event vẫn tồn tại

Giả sử handler hoàn toàn không được gọi:

- Spring Kafka có publish đúng event type không?
- Idle event interval đã được bật chưa?
- Bean chứa @EventListener có được Spring scan không?
- Context publisher và event listener có cùng ApplicationContext hoặc quan hệ propagation phù hợp không?
- Event.listenerId thực tế có suffix không?
- Condition có sai ID, sai case hoặc regex không?
- SpEL expression có thể parse và evaluate không?
- Có exception trong event dispatch đã bị che bởi logging không?

Không sửa bằng cách loại bỏ mọi điều kiện rồi gắn monitoring trên toàn bộ ứng dụng. Hãy log metadata ở một handler debug có giới hạn thời gian hoặc dùng instrumentation có chọn lọc.

### 10.2 Đặt ID ổn định

Listener ID có thể trở thành một contract vận hành, nhưng nó vẫn là cấu hình nội bộ Spring. Khi rename ID, cần cập nhật:

- @EventListener conditions.
- KafkaListenerEndpointRegistry lookup.
- Monitoring dashboards và alert labels.
- Automation điều khiển pause/resume.
- Integration tests về sự kiện.

Không đổi ID thường xuyên theo build timestamp hoặc deployment UUID nếu monitoring cần nhận dạng cùng logical listener. Nếu cần phân biệt pods, dùng thêm instance ID hoặc client ID.

## 11. Điều kiện dạng prefix: nguy cơ collision

Giả sử có các listener:

~~~text
orders-projection
orders-projection-v2
orders-projection-canary
~~~

Condition:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-projection')"
)
~~~

sẽ match cả ba, dù người viết chỉ muốn production listener cũ.

### 11.1 Đặt naming convention

Một convention minh họa:

~~~text
orders-main
orders-main-0
orders-main-1

orders-canary
orders-canary-0
orders-canary-1

payments-main
payments-main-0
~~~

Vẫn phải cẩn thận nếu dùng prefix orders-main và có ID orders-main-v2. Để rõ ràng, có thể dùng regex theo chính xác parent và numeric children hoặc một helper Java.

### 11.2 Khi nào nên bỏ condition và lọc trong Java?

Nếu điều kiện phải đồng thời xét:

- Một danh sách listener IDs được tải từ configuration.
- Regex có quy tắc tên phức tạp.
- Topic-partition cụ thể.
- ConsumerStoppedEvent reason.
- Environment hoặc tenant.
- Runtime feature flag.

thì code Java trong method có thể dễ đọc, dễ unit test và dễ logging hơn.

~~~java
@Component
public class OrdersIdleMonitor {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {

        if (!belongsToOrdersMain(event.getListenerId())) {
            return;
        }

        log.info("Orders main idle: {}", event.getListenerId());
    }

    private boolean belongsToOrdersMain(String id) {

        if (id == null) {
            return false;
        }

        return id.equals("orders-main")
            || id.matches("orders-main-[0-9]+");
    }
}
~~~

Với cách này, @EventListener được gọi cho mọi idle event nhưng method có thể return sớm. Đánh đổi là một số method invocations không cần thiết, đổi lại việc kiểm thử và thay đổi predicate trở nên đơn giản.

## 12. Condition với SpEL property và method invocation

Trong SpEL, Java bean property có thể được đọc bằng property-style access. Ví dụ:

~~~text
#root.event.listenerId
~~~

tham chiếu tới thuộc tính listenerId qua accessor tương ứng của event. Có thể gọi String methods như startsWith nếu expression được phép theo evaluation context.

Các ví dụ biểu thức:

| Biểu thức | Ý nghĩa |
|---|---|
| #root.event.listenerId == 'orders-main' | Exact listener ID |
| #root.event.listenerId.startsWith('orders-') | Prefix matching |
| #root.event.listenerId != null | Bỏ qua event không có ID |
| #root.event.listenerId matches '^orders-main-[0-9]+$' | Regex cho child IDs theo convention |
| #root.event.listenerId != 'payments-main' | Loại trừ một ID |

Không cần tạo một application event mới chỉ để lọc. Nhưng hãy nhớ event types khác nhau có thể có các thuộc tính khác nhau: một condition dùng getIdleTime() sẽ không phù hợp với ConsumerStoppedEvent.

### 12.1 Ưu tiên property metadata, không dùng payload

Container events không đại diện cho business Kafka record; chúng thường không có payload OrderCreated như listener nhận. Dựa vào listenerId, partition set, idle duration hoặc reason là đúng mức abstraction.

Nếu cần lọc business data, đặt rule đó trong consumer record processing hoặc validation, không trong application event condition.

## 13. Vấn đề concurrency và child event IDs

Với @KafkaListener concurrency=3, Spring Kafka có thể tạo ba child consumers. Các events có thể đến theo thứ tự khác nhau:

~~~text
ConsumerStartedEvent id=orders-main-0
ConsumerStartedEvent id=orders-main-2
ConsumerStartedEvent id=orders-main-1
ConsumerPausedEvent  id=orders-main-1
ConsumerPausedEvent  id=orders-main-0
ConsumerPausedEvent  id=orders-main-2
~~~

Không giả định event arrival order phản ánh một state transition duy nhất của parent.

### 13.1 Group theo logical listener

Khi monitoring cần một trạng thái tổng thể, hãy xác định:

- Parent listener ID.
- Các child IDs thực tế.
- Số child consumers đang running.
- Số children đã paused.
- Partition assignment và trạng thái từng partition.
- Thời gian event và phiên bản instance.

Một parent có ba children, mới nhận một ConsumerPausedEvent, không có nghĩa toàn bộ listener đã paused.

### 13.2 Không trộn events của nhiều pods thành một local state

Spring Application Events là local trong một JVM/ApplicationContext. Pod A và Pod B mỗi pod có các events riêng. Nếu muốn dashboard toàn deployment, export metrics/traces với labels **service, pod/instance, listenerId, clientId**.

Một in-memory Map được cập nhật từ events chỉ phản ánh quá trình mà nó thuộc về; nó không thể biết chắc trạng thái consumers ở pods khác.

### 13.3 Prefix match cần kiểm tra IDs runtime

Đôi khi ID child được framework đặt theo quy tắc khác khi tạo custom containers, assign partitions thủ công hoặc dùng bean container ngoài @KafkaListener. Do đó, trước khi gắn alert production, hãy xem log listenerId thực tế rồi chọn equality, startsWith hoặc regex.

## 14. Thread của ApplicationEvent listener

Theo mặc định, Spring ApplicationEventMulticaster thường dispatch event listeners đồng bộ trên thread phát event. Đối với Spring Kafka container events, thread đó có thể là **consumer thread**.

Điều này tạo ra một rủi ro: nếu @EventListener thực hiện HTTP request chậm hoặc truy vấn database mất 30 giây, nó có thể block consumer thread và làm poll chậm.

### 14.1 Handler event nên nhẹ

Ưu tiên:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-main')"
)
public void onPaused(ConsumerPausedEvent event) {

    meterRegistry.counter(
        "kafka_container_paused_total",
        "listenerId", event.getListenerId()
    ).increment();
}
~~~

Trong production, cần kiểm soát cardinality của metric labels. Nếu listener IDs chứa UUID/pod-unique suffix quá nhiều, số series có thể phình to. Ví dụ trên chỉ minh họa một metric đơn giản.

Tránh:

~~~java
@EventListener
public void onPaused(ConsumerPausedEvent event) {

    // Anti-pattern: có thể block consumer event thread.
    remoteAuditService.callSlowExternalApi(event);
}
~~~

Nếu cần xử lý lâu, chuyển thông tin metadata đã copy sang một bounded executor hoặc pipeline monitoring tách biệt; không giữ tham chiếu KafkaConsumer để dùng bất đồng bộ.

### 14.2 Async ApplicationEventMulticaster

Spring cho phép cấu hình ApplicationEventMulticaster bất đồng bộ. Khi đó event listener có thể chạy trên thread khác consumer thread.

Hệ quả:

- Không nên gọi KafkaConsumer methods từ async event listener.
- Đừng giả định event được xử lý ngay hoặc đúng thứ tự.
- Một số event có chứa consumer reference chỉ dùng an toàn trên thread gốc.
- Nếu muốn điều khiển container, dùng MessageListenerContainer API.
- Cần thiết kế bounded queue, error handling và shutdown cho async executor.

Thay đổi multicaster sang async có thể tác động tất cả Application Events khác trong context, không chỉ Spring Kafka events. Cần đánh giá phạm vi thay đổi.

### 14.3 Không block hoặc stop container ngay trong consumer event callback

Một số Spring Kafka event callbacks chạy trên consumer thread. Việc thực hiện thao tác lifecycle có thể chờ chính thread đang dispatch event dẫn đến deadlock hoặc chậm.

Nếu cần stop container khi idle quá lâu, cách an toàn hơn là gửi tín hiệu cho một executor/controller khác điều phối stop, theo API Spring Kafka version tương ứng. Không gọi consumer.close(), consumer.seek() hoặc thao tác nguy hiểm khác trực tiếp từ event handler mà không hiểu thread ownership.

## 15. Dùng event để điều khiển pause/resume có kiểm soát

Một use case là theo dõi downstream overload và pause đúng listener. Tuy nhiên, Application Events nên chủ yếu dùng để **quan sát trạng thái**, còn quyết định pause/resume nên thuộc một component có ownership rõ ràng.

Ví dụ lấy container theo ID:

~~~java
@Service
public class OrdersContainerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersContainerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {

        MessageListenerContainer c =
            registry.getListenerContainer("orders-projection");

        if (c != null && !c.isPauseRequested()) {
            c.pause();
        }
    }

    public void resumeOrders() {

        MessageListenerContainer c =
            registry.getListenerContainer("orders-projection");

        if (c != null && c.isPauseRequested()) {
            c.resume();
        }
    }
}
~~~

Container registry dùng **parent endpoint ID** theo @KafkaListener. Event ID của child có thể là orders-projection-0, nhưng lookup registry theo child suffix không nhất thiết trả về container mong muốn.

### 15.1 Đừng gắn hành động pause vào mọi idle event

Idle vì **topic không có traffic** là trạng thái có thể lành mạnh. Gọi pause vì idle khiến container không nhận records mới khi producer hoạt động trở lại, trừ khi có một cơ chế resume khác.

Không thiết kế vòng lặp:

~~~text
idle event -> pause
pause -> tiếp tục idle
idle event -> pause
...
~~~

Chỉ pause nếu có lý do như downstream overload, maintenance hoặc backpressure với điều kiện resume rõ ràng.

### 15.2 Theo dõi trạng thái sau yêu cầu

Khi một controller gọi pause():

1. Yêu cầu được ghi nhận.
2. Container áp dụng pause theo vòng consumer, có thể sau current record.
3. ConsumerPausedEvent được publish.
4. Monitoring cập nhật trạng thái.
5. Khi resume, ConsumerResumedEvent xác nhận phục hồi.

Không dùng event filter để tự động suy ra rằng **mọi** child đã pause; cần tổng hợp children hoặc dùng container state API.

## 16. Khi có nhiều ApplicationContexts

Trong một ứng dụng Spring Boot thông thường, Spring Kafka containers và @EventListener beans nằm trong cùng ApplicationContext. Với cấu trúc parent/child contexts hoặc một số integration tests phức tạp, events có thể được propagate theo context hierarchy.

Hệ quả:

- Một @EventListener có thể được gọi bởi event từ child context.
- Có thể có nhiều listeners có cùng logical ID trong các contexts khác nhau.
- Predicate chỉ theo listenerId có thể không phân biệt nguồn context.
- Một metric aggregator có thể đếm lặp nếu event được truyền qua nhiều levels.

Nếu ứng dụng có hierarchy, cần thiết kế lọc theo source/context phù hợp, không dựa duy nhất vào prefix ID. Trong ứng dụng đơn context, đây thường không phải vấn đề.

## 17. Kiến trúc event handlers dễ bảo trì

Khi số listeners tăng, không nên tạo một class với hàng chục điều kiện SpEL lặp nhau và nhiều hardcoded IDs mà không có convention.

Một tổ chức thực dụng:

~~~text
Application events
  -> KafkaContainerEventObserver
       - nhận các event types quan trọng
       - xác định listenerId
       - chuẩn hóa metric/log labels
       - gửi tín hiệu vận hành
  -> BackpressureController
       - chủ sở hữu pause policy
       - lookup container bằng endpoint ID
       - quyết định pause/resume theo downstream state
  -> Alerting
       - dùng metrics và SLA
       - không gọi KafkaConsumer trực tiếp
~~~

### 17.1 Condition dùng cho lọc đơn giản

Ví dụ:

~~~java
@EventListener(
    condition = "#root.event.listenerId.startsWith('orders-main')"
)
public void onOrdersIdle(ListenerContainerIdleEvent event) {
    ordersMetrics.recordIdle(event.getListenerId(), event.getIdleTime());
}
~~~

### 17.2 Java predicate cho logic phức tạp

Ví dụ:

~~~java
@EventListener
public void onConsumerStopped(ConsumerStoppedEvent event) {

    if (!listenerPolicy.isMonitored(event.getListenerId())) {
        return;
    }

    if (!shutdownPolicy.isExpected(event)) {
        alerting.reportUnexpectedStop(
            event.getListenerId(),
            event.getReason()
        );
    }
}
~~~

Cách này cho phép unit test listenerPolicy và shutdownPolicy riêng, đồng thời có logs giải thích vì sao event bị bỏ qua.

### 17.3 Không coi event handler là consumer của một durable stream

Spring Application Events không phải một topic Kafka với committed offsets. Nếu JVM chết trong lúc phát event hoặc event listener không chạy, nó không tự được replay sau restart.

Các sự kiện quan trọng cần audit bền vững phải được chuyển thành metric/log hoặc durable audit event qua một pipeline có retry và error handling phù hợp. Không dựa vào Application Events như kênh lưu lịch sử duy nhất.

## 18. Tình huống: condition không lọc đúng listener

Giả sử orders idle handler nhận cả payments events hoặc không nhận event orders nào.

### 18.1 Checklist điều tra

1. Xác nhận @KafkaListener.id và idIsGroup/groupId.
2. Xác nhận listener container factory và concurrency.
3. Đăng ký tạm handler chỉ log event.getListenerId() cho event type đang quan tâm.
4. Kiểm tra có child suffix hay custom container bean name không.
5. Kiểm tra SpEL condition đang dùng equality, prefix hay regex.
6. Nếu dùng prefix, kiểm tra collision giữa orders-main và orders-main-v2.
7. Nếu dùng tham số tên #event, kiểm tra Java compile metadata; cân nhắc #root.event.
8. Xác nhận bean chứa @EventListener được Spring quản lý.
9. Kiểm tra event có thực sự được publish bằng cách xác nhận idleEventInterval hoặc trạng thái lifecycle.
10. Kiểm tra ApplicationContext hierarchy và việc multicaster bất đồng bộ.
11. Không tự thay đổi Kafka group.id để sửa event filter.

### 18.2 Một lỗi naming thường gặp

~~~text
@KafkaListener.id = orders
concurrency = 3

event.listenerId:
  orders-0
  orders-1
  orders-2

condition = listenerId == 'orders'
~~~

Kết quả: condition có thể không match. Sửa bằng predicate hỗ trợ child IDs hoặc thay đổi conventions để match IDs thực tế, thay vì tưởng container không phát events.

### 18.3 Một lỗi khác: lọc quá rộng

~~~text
@KafkaListener.id:
  orders
  orders-retry
  orders-dlt

condition:
  startsWith('orders')
~~~

Kết quả: event handler theo dõi cả retry/DLT listeners. Nếu chỉ muốn main listener, dùng một tên chuyên biệt và predicate hẹp hơn.

## 19. Tình huống: idle event bị hiểu là outage

Một listener idle 60 giây có thể vì đơn giản không có data. Muốn tạo cảnh báo đáng tin cậy cần xét:

| Tín hiệu | Diễn giải |
|---|---|
| ListenerContainerIdleEvent | Không có delivery trong khoảng idle đã cấu hình |
| Consumer lag = 0 | Consumer đang bắt kịp producer; idle có thể bình thường |
| Consumer lag lớn | Có backlog chưa xử lý; cần điều tra |
| ConsumerPausedEvent | Consumer đang chủ động paused |
| NonResponsiveConsumerEvent | Poll có thể bị chậm/tắc |
| Producer rate | Có records được ghi vào topic không |
| Partition assignment | Consumer có được gán partitions không |
| Last processed business event time | Mức freshness của nghiệp vụ |

Một alert đúng nên gắn với SLA, ví dụ “orders có producer traffic và lag tăng, nhưng listener không xử lý record trong 5 phút”, thay vì chỉ “idle hơn 10 giây”.

### 19.1 Chọn condition dựa trên ID, không dựa trên giả định health

Condition chỉ nên lọc **người phát event**. Logic đánh giá event là bình thường hay bất thường nằm ở monitoring/alert service, nơi có thể kết hợp nhiều metrics.

Nếu condition trở thành một biểu thức SpEL cực dài chứa cả stateful health checks, việc bảo trì và kiểm thử sẽ khó hơn.

## 20. Tích hợp với test và observability

Bài toán thực tế là xác minh event filter chỉ bắt đúng logical listener và không bỏ sót child containers.

### 20.1 Integration test với concurrency=1

1. Tạo Kafka listener id orders-main, groupId riêng.
2. Cấu hình idleEventInterval ngắn trong môi trường test.
3. Đợi ListenerContainerIdleEvent được phát.
4. Xác nhận handler dành cho orders-main được gọi.
5. Định nghĩa thêm payments-main và tạo idle.
6. Xác nhận orders handler không xử lý payments event.
7. Kiểm tra listenerId thực tế trong event.

Không dùng unit test gọi trực tiếp handler để chứng minh @EventListener condition được Spring đánh giá đúng; unit test đó chỉ kiểm tra Java method.

### 20.2 Integration test với concurrency>1

1. Chạy orders-main với concurrency=3 và topic đủ partitions.
2. Đợi child consumer containers được tạo.
3. Quan sát listener IDs của child events.
4. Xác nhận condition/predicate nhận các IDs thuộc orders-main.
5. Thêm listener orders-main-v2 để kiểm tra prefix collision.
6. Xác nhận predicate không nhận nhầm v2 nếu yêu cầu chỉ main.
7. Kiểm tra metric labels có phân biệt child và parent hợp lý.

### 20.3 Test pause/resume events

1. Lấy parent container từ KafkaListenerEndpointRegistry.
2. Gọi container.pause() từ test thread.
3. Đợi actual pause bằng isConsumerPaused hoặc event.
4. Xác nhận ConsumerPausedEvent được handler tương ứng nhận.
5. Gọi resume().
6. Đợi ConsumerResumedEvent và tiến triển records trở lại.
7. Xác nhận không có handler của listener khác bị gọi sai.

### 20.4 Test ApplicationEvent condition

Có thể dựng test context dùng ApplicationEventPublisher và event instance thích hợp để kiểm tra condition. Tuy nhiên, cách khởi tạo một số Spring Kafka event classes thay đổi theo version. Integration test với listener container thật đáng tin cậy hơn để kiểm tra listenerId và child naming.

### 20.5 Test thread-safety

- Đo latency của event handler để bảo đảm nó không block consumer poll.
- Nếu ApplicationEventMulticaster là async, xác nhận handler không truy cập KafkaConsumer ngoài consumer thread.
- Test shutdown khi có nhiều events queued.
- Đảm bảo metric/log pipeline quá tải không làm consumer mất poll interval.

## 21. Runbook khi event lọc sai hoặc thiếu event

Khi operator nói “orders consumer đã pause nhưng dashboard không thấy event”:

1. Xác định listener ID thực tế, không chỉ tên Kafka group.
2. Kiểm tra child consumer IDs theo concurrency.
3. Xác nhận pause request đã được gửi vào container đúng ID.
4. Xác nhận consumer đã pause thật, không chỉ isPauseRequested().
5. Kiểm tra ConsumerPausedEvent có phát trong cùng ApplicationContext.
6. Kiểm tra @EventListener type và SpEL condition.
7. So sánh event.getListenerId() với predicate đúng từng ký tự.
8. Kiểm tra prefix collision và null listenerId.
9. Kiểm tra event handler có bị block, lỗi hoặc chạy async không.
10. Kiểm tra dashboard labels và metrics exporter, tránh nhầm lỗi filter với lỗi xuất metric.
11. Sửa predicate hoặc naming convention có kiểm soát.
12. Kiểm chứng lại trên integration/staging với concurrency tương tự production.

Không sửa Kafka committed offsets hoặc reset consumer group để giải quyết một vấn đề thuần Application Event filtering. Hai lớp này độc lập.

## 22. Những hiểu nhầm thường gặp

**“@EventListener nhận Kafka records.”** Không. Nó nhận Spring Application Events. Kafka records được xử lý bởi @KafkaListener.

**“Condition lọc dữ liệu ở broker.”** Không. Nó lọc việc gọi Spring event handler, không giảm record fetch.

**“Listener ID chính là group.id.”** Không mặc định. Đây là hai danh tính khác nhau, dù idIsGroup có thể dùng ID làm group khi thiếu groupId.

**“Một @KafkaListener luôn phát events với đúng id không suffix.”** Không. Concurrent container có thể phát từ child IDs có hậu tố.

**“startsWith luôn an toàn.”** Không. orders-main cũng match orders-main-v2 nếu predicate quá rộng.

**“@EventListener condition chỉ dùng được với type event.”** Không. Type được lọc qua argument, condition đọc metadata trên event.

**“ListenerContainerIdleEvent chứng minh broker lỗi.”** Không. Ít traffic có thể hoàn toàn bình thường.

**“Một ConsumerPausedEvent nghĩa là toàn bộ concurrent listener đã pause.”** Không. Event có thể thuộc một child hoặc partitions.

**“Event handler có thể gọi KafkaConsumer ở bất kỳ thread nào.”** Không. KafkaConsumer có thread ownership; async event listener đặc biệt cần tránh.

**“Event handler chậm không ảnh hưởng Kafka.”** Sai. Với synchronous multicaster, handler có thể chạy trên consumer thread.

**“Đổi @KafkaListener.id không ảnh hưởng gì ngoài log.”** Không hẳn. Registry lookup và event filters dựa trên ID; nếu idIsGroup giữ true và không có groupId riêng, Kafka group còn có thể đổi theo.

**“Application Events là durable audit log.”** Không. Chúng không được Kafka broker tự lưu và replay.

## 23. Checklist triển khai

**Listener identity**

- [ ] @KafkaListener.id được đặt rõ ràng và ổn định.
- [ ] groupId được đặt riêng khi cần, tránh side effect của idIsGroup.
- [ ] Phân biệt listener ID, Kafka group ID và clientIdPrefix.
- [ ] Có naming convention cho main/retry/DLT/canary listeners.
- [ ] Biết child IDs thực tế khi concurrency>1.

**Application events**

- [ ] Chọn đúng event type: idle, paused, resumed, started, stopped hoặc loại phù hợp.
- [ ] Đã bật cấu hình sinh event khi cần, ví dụ idleEventInterval.
- [ ] Dùng @EventListener(condition) cho predicate đơn giản.
- [ ] Condition null-safe nếu cần và tránh prefix collision.
- [ ] Logic phức tạp được viết trong Java predicate/service có thể test.

**Threading và vận hành**

- [ ] Handler nhẹ, không block consumer thread.
- [ ] Không gọi KafkaConsumer từ async event handler.
- [ ] Pause/resume qua MessageListenerContainer API.
- [ ] Không dùng idle event đơn lẻ như lỗi nghiêm trọng.
- [ ] Có metrics/log theo listenerId, instance và partition.
- [ ] Có alert tránh metric cardinality quá cao.

**Verification**

- [ ] Test condition equality và startsWith/regex nếu dùng.
- [ ] Test concurrency>1 và child suffix.
- [ ] Test không nhận nhầm event từ main/retry/DLT hoặc canary.
- [ ] Test pause/resume events và trạng thái thực.
- [ ] Test event listener hoạt động trong ApplicationContext thật.
- [ ] Test handler không làm chậm Kafka poll và không phụ thuộc event durability.

## 24. Kết luận

**Listener ID và @EventListener(condition)** là cặp công cụ hữu ích để chọn đúng Spring Kafka Application Events trong ứng dụng có nhiều listener containers. Listener ID xác định endpoint/container phát event; condition là biểu thức SpEL được Spring đánh giá trước khi gọi event handler. Khi listener có concurrency, event có thể mang ID của child container với hậu tố; cần chọn equality, prefix hoặc regex theo naming convention thực tế và tránh collision.

Sử dụng đúng cơ chế này giúp monitoring và automation quan sát chính xác từng listener, nhưng không thay thế Kafka record filtering, không điều khiển group offsets và không tự bảo đảm sức khỏe consumer. Handler nên nhẹ, thread-safe, phân biệt trạng thái vận hành với sự cố thật và được kiểm chứng bằng integration test có nhiều containers, nhiều event types cùng concurrency gần với production.

