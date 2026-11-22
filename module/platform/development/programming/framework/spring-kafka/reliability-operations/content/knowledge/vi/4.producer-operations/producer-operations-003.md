# ProducerListener

## 1. ProducerListener trong Spring Kafka

`ProducerListener<K, V>` là callback ở tầng Spring Kafka để quan sát kết quả gửi record qua một `KafkaTemplate<K, V>`. Nó cho ứng dụng biết một lần gửi đã thành công hay thất bại sau khi Kafka producer hoàn tất callback tương ứng.

ProducerListener thường được dùng cho các công việc xuyên suốt nhiều lần gửi:

- Ghi log tập trung khi record được gửi thành công hoặc gặp lỗi.
- Ghi metric về số lần gửi thành công, thất bại và loại exception.
- Thu thập metadata như topic, partition, offset và timestamp.
- Bổ sung thông tin phục vụ truy vết, điều tra sự cố và vận hành producer.

ProducerListener không thực hiện việc gửi record, không chọn partition, không cấu hình retry và không quyết định mức xác nhận của broker. Nó quan sát kết quả từ đường gửi do KafkaTemplate và Kafka client quản lý.

Một lần gửi điển hình có luồng:

~~~mermaid
sequenceDiagram
    participant S as Service
    participant T as KafkaTemplate
    participant P as KafkaProducer
    participant B as Broker
    participant PL as ProducerListener
    participant F as Send Future

    S->>T: send(topic, key, value)
    T->>P: send(record, callback)
    P->>P: serialize, partition, batch
    P->>B: Produce request
    B-->>P: Produce response
    P->>PL: onSuccess hoặc onError
    P->>F: hoàn tất future
    F-->>S: SendResult hoặc exception
~~~

Sơ đồ diễn tả các thành phần chính. Thứ tự chi tiết giữa việc gọi ProducerListener và hoàn tất future thuộc implementation của phiên bản Spring Kafka đang chạy; ứng dụng nên coi đây là hai cách nhận kết quả của cùng một lần gửi, không phụ thuộc vào thứ tự callback để điều phối nghiệp vụ.

## 2. Các phương thức của ProducerListener

Interface có hai callback quan trọng:

~~~java
public interface ProducerListener<K, V> {

    default void onSuccess(
        ProducerRecord<K, V> producerRecord,
        RecordMetadata recordMetadata
    ) {
    }

    default void onError(
        ProducerRecord<K, V> producerRecord,
        RecordMetadata recordMetadata,
        Exception exception
    ) {
    }

    default boolean isInterestedInSuccess() {
        return false;
    }
}
~~~

Các phương thức trên thể hiện API phổ biến trong Spring Kafka 2.x/3.x. Hãy kiểm tra Javadoc của dependency thực tế nếu dự án dùng phiên bản khác.

### 2.1. onSuccess

`onSuccess(ProducerRecord, RecordMetadata)` được gọi khi Kafka producer báo lần gửi thành công theo cơ chế xác nhận đang cấu hình. Hai tham số cung cấp:

- `ProducerRecord`: record mà ứng dụng đã gửi, gồm topic, partition nếu chỉ định, timestamp, key, value và headers.
- `RecordMetadata`: metadata broker trả về, thường gồm topic, partition, offset, timestamp và kích thước record.

Mặc định `isInterestedInSuccess()` trả về `false`. Nếu muốn nhận callback thành công, implementation cần override phương thức này và trả về `true`. Cách này giúp các listener chỉ quan tâm lỗi không phải xử lý callback success cho mọi record.

### 2.2. onError

`onError(ProducerRecord, RecordMetadata, Exception)` được gọi khi lần gửi hoàn tất với lỗi. Exception là thông tin chính để phân loại nguyên nhân; metadata có thể không có, vì vậy không nên giả định partition hoặc offset luôn sẵn sàng.

Những nguyên nhân thường gặp:

- Serializer không thể chuyển key hoặc value thành bytes.
- Không lấy được metadata topic hoặc producer buffer trong thời gian cho phép.
- Mất kết nối, broker không khả dụng hoặc request timeout.
- Broker từ chối ghi do quyền truy cập, kích thước record hoặc điều kiện ISR.
- Delivery timeout hết hạn sau các lần thử mà producer không nhận được kết quả thành công.

