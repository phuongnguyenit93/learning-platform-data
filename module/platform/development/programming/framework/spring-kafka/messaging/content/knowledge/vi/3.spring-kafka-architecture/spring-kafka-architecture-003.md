# ConsumerFactory và producer factory

Trong Spring Kafka, ứng dụng thường không tạo trực tiếp Kafka producer hoặc consumer ở mỗi nơi cần gửi và nhận sự kiện. Thay vào đó, Spring Kafka đặt các factory ở giữa để quản lý cấu hình và vòng đời của client:

- **ProducerFactory** tạo và quản lý Kafka producer. **KafkaTemplate** sử dụng factory này để gửi record.
- **ConsumerFactory** tạo Kafka consumer. Listener container sử dụng factory này để đọc record và gọi phương thức **@KafkaListener**.
- **ConcurrentKafkaListenerContainerFactory** tạo listener container với các chính sách như concurrency, acknowledgement và error handling. Nó không phải là Kafka ConsumerFactory.

Hiểu đúng ba thành phần này giúp cấu hình Kafka client nhất quán, kiểm soát số lượng kết nối, xử lý transaction và mở rộng consumer mà không tự quản lý vòng đời client trong từng lớp nghiệp vụ.

Bài học thuộc chương **Kiến trúc Spring Kafka** trong module **SPRING_KAFKA_MESSAGING**. Module này hướng tới việc xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, hiểu topic, partition, offset và consumer group, đồng thời chuẩn bị nền tảng để cấu hình serialization, retry, dead-letter, transaction, xử lý đồng thời và kiểm thử.

## 1. Vị trí của factory trong kiến trúc Spring Kafka

Một ứng dụng Spring Kafka thường có hai luồng chính:

1. Luồng gửi: service nghiệp vụ gọi KafkaTemplate; KafkaTemplate lấy producer từ ProducerFactory; producer serialize và gửi record tới broker.
2. Luồng nhận: listener container lấy consumer từ ConsumerFactory; consumer poll record; container chuyển record đến phương thức @KafkaListener và phối hợp việc xác nhận offset.

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    subgraph Sending["Luồng producer"]
        A[Service nghiệp vụ] --> B[KafkaTemplate]
        B --> C[ProducerFactory]
        C --> D[Kafka Producer]
        D --> E[Kafka Broker]
    end

    subgraph Receiving["Luồng consumer"]
        E --> F[Kafka Consumer]
        F --> G[ConsumerFactory]
        G --> H[Listener Container]
        H --> I[@KafkaListener]
        I --> J[Xử lý nghiệp vụ]
    end

    K[ConcurrentKafkaListenerContainerFactory] --> H
~~~

Sơ đồ thể hiện quan hệ trách nhiệm. Khi chạy thực tế, ConsumerFactory được listener container gọi để tạo consumer; consumer kết nối broker và poll dữ liệu. ConcurrentKafkaListenerContainerFactory được dùng ở bước cấu hình container, thường thông qua thuộc tính containerFactory của @KafkaListener.

Factory là đối tượng quản lý việc tạo client, không phải client đang thực hiện gửi hoặc poll. Producer và consumer mới là các đối tượng giao tiếp với Kafka broker.

## 2. Các interface và implementation cốt lõi

Spring Kafka cung cấp các interface để ứng dụng có thể dùng abstraction hoặc thay implementation khi cần:

| Thành phần | Trách nhiệm | Implementation thường dùng |
| --- | --- | --- |
| ProducerFactory<K,V> | Cung cấp producer để gửi record và quản lý vòng đời producer | DefaultKafkaProducerFactory<K,V> |
| ConsumerFactory<K,V> | Tạo consumer với cấu hình key/value và group tương ứng | DefaultKafkaConsumerFactory<K,V> |
| KafkaTemplate<K,V> | API gửi record, nhận kết quả gửi và hỗ trợ thao tác producer | KafkaTemplate<K,V> |
| KafkaListenerContainerFactory<C> | Tạo container thực thi listener | ConcurrentKafkaListenerContainerFactory<K,V> |
| KafkaMessageListenerContainer | Container xử lý listener với một consumer | KafkaMessageListenerContainer |
| ConcurrentMessageListenerContainer | Container quản lý nhiều child container/consumer | ConcurrentMessageListenerContainer |

K và V là kiểu key và value ở phía ứng dụng. Ví dụ ProducerFactory<String, OrderCreated> biểu thị ứng dụng gửi key dạng String và payload dạng OrderCreated. Trước khi gửi, serializer chuyển các giá trị này thành byte. Ở chiều nhận, deserializer chuyển byte về kiểu mà listener sử dụng.

