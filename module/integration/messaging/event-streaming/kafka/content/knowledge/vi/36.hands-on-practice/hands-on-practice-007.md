# Pipeline đọc, biến đổi và ghi bằng giao dịch Kafka

Bài thực hành xây dựng một pipeline event streaming đọc record từ topic đầu vào, kiểm tra và biến đổi dữ liệu, ghi kết quả sang topic đầu ra rồi commit offset đầu vào trong cùng một Kafka transaction. Khi pipeline lỗi giữa chừng, Kafka có thể hủy phần ghi đầu ra và phần commit offset, nhờ đó lần chạy lại không để lại một nửa kết quả.

Lab dùng đơn hàng làm ví dụ. Event hợp lệ được chuẩn hóa rồi ghi vào `orders.accepted`; event không hợp lệ được ghi vào `orders.rejected` kèm lý do. Consumer chỉ tiến offset sau khi transaction chứa kết quả tương ứng được commit.

## 1. Kết quả cần đạt

Sau bài thực hành, người học có thể:

- Thiết kế pipeline đọc-transform-write theo key và partition.
- Phân biệt lỗi dữ liệu nghiệp vụ với lỗi hạ tầng có thể retry.
- Cấu hình transactional producer và consumer phù hợp.
- Ghi output records và input offsets atomically trong một transaction.
- Dùng `read_committed` để consumer chỉ đọc dữ liệu đã commit.
- Hiểu vai trò của `transactional.id`, producer fencing và consumer group generation.
- Kiểm thử crash trước commit, lỗi send, rebalance và restart.
- Tổ chức cùng pipeline bằng Kafka client thuần và Spring Kafka.

Pipeline này cung cấp exactly-once processing trong phạm vi Kafka read-process-write khi được cấu hình và sử dụng đúng. Nó không tự bao phủ database, HTTP API, email hoặc side effect bên ngoài Kafka.

## 2. Kiến trúc pipeline

~~~mermaid
flowchart LR
    P["Order producer"] --> R[("orders.raw")]
    R --> W["Order pipeline consumer"]
    W --> V{"Validate"}
    V -->|"Hợp lệ"| T["Normalize / enrich"]
    V -->|"Không hợp lệ"| D["Build rejection"]
    T --> A[("orders.accepted")]
    D --> X[("orders.rejected")]
    A --> C["Commit output + input offsets"]
    X --> C
    C --> G["Consumer group position"]
~~~

Trong một lần xử lý, pipeline thực hiện ba nhóm thao tác:

1. Đọc một batch record từ `orders.raw`.
2. Ghi từng kết quả vào `orders.accepted` hoặc `orders.rejected`.
3. Gửi offset tiếp theo của từng partition vào transaction, rồi commit transaction.

Nếu commit thành công, output và offset đầu vào cùng có hiệu lực. Nếu transaction bị abort, output của transaction không hiển thị với consumer `read_committed`, và offset đầu vào không được commit bởi transaction đó. Pipeline có thể đọc lại batch.

Không được tự gọi `consumer.commitSync()` cho các offset này sau transaction. Làm vậy sẽ tách offset khỏi output và phá vỡ bảo đảm atomic mà lab đang xây dựng.

## 3. Thiết kế topic và event contract

### 3.1. Topic sử dụng

| Topic | Vai trò | Cleanup policy gợi ý |
|---|---|---|
| `orders.raw` | Event đơn hàng đầu vào | `delete` theo retention nghiệp vụ |
| `orders.accepted` | Đơn hàng đã chuẩn hóa | `delete` hoặc `compact` tùy nhu cầu downstream |
| `orders.rejected` | Event không đạt validation kèm lý do | `delete` với retention đủ cho điều tra |
| `orders.audit` (tùy chọn) | Dấu vết nghiệp vụ của pipeline | `delete` hoặc `compact` theo contract |

Mỗi topic có partition riêng. Dùng `orderId` làm record key để các event cùng một đơn hàng đi vào cùng partition trong một topic, giữ thứ tự theo key trong phạm vi partition đó.

Nếu cần ordering giữa các topic, Kafka không cung cấp một thứ tự toàn cục giữa `orders.accepted` và `orders.rejected`. Consumer downstream phải dựa vào event ID, aggregate version hoặc business sequence để nhận biết thứ tự nghiệp vụ.

### 3.2. Event đầu vào

Ví dụ record JSON trên `orders.raw`:

~~~json
{
  "eventId": "evt-10001",
  "orderId": "order-9001",
  "customerId": "customer-42",
  "currency": "VND",
  "amount": 1250000,
  "items": [
    {"sku": "KB-01", "quantity": 1, "unitPrice": 900000},
    {"sku": "MS-02", "quantity": 1, "unitPrice": 350000}
  ],
  "occurredAt": "2026-11-20T09:30:00Z"
}
~~~

Pipeline kiểm tra tối thiểu:

- `eventId`, `orderId`, `customerId` không rỗng.
- `currency` nằm trong tập tiền tệ được hỗ trợ.
- `amount` lớn hơn 0 và không vượt giới hạn nghiệp vụ.
- `items` không rỗng; quantity và unit price hợp lệ.
- Tổng tiền dòng hàng khớp `amount` theo quy tắc rounding đã thống nhất.

Trong hệ thống thật, dùng `BigDecimal` cho tiền tệ, schema version và contract validation rõ ràng. Ví dụ trên dùng số nguyên để đơn giản hóa lab.

