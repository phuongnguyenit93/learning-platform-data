# Metadata refresh và phản ứng khi leader thay đổi

Kafka producer không gửi record đến một địa chỉ broker cố định. Mỗi partition có một leader riêng, và producer phải biết broker nào đang giữ vai trò leader để gửi Produce request đúng nơi. Khi leader thay đổi, metadata mà producer đang cache có thể đã cũ. Kafka client cần phát hiện trạng thái này, làm mới metadata và gửi lại batch đến leader mới trong giới hạn retry và timeout đã cấu hình.

Bài học này giải thích metadata cache của Java producer, cách bootstrap và refresh, các lỗi thường gặp khi leader chuyển broker, cách retry mà vẫn giữ ordering, cùng cách cấu hình và kiểm tra trong Java/Spring Kafka.

## 1. Metadata quyết định producer gửi record đến đâu

Metadata là thông tin mô tả cluster và cách các partition được phân bố. Với mỗi topic, producer cần biết:

- Topic có những partition nào.
- Broker nào đang là leader của từng partition.
- Broker nào đang giữ replica và replica nào thuộc ISR.
- Địa chỉ host/port mà client có thể dùng để kết nối đến broker.
- Leader epoch hiện tại để nhận biết các thế hệ leadership.

Ví dụ topic `orders` có ba partition:

| Partition | Leader hiện tại | Replica |
|---|---|---|
| orders-0 | Broker 1 | Broker 1, 2, 3 |
| orders-1 | Broker 2 | Broker 2, 3, 1 |
| orders-2 | Broker 3 | Broker 3, 1, 2 |

Nếu producer chọn partition 1, nó phải gửi batch đến Broker 2. Nếu Broker 2 ngừng hoạt động và Broker 3 được bầu làm leader mới, producer cần cập nhật metadata để gửi các batch tiếp theo đến Broker 3.

Metadata không phải một cấu hình tĩnh. Leader, ISR, broker membership và partition assignment có thể thay đổi trong suốt thời gian ứng dụng chạy.

### 1.1. Phân biệt controller leader và partition leader

Trong Kafka, hai khái niệm leader này có nhiệm vụ khác nhau:

- **Controller leader:** điều phối trạng thái và metadata của cluster. Trong KRaft, controller leader thuộc metadata quorum.
- **Partition leader:** broker nhận Produce request và Fetch request cho một partition cụ thể.

Một cluster có một controller leader nhưng có thể có hàng nghìn partition leader phân bố trên nhiều broker. Producer định tuyến theo partition leader; producer không gửi record qua controller leader.

Nếu controller leader thay đổi nhưng leader của partition mà producer đang ghi vẫn giữ nguyên, producer không nhất thiết phải đổi broker đích cho partition đó. Điều producer cần theo dõi là metadata về partition và broker mà nó sử dụng.

## 2. Producer lấy metadata bằng cách nào?

### 2.1. Bootstrap chỉ là điểm bắt đầu

Cấu hình `bootstrap.servers` là danh sách broker seed mà producer dùng để kết nối ban đầu. Sau khi kết nối được một broker, client gửi Metadata request để khám phá cluster, bao gồm các broker và leader của từng partition.

Ví dụ:

~~~properties
bootstrap.servers=broker-1.example.com:9092,broker-2.example.com:9092,broker-3.example.com:9092
~~~

Không cần liệt kê mọi broker trong cluster. Nên cung cấp từ hai đến ba địa chỉ seed để client vẫn có thể bootstrap nếu một địa chỉ không truy cập được.

Sau bootstrap, producer quản lý kết nối đến các broker đã biết và cache metadata. Nó không gửi tất cả Produce request về bootstrap broker.

### 2.2. Metadata response chứa gì?

Metadata response cho client biết cluster có những topic/partition nào và broker nào đang là leader. Với mỗi partition, thông tin quan trọng gồm:

- Partition ID.
- Leader broker ID; giá trị không xác định nếu partition chưa có leader.
- Leader epoch được biết gần nhất.
- Danh sách replica.
- Danh sách ISR.
- Các endpoint của broker.

Producer dùng broker ID để tìm endpoint và mở kết nối phù hợp. Khi leader thay đổi, metadata mới cung cấp leader ID và endpoint để producer cập nhật tuyến gửi.

