# Idempotent Receiver Pattern trong Spring Integration Adapters

## 1. Vì sao một message có thể tới hai lần?

Hãy hình dung hệ thống nhận một sự kiện `ORDER_CONFIRMED` từ Kafka, ghi trạng thái đơn hàng vào database rồi gửi thông báo. Database đã cập nhật thành công, nhưng ngay trước khi consumer xác nhận offset, JVM bị dừng. Kafka có thể giao lại record khi consumer khởi động; nếu handler chạy lại toàn bộ nghiệp vụ, người dùng có thể bị gửi hai thông báo hoặc bị ghi hai giao dịch.

Tình huống này không phải lỗi riêng của Kafka. **HTTP client retry sau timeout, JMS/AMQP redelivery, SFTP quét lại file, JDBC poll lại row, File watcher phát lại, broker failover hoặc operator replay từ DLQ** đều có thể làm cùng một *logical event* tới receiver nhiều lần.

**Idempotent Receiver** là một **Enterprise Integration Pattern** thiết kế để phía nhận nhận diện và xử lý một cách an toàn những lần giao lặp: **một sự kiện nghiệp vụ đã xử lý thành công không được tạo thêm tác dụng phụ không mong muốn khi xuất hiện lần nữa**.

Trong module **SPRING_INTEGRATION_ADAPTERS**, pattern này gắn với inbound/outbound adapter, gateway, poller và `MessageChannel`, các luồng File/SFTP/HTTP/JMS/AMQP/Kafka/database, cũng như hợp đồng message, retry, lỗi và vòng đời kết nối. Nó thuộc chương **Design patterns** vì là **quyết định kiến trúc của receiver**, không chỉ là một câu lệnh kiểm tra `if (seen) return`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **duplicate delivery, duplicate processing, idempotent side effect** và “exactly-once” ở những ranh giới khác nhau.
2. Chọn **idempotency key** ổn định, có scope và vòng đời phù hợp.
3. Thiết kế **kiểm tra–ghi nhận nguyên tử** bằng metadata store hoặc cơ sở dữ liệu có unique constraint.
4. Dùng cơ chế **`IdempotentReceiverInterceptor`/`MetadataStoreSelector`** của Spring Integration khi phù hợp.
5. Xử lý crash, concurrency, retry, DLQ, transaction, broker ACK và external side effect.
6. Áp dụng pattern cho File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC và kiểm thử những race condition quan trọng.

> **Nguyên tắc xuyên suốt:** *Idempotent receiver không biến mọi luồng phân tán thành exactly-once*. Cần xác định “once” có nghĩa là **một lần cập nhật DB**, **một lần gửi sang API**, **một lần publish broker** hay **một lần hoàn thành nghiệp vụ**; mỗi mục tiêu đòi hỏi điểm xác nhận khác nhau.

## 2. Thuật ngữ nền tảng

| Thuật ngữ | Nghĩa trong bài | Ví dụ |
|---|---|---|
| **Logical event** | Sự kiện/lệnh nghiệp vụ cần xử lý | “Đơn A đã thanh toán” |
| **Delivery** | Một lần transport giao thông điệp | Kafka poll/JMS delivery |
| **Processing attempt** | Một lần handler được gọi | Retry lần 1, lần 2 |
| **Side effect** | Thay đổi có thể quan sát bên ngoài handler | Ghi DB, gửi tiền, tạo file, publish |
| **Idempotency key** | Khóa nhận diện thao tác logic đã xử lý | `tenant:order-confirmation:event-74` |
| **Duplicate** | Cùng logical operation đã/đang được xử lý xuất hiện lại | Event 74 được giao lại |
| **Claim/dedup reservation** | Bước giành quyền xử lý theo key | Insert unique/put-if-absent |
| **Completion marker** | Bằng chứng operation hoàn tất theo phạm vi định nghĩa | Bản ghi `COMPLETED` có transaction |
| **Redelivery** | Broker chuyển lại thông điệp đã giao | JMS rollback, AMQP NACK/requeue |
| **Replay** | Cố ý xử lý lại từ DLQ/topic/file/log | Reprocess sự kiện theo yêu cầu |
| **Idempotent effect** | Áp dụng lại cùng command không làm đổi kết quả ngoài lần đầu | `SET status=PAID` thay vì `balance += amount` |

### 2.1. Phát lại không phải lúc nào cũng là lỗi

Nhiều transport được thiết kế theo **at-least-once delivery** hoặc có retry để tăng độ tin cậy. Giữ lại message rồi redeliver khi chưa chắc ACK thường tốt hơn làm mất dữ liệu. Vì thế receiver cần chấp nhận khả năng gặp duplicate như **điều kiện vận hành bình thường**.

### 2.2. Duplicate delivery và duplicate business action

Receiver nhận ba deliveries cùng một event có thể ghi **ba log attempts** nhưng chỉ nên tạo **một side effect đã cam kết** trong phạm vi nghiệp vụ đã chọn. Nếu đếm số handler invocations để báo số đơn hàng xử lý, dashboard sẽ phóng đại kết quả.

## 3. Những nguồn tạo duplicate thường gặp

| Nguồn | Vì sao lặp? | Chỗ cần xác minh |
|---|---|---|
| **HTTP inbound gateway** | Client retry khi kết nối đứt hoặc request timeout | Idempotency-Key, server state, response replay |
| **HTTP outbound gateway** | Receiver gọi remote rồi không nhận response | Remote có thể đã commit |
| **File inbound** | Khởi động lại, file filter/metadata store mất state | Identity file, fingerprint, lifecycle |
| **SFTP inbound** | Transfer gián đoạn, remote file còn nguyên, restart | Remote identity, metadata store, rename/handoff |
| **JMS inbound** | Transaction rollback, ACK không hoàn tất | Message ID, redelivery, DB transaction |
| **AMQP inbound** | NACK/requeue, unacked message khi consumer chết | Delivery count, DLQ, consumer ACK |
| **Kafka inbound** | Offset chưa commit, rebalance, retry/replay | Topic-partition-offset và event ID |
| **JDBC inbound poller** | Row chưa đánh dấu processed khi crash | Watermark/processed marker và transaction |
| **QueueChannel** | Hệ ứng dụng chủ động resubmit hoặc job retry | Retry key và in-memory/durable state |
| **Batch splitter** | Cả batch chạy lại, một số items đã xong | Parent/child identity, per-item completion |
| **Operator replay** | Đưa DLQ/file vào flow lần nữa | Replay policy, idempotency window |

Một message được truyền lại không nhất thiết có **cùng Spring Message ID**, timestamp, trace ID hoặc broker delivery tag. Chọn key chỉ dựa trên một trong các trường đó có thể khiến receiver **không nhận ra cùng nghiệp vụ**.

## 4. Mô hình Idempotent Receiver: nhận diện trước khi tạo side effect

~~~mermaid
flowchart TD
    A[Inbound adapter / gateway] --> B[Message và hợp đồng event]
    B --> C[Validate key, scope, operation]
    C --> D{Atomic claim / lookup}
    D -->|Completed duplicate| E[Skip effect hoặc replay prior result]
    D -->|New claim| F[Apply business effect]
    F --> G{Effect committed?}
    G -->|Yes| H[Record COMPLETED / receipt]
    G -->|No, rollback| I[Release in same transaction / retry safely]
    D -->|In progress/unknown| J[Retry later, wait hoặc reconcile]
    H --> K[ACK / reply theo protocol]
    E --> K
    I --> L[Error / retry / DLQ policy]
    J --> L
~~~

Điểm quyết định quan trọng: **không đánh dấu “đã hoàn tất” trước khi tác dụng phụ cần bảo vệ thực sự được xác nhận**, trừ khi marker và side effect được cập nhật **trong cùng một transaction nguyên tử**. Ngược lại, cũng không để hai worker cùng xử lý vì đọc `seen=false` rồi cùng ghi.

### 4.1. “Drop duplicate” chỉ là một lựa chọn

Với consumer one-way, duplicate đã hoàn tất có thể được **bỏ qua và ACK**. Với HTTP request/reply, gọi trùng cần có thể **trả lại kết quả trước đó** (status/body/reference) theo contract, thay vì im lặng và để client timeout. Với duplicate đang xử lý, có thể trả `202`/`409`/`Retry-After` tùy API design — không có một response bắt buộc cho mọi hệ thống.

### 4.2. Ba trạng thái cần tách

- **NEW:** key chưa được xử lý; có thể tranh chấp quyền claim.
- **IN_PROGRESS/UNKNOWN:** có người đã claim nhưng chưa xác nhận hoàn tất; không tự xem là success.
- **COMPLETED:** side effect đã đạt định nghĩa hoàn tất và có bằng chứng bền vững.

Nếu lưu lỗi cuối cùng/response để replay, có thể thêm `FAILED_TERMINAL` hoặc `FAILED_RETRYABLE`, nhưng phải định nghĩa rõ một request lỗi có được phép gọi lại với cùng key hay không.

## 5. Bước khó nhất: xác định “cùng một thao tác”

### 5.1. Thiết kế idempotency key

Một key tốt phải:

1. **Ổn định** giữa lần nhận đầu và redelivery/retry của cùng logical operation.
2. **Duy nhất trong scope** cần bảo vệ: tenant, nguồn, loại thao tác hoặc business event ID.
3. **Không bị thay** bởi serialization, message conversion, consumer rebalance hoặc deployment.
4. **Đủ phân biệt** hai tác vụ nghiệp vụ thực sự khác nhau.
5. **Có chính sách cấp phát/độ tin cậy** khi key do hệ thống ngoài cung cấp.
6. **Không chứa credential/PII** trong log, cache key công khai hay metric labels.
7. **Có cửa sổ giữ trạng thái** phù hợp retry horizon, broker retention và khả năng replay.

