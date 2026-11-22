# Commit, rollback và redelivery trong Spring Integration

## 1. Câu hỏi quan trọng nhất: lỗi sau khi nhận message thì điều gì xảy ra?

Một hệ thống bán hàng gửi sự kiện `OrderPaid` tới dịch vụ kho. Consumer nhận thông điệp, trừ tồn kho, rồi báo với nguồn rằng message đã được xử lý. Mạng hoặc tiến trình có thể gặp lỗi ở bất kỳ bước nào:

1. Message đến listener nhưng handler chưa chạy.
2. Handler bắt đầu transaction và cập nhật database.
3. Database **commit**, nhưng listener chưa kịp gửi ACK hoặc commit offset.
4. Broker quyết định giao lại message vì lần xử lý trước chưa được xác nhận.

Nếu consumer xử lý lần hai như một đơn hàng hoàn toàn mới, một sự kiện có thể trừ tồn kho hai lần. Ngược lại, nếu consumer ACK quá sớm rồi database rollback, công việc có thể bị **mất xử lý** vì nguồn nghĩ rằng message đã hoàn tất.

**Commit, rollback và redelivery** phải được thiết kế đồng thời:

- **Commit** xác nhận thay đổi của *một transaction cụ thể* trên các tài nguyên tham gia.
- **Rollback** hủy những thay đổi *chưa commit* thuộc transaction đó; không tự thu hồi tác dụng phụ ở hệ thống khác.
- **Redelivery** là việc một nguồn đưa message cho consumer thêm lần nữa, thường sau lỗi, timeout, ngắt kết nối hoặc chưa xác nhận tiến độ.

Trong module `SPRING_INTEGRATION_PATTERN`, Spring Integration cho phép ghép Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation thành các luồng ít phụ thuộc. Tuy nhiên, message đi qua những pattern đó **không tự mang một transaction xuyên thread, process và broker**. Bài học giúp đặt transaction boundary, ACK, retry và idempotency đúng vị trí để một message được giao lại vẫn tạo kết quả nghiệp vụ chính xác.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Vẽ chính xác ranh giới **DB transaction**, **message source/broker transaction** và **ACK/offset**.
2. Phân biệt rollback của JDBC, rollback của JMS session, requeue của RabbitMQ và đọc lại theo Kafka offset.
3. Dự đoán hệ quả khi message gặp lỗi trước commit, sau commit nhưng trước ACK, hoặc sau ACK.
4. Cấu hình flow đồng bộ/transactional poller ở vị trí hợp lý, không nhầm queue in-memory với nguồn bền vững.
5. Xây dựng consumer idempotent với khóa sự kiện ổn định và kiểm thử retry/redelivery bằng failure injection.

## 2. Ba ranh giới cần phân biệt

### Transaction boundary

Một transaction quản lý một tập hoạt động được tài nguyên hỗ trợ, ví dụ các câu SQL dùng cùng `DataSource` và transaction manager. Spring thường mở/kết thúc transaction bằng `@Transactional`, `TransactionTemplate`, transaction interceptor hoặc advice của polling endpoint.

Với mô hình transaction imperative thông dụng, ngữ cảnh giao dịch được gắn với **thread đang thực thi**. Nếu downstream chạy qua `DirectChannel` trên cùng thread, handler có thể tham gia transaction đang mở. Nếu dùng `ExecutorChannel`, task thường chuyển sang thread khác; transaction ban đầu không tự đi theo.

### Delivery boundary

Một message có thể được nhận từ:

- `QueueChannel` trong bộ nhớ;
- persistent channel/message store trong database;
- JMS, RabbitMQ/AMQP hoặc Kafka;
- file, HTTP webhook hoặc một `MessageSource` khác.

Mỗi nguồn có cơ chế quyết định message có còn sẵn để nhận lại, đã bị xóa khỏi queue, đang chờ ACK, hay đã được đánh dấu offset. Không thể áp dụng quy tắc rollback của một nguồn cho tất cả nguồn khác.

### Acknowledgement boundary

ACK, commit JMS session, hoặc commit Kafka offset là tín hiệu về tiến độ *ở nguồn message*. DB commit là kết quả *ở tài nguyên nghiệp vụ*. Hai hành động có thể xảy ra ở thời điểm khác nhau.

| Sự kiện | Nói lên điều gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| `receive()` trả message | Consumer lấy/nhận được một message. | Handler đã xử lý xong hoặc dữ liệu đã commit. |
| `MessageChannel.send()` thành công | Channel chấp nhận message theo contract của nó. | Mọi worker bất đồng bộ đã xử lý xong. |
| JDBC `COMMIT` thành công | Các thay đổi JDBC tham gia transaction đã commit. | Broker đã ACK hoặc consumer khác đã nhận sự kiện. |
| JMS session commit | Những thao tác JMS tham gia JMS session transaction được commit. | Một database khác đã commit cùng nguyên tử. |
| RabbitMQ ACK | Delivery được xác nhận theo cơ chế broker. | Business DB độc lập đã commit. |
| Kafka offset commit | Consumer group có tiến độ offset đã được ghi nhận. | Side effect trên DB bên ngoài chắc chắn đã commit. |
| Redelivery | Message/record được chuyển lại để xử lý. | Lần xử lý trước chắc chắn chưa tạo side effect. |

**Quy tắc:** Khi đọc một flow, phải trả lời được “tài nguyên nào được rollback?”, “ai quyết định phát lại?” và “điểm xác nhận thực tế nằm ở đâu?”.

## 3. State machine của một message được nhận

~~~mermaid
flowchart TD
    A["Available tại source"] --> B["Delivered / In-flight"]
    B --> C["Consumer xử lý nghiệp vụ"]
    C --> D{"Business DB commit thành công?"}
    D -->|"Có"| E["Committed business effect"]
    D -->|"Không"| F["Business rollback"]
    E --> G{"Nguồn nhận ACK / offset commit?"}
    G -->|"Có"| H["Delivery hoàn tất"]
    G -->|"Không / mất kết nối"| I["Nguồn có thể redeliver"]
    F --> J{"Source policy"}
    J -->|"Retry / requeue"| I
    J -->|"Reject / DLQ"| K["Quarantine / dead letter"]
    I --> B
