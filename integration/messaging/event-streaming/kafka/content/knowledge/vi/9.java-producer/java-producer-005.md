# Đọc RecordMetadata để xác nhận partition, offset và timestamp

## Mục tiêu bài học

Khi producer gửi một record đến Kafka, ứng dụng thường cần biết broker đã ghi record vào partition nào, tại offset nào và timestamp nào được lưu trong log. Kafka trả về thông tin này qua đối tượng RecordMetadata. Đây là cơ sở để ghi log có thể truy vết, đối chiếu vị trí record, đo độ trễ gửi và kiểm tra cách partitioner phân phối dữ liệu.

Bài học trình bày cách nhận RecordMetadata bằng Kafka Java Producer API và Spring Kafka, đọc các trường metadata quan trọng, phân biệt timestamp do producer tạo với timestamp do broker gán, xử lý callback và lỗi gửi, cũng như hiểu giới hạn của xác nhận từ producer.

Sau bài học, người học có thể:

- Giải thích RecordMetadata được trả về khi nào và dùng để làm gì.
- Đọc topic, partition, offset, timestamp và kích thước serialized record.
- Nhận metadata bằng Future, Callback và KafkaTemplate.
- Phân biệt timestamp kiểu CreateTime và LogAppendTime.
- Xử lý lỗi gửi bất đồng bộ và timeout khi chờ kết quả.
- Dùng metadata để quan sát phân phối partition và truy vết record.
- Hiểu vì sao producer ack không đồng nghĩa consumer đã xử lý nghiệp vụ.

## 1. RecordMetadata xuất hiện ở đâu trong luồng gửi?

Producer tạo ProducerRecord gồm topic, key, value và có thể có partition hoặc timestamp do ứng dụng chỉ định. Producer serialize record, chọn partition nếu ứng dụng chưa chỉ định, gom record vào batch và gửi đến broker. Khi broker trả kết quả theo cấu hình acks, producer hoàn tất việc gửi và cung cấp RecordMetadata.

~~~mermaid
flowchart TD
    A[Ứng dụng tạo ProducerRecord] --> B[Serialize key và value]
    B --> C[Chọn partition]
    C --> D[Gửi batch đến broker]
    D --> E{Broker phản hồi theo acks}
    E -->|Thành công| F[RecordMetadata]
    E -->|Thất bại hoặc hết hạn| G[Exception]
    F --> H[Đọc topic, partition, offset, timestamp]
    G --> I[Log lỗi, retry theo chính sách]
~~~

RecordMetadata thường được nhận qua:

- Future<RecordMetadata> khi gọi KafkaProducer.send(record).
- Callback truyền vào overload KafkaProducer.send(record, callback).
- SendResult.getRecordMetadata() khi dùng KafkaTemplate của Spring Kafka.

Metadata không phải đối tượng record đầy đủ. Nó không chứa payload để ứng dụng đọc lại; ProducerRecord mới giữ key, value và headers mà producer đã gửi.

## 2. Các trường quan trọng trong RecordMetadata

| Trường/phương thức | Ý nghĩa | Cách sử dụng |
|---|---|---|
| topic() | Tên topic nhận record | Xác nhận luồng dữ liệu đích |
| partition() | Số partition nhận record | Kiểm tra partitioner và phân phối tải |
| offset() | Vị trí record trong partition | Truy vết hoặc đối chiếu vị trí trong log |
| timestamp() | Timestamp được lưu cùng record | Phân tích thời gian sự kiện hoặc thời điểm broker append |
| timestampType() | Loại timestamp được lưu | Phân biệt CreateTime và LogAppendTime |
| hasOffset() | Metadata có offset hợp lệ hay không | Kiểm tra trước khi dùng offset |
| hasTimestamp() | Metadata có timestamp hay không | Kiểm tra trước khi diễn giải timestamp |
| serializedKeySize() | Kích thước key sau serialization, tính bằng byte | Quan sát kích thước record |
| serializedValueSize() | Kích thước value sau serialization, tính bằng byte | Theo dõi payload và batching |