Ví dụ mang tính khái niệm:

~~~text
idempotencyKey = namespace + ":" + tenantRef + ":" +
                 operationType + ":" + stableEventId
~~~

`tenantRef` là ID nội bộ hợp lệ hoặc opaque reference được quản lý, không phải raw email/tên khách hàng. `stableEventId` phải đến từ nguồn đáng tin hoặc được ánh xạ bền vững.

### 5.2. Những key thường sai

| Key | Vì sao nguy hiểm? | Khi nào có thể dùng? |
|---|---|---|
| `MessageHeaders.ID` | Tạo message mới có ID khác | Chỉ muốn dedup đúng instance message cục bộ |
| `traceId`/`spanId` | Trace thay đổi theo retry, replay | Không dùng làm business idempotency key |
| Kafka topic-partition-offset | Nhận ra một record vật lý nhưng không dedup hai records cùng event | Khi yêu cầu chỉ xử lý mỗi Kafka record một lần |
| JMSMessageID | Có thể khác khi producer gửi lại cùng logical event | Khi contract chỉ cần identity một JMS delivery record |
| Filename | Cùng tên có nội dung mới hoặc rename; tên có PII | Khi source quy định tên không tái sử dụng và tin cậy |
| `lastModified` đơn lẻ | Collision, clock resolution, timestamp thay đổi | Một tín hiệu phụ trong file identity |
| Raw HTTP request body hash | Body có thể chứa PII; canonicalization/schema khó | Chỉ theo thiết kế hash đã kiểm soát và contract rõ |
| Client-supplied key bất kỳ | Có thể giả/va chạm giữa tenants | Sau auth, scope, length, ownership và conflict validation |
| Current timestamp | Retry có key mới | Hầu như không phù hợp |

### 5.3. Cùng key nhưng payload khác

Giả sử HTTP request thứ hai dùng cùng `Idempotency-Key` nhưng thay amount/recipient. Nếu chỉ trả kết quả cũ, bạn có thể che lỗi hoặc bị tấn công. Hãy lưu **request fingerprint đã canonicalize** hoặc các thuộc tính nghiệp vụ bất biến cần thiết, rồi:

- Key giống + fingerprint giống + đã hoàn tất → trả prior result.
- Key giống + fingerprint khác → **reject conflict**, không xử lý thao tác khác dưới cùng key.
- Key giống + IN_PROGRESS → phản hồi “đang xử lý” hoặc áp retry/wait policy.

Fingerprint phải được lưu/so sánh an toàn, không log raw nội dung nhạy cảm. Canonicalization cần tính đến thứ tự JSON fields, số thập phân, locale, schema version và nghĩa của API.

## 6. Atomicity: vì sao `containsKey` rồi `put` là sai?

### 6.1. Race condition kinh điển

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant S as Dedup Store
    participant B as Consumer B
    participant DB as Business Database
    A->>S: contains(key) = false
    B->>S: contains(key) = false
    A->>DB: Apply side effect
    B->>DB: Apply side effect
    A->>S: put(key, completed)
    B->>S: put(key, completed)
    Note over A,B: Cùng logical event tạo hai side effects
~~~

Hai consumer cùng thấy “chưa xử lý”, rồi đều thực hiện. Việc thêm `synchronized` trong một JVM chỉ bảo vệ instance đó, **không đủ khi có nhiều pod/process**.

### 6.2. Các primitive phù hợp

- **Database unique constraint** cho khóa idempotency, với insert và side effect trong transaction phù hợp.
- **Atomic `putIfAbsent`/compare-and-set** của một **shared ConcurrentMetadataStore**, nếu cần claim trước khi xử lý.
- **Conditional insert / optimistic version** với policy xử lý state `IN_PROGRESS`.
- **Business unique key/constraint** tại bảng đích nếu side effect là tạo resource.
- **Remote API idempotency contract** khi side effect nằm ở dịch vụ khác.

Không chỉ cần atomic **claim**; còn phải hiểu **điểm commit của side effect** và thời điểm ACK message.

### 6.3. Giới hạn của lock phân tán

Một distributed lock có thể ngăn xử lý đồng thời, nhưng nếu lock hết lease khi worker vẫn đang làm hoặc bị network partition, worker khác có thể vào. Với side effect quan trọng, cần **fencing token/version, uniqueness ở đích hoặc transactional design**, không chỉ dựa vào “đã giữ Redis lock”.

## 7. State machine của một idempotent operation

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> IN_PROGRESS: Atomic claim
    IN_PROGRESS --> COMPLETED: Effect + durable commit
    IN_PROGRESS --> RETRYABLE: Transient error / recovery
    RETRYABLE --> IN_PROGRESS: Safe retry with ownership
    IN_PROGRESS --> UNKNOWN: Timeout after external call
    UNKNOWN --> COMPLETED: Reconciled positive
    UNKNOWN --> RETRYABLE: Reconciled negative
    IN_PROGRESS --> FAILED_TERMINAL: Permanent failure
    COMPLETED --> COMPLETED: Duplicate / replay result
    FAILED_TERMINAL --> FAILED_TERMINAL: Duplicate per policy
~~~

### 7.1. Giữ completion marker bao lâu?

Nếu delete marker quá sớm, một message cũ được replay có thể trở thành **NEW** và chạy lại. TTL phải bao trùm **thời gian retry/redelivery tối đa, DLQ replay window, batch re-import, retention của source và business obligations**. Với thanh toán hoặc lệnh tạo tài nguyên, có thể cần lưu key/receipt dài hơn TTL của cache.

### 7.2. Claim bị kẹt

Worker đã claim rồi crash trước completion → `IN_PROGRESS` tồn tại mãi nếu không có recovery. Cần **lease/timeout có điều kiện**, owner token/version và cơ chế kiểm tra business effect trước khi cho phép retry. Không xem một marker cũ là “chắc chắn chưa commit”: nếu đã gọi hệ thống ngoài, trạng thái có thể là `UNKNOWN`.

### 7.3. Mark trước/mark sau

| Thời điểm đánh dấu | Nguy cơ |
|---|---|
| **Mark completed trước side effect** | Crash khiến retry bị bỏ qua dù chưa xử lý |
| **Side effect trước mark completed** | Crash khiến retry tạo lại side effect |
| **Marker và side effect trong cùng DB transaction** | Có thể giải quyết cho thay đổi cùng database, nhưng không bao trùm external API |
| **Remote idempotency key + reconciliation** | Giảm duplicate external effect, cần remote hỗ trợ đúng contract |

## 8. Spring Integration hỗ trợ Idempotent Receiver như thế nào?

Spring Integration có các thành phần hỗ trợ **Idempotent Receiver pattern**, điển hình:

- **`IdempotentReceiverInterceptor`:** advice quanh một message endpoint/handler để phát hiện duplicate theo selector.
- **`MetadataStoreSelector`:** đánh giá key và lưu/so sánh metadata để quyết định message đã xuất hiện hay chưa.
- **`MetadataStore`/`ConcurrentMetadataStore`:** lưu key/value; lựa chọn implementation quyết định tính bền vững và atomicity.
- Các cấu hình **endpoint advice** hoặc annotation tương thích theo phiên bản.

**Các lớp và DSL API cụ thể cần được kiểm tra theo Spring Integration version đang dùng.** Pattern có thể dùng theo cách đơn giản cho duplicate tracking trong một flow; khi side effect có yêu cầu nhất quán cao, vẫn phải kiểm tra chuyện **marker, transaction, ACK và remote outcome**.

### 8.1. Điểm gắn interceptor quyết định phạm vi

~~~text
Inbound -> deserialize -> validate -> [IDEMPOTENT RECEIVER] -> business handler -> outbound
~~~

Nếu gắn advice:

- **Quá sớm**, trước khi có key đáng tin hoặc payload chuẩn hóa, có thể dedup nhầm.
- **Quá muộn**, sau một side effect đã xảy ra, sẽ không ngăn duplicate ở bước trước.
- **Trên channel không đúng**, message có thể đi đường khác hoặc bị split trước khi dedup.
- **Trên một handler trong pub/sub**, chỉ nhánh đó được bảo vệ, không phải mọi subscriber.
- **Trên từng item sau splitter**, key phải chỉ rõ item identity chứ không phải chỉ batch ID.

### 8.2. Duplicate flag khác “drop”

Tùy cấu hình/phiên bản, advice có thể **đánh dấu header duplicate** (thường liên quan tới `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE`), gửi tới discard channel, chặn handler hoặc có behavior khác. **Không được giả định** rằng thêm interceptor mặc định đã loại bỏ mọi duplicate hoặc tự rollback marker khi handler lỗi. Kiểm tra đúng API và hành vi của version, sau đó viết integration test.

### 8.3. Cần key generator có hợp đồng

Đừng để selector lấy raw `MessageHeaders.ID` nếu logic cần dedup một business event được giao lại dưới Spring Message ID khác. Selector nên được cung cấp **event ID + scope + operation**, validate và chuẩn hóa trước khi kiểm tra.

## 9. MetadataStore: lưu gì, ở đâu và có sống sót sau restart?

| Lựa chọn | Phạm vi | Thích hợp | Rủi ro |
|---|---|---|---|
| **In-memory metadata store** | Một JVM/process | Demo/test hoặc cache ngắn không quan trọng | Mất state sau restart, không chia sẻ giữa replicas |
| **Persistent shared store (JDBC/Redis phù hợp)** | Nhiều instances | Dedup cần giữ qua restart/scale-out | Cần atomic operations, migration, TTL và HA |
| **Business database unique constraint** | Transaction cùng domain state | Cần bảo đảm effect một lần trong cùng DB | Không bao trùm external side effect trực tiếp |
| **Remote target idempotency** | Phía dịch vụ đích | Outbound HTTP/payment/create resource | Tùy TTL, scope và semantics nhà cung cấp |
| **Object/file metadata store** | Nguồn File/SFTP | Theo dõi file đã poll/accept | Không tương đương hoàn tất nghiệp vụ downstream |

