# Idempotent producer và transactional producer khác nhau thế nào

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này phân biệt hai cơ chế bảo đảm ở phía producer: **idempotent producer** và **transactional producer**.

Idempotent producer giúp Kafka nhận diện request gửi lại do retry để tránh ghi trùng record trong phạm vi một producer identity và partition. Transactional producer dùng transaction coordinator để nhóm nhiều thao tác Kafka thành một đơn vị commit hoặc abort, có thể bao gồm output records trên nhiều partition và consumer offsets. Transactional producer có sử dụng cơ chế idempotence, nhưng idempotence đơn thuần không tạo ra transaction nhiều partition.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích duplicate có thể xuất hiện khi producer retry sau timeout.
- Mô tả cách Producer ID, producer epoch và sequence number hỗ trợ idempotence.
- Xác định phạm vi bảo đảm và giới hạn của idempotent producer.
- Giải thích transactional.id, transaction coordinator và transaction marker.
- Phân biệt retry idempotent với commit/abort transaction.
- So sánh phạm vi nguyên tử của idempotent producer và transactional producer.
- Viết Java producer bật idempotence và Java transactional producer.
- Kết hợp output records với consumer offsets bằng sendOffsetsToTransaction().
- Cấu hình và sử dụng transaction với Spring Kafka.
- Nhận diện vì sao Kafka transaction không tự mở rộng sang database hoặc HTTP API bên ngoài.

## 2. Vì sao cần hai cơ chế khác nhau?

Giả sử một ứng dụng phát event OrderCreated đến topic orders. Producer gửi record, broker ghi thành công nhưng response bị mất trên đường về. Producer thấy timeout và không biết broker đã ghi hay chưa.

Nếu producer gửi lại record như một request mới, broker có thể ghi thêm một bản sao. Idempotent producer giải quyết trường hợp retry giao thức này bằng cách nhận diện request dựa trên producer identity và sequence number.

Một bài toán khác phức tạp hơn: ứng dụng đọc event từ topic orders, xử lý rồi ghi event sang topic shipments. Đồng thời, ứng dụng phải commit offset đầu vào. Nếu output đã ghi nhưng offset đầu vào chưa commit, khi ứng dụng restart, event đầu vào có thể được đọc lại và tạo output trùng. Nếu offset được commit trước khi output thành công, ứng dụng có thể bỏ mất output.

Transactional producer giải quyết bài toán này bằng cách đưa output records và consumer offsets vào cùng một Kafka transaction. Kafka quyết định commit hoặc abort toàn bộ nhóm thao tác đó.

Hai cơ chế xử lý hai phạm vi khác nhau:

- Idempotence: một request gửi lại do retry không tạo thêm bản ghi trùng trong phạm vi Kafka producer protocol.
- Transaction: nhiều thao tác Kafka được commit hoặc abort như một đơn vị.

## 3. Duplicate xảy ra khi producer retry như thế nào?

Giả sử producer gửi record R đến partition orders-0:

~~~text
1. Producer gửi request chứa R.
2. Leader append R tại offset 100.
3. Broker gửi response thành công.
4. Response bị mất do network.
5. Producer không nhận được response và timeout.
6. Producer gửi lại request.
~~~

Nếu broker không nhận diện request gửi lại, R có thể được append lần nữa tại offset 101. Consumer sẽ nhìn thấy hai record dù ứng dụng chỉ định gửi một lần.

Đây là tình huống **ambiguous outcome**: producer không biết request trước đã được broker ghi hay chưa. Retry là cần thiết để phục hồi khi lỗi tạm thời, nhưng retry không có cơ chế nhận diện có thể tạo duplicate.

Cần phân biệt hai kiểu lặp:

- **Protocol retry duplicate:** cùng một request được gửi lại vì timeout hoặc lỗi mạng. Idempotent producer được thiết kế để xử lý tình huống này.
- **Application duplicate:** ứng dụng gọi send() hai lần cho cùng một sự kiện nghiệp vụ, hoặc chạy lại công việc sau restart bằng một producer identity mới. Idempotent producer không tự suy luận rằng hai lần send đó đại diện cho cùng một nghiệp vụ.

Nếu nghiệp vụ có event ID như order-event-123, consumer hoặc hệ thống đích vẫn có thể cần deduplication theo event ID.

## 4. Idempotent producer là gì?

**Idempotent producer** là Kafka producer sử dụng định danh producer và sequence number để broker phát hiện request retry đã được ghi trước đó. Khi cùng một batch được gửi lại theo đúng protocol, broker không append thêm một bản sao của batch đó.

