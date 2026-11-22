# Thử nghiệm crash để xác minh phạm vi exactly-once

Kafka transactions cho phép một ứng dụng consume record từ topic đầu vào, xử lý dữ liệu, ghi kết quả sang topic đầu ra và commit offset đầu vào trong cùng một giao dịch. Nếu giao dịch commit, output và offset cùng có hiệu lực; nếu giao dịch abort, output transactional không được consumer ở chế độ read_committed nhìn thấy và offset đầu vào không được tiến lên. Cơ chế này tạo nền tảng cho exactly-once processing trong phạm vi Kafka-to-Kafka.

Để hiểu chính xác phạm vi đó, cần thử nghiệm các điểm crash khác nhau: trước khi gửi output, sau khi output đã được broker nhận nhưng trước commit, sau khi gửi offset vào transaction và sau khi commit thành công. Bài này xây dựng một ứng dụng Java consume-transform-produce, dùng transactional.id ổn định, gửi offset bằng sendOffsetsToTransaction và kiểm chứng kết quả bằng cả read_committed lẫn read_uncommitted.

Exactly-once ở đây bảo đảm kết quả Kafka-to-Kafka không bị nhân đôi khi transaction được phục hồi và xử lý lại. Nó không tự bao gồm thao tác database, REST API, email hoặc hệ thống ngoài Kafka. Những side effect đó cần inbox/outbox, idempotency hoặc cơ chế phối hợp transaction riêng.

## 1. Exactly-once cần bảo vệ điều gì?

Giả sử topic đầu vào có record:

~~~text
orders.created: partition 0, offset 100, eventId=evt-100
~~~

Ứng dụng đọc record, tính phí và ghi kết quả vào topic payments.processed. Một giao dịch Kafka có thể nhóm hai hành động:

1. Ghi record kết quả vào topic đầu ra.
2. Commit offset kế tiếp của topic đầu vào cho consumer group.

Hai hành động này phải cùng commit hoặc cùng abort. Nếu chỉ ghi output rồi commit offset bằng hai request độc lập, crash có thể xảy ra ở giữa:

| Thứ tự thao tác | Crash xảy ra sau thao tác | Hệ quả nếu không dùng transaction |
|---|---|---|
| Ghi output | Trước commit offset | Consumer đọc lại input và có thể ghi output lần hai |
| Commit offset | Trước ghi output | Input đã được xác nhận nhưng output chưa được tạo; dữ liệu bị mất ở luồng xử lý |
| Ghi output và commit offset độc lập | Mạng lỗi giữa hai request | Ứng dụng khó xác định một hay cả hai thao tác đã thành công |

Kafka transaction giải quyết khoảng trống giữa output Kafka và input offset bằng một quyết định commit duy nhất của transaction coordinator.

~~~mermaid
flowchart TD
    A[Consumer poll input] --> B[Begin transaction]
    B --> C[Transform records]
    C --> D[Send output records]
    D --> E[Send input offsets to transaction]
    E --> F{Commit transaction}
    F -- Commit --> G[Output visible + offsets advanced]
    F -- Abort / crash recovery --> H[Output aborted + offsets unchanged]
    H --> I[Input records are replayed]
    I --> B
~~~

## 2. Các thành phần tham gia giao dịch

| Thành phần | Vai trò |
|---|---|
| Transactional producer | Gửi output và điều khiển begin/commit/abort |
| transactional.id | Định danh ổn định của một logical producer để khôi phục giao dịch và fencing phiên cũ |
| Producer ID và epoch | Nhận diện producer session; epoch mới vô hiệu hóa producer cũ cùng transactional.id |
| Transaction coordinator | Quản lý trạng thái transaction và ghi nhận quyết định commit/abort |
| Consumer group metadata | Xác định group/generation khi gửi offset vào transaction |
| sendOffsetsToTransaction | Đưa offset input vào cùng transaction với output |
| isolation.level=read_committed | Chỉ trả record transactional thuộc transaction đã commit |

Khi producer có transactional.id, Kafka bật idempotence cho producer. Idempotence bảo vệ việc retry gửi record trong producer protocol; transaction bổ sung khả năng commit hoặc abort một nhóm record và offset như một đơn vị.

Transactional ID phải ổn định qua lần restart của cùng một logical producer shard, nhưng phải duy nhất giữa các producer đang chạy đồng thời. Nếu hai instance cùng dùng một transactional.id, instance khởi tạo sau sẽ tăng epoch và fence instance trước. Đây là cơ chế bảo vệ, không phải cách chia sẻ một producer ID giữa nhiều instance.

## 3. Luồng consume-transform-produce đúng cách

