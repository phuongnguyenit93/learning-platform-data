# Số consumer thực tế được tạo

Trong Spring Kafka, một listener không nhất thiết tương ứng với một Kafka consumer duy nhất. Khi bật concurrency, listener container tạo nhiều consumer worker để đọc song song. Khi ứng dụng chạy nhiều replica, số consumer tiếp tục tăng theo từng replica. Vì vậy, để biết hệ thống thực sự tạo bao nhiêu consumer, cần tính từ số listener container, concurrency và số instance ứng dụng.

Một điểm dễ nhầm là **consumer được tạo**, **member đã tham gia consumer group** và **consumer được gán partition** là ba trạng thái khác nhau. Spring có thể đã tạo consumer nhưng nó chưa join group; một member đã join vẫn có thể không được gán partition nếu số member lớn hơn số partition phù hợp. Đếm đúng ba lớp này giúp tránh scale thừa và chẩn đoán chính xác vì sao một số consumer không nhận record.

Bài học thuộc chương **Concurrency và scale** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách Spring Kafka tạo consumer từ listener concurrency, cách tính số lượng trên nhiều replica và listener, và cách quan sát assignment thực tế trong Kafka consumer group.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa @KafkaListener, listener container, concurrency và KafkaConsumer.
- Tính số consumer được tạo trong một JVM và trên toàn bộ deployment.
- Tính riêng số consumer thuộc từng group.id.
- Phân biệt consumer instance đã tạo, group member đã đăng ký và member có partition assignment.
- Cấu hình concurrency bằng Spring Boot, container factory và @KafkaListener.
- Hiểu tác động của nhiều listener và nhiều replica.
- Quan sát container con trong Spring và group member ở Kafka.
- Giải thích vì sao tăng concurrency không tự tăng số partition hoặc throughput.
- Xác định cấu hình nào tạo consumer dư hoặc làm tăng chi phí vận hành.

## 1. Một @KafkaListener tạo ra consumer như thế nào?

Spring Kafka không gọi trực tiếp phương thức @KafkaListener bằng một KafkaConsumer dùng chung cho toàn ứng dụng. Khi ứng dụng khởi động, Spring tạo listener endpoint và listener container để quản lý vòng đời consumer.

Với concurrency lớn hơn một, Spring Kafka dùng ConcurrentMessageListenerContainer. Container này tạo các KafkaMessageListenerContainer con; mỗi container con quản lý một Kafka consumer và vòng poll riêng.

~~~mermaid
flowchart TD
    A["@KafkaListener"] --> B["Listener endpoint"]
    B --> C["ConcurrentMessageListenerContainer"]
    C --> D1["KafkaMessageListenerContainer 1"]
    C --> D2["KafkaMessageListenerContainer 2"]
    C --> D3["KafkaMessageListenerContainer 3"]
    D1 --> K1["KafkaConsumer 1"]
    D2 --> K2["KafkaConsumer 2"]
    D3 --> K3["KafkaConsumer 3"]
    K1 --> G["Consumer group"]
    K2 --> G
    K3 --> G
~~~

Ví dụ một listener có concurrency bằng ba:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        concurrency = "3"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Khi container khởi động thành công, listener này có ba consumer worker trong cùng JVM. Mỗi worker có KafkaConsumer riêng và có thể được Kafka group coordinator đăng ký thành một member của group orders-fulfillment.

Concurrency là số consumer worker mà container được cấu hình tạo. Nó không phải số lần gọi phương thức listener, số record trong một poll hay số partition của topic.

## 2. Ba con số cần phân biệt

Khi nói “có bao nhiêu consumer”, cần xác định đang đếm lớp nào:

| Khái niệm | Ý nghĩa | Nơi quan sát |
|---|---|---|
| Consumer được tạo (instantiated) | KafkaConsumer được listener container khởi tạo trong ứng dụng | Spring listener container và log khởi động |
| Group member | Consumer đã tham gia consumer group và được coordinator nhận diện | Kafka AdminClient hoặc công cụ quản trị group |
| Consumer được gán partition | Group member đang sở hữu ít nhất một partition theo assignment hiện tại | Group assignment |