Idempotence tập trung vào việc bảo vệ thao tác ghi của một producer lên các partition. Nó không nhóm nhiều partition thành một transaction nguyên tử.

### 4.1. Các thành phần chính

| Thành phần | Vai trò |
|---|---|
| Producer ID (PID) | Định danh producer ở cấp giao thức Kafka. |
| Producer epoch | Thế hệ của producer, giúp phân biệt phiên producer hiện tại và phiên cũ. |
| Sequence number | Số thứ tự batch record của producer trên từng partition. |
| Partition leader | Theo dõi trạng thái producer và sequence để nhận diện batch hợp lệ hoặc batch retry. |

Sequence number được theo dõi theo producer identity và partition. Broker dùng nó để phát hiện batch mới, batch gửi lại và các trường hợp sequence không hợp lệ.

### 4.2. Luồng retry với idempotent producer

~~~mermaid
sequenceDiagram
    participant P as Idempotent Producer
    participant L as Partition Leader

    P->>L: Produce batch (PID, epoch, sequence=10)
    L->>L: Append batch tại offset 100
    L--xP: Response bị mất
    P->>L: Retry cùng batch, sequence=10
    L->>L: Nhận diện batch đã append
    L-->>P: Trả kết quả mà không append duplicate
~~~

Broker nhận ra request retry dựa trên metadata producer và sequence. Request retry không được ghi thêm một lần nữa.

### 4.3. Idempotence bảo đảm điều gì?

Khi được cấu hình và sử dụng đúng:

- Retry của producer không tạo duplicate do cùng batch được gửi lại.
- Thứ tự ghi trong partition được bảo vệ khi request retry.
- Producer có thể phục hồi một số lỗi tạm thời mà không tạo thêm bản ghi do retry.
- Ứng dụng có thể kết hợp idempotence với acks=all để tăng độ tin cậy khi ghi.

### 4.4. Idempotence không bảo đảm điều gì?

Idempotent producer không tự bảo đảm:

- Hai lần gọi send() riêng biệt cho cùng một event nghiệp vụ chỉ tạo một record.
- Duplicate do ứng dụng chủ động gửi lại sau restart luôn được loại bỏ.
- Ghi nhiều topic/partition có tính nguyên tử.
- Consumer xử lý record đúng một lần.
- Database và Kafka cùng commit hoặc rollback.
- HTTP API bên ngoài chỉ được gọi một lần.

Phạm vi bảo đảm của idempotence gắn với producer protocol và producer identity mà Kafka quản lý. Nếu ứng dụng tạo một producer identity mới rồi gửi lại cùng dữ liệu, broker không có cơ sở để mặc định coi đó là retry của phiên trước.

## 5. Cấu hình idempotent producer trong Java

Ví dụ producer gửi event vào topic orders:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;
import java.util.concurrent.ExecutionException;

public class IdempotentOrderProducer {

    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
        properties.put(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
            5
        );

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {

            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "ORD-1001",
                    "OrderCreated"
                );

            producer.send(record).get();
            System.out.println("Record acknowledged by Kafka");
        } catch (ExecutionException exception) {
            throw new RuntimeException(
                "Could not publish order event",
                exception.getCause()
            );
        }
    }
}
~~~

Các cấu hình quan trọng:

- enable.idempotence=true bật cơ chế idempotent producer.
- acks=all yêu cầu xác nhận theo ISR.
- retries cho phép thử lại request khi lỗi được phân loại là có thể retry.
- max.in.flight.requests.per.connection phải nằm trong giới hạn tương thích với idempotence; Kafka client hiện đại hỗ trợ tối đa 5.

Trong các phiên bản Kafka client hiện đại, idempotence có thể được bật mặc định khi các cấu hình tương thích. Tuy nhiên, nên khai báo rõ khi đây là yêu cầu durability của ứng dụng và xác minh effective configuration theo đúng phiên bản client đang chạy.

## 6. Transactional producer là gì?

**Transactional producer** là producer có thể gom nhiều thao tác ghi Kafka thành một transaction. Kafka transaction coordinator theo dõi vòng đời transaction và quyết định commit hoặc abort.

Transactional producer sử dụng idempotence để bảo vệ việc ghi trong transaction, đồng thời bổ sung:

- transactional.id ổn định cho logical producer.
- Transaction coordinator.
- Transaction state log.
- Danh sách partition tham gia.
- Transaction marker commit/abort.
- Cơ chế read_committed để consumer chỉ nhận dữ liệu đã commit.

Transaction có thể bao gồm record trên nhiều topic và partition. Consumer cấu hình read_committed sẽ không nhận record thuộc transaction đã abort hoặc transaction chưa hoàn tất vượt qua Last Stable Offset.

