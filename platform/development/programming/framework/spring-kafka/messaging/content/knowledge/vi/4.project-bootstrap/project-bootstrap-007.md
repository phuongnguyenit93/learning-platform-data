# Cấu hình Kafka chạy ở chế độ KRaft

## Mục tiêu của bài học

Trong chương **Khởi tạo dự án**, bài này hướng dẫn cấu hình Apache Kafka ở chế độ KRaft (Kafka Raft Metadata mode), từ một node phục vụ phát triển cục bộ đến kiến trúc nhiều broker và controller cho môi trường production.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Kafka KRaft là nền tảng hạ tầng mà ứng dụng sử dụng để lưu trữ và phân phối các bản ghi.

Sau bài học, người học có thể:

- Giải thích KRaft thay đổi cách Kafka quản lý metadata và vai trò controller như thế nào.
- Phân biệt broker, controller và node kết hợp broker/controller.
- Cấu hình process role, node id, listener, địa chỉ quảng bá và controller quorum.
- Khởi tạo storage bằng cluster ID và lệnh format phù hợp.
- Khởi động, kiểm tra cluster và tạo topic.
- Kết nối ứng dụng Spring Kafka tới broker KRaft.
- Nhận diện các khác biệt giữa cấu hình development và production, cũng như các lỗi cấu hình thường gặp.

## 1. KRaft là gì?

KRaft là chế độ Kafka sử dụng giao thức đồng thuận Raft để quản lý metadata của cluster. Metadata bao gồm thông tin về broker, topic, partition, replica, cấu hình và các thay đổi quản trị liên quan.

Trong kiến trúc Kafka trước đây, ZooKeeper được dùng để lưu và phối hợp metadata của cluster. Với KRaft, Kafka đưa chức năng quản lý metadata vào chính hệ thống Kafka thông qua một nhóm controller. Vì vậy, cluster KRaft không cần một cụm ZooKeeper riêng.

KRaft không thay đổi cách ứng dụng producer và consumer gửi, nhận bản ghi qua Kafka protocol. Ứng dụng Spring vẫn kết nối tới địa chỉ bootstrap của broker như thông thường. Thay đổi chủ yếu nằm ở kiến trúc quản lý cluster, khởi tạo storage và vận hành controller.

~~~mermaid
flowchart TB
    subgraph APP["Ứng dụng"]
        P["Producer / KafkaTemplate"]
        C["Consumer / @KafkaListener"]
    end
    subgraph KAFKA["Kafka cluster chạy KRaft"]
        B1["Broker 1"]
        B2["Broker 2"]
        B3["Broker 3"]
        Q["Controller quorum"]
        B1 --- Q
        B2 --- Q
        B3 --- Q
    end
    P --> B1
    C --> B2
    Q --> B1
    Q --> B2
    Q --> B3
~~~

Controller quản lý metadata và điều phối các thay đổi của cluster. Broker tiếp nhận request từ producer/consumer, lưu trữ log partition và phục vụ việc đọc bản ghi. Các broker trao đổi metadata với controller thông qua controller listener.

### 1.1. KRaft mang lại điều gì?

- Giảm thành phần hạ tầng phải triển khai và vận hành vì không cần ZooKeeper.
- Quản lý metadata bằng cơ chế quorum controller dựa trên Raft.
- Tách rõ trách nhiệm điều phối metadata và phục vụ dữ liệu.
- Hỗ trợ mở rộng và phục hồi metadata theo mô hình controller quorum.
- Giúp kiến trúc Kafka tiến tới một hệ thống tự quản lý hơn.

KRaft không tự động bảo đảm cluster có tính sẵn sàng cao. Số lượng controller, replication của dữ liệu, cấu hình listener, lưu trữ bền vững, mạng và quy trình vận hành vẫn quyết định độ tin cậy của hệ thống.

## 2. Phân biệt broker và controller

### 2.1. Broker

Broker là node phục vụ dữ liệu Kafka. Nó nhận bản ghi từ producer, lưu bản ghi vào partition log, phục vụ consumer đọc dữ liệu và tham gia replication giữa các broker.

Các trách nhiệm thường gặp:

- Tiếp nhận kết nối từ producer và consumer.
- Lưu trữ các partition replica trên ổ đĩa.
- Phối hợp replication, leader và follower.
- Phục vụ request đọc/ghi và request quản trị.
- Báo cáo trạng thái broker và metadata cho controller.