Ba con số có thể khác nhau trong một khoảng thời gian:

- Container chưa start hoặc đang dừng có thể chưa có consumer hoạt động.
- Consumer vừa khởi động có thể chưa hoàn tất quá trình join group.
- Member đã tham gia group có thể không nhận partition vì số member lớn hơn số partition có thể gán.
- Khi rebalance, assignment có thể tạm thời chưa ổn định.

Một member không có partition vẫn có thể là thành viên hợp lệ của group và duy trì membership. Nó chưa xử lý record từ các partition của subscription trong assignment hiện tại, nhưng không có nghĩa consumer object chưa được tạo.

## 3. Công thức tính consumer theo replica và concurrency

Với một listener container giống nhau chạy trên nhiều replica:

~~~text
N_{created} = R \times C
~~~

Trong đó:

- (R): số replica đang chạy listener.
- (C): concurrency của listener container trên mỗi replica.
- (N_{created}): số consumer worker dự kiến được tạo khi tất cả container đã khởi động ổn định.

Ví dụ:

| Replica | Concurrency mỗi replica | Consumer worker dự kiến |
|---:|---:|---:|
| 1 | 1 | 1 |
| 1 | 3 | 3 |
| 2 | 3 | 6 |
| 4 | 3 | 12 |
| 5 | 4 | 20 |

Nếu deployment có ba pod và listener concurrency bằng bốn, tổng số consumer worker của listener đó là 12, không phải bốn.

Công thức trên tính một listener container. Nếu ứng dụng có nhiều listener container, cần cộng số consumer của từng container:

~~~text
N_{created,total} = sum_{j=1}^{L} (R_j \times C_j)
~~~

Với (L) là số loại listener/container được tính, (R_j) là số replica chạy container j và (C_j) là concurrency của container đó.

Nếu các listener dùng group ID khác nhau, chúng thuộc các consumer group riêng. Nếu cùng group ID, các member của những listener đó cùng tham gia một group và việc phân phối partition phụ thuộc subscription cùng assignor. Khi tính theo group, chỉ cộng các container có cùng group ID và đang kết nối cùng cluster.

Các consumer được tạo thủ công bằng KafkaConsumer ngoài listener container cũng cần được tính riêng.

## 4. Ví dụ ứng dụng có nhiều listener

Giả sử một ứng dụng có hai listener:

- fulfillment listener concurrency 3, group orders-fulfillment.
- audit listener concurrency 2, group orders-audit.

Ứng dụng chạy bốn replica. Mỗi replica tạo:

| Listener | Group ID | Concurrency | Consumer mỗi replica |
|---|---|---:|---:|
| Fulfillment | orders-fulfillment | 3 | 3 |
| Audit | orders-audit | 2 | 2 |
| Tổng | Hai group riêng | 5 | 5 |

Trên bốn replica:

- Group orders-fulfillment có tối đa 12 consumer member từ các listener này.
- Group orders-audit có tối đa 8 consumer member.
- Toàn ứng dụng tạo dự kiến 20 consumer worker.

Không cộng 12 và 8 thành một group có 20 member. Đây là hai group độc lập, có offset và partition assignment riêng.

Ví dụ code:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment",
            concurrency = "3"
    )
    public void fulfill(OrderCreatedEvent event) {
        fulfillmentService.handle(event);
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-audit",
            concurrency = "2"
    )
    public void audit(OrderCreatedEvent event) {
        auditService.record(event);
    }
}
~~~

Mỗi phương thức @KafkaListener tạo một listener endpoint/container riêng. Concurrency của listener này không tự động chia sẻ hoặc cộng dồn với listener kia, dù chúng nằm trong cùng class Java.

## 5. Cấu hình concurrency bằng Spring Boot

