# Topic và partition trong logging ứng dụng message (Java/Kafka)

## 1. Mục tiêu bài học

Trong ứng dụng xử lý message, một dòng log như “đã nhận message” thường **không đủ để điều tra lỗi**. Khi nhiều producer/consumer chạy đồng thời, cùng một loại message có thể đến từ nhiều topic, partition và consumer group; một record cũng có thể được xử lý lại sau retry, restart hoặc rebalance.

**Topic và partition** là ngữ cảnh rất quan trọng khi logging ứng dụng message, đặc biệt với **Apache Kafka**. Ghi đúng metadata giúp xác định: message thuộc luồng nào, nằm ở partition nào, offset bao nhiêu, đã được broker xác nhận hay consumer xử lý tới đâu, và vì sao cùng một record xuất hiện nhiều lần trong log.

Bài này dùng Kafka làm ví dụ chính vì Kafka có khái niệm **topic, partition và offset** rõ ràng. Các hệ thống như RabbitMQ, JMS hay SQS có các mô hình queue/topic, delivery tag, message ID và acknowledgement riêng; **không được áp đặt quy tắc offset/partition của Kafka cho mọi broker**.

Sau bài học, bạn sẽ:
- Phân biệt `topic`, `partition`, `offset`, message key, consumer group và message/trace ID.
- Hiểu **thứ tự trong một partition**, các giới hạn khi phân tích log đa partition và tác động của retry/rebalance.
- Biết event nào cần ghi ở producer, consumer, quá trình xử lý, commit và dead-letter topic (DLT).
- Viết ví dụ Java 17+ tạo log có metadata được kiểm soát **mà không làm lộ message payload**.
- Tích hợp metadata từ Kafka Producer/Consumer API và biết các lỗi thường gặp với offset commit.
- Thiết kế field logging, metrics, tracing, security và test có thể dùng trong môi trường production.

## 2. Topic, partition và offset là gì?

### 2.1. Topic là luồng logic

Một **Kafka topic** là tên luồng bản ghi, ví dụ `orders.events`, `payments.status` hoặc `inventory.updated`. Producer ghi record vào một topic; consumer đăng ký đọc topic đó. Một topic có thể chia thành nhiều partition để mở rộng lưu trữ và xử lý.

`Topic` không nhất thiết trùng với tên nghiệp vụ trong payload. Một topic có thể chứa nhiều loại event, được phân biệt bằng schema/type/headers của ứng dụng. Vì vậy một sự kiện log có thể có cả:
- `topic=orders.events` — tên đích Kafka;
- `event_type=order_created` — loại message trong ứng dụng;
- `event=message_processed` — hành động mà chương trình đang ghi log.

Ba trường này **không đồng nghĩa**. Dùng tên riêng rõ ràng sẽ tránh nhầm “Kafka event” với “event log”.

### 2.2. Partition là log con của topic

Một topic có thể có nhiều partition độc lập. Mỗi partition giữ một chuỗi record có thứ tự theo offset:

```text
Topic: orders.events

Partition 0: [offset 7] -> [offset 8] -> [offset 9] ...
Partition 1: [offset 2] -> [offset 3] -> [offset 4] ...
Partition 2: [offset 5] -> [offset 6] -> [offset 7] ...
```

Cùng offset `7` có thể tồn tại ở nhiều partition. Do đó **chỉ ghi `offset=7` là thiếu ngữ cảnh**. Một record Kafka được định vị trong luồng bằng bộ ba:

```text
(topic, partition, offset)
```

Ví dụ `(orders.events, 0, 7)` khác `(orders.events, 2, 7)`. Khi phân tích log consumer, cần thêm `group_id` và `client_id` để biết **ai đang xử lý** record đó. Cùng một record có thể được nhiều consumer group khác nhau đọc, nên group không phải thành phần bắt buộc của địa chỉ record nhưng rất quan trọng cho chẩn đoán.

### 2.3. Offset là vị trí trong partition

`Offset` là vị trí của record trong một partition Kafka, không phải ID nghiệp vụ và không phải số đếm toàn topic. Offset của record được broker gán theo log partition; producer thường biết offset chính xác sau khi nhận metadata từ callback/Future khi send hoàn tất thành công.

Không diễn giải sai:
- Offset **không** là thứ tự toàn cục giữa các partition.
- Offset **không** nói message đã xử lý thành công ở ứng dụng.
- Offset **không** cho biết consumer nào đọc record, vì nhiều group có thể đọc.
- Offset tăng không có nghĩa các bản ghi đều còn tồn tại hoặc đều hiển thị: retention, compaction, transaction visibility có thể làm vị trí quan sát bị khuyết.
- `offset_b - offset_a` **không luôn bằng số message ứng dụng đã xử lý**, đặc biệt nếu có gap hoặc một số record không được consumer trả về.

Với Kafka consumer, **committed offset** thông thường biểu diễn **vị trí kế tiếp sẽ đọc**, không phải offset của record cuối vừa xử lý. Nếu hoàn tất record offset `7` và muốn bắt đầu từ `8` khi phục hồi, commit giá trị `8` cho partition đó (với điều kiện các offset trước nó trong luồng xử lý đã hoàn tất theo chính sách).

## 3. Thứ tự chỉ có phạm vi từng partition

Kafka giữ thứ tự append trong **mỗi partition**. Điều này hữu ích khi các message liên quan cùng một entity (ví dụ một order) cần xử lý theo thứ tự. Tuy nhiên:
- Không có **thứ tự tổng quát** giữa partition 0 và partition 1.
- Log từ hai consumer hoặc hai thread có thể xen kẽ theo thời gian ghi vào sink.
- Một consumer có thể nhận records có thứ tự theo partition nhưng ứng dụng xử lý song song rồi hoàn thành **khác thứ tự**.
- Retry, delay, DLT, read-committed isolation hoặc việc tăng số partition có thể làm điều kiện nghiệp vụ về thứ tự phức tạp hơn.