### 9.1. ConcurrentMetadataStore là abstraction, không phải magic

Việc interface có `putIfAbsent` hoặc `replace` không có nghĩa mọi backend đều:

- Chia sẻ state giữa replicas theo cấu hình hiện tại.
- Bền vững qua crash, failover hoặc TTL.
- Có transaction nguyên tử với business table.
- Bảo đảm việc đánh dấu duplicate đúng sau remote API timeout.

Phải đánh giá implementation cụ thể, consistency model, network failure, capacity và data recovery.

### 9.2. Trạng thái metadata trong demo và production

Một demo có thể dùng `SimpleMetadataStore` để thấy interceptor nhận diện duplicate **trong cùng JVM**. Nhưng bài toán production nhiều replicas và crash recovery thường cần **shared durable store** hoặc dedup transaction tại business database.

### 9.3. Không nhầm AcceptOnceFileListFilter với business idempotence

File/SFTP inbound có thể dùng accept-once filter và metadata store để tránh lấy lại một file đã thấy. Nó chỉ bảo vệ **bước phát hiện/nhận file**, không bảo đảm transformer, database hoặc outbound HTTP đã **hoàn tất nghiệp vụ**. Một file được đánh dấu “đã thấy” nhưng handler lỗi có thể cần retry có kiểm soát.

## 10. Cấu hình interceptor: sơ đồ thiết kế (version-aware)

Pseudocode dưới đây trình bày **ý định tích hợp**, không phải đoạn cấu hình Java được xác nhận compile cho mọi Spring Integration release:

~~~text
sharedStore = durable_concurrent_metadata_store()
selector = MetadataStoreSelector(
    key = message -> canonical(
        tenantRef, operationType, trustedBusinessEventId),
    store = sharedStore)

advice = IdempotentReceiverInterceptor(selector)

integrationFlow:
    inboundMessage
      -> validateIdentityAndSchema
      -> handler(with advice, id="receiveOrder")
      -> downstreamSideEffects

onDuplicate:
    if completed: skip effect, ACK or return prior result
    if inProgress/unknown: retry later or reconcile
~~~

Trong project thực:

1. Kiểm tra package/class/constructor/DSL `advice` của **version đang dùng**.
2. Xác minh interceptor hoạt động ở **đúng endpoint**.
3. Đọc tài liệu/test về duplicate flag và discard behavior.
4. Kiểm tra thời điểm key được ghi so với handler success/exception.
5. Chọn store có tính durable/concurrent tương ứng yêu cầu.
6. Tách duplicate detection khỏi **completion semantics** cho external side effects.
7. Test restart, handler throw, hai consumers song song, broker redelivery và đổi key.

Nếu không thể bảo đảm store và side effect nguyên tử, hãy cân nhắc **DB unique constraint/inbox/outbox** như các mục tiếp theo.

## 11. Cách đơn giản mà mạnh: unique constraint và business effect trong một transaction

Đối với thay đổi **cùng một database**, có thể đặt một bảng **processed events** với khóa duy nhất và thực hiện business update **trong cùng DB transaction**.

### 11.1. SQL ví dụ cho PostgreSQL

~~~sql
CREATE TABLE processed_event (
    tenant_ref   varchar(80)  NOT NULL,
    operation    varchar(80)  NOT NULL,
    event_id     varchar(160) NOT NULL,
    processed_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_ref, operation, event_id)
);

CREATE TABLE inventory_projection (
    tenant_ref varchar(80)  NOT NULL,
    sku_ref    varchar(160) NOT NULL,
    quantity   bigint       NOT NULL,
    PRIMARY KEY (tenant_ref, sku_ref)
);
~~~

**Chỉ là schema minh họa.** Bảng `processed_event` xác định scope `tenant + operation + eventId`. Nếu source event ID không đủ ổn định hoặc key có thể tái sử dụng cho payload khác, cần thêm request fingerprint/semantic version và kiểm tra conflict.

### 11.2. Receiver service với Spring JDBC

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record InventoryEvent(
        String tenantRef,
        String eventId,
        String skuRef,
        long quantityDelta) {}

enum ApplyResult { APPLIED, ALREADY_APPLIED }

@Service
public class InventoryEventReceiver {
    private final JdbcTemplate jdbc;

    public InventoryEventReceiver(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult applyOnce(InventoryEvent event) {
        // Validate trusted IDs/schema/tenant ownership before this step.
        int claimed = jdbc.update(
            """
            INSERT INTO processed_event(tenant_ref, operation, event_id)
            VALUES (?, 'INVENTORY_ADJUST', ?)
            ON CONFLICT DO NOTHING
            """,
            event.tenantRef(), event.eventId());

        if (claimed == 0) {
            return ApplyResult.ALREADY_APPLIED;
        }

        int updated = jdbc.update(
            """
            UPDATE inventory_projection
               SET quantity = quantity + ?
             WHERE tenant_ref = ? AND sku_ref = ?
            """,
            event.quantityDelta(),
            event.tenantRef(),
            event.skuRef());

        if (updated != 1) {
            throw new IllegalStateException("INVENTORY_ROW_NOT_FOUND");
        }
        return ApplyResult.APPLIED;
    }
}
~~~

### 11.3. Giải thích tính đúng đắn và giới hạn

- `@Transactional` phải thực sự hoạt động qua Spring proxy/transaction manager phù hợp.
- Việc **insert marker + update business row** trong **cùng PostgreSQL transaction** giúp rollback cả hai nếu update thất bại.
- Unique constraint tạo rào chắn trước hai consumers đồng thời với cùng key.
- Nếu transaction đầu rollback, transaction sau có thể claim lại và xử lý.
- Nếu commit xong nhưng broker ACK thất bại, redelivery sẽ thấy key đã có và bỏ qua update trùng.
- Ví dụ này không kiểm tra payload fingerprint; production cần xử lý **same key, different command**.
- Ví dụ chỉ bảo vệ **một DB side effect**. Nếu thêm HTTP call/Kafka publish ngay trong transaction, atomicity không tự mở rộng sang remote.
- Input phải được validate (tenant, ID, quantity, domain rules); duplicate detection không thay authentication/authorization.
- `UPDATE ... quantity + delta` là hành động **không idempotent tự thân**, chính unique marker trong transaction mới chặn thực thi lần hai.

### 11.4. Handler Spring Integration gọi service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class InventoryInboundFlow {
    @Bean
    IntegrationFlow inventoryEvents(InventoryEventReceiver receiver) {
        return IntegrationFlow.from("inventoryEventsInput")
                .handle(message -> {
                    InventoryEvent event =
                            (InventoryEvent) message.getPayload();
                    receiver.applyOnce(event);
                }, endpoint -> endpoint.id("applyInventoryOnce"))
                .get();
    }
}
~~~

Đây là flow **one-way** minh họa, không có adapter/broker cụ thể. Khi nhận từ Kafka/JMS/AMQP, cần cấu hình ACK/transaction/error handling phù hợp: service trả `ALREADY_APPLIED` vẫn có thể là **thành công an toàn** cho một delivery trùng đã completed.

## 12. Khi nghiệp vụ gọi hệ thống ngoài: không có transaction nguyên tử miễn phí

Giả sử receiver ghi `processed_event` vào DB rồi gửi HTTP tới hệ thanh toán. Bốn kịch bản:

| Điểm crash | DB marker | Remote payment | Hậu quả nếu retry thiếu thiết kế |
|---|---|---|---|
| Trước commit marker | Chưa có | Chưa có | Có thể xử lý lại |
| Sau commit marker, trước HTTP call | Đã có | Chưa có | Duplicate bị bỏ qua, **mất side effect** |
| Sau remote commit, trước marker | Chưa có | Đã có | Retry có thể **gửi trùng** |
| Sau marker và remote effect, trước ACK broker | Đã có | Đã có | Redelivery phải skip safely |

**Không thể sửa cả bốn kịch bản bằng một bảng `processed_event` đơn lẻ** nếu remote không tham gia transaction chung.

### 12.1. Phương án thiết kế

- **Remote idempotency key:** lệnh lặp tới target được dedup bởi chính target và có response/reconciliation.
- **Transactional Outbox:** trong một DB transaction, commit domain change và **intent to publish/call**; worker khác gửi từ outbox với retry an toàn.
- **Inbox + Outbox:** consumer ghi nhận input, áp business state và tạo outbound intent trong một transaction.
- **Saga/compensation:** khi nhiều service có side effects độc lập, cần trạng thái bước và cơ chế bù.
- **Reconciliation:** timeout có kết quả chưa rõ phải query trạng thái target trước khi lặp tác vụ nguy hiểm.

### 12.2. “Exactly once” phải có phạm vi

Kafka transactions có thể hỗ trợ một số luồng consume–process–produce nằm trong broker; khi có **database bên ngoài, HTTP payment API, email/SFTP/file system**, các side effects không tự tham gia giao dịch Kafka. Cần xác nhận semantics từng hệ trước khi đưa ra cam kết “exactly once”.

## 13. Inbox + Transactional Outbox: ghép bền vững inbound và outbound

~~~mermaid
flowchart LR
    BROKER[JMS / AMQP / Kafka / HTTP ingress] --> IN[Inbox Receiver]
    IN --> TX[One Local DB Transaction]
    TX --> DEDUP[Unique Inbox Key]
    TX --> DOMAIN[Business State]
    TX --> OUTBOX[Outbound Intent / Outbox Row]
    OUTBOX --> DISPATCH[Outbox Dispatcher + Retry]
    DISPATCH --> TARGET[HTTP / Broker / SFTP]
    TARGET --> CONFIRM[ACK / Receipt / Reconciliation]
    CONFIRM --> STATUS[Outbox Outcome]