Một vòng xử lý transactional có trình tự:

1. Consumer poll các record đầu vào.
2. Producer bắt đầu transaction.
3. Ứng dụng transform và gửi các record đầu ra.
4. Chờ các send hoàn tất hoặc xử lý lỗi gửi.
5. Tính next offset cho từng partition từ những record đã xử lý thành công.
6. Gọi sendOffsetsToTransaction với offset map và consumer.groupMetadata().
7. Gọi commitTransaction.

Không gọi consumer.commitSync hoặc commitAsync cho offset của batch đang được xử lý theo EOS. Nếu commit offset độc lập ngoài transaction, tính nguyên tử giữa output và offset bị phá vỡ.

Với mỗi partition, offset gửi vào transaction là vị trí kế tiếp cần đọc, thường là offset record cuối cùng đã xử lý thành công cộng một. Nếu batch có nhiều record, chỉ commit đến vị trí liên tục cao nhất đã xử lý xong. Không commit qua record bị lỗi hoặc chưa hoàn tất.

## 4. Chuẩn bị môi trường lab

Yêu cầu:

- JDK 17 trở lên và Maven.
- Kafka cluster có broker truy cập được từ ứng dụng.
- Hai topic riêng: orders.created làm input và payments.processed làm output.
- Một consumer group dùng riêng cho bài thử.
- Một transactional.id cố định cho logical worker của lab.

Tạo hai topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.created \
  --partitions 3 \
  --replication-factor 1

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic payments.processed \
  --partitions 3 \
  --replication-factor 1
~~~

Replication factor một phù hợp cho lab một broker, nhưng không kiểm chứng khả năng chịu lỗi broker. Với cluster nhiều broker, chọn replication factor và min.insync.replicas theo chính sách durability của môi trường.

Với Kafka lab chỉ có một broker, kiểm tra các cấu hình internal topic trước khi thử transaction. Nếu cluster chưa tạo các internal topic này, broker cần được cấu hình phù hợp với quy mô lab, ví dụ:

~~~properties
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
~~~

Đây là cấu hình riêng cho lab một broker, không dùng làm cấu hình production. Với cluster nhiều broker, giữ replication factor và min ISR phù hợp để internal offset/transaction state có khả năng chịu lỗi.

Gửi một tập input có eventId duy nhất:

~~~text
eventId=evt-001, orderId=ORD-001, amount=120000
eventId=evt-002, orderId=ORD-002, amount=250000
eventId=evt-003, orderId=ORD-003, amount=80000
~~~

Có thể dùng producer Java hoặc console producer để chuẩn bị dữ liệu. Trong suốt một lượt thử, không tái tạo topic hoặc xóa offset group; cần giữ lại trạng thái để so sánh trước và sau crash.

Ví dụ gửi JSON có key bằng console producer:

~~~bash
kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created \
  --property parse.key=true \
  --property key.separator=:
~~~

Nhập từng record:

~~~text
ORD-001:{"eventId":"evt-001","orderId":"ORD-001","amount":120000}
ORD-002:{"eventId":"evt-002","orderId":"ORD-002","amount":250000}
ORD-003:{"eventId":"evt-003","orderId":"ORD-003","amount":80000}
~~~

Một transaction có thể chứa nhiều record từ nhiều partition. Nếu một record trong batch không deserialize hoặc transform được và ứng dụng abort transaction, toàn bộ output của batch bị abort và offsets của batch không tiến. Khi replay, các record đã xử lý thành công trước đó trong cùng batch cũng được xử lý lại; đây là hành vi nguyên tử cần tính đến khi thiết kế batch và poison-record handling.

## 5. Cấu hình Maven và producer/consumer

Ví dụ dependency Kafka client trong pom.xml:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-clients</artifactId>
    <version>3.9.1</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.18.2</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
    <version>2.18.2</version>
</dependency>
~~~

Chọn Kafka client tương thích với cluster và dependency management của ứng dụng. Ví dụ sử dụng JSON string để tập trung vào transaction semantics.

Producer properties:

~~~java
Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "payments-eos-worker-0");
producerProps.put(ProducerConfig.ACKS_CONFIG, "all");
producerProps.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
producerProps.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, "60000");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
~~~

Consumer properties:

~~~java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "payments-eos-lab");
consumerProps.put(ConsumerConfig.CLIENT_ID_CONFIG, "payments-eos-consumer-0");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
consumerProps.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "20");
~~~

