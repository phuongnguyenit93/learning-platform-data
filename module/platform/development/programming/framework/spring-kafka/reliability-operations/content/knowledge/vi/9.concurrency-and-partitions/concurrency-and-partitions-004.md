# clientIdSuffix

## 1. Vai trò của clientIdSuffix trong Spring Kafka

Khi một listener Spring Kafka chạy với concurrency lớn hơn một, framework tạo nhiều consumer để đọc các partition song song. Mỗi consumer là một Kafka client riêng, có poll loop, kết nối và bộ metric riêng. Để phân biệt các client này trong log, broker metrics và công cụ giám sát, Spring Kafka có thể gắn một hậu tố vào client ID.

**clientIdSuffix** là hậu tố Spring Kafka thêm vào client ID nền của từng consumer con do `ConcurrentMessageListenerContainer` quản lý. Khi có concurrency, các consumer con thường nhận các client ID như:

~~~text
orders-fulfillment-0
orders-fulfillment-1
orders-fulfillment-2
~~~

Trong ví dụ này, `orders-fulfillment` là client ID prefix và `-0`, `-1`, `-2` là các suffix do concurrent container tạo ra.

Hậu tố giúp người vận hành nhận ra consumer nào đang phát metric, ghi log hoặc tạo request tới broker. Nó phục vụ nhận diện và quan sát. Nó không quyết định consumer thuộc group nào, partition nào được gán, hoặc record nào được xử lý.

## 2. Phân biệt client.id, clientIdPrefix, clientIdSuffix và group.id

Các tên này có liên quan nhưng đại diện cho những khái niệm khác nhau:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `client.id` | Kafka client identifier được gửi cùng request và dùng trong metric/log | `orders-fulfillment-0` |
| `clientIdPrefix` | Prefix Spring Kafka dùng làm nền để tạo client ID cho listener | `orders-fulfillment` |
| `clientIdSuffix` | Hậu tố phân biệt các consumer con của concurrent container | `-0`, `-1`, `-2` |
| `group.id` | Định danh consumer group; các consumer cùng group chia nhau partition | `order-fulfillment` |
| `group.instance.id` | Định danh thành viên tĩnh của group khi dùng static membership | `order-fulfillment-pod-a` |

`client.id` và `group.id` không thay thế nhau. Hai consumer có thể có client ID khác nhau nhưng cùng group ID để chia partition. Ngược lại, hai consumer có client ID giống nhau nhưng group ID khác nhau vẫn thuộc hai consumer group độc lập.

`clientIdSuffix` cũng không phải partition number. Consumer có client ID kết thúc bằng `-0` có thể nhận một hoặc nhiều partition; sau rebalance, assignment có thể thay đổi trong khi client ID vẫn giữ nguyên.

## 3. Cách concurrent container tạo suffix

`ConcurrentMessageListenerContainer` quản lý nhiều `KafkaMessageListenerContainer` con. Mỗi container con tạo một Kafka consumer. Khi Spring Kafka tạo các consumer con, nó sử dụng client ID nền và thêm suffix để chúng có thể được nhận diện riêng.

Giả sử listener có concurrency bằng ba và prefix là `billing-consumer`:

~~~text
ConcurrentMessageListenerContainer
    |
    +-- Child container 0
    |      +-- KafkaConsumer
    |      +-- client.id = billing-consumer-0
    |
    +-- Child container 1
    |      +-- KafkaConsumer
    |      +-- client.id = billing-consumer-1
    |
    +-- Child container 2
           +-- KafkaConsumer
           +-- client.id = billing-consumer-2
~~~

Thông thường, chỉ số suffix bắt đầu từ 0 và tăng theo child container. Đây là chỉ số nhận diện consumer trong concurrent container, không phải số thứ tự partition.

### 3.1. Khi concurrency bằng một

Mặc định, suffix thường được thêm khi concurrency lớn hơn một. Với concurrency bằng một, client ID có thể dùng prefix mà không có suffix.

Spring Kafka cung cấp tùy chọn `alwaysClientIdSuffix` trên `ConcurrentMessageListenerContainer`. Khi bật tùy chọn này, container luôn thêm suffix, kể cả khi concurrency bằng một. Kết quả khi đó có dạng:

~~~text
billing-consumer-0
~~~

