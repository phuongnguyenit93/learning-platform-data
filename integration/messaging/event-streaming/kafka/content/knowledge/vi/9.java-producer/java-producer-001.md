# Vòng đời KafkaProducer và cấu hình tối thiểu

`KafkaProducer` là client Java dùng để ghi record vào topic của Apache Kafka. Một producer thường được tạo một lần và tái sử dụng trong suốt vòng đời ứng dụng hoặc service. Khi gửi record, producer chọn partition, gom record thành batch, gửi request bất đồng bộ đến broker và nhận kết quả qua callback hoặc Future.

Hiểu vòng đời này giúp tránh các lỗi phổ biến như tạo producer cho từng message, đóng producer quá sớm, gọi `flush()` sau mỗi record làm mất lợi ích batching, hoặc chỉ kiểm tra lỗi lúc gọi `send()` mà bỏ qua lỗi trả về sau đó.

## 1. KafkaProducer làm những việc gì?

Producer Java đảm nhiệm nhiều công việc trước khi record được ghi vào Kafka:

1. Nhận cấu hình bootstrap broker, serializer và các chính sách gửi.
2. Khởi tạo metadata client để tìm broker và partition leader.
3. Serialize key và value thành byte.
4. Chọn partition dựa trên partition chỉ định, key và partitioner.
5. Đưa record vào bộ đệm theo partition.
6. Gom record thành batch và gửi request đến broker leader.
7. Xử lý retry, nhận acknowledgement và hoàn tất Future/callback.

Sơ đồ đơn giản:

~~~mermaid
flowchart TD
    A["Application creates ProducerRecord"] --> B["KafkaProducer.send()"]
    B --> C["Serialize key and value"]
    C --> D["Choose topic partition"]
    D --> E["RecordAccumulator<br/>buffer by partition"]
    E --> F["Sender background thread"]
    F --> G["Broker partition leader"]
    G --> H["Broker acknowledgement"]
    H --> I["Complete Future / callback"]
~~~

`KafkaProducer` có thể được nhiều thread trong ứng dụng sử dụng đồng thời. Client quản lý việc gom batch và gửi request bằng thread nền. Ứng dụng không cần tự tạo một thread gửi riêng cho mỗi record.

## 2. Vòng đời của một producer

### 2.1. Khởi tạo và nạp cấu hình

Ứng dụng tạo một đối tượng `Properties` hoặc cấu hình tương đương, khai báo địa chỉ Kafka, serializer và các thuộc tính gửi. Sau đó tạo `KafkaProducer`.

Ví dụ:

~~~java
Properties props = new Properties();

props.put(
    ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);
props.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);

KafkaProducer<String, String> producer =
    new KafkaProducer<>(props);
~~~

Constructor khởi tạo tài nguyên nội bộ và các thành phần cần thiết cho việc gửi. Không nên giả định constructor đã kiểm tra xong mọi broker hoặc mọi topic; việc lấy metadata và thiết lập kết nối có thể tiếp tục diễn ra khi producer bắt đầu gửi.

### 2.2. Tạo ProducerRecord

Mỗi lần gửi, ứng dụng tạo `ProducerRecord` gồm topic, key và value. Có thể chỉ định partition hoặc timestamp nếu nghiệp vụ cần.

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        "order-123",
        "{\"eventType\":\"OrderCreated\"}"
    );
~~~

Trong ví dụ:

- `orders` là topic đích.
- `order-123` là key.
- JSON là value.

Nếu dùng key, partitioner có thể định tuyến các record cùng key vào cùng partition để giữ thứ tự trong phạm vi partition đó. Nếu không có key, producer áp dụng chính sách phân phối record không key của client.

### 2.3. Gửi record bất đồng bộ

Phương thức `send()` trả về `Future<RecordMetadata>`. Ứng dụng có thể tiếp tục làm công việc khác trong khi producer gửi record. Khi broker phản hồi, callback được gọi hoặc Future hoàn tất.

