# Giám sát độ trễ, bản ghi kẹt và lỗi chuyển tiếp trong truyền sự kiện tin cậy

## Mục tiêu học tập

Giao tiếp bất đồng bộ làm cho request ban đầu có thể kết thúc trước khi công việc nghiệp vụ thực sự hoàn tất. Một Order Service có thể ghi Order(PENDING) và một bản ghi transactional outbox, trả 202 Accepted cho client, rồi relay chuyển sự kiện đến broker. Consumer Inventory tiếp nhận event, thực hiện reservation, lưu kết quả và phát event tiếp theo cho Order. Mỗi bước có thể thành công, chậm, thất bại hoặc rơi vào trạng thái không rõ.

Khi không giám sát đúng, hệ thống có thể trông khỏe ở API gateway vì mọi request trả 202 rất nhanh, trong khi hàng nghìn bản ghi outbox không được phát, consumer lag nhiều giờ, một số sự kiện bị retry vô hạn và người dùng nhìn thấy đơn hàng PENDING quá thời hạn. **Truyền sự kiện tin cậy không chỉ là không mất message; còn là phát hiện được công việc bị trì hoãn, biết chính xác nó đang mắc ở đâu, có cách phục hồi và đo thời gian đến kết quả nghiệp vụ cuối.**

Bài học tập trung vào:

- **Độ trễ (latency/lag):** Thời gian từ một mốc nghiệp vụ đến các mốc publish, delivery, processing và completion; phân biệt từng đoạn với end-to-end.
- **Bản ghi kẹt (stuck records):** Outbox, inbox, message, consumer offset hoặc business operation quá hạn/không có tiến triển dù chưa được đánh dấu kết thúc.
- **Lỗi chuyển tiếp (relay/forwarding failures):** Chuyển bản ghi outbox/CDC sang broker, broker giao cho consumer, consumer chuyển đến hệ thống đích hoặc công bố event tiếp theo thất bại.
- **Độ tin cậy khôi phục:** Retry có giới hạn, idempotency, DLQ, replay, reconciliation, supervision và runbook.

Sau bài học, người học có thể:

1. Mô tả được chuỗi trạng thái **business commit → outbox committed → relay attempted → broker acknowledged → consumer received → business effect committed → ACK/offset committed → workflow completed**.
2. Định nghĩa và đo **outbox age, publish delay, queue depth, consumer lag, oldest unprocessed age, processing time, end-to-end completion time** mà không nhầm các mốc.
3. Thiết kế schema trạng thái outbox/inbox với attemptCount, nextAttemptAt, lastError, lease/lock, publishedAt, correlationId và idempotency.
4. Phát hiện bản ghi kẹt bằng ngưỡng tuổi, tiến độ, retry, heartbeat/lease và số operation ở trạng thái trung gian quá lâu.
5. Phân loại lỗi transient, permanent, ambiguous outcome, poison message, throttling, serialization/schema, broker unavailable và dependency outage.
6. Dùng **metrics + structured logs + distributed tracing + audit status** để xác định điểm đứt gãy.
7. Thiết kế cảnh báo dựa trên **SLO và khả năng hành động**, có thời gian duy trì, ngưỡng theo mức ưu tiên và giảm nhiễu.
8. Thực hiện runbook recovery an toàn với at-least-once delivery, tránh nhân bản side effects khi replay/retry.
9. Kiểm thử failure injection: relay crash sau broker ACK, consumer commit trước ACK, CDC lag, network partition, backlog burst và stuck payment.
10. Viết ADR về các ngưỡng, kiến trúc quan sát và quy trình vận hành hệ thống event-driven.

**Ngữ cảnh:** Đây là bài thuộc nhóm **Truyền sự kiện tin cậy** của Software Design / System Architecture / Microservices. Ví dụ sử dụng Order–Inventory–Payment và mô hình transactional outbox + broker + consumer. Những tên bảng, topic, event và số liệu bên dưới là ví dụ, không phải tiêu chuẩn áp dụng nguyên trạng.

**Nguyên tắc:** Một message được ACK tại broker hoặc một HTTP response 202 **không đồng nghĩa nghiệp vụ đã hoàn tất**. Phải đo cả vận chuyển kỹ thuật lẫn tiến độ nghiệp vụ.

---

## 1. Đường đi đầy đủ của một sự kiện

Xét quá trình tạo đơn và giữ hàng:

~~~mermaid
sequenceDiagram
    participant U as User
    participant O as Order Service
    participant DB as Order DB + Outbox
    participant R as Outbox Relay
    participant B as Broker
    participant I as Inventory Consumer
    participant IDB as Inventory DB
    U->>O: POST /orders
    O->>DB: Transaction: Order PENDING + Outbox ReserveInventory
    DB-->>O: COMMIT OK
    O-->>U: 202 Accepted + orderId
    R->>DB: Claim bản ghi chưa publish
    DB-->>R: Outbox row
    R->>B: Publish ReserveInventory
    B-->>R: Publish acknowledged
    R->>DB: Mark published
    B->>I: Deliver message
    I->>IDB: Reserve idempotently + commit
    IDB-->>I: Commit OK
    I-->>B: ACK/commit offset
    Note over O,I: Kết quả InventoryReserved cần đến Order để hoàn thành workflow
~~~

Ở đây có nhiều mốc riêng biệt:

1. Request được nhận vào Order.
2. Transaction trong Order DB commit, lưu trạng thái và outbox.
3. Relay phát hiện bản ghi cần gửi.
4. Relay thực hiện một lần publish.
5. Broker phản hồi xác nhận theo cơ chế và cấu hình độ bền của nó.
6. Relay cập nhật trạng thái outbox.
7. Message được phân phối/đọc bởi consumer.
8. Consumer thực hiện side effect và commit trạng thái trong domain của mình.
9. Consumer ACK/commit offset.
10. Event kết quả được công bố, workflow chủ cập nhật trạng thái cuối.

**Không có một mốc ACK nào chứng minh mọi bước 1–10 đều đã xong.** Monitoring tốt phải có thước đo và ngữ nghĩa cho từng mốc.

### 1.1. Ba lớp thành công

| Lớp | Thành công khi nào? | Ví dụ |
|---|---|---|
| Acceptance | Yêu cầu đã được nhận và lưu theo contract | Order(PENDING) + outbox commit |
| Transport | Event đã được broker nhận/đọc theo acknowledgment semantics | Publish confirmed, delivery/offset progressed |
| Business completion | Domain owner đã commit outcome và workflow tới state đúng | Reservation RESERVED, Order CONFIRMED/REJECTED |

Nếu dashboard chỉ có metric HTTP 202 hoặc broker publish success, nó bỏ qua phần quan trọng nhất: **người dùng nhận được kết quả nghiệp vụ khi nào**.

### 1.2. Ba loại thời gian

**Thời gian hàng đợi:** Từ enqueue/commit đến lúc worker bắt đầu xử lý.

**Thời gian xử lý attempt:** Từ lúc worker bắt đầu đến lúc nó commit kết quả hoặc kết thúc attempt.

**Thời gian nghiệp vụ end-to-end:** Từ command được chấp nhận đến kết quả cuối, có thể bao gồm nhiều queue, retry và compensation.

Tránh dùng một metric có tên generic latency cho cả ba vì sẽ làm cảnh báo và chẩn đoán sai.

## 2. Định nghĩa mốc thời gian rõ trước khi xây metrics

Một event có thể mang:

~~~json
{
  "eventId": "EVT-501",
  "type": "ReserveInventory",
  "aggregateId": "O-101",
  "correlationId": "CORR-O-101",
  "causationId": "CMD-O-101",
  "occurredAt": "2026-11-11T10:00:00Z",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-101",
    "sku": "SKU-8",
    "quantity": 2
  }
}
~~~

Event metadata giúp tương quan nhưng cần phân biệt:

- **occurredAt:** Lúc sự kiện nghiệp vụ xảy ra, do owner định nghĩa.
- **outboxCreatedAt:** Lúc outbox row được tạo trong transaction, có thể trùng hoặc khác occurredAt.
- **committedAt:** Lúc transaction bền vững, nếu hệ thống có nguồn ghi nhận đáng tin.
- **firstAttemptAt/lastAttemptAt:** Mốc relay thử publish.
- **brokerAcceptedAt:** Mốc broker xác nhận publish, có thể không có field trực tiếp trong mọi nền tảng.
- **publishedAt:** Mốc relay đánh dấu xong; không phải bằng chứng tuyệt đối broker có hoặc chưa giao.
- **deliveredAt/receivedAt:** Mốc consumer nhìn thấy message.
- **processingStartedAt:** Mốc worker bắt đầu business handler.
- **businessCommittedAt:** Mốc side effect được commit.
- **ackedAt/offsetCommittedAt:** Mốc consumer xác nhận tiến độ với broker.
- **workflowCompletedAt:** Mốc Order hoặc workflow owner ghi terminal state.

Một luồng có thể cần timestamp tại nhiều service với đồng hồ không hoàn toàn đồng bộ. Khi tính duration **bên trong cùng một process**, ưu tiên monotonic clock. Khi so mốc xuyên máy, cần đồng bộ clock, ghi nhận sai số và không coi duration âm nhỏ là kết quả nghiệp vụ âm. Một số thông số nên đo từ broker/server ở một miền đồng hồ nhất quán hoặc ghi latency histogram tại nơi trực tiếp quan sát.

## 3. Các chỉ số độ trễ phải tách theo chặng

### 3.1. Outbox waiting age

Thời gian từ lúc một row đủ điều kiện publish tới thời điểm hiện tại khi nó còn đang pending:

~~~text
outbox_wait_age = now - eligibleAt
~~~

eligibleAt có thể là createdAt đối với row bình thường hoặc nextAttemptAt đối với một attempt được hoãn. **Không đánh mất originalCreatedAt**, vì retry liên tục không được xóa bằng chứng một operation đã tồn tại quá lâu.

Theo dõi:

- oldest unpublished outbox age;
- số outbox rows đang chưa publish;
- số row theo trạng thái PENDING, IN_PROGRESS, RETRY_WAIT, FAILED/QUARANTINED;
- rows tạo/giây so với rows publish thành công/giây.