Với producer transactional, transactional.id là bắt buộc. Transaction timeout phải nằm trong giới hạn transaction.max.timeout.ms của broker. Tổng thời gian xử lý batch phải nằm trong transaction timeout và max.poll.interval.ms; nếu không, transaction có thể timeout hoặc consumer bị rebalance trước khi gửi offset. Không dùng cùng transactional.id cho nhiều instance đồng thời. Consumer auto commit phải tắt; input offsets được gửi bằng producer transaction.

## 6. Mã xử lý transactional

Ví dụ event:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amount
) {}

public record PaymentProcessed(
        String eventId,
        String orderId,
        long amount,
        String status
) {}
~~~

Đặt các class event, ExactlyOnceWorker, CrashInjector và EosApplication trong cùng package lab, ví dụ com.example.eos, hoặc thêm import/package tương ứng khi tách file.

Hàm xử lý batch:

~~~java
public final class ExactlyOnceWorker implements AutoCloseable {
    private static final String INPUT_TOPIC = "orders.created";
    private static final String OUTPUT_TOPIC = "payments.processed";

    private final KafkaConsumer<String, String> consumer;
    private final KafkaProducer<String, String> producer;
    private final ObjectMapper mapper;
    private final String crashAt;

    public ExactlyOnceWorker(Properties consumerProps, Properties producerProps,
                             String crashAt) {
        this.consumer = new KafkaConsumer<>(consumerProps);
        this.producer = new KafkaProducer<>(producerProps);
        this.mapper = new ObjectMapper().registerModule(new JavaTimeModule());
        this.crashAt = crashAt == null ? "" : crashAt;
        this.producer.initTransactions();
        this.consumer.subscribe(List.of(INPUT_TOPIC));
    }

    public void runBatch() throws Exception {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofSeconds(2));

        if (records.isEmpty()) {
            return;
        }
        CrashInjector.crashIfRequested(crashAt, "AFTER_POLL");

        Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();
        producer.beginTransaction();
        CrashInjector.crashIfRequested(crashAt, "AFTER_BEGIN");

        try {
            for (ConsumerRecord<String, String> record : records) {
                OrderCreated input =
                        mapper.readValue(record.value(), OrderCreated.class);
                PaymentProcessed output = new PaymentProcessed(
                        input.eventId(),
                        input.orderId(),
                        input.amount(),
                        "ACCEPTED");

                String outputJson = mapper.writeValueAsString(output);
                ProducerRecord<String, String> outputRecord =
                        new ProducerRecord<>(OUTPUT_TOPIC, input.orderId(), outputJson);

                producer.send(outputRecord).get();

                TopicPartition partition =
                        new TopicPartition(record.topic(), record.partition());
                offsets.put(partition,
                        new OffsetAndMetadata(record.offset() + 1));
            }

            CrashInjector.crashIfRequested(crashAt, "AFTER_OUTPUT_ACK");
            producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
            CrashInjector.crashIfRequested(crashAt, "AFTER_OFFSETS_SENT");
        } catch (Exception exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            try {
                producer.abortTransaction();
            } catch (KafkaException abortFailure) {
                exception.addSuppressed(abortFailure);
            }
            throw exception;
        }

        // A commit exception can leave the outcome unknown to this process.
        // Close/restart with the same transactional.id and inspect Kafka state.
        producer.commitTransaction();
        CrashInjector.crashIfRequested(crashAt, "AFTER_COMMIT");
    }

    @Override
    public void close() {
        consumer.close(Duration.ofSeconds(10));
        producer.close(Duration.ofSeconds(10));
    }
}
~~~

Các import cần có:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import java.time.Duration;
import java.util.*;
~~~

Đây là skeleton cho một batch lab. Ứng dụng thực tế cần vòng poll liên tục, shutdown có kiểm soát, xử lý rebalance, giới hạn thời gian xử lý batch và phân loại lỗi producer. Nếu lỗi là fatal như ProducerFencedException hoặc InvalidProducerEpochException, dừng worker và tạo lại producer theo lifecycle phù hợp; không tiếp tục dùng producer đã bị fence.

Offset map ở ví dụ lưu offset mới nhất đã xử lý cho mỗi partition. Vòng lặp đang xử lý tuần tự nên các offset trong partition được hoàn tất theo thứ tự. Nếu chuyển sang xử lý song song, chỉ đưa next offset liên tục cao nhất đã hoàn tất vào map; không lấy đơn giản offset lớn nhất nếu còn record trước đó chưa xong.

## 7. Khởi tạo transactional producer và fencing

Gọi initTransactions() trước khi bắt đầu gửi transactional record. Lệnh này đăng ký producer với transaction coordinator, lấy producer ID/epoch và hoàn tất việc xử lý transaction cũ còn dang dở của cùng transactional.id khi producer mới khởi tạo.