~~~java
producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Ghi log và xử lý lỗi gửi.
        System.err.println("Send failed: " + exception.getMessage());
        return;
    }

    System.out.printf(
        "topic=%s partition=%d offset=%d%n",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Callback cho biết kết quả của lần gửi: lỗi hoặc metadata của record đã được broker xác nhận theo cấu hình `acks`. Callback thường được gọi trên thread I/O nền của producer; tránh thực hiện công việc nặng, chờ đồng bộ lâu hoặc gọi các thao tác blocking trong callback. Nếu cần xử lý hậu kỳ nặng, hãy chuyển kết quả sang executor riêng.

### 2.4. Flush và đóng producer

`flush()` chờ các record đã được gửi trước thời điểm gọi hoàn tất. Nó hữu ích khi ứng dụng cần chắc chắn các lần gửi đang chờ đã có kết quả trước một mốc cụ thể.

`close()` đóng producer, giải phóng tài nguyên và chờ xử lý các lần gửi còn tồn đọng theo hành vi đóng của client. Ứng dụng cần đóng producer khi service dừng, không đóng sau từng record.

Với ứng dụng Java, try-with-resources là cách đơn giản để bảo đảm producer được đóng:

~~~java
try (KafkaProducer<String, String> producer =
         new KafkaProducer<>(props)) {

    producer.send(record, callback);
    producer.flush();
}
~~~

Trong service chạy lâu dài, thường tạo producer khi khởi động ứng dụng, tái sử dụng cho các request và đóng trong lifecycle shutdown. Không tạo rồi đóng một producer cho mỗi HTTP request hoặc mỗi message, vì thao tác này làm tăng chi phí kết nối, metadata và mất hiệu quả batching.

## 3. Cấu hình tối thiểu cho producer

Một producer cần biết broker để bootstrap và cách chuyển đổi key/value thành bytes. Với ứng dụng Java dùng chuỗi:

~~~properties
bootstrap.servers=localhost:9092
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.StringSerializer
client.id=orders-service-producer
acks=all
enable.idempotence=true
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Mục đích | Gợi ý |
|---|---|---|
| `bootstrap.servers` | Danh sách địa chỉ broker ban đầu | Khai báo nhiều broker có thể truy cập |
| `key.serializer` | Serialize key | Chọn theo kiểu key của ứng dụng |
| `value.serializer` | Serialize value | Chọn theo định dạng event |
| `client.id` | Nhận diện producer trong log/metric | Dùng tên service dễ tìm |
| `acks` | Mức acknowledgement producer chờ | `all` khi cần độ bền ghi cao |
| `enable.idempotence` | Hạn chế duplicate do retry của producer | Bật cho luồng ghi cần độ tin cậy |
| `delivery.timeout.ms` | Giới hạn tổng thời gian giao record, gồm retry | Đặt theo SLA và thời gian chịu lỗi |
| `max.block.ms` | Giới hạn thời gian một số thao tác gửi chờ metadata/buffer | Theo dõi timeout khi cluster nghẽn |

Có thể khai báo bằng Java:

~~~java
Properties props = new Properties();

props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(
    ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);
props.put(
    ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName()
);
props.put(ProducerConfig.CLIENT_ID_CONFIG, "orders-service-producer");
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
~~~

Với Kafka client hiện đại, idempotence thường được bật mặc định khi các cấu hình liên quan tương thích. Khai báo rõ giúp người đọc cấu hình hiểu chủ đích của ứng dụng. Nếu thay đổi `acks`, retry hoặc số request đang chờ trên một kết nối, hãy bảo đảm cấu hình vẫn tương thích với điều kiện idempotence của phiên bản client.

### 3.1. Chọn bootstrap.servers

`bootstrap.servers` là các điểm bắt đầu để producer kết nối và lấy metadata. Không cần liệt kê mọi broker, nhưng nên cung cấp nhiều broker có thể truy cập để client vẫn bootstrap được khi một địa chỉ gặp sự cố.

Ví dụ:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
~~~

Địa chỉ phải phù hợp với môi trường chạy ứng dụng. Container trong cùng Docker network có thể dùng service name như `kafka-1`; ứng dụng chạy trên host hoặc máy khác cần listener và địa chỉ được broker quảng bá tương ứng.

### 3.2. Chọn serializer

Serializer chuyển kiểu dữ liệu Java thành byte để broker lưu trữ. Key và value có serializer độc lập.

| Kiểu dữ liệu Java | Serializer thường dùng |
|---|---|
| `String` | `StringSerializer` |
| `byte[]` | `ByteArraySerializer` |
| `Integer` | `IntegerSerializer` |
| `Long` | `LongSerializer` |

Với JSON, Avro hoặc Protobuf, ứng dụng có thể dùng serializer tương ứng từ thư viện đang chọn. Producer và consumer phải thống nhất schema/format, encoding và cách quản lý version. Không nên dùng `toString()` tùy tiện làm định dạng event vì kết quả có thể không ổn định giữa các phiên bản code.

Nếu serializer ném lỗi, record không thể được gửi thành công. Lỗi serialize có thể xuất hiện ngay trong quá trình gọi `send()`, trước khi có callback hoàn tất.

## 4. send() bất đồng bộ nhưng không có nghĩa luôn không chờ

`send()` chủ yếu bất đồng bộ đối với thao tác truyền dữ liệu và chờ broker. Tuy nhiên, lời gọi có thể chờ trong một số trường hợp:

- Producer cần metadata của topic/partition nhưng metadata chưa sẵn sàng.
- Bộ đệm gửi đầy và cần chờ chỗ trống.
- Serializer thực hiện công việc đồng bộ.
- Ứng dụng đã chờ quá thời gian `max.block.ms`.

Do đó, `send()` có thể ném exception ngay tại thread gọi. Sau khi record được nhận vào luồng gửi, lỗi xảy ra trong quá trình gửi đến broker sẽ được báo qua callback hoặc Future.

Phân biệt hai nhóm lỗi:

| Thời điểm | Ví dụ | Nơi xử lý |
|---|---|---|
| Trước khi record được chấp nhận vào luồng gửi | Serializer lỗi, metadata không lấy được, buffer hết thời gian chờ | try/catch quanh `send()` |
| Trong quá trình broker xử lý/gửi request | Timeout, authorization failure, topic lỗi, replica không đủ | Callback hoặc Future |

Ví dụ bắt cả lỗi đồng bộ và bất đồng bộ:

~~~java
try {
    producer.send(record, (metadata, exception) -> {
        if (exception != null) {
            logSendFailure(record, exception);
        } else {
            logSendSuccess(metadata);
        }
    });
} catch (KafkaException exception) {
    // send() chưa chấp nhận record vào luồng gửi.
    logSendFailure(record, exception);
}
~~~

Các hàm `logSendFailure` và `logSendSuccess` trong ví dụ đại diện cho logger/telemetry của ứng dụng.

## 5. Batching và thread gửi nền

Producer không nhất thiết gửi từng record thành một request riêng. Các record của cùng partition có thể được gom vào batch trong `RecordAccumulator`. Thread nền `Sender` lấy batch đã sẵn sàng và gửi đến broker leader.

Các cấu hình ảnh hưởng đến batching:

| Thuộc tính | Ý nghĩa |
|---|---|
| `batch.size` | Kích thước mục tiêu của batch cho một partition |
| `linger.ms` | Thời gian producer chờ thêm record để gom batch trước khi gửi |
| `buffer.memory` | Bộ nhớ dành cho các record đang chờ gửi |
| `compression.type` | Thuật toán nén batch, ví dụ gzip, lz4, snappy hoặc zstd nếu client hỗ trợ |

Ví dụ:

~~~properties
batch.size=32768
linger.ms=5
buffer.memory=67108864
compression.type=lz4
~~~

Đây là giá trị minh họa, không phải cấu hình tối ưu cho mọi workload.

- Tăng `batch.size` có thể cải thiện hiệu quả khi mỗi partition có đủ lưu lượng, nhưng có thể làm tăng bộ nhớ sử dụng.
- Tăng `linger.ms` có thể tạo batch lớn hơn và tăng throughput, đổi lại độ trễ chờ gửi có thể tăng.
- Tăng `buffer.memory` giúp giữ nhiều record đang chờ hơn, nhưng không sửa được tình trạng broker hoặc network nghẽn kéo dài.
- Nén giảm lượng byte truyền và lưu trữ, nhưng tiêu tốn CPU. Hãy benchmark với dữ liệu thực tế.

Không gọi `flush()` sau mỗi record nếu không có yêu cầu đặc biệt về thời điểm hoàn tất. Flush liên tục làm giảm khả năng gom batch và thường khiến throughput kém hơn.

## 6. Acknowledgement, retry và idempotence

### 6.1. acks

Producer chọn mức xác nhận qua `acks`:

| Giá trị | Hành vi |
|---|---|
| `0` | Không chờ broker acknowledgement |
| `1` | Chờ leader xác nhận sau khi append vào log cục bộ |
| `all` | Chờ các replica hiện thuộc ISR xác nhận theo semantics Kafka |

`acks=all` thường được kết hợp với `min.insync.replicas` ở broker hoặc topic. Ví dụ RF = 3 và min ISR = 2 cho phép ghi khi còn ít nhất hai replica trong ISR. Khi ISR giảm xuống một, broker từ chối ghi thay vì hạ thấp mức replication yêu cầu.

### 6.2. Retry và delivery timeout

Producer có thể retry những lỗi tạm thời, ví dụ leader đang chuyển hoặc broker tạm thời không sẵn sàng. `delivery.timeout.ms` giới hạn tổng thời gian producer cố giao một record, gồm thời gian chờ batch, request và retry.

Nếu hết thời gian này, callback/Future nhận lỗi. Ứng dụng cần xác định hành vi tiếp theo: ghi log, retry ở tầng nghiệp vụ, đưa event vào outbox hoặc báo lỗi cho caller. Tránh retry vô hạn ở nhiều tầng cùng lúc vì có thể tạo tải dồn lên cluster.

### 6.3. Idempotent producer

Khi bật `enable.idempotence=true`, producer dùng producer ID và sequence number để broker nhận diện request retry, giúp tránh ghi trùng do retry trong phạm vi producer session và giữ thứ tự theo các điều kiện cấu hình được hỗ trợ.

Idempotence không bảo đảm một event chỉ được xử lý đúng một lần ở mọi hệ thống bên ngoài Kafka. Nếu consumer ghi database rồi chết trước khi commit offset, nghiệp vụ vẫn có thể được thực hiện lại. Cần idempotent consumer, idempotency key hoặc transactional/outbox design ở ranh giới tương ứng.

Không nên tự ý tắt idempotence trong luồng ghi cần reliability chỉ để ép throughput tăng. Hãy đo batch size, compression, partition distribution và network trước khi thay đổi semantics.

## 7. Gửi đồng bộ hay bất đồng bộ?

Hai cách thường gặp:

**Bất đồng bộ với callback** phù hợp khi ứng dụng cần throughput và có thể xử lý kết quả sau:

~~~java
producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        handleFailure(exception);
        return;
    }

    handleSuccess(metadata);
});
~~~