Các generic type giúp kiểm tra kiểu ở thời điểm biên dịch. Chúng không tự bảo đảm serializer và deserializer ở hai phía tương thích. Cấu hình định dạng dữ liệu vẫn phải được thống nhất.

## 3. ProducerFactory và DefaultKafkaProducerFactory

### 3.1. ProducerFactory giải quyết vấn đề gì?

KafkaProducer là client của Kafka Java API. Ứng dụng có thể tự tạo KafkaProducer, gọi send và đóng producer. Tuy nhiên, nếu nhiều service hoặc component cùng gửi dữ liệu, việc mỗi nơi tự tạo client dễ dẫn đến:

- Lặp lại cấu hình bootstrap server, serializer, acknowledgement, retry và bảo mật.
- Tạo quá nhiều kết nối hoặc producer không được đóng đúng lúc.
- Khó quản lý transaction và tái sử dụng producer.
- Khó thay cấu hình giữa môi trường phát triển, kiểm thử và production.
- Các component có cách xử lý lỗi và timeout không nhất quán.

ProducerFactory tập trung việc tạo và quản lý producer. KafkaTemplate nhận ProducerFactory qua constructor hoặc dependency injection, sau đó sử dụng producer do factory cấp để gửi record.

### 3.2. DefaultKafkaProducerFactory tạo và tái sử dụng producer

DefaultKafkaProducerFactory là implementation phổ biến của ProducerFactory. Với cấu hình thông thường, factory dùng một producer dùng chung. KafkaProducer được thiết kế thread-safe, vì vậy nhiều luồng có thể gửi record thông qua cùng producer mà không cần tạo một producer riêng cho từng lời gọi.

Mô hình mặc định:

~~~text
ProducerFactory
      |
      +---- KafkaProducer dùng chung
                 ^
                 |
          KafkaTemplate
            /   |   \
         Thread A  Thread B  Thread C
~~~

Cách dùng producer dùng chung giúp tránh chi phí khởi tạo client và kết nối broker lặp lại. KafkaTemplate có thể được dùng như một bean singleton trong ứng dụng Spring.

ProducerFactory quản lý việc lấy và trả producer theo chính sách của factory. Khi sử dụng KafkaTemplate, thông thường ứng dụng không tự đóng producer sau mỗi lần send. Factory chịu trách nhiệm đóng tài nguyên khi application context dừng.

### 3.3. ProducerFactory và KafkaTemplate có vai trò khác nhau

Hai lớp này thường được inject cùng nhau nhưng không thay thế nhau:

- ProducerFactory tạo và quản lý Kafka producer.
- KafkaTemplate cung cấp API tiện dụng cho code nghiệp vụ: gửi theo topic/key/value, gửi ProducerRecord, nhận future, thực hiện callback hoặc thao tác trong transaction.
- KafkaProducer là client thực tế thực hiện giao tiếp với broker.

Ví dụ gửi event:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
~~~

Service chỉ phụ thuộc KafkaTemplate. Service không cần biết factory tạo producer ra sao, producer được tái sử dụng thế nào hoặc cấu hình serializer nằm ở đâu. Trách nhiệm cấu hình client thuộc tầng hạ tầng messaging.

### 3.4. Cấu hình producer factory

ProducerFactory nhận một map cấu hình theo Kafka ProducerConfig và các cấu hình serializer của Spring Kafka. Các giá trị thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| bootstrap.servers | Danh sách broker dùng để khởi tạo kết nối và lấy metadata cluster |
| key.serializer | Serializer cho key |
| value.serializer | Serializer cho value |
| acks | Mức broker xác nhận record |
| enable.idempotence | Bật producer idempotence để hạn chế duplicate do retry ở tầng producer |
| retries | Số lần producer thử gửi lại khi gặp lỗi có thể retry |
| delivery.timeout.ms | Giới hạn thời gian hoàn tất việc gửi, gồm chờ acknowledgement và retry |
| request.timeout.ms | Thời gian chờ phản hồi cho một request |
| linger.ms | Thời gian producer có thể chờ để gom record thành batch |
| batch.size | Kích thước batch mục tiêu theo partition |
| compression.type | Kiểu nén record batch |

Không nên sao chép mọi cấu hình vào mọi môi trường một cách máy móc. Ví dụ acks, idempotence, retries và delivery timeout cần được chọn cùng nhau dựa trên yêu cầu độ bền, độ trễ và khả năng chịu lỗi.

Ví dụ cấu hình producer properties bằng Java:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> orderProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    props.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    return new DefaultKafkaProducerFactory<>(props);
}
~~~