Ví dụ hai dòng xuất hiện theo thứ tự thời gian trong collector:

```text
INFO event=message_processed topic=orders.events partition=1 offset=2
INFO event=message_processed topic=orders.events partition=0 offset=7
```

Bạn **không thể suy ra** record ở partition 1 xảy ra “trước trong toàn bộ topic” chỉ vì dòng log được collector nhận trước. Muốn lần theo một entity, cần routing/partition key nhất quán hoặc một ID nghiệp vụ/correlation ID an toàn.

### 3.1. Key và lựa chọn partition

Producer có thể cung cấp `key`. Khi dùng partitioner phù hợp, records có cùng key thường được đưa về cùng partition, giúp xử lý theo thứ tự tương đối **nếu** số partition/partitioner, định dạng key và cơ chế xử lý được duy trì phù hợp.

Không nên tuyên bố “mọi record cùng key mãi ở một partition”:
- Tăng số partition có thể thay đổi cách phân phối key cho record mới.
- Custom partitioner có thể có quy tắc khác.
- Key null, explicit partition hoặc producer version/config khác có thể làm phân phối khác.
- Ứng dụng consumer xử lý song song không giữ thứ tự hoàn tất nếu không điều phối.

Với log, thường **không cần in raw key**. Key có thể là email, user ID, số tài khoản, số điện thoại hoặc chuỗi nhạy cảm. Khi cần correlate, dùng một correlation ID server-generated hoặc pseudonym được thiết kế theo chính sách; hash không tự đồng nghĩa ẩn danh.

## 4. Consumer group, assignment và rebalance

Kafka consumer group dùng `group.id` để nhiều consumer phối hợp xử lý các partition của topic đã đăng ký. Trong cách hoạt động thông thường, **mỗi partition được gán cho tối đa một member tại một thời điểm trong cùng group**, giúp phân phối công việc. Một group khác có thể độc lập đọc toàn bộ các partition.

Ví dụ:

```text
Topic orders.events: P0, P1, P2

Group orders-workers:
  Consumer A -> P0, P1
  Consumer B -> P2

Group analytics-workers:
  Consumer C -> P0, P1, P2
```

Khi A/B thay đổi số lượng, bị lỗi hoặc có thay đổi về metadata/topic, Kafka có thể **rebalance** và gán partition cho member khác. Vì vậy cùng `topic, partition, offset` có thể được ghi trong log của các `client_id`/instance khác nhau sau retry hoặc rebalance.

Cần phân biệt:
- `consumer_group`: nhóm độc lập xử lý/commit offset.
- `client_id`: định danh một Kafka client dùng cho chẩn đoán/metrics; không nhất thiết là định danh duy nhất vĩnh viễn.
- `instance_id` hoặc hostname/pod ID: giúp biết tiến trình nào xử lý khi scale/restart; phải theo policy riêng tư.
- `member_id`: định danh membership của Kafka, có thể đổi khi rebalance.
- `generation`/assignment epoch: hữu ích khi điều tra fencing và rebalance nhưng thường cần API/cấu hình cụ thể.

**Nên log sự kiện assignment/revocation** một cách gọn: tên group, số partition được giao/thu hồi, lý do/điểm kết thúc khi có thể. Không log nguyên object lớn hoặc toàn bộ cấu hình/credential Kafka.

Một hệ thống có thể xảy ra xử lý lại record sau khi consumer xử lý nghiệp vụ thành công nhưng **chưa commit** offset. Đây là một đặc điểm của at-least-once, không phải tự động là broker tạo record mới. Dùng `(topic, partition, offset, group)` để điều tra lần xử lý lặp và xác minh tính **idempotent** của nghiệp vụ.

## 5. Thiết kế schema logging theo message

Đề xuất field cho một event xử lý message (chọn theo nhu cầu, không phải tất cả đều bắt buộc):

| Field | Ví dụ | Ý nghĩa/chú ý |
| --- | --- | --- |
| `event` | `message_received`, `message_processed`, `message_failed` | **Giai đoạn xử lý**, tránh dùng message type thay thế |
| `messaging_system` | `kafka` | Phân biệt hệ thống broker |
| `topic` | `orders.events` | Tên luồng; không dùng topic chứa PII nếu có thể |
| `partition` | `0` | Chỉ số partition theo broker |
| `offset` | `7` | Vị trí record **trong partition này** |
| `consumer_group` | `orders-workers` | Group xử lý, quan trọng khi debug duplicate |
| `client_id`/`instance_id` | `orders-worker-2` | Instance cụ thể; có thể đổi khi restart |
| `message_type` | `order_created` | Loại event nghiệp vụ |
| `trace_id`/`correlation_id` | `trace_01` | Kết nối producer, consumer và trace |
| `result` | `OK`, `RETRYABLE`, `FAILED` | Kết quả của **giai đoạn cụ thể** |
| `attempt` | `2` | Số lần xử lý **do ứng dụng theo dõi**, không suy từ offset |
| `error_type` | `VALIDATION_ERROR` | Loại lỗi ổn định, không chứa bí mật |
| `duration_ms` | `13` | Thời gian xử lý, dùng clock đơn điệu |
| `next_commit_offset` | `8` | Giá trị định commit **sau khi đã xử lý đủ điều kiện** |