**Đồng bộ bằng Future.get()** phù hợp với tác vụ ít record hoặc khi bước hiện tại cần biết kết quả trước khi đi tiếp:

~~~java
RecordMetadata metadata =
    producer.send(record).get();

System.out.printf(
    "partition=%d offset=%d%n",
    metadata.partition(),
    metadata.offset()
);
~~~

Cách đồng bộ sẽ chặn thread gọi cho đến khi gửi xong hoặc phát sinh lỗi. Nếu gọi `get()` cho từng record trong một vòng lặp, ứng dụng giảm khả năng tận dụng batching và gửi song song. Với workload nhiều record, thường nên dùng async và quản lý callback/giới hạn outstanding request phù hợp.

## 8. Ví dụ hoàn chỉnh: producer Java tối thiểu

Ví dụ dưới đây dùng String key/value, gửi một event vào topic `orders`, nhận callback và đóng producer đúng cách.

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.errors.KafkaException;
import org.apache.kafka.common.serialization.StringSerializer;

public class OrderProducer {

    public static void main(String[] args) {
        Properties props = new Properties();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(
            ProducerConfig.CLIENT_ID_CONFIG,
            "orders-service-producer"
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(props)) {

            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "order-123",
                    "{\"eventType\":\"OrderCreated\",\"orderId\":\"order-123\"}"
                );

            try {
                producer.send(record, (metadata, exception) -> {
                    if (exception != null) {
                        System.err.println(
                            "Cannot deliver event: " + exception.getMessage()
                        );
                        return;
                    }

                    System.out.printf(
                        "Delivered topic=%s partition=%d offset=%d%n",
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset()
                    );
                });
            } catch (KafkaException exception) {
                // Lỗi xảy ra ngay khi send() chưa chấp nhận record.
                System.err.println(
                    "Cannot enqueue event: " + exception.getMessage()
                );
            }

            // Chờ các record đã gửi hoàn tất trước khi đóng producer.
            producer.flush();
        }
    }
}
~~~