Nếu một worker mới khởi động với cùng transactional.id trong khi worker cũ vẫn chạy:

- Worker mới nhận epoch mới.
- Worker cũ bị fence.
- Các thao tác transaction tiếp theo của worker cũ có thể thất bại với ProducerFencedException hoặc lỗi epoch tương ứng.
- Worker cũ phải dừng; không được bắt lỗi rồi tiếp tục xử lý batch như thể vẫn sở hữu transactional.id.

Trong triển khai nhiều instance, cấp transactional.id theo logical shard/partition worker có tính ổn định. Ví dụ worker shard 0 luôn dùng payments-eos-worker-0 khi restart, shard 1 dùng payments-eos-worker-1. Không dùng một chuỗi chung cho tất cả replica.

## 8. Các điểm crash cần kiểm tra

Đặt fault injection tại các điểm sau. Mỗi lần thử nên dùng một tập input có eventId riêng hoặc reset lab theo quy trình để kết quả dễ đối chiếu.

| Điểm crash | Thời điểm | Trạng thái transaction | Kết quả mong đợi sau recovery |
|---|---|---|---|
| P0 | Sau poll, trước beginTransaction | Chưa có transaction output | Input chưa commit; consumer đọc lại |
| P1 | Sau beginTransaction, trước send output | Transaction đang mở, chưa có output | Transaction được abort/timeout; input đọc lại |
| P2 | Sau khi output send được broker ack, trước sendOffsetsToTransaction | Output đã append nhưng transaction chưa commit | Output không hiện với read_committed; input đọc lại |
| P3 | Sau sendOffsetsToTransaction, trước commitTransaction | Output và offsets nằm trong transaction chưa commit | Cả output và offset cùng abort; input đọc lại |
| P4 | Sau commitTransaction trả về thành công | Transaction đã commit | Output visible và input offset đã tiến; restart không xử lý lại input đã commit |
| P5 | Commit request đã gửi nhưng client chưa nhận response | Kết quả phía client chưa rõ | Sau restart, kiểm tra trạng thái transaction; không tự kết luận commit thất bại |

P2 và P3 là hai điểm quan trọng nhất để chứng minh output và input offset được xử lý nguyên tử. P5 mô phỏng kết quả commit không rõ với client; có thể tạo bằng cách ngắt kết nối/kill process đúng lúc commit đang diễn ra. Không thể chỉ dựa vào exception phía client để biết transaction đã commit hay abort. Nếu commitTransaction ném timeout hoặc mất kết nối, không gọi abortTransaction một cách mù quáng và không phát lại batch bằng một transactional.id mới. Hãy đóng producer, khởi động lại cùng transactional.id, để initTransactions phục hồi trạng thái cũ, rồi đối chiếu output read_committed với committed offset.

## 9. Thêm crash hook cho bài lab

Chỉ dùng crash hook trong cluster lab. Runtime.halt dừng JVM ngay lập tức và bỏ qua shutdown hook, close producer, close consumer hoặc flush ứng dụng. Đây là cách mô phỏng process crash rõ hơn System.exit, vốn có thể chạy shutdown hook.

~~~java
public final class CrashInjector {
    private CrashInjector() {}

    public static void crashIfRequested(String configuredPoint,
                                        String currentPoint) {
        if (currentPoint.equalsIgnoreCase(configuredPoint)) {
            System.err.println("CRASH_INJECTED point=" + currentPoint);
            Runtime.getRuntime().halt(137);
        }
    }
}
~~~

Đặt hook vào luồng giao dịch:

~~~java
producer.beginTransaction();
CrashInjector.crashIfRequested(crashAt, "AFTER_BEGIN");

for (ConsumerRecord<String, String> record : records) {
    // Deserialize, transform and send output.
    producer.send(outputRecord).get();
}
CrashInjector.crashIfRequested(crashAt, "AFTER_OUTPUT_ACK");

producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
CrashInjector.crashIfRequested(crashAt, "AFTER_OFFSETS_SENT");

producer.commitTransaction();
CrashInjector.crashIfRequested(crashAt, "AFTER_COMMIT");
~~~

Để mô phỏng P5, cần gây lỗi mạng hoặc dừng tiến trình trong lúc commitTransaction đang chờ phản hồi. Nếu hook chỉ chạy sau khi commitTransaction trả về, đó là P4 (commit đã được xác nhận), không phải P5. Sau P5, trạng thái phải được xác minh từ phía Kafka bằng read_committed output và group offset.

Ví dụ khởi chạy worker lặp qua các batch:

~~~java
package com.example.eos;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public final class EosApplication {
    public static void main(String[] args) throws Exception {
        Properties consumerProps = buildConsumerProperties();
        Properties producerProps = buildProducerProperties();
        String crashAt = System.getenv("CRASH_AT");

        try (ExactlyOnceWorker worker =
                     new ExactlyOnceWorker(consumerProps, producerProps, crashAt)) {
            while (true) {
                worker.runBatch();
            }
        }
    }

    private static Properties buildConsumerProperties() {
        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "payments-eos-lab");
        properties.put(ConsumerConfig.CLIENT_ID_CONFIG, "payments-eos-consumer-0");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        properties.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, "20");
        return properties;
    }

    private static Properties buildProducerProperties() {
        Properties properties = new Properties();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
                "payments-eos-worker-0");
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
        properties.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, "60000");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class.getName());
        return properties;
    }
}
~~~

Đây là ứng dụng lab có thể build cùng các class event, worker và CrashInjector ở trên. Trong ứng dụng thật, vòng lặp cần xử lý shutdown, rebalance và backoff khi poll không có record. Chạy không đặt CRASH_AT để xử lý bình thường; mỗi giá trị CRASH_AT chỉ nên dùng cho một lần chạy thử.

Chạy một worker với biến môi trường CRASH_AT tương ứng:

~~~powershell
$env:CRASH_AT = "AFTER_OUTPUT_ACK"
mvn org.codehaus.mojo:exec-maven-plugin:3.5.0:java "-Dexec.mainClass=com.example.eos.EosApplication"
~~~

Sau khi process dừng với exit code 137, xóa biến CRASH_AT rồi khởi động lại đúng logical worker với cùng transactional.id. Không đổi group ID hoặc transactional.id giữa lần chạy lỗi và lần phục hồi.

~~~powershell
Remove-Item Env:CRASH_AT
mvn org.codehaus.mojo:exec-maven-plugin:3.5.0:java "-Dexec.mainClass=com.example.eos.EosApplication"
~~~

## 10. Vì sao phải dùng cùng transactional.id khi restart?

Khi process chết giữa transaction, transaction coordinator có thể còn thấy transaction đang mở. Lần khởi tạo producer mới bằng cùng transactional.id sẽ nhận epoch mới, fence producer session cũ và giúp coordinator phục hồi transaction trước đó theo trạng thái đã ghi.

Nếu restart bằng một transactional.id hoàn toàn mới, producer mới không đại diện cho cùng logical producer session. Nó không fence producer cũ theo ID cũ; transaction cũ vẫn được giải quyết theo transaction timeout và recovery của coordinator. Điều này làm bài thử khó xác định và không mô phỏng đúng vòng đời một shard producer.

Sau khi producer mới initTransactions thành công, worker tạo transaction mới và consumer tiếp tục đọc từ committed offset. Nếu transaction cũ bị abort, input record được đọc lại. Nếu transaction cũ đã commit, input offset đã tiến và record đó không được xử lý lại trong group.

## 11. Đọc output bằng read_committed và read_uncommitted

Đây là bước quan sát quan trọng. Consumer read_committed chỉ thấy record thuộc transaction đã commit; consumer read_uncommitted có thể nhìn thấy record transactional chưa commit hoặc đã abort, tùy vị trí đọc và trạng thái log.

Đọc output với read_committed:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic payments.processed \
  --from-beginning \
  --consumer-property isolation.level=read_committed \
  --property print.key=true \
  --property print.offset=true
~~~

Đọc output với read_uncommitted:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic payments.processed \
  --from-beginning \
  --consumer-property isolation.level=read_uncommitted \
  --property print.key=true \
  --property print.offset=true
~~~

Sau crash P2/P3, record output có thể đã được append vật lý vào log nhưng transaction bị abort khi phục hồi. Consumer read_uncommitted có thể nhìn thấy record aborted; read_committed không trả record đó. Offset của record đã append không được tái sử dụng, vì vậy log có thể có khoảng trống offset.

Read_committed dùng Last Stable Offset (LSO) làm ranh giới đọc an toàn. Một transaction đang mở ở đầu log có thể làm consumer read_committed chưa đọc được các record phía sau LSO, kể cả record non-transactional đã append sau đó. Khi transaction được commit hoặc abort, LSO có thể tiến lên.

Vì vậy, sau crash P2/P3, nếu producer cũ chết nhưng transaction chưa được coordinator giải quyết, consumer read_committed có thể tạm thời chờ ở LSO. Khởi động lại cùng transactional.id để initTransactions fence producer cũ và hoàn tất recovery, hoặc chờ transaction timeout của broker; sau đó mới kết luận record aborted không visible. Read_uncommitted có thể thấy record ngay cả khi transaction chưa được hoàn tất.