Trong ví dụ, DefaultKafkaProducerFactory đọc map cấu hình và tạo KafkaProducer với StringSerializer cho key, JsonSerializer cho value. Cấu hình acks=all yêu cầu leader chờ các replica đang nằm trong ISR xác nhận theo giao thức replication. Độ bền thực tế còn phụ thuộc replication factor và min.insync.replicas của topic/broker.

### 3.5. Serializer thuộc cấu hình producer factory

Kafka lưu record dưới dạng byte. Vì vậy, producer factory phải biết cách chuyển kiểu key/value của ứng dụng thành byte.

Ví dụ:

- StringSerializer phù hợp với key hoặc value là chuỗi.
- ByteArraySerializer phù hợp khi ứng dụng đã tự tạo payload byte.
- JsonSerializer của Spring Kafka chuyển object thành JSON.
- Serializer Avro hoặc Protobuf có thể được dùng khi hệ thống quản lý schema theo các định dạng đó.

Serializer có thể được khai báo bằng class trong map cấu hình. Kafka client sẽ khởi tạo serializer cho producer. Với serializer tùy chỉnh cần có dependency hoặc trạng thái riêng, cần kiểm tra cách khởi tạo và cấu hình của serializer để tránh chia sẻ state ngoài ý muốn.

ProducerFactory không biến một object Java thành JSON bằng phép tự động không điều kiện. Nó tạo producer với serializer đã cấu hình; chính serializer thực hiện chuyển đổi tại thời điểm gửi.

### 3.6. Producer dùng chung và producer theo thread

KafkaProducer thread-safe nên mô hình dùng chung là lựa chọn mặc định phù hợp cho nhiều ứng dụng. Tuy nhiên, DefaultKafkaProducerFactory cũng có tùy chọn producer theo thread thông qua producerPerThread trong các phiên bản hỗ trợ.

Khi bật producerPerThread, factory giữ producer gắn với từng thread thay vì chỉ dùng một producer chung. Cách này có thể hữu ích với một số tình huống cần cô lập trạng thái theo thread, nhưng làm tăng số lượng producer và tài nguyên kết nối. Ứng dụng phải gọi closeThreadBoundProducer() khi thread không còn sử dụng producer đó để giải phóng tài nguyên đúng cách.

Không nên bật producerPerThread chỉ vì ứng dụng có nhiều thread. Producer dùng chung đã được thiết kế để hỗ trợ truy cập đồng thời. Chỉ thay đổi chính sách khi có lý do kỹ thuật rõ ràng và đã đo lường tác động.

## 4. ConsumerFactory và DefaultKafkaConsumerFactory

### 4.1. ConsumerFactory giải quyết vấn đề gì?

KafkaConsumer là client đọc record từ Kafka. Khác với KafkaProducer, KafkaConsumer không thread-safe. Một consumer không được dùng đồng thời từ nhiều thread tùy ý.

Trong ứng dụng Spring Kafka, listener container quản lý consumer và vòng lặp poll. ConsumerFactory tạo các consumer theo cấu hình mà container yêu cầu. Nhờ đó, ứng dụng không cần tự tạo KafkaConsumer trong mỗi listener.

ConsumerFactory giúp tập trung:

- bootstrap server và group ID mặc định.
- key deserializer và value deserializer.
- auto commit, offset reset và các giới hạn poll/fetch.
- client ID và các thuộc tính kết nối.
- việc tạo consumer mới cho từng listener container hoặc child container.

DefaultKafkaConsumerFactory là implementation phổ biến. Mỗi lần container cần consumer, factory tạo một KafkaConsumer mới với cấu hình tương ứng. Các consumer này thuộc group được chỉ định và được Kafka group coordinator phân phối partition.

### 4.2. Mỗi consumer cần được sở hữu bởi một luồng xử lý

Mô hình tiêu biểu khi listener container có concurrency bằng ba:

~~~text
ConcurrentKafkaListenerContainerFactory
                  |
                  v
        ConcurrentMessageListenerContainer
             /          |          \
            v           v           v
       Child 1       Child 2       Child 3
            |           |           |
            v           v           v
       Consumer 1   Consumer 2   Consumer 3
            |           |           |
         Partition   Partition   Partition
~~~

Mỗi consumer được container quản lý theo vòng đời và luồng thực thi của nó. Container điều phối poll, gọi listener, xử lý exception và commit offset theo cấu hình.

Không nên lấy một KafkaConsumer rồi chia sẻ cho nhiều listener thread. Cách đó vi phạm mô hình thread-safety của KafkaConsumer và có thể dẫn tới lỗi truy cập đồng thời, trạng thái poll không hợp lệ hoặc lỗi khi commit.

