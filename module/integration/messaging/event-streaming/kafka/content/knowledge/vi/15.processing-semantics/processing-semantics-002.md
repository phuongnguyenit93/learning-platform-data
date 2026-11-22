# Phân biệt xác nhận ghi, giao bản ghi và hoàn tất xử lý

Trong Kafka, một record có thể đã được producer gửi thành công, được broker xác nhận, được consumer đọc về và thậm chí đã được xử lý nghiệp vụ. Đây là các mốc khác nhau. Nếu gọi tất cả là “message đã được xử lý” hoặc “đã ACK”, ứng dụng rất dễ commit offset quá sớm, báo thành công khi dữ liệu chưa bền vững hoặc tạo side effect trùng khi retry.

Bài học này phân biệt bốn mốc chính:

1. **Write acknowledgment:** broker phản hồi producer rằng request ghi đã đạt mức xác nhận cấu hình.
2. **Consumer delivery:** consumer nhận record qua Fetch/`poll()` hoặc listener container.
3. **Business processing completion:** logic nghiệp vụ và side effect cần thiết đã hoàn tất.
4. **Offset commit:** consumer group lưu vị trí tiếp theo cần đọc.

Mỗi mốc trả lời một câu hỏi khác nhau. Producer ACK không chứng minh consumer đã nhận record; consumer nhận record không chứng minh nghiệp vụ đã xử lý xong; xử lý xong cũng chưa có nghĩa offset đã commit.

## 1. Vòng đời của một record qua Kafka

Một luồng event điển hình:

~~~mermaid
sequenceDiagram
    participant A as Producer application
    participant P as Kafka Producer
    participant B as Broker leader
    participant R as ISR followers
    participant C as Consumer
    participant D as Downstream system
    A->>P: send(record)
    P->>B: Produce request
    B->>B: Append record vào log
    B->>R: Replicate record
    R-->>B: Replica acknowledgment
    B-->>P: Produce response / ACK
    P-->>A: Future hoàn tất thành công
    C->>B: Fetch request
    B-->>C: Record batch
    C->>D: Gọi xử lý nghiệp vụ
    D-->>C: Kết quả xử lý thành công
    C->>B: Commit next offset
    B-->>C: Commit response
~~~

Luồng này có nhiều điểm lỗi độc lập:

- Broker có thể ghi record nhưng response bị mất trên mạng.
- Producer có thể nhận ACK trong khi consumer chưa chạy hoặc đang lag.
- Consumer có thể fetch record rồi crash trước khi xử lý.
- Consumer có thể hoàn tất side effect nhưng crash trước khi commit offset.
- Offset có thể commit thành công nhưng side effect bên ngoài chưa được lưu nếu ứng dụng commit sai thứ tự.

Do đó, cần xác định rõ từng ACK xác nhận điều gì và thành phần nào chịu trách nhiệm cho bước tiếp theo.

## 2. Producer ACK xác nhận điều gì?

Producer gửi `ProduceRequest` đến leader của partition. Cấu hình `acks` quyết định producer chờ mức xác nhận nào trước khi coi request gửi thành công.

Kafka 4.4 có các giá trị:

| `acks` | Điều broker xác nhận | Rủi ro |
|---|---|---|
| `0` | Producer không chờ broker phản hồi | Không biết broker có nhận/ghi record hay không; không có retry dựa trên lỗi broker |
| `1` | Leader đã ghi record vào local log và phản hồi | Nếu leader hỏng trước khi follower sao chép, record có thể mất khi leader mới được chọn |
| `all` hoặc `-1` | Leader chờ các replica hiện thuộc ISR xác nhận | Mức xác nhận mạnh nhất; còn phụ thuộc replication factor, ISR và cấu hình cluster |

`acks=all` không có nghĩa mọi replica được cấu hình ban đầu đều phải xác nhận. Nó có nghĩa leader chờ toàn bộ replica đang nằm trong ISR. Replica không nằm trong ISR không tham gia điều kiện xác nhận của request đó.

Kafka 4.4 mặc định `acks=all`. Với producer cần durability cao, thường kết hợp `acks=all`, replication factor phù hợp và `min.insync.replicas`.