### 2.2. Controller

Controller là node tham gia quản lý metadata của cluster. Nhóm controller tạo thành quorum và sử dụng Raft để thống nhất các thay đổi metadata.

Các trách nhiệm chính:

- Quản lý trạng thái metadata của cluster.
- Điều phối thay đổi broker membership.
- Quản lý thay đổi topic, partition và cấu hình liên quan.
- Phối hợp các thay đổi leader và trạng thái replica.
- Phân phối metadata cần thiết cho broker.

Trong một quorum, một controller giữ vai trò leader và các controller còn lại theo dõi log metadata, sẵn sàng tham gia bầu chọn khi cần. Quorum chỉ có thể tiến hành các thay đổi cần đồng thuận khi có đủ thành viên hoạt động theo ngưỡng majority.

### 2.3. Node kết hợp broker và controller

Kafka cho phép một node có cả hai role:

~~~properties
process.roles=broker,controller
~~~

Cách kết hợp này thuận tiện cho môi trường development hoặc thử nghiệm một node. Nó giúp chạy Kafka với ít thành phần hơn, nhưng broker và controller cùng chia sẻ tài nguyên CPU, memory, mạng và storage.

Trong production, thường nên tách controller chuyên dụng khỏi broker để tải phục vụ dữ liệu không ảnh hưởng trực tiếp đến khả năng duy trì quorum metadata. Quyết định triển khai cần dựa trên hướng dẫn của phiên bản Kafka, quy mô cluster và yêu cầu sẵn sàng.

## 3. Các thuộc tính cấu hình KRaft quan trọng

Một file cấu hình Kafka KRaft thường có các nhóm thuộc tính sau.

| Thuộc tính | Ý nghĩa |
|---|---|
| `process.roles` | Các role mà node đảm nhiệm: `broker`, `controller` hoặc cả hai |
| `node.id` | ID duy nhất của node trong cluster |
| `controller.quorum.voters` | Danh sách controller voter trong cấu hình quorum tĩnh |
| `controller.quorum.bootstrap.servers` | Địa chỉ bootstrap controller trong các phiên bản hỗ trợ dynamic quorum |
| `listeners` | Các endpoint mà tiến trình Kafka bind để nhận kết nối |
| `advertised.listeners` | Địa chỉ node công bố cho client hoặc broker khác kết nối |
| `controller.listener.names` | Tên listener dùng cho giao tiếp controller |
| `inter.broker.listener.name` | Listener dùng cho giao tiếp giữa các broker |
| `listener.security.protocol.map` | Ánh xạ tên listener tùy chỉnh sang protocol bảo mật |
| `log.dirs` | Thư mục lưu partition log |
| `metadata.log.dir` | Thư mục riêng lưu metadata log của KRaft nếu được cấu hình |

### 3.1. process.roles

Giá trị của `process.roles` xác định node tham gia vào hệ thống với vai trò nào:

- `broker`: node phục vụ dữ liệu.
- `controller`: node quản lý metadata và tham gia quorum.
- `broker,controller`: node kết hợp cả hai vai trò.

Một node controller-only không nhận request dữ liệu từ producer/consumer. Một node broker-only không tham gia bầu chọn controller, nhưng vẫn cần kết nối tới controller quorum để nhận metadata.

### 3.2. node.id

`node.id` là định danh duy nhất của từng Kafka node. Giá trị này phải nhất quán với định danh được khai báo trong cấu hình quorum nếu node là controller voter.

Ví dụ:

~~~properties
node.id=1
~~~

Không dùng cùng node ID cho hai node đang hoạt động trong một cluster. Khi thay thế node, cần tuân theo quy trình vận hành và membership của cluster thay vì tùy ý sao chép cấu hình hoặc storage.

### 3.3. Controller quorum

Với cấu hình quorum tĩnh, thuộc tính `controller.quorum.voters` liệt kê các controller voter theo dạng:

~~~properties
controller.quorum.voters=1@controller-1:9093,2@controller-2:9093,3@controller-3:9093
~~~

Mỗi phần tử có dạng `node-id@host:port`. Node ID phải trùng với `node.id` của controller tương ứng; host và port phải trỏ tới controller listener có thể truy cập được.

Một quorum gồm 3 voter cần tối thiểu 2 voter hoạt động để đạt majority. Quorum 5 voter cần tối thiểu 3 voter. Vì thế, triển khai production thường dùng số controller lẻ như 3 hoặc 5 để cân bằng khả năng chịu lỗi và chi phí vận hành.