Với listener container factory tự động cấu hình bởi Spring Boot, có thể đặt concurrency mặc định:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 3
~~~

Giá trị này được áp dụng làm concurrency mặc định cho listener container được tạo từ factory auto-configured, trừ khi listener hoặc cấu hình factory cụ thể ghi đè.

Cấu hình này không có nghĩa toàn ứng dụng chỉ tạo ba consumer. Nếu ứng dụng có nhiều listener endpoint sử dụng factory đó, mỗi endpoint có thể tạo số consumer theo concurrency của nó.

Cần kiểm tra listener nào đang dùng factory mặc định và listener nào chỉ định containerFactory riêng.

## 6. Cấu hình concurrency trong ConcurrentKafkaListenerContainerFactory

Khi cần kiểm soát từng nhóm listener, có thể tạo factory riêng:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
fulfillmentKafkaListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Sử dụng factory:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "fulfillmentKafkaListenerFactory"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

Ở đây factory đặt concurrency bằng ba. Các listener dùng factory này sẽ nhận cấu hình đó nếu không có thuộc tính concurrency riêng tại endpoint.

Nếu có cả cấu hình mặc định Spring Boot, factory tùy chỉnh và thuộc tính concurrency trong @KafkaListener, hãy xác định rõ listener đang dùng factory nào và giá trị cuối cùng được áp dụng. Tránh cộng các giá trị cấu hình với nhau: chúng là các nguồn đặt giá trị concurrency cho container, không phải số consumer cộng dồn.

## 7. Ghi đè concurrency ở @KafkaListener

Spring Kafka cho phép khai báo concurrency trực tiếp tại @KafkaListener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "fulfillmentKafkaListenerFactory",
        concurrency = "5"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

Nếu endpoint đặt concurrency bằng năm, container của endpoint này sử dụng giá trị năm thay vì concurrency mặc định của factory. Thuộc tính annotation có thể dùng placeholder cấu hình để thay đổi theo môi trường:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        concurrency = "${app.kafka.fulfillment.concurrency:3}"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

Trong ví dụ, giá trị mặc định là ba nếu app.kafka.fulfillment.concurrency không được khai báo. Khi chạy trên nhiều replica, mỗi replica tạo số worker theo giá trị concurrency hiệu lực.

Nên tập trung concurrency vào cấu hình theo môi trường hoặc theo factory để dễ vận hành. Nếu đặt giá trị rải rác ở nhiều annotation, việc tính tổng consumer và điều chỉnh tải sẽ khó hơn.

## 8. Số partition giới hạn số consumer được giao việc, không giới hạn số consumer được tạo

Giả sử topic orders.created có bốn partition, ứng dụng chạy ba replica và mỗi replica có concurrency bằng ba.

Số consumer worker dự kiến được tạo:

~~~text
3 \times 3 = 9
~~~

Nhưng với một topic có bốn partition và tất cả member cùng subscribe topic đó, tối đa bốn member có thể được gán partition tại một thời điểm. Các member còn lại có thể ở trong group nhưng không có partition assignment.