Điều này hữu ích khi muốn mọi listener tuân theo một quy tắc đặt tên thống nhất, hoặc khi có nhiều container với cùng prefix cần phân biệt trong metric.

Tùy chọn này là thiết lập của Spring Kafka container, không phải Kafka consumer property `client.id` tiêu chuẩn. Hãy kiểm tra API của phiên bản Spring Kafka ứng dụng đang dùng khi cấu hình nó.

## 4. Đặt clientIdPrefix trên @KafkaListener

Với listener được khai báo bằng annotation, cách thông dụng là đặt `clientIdPrefix`:

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
        concurrency = "3",
        clientIdPrefix = "orders-fulfillment"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.process(event);
    }
}
~~~

Với concurrency bằng ba, các consumer con sẽ có client ID riêng dựa trên prefix. Ví dụ:

~~~text
orders-fulfillment-0
orders-fulfillment-1
orders-fulfillment-2
~~~

`id` của listener là ID endpoint Spring Kafka, còn `clientIdPrefix` tạo tên cho Kafka consumer client. Hai giá trị có thể giống nhau nhưng không có cùng vai trò.

### 4.1. Dùng placeholder theo môi trường

Có thể đưa tên ứng dụng hoặc instance vào prefix để client ID dễ nhận diện:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "${orders.consumer.concurrency:3}",
    clientIdPrefix = "${spring.application.name:orders}-${INSTANCE_ID:local}"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: order-service

orders:
  consumer:
    concurrency: 3
~~~

Nếu biến môi trường `INSTANCE_ID` của pod là `pod-a7`, các client ID có thể là:

~~~text
order-service-pod-a7-0
order-service-pod-a7-1
order-service-pod-a7-2
~~~

Placeholder cần được Spring resolve trong môi trường chạy. Nếu ứng dụng không cung cấp `INSTANCE_ID`, giá trị mặc định `local` được dùng trong ví dụ. Với deployment nhiều replica, nên cung cấp định danh instance thực tế để tránh các pod tạo ra cùng một tập client ID.

## 5. Cấu hình trên ConcurrentMessageListenerContainer

Khi tự tạo concurrent container thay vì dùng `@KafkaListener`, có thể đặt concurrency và tùy chọn suffix trực tiếp trên container:

~~~java
ContainerProperties containerProperties =
    new ContainerProperties("orders.created");

containerProperties.setGroupId("order-fulfillment");
containerProperties.setClientId("orders-fulfillment");

ConcurrentMessageListenerContainer<String, OrderCreated> container =
    new ConcurrentMessageListenerContainer<>(
        consumerFactory,
        containerProperties
    );

container.setConcurrency(3);
container.setAlwaysClientIdSuffix(true);
~~~

Đoạn mã tập trung vào phần cấu hình container. Ứng dụng còn phải thiết lập message listener, deserializer, lifecycle và các thuộc tính bảo mật phù hợp trước khi start container.

Nếu dùng `ConcurrentKafkaListenerContainerFactory`, có thể áp dụng tùy chọn cho container được factory tạo ra bằng container customizer ở các phiên bản Spring Kafka hỗ trợ API này:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.setContainerCustomizer(container ->
        container.setAlwaysClientIdSuffix(true)
    );

    return factory;
}
~~~

Nếu phiên bản thư viện chưa có container customizer, có thể cấu hình trực tiếp container sau khi tạo hoặc nâng cấp theo kế hoạch dependency của ứng dụng. Không nên giả định một property YAML tên `client-id-suffix` tồn tại trong mọi phiên bản; suffix thường được điều khiển qua API của concurrent container.

## 6. Suffix và nhiều application instance

Một điểm dễ bị bỏ sót là suffix thường chỉ phân biệt các consumer con bên trong một concurrent container. Nó không tự đảm bảo client ID duy nhất trên toàn bộ deployment.

Ví dụ có hai pod cùng chạy:

- concurrency = 2
- clientIdPrefix = `orders-fulfillment`

Khi đó mỗi pod có thể tạo:

~~~text
Pod A:
  orders-fulfillment-0
  orders-fulfillment-1

Pod B:
  orders-fulfillment-0
  orders-fulfillment-1
~~~