**Lưu ý về phiên bản:** Kafka có các phiên bản hỗ trợ dynamic controller quorum, sử dụng `controller.quorum.bootstrap.servers` và quy trình bootstrap storage tương ứng. Không trộn cấu hình quorum tĩnh và động một cách tùy ý. Hãy dùng đúng cấu hình, lệnh format và quy trình membership theo phiên bản Kafka đang triển khai. Các ví dụ `controller.quorum.voters` trong bài này minh họa mô hình quorum tĩnh.

### 3.4. Listener và địa chỉ quảng bá

Kafka có thể sử dụng nhiều listener cho các mục đích khác nhau:

- Client listener nhận kết nối từ producer và consumer.
- Inter-broker listener phục vụ giao tiếp giữa các broker.
- Controller listener phục vụ giao tiếp giữa broker và controller quorum.

`listeners` xác định địa chỉ bind trên node. `advertised.listeners` xác định địa chỉ Kafka công bố cho client hoặc broker khác. Hai giá trị này có thể khác nhau, đặc biệt khi chạy Kafka trong container hoặc sau NAT.

Không nên quảng bá địa chỉ controller listener như endpoint ứng dụng. Producer và consumer chỉ cần bootstrap tới broker listener; controller listener nên nằm trong mạng nội bộ dành cho các thành phần Kafka.

## 4. Cấu hình KRaft một node cho development

Để học và phát triển ứng dụng Spring Kafka, có thể bắt đầu với một node kết hợp broker/controller. Cấu hình sau dùng quorum tĩnh một voter và listener PLAINTEXT trên máy local.

Tạo file `config/kraft/server.properties`:

~~~properties
# Node identity and roles
process.roles=broker,controller
node.id=1

# Static controller quorum: one node for local development
controller.quorum.voters=1@localhost:9093

# Network listeners
listeners=PLAINTEXT://:9092,CONTROLLER://:9093
advertised.listeners=PLAINTEXT://localhost:9092
listener.security.protocol.map=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT

# Controller and inter-broker communication
controller.listener.names=CONTROLLER
inter.broker.listener.name=PLAINTEXT

# Storage
log.dirs=/tmp/kraft-combined-logs

# Single-node development settings
num.partitions=3
default.replication.factor=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0

# Explicitly manage topics during learning
auto.create.topics.enable=false
~~~

Giải thích các điểm chính:

- `process.roles=broker,controller` cho phép node vừa phục vụ dữ liệu vừa quản lý metadata.
- `node.id=1` đặt định danh node.
- `controller.quorum.voters=1@localhost:9093` khai báo chính node này là controller voter duy nhất.
- `listeners` mở broker listener ở cổng 9092 và controller listener ở cổng 9093.
- `advertised.listeners` công bố địa chỉ broker cho ứng dụng chạy trên cùng máy.
- `controller.listener.names` chỉ định listener cho controller protocol.
- `inter.broker.listener.name` chỉ định listener cho giao tiếp giữa broker.
- `log.dirs` xác định nơi lưu partition log.
- Các replication factor bằng 1 chỉ phù hợp cho cluster một node. Chúng không cung cấp khả năng chịu lỗi khi node dừng.

Đây là cấu hình development. Không dùng PLAINTEXT, replication factor 1 hoặc một controller duy nhất làm cấu hình production.

## 5. Tạo cluster ID và format storage

KRaft lưu metadata trong storage của Kafka. Trước khi khởi động node lần đầu, cần tạo cluster ID và format các thư mục storage theo cấu hình node.

### 5.1. Tạo cluster ID

Dùng công cụ `kafka-storage` đi kèm bản phân phối Kafka:

~~~bash
bin/kafka-storage.sh random-uuid
~~~

Lệnh trả về một UUID. Ghi lại giá trị này để dùng cho cluster.

Cluster ID xác định danh tính cluster. Tất cả node thuộc cùng cluster phải được format với cùng cluster ID. Mỗi node vẫn có `node.id` riêng.

### 5.2. Format storage lần đầu

Với ví dụ quorum tĩnh ở trên:

~~~bash
bin/kafka-storage.sh format \
  -t <CLUSTER_ID> \
  -c config/kraft/server.properties
~~~

Thay `<CLUSTER_ID>` bằng UUID vừa tạo. Lệnh format khởi tạo metadata cần thiết trong các thư mục storage được cấu hình.

