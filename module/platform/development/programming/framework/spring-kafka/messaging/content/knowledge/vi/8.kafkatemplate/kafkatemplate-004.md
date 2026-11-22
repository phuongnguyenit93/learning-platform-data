# sendDefault với default topic

`KafkaTemplate` là API gửi record phổ biến trong Spring Kafka. Khi gọi các phương thức như `send(topic, value)` hoặc `send(topic, key, value)`, code phải truyền tên topic ở từng lần gửi. Nếu một template chủ yếu gửi vào một topic, có thể cấu hình topic mặc định trên chính `KafkaTemplate` rồi dùng các phương thức `sendDefault(...)`.

`sendDefault` giúp lời gọi ngắn gọn hơn và làm rõ rằng template được thiết kế để gửi vào một topic đã chọn trước. Nó vẫn dùng cùng ProducerFactory, Kafka producer, serializer, partitioner, acknowledgement, retry và cơ chế transaction như các phương thức send khác. Default topic chỉ là giá trị cấu hình ở tầng KafkaTemplate; nó không phải cấu hình mặc định của Kafka broker và cũng không tự tạo topic trên cluster.

Bài học thuộc chương **KafkaTemplate** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, KafkaTemplate và @KafkaListener, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Khi nào nên dùng sendDefault?

Giả sử một service chỉ phát sự kiện đơn hàng vào topic `order-events`. Nếu mỗi phương thức đều viết:

~~~java
kafkaTemplate.send("order-events", event);
kafkaTemplate.send("order-events", event.orderId(), event);
~~~

tên topic bị lặp lại ở nhiều nơi. Khi topic thay đổi, phải tìm và sửa nhiều lời gọi. Có thể cấu hình một KafkaTemplate với default topic:

~~~java
kafkaTemplate.setDefaultTopic("order-events");
~~~

Sau đó gửi bằng:

~~~java
kafkaTemplate.sendDefault(event);
kafkaTemplate.sendDefault(event.orderId(), event);
~~~

Các lời gọi trên sử dụng default topic đã cấu hình. Code nghiệp vụ tập trung vào payload và key thay vì lặp tên topic.

sendDefault phù hợp khi:

- Một KafkaTemplate được thiết kế để gửi chủ yếu vào một topic.
- Một publisher/service có trách nhiệm phát một loại event vào một topic xác định.
- Muốn tập trung tên topic tại cấu hình bean hoặc application properties.
- Muốn giảm lỗi gõ sai tên topic giữa các phương thức gửi cùng loại event.

Nên dùng send với topic tường minh khi cùng một template phải gửi nhiều topic khác nhau hoặc topic được quyết định động theo nghiệp vụ. Default topic không nên được dùng để che giấu việc publisher đang gửi tới nhiều luồng dữ liệu không liên quan.

## 2. Default topic thuộc về KafkaTemplate

Mỗi KafkaTemplate có thể được cấu hình một default topic riêng. Nó không phải một thuộc tính toàn cục của Kafka cluster, consumer group hay ProducerFactory.

Kiến trúc gửi với default topic:

~~~mermaid
flowchart TD
    A[Service nghiệp vụ] --> B[KafkaTemplate]
    C[Default topic cấu hình trên template] --> B
    B --> D[sendDefault]
    D --> E[ProducerFactory]
    E --> F[Kafka Producer]
    F --> G[Serializer và partitioner]
    G --> H[Kafka broker]
~~~

KafkaTemplate kết hợp default topic với key/value hoặc partition được truyền vào sendDefault. Sau đó nó đi theo cùng đường gửi như khi gọi send với topic tường minh.

Điều này dẫn tới ba điểm:

1. Đổi default topic trên một KafkaTemplate chỉ ảnh hưởng những lời gọi sendDefault dùng template đó.
2. Các lời gọi send(topic, ...) vẫn sử dụng topic truyền trực tiếp trong lời gọi.
3. Cấu hình default topic không thay đổi topic đã được lưu trên broker và không tự tạo topic.

Nếu ứng dụng có nhiều publisher với topic mặc định khác nhau, có thể tạo nhiều KafkaTemplate bean được đặt tên rõ ràng và inject bằng @Qualifier.

## 3. Cấu hình default topic bằng Spring Boot

Spring Boot hỗ trợ cấu hình default topic của KafkaTemplate qua thuộc tính `spring.kafka.template.default-topic`.

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    template:
      default-topic: order-events