Đừng so sánh số dòng console output với offset liên tục. Aborted record và control record có thể tạo khoảng trống offset; điều cần so sánh là tập eventId visible và trạng thái input offset.

Exactly-once không tự loại bỏ các input event trùng đã tồn tại ở topic nguồn. Nếu cùng eventId được producer/upstream ghi thành hai record ở hai offset khác nhau, consumer transaction sẽ xử lý cả hai offset một cách nguyên tử. Muốn deduplicate theo nghiệp vụ, vẫn cần eventId ổn định và state/inbox dedup riêng.

## 12. Ma trận kết quả mong đợi

Giả sử một input event evt-101 tạo một output event evt-101:

| Kịch bản | Output read_committed | Output read_uncommitted | Input committed offset |
|---|---|---|---|
| Crash trước khi gửi output | Không có output | Không có output | Không tiến qua input event |
| Crash sau output ack, trước commit | Không thấy output aborted | Có thể thấy output aborted | Không tiến qua input event |
| Crash sau sendOffsetsToTransaction, trước commit | Không thấy output aborted | Có thể thấy output aborted | Không tiến qua input event |
| Commit thành công rồi crash | Có đúng một output đã commit | Có output đã commit | Đã tiến qua input event |
| Commit response bị mất, transaction thực tế commit | Có output đã commit | Có output đã commit | Đã tiến qua input event |
| Commit response bị mất, transaction thực tế abort | Không có output đã commit | Có thể thấy output aborted | Không tiến qua input event |

Sau mỗi lần crash, hãy restart worker cùng transactional.id, chờ recovery và xử lý đến khi input group lag về 0. Tập output visible với read_committed phải có đúng một kết quả đã commit cho mỗi input event được xử lý thành công trong test. Record aborted có thể còn nhìn thấy với read_uncommitted, nhưng không được tính là output nghiệp vụ đã commit.

## 13. Đối chiếu offset của consumer group

Kiểm tra committed offset trước và sau từng kịch bản:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group payments-eos-lab
~~~

Ghi lại:

- Current offset của từng input partition.
- Log end offset.
- Consumer lag.
- EventId cuối cùng đã xử lý thành công.
- Output eventId quan sát được bằng read_committed.

Sau P2/P3, offset group không được tiến qua batch chưa commit. Sau recovery, worker đọc lại batch đó và commit output + offsets cùng nhau. Sau P4, offset group đã tiến; worker restart không được phát sinh output thứ hai cho input đã commit.

Không dùng kafka-consumer-groups --reset-offsets giữa một lần thử nếu mục tiêu là xác minh recovery tự nhiên. Reset offset tạo một kịch bản replay thủ công khác và có thể làm sai kết luận.

## 14. So sánh với at-least-once không có transaction

Chạy một baseline đơn giản: consumer đọc input, producer gửi output không transactional, rồi consumer commit offset bằng commitSync. Nếu process chết sau khi output đã được ack nhưng trước commit offset, input sẽ được đọc lại và output có thể được ghi lần hai.

| Đặc điểm | At-least-once thủ công | Kafka transaction consume-transform-produce |
|---|---|---|
| Output send | Độc lập với offset commit | Nằm trong transaction |
| Input offset | Commit riêng | Gửi vào transaction |
| Crash sau output trước offset | Có thể tạo output trùng | Transaction abort; output không visible với read_committed |
| Crash sau commit | Output và offset có thể lệch nếu thao tác không nguyên tử | Output và offset cùng commit |
| Consumer output | Thường đọc record đã ghi | Cần read_committed để loại output aborted |
| Phạm vi | Tùy cách commit và idempotency ứng dụng | Kafka-to-Kafka atomicity; không bao gồm DB/HTTP |

Idempotent producer đơn lẻ không đủ cho EOS consume-transform-produce. Nó ngăn một số duplicate do retry protocol của producer, nhưng không nhóm output record với input offset. Cần transactional.id, beginTransaction, sendOffsetsToTransaction và commitTransaction.

## 15. Kiểm tra fencing và producer zombie

Thử nghiệm hai process:

1. Khởi động worker A với transactional.id payments-eos-worker-0.
2. Giữ worker A chạy và xử lý transaction.
3. Khởi động worker B với cùng transactional.id.
4. Quan sát worker B gọi initTransactions và nhận epoch mới.
5. Worker A thực hiện send/commit tiếp theo và bị fence.
6. Xác nhận chỉ worker B tiếp tục sở hữu transactional.id.

