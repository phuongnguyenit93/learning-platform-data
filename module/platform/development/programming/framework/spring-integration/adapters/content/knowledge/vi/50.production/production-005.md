# Đảm bảo idempotency khi restart trong Spring Integration Adapters

> **Chương:** Production  
> **Bài học:** Đảm bảo idempotency khi restart  
> **Module:** Spring Integration Adapters  
> **Phạm vi:** Inbound/outbound adapter, gateway, poller và MessageChannel kết nối File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC; chú trọng hợp đồng message, quản lý lỗi, trạng thái bền vững và vòng đời kết nối.

## 1. Mục tiêu học tập và bài toán thực tế

Kết thúc bài, bạn có thể:

1. Giải thích vì sao **restart** có thể gây mất message, nhận lại message cũ và tạo side effect trùng mặc dù hệ đã có retry.
2. Xác định **điểm bền vững (durable boundary)**, **điểm ack/offset/checkpoint**, **business commit** và **điểm kết quả không chắc chắn** trong mỗi IntegrationFlow.
3. Chọn **idempotency key ổn định** xuyên restart, nhiều replica, replay và thay đổi message headers.
4. Triển khai mô hình **transactional inbox/processed-event ledger**, **transactional outbox**, unique constraint và xử lý concurrent duplicate đúng cách.
5. Hiểu phạm vi của `AcceptOnceFileListFilter`, persistent metadata store, `IdempotentReceiverInterceptor` và tại sao chúng không tự cung cấp exactly-once nghiệp vụ.
6. Phân tích đặc tính restart/redelivery của **File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC**.
7. Thiết kế **claim/lease/fencing**, graceful shutdown, recovery scan, retention, reconciliation và replay an toàn.
8. Xây test matrix chủ động kill process tại các điểm lỗi; theo dõi duplicate, pending age, outbox lag và những trạng thái không rõ kết quả.

**Tình huống xuyên suốt:** Ứng dụng Spring Boot dùng Spring Integration nhận file đơn hàng qua SFTP, tạo order trong JDBC database, gọi HTTP API đối tác và phát sự kiện Kafka. Một pod bị kill ngay sau khi ghi database nhưng trước khi đánh dấu file đã xử lý hoặc commit Kafka offset. Khi pod mới lên, cùng dữ liệu có thể được xử lý lại. Nếu không có ledger/idempotency, hệ tạo đơn hàng hoặc thanh toán hai lần; nếu đánh dấu đã nhận quá sớm, hệ lại có nguy cơ **bỏ sót** đơn hàng.

**Cam kết thực tế:** Với các hệ thống độc lập, thiết kế thường đạt **at-least-once delivery + idempotent business effects** chứ không tuyên bố “exactly once end-to-end” qua file, database, broker và HTTP. Những ví dụ trong bài minh họa hành vi có thể kiểm chứng; API và cấu hình phải đối chiếu **phiên bản Spring Integration/client cụ thể**.

## 2. Idempotency là tính chất của tác động nghiệp vụ

Một thao tác `f` là idempotent nếu lặp lại thao tác với cùng ý nghĩa không tạo thêm tác động ngoài trạng thái mong muốn:

\[
f(f(s,x),x)=f(s,x)
\]

Trong đó `s` là trạng thái nghiệp vụ và `x` là **cùng một yêu cầu logic**. Trên hệ phân tán, phải định nghĩa rõ phạm vi: một record database, một order, một lần gửi thông báo hay toàn bộ workflow?

| Ví dụ | Có thể idempotent? | Điều kiện |
|---|---|---|
| `PUT` đặt trạng thái order thành `CONFIRMED` | Có | Cùng ID/version, không tạo notification mới mỗi lần |
| `INSERT` order mới với unique business key | Có thể | Duplicate được nhận diện và xử lý an toàn |
| Cộng tiền ví lên 100.000 đồng mỗi request | Không mặc định | Phải gắn transaction/request ID để chống cộng lại |
| Gửi email xác nhận | Không mặc định | Cần delivery ledger/dedupe theo template + business event |
| Tạo giao dịch thanh toán qua HTTP POST | Không mặc định | Đối tác có idempotency key/tra cứu trạng thái |
| Upload cùng file SFTP | Không mặc định | Versioned name, checksum/manifest và remote state |
| Publish cùng event Kafka | Có thể trùng delivery | Consumer cần dedupe và xử lý duplicate đúng |
| Replay file sau restart | Không tự an toàn | Business key + durable state + recovery protocol |

**Phân biệt ba lớp idempotency:**

- **Ingress deduplication:** tránh nhận/lấy lại cùng file/record theo quy tắc filter/metadata. Có ích để giảm công việc nhưng chưa chứng minh nghiệp vụ đã commit.
- **Business idempotency:** đảm bảo cùng business key chỉ có một tác động nghiệp vụ hợp lệ, kể cả hai worker chạy đồng thời.
- **Egress idempotency:** không gửi hoặc không thực hiện trùng tác động tới đối tác; cần ledger và/hoặc idempotency do hệ nhận hỗ trợ.

Nếu bài toán cần đúng cả ba, **một accept-once filter duy nhất là không đủ**.

## 3. Vì sao restart tạo ra duplicate và mất dữ liệu?

Restart không chỉ là dừng/start có chủ đích. Nó có thể bắt nguồn từ:

- Deploy/rolling update, scale-in, liveness restart;
- JVM crash, OOM, host reboot, mất điện;
- Broker/client reconnect khiến JMS/AMQP redelivery hoặc Kafka rebalancing;
- Scheduler/poller khởi động lại và nhìn thấy cùng file/row;
- Metadata store hoặc in-memory queue không được lưu bền vững;
- HTTP caller hết timeout rồi tự gửi lại dù backend vẫn tiếp tục xử lý;
- Lease của worker hết hạn, pod mới claim cùng item khi pod cũ còn chạy.

### 3.1. Các cửa sổ lỗi tối thiểu

| Mốc | Điều đã xảy ra | Restart có thể gây ra | Bảo vệ chính |
|---|---|---|---|
| **W0** | Nguồn còn giữ message, ứng dụng chưa nhận | Nguồn có thể giao lại bình thường | Source retention/checkpoint |
| **W1** | Đã poll/receive; chưa lưu durable state | In-memory item mất nếu nguồn đã ack | Ack sau durable handoff hoặc rollback/redelivery |
| **W2** | Metadata/filter đánh dấu accepted; business chưa commit | File/record bị bỏ qua sau restart | Inflight recovery + không dùng metadata như success |
| **W3** | Business transaction đang mở, chưa commit | Rollback hoặc kết quả chưa rõ tùy storage/network | Transaction boundary và kiểm tra actual state |
| **W4** | Business DB commit xong, source ack/offset chưa commit | Source giao lại → duplicate risk | Unique business key + processed-event ledger |
| **W5** | Outbound HTTP/Kafka/file đã thực hiện; local success record chưa commit | Lặp tác động ở hệ ngoài | Stable idempotency key + remote reconciliation |
| **W6** | Source đã ack; downstream chưa durable | Message có thể mất vĩnh viễn | Durable inbox/outbox trước ack |
| **W7** | Đã commit/ack đầy đủ theo contract | Restart/replay chủ động vẫn có thể xử lý lại | Ledger retention + idempotent result |

**Hai lỗi đối nghịch:**

1. **Ack sớm:** nguồn coi là DONE trước khi business result được ghi bền vững → mất message.
2. **Ack muộn:** business đã commit nhưng nguồn chưa nhận ack → redelivery → có thể xử lý trùng.

Trong nhiều tích hợp, thiết kế ưu tiên **ack sau durable commit** để tránh mất dữ liệu, sau đó dùng idempotency giải quyết duplicate do redelivery.

### 3.2. Dòng thời gian crash cụ thể

~~~text
T0    Consumer nhận orderId=O-123 từ Kafka
T1    Xác minh schema và business key
T2    INSERT order O-123 + processed event trong DB transaction
T3    COMMIT DB thành công
T4    Pod bị SIGKILL / JVM crash
T5    Kafka offset chưa commit
T6    Consumer mới nhận lại cùng record
T7    Unique key/ledger trả "ALREADY_PROCESSED"
T8    Consumer xác nhận offset theo container policy
~~~

Nếu `T2` chỉ làm INSERT vào database nhưng không có unique constraint, record có thể được tạo lần hai. Nếu `T2` ghi “processed” ở cache riêng **trước** `T3`, rồi DB rollback, lần nhận sau có thể bị loại bỏ sai.

## 4. Định nghĩa các bất biến cần được bảo vệ

Trước khi viết code, xác định **invariant**:

- **I1 – Không mất nghĩa vụ:** Khi inbound được ack, kết quả nghiệp vụ **hoặc** một nghĩa vụ xử lý bền vững đã tồn tại.
- **I2 – Không tác động trùng:** Cùng business identity + version không tạo thêm business effect ngoài contract.
- **I3 – Không che xung đột:** Cùng key nhưng payload khác không bị bỏ qua âm thầm; phải phát hiện và xử lý.
- **I4 – Có khả năng phục hồi:** Item bị dừng giữa chừng có trạng thái, deadline, owner và đường retry/claim lại.
- **I5 – Không gửi mù khi outcome chưa rõ:** Timeout ở egress không tự chứng minh remote chưa thực hiện.
- **I6 – Concurrency an toàn:** Hai workers cùng key không tạo hai tác động bất kể thứ tự chạy.
- **I7 – Có retention phù hợp:** Dedupe ledger không hết hạn trước khi khả năng replay/chậm đến tồn tại.
- **I8 – Có quan sát và audit:** Có thể trả lời “order này nhận bao nhiêu lần, commit lần nào, ai replay?”.

### 4.1. Độ tin cậy phải có phạm vi

| Tuyên bố | Chấp nhận khi |
|---|---|
| “Không mất record sau restart” | Đã thử crash ở ingress/commit/ack, nguồn hoặc inbox giữ được dữ liệu |
| “Order chỉ tạo một lần” | DB uniqueness + transaction có bằng chứng khi duplicate đồng thời |
| “Kafka publish exactly-once” | Ghi rõ phạm vi Kafka client/transaction và không suy ra external HTTP/DB |
| “Không phát email trùng” | Có delivery ledger hoặc đích hỗ trợ khóa idempotency; test gửi xong mất ACK |
| “SFTP file không bị bỏ qua” | Có ready protocol + persistent ingest state + recovery scan |
| “Replay an toàn” | Có key/version, side-effect reconciliation và retention đạt yêu cầu |

**Không dùng số message ID của Spring Integration để bảo đảm nghiệp vụ** khi mỗi lần ingress/replay có thể tạo Message mới.

## 5. Chọn idempotency key cho restart và replay

### 5.1. Key phải ổn định và có phạm vi

Những thành phần thường cần:

- `sourceSystem` hoặc `producerId`: tránh va chạm giữa đối tác;
- `tenantId`: phân biệt không gian dữ liệu đa tenant;
- `eventId` do producer phát sinh **một lần cho cùng event**;
- `businessId` và `revision`: khi hợp đồng cho phép nhiều phiên bản hợp lệ;
- `operationType`: tránh nhập nhằng `CREATE`, `UPDATE`, `CANCEL`;
- `target` hoặc `sideEffectKind`: khi theo dõi egress riêng.

Ví dụ:

~~~text
ingress-key = (sourceSystem, tenantId, eventId)
order-transition-key = (tenantId, orderId, revision, transitionType)
http-payment-key = (tenantId, paymentRequestId)
file-key = (partnerId, logicalFileId, fileVersion)
outbox-key = (businessEventId, targetSystem)
~~~

**Các khóa không nên mặc định dùng một mình:**

| Giá trị | Vì sao dễ sai |
|---|---|
| Spring Integration `MessageHeaders.ID` | Có thể sinh mới khi parse/gửi lại |
| Kafka offset | Gắn với partition/topic và cơ chế reprocess, không phải business identity liên hệ qua hệ khác |
| HTTP correlation ID | Dùng tracing, có thể thay đổi mỗi request/retry |
| Tên file `orders.csv` | Có thể được tái sử dụng qua nhiều ngày/phiên bản |
| Timestamp hiện tại | Thay đổi qua retry, có clock skew và collisions |
| Hash toàn payload | Schema/order JSON/metadata có thể biến đổi dù business event như cũ |
| Username hoặc email | Có thể thay đổi và không đảm bảo duy nhất dài hạn |

### 5.2. Key trùng nhưng payload khác

Nếu producer tái sử dụng eventId với payload khác, `ON CONFLICT DO NOTHING` có thể lặng lẽ bỏ một cập nhật hợp lệ hoặc che dữ liệu hỏng. Dedupe ledger nên lưu **payload fingerprint/schemaVersion/business version** để phân biệt:

- **Same key, same semantic payload:** `ALREADY_PROCESSED` và trả kết quả cũ.
- **Same key, different semantic payload:** `CONFLICT` / quarantine + alert, không ghi đè im lặng.
- **Different key, later revision:** Quy tắc version/ordering quyết định có xử lý không.
- **Different key, same business operation:** Nếu nghiệp vụ cần chống gửi lặp, thêm một cấp khóa theo action, không chỉ eventId.

Hash dùng để phát hiện xung đột chứ không thay business identifier; chuẩn hóa canonical payload một cách có chủ đích và chọn thuật toán hash phù hợp, tránh nhầm giữa thay đổi format vô hại với thay đổi nghiệp vụ.

### 5.3. Key retention phải theo cửa sổ replay

Không đặt TTL 24 giờ chỉ vì “một ngày đủ lâu” khi Kafka retention 7 ngày, JMS DLQ có thể replay sau 30 ngày, hoặc SFTP partner gửi lại file sau vài tuần.

Dedupe retention cần xét:

- Thời gian redelivery/retry tự động lớn nhất;
- Thời gian message có thể tồn tại trong DLQ/DLT/quarantine;
- Source replay/reprocessing và disaster recovery;
- Business SLA, audit/legal retention và PII minimization;
- Khả năng producer dùng lại key theo version/epoch sau một thời hạn được **định nghĩa trong contract**.

Khi không thể giữ ledger mãi, cần chiến lược archive/compaction hoặc kiểm tra business state authoritative trước khi replay dữ liệu cũ.

## 6. Kiến trúc idempotency cho một IntegrationFlow

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound adapter / gateway"]
    IN --> VAL["Validate schema + stable key"]
    VAL --> INBOX["Transactional inbox / dedupe ledger"]
    INBOX --> DECIDE{"Key state?"}
    DECIDE -->|"New"| BIZ["Business DB transaction"]
    DECIDE -->|"Processed"| DUP["Replay prior outcome / no-op"]
    DECIDE -->|"Conflict"| Q["Quarantine + alert"]
    BIZ --> OUTBOX["Outbox event / target command"]
    BIZ --> ACK["Source checkpoint / ack after durable outcome"]
    OUTBOX --> PUBLISH["Independent outbound worker"]
    PUBLISH --> TARGET["Kafka / HTTP / SFTP / JMS / AMQP"]
    TARGET --> RECEIPT["Receipt / reconcile / retry"]
    RECEIPT --> OUTBOX
    DUP --> ACK
    Q --> OPS["Owner + runbook"]
    INBOX --> OPS
~~~

Trong một transaction database, có thể ghi business state và processed-event marker **cùng lúc**. Nếu không có cùng database/transaction manager, thiết kế phải nêu rõ mốc durable handoff và cách recovery theo saga/queue.

### 6.1. Trạng thái nên lưu

| Bảng / store | Dữ liệu quan trọng | Lý do |
|---|---|---|
| `integration_inbox` | Stable key, source, receivedAt, payloadRef/hash, schema, status, lease/attempt | Recover ingress nếu ngừng giữa chừng |
| `processed_events` | Business key, payload hash, committed outcome/ref, completedAt | Dedupe sau restart |
| `orders` / domain state | Business ID, version, invariant, unique constraint | Bảo vệ kết quả thực sự |
| `integration_outbox` | Event ID, target, payload/ref, status, nextAttemptAt, attempt, last error | Gửi egress sau DB commit |
| `external_operations` | Remote operation ID, idempotency key, unknown/success/failure, receipt | Reconcile HTTP/SFTP và side effect ngoài DB |
| `audit/replay_log` | Operator, reason, source offset/file, before/after state | Điều tra và tuân thủ |

Không nhất thiết ứng dụng nào cũng cần mọi bảng. Điều quan trọng là **mỗi mốc trạng thái có owner và transaction boundary rõ**.

### 6.2. State machine của một inbound event

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> CLAIMED: lease / claim
    CLAIMED --> PROCESSED: business commit + dedupe marker
    CLAIMED --> RETRYABLE: transient failure / lease release
    CLAIMED --> QUARANTINED: permanent payload failure
    RETRYABLE --> CLAIMED: backoff + re-claim
    CLAIMED --> UNKNOWN: ambiguous external effect
    UNKNOWN --> PROCESSED: reconcile confirms success
    UNKNOWN --> RETRYABLE: verified not executed
    PROCESSED --> [*]: source ack/checkpoint
    QUARANTINED --> [*]: durable handling per policy
~~~

**Lưu ý:** `RECEIVED`, `CLAIMED`, `PROCESSED` có thể là ledger của ứng dụng; không phải trạng thái Spring Integration mặc định. `UNKNOWN` không nên tự chuyển về `RETRYABLE` khi chưa có bằng chứng rằng side effect chưa xảy ra hoặc có idempotency contract bảo vệ retry.

## 7. Mẫu transaction: business effect và dedupe marker cùng commit

### 7.1. Mẫu sai: check-then-act không nguyên tử

~~~text
if not alreadyProcessed(key):
    chargeCustomer()
    markProcessed(key)
~~~

Hai workers có thể cùng nhìn “chưa xử lý” rồi cùng thực hiện. Ngoài ra, nếu `chargeCustomer()` thành công nhưng tiến trình chết trước `markProcessed()`, restart sẽ thử lại.

### 7.2. Mẫu tốt hơn cho side effect nằm trong một database

Giả sử cùng transaction DB có thể ghi `processed_events`, cập nhật `orders` và thêm `outbox`:

~~~text
handle(message):
    validate(message)
    key = stableBusinessKey(message)
    hash = semanticPayloadFingerprint(message)

    begin database transaction
        newlyClaimed = insertDedupeKeyIfAbsent(key, hash)

        if not newlyClaimed:
            saved = readCommittedOutcome(key)
            if saved.hash != hash:
                rollback
                return CONFLICT
            commit
            return ALREADY_PROCESSED(saved.result)

        updateBusinessStateWithInvariantChecks(message)
        insertOutboxEventsWithStableIds(message)
        markDedupeCommitted(key, resultingBusinessVersion)
    commit

    return PROCESSED
~~~

**Điểm then chốt:**

- `insertDedupeKeyIfAbsent`, business mutation, outbox và completion marker nằm **trong một local transaction**.
- Dùng unique constraint theo stable key. Transaction isolation và behavior của concurrent inserts phải kiểm tra theo database.
- Nếu transaction rollback, dedupe insert cũng rollback; message sau restart còn cơ hội thực hiện.
- Nếu transaction commit nhưng source ack chưa xảy ra, lần nhận lại thấy kết quả đã commit và không tạo side effect mới.
- Nếu cùng key nhưng payload khác, không trả success như duplicate hợp lệ.
- Nếu cần lưu response cho HTTP gateway, outcome có thể chứa result/reference để trả response nhất quán.

**Không đưa remote HTTP/SFTP call vào transaction này rồi cho rằng DB rollback sẽ hoàn tác remote effect.** Hành động ngoài DB cần command/outbox + remote idempotency/reconciliation.

### 7.3. Ví dụ PostgreSQL: unique key là rào chắn concurrency

~~~sql
CREATE TABLE processed_events (
    source_system     VARCHAR(80)  NOT NULL,
    tenant_id         VARCHAR(80)  NOT NULL,
    event_id          VARCHAR(160) NOT NULL,
    payload_sha256    VARCHAR(64)  NOT NULL,
    business_ref      VARCHAR(160),
    completed_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, tenant_id, event_id)
);

