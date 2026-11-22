# ConcurrentMessageListenerContainer

## 1. Vai trò trong Spring Kafka

`ConcurrentMessageListenerContainer` là container của Spring Kafka dùng để chạy một listener với nhiều Kafka consumer đồng thời. Nó quản lý vòng đời của các container con, phối hợp cấu hình listener và phân phối việc tiêu thụ record qua nhiều consumer thread.

Kafka client cung cấp `KafkaConsumer`, mỗi consumer thực hiện poll trên thread sở hữu nó và tham gia consumer group để nhận partition assignment. Spring Kafka cung cấp `KafkaMessageListenerContainer` để quản lý một consumer. Khi cần concurrency, `ConcurrentMessageListenerContainer` tạo và quản lý nhiều `KafkaMessageListenerContainer` con.

Ví dụ, đặt concurrency bằng 3 thường tạo ba container con, mỗi container có một Kafka consumer và một luồng xử lý poll riêng. Các consumer này dùng cùng cấu hình group của listener, vì vậy Kafka phân phối partition trong group giữa chúng.

Điều quan trọng là concurrency tạo thêm consumer và khả năng xử lý song song theo partition. Nó không làm một partition được nhiều consumer trong cùng group đọc đồng thời, cũng không tự tăng số partition của topic.

## 2. Cấu trúc container cha và container con

Có thể hình dung cấu trúc như sau:

~~~text
ConcurrentMessageListenerContainer
             |
             +-- KafkaMessageListenerContainer #1
             |          |
             |          +-- KafkaConsumer #1
             |          +-- Consumer thread #1
             |
             +-- KafkaMessageListenerContainer #2
             |          |
             |          +-- KafkaConsumer #2
             |          +-- Consumer thread #2
             |
             +-- KafkaMessageListenerContainer #3
                        |
                        +-- KafkaConsumer #3
                        +-- Consumer thread #3

             Tất cả consumer cùng tham gia
             một consumer group của listener
~~~

Container cha điều phối start, stop, pause/resume và trạng thái của các container con. Mỗi container con quản lý một Kafka consumer và thực hiện poll trên thread riêng.

Vì vậy, khi nói listener có concurrency bằng 3, ta đang nói có tối đa ba consumer instance hoạt động cho listener đó trong cùng ứng dụng. Số consumer thực sự có partition để đọc còn phụ thuộc số partition và cách Kafka assign partition.

### 2.1. Khác nhau giữa hai loại container

| Thành phần | Trách nhiệm |
|---|---|
| `KafkaMessageListenerContainer` | Quản lý một Kafka consumer, poll loop, listener invocation và commit offset |
| `ConcurrentMessageListenerContainer` | Quản lý nhiều `KafkaMessageListenerContainer` con và điều phối vòng đời của chúng |
| `KafkaConsumer` | Client Kafka thực hiện subscribe/assign, poll, commit và nhận record |
| `ConcurrentKafkaListenerContainerFactory` | Tạo container phù hợp cho endpoint được khai báo bằng `@KafkaListener` |

Ứng dụng thường không cần tự tạo từng container con. Có thể cấu hình một `ConcurrentKafkaListenerContainerFactory` và để Spring Kafka tạo container cho listener endpoint.

### 2.2. Container cha không phải một KafkaConsumer dùng chung

Mỗi consumer con có client ID, poll loop, buffer và trạng thái assignment riêng. Việc một consumer con gặp rebalance hoặc lỗi không có nghĩa toàn bộ consumer khác đang chạy trên cùng JVM dùng chung một KafkaConsumer object.

Các consumer vẫn thuộc cùng group nếu chúng dùng cùng group ID. Kafka coordinator quản lý membership và partition assignment của group đó.

## 3. Concurrency và partition assignment

Kafka phân phối partition trong một consumer group sao cho tại một thời điểm, mỗi partition được gán cho tối đa một consumer trong group. Nhiều consumer có thể cùng đọc một topic nếu topic có nhiều partition.

Giả sử topic `orders.created` có sáu partition và listener có concurrency bằng ba:

~~~text
Topic orders.created:
  P0  P1  P2  P3  P4  P5

Consumer group order-fulfillment:
  Consumer #1 -> P0, P1
  Consumer #2 -> P2, P3
  Consumer #3 -> P4, P5
~~~

Assignment thực tế phụ thuộc partition assignor và membership của group. Sơ đồ chỉ minh họa một cách phân phối có thể xảy ra.

