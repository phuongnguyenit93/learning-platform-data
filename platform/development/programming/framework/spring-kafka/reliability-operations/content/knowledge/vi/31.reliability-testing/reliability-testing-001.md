# Test producer send thành công

Trong Spring Kafka, gọi được phương thức **KafkaTemplate.send()** chưa có nghĩa message đã được broker ghi nhận. Producer gửi dữ liệu bất đồng bộ: lời gọi ban đầu thường chỉ đưa record vào luồng gửi của client. Kết quả cuối cùng được trả về sau khi broker phản hồi hoặc khi lần gửi thất bại.

Vì vậy, một bài kiểm thử producer thành công cần xác định rõ điều gì đang được chứng minh:

- Ứng dụng tạo đúng topic, key, value và header cho record.
- Broker nhận record và trả acknowledgement theo cấu hình **acks**.
- Record có metadata hợp lệ như topic, partition và offset.
- Khi cần kiểm chứng sâu hơn, consumer có thể đọc lại đúng key và payload từ topic.

Các mức kiểm chứng này bổ trợ cho nhau. Unit test giúp kiểm tra logic tạo message; integration test với Kafka broker giúp xác nhận đường gửi thực tế hoạt động.

## 1. Thế nào là một lần gửi thành công?

### 1.1 send() là thao tác bất đồng bộ

**KafkaTemplate.send()** gửi record thông qua Kafka producer. Trong Spring Kafka 3.x, các overload của phương thức này trả về **CompletableFuture<SendResult<K, V>>**. Future hoàn tất khi producer nhận được kết quả gửi thành công hoặc thất bại.

Ví dụ:

~~~java
CompletableFuture<SendResult<String, String>> future =
        kafkaTemplate.send("orders", "order-42", "ORDER_CREATED");
~~~

Ngay sau dòng lệnh trên, record có thể vẫn đang nằm trong buffer của producer hoặc đang trên đường tới broker. Không nên xem việc phương thức trả về future là bằng chứng broker đã ghi record.

Trong test, có thể chờ kết quả:

~~~java
SendResult<String, String> result =
        kafkaTemplate.send("orders", "order-42", "ORDER_CREATED")
                .get(10, TimeUnit.SECONDS);
~~~

Nếu lần gửi thành công, get() trả về SendResult. Nếu producer gặp lỗi, future hoàn tất bất thường và get() ném ExecutionException. Nếu quá thời hạn chờ của bài test, get() ném TimeoutException. Thời hạn 10 giây ở đây là giới hạn chờ của test; nó không đồng nghĩa với cấu hình delivery.timeout.ms của producer.

Không nên dùng Thread.sleep() để chờ gửi xong. Sleep chỉ trì hoãn test theo một khoảng thời gian phỏng đoán, trong khi future biểu diễn trực tiếp kết quả của lần gửi.

### 1.2 Ý nghĩa của broker acknowledgement

Mức xác nhận phụ thuộc cấu hình producer acks:

| Giá trị | Ý nghĩa | Điều test có thể kết luận |
|---|---|---|
| 0 | Producer không chờ broker acknowledgement | Future không chứng minh broker đã nhận record |
| 1 | Leader partition xác nhận đã ghi record | Leader đã xác nhận; dữ liệu vẫn có thể mất nếu leader lỗi trước khi replica khác nhận record |
| all hoặc -1 | Broker chờ các replica đang thuộc ISR xác nhận theo giao thức Kafka | Record được xác nhận theo tập ISR và cấu hình replication tại thời điểm ghi |

Nếu yêu cầu của ứng dụng là chỉ báo gửi thành công sau khi broker xác nhận, test cần chạy với acks=1 hoặc acks=all; với yêu cầu độ bền cao, thường chọn acks=all và cấu hình min.insync.replicas phù hợp ở broker/topic.

acks=all không có nghĩa mọi broker trong cluster đều phải xác nhận. Nó áp dụng cho các replica đang nằm trong in-sync replica set (ISR). Vì vậy, độ bền còn phụ thuộc replication factor, ISR và min.insync.replicas.

### 1.3 Đọc metadata của kết quả gửi

SendResult chứa record producer đã gửi và RecordMetadata do broker trả về:

~~~java
RecordMetadata metadata = result.getRecordMetadata();

String topic = metadata.topic();
int partition = metadata.partition();
long offset = metadata.offset();
long timestamp = metadata.timestamp();
~~~

Trong test, các assertion thường hữu ích gồm:

- Topic đúng với topic dự kiến.
- Partition không âm.
- Offset không âm.
- Key và value của producer record khớp dữ liệu đầu vào.