Với `acks=0`, producer không nhận được xác nhận từ broker; `RecordMetadata` trả về không có offset broker hợp lệ (offset là `-1`). Vì vậy, callback hoặc Future hoàn tất trong chế độ này không thể được dùng làm bằng chứng broker đã ghi record.

### 2.1. Vai trò của min.insync.replicas

`min.insync.replicas` là số replica tối thiểu phải nằm trong ISR để broker chấp nhận một lần ghi với `acks=all`.

Ví dụ:

- Topic có replication factor 3.
- `min.insync.replicas=2`.
- Hiện có 3 replica trong ISR: ghi có thể được chấp nhận và leader chờ cả 3 replica ISR xác nhận.
- Một replica rời ISR, còn 2 replica: ghi vẫn có thể được chấp nhận.
- Chỉ còn 1 replica trong ISR: ghi với `acks=all` bị từ chối bằng lỗi như `NotEnoughReplicasException`.

Cấu hình này cân bằng availability và durability. Đặt `min.insync.replicas` cao hơn số replica thường còn hoạt động có thể khiến producer không ghi được khi có sự cố. Đặt quá thấp làm giảm khả năng bảo vệ record trước lỗi broker.

Ví dụ cấu hình topic:

~~~properties
min.insync.replicas=2
~~~

Replication factor được đặt khi tạo topic hoặc thay đổi replica assignment; không phải mọi cấu hình topic đều có thể thay đổi bằng cách chỉnh một property. Hãy xác minh cấu hình topic và trạng thái ISR thực tế.

### 2.2. ACK thành công không phải xử lý nghiệp vụ thành công

Khi producer callback nhận `RecordMetadata`, thông tin đó cho biết broker đã phản hồi thành công theo `acks` đã chọn. Metadata gồm topic, partition và offset được broker gán cho record.

Điều đó **không** chứng minh:

- Consumer đã fetch record.
- Listener đã được gọi.
- Database đích đã commit.
- Email, thanh toán hoặc API bên ngoài đã hoàn tất.
- Một consumer group cụ thể đã commit offset.

Producer chỉ xác nhận được việc ghi theo hợp đồng giữa producer và broker. Muốn biết consumer xử lý đến đâu, cần quan sát consumer group, offset và trạng thái nghiệp vụ ở downstream.

## 3. Gửi thành công trong Java Producer

`KafkaProducer.send()` là API bất đồng bộ. Lời gọi thường đưa record vào buffer và trả về `Future`; việc gửi request, chờ ACK và retry diễn ra ở sender thread.

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>("orders", orderId, payload);

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        log.error("Kafka write failed, orderId={}", orderId, exception);
        return;
    }

    log.info(
        "Kafka write acknowledged: topic={}, partition={}, offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Callback thành công là mốc producer nhận được kết quả gửi thành công theo cấu hình producer. Không nên đổi tên log thành `order processed` hoặc `payment completed` vì consumer/downstream chưa được xác nhận.

Nếu ứng dụng cần chờ kết quả trong luồng hiện tại, có thể dùng:

~~~java
RecordMetadata metadata = producer.send(record).get();
~~~

Cách gọi `.get()` chặn thread hiện tại cho đến khi request hoàn tất hoặc lỗi. Không nên dùng đồng loạt trong đường xử lý cần throughput cao nếu chưa đánh giá tác động.

### 3.1. Idempotent producer xử lý retry như thế nào?

Nếu broker đã ghi record nhưng ACK bị mất, producer có thể không biết request đã thành công hay chưa. Khi retry, record có nguy cơ được ghi trùng.

Idempotent producer dùng producer ID và sequence number để broker nhận diện batch retry của cùng producer session. Điều này giúp retry do lỗi mạng/broker không tạo thêm bản ghi trùng trong log.

Kafka 4.4 mặc định bật `enable.idempotence=true` nếu không có cấu hình xung đột. Idempotence yêu cầu:

- `acks=all`.
- `retries` lớn hơn 0.
- `max.in.flight.requests.per.connection` không vượt quá 5.

Idempotence bảo vệ retry nội bộ của producer. Nó không tự khử trùng khi ứng dụng khởi động lại rồi chủ động gửi lại cùng một nghiệp vụ bằng một lần `send()` mới. Với nghiệp vụ cần deduplicate xuyên lần restart, hãy dùng event ID ổn định và cơ chế idempotency ở tầng nghiệp vụ.

## 4. Consumer delivery là mốc nào?

Consumer gửi Fetch request đến broker leader của partition và nhận các record batch từ vị trí offset của nó. Với Java Consumer, ứng dụng nhận các record qua `poll()`:

~~~java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, String> record : records) {
    log.info(
        "Received topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset()
    );
}
~~~