Một số lưu ý quan trọng:

- Format storage trước khi khởi động Kafka lần đầu trên node mới.
- Dùng cùng cluster ID cho các node trong cùng cluster.
- Dùng node ID riêng cho mỗi node.
- Mỗi node phải format storage của chính nó với file cấu hình tương ứng.
- Không chạy format mỗi lần restart.
- Không xóa hoặc format lại thư mục chứa dữ liệu đang hoạt động để xử lý lỗi khởi động thông thường.
- Với dynamic quorum, dùng quy trình bootstrap và tham số format dành riêng cho phiên bản đó; không sao chép nguyên lệnh quorum tĩnh.

Có thể kiểm tra thông tin storage bằng:

~~~bash
bin/kafka-storage.sh info \
  -c config/kraft/server.properties
~~~

### 5.3. Khởi động Kafka

Sau khi format thành công:

~~~bash
bin/kafka-server-start.sh config/kraft/server.properties
~~~

Kafka sẽ khởi động broker và controller trong cùng tiến trình. Theo dõi log để xác nhận node đã khởi động, controller quorum đã hình thành và broker listener sẵn sàng nhận kết nối.

Nếu dùng Windows, bản phân phối Kafka cung cấp các script tương ứng trong `bin\windows`, ví dụ:

~~~powershell
.\bin\windows\kafka-storage.bat random-uuid
.\bin\windows\kafka-storage.bat format -t <CLUSTER_ID> -c .\config\kraft\server.properties
.\bin\windows\kafka-server-start.bat .\config\kraft\server.properties
~~~

Tên script và tham số cần đối chiếu với bản Kafka đang cài đặt. Không chạy đồng thời nhiều lệnh format trên cùng một thư mục storage.

## 6. Kiểm tra cluster KRaft sau khi khởi động

Khởi động thành công một process chưa đủ để kết luận cluster hoạt động đúng. Cần kiểm tra controller quorum, broker listener và thao tác quản trị topic.

### 6.1. Kiểm tra controller quorum

Dùng công cụ metadata quorum:

~~~bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller localhost:9093 \
  describe --status
~~~

Ở cluster một node, cần xác nhận controller đã hình thành quorum và có leader. Với cluster nhiều controller, kiểm tra leader, voter và trạng thái đồng bộ metadata theo công cụ của phiên bản đang dùng.

### 6.2. Kiểm tra broker có nhận kết nối

~~~bash
bin/kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092
~~~

Lệnh này kiểm tra khả năng kết nối tới broker listener và hiển thị các API version broker hỗ trợ.

### 6.3. Tạo và mô tả topic

Tạo topic phục vụ ví dụ Spring Kafka:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.created \
  --partitions 3 \
  --replication-factor 1
~~~

Liệt kê topic:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Mô tả topic:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.created
~~~

Với cluster một broker, replication factor phải bằng 1. Nếu yêu cầu replication factor lớn hơn số broker có sẵn, lệnh tạo topic sẽ thất bại.

### 6.4. Thử gửi và đọc bản ghi

Gửi một bản ghi bằng console producer:

~~~bash
bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created
~~~

Nhập một dòng văn bản rồi kết thúc input. Ở terminal khác, chạy console consumer:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created \
  --from-beginning
~~~

Nếu consumer nhận được bản ghi, broker listener đang phục vụ được luồng publish/consume cơ bản. Đây là kiểm tra hạ tầng Kafka; kiểm thử tích hợp Spring Kafka sẽ được thực hiện ở cấp ứng dụng.

## 7. Kết nối ứng dụng Spring Kafka tới cluster KRaft

Ứng dụng Spring Kafka không cần biết controller quorum hoạt động ra sao. Nó kết nối tới broker thông qua bootstrap server.

Ví dụ cấu hình trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

Một producer đơn giản:

~~~java
@Service
public class EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public EventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.created", orderId, payload);
    }
}
~~~

Một consumer đơn giản:

~~~java
@Service
public class EventListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void receive(String payload) {
        // Xử lý event trong nghiệp vụ billing.
    }
}
~~~

Các điểm cần nhớ:

- `spring.kafka.bootstrap-servers` trỏ tới broker listener, không phải controller listener.
- Ứng dụng không kết nối trực tiếp tới controller quorum để gửi hoặc nhận bản ghi.
- Serializer và deserializer phải tương thích với định dạng dữ liệu hai phía.
- Group ID xác định nhóm consumer và cách Kafka phân phối partition.
- Khi chuyển từ cluster development sang production, thay địa chỉ bootstrap, bảo mật và các thuộc tính client tương ứng.