CREATE TABLE orders (
    tenant_id         VARCHAR(80)  NOT NULL,
    order_id          VARCHAR(160) NOT NULL,
    revision          BIGINT       NOT NULL,
    state             VARCHAR(40)  NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE integration_outbox (
    event_id          VARCHAR(160) PRIMARY KEY,
    target            VARCHAR(60)  NOT NULL,
    payload_json      JSONB        NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    attempt_count     INTEGER      NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
~~~

Schema này chỉ là **ví dụ cho PostgreSQL**, không phải database migration sẵn dùng. Cần thiết kế business version, event ID generation, index, retention, consistency và privacy theo domain thực.

Câu lệnh đưa key vào cùng transaction:

~~~sql
INSERT INTO processed_events
    (source_system, tenant_id, event_id, payload_sha256, business_ref)
VALUES
    (:source, :tenant, :eventId, :fingerprint, :businessRef)
ON CONFLICT (source_system, tenant_id, event_id) DO NOTHING;
~~~

Kiểm tra update count: nếu là 0, đọc record đã commit và so sánh fingerprint/outcome. Nếu là 1, thực hiện business update và thêm outbox **trước khi commit transaction đó**. Nếu update sau insert thất bại, toàn transaction phải rollback. Cách `ON CONFLICT`, mức isolation và visibility của concurrent transactions phụ thuộc DB; phải kiểm thử concurrent duplicate và transaction failure window.

### 7.4. Đừng ghi `PROCESSED` ở transaction riêng trước business write

Nếu ledger `PROCESSED` commit trước, rồi business update thất bại, restart sẽ loại bỏ message chưa xử lý. Nếu cần claim trước qua transaction riêng vì công việc kéo dài, trạng thái nên là `CLAIMED/PROCESSING` có lease/recovery, **không** là thành công cuối.

## 8. Transactional inbox và outbox giải quyết hai chiều rủi ro

### 8.1. Inbox: trước khi ack ingress

Có những nguồn như HTTP webhook hoặc asynchronous callback muốn trả success sớm nhưng xử lý nội bộ lâu. Nếu cần trả `202 Accepted`, trước đó phải bảo đảm yêu cầu đã vào **durable inbox/queue** có key, payload/ref và owner xử lý.

~~~text
HTTP ingress
    -> validate + stable event ID
    -> INSERT inbox row (dedupe + durable)
    -> COMMIT
    -> return 202 + tracking ID
    -> background worker claims inbox row
    -> business transaction
    -> mark processed + enqueue outbound
~~~

Nếu cùng request tới hai lần, transaction đầu bảo đảm không tạo hai inbox jobs cho một key. Nếu request có cùng key nhưng payload khác, trả conflict/chuyển review theo API contract.

### 8.2. Outbox: sau business commit nhưng trước khi publish

Nếu ghi DB xong rồi gọi Kafka/HTTP trực tiếp, crash giữa hai bước có thể khiến remote side effect không bao giờ xảy ra, hoặc xảy ra nhưng app không biết.

~~~text
Transaction A:
    update order
    insert processed-key
    insert outbox command/event
COMMIT

Worker B:
    claim outbox
    publish to target
    if success/receipt established:
        mark delivery outcome
    else:
        bounded retry or UNKNOWN_OUTCOME
~~~

Outbox giải quyết **mất nghĩa vụ publish** giữa DB commit và outbound send. Nhưng nếu broker nhận thành công rồi worker chết trước khi đánh dấu sent, event có thể được phát lại. Vì thế **consumer vẫn cần idempotency**. Outbox không tự tạo exactly-once delivery tới mọi đích.

### 8.3. Transaction isolation và outbox concurrency

- Outbox workers dùng row claim/lease hoặc locking theo database dialect.
- Một worker đã claim nhưng bị chậm có thể bị worker khác reclaim; bên nhận vẫn cần idempotency.
- Status `SENT` nên được ghi sau khi xác nhận theo contract; `UNKNOWN` khi response mơ hồ.
- Outbox event ID ổn định qua attempts, không sinh mới mỗi retry.
- Dùng retry/backoff có giới hạn, alert cho oldest pending/failed và capacity.
- Với outbox chứa PII, xem xét mã hóa, quyền đọc và retention.

## 9. Cơ chế Spring Integration: dedupe ở đúng lớp

Spring Integration hỗ trợ nhiều cách nhận diện message đã từng được thấy, nhưng chúng có **mục tiêu và phạm vi** khác nhau. Cần biết cách chúng tương tác với transaction, crash và restart.

### 9.1. Accept-once filter không phải business ledger

| Cơ chế | Mục đích điển hình | Điều không bảo đảm |
|---|---|---|
| `AcceptOnceFileListFilter` | Hạn chế nhận cùng file nhiều lần trong phạm vi filter | Cache in-memory tồn tại sau process restart |
| Persistent file accept-once filter | Dùng `MetadataStore` giữ thông tin file qua restart | Business handler đã commit thành công |
| `SftpPersistentAcceptOnceFileListFilter` | Giữ trạng thái nhận file remote qua store phù hợp | Download/parse/DB/HTTP đã hoàn tất |
| `FileSystemPersistentAcceptOnceFileListFilter` | Giữ trạng thái file local theo metadata | Remote source file đã được xử lý nghiệp vụ |
| `MetadataStore` | Lưu key/value của integration components | Idempotency nghiệp vụ hay ACID cùng DB tự động |
| `IdempotentReceiverInterceptor` | Intercept handler và nhận diện duplicate theo selector | Mọi side effect sau đó được rollback nếu handler lỗi |
| Domain unique constraint/processed ledger | Bảo vệ một business effect trong DB transaction | Các HTTP/SMTP/SFTP effects ngoài DB tự idempotent |

Các tên lớp trên có thể khác API/constructor hoặc được thay đổi theo phiên bản Spring Integration. Bài nêu **vai trò thiết kế**; cần kiểm tra đúng adapter và factory thực tế.

### 9.2. Metadata store phải có durability và chia sẻ phù hợp

Một store key-value nằm trong memory giúp tránh lặp trong cùng JVM, nhưng restart sẽ xóa state. Nếu mục tiêu là sống sót qua restart/multi-replica, xem xét **persistent MetadataStore** trên DB, Redis hoặc kho phù hợp được framework hỗ trợ.

Cần kiểm tra:

- **Durability:** Sau JVM/pod restart, key còn tồn tại không?
- **Atomic claim/update:** Nếu hai replica cùng ghi key, có thao tác atomic `putIfAbsent`/compare-and-set phù hợp không?
- **Transaction coupling:** Metadata commit lúc nào, có nằm cùng DB business transaction không?
- **Key prefix/namespace:** Hai inbound flows có dùng trùng key gây loại nhầm file không?
- **Expiry/cleanup:** Metadata bị xóa/TTL có làm file đã xử lý được nhận lại không?
- **Recovery:** Khi filter accepted nhưng handler failed, làm thế nào để re-drive?
- **Cross-region/multi-process:** Store có tính nhất quán phù hợp với duplicate race không?

**Sai lầm nghiêm trọng:** Chỉ đổi in-memory metadata sang persistent store có thể ngăn một file được poll lại sau crash — nhưng nếu file được đánh dấu accepted **trước** business commit, nó có thể bị bỏ qua **mãi**. Cần recovery state và workflow theo đúng giai đoạn.

### 9.3. IdempotentReceiverInterceptor có semantics riêng

`IdempotentReceiverInterceptor` dùng một message selector để phân loại duplicate ở handler boundary; `MetadataStoreSelector` là một lựa chọn dựa trên store key/value. Cách xử lý duplicate (đánh dấu header, discard/reject, hay cho handler tùy chọn xử lý) phụ thuộc cấu hình của interceptor và luồng.

Những điểm bắt buộc:

1. Key lấy từ **business identity**, không dựa mặc định vào `MessageHeaders.ID`.
2. Nếu selector chỉ “đánh dấu đã thấy” trước handler rồi handler thất bại, cần biết cách rollback/reclaim marker.
3. Không đặt marker “processed” trước khi business state commit nếu chúng không cùng transaction.
4. Nếu duplicate vẫn được đưa xuống handler với header báo duplicate, handler phải có hành vi an toàn.
5. Nếu dùng discard channel, bảo đảm không làm mất nghiệp vụ chưa được xử lý.
6. Cơ chế filter/interceptor là **tầng ingress**, còn domain unique constraint bảo vệ race ở tầng cuối.
7. Kiểm tra behavior khi exception, retry advice, async channel và transaction boundaries thay đổi.

### 9.4. MessageChannel và durable handoff

- `DirectChannel`: handler được gọi đồng bộ theo đường thông thường; exception có thể trở về poller/listener, nhưng cần xem transaction/ack của adapter.
- `ExecutorChannel`: chuyển thread; transaction context upstream không tự lan sang handler; dispatch thành công **không nghĩa** business đã xử lý.
- `QueueChannel`: memory queue không mặc định survive restart; persistent MessageStore hoặc broker cần được chọn khi yêu cầu bền vững.
- Messaging gateway: `sendTimeout` và `replyTimeout` chỉ áp cho những giai đoạn cụ thể; caller timeout không chứng minh handler đã bị hủy.
- Error channel: `ErrorMessage` cho phép xử lý lỗi tùy luồng; **log-and-swallow** có thể khiến nguồn coi là success theo một số cấu hình.

**Review question:** Nếu process bị kill **ngay sau `.channel("workQueue")` trả về** nhưng trước handler, nguồn còn message hay đã ack? Nếu đã ack và queue chỉ ở memory, cần sửa thiết kế.

## 10. File inbound/outbound: restart sau ingest và sau archive

File adapter thường quét thư mục, lọc file và đưa thông tin file vào IntegrationFlow. Khác với broker queue, filesystem không cung cấp một consumer acknowledgement thống nhất cho business workflow.

### 10.1. Quy ước file-ready và business state

Một quy trình rõ ràng:

~~~text
producer:
    write orders_20261123.csv.tmp
    close/flush according to contract
    rename to orders_20261123.csv.ready

consumer:
    discover READY file
    verify source identity + version + checksum/manifest
    claim business file ID
    parse/validate
    transactionally process rows with stable keys
    record complete outcome
    archive or mark DONE
~~~

File có thể được xử lý nhiều lần ở tầng file nhưng vẫn **chỉ một tác động nghiệp vụ cho từng row/order**, nếu thiết kế dedupe đúng.

### 10.2. Crash window theo file

| Sự cố | Có thể thấy sau restart | Cách khôi phục |
|---|---|---|
| Crash trước khi filter accept | File vẫn ở ready | Poll lại bình thường |
| Filter accepted nhưng chưa parse | Persistent filter có thể bỏ qua file | Recovery scan dựa trên business status; sửa/đặt lại metadata **theo runbook** |
| Parse xong, chưa commit row | Chưa có business record | Re-run rows theo stable key |
| Một số row commit, một số chưa | File ở trạng thái partial | Per-row ledger/transaction + file completion marker |
| Toàn bộ rows commit, archive chưa xong | File vẫn ở ready/processing | Reconcile rồi archive, không insert lại |
| Archive xong nhưng durable completion chưa lưu | File mất khỏi ready | Có receipt/manifest và business reconciliation |

### 10.3. File lớn: idempotency ở cấp nào?

- **File-level dedupe:** Cùng logical file/version chỉ được ingest đầy đủ một lần.
- **Record-level dedupe:** Từng row có source record key; retry file không tạo duplicate row.
- **Business-level dedupe:** Hai file khác nhau vẫn có thể cùng một order ID/revision và cần nhận diện trùng.
- **Output-level dedupe:** Việc tạo file outbound có deterministic path/version hoặc manifest.

Nếu file gồm 50.000 rows và công việc commit theo batch 500 rows, restart sau batch thứ 20 đòi hỏi biết **những rows nào đã commit**; một cờ `fileProcessed=true` không đủ để khôi phục giữa chừng.

### 10.4. File outbound

Khi ghi file ra cho đối tác:

- Dùng tên tạm, ghi hoàn tất, xác minh checksum/record count, rồi rename/đặt marker.
- Với mỗi logical batch/event, có deterministic output identity/version.
- Nếu timeout hoặc crash sau rename nhưng trước ghi ledger, kiểm tra file đích thay vì tạo tên ngẫu nhiên mới.
- Không ghi đè file có cùng tên nhưng khác payload/version mà không có chính sách.
- Không xóa original source và outbox command trước khi target delivery đạt contract.

### 10.5. Checklist File sau restart

- [ ] Ready protocol được cả hai phía xác nhận.
- [ ] Persistent filter có cơ chế re-drive file đã accept nhưng chưa xử lý.
- [ ] File, record và business dedupe key được phân biệt.
- [ ] Archive/move/delete chỉ sau durable completion.
- [ ] Partial batch có checkpoint và recovery theo row.
- [ ] File lỗi schema được quarantine, không lặp vô hạn.
- [ ] Nhiều replica có distributed claim/partition, không chỉ in-memory filter.
- [ ] Đã thử kill tại từng giai đoạn từ discover đến archive.

## 11. SFTP inbound/outbound: hai dấu vết remote và local

SFTP inbound thường có thể gồm **remote file synchronizer**, **local file cache** và **downstream business handler**. Có thể có trạng thái “remote file đã được tải” trong khi chưa có business commit.

### 11.1. Cửa sổ lỗi riêng của SFTP

~~~text
Remote SFTP file READY
   -> remote accept-once metadata
   -> local download (temporary -> final)
   -> local accept-once metadata
   -> parse / validate
   -> DB transaction
   -> business COMPLETE
   -> remote/local archive policy
~~~

Phải xác định ở mỗi bước:

- Metadata remote/local lưu ở đâu, có sống sót qua restart không?
- Nếu tải được file nhưng parse lỗi, file ở local cache hay đã bị xóa?
- Nếu remote file thay cùng tên, filter dựa trên timestamp/size/version có nhận ra không?
- Nếu hai pods tải cùng file, metadata store/claim có dùng chung và atomic không?
- Nếu remote source xóa sớm, có bản sao bền vững để replay không?
- Business completion có độc lập với remote accept-once marker không?

### 11.2. Chiến lược an toàn

1. Producer upload tên tạm rồi rename hoặc tạo marker khi hoàn tất.
2. Consumer xác minh SSH host key và có timeout/retry bounded.
3. Ghi nhận logical file ID/version, checksum và source metadata.
4. Download vào local temporary path, chỉ hiển thị final path khi hoàn tất; kiểm tra semantics filesystem.
5. Lưu file bền vững hoặc bảo đảm có thể tải lại cho tới khi business complete.
6. Parse/commit theo stable business keys; có per-row hoặc per-batch checkpoint.
7. Mark complete và archive sau khi dữ liệu đã durable và đối soát đúng.
8. Nếu crash, recovery scan những item accepted/downloaded nhưng chưa complete.
9. Không xóa remote file tùy tiện; áp retention và owner của đối tác.
10. Khi multi-replica, dùng distributed claim hoặc phân vùng rõ.

### 11.3. SFTP outbound và outcome mơ hồ

Nếu SFTP `rename` thành công trên server nhưng client mất response:

- Không khẳng định upload thất bại.
- Kiểm tra remote final/temporary path, size/hash/manifest và target receipt.
- Với cùng business command, giữ **same output identity**, không tạo file trùng bằng tên mới.
- Nếu remote đã nhận file và phía đối tác xử lý, tránh upload lại ngoài contract.
- Ghi `UNKNOWN_OUTCOME` nếu chưa có bằng chứng, có owner và reconciliation workflow.

### 11.4. Checklist SFTP

- [ ] Metadata remote/local và business ledger có trách nhiệm riêng.
- [ ] Có recovery cho file đã download nhưng handler chưa commit.
- [ ] Không chỉ dựa accept-once filter để tránh duplicate nghiệp vụ.
- [ ] Có checksum/version khi file remote có thể thay đổi.
- [ ] Có distributed claim nếu nhiều pods poll cùng remote path.
- [ ] Có session reconnect/backoff, host-key validation và secret rotation.
- [ ] Có đối soát khi upload/rename response bị mất.
- [ ] Test restart sau metadata accept, sau download và sau business commit.

## 12. HTTP inbound/outbound: caller retry và side effect chưa rõ

### 12.1. HTTP inbound gateway/webhook

Với request có side effect, client thường sẽ retry khi:

- Mất kết nối;
- HTTP 502/503/504;
- Gateway timeout;
- Không nhận response dù backend đã commit;
- Client app restart hoặc load balancer đổi backend.

Để xử lý:

1. Bắt buộc có **client-generated idempotency key** hoặc một business request ID được contract công nhận.
2. Validate authentication/authorization và tính toàn vẹn của request.
3. Bảo vệ key bằng unique constraint trong durable inbox/processed ledger.
4. Với cùng key và cùng semantic payload, trả **prior result/tracking ID** nhất quán.
5. Với cùng key nhưng payload khác, trả conflict hoặc xử lý theo API contract.
6. Chỉ trả `200/201/202` khi trạng thái theo contract đã bền vững.
7. Nếu xử lý dài, dùng `202 Accepted + tracking ID` sau khi ghi durable inbox.
8. Khi client disconnect, backend không mặc định bị cancel; worker vẫn cần idempotency.

**Lưu ý:** Trả `202` sau khi chỉ enqueue vào memory `ExecutorChannel` hoặc QueueChannel không persistent có thể mất yêu cầu khi pod restart.

### 12.2. HTTP outbound gateway

| Tình huống | Sai lầm dễ mắc | Hành vi nên chọn |
|---|---|---|
| POST đã gửi, response timeout | Retry với request ID mới | Query remote state hoặc retry cùng idempotency key được remote hỗ trợ |
| 409 do cùng key đã xử lý | Coi là lỗi vĩnh viễn và gửi lại tên khác | Đọc contract: có thể trả prior result |
| 503 trước remote commit | Retry có giới hạn | Per-attempt timeout, jitter, deadline |
| 401 token expired | Lặp liên tục | Refresh có kiểm soát, không đổi business identity |
| Remote API không hỗ trợ idempotency | Retry POST mù | Tạo command ledger/unknown outcome, require reconciliation |
| Caller đã timeout | Cho rằng downstream chưa xử lý | Tra kết quả qua business key/tracking |

### 12.3. Outbound command ledger

~~~text
external_operations(
    operation_id,
    target,
    idempotency_key,
    payload_fingerprint,
    status = PENDING | IN_FLIGHT | SUCCEEDED | FAILED | UNKNOWN,
    remote_reference,
    last_attempt_at,
    next_attempt_at
)
~~~

- Record command nên được ghi bền vững trong cùng transaction với quyết định nghiệp vụ nếu có thể.
- Khi worker gọi remote, dùng stable idempotency key cho các attempts.
- Nếu remote trả xác nhận hợp lệ, lưu remote receipt/result.
- Nếu connection mất sau khi request có thể đã tới remote, giữ `UNKNOWN`; query trạng thái hoặc retry nếu remote idempotency contract cho phép.
- Khi restart, không tự chuyển tất cả `IN_FLIGHT` thành `PENDING` rồi gửi lại mù.

### 12.4. Checklist HTTP

- [ ] Có idempotency key do API contract xác nhận cho endpoint có side effect.
- [ ] Response của duplicate request nhất quán với kết quả trước.
- [ ] Same key/different payload được xử lý rõ.
- [ ] Durable handoff trước khi trả `202`.
- [ ] Có xử lý unknown outcome và late response.
- [ ] Timeout/retry không tự tạo payment/shipment trùng.
- [ ] Không log token, cookie hoặc payload nhạy cảm.
- [ ] Test HTTP POST thành công nhưng response bị mất, và caller retry sau restart.

## 13. JMS: redelivery sau listener restart

JMS có cơ chế acknowledgement và session transaction phụ thuộc provider/container. Khi listener crash trước khi message được xác nhận, broker có thể redeliver.

### 13.1. Cửa sổ điển hình

~~~text
Broker queue -> JMS listener -> DB transaction commit
                                   |
                            Process crash
                                   |
                         JMS ack chưa hoàn tất
                                   |
                            Broker redelivers
                                   |
                      Business ledger sees duplicate
                                   |
                      No-op / prior outcome + ack
~~~

Không thể chỉ dùng JMS acknowledgement để tạo exactly-once tác động trong DB bên ngoài broker transaction. Ngay cả khi listener được cấu hình transacted, cần hiểu phạm vi transaction **có bao gồm DB không**. Local JMS session transaction không mặc định bao trùm JDBC hoặc HTTP.

### 13.2. Checklist JMS

- [ ] Listener container, session transacted/ack mode và thời điểm acknowledge được ghi rõ.
- [ ] Handler exception được propagate hoặc recover theo policy; không nuốt lỗi chưa durable.
- [ ] Nếu container redeliver, business key và processed ledger bảo vệ side effect.
- [ ] Nếu dùng local transaction, xác định rõ DB write nằm ở boundary khác.
- [ ] Poison message có bounded retry/redelivery rồi DLQ.
- [ ] Reply destination/request-reply gateway xử lý late reply/timeout.
- [ ] Consumer concurrency/prefetch không phá ordering và transaction.
- [ ] DLQ replay theo business key, không thay key để “bắt hệ xử lý lại”.
- [ ] Test crash trước/sau DB commit, trước/sau JMS ack và broker restart.

### 13.3. Không ack trước khi durable recovery hoàn tất

Nếu handler lỗi mà listener nuốt exception rồi return, một số container/ack modes có thể acknowledge message. Cần:

- Rethrow để rollback/redelivery theo source semantics, **hoặc**
- Lưu message và lỗi vào durable quarantine/inbox, xác nhận lưu thành công rồi ack nguồn theo policy.

Không xem `errorChannel` mặc định là DLQ bền vững. Kiểm tra error flow thật trong IntegrationFlow/adapter và phiên bản đang chạy.

## 14. AMQP/RabbitMQ: ack, requeue và publisher confirm

### 14.1. Consumer redelivery

Với AMQP listener, các quyết định quan trọng là:

- Broker queue durability và message persistence có đáp ứng yêu cầu?
- Container dùng acknowledgement mode nào?
- Thời điểm ack nằm trước hay sau DB commit?
- Nếu process chết trước ack, broker phát lại như thế nào?
- Requeue/reject/DLX/DLQ có giới hạn và retention không?
- Consumer idempotency hoạt động khi hai deliveries gần nhau không?

**Manual ack** làm rõ quyền điều khiển thời điểm xác nhận, nhưng **không tự tạo exactly-once**. DB đã commit mà ack chưa đến broker thì redelivery là tình huống bình thường phải xử lý.

### 14.2. Publisher confirm cũng có cửa sổ mơ hồ

~~~text
Outbox worker -> broker publish -> broker accepts
                                    |
                            confirm response lost
                                    |
                               worker crash
                                    |
                         outbox still PENDING
                                    |
                           retry same event
~~~

Có thể xuất hiện duplicate publish. Dùng stable message/event ID, consumer dedupe; không dựa vào publisher confirms để khẳng định broker không nhận nếu confirm timeout.

### 14.3. Checklist AMQP

- [ ] Publisher confirms/returns và behavior khi confirm mất được xác định.
- [ ] Outbox event ID giữ nguyên qua retry/restart.
- [ ] Queue/message durability theo SLA; không chỉ đặt durable queue.
- [ ] Consumer ack/requeue/reject behavior được test với crash.
- [ ] Không requeue poison message vô hạn.
- [ ] Có DLQ và durable replay/retention/audit.
- [ ] Consumer idempotent khi broker redeliver.
- [ ] Có test hai consumers nhận cùng logical business event ở các thời điểm khác nhau.
- [ ] Khi scale/restart, prefetch/unacked và queue age được giám sát.

## 15. Kafka: offset commit và DB transaction là hai thế giới

### 15.1. Offset không phải business processed key

Kafka record được xác định bởi topic/partition/offset, nhưng:

- Replay với cùng consumer group có thể đọc lại offset chưa commit.
- Đổi consumer group hoặc reset offset làm đọc lại một khoảng lớn.
- Producer có thể phát cùng business event ở một offset khác.
- Event được copy sang topic khác hoặc retry/DLT tạo một record mới.
- Cùng order có thể xuất hiện nhiều events với revision khác nhau.

**Đừng chỉ lưu offset để chống duplicate nghiệp vụ.** Dùng eventId hoặc `(source, orderId, revision)`, và lưu source topic/partition/offset như metadata audit/checkpoint.

### 15.2. Crash sau DB commit, trước offset commit

~~~text
Kafka record O-123
    -> listener
    -> DB transaction: order update + processed key + outbox
    -> COMMIT
    -> process crashes
    -> offset not committed
    -> Kafka delivers record again
    -> processed key exists + matching fingerprint
    -> no-op, then commit offset according to container policy
~~~

Phải xác định cấu hình ack/commit thực tế của **Spring Kafka listener container** đứng dưới Spring Integration Kafka inbound adapter; không mặc định mọi error handler có cùng semantics. Nếu handler exception bị recover ở error flow, kiểm tra offset có bị commit hay không và message đã durable ở đâu.

### 15.3. Transactional producer không thay thế idempotent DB consumer

Kafka hỗ trợ các semantics về producer idempotence và transaction **trong phạm vi Kafka được cấu hình**. Những bảo đảm đó không tự mở rộng transaction sang external PostgreSQL/HTTP/SFTP.

Với DB + Kafka, lựa chọn phổ biến là:

- Database transaction ghi business + outbox;
- Worker phát Kafka event theo at-least-once;
- Consumer khác dùng processed-event ledger;
- Không hứa exactly-once end-to-end ngoài phạm vi đã chứng minh.

### 15.4. Ordering khi replay

Nếu order revision 2 đang lỗi nhưng revision 3 được xử lý trước, business state có thể sai dù cả hai event có key khác nhau và “không duplicate”. Vì vậy:

- Kafka key/partition phù hợp business ordering requirement;
- Nếu chuyển record sang retry topic/DLT, định nghĩa cách chặn hoặc xử lý revision sau;
- DB dùng version check/optimistic locking để phát hiện stale event;
- Dedupe key có revision khi mỗi revision là một sự kiện hợp lệ khác nhau;
- Không xem “đã thấy key khác” là lý do bỏ qua kiểm tra thứ tự.

### 15.5. Checklist Kafka

- [ ] Stable event ID không phụ thuộc offset.
- [ ] Ack/commit theo listener container phù hợp business durable completion.
- [ ] DB update + processed ledger nằm trong transaction nguyên tử.
- [ ] Producer/outbox retry vẫn giữ event ID.
- [ ] Consumer replay sau reset offset hoặc group migration không nhân đôi side effect.
- [ ] Error recovery/DLT bền vững trước khi coi record đã được xử lý theo policy.
- [ ] Ordering/version guard khi retry topic cho record lỗi.
- [ ] Test crash trước DB commit, sau DB commit/trước offset commit và sau ack.
- [ ] Giám sát consumer lag, rebalances, duplicate count và outbox pending.

## 16. JDBC polling: row claim không phải idempotency

JDBC inbound adapter/poller thường truy vấn rows thỏa điều kiện. Nếu hai replicas cùng `SELECT WHERE status='NEW'`, cả hai có thể đọc cùng row trước khi bất kỳ worker nào đánh dấu `PROCESSING`.

### 16.1. Mô hình claim/lease/complete

~~~text
NEW -> CLAIMED(owner, lease_until, fencing_version)
     -> BUSINESS_COMMITTED
     -> COMPLETE

CLAIMED -> lease_expired -> re-claim by new worker
CLAIMED -> recoverable_error -> RETRYABLE
CLAIMED -> invalid_payload -> QUARANTINED
~~~

Một thiết kế đúng cần:

- Atomic claim/lock theo DB dialect, không SELECT rồi UPDATE không điều kiện;
- Một owner/token/version cho mỗi lần claim;
- Lease expiry để thu hồi job khi pod chết;
- Business unique key để chống duplicate nếu worker cũ vẫn tiếp tục;
- Retry/backoff và limit số attempts;
- Timeout cho query/connection/pool;
- Monitoring rows đang `CLAIMED` quá lâu;
- Durable business commit và complete marker đúng transaction boundary.

### 16.2. Pseudo-SQL PostgreSQL cho claim một batch

~~~sql
-- Ví dụ mang tính định hướng; cần xác minh schema, isolation và index.
BEGIN;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Trong cùng transaction, giới hạn batch và chuyển các ID đã chọn
-- sang CLAIMED, gán lease_owner, lease_until, fencing_version tăng dần.

COMMIT;
~~~

`SKIP LOCKED` và cú pháp giới hạn rows khác nhau theo database. Với PostgreSQL thật, có thể dùng CTE + `UPDATE ... RETURNING` để claim nguyên tử trong một statement. Sau khi claim, business processing phải ngăn worker cũ ghi dữ liệu sau khi lease hết hạn.

### 16.3. Vì sao cần fencing?

Worker A claim job `O-123` với lease 60 giây, nhưng chậm vì GC pause. Lease hết hạn; worker B claim lại và hoàn tất. Sau đó A tiếp tục gửi HTTP POST dựa trên lease cũ. Nếu chỉ có “lock đã hết hạn” mà không có control ở side effect, A vẫn có thể ghi sai hoặc gửi trùng.

**Fencing token/version** giúp hệ đích **có hỗ trợ** từ chối thao tác từ owner cũ. Nếu đích không hỗ trợ fencing, phải dùng idempotency key, workflow status/authorization và reconciliation; chỉ tăng lease timeout không loại bỏ rủi ro.

### 16.4. Checklist JDBC

- [ ] Claim rows nguyên tử, có owner và lease recovery.
- [ ] Có fencing/version khi stale worker có thể tiếp tục ghi.
- [ ] Business unique key độc lập với claim state.
- [ ] Ghi `PROCESSED` cùng transaction với domain changes nếu cùng DB.
- [ ] DB commit outcome mất kết nối được xác minh trước retry.
- [ ] Query/pool timeout, index và batch limit được kiểm thử.
- [ ] Không giữ transaction qua HTTP/SFTP call kéo dài nếu có thể tách.
- [ ] Rows quá hạn `CLAIMED` được scan/recover có audit.
- [ ] Multi-replica test với cùng key, kill/restart và lease expiry.

## 17. Thực hành: handler JDBC idempotent có transaction

Giả sử business database, bảng `processed_events`, bảng `orders` và `integration_outbox` cùng nằm trong PostgreSQL. Producer cấp `eventId` ổn định, consumer tự tính fingerprint sau khi validate payload. Mục tiêu là **DB mutation + dedupe marker + outbound obligation cùng commit**, còn outbound gửi sau bằng worker khác.

### 17.1. Hợp đồng đầu vào

- `(sourceSystem, tenantId, eventId)` là khóa duy nhất của một logical event.
- `(tenantId, orderId, revision)` thể hiện business version, không được tự ý xử lý revision cũ.
- Khi producer retry **cùng event**, eventId và semantic payload không đổi.
- Cùng eventId nhưng payload khác phải là conflict, không silent drop.
- Lệnh publish Kafka/HTTP không được chạy trực tiếp trong DB transaction này.

~~~java
// Java 17+. fingerprint phải được tính phía server từ canonical payload.
record OrderEvent(
    String sourceSystem,
    String tenantId,
    String eventId,
    String orderId,
    long revision,
    String state,
    String fingerprint,
    String outboundJson
) {}
~~~

### 17.2. Mẫu service với unique constraint

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventProcessor {

    private final NamedParameterJdbcTemplate jdbc;

    OrderEventProcessor(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ProcessingOutcome process(OrderEvent event) {
        MapSqlParameterSource p = new MapSqlParameterSource()
            .addValue("source", event.sourceSystem())
            .addValue("tenant", event.tenantId())
            .addValue("eventId", event.eventId())
            .addValue("fingerprint", event.fingerprint())
            .addValue("orderId", event.orderId())
            .addValue("revision", event.revision())
            .addValue("state", event.state())
            .addValue("outboundJson", event.outboundJson());

        int claimed = jdbc.update("""
            INSERT INTO processed_events
              (source_system, tenant_id, event_id, payload_sha256, business_ref)
            VALUES
              (:source, :tenant, :eventId, :fingerprint, :orderId)
            ON CONFLICT (source_system, tenant_id, event_id) DO NOTHING
            """, p);

        if (claimed == 0) {
            String knownHash = jdbc.queryForObject("""
                SELECT payload_sha256 FROM processed_events
                 WHERE source_system = :source
                   AND tenant_id = :tenant
                   AND event_id = :eventId
                """, p, String.class);

            if (!event.fingerprint().equals(knownHash)) {
                throw new IllegalArgumentException(
                    "Same event key with different business payload");
            }
            return ProcessingOutcome.ALREADY_PROCESSED;
        }

        int changed = jdbc.update("""
            INSERT INTO orders (tenant_id, order_id, revision, state)
            VALUES (:tenant, :orderId, :revision, :state)
            ON CONFLICT (tenant_id, order_id)
            DO UPDATE SET revision = EXCLUDED.revision,
                          state = EXCLUDED.state
            WHERE orders.revision < EXCLUDED.revision
            """, p);

        if (changed != 1) {
            // Ví dụ chọn reject stale revision. Domain thực cần policy rõ.
            throw new IllegalStateException("Stale order revision");
        }

        jdbc.update("""
            INSERT INTO integration_outbox
                (event_id, target, payload_json, status)
            VALUES (:eventId, 'kafka-orders', CAST(:outboundJson AS jsonb), 'PENDING')
            ON CONFLICT (event_id) DO NOTHING
            """, p);

        // Không gọi remote HTTP hoặc Kafka trực tiếp ở đây.
        return ProcessingOutcome.APPLIED;
    }

    enum ProcessingOutcome { APPLIED, ALREADY_PROCESSED }
}
~~~

**Lưu ý kỹ thuật:**

1. Đây là skeleton cho **PostgreSQL + Spring JDBC**, không phải code production hoàn chỉnh. Cần kiểm tra imports, phiên bản Java, migrations, validation, logging, exception mapping, canonical hashing, transaction manager, payload schema và các tình huống concurrent inserts.
2. Transaction `@Transactional` có hiệu lực khi phương thức được gọi qua proxy/transaction infrastructure thích hợp; không giả định self-invocation luôn áp transaction.
3. Dedupe insert, domain mutation, outbox được commit/rollback **nguyên tử** trong cùng DB transaction.
4. Nếu duplicate được gửi lại sau commit, `claimed=0`; kiểm tra fingerprint và không tạo side effect mới.
5. Nếu business update thất bại, exception làm rollback marker đã insert, cho phép retry hợp lệ.
6. Với nhiều targets, cần compound outbox identity như `(eventId, target)` hoặc generated target-specific event ID; schema minh họa ở mục 7 dùng một `event_id` khóa chính nên chỉ phù hợp một event/target.
7. Nếu cần response giống lần trước cho HTTP, lưu outcome/response hoặc truy vấn trạng thái domain authoritative.
8. Unique constraint chặn hai workers cùng key hiệu quả hơn một phép SELECT trước INSERT độc lập; vẫn cần kiểm thử isolation và exception semantics.

### 17.3. Tích hợp handler vào IntegrationFlow

~~~java
// Cấu trúc minh họa; kiểm tra DSL của version Spring Integration đang dùng.
@Bean
IntegrationFlow orderEventFlow(OrderEventProcessor processor) {
    return IntegrationFlow.from("orderEvents")
        .handle(OrderEvent.class, (event, headers) ->
            processor.process(event))
        .get();
}
~~~

Flow trên chưa khai báo nguồn/channels/acks và error handling đầy đủ. Đầu vào từ Kafka/JMS/AMQP/File phải được cấu hình sao cho source chỉ được ack/checkpoint theo hợp đồng sau durable completion. Handler trả `APPLIED` cũng chưa có nghĩa Kafka outbox event đã publish thành công.

### 17.4. Test bằng SQL và kết quả nghiệp vụ

- Insert event mới: bảng order có đúng một bản ghi, processed ledger có một key, outbox có một event.
- Gửi lại cùng event: không tăng số order/outbox, kết quả `ALREADY_PROCESSED`.
- Hai threads gửi cùng event: chỉ một transaction tạo business effect.
- Đổi payload nhưng giữ eventId: phát hiện conflict.
- Ném exception giữa business update và outbox: rollback toàn transaction.
- Kill process sau commit trước ack: redelivery trả duplicate no-op.
- Gửi revision cũ: policy xử lý stale revision rõ, không âm thầm ghi đè.
- Outbox worker gửi thành công rồi chết trước khi mark sent: consumer downstream vẫn idempotent.

## 18. Claim/lease, fencing và nhiều replica

### 18.1. Ba tình huống cạnh tranh

**Duplicate đồng thời:** Hai Kafka consumers hoặc hai file pollers nhận cùng logical event. Atomic business key/unique constraint bảo vệ tác động, bất kể những marker ở tầng ingress có được chia sẻ hay không.

**Lease hết hạn:** Worker A claim job với lease 60 giây; bị GC pause lâu. Worker B reclaim và hoàn tất; A thức dậy rồi tiếp tục gọi HTTP. Nếu chỉ có lease mà không có guard tại side effect, duplicate vẫn có thể xảy ra.

**Split brain:** Network partition khiến hai nodes tin rằng mình đang là owner. Không nên dựa duy nhất vào leader election/distributed lock để bảo vệ thao tác có rủi ro cao như thanh toán.

### 18.2. Fencing token

Mỗi lần claim hợp lệ cấp một `fencingVersion` tăng đơn điệu. Nếu hệ đích **có hỗ trợ**, nó phải từ chối mutation từ token thấp hơn version đã chấp nhận. Nếu target không hỗ trợ fencing:

- Dùng stable idempotency key do target xác nhận.
- Kiểm tra trạng thái domain authoritative trước khi thực hiện.
- Dùng durable command ledger, owner và reconciliation workflow.
- Kiểm tra lease trước side effect và áp timeout nhưng không xem đó là bảo đảm tuyệt đối.
- Dùng version/unique constraint cho DB state.
- Không tuyên bố “exactly-once” chỉ vì lock/lease được thiết lập.

### 18.3. Scheduled retry sau restart

- [ ] Một retry owner chính cho mỗi operation, không chồng client/advice/container/broker attempts.
- [ ] `nextAttemptAt`, `maxAttempts`, `lastError` được lưu bền vững.
- [ ] Pending/leased job có recovery khi pod bị kill.
- [ ] Khi redispatch, giữ nguyên business key và target operation ID.
- [ ] Nếu outcome không rõ, kiểm tra remote state hoặc idempotency contract trước resend.
- [ ] Throttle recovery, dùng backoff/jitter tránh hàng nghìn pods cùng retry.
- [ ] Retry queue có TTL, retention và alert oldest pending.
- [ ] Mỗi replay được audit và có owner.

## 19. Startup, graceful shutdown và rolling deploy

### 19.1. Graceful shutdown giúp nhưng không thay crash recovery

Một quy trình ngừng có kiểm soát:

1. Dừng nhận message mới ở poller/listener theo lifecycle adapter.
2. Không claim inbox/outbox jobs mới.
3. Hoàn thành business transactions đang chạy trong khoảng grace period.
4. Chỉ acknowledge những message có durable completion theo contract.
5. Đối với I/O không thể hoàn thành, bảo đảm tồn tại retry/recovery state.
6. Đóng session/connection pools, flush telemetry, báo remaining inflight.
7. Khi force kill, không xem cleanup đã chạy; nguồn/ledger phải tự phục hồi.

**Phải thử SIGKILL/JVM crash**, vì OOM và mất điện không gọi graceful hooks.

### 19.2. Startup recovery có thứ tự

- [ ] Xác minh schema/migrations, secret, TLS/SSH host key và dependency readiness.
- [ ] Đọc durable inbox/outbox để biết trạng thái sau crash.
- [ ] `RECEIVED`: cho claim theo capacity.
- [ ] `CLAIMED` lease chưa hết: không tự claim lại.
- [ ] `CLAIMED` lease hết: reconcile/fence, rồi reclaim nếu an toàn.
- [ ] `PROCESSED` nhưng chưa ack: khi redelivery chỉ no-op và ack theo policy.
- [ ] `OUTBOX PENDING`: worker tiếp tục publish với stable event ID.
- [ ] `UNKNOWN_OUTCOME`: xác minh remote receipt trước retry.
- [ ] File đã accepted nhưng business incomplete: recovery scan, xử lý filter có chọn lọc.
- [ ] Poison/invalid message: quarantine, không retry nóng.
- [ ] Mở lại pollers/listeners theo rate limit và quan sát backlog drain.

### 19.3. Hai app versions cùng chạy lúc rolling

- Key format, canonical payload hashing và ledger schema tương thích.
- Không đổi event ID theo application version.
- Migrations hỗ trợ app cũ/mới trong rolling window.
- Pods cũ có thể giữ lease khi pod mới khởi động; fencing và idempotency bảo vệ.
- HPA/rolling surge có thể tăng tổng claims/connections; tính quota toàn cụm.
- Khi rollback, không xóa metadata/offset/ledger của phiên bản mới để “bắt đầu lại”.
- Test manual replay trên dữ liệu được tạo từ cả hai versions.

## 20. Retention, schema evolution và disaster recovery

### 20.1. Dedupe key phải tồn tại đủ lâu

Retention phải dựa trên cửa sổ replay thực:

| Nguồn | Những khoảng cần xét |
|---|---|
| Kafka | Topic retention, offset reset, consumer group migration, replay thủ công |
| JMS/AMQP | DLQ/DLT retention, redelivery/requeue, operator replay |
| SFTP/File | Partner gửi lại file, recovery từ archive, disaster replay |
| HTTP | Client retry window, remote idempotency key TTL, business reconciliation |
| JDBC | Inbox/outbox retention, lease recovery, row/archive migration |
| DR/backup | Khả năng restore snapshot cũ và nhận lại event mới hơn |

Nếu bên nhận HTTP chỉ duy trì idempotency key trong 24 giờ nhưng ứng dụng replay payment sau 7 ngày, **gửi lại cùng key có thể vẫn gây trùng**. Cần kiểm tra hợp đồng remote, tra trạng thái hoặc phê duyệt nghiệp vụ trước resend.

### 20.2. Canonical fingerprint và format version

Một serializer có thể đổi thứ tự JSON fields sau upgrade mà business payload không đổi. Hash raw bytes dẫn tới false conflict khi restart. Nên:

1. Parse theo schema/version được hỗ trợ.
2. Chuẩn hóa những trường có ý nghĩa nghiệp vụ.
3. Tính canonical fingerprint ở phía consumer.
4. Lưu `fingerprintVersion` bên cạnh hash.
5. Khi đổi thuật toán/schema, có dual-read/migration tương thích.
6. Không dùng hash thay authentication/authorization hoặc business key.

### 20.3. Ledger cleanup và quyền riêng tư

- Không xóa dedupe keys trước khi mọi nguồn replay theo hợp đồng đã hết hạn.
- Với archive dài hạn, cân nhắc tombstone/summary non-sensitive.
- Quản lý payload/raw file chứa PII theo retention và access control.
- Khi scrub dữ liệu, xác định khả năng vẫn chống duplicate bằng key đã pseudonymize phù hợp.
- Không purge metadata store hàng loạt chỉ vì reset môi trường ứng dụng.
- Có audit cho dọn DLQ/quarantine và manual replay.

### 20.4. Disaster recovery khó hơn pod restart

Một bản backup DB cũ có thể chưa chứa processed keys của các event gần đây. Sau restore, Kafka/SFTP lại phát những event đã từng thực hiện side effect tại target. DR runbook phải:

1. Xác định recovery point và khoảng dữ liệu có thể bị mất khỏi ledger.
2. Đối soát business state/remote receipts, không chỉ restart consumers.
3. Rebuild hoặc merge processed ledger có kiểm chứng.
4. Khoanh vùng replay theo stable business IDs, version và source window.
5. Không phát lại hành động không idempotent nếu outcome mơ hồ.
6. Kiểm chứng database, file, broker và HTTP state sau DR bằng test fixtures.
7. Ghi evidence và owner phê duyệt kết thúc phục hồi.

## 21. Observability: đo duplicate và trách nhiệm khôi phục

Một dashboard chỉ đếm message ingress hoặc Kafka offset tăng sẽ không chứng minh hệ xử lý đúng. Cần theo dõi **logical event → business effect → source acknowledgement → downstream delivery**.

### 21.1. Log cấu trúc và tracing

| Trường | Mục đích |
|---|---|
| `sourceSystem`, `tenantId`, `eventId` | Khóa logic của event |
| `businessId`, `revision`, `operation` | Nhận diện side effect |
| `fingerprintVersion`, `payloadHash` | Phát hiện cùng key/different payload |
| `integrationFlowId`, endpoint/adapter ID | Biết message đi qua handler nào |
| `podId`, `workerId`, `leaseVersion` | Điều tra duplicate đồng thời |
| `fileId`, `sourceOffset`, `sourceMessageId` (nếu có) | Truy vết nguồn, không dùng thay business key |
| `inboxStatus`, `processedStatus`, `outboxStatus` | Phân biệt trạng thái bền vững |
| `ack/commitState` | Phân biệt business commit và source acknowledgement |
| `attempt`, `errorCategory`, `retryDelayMs` | Phát hiện retry storm |
| `remoteOperationId`, `remoteReceipt` | Đối soát external side effect |
| `correlationId`, `traceId`, `incidentId` | Điều tra end-to-end |
| `replayOwner`, `replayReason` | Audit thao tác phục hồi thủ công |

Không ghi password, raw API token, SFTP private key, Authorization header, session cookie hoặc payload chứa PII. Ledger/quarantine cũng phải có ACL, encryption và retention phù hợp.

### 21.2. Metrics cần xuất

| Metric logic | Cảnh báo khi |
|---|---|
| Ingress received vs business committed | Tồn item nhận nhưng không có completion |
| Duplicate detection rate | Tăng bất thường sau restart/replay |
| Dedupe conflict count | Same key/different payload, bug producer/migration |
| Inbox oldest pending/claimed age | Worker ngừng hoặc lease hết hạn |
| Stale lease and recovery count | Worker bị treo hoặc timeout không hợp lý |
| Outbox pending count/oldest age | Commit nghiệp vụ có nhưng outbound chưa gửi |
| Outbox retries/exhausted | Target gặp lỗi kéo dài |
| Unknown-outcome count/age | Side effect chưa xác minh |
| Kafka lag/rebalances/offset commit errors | Message backlog hoặc bị phát lại |
| JMS/AMQP ready/unacked/redelivery/DLQ age | Redelivery/poison message chưa xử lý |
| SFTP/File oldest ready/processing age | File kẹt sau restart |
| JDBC lock/transaction/pool wait | DB contention gây lease timeout |
| Business effect count per unique event | Phát hiện thao tác lặp thực sự |
| Recovery backlog drain rate | Khả năng phục hồi sau outage |
| End-to-end business completion latency | Đạt SLO hay không |

Tên chỉ số là **khái niệm**, không phải mọi metric đều có sẵn từ Spring Integration/Micrometer. Các chỉ số nghiệp vụ thường phải được instrument bằng code/ledger riêng. Tránh gắn eventId làm label metric cardinality cao; lưu eventId ở logs/traces có kiểm soát.

### 21.3. Đọc metric cho đúng

- Duplicate count tăng sau Kafka replay **có thể là bình thường**; nếu business side effect count tăng tương ứng cho cùng key mới là lỗi.
- Queue depth thấp không chứng minh không có backlog; JMS/AMQP có thể giữ nhiều unacked messages.
- Kafka committed offsets tăng nhưng processed ledger không tăng có thể cho thấy ack quá sớm hoặc error handler nuốt lỗi.
- Outbox pending tăng dù DB business commit vẫn đều cho thấy egress bị nghẽn.
- `CLAIMED` lease expiry tăng có thể do GC pause, quá tải worker, remote timeout hoặc pool saturation.
- Conflict tăng sau deploy có thể xuất phát từ thay đổi canonical hash/schema version chứ không chỉ producer gửi dữ liệu sai.

**Câu hỏi giám sát hàng ngày:** Mọi event được nhận có thuộc một trong ba trạng thái rõ ràng: **đã xử lý**, **đang chờ có khả năng phục hồi**, hoặc **lỗi đã có owner** hay không?

## 22. Bảo mật, replay attack và phân quyền vận hành

Idempotency không thay authentication/authorization. Một client không được phép nhận lại prior result chỉ bằng cách biết hoặc đoán idempotency key.

Checklist:

- [ ] Xác thực và phân quyền người gửi trước khi tra ledger hoặc trả response cũ.
- [ ] Key namespace có source/tenant phù hợp, không xung đột giữa tenant.
- [ ] Với webhook, kiểm tra signature, timestamp/nonce theo protocol khi cần chống replay attack.
- [ ] Không dùng security nonce thay business key cho redelivery hợp lệ.
- [ ] Ledger/inbox/outbox được mã hóa/lưu an toàn, có quyền đọc/ghi tối thiểu.
- [ ] DLQ/quarantine được bảo vệ như dữ liệu nguồn, không mở truy cập toàn tổ chức.
- [ ] Operator replay phải có người phê duyệt, reason, scope và audit.
- [ ] Không cho phép replay dữ liệu đã hủy/expired mà không kiểm tra domain state.
- [ ] Không trả prior response thuộc tenant khác khi key bị trùng.
- [ ] Không bypass TLS/SSH host-key validation trong lúc phục hồi.
- [ ] Có rate limit cho replay batches và retry để không gây DoS.
- [ ] Khi command gây payment, refund, cancellation hoặc cấp quyền, kiểm tra authorization và current policy trước bất kỳ side effect mới nào.

**Đặc biệt:** Idempotency key của API đối tác có thể có giới hạn TTL hoặc phạm vi merchant/account. Việc gửi cùng key dưới credential khác không nhất thiết được remote nhận diện là duplicate; phải đọc contract thực.

## 23. Ma trận kiểm thử restart và replay: 65 tình huống

### 23.1. Cách thiết kế kiểm thử có bằng chứng

1. Tạo test fixtures với stable eventId, businessId, source/tenant, schema version và fingerprint.
2. Ghi nhận state trước lỗi: ingress marker, DB transaction, outbox record, ack/offset.
3. Tiêm lỗi ở **thời điểm cố ý**, không chỉ restart sau khi xử lý xong.
4. Kill process thực sự hoặc ngắt network/commit confirmation đúng cửa sổ.
5. Khởi động lại hoặc scale sang replica khác, để source redeliver/replay.
6. Đọc actual business state tại DB/partner/broker/file, không chỉ log.
7. Ghi attempts, completed effects, duplicate no-op, DLQ/UNKNOWN outcomes.
8. Thử hai workers cùng key và một worker cũ hoạt động sau lease expiry.
9. Thử key retention, migration schema và restore backup.
10. Chỉ PASS khi các bất biến I1–I8 được chứng minh.

### 23.2. Ma trận nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **T01** | Same eventId nhận hai lần trong một JVM | Một business effect, duplicate no-op |
| **T02** | Same eventId nhận lại sau restart | Persistent ledger ngăn duplicate |
| **T03** | Same key nhưng khác semantic payload | Conflict/quarantine, không silent drop |
| **T04** | Hai threads cùng insert dedupe key | Unique constraint ngăn double effect |
| **T05** | Hai pods nhận same business event | Một business effect |
| **T06** | Crash trước transaction dedupe | Source/inbox replay xử lý được |
| **T07** | Crash sau insert marker, trước commit | Marker và business mutation cùng rollback |
| **T08** | Crash trong lúc update order | Không có partial committed state trái invariant |
| **T09** | Crash ngay sau DB commit | Redelivery trả already-processed |
| **T10** | Crash sau DB commit, trước source ack | Không mất và không trùng |
| **T11** | Source ack trước durable inbox | Test phát hiện nguy cơ mất dữ liệu, không cho GO |
| **T12** | ExecutorChannel accept task rồi pod chết | Có durable recovery, không nhầm enqueue với processed |
| **T13** | QueueChannel in-memory bị restart | Không giả định queue sống sót nếu chưa persistent |
| **T14** | Metadata/business store unavailable | Không ack success khi chưa durable |
| **T15** | IdempotentReceiverInterceptor thấy duplicate | Duplicate handling đúng cấu hình, không chạy side effect |
| **T16** | In-memory MetadataStore reset | Business ledger vẫn bảo vệ side effect |
| **T17** | Persistent file filter accepted nhưng handler failed | Recovery scan tìm file incomplete |
| **T18** | Hai flows dùng metadata prefix trùng | Namespace ngăn loại nhầm |
| **T19** | Metadata TTL hết trước replay window | Test phát hiện hoặc có authoritative state fallback |
| **T20** | File đang upload dở | Không xử lý trước ready marker/rename |
| **T21** | File xử lý được 500/1.000 rows rồi crash | Per-row/transaction checkpoint giúp resume |
| **T22** | File toàn bộ rows commit nhưng archive lỗi | Không insert lại, chỉ reconcile/archive |
| **T23** | Cùng file name nhưng revision khác | Version contract xử lý đúng |
| **T24** | Hai file khác tên có cùng order revision | Business dedupe chặn |
| **T25** | File outbound ghi xong, ledger chưa nhận | Reconcile target path/checksum trước retry |
| **T26** | SFTP remote accepted, local download dở | Re-fetch/resume an toàn |
| **T27** | SFTP local ready, business chưa commit | Recovery từ local/remote |
| **T28** | SFTP remote metadata persisted, DB rollback | Accepted không bị coi là completed |
| **T29** | Hai pods tải cùng SFTP file | Claim/idempotency giữ một effect |
| **T30** | SFTP upload/rename thành công, response mất | Check remote state, không tạo file thứ hai |
| **T31** | HTTP webhook cùng idempotency key lặp | Same result/tracking ID, một command |
| **T32** | HTTP same key/different payload | Conflict, không trả prior result sai |
| **T33** | HTTP trả 202 trước durable inbox | Test xác định sai thiết kế, không GO |
| **T34** | HTTP client disconnect sau backend commit | Retry không double effect |
| **T35** | HTTP POST remote commit, response timeout | Reconcile hoặc retry same key nếu được hỗ trợ |
| **T36** | Remote idempotency TTL hết trước replay | Không resend blind, có owner review |
| **T37** | JMS listener crash trước DB commit | Redelivery xử lý được |
| **T38** | JMS listener crash sau DB commit, trước ack | Redelivery no-op |
| **T39** | JMS handler nuốt lỗi chưa durable | Test phát hiện ack sai và sửa |
| **T40** | JMS poison message redelivery nhiều lần | Bounded DLQ, không retry vô hạn |
| **T41** | AMQP consumer commit DB, ack mất | Redelivery idempotent |
| **T42** | AMQP publisher broker nhận, confirm mất | Outbox retry + consumer dedupe |
| **T43** | AMQP DLQ đích không tồn tại | Không silent recover/drop |
| **T44** | AMQP poison requeue storm | Bounded retry và quarantine |
| **T45** | Kafka DB commit, offset chưa commit | Redelivery no-op |
| **T46** | Kafka đổi consumer group, replay topic | Business effects không nhân đôi |
| **T47** | Kafka producer gửi lại cùng event với offset mới | Consumer dùng business key |
| **T48** | Kafka retry topic tạo offset/topic mới | Event identity vẫn ổn định |
| **T49** | Order revision 3 tới trước revision 2 | Version/ordering guard xử lý đúng |
| **T50** | Kafka error flow nuốt exception rồi commit offset | Test phát hiện mất processing obligation |
| **T51** | Hai JDBC pollers claim cùng row | Atomic claim/unique guard |
| **T52** | JDBC worker crash khi CLAIMED | Lease/recovery cho phép xử lý lại |
| **T53** | Lease hết hạn, worker cũ thức dậy | Fencing/idempotency chặn stale side effect |
| **T54** | DB connection mất đúng lúc COMMIT | Reconcile actual state trước retry |
| **T55** | Key/fingerprint thay sau schema migration | Có versioned migration/dual read |
| **T56** | Business DB commit, publisher chưa chạy | Outbox còn PENDING và được phát sau restart |
| **T57** | Publish thành công, worker chưa mark SENT | Event ID ổn định và consumer dedupe |
| **T58** | Một event gửi hai targets | Per-target delivery ledger tránh bỏ sót |
| **T59** | Outbox có 10.000 pending events sau outage | Retry/throttle có giới hạn, drain được |
| **T60** | Restore database backup cũ và replay source | DR reconciliation tránh double effects |
| **T61** | Dedupe ledger purge sớm | Retention policy bị phát hiện/điều chỉnh |
| **T62** | Operator replay DLQ sau sửa schema | Không duplicate, có audit |
| **T63** | Replay payment/order đã expired/cancelled | Business validity check từ chối tác động sai |
| **T64** | Rolling deploy hai versions cùng xử lý | Key/schema/claim tương thích |
| **T65** | Graceful stop và SIGKILL khi inflight | Recovery theo I1–I8, không mất/trùng effect |

**Bằng chứng cho mỗi test:** môi trường và version, input/business ID, payload fingerprint, source offset/path, expected/actual, DB/remote side effect count, ack status, inbox/outbox result, attempts, logs/traces và owner xác minh.

### 23.3. Ưu tiên kiểm thử

- **P0 trước go-live:** T04, T09–T12, T17, T31–T35, T38, T41–T42, T45, T51–T57 và T65. Đây là các cửa sổ mất/trùng điển hình.
- **P1 trước mở rộng:** multi-replica claims, retry/DLQ, ordering, rolling deploy, quota và backlog.
- **P2 định kỳ:** backup restore, retention expiry, key/fingerprint migrations, manual replay audit.

Mức ưu tiên là đề xuất học tập; hệ thống thanh toán, cấp quyền truy cập hoặc thao tác không thể đảo ngược có thể yêu cầu risk assessment nghiêm ngặt hơn.

## 24. Runbook phục hồi sau restart hoặc outage

### 24.1. Bắt đầu bằng một câu hỏi: nghĩa vụ đã nằm ở đâu?

Khi có sự cố, phân biệt:

1. **Nguồn vẫn giữ dữ liệu?** File ready, SFTP remote file, JMS/AMQP queue, Kafka offset chưa commit, JDBC row NEW?
2. **Ứng dụng đã lưu bền vững?** Inbox row, processed key, business record, outbox event?
3. **Đã có side effect ngoài DB?** HTTP payment/shipment, file SFTP outbound, Kafka publish, broker message?
4. **Đã có receipt/confirmation không?** Response, publisher confirm, remote file checksum, partner transaction ID?
5. **Có thể gửi lại an toàn không?** Remote có idempotency contract, fencing/version, reconciliation hoặc operator approval?

**Không** reset metadata, xóa file/queue hoặc seek Kafka offset trước khi đối chiếu năm câu hỏi này.

### 24.2. Quy trình 12 bước

1. **Đóng băng phạm vi lỗi:** Xác định deployment, pod, source range, thời gian, target và business IDs liên quan.
2. **Giảm ingress khi cần:** Pause poller/listener/HTTP command acceptance nếu source có khả năng giữ bền vững.
3. **Chụp trạng thái:** Inbox/outbox/processed ledger, file metadata, offsets, queue ready/unacked, connection state.
4. **Chốt business side effects:** Kiểm tra DB authoritative và remote target bằng operation ID hoặc receipt.
5. **Phân loại:** NEW, CLAIMED, PROCESSED, PENDING_OUTBOX, SENT, UNKNOWN_OUTCOME, QUARANTINED.
6. **Tìm root cause:** Schema, transaction rollback, lost ack, network timeout, worker OOM, lease expiry, code bug.
7. **Kiểm tra idempotency scope:** Key, tenant, eventId, revision, remote TTL, canonical hash version.
8. **Sửa nguyên nhân:** Bản vá code/config, credential, capacity, partner outage hoặc dữ liệu sai.
9. **Reconcile unknown outcomes:** Không resend mù side effect tài chính/khó đảo ngược.
10. **Replay có giới hạn:** Chọn batch nhỏ, giữ business key, attempts/ordering, quan sát actual result.
11. **Drain backlog:** Tăng dần concurrency trong quota, giám sát outbox lag/duplicate counts.
12. **Đóng incident:** So sánh số logical events với business effects, lưu audit và thay đổi test/runbook.

### 24.3. Bảng quyết định nhanh

| Trạng thái | Không nên làm | Hành động phù hợp |
|---|---|---|
| File đã accepted, DB chưa có order | Mặc định bỏ qua vì filter đã thấy | Recovery scan và re-drive theo key/ledger |
| DB đã commit, Kafka offset chưa commit | Reset DB để “khớp offset” | Cho redelivery; business idempotency no-op |
| DB commit, outbox PENDING | Gửi lại inbound từ đầu với eventId mới | Cho outbox worker phát event cũ |
| HTTP outcome UNKNOWN | Retry với request ID mới | Query partner hoặc retry cùng key được hỗ trợ |
| AMQP publisher confirm mất | Khẳng định broker không nhận | Reconcile/consumer dedupe khi publish lại |
| JMS poison message | Requeue nóng mãi | DLQ và root-cause fix |
| Kafka DLT record cần replay | Chuyển về topic chính tùy tiện | Kiểm tra ordering/version và duplicate state |
| JDBC lease hết nhưng worker cũ còn chạy | Chỉ tăng TTL | Fencing/idempotency, kiểm tra remote state |
| Metadata store mất dữ liệu | Xóa business state cho “đồng bộ” | Rebuild/reconcile từ authoritative records |
| Backup DB cũ được restore | Resume tất cả consumers ngay | DR reconciliation cho khoảng thiếu ledger |

### 24.4. Replay checklist

- [ ] Có incident/replay ticket, owner và phạm vi cụ thể.
- [ ] Root cause đã xử lý hoặc có mitigation được phê duyệt.
- [ ] Business idempotency key giữ nguyên.
- [ ] Same-key/different-payload được kiểm tra.
- [ ] Không vi phạm business version, expiry, cancellation state.
- [ ] Unknown remote side effect đã xác minh hoặc có idempotency contract.
- [ ] Có giới hạn batch/concurrency/rate và khả năng dừng.
- [ ] Có alert trên duplicate conflicts, DLQ, target errors và backlog.
- [ ] Có expected number of logical successes và đối soát actual effects.
- [ ] Có audit đầy đủ trước/sau replay; chỉ dọn DLQ theo retention policy.

## 25. Case study: SFTP → JDBC/inbox-outbox → Kafka và HTTP logistics

Một nền tảng xử lý đơn hàng từ đối tác: cứ 10 phút đối tác đưa file CSV lên SFTP. Mỗi file chứa 1.000–10.000 dòng. Sau khi validate, ứng dụng ghi order vào PostgreSQL, gửi `OrderAccepted` sang Kafka và tạo shipment qua HTTP logistics partner.

### 25.1. Thiết kế ban đầu gặp lỗi

- Producer upload thẳng tên `orders.csv`, chưa hoàn tất vẫn bị poll.
- SFTP filter accept-once chỉ dùng memory; restart khiến file được đọc lại.
- DB không có `(tenant, orderId, revision)` uniqueness.
- Handler commit order rồi gửi Kafka trực tiếp; không có outbox.
- HTTP POST tạo shipment không dùng idempotency key.
- Khi pod restart, đã có order nhưng file chưa move sang `done`, nên xử lý lại.
- Khi HTTP timeout sau shipment creation, worker gửi lại một request ID khác.
- Khi Kafka consumer redeliver, một service downstream tạo shipment thứ hai.
- Không có durable record để trả lời một file có bao nhiêu rows đã xử lý.

### 25.2. Thiết kế mục tiêu

**Nguồn SFTP:**

- Producer ghi file tạm rồi rename thành `.ready` hoặc gửi manifest.
- Mỗi file có logical file ID, version và checksum.
- Remote/local metadata stores có namespace rõ; application lưu ingest state độc lập.
- Multi-replica dùng distributed claim hoặc phân vùng remote path.

**Business inbox/ledger:**

- Mỗi row có stable key `(partnerId, tenantId, orderId, revision)`.
- Dùng DB transaction có unique guard, domain update và outbox insert.
- File completion chỉ được mark khi mọi row hợp lệ đã xử lý hoặc lỗi được xử lý theo policy.
- Với batch partial, có per-row status hoặc committed checkpoint để resume.

**Kafka egress:**

- Outbox event có `eventId` ổn định, payload version rõ.
- Publisher retry at-least-once, không tạo event ID mới sau restart.
- Consumer dùng processed-event ledger hoặc unique business effect key.
- Offset commit phụ thuộc durable processing, không chỉ nhận record.

**HTTP logistics:**

- Outbound command ledger có `shipmentRequestId` ổn định.
- Partner hỗ trợ idempotency key thì giữ cùng key qua retries.
- Nếu partner không hỗ trợ, dùng status lookup/receipt/reconciliation.
- Timeout sau remote commit được phân loại `UNKNOWN_OUTCOME`, không tự tạo shipment thứ hai.

**Quan sát:**

- File received/processed counts, oldest pending, partial file progress.
- Duplicate no-op per source/business event.
- Inbox stale leases, outbox pending age, Kafka lag/commit errors.
- HTTP unknown outcomes và verified shipment results.
- Correlation qua file ID → order ID → outbox event ID → Kafka/HTTP receipt.

### 25.3. Dòng thời gian kill giữa chừng

~~~text
09:00:00  File F-001 được rename thành READY
09:00:01  Pod A claim F-001; parse 2.000 orders
09:00:05  1.000 orders đầu đã commit cùng outbox events
09:00:06  Pod A bị kill; file chưa DONE
09:00:20  Pod B recovery file F-001
09:00:22  Rows 1..1000 -> ALREADY_PROCESSED
09:00:30  Rows 1001..2000 -> process/commit
09:00:31  File complete marker được commit
09:00:35  File được archive theo contract
09:00:40  Outbox workers phát Kafka events pending
09:00:45  Một publisher bị kill sau publish nhưng trước mark SENT
09:01:00  Publish lại same event ID; downstream consumer no-op
~~~

Cùng file có thể được ingest lại, nhưng **mỗi order version chỉ được commit hợp lệ một lần**. Không nên cố ngăn mọi duplicate delivery ở mọi tầng; thay vào đó bảo vệ invariant cuối cùng bằng durable state.

### 25.4. Các failure drills

**Drill A — Crash sau filter accept, trước DB commit.** Recovery scan vẫn phát hiện file chưa complete dù metadata store có record accepted.

**Drill B — Crash giữa các batches.** Chỉ rows chưa committed được áp business effect; rows đã complete trả no-op.

**Drill C — DB commit nhưng Kafka publisher chưa phát.** Outbox pending được phát sau restart, không tạo order mới.

**Drill D — Kafka publisher được broker accept nhưng confirm/callback mất.** Có thể publish lại, nhưng consumer có processed ledger và business effect không trùng.

**Drill E — HTTP logistics tạo shipment nhưng response timeout.** Query partner bằng business shipment ID hoặc retry cùng idempotency key; không tạo shipment khác.

**Drill F — Pod A hết lease trong khi vẫn gọi HTTP.** Pod B claim lại; fencing/remote idempotency/reconciliation bảo vệ business side effect.

**Drill G — Restore backup thiếu ledger gần đây.** Recovery đối soát order/shipment và outbox, không replay mù các lệnh thanh toán/shipment.

### 25.5. Tiêu chí nghiệm thu

- Tổng số logical orders hợp lệ khớp với số business records theo domain contract.
- Không có order/shipment duplicate do restart/redelivery.
- Có thể xác định row nào đã commit, row nào failed, row nào chưa bắt đầu.
- Kafka/outbox pending sau outage được drain theo SLA.
- File accepted nhưng incomplete không bị bỏ sót.
- Unknown HTTP outcomes có owner và được đối soát.
- Multi-replica, rolling deployment và manual replay không tạo sai lệch nghiệp vụ.
- Dashboard/runbook đủ để điều tra với business ID mà không phải mở raw payload nhạy cảm.

## 26. Mẫu phiếu review idempotency trước production

Đây là **YAML minh họa cho review nghiệp vụ/kỹ thuật**, không phải cấu hình mà Spring Integration hoặc Spring Boot tự hiểu:

~~~yaml
flow: supplier-orders-sftp-to-kafka-and-http
owner:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

ingress:
  type: sftp-file
  remoteReadyProtocol: temporary-then-rename
  sourceId: partner-id
  fileIdentity: partner-file-id-version
  distributedClaim: required
  acceptedFileRecovery: required

messageIdentity:
  key: source-tenant-orderId-revision
  fingerprint: canonical-business-payload-sha256
  fingerprintVersion: 1
  sameKeyDifferentPayload: QUARANTINE_AND_ALERT
  retention: REVIEW_WITH_BUSINESS_OWNER

durability:
  sourceAckAfterDurableCommit: required
  inbox: relational-database
  businessEffect: unique-constraint-and-transaction
  outbox: same-transaction-as-domain
  archiveAfterCompletion: required

outbound:
  kafka:
    stableEventId: required
    consumerIdempotency: required
    commitPolicy: REVIEW_CONTAINER_CONFIGURATION
  logisticsHttp:
    stableIdempotencyKey: shipment-request-id
    partnerKeyTtl: REVIEW_WITH_PARTNER
    ambiguousOutcome: RECONCILE_BEFORE_RESEND

restartRecovery:
  lease: required
  fencingOrTargetIdempotency: required
  staleClaimScan: required
  unknownOutcomeQueue: required
  replayAudit: required
  rateLimitAfterOutage: required

observability:
  duplicateNoopRate: required
  sameKeyPayloadConflictRate: required
  inboxStaleAge: required
  outboxPendingAge: required
  unknownOutcomeAge: required
  businessCompletionLatency: required

testing:
  crashWindowTestsPassed: PENDING
  twoReplicaDuplicateTestsPassed: PENDING
  remoteSideEffectTestsPassed: PENDING
  replayAndRollbackTestsPassed: PENDING

approval:
  technicalOwner: PENDING
  businessOwner: PENDING
  securityOwner: PENDING
  operationsOwner: PENDING
~~~

Các giá trị `REVIEW_...` và `PENDING` phải được hoàn tất; phiếu không thay thế việc triển khai các mechanism trong code hoặc cấu hình broker/adapter.

### 26.1. Cổng go/no-go

| Trạng thái | Điều kiện |
|---|---|
| **GO** | Crash windows, concurrent duplicate, durable ack và outbound reconciliation đã được thử với bằng chứng |
| **GO WITH EXCEPTION** | Ngoại lệ có owner, expiry, giới hạn ảnh hưởng và biện pháp được duyệt |
| **HOLD / RETEST** | Thiếu test restart/rollback, chưa xác minh retention hoặc container ack semantics |
| **NO-GO** | Mất message sau ack, duplicate side effect không kiểm soát, không biết remote outcome, hoặc bỏ qua bảo mật |

### 26.2. Checklist cuối trước go-live

- [ ] Có sơ đồ durable boundaries, source ack/offset và business/outbox transaction.
- [ ] Stable key + payload fingerprint, policy same-key/different-payload rõ.
- [ ] Domain unique constraint hoạt động khi hai workers tranh chấp.
- [ ] Dedupe marker và business update commit trong cùng transaction nếu cùng DB.
- [ ] Metadata filter không đánh đồng accepted với processed.
- [ ] In-memory QueueChannel/ExecutorChannel không được coi là durable.
- [ ] File/SFTP accepted but incomplete có recovery scan.
- [ ] HTTP inbound trả Accepted chỉ sau durable handoff.
- [ ] JMS/AMQP/Kafka redelivery được test sau business commit trước ack.
- [ ] Outbox event ID ổn định, publisher/consumer idempotency đúng phạm vi.
- [ ] Unknown outcome có reconciliation/approval, không retry mù.
- [ ] Claim/lease/fencing/recovery phù hợp multi-replica.
- [ ] Dedupe retention dài hơn replay window hoặc có fallback authoritative state.
- [ ] Rolling deploy và DR backup restore đã được xem xét.
- [ ] Có logs/metrics/alerts, replay runbook, incident owner và security controls.
- [ ] Những ca kiểm thử P0 đã pass, không có blocker mất/trùng nghiệp vụ.

## 27. Anti-pattern cần tránh

**“Filter accept-once nghĩa là xử lý đúng một lần.”** Filter thường chỉ biết file/message đã được nhìn thấy; không chứng minh DB/HTTP side effect đã commit.

**“Ghi processed key trước rồi xử lý sau.”** Nếu marker commit sớm và worker crash, message chưa xử lý có thể bị bỏ qua mãi. Marker phải đi với business transaction hoặc có state-machine/lease phục hồi.

**“SELECT xem key tồn tại rồi INSERT là đủ.”** Hai workers có thể cùng SELECT false; cần unique constraint/atomic claim và transaction isolation phù hợp.

**“Dùng MessageHeaders.ID làm khóa nghiệp vụ.”** Message được tạo lại sau restart có ID khác. Chọn stable business/event ID.

**“HTTP timeout nghĩa request chưa chạy.”** Partner có thể đã commit; phải dùng remote idempotency/lookup/reconciliation.

**“Kafka exactly-once tự bảo vệ database.”** Kafka transactions/idempotent producer có phạm vi riêng, không tự gộp external DB/HTTP/SFTP.

**“JMS/AMQP ack mode sẽ ngăn duplicate.”** Crash sau DB commit trước ack vẫn có redelivery; consumer phải idempotent.

**“Đổi eventId khi replay để hệ xử lý lại.”** Phá dedupe và có nguy cơ tạo side effect lặp; nếu cần điều chỉnh nghiệp vụ, tạo một **business action mới có version/approval**, không giả dạng duplicate cũ thành event mới.

**“Lease giữ độc quyền tuyệt đối.”** Worker cũ vẫn có thể tiếp tục sau lease expiry; cần fencing hoặc idempotency ở target.

**“Outbox bảo đảm chỉ publish một lần.”** Publish thành công nhưng mark SENT thất bại vẫn có thể gửi lại; receiver phải dedupe.

**“Xóa metadata store sau deploy giúp hệ bắt đầu sạch.”** Có thể gây replay hàng loạt và duplicate; thay đổi store cần migration và đối soát.

**“Đặt retention ngắn để tiết kiệm DB.”** Có thể hết dedupe window trước khi Kafka replay/DLQ thủ công; phải tính theo business contract.

**“Chỉ test graceful shutdown.”** OOM, SIGKILL và mất điện không chờ cleanup; phải test hard crash.

**“Một dấu PROCESSED cho cả file là đủ.”** Nếu file xử lý theo batches, restart giữa chừng cần per-row/checkpoint và handling partial success.

**“Chỉ giữ idempotency key, không kiểm tra payload.”** Same key/different payload có thể che dữ liệu thay đổi hoặc lỗi producer.

**“Khôi phục backup rồi restart consumer ngay.”** Backup có thể thiếu processed keys của events đã tác động bên ngoài; DR cần reconciliation trước replay.

**“Duplicate count phải bằng 0.”** Trong at-least-once delivery, duplicate nhận lại có thể hợp lệ; mục tiêu là **duplicate business effect = 0** trong phạm vi cam kết.

## 28. Câu hỏi ôn tập và tài liệu nền tảng

### 28.1. Câu hỏi tự kiểm tra

1. Vì sao restart gây duplicate ngay cả khi broker giữ đúng một record?
2. “Đã poll file” và “đã xử lý business” khác nhau như thế nào?
3. Cửa sổ crash nào làm mất message nếu upstream ack quá sớm?
4. Cửa sổ crash nào tạo redelivery nếu DB đã commit nhưng source chưa ack?
5. Tại sao `MessageHeaders.ID` không phải business idempotency key mặc định?
6. Khi same key nhưng payload khác, có nên trả `ALREADY_PROCESSED` không?
7. Một unique constraint giải quyết race nào mà SELECT trước INSERT không giải quyết?
8. Vì sao dedupe marker nên commit cùng business mutation khi dùng cùng database?
9. Inbox khác outbox về mục tiêu và vị trí trong flow như thế nào?
10. Outbox có loại bỏ duplicate Kafka publish hoàn toàn không?
11. Vì sao persistent file filter vẫn có thể dẫn tới mất nghiệp vụ sau restart?
12. `IdempotentReceiverInterceptor` có tự rollback HTTP side effect khi handler lỗi không?
13. Khi SFTP remote file đã được download nhưng DB chưa commit, recovery làm gì?
14. Với HTTP POST thành công nhưng response mất, tại sao retry cùng ID có thể vẫn chưa đủ nếu remote TTL đã hết?
15. JMS/AMQP redelivery xảy ra sau DB commit trước ack như thế nào?
16. Kafka offset có nên làm khóa business dedupe cho một event qua nhiều topics không?
17. Khi Kafka retry topic phá thứ tự revision, business xử lý thế nào?
18. Khi một JDBC lease hết hạn nhưng worker cũ tiếp tục, fencing có vai trò gì?
19. Vì sao `QueueChannel` in-memory không phải durable handoff?
20. Nếu trả HTTP 202 trước khi lưu inbox bền vững, restart có thể làm gì?
21. Những chỉ số nào chứng minh nhận nhiều lần nhưng chỉ một business effect?
22. Khi ledger retention hết trước source replay window, rủi ro nào xảy ra?
23. Khi nâng cấp canonicalization, vì sao có thể phát sinh false conflict?
24. Khi restore backup cũ, vì sao cần reconcile trước khi resume Kafka/file poller?
25. Một runbook replay an toàn cần kiểm tra gì về side effect, business version và authorization?

**Gợi ý:** Với mỗi câu hỏi, xác định **source identity → durable ingest → transaction commit → ack/checkpoint → outbound delivery → recovery** và tự hỏi “nếu pod chết ngay tại đây, event này sẽ được nhận lại ở đâu và được xử lý ra sao?”.

### 28.2. Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Idempotency** | Lặp cùng yêu cầu mà không tạo tác động nghiệp vụ lặp ngoài contract |
| **Stable business key** | Khóa không đổi qua retry, restart và replay |
| **Payload fingerprint** | Dấu vân tay nội dung semantic để phát hiện xung đột |
| **Deduplication ledger** | Bản ghi bền vững những logical events/operations đã xử lý |
| **Durable boundary** | Mốc dữ liệu/nghĩa vụ đã lưu đủ bền vững để có thể phục hồi |
| **Inbox** | Bản ghi nhận yêu cầu/sự kiện để xử lý có thể phục hồi |
| **Outbox** | Nghĩa vụ gửi sự kiện/command ghi cùng transaction với business |
| **At-least-once delivery** | Có thể nhận lại khi chưa xác nhận nguồn |
| **Ack / offset commit** | Xác nhận nguồn hoặc vị trí đã xử lý |
| **MetadataStore** | Store dùng cho state của integration components |
| **Accept-once filter** | Cơ chế hạn chế nhận lại item theo tiêu chí filter |
| **IdempotentReceiverInterceptor** | Interceptor nhận diện duplicate theo selector |
| **Lease / fencing token** | Quyền claim có hạn / bảo vệ chống worker đã mất quyền |
| **Unknown outcome** | Không biết chắc thao tác ở remote đã thành công chưa |
| **DLQ / DLT / quarantine** | Nơi cách ly message không thể xử lý trong đường bình thường |
| **Reconciliation** | Đối soát actual state giữa nguồn, DB, broker và partner |
| **Replay** | Phát lại dữ liệu đã có để xử lý/khôi phục |
| **Graceful shutdown** | Dừng nhận mới và xử lý inflight có kiểm soát |
| **Disaster recovery** | Phục hồi sau mất dữ liệu/hạ tầng, có thể cần tái tạo ledger |

### 28.3. Tài liệu nên đối chiếu theo phiên bản sử dụng

- **Spring Integration Reference Guide:** Idempotent Receiver, `IdempotentReceiverInterceptor`, `MetadataStoreSelector`, File/SFTP persistent filters, Message Channels, Polling Consumer, Error Handling, Message Stores và Endpoint Lifecycle.
- **Spring Framework/Spring Boot Reference:** Transaction Management, JDBC, declarative `@Transactional`, lifecycle, Actuator/Micrometer, graceful shutdown.
- **Spring for Apache Kafka Reference và Apache Kafka docs:** Consumer offsets/ack modes, error handling, DLT/retry topics, producer idempotence và transactional semantics trong phạm vi Kafka.
- **Spring AMQP/RabbitMQ Reference:** Acknowledgement, redelivery, DLX/DLQ, publisher confirms và listener recovery.
- **Jakarta Messaging/JMS specification và tài liệu broker provider:** Sessions, acknowledgement, transaction, durable queue, redelivery và DLQ.
- **PostgreSQL docs hoặc database vendor docs:** Transactions, unique constraints, `ON CONFLICT`, isolation, row locking, `SKIP LOCKED` và concurrency.
- **HTTP API partner contract:** Idempotency key TTL, status lookup, response semantics, retry và side-effect receipt.
- **SFTP/SSH client và server docs:** Accept-once metadata, host-key verification, rename/ready protocol, transfer integrity và file retention.

**Kết luận:** “Idempotent khi restart” không có nghĩa message chỉ được gửi hoặc nhận một lần. Nó có nghĩa hệ thống **có thể nhận lại, kiểm tra trạng thái bền vững và hoàn tất nghĩa vụ còn thiếu mà không lặp tác động nghiệp vụ**. Trong Spring Integration Adapters, hãy đặt idempotency ở đúng tầng, ghi business state với ledger trong transaction phù hợp, dùng inbox/outbox cho các ranh giới hệ thống, coi ack/offset/filter chỉ là trạng thái của nguồn, và kiểm chứng bằng crash tests, reconciliation cùng runbook trước khi đưa vào production.