### 2.1. Topic và partition

topic() trả về topic của record. partition() trả về partition thực tế mà producer đã gửi đến. Nếu ứng dụng không chỉ định partition trong ProducerRecord, producer partitioner quyết định partition dựa trên key hoặc chính sách phân phối record không có key.

Ví dụ:

~~~text
topic=orders partition=2
~~~

Kết quả này cho biết record được ghi vào partition 2 của topic orders. Nó hữu ích để kiểm tra key có đang phân phối đúng như thiết kế hay có partition nóng.

### 2.2. Offset

offset() là vị trí của record trong partition. Offset chỉ có ý nghĩa trong phạm vi một topic-partition, không phải số thứ tự toàn cục của topic hoặc toàn cluster.

Ví dụ:

~~~text
topic=orders partition=2 offset=1048
~~~

Có thể định danh vị trí record bằng bộ ba topic, partition và offset. Nếu chỉ ghi offset 1048 mà thiếu topic và partition, thông tin truy vết sẽ không đủ.

Offset được broker cấp khi record được append vào partition. Offset có thể không liên tiếp trong những tình huống như compaction hoặc do các loại batch/transaction record; không nên giả định hai record còn nhìn thấy luôn có offset cách nhau đúng một đơn vị.

Với producer cấu hình acks=0, broker không gửi acknowledgement. Ứng dụng không thể dựa vào metadata để xác nhận offset broker đã cấp; hãy kiểm tra hasOffset() trước khi dùng offset(). Các ví dụ trong bài dùng acks=all để nhận xác nhận từ broker.

### 2.3. Timestamp

timestamp() trả về timestamp được lưu trong record metadata. Ý nghĩa của giá trị phụ thuộc timestamp type:

- CreateTime: timestamp do producer cung cấp hoặc producer client tạo khi ứng dụng không chỉ định timestamp.
- LogAppendTime: broker ghi đè timestamp bằng thời điểm broker append record vào log.

Topic có thể cấu hình message.timestamp.type để chọn kiểu timestamp. Với CreateTime, timestamp có thể đại diện thời điểm sự kiện nghiệp vụ xảy ra nếu ứng dụng chủ động cung cấp event time. Với LogAppendTime, timestamp phản ánh thời điểm broker ghi record, hữu ích khi cần quan sát thời gian tiếp nhận.

Timestamp không phải thời điểm callback chạy và cũng không phải thời gian consumer hoàn tất xử lý. Muốn đo thời gian từ lúc gửi đến lúc nhận acknowledgement, ứng dụng cần tự đo elapsed time bằng đồng hồ monotonic như System.nanoTime().

Nếu metadata không có timestamp hợp lệ, hãy kiểm tra hasTimestamp() trước khi diễn giải giá trị. Không tự coi timestamp là UTC hoặc thời điểm nghiệp vụ nếu chưa thống nhất timezone và nguồn tạo timestamp.

### 2.4. Kích thước serialized key và value

serializedKeySize() và serializedValueSize() cho biết số byte sau khi serializer chuyển key/value thành dạng truyền trên wire. Đây không nhất thiết là kích thước JSON ban đầu trong bộ nhớ; serializer, encoding và schema format có thể làm kích thước thay đổi.

Hai trường này giúp phát hiện payload tăng bất thường hoặc key quá lớn. Chúng không bao gồm toàn bộ overhead của record batch, protocol, headers và network framing.

## 3. Nhận RecordMetadata bằng KafkaProducer

Ví dụ dưới đây dùng Kafka Java client trực tiếp với String serializer.

### 3.1. Cấu hình producer

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.common.serialization.StringSerializer;

public class ProducerFactory {