### 2.3. Metadata cache

Java producer giữ metadata trong bộ nhớ để không phải gửi Metadata request trước mỗi record. Khi nhiều record được gửi liên tục, cache này giúp giảm request quản trị và độ trễ.

Luồng xử lý cơ bản:

1. Producer khởi tạo và kết nối đến một broker trong `bootstrap.servers`.
2. Client lấy metadata của cluster và topic cần sử dụng.
3. Partitioner chọn partition cho từng record.
4. Producer tra metadata để tìm leader của partition.
5. Sender gom record thành batch và gửi đến broker leader.
6. Khi metadata lỗi thời hoặc đến kỳ refresh, client cập nhật cache.

Metadata cache là chi tiết nội bộ của Kafka client. Ứng dụng không cần tự xây dựng bảng ánh xạ partition sang broker hoặc tự quản lý danh sách leader.

## 3. Khi nào producer làm mới metadata?

Kafka producer làm mới metadata trong nhiều tình huống.

### 3.1. Lần đầu sử dụng topic

Khi producer chưa có metadata cho topic, nó phải lấy thông tin topic và partition trước khi xác định broker đích. Nếu metadata chưa sẵn sàng, lời gọi `send()` có thể chờ.

API `partitionsFor(topic)` cũng có thể chờ metadata nếu chưa có thông tin partition.

### 3.2. Broker báo metadata đã lỗi thời

Nếu producer gửi request đến broker không còn là leader của partition, broker trả về lỗi phù hợp, thường là `NOT_LEADER_OR_FOLLOWER`. Client hiểu rằng metadata hiện tại không còn đúng và yêu cầu refresh.

Một số lỗi liên quan:

| Lỗi | Ý nghĩa | Hành động cần hiểu |
|---|---|---|
| `NotLeaderOrFollowerException` | Broker nhận request không còn là leader hoặc không còn là replica phù hợp của partition | Refresh metadata và thử lại nếu lỗi có thể retry |
| `LeaderNotAvailableException` | Partition chưa có leader khả dụng, thường trong lúc election hoặc khi tất cả replica đều không hoạt động | Chờ quá trình phục hồi, retry theo backoff và timeout |
| `UnknownTopicOrPartitionException` | Topic hoặc partition chưa tồn tại hoặc broker chưa nhận diện được | Refresh metadata; đồng thời kiểm tra tên topic và trạng thái tạo topic |
| `NetworkException` / disconnect | Kết nối đến broker bị gián đoạn hoặc broker không trả lời | Kết nối lại; nếu các broker đã biết đều không khả dụng thì có thể cần rebootstrap |
| `NotEnoughReplicasException` | ISR thấp hơn `min.insync.replicas` | Đây là vấn đề replication/durability, không thể giải quyết chỉ bằng metadata refresh |

Các lỗi trên không có cùng nguyên nhân. Metadata refresh có ích khi tuyến đến broker hoặc trạng thái partition đã cũ; nó không sửa được lỗi ACL, authentication, thiếu replica hoặc sai tên topic.

### 3.3. Refresh định kỳ theo tuổi metadata

Kafka 4.4 có cấu hình:

~~~properties
metadata.max.age.ms=300000
~~~

Mặc định là 300.000 ms, tương đương 5 phút. Sau khoảng thời gian này, producer chủ động refresh metadata ngay cả khi chưa gặp lỗi leadership, nhằm phát hiện broker hoặc partition mới.

Giá trị này là chu kỳ refresh chủ động, không phải thời gian producer phải chờ để nhận ra leader đã đổi. Khi nhận được lỗi chỉ ra metadata cũ, client có thể refresh sớm hơn.

Giảm `metadata.max.age.ms` làm tăng tần suất Metadata request. Không nên giảm mạnh chỉ để xử lý leader failover; hãy để cơ chế phản ứng theo lỗi hoạt động và chỉ điều chỉnh chu kỳ định kỳ khi có lý do đo lường rõ ràng.

### 3.4. Metadata của topic không hoạt động

