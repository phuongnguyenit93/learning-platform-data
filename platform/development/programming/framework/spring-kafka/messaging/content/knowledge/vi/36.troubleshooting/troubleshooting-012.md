# Dead-letter không được tạo

## 1. Phân biệt topic DLT không tồn tại và record không được gửi vào DLT

Khi nói dead-letter không được tạo, cần xác định đang gặp trường hợp nào:

- **Topic DLT không tồn tại:** broker chưa có topic đích, hoặc topic được tạo với tên khác với tên mà recoverer đang dùng.
- **Topic có tồn tại nhưng không có record:** listener chưa đi tới bước recovery, record vẫn đang retry, hoặc việc publish DLT thất bại.
- **Record đã được gửi nhưng không tìm thấy:** consumer kiểm tra sai topic, partition, offset hoặc group; hoặc record chưa được poll do consumer test chưa subscribe/assign.
- **DLT có record nhưng ứng dụng không đọc được:** consumer DLT thiếu quyền, deserializer không tương thích hoặc group offset đã ở cuối log.

Đừng kết luận lỗi chỉ từ việc không nhìn thấy một topic trong Kafka UI. Hãy kiểm tra riêng luồng xử lý, lệnh publish, topic metadata, partition, quyền và record thực tế.

Trong Spring Kafka, dead-letter là một bước recovery. Listener thất bại, error handler quyết định retry; khi hết retry hoặc gặp exception không retry, recoverer mới publish record sang topic đích. Nếu listener tự bắt exception rồi trả về bình thường, error handler không nhận được lỗi để chuyển record sang DLT.

~~~mermaid
flowchart TD
    A["Kafka record"] --> B["Listener"]
    B --> C{"Listener ném exception?"}
    C -->|Không| D["Xử lý thành công / commit theo AckMode"]
    C -->|Có| E["Error handler"]
    E --> F{"Còn retry?"}
    F -->|Có| G["BackOff và giao lại"]
    G --> B
    F -->|Không| H["DeadLetterPublishingRecoverer"]
    H --> I{"Broker xác nhận publish?"}
    I -->|Có| J["Record trong DLT"]
    I -->|Không| K["Recovery publish failure"]
~~~

Bài này tập trung vào record listener dùng blocking retry với `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`, đồng thời chỉ ra các khác biệt cần kiểm tra nếu ứng dụng dùng transaction hoặc `@RetryableTopic`.

## 2. Xác định chính xác tên topic DLT

Một nguyên nhân phổ biến là tên topic được tạo không khớp với destination resolver.

Với `DeadLetterPublishingRecoverer` mặc định, tên đích thường được tạo bằng cách nối hậu tố `-dlt` vào tên topic nguồn và giữ partition nguồn. Ví dụ:

| Topic nguồn | Topic DLT mặc định |
|---|---|
| `orders` | `orders-dlt` |
| `payments` | `payments-dlt` |
| `customer-events` | `customer-events-dlt` |

Nếu đội vận hành đã tạo `orders.DLT` nhưng recoverer mặc định đang gửi tới `orders-dlt`, record sẽ không xuất hiện ở topic mà họ đang kiểm tra. Ngược lại, nếu code cấu hình `.DLT` nhưng topic được provision là `-dlt`, producer sẽ gửi tới một tên khác hoặc gặp lỗi nếu broker không tự tạo topic.

Để dùng quy ước `orders.DLT`, cấu hình resolver tường minh:

~~~java
var recoverer = new DeadLetterPublishingRecoverer(
    kafkaTemplate,
    (record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
    )
);
~~~

Khi dùng resolver riêng, cần thống nhất quy ước tên giữa code, topic provisioning, ACL, dashboard, runbook và DLT consumer. Không giả định mọi phiên bản hoặc mọi cấu hình của ứng dụng đều dùng cùng hậu tố.

## 3. Kiểm tra listener có thật sự phát sinh lỗi

DLT chỉ được sử dụng khi listener thất bại và exception được truyền về container. Nếu exception bị nuốt, Spring Kafka xem lời gọi listener là thành công.

Ví dụ sai:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception ex) {
        log.error("Cannot process order", ex);
        // Không ném lại exception: container không biết xử lý thất bại.
    }
}
~~~