~~~

Sơ đồ mô tả một **mẫu vận hành**. Cách từng broker xác định in-flight, ACK, reject, requeue, retry và dead letter phụ thuộc adapter/container/configuration. Với nguồn không hỗ trợ redelivery (ví dụ queue thuần trong bộ nhớ), nhánh retry **không tự xuất hiện**.

### At-most-once, at-least-once và exactly-once

| Chiến lược | Đặc điểm | Rủi ro cần chấp nhận |
| --- | --- | --- |
| **At-most-once** | Có thể không xử lý lại sau lỗi; thường dùng cơ chế xác nhận sớm hoặc nguồn không bền vững. | Mất công việc khi lỗi xảy ra sau khi nguồn coi message đã được xử lý. |
| **At-least-once** | Có khả năng giao lại message chưa được xác nhận. | Một message có thể được xử lý **nhiều lần**; cần idempotency. |
| **Exactly-once trong một phạm vi cụ thể** | Một số hệ thống hỗ trợ giao dịch/khử trùng lặp trong phạm vi tài nguyên xác định. | Không tự bảo đảm **exactly-once end-to-end** giữa Kafka/JMS, database khác và external API. |

Trong hệ thống thực tế, mô hình **at-least-once delivery + idempotent business processing** thường dễ kiểm chứng hơn một lời hứa exactly-once xuyên nhiều hệ thống độc lập.

## 4. Timeline của ba cửa sổ lỗi quan trọng

### Kịch bản A — rollback trước khi DB commit

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C->>DB: BEGIN + UPDATE inventory
    DB-->>C: Lỗi SQL / business rule
    C->>DB: ROLLBACK
    Note over S,C: Error được truyền về source adapter
    C-->>S: Reject / rollback source transaction
    S->>C: Có thể redeliver theo policy
~~~

Nếu JDBC rollback thành công, thay đổi chưa commit trong transaction đó bị hoàn tác. **Message có được redeliver hay không** là vấn đề của source: nguồn phải còn giữ message/offset và có chính sách giao lại khi lỗi.

### Kịch bản B — DB commit rồi consumer sập trước ACK

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C->>DB: BEGIN + UPDATE inventory
    C->>DB: COMMIT
    DB-->>C: Commit OK
    Note over C: Crash trước ACK
    S->>C: Redeliver(eventId=E-17)
    C->>DB: Check processed_messages(E-17)
    DB-->>C: Đã xử lý
    C-->>S: ACK sau khi xác minh
~~~

Ở đây, rollback **không thể thu hồi** transaction DB đã commit. Redelivery là điều hợp lệ. Consumer phải nhận ra `E-17` đã xử lý và tránh thực hiện business effect lần thứ hai.

### Kịch bản C — ACK quá sớm rồi DB rollback

~~~mermaid
sequenceDiagram
    participant S as Source/Broker
    participant C as Consumer
    participant DB as Business DB
    S->>C: Deliver(eventId=E-17)
    C-->>S: ACK / commit offset
    C->>DB: BEGIN + UPDATE inventory
    DB-->>C: Lỗi
    C->>DB: ROLLBACK
    Note over S,C: Source có thể không redeliver
~~~

ACK sớm chỉ hợp lý nếu ứng dụng đã **chuyển trách nhiệm xử lý sang một nguồn bền vững khác**, ví dụ đã ghi message vào durable inbox trước khi ACK. Nếu chỉ giao message cho một executor in-memory rồi ACK, process crash có thể làm mất công việc.

## 5. Commit và rollback của Spring Transaction

### Transaction với JDBC

Ví dụ một application service:

~~~java
@Service
class InventoryApplicationService {
    private final JdbcTemplate jdbc;

    InventoryApplicationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserveStock(String sku, int quantity) {
        int updated = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, quantity, sku, quantity);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Insufficient stock for " + sku);
        }
    }
}
~~~

Nếu handler được gọi qua Spring proxy và `JdbcTemplate` sử dụng datasource thuộc transaction manager, một `RuntimeException` thoát ra thường làm transaction rollback. Nếu method hoàn tất bình thường, transaction interceptor có thể commit.

Một số lưu ý quan trọng:

1. `@Transactional` theo mặc định rollback với `RuntimeException` và `Error`; các **checked exception** cần xét `rollbackFor`/rollback rules.
2. Nếu catch exception rồi return bình thường, transaction có thể commit mặc dù nghiệp vụ thất bại; ngoại lệ là khi transaction đã bị đánh dấu `rollback-only` hoặc có lỗi commit riêng.
3. Lời gọi nội bộ `this.reserveStock(...)` thường không đi qua Spring proxy, nên advice của phương thức được gọi có thể không chạy.
4. `Propagation.REQUIRES_NEW` tạo một transaction độc lập; transaction con đã commit **không tự bị rollback** nếu transaction bao ngoài rollback sau đó.
5. Transaction của database không tự bao gồm gửi HTTP, publish broker, file move hoặc việc ACK message.

### Rollback-only và retry

Một transaction đã được đánh dấu `rollback-only` không thể "cứ retry thêm vài dòng SQL" là chắc chắn commit được. Với lỗi cần xử lý lại toàn bộ nghiệp vụ, thường phù hợp hơn là **mỗi attempt có một transaction mới**, đặt retry và transaction advice theo thứ tự rõ ràng.

~~~text
Retry boundary
  attempt 1 -> begin TX-1 -> handler -> rollback
  backoff
  attempt 2 -> begin TX-2 -> handler -> commit
~~~

Thực tế, thứ tự advice, transaction propagation và error handler của endpoint quyết định mỗi attempt có transaction riêng hay không. Với broker, retry in-memory tại consumer và redelivery từ broker là **hai tầng** có thể tương tác; phải tránh lặp vô hạn.

## 6. Vai trò của channel trong redelivery