### 3.2. Commit-to-publish latency

~~~text
commit_to_publish = brokerPublishConfirmedAt - businessCommittedAt
~~~

Đây là metric quan trọng của outbox relay. Nó phản ánh thời gian row chờ relay, thời gian retry, broker availability và tốc độ relay. Nếu không có committedAt đáng tin, dùng outboxCreatedAt và nêu rõ đây là approximation.

### 3.3. Broker-to-consumer delay

~~~text
broker_to_consumer = consumerReceivedAt - brokerAcceptedAt
~~~

Có thể dùng broker message timestamp, offset lag, queue delivery timestamp hoặc receivedAt tùy nền tảng. Không suy ra trực tiếp từ offset lag nếu tốc độ message thay đổi; 10.000 messages có thể là vài mili giây hoặc nhiều giờ tùy throughput.

### 3.4. Processing latency

~~~text
processing_attempt_duration = processingFinishedAt - processingStartedAt
~~~

Nên đo histogram p50/p95/p99 và phân tách outcome success, business rejection, transient failure. Nếu một message retry 10 lần, histogram từng attempt không thể thay cho **total business completion time**.

### 3.5. End-to-end event latency

~~~text
event_e2e_latency = businessEffectCommittedAt - originalBusinessEventAt
~~~

Với một workflow có nhiều events, cần thêm:

~~~text
operation_completion_time = terminalStateAt - operationAcceptedAt
~~~

Ví dụ trong Order–Payment, thời gian event tới Inventory được xử lý chỉ là một phần của thời gian Order CONFIRMED. Business SLO thường yêu cầu đo operation completion, không chỉ relay p99.

### 3.6. Phân biệt latency với lag/backlog

| Đại lượng | Ý nghĩa | Hạn chế |
|---|---|---|
| API acceptance latency | Request nhận vào nhanh không? | Không bảo đảm job chạy |
| Outbox depth | Bao nhiêu row chờ publish? | Không cho biết tuổi từng row |
| Oldest outbox age | Có row nào chờ quá lâu? | Một row poison có thể làm metric kéo dài |
| Publish success rate | Relay gửi thành công bao nhiêu? | Không chứng minh consumer xử lý |
| Broker queue depth | Bao nhiêu message đang chờ? | Có thể không gồm inflight/unacked |
| Kafka consumer lag | Offset chênh với log end | Không phải duration, không luôn tương đương xử lý xong |
| Oldest unprocessed message age | Message lâu nhất chưa hoàn thành đã tồn tại bao lâu? | Cần đo đúng semantics ACK/commit |
| Processing p99 | Handler chậm không? | Không gồm queue/retry wait |
| Stuck operations count | Bao nhiêu operation chưa terminal quá hạn? | Cần domain deadline và state model |
| Completion SLO | Tỷ lệ operation hoàn thành đúng hạn | Phải biết outcome và cohort |

**Quy tắc:** Cần ít nhất một metric về **độ già của công việc chưa hoàn thành**, không chỉ số lượng message.

## 4. Bài toán backlog: ví dụ tính toán

Giả sử:

- Producer tạo 900 sự kiện/giây.
- Relay hoặc consumer chỉ hoàn thành 600 sự kiện/giây.
- Tốc độ tăng tồn đọng lý tưởng: 300 sự kiện/giây.

Sau 5 phút:

~~~text
backlog_growth = (900 - 600) × 300 = 90.000 sự kiện
~~~

Nếu mọi event giữ nguyên payload trung bình 2 KB, nội dung payload tăng tương đương khoảng 180 MB, chưa tính replication, indexes, metadata và log storage.

Nếu producer giảm còn 200 event/giây trong khi consumer tiếp tục xử lý 600 event/giây:

~~~text
net_drain = 600 - 200 = 400 sự kiện/giây
time_to_drain = 90.000 / 400 = 225 giây (xấp xỉ)
~~~

Đây là mô hình đơn giản; latency DB, retry, partition skew và consumer restarts có thể kéo dài thời gian thực tế.

### 4.1. Vì sao depth = 0 chưa đủ?

Một queue depth thấp có thể do:

- Consumer đã đọc message nhưng giữ chúng unacked/inflight;
- Offset được commit quá sớm trước business transaction;
- Message bị drop theo retention/TTL mà workflow còn PENDING;
- Relay chưa từng publish nên broker hoàn toàn trống;
- Có event vào DLQ/parking lot thay vì main queue;
- Producer đã ngừng tạo events do lỗi app.

Do vậy dashboard cần nhìn **outbox → broker → consumer → workflow**, không chỉ một topic.

### 4.2. Đếm sự kiện tạo, phát, nhận và hoàn thành

Các counter từ nhiều service có thể không khớp 1:1 vì retry, duplicate, fan-out và nhiều consumer groups. Tuy nhiên nếu được gắn **event type, source, destination và logical operation** rõ, chúng giúp phát hiện điểm mất tiến độ.

Ví dụ:

~~~text
Outbox inserted:             10.000 events
Publish confirmed:           10.020 attempts
Unique events published:     10.000 events
Consumer delivery attempts:  10.030 attempts
Unique events processed:     10.000 events
Workflow terminals:           9.990 operations
Still pending:                   10 operations
~~~

Các số trên minh họa. Chênh 10 operations không nhất thiết do mất event: có thể là công việc còn trong deadline, chờ một bước nghiệp vụ hoặc cần compensation. Quan trọng là **xác định và giải thích được**.

## 5. Transactional outbox và những trạng thái cần quan sát

Outbox giúp tránh cửa sổ lỗi giữa commit domain transaction và publish event:

~~~text
BEGIN TRANSACTION
  INSERT Order(status = PENDING)
  INSERT Outbox(eventId, type, payload, status = PENDING)
COMMIT
~~~

Relay đọc outbox, publish tới broker, rồi cập nhật trạng thái. Nếu relay crash sau publish nhưng trước mark published, message có thể được publish lại. Vì vậy outbox cho phép **at-least-once-ish transfer theo cơ chế đảm bảo và cấu hình**, không tự tạo exactly-once side effect xuyên các hệ thống.

### 5.1. Schema outbox minh họa

~~~sql
CREATE TABLE outbox_events (
    id                VARCHAR(64) PRIMARY KEY,
    aggregate_id      VARCHAR(64) NOT NULL,
    event_type        VARCHAR(128) NOT NULL,
    schema_version    INT NOT NULL,
    payload_json      TEXT NOT NULL,
    correlation_id    VARCHAR(128),
    status            VARCHAR(32) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    next_attempt_at   TIMESTAMP NOT NULL,
    last_attempt_at   TIMESTAMP,
    published_at      TIMESTAMP,
    attempt_count     INT NOT NULL DEFAULT 0,
    last_error_code   VARCHAR(64),
    last_error_at     TIMESTAMP,
    lease_owner       VARCHAR(128),
    lease_until       TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL
);
~~~

Cột và kiểu dữ liệu chỉ minh họa; có thể cần event partition key, destination, headers, tenant ID, priority, payload reference, trace context và độ dài theo giới hạn storage thực.

### 5.2. State machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Business transaction commit
    PENDING --> IN_PROGRESS: Relay claim + lease
    IN_PROGRESS --> PUBLISHED: Broker ACK + state update
    IN_PROGRESS --> RETRY_WAIT: Transient failure
    RETRY_WAIT --> IN_PROGRESS: nextAttemptAt reached
    IN_PROGRESS --> QUARANTINED: Permanent failure / policy
    IN_PROGRESS --> PENDING: Lease expired + safe re-claim
    QUARANTINED --> RETRY_WAIT: Authorized repair + replay
    PUBLISHED --> [*]
~~~

Không nhất thiết mọi hệ thống dùng đủ các trạng thái. Nhưng phải trả lời được:

- Bản ghi này đã được commit lúc nào?
- Nó đã được relay claim chưa, ai đang giữ lease?
- Lần thử publish gần nhất khi nào, attempt thứ mấy?
- Có đang chờ backoff đúng policy hay bị kẹt?
- Broker đã xác nhận theo điều kiện durability nào?
- Có kết quả không rõ vì timeout sau khi broker có thể đã nhận?
- Ai có quyền sửa, replay hoặc đánh dấu quarantine?
- Bản ghi được dọn dẹp khi nào và lưu bằng chứng audit ở đâu?

### 5.3. Thời điểm đánh dấu published

Nếu relay cập nhật PUBLISHED **trước khi broker confirm**, crash giữa hai thao tác có thể làm mất message. Nếu relay cập nhật **sau khi broker confirm**, crash giữa hai thao tác có thể tạo duplicate. Thường ưu tiên tránh mất bằng cách có khả năng publish lại, kết hợp idempotent consumers.

**PUBLISHED chứng minh relay đã quan sát broker confirm và ghi nhận trạng thái**, không chứng minh mọi consumer đã xử lý hoặc workflow terminal.

## 6. Phát hiện bản ghi outbox bị kẹt

Không phải mọi record chưa publish đều kẹt. Một record có thể ở RETRY_WAIT theo backoff hợp lệ. Cần phân biệt **đúng lịch**, **đang tiến triển**, **hết lease**, **quá business deadline** và **không còn khả năng phục hồi tự động**.

### 6.1. Các tiêu chí gợi ý

Một row có thể bị nghi kẹt khi:

- status=PENDING và now-createdAt vượt ngưỡng SLO publish;
- status=IN_PROGRESS nhưng leaseUntil đã qua;
- attemptCount vượt ngưỡng và lastAttemptAt đã quá lâu;
- status=RETRY_WAIT nhưng now > nextAttemptAt + scheduling tolerance mà chưa có attempt mới;
- không có relay progress trong thời gian dài dù outbox depth tăng;
- event đã publish nhưng consumer business effect chưa xảy ra đúng hạn;
- tương quan với operation vẫn PENDING dù các thời hạn đã hết;
- record đi qua nhiều retries với cùng lỗi không hồi phục.

### 6.2. Ví dụ truy vấn phát hiện

