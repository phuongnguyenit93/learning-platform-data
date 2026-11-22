# At-most-once, at-least-once và exactly-once

## Mục tiêu bài học

Khi consumer đọc một record, thực hiện xử lý rồi commit offset, lỗi có thể xảy ra ở bất kỳ thời điểm nào giữa các bước. Nếu ứng dụng commit quá sớm, record có thể bị bỏ qua; nếu commit quá muộn, record có thể được xử lý lại. Kafka cung cấp các cơ chế để lựa chọn giữa at-most-once, at-least-once và exactly-once trong những phạm vi nhất định.

Sau bài học, bạn có thể:

- Phân biệt ba ngữ nghĩa xử lý và đánh đổi giữa mất dữ liệu với xử lý trùng.
- Giải thích các cửa sổ lỗi giữa đọc record, thực hiện side effect và commit offset.
- Cấu hình consumer Java để đạt at-most-once hoặc at-least-once.
- Thiết kế consumer idempotent bằng event ID, inbox/deduplication và transaction database.
- Giải thích producer idempotence khác Kafka transaction như thế nào.
- Dùng Kafka transaction để ghi output và commit input offset một cách nguyên tử.
- Hiểu giới hạn của exactly-once khi side effect nằm ngoài Kafka.
- Chọn semantics phù hợp cho từng loại nghiệp vụ và kiểm thử khi process crash.

## 1. Processing semantics là gì?

Processing semantics mô tả số lần một sự kiện có thể tạo ra hiệu quả xử lý được quan sát trong hệ thống khi có retry, crash, timeout hoặc restart. Ba cách diễn đạt phổ biến là:

- **At-most-once:** một record được xử lý không quá một lần; đổi lại, record có thể bị mất khỏi luồng xử lý nếu lỗi xảy ra đúng thời điểm.
- **At-least-once:** record được xử lý một hoặc nhiều lần cho đến khi thành công; đổi lại, side effect có thể bị lặp.
- **Exactly-once:** trong một phạm vi được xác định, kết quả xử lý được ghi nhận đúng một lần dù có retry hoặc crash.

Không có một công tắc duy nhất khiến toàn bộ hệ thống phân tán trở thành exactly-once. Cần xác định rõ phạm vi: từ producer đến Kafka, từ Kafka qua một consumer group, giữa các topic Kafka hay từ Kafka sang database/HTTP service.

### 1.1. Phân biệt delivery với processing

Producer delivery semantics nói về việc record được broker nhận và xác nhận ra sao. Consumer processing semantics nói về quan hệ giữa việc xử lý record và việc lưu tiến độ đọc.

Ví dụ:

- `acks=all` yêu cầu broker xác nhận ghi theo trạng thái ISR và cấu hình min ISR.
- Producer idempotence giúp loại bỏ duplicate do retry của cùng producer sequence trong phạm vi Kafka hỗ trợ.
- Consumer commit offset sau khi xử lý quyết định record có thể được đọc lại sau restart hay không.
- Kafka transaction có thể kết hợp ghi output Kafka với commit input offset.

Một producer ghi record đáng tin cậy không tự bảo đảm consumer chỉ thực hiện side effect một lần. Ngược lại, consumer idempotent có thể làm cho việc xử lý lặp không gây tác động nghiệp vụ lặp, dù record vẫn được giao nhiều lần.

### 1.2. Offset commit là mốc tiến độ, không phải xác nhận side effect

Committed offset của một topic-partition thường là offset kế tiếp consumer cần đọc. Khi consumer commit offset 25, group sẽ tiếp tục từ 25 ở lần đọc sau nếu offset còn hợp lệ.

Kafka không tự biết database đã cập nhật, email đã gửi hay HTTP request đã thành công. Offset commit và side effect bên ngoài là hai thao tác riêng, trừ khi ứng dụng phối hợp chúng bằng một transaction phù hợp.

## 2. Cửa sổ lỗi giữa xử lý và commit

Một luồng consumer cơ bản gồm:

```text
poll record
    |
    v
process business logic
    |
    v
write side effect (database/API)
    |
    v
commit consumer offset
```

Nếu process crash giữa các bước, kết quả phụ thuộc vào thời điểm commit.