### 4.3. Cấu hình consumer factory

ConsumerFactory sử dụng cấu hình Kafka ConsumerConfig cùng deserializer. Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| bootstrap.servers | Địa chỉ broker để khởi tạo kết nối |
| group.id | Tên consumer group |
| key.deserializer | Chuyển key từ byte về kiểu ứng dụng |
| value.deserializer | Chuyển value từ byte về kiểu ứng dụng |
| enable.auto.commit | Bật/tắt auto commit của Kafka client |
| auto.offset.reset | Vị trí bắt đầu khi group chưa có offset hợp lệ |
| max.poll.records | Số record tối đa trả về trong một lần poll |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa các lần poll trước khi consumer bị xem là không tiến triển |
| session.timeout.ms | Giới hạn thời gian session khi coordinator không nhận heartbeat |
| heartbeat.interval.ms | Chu kỳ gửi heartbeat trong cơ chế group membership |
| fetch.min.bytes | Lượng dữ liệu tối thiểu consumer mong muốn nhận trong fetch |
| client.id | Định danh client phục vụ theo dõi và metric |

Trong listener container, Spring Kafka thường quản lý việc commit offset dựa trên kết quả listener. Vì vậy, cấu hình enable.auto.commit=false thường được sử dụng để container kiểm soát acknowledgement và commit. Không nên bật auto commit mà không hiểu tác động của nó tới thời điểm xử lý thực tế.

Ví dụ tạo consumer factory:

~~~java
@Bean
public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    props.put(
        "spring.json.value.default.type",
        OrderCreated.class.getName()
    );
    props.put(
        "spring.json.trusted.packages",
        "com.example.orders.events"
    );

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Trong ví dụ, consumer đọc key dạng String và giải mã value thành OrderCreated. Cấu hình default type cần khớp với event contract mà ứng dụng muốn nhận. Trusted packages nên giới hạn trong package chứa các kiểu dữ liệu được phép giải mã, tránh mở rộng phạm vi không cần thiết.

Nếu producer gửi type header, consumer có thể sử dụng header để xác định kiểu theo cấu hình JsonDeserializer. Nếu ứng dụng không muốn phụ thuộc type header, cần thống nhất default type hoặc type mapping giữa các service. Điều quan trọng là hai phía phải hiểu cùng một schema và cùng ý nghĩa của payload.

### 4.4. Deserializer được tạo và cấu hình thế nào?

DefaultKafkaConsumerFactory có thể nhận cấu hình deserializer bằng class trong map, bằng instance hoặc bằng supplier tùy constructor và phiên bản Spring Kafka. Khi có nhiều consumer, cần tránh chia sẻ một deserializer có mutable state giữa các consumer nếu implementation đó không thread-safe.

Dùng class cấu hình trong map là cách đơn giản: Kafka client tạo deserializer cho từng consumer. Với deserializer tùy chỉnh, có thể dùng supplier để factory tạo instance riêng cho mỗi consumer. Cách này hữu ích khi deserializer có trạng thái, cần dependency hoặc phải được cấu hình riêng theo từng consumer.

Deserializer chịu trách nhiệm chuyển byte thành kiểu Java. Nó không thay thế validation nghiệp vụ. Một payload giải mã thành công vẫn có thể thiếu orderId, có tổng tiền âm hoặc vi phạm trạng thái đơn hàng; listener hoặc tầng application vẫn phải kiểm tra dữ liệu theo quy tắc nghiệp vụ.

## 5. ConsumerFactory không phải ConcurrentKafkaListenerContainerFactory

Đây là điểm dễ nhầm khi đọc cấu hình Spring Kafka.

| Đối tượng | Nó tạo ra | Nhiệm vụ |
| --- | --- | --- |
| DefaultKafkaConsumerFactory | Kafka Consumer | Tạo client đọc dữ liệu từ broker |
| ConcurrentKafkaListenerContainerFactory | Listener container | Tạo và cấu hình container thực thi @KafkaListener |
| KafkaMessageListenerContainer | Consumer và vòng lặp listener được quản lý | Poll và gọi listener với một consumer |
| ConcurrentMessageListenerContainer | Các child container | Điều phối nhiều consumer theo concurrency |

Ví dụ cấu hình listener container factory:

~~~java
@Bean(name = "kafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(orderConsumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Trong ví dụ:

- setConsumerFactory kết nối listener container factory với ConsumerFactory đã cấu hình.
- setConcurrency(3) yêu cầu container quản lý tối đa ba consumer cho listener này.
- AckMode.RECORD yêu cầu container commit tiến độ sau khi listener xử lý thành công từng record, theo các quy tắc và giới hạn của container.

Phương thức listener có thể chọn container factory bằng tên bean:

~~~java
@Component
public class BillingOrderListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.startBilling(event);
    }
}
~~~