Khi `poll()` trả record, consumer position đã tiến lên. Điều đó chỉ cho biết Kafka client đã giao record cho ứng dụng trong lần poll. Nó chưa chứng minh `process(record)` đã chạy xong.

Cần phân biệt:

- **Broker fetch response:** broker trả record batch cho consumer.
- **Consumer poll delivery:** Kafka client trả record cho code ứng dụng.
- **Listener invocation:** Spring Kafka container gọi listener với record.
- **Business completion:** ứng dụng hoàn tất các thao tác nghiệp vụ cần thiết.
- **Offset commit:** group coordinator lưu next offset để lần sau tiếp tục.

Nếu ứng dụng log “received” ngay sau `poll()`, log đó không nên được diễn giải thành “processed”.

### 4.1. Consumer position và committed position

Consumer position là offset tiếp theo mà `poll()` sẽ trả về. Position tiến lên khi client nhận record, ngay cả khi ứng dụng chưa xử lý xong.

Committed position là vị trí đã được lưu bền vững cho consumer group. Khi consumer restart hoặc partition được giao cho member khác, consumer tiếp tục từ committed offset.

Committed offset là **offset tiếp theo cần đọc**, không phải offset cuối đã xử lý. Nếu record offset 10, 11 và 12 đều được xử lý thành công, vị trí commit là 13.

Không commit dựa trên số record đã fetch nếu ứng dụng chưa hoàn tất xử lý tương ứng.

## 5. Business processing completion là gì?

Một record được xem là xử lý nghiệp vụ hoàn tất khi tất cả side effect bắt buộc của bước xử lý đã đạt trạng thái thành công theo hợp đồng ứng dụng.

Ví dụ consumer xử lý `OrderCreated`:

1. Deserialize và validate event.
2. Kiểm tra event ID đã được xử lý chưa.
3. Ghi order vào database.
4. Cập nhật projection hoặc trạng thái nghiệp vụ.
5. Ghi nhận kết quả xử lý/idempotency key.
6. Commit transaction database.
7. Sau đó mới xác nhận offset Kafka theo chiến lược đã chọn.

Nếu ứng dụng chỉ deserialize record, gọi hàm xử lý bất đồng bộ rồi trả về listener ngay, container có thể coi listener đã hoàn tất trong khi công việc thật vẫn đang chạy. Với xử lý bất đồng bộ, phải gắn acknowledgment với kết quả hoàn tất thật và giữ thứ tự commit theo partition.

### 5.1. Xử lý xong nhưng offset chưa commit

Đây là cửa sổ lỗi thường gặp:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant D as Database
    participant K as Kafka group coordinator
    C->>D: Ghi kết quả nghiệp vụ
    D-->>C: DB commit thành công
    Note over C: Consumer crash trước offset commit
    C->>K: Restart và nhận lại partition
    K-->>C: Trả committed offset cũ
    C->>D: Xử lý lại record
~~~

Record được xử lý lần thứ hai vì offset chưa commit. Đây là hành vi at-least-once thường gặp. Muốn tránh side effect trùng, database operation cần idempotent hoặc có bảng inbox/deduplication theo event ID.

### 5.2. Commit offset trước khi xử lý xong

Nếu consumer commit offset trước rồi mới ghi database:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka group coordinator
    participant D as Database
    C->>K: Commit next offset
    K-->>C: Commit thành công
    Note over C: Consumer crash trước khi xử lý
    C->>K: Restart
    K-->>C: Bắt đầu sau record đã commit
    Note over C,D: Record chưa được xử lý nhưng bị bỏ qua
~~~

Record có thể bị bỏ qua trong lần đọc tiếp theo dù side effect chưa hoàn tất. Đây là hành vi at-most-once theo hướng commit trước xử lý.

Đối với hầu hết hệ thống nghiệp vụ, xử lý xong rồi commit offset phù hợp hơn; chấp nhận record có thể được giao lại và thiết kế handler idempotent.