### 2.1. Crash trước khi xử lý

Consumer đã poll record nhưng process crash trước khi side effect hoàn tất và trước khi commit offset. Khi member khởi động lại, group tiếp tục từ committed offset cũ nên record được đọc lại.

Đọc lại là điều mong đợi với at-least-once. Ứng dụng cần chịu được trường hợp record được giao nhiều lần.

### 2.2. Crash sau side effect nhưng trước commit

Consumer đã cập nhật database thành công nhưng crash trước khi commit offset. Sau restart, Kafka vẫn thấy offset cũ và giao lại record. Nếu consumer thực hiện database update lần nữa mà không deduplicate, side effect có thể bị lặp.

Đây là cửa sổ duplicate điển hình của at-least-once.

### 2.3. Crash sau commit nhưng trước side effect

Nếu consumer commit offset trước khi thực hiện side effect, rồi process crash, Kafka coi record đã được xử lý và không giao lại cho group. Side effect chưa xảy ra nên dữ liệu bị bỏ qua.

Đây là rủi ro điển hình của at-most-once.

### 2.4. Bảng so sánh cửa sổ lỗi

| Thứ tự thao tác | Nếu crash ở giữa | Hệ quả có thể xảy ra |
|---|---|---|
| Commit offset rồi mới xử lý | Sau commit, trước side effect | Record bị bỏ qua; at-most-once |
| Xử lý side effect rồi mới commit | Sau side effect, trước commit | Record được giao lại; có thể duplicate; at-least-once |
| Ghi output Kafka và commit input offset trong cùng Kafka transaction | Transaction chưa commit | Cả output và offset transaction đều không được công bố như một transaction đã commit |
| Cập nhật database và commit Kafka offset bằng hai thao tác độc lập | Crash giữa hai hệ thống | Có thể duplicate hoặc mất tiến độ tùy thứ tự; cần inbox/outbox hoặc transaction phối hợp |

## 3. At-most-once

### 3.1. Nguyên tắc

At-most-once ưu tiên tránh xử lý trùng. Consumer commit offset trước khi thực hiện side effect. Nếu side effect thất bại sau commit, record sẽ không được group đọc lại theo offset đó.

```text
poll record
    |
    v
commit offset
    |
    v
process record
    |
    v
side effect thành công hoặc thất bại
```

Nếu process crash sau commit, record có thể bị mất khỏi luồng xử lý. Vì vậy at-most-once chỉ phù hợp khi mất một số event có thể chấp nhận được hoặc khi side effect không quan trọng bằng việc tránh lặp.

### 3.2. Ví dụ Java với commit trước khi xử lý

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "metrics-live-view");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("telemetry"));

    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        // Commit vị trí sau batch trước khi chạy side effect.
        // Nếu process crash sau đây, các record trong batch có thể bị bỏ qua.
        consumer.commitSync();

        for (ConsumerRecord<String, String> record : records) {
            updateBestEffortLiveView(record);
        }
    }
}
```

Ví dụ dùng manual commit để thể hiện rõ thứ tự. `commitSync()` sau `poll()` commit vị trí consumer đã tiến đến, thường bao gồm các record vừa trả về trong batch. Nếu xử lý record đầu tiên thất bại, các record còn lại trong batch cũng có thể đã bị commit và không được giao lại.

### 3.3. Khi nào dùng at-most-once?

Có thể cân nhắc khi:

- Dữ liệu là telemetry hoặc thống kê best-effort, một số mẫu bị mất không làm sai quyết định quan trọng.
- Side effect chỉ cập nhật giao diện tạm thời và dữ liệu mới sẽ nhanh chóng thay thế dữ liệu cũ.
- Hệ thống ưu tiên không tạo tác động lặp, đồng thời chấp nhận mất event khi lỗi.

Không nên chọn at-most-once cho thanh toán, sổ cái, tồn kho, đơn hàng hoặc các luồng mà bỏ sót một event gây sai lệch nghiệp vụ.

## 4. At-least-once

### 4.1. Nguyên tắc

At-least-once ưu tiên không bỏ qua record. Consumer chỉ commit offset sau khi side effect đã hoàn tất thành công.

```text
poll record
    |
    v
process record
    |
    v
side effect thành công
    |
    v