Nếu topic chỉ có hai partition nhưng concurrency bằng bốn, tối đa hai consumer có thể nhận partition trong group tại thời điểm đó:

~~~text
Topic orders.created:
  P0  P1

Consumer group:
  Consumer #1 -> P0
  Consumer #2 -> P1
  Consumer #3 -> không có partition
  Consumer #4 -> không có partition
~~~

Các consumer không có partition vẫn có thể là thành viên của group và tham gia poll/rebalance, nhưng không đóng góp thêm khả năng xử lý record của topic đó. Tăng concurrency vượt số partition không làm tăng throughput tiêu thụ của một group.

### 3.1. Giới hạn song song theo partition

Với một topic có P partition và một consumer group có C consumer, số consumer có thể đọc topic cùng lúc không vượt quá số partition được phân phối cho group. Trong trường hợp đơn giản, mức song song hữu ích tối đa xấp xỉ:

`min(P, C)`

Nếu listener subscribe nhiều topic, cần xem tổng partition và assignment trên toàn bộ tập topic. Một consumer có thể nhận partition từ nhiều topic; phân bố không nhất thiết đều tuyệt đối.

### 3.2. Nhiều consumer group là một trường hợp khác

Nếu hai ứng dụng dùng hai group ID khác nhau, mỗi group có thể nhận toàn bộ record của topic. Đây là cơ chế fan-out để nhiều hệ thống độc lập cùng tiêu thụ event, không phải cách tăng concurrency cho cùng một công việc.

Nếu mục tiêu là chia tải xử lý một luồng event giữa các instance, các instance phải tham gia cùng consumer group. Nếu mỗi instance có group ID riêng, mỗi instance sẽ đọc bản sao luồng dữ liệu theo semantics của Kafka.

## 4. Cấu hình concurrency bằng Spring Boot

Spring Boot có thể cấu hình concurrency mặc định cho các listener container do auto-configured factory tạo ra.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: localhost:9092
      group-id: order-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: batch
~~~

Với cấu hình này, listener container mặc định có concurrency bằng ba. Mỗi consumer con dùng consumer factory và các thiết lập group/consumer tương ứng.

`ack-mode: batch` là chính sách commit offset của listener container. Nó độc lập với concurrency: một property quyết định thời điểm commit, property còn lại quyết định số consumer con được quản lý.

Nếu ứng dụng dùng custom container factory, hãy xác nhận factory đó được cấu hình từ Boot properties hoặc tự đặt concurrency. Một factory tự tạo có thể không nhận mọi thiết lập từ factory mặc định.

## 5. Cấu hình bằng ConcurrentKafkaListenerContainerFactory

Khi cần factory riêng cho một luồng, có thể đặt concurrency trên `ConcurrentKafkaListenerContainerFactory`:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Listener sử dụng factory này:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-fulfillment-listener",
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderKafkaListenerContainerFactory"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Khi container được khởi tạo, factory tạo concurrent container và container này quản lý ba consumer con. Nếu topic có đủ partition, Kafka có thể phân phối công việc giữa ba consumer.

### 5.1. Ghi đè concurrency ở @KafkaListener

Spring Kafka cho phép chỉ định concurrency ngay trên endpoint:

~~~java
@KafkaListener(
    id = "orders-fulfillment-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Giá trị concurrency của endpoint có thể ghi đè giá trị từ factory. Có thể dùng placeholder cấu hình để điều chỉnh theo môi trường:

~~~java
@KafkaListener(
    id = "orders-fulfillment-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "${orders.consumer.concurrency:3}"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Với cách này, có thể đặt giá trị trong file cấu hình:

~~~yaml
orders:
  consumer:
    concurrency: 3
~~~

Nên chọn một nguồn cấu hình rõ ràng để tránh việc factory và annotation đặt các giá trị khác nhau khiến người vận hành khó xác định concurrency thực tế.

## 6. Cấu hình client ID cho từng consumer

Khi có nhiều consumer trong cùng một ứng dụng, client ID riêng giúp nhận diện metric, log và kết nối của từng consumer.

Có thể cấu hình prefix trên listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders-fulfillment"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Với concurrent container, Spring Kafka thêm hậu tố phân biệt cho các consumer con khi cần, giúp client ID không trùng nhau. Ví dụ minh họa:

~~~text
orders-fulfillment-0
orders-fulfillment-1
orders-fulfillment-2
~~~

Prefix này hữu ích khi lọc metric hoặc log theo client ID. Cần tránh tái sử dụng cùng prefix cho nhiều listener không liên quan nếu công cụ giám sát cần phân biệt từng endpoint.

## 7. Cấu hình topic và partition assignment

Có hai cách phổ biến để listener tham gia nhận partition:

- Subscribe theo topic và để Kafka consumer group tự phân phối partition.
- Gán partition tường minh cho listener bằng `topicPartitions`.

### 7.1. Subscribe theo topic

Đây là cách thường dùng khi muốn các instance tự tham gia group và Kafka quản lý assignment:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Kafka group coordinator và partition assignor phân phối các partition của topic cho các consumer thành viên. Khi consumer tham gia hoặc rời group, assignment có thể thay đổi và gây rebalance.

### 7.2. Gán partition tường minh

Nếu cần listener nhận một tập partition cụ thể, có thể dùng `@TopicPartition`:

~~~java
@KafkaListener(
    id = "priority-orders-listener",
    topicPartitions = @TopicPartition(
        topic = "orders.priority",
        partitions = {"0", "1", "2", "3"}
    ),
    concurrency = "2"
)
public void consumePriority(OrderCreated event) {
    fulfillmentService.processPriority(event);
}
~~~

Với concurrent container và assignment tường minh, Spring Kafka phân phối các partition được chỉ định cho các container con. Khi concurrency lớn hơn số partition được chỉ định, concurrency được điều chỉnh để không tạo nhiều consumer con hơn số partition có thể phân công trong cấu hình đó.

Manual assignment hữu ích khi cần kiểm soát chính xác partition, nhưng ứng dụng phải có kế hoạch thay đổi assignment khi topology thay đổi. Subscribe theo group thường phù hợp hơn khi muốn Kafka tự cân bằng partition giữa các instance.

## 8. Quan hệ giữa concurrency, partition và số instance

Concurrency trong một JVM và số replica ứng dụng trong deployment cùng ảnh hưởng tổng số consumer.

Giả sử:

- Topic có 12 partition.
- Mỗi pod chạy một listener với concurrency bằng 3.
- Deployment có 2 pod.
- Tất cả consumer dùng cùng group ID.

Tổng số consumer là sáu. Kafka có thể phân phối 12 partition cho sáu consumer, trung bình khoảng hai partition mỗi consumer.

~~~text
orders.created: 12 partitions

Pod A:
  Concurrent container
    Consumer A1
    Consumer A2
    Consumer A3

Pod B:
  Concurrent container
    Consumer B1
    Consumer B2
    Consumer B3

Consumer group order-fulfillment:
  6 consumer chia nhau 12 partition
~~~

Nếu tăng lên bốn pod, concurrency vẫn bằng ba, tổng consumer thành 12. Khi đó mỗi consumer có thể nhận một partition. Nếu tiếp tục tăng lên sáu pod, tổng consumer thành 18 nhưng topic vẫn chỉ có 12 partition; ít nhất sáu consumer sẽ không có partition.

Cần tính tổng concurrency của toàn deployment:

`TotalConsumers = replicas 	imes concurrencyPerReplica`

Đây là số consumer được tạo, không phải số consumer chắc chắn có partition. Năng lực song song hữu ích còn bị giới hạn bởi số partition, tốc độ broker, CPU, network và downstream.

### 8.1. Chọn concurrency theo partition

Một điểm bắt đầu là không đặt tổng consumer vượt xa số partition của workload. Tuy nhiên, không nhất thiết phải luôn có một consumer cho mỗi partition. Nếu mỗi record tốn nhiều CPU hoặc downstream có giới hạn kết nối, concurrency thấp hơn có thể ổn định hơn.

Hãy cân nhắc:

- Số partition và cách partition phân bố trên broker.
- Throughput và kích thước record.
- Thời gian xử lý p95/p99 của listener.
- Năng lực CPU, heap và network của ứng dụng.
- Connection pool và throughput của DB hoặc API downstream.
- SLO event freshness và mức consumer lag chấp nhận được.

## 9. Threading và tính an toàn của listener

Mỗi consumer con chạy poll loop trên thread riêng. Vì vậy, cùng một listener bean có thể được gọi đồng thời từ nhiều thread khi concurrency lớn hơn một.

Điều này ảnh hưởng đến cách viết code:

- Không lưu trạng thái mutable dùng chung trong field của listener nếu không có đồng bộ phù hợp.
- Dùng service stateless hoặc thiết kế thread-safe.
- Đảm bảo repository và connection pool đáp ứng số lời gọi song song.
- Tránh dùng một object không thread-safe chung cho tất cả consumer.
- Không gọi trực tiếp KafkaConsumer từ thread khác với thread sở hữu consumer.

Ví dụ listener stateless:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        concurrency = "3"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Nếu `FulfillmentService` giữ cache hoặc mutable state trong bộ nhớ, cần đánh giá thread safety. Một singleton Spring bean mặc định được chia sẻ giữa các consumer thread.

### 9.1. Thứ tự xử lý

Kafka đảm bảo thứ tự trong một partition. Trong cùng consumer group, một partition chỉ được gán cho một consumer tại một thời điểm, vì vậy concurrency không làm nhiều consumer trong group đọc cùng partition song song.

Các partition khác nhau có thể được xử lý đồng thời. Do đó:

- Event cùng key thường được đưa vào cùng partition nếu partitioner và key ổn định.
- Event cùng partition giữ thứ tự log khi xử lý đồng bộ theo poll loop.
- Không có thứ tự toàn cục giữa các partition.
- Nếu listener tự chuyển xử lý sang thread pool hoặc trả về kết quả bất đồng bộ, ứng dụng phải tự quản lý thứ tự hoàn tất và commit semantics phù hợp.

Nếu nghiệp vụ cần thứ tự theo order ID, hãy dùng key ổn định để các event của cùng đơn hàng đi vào cùng partition và tránh tạo xử lý bất đồng bộ làm đảo thứ tự ngoài ý muốn.

## 10. Tương tác với AckMode và batch listener

Concurrency xác định số consumer con. AckMode xác định thời điểm container commit offset. Hai thiết lập này độc lập nhưng phối hợp trong vận hành.

Với AckMode.BATCH, mỗi consumer con commit offset sau khi các record trong poll của chính consumer đó được xử lý xong. Không có một batch chung giữa các consumer con.

Ví dụ:

~~~text
Consumer #1:
  poll -> records P0, P1
  xử lý xong -> commit offset của P0, P1

Consumer #2:
  poll -> records P2, P3
  xử lý xong -> commit offset của P2, P3

Consumer #3:
  poll -> records P4, P5
  xử lý xong -> commit offset của P4, P5
~~~

Nếu dùng batch listener, mỗi child container có thể chuyển batch record của poll cho listener. Các batch từ consumer khác vẫn được xử lý độc lập.

Khi một consumer gặp lỗi, error handler của container đó xử lý retry/recovery theo cấu hình. Các consumer con khác có thể tiếp tục xử lý partition được gán cho chúng. Tuy nhiên, rebalance hoặc lỗi toàn ứng dụng có thể ảnh hưởng nhiều consumer hơn; không nên xem mỗi child là một dịch vụ hoàn toàn tách biệt.

## 11. Rebalance khi concurrency thay đổi

Kafka consumer group thực hiện rebalance khi membership hoặc subscription thay đổi, hoặc khi điều kiện assignment thay đổi. Những tình huống thường gặp:

- Một pod mới khởi động và tạo thêm consumer.
- Một pod bị dừng hoặc mất kết nối.
- Listener container được start hoặc stop.
- Concurrency thay đổi làm số consumer trong group thay đổi.
- Topic được thêm partition hoặc subscription thay đổi.

Trong rebalance, partition có thể bị thu hồi từ consumer cũ và gán cho consumer mới. Ứng dụng cần hoàn tất xử lý đang diễn ra theo semantics của container, commit offset phù hợp và tránh side effect không an toàn khi record được giao lại.

### 11.1. Tác động tới độ trễ và throughput

Rebalance thường tạo một khoảng thời gian consumer chưa xử lý bình thường. Nếu scale ứng dụng liên tục hoặc consumer thường xuyên rời group, lag có thể tăng dù tổng CPU vẫn còn.

Cần theo dõi:

- Rebalance rate và thời gian rebalance.
- Partition assignment theo consumer.
- Consumer group state.
- Consumer lag trước, trong và sau rebalance.
- Thời gian xử lý record và số record chưa commit.
- Lỗi heartbeat, session timeout hoặc poll interval.

Không tăng concurrency liên tục chỉ vì lag tăng. Lag có thể đến từ downstream chậm, hot partition, broker bottleneck hoặc rebalance lặp lại. Cần tìm nguyên nhân trước khi scale.

### 11.2. Graceful shutdown

Khi ứng dụng dừng, container cha dừng các container con theo lifecycle của Spring. Một shutdown có kiểm soát giúp consumer rời group, hoàn tất công việc đang xử lý trong giới hạn cấu hình và commit offset theo chính sách hiện tại.

Trong deployment, nên cho ứng dụng đủ thời gian graceful shutdown trước khi process bị kill. Thời gian thực tế cần phù hợp với thời gian xử lý listener, retry và orchestration termination grace period.

Nếu process bị kill đột ngột, record chưa commit có thể được giao lại. Idempotent consumer vẫn cần thiết ngay cả khi đã có graceful shutdown.

## 12. Pause, resume và quản lý tải

Concurrent container cung cấp khả năng điều khiển trạng thái tiêu thụ thông qua API container. Có thể lấy container theo ID từ `KafkaListenerEndpointRegistry`, sau đó yêu cầu pause hoặc resume.

Ví dụ:

~~~java
@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Khi thao tác với concurrent container, pause/resume được áp dụng qua container quản lý các consumer con. Cần phân biệt yêu cầu pause với trạng thái đã pause thực tế; Kafka consumer thực hiện pause/resume trên consumer thread theo cơ chế của container.

Pause hữu ích khi downstream đang quá tải, cần bảo trì hoặc muốn kiểm soát tốc độ nhận record. Tuy nhiên, pause không xóa record trong Kafka và không làm consumer group ngừng tồn tại. Khi resume, consumer tiếp tục đọc từ vị trí phù hợp với offset hiện tại.

Nếu pause quá lâu, cần xem xét các timeout và tình trạng group theo phiên bản Kafka client, đặc biệt khi consumer không tiếp tục poll. Dùng API của container thay vì gọi trực tiếp KafkaConsumer từ thread ứng dụng.

## 13. Cấu hình và vận hành nhiều listener

Một ứng dụng có thể có nhiều listener với mục tiêu throughput khác nhau. Mỗi listener nên có ID, group ID, topic và factory rõ ràng.

Ví dụ hai listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void consumeOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
    id = "audit-listener",
    topics = "orders.audit",
    groupId = "audit-indexer",
    containerFactory = "auditKafkaListenerContainerFactory"
)
public void consumeAudit(OrderAudit event) {
    auditService.index(event);
}
~~~

Factory cho mỗi listener có thể đặt concurrency, AckMode, error handler và batch mode riêng. Không nên dùng một concurrency cao cho mọi luồng chỉ vì một topic cần throughput lớn.

Với nhiều listener, cần tính tổng số consumer trên mỗi pod và tổng số consumer của toàn deployment. Ví dụ ba listener mỗi listener concurrency bằng bốn có thể tạo 12 consumer trên một pod. Điều đó ảnh hưởng số kết nối, thread, heap, CPU và tải broker.

## 14. Quan sát ConcurrentMessageListenerContainer

Để vận hành concurrent container, cần theo dõi cả trạng thái container và metric của Kafka consumer.

| Nhóm quan sát | Chỉ số hoặc thông tin |
|---|---|
| Container lifecycle | Running/stopped, start/stop event, pause state |
| Consumer identity | Group ID, client ID, member ID |
| Partition assignment | Partition mỗi consumer đang sở hữu |
| Throughput | Records/bytes consumed theo consumer và topic |
| Lag | Lag theo group, topic và partition |
| Processing | Listener duration, batch duration, lỗi xử lý |
| Commit | Commit rate, commit latency, commit failures |
| Rebalance | Rebalance count, thời gian và nguyên nhân |
| Resource | Thread count, heap, GC, CPU và connection pool |
| Downstream | DB pool saturation, API latency, timeout và retry |

Spring Kafka và Kafka client có thể tích hợp Micrometer để phát metric, tùy phiên bản và cấu hình. Client ID suffix giúp phân biệt consumer con trong dashboard. Hãy kiểm tra metric thực tế được export và giữ label cardinality ở mức kiểm soát.

### 14.1. Theo dõi partition assignment

Lag tổng của group có thể che khuất một partition bị nóng. Nên xem lag theo partition và client ID để xác định:

- Một consumer có nhận quá nhiều partition so với consumer khác không.
- Một partition có lưu lượng lớn hơn hẳn các partition còn lại không.
- Một consumer có processing duration hoặc error rate cao bất thường không.
- Consumer nào không có assignment do concurrency vượt số partition.

Nếu một partition bị hot, tăng concurrency không nhất thiết giải quyết được vì partition đó vẫn chỉ được gán cho một consumer trong group. Có thể cần xem lại key distribution hoặc tăng partition sau khi đánh giá tác động tới ordering và dữ liệu hiện có.

## 15. Chẩn đoán các tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Tăng concurrency nhưng throughput không đổi | Số partition thấp, downstream là bottleneck hoặc consumer không nhận partition | Kiểm tra assignment, partition count, DB/API latency |
| Nhiều consumer ở trạng thái idle | Concurrency lớn hơn số partition có thể gán | So sánh tổng consumer với partition count |
| Lag chỉ cao trên một partition | Hot key hoặc phân phối key không đều | Xem records/bytes theo partition và key strategy |
| Rebalance liên tục | Pod restart, heartbeat/poll timeout hoặc thay đổi membership | Xem lifecycle, logs, timeout và deployment events |
| DB connection pool cạn | Listener concurrency vượt khả năng DB | Đo active connection, wait time và downstream latency |
| Heap tăng mạnh | Quá nhiều consumer, fetch buffer lớn hoặc batch lớn | Xem heap, fetch limits, max.poll.records và concurrency |
| Record xử lý trùng sau scale/restart | Side effect đã chạy nhưng offset chưa commit | Kiểm tra AckMode, error handling và idempotency |
| Thứ tự event sai theo nghiệp vụ | Event cùng entity vào nhiều partition hoặc xử lý async không kiểm soát | Kiểm tra key, partitioner và listener execution model |
| Pause nhưng record vẫn được xử lý trong chốc lát | Yêu cầu pause đang chờ consumer thread áp dụng hoặc record đã được poll | Kiểm tra pause state và cách xử lý poll hiện tại |

Khi điều tra, xác định trước consumer group, topic, partition và client ID bị ảnh hưởng. So sánh thời điểm thay đổi concurrency với rebalance, lag và downstream latency. Tránh scale consumer hoặc tăng timeout trước khi xác định nguyên nhân.

## 16. Lựa chọn concurrency theo tải thực tế

Một quy trình lựa chọn có thể bắt đầu như sau:

1. Ghi nhận số partition của các topic listener subscribe.
2. Đo records/bytes per second và phân bố tải theo partition.
3. Đo processing duration p50/p95/p99 và độ trễ downstream.
4. Chọn concurrency ban đầu phù hợp với số partition và tài nguyên pod.
5. Chạy thử tải đại diện và quan sát assignment, lag, throughput, rebalance và resource.
6. Tăng concurrency từng bước nếu consumer là bottleneck và downstream còn năng lực.
7. Dừng tăng khi throughput không cải thiện, partition không đủ hoặc tài nguyên/downstream chạm giới hạn.
8. Kiểm tra lại tổng consumer khi tăng số pod trong deployment.
9. Ghi lại cấu hình, số liệu trước/sau và giới hạn scale trong runbook.

Nếu cần throughput cao hơn nhưng đã có một consumer cho mỗi partition, có thể cần tăng số partition hoặc tối ưu xử lý. Tăng partition có ảnh hưởng đến key mapping và thứ tự event; đây là thay đổi thiết kế topic cần được đánh giá riêng.

## 17. Những sai lầm thường gặp

**Cho rằng concurrency là số thread listener tùy ý.** Mỗi consumer con có KafkaConsumer và poll loop riêng. Số consumer hữu ích bị giới hạn bởi partition assignment.

**Tăng concurrency vượt xa partition count.** Consumer dư không tạo thêm khả năng đọc song song và vẫn tiêu thụ tài nguyên.

**Nhầm nhiều consumer trong một group với nhiều group.** Một group chia partition để xử lý công việc; nhiều group nhận bản sao dữ liệu độc lập.

**Dùng listener bean có state mutable mà không thread-safe.** Nhiều consumer thread có thể gọi cùng một singleton bean đồng thời.

**Cho rằng một partition có thể được xử lý song song bởi nhiều consumer cùng group.** Kafka chỉ gán một partition cho một consumer trong group tại một thời điểm.

**Tăng concurrency để chữa hot partition.** Partition nóng vẫn chỉ có một consumer sở hữu. Cần xem key distribution và thiết kế partition.

**Không tính tổng concurrency toàn deployment.** Số consumer bằng concurrency trên mỗi replica nhân với số replica, trước khi tính partition assignment.

**Gọi KafkaConsumer trực tiếp từ thread khác.** KafkaConsumer không thread-safe; dùng container API để điều khiển pause/resume và lifecycle.

**Bỏ qua downstream capacity.** Consumer nhanh hơn có thể làm DB hoặc API quá tải. Cần điều chỉnh concurrency cùng connection pool và backpressure.

**Không quan sát rebalance.** Scale liên tục có thể làm group mất thời gian ổn định và khiến lag tăng.

## 18. Ví dụ tổng hợp: Order fulfillment

Giả sử topic `orders.created` có 12 partition. Ứng dụng Order Fulfillment chạy ba pod, mỗi pod cấu hình concurrency bằng hai. Tất cả consumer dùng group ID `order-fulfillment`.

Tổng số consumer được tạo:

`3 pods × 2 consumers = 6 consumers`

Kafka phân phối 12 partition cho sáu consumer. Nếu tải tương đối đều, mỗi consumer có thể nhận khoảng hai partition.

Cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: kafka:9092
      group-id: order-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 2
      ack-mode: batch

orders:
  consumer:
    max-poll-records: 100
~~~

Listener:

~~~java
@Service
public class OrderFulfillmentListener {

    private final FulfillmentService fulfillmentService;

    public OrderFulfillmentListener(
            FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-fulfillment",
        topics = "orders.created",
        groupId = "order-fulfillment",
        concurrency = "${spring.kafka.listener.concurrency:2}",
        clientIdPrefix = "orders-fulfillment"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Khi lượng đơn tăng, đội vận hành quan sát lag theo partition, processing duration và DB pool. Nếu tất cả consumer đều bận, lag tăng đồng đều và DB vẫn còn năng lực, có thể cân nhắc tăng concurrency hoặc số pod. Nếu chỉ một partition tăng lag, cần kiểm tra key distribution và hot partition. Nếu DB pool đã bão hòa, tăng concurrency có thể làm tình hình tệ hơn.

Nếu tăng lên sáu pod trong khi concurrency vẫn bằng hai, tổng consumer là 12, bằng số partition. Đây có thể là một điểm scale hợp lý nếu broker và downstream đáp ứng. Nếu tiếp tục tăng lên tám pod, sẽ có 16 consumer cho 12 partition; ít nhất bốn consumer không có partition trong trạng thái assignment đơn giản.

Ví dụ này cho thấy quyết định scale cần dựa trên partition, throughput và năng lực xử lý thực tế, không chỉ CPU của ứng dụng.

## 19. Quy trình triển khai và vận hành

1. Xác định listener endpoint, group ID, topic subscription và partition count.
2. Chọn concurrency ban đầu ở factory hoặc trên `@KafkaListener`.
3. Đảm bảo mỗi consumer có client ID nhận diện được.
4. Kiểm tra listener bean và downstream service có thể chạy đồng thời an toàn.
5. Đặt AckMode, error handler, retry và batch mode phù hợp với nghiệp vụ.
6. Tính tổng consumer trên tất cả pod và so sánh với partition count.
7. Triển khai có kiểm soát và theo dõi rebalance trong lúc group hội tụ.
8. Đo lag theo partition, throughput, processing duration, commit, resource và downstream.
9. Dùng pause/resume qua container API khi cần kiểm soát tải hoặc bảo trì.
10. Kiểm tra graceful shutdown và khả năng replay an toàn khi consumer restart.
11. Ghi rõ giới hạn concurrency, số partition và hành động scale trong runbook.

## 20. Ghi nhớ

`ConcurrentMessageListenerContainer` là container Spring Kafka quản lý nhiều `KafkaMessageListenerContainer` con. Mỗi container con quản lý một Kafka consumer và poll loop riêng. Các consumer thường tham gia cùng consumer group để chia nhau partition.

Concurrency giúp xử lý nhiều partition song song, nhưng mức song song hữu ích bị giới hạn bởi số partition và năng lực downstream. Listener bean có thể được gọi đồng thời, vì vậy code và service dùng chung cần thread-safe. Khi scale, cần quan sát partition assignment, lag, rebalance, processing latency, tài nguyên và side effect để bảo đảm consumer group hoạt động ổn định.