Nếu ứng dụng chỉ có một listener container factory mặc định, thuộc tính containerFactory có thể được bỏ qua. Khi có nhiều cấu hình listener khác nhau, đặt tên bean rõ ràng và chỉ định containerFactory giúp tránh dùng nhầm consumer factory hoặc chính sách xử lý.

## 6. Cấu hình bằng Spring Boot và cấu hình factory thủ công

Có hai cách phổ biến để cấu hình Kafka client trong ứng dụng Spring Boot.

### 6.1. Để Spring Boot tự cấu hình

Khi có dependency Spring Kafka và cấu hình spring.kafka trong application.yml, Spring Boot có thể tạo các bean mặc định như ProducerFactory, ConsumerFactory, KafkaTemplate và listener container factory.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
    listener:
      ack-mode: record
      concurrency: 3
~~~

Cách này phù hợp khi ứng dụng dùng một cluster Kafka và cần cấu hình client theo môi trường. Spring Boot quản lý việc tạo các bean nền tảng, giúp giảm lượng mã cấu hình.

Không phải mọi thuộc tính Kafka đều có cùng cấp cấu hình. Các thuộc tính producer, consumer, listener và thuộc tính mở rộng cần đặt đúng nhánh. Nếu đặt nhầm producer property vào consumer hoặc ngược lại, client có thể không nhận cấu hình mong muốn.

### 6.2. Tự khai báo factory khi cần kiểm soát

Khi cần nhiều cluster, serializer đặc biệt, cấu hình transaction hoặc chính sách listener khác nhau, ứng dụng có thể tự khai báo bean ProducerFactory, ConsumerFactory và container factory.

Một cấu hình thủ công hoàn chỉnh có thể gồm:

~~~java
@Configuration
@EnableKafka
public class KafkaClientConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreated> orderProducerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> orderProducerFactory) {
        return new KafkaTemplate<>(orderProducerFactory);
    }

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class
        );
        props.put(
            "spring.json.value.default.type",
            OrderCreated.class.getName()
        );
        props.put(
            "spring.json.trusted.packages",
            "com.example.orders.events"
        );

        return new DefaultKafkaConsumerFactory<>(props);
    }

    @Bean(name = "kafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Các import được lược bỏ để tập trung vào quan hệ giữa bean. Ví dụ dùng API Spring Kafka hiện đại; chữ ký constructor hoặc tùy chọn cấu hình cụ thể có thể khác giữa các phiên bản. Cần đối chiếu phiên bản Spring Boot và Spring Kafka mà dự án đang dùng trước khi sao chép cấu hình.

Khi tự khai báo bean, cần hiểu cơ chế auto-configuration của Spring Boot. Một số cấu hình mặc định sẽ nhường chỗ cho bean ứng dụng cung cấp. Nếu đã tự tạo ProducerFactory hoặc ConsumerFactory, hãy kiểm tra các bean phụ thuộc như KafkaTemplate và listener container factory có đang được nối với đúng factory hay không.

### 6.3. Chọn cách cấu hình nào?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một Kafka cluster, cấu hình serializer/deserializer tiêu chuẩn | Spring Boot properties |
| Muốn thay ack mode hoặc concurrency cho listener | Cấu hình listener container factory |
| Nhiều Kafka cluster độc lập | Khai báo factory và template/container factory riêng |
| Cần transaction producer | Cấu hình DefaultKafkaProducerFactory với transaction ID prefix |
| Serializer/deserializer tùy chỉnh | Cấu hình factory với class, instance hoặc supplier thích hợp |
| Muốn test với broker khác môi trường chạy | Override properties hoặc cung cấp factory riêng trong test |

Không cần tạo factory riêng cho mọi topic. Nếu các topic cùng cluster và dùng chung kiểu key/value, serializer và chính sách client, một ProducerFactory có thể phục vụ nhiều topic. Tương tự, một ConsumerFactory có thể phục vụ nhiều listener cùng cấu hình client cơ bản; từng listener container vẫn có thể có concurrency, group hoặc error handling riêng.

## 7. Nhiều factory và nhiều Kafka cluster

Một ứng dụng có thể kết nối nhiều Kafka cluster, chẳng hạn cluster nội bộ cho event nghiệp vụ và cluster riêng để trao đổi dữ liệu với hệ thống đối tác. Mỗi cluster có thể có bootstrap server, credential, serializer, timeout và chính sách bảo mật khác nhau.

Trong trường hợp này, nên tạo các bean có tên rõ ràng:

~~~java
@Bean("internalProducerFactory")
ProducerFactory<String, OrderCreated> internalProducerFactory() {
    // Cấu hình cluster nội bộ
}

@Bean("partnerProducerFactory")
ProducerFactory<String, PartnerEvent> partnerProducerFactory() {
    // Cấu hình cluster đối tác
}

@Bean("internalKafkaTemplate")
KafkaTemplate<String, OrderCreated> internalKafkaTemplate(
        @Qualifier("internalProducerFactory")
        ProducerFactory<String, OrderCreated> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}

@Bean("partnerKafkaTemplate")
KafkaTemplate<String, PartnerEvent> partnerKafkaTemplate(
        @Qualifier("partnerProducerFactory")
        ProducerFactory<String, PartnerEvent> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
~~~

Đoạn mã trên minh họa cách đặt tên và inject đúng factory; phần cấu hình cụ thể được lược bỏ. Với consumer, có thể tạo các ConsumerFactory và listener container factory tương ứng rồi chỉ định containerFactory trên từng @KafkaListener.

Khi có nhiều bean cùng interface hoặc cùng generic type, dùng @Qualifier để tránh Spring inject nhầm. Tên bean nên thể hiện cluster hoặc mục đích nghiệp vụ, không chỉ đặt tên chung chung như factory1 và factory2.

Cần lưu ý một factory gắn với cấu hình cluster và serializer/deserializer của nó. Không nên dùng KafkaTemplate của cluster này để gửi vào cluster khác chỉ bằng cách đổi topic. Địa chỉ broker thuộc producer factory, không thuộc tên topic.

## 8. Factory và transaction

ProducerFactory có vai trò quan trọng khi ứng dụng dùng Kafka transaction. Với DefaultKafkaProducerFactory, có thể cấu hình transaction ID prefix để factory tạo các producer transactional.

Ví dụ:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> transactionalProducerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    props.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );
    props.put(ProducerConfig.ACKS_CONFIG, "all");

    var factory =
        new DefaultKafkaProducerFactory<String, OrderCreated>(props);

    factory.setTransactionIdPrefix("orders-tx-instance-a-");
    return factory;
}
~~~