Cách xử lý phù hợp nếu muốn error handler quản lý retry và DLT:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    orderService.process(event);
}
~~~

Hoặc nếu cần log/bổ sung context, hãy ném lại exception:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void consume(OrderCreatedEvent event) {
    try {
        orderService.process(event);
    }
    catch (OrderProcessingException ex) {
        log.error(
            "Cannot process eventId={}",
            event.eventId(),
            ex
        );
        throw ex;
    }
}
~~~

Kiểm tra thêm các trường hợp:

- Listener có trả về bình thường sau khi đánh dấu lỗi trong kết quả nghiệp vụ không?
- Có `Acknowledgment.acknowledge()` được gọi trước khi xử lý xong không?
- Có cấu hình `MANUAL`/`MANUAL_IMMEDIATE` làm offset được xác nhận quá sớm không?
- Listener có dùng `@Retryable` của Spring Retry hoặc cơ chế retry riêng khiến exception không tới `DefaultErrorHandler` không?
- Có adapter, interceptor hoặc wrapper bắt exception và chuyển thành kết quả thành công không?

Nếu listener tự xử lý lỗi thành một kết quả bình thường, DLT không tự xuất hiện. Cần quyết định rõ lớp nào chịu trách nhiệm retry và recovery.

## 4. Kiểm tra error handler đã được gắn vào đúng container factory

Khai báo bean `DefaultErrorHandler` chưa đủ. Listener container phải dùng factory có gắn error handler đó.

Ví dụ cấu hình:

~~~java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

        recoverer.setFailIfSendResultIsError(true);

        return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    DefaultErrorHandler kafkaErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);

        return factory;
    }
}
~~~

Listener phải tham chiếu đúng factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(OrderCreatedEvent event) {
    orderService.process(event);
}
~~~

Các điểm cần kiểm tra:

- Tên bean trong `containerFactory` có chính xác không?
- Factory có gọi `setCommonErrorHandler()` không?
- Có nhiều factory và listener đang dùng nhầm factory mặc định không?
- Cấu hình Spring Boot có tạo factory tự động khác với factory custom không?
- Listener container đã được khởi động với cấu hình mới sau lần deploy gần nhất chưa?

Một cách xác minh là đặt `id` cho listener, tra container qua `KafkaListenerEndpointRegistry` và kiểm tra trạng thái container, concurrency, group ID cùng factory thực tế.

## 5. Hiểu đúng số lần retry trước khi recovery

Với cấu hình:

~~~java
new FixedBackOff(1_000L, 2L)
~~~

Container chờ 1 giây giữa các lần retry và cho phép tối đa hai lần retry bổ sung sau lần giao ban đầu. Nếu listener luôn thất bại với exception retryable, tổng số lần gọi listener là ba:

1. Lần giao ban đầu.
2. Retry thứ nhất.
3. Retry thứ hai.
4. Sau khi hết retry, error handler gọi recoverer để publish DLT.

Không nhầm số retry bổ sung với tổng số lần giao. Nếu test chỉ chờ hai lần gọi hoặc kỳ vọng DLT xuất hiện ngay sau lần đầu, kết quả sẽ không khớp cấu hình.

Nếu exception được phân loại non-retryable, error handler có thể gọi recoverer ngay mà không thực hiện các lần retry bổ sung. Nếu exception thuộc nhóm được retry mặc định hoặc đã được tùy chỉnh, hành vi sẽ khác. Hãy xem cấu hình phân loại exception của đúng `DefaultErrorHandler` đang được gắn vào listener.

## 6. Kiểm tra exception có được phân loại retryable không

Một record có thể chưa tới DLT vì error handler vẫn đang retry. Một record khác có thể được chuyển ngay vì exception được đánh dấu non-retryable.

Ví dụ:

~~~java
handler.addNotRetryableExceptions(
    InvalidOrderPayloadException.class
);
~~~

Nếu listener ném `InvalidOrderPayloadException`, recoverer được gọi ngay theo chính sách recovery. Nếu listener ném `TransientDatabaseException`, record có thể được retry theo `BackOff`.

Khi điều tra, cần xác định:

- Exception thực tế ở root cause là gì?
- Error handler nhận exception nào sau khi unwrap?
- Exception đó có nằm trong danh sách retryable/non-retryable tùy chỉnh không?
- Có retry listener, recoverer hoặc error handler khác ghi đè hành vi không?
- Log có cho thấy số lần delivery và thời điểm lần retry tiếp theo không?

Không nên đánh dấu mọi `RuntimeException` là non-retryable hoặc retryable một cách máy móc. Lỗi dữ liệu không thể tự phục hồi thường nên đi recovery nhanh; lỗi phụ thuộc tạm thời như timeout hoặc unavailable có thể cần retry có giới hạn.

## 7. Kiểm tra topic DLT có được provision hay không

Không nên phụ thuộc vào broker tự tạo topic DLT. Trong nhiều production cluster, `auto.create.topics.enable` bị tắt hoặc topic auto-created không có số partition, replication factor và retention phù hợp.

Có thể provision topic DLT bằng `NewTopic`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Bean
NewTopic ordersDltTopic() {
    return TopicBuilder.name("orders.DLT")
        .partitions(6)
        .replicas(3)
        .config("retention.ms", "604800000")
        .build();
}
~~~

Ví dụ dùng 6 partition và replication factor 3; các con số phải phù hợp với cluster và topic nguồn. Không dùng replication factor 3 nếu cluster chỉ có một broker. Trong môi trường production, topic provisioning có thể được quản lý bởi nền tảng hoặc pipeline hạ tầng thay vì tự động từ ứng dụng.

Kiểm tra topic bằng CLI:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --describe \
  --topic orders.DLT
~~~

Nếu CLI báo topic không tồn tại, kiểm tra lại tên destination resolver, provisioning pipeline và quyền `CREATE` nếu ứng dụng được phép tạo topic. Nếu topic tồn tại, tiếp tục kiểm tra partition, leader, ISR và ACL.

## 8. Kiểm tra partition đích

`DeadLetterPublishingRecoverer` thường định tuyến record đến partition tương ứng với partition nguồn. Nếu record nguồn ở partition 5, destination cần có partition 5 để resolver giữ nguyên partition.

Ví dụ:

| Topic | Số partition | Kết quả |
|---|---:|---|
| `orders` | 6 | Partition nguồn có thể từ 0 đến 5 |
| `orders.DLT` | 1 | Không đủ partition nếu resolver chọn partition nguồn |
| `orders.DLT` | 6 | Có partition tương ứng 0 đến 5 |

Nếu DLT có ít partition hơn topic nguồn, send có thể thất bại vì partition đích không tồn tại. Hãy provision DLT với số partition phù hợp hoặc thay resolver để chọn partition hợp lệ theo một chiến lược được thiết kế rõ ràng.

Không tự ý chuyển mọi record về partition 0 nếu nghiệp vụ cần ordering hoặc khả năng xử lý song song theo partition. Chuyển partition có thể làm mất quan hệ ordering với luồng gốc và tạo điểm nóng tải.

Kiểm tra cả partition count của retry topics nếu ứng dụng dùng non-blocking retry. Với `@RetryableTopic`, topic topology và partition strategy phải đồng bộ với nguồn theo cấu hình của framework.

## 9. Kiểm tra producer gửi DLT và serializer

DLT được publish bằng Kafka producer phía ứng dụng. Producer này cần serializer tương thích với key/value của record được recover.

Một lỗi thường gặp là producer serialize được event bình thường nhưng không serialize được raw `byte[]` từ lỗi deserialize.

Ví dụ, nếu cấu hình DLT template chỉ dùng `StringSerializer`, việc gửi value kiểu `byte[]` có thể thất bại. Với dữ liệu deserialize thành công, value có thể là object domain; với `ErrorHandlingDeserializer`, raw payload lỗi có thể được đưa vào recovery dưới dạng byte array.

Kiểm tra:

- Key serializer có xử lý kiểu key gốc không?
- Value serializer có hỗ trợ object domain và `byte[]` không?
- Template có dùng đúng producer factory và security properties không?
- Header có được serialize/chuyển tiếp phù hợp không?
- Có lỗi class cast hoặc serializer exception trong log producer không?