| Thành phần Spring Integration | Khi chạy | Khi handler thất bại |
| --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ trên thread người gửi. | Exception thường đi ngược về sender/listener; transaction hiện hành có thể rollback nếu lỗi được truyền đúng. |
| `PublishSubscribeChannel` không executor | Gọi các subscriber đồng bộ. | Có thể có partial side effect ở subscriber đã chạy; rollback chỉ áp dụng cho tài nguyên tham gia transaction. |
| `ExecutorChannel` | Thường bàn giao xử lý sang thread worker. | Lỗi worker xảy ra sau lúc send; không tự khiến transaction/ACK phía sender rollback. |
| `QueueChannel` in-memory | Lưu message trong hàng đợi RAM để poller lấy sau. | JDBC rollback không tự trả message đã dequeue về RAM queue; restart có thể làm mất hàng đợi. |
| Persistent channel/message store | Lưu message trên một storage bền vững, có thể hỗ trợ transaction. | Phụ thuộc thao tác nhận/xóa, loại store, datasource và transaction manager; phải kiểm tra khả năng khôi phục. |
| Inbound adapter/listener | Nhận từ broker hoặc nguồn ngoài. | ACK/redelivery theo container/source và error propagation; không phải do channel quyết định độc lập. |

### Ví dụ luồng đồng bộ

~~~mermaid
flowchart LR
    A["Message-driven inbound"] --> B["DirectChannel"]
    B --> C["Transformer"]
    C --> D["Filter / Router"]
    D --> E["Business handler"]
    E --> F[("DB")]
    F --> G["Trả về listener"]
    G --> H["Nguồn quyết định ACK / retry"]
~~~

Đặt một `ExecutorChannel` trước business handler làm thay đổi mô hình:

~~~mermaid
flowchart LR
    A["Listener thread: receive"] --> B["ExecutorChannel.send()"]
    B --> C["Listener có thể kết thúc và ACK"]
    B -. "handoff" .-> D["Worker thread"]
    D --> E["Business handler trong TX khác"]
    E --> F[("DB")]
~~~

Một số executor có thể thực thi đồng bộ tùy cấu hình; cần kiểm tra `TaskExecutor` cụ thể. Với executor bất đồng bộ, nếu muốn ACK sau khi công việc **thật sự bền vững**, cần cơ chế phối hợp riêng hoặc lưu durable inbox trước khi ACK.

## 7. Transactional poller và sự khác biệt giữa DB rollback với dequeue

Spring Integration cho phép dùng transaction advice tại polling endpoint. Ví dụ:

~~~java
@Configuration
@EnableIntegration
class PollingConfiguration {
    @Bean
    QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow workFlow(
            PlatformTransactionManager transactionManager,
            InventoryConsumer consumer) {
        return IntegrationFlow.from(
                    "workQueue",
                    e -> e.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
                .handle(consumer, "process")
                .get();
    }
}
~~~

Đoạn DSL giả định `InventoryConsumer.process(...)` là phương thức public có payload tương thích và transaction manager được cấu hình phù hợp. Poller mở transaction quanh một lần poll và phần downstream **đồng bộ** trong phạm vi advice.

**Điểm dễ nhầm:** `QueueChannel(100)` trong ví dụ lưu message trong RAM. Transaction JDBC bao quanh handler **không** tự biến việc lấy một phần tử khỏi queue RAM thành thao tác giao dịch. Nếu handler thất bại:

- Những câu SQL tham gia JDBC transaction có thể rollback.
- Message đã lấy khỏi `QueueChannel` không mặc nhiên được put lại.
- Process crash có thể làm mất message đang chờ trong RAM.

Muốn có khả năng khôi phục, cần một **nguồn bền vững**: broker có ACK/redelivery, database-backed message store với giao dịch tương thích, hoặc bảng công việc có claim/lease và reclaim. Cần kiểm chứng atomicity giữa việc lấy/xóa message và ghi nghiệp vụ theo loại storage cụ thể.

### Polling nhiều message trong một transaction?

Các thiết lập như `maxMessagesPerPoll` quyết định số message được xử lý mỗi đợt poll, nhưng số message chia sẻ transaction còn phụ thuộc cách poller/transaction advice vận hành và cấu hình task. Tránh suy rằng toàn bộ batch đã commit/rollback cùng nhau chỉ từ tham số này. Đối với nghiệp vụ cần cô lập mỗi message, thử với `maxMessagesPerPoll(1)` và kiểm chứng transaction scope bằng integration test.

## 8. JMS, RabbitMQ và Kafka: ba kiểu redelivery khác nhau

### 8.1. JMS — rollback của session giao dịch

Trong JMS, listener container có thể dùng một **transacted JMS session**. Khi message được xử lý đồng bộ thành công, container có thể commit session; khi có exception phù hợp, container rollback JMS session và broker có thể giao message lại.

~~~text
JMS queue
  -> listener container (sessionTransacted = true)
  -> Spring Integration inbound adapter
  -> DirectChannel
  -> JDBC business handler

Lỗi handler -> lỗi truyền về listener
            -> rollback JMS session
            -> broker có thể redeliver
~~~

**JMS local transaction** và **JDBC transaction** là hai phạm vi riêng nếu không có cơ chế phối hợp được cấu hình. Có thể xảy ra:

- DB commit, nhưng JMS session rollback → redelivery cùng message.
- DB rollback, nhưng JMS session commit do lỗi bị nuốt → message không được phát lại.

Nếu muốn atomicity giữa JMS và một DB khác, phải đánh giá hỗ trợ **XA/JTA** từ provider, JDBC driver và transaction manager. Không tự suy rằng `sessionTransacted = true` đã đủ để đạt transaction chung.

### 8.2. RabbitMQ / AMQP — ACK, NACK, requeue và DLQ

RabbitMQ quản lý việc xác nhận các delivery. Tùy listener container/adapter, có thể:

- ACK khi công việc được xem là thành công.
- Reject/NACK sau lỗi, chọn requeue hoặc không.
- Dùng dead-letter exchange/queue để lưu message không thể xử lý.
- Redeliver message chưa ACK khi channel/connection của consumer bị đóng.

Các cấu hình cần kiểm tra theo adapter/version: acknowledgement mode, prefetch, retry interceptor, error handler, default requeue policy, dead-letter configuration và consumer concurrency.

**Ví dụ:** consumer ghi DB commit thành công nhưng mất connection trước khi ACK. Broker có thể giao lại message; **consumer phải idempotent**. Ngược lại, nếu một error handler tiêu thụ exception và container xem invocation là thành công, container có thể ACK một message dù nghiệp vụ không hoàn tất.

Transaction hoặc confirm ở broker không tự trở thành transaction của JDBC datasource. Cần phân biệt publisher confirm, consumer acknowledgement và local transaction của broker, bởi chúng phục vụ các thời điểm và trách nhiệm khác nhau.

### 8.3. Kafka — offset và đọc lại record

Kafka lưu record trong log và theo dõi tiến độ tiêu thụ bằng **offset** của consumer group. Không có thao tác “đưa message về đầu queue” theo nghĩa giống một số broker khác: record vẫn nằm trong log theo retention; việc đọc lại phụ thuộc offset, partition, consumer group và chính sách retry.

Ví dụ:

1. Consumer đọc record offset 120.
2. Handler cập nhật PostgreSQL và commit DB.
3. Process sập trước khi offset tương ứng được commit.
4. Consumer tiếp theo có thể đọc lại offset 120.

Kafka transaction hỗ trợ atomicity cho một số luồng **Kafka-read → Kafka-write** và thao tác offset theo cơ chế Kafka được cấu hình thích hợp. Nó **không tự** làm PostgreSQL trở thành tài nguyên của Kafka transaction. Vì thế, với consumer ghi database, cần idempotency/inbox và cấu hình offset commit phù hợp.

### So sánh ngắn

| Nguồn | “Đã xử lý” thường được xác định qua | Điều kiện phổ biến gây xử lý lại | Cần kiểm tra |
| --- | --- | --- | --- |
| JMS | Commit/ACK của session theo container. | Session rollback hoặc connection lỗi trước commit. | Transaction mode, exception propagation, redelivery policy, DLQ. |
| RabbitMQ | Consumer ACK. | NACK/requeue, reject policy, connection mất khi chưa ACK. | ACK mode, prefetch, requeue, DLX/DLQ, retry. |
| Kafka | Offset commit/tiến độ consumer group. | Offset chưa được ghi nhận, rebalance hoặc retry/seek. | Ack/commit mode, offset, partition, retry handler, DLT. |
| DB work queue | Trạng thái row/claim/lease hoặc thao tác dequeue. | Chưa ghi trạng thái bền vững, claim hết hạn, transaction rollback. | Isolation, khóa, lease, reclaim và atomicity. |

## 9. Lỗi đi qua error channel ảnh hưởng commit như thế nào?

Với các flow đồng bộ qua `DirectChannel`, exception từ Filter, Transformer, Router, Service Activator hoặc handler thường có thể lan về inbound adapter hay caller. Nhưng khi chuyển sang `ExecutorChannel`, poller hay nguồn message-driven, lỗi có thể được đóng gói thành `ErrorMessage` và chuyển tới `errorChannel` theo cấu hình.

Điều cần xác định **không chỉ là errorChannel có nhận lỗi hay không**, mà là:

1. Transaction interceptor quan sát exception hay kết quả thành công?
2. Inbound listener có nhận được exception để rollback/NACK hay không?
3. Error flow đã xử lý lỗi rồi return bình thường hay ném lại?
4. Việc ACK xảy ra trước hay sau khi exception được xử lý?

| Hành vi | Kết quả có thể xảy ra |
| --- | --- |
| Exception từ handler đồng bộ đi ra ngoài `@Transactional`. | DB rollback theo rollback rules. |
| Handler bắt exception và chỉ log rồi return. | DB có thể commit; listener có thể ACK nếu coi là thành công. |
| Error flow đưa lỗi vào DLQ rồi hoàn tất bình thường. | Delivery ban đầu có thể được xem là đã xử lý; phù hợp nếu DLQ lưu bền vững và chính sách chấp nhận điều đó. |
| Async worker lỗi sau khi caller đã ACK. | Lỗi không tự gây redelivery từ nguồn ban đầu. |
| Retry cục bộ hết số lần và lỗi được ném ngược listener. | Broker có thể redeliver hoặc dead-letter theo policy. |

### Anti-pattern: nuốt lỗi rồi mong rollback

~~~java
@Transactional
public void processBadly(ReserveInventory event) {
    try {
        inventoryService.apply(event);
    } catch (RuntimeException exception) {
        log.warn("Reserve failed, orderId={}", event.orderId(), exception);
        // Nếu không ném lỗi và transaction chưa rollback-only,
        // lời gọi có thể được coi là thành công.
    }
}
~~~

Khi nghiệp vụ muốn nguồn phát lại, lỗi phải **đến đúng boundary có khả năng yêu cầu retry/redelivery**. Tuy vậy, không được ném mọi lỗi vô thời hạn: message sai schema hoặc vi phạm quy tắc nghiệp vụ có thể thành poison message và làm nghẽn consumer.

## 10. Retry, redelivery và dead-letter: đặt trách nhiệm ở đâu?

Phân biệt:

- **Retry trong handler**: gọi lại xử lý trước khi trả kết quả cho listener. Có thể cùng delivery nhưng nhiều attempt.
- **Redelivery từ broker/source**: nguồn giao lại message vì delivery trước không được xác nhận hoặc bị từ chối.
- **Replay vận hành**: chủ động phát lại event từ DLQ, durable inbox, outbox hoặc event log.

| Nhóm lỗi | Cách xử lý thường phù hợp | Giới hạn |
| --- | --- | --- |
| DB mất kết nối ngắn | Retry hữu hạn với exponential backoff và jitter nếu thích hợp. | Đặt transaction mới cho attempt phù hợp, tránh reuse rollback-only transaction. |
| Broker/network timeout | Retry nếu có định danh sự kiện ổn định và idempotency. | Timeout không có nghĩa phía nhận chắc chắn chưa xử lý. |
| Payload sai schema | Reject/quarantine/DLQ với nguyên nhân rõ. | Retry vô hạn không sửa được dữ liệu sai. |
| Không đủ tồn kho | Quyết định theo nghiệp vụ: từ chối có kiểm soát, lưu kết quả thất bại, hoặc đợi thay đổi trạng thái. | Không mặc định retry vô hạn. |
| Consumer chết sau DB commit | Source redeliver khi chưa ACK; consumer kiểm tra event ID. | Phải chứng minh không tạo side effect hai lần. |
| Một nhánh Splitter thất bại | Retry riêng từng nhánh, timeout, trạng thái partial; Saga/compensation nếu cần. | Rollback một transaction cục bộ không hoàn tác nhánh khác đã commit. |

### Dead-letter không có nghĩa là “xóa lỗi”

DLQ hoặc dead-letter topic là nơi lưu message chưa thể xử lý để **quan sát, phân loại, sửa dữ liệu và replay**. Cần theo dõi message gốc, `eventId`, nguyên nhân lỗi, attempt count, thời gian lỗi, endpoint và phiên bản schema. Khi replay phải giữ nguyên định danh sự kiện hoặc có quy tắc chuyển đổi rõ ràng để idempotency không bị phá.

Một chính sách thường thấy:

~~~text
Receive
  -> Validate schema
     -> Permanent error: quarantine / DLQ
  -> Start business transaction
     -> Temporary failure: rollback + bounded retry/backoff
     -> Success: commit
  -> Complete delivery using source ACK/offset policy

After retries exhausted:
  -> durable error record / DLQ
  -> alert + manual/automatic replay with deduplication
~~~

Không nên giả định việc đưa message vào DLQ của một hệ thống bên ngoài **nguyên tử** với DB rollback; nếu điều đó là yêu cầu nghiệp vụ, phải thiết kế cơ chế lưu trạng thái bền vững và khôi phục tương ứng.

## 11. Xử lý trùng an toàn: idempotent consumer với PostgreSQL

Mẫu **idempotent consumer** lưu ID sự kiện đã hoàn tất cùng transaction với business update. Nếu nhận lại cùng message, consumer trả về bình thường sau khi xác nhận đã xử lý.

### Thiết kế dữ liệu

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE processed_messages (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa `(consumer_name, event_id)` cho phép các consumer nghiệp vụ khác nhau xử lý cùng event một cách độc lập. Nếu chỉ một consumer, có thể dùng `event_id` làm khóa duy nhất.

### Payload và handler

~~~java
record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}

@Service
class InventoryConsumer {
    private static final String CONSUMER_NAME = "inventory-reservation";