    public static KafkaProducer<String, String> create() {
        Properties props = new Properties();
        props.put("bootstrap.servers", "localhost:9092");
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", StringSerializer.class.getName());

        // Yêu cầu acknowledgement từ toàn bộ ISR hiện tại.
        props.put("acks", "all");
        props.put("enable.idempotence", "true");
        props.put("delivery.timeout.ms", "120000");

        return new KafkaProducer<>(props);
    }
}
~~~

acks=all yêu cầu broker chỉ xác nhận sau khi record được replicate theo điều kiện ISR. min.insync.replicas của topic/broker vẫn quyết định số replica đồng bộ tối thiểu cần có để chấp nhận ghi với acks=all. enable.idempotence=true giúp producer tránh ghi trùng do retry nội bộ trong phạm vi bảo đảm của producer session.

### 3.2. Chờ Future để lấy metadata

send(record) trả về Future<RecordMetadata>. Ứng dụng có thể gọi get() để chờ broker phản hồi:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

public class SyncMetadataExample {

    public static void main(String[] args) {
        try (KafkaProducer<String, String> producer = ProducerFactory.create()) {
            ProducerRecord<String, String> record =
                new ProducerRecord<>("orders", "order-42", "{\"status\":\"CREATED\"}");

            try {
                RecordMetadata metadata =
                    producer.send(record).get(10, TimeUnit.SECONDS);

                printMetadata(metadata);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted while waiting for Kafka", ex);
            } catch (ExecutionException ex) {
                throw new IllegalStateException("Kafka rejected or failed to send record", ex.getCause());
            } catch (TimeoutException ex) {
                throw new IllegalStateException("Timed out waiting for send result", ex);
            }
        }
    }

    private static void printMetadata(RecordMetadata metadata) {
        System.out.printf(
            "topic=%s partition=%d offset=%d timestamp=%d timestampType=%s%n",
            metadata.topic(),
            metadata.partition(),
            metadata.offset(),
            metadata.timestamp(),
            metadata.timestampType()
        );
    }
}
~~~

Ưu điểm của cách này là luồng code đơn giản: chỉ tiếp tục sau khi đã có kết quả gửi. Nhược điểm là get() chặn thread hiện tại. Nếu gọi cho từng record trong một vòng lặp tải lớn, ứng dụng sẽ mất lợi ích batching và gửi bất đồng bộ của producer.

Future.get(timeout) hết thời gian không có nghĩa Kafka chắc chắn chưa ghi record. Request có thể vẫn đang được xử lý hoặc acknowledgement bị trễ. Không tự động gửi lại một record chỉ vì thread chờ bị timeout nếu chưa có cơ chế idempotency ở tầng nghiệp vụ; việc gửi lại có thể tạo sự kiện trùng.

### 3.3. Đọc metadata an toàn

Một hàm dùng chung có thể kiểm tra các trường tùy tình huống:

~~~java
private static void printMetadataSafely(RecordMetadata metadata) {
    String offsetText = metadata.hasOffset()
        ? Long.toString(metadata.offset())
        : "unavailable";

    String timestampText = metadata.hasTimestamp()
        ? Long.toString(metadata.timestamp())
        : "unavailable";

    System.out.printf(
        "topic=%s partition=%d offset=%s timestamp=%s keyBytes=%d valueBytes=%d%n",
        metadata.topic(),
        metadata.partition(),
        offsetText,
        timestampText,
        metadata.serializedKeySize(),
        metadata.serializedValueSize()
    );
}
~~~

Trong cấu hình có acknowledgement như acks=1 hoặc acks=all, metadata thường có offset và timestamp. Kiểm tra hasOffset()/hasTimestamp() giúp code không giả định các trường luôn khả dụng, đặc biệt khi thay đổi cấu hình producer hoặc phiên bản client.

## 4. Nhận metadata bất đồng bộ bằng Callback

Để giữ throughput, producer thường gửi record bất đồng bộ và xử lý kết quả trong callback. Kafka gọi callback khi gửi thành công hoặc thất bại.

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

public class CallbackMetadataExample {

