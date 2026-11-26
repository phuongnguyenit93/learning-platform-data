# Deduplication message trong Spring Batch phân tán

> **Chương:** Idempotency
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài này phân tích **loại bỏ thông điệp lặp (message deduplication)** để xử lý an toàn khi broker giao lại message, worker retry/restart, manager mất phản hồi và nhiều consumer chạy đồng thời.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **message delivery**, **message processing**, **business effect** và giới hạn của bảo đảm `at-least-once`.
2. Lựa chọn khóa deduplication ổn định giữa retry, broker redelivery, restart và nhiều `JobExecution`; không đánh đồng broker message ID với business event ID.
3. Triển khai mẫu **transactional inbox** bằng unique constraint để xử lý đồng thời các delivery trùng mà không thực hiện nghiệp vụ hai lần.
4. Giải thích **crash window** giữa ghi database và ACK, đồng thời chọn inbox/outbox/idempotency key phù hợp với hệ thống đích.
5. Áp dụng vào remote chunking và remote partitioning của Spring Batch, theo dõi duplicate, độ trễ, retry và reconciliation.
6. Kiểm thử các tình huống giao lại message, lỗi giữa chừng, worker song song và message đến sai thứ tự.

## 1. Vì sao message lặp xuất hiện?

Trong một hệ thống Batch xử lý phân tán, manager và worker thường trao đổi qua message broker. Một message có thể được worker xử lý thành công nhưng **ACK hoặc reply bị mất** vì network timeout, broker restart, consumer crash hoặc manager chưa nhận kết quả.

Nếu broker ưu tiên không mất message, nó thường có thể **giao lại** message chưa được xác nhận. Điều này hữu ích cho độ tin cậy, nhưng có nghĩa worker có thể nhìn thấy **cùng một công việc nhiều lần**.

### Ví dụ cụ thể

Giả sử manager yêu cầu ghi giao dịch `PAY-1001`:

~~~text
T0  Broker giao event PAY-1001 cho Worker A
T1  Worker A cập nhật bảng giao dịch và COMMIT thành công
T2  Worker A mất kết nối trước khi ACK broker
T3  Broker thấy delivery chưa được ACK -> giao lại event cho Worker B
T4  Worker B nhìn thấy cùng event PAY-1001
T5  Nếu không có dedupe -> có thể ghi/charge lần thứ hai
~~~

**Điểm mấu chốt:** “Worker đã chạy mã thành công” và “broker đã ghi nhận ACK” là **hai sự kiện khác nhau**. Không có một transaction atomic mặc định bao trùm cả database của worker và broker.

~~~mermaid
sequenceDiagram
    participant B as Message broker
    participant A as Worker A
    participant D as Business database
    participant W as Worker B
    B->>A: Deliver event E-1001
    A->>D: Apply E-1001
    D-->>A: COMMIT
    A--xB: ACK thất lạc
    B->>W: Redeliver event E-1001
    W->>D: Check idempotency key E-1001
    D-->>W: Đã xử lý -> không áp dụng lại
    W->>B: ACK sau khi xác nhận trạng thái
~~~

Sơ đồ giả định database và mã xử lý có cơ chế chống trùng bền vững. Nếu không có cơ chế này, worker B khó biết A đã commit hay chưa.

### Những nguồn tạo message lặp

| Nguồn | Điều có thể xảy ra | Dedupe cần chịu được |
| --- | --- | --- |
| Broker `at-least-once` | Message chưa ACK bị giao lại | Cùng event, nhiều delivery |
| Timeout ở producer | Producer publish lại khi không biết publish cũ thành công chưa | Hai message vận chuyển khác nhau cho cùng event nghiệp vụ |
| Worker crash | Ghi database xong nhưng chưa ACK | Redelivery sau commit |
| Retry ở client/handler | Cùng công việc được gọi nhiều lần | Lặp requests ngay trong một JobExecution |
| Spring Batch restart | `StepExecution`/`JobExecution` mới chạy lại phần chưa hoàn tất | Message/work unit cũ xuất hiện trong attempt mới |
| Remote partition manager mất reply | Manager không biết worker đã hoàn thành hay chưa | Yêu cầu hoặc kết quả có thể cần reconciliation |
| Operator chủ động replay | Replay từ dead-letter/quarantine | Event cũ được xử lý lại có chủ đích |

## 2. Ba tầng cần phân biệt: delivery, xử lý, tác dụng nghiệp vụ

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Delivery** | Broker đã giao message bao nhiêu lần? | Event E-1001 được giao hai lần |
| **Processing attempt** | Consumer chạy logic bao nhiêu lần? | Worker A và B đều gọi hàm `handle` |
| **Business effect** | Hệ thống đích đã thực sự thay đổi bao nhiêu lần? | Giao dịch E-1001 chỉ được ghi một lần |

Ta thường không thể ngăn broker giao lại message trong mọi tình huống. Mục tiêu thực tế là **lặp delivery vẫn cho ra cùng kết quả nghiệp vụ**, hoặc ít nhất không sinh thêm side effect không mong muốn.

### At-most-once, at-least-once và exactly-once

| Cách giao | Ưu điểm | Rủi ro |
| --- | --- | --- |
| `At-most-once` | Không cố giao lại message sau một số thất bại | Có thể mất message nếu ACK/đánh dấu đã xử lý trước khi business commit |
| `At-least-once` | Có thể giao lại để tránh mất công việc | Consumer phải xử lý duplicate |
| “Exactly-once” trong một thành phần | Có thể hạn chế duplicate trong phạm vi broker/transaction cụ thể | **Không** tự bảo đảm mọi external API, email, DB khác đều chỉ có side effect một lần |