Với nhiều kiểu payload, có thể dùng `DelegatingByTypeSerializer` để chọn serializer theo kiểu:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(String.class, new StringSerializer());
delegates.put(OrderCreatedEvent.class, new JsonSerializer<>());

var valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

Đây là ví dụ cấu trúc; hãy cấu hình serializer key/value và `ProducerFactory` theo generic type thực tế của ứng dụng. Với JSON serializer, cần thống nhất type headers, trusted packages và schema/version strategy giữa producer, consumer và DLT reader.

Nếu DLT cần giữ raw payload chính xác để điều tra, cân nhắc template chuyên dụng có `ByteArraySerializer` hoặc cấu hình serializer theo kiểu thay vì deserialize rồi serialize lại dữ liệu không hợp lệ.

## 10. Bật chế độ phát hiện lỗi gửi DLT

`KafkaTemplate.send()` là thao tác bất đồng bộ. Nếu chỉ khởi tạo send mà không kiểm tra kết quả, ứng dụng có thể không quan sát được lỗi broker trả về.

Với `DeadLetterPublishingRecoverer`, có thể yêu cầu recovery thất bại khi send result báo lỗi:

~~~java
recoverer.setFailIfSendResultIsError(true);
~~~

Khi bật tùy chọn này, lỗi publish DLT được truyền lại để error handler/container xử lý theo chính sách thay vì âm thầm coi record đã recovered thành công. Hành vi timeout và exception cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình recoverer. Kiểm tra API của dependency đang dùng nếu method này không có trong phiên bản cũ.

Kiểm tra log cho các lỗi:

- Topic authorization hoặc group/cluster authorization.
- Unknown topic hoặc partition.
- Not leader hoặc leader unavailable.
- Request timeout, network disconnect.
- Serialization exception.
- Record quá lớn hoặc quota exceeded.
- Transaction aborted hoặc producer fencing nếu dùng transaction.

Không chỉ nhìn log listener. Cần kiểm tra log của producer DLT và broker để biết send đã thất bại ở bước nào.

## 11. Kiểm tra ACL của principal publish DLT

Consumer đọc topic nguồn và producer ghi DLT có thể dùng cùng principal ứng dụng, nhưng quyền trên topic nguồn không tự động cấp quyền trên DLT.

Principal cần quyền phù hợp cho thao tác publish DLT, thường là `WRITE` trên topic đích và có thể cần `DESCRIBE` theo client flow/broker policy. Nếu DLT consumer đọc record, principal của consumer DLT cần `READ` trên topic DLT và `READ` trên consumer group.

Ví dụ kiểm tra ACL bằng CLI:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config admin-client.properties \
  --list \
  --topic orders.DLT
~~~

Tên resource và quyền hiển thị tùy authorizer. Kiểm tra principal thực tế mà broker nhìn thấy, đặc biệt khi dùng SASL, mTLS hoặc principal mapping.

Một số dấu hiệu:

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Consumer đọc `orders` được nhưng DLT publish bị từ chối | Thiếu `WRITE` trên `orders.DLT` |
| DLT record đã có nhưng công cụ kiểm tra không đọc được | Principal kiểm tra thiếu `READ` |
| Topic được tạo bởi admin nhưng app không publish | ACL của application principal chưa được cập nhật |
| CLI admin đọc được nhưng app lỗi | Hai client dùng principal/credential khác nhau |

Không cấp superuser để chữa lỗi. Cấp quyền tối thiểu cho producer DLT và consumer DLT theo đúng namespace.

## 12. Kiểm tra security properties của DLT producer

Nếu producer chính hoạt động nhưng DLT producer thất bại, hãy xác minh DLT `KafkaTemplate` có cùng cấu hình bootstrap server, TLS/SASL, truststore và credential phù hợp.

Nếu dùng một `KafkaTemplate` riêng cho DLT:

- Xác minh producer factory của template đó.
- Kiểm tra `security.protocol`, SASL mechanism và JAAS config.
- Kiểm tra truststore/keystore được mount đúng.
- Xác minh principal mapping và ACL.
- Kiểm tra transaction ID prefix nếu template transactional.
- Kiểm tra serializer và producer interceptor.

Đừng giả định template DLT tự kế thừa mọi cấu hình từ template chính nếu ứng dụng tạo producer factory riêng.

