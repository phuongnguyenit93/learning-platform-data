# bootstrap servers và cơ chế khám phá broker

Một ứng dụng Spring Kafka cần biết địa chỉ để bắt đầu kết nối tới Kafka cluster. Thuộc tính **bootstrap.servers** cung cấp danh sách các địa chỉ broker ban đầu mà Kafka client có thể liên hệ. Sau khi kết nối được một broker, client lấy metadata của cluster để biết broker nào đang quản lý partition, broker nào là leader và cần kết nối tới địa chỉ nào để gửi hoặc nhận record.

Vì vậy, bootstrap servers là điểm khởi đầu của quá trình kết nối. Danh sách này không phải danh sách cố định mà client dùng cho mọi thao tác. Kafka client khám phá topology từ metadata do broker trả về rồi kết nối trực tiếp tới các broker được công bố trong metadata. Cơ chế này giúp producer, consumer và AdminClient hoạt động trên cluster nhiều broker.

Bài học thuộc chương **Cấu hình kết nối** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách cấu hình Spring Kafka, hiểu metadata discovery, xử lý địa chỉ broker trong môi trường container và mạng triển khai, cũng như chẩn đoán lỗi kết nối để vận hành luồng messaging tin cậy.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích bootstrap.servers là gì và vì sao client chỉ cần một số địa chỉ khởi đầu có thể truy cập.
- Mô tả các bước Kafka client kết nối broker, lấy metadata và định tuyến request tới partition leader.
- Phân biệt listeners và advertised.listeners ở phía broker.
- Cấu hình bootstrap servers cho Spring Boot và Spring Kafka.
- Chọn địa chỉ phù hợp khi ứng dụng chạy trên máy cá nhân, Docker Compose, Kubernetes hoặc mạng bên ngoài.
- Nhận biết vì sao kết nối bootstrap thành công nhưng producer hoặc consumer vẫn không hoạt động.
- Kiểm tra metadata và phân biệt lỗi DNS, TCP, TLS/SASL, ACL và lỗi leader.
- Thiết kế cấu hình kết nối có dự phòng, bảo mật và kiểm thử được.

## 1. bootstrap.servers là gì?

Kafka client cần một địa chỉ để gửi request đầu tiên tới cluster. Thuộc tính bootstrap.servers là danh sách host và port dùng cho bước này.

Ví dụ:

~~~properties
bootstrap.servers=kafka-1.example.net:9092,kafka-2.example.net:9092,kafka-3.example.net:9092
~~~

Mỗi phần tử thường có định dạng host:port. Các địa chỉ được phân tách bằng dấu phẩy, không có tiền tố giao thức như http:// hoặc https://. Giao thức bảo mật được cấu hình riêng bằng security.protocol và các thuộc tính liên quan.

Một client không bắt buộc phải biết trước mọi broker trong cluster. Chỉ cần ít nhất một địa chỉ bootstrap đang hoạt động và trả về metadata hợp lệ, client có thể khám phá các broker khác. Tuy vậy, khai báo nhiều địa chỉ bootstrap giúp client có thêm lựa chọn nếu một broker hoặc một endpoint ban đầu tạm thời không truy cập được.

Ví dụ cấu hình cho môi trường phát triển:

~~~properties
bootstrap.servers=localhost:9092
~~~

Ví dụ cấu hình cho cluster nhiều broker:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
~~~

Danh sách bootstrap không quyết định partition nào nằm trên broker nào. Việc phân phối partition, leader và replica do Kafka cluster quản lý. Client lấy thông tin đó qua metadata.

Cần phân biệt:

| Thành phần | Ý nghĩa |
|---|---|
| bootstrap.servers | Danh sách địa chỉ ban đầu để client liên hệ cluster và lấy metadata. |
| Broker ID | Định danh broker trong cluster, được metadata sử dụng để mô tả topology. |
| Partition leader | Broker chịu trách nhiệm nhận request đọc/ghi chính cho partition đó. |
| advertised.listeners | Các địa chỉ broker công bố cho client kết nối sau khi khám phá metadata. |
| Metadata | Thông tin cluster, broker, topic, partition, leader, replica và ISR. |

## 2. Cơ chế khám phá broker và metadata

