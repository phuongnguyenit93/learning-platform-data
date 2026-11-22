# Chuyển tiếp outbox bằng truy vấn định kỳ hoặc CDC trong Microservices

> **Bối cảnh:** Software Design Architecture → System Architecture → Microservices → Truyền sự kiện tin cậy.  
> **Chủ đề:** Chuyển tiếp các bản ghi Transactional Outbox từ cơ sở dữ liệu của dịch vụ sang message broker bằng **polling publisher** hoặc **Change Data Capture (CDC)**.  
> **Mục tiêu học tập:** Giải thích đúng cửa sổ lỗi giữa DB và broker, lựa chọn polling/CDC theo nhu cầu, xây relay có retry và quan sát được, bảo vệ tính đúng đắn trước duplicate, ordering, replay, failover và vận hành ở quy mô production.

## 1. Vấn đề dual write: vì sao chỉ gọi broker sau khi ghi DB là chưa đủ?

Giả sử Ordering Service xác nhận một đơn:

~~~text
1. UPDATE orders SET status='SUBMITTED'
2. COMMIT database transaction
3. publish OrderSubmitted to message broker
~~~

Nếu bước 2 thành công nhưng bước 3 thất bại, đơn đã chuyển trạng thái mà Inventory, Payment và Analytics không nhận được thông báo. Nếu đổi thứ tự publish trước COMMIT, broker có thể nhận một event dù transaction DB cuối cùng rollback.

Hai thao tác ghi vào **hai hệ thống độc lập** không tự trở thành một transaction atomic. Các tình huống thường gặp:

- Broker unavailable ngay sau khi DB commit.
- Network timeout: broker đã lưu event nhưng ứng dụng không nhận ACK.
- Process crash giữa hai thao tác.
- Application retry publish và phát event trùng.
- Broker quá tải, publisher không có backpressure.
- Service deploy/restart khi có event chưa phát.
- Event được publish trước khi dữ liệu nguồn thật sự commit.

**Transactional Outbox** giải quyết cửa sổ mất event intent bằng cách ghi **business state và bản ghi sự kiện cần phát vào cùng một local database transaction**.

~~~text
Ordering Service
      |
      v
BEGIN DB TRANSACTION
  Update Order to SUBMITTED
  Insert OutboxEvent(OrderSubmitted)
COMMIT
      |
      v
Outbox table (durable)
      |
      +------ Polling Relay --------\
      |                              \
      +------ CDC Relay --------------> Message Broker
                                           |
                                 +---------+---------+
                                 |                   |
                           Inventory Consumer  Analytics Consumer
~~~

Polling và CDC là hai cách khác nhau để **chuyển tiếp** bản ghi outbox đã commit. Chúng không thay đổi nguyên lý cốt lõi: **producer nghiệp vụ ghi outbox atomically với trạng thái của nó; relay chịu trách nhiệm publish; consumer chịu được việc nhận lại**.

## 2. Các thành phần và ranh giới trách nhiệm

| Thành phần | Trách nhiệm | Không nên đảm nhận |
|---|---|---|
| Business Service | Kiểm tra invariant, cập nhật state và ghi outbox cùng transaction | Cố bảo đảm DB và broker là một atomic write bằng hai API độc lập |
| Outbox Table | Lưu durable event intent và metadata cần phát | Là nơi mỗi consumer tùy ý sửa business state |
| Polling Relay | Truy vấn các bản ghi chưa phát, claim, publish, đánh dấu trạng thái | Thay owner quyết định event nào là sự thật |
| CDC Connector/Relay | Đọc thay đổi DB log và đưa record/event ra broker | Tự hiểu mọi business semantics nếu chỉ nhìn raw row changes |
| Message Broker | Lưu/phân phối sự kiện tới subscribers | Tự bảo đảm exactly-once side effect trên DB bên ngoài |
| Consumer | Xử lý event, dedup, cập nhật trạng thái riêng | Tin rằng mỗi event chỉ được giao một lần |
| Observability/Operations | Theo dõi backlog, age, failures, connector state và phục hồi | Đánh dấu sự kiện published khi chưa có bằng chứng broker chấp nhận |

Một outbox event là **ý định phát thông điệp bền vững** đã được ghi cùng transaction domain. Tùy thiết kế, event có thể là domain event, integration event hoặc command được gửi đi. Cần quy định rõ loại thông điệp, người nhận, schema và ý nghĩa nghiệp vụ.

## 3. Transactional Outbox bảo đảm điều gì?

Trong một DB hỗ trợ local transactions, service thực hiện:

~~~text
BEGIN
  Domain changes
  Outbox event insert
COMMIT
~~~

Nếu transaction rollback, cả domain changes và outbox insert cùng rollback. Nếu COMMIT thành công, outbox row tồn tại để relay chuyển tiếp sau, dù service chết ngay.

Điều này bảo vệ thuộc tính:

**Business state đã commit thì event intent tương ứng cũng đã được ghi bền trong cùng transaction.**

Nhưng nó **không tự bảo đảm**:

- Relay chỉ publish đúng một lần.
- Mọi subscriber xử lý event đúng một lần.
- Event vừa commit đã xuất hiện tức thời trong broker.
- Thứ tự business events được giữ nếu producer/relay có concurrency không kiểm soát.
- External API side effects được rollback cùng DB.
- Outbox row tồn tại mãi dù retention/cleanup sai.
- Broker không mất dữ liệu do cấu hình durability/ACK yếu.
- Consumer không bỏ qua event do commit offset trước khi xử lý.

Mô hình phù hợp trong phần lớn thực tế là **at-least-once publication + idempotent consumption**, với ordering và data recovery được thiết kế riêng.

## 4. Hai cách chuyển tiếp phổ biến

### 4.1. Polling publisher

Một worker chạy định kỳ:

1. Đọc một batch outbox records có trạng thái chưa phát.
2. Claim hoặc khóa những records đó để tránh relay khác lấy cùng lúc.
3. Publish tới broker.
4. Chờ broker acknowledgement phù hợp.
5. Đánh dấu published hoặc ghi tiến độ; nếu lỗi, retry có backoff.
6. Dọn bản ghi cũ sau retention.

~~~text
Outbox DB
  |
  | SELECT pending (every interval)
  v
Polling Worker(s)
  |
  | publish with broker confirmation
  v
Message Broker
  |
  +--> Consumers
~~~

### 4.2. Change Data Capture (CDC)

Connector đọc thay đổi đã commit từ transaction log của DB (ví dụ PostgreSQL WAL, MySQL binlog hoặc cơ chế tương ứng) rồi phát record/event qua pipeline.

~~~text
Outbox DB Transaction Log
          |
          v
CDC Connector
          |
          v
Transformation / Outbox Routing
          |
          v
Message Broker
          |
          v
Consumers
~~~

CDC thường không cần query quét outbox liên tục, nhưng thêm hạ tầng connector, replication/log retention, offset/checkpoint và bài toán snapshot/cutover.

**Cả hai đều có thể đúng.** Lựa chọn phụ thuộc độ trễ sự kiện, quy mô ghi, hạ tầng DB/broker, khả năng vận hành và yêu cầu consistency.

## 5. So sánh nhanh Polling và CDC

| Tiêu chí | Polling | CDC |
|---|---|---|
| Cơ chế | SQL query các bản ghi chờ | Đọc committed changes từ DB log |
| Độ trễ | Gắn với polling interval, load và scheduling | Thường thấp khi connector/log khỏe |
| Tải DB | Query, lock, update trạng thái, index maintenance | Log streaming và replication overhead |
| Chi phí triển khai | Đơn giản hơn khi đã có DB + worker | Phức tạp hơn vì connector, permissions, vận hành log |
| Scaling | Nhiều workers, batch, SKIP LOCKED/leases | Connector tasks, DB-log sequencing và broker partitions |
| Thứ tự | Dễ mất thứ tự nếu claim/publish đồng thời | Có log ordering ở nguồn nhưng downstream vẫn cần key/ordering |
| Retry | Tự thiết kế trạng thái, backoff, claim, DLQ | Connector retries, offsets, xử lý record lỗi và consumer retries |
| Quan sát | SQL backlog/age, relay metrics | Connector status, source lag, log retention, sink lag |
| Recovery | Reclaim expired leases, re-publish pending | Resume từ lưu offset nếu WAL/binlog còn |
| Cleanup | Thường phụ thuộc trạng thái PUBLISHED | Có thể dùng retention/truncate theo checkpoint an toàn |
| DB support | SQL/transaction/locking đủ dùng | CDC feature và quyền đọc log được hỗ trợ |
| Rủi ro chính | DB polling load, hot batch, lease duplicates | Log growth, connector outage, schema/DDL changes, snapshot |
| Phù hợp | Hệ nhỏ-vừa, vận hành tối giản, SLA giây/phút | Hệ có lượng event cao, yêu cầu lag thấp, đã có CDC platform |

Bảng là so sánh khái niệm. Hiệu năng thực tế phụ thuộc DB engine, indexes, broker, connector configuration, commit rate, network và vận hành.

## 6. Mô hình dữ liệu outbox tối thiểu

Một schema có thể gồm:

~~~sql
CREATE TABLE outbox_events (
    id                 UUID PRIMARY KEY,
    aggregate_type     VARCHAR(100) NOT NULL,
    aggregate_id       VARCHAR(150) NOT NULL,
    event_type         VARCHAR(150) NOT NULL,
    event_version      INTEGER NOT NULL,
    aggregate_version  BIGINT,
    partition_key      VARCHAR(200) NOT NULL,
    payload            JSONB NOT NULL,
    headers            JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    state              VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts           INTEGER NOT NULL DEFAULT 0,
    available_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at       TIMESTAMPTZ,
    last_error_code    VARCHAR(100),
    locked_by          VARCHAR(150),
    locked_until       TIMESTAMPTZ,
    claim_token        UUID
);
~~~

Đây là ví dụ PostgreSQL cho **polling-oriented outbox**; CDC-only outbox có thể không cần state, attempts, lock fields hoặc UPDATE published_at. Không dùng mọi cột chỉ vì schema minh họa có chúng.

### Các trường quan trọng

