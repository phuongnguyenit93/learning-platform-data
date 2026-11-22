# Tránh group id thay đổi ngoài ý muốn

Trong Kafka, **group.id** xác định danh tính của một consumer group. Kafka dùng giá trị này để phối hợp các consumer cùng chia partition và lưu offset đã commit. Vì vậy, group id là một phần của danh tính xử lý dữ liệu: thay đổi nó có thể làm ứng dụng bắt đầu một luồng đọc mới, đọc lại dữ liệu cũ hoặc bỏ qua backlog tùy cấu hình offset.

Trong Spring Kafka, group id có thể đến từ cấu hình consumer của Spring Boot, ConsumerFactory, thuộc tính của listener hoặc biến môi trường. Một giá trị bị ghi đè ngoài ý muốn có thể khiến mỗi pod tham gia một group khác nhau, hai service độc lập lại dùng chung một group, hoặc một lần triển khai tạo ra group mới. Các lỗi này thường không làm ứng dụng khởi động thất bại; chúng làm thay đổi cách phân phối record và có thể tạo ra duplicate hoặc bỏ sót nghiệp vụ.

Mục tiêu vận hành là giữ group id ổn định cho cùng một logical consumer subscription, đồng thời chỉ thay đổi khi có kế hoạch chuyển đổi offset và xử lý dữ liệu rõ ràng.

## 1. group.id đại diện cho điều gì?

Một consumer group là tập các consumer phối hợp đọc một hoặc nhiều topic. Với một topic có nhiều partition, Kafka gán các partition cho consumer trong group để chia tải. Các consumer trong cùng group dùng chung không gian offset theo từng topic-partition.

Ví dụ, topic **orders** có sáu partition và group id là **billing-service**. Nếu service chạy ba consumer trong cùng group, Kafka có thể phân phối mỗi consumer hai partition. Khi tăng lên sáu consumer, mỗi consumer có thể nhận một partition. Nếu tăng lên tám consumer, hai consumer có thể không nhận partition nào vì số consumer đang hoạt động vượt số partition.

~~~mermaid
flowchart TD
    T["Topic: orders (6 partitions)"] --> G["Consumer group: billing-service"]
    G --> C1["Consumer 1: P0, P1"]
    G --> C2["Consumer 2: P2, P3"]
    G --> C3["Consumer 3: P4, P5"]
~~~

Group id liên kết ba điều:

- **Membership**: consumer nào đang tham gia cùng một group và phối hợp assignment.
- **Partition assignment**: các partition được phân phối giữa các member của group.
- **Offset state**: vị trí đã commit của group cho từng topic-partition.

Một consumer group mới có offset state riêng, kể cả khi nó đọc cùng topic với một group đã tồn tại. Kafka không tự coi hai group có cùng code, cùng application name hoặc cùng database là một consumer group. Danh tính group dựa trên chính chuỗi group id.

### 1.1 Cùng group id nghĩa là chia tải

Giả sử hai pod cùng chạy listener đọc topic orders với group id billing-service. Chúng là hai member của cùng một group. Kafka chia partition giữa chúng; thông thường mỗi partition chỉ được gán cho tối đa một member trong group tại một thời điểm.

Kết quả là mỗi record của partition được xử lý bởi một member trong group. Hai pod không phải hai bản sao độc lập cùng nhận tất cả record. Đây là cách scale một logical consumer service.

Nếu có hai ứng dụng khác nhau nhưng vô tình cùng group id, chúng sẽ cạnh tranh partition. Một ứng dụng có thể nhận một số partition, ứng dụng còn lại nhận các partition khác. Mỗi ứng dụng vì thế chỉ thấy một phần stream. Đây là lỗi thường gặp khi sao chép cấu hình từ service khác mà không đổi group id.

### 1.2 Khác group id nghĩa là hai subscription độc lập

Nếu hai ứng dụng dùng group id khác nhau, Kafka xem chúng là hai subscriber độc lập. Mỗi group có assignment và offset riêng, nên cả hai có thể đọc toàn bộ partition của topic.

Ví dụ:

- billing-service đọc orders để cập nhật thanh toán.
- analytics-service đọc orders để xây dựng báo cáo.

Hai service này thường cần group id riêng. Nếu dùng chung một group, Kafka sẽ chia partition giữa chúng và mỗi service chỉ xử lý một phần record, trái với ý định nghiệp vụ.

~~~mermaid
flowchart TD
    T["Topic: orders"] --> G1["Group: billing-service"]
    T --> G2["Group: analytics-service"]
    G1 --> B1["Billing consumers"]
    G2 --> A1["Analytics consumers"]
    B1 --> DB1["Billing database"]
    A1 --> DB2["Analytics store"]
~~~

Không có một group id “đúng cho topic”. Group id phải đại diện cho một logical subscription hoặc một luồng xử lý có chung mục tiêu và offset.

## 2. Điều gì xảy ra khi group id thay đổi?

Kafka lưu offset theo group id, topic và partition. Khi group id thay đổi, consumer mới không tự động kế thừa offset của group cũ.

Giả sử service đang chạy với group id **orders-projection-v1**, đã xử lý đến offset 500 ở partition 0. Một lần triển khai thay đổi group id thành **orders-projection-v2**.