    public static void publish(
            KafkaProducer<String, String> producer,
            String orderId,
            String payload) {

        long startedAt = System.nanoTime();
        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", orderId, payload);

        producer.send(record, (metadata, exception) -> {
            long ackLatencyMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt
            );

            if (exception != null) {
                System.err.printf(
                    "send failed orderId=%s latencyMs=%d error=%s%n",
                    orderId,
                    ackLatencyMs,
                    exception.getMessage()
                );
                return;
            }

            System.out.printf(
                "send succeeded topic=%s partition=%d offset=%d timestamp=%d latencyMs=%d%n",
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                metadata.timestamp(),
                ackLatencyMs
            );
        });
    }

    public static void main(String[] args) {
        try (KafkaProducer<String, String> producer = ProducerFactory.create()) {
            publish(producer, "order-42", "{\"status\":\"CREATED\"}");
            publish(producer, "order-43", "{\"status\":\"CREATED\"}");
            producer.flush();
        }
    }
}
~~~

Trong ví dụ, callback xử lý cả hai trường hợp:

- exception != null: gửi thất bại sau các lần retry mà producer thực hiện theo cấu hình, hoặc phát sinh lỗi gửi.
- exception == null: metadata chứa vị trí broker đã xác nhận.

Callback chạy trên thread I/O của producer. Hãy giữ callback ngắn: ghi log, cập nhật metric hoặc chuyển kết quả sang executor khác. Tránh gọi database chậm, gọi HTTP, chờ Future hoặc gọi thao tác gửi đồng bộ ngay trong callback vì có thể làm nghẽn luồng xử lý response của producer.

flush() chờ các record đã gửi trước đó hoàn tất và callback tương ứng được thực thi. Trong ứng dụng chạy lâu, không gọi flush() sau từng record vì sẽ làm giảm khả năng batching; thường flush khi cần ranh giới đồng bộ rõ ràng hoặc trước khi đóng producer.

## 5. Chỉ định partition và timestamp trong ProducerRecord

Ứng dụng có thể chỉ định partition hoặc timestamp khi tạo record. Nếu partition là null, producer partitioner tự chọn partition.

~~~java
long eventTime = System.currentTimeMillis();

ProducerRecord<String, String> record = new ProducerRecord<>(
    "orders",
    null,          // Để partitioner chọn partition.
    eventTime,     // Timestamp do ứng dụng cung cấp.
    "order-42",    // Key.
    "{\"status\":\"PAID\"}"
);

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        System.err.println("Send failed: " + exception.getMessage());
        return;
    }

    System.out.printf(
        "partition=%d offset=%d timestamp=%d timestampType=%s%n",
        metadata.partition(),
        metadata.offset(),
        metadata.timestamp(),
        metadata.timestampType()
    );
});
~~~

Nếu chỉ định partition trực tiếp, producer gửi đến partition đó và metadata trả lại partition thực tế. Chỉ nên làm vậy khi ứng dụng có lý do rõ ràng; chỉ định partition thủ công có thể làm lệch tải và khiến code phụ thuộc vào số partition hiện tại.

Nếu gửi cùng key nhưng không chỉ định partition, partitioner mặc định thường định tuyến cùng key về cùng partition khi số partition và cấu hình partitioner ổn định. Khi tăng số partition hoặc thay đổi partitioner, key có thể được ánh xạ sang partition khác.

## 6. Timestamp: CreateTime và LogAppendTime

Timestamp có thể đại diện cho hai thời điểm khác nhau:

| Timestamp type | Nguồn timestamp | Ý nghĩa |
|---|---|---|
| CreateTime | Producer hoặc ứng dụng | Thời điểm record được tạo/sự kiện xảy ra theo đồng hồ của producer |
| LogAppendTime | Broker | Thời điểm broker append record vào log |

Ví dụ topic dùng CreateTime:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders \
  --alter --add-config message.timestamp.type=CreateTime
~~~