ProducerListener chỉ nhận thông tin lỗi. Nó không tự retry, không sửa record và không thay đổi cấu hình producer. Chính sách retry nội bộ vẫn do Kafka producer thực hiện; listener quan sát kết quả cuối cùng của lần gửi.

### 2.3. isInterestedInSuccess

`isInterestedInSuccess()` cho KafkaTemplate biết implementation có cần callback thành công hay không. Giá trị mặc định là `false`. Khi chỉ cần ghi nhận lỗi, giữ nguyên mặc định sẽ giảm công việc callback trên đường gửi.

Nếu cần log hoặc metric success, override thành `true`. Không nên bật callback success chỉ để thực hiện một tác vụ không cần thiết cho từng record, nhất là ở topic có throughput cao.

## 3. Cài đặt một ProducerListener

Một implementation thường được dùng chung bởi các lần gửi qua một KafkaTemplate:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.ProducerListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProducerListener
        implements ProducerListener<String, OrderCreated> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderProducerListener.class);

    @Override
    public boolean isInterestedInSuccess() {
        return true;
    }

    @Override
    public void onSuccess(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata
    ) {
        log.info(
            "Kafka publish succeeded: topic={}, partition={}, offset={}, key={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            record.key()
        );
    }

    @Override
    public void onError(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata,
        Exception exception
    ) {
        Integer partition =
            metadata == null ? null : metadata.partition();

        log.error(
            "Kafka publish failed: topic={}, partition={}, key={}",
            record.topic(),
            partition,
            record.key(),
            exception
        );
    }
}
~~~

Ví dụ dùng generic type phù hợp với key và value của template. Khi có nhiều loại event, có thể dùng một listener chung với kiểu tổng quát hoặc đăng ký listener riêng theo từng KafkaTemplate để log đúng metadata nghiệp vụ. Tránh ép kiểu value không an toàn trong một listener dùng cho nhiều template.

Trong callback lỗi, metadata được xử lý null-safe. Nếu producer chưa nhận được metadata broker, ứng dụng vẫn có thể ghi topic và key từ ProducerRecord cùng exception để phục vụ điều tra.

Trong môi trường thật, cần cân nhắc dữ liệu được ghi log. Key có thể chứa mã khách hàng hoặc thông tin nhạy cảm; không ghi toàn bộ payload nếu payload có dữ liệu cá nhân. Dùng event ID hoặc correlation ID đã được kiểm soát để truy vết khi cần.

## 4. Đăng ký ProducerListener với KafkaTemplate

ProducerListener được gắn vào KafkaTemplate. Mọi lần gửi qua template đó sẽ đi qua listener đã cấu hình.

### 4.1. Khi tự tạo KafkaTemplate

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ProducerListener<String, OrderCreated> orderProducerListener() {
        return new OrderProducerListener();
    }

    @Bean
    public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory,
        ProducerListener<String, OrderCreated> orderProducerListener
    ) {
        KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);

        template.setProducerListener(orderProducerListener);
        return template;
    }
}
~~~

`setProducerListener(...)` thiết lập listener cho template. Cách tạo bean cụ thể có thể khác nếu ứng dụng dùng Spring Boot auto-configuration, nhiều producer factory hoặc transactional template. Khi dùng template do Boot tạo sẵn, hãy cấu hình listener trên đúng template mà service đang inject; không tạo thêm một KafkaTemplate thứ hai mà service không sử dụng.

Nếu có nhiều template gửi đến các cụm Kafka hoặc kiểu dữ liệu khác nhau, mỗi template có thể dùng ProducerListener riêng. Điều này giúp tách metric và log theo luồng, đồng thời giữ generic type chính xác.

### 4.2. Listener mặc định

KafkaTemplate tiêu chuẩn có listener mặc định để ghi nhận lỗi gửi, thường là `LoggingProducerListener`. Implementation này phục vụ log lỗi cơ bản. Khi cần metric, correlation hoặc cách ghi log theo nghiệp vụ, ứng dụng có thể thay bằng implementation riêng.

Không nên giả định listener tùy chỉnh được tự động gắn vào mọi KafkaTemplate trong ứng dụng. Hãy kiểm tra cách bean template được tạo và bảo đảm listener được gắn vào đúng instance.

## 5. ProducerListener và CompletableFuture