Kết quả mong đợi:

- Worker A không thể tiếp tục commit transaction bằng epoch cũ.
- Transaction chưa hoàn tất của A được coordinator phục hồi theo trạng thái commit/abort.
- Worker B tiếp tục từ committed offset của consumer group.
- Không có hai producer đồng thời hợp lệ cùng ghi dưới một transactional.id.

Không chạy thử nghiệm này bằng hai process trên topic nghiệp vụ. Đây là bài lab có chủ đích làm producer cũ mất quyền hoạt động.

## 16. Giới hạn exactly-once với database và dịch vụ ngoài

Kafka transaction chỉ nhóm các record Kafka và consumer offsets được gửi vào transaction. Giả sử worker vừa ghi output Kafka vừa cập nhật database:

1. Database commit thành công.
2. Kafka transaction abort hoặc process crash trước commit.
3. Input được đọc lại.
4. Database side effect có thể chạy lần hai.

Kafka không thể rollback transaction database chỉ bằng abortTransaction. Để bảo vệ side effect ngoài Kafka, dùng một trong các mẫu:

| Mẫu | Cách hoạt động |
|---|---|
| Inbox/idempotency key | Lưu eventId trong cùng transaction database với cập nhật nghiệp vụ; replay bị bỏ qua |
| Outbox | Ghi thay đổi nghiệp vụ và outbox row trong cùng database transaction; relay phát outbox sang Kafka |
| Transactional integration | Dùng transaction manager phối hợp nếu hệ thống thực sự hỗ trợ cùng một transaction boundary |
| Reconciliation | Đối chiếu trạng thái Kafka và hệ thống đích, sửa sai lệch theo quy trình có kiểm soát |

Không tuyên bố một ứng dụng đạt exactly-once end-to-end chỉ vì producer dùng transactional.id. Cần nêu rõ phạm vi: Kafka input offsets và Kafka output records, hay cả side effect database/HTTP.

## 17. Kafka Streams và exactly-once v2

Kafka Streams có thể quản lý transaction cho input offsets, output records và state store changelog. Cấu hình processing guarantee:

~~~java
Properties streamsProps = new Properties();
streamsProps.put(StreamsConfig.APPLICATION_ID_CONFIG, "payments-streams-eos");
streamsProps.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
streamsProps.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG,
        StreamsConfig.EXACTLY_ONCE_V2);
~~~

Với exactly-once v2, Kafka Streams điều phối transaction và offset cho topology. Ứng dụng vẫn cần kiểm tra các side effect ngoài Kafka, state store retention, throughput và transaction timeout. Không thêm thao tác database không transactional vào processor rồi giả định Kafka Streams tự đưa nó vào transaction.

## 18. Các lỗi và tình huống cần nhận biết

| Lỗi/hiện tượng | Ý nghĩa | Hành động |
|---|---|---|
| ProducerFencedException | Producer session cũ bị transactional.id epoch mới fence | Dừng producer cũ; không retry bằng instance đã bị fence |
| InvalidProducerEpochException | Epoch không còn hợp lệ | Khởi tạo producer mới theo lifecycle đúng |
| Transaction timed out | Transaction vượt transaction.timeout.ms hoặc coordinator không thể hoàn tất | Điều tra batch duration, broker và transaction coordinator |
| Commit timeout / mất response | Client không biết chắc kết quả commit | Restart cùng transactional.id và xác minh output/offset từ Kafka |
| Consumer không thấy output | Output có thể aborted hoặc consumer đang ở read_committed trước LSO | Kiểm tra transaction status/recovery và LSO behavior |
| Consumer read_uncommitted thấy record không có ở read_committed | Record thuộc transaction aborted hoặc chưa commit | Không tính record đó là output nghiệp vụ đã commit |
| Consumer group offset không tiến | Transaction abort hoặc sendOffsetsToTransaction chưa commit | Kiểm tra lỗi transaction, group metadata và rebalance |
| LSO không tiến | Transaction mở lâu hoặc transaction coordinator chưa hoàn tất | Tìm producer transaction bị treo, timeout và coordinator log |
| Hai instance liên tục fence nhau | Dùng chung transactional.id không đúng cách | Cấp transactional.id duy nhất cho từng logical shard |

## 19. Quan sát và metrics

Trong mỗi lần thử, thu thập:

- Số transaction bắt đầu, commit và abort.
- Transaction duration và commit latency.
- Producer send error, retry, timeout và fencing exception.
- Input group committed offset theo partition.
- Input consumer lag.
- Output eventId visible với read_committed.
- Output eventId visible với read_uncommitted.
- Thời gian từ process restart đến khi transaction recovery hoàn tất.
- Trạng thái LSO nếu có công cụ/metric broker phù hợp.