Các field này giúp tách ba trạng thái:
1. **Received**: consumer đã lấy record từ poll; chưa hẳn đã xử lý thành công.
2. **Processed**: code xử lý nghiệp vụ đã hoàn tất theo định nghĩa ứng dụng.
3. **Committed**: consumer đã commit vị trí kế tiếp cho group (nếu commit thành công).

Không dùng cùng event name `message_success` cho mọi giai đoạn vì dễ hiểu nhầm. Một producer callback thành công chỉ cho thấy kết quả send/ack tương ứng, **không bảo đảm business consumer đã xử lý**.

### 5.1. Dạng text và JSON

Text ngắn gọn:

```text
INFO event=message_processed topic=orders.events partition=0 offset=7 group=orders-workers result=OK trace_id=trace_01
```

Structured JSON (ví dụ):

```json
{
  "event": "message_processed",
  "messaging_system": "kafka",
  "topic": "orders.events",
  "partition": 0,
  "offset": 7,
  "consumer_group": "orders-workers",
  "result": "OK",
  "trace_id": "trace_01"
}
```

Dùng JSON encoder thực, không tự nối chuỗi từ raw headers/payload. Khi ghi `topic` hoặc `trace_id` từ dữ liệu ngoài, cần validate/escape đúng format; không tin các chuỗi chứa CR/LF, control characters hoặc quá dài.

## 6. Ví dụ Java 17+ độc lập: ghi log topic/partition/offset mà không lộ payload

Ví dụ này dùng **JDK thuần và JUL** để minh họa cách thiết kế event; **không kết nối Kafka thực**. Ta giả lập metadata record từ hai partition; một record xử lý thất bại cần retry. Mục tiêu: log metadata an toàn, phân biệt outcome và chứng minh không in payload.

Tạo file **`TopicPartitionLogDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class TopicPartitionLogDemo {
    record Message(String topic, int partition, long offset,
                   String traceId, String payload) {}

    enum Outcome { OK, RETRYABLE }

    static String format(Message m, Outcome outcome) {
        if (!"orders.events".equals(m.topic())
                || m.partition() < 0 || m.offset() < 0) {
            throw new IllegalArgumentException(
                    "Invalid record metadata");
        }

        String trace = m.traceId() != null
                && m.traceId().matches("[A-Za-z0-9_-]{1,32}")
                ? m.traceId() : "invalid";

        return "event=" + (outcome == Outcome.OK
                    ? "message_processed" : "message_failed")
                + " topic=" + m.topic()
                + " partition=" + m.partition()
                + " offset=" + m.offset()
                + " group=orders-worker"
                + " outcome=" + outcome
                + " trace_id=" + trace;
    }

    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        List<String> entries = new ArrayList<>();
        Handler capture = new Handler() {
            @Override
            public void publish(LogRecord r) {
                if (isLoggable(r)) {
                    entries.add(r.getMessage());
                    System.out.println(r.getLevel().getName()
                            + " " + r.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        log.addHandler(capture);

        try {
            log.info(format(new Message(
                    "orders.events", 0, 7, "trace_01",
                    "password=FAKE_SECRET"), Outcome.OK));
            log.info(format(new Message(
                    "orders.events", 1, 2, "trace_02",
                    "token=FAKE_SECRET"), Outcome.OK));
            log.warning(format(new Message(
                    "orders.events", 0, 8, "trace_03",
                    "email=private@example.invalid"),
                    Outcome.RETRYABLE));

            if (entries.size() != 3
                    || entries.stream().anyMatch(x ->
                        x.contains("FAKE_SECRET")
                        || x.contains("private@")
                        || x.contains("password")
                        || x.contains("token="))) {
                throw new AssertionError("Unsafe event");
            }

            System.out.println("captured=" + entries.size());
            System.out.println("payload_leaked=false");
        } finally {
            log.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac TopicPartitionLogDemo.java
java TopicPartitionLogDemo
```

**Standard output xác định:**

```text
INFO event=message_processed topic=orders.events partition=0 offset=7 group=orders-worker outcome=OK trace_id=trace_01
INFO event=message_processed topic=orders.events partition=1 offset=2 group=orders-worker outcome=OK trace_id=trace_02
WARNING event=message_failed topic=orders.events partition=0 offset=8 group=orders-worker outcome=RETRYABLE trace_id=trace_03
captured=3
payload_leaked=false
```

Giải thích:
- Hai partition có offset **khác nhau và độc lập**; dòng log có `partition=1 offset=2` xen giữa hai event của partition 0 không tạo thành một thứ tự toàn cục.
- `format` chọn topic được phép, kiểm tra partition/offset không âm và chỉ nhận trace ID theo tập ký tự/độ dài hạn chế.
- `payload` có các chuỗi giả nhạy cảm nhưng **không bao giờ được đưa vào message log**; kiểm tra cuối chương trình xác nhận không lộ.
- `Outcome.RETRYABLE` dẫn đến `event=message_failed` ở mức WARNING; đoạn minh họa **chưa thực hiện retry, DLT hay offset commit**.
- JUL logger và handler cục bộ phục vụ test; `finally` tháo handler, không làm thay đổi root logger của toàn JVM.

Lưu ý: `payload` và `traceId` ở đây được định nghĩa cho demo; trong production nên log event fields dưới dạng structured logging với schema/encoder thay vì chuỗi nối bằng tay. Không coi việc regex cho phép một trace ID là chứng nhận “không PII”; ID nên được sinh theo thiết kế riêng tư và xác minh nguồn.

## 7. Kafka Producer: ghi đúng topic/partition/offset sau send

Với Kafka Java client, một `ProducerRecord<K,V>` chứa topic, key, value và có thể có partition chỉ định. Metadata sau send thành công được trả về qua callback/Future dạng `RecordMetadata`, bao gồm `topic()`, `partition()` và `offset()`.