`metadata.max.idle.ms` mặc định là 300.000 ms. Cấu hình này quyết định thời gian producer giữ metadata của một topic không có hoạt động produce. Khi topic idle quá lâu, metadata của topic có thể bị loại khỏi cache; lần sử dụng tiếp theo sẽ cần fetch metadata lại.

Đây không phải chu kỳ refresh định kỳ và cũng không phải timeout để phát hiện leader thay đổi.

### 3.5. Rebootstrap khi không còn broker đã biết nào khả dụng

Kafka 4.4 có cơ chế phục hồi metadata:

~~~properties
metadata.recovery.strategy=rebootstrap
metadata.recovery.rebootstrap.trigger.ms=300000
~~~

Mặc định `metadata.recovery.strategy` là `rebootstrap`. Khi tất cả broker trong metadata gần nhất đều có vẻ không khả dụng, client có thể quay lại danh sách `bootstrap.servers` để khám phá cluster một lần nữa. `metadata.recovery.rebootstrap.trigger.ms` mặc định là 5 phút và tham gia quyết định khi nào thử lại bootstrap trong trường hợp không kết nối được broker đã biết.

Cơ chế này xử lý tình huống tập broker đã biết không còn dùng được, chẳng hạn cluster đã thay đổi broker hoặc client đã kết nối quá lâu. Nó không thay thế refresh thông thường khi một partition chuyển leader.

## 4. Điều gì xảy ra khi partition chuyển leader?

Giả sử producer đang giữ metadata cũ:

- Topic `orders`, partition 0.
- Metadata cache cho biết leader là Broker 1.
- Broker 1 bị dừng hoặc mất quyền leader.
- Controller bầu Broker 2 làm leader mới.

Luồng xử lý:

~~~mermaid
sequenceDiagram
    participant P as Java Producer
    participant B1 as Broker 1 (leader cũ)
    participant B2 as Broker 2 (leader mới)
    P->>B1: Produce batch theo metadata cũ
    B1-->>P: NOT_LEADER_OR_FOLLOWER
    P->>P: Đánh dấu metadata cần refresh
    P->>B2: Metadata request qua broker còn truy cập được
    B2-->>P: Partition 0 có leader là Broker 2
    P->>B2: Retry Produce batch
    B2-->>P: Produce response / ACK
    P->>P: Hoàn tất Future nếu thành công
~~~

Các bước diễn ra như sau:

1. Producer chọn partition 0 và gửi batch đến Broker 1 theo metadata đang cache.
2. Broker 1 trả về `NOT_LEADER_OR_FOLLOWER` vì nó không còn là leader.
3. Kafka client nhận diện lỗi liên quan metadata và yêu cầu cập nhật thông tin partition.
4. Client lấy metadata mới từ một broker có thể truy cập.
5. Metadata mới cho biết Broker 2 là leader của partition 0.
6. Sender gửi lại batch đến Broker 2 nếu lỗi có thể retry và thời hạn giao hàng chưa hết.
7. Khi nhận ACK thành công, producer hoàn tất callback hoặc Future của record.

Quá trình election có thể tạo một khoảng thời gian partition chưa có leader. Trong khoảng này, producer có thể nhận `LeaderNotAvailableException` hoặc lỗi tạm thời khác. Client cần chờ theo retry backoff và tiếp tục trong giới hạn timeout.

### 4.1. Leader epoch giúp nhận diện thế hệ leadership

Leader epoch là số thế hệ tăng khi partition thay đổi leader. Metadata mới mang leader epoch mới để các broker và client nhận biết leadership đã thay đổi.

Kafka protocol hiện đại có thể trả thông tin current leader và leader epoch trong Produce response cho các lỗi leader. Client dùng thông tin này cùng metadata refresh để cập nhật tuyến gửi.

Ứng dụng không tự tăng leader epoch, không tự ghi đè leader trong metadata và không cần gọi API riêng để thông báo leader mới. Broker/controller và Kafka client phối hợp thực hiện việc này.

### 4.2. Request có thể đã được ghi nhưng ACK bị mất

Một tình huống khó chẩn đoán xảy ra khi broker đã ghi record nhưng kết nối bị ngắt trước khi producer nhận được ACK. Producer không thể chỉ dựa vào disconnect để biết chắc record đã được ghi hay chưa.