    private final JdbcTemplate jdbc;

    InventoryConsumer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void process(ReserveInventory event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid inventory event");
        }

        // PostgreSQL: unique key xử lý cả delivery lặp đồng thời.
        int claimed = jdbc.update("""
                INSERT INTO processed_messages(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """, CONSUMER_NAME, event.eventId());

        if (claimed == 0) {
            // Cùng event đã commit trong lần xử lý trước.
            return;
        }

        int changed = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                event.quantity(), event.sku(), event.quantity());

        if (changed != 1) {
            throw new IllegalStateException(
                    "Cannot reserve stock for " + event.sku());
        }
    }
}
~~~

**Tại sao chèn `processed_messages` trước khi cập nhật tồn kho?** Vì *cả hai lệnh SQL* cùng nằm trong một DB transaction:

- Nếu cập nhật thất bại, exception làm transaction rollback, **dấu đã xử lý cũng bị rollback**. Lần redelivery sau vẫn có thể thử lại.
- Nếu cập nhật và commit thành công, delivery tiếp theo nhìn thấy khóa đã tồn tại và **không giảm tồn kho thêm**.
- Khi hai worker xử lý cùng event đồng thời, unique constraint và cơ chế transaction/locking của database phối hợp ngăn cả hai commit business effect cho cùng khóa.

Lệnh `ON CONFLICT ... DO NOTHING` là cú pháp PostgreSQL; thay bằng upsert/conflict handling phù hợp nếu dùng DB khác. Không dùng mẫu `SELECT` rồi `INSERT` không được bảo vệ vì hai worker có thể cùng đọc “chưa tồn tại”.

### Đặt handler vào một IntegrationFlow đồng bộ

~~~java
@Configuration
@EnableIntegration
class InventoryFlowConfiguration {
    @Bean("inventoryInput")
    MessageChannel inventoryInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reserveInventoryFlow(InventoryConsumer consumer) {
        return IntegrationFlow.from("inventoryInput")
                .handle(consumer, "process")
                .get();
    }
}
~~~

Ví dụ trên minh họa **một nhánh xử lý đồng bộ**, không tự cấu hình inbound broker hoặc ACK. Nếu một listener adapter gửi message vào `inventoryInput` và chờ handler kết thúc, lỗi có thể truyền lại theo hợp đồng adapter. Phải bổ sung cấu hình riêng cho JMS/RabbitMQ/Kafka phù hợp bản Spring Integration và chính sách nguồn.

### Những giới hạn của idempotency

1. `eventId` phải **ổn định** khi retry/redelivery; không sinh UUID mới ở mỗi attempt xử lý cùng message.
2. `consumer_name` xác định **phạm vi nghiệp vụ** áp dụng unique constraint; không dùng chung sai giữa các consumer khác nhau.
3. Dấu đã xử lý và thay đổi nghiệp vụ phải cùng transaction trên tài nguyên thích hợp.
4. Side effect bên ngoài như email/HTTP không tự rollback cùng hai lệnh SQL; với outbound event quan trọng nên ghi **outbox record** cùng business update.
5. Nếu cùng `eventId` nhưng payload mâu thuẫn, cần phát hiện và cảnh báo (ví dụ lưu payload hash hoặc version), tránh âm thầm bỏ qua message bị sửa sai.
6. Với business rule không đủ tồn kho, cần phân biệt kết quả thất bại **vĩnh viễn** và lỗi **tạm thời** để quyết định lưu trạng thái, DLQ hay retry.