Để chạy ví dụ, project cần dependency `kafka-clients` tương thích với phiên bản Kafka cluster. Ví dụ Maven, đặt phiên bản trong property quản lý dependency của project:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>${kafka.version}</version>
</dependency>
~~~

Trong ứng dụng thực tế, thay `localhost:9092` bằng bootstrap endpoint truy cập được từ môi trường triển khai, đưa cấu hình ra environment/config service và dùng logger thay cho `System.out`.

## 9. Quản lý producer trong ứng dụng Spring

Trong Spring Boot, không nên tự tạo một `KafkaProducer` mới trong mỗi lần gọi service. Spring Kafka cung cấp `KafkaTemplate`, thường được cấu hình từ producer factory và quản lý lifecycle phù hợp với ứng dụng.

Ví dụ gửi message bằng `KafkaTemplate`:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String eventJson) {
        kafkaTemplate.send("orders", orderId, eventJson)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Ghi log hoặc chuyển sang xử lý lỗi phù hợp.
                    return;
                }

                RecordMetadata metadata =
                    result.getRecordMetadata();

                // Ghi nhận topic, partition và offset.
            });
    }
}
~~~

Cấu hình Spring Boot thường nằm trong `spring.kafka.bootstrap-servers` và các thuộc tính producer serializer/acks/idempotence. Cách khai báo cụ thể tùy phiên bản Spring Boot và Spring Kafka. `KafkaTemplate` là abstraction của Spring; không trộn lifecycle của nó với việc tự đóng KafkaProducer do producer factory quản lý.