### 3.3. Event đầu ra

Event hợp lệ trên `orders.accepted` có thể được chuẩn hóa như sau:

~~~json
{
  "eventId": "evt-10001",
  "orderId": "order-9001",
  "customerId": "customer-42",
  "currency": "VND",
  "amount": 1250000,
  "status": "ACCEPTED",
  "processedAt": "2026-11-20T09:30:01Z",
  "pipelineVersion": "1"
}
~~~

Event không hợp lệ trên `orders.rejected` giữ lại thông tin có thể điều tra:

~~~json
{
  "eventId": "evt-10002",
  "orderId": "order-9002",
  "status": "REJECTED",
  "reasonCode": "INVALID_AMOUNT",
  "reason": "amount must be greater than zero",
  "originalPayload": "{...}",
  "pipelineVersion": "1"
}
~~~

Không đưa dữ liệu nhạy cảm không cần thiết vào rejected topic. Phân biệt `reasonCode` ổn định cho máy xử lý với `reason` dành cho người vận hành; tránh dùng exception message trực tiếp làm contract lâu dài.

## 4. Tạo topic cho lab

Trên cluster lab, tạo ba topic với partition count bằng nhau để dễ theo dõi key distribution:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders.raw --partitions 3 --replication-factor 1
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders.accepted --partitions 3 --replication-factor 1
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders.rejected --partitions 3 --replication-factor 1
~~~

Replication factor 1 chỉ phù hợp cho cluster local một broker. Với cluster nhiều broker, chọn RF theo durability target, ví dụ RF=3 và min.insync.replicas=2 khi có đủ broker/failure domain.

Xác minh topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.raw
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.accepted
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders.rejected
~~~

Giữ partition count của các topic output tương thích với chiến lược partitioning nếu cần cùng orderId tiếp tục map ổn định. Tăng partition count có thể thay đổi kết quả hash partitioning cho key mới; không xem việc cùng key luôn nằm cùng số partition sau khi thay partition count là bảo đảm bất biến.

## 5. Cấu hình consumer và producer

### 5.1. Consumer

Các property quan trọng:

~~~properties
bootstrap.servers=localhost:9092
group.id=orders-pipeline-v1
key.deserializer=org.apache.kafka.common.serialization.StringDeserializer
value.deserializer=org.apache.kafka.common.serialization.StringDeserializer
enable.auto.commit=false
auto.offset.reset=earliest
isolation.level=read_committed
max.poll.records=10
max.poll.interval.ms=300000
~~~

- enable.auto.commit=false: ứng dụng không tự commit offset độc lập với transaction.
- isolation.level=read_committed: chỉ đọc record thuộc transaction đã commit và không đọc record bị abort.
- group.id: định danh consumer group xử lý pipeline.
- max.poll.records: giới hạn số record trong một batch để kiểm soát thời gian xử lý.
- max.poll.interval.ms: phải đủ lớn cho thời gian xử lý batch và commit.

auto.offset.reset=earliest chỉ áp dụng khi group chưa có offset hợp lệ. Nó không phải cơ chế retry hay recovery cho mọi lỗi.

### 5.2. Transactional producer

~~~properties
bootstrap.servers=localhost:9092
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.StringSerializer
acks=all
enable.idempotence=true
transactional.id=orders-pipeline-instance-1
transaction.timeout.ms=60000
~~~

Gọi initTransactions() trước khi xử lý record. transactional.id phải ổn định cho một logical worker instance và duy nhất giữa các worker đang chạy đồng thời. Nếu hai producer đồng thời dùng cùng ID, producer mới có thể fence producer cũ. Đây là cơ chế bảo vệ khỏi hai instance cùng ghi một transaction identity.

Khi chạy nhiều replica, inject một instance ID riêng cho từng replica, chẳng hạn StatefulSet ordinal hoặc worker slot. Không hard-code cùng một transactional.id cho mọi pod. Khi dùng Spring Kafka, cấu hình transaction ID prefix duy nhất cho từng instance.

acks=all và idempotence hỗ trợ độ bền và loại bỏ duplicate do retry producer trong session; transaction mở rộng atomicity sang nhiều record và consumer offsets. Chúng không thay thế nhau.

## 6. Quy tắc xử lý lỗi

Không phải lỗi nào cũng nên retry vô hạn.

| Loại lỗi | Ví dụ | Cách xử lý trong pipeline |
|---|---|---|
| Lỗi nghiệp vụ không thể sửa bằng retry | Thiếu order ID, amount âm, currency không hỗ trợ | Ghi orders.rejected rồi commit input offset trong cùng transaction |
| Lỗi tạm thời khi xử lý | Dịch vụ enrich tạm mất kết nối, lỗi dependency có thể phục hồi | Abort transaction; không commit input offset; retry theo backoff có giới hạn |
| Lỗi gửi Kafka | Broker unavailable, timeout, not enough replicas | Abort nếu transaction còn trạng thái hợp lệ; retry/restart theo policy |
| Producer bị fence | Trùng transactional.id hoặc instance cũ bị thay thế | Dừng producer cũ; khởi tạo đúng instance identity |
| Lỗi schema/serialization | Payload không parse được hoặc schema không tương thích | Nếu xác định là dữ liệu xấu, ghi rejected theo policy; lỗi code/schema deployment cần dừng và cảnh báo |
| Lỗi cấu hình/authorization | ACL deny, TLS/SASL failure | Không retry vô hạn; sửa identity, certificate hoặc ACL |