## 12. Khi consumer còn phải phát sự kiện: inbox kết hợp outbox

Ví dụ một message `PaymentConfirmed` làm DB cập nhật đơn và cần phát `OrderReady`. Nếu consumer trực tiếp publish broker **trong** DB transaction, có thể xảy ra broker đã nhận message nhưng DB rollback. Nếu publish **sau** DB commit, có thể mất event khi process sập trước khi publish.

Mẫu an toàn hơn trong một database:

~~~mermaid
flowchart LR
    A["Inbound broker"] --> B["Consumer"]
    subgraph TX["Một DB transaction"]
      C["INSERT processed_messages"] --> D["UPDATE orders"]
      D --> E["INSERT outbox_events"]
    end
    B --> C
    E --> F[("Committed DB")]
    F --> G["Outbox relay"]
    G --> H["Outbound broker"]
    H --> I["Idempotent downstream consumer"]
~~~

Các bước:

1. Nhận message và kiểm tra khóa idempotency.
2. Trong **cùng transaction DB**, đánh dấu đã xử lý, thay đổi dữ liệu nghiệp vụ và ghi outbox event.
3. Commit DB; listener hoàn thành việc xác nhận nguồn theo chính sách phù hợp.
4. Relay đọc outbox đã commit và publish với `eventId` cố định.
5. Sau khi broker xác nhận theo protocol, relay đánh dấu đã gửi; có thể publish lại nếu crash trước lúc đánh dấu.

Inbox/outbox giải quyết hai mặt của reliability: **đầu vào xử lý trùng** và **đầu ra không bỏ quên ý định gửi**. Nó vẫn đòi hỏi giám sát backlog và consumer idempotent; broker và DB không trở thành một transaction phân tán chỉ vì áp dụng mẫu này.

## 13. Router, Filter, Splitter, Aggregator: rollback đến đâu?

Trong flow phức tạp, một message có thể rẽ nhánh:

~~~mermaid
flowchart LR
    A["Gateway hoặc inbound adapter"] --> B["Transformer"]
    B --> C{"Router"}
    C --> D["Filter + DirectChannel"]
    C --> E["Splitter"]
    D --> F["Handler A: JDBC"]
    E --> G["ExecutorChannel / workers"]
    G --> H["Handler B: remote"]
    F --> I["Aggregator"]
    H --> I
~~~

- **Transformer** có thể thất bại do payload sai. Nếu chạy đồng bộ trong consumer boundary và exception truyền ngược, transaction có thể rollback, nguồn có thể redeliver theo policy.
- **Filter** thường loại message theo chính sách nghiệp vụ và kết thúc flow **thành công**. Nếu message bị loại trong khi inbound adapter ACK, nó có thể không được giao lại. Nếu đây là lỗi, hãy đi vào nhánh lỗi có chủ đích.
- **Router** chọn nhánh. Nhánh qua `DirectChannel` có thể còn trong transaction thread hiện tại; nhánh chuyển sang executor/broker thường có transaction riêng.
- **Splitter** tạo nhiều message con. Nếu các nhánh chạy trên thread hoặc service khác nhau, không có một rollback cục bộ mặc định xóa được tất cả side effect đã commit.
- **Aggregator** cần correlation key, release strategy và store phù hợp. Khi một nhánh redeliver, aggregator cần chống kết quả lặp, xử lý message tới trễ và timeout; một correlation ID không làm transaction các nhánh trở thành nguyên tử.
- **Gateway** đồng bộ chỉ trả về kết quả của những bước đã hoàn tất trước khi return; một nhánh bất đồng bộ có thể vẫn đang chạy dù người gọi đã nhận ACK/response.

### Correlation, message ID và business event ID

| ID | Mục đích | Dùng để dedupe business side effect? |
| --- | --- | --- |
| `MessageHeaders.ID` | Định danh message instance trong Spring Integration. | Không nên phụ thuộc duy nhất; message mới tạo khi retry có thể mang ID khác. |
| `correlationId` hoặc `orderId` | Nhóm các message cùng workflow/đơn hàng. | Chỉ khi domain quy định chính xác phạm vi duy nhất của công việc. |
| `eventId` nghiệp vụ | Định danh **một sự kiện** ổn định qua redelivery. | Thường phù hợp làm khóa idempotency của consumer. |
| `sequenceNumber` | Thứ tự message con trong Splitter/Aggregator. | Không tự thay thế event ID hoặc transaction ID. |

Nếu nghiệp vụ cần nhiều bước có thể commit riêng, dùng Saga/compensation và lưu tiến độ. Compensation là **thao tác nghiệp vụ mới** (ví dụ hoàn tiền sau khi đã thu tiền), không phải rollback của transaction ở dịch vụ khác.

## 14. Kiểm thử hành vi rollback và redelivery

### 14.1. Kiểm thử idempotency trong database

Với schema và `InventoryConsumer` đã trình bày:

~~~java
@SpringBootTest
class InventoryConsumerIT {
    @Autowired InventoryConsumer consumer;
    @Autowired JdbcTemplate jdbc;

    @Test
    void redeliveryDoesNotReserveTwice() {
        String sku = "SKU-" + UUID.randomUUID();
        String eventId = UUID.randomUUID().toString();

        jdbc.update(
                "INSERT INTO inventory(sku, available) VALUES (?, ?)",
                sku, 10);

        ReserveInventory message =
                new ReserveInventory(eventId, "ORDER-1", sku, 3);

        consumer.process(message);
        consumer.process(message); // Mô phỏng redelivery.

        Integer available = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, sku);