Kafka nhìn thấy một group mới. Group mới không có committed offset của group cũ, nên hành vi bắt đầu phụ thuộc vào **auto.offset.reset**.

| auto.offset.reset | Hành vi khi group mới chưa có offset hợp lệ |
|---|---|
| earliest | Bắt đầu từ offset sớm nhất còn được giữ trong partition |
| latest | Bắt đầu từ cuối log tại thời điểm cần xác lập vị trí đọc; backlog hiện có có thể bị bỏ qua |
| none | Ném lỗi nếu không có offset hợp lệ để sử dụng |

Điều này có thể dẫn đến hai kết quả rất khác nhau:

- Với **earliest**, service có thể đọc lại nhiều record đã xử lý bởi group cũ. Database hoặc downstream có thể nhận duplicate nếu nghiệp vụ không idempotent.
- Với **latest**, service có thể bắt đầu sau backlog đang tồn tại. Các record chưa từng được xử lý bởi group mới có thể bị bỏ qua.
- Với **none**, consumer không tự chọn vị trí bắt đầu và báo lỗi để vận hành quyết định offset.

**auto.offset.reset không reset offset đang tồn tại.** Nó chỉ được dùng khi group chưa có committed offset hợp lệ cho partition hoặc offset đã lưu không còn hợp lệ, chẳng hạn nằm ngoài phạm vi log do retention. Vì vậy, thay đổi group id thường kích hoạt hành vi reset; thay đổi riêng auto.offset.reset trên một group đã có offset hợp lệ thường không làm group nhảy về earliest/latest.

### 2.1 Offset cũ không chuyển sang group mới

Offset của group cũ vẫn thuộc group cũ. Việc đổi cấu hình group id không xóa hoặc chuyển offset đó.

Offset cũ có thể còn được giữ một khoảng thời gian theo chính sách lưu offset của Kafka, nhưng không nên xem nó là bản backup vĩnh viễn. Offset metadata có thể hết hạn khi group không hoạt động đủ lâu hoặc bị xóa bởi thao tác quản trị.

Nếu mục tiêu là đổi tên group nhưng tiếp tục đúng vị trí xử lý, cần một kế hoạch chuyển offset rõ ràng. Không thể chỉ đổi chuỗi group id rồi mong Kafka tự nối tiếp.

### 2.2 Group mới có thể phát sinh duplicate side effect

Nếu group mới dùng earliest, nó có thể đọc lại các record đã được group cũ xử lý. Ví dụ:

1. billing-service cũ đã ghi hóa đơn cho order 1001.
2. Một lần deploy thay group id.
3. Group mới bắt đầu từ earliest.
4. Record order 1001 được xử lý lại.
5. Ứng dụng ghi hóa đơn lần nữa nếu không có idempotency hoặc unique business key.

Kafka không biết hai lần xử lý thuộc cùng một nghiệp vụ. Consumer cần dùng event id, order id hoặc idempotency key để ngăn side effect trùng.

### 2.3 Group mới có thể bỏ qua backlog

Nếu group mới dùng latest, nó có thể đặt vị trí bắt đầu ở cuối log khi group chưa có offset. Các record đang chờ xử lý tại thời điểm đó không được đọc bởi group mới.

Đây là một kiểu mất xử lý ở cấp ứng dụng, dù record vẫn còn trong Kafka. Dữ liệu chưa bị xóa; consumer chỉ bắt đầu đọc sau chúng. Có thể phục hồi bằng cách điều chỉnh offset có kiểm soát nếu dữ liệu vẫn còn retention.

## 3. Những cách group id bị thay đổi ngoài ý muốn

Thay đổi group id thường xuất phát từ cấu hình được tổng hợp từ nhiều nguồn hoặc từ việc dùng một giá trị không ổn định.

### 3.1 Dùng pod name, hostname hoặc UUID làm group id

Ví dụ cấu hình nguy hiểm:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${HOSTNAME}
~~~

Trong Kubernetes, mỗi pod thường có hostname riêng. Khi mỗi pod có group id riêng, Kafka tạo một consumer group cho từng pod. Thay vì chia partition giữa các replica, mỗi pod trở thành subscriber độc lập và có thể nhận toàn bộ stream.

Hậu quả có thể gồm:

- Mỗi pod xử lý cùng record và tạo side effect trùng.
- Số consumer group tăng theo số lần scale hoặc restart.
- Mỗi group có offset riêng, khiến việc quan sát lag và quản trị offset phức tạp.
- Tải đọc và tải downstream tăng theo số pod.
- Pod mới tạo group mới và có thể đọc lại từ earliest hoặc bắt đầu từ latest.

Không dùng các giá trị thay đổi theo vòng đời instance làm group id: pod name, container id, hostname, random UUID, timestamp, process id hoặc deployment revision. Các giá trị này phù hợp hơn cho client id hoặc metadata quan sát, tùy mục đích.

### 3.2 Dùng cùng group id cho nhiều môi trường

Nếu development, staging và production cùng kết nối một Kafka cluster và dùng chung group id, consumer ở các môi trường có thể cạnh tranh partition. Một số record production có thể bị staging xử lý, hoặc các member từ môi trường khác nhau liên tục làm group rebalance.

Tên môi trường nên được thể hiện trong group id khi nhiều môi trường dùng chung cluster, ví dụ:

- orders-projection-dev
- orders-projection-staging
- orders-projection-prod

Nếu mỗi môi trường có Kafka cluster riêng, group id vẫn nên được đặt có quy ước rõ ràng. Điều đó giúp log, dashboard và runbook dễ đọc, đồng thời giảm nguy cơ khi môi trường được chuyển sang dùng chung cluster.

### 3.3 Gắn phiên bản ứng dụng vào group id

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-${APP_VERSION}
~~~

Khi APP_VERSION thay đổi sau mỗi build hoặc release, mỗi phiên bản có thể tạo một group mới. Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy nhưng thuộc hai group khác nhau. Cả hai group đều đọc toàn bộ stream, làm side effect bị nhân đôi.

Thông thường, group id đại diện cho logical subscription ổn định qua các phiên bản ứng dụng. Không đưa version, build number, Git SHA hoặc release timestamp vào group id nếu mục tiêu là tiếp tục offset hiện có.

Có những trường hợp migration chủ động cần chạy hai group song song, chẳng hạn kiểm chứng read model mới. Khi đó, hậu tố version có thể hữu ích, nhưng phải xem đó là một subscription độc lập có kế hoạch replay, dữ liệu đích riêng và tiêu chí kết thúc rõ ràng.

### 3.4 Placeholder hoặc profile bị ghi đè

Một cấu hình có vẻ ổn định vẫn có thể thay đổi theo môi trường:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${APP_KAFKA_GROUP:orders-projection}
~~~

Giá trị thực tế phụ thuộc biến môi trường APP_KAFKA_GROUP. Nếu ConfigMap, Secret, Helm values hoặc pipeline CI đặt giá trị khác, ứng dụng sẽ dùng group id khác.

Spring Boot có nhiều nguồn property. Profile, environment variable, command-line argument, system property và external configuration có thể ghi đè giá trị trong application.yml. Khi điều tra, cần xem cấu hình hiệu lực ở runtime thay vì chỉ đọc một file YAML.

Biến môi trường theo quy ước relaxed binding có thể ghi đè property dạng:

~~~text
SPRING_KAFKA_CONSUMER_GROUP_ID
~~~

Nếu một deployment template vô tình đưa release name, pod name hoặc namespace vào biến này, group id có thể thay đổi theo mỗi lần triển khai.

### 3.5 Annotation ghi đè ConsumerFactory

Spring Kafka cho phép đặt group id ở cấp listener. Vì vậy, cấu hình group id toàn cục trong Spring Boot có thể không phải giá trị cuối cùng của listener.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreated event) {
    // Process the event.
}
~~~

Thuộc tính **groupId** trên listener ghi đè group.id lấy từ consumer factory cho listener đó. Nếu groupId được viết trực tiếp trong annotation, thay đổi application.yml có thể không ảnh hưởng listener như người vận hành dự đoán.

Cũng cần chú ý thuộc tính **id** và **idIsGroup**:

- **id** là định danh của listener container.
- Theo mặc định, khi không cung cấp groupId riêng, Spring Kafka có thể dùng id làm group id nếu idIsGroup đang bật.
- **groupId** cho phép chỉ định group id rõ ràng cho listener.
- Đặt **idIsGroup=false** khi muốn id chỉ là container id và không muốn nó được dùng làm group id trong trường hợp không khai báo groupId.

Ví dụ khai báo rõ cả hai định danh:

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "orders"
)
public void handle(OrderCreated event) {
    // Process the event.
}
~~~

Cú pháp và khả năng cấu hình có thể phụ thuộc phiên bản Spring Kafka. Hãy kiểm tra annotation của phiên bản dự án. Điều quan trọng là không nhầm container id với group id, và biết chính xác listener đang nhận giá trị từ đâu.

### 3.6 Custom ConsumerFactory hoặc container factory

Ứng dụng có thể định nghĩa nhiều ConsumerFactory hoặc ConcurrentKafkaListenerContainerFactory. Mỗi factory có thể có cấu hình group id riêng. Một listener dùng factory khác có thể không nhận giá trị của spring.kafka.consumer.group-id.

Khi dự án có nhiều listener, hãy lập bản đồ:

- Listener nào dùng factory nào.
- Factory nhận group id từ property nào.
- Annotation có groupId riêng hay không.
- Listener có sử dụng idIsGroup mặc định hay không.
- Có bean post-processor hoặc customizer nào sửa consumer properties hay không.

Không giả định mọi listener trong một ứng dụng đều dùng cùng một group chỉ vì chúng nằm trong cùng file application.yml.

## 4. Quy ước đặt group id ổn định

Một group id tốt thể hiện logical consumer subscription, môi trường và mục đích xử lý. Nó không nên phụ thuộc vào instance cụ thể.

Một quy ước có thể dùng:

~~~text
<service>-<subscription>-<environment>
~~~

Ví dụ:

~~~text
billing-service-orders-prod
orders-projection-prod
analytics-orders-staging
inventory-reservation-dev
~~~

Có thể chọn quy ước khác, nhưng cần bảo đảm các thuộc tính sau:

- Ổn định qua restart, scale và rolling deployment.
- Giống nhau giữa các replica thuộc cùng logical consumer group.
- Khác nhau giữa các logical subscription cần nhận toàn bộ stream độc lập.
- Khác nhau giữa các môi trường nếu chúng dùng chung Kafka cluster.
- Không chứa pod name, random value, build number hoặc version nếu không có mục đích migration.
- Được quản lý tập trung và có owner rõ ràng.