~~~sql
SELECT id, event_type, aggregate_id, status,
       created_at, next_attempt_at, attempt_count,
       last_error_code, lease_owner, lease_until
FROM outbox_events
WHERE
      (status = 'PENDING'
       AND created_at < :publish_slo_cutoff)
   OR (status = 'IN_PROGRESS'
       AND lease_until < :now)
   OR (status = 'RETRY_WAIT'
       AND next_attempt_at < :overdue_cutoff)
ORDER BY created_at ASC
LIMIT 100;
~~~

Ví dụ minh họa, không phải truy vấn portable cho mọi DB. Có thể cần index phù hợp và hạn chế tần suất quét để monitoring không tự làm DB quá tải. Đặc biệt, record RETRY_WAIT chưa đến nextAttemptAt **không mặc nhiên stuck**, dù tuổi gốc cao; business SLO có thể vẫn yêu cầu cảnh báo nếu vượt thời hạn.

### 6.3. Truy vấn theo trạng thái và tuổi

~~~sql
SELECT status, COUNT(*) AS count_rows
FROM outbox_events
GROUP BY status;
~~~

~~~sql
SELECT MIN(created_at) AS oldest_pending_created_at
FROM outbox_events
WHERE status IN ('PENDING', 'RETRY_WAIT', 'IN_PROGRESS');
~~~

Nếu muốn đo **oldest age** chính xác và tránh chi phí full table scan, cân nhắc index hoặc aggregate theo bucket thời gian. Không biến một truy vấn monitoring rất nặng thành nguyên nhân khiến relay chậm hơn.

### 6.4. Lease và zombie workers

Nhiều relay instances có thể claim cùng nguồn dữ liệu. Nếu worker A giữ lease nhưng bị pause lâu, lease hết; worker B claim lại. Worker A hồi phục rồi tiếp tục publish; hệ thống có thể phát duplicate.

Dùng:

- Lease timeout phù hợp với thời gian xử lý;
- Heartbeat/renew nếu cần;
- Lock/row claim có transaction và fencing token/version khi cần bảo vệ cập nhật;
- Update trạng thái có điều kiện theo owner/version;
- Stable eventId và idempotent consumer;
- Kiểm soát shutdown/drain.

Lease ngăn nhiều worker đồng thời trong điều kiện thông thường nhưng không chứng minh exactly-once delivery. Sau timeout, trạng thái publish có thể không rõ.

## 7. Lỗi chuyển tiếp outbox → broker

### 7.1. Phân loại lỗi

| Lỗi | Ví dụ | Xử lý gợi ý |
|---|---|---|
| Network/connect timeout | Broker không kết nối được | Backoff + jitter, retry budget, quan sát |
| Broker unavailable | Cluster mất quorum hoặc leader | Ngừng gửi ồ ạt, retry có giới hạn, cảnh báo |
| Broker throttling | Quota/overload, phản hồi cần chậm | Tôn trọng quota, giảm publish rate |
| Authorization failure | Credential hết hạn, ACL topic sai | Cảnh báo cấu hình/bảo mật, không retry nóng vô hạn |
| Unknown destination | Topic/exchange không tồn tại | Quarantine hoặc sửa route, kiểm tra cấu hình |
| Serialization failure | Payload/schema không thể mã hóa | Quarantine, sửa dữ liệu/schema, replay |
| Payload quá lớn | Vượt message size | Điều chỉnh hợp đồng/payload, không retry lặp vô ích |
| Invalid partition key | Routing key không đúng contract | Sửa mapping và kiểm ordering |
| Publish ACK timeout | Broker có thể đã nhận hoặc chưa | Kết quả mơ hồ, retry với stable eventId |
| State update failure | Publish thành công, DB mark failed | Có thể publish trùng, cần dedup |
| CDC connector lag | Đọc log/offset chậm hoặc ngừng | Theo dõi connector offsets, checkpoint, retention |
| Outbox DB unavailable | Relay không đọc/claim được | Đánh giá DB health, không đánh dấu published giả |

### 7.2. Không retry mọi lỗi giống nhau

Lỗi network ngắn có thể hồi phục; lỗi schema không đúng có thể lặp mãi nếu dữ liệu không được sửa. Cần policy retry theo error code và có giới hạn:

- transient: exponential backoff + jitter;
- throttled: respect retry-after hoặc quota policy;
- ambiguous: stable eventId, status lookup nếu có;
- permanent: quarantine/DLQ tương ứng, cảnh báo owner;
- security: sửa credential/ACL, không nới quyền bừa bãi;
- business deadline expired: xử lý state machine và reconciliation.

### 7.3. Broker ACK không đơn nghĩa “đã được lưu bền”

Bảo đảm xác nhận phụ thuộc công nghệ, cấu hình replication/acks/durability và failure modes. Nếu producer chỉ xác nhận gửi tới socket hoặc nhận một acknowledgment quá yếu, message vẫn có thể mất trong một số sự cố. Monitoring cần biết ý nghĩa **publishConfirmed** trong môi trường cụ thể.

### 7.4. Publisher retry có thể nhân tải

Nếu broker chậm và mỗi relay worker retry ngay không backoff, rất nhiều event có thể được gửi đồng thời khi broker hồi phục. Cần hạn chế outbound concurrency, batch size, retry budget, ramp-up và global rate control. Broker trở lại hoạt động không có nghĩa nó chịu được toàn bộ backlog được xả trong một giây.

## 8. CDC relay: các điểm đo bổ sung

Transactional outbox có thể được phát qua polling relay hoặc Change Data Capture (CDC). Với CDC, connector đọc database log rồi chuyển sự kiện sang broker.

~~~mermaid
flowchart LR
    DB[("Domain DB + Outbox")] --> LOG["Transaction Log / CDC"]
    LOG --> CON["CDC Connector"]
    CON --> B[("Event Broker")]
    B --> C["Consumers"]
~~~

Cần giám sát thêm:

- Database log position/LSN hoặc nguồn checkpoint tương ứng;
- Connector source offset;
- Thời gian từ DB commit đến connector đọc được;
- Thời gian connector giữ record trước khi publish;
- Connector status RUNNING/PAUSED/FAILED;
- Task restarts và lỗi parsing/schema;
- Log retention còn đủ cho connector bắt kịp không;
- Snapshot/backfill status;
- Destination topic write errors;
- CDC event ordering và partitioning;
- Có bỏ qua những thay đổi cần thiết khi connector restart hoặc schema evolution không.

**CDC connector “RUNNING” không chứng minh nó có tiến triển.** Có thể connector vẫn sống nhưng không advance source offset, bị kẹt vào một record poison hoặc topic permissions sai. Vì vậy đo **last successful record/offset/time** và oldest unprocessed age.

### 8.1. Không suy ra liveness từ heartbeat duy nhất

Heartbeat đều đặn có thể chứng minh process/connection còn hoạt động, nhưng nếu production change log đang có dữ liệu mà source offset không tiến, pipeline vẫn kẹt. Cần kết hợp:

- Is connector alive?
- Is source producing data?
- Is connector consuming/advancing?
- Is destination receiving/acknowledging?
- Is downstream consumer processing?

Nếu nguồn thật sự không có events, “0 throughput” là bình thường. Alert phải xét arrival rate và trạng thái kỳ vọng của workload.

## 9. Broker → consumer: queue depth, lag, offset và ACK

### 9.1. Với queue kiểu push

Một queue có thể có:

- ready messages chờ giao;
- unacked/inflight messages đã giao nhưng chưa ACK;
- redelivery count;
- consumer count;
- oldest ready age;
- dead-letter count;
- delivery rate và ack rate.

Nếu ready depth thấp nhưng unacked rất cao, worker có thể đang giữ quá nhiều message hoặc processing chậm. Không cho rằng queue đã được xả.

### 9.2. Với log-based broker như Kafka

Cần theo dõi:

- log-end offset và consumer committed offset theo partition/group;
- consumer lag theo partition;
- tốc độ tăng log-end và tốc độ commit;
- thời gian consumer không poll/không commit;
- rebalances, assignment changes;
- consumer processing/commit errors;
- message event-time age hoặc processing-time delay;
- hot partition/poison record;
- retention và khả năng consumer bắt kịp.

**Offset lag không tự là thời gian.** 5.000 records có thể tương ứng 0,5 giây ở throughput 10.000/s hoặc nhiều giờ ở stream thưa. Cần age metric hoặc ước tính có điều kiện.

### 9.3. ACK/offset commit semantics

Nếu consumer ACK/commit offset **trước** business commit, crash sau ACK có thể làm mất công việc. Nếu consumer commit domain state **trước** ACK, crash giữa hai bước có thể gây redelivery; cần idempotency.

Một lý tưởng:

~~~text
Receive message
  → Validate contract
  → Check duplicate / operation state
  → Commit domain effect + processed marker (+ outbox)
  → ACK/commit offset
~~~

Không phải broker nào cũng hỗ trợ một atomic transaction với external DB. Vì vậy cần chấp nhận khả năng redelivery và thiết kế handler chịu được.

### 9.4. Một poison message có thể giữ partition kẹt

Nếu consumer phải xử lý theo thứ tự trong một partition, event có schema sai hoặc handler liên tục exception có thể chặn những records sau nó.

Giải pháp cần cân nhắc:

- Retry hạn chế cho lỗi transient;
- Quarantine/DLQ cho lỗi permanent;
- Không “bỏ qua để chạy tiếp” nếu sequencing và domain invariant yêu cầu xử lý record đó;
- Đảm bảo event lỗi vẫn có business owner, audit và recovery plan;
- Cho phép replay sau sửa bug, không phá idempotency.

Không có quy tắc duy nhất cho mọi event type: analytics có thể chấp nhận bỏ một event theo policy, PaymentCaptured thường không.

## 10. Bản ghi kẹt ở consumer và workflow

Một event có thể rời outbox và được broker giao, nhưng business operation vẫn không tiến triển.

Ví dụ:

~~~text
Order PENDING
  → InventoryReserved
  → PaymentCommand queued
  → Payment provider đã charge
  → Payment consumer timeout trước khi ghi kết quả
  → Order vẫn PAYMENT_PENDING