Trong Spring Kafka 3.x, `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K, V>>`. ProducerListener và future cùng quan sát kết quả gửi nhưng phục vụ hai nhu cầu khác nhau.

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| ProducerListener | Tập trung ở KafkaTemplate | Logging, metrics và quan sát chung cho các lần gửi |
| CompletableFuture | Từng lời gọi send | Kết hợp luồng bất đồng bộ và xử lý kết quả tại nơi gọi |
| Callback truyền cho KafkaProducer | API Kafka client cấp thấp | Tùy chỉnh xử lý ở tầng producer khi thực sự cần |

Ví dụ dùng future tại service:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
    OrderCreated event
) {
    return kafkaTemplate
        .send("orders", event.orderId(), event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.warn("Publish did not complete for event {}", event.eventId(), error);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.debug(
                "Published event {} to {}-{} at offset {}",
                event.eventId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

ProducerListener thích hợp cho hành vi dùng chung ở tầng template. Future thích hợp khi service cần trả kết quả cho caller, ghép nhiều lần gửi, cập nhật trạng thái của một command hoặc thực hiện bước tiếp theo có phụ thuộc kết quả.

Không cần lặp cùng một log hoặc metric trong cả ProducerListener và future callback. Nếu cả hai cùng ghi một sự kiện success/error, số liệu có thể bị đếm hai lần. Hãy quyết định nơi sở hữu metric và nơi xử lý nghiệp vụ cho rõ ràng.

Trước Spring Kafka 3.0, các phương thức send thường dùng `ListenableFuture`; từ 3.0 chúng dùng `CompletableFuture`. Ví dụ cũ có thể cần điều chỉnh khi nâng cấp.

## 6. Thời điểm callback và ý nghĩa của success

### 6.1. Success có nghĩa gì?

`onSuccess` cho biết Kafka producer đã hoàn tất lần gửi theo cấu hình producer đang sử dụng. Ý nghĩa xác nhận phụ thuộc `acks`:

| Cấu hình | Điều callback success thể hiện |
|---|---|
| `acks=0` | Client hoàn tất việc gửi mà không chờ broker xác nhận |
| `acks=1` | Leader đã xác nhận theo giao thức sau khi ghi |
| `acks=all` | Các replica thuộc ISR đáp ứng điều kiện xác nhận của Kafka |

Do đó, success không đồng nghĩa consumer đã đọc record, listener đã xử lý, database đã commit hoặc một giao dịch nghiệp vụ đã hoàn tất. ProducerListener là điểm quan sát kết quả gửi ở phía producer.

### 6.2. Transaction chưa chắc đã commit

Với Kafka transaction, một record có thể được producer xác nhận gửi thành công trong khi transaction vẫn đang mở. Transaction sau đó vẫn có thể commit hoặc abort. Vì vậy, callback success của một record không chứng minh record đã trở thành dữ liệu committed mà consumer dùng `read_committed` có thể nhìn thấy.

Nếu cần biết kết quả transaction, phải quan sát kết quả của ranh giới transaction, ví dụ kết quả từ `executeInTransaction` hoặc cơ chế transaction synchronization tương ứng. Không dùng riêng ProducerListener để kết luận một transaction nhiều record đã commit.

Kafka transaction chỉ bao phủ các thao tác Kafka tham gia transaction đó. Nó không tự tạo transaction phân tán với database hay HTTP service.

### 6.3. Thứ tự callback

Một ứng dụng có thể gửi nhiều record đồng thời đến nhiều partition. Callback hoàn tất theo tiến trình xử lý của producer và broker; không có một thứ tự tổng thể giữa các partition. Không dùng thứ tự gọi ProducerListener để suy ra thứ tự nghiệp vụ trên toàn topic.

Nếu cần ordering, chọn key và partition phù hợp. Kafka đảm bảo thứ tự record trong một partition; ProducerListener chỉ quan sát kết quả từng lần gửi.

## 7. ProducerListener có xử lý retry không?

Không. Kafka producer quản lý retry nội bộ dựa trên cấu hình client như `retries`, `retry.backoff.ms`, `request.timeout.ms` và `delivery.timeout.ms`. ProducerListener nhận callback khi lần gửi có kết quả thành công hoặc lỗi cuối cùng.

Ví dụ một request bị lỗi tạm thời, producer có thể tự retry và cuối cùng gửi thành công. Khi đó listener nhận success; nó không nhất thiết nhận một callback riêng cho từng lần retry nội bộ. Muốn quan sát số lần retry, cần dùng producer metrics hoặc hệ thống monitoring phù hợp.

Nếu mọi lần retry nội bộ đều thất bại, listener nhận onError với exception tương ứng. Không nên gọi lại `KafkaTemplate.send()` ngay bên trong onError như một cơ chế retry mặc định:

- Có thể tạo vòng lặp gửi lại không giới hạn.
- Callback có thể chạy trên thread producer; gửi lại hoặc chờ đồng bộ có thể làm nghẽn đường gửi.
- Timeout không chứng minh broker chưa ghi record, nên gửi lại có thể tạo duplicate.
- Việc retry cần có giới hạn, backoff, phân loại lỗi và event ID ổn định.

Nếu nghiệp vụ cần thử gửi lại sau khi ứng dụng nhận lỗi, hãy điều phối retry ở tầng phù hợp, có giới hạn số lần, backoff và cơ chế idempotent. Với sự kiện cần bảo đảm phát ra sau khi database commit, cân nhắc transactional outbox thay vì cố gắng retry trong callback.

## 8. Viết callback an toàn cho production

ProducerListener thường được dùng như một thành phần dùng chung và callback được gọi trong đường hoàn tất của Kafka producer. Vì vậy, callback cần ngắn gọn và an toàn với xử lý đồng thời.

### 8.1. Tránh blocking

Không thực hiện các tác vụ chậm trong onSuccess/onError:

- Gọi HTTP đồng bộ đến một service khác.
- Chạy truy vấn database hoặc chờ transaction.
- Chờ future khác bằng `get()` hoặc `join()`.
- Xử lý payload lớn hoặc tính toán CPU nặng.
- Chờ khóa có thể bị giữ bởi thread khác.

Một callback chậm có thể làm chậm việc xử lý callback của producer và ảnh hưởng throughput. Nếu cần xử lý tiếp, chuyển công việc sang executor riêng có giới hạn hàng đợi hoặc một cơ chế xử lý bất đồng bộ khác. Executor phải có chính sách từ chối và metric để tránh tích tụ công việc vô hạn.

### 8.2. An toàn với nhiều thread

Một ProducerListener có thể được dùng đồng thời cho nhiều lần gửi. Không lưu trạng thái tạm của từng record vào field mutable dùng chung nếu không có đồng bộ phù hợp.

Không nên viết:

~~~java
public class UnsafeProducerListener
        implements ProducerListener<String, OrderCreated> {

    private String currentOrderId;

    @Override
    public void onSuccess(
        ProducerRecord<String, OrderCreated> record,
        RecordMetadata metadata
    ) {
        currentOrderId = record.key();
        // Other code reads currentOrderId later.
    }
}
~~~

Hai callback có thể ghi đè giá trị của nhau. Hãy dùng biến local lấy trực tiếp từ tham số callback, hoặc chuyển dữ liệu cần thiết thành một object bất biến trước khi gửi sang executor.

### 8.3. Không để lỗi callback che khuất kết quả gửi

Logic callback nên có kiểm soát exception riêng. Nếu code ghi log, tăng metric hoặc đẩy event nội bộ có thể ném exception, hãy xử lý lỗi đó tại callback và gửi cảnh báo phù hợp. Không để lỗi trong instrumentation biến thành lỗi nghiệp vụ mới hoặc làm mất thông tin về kết quả gửi ban đầu.

Đặc biệt, tránh gọi lại ProducerListener trực tiếp từ code phục hồi; callback chỉ nên được KafkaTemplate gọi theo vòng đời send.

## 9. Dùng ProducerListener cho metrics và tracing

Một listener có thể cập nhật metric cho toàn bộ lần gửi qua template. Ví dụ về các nhóm metric:

| Metric | Ý nghĩa |
|---|---|
| Producer send success count | Số lần gửi hoàn tất thành công |
| Producer send error count | Số lần gửi hoàn tất thất bại |
| Send completion latency | Thời gian từ lúc gọi send đến callback |
| Error count by exception class | Phân loại nhóm lỗi |
| Success by topic | Theo dõi luồng gửi theo topic |
| Missing metadata count | Số lần lỗi không có metadata broker |

Nhãn metric nên có cardinality thấp. Topic, outcome và nhóm exception thường phù hợp; event ID, order ID, customer ID hoặc key không nên trở thành metric label vì có thể tạo hàng triệu chuỗi nhãn.

Để tracing, có thể dùng correlation ID trong record header và đưa nó vào log hoặc trace context. Nếu cần giữ trace context xuyên qua thread callback, dùng cơ chế context propagation của hệ thống tracing đang triển khai; không giả định ThreadLocal từ request ban đầu luôn có mặt trên callback thread.

Ví dụ cập nhật metric theo topic và outcome:

~~~java
@Override
public boolean isInterestedInSuccess() {
    return true;
}

@Override
public void onSuccess(
    ProducerRecord<String, OrderCreated> record,
    RecordMetadata metadata
) {
    meterRegistry.counter(
        "app.kafka.producer.send",
        "topic", record.topic(),
        "outcome", "success"
    ).increment();
}

@Override
public void onError(
    ProducerRecord<String, OrderCreated> record,
    RecordMetadata metadata,
    Exception exception
) {
    meterRegistry.counter(
        "app.kafka.producer.send",
        "topic", record.topic(),
        "outcome", "error"
    ).increment();
}
~~~

Ví dụ cần được bổ sung constructor injection cho `MeterRegistry` và phân loại exception theo nhu cầu. Nếu cần latency, lưu thời điểm gửi ở nơi gọi hoặc dùng observation/metrics tích hợp của Spring Kafka và Micrometer; không cố suy ra latency chỉ từ metadata broker.

Không nên chỉ dựa vào ProducerListener để xây toàn bộ dashboard producer. Kết hợp callback với metric Kafka client như request latency, retry rate, buffer availability, batch size và record error rate để phân biệt lỗi ở ứng dụng với broker hoặc network.

## 10. Xử lý lỗi và phục hồi ở tầng ứng dụng

onError là điểm để ghi nhận thất bại, nhưng chiến lược phục hồi cần được thiết kế theo loại lỗi và trạng thái nghiệp vụ.

| Nhóm lỗi | Hướng xử lý |
|---|---|
| Lỗi dữ liệu hoặc serializer | Sửa schema/dữ liệu; không retry vô hạn cùng payload |
| Authorization hoặc cấu hình | Sửa quyền, credential hoặc cấu hình producer |
| Broker/network tạm thời | Để producer retry theo cấu hình; nếu thất bại cuối cùng, retry nghiệp vụ có giới hạn |
| Not enough replicas | Kiểm tra ISR, replication và min.insync.replicas |
| Timeout với kết quả không rõ | Xem khả năng record đã được ghi; dùng event ID và consumer idempotency |
| Kích thước record vượt giới hạn | Giảm payload hoặc điều chỉnh giới hạn có kiểm soát |

Nếu ứng dụng cần giữ event cho đến khi gửi thành công, transactional outbox là một lựa chọn thường dùng. Service ghi thay đổi nghiệp vụ và outbox record trong cùng transaction database. Một publisher riêng đọc outbox, gửi Kafka và đánh dấu trạng thái sau khi nhận kết quả. Nếu publisher bị dừng sau khi broker ghi nhưng trước khi cập nhật outbox, nó có thể gửi lại; consumer vẫn cần idempotency.

ProducerListener có thể cung cấp log/metric để quan sát kết quả của publisher, nhưng không thay thế cơ chế lưu trữ outbox, lịch retry, trạng thái gửi hoặc quy trình replay.

## 11. Kiểm thử ProducerListener

Có thể kiểm thử implementation độc lập bằng cách gọi callback với ProducerRecord, RecordMetadata giả lập và exception mẫu. Kiểm thử này xác nhận listener xử lý đúng metadata, log/metric và trường hợp metadata null.

Ví dụ kiểm thử đơn vị có thể tập trung vào:

- onSuccess ghi metric success đúng topic.
- onError ghi metric error và không giả định metadata luôn khác null.
- isInterestedInSuccess trả về true khi cần theo dõi success.
- Callback không gọi service ngoài hoặc thực hiện thao tác blocking.
- Listener dùng chung không giữ trạng thái của record trước trong field mutable.

Ở mức tích hợp, dùng test broker hoặc Embedded Kafka phù hợp với phiên bản Spring Kafka để xác nhận KafkaTemplate thực sự gọi listener khi gửi thành công và khi producer nhận lỗi. Với lỗi broker, cần thiết kế tình huống kiểm thử có thể tái lập; không chỉ ném exception thủ công vào implementation rồi kết luận đường gửi Kafka đã được kiểm tra.

Kiểm thử listener độc lập không chứng minh cấu hình broker, serializer, acks, retry hoặc transaction hoạt động đúng. Những phần đó cần kiểm thử ở tầng tích hợp tương ứng.

## 12. Các lỗi thường gặp khi dùng ProducerListener

**Quên override isInterestedInSuccess():** onSuccess không được gọi vì giá trị mặc định thường là false. Nếu cần success callback, trả về true.

**Giả định metadata luôn tồn tại:** Khi gửi thất bại trước khi broker trả metadata, tham số metadata trong onError có thể null. Luôn xử lý null-safe.

**Dùng ProducerListener như retry handler:** Listener không có cơ chế retry riêng. Retry nội bộ do Kafka producer quản lý; retry nghiệp vụ cần giới hạn, backoff và idempotency.

**Gọi database hoặc HTTP trong callback:** Callback chậm có thể ảnh hưởng đường xử lý producer. Chuyển công việc cần thiết sang executor có giới hạn hoặc worker riêng.

**Ghi payload vào log:** Payload có thể chứa dữ liệu nhạy cảm và làm log tăng nhanh. Ưu tiên event ID, topic, key đã được phép ghi, partition, offset và exception.

**Đếm metric trùng:** Cùng một send vừa được ProducerListener vừa được future callback ghi nhận. Chỉ định một nơi chịu trách nhiệm cho metric chung.

**Coi success là transaction commit:** Record callback thành công chưa bảo đảm transaction đã commit hoặc consumer đã xử lý. Theo dõi transaction outcome và downstream riêng.

**Dùng chung listener nhưng giữ state mutable:** Callback đồng thời có thể ghi đè trạng thái. Xử lý bằng biến local hoặc object bất biến.

## 13. Quy trình điều tra khi ProducerListener nhận onError

Khi callback lỗi xuất hiện, hãy lần theo theo thứ tự:

1. Ghi nhận topic, key hoặc event ID, exception class và thông điệp lỗi.
2. Xác định lỗi phát sinh khi serialize, chờ metadata/buffer, kết nối broker hay broker từ chối request.
3. Đọc cause chain của exception; phân biệt timeout, authorization, serialization và lỗi ISR.
4. Đối chiếu producer metrics như retry rate, request latency, buffer availability và error rate.
5. Kiểm tra broker/partition health, ISR và quyền ghi nếu lỗi đến từ broker.
6. Xác định kết quả có rõ ràng hay không. Với timeout, xem khả năng record đã được ghi trước khi quyết định gửi lại.
7. Nếu cần retry ở tầng nghiệp vụ, dùng event ID ổn định, backoff có giới hạn và cơ chế idempotent ở consumer.

Với callback success, lưu metadata cần thiết để có thể tìm record theo topic, partition và offset. Với callback error, không bịa partition/offset nếu metadata không có; lưu exception và thông tin record mà ứng dụng đã biết.

## 14. Nguyên tắc vận hành

- Gắn ProducerListener vào đúng KafkaTemplate mà service sử dụng.
- Override `isInterestedInSuccess()` khi thật sự cần callback success.
- Xử lý metadata null-safe trong onError.
- Giữ callback ngắn, không blocking và an toàn khi nhiều thread gọi đồng thời.
- Dùng ProducerListener cho logging/metrics tập trung; dùng future cho logic phụ thuộc kết quả của một lần send.
- Không retry vô hạn hoặc gửi lại mù sau timeout.
- Phân biệt xác nhận gửi, transaction commit và xử lý nghiệp vụ ở consumer.
- Kết hợp callback metrics với Kafka producer metrics và broker metrics.
- Dùng event ID ổn định cùng consumer idempotency hoặc transactional outbox khi cần bảo đảm phát event.

ProducerListener cung cấp một điểm quan sát nhất quán cho các lần gửi qua KafkaTemplate. Khi callback được dùng đúng vai trò, đội vận hành có thể biết lần gửi đã hoàn tất thế nào, thu thập metadata để truy vết và nhận diện lỗi producer. Độ tin cậy của luồng vẫn phụ thuộc vào cấu hình Kafka, transaction, retry và cách ứng dụng xử lý duplicate ở các hệ thống nhận.