Ví dụ chuyển sang LogAppendTime:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders \
  --alter --add-config message.timestamp.type=LogAppendTime
~~~

Kiểm tra cấu hình:

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders --describe
~~~

Khi dùng CreateTime, các máy producer cần đồng bộ đồng hồ nếu timestamp được dùng để so sánh hoặc phân tích thời gian. Khi dùng LogAppendTime, timestamp phản ánh thời điểm broker nhận record, nhưng không thể thay thế timestamp nghiệp vụ đã xảy ra trước đó.

Độ trễ acknowledgement nên được đo riêng:

~~~java
long startedAt = System.nanoTime();
producer.send(record, (metadata, exception) -> {
    long elapsedNanos = System.nanoTime() - startedAt;
    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // elapsedMs là thời gian từ lúc gửi đến khi callback hoàn tất.
});
~~~

Không lấy metadata.timestamp() trừ cho System.currentTimeMillis() để tính send latency nếu chưa kiểm soát timestamp type, timezone và clock skew.

## 7. Đọc RecordMetadata trong Spring Kafka

Spring Kafka bọc Kafka Producer API bằng KafkaTemplate. Với Spring Kafka 3.x, các phương thức send() trả về CompletableFuture<SendResult<K,V>>. SendResult chứa ProducerRecord và RecordMetadata.

### 7.1. Cấu hình application.yml

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

### 7.2. Gửi và đọc metadata bằng CompletableFuture

~~~java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String payload) {

        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", orderId, payload);

        return kafkaTemplate.send(record)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    System.err.printf(
                        "Kafka send failed orderId=%s error=%s%n",
                        orderId,
                        exception.getMessage()
                    );
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                System.out.printf(
                    "Kafka send succeeded topic=%s partition=%d offset=%d timestamp=%d%n",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset(),
                    metadata.timestamp()
                );
            });
    }
}
~~~

Ứng dụng có thể trả CompletableFuture cho tầng gọi để tiếp tục xử lý bất đồng bộ. Không gọi join() hoặc get() trên request thread nếu không thực sự cần chờ kết quả, vì việc đó biến luồng xử lý thành đồng bộ và có thể làm tăng latency.

Với Spring Kafka 2.x, API gửi thường dùng ListenableFuture và callback addCallback; hãy đối chiếu đúng phiên bản dependency trước khi sao chép ví dụ 3.x. SendResult.getRecordMetadata() vẫn là nơi lấy metadata của record đã gửi thành công.

### 7.3. Gửi với timestamp tường minh

KafkaTemplate hỗ trợ overload gửi record có partition và timestamp:

~~~java
Long eventTimestamp = System.currentTimeMillis();