Một cách tích hợp với **SLF4J + Kafka Client** (đây là đoạn mã rút gọn, không phải file chạy độc lập; `producer`, `orderId`, `serializedEvent` và `LOG` đã được khởi tạo):

```java
import org.apache.kafka.clients.producer.ProducerRecord;

// Đoạn tích hợp trong hàm gửi event, Kafka Producer và LOG đã tồn tại.
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.events", orderId, serializedEvent);

try {
    producer.send(record, (metadata, error) -> {
        if (error != null) {
            LOG.error(
                "event=message_send_failed topic={} error_type={}",
                record.topic(),
                error.getClass().getSimpleName());
            return;
        }

        LOG.info(
            "event=message_send_succeeded topic={} "
            + "partition={} offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset());
    });
} catch (RuntimeException error) {
    LOG.error("event=message_send_rejected topic={} error_type={}",
            record.topic(), error.getClass().getSimpleName());
    throw error;
}
```

Ý nghĩa:
1. Trước `send`, producer biết topic và có thể biết key; nếu không chỉ định partition, **không tự phỏng đoán** partition/offset từ key. Partition có thể phụ thuộc partitioner, metadata hoặc cấu hình client.
2. `send(...)` là bất đồng bộ; callback `error == null` cung cấp broker/producer result tương ứng. Ghi `send_requested` ở thời điểm gọi được, nhưng **không gọi đó là “đã lưu thành công”**.
3. Nếu send bị lỗi đồng bộ hoặc callback có lỗi, log event lỗi với topic và error type; tránh in payload/credential.
4. `acks`/idempotence/retries quyết định bảo đảm của producer; callback thành công không có nghĩa consumer downstream đã xử lý.
5. `RecordMetadata.offset()` là offset trong partition của record đã gửi, không phải offset consumer đã commit.

**Quyền riêng tư:** `serializedEvent` có thể chứa PII, còn `orderId` dùng làm key có thể là định danh cá nhân. **Không log raw key/value** trong callback chỉ để debug; dùng metadata và correlation ID đã được phê duyệt.

Một request nghiệp vụ có thể gửi nhiều record đến các topic khác nhau. Cần nối chúng qua `trace_id`/`correlation_id` hoặc application event ID, **không dùng offset làm transaction ID toàn hệ thống**.

## 8. Kafka Consumer: ghi lúc nhận, xử lý và commit khác nhau

Kafka `ConsumerRecord<K,V>` cung cấp:
- `topic()`: topic nhận record.
- `partition()`: partition.
- `offset()`: vị trí của record trong partition.
- `key()` và `value()`: payload/key, có thể nhạy cảm.
- `headers()`: metadata bổ sung, có thể chứa trace context hoặc dữ liệu do producer đưa vào, không nên dump toàn bộ.
- `timestamp()`: timestamp gắn trên record theo loại timestamp; không đồng nghĩa thời điểm consumer xử lý.

Ví dụ **đoạn tích hợp** dùng Kafka client, SLF4J và handler nghiệp vụ giả định:

```java
import java.time.Duration;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;

// consumer, LOG và processMessage đã được định nghĩa trong ứng dụng.
ConsumerRecords<String, byte[]> records =
        consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, byte[]> record : records) {
    LOG.debug(
        "event=message_received topic={} partition={} offset={}",
        record.topic(), record.partition(), record.offset());

    long started = System.nanoTime();
    try {
        processMessage(record.value()); // Nghiệp vụ thực tế.
        long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

        LOG.info(
            "event=message_processed topic={} partition={} "
            + "offset={} duration_ms={}",
            record.topic(), record.partition(),
            record.offset(), durationMs);

        // Chỉ đánh dấu offset hoàn thành khi nghiệp vụ thành công.
        // Chiến lược commit nằm ngoài đoạn mã rút gọn này.
    } catch (Exception error) {
        LOG.warn(
            "event=message_failed topic={} partition={} "
            + "offset={} error_type={}",
            record.topic(), record.partition(), record.offset(),
            error.getClass().getSimpleName());

        // Phải áp dụng chính sách retry/pause/seek/DLT phù hợp.
        // Không commit vượt qua record thất bại.
        throw error;
    }
}
```

Đây **không phải vòng lặp consumer đầy đủ**: còn thiếu khởi tạo client, đăng ký group, chính sách commit, lifecycle, rebalance và xử lý lỗi thực tế. Điểm cần học là:
- `poll()` nhận record không chứng minh business handler thành công.
- `message_processed` chỉ nên ghi **sau khi** hàm xử lý hoàn tất theo contract.
- Nếu xử lý lỗi, log `message_failed` kèm topic/partition/offset để có thể tìm record gây lỗi.
- Nếu handler chạy side effect bất đồng bộ, **chưa thể tuyên bố processed** chỉ vì đã gửi task vào executor.
- Khi catch rồi retry, phải phân biệt lỗi retryable và non-retryable theo policy; không tự coi mọi lỗi là retryable.

### 8.1. Manual commit: “offset kế tiếp” và điều kiện an toàn

Nếu consumer **tự commit offset** (`enable.auto.commit=false`), sau khi xử lý an toàn record `offset=7` ở `partition=0`, giá trị commit để resume từ record tiếp theo thường là `8`.

Với Kafka Java client, một đoạn **minh họa** cho đúng một partition đã xử lý liên tục đến offset `7`:

```java
import java.util.Map;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

// Chỉ hợp lệ khi tất cả records trước vị trí tiếp theo
// đã hoàn tất theo contract xử lý và consumer sở hữu assignment.
TopicPartition tp = new TopicPartition("orders.events", 0);
consumer.commitSync(Map.of(tp, new OffsetAndMetadata(8L)));
```

