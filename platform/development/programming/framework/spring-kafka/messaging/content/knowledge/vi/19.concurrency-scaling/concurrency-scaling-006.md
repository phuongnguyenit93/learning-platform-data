# client.id khi dùng concurrency

Trong Spring Kafka, một listener container có thể chạy nhiều consumer đồng thời thông qua thuộc tính concurrency. Mỗi consumer là một Kafka client riêng và cần một client ID đủ rõ để quan sát log, metrics và hoạt động của từng consumer. Spring Kafka cho phép đặt tiền tố client ID rồi tự thêm hậu tố cho từng consumer con.

Ví dụ listener có concurrency bằng ba và tiền tố orders-listener có thể tạo ra ba consumer:

~~~text
orders-listener-0
orders-listener-1
orders-listener-2
~~~

client.id giúp nhận diện một Kafka client trong log, metrics và cơ chế quota. Nó không xác định consumer group, không quyết định partition được assign và không lưu offset. Các trách nhiệm đó thuộc về group.id và cơ chế consumer group của Kafka.

Bài học tập trung vào cách Spring Kafka tạo client ID khi dùng concurrency, cách cấu hình bằng ConsumerFactory, ContainerProperties và @KafkaListener, cách đặt tên khi ứng dụng chạy nhiều replica, cùng cách dùng client ID để quan sát từng consumer.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của client.id trong Kafka consumer.
- Phân biệt client.id, group.id và id của @KafkaListener.
- Mô tả cách ConcurrentMessageListenerContainer tạo consumer con.
- Giải thích hậu tố -n được Spring Kafka thêm vào client ID.
- Cấu hình client ID qua ConsumerFactory, ContainerProperties và clientIdPrefix.
- Hiểu thứ tự ưu tiên khi cấu hình client ID.
- Thiết kế client ID khi chạy nhiều replica hoặc trên Kubernetes.
- Quan sát metrics và partition assignment theo client ID.
- Nhận biết lỗi trùng client ID, đặt tên khó truy vết và hiểu sai tác dụng của concurrency.

## 1. client.id là gì?

client.id là thuộc tính cấu hình của Kafka client. Consumer gửi giá trị này trong các request đến broker để broker có thể nhận diện client đang thực hiện request.

client.id thường được dùng cho:

- Gắn nhãn metrics của Kafka consumer.
- Phân biệt request và log của các client.
- Áp dụng client quota theo cấu hình broker.
- Đặt tên JMX MBean và tránh trùng tên giữa các consumer trong cùng JVM.
- Hỗ trợ vận hành khi cần xác định consumer instance nào đang chậm hoặc có lỗi.

Ví dụ:

~~~properties
bootstrap.servers=localhost:9092
group.id=order-service
client.id=orders-listener
~~~

Trong ví dụ, consumer thuộc group order-service và có client ID orders-listener. Đây là hai định danh khác nhau, phục vụ hai mục đích khác nhau.

### client.id không thay thế group.id

| Thuộc tính | Mục đích | Ảnh hưởng chính |
|---|---|---|
| client.id | Nhận diện Kafka client | Metrics, log, client quota và JMX |
| group.id | Nhận diện consumer group | Membership, partition assignment và committed offset |
| @KafkaListener id | Định danh listener endpoint trong Spring | Quản lý container qua KafkaListenerEndpointRegistry; có thể làm group ID nếu idIsGroup bật |
| clientIdPrefix | Tiền tố client.id do Spring Kafka áp dụng cho listener | Tạo tên client ID cho consumer con |

Ví dụ hai consumer có cùng group.id nhưng client.id khác nhau vẫn thuộc cùng consumer group:

~~~text
group.id = order-service

Consumer A:
  client.id = orders-listener-0

Consumer B:
  client.id = orders-listener-1
~~~

Kafka phân phối partition giữa hai consumer dựa trên group membership và subscription. client.id không quyết định consumer nào nhận partition nào.