Quá trình kết nối không dừng lại ở việc mở TCP tới bootstrap server. Kafka client cần metadata để biết đích thực tế của các request.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant Client as Kafka Client
    participant Seed as Bootstrap Broker
    participant Leader as Partition Leader
    Client->>Seed: Kết nối tới host:port ban đầu
    Client->>Seed: ApiVersions / Metadata request
    Seed-->>Client: Cluster metadata và advertised endpoints
    Client->>Client: Lưu metadata vào cache
    Client->>Leader: Gửi request tới broker quản lý partition
    Leader-->>Client: Produce / Fetch response
~~~

Các bước chính:

1. **Đọc bootstrap.servers:** client phân tích danh sách host và port.
2. **Phân giải DNS:** hệ điều hành phân giải hostname thành địa chỉ IP.
3. **Thiết lập kết nối:** client mở kết nối tới một endpoint bootstrap có thể truy cập.
4. **Thương lượng giao thức và bảo mật:** client trao đổi thông tin phiên bản API; nếu dùng TLS hoặc SASL, quá trình bắt tay và xác thực được thực hiện theo cấu hình.
5. **Yêu cầu metadata:** client hỏi broker về topology cluster và các topic cần sử dụng.
6. **Nhận metadata:** broker trả về danh sách broker cùng thông tin partition, leader, replica và ISR.
7. **Kết nối tới broker đích:** client dùng địa chỉ broker trong metadata để gửi Produce, Fetch hoặc request quản trị.
8. **Làm mới metadata:** khi topology thay đổi hoặc client gặp lỗi liên quan tới leader, client có thể yêu cầu metadata mới.

Ví dụ, topic orders.created có ba partition. Partition 0 có leader trên broker 1, partition 1 có leader trên broker 2 và partition 2 có leader trên broker 3. Producer gửi record với key được định tuyến vào partition 2 sẽ cần kết nối tới broker 3 theo metadata, dù kết nối ban đầu được thiết lập qua broker 1.

~~~mermaid
flowchart TD
    C[Kafka Producer] --> S[Bootstrap endpoint]
    S --> M[Cluster metadata]
    M --> P0[Partition 0 - Leader Broker 1]
    M --> P1[Partition 1 - Leader Broker 2]
    M --> P2[Partition 2 - Leader Broker 3]
    C --> P2
~~~

Consumer cũng sử dụng metadata để biết broker phục vụ các partition được gán. Ngoài ra, consumer group cần tìm group coordinator để tham gia group, heartbeat và commit offset. Coordinator có thể là một broker khác với bootstrap broker.

Điều này giải thích một tình huống thường gặp: lệnh kiểm tra kết nối tới bootstrap server thành công, nhưng ứng dụng vẫn không gửi hoặc nhận được record. Nguyên nhân có thể là các địa chỉ broker trong metadata không thể truy cập từ mạng của ứng dụng.

## 3. Bootstrap servers không phải proxy cho toàn bộ cluster

Một hiểu lầm phổ biến là khai báo một địa chỉ bootstrap có nghĩa mọi request Kafka đều đi qua địa chỉ đó. Thực tế, bootstrap server chỉ giúp client bắt đầu kết nối và lấy metadata. Sau đó client kết nối tới broker được chỉ định trong metadata.

Ví dụ:

- Ứng dụng kết nối tới kafka-bootstrap.example.net:9092.
- Broker trả metadata cho biết leader của partition cần gửi là kafka-2.internal:9092.
- Client cần phân giải và kết nối được kafka-2.internal:9092.

Nếu máy chạy ứng dụng không phân giải được hostname kafka-2.internal hoặc firewall chặn port 9092, client vẫn thất bại dù endpoint bootstrap ban đầu hoạt động.

Khai báo nhiều bootstrap servers giúp dự phòng cho bước kết nối ban đầu. Nó không tự sửa các địa chỉ advertised.listeners sai, không tạo ra đường mạng tới broker leader và cũng không thay thế cơ chế replication của Kafka.

Với load balancer, cần hiểu rõ cách nó hoạt động. Một TCP load balancer có thể chuyển kết nối bootstrap tới một broker, nhưng metadata vẫn có thể chứa địa chỉ riêng của từng broker. Client phải truy cập được các địa chỉ đó. Một load balancer chung không tự động biến Kafka thành giao thức chỉ có một endpoint như một HTTP API thông thường. Nếu dùng load balancer hoặc DNS, hạ tầng phải cung cấp ánh xạ kết nối phù hợp cho từng broker được công bố.

## 4. listeners và advertised.listeners