~~~

### 13.1. Luồng xử lý

1. Inbound có **event key** hợp lệ và payload đã xác minh.
2. Trong **một local DB transaction**, insert unique inbox marker, update domain state và ghi row outbox (có `outbound_command_id`).
3. Nếu transaction rollback, không có marker/domain/outbox nào được commit.
4. Nếu commit thành công nhưng ACK inbound thất bại, delivery lặp nhìn thấy inbox key và không cập nhật domain lần nữa.
5. Outbox dispatcher gửi command, có thể retry và cần **idempotency ở target** hoặc readback.
6. Xác nhận target rồi cập nhật outbox status; nếu timeout, đánh dấu `UNKNOWN` và reconcile.

### 13.2. Vì sao outbox vẫn có duplicate sends?

Dispatcher có thể gửi xong rồi crash trước khi đánh dấu outbox `SENT`. Sau restart, nó gửi lại. Outbox giải quyết **không mất ý định gửi**, không bảo đảm target thực hiện đúng một lần nếu target không có idempotency/reconciliation. Định danh outbound command phải ổn định giữa các attempts.

### 13.3. Cẩn thận với trạng thái `COMPLETED`

Một inbox event `COMPLETED` có thể chỉ nghĩa là **đã commit domain state và outbox intent**. Nếu nghiệp vụ yêu cầu “đối tác đã xử lý”, cần một trạng thái hoàn tất ở **outbox/remote outcome** riêng. Đừng dùng một cờ duy nhất cho cả hai định nghĩa.

## 14. File inbound/outbound: identity của file không phải identity của nghiệp vụ

### 14.1. Một file có thể xuất hiện lại

File scanner/poller có thể thấy lại file sau restart, metadata store mất state, rename/copy hoặc file được upload lại. Nếu chỉ dùng tên file, một tài liệu mới cùng tên có thể bị bỏ qua; nếu dùng full content hash, cùng nội dung nhưng **hai nghiệp vụ độc lập** có thể bị gộp nhầm.

### 14.2. Gợi ý các key và scope

| Đơn vị | Key khả dĩ | Cảnh báo |
|---|---|---|
| Một file drop đã được định danh | Producer file ID/manifest ID | Cần hợp đồng source bảo đảm uniqueness |
| Một file version cụ thể | Source ID + stable version/generation | Không dùng lastModified một mình |
| Một record trong file | Batch ID + record ID/sequence | Sequence chỉ có nghĩa trong batch |
| Một business command trong file | Stable business event ID | Tốt nếu source thực sự bảo đảm |
| Một lần poll | Poll ref | Chỉ để observability, **không** làm idempotency key |

### 14.3. Accept-once và business receiver

Sự kết hợp có ích:

1. **File accept-once filter** tránh poll lại các file đã nhận.
2. **Idempotent receiver** đảm bảo một record hoặc command đã commit không chạy lại khi file được xử lý lại.
3. **Transaction/Outbox** giữ kết quả domain và ý định gửi downstream.
4. **Checkpoint và retry** bảo vệ khi đọc stream, parsing hoặc upload thất bại.

Không đánh dấu file “business completed” chỉ vì inbound adapter tạo message thành công. Nếu file chứa 10.000 records, theo dõi completion theo **record/batch** phù hợp.

## 15. SFTP: metadata store, file transfer và duplicate delivery

SFTP inbound thường có remote directory listing, filter, transfer xuống local và flow xử lý sau tải về. Các thất bại đáng chú ý:

- Connection timeout khiến file chỉ tải một phần.
- Đã tải file nhưng chưa cập nhật remote metadata store.
- Remote filename tái sử dụng cho nội dung mới.
- Hai replicas cùng poll một remote file khi không có lock/filter dùng chung.
- Source retry một upload khiến cùng business event xuất hiện hai lần.

### 15.1. Thiết kế an toàn

1. Có **remote file identity** theo hợp đồng nguồn; không dựa riêng filename.
2. Dùng persistent/shared metadata store hoặc distributed coordination phù hợp khi nhiều replicas.
3. Tránh xử lý file chưa upload hoàn tất; dùng manifest/rename/ready marker theo nguồn.
4. Tách **download completed** khỏi **business processing completed**.
5. Với file chứa nhiều records, dedup ở cấp record/business command nếu cần.
6. Khi SFTP outbound, cân nhắc atomic handoff/rename và duplicate remote writes.
7. Với timeout, kiểm tra trạng thái remote trước retry; không coi `send()` là đã commit.

### 15.2. Đừng xử lý duplicate bằng cách xóa file nguồn ngay

Xóa file SFTP ngoài quyền hoặc khi handler chưa hoàn tất có thể làm mất khả năng retry/audit. Chỉ archive/move/delete theo **source contract, retention và xác nhận hoàn tất**, không phải như một cách tránh duplicate đơn giản.

## 16. HTTP inbound gateway: Idempotency-Key và response replay

Client HTTP có thể retry `POST /payments` hoặc `POST /orders` sau network timeout. Để hành vi an toàn, API có thể hỗ trợ **`Idempotency-Key`** do caller cung cấp theo hợp đồng.

### 16.1. Quy trình server

1. Authenticate client, xác định tenant/consumer scope.
2. Validate key: length/charset/entropy và scope; không coi key như credential.
3. Canonicalize phần payload cần so sánh; tính fingerprint có bảo vệ.
4. Atomic claim theo `tenant + operation + key`.
5. Nếu **new**, xử lý và lưu **response/receipt** tương ứng với kết quả commit.
6. Nếu **completed duplicate + same fingerprint**, replay prior response hoặc cung cấp resource status theo contract.
7. Nếu **same key + different fingerprint**, trả lỗi conflict và không thực thi command khác.
8. Nếu **in progress**, áp chính sách wait/`202`/`409`/retry-later.
9. Nếu **unknown outcome**, reconcile; không tạo payment mới một cách mù quáng.

### 16.2. Bảng trạng thái mẫu

| Key state | Payload | Response gợi ý | Ý nghĩa |
|---|---|---|---|
| Absent | Hợp lệ | Xử lý theo workflow | Claim mới |
| Completed | Same fingerprint | Prior status/body hoặc resource reference | Không lặp side effect |
| Completed | Different fingerprint | Conflict, thường `409` | Không dùng lại key cho lệnh khác |
| In progress | Same fingerprint | `202`/`409`/retry-later theo contract | Không chạy song song |
| Unknown | Same fingerprint | Status pending + reconciliation | Không đoán đã thất bại |

Không có mã HTTP bắt buộc cho mọi API; quan trọng là contract **được công bố và nhất quán**. Với response chứa PII/secret, prior response store cần ACL, encryption và retention phù hợp.

## 17. HTTP outbound gateway: receiver thực sự nằm ở đâu?

Khi Spring Integration gọi **remote HTTP API**, thành phần idempotent thực sự có thể nằm tại **remote service**. Client cần giữ **cùng remote idempotency key** cho các attempts của cùng command.

~~~text
Spring Integration Receiver (local) -- OUTBOUND_ATTEMPT #1 --> Remote API
                                              |
                                              +-- timeout, result UNKNOWN
                 retry with SAME remote key --> Remote API
                                              |
                                              +-- returns previous result safely
~~~

Nếu remote không hỗ trợ idempotency key, phải cân nhắc **readback/status API, local outbox, reconciliation, business dedup ở target hoặc bù nghiệp vụ**. Một interceptor local không thể đảm bảo external API chỉ thực hiện một lần khi timeout sau remote commit.

### 17.1. Không nhầm HTTP GET với POST

HTTP methods có semantics riêng theo giao thức; GET/PUT thường được thiết kế idempotent ở mức resource intent, còn POST tạo resource thường cần idempotency contract khi retry. **Đừng suy rằng mọi endpoint GET/PUT đều không có side effect** hoặc mọi POST đều không thể an toàn; phải kiểm tra API contract và implementation.

## 18. JMS: redelivery và transactional receive

Trong JMS, consumer có thể gặp lại message do rollback, process crash hoặc ACK không hoàn tất. `JMSRedelivered`, `JMSMessageID` và `JMSCorrelationID` có thể giúp quan sát nhưng có giới hạn:

- `JMSRedelivered` là tín hiệu vận chuyển, không phải quyết định idempotent cuối cùng.
- `JMSMessageID` giúp định danh broker message, không chắc ổn định nếu producer publish lại cùng business event dưới message mới.
- `JMSCorrelationID` phục vụ request/reply hoặc app mapping, không mặc nhiên là event ID duy nhất.
- Handler logic vẫn phải có **business idempotency key** phù hợp nếu cùng command có thể đến dưới các JMS messages khác nhau.

### 18.1. Mô hình nhận và commit

1. Consumer nhận message, parse và validate event identity.
2. Idempotent receiver kiểm tra key qua store/DB.
3. Nếu marker và business change nằm trong **cùng DB transaction**, commit hoặc rollback đúng ranh giới.
4. ACK JMS theo cấu hình session/transaction **sau khi đã đảm bảo state cần thiết bền vững**.
5. Nếu broker redeliver do ACK thất bại, key đã committed nên receiver skip effect và hoàn tất ACK an toàn.

**Cảnh báo:** JMS transaction và database transaction không tự là một transaction chung. Nếu cần coordination nâng cao, thiết kế transaction/outbox/idempotency cụ thể; không giả định một `@Transactional` trên Java service tự bao trùm JMS ACK.