Các consumer vẫn có thể hoạt động bình thường trong cùng group; client ID không phải khóa membership của group. Tuy nhiên, dashboard hoặc hệ thống metrics tập trung có thể gộp dữ liệu của các client trùng tên, khiến việc điều tra từng pod khó hơn.

Giải pháp là đưa định danh instance vào prefix:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "2",
    clientIdPrefix = "orders-${POD_NAME:local}"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Kết quả minh họa:

~~~text
Pod A:
  orders-pod-a-0
  orders-pod-a-1

Pod B:
  orders-pod-b-0
  orders-pod-b-1
~~~

Có thể dùng pod name, hostname hoặc một instance ID được deployment cấp. Prefix nên ổn định đủ để theo dõi một instance trong thời gian nó chạy, nhưng phải khác nhau giữa các replica nếu cần phân biệt chúng trong telemetry.

Không cần đưa các giá trị có độ biến thiên cao như event ID, order ID hoặc request ID vào client ID. Những giá trị đó thuộc log/trace của từng event, không phải danh tính của Kafka consumer.

## 7. client.id được dùng ở đâu?

Kafka client gửi `client.id` trong request để broker và các công cụ vận hành có thể nhận diện nguồn request. Nó thường xuất hiện trong:

- Log broker khi điều tra request hoặc lỗi kết nối.
- Kafka client metrics và JMX metrics.
- Metric labels do exporter hoặc Micrometer tích hợp tạo ra.
- Công cụ quan sát consumer group, tùy công cụ có hiển thị client ID hay không.
- Log ứng dụng khi bật log consumer/client phù hợp.

Khi client ID có suffix, người vận hành có thể so sánh các consumer con:

| Client ID | Dữ liệu cần xem |
|---|---|
| `orders-fulfillment-0` | Request rate, fetch latency, assigned partitions và processing rate |
| `orders-fulfillment-1` | Lag, retry, rebalance và thời gian xử lý |
| `orders-fulfillment-2` | Consumer errors, throughput và resource usage |

Nếu một consumer có fetch rate thấp và lag cao trong khi các consumer khác ổn định, có thể kiểm tra assignment, hot partition hoặc lỗi riêng của instance đó. Client ID giúp định vị consumer để điều tra; nó không tự cung cấp nguyên nhân.

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Hãy kiểm tra metric thực tế đang được export trước khi viết dashboard hoặc alert rule.

## 8. Suffix không ảnh hưởng group membership và partition assignment

Kafka sử dụng `group.id` để xác định consumer group. Group coordinator quản lý member, generation và partition assignment. `client.id` chủ yếu dùng cho nhận diện request và telemetry.

Các thành phần cần phân biệt:

| Thành phần | Tác động chính |
|---|---|
| `client.id` | Nhận diện Kafka client trong request, log và metrics |
| `group.id` | Xác định consumer group và phạm vi chia partition |
| `group.instance.id` | Định danh static member khi dùng static membership |
| `member.id` | Định danh thành viên group do Kafka quản lý |
| Partition assignor | Quyết định cách partition được phân phối giữa các consumer |

Đổi suffix không làm consumer chuyển sang group khác, không tạo partition mới và không thay đổi key partitioning của producer. Nếu thay đổi `group.id`, hành vi tiêu thụ mới có thể hoàn toàn khác; nếu chỉ đổi client ID, mục tiêu chủ yếu là nhận diện client.

### 8.1. Không dùng suffix làm static member ID

Static membership dùng `group.instance.id` để giảm rebalance trong một số tình huống restart tạm thời. Đây là một định danh thành viên group cần tuân thủ quy tắc duy nhất trong group.

`clientIdSuffix` không thay thế `group.instance.id`. Không dùng client ID làm static membership identity trừ khi ứng dụng chủ động cấu hình đúng property group.instance.id theo quy tắc của Kafka. Đặc biệt, nhiều consumer trong cùng group không thể dùng chung một static member ID.

## 9. Tương tác với concurrency và partition

Giả sử topic `orders.created` có sáu partition và một listener chạy concurrency bằng ba:

~~~text
Topic:
  P0  P1  P2  P3  P4  P5

Consumer clients:
  orders-fulfillment-0
  orders-fulfillment-1
  orders-fulfillment-2
~~~