Để hiểu tại sao client có thể kết nối bootstrap thành công nhưng không thể kết nối broker tiếp theo, cần phân biệt hai cấu hình ở phía Kafka broker.

- **listeners:** địa chỉ và port mà broker bind để lắng nghe kết nối trên các network interface.
- **advertised.listeners:** địa chỉ và port mà broker công bố trong metadata để client sử dụng khi kết nối.

Một ví dụ broker có hai listener:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9094
advertised.listeners=INTERNAL://kafka-1:9092,EXTERNAL://broker-1.example.net:9094
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL
~~~

Trong ví dụ:

- Broker lắng nghe trên mọi interface ở port 9092 cho listener INTERNAL và port 9094 cho EXTERNAL.
- Client trong cùng mạng nội bộ dùng kafka-1:9092.
- Client từ mạng bên ngoài dùng broker-1.example.net:9094.
- Broker giao tiếp nội bộ qua listener INTERNAL.

Địa chỉ 0.0.0.0 là địa chỉ bind, không phải hostname để client sử dụng. Broker phải công bố hostname có thể truy cập từ góc nhìn của client.

Đối với một cluster, mỗi broker cần công bố đúng endpoint tương ứng với listener mà client đã kết nối. Nếu metadata trả về hostname nội bộ cho client bên ngoài, client sẽ không thể kết nối. Nếu broker công bố localhost cho client ở container hoặc máy khác, client sẽ cố kết nối tới chính máy của nó thay vì máy đang chạy broker.

~~~mermaid
flowchart LR
    subgraph Network["Mạng ứng dụng"]
        APP[Spring Boot client]
        DNS[DNS / Service discovery]
    end
    subgraph Cluster["Kafka cluster"]
        B1[Broker 1]
        B2[Broker 2]
        B3[Broker 3]
    end
    APP --> DNS
    DNS --> B1
    B1 -. Metadata .-> APP
    APP --> B2
    APP --> B3
~~~

Nguyên tắc quan trọng: mọi endpoint broker được trả về trong metadata phải phân giải được và truy cập được từ môi trường đang chạy Kafka client.

## 5. Cấu hình Spring Kafka trong Spring Boot

Với Spring Boot, cấu hình bootstrap servers thường được đặt trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
~~~

Biến môi trường KAFKA_BOOTSTRAP_SERVERS cho phép thay đổi địa chỉ cluster theo môi trường mà không sửa source code. Giá trị mặc định localhost:9092 chỉ phù hợp khi Kafka chạy trên máy phát triển và ứng dụng kết nối từ chính máy đó.

Nếu cluster có nhiều bootstrap endpoint:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9092,kafka-2.internal:9092,kafka-3.internal:9092
~~~

Spring Boot dùng cấu hình chung này để tạo các thành phần producer, consumer và admin theo auto-configuration. Vì vậy, hãy bảo đảm các địa chỉ trong danh sách đều thuộc cùng một cluster và cùng loại listener phù hợp với mạng của ứng dụng.

Có thể kiểm tra giá trị đã được nạp bằng cách xem cấu hình hiệu lực trong môi trường phát triển hoặc log cấu hình không nhạy cảm khi ứng dụng khởi động. Không ghi credential hoặc toàn bộ cấu hình SASL vào log.

Một producer và consumer tối thiểu có thể dùng cấu hình này:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

~~~java
@Component
public class OrderListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-processor"
    )
    public void consume(OrderCreatedEvent event) {
        // Xử lý sự kiện đơn hàng.
    }
}
~~~

KafkaTemplate và @KafkaListener không cần tự truyền bootstrap server trong từng lời gọi. Chúng dùng ProducerFactory và ConsumerFactory được cấu hình từ Spring Boot hoặc cấu hình Spring Kafka của ứng dụng.

## 6. Kết nối từ máy cá nhân, Docker và Kubernetes

Địa chỉ bootstrap phải được chọn theo góc nhìn mạng của tiến trình Kafka client. Cùng một Kafka broker có thể cần công bố các listener khác nhau cho các môi trường kết nối khác nhau.

### Ứng dụng chạy trực tiếp trên máy cá nhân

Nếu Kafka chạy trên máy cá nhân và publish port 9092 ra host, ứng dụng chạy trực tiếp trên máy đó có thể dùng:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Nếu ứng dụng chạy trên một máy khác, localhost sẽ trỏ tới máy chạy ứng dụng. Khi đó cần dùng hostname hoặc IP của máy Kafka có thể truy cập qua mạng.

