# Tính bất biến và tính lũy đẳng trong xử lý sự kiện

Hệ thống event streaming thường phải chịu retry, consumer restart, rebalance và phát lại dữ liệu. Vì vậy, một event có thể được giao đến ứng dụng nhiều lần dù producer chỉ tạo ra một sự kiện nghiệp vụ. Nếu mỗi lần nhận đều tạo thêm side effect, hệ thống có thể trừ tiền hai lần, gửi thông báo lặp hoặc cập nhật read model sai.

Hai nguyên tắc giúp kiểm soát vấn đề này là **tính bất biến của event** và **tính lũy đẳng của xử lý**:

- Event bất biến mô tả một sự thật đã xảy ra. Khi cần sửa hoặc bổ sung thông tin, hệ thống phát event mới thay vì thay đổi event lịch sử.
- Xử lý lũy đẳng bảo đảm xử lý cùng một event nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương với xử lý một lần.

Hai nguyên tắc bổ trợ nhau nhưng không thay thế nhau. Event bất biến giúp lịch sử có thể kiểm tra và phát lại; idempotency bảo vệ hệ thống khỏi duplicate khi giao nhận hoặc xử lý lặp.

## 1. Phân biệt event bất biến và xử lý lũy đẳng

### 1.1. Event bất biến (immutable event)

Một event là bản ghi mô tả một điều đã xảy ra, ví dụ:

- `OrderCreated`: đơn hàng được tạo.
- `PaymentAuthorized`: khoản thanh toán được cấp phép.
- `OrderShipped`: đơn hàng đã được giao cho đơn vị vận chuyển.
- `AccountCredited`: tài khoản đã được ghi có.

Sau khi event được công bố, nội dung của nó nên được xem là bất biến. Nếu địa chỉ giao hàng được sửa, không chỉnh sửa event `OrderCreated` cũ; phát một event mới như `ShippingAddressChanged`. Nếu một giao dịch cần hoàn tiền, phát `PaymentRefunded` hoặc event nghiệp vụ tương ứng.

Event bất biến giúp:

- Giữ lại lịch sử thay đổi có thể kiểm toán.
- Tái tạo trạng thái bằng cách phát lại event.
- Phân tích nguyên nhân sự cố theo dữ liệu đã xảy ra.
- Cho phép nhiều consumer xây dựng các read model khác nhau.
- Tách dữ kiện lịch sử khỏi trạng thái hiện tại được tính toán.

### 1.2. Xử lý lũy đẳng (idempotent processing)

Một handler lũy đẳng bảo đảm cùng một event được xử lý nhiều lần không làm tăng thêm side effect.

Có thể biểu diễn đơn giản:

`apply(apply(state, event), event) = apply(state, event)`

Ví dụ, khi nhận `PaymentAuthorized` có event ID `evt-1001`, handler ghi nhận giao dịch vào database. Nếu Kafka giao lại event này sau khi consumer restart, handler nhận ra ID đã xử lý và không ghi nhận thanh toán lần thứ hai.

Idempotency cần được triển khai tại nơi tạo side effect. Kafka không thể tự biết hai lần gọi database hoặc API bên ngoài có phải cùng một nghiệp vụ hay không.

| Khái niệm | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Event bất biến | Sự kiện lịch sử có bị sửa sau khi công bố không? | Phát `OrderAddressChanged` thay vì sửa `OrderCreated` |
| Idempotent producer | Retry cùng request gửi Kafka có tạo record trùng không? | PID và sequence number |
| Idempotent consumer | Nhận lại cùng event có tạo side effect lần nữa không? | Inbox table có unique event ID |
| Idempotent API | Gọi lại cùng yêu cầu có tạo thao tác nghiệp vụ mới không? | HTTP Idempotency-Key |

## 2. Vì sao event có thể được xử lý nhiều lần?

Kafka lưu record trong partition log và consumer quản lý tiến độ bằng offset. Việc xử lý nghiệp vụ và commit offset thường không nằm trong cùng một transaction nếu đích xử lý là database hoặc dịch vụ bên ngoài.