Metadata chứng minh producer nhận acknowledgement cho record theo cấu hình hiện hành. Nó chưa chứng minh consumer downstream đã xử lý record hoặc side effect nghiệp vụ đã hoàn tất.

## 2. Chọn đúng loại test

| Loại test | Cách thực hiện | Điều chứng minh được |
|---|---|---|
| Unit test | Mock KafkaTemplate | Service gọi đúng topic, key, payload và header |
| Integration test | Dùng @EmbeddedKafka | Producer, serializer, broker và đường gửi hoạt động cùng nhau |
| Integration test với broker container | Dùng Kafka trong Testcontainers | Kiểm tra cấu hình gần môi trường triển khai hơn |
| System test | Gửi vào cluster kiểm thử thật | Kiểm tra ACL, TLS, replication, broker policy và cấu hình môi trường |

Nếu mục tiêu là kiểm tra producer send thành công, unit test chỉ xác nhận lời gọi đến mock. Mock có thể trả về một future thành công dù không có broker nào tồn tại. Do đó, cần ít nhất một integration test kết nối với broker để xác nhận acknowledgement thực tế.

## 3. Kiểm thử bằng Embedded Kafka

Spring Kafka cung cấp spring-kafka-test với @EmbeddedKafka, EmbeddedKafkaBroker và KafkaTestUtils. Embedded broker phù hợp cho integration test nhanh, chạy cùng test suite mà không cần cluster Kafka dùng chung.

### 3.1 Khai báo dependency

Với Spring Boot, thêm test dependency tương ứng với phiên bản Spring Kafka do Spring Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Thông thường không cần tự chỉ định version nếu dự án dùng Spring Boot dependency management. Nếu quản lý version thủ công, hãy bảo đảm spring-kafka-test tương thích với phiên bản spring-kafka trong ứng dụng.

### 3.2 Cấu hình test với một topic

Ví dụ dưới đây dùng KafkaTemplate<String, String> để tập trung vào hành vi gửi. Trong ứng dụng thực tế, serializer phải khớp kiểu dữ liệu mà producer sử dụng.

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
    "spring.kafka.producer.acks=all",
    "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
    "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer"
})
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderProducerIntegrationTest {

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    private EmbeddedKafkaBroker embeddedKafka;

    @Test
    void shouldSendRecordAndReceiveBrokerAcknowledgement() throws Exception {
        Map<String, Object> consumerProps =
                KafkaTestUtils.consumerProps(
                        "producer-send-test",
                        "false",
                        embeddedKafka
                );

        try (Consumer<String, String> consumer =
                     new DefaultKafkaConsumerFactory<String, String>(
                             consumerProps
                     ).createConsumer()) {

            // Tạo subscription trước khi producer gửi record.
            embeddedKafka.consumeFromAnEmbeddedTopic(consumer, "orders");

            SendResult<String, String> result =
                    kafkaTemplate.send(
                            "orders",
                            "order-42",
                            "ORDER_CREATED"
                    ).get(10, TimeUnit.SECONDS);

            assertEquals(
                    "orders",
                    result.getRecordMetadata().topic()
            );
            assertTrue(result.getRecordMetadata().partition() >= 0);
            assertTrue(result.getRecordMetadata().offset() >= 0);
            assertEquals(
                    "order-42",
                    result.getProducerRecord().key()
            );
            assertEquals(
                    "ORDER_CREATED",
                    result.getProducerRecord().value()
            );

            ConsumerRecord<String, String> received =
                    KafkaTestUtils.getSingleRecord(consumer, "orders");

            assertEquals("order-42", received.key());
            assertEquals("ORDER_CREATED", received.value());
        }
    }
}
~~~

Một số điểm cần chú ý:

1. @EmbeddedKafka khởi tạo broker và topic orders cho test.
2. bootstrapServersProperty đưa địa chỉ broker nhúng vào cấu hình mà Spring Boot dùng để tạo KafkaTemplate.
3. Test tạo consumer và đăng ký topic trước khi gửi. Như vậy consumer không bỏ lỡ record do bắt đầu đọc sau thời điểm publish.
4. get(10, TimeUnit.SECONDS) chờ acknowledgement và làm test thất bại nếu future hoàn tất bằng exception hoặc hết thời gian chờ.
5. Assertion trên RecordMetadata kiểm tra kết quả broker trả về; assertion trên consumer kiểm tra record có thể được đọc từ topic.

KafkaTestUtils.getSingleRecord() chờ một record và kiểm tra kết quả đọc. Nếu test cần xử lý nhiều record, hãy dùng getRecords() hoặc poll consumer rồi kiểm tra số lượng, key và value theo yêu cầu.