## 10. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không serialize được record | Serializer không tương thích kiểu dữ liệu hoặc schema | Kiểm tra key/value type, serializer và schema |
| Timeout khi gọi send | Không lấy được metadata, buffer đầy hoặc broker không phản hồi | Kiểm tra bootstrap, advertised listener, buffer và network |
| Callback nhận lỗi | Broker từ chối, timeout, authorization hoặc ISR không đủ | Đọc exception đầy đủ, kiểm tra ACL, topic, leader và ISR |
| Producer gửi chậm | Batch nhỏ, linger thấp, nén tốn CPU hoặc broker/network nghẽn | Đo throughput, batch size, compression và latency |
| Dữ liệu bị trùng sau retry ở tầng ứng dụng | Retry nghiệp vụ không có idempotency key | Dùng event ID và xử lý idempotent |
| Ứng dụng mất record khi shutdown | Producer bị kết thúc trước khi gửi tồn đọng hoàn tất | Flush/close đúng lifecycle và theo dõi callback |
| Producer kết nối được bootstrap nhưng gửi thất bại | Broker quảng bá địa chỉ client không truy cập được | Kiểm tra metadata và advertised.listeners |

Một số lưu ý vận hành:

- Theo dõi tỷ lệ record gửi thành công/thất bại, request latency, retry rate và buffer availability.
- Dùng `client.id` riêng cho từng service hoặc nhóm producer để dễ truy vết.
- Không log toàn bộ payload nếu event có dữ liệu nhạy cảm.
- Đặt timeout theo SLA và thời gian outage mà ứng dụng có thể chịu.
- Khi shutdown, ngừng nhận công việc mới trước, sau đó flush/close producer và chờ hoàn tất trong giới hạn thời gian của nền tảng.

## 11. Checklist trước khi dùng KafkaProducer

- [ ] Producer được tạo một lần và tái sử dụng, không tạo theo từng record.
- [ ] `bootstrap.servers` truy cập được từ môi trường ứng dụng.
- [ ] Key/value serializer khớp kiểu dữ liệu và hợp đồng event.
- [ ] Key được chọn đúng phạm vi cần giữ thứ tự.
- [ ] `acks`, idempotence và min ISR phù hợp với yêu cầu độ bền.
- [ ] Có xử lý cả lỗi đồng bộ khi gọi `send()` và lỗi trong callback/Future.
- [ ] Callback không thực hiện công việc blocking hoặc quá nặng.
- [ ] Batch, linger, buffer và compression được điều chỉnh dựa trên số liệu.
- [ ] Không flush sau từng record nếu không có lý do nghiệp vụ.
- [ ] Producer được flush/close trong lifecycle shutdown.
- [ ] Có metric và log đủ để theo dõi lỗi, latency và retry.

KafkaProducer là một thành phần có trạng thái và tài nguyên nền, được thiết kế để tái sử dụng và gửi bất đồng bộ. Một cấu hình khởi đầu tốt cần xác định đúng broker, serializer, acknowledgement và idempotence; sau đó mới điều chỉnh batching, nén và buffer theo workload thực tế. Việc xử lý callback/Future và đóng producer đúng thời điểm quan trọng không kém lời gọi `send()` để bảo đảm ứng dụng biết record đã được giao hay chưa.