commit offset
```

Nếu process crash trước khi side effect hoàn tất, offset chưa được commit nên record sẽ được giao lại. Nếu crash sau side effect nhưng trước commit, record cũng được giao lại và side effect có thể chạy lần nữa.

Đây là cách tiếp cận phổ biến vì duplicate có thể được kiểm soát bằng idempotency, còn record bị bỏ qua thường khó phục hồi hơn.

### 4.2. Ví dụ Java: xử lý thành công rồi commit

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("orders"));

    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        try {
            for (ConsumerRecord<String, String> record : records) {
                updateOrderProjectionDurably(record);
            }

            // Chỉ commit khi toàn bộ record trong batch đã xử lý thành công.
            consumer.commitSync();
        } catch (Exception processingError) {
            // Không commit batch này. Record có thể được giao lại.
            // Các side effect đã thành công trước lỗi có thể bị lặp.
            handleBatchFailure(processingError);
            // Dừng consumer để lần chạy sau đọc lại từ committed offset cũ.
            throw new RuntimeException("Batch processing failed", processingError);
        }
    }
}
```

Đây là ví dụ minh họa cho xử lý tuần tự theo batch. `updateOrderProjectionDurably` phải hoàn tất side effect bền vững trước khi trả về. Nếu một record trong batch lỗi, không commit batch; các record đã xử lý thành công trước đó có thể được đọc lại. Đây là hành vi at-least-once và cần idempotency ở tầng nghiệp vụ.

Với xử lý song song, không được gọi `commitSync()` chỉ vì một số worker đã hoàn tất. Chỉ commit offset kế tiếp sau chuỗi offset liên tục đã xử lý thành công của từng partition. Nếu offset 11 còn dang dở nhưng offset 12 đã hoàn tất, không commit vượt qua 11.

### 4.3. Vì sao tắt auto commit?

Để kiểm soát rõ thời điểm commit, thường đặt:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
```

Nếu bật auto commit, consumer có thể commit vị trí đã poll theo chu kỳ trước khi business processing hoàn tất. Khi ứng dụng xử lý chậm hoặc crash, record chưa có side effect vẫn có thể bị bỏ qua. Auto commit đơn giản cho một số workload, nhưng không thể thay thế việc thiết kế commit theo ranh giới xử lý nghiệp vụ.

### 4.4. Khi nào dùng at-least-once?

Phù hợp khi:

- Không được bỏ sót event.
- Side effect có thể được làm idempotent hoặc deduplicate.
- Có thể chấp nhận record được giao lại khi crash hoặc rebalance.
- Hệ thống cần xử lý và phục hồi có thể kiểm tra được.

Đây thường là điểm khởi đầu thực tế cho consumer xử lý nghiệp vụ. Cần thiết kế duplicate handling ngay từ đầu thay vì giả định mỗi record chỉ đến một lần.

## 5. Làm cho side effect idempotent

### 5.1. Idempotency là gì?

Một thao tác idempotent có thể được thực hiện lặp lại mà trạng thái cuối cùng không thay đổi ngoài kết quả của lần thực hiện đầu tiên.

Ví dụ:

- `SET order_status = 'PAID'` theo trạng thái/version có thể idempotent hơn thao tác cộng trừ không điều kiện.
- Ghi nhận event ID vào bảng có unique constraint giúp phát hiện event đã xử lý.
- Cập nhật số dư bằng cách cộng tiền mỗi lần nhận record không idempotent nếu không có transaction/deduplication.

Idempotency không có nghĩa bỏ qua mọi message trùng payload. Hai event hợp lệ khác nhau có thể có cùng nội dung nhưng event ID khác nhau; ngược lại, một event được retry cần giữ cùng event ID.

### 5.2. Dùng event ID ổn định

Mỗi event nghiệp vụ nên có một định danh ổn định được tạo tại nguồn:

```json
{
  "eventId": "evt-7f1a9c",
  "eventType": "OrderPaid",
  "orderId": "ORD-101",
  "amount": 250000,
  "currency": "VND"
}
```

Khi producer retry hoặc event được replay, `eventId` phải giữ nguyên. Không tạo event ID mới cho mỗi lần gửi lại cùng một sự kiện, nếu không consumer không thể nhận ra đó là cùng một event logic.

### 5.3. Inbox/deduplication table

Consumer có thể lưu event ID đã xử lý vào bảng inbox trong cùng transaction database với business update. Một unique constraint ngăn event được áp dụng hai lần.

Ví dụ SQL:

```sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Luồng xử lý trong một database transaction:

1. Thử insert `eventId` vào `processed_events`.
2. Nếu insert thành công, thực hiện business update.
3. Commit database transaction.
4. Sau khi database commit thành công, commit Kafka offset.
5. Nếu event ID đã tồn tại, bỏ qua business update và vẫn xác nhận record đã được xử lý trước đó.

Nếu process crash sau database commit nhưng trước Kafka offset commit, Kafka giao lại record. Insert event ID lần nữa bị unique constraint từ chối hoặc ứng dụng nhận ra duplicate; business update không chạy lần hai. Sau đó consumer có thể commit offset.

### 5.4. Ví dụ pseudo-code với database transaction

```java
void handle(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    database.inTransaction(tx -> {
        boolean firstDelivery = tx.insertProcessedEventIfAbsent(event.eventId());

        if (firstDelivery) {
            tx.applyOrderEvent(event);
        }
    });

    // Chỉ sau khi database transaction commit thành công,
    // consumer mới commit Kafka offset của các record đã hoàn tất.
}
```

`insertProcessedEventIfAbsent` cần được triển khai bằng unique constraint hoặc câu lệnh atomic tương đương. Không dùng chuỗi thao tác “SELECT rồi INSERT” không có khóa/constraint, vì hai worker có thể cùng kiểm tra chưa tồn tại và cùng áp dụng event.

Inbox bảo đảm hiệu quả xử lý một lần ở database nếu dedup record và business update nằm trong cùng transaction. Kafka offset vẫn là transaction riêng; crash giữa hai hệ thống có thể làm record được giao lại, nhưng lần giao lại được deduplicate.

## 6. Exactly-once trong phạm vi Kafka

### 6.1. Producer idempotence chưa phải exactly-once processing

`enable.idempotence=true` giúp broker nhận diện retry của cùng producer sequence và tránh duplicate do retry trong phạm vi producer session được Kafka hỗ trợ.

Nó không giải quyết:

- Ứng dụng chủ động gọi `send()` hai lần cho cùng event logic.
- Consumer thực hiện side effect database rồi crash trước khi commit offset.
- Gửi email/HTTP request bị timeout nhưng service đích đã thực hiện thao tác.
- Hai producer độc lập phát cùng một event nghiệp vụ.

Vì vậy, idempotent producer cải thiện độ tin cậy khi publish nhưng không tự tạo exactly-once end-to-end.

### 6.2. Kafka transaction kết hợp output và input offset

Với luồng consume-transform-produce chỉ làm việc trong Kafka, Kafka transaction có thể kết hợp:

- Ghi một hoặc nhiều output record vào một hoặc nhiều topic.
- Ghi committed offset của input consumer group.
- Commit hoặc abort toàn bộ thay đổi như một đơn vị nguyên tử.

Khi transaction commit, output record được công bố và input offset được cập nhật cùng transaction. Nếu transaction abort, output thuộc transaction không được consumer `read_committed` nhìn thấy và input offset của transaction không được tiến lên.

Điều này giúp tránh hai trạng thái không nhất quán:

- Output đã được ghi nhưng input offset chưa commit, khiến input được xử lý lại và tạo output trùng.
- Input offset đã commit nhưng output chưa được ghi, khiến kết quả bị mất.

### 6.3. Consumer cần `read_committed`

Consumer downstream muốn chỉ nhìn thấy output của transaction đã commit cần cấu hình:

```java
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

Với `read_uncommitted`, consumer có thể đọc record thuộc transaction chưa commit hoặc đã abort. Vì vậy, producer transaction chỉ đảm bảo output được lọc đúng cho consumer có isolation phù hợp.

`read_committed` có thể khiến consumer phải chờ khi gặp transaction đang mở trong partition, vì ranh giới đọc ổn định (Last Stable Offset) chưa vượt qua transaction đó. Điều này là một phần của tính nhất quán transaction và có thể ảnh hưởng latency.

## 7. Ví dụ Java: consume-transform-produce trong Kafka transaction

Ví dụ dưới đây đọc từ `orders`, tạo output vào `order-events` và commit input offsets trong cùng transaction.

### 7.1. Cấu hình consumer

```java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "order-transformer");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