Ngược lại, hai consumer có client.id giống nhau nhưng group.id khác nhau vẫn thuộc hai consumer group độc lập. Tuy nhiên, dùng client ID trùng nhau có thể làm metrics khó phân biệt và khiến quota theo client ID được áp dụng chung.

Kafka không yêu cầu client.id phải duy nhất trên toàn cluster. Việc dùng cùng giá trị ở nhiều tiến trình không làm các consumer nhập chung group. Tuy vậy, metrics và quota theo client ID có thể được tổng hợp theo cùng tên; trong cùng JVM, tên JMX MBean cũng cần được phân biệt.

## 2. Vì sao concurrency tạo nhiều client ID?

Khi dùng ConcurrentKafkaListenerContainer, Spring Kafka quản lý nhiều KafkaMessageListenerContainer con. Mỗi container con sở hữu một KafkaConsumer riêng và chạy trên consumer thread riêng.

Ví dụ cấu hình:

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

Nếu listener subscribe topic orders và concurrency bằng ba, Spring Kafka tạo tối đa ba consumer con:

Sơ đồ dưới đây giả sử listener đã được cấu hình tiền tố client ID là orders-listener.

~~~mermaid
flowchart TD
    A["@KafkaListener orders"] --> B["ConcurrentMessageListenerContainer"]
    B --> C["Child container 0"]
    B --> D["Child container 1"]
    B --> E["Child container 2"]
    C --> F["KafkaConsumer: orders-listener-0"]
    D --> G["KafkaConsumer: orders-listener-1"]
    E --> H["KafkaConsumer: orders-listener-2"]
    F --> I["Kafka broker"]
    G --> I
    H --> I
~~~

Mỗi consumer con cần client ID riêng để metrics và JMX có thể phân biệt chúng. Spring Kafka thêm hậu tố dạng -n vào tiền tố client ID.

Ví dụ:

~~~text
clientIdPrefix = orders-listener
concurrency    = 3

Consumer con 0 -> orders-listener-0
Consumer con 1 -> orders-listener-1
Consumer con 2 -> orders-listener-2
~~~

Hậu tố được đánh số từ 0. Khi concurrency lớn hơn 1, hậu tố giúp các consumer con trong cùng listener container có tên khác nhau.

Concurrency là số consumer con mà container quản lý. Số consumer thực sự nhận partition còn phụ thuộc số partition được subscribe hoặc assign và số consumer member trong group.

## 3. Cách Spring Kafka tạo client ID

Spring Kafka hỗ trợ đặt client ID thông qua tiền tố. Với concurrent container, tiền tố được nối thêm hậu tố tương ứng với chỉ số consumer con.

Có ba nơi thường cấu hình:

1. ConsumerConfig.CLIENT_ID_CONFIG trong ConsumerFactory.
2. ContainerProperties.clientId trên listener container factory.
3. clientIdPrefix trong @KafkaListener.

Trong đó, cấu hình ở container hoặc annotation có thể ghi đè client.id trong ConsumerFactory.

### Ví dụ khi chỉ cấu hình ConsumerFactory

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
    );
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    props.put(
            ConsumerConfig.CLIENT_ID_CONFIG,
            "orders-consumer"
    );

    return new DefaultKafkaConsumerFactory<>(
            props,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class)
    );
}
~~~

Nếu listener container dùng concurrency bằng ba, các consumer con có thể nhận client ID:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2
~~~

Đây là cách đặt một tiền tố chung ở cấp ConsumerFactory. Nếu nhiều listener cùng dùng factory này, các listener có thể cùng dùng một tiền tố. Khi đó, nên cân nhắc đặt tiền tố riêng ở cấp listener để dễ quan sát.

## 4. Cấu hình bằng ContainerProperties.clientId

Với custom container factory, có thể đặt tiền tố client ID trên ContainerProperties:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    factory.getContainerProperties().setClientId("orders-worker");

    return factory;
}
~~~

Khi factory tạo concurrent container, tiền tố orders-worker được dùng để tạo client ID cho các consumer con:

~~~text
orders-worker-0
orders-worker-1
orders-worker-2
~~~