Khi retry, nếu không bật idempotence, record có thể bị ghi trùng. Kafka producer idempotence dùng producer ID và sequence number để broker nhận diện retry của cùng batch trong producer session.

Vì vậy, idempotence đặc biệt quan trọng khi leader thay đổi, network chập chờn hoặc ACK bị mất.

## 5. Retry, timeout và ordering khi leader thay đổi

Metadata refresh và retry có quan hệ chặt chẽ nhưng là hai việc khác nhau:

- **Metadata refresh** cập nhật thông tin leader và endpoint.
- **Retry** gửi lại request hoặc batch bị lỗi tạm thời.
- **Timeout** giới hạn tổng thời gian producer chờ kết quả.

### 5.1. Các cấu hình liên quan

Các mặc định dưới đây theo tài liệu producer Kafka 4.4:

| Cấu hình | Mặc định | Vai trò |
|---|---:|---|
| `metadata.max.age.ms` | 300.000 ms | Refresh metadata định kỳ |
| `metadata.max.idle.ms` | 300.000 ms | Thời gian giữ metadata topic idle trong cache |
| `max.block.ms` | 60.000 ms | Giới hạn thời gian `send()` và `partitionsFor()` chờ metadata/buffer |
| `request.timeout.ms` | 30.000 ms | Thời gian chờ phản hồi cho một request |
| `delivery.timeout.ms` | 120.000 ms | Tổng thời gian tối đa từ khi `send()` trả về đến khi record thành công hoặc thất bại |
| `retry.backoff.ms` | 100 ms | Thời gian chờ ban đầu trước khi retry request |
| `retry.backoff.max.ms` | 1.000 ms | Mức backoff tối đa |
| `retries` | 2.147.483.647 | Số lần retry tối đa; delivery timeout thường giới hạn trước |
| `max.in.flight.requests.per.connection` | 5 | Số request chưa nhận ACK tối đa trên một kết nối |

Không cần tăng `retries` vô hạn hoặc đặt timeout cực lớn để khắc phục leader change. Hãy để `delivery.timeout.ms` kiểm soát thời gian giao hàng tổng thể và dùng backoff để tránh retry liên tục khi broker đang phục hồi.

### 5.2. Phân biệt max.block.ms và delivery.timeout.ms

`max.block.ms` giới hạn thời gian lời gọi `send()` bị chặn khi producer cần chờ metadata hoặc chờ cấp phát buffer. Nó cũng áp dụng cho `partitionsFor()` khi metadata chưa sẵn sàng.

Sau khi `send()` trả về Future, việc chờ ACK và retry của record được điều khiển chủ yếu bởi `delivery.timeout.ms`, `request.timeout.ms` và retry behavior.

Giá trị `delivery.timeout.ms` nên lớn hơn hoặc bằng tổng `request.timeout.ms` và `linger.ms`, để producer có đủ thời gian chờ một request cùng độ trễ gom batch đã cấu hình.

Ví dụ, nếu `send()` trả về Future nhanh nhưng broker leader đang thay đổi, Future vẫn có thể ở trạng thái pending trong khi producer refresh metadata và retry. Nếu quá thời hạn giao hàng, Future hoàn tất với lỗi.

### 5.3. Idempotence giúp giữ thứ tự trong cùng partition

Cấu hình khuyến nghị cho producer cần độ tin cậy cao:

~~~properties
acks=all
enable.idempotence=true
max.in.flight.requests.per.connection=5
delivery.timeout.ms=120000
~~~

Trong Kafka 4.4, idempotence mặc định được bật nếu không có cấu hình xung đột. Khi bật idempotence:

- `acks` phải là `all`.
- `retries` phải lớn hơn 0.
- `max.in.flight.requests.per.connection` phải nhỏ hơn hoặc bằng 5.
- Kafka giữ sequence của producer để nhận diện batch retry và duy trì ordering.

`acks=all` yêu cầu leader chờ các replica đang nằm trong ISR xác nhận. `min.insync.replicas` đặt ngưỡng ISR tối thiểu để broker chấp nhận ghi khi dùng `acks=all`. Nếu ISR thấp hơn ngưỡng, producer có thể nhận `NotEnoughReplicasException`; metadata refresh không làm tăng số replica đang đồng bộ. Cần khôi phục follower hoặc đánh giá lại chính sách durability.