### 6.1. transactional.id

transactional.id là định danh ổn định của một logical transactional producer. Coordinator dùng nó để xác định trạng thái giao dịch và quản lý producer epoch.

Ví dụ:

~~~properties
transactional.id=orders-publisher-instance-1
~~~

Nguyên tắc:

- Mỗi producer instance đang hoạt động độc lập phải có transactional.id riêng.
- Khi cùng logical producer khởi động lại, transactional.id cần được giữ ổn định để Kafka có thể khôi phục và fence phiên cũ.
- Nếu hai producer đồng thời dùng cùng transactional.id, producer mới có thể làm producer cũ bị fence.
- Không tạo transactional.id ngẫu nhiên ở mỗi lần khởi động nếu muốn giữ danh tính logical producer qua restart.

transactional.id khác group.id. Group ID định danh consumer group; transactional.id định danh producer tham gia giao dịch.

### 6.2. Transaction coordinator

Transaction coordinator là broker chịu trách nhiệm điều phối transaction cho transactional.id. Kafka ánh xạ transactional.id đến partition tương ứng của topic nội bộ __transaction_state. Broker leader của partition đó đảm nhận vai trò coordinator.

Coordinator theo dõi:

- Producer ID và epoch.
- Transaction timeout.
- Trạng thái transaction.
- Các topic-partition tham gia.
- Quyết định commit hoặc abort.
- Tiến độ ghi transaction marker.

Producer vẫn gửi record trực tiếp đến leader của partition dữ liệu. Coordinator quản lý metadata và quyết định transaction; nó không gom toàn bộ payload record qua một broker trung tâm.

### 6.3. Luồng commit transaction

~~~mermaid
sequenceDiagram
    participant P as Transactional Producer
    participant TC as Transaction Coordinator
    participant TS as __transaction_state
    participant L1 as orders-0 leader
    participant L2 as shipments-1 leader

    P->>TC: initTransactions()
    P->>P: beginTransaction()
    P->>L1: Ghi output record
    P->>L2: Ghi output record
    P->>TC: commitTransaction()
    TC->>TS: Ghi PrepareCommit
    TC->>L1: WriteTxnMarkers(COMMIT)
    TC->>L2: WriteTxnMarkers(COMMIT)
    L1-->>TC: Marker được ghi
    L2-->>TC: Marker được ghi
    TC->>TS: Ghi CompleteCommit
    TC-->>P: Commit hoàn tất
~~~

Luồng khái quát:

1. Producer gọi initTransactions() để đăng ký transactional.id.
2. Producer gọi beginTransaction().
3. Producer gửi record đến một hoặc nhiều partition.
4. Coordinator ghi nhận các partition tham gia.
5. Producer gọi commitTransaction().
6. Coordinator ghi quyết định commit vào transaction state log.
7. Coordinator yêu cầu các partition ghi commit marker.
8. Khi transaction hoàn tất, producer nhận kết quả commit.

Nếu ứng dụng gọi abortTransaction(), coordinator điều phối ghi abort marker. Consumer read_committed sẽ bỏ qua record thuộc transaction bị abort.

## 7. So sánh trực tiếp idempotent và transactional producer

| Tiêu chí | Idempotent producer | Transactional producer |
|---|---|---|
| Mục tiêu chính | Tránh duplicate do retry của cùng producer protocol | Commit/abort nhiều thao tác Kafka như một đơn vị |
| Định danh | Producer ID và epoch do Kafka quản lý | transactional.id kết hợp producer ID và epoch |
| Sequence number | Có | Có, vì transaction producer dùng idempotence |
| Một partition | Có | Có |
| Nhiều partition | Không tạo atomicity giữa partition | Có thể nhóm nhiều partition trong một transaction |
| Nhiều topic | Có thể gửi đến nhiều topic nhưng từng lần ghi không nguyên tử chung | Có thể commit/abort record trên nhiều topic |
| Consumer offsets | Không tự đưa offsets vào cùng thao tác ghi | Có thể dùng sendOffsetsToTransaction() |
| Transaction coordinator | Không cần transaction coordinator cho idempotence đơn thuần | Cần transaction coordinator |
| Commit/abort | Không có API transaction | Có begin, commit và abort |
| Consumer read_committed | Không bắt buộc | Cần khi consumer chỉ muốn thấy transaction đã commit |
| Exactly-once trong Kafka | Chống duplicate do retry ở producer; chưa đủ cho consume-transform-produce | Hỗ trợ exactly-once consume-transform-produce khi output và offsets cùng transaction |