Một tình huống điển hình:

1. Consumer đọc event tại offset 120.
2. Ứng dụng cập nhật database thành công.
3. Process bị dừng trước khi commit offset 121.
4. Consumer khởi động lại và đọc lại offset 120.
5. Database nhận cùng một nghiệp vụ lần thứ hai.

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant C as Consumer
    participant DB as Database

    K->>C: Event evt-1001, offset 120
    C->>DB: Ghi nhận thanh toán
    DB-->>C: Commit thành công
    Note over C: Process crash trước OffsetCommit
    K->>C: Giao lại event evt-1001
    C->>DB: Xử lý lại cùng event
    DB-->>C: Inbox nhận diện duplicate
    C->>K: Commit offset 121
~~~

Đây là một lý do phổ biến khiến consumer cần chịu được xử lý lặp. Ngoài crash, duplicate còn có thể đến từ:

- Producer retry sau khi acknowledgement bị mất.
- Ứng dụng gửi lại event sau timeout nhưng không biết lần gửi trước đã thành công hay chưa.
- Consumer group rebalance khi batch chưa được commit.
- Operator chủ động reset offset hoặc chạy replay bằng group mới.
- Retry topic hoặc dead-letter topic được đưa trở lại luồng xử lý.
- Một dịch vụ upstream phát cùng event nhiều lần.

Không nên xem duplicate là trường hợp bất thường hiếm gặp. Với hệ thống phân tán, thiết kế xử lý lũy đẳng thường đơn giản và bền vững hơn việc cố loại bỏ mọi khả năng giao nhận lặp.

## 3. At-most-once, at-least-once và exactly-once

Ba thuật ngữ mô tả số lần một record được xử lý hoặc tạo hiệu ứng trong một phạm vi nhất định.

| Semantics | Cách làm thường gặp | Đánh đổi |
|---|---|---|
| At-most-once | Commit offset trước khi xử lý | Có thể mất xử lý nếu process lỗi sau commit |
| At-least-once | Xử lý trước, commit offset sau | Có thể xử lý lặp nếu lỗi trước commit |
| Exactly-once | Kết hợp transaction hoặc cơ chế dedup ở đúng ranh giới | Phạm vi bảo đảm phụ thuộc hệ thống tham gia |

### 3.1. At-most-once

Nếu consumer commit offset trước khi thực hiện nghiệp vụ, Kafka sẽ xem record đã được tiêu thụ ngay cả khi ứng dụng gặp lỗi sau đó. Record có thể không được xử lý lại.

Cách này chỉ phù hợp khi bỏ sót một số record có thể chấp nhận, hoặc khi nguồn khác có thể tái tạo dữ liệu.

### 3.2. At-least-once

Nếu consumer xử lý xong rồi mới commit offset, record có thể được giao lại khi process gặp sự cố giữa hai thao tác. Đây là cách phổ biến vì ưu tiên không bỏ sót record.

Để side effect không bị lặp, handler cần idempotent. Ví dụ, ghi nhận event ID và cập nhật read model trong cùng database transaction.

### 3.3. Exactly-once có phạm vi cụ thể

Kafka hỗ trợ transaction cho luồng đọc-transform-ghi giữa các topic Kafka và offset consumer. Kafka Streams cũng cung cấp chế độ xử lý exactly-once phù hợp.

Tuy nhiên, Kafka transaction không tự bao trùm một transaction PostgreSQL, lời gọi REST, email hoặc thao tác thanh toán bên ngoài. Nếu ứng dụng ghi database rồi commit Kafka offset, hai thao tác đó không tự động trở thành một transaction nguyên tử.

Vì vậy, khi nói exactly-once, cần nêu rõ phạm vi: trong Kafka, trong một database, hay xuyên qua nhiều hệ thống. Với side effect bên ngoài, thường cần inbox/outbox, idempotency key hoặc cơ chế transaction được các hệ thống cùng hỗ trợ.

## 4. Thiết kế event bất biến với envelope rõ ràng