## 8. Chạy KRaft trong Docker và phân biệt địa chỉ mạng

Khi chạy Kafka trong Docker, địa chỉ `localhost` bên trong container là chính container đó. Một ứng dụng chạy trên máy host và một ứng dụng chạy trong Docker network có thể cần hai địa chỉ broker khác nhau.

Một cấu hình nhiều listener thường có ý tưởng như sau:

~~~properties
listeners=INTERNAL://:9092,EXTERNAL://:29092,CONTROLLER://:9093
advertised.listeners=INTERNAL://kafka:9092,EXTERNAL://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

Trong ví dụ này:

- Container ứng dụng trong cùng Docker network kết nối tới `kafka:9092`.
- Ứng dụng chạy trên máy host kết nối tới `localhost:29092`.
- Controller listener dùng cổng 9093 cho giao tiếp nội bộ của Kafka.
- Tên host `kafka` phải phân giải được trong Docker network.
- Cổng external phải được publish ra host nếu cần ứng dụng ngoài Docker truy cập.

Đây là phần cấu hình listener minh họa; vẫn phải kết hợp `process.roles`, `node.id`, quorum, storage và các thuộc tính replication phù hợp. Biến môi trường và cách format storage phụ thuộc Docker image Kafka được chọn. Không nên giả định tên biến của image này áp dụng cho image khác.

### 8.1. Những lỗi địa chỉ thường gặp

- Ứng dụng trong container kết nối `localhost:9092` nhưng Kafka chạy ở container khác: `localhost` trỏ nhầm về container ứng dụng.
- Kafka quảng bá `localhost:9092` cho client trong Docker network: client nhận địa chỉ không thể truy cập từ container của nó.
- Ứng dụng dùng cổng controller 9093 làm bootstrap server: đây không phải broker client listener.
- Listener bind đúng nhưng `advertised.listeners` sai: kết nối bootstrap có thể thành công nhưng client thất bại khi kết nối tới broker được metadata trả về.

## 9. Kiến trúc KRaft nhiều node cho production

Một cluster production thường tách controller và broker thành các nhóm node riêng.

Ví dụ kiến trúc:

~~~mermaid
flowchart TB
    subgraph CTRL["Controller quorum - 3 nodes"]
        C1["Controller 1"]
        C2["Controller 2"]
        C3["Controller 3"]
        C1 --- C2
        C2 --- C3
        C3 --- C1
    end
    subgraph BR["Broker pool"]
        B1["Broker 1"]
        B2["Broker 2"]
        B3["Broker 3"]
    end
    APP["Spring applications"] --> B1
    APP --> B2
    APP --> B3
    B1 --> C1
    B2 --> C2
    B3 --> C3
~~~

### 9.1. Controller-only node

Ví dụ một controller trong quorum tĩnh ba node:

~~~properties
process.roles=controller
node.id=100

listeners=CONTROLLER://controller-1.internal:9093
controller.listener.names=CONTROLLER
controller.quorum.voters=100@controller-1.internal:9093,101@controller-2.internal:9093,102@controller-3.internal:9093

listener.security.protocol.map=CONTROLLER:SSL
metadata.log.dir=/var/lib/kafka/controller-metadata
~~~

Các controller khác dùng node ID và địa chỉ riêng, nhưng khai báo cùng danh sách quorum voter. Controller listener phải phân giải được và cho phép các thành viên quorum giao tiếp.

### 9.2. Broker-only node

Ví dụ một broker:

~~~properties
process.roles=broker
node.id=1

listeners=INTERNAL://broker-1.internal:9092
advertised.listeners=INTERNAL://broker-1.internal:9092
inter.broker.listener.name=INTERNAL

controller.listener.names=CONTROLLER
controller.quorum.voters=100@controller-1.internal:9093,101@controller-2.internal:9093,102@controller-3.internal:9093

listener.security.protocol.map=INTERNAL:SSL,CONTROLLER:SSL
log.dirs=/var/lib/kafka/data
~~~

Broker-only node không bind controller listener để nhận kết nối từ controller. Nó dùng cấu hình controller listener và địa chỉ quorum để kết nối tới controller. Các broker cần cùng cách cấu hình quorum và bảo mật phù hợp với cluster.