**Kết luận lựa chọn:** nếu ứng dụng chỉ cần chống duplicate do producer retry, idempotent producer thường đủ. Nếu ứng dụng cần nhiều output Kafka và consumer offsets cùng thành công hoặc cùng bị hủy, cần transactional producer.

## 8. Vì sao transactional producer bao gồm idempotence?

Transactional producer phải gửi record đến nhiều partition và có thể retry request trong lúc transaction đang diễn ra. Nếu retry tạo duplicate, kết quả transaction cũng có thể sai.

Vì thế transactional producer sử dụng các cơ chế producer ID, epoch và sequence number của idempotence. Transaction bổ sung khả năng điều phối commit/abort trên nhiều partition.

Có thể hình dung:

~~~text
Idempotent producer:
  Producer identity
       |
  Sequence per partition
       |
  Retry không append duplicate

Transactional producer:
  Producer identity + epoch
       |
  Transaction coordinator
       |
  Nhiều partition tham gia
       |
  Commit hoặc Abort toàn transaction
       |
  Consumer read_committed quan sát kết quả
~~~

Không cần bật hai cơ chế như hai producer riêng biệt. Khi cấu hình transactional.id, Kafka producer sử dụng các cơ chế idempotence cần thiết cho transaction. Nên kiểm tra effective configuration theo phiên bản Kafka client.

## 9. Ví dụ transactional producer bằng Java

Ví dụ gửi hai event vào hai topic trong cùng transaction:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class TransactionalOrderProducer {

    public static void main(String[] args) {
        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            "orders-publisher-instance-1"
        );
        properties.put("transaction.timeout.ms", 60000);

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {

            producer.initTransactions();

            try {
                producer.beginTransaction();

                producer.send(
                    new ProducerRecord<>(
                        "payment.events",
                        "ORD-1001",
                        "PaymentCompleted"
                    )
                );

                producer.send(
                    new ProducerRecord<>(
                        "orders.events",
                        "ORD-1001",
                        "OrderReadyToShip"
                    )
                );

                producer.commitTransaction();

            } catch (Exception exception) {
                try {
                    producer.abortTransaction();
                } catch (KafkaException abortException) {
                    exception.addSuppressed(abortException);
                }

                throw new RuntimeException(
                    "Kafka transaction failed",
                    exception
                );
            }
        }
    }
}
~~~

Các bước cần nhớ:

- transactional.id phải ổn định và duy nhất giữa các producer instance hoạt động đồng thời.
- initTransactions() khởi tạo producer và đăng ký với coordinator.
- beginTransaction() bắt đầu transaction.
- send() thêm record vào transaction.
- commitTransaction() xác nhận toàn bộ transaction.
- abortTransaction() hủy transaction nếu ứng dụng quyết định không commit.

Trong production, cần phân biệt lỗi retryable và lỗi fatal. Producer bị fence không được tiếp tục sử dụng. Nếu commitTransaction() gặp timeout hoặc lỗi không rõ kết quả, không nên tự suy đoán transaction đã commit hay abort; cần xử lý theo semantics và exception của Kafka client đang dùng.

## 10. Consumer phải dùng read_committed khi cần kết quả transaction

Transactional producer ghi record trước khi transaction được quyết định. Trong thời gian transaction chưa hoàn tất, consumer read_uncommitted có thể nhìn thấy các record đó.

Consumer read_committed chỉ trả về:

- Record không thuộc transaction.
- Record thuộc transaction đã commit.

Nó bỏ qua record thuộc transaction đã abort và không đọc vượt qua Last Stable Offset khi còn transaction chưa hoàn tất sớm nhất trong partition.

Cấu hình Java:

~~~java
Properties properties = new Properties();

properties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-downstream"
);
properties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
properties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
properties.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
~~~

Nếu consumer dùng read_uncommitted, nó có thể xử lý record thuộc transaction sau đó bị abort. Vì vậy, read_committed là một phần quan trọng của luồng consume-transform-produce exactly-once trong Kafka.

## 11. Exactly-once consume-transform-produce

Một ứng dụng xử lý event thường cần:

1. Đọc record đầu vào từ topic orders.
2. Biến đổi dữ liệu.
3. Ghi record đầu ra sang topic shipments.
4. Commit offset đầu vào để không đọc lại record đã xử lý.

Nếu output và offset không được commit cùng nhau, có thể xảy ra hai tình huống:

- Output commit trước, offset chưa commit: restart có thể đọc lại input và tạo output trùng.
- Offset commit trước, output chưa commit: restart có thể bỏ qua input dù output chưa được tạo.

Kafka transaction cho phép gửi output records và consumer offsets trong cùng transaction.