Một event nên có định danh và metadata đủ để consumer xử lý, kiểm tra duplicate và truy vết.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "PaymentAuthorized",
  "aggregateType": "Order",
  "aggregateId": "order-123",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-20T10:15:30Z",
  "schemaVersion": 1,
  "correlationId": "req-8f91",
  "data": {
    "paymentId": "pay-456",
    "amount": 1250000,
    "currency": "VND"
  }
}
~~~

Các trường có ý nghĩa:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất, ổn định qua retry và replay |
| `eventType` | Loại sự kiện nghiệp vụ |
| `aggregateType` | Loại thực thể phát sinh sự kiện |
| `aggregateId` | ID thực thể, thường cũng là Kafka key để giữ thứ tự theo thực thể |
| `aggregateVersion` | Phiên bản hoặc sequence nghiệp vụ của aggregate |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra |
| `schemaVersion` | Phiên bản cấu trúc payload |
| `correlationId` | Liên kết các hoạt động trong cùng request/flow |
| `data` | Dữ liệu nghiệp vụ của event |

### 4.1. Quy tắc tạo event ID

Event ID phải được tạo một lần cho một sự kiện nghiệp vụ và giữ nguyên qua mọi lần publish retry. Không tạo UUID mới mỗi lần producer gửi lại cùng một event đã lưu trong outbox.

Nếu event ID thay đổi theo mỗi lần retry, inbox của consumer không thể nhận ra đó là cùng một sự kiện.

Một event ID nên:

- Duy nhất trong phạm vi hệ thống hoặc namespace đã chọn.
- Ổn định trong outbox và các lần publish lại.
- Được truyền qua retry topic và dead-letter topic.
- Không phụ thuộc Kafka offset, vì offset là vị trí lưu trữ chứ không phải danh tính nghiệp vụ.

### 4.2. Sửa dữ liệu bằng event mới

Giả sử đơn hàng ban đầu có địa chỉ A, sau đó khách hàng đổi sang địa chỉ B. Không sửa record lịch sử `OrderCreated`; phát thêm:

~~~json
{
  "eventId": "evt-1002",
  "eventType": "ShippingAddressChanged",
  "aggregateId": "order-123",
  "aggregateVersion": 8,
  "data": {
    "previousAddress": "A",
    "newAddress": "B"
  }
}
~~~

Consumer có thể tái tạo trạng thái hiện tại bằng cách áp dụng các event theo thứ tự aggregate version. Event cũ vẫn giữ nguyên ý nghĩa tại thời điểm nó xảy ra.

## 5. Idempotency key và inbox pattern

Cách phổ biến để tạo consumer lũy đẳng là lưu event ID đã xử lý vào cùng database transaction với side effect.

Một bảng inbox tối thiểu:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa chính bảo đảm cùng một consumer không ghi nhận cùng event ID hai lần. Có thể thêm topic/partition/offset để truy vết nguồn record, nhưng không nên dùng offset làm idempotency key nghiệp vụ vì cùng event có thể được publish lại ở offset khác.

Luồng xử lý:

1. Bắt đầu database transaction.
2. Thử insert event ID vào inbox.
3. Nếu event ID đã tồn tại, bỏ qua side effect và kết thúc transaction.
4. Nếu insert thành công, thực hiện cập nhật nghiệp vụ.
5. Commit database transaction.
6. Sau khi batch xử lý thành công, commit Kafka offset.

~~~mermaid
flowchart TD
    A["Consumer nhận event"] --> B["BEGIN DB transaction"]
    B --> C["INSERT eventId vào inbox"]
    C --> D{"Insert mới?"}
    D -->|Không, đã tồn tại| E["Bỏ qua side effect"]
    D -->|Có| F["Cập nhật read model / nghiệp vụ"]
    F --> G["COMMIT DB transaction"]
    E --> H["Xử lý record thành công"]
    G --> H
    H --> I["Commit Kafka offset"]
~~~

