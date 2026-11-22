# Message receive và transaction trong Spring Integration

## 1. Bài toán: nhận được thông điệp rồi xử lý lỗi thì sao?

Hệ thống đặt hàng phát thông điệp `ReserveInventory` để dịch vụ kho giữ hàng. Dịch vụ kho nhận thông điệp, trừ tồn kho trong database, rồi xác nhận với nguồn gửi. Có hai tình huống khó:

- Database **rollback** sau khi consumer đã lấy message. Liệu message có được giao lại để thử lần nữa?
- Database **commit** thành công, nhưng consumer sập trước khi gửi xác nhận (ACK) hoặc commit offset. Khi nguồn gửi lại message, liệu tồn kho có bị trừ hai lần?

Đó là trọng tâm của **message receive và transaction**: thiết kế điểm **nhận**, điểm **bắt đầu/kết thúc giao dịch**, điểm **ACK** và cách **xử lý lại** sao cho hệ thống có thể phục hồi trước lỗi.

Trong phạm vi module `SPRING_INTEGRATION_PATTERN`, Spring Integration giúp ghép các **Enterprise Integration Patterns (EIP)** như Gateway, Filter, Transformer, Router, Splitter, Aggregator bằng các channel và endpoint ít phụ thuộc. Nhưng transaction không tự di chuyển theo message qua mọi thread hoặc process. Để thiết kế luồng đáng tin cậy, phải kiểm tra **nguồn message**, **loại channel**, **thread xử lý**, **transaction manager** và **cơ chế acknowledgement** của từng adapter.

### Mục tiêu của bài

Sau bài này, người học có thể:

1. Phân biệt **polling consumer** và **message-driven consumer**, biết transaction thường bắt đầu ở đâu.
2. Giải thích điều gì xảy ra khi `receive()`, handler, database commit và ACK thành công hoặc thất bại.
3. Xác định tác động của `DirectChannel`, `ExecutorChannel`, `QueueChannel`, persistent message store và inbound broker adapter.
4. Đặt transaction ở poller hoặc handler, điều khiển retry/redelivery và tránh nuốt exception khiến ACK sai.
5. Dùng **idempotent consumer/inbox** để xử lý lại message an toàn và kiểm thử các cửa sổ lỗi quan trọng.

## 2. Receive không đồng nghĩa với xử lý xong

Một thông điệp đi vào ứng dụng thường trải qua các giai đoạn:

~~~mermaid
flowchart LR
    A["Nguồn: broker / queue / DB"] --> B["Inbound adapter hoặc poller"]
    B --> C["MessageChannel"]
    C --> D["Filter / Transformer / Router"]
    D --> E["Business handler"]
    E --> F[("Business DB")]
    B -. "ACK / offset / source transaction" .-> A
~~~

Các mốc này có ngữ nghĩa khác nhau:

| Mốc | Diễn giải | Có bảo đảm gì? |
| --- | --- | --- |
| **Receive** | Consumer nhận hoặc lấy được message từ nguồn. | Message có thể chưa được xử lý nghiệp vụ; một số nguồn hỗ trợ trả lại sau lỗi, một số không. |
| **Dispatch** | Adapter chuyển message vào Spring Integration flow. | Với channel bất đồng bộ, downstream có thể còn đang chạy. |
| **Business commit** | Giao dịch của DB nghiệp vụ commit thành công. | Không tự động ACK với broker hoặc commit offset. |
| **ACK / offset commit** | Nguồn đánh dấu delivery đã được nhận hoặc tiến độ đã được xác nhận. | Không chứng minh cập nhật trên DB khác chắc chắn thành công. |
| **Redelivery** | Nguồn gửi lại message hoặc consumer đọc lại. | Không bảo đảm đây là lần xử lý đầu; cần thiết kế chống trùng. |

**Thời điểm ACK là một quyết định về độ tin cậy.** Nếu ACK trước rồi xử lý DB, process có thể sập và làm mất công việc. Nếu commit DB trước ACK, process có thể sập giữa hai bước và message được giao lại. Lựa chọn phổ biến cho hệ thống quan trọng là chấp nhận **at-least-once delivery**, đồng thời làm nghiệp vụ **idempotent**.

### Receive từ đâu?

Spring Integration có hai kiểu endpoint nhận chính:

- **Polling endpoint**: một poller định kỳ gọi `MessageSource.receive()` hoặc `PollableChannel.receive()`. Ví dụ: đọc hàng đợi, JDBC-backed store, file hoặc một nguồn hỗ trợ polling.
- **Message-driven endpoint**: nguồn chủ động đẩy message vào handler thông qua listener hoặc callback, ví dụ JMS/AMQP/Kafka tùy adapter. Điểm ACK, transaction và retry chịu ảnh hưởng lớn từ listener container và broker.

`SubscribableChannel` như `DirectChannel` thường dispatch khi có message được gửi vào channel; `PollableChannel` như `QueueChannel` cho phép consumer gọi `receive()`. **Không phải mọi channel đều có API hoặc tính chất rollback giống nhau.**

## 3. Bốn ranh giới cần vẽ trước khi viết code

Trong một luồng nhận message, cần tách:

1. **Receive boundary**: nguồn nào quyết định message còn sẵn để nhận lại hay đã bị lấy khỏi nguồn?
2. **Execution boundary**: handler chạy trên cùng thread với listener/poller hay được đưa cho executor khác?
3. **Transaction boundary**: ai mở transaction, tài nguyên nào tham gia, bước nào thực sự nằm trước commit/rollback?
4. **Acknowledgement boundary**: lúc nào nguồn tin rằng delivery hoàn tất, khi nào nó sẽ phát lại?

### Luồng đồng bộ với một consumer transaction

~~~mermaid
sequenceDiagram
    participant Source as Message source
    participant Poller as Poller / Listener
    participant Flow as DirectChannel + Handler
    participant DB as Business DB
    Source-->>Poller: Deliver message
    Note over Poller,DB: Boundary xử lý đồng bộ
    Poller->>Flow: Dispatch
    Flow->>DB: BEGIN + UPDATE
    DB-->>Flow: COMMIT OK
    Flow-->>Poller: Complete
    Poller-->>Source: ACK / commit source transaction
    Note over Source,DB: ACK có thể là bước riêng, không nguyên tử với DB
~~~

Sơ đồ là **một chính sách xử lý mong muốn**, không khẳng định mọi adapter tự ACK sau khi DB commit. Broker có thể quản lý ACK ở listener container; một số cấu hình có auto-ack; thời điểm commit offset của Kafka và transaction JMS khác nhau. Phải kiểm tra cơ chế thực tế.

### Khi có thread bất đồng bộ

~~~mermaid
flowchart LR
    subgraph T1["Thread A — listener/poller"]
      A["Receive"] --> B["ExecutorChannel.send()"]
      B --> C["Listener có thể kết thúc / ACK"]
    end
    B -. "handoff" .-> D["Worker thread B"]
    subgraph T2["Transaction khác nếu được mở"]
      D --> E["Business handler"]
      E --> F[("DB")]
    end
~~~

Với `ExecutorChannel`, transaction kiểu thread-bound của listener/poller **không tự được truyền** sang worker. Nếu listener kết thúc và ACK theo việc đã bàn giao cho executor, một lỗi xuất hiện sau đó ở worker có thể không khiến nguồn phát lại message. Muốn đánh giá việc này phải xem channel, executor, container và error handler cùng nhau.

## 4. Cách transaction hoạt động theo loại nguồn nhận

| Nguồn hoặc channel | Khi handler lỗi | Cần kiểm tra để dự đoán redelivery |
| --- | --- | --- |
| `QueueChannel` **trong bộ nhớ** | DB transaction có thể rollback. | Việc dequeue khỏi queue trong bộ nhớ thường không nằm trong JDBC transaction; message không tự quay lại chỉ vì DB rollback, và có thể mất khi process sập. |
| `QueueChannel` với **persistent MessageStore** | Có thể phối hợp thao tác queue với transaction của store. | Cấu hình store, mức hỗ trợ transaction, group ID, datasource và transaction manager; việc nhận/xóa message có thực sự cùng transaction DB hay không. |
| JDBC/SQL polling source | DB operation có thể rollback nếu source tham gia transaction. | Cơ chế claim row, khóa, checkpoint, thời điểm update trạng thái đã xử lý, isolation và nhiều poller chạy song song. |
| JMS message-driven inbound | Một JMS session transacted có thể rollback việc consume trên JMS và dẫn đến redelivery. | `sessionTransacted`, listener container, error propagation, loại session và transaction manager. JDBC có cùng global transaction hay không là vấn đề riêng. |
| AMQP/RabbitMQ inbound | Broker có thể redeliver khi delivery bị reject/nack hoặc connection mất trước ACK. | ACK mode, listener container, requeue, prefetch, DLQ và transaction của broker/DB. |
| Kafka inbound | Message được đọc lại nếu offset chưa được commit tương ứng. | Ack mode, offset commit, partition, rebalance, retry/error handler, producer transaction và consumer group. |
| HTTP inbound gateway/webhook | Request được nhận thông qua HTTP. | Response status, timeout, retry của client; không có rollback request từ xa như một JDBC transaction. |
| File poller | Có thể nhìn thấy file hoặc di chuyển file giữa các lần poll. | Accept-once filter, rename/move, metadata store, checkpoint, restart và độ bền của filesystem. |

Điểm chung là: **transaction của handler chỉ bảo vệ tài nguyên thực sự tham gia**. Chẳng hạn, việc sử dụng `@Transactional` cho PostgreSQL không tự biến ACK RabbitMQ, offset Kafka hay lời gọi HTTP thành một phần của PostgreSQL transaction.

### Một ví dụ cần nhớ

Consumer nhận `ReserveInventory(eventId = E-17)`:

1. Handler ghi thay đổi tồn kho và DB commit.
2. Consumer sập **trước** khi xác nhận delivery.
3. Broker cho nhận lại `E-17`.

**Redelivery trong tình huống này là hợp lý.** Hệ thống phải nhận diện `E-17` đã được xử lý và tránh trừ kho lần thứ hai; không thể chỉ dựa vào transaction rollback.

## 5. Transactional poller trong Spring Integration

Trong polling flow, một cách mở transaction là đặt transaction advice ở **poller**. Ví dụ Java DSL sau cho thấy vị trí boundary (giả định đã khai báo `workQueue` và một `PlatformTransactionManager` cho DB nghiệp vụ):

~~~java
@Configuration
@EnableIntegration
class PollingFlowConfig {