Kafka có thể gán hai partition cho mỗi consumer trong một assignment cân bằng. Nhưng suffix không nói consumer nào sở hữu P0 hay P1. Partition assignment có thể thay đổi sau rebalance trong khi suffix vẫn gắn với child container tương ứng.

Nếu topic chỉ có hai partition nhưng concurrency bằng bốn, vẫn có thể có bốn consumer con và bốn client ID, nhưng tối đa hai consumer nhận partition tại một thời điểm. Hai consumer còn lại không đọc record cho topic đó. Việc có suffix không có nghĩa consumer đang xử lý dữ liệu.

Vì vậy, khi điều tra lag hoặc throughput, hãy kết hợp client ID với partition assignment. Không suy luận assignment chỉ từ hậu tố.

## 10. Tương tác với nhiều listener trong cùng ứng dụng

Một ứng dụng có thể có nhiều listener container, mỗi container có prefix riêng:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders"
)
public void consumeOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
    id = "audit-listener",
    topics = "orders.audit",
    groupId = "audit-indexer",
    concurrency = "2",
    clientIdPrefix = "audit"
)
public void consumeAudit(OrderAudit event) {
    auditService.index(event);
}
~~~

Các client ID có thể là:

~~~text
orders-0
orders-1
orders-2

audit-0
audit-1
~~~

Prefix riêng giúp lọc metric theo endpoint. Nếu hai listener dùng cùng prefix và cùng suffix index, client ID có thể trùng. Hãy chọn prefix có ý nghĩa và duy nhất trong phạm vi ứng dụng, sau đó thêm instance ID nếu cần phân biệt nhiều pod.

## 11. Chẩn đoán sự cố bằng clientIdSuffix

Suffix có ích khi một consumer con hoạt động khác thường so với các consumer khác. Ví dụ:

| Triệu chứng | Cách dùng client ID để điều tra |
|---|---|
| Một consumer lag cao | Xác định client ID, xem partition assignment và throughput của consumer đó |
| Fetch rate thấp trên một consumer | Kiểm tra partition được gán, broker leader và client metrics |
| Một consumer thường xuyên lỗi | Lọc log theo client ID và so sánh với consumer cùng listener |
| Metric bị gộp giữa các pod | Kiểm tra prefix có chứa instance ID chưa |
| Nhiều client ID trùng nhau | Kiểm tra các listener có dùng cùng clientIdPrefix và concurrency index không |
| Consumer ID thay đổi sau deployment | Kiểm tra cách tạo prefix và instance identity của pod |

Khi một client ID không xuất hiện trong metrics, cần kiểm tra consumer có được tạo và khởi động thành công hay không, có nhận partition hay không, và exporter có thu thập metric theo client ID đó hay không. Không có metric không nhất thiết nghĩa là consumer bị lỗi.

### 11.1. Log nên có thông tin gì?

Log ứng dụng hữu ích nên chứa listener ID, group ID, client ID hoặc instance ID khi có thể lấy được, cùng topic/partition/offset của record đang xử lý.

Ví dụ log có cấu trúc:

~~~text
listener=orders-listener
groupId=order-fulfillment
clientId=orders-pod-a-1
topic=orders.created
partition=3
offset=12840
eventId=evt-92
result=processed
~~~

Các trường này giúp nối log xử lý event với metric của consumer. Tránh dùng event ID hoặc order ID làm label metric vì cardinality có thể tăng rất lớn; các ID đó phù hợp hơn trong log hoặc trace.

## 12. Những nhầm lẫn thường gặp

**Cho rằng suffix là partition ID.** Suffix nhận diện child consumer, còn partition assignment do Kafka group coordinator và assignor quản lý.

**Cho rằng suffix làm consumer thuộc group riêng.** Group membership dựa trên group.id và cơ chế coordinator, không dựa trên client.id.

**Cho rằng suffix duy nhất trên toàn deployment.** Suffix thường chỉ phân biệt consumer con trong một container. Nhiều pod có cùng prefix có thể tạo tên trùng.

**Cho rằng client ID quyết định thứ tự event.** Thứ tự phụ thuộc partition và cách ứng dụng xử lý record. Đổi client ID không thay đổi thứ tự trong log.

**Dùng clientIdSuffix như group.instance.id.** Đây là hai khái niệm riêng. Static membership cần group.instance.id duy nhất và ổn định theo member.