### Ứng dụng chạy trong Docker Compose

Các container trong cùng Docker network thường liên hệ nhau bằng service name. Ví dụ container ứng dụng có thể dùng kafka:9092 thay vì localhost:9092:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
~~~

Ở bên trong container ứng dụng, localhost là chính container ứng dụng. Nó không tự động trỏ tới container Kafka.

Nếu cả ứng dụng và Kafka cần được truy cập từ host, broker cần cấu hình listener nội bộ và listener bên ngoài tương ứng. Ví dụ minh họa:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,HOST://0.0.0.0:29092
advertised.listeners=INTERNAL://kafka:9092,HOST://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,HOST:PLAINTEXT
inter.broker.listener.name=INTERNAL
~~~

Container ứng dụng sử dụng listener INTERNAL và host sử dụng listener HOST. Cấu hình thực tế còn phụ thuộc image Kafka, chế độ KRaft hoặc ZooKeeper, cách publish port và các biến môi trường của image đang dùng. Không sao chép riêng các dòng listener mà bỏ qua cấu hình cluster đi kèm.

### Ứng dụng chạy trong Kubernetes

Trong Kubernetes, client có thể dùng DNS của Service để bắt đầu kết nối. Tuy nhiên, Kafka client còn cần truy cập các endpoint broker được công bố trong metadata.

Một mô hình thường dùng là headless Service hoặc cơ chế discovery do Kafka operator quản lý để mỗi broker có hostname ổn định. Nếu client chạy bên ngoài cluster, cần cấu hình external listener và endpoint tương ứng cho từng broker.

Với Kubernetes, hãy kiểm tra:

- Pod ứng dụng và broker có network policy cho phép giao tiếp hay không.
- DNS Service có phân giải được từ namespace của ứng dụng không.
- Port của từng broker có được expose đúng không.
- advertised.listeners có công bố hostname phù hợp với client nội bộ hoặc bên ngoài không.
- TLS certificate có SAN phù hợp với hostname mà client kết nối không.

Một endpoint bootstrap dùng chung có thể hoạt động trong bước đầu, nhưng từng broker được công bố trong metadata vẫn phải truy cập được.

## 7. Cấu hình bảo mật cho bootstrap connection

Bootstrap connection cũng phải tuân thủ cơ chế bảo mật của cluster. Khi Kafka sử dụng TLS hoặc SASL, client cần các thuộc tính bảo mật tương ứng.

Ví dụ cấu hình SASL_SSL với SCRAM:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="<username>" password="<password>";
~~~

Giá trị JAAS cần được cấp từ secret manager hoặc cơ chế quản lý secret của môi trường triển khai. Không đặt username và password thật trực tiếp trong file cấu hình được commit vào repository.

Với TLS, client cần trust certificate của broker. Nếu dùng mutual TLS, client còn cần certificate và private key tương ứng. Cần kiểm tra hostname verification: hostname trong advertised.listeners phải khớp với Subject Alternative Name của certificate theo cấu hình xác thực.

Các điểm cần phân biệt khi chẩn đoán:

- TCP connection thành công không đồng nghĩa TLS handshake thành công.
- TLS handshake thành công không đồng nghĩa SASL authentication thành công.
- Authentication thành công không đồng nghĩa tài khoản có ACL cho topic hoặc consumer group.
- Có quyền truy cập bootstrap broker không đảm bảo mọi broker trong metadata đều cho phép cùng kết nối và xác thực.

Nếu cluster dùng nhiều listener với cơ chế bảo mật khác nhau, bootstrap endpoint và các endpoint metadata trả về phải tương thích với cấu hình listener mà client sử dụng.

## 8. Dự phòng bootstrap và làm mới metadata

Khai báo nhiều bootstrap server giúp client có thể thử một endpoint khác khi endpoint đầu tiên không khả dụng. Danh sách này nên chứa các địa chỉ độc lập đủ để client bắt đầu khám phá cluster khi một broker gặp sự cố.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal:9092
      - kafka-2.internal:9092
      - kafka-3.internal:9092
~~~

Spring Boot hỗ trợ cấu hình bootstrap servers dưới dạng danh sách hoặc chuỗi phân tách bằng dấu phẩy. Chọn một cách biểu diễn nhất quán theo định dạng file cấu hình và phiên bản Spring Boot đang dùng.