Nếu process crash sau bước 5 nhưng trước bước 6, Kafka giao lại event. Lần xử lý sau, inbox phát hiện event ID đã tồn tại nên không lặp side effect; consumer có thể commit offset.

Nếu database transaction rollback, cả inbox insert và cập nhật nghiệp vụ đều rollback. Khi Kafka giao lại, event có thể được xử lý lại từ đầu.

### 5.1. Ví dụ SQL với PostgreSQL

~~~sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_id)
VALUES ('billing-projection', 'evt-1001')
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Ứng dụng kiểm tra số dòng được insert.
-- Chỉ khi insert mới thì thực hiện cập nhật nghiệp vụ.

UPDATE order_payment_projection
SET payment_status = 'AUTHORIZED'
WHERE order_id = 'order-123';

COMMIT;
~~~

Đoạn SQL minh họa ý tưởng; trong ứng dụng, chỉ chạy UPDATE khi INSERT thực sự tạo một dòng mới. Có thể kiểm tra row count từ JDBC hoặc dùng CTE/transaction logic để ràng buộc hai thao tác. Không được luôn UPDATE dù inbox insert đã conflict.

### 5.2. Ví dụ Java với JDBC

~~~java
public boolean processOnce(
        DataSource dataSource,
        String consumerName,
        String eventId,
        String orderId,
        String paymentStatus) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            int inserted;

            String inboxSql = """
                INSERT INTO processed_events (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """;

            try (PreparedStatement statement =
                     connection.prepareStatement(inboxSql)) {
                statement.setString(1, consumerName);
                statement.setString(2, eventId);
                inserted = statement.executeUpdate();
            }

            if (inserted == 0) {
                // Event đã xử lý trước đó; không lặp side effect.
                connection.commit();
                return false;
            }

            String updateSql = """
                UPDATE order_payment_projection
                SET payment_status = ?
                WHERE order_id = ?
                """;

            try (PreparedStatement statement =
                     connection.prepareStatement(updateSql)) {
                statement.setString(1, paymentStatus);
                statement.setString(2, orderId);
                statement.executeUpdate();
            }

            connection.commit();
            return true;

        } catch (SQLException exception) {
            connection.rollback();
            throw exception;
        }
    }
}
~~~

Phương thức trả về `false` khi event đã được xử lý. Caller vẫn xem record đó là đã xử lý thành công và có thể commit Kafka offset sau khi toàn bộ batch đạt yêu cầu.

Cách làm này dựa trên PostgreSQL `ON CONFLICT`; database khác có cú pháp upsert hoặc unique constraint tương ứng. Nếu cập nhật nhiều bảng, tất cả side effect thuộc cùng database nên nằm trong cùng transaction với inbox insert.

## 6. Commit offset sau database transaction

Với KafkaConsumer dùng manual commit, thứ tự thông thường là:

1. Poll record.
2. Xử lý record và commit database transaction.
3. Khi toàn bộ record trong batch đã xử lý thành công, commit offset Kafka.

Ví dụ rút gọn:

~~~java
ConsumerRecords<String, PaymentEvent> records =
    consumer.poll(Duration.ofMillis(500));

for (ConsumerRecord<String, PaymentEvent> record : records) {
    processOnce(
        dataSource,
        "billing-projection",
        record.value().eventId(),
        record.value().orderId(),
        "AUTHORIZED"
    );
}

if (!records.isEmpty()) {
    consumer.commitSync();
}
~~~

Nếu một record ném lỗi, không commit vượt qua record đó. Với nhiều partition, nếu xử lý song song, phải theo dõi offset liên tục đã hoàn tất theo từng partition; không lấy offset cao nhất hoàn thành rồi commit khi còn record trước đó chưa xử lý.

Mẫu trên ưu tiên at-least-once và dùng inbox để chống side effect lặp. Nó không tạo transaction nguyên tử giữa database và Kafka offset. Khoảng crash giữa DB commit và offset commit vẫn tồn tại, nhưng inbox giúp xử lý lại an toàn.

## 7. Producer idempotence, event ID và consumer inbox là ba lớp khác nhau