## 19. AMQP/RabbitMQ: ACK, NACK và poison messages

AMQP consumer có thể nhận lại message do NACK/requeue, connection drop hoặc consumer restart. Receiver phải:

- Tách **delivery attempt** khỏi **logical event**.
- Dùng key từ hợp đồng producer đã kiểm tra thay vì chỉ delivery tag.
- Commit side effect/dedup state trước khi ACK theo semantics đã thiết kế.
- Khi gặp **completed duplicate**, ACK an toàn; không tăng số business completions.
- Với lỗi transient, áp bounded retry/backoff và DLQ.
- Với poison message, tránh vòng lặp requeue vô hạn.
- Với timeout external API, giữ `UNKNOWN` và reconcile trước khi replay.

### 19.1. Publisher confirm không phải consumer completion

AMQP producer có thể nhận publish confirm trong khi consumer chưa xử lý. Đừng dùng một log `publisher_confirmed` để đánh dấu event đã được business receiver xử lý. Với outbound, target receiver cũng cần idempotency nếu broker giao nhiều lần.

## 20. Kafka: offset, event ID và idempotent receiver

Kafka thường được xử lý theo mô hình có thể **giao lại record** khi offset chưa commit, rebalance hoặc retry. Receiver có thể chọn scope:

1. **Per physical record:** dedup theo `topic + partition + offset`.
2. **Per logical event:** dedup theo `producer/event ID + operation/tenant`, ngay cả khi producer publish cùng event lên hai offsets.
3. **Per business command:** dedup theo ID của lệnh nghiệp vụ, kể cả đi qua nhiều topics/bridges.

Chọn scope theo yêu cầu. Với nghiệp vụ thanh toán/điều chỉnh số dư, **business-level key** thường có giá trị hơn record offset.

### 20.1. Các lần xử lý lại

| Tình huống | Key theo offset | Key theo business event |
|---|---|---|
| Same Kafka record redelivered | Nhận ra | Nhận ra |
| Producer publish lại same event ở offset mới | **Không** nhận ra | Nhận ra nếu event ID ổn định |
| Hai business events hợp lệ có payload giống | Coi khác nếu offset khác | Coi khác nếu event ID khác |
| Replay từ retry topic | Offset khác | Có thể nhận ra theo logical event key |
| Cần xử lý lại bằng command mới | Offset mới | Cần operation/event version mới theo policy |

### 20.2. Commit offset sau side effect

Nếu handler hoàn tất DB transaction nhưng process chết trước commit Kafka offset, record có thể được giao lại. Unique marker ở DB khiến lần sau không áp cùng side effect; sau đó consumer có thể commit offset an toàn theo cấu hình.

### 20.3. Kafka transactions không giải quyết mọi external effects

Kafka producer idempotence/transactions có các guarantee trong phạm vi Kafka. Một handler cập nhật **database hoặc gọi HTTP** vẫn có transaction boundary khác. Không tuyên bố end-to-end exactly-once nếu chưa xử lý cross-system side effects, retries và failure modes.

## 21. JDBC inbound poller: một row có thể được SELECT nhiều lần

Một luồng database polling thường dùng câu query lấy các rows có trạng thái `PENDING`, tạo message, xử lý rồi đánh dấu `PROCESSED`. Nếu process chết sau khi gửi HTTP nhưng trước khi update trạng thái, lần poll sau sẽ lấy lại row.

### 21.1. Những mốc không giống nhau

| Mốc | Ý nghĩa | Có phải đã xử lý xong? |
|---|---|---|
| `ROW_SELECTED` | Poller tìm thấy row | Chưa |
| `MESSAGE_EMITTED` | JDBC adapter tạo Spring Message | Chưa |
| `CLAIMED` | Có worker được quyền xử lý | Chưa |
| `BUSINESS_COMMITTED` | Thay đổi DB đã commit | Có, **đối với local DB effect** |
| `OUTBOUND_SENT` | Có outbound attempt | Chưa chắc remote commit |
| `OUTBOUND_CONFIRMED` | Remote xác nhận theo contract | Có ở scope được xác nhận |
| `SOURCE_MARKED_PROCESSED` | Source row/watermark đã cập nhật | Chỉ nói về checkpoint |

### 21.2. Thiết kế lựa chọn

- **Một DB duy nhất:** có thể cập nhật business state, marker và nguồn row trong cùng transaction nếu điều kiện phù hợp.
- **DB nguồn và DB nghiệp vụ khác nhau:** không có atomic transaction mặc định; cân nhắc inbox/dedup tại consumer, outbox và reconciliation.
- **DB poll → HTTP API:** dùng remote idempotency key ổn định, sau timeout phải readback.
- **Batch query:** đừng dùng `poll timestamp` làm key cho tất cả rows trong batch.
- **Concurrent pollers:** cần row claim/lease, locking strategy, immutable event ID, và tránh worker đọc cùng row rồi cùng gọi remote.

### 21.3. Watermark không thay idempotency

Watermark như `last_processed_id` hoặc `updated_at` giúp biết lần tiếp theo nên đọc từ đâu. Nhưng khi transaction rollback, source thay đổi thứ tự, timestamp trùng hoặc event đến muộn, watermark có thể bỏ sót hoặc chọn lại. **Idempotency key và marker ở receiver** bảo vệ duplicate; watermark chỉ là một phần thuật toán polling.

## 22. Splitter, Aggregator và batch replay

Khi splitter biến một batch thành nhiều messages, dùng key **chỉ theo batch ID** ở mỗi item handler sẽ chặn nhầm các item hợp lệ thứ hai, thứ ba… Ngược lại, dùng mỗi `sequenceNumber` không có batch scope sẽ va chạm giữa các batches.

### 22.1. Quy tắc tạo key cho children

~~~text
parentKey = source + ":" + batchId
itemKey   = source + ":" + batchId + ":" + stableItemId
operation = "VALIDATE_AND_APPLY"

idempotencyKey = tenantRef + ":" + operation + ":" + itemKey
~~~

`stableItemId` phải được nguồn xác định, hoặc dựa trên chỉ số vị trí **khi batch được định nghĩa bất biến**. Nếu batch thay đổi thứ tự/thành phần giữa các lần tải, sequence index có thể không còn biểu diễn cùng logical item.

### 22.2. Aggregator và partial failure

Một số item có thể đã được xử lý nhưng aggregator timeout trước khi nhận đủ. Khi batch được replay:

1. Các item đã commit → skip side effect ở mức item.
2. Các item chưa commit → được phép xử lý.
3. Aggregator phải biết **completion/expiry semantics** và không ghép lại sai group.
4. Kết quả aggregate phải có **group/version key**, tránh publish trùng khi aggregation result được tạo lại.

**Không** mặc định một history/header của aggregate result chứa bằng chứng tất cả item đã hoàn tất. Cần item-level completion ledger hoặc event statuses theo contract.

### 22.3. Publish-subscribe

Nếu một message được gửi qua `PublishSubscribeChannel` tới ba subscribers, mỗi nhánh có một side effect khác. Có thể cần key **business event + subscriber/operation**, chẳng hạn:

~~~text
tenant:t1:event:e100:op:update-ledger
tenant:t1:event:e100:op:send-email
tenant:t1:event:e100:op:notify-warehouse
~~~

Nếu chỉ dùng `event:e100` toàn cục, nhánh đầu tiên mark completed sẽ vô tình khiến các nhánh còn lại bị xem là duplicate. **Scope của key phải phản ánh tác dụng phụ cần bảo vệ**.

## 23. Retry và backoff: duplicate an toàn không có nghĩa retry vô hạn

Retry xảy ra khi network/broker/database tạm lỗi. Idempotency làm retry an toàn hơn nhưng không loại bỏ nhu cầu **bounded retry, exponential backoff, jitter, circuit breaker hoặc DLQ**.

### 23.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| **Transient** | Rate limit, 503, network reset trước khi request đi | Retry có backoff/budget |
| **Permanent** | Schema không hợp lệ, thiếu quyền thực sự | Reject/DLQ, không retry y nguyên vô hạn |
| **Unknown outcome** | Timeout sau khi remote có thể commit | Reconcile/readback, giữ idempotency key |
| **In-progress conflict** | Worker khác đang claim cùng key | Wait/retry later, không tạo side effect song song |
| **Same key different payload** | Request key bị tái sử dụng sai | Conflict, điều tra |
| **Store unavailable** | Không thể check dedup state | Fail-closed hoặc defer theo rủi ro; không bypass mù |

### 23.2. Điểm nguy hiểm: retry do mất ACK

Một handler đã hoàn tất DB effect, nhưng broker ACK/offset commit thất bại. Khi redelivery, **trả kết quả “duplicate completed” không phải processing failure**. Cần cho phép transport ACK/cursor tiến lên, nếu không message sẽ lặp mãi dù marker đã tồn tại.

### 23.3. Error channel và duplicate state

Spring Integration có các luồng error handling tùy endpoint, transaction và poller. Khi handler ném exception:

- Xem marker được ghi **trước hay sau** handler.
- Nếu marker nằm trong transaction đã rollback, retry có thể claim lại.
- Nếu selector/store mark độc lập trước handler, marker có thể vẫn còn dù effect thất bại; phải có chính sách recovery.
- Không đặt `COMPLETED` chỉ vì exception đã được gửi vào `errorChannel`.
- Với `ErrorMessage`, lưu correlation và reason code an toàn, không in raw failed payload.

## 24. Replay từ DLQ và reprocessing có chủ đích

Một thông điệp ở DLQ có thể được xử lý lại sau khi sửa lỗi code/schema. Thời gian replay có thể vượt xa TTL của cache chống trùng.

### 24.1. Hai trường hợp cần phân biệt