~~~

Đây là **stuck business operation** ngay cả khi broker queue depth bằng 0 hoặc message đã ACK nhầm. Muốn nhận diện, workflow owner phải lưu state và thời gian chuyển trạng thái.

### 10.1. Business state với updatedAt và deadline

~~~text
ORDER_PENDING:
    acceptedAt
    lastTransitionAt
    expectedNextEvent
    deadlineAt
    retryPolicyReference
    correlationId
    lastKnownOutcome
~~~

Tạo một scanner hoặc workflow monitor:

~~~text
find operations where
  state not in TERMINAL_STATES
  and now > stateDeadlineAt
~~~

Các terminal states có thể là CONFIRMED, REJECTED, CANCELLED, FAILED_CLOSED theo contract. Một trạng thái REVIEW_REQUIRED có thể chưa phải terminal nếu cần người xử lý. **“Quá hạn” không đồng nghĩa “thất bại chắc chắn”** khi đã có external side effect chưa rõ.

### 10.2. Thiết kế state machine recovery

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING
    PROCESSING --> COMPLETED: Domain outcome committed
    PROCESSING --> RETRY_WAIT: Transient failure
    RETRY_WAIT --> PROCESSING: Retry due
    PROCESSING --> REVIEW_REQUIRED: Ambiguous outcome
    REVIEW_REQUIRED --> COMPLETED: Reconciled success
    REVIEW_REQUIRED --> FAILED: Reconciled failure
    PROCESSING --> COMPENSATING: Business rollback needed
    COMPENSATING --> CANCELLED: Compensation complete
    COMPENSATING --> REVIEW_REQUIRED: Compensation uncertain
~~~

Không chuyển REVIEW_REQUIRED thành FAILED chỉ vì một timer hết hạn nếu Payment provider có thể đã charge. Phải query theo stable operationId/idempotency key hoặc đối soát dữ liệu kết quả.

### 10.3. Stuck detection cần biết loại công việc

- Notification có thể chậm vài phút mà không ảnh hưởng OrderConfirmed;
- Inventory reservation cần kết quả trước reservation expiry;
- Payment cần bảo đảm không duplicate charge;
- Audit event không được mất theo policy;
- Export report có thể mất hàng chục phút;
- Telemetry có thể cho phép sampling/drop.

Một ngưỡng “mọi message trên 30 giây là stuck” thường gây false positives. SLO phải theo event type, destination, priority và business deadline.

## 11. Metrics cần phát ra ở producer/outbox/relay

### 11.1. Counter

Gợi ý tên logic:

~~~text
outbox_events_created_total
outbox_publish_attempts_total{outcome=success|failure}
outbox_publish_confirmed_total
outbox_state_transitions_total{from,to}
outbox_retry_scheduled_total{reason}
outbox_quarantined_total{reason}
relay_errors_total{class}
relay_claim_conflicts_total
relay_lease_expirations_total
~~~

Label ví dụ nên chứa **service, eventType, destination, errorClass, outcome** với tập giá trị được kiểm soát. Không đưa eventId, orderId, correlationId, userId hoặc exception message tùy ý làm metric labels vì cardinality cao.

### 11.2. Gauge

~~~text
outbox_pending_records
outbox_retry_wait_records
outbox_in_progress_records
outbox_quarantined_records
outbox_oldest_pending_age_seconds
outbox_overdue_records
relay_active_workers
relay_last_success_age_seconds
relay_last_progress_age_seconds
~~~

Gauge last-success age cần được diễn giải theo arrival: nếu không có events trong nhiều giờ, không có publish success là bình thường. Có thể dùng một synthetic heartbeat/event riêng ở nơi yêu cầu pipeline liên tục, nhưng heartbeat cũng phải đi qua **cùng đường dữ liệu** nếu muốn kiểm chứng end-to-end.

### 11.3. Histogram

~~~text
outbox_commit_to_publish_seconds
relay_publish_attempt_seconds
broker_publish_ack_seconds
outbox_claim_wait_seconds
relay_retry_delay_seconds
~~~

Đo latency distribution theo SLO phù hợp. P99 chỉ của các event đã publish có thể che những event **chưa bao giờ được publish**. Kết hợp histogram với oldest pending age và overdue count.

### 11.4. Sử dụng createdAt thay requestId để đo age

Để tính oldest age, cần nguồn timestamp tương đối đáng tin. Bản ghi createdAt có thể là mốc đủ tốt nếu dùng DB time, nhưng phải hiểu sai lệch clock giữa DB và monitoring process. Thực tế có thể dùng SQL age tính ở DB rồi export như gauge để giảm drift.

## 12. Metrics ở broker và consumer

Gợi ý:

~~~text
broker_messages_published_total
broker_publish_failures_total
broker_queue_ready_messages
broker_queue_unacked_messages
broker_oldest_unprocessed_age_seconds
consumer_lag_records{topic,partition,group}
consumer_received_total
consumer_processing_attempts_total{outcome}
consumer_processed_unique_total
consumer_retries_total{reason}
consumer_dlq_total{reason}
consumer_processing_duration_seconds
consumer_queue_wait_seconds
consumer_last_progress_age_seconds
consumer_ack_failures_total
consumer_rebalances_total
~~~

**Lưu ý:** Tên, khả năng đo và định nghĩa metric phụ thuộc broker/client. Kafka consumer lag thường là record/offset based; RabbitMQ ready/unacked là queue state; cloud queues có approximate counts và age metrics. Không giả định chúng tương đương tuyệt đối.

### 12.1. Đo processed success, không chỉ poll rate

Một consumer poll được 1.000 records/s nhưng chỉ xử lý bền vững 100 records/s có thể tạo một backlog **in-process** hoặc ACK sai. Chỉ số quan trọng là unique logical operations successfully committed/s và age của công việc chưa hoàn thành.

### 12.2. Throughput và attempt count khác nhau

At-least-once delivery có thể tạo duplicates. Nếu mỗi event retry 5 lần, attempts/s tăng nhưng số events hoàn thành/s không tăng. Theo dõi unique eventId/operationId (ở logs/store; metrics đếm aggregate), tỷ lệ duplicate detected và retry amplification.

### 12.3. Partition skew

Có thể tổng consumer lag vừa phải nhưng một partition cụ thể lag rất cao vì một hot key, poison record hoặc worker bị nghẽn. Dashboard cần phân tích theo partition/consumer group ở mức vận hành, không chỉ aggregate.

## 13. Tracing xuyên ranh giới async

Một distributed trace request đồng bộ dễ nối qua HTTP headers. Với async:

~~~mermaid
flowchart LR
    A["POST /orders\ntrace A"] --> B["Order DB commit"]
    B --> C["Outbox Relay\ntrace/span B"]
    C --> D["Broker"]
    D --> E["Inventory Handler\ntrace/span C"]
    E --> F["Inventory DB commit"]
    F --> G["InventoryReserved event"]
    G --> H["Order workflow transition"]
~~~

Traces có thể cần **context propagation**, span links hoặc correlation attributes để liên kết những quá trình diễn ra sau nhiều giây/phút hoặc sau restart.

### 13.1. Các định danh nên phân biệt

- **traceId:** Liên kết spans theo tracing system.
- **spanId:** Định danh một thao tác trong trace.
- **correlationId:** Liên kết chuỗi hoạt động của cùng business workflow.
- **causationId:** Chỉ ra command/event nào dẫn tới message hiện tại.
- **eventId/messageId:** Định danh message để dedup/audit.
- **operationId/orderId:** Định danh nghiệp vụ ổn định.
- **attemptNumber:** Lần thử publish/process.
- **destination/topic/partition:** Ngữ cảnh tuyến vận chuyển.
- **schemaVersion:** Hỗ trợ chẩn đoán compatibility.

Không dùng orderId làm traceId mặc định; hai identifier có vòng đời, quyền dữ liệu và semantics khác nhau. Có thể liên kết chúng bằng attribute có kiểm soát.

### 13.2. Vì sao trace sampling có thể che lỗi hiếm?

Nếu chỉ sample 1% traces ngẫu nhiên, một event kẹt hiếm có thể không có trace đầy đủ. Cần kết hợp:

- Metrics luôn-on và được aggregate;
- Structured logs có correlationId;
- Tail-based sampling có khả năng giữ error/slow traces nếu nền tảng hỗ trợ;
- Durable operation/outbox status để điều tra;
- Audit records cho workflow nhạy cảm.

Không coi tracing là nguồn chân lý duy nhất về business completion; traces có thể bị drop, retention hạn chế hoặc không kết nối được mọi async spans.

### 13.3. Ví dụ structured log

~~~text
timestamp=2026-11-11T10:01:00Z
service=order-outbox-relay
eventId=EVT-501
correlationId=CORR-O-101
operationId=O-101
stage=broker_publish
attempt=3
destination=inventory.commands
outcome=FAILED
errorClass=BROKER_TIMEOUT
retryAt=2026-11-11T10:01:30Z
durationMs=850
~~~

Log đủ để truy vết, nhưng không nên ghi access token, toàn bộ dữ liệu nhạy cảm của payment/customer, connection secrets hay các thông tin không cần thiết. EventId/correlationId có thể xuất hiện ở logs nhưng không nên là metric labels.

## 14. Thiết kế dashboard theo pipeline

Một dashboard tốt cần kể được câu chuyện “dữ liệu đang mắc ở đoạn nào”.

### Bảng chính

| Panel | Metric chính | Câu hỏi |
|---|---|---|
| Ingress | Business accepted/s | Có bao nhiêu operation được nhận? |
| Outbox | Created/s vs confirmed published/s | Relay có theo kịp không? |
| Outbox age | Oldest pending + p95 commit-to-publish | Event nằm chờ bao lâu? |
| Relay | Attempts, success, error classes, lease expiries | Lỗi chuyển tiếp do đâu? |
| Broker | Queue depth/lag, oldest message age, storage | Broker đang tích lũy hay bị nghẽn? |
| Consumer | Unique processed/s, processing p99, in-flight | Consumer có thực sự hoàn thành? |
| Retry/DLQ | Retries, quarantined, DLQ age | Có message không tự phục hồi? |
| Workflow | Stuck operations, completion SLO | Người dùng có nhận kết quả đúng hạn? |
| Dependencies | DB latency, 429, network/TLS failures | Nút thắt nằm ở đâu? |
| Recovery | Backlog drain rate, reconciliation count | Hệ thống có phục hồi sau outage không? |