ContainerProperties.clientId là tiền tố và ghi đè giá trị client.id lấy từ ConsumerFactory. Cách này hữu ích khi một factory chỉ phục vụ một nhóm listener có cùng mục đích vận hành.

Nếu nhiều listener cần các tên riêng biệt, clientIdPrefix trên từng @KafkaListener thường linh hoạt hơn.

## 5. Cấu hình bằng clientIdPrefix trên @KafkaListener

@KafkaListener cung cấp thuộc tính clientIdPrefix để đặt tiền tố client ID riêng cho listener endpoint.

Ví dụ:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        clientIdPrefix = "orders-consumer",
        concurrency = "3"
    )
    public void listen(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Các client ID được tạo:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2
~~~

clientIdPrefix ghi đè tiền tố client ID trong ConsumerFactory hoặc ContainerProperties được dùng làm cấu hình nền cho endpoint này.

Đây thường là cách dễ đọc khi một ứng dụng có nhiều listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "orders-consumer",
    concurrency = "3"
)
public void listenOrder(OrderEvent event) {
    orderService.process(event);
}

@KafkaListener(
    id = "payments-listener",
    topics = "payments",
    groupId = "payment-service",
    clientIdPrefix = "payments-consumer",
    concurrency = "2"
)
public void listenPayment(PaymentEvent event) {
    paymentService.process(event);
}
~~~

Tên client ID:

~~~text
orders-consumer-0
orders-consumer-1
orders-consumer-2

payments-consumer-0
payments-consumer-1
~~~

Nhờ đó, metrics và log có thể phân biệt consumer của từng listener.

clientIdPrefix được hỗ trợ từ Spring Kafka 2.1.1. Với các phiên bản cũ hơn, cần kiểm tra API và cách cấu hình tương ứng.

## 6. Placeholder và SpEL trong clientIdPrefix

clientIdPrefix hỗ trợ property placeholder và SpEL. Điều này cho phép thay đổi tiền tố theo profile hoặc môi trường chạy.

Cấu hình:

~~~yaml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: orders-consumer
        concurrency: 3
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "${app.kafka.listeners.orders.client-id-prefix}",
    concurrency = "${app.kafka.listeners.orders.concurrency:3}"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Mỗi môi trường có thể dùng tiền tố riêng:

~~~yaml
# application-dev.yml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: dev-orders
~~~

~~~yaml
# application-prod.yml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: prod-orders
~~~

Trong production, client ID sẽ có dạng:

~~~text
prod-orders-0
prod-orders-1
prod-orders-2
~~~

Có thể dùng SpEL khi cần lấy tiền tố từ bean cấu hình:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "#{@kafkaClientSettings.ordersClientIdPrefix}",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Chỉ nên dùng biểu thức khi có nhu cầu thực tế. Với cấu hình thông thường, property placeholder giúp việc quản lý profile và triển khai đơn giản hơn.

## 7. client.id khi chạy nhiều replica

Concurrency chỉ tạo các consumer con trong một instance ứng dụng. Khi triển khai nhiều replica, mỗi replica lại tạo một nhóm consumer con.

Ví dụ:

- Ứng dụng có hai replica.
- Mỗi replica có concurrency bằng ba.
- Cả hai replica dùng cùng group.id là order-service.
- Mỗi replica có một clientIdPrefix riêng.

Kết quả:

~~~text
Replica A:
  clientIdPrefix = orders-pod-a

  orders-pod-a-0
  orders-pod-a-1
  orders-pod-a-2

Replica B:
  clientIdPrefix = orders-pod-b

  orders-pod-b-0
  orders-pod-b-1
  orders-pod-b-2
~~~

Tổng cộng có sáu consumer member trong group order-service. Kafka phân phối partition giữa các member dựa trên group assignment.

### Đặt tiền tố theo instance

Có thể đưa tên instance vào cấu hình:

~~~yaml
app:
  kafka:
    listeners:
      orders:
        client-id-prefix: orders-${HOSTNAME:local}