Ba cơ chế thường bị nhầm:

| Cơ chế | Phạm vi bảo vệ | Không bảo vệ |
|---|---|---|
| Kafka producer idempotence | Retry cùng batch trong producer session qua PID/epoch/sequence | Gửi lại event ở lần gọi mới, restart với PID mới hoặc hai producer độc lập |
| Event ID ổn định | Nhận diện cùng sự kiện nghiệp vụ qua retry, replay và nhiều hệ thống | Tự ngăn side effect nếu consumer không lưu/kiểm tra ID |
| Consumer inbox/dedup | Ngăn consumer thực hiện lại side effect đã ghi nhận trong cùng database transaction | Side effect bên ngoài database nếu không có idempotency hoặc transaction riêng |

Một hệ thống đáng tin cậy thường kết hợp cả ba:

- Producer idempotence giảm duplicate do retry giao thức.
- Event ID giữ danh tính sự kiện qua các ranh giới dịch vụ.
- Inbox bảo vệ database khi consumer nhận lại cùng event.

Không nên dựa vào Kafka offset làm event ID. Nếu cùng event được replay vào topic khác hoặc publish lại, offset sẽ khác dù sự kiện nghiệp vụ giống nhau.

## 8. Transactional outbox khi database là nguồn dữ liệu chính

Một service thường vừa cập nhật database vừa cần phát event Kafka. Nếu thực hiện hai thao tác riêng:

1. Commit database thành công.
2. Gửi Kafka thất bại.

Hệ thống có trạng thái nghiệp vụ mới nhưng không có event để các service khác biết.

Chiều ngược lại cũng có thể xảy ra: event gửi thành công nhưng database rollback. Đây là dual-write problem.

Transactional outbox giải quyết bằng cách ghi thay đổi nghiệp vụ và event vào cùng một database transaction:

~~~mermaid
flowchart TD
    A["Business command"] --> B["BEGIN DB transaction"]
    B --> C["Update business tables"]
    B --> D["Insert outbox event with stable eventId"]
    C --> E["COMMIT DB"]
    D --> E
    E --> F["Outbox relay / CDC"]
    F --> G["Publish event to Kafka"]
    G --> H["Mark published or advance CDC"]
~~~

Bảng outbox có thể gồm:

~~~sql
CREATE TABLE outbox_events (
    event_id       VARCHAR(160) PRIMARY KEY,
    aggregate_id   VARCHAR(160) NOT NULL,
    event_type     VARCHAR(160) NOT NULL,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at   TIMESTAMPTZ
);
~~~

Business update và outbox insert nằm trong cùng transaction. Nếu transaction rollback, cả hai đều không xuất hiện. Nếu commit, relay hoặc CDC có thể tiếp tục publish event kể cả khi service dừng ngay sau đó.

Outbox không tự bảo đảm chỉ publish đúng một lần. Relay có thể gửi event thành công rồi crash trước khi đánh dấu published, dẫn đến publish lại. Giữ nguyên event ID qua lần publish lại và yêu cầu consumer idempotent.

## 9. Kafka transaction cho luồng consume-transform-produce

Khi input và output đều là Kafka, có thể dùng transaction để ghi output và commit input offsets trong cùng transaction Kafka.

Luồng tổng quát:

1. Consumer đọc record từ input topic.
2. Ứng dụng transform record.
3. Transactional producer bắt đầu transaction.
4. Producer ghi output record.
5. Producer gửi consumer offsets vào transaction.
6. Commit transaction.
7. Nếu transaction abort, output và offset commit đều không được xem là đã commit.

Ví dụ cấu hình producer:

~~~properties
transactional.id=orders-transformer-0
enable.idempotence=true
acks=all
~~~

Ví dụ Java minh họa:

~~~java
producer.initTransactions();

while (running) {
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
            currentOffsetsAfter(records);

        producer.sendOffsetsToTransaction(
            offsets,
            consumer.groupMetadata()
        );

        producer.commitTransaction();

    } catch (Exception exception) {
        producer.abortTransaction();
        throw exception;
    }
}
~~~