**Không** sao chép `8L` cố định vào ứng dụng thật. Thông thường tính `record.offset() + 1` từ offset cuối đã xử lý an toàn, **theo từng TopicPartition**, không commit vị trí cao nhất đã đọc khi có record trước đó chưa xử lý.

Ví dụ sai: lấy batch offsets 7, 8, 9 ở partition 0; record 8 lỗi, record 9 thành công; commit 10 sẽ làm consumer group có thể bỏ qua offset 8 khi khởi động lại. Cần giữ *contiguous processed frontier* theo partition, hoặc dừng/pause/seek/retry đúng chiến lược. Với concurrency hoặc rebalances, offset tracking còn phải xử lý các record đang chạy và partition revocation.

**Auto commit** có thể commit vị trí được poll theo lịch mà không đợi side effect ứng dụng hoàn tất, tùy cách xử lý; không coi “committed” là “downstream đã hoàn toàn xử lý”. Để thiết kế at-least-once, exactly-once hoặc transactional processing phải đánh giá toàn bộ đường dữ liệu, không suy ra chỉ từ log commit.

### 8.2. Khi nào log commit?

Có thể phân biệt:
- `commit_attempted`: code bắt đầu gửi commit.
- `commit_succeeded`: Kafka client xác nhận commit thành công cho group.
- `commit_failed`: lỗi commit, cần xem tình trạng assignment/rebalance.

Một log `commit_succeeded topic=... partition=... next_offset=8` cho biết vị trí group được lưu; nó **không phải** event rằng business side effect ở database chắc chắn bền vững, trừ khi ứng dụng đã xây hợp đồng và thứ tự commit phù hợp.

## 9. Rebalance và việc “cùng record xử lý hai lần”

Rebalance xảy ra khi membership/assignment thay đổi. Kafka Java client có `ConsumerRebalanceListener` với callback phù hợp để ứng dụng phản ứng khi partition được revoke/assign.

Ví dụ **đoạn tích hợp** (Kafka Java client + SLF4J, không phải chương trình hoàn chỉnh):

```java
consumer.subscribe(
    java.util.List.of("orders.events"),
    new org.apache.kafka.clients.consumer.ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                java.util.Collection<
                    org.apache.kafka.common.TopicPartition> partitions) {
            LOG.info(
                "event=partitions_revoked group={} count={}",
                "orders-workers", partitions.size());

            // Dừng/đợi work của các partition bị thu hồi,
            // commit frontier đã hoàn tất nếu còn hợp lệ,
            // và giải phóng state liên quan theo thiết kế.
        }

        @Override
        public void onPartitionsAssigned(
                java.util.Collection<
                    org.apache.kafka.common.TopicPartition> partitions) {
            LOG.info(
                "event=partitions_assigned group={} count={}",
                "orders-workers", partitions.size());
        }
    });
```

Các callback có contract khác nhau theo protocol/assignor; trong cooperative rebalance có thể chỉ một **tập con** partition bị revoke. Không viết logic giả định mọi rebalance đều thu hồi toàn bộ partition. Nếu cần log từng partition được gán, tạo field structured với giới hạn số lượng/độ dài hoặc event cho từng assignment, tránh in nguyên object cấu hình khổng lồ.

Cùng một bộ ba `(topic, partition, offset)` có thể xuất hiện trong log của hai consumer instances ở thời điểm khác nhau vì:
- Consumer A xử lý nhưng chết trước commit; consumer B đọc lại sau rebalance.
- Commit lỗi, hoặc consumer reset/seek vị trí.
- Ứng dụng retry một record tại cùng offset mà chưa tiến vị trí.
- Một consumer group khác độc lập đọc cùng record.

Không quy mọi trường hợp thành **duplicate broker record**. Phân biệt **record Kafka giống nhau được xử lý lại** với **producer gửi hai bản ghi khác nhau** (offset khác nhau, có thể cùng business event ID).

## 10. Retry và dead-letter topic: liên kết thế nào?

Một message lỗi có thể được:
- Retry tại cùng partition/offset trước khi tiến tiếp.
- Tạm dừng partition (`pause`), xử lý retry có backoff, rồi resume.
- Chuyển sang retry topic hoặc dead-letter topic (DLT) theo framework/policy.
- Bỏ hoặc đánh dấu lỗi nghiệp vụ khi đã có cơ chế audit chấp thuận.

Khi chuyển sang **topic khác**, record mới có **topic/partition/offset mới**. Do đó không thể nối record gốc và record DLT chỉ bằng offset.

Ví dụ event:

```text
WARN event=message_failed topic=orders.events partition=0 offset=8 error_type=VALIDATION_ERROR trace_id=trace_03
INFO event=message_routed_to_dlt source_topic=orders.events source_partition=0 source_offset=8 dlt_topic=orders.events.dlt trace_id=trace_03
INFO event=message_received topic=orders.events.dlt partition=1 offset=52 trace_id=trace_03
```

Đây là ví dụ dữ liệu, không phải Kafka thực chạy. Lưu ý **DLT send phải thành công rồi mới log “routed”**; nếu chưa được broker xác nhận, event phải là `dlt_send_requested` hoặc `dlt_send_failed`. Với hệ thống đòi hỏi độ tin cậy cao, xét atomicity giữa xử lý/commit/send DLT hoặc mô hình transactional/outbox phù hợp.

Một attempt count nên thuộc **state do ứng dụng quản lý** hoặc metadata rõ ràng của framework; Kafka offset **không phải** số lần retry. Một số API mới có metadata liên quan delivery count trong các ngữ cảnh riêng, nhưng không mặc định mọi record có counter và đừng suy giá trị retry từ offset gap.