~~~

Annotation:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    clientIdPrefix = "${app.kafka.listeners.orders.client-id-prefix}",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Nếu môi trường cung cấp HOSTNAME khác nhau cho mỗi instance, client ID sẽ có dạng:

~~~text
orders-pod-a-0
orders-pod-a-1
orders-pod-a-2

orders-pod-b-0
orders-pod-b-1
orders-pod-b-2
~~~

Trong Kubernetes, có thể sử dụng Pod name qua biến môi trường được khai báo bằng Downward API. Không nên giả định mọi môi trường đều cung cấp cùng một tên biến; hãy xác nhận cấu hình deployment.

### Khi nào cần client ID riêng theo replica?

Nên đặt tiền tố riêng theo instance khi:

- Cần phân biệt consumer của từng pod trong dashboard.
- Cần truy vết consumer đang có latency hoặc lỗi.
- Cần phân tích partition assignment theo từng instance.
- Cần áp dụng quota riêng cho từng nhóm client.
- Cần đối chiếu log của một replica với metrics Kafka.

Nếu muốn broker áp dụng quota chung cho toàn service, có thể chủ động dùng một tiền tố chung và cấu hình quota theo pattern phù hợp. Nếu muốn quota tách theo instance, cần thiết kế tên client ID và quota tương ứng.

## 8. client.id và số partition

client.id không tạo thêm partition và cũng không làm tăng số consumer có thể nhận dữ liệu. Nó chỉ nhận diện từng Kafka client.

Ví dụ topic orders có bốn partition:

~~~text
Topic orders:
P0  P1  P2  P3

Ứng dụng:
  2 replica x concurrency 3 = 6 consumer

Consumer có client ID:
  pod-a-0
  pod-a-1
  pod-a-2
  pod-b-0
  pod-b-1
  pod-b-2
~~~

Trong cùng một consumer group, tối đa bốn consumer có thể nhận partition của topic này tại một thời điểm. Hai consumer còn lại có thể không được gán partition.

Tên client ID vẫn được tạo cho các consumer đó, nhưng chúng không làm tăng throughput khi topic chỉ có bốn partition.

| Partition | Tổng consumer | Consumer có thể nhận partition |
|---:|---:|---:|
| 4 | 2 | 2 |
| 4 | 4 | 4 |
| 4 | 6 | Tối đa 4 |
| 12 | 6 | Tối đa 6 |

Hãy chọn concurrency dựa trên partition count và năng lực downstream. Đặt client ID tốt giúp quan sát consumer, nhưng không thay đổi giới hạn song song của Kafka.

## 9. Hậu tố client ID và alwaysClientIdSuffix

Spring Kafka thêm hậu tố -n cho consumer con trong concurrent container. Mặc định, thuộc tính alwaysClientIdSuffix là true. Vì vậy, ngay cả khi concurrency bằng một, client ID vẫn có thể có hậu tố -0.

Ví dụ:

~~~text
clientIdPrefix = orders-consumer
concurrency = 1

client.id = orders-consumer-0
~~~

Từ Spring Kafka 2.2.14, ConcurrentMessageListenerContainer có phương thức setAlwaysClientIdSuffix(false) để bỏ hậu tố khi concurrency chỉ bằng một.

Ví dụ với container được tạo và quản lý trực tiếp:

~~~java
ConcurrentMessageListenerContainer<String, OrderEvent> container =
        factory.createContainer("orders");

container.setAlwaysClientIdSuffix(false);
container.start();
~~~

Khi đó, nếu concurrency là một, client ID có thể giữ nguyên tiền tố orders-consumer mà không thêm -0.

Thiết lập này chỉ bỏ suffix khi concurrency bằng một. Khi concurrency lớn hơn một, suffix vẫn cần thiết để phân biệt consumer con.

Với listener được tạo tự động từ @KafkaListener, không nên giả định có thuộc tính annotation tương ứng để tắt suffix. Nếu thực sự cần thay đổi hành vi này, hãy quản lý container theo cách phù hợp với phiên bản Spring Kafka và kiểm thử trước khi triển khai.