Đây là skeleton minh họa; ứng dụng cần triển khai chính xác việc tính offset tiếp theo cho từng partition, xử lý rebalance và exception transaction theo phiên bản client. Consumer cần cấu hình:

~~~properties
isolation.level=read_committed
enable.auto.commit=false
~~~

Consumer đọc với `read_committed` chỉ thấy record thuộc transaction đã commit. Kafka transaction cung cấp atomicity trong phạm vi Kafka topics và consumer offsets được đưa vào transaction.

Kafka transaction không tự commit database hoặc API bên ngoài. Nếu transform có cập nhật database, cần inbox/outbox hoặc thiết kế phối hợp riêng.

Với Kafka Streams, có thể cấu hình `processing.guarantee=exactly_once_v2` ở phiên bản hỗ trợ để framework quản lý transaction và offset theo mô hình của Kafka Streams.

## 10. Giữ tính bất biến khi thay đổi schema

Event bất biến không có nghĩa schema không bao giờ được phát triển. Hệ thống có thể thêm trường, thay đổi cách biểu diễn hoặc giới thiệu event type mới, nhưng cần bảo đảm consumer cũ và dữ liệu lịch sử vẫn được hiểu đúng.

Một số nguyên tắc:

- Thêm field mới theo hướng backward-compatible khi có thể.
- Không đổi ý nghĩa của field cũ mà không thay version/contract.
- Dùng schema registry và compatibility policy nếu hệ thống có quản lý schema.
- Không tái sử dụng tên event cho một ý nghĩa nghiệp vụ khác.
- Nếu cần sửa sự thật đã công bố, phát event correction/compensation có liên kết event gốc.
- Consumer có thể dùng upcaster/adapter để chuyển schema cũ sang model nội bộ mới.

Ví dụ, thay vì sửa event `OrderCreated` cũ để thêm trạng thái thanh toán mới, phát `PaymentAuthorized`. Mỗi event giữ ý nghĩa tại thời điểm phát sinh.

Không nên lưu secret hoặc dữ liệu cá nhân không cần thiết vào event bất biến. Retention và compaction không phải cơ chế bảo đảm xóa dữ liệu theo yêu cầu pháp lý. Hãy thiết kế tối thiểu hóa dữ liệu, tokenization hoặc tham chiếu đến kho dữ liệu có chính sách quản lý phù hợp.

## 11. Ordering và version của aggregate

Idempotency không tự bảo đảm thứ tự nghiệp vụ. Hai event khác nhau có thể đến sai thứ tự do producer độc lập, retry, nhiều partition hoặc xử lý song song.

Để kiểm soát:

- Dùng `aggregateId` làm Kafka key để event của cùng aggregate vào cùng partition.
- Gắn `aggregateVersion` hoặc sequence nghiệp vụ tăng dần.
- Consumer kiểm tra version trước khi cập nhật state.
- Từ chối hoặc đưa vào retry khi phát hiện version bị thiếu hoặc cũ hơn.
- Không áp dụng event version 8 trước version 7 nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt.

Ví dụ update có điều kiện:

~~~sql
UPDATE order_projection
SET status = :new_status,
    version = :incoming_version
WHERE order_id = :order_id
  AND version = :incoming_version - 1;
~~~

Nếu update không tác động dòng nào, có thể event đã cũ, đã được áp dụng hoặc đang thiếu version trước đó. Ứng dụng cần phân biệt các trường hợp bằng cách đọc version hiện tại và áp dụng chính sách retry/ignore/alert phù hợp.

Không dùng timestamp đơn thuần làm cơ chế sắp thứ tự tuyệt đối. Đồng hồ giữa các producer có thể lệch và hai event có thể có timestamp bằng nhau.

## 12. Retry topic và dead-letter topic vẫn cần giữ event identity

Khi consumer xử lý lỗi, event có thể được đưa sang retry topic hoặc dead-letter topic (DLT). Khi re-drive từ retry/DLT, cần giữ nguyên:

- `eventId`.
- `aggregateId` và key.
- `aggregateVersion`.
- Loại event và schema version.
- Metadata truy vết như correlation ID và original topic/partition/offset.

Nếu retry handler tạo event ID mới cho cùng một event gốc, inbox sẽ xem đó là sự kiện mới và có thể thực hiện side effect lần nữa.

DLT nên bổ sung metadata lỗi như exception type, thời điểm lỗi, consumer group và số lần thử; không sửa nội dung event gốc. Khi sửa code rồi re-drive, handler idempotent vẫn cần bảo vệ trường hợp event đã được xử lý một phần trước đó.

## 13. Kiểm thử tính bất biến và lũy đẳng

Một bộ test hữu ích cần xác minh cả nội dung event và hành vi khi nhận trùng.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Gửi cùng event hai lần do retry | Gửi cùng event ID qua hai lần publish | Consumer chỉ tạo một side effect |
| Crash sau DB commit trước offset commit | Dừng consumer ngay sau database transaction | Record được giao lại nhưng inbox bỏ qua duplicate |
| Hai consumer xử lý cùng event đồng thời | Chạy song song hai handler với cùng event ID | Unique constraint chỉ cho một transaction thực hiện side effect |
| Replay bằng group mới | Đọc lại toàn bộ event lịch sử | Read model dựng lại đúng, không lặp external side effect |
| Event version đến sai thứ tự | Gửi version 8 trước version 7 | Handler phát hiện gap và áp dụng policy |
| Schema event cũ | Đọc fixture event version cũ | Adapter/upcaster chuyển đổi đúng |
| Outbox relay crash sau publish | Dừng relay trước khi mark published | Publish có thể lặp nhưng event ID giữ nguyên và consumer idempotent |
| Kafka transaction abort | Abort sau khi gửi output nhưng trước commit | Consumer read_committed không thấy output chưa commit |

Các test nên kiểm tra kết quả database, số side effect thực tế, event ID, offset và log/metric. Chỉ xác minh producer nhận acknowledgement không chứng minh consumer xử lý lũy đẳng.

## 14. Checklist thiết kế event processing

- [ ] Event mô tả sự thật đã xảy ra và không bị sửa sau khi công bố.
- [ ] Thay đổi hoặc correction được biểu diễn bằng event mới.
- [ ] Mỗi event có event ID duy nhất và ổn định qua retry/replay.
- [ ] Event envelope có aggregate ID, version, type và schema version phù hợp.
- [ ] Kafka key được chọn theo phạm vi cần giữ thứ tự.
- [ ] Consumer ghi inbox/dedup key cùng database transaction với side effect.
- [ ] Offset chỉ commit sau khi xử lý thành công theo từng partition.
- [ ] Xử lý duplicate sau crash giữa DB commit và offset commit.
- [ ] Producer idempotence không bị nhầm với business idempotency.
- [ ] Outbox được dùng khi database update và publish Kafka cần tránh dual-write.
- [ ] Kafka transaction được dùng cho atomicity trong phạm vi Kafka khi phù hợp.
- [ ] External API có idempotency key hoặc cơ chế chống lặp riêng.
- [ ] Retry/DLT giữ nguyên event ID và metadata nghiệp vụ.
- [ ] Ordering được bảo vệ bằng key và aggregate version nếu cần.
- [ ] Có test crash, retry, replay, duplicate đồng thời và transaction abort.
- [ ] Theo dõi duplicate count, retry rate, outbox backlog và processing lag.

Tính bất biến giữ cho event là lịch sử đáng tin cậy; tính lũy đẳng giúp ứng dụng có thể nhận và xử lý lại lịch sử đó mà không tạo side effect lặp. Kafka cung cấp các cơ chế hữu ích như producer idempotence, consumer offsets và transactions, nhưng mỗi cơ chế có phạm vi riêng. Một thiết kế vững chắc cần event ID ổn định, inbox/outbox ở ranh giới database, commit offset sau xử lý, cùng quy tắc ordering và retry phù hợp với nghiệp vụ.