## 11. Metrics, consumer lag và cardinality

Access log trên mọi message rất hữu ích để điều tra, nhưng hệ thống nhiều partition cũng có thể tạo rất nhiều event. Đừng biến **offset** thành label của metrics/histogram: đó là giá trị thay đổi liên tục, gây nổ cardinality.

Nên phân tách:

| Thông tin | Nên là log field? | Nên là metric label? |
| --- | --- | --- |
| `topic` | Có nếu cần | Có khi tập topic được kiểm soát |
| `partition` | Có khi điều tra | Có thể, nếu số partition hợp lý; lưu ý cardinality |
| `offset` | Có khi lần theo record | **Không**, thường quá nhiều giá trị |
| `consumer_group` | Có | Có nếu tập group hữu hạn |
| `trace_id`, `message_id` | Có theo policy | **Không** làm label phổ thông |
| `error_type` | Có | Có khi enum hữu hạn |
| `duration_ms` | Có ở event xử lý | Là observation/histogram, không dùng raw duration làm label |

### Consumer lag

Khái niệm thường dùng theo một partition của một group:

```text
consumer_lag ~= log_end_offset - committed_next_offset
```

Ví dụ nếu log end offset là 110 và group đã commit next offset 108, lag là khoảng 2 positions. Cần phân biệt `logEndOffset` với high watermark/last stable offset theo isolation và công cụ đo; ở một số tình huống retention/transaction, chênh lệch offset không bằng đúng số bản ghi hiển thị hoặc số business event còn chờ xử lý.

Lag tăng có thể xuất phát từ:
- Producer tạo record nhanh hơn consumer xử lý.
- Một partition nóng vì key phân bố lệch.
- Consumer dừng vì retry/backoff hoặc chờ I/O.
- Rebalance liên tục hoặc poll loop bị chặn.
- Commit bị trễ, nên lag dựa trên committed offset lớn dù ứng dụng đã xử lý tiến xa hơn.

**Lag gần 0 không chứng minh nghiệp vụ hoàn toàn thành công** nếu code tự động commit trước khi side effect hoàn tất. Cần kết hợp metric processed/error, commit success, retries, DLT, processing latency và queue/backpressure.

### Giảm log volume

Ở prod, thường không cần INFO cho từng message thành công khi throughput rất cao. Có thể:
- Log aggregate/metrics cho success, giữ WARN/ERROR có ngữ cảnh theo policy.
- Sample success logs theo tỷ lệ/thời gian có kiểm soát, nhưng giữ failure/audit cần thiết.
- Gắn MDC ở phạm vi xử lý để log nghiệp vụ quan trọng vẫn có topic/partition/offset.
- Giới hạn sampling/drop và theo dõi số sự kiện bị bỏ. Không để việc sampling gây hiểu sai số lỗi tuyệt đối.

## 12. Tracing và MDC: gắn ngữ cảnh đúng thời điểm

Trong Java, SLF4J MDC hoặc Log4j ThreadContext có thể giúp mọi application log trong đoạn xử lý message mang các trường:
`topic`, `partition`, `offset`, `consumer_group`, `trace_id`.

Ví dụ tích hợp **SLF4J MDC**:

```java
// Trong phạm vi xử lý một ConsumerRecord có thật.
java.util.Map<String, String> old =
        org.slf4j.MDC.getCopyOfContextMap();

try {
    org.slf4j.MDC.put("kafka.topic", record.topic());
    org.slf4j.MDC.put("kafka.partition",
                      Integer.toString(record.partition()));
    org.slf4j.MDC.put("kafka.offset",
                      Long.toString(record.offset()));

    processMessage(record.value());
} finally {
    if (old == null) {
        org.slf4j.MDC.clear();
    } else {
        org.slf4j.MDC.setContextMap(old);
    }
}
```

Đây là đoạn tích hợp cần SLF4J provider và `record`/`processMessage` được định nghĩa; việc copy/restore context giúp tránh làm bẩn MDC của message tiếp theo trên thread được tái sử dụng. Không đưa raw key/payload, Authorization, toàn bộ headers hoặc dữ liệu cá nhân vào MDC.

Nếu xử lý message trên thread khác, worker pool hoặc virtual thread, **MDC không tự nhiên luôn được truyền qua**; cần cơ chế context propagation được framework/bộ thư viện hỗ trợ. Với Kafka client, `ConsumerRecord`/KafkaConsumer không được chia sẻ bừa giữa nhiều thread; lấy snapshot metadata bất biến khi dispatch task.

**OpenTelemetry** có các semantic convention cho messaging. Những trường như `messaging.destination.name`, `messaging.destination.partition.id`, `messaging.consumer.group.name` và `kafka.offset` có thể được gắn vào span theo phiên bản conventions; không nhất thiết tất cả là field log tự động. Nên map log schema nội bộ sang trace attributes một cách có kiểm soát, và lưu ý một số conventions còn ở trạng thái Development, có thể đổi tên/semantics theo version.

### Trace context qua message headers

Trace context thường được inject vào headers bởi producer và extract bởi consumer. Nhưng headers là dữ liệu đầu vào có thể đến từ nguồn khác; đừng copy tất cả ra log. Chỉ chấp nhận các header cần thiết, xác minh định dạng/kích thước, dùng OpenTelemetry propagator theo chuẩn; trace ID **không phải** authorization token.

Trong môi trường có nhiều async hops hoặc DLT/retry topic, liên kết các spans bằng context/links phù hợp. Không suy từ một trace ID rằng consumer đã commit thành công; đó là một event/metric riêng.

## 13. Bảo mật logging ở topic/partition