Kafka client duy trì metadata cache và tự làm mới khi cần. Một số tình huống có thể kích hoạt việc cập nhật metadata:

- Metadata đã quá thời gian làm mới theo cấu hình client.
- Client gặp lỗi cho biết leader hoặc partition metadata đã cũ.
- Broker trả về lỗi như NOT_LEADER_OR_FOLLOWER hoặc LEADER_NOT_AVAILABLE.
- Cluster thay đổi topology hoặc partition leader được bầu lại.

Thuộc tính metadata.max.age.ms điều khiển chu kỳ làm mới metadata định kỳ của Kafka client. Các thuộc tính reconnect.backoff.ms và reconnect.backoff.max.ms điều khiển khoảng nghỉ khi kết nối lại. Giá trị cụ thể nên được điều chỉnh theo độ ổn định mạng và yêu cầu phục hồi; không nên giảm quá thấp khiến client tạo nhiều request hoặc kết nối lặp khi cluster đang gặp sự cố.

Nhiều bootstrap endpoint tăng khả năng bắt đầu kết nối, nhưng không thay thế replication factor, ISR hoặc cơ chế failover leader. Những cơ chế đó thuộc về Kafka cluster.

## 9. Kết nối nhiều Kafka cluster

Một ứng dụng có thể cần kết nối tới nhiều Kafka cluster, ví dụ cluster nội bộ và cluster đối tác, hoặc cluster phục vụ các miền dữ liệu khác nhau.

Cấu hình Spring Boot mặc định thường phù hợp với một cluster chung cho producer, consumer và admin. Nếu cần nhiều cluster, cần khai báo riêng các thành phần kết nối như ProducerFactory, ConsumerFactory, KafkaTemplate, listener container factory hoặc AdminClient với bootstrap servers và security config riêng.

Ví dụ tạo AdminClient cho một cluster phụ:

~~~java
@Bean(destroyMethod = "close")
AdminClient auditAdminClient(
        @Value("${app.kafka.audit.bootstrap-servers}") String servers) {

    Map<String, Object> configs = new HashMap<>();
    configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            servers
    );

    return AdminClient.create(configs);
}
~~~

Cấu hình tương ứng:

~~~yaml
app:
  kafka:
    audit:
      bootstrap-servers: audit-kafka-1:9092,audit-kafka-2:9092
~~~

Đoạn code chỉ minh họa riêng AdminClient cho cluster phụ. Nếu gửi hoặc nhận record ở cluster này, cần tạo ProducerFactory hoặc ConsumerFactory tương ứng và bảo đảm listener sử dụng đúng container factory. Không dùng nhầm KafkaTemplate hoặc consumer factory của cluster mặc định.

Mỗi cluster có thể có:

- Danh sách bootstrap servers khác nhau.
- Listener nội bộ hoặc bên ngoài khác nhau.
- Cơ chế SASL/TLS và credential riêng.
- Topic, ACL, consumer group và chính sách lưu trữ riêng.

Nên đặt tên bean và cấu hình rõ ràng theo mục đích, chẳng hạn primaryKafkaTemplate và auditKafkaTemplate, để tránh nhầm cluster khi inject dependency.

## 10. Chẩn đoán lỗi kết nối và metadata discovery

Khi client không kết nối được, hãy phân tích theo từng lớp thay vì thay đổi ngẫu nhiên bootstrap servers.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| UnknownHostException | DNS không phân giải được hostname | Kiểm tra hostname từ đúng môi trường chạy ứng dụng. |
| Connection refused | Broker không lắng nghe port hoặc port chưa được publish | Kiểm tra listeners, port mapping và trạng thái broker. |
| Connection timed out | Firewall, route hoặc network policy chặn kết nối | Kiểm tra đường mạng từ container/pod/host tới broker. |
| TLS handshake failed | Certificate, truststore, hostname hoặc protocol không khớp | Kiểm tra certificate chain, SAN và cấu hình TLS. |
| SASL authentication failed | Mechanism, username, password hoặc JAAS config sai | Kiểm tra secret và cơ chế SASL của listener. |
| Bootstrap kết nối được nhưng broker khác không truy cập được | advertised.listeners trả hostname hoặc port không phù hợp | Đọc metadata và kiểm tra từng endpoint broker được công bố. |
| Not authorized | Tài khoản xác thực thành công nhưng thiếu ACL | Kiểm tra quyền topic, group hoặc cluster resource. |
| LEADER_NOT_AVAILABLE | Partition chưa có leader khả dụng hoặc cluster đang phục hồi | Kiểm tra trạng thái partition, controller và broker. |
| NOT_LEADER_OR_FOLLOWER | Metadata cũ hoặc leader vừa thay đổi | Để client làm mới metadata; kiểm tra tình trạng cluster nếu lỗi kéo dài. |