### 4.1 Một group cho một logical subscription

Hãy bắt đầu từ câu hỏi: “Nhóm consumer này đang cùng thực hiện một công việc nào?”

Ví dụ một ứng dụng thương mại điện tử có thể có:

| Logical subscription | Topic | Group id |
|---|---|---|
| Cập nhật read model đơn hàng | orders | orders-projection-prod |
| Xử lý thanh toán | orders | billing-service-prod |
| Giữ chỗ tồn kho | orders | inventory-reservation-prod |
| Phân tích hành vi | orders | analytics-orders-prod |

Các group trên đọc cùng topic nhưng có offset và assignment độc lập. Mỗi logical subscription có thể scale số replica riêng.

### 4.2 Các replica phải dùng cùng group id

Nếu service có bốn pod, cả bốn pod cần dùng cùng group id để Kafka phân phối partition giữa chúng.

~~~mermaid
flowchart TD
    T["Topic: orders"] --> G["Group: billing-service-prod"]
    G --> P1["Pod 1"]
    G --> P2["Pod 2"]
    G --> P3["Pod 3"]
    G --> P4["Pod 4"]
    P1 --> D["Shared billing database"]
    P2 --> D
    P3 --> D
    P4 --> D
~~~

Số partition giới hạn mức song song trong một group. Nếu topic có 8 partition, chạy 20 consumer trong cùng group không tạo ra 20 luồng xử lý partition độc lập. Một số consumer sẽ idle. Không nên tạo group id khác nhau cho từng pod chỉ để tận dụng mọi instance; cách đó biến mỗi pod thành một subscriber độc lập và làm tăng số lần xử lý.

### 4.3 Phân biệt group.id với client.id và group.instance.id

Ba thuộc tính thường bị nhầm:

| Thuộc tính | Mục đích | Có nên thay đổi theo instance? |
|---|---|---|
| group.id | Danh tính logical consumer group và không gian offset | Không; các replica của cùng group dùng chung |
| client.id | Định danh client để quan sát, log, metrics và quota | Có thể, thường thêm tên service/pod |
| group.instance.id | Định danh một member cụ thể khi dùng static membership | Có thể duy nhất và ổn định cho từng member |

**client.id** không thay thế group.id. Đổi client.id không tạo một consumer group mới và không tạo offset namespace mới.

**group.instance.id** dùng cho static membership trong các phiên bản Kafka hỗ trợ. Nó giúp broker nhận diện member ổn định qua một số lần restart, giảm rebalance không cần thiết. Mỗi member trong cùng group phải có group.instance.id duy nhất. Nếu hai consumer đồng thời dùng cùng static member id, một member có thể bị fencing hoặc rời group.

Không đặt group.instance.id giống group.id cho mọi pod. Cũng không dùng group.instance.id như cách đặt group id riêng cho từng pod. Chúng giải quyết hai cấp danh tính khác nhau.

## 5. Cấu hình group id trong Spring Boot và Spring Kafka

Nên chọn một nguồn cấu hình có chủ đích cho mỗi listener và tránh khai báo nhiều giá trị mâu thuẫn.

### 5.1 Cấu hình mặc định qua application.yml

Với ứng dụng chỉ có một logical consumer group chính, có thể đặt group id ở consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-projection-prod
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Các listener dùng ConsumerFactory mặc định có thể kế thừa group id này nếu annotation không ghi đè. Đây là cách đơn giản khi tất cả listener cùng thuộc một subscription hoặc cùng một nhóm xử lý.

Nếu ứng dụng có nhiều listener với mục đích khác nhau, không nên cố ép tất cả dùng chung một group id. Hãy khai báo group id riêng cho từng listener hoặc dùng factory tương ứng.

### 5.2 Dùng property riêng cho logical subscription

Một cách dễ quản lý hơn là đặt tên property theo mục đích ứng dụng:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod

spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Listener tham chiếu property:

~~~java
@KafkaListener(
    id = "ordersProjectionListener",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "orders"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

Lợi ích là tên group id được quản lý theo nghiệp vụ, trong khi id của container phục vụ lifecycle và quan sát nội bộ của Spring Kafka. Với nhiều listener, có thể tạo property riêng cho từng subscription.

### 5.3 Override theo môi trường có kiểm soát

Có thể giữ cùng cấu trúc property nhưng đặt giá trị riêng trong profile:

application.yml:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-dev
~~~

application-prod.yml:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

Hoặc inject qua biến môi trường:

~~~yaml
app:
  kafka:
    consumer:
      group-id: ${APP_KAFKA_GROUP_ID:orders-projection-dev}
~~~

Biến môi trường cần chứa một giá trị ổn định cho logical subscription, chẳng hạn **orders-projection-prod**. Không gắn nó với pod name hoặc build id.

### 5.4 Cấu hình bằng Java

Nếu tạo ConsumerFactory thủ công:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> ordersConsumerFactory(
        @Value("${app.kafka.consumer.group-id}") String groupId) {

    Map<String, Object> props = new HashMap<>();
    props.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092,kafka-3:9092"
    );
    props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Nếu annotation có groupId riêng, giá trị annotation có thể ghi đè group id từ factory. Hãy kiểm tra giá trị cuối cùng tại listener container thay vì chỉ kiểm tra bean factory.

### 5.5 Tránh nhiều nguồn cấu hình không rõ ưu tiên

Các nguồn phổ biến có thể ảnh hưởng group id:

- application.yml và application-{profile}.yml.
- Environment variables.
- Java system properties và command-line arguments.
- Helm values, ConfigMap hoặc deployment manifest.
- ConsumerFactory được tạo thủ công.
- Annotation @KafkaListener.
- Property placeholder hoặc SpEL.
- Customizer, bean post-processor hoặc thư viện nội bộ.

Tạo một nơi quản lý giá trị chính cho mỗi logical subscription. Nếu cần override theo môi trường, ghi rõ quy tắc và kiểm tra giá trị runtime. Không để một property trong YAML và một groupId literal trong annotation cùng tồn tại mà không có chủ đích.

## 6. Thiết kế group id cho các tình huống triển khai

### 6.1 Scale số replica

Khi scale từ 2 lên 5 pod, group id phải giữ nguyên. Kafka sẽ rebalance partition để phân phối lại giữa số member mới. Offset group tiếp tục từ vị trí đã commit.

Ví dụ:

- Trước scale: 2 pod, group orders-projection-prod.
- Sau scale: 5 pod, vẫn group orders-projection-prod.
- Kafka thực hiện rebalance và chia partition lại.
- Consumer tiếp tục đọc theo offset của group.

Scale không phải lý do để thay group id.

### 6.2 Rolling deployment

Trong rolling deployment, pod phiên bản cũ và mới có thể chạy đồng thời trong một khoảng thời gian. Nếu cả hai dùng cùng group id, chúng cùng tham gia một group và chia partition. Đây thường là hành vi mong muốn khi phiên bản mới tương thích với phiên bản cũ về payload, schema và side effect.

Nếu group id được gắn với version, hai phiên bản sẽ thuộc hai group khác nhau. Cả hai có thể xử lý toàn bộ stream song song, gây duplicate nghiệp vụ hoặc tạo hai read model cùng ghi một nơi.

Chỉ dùng group id riêng cho phiên bản mới khi đang thực hiện migration có chủ đích, có vùng dữ liệu đích riêng hoặc có cơ chế kiểm soát side effect.

### 6.3 Blue/green deployment

Blue/green có thể chạy hai nhóm consumer song song. Cần xác định mục đích:

- Nếu blue và green chỉ là hai tập replica thay thế nhau cho cùng một subscription, dùng cùng group id và kiểm soát thời điểm chuyển traffic/assignment.
- Nếu muốn green đọc độc lập để kiểm chứng dữ liệu trước khi cutover, dùng group id riêng, nhưng cần ngăn side effect trùng và xác định cách so sánh output.
- Khi cutover, cần quyết định offset của group mới tiếp tục từ đâu và xử lý backlog như thế nào.

Không để hai nhóm cùng ghi vào cùng bảng nghiệp vụ trong thời gian dài nếu chưa có idempotency hoặc cơ chế phân biệt side effect.

### 6.4 Chạy nhiều instance cho các tenant

Một số hệ thống tạo consumer group theo tenant. Đây có thể là thiết kế hợp lệ nếu mỗi tenant cần offset và tiến độ xử lý độc lập. Tuy nhiên, group id động phải được kiểm soát:

- Quy tắc tên phải ổn định và không chứa dữ liệu nhạy cảm.
- Số lượng group được giới hạn hoặc có cơ chế dọn dẹp.
- Có theo dõi group idle và offset retention.
- Lifecycle tạo/xóa tenant phải gắn với lifecycle group.
- Không tạo group mới cho mỗi request hoặc mỗi lần restart.

Nếu mỗi tenant chỉ là một partition key và các tenant có thể chia sẻ tiến độ xử lý, một group dùng chung có thể phù hợp hơn. Quyết định phụ thuộc isolation và scaling requirement của nghiệp vụ.

### 6.5 Tách môi trường và cluster

Khi dev, staging và production dùng chung Kafka cluster, group id phải khác nhau để không chia partition chéo môi trường. Nếu các môi trường có cluster độc lập, cùng một tên group id không chia sẻ offset giữa cluster vì offset được lưu trong cluster, nhưng tên chứa environment vẫn giúp vận hành rõ ràng.

## 7. Thay đổi group id có chủ đích: quy trình migration

Có lúc cần đổi group id thật sự, ví dụ đổi tên subscription, tách service hoặc xây dựng consumer mới. Khi đó, coi đây là migration offset, không phải thay một chuỗi cấu hình.

### 7.1 Xác định mục tiêu trước khi đổi

Có ba mục tiêu khác nhau:

1. **Đổi tên nhưng tiếp tục xử lý tại vị trí hiện tại**: cần chuyển offset từ group cũ sang group mới hoặc thực hiện cơ chế tương đương.
2. **Tạo subscriber độc lập từ đầu**: group mới có offset riêng và cần quyết định đọc lại lịch sử hay chỉ đọc dữ liệu mới.
3. **Replay dữ liệu để tái tạo read model**: group mới thường bắt đầu từ earliest còn được giữ hoặc từ timestamp/offset được chọn; output phải được cô lập hoặc ghi đè an toàn.

Không dùng cùng một cách cho cả ba trường hợp.

### 7.2 Ghi nhận trạng thái group cũ

Trước khi dừng group cũ:

- Ghi lại group id, topic, partition và committed offset.
- Ghi lại lag và log end offset tại thời điểm snapshot.
- Xác định partition nào đang được gán cho consumer.
- Kiểm tra retention để biết dữ liệu cũ còn có thể đọc hay không.
- Xác nhận consumer không còn xử lý dở dang hoặc side effect chưa commit.

Có thể dùng công cụ Kafka để xem trạng thái group:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server kafka.example:9092   --describe   --group orders-projection-prod
~~~

Lệnh describe giúp xem committed offset, log end offset, lag và thông tin member tùy phiên bản Kafka. Chọn đúng cluster và đúng group trước khi thao tác.

### 7.3 Chọn vị trí bắt đầu cho group mới

Nếu đổi tên nhưng muốn tiếp tục từ vị trí cũ, cần chuyển committed offset theo từng topic-partition. Có thể dùng Kafka AdminClient hoặc công cụ quản trị phù hợp để ghi offset cho group mới.

Offset được commit biểu thị vị trí tiếp theo consumer sẽ đọc, không phải offset cuối cùng đã xử lý theo cách cộng thêm tùy ý. Khi sao chép offset, phải giữ đúng semantics của committed offset và mapping partition.

Nếu muốn replay, hãy chọn earliest, timestamp hoặc offset cụ thể theo kế hoạch. Đảm bảo dữ liệu còn trong retention và xác định side effect có thể được chạy lại hay không.

### 7.4 Dừng consumer và thực hiện migration

Một quy trình thận trọng:

1. Đóng băng thay đổi cấu hình group id trong lúc migration.
2. Dừng consumer group cũ hoặc bảo đảm nó không còn xử lý khi thao tác offset yêu cầu group inactive.
3. Snapshot committed offset và trạng thái partition.
4. Tạo group id mới trong cấu hình.
5. Chuyển offset theo từng partition nếu mục tiêu là tiếp tục tại vị trí cũ.
6. Kiểm tra offset mới đã được ghi chính xác.
7. Khởi động một canary consumer với group mới.
8. Xác nhận assignment, record đầu tiên được đọc, lag và side effect.
9. Mở rộng số replica sau khi canary ổn định.
10. Chỉ xóa hoặc ngừng quản lý group cũ khi đã qua thời gian rollback và xác nhận không còn consumer sử dụng.

Nếu dùng công cụ reset offset, đọc kỹ chế độ dry-run và chỉ execute sau khi xác minh group, topic và partition. Không reset offset của group đang hoạt động khi chưa hiểu hành vi rebalance và điều kiện tool yêu cầu.

### 7.5 Rollback migration

Nếu group mới hoạt động sai, quay lại group cũ có thể làm record được xử lý lại vì group cũ có offset riêng và có thể đã dừng ở vị trí trước đó. Cần so sánh offset của cả hai group, xác định side effect đã xảy ra và dùng idempotency hoặc reconciliation để tránh duplicate.

Không xóa group cũ ngay sau cutover. Giữ runbook rollback và bằng chứng offset cho đến khi migration được xác nhận hoàn tất.

## 8. Quan sát group id và phát hiện thay đổi bất thường

Group id thay đổi có thể không tạo exception. Cần giám sát danh tính group cùng với lag và assignment.

### 8.1 Theo dõi danh sách group

Theo dõi số lượng consumer group theo cluster và namespace ứng dụng. Một đợt tăng đột biến số group có thể chỉ ra:

- Group id đang chứa pod name hoặc UUID.
- Release mới tạo group id mới.
- Một profile hoặc biến môi trường bị ghi đè.
- Service khởi động lại với cấu hình khác.
- Một consumer migration đã tạo group nhưng chưa có kế hoạch cleanup.

Không phải mọi group mới đều là lỗi. Cần so sánh với danh sách subscription được quản lý và owner của từng group.

### 8.2 Theo dõi offset và lag theo group

Consumer lag phải được xem theo group id. Khi group id đổi, dashboard cũ có thể tiếp tục hiển thị group cũ trong khi group mới xuất hiện với offset trống hoặc lag khác.

Theo dõi:

- Group id dự kiến và group id thực tế.
- Số member theo group.
- Partition assignment.
- Committed offset theo topic-partition.
- Log end offset và lag.
- Consumer restart và rebalance count.
- Số record xử lý và side effect theo business key.
- Group không có member nhưng còn offset hoặc lag.

Cảnh báo khi một service tạo group id ngoài danh sách cho phép hoặc khi group id thực tế thay đổi giữa các lần deploy mà không có migration ticket.

### 8.3 Log group id lúc khởi động

Ghi rõ group id hiệu lực cùng service name, environment và client id trong log startup. Không log secret hoặc thông tin nhạy cảm trong cùng dòng.

Ví dụ log dễ điều tra:

~~~text
service=orders-projection
environment=prod
consumerGroup=orders-projection-prod
clientId=orders-projection-pod-7f8c
topics=orders
~~~

Khi deploy, so sánh giá trị này với cấu hình dự kiến. Nếu annotation override group id, log từ file YAML không đủ; cần kiểm tra consumer config được tạo cho listener thực tế.

### 8.4 Kiểm tra runtime config

Khi nghi group id bị đổi:

1. Đọc giá trị property sau khi Spring Boot nạp profile và external configuration.
2. Kiểm tra ConsumerFactory properties.
3. Kiểm tra annotation @KafkaListener, đặc biệt groupId, id và idIsGroup.
4. Kiểm tra listener container đang dùng factory nào.
5. Xem log consumer config lúc khởi động.
6. Dùng công cụ Kafka liệt kê và mô tả group trên đúng cluster.
7. Đối chiếu deployment revision và biến môi trường của pod.

Không chỉ sửa YAML rồi giả định vấn đề đã hết. Nếu annotation hoặc factory đang override, giá trị runtime sẽ không đổi.

## 9. Các tình huống sai cấu hình và cách xử lý

| Tình huống | Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|---|
| Group id chứa pod name | Mỗi pod có một group; mỗi pod xử lý toàn bộ stream | Dùng HOSTNAME hoặc pod UID làm group id | Dùng group id ổn định chung cho các replica |
| Group id chứa version | Sau mỗi release xuất hiện group mới | Gắn APP_VERSION/build number vào group id | Dùng logical subscription id ổn định; chỉ version hóa khi migration chủ đích |
| Hai service dùng cùng group | Mỗi service chỉ nhận một phần partition | Copy nhầm group id | Tách group theo logical subscription |
| Dev và prod dùng cùng group trên một cluster | Member cross-environment, rebalance bất thường | Thiếu environment trong group id | Tách group theo môi trường |
| Annotation override YAML | Thay application.yml nhưng group runtime không đổi | @KafkaListener có groupId hoặc idIsGroup | Kiểm tra listener metadata và cấu hình annotation |
| Group mới với earliest | Record cũ được xử lý lại | Group không có committed offset | Chuyển offset có kiểm soát hoặc chuẩn bị replay/idempotency |
| Group mới với latest | Backlog hiện có không được đọc | auto.offset.reset=latest | Chọn offset theo yêu cầu nghiệp vụ trước khi chạy |
| Nhiều ConsumerFactory | Một listener dùng group khác dự kiến | Factory có group.id riêng | Lập bản đồ factory và listener |
| Static member id bị trùng | Member bị fencing hoặc rời group | Nhiều instance dùng cùng group.instance.id | Cấp member id duy nhất cho từng instance |

## 10. Các ví dụ cấu hình nên tránh và cách sửa

### 10.1 Không dùng hostname làm group id

Cấu hình không phù hợp:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: ${HOSTNAME}
~~~

Cấu hình ổn định hơn:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

Mọi replica của orders-projection trong production dùng cùng giá trị. Pod identity có thể được dùng cho client.id nếu cần phân biệt metrics.

### 10.2 Không gắn build version vào group id

Cấu hình không phù hợp:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-${BUILD_NUMBER}
~~~

Cấu hình ổn định:

~~~yaml
app:
  kafka:
    consumer:
      group-id: orders-projection-prod
~~~

Nếu cần chạy consumer mới song song để kiểm chứng, tạo group id riêng có tên migration rõ ràng, dùng output riêng và có ngày kết thúc.

### 10.3 Khai báo rõ listener id và group id

Cấu hình rõ ràng:

~~~java
@KafkaListener(
    id = "ordersProjectionContainer",
    idIsGroup = false,
    groupId = "${app.kafka.consumer.group-id}",
    topics = "${app.kafka.consumer.topic}"
)
public void handle(OrderCreated event) {
    projectionService.apply(event);
}
~~~

Cách này giúp tách container identity khỏi consumer group identity. Đảm bảo placeholder được resolve thành cùng giá trị trên mọi replica trong một môi trường.

## 11. Những hiểu nhầm cần tránh

**“Mỗi pod phải có group id riêng để Kafka phân biệt consumer.”** Sai. Kafka phân biệt member trong group bằng member identity; group id phải giống nhau giữa các replica muốn chia partition và offset.

**“Đổi group id chỉ đổi tên hiển thị.”** Sai. Nó tạo một consumer group khác với offset state độc lập.

**“Group mới tự kế thừa offset cũ.”** Sai. Kafka không tự chuyển committed offset giữa hai group id.

**“auto.offset.reset=earliest luôn đọc được toàn bộ lịch sử.”** Sai. Earliest chỉ là offset sớm nhất còn có thể đọc trong log theo retention/compaction; record đã bị xóa không thể replay từ Kafka.

**“auto.offset.reset=latest sẽ nhảy group cũ về cuối.”** Sai. Nó áp dụng khi group không có offset hợp lệ, không phải reset offset hợp lệ đang tồn tại.

**“client.id và group.id có thể thay thế cho nhau.”** Sai. client.id phục vụ nhận diện client/metrics; group.id điều khiển membership và offset.

**“Dùng chung group id cho các service giúp tiết kiệm tài nguyên.”** Sai nếu các service cần nhận toàn bộ stream độc lập. Chúng sẽ chia partition và mỗi service chỉ nhận một phần dữ liệu.

**“Đưa version vào group id giúp deploy an toàn.”** Không tự động. Nó tạo subscription mới, có thể khiến hai phiên bản cùng xử lý toàn bộ dữ liệu và tạo duplicate.

**“Xem application.yml là biết group id runtime.”** Sai. Environment, profile, ConsumerFactory và annotation có thể ghi đè giá trị.

## 12. Quy trình xử lý khi phát hiện group id bất ngờ thay đổi

Khi dashboard xuất hiện group mới hoặc consumer bắt đầu replay/skip record, xử lý theo thứ tự:

1. Ghi nhận group id đang chạy trong từng pod và thời điểm bắt đầu thay đổi.
2. Xác định pod thuộc cùng service, cùng môi trường và cùng release hay không.
3. So sánh group id thực tế với giá trị trong application properties và deployment environment.
4. Kiểm tra annotation groupId, idIsGroup, container id và ConsumerFactory.
5. Dùng công cụ Kafka mô tả group cũ và mới: member, partition, committed offset, log end offset và lag.
6. Xác định group mới đang dùng earliest, latest hay none khi chưa có offset.
7. Kiểm tra side effect đã xảy ra: record nào bị replay, record nào có thể bị bỏ qua, downstream nào bị ảnh hưởng.
8. Nếu là lỗi cấu hình, dừng rollout hoặc sửa nguồn cấu hình để khôi phục group id dự kiến.
9. Nếu group mới đã xử lý dữ liệu, đối chiếu event id/business key trước khi chuyển lại để tránh duplicate.
10. Xác nhận sau phục hồi chỉ còn các group mong muốn, assignment đúng và lag tiến triển bình thường.

Không xóa group mới ngay khi phát hiện. Trước tiên xác định nó đã xử lý record nào và offset đã tiến đến đâu. Xóa group hoặc reset offset mà không có snapshot có thể làm mất bằng chứng điều tra và tăng rủi ro replay.

## 13. Kiểm thử tính ổn định của group id

Có thể kiểm tra cấu hình trong môi trường tích hợp hoặc staging:

- Khởi chạy hai replica cùng service và xác nhận chúng tham gia cùng một group id.
- Scale replica lên rồi xuống; xác nhận group id giữ nguyên và offset tiếp tục.
- Restart pod; xác nhận member mới quay lại cùng group thay vì tạo group mới.
- Thực hiện rolling deployment; xác nhận phiên bản cũ và mới cùng tham gia group dự kiến.
- Thay đổi profile hoặc biến môi trường thử nghiệm; xác nhận group id hiệu lực đúng giá trị được phê duyệt.
- Tạo hai logical subscription cần đọc độc lập; xác nhận chúng có group id khác nhau và mỗi group nhận toàn bộ stream.
- Thử migration group id trong staging; xác nhận offset được chuyển đúng hoặc replay bắt đầu đúng mốc đã chọn.
- Kiểm tra side effect idempotency khi group mới replay record.

Tiêu chí thành công cần cụ thể: số group dự kiến không tăng sau restart/scale; mọi replica của cùng subscription dùng cùng group; committed offset tiếp tục tăng; không có duplicate side effect ngoài chính sách; và group mới chỉ xuất hiện khi có migration được ghi nhận.

## 14. Checklist thiết kế và vận hành

**Danh tính group**

- [ ] Mỗi group id đại diện cho một logical subscription có owner.
- [ ] Các replica của cùng subscription dùng chung group id.
- [ ] Các service cần đọc độc lập dùng group id riêng.
- [ ] Môi trường được tách biệt khi dùng chung Kafka cluster.
- [ ] Group id không chứa pod name, hostname, UUID, timestamp, build number hoặc version ngoài kế hoạch migration.

**Spring configuration**

- [ ] Nguồn group id chính được xác định rõ.
- [ ] application.yml/profile/environment không ghi đè ngoài ý muốn.
- [ ] @KafkaListener groupId được kiểm tra.
- [ ] id và idIsGroup được hiểu đúng theo phiên bản Spring Kafka.
- [ ] ConsumerFactory và listener container factory được ánh xạ rõ.
- [ ] Group id runtime được log lúc khởi động và đối chiếu với giá trị dự kiến.

**Offset và migration**

- [ ] auto.offset.reset được hiểu đúng cho group chưa có offset hợp lệ.
- [ ] Đổi group id có kế hoạch replay hoặc chuyển offset theo partition.
- [ ] Offset cũ được snapshot trước migration.
- [ ] Group cũ được giữ đủ lâu cho rollback.
- [ ] Consumer side effect có idempotency hoặc reconciliation khi có replay.

**Quan sát và kiểm thử**

- [ ] Có danh sách group id được phép theo service/environment.
- [ ] Theo dõi số group, member, assignment, committed offset và lag.
- [ ] Cảnh báo khi group id ngoài dự kiến xuất hiện.
- [ ] Đã kiểm thử restart, scale, rolling deploy và migration group trong staging.
- [ ] Có runbook điều tra replay, skip backlog và duplicate side effect.

Group id là một phần của trạng thái vận hành của consumer, vì nó quyết định membership, partition assignment và offset namespace. Giữ group id ổn định qua restart, scale và release giúp consumer tiếp tục đúng tiến độ đã commit. Khi cần đổi group id, hãy coi đó là một migration dữ liệu: xác định mốc đọc, bảo toàn offset, kiểm soát side effect và xác minh group mới trước khi chuyển toàn bộ tải.