### 14.1. Mỗi panel nên có chiều thời gian

Tức thời depth=1.000 không rõ bình thường hay quá tải. Nếu nó tăng từ 0 lên 1.000 rồi giảm nhanh, có thể là burst lành mạnh. Nếu 1.000 không đổi nhưng oldest age tăng 20 phút, pipeline có thể bị kẹt. Cần trend **arrival vs completion**, age và last progress.

### 14.2. Business criticality

Tách dashboard/alert theo event class:

- Payment/Inventory commands;
- Order state transitions;
- Notification;
- Analytics;
- Search projection;
- Audit/security events.

Mức độ ưu tiên và thời hạn khác nhau. Không để hàng triệu telemetry events che mất 10 payment operations chưa rõ kết quả.

### 14.3. Tránh alert từ metrics không có data

Khi exporter mất kết nối, metric có thể biến mất và dashboard trông giống zero. Phải giám sát cả **metric availability, scraper/up status, heartbeat và last sample timestamp**. “0 pending” từ dữ liệu thiếu không chứng minh pipeline đã xả xong.

## 15. Đặt SLO cho event delivery

Một SLO tốt có đối tượng và thời hạn rõ:

~~~text
SLO A:
99.9% ReserveInventory outbox events được broker xác nhận
trong 10 giây kể từ commit, tính theo cohort event đã commit.

SLO B:
99.5% ReserveInventory commands được Inventory xử lý
trong 30 giây kể từ khi Order chấp nhận yêu cầu.

SLO C:
99.0% Orders đạt terminal business state
trong 2 phút kể từ acceptance, trừ loại workflow có ngoại lệ công bố.
~~~

Các con số là minh họa. Cần đo baseline và đàm phán theo business requirements, không chọn tùy ý.

### 15.1. Numerator và denominator

Nếu chỉ đo histogram của events **đã được publish**, những events kẹt mãi không bao giờ được tính vào mẫu, khiến p99 giả đẹp.

Định nghĩa nên theo **cohort đã tạo/được chấp nhận**:

~~~text
good = số events được publish trong hạn
eligible = số events đã commit đủ lâu để đánh giá deadline
SLO = good / eligible
~~~

Tương tự completion SLO phải xét các operations đã đủ thời gian để quan sát, kể cả những operation vẫn PENDING.

### 15.2. Ngưỡng alert theo SLO

Có thể kết hợp:

- **Fast burn:** Tỷ lệ vi phạm SLO cao trong cửa sổ ngắn;
- **Slow burn:** Vi phạm tích lũy kéo dài;
- **Oldest pending age:** Có records vượt thời hạn;
- **Stuck operations count:** Một số operation giá trị cao bị kẹt;
- **Complete outage:** Trong khi event creation vẫn tăng, publish/processing progress dừng.

Một alert tốt chỉ bắn khi có hành động rõ: giảm intake, kiểm tra relay, mở runbook DLQ, đối soát Payment hoặc rollback config.

### 15.3. Hysteresis và thời gian duy trì

Nếu queue age dao động quanh một ngưỡng, alert mỗi phút rồi tự khỏi dễ gây mệt mỏi. Có thể yêu cầu ngưỡng vượt trong 5 phút, chọn warning/critical theo tuổi và rate tăng, cùng hysteresis để chỉ clear sau khi backlogs giảm ổn định. Với workflow thanh toán giá trị cao, alert theo một operation quá hạn nghiêm trọng vẫn có thể cần ngay.

### 15.4. Một alert không được che một sự cố khác

Không cấu hình alert chỉ khi depth > 1000. Một poison message duy nhất kẹt 2 giờ có depth=1 nhưng vẫn đáng cảnh báo. Cần điều kiện **oldest age** và **per-operation deadline** riêng.

## 16. Lỗi relay phổ biến và triệu chứng

### 16.1. Broker outage

**Triệu chứng:** Outbox pending tăng, oldest age tăng, publish failures nhiều, attempts tăng; broker connections fail.

**Xử lý:** Xác minh broker health và quota, giảm producer admissions nếu completion SLO nguy cơ vỡ, backoff relay, tránh retry storm. Khi broker hồi phục, xả backlog có giới hạn và theo dõi duplicate handling.

### 16.2. Sai topic/ACL

**Triệu chứng:** Nhiều lỗi authorization/unknown topic, thường bắt đầu sau deploy/config change, không có publish confirmations dù network hoạt động.

**Xử lý:** So sánh cấu hình version, quyền principal, destination mapping và schema; rollback/sửa. Không cấp quyền wildcard cho mọi topic chỉ để bỏ lỗi.

### 16.3. Một event không serialize được

**Triệu chứng:** Một id/event type có attempts tăng đều và cùng lỗi, những event khác vẫn publish.

**Xử lý:** Quarantine event, ghi lastErrorClass, giữ payload an toàn, xác minh schemaVersion; sửa producer/serializer hoặc migration; replay có kiểm soát. Không xóa row khỏi outbox để “số pending về 0”.

### 16.4. Relay mất lease

**Triệu chứng:** IN_PROGRESS rows có leaseUntil trong quá khứ, worker heartbeat ngừng, một số row bị claim lặp.

**Xử lý:** Kiểm process/DB locks, lease TTL, worker pause và concurrency. Re-claim có điều kiện, chấp nhận khả năng duplicate publish; consumer idempotent.

### 16.5. Publish thành công nhưng mark published lỗi

**Triệu chứng:** Broker có message, outbox vẫn PENDING/IN_PROGRESS và có thể retry lại.

**Xử lý:** Không giả định message chưa gửi. Relay có thể thử lại với cùng eventId; consumer dedup. Nếu broker hỗ trợ truy vấn trạng thái bằng key phù hợp, có thể dùng để điều tra nhưng không biến nó thành transaction xuyên hệ thống.

### 16.6. CDC connector đứng im

**Triệu chứng:** Source DB vẫn có commits/outbox rows nhưng connector offset không advance; outbox age tăng; connector có thể vẫn báo RUNNING.

**Xử lý:** Kiểm snapshot/cdc task status, source log retention, permission, schema change, destination errors, retries. Không reset offsets mù vì có thể bỏ records hoặc replay ngoài dự kiến.

### 16.7. Consumer lag do downstream DB

**Triệu chứng:** Broker publish ổn nhưng lag và oldest message age tăng; processing duration p99 tăng; DB locks/pool saturation.

**Xử lý:** Giảm concurrency nếu contention, tối ưu transaction/index, kiểm hot key, rate limit producer nếu cần; không chỉ scale consumer khiến DB càng nghẽn.

### 16.8. DLQ tích lũy

**Triệu chứng:** Main queue có vẻ thông suốt nhưng DLQ count/oldest age tăng; business operations PENDING.

**Xử lý:** Phân nhóm theo errorClass/schemaVersion, tìm owner, sửa nguyên nhân, replay idempotently với quota, đối soát state. DLQ không phải nơi “đưa vào là xong”.

## 17. Retry, DLQ và parking lot

Một message có thể lỗi tạm thời do DB timeout, lỗi vĩnh viễn do schema không tương thích hoặc kết quả mơ hồ do external side effect. Retry policy nên dựa trên loại lỗi.

### 17.1. Retry có giới hạn

~~~text
attempt 1: ngay khi đủ điều kiện
attempt 2: sau 1 giây + jitter
attempt 3: sau 5 giây + jitter
attempt 4: sau 30 giây + jitter
attempt 5: sau 2 phút + jitter
sau đó: quarantine/reconcile theo contract
~~~

Thời gian chỉ minh họa. Cần maxAttempts, maximum elapsed time, business deadline và retry budget theo event type. Khi downstream trả Retry-After, tôn trọng chỉ dẫn phù hợp. Không để producer, gateway, relay và consumer cùng retry không phối hợp làm attempts bùng nổ.

### 17.2. DLQ không thay business recovery

Message vào DLQ có thể được lưu để xử lý sau, nhưng workflow owner vẫn cần biết operation nào chưa terminal. Một payment event ở DLQ không được coi tự động là FAILED nếu charge có thể đã xảy ra.

### 17.3. Parking lot/quarantine

Với lỗi không thể giải quyết tự động:

- Lưu eventId, operationId, destination, schemaVersion;
- Ghi class lỗi, thời điểm, attempts;
- Bảo vệ payload chứa dữ liệu nhạy cảm;
- Xác định owner/runbook;
- Có quy trình sửa và replay;
- Ghi audit ai thực hiện và lý do;
- Có chỉ số age của bản ghi quarantine;
- Không cho replay trùng side effect.

### 17.4. Retry storm

Một broker outage vài phút có thể khiến hàng triệu events chờ. Nếu tất cả retries đến đúng phút thứ 5, broker hoặc DB bị quá tải ngay khi hồi phục. Cần jitter, per-destination token bucket/concurrency limits, phased recovery và rate ramp-up.

## 18. Idempotency và kết quả không chắc chắn

**At-least-once delivery** có thể phát một event nhiều lần. Theo dõi duplicate count là hữu ích, nhưng mục tiêu là ngăn **business side effect trùng**.

### 18.1. Stable eventId và operationId

- eventId: định danh một event cụ thể, dùng dedup khi redelivery/publish lặp;
- operationId: định danh một logical business command (một charge/reservation) qua nhiều attempts;
- correlationId: nối toàn bộ workflow;
- causationId: chỉ ra message gây event.

Một eventId khác nhưng cùng operationId có thể vẫn yêu cầu business idempotency để không tạo giao dịch trùng.

### 18.2. Consumer inbox/dedup

~~~sql
BEGIN;

INSERT INTO processed_events(event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP);
-- Khi trùng unique key: xử lý theo semantics "already processed".

UPDATE inventory_reservations
SET status = 'RESERVED'
WHERE reservation_id = :reservation_id
  AND status = 'PENDING';