~~~mermaid
flowchart TB
    subgraph Apps["3 application replicas"]
        A1["Replica 1: 3 consumers"]
        A2["Replica 2: 3 consumers"]
        A3["Replica 3: 3 consumers"]
    end
    subgraph Topic["orders.created: 4 partitions"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
        P3["Partition 3"]
    end
    A1 --> P0
    A2 --> P1
    A3 --> P2
    A1 --> P3
    A2 -.-> I["5 members may have no assignment"]
    A3 -.-> I
~~~

Sơ đồ chỉ minh họa giới hạn số member có assignment; partition cụ thể được phân phối theo assignor và group membership thực tế.

Điểm quan trọng:

- Partition count không ngăn Spring tạo thêm consumer worker.
- Consumer dư vẫn có chi phí thread, kết nối, heartbeat và quản lý group.
- Tăng concurrency vượt số partition thường không tăng mức song song đọc của topic đó.
- Nếu group subscribe nhiều topic, cần xét tổng số partition phù hợp với subscription và assignment strategy, không chỉ đếm partition của một topic.

Với subscription phức tạp hoặc nhiều topic, không phải lúc nào mọi member cũng được gán partition chỉ vì tổng partition count lớn hơn member count. Kết quả còn phụ thuộc assignor và cách các member subscribe.

## 9. Trường hợp chỉ định partition tường minh

Khi @KafkaListener dùng @TopicPartition để gán partition cụ thể, Spring Kafka phân phối các TopicPartition được khai báo giữa các child container.

Ví dụ:

~~~java
@KafkaListener(
        groupId = "orders-fixed-assignment",
        topicPartitions = {
                @TopicPartition(topic = "orders.created", partitions = {"0", "1", "2"})
        },
        concurrency = "5"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Có ba partition được chỉ định nhưng concurrency khai báo là năm. Với explicit partition assignment, Spring Kafka điều chỉnh số child container xuống theo số partition được chỉ định khi concurrency lớn hơn số partition có thể phân phối. Vì vậy trường hợp này không nhất thiết tạo đủ năm consumer.

Đây là khác biệt cần nhớ giữa subscription theo topic và assignment partition tường minh. Hãy kiểm tra log khởi động và số child container thực tế khi dùng @TopicPartition.

Khi có nhiều TopicPartitionOffset, Spring Kafka phân phối chúng giữa các child container. Mỗi partition vẫn chỉ được một consumer trong container assignment tương ứng quản lý tại một thời điểm.

## 10. Đếm consumer khi có nhiều group ID

Một ứng dụng có thể có nhiều listener với group ID khác nhau. Mỗi group duy trì membership và offset riêng, dù các listener cùng đọc một topic.

Ví dụ một replica có:

- Listener A: group orders-fulfillment, concurrency 3.
- Listener B: group orders-analytics, concurrency 2.
- Listener C: group orders-audit, concurrency 1.

Tổng số consumer worker trong JVM là sáu, nhưng số lượng được phân thành ba group:

| Group ID | Consumer mỗi replica | 3 replica |
|---|---:|---:|
| orders-fulfillment | 3 | 9 |
| orders-analytics | 2 | 6 |
| orders-audit | 1 | 3 |
| Tổng toàn ứng dụng | 6 | 18 |

Không dùng tổng 18 để suy ra có 18 consumer đang cạnh tranh partition trong một group. Mỗi group nhận toàn bộ luồng theo offset riêng và có assignment độc lập.

Ngược lại, nếu nhiều listener dùng chung group ID và subscribe cùng topic, member từ tất cả listener có thể cùng chia partition. Hãy kiểm tra groupId hiệu lực tại từng endpoint thay vì chỉ nhìn group-id mặc định trong application.yml.

## 11. Quan sát số container con trong Spring

Có thể dùng KafkaListenerEndpointRegistry để xem các listener container đang được quản lý. Với ConcurrentMessageListenerContainer, có thể đọc concurrency và số container con.

Ví dụ minh họa:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logContainerCounts() {
        for (MessageListenerContainer container :
                registry.getListenerContainers()) {

            if (container instanceof
                    ConcurrentMessageListenerContainer<?, ?> concurrent) {

                log.info(
                        "Listener container concurrency={}, childContainers={}",
                        concurrent.getConcurrency(),
                        concurrent.getContainers().size()
                );
            }
        }
    }
}
~~~

getConcurrency() cho biết concurrency của container; getContainers().size() cho biết số KafkaMessageListenerContainer con hiện có. Đối chiếu hai giá trị này giúp phát hiện container chưa tạo đủ worker như cấu hình.

Đây là số liệu ở phía Spring. Nó không chứng minh mọi consumer đã join group hoặc có partition assignment. Để xác minh trạng thái phía Kafka, cần quan sát group membership và assignment.

Nếu ứng dụng có nhiều container factory hoặc listener tự tạo, hãy duyệt toàn bộ container đang quản lý và tính theo listener ID/group ID tương ứng. Tránh chỉ log một factory rồi coi đó là tổng consumer của ứng dụng.

## 12. Quan sát group member và partition assignment bằng AdminClient

Kafka AdminClient có thể mô tả consumer group. Kết quả cho biết member mà coordinator đang nhận diện và các partition được gán cho từng member.

Ví dụ:

~~~java
Map<String, ConsumerGroupDescription> groups =
        adminClient.describeConsumerGroups(
                List.of("orders-fulfillment")
        ).all().get(10, TimeUnit.SECONDS);

ConsumerGroupDescription group =
        groups.get("orders-fulfillment");

log.info(
        "Group={}, state={}, members={}",
        group.groupId(),
        group.state(),
        group.members().size()
);

for (MemberDescription member : group.members()) {
    log.info(
            "memberId={}, clientId={}, host={}, assignedPartitions={}",
            member.consumerId(),
            member.clientId(),
            member.host(),
            member.assignment().topicPartitions()
    );
}
~~~

Ví dụ này giúp phân biệt:

- Tổng member đã join group.
- Client ID và host của từng member.
- Số partition được gán cho từng member.
- Member có assignment rỗng.

API AdminClient có thể khác nhẹ theo phiên bản Kafka client; hãy dùng phiên bản dependency đang có trong dự án. Khi group đang rebalance, kết quả quan sát có thể thay đổi nhanh; nên lấy mẫu sau khi group ổn định và dùng timeout hợp lý.

Khi đối chiếu với số consumer Spring tạo, cần tính đến thời điểm khởi động, lỗi kết nối, xác thực, group join và việc container đang dừng.

## 13. Tính consumer cho deployment Kubernetes

Trong Kubernetes, số replica thường thay đổi theo cấu hình Deployment hoặc HorizontalPodAutoscaler. Nếu mỗi pod có một listener container concurrency cố định, số consumer sẽ thay đổi theo số pod đang chạy.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-fulfillment
spec:
  replicas: 4
  template:
    spec:
      containers:
        - name: app
          image: example/orders-fulfillment:1.0
          env:
            - name: SPRING_KAFKA_LISTENER_CONCURRENCY
              value: "3"
~~~

Với bốn pod và concurrency ba, deployment dự kiến tạo 12 consumer worker cho listener sử dụng cấu hình này.

Nếu HPA tăng replicas từ bốn lên sáu, số worker dự kiến tăng từ 12 lên 18. Kafka sẽ rebalance group để phân phối partition theo membership mới.

Cần nhớ:

- Pod ở trạng thái Pending hoặc chưa start ứng dụng chưa tạo listener consumer.
- Pod đang Terminating có thể còn consumer trong quá trình shutdown.
- Rolling deployment có thể tạm thời làm số pod và consumer vượt số replica mong muốn trong chiến lược maxSurge.
- HPA scale nhanh có thể tạo nhiều lần rebalance.
- Số consumer tăng không có ích nếu partition hoặc downstream đã đạt giới hạn.

Khi tính capacity, hãy dùng số pod thực sự chạy listener và concurrency hiệu lực, không chỉ lấy replicas khai báo trong manifest.

## 14. Tính concurrency khi có nhiều listener và nhiều replica

Một bảng cấu hình rõ ràng giúp dự đoán số consumer trước khi triển khai.

Giả sử deployment có ba replica và các listener:

| Listener | Group ID | Concurrency/pod | Consumer toàn deployment |
|---|---|---:|---:|
| Fulfillment | orders-fulfillment | 4 | 12 |
| Notification | orders-notification | 2 | 6 |
| Audit | orders-audit | 1 | 3 |
| Tổng | 3 group | 7 | 21 |

Nếu tăng fulfillment concurrency từ bốn lên sáu, tổng consumer toàn deployment tăng thêm sáu, từ 21 lên 27. Chỉ group orders-fulfillment tăng member; hai group còn lại không đổi.

Công thức hữu ích:

[
N_{group} = sum_{j \in group} R_j \times C_j
]

Trong đó chỉ cộng listener container cùng group ID trên cùng Kafka cluster. Nếu một container được triển khai trên các replica khác nhau với concurrency khác nhau, hãy dùng số replica và concurrency thực tế của từng nhóm triển khai.

Không cộng số partition vào công thức consumer được tạo. Partition count dùng để đánh giá khả năng nhận assignment và mức song song đọc, không quyết định số consumer object mà Spring khởi tạo.

## 15. Các nguyên nhân khiến số consumer thực tế khác dự kiến

| Nguyên nhân | Hiện tượng | Cách kiểm tra |
|---|---|---|
| Container chưa start | Spring chưa tạo đủ consumer | Kiểm tra lifecycle và trạng thái listener container. |
| Listener dùng factory khác | Concurrency khác cấu hình Boot | Kiểm tra containerFactory trên @KafkaListener. |
| Annotation override | Giá trị concurrency không như factory | Kiểm tra concurrency trên endpoint. |
| Explicit partition assignment | Spring có thể giảm concurrency theo số partition được khai báo | Kiểm tra @TopicPartition và child container count. |
| Replica chưa sẵn sàng | Tổng worker thấp hơn replicas khai báo | Kiểm tra pod readiness và log ứng dụng. |
| Consumer lỗi kết nối/authentication | Worker không join được group | Kiểm tra exception, broker address, TLS/SASL và ACL. |
| Rebalance đang diễn ra | Member/assignment thay đổi tạm thời | Quan sát group state và log rebalance. |
| Nhiều group ID | Consumer bị chia vào nhiều group riêng | Kiểm tra group ID hiệu lực từng listener. |
| Shutdown/rolling update | Consumer đang rời group hoặc được tạo lại | Kiểm tra lifecycle và rollout events. |

Nếu số consumer member thấp hơn số worker dự kiến, hãy xác minh container đã start và consumer có join được broker trước khi tăng concurrency thêm.

Nếu số member đúng nhưng số member có assignment thấp, hãy kiểm tra số partition, subscription, assignor và explicit assignment. Đây là hai loại vấn đề khác nhau.

## 16. Tác động của consumer dư tới tài nguyên và throughput

Consumer dư không chỉ là con số hiển thị trên dashboard. Mỗi consumer worker có thể tạo thêm:

- Một KafkaConsumer và các cấu trúc buffer nội bộ.
- Một thread xử lý poll/listener.
- Kết nối mạng tới broker và group coordinator.
- Heartbeat và request fetch/commit.
- Tài nguyên heap, CPU và metric.
- Chi phí group coordination và rebalance khi membership thay đổi.

Nếu có 24 consumer member nhưng topic chỉ có sáu partition trong group, tối đa sáu member có thể nhận partition của topic đó khi mọi member cùng subscription. Các member còn lại vẫn tạo chi phí nhưng không làm tăng khả năng đọc song song.

Consumer quá nhiều có thể làm tăng số lần rebalance khi autoscaling hoặc rolling deployment, tăng kết nối tới broker và gây áp lực lên hệ thống quản lý group.

Mặt khác, concurrency quá thấp cũng có thể làm partition không được khai thác khi mỗi consumer xử lý chậm. Mục tiêu là chọn số consumer phù hợp với partition, tài nguyên và throughput cần đạt, không phải tối đa hóa số worker.

## 17. Quy trình chọn số consumer phù hợp

Có thể xác định concurrency theo các bước:

1. Liệt kê các listener endpoint và group ID.
2. Xác định số replica thực tế của từng deployment.
3. Xác định concurrency hiệu lực của từng listener container.
4. Tính tổng consumer worker theo từng group.
5. Đối chiếu số partition và subscription của từng group.
6. Đo lag, throughput, processing latency và downstream capacity.
7. Tăng concurrency hoặc replica khi còn partition chưa được khai thác và tài nguyên cho phép.
8. Nếu số member đã vượt partition, ưu tiên tối ưu xử lý hoặc đánh giá tăng partition thay vì tiếp tục thêm consumer.
9. Kiểm tra tác động tới database, connection pool, API downstream và broker.
10. Theo dõi group membership và rebalance sau mỗi lần thay đổi.
11. Ghi lại cấu hình hiệu lực để lần scale sau có thể tính toán nhất quán.

Không nên đặt concurrency bằng số CPU một cách máy móc. Consumer có thể bị giới hạn bởi partition count, I/O, database hoặc dịch vụ downstream trước khi CPU được sử dụng hết.

## 18. Bài tập tổng hợp: tính consumer cho hệ thống đơn hàng

Một hệ thống Spring Kafka có ba deployment:

- Fulfillment: ba replica, concurrency bốn, group orders-fulfillment.
- Notification: hai replica, concurrency hai, group orders-notification.
- Audit: bốn replica, concurrency một, group orders-audit.

Yêu cầu:

1. Tính số consumer worker mỗi deployment.
2. Tính tổng số consumer toàn hệ thống.
3. Tính số member dự kiến của từng group.
4. Cho biết nếu orders.created có sáu partition thì tối đa bao nhiêu member của group fulfillment có partition khi tất cả cùng subscribe topic.
5. Tăng fulfillment lên concurrency sáu và tính lại số member.
6. Chạy hai listener cùng group ID và xác minh chúng chia assignment theo group.
7. Đổi một listener sang group ID riêng và quan sát offset độc lập.
8. Dùng KafkaListenerEndpointRegistry để kiểm tra concurrency và child container count.
9. Dùng AdminClient để xem member, client ID và partition assignment.
10. Scale deployment từ ba lên năm replica và quan sát rebalance.
11. Kiểm tra số consumer trong giai đoạn rolling update.
12. Đề xuất cấu hình cuối dựa trên partition, lag và năng lực downstream.

Kết quả cần có bảng gồm deployment, listener, group ID, replica, concurrency, consumer dự kiến, member quan sát được và số member có partition assignment. Hãy ghi rõ thời điểm đo vì group membership có thể thay đổi trong lúc rollout hoặc rebalance.

## 19. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Container model | @KafkaListener và listener container | Giải thích được container con quản lý KafkaConsumer. |
| 2. Concurrency | Một container tạo nhiều consumer worker | Tính được consumer trong một JVM. |
| 3. Replicas | Nhiều pod/instance | Tính được số consumer toàn deployment. |
| 4. Multiple listeners | Nhiều endpoint và group ID | Cộng đúng consumer theo từng group. |
| 5. Configuration | Boot, factory và annotation | Xác định đúng concurrency hiệu lực. |
| 6. Assignment | Member và partition | Phân biệt consumer được tạo với consumer được gán partition. |
| 7. Runtime inspection | Registry và AdminClient | Đối chiếu số worker với group member thực tế. |
| 8. Scaling | Partition, lag và downstream | Chọn concurrency theo số liệu và giới hạn. |
| 9. Operations | Kubernetes rollout và rebalance | Dự đoán được biến động consumer khi scale. |

Bài học hoàn thành khi bạn có thể tính số consumer được Spring Kafka tạo ra từ số replica và concurrency của từng listener, tách chính xác số consumer theo group ID, và xác minh được group member cùng partition assignment ở runtime.

Số consumer thực tế không chỉ là giá trị concurrency trong một annotation. Nó là kết quả của số listener container, concurrency hiệu lực và số instance đang chạy. Sau khi tính số worker, hãy kiểm tra riêng group membership và partition assignment để biết bao nhiêu consumer thực sự có thể nhận dữ liệu và tạo thêm throughput.