### 11.1. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant P as Transactional Producer
    participant TC as Transaction Coordinator
    participant K as Kafka partitions

    C->>K: poll input records
    C->>P: beginTransaction()
    P->>K: Ghi output records
    C->>P: sendOffsetsToTransaction()
    P->>TC: commitTransaction()
    TC->>K: Commit output và offsets
    TC-->>P: Transaction hoàn tất
~~~

Nếu transaction commit thành công, output records và offsets đầu vào được xác nhận trong cùng transaction. Nếu abort, output bị loại khỏi kết quả read_committed và input offset không được commit trong transaction đó.

### 11.2. Ví dụ Java

~~~java
ConsumerRecords<String, String> records =
    consumer.poll(Duration.ofSeconds(1));

if (!records.isEmpty()) {
    producer.beginTransaction();

    try {
        for (ConsumerRecord<String, String> record : records) {
            ProducerRecord<String, String> output =
                new ProducerRecord<>(
                    "shipments.events",
                    record.key(),
                    transform(record.value())
                );

            producer.send(output);
        }

        Map<TopicPartition, OffsetAndMetadata> offsets =
            new HashMap<>();

        for (TopicPartition partition : records.partitions()) {
            List<ConsumerRecord<String, String>> partitionRecords =
                records.records(partition);

            long nextOffset =
                partitionRecords.get(partitionRecords.size() - 1).offset() + 1;

            offsets.put(
                partition,
                new OffsetAndMetadata(nextOffset)
            );
        }

        producer.sendOffsetsToTransaction(
            offsets,
            consumer.groupMetadata()
        );

        producer.commitTransaction();

    } catch (Exception exception) {
        producer.abortTransaction();
        throw new RuntimeException(
            "Consume-transform-produce failed",
            exception
        );
    }
}
~~~

Đây là ví dụ minh họa cho một batch xử lý tuần tự. Ứng dụng production cần quản lý consumer rebalance, transaction timeout, retry, producer fencing và các lỗi fatal. Khi partition bị thu hồi trong lúc xử lý, ứng dụng phải phối hợp dừng công việc và không commit offset của assignment đã mất.

Nếu consumer xử lý song song, chỉ đưa vào transaction offset tiếp theo sau chuỗi record liên tục đã hoàn tất cho từng partition. Không commit vượt qua record còn đang xử lý.

### 11.3. Điều kiện để đạt exactly-once trong Kafka

- Output records được gửi qua transactional producer.
- Consumer offsets được đưa vào cùng transaction bằng sendOffsetsToTransaction().
- Transaction được commit/abort theo kết quả xử lý.
- Consumer downstream dùng read_committed nếu chỉ chấp nhận output đã commit.
- Ứng dụng quản lý rebalance và partition assignment đúng cách.
- Side effect ngoài Kafka được xử lý bằng cơ chế riêng.

Exactly-once ở đây nói về kết quả trong luồng Kafka được transaction bảo vệ. Nó không tự mở rộng sang mọi hệ thống mà ứng dụng gọi.

## 12. Cấu hình Spring Kafka

Spring Kafka hỗ trợ transaction thông qua transactional ProducerFactory, KafkaTemplate và KafkaTransactionManager.

Ví dụ cấu hình trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-tx-
      properties:
        transaction.timeout.ms: 60000
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

transaction-id-prefix cần tạo ra transactional.id duy nhất cho mỗi producer instance. Ví dụ, có thể thêm mã instance do môi trường triển khai cấp vào prefix; không dùng cùng một prefix gây trùng transactional.id giữa các instance hoạt động độc lập.

Spring Kafka có thể tạo transactional producer và quản lý transaction cho KafkaTemplate.

Ví dụ gửi nhiều record trong một transaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
        KafkaTemplate<String, String> kafkaTemplate
    ) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrderEvents(
        String orderId,
        String paymentEvent,
        String orderEvent
    ) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                "payment.events",
                orderId,
                paymentEvent
            );

            operations.send(
                "orders.events",
                orderId,
                orderEvent
            );

            return true;
        });
    }
}
~~~

Nếu callback hoàn thành bình thường, transaction được commit. Nếu callback ném exception, framework abort transaction theo cơ chế transaction được cấu hình.

Với @KafkaListener, Spring Kafka có thể kết hợp xử lý listener và Kafka transaction. Cần cấu hình transaction manager, listener container, AckMode và error handler phù hợp với phiên bản Spring Kafka. Không nên giả định annotation @Transactional tự động tạo một distributed transaction giữa Kafka và database.

## 13. Transactional producer và producer fencing

transactional.id cho phép Kafka nhận diện logical producer qua restart. Khi một producer mới khởi tạo với cùng transactional.id, coordinator có thể tăng producer epoch để fence phiên cũ.