### 7.2. Cấu hình transactional producer

```java
Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
producerProps.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
    "order-transformer-instance-0");
```

`transactional.id` phải duy nhất giữa các producer đang hoạt động. Nếu cùng một logical producer được khởi động lại, có thể dùng lại ID đã định danh cho instance đó để producer mới fence instance cũ và xử lý transaction chưa hoàn tất theo cơ chế Kafka. Không dùng cùng ID cho nhiều instance đồng thời.

### 7.3. Xử lý một batch và commit offsets trong transaction

```java
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(consumerProps);
KafkaProducer<String, String> producer = new KafkaProducer<>(producerProps);

producer.initTransactions();
consumer.subscribe(List.of("orders"));

try {
    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        if (records.isEmpty()) {
            continue;
        }

        producer.beginTransaction();

        try {
            Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

            for (ConsumerRecord<String, String> record : records) {
                String transformed = transform(record.value());

                ProducerRecord<String, String> output = new ProducerRecord<>(
                    "order-events",
                    record.key(),
                    transformed
                );
                producer.send(output);

                TopicPartition inputPartition = new TopicPartition(
                    record.topic(), record.partition()
                );
                offsets.put(
                    inputPartition,
                    new OffsetAndMetadata(record.offset() + 1)
                );
            }

            producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
            producer.commitTransaction();
        } catch (Exception processingError) {
            try {
                producer.abortTransaction();
            } catch (Exception abortError) {
                processingError.addSuppressed(abortError);
            }
            throw new RuntimeException("Kafka transaction failed", processingError);
        }
    }
} finally {
    consumer.close();
    producer.close();
}
```

Đây là ví dụ minh họa API transactional producer. Cần bổ sung shutdown coordination, xử lý exception fatal/fencing và chính sách retry theo ứng dụng. Với mỗi partition, vòng lặp ghi offset kế tiếp sau record cuối cùng đã xử lý; vì `records` được duyệt theo thứ tự partition/offset, giá trị cuối cùng trong map là offset lớn nhất đã xử lý cộng một. Không commit qua record chưa xử lý thành công.

Các điểm quan trọng:

- `initTransactions()` khởi tạo transactional producer và xử lý transaction cũ theo `transactional.id`.
- `beginTransaction()` mở transaction mới.
- `send()` thêm output record vào transaction hiện tại.
- `sendOffsetsToTransaction()` đưa input offsets và metadata group vào cùng transaction.
- `commitTransaction()` công bố output và offset như một đơn vị.
- `abortTransaction()` hủy transaction khi xử lý thất bại.
- Consumer downstream nên dùng `isolation.level=read_committed` để chỉ thấy output đã commit.

Không gọi `consumer.commitSync()` cho cùng các input offsets trong luồng này. Việc commit offset độc lập sẽ phá vỡ tính nguyên tử mà transaction đang cung cấp.

### 7.4. Yêu cầu vận hành của transactional producer

- Mỗi producer instance đang hoạt động có `transactional.id` duy nhất.
- Producer được khởi tạo bằng `initTransactions()` trước khi gửi transaction.
- Consumer tắt auto commit và truyền đúng `consumer.groupMetadata()`.
- `transaction.timeout.ms` đủ cho thời gian xử lý batch nhưng không quá dài ngoài nhu cầu.
- Broker có cấu hình transaction state log và replication phù hợp cho môi trường production.
- Xử lý `ProducerFencedException` và lỗi transaction fatal bằng cách dừng hoặc tạo producer mới theo vòng đời hợp lệ; không retry mù quáng trên producer đã bị fence.
- Downstream consumer dùng `read_committed` nếu cần bỏ qua output transaction bị abort.

## 8. Exactly-once với database hoặc hệ thống bên ngoài Kafka

### 8.1. Kafka transaction không tự bao trùm database

Giả sử consumer đọc một event, cập nhật PostgreSQL rồi commit Kafka offset. Kafka transaction không tự động làm database transaction và offset commit thành một transaction phân tán.