Điểm quan trọng: record sai nghiệp vụ vẫn là một record đã được xử lý. Ghi nó vào orders.rejected rồi commit offset trong transaction giúp consumer không mắc kẹt mãi tại record đó. Ngược lại, khi Kafka hoặc dependency tạm lỗi, abort transaction để input offset chưa tiến và batch có thể được xử lý lại.

Nếu một batch chứa cả record hợp lệ và record lỗi nghiệp vụ, có thể gửi các record tương ứng sang accepted/rejected trong cùng transaction. Nếu có lỗi hạ tầng giữa batch, abort toàn bộ transaction; lần poll sau sẽ đọc lại các input record chưa commit.

## 7. Triển khai bằng Kafka Java client

### 7.1. Khởi tạo consumer và producer

Đoạn code minh họa transaction per poll batch. OrderTransformer là phần nghiệp vụ của bài lab; transformer trả về topic và JSON output, hoặc trả về kết quả rejected nếu validation thất bại.

~~~java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-pipeline-v1");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
consumerProps.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "10");

Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
producerProps.put(ProducerConfig.ACKS_CONFIG, "all");
producerProps.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
producerProps.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "orders-pipeline-instance-1");
producerProps.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, "60000");
~~~

~~~java
OrderTransformer transformer = new OrderTransformer(new ObjectMapper());
~~~

Khi khởi tạo client, gọi initTransactions một lần trước khi xử lý. Subscribe consumer vào orders.raw. Mỗi poll batch được xử lý trong một transaction độc lập.

### 7.2. Xử lý batch và commit offset cùng transaction

~~~java
try (KafkaConsumer<String, String> consumer =
             new KafkaConsumer<>(consumerProps);
     KafkaProducer<String, String> producer =
             new KafkaProducer<>(producerProps)) {

    producer.initTransactions();
    consumer.subscribe(List.of("orders.raw"));

    while (true) {
        ConsumerRecords<String, String> batch =
                consumer.poll(Duration.ofMillis(500));

        if (batch.isEmpty()) {
            continue;
        }

        try {
            producer.beginTransaction();

            Map<TopicPartition, OffsetAndMetadata> offsets =
                    new HashMap<>();

            for (TopicPartition partition : batch.partitions()) {
                List<ConsumerRecord<String, String>> partitionRecords =
                        batch.records(partition);

                for (ConsumerRecord<String, String> input : partitionRecords) {
                    OrderResult result = transformer.transform(input.value());

                    ProducerRecord<String, String> output =
                            new ProducerRecord<>(
                                    result.topic(),
                                    input.key(),
                                    result.payload());

                    input.headers().forEach(header ->
                            output.headers().add(header));

                    producer.send(output).get(2, TimeUnit.SECONDS);
                }

                ConsumerRecord<String, String> last =
                        partitionRecords.get(partitionRecords.size() - 1);

                offsets.put(partition,
                        new OffsetAndMetadata(last.offset() + 1));
            }

            producer.sendOffsetsToTransaction(
                    offsets,
                    consumer.groupMetadata());

            producer.commitTransaction();

        } catch (ProducerFencedException fenced) {
            // Instance này đã bị producer khác thay thế.
            // Dừng worker; không tiếp tục dùng producer bị fence.
            throw fenced;

        } catch (Exception processingFailure) {
            try {
                producer.abortTransaction();
            } catch (Exception abortFailure) {
                processingFailure.addSuppressed(abortFailure);
                throw new IllegalStateException(
                        "Không xác nhận được trạng thái abort; cần restart worker",
                        processingFailure);
            }

            if (processingFailure instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }

            throw new IllegalStateException(
                    "Batch đã abort; cần retry hoặc restart theo policy",
                    processingFailure);
        }
    }
}
~~~

Các import cần dùng gồm org.apache.kafka.clients.consumer.*, org.apache.kafka.clients.producer.*, org.apache.kafka.common.TopicPartition, org.apache.kafka.common.errors.ProducerFencedException, java.time.Duration, java.time.Instant, java.util.*, java.util.concurrent.TimeUnit, com.fasterxml.jackson.core.JsonProcessingException và com.fasterxml.jackson.databind.ObjectMapper. Thêm Jackson Databind vào project.

OrderResult là kiểu dữ liệu của ứng dụng, có thể định nghĩa bằng record trên Java 16 trở lên:

~~~java
public record OrderResult(String topic, String payload) {}
~~~

Với Java cũ hơn, dùng một class immutable có hai field topic và payload cùng getter tương ứng.

Hàm transformOrder phải luôn trả về một trong hai topic đã quy định:

- orders.accepted nếu event hợp lệ và đã chuẩn hóa.
- orders.rejected nếu event không đạt business validation.

Không để exception parse/validation không được phân loại trôi ra ngoài nếu policy muốn đưa payload lỗi vào rejected topic. Ngược lại, lỗi dependency tạm thời phải được ném ra để transaction abort, không biến mọi lỗi thành rejected.

### 7.3. Cài đặt transform và validation

Ví dụ DTO dùng Java record (Java 16 trở lên):

~~~java
public record OrderInput(
        String eventId,
        String orderId,
        String customerId,
        String currency,
        long amount,
        List<OrderItem> items,
        Instant occurredAt) {}