Nếu tắt idempotence và cho phép nhiều request in-flight, batch gửi sau có thể được ghi trước batch cũ khi batch cũ lỗi và phải retry. Điều này có thể làm thay đổi thứ tự record trong cùng partition.

Ordering trong Kafka được bảo đảm theo thứ tự append của một partition. Nếu ứng dụng cần thứ tự theo một thực thể nghiệp vụ, hãy dùng key ổn định để các event của thực thể đó vào cùng partition.

### 5.4. Idempotence không thay thế idempotency nghiệp vụ

Idempotent producer bảo vệ retry ở tầng Kafka producer trong phạm vi producer session. Nó không tự loại bỏ event trùng do ứng dụng khởi động lại rồi gửi lại cùng một nghiệp vụ, hoặc do nhiều service phát cùng một event.

Với nghiệp vụ quan trọng, nên có `eventId` ổn định và cơ chế deduplicate ở consumer hoặc dùng Transactional Outbox để đồng bộ thay đổi database với event phát ra.

### 5.5. Leader change không đồng nghĩa ordering bị thay đổi

Leader mới tiếp tục làm leader cho cùng partition và tiếp tục log của partition theo quy tắc replication. Việc đổi broker leader không làm thay đổi partition ID của record.

Tuy nhiên, nếu ứng dụng tăng số partition của topic, partitioner dựa trên hash key có thể ánh xạ cùng một key sang partition khác. Khi đó, event cũ và event mới của cùng key có thể nằm ở hai partition khác nhau; Kafka không cung cấp ordering toàn cục giữa hai partition.

Đừng nhầm việc đổi leader với việc thay đổi partition count hoặc thay đổi partitioner.

## 6. Cấu hình Java producer