Một quy trình chẩn đoán hữu ích:

1. Xác nhận giá trị bootstrap servers thực tế mà ứng dụng đang sử dụng.
2. Phân giải DNS hostname từ đúng máy, container hoặc pod chạy ứng dụng.
3. Kiểm tra TCP tới từng endpoint bootstrap.
4. Xác minh TLS/SASL nếu cluster có bảo mật.
5. Lấy metadata từ bootstrap endpoint.
6. Kiểm tra từng hostname và port trong metadata.
7. Xác nhận partition leader, broker và ACL.
8. Đọc log client để xác định lỗi xảy ra ở bước nào.

Có thể dùng công cụ CLI để xem metadata:

~~~bash
kcat -b kafka-1.internal:9092,kafka-2.internal:9092 -L
~~~

Lệnh trên yêu cầu kcat được cài đặt và có cấu hình bảo mật phù hợp nếu cluster yêu cầu xác thực. Kết quả metadata cho thấy broker và partition mà client nhìn thấy. Nếu metadata trả về hostname nội bộ không thể truy cập từ máy đang chạy kcat, cần sửa advertised.listeners hoặc chọn listener phù hợp.

Có thể dùng kafka-broker-api-versions.sh để kiểm tra kết nối và phiên bản API:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server kafka-1.internal:9092
~~~

Đây là phép kiểm tra hữu ích cho bootstrap endpoint; vẫn cần kiểm tra endpoint broker được trả về trong metadata để xác nhận toàn bộ đường kết nối.

## 11. Kiểm thử cấu hình bootstrap servers

Kiểm thử kết nối nên xác nhận cả bootstrap và khả năng khám phá broker. Một test chỉ kiểm tra socket tới một địa chỉ không chứng minh client có thể gửi record tới partition leader hoặc tham gia consumer group.

Các lớp kiểm thử:

| Loại kiểm thử | Mục tiêu |
|---|---|
| Configuration test | Đảm bảo bootstrap servers được nạp đúng theo profile và biến môi trường. |
| Connectivity test | Client tạo được kết nối và lấy metadata từ cluster. |
| Producer integration test | Gửi record tới topic và nhận kết quả broker xác nhận. |
| Consumer integration test | Consumer tham gia group, nhận record và xử lý được partition assignment. |
| Multi-broker test | Metadata chứa nhiều broker và client truy cập được leader tương ứng. |
| Security test | TLS/SASL hoạt động; credential sai hoặc thiếu ACL được phát hiện rõ ràng. |
| Network failure test | Một bootstrap endpoint mất kết nối nhưng client vẫn có thể khám phá cluster qua endpoint còn lại. |

Với Testcontainers, nên lấy địa chỉ kết nối từ container thay vì hardcode localhost. Ví dụ cấu hình Spring test bằng DynamicPropertySource:

~~~java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafkaContainer::getBootstrapServers
    );
}
~~~

Biến kafkaContainer cần được khởi tạo và quản lý bởi test fixture phù hợp với phiên bản Testcontainers và Kafka image của dự án. Trong môi trường nhiều broker, test nên xác minh metadata chứa các broker cần thiết và gửi record tới các partition có leader khác nhau.

Không nên dùng sleep cố định để đợi broker sẵn sàng. Hãy dùng health check hoặc chờ điều kiện kết nối/metadata với timeout rõ ràng. Nếu kiểm thử lỗi mạng, cần giới hạn thời gian và phục hồi network sau test để không làm ảnh hưởng các test khác.

## 12. Checklist vận hành kết nối

Khi triển khai Spring Kafka, hãy kiểm tra các điểm sau:

- Bootstrap servers trỏ tới đúng cluster và đúng listener cho môi trường ứng dụng.
- Có nhiều endpoint bootstrap độc lập nếu hạ tầng yêu cầu khả năng dự phòng.
- Mọi broker được trả về trong metadata đều có hostname và port truy cập được.
- advertised.listeners phù hợp với mạng của client.
- DNS, firewall, route và Kubernetes NetworkPolicy cho phép kết nối tới từng broker.
- TLS certificate khớp hostname và được trust đúng cách.
- SASL mechanism, credential và ACL được cấu hình theo nguyên tắc quyền tối thiểu.
- Ứng dụng không ghi secret vào log.
- Timeout và reconnect backoff phù hợp với thời gian phục hồi dự kiến.
- Log có thông tin cần thiết để xác định broker và lỗi kết nối, nhưng không chứa thông tin xác thực.
- Health/readiness phản ánh đúng khả năng sử dụng Kafka theo yêu cầu nghiệp vụ.

Khi thay đổi hostname, port, listener hoặc certificate của broker, cần đánh giá ảnh hưởng tới tất cả client đang sử dụng cluster. Thay đổi advertised.listeners có thể làm gián đoạn client nếu DNS hoặc firewall chưa được cập nhật đồng bộ.

## 13. Bài tập tổng hợp: kết nối Spring Kafka tới cluster nhiều broker

Hãy xây dựng môi trường thực hành với một ứng dụng Spring Boot và Kafka cluster có ít nhất hai broker nếu môi trường cho phép.

Yêu cầu:

1. Cấu hình bootstrap servers với nhiều endpoint.
2. Khởi động ứng dụng và ghi nhận broker nào được dùng cho kết nối ban đầu.
3. Dùng AdminClient hoặc kcat lấy metadata và liệt kê broker.
4. Tạo topic có nhiều partition và xác định leader của từng partition.
5. Gửi OrderCreatedEvent bằng KafkaTemplate với nhiều key để record được phân bố qua các partition.
6. Dùng @KafkaListener nhận record và ghi log topic, partition, offset, key.
7. Dừng một bootstrap endpoint rồi kiểm tra khả năng client kết nối qua endpoint còn lại.
8. Cấu hình sai advertised.listeners có chủ đích trong môi trường test để quan sát lỗi metadata discovery.
9. Sửa endpoint, kiểm tra lại DNS, port và metadata.
10. Thử bật TLS hoặc SASL nếu môi trường hỗ trợ, rồi kiểm tra xác thực và ACL.
11. Viết integration test dùng địa chỉ bootstrap do test container cung cấp.
12. Ghi lại cấu hình local, Docker hoặc Kubernetes để thành viên khác có thể tái tạo kết nối.

Sau bài tập, bạn cần giải thích được vì sao kết nối tới bootstrap server chưa đủ để bảo đảm ứng dụng có thể gửi và nhận record, và vì sao advertised.listeners phải được thiết kế theo vị trí mạng của Kafka client.

## 14. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Bootstrap | Host, port, danh sách endpoint | Cấu hình đúng một hoặc nhiều bootstrap servers. |
| 2. Metadata | Broker, topic, partition, leader, ISR | Đọc được metadata và xác định leader cho partition. |
| 3. Listener | listeners và advertised.listeners | Giải thích được khác biệt giữa địa chỉ bind và địa chỉ công bố. |
| 4. Spring Boot | spring.kafka.bootstrap-servers | Producer, consumer và admin dùng đúng cluster. |
| 5. Network | Local, Docker, Kubernetes, DNS, firewall | Client truy cập được mọi broker trong metadata. |
| 6. Security | TLS, SASL, ACL | Kết nối và xác thực đúng listener. |
| 7. Reliability | Nhiều bootstrap endpoints, reconnect, metadata refresh | Phân biệt dự phòng bootstrap với failover broker/replica. |
| 8. Testing | Testcontainers, CLI, metadata checks | Có kiểm thử gửi, nhận và khám phá broker. |

Bài học hoàn thành khi bạn có thể cấu hình bootstrap servers trong Spring Boot, mô tả được quá trình metadata discovery, thiết kế advertised.listeners phù hợp với mạng triển khai và chẩn đoán được trường hợp bootstrap kết nối thành công nhưng các broker khác không truy cập được.

Kafka client cần một điểm bắt đầu để khám phá cluster, sau đó dựa vào metadata và địa chỉ broker được công bố để định tuyến request. Khi hiểu rõ mối quan hệ giữa bootstrap.servers, listeners, advertised.listeners, DNS và network, bạn có thể cấu hình kết nối Spring Kafka ổn định hơn trong môi trường local, container và production.