Ví dụ:

~~~text
Instance A:
  transactional.id = orders-publisher-1
  producer epoch = 3

Instance B khởi động với cùng transactional.id:
  coordinator cấp epoch mới = 4

Instance A tiếp tục gửi:
  request mang epoch 3 bị từ chối
  Producer A bị fence
~~~

Fencing ngăn hai instance cùng điều khiển transaction với một transactional.id. Đây là cơ chế bảo vệ tính nhất quán của transaction.

Một số lỗi liên quan:

- ProducerFencedException: producer cũ bị producer mới thay thế.
- InvalidProducerEpochException: epoch không còn hợp lệ.
- TransactionalIdAuthorizationException: producer không có quyền dùng transactional.id.
- CoordinatorNotAvailableException: coordinator tạm thời không sẵn sàng.
- TimeoutException: request hoặc transaction vượt quá thời gian chờ.

Nếu producer bị fence, hãy đóng instance đó và kiểm tra transactional.id có bị trùng giữa các instance không. Không retry vô hạn trên cùng producer đã bị fence.

## 14. Timeout và vận hành transaction

Transaction cần được giới hạn thời gian để coordinator có thể xử lý producer bị treo.

Các cấu hình liên quan:

| Cấu hình | Vai trò |
|---|---|
| transactional.id | Định danh logical producer. |
| transaction.timeout.ms | Thời gian producer yêu cầu cho một transaction. |
| transaction.max.timeout.ms | Giới hạn trên broker cho transaction timeout. |
| transaction.state.log.replication.factor | Replication factor của topic nội bộ __transaction_state. |
| transaction.state.log.min.isr | Min ISR của transaction state log. |
| transactional.id.expiration.ms | Thời gian metadata transactional.id không hoạt động trước khi đủ điều kiện hết hạn. |

Nguyên tắc vận hành:

1. Giữ transaction ngắn và có giới hạn.
2. Không gọi HTTP API chậm hoặc chờ người dùng trong khi transaction đang mở.
3. Chọn transaction timeout phù hợp với batch size và độ trễ broker.
4. Bảo đảm __transaction_state có replication phù hợp.
5. Theo dõi transaction duration, commit rate, abort rate và timeout.
6. Theo dõi coordinator errors và producer fencing.
7. Dùng transactional.id ổn định nhưng duy nhất giữa các producer instance.
8. Có quy trình xử lý lỗi khi commit hoặc abort không hoàn tất đúng thời hạn.

Transaction kéo dài có thể giữ Last Stable Offset ở một vị trí, khiến consumer read_committed chưa đọc được record phía sau trên partition liên quan.

## 15. Kafka transaction không bao gồm database hoặc HTTP API

Một hiểu nhầm phổ biến là transactional producer làm cho toàn bộ nghiệp vụ trở thành exactly-once. Thực tế, Kafka transaction chỉ quản lý những thao tác Kafka được đưa vào transaction.

Ví dụ:

1. Ứng dụng cập nhật PostgreSQL.
2. Ứng dụng gửi OrderCreated đến Kafka.
3. Kafka transaction commit thành công.

Nếu database commit nhưng Kafka transaction abort, database và Kafka có thể lệch nhau. Transaction coordinator của Kafka không thể rollback transaction PostgreSQL thông thường.

### 15.1. Transactional outbox

Một cách xử lý phổ biến là transactional outbox:

1. Trong cùng transaction database, ứng dụng cập nhật bảng nghiệp vụ và ghi một outbox event.
2. CDC connector hoặc relay đọc outbox.
3. Relay phát event lên Kafka.
4. Consumer downstream xử lý event idempotent.

Database bảo đảm cập nhật nghiệp vụ và outbox row cùng commit. Kafka nhận event từ outbox qua một luồng truyền riêng có khả năng retry.

### 15.2. Idempotent consumer và inbox

Nếu consumer gọi API hoặc ghi database bên ngoài Kafka, hãy thiết kế xử lý idempotent:

- Dùng event ID ổn định.
- Lưu event ID đã xử lý trong database.
- Dùng unique constraint hoặc inbox table để chống xử lý trùng.
- Gộp cập nhật nghiệp vụ và ghi nhận event ID trong cùng transaction database.

### 15.3. Saga

Với workflow trải qua nhiều dịch vụ, có thể dùng saga để phối hợp các bước nghiệp vụ và hành động bù trừ. Saga không tạo một transaction ACID xuyên suốt, nhưng giúp quản lý trạng thái khi một bước thất bại sau khi bước trước đã commit.

## 16. Bảng lựa chọn cơ chế

| Yêu cầu | Idempotent producer | Transactional producer |
|---|---|---|
| Retry do timeout không tạo duplicate protocol | Có | Có, vì transaction producer dùng idempotence |
| Gửi một record vào một partition | Có | Có |
| Ghi nhiều partition nguyên tử | Không | Có |
| Commit output cùng consumer offsets | Không | Có |
| Consumer chỉ thấy transaction đã commit | Không cần cho idempotence đơn thuần | Dùng read_committed |
| Chống ứng dụng gửi lại cùng event ID sau restart | Cần deduplication nghiệp vụ | Vẫn cần nếu gửi lại thành transaction mới |
| Bao gồm database transaction | Không | Không tự động |
| Độ phức tạp vận hành | Thấp hơn | Cao hơn do coordinator và transaction lifecycle |

Chọn idempotent producer nếu yêu cầu chỉ là bảo vệ retry trong Kafka producer protocol. Chọn transactional producer nếu cần commit/abort nhiều thao tác Kafka cùng nhau. Không thêm transaction chỉ vì muốn chống retry duplicate; transaction làm tăng yêu cầu vận hành và quản lý trạng thái.

## 17. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Record duplicate sau retry | Idempotence tắt hoặc retry được thực hiện như một lần send nghiệp vụ mới. | Bật idempotence và kiểm tra producer identity; dùng event ID nếu cần dedup nghiệp vụ. |
| Producer bị ProducerFencedException | Hai instance dùng cùng transactional.id. | Bảo đảm transactional.id duy nhất giữa instance đồng thời và ổn định qua restart của cùng logical producer. |
| Transaction timeout | Transaction mở quá lâu hoặc producer không hoàn tất commit/abort. | Giảm thời gian xử lý trong transaction và kiểm tra timeout. |
| CoordinatorNotAvailableException | Broker coordinator failover hoặc chưa sẵn sàng. | Kiểm tra broker, leader của __transaction_state và retry theo client policy. |
| Consumer nhìn thấy record bị abort | Consumer đang dùng read_uncommitted. | Chuyển sang read_committed nếu chỉ cần dữ liệu đã commit. |
| Output trùng khi consume-transform-produce | Output và input offsets không được đưa vào cùng transaction. | Dùng sendOffsetsToTransaction() và commit transaction chung. |
| Transaction không commit được | Partition thiếu ISR, coordinator lỗi hoặc producer đã bị fence. | Kiểm tra ISR, broker logs, coordinator errors và producer epoch. |
| Database và Kafka lệch trạng thái | Ứng dụng giả định Kafka transaction bao gồm database. | Dùng transactional outbox, CDC, inbox hoặc saga. |

## 18. Checklist triển khai production

Trước khi đưa producer vào production, hãy xác nhận:

1. Yêu cầu thực sự là chống retry duplicate hay atomicity nhiều thao tác?
2. Idempotent producer đã được bật và cấu hình tương thích chưa?
3. Producer dùng acks=all khi yêu cầu durability cao chưa?
4. transactional.id có ổn định và duy nhất giữa các instance chưa?
5. Transaction timeout có phù hợp với thời gian xử lý không?
6. Producer có xử lý ProducerFencedException đúng cách không?
7. Consumer downstream có dùng read_committed khi cần không?
8. Consume-transform-produce có gửi input offsets vào transaction không?
9. Consumer có commit offset liên tục sau record đã xử lý không?
10. __transaction_state có replication và min ISR phù hợp không?
11. Transaction duration, abort rate và coordinator errors có được giám sát không?
12. Side effect database hoặc HTTP có cơ chế outbox/inbox/idempotency riêng không?
13. Có kiểm thử broker failover, producer restart và transaction timeout trong môi trường lab không?

## 19. Bài tập thực hành

### Bài 1: Quan sát retry với idempotent producer

1. Tạo topic orders-lab có một partition.
2. Viết producer bật enable.idempotence=true.
3. Gửi record và quan sát callback hoặc metadata offset.
4. Tạo lỗi mạng ngắn trong môi trường lab để producer phải retry.
5. Kiểm tra log và số record được append.
6. Tắt idempotence trong một lần chạy thử và so sánh hành vi retry.
7. Giải thích vì sao application-level resend vẫn có thể tạo duplicate.

### Bài 2: Ghi nhiều topic bằng transaction

1. Tạo topic payment.events và orders.events.
2. Viết transactional producer với transactional.id cố định.
3. Gửi một record vào mỗi topic trong cùng transaction.
4. Commit transaction và đọc bằng consumer read_committed.
5. Chạy lại nhưng chủ động abort trước commit.
6. So sánh kết quả read_committed và read_uncommitted.

### Bài 3: Producer fencing

1. Khởi chạy producer A với transactional.id là orders-publisher-1.
2. Khởi chạy producer B với cùng transactional.id.
3. Quan sát producer A bị fence khi tiếp tục thao tác.
4. Giải thích vai trò producer epoch và vì sao mỗi instance đồng thời cần ID riêng.

### Bài 4: Exactly-once consume-transform-produce

1. Tạo topic input.orders và output.shipments.
2. Consumer đọc batch từ input.orders.
3. Producer bắt đầu transaction và ghi output.
4. Gọi sendOffsetsToTransaction() với offset tiếp theo của mỗi partition.
5. Commit transaction.
6. Restart ứng dụng ở các thời điểm khác nhau để kiểm tra output và input offset.
7. Dùng consumer read_committed xác nhận chỉ nhìn thấy output đã commit.

### Bài 5: Kafka và database

Thiết kế một luồng tạo đơn hàng có cập nhật PostgreSQL và phát event Kafka. Chỉ ra tình huống database commit nhưng Kafka abort. Đề xuất transactional outbox và giải thích vì sao Kafka transaction không tự giải quyết được vấn đề này.

## 20. Câu hỏi tự kiểm tra

1. Vì sao producer timeout có thể dẫn đến duplicate?
2. Producer ID, epoch và sequence number có vai trò gì?
3. Idempotent producer ngăn loại duplicate nào?
4. Vì sao idempotence không loại bỏ hai lần send riêng biệt cho cùng event ID?
5. Transactional.id khác group.id như thế nào?
6. Transaction coordinator quản lý thông tin gì?
7. Vì sao transactional producer sử dụng idempotence?
8. Transaction marker được ghi ở đâu?
9. read_committed khác read_uncommitted như thế nào?
10. Vì sao output records và consumer offsets cần nằm trong cùng transaction?
11. sendOffsetsToTransaction() nhận offset nào: offset record cuối hay offset tiếp theo cần đọc?
12. ProducerFencedException xảy ra trong tình huống nào?
13. Kafka transaction có bao gồm PostgreSQL transaction không?
14. Transactional outbox giải quyết khoảng trống nhất quán nào?
15. Khi nào nên chọn idempotent producer thay vì transactional producer?

## Kết luận

Idempotent producer bảo vệ thao tác ghi trước duplicate phát sinh từ retry của cùng producer protocol bằng Producer ID, epoch và sequence number. Nó phù hợp khi ứng dụng cần gửi record tin cậy hơn mà không cần gom nhiều thao tác thành một transaction.

Transactional producer sử dụng idempotence và bổ sung transactional.id, transaction coordinator, transaction marker cùng commit/abort. Nó có thể nhóm record trên nhiều partition và consumer offsets thành một đơn vị Kafka transaction. Để consumer chỉ nhận dữ liệu đã commit, cần dùng read_committed.

Hai cơ chế không thay thế hoàn toàn cho nhau. Idempotence xử lý retry ở tầng producer; transaction xử lý atomicity trong phạm vi Kafka. Khi nghiệp vụ còn cập nhật database hoặc gọi dịch vụ bên ngoài, cần thêm transactional outbox, inbox, idempotency hoặc saga để phối hợp trạng thái.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Idempotent producer | Producer dùng PID, epoch và sequence để broker nhận diện request retry. |
| Transactional producer | Producer có thể commit/abort nhiều thao tác Kafka trong một transaction. |
| Producer ID (PID) | Định danh producer ở cấp giao thức Kafka. |
| Producer epoch | Thế hệ producer dùng để fence phiên cũ. |
| Sequence number | Số thứ tự batch record của producer trên từng partition. |
| transactional.id | Định danh ổn định của logical transactional producer. |
| Transaction coordinator | Broker điều phối vòng đời transaction. |
| __transaction_state | Topic nội bộ lưu metadata và trạng thái transaction. |
| Transaction marker | Control record đánh dấu commit hoặc abort trên partition. |
| Producer fencing | Cơ chế ngăn producer cũ tiếp tục ghi sau khi bị thay thế. |
| read_committed | Isolation level chỉ trả về record ngoài transaction hoặc thuộc transaction đã commit. |
| sendOffsetsToTransaction() | Đưa consumer offsets vào cùng Kafka transaction với output records. |
| Transactional outbox | Mẫu ghi event vào outbox cùng transaction database rồi phát sang Kafka. |
| Exactly-once processing | Bảo đảm kết quả xử lý không bị nhân đôi trong phạm vi được transaction bảo vệ. |