### 3.3 Vì sao nên kiểm tra cả future và consumer?

Hai assertion trả lời hai câu hỏi khác nhau:

- Future thành công cùng metadata xác nhận producer nhận acknowledgement từ broker theo cấu hình acks.
- Consumer đọc được record xác nhận record hiện diện trên topic và có thể được đọc bằng consumer group trong test.

Nếu chỉ cần kiểm tra hợp đồng gửi và acknowledgement, assertion trên future cùng metadata thường là đủ. Nếu cần kiểm tra serializer, topic routing, key, payload hoặc khả năng đọc lại, hãy thêm consumer assertion.

Consumer trong ví dụ là consumer kiểm thử độc lập. Nó không đại diện cho toàn bộ logic listener nghiệp vụ của ứng dụng. Muốn kiểm tra listener, cần một test khác xác nhận listener nhận record và hoàn thành side effect tương ứng.

## 4. Kiểm tra producer service thay vì chỉ kiểm tra KafkaTemplate

Trong ứng dụng, producer thường được bọc trong một service để giữ logic tạo event ở một nơi:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
~~~

Có thể chia kiểm thử thành hai phần:

- Unit test cho OrderEventPublisher dùng mock để xác nhận topic, key và event được gửi đúng. Test này nhanh và tập trung vào logic của service.
- Integration test dùng Embedded Kafka để gọi publisher thật, chờ future hoàn tất và kiểm tra metadata hoặc record consumer nhận được.

Không nên để unit test mock được xem là bằng chứng producer gửi thành công tới Kafka. Nó chỉ chứng minh code đã yêu cầu template gửi record.

## 5. Kiểm tra kết quả bất đồng bộ trong code ứng dụng

Trong code chạy thật, thường không nên chặn thread bằng get() chỉ để chờ broker. Hãy xử lý future bằng callback:

~~~java
public void publish(OrderCreated event) {
    kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                            "Cannot publish order event, orderId={}",
                            event.orderId(),
                            exception
                    );
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info(
                        "Published order event, orderId={}, partition={}, offset={}",
                        event.orderId(),
                        metadata.partition(),
                        metadata.offset()
                );
            });
}
~~~

Callback giúp ứng dụng quan sát kết quả gửi mà không giữ thread chờ. Với hệ thống production, nên bổ sung metric cho số lần gửi thành công/thất bại, retry, độ trễ gửi và lỗi theo loại. Tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log.

Nếu tầng gọi cần biết publish đã thành công trước khi hoàn tất một quy trình, hãy trả future về cho tầng đó hoặc thiết kế một trạng thái nghiệp vụ phù hợp. Không nuốt exception trong callback rồi báo thành công cho caller khi record chưa được broker xác nhận.

Trong Spring Kafka 2.x, API gửi thường trả về ListenableFuture và dùng addCallback(). Từ Spring Kafka 3.0, API chuyển sang CompletableFuture; hãy viết test theo đúng phiên bản dependency của dự án.

## 6. Kiểm thử nhiều record và batch gửi

Khi producer gửi nhiều record, không nên chỉ chờ future của record cuối cùng. Mỗi lần gọi send() có kết quả độc lập; một record thành công không chứng minh các record trước đó đều thành công.

Với Spring Kafka 3.x và Java 17 trở lên, có thể gom các future:

~~~java
List<CompletableFuture<SendResult<String, String>>> futures =
        events.stream()
                .map(event -> kafkaTemplate.send(
                        "orders",
                        event.orderId(),
                        event.payload()
                ))
                .toList();

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])
).get(10, TimeUnit.SECONDS);

for (CompletableFuture<SendResult<String, String>> future : futures) {
    SendResult<String, String> result = future.join();
    assertTrue(result.getRecordMetadata().offset() >= 0);
}
~~~

allOf() chỉ hoàn tất bình thường khi tất cả future đầu vào hoàn tất bình thường. Nếu một future lỗi, thao tác chờ sẽ báo lỗi; khi cần báo cáo chính xác record nào thất bại, hãy duyệt từng future và ghi nhận kết quả tương ứng.

Khi kiểm tra consumer nhận batch, đừng giả định thứ tự giữa các partition. Kafka chỉ bảo đảm thứ tự trong cùng một partition. Nếu test cần thứ tự nghiệp vụ, hãy gửi các record cùng key để chúng được định tuyến vào cùng partition, rồi kiểm tra thứ tự trong partition đó.