INSERT INTO outbox_events (... InventoryReserved ...);

COMMIT;
~~~

Đây là pseudocode SQL. Thực tế phải xử lý duplicate conflict rõ và tránh việc cùng command tạo nhiều outbox events trong transaction khác. Sử dụng khóa uniqueness và state transition guard theo domain.

### 18.3. Crash sau commit trước ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Consumer DB
    B->>C: Event E
    C->>DB: Commit business state + processed E
    DB-->>C: Success
    Note over C: Crash trước ACK
    B->>C: Redeliver E
    C->>DB: Check processed E
    DB-->>C: Already done
    C-->>B: ACK
~~~

Một metric delivery attempts có thể tăng, nhưng business completed unique count không tăng lại. Monitoring phải phân biệt duplicate delivery là expected recovery với duplicate side effect là sự cố nghiêm trọng.

### 18.4. Timeout sau external side effect

Payment provider có thể charge thành công rồi connection timeout. Consumer không thể chỉ retry với key mới vì dễ charge hai lần. Cần:

- Stable idempotency key nếu provider hỗ trợ;
- Query transaction status;
- Reconciliation;
- State REVIEW_REQUIRED/UNKNOWN;
- Alert khi outcome không rõ quá hạn;
- Audit của người can thiệp;
- Không tự đánh dấu PAYMENT_FAILED chỉ vì HTTP timeout.

## 19. Reconciliation: lớp bảo đảm cuối cùng

Một số sự cố không thể suy ra chỉ từ broker metrics:

- Event đã được ACK sai trước DB commit;
- Outbox row mất do lỗi migration;
- Consumer ghi DB nhưng event kết quả không publish;
- Một operation bị stale ở Order dù Payment đã hoàn tất;
- DLQ chứa event quan trọng chưa được replay;
- Business idempotency store ghi thiếu;
- CDC connector bỏ qua một khoảng log do retention.

**Reconciliation** đối chiếu nguồn sự thật hoặc trạng thái các bên để tìm sai lệch và đưa workflow về trạng thái đúng.

### 19.1. Đối soát Operation

Ví dụ:

~~~text
Order O-101 = PAYMENT_PENDING quá 10 phút
Payment lookup(operationId=O-101) = AUTHORIZED
Inventory reservation = RESERVED

Action:
  xác minh ownership và contract
  ghi state transition hợp lệ ở Order
  phát OrderConfirmed nếu chưa có
  audit reconciliation
~~~

Nếu Payment lookup không có kết quả nhưng provider có thể đang xử lý bất đồng bộ, không kết luận FAILED quá sớm. Recovery có thể cần chờ hoặc điều tra.

### 19.2. Đối soát Outbox

Có thể định kỳ tìm Orders ở PENDING nhưng không có outbox command tương ứng, hoặc những outbox events đã publish nhưng workflow chưa tiến triển. Cần xác định mối liên hệ giữa business state, outbox rows và downstream outcomes.

### 19.3. Không sửa DB thủ công thiếu contract

Một thao tác UPDATE order SET status='CONFIRMED' trong production có thể bỏ qua invariant, audit và event cần phát. Runbook nên dùng domain repair command hoặc transaction được owner kiểm soát, lưu idempotency/audit.

### 19.4. Mức độ ưu tiên

- Payment/financial mismatch: cảnh báo cao, kiểm tra không charge/refund trùng;
- Inventory reservations quá hạn: xử lý compensation/release;
- Notification delay: retry trong giới hạn, không đảo trạng thái OrderConfirmed;
- Analytics projection lag: xác nhận eventual consistency và lịch backfill.

## 20. Runbook: khi oldest outbox age tăng

**Mục tiêu:** Tìm đúng nguyên nhân, bảo vệ dữ liệu và khôi phục mà không tạo duplicate side effects.

### Bước 1 — Xác nhận sự cố

Kiểm tra:

- Outbox pending depth và oldest age tăng liên tục hay chỉ burst;
- Created/s và published unique/s;
- Relay last progress;
- Error classes, retry rate, lease expires;
- Broker health, quota, disk/replication;
- Mức ảnh hưởng theo eventType, tenant, destination và zone.

Không chỉ nhìn một gauge vì exporter có thể stale.

### Bước 2 — Xác định đoạn kẹt

~~~text
Outbox created > published?
  → Relay hoặc broker publish path

Outbox published bình thường, consumer lag tăng?
  → Broker delivery hoặc consumer processing

Consumer progress bình thường, workflow vẫn PENDING?
  → Result event, state transition hoặc reconciliation path
~~~

### Bước 3 — Chặn khuếch đại tải

Giảm retry storms, giới hạn relay publish concurrency, tôn trọng broker quotas; nếu completion SLO nguy hiểm, điều chỉnh admission policy ở producer/API. Không đơn thuần tăng replica relay nếu broker/DB đã saturation.

### Bước 4 — Sửa nguyên nhân

Ví dụ: credentials, routing, broker outage, serializer regression, DB index, poison event, CDC connector checkpoint. Dùng deploy/rollback có kiểm soát; không xóa pending rows để làm metric xanh.

### Bước 5 — Xả backlog có kiểm soát

Tăng publish rate dần khi broker và consumers có capacity; theo dõi age, consumer lag, error rate, DB p99 và duplicates. Nếu consumer vẫn chậm hơn producer, backlog sẽ không tự giảm.

### Bước 6 — Đối soát

Tìm operations quá hạn, payment outcomes không rõ, event kết quả thiếu và cần compensation. Chứng minh business terminal states đúng.

### Bước 7 — Kết thúc và ghi nhận

Lưu timeline, root cause, số bản ghi ảnh hưởng, thời gian violation, actions, khối lượng replay/reconciliation và preventive fixes. Kiểm tra alert có phát đúng người/đúng thời điểm không.

## 21. Runbook: bản ghi stuck một mình

Một outbox row EVENT-789 ở RETRY_WAIT hơn một giờ, trong khi mọi row khác bình thường.

1. Xác minh eventId, operationId, event type, createdAt và business deadline.
2. Xem status, attemptCount, lastErrorClass, nextAttemptAt, lease owner.
3. Tìm logs/traces theo correlationId và eventId.
4. Xác định lỗi permanent hay transient; có phải poison message không?
5. Xác minh bản ghi đã được broker nhận trước đó chưa; outcome có thể mơ hồ.
6. Nếu đã có side effect, không replay bằng logical operation key mới.
7. Nếu cần sửa payload/schema, dùng quy trình có audit và owner xác nhận.
8. Replay/quarantine theo contract, giữ event ID/causation nếu phù hợp.
9. Theo dõi đến business terminal state, không dừng ở broker ACK.
10. Ghi lại nguyên nhân và bổ sung test tránh tái diễn.

**Một row kẹt vẫn có thể là sự cố nghiêm trọng**, nhất là Payment/Inventory. Không đặt alert chỉ dựa trên queue depth lớn.

## 22. Runbook: consumer lag tăng nhưng relay bình thường

### Chẩn đoán

- Publish/s còn tăng nhưng processed unique/s không theo kịp;
- Kafka lag per partition hoặc queue ready/unacked tăng;
- Processing duration p99 tăng;
- DB locks/pool hoặc external API 429 tăng;
- Rebalance, consumer crash hoặc poison message;
- Partition skew/hot key;
- Broker/network throughput.

### Hành động có điều kiện

| Nguyên nhân | Hành động |
|---|---|
| Thiếu worker, downstream còn capacity | Scale consumer theo giới hạn partition/capacity |
| DB lock contention | Tối ưu transaction, giới hạn concurrency, phân vùng workload |
| External provider quota | Throttle outbound, respect Retry-After |
| Poison message | Quarantine/DLQ theo ordering semantics và owner policy |
| Consumer rebalance liên tục | Kiểm poll loop, heartbeat, max processing, partition assignments |
| Partition hotspot | Xem key distribution, data model và ordering constraints |
| Broker outage | Sửa broker trước, giới hạn retry |
| Event schema regression | Rollback/sửa compatibility, replay có kiểm soát |

**Không mặc định scale consumer là đáp án.** Tăng consumer có thể đẩy nhiều request đồng thời vào một DB đã chạm trần và làm completion latency tệ hơn.

## 23. Chỉ số kinh doanh và trải nghiệm người dùng

Một API chấp nhận 10.000 đơn trong một phút nhưng 300 đơn vẫn PENDING sau 30 phút là vấn đề người dùng, dù mọi broker producer confirms đều xanh.

Theo dõi:

- accepted orders / phút;
- confirmed/rejected / phút;
- p95/p99 acceptance-to-terminal duration;
- số orders pending quá business deadline;
- số operations ở UNKNOWN/REVIEW_REQUIRED;
- số compensations pending;
- số bản ghi replay cần can thiệp;
- tỷ lệ cần manual reconciliation;
- số complaint/ticket liên quan pending operations nếu hệ thống có;
- đối chiếu payment authorization và order confirmation.

### 23.1. Đừng nhầm throughput với success

Nếu consumer xử lý 1000 attempts/s nhưng 900 attempts là retries của 100 events độc nhất, throughput “attempts” cao không phản ánh công việc hoàn tất nhiều.

### 23.2. Phân loại thành công

PaymentRejected vì thẻ không đủ tiền là một **business outcome xác định**, không phải transport failure. Monitoring nên phân biệt business rejection với technical errors. Nếu gom tất cả vào error_total, alert có thể báo incident trong lúc nghiệp vụ bình thường.

### 23.3. Tổng thời gian với compensation

Nếu Order phải release Inventory sau PaymentRejected, thời gian tới CANCELLED terminal state gồm compensation delay. Không đo completion tại thời điểm “đã gửi ReleaseInventory” rồi coi workflow xong.

## 24. Ví dụ Java: instrument outbox relay

Đây là pseudocode Java định hướng, sử dụng interface thay vì thư viện metrics cụ thể.

~~~java
public interface RelayMetrics {
    void publishAttempt(String eventType, String outcome, String errorClass);
    void observePublishDelay(String eventType, double seconds);
    void recordPendingCount(String eventType, long count);
    void recordOldestPendingAge(String eventType, double seconds);
}