Trong Spring Boot, cấu hình common Kafka properties và producer-specific properties có thể khác nhau. So sánh cấu hình hiệu lực của producer gửi event chính và producer publish DLT; không log password, token hoặc private key khi debug.

## 13. Kiểm tra kích thước record và cấu hình broker

DLT thường giữ lại payload gốc cùng các header chứa thông tin exception và vị trí nguồn. Record DLT vì vậy có thể lớn hơn record nguồn.

Nếu send thất bại do record quá lớn, kiểm tra:

- `max.request.size` của producer.
- `max.message.bytes` của topic DLT.
- `message.max.bytes` của broker.
- Kích thước header và exception stack trace được thêm vào DLT.
- Compression và cấu hình batch/request.

Không tăng giới hạn kích thước tùy tiện trên toàn cluster. Xác định record lớn đến từ payload hay header, rồi đặt giới hạn hợp lý ở producer, topic và broker. Có thể tắt/giới hạn header exception stack trace nếu không cần lưu toàn bộ stack trace; cần giữ lại thông tin đủ để điều tra.

## 14. Kiểm tra transaction và recovery sau rollback

Nếu listener container chạy với Kafka transaction, exception thường làm transaction bị rollback. Luồng recovery sau rollback khác với cấu hình record listener không transaction.

Trong trường hợp này, cần kiểm tra `DefaultAfterRollbackProcessor` và cấu hình recoverer tương ứng thay vì chỉ nhìn `DefaultErrorHandler`. Nếu muốn publish DLT và commit offset recovered theo transaction, cấu hình phải phối hợp đúng với `KafkaTemplate`, transaction manager và container.

Các điểm cần xác minh:

- Listener container có bật transaction không?
- `KafkaTransactionManager` nào được gắn với container?
- Exception có làm transaction rollback như mong muốn không?
- `DefaultAfterRollbackProcessor` có được cấu hình với recoverer không?
- Recoverer có dùng template tham gia transaction phù hợp không?
- Offset nguồn được commit cùng transaction hay theo chính sách khác?
- Có lỗi producer fencing, transaction timeout hoặc abort không?

Không dùng cấu hình `DefaultErrorHandler` cho listener transactional rồi mặc định rằng hành vi sẽ giống hệt non-transactional. Hãy kiểm thử recovery với transaction manager và broker version thực tế.

## 15. Phân biệt blocking retry với @RetryableTopic

Nếu listener dùng `@RetryableTopic`, record được chuyển qua retry topics theo topology do Spring Kafka tạo hoặc được provision. Khi hết attempt, framework chuyển record tới DLT topic theo naming strategy.

Khi DLT không xuất hiện, kiểm tra:

- `@RetryableTopic` có nằm trên listener method đúng không?
- Retry topic infrastructure có được bật theo phiên bản/cấu hình không?
- `attempts` là tổng số lần giao dự kiến, không phải số retry bổ sung như `FixedBackOff`.
- DLT handler có được đăng ký đúng không?
- Tên retry topic và DLT có khớp naming strategy không?
- Retry/DLT topics đã được tạo với partition và replication phù hợp chưa?
- Producer gửi retry/DLT có quyền `WRITE` không?
- Record có đang chờ delay ở retry topic không?

Không tìm record trong DLT ngay sau lần đầu thất bại nếu nó vẫn đang ở retry topic và delay chưa hết.

Với non-blocking retry, ordering có thể thay đổi vì record lỗi được đưa sang topic khác trong khi record sau vẫn tiếp tục. Kiểm tra cả retry topic, DLT và consumer group tương ứng trước khi kết luận record bị mất.

## 16. Kiểm tra deserialization failure

Lỗi deserialize có thể xảy ra trong `poll()` trước khi listener method được gọi. Khi đó, breakpoint hoặc log trong listener không xuất hiện dù record lỗi đang được xử lý.

Để error handler có thể xử lý lỗi deserialize, thường cần `ErrorHandlingDeserializer` bọc deserializer thực tế. Cấu hình producer DLT phải tương thích với raw bytes và metadata exception được giữ lại.

Kiểm tra:

1. Consumer có dùng `ErrorHandlingDeserializer` không?
2. Delegate deserializer có đúng type và cấu hình không?
3. Exception deserialize có được chuyển qua `ConsumerRecord`/header để error handler nhận không?
4. DLT producer có serialize được `byte[]` không?
5. DLT reader có dùng deserializer phù hợp với raw payload không?
6. Có tombstone value null hoặc key deserialize failure không?

Không chỉ kiểm tra JSON sai cú pháp. Schema version không tương thích, type header sai, trusted packages thiếu và dữ liệu cũ có thể gây deserialize failure.

## 17. Đọc DLT headers để xác định record nguồn

Spring Kafka thêm dead-letter headers giúp truy ngược record gốc. Một số header quan trọng:

| Header | Ý nghĩa |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic nguồn |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition nguồn |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset nguồn |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group nguồn |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên class exception |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Thông báo exception |

Header có thể thay đổi theo phiên bản và cấu hình recoverer. Dùng hằng số `KafkaHeaders` tương ứng của dependency hiện tại khi viết code đọc header.

Không giả định record DLT có cùng offset với record nguồn. Offset của DLT thuộc log riêng; metadata gốc được lưu trong header. Nếu DLT consumer không thấy record, kiểm tra consumer group, `auto.offset.reset`, topic subscription và offset hiện tại của DLT group.

## 18. Dùng AdminClient xác minh topic và partition

Có thể dùng `AdminClient` để xác minh topic đích tồn tại và số partition:

~~~java
import java.util.List;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

public class DltTopicProbe {

    public void verify(String bootstrapServers, String topic)
            throws Exception {

        Properties properties = new Properties();
        properties.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            var description = admin.describeTopics(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS)
                .get(topic);

            System.out.printf(
                "DLT topic=%s partitions=%d%n",
                topic,
                description.partitions().size()
            );
        }
    }
}
~~~

Ví dụ cần bổ sung security properties của cluster thật vào `properties`. `describeTopics` yêu cầu quyền phù hợp trên topic; lỗi authorization không có nghĩa topic chắc chắn không tồn tại.

Kiểm tra cả leader và replicas trong `TopicDescription`. Nếu partition không có leader hoặc replica không đồng bộ, producer có thể gặp lỗi metadata/availability dù topic đã được tạo.

## 19. Kiểm tra record có thật sự nằm trong DLT

Nếu topic tồn tại, dùng consumer kiểm tra với group riêng và bắt đầu từ đầu log còn giữ:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker.example.com:9092 \
  --consumer.config client.properties \
  --topic orders.DLT \
  --group dlt-investigation \
  --from-beginning \
  --timeout-ms 10000 \
  --property print.key=true \
  --property print.headers=true
~~~

Một số phiên bản CLI không hỗ trợ đúng các property hiển thị header như ví dụ; kiểm tra `--help` của bản phân phối đang dùng. Có thể dùng consumer Java để đọc `ConsumerRecord` và in key, partition, offset cùng header.

Nếu dùng group ID đã đọc hết DLT trước đó, `--from-beginning` không nhất thiết đưa committed offset của group hiện tại về đầu. Dùng group điều tra mới hoặc reset offset của group điều tra trong môi trường phù hợp. Không reset group production chỉ để xem DLT.

Nếu không có record, đối chiếu:

- Topic DLT thực tế theo resolver.
- Thời điểm listener hết retry.
- Log send result của recoverer.
- Partition đích và offset log end.
- ACL và serializer.
- Consumer group điều tra và offset của nó.

## 20. Kiểm tra log và metrics theo chuỗi sự kiện

Khi điều tra, ghép log theo event ID, correlation ID hoặc key record. Cần xác định các mốc:

1. Record được poll.
2. Listener bắt đầu xử lý.
3. Listener ném exception.
4. Error handler nhận exception.
5. Các lần retry diễn ra.
6. Recoverer được gọi.
7. Producer DLT bắt đầu send.
8. Broker xác nhận hoặc trả lỗi.
9. Offset nguồn được commit hoặc transaction hoàn tất.

Metrics hữu ích:

| Metric/quan sát | Câu hỏi |
|---|---|
| Listener invocation/error count | Listener có thất bại không? |
| Retry count | Record còn đang retry hay đã hết retry? |
| DLT publish success/failure | Recoverer có gửi thành công không? |
| Producer error/record error | Broker hoặc serializer từ chối điều gì? |
| Consumer lag của source | Record còn ở backlog không? |
| DLT topic end offset | Có record mới được append không? |
| DLT consumer lag | Record có tồn tại nhưng chưa được đọc không? |

Tên metric cụ thể phụ thuộc Micrometer, Spring Kafka version và instrumentation. Không giả định mọi ứng dụng đều expose sẵn metric `dlt.publish`; có thể cần log/observation tùy chỉnh cho recoverer.

## 21. Quy trình điều tra từ nhanh đến sâu

Dùng quy trình sau để khoanh vùng:

1. **Xác định đích:** đọc cấu hình recoverer để biết topic DLT chính xác.
2. **Xác nhận lỗi:** kiểm tra listener có ném exception và exception có tới container không.
3. **Xác nhận retry:** đối chiếu `BackOff`, retry count và exception classification.
4. **Xác nhận recoverer:** kiểm tra error handler/factory hoặc after-rollback processor có recoverer không.
5. **Xác nhận topic:** kiểm tra topic tồn tại, partition count, leader và ISR.
6. **Xác nhận publish:** xem producer DLT log/send result và timeout.
7. **Xác nhận quyền:** kiểm tra principal có `WRITE` trên DLT.
8. **Xác nhận serializer:** kiểm tra key/value type, raw bytes và header.
9. **Xác nhận transaction:** kiểm tra rollback, producer transaction và offset commit.
10. **Xác nhận người đọc:** dùng consumer group điều tra mới để tìm record.

~~~mermaid
flowchart TD
    A["Không thấy record DLT"] --> B{"Topic đích đúng?"}
    B -->|Không| C["Sửa destination resolver / tên topic"]
    B -->|Có| D{"Listener ném exception?"}
    D -->|Không| E["Sửa listener để lỗi được propagate"]
    D -->|Có| F{"Đã hết retry / recovery được gọi?"}
    F -->|Chưa| G["Kiểm tra BackOff và exception classification"]
    F -->|Rồi| H{"Publish DLT thành công?"}
    H -->|Không| I["Kiểm tra partition, ACL, serializer, broker, transaction"]
    H -->|Có| J{"Consumer kiểm tra đúng topic/group?"}
    J -->|Không| K["Sửa subscription/offset/group"]
    J -->|Có| L["Đối chiếu log end offset và headers"]
~~~

## 22. Kiểm thử integration để tái hiện lỗi

Một test integration cần chứng minh cả listener failure, retry exhaustion, DLT publish và việc đọc được record.

Ví dụ dùng Embedded Kafka hoặc Testcontainers với topic nguồn và DLT được tạo trước:

~~~java
@EmbeddedKafka(
    partitions = 2,
    topics = {"orders", "orders.DLT"}
)
@SpringBootTest
class DltPublishingIntegrationTest {
    // Inject KafkaTemplate, registry và probe listener.
}
~~~

Test listener có thể luôn ném exception:

~~~java
@KafkaListener(
    id = "ordersFailureListener",
    topics = "orders",
    groupId = "orders-dlt-test",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(String payload) {
    throw new IllegalStateException("Simulated processing failure");
}
~~~

Kiểm thử nên:

- Chờ listener container được assign đủ partition trước khi gửi.
- Gửi một message ID duy nhất.
- Chờ đủ số lần retry theo `FixedBackOff`.
- Poll DLT bằng consumer group riêng.
- Assert key/value, source topic, source partition và source offset trong header.
- Assert producer send failure được phát hiện khi cố ý cấu hình destination sai.
- Dùng timeout hữu hạn và dọn container/context sau test.

Không dùng `Thread.sleep()` cố định để đồng bộ. Dùng `ContainerTestUtils.waitForAssignment`, `CountDownLatch`, Awaitility hoặc `KafkaTestUtils.getRecords` với timeout.

## 23. Các tình huống test lỗi publish DLT

Nên có test riêng cho từng nguyên nhân có thể tái hiện:

| Tình huống | Cách mô phỏng | Kết quả mong đợi |
|---|---|---|
| Sai tên DLT | Resolver trỏ tới topic chưa provision, tắt auto-create trong test | Recoverer báo publish failure |
| Thiếu partition | Topic nguồn nhiều partition hơn DLT, resolver giữ partition | Send thất bại với partition đích không hợp lệ |
| Thiếu ACL | Principal test không có WRITE trên DLT | Broker từ chối publish |
| Serializer không hỗ trợ byte[] | Gửi payload lỗi deserialize qua template chỉ serialize String | Producer báo serialization failure |
| Broker tạm unavailable | Dừng broker/test container hoặc chặn kết nối | Send timeout/failure được quan sát |
| Transaction bị abort | Làm listener transaction rollback | DLT và offset theo transaction recovery policy |
| Topic DLT có nhưng consumer group ở cuối | Đọc bằng group đã commit offset mới nhất | Consumer không thấy record cũ dù record tồn tại |

Test lỗi cần cô lập topic, group và principal. Không để một listener liên tục retry trong test suite dùng chung vì có thể làm các test khác bị ảnh hưởng.

## 24. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không thấy topic DLT | Sai suffix hoặc topic chưa provision | Kiểm tra resolver và tạo đúng topic |
| Topic có nhưng không có record | Listener chưa tới recovery hoặc publish thất bại | Kiểm tra exception, retry và recoverer send result |
| Listener lỗi nhưng không có retry | Exception bị catch hoặc listener đã acknowledge | Propagate exception và kiểm tra AckMode |
| Retry mãi không tới DLT | Retry count lớn, exception classification hoặc retry khác đang can thiệp | Kiểm tra BackOff và error handler thực tế |
| DLT publish lỗi partition | DLT ít partition hơn nguồn | Tăng partition hoặc thiết kế resolver |
| DLT publish bị authorization error | Thiếu WRITE trên DLT | Cấp ACL cho principal ứng dụng |
| DLT publish lỗi serializer | Raw bytes/object không được serializer hỗ trợ | Cấu hình serializer theo kiểu payload |
| DLT gửi thành công nhưng không đọc được | Sai topic, group hoặc offset consumer kiểm tra | Dùng group điều tra mới và kiểm tra metadata |
| DLT bị rollback | Transactional recovery cấu hình không đúng | Kiểm tra AfterRollbackProcessor và transaction manager |
| Retry topic có record nhưng DLT chưa có | Non-blocking retry vẫn đang chờ delay | Theo dõi retry topic và attempts |

## 25. Checklist xử lý sự cố

- [ ] Xác định tên topic DLT thực tế từ destination resolver.
- [ ] Kiểm tra listener có propagate exception về container.
- [ ] Xác minh đúng listener container factory và error handler.
- [ ] Kiểm tra retry count, BackOff và exception classification.
- [ ] Xác minh recoverer đã được gọi.
- [ ] Kiểm tra topic DLT tồn tại và đúng số partition.
- [ ] Kiểm tra leader, ISR và broker availability.
- [ ] Kiểm tra DLT producer có đúng bootstrap, TLS/SASL và credential.
- [ ] Kiểm tra ACL WRITE trên topic DLT.
- [ ] Kiểm tra serializer cho object domain và raw byte[].
- [ ] Bật phát hiện lỗi send result của recoverer.
- [ ] Kiểm tra transaction và after-rollback recovery nếu listener transactional.
- [ ] Nếu dùng `@RetryableTopic`, kiểm tra retry topic, naming strategy và delay.
- [ ] Dùng consumer group điều tra riêng để đọc DLT.
- [ ] Kiểm tra DLT headers và metadata record nguồn.
- [ ] Theo dõi log, metrics, consumer lag và producer errors.
- [ ] Tái hiện bằng integration test có topic/group cô lập.

Dead-letter không được tạo thường bắt nguồn từ một trong ba nhóm: listener chưa đi tới recovery, recoverer không publish được hoặc nhóm điều tra đang đọc sai topic/partition/offset. Xác định destination resolver, theo dõi chuỗi exception → retry → recoverer → producer send, rồi kiểm tra topic, partition, serializer, ACL và transaction. Khi send result được giám sát và DLT được provision trước với cấu hình phù hợp, lỗi sẽ dễ khoanh vùng và tránh mất record hơn.