    @Bean
    QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow orderWorker(
            PlatformTransactionManager transactionManager,
            InventoryHandler inventoryHandler) {
        return IntegrationFlow.from(
                        "workQueue",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1_000)
                                        .maxMessagesPerPoll(1)
                                        .transactional(transactionManager)))
                .handle(inventoryHandler, "reserve")
                .get();
    }
}
~~~

**Diễn biến:**

1. Poller tới kỳ thực thi và bắt đầu transaction theo cấu hình.
2. Poller lấy tối đa một message từ `workQueue` trong một lần poll.
3. Nếu endpoint tiếp tục xử lý đồng bộ qua handler JDBC, các thao tác DB phù hợp có thể tham gia transaction đó.
4. Nếu handler hoàn tất, transaction commit; nếu exception thỏa rollback rules thoát qua advice, transaction rollback.

`maxMessagesPerPoll(1)` giúp quan sát từng đơn vị công việc; nó không tự thay đổi độ bền của queue.

**Cảnh báo về ví dụ:** `QueueChannel(100)` là queue **in-memory**. Nếu poller đã lấy message ra, rồi handler lỗi, JDBC rollback không có nghĩa thao tác lấy từ queue được đảo ngược. Tránh dùng ví dụ này để khẳng định có redelivery bền vững hoặc khôi phục message khi ứng dụng restart.

### Khi cần nhận message bền vững

Thay nguồn in-memory bằng một nguồn có cơ chế lưu trữ và phục hồi được định nghĩa rõ:

- **Persistent channel/message store**: đánh giá cách lấy/xóa message trong transaction và khả năng dùng chung transaction manager với database nghiệp vụ.
- **Broker**: dùng listener container hoặc adapter hỗ trợ ACK/redelivery; cấu hình lỗi để broker có thể giao lại, đồng thời dùng idempotency.
- **Database polling**: dùng row status hoặc claim token được ghi bền vững, tránh nhiều worker cùng nhận một dòng; có chiến lược reclaim khi worker chết.

Không thể kết luận “poller có `transactional()` thì message tự được đưa trở lại” nếu chưa biết **nguồn message** có tham gia transaction hay không.

## 6. Transaction ở handler khác gì transaction ở poller?

Đặt `@Transactional` trên một Spring service xử lý nghiệp vụ cũng có thể bảo vệ DB:

~~~java
@Service
class SimpleInventoryHandler {
    private final JdbcTemplate jdbc;

    SimpleInventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory command) {
        jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """, command.quantity(), command.sku(), command.quantity());
    }
}
~~~

Giả sử `ReserveInventory` là kiểu payload của incoming message. Với handler này, Spring transaction interceptor có thể bao quanh thao tác JDBC khi integration endpoint gọi qua Spring bean proxy.

Hai cách đặt transaction có phạm vi khác nhau:

| Đặt boundary tại | Phạm vi thường thấy | Giới hạn |
| --- | --- | --- |
| **Poller** với `.transactional(manager)` | Có thể bao quanh một lần poll và các bước synchronous downstream. | Không tự làm queue in-memory transactional; async boundary có thể thoát khỏi phạm vi transaction. |
| **Handler** với `@Transactional` | Bao quanh method xử lý nghiệp vụ. | Thao tác nhận/ACK ở bên ngoài method không tự tham gia; nếu caller nuốt exception, nguồn có thể ACK. |
| **Listener container** với broker transaction | Bao quanh việc nhận/xử lý theo cơ chế adapter hoặc broker. | Không tự đồng nhất broker transaction và transaction database riêng. |

Trong nhiều hệ thống, **handler transaction và cơ chế ACK của nguồn phối hợp về thứ tự**, song vẫn là hai tài nguyên độc lập. Thiết kế cần xử lý tình huống DB commit nhưng ACK thất bại.

### Đặt transaction trên service được gọi qua Spring proxy

Nếu gọi một method `@Transactional` qua `this.reserve(...)` trong cùng bean theo cơ chế Spring proxy thông thường, advice có thể không chạy. Tương tự, nếu handler trực tiếp thao tác với các connection ngoài transaction manager, annotation trên method không biến các tài nguyên đó thành một transaction chung.

Để chắc chắn, kiểm thử trạng thái DB sau handler lỗi thay vì chỉ kiểm tra annotation có xuất hiện trong source code.

## 7. Message-driven: ACK, session transaction và rollback

Với listener nhận từ broker, message thường được giao qua container/adapter để chạy downstream flow. Trình tự phải được hiểu theo **broker và adapter cụ thể**.

### JMS: session transacted

Một JMS listener container có thể được cấu hình `sessionTransacted = true`. Khi đó việc nhận message tham gia **JMS local transaction**: nếu listener xử lý thành công, JMS session commit; nếu lỗi thích hợp đi ra ngoài, session rollback và message có thể được broker giao lại.

Ví dụ các bước cấu hình ở mức ý tưởng:

~~~text
JMS queue "orders.reserve"
  -> JMS message-driven inbound adapter
  -> DirectChannel (xử lý synchronous)
  -> InventoryHandler.reserve(...)

JMS listener container:
  sessionTransacted = true
  error propagation  = giữ lỗi để container có thể rollback

Business DB:
  dùng PlatformTransactionManager tương ứng
  handler cập nhật DB trong transaction riêng nếu cần
~~~

**Cần phân biệt hai transaction:** JMS local transaction của việc consume và JDBC transaction của nghiệp vụ **không tự động commit nguyên tử cùng nhau**. Có thể xảy ra DB commit nhưng JMS session rollback, dẫn tới redelivery. Nếu hệ thống yêu cầu atomicity across resources, phải kiểm tra khả năng và cấu hình của XA/JTA, JDBC driver, JMS provider và chi phí vận hành; không suy ra điều đó từ `sessionTransacted = true`.

Không đưa `ExecutorChannel` vào ngay sau adapter chỉ để tăng throughput mà chưa kiểm tra cơ chế ACK: khi container chỉ quan sát việc dispatch thành công sang executor, lỗi nghiệp vụ xảy ra sau đó có thể không tác động đến JMS transaction của listener.

### AMQP/RabbitMQ: ACK và requeue

Ở RabbitMQ, listener container quyết định khi nào ACK, reject/nack và có requeue hay không. Một exception có thể dẫn đến redelivery, đưa vào DLQ hoặc bị tiêu thụ bởi error handler tùy cấu hình. Cần kiểm tra:

- Chế độ acknowledgement của container (tự quản lý, manual, hay chế độ khác mà adapter hỗ trợ).
- Consumer prefetch và khả năng nhiều delivery đang chờ ACK.
- Lỗi được ném trở lại listener hay bị error flow xử lý và coi như thành công.
- Chính sách requeue, số lần thử và dead-letter exchange/queue.

Việc dùng transaction của RabbitMQ và transaction JDBC riêng không tự tạo giao dịch hai pha. Redelivery sau lỗi vẫn phải an toàn đối với message đã cập nhật DB trước đó.

### Kafka: offset commit và processing transaction

Kafka đánh dấu tiến độ tiêu thụ thông qua **offset**. Consumer đã cập nhật DB nhưng chưa commit offset có thể đọc lại message sau khi crash hoặc rebalance. Ngược lại, commit offset trước khi xử lý an toàn có thể khiến message không được xử lý lại dù DB chưa cập nhật.

Kafka hỗ trợ transaction cho một số kịch bản **đọc từ Kafka và ghi trở lại Kafka**, với việc phối hợp offset trong Kafka transaction theo cấu hình producer/consumer phù hợp. Điều đó **không tự đưa database JDBC bên ngoài vào cùng atomic transaction**. Với side effect trên DB, vẫn phải thiết kế idempotent consumer/inbox hoặc cơ chế phối hợp được kiểm chứng.

### HTTP webhook: response chính là tín hiệu hoàn tất

Inbound HTTP gateway có thể nhận một request rồi trả status. Nếu response `2xx` được gửi ra **trước khi công việc bất đồng bộ thật sự hoàn thành**, client có thể coi yêu cầu là thành công và không retry. Đối với webhook quan trọng, cân nhắc ghi một **durable inbox/command** trước khi trả `2xx`; nếu không lưu bền vững, một lần crash có thể làm mất công việc đã được chấp nhận.

## 8. Xây dựng idempotent consumer bằng inbox

Để xử lý an toàn tình huống **DB commit nhưng nguồn giao lại message**, có thể tạo bảng lưu `eventId` đã được xử lý. Ví dụ bên dưới dùng cú pháp PostgreSQL và giả định mỗi delivery có một `eventId` nghiệp vụ ổn định:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(80) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE processed_messages (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Payload vào flow:

~~~java
record ReserveInventory(
        String eventId,
        String orderId,
        String sku,
        int quantity) {}
~~~

Handler xử lý message như sau:

~~~java
@Service
class InventoryHandler {
    private final JdbcTemplate jdbc;

    InventoryHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(ReserveInventory command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // PostgreSQL: bản ghi có eventId giống hệt là delivery lặp.
        int inserted = jdbc.update("""
                INSERT INTO processed_messages (event_id)
                VALUES (?)
                ON CONFLICT (event_id) DO NOTHING
                """, command.eventId());

        if (inserted == 0) {
            // Event đã được commit ở lần xử lý trước.
            return;
        }

        int updated = jdbc.update("""
                UPDATE inventory
                   SET available = available - ?
                 WHERE sku = ? AND available >= ?
                """,
                command.quantity(),
                command.sku(),
                command.quantity());

        if (updated != 1) {
            throw new IllegalStateException(
                    "Unable to reserve inventory for " + command.sku());
        }
    }
}
~~~

**Vì sao ghi `processed_messages` trước lại an toàn?** Cả `INSERT` và `UPDATE inventory` được thực hiện **trong cùng transaction DB**. Nếu không đủ tồn kho, exception thoát khỏi method và transaction rollback **cả dấu đã xử lý lẫn thay đổi tồn kho**. Nếu mọi thứ commit, redelivery sẽ thấy cùng `eventId` và không cập nhật lần hai.

Thiết kế này tránh mẫu `SELECT rồi INSERT` đơn giản dễ xảy ra **race condition** khi hai worker xử lý cùng `eventId`. Ràng buộc `PRIMARY KEY` bảo đảm tính duy nhất; `ON CONFLICT DO NOTHING` là cú pháp PostgreSQL, cần đổi nếu dùng database khác. Khi có nhiều transaction đồng thời, unique index và cơ chế khóa/isolation của database quyết định cách transaction thứ hai đợi hoặc giải quyết xung đột.

### Điều kiện để idempotency đúng

1. `eventId` phải được giữ **ổn định qua retry và redelivery** của cùng sự kiện. Không sinh UUID mới mỗi lần nhận.
2. Định nghĩa phạm vi duy nhất: nếu nhiều consumer nghiệp vụ độc lập dùng cùng kho deduplication, khóa có thể là `(consumer_name, event_id)` thay vì chỉ `event_id`.
3. Ghi dấu đã xử lý và cập nhật nghiệp vụ phải **cùng DB transaction**. Nếu ở hai DB không giao dịch chung, cần giải pháp khác.
4. Handler không được làm side effect từ xa **trước** khi hoàn tất giao dịch nếu bạn đang giả định rằng rollback sẽ hoàn tác mọi thứ. Với email/HTTP, dùng outbox/compensation hoặc idempotency của hệ nhận.
5. Dù duplicate đã được nhận diện, consumer vẫn phải hoàn thành xử lý delivery theo đúng chính sách ACK của adapter.

### Inbox kết hợp với outbox

Nếu xử lý message nhận vào còn cần phát một message mới, một mẫu thường dùng là:

~~~text
Receive OrderPaid(eventId)
   -> begin DB transaction
        insert processed_messages(eventId) if absent
        update orders / inventory
        insert outbox_events(newEventId, payload)
      commit DB transaction
   -> acknowledge input delivery

Outbox relay
   -> publish outbox event
   -> mark sent (có thể retry và publish lặp)
~~~

Inbox giúp chống xử lý lặp **ở đầu vào**. Outbox bảo đảm ý định gửi sự kiện mới được ghi bền vững **cùng dữ liệu nghiệp vụ**. Hai mẫu kết hợp giúp các service giao tiếp ít phụ thuộc hơn nhưng vẫn đòi hỏi xử lý redelivery và giám sát backlog.

## 9. Exception đi tới đâu quyết định retry và rollback

Một flow có thể ném lỗi ở Filter, Transformer, Router, Service Activator, handler hoặc Aggregator. Cần hiểu nơi nào bắt lỗi cuối cùng:

| Hoàn cảnh | Transaction/ACK có thể phản ứng thế nào? |
| --- | --- |
| Handler đồng bộ ném `RuntimeException` và lỗi tới transaction interceptor. | DB transaction thông thường rollback theo rollback rules. |
| Listener/poller nhận exception và cấu hình source cho phép redelivery khi lỗi. | Nguồn có thể giao lại, có backoff/requeue tùy cấu hình. |
| Handler bắt exception, chỉ log rồi return bình thường. | Transaction có thể commit và container có thể ACK, ngay cả khi nghiệp vụ chưa hoàn tất. |
| Exception được chuyển thành `ErrorMessage` và error flow xử lý xong. | Không suy rằng transaction rollback; cần xác minh kết quả cuối mà transaction advice/container quan sát. |
| Handler async lỗi sau khi adapter đã xác nhận nguồn. | Lỗi có thể không còn tác động đến ACK ban đầu; cần retry/durable queue ở phía worker. |
| Một message sai dữ liệu bị redeliver liên tục. | Cần retry hữu hạn, DLQ/quarantine và cách xử lý poison message. |

### Không được nuốt lỗi cần rollback

~~~java
@Transactional
public void handleBadly(ReserveInventory command) {
    try {
        inventoryHandler.reserve(command);
    } catch (RuntimeException ex) {
        log.warn("Failed to reserve {}", command.orderId(), ex);
        // Lời gọi kết thúc bình thường: phía ngoài có thể coi là success.
    }
}
~~~

Nếu muốn rollback và để nguồn xử lý redelivery, hãy bảo đảm lỗi **được truyền ra đúng boundary**. Tuy nhiên, không chỉ thêm `throw` tùy tiện: cần xác định lỗi nào là tạm thời, lỗi nào vĩnh viễn, retry ở đâu, và khi nào đi vào DLQ. Một số trường hợp transaction đã được đánh dấu `rollback-only` do inner method thất bại; cần kiểm thử toàn bộ transaction advice chain.

### Retry và transaction phải có thứ tự nhất quán

Ví dụ có hai mô hình:

~~~text
Mô hình 1:
retry whole operation
  -> open NEW transaction per attempt
     -> process message
     -> commit/rollback

Mô hình 2:
open transaction ONCE
  -> retry handler repeatedly inside same transaction
  -> commit/rollback
~~~

Hai mô hình **khác nhau**. Nếu transaction đầu đã `rollback-only` hoặc có lỗi connection/SQL, retry ngay trong transaction đó có thể tiếp tục thất bại hoặc không thể commit. Khi cần thử lại trọn vẹn, thường nên có **transaction mới cho từng attempt** (tùy broker adapter, retry advice và thứ tự interceptor).

Các chính sách thực hành:

- Lỗi tạm thời: retry hữu hạn, backoff, có jitter khi phù hợp.
- Lỗi không thể khắc phục: ghi nhận rõ nguyên nhân và chuyển DLQ/quarantine.
- Lỗi không chắc request trước đã hoàn tất: giữ nguyên `eventId` và xử lý idempotent.
- Sau nhiều lần lỗi: có công cụ xem, sửa dữ liệu và **replay** message có kiểm soát.

## 10. Kết hợp receive với Router, Filter, Splitter và Aggregator

Sau inbound adapter, một message có thể đi qua nhiều pattern:

~~~mermaid
flowchart LR
    A["Inbound adapter"] --> B["DirectChannel"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["Filter"]
    D --> F["Splitter"]
    E --> G["Handler A"]
    F --> H["ExecutorChannel / workers"]
    H --> I["Aggregator theo orderId"]
    G --> I
~~~

- **Transformer** có thể làm lỗi chuyển đổi payload. Nếu xảy ra trong listener đồng bộ, lỗi có thể kích hoạt rollback nguồn; nếu bị error flow tiêu thụ, kết quả khác.
- **Filter** bỏ qua message thường là **kết quả hợp lệ** theo chính sách lọc. Nếu consumer ACK sau khi Filter loại bỏ message, message sẽ không tự được phát lại. Nếu bỏ đi là lỗi nghiệp vụ, phải có error path rõ.
- **Router** chọn đích. Một nhánh đồng bộ có thể còn ở transaction hiện tại; nhánh async tạo ranh giới thực thi khác.
- **Splitter** tạo nhiều thông điệp con. Một transaction của nguồn **không tự bao phủ** những nhánh xử lý đã chuyển sang nhiều thread/process.
- **Aggregator** gom message bằng `correlationId`, sequence/release strategy và message store. Nếu cần khôi phục trạng thái khi restart, phải cân nhắc persistent store, timeout, duplicate và việc hoàn tất một phần.
- **Gateway** giúp tiếp nhận hoặc yêu cầu–trả lời theo contract. Với async flow, phản hồi ban đầu chỉ có thể cho biết tác vụ đã được chấp nhận, không bảo đảm tất cả nhánh đã commit.

Ví dụ, một message `OrderConfirmed` được Splitter tạo hai nhánh `ReserveInventory` và `ChargePayment`. Nếu thanh toán đã commit ở một service nhưng kho thất bại ở service khác, rollback transaction của consumer ban đầu **không thu hồi được** thanh toán. Quy trình cần cơ chế bù trừ/Saga hoặc trạng thái theo dõi từng bước, cùng định danh correlation và idempotency của từng nhánh.

### Correlation không phải transaction

Thông tin như `orderId`, `correlationId`, `sequenceNumber` và `eventId` rất hữu ích cho routing, aggregation và tracing. Nhưng không header nào tự mang theo JDBC transaction hay đồng bộ hóa ACK giữa các broker. **Correlation để theo dõi/ngữ nghĩa, transaction để kiểm soát thay đổi trên tài nguyên.**

## 11. Ma trận độ tin cậy: thời điểm ACK so với commit

| Thứ tự | Cửa sổ lỗi | Nguy cơ | Cách giảm rủi ro |
| --- | --- | --- | --- |
| **ACK rồi mới commit DB** | App sập sau ACK, trước commit. | Message không được phát lại nhưng dữ liệu chưa cập nhật: **mất xử lý**. | Tránh ACK quá sớm; dùng nguồn bền vững, ACK sau khi commit hoặc lưu inbox bền vững. |
| **Commit DB rồi ACK** | App sập sau commit, trước ACK. | Message được giao lại, có thể **xử lý trùng**. | Idempotent consumer và ràng buộc unique trên `eventId`. |
| **DB rollback và broker nhận lỗi** | Handler ném lỗi, listener trả về thất bại. | Retry nhiều lần, có thể tắc bởi poison message. | Retry/backoff/DLQ, phân loại lỗi vĩnh viễn. |
| **DB rollback nhưng lỗi bị nuốt** | Handler return bình thường. | Broker ACK dù nghiệp vụ thất bại. | Không nuốt lỗi cần rollback; kiểm thử error channel và container. |
| **Dispatch sang worker trước ACK** | Listener đã ACK, worker sau đó lỗi. | Không có nguồn bền vững để retry nếu task chỉ trong executor. | Durable queue/inbox; ACK theo điểm đã lưu bền vững hoặc giữ processing sync khi phù hợp. |
| **Source transactional + business DB cùng một transaction manager hợp lệ** | Một thao tác trong transaction thất bại. | Các thay đổi tham gia transaction có thể rollback cùng nhau. | Xác nhận loại store, datasource, manager và thực hiện kiểm thử crash/recovery. |

Không nên tuyên bố **exactly-once end-to-end** chỉ vì có Kafka transaction, JDBC transaction hoặc JMS transacted session. Mỗi công nghệ có một **phạm vi bảo đảm**; các thao tác đi qua nhiều hệ thống cần xem xét duplicate, crash và xác nhận không rõ kết quả.

## 12. Kiểm thử receive và transaction bằng failure injection

Một bài thực hành tốt phải kiểm tra **kết quả được lưu** và **hành vi của nguồn** sau lỗi, không chỉ kiểm tra handler được gọi.

### Kiểm thử idempotency ở DB

Với handler `InventoryHandler.reserve` ở phần 8 và dữ liệu kiểm thử ban đầu `inventory("SKU-1", available=10)`, một kiểm thử tích hợp có thể viết:

~~~java
@SpringBootTest
class InventoryReceiveIT {
    @Autowired InventoryHandler handler;
    @Autowired JdbcTemplate jdbc;

    @Test
    void duplicateEventChangesStockOnlyOnce() {
        String eventId = UUID.randomUUID().toString();
        ReserveInventory event = new ReserveInventory(
                eventId, "ORDER-1", "SKU-1", 3);

        handler.reserve(event);
        handler.reserve(event); // Mô phỏng redelivery cùng eventId.

        Integer available = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "SKU-1");
        assertEquals(7, available);

        Integer applied = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_messages WHERE event_id = ?",
                Integer.class, eventId);
        assertEquals(1, applied);
    }

    @Test
    void invalidReservationRollsBackProcessedMarker() {
        String eventId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> handler.reserve(new ReserveInventory(
                        eventId, "ORDER-2", "SKU-1", 1000)));

        Integer processed = jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_messages WHERE event_id = ?",
                Integer.class, eventId);
        assertEquals(0, processed);
    }
}
~~~

Ví dụ giả định đã tạo schema và dữ liệu test ban đầu; mỗi test cần chạy trên dữ liệu được cô lập hoặc reset trạng thái phù hợp. Khi kiểm tra commit/rollback của ứng dụng, tránh để `@Transactional` trên chính test che lấp transaction của handler. Đối với kiểm thử duplicate, phải giữ **cùng eventId** ở hai lần gọi.

### Kiểm thử trên broker thật

| Kịch bản | Quan sát cần thu thập |
| --- | --- |
| Handler ném exception trước DB commit | Có rollback DB? Broker/adapter có redeliver hay chuyển DLQ theo cấu hình? |
| Handler commit DB, rồi connection/consumer bị ngắt trước ACK | Có redelivery không? DB có xử lý trùng không? |
| Consumer bị rebalance (Kafka) | Offset và việc xử lý cùng partition có tiếp tục đúng? |
| Listener đẩy vào `ExecutorChannel` rồi worker lỗi | Consumer đã ACK chưa? Lỗi xuất hiện ở error channel nào? |
| DB tạm unavailable | Retry/backoff có giới hạn, không gây bão request hoặc khóa queue vô thời hạn? |
| Message sai schema | Có đi DLQ/quarantine với nguyên nhân đầy đủ, tránh poison loop? |
| Hai delivery cùng `eventId` chạy song song | Unique constraint và transaction có bảo vệ chỉ một lần cập nhật? |
| Ứng dụng restart khi có message trong queue in-memory | Message có thể mất? Có cần chuyển sang durable source? |

Ở cấp integration test, có thể dùng broker thật trong môi trường kiểm thử hoặc Testcontainers tương ứng; kết quả phụ thuộc cấu hình cụ thể. Thu thập cả **trạng thái DB**, **số lần delivery**, **ACK/offset**, **DLQ** và **các event đã xử lý**.

## 13. Quan sát vận hành và khôi phục

### Logging và tracing

Tại thời điểm nhận và kết thúc xử lý, nên theo dõi:

- `eventId` ổn định để phát hiện duplicate.
- `orderId`/`correlationId` để nối các nhánh xử lý và Aggregator.
- Tên channel/endpoint, consumer group/queue, partition–offset hoặc delivery tag theo broker tương ứng.
- Kết quả xử lý (`committed`, `rolled_back`, `duplicate_skipped`), số lần thử, loại exception.
- Trạng thái xác nhận (`ACK`, `NACK`, `offset_commit`) khi adapter cho phép quan sát.

Không ghi các payload chứa thông tin nhạy cảm vào log. Đừng lấy dòng log “received” làm bằng chứng đã xử lý xong.

### Metrics quan trọng

| Metric | Dấu hiệu cần điều tra |
| --- | --- |
| Consumer lag / queue depth | Consumer xử lý chậm hoặc không hoạt động, backlog tăng. |
| Redelivery count | Nhiều lỗi tạm thời hoặc ACK không thành công. |
| Duplicate detection count | Message bị phát lại; tỷ lệ tăng bất thường cần xem producer/ACK. |
| Handler error rate và retry rate | Lỗi schema, DB, phụ thuộc downstream hoặc poison message. |
| DLQ size / age | Công việc cần can thiệp chưa được giải quyết. |
| End-to-end latency | Khoảng cách từ lúc event được tạo đến khi business DB commit. |
| Stuck processing/lease age | Worker chết giữa chừng hoặc cơ chế claim chưa reclaim đúng. |

**Khôi phục:** cung cấp khả năng xem một message lỗi, sửa dữ liệu gốc hoặc cấu hình, phát lại có kiểm soát và xác minh idempotency. Nếu lưu pending/in-progress trong database, cần chính sách reclaim cho worker không heartbeat hoặc lease đã hết hạn.

## 14. Chọn thiết kế phù hợp

| Yêu cầu | Thiết kế gợi ý | Điều phải kiểm chứng |
| --- | --- | --- |
| Xử lý local, không cần bền vững khi restart | `QueueChannel` in-memory và poller. | Chấp nhận mất message khi crash; không mặc định rollback dequeue. |
| Nhận công việc từ nguồn JDBC bền vững | Transactional poller + persistent store/claim logic cùng DB. | Isolation, locking, transaction manager, reclaim và nhiều worker. |
| Nhận từ JMS với yêu cầu redelivery | Message-driven adapter và listener container có session/transaction phù hợp. | Exception propagation, JMS rollback/commit, transaction DB riêng, DLQ. |
| Nhận từ RabbitMQ | Inbound adapter với ACK/requeue/DLQ theo cấu hình, handler idempotent. | ACK mode, broker confirm, prefetch, lỗi tạm thời/vĩnh viễn. |
| Nhận từ Kafka và ghi database | Consumer + DB transaction, idempotency theo `eventId`, quản lý offset thích hợp. | Crash giữa DB commit và offset commit, rebalance, duplicate và DLQ. |
| Webhook cần phản hồi nhanh | Lưu message/command vào durable inbox rồi trả HTTP response; worker xử lý nền. | Chỉ trả success khi đã lưu bền vững; retry/idempotency của request. |
| Workflow phân nhánh nhiều dịch vụ | Mỗi consumer tự quản lý transaction + inbox/outbox; theo dõi correlation/Saga. | Retry, timeout, bù trừ và Aggregator state bền vững. |

Một transaction ngắn ở từng consumer thường dễ phục hồi hơn một transaction kéo dài qua nhiều cuộc gọi mạng. Với EIP phân tán, “chính xác một lần” ở cấp nghiệp vụ thường đạt được bằng **delivery có thể lặp + xử lý idempotent**, thay vì trông chờ một local transaction bao hết hệ thống.

## 15. Bài tập thực hành

**Bài 1 — xác định boundary.** Cho flow `JMS listener → DirectChannel → Filter → Transformer → Service Activator JDBC`. Hãy vẽ boundary của JMS session và DB transaction. Sau đó thay `DirectChannel` bằng `ExecutorChannel`, giải thích vì sao ACK sau khi dispatch có thể mất tác dụng rollback lỗi downstream.

**Bài 2 — nhận từ queue in-memory.** Sử dụng transactional poller ở phần 5. Khi handler ném lỗi, kiểm tra DB rollback và đếm số message còn trong queue. Phân biệt kết quả thực tế với kỳ vọng sai rằng JDBC rollback tự trả lại phần tử đã lấy.

**Bài 3 — xử lý hai lần mà không trừ kho hai lần.** Tạo `inventory` và `processed_messages`, gửi cùng `ReserveInventory(eventId)` hai lần. Kiểm tra inventory chỉ giảm một lần; thử đồng thời hai consumer cùng eventId để chứng minh unique constraint.

**Bài 4 — crash giữa DB commit và ACK.** Dùng broker trong môi trường kiểm thử, cho consumer commit DB rồi ngắt kết nối trước khi ACK. Quan sát redelivery và xác nhận handler idempotent trả về an toàn.

**Bài 5 — Splitter/Aggregator chịu lỗi.** Tách đơn thành các message con theo `correlationId`, xử lý trên nhiều worker, lưu kết quả trong Aggregator có persistent store. Tiêm lỗi vào một worker, kiểm tra retry, timeout và cách phân biệt message đến trễ/đến lặp.

### Câu hỏi tự đánh giá

**1. Transactional poller có bảo đảm message trở lại `QueueChannel` in-memory khi DB rollback không?** Không. JDBC rollback chỉ ảnh hưởng tới tài nguyên tham gia transaction; việc dequeue trong bộ nhớ và độ bền của queue là vấn đề khác.

**2. Vì sao DB đã commit rồi vẫn có redelivery?** Consumer có thể sập hoặc mất kết nối trước ACK/offset commit, nên nguồn chưa biết rằng công việc đã xử lý thành công.

**3. `@Transactional` trên handler có bao gồm ACK của Kafka/RabbitMQ không?** Không mặc định. Nó quản lý các tài nguyên transaction manager tương ứng; ACK/offset do broker adapter/container quản lý.

**4. Vì sao không nên nuốt lỗi ở consumer?** Listener/poller có thể xem lời gọi là thành công và ACK, dù DB rollback hoặc nghiệp vụ chưa xử lý xong.

**5. Inbox giúp giải quyết điều gì?** Ghi nhận `eventId` đã xử lý trong cùng transaction với cập nhật nghiệp vụ, để redelivery không thực hiện side effect trùng.

## 16. Checklist trước khi đưa consumer vào production

- [ ] Xác định nguồn message và cơ chế receive, ACK/offset, redelivery, restart.
- [ ] Chỉ rõ nơi transaction được mở: poller, listener container, handler hay service.
- [ ] Kiểm tra cùng thread hay có chuyển sang executor/broker trước khi ACK.
- [ ] Xác minh những tài nguyên thực sự tham gia transaction và thứ tự commit.
- [ ] Không dựa vào `QueueChannel` in-memory để đảm bảo redelivery bền vững.
- [ ] Thiết kế `eventId` ổn định, bảng dedupe/inbox hoặc cập nhật idempotent.
- [ ] Đảm bảo đánh dấu đã xử lý và cập nhật dữ liệu nằm trong cùng transaction phù hợp.
- [ ] Đưa exception cần rollback tới đúng interceptor/container; kiểm tra error channel.
- [ ] Cấu hình retry hữu hạn, backoff, DLQ, cách replay và xử lý poison message.
- [ ] Kiểm thử ít nhất ba thời điểm lỗi: trước DB commit, sau DB commit/trước ACK, sau ACK.
- [ ] Theo dõi lag, redelivery, duplicate, DLQ, correlation và end-to-end latency.
- [ ] Với flow đa nhánh, xác định boundary, timeout và compensation riêng cho từng nhánh.

**Ghi nhớ:** Nhận được message chỉ là **đầu vào của một đơn vị công việc**. Trong Spring Integration, độ tin cậy của consumer phụ thuộc vào **transaction của tài nguyên**, **cách xử lý lỗi** và **thời điểm nguồn xác nhận delivery**. Hãy chủ động thiết kế redelivery và idempotency để một message được nhận nhiều lần vẫn tạo ra đúng kết quả nghiệp vụ mong muốn.