public record OrderItem(String sku, int quantity, long unitPrice) {}

public record OrderOutput(
        String eventId,
        String orderId,
        String customerId,
        String currency,
        long amount,
        String status,
        Instant processedAt,
        String pipelineVersion) {}

public record RejectedOrder(
        String eventId,
        String orderId,
        String status,
        String reasonCode,
        String reason,
        String originalPayload,
        String pipelineVersion) {}
~~~

Transformer mẫu:

~~~java
public final class OrderTransformer {

    private final ObjectMapper mapper;

    public OrderTransformer(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public OrderResult transform(String payload) {
        if (payload == null || payload.isBlank()) {
            return rejected(null, null, "EMPTY_PAYLOAD",
                    "Payload rỗng", payload);
        }

        final OrderInput input;

        try {
            input = mapper.readValue(payload, OrderInput.class);
        } catch (JsonProcessingException malformedJson) {
            return rejected(null, null, "MALFORMED_JSON",
                    "Payload không phải JSON hợp lệ", payload);
        }

        if (input == null) {
            return rejected(null, null, "EMPTY_EVENT",
                    "Payload JSON không chứa order object", payload);
        }

        String reasonCode = validate(input);
        if (reasonCode != null) {
            return rejected(input.eventId(), input.orderId(),
                    reasonCode, "Order không đạt business validation", payload);
        }

        OrderOutput output = new OrderOutput(
                input.eventId(),
                input.orderId(),
                input.customerId(),
                input.currency(),
                input.amount(),
                "ACCEPTED",
                Instant.now(),
                "1");

        try {
            return new OrderResult(
                    "orders.accepted",
                    mapper.writeValueAsString(output));
        } catch (JsonProcessingException serializationFailure) {
            throw new IllegalStateException(
                    "Không serialize được accepted event", serializationFailure);
        }
    }

    private String validate(OrderInput input) {
        if (input.eventId() == null || input.eventId().isBlank()) {
            return "MISSING_EVENT_ID";
        }
        if (input.orderId() == null || input.orderId().isBlank()) {
            return "MISSING_ORDER_ID";
        }
        if (input.customerId() == null || input.customerId().isBlank()) {
            return "MISSING_CUSTOMER_ID";
        }
        if (input.currency() == null
                || !Set.of("VND", "USD").contains(input.currency())) {
            return "UNSUPPORTED_CURRENCY";
        }
        if (input.amount() <= 0) {
            return "INVALID_AMOUNT";
        }
        if (input.items() == null || input.items().isEmpty()) {
            return "EMPTY_ITEMS";
        }

        try {
            long total = 0;
            for (OrderItem item : input.items()) {
                if (item == null || item.sku() == null || item.sku().isBlank()
                        || item.quantity() <= 0 || item.unitPrice() < 0) {
                    return "INVALID_ITEM";
                }
                total = Math.addExact(total,
                        Math.multiplyExact((long) item.quantity(), item.unitPrice()));
            }
            if (total != input.amount()) {
                return "AMOUNT_MISMATCH";
            }
        } catch (ArithmeticException overflow) {
            return "AMOUNT_OVERFLOW";
        }

        return null;
    }

    private OrderResult rejected(
            String eventId,
            String orderId,
            String reasonCode,
            String reason,
            String originalPayload) {

        RejectedOrder rejected = new RejectedOrder(
                eventId,
                orderId,
                "REJECTED",
                reasonCode,
                reason,
                originalPayload,
                "1");

        try {
            return new OrderResult(
                    "orders.rejected",
                    mapper.writeValueAsString(rejected));
        } catch (JsonProcessingException serializationFailure) {
            throw new IllegalStateException(
                    "Không serialize được rejected event", serializationFailure);
        }
    }
}
~~~

Code này chỉ minh họa validation cho lab. Trong production, cần giới hạn kích thước payload lưu ở rejected topic, redact dữ liệu nhạy cảm, xác định chính sách tiền tệ/rounding và quản lý schema version. Lỗi parse JSON được phân loại là dữ liệu không hợp lệ; lỗi serialize output hoặc lỗi dependency vẫn được ném ra để transaction rollback.

Nếu dùng Java 11 hoặc thấp hơn, thay record bằng POJO immutable và getter. Thêm Jackson Databind cùng các import DTO/Java time cần thiết vào project.

### 7.4. Vì sao phải gửi offset vào transaction?

Giả sử batch đọc từ partition 0 các offset 10, 11 và 12. Offset kế tiếp cần commit là 13. Nếu batch đọc từ nhiều partition, cần một offset tiếp theo cho mỗi partition:

~~~text
orders.raw-0: đọc 10, 11, 12 -> commit offset 13
orders.raw-1: đọc 20, 21     -> commit offset 22
orders.raw-2: đọc 7          -> commit offset 8
~~~

Kafka lưu consumer group offsets theo partition. sendOffsetsToTransaction đưa các offset này vào transaction cùng output records. consumer.groupMetadata() cung cấp generation/member metadata để broker xác minh consumer group vẫn ở generation hợp lệ. Nếu partition đã bị revoke và metadata cũ không còn hợp lệ, transaction không thể tùy tiện commit offset của owner cũ.

Không dùng offset cuối cùng vừa đọc mà quên cộng 1: offset commit là vị trí record tiếp theo cần đọc, không phải offset của record cuối cùng đã xử lý.

### 7.5. Transaction boundary và giới hạn

Một transaction có thể chứa nhiều output record và offset của nhiều input partition. Chỉ commit sau khi toàn bộ record trong batch đã được biến đổi và gửi thành công.

Nếu một send thất bại:

- Không commit offsets của batch.
- Abort transaction nếu producer còn ở trạng thái có thể abort.
- Không tự ghi output lần nữa bên ngoài transaction.
- Retry batch sau backoff hoặc để supervisor khởi động lại worker.

Nếu producer bị fence, producer đã mất quyền sở hữu transactional ID. Không tiếp tục vòng lặp bằng instance đó. Khởi động một producer mới với identity đúng sau khi xác nhận instance cũ đã dừng.

Với lỗi commit timeout hoặc lỗi coordinator, trạng thái transaction có thể cần được xác định lại theo protocol. Không tự commit offset thủ công để sửa trạng thái không rõ ràng; đóng/recreate producer theo hướng dẫn client và quan sát transaction coordinator trước khi tiếp tục.

Exactly-once của Kafka áp dụng cho output records và consumer offsets nằm trong transaction Kafka. Nếu transform gọi database, REST API, gửi email hoặc ghi filesystem thì side effect đó không tự rollback cùng Kafka transaction. Dùng outbox/inbox, idempotency key hoặc transaction boundary của hệ thống ngoài để xử lý phần này.

## 8. Triển khai bằng Spring Kafka

Spring Kafka có thể để listener container quản lý transaction. Khi listener xử lý thành công, container gửi offsets của record/batch vào Kafka transaction rồi commit. KafkaTemplate dùng cùng ProducerFactory sẽ tham gia transaction hiện tại.

### 8.1. Cấu hình producer factory và transaction manager

Ví dụ cấu hình Java:

~~~java
@Bean
DefaultKafkaProducerFactory<String, String> ordersProducerFactory(
        KafkaProperties kafkaProperties,
        Environment environment) {

    Map<String, Object> props =
            kafkaProperties.buildProducerProperties();

    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(props);

    String instanceId = environment.getRequiredProperty("app.instance-id");
    factory.setTransactionIdPrefix("orders-pipeline-" + instanceId + "-");
    return factory;
}

@Bean
KafkaTemplate<String, String> ordersKafkaTemplate(
        ProducerFactory<String, String> ordersProducerFactory) {
    return new KafkaTemplate<>(ordersProducerFactory);
}

@Bean
KafkaTransactionManager<String, String> ordersKafkaTransactionManager(
        ProducerFactory<String, String> ordersProducerFactory) {
    return new KafkaTransactionManager<>(ordersProducerFactory);
}
~~~

app.instance-id phải khác nhau giữa các instance chạy đồng thời. Prefix được Spring Kafka kết hợp với suffix để tạo transactional ID cho producer. Tất cả KafkaTemplate dùng trong listener phải lấy producer từ cùng ProducerFactory đang được transaction manager quản lý.

Ví dụ cấu hình app.instance-id là worker-1 trên replica thứ nhất và worker-2 trên replica thứ hai. Không cấp cùng một giá trị cho hai instance hoạt động đồng thời.

### 8.2. Cấu hình listener container

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
ordersTransactionalListenerFactory(
        ConsumerFactory<String, String> consumerFactory,
        KafkaTransactionManager<String, String> ordersKafkaTransactionManager) {

    ConcurrentKafkaListenerContainerFactory<String, String> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(ordersKafkaTransactionManager);

    return factory;
}
~~~

Consumer factory cần cấu hình tối thiểu:

~~~properties
enable.auto.commit=false
isolation.level=read_committed
group.id=orders-pipeline-v1
~~~

Với transactional listener, container bắt đầu transaction trước khi gọi listener. Nếu listener hoàn tất bình thường, offset được gửi vào transaction và transaction commit. Nếu listener ném exception, transaction rollback và input offset không được commit bởi transaction đó.

API cấu hình có thể khác giữa các phiên bản Spring Kafka. Đối chiếu đúng phiên bản dependency đang dùng; ví dụ trên dùng API listener container có KafkaAwareTransactionManager.

### 8.3. Listener đọc, biến đổi và ghi

~~~java
@Component
class OrderPipelineListener {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final OrderTransformer transformer;