Thông thường, giữ suffix mặc định giúp tên consumer nhất quán khi concurrency thay đổi giữa các môi trường.

## 10. Quan sát metrics theo client.id

Kafka consumer cung cấp metrics theo client ID. Khi dùng ConcurrentMessageListenerContainer, Spring Kafka tổng hợp metrics của các consumer con và nhóm theo client ID.

Ví dụ:

~~~text
orders-consumer-0
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg

orders-consumer-1
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg

orders-consumer-2
  records-consumed-rate
  bytes-consumed-rate
  records-lag-max
  fetch-latency-avg
~~~

Khi metrics được gắn client ID riêng, có thể nhận diện consumer nào có throughput thấp hoặc lag cao hơn các consumer khác.

Một số metrics thường được quan sát:

| Metric | Ý nghĩa |
|---|---|
| records-consumed-rate | Tốc độ consumer đọc record |
| bytes-consumed-rate | Tốc độ dữ liệu consumer nhận |
| fetch-latency-avg | Độ trễ fetch trung bình |
| fetch-rate | Tần suất fetch request |
| records-lag-max | Lag lớn nhất được ghi nhận theo metric tương ứng |
| commit-latency-avg | Độ trễ commit offset trung bình |

Tên metric và cách tag có thể thay đổi theo Kafka client version, Micrometer và hệ thống monitoring. Hãy kiểm tra metrics thực tế được exporter công bố.

### Lấy metrics từ listener container

Có thể lấy container qua KafkaListenerEndpointRegistry:

~~~java
@Component
public class KafkaConsumerMetricsInspector {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaConsumerMetricsInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void inspectOrdersListener() {
        MessageListenerContainer listenerContainer =
                registry.getListenerContainer("orders-listener");

        if (listenerContainer instanceof
                ConcurrentMessageListenerContainer<?, ?> concurrent) {

            Map<String, Map<MetricName, ? extends Metric>> metrics =
                    concurrent.metrics();

            metrics.forEach((clientId, clientMetrics) -> {
                log.info(
                    "Kafka consumer client.id={}, metricCount={}",
                    clientId,
                    clientMetrics.size()
                );
            });
        }
    }
}
~~~

metrics() của concurrent container trả về metrics được nhóm theo client ID. Cấu trúc này giúp ứng dụng quan sát từng consumer con mà không phải truy cập trực tiếp vào KafkaConsumer từ thread nghiệp vụ.

Không gọi các thao tác consumer không thread-safe từ thread giám sát. Hãy dùng API metrics mà container cung cấp hoặc exporter được tích hợp.

## 11. Xem partition assignment theo client ID

Ngoài metrics, Spring Kafka còn cung cấp thông tin partition assignment theo client ID trong concurrent container.

Ví dụ minh họa:

~~~text
client.id             Assigned partitions
------------------------------------------------
orders-consumer-0    orders-0, orders-1
orders-consumer-1    orders-2
orders-consumer-2    orders-3
~~~

Thông tin này hữu ích khi:

- Một consumer có lag cao bất thường.
- Partition bị dồn vào một consumer.
- Thay đổi concurrency hoặc số replica.
- Điều tra rebalance và assignment.
- Xác nhận consumer nào đang xử lý partition cần kiểm tra.

Trong các phiên bản Spring Kafka có API tương ứng, có thể sử dụng getAssignmentsByClientId() hoặc thuộc tính assignment theo client ID của concurrent container.

Không nên dựa vào một sơ đồ assignment cố định. Kết quả phụ thuộc partition assignor, số member đang hoạt động, subscription và thời điểm rebalance.

## 12. client.id và JMX

Kafka client có thể xuất metrics qua JMX. Tên MBean thường chứa client ID để phân biệt các client.

Khi một concurrent container tạo nhiều consumer, các hậu tố riêng giúp tránh trùng tên MBean giữa các consumer con.

Ví dụ:

~~~text
kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-0

kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-1

kafka.consumer:type=consumer-fetch-manager-metrics,
client-id=orders-consumer-2
~~~

Nếu các consumer trong cùng JVM dùng cùng client ID, MBean có thể xung đột hoặc không thể phân biệt theo cách mong muốn. Đây là một lý do Spring Kafka tự thêm suffix khi concurrency được sử dụng.

JMX ObjectName cụ thể phụ thuộc Kafka client version và loại metric. Hãy dùng JConsole, VisualVM hoặc JMX exporter để kiểm tra tên MBean thực tế.

## 13. client.id và client quota

Kafka broker có thể áp dụng quota theo client ID. Ví dụ, broker có thể giới hạn tốc độ dữ liệu hoặc request của các client khớp với một cấu hình quota.

Điều này có nghĩa cách đặt client ID có thể ảnh hưởng đến chính sách vận hành.

Ví dụ:

~~~text
Client IDs:
  orders-pod-a-0
  orders-pod-a-1
  orders-pod-b-0
  orders-pod-b-1
~~~

Nếu quota được cấu hình theo pattern orders-, các consumer trên có thể cùng thuộc một nhóm quota tùy cách broker cấu hình. Nếu quota được cấu hình theo client ID cụ thể, mỗi consumer có thể nhận mức quota riêng.

Cần phân biệt:

- client ID là nhãn nhận diện client.
- quota là chính sách broker áp dụng dựa trên client ID hoặc principal.
- group ID vẫn quyết định consumer group và partition assignment.

Không nên thay đổi client ID tùy tiện trong hệ thống có quota. Một prefix mới có thể khiến client không còn khớp quota hiện tại hoặc vô tình được áp dụng quota khác.

## 14. client.id, id và groupId trong @KafkaListener

Ba tên này dễ gây nhầm lẫn vì đều xuất hiện trong annotation.