## 6. Bốn mốc cần quan sát và cách đặt tên log

Dùng tên log/metric phản ánh đúng mốc để tránh kết luận sai khi điều tra sự cố.

| Mốc | Ví dụ log | Điều có thể kết luận |
|---|---|---|
| Producer gửi | `producer_send_started` | Ứng dụng bắt đầu gửi |
| Broker ACK | `producer_acknowledged` | Broker xác nhận theo `acks` |
| Consumer nhận | `consumer_received` | Client/listener nhận record |
| Nghiệp vụ hoàn tất | `business_processing_completed` | Side effect bắt buộc đã hoàn tất |
| Offset commit | `consumer_offset_committed` | Group coordinator đã xác nhận checkpoint |

Nên gắn các trường sau vào log:

- `eventId`: định danh nghiệp vụ ổn định.
- `topic`, `partition`, `offset`: định vị record trong Kafka.
- `groupId`, `clientId`: xác định consumer group và client.
- `correlationId`/`traceId`: liên kết các bước giữa service.
- `attempt`: số lần xử lý/retry ở tầng ứng dụng.
- `processingResult`: success, retrying, recovered hoặc failed.

Không dùng `offset` làm event ID toàn cục. Offset chỉ duy nhất trong phạm vi một partition; khóa định danh phù hợp thường là kết hợp topic-partition-offset hoặc event ID do nghiệp vụ cấp.

## 7. At-most-once, at-least-once và exactly-once

Ba thuật ngữ này mô tả cách hệ thống xử lý lỗi và giao lại record.

| Semantics | Thứ tự điển hình | Kết quả khi lỗi | Đánh đổi |
|---|---|---|---|
| At-most-once | Commit offset trước xử lý | Có thể mất xử lý, không phát lại record đã commit | Ít duplicate, chấp nhận mất record |
| At-least-once | Xử lý xong rồi commit | Có thể xử lý lại nếu crash trước commit | Không bỏ qua record đã được Kafka lưu và còn trong retention; cần idempotency |
| Exactly-once | Output và input offset được commit atomically trong một transaction phù hợp | Transaction commit hoặc abort cùng nhau | Phức tạp hơn; phạm vi bảo đảm phải được xác định |

### 7.1. At-most-once

Ứng dụng commit offset trước khi thực hiện side effect. Nếu crash sau commit nhưng trước khi side effect hoàn tất, record không được đọc lại từ committed offset.

Chỉ chọn cách này khi mất một số lần xử lý được chấp nhận và ưu tiên không xử lý trùng hơn không mất dữ liệu.

### 7.2. At-least-once

Ứng dụng xử lý record thành công rồi mới commit next offset. Nếu crash giữa hai bước, record được giao lại. Đây là lựa chọn phổ biến khi dữ liệu quan trọng và downstream có thể xử lý idempotent.

Ví dụ:

~~~java
for (ConsumerRecord<String, String> record : records) {
    processAndPersistIdempotently(record);
}

consumer.commitSync(records.nextOffsets());
~~~

Nếu một record lỗi, không commit vượt qua nó. Nếu xử lý thành công nhưng commit thất bại, lần sau có thể nhận lại record và chạy lại handler.

### 7.3. Exactly-once phải xác định phạm vi

“Exactly-once” không phải một ACK duy nhất. Cần nói rõ exactly-once ở đâu:

- Exactly-once write vào Kafka log với idempotent producer: retry của cùng producer session không tạo duplicate trong log.
- Exactly-once consume-transform-produce giữa các topic Kafka: output records và input offsets được commit trong cùng Kafka transaction; downstream consumer dùng `read_committed`.
- Exactly-once side effect vào database/HTTP/email: Kafka transaction tự nó không bao trùm transaction của hệ thống bên ngoài.

Nếu một service gọi payment API rồi commit offset Kafka, crash có thể xảy ra sau khi payment thành công nhưng trước khi offset commit. Khi record được giao lại, API có thể bị gọi lần nữa. Cần idempotency key ở payment service hoặc một cơ chế inbox/outbox/transaction phù hợp.

## 8. Kafka transaction kết hợp output và input offset