Transaction ID prefix cần duy nhất giữa các instance ứng dụng đang hoạt động đồng thời. Khi chạy nhiều replica, mỗi instance phải có prefix riêng để tránh xung đột transactional ID. Trong triển khai thực tế, prefix thường được ghép từ tên dịch vụ và định danh instance ổn định trong vòng đời tiến trình.

Khi factory được cấu hình transaction ID prefix, nó quản lý producer transactional và tái sử dụng producer đã hoàn tất transaction theo chính sách cache. Không nên tự đặt một transactional.id cố định dùng chung cho nhiều instance nếu factory đang chịu trách nhiệm cấp ID.

Có thể tạo KafkaTransactionManager từ ProducerFactory để tích hợp transaction Kafka với cơ chế transaction của Spring:

~~~java
@Bean
public KafkaTransactionManager<String, OrderCreated> kafkaTransactionManager(
        ProducerFactory<String, OrderCreated> transactionalProducerFactory) {
    return new KafkaTransactionManager<>(transactionalProducerFactory);
}
~~~

Cách áp dụng transaction phụ thuộc luồng xử lý: gửi nhiều record trong cùng transaction, dùng @Transactional với transaction manager tương ứng, hoặc cấu hình listener container tham gia Kafka transaction. Cần chọn đúng ranh giới transaction và xác minh hành vi khi listener ném exception.

Kafka transaction có thể phối hợp việc ghi record vào Kafka và commit offset trong Kafka theo cấu hình phù hợp. Nó không tự động bao trùm thao tác ghi database, gọi REST API hoặc gửi email. Với tác dụng phụ ngoài Kafka, vẫn cần thiết kế idempotency, outbox/inbox hoặc cơ chế nhất quán phù hợp.

## 9. Concurrency, số lượng client và partition

Concurrency của listener container quyết định số consumer mà container có thể tạo để xử lý song song. ConsumerFactory tạo từng consumer theo yêu cầu đó.

Ví dụ topic có sáu partition và listener container có concurrency bằng ba. Group có thể phân phối sáu partition cho ba consumer, mỗi consumer phụ trách một hoặc nhiều partition. Nếu tăng concurrency lên tám, group vẫn chỉ có sáu partition để phân phối; một số consumer có thể không được gán partition.

Một vài nguyên tắc:

- Số consumer hoạt động hữu ích trong một group bị giới hạn bởi số partition được assign cho group.
- Một partition tại một thời điểm chỉ được gán cho tối đa một consumer trong cùng group.
- Tăng concurrency làm tăng số consumer, kết nối và nhu cầu tài nguyên.
- Nhiều consumer không đồng nghĩa throughput chắc chắn tăng; còn phụ thuộc thời gian xử lý, broker, network, batch và dependency phía sau.
- Rebalance có thể xảy ra khi thành viên group thay đổi hoặc consumer không poll đúng giới hạn.

ProducerFactory và ConsumerFactory có mô hình tài nguyên khác nhau. Producer mặc định có thể được chia sẻ giữa nhiều thread; consumer cần được sở hữu bởi luồng/container tương ứng. Không nên áp dụng tư duy chia sẻ producer sang consumer.

## 10. Vòng đời và đóng tài nguyên

Trong ứng dụng Spring, factory và template thường là bean do container quản lý. Cần để Spring quản lý vòng đời thay vì đóng client tùy tiện trong service nghiệp vụ.

### 10.1. Producer

KafkaTemplate lấy producer từ ProducerFactory khi cần gửi. Với producer dùng chung, factory tái sử dụng client. Với producer transactional, factory quản lý việc cấp phát và thu hồi producer theo transaction. Khi application context dừng, factory đóng producer và tài nguyên liên quan.

Không nên gọi close() trên producer dùng chung sau mỗi lần gửi. Nếu tự lấy producer trực tiếp từ factory cho một thao tác đặc biệt, phải tuân theo hợp đồng lấy/trả tài nguyên của factory và phiên bản API đang dùng.

### 10.2. Consumer

Listener container tạo consumer từ ConsumerFactory khi container khởi động. Khi container dừng, nó kết thúc vòng poll, thực hiện quy trình shutdown/commit phù hợp và đóng consumer.

Không nên tự đóng consumer đang được listener container quản lý. Cũng không nên tự tạo một KafkaConsumer dùng chung bên trong singleton service để nhiều thread gọi poll hoặc commit.

### 10.3. Shutdown có trật tự

Khi ứng dụng dừng, container cần có thời gian để ngừng nhận record mới và hoàn tất phần xử lý đang chạy theo cấu hình shutdown. Nếu thời gian xử lý listener dài hơn thời gian shutdown được cấp, ứng dụng có thể bị dừng trước khi hoàn tất. Vì vậy, timeout shutdown, thời gian xử lý nghiệp vụ và commit offset cần được xem xét cùng nhau.

## 11. Kiểm thử factory và cấu hình listener

Factory là thành phần hạ tầng nên cần kiểm thử ở mức phù hợp. Có thể chia thành ba lớp:

1. Kiểm tra cấu hình: xác nhận bean được tạo, dùng đúng bootstrap server, serializer/deserializer và group.
2. Kiểm thử tích hợp với Kafka: gửi event qua KafkaTemplate, nhận qua @KafkaListener và xác nhận payload/metadata.
3. Kiểm thử lỗi và vòng đời: xác nhận hành vi khi deserialize lỗi, broker tạm mất kết nối, listener thất bại hoặc container dừng.

Có thể dùng Embedded Kafka trong Spring Kafka hoặc Testcontainers để chạy broker thật trong kiểm thử tích hợp. Broker thật giúp xác nhận serialization, partition, group assignment và commit offset đúng với hành vi Kafka. Mock producer/consumer hữu ích cho unit test một số nhánh logic, nhưng không thay thế kiểm thử tích hợp khi cần xác nhận tương tác với broker.

Một bài test tích hợp nên kiểm tra ít nhất:

- ProducerFactory và KafkaTemplate gửi đúng topic, key và payload.
- ConsumerFactory tạo consumer với đúng group và deserializer.
- Listener container gọi đúng listener.
- Payload sau deserialize giữ đúng dữ liệu.
- Lỗi trong listener đi qua error handler theo cấu hình.
- Consumer được đóng khi container dừng.

Không nên chỉ kiểm tra ApplicationContext khởi động thành công rồi kết luận luồng messaging hoạt động. Cấu hình serializer có thể đúng về mặt bean nhưng sai định dạng với consumer; listener container có thể khởi động nhưng không được gán partition; hoặc listener nhận được record nhưng commit không đúng mong đợi.