public interface OutboxRepository {
    java.util.List<OutboxRecord> claimDueBatch(int maxBatch);
    void markPublished(String eventId, String leaseToken);
    void scheduleRetry(String eventId, String leaseToken,
                       java.time.Instant nextAttemptAt, String errorClass);
    void quarantine(String eventId, String leaseToken, String reason);
}

public interface EventPublisher {
    void publishAndAwaitConfirmation(OutboxRecord row) throws Exception;
}

public record OutboxRecord(
        String eventId,
        String eventType,
        String aggregateId,
        String correlationId,
        String leaseToken,
        java.time.Instant createdAt,
        int attemptCount,
        String payload
) {}
~~~

Relay logic:

~~~java
public final class OutboxRelay {
    private final OutboxRepository repository;
    private final EventPublisher publisher;
    private final RelayMetrics metrics;

    public OutboxRelay(OutboxRepository repository,
                       EventPublisher publisher,
                       RelayMetrics metrics) {
        this.repository = repository;
        this.publisher = publisher;
        this.metrics = metrics;
    }

    public void publishOne(OutboxRecord row) {
        try {
            publisher.publishAndAwaitConfirmation(row);

            // Update phải kiểm lease/version để tránh stale worker.
            repository.markPublished(row.eventId(), row.leaseToken());

            metrics.publishAttempt(row.eventType(), "SUCCESS", "none");
            double delay = java.time.Duration.between(
                    row.createdAt(), java.time.Instant.now()
            ).toMillis() / 1000.0;
            metrics.observePublishDelay(row.eventType(), Math.max(delay, 0));
        } catch (Exception ex) {
            String errorClass = classify(ex);
            metrics.publishAttempt(row.eventType(), "FAILED", errorClass);

            // classify() quyết định transient hay permanent.
            // scheduleRetry/quarantine phải có transaction và policy rõ.
            handleFailure(row, errorClass);
        }
    }

    private String classify(Exception ex) {
        return "TRANSIENT_OR_PERMANENT_BY_POLICY";
    }

    private void handleFailure(OutboxRecord row, String errorClass) {
        // Pseudocode: retry budget, jitter, DLQ/quarantine,
        // no blind retry on ambiguous outcome.
    }
}
~~~

**Giới hạn của ví dụ:** Không phải code production-ready. Chưa thể hiện transaction claim, leasing heartbeat, connection pooling, retry budget, circuit breaker, key-based partitioning hoặc đầy đủ API của metrics library. Nếu markPublished thất bại sau publish ACK, catch có thể chạy và lên lịch retry; cần giữ stable eventId và consumer idempotency.

### 24.1. Đừng dùng exception class làm high-cardinality label

Metrics chỉ nên dùng errorClass chuẩn hóa: BROKER_TIMEOUT, AUTH, PAYLOAD_INVALID, SCHEMA, UNKNOWN_DESTINATION, DB_FAILURE. Để biết stack trace/exception cụ thể, sử dụng structured logs và trace có giới hạn.

## 25. Ví dụ pseudocode: scanner phát hiện stuck

~~~text
every interval:
    threshold = now - configuredPublishSlo

    metrics.pending = countOutboxUnpublished()
    metrics.oldestAge = oldestOutboxAge()
    metrics.overdue = countOutbox(createdAt < threshold)

    stuckRows = findOutboxRows(
        status = PENDING and createdAt older than threshold
        OR status = IN_PROGRESS and leaseUntil < now
        OR status = RETRY_WAIT and nextAttemptAt overdue beyond tolerance
    )

    for each row in boundedResult:
        log structured STUCK_DETECTED with eventId, operationId,
            eventType, status, attemptCount, lastErrorClass
        alert or enqueue diagnostic action according to policy

    stuckOperations = findBusinessOperations(
        nonTerminal and stateDeadlineAt < now
    )
    metrics.stuckOperations = count(stuckOperations)
~~~

Scanner phải có **bounded batch**, indexes, scheduling jitter và concurrency control. Không chạy full table scan vài giây một lần trên hàng trăm triệu outbox records. Kế hoạch partition/archival giúp bảng duy trì hiệu năng.

### 25.1. Tránh trùng alert

Nếu một event kẹt được scanner phát hiện mỗi phút, không gửi 60 pages cho on-call trong một giờ. Dùng alert grouping/dedup theo service/destination/error class, incident lifecycle và runbook. Với những operations cá biệt có giá trị cao, có thể tạo ticket/case theo operationId mà không đưa nó thành metric label.

### 25.2. Tránh scanner tự tạo race

Nếu scanner tự retry message chỉ vì age cao, nó có thể cạnh tranh với relay chính, tạo duplicate publish. Phân tách **detection** và **authorized recovery action**; mọi recovery phải tôn trọng lease/version, idempotency và retry policy.

## 26. Prometheus/PromQL minh họa

Giả sử hệ thống export counters/gauges chuẩn hóa theo tên trên. Cú pháp sau chỉ minh họa truy vấn; cần xác thực phiên bản Prometheus, labels thực và cách scrape.

### 26.1. Lưu lượng event tạo và publish

~~~promql
sum by (service, event_type) (
  rate(outbox_events_created_total[5m])
)
~~~

~~~promql
sum by (service, event_type) (
  rate(outbox_publish_confirmed_total[5m])
)
~~~

Nếu events created > unique published kéo dài, outbox backlog có thể tăng. Nhưng publish confirmed counter có thể đếm attempts nếu instrument sai; nên thống nhất name và semantics.

### 26.2. Tuổi outbox cũ nhất

~~~promql
max by (service, event_type) (
  outbox_oldest_pending_age_seconds
)
~~~

Đây là gauge đo tại DB/relay; một event poison có thể giữ metric cao, nên có thêm overdue count/errorClass để xác định nguồn vấn đề.

### 26.3. Tỷ lệ publish failures

~~~promql
sum by (service, destination) (
  rate(outbox_publish_attempts_total{outcome="FAILED"}[5m])
)
/
clamp_min(
  sum by (service, destination) (
    rate(outbox_publish_attempts_total[5m])
  ),
  0.001
)
~~~

Tỷ lệ này là theo **attempts**, không phải theo unique events. Trong giai đoạn retry storm, nhiều failures có thể thuộc ít events. Cần xem cùng backlog age và affected unique operations.

### 26.4. Alert minh họa

~~~yaml
groups:
  - name: event-reliability
    rules:
      - alert: OutboxPublishingDelayed
        expr: outbox_oldest_pending_age_seconds > 60
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Outbox oldest pending age exceeds threshold"
          description: "Check relay, broker, retry and outbox state"
~~~

Ngưỡng 60 giây chỉ để minh họa. Thực tế cần alert theo event type/business SLO, tránh thiếu metric bị hiểu là 0, và có runbook link/quyền truy cập phù hợp.

## 27. Alert matrix theo mức độ ưu tiên

| Điều kiện | Mức gợi ý | Action |
|---|---|---|
| Outbox oldest age tăng nhưng dưới business SLO | Dashboard/warning | Xem tốc độ created vs publish |
| Publish progress dừng khi nguồn đang tạo events | Critical nếu kéo dài theo SLO | Kiểm relay, broker và source DB |
| Một Payment operation UNKNOWN quá hạn | High/critical theo rủi ro | Đối soát provider và domain owner |
| Inventory stuck compensation | High | Chạy recovery/compensation |
| Analytics projection lag tăng | Warning theo freshness SLO | Kiểm consumer/index |
| DLQ có poison message mới | Warning/critical theo event type | Phân loại, sửa, replay |
| Quota broker gần đầy | Critical trước retention risk | Throttle producer và mở capacity |
| Metrics exporter mất data | Monitoring incident | Khôi phục telemetry, dùng nguồn kiểm tra khác |
| Retries tăng nhiều nhưng unique throughput giảm | High | Chặn retry amplification và tìm downstream |
| Oldest age giảm, backlog đang xả ổn định | Informational | Tiếp tục theo dõi recovery |

**Không cố áp một mức severity cho mọi hệ thống.** Số lượng tenant ảnh hưởng, business criticality và thời hạn phải được quyết định trước. Một event xác nhận email chậm có thể ít nghiêm trọng hơn một payment đã thu tiền nhưng Order chưa ghi kết quả.

## 28. Failure injection và test matrix

| Kịch bản | Cách tạo lỗi | Điều cần chứng minh |
|---|---|---|
| Relay không chạy | Dừng relay process | Outbox oldest age tăng, cảnh báo phát |
| Broker unavailable | Chặn kết nối broker | Retry/backoff, outbox không mất |
| Publish ACK mất | Broker nhận, relay không nhận response | Retry với stable eventId, consumer dedup |
| Relay crash sau ACK trước mark | Kill relay đúng điểm | Không mất event, duplicate được xử lý an toàn |
| Relay lease hết hạn | Pause worker lâu hơn TTL | Re-claim và version guard hoạt động |
| Một payload invalid | Publish event schema sai | Quarantine/DLQ, không spin nóng |
| CDC connector đứng im | Pause CDC task | Source offset/lag/oldest age phản ánh |
| Consumer crash trước ACK | Commit effect rồi kill consumer | Redelivery không lặp business side effect |
| Consumer ACK sớm | Mô phỏng lỗi code | Test phát hiện nguy cơ mất event, sửa policy |
| Poison Kafka partition | Event không parse được đầu partition | Alert lag per partition, recovery có ordering plan |
| External provider 429 | Quota provider thấp | Delayed retries, concurrency limit |
| DB lock contention | Đánh vào hot aggregate | Không scale vô hạn, invariant vẫn đúng |
| Broker backlog burst | Producer > consumer 10 phút | Admission/backpressure, tính time-to-drain |
| Workflow event kết quả mất | Chặn InventoryReserved | Stuck operation scanner tìm đúng |
| Payment timeout after charge | Provider commit, response mất | REVIEW_REQUIRED và reconciliation, không charge trùng |
| DLQ replay lặp | Replay cùng event nhiều lần | Idempotency và audit |
| Metric exporter lỗi | Chặn scrape | Alert missing data, không báo queue=0 giả |
| Duplicate/out-of-order event | Đảo thứ tự delivery | Version/state transition guard |
| Index/replay sau schema update | Deploy phiên bản khác | Event compatibility, recovery và SLO |