Trong consume-transform-produce, consumer đọc input record, producer gửi output record và offset input được thêm vào cùng transaction.

Luồng:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant P as Transactional Producer
    participant K as Kafka brokers
    C->>K: Fetch input records
    K-->>C: Input batch
    P->>K: beginTransaction
    P->>K: Produce output records
    P->>K: sendOffsetsToTransaction(next offsets, group metadata)
    P->>K: commitTransaction
    K-->>P: Transaction committed
    Note over K: Output và input offsets cùng được công nhận
~~~

Ví dụ Java ở mức API:

~~~java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-transformer");
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
consumerProps.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
consumerProps.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);

Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-transformer-instance-0");

KafkaConsumer<String, String> consumer =
        new KafkaConsumer<>(consumerProps);
KafkaProducer<String, String> producer =
        new KafkaProducer<>(producerProps);

producer.initTransactions();
consumer.subscribe(List.of("orders"));

while (running) {
    ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

    if (records.isEmpty()) {
        continue;
    }

    try {
        producer.beginTransaction();

        for (ConsumerRecord<String, String> record : records) {
            String transformed = transform(record.value());
            producer.send(new ProducerRecord<>(
                    "orders-enriched",
                    record.key(),
                    transformed
            ));
        }

        producer.sendOffsetsToTransaction(
                records.nextOffsets(),
                consumer.groupMetadata()
        );

        producer.commitTransaction();
    }
    catch (Exception e) {
        producer.abortTransaction();
        throw e;
    }
}
~~~

Đây là skeleton minh họa. Production code phải phân loại exception, xử lý fencing/abort, đóng client đúng cách, quản lý lifecycle và bảo đảm consumer position được khôi phục phù hợp sau transaction abort. Không tiếp tục xử lý batch tiếp theo như thể transaction đã commit nếu transaction trước đó thất bại.

Producer transactional cần `transactional.id` ổn định và duy nhất theo instance logic. `initTransactions()` khởi tạo producer transactional và fencing producer cũ dùng cùng transactional ID. Consumer cần `enable.auto.commit=false`. Consumer đọc output transactional nên dùng `isolation.level=read_committed` để không nhìn thấy record của transaction đã abort hoặc chưa hoàn tất.

### 8.1. Vì sao sendOffsetsToTransaction quan trọng?

Nếu ứng dụng gửi output thành công rồi commit offset bằng `consumer.commitSync()` riêng, có thể xảy ra:

- Output đã commit nhưng input offset chưa commit: input được đọc lại và output có thể bị ghi lần nữa.
- Input offset đã commit nhưng output transaction abort: input bị bỏ qua dù output không tồn tại.

`sendOffsetsToTransaction()` đưa next offset của input vào cùng transaction với output. Kafka có thể công nhận hoặc hủy cả hai một cách nguyên tử trong phạm vi Kafka.

## 9. Khi side effect nằm trong database hoặc dịch vụ bên ngoài

Kafka transaction không tự tạo distributed transaction với PostgreSQL, MySQL, REST API, payment gateway hay hệ thống email. Phải thiết kế ranh giới nhất quán riêng.

### 9.1. Inbox/deduplication trong cùng transaction database

Một cách phổ biến là lưu event ID đã xử lý trong cùng transaction database với side effect:

~~~sql
BEGIN;

WITH inserted AS (
    INSERT INTO processed_events(event_id)
    VALUES ('evt-123')
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
)
UPDATE orders
SET status = 'PROCESSED'
WHERE order_id = 'order-42'
  AND EXISTS (SELECT 1 FROM inserted);

COMMIT;
~~~

Đoạn SQL dùng cú pháp PostgreSQL và minh họa ý tưởng; `processed_events.event_id` cần có unique constraint hoặc là primary key. Nếu event ID đã tồn tại, CTE không trả row nên business update không chạy. Ứng dụng thực tế cần xử lý cả trường hợp event trùng nhưng payload khác, và bảo đảm inbox key cùng business update nằm trong một transaction database.

Sau khi DB transaction commit, consumer mới commit Kafka offset. Nếu consumer crash trước Kafka commit, record có thể được giao lại nhưng inbox nhận diện event ID đã xử lý và không lặp side effect.

### 9.2. Outbox khi phát event sau thay đổi database

