# sendOffsetsToTransaction trong luồng đọc, xử lý và ghi lại Kafka

Một ứng dụng Kafka thường đọc event từ topic đầu vào, biến đổi dữ liệu rồi ghi kết quả sang topic khác. Nếu producer ghi output thành công nhưng consumer offset chưa được commit, ứng dụng có thể đọc lại input và ghi output trùng. Nếu commit offset trước rồi ghi output thất bại, event có thể bị bỏ qua.

Kafka transaction giải quyết khoảng hở này bằng cách đưa **output records và offset của input consumer vào cùng một transaction**. API `sendOffsetsToTransaction()` là bước đăng ký offset vào transaction đang mở. Khi transaction commit, output và offset cùng được commit; khi transaction abort, cả hai cùng không được xem là đã commit.

## 1. Vấn đề khi chỉ commit offset thông thường

Giả sử service đọc từ `orders`, tính phí và ghi kết quả vào `order-fees`.

Nếu ứng dụng thực hiện hai thao tác độc lập:

1. Gửi kết quả sang `order-fees`.
2. Gọi `consumer.commitSync()` để commit offset input.

Một sự cố có thể xảy ra giữa hai thao tác:

- Output đã được ghi nhưng offset chưa commit: input được đọc lại và output có thể bị ghi lần nữa.
- Offset đã commit nhưng output chưa được ghi: input bị bỏ qua khi consumer tiếp tục.

~~~mermaid
flowchart TD
    A["Consumer đọc input offset 120"] --> B["Transform event"]
    B --> C["Ghi output topic"]
    C --> D{"Process gặp sự cố?"}
    D -->|"Trước commit offset"| E["Input được đọc lại<br/>Output có thể trùng"]
    D -->|"Commit offset trước output"| F["Output thất bại<br/>Input đã bị bỏ qua"]
~~~

Đây là vấn đề dual-write giữa output Kafka và offset consumer. Gọi hai API riêng biệt không làm chúng trở thành một thao tác nguyên tử.

## 2. sendOffsetsToTransaction giải quyết điều gì?

`sendOffsetsToTransaction()` thêm tiến độ đọc của consumer vào transaction của producer. Ứng dụng thực hiện:

1. Đọc record từ input topic.
2. Bắt đầu producer transaction.
3. Ghi các record đã transform vào output topic.
4. Gọi `sendOffsetsToTransaction()` với offset tiếp theo cần đọc của từng partition và metadata của consumer group.
5. Commit transaction.

Kafka phối hợp transaction coordinator và group coordinator để output records cùng consumer offsets thuộc một transaction. Khi commit thành công, cả hai phía được ghi nhận. Khi abort, output transactional không được consumer `read_committed` nhìn thấy và input offsets không tiến lên.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant B as Input partition leader
    participant P as Transactional producer
    participant TC as Transaction coordinator
    participant GC as Group coordinator
    participant O as Output partition leader

    C->>B: Fetch input records
    B-->>C: Batch + offsets
    P->>TC: beginTransaction / transaction state
    P->>O: Produce output records
    O-->>P: Produce acknowledgements
    P->>TC: Add offsets to transaction
    P->>GC: TxnOffsetCommit + group metadata
    GC-->>P: Offset accepted into transaction
    P->>TC: EndTxn(commit)
    TC-->>P: Transaction committed
~~~

Điểm cốt lõi: offset được gửi vào transaction phải là **offset tiếp theo cần đọc**, không phải offset cuối cùng vừa xử lý.

## 3. Phân biệt các API liên quan

| API | Vai trò |
|---|---|
| `producer.beginTransaction()` | Bắt đầu transaction mới |
| `producer.send(record)` | Gửi output record trong transaction hiện tại |
| `producer.sendOffsetsToTransaction(offsets, groupMetadata)` | Đăng ký offset input của consumer group vào transaction |
| `producer.commitTransaction()` | Commit output và offset trong cùng transaction |
| `producer.abortTransaction()` | Abort transaction, loại bỏ kết quả transactional chưa commit |
| `consumer.commitSync()` | Commit offset độc lập qua consumer; không dùng để thay thế sendOffsetsToTransaction trong luồng EOS |

Không gọi `consumer.commitSync()` cho cùng batch sau khi đã dùng `sendOffsetsToTransaction()`. Làm như vậy tạo một đường commit riêng bên ngoài transaction và phá vỡ tính nguyên tử mà luồng đang cần.

Consumer phải tắt auto commit:

~~~properties
enable.auto.commit=false
~~~

Nếu auto commit vẫn bật, consumer có thể commit input offset độc lập trong lúc producer transaction chưa hoàn tất.

## 4. Tính offset tiếp theo cho từng partition

Kafka quản lý offset riêng cho từng partition. Khi đưa offset vào transaction, ứng dụng phải gửi vị trí tiếp theo cần đọc.

Ví dụ batch nhận được:

| Topic-partition | Record đã xử lý | Offset cần gửi vào transaction |
|---|---|---:|
| `orders-0` | 120, 121, 122 | 123 |
| `orders-1` | 45, 46 | 47 |
| `orders-2` | 90 | 91 |

Công thức:

`committed offset = last successfully processed offset + 1`

Không gửi offset cuối cùng đã xử lý. Nếu gửi 122 thay vì 123, consumer sẽ đọc lại record offset 122 sau lần khởi động tiếp theo.

### 4.1. Xây dựng map offset

Với batch được xử lý tuần tự và toàn bộ record trong batch đều thành công, có thể lấy offset lớn nhất đã xử lý của mỗi partition rồi cộng một:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsetsForTransaction(
        ConsumerRecords<String, String> records) {

    Map<TopicPartition, Long> nextOffsets = new HashMap<>();

    for (ConsumerRecord<String, String> record : records) {
        TopicPartition partition = new TopicPartition(
            record.topic(),
            record.partition()
        );

        nextOffsets.merge(
            partition,
            record.offset() + 1,
            Math::max
        );
    }

    Map<TopicPartition, OffsetAndMetadata> offsets =
        new HashMap<>();

    nextOffsets.forEach((partition, nextOffset) ->
        offsets.put(partition, new OffsetAndMetadata(nextOffset))
    );

    return offsets;
}
~~~

Cách tính này chỉ an toàn khi mọi record trong batch đến offset cao nhất của mỗi partition đã được xử lý thành công. Nếu xử lý song song và offset 122 hoàn thành trước offset 121, không được commit 123 khi 121 chưa xong. Khi đó phải theo dõi offset liên tục đã hoàn tất cho từng partition.

Offset có thể không liên tiếp do compaction hoặc control records; dùng offset thực tế của record cuối cùng đã xử lý cộng một, không tự giả định batch luôn bắt đầu ở một offset liền kề.

## 5. ConsumerGroupMetadata và vì sao cần truyền metadata group

API hiện đại có dạng:

~~~java
producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

`consumer.groupMetadata()` cung cấp metadata của consumer group, gồm các thông tin như group ID, generation/member identity và static member identity nếu có. Metadata này giúp broker xác nhận offset đang được commit bởi đúng generation/member còn hợp lệ.

Không nên chỉ truyền một chuỗi `group.id` khi có thể dùng API nhận `ConsumerGroupMetadata`. Nếu group đã rebalance và consumer không còn quyền commit offset cho generation cũ, broker có thể từ chối thao tác thay vì chấp nhận offset của member đã mất assignment.

Một số phiên bản Kafka client cũ có overload nhận `groupId`. Khi phát triển mới, ưu tiên overload nhận `ConsumerGroupMetadata` nếu phiên bản client hỗ trợ. Kiểm tra API của dependency `kafka-clients` thực tế trước khi áp dụng.

## 6. Cấu hình consumer và transactional producer

Ví dụ cấu hình consumer:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=order-fee-processor
enable.auto.commit=false
isolation.level=read_committed
key.deserializer=org.apache.kafka.common.serialization.StringDeserializer
value.deserializer=org.apache.kafka.common.serialization.StringDeserializer
max.poll.records=100
~~~

Ví dụ cấu hình producer:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
transactional.id=order-fee-processor-0
enable.idempotence=true
acks=all
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.StringSerializer
transaction.timeout.ms=60000
~~~

Các điểm cần lưu ý:

- `transactional.id` là định danh ổn định cho logical transactional producer instance và phải duy nhất giữa các instance hoạt động đồng thời.
- Khi cùng logical instance khởi động lại, có thể dùng lại transactional ID để producer mới fence instance cũ.
- Không dùng chung một transactional ID cho nhiều replica chạy đồng thời.
- Producer transaction bật idempotence; các điều kiện cấu hình liên quan như `acks=all` được yêu cầu.
- `transaction.timeout.ms` phải đủ cho thời gian xử lý batch, gửi output và commit; broker giới hạn giá trị tối đa qua `transaction.max.timeout.ms`.
- `isolation.level=read_committed` giúp consumer chỉ đọc output thuộc transaction đã commit. Nếu input topic cũng chứa dữ liệu transactional và ứng dụng không muốn xử lý dữ liệu đã abort, cũng cần đọc input với `read_committed`.

Giá trị trên là ví dụ cho lab, không phải cấu hình tối ưu cho mọi workload.

## 7. Ví dụ Java: consume-transform-produce nguyên tử

Ví dụ sau đọc một batch từ `orders`, chuyển thành record cho `order-fees`, đưa offset input vào transaction rồi commit.

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

public class OrderFeeProcessor {

    public static void main(String[] args) {
        Properties consumerProps = new Properties();
        consumerProps.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        consumerProps.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "order-fee-processor"
        );
        consumerProps.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false
        );
        consumerProps.put(
            ConsumerConfig.ISOLATION_LEVEL_CONFIG,
            "read_committed"
        );
        consumerProps.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        consumerProps.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        consumerProps.put(
            ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
            100
        );

        Properties producerProps = new Properties();
        producerProps.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        producerProps.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        producerProps.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        producerProps.put(
            ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            "order-fee-processor-0"
        );
        producerProps.put(ProducerConfig.ACKS_CONFIG, "all");
        producerProps.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(consumerProps);
             KafkaProducer<String, String> producer =
                 new KafkaProducer<>(producerProps)) {

            producer.initTransactions();
            consumer.subscribe(java.util.List.of("orders"));

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(500));

                if (records.isEmpty()) {
                    continue;
                }

                producer.beginTransaction();

                try {
                    for (ConsumerRecord<String, String> record : records) {
                        ProducerRecord<String, String> output =
                            transform(record);

                        producer.send(output);
                    }

                    Map<TopicPartition, OffsetAndMetadata> offsets =
                        offsetsForTransaction(records);

                    producer.sendOffsetsToTransaction(
                        offsets,
                        consumer.groupMetadata()
                    );

                    producer.commitTransaction();

                } catch (Exception exception) {
                    try {
                        producer.abortTransaction();
                    } catch (Exception abortException) {
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

    private static ProducerRecord<String, String> transform(
            ConsumerRecord<String, String> input) {

        String outputValue =
            "{\"sourceOffset\":" + input.offset()
            + ",\"order\":" + input.value() + "}";

        return new ProducerRecord<>(
            "order-fees",
            input.key(),
            outputValue
        );
    }

    private static Map<TopicPartition, OffsetAndMetadata>
    offsetsForTransaction(
            ConsumerRecords<String, String> records) {

        Map<TopicPartition, Long> nextOffsets = new HashMap<>();

        for (ConsumerRecord<String, String> record : records) {
            TopicPartition partition = new TopicPartition(
                record.topic(),
                record.partition()
            );

            nextOffsets.merge(
                partition,
                record.offset() + 1,
                Math::max
            );
        }

        Map<TopicPartition, OffsetAndMetadata> offsets =
            new HashMap<>();

        nextOffsets.forEach((partition, nextOffset) ->
            offsets.put(partition, new OffsetAndMetadata(nextOffset))
        );

        return offsets;
    }
}
~~~

Đây là skeleton minh họa. Trong service thực tế cần bổ sung shutdown có kiểm soát, logging, metric, retry/fatal exception handling và xử lý rebalance. Vòng lặp mẫu ném lỗi ra ngoài để process dừng khi transaction thất bại; không nên tự động tiếp tục với cùng producer sau mọi loại exception.

### 7.1. Trình tự trong mỗi batch

| Bước | Hành động | Ý nghĩa |
|---:|---|---|
| 1 | `consumer.poll()` | Lấy batch input |
| 2 | `producer.beginTransaction()` | Mở transaction |
| 3 | `producer.send(output)` | Gửi output record vào transaction |
| 4 | Tính offset tiếp theo theo partition | Chuẩn bị checkpoint input |
| 5 | `sendOffsetsToTransaction()` | Đưa checkpoint vào transaction |
| 6 | `commitTransaction()` | Commit output và offset cùng nhau |

`send()` là bất đồng bộ. `commitTransaction()` sẽ flush các record đang chờ và chờ kết quả cần thiết trước khi hoàn tất transaction. Nếu muốn phát hiện lỗi gửi sớm hơn trong ví dụ đơn giản, có thể chờ Future của từng send, nhưng chờ từng record sẽ giảm khả năng batching và throughput.

## 8. Điều gì xảy ra khi transaction commit hoặc abort?

### 8.1. Commit thành công

Khi `commitTransaction()` thành công:

- Output records được commit.
- Input offsets được commit trong cùng transaction.
- Consumer group tiếp tục từ offset kế tiếp.
- Consumer output với `read_committed` có thể nhìn thấy output records.

### 8.2. Abort hoặc lỗi trước commit

Khi transaction bị abort:

- Output records thuộc transaction không hiển thị với consumer `read_committed`.
- Input offsets không được commit bởi transaction đó.
- Consumer có thể đọc lại input sau khi group tiếp tục.
- Ứng dụng có thể chạy lại transform trong transaction mới.

Sơ đồ:

~~~mermaid
flowchart TD
    A["beginTransaction"] --> B["Produce output"]
    B --> C["sendOffsetsToTransaction"]
    C --> D{"commitTransaction"}
    D -->|"Commit"| E["Output visible to read_committed"]
    D -->|"Abort / failure"| F["Output remains uncommitted"]
    E --> G["Input offset advances"]
    F --> H["Input offset does not advance"]
    H --> I["Input can be processed again"]
~~~

Consumer dùng `read_uncommitted` có thể nhìn thấy record transactional chưa commit hoặc đã abort. Vì vậy, các consumer downstream cần dựa vào transaction semantics nên cấu hình `isolation.level=read_committed`.

## 9. Rebalance trong khi transaction đang mở

Consumer group có thể rebalance khi consumer mất heartbeat, xử lý batch quá lâu, partition được thêm hoặc member thay đổi. Nếu consumer mất quyền sở hữu partition hoặc group generation thay đổi trong lúc xử lý, metadata gửi vào `sendOffsetsToTransaction()` có thể không còn hợp lệ.

Kafka có thể từ chối offset commit trong transaction. Khi đó ứng dụng phải abort transaction và xử lý theo trạng thái group mới. Không được cố commit offset bằng metadata cũ hoặc gọi `consumer.commitSync()` để né lỗi.

Một số nguyên tắc:

- Chỉ xử lý record thuộc partition hiện được assign.
- Giữ thời gian xử lý batch trong giới hạn `max.poll.interval.ms`.
- Giới hạn `max.poll.records` theo thời gian xử lý thực tế.
- Xử lý partition revoke/lost đúng cách; không commit offset cho partition đã mất quyền sở hữu.
- Khi group metadata không còn hợp lệ, abort transaction và để consumer đọc lại theo offset đã commit.
- Theo dõi lỗi commit, rebalance, transaction abort và consumer lag.

Nếu dùng cooperative rebalancing hoặc group protocol mới, callback và thời điểm thu hồi partition có thể khác. Thiết kế cần dựa trên protocol/assignor và phiên bản client đang triển khai.

## 10. Producer fencing và transactional.id

Kafka dùng transactional ID và producer epoch để bảo vệ quyền sở hữu transaction của một logical producer.

Ví dụ hai process cùng khởi chạy với:

~~~properties
transactional.id=order-fee-processor-0
~~~

Process mới có thể làm tăng epoch và fence process cũ. Producer cũ không còn được phép tiếp tục gửi hoặc commit transaction.

Đây là hành vi bảo vệ tính nhất quán, không phải lỗi nên retry vô hạn. Khi gặp `ProducerFencedException`, `InvalidProducerEpochException` hoặc lỗi fatal tương tự:

- Dừng sử dụng producer đã bị fence.
- Kiểm tra có hai instance dùng cùng transactional ID hay không.
- Bảo đảm transactional ID duy nhất giữa các logical instance đang chạy đồng thời.
- Tạo/khởi động producer theo lifecycle được thiết kế; không lặp lại transaction trên producer đã mất quyền.

Nếu service có nhiều replica, có thể gắn ordinal hoặc identity ổn định vào transactional ID, ví dụ `order-fee-processor-0`, `order-fee-processor-1`. Khi restart cùng logical slot, dùng lại ID đó để producer mới fence instance cũ còn sót lại.

## 11. Timeout và kích thước transaction

Transaction bao trùm thời gian xử lý batch, gửi output và đăng ký offsets. Nếu batch quá lớn hoặc downstream transform chậm, transaction có thể vượt quá `transaction.timeout.ms`.

Các tham số cần xem xét:

| Cấu hình | Phía | Tác động |
|---|---|---|
| `transaction.timeout.ms` | Producer | Thời gian tối đa transaction có thể mở theo cấu hình client |
| `transaction.max.timeout.ms` | Broker | Giới hạn trên broker chấp nhận cho transaction timeout |
| `max.poll.interval.ms` | Consumer | Giới hạn khoảng cách giữa hai lần poll |
| `max.poll.records` | Consumer | Số record tối đa trong một poll batch |
| `delivery.timeout.ms` | Producer | Giới hạn thời gian giao record, ảnh hưởng việc gửi output |

Transaction timeout và max poll interval giải quyết các vấn đề khác nhau. Tăng transaction timeout không tự ngăn consumer vượt max poll interval. Tăng max poll interval cũng không làm broker chấp nhận transaction timeout vượt giới hạn.

Hãy chọn batch đủ nhỏ để transaction hoàn tất ổn định. Đo p95/p99 thời gian transform, thời gian gửi output và commit transaction trước khi tăng timeout.

## 12. sendOffsetsToTransaction khác với consumer.commitSync

| Tiêu chí | `sendOffsetsToTransaction()` | `consumer.commitSync()` |
|---|---|---|
| Nơi commit | Trong Kafka producer transaction | Commit offset độc lập |
| Atomic với output records | Có | Không |
| Dùng cho consume-transform-produce EOS | Có | Không đủ |
| Cần transactional producer | Có | Không |
| Cần group metadata | Có, với API hiện đại | Consumer tự quản lý membership |
| Khi transaction abort | Offset không được commit bởi transaction | Offset commit riêng có thể đã tồn tại |

Nếu mục tiêu chỉ là xử lý rồi commit offset theo at-least-once, manual `commitSync()` có thể phù hợp. Nếu output và input offset phải cùng commit nguyên tử trong Kafka, dùng transactional producer và `sendOffsetsToTransaction()`.

## 13. Phạm vi exactly-once và hệ thống bên ngoài Kafka

`sendOffsetsToTransaction()` cung cấp atomicity cho output Kafka records và input offsets tham gia transaction. Nó không tự bao gồm:

- Database PostgreSQL/MySQL.
- REST hoặc gRPC service.
- Email/SMS provider.
- Payment gateway.
- File system hoặc object storage.

Ví dụ nếu ứng dụng cập nhật database rồi gửi Kafka output trong cùng luồng, Kafka transaction không thể rollback database khi Kafka transaction abort. Với database là nguồn dữ liệu chính, cân nhắc transactional outbox. Với consumer ghi database, dùng inbox/dedup cùng database transaction để side effect lũy đẳng.

Khi mô tả exactly-once, luôn nói rõ ranh giới. Kafka EOS không đồng nghĩa mọi hệ thống bên ngoài chỉ thực hiện nghiệp vụ đúng một lần.

## 14. Kiểm tra và giám sát transactional consumer

Các dấu hiệu nên theo dõi:

- Transaction commit rate và abort rate.
- Transaction duration và timeout.
- Producer fencing và invalid epoch errors.
- Consumer rebalance count.
- Consumer lag theo partition.
- Output throughput và request latency.
- Số lần retry và số batch phải xử lý lại.

Kiểm tra consumer group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-fee-processor
~~~

Kiểm tra topic đầu vào và đầu ra:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic order-fees
~~~

Các lệnh trên kiểm tra metadata và partition; chúng không tự chứng minh transaction đã commit đúng. Cần kết hợp log producer/consumer, metric transaction và một consumer `read_committed` để xác minh output quan sát được.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Output trùng sau restart | Commit output và offset tách rời hoặc downstream dùng read_uncommitted | Đưa offsets vào transaction, đọc output bằng read_committed |
| Input bị bỏ qua | Offset được commit độc lập trước khi output hoàn tất | Không dùng commitSync cho batch EOS |
| `sendOffsetsToTransaction` thất bại | Group generation/member metadata đã cũ sau rebalance | Abort transaction, xử lý assignment mới và đọc lại |
| `ProducerFencedException` | Hai instance dùng cùng transactional ID hoặc producer cũ bị thay thế | Kiểm tra uniqueness và lifecycle transactional ID |
| Transaction timeout | Batch lớn, transform chậm hoặc broker/downstream chậm | Giảm batch, đo latency, điều chỉnh timeout trong giới hạn broker |
| Output không xuất hiện với consumer | Consumer đang dùng read_committed và transaction chưa commit/đã abort | Kiểm tra transaction state và producer log |
| Commit transaction thất bại | Lỗi produce, coordinator, fencing hoặc timeout | Phân loại exception; abort/reinitialize khi cần |
| Rebalance liên tục | Poll quá chậm, heartbeat hoặc group membership không ổn định | Kiểm tra max.poll.interval, batch size, session và coordinator |

Không retry vô hạn trên cùng producer sau lỗi fatal. Một số lỗi yêu cầu dừng instance hoặc tạo producer mới theo transactional ID đã quản lý.

## 16. Checklist triển khai sendOffsetsToTransaction

- [ ] Producer có `transactional.id` duy nhất giữa các instance chạy đồng thời.
- [ ] Đã gọi `initTransactions()` trước khi xử lý.
- [ ] Consumer tắt `enable.auto.commit`.
- [ ] Consumer dùng `group.id` ổn định.
- [ ] Dùng `consumer.groupMetadata()` khi gọi API hiện đại.
- [ ] Offset gửi vào transaction là offset tiếp theo cần đọc cho từng partition.
- [ ] Chỉ tính offset từ các record đã xử lý thành công liên tục.
- [ ] Output records được gửi trước khi commit transaction.
- [ ] Gọi `sendOffsetsToTransaction()` trước `commitTransaction()`.
- [ ] Không gọi `consumer.commitSync()` cho cùng batch EOS.
- [ ] Consumer downstream dùng `read_committed`.
- [ ] Xử lý rebalance và partition revocation/loss đúng cách.
- [ ] Transaction hoàn tất trong giới hạn timeout và max poll interval.
- [ ] Phân loại producer fencing và lỗi fatal, không retry mù.
- [ ] Đã kiểm thử crash trước commit, abort và rebalance giữa xử lý.
- [ ] Không giả định Kafka transaction bao gồm database hoặc API bên ngoài.

`sendOffsetsToTransaction()` là cầu nối giữa tiến độ đọc của consumer group và output của transactional producer. Khi offset tiếp theo của từng partition được đưa vào transaction cùng output records, Kafka có thể commit hoặc abort cả hai như một đơn vị. Để đạt được semantics này, ứng dụng cần tắt auto commit, dùng group metadata hiện hành, tính offset chính xác, quản lý transactional ID ổn định và xử lý rebalance/fencing đúng cách. Bảo đảm exactly-once chỉ nằm trong phạm vi Kafka transaction; side effect bên ngoài vẫn cần inbox, outbox hoặc idempotency riêng.