**Đưa ID của từng event vào client ID.** Client ID đại diện cho consumer process, không phải message. Dùng ID động sẽ làm telemetry khó quản lý.

**Không đặt prefix cho các listener khác nhau.** Nhiều listener có thể tạo client ID trùng nếu dùng cùng prefix và suffix index.

**Giả định concurrency bằng một luôn có suffix.** Mặc định suffix thường chỉ được thêm khi concurrency lớn hơn một. Bật alwaysClientIdSuffix nếu cần suffix ngay cả với một consumer.

## 13. Quy trình cấu hình và vận hành

1. Xác định listener endpoint và số consumer con cần chạy.
2. Đặt `clientIdPrefix` có ý nghĩa cho từng listener.
3. Dùng suffix mặc định để phân biệt consumer con khi concurrency lớn hơn một.
4. Nếu cần suffix khi concurrency bằng một, cấu hình `alwaysClientIdSuffix` trên concurrent container.
5. Nếu có nhiều pod, thêm pod/instance ID vào prefix để tránh trùng tên trong telemetry.
6. Giữ `group.id` và `group.instance.id` theo đúng mục đích riêng; không dùng suffix thay thế chúng.
7. Xác nhận client ID thực tế trong log hoặc metrics sau khi container khởi động.
8. Tạo dashboard có thể lọc theo listener, client ID, group ID, topic và partition.
9. Khi điều tra lag, luôn xem partition assignment cùng client ID.
10. Ghi lại quy ước đặt tên trong runbook để mọi môi trường dùng thống nhất.

## 14. Ví dụ tổng hợp: Order Fulfillment

Một ứng dụng Order Fulfillment có topic `orders.created` với 12 partition. Mỗi pod chạy listener concurrency bằng ba. Deployment có ba pod và tất cả consumer dùng group ID `order-fulfillment`.

Cấu hình listener:

~~~java
@KafkaListener(
    id = "orders-fulfillment-listener",
    topics = "orders.created",
    groupId = "order-fulfillment",
    concurrency = "3",
    clientIdPrefix = "orders-${POD_NAME:local}"
)
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

Giả sử ba pod có tên `orders-a`, `orders-b` và `orders-c`. Các client ID sẽ có dạng:

~~~text
orders-orders-a-0
orders-orders-a-1
orders-orders-a-2

orders-orders-b-0
orders-orders-b-1
orders-orders-b-2

orders-orders-c-0
orders-orders-c-1
orders-orders-c-2
~~~

Tổng số consumer được tạo là:

`3 pods × 3 consumers = 9 consumers`

Với 12 partition, Kafka có thể phân phối partition cho chín consumer. Một consumer có thể nhận một hoặc hai partition tùy assignment.

Nếu dashboard cho thấy `orders-orders-b-1` có lag tăng, đội vận hành có thể xác định đúng consumer và xem partition đang được gán, fetch rate, processing duration và downstream latency. Nếu consumer đó không có partition, lag không thể được giải thích bằng việc nó xử lý chậm; cần kiểm tra assignment và consumer khác đang sở hữu partition bị lag.

Nếu deployment tăng lên năm pod mà prefix không chứa pod name, các pod có thể tạo client ID giống nhau như `orders-0`, `orders-1`, `orders-2`. Điều này làm dashboard khó phân biệt instance. Thêm instance ID vào prefix giúp giữ telemetry riêng cho từng pod.

## 15. Ghi nhớ

`clientIdSuffix` là hậu tố Spring Kafka dùng để phân biệt client ID của các consumer con trong `ConcurrentMessageListenerContainer`. Khi concurrency lớn hơn một, Spring Kafka thường thêm suffix như `-0`, `-1`, `-2` vào client ID prefix.

Suffix hỗ trợ quan sát consumer trong log và metrics. Nó không quyết định group membership, partition assignment, thứ tự event hoặc static membership. Khi chạy nhiều pod, hãy thêm instance ID vào `clientIdPrefix` nếu cần client ID duy nhất trong hệ thống giám sát. Nếu cần suffix ngay cả khi concurrency bằng một, dùng `alwaysClientIdSuffix` trên concurrent container theo API của phiên bản Spring Kafka đang chạy.