        Integer processedCount = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_messages
                WHERE consumer_name = ? AND event_id = ?
                """, Integer.class, "inventory-reservation", eventId);

        assertEquals(7, available);
        assertEquals(1, processedCount);
    }

    @Test
    void rollbackKeepsEventEligibleForRetry() {
        String sku = "SKU-" + UUID.randomUUID();
        String eventId = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO inventory(sku, available) VALUES (?, ?)",
                sku, 2);

        assertThrows(IllegalStateException.class,
                () -> consumer.process(new ReserveInventory(
                        eventId, "ORDER-2", sku, 5)));

        Integer markers = jdbc.queryForObject("""
                SELECT COUNT(*) FROM processed_messages
                WHERE consumer_name = ? AND event_id = ?
                """, Integer.class, "inventory-reservation", eventId);
        assertEquals(0, markers);
    }
}
~~~

Ví dụ giả định đã có Spring Boot test, JUnit Jupiter, schema và datasource. Không gắn `@Transactional` lên chính test nếu điều đó khiến transaction bao ngoài che mất kết quả commit/rollback của handler. Hai kiểm thử trên chứng minh tính idempotent và rollback **ở DB**, chưa chứng minh nguồn thực sự redeliver.

### 14.2. Kiểm thử nguồn message thật

Để xác nhận redelivery, cần integration test với broker/container thực và cấu hình ACK cụ thể:

| Kịch bản chèn lỗi | Cần quan sát | Tiêu chí đạt |
| --- | --- | --- |
| Handler ném exception **trước** DB commit. | DB state, ACK/NACK/offset, số delivery. | Không có business row commit; retry/DLQ đúng policy nguồn. |
| Handler commit DB, consumer mất kết nối **trước** ACK. | Message được giao lại và số lần business effect. | Source có thể redeliver; side effect chỉ áp dụng một lần. |
| Consumer ACK/commit offset **trước** DB commit rồi crash. | Có message tồn đọng/được giao lại không? | Nhận ra rủi ro mất công việc; sửa thứ tự hoặc dùng durable inbox. |
| Một worker nhận message lặp đồng thời với worker khác. | Unique constraint, transaction isolation và kết quả tồn kho. | Chỉ một business effect được commit. |
| Retry liên tiếp vì SQL error. | Transaction mới mỗi attempt, backoff, số lần retry. | Không vượt retry budget, không giữ transaction lỗi. |
| Message poison (schema sai). | DLQ, error record, consumer backlog. | Không retry vô hạn; có thể khôi phục/replay có kiểm soát. |
| Handler qua `ExecutorChannel` lỗi sau listener return. | ACK ban đầu, error channel và trạng thái task. | Hiểu rõ giới hạn async, có durable handoff hoặc thiết kế lại ACK. |
| Splitter tạo nhiều nhánh, một nhánh thất bại. | Correlation, duplicate, aggregator timeout, compensation. | Không mất hoặc đếm trùng kết quả; xử lý partial failure rõ ràng. |

Testcontainers với JMS/RabbitMQ/Kafka có thể giúp dựng môi trường kiểm thử sát thực tế, nhưng phải kiểm tra broker, adapter và framework version được dự án sử dụng. Với các ca crash, thường cần điều khiển điểm dừng **sau DB commit trước ACK** bằng hook/fixture rõ ràng, rồi khởi động lại consumer và kiểm tra dữ liệu.

## 15. Quan sát vận hành

Hệ thống đáng tin cậy cần giải thích được *vì sao* một message được redeliver. Nên ghi nhận:

- `eventId` nghiệp vụ ổn định; `orderId` và `correlationId` nếu có nhiều nhánh.
- Tên endpoint/channel, consumer group hoặc queue; partition/offset hay delivery tag nếu nguồn cung cấp.
- Thời điểm `received`, `business_committed`/`rolled_back`, `acknowledged`/`offset_committed`.
- Số lần thử cục bộ, redelivery count, kết quả dedupe và loại exception.
- Số message chờ xử lý, độ trễ từ publish đến commit nghiệp vụ, DLQ size/age và tỷ lệ retry thành công.

Không log dữ liệu nhạy cảm trong payload. Một log `"received message"` hoặc `"send true"` không đủ chứng minh transaction hoặc xử lý end-to-end đã hoàn tất.

### Chỉ số điều tra sự cố

| Dấu hiệu | Nghi vấn cần kiểm tra |
| --- | --- |
| Redelivery tăng mạnh | Consumer rollback liên tục, ACK lỗi, rebalance hoặc crash lặp lại. |
| Duplicate skip tăng đột biến | Source redelivery nhiều hoặc producer publish lại cùng event. |
| Queue depth / Kafka lag tăng | Consumer quá chậm, stuck transaction, poison message hoặc thiếu tài nguyên. |
| DLQ tồn đọng lâu | Chưa có quy trình xử lý/replay hoặc lỗi schema khó sửa. |
| DB có bản ghi nhưng event downstream thiếu | Dual write lỗi, thiếu outbox, callback sau commit bị mất hoặc relay tắc. |
| Nhiều xử lý trùng dù có bảng dedupe | eventId thay đổi theo retry, phạm vi khóa sai hoặc side effect nằm ngoài transaction. |

## 16. Chọn cấu trúc phù hợp với yêu cầu

| Yêu cầu | Mẫu thiết kế | Rủi ro cần kiểm chứng |
| --- | --- | --- |
| Xử lý tạm thời trong cùng process, chấp nhận mất dữ liệu khi restart | `QueueChannel` trong bộ nhớ + poller. | Dequeue không rollback cùng JDBC; crash có thể mất message. |
| DB-backed work queue cùng DB nghiệp vụ | Transactional poller + store/claim có transaction phù hợp. | Isolation, lease, concurrency, reclaim và commit cùng tài nguyên. |
| Nhận từ JMS/RabbitMQ/Kafka và ghi DB | Inbound adapter đồng bộ + DB transaction + idempotent consumer; ACK theo nguồn. | Crash sau DB commit trước ACK, broker-specific retry và DLQ. |
| Consumer xử lý nền nhưng listener cần ACK sớm | Durable inbox/queue handoff rồi ACK. | ACK chỉ sau khi dữ liệu đã được lưu bền vững. |
| Business event mới phải phát ra sau cập nhật DB | Cùng transaction ghi outbox, relay và consumer idempotent. | Publisher gửi trùng sau crash; cần retry và giám sát backlog. |
| Router/Splitter nhiều service, Aggregator cần chờ kết quả | Transaction ở từng consumer + correlation + persistent state + compensation. | Partial commit, timeout, message trễ và duplicate. |

Trong hệ thống nhiều tài nguyên, **commit cục bộ ngắn + nguồn bền vững + idempotency + retry có giới hạn** thường tạo mô hình khôi phục rõ ràng. Một transaction dài qua lời gọi mạng không tự thêm được bảo đảm nguyên tử và có thể làm tăng thời gian giữ connection/lock.

## 17. Bài tập vận dụng

**Bài 1 — vẽ hai transaction.** Với `RabbitMQ listener → DirectChannel → InventoryConsumer @Transactional → PostgreSQL`, vẽ timeline nhận, commit DB, ACK. Nếu process sập ngay sau DB commit, dự đoán broker và handler sẽ làm gì khi cùng message được giao lại.

**Bài 2 — kiểm chứng QueueChannel.** Tạo `QueueChannel(100)` và poller dùng `.transactional(transactionManager)`. Trong handler, ghi một bản ghi rồi ném lỗi. Quan sát DB rollback và số phần tử còn trong queue. Giải thích vì sao kết quả không thể dùng để khẳng định redelivery bền vững.

**Bài 3 — poison message.** Gửi một payload thiếu `eventId` hoặc quantity không hợp lệ. Thiết kế lỗi vĩnh viễn đi DLQ thay vì retry vô hạn; cung cấp quy trình sửa schema và replay message theo cùng business key.

**Bài 4 — hai delivery đồng thời.** Cho hai worker cùng nhận `ReserveInventory(eventId="E-17")`. Dùng unique constraint và transaction để chứng minh chỉ một worker làm thay đổi tồn kho; kiểm tra xử lý khi worker đầu rollback.

**Bài 5 — inbox và outbox.** Consumer nhận `PaymentConfirmed`, cập nhật `orders` và ghi `OrderReady` vào outbox. Giả lập relay publish thành công rồi sập trước khi đánh dấu `SENT`. Khi relay chạy lại, chứng minh consumer downstream vẫn chỉ thực hiện nghiệp vụ một lần.

### Tự kiểm tra hiểu biết

**1. JDBC rollback có tự làm RabbitMQ đưa message trở lại không?** Không. Redelivery phụ thuộc listener/container ACK/NACK/requeue; JDBC rollback chỉ tác động đến tài nguyên JDBC tham gia.

**2. Vì sao DB đã commit vẫn có thể gặp redelivery?** Nguồn chưa nhận ACK hoặc offset chưa commit, chẳng hạn process sập sau DB commit trước ACK.

**3. Đặt `@Transactional` trên handler có tự bao gồm Kafka offset commit không?** Không mặc định. Offset thuộc cơ chế Kafka/adapter, còn JDBC transaction manager quản lý database.

**4. `DirectChannel` bảo đảm điều gì?** Dispatch đồng bộ trên cùng thread, giúp exception và transaction context của caller có thể liên quan đến handler; không bảo đảm side effect ngoài JDBC cùng rollback.

**5. Chống trùng tốt nhất nên dùng ID nào?** Một `eventId` nghiệp vụ ổn định qua redelivery, với unique constraint trong transaction cùng thay đổi nghiệp vụ; không dựa vào việc mỗi lần chuyển message có cùng `MessageHeaders.ID`.

**6. Khi nào cần DLQ?** Khi message không thể xử lý sau retry hữu hạn hoặc không hợp lệ vĩnh viễn; cần giữ thông tin lỗi để sửa và replay có kiểm soát.

## 18. Checklist trước khi đưa consumer vào production

- [ ] Xác định nguồn message là in-memory, persistent store, JMS, RabbitMQ, Kafka, HTTP hay loại khác.
- [ ] Vẽ ranh giới transaction và chỉ rõ tài nguyên được commit/rollback bởi từng transaction manager.
- [ ] Biết listener/poller bắt đầu và kết thúc xử lý vào thời điểm nào; xác định ACK/offset policy.
- [ ] Kiểm tra điểm chuyển thread ở `ExecutorChannel` và mọi nhánh xử lý bất đồng bộ.
- [ ] Phân biệt handler rollback với source rollback/requeue; kiểm chứng redelivery thực tế.
- [ ] Không ACK trước khi nghiệp vụ hoàn tất **hoặc** được lưu bền vững tại một điểm handoff có thể phục hồi.
- [ ] Đảm bảo `eventId` ổn định qua retry và bảng idempotency cùng transaction với business update.
- [ ] Không nuốt exception làm listener nhận sai tín hiệu thành công; kiểm tra error channel và retry advice.
- [ ] Có retry hữu hạn, backoff, DLQ/quarantine và quy trình replay.
- [ ] Nếu consumer còn phát event mới, cân nhắc inbox + outbox để bảo toàn ý định gửi.
- [ ] Kiểm thử lỗi trước DB commit, sau DB commit trước ACK và ngay sau ACK.
- [ ] Kiểm thử duplicate đồng thời, broker disconnect, restart, poison message và flow nhiều nhánh.
- [ ] Theo dõi queue depth/consumer lag, redelivery, duplicate, error rate, DLQ, correlation và độ trễ end-to-end.

**Ghi nhớ:** **Commit/rollback chỉ tác động đến những tài nguyên thực sự nằm trong transaction; redelivery do nguồn message và cơ chế ACK/offset quyết định.** Với Spring Integration, hãy kết hợp transaction boundary rõ ràng, xử lý lỗi đúng đường, message bền vững và consumer idempotent. Đó là nền tảng để các luồng Router, Filter, Transformer, Splitter, Aggregator và Gateway có thể phục hồi sau lỗi mà không gây tác dụng phụ lặp.