Đây là các ví dụ định hướng cho quorum tĩnh. Cấu hình TLS thực tế còn cần truststore, keystore, principal, ACL và các thuộc tính xác thực phù hợp. Cần kiểm tra yêu cầu của phiên bản Kafka và nền tảng triển khai trước khi sử dụng trực tiếp.

### 9.3. Replication và khả năng chịu lỗi

Cluster production cần có đủ broker để đặt replica cho partition. Ví dụ phổ biến là replication factor 3, với `min.insync.replicas=2` cho topic hoặc broker theo yêu cầu ghi.

Controller quorum và partition replication giải quyết hai loại trạng thái khác nhau:

- Controller quorum bảo đảm khả năng thống nhất metadata.
- Partition replication bảo vệ bản ghi khi broker gặp sự cố.

Có 3 controller không có nghĩa dữ liệu topic tự động có 3 replica. Cần cấu hình replication factor, min ISR, rack awareness và phân phối replica riêng.

## 10. Storage và vòng đời cluster

### 10.1. Phân biệt cluster ID, node ID và directory

| Định danh | Phạm vi | Mục đích |
|---|---|---|
| Cluster ID | Toàn cluster | Nhận diện một Kafka cluster |
| Node ID | Từng node | Nhận diện broker/controller trong cluster |
| Directory ID | Từng storage directory trong các quy trình hỗ trợ | Nhận diện thư mục lưu trữ của node |

Cluster ID phải thống nhất giữa các node trong cùng cluster. Node ID phải duy nhất. Không dùng cluster ID thay cho node ID và không tự tạo cluster ID mới khi chỉ restart một node.

### 10.2. Partition log và metadata log

Partition log chứa các bản ghi producer gửi tới topic. Metadata log lưu các thay đổi metadata mà controller quorum thống nhất.

Có thể cấu hình `log.dirs` để lưu partition data và `metadata.log.dir` để chỉ định riêng nơi lưu metadata log. Nếu không cấu hình metadata log directory riêng, vị trí mặc định phụ thuộc cấu hình storage của Kafka.

Các thư mục này cần dùng storage bền vững trong production. Nếu chạy container, phải mount volume phù hợp để dữ liệu không mất khi container bị thay thế.

### 10.3. Restart và thay thế node

Restart node với storage hiện có là thao tác vận hành thông thường. Kafka sử dụng metadata và dữ liệu đã lưu để khôi phục trạng thái.

Khi thay thế node, không nên chỉ sao chép nguyên thư mục storage từ node khác rồi đổi `node.id`. Cần thực hiện theo quy trình thay thế broker/controller của phiên bản Kafka, bảo đảm membership, directory identity, replica reassignment và quorum được xử lý đúng.

Không format lại storage đang chứa dữ liệu để giải quyết lỗi khởi động nếu chưa xác định nguyên nhân và phương án phục hồi. Format là thao tác khởi tạo storage, không phải lệnh reset an toàn.

## 11. Bảo mật listener và kết nối

Ví dụ development dùng PLAINTEXT để giảm cấu hình ban đầu. Production cần thiết kế bảo mật cho cả client listener, inter-broker listener và controller listener.

Các nội dung cần xem xét:

- TLS để mã hóa kết nối.
- SASL khi cần xác thực client hoặc node.
- ACL để giới hạn quyền đọc, ghi, tạo topic và quản trị.
- Tách mạng controller khỏi mạng truy cập client.
- Không công bố controller endpoint ra Internet hoặc mạng không tin cậy.
- Quản lý chứng thư, khóa và bí mật bằng secret manager.
- Kiểm tra hostname và certificate khi client dùng TLS.

Tên listener có thể ánh xạ sang `SSL` hoặc `SASL_SSL` thông qua `listener.security.protocol.map`. Mỗi listener cần được cấu hình credential và chính sách bảo mật tương ứng. Không nên chỉ đổi giá trị protocol mà bỏ qua truststore, keystore, SASL mechanism hoặc ACL cần thiết.

## 12. Kết nối KRaft với quy trình khởi tạo dự án Spring

Khi khởi tạo dự án Spring Kafka, có thể chia việc thành các bước:

1. Chọn phiên bản Kafka và xác định mô hình quorum phù hợp.
2. Chuẩn bị cấu hình broker/controller và địa chỉ listener.
3. Tạo cluster ID và format storage lần đầu.
4. Khởi động Kafka và xác minh controller quorum.
5. Tạo topic, partition và replication factor theo môi trường.
6. Cấu hình `spring.kafka.bootstrap-servers` cho ứng dụng.
7. Chọn serializer/deserializer và consumer group.
8. Chạy thử producer, consumer và kiểm thử tích hợp.
9. Thiết lập log, metric, cảnh báo và quy trình vận hành.

Spring Kafka là lớp tích hợp ở phía ứng dụng. Việc khởi tạo KRaft cluster thuộc trách nhiệm của nền tảng Kafka; hai phần kết nối với nhau qua broker listener và Kafka protocol.

## 13. Các lỗi KRaft thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Kafka không khởi động do thiếu cấu hình role | Thiếu hoặc sai `process.roles` | Kiểm tra role của node và phiên bản Kafka |
| Controller không hình thành quorum | Sai voter ID, hostname, port hoặc controller listener | So sánh `node.id`, quorum list và địa chỉ controller |
| Node báo cluster ID không khớp | Storage được format với cluster ID khác | Kiểm tra cluster ID của từng node và lịch sử format |
| Broker khởi động nhưng client không kết nối | Sai `listeners`, firewall hoặc port mapping | Kiểm tra endpoint bind và log broker |
| Bootstrap thành công nhưng request sau đó thất bại | `advertised.listeners` công bố host không truy cập được | Kiểm tra địa chỉ broker trả về cho client |
| Client kết nối nhầm controller port | Dùng controller listener làm bootstrap server | Dùng broker listener |
| Không tạo được topic với RF yêu cầu | Replication factor lớn hơn số broker phù hợp | Kiểm tra số broker và replication factor |
| Transaction topic không tạo được trên cluster một node | Transaction replication factor hoặc min ISR lớn hơn khả năng cluster | Dùng giá trị phù hợp cho development hoặc bổ sung broker |
| Docker client không phân giải được broker | Quảng bá hostname sai network | Dùng địa chỉ nội bộ cho container và địa chỉ external cho host |
| Restart làm mất dữ liệu | Storage không được giữ bằng persistent volume | Kiểm tra mount và quyền truy cập volume |

## 14. Checklist trước khi sử dụng

### Development

- [ ] Chọn đúng phiên bản Kafka và kiểu quorum được hỗ trợ.
- [ ] Khai báo `process.roles` và `node.id`.
- [ ] Cấu hình broker listener và controller listener riêng.
- [ ] Đặt `advertised.listeners` theo địa chỉ client thực sự truy cập được.
- [ ] Tạo một cluster ID và format storage lần đầu.
- [ ] Dùng replication factor 1 chỉ cho cluster một node.
- [ ] Xác nhận controller quorum và broker listener hoạt động.
- [ ] Tạo topic và thử gửi/nhận bản ghi.
- [ ] Kết nối Spring Kafka qua broker bootstrap server.

### Production

- [ ] Tách controller chuyên dụng và broker theo thiết kế cluster.
- [ ] Dùng quorum controller có số voter phù hợp, thường là 3 hoặc 5.
- [ ] Có cluster ID, node ID và storage identity rõ ràng cho từng node.
- [ ] Dùng storage bền vững và có quy trình phục hồi.
- [ ] Cấu hình replication factor, min ISR và rack awareness.
- [ ] Tách listener client, inter-broker và controller.
- [ ] Bật TLS/SASL và ACL theo yêu cầu bảo mật.
- [ ] Không công bố controller listener cho client ứng dụng.
- [ ] Giám sát quorum, broker, partition, replica và dung lượng storage.
- [ ] Có quy trình nâng cấp, thay thế node và phục hồi sự cố.

## Kết luận

KRaft đưa việc quản lý metadata và điều phối cluster vào hệ thống Kafka thông qua controller quorum dựa trên Raft. Mỗi node được cấu hình bằng role và node ID; listener xác định các endpoint cho client, broker và controller; storage được khởi tạo bằng cluster ID phù hợp với quy trình của phiên bản Kafka.

Đối với ứng dụng Spring Kafka, điểm kết nối vẫn là broker listener được công bố qua bootstrap server. Khi hiểu rõ ranh giới giữa controller, broker và ứng dụng, người học có thể khởi tạo môi trường development nhanh chóng, đồng thời biết những cấu hình cần thiết để tiến tới một cluster production có khả năng chịu lỗi, bảo mật và vận hành ổn định.