**Không tuyên bố exactly-once end-to-end chỉ vì broker hỗ trợ một chế độ có tên “exactly-once”.** Phải xác định rõ biên giới transaction và hệ thống đích nào được bảo vệ.

## 3. Deduplication và idempotency có giống nhau không?

**Deduplication** là cơ chế **nhận diện và chặn thao tác lặp** dựa trên identity: “Message/event này đã được xử lý chưa?”.

**Idempotency** là tính chất của thao tác: thực hiện lại cùng yêu cầu hợp lệ không tạo ra thêm thay đổi ngoài kết quả đã định nghĩa.

Ví dụ:

- `SET status='PAID' WHERE order_id=123` có thể đạt tính idempotent về **trạng thái cuối** nhưng vẫn tạo duplicate audit/event nếu side effect bổ sung không được bảo vệ.
- `balance = balance + 100` **không idempotent**: gọi hai lần cộng hai lần.
- Chèn ledger với unique key `(tenant_id, operation_id)` có thể ngăn thực hiện cùng operation hai lần dù hai worker cùng chạy.
- Transactional inbox ghi nhận event đã xử lý, nhưng nếu bên trong transaction gọi API thanh toán không được bảo vệ, message vẫn có thể gây **double charge** khi có crash window.

Do đó, **dedupe ở cửa vào** cần kết hợp **idempotent side effect tại đích**. Không có một câu lệnh “đã xử lý message” nào tự bảo đảm an toàn cho toàn bộ chuỗi hệ thống.

## 4. Thiết kế dedupe key: ổn định, duy nhất, đúng phạm vi

Lựa chọn khóa đúng là phần quan trọng nhất của message deduplication.

### Các loại ID thường gặp

| ID | Ai cấp? | Có phù hợp làm khóa dedupe lâu dài không? |
| --- | --- | --- |
| Broker delivery tag | Broker/consumer channel | **Không**: có thể đổi khi giao lại, phạm vi thường hẹp |
| Transport message ID | Adapter hoặc producer | **Chỉ khi** producer bảo đảm giữ nguyên qua retry/re-publish |
| Business event ID | Hệ thống phát sinh event | **Có**, nếu duy nhất và ổn định cho cùng event |
| Business operation ID | Hệ thống nghiệp vụ | **Có**, đặc biệt cho charge/ledger hoặc thao tác không được thực hiện hai lần |
| `StepExecutionId` | Spring Batch | **Không đủ** cho nghiệp vụ xuyên restart vì attempt mới có ID mới |
| `JobExecutionId` | Spring Batch | **Không đủ** khi cùng `JobInstance` được restart |
| Partition key | `Partitioner` | Hữu ích xác định work unit nhưng **không đủ** để phân biệt item trong partition |
| Payload hash | Consumer tính toán | Chỉ là phụ trợ; hai sự kiện hợp lệ có payload giống nhau |

Giả sử hệ thống có nhiều loại event và nhiều consumer độc lập. Khóa inbox có thể là:

~~~text
(consumerName, sourceSystem, businessEventId)
~~~

Với dịch vụ có nhiều tenant, cần chắc chắn business event ID đã **globally unique** hoặc bao gồm tenant:

~~~text
(consumerName, tenantId, sourceSystem, businessEventId)
~~~

**Vì sao có `consumerName`?** Một event có thể được nhiều subscriber sử dụng cho **những nghiệp vụ khác nhau**. `billing-consumer` xử lý event E-1 không có nghĩa `analytics-consumer` phải bỏ qua E-1.

### Cùng message ID nhưng payload khác

Hai delivery sử dụng cùng event ID nhưng payload khác nhau là **xung đột identity**, không nên coi đó là duplicate hợp lệ để bỏ qua.

Ví dụ:

~~~text
Event E-1001, amount=100.00  -> đã xử lý
Event E-1001, amount=900.00  -> đến sau
~~~

Nếu consumer chỉ nhìn ID và trả “đã xử lý”, nó có thể che lỗi producer hoặc giả mạo dữ liệu. Một inbox có thể lưu thêm `payload_hash` (tính từ **canonical representation** có quy tắc version hóa) và khi gặp duplicate thì so sánh hash/metadata quan trọng. Nếu khác, **quarantine/alert**, không ghi đè hiệu ứng nghiệp vụ.

Hash không phải khóa dedupe thay thế business ID: hai event hợp lệ có nội dung giống hệt vẫn có thể là hai lần thực thi nghiệp vụ khác nhau.

## 5. Mẫu thiết kế: transactional inbox

**Transactional inbox** dùng một bảng có unique constraint để ghi nhận message đã xử lý **trong cùng transaction với thay đổi nghiệp vụ tại cùng database**.

~~~mermaid
flowchart TD
    B["Broker delivers event E"] --> W["Consumer worker"]
    W --> T["Begin DB transaction"]
    T --> I{"INSERT inbox key<br/>unique constraint"}
    I -- "Lần đầu" --> D["Áp dụng thay đổi nghiệp vụ"]
    D --> C["COMMIT cả inbox và business data"]
    I -- "Đã có" --> K["Đối chiếu identity/payload<br/>không áp dụng lại"]
    K --> A["Return thành công duplicate"]
    C --> A2["Return thành công first delivery"]
    A --> ACK["ACK broker sau DB commit"]
    A2 --> ACK
~~~