| Trường | Ý nghĩa |
|---|---|
| id / eventId | Identity ổn định xuyên retries và replays |
| aggregateId | Entity hoặc aggregate của sự kiện |
| aggregateVersion | Version của state nguồn nếu có |
| eventType/eventVersion | Contract của integration event |
| partitionKey | Giúp event cùng aggregate đi chung ordering scope |
| payload | Nội dung để publish, tránh chứa bí mật không cần thiết |
| headers | Correlation/trace/tenant/schema metadata đã được validate |
| createdAt | Mốc ghi DB; dùng đo age, không mặc nhiên là commit ordering |
| state | PENDING, IN_PROGRESS, PUBLISHED, FAILED theo polling state machine |
| attempts | Số lần relay claim hoặc publish đã thử; phải định nghĩa rõ |
| availableAt | Retry không được chạy trước mốc này |
| lockedBy/lockedUntil | Lease/ownership của polling worker |
| claimToken | Chống worker đã mất lease cập nhật trạng thái nhầm |
| publishedAt | Bằng chứng ứng dụng đã ghi nhận broker accept, không nhất thiết consumer đã xử lý |

Không đặt mã thông tin mật trong headers/payload. Nếu payload quá lớn, cần thiết kế giới hạn message size hoặc một reference đến storage có quyền, retention và kiểm soát lifecycle; không tùy ý tách event làm mất tính atomicity và reliability.

## 7. Service tạo outbox row cùng business transaction

Ví dụ một lệnh SubmitOrder:

~~~text
Input:
  orderId = O-101
  commandId = cmd-submit-101

Database transaction:
  SELECT Order FOR UPDATE / optimistic concurrency
  Validate transition DRAFT -> SUBMITTED
  UPDATE Order status=SUBMITTED, version=version+1
  INSERT outbox OrderSubmitted(
      eventId=stableId,
      aggregateId=O-101,
      aggregateVersion=newVersion
  )
  COMMIT
~~~

Điểm quan trọng:

- **Kiểm tra invariant trước commit:** không để application phát OrderSubmitted cho đơn vẫn DRAFT.
- **Local transaction:** outbox insert và domain update chung DB transaction.
- **Stable event identity:** nếu command được retry, dedup ở command/business boundary để không tạo nhiều event cho cùng một transition.
- **Version:** nếu business ordering quan trọng, ghi aggregateVersion.
- **Payload snapshot:** nội dung event cần phản ánh state của transaction đã commit, không xây lại từ dữ liệu mutable sau đó.
- **Không gọi broker bên trong transaction dài** để cố đạt atomicity: mạng chậm sẽ giữ DB locks/transaction resources, và bản thân broker publish vẫn có kết quả không rõ.

Nếu service chỉ cập nhật DB trước, rồi INSERT outbox trong transaction thứ hai, vẫn có dual-write gap. Outbox chỉ có giá trị đầy đủ khi **cùng atomic commit** với sự thật nguồn.

## 8. Java/Spring: ghi domain và outbox cùng @Transactional

~~~java
@Service
public final class SubmitOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public SubmitOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public SubmitOrderResult submit(
            String orderId, String commandId) {

        Order order = orders.loadForUpdate(orderId);

        if (order.isSubmitted()) {
            return SubmitOrderResult.alreadyApplied(order.getId());
        }

        order.submit();
        orders.save(order);

        OutboxEvent event = OutboxEvent.orderSubmitted(
                UUID.randomUUID(),
                order.getId(),
                order.getVersion(),
                commandId,
                order.snapshotForIntegration()
        );
        outbox.save(event);

        return SubmitOrderResult.submitted(order.getId());
    }
}
~~~

Đoạn code minh họa các type nghiệp vụ chưa được định nghĩa đầy đủ. Trong production cần:

- Xác định transaction manager cùng datasource cho domain và outbox.
- Bảo vệ command idempotency để retry cùng command không tạo event khác.
- Dùng optimistic locking hoặc row lock phù hợp.
- Không dùng random UUID mới để biểu diễn cùng một domain transition trong những lần retry có thể tạo nhiều commit: event ID phải gắn với transaction thành công và được lưu bền, hoặc business dedup phải chặn transition trùng.
- Cân nhắc aggregateVersion, unique constraint và concurrency tests.
- Không dựa vào @Transactional nếu outbox repository thực tế ghi DB khác không tham gia cùng transaction.

## 9. Tại sao không publish trực tiếp trong @Transactional?

Một giải pháp dễ nhầm:

~~~java
@Transactional
public void submit(String orderId) {
    orderRepository.submit(orderId);
    kafkaTemplate.send("orders", orderId, event);
}
~~~

Tùy cấu hình, send có thể bất đồng bộ. Ngay cả nếu broker ACK, DB transaction vẫn có thể rollback. Nếu DB commit xong mà broker publish fail/unknown, code không tự có một atomic write xuyên cả hai systems.

Các transaction mechanisms riêng của broker/DB có scope và điều kiện cụ thể. Nếu không sử dụng một distributed transaction protocol được hỗ trợ với độ phức tạp tương ứng, **đừng tuyên bố hai writes là một**.

Transactional Outbox chọn đánh đổi: ghi local transaction trước; publish asynchronously và có thể trùng, nhưng có bằng chứng bền vững để retry.

## 10. Polling: cơ chế cơ bản nhất

Một single worker có thể chạy:

~~~sql
SELECT id, aggregate_type, aggregate_id, event_type,
       partition_key, payload, headers
FROM outbox_events
WHERE state = 'PENDING'
  AND available_at <= now()
ORDER BY created_at, id
LIMIT 100;
~~~

Sau đó publish từng record và đánh dấu PUBLISHED khi broker xác nhận.

Nhưng một SELECT thông thường **không claim độc quyền**. Hai relay instances có thể đọc cùng batch và publish trùng. Có thể chấp nhận duplicate vì at-least-once, nhưng nếu không kiểm soát, lượng duplicate sẽ lớn và gây lãng phí.

Ngoài ra, ORDER BY created_at không bảo đảm chính xác thứ tự commit nghiệp vụ: clock, transaction timing và concurrency có thể làm thứ tự createdAt hoặc sequence ID khác thời điểm COMMIT. Nếu per-aggregate ordering quan trọng, phải có cơ chế bảo vệ khác.

## 11. Polling có nhiều workers: claim qua SKIP LOCKED

Một cách phổ biến trong PostgreSQL là claim batch bằng transaction:

~~~sql
BEGIN;