Nếu một request vừa cập nhật database vừa cần phát event, dùng Transactional Outbox:

1. Trong một transaction database, ghi business state và một outbox row.
2. Dispatcher/CDC đọc outbox và publish sang Kafka.
3. Khi publish được xác nhận, đánh dấu hoặc tiến trạng thái outbox theo thiết kế.
4. Consumer downstream xử lý idempotent theo event ID.

Outbox tránh khoảng trống “database commit nhưng Kafka publish thất bại” mà không cần transaction phân tán giữa database và Kafka. Dispatcher có thể publish lặp khi mất ACK, vì vậy event ID và idempotency vẫn cần thiết.

### 9.3. API bên ngoài cần idempotency key

Nếu consumer gọi payment, shipment hoặc REST API, hãy truyền event ID hoặc operation ID ổn định làm idempotency key nếu dịch vụ hỗ trợ.

Không tạo key mới mỗi lần retry. Dịch vụ nhận request có thể lưu kết quả của key đầu tiên và trả lại kết quả cũ khi nhận lại cùng key, tránh tạo side effect lần thứ hai.

Nếu dịch vụ không hỗ trợ idempotency, cần một quy trình đối soát trạng thái hoặc một adapter có lưu operation state bền vững. Không thể suy ra API đã thất bại chỉ vì consumer timeout; request có thể đã hoàn tất ở server nhưng response bị mất.

## 10. Spring Kafka: listener return và acknowledgment

Với Spring Kafka, listener container gọi listener và quản lý commit theo `AckMode`. Cần hiểu listener return có ý nghĩa khác nhau tùy acknowledgment mode.

| AckMode | Mốc commit |
|---|---|
| `RECORD` | Sau khi listener xử lý xong từng record |
| `BATCH` | Sau khi tất cả record trong poll batch được xử lý |
| `TIME` | Sau khi batch hoàn tất và đạt thời gian commit |
| `COUNT` | Sau khi batch hoàn tất và đạt số record |
| `COUNT_TIME` | Khi đạt điều kiện count hoặc time |
| `MANUAL` | Listener gọi `acknowledge()`, container áp dụng semantics tương tự batch |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread |

Từ Spring Kafka 2.3, framework mặc định đặt `enable.auto.commit=false` nếu ứng dụng không cấu hình rõ. `AckMode.BATCH` là mặc định của listener container.

Ví dụ record listener với manual immediate acknowledgment:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection",
    containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.processAndPersist(record.value());
    acknowledgment.acknowledge();
}
~~~

Chỉ acknowledge sau khi `processAndPersist()` hoàn tất. Nếu listener trả về trước khi công việc bất đồng bộ hoàn thành, container có thể commit quá sớm tùy AckMode.

Ví dụ cấu hình factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
manualAckFactory(ConsumerFactory<String, OrderEvent> consumerFactory) {
    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);

    return factory;
}
~~~

Với retry và DLT, cần cấu hình error handler/recoverer. Chỉ khi việc recover (ví dụ publish record sang DLT) thành công theo chính sách thì offset của record lỗi mới được tiến qua. Nếu publish DLT thất bại, không được âm thầm commit record gốc như thể đã xử lý xong.

## 11. Failure matrix: điều gì xảy ra nếu crash ở từng mốc?

| Thời điểm crash | Trạng thái có thể có | Hành vi khi khôi phục | Cách bảo vệ |
|---|---|---|---|
| Trước khi producer gửi | Chưa có record ở Kafka | Ứng dụng cần gửi lại | Outbox hoặc retry nguồn |
| Broker ghi nhưng producer chưa nhận ACK | Record có thể đã tồn tại | Retry có thể tạo duplicate nếu không idempotent | Idempotent producer, event ID |
| Sau producer ACK, trước consumer fetch | Record đã được broker xác nhận, consumer chưa nhận | Consumer đọc sau đó | Theo dõi consumer lag |
| Sau fetch/poll, trước business processing | Record đã giao cho app, offset chưa commit | Đọc lại sau restart/rebalance | Commit sau xử lý |
| Sau business processing, trước offset commit | Side effect đã hoàn tất, offset cũ | Record có thể được giao lại | Inbox/deduplication/idempotent handler |
| Sau offset commit, trước business processing | Offset đã tiến, side effect chưa hoàn tất | Record có thể bị bỏ qua | Không commit trước xử lý |
| Trong Kafka transaction trước commit | Transaction chưa hoàn tất | Output không được thấy bởi `read_committed` consumer nếu abort | Abort/recovery đúng cách |
| Sau Kafka transaction commit | Output và input offset được commit cùng nhau | Tiếp tục sau input offset mới | `read_committed`, transaction handling |
| API ngoài đã thực hiện nhưng consumer chưa commit | Side effect ngoài đã xảy ra, offset cũ | API có thể bị gọi lại | Idempotency key/đối soát |