## 7. Những lỗi thường gặp khi test producer

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Test xanh dù broker không chạy | Test chỉ mock KafkaTemplate hoặc không chờ future | Dùng Embedded Kafka và chờ kết quả gửi |
| get() ném ExecutionException | Broker lỗi, topic không tồn tại theo policy, serializer lỗi, ACL từ chối hoặc timeout gửi | Xem getCause() và exception gốc |
| Test hết thời gian chờ | Broker chưa sẵn sàng, consumer setup sai, producer đang retry hoặc cấu hình timeout quá ngắn | Kiểm tra bootstrap server, log broker và delivery timeout |
| Future thành công nhưng consumer không thấy record | Consumer bắt đầu đọc sai thời điểm, offset reset không phù hợp, đọc nhầm topic/partition hoặc record đã được lọc bởi cấu hình đọc | Tạo consumer trước khi gửi và kiểm tra topic, group, offset |
| Key/value đọc ra khác mong đợi | Serializer/deserializer không tương thích hoặc schema mapping sai | Kiểm tra cấu hình serializer hai phía và payload thực tế |
| Test chạy độc lập thành công nhưng chạy cả suite thất bại | Dùng trùng group ID, topic hoặc context; dữ liệu test còn sót | Dùng group ID riêng, topic riêng hoặc cô lập context |

Khi future lỗi, nên báo nguyên nhân gốc thay vì chỉ in thông báo ExecutionException. Các lỗi thường gặp gồm SerializationException, TimeoutException, TopicAuthorizationException, RecordTooLargeException và NotEnoughReplicasException.

Phân biệt hai loại timeout:

- Timeout truyền vào future.get(timeout, unit) chỉ giới hạn thời gian test chờ kết quả.
- delivery.timeout.ms là giới hạn thời gian producer cố gắng hoàn tất việc gửi, bao gồm retry và thời gian chờ acknowledgement.

Hai giới hạn có thể khác nhau. Nếu test chờ ngắn hơn thời gian producer được phép retry, test có thể timeout dù producer vẫn đang gửi. Hãy đặt thời hạn chờ test đủ lớn so với cấu hình producer và thời gian khởi động broker.

## 8. Giới hạn của Embedded Kafka và khi nào cần broker thật

Embedded Kafka hữu ích cho việc kiểm tra đường gửi, serializer, topic và consumer đọc record. Tuy nhiên, cấu hình một broker không mô phỏng đầy đủ cluster production:

- Không kiểm tra được khả năng chịu lỗi khi leader partition dừng và replica khác được bầu làm leader.
- Không chứng minh được hành vi acks=all với nhiều replica hoặc chính sách min.insync.replicas.
- Không đại diện đầy đủ cho ACL, TLS, SASL, quota, network policy và cấu hình broker của môi trường thật.
- Không thay thế kiểm thử tương thích phiên bản Kafka, schema registry hoặc hệ thống giám sát production.

Nếu yêu cầu của producer liên quan đến replication hoặc failover, hãy dùng Kafka cluster kiểm thử có nhiều broker, chẳng hạn môi trường Testcontainers được cấu hình phù hợp hoặc cluster integration riêng. Nếu cần xác nhận ACL/TLS, test phải chạy với đúng cơ chế xác thực và quyền truy cập tương ứng.

Không nên suy ra độ bền của production chỉ từ một test Embedded Kafka xanh. Kết quả test chỉ có ý nghĩa trong phạm vi broker và cấu hình mà test thực sự sử dụng.

## 9. Checklist thiết kế bài test

Trước khi kết luận producer gửi thành công, hãy xác định:

1. Test có kết nối broker thật hay chỉ mock KafkaTemplate?
2. acks được cấu hình ở mức nào, và mức đó có phù hợp với yêu cầu không?
3. Test có chờ future hoàn tất và xử lý trường hợp exceptional completion không?
4. Có kiểm tra metadata như topic, partition và offset không?
5. Có cần consumer đọc lại để kiểm tra key, payload, header hoặc serializer không?
6. Consumer đã đăng ký topic trước khi gửi và dùng group ID riêng cho test chưa?
7. Timeout của test có phù hợp với timeout gửi và thời gian khởi động broker không?
8. Nếu yêu cầu liên quan đến replication, ACL hoặc TLS, test có chạy trên cluster phản ánh các cấu hình đó không?

Một producer test đáng tin cậy không chỉ xác nhận code đã gọi send(). Nó chờ kết quả bất đồng bộ, kiểm tra acknowledgement theo cấu hình acks, và xác nhận metadata broker trả về. Khi hợp đồng của ứng dụng còn bao gồm nội dung record, hãy đọc record bằng consumer kiểm thử để xác nhận key và payload thực tế. Cách kiểm tra này giúp phát hiện lỗi serializer, cấu hình broker và đường gửi trước khi chúng xuất hiện trong luồng xử lý nghiệp vụ.