### 28.1. Test đủ các mốc trung gian

Không chỉ viết test “publish thành công”. Cần điều khiển crash tại **trước/sau commit, trước/sau broker confirmation và trước/sau ACK**, vì các cửa sổ lỗi đó quyết định có mất hay trùng event.

### 28.2. Golden signals

Với mỗi kịch bản, ghi:

- accepted operations;
- created outbox rows;
- publish attempts và unique confirmations;
- broker lag/age;
- consumer unique completed;
- operation terminal states;
- retry attempts, DLQ/quarantine;
- thời gian alert xuất hiện;
- thời gian xả backlog;
- số side effects trùng (mục tiêu bằng 0);
- số operation cần manual reconciliation.

### 28.3. Chaos test phải có giới hạn

Chạy failure injection trong môi trường an toàn, có rollback/cleanup và giới hạn số message. Với payment thực, không làm phát sinh giao dịch thật ngoài ý muốn; dùng sandbox/test doubles phù hợp và idempotency.

## 29. Bài thực hành: xây dashboard event reliability

**Bài toán:** Order Service dùng outbox để gửi ReserveInventory và AuthorizePayment. Có broker, Inventory consumer, Payment consumer và một workflow coordinator. Khi broker dừng 5 phút, Order vẫn có thể tiếp nhận một phần công việc theo policy; sau đó backlog tăng. Một bản ghi Payment bị stuck do provider timeout.

### Bước 1 — Xác định mốc và trạng thái

Vẽ sequence diagram từ Order Accepted đến Order terminal state. Đánh dấu outbox commit, relay attempt, broker confirm, consumer receipt, business commit và ACK. Ghi rõ ai sở hữu dữ liệu cho mỗi mốc.

### Bước 2 — Thiết kế schema

Lập bảng các cột outbox tối thiểu: eventId, aggregateId, destination, createdAt, status, attemptCount, lastAttemptAt, nextAttemptAt, lastErrorClass, leaseUntil, publishedAt, correlationId. Nêu index cần cho scanner.

### Bước 3 — Chọn metrics

Tối thiểu: outbox pending count, oldest pending age, created/s, unique published/s, broker lag/age, consumer completed/s, processing p99, DLQ count, stuck operations và completion SLO.

### Bước 4 — Định nghĩa SLO và alert

Đề xuất ngưỡng có lý do cho ReserveInventory và Payment events, thời gian chờ, warning/critical, và một alert cho metrics missing. Gắn mỗi alert với runbook và owner.

### Bước 5 — Tiêm lỗi

- Relay crash sau broker ACK nhưng trước markPublished;
- Consumer crash sau business commit nhưng trước ACK;
- Broker outage;
- Payment provider 429;
- Poison message;
- CDC lag nếu dùng CDC.

Với mỗi lỗi, ghi expected outbox/broker/operation state, metrics, alert và cách phục hồi.

### Bước 6 — Tính backlog

Nếu producer 900 events/s nhưng relay chỉ publish 600 events/s trong 5 phút, tồn đọng tăng bao nhiêu? Nếu producer hạ còn 200 events/s và relay đạt 600/s, cần bao lâu để xả backlog phần tăng đó trong mô hình lý tưởng?

### Bước 7 — Viết runbook

Tạo runbook có các bước: detect, scope, classify, mitigate, recover, reconcile, verify và postmortem. Không dùng “xóa outbox pending” hoặc “reset offsets” như hành động mặc định.

### Bước 8 — Viết ADR

Nêu lý do chọn polling hay CDC, metrics/trace retention, SLO, retry/DLQ/replay policy, business reconciliation và chi phí vận hành. Xác định điều kiện xem xét lại.

**Sản phẩm:** Sơ đồ đường đi, schema trạng thái, dashboard metrics, alert definitions, test evidence, runbook và ADR.

## 30. Câu hỏi ôn tập

1. Vì sao HTTP 202 Accepted không chứng minh một event đã đến consumer?
2. Những mốc nào cần đo giữa outbox commit và business terminal state?
3. Commit-to-publish latency khác consumer processing latency ở đâu?
4. Vì sao p99 publish latency của những events đã thành công có thể che events kẹt mãi?
5. Oldest pending age khác outbox depth như thế nào?
6. Broker queue depth bằng 0 có thể đi kèm pending Order nào?
7. Kafka consumer lag đo records hay thời gian? Vì sao phải có age metric?
8. Trong RabbitMQ/queue push, ready và unacked khác nhau thế nào?
9. Vì sao publish confirmed không đồng nghĩa các consumers đã xử lý?
10. Transactional outbox giảm cửa sổ lỗi nào giữa DB và broker?
11. Relay crash sau broker ACK trước DB mark tạo rủi ro gì?
12. Khi một lease hết hạn nhưng worker cũ hồi phục, cần guard gì?
13. Một event poison ảnh hưởng Kafka partition ordering ra sao?
14. Vì sao không nên retry lỗi schema giống retry network timeout?
15. Retry storm có thể làm broker hồi phục chậm thêm như thế nào?
16. DLQ có phải terminal state của business operation không?
17. Khi Payment provider đã charge nhưng response mất, cần xử lý gì?
18. EventId và operationId khác vai trò trong idempotency như thế nào?
19. Vì sao consumer ACK trước DB commit có thể làm mất công việc?
20. Vì sao consumer commit rồi ACK sau có thể gây duplicate delivery?
21. CDC connector RUNNING có thể vẫn kẹt như thế nào?
22. Làm sao phát hiện registry/broker/consumer metrics thiếu thay vì queue thực sự trống?
23. Vì sao việc tăng consumer không giải quyết DB lock contention?
24. Một operation đã PENDING quá hạn được xem là FAILED chắc chắn không?
25. Reconciliation khác replay message ở điểm nào?
26. Bạn sẽ dùng correlationId, causationId, eventId và traceId ra sao?
27. Vì sao không đặt eventId làm Prometheus label?
28. Cách tách business rejection khỏi technical failure trong metrics?
29. SLO denominator nên tính theo events nào để không bỏ những event chưa bao giờ publish?
30. Alert nên chỉ dựa trên pending count hay cần thời gian/tiến độ?
31. Khi nào cần quarantine message thay vì delayed retry?
32. Vì sao việc xóa outbox pending để dashboard xanh là nguy hiểm?
33. Cách xác minh recovery không tạo side effect trùng?
34. Làm sao chứng minh end-to-end completion SLO sau một broker outage?
35. Với một event duy nhất bị stuck nhiều giờ, làm sao phát hiện mà không đợi depth lớn?

## 31. Checklist triển khai

- [ ] Các mốc accepted, outbox committed, published, received, business committed, ACK và workflow terminal có semantics riêng.
- [ ] Outbox row có eventId, aggregateId, correlationId, createdAt, status và retry metadata.
- [ ] Có claim/lease/version protection cho relay đồng thời nếu cần.
- [ ] Ghi publish confirmation theo broker durability semantics được hiểu rõ.
- [ ] Không mark PUBLISHED trước khi broker ACK theo chính sách đã chọn.
- [ ] Consumer idempotent theo event và logical operation.
- [ ] Không ACK/commit offset trước business effect durable.
- [ ] Có pending/outbox depth, oldest age, publish throughput, error classes.
- [ ] Có broker queue/partition lag, unacked/inflight, oldest message age.
- [ ] Có consumer processed unique/s, retries, processing latency, DLQ.
- [ ] Có stuck workflow operations count theo business deadline.
- [ ] Có completion SLO với denominator không bỏ các events còn pending.
- [ ] Monitoring phân biệt lỗi technical với business rejection.
- [ ] Không dùng eventId/userId/orderId làm metric labels high-cardinality.
- [ ] Structured logs và tracing có correlationId/causationId phù hợp.
- [ ] Retry theo transient/permanent/ambiguous outcome, backoff và jitter.
- [ ] Có retry budget, rate/backpressure policy và phương án xả backlog.
- [ ] DLQ/quarantine có owner, alerts, retention và runbook replay.
- [ ] Stuck scanner dùng index, bounded batches, không tạo lock contention.
- [ ] CDC nếu có được theo dõi bằng progress/offset/lag, không chỉ status RUNNING.
- [ ] Có cảnh báo khi exporter/metrics bị thiếu.
- [ ] Có runbook theo từng vị trí lỗi: outbox, relay, broker, consumer, workflow.
- [ ] Có reconciliation cho Payment/Inventory và những outcome mơ hồ.
- [ ] Không tự động retry Payment với idempotency key mới khi timeout.
- [ ] Đã thử crash sau broker ACK trước mark và sau DB commit trước ACK.
- [ ] Đã thử broker outage, poison message, retry storm, backlog burst, CDC pause.
- [ ] Đã đo time-to-detect, time-to-recover và thời gian xả backlog.
- [ ] Đã kiểm tra business terminal states và không có duplicate side effects.
- [ ] Alert có owner/runbook, severity theo business risk và chính sách giảm nhiễu.
- [ ] Có audit hoạt động manual repair/replay và postmortem khi vi phạm SLO.

**Kết luận:** Truyền sự kiện tin cậy đòi hỏi nhiều hơn việc thấy broker hoạt động hay relay đã gửi thành công. Hệ thống phải biết **event được commit lúc nào, chờ ở đâu, đã thử chuyển bao nhiêu lần, đã được broker xác nhận chưa, consumer đã commit business effect chưa và workflow có đạt trạng thái cuối đúng hạn không**. Bằng cách kết hợp **oldest-age và backlog metrics, tiến độ relay/consumer, tracing, state machine, cảnh báo theo SLO, idempotency, retry có giới hạn, DLQ, runbook và reconciliation**, đội vận hành có thể phát hiện bản ghi kẹt sớm, xác định đúng điểm lỗi và khôi phục mà không làm mất hoặc nhân đôi tác dụng nghiệp vụ.