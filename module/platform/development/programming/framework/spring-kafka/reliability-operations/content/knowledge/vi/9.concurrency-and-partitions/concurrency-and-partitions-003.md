# Child container trong concurrent container

Trong Spring Kafka, một listener cần xử lý nhiều partition song song có thể được chạy bằng **ConcurrentMessageListenerContainer**. Container này đóng vai trò quản lý và tạo ra nhiều **child container** kiểu **KafkaMessageListenerContainer**. Mỗi child container quản lý một Kafka consumer riêng và thực hiện poll, nhận record, gọi listener, xử lý acknowledgment và commit offset theo cấu hình.

Hiểu đúng quan hệ giữa parent container, child container, consumer và partition giúp cấu hình concurrency có chủ đích. Nếu chỉ tăng số child container mà không xét số partition, số replica ứng dụng và năng lực downstream, hệ thống có thể tạo nhiều consumer idle hoặc làm database quá tải. Nếu không hiểu lifecycle của child container, việc theo dõi lỗi, pause/resume và shutdown cũng dễ bị nhầm ở cấp parent với cấp consumer thực tế.

Bài này tập trung vào cách **ConcurrentMessageListenerContainer** tổ chức child container, cách partition được phân phối, cách cấu hình trong Spring Boot/Spring Kafka và cách vận hành khi một child gặp sự cố.

## 1. ConcurrentMessageListenerContainer là gì?

Spring Kafka có hai container listener chính cần phân biệt:

- **KafkaMessageListenerContainer**: quản lý một Kafka consumer và thực thi listener trên consumer thread của container đó.
- **ConcurrentMessageListenerContainer**: container điều phối, tạo và quản lý nhiều KafkaMessageListenerContainer để cung cấp khả năng tiêu thụ song song.

Vì vậy, concurrent container thường được xem là parent container; các KafkaMessageListenerContainer do nó tạo ra là child container.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer<br/>parent"]
    P --> C0["KafkaMessageListenerContainer<br/>child 0"]
    P --> C1["KafkaMessageListenerContainer<br/>child 1"]
    P --> C2["KafkaMessageListenerContainer<br/>child 2"]
    C0 --> K0["KafkaConsumer 0"]
    C1 --> K1["KafkaConsumer 1"]
    C2 --> K2["KafkaConsumer 2"]
    K0 --> A0["Assigned partitions"]
    K1 --> A1["Assigned partitions"]
    K2 --> A2["Assigned partitions"]
~~~

Parent container không tự poll record như một consumer độc lập. Nó quản lý lifecycle và tập child container. Mỗi child có consumer riêng, thread riêng và assignment riêng theo cơ chế subscription hoặc assignment đang dùng.

Ví dụ, khi cấu hình concurrency bằng 3, một ConcurrentMessageListenerContainer thường tạo ba KafkaMessageListenerContainer con. Mỗi child có một Kafka consumer. Kafka group coordinator phân phối partition giữa các consumer đó nếu listener sử dụng group subscription.

### 1.1 Vì sao cần child container?

Kafka consumer không được thiết kế để một consumer instance xử lý nhiều partition đồng thời trên nhiều thread bằng cách gọi poll từ nhiều thread. Một consumer có vòng đời và thread ownership rõ ràng. Muốn tăng khả năng xử lý song song, ứng dụng thường tạo nhiều consumer instance trong cùng consumer group.

Spring Kafka cung cấp ConcurrentMessageListenerContainer để quản lý việc tạo các consumer instance đó. Developer chỉ cấu hình concurrency ở factory hoặc listener; framework tạo child container và quản lý chúng.

Lợi ích:

- Có thể xử lý nhiều partition song song trong một application instance.
- Mỗi child có consumer và consumer thread riêng.
- Parent quản lý start, stop và lifecycle của các child.
- Có thể quan sát trạng thái container theo cấp parent và child.
- Cấu hình listener vẫn giữ một phương thức nghiệp vụ, không cần tự tạo thread hoặc KafkaConsumer thủ công.

### 1.2 Child container không phải là partition

Một child container quản lý một consumer. Consumer đó có thể được gán không partition nào, một partition hoặc nhiều partition.

Ví dụ topic có sáu partition và concurrency bằng ba:

- Child 0 có thể nhận partition 0 và 1.
- Child 1 có thể nhận partition 2 và 3.
- Child 2 có thể nhận partition 4 và 5.

Đây chỉ là ví dụ minh họa. Assignment thực tế phụ thuộc partition assignor, các member khác trong group, subscription và trạng thái rebalance. Không nên giả định child số 0 luôn nhận partition 0 hoặc assignment luôn chia đều tuyệt đối.

Nếu concurrency lớn hơn số partition có thể được gán trong group, một số child sẽ không nhận partition và không xử lý record cho đến khi assignment thay đổi.

## 2. Quan hệ giữa parent, child, consumer thread và listener

Một cấu trúc điển hình trong Spring Kafka:

| Thành phần | Trách nhiệm |
|---|---|
| ConcurrentMessageListenerContainer | Parent; quản lý danh sách child container và lifecycle chung |
| KafkaMessageListenerContainer | Child; quản lý một consumer và vòng lặp poll |
| KafkaConsumer | Thực hiện poll, quản lý subscription/assignment, heartbeat và offset protocol |
| Consumer thread | Thread sở hữu consumer, poll record và gọi listener theo container model |
| Listener method | Xử lý record hoặc batch được child consumer nhận |
| Partition assignment | Tập partition được gán cho một consumer trong group |

Khi child container poll được record, listener được gọi theo cấu hình record listener hoặc batch listener. Với mô hình thông thường, listener invocation diễn ra trên consumer thread của child đó. Vì vậy, concurrency của parent tạo ra nhiều luồng thực thi listener song song.

### 2.1 Một child có một consumer

Trong cấu trúc concurrent container tiêu chuẩn, mỗi child KafkaMessageListenerContainer quản lý một Kafka consumer. Consumer này không được chia sẻ cho các child khác.

Đây là ranh giới quan trọng khi điều tra:

- Một child dừng không có nghĩa mọi child đều dừng.
- Một consumer bị lỗi có thể rời group và khiến partition được gán lại cho child khác.
- Listener xử lý chậm trên một child có thể làm chậm các partition được gán cho chính consumer đó.
- Parent vẫn có thể ở trạng thái running trong khi một child đang restart hoặc gặp lỗi, tùy trạng thái lifecycle và error handling.

### 2.2 Listener bean có thể được gọi đồng thời

Một Spring component thường là singleton. Nếu nhiều child container cùng gọi một listener method, các invocation có thể diễn ra đồng thời trên nhiều thread.

Ví dụ:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "orders-projection-prod",
        concurrency = "3"
    )
    public void handle(OrderCreated event) {
        projectionService.apply(event);
    }
}
~~~

Ba child container có thể gọi handle() đồng thời. Nếu listener giữ mutable state trong field, cần bảo đảm thread safety. Không nên lưu một biến tạm dùng chung cho nhiều invocation nếu không có đồng bộ hóa hoặc thiết kế immutable.

Các dependency singleton như service, repository và client HTTP cũng cần an toàn khi được gọi đồng thời. Spring bean singleton không tự động có nghĩa mọi method đều thread-safe.

### 2.3 Consumer thread và tác vụ bất đồng bộ

Nếu listener đẩy công việc sang executor rồi trả về ngay, container có thể xem listener đã hoàn tất theo ack mode hiện tại trong khi tác vụ bất đồng bộ vẫn đang chạy. Nếu offset được commit trước khi tác vụ hoàn thành, process chết có thể làm mất công việc ở tầng ứng dụng.

Nếu muốn xử lý bất đồng bộ, phải thiết kế acknowledgment và offset commit gắn với kết quả thực tế. Cũng cần kiểm soát thứ tự, backpressure, số tác vụ đang chạy và khả năng xử lý lại. Không nên chỉ thêm CompletableFuture hoặc @Async rồi giả định Kafka container sẽ chờ task hoàn tất.

## 3. Cấu hình concurrency và số child container

Concurrency là số child container mà ConcurrentMessageListenerContainer tạo ra cho một listener container. Có thể cấu hình ở factory hoặc trực tiếp trên @KafkaListener.

### 3.1 Cấu hình ở listener annotation

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersProjection",
    topics = "orders",
    groupId = "orders-projection-prod",
    concurrency = "3"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

Với cấu hình này, listener container concurrent có concurrency bằng 3. Parent quản lý ba child KafkaMessageListenerContainer. Mỗi child có một consumer riêng.

Giá trị concurrency trong annotation là chuỗi vì thuộc tính annotation có thể nhận placeholder hoặc SpEL ở các phiên bản Spring Kafka hỗ trợ. Có thể dùng giá trị cấu hình theo môi trường, nhưng cần xác nhận giá trị runtime sau khi placeholder được resolve.

### 3.2 Cấu hình ở ConcurrentKafkaListenerContainerFactory

Có thể đặt concurrency mặc định cho các listener sử dụng factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener sử dụng factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection-prod",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

Nếu annotation có thuộc tính concurrency, giá trị tại annotation có thể override concurrency của factory cho listener đó. Nên chọn một nguồn cấu hình chính để tránh người vận hành đọc factory thấy 3 nhưng listener thực tế chạy với concurrency khác.

### 3.3 Cấu hình bằng Spring Boot

Với factory mặc định được Spring Boot auto-configure, có thể đặt concurrency mặc định qua listener properties trong các phiên bản Spring Boot hỗ trợ:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
    consumer:
      group-id: orders-projection-prod
      enable-auto-commit: false
~~~

Nếu ứng dụng tự tạo ConcurrentKafkaListenerContainerFactory, cần cấu hình concurrency trên factory custom tương ứng. Không giả định property của factory mặc định tự động áp dụng cho factory tự khai báo.

### 3.4 Chọn concurrency theo partition

Giả sử topic có tám partition. Một application instance chạy concurrency bằng bốn. Trong một group chỉ có instance đó, tối đa bốn child consumer hoạt động, mỗi child có thể nhận khoảng hai partition.

Nếu concurrency bằng mười, chỉ tối đa tám consumer có thể nhận partition của topic này; hai child còn lại idle nếu không có partition khác được subscribe.

Cần phân biệt hai số:

- **Child count**: số child container được tạo bởi parent.
- **Active consumer count**: số consumer thực sự có assignment và đang xử lý partition.

Hai số này không nhất thiết bằng nhau.

## 4. Tính concurrency ở cấp toàn bộ deployment

Khi ứng dụng có nhiều pod, số child container được tạo ra trên mỗi pod cần được tính cùng số replica.

Công thức cơ bản:

~~~text
Tổng số child container = số application instance × concurrency mỗi instance
~~~

Ví dụ deployment có ba pod, mỗi pod cấu hình concurrency bằng bốn:

~~~text
3 pods × 4 child containers = 12 consumer instances
~~~

Nếu tất cả dùng cùng group id và cùng subscribe topic có tám partition, group có tối đa tám consumer được gán partition của topic đó. Bốn consumer còn lại có thể idle đối với topic này.

| Số pod | Concurrency mỗi pod | Tổng consumer | Số partition | Consumer có thể nhận partition |
|---:|---:|---:|---:|---:|
| 1 | 4 | 4 | 8 | Tối đa 4 |
| 2 | 4 | 8 | 8 | Tối đa 8 |
| 3 | 4 | 12 | 8 | Tối đa 8 |
| 4 | 2 | 8 | 16 | Tối đa 8 |
| 4 | 4 | 16 | 16 | Tối đa 16 |

Bảng giả định tất cả consumer thuộc cùng group và chỉ xét một topic có số partition nêu trong bảng. Nếu listener subscribe nhiều topic, assignment phụ thuộc toàn bộ tập partition được subscribe.

### 4.1 Không nên tăng concurrency vô hạn

Tăng concurrency có thể tăng song song, nhưng đồng thời tăng:

- Số Kafka consumer và connection tới broker.
- Số consumer thread và bộ nhớ.
- Số request poll và heartbeat.
- Số invocation listener đồng thời.
- Số connection hoặc request tới database/downstream.
- Áp lực lên CPU, heap, connection pool và thread pool.

Nếu downstream chỉ chịu được 20 request đồng thời, tăng từ 4 lên 30 child có thể làm hệ thống downstream quá tải. Consumer lag có thể tăng thêm vì listener timeout, retry và connection pool saturation.

Nên xác định bottleneck trước khi tăng concurrency. Nếu database là giới hạn, cần điều tiết mức song song hoặc tối ưu query; tăng child container không làm database xử lý nhanh hơn.

### 4.2 Nhiều listener có concurrency riêng

Một ứng dụng có thể có nhiều @KafkaListener với các topic và workload khác nhau. Mỗi listener có container riêng và có thể có concurrency khác nhau.

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-service-prod",
    concurrency = "4"
)
public void handleOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
    id = "notificationsListener",
    topics = "notifications",
    groupId = "notification-service-prod",
    concurrency = "2"
)
public void handleNotification(NotificationRequested event) {
    notificationService.send(event);
}
~~~

Hai listener có tổng cộng sáu child container trên mỗi application instance. Nếu ứng dụng chạy ba pod, có thể có 18 child consumer instance. Tuy nhiên, hai group id khác nhau tạo hai subscription độc lập và mỗi group có assignment riêng.

Đừng chỉ cộng concurrency trong một service rồi so với partition count của một topic. Cần tính theo từng logical consumer group và toàn bộ topic mà listener subscribe.

## 5. Partition được phân phối giữa các child container

Với group subscription, mỗi child container tham gia group như một consumer member. Kafka group coordinator và partition assignor quyết định partition nào thuộc về consumer nào.

Ví dụ topic orders có sáu partition, concurrency bằng ba:

| Child container | Consumer member | Ví dụ assignment |
|---|---|---|
| Child 0 | Consumer 0 | orders-0, orders-1 |
| Child 1 | Consumer 1 | orders-2, orders-3 |
| Child 2 | Consumer 2 | orders-4, orders-5 |

Assignment có thể khác theo assignor, member count và các topic khác. Consumer có thể nhận nhiều partition; một partition không được gán cho hai consumer trong cùng group tại cùng thời điểm.

### 5.1 Assignment phụ thuộc partition assignor

Kafka có các partition assignor với cách phân phối khác nhau, ví dụ RangeAssignor, RoundRobinAssignor và CooperativeStickyAssignor. Cách phân phối có thể ảnh hưởng số partition mỗi child nhận và mức độ thay đổi assignment khi member gia nhập hoặc rời group.

Spring Kafka tạo consumer theo cấu hình; việc chọn assignor được thực hiện qua consumer properties. Concurrent container không tự bảo đảm assignment cân bằng theo tải nghiệp vụ. Một partition có lượng record lớn có thể tạo bottleneck dù số partition mỗi child bằng nhau.

### 5.2 Rebalance khi child gia nhập hoặc rời group

Khi child container start, stop hoặc mất kết nối, group membership thay đổi. Kafka có thể thực hiện rebalance để phân phối lại partition.

Các tình huống:

- Scale concurrency từ 2 lên 4: thêm consumer member; group có thể rebalance.
- Restart application: child consumer rời group rồi tham gia lại.
- Một child bị lỗi: partition của nó có thể được gán cho member còn lại.
- Rolling deployment: pod cũ và mới cùng tham gia group trong thời gian rollout.
- Thay subscription hoặc partition count: assignment có thể thay đổi.

Rebalance có thể tạm dừng xử lý trên một số partition. Nếu listener chưa commit offset, record có thể được giao lại. Vì vậy, tăng concurrency giữa lúc hệ thống đang xử lý chậm có thể làm lag tăng tạm thời trước khi ổn định.

### 5.3 Child không nhận partition vẫn là child đang tồn tại

Nếu số child lớn hơn số partition, child dư vẫn có thể được tạo và có lifecycle running, nhưng không nhận assignment. Đây không phải lỗi tạo container. Nó chỉ là consumer chưa có partition để xử lý.

Theo dõi số child container không đủ để biết năng lực xử lý thực tế. Cần quan sát consumer assignment, số partition assigned và record processing rate.

## 6. Explicit partition assignment và child container

Ngoài group subscription, Spring Kafka cho phép chỉ định partition cụ thể qua @TopicPartition hoặc TopicPartitionOffset. Trong trường hợp này, cách phân phối partition khác với group subscription thông thường.

Ví dụ:

~~~java
@KafkaListener(
    id = "priorityOrders",
    groupId = "priority-orders-worker",
    topicPartitions = {
        @TopicPartition(
            topic = "orders",
            partitions = {"0", "1", "2", "3"}
        )
    },
    concurrency = "2"
)
public void handle(OrderCreated event) {
    priorityOrderService.process(event);
}
~~~

Với explicit partition assignment, Spring Kafka có thể phân phối các partition được khai báo giữa các child container trong concurrent container. Nếu concurrency lớn hơn số partition được khai báo, concurrency có thể được giảm xuống để không tạo child dư cho assignment tĩnh theo cơ chế của phiên bản framework đang dùng.

Cần phân biệt:

- **Group subscription**: consumer subscribe topic; Kafka group coordinator phân phối partition.
- **Manual assignment**: ứng dụng chỉ định partition cho consumer; consumer tự quản lý assignment và không tham gia group coordination để chia partition như subscription thông thường.

Với manual assignment, nếu nhiều application instance cùng khai báo cùng tập partition, các instance có thể cùng đọc các partition đó độc lập. Điều này có thể tạo duplicate processing. Không triển khai cùng một manual assignment trên nhiều replica nếu không có cơ chế phân chia partition duy nhất và điều phối ownership.

### 6.1 Khi nào dùng explicit assignment?

Explicit assignment có thể hữu ích khi:

- Ứng dụng cần gán partition cụ thể cho worker theo topology đã quản lý.
- Cần cô lập một partition hoặc nhóm partition.
- Một hệ thống có cơ chế phân phối ownership bên ngoài Kafka.
- Cần cấu hình offset ban đầu hoặc seek cụ thể theo partition.

Tuy nhiên, explicit assignment làm ứng dụng chịu trách nhiệm cao hơn về ownership, rebalance, scale và failover. Với đa số service consumer cần scale replica tự động, group subscription thường đơn giản và an toàn hơn.

### 6.2 Offset ban đầu theo TopicPartitionOffset

Spring Kafka hỗ trợ khai báo partition và initial offset thông qua TopicPartitionOffset. Cần hiểu kiểu offset được dùng: offset tuyệt đối, relative offset hoặc timestamp-based offset tùy API và phiên bản.

Không coi initial offset annotation là cơ chế liên tục reset offset mỗi lần child restart. Offset ban đầu thường có vai trò khi thiết lập assignment; committed offset và lifecycle consumer vẫn ảnh hưởng vị trí tiếp tục. Khi cần replay có chủ đích, hãy dùng quy trình reset/seek rõ ràng và kiểm tra trạng thái group.

## 7. Lifecycle của parent và child container

Parent ConcurrentMessageListenerContainer quản lý tập child container. Khi parent được start, nó tạo hoặc khởi động các child theo concurrency. Khi parent stop, nó điều phối việc dừng child và chờ consumer đóng theo lifecycle container.

### 7.1 Start

Khi application context khởi động hoặc listener endpoint được đăng ký:

1. Spring tạo listener container từ factory.
2. Nếu endpoint cần concurrent container, parent được tạo.
3. Parent xác định concurrency.
4. Parent tạo các KafkaMessageListenerContainer con.
5. Mỗi child khởi tạo Kafka consumer và tham gia group hoặc thực hiện assignment.
6. Consumer poll và listener bắt đầu nhận record khi partition được gán.

Các bước cụ thể có thể khác theo lifecycle và cấu hình lazy startup, nhưng mô hình parent quản lý child vẫn là điểm cần nhớ.

### 7.2 Stop và shutdown

Khi parent dừng, child container dừng theo container lifecycle. Consumer cần hoàn tất hoặc hủy công việc theo shutdown timeout và ack mode. Nếu listener đang xử lý record lâu, thời gian shutdown có thể kéo dài hoặc container phải kết thúc theo timeout.

Nên:

- Đặt thời gian xử lý listener có giới hạn.
- Cấu hình shutdown timeout phù hợp với thời gian xử lý và commit.
- Dùng graceful shutdown của nền tảng triển khai.
- Tránh force terminate trong hoạt động bình thường.
- Kiểm tra offset đã commit và record có thể được giao lại sau restart.

Nếu process dừng trước khi offset được commit, record có thể được xử lý lại. Đây là hành vi at-least-once thường gặp và cần idempotent business processing.

### 7.3 Child restart và parent state

Một child có thể gặp lỗi và được container lifecycle/error handling xử lý tùy loại exception, container configuration và phiên bản Spring Kafka. Parent quản lý các child nhưng không nên giả định trạng thái parent running đồng nghĩa mọi child đều khỏe.

Khi điều tra, xem trạng thái từng child:

- Child nào đang running?
- Child nào đang stopping hoặc bị restart?
- Consumer member nào đang có assignment?
- Child nào có listener error hoặc poll gap?
- Partition nào bị ảnh hưởng?

Nếu chỉ xem một health indicator tổng quát của parent, có thể bỏ sót một child không xử lý record.

## 8. Quan sát child container và consumer

Spring Kafka cung cấp API và event để quan sát container. Tên method và event có thể khác theo phiên bản; cần dùng đúng API của phiên bản đang triển khai.

### 8.1 Lấy child container từ parent

ConcurrentMessageListenerContainer cung cấp cách truy cập danh sách child container qua API như **getContainers()**.

Ví dụ minh họa:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void printChildren() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersProjection");

        if (container instanceof ConcurrentMessageListenerContainer<?, ?> concurrent) {
            for (MessageListenerContainer child :
                    concurrent.getContainers()) {
                log.info(
                    "childId={}, running={}",
                    child.getListenerId(),
                    child.isRunning()
                );
            }
        }
    }
}
~~~

Đây là ví dụ minh họa; generic type và API visibility có thể cần điều chỉnh theo Spring Kafka version. KafkaListenerEndpointRegistry quản lý listener container được tạo bởi endpoint annotation. Container bean tự khai báo có thể cần được truy cập qua bean name hoặc cơ chế quản lý riêng.

Không nên gọi lifecycle method của child tùy tiện từ nhiều nơi. Việc start/stop child cần theo một quy trình điều phối rõ ràng để tránh assignment và ownership không mong muốn.

### 8.2 Container events

Spring Kafka phát các container event như event khi container start, stop, idle, consumer failed hoặc partition assignment thay đổi tùy phiên bản. Có thể dùng listener cho application event để ghi nhận thay đổi lifecycle.

Ví dụ khái niệm:

~~~java
@Component
public class KafkaContainerEvents {

    @EventListener
    public void onContainerEvent(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped: listenerId={}",
            event.getContainer()
        );
    }
}
~~~

Ví dụ event chỉ minh họa ý tưởng; cần kiểm tra tên event, accessor và package trong phiên bản Spring Kafka đang dùng. Có thể cấu hình event publisher để nhận event từ child container, không chỉ parent.

### 8.3 Client ID và metrics

Mỗi child có consumer client riêng. Spring Kafka có thể thêm suffix vào client id prefix để phân biệt consumer được tạo bởi concurrent container. Điều này giúp metrics broker/client và log nhận diện từng consumer.

Ví dụ các client id có dạng:

~~~text
orders-projection-0
orders-projection-1
orders-projection-2
~~~

Hình thức suffix cụ thể phụ thuộc client id prefix và framework version. Không dựa vào số suffix như một partition id. Suffix phân biệt consumer instance, còn partition assignment được Kafka quản lý riêng.

Theo dõi:

- Consumer client id.
- Assigned partitions theo child.
- Poll rate và processing duration.
- Commit latency và commit failure.
- Rebalance count.
- Listener error rate.
- Consumer lag theo group/topic/partition.
- Số child running so với concurrency mong muốn.

## 9. Thread safety và chia sẻ tài nguyên giữa child container

Các child container chạy song song, thường gọi cùng một listener bean. Đây là một nguồn lỗi phổ biến khi chuyển từ concurrency 1 sang nhiều child.

### 9.1 Tránh mutable state dùng chung

Ví dụ không an toàn:

~~~java
@Component
public class CounterListener {

    private long processedCount;

    @KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        concurrency = "4"
    )
    public void handle(OrderCreated event) {
        processedCount++;
    }
}
~~~

processedCount++ không phải thao tác atomic. Nhiều child thread có thể cập nhật đồng thời và làm mất increment. Nếu cần metrics, dùng Micrometer counter hoặc cấu trúc thread-safe phù hợp.

Không lưu ConsumerRecord hiện tại, correlation id hiện tại hoặc mutable request context vào field singleton để chia sẻ giữa invocation.

### 9.2 Database connection pool

Concurrency làm tăng số listener invocation đồng thời. Nếu mỗi invocation mở transaction database hoặc gọi repository, connection pool phải đủ capacity cho tổng tải thực tế.

Ví dụ ba pod, mỗi pod concurrency 5, có thể tạo tối đa 15 listener invocation đồng thời cho group này. Nếu mỗi invocation cần một connection và pool tổng chỉ có 10 connection trên toàn bộ hệ thống, một phần invocation sẽ chờ. Nếu chờ lâu hơn poll interval hoặc timeout, consumer có thể rebalance hoặc retry.

Cần cân bằng:

- Số child trên mỗi pod.
- Số pod.
- Số partition và tải từng partition.
- Pool connection của database.
- Giới hạn request của downstream.
- Thời gian xử lý trung bình và p95/p99.

### 9.3 Thread pool và async processing

Nếu listener dùng executor khác, tổng số luồng thực thi có thể lớn hơn số child container. Consumer thread có thể tiếp tục poll trong khi task trước chưa hoàn tất nếu code không điều phối cẩn thận. Điều này ảnh hưởng thứ tự, acknowledgment và backpressure.

Nếu cần async listener pattern, dùng cơ chế được Spring Kafka hỗ trợ trong phiên bản tương ứng và hiểu rõ ack semantics. Không tự tạo queue không giới hạn từ consumer thread sang executor; queue có thể tăng vô hạn khi downstream chậm.

### 9.4 Ordering theo partition

Kafka bảo đảm thứ tự record trong một partition. Với group subscription, một partition chỉ được gán cho một consumer member tại một thời điểm. Vì vậy, tăng child container không làm cùng một partition được xử lý song song an toàn theo thứ tự mặc định.

Nếu record cùng business key phải giữ thứ tự, cần bảo đảm chúng được route vào cùng partition bằng key phù hợp. Consumer có thể xử lý nhiều partition song song, nhưng record trong một partition vẫn cần được xử lý theo yêu cầu thứ tự.

Nếu listener gửi task bất đồng bộ và hoàn thành không theo thứ tự, ứng dụng có thể phá vỡ thứ tự nghiệp vụ dù Kafka đã giao record đúng thứ tự. Cần thiết kế sequencing hoặc chỉ xác nhận offset sau khi các side effect trước đó hoàn tất.

## 10. Error handling ở cấp child container

Mỗi child nhận một phần partition assignment và gọi listener trên consumer thread riêng. Một lỗi listener có thể tác động đến partition được gán cho child đó theo error handler và retry policy.

Các vấn đề cần quan sát:

- Một poison record làm child retry liên tục.
- Listener xử lý lâu làm consumer không poll kịp.
- Downstream outage ảnh hưởng nhiều child đồng thời.
- Một child dừng khiến partition được gán lại.
- DLT publish thất bại làm recovery không hoàn tất.

Error handler thường được cấu hình trên ConcurrentKafkaListenerContainerFactory và được áp dụng cho các child container được tạo từ factory đó. Tùy cấu hình, một exception có thể retry tại child, rollback transaction hoặc chuyển record sang DLT.