~~~

Trong cấu hình này:

- `bootstrap-servers` xác định địa chỉ broker dùng để khởi tạo kết nối.
- `key-serializer` và `value-serializer` xác định cách chuyển key/value thành byte.
- `acks` điều khiển mức broker xác nhận record.
- `template.default-topic` là topic mặc định Spring Boot áp dụng cho KafkaTemplate được auto-configure.

Khi dùng Spring Boot auto-configuration, có thể inject KafkaTemplate và gọi sendDefault:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.sendDefault(event.orderId(), event);
    }
}
~~~

Không cần gọi setDefaultTopic lần nữa nếu Spring Boot đã cấu hình template theo application.yml. Nên chọn một nơi quản lý default topic để tránh cấu hình trùng lặp và khó xác định giá trị cuối cùng.

Giá trị default topic có thể được override theo môi trường bằng cơ chế externalized configuration của Spring Boot. Ví dụ local, test và production có thể dùng các cluster hoặc topic naming convention khác nhau.

## 4. Cấu hình default topic bằng Java

Nếu tự tạo KafkaTemplate bean, có thể gọi setDefaultTopic trong lúc khởi tạo bean:

~~~java
@Configuration
public class KafkaTemplateConfiguration {

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
            ProducerFactory<String, OrderCreated> producerFactory) {

        KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);

        template.setDefaultTopic("order-events");
        return template;
    }
}
~~~

Trong ví dụ:

- ProducerFactory cung cấp Kafka producer và các cấu hình client.
- KafkaTemplate cung cấp API gửi record.
- setDefaultTopic gán topic mặc định cho template.
- Publisher inject bean này và dùng sendDefault.

Nên cấu hình default topic khi tạo bean, trước khi bean được sử dụng để gửi record. Không nên thay đổi default topic liên tục trong lúc nhiều thread đang dùng chung template, vì điều đó làm cho topic đích của sendDefault phụ thuộc thời điểm lời gọi đọc cấu hình.

Nếu cần gửi tới các topic khác nhau theo từng nghiệp vụ, hãy truyền topic tường minh hoặc tạo các template riêng có trách nhiệm rõ ràng.

## 5. Các overload sendDefault thường dùng

KafkaTemplate cung cấp các overload sendDefault để gửi value, key/value hoặc partition/key/value vào default topic.

| Phương thức | Ý nghĩa |
| --- | --- |
| `sendDefault(V data)` | Gửi value, không cung cấp key và không chỉ định partition. |
| `sendDefault(K key, V data)` | Gửi key và value; partitioner chọn partition dựa trên key. |
| `sendDefault(Integer partition, K key, V data)` | Gửi vào partition được chỉ định của default topic, với key/value tương ứng. |

### 5.1. Gửi chỉ có value

~~~java
kafkaTemplate.sendDefault(event);
~~~

Lời gọi này không truyền key. Producer dùng partitioner để chọn partition theo cấu hình và phiên bản Kafka client. Nếu dùng partitioner mặc định hiện đại, record không key thường được xử lý bằng sticky partitioning để tối ưu batching.

### 5.2. Gửi key và value

~~~java
kafkaTemplate.sendDefault(event.orderId(), event);
~~~

Key giúp partitioner định tuyến các event cùng orderId về cùng partition theo thuật toán mặc định. Đây là lựa chọn phù hợp khi nghiệp vụ cần giữ thứ tự các thay đổi của cùng một đơn hàng trong phạm vi partition.

### 5.3. Chỉ định partition

~~~java
kafkaTemplate.sendDefault(2, event.orderId(), event);
~~~

Lời gọi yêu cầu gửi record vào partition số 2 của default topic. Partition phải tồn tại trong topic. Việc chỉ định partition có ưu tiên hơn việc để partitioner tự chọn.

Chỉ định partition trực tiếp có thể hữu ích khi ứng dụng có chiến lược phân vùng riêng, nhưng không nên hard-code partition nếu chưa hiểu tác động của thay đổi số partition và topology cluster.

Các overload có thể khác nhau giữa các phiên bản Spring Kafka. Khi cần timestamp hoặc headers riêng, có thể tạo ProducerRecord và gửi qua phương thức send(ProducerRecord) phù hợp với API đang dùng. Hãy đối chiếu Javadoc của phiên bản dependency thay vì giả định mọi phiên bản có cùng chữ ký.