Metadata có vẻ vô hại nhưng vẫn cần review:
- **Topic name** có thể tiết lộ tên nghiệp vụ, tenant hoặc môi trường. Nếu topic được tạo động từ email/tenant ID, tên topic có thể chứa PII.
- **Key** rất hay là user ID, email, số tài khoản; không ghi raw key.
- **Value/payload** có thể chứa token, đơn hàng, thông tin thanh toán, hồ sơ cá nhân; không dump toàn bộ kể cả khi xử lý lỗi.
- **Headers** có thể chứa trace context, routing info và cả secret. Chỉ ghi allowlist cụ thể.
- **Consumer group/client ID** có thể chứa hostname hoặc tenant; kiểm tra sensitivity và lượng giá trị.
- **Exception message/stack trace** có thể lộ nội dung record hoặc cấu hình; review cách khởi tạo exception và formatter.

Khi cần định danh tương quan ngoài offset, tạo `message_id`/`correlation_id` tại nguồn với thiết kế riêng tư. Hash raw key không mặc nhiên biến nó thành anonymous, đặc biệt khi key có không gian nhỏ dễ dò; dùng pseudonymization có quản lý nếu cần.

### Log injection

Topic, header, error message, key hay một metadata do client chi phối có thể chứa ký tự điều khiển, xuống dòng hoặc text dài. Nếu xây plain-text log bằng nối chuỗi từ chúng, attacker có thể tạo dòng log giả.

Phòng vệ:
1. Chỉ ghi các field được duyệt, ưu tiên tên topic/config do hệ thống kiểm soát.
2. Validate độ dài, charset và kiểu của trace/message ID.
3. Dùng structured JSON encoder có escaping đúng; không ghép JSON thủ công từ raw input.
4. Giới hạn số lượng headers/fields và kích thước event.
5. Test CR/LF, Unicode, quote, long payload và secret giả tại collector, không chỉ tại call site.

Ví dụ Java mục 6 chỉ nhận topic `orders.events` và trace ID theo tập ký tự/độ dài; payload không được đưa vào `format`. Đây là **mô hình allowlist minh họa**, không phải bộ lọc mọi dạng dữ liệu nhạy cảm.

## 14. Kiểm thử topic/partition logging

### 14.1. Unit test schema

Với hàm dựng event riêng:
- Đầu vào `topic=orders.events, partition=0, offset=7` tạo đúng ba field và type.
- Cùng offset `7` ở partition 0 và partition 1 phải được coi là **hai record khác nhau**.
- Partition âm, offset âm và topic không thuộc tập hợp cho phép bị từ chối hoặc map an toàn theo contract.
- Trace ID chứa CR/LF hoặc quá dài bị loại/chuẩn hóa.
- Payload có token/email giả không xuất hiện trong event.
- Message failure dùng event name và level riêng, không có thông điệp khẳng định đã xử lý xong.

### 14.2. Integration test Kafka thật

Dùng test broker/Testcontainers hoặc cluster test riêng, producer/consumer thật:
1. Gửi records vào topic có ít nhất hai partition, chỉ định key/partition theo test setup.
2. Lấy `RecordMetadata.topic/partition/offset` từ producer callback, xác minh Kafka thật trả metadata.
3. Consumer lấy `ConsumerRecord.topic/partition/offset`, kiểm tra event `message_received` và `message_processed` khớp.
4. Tạo lỗi xử lý có kiểm soát, xác minh không commit vượt qua offset chưa hoàn tất.
5. Test restart và rebalance: instance khác đọc lại record nếu chưa commit; kiểm tra idempotency.
6. Gửi vào DLT/retry topic, xác minh metadata **mới** và liên kết với source bằng correlation ID.
7. Cố ý set trace ID chứa newline/secret giả; xác minh không bị in trong log, MDC hoặc collector.
8. Đo lag và xác nhận nghĩa của committed *next offset*.
9. Thử async logging queue/drop/backpressure; phân biệt lỗi logging với lỗi Kafka.
10. Tắt/bật process/collector, kiểm tra flush và hành vi khi log còn trong RAM.

Không dùng broker production hoặc dữ liệu khách hàng thật để test các trường hợp này.

### 14.3. Đọc log khi có sự cố

Tình huống: khách hàng nói order event được xử lý hai lần.
- Tìm theo application event ID/correlation ID an toàn.
- Nhóm logs theo `topic + partition + offset + consumer_group`.
- Nếu **cùng bộ ba** xuất hiện hai lần trong cùng group, xem retry, consumer restart, commit failure, rebalance và idempotency.
- Nếu **offset khác** nhưng cùng business ID, xem producer send retry/duplicate event, outbox/transaction và nghiệp vụ tạo message nhiều lần.
- So `message_received`, `message_processed`, `commit_succeeded`, không dựa một dòng duy nhất.
- Nếu record rơi vào DLT, truy về source metadata và trạng thái send/commit; không coi việc DLT có record là đã xử lý nghiệp vụ thành công.

## 15. Lỗi thường gặp