WITH selected AS (
    SELECT id
    FROM outbox_events
    WHERE (
        state = 'PENDING'
        AND available_at <= now()
    ) OR (
        state = 'IN_PROGRESS'
        AND locked_until < now()
    )
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE outbox_events AS o
SET state = 'IN_PROGRESS',
    locked_by = :worker_id,
    locked_until = now() + INTERVAL '60 seconds',
    claim_token = :new_claim_token,
    attempts = attempts + 1
FROM selected AS s
WHERE o.id = s.id
RETURNING o.*;

COMMIT;
~~~

Đây là mô hình tham khảo. Trong PostgreSQL thực tế cần đặt parentheses chính xác cho predicate, kiểm thử transaction isolation, indexes và version DB. Chọn claim token riêng cho mỗi batch hoặc mỗi row theo mô hình ownership, và giữ token trong worker để kiểm tra khi update.

**SKIP LOCKED** giúp các workers không chờ cùng một row đang bị khóa. Sau khi transaction claim commit, chúng có thể publish bên ngoài transaction DB.

### Vì sao không giữ transaction DB mở trong lúc gọi broker?

Giữ row locks từ lúc SELECT đến khi broker ACK có thể:

- Tăng thời gian giữ DB connections.
- Làm transaction dài, kéo vacuum/maintenance và contention.
- Gây timeout hoặc deadlocks.
- Giảm throughput.
- Làm broker outage kéo theo DB pressure.

Lease-based claim tách transaction DB ngắn khỏi publish network, đổi lại phải xử lý lease expiry và duplicate.

### Claim và ownership

Trong môi trường có nhiều workers, record nên được cập nhật PUBLISHED chỉ khi worker còn quyền claim phù hợp. Một lệnh minh họa:

~~~sql
UPDATE outbox_events
SET state = 'PUBLISHED',
    published_at = now(),
    locked_by = NULL,
    locked_until = NULL
WHERE id = :event_id
  AND state = 'IN_PROGRESS'
  AND claim_token = :claim_token;
~~~

Nếu affected rows = 0, worker có thể đã mất lease hoặc record được xử lý bởi worker khác; phải điều tra theo policy, không blind overwrite.

## 12. Polling state machine

~~~text
PENDING
   |
   | claim
   v
IN_PROGRESS
   |
   +---- broker ACK confirmed ----> PUBLISHED
   |
   +---- retryable failure -------> PENDING (availableAt in future)
   |
   +---- lease expired -----------> eligible for reclaim
   |
   +---- non-retryable issue -----> BLOCKED / QUARANTINED
~~~

Các tên trạng thái có thể khác, nhưng semantics cần rõ.

**PUBLISHED** nghĩa là relay đã ghi nhận broker chấp nhận message theo ACK/durability được cấu hình. Nó **không** nghĩa tất cả consumers đã xử lý thành công.

**BLOCKED/QUARANTINED** cần owner và runbook, không được âm thầm xóa. Nếu payload không parse hoặc serializer lỗi lâu dài, liên tục retry mỗi giây sẽ tạo vòng lặp nóng và che nguyên nhân.

## 13. Polling interval, batch size và latency

Đơn giản hóa, một event commit ngay sau một lần poll có thể phải chờ gần một interval mới được thấy. Nhưng độ trễ thực tế còn gồm:

\[
L_{\text{publish}} =
L_{\text{wait}} + L_{\text{claim}}
+ L_{\text{serialization}} + L_{\text{broker}}
+ L_{\text{mark}}.
\]

Nếu interval 1 giây, latency không tự có p99 < 1 giây: backlog, database slow query, broker ACK và retry đều có thể lớn hơn.

Các tham số:

| Tham số | Tác động |
|---|---|
| pollingInterval | Thời gian chờ tối đa thông thường giữa các poll, khi không lag |
| batchSize | Số rows claim mỗi lượt; lớn quá gây memory/network bursts |
| workerCount | Throughput và contention giữa relays |
| maxInFlight | Số publish đang chờ ACK |
| publishTimeout | Giới hạn một operation network |
| leaseDuration | Thời hạn claim, cần dài hơn xử lý hoặc gia hạn |
| retryBackoff | Độ trễ khi broker thất bại |
| jitter | Tránh workers retry đồng loạt |
| dbPool/SQLTimeout | Bảo vệ DB khỏi relay nghẽn |
| cleanupRetention | Dung lượng outbox, khả năng điều tra và replay |

Không đặt interval cực nhỏ nhưng query không có index, dẫn tới DB bị quét liên tục khi table hàng triệu rows.

## 14. Indexing, partitioning và housekeeping cho polling

Một index minh họa:

~~~sql
CREATE INDEX idx_outbox_pending
ON outbox_events (available_at, created_at, id)
WHERE state = 'PENDING';

CREATE INDEX idx_outbox_expired_lease
ON outbox_events (locked_until, id)
WHERE state = 'IN_PROGRESS';
~~~

Không có index tối ưu tuyệt đối cho mọi workload. Query predicate, ORDER BY, data distribution và state transitions quyết định execution plan. Cần đo EXPLAIN/ANALYZE, DB CPU, I/O, lock waits, table bloat và vacuum overhead.

Cleanup:

- Chỉ xóa PUBLISHED rows sau khoảng retention đủ cho điều tra và đối soát.
- Không xóa PENDING, IN_PROGRESS hoặc BLOCKED chỉ vì createdAt cũ.
- Có thể partition table theo ngày/tuần để dọn dữ liệu đã đủ điều kiện.
- Nếu cần audit lâu hơn, đưa metadata/payload đã xử lý sang archive có bảo mật.
- Đảm bảo quy trình restore DB/outbox nhất quán với broker replay.
- Không để cleanup job và relay tranh lock hoặc xóa một row còn trách nhiệm.

Một outbox backlog tăng có thể làm database chính chịu tải lớn. Cần SLO về oldest pending age và dung lượng, không chỉ CPU/5xx.

## 15. Publish acknowledgement: lúc nào được đánh dấu PUBLISHED?

Giả sử worker gọi broker:

~~~text
Worker ---- publish(eventId=E100) ----> Broker
Worker <--- broker ACK confirmed ----- Broker
Worker ---- UPDATE outbox PUBLISHED --> DB
~~~

Cần kiểm tra ACK semantics:

- Với Kafka: acknowledgement/producer delivery result và durability configuration theo yêu cầu.
- Với RabbitMQ: publisher confirms và unroutable-message handling phù hợp.
- Với cloud queues: API send acknowledgement và queue durability contract.
- Với bridge/proxy: ACK có nghĩa destination broker đã chấp nhận hay chỉ proxy đã nhận?

Đánh dấu published **trước** khi nhận confirmation có thể làm mất event nếu broker thật ra chưa lưu. Đánh dấu sau confirmation vẫn có cửa sổ duplicate vì worker có thể crash trước DB update.

Đây là trade-off có chủ đích: **ưu tiên không bỏ sót event intent, chấp nhận khả năng duplicate** và giải quyết duplicate ở consumer.

## 16. Ba cửa sổ lỗi phải thuộc lòng

### A. DB commit thành công, relay chưa publish

~~~text
Business + outbox COMMIT
Relay not yet run
Service/worker crashes
~~~

Outbox row còn bền vững. Worker sau restart có thể tìm và publish. Đây là lợi ích chính.

### B. Broker đã nhận, relay crash trước đánh dấu PUBLISHED

~~~text
Broker stores event E100
ACK is received (or lost)
Relay crashes before DB mark
~~~

Sau restart row có thể vẫn PENDING hoặc lease hết hạn, worker publish lại E100.

**Kết quả:** broker có thể chứa duplicate. Consumer phải dedup bằng stable eventId hoặc business operation ID.

### C. Relay đánh dấu PUBLISHED nhưng thực tế broker chưa lưu

~~~text
Relay marks PUBLISHED too early
Broker rejects/loss after the mark
~~~

Có nguy cơ mất event vĩnh viễn khỏi đường retry thông thường. Tránh bằng việc chờ broker confirmation phù hợp và dùng đúng guarantee hạ tầng.

Không nên đặt tên trạng thái Published chỉ vì code đã gọi send(). Với API bất đồng bộ, future/callback completion và broker ACK semantics cần được tôn trọng.

## 17. Lease hết hạn và worker “zombie”

Một worker claim row với lease 60 giây rồi broker publish treo 90 giây. Worker khác nhìn lease expired và claim lại record. Hai worker có thể publish cùng event.

Điều này không nhất thiết là lỗi correctness nếu duplicate có thể xử lý. Nhưng cần ngăn worker cũ **đánh dấu sai state** sau khi mất lease.

Biện pháp:

- Per-attempt claim token hoặc fencing generation.
- UPDATE có điều kiện claim_token.
- Lease duration dựa trên worst-case publish, hoặc có heartbeat/renewal.
- Broker publish timeout để không giữ in-flight vô thời hạn.
- Bounded concurrency và backpressure.
- Sử dụng stable eventId để consumer dedup.
- Metric lease expiry và duplicate publish attempts.

Fencing token chỉ bảo vệ cập nhật **ở nơi thực sự kiểm tra token**; không tự ngăn broker đã nhận hai publish. Muốn ngăn side effect trùng vẫn phải idempotent downstream.

## 18. Retry/backoff khi publish thất bại

Không nên retry vô hạn trong một loop nóng. Một policy có thể gồm:

- Retryable error classification (broker unavailable, throttling, temporary network).
- Max attempts hoặc max elapsed trước khi chuyển quarantine/manual intervention.
- Exponential backoff + jitter.
- Publish timeout và circuit breaker.
- Rate limit toàn relay khi broker hoặc DB quá tải.
- Tách lỗi serialization/schema permanent khỏi lỗi connectivity.
- Không xóa event chưa phát chỉ vì đã quá tuổi; nếu business deadline đã qua, phải quyết định và audit.
- Alert khi retry backlog làm quá SLA business event propagation.

Công thức tham khảo:

\[
d_k = \min(d_{\max}, d_0 \cdot 2^{k-1}),
\]

với jitter để tránh các relays đồng loạt dồn tải. Chọn khoảng chờ dựa trên event delivery SLO và khả năng broker phục hồi.

### Bảng minh họa

| Attempt | Max delay trước lần sau | Hành động |
|---:|---:|---|
| 1 | 1 giây | Retry transient |
| 2 | 2 giây | Retry transient |
| 3 | 4 giây | Retry transient |
| 4 | 8 giây | Retry transient |
| 5 | 16 giây | Kiểm tra deadline/budget |
| Exhausted | Theo policy | Quarantine/alert/controlled redrive |

Không xem các con số này là mặc định cho production. Một payment authorization event critical có thể cần policy và on-call khác notification email.

## 19. Java: polling relay ở mức thuật toán

Pseudocode Java, không gắn vào broker cụ thể:

~~~java
public final class PollingOutboxRelay {
    private final OutboxStore outboxStore;
    private final EventPublisher publisher;

    public void tick() {
        List<OutboxClaim> claims = outboxStore.claimBatch(
                100,
                Duration.ofSeconds(60)
        );

        for (OutboxClaim claim : claims) {
            try {
                // Phải chờ broker confirmation thực sự
                publisher.publishAndAwaitAck(
                        claim.partitionKey(),
                        claim.eventId(),
                        claim.payload(),
                        Duration.ofSeconds(10)
                );

                outboxStore.markPublishedIfClaimMatches(
                        claim.eventId(),
                        claim.claimToken()
                );

            } catch (RetryablePublishException e) {
                outboxStore.scheduleRetryIfClaimMatches(
                        claim.eventId(),
                        claim.claimToken(),
                        computeBackoffWithJitter(claim.attempt())
                );

            } catch (NonRetryablePublishException e) {
                outboxStore.quarantineIfClaimMatches(
                        claim.eventId(),
                        claim.claimToken(),
                        e.errorCode()
                );
            }
        }
    }
}
~~~

Các interface, exception, fields và method được viết ở mức minh họa; cần định nghĩa trong ứng dụng thật.

Lưu ý thiết kế:

1. claimBatch dùng transaction DB ngắn.
2. publishAndAwaitAck có timeout và backpressure.
3. Mark PUBLISHED dùng claim token để chống lost lease.
4. Không ném event away khi lệnh markPublished DB lỗi: publish có thể đã thành công và cần retry an toàn.
5. Có shutdown hook để dừng claim mới và cho in-flight operations kết thúc theo deadline.
6. Có metrics per stage và worker identity.
7. Batch có thể được xử lý song song giữa aggregate khác nhau; per-aggregate ordering cần chính sách riêng.

## 20. Java/Spring: scheduled polling và giới hạn nó

Một worker có thể dùng @Scheduled:

~~~java
@Component
public final class OutboxSchedule {
    private final PollingOutboxRelay relay;

    public OutboxSchedule(PollingOutboxRelay relay) {
        this.relay = relay;
    }

    @Scheduled(fixedDelayString = "1000")
    public void poll() {
        relay.tick();
    }
}
~~~

Ví dụ này **không đủ để vận hành production**: nhiều replicas cùng chạy, executor concurrency, DB locking, relay failure, broker confirms, shutdown/retry và metrics vẫn phải được thiết kế.

Đừng đặt SQL query, publish broker và UPDATE DB trong cùng @Transactional method dài chỉ để cảm thấy atomic. Broker không tự tham gia local DB transaction.

### Trường hợp một worker đơn giản là đủ

Hệ thống event rate thấp, publication SLO vài giây, database không quá tải và chưa có platform CDC có thể bắt đầu với một polling worker. Dù chỉ một worker vẫn cần:

- Idempotency cho consumer.
- Bền vững trước crash.
- Index để query pending.
- Trạng thái lỗi/retry.
- Alert cho backlog và oldest age.
- Định nghĩa behavior khi deploy/restart.

Không đổi sang CDC chỉ vì polling trông “ít hiện đại” hơn; đo nhu cầu thực.

## 21. CDC: đọc committed log thay vì quét bảng

CDC thường đọc thay đổi từ database transaction log. Trong PostgreSQL, logical decoding có thể cho connector biết các committed changes theo cơ chế WAL. Trong MySQL, CDC có thể đọc binlog khi được cấu hình và cấp quyền phù hợp.

Một pipeline tổng quát:

~~~text
Application transaction
  |
  +--> business row changes
  +--> INSERT outbox row
  |
  v
Database commit / transaction log
  |
  v
CDC source connector
  |
  v
Outbox event routing / transformation
  |
  v
Message broker topic
  |
  v
Consumer group
~~~

CDC không nên coi raw DB change event là public integration event nếu các field table/column không có semantics nghiệp vụ. Outbox Event Router hoặc transformation layer chọn các cột như eventId, aggregateType, aggregateId, type và payload để tạo message contract.

CDC phù hợp khi muốn giảm SQL polling, đã có platform Debezium/Kafka Connect hoặc muốn publication lag thấp. Đổi lại cần vận hành connector, replication slot, log retention, schema changes, offsets và destination availability.

## 22. Thiết kế CDC-oriented outbox

Schema CDC có thể tối giản:

~~~sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    event_version INTEGER NOT NULL,
    aggregate_version BIGINT,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Lưu ý:

- INSERT outbox và domain updates cùng local transaction.
- CDC đọc INSERT đã commit.
- Connector/transformation chọn routing key, topic và headers.
- Outbox row thường **append-only** đối với event intent. UPDATE trạng thái của polling không bắt buộc.
- Nếu xóa outbox records, CDC sẽ thấy DELETE/tombstone hoặc các event kỹ thuật tùy connector; phải cấu hình route/filter tránh biến việc cleanup thành business event.
- Retention cleanup chỉ an toàn khi đã xác minh CDC connector qua vị trí thay đổi liên quan; không tự xóa row quá sớm khi connector chưa snapshot hoặc chưa bắt kịp.
- Nếu có snapshot ban đầu, cần phân biệt rows lịch sử đã publish với rows cần replay.

Không dùng một schema duy nhất cho polling và CDC mà không xét cách CDC xử lý UPDATE/DELETE, row filters và thông điệp lặp.

## 23. Debezium và Outbox Event Router: vai trò khái niệm

Một triển khai phổ biến kết hợp:

1. PostgreSQL/MySQL transactional log.
2. Debezium source connector.
3. Một transform nhận dạng outbox rows và chuyển thành integration events.
4. Kafka topics theo aggregate type/event routing.
5. Consumers idempotent.

Ví dụ outbox row:

~~~json
{
  "id": "b8f3a111-60d0-4d53-9b50-2d79113e74e1",
  "aggregate_type": "Order",
  "aggregate_id": "O-101",
  "event_type": "OrderSubmitted",
  "event_version": 2,
  "aggregate_version": 8,
  "payload": {
    "orderId": "O-101",
    "status": "SUBMITTED"
  }
}
~~~

Một message đích có thể được ánh xạ:

~~~text
topic: domain.orders
key: O-101
headers:
  eventId: b8f3a111-60d0-4d53-9b50-2d79113e74e1
  eventType: OrderSubmitted
  eventVersion: 2
value:
  {"orderId":"O-101","status":"SUBMITTED"}
~~~

Đây là mô hình logic, không phải cấu hình connector phiên bản cụ thể. Tên trường, SMT config, serialization và routing property phụ thuộc bản Debezium/Kafka Connect đang chạy; phải dùng tài liệu và thử nghiệm tương ứng.

Không coi Debezium tự biến mọi table mutation thành domain event đúng nghĩa. Business service vẫn phải tự tạo outbox record đúng semantics.

## 24. CDC snapshot ban đầu và ranh giới giữa lịch sử/hiện tại

Một connector mới thường cần xác định đọc những gì đã tồn tại trước khi bắt đầu stream:

- Chỉ đọc changes sau một log position?
- Snapshot toàn bộ outbox table hiện có?
- Bản ghi nào đã được publish bởi hệ cũ?
- Có cần backfill records chưa phát sau migration?
- Có duplicates giữa snapshot và streaming phase không?
- Schema của records cũ còn tương thích với consumer không?

Nếu một outbox table đã chứa một triệu records PUBLISHED từ relay cũ, bật CDC snapshot toàn bảng rồi phát chúng lại có thể gây side effects trùng quy mô lớn.

Các chiến lược:

1. Chỉ CDC từ một mốc cutover đã kiểm soát với tất cả event cũ được xử lý/xác minh.
2. Dùng table mới hoặc event stream mới cho CDC outbox.
3. Dùng migration marker/filters và quy trình replay có kiểm soát.
4. Có thể cần snapshot dành riêng cho rows chưa publish và xác nhận dữ liệu.
5. Đánh giá retention và khả năng khởi động từ log position với DB/connector thực.
6. Ghi rõ event ID và idempotency khi có overlap.

Mỗi chiến lược phải có bằng chứng **không mất event** trong cửa sổ chuyển tiếp; nếu chấp nhận duplicate, consumer phải idempotent.

## 25. CDC offsets và database log retention

CDC connector thường lưu tiến độ đọc vào offset/checkpoint store. Khi restart, nó tiếp tục từ vị trí đã lưu nếu transaction log cần thiết còn có thể truy cập.

Nếu connector dừng lâu:

~~~text
DB keeps writing
CDC connector is down
WAL/binlog accumulates
Replication lag grows
Storage pressure increases
~~~

Các rủi ro:

- PostgreSQL replication slot có thể giữ lại WAL khiến disk đầy nếu connector ngừng hoặc không tiến.
- MySQL binlog retention có thể xóa đoạn connector cần để resume, dẫn tới lỗi hoặc phải resnapshot.
- Permission hoặc network lỗi khiến connector không thể đọc log.
- DB failover, upgrade hoặc replication topology thay đổi ảnh hưởng log position.
- Nếu sink/broker chậm, source connector backpressure và offset lag tăng.
- Connector recovery có thể replay một đoạn records, tạo duplicate.

Cần monitor **log retention headroom, connector lag, replication slot/binlog size, source DB disk** và cảnh báo trước khi ảnh hưởng hệ thống giao dịch. CDC giảm SQL polling nhưng không miễn phí về hạ tầng nguồn.

## 26. CDC transaction ordering và giới hạn của nó

Trong cùng DB log, CDC có thể phản ánh thứ tự committed changes theo cơ chế log; đây là lợi thế khi cần hiểu thứ tự publication tại nguồn.

Tuy nhiên:

- Hai transactions thay đổi cùng aggregate có thể cạnh tranh; domain cần aggregateVersion/optimistic locking.
- Outbox routing sang nhiều topics/partitions không có global ordering.
- Connector có thể retry/replay khi restart.
- Consumer dùng worker pool có thể commit v9 trước v8 dù broker lưu đúng thứ tự.
- Migration topic/partition count làm thay đổi routing key scope.
- Multi-database business flow không tự tạo transaction order xuyên services.
- Nếu event payload không chứa version/causation, consumer khó xác minh semantics khi nhận out-of-order.

**Commit-order observation** không đồng nghĩa **end-to-end business side-effect order**. Với các nghiệp vụ nhạy cảm, cần key/aggregate version, idempotency và concurrency control tại consumer.

## 27. Routing theo aggregate key

Để tăng khả năng giữ thứ tự per aggregate:

~~~text
Outbox:
  aggregateType = Order
  aggregateId = O-101
  eventType = OrderSubmitted
  aggregateVersion = 8

Broker:
  topic = domain.orders
  key = O-101
~~~

Các sự kiện cùng order được định tuyến tới cùng partition khi dùng partitioner/partition count nhất quán. Nhưng:

- Key giống nhau không sửa lỗi publisher phát sai domain sequence.
- Tăng số partitions có thể đổi mapping của key trong giai đoạn chuyển tiếp.
- Kafka không bảo đảm total order xuyên partitions.
- Consumer async handler có thể phá completion order.
- Retry/DLT chuyển event v8 ra ngoài luồng, khiến v9 chạy trước.
- Multiple outbox relay workers có thể claim v8/v9 và publish ngược nếu không có per-key ordered publication.

Nên công bố contract **ordering scope**, không chỉ “events ordered”. Nếu các event không phụ thuộc nhau hoặc commute được, có thể ưu tiên throughput hơn strict order.

## 28. Polling và thứ tự: điểm yếu của nhiều workers

Ví dụ:

~~~text
Outbox:
  O-101 v7  -> claimed by Worker A
  O-101 v8  -> claimed by Worker B

Worker A broker timeout 10 seconds
Worker B publishes v8 in 50 ms
~~~

Dù query ORDER BY createdAt, event v8 có thể vào broker trước v7. SKIP LOCKED giúp cạnh tranh công việc nhưng **không bảo đảm ordered publish cho cùng aggregate**.

Các chiến lược:

- Một relay worker tuần tự nếu tải đủ nhỏ.
- Partition outbox ownership theo aggregate key, mỗi key có một serial queue.
- Claim theo aggregate, không claim row tùy ý; một key chỉ có một active worker.
- Dùng sequence guard và không publish v8 trước khi v7 được xác nhận hoặc chuyển sang recovery policy.
- Consumer có aggregateVersion và durable gap handling, nếu business cho phép.
- Chọn CDC với transaction-log ordering và cấu hình routing phù hợp, nhưng vẫn kiểm tra downstream semantics.

Đừng giả định database auto-increment ID hoặc createdAt luôn phản ánh commit order khi các transactions concurrency. Cần xác định một **nguồn sequence đáng tin** theo domain nếu muốn strict order.

## 29. Broker key, topic và schema evolution

Một event contract cần quyết định:

| Trường | Ví dụ | Câu hỏi |
|---|---|---|
| eventId | UUID | Idempotency dedup dùng trong bao lâu? |
| type | OrderSubmitted | Có ý nghĩa nghiệp vụ ổn định không? |
| eventVersion | 2 | Consumer cũ xử lý version mới thế nào? |
| aggregateId | O-101 | Partitioning và ordering scope là gì? |
| aggregateVersion | 8 | Có liên tục trong stream subscriber nhìn thấy không? |
| occurredAt | ISO-8601 | Là event time hay DB recorded time? |
| correlationId | checkout-55 | Truy vết workflow ra sao? |
| payload | JSON/Avro/Protobuf | Có PII, size, schema registry không? |
| tenantId | opaque reference | Quyền truy cập và isolation thế nào? |

Không công bố raw outbox table schema làm public contract nếu consumer chỉ cần domain event. Có thể transform payload sang representation hợp lệ, nhưng transformation phải có versioning và khả năng phục hồi, không mất original event intent khi sai schema.

Nếu eventVersion thay đổi, cần compatibility tests, deprecation policy và xử lý unknown values. Relay có thể publish bytes chuẩn bị sẵn tại commit để tránh diễn giải bằng code mới dữ liệu cũ.

## 30. Consumer idempotency: chìa khóa cho cả Polling và CDC

Giả sử relay đã publish event E100 nhưng không thể ghi nhận success. Khi retry, E100 được publish lại.

Consumer nên:

1. Kiểm tra eventId hoặc business operation key.
2. Bảo vệ bằng unique constraint hoặc idempotency state.
3. Thực hiện domain mutation/processed marker trong cùng local transaction.
4. ACK/commit broker progress sau durable outcome.
5. Đánh giá external API side effect riêng với idempotency key/reconciliation.

Một inbox table:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ logic:

~~~text
BEGIN
  INSERT consumed_events (consumer, eventId)
  ON CONFLICT DO NOTHING

  if row already existed:
      COMMIT; ACK as duplicate
  else:
      apply domain state mutation
      insert outbox event if this consumer produces follow-up event
      COMMIT; ACK
~~~

Mọi bước cập nhật DB cần chung transaction để nếu business mutation thất bại, inbox marker cũng rollback. Với parallel processing, unique constraint và transaction isolation phải ngăn hai handlers cùng thực hiện side effect.

**Exactly-once là guarantee có phạm vi.** Không được suy từ CDC, Kafka transactional producer hoặc inbox rằng giao dịch trên payment provider bên ngoài sẽ exactly-once.

## 31. Payload quá lớn, serialization và schema lỗi

Outbox row có thể chứa payload lớn hoặc dữ liệu không serialize được. Lỗi này có thể là permanent cho relay hiện tại.

Cần:

- Giới hạn kích thước event và header.
- Validate schema/payload trước khi commit outbox nếu thực tế cho phép.
- Ghi explicit eventVersion và format.
- Không để serializer mới vô tình không còn đọc được event cũ trong backlog.
- Tách lỗi schema permanent với broker outage transient.
- Quarantine row có errorCode, eventId, owner và audit.
- Cung cấp controlled migration/transform bản lỗi, giữ bản gốc.
- Có quyền truy cập phù hợp vì outbox và DLQ thường chứa dữ liệu nhạy cảm.
- Không xóa event chỉ vì không còn tương thích code của một relay deploy mới.

Nếu schema conversion nằm trong relay, cần versioned converter và contract tests; một deployment có thể khiến hàng nghìn pending events lỗi dù chúng hợp lệ lúc commit.

## 32. Polling cleanup và CDC retention: đừng dọn quá sớm

### Polling

Không xóa row trước khi broker confirmation được ghi bền trong DB. Nếu cleanup job xóa PENDING hoặc IN_PROGRESS theo createdAt thay vì theo state/retention, có thể mất event intent.

Một policy minh họa:

~~~text
PENDING: keep until published or explicitly resolved
IN_PROGRESS: reclaim after lease expiration if needed
BLOCKED: keep for investigation/redrive
PUBLISHED: retain for 7 days; then archive/delete by policy
~~~

### CDC

Không dựa đơn thuần vào publishedAt nếu CDC-only outbox không có field này. Cần biết connector đã tiêu thụ thay đổi ở log position nào và retention/snapshot strategy.

Nếu DELETE từ outbox table tạo CDC events, transformation phải định nghĩa cách bỏ qua delete/tombstone, nếu không cleanup có thể xuất messages không phải business facts.

### Recovery và audit

Những event liên quan tài chính hoặc compliance có thể cần metadata/audit retention lâu hơn. Nhưng giữ toàn bộ payload trong OLTP DB mãi làm tăng storage và blast radius bảo mật. Chọn tách audit archive/trace metadata theo policy và yêu cầu pháp lý.

## 33. CDC connector outage và failover DB

Khi CDC connector down nhưng DB service vẫn ghi outbox:

- DB transactions vẫn có thể commit.
- Publication lag tăng.
- Transaction log có thể bị giữ lại, tạo áp lực disk.
- Consumer không nhận events mới; workflow async có thể pending.
- Khi connector khôi phục, backlog có thể tạo burst vào broker.
- Connector có thể replay events từ checkpoint cũ.
- Nếu failover DB, log position/slot/permissions cần được khôi phục theo topology.

Runbook:

1. Xác định connector status và source/sink connectivity.
2. Kiểm tra replication slot/binlog/WAL retention và disk.
3. Đánh giá mốc offset/checkpoint gần nhất đã lưu.
4. Kiểm tra broker capacity và consumer lag.
5. Khôi phục connector theo supported procedure của DB và version.
6. Giới hạn backfill throughput nếu cần để bảo vệ production workload.
7. Theo dõi duplicate, gap và event age.
8. Nếu log segment đã mất, xác định phương án resnapshot/reconcile từ outbox và nguồn sự thật, không tự reset offset ngẫu nhiên.
9. Đóng incident với bằng chứng đã phục hồi các events bị thiếu.

Không xóa replication slot chỉ để giải phóng disk rồi giả định connector có thể tiếp tục từ cùng vị trí cũ. Đây là hành động có thể làm mất khả năng stream liên tục và cần kế hoạch recovery.

## 34. Quyết định CDC có thích hợp với database nguồn không

Trước khi triển khai:

- DB hỗ trợ đọc committed change log theo cách tin cậy không?
- Có quyền bật logical replication/binlog và quản lý slot không?
- Các operations DBA/Platform có thể theo dõi log retention không?
- DB failover/backups có hỗ trợ resume connector không?
- Connector có quyền tối thiểu và secrets được quản lý không?
- Schema DDL changes và column type evolution có compatible không?
- Cần snapshot ban đầu không?
- Có giới hạn max retention, disk và replication lag không?
- Có broker/sink quotas đủ khi backlog được xả không?
- Có test end-to-end với broker unavailable, connector restart và failover chưa?

CDC không phải “không có tác động lên DB”. Log generation và retention, replication buffers, snapshot reads và connector metadata đều có chi phí vận hành.

## 35. Hybrid: Polling và CDC chuyển đổi theo giai đoạn

Có thể ban đầu hệ thống dùng polling, sau đó chuyển sang CDC khi lưu lượng tăng. Nhưng bật hai relays cùng publish một outbox table không kiểm soát sẽ tạo duplicate và có thể phá ordering.

Một migration strategy:

1. Xác định những rows nào relay polling đã xử lý.
2. Chọn boundary cutover có event IDs, DB checkpoint/transaction position phù hợp.
3. Đảm bảo không có gap giữa event cuối polling và event đầu CDC.
4. Nếu có overlap, consumer phải idempotent và hệ thống đo duplication.
5. Dùng connector snapshot mode/filters theo kế hoạch, không phát lại toàn bộ PUBLISHED history.
6. Chạy canary topic/consumer không có side effect hoặc shadow comparison nếu thích hợp.
7. Chỉ một live publication owner tại một thời điểm, trừ dual-run được thiết kế riêng.
8. Giám sát source-to-broker event parity, event age và aggregateVersion gaps.
9. Rollback cần biết events nào đã phát, không chỉ bật lại polling mù.
10. Retire old relay/cleanup fields khi đã đủ bằng chứng.

Không được dựa vào createdAt timestamp duy nhất để xác lập exactly-once boundary khi transactions concurrency và clock skew. Có thể cần control marker, outbox sequence, checkpoint và reconciliation.

## 36. Phân phối tới nhiều brokers hoặc destinations

Một outbox row có thể cần gửi tới Kafka và một integration endpoint khác. Vấn đề phức tạp hơn:

~~~text
Outbox event E100
    |
    +--> Kafka cluster A
    |
    +--> Message queue B
    |
    +--> Partner webhook C
~~~

Nếu chỉ có state=PUBLISHED chung, không biết destination nào đã chấp nhận. Có thể dùng **delivery records theo destination**, mỗi bản ghi có status/attempts/checkpoint riêng, hoặc publish một canonical event trước rồi bridge ra các destinations.

Để tránh dual-write mới:

- Một authoritative event stream làm nguồn phân phối nếu phù hợp.
- Per-destination delivery state và idempotency.
- Retry policy theo từng sink.
- Quan sát lag/health theo destination.
- Không coi một broker ACK nghĩa các broker khác đã nhận.
- Bảo vệ data residency/permissions khi fan-out.

Khi event có nhiều subscribers, **broker fan-out** thường tốt hơn để producer/relay phải tự quản từng consumer. Nhưng khi cần nhiều hệ broker, kiến trúc bridging cần đảm bảo nguồn/chịu trách nhiệm rõ.

## 37. Polling throughput và backpressure

Giả sử DB ghi 2.000 outbox events/giây, polling workers tổng cộng chỉ publish 1.500 events/giây. Backlog tăng trung bình:

\[
2{,}000 - 1{,}500 = 500 \text{ events/giây}.
\]

Sau 10 phút:

\[
500 \times 600 = 300{,}000 \text{ events}.
\]

Ngay cả khi relay không lỗi, hệ thống đã không bắt kịp. Nếu tiếp tục, oldest event age tăng và bảng outbox phình ra.

Giải pháp:

- Tăng relay throughput trong giới hạn DB và broker.
- Dùng batch claim/publish với maxInFlight phù hợp.
- Tăng worker song song giữa independent aggregates.
- Tối ưu indexes/query plan và connection pooling.
- Giảm payload/serialization overhead khi có thể.
- Tách high-volume events sang pipeline riêng.
- Chọn CDC nếu giảm polling overhead là bottleneck thực.
- Throttle producer hoặc ưu tiên business-critical events khi backlog vượt budget.
- Định nghĩa alert theo production rate, publication rate và oldest pending age.

Không tăng số workers vô hạn nếu broker quota/DB contention là nút cổ chai. Backpressure phải phản ánh capacity thật của cả hai đầu.

## 38. CDC lag cũng cần ngân sách

CDC pipeline latency có thể phân rã:

\[
L_{\text{CDC}} =
L_{\text{DB log availability}}
+ L_{\text{connector capture}}
+ L_{\text{transform}}
+ L_{\text{broker ACK}}
+ L_{\text{consumer wait}}.
\]

Một connector “running” không có nghĩa sự kiện đã đến consumer trong SLO. Có thể có lag do log read, transformation, broker send, topic partitions hoặc consumer group downstream.

Đặt hai SLI riêng:

- **Outbox publication latency:** từ local DB commit đến broker accept.
- **Business outcome latency:** từ command/event tới kết quả nghiệp vụ downstream.

Nếu Inventory xử lý chậm, outbox relay có thể khỏe nhưng Order vẫn không hoàn tất. Ngược lại, consumer khỏe mà relay lag thì event chưa tới.

Cần trace/correlation ID nối cả hai giai đoạn để phân biệt vấn đề publisher với consumer.

## 39. Observability: metrics cho polling

| Metric | Ý nghĩa |
|---|---|
| outbox_pending_count | Số events chờ |
| outbox_oldest_pending_age | Sự kiện lâu nhất chưa phát |
| outbox_claim_rate | Tốc độ lấy việc |
| outbox_publish_rate | Tốc độ broker accept |
| outbox_publish_failure_rate | Tỷ lệ thất bại |
| outbox_retry_attempts | Retry distribution |
| outbox_in_progress_count | Số rows đang được claim |
| outbox_expired_lease_count | Worker chậm/crash/timeout |
| outbox_quarantined_count | Bản ghi lỗi cần xử lý thủ công |
| outbox_db_query_latency | DB polling cost |
| outbox_broker_ack_latency | Độ trễ publish |
| outbox_cleanup_lag | Rủi ro phình bảng |
| relay_worker_count/health | Năng lực worker |
| event_age_at_publish | Trễ thực tế đến broker |

Một dashboard nên hiển thị **rate** và **age**. Một queue có 1.000 events có thể ổn nếu xử lý 50.000/s, nhưng nguy hiểm nếu oldest age = 2 giờ và SLO = 30 giây.

## 40. Observability: metrics cho CDC

| Metric | Ý nghĩa |
|---|---|
| connector_running/task_status | Connector có hoạt động? |
| source_log_position_lag | Độ lệch vị trí đọc log |
| source_commit_to_capture_lag | Thời gian từ commit đến capture |
| sink_publish_latency/error | Broker có nhận data? |
| replication_slot_retained_bytes | Áp lực log giữ lại |
| WAL/binlog disk usage | Rủi ro storage |
| connector_restarts/rebalances | Độ ổn định |
| snapshot_progress | Trạng thái load ban đầu |
| transform_failure_count | Lỗi schema/routing |
| source_to_sink_record_rate | Thông lượng |
| event_age_at_sink | Tuổi event lúc xuất |
| consumer_lag | Tiến độ downstream |

Tên metric thực tế do DB/connector version quyết định. Dashboard cần được xây từ những trường thật mà hệ thống phát ra, không giả định mọi connector cùng metric names.

### Logs và traces

Ghi:

~~~json
{
  "eventId": "b8f3a111-60d0-4d53-9b50-2d79113e74e1",
  "aggregateId": "O-101",
  "eventType": "OrderSubmitted",
  "relayMode": "POLLING",
  "workerId": "relay-2",
  "attempt": 3,
  "action": "PUBLISH_CONFIRMED",
  "durationMs": 112,
  "correlationId": "checkout-55"
}
~~~

Không log toàn payload có PII. Tránh eventId/aggregateId làm metric labels cardinality vô hạn; dùng structured logs/traces có quyền truy cập, và metrics aggregate theo loại lỗi/topic/service.

## 41. Alert và mức độ ưu tiên sự cố

Các alert có khả năng hành động:

- Oldest pending age vượt business publication SLO.
- Publish failure rate tăng mạnh hoặc broker unavailable.
- Pending count tăng liên tục dù workers hoạt động.
- Quarantined records xuất hiện trên event critical.
- CDC source log retention headroom giảm nhanh.
- Connector stopped/task failed hoặc offset không tiến.
- AggregateVersion gaps sau deploy/migration.
- Consumer duplicates tăng bất thường.
- Relay DB query load làm ảnh hưởng primary OLTP.
- Một service vẫn commit business state nhưng outbox publishing ngừng.

Mức ưu tiên nên phản ánh **business impact**. Một OrderSubmitted chưa đến Inventory 20 phút có thể cần xử lý ngay; một analytics aggregation event trễ 2 phút có thể ít khẩn hơn.

Không page chỉ vì một counter tăng nếu đây là giai đoạn backfill có kế hoạch và vẫn trong SLO; nhưng không bỏ qua một event bị blocked khi nó đại diện cho giao dịch quan trọng.

## 42. Runbook Polling Relay outage

1. Kiểm tra outbox_pending_count và oldest age.
2. Xác định source DB khỏe hay bị lock/CPU pressure.
3. Kiểm tra worker status, deployment, connection pool và logs.
4. Kiểm tra broker availability, ACK latency, throttling.
5. Xem IN_PROGRESS rows có lease expired hoặc stuck.
6. Không reset hàng loạt state khi chưa biết event nào đã tới broker.
7. Khôi phục worker, cho expired leases được reclaim theo policy.
8. Theo dõi duplicate rate và consumer idempotency.
9. Áp rate limit khi drain backlog để tránh gây overload.
10. Xác nhận pending age giảm và business workflow hoàn tất.
11. Điều tra root cause, cải thiện circuit breaker/index/retry nếu cần.

Không dùng SQL DELETE FROM outbox_events WHERE state!='PUBLISHED' để dọn backlog. Đó có thể xóa event intents mà domain đã commit.

## 43. Runbook CDC outage

1. Xác định connector/task lỗi hay lag, phiên bản triển khai.
2. Kiểm tra DB log/replication slot/binlog retention và disk.
3. Kiểm tra network, credentials, permissions và connector offset store.
4. Kiểm tra sink broker/quota và transformation errors.
5. Xác định committed source position, last durable offset và khoảng gap có thể có.
6. Khôi phục connector bằng procedure được DB/connector hỗ trợ.
7. Nếu WAL/binlog cần thiết đã mất, không tự resume bằng offset ngẫu nhiên; lập kế hoạch snapshot/reconciliation.
8. Đo event parity giữa outbox và broker (event IDs/checkpoints) theo phạm vi khả thi.
9. Cho consumer xử lý duplicate idempotently; theo dõi ordering gaps.
10. Tránh backlog flush gây overload ở broker/consumers.
11. Có bằng chứng khôi phục tới mốc hiện tại trước khi đóng incident.

Một connector status=RUNNING không đủ để chứng minh không mất event. Cần metrics lag và reconciliation theo contract.

## 44. Phục hồi từ backup, restore và rollback deployment

Một trường hợp khó: restore database về snapshot 10 phút trước trong khi broker vẫn giữ event phát sau snapshot.

Sau restore:

- Outbox rows đã publish có thể xuất hiện lại với state=PENDING.
- Các rows mới hơn snapshot có thể không có trong DB được restore.
- Domain state có thể lùi so với events downstream đã xử lý.
- Event IDs có thể bị tái tạo khác nếu application retry workflow.
- CDC log positions/slots có thể không còn tương thích với checkpoint trước restore.

Cần **recovery plan cho toàn chuỗi**, không chỉ backup DB:

1. Đánh giá mốc DB backup và mốc broker event commit.
2. Lưu eventId, aggregateVersion và nguồn transaction để đối soát.
3. Định nghĩa cách rebuild state hoặc compensate thay vì tái phát mù.
4. Kiểm tra CDC checkpoint/slot sau failover/restore.
5. Consumer phải idempotent và có stale-event policy.
6. Ghi audit các adjustments và window có nguy cơ mismatch.
7. Thử diễn tập restore trong môi trường an toàn.

Outbox giúp reliable publication bình thường, nhưng không tự biến DB restore và broker log thành một transaction atomic xuyên thời gian.

## 45. Bảo mật và dữ liệu nhạy cảm

Outbox là một bản sao dữ liệu nghiệp vụ trong database producer. CDC thêm một tuyến đưa dữ liệu từ log sang platform ngoài DB.

Yêu cầu:

- Encrypt DB/broker connections theo chính sách.
- Least privilege cho polling worker (SELECT/UPDATE đúng bảng).
- Least privilege cho CDC connector (logical replication/binlog permissions cần thiết, không cấp superuser mặc định).
- Secrets trong secret manager, có rotation.
- Giới hạn topic/tenant mà connector được publish.
- Tách quyền vận hành connector khỏi quyền sửa business state khi có thể.
- Giữ dữ liệu nhạy cảm tối thiểu trong payload/headers.
- Audit manual replay, redrive và config changes.
- Thiết kế retention/privacy cho outbox, broker, DLQ và logs.
- Không xuất raw DB changes ngoài phạm vi outbox nếu không được phê duyệt.
- Bảo vệ payload khỏi code injection/schema bombs và giới hạn kích thước.
- Kiểm tra tenant authorization ở consumer, không tin tenantId tự báo cáo từ payload.

Đặc biệt, một CDC connector được cấu hình capture cả DB thay vì chỉ outbox có thể vô tình công bố bảng chứa PII hoặc secrets. Phạm vi table capture và destination permissions phải được review.

## 46. Kiểm thử lỗi: bài test quan trọng hơn happy path

| Test | Kích hoạt | Kết quả cần quan sát |
|---|---|---|
| DB rollback | Domain transaction thất bại | Không tồn tại outbox event đã commit |
| Crash sau DB commit | Kill service trước relay | Event vẫn tồn tại và có thể publish |
| Broker unavailable | Relay không gửi được | Pending/retry giữ bền, không xóa |
| ACK lost | Broker lưu nhưng worker không thấy ACK | Duplicate có thể xảy ra; consumer dedup |
| Crash sau broker ACK | Kill relay trước markPublished | Relay gửi lại; business effect không trùng |
| Two polling workers | Claim đồng thời | Không mất row; bounded duplicate |
| Expired lease | Worker chậm hơn lease | Zombie không ghi trạng thái claim mới |
| Poison payload | Serializer không đọc được | Quarantine/alert, không retry nóng |
| CDC restart | Connector down/restart | Resume hoặc reconcile, không gap không phát hiện |
| WAL/binlog retention exhausted | Connector lag vượt retention | Có recovery procedure, không claim resume thành công giả |
| Schema migration | Thay đổi outbox columns | Connector/transform compatible hoặc fail rõ |
| Key ordering | Publish v8/v9 cạnh tranh | Consumer bảo vệ state version |
| Backlog burst | Tạo nhiều events trong thời gian ngắn | Backpressure và SLO behavior đo được |
| Cleanup crash | Cleanup chạy cùng relay | Không xóa pending/in-progress chưa an toàn |
| DB restore | Restore snapshot cũ | Reconciliation tránh sai business state |
| Tenant isolation | Cross-tenant events | Không lộ hoặc ghi chéo dữ liệu |

Thành công phải được đánh giá cả **event durability, event delivery, consumer business outcomes và absence of unintended duplicates**, không chỉ connector alive.

## 47. Test theo mốc và đối chiếu event parity

Một phương pháp kiểm tra kỹ thuật trong môi trường thử nghiệm:

1. Ghi N domain transactions có stable event IDs.
2. Xác minh đúng N outbox intents đã commit.
3. Dừng broker và khởi động relay để quan sát backlog.
4. Khôi phục broker.
5. Thu thập event IDs tại destination.
6. So sánh **set unique event IDs** với outbox committed IDs.
7. Ghi riêng duplicate count và attempt distribution.
8. Xác minh consumer side effects chỉ một lần theo business key.
9. Với ordering-critical aggregates, xác minh sequence monotonicity.
10. Test reconnect/rebalance/failover một lần nữa ở cửa sổ khác.

Một lưu ý: nếu broker retention và cleanup đã xóa dữ liệu cũ, parity phải dựa trên log/audit/metrics trong cửa sổ có bằng chứng, không giả định có thể query toàn bộ lịch sử mãi.

## 48. Lựa chọn Polling hay CDC: khung quyết định

Hãy ghi câu trả lời cho mỗi câu:

1. Event rate trung bình và peak là bao nhiêu?
2. Publication p95/p99 latency SLO là bao nhiêu?
3. Primary DB chịu thêm polling read/update load được không?
4. Có đội/platform vận hành CDC connector, WAL/binlog, offset store không?
5. CDC có được DB engine và hosting provider hỗ trợ ở môi trường đang dùng không?
6. Nếu connector down vài giờ, retention log có đủ không?
7. Cần per-aggregate ordering mạnh đến đâu?
8. Outbox records có thể append-only không?
9. Có sẵn tracing, metrics, alarms và incident ownership không?
10. Dung lượng outbox và retention/audit requirements là bao nhiêu?
11. Khi retry, có chấp nhận duplicate và consumer đã idempotent không?
12. Có nhiều destinations hay một broker làm trung tâm?

### Ma trận gợi ý

| Tình huống | Hướng thường đáng cân nhắc |
|---|---|
| Hệ nhỏ, event rate thấp, đội vận hành gọn | Polling worker đơn giản |
| Publication SLO vài giây, DB còn capacity | Polling có index/batching |
| Event rate cao, polling làm nặng OLTP | CDC với platform vận hành tốt |
| Cần lag rất thấp, đã có Debezium/Kafka Connect | CDC |
| DB không cho replication log access | Polling |
| Nhiều topics, payload cần transform/version | Cả hai đều được; thiết kế routing/contract riêng |
| Strict per-aggregate order với nhiều publishers | Phải xét sequence/serialization dù dùng mode nào |
| Có legacy polling và muốn migrate | Cutover có checkpoint/parity, không dual-publish mù |

Không có kết luận “CDC luôn tốt hơn polling”. Một relay ít moving parts, dễ test và đáp ứng SLO có thể là lựa chọn tối ưu.

## 49. Mẫu thiết kế kiến trúc cho Polling

~~~text
Service:
  Ordering

Business transaction:
  Order state change + outbox INSERT in same database transaction.

Outbox:
  Stable UUID eventId, orderId partitionKey,
  eventVersion and aggregateVersion, payload snapshot.

Relay:
  2 workers.
  Bounded batch, SKIP LOCKED claim, per-row lease token.
  Broker ACK required before PUBLISHED update.
  Retry with backoff and jitter.
  Permanent serializer failures quarantined.

Ordering:
  Per-Order delivery preferred.
  Version guard in consumer; no claim-order guarantee assumed.

Cleanup:
  Retain PUBLISHED per business/audit policy.
  Never delete pending or unresolved events silently.

Observability:
  Pending count, oldest age, publish/ACK latency,
  retry rate, lease expiry and duplicate detection.

SLO:
  Outbox publish latency measured at source commit -> broker ACK.

Runbook:
  Recovery from broker outage, stuck leases,
  backlog, deployment and DB restore.
~~~

Các tham số worker/batch/lease phải được định lượng bằng benchmark, không chọn cố định theo mẫu.

## 50. Mẫu thiết kế kiến trúc cho CDC

~~~text
Service:
  Ordering

Business transaction:
  Order state change + outbox INSERT in same database transaction.

Source:
  PostgreSQL with supported logical decoding.
  Outbox table filtered explicitly.
  Change log retention and replication slot monitored.

Connector:
  CDC source + outbox event transformation.
  Durable offset/checkpoint store.
  Versioned connector configuration and managed secrets.

Destination:
  Kafka topic domain.orders.
  Message key orderId.
  eventId/type/version included in headers or payload.

Snapshot:
  Explicit initial snapshot/cutover policy.
  No accidental replay of old published history.

Ordering:
  DB commit log order within source scope.
  Consumer aggregateVersion and idempotency still required.

Recovery:
  WAL retention headroom alerts, connector restart,
  failover and resnapshot/reconciliation runbook.

Observability:
  Connector lag, log retained bytes, transform errors,
  broker ACK and consumer business outcome SLO.
~~~

CDC kết hợp tốt với outbox append-only khi được triển khai có kỷ luật, nhưng việc chọn connector không chuyển trách nhiệm correctness sang hạ tầng.

## 51. Tình huống nghiệp vụ: OrderSubmitted tới Inventory

Ordering submit Order O-101:

~~~text
Ordering DB transaction:
  orders[O-101] = SUBMITTED, version=8
  outbox[E101] = OrderSubmitted(O-101, version=8)
COMMIT

Relay:
  publish E101 to domain.orders, key=O-101

Inventory:
  consume E101
  create reservation once
  publish StockReserved or ReservationRejected
~~~

### Kịch bản 1: Broker down

Order đã SUBMITTED, E101 vẫn trong outbox. API có thể trả trạng thái PENDING_WORKFLOW; hệ thống không được hiển thị “hàng đã được giữ” trước khi Inventory xác nhận.

### Kịch bản 2: Relay publish trùng

Inventory inbox/business reservation key đảm bảo một OrderSubmitted intent không tạo hai reservations.

### Kịch bản 3: Event v9 đến trước v8

Nếu Inventory cần thứ tự, nó phải có version/gap strategy hoặc event contract đảm bảo phù hợp. Không áp v8 lên trạng thái đã phản ánh v9.

### Kịch bản 4: Order bị hủy trong lúc backlog

Khi E101 tới muộn, Inventory phải kiểm tra business validity và workflow state theo contract. Outbox bảo đảm event intent được phát, không bảo đảm một command cũ còn hợp lệ lúc consumer thực thi.

### Kịch bản 5: CDC connector lag nhiều phút

Ordering vẫn ghi outbox, nhưng inventory completion trễ. SLO business end-to-end có thể vi phạm dù local DB transaction success. Monitor event age và workflow pending state.

## 52. Tình huống nghiệp vụ: PaymentAuthorized và kết quả chưa rõ

Payment Service cập nhật payment state và ghi outbox PaymentAuthorized cùng transaction. Relay publish event đến Ordering.

Nếu relay gửi lại event, Ordering không nên xác nhận đơn hai lần hoặc phát RefundRequested hai lần. Cần dedup eventId và command/business operation IDs.

Nếu Payment gọi external provider trước khi DB commit và nhận timeout, **đây là vấn đề khác** so với outbox relay:

- Provider có thể đã authorize/capture.
- Payment phải dùng idempotency key và reconciliation.
- Không được chỉ retry “PaymentRequested” mù.
- Outbox chỉ được ghi event về một outcome mà Payment thực sự có bằng chứng/đã ghi nhận.
- UNKNOWN/PENDING_RECONCILIATION có thể là một trạng thái bền vững, không tự kết luận FAILED.

**Transactional Outbox giải quyết reliable propagation của state local đã commit**, không tự cung cấp exactly-once transaction với external payment provider.

## 53. Bài tập tính toán: backlog và độ trễ

**Đề bài:** Service tạo 1.200 events/giây. Polling workers publish được 900 events/giây khi broker khỏe. Ban đầu backlog bằng 0.

**Câu hỏi A:** Sau 5 phút backlog tăng bao nhiêu nếu tốc độ giữ nguyên?

\[
(1{,}200 - 900) \times 300 = 90{,}000 \text{ events}.
\]

**Câu hỏi B:** Nếu sau 5 phút producer ngừng hẳn và relay duy trì 900 events/giây, ít nhất mất bao lâu để giải phóng backlog này trong mô hình đơn giản?

\[
90{,}000 / 900 = 100 \text{ giây}.
\]

**Câu hỏi C:** Nếu relay tăng lên 1.500 events/giây trong khi producer tiếp tục 1.200 events/giây, thời gian tối thiểu để xóa backlog 90.000 events là bao nhiêu?

\[
90{,}000 / (1{,}500 - 1{,}200) = 300 \text{ giây}.
\]

**Câu hỏi D:** Vì sao các kết quả là lower-bound lý thuyết?

Vì còn DB contention, retries, serialization, broker acks, cleanup, key skew, downstream backpressure, worker startup và message processing latency.

**Câu hỏi E:** Nếu event age SLO là 10 giây, một polling interval 1 giây có bảo đảm đạt SLO không?

Không. Khi backlog tăng 90.000 records, publication age có thể lớn hơn rất nhiều so với polling interval.

## 54. Bài tập so sánh Polling và CDC

Cho hai hệ thống:

**Hệ A:** 50 events/giây, publication SLO 5 giây, PostgreSQL vừa phải, 3 người vận hành, chưa có CDC platform.

**Hệ B:** 20.000 events/giây, publication SLO dưới 500 ms ở p95, có đội DBA/SRE vận hành Debezium và Kafka Connect, DB cho logical replication.

Phân tích:

- Hệ A có thể bắt đầu với polling worker có index, batch, retry, idempotency và alert.
- Hệ B có lý do mạnh để benchmark CDC, monitor WAL/slot và connector/sink lag, nhưng vẫn phải kiểm chứng SLO và capacity.
- Cả hai cần outbox local transaction, stable eventId, consumer dedup, schema, cleanup và recovery.
- Hệ A không “sai kiến trúc” vì không dùng CDC.
- Hệ B cũng có thể cần tối ưu outbox payload, broker partitions và consumer throughput; đổi sang CDC không tự giải quyết tất cả bottlenecks.

**Câu hỏi mở:** Nếu cùng aggregate có 5.000 events/giây và yêu cầu strict processing order, CDC có cho phép tăng consumer replicas tùy ý không? Không: hot key và domain serialization vẫn có thể là giới hạn.

## 55. Checklist trước khi triển khai

### Producer và DB transaction

- [ ] Business state và outbox insert nằm cùng local database transaction.
- [ ] Outbox eventId ổn định, schema/type/version rõ.
- [ ] Payload phản ánh committed business fact, không phải state suy ra từ cache ngoài transaction.
- [ ] Domain invariants và command idempotency được bảo vệ.
- [ ] Có aggregateId/version nếu ordering quan trọng.
- [ ] Không publish broker và coi nó atomic với DB chỉ vì cùng @Transactional.
- [ ] Có giới hạn payload và bảo vệ PII.

### Polling relay

- [ ] Query pending có index phù hợp.
- [ ] Batch/interval/workerCount được chọn theo benchmark.
- [ ] Claim có phạm vi transaction ngắn và tránh tranh chấp.
- [ ] Lease expiry và zombie worker được xử lý.
- [ ] Không markPublished trước broker confirmation.
- [ ] Có retry/backoff/jitter và phân loại permanent errors.
- [ ] Quarantine records không publish được với runbook.
- [ ] Cleanup chỉ xóa sau khi xác nhận và hết retention.
- [ ] Có backpressure khi broker hoặc DB quá tải.

### CDC relay

- [ ] DB hỗ trợ CDC và quyền đọc log phù hợp.
- [ ] Connector capture đúng outbox table, không lộ bảng nhạy cảm.
- [ ] Snapshot/cutover policy được ghi rõ.
- [ ] Offset/checkpoint store bền và có recovery procedure.
- [ ] WAL/binlog/replication slot retention được monitor.
- [ ] Có test connector restart, schema migration và DB failover.
- [ ] Đã định nghĩa routing/topic/key và transform version.
- [ ] Delete/cleanup outbox không trở thành domain event ngoài ý muốn.
- [ ] Có phương án resnapshot/reconcile khi mất log segment.

### Broker và consumer

- [ ] Broker ACK semantics/durability được hiểu rõ.
- [ ] Event ID được giữ nguyên khi retry/replay.
- [ ] Consumer idempotent, inbox marker và domain write atomic khi phù hợp.
- [ ] External side effects có idempotency/reconciliation.
- [ ] Per-key ordering requirement được ghi, không suy từ event timestamp.
- [ ] Retry/DLT không tự phá domain state sequence.
- [ ] Schema evolution có contract tests và unknown version handling.
- [ ] Không nhầm Published với BusinessProcessed.

### Vận hành

- [ ] Có publication age SLI và business completion SLO riêng.
- [ ] Có dashboard backlog, oldest age, publish errors, retries.
- [ ] CDC log retention headroom được cảnh báo.
- [ ] Có runbook broker outage, relay crash, connector lag và DB restore.
- [ ] Có audit manual replay và permission riêng.
- [ ] Đã thử fault injection cho DB rollback, ACK lost và crash after publish.
- [ ] Migration polling↔CDC có cutover marker/checkpoint và parity check.
- [ ] Data protection/retention áp dụng cho outbox, topic, DLQ và backups.

## 56. Mẫu ADR cho quyết định triển khai

~~~text
ADR: Order Outbox Relay

Context:
  Ordering persists domain transactions in PostgreSQL.
  OrderSubmitted must reach the broker reliably.
  Publication latency SLO: 5 seconds at p99.

Decision:
  Use transactional outbox.
  Start with polling publisher using bounded SQL claims.
  Each event has stable UUID, orderId key, eventVersion and aggregateVersion.

Atomicity:
  Order state transition and outbox insert share one DB transaction.

Delivery:
  At-least-once publication.
  Broker acknowledgement required before marking PUBLISHED.
  Consumers implement idempotency.

Retry:
  Exponential backoff with jitter and bounded attempts.
  Permanent conversion failures enter quarantine.

Concurrency:
  Worker claims use short transactions and lease tokens.
  Ordering-critical events use aggregate sequence safeguards.

Observability:
  Pending count, oldest event age, broker ACK latency,
  lease expirations, retries, business completion SLO.

Retention:
  Published events kept according to audit and recovery policy.
  No deletion of unresolved rows.

Alternative:
  CDC via Debezium/Kafka Connect.
  Reassess when SQL polling load or publication lag exceeds budget.

Recovery:
  Broker outage, crash after ACK, DB restore and event reconciliation.

Owner:
  Ordering Team; platform supports broker/DB infrastructure.
~~~

Đây là một ADR ví dụ, không phải cấu hình sẵn cho hệ thống bất kỳ. Thực thi bằng tests, alert, permissions và runbook.

## 57. Các câu hỏi thường gặp

**1. Polling outbox có phải đảm bảo exactly-once không?**  
Không. Nó giúp event intent không mất khi business transaction commit, nhưng relay có thể publish trùng sau crash/unknown ACK. Consumer phải idempotent.

**2. CDC có tránh hoàn toàn duplicate không?**  
Không. Connector restart/checkpoint/replay và downstream broker/consumer đều có thể phát sinh duplicate trong phạm vi khác nhau. Cần xác định guarantee thực tế của từng hệ.

**3. Nếu có CDC rồi, có cần outbox table không?**  
Không phải mọi use case đều bắt buộc, nhưng nếu muốn phát **business event có semantics được xác định trong cùng transaction**, outbox rất hữu ích. Raw CDC từ domain tables thường gắn với private schema và không tương đương domain event.

**4. Có thể xóa row ngay khi worker gọi send() không?**  
Không an toàn nếu chưa có broker confirmation. Nếu ACK unknown, cần giữ khả năng retry; lựa chọn at-least-once dẫn đến duplicate có thể xảy ra.

**5. SKIP LOCKED có bảo đảm event cùng aggregate publish theo thứ tự không?**  
Không. Nó giúp workers claim những rows không bị khóa; publication completion giữa workers có thể đảo.

**6. Có cần CDC khi lượng event thấp?**  
Không nhất thiết. Polling được index/monitor tốt có thể đơn giản và đủ SLO.

**7. Có cần polling khi đã dùng Debezium?**  
Thường không cần hai relays publish song song cùng event. Nếu vận hành migration/fallback, phải thiết kế cutover và dedup, không bật cả hai mù.

**8. Nếu connector ngừng lâu và WAL đã bị xóa?**  
Không giả định resume được. Cần kế hoạch resnapshot/reconciliation được hỗ trợ và kiểm chứng không mất business events.

**9. Outbox row PUBLISHED nghĩa là OrderConfirmed đã được xử lý chưa?**  
Không. Đó là tiến độ relay/broker. Business outcome của downstream cần trạng thái/SLI riêng.

**10. Tại sao không để mọi consumer SELECT outbox trực tiếp?**  
Vì outbox là implementation detail của owner; consumer trực tiếp đọc DB gây coupling, quyền truy cập rộng và khó scaling. Đường công bố chuẩn là event broker/API contract.

## 58. Kết luận

**Transactional Outbox tách việc ghi sự thật nghiệp vụ khỏi việc truyền thông điệp mà không đánh mất ý định phát event sau khi local transaction đã commit.** Từ bảng outbox đến broker, hệ thống có hai cách tiếp cận phổ biến: **Polling** bằng truy vấn định kỳ có claim/lease/retry và **CDC** đọc committed change log qua connector.

Polling thường dễ bắt đầu, ít hạ tầng hơn nhưng phải kiểm soát query load, worker concurrency, leases và backlog. CDC có thể đạt độ trễ thấp và giảm polling queries, nhưng đòi hỏi vận hành transaction logs, offsets, snapshot, connector compatibility và recovery nghiêm túc.

Dù chọn phương án nào, sự thật cốt lõi không thay đổi: **publish có thể trùng, consumer phải idempotent, ordering cần scope rõ, event backlog phải quan sát được, và business outcome quan trọng hơn tình trạng RUNNING của relay.**

Thiết kế tốt bao gồm một local transaction atomic, event ID/schema/key ổn định, broker confirmation, retry có giới hạn, cleanup an toàn, version/gap handling, consumer inbox/idempotency, SLO publication và kế hoạch khôi phục sau crash, outage, failover hoặc migration. Khi đó event từ Microservices có thể được phát đáng tin cậy trong điều kiện hệ thống phân tán vốn luôn có khả năng lỗi từng phần.