Bảng này cho thấy “ACK” cần luôn đi kèm tên thành phần và mốc thời gian. Không thể dùng producer ACK để suy ra trạng thái database hoặc consumer offset.

## 12. Chọn semantics theo yêu cầu nghiệp vụ

| Use case | Hướng thiết kế thường phù hợp |
|---|---|
| Telemetry/metrics có thể mất một lượng nhỏ | Có thể cân nhắc `acks=1` hoặc `acks=0` tùy mức chấp nhận mất dữ liệu; đánh giá rõ rủi ro |
| Đơn hàng, thanh toán, tồn kho | `acks=all`, replication/min ISR phù hợp; consumer xử lý rồi commit; idempotency/inbox |
| Consume-transform-produce giữa các topic Kafka | Idempotent/transactional producer, gửi offsets vào transaction, downstream `read_committed` |
| Đồng bộ Kafka sang database | At-least-once + inbox/deduplication trong DB; hoặc connector có hỗ trợ offset/output atomicity |
| Gửi email hoặc gọi REST API | Event ID ổn định, idempotency key, retry có giới hạn và đối soát |
| Gửi record lỗi sang DLT | Chỉ tiến offset sau khi recovery/DLT publish thành công; deduplicate DLT theo event ID |

Không có cấu hình `acks` nào tự bảo đảm end-to-end exactly-once. `acks` điều khiển xác nhận ghi; consumer commit điều khiển vị trí đọc; nghiệp vụ bên ngoài cần cơ chế nhất quán riêng.

## 13. Kiểm thử các mốc xác nhận

Có thể xây dựng lab để quan sát sự khác nhau giữa producer ACK, consumer delivery, business completion và offset commit.

### Bước 1: Tạo topic có replication

Tạo topic `orders` với replication factor 3 trong cluster thử nghiệm. Kiểm tra ISR và đặt `min.insync.replicas=2`.

### Bước 2: Gửi record và log producer ACK

Gửi record có `eventId` duy nhất. Trong callback, log topic, partition và offset. Gọi log này là `producer_acknowledged`.

### Bước 3: Tách consumer receive và process

Consumer log `consumer_received` ngay sau khi nhận record. Sau đó cố ý chờ hoặc gọi service giả lập trước khi log `business_processing_completed`.

Quan sát rằng producer ACK có thể xảy ra trước consumer receive; consumer receive có thể xảy ra trước business completion.

### Bước 4: Crash sau business completion nhưng trước commit

Tắt consumer sau khi database transaction thành công nhưng trước `commitSync()`. Khởi động lại consumer và quan sát record được giao lại. Kiểm tra inbox/event ID ngăn side effect trùng.

### Bước 5: Crash sau commit nhưng trước process

Trong lab riêng, cố ý commit trước khi ghi database rồi dừng process. Quan sát record không được đọc lại từ committed offset và side effect chưa xuất hiện. Đây là ví dụ minh họa rủi ro at-most-once.

### Bước 6: Thử acks

Trong môi trường test, gửi record với `acks=1` và `acks=all`, theo dõi producer callback và broker ISR. Có thể dừng broker leader để kiểm tra hành vi retry/failover; không làm thử nghiệm này trên cluster production.

### Bước 7: Thử Kafka transaction

Consume từ `orders`, produce sang `orders-enriched`, gửi input offsets vào transaction và commit. Tạo một lần abort có kiểm soát, sau đó xác nhận consumer `read_committed` không nhìn thấy output đã abort và input offset không được tiến qua transaction thất bại.

## 14. Metrics và log cần quan sát

### Producer