Phần “đã có” chỉ được coi là duplicate an toàn **nếu bản inbox tương ứng biểu diễn một lần xử lý đã commit thành công**. Với mẫu inbox và nghiệp vụ nằm **chung một transaction**, row của một lần xử lý thất bại trước commit sẽ rollback, nên không bị hiểu nhầm là đã xử lý. Nếu dùng bảng `PROCESSING` với commit sớm hoặc distributed workflow, cần state machine/lease/recovery bổ sung, không thể đơn giản bỏ qua mọi row đang tồn tại.

### 5.1. Schema ví dụ PostgreSQL

~~~sql
CREATE TABLE consumed_message (
    consumer_name     VARCHAR(100) NOT NULL,
    source_system     VARCHAR(100) NOT NULL,
    business_event_id VARCHAR(160) NOT NULL,
    payload_hash      VARCHAR(128) NOT NULL,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, source_system, business_event_id)
);

CREATE TABLE order_ledger (
    tenant_id       VARCHAR(100) NOT NULL,
    operation_id    VARCHAR(160) NOT NULL,
    order_id        VARCHAR(160) NOT NULL,
    amount          NUMERIC(18, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Hai unique constraints bảo vệ **hai mục tiêu khác nhau**:

1. `consumed_message` ngăn cùng **event** được consumer áp dụng lại.
2. `order_ledger` ngăn cùng **business operation** được thực hiện nhiều lần, kể cả nếu producer vô tình phát hai event ID khác nhau cho một operation.

Schema không có cột `status` vì ở mẫu này inbox row và business write được commit **cùng một transaction**, row đã commit có nghĩa transaction xử lý tương ứng đã commit. Nếu quy trình có nhiều giai đoạn bất đồng bộ, cần thêm trạng thái hoặc outbox và không được suy luận như trên.

### 5.2. Ví dụ consumer Spring JDBC + @Transactional

~~~java
import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public record OrderPosted(
        String eventId,
        String sourceSystem,
        String payloadHash,
        String tenantId,
        String operationId,
        String orderId,
        BigDecimal amount) {}

@Service
public class OrderPostedConsumer {

    private final JdbcTemplate jdbc;

    public OrderPostedConsumer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "businessTransactionManager")
    public void consume(OrderPosted event) {
        final String consumer = "order-ledger-v1";

        // PostgreSQL: unique constraint quyết định atomic ai được claim.
        int inserted = jdbc.update(
                """
                INSERT INTO consumed_message
                    (consumer_name, source_system, business_event_id,
                     payload_hash)
                VALUES (?, ?, ?, ?)
                ON CONFLICT
                    (consumer_name, source_system, business_event_id)
                DO NOTHING
                """,
                consumer,
                event.sourceSystem(),
                event.eventId(),
                event.payloadHash());

        if (inserted == 0) {
            String priorHash = jdbc.queryForObject(
                    """
                    SELECT payload_hash
                    FROM consumed_message
                    WHERE consumer_name = ?
                      AND source_system = ?
                      AND business_event_id = ?
                    """,
                    String.class,
                    consumer, event.sourceSystem(), event.eventId());

            if (!Objects.equals(priorHash, event.payloadHash())) {
                throw new IllegalStateException(
                        "Trùng event ID nhưng payload không khớp");
            }
            return; // Duplicate đã commit: không ghi ledger lần nữa.
        }

        // Cùng DB transaction: lỗi tại đây rollback cả inbox insert.
        jdbc.update(
                """
                INSERT INTO order_ledger
                    (tenant_id, operation_id, order_id, amount)
                VALUES (?, ?, ?, ?)
                """,
                event.tenantId(),
                event.operationId(),
                event.orderId(),
                event.amount());
    }
}
~~~

Mẫu trên dùng **Java 17 text blocks** và PostgreSQL `ON CONFLICT`. Khi đưa vào dự án Java, hãy đặt các kiểu `public` như `OrderPosted` và `OrderPostedConsumer` vào **những file Java riêng**. Nó minh họa consumer được gọi qua **Spring proxy** để `@Transactional` có hiệu lực; `businessTransactionManager` phải quản lý **đúng DataSource** của cả hai bảng. Nếu adapter broker gọi method từ bên trong cùng class bằng self-invocation, cần kiểm tra việc proxy transaction có thực sự được áp dụng.

**Giới hạn chủ đích của ví dụ:**

- `payloadHash` được tạo/kiểm tra ở tầng nhận theo quy tắc canonical hóa của ứng dụng; ví dụ giả định field đã hợp lệ.
- Không có external API call trong transaction. Nếu cần gọi API ngoài, dùng outbox hoặc idempotency key ở API đích.
- Nếu event ID đụng độ với hash khác, method ném lỗi; quy trình vận hành cần định nghĩa dead-letter/quarantine để tránh retry vô hạn.
- Nếu ledger đã có cùng `operationId` do **một event ID khác**, unique constraint làm transaction thất bại (inbox insert cũng rollback). Ứng dụng cần phân loại trường hợp này là duplicate business operation hay xung đột payload và reconcile trước khi ACK.
- Trong ví dụ này, `JdbcTemplate` phải trỏ tới cùng transactional database. Việc tồn tại `@Transactional` không bảo đảm atomic nếu hai bảng nằm ở hai datasource độc lập.

### Vì sao không làm SELECT trước rồi INSERT?

Mã sau có race:

~~~java
if (!alreadyProcessed(eventId)) {
    applyBusinessEffect();
    markProcessed(eventId);
}
~~~

Hai worker có thể cùng thấy “chưa xử lý” trước khi một worker ghi row. **Unique constraint/atomic insert** mới là hàng rào có thể chịu concurrency xuyên thread và JVM. Nếu cần trạng thái `IN_PROGRESS` dài hạn, phải có claim/lock/lease và cơ chế phục hồi owner chết, thay vì chỉ dựa vào SELECT.

### ACK phải xảy ra sau khi transaction hoàn tất

Adapter broker cần xác nhận message **sau khi method giao dịch đã return thành công và commit thực sự hoàn tất**. Nếu adapter ACK trước commit, consumer crash có thể làm mất công việc dù broker nghĩ message đã xong.

Với các listener container có auto-ack, manual-ack, batch ACK hoặc transaction integration khác nhau, phải xem chính xác semantics của thư viện/adapter thực tế. Không đặt lời gọi `acknowledge()` ngay giữa body `@Transactional` rồi mặc định đã an toàn: transaction có thể **chưa commit** khi code còn ở trong method.

## 6. Crash window: bảng quyết định

| Điểm crash | Inbox/business DB | Broker | Hành vi an toàn khi giao lại |
| --- | --- | --- | --- |
| Trước khi bắt đầu transaction | Chưa thay đổi | Chưa ACK | Xử lý lần đầu |
| Sau INSERT inbox nhưng **trước commit** | Transaction rollback khi connection/worker chết | Chưa ACK | Xử lý lại bình thường |
| Sau business SQL nhưng **trước commit** | Cả inbox và business rollback nếu chung transaction | Chưa ACK | Xử lý lại bình thường |
| **Sau COMMIT, trước ACK** | Inbox và business đều đã commit | Broker có thể giao lại | Inbox nhận diện duplicate và bỏ qua side effect |
| Sau ACK | Inbox và business đã commit | Broker coi đã hoàn tất | Không cần giao lại |

Bảng giả định **một transaction database atomic**, ACK thực hiện đúng sau commit và broker có chế độ giao lại khi chưa ACK. Những thao tác gửi HTTP, email hoặc message bên ngoài **không nằm trong bảng bảo đảm này**.

### Nếu đánh dấu inbox trước, rồi commit tách rời business write?

~~~text
Commit inbox E-1001 = processed
     ↓
Worker crash trước khi ghi ledger
     ↓
Broker redeliver E-1001
     ↓
Consumer thấy inbox đã có → bỏ qua
     ↓
Ledger thiếu E-1001 vĩnh viễn
~~~

Đây là lỗi **false positive dedupe**. Vì vậy, nếu không thể giữ inbox và business effect trong cùng transaction, phải dùng trạng thái/phối hợp khác: outbox, durable task state, idempotency key ở service nhận hoặc reconciliation.

## 7. Transactional outbox: khi còn phải phát message tiếp

Một worker có thể nhận `OrderPosted`, ghi database và phải phát tiếp `OrderEnriched`. Nếu ghi database thành công rồi publish event thất bại, downstream thiếu event. Nếu publish trước khi commit DB, downstream có thể nhận event cho dữ liệu sau đó rollback.

**Transactional outbox** ghi **ý định phát sự kiện** thành một row trong **cùng transaction** với thay đổi dữ liệu nghiệp vụ/inbox:

~~~mermaid
flowchart LR
    IN["Message broker input"] --> C["Consumer transaction"]
    C --> I[("Inbox unique key")]
    C --> D[("Business data")]
    C --> O[("Outbox event")]
    O --> P["Dispatcher / CDC"]
    P --> B["Message broker output"]
    B --> W["Downstream consumer<br/>inbox/dedupe riêng"]
~~~

Outbox dispatcher có thể gửi **một event nhiều lần** nếu publish thành công nhưng chưa đánh dấu outbox row là đã gửi. Vì vậy downstream vẫn cần dedupe. **Outbox giải quyết tính bền vững của ý định gửi**, không tự bảo đảm delivery exactly-once tới mọi đích.

### Khóa outbox có vai trò gì?

`outbox_event_id` nên là ID ổn định cho một **sự kiện nghiệp vụ**; dispatcher dùng lại ID đó khi retry. Consumer downstream sử dụng nó làm input business event ID. Không tự sinh ID mới mỗi khi publisher retry cùng row outbox.

Một workflow hoàn chỉnh thường có:

1. Consumer nhận input, kiểm tra inbox và áp dụng business effect cùng transaction.
2. Transaction ghi outbox row với stable event ID.
3. Dispatcher đọc outbox chưa giao, publish, rồi đánh dấu `SENT` hoặc tiến độ dispatch theo cơ chế phù hợp.
4. Consumer phía sau dedupe theo stable event ID của outbox.
5. Hệ thống đối soát row outbox tồn lâu hoặc chưa được ACK.

## 8. Áp dụng trong Spring Batch remote chunking

Trong **remote chunking**, manager thường **đọc item và tạo chunk requests**, gửi chunk qua middleware; worker xử lý/ghi rồi gửi **reply** về manager.

~~~text
Manager:
  read items -> tạo chunk request -> publish request

Worker:
  consume request -> process/write -> reply

Manager:
  consume reply -> cập nhật tiến độ/điều phối
~~~

### Các điểm có thể lặp

| Đối tượng | Tại sao lặp? | Dedupe/correlation cần gì? |
| --- | --- | --- |
| **Chunk request** | Broker redelivery, manager gửi lại sau timeout | Stable chunk/work-unit ID và nhận diện attempt |
| **Business item trong chunk** | Chunk bị replay, rollback hoặc restart | Business idempotency key theo item/operation |
| **Chunk reply** | Worker reply lại, broker giao lại hoặc reply đến trễ | Correlation tới request và attempt; manager xử lý reply idempotent |

Đừng khẳng định một `ChunkRequest` có đúng một unique key với format giống nhau ở mọi phiên bản Spring Batch Integration. Thiết kế dedupe dựa trên **metadata correlation thực tế của framework**, phiên bản đang dùng và business identity ổn định; khi cần hãy bổ sung envelope/event ID do ứng dụng kiểm soát.

### Vì sao chỉ dedupe chunk ID có thể chưa đủ?

Giả sử chunk #7 chứa 200 item. Lần chạy đầu ghi 120 item thành công ở một hệ thống không transactional, rồi worker crash; chunk được gửi lại. Nếu chỉ dedupe chunk sau khi hoàn tất, những item đã ghi sẽ được gửi lần nữa.

**Cần idempotency cấp item/business operation tại đích**, đặc biệt với API, file hoặc database ngoài transaction quản lý inbox. Dedupe chunk giúp giảm thực thi thừa, nhưng không thay thế chống trùng nghiệp vụ khi chunk có partial side effects.

### Phân biệt request/reply và trạng thái commit

Manager có thể nhận một **reply thành công** từ worker nhưng chưa cập nhật được `JobRepository`, hoặc worker đã commit nhưng reply chưa tới. Vì thế:

- Không lấy một reply đến hai lần làm tín hiệu “xử lý business hai lần”.
- Không cập nhật trạng thái manager theo reply cũ của attempt đã hết hiệu lực.
- Đối chiếu `StepExecution`/chunk state, request identity và business ledger để xử lý các trường hợp không rõ.
- Kiểm tra thời gian lưu dữ liệu dedupe đủ dài cho khoảng thời gian retry/restart hợp lệ.

## 9. Áp dụng trong Spring Batch remote partitioning

Trong **remote partitioning**, manager giao một **worker step execution** cùng `ExecutionContext` mô tả phạm vi xử lý, thường qua message; worker thực thi step ở JVM khác.

Ví dụ:

~~~text
JobInstance: import-orders-2026-11-26
Manager step: importManager
Partition key: range-0003
Input range: [300001, 400001)
Worker StepExecution attempt: ID=712
~~~

### Hai mức identity khác nhau

**Work-unit identity** nhận diện công việc logic, chẳng hạn:

~~~text
(jobInstanceIdentity, managerStepName, partitionKey, inputSnapshotVersion)
~~~

Nó hữu ích để biết “partition range-0003 trong kế hoạch này” là một phần việc. Nhưng **worker `StepExecutionId`** nhận diện **một lần thực thi** của phần việc đó; khi restart có thể có ID khác.

Không dùng duy nhất work-unit identity để vô điều kiện chặn **mọi lượt thực thi lại**: nếu attempt trước bị lỗi chưa hoàn thành, cần cho worker hợp lệ tiếp tục/restart. Ngược lại, không dùng duy nhất `StepExecutionId` để bảo vệ business effects xuyên restart vì attempt mới có ID mới.

| Mục tiêu | Khóa và trạng thái phù hợp |
| --- | --- |
| Không chạy **hai worker đồng thời cho cùng execution** | Claim/lease/lock theo `StepExecutionId` hoặc worker task ID, kiểm tra trạng thái |
| Không chạy lại partition đã `COMPLETED` | `JobRepository`, `StepExecutionSplitter` và chính sách restart |
| Cho phép restart partition `FAILED` | Attempt/state mới gắn với **cùng partition logic** |
| Không ghi hai lần một order trong partition | Unique business operation key tại database/service đích |
| Không dùng reply cũ để hoàn tất attempt mới | Correlation request/reply gồm execution/attempt identity |

### Worker cũ chưa dừng nhưng manager đã gửi lại

Đặc biệt trong remote partitioning, một worker có thể bị coi là timeout trong khi thực tế vẫn đang chạy. Một worker khác nhận cùng partition có thể đọc/ghi trùng.

Cơ chế phòng vệ có thể gồm:

- Coordinator kiểm tra trạng thái execution và ngăn **hai owners cùng active** khi có thể.
- Lease/claim có thời hạn và fencing token nếu tài nguyên đích hỗ trợ kiểm tra thế hệ owner.
- Business idempotency key/unique constraint cho từng bản ghi.
- Kiểm tra worker thực sự đã dừng trước khi restart; không chỉ dựa vào timeout.
- Hòa giải trạng thái từ `JobRepository`, broker và business store.

**Một lock trong bộ nhớ manager không đủ** khi có nhiều JVM, failover hoặc worker đang giữ kết nối cũ. Dedupe message cũng không tự ngăn worker đã nhận request từ trước tiếp tục ghi dữ liệu sau khi mất lease; khi rủi ro nghiêm trọng cần fencing hoặc kiểm soát ở nơi thực hiện side effect.

## 10. Dedupe trong một JVM và giữa nhiều JVM

Một cache trong RAM có thể giảm số lần tính toán lặp trong **cùng một tiến trình**, nhưng không phải nguồn chân lý cho dedupe có tính bền vững.

| Cơ chế | Hữu ích | Không đủ khi |
| --- | --- | --- |
| `ConcurrentHashMap` trong worker | Tránh xử lý trùng ngắn hạn trong JVM | Pod restart, JVM khác, consumer khác |
| Redis `SETNX` hoặc key TTL | Giảm duplicate, phối hợp tạm thời giữa node | Key hết hạn, side effect khác hệ thống không cùng transaction |
| DB unique constraint + transaction | Dedupe bền vững xuyên worker/JVM | Side effect nằm ngoài transaction DB |
| Broker-side dedupe | Giảm duplicate publish/delivery theo phạm vi broker hỗ trợ | Producer có event ID mới hoặc nghiệp vụ ghi DB/API riêng |
| Idempotency key được service nhận xác nhận | Bảo vệ thao tác ở downstream | Service không lưu key đủ lâu hoặc trả kết quả không nhất quán |

### Lưu ý với Redis và trạng thái PROCESSING

Ví dụ worker dùng `SETNX(eventId)` rồi gọi một API. Nếu worker crash sau khi set key nhưng trước khi gọi API, các worker sau có thể thấy key tồn tại và **bỏ qua event chưa xử lý**. Ngược lại, nếu TTL hết sau khi API đã xử lý, event có thể bị thực hiện lại.

Muốn dùng cache/lease có ý nghĩa, phải có:

1. Trạng thái `PROCESSING` / `COMPLETED` được định nghĩa rõ;
2. Claim atomic và cơ chế phục hồi owner chết;
3. Retention dài hơn cửa sổ redelivery/replay;
4. Hàng rào idempotency ở chính hệ thống đích hoặc reconciliation khi không thể giao dịch atomic.

Redis không tự tạo một transaction atomic với một database/HTTP API khác.

## 11. Retention, TTL và message đến sai thứ tự

### Giữ dedupe record trong bao lâu?

Phải tính theo **cửa sổ lớn nhất mà một event có thể được giao lại**, không chỉ theo thời gian xử lý một chunk:

~~~text
Retention dedupe
  >= thời gian redelivery hợp lệ
     + thời gian giữ dead-letter/quarantine có thể replay
     + cửa sổ restart/khôi phục job
     + biên an toàn theo chính sách vận hành
~~~

Đây là **hướng thiết kế**, không phải một công thức thời gian chính xác áp dụng cho mọi broker. Nếu nghiệp vụ yêu cầu “một operation không bao giờ được thực hiện hai lần”, thường cần **business ledger/unique key lâu dài**, thay vì xóa inbox sau vài giờ.

Trước khi xóa dedupe rows, phải có chính sách archival, luật replay, cửa sổ xác nhận và test một event cũ được phát lại sau cleanup.

### Duplicate khác out-of-order

Hai message:

~~~text
E-1: Order status = PAID, version = 4
E-2: Order status = CANCELLED, version = 5
~~~

Nếu `E-2` đến trước `E-1`, cả hai đều là **event khác nhau** nên inbox dedupe theo event ID **không chặn được việc áp dụng trạng thái cũ sau trạng thái mới**.

Để xử lý out-of-order:

- Mang `aggregateId` và `aggregateVersion`/sequence do nguồn cấp.
- Áp dụng optimistic version check hoặc state transition được phép.
- Định nghĩa rõ event cũ bị bỏ qua, trì hoãn hay đưa vào reconciliation.
- Đừng đoán sequence từ thời điểm consumer nhận message.

Ví dụ DB:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :newVersion
WHERE order_id = :orderId
  AND version = :expectedPreviousVersion;
~~~

Nếu câu lệnh cập nhật 0 hàng, đó có thể là duplicate, out-of-order hoặc version conflict; consumer phải đọc trạng thái và phân loại đúng. Không tự ACK vô điều kiện chỉ vì update count bằng 0.

## 12. Khi dedupe làm sai nghiệp vụ

### False positive: hai giao dịch hợp lệ bị coi là một

Nếu một hệ thống chỉ dùng `(customerId, amount)` làm dedupe key, hai đơn hàng cùng khách với cùng giá là **hai nghiệp vụ khác nhau** nhưng có thể bị bỏ qua mất một.

### False negative: một nghiệp vụ có hai transport IDs

Producer timeout và phát lại cùng yêu cầu thanh toán nhưng tạo `UUID` mới cho mỗi message. Dedupe bằng transport ID xem đó là hai event khác nhau. Cần **business operation ID** bền vững do producer tạo **trước lần thử publish đầu tiên**, giữ nguyên qua mọi retry.

### Dedupe sai namespace

Tenant A và tenant B đều có `orderId=1001`. Nếu bảng inbox chỉ dùng `orderId` và bỏ qua tenant/source, một tenant có thể khiến event hợp lệ của tenant khác bị chặn. Đây còn là vấn đề cách ly dữ liệu, không chỉ sai số thống kê.

### Nuốt lỗi logic

Consumer gặp cùng event ID nhưng payload amount khác, lại coi là duplicate bình thường. Đó có thể là lỗi upstream nghiêm trọng; cần incident/quarantine thay vì im lặng.

## 13. Kiểm thử message deduplication

### 13.1. Unit test: identity và policy

Các test unit nên chứng minh:

- Cùng `businessEventId` và cùng payload canonical -> nhận diện duplicate hợp lệ.
- Cùng event ID nhưng payload khác -> conflict, không áp dụng lại.
- Cùng nội dung payload nhưng **khác event ID có ý nghĩa nghiệp vụ riêng** -> không tự động bỏ qua.
- Cùng event ID cho hai consumer khác nhau -> hai consumer xử lý công việc riêng.
- Cùng order ID nhưng khác tenant -> không collide.

Unit test chỉ kiểm tra logic; **không chứng minh unique constraint chịu được race**.

### 13.2. Integration test: cùng message hai lần

Với PostgreSQL test database:

~~~java
@Test
void duplicateMessageKhongGhiLedgerHaiLan() {
    OrderPosted event = new OrderPosted(
            "evt-1001",
            "orders-service",
            "sha256:example-stable-hash",
            "tenant-A",
            "op-1001",
            "order-1001",
            new BigDecimal("125.00"));

    consumer.consume(event);
    consumer.consume(event); // Broker redelivery được mô phỏng.

    Integer ledgerRows = jdbc.queryForObject(
            "SELECT COUNT(*) FROM order_ledger "
            + "WHERE tenant_id=? AND operation_id=?",
            Integer.class,
            "tenant-A", "op-1001");

    assertEquals(1, ledgerRows);
}
~~~

Đây là **đoạn test tích hợp minh họa**; cần Spring context, `OrderPostedConsumer` dùng proxy `@Transactional`, bảng SQL và `JdbcTemplate` đúng datasource. Test còn phải kiểm tra nội dung amount, tenant và inbox row. Dùng riêng `COUNT(*)` chưa chứng minh mọi side effect được bảo vệ nếu consumer gửi API ngoài.

### 13.3. Test cạnh tranh: hai worker nhận cùng event

Hai `@Transactional` consumer ở hai thread hoặc hai JVM cố xử lý **cùng event** trong một thời điểm. Kỳ vọng chỉ một transaction nhận được claim mới; transaction kia phải chờ/quan sát unique constraint rồi nhận diện duplicate sau commit, hoặc thất bại có thể retry theo cơ chế DB.

**Đừng viết test chỉ chạy tuần tự** rồi kết luận dedupe an toàn đa worker. Cần:

1. Test database cùng loại với production nếu có thể, ví dụ PostgreSQL Testcontainers.
2. Hai connection/transaction thật, có latch để ép hai worker khởi động gần đồng thời.
3. Unique constraint trên inbox và business ledger hoạt động.
4. Chỉ một business effect được commit; không có hai ledger rows.
5. Nếu một worker rollback, worker còn lại vẫn có thể xử lý hợp lệ.

Lưu ý PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` có thể phải **đợi transaction khác kết thúc** trước khi quyết định duplicate. Đây là hành vi đúng để tránh race, nhưng cần đo contention/lock waits khi tải tăng.

### 13.4. Test crash windows

| Điểm lỗi cố ý | Kỳ vọng |
| --- | --- |
| Crash trước khi nhận message | Broker có thể giao lại; xử lý lần đầu |
| Crash sau INSERT inbox, trước commit | Transaction rollback; redelivery xử lý được |
| Crash sau business SQL, trước commit | Inbox/business cùng rollback; không có hiệu ứng nửa vời |
| Crash sau commit, trước ACK | Redelivery bị nhận diện duplicate; không ghi lại |
| Cùng event ID, payload khác | Đưa vào conflict/quarantine, không ACK như duplicate hợp lệ |
| Cùng business operation, event ID khác | Unique operation key chặn double effect; có reconciliation |
| Restart `JobInstance` | Không dựa vào `JobExecutionId` mới để bỏ qua business dedupe |
| Broker reply đến chậm hoặc lặp | Manager không cập nhật attempt mới bằng reply cũ |
| Dedupe TTL hết trước replay | Test phát hiện duplicate side effect; sửa retention/ledger |
| Hai version đến sai thứ tự | Aggregate state không bị lùi version |

### 13.5. Test Spring Batch remote chunking/partitioning

Với remote chunking:

- Giả lập request redelivery, chunk reply duplicate và reply đến sau khi manager timeout.
- Kiểm tra không nhân đôi writer side effects theo **business key**.
- Xác minh chunk progress và `JobRepository` sau restart.

Với remote partitioning:

- Giả lập worker cũ chưa dừng trong khi manager gửi partition cho worker khác.
- Kiểm tra claim/fencing nếu có, cùng idempotency tại đích.
- Xác minh partition `COMPLETED` không được chạy lại trái chính sách, partition `FAILED` còn có đường restart hợp lệ.

**Quan trọng:** Kiểm thử phải đối soát đầu ra, không chỉ assert `BatchStatus.COMPLETED` hoặc số lượng ACK. Một worker có thể hoàn tất Batch nhưng tác dụng ngoài transaction bị nhân đôi.

## 14. Quan sát và đo bottleneck

### Các metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| `messages_received_total` | Tổng deliveries được consumer nhận |
| `messages_duplicate_total` | Số deliveries bị nhận diện duplicate |
| `messages_identity_conflict_total` | Cùng event ID nhưng payload/source metadata không nhất quán |
| `messages_processed_total` | Số events được áp dụng thành công tại consumer |
| `consumer_transaction_rollback_total` | Số transaction bị rollback |
| `inbox_insert_latency` / lock wait | Chi phí unique constraint, contention |
| `outbox_pending` và tuổi bản ghi cũ nhất | Message chưa phát được |
| `broker_redelivery_total` / lag / DLQ depth | Chất lượng transport và worker capacity |
| `business_duplicate_prevented_total` | Business operation đã có từ event ID khác |
| `reconciliation_mismatch_total` | Sự khác nhau giữa inbox, output và ledger |

Không gắn `businessEventId`, `orderId` hoặc `StepExecutionId` làm **label dài hạn** cho mọi metric, vì cardinality rất lớn. Dùng log/tracing có kiểm soát hoặc truy vấn inbox/ledger để điều tra từng event.

### Throughput và dedupe overhead

Với hàng triệu event, inbox row và unique index có thể trở thành điểm nghẽn. Cách tối ưu phải dựa trên **đo thực tế**:

- Chọn khóa/index đúng truy vấn dedupe, tránh thêm quá nhiều index không cần thiết.
- Sử dụng connection pool tương ứng với worker concurrency và giới hạn database.
- Kiểm tra lock contention khi cùng key được giao lại liên tục.
- Có chính sách partition/archival dedupe records **phù hợp retention**, không xóa sớm chỉ để giảm dung lượng.
- Batch insert có thể tăng throughput, nhưng xử lý một duplicate trong batch không được làm mất những event hợp lệ còn lại.
- Thống kê tỷ lệ duplicate, transaction latency, throughput, CPU, I/O và khả năng restart trước khi tăng `gridSize` hoặc số consumer.

Tăng `gridSize` khi database đã nghẽn unique index có thể làm job **chậm hơn**, không nhanh hơn. Dedupe là yêu cầu tính đúng; tối ưu hiệu năng không được bỏ unique constraint hoặc ACK sớm để “giảm latency”.

## 15. Runbook khi xuất hiện duplicate hoặc dữ liệu bị thiếu

1. **Xác định identity:** Source system, tenant, business event ID, operation ID, JobInstance, partition và attempt.
2. **Phân biệt transport duplicate với business duplicate:** Có bao nhiêu deliveries/ACK, bao nhiêu inbox rows và bao nhiêu effects thật?
3. **Đọc trạng thái transaction:** Có crash giữa commit và ACK, hoặc inbox được commit tách rời business write không?
4. **Kiểm tra producer:** Có tạo lại message/event ID mỗi lần retry publish không? Outbox có stable event ID không?
5. **Kiểm tra consumer:** Unique constraint có thực sự tồn tại? Method `@Transactional` có chạy qua proxy và đúng datasource không?
6. **Kiểm tra worker concurrency:** Có hai worker cùng nhận partition, listener dùng shared mutable singleton, hoặc lease hết hạn khi worker cũ còn chạy không?
7. **Kiểm tra retention:** Inbox/Redis dedupe key đã bị xóa trước khi job restart hoặc DLQ replay chưa?
8. **Đối soát nghiệp vụ:** So sánh nguồn event, inbox, ledger, outbox và hệ thống bên ngoài theo operation ID.
9. **Khắc phục an toàn:** Không tự xóa inbox để “chạy lại cho chắc”. Với hiệu ứng chưa rõ, xác minh đích rồi mới quyết định replay/compensate.
10. **Cập nhật kiểm thử và guardrails:** Bổ sung ca crash window, two-workers-same-key, reply cũ, schema mismatch và circuit breaker nếu downstream quá tải.

### Khi nào đưa vào quarantine?

Đưa vào quarantine/manual review khi:

- Cùng event ID nhưng payload khác;
- Không xác định được business operation key;
- Message schema/version không hỗ trợ;
- Ledger và inbox thể hiện kết quả mâu thuẫn;
- Tác dụng bên ngoài ở trạng thái chưa rõ, không thể xác nhận tự động;
- Event liên tục thất bại dù đã hết ngân sách retry.

**Đừng coi quarantine là skip im lặng**. Quarantine phải có source identity, lý do, thời điểm, owner, trạng thái xử lý và đường replay có kiểm soát.

## 16. Bài tập tình huống

Một Spring Batch job chia 8 partition xử lý giao dịch và gửi message sang dịch vụ khác. Worker dùng `ConcurrentHashMap<String, Boolean>` để tránh event lặp. Dữ liệu mỗi partition được ghi vào database, nhưng worker ACK broker ngay khi đọc message, trước khi commit. Một ngày, manager timeout và khởi động lại partition trên node mới. Node cũ vẫn còn chạy; một số giao dịch xuất hiện hai lần ở hệ thống đích, trong khi một số event khác bị mất.

Hãy trả lời:

1. Vì sao `ConcurrentHashMap` không đủ làm dedupe giữa node và restart?
2. Vì sao ACK trước database commit có thể gây mất dữ liệu?
3. Vì sao event ID, `StepExecutionId` và business operation ID không thể dùng thay thế nhau một cách tùy tiện?
4. Khi cùng một partition được hai worker xử lý, cần những cơ chế nào ngoài message dedupe?
5. Nếu worker phải phát message tiếp sau khi ghi DB, cần mô hình nào để tránh DB đã commit nhưng không publish?
6. Những test và metric nào sẽ giúp phát hiện lỗi trước production?

**Định hướng trả lời:** RAM cache mất khi restart và không chia sẻ giữa JVM; ACK sớm có thể khiến broker không giao lại dù transaction business rollback. Dùng stable event ID để dedupe deliveries, business operation key để bảo vệ side effect xuyên attempt, execution/partition identity để điều phối. Dùng unique DB constraint và transactional inbox, ACK sau commit, outbox cho message đi tiếp, claim/fencing nếu worker cũ có thể chạy chồng. Kiểm thử crash trước/sau commit, redelivery, concurrency, reply trễ, restart và đối soát ledger theo operation ID.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): local/remote partitioning và mô hình scale.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): các mô hình message-driven với Spring Integration.
- [Spring Batch Reference — Remote Chunking](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-chunking.html): manager/worker chunk request–reply.
- [Spring Batch Reference — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): worker `StepExecution` từ xa.
- [Spring Batch Reference — JobRepository and Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): metadata job/step và restart.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, proxy và phạm vi transaction.
- [PostgreSQL Documentation — INSERT ... ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upsert và xử lý unique conflicts ở PostgreSQL.

> **Ghi nhớ:** Hệ thống message phân tán có thể giao lại cùng công việc **nhiều lần**. Mục tiêu là **business effect đúng một lần theo identity nghiệp vụ** hoặc đạt trạng thái có thể đối soát, không phải tin rằng delivery chỉ diễn ra một lần. Hãy dùng **stable event/operation ID**, transactional inbox hoặc idempotency key ở đích, ACK sau commit, outbox khi phát sự kiện tiếp, cùng kiểm thử crash/restart và concurrency xuyên JVM.