### 10.1 Retry có thể giữ partition trên child

Với blocking retry, child có thể dành thời gian xử lý lại một record. Các record phía sau trên cùng partition không thể vượt qua record đang bị retry theo thứ tự xử lý của partition.

Nếu child có nhiều partition, một record lỗi có thể ảnh hưởng thời gian poll và tiến triển của các partition khác được gán cho cùng consumer. Vì vậy, cần xem assignment của child khi điều tra một partition bị kẹt.

### 10.2 DLT và child container

Nếu dùng Dead Letter Topic, record lỗi có thể được publish sang DLT sau số lần thử. Sau khi recover thành công và commit offset theo error handling policy, child có thể tiếp tục các record sau.

DLT không phải nơi lưu trữ vô thời hạn mặc định. Cần cấu hình retention, replication, ACL, monitoring và quy trình replay. Nếu DLT publish thất bại, không được coi record đã được xử lý xong.

### 10.3 Một child lỗi không đồng nghĩa phải restart toàn ứng dụng

Nếu chỉ một child gặp lỗi, hãy xác định lỗi thuộc consumer, broker, listener hay dependency. Có thể cần restart container hoặc phục hồi dependency, nhưng restart toàn bộ application có thể gây rebalance trên tất cả child và tạo thêm gián đoạn.

Ưu tiên tìm phạm vi lỗi qua child id, client id, partition assignment và exception gốc trước khi chọn hành động.

## 11. Scale concurrency và thay đổi runtime

Một số phiên bản Spring Kafka cho phép điều chỉnh concurrency của concurrent listener container trong runtime thông qua API của container. Cần kiểm tra phiên bản và lifecycle API trước khi dùng.

Thay đổi concurrency có thể làm parent dừng hoặc tạo lại một phần child container và khiến group rebalance. Đây không phải thao tác miễn phí.

Khi tăng concurrency:

1. Kiểm tra partition count và active consumer count.
2. Kiểm tra capacity broker và downstream.
3. Tăng concurrency theo bước nhỏ.
4. Theo dõi rebalance, lag và processing rate.
5. Xác nhận child mới có assignment.
6. Dừng tăng khi throughput không cải thiện hoặc downstream saturation tăng.

Khi giảm concurrency:

1. Đánh giá số partition còn được gán cho member còn lại.
2. Dừng child theo lifecycle container.
3. Theo dõi rebalance và offset commit.
4. Xác nhận consumer còn lại đủ capacity.
5. Kiểm tra lag sau khi assignment ổn định.

Nếu concurrency thay đổi qua deployment config, rolling deployment có thể khiến số member trong group dao động. Cần tính cả giai đoạn pod cũ và mới cùng tồn tại.

## 12. Tình huống thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Parent running nhưng không có record | Child chưa có assignment, group id sai, topic rỗng hoặc LSO/read policy | Xem trạng thái từng child, group membership, assignment và topic |
| Có child running nhưng một số child idle | Concurrency lớn hơn số partition được gán | So sánh active consumer count với partition count |
| Một partition lag cao | Partition tải lệch, record poison hoặc child xử lý chậm | Xem partition thuộc child nào, listener latency và retry |
| Tăng concurrency nhưng throughput không tăng | Partition count giới hạn, downstream bottleneck hoặc CPU saturation | Xem assignment, database pool, processing rate và CPU |
| Restart một child làm rebalance | Consumer member rời group | Xem rebalance event, committed offset và assignment mới |
| Nhiều listener invocation chạy đồng thời gây race | Listener bean có mutable state không thread-safe | Kiểm tra shared field, cache và dependency |
| Nhiều pod xử lý cùng record | Group id khác nhau hoặc manual assignment trùng | Kiểm tra group id và assignment mode |
| Shutdown kéo dài | Listener đang xử lý lâu hoặc task async chưa kết thúc | Xem processing duration, shutdown timeout và executor queue |
| DLT tăng nhanh | Poison message hoặc downstream lỗi hàng loạt | Phân loại exception, retry count và dependency health |

Một triệu chứng không đủ kết luận nguyên nhân. Ví dụ, một child idle có thể hoàn toàn bình thường nếu số child lớn hơn partition count. Ngược lại, parent running nhưng tất cả child không có assignment có thể là cấu hình group hoặc subscription sai.

## 13. Quy trình điều tra child container không xử lý record

Khi một concurrent listener không xử lý record như mong đợi:

1. Xác định listener id và tên ConcurrentMessageListenerContainer.
2. Đọc concurrency cấu hình ở factory và annotation; xác nhận giá trị runtime.
3. Liệt kê child container và trạng thái running/stopped của từng child.
4. Xác định consumer client id tương ứng với child.
5. Kiểm tra group id, member count và partition assignment trong Kafka.
6. Xác định partition nào chưa có consumer hoặc đang lag.
7. Kiểm tra poll rate, listener processing duration, error handler và retry.
8. Đối chiếu database/downstream latency, pool saturation và thread state.
9. Kiểm tra rebalance event, consumer restart và commit failures.
10. Sau khi xử lý nguyên nhân, xác nhận child có assignment, offset tiến triển và business side effect hoàn tất.