kafkaTemplate.send(
    "orders",
    null,              // Partition do partitioner chọn.
    eventTimestamp,
    "order-42",
    "{\"status\":\"SHIPPED\"}"
).whenComplete((result, exception) -> {
    if (exception != null) {
        System.err.println("Send failed: " + exception.getMessage());
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    System.out.printf(
        "partition=%d offset=%d timestamp=%d%n",
        metadata.partition(),
        metadata.offset(),
        metadata.timestamp()
    );
});
~~~

Broker có thể thay timestamp theo message.timestamp.type=LogAppendTime; vì vậy hãy đọc RecordMetadata.timestamp() để biết timestamp thực tế được lưu.

## 8. Xử lý lỗi và timeout khi lấy metadata

Không phải mọi lỗi đều xuất hiện trong cùng một thời điểm:

- Lỗi cấu hình hoặc serializer có thể xảy ra ngay trong lúc gọi send().
- Lỗi metadata lookup hoặc buffer allocation có thể làm send() chờ đến giới hạn max.block.ms.
- Lỗi network, broker hoặc hết thời gian delivery có thể được trả qua Future/Callback.
- Khi chờ Future bằng timeout riêng, get(timeout) có thể ném TimeoutException dù request vẫn có thể hoàn tất sau đó.

Một số lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SerializationException | Serializer không xử lý được key/value | Kiểm tra kiểu dữ liệu, serializer và schema |
| TimeoutException khi chờ Future | Chưa nhận kết quả trong thời gian chờ của ứng dụng | Kiểm tra broker/network và phân biệt timeout chờ với delivery timeout |
| TimeoutException khi gửi | Metadata hoặc buffer không sẵn sàng trong max.block.ms | Kiểm tra bootstrap server, broker availability và producer buffer |
| NotEnoughReplicas | ISR thấp hơn min.insync.replicas khi dùng acks=all | Khôi phục replica và kiểm tra replication health |
| NotEnoughReplicasAfterAppend | ISR giảm trong quá trình ghi trước khi đủ điều kiện acknowledgement | Kiểm tra broker lỗi, network và ISR |
| RecordTooLargeException | Record hoặc batch vượt giới hạn | Giảm payload hoặc điều chỉnh giới hạn message/batch phù hợp |
| TopicAuthorizationException | Principal không có quyền ghi topic | Kiểm tra ACL và danh tính producer |

Khi Future chờ timeout, không kết luận record chắc chắn chưa được ghi. Nếu ứng dụng retry bằng một lần gửi mới, hãy dùng event ID/idempotency key ở tầng nghiệp vụ để consumer có thể nhận diện sự kiện lặp.

Producer idempotence bảo vệ các retry do cùng producer session thực hiện theo giao thức Kafka; nó không thay thế idempotency nghiệp vụ khi ứng dụng tự gửi lại record mới sau timeout hoặc sau khi process restart.

## 9. RecordMetadata và các mức acknowledgement

RecordMetadata phải được diễn giải cùng cấu hình producer:

| acks | Hành vi xác nhận | Ý nghĩa khi đọc metadata |
|---|---|---|
| 0 | Producer không chờ broker acknowledgement | Không dựa vào offset để xác nhận broker đã append |
| 1 | Leader broker xác nhận sau khi append vào local log | Metadata xác nhận theo mức leader ack |
| all | Chờ các replica trong ISR đáp ứng điều kiện acknowledgement | Metadata xác nhận theo trạng thái ISR và min.insync.replicas |

acks=all không có nghĩa mọi replica từng được cấu hình đều phải phản hồi. Nó liên quan đến ISR hiện tại và điều kiện min.insync.replicas. Hãy thiết kế replication factor, min ISR và producer acks cùng nhau.

Producer nhận metadata thành công chỉ xác nhận việc gửi đã hoàn tất theo cấu hình acknowledgement. Nó không chứng minh:

- Consumer đã nhận record.
- Consumer đã commit offset.
- Database hoặc dịch vụ downstream đã cập nhật thành công.
- Nghiệp vụ đã hoàn tất đúng một lần.

Nếu gửi record trong Kafka transaction, acknowledgement của từng record có thể đến trước khi transaction được commit. Consumer dùng isolation.level=read_committed chỉ nhìn thấy record sau khi transaction commit; record thuộc transaction bị abort sẽ không được coi là dữ liệu đã commit.

## 10. Dùng metadata để truy vết và giám sát

### 10.1. Log có cấu trúc

Khi gửi thành công, nên log các trường đủ để tìm lại record:

~~~text
event=KafkaSendSucceeded
topic=orders
partition=2
offset=1048
timestamp=1732100000000
eventId=evt-8f21
correlationId=req-7a11
~~~

eventId và correlationId là metadata nghiệp vụ do ứng dụng quản lý. Không nên ghi payload nhạy cảm vào log chỉ để truy vết; thường chỉ cần ID, topic, partition, offset và kết quả gửi.

### 10.2. Kiểm tra phân phối partition

Thu thập số lượng record và byte theo partition từ metadata để phát hiện phân phối lệch:

| Partition | Số record gửi thành công | Byte gửi thành công |
|---:|---:|---:|
| 0 | 12.400 | 8,2 MiB |
| 1 | 12.100 | 8,0 MiB |
| 2 | 37.900 | 25,1 MiB |

Nếu một partition nhận nhiều record hoặc byte hơn hẳn, hãy kiểm tra key cardinality, hot key, custom partitioner và thay đổi số partition. Chỉ số producer cần được đối chiếu với broker metrics và consumer lag.

### 10.3. Đo acknowledgement latency

Đo khoảng thời gian từ lúc gọi send() đến khi callback hoàn tất bằng System.nanoTime(). Không dùng timestamp record thay cho acknowledgement latency.

Nên theo dõi:

- Tỷ lệ send success/failure.
- Latency trung bình và percentile (p95/p99).
- Record/byte rate theo topic và partition.
- Kích thước serialized key/value.
- Số lần retry và lỗi delivery timeout.
- Chênh lệch phân phối giữa các partition.

RecordMetadata là dữ liệu cho từng record; metrics tổng hợp nên được ghi qua Micrometer/JMX hoặc hệ thống observability thay vì chỉ ghi một log cho mọi record ở tải lớn.

## 11. Bài tập thực hành

### Bài tập 1: Đọc metadata bằng KafkaProducer

1. Tạo topic orders-lab có ba partition.
2. Cấu hình producer với acks=all và String serializer.
3. Gửi record có key order-1, order-2 và order-3.
4. In topic, partition, offset, timestamp và serialized sizes.
5. Gửi lại nhiều record cùng key và quan sát partition.

**Kết quả mong đợi:** người học giải thích được partition được chọn như thế nào và offset thuộc phạm vi partition.

### Bài tập 2: So sánh callback và Future

1. Gửi một record bằng Future<RecordMetadata> và get(timeout).
2. Gửi một batch record bằng callback.
3. Đo thời gian acknowledgement bằng System.nanoTime().
4. So sánh độ phức tạp và tác động của blocking với throughput.
5. Thử một timeout chờ ngắn trong môi trường lab và quan sát vì sao timeout không chứng minh record chưa được ghi.

### Bài tập 3: Timestamp type

1. Gửi record có timestamp tường minh vào topic dùng CreateTime.
2. Đọc timestamp() và timestampType() trong metadata.
3. Đổi topic sang LogAppendTime rồi gửi record khác.
4. So sánh timestamp nhận được.
5. Giải thích vì sao timestamp metadata không phải acknowledgement latency.

### Bài tập 4: Spring Kafka

1. Cấu hình KafkaTemplate<String, String>.
2. Gửi record có key và lấy SendResult.getRecordMetadata().
3. Log topic, partition, offset và timestamp.
4. Thử gửi đến topic không tồn tại hoặc topic không có ACL ghi trong môi trường phù hợp.
5. Xử lý exceptional completion của CompletableFuture.

## 12. Câu hỏi tự kiểm tra

1. RecordMetadata được trả về ở giai đoạn nào của quá trình gửi?
2. Vì sao offset cần đi cùng topic và partition khi truy vết?
3. timestamp() khác thời điểm callback hoàn tất như thế nào?
4. CreateTime và LogAppendTime lấy timestamp từ đâu?
5. Khi nào hasOffset() có thể không cho biết offset broker đã cấp?
6. Vì sao gọi Future.get() cho từng record có thể làm giảm throughput?
7. Vì sao callback của producer nên được giữ ngắn?
8. acks=all liên quan thế nào đến ISR và min.insync.replicas?
9. Producer nhận metadata thành công có chứng minh consumer đã xử lý record không?
10. Vì sao timeout khi chờ Future không đủ để kết luận record chưa được ghi?

Khi đọc đúng RecordMetadata, ứng dụng có thể xác nhận vị trí record theo acknowledgement, truy vết dữ liệu và giám sát producer. Việc diễn giải metadata phải luôn gắn với partition, timestamp type, cấu hình acks và trạng thái xử lý tiếp theo của hệ thống.