Nếu database commit trước và Kafka offset commit sau, process có thể crash ở giữa. Record được giao lại; cần inbox/idempotency để không áp dụng business update lần nữa.

Nếu commit Kafka offset trước rồi database mới commit, process có thể crash ở giữa và database không bao giờ nhận update. Đây là nguy cơ mất dữ liệu.

Vì vậy, không gọi một luồng Kafka + database là exactly-once chỉ vì producer bật idempotence hoặc consumer dùng `read_committed`.

### 8.2. Inbox pattern cho Kafka-to-database

Inbox pattern lưu `eventId` và business update trong cùng database transaction. Khi event được giao lại, unique constraint phát hiện event đã được áp dụng và bỏ qua side effect lặp. Sau database commit, consumer commit Kafka offset.

Kết quả thực tế:

- Kafka có thể giao record nhiều lần.
- Consumer có thể chạy handler nhiều lần.
- Database chỉ áp dụng business effect một lần theo event ID.

Đây thường được gọi là effectively-once processing ở ranh giới database, dựa trên idempotency và transaction của database. Cần giữ inbox record đủ lâu để bao phủ khoảng thời gian replay/duplicate có thể xảy ra.

### 8.3. Outbox pattern cho database-to-Kafka

Khi một service vừa cập nhật database vừa cần publish event, có thể dùng transactional outbox:

1. Trong một database transaction, cập nhật business table và insert event vào bảng outbox.
2. Một publisher đọc outbox và gửi event đến Kafka.
3. Sau khi Kafka xác nhận, publisher đánh dấu outbox row đã publish hoặc lưu checkpoint.
4. Nếu publisher crash sau khi Kafka nhận event nhưng trước khi đánh dấu outbox, event có thể được gửi lại; downstream cần deduplicate bằng event ID hoặc publisher dùng cơ chế phù hợp.

Outbox tránh tình trạng database commit thành công nhưng ứng dụng crash trước khi publish event. Nó không làm database và Kafka cùng commit bằng một transaction nguyên tử; nó tạo một nguồn sự thật bền vững để retry.

### 8.4. HTTP, email và side effect không có idempotency

Nếu consumer gọi dịch vụ thanh toán hoặc gửi email, timeout có thể xảy ra sau khi hệ thống đích đã thực hiện thao tác nhưng trước khi consumer nhận response. Consumer không biết chắc thao tác đã xảy ra hay chưa.

Giải pháp thường gồm:

- Truyền idempotency key ổn định, thường dựa trên event ID.
- Hệ thống đích lưu kết quả theo key và trả lại kết quả cũ khi nhận request lặp.
- Có API tra cứu trạng thái khi kết quả timeout không rõ ràng.
- Lưu request/outcome trong database để đối soát.

Nếu hệ thống đích không hỗ trợ idempotency hoặc tra cứu, không thể bảo đảm exactly-once side effect chỉ bằng Kafka consumer offset.

## 9. Kafka Streams và exactly-once processing

Kafka Streams cung cấp cơ chế xử lý stream với khả năng tích hợp Kafka transaction. Khi bật processing guarantee phù hợp, Streams phối hợp output topic, state store changelog và input offsets để bảo đảm các kết quả xử lý trong phạm vi Kafka được commit nhất quán.

Với phiên bản Kafka Streams hỗ trợ EOS v2, cấu hình thường dùng:

```properties
processing.guarantee=exactly_once_v2
```

Hãy xác nhận giá trị hỗ trợ theo phiên bản Kafka Streams. Exactly-once của Kafka Streams áp dụng cho các thao tác được framework quản lý trong Kafka và state store được tích hợp theo thiết kế. Nếu processor gọi database hoặc HTTP service ngoài Kafka, side effect đó vẫn cần idempotency hoặc transaction riêng.

## 10. So sánh ba semantics