**Trường hợp A — Replay để đảm bảo hoàn tất cùng operation:** giữ nguyên business idempotency key. Nếu đã completed, skip; nếu chưa, xử lý theo policy.

**Trường hợp B — Một nghiệp vụ mới phát sinh từ dữ liệu cũ:** phải tạo **operation/version/event ID mới có chủ đích**, không “xóa dedup marker” để ép chạy lại.

Ví dụ, tính lại báo cáo tháng này có thể là một lệnh mới `RECOMPUTE_REPORT:v2`, trong khi phát lại `PAY_INVOICE:event-77` không được tạo một khoản thanh toán thứ hai.

### 24.2. Quy trình replay an toàn

1. Xác nhận nguồn, event identity, trạng thái trước đó và lý do DLQ.
2. Xem marker `COMPLETED/FAILED/UNKNOWN` và side effect ở target.
3. Quyết định **resume same operation** hay **new compensating operation**.
4. Giữ source event ID và bổ sung `replay_ref`/`attempt_ref` mới cho observability.
5. Không bypass idempotency để “cho chạy qua” khi chưa hiểu trạng thái.
6. Dùng owner/approval và giới hạn batch replay nếu ảnh hưởng tài chính hoặc dữ liệu nhạy cảm.
7. Theo dõi completed, skipped, conflicts, failures và reconciliation results.

### 24.3. Không xóa marker chỉ vì muốn thử lại

Xóa marker `COMPLETED` làm mất khả năng phân biệt sự kiện đã xử lý. Nếu business muốn sửa kết quả, dùng **compensation/correction event** có ID và audit riêng, thay vì tái thực thi nguyên command không kiểm soát.

## 25. TTL, retention và garbage collection của dedup store

### 25.1. TTL tối thiểu phụ thuộc cả hệ thống

Các yếu tố ảnh hưởng:

- Client HTTP retry window và thời hạn sử dụng Idempotency-Key.
- Broker retention/redelivery/DLQ replay horizon.
- Khả năng file SFTP được upload lại sau nhiều ngày.
- Database polling/reconciliation và batch schedule.
- Compliance, audit và khoảng thời gian business transaction cần chống trùng.
- Số lượng keys, chi phí lưu trữ, quyền riêng tư và yêu cầu xóa dữ liệu.

Không có một TTL đúng cho mọi nghiệp vụ. Với một số operation, có thể giữ **business unique constraint lâu dài** và chỉ dọn transient attempts/leases.

### 25.2. Chia thông tin lưu trữ theo vòng đời

| Dữ liệu | Mục đích | Retention mẫu |
|---|---|---|
| Completed business key | Bảo vệ side effect cũ khi replay | Theo business replay horizon |
| In-progress claim | Tránh xử lý đồng thời | Lease ngắn, kèm owner/fencing |
| Attempt logs | Chẩn đoán retry/latency | Theo logging policy |
| Outbox intent | Đảm bảo gửi tiếp đến target | Tới khi confirmed và qua retention |
| Audit event | Truy vết thay đổi có trách nhiệm | Theo chính sách/luật áp dụng |
| Reconciliation evidence | Phân định unknown outcome | Tới khi hoàn tất điều tra/obligation |

**Không lưu raw payload/PII vào dedup key hoặc logs** chỉ để giữ được history lâu hơn. Dùng opaque ref và store có ACL phù hợp.

### 25.3. Cleanup phải an toàn với concurrent processing

Nếu TTL xóa `IN_PROGRESS` khi worker cũ còn chạy, một worker mới có thể claim cùng key. Dùng conditional update/version/fencing hoặc side effect uniqueness ở đích. Không chỉ xóa mọi record “quá 5 phút” mà không đối soát trạng thái.

## 26. Nhiều JVM, nhiều pod: store phải có tính chia sẻ và consistency phù hợp

~~~mermaid
flowchart TD
    SRC[Shared Broker / Source] --> A[Receiver Pod A]
    SRC --> B[Receiver Pod B]
    SRC --> C[Receiver Pod C]
    A --> S[(Shared Dedup Store)]
    B --> S
    C --> S
    S --> DB[(Business Database)]
    A --> OUT[Outbound Side Effect]
    B --> OUT
    C --> OUT
~~~

### 26.1. Những lỗi thường gặp ở cluster

1. Dùng `SimpleMetadataStore` mỗi pod → cả A/B đều coi message là mới.
2. Redis key hết TTL quá sớm → cùng event được claim lần hai.
3. Chuyển region nhưng metadata store chưa replicate kịp → nhận duplicate.
4. Network partition → client không biết claim đã lưu thành công hay chưa.
5. Worker cũ giữ lease nhưng tiếp tục chạy sau khi lease hết → side effect hai lần.
6. Rolling deployment thay đổi key format → record cũ không còn match.
7. Hai source adapters dùng namespace giống nhau, key collision giữa tenants.
8. Một consumer crash nhưng broker chưa ACK, redelivery sang pod khác.

### 26.2. Cách bảo vệ

- Một **shared durable store** có atomic claim/unique key phù hợp.
- **Key namespace và schema version** ổn định, kế hoạch migration khi thay đổi.
- **Local DB transaction** với unique constraint khi side effect nằm trong DB.
- **Remote idempotency/reconciliation** cho side effects ngoài DB.
- Recovery state `UNKNOWN/IN_PROGRESS` thay vì bỏ qua hoặc retry mù.
- Giám sát collisions, store latency, cleanup, capacity và error rate.

## 27. Thứ tự message, version và xử lý event đến muộn

Idempotency không giải quyết vấn đề **out-of-order delivery**. Hai sự kiện khác nhau `STATUS_CHANGED:version=7` và `STATUS_CHANGED:version=8` đều có key riêng; nếu xử lý version 8 rồi version 7, bản ghi cuối có thể quay lại trạng thái cũ dù mỗi event chỉ được xử lý một lần.

### 27.1. Kết hợp idempotency với version guard

~~~sql
-- Minh họa guard: chỉ cập nhật nếu event version mới hơn.
UPDATE order_projection
   SET status = :new_status,
       source_version = :incoming_version
 WHERE order_id = :order_id
   AND source_version < :incoming_version;
~~~

**Đây là pseudo-SQL có named parameters**, không phải cú pháp JDBC thô. Nếu `UPDATE` trả 0 rows, cần phân biệt **stale event, duplicate version, missing order hay conflict** theo business rules. Không gắn nhãn mọi trường hợp là “duplicate completed”.

### 27.2. Trường hợp cần sequential processing

Với Kafka, key partition có thể giúp giữ thứ tự trong một partition nhưng retry topic, concurrency và process khác vẫn thay đổi quan hệ thực thi. Với JMS/AMQP/file batch, cần ordering/sequence contract riêng nếu nghiệp vụ yêu cầu. **Idempotent receiver + ordering/versioning** giải quyết hai vấn đề khác nhau.

## 28. Idempotent receiver so với các pattern liên quan

| Pattern/cơ chế | Câu hỏi chính | Quan hệ với Idempotent Receiver |
|---|---|---|
| **Idempotent Receiver** | Có nên thực hiện logical operation này một lần nữa? | Chủ đề chính |
| **Idempotent Producer** | Producer retry publish có làm trùng record? | Có thể giảm trùng tại source, không thay receiver |
| **Idempotency-Key HTTP** | Remote API nhận cùng lệnh nhiều lần có an toàn? | Receiver phía HTTP service |
| **Message Filter** | Message có hợp lệ/đúng loại không? | Có thể đặt trước dedup để xác minh identity |
| **Message Store/Metadata Store** | Lưu trạng thái nhận diện ở đâu? | Một cách triển khai |
| **Transactional Inbox** | Ghi nhận inbound và domain effect một cách bền vững ra sao? | Củng cố atomicity |
| **Transactional Outbox** | Không mất outbound intent sau DB commit? | Bổ trợ, vẫn cần idempotent target |
| **Retry/DLQ** | Làm gì khi xử lý lỗi? | Tạo tình huống lặp cần pattern |
| **Resequencer** | Message có đến sai thứ tự? | Không trùng với dedup |
| **Aggregator** | Khi nào đủ messages để kết quả hoàn chỉnh? | Cần per-item và per-result idempotency |
| **Compensating Transaction/Saga** | Làm gì khi side effects phân tán đã xảy ra? | Dùng khi không thể rollback nguyên tử |
| **Exactly-once semantics** | Guarantee trong phạm vi nào? | Không tự có chỉ nhờ interceptor |

## 29. Observability: đo duplicate mà không đếm sai thành công

### 29.1. Event taxonomy gợi ý

~~~text
INGRESS_ACCEPTED
IDEMPOTENCY_KEY_VALIDATED
CLAIM_ATTEMPTED
CLAIM_ACQUIRED
DUPLICATE_COMPLETED_SKIPPED
IN_PROGRESS_CONFLICT
PAYLOAD_KEY_CONFLICT
BUSINESS_EFFECT_COMMITTED
OUTBOUND_INTENT_CREATED
OUTBOUND_ATTEMPTED
REMOTE_OUTCOME_UNKNOWN
REMOTE_CONFIRMED
RECONCILIATION_COMPLETED
REPLAY_STARTED
TERMINAL_FAILURE
~~~

Không log raw payload, secret hay full business ID. Ghi **opaque correlation reference**, operation, key scope category, attempt index, bounded reason code và result.

### 29.2. Những metric hữu ích