Ví dụ dưới đây cấu hình Java producer với ba bootstrap broker, idempotence và timeout rõ ràng:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class OrderProducer {
    public static KafkaProducer<String, String> createProducer() {
        Properties props = new Properties();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "broker-1:9092,broker-2:9092,broker-3:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
            5
        );

        props.put(ProducerConfig.METADATA_MAX_AGE_CONFIG, 300_000);
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);

        return new KafkaProducer<>(props);
    }

    public static void sendOrder(
            KafkaProducer<String, String> producer,
            String orderId,
            String json
    ) {
        ProducerRecord<String, String> record =
                new ProducerRecord<>("orders", orderId, json);

        producer.send(record, (metadata, exception) -> {
            if (exception != null) {
                // Ghi log eventId/orderId và phân loại lỗi cuối cùng.
                System.err.println(
                    "Send failed for " + orderId + ": "
                    + exception.getMessage()
                );
                return;
            }

            System.out.printf(
                "topic=%s partition=%d offset=%d%n",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
    }
}
~~~

Producer tự lấy và cập nhật metadata khi cần. Ứng dụng không cần tự bắt `NotLeaderOrFollowerException` để gửi cùng record đến một broker khác bằng tay. Hãy để Kafka producer quản lý refresh và retry; callback nhận kết quả cuối cùng sau khi thành công hoặc khi lỗi không thể retry/đã hết thời gian giao hàng.

### 6.1. Xem metadata partition bằng API

Khi cần chẩn đoán, có thể gọi `partitionsFor(topic)`:

~~~java
producer.partitionsFor("orders").forEach(partitionInfo -> {
    System.out.printf(
        "partition=%d leader=%s replicas=%s isr=%s%n",
        partitionInfo.partition(),
        partitionInfo.leader(),
        java.util.Arrays.toString(partitionInfo.replicas()),
        java.util.Arrays.toString(partitionInfo.inSyncReplicas())
    );
});
~~~

API này trả về metadata mà producer đang nhìn thấy sau khi cần fetch. Dữ liệu có thể thay đổi ngay sau khi được đọc, vì vậy không nên lưu kết quả thành bảng định tuyến cố định trong ứng dụng.

## 7. Cấu hình Spring Kafka

Spring Kafka dùng Kafka Java client bên dưới. `KafkaTemplate` gửi record qua `KafkaProducer`, vì vậy metadata refresh, leader discovery, retry và idempotence vẫn do Kafka client quản lý.

Ví dụ `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1:9092
      - broker-2:9092
      - broker-3:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[metadata.max.age.ms]": 300000
        "[delivery.timeout.ms]": 120000
~~~

Gửi event bằng `KafkaTemplate`:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate
    ) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders", orderId, payload)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Ghi log có correlation ID để điều tra.
                    log.error(
                        "Cannot publish order event: {}",
                        orderId,
                        exception
                    );
                    return;
                }

                var metadata = result.getRecordMetadata();
                log.info(
                    "Published orderId={} partition={} offset={}",
                    orderId,
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
~~~

Không cần tạo một `KafkaTemplate` mới hoặc gọi refresh metadata thủ công mỗi khi leader đổi. Tạo nhiều producer không cần thiết có thể làm tăng số connection, bộ đệm và tài nguyên broker.

Nếu Future thất bại sau khi retry hết thời gian, ứng dụng cần quyết định cách xử lý nghiệp vụ: ghi outbox, retry ở tầng ứng dụng với event ID ổn định, hoặc đưa vào quy trình xử lý lỗi. Không retry vô hạn trong callback vì có thể tạo vòng lặp tải khi cluster đang gặp sự cố.

## 8. Kiểm tra metadata và quan sát producer

### 8.1. Kiểm tra leader của topic

Dùng lệnh:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Kết quả cho biết partition, leader, replicas và ISR. Chạy lệnh trước và sau khi thay đổi leader để so sánh.

### 8.2. Các metric nên theo dõi

Nhóm producer metrics hữu ích:

| Metric | Ý nghĩa khi chẩn đoán |
|---|---|
| `metadata-age` (nếu được client expose) | Tuổi metadata hiện tại |
| `record-retry-rate` | Tần suất record phải retry |
| `record-error-rate` | Tỷ lệ record gửi thất bại |
| `request-latency-avg` / `request-latency-max` | Độ trễ request đến broker |
| `record-queue-time-avg` | Thời gian record nằm trong producer buffer |
| `requests-in-flight` | Số request đang chờ phản hồi |
| `connection-count` | Số kết nối broker hiện tại |
| `buffer-available-bytes` | Dung lượng buffer producer còn trống |

Tên và khả năng expose metric có thể phụ thuộc phiên bản client và cấu hình metrics reporter. Có thể kiểm tra qua JMX hoặc hệ thống metrics mà ứng dụng đang dùng.

Ở broker, theo dõi thêm:

- Offline partitions.
- Under-replicated partitions.
- ISR shrink/expand.
- Leader election rate và thời gian bầu leader.
- Request handler queue, network processor và produce request latency.

Khi leader chuyển broker, có thể xuất hiện một đợt tăng ngắn của retry rate và request latency. Nếu các chỉ số không trở lại bình thường, hãy điều tra broker leader mới, network và ISR.

### 8.3. Đọc log đúng cách

Các thông báo như `NotLeaderOrFollower`, `LeaderNotAvailable`, `DisconnectException` và `TimeoutException` có thể xuất hiện trong lúc failover.

Cần ghép log theo:

- `client.id`.
- Topic và partition.
- Broker ID/endpoint.
- Thời điểm leader thay đổi.
- Request latency và số lần retry.
- Lỗi cuối cùng của callback/Future.

Một lỗi `NotLeaderOrFollower` đơn lẻ trong lúc chuyển leader thường là tín hiệu metadata cũ. Một chuỗi timeout kéo dài có thể chỉ ra leader chưa được bầu, advertised endpoint sai, network lỗi hoặc broker mới không hoạt động ổn định.

## 9. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NotLeaderOrFollowerException` xuất hiện ngắn khi failover | Producer gửi theo metadata cũ | Để client refresh và retry; kiểm tra leader mới nếu lỗi kéo dài |
| `LeaderNotAvailableException` lặp lại | Election chưa hoàn tất hoặc replica không đủ điều kiện làm leader | Kiểm tra broker, ISR, controller và trạng thái partition |
| Producer nhận metadata nhưng không kết nối được leader | `advertised.listeners` trả về hostname/port không thể truy cập từ ứng dụng | Kiểm tra DNS, firewall, routing và listener quảng bá |
| `TimeoutException` sau `delivery.timeout.ms` | Retry kéo dài, broker không ACK hoặc network chậm | Kiểm tra request latency, ISR, broker log và timeout |
| `UnknownTopicOrPartitionException` | Sai topic, topic chưa được tạo hoặc metadata chưa cập nhật | Kiểm tra tên topic, topic existence và quyền truy cập |
| `NotEnoughReplicasException` | ISR thấp hơn `min.insync.replicas` | Khôi phục replica và kiểm tra replication; metadata refresh không giải quyết được |
| `TopicAuthorizationException` | Principal không có quyền ghi topic | Kiểm tra ACL và danh tính ứng dụng |
| `OutOfOrderSequenceException` | Producer sequence không khớp, có thể liên quan lỗi retry/session | Kiểm tra idempotence, producer lifecycle và log broker |

### 9.1. Bootstrap được nhưng broker leader không truy cập được

Đây là lỗi cấu hình phổ biến. Producer kết nối thành công với một seed broker và lấy metadata, nhưng metadata trả về endpoint leader nội bộ mà máy chạy ứng dụng không thể truy cập.

Ví dụ, broker quảng bá `kafka-1.internal:9092`, trong khi ứng dụng chạy ngoài mạng nội bộ không phân giải được hostname đó.

Cách khắc phục là cấu hình `advertised.listeners` phù hợp với mạng client, DNS và routing. Thêm nhiều `bootstrap.servers` không sửa được endpoint leader sai mà broker quảng bá.

### 9.2. Nhầm lỗi replication với lỗi metadata

Nếu partition có leader nhưng ISR thấp hơn `min.insync.replicas`, producer có thể nhận `NotEnoughReplicasException`. Producer đã biết broker leader ở đâu; vấn đề là điều kiện durability không đạt.

Không nên giảm `min.insync.replicas` hoặc đổi `acks` chỉ để làm lỗi biến mất mà chưa đánh giá rủi ro mất dữ liệu.

## 10. Lab: quan sát producer khi partition chuyển leader

Mục tiêu: gửi event liên tục đến một topic, thay đổi leader của một partition và quan sát producer tự refresh metadata.

### Bước 1: Chuẩn bị cluster

Dùng cluster thử nghiệm có ít nhất ba broker và topic có replication factor 3:

~~~bash
bin/kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --partitions 3 \
  --replication-factor 3
~~~

Kiểm tra leader và ISR:

~~~bash
bin/kafka-topics.sh --describe \
  --bootstrap-server localhost:9092 \
  --topic orders
~~~

Ghi lại leader của partition 0.

### Bước 2: Chạy producer

Dùng Java producer ở phần trước để gửi nhiều record với key ổn định, ví dụ `order-1001`. Log kết quả gồm topic, partition và offset.

Quan sát:

- Các record cùng key đi vào cùng partition khi partition count không thay đổi.
- Producer giữ metadata cache và gửi đến leader tương ứng.
- Callback chỉ báo lỗi cuối cùng nếu client không thể giao record trong giới hạn timeout.

### Bước 3: Thay đổi leader trong môi trường lab

Trong cluster thử nghiệm, có thể yêu cầu preferred leader election cho partition 0:

~~~bash
bin/kafka-leader-election.sh \
  --bootstrap-server localhost:9092 \
  --election-type preferred \
  --topic orders \
  --partition 0
~~~

Lệnh chỉ thành công khi replica preferred có thể trở thành leader. Nếu preferred replica không khả dụng hoặc không nằm trong ISR theo điều kiện cần thiết, hãy kiểm tra trạng thái replica trước khi tiếp tục.

Kiểm tra lại:

~~~bash
bin/kafka-topics.sh --describe \
  --bootstrap-server localhost:9092 \
  --topic orders
~~~

### Bước 4: Quan sát producer

Trong log producer, quan sát request có thể gặp `NotLeaderOrFollower` trong lúc chuyển đổi, metadata refresh và retry. Ghi nhận:

- Leader cũ và leader mới.
- Khoảng thời gian từ khi đổi leader đến khi producer gửi thành công trở lại.
- Số lần retry và request latency.
- Có record nào thất bại sau `delivery.timeout.ms` hay không.
- Ordering của record cùng partition.

### Bước 5: Thử các lỗi khác nhau

Trong môi trường lab riêng, thử:

- Tắt một broker đang giữ leader.
- Khôi phục broker và quan sát replica bắt kịp.
- Làm gián đoạn kết nối từ producer đến endpoint broker.
- Dùng hostname `advertised.listeners` không thể phân giải trong một môi trường test để hiểu lỗi định tuyến.
- Tạo topic không tồn tại và quan sát lỗi khác với leader change.

Không thực hiện các thử nghiệm dừng broker hoặc thay đổi listener trên cluster production.

## 11. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Producer gửi mọi record đến bootstrap broker | Bootstrap broker chỉ giúp khám phá cluster; Produce request đi đến leader của partition |
| Producer phải polling metadata liên tục | Client cache metadata và refresh khi cần hoặc theo chu kỳ |
| `metadata.max.age.ms` là thời gian phát hiện leader failover | Lỗi từ broker có thể kích hoạt refresh sớm hơn chu kỳ định kỳ |
| `metadata.max.idle.ms` là chu kỳ refresh | Nó điều khiển thời gian giữ metadata của topic idle |
| Controller leader là broker nhận mọi Produce request | Producer gửi đến partition leader |
| Ứng dụng phải tự bắt lỗi NotLeader rồi gửi lại sang broker khác | Kafka producer quản lý metadata refresh và retry |
| Tăng `retries` sẽ giải quyết mọi lỗi | Lỗi không retry được, ACL, sai endpoint và delivery timeout vẫn làm send thất bại |
| Idempotence bảo đảm không có event trùng ở cấp nghiệp vụ | Nó bảo vệ retry của producer session; ứng dụng vẫn cần event ID/deduplication |
| Đổi partition leader làm đổi partition của record | Leader đổi broker; partition ID vẫn giữ nguyên |
| Tăng số partition không ảnh hưởng ordering theo key | Hash mapping có thể thay đổi, khiến cùng key được gửi sang partition khác |

## 12. Checklist triển khai producer

- [ ] `bootstrap.servers` có nhiều seed broker có thể truy cập.
- [ ] `advertised.listeners` trả về endpoint có thể truy cập từ môi trường ứng dụng.
- [ ] Producer dùng metadata cache và không tự duy trì bảng leader riêng.
- [ ] Hiểu sự khác nhau giữa controller leader và partition leader.
- [ ] `metadata.max.age.ms` được đặt theo nhu cầu và không bị giảm tùy tiện.
- [ ] Hiểu `metadata.max.idle.ms` và `metadata.recovery.strategy`.
- [ ] `max.block.ms`, `request.timeout.ms` và `delivery.timeout.ms` được phân biệt rõ.
- [ ] Producer bật idempotence và `acks=all` nếu cần độ tin cậy cao.
- [ ] `max.in.flight.requests.per.connection` không vượt 5 khi bật idempotence.
- [ ] Có log và metric cho retry, error rate, request latency và broker connection.
- [ ] Đã thử leader election trong môi trường lab.
- [ ] Đã kiểm tra lỗi advertised endpoint, ISR thấp và topic không tồn tại.
- [ ] Ứng dụng có chiến lược xử lý Future thất bại và event ID ổn định.

## 13. Tài liệu tham khảo

- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Protocol](https://kafka.apache.org/44/design/protocol/)
- [Apache Kafka 4.4 – Producer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Apache Kafka 4.4 – NotLeaderOrFollowerException](https://kafka.apache.org/44/javadoc/org/apache/kafka/common/errors/NotLeaderOrFollowerException.html)
- [Spring for Apache Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)

Metadata refresh cho phép producer thích nghi với thay đổi broker và leader mà không cần ứng dụng tự quản lý tuyến gửi. Khi kết hợp retry, timeout và idempotence đúng cách, producer có thể tiếp tục gửi dữ liệu qua những lần leader chuyển đổi ngắn, đồng thời giữ thứ tự trong từng partition và báo lỗi rõ ràng khi cluster không phục hồi trong giới hạn đã đặt.