| Tiêu chí | At-most-once | At-least-once | Exactly-once trong Kafka transaction |
|---|---|---|---|
| Thời điểm commit input offset | Trước side effect | Sau side effect thành công | Cùng transaction với output Kafka |
| Nguy cơ mất record do crash | Có | Giảm thiểu; record được giao lại | Output và input offset cùng commit/abort trong Kafka |
| Nguy cơ xử lý trùng | Thấp hơn, đổi lại có thể mất | Có | Được kiểm soát trong phạm vi transaction Kafka |
| Cần idempotent side effect bên ngoài Kafka | Tùy nghiệp vụ | Rất nên có | Vẫn cần nếu có side effect ngoài Kafka |
| Độ phức tạp | Thấp | Trung bình | Cao hơn; cần transactional producer/consumer |
| Trường hợp phù hợp | Best-effort, có thể mất event | Phần lớn consumer nghiệp vụ | Consume-transform-produce trong Kafka cần atomicity |

Exactly-once không có nghĩa message không bao giờ được đọc lại ở mọi tình huống. Một transaction abort có thể khiến input được đọc lại; điều được bảo đảm là output transaction bị abort không được xem như output đã commit và input offset không được tiến lên một cách độc lập.

## 11. Chọn semantics theo nghiệp vụ

| Nghiệp vụ | Gợi ý | Lý do |
|---|---|---|
| Telemetry best-effort, biểu đồ realtime | Có thể at-most-once | Chấp nhận mất một số mẫu để tránh backlog/duplicate |
| Đồng bộ trạng thái đơn hàng vào database | At-least-once + inbox/idempotency | Không bỏ event; duplicate được khử ở database |
| Tính toán output từ input Kafka rồi ghi sang topic khác | Kafka transaction hoặc Kafka Streams EOS | Output và input offset cần commit nguyên tử |
| Cập nhật sổ cái hoặc số dư | At-least-once + unique event ID + DB transaction/inbox | Side effect phải bền vững và không được áp dụng lặp |
| Gửi email hoặc gọi payment API | At-least-once + idempotency key ở hệ thống đích | Timeout có thể không rõ side effect đã xảy ra hay chưa |
| Rebuild projection từ đầu | Group mới hoặc reset offset có kiểm soát + idempotent handler | Replay có chủ đích và có thể lặp event |

Đừng chọn exactly-once chỉ vì tên gọi nghe an toàn hơn. Nếu ứng dụng không cần output transaction hoặc có side effect ngoài Kafka, at-least-once kết hợp idempotency thường đơn giản và dễ vận hành hơn.

## 12. Kiểm thử failure scenario

Để xác minh semantics, cần chủ động kiểm thử các cửa sổ lỗi thay vì chỉ chạy happy path.

| Điểm gây lỗi | Điều cần quan sát |
|---|---|
| Kill consumer sau `poll()` trước xử lý | Record có được giao lại không? |
| Kill consumer sau DB commit trước Kafka commit | Inbox có ngăn business update lặp không? |
| Kill consumer sau commit trước DB update | At-most-once có làm mất side effect như dự kiến không? |
| Ngắt mạng sau khi broker append nhưng trước khi producer nhận ACK | Producer retry có tạo duplicate không? |
| Abort Kafka transaction sau khi gửi output | Consumer `read_committed` có bỏ qua output bị abort không? |
| Kill process khi transaction đang mở | Transaction timeout/recovery có giữ input offset và output nhất quán không? |
| Rebalance khi worker đang xử lý | Offset có commit vượt qua record chưa hoàn tất không? |
| Replay cùng event ID nhiều lần | Database hoặc downstream có deduplicate đúng không? |

Ghi log tối thiểu `eventId`, topic, partition, offset, group ID, transaction ID (nếu có), thời điểm bắt đầu/kết thúc xử lý và kết quả side effect. Những trường này giúp đối chiếu duplicate, replay và commit.