| Metric logic | Ý nghĩa | Điều không được suy |
|---|---|---|
| Inbound deliveries | Số lần source giao message | Không phải unique business events |
| Unique keys claimed | Số logical keys mới được nhận | Không chắc đã completed |
| Completed duplicate skips | Số lần giao trùng được bỏ qua | Không phải lỗi nghiệp vụ |
| In-progress conflicts | Số lần nhiều workers tranh cùng key | Không chắc side effect đã trùng |
| Payload-key conflicts | Same key, different operation payload | Có thể là lỗi client hoặc tấn công |
| Business effects committed | Kết quả domain đã bền vững | Scope theo DB/target cụ thể |
| Outbound attempts | Số lần gọi hệ đích | Có retry/redelivery |
| Remote confirmed | Số kết quả transport/remote xác nhận | Không luôn bằng business completion |
| Unknown outcomes | Có khả năng đã thực thi nhưng chưa xác minh | Không được đếm như failed chắc chắn |
| Dedup store latency/errors | Chất lượng primitive atomic | Có thể tạo backlog/incomplete |
| Key retention expirations | Tỷ lệ cleanup | Theo dõi nguy cơ replay ngoài TTL |

**Không dùng idempotency key, event ID, tenant ID động hoặc filename làm metric tag.** Ghi ở structured log có quyền nếu cần, metrics dùng `flow`, `source_type`, `operation`, `outcome` hữu hạn.

### 29.3. SLI ưu tiên unique events

Ví dụ có 100 logical events, 120 deliveries, 110 processing attempts, 97 events completed, 3 pending reconciliation. **Success theo logical event** không phải 110/120. Cần quy định eligible events, thời điểm hoàn tất và treatment cho unknown/pending để tính SLI chính xác.

## 30. Bảo mật và rủi ro bị lạm dụng idempotency key

### 30.1. Key poisoning và cross-tenant collisions

Một caller chưa xác thực có thể cố tình gửi key của người khác để làm server tưởng request của người đó đã được xử lý. Do đó:

- Xác minh authentication và tenant/actor scope **trước khi tra key**.
- Namespace key theo operation và principal/tenant context phù hợp.
- Khi cùng key khác payload, trả conflict; không replay kết quả nhạy cảm của request khác.
- Không tiết lộ tồn tại của resource/response thuộc tenant khác thông qua status code.
- Giới hạn tốc độ và số lượng keys một caller có thể tạo để tránh memory exhaustion.

### 30.2. Không lưu dữ liệu quá mức trong metadata store

Dedup key nên là tham chiếu tối thiểu, không chứa password, OAuth token, số thẻ, email hoặc full file path nhạy cảm. Nếu cần request fingerprint, dùng thuật toán và canonicalization được review, lưu ở hệ có ACL; **hash thường của PII entropy thấp không mặc nhiên vô danh**.

### 30.3. Quyền truy cập và audit

Store và response cache có thể chứa thông tin business sensitive. Cần encryption, access control, rotation credentials, retention và operation audit phù hợp. Không cho phép operator tùy tiện xóa completed keys để “sửa nhanh”; một thay đổi như vậy có thể gây chi trả hoặc phát hành tài nguyên trùng.

## 31. Kịch bản kiểm thử bắt buộc

### 31.1. Bảng test

| Trường hợp | Input/điều kiện | Mong đợi |
|---|---|---|
| **First delivery** | Key mới, payload hợp lệ | Một business effect, marker completed |
| **Identical redelivery** | Cùng key, payload | Effect không chạy lần hai |
| **Concurrent same key** | Hai consumers cùng lúc | Chỉ một claim/effect được commit |
| **Different keys** | Hai events hợp lệ cùng nội dung | Cả hai được xử lý nếu nghiệp vụ cho phép |
| **Same key different payload** | Key tái sử dụng sai | Conflict; không tạo side effect mới |
| **Handler fails before commit** | Exception trong DB transaction | Marker/effect rollback; retry xử lý được |
| **Crash after DB commit before ACK** | Broker redeliver | Bỏ qua effect, ACK an toàn |
| **Crash after outbox send before status** | Dispatcher retry | Remote idempotency/reconciliation ngăn trùng |
| **Store unavailable** | DB/Redis unreachable | Không bypass chặn trùng trái policy |
| **Stale IN_PROGRESS** | Worker chết hoặc lease hết | Recovery có kiểm chứng, tránh concurrent duplicate |
| **TTL expired replay** | Event cũ quay lại | Policy rõ; không tạo side effect bất ngờ |
| **Out-of-order versions** | Version 8 trước 7 | Version guard ngăn rollback state |
| **Batch replay** | 100 items, 90 đã completed | Chỉ 10 item chưa completed chạy |
| **DLQ reprocess** | Replay cùng command | Key giữ nguyên hoặc tạo correction event có chủ đích |
| **Multi-pod** | 3 replicas chung broker | Shared store/unique constraint ngăn double effect |
| **Broker timeout** | Outcome unknown | Reconciliation, không mark chắc chắn failed |
| **Restart** | JVM/Pod restart | Dedup state vẫn tồn tại theo retention |

### 31.2. Unit test hay integration test?

**Unit test** có thể kiểm tra key canonicalization, operation scoping và conflict policy. Nhưng **atomic uniqueness, JDBC transaction rollback, broker ACK/offset, multi-process race và restart** cần integration/failure tests với infrastructure đại diện. Một `ConcurrentHashMap` test trong một JVM không chứng minh an toàn trên cluster.

### 31.3. Test thứ tự apply và marker

Đặc biệt cần phép thử **throw exception giữa insert marker và business update**. Với thiết kế PostgreSQL mục 11, nếu `@Transactional` hoạt động đúng, transaction rollback và retry sau đó có thể insert lại. Nếu marker được ghi bởi metadata store ngoài transaction, kết quả có thể khác; test phải phơi bày điều đó.

## 32. Ví dụ test JUnit cho key canonicalization

Để key ổn định và phân biệt operation, có thể định nghĩa helper đơn giản:

~~~java
import java.util.Objects;
import java.util.regex.Pattern;

public final class EventKeys {
    private static final Pattern PART =
            Pattern.compile("[A-Za-z0-9_-]{1,120}");

    private EventKeys() {}

    public static String key(String tenantRef,
                             String operation,
                             String eventId) {
        validate(tenantRef);
        validate(operation);
        validate(eventId);
        return tenantRef + ":" + operation + ":" + eventId;
    }

    private static void validate(String value) {
        Objects.requireNonNull(value, "key segment");
        if (!PART.matcher(value).matches()) {
            throw new IllegalArgumentException("INVALID_EVENT_KEY");
        }
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EventKeysTest {
    @Test
    void sameEventUsesStableKey() {
        String first = EventKeys.key("tenantA", "CONFIRM", "ev-100");
        String replay = EventKeys.key("tenantA", "CONFIRM", "ev-100");
        assertEquals(first, replay);
    }

    @Test
    void operationsCannotCollide() {
        assertNotEquals(
                EventKeys.key("tenantA", "CONFIRM", "ev-100"),
                EventKeys.key("tenantA", "REFUND", "ev-100"));
    }

    @Test
    void unsafeUserInputIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> EventKeys.key("tenantA", "CONFIRM",
                        "ev-100\nFAKE-LOG"));
    }
}
~~~

**Giới hạn ví dụ:** đây là kiểm tra **định dạng key** chứ chưa kiểm tra nguồn tin cậy, business uniqueness, payload fingerprint hay DB atomicity. `tenantRef` cũng phải được xác thực theo actor/session thực tế; không chỉ regex cho qua là đủ.

## 33. Test hành vi transactional receiver

Một integration test cần chạy database thật hoặc môi trường tương thích PostgreSQL với unique constraint như mục 11.

### 33.1. Kịch bản cơ bản

~~~text
Given:
  inventory_projection(tenantA, sku01, quantity=100)
  processed_event chưa có eventId=ev-77

When:
  receiver.applyOnce(tenantA, ev-77, sku01, delta=-2)
  receiver.applyOnce(tenantA, ev-77, sku01, delta=-2)

Then:
  kết quả lần đầu = APPLIED
  kết quả lần hai = ALREADY_APPLIED
  inventory quantity = 98
  processed_event có đúng 1 row cho (tenantA, INVENTORY_ADJUST, ev-77)
~~~

### 33.2. Kịch bản lỗi

~~~text
Given:
  một event mới có SKU không tồn tại

When:
  receiver.applyOnce(...) ném IllegalStateException

Then:
  transaction rollback
  processed_event KHÔNG có completed marker cho event đó

When:
  tạo SKU hợp lệ rồi retry event

Then:
  receiver apply thành công đúng một lần
~~~

### 33.3. Race condition test

Cho hai worker invoke `applyOnce` đồng thời với cùng key, dùng barrier để tạo tranh chấp. Kiểm tra quantity chỉ thay đổi một lần, cả hai requests không tạo record trùng, transaction behavior của store đúng. Tránh dùng `Thread.sleep` làm phép chứng minh concurrency vì test có thể không thực sự tạo race.

## 34. Runbook IDEMP-01 — Duplicate tăng đột ngột

**Trigger:** `duplicate_skips`, broker redelivery hoặc outbound attempts tăng nhanh trong khi business completion không tăng tương ứng.

1. Xác định flow, source, operation, timeframe và **logical key scope**.
2. Tách **duplicate deliveries** khỏi những **hai events hợp lệ có payload giống nhau**.
3. Xem transport telemetry: Kafka lag/rebalance/offset, JMS rollback, AMQP NACK/requeue, HTTP retries, SFTP repoll.
4. Kiểm tra recent changes ở ACK mode, transaction, retry policy, metadata store và key generator.
5. Kiểm tra dedup store latency/errors/capacity, TTL và trạng thái `IN_PROGRESS` bị kẹt.
6. Đối chiếu **unique business completions** thay vì số handler invocations.
7. Với external API, xem timeout và `UNKNOWN_OUTCOME` trước khi replay.
8. Nếu nhiều nodes, xác minh mọi instance dùng **cùng store/key namespace/schema version**.
9. Xử lý nguyên nhân retry/rebalance/poison message theo runbook từng adapter.
10. Giữ evidence, sửa test coverage và theo dõi trở lại baseline.