    OrderPipelineListener(
            KafkaTemplate<String, String> kafkaTemplate,
            OrderTransformer transformer) {
        this.kafkaTemplate = kafkaTemplate;
        this.transformer = transformer;
    }

    @KafkaListener(
            topics = "orders.raw",
            groupId = "orders-pipeline-v1",
            containerFactory = "ordersTransactionalListenerFactory")
    public void process(ConsumerRecord<String, String> input)
            throws Exception {

        OrderResult result = transformer.transform(input.value());

        kafkaTemplate.send(
                result.topic(),
                input.key(),
                result.payload()).get(10, TimeUnit.SECONDS);
    }
}
~~~

Trong ví dụ này, send được chờ hoàn tất để lỗi publish được truyền về listener. Nếu transformer trả về rejected result, listener vẫn gửi record vào orders.rejected và return bình thường; container commit rejected record cùng input offset.

Nếu dependency tạm thời lỗi, transformer ném exception. Container rollback transaction; record đầu vào sẽ được giao lại theo cơ chế rollback/recovery đã cấu hình. Không bắt rồi nuốt exception nếu muốn transaction rollback.

### 8.4. Retry và dead-letter trong Spring Kafka

Cấu hình retry cần phân biệt lỗi transient và lỗi không thể phục hồi:

- Lỗi tạm thời: rollback transaction và retry với backoff hữu hạn.
- Lỗi dữ liệu nghiệp vụ: gửi orders.rejected trong transaction của listener rồi return.
- Lỗi code/schema hoặc authorization: dừng hoặc cảnh báo theo policy; tránh retry vô hạn.
- Sau số lần retry tối đa: dùng recovery/DLT policy được thiết kế rõ ràng.

Nếu dùng DefaultAfterRollbackProcessor để recover record sang DLT, cần quyết định DLT send có nằm trong transaction mới hay không, cách commit recovered offset và cách tránh mất record. Cấu hình các tùy chọn transaction/recovery theo đúng phiên bản Spring Kafka. Không mặc định rằng mọi DeadLetterPublishingRecoverer đều tự động có semantics giống transaction của listener.

Không kết hợp một listener transactional với lệnh commit offset thủ công. Để container quản lý offset của listener.

## 9. Chạy lab từ đầu đến cuối

### 9.1. Chuẩn bị môi trường

Cần có:

- Kafka cluster lab đang chạy và có thể truy cập qua localhost:9092.
- Ba topic orders.raw, orders.accepted và orders.rejected.
- Java project có Kafka clients hoặc Spring Kafka tương thích với broker.
- Kafka Java client, Jackson Databind; nếu triển khai Spring thì thêm Spring Kafka (dùng phiên bản do Spring Boot BOM quản lý).
- Jackson Databind nếu dùng transformer JSON ở trên.
- Một instance ID duy nhất cho mỗi worker đang chạy.

Nếu dùng cluster bảo mật, thay bootstrap server và bổ sung security properties cho producer/consumer. Không dùng superuser cho principal ứng dụng; cấp quyền đọc orders.raw, ghi orders.accepted/orders.rejected và quyền transactional ID cần thiết.

### 9.2. Produce event hợp lệ

Chạy console producer có key separator là dấu hai chấm:

~~~bash
kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders.raw --property parse.key=true --property key.separator=:
~~~

Nhập một dòng:

~~~text
order-9001:{"eventId":"evt-10001","orderId":"order-9001","customerId":"customer-42","currency":"VND","amount":1250000,"items":[{"sku":"KB-01","quantity":1,"unitPrice":900000},{"sku":"MS-02","quantity":1,"unitPrice":350000}],"occurredAt":"2026-11-20T09:30:00Z"}
~~~

Key order-9001 giúp partitioner phân phối các event của cùng order vào cùng partition. Producer của ứng dụng cần giữ contract này; nếu key rỗng hoặc khác orderId, ordering theo aggregate có thể không còn đúng.

### 9.3. Produce event không hợp lệ

Gửi event có amount bằng 0 hoặc tổng item không khớp amount:

~~~text
order-9002:{"eventId":"evt-10002","orderId":"order-9002","customerId":"customer-42","currency":"VND","amount":0,"items":[{"sku":"KB-01","quantity":1,"unitPrice":900000}],"occurredAt":"2026-11-20T09:31:00Z"}
~~~

Transformer phải tạo rejected event với reasonCode phù hợp. Input offset chỉ được commit khi rejected output được commit trong transaction.

### 9.4. Khởi động pipeline và đọc kết quả

Khởi động worker native Java hoặc Spring Kafka. Dùng consumer group orders-pipeline-v1 và một transactional ID/prefix duy nhất cho instance.

Đọc accepted topic:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders.accepted --from-beginning --property print.key=true --consumer-property isolation.level=read_committed
~~~

Đọc rejected topic:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders.rejected --from-beginning --property print.key=true --consumer-property isolation.level=read_committed
~~~

Kiểm tra key, eventId, status, pipelineVersion và reasonCode. Không yêu cầu accepted topic phải có record cho order bị reject; mỗi input event phải tạo đúng một kết quả theo contract.

### 9.5. Kiểm tra consumer group offsets

Dùng lệnh sau để xem trạng thái group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-pipeline-v1
~~~

Đối chiếu CURRENT-OFFSET, LOG-END-OFFSET và LAG của từng partition. Offset chỉ tiến sau khi transaction chứa output tương ứng được commit. Lag có thể còn tồn tại trong lúc transaction đang mở hoặc consumer đang xử lý batch.

### 9.6. Mô phỏng crash trước commit

Trong môi trường lab, thêm một test hook sau khi producer gửi hết output nhưng trước sendOffsetsToTransaction/commitTransaction. Ghi log marker để biết worker đã tới điểm này, sau đó dừng process đột ngột.

Kết quả mong đợi:

1. Transaction chưa commit nên output chưa hiển thị với consumer read_committed.
2. Consumer group offset chưa được commit bởi transaction đó.
3. Khởi động lại worker với cùng transactional.id của logical instance.
4. initTransactions hoàn tất việc xử lý transaction cũ còn dang dở theo protocol.
5. Worker đọc lại input record và xử lý trong transaction mới.
6. Sau commit thành công, downstream read_committed thấy một kết quả cho input event.

Không dùng cùng transactional.id cho hai process đang chạy đồng thời. Nếu khởi động instance mới trong khi instance cũ chưa chết, producer mới sẽ fence instance cũ; đó là hành vi mong đợi nhưng cần được quan sát trong lab.

### 9.7. Mô phỏng lỗi dependency

Tạm thời làm transformer ném exception cho một event được chọn, trước khi gửi output. Xác minh transaction rollback và input offset không tiến. Khôi phục dependency rồi restart/retry worker; event phải được xử lý lại.

Không biến lỗi dependency thành rejected event. Rejected topic dành cho dữ liệu không hợp lệ theo business contract, không phải nơi chứa mọi lỗi vận hành.

## 10. Ma trận kiểm thử và tiêu chí đạt

Chạy từng case trên cluster lab riêng, lưu output topic, consumer group offset và log của worker.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| TX-01 | Event hợp lệ | Có đúng một accepted event; input offset tiến |
| TX-02 | Event sai business validation | Có đúng một rejected event; input offset tiến |
| TX-03 | JSON malformed | Có rejected event với reasonCode MALFORMED_JSON; input offset tiến |
| TX-04 | Exception transient trước khi send | Transaction rollback; input offset không tiến |
| TX-05 | Send output thất bại | Không có output committed; input offset không tiến |
| TX-06 | Crash sau send nhưng trước commit | read_committed không thấy output của transaction dang dở; offset chưa commit |
| TX-07 | Restart cùng transactional.id sau crash | Input được xử lý lại; chỉ một kết quả committed được quan sát |
| TX-08 | Producer mới dùng cùng transactional.id khi producer cũ còn sống | Producer cũ bị fenced và không thể tiếp tục ghi |
| TX-09 | Rebalance khi batch đang xử lý | Group metadata cũ không được phép commit offset cho generation mới; worker xử lý rollback/recovery |
| TX-10 | Downstream dùng read_committed | Chỉ đọc output của transaction đã commit |
| TX-11 | Downstream dùng read_uncommitted trong lab | Có thể quan sát record chưa commit hoặc record thuộc transaction bị abort; dùng để minh họa khác biệt isolation |
| TX-12 | Crash sau commit thành công | Input offset đã tiến; restart không xử lý lại batch đã commit |

Tiêu chí đạt:

- Mỗi input record được phân loại thành accepted hoặc rejected theo business contract.
- Output và input offset không bị tách rời khi transaction commit/abort.
- Không có consumer downstream read_committed nhìn thấy output của transaction bị abort.
- Rebalance và producer fencing không tạo ra commit offset từ consumer owner cũ.
- Worker restart không tạo duplicate committed output cho cùng một input trong phạm vi pipeline Kafka.
- Log đủ để truy vết transaction, partition, offset và eventId nhưng không lộ payload nhạy cảm.

Để xác minh đúng, dùng consumer test có group riêng và isolation.level=read_committed. Tránh đọc output bằng một công cụ mặc định read_uncommitted rồi kết luận rằng record aborted đã được publish thành công.

## 11. Tuning và vận hành pipeline

### 11.1. Batch size và thời gian xử lý

Một transaction cho mỗi poll batch giúp giảm overhead so với transaction cho từng record, nhưng batch quá lớn làm tăng thời gian mở transaction và lượng dữ liệu phải retry khi abort.

Điều chỉnh đồng thời:

- max.poll.records: số record tối đa trong một lần poll.
- max.poll.interval.ms: thời gian tối đa giữa các lần poll tiếp theo.
- transaction.timeout.ms: thời gian broker cho phép transaction hoàn tất.
- max.block.ms và request.timeout.ms: giới hạn chờ metadata/buffer/request theo client.
- Số partition và concurrency: quyết định mức song song của consumer group.

Thời gian xử lý batch cộng thời gian send/commit phải thấp hơn max.poll.interval.ms với headroom đủ lớn. transaction.timeout.ms phải đủ cho batch nhưng không vượt transaction.max.timeout.ms của broker. Nếu xử lý ngoài Kafka quá lâu, tách bước đó ra hoặc dùng asynchronous workflow có idempotency thay vì giữ transaction mở lâu.

### 11.2. Throughput và transaction size

- Tăng partition khi cần tăng parallelism, sau khi đánh giá lại key distribution và ordering.
- Chọn max.poll.records dựa trên payload size, thời gian transform và transaction latency.
- Dùng producer batching/compression phù hợp để giảm network overhead.
- Theo dõi buffer exhaustion, request latency và broker throttling.
- Không gom transaction quá lớn; transaction lớn làm tăng memory, coordinator work và thời gian recovery.
- Giới hạn số output record cho mỗi input event và kích thước rejected payload.

### 11.3. Consumer visibility và Last Stable Offset

Consumer read_committed chỉ đọc tới Last Stable Offset (LSO), tức ranh giới dữ liệu ổn định trước các transaction đang mở. Một transaction kéo dài có thể làm record phía sau chưa hiển thị với read_committed consumer dù record đã được append.

Vì vậy cần theo dõi transaction duration và timeout, không để worker giữ transaction mở khi chờ dependency chậm. Đây là một nguyên nhân làm downstream lag dù broker vẫn nhận produce traffic.

### 11.4. Metrics và log nên theo dõi

| Nhóm | Tín hiệu |
|---|---|
| Consumer | Lag theo partition, poll interval, rebalance count, records consumed |
| Producer | Send latency, record errors, buffer wait, request retries |
| Transaction | Commit latency, abort count, transaction timeout, fencing errors |
| Broker | Under-replicated partitions, request queue, disk/network throughput |
| Pipeline | Accepted/rejected rate, validation reasonCode, processing duration |
| Reliability | Restart count, retry count, batch replay count, DLQ/rejected growth |

Tên JMX metric phụ thuộc Kafka/client version và hệ thống export. Chọn metric có thật trong release đang chạy, rồi đặt alert theo SLO của pipeline.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Producer khởi động nhưng transaction lỗi | Chưa gọi initTransactions hoặc transactional ID không hợp lệ | Gọi initTransactions một lần trước khi xử lý; kiểm tra broker transaction config |
| ProducerFencedException | Hai instance dùng cùng transactional.id | Đảm bảo ID duy nhất giữa instance đang chạy; dừng instance cũ |
| Transaction timeout | Batch lớn hoặc dependency chậm | Giảm batch, tối ưu transform, điều chỉnh timeout trong giới hạn broker |
| Consumer lag tăng khi transaction mở | LSO bị giữ bởi transaction dài | Giảm thời gian transaction; tìm worker bị treo |
| Output có nhưng input offset không tiến | Output được ghi ngoài transaction hoặc offset commit độc lập | Đưa cả output và offsets vào cùng transaction |
| Input offset tiến nhưng output thiếu | Offset commit riêng trước output | Bỏ manual commit; dùng sendOffsetsToTransaction hoặc transactional container |
| Transaction bị abort liên tục | ACL, producer fencing, rebalance hoặc lỗi send | Đọc root cause; kiểm tra group generation và quyền transactional ID |
| Consumer đọc record chưa commit | isolation.level đang là read_uncommitted | Đặt read_committed cho consumer cần chỉ thấy committed data |
| Consumer downstream không thấy output ngay | Transaction chưa commit hoặc LSO bị chặn | Kiểm tra transaction coordinator, commit latency và open transaction |
| Duplicate ở database/API | Side effect ngoài Kafka transaction | Dùng idempotency key, inbox/outbox hoặc transaction riêng của hệ thống ngoài |

## 13. Giới hạn và nguyên tắc thiết kế

1. Input topic, output topic và consumer group offsets phải thuộc cùng Kafka cluster để Kafka transaction atomically commit output và offsets. Kafka transaction không trải qua hai cluster độc lập.
2. Exactly-once ở đây là read-process-write trong Kafka. Database, REST API, email và filesystem không tự tham gia transaction Kafka.
   Idempotent producer chống retry trùng ở protocol producer; nó không tự loại hai input record khác offset nhưng mang cùng eventId. Nếu business cần deduplication, xác định eventId ổn định và thiết kế inbox/idempotency ở consumer hoặc hệ thống đích.
3. Ordering chỉ được bảo đảm trong một partition. Dùng cùng key và partitioning contract; không giả định thứ tự toàn cục giữa nhiều partition hoặc nhiều output topic.
4. Consumer downstream cần read_committed nếu không muốn nhìn thấy record từ transaction chưa commit/đã abort.
5. transactional.id phải duy nhất giữa producer instance đồng thời; producer fencing là cơ chế bảo vệ ownership.
6. Transaction timeout, max poll interval và thời gian xử lý phải được thiết kế cùng nhau.
7. Rejected topic không phải nơi đẩy mọi lỗi. Chỉ dùng cho record không đạt contract; lỗi hạ tầng cần retry/rollback và lỗi cấu hình cần alert.

## 14. Checklist hoàn tất

- [ ] Tạo được orders.raw, orders.accepted và orders.rejected.
- [ ] Producer đầu vào dùng orderId làm key.
- [ ] Consumer tắt auto commit và dùng read_committed.
- [ ] Producer bật idempotence, acks=all và transactional.id riêng.
- [ ] Gọi initTransactions trước khi xử lý batch.
- [ ] Mỗi batch có beginTransaction và commit/abort rõ ràng.
- [ ] Output accepted/rejected được gửi trong transaction.
- [ ] Offset tiếp theo của từng partition được tính đúng bằng last offset + 1.
- [ ] Gọi sendOffsetsToTransaction với consumer.groupMetadata().
- [ ] Không gọi commitSync/commitAsync cho cùng input offsets.
- [ ] Spring Kafka listener container và KafkaTemplate dùng cùng ProducerFactory.
- [ ] Lỗi business được ghi rejected; lỗi transient làm rollback.
- [ ] Crash trước commit và restart được kiểm thử.
- [ ] Producer fencing và rebalance được kiểm thử.
- [ ] Downstream read_committed chỉ thấy transaction đã commit.
- [ ] Metrics, log, retry và rejected rate được theo dõi.
- [ ] Side effect ngoài Kafka có idempotency/outbox/inbox phù hợp.
Pipeline đọc, biến đổi và ghi bằng giao dịch giúp gắn output records với input offsets trong một commit Kafka nguyên tử. Khi xử lý thành công, consumer group tiến lên cùng lúc với output; khi transaction abort, output không hiển thị với read_committed và input có thể được xử lý lại. Để đạt semantics này, cần tắt auto commit, dùng transactional producer có ID riêng, gửi offsets qua sendOffsetsToTransaction hoặc để Spring Kafka transactional listener container quản lý, và kiểm thử crash/rebalance/fencing.