Nếu parent có concurrency 4 nhưng chỉ ba partition, một child idle có thể là expected. Nếu cả bốn child không có assignment, cần kiểm tra group id, topic subscription, ACL và trạng thái group.

## 14. Kiểm thử cấu trúc parent-child và concurrency

Nên kiểm thử trong môi trường tích hợp với topic có số partition biết trước.

### 14.1 Kiểm tra số child

- Cấu hình concurrency bằng 3.
- Khởi động listener.
- Xác nhận parent là ConcurrentMessageListenerContainer.
- Xác nhận parent quản lý ba child KafkaMessageListenerContainer.
- Xác nhận mỗi child có consumer client riêng.

### 14.2 Kiểm tra partition assignment

- Tạo topic có sáu partition.
- Chạy một application instance với concurrency 3.
- Xác nhận ba child tham gia cùng group.
- Xác nhận partition được phân phối giữa consumer.
- Tăng concurrency lên 8 và xác nhận số consumer có assignment không vượt số partition của topic trong group.

### 14.3 Kiểm tra nhiều replica

- Chạy hai pod, mỗi pod concurrency 3.
- Xác nhận tổng số consumer member xấp xỉ sáu cho group khi cả hai pod ổn định.
- Xác nhận group id giống nhau giữa các pod.
- Xác nhận partition được chia trên toàn group, không phải mỗi pod nhận toàn bộ stream.
- Restart một pod và xác nhận partition được gán lại.

### 14.4 Kiểm tra thread safety

- Gửi nhiều record với các key khác nhau.
- Ghi nhận listener thread name và child/client id.
- Xác nhận invocation có thể chạy đồng thời.
- Kiểm tra shared state, database pool và downstream concurrency.
- Xác nhận thứ tự theo partition/key được giữ theo thiết kế.

### 14.5 Kiểm tra lỗi và shutdown

- Tạo một record lỗi để kiểm tra retry/DLT ở child.
- Dừng một child hoặc một pod trong môi trường thử nghiệm.
- Xác nhận partition được gán lại và record chưa commit được xử lý lại an toàn.
- Kiểm tra graceful shutdown khi listener đang xử lý.
- Xác nhận parent và child đều dừng theo lifecycle mong muốn.

## 15. Checklist thiết kế và vận hành

**Cấu trúc container**

- [ ] Listener dùng ConcurrentMessageListenerContainer khi cần concurrency.
- [ ] Parent quản lý số child container dự kiến.
- [ ] Mỗi child có consumer riêng và consumer thread riêng.
- [ ] Phân biệt số child được tạo với số consumer có partition assignment.
- [ ] Biết listener đang dùng group subscription hay explicit assignment.

**Concurrency và partition**

- [ ] Tổng consumer được tính bằng số pod nhân concurrency mỗi pod.
- [ ] Concurrency được so sánh với partition count của từng group.
- [ ] Không tăng concurrency khi downstream đã quá tải.
- [ ] Assignment được quan sát theo partition và child/client id.
- [ ] Các replica cùng logical subscription dùng cùng group id.

**Code và tài nguyên**

- [ ] Listener singleton an toàn khi được gọi đồng thời.
- [ ] Shared state, cache và metrics dùng cơ chế thread-safe.
- [ ] Database pool và HTTP pool đủ capacity cho mức concurrency dự kiến.
- [ ] Async processing có acknowledgment/backpressure rõ ràng.
- [ ] Thứ tự nghiệp vụ theo partition/key được bảo toàn.

**Lifecycle và phục hồi**

- [ ] Parent và child có graceful start/stop.
- [ ] Theo dõi trạng thái child, assignment và rebalance.
- [ ] Retry hữu hạn và DLT được vận hành.
- [ ] Một child lỗi được khoanh vùng trước khi restart toàn ứng dụng.
- [ ] Đã kiểm thử scale, pod restart, child idle và shutdown trong môi trường phù hợp.

ConcurrentMessageListenerContainer là lớp quản lý concurrency của Spring Kafka. Parent tạo và điều phối các KafkaMessageListenerContainer con; mỗi child quản lý một consumer riêng để poll và xử lý partition được gán. Khi cấu hình số child, cần tính cả số replica ứng dụng, partition count, assignment mode và năng lực downstream. Khi quan sát sự cố, hãy đi từ parent xuống child, consumer, partition và listener để xác định đúng phạm vi bị ảnh hưởng.