- `record-send-rate`, `record-error-rate`, `record-retry-rate`.
- `request-latency-avg`, `request-latency-max`.
- `record-queue-time-avg`.
- Callback success/failure và lỗi cuối cùng.
- Producer transaction commit/abort nếu dùng transaction.

### Consumer

- Records consumed/processed rate.
- Consumer group lag và lag theo partition.
- Consumer position so với committed position.
- Commit latency và commit error rate.
- Listener processing duration.
- Retry count, DLT publish success/failure.
- Rebalance count và duration.

### Downstream

- Database transaction success/failure.
- Duplicate event ID count.
- Idempotency conflict count.
- API timeout, retry và rate limit.
- Outbox backlog và tuổi outbox row.
- Inbox/deduplication table growth.

Đặt tên log rõ mốc. Ví dụ `producer_acknowledged` không nên được dùng thay cho `business_processing_completed`. Nếu cần một trạng thái end-to-end, hãy xây dựng correlation/trace từ event ID xuyên qua producer, consumer và downstream.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Producer ACK nghĩa consumer đã nhận record | ACK chỉ xác nhận write theo acks |
| `acks=all` nghĩa mọi broker trong cluster xác nhận | Chỉ các replica trong ISR của partition liên quan |
| `send()` trả về nghĩa record đã được broker ghi | `send()` thường trả Future; phải quan sát kết quả Future/callback |
| Consumer `poll()` nhận record nghĩa xử lý xong | `poll()` chỉ giao record cho ứng dụng và tiến consumer position |
| Listener return luôn có nghĩa offset đã commit ngay | Phụ thuộc AckMode và container lifecycle |
| Commit offset là xác nhận database đã commit | Kafka group coordinator chỉ lưu checkpoint Kafka |
| Xử lý xong rồi commit bảo đảm không duplicate | Crash trước commit có thể khiến record được giao lại |
| Idempotent producer chống mọi duplicate nghiệp vụ | Nó bảo vệ retry của producer session, không khử lần gửi mới từ ứng dụng |
| Kafka transaction bao trùm database và REST API | Kafka transaction chỉ nguyên tử trong phạm vi Kafka |
| Exactly-once là một cờ cấu hình đơn lẻ | Cần xác định phạm vi, transaction boundary và hệ thống đích |

## 16. Checklist thiết kế

- [ ] Phân biệt rõ producer ACK, consumer delivery, business completion và offset commit.
- [ ] Chọn `acks` theo mức durability cần thiết.
- [ ] Đánh giá replication factor, ISR và `min.insync.replicas`.
- [ ] Dùng idempotent producer khi cần retry an toàn.
- [ ] Không ghi log producer ACK như thể nghiệp vụ đã hoàn tất.
- [ ] Phân biệt consumer position với committed position.
- [ ] Commit next offset sau khi side effect bắt buộc đã hoàn tất.
- [ ] Chấp nhận và xử lý duplicate theo at-least-once.
- [ ] Dùng event ID ổn định cho deduplication.
- [ ] Với Kafka-to-Kafka exactly-once, commit output và input offset trong cùng transaction.
- [ ] Dùng `isolation.level=read_committed` khi cần ẩn output transaction abort/chưa commit.
- [ ] Với database/API ngoài Kafka, dùng inbox/outbox/idempotency hoặc transaction boundary phù hợp.
- [ ] Cấu hình Spring Kafka AckMode và error handler phù hợp.
- [ ] Có failure test cho crash trước/sau ACK, processing và offset commit.
- [ ] Theo dõi producer retry, consumer lag, commit errors và downstream duplicate.

## 17. Tài liệu tham khảo

- [Apache Kafka 4.4 – Design: Message Delivery Semantics](https://kafka.apache.org/44/design/design/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Protocol: Produce Request and Acknowledgments](https://kafka.apache.org/44/design/protocol/)
- [Apache Kafka 4.4 – KafkaProducer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Apache Kafka 4.4 – KafkaConsumer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Spring Kafka – Message Listener Containers and Offset Commits](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)

Hãy luôn nói rõ ACK đến từ producer/broker, consumer container, database hay API ngoài. Khi các mốc được tách riêng, nhóm phát triển có thể chọn đúng durability, delivery semantics, retry và offset commit để bảo vệ dữ liệu trong từng failure window.