## 12. Lỗi cấu hình thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| KafkaTemplate không gửi được record | ProducerFactory dùng sai bootstrap server, ACL hoặc serializer | Kiểm tra exception từ future, producer properties, broker và serializer |
| Producer gửi thành công nhưng consumer không nhận | ConsumerFactory dùng sai cluster/topic/group hoặc không có partition assignment | Kiểm tra cluster, subscription, group state, assignment và offset |
| Listener lỗi deserialize | Value deserializer hoặc default type không khớp payload | Kiểm tra byte format, type header, trusted packages và event contract |
| Tạo quá nhiều kết nối producer | Nhiều factory/producer được tạo không cần thiết hoặc bật producerPerThread | Kiểm tra bean scope, số factory, chính sách producer và vòng đời thread |
| Consumer bị rebalance liên tục | Xử lý quá lâu giữa các lần poll, heartbeat hoặc kết nối không ổn định | Kiểm tra max.poll.interval.ms, session.timeout.ms, thời gian listener và log group |
| Listener không chạy dù container đã tạo | Consumer không được gán partition hoặc listener dùng nhầm container factory | Kiểm tra group assignment, topic, bean name và thuộc tính containerFactory |
| Bean injection bị mơ hồ | Có nhiều ProducerFactory/ConsumerFactory cùng kiểu | Dùng @Qualifier hoặc tên bean rõ ràng |
| Transactional producer không khởi tạo | Transaction ID prefix thiếu hoặc xung đột giữa các instance | Kiểm tra cấu hình transaction và tính duy nhất của prefix |

Khi điều tra, hãy xác định lỗi xảy ra ở tầng nào: factory không tạo được client, client không kết nối được broker, serialization/deserialization thất bại, container không được cấu hình đúng hay listener xử lý lỗi. Không nên quy mọi lỗi gửi/nhận về ProducerFactory hoặc ConsumerFactory chỉ vì chúng đứng ở tầng cấu hình.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| ProducerFactory chính là KafkaProducer. | Factory tạo và quản lý producer; KafkaProducer là client giao tiếp với broker. |
| ConsumerFactory là listener container. | ConsumerFactory tạo consumer; listener container quản lý poll và gọi listener. |
| ConcurrentKafkaListenerContainerFactory tạo Kafka consumer trực tiếp. | Nó tạo listener container; container dùng ConsumerFactory để tạo consumer. |
| Mỗi lời gọi KafkaTemplate.send tạo một producer mới. | Factory mặc định tái sử dụng producer dùng chung; transaction và tùy chọn factory có chính sách riêng. |
| Có thể chia sẻ một KafkaConsumer cho nhiều thread. | KafkaConsumer không thread-safe; container quản lý consumer theo luồng phù hợp. |
| Tăng concurrency luôn tăng throughput. | Concurrency còn bị giới hạn bởi partition, năng lực xử lý và tài nguyên. |
| Một factory chỉ dùng được cho một topic. | Factory có thể phục vụ nhiều topic nếu cùng cluster và cấu hình client tương thích. |
| Đổi tên topic sẽ đổi Kafka cluster. | Cluster được xác định bởi bootstrap server trong factory; topic chỉ là luồng dữ liệu trong cluster. |
| Factory tự xử lý mọi lỗi nghiệp vụ. | Factory quản lý client; retry, DLT và logic nghiệp vụ thuộc listener container/error handler và application. |
| Dùng Kafka transaction sẽ bao gồm database. | Kafka transaction không tự động bao trùm hệ thống bên ngoài Kafka. |

## 14. Checklist thiết kế factory cho một ứng dụng Spring Kafka

Trước khi đưa cấu hình vào ứng dụng, hãy trả lời các câu hỏi sau:

1. Ứng dụng kết nối một hay nhiều Kafka cluster?
2. Mỗi cluster cần ProducerFactory và ConsumerFactory nào?
3. Key và value dùng kiểu dữ liệu nào; serializer/deserializer có tương thích không?
4. Producer cần mức acks, idempotence, retry và timeout nào?
5. Consumer group được đặt tên ra sao; auto commit có được tắt để container quản lý offset không?
6. Listener cần concurrency bao nhiêu và topic có đủ partition không?
7. Có cần listener container factory riêng cho batch, acknowledgement hoặc error handling không?
8. Có dùng Kafka transaction không; transaction ID prefix có duy nhất giữa các instance không?
9. Bean nào được Spring Boot auto-configure và bean nào được ứng dụng tự khai báo?
10. Ai sở hữu vòng đời client và tài nguyên được đóng ở đâu?
11. Có kiểm thử tích hợp xác nhận serialization, listener, offset và shutdown không?

Khi các câu hỏi này được trả lời rõ, ProducerFactory và ConsumerFactory trở thành ranh giới cấu hình ổn định giữa tầng nghiệp vụ và Kafka client. Service nghiệp vụ có thể tập trung vào event cần gửi hoặc xử lý; tầng messaging chịu trách nhiệm tạo client, áp dụng cấu hình, điều phối listener và quản lý tài nguyên theo vòng đời ứng dụng.