Log ứng dụng nên chứa transaction attempt ID, transactional.id (không chứa credential), eventId, input topic/partition/offset, output topic/partition/offset và crash point. Điều này giúp nối một lần input với transaction output và offset commit.

Không dùng số record read_uncommitted làm số lượng kết quả nghiệp vụ. Với transaction abort, record có thể tồn tại trong log nhưng không được xem là committed output.

## 20. Quy trình chạy lab đầy đủ

1. Tạo hai topic input/output và một consumer group riêng; kiểm tra internal topic replication phù hợp với cluster.
2. Gửi 10 input event có eventId duy nhất, ghi lại offset.
3. Chạy worker với transactional.id ổn định và CRASH_AT=AFTER_OUTPUT_ACK.
4. Xác nhận process dừng đột ngột.
5. Đọc output bằng read_uncommitted để quan sát record đã append; ghi nhận nếu read_committed đang chờ LSO.
6. Xóa CRASH_AT và restart cùng transactional.id để initTransactions phục hồi transaction cũ; không reset offset.
7. Sau khi recovery hoàn tất, đọc output bằng read_committed và read_uncommitted; ghi lại khác biệt.
8. Kiểm tra input group offset chưa tiến qua batch bị abort.
9. Chờ worker xử lý xong và consumer lag về 0; xác nhận mỗi input event có một output committed.
10. Lặp lại với AFTER_OFFSETS_SENT và AFTER_COMMIT.
11. Chạy hai worker cùng transactional.id để quan sát fencing.
12. Chạy baseline at-least-once để so sánh duplicate khi crash sau output trước offset commit.
13. Lưu bảng kết quả và phân loại record aborted, committed, replayed và duplicate.

## 21. Biểu mẫu ghi kết quả

| Lần chạy | Crash point | Input offset trước | Output read_committed | Output read_uncommitted | Input offset sau recovery | Kết luận |
|---|---|---:|---|---|---:|---|
| 1 | AFTER_OUTPUT_ACK | 0 |  |  |  |  |
| 2 | AFTER_OFFSETS_SENT |  |  |  |  |  |
| 3 | AFTER_COMMIT |  |  |  |  |  |
| 4 | Commit response bị mất |  |  |  |  |  |

Khi điền bảng, dùng eventId làm khóa đối chiếu. Không chỉ đếm record vì một input có thể tạo nhiều output hợp lệ trong các bài toán thực tế; với bài lab này, quy tắc là một input event tạo một output event.

## 22. Tiêu chí hoàn thành

- Giải thích được vì sao output và input offset phải nằm trong cùng Kafka transaction.
- Cấu hình transactional.id ổn định và gọi initTransactions trước khi gửi.
- Dùng beginTransaction, send output, sendOffsetsToTransaction và commitTransaction đúng thứ tự.
- Tắt auto commit và không commit offset độc lập trong luồng EOS.
- Dùng read_committed để xác định output đã commit.
- Giải thích vì sao read_uncommitted có thể thấy record aborted.
- Thử crash sau output ack và trước commit; chứng minh input được replay nhưng output aborted không visible với read_committed.
- Thử crash sau commit; chứng minh offset và output đã commit cùng nhau.
- Nhận biết ProducerFencedException và xử lý producer zombie.
- Nêu rõ exactly-once Kafka-to-Kafka không bao gồm side effect database/HTTP.

## 23. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| transactional.id | Định danh logical producer qua restart và hỗ trợ fencing/recovery |
| initTransactions | Đăng ký producer epoch và xử lý transaction cũ |
| beginTransaction | Bắt đầu nhóm thao tác nguyên tử |
| send | Ghi output transactional |
| sendOffsetsToTransaction | Gộp input offsets vào transaction |
| commitTransaction | Làm output và offsets cùng có hiệu lực |
| abortTransaction | Hủy output và offset của transaction chưa commit |
| read_committed | Chỉ đọc output transactional đã commit |
| read_uncommitted | Có thể thấy record aborted/chưa commit |
| Producer fencing | Ngăn producer cũ tiếp tục ghi bằng epoch đã lỗi thời |

Thử nghiệm crash chỉ chứng minh exactly-once khi kiểm tra đồng thời output visibility và input committed offset. Với Kafka transaction, crash trước commit làm transaction abort và input được replay; commit thành công làm output cùng offset có hiệu lực. Kết quả này áp dụng cho luồng Kafka-to-Kafka. Mọi side effect ngoài Kafka vẫn cần transaction hoặc idempotency riêng.