| Hiện tượng/sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Chỉ log `offset=7` | Offset lặp giữa topic/partition | Log đủ `topic, partition, offset` |
| Sắp xếp offset giữa partition để đo global order | Không có offset toàn cục | So thứ tự **trong từng partition** |
| Gọi `send()` rồi log “published” ngay | Kafka send thường async | Log requested; success ở callback/Future |
| Log `message_received` như processed | Poll chưa hoàn tất nghiệp vụ | Có event processed riêng sau thành công |
| Commit offset lớn nhất trong batch dù có lỗi | Có thể bỏ record chưa xử lý | Commit frontier liên tục đã hoàn tất theo partition |
| Coi commit là DB transaction success | Commit Kafka không tự bảo đảm side effect bên ngoài | Thiết kế thứ tự, idempotency/transaction |
| Coi duplicate log là Kafka record duplicate | Retry/rebalance/các group có thể đọc lại | Nhóm theo triple + group/instance |
| Cho rằng same key luôn ở same partition bất biến | Partitioner/count/topic có thể đổi | Ràng buộc routing và test khi scale |
| Ghi raw payload/key/headers để debug | Rủi ro PII, secret, log injection | Log metadata + event ID allowlisted |
| Dùng offset làm metric label | Cardinality tăng không kiểm soát | Offset ở log, không là label phổ thông |
| Dùng lag=0 để kết luận nghiệp vụ OK | Auto commit có thể chạy trước processing | Kết hợp metrics processing, retries, DLT |
| Không cleanup MDC sau record | Ngữ cảnh lẫn giữa các request/messages | Restore/clear trong `finally` |
| Log quá nhiều success events | Tăng chi phí và backlog | Aggregate/metrics/sampling phù hợp |
| Không log rebalance | Khó điều tra đổi ownership partition | Log assigned/revoked và lifecycle |
| Copy offset cũ sang DLT như offset mới | DLT có topic/partition/offset mới | Log source location và DLT metadata tách biệt |

## 16. Checklist triển khai production

- [ ] Mọi event consumer quan trọng có `topic, partition, offset`; có `group_id` khi cần debug reprocess.
- [ ] Phân biệt `send_requested`, `send_succeeded`, `received`, `processed`, `failed`, `commit_succeeded`.
- [ ] Ghi producer metadata **sau khi ACK/callback thành công**, không suy partition/offset trước.
- [ ] Commit “next offset” đúng **sau khi** record trước đó hoàn tất; không bỏ qua failed gaps.
- [ ] Có chính sách idempotency/retry/DLT và event giúp đối chiếu nguồn với đích.
- [ ] Log assignment/revocation/rebalance có scope rõ; không coi instance ID là định danh record.
- [ ] Không log raw payload/key/headers hoặc exception chứa secret; dùng correlation ID được duyệt.
- [ ] Validate trace/message ID, encode structured output và test log injection.
- [ ] Không dùng offset/trace ID làm metric label; giám sát processing lag và Kafka lag riêng.
- [ ] Có test producer/consumer thật, multi-partition, restart/rebalance và recovery.
- [ ] Đánh giá logging throughput, async queue, retry storms và lưu trữ/retention/collector.
- [ ] Liên kết access/application logs với trace context khi có thể, nhưng giữ nguồn thông tin độc lập.

## 17. Bài tập

1. Chạy `TopicPartitionLogDemo`. Giải thích vì sao `partition=1 offset=2` không thể đặt trước/sau `partition=0 offset=7` theo thứ tự toàn cục.
2. Thêm event `message_received` cho record offset 8 rồi cho xử lý lỗi; kiểm tra không phát `message_processed` khi lỗi.
3. Cho topic không hợp lệ, offset âm hoặc trace ID chứa `\n`; xem contract validate của hàm `format`.
4. Giả lập record trùng `(orders.events,0,7)` được xử lý lại trong cùng consumer group; thiết kế log có `attempt` và giải thích vì sao cần idempotency.
5. Với Kafka Producer thật, ghi `send_requested` trước `send` và `send_succeeded` trong callback. Khi gửi lỗi, loại bỏ nội dung message khỏi log.
6. Trong consumer test, xử lý offsets 7 OK, 8 lỗi, 9 OK. Xác định vì sao không commit 10 và cách giữ frontier liên tục.
7. Tạo một retry/DLT topic trong môi trường test, kiểm tra offset mới và cách nối với source location.
8. Tạo dashboard theo topic/group/error type; giữ offset trong log nhưng không dùng làm label metrics.
9. Thử consumer group rebalance, ghi assigned/revoked; tìm cách cùng record bị đọc lại mà không cần có producer gửi record mới.
10. Kiểm tra MDC sau hai record được xử lý trên cùng thread: context record thứ nhất có bị rò sang record thứ hai không?

## 18. Ghi nhớ

- **Topic** là luồng logic; **partition** là log con; **offset** là vị trí chỉ có ý nghĩa trong partition. Bộ ba `(topic, partition, offset)` là mốc đối chiếu record Kafka.
- Kafka giữ thứ tự trong **mỗi partition**, không có thứ tự chung giữa mọi partition; app xử lý song song còn có thể hoàn tất khác thứ tự.
- **Producer ACK, consumer poll, business processing và offset commit** là bốn mốc khác nhau; nên ghi event với tên riêng.
- Cùng record được đọc/xử lý lại sau retry/rebalance không nhất thiết là broker có bản ghi duplicate; so triple, group và business ID.
- Offset được commit thông thường là **next offset**; không commit vượt qua xử lý thất bại.
- Log metadata an toàn, không dump key/value/headers, đừng dùng offset làm high-cardinality metric label.
- Quan sát được cả per-partition lag, rebalance, retries, DLT và đường đi của trace mà không lộ payload.

### Tài liệu tham khảo

- Apache Kafka — *Design* (topic/partition, offsets, replication): https://kafka.apache.org/documentation/#design
- Apache Kafka Java Client — `ConsumerRecord`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html
- Apache Kafka Java Client — `KafkaConsumer`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
- Apache Kafka Java Client — `RecordMetadata`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/producer/RecordMetadata.html
- Apache Kafka Java Client — `ConsumerRebalanceListener`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.html
- Apache Kafka Java Client — `OffsetAndMetadata`: https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/OffsetAndMetadata.html
- OpenTelemetry — *Messaging semantic conventions, Kafka*: https://opentelemetry.io/docs/specs/semconv/messaging/kafka/
- OWASP — *Logging Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