### 34.1. Những thao tác không nên làm

- Không xóa hàng loạt completed keys để “thông queue”.
- Không tắt dedup khi store chậm nếu đó là lệnh tài chính/side effect quan trọng.
- Không ACK như success một event chưa biết business result.
- Không tăng retry/concurrency vô hạn khi target đang rate-limit.
- Không in raw payload/keys chứa PII để so sánh duplicate.

## 35. Runbook IDEMP-02 — Claim tồn tại nhưng nghiệp vụ chưa hoàn tất

**Trigger:** message không được xử lý vì key đã `IN_PROGRESS`/`COMPLETED`, nhưng target không có kết quả mong đợi.

1. Đọc trạng thái key, owner/lease/version, timestamp, store consistency và bản ghi business thực tế.
2. Phân biệt **marker đã commit mà effect chưa chạy** với **effect đã chạy nhưng confirmation/log thiếu**.
3. Kiểm tra transaction boundary: marker có nằm cùng DB transaction với business update không?
4. Với remote API, dùng status/readback theo idempotency key hoặc business reference trước retry.
5. Nếu `IN_PROGRESS` bị stale, đánh giá worker cũ còn chạy không; chỉ takeover theo lease/fencing policy.
6. Nếu `COMPLETED` bị ghi quá sớm, mở incident thiết kế và thực hiện remediation được phê duyệt; không xóa marker mù.
7. Cập nhật state `UNKNOWN/RETRYABLE/COMPLETED` dựa trên chứng cứ, giữ audit.
8. Test crash tại đúng checkpoint gây lỗi để đảm bảo không tái diễn.

## 36. Mười hai tình huống thực hành

### Tình huống A — Kafka redelivery sau khi DB commit

Consumer ghi DB xong, crash trước offset commit. Broker giao lại record cùng event ID.

**Hướng xử lý:** dùng unique key và business update trong DB transaction; retry thấy completed, không ghi lại, rồi ACK/commit offset an toàn theo container settings. Đừng coi log handler chạy hai lần là hai business events.

### Tình huống B — Producer publish lại cùng event ở Kafka offset mới

Producer bị timeout và publish bản sao cùng event ID lên offset khác.

**Hướng xử lý:** dedup theo **stable event ID** chứ không chỉ `topic-partition-offset` nếu phạm vi cần một business completion. Đối chiếu producer retries, idempotent producer settings và consumer metrics.

### Tình huống C — JMS consumer rollback sau khi gửi email

Handler gửi email bên ngoài, sau đó DB update ném lỗi và JMS rollback.

**Hướng xử lý:** lần delivery sau có thể gửi email trùng. Tách email thành outbox command với ID ổn định; sender/reconciliation và email provider idempotency nếu hỗ trợ, hoặc chấp nhận/giám sát duplicate theo contract.

### Tình huống D — AMQP poison message lặp mãi

RabbitMQ requeue message sai schema, consumer tiếp tục reject.

**Hướng xử lý:** phân loại lỗi permanent, bounded retries và DLQ; không “cứ thêm idempotency marker” để che payload không hợp lệ. Chỉ mark completed khi nghiệp vụ hoàn tất hoặc có terminal rejection được định nghĩa.

### Tình huống E — SFTP cùng filename nhưng nội dung mới

Đối tác upload lại `report.csv` cho ngày mới, accept-once filter/selector theo tên file coi đó là duplicate.

**Hướng xử lý:** thỏa thuận file generation ID/manifest hoặc version đáng tin; với record cần event ID riêng. Không dựa filename đơn lẻ và không in raw remote path vào log.

### Tình huống F — JDBC poll lại row sau remote timeout

Poller đọc row `PENDING`, gọi HTTP API và timeout; row chưa được đánh dấu processed.

**Hướng xử lý:** trạng thái external effect là `UNKNOWN`, query remote/idempotency status trước khi gọi lại; dùng durable outbox/marker và retry budget.

### Tình huống G — HTTP Idempotency-Key trùng nhưng amount đổi

Hai POST requests cùng key, request thứ hai có amount khác.

**Hướng xử lý:** key scope theo actor/tenant/operation, so fingerprint đã canonicalize. Trả conflict, không replay response nhạy cảm của request khác hoặc tạo charge mới.

### Tình huống H — Hai pods xử lý cùng event

Hai replicas dùng `SimpleMetadataStore` cục bộ và cùng nhận event do failover.

**Hướng xử lý:** dùng shared durable/atomic store hoặc DB unique constraint; kiểm thử concurrency và restart. Không sửa bằng `synchronized` trong từng JVM.

### Tình huống I — Metadata TTL ngắn hơn DLQ replay

Completed key hết hạn sau 1 giờ, DLQ được replay sau 2 ngày.

**Hướng xử lý:** review retention so với replay horizon và business obligations, giữ marker/receipt lâu hơn hoặc kiểm tra business state trước replay. Không chạy lại financial command mù.

### Tình huống J — Splitter chặn 99/100 items

Mọi item dùng cùng `batchId` làm idempotency key.

**Hướng xử lý:** chọn key `batch + stable item ID + operation`; giữ group completion độc lập. Không coi các items khác nhau là duplicate vì chung batch.

### Tình huống K — Event đến sai thứ tự

Version 8 xử lý trước version 7; cả hai key đều mới.

**Hướng xử lý:** thêm version/order guard/expected state CAS; idempotency không ngăn stale event làm rollback business state.

### Tình huống L — Một outbound call đã commit nhưng thiếu ACK

Remote payment đã thành công, receiver mất response và chuẩn bị retry.

**Hướng xử lý:** giữ same remote idempotency key, readback status, ghi `UNKNOWN_OUTCOME` cho tới khi xác minh. Nếu remote không có idempotency, dùng reconciliation/compensation do owner nghiệp vụ duyệt.

## 37. Checklist áp dụng Idempotent Receiver

### 37.1. Thiết kế key

- [ ] Xác định logical operation và side effect cần bảo vệ?
- [ ] Key ổn định xuyên redelivery/retry/restart/process boundary?
- [ ] Key có scope tenant/source/operation để tránh collision?
- [ ] Có policy khi cùng key nhưng payload khác?
- [ ] Không sử dụng raw filename/email/token/PII làm key/log?
- [ ] Có contract cho client-supplied Idempotency-Key và trust validation?

### 37.2. Lưu trữ và atomicity

- [ ] Store có **atomic claim/unique constraint** phù hợp?
- [ ] State được chia sẻ và durable khi nhiều JVM/pod?
- [ ] Với local DB effect, marker và business update nằm **cùng transaction**?
- [ ] Có test rollback giữa marker và effect?
- [ ] Với external side effect, có remote idempotency/outbox/reconciliation?
- [ ] `IN_PROGRESS` stale có owner/lease/fencing/recovery?
- [ ] TTL/retention bao trùm retry/DLQ/replay horizon?

### 37.3. Spring Integration và từng adapter

- [ ] Interceptor/selector đặt **trước** side effect cần chặn?
- [ ] Duplicate flag/discard behavior đã được kiểm chứng đúng framework version?
- [ ] File/SFTP accept-once không bị hiểu lầm là business completion?
- [ ] HTTP inbound duplicate có response replay/conflict policy?
- [ ] HTTP outbound retry dùng same remote idempotency key?
- [ ] JMS/AMQP ACK, rollback và redelivery nằm đúng boundary?
- [ ] Kafka offset commit, record ID và business event ID được phân biệt?
- [ ] JDBC poller watermark và durable marker có chiến lược rõ?
- [ ] Splitter/aggregator có per-item và per-result keys?
- [ ] DLQ replay giữ lineage và không bypass dedup vô ý?

### 37.4. Kiểm thử, giám sát và vận hành

- [ ] Có duplicate, concurrency, crash, timeout sau remote commit tests?
- [ ] Có test store unavailable, process restart và multiple replicas?
- [ ] Đã phân biệt attempts, duplicate skips, unique completions và unknown outcomes?
- [ ] Logs dùng correlation/attempt refs không chứa secrets/PII?
- [ ] Metrics không gắn key/message ID làm tag?
- [ ] Có runbook cho duplicate spike và stuck claim?
- [ ] Không xóa completed markers để “fix” mà thiếu approval/evidence?
- [ ] Business owner hiểu guarantee ở phạm vi nào và hạn chế còn lại?

## 38. Tổng kết

**Idempotent Receiver Pattern** làm cho Spring Integration chịu được đặc tính **at-least-once delivery**, retry, redelivery và replay mà không thực thi nhiều lần những side effects đáng lẽ chỉ xảy ra một lần. Để áp dụng đúng, cần phân biệt **logical event** với **transport delivery**, chọn **key ổn định theo scope**, dùng **atomic claim/unique constraint**, xử lý trạng thái **NEW/IN_PROGRESS/COMPLETED/UNKNOWN**, và kiểm tra **transaction/ACK** ở đúng ranh giới.

Với **File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC**, nguồn duplicate và cách xác nhận completion khác nhau. Các thành phần Spring Integration như **`IdempotentReceiverInterceptor`, `MetadataStoreSelector`** giúp nhận diện duplicate ở endpoint; **business database unique constraint, Inbox/Outbox, target idempotency và reconciliation** giải quyết phần khó hơn là tránh mất hoặc lặp side effect khi crash và timeout. Kết hợp **kiểm thử concurrency/failure, metrics unique-event, structured logs an toàn và runbooks** giúp hệ tích hợp đáng tin cậy mà không tuyên bố sai rằng chỉ cần một interceptor là đạt exactly-once end-to-end.