## 13. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Commit offset trước side effect nhưng kỳ vọng không mất event | Crash sau commit làm mất xử lý | Commit sau side effect nếu cần at-least-once |
| Side effect xong mới commit nhưng không deduplicate | Crash giữa hai bước tạo duplicate | Dùng event ID và inbox/unique constraint |
| Bật auto commit rồi giả định xử lý thành công mới commit | Offset có thể được commit trước khi handler hoàn tất | Tắt auto commit và commit theo ranh giới nghiệp vụ |
| Cho rằng producer idempotence bảo vệ database | Producer idempotence chỉ áp dụng cho publish Kafka | Dùng DB transaction và inbox/outbox |
| Dùng Kafka transaction nhưng downstream đọc `read_uncommitted` | Có thể nhìn thấy record thuộc transaction chưa commit/đã abort | Dùng `read_committed` cho consumer cần transaction isolation |
| Dùng chung `transactional.id` cho nhiều producer hoạt động đồng thời | Producer có thể fence lẫn nhau | Đảm bảo transactional ID duy nhất cho mỗi active instance |
| Commit offset độc lập trong consume-transform-produce EOS | Phá vỡ atomicity giữa output và input offset | Dùng `sendOffsetsToTransaction()` |
| Gọi email/HTTP rồi nghĩ Kafka transaction rollback được side effect | Side effect ngoài Kafka không được rollback | Dùng idempotency key, inbox/outbox hoặc transaction phía dịch vụ đích |
| Retry vô hạn với event lỗi | Poison message làm partition kẹt hoặc retry storm | Có retry policy, DLT và quy trình xử lý lỗi rõ ràng |

## 14. Checklist thiết kế processing semantics

Trước khi triển khai consumer, hãy xác nhận:

- Đã xác định phạm vi exactly-once cần bảo đảm: Kafka-to-Kafka hay bao gồm database/API?
- Đã xác định chấp nhận mất event hay chấp nhận duplicate?
- `enable.auto.commit` được cấu hình phù hợp với thứ tự xử lý/commit.
- Nếu at-least-once, side effect có idempotent hoặc có deduplication không?
- Event ID ổn định qua retry và replay.
- Inbox record và business update có nằm trong cùng database transaction không?
- Offset chỉ commit qua các record đã xử lý liên tục thành công.
- Nếu dùng Kafka transaction, producer có `transactional.id` duy nhất và gọi `initTransactions()` không?
- Input offset có được gửi qua `sendOffsetsToTransaction()` thay vì commit độc lập không?
- Downstream cần transaction isolation có dùng `read_committed` không?
- Đã xử lý fencing, abort, transaction timeout và rebalance chưa?
- Có kiểm thử crash ở các cửa sổ lỗi quan trọng không?
- Có metric/log để truy vết event ID, offset, group và transaction không?

## 15. Câu hỏi tự kiểm tra

1. At-most-once và at-least-once khác nhau ở thứ tự side effect và offset commit như thế nào?
2. Vì sao commit offset trước xử lý có thể làm mất event?
3. Vì sao commit sau side effect có thể làm side effect chạy hai lần?
4. Committed offset biểu thị record cuối đã xử lý hay offset kế tiếp cần đọc?
5. Vì sao `enable.auto.commit=true` không phải lựa chọn phù hợp khi cần kiểm soát chặt thời điểm xử lý hoàn tất?
6. Idempotency khác exactly-once delivery như thế nào?
7. Inbox table cần unique constraint trên trường nào và vì sao business update phải cùng transaction?
8. Producer idempotence giải quyết duplicate trong trường hợp nào và không giải quyết trường hợp nào?
9. Kafka transaction kết hợp những thao tác nào để tạo consume-transform-produce atomicity?
10. Vì sao consumer downstream cần `isolation.level=read_committed`?
11. Vì sao Kafka transaction không tự làm database update và offset commit thành một transaction?
12. Outbox pattern giải quyết failure window nào giữa database và Kafka?
13. `transactional.id` cần đáp ứng điều kiện gì khi chạy nhiều producer instance?
14. Khi nào at-least-once kết hợp idempotency phù hợp hơn Kafka transaction?

## Kết luận

At-most-once commit offset trước side effect nên tránh xử lý trùng nhưng có thể bỏ qua event. At-least-once thực hiện side effect trước khi commit nên giảm nguy cơ mất event, đổi lại consumer phải chịu được duplicate. Exactly-once trong Kafka được xây dựng bằng transaction để ghi output và input offset nguyên tử, kết hợp downstream `read_committed`. Khi side effect nằm trong database hoặc dịch vụ ngoài Kafka, cần inbox/outbox, idempotency key hoặc transaction phối hợp riêng. Lựa chọn đúng bắt đầu từ việc xác định phạm vi bảo đảm và cửa sổ lỗi mà nghiệp vụ chấp nhận.