## 6. Ví dụ publisher sử dụng sendDefault

Giả sử ứng dụng có event:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
~~~

Cấu hình KafkaTemplate có default topic là order-events. Publisher có thể cung cấp các phương thức theo nhu cầu nghiệp vụ:

~~~java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate.sendDefault(event.orderId(), event);
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publishWithoutKey(
            OrderCreated event) {

        return kafkaTemplate.sendDefault(event);
    }
}
~~~

Phương thức publish dùng orderId làm key để các event của cùng đơn hàng được định tuyến ổn định theo partitioner. Phương thức publishWithoutKey gửi record không key, phù hợp khi không cần thứ tự theo orderId.

Dù dùng sendDefault, producer vẫn phải serialize event. Nếu JsonSerializer được cấu hình cho value, OrderCreated được chuyển thành JSON byte trước khi gửi. Consumer phải có deserializer và contract tương thích để đọc payload.

## 7. sendDefault không tự tạo topic

Default topic chỉ là tên topic mà KafkaTemplate dùng khi gửi. Nó không tạo topic trong broker.

Topic cần được provision bằng một trong các cách:

- Khai báo NewTopic bean cùng KafkaAdmin trong ứng dụng.
- Tạo topic qua Kafka Admin API hoặc CLI.
- Dùng pipeline hạ tầng như Terraform hoặc quy trình quản trị cluster.
- Dùng cơ chế auto-create topic của broker nếu môi trường cho phép, dù production thường cần quản lý topic có chủ đích.

Ví dụ khai báo NewTopic bean:

~~~java
@Bean
public NewTopic orderEventsTopic() {
    return TopicBuilder.name("order-events")
        .partitions(6)
        .replicas(3)
        .build();
}
~~~

Tên trong TopicBuilder phải khớp với default topic của KafkaTemplate. Nếu default topic là order-events nhưng topic được tạo là order-event, producer sẽ gửi tới tên khác và có thể nhận lỗi UnknownTopicOrPartition hoặc tạo topic ngoài dự kiến nếu broker cho phép auto-create.

Nếu topic chưa tồn tại và broker không tự tạo, send có thể thất bại khi producer lấy metadata hoặc gửi record. Cần kiểm tra topic và quyền ACL khi triển khai.

## 8. Kết quả gửi và xử lý bất đồng bộ

sendDefault trả về kết quả bất đồng bộ tương tự send. Trong Spring Kafka 3.x, kiểu trả về là CompletableFuture<SendResult<K,V>>. Future hoàn tất khi producer nhận kết quả theo acknowledgement đã cấu hình hoặc khi thao tác gửi thất bại.

Ví dụ ghi metadata:

~~~java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.sendDefault(event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Không gửi được orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Đã gửi orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

RecordMetadata cho biết topic, partition, offset và timestamp của record được broker ghi nhận. Đây là dữ liệu hữu ích để truy vết event giữa producer và consumer.

Không nên xem việc gọi sendDefault không ném exception đồng bộ là bằng chứng gửi thành công. Lỗi mạng hoặc lỗi broker có thể được báo về future sau khi phương thức đã trả về. Nếu caller cần biết kết quả trước khi phản hồi, có thể chờ future trong một giới hạn timeout có chủ đích; cần cân nhắc việc chặn thread và tác động đến throughput.

Ở các phiên bản Spring Kafka trước 3.x, kiểu future trả về có thể là ListenableFuture thay vì CompletableFuture. Hãy dùng đúng API của phiên bản dự án.

## 9. sendDefault có giữ nguyên key và partition semantics không?

Có. sendDefault không thay đổi cách Kafka xử lý key hoặc partition. Nó chỉ lấy topic từ default topic đã cấu hình rồi chuyển record sang cùng cơ chế producer.

| Cách gọi | Topic | Key | Partition |
| --- | --- | --- | --- |
| sendDefault(value) | Default topic | null | Partitioner chọn |
| sendDefault(key, value) | Default topic | key được truyền | Partitioner chọn theo key |
| sendDefault(partition, key, value) | Default topic | key được truyền | Partition chỉ định |
| send(topic, key, value) | Topic truyền trực tiếp | key được truyền | Partitioner chọn theo key |

Nếu key null, partitioner dùng chiến lược dành cho record không key. Nếu key khác null, partitioner mặc định thường sử dụng key đã serialize để chọn partition. Nếu partition được chỉ định, producer gửi vào partition đó.

sendDefault không bảo đảm thứ tự toàn topic. Kafka chỉ bảo đảm thứ tự trong một partition. Nếu nghiệp vụ cần tuần tự theo orderId, hãy truyền orderId làm key và thiết kế số partition ổn định.

## 10. Một template hay nhiều template?

Một KafkaTemplate có default topic phù hợp khi một nhóm publisher cùng gửi vào một topic. Nếu một service gửi nhiều loại event tới các topic khác nhau, có hai lựa chọn.

### 10.1. Dùng một template và truyền topic tường minh

~~~java
kafkaTemplate.send("order-events", orderEvent);
kafkaTemplate.send("payment-events", paymentEvent);
~~~

Cách này phù hợp khi các topic dùng chung ProducerFactory, serializer và cluster. Topic được quyết định tại thời điểm gọi.

### 10.2. Dùng nhiều template có default topic riêng

~~~java
@Bean("orderKafkaTemplate")
KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {
    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(producerFactory);
    template.setDefaultTopic("order-events");
    return template;
}

@Bean("paymentKafkaTemplate")
KafkaTemplate<String, PaymentCompleted> paymentKafkaTemplate(
        ProducerFactory<String, PaymentCompleted> producerFactory) {
    KafkaTemplate<String, PaymentCompleted> template =
        new KafkaTemplate<>(producerFactory);
    template.setDefaultTopic("payment-events");
    return template;
}
~~~

Publisher inject đúng template:

~~~java
@Service
@RequiredArgsConstructor
public class PaymentEventPublisher {

    @Qualifier("paymentKafkaTemplate")
    private final KafkaTemplate<String, PaymentCompleted> kafkaTemplate;

    public CompletableFuture<SendResult<String, PaymentCompleted>> publish(
            PaymentCompleted event) {
        return kafkaTemplate.sendDefault(event.paymentId(), event);
    }
}
~~~

Ví dụ trên minh họa cách đặt tên bean và chọn template. Nếu nhiều bean cùng kiểu generic, nên dùng @Qualifier hoặc constructor injection có qualifier rõ ràng để tránh Spring inject nhầm.

Không nên tạo nhiều template chỉ vì mỗi topic có một tên khác nếu chúng dùng chung cấu hình. Nhiều template hợp lý khi cần phân tách default topic, kiểu payload, cluster hoặc chính sách producer.

## 11. sendDefault trong transaction

Nếu KafkaTemplate được cấu hình với transactional ProducerFactory và đang tham gia Kafka transaction, sendDefault gửi record vào default topic trong cùng transaction như các phương thức send khác.

Ví dụ về mặt sử dụng:

~~~java
@Transactional("kafkaTransactionManager")
public void publishOrder(OrderCreated event) {
    kafkaTemplate.sendDefault(event.orderId(), event);
}
~~~

Đoạn code chỉ minh họa cách gọi trong transaction; ứng dụng phải cấu hình KafkaTransactionManager và ProducerFactory có transaction ID prefix phù hợp. Transaction ID prefix cần duy nhất giữa các instance ứng dụng chạy đồng thời.

sendDefault không tự mở transaction chỉ vì tên phương thức có chữ default. Transaction phụ thuộc cấu hình template, transaction manager và ranh giới transaction đang hoạt động.

Kafka transaction có thể phối hợp việc ghi record và commit offset trong Kafka theo cấu hình phù hợp. Nó không tự động bao trùm thao tác database, HTTP hoặc email. Nếu service vừa cập nhật database vừa gửi event, cần thiết kế outbox hoặc cơ chế nhất quán phù hợp để xử lý khoảng hở giữa hai hệ thống.

## 12. Kiểm thử default topic

Một bài test nên xác nhận template thực sự gửi vào topic mặc định mà không cần truyền tên topic trong lời gọi.

Có thể dùng Embedded Kafka hoặc Testcontainers để chạy broker cho integration test. Test cần:

1. Khởi tạo KafkaTemplate với default topic.
2. Gửi record bằng sendDefault.
3. Chờ future hoàn tất trong timeout hữu hạn.
4. Xác nhận RecordMetadata.topic() đúng default topic.
5. Xác nhận key và value theo mong đợi.
6. Đọc record từ consumer test nếu cần kiểm tra end-to-end.

Ví dụ:

~~~java
@Test
void shouldSendToConfiguredDefaultTopic() throws Exception {
    OrderCreated event = new OrderCreated(
        "evt-100",
        "order-100",
        new BigDecimal("125.50"),
        Instant.now()
    );

    SendResult<String, OrderCreated> result =
        kafkaTemplate.sendDefault(event.orderId(), event)
            .get(10, TimeUnit.SECONDS);

    assertThat(result.getRecordMetadata().topic())
        .isEqualTo("order-events");
    assertThat(result.getRecordMetadata().partition())
        .isGreaterThanOrEqualTo(0);
    assertThat(result.getRecordMetadata().offset())
        .isGreaterThanOrEqualTo(0);
}
~~~

Test cần có broker, topic order-events và KafkaTemplate đã cấu hình default topic. Không nên chỉ assert future khác null; phải chờ kết quả và kiểm tra metadata để chứng minh record được gửi tới đúng topic.

Có thể bổ sung test cho các trường hợp:

- Template chưa được cấu hình default topic.
- Topic không tồn tại hoặc producer không có quyền ghi.
- Serializer thất bại với payload không hợp lệ.
- Broker tạm thời không khả dụng.
- Gửi trong transaction rồi commit hoặc rollback.
- Template có default topic riêng nhưng lời gọi send(topic, value) vẫn dùng topic truyền trực tiếp.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| sendDefault báo lỗi khi gọi | KafkaTemplate chưa có default topic | Kiểm tra spring.kafka.template.default-topic hoặc setDefaultTopic |
| Record vào nhầm topic | Inject nhầm KafkaTemplate hoặc cấu hình default topic sai | Kiểm tra bean name, @Qualifier và giá trị cấu hình theo môi trường |
| sendDefault không tạo topic | Default topic chỉ là tên đích, không phải khai báo NewTopic | Provision topic bằng KafkaAdmin/NewTopic hoặc quy trình hạ tầng |
| Producer nhận UnknownTopicOrPartition | Topic chưa tồn tại, sai cluster hoặc metadata chưa cập nhật | Kiểm tra bootstrap server, topic metadata và ACL |
| Payload không deserialize được | Serializer producer và deserializer consumer không tương thích | Kiểm tra JSON/schema/type header và event contract |
| Gửi không key nhưng mong record vào partition cụ thể | Không truyền partition và đang dựa vào partitioner mặc định | Dùng overload có partition hoặc thiết kế key phù hợp |
| Thay đổi default topic lúc runtime gây khó truy vết | Nhiều thread dùng chung template trong khi cấu hình bị thay đổi | Cấu hình cố định khi khởi tạo bean hoặc tạo template riêng |
| Future báo lỗi sau khi phương thức đã trả về | Gửi bất đồng bộ | Quan sát CompletableFuture/callback và xử lý lỗi |
| Nhầm sendDefault với gửi vào topic mặc định của broker | Default topic là cấu hình trên KafkaTemplate | Kiểm tra template đang được inject và cấu hình của nó |

## 14. Checklist sử dụng sendDefault

Trước khi dùng sendDefault, hãy xác nhận:

1. KafkaTemplate có default topic rõ ràng và được cấu hình lúc khởi tạo.
2. Default topic tồn tại hoặc có quy trình tạo topic tương ứng.
3. ProducerFactory kết nối đúng Kafka cluster.
4. Serializer key/value phù hợp với kiểu dữ liệu gửi.
5. Key có được truyền hay không phản ánh đúng yêu cầu partitioning.
6. Partition chỉ được chỉ định khi ứng dụng thực sự cần điều khiển đích.
7. Future/callback được quan sát để phát hiện lỗi gửi bất đồng bộ.
8. Nhiều KafkaTemplate bean có tên và qualifier rõ ràng.
9. Transaction chỉ được sử dụng khi ProducerFactory và transaction manager đã cấu hình đúng.
10. Integration test xác nhận metadata topic đúng với default topic mong muốn.

sendDefault giúp giảm lặp tên topic và làm cho publisher thể hiện rõ trách nhiệm gửi vào một luồng dữ liệu đã chọn trước. Giá trị của nó nằm ở cấu hình tập trung và code nghiệp vụ gọn hơn; mọi semantics về serialization, partition, acknowledgement, retry và transaction vẫn do cấu hình producer cùng KafkaTemplate hiện có quyết định.