~~~java
@KafkaListener(
    id = "orders-listener",
    groupId = "order-service",
    clientIdPrefix = "orders-consumer",
    topics = "orders",
    concurrency = "3"
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

| Thuộc tính | Giá trị ví dụ | Vai trò |
|---|---|---|
| id | orders-listener | Định danh endpoint trong Spring |
| groupId | order-service | Consumer group của Kafka |
| clientIdPrefix | orders-consumer | Tiền tố client ID cho consumer con |
| concurrency | 3 | Số consumer con được container quản lý |

Nếu idIsGroup là true và không khai báo groupId, Spring Kafka có thể dùng id làm group ID. Điều đó không làm id trở thành client ID.

Hãy khai báo groupId rõ ràng khi muốn kiểm soát consumer group độc lập với listener endpoint. Dùng clientIdPrefix riêng để quản lý metrics và log.

## 15. Đặt tên client ID theo quy ước

Một quy ước tên tốt nên thể hiện được service, listener và instance khi cần.

Có thể sử dụng cấu trúc:

~~~text
<service>-<listener>-<instance>-<consumer-index>
~~~

Ví dụ:

~~~text
order-service-orders-pod-a-0
order-service-orders-pod-a-1
order-service-orders-pod-b-0
order-service-orders-pod-b-1
~~~

Vì Spring Kafka tự thêm hậu tố consumer index, chỉ cần cấu hình prefix:

~~~text
order-service-orders-pod-a
~~~

Spring tạo:

~~~text
order-service-orders-pod-a-0
order-service-orders-pod-a-1
~~~

Một số nguyên tắc:

- Dùng tên ngắn, ổn định và dễ tìm trong dashboard.
- Đưa tên service và listener vào prefix.
- Thêm instance ID khi cần phân biệt replica.
- Để Spring Kafka thêm hậu tố consumer con.
- Tránh tự nối thêm index trong prefix vì dễ tạo tên khó hiểu.
- Tránh chứa thông tin nhạy cảm trong client ID.
- Kiểm tra quy tắc quota nếu broker áp dụng quota theo client ID.
- Giữ quy ước nhất quán giữa dev, staging và production.

Không đưa email, token, mật khẩu hoặc dữ liệu cá nhân vào client ID. Đây là metadata vận hành có thể xuất hiện trong log, metrics và broker.

## 16. Ví dụ cấu hình hoàn chỉnh

Ví dụ cấu hình ConsumerFactory:

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ConsumerFactory<String, OrderEvent> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();

        props.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(
                ConsumerConfig.CLIENT_ID_CONFIG,
                "order-service-default"
        );
        return new DefaultKafkaConsumerFactory<>(
                props,
                new StringDeserializer(),
                new JsonDeserializer<>(OrderEvent.class)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> orderConsumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        clientIdPrefix = "${app.kafka.orders.client-id-prefix:orders-consumer}",
        concurrency = "${app.kafka.orders.concurrency:3}",
        containerFactory = "orderListenerFactory"
    )
    public void listen(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Cấu hình:

~~~yaml
app:
  kafka:
    orders:
      client-id-prefix: orders-consumer-${HOSTNAME:local}
      concurrency: 3
~~~

Với HOSTNAME là pod-a, consumer client ID có thể là:

~~~text
orders-consumer-pod-a-0
orders-consumer-pod-a-1
orders-consumer-pod-a-2
~~~

Trong ví dụ này:

- ConsumerFactory cung cấp client.id mặc định.
- clientIdPrefix trên annotation ghi đè tiền tố mặc định cho listener orders.
- concurrency tạo ba consumer con.
- Spring Kafka thêm hậu tố để phân biệt từng consumer.
- groupId xác định consumer group.
- id xác định endpoint Spring.

## 17. Kiểm tra client ID khi ứng dụng khởi động

Khi cấu hình không đúng, log có thể không thể hiện rõ consumer nào được tạo hoặc các consumer có thể dùng cùng một tiền tố ngoài dự kiến.

Có thể kiểm tra qua các cách:

- Bật log cấu hình container trong môi trường cần chẩn đoán.
- Quan sát log của Kafka client khi consumer khởi tạo.
- Đọc metrics của ConcurrentMessageListenerContainer theo client ID.
- Kiểm tra JMX MBean của Kafka consumer.
- Dùng Kafka broker logs và client quota metrics.
- Kiểm tra cấu hình hiệu lực của profile và environment variable.

Spring Kafka có tùy chọn log cấu hình container ở mức INFO thông qua logContainerConfig trên ContainerProperties. Chỉ bật khi cần chẩn đoán vì log cấu hình có thể làm tăng lượng log và cần kiểm tra nội dung trước khi đưa ra môi trường có yêu cầu bảo mật cao.

Không dùng client.id để suy ra partition assignment. Muốn biết partition nào đang thuộc consumer nào, hãy đọc assignment theo client ID hoặc dùng công cụ quản trị consumer group.

## 18. Các lỗi thường gặp

**Dùng client.id như group.id.** client ID không điều khiển membership hoặc offset. Cấu hình groupId riêng cho consumer group.

**Đặt client.id giống nhau cho mọi listener.** Metrics và log khó phân biệt, quota có thể bị áp dụng chung. Đặt prefix theo listener.

**Quên suffix khi dùng concurrency.** Spring Kafka tự thêm hậu tố cho consumer con. Không tự nối index vào prefix.

**Dùng clientIdPrefix và nghĩ nó đổi group.** Prefix chỉ ảnh hưởng client ID. groupId vẫn cần được cấu hình riêng.

**Dùng cùng prefix cho nhiều replica nhưng kỳ vọng tên duy nhất toàn cluster.** Suffix chỉ phân biệt consumer con trong container. Thêm instance ID nếu cần nhận diện từng replica.

**Tăng concurrency và nghĩ client ID tạo thêm throughput.** client ID chỉ là nhãn nhận diện. Throughput phụ thuộc partition, số consumer có assignment và năng lực xử lý.

**Đặt client ID chứa thông tin nhạy cảm.** client ID có thể xuất hiện trong log và metrics. Chỉ dùng tên vận hành không nhạy cảm.

**Đổi prefix làm quota thay đổi.** Broker có thể áp dụng quota theo client ID. Kiểm tra quota sau khi thay đổi quy ước tên.

**Nhầm id của @KafkaListener với clientIdPrefix.** id định danh endpoint và có thể liên quan group ID theo idIsGroup; clientIdPrefix tạo client ID cho consumer.

**Tắt suffix trong container concurrency lớn hơn một.** Suffix cần thiết để phân biệt consumer con. Chỉ cân nhắc tắt khi concurrency bằng một và có lý do rõ ràng.

## 19. Kiểm thử client.id khi dùng concurrency

Kiểm thử nên xác nhận số consumer, client ID và assignment trong môi trường có Kafka broker.

Các kịch bản hữu ích:

- Tạo listener với concurrency bằng ba và xác nhận có ba consumer client ID khác nhau.
- Đặt clientIdPrefix trong @KafkaListener và xác nhận prefix ghi đè ConsumerFactory client.id.
- Bỏ clientIdPrefix và xác nhận cấu hình client.id nền được dùng.
- Chạy hai listener có prefix khác nhau và xác nhận metrics phân biệt được.
- Chạy hai replica có prefix theo instance và xác nhận client ID không bị trùng ngoài ý muốn.
- Tăng concurrency vượt partition count và xác nhận consumer dư không nhận partition.
- Chạy concurrency bằng một để kiểm tra hậu tố mặc định.
- Nếu quản lý container trực tiếp, kiểm tra setAlwaysClientIdSuffix(false) với concurrency bằng một.
- Kiểm tra metrics được nhóm theo client ID.
- Kiểm tra JMX MBean không xung đột trong cùng JVM khi bật JMX.
- Kiểm tra quota nếu broker có cấu hình theo client ID.
- Restart hoặc scale replica và xác nhận tên client ID mới phản ánh đúng instance.

Khi kiểm thử bằng EmbeddedKafka hoặc Testcontainers, nên chờ consumer assignment hoàn tất trước khi kiểm tra. Không dùng sleep ngắn để kết luận consumer chưa được tạo hoặc chưa nhận partition.

## 20. Checklist cấu hình client.id

- [ ] Đã phân biệt client.id với group.id và @KafkaListener id.
- [ ] Đã xác định listener nào cần client ID riêng.
- [ ] Đã chọn prefix dễ nhận diện service và listener.
- [ ] Đã hiểu Spring Kafka tự thêm hậu tố -n khi dùng concurrency.
- [ ] Đã kiểm tra clientIdPrefix có ghi đè cấu hình ConsumerFactory hay không.
- [ ] Đã tính đến số replica khi cần tên client ID riêng theo instance.
- [ ] Không tự nối consumer index vào prefix.
- [ ] Không đưa dữ liệu nhạy cảm vào client ID.
- [ ] Đã kiểm tra client quota nếu broker áp dụng quota theo client ID.
- [ ] Đã kiểm tra metrics và JMX theo client ID.
- [ ] Đã xác nhận client ID không được dùng thay group ID.
- [ ] Đã kiểm thử concurrency, assignment và scale replica.

## Kết luận

Khi dùng concurrency, Spring Kafka tạo nhiều Kafka consumer con trong một ConcurrentMessageListenerContainer và tự thêm hậu tố -n vào client ID để phân biệt từng consumer. Có thể đặt tiền tố ở ConsumerFactory, ContainerProperties hoặc clientIdPrefix của @KafkaListener; cấu hình ở container hoặc annotation có thể ghi đè client ID nền. Hãy phân biệt client.id với group.id và id của listener, đặt tên theo service/listener/instance khi cần quan sát nhiều replica, rồi dùng metrics và JMX để theo dõi từng consumer. client.id giúp vận hành và chẩn đoán; nó không thay đổi partition assignment, offset hoặc giới hạn throughput của consumer group.

## Tài liệu tham khảo

- [Spring Kafka – Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka – @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Kafka – Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)

