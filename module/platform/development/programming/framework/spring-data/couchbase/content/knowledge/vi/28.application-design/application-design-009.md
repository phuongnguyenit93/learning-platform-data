# Phối hợp cập nhật dữ liệu với sự kiện bên ngoài một cách tin cậy

Trong ứng dụng **Spring Data Couchbase**, cập nhật một document thường kéo theo hành động ở hệ thống khác: gửi message vào Kafka, gọi API thanh toán, phát webhook, tạo hóa đơn, cập nhật kho hoặc gửi email. Vấn đề khó là **cập nhật dữ liệu và gửi sự kiện không nằm trong một transaction chung**. Nếu document đã commit nhưng message chưa đến nơi, các hệ thống lệch trạng thái; nếu message được phát rồi database rollback, consumer có thể hành động dựa trên một thay đổi chưa hề tồn tại.

Bài thuộc chương **Thiết kế ứng dụng** của module **SPRING_DATA_COUCHBASE**: phát triển tầng truy cập Couchbase bằng document mapping, Repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, tính nhất quán và vận hành. Trọng tâm là **transactional outbox**, **idempotent inbox**, **at-least-once delivery**, **reconciliation** và những giới hạn thực tế khi phối hợp Couchbase với dịch vụ bên ngoài.

> **Nguyên tắc:** Commit thay đổi nghiệp vụ và **ý định phát sự kiện** trong cùng một transaction Couchbase; giao việc gửi cho relay riêng, chấp nhận phát lặp và yêu cầu consumer xử lý idempotent. Không hứa exactly-once end-to-end chỉ từ retry, `@Transactional` hay broker acknowledgement.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chỉ ra dual-write failure khi gọi `repository.save(...)` và `publisher.send(...)` nối tiếp.
2. Phân biệt CAS, durability, transaction, at-most-once, at-least-once và exactly-once.
3. Thiết kế outbox event document cùng commit với domain document.
4. Dùng SDK `cluster.transactions().run(ctx -> ...)` với `ctx.get`, `ctx.replace` và `ctx.insert`; tránh external side effects trong transaction lambda.
5. Giải thích vì sao Spring `@Transactional`/`@TransactionalEventListener(AFTER_COMMIT)` không tự bảo đảm durable broker publish.
6. Xây relay polling hoặc DCP/CDC, biết giới hạn source connector phát phiên bản mới nhất.
7. Dùng CAS và lease khi nhiều workers claim outbox; biết tại sao vẫn có duplicate.
8. Dùng event ID ổn định và transactional inbox để chống double-apply.
9. Thiết kế xử lý webhook/consumer với duplicate, out-of-order, poison message và retry.
10. Hiểu ordering theo aggregate/partition, versioning và schema evolution.
11. Xử lý timeout ambiguous, crash window, retention/TTL, bảo mật đa tenant, observability và reconciliation.
12. Viết integration tests có fault injection, không chỉ kiểm thử happy path.

## 2. Tình huống xuyên suốt: Order chuyển PAID

Dữ liệu vận hành:

~~~text
Bucket shop
  Scope sales
    Collection orders
    Collection outbox_events
    Collection inbox_events

Order key: order::tenant-01::1001
Outbox key: outbox::tenant-01::evt-9b2c
Inbox key: inbox::invoice::tenant-01::evt-9b2c
~~~

Document Order:

~~~json
{
  "tenantId": "tenant-01",
  "orderId": "1001",
  "status": "PENDING",
  "totalMinorUnits": 245000,
  "currency": "VND",
  "businessVersion": 7
}
~~~

Khi thanh toán được **xác minh**, hệ thống cần:

- Đổi `status` từ `PENDING` sang `PAID` và nâng `businessVersion`.
- Phát `OrderPaid` cho dịch vụ hóa đơn, kho, thông báo.
- Chặn việc phát sai khi domain transaction rollback.
- Không làm mất ý định phát event sau crash.
- Cho phép payment callback và broker message được nhận lặp mà không tạo hai hóa đơn/đôi tác động.
- Đảm bảo dữ liệu tenant khác không lọt vào events hoặc consumers.

Bắt đầu từ **business invariants** trước khi chọn Kafka, Eventing hay SDK API.

## 3. Dual-write problem: cả hai thứ tự đều có lỗ hổng

**Ghi Couchbase trước, publish sau:**

~~~java
orderRepository.save(paidOrder);
brokerPublisher.send(orderPaidEvent);
~~~

~~~text
T0  Order=PAID commit thành công
T1  Process chết / broker không khả dụng
T2  Send chưa xảy ra
=> Database đã đổi; hệ thống ngoài không biết
~~~

**Publish trước, ghi Couchbase sau:**

~~~java
brokerPublisher.send(orderPaidEvent);
orderRepository.save(paidOrder);
~~~

~~~text
T0  Broker đã nhận OrderPaid
T1  Consumer gửi hóa đơn
T2  Database save thất bại/CAS conflict
=> Consumer xử lý event không phản ánh trạng thái committed
~~~

Thêm `try/catch`, retry hay đổi thứ tự không tạo atomic commit xuyên Couchbase và broker/HTTP.

## 4. Những bảo đảm không được đánh đồng

| Cơ chế | Bảo vệ | Không tự bảo vệ |
| --- | --- | --- |
| `@Version`/KV CAS | Conditional update theo version một document | Gửi event ra ngoài |
| Couchbase transaction | Atomicity của những Couchbase operations hỗ trợ trong cùng context | Kafka/HTTP/email bất kỳ |
| Sync durability | Mức xác nhận mutation trên replica/disk theo policy | Consumer xử lý business |
| SDK retry | Lặp operation khi SDK xác định phù hợp | Exactly-once cho mọi side effect |
| Broker at-least-once | Message có thể được phát/nhận nhiều lần trong phạm vi bảo đảm | Chống áp dụng business hai lần |
| Outbox | Ghi bền ý định phát cùng domain change | Consumer chỉ xử lý một lần |
| Inbox | Dedup/ghi nhận xử lý theo event ID | Thứ tự toàn cục |
| Saga | Workflow nhiều bước và compensation | ACID rollback đa hệ thống |

Một hệ thống đáng tin cần **phối hợp** các cơ chế này và ghi rõ phạm vi bảo đảm.

## 5. Kiến trúc transactional outbox

~~~text
Client / Payment provider
          |
          v
Verify + validate business command
          |
          v
+----- Couchbase transaction -----+
|                                  |
| Update Order -> PAID             |
| Insert Outbox(OrderPaid)         |
|                                  |
+--------- Commit -----------------+
                  |
           Outbox relay
                  |
          Kafka/Queue/HTTP
                  |
           Consumer
                  |
        Inbox + domain update
~~~

Điều bảo đảm trong Couchbase transaction: nếu commit thành công, Order change và outbox record cùng tồn tại; nếu rollback, cả hai không commit. **Gửi broker xảy ra sau**, có thể bị lặp và cần idempotency. Nếu transaction outcome ambiguous, cần tra cứu trạng thái/đối soát chứ không coi chắc chắn rollback.

## 6. Schema outbox event

Document `outbox_events` minh họa:

~~~json
{
  "type": "outbox_event",
  "eventId": "evt-9b2c",
  "tenantId": "tenant-01",
  "aggregateType": "Order",
  "aggregateId": "order::tenant-01::1001",
  "aggregateVersion": 8,
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T03:00:00Z",
  "nextAttemptAt": "2026-11-25T03:00:00Z",
  "status": "PENDING",
  "attempts": 0,
  "payload": {
    "orderId": "1001",
    "amountMinorUnits": 245000,
    "currency": "VND"
  }
}
~~~

Quy tắc thiết kế:

- `eventId` là identity ổn định cho một **logical event**.
- `aggregateId` định danh entity nguồn; `aggregateVersion` hỗ trợ ordering.
- `schemaVersion` áp dụng cho **event contract**, không phải CAS.
- `occurredAt` là thời điểm nghiệp vụ, không dùng làm unique global sequence.
- `nextAttemptAt` phục vụ relay; tránh trường thiếu/missing khó lập index.
- `status` và `attempts` là metadata publisher, không thuộc payload public.
- `payload` tối giản, không chứa mật khẩu/token/PII không cần thiết.
- Document được **insert cùng transaction** với cập nhật Order.

## 7. SDK transaction: domain state và outbox cùng commit

Java SDK 3.x có `cluster.transactions().run(...)` và transactional KV API như `ctx.get`, `ctx.replace`, `ctx.insert`.

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.transactions.TransactionGetResult;

public void confirmPaid(
        Cluster cluster,
        Collection orders,
        Collection outbox,
        String orderKey,
        String eventKey,
        String eventId,
        String tenantId) {

    cluster.transactions().run(ctx -> {
        TransactionGetResult current = ctx.get(orders, orderKey);
        JsonObject order = current.contentAs(JsonObject.class);

        if (!tenantId.equals(order.getString("tenantId"))) {
            throw new SecurityException("Wrong tenant");
        }
        if (!"PENDING".equals(order.getString("status"))) {
            throw new IllegalStateException("Invalid transition");
        }

        Long oldVersion = order.getLong("businessVersion");
        if (oldVersion == null) {
            throw new IllegalArgumentException("Version missing");
        }
        long nextVersion = oldVersion + 1;

        order.put("status", "PAID");
        order.put("businessVersion", nextVersion);

        JsonObject outboxEvent = JsonObject.create()
                .put("type", "outbox_event")
                .put("eventId", eventId)
                .put("eventType", "OrderPaid")
                .put("tenantId", tenantId)
                .put("aggregateId", orderKey)
                .put("aggregateVersion", nextVersion)
                .put("schemaVersion", 1)
                .put("status", "PENDING")
                .put("attempts", 0)
                .put("nextAttemptAt", "2026-11-25T03:00:00Z")
                .put("payload", JsonObject.create()
                        .put("orderId", order.getString("orderId")));

        ctx.replace(current, order);
        ctx.insert(outbox, eventKey, outboxEvent);
    });
}
~~~

Lưu ý:

1. `orders` và `outbox` là các `Collection` handles đúng keyspace, có quyền cần thiết.
2. Hai mutations **đều dùng `ctx`** trong cùng transaction; không gọi `orders.upsert(...)` bên ngoài `ctx`.
3. Xác định `eventId`/`eventKey` **trước** transaction callback; không tạo event ID mới trong mỗi retry.
4. Transaction framework có thể chạy lại lambda sau conflict/transient failures. **Không gửi Kafka, gọi HTTP, email hay side effect ngoài Couchbase trong callback**.
5. Đoạn này là **khung SDK**: production phải kiểm tra paymentId/amount/currency, schema, auditing, type discriminator và logic chống duplicate payment.
6. SDK raw JSON không tự chạy Spring Data `@Field`/`@Version`/converter/callback. Nếu cùng ghi entity qua Repository, cần document contract và integration test.
7. `nextAttemptAt` phải được lấy từ clock/application policy tại điểm phù hợp; chuỗi literal chỉ để minh họa hình dạng dữ liệu.
8. Không tự suy rằng broker đã nhận event chỉ vì transaction database thành công.

## 8. Tại sao không gửi message trong transaction callback?

Sai:

~~~java
cluster.transactions().run(ctx -> {
    // ctx.replace(...)
    brokerPublisher.send(event); // external side effect!
    // ctx.insert(...)
});
~~~

Một retry có thể **chạy lại callback**. Message có thể được gửi nhiều lần, ngay cả khi transaction attempt ban đầu rollback. Nếu broker chậm, transaction giữ resources lâu, tăng conflict/timeout.

Transaction callback nên chỉ chứa **Couchbase transactional operations** và computation thuần, không gửi mail/HTTP/mutation qua SDK raw bên ngoài context.

## 9. Spring `@Transactional` không bao trùm broker mặc định

~~~java
@Transactional
public void onPayment() {
    orderRepository.save(paid);
    kafkaTemplate.send("orders", event);
}
~~~

Không có gì trong đoạn trên tự chứng minh Couchbase write và Kafka send được commit chung. Transaction management của Spring Data Couchbase và broker integration cần kiểm chứng **theo version, cấu hình và API**; raw `Collection.upsert(...)` cũng không tự enlist vào Spring transaction chỉ vì dùng cùng `Cluster`.

Nếu dùng Spring transaction integration, phải test thật rằng cả **Order** và **Outbox** cùng commit/rollback, không chỉ unit-test annotation tồn tại.

## 10. `AFTER_COMMIT` callback không thay outbox

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
void afterPaid(OrderPaid event) {
    brokerPublisher.send(event);
}
~~~

Nếu JVM chết **sau DB commit nhưng trước callback**, event có thể mất. AFTER_COMMIT phù hợp đánh thức relay như một **optimization** khi đã có durable outbox. Nếu tín hiệu đánh thức mất, relay polling/CDC vẫn phải có cách tìm record `PENDING`.

## 11. Keyspace, index và expiry cho outbox

Ví dụ bố trí:

~~~text
shop.sales.orders
shop.sales.outbox_events
shop.sales.inbox_events
~~~

Cần xác định:

- Event keys ổn định, unique và không trùng giữa tenants.
- Broker routing được cấu hình/allowlist, không lấy endpoint từ user input thô.
- Một index riêng cho `status`/`nextAttemptAt` nếu dùng polling.
- RBAC phân vai publisher/relay/consumer; không cho mọi worker sửa mọi Order.
- Backup/restore, retention và capacity plan.
- **Không bật TTL ngắn cho outbox PENDING/LEASED/DEAD**, nếu việc hết hạn sẽ xóa ý định phát chưa hoàn tất.
- Nếu bucket/collection có `maxExpiry`, phải kiểm tra tác động đến outbox/inbox.
- Cơ chế làm sạch SENT chỉ khi đã đủ retention/audit/replay policy.

## 12. Relay: polling hoặc CDC/DCP

Hai kiến trúc:

**Polling application-managed**

~~~text
Query eligible PENDING events
    -> Claim CAS + lease
    -> Publish broker/HTTP
    -> Mark SENT on ack
    -> Retry/reconcile on failure
~~~

**Change Data Capture**

~~~text
Couchbase documents
    -> DCP / Couchbase Kafka Source Connector
    -> Kafka topic
    -> Consumers
~~~

Polling cho phép tự quản lý attempts/retries/lease, nhưng phải lập index và bảo vệ concurrency. DCP giảm scanning nhưng có **ordering và document-history limitations**. Cả hai cần idempotent consumer.

## 13. DCP/Kafka Connector không cam kết mọi document version

Couchbase Kafka Source Connector dùng **Database Change Protocol (DCP)**; tài liệu bảo đảm **at-least-once delivery của phiên bản mới nhất của từng document**.

Ví dụ một Order thay đổi nhanh:

~~~text
Order document: V1(PENDING) -> V2(PAID) -> V3(REFUNDED)
Connector offline hoặc xử lý trễ -> có thể chỉ thấy V3
~~~

Không dùng CDC của **mutable Order document** làm source duy nhất nếu downstream bắt buộc nhận đủ **OrderPaid rồi OrderRefunded**. Các hướng:

- Ghi **immutable event document** riêng cho mỗi logical transition (mỗi eventId một key).
- Hoặc cấu hình **change history** nếu deployment/retention/connector hỗ trợ, với giới hạn thời gian lịch sử.
- Giữ checkpoint/replay và kiểm tra rằng events không bị TTL xóa trước khi connector bắt kịp.

Connector có thể replay sau restart, order trong cùng vBucket được bảo toàn theo phạm vi documented (ngoại trừ rewind), **không bảo đảm global ordering giữa các vBuckets**. Expiry event có thể được publish sau khi document bị purge, không chính xác ngay tại TTL deadline.

**Cực kỳ quan trọng:** nếu outbox record mutable chuyển nhanh từ `PENDING` sang `SENT`, source connector có thể chỉ phát **latest state SENT**, không phát trạng thái PENDING. Với CDC event log, ưu tiên immutable event docs và giữ dispatch state riêng hoặc dùng cách extraction khác được test kỹ.

## 14. Eventing Service không tự tạo exactly-once HTTP side effect

Couchbase Eventing Service có thể chạy functions khi document mutate hoặc timer fire. Nó hữu ích cho near-real-time processing, nhưng handlers có thể coalesce những thay đổi liên tiếp trên cùng document, và HTTP call từ handler không trở thành participant của Couchbase transaction.

Không dùng Eventing làm bằng chứng “mọi domain transition chắc chắn được phát đúng một lần” nếu chưa thiết kế event identity, retry, dedup và replay. Với yêu cầu mỗi business event bắt buộc xuất hiện, ưu tiên durable immutable event documents/transactional outbox phù hợp.

## 15. Polling relay: truy vấn events đủ điều kiện

Nếu dùng application-managed relay, một query có thể chọn:

~~~sql
SELECT META(e).id AS id,
       e.eventId AS eventId,
       e.aggregateId AS aggregateId,
       e.eventType AS eventType,
       e.attempts AS attempts,
       e.nextAttemptAt AS nextAttemptAt
FROM `shop`.`sales`.`outbox_events` AS e
WHERE e.type = "outbox_event"
  AND e.status = "PENDING"
  AND e.nextAttemptAt <= $nowIso
ORDER BY e.nextAttemptAt ASC, META(e).id ASC
LIMIT $batchSize;
~~~

Tất cả timestamps phải tuân một định dạng UTC chuẩn để so sánh chuỗi không bị lệch. Nếu `nextAttemptAt` có thể thiếu/NULL, điều kiện query phải chủ động xử lý (hoặc chuẩn hóa schema từ lúc insert).

Điểm cần lưu ý:

- `LIMIT 100` chỉ giới hạn **result rows**, không buộc Query Service chỉ scan 100 index entries.
- GSI có thể lag sau mutation; relay **phải poll lặp lại**, không chỉ chạy một lần sau commit.
- `QueryScanConsistency.REQUEST_PLUS` có thể cải thiện freshness trong một query, nhưng không thay CAS claim.
- Index và throughput của Query Service phải được benchmark với tỷ lệ event tạo mới và purge.
- Job cần có lịch restart/recovery; một lần query không thấy PENDING không chứng minh mọi event đã phát.

## 16. Index phục vụ polling có chủ đích

Một partial GSI minh họa:

~~~sql
CREATE INDEX idx_outbox_due
ON `shop`.`sales`.`outbox_events`(
    status, nextAttemptAt, eventId
)
WHERE type = "outbox_event";
~~~

Đây là ví dụ DDL để thảo luận, không phải index tối ưu mặc định cho mọi workload. Khi triển khai, kiểm tra:

1. Predicate trong SQL++ có phù hợp partial index không?
2. Có đọc cả `LEASED` đã hết hạn không? Nếu có, query/index phục hồi lease cần thiết kế riêng.
3. Số record `SENT` được lưu bao lâu?
4. `EXPLAIN` có dùng index dự kiến không?
5. Query lặp mỗi giây có cạnh tranh Query Service với OLTP không?
6. Có thể tách relay work queue theo tenant/partition không?
7. Khi nhiều workers đều query cùng record, **CAS** mới xác định ai claim thành công.

Index phục vụ tìm candidates, **không đóng vai trò lock hay distributed queue lease**.

## 17. CAS claim và lease khi nhiều workers

Timeline:

~~~text
Worker A: GET outbox::evt-1, CAS=A, status=PENDING
Worker B: GET outbox::evt-1, CAS=A, status=PENDING
Worker A: CAS replace status=LEASED -> thành công, CAS=B
Worker B: CAS replace với CAS=A -> CasMismatchException
=> Tại thời điểm claim đó A thắng
~~~

Code minh họa một bước claim:

~~~java
GetResult current = outbox.get(eventKey);
JsonObject event = current.contentAsObject();

if (!"PENDING".equals(event.getString("status"))) {
    return; // Skip; logic thực tế còn xử lý lease hết hạn
}

event.put("status", "LEASED");
event.put("leaseOwner", workerId);
event.put("leaseUntil", leaseUntilIso);

outbox.replace(
        eventKey,
        event,
        replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true));
~~~

Trong production:

- Lease có deadline và recovery cho worker crash.
- Nếu lease hết hạn, worker khác có thể claim lại; **hai lần publish vẫn có thể xảy ra**.
- Worker đang giữ lease cần check owner/fencing token và CAS khi mark SENT.
- Đồng hồ giữa pods có thể lệch; quy ước clock/deadline/tolerance rõ.
- Nếu số workers lớn, dùng backoff/jitter và giới hạn claim concurrency.
- Cập nhật TTL không được vô tình xóa events trước khi relay hoàn thành.
- Nếu event status được CDC gửi làm payload, mutations PENDING→LEASED→SENT phải được lọc tách khỏi **immutable domain event**.

CAS chỉ xác định ai được cập nhật **một version của outbox document**; không khóa bên broker hay HTTP provider.

## 18. State machine relay và những trạng thái cần lưu

~~~text
PENDING  --CAS claim--> LEASED
LEASED   --broker ACK--> SENT
LEASED   --retryable failure--> PENDING(nextAttemptAt=...)
LEASED   --worker crash / lease expire--> recoverable
PENDING/LEASED --permanent failure--> DEAD
SENT     --retention elapsed--> archived/deleted
~~~

Một record relay có thể có:

~~~json
{
  "status": "LEASED",
  "leaseOwner": "relay-07",
  "leaseUntil": "2026-11-25T03:05:00Z",
  "attempts": 3,
  "nextAttemptAt": "2026-11-25T03:05:00Z",
  "lastErrorCategory": "BROKER_TIMEOUT"
}
~~~

Quy tắc:

1. Chỉ mark `SENT` khi đã nhận acknowledgement theo **broker/provider contract**.
2. `SENT` chưa chắc consumer đã tạo hóa đơn; nó thường chỉ có nghĩa **đã phát tới broker**.
3. Sau timeout có thể ghi `UNKNOWN` hoặc để lease hồi phục; phải bảo đảm retry an toàn theo eventId.
4. Không để record `DEAD` biến mất âm thầm; cần DLQ/manual triage.
5. Có finite retry budget, backoff và jitter; đừng retry liên tục trên hot loop.
6. Mỗi transition có CAS/owner check để worker cũ không ghi đè worker mới.
7. Khi job restart, scan cả `PENDING` lẫn `LEASED` đã hết lease theo chính sách.

## 19. Cửa sổ lỗi: đã publish nhưng chưa mark SENT

~~~text
T0  Event PENDING
T1  Worker claim
T2  Broker nhận event, trả ACK
T3  JVM chết trước khi cập nhật status=SENT
T4  Lease hết, worker khác publish cùng eventId
=> Consumer nhận duplicate
~~~

Không thể “sửa” bằng cách mark SENT **trước** publish:

~~~text
T0  Đánh dấu SENT
T1  JVM chết trước khi gửi broker
=> Event mất vĩnh viễn dù trạng thái ghi đã gửi
~~~

Vì vậy transactional outbox thông thường chấp nhận **at-least-once publish**, không hứa exactly-once qua Couchbase+broker độc lập.

## 20. Event envelope: idempotency và version ổn định

Message bên ngoài nên có hợp đồng tường minh:

~~~json
{
  "eventId": "evt-9b2c",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "tenantId": "tenant-01",
  "aggregateId": "order::tenant-01::1001",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-25T03:00:00Z",
  "data": {
    "orderId": "1001",
    "amountMinorUnits": 245000,
    "currency": "VND"
  }
}
~~~

- Giữ **cùng eventId** qua mọi publish attempts của cùng logical event.
- `aggregateVersion` giúp chống áp dụng các events cũ lên state mới.
- `schemaVersion` giúp readers phân biệt V1/V2, không dùng CAS thay thế.
- `tenantId` phải được xác minh khi nhận; không tin một string không có authentication/routing.
- Payload tối thiểu; dùng business IDs và projection cần thiết, không phát full Spring entity chứa PII.
- Đặt message key theo `aggregateId` nếu broker hỗ trợ partitioning theo key và cần thứ tự cục bộ.
- Không tạo UUID khác trên mỗi retry hoặc khi callback thanh toán bị lặp.

## 21. Consumer at-least-once có thể nhận trùng dù relay đúng

Một consumer:

~~~java
void consume(OrderPaid event) {
    invoiceService.createInvoice(event.orderId());
    broker.acknowledge(event);
}
~~~

Lỗi:

~~~text
T0  Consumer tạo invoice thành công
T1  JVM chết trước khi broker ack/commit offset
T2  Broker giao lại cùng event
T3  Consumer tạo invoice thứ hai
~~~

Không có logic inbox/idempotency, **ít nhất một lần delivery** biến thành **nhiều lần business side effect**.

Một consumer phải xác định cái gì là *cùng logical event* và cái gì là *event mới hợp lệ*; không chỉ `if (orderId exists) return` nếu một Order có thể phát nhiều sự kiện khác nhau.

## 22. Transactional inbox: ghi receipt cùng cập nhật domain

Nếu consumer ghi dữ liệu vào Couchbase, có thể dùng transaction để atomically:

1. Ghi một **inbox receipt** với unique key theo eventId/consumer/tenant.
2. Áp thay đổi nghiệp vụ ở consumer (ví dụ tạo Invoice document).
3. Commit cả hai.

~~~text
Message OrderPaid(eventId=evt-9b2c)
           |
           v
Couchbase transaction
   |
   +-- Insert inbox::invoice::tenant-01::evt-9b2c
   +-- Insert invoice::tenant-01::order-1001
   |
  Commit
           |
           v
Acknowledge broker delivery
~~~

Nếu message bị giao lại:

- Receipt key đã tồn tại → nhận ra **event đã xử lý** và không tạo Invoice lần nữa.
- Nếu transaction rollback, receipt và Invoice cùng không commit, có thể retry message.
- Nếu commit đã thành công nhưng ack broker thất bại, lần giao lại tìm thấy receipt và có thể ack an toàn.

**Lưu ý:** Trong transaction, lỗi duplicate receipt/invoice có thể được SDK bọc vào exception của transaction; cần phân loại và kiểm tra receipt hiện hành, không giả định luôn bắt trực tiếp `DocumentExistsException`. Nếu có receipt cùng ID nhưng payload fingerprint khác, đó là **identity collision/tampering**, không được bỏ qua.

## 23. Code khung của inbox handler bằng SDK transaction

Ví dụ đơn giản với **hai insert** đồng thời atomically trong Couchbase:

~~~java
public void applyOrderPaid(
        Cluster cluster,
        Collection inbox,
        Collection invoices,
        OrderPaidMessage event) {

    String receiptKey = "inbox::invoice::"
            + event.tenantId() + "::" + event.eventId();

    String invoiceKey = "invoice::"
            + event.tenantId() + "::" + event.orderId();

    cluster.transactions().run(ctx -> {
        JsonObject receipt = JsonObject.create()
                .put("eventId", event.eventId())
                .put("tenantId", event.tenantId())
                .put("consumer", "invoice")
                .put("payloadHash", event.canonicalHash());

        JsonObject invoice = JsonObject.create()
                .put("orderId", event.orderId())
                .put("tenantId", event.tenantId())
                .put("status", "CREATED")
                .put("sourceEventId", event.eventId());

        ctx.insert(inbox, receiptKey, receipt);
        ctx.insert(invoices, invoiceKey, invoice);
    });
}
~~~

`OrderPaidMessage` và `canonicalHash()` là **kiểu/hàm ứng dụng minh họa**, không phải SDK types. Production code cần validate signature, event schema, tenant authorization và status transition trước transaction.

Nếu receipt đã tồn tại:

- Ngoài transaction, phân loại lỗi theo transaction API thực tế.
- Kiểm tra receipt đã commit, `eventId` và fingerprint phù hợp.
- Nếu match → coi là duplicate đã xử lý và ack.
- Nếu mismatch → fail closed/quarantine, không tự “skip success”.
- Nếu receipt chưa tồn tại nhưng Invoice key đã có → có thể là business conflict/legacy data, **không ghi nhận như duplicate thành công**.

Không gọi external email/payment API bên trong transaction callback; nếu side effect consumer cũng là external, dùng **một outbox tiếp theo** hoặc provider idempotency có kiểm chứng.

## 24. Inbox receipt cần retention đủ dài

Nếu consumer dedup trong 7 ngày nhưng broker có thể replay một message sau 30 ngày, receipt đã hết TTL sẽ không còn ngăn duplicate.

Chọn thời hạn theo:

- Broker retention và reprocessing horizon.
- SLA khôi phục từ backup.
- Manual replay/DLQ retention.
- Downstream event/ledger lifespan.
- Khả năng event IDs bị tái sử dụng.
- Bắt buộc pháp lý về lưu/xóa dữ liệu.
- Chi phí storage/index.

Có thể giữ receipt gọn `{eventId,consumer,tenant,hash,processedAt}` và archive lâu hơn, thay vì xóa ngay sau ack. **Không để bucket `maxExpiry` vô tình xóa receipt sớm hơn replay window**.

Ngay cả khi lưu receipt vô hạn, phải kiểm soát quy mô và quyền truy cập. Retention có tính chất business/security chứ không chỉ cleanup.

## 25. Event đến sai thứ tự: CAS không tự sắp messages

Ví dụ cùng một Order có:

~~~text
Version 8:  OrderPaid
Version 9:  OrderRefunded
~~~

Consumer nhận `OrderRefunded` trước `OrderPaid` vì retries, partitions hoặc các subscriptions khác nhau.

Nếu consumer chỉ làm:

~~~java
invoice.status = event.newStatus();
repository.save(invoice);
~~~

thì event cũ có thể ghi đè trạng thái mới.

Các chiến lược:

1. Gắn `aggregateId` làm partition key để giảm reorder trong một topic.
2. Ghi `aggregateVersion`/sequence monotonic.
3. Áp dụng state machine: chỉ cho phép transition hợp lệ.
4. Với event cũ (`version <= lastAppliedVersion`), xác minh và bỏ qua.
5. Với gap (`version > lastAppliedVersion+1`), defer/retry/reconcile nếu nghiệp vụ yêu cầu từng bước.
6. Dùng CAS/transaction khi ghi version mới vào consumer state.
7. Không giả định global ordering giữa partitions/vBuckets/topics hoặc consumers.
8. Không dùng `occurredAt` wall-clock làm total order khi clock skew có thể xảy ra.

**Thứ tự delivery và tính đúng business là hai tầng độc lập.**

## 26. Đặt partition key và thứ tự theo aggregate

Ví dụ Kafka:

~~~text
Topic orders.events
Key: order::tenant-01::1001
Value: OrderPaid(... aggregateVersion=8 ...)
~~~

Nếu key ổn định và partitioner cấu hình phù hợp, các messages của cùng aggregate thường vào cùng partition, giúp duy trì thứ tự **trong partition** khi không có replay/reordering từ producer/relay.

Nhưng:

- Không có thứ tự toàn cục giữa các aggregates.
- Hai producer/relay cùng phát các versions khác nhau có thể đảo thứ tự.
- Rebalance/replay và multiple topics có thể phá giả định đơn giản.
- EventId dedup và aggregateVersion guard vẫn cần thiết.
- Một aggregate có thể bị phân phối sai nếu key thay đổi sau migration.
- Cần một owner/sequence generator cho aggregate, không tự lấy CAS làm sequence business.

Nếu cần workflow strictly ordered, thiết kế keyed serializer/scheduler hoặc consumer state machine, không dựa vào “Kafka có thứ tự” như một câu tuyệt đối.

## 27. Webhook từ hệ thống ngoài: inbox bắt đầu từ cửa vào

Payment provider có thể gửi cùng webhook nhiều lần và **không bảo đảm đúng thứ tự**. Một handler nên:

1. Nhận **raw request body** và headers cần thiết.
2. Xác minh chữ ký/HMAC theo tài liệu provider, timestamp tolerance/replay protection.
3. Parse event schema, xác định `providerEventId`, account/tenant và event type.
4. Kiểm tra event có thuộc merchant/account được ủy quyền không.
5. Ghi durable inbound receipt/inbox hoặc xử lý domain+receipt trong transaction.
6. Trả 2xx/202 **sau khi đã chấp nhận bền** theo contract.
7. Nếu sẽ xử lý async, phải có worker/job recovery đọc inbox PENDING.
8. Nếu processing lỗi tạm thời, trả mã phù hợp cho provider retry hoặc xử lý nội bộ có chứng minh không mất.
9. Không đánh đồng nhận webhook với thanh toán đã chắc chắn hoàn tất; cần xác minh event/status/amount/currency theo contract.

Không log signature secrets/PCI/PII và không tin `tenantId` từ body khi chưa gắn với webhook endpoint/account credential xác thực.

## 28. Xử lý duplicate payment callback mà không phát lại event mới

Một business rule có thể là:

~~~text
PENDING + verified PaymentSucceeded(paymentId=X)
    -> PAID, emit OrderPaid(eventId derived from X)

PAID + same PaymentSucceeded(paymentId=X)
    -> idempotent success; không emit OrderPaid mới

PAID + different paymentId
    -> review/reconcile; không tự tạo second charge

REFUNDED + old PaymentSucceeded
    -> không đổi state về PAID
~~~

Cách thực hiện:

- Lưu `paymentId` đã xử lý trong domain document hoặc receipt bền vững.
- Dùng key/event ID ổn định theo provider transaction identity.
- Kiểm tra status transition và tổng tiền/currency.
- Transactionally insert receipt + update Order + outbox event.
- Nếu transaction commit ambiguous, đọc lại Order/receipt/outbox để đối soát.
- Với callback mới là sự kiện kinh doanh khác, không dedup theo mỗi `orderId`.

Ở đây, **exactly-once business effect** là một thuộc tính được thiết kế/kiểm thử dựa trên idempotency và invariants, không phải bảo đảm transport đúng một lần.

## 29. Gọi external payment API là một saga, không phải một DB transaction

Không nên:

~~~java
cluster.transactions().run(ctx -> {
    ctx.replace(orderDoc, paidBody);
    paymentProvider.capture(card); // side effect ngoài Couchbase
});
~~~

Một workflow hợp lý:

~~~text
Create Order(status=PENDING_CAPTURE)
   + Outbox(PaymentCaptureRequested)
            |
       Payment worker
            |
   Call provider with idempotencyKey
            |
    +-------+--------+
    |                |
 capture succeeded   failed/unknown
    |                |
 Verify result       retry/reconcile
    |
 Couchbase transaction:
  Order -> PAID
  Outbox -> OrderPaid
~~~

Nếu cần compensation (refund/release inventory), thiết kế **saga** với state transitions, idempotency, timeout và audit. Compensation **không phải rollback ACID**: một refund có thể thất bại, cần tiếp tục theo dõi trạng thái chưa giải quyết.

## 30. Retry, backoff, DLQ và poison events

Phân loại trước khi retry:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transient | Broker timeout, network flap, 503 | Retry bounded, exponential backoff + jitter |
| Rate limit | HTTP 429 | Tôn trọng retry-after/quota, không storm |
| Authorization | API key hết quyền, sai tenant | Dừng/fail closed, alert |
| Schema/validation | Unknown event type, missing required field | Quarantine/DEAD, sửa schema/migration |
| Business conflict | Invoice đã thuộc event khác | Reconcile, không lặp mù |
| Ambiguous outcome | HTTP timeout sau khi provider có thể đã xử lý | Lookup bằng idempotency key/provider reference |
| Lease conflict | CAS mismatch | Worker khác thắng, không publish từ claim cũ |

`DEAD`/DLQ là **điểm bắt đầu vận hành**, không phải chỗ xóa event để thống kê đẹp. Cần ghi original event ID, retry history, error category, owner, policy replay và trạng thái xử lý.

Một poison event không nên chặn vô hạn mọi events của tenant/partition; tuy nhiên bỏ qua nó có thể phá ordering của aggregate. Chọn chiến lược theo invariant.


## 31. Durability của Couchbase không bảo đảm bên ngoài đã nhận message

Couchbase cho phép yêu cầu durability như `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` hoặc `PERSIST_TO_MAJORITY` ở những deployment hỗ trợ. Durability nói về **xác nhận mutation tại Data Service**, không nói broker/HTTP receiver đã xử lý event.

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

collection.insert(
        id,
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY));
~~~

Đây là một **KV write độc lập**. Với transaction, cấu hình durability trong **transaction API**; không dùng `collection.insert` trực tiếp bên trong callback thay vì `ctx.insert`.

| Mốc xác nhận | Điều nó chứng minh | Không chứng minh |
| --- | --- | --- |
| Couchbase transaction commit | Domain+outbox đã commit cùng nhau | Broker nhận event |
| Sync durability | DB mutation đạt mức xác nhận được chọn | Consumer thực thi |
| Broker ACK | Broker nhận message theo policy | Invoice/payment thành công |
| Consumer inbox commit | Receipt + effect trong DB đã commit | External HTTP effect hoàn tất |
| HTTP 200 của provider | Provider trả kết quả theo contract | Exactly-once nếu provider không hỗ trợ |

Không lấy một cấp xác nhận để tuyên bố toàn bộ workflow đã hoàn tất.

## 32. Commit ambiguous và retry transaction

Một transaction có thể commit trên Server nhưng client không nhận được response. **Commit ambiguous** không đồng nghĩa rollback. Quy trình đúng:

1. Dùng business `commandId`/`paymentId` ổn định.
2. Giữ `eventId`/outbox key cố định xuyên mọi attempts.
3. Tra cứu Order state, receipt và outbox record sau khi cluster khả dụng.
4. Nếu Order PAID và outbox đúng command đã tồn tại, không phát một event logic mới.
5. Nếu dữ liệu không khớp, đưa vào reconciliation với dấu vết và audit.
6. Không tự sửa bằng hai raw writes **ngoài transaction**.
7. Khi chưa kết luận được, trả processing/unknown thay vì tuyên bố chắc failed.
8. Không gọi external side effects trong transaction lambda, vì lambda có thể được retry.

## 33. Kafka transactions không tự enlist Couchbase

Kafka transactional producer/stream processing có thể cung cấp exactly-once semantics **trong phạm vi Kafka được cấu hình**, nhưng:

~~~text
Couchbase transaction commit
         |
Kafka producer transaction commit
~~~

vẫn là **hai resource boundaries**. Không có atomic commit xuyên cả hai chỉ vì dùng Kafka transaction.

Khi gọi “exactly once”, hãy nêu rõ là **một message Kafka**, **một consumer invocation**, **một Invoice document**, hay **một external payment capture**. Chỉ định và kiểm chứng bảo đảm theo **business effect**, không theo tên tính năng transport.

## 34. Duplicate vẫn có chi phí và rủi ro

Ngay cả với inbox:

- Duplicate events tốn network, CPU, transaction reads.
- Receipt TTL ngắn khiến replay cũ có thể bị xử lý lần nữa.
- Cùng eventId nhưng payload khác có thể che tampering.
- Retry storm tạo hot partition/timeout.
- Provider có thể chỉ lưu idempotency key trong một cửa sổ hữu hạn.
- External HTTP side effect thực hiện trước receipt vẫn có thể bị lặp.

Vì vậy cần bounded retry, rate limiting, payload fingerprint, durable receipt, DLQ và đối soát provider. **Idempotency không chỉ là một `Set<String>` trong RAM**.

## 35. Event schema evolution có version rõ

~~~json
{
  "eventId": "evt-9b2c",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "aggregateId": "order::tenant-01::1001",
  "aggregateVersion": 8,
  "data": {
    "orderId": "1001",
    "amountMinorUnits": 245000,
    "currency": "VND",
    "paymentMethod": "CARD"
  }
}
~~~

- `schemaVersion` của event độc lập với Spring `_class`/document schema.
- Ưu tiên thêm optional fields có defaults rõ.
- Hỗ trợ V1/V2 trong migration và replay window.
- Unknown event type/version phải có policy; financial side effect nên quarantine nếu không hiểu.
- Contract tests kiểm tra producer/consumer trước deploy.
- Đừng serialize full Spring entity rồi coi đó là event API.
- Replay sau nhiều năm có thể gặp event format cũ.

Một JSON parse được chưa chắc là một message **tương thích nghiệp vụ**.

## 36. Reactive relay cần bounded concurrency và per-event outcomes

Ví dụ orchestration:

~~~java
Flux.fromIterable(candidateIds)
        .flatMap(id -> claimPublishAndMark(id), 8);
~~~

`claimPublishAndMark` là helper ứng dụng trả `Mono<PublishOutcome>`, không phải SDK API. Nó thực hiện CAS claim, async broker send, chờ ACK và chuyển trạng thái/đặt retry.

Cần tránh:

- `Mono.just(blockingSend())` trên WebFlux event loop.
- `subscribe()` rời lifecycle rồi trả success.
- `onErrorResume(e -> Mono.empty())` che mất failures.
- `retry(3)` trên toàn batch khiến replay cả events đã gửi.
- Nhầm `flatMap(...,8)` là concurrency cap toàn bộ pods.
- Coi cancellation/timeout là bằng chứng broker chưa nhận event.

Có global bulkhead, rate limiting, retry budget và metrics theo pending age/duplicate/timeout.

## 37. TTL và retention cho outbox, inbox

| Dữ liệu | Chính sách | Nguy cơ TTL quá ngắn |
| --- | --- | --- |
| Domain Order | Business/legal retention | Không đối soát được |
| Outbox PENDING/LEASED/DEAD | Giữ tới khi được xử lý/reconcile | Mất event chưa phát |
| Outbox SENT | Audit/replay, rồi archive | Mất bằng chứng phát |
| Inbox receipt | Trùm broker/DLQ/backup replay horizon | Duplicate cũ áp lại |
| Immutable CDC events | Đủ cho connector ingestion/recovery | DCP lag bỏ lỡ event |
| Saga state | Cho tới khi workflow resolved | Không resume được |

Cần kiểm tra `maxExpiry` ở bucket/collection và cách SDK/Spring `@Expiry` áp dụng. Không mặc định một outbox PENDING có thể tự hết hạn sau vài giờ. TTL không phải đồng hồ chính xác cho thanh toán/refund; Eventing/expiry purge có thể đến trễ.

## 38. Bảo mật đa tenant và payload tối thiểu

1. Tenant lấy từ authenticated context/payment merchant mapping.
2. Webhook phải kiểm chứng signature, timestamp và chống replay.
3. Outbox `eventId`/`aggregateId` không chứa secret/token.
4. Consumer xác thực event source, tenant và target resources.
5. Không cho message payload chọn bucket/scope/collection hay callback URL bất kỳ.
6. Topic/endpoint/routing lấy từ allowlist, dùng RBAC tối thiểu.
7. Không gửi raw entity chứa PII khi downstream không cần.
8. Bảo vệ broker, DLQ, backup, logs và retention.
9. Không log card data, JWT, signatures, encryption keys hay customer PII.
10. Các yêu cầu xóa dữ liệu phải tính cả events được nhân bản và audit constraints.

**At-least-once nhưng rò dữ liệu tenant vẫn không phải hệ thống đáng tin.**


## 39. Observability phải theo dõi từ outbox đến business effect

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| `outbox_pending_count` | Còn bao nhiêu events chưa phát? |
| `outbox_oldest_pending_age_seconds` | Event lâu nhất đã chờ bao lâu? |
| `outbox_lease_expired_count` | Có worker crash/stuck không? |
| `outbox_publish_attempts_total` | Có retry storm không? |
| `outbox_ack_latency_p95` | Broker/provider nhận event có chậm không? |
| `outbox_dead_count` | Bao nhiêu poison events cần sửa? |
| `inbox_duplicates_total` | Consumer nhận trùng nhiều không? |
| `consumer_apply_latency_p95` | Business effect có bị chậm không? |
| `aggregate_version_gap_count` | Consumer bị out-of-order/gap không? |
| `webhook_signature_failures` | Có tấn công hoặc sai config? |
| `saga_unresolved_age_seconds` | Workflow nào bị kẹt? |
| `reconciliation_mismatch_count` | Domain/event/receipt có lệch không? |

Structured trace có thể nối:

~~~text
HTTP traceId
    -> commandId / paymentId
    -> Couchbase transaction attempt
    -> outbox eventId
    -> broker topic / partition / offset
    -> inbox receipt / consumer transaction
    -> invoice ID / external provider reference
~~~

Không gắn eventId, email, document ID hoặc tenant secret vào Prometheus labels có cardinality cao; dùng logs/traces được phân quyền và redaction. Broker send success chỉ là một **mốc**, không thay monitor consumer/business.

## 40. Reconciliation job là lớp bảo vệ sau sự cố

Không phải sai lệch nào cũng có thể sửa bằng retry. Có thể mất connector checkpoint, restore từ backup cũ hoặc provider trả ambiguous outcome. Một job đối soát định kỳ nên tìm:

1. Order PAID nhưng không có outbox `OrderPaid` đúng command/version.
2. Outbox PENDING/LEASED quá lâu, lease hết hạn.
3. Outbox SENT nhưng downstream invoice chưa có hoặc chưa ACK theo contract.
4. Hai invoices cùng business identity.
5. Provider payment CAPTURED nhưng Order PENDING.
6. Saga step/compensation stuck UNKNOWN.
7. DLQ/DEAD records vượt SLA.
8. Receipt eventId trùng nhưng hash khác.

Báo cáo minh họa:

~~~json
{
  "orderId": "1001",
  "paymentStatus": "CAPTURED",
  "orderStatus": "PAID",
  "outboxStatus": "SENT",
  "invoiceStatus": "MISSING",
  "suggestedAction": "REPLAY_SAME_EVENT_ID"
}
~~~

`suggestedAction` là **đề xuất**, không tự thực thi nếu side effect có thể không idempotent. Reconciliation phải ghi audit và xác minh business constraints.

## 41. Restore/backup không undo external side effects

Timeline:

~~~text
T0  Order+outbox commit
T1  Broker gửi OrderPaid, consumer tạo hóa đơn
T2  Couchbase backup snapshot trước T1
T3  Restore; outbox có thể trở lại PENDING
T4  Relay phát lại eventId cũ
~~~

Nếu inbox database cũng restore từ một thời điểm khác, cả receipt và trạng thái business có thể không phản ánh history thực tế.

Do đó:

- Xác định RPO/RTO cho domain, outbox, inbox và broker.
- Có archive/audit evidence khi cần.
- Sau restore, so với broker offsets/provider/invoice ledger trước khi mass replay.
- Không tạo eventId mới để “bù”; giữ identity cũ nếu là cùng logical event.
- Đảm bảo consumer/version guard ngăn record cũ ghi đè state mới.
- Có runbook, quyền phê duyệt và rate limit cho mass recovery.
- Nếu connector rewind, hiểu có thể phát lại records.
- Không mặc định backup Couchbase đã khôi phục lại trạng thái của external payment.

**Khôi phục dữ liệu không đảo ngược một email đã gửi hoặc khoản tiền đã capture.**

## 42. Integration test domain + outbox transaction

Chạy trên **Couchbase deployment có transaction hỗ trợ**, không chỉ mock bean.

**A — Commit:**

~~~text
Given Order=PENDING, không có outbox event
When  update PAID + insert outbox trong cùng transaction
Then  Order=PAID, version tăng
And   outbox event đúng key, tenant, schema, payload
~~~

**B — Rollback:**

~~~text
Given Order=PENDING
When  transaction lỗi giữa hai mutations staged
Then  Order vẫn PENDING
And   outbox event không commit
~~~

**C — Duplicate confirmation:**

~~~text
Given cùng verified paymentId đến 2 lần concurrent
When  2 transaction attempts tranh cùng Order
Then  chỉ một logical OrderPaid/command được ghi
And   request khác nhận idempotent answer hoặc conflict rõ
~~~

Test phải kiểm chứng **committed DB state**, không chỉ callback chạy hoặc in-memory object. Khóa `eventId` ổn định để phát hiện duplicate commands.

## 43. Fault injection đúng các cửa sổ lỗi

| Điểm cắt sự cố | Kết quả mong đợi |
| --- | --- |
| Trước transaction commit | Không có Order PAID/outbox committed |
| Sau commit, trước relay | Outbox PENDING còn để recover |
| Trước broker send | Retry được |
| Sau broker ACK, trước SENT | Có thể duplicate, consumer idempotent |
| Worker crash khi lease còn | Lease expiry/recovery đúng |
| Worker A mark sau khi B chiếm lease | CAS/owner check từ chối A |
| Consumer commit trước ack offset | Redelivery không tạo Invoice thứ hai |
| Receipt insert thành công trong attempt nhưng invoice insert fail | Transaction rollback cả hai |
| Provider HTTP timeout sau capture | Lookup/reconcile; không charge lại mù |
| Version 9 đến trước 8 | State machine/version check |
| Outbox TTL quá ngắn | Test bắt event bị mất, sửa policy |
| 100 worker retry cùng lúc | Global rate limiting/bulkhead |
| Restore backup cũ | Reconciliation không tạo double charge |
| Webhook signature sai | Không update domain, audit |

Fault injection chỉ ở test/staging cô lập. Không cắt network production để “kiểm thử độ bền” mà không có kế hoạch rủi ro và quyền phê duyệt.

## 44. Benchmark và capacity planning

Một benchmark nên có các chiều:

~~~text
Event rate:       10, 100, 1000/s
Relay workers:    1, 4, 16, 64
Payload sizes:    1KB, 10KB, 100KB
Broker latency:   normal, high, timeout
Consumer latency: 5ms, 100ms, 2s
Failure rates:    0%, 1%, 10%
~~~

Theo dõi:

- Couchbase transaction p95/p99, CAS conflict và durability latency.
- Outbox data/index growth, write amplification và purge cost.
- Polling SQL++ CPU/`EXPLAIN`/GSI scan cost.
- Pending age, backlog drain time sau broker outage.
- Producer retries/timeout/partial ACK.
- Duplicates và inbox contention.
- Kafka partition imbalance theo aggregateId.
- Consumer lag, heap/GC và DLQ volume.
- Tải thêm lên Repository/Template/OLTP cùng cluster.

Đừng chọn nhiều relay workers chỉ vì throughput cao trong một benchmark ngắn. Tìm mức giữ **tail latency, error rate, database load và recovery SLO** ở ngưỡng chấp nhận được.

## 45. Ma trận lựa chọn kiến trúc

| Use case | Hướng bắt đầu | Giới hạn/điều kiện |
| --- | --- | --- |
| Email marketing không quan trọng | Best-effort after commit có thể đủ | Chấp nhận event mất |
| Order state bắt buộc có event | Transactional outbox | Domain + outbox cùng commit |
| Đồng bộ cache trạng thái mới nhất | CDC mutable document | Có thể bỏ versions trung gian |
| Mỗi transition phải được phát | Immutable event documents | Identity/retention đủ |
| Kafka delivery từ Couchbase | Polling relay/DCP connector | At-least-once + consumer idempotency |
| Multiple relay workers | CAS lease claim | Duplicate vẫn có thể phát |
| Consumer ghi invoice vào Couchbase | Transactional inbox + invoice | Ack broker sau commit |
| Consumer gọi payment API | Provider idempotency + saga | Reconcile ambiguous outcomes |
| Payment webhook | Signature + durable inbox | Dedupe và ordering |
| Multi-service workflow có compensation | Saga | Không phải ACID rollback |
| Strict global event ordering | Thiết kế đặc biệt, cost cao | Không suy từ vBucket/Kafka |
| Phục hồi sau disaster | Reconciliation/job replay | Independent evidence |

Bảo đảm theo **giá trị side effect**: một lần gửi email có thể khác hẳn một lần capture tiền.

## 46. Checklist code review

### Domain, transaction, event

- [ ] Domain transition và outbox insert cùng Couchbase transaction.
- [ ] Không broker/HTTP/side effects trong transaction lambda.
- [ ] EventId/commandId ổn định qua retries.
- [ ] AggregateVersion/eventType/schemaVersion/payload có contract.
- [ ] Transaction commit ambiguous có reconciliation.
- [ ] Spring `@Transactional` không được coi là broker transaction.
- [ ] AFTER_COMMIT listener không thay durable outbox.
- [ ] CAS/`@Version`, mapping, TTL/expiry, tenant nhất quán giữa SDK/Spring.

### Relay/consumer

- [ ] Polling query có index và lặp định kỳ.
- [ ] CAS claim + lease + owner/fencing check.
- [ ] ACK broker trước mark SENT.
- [ ] Backoff + jitter + max attempts + DEAD/DLQ.
- [ ] Hiểu DCP source latest-version delivery.
- [ ] Immutable event docs nếu mọi logical event đều cần được phát.
- [ ] Inbox receipt và domain effect atomically commit khi cùng Couchbase.
- [ ] Broker offset/ack sau business commit.
- [ ] Duplicate eventId + payload fingerprint được xác minh.
- [ ] Aggregate ordering và version gap được xử lý.
- [ ] External provider dùng idempotency/reconciliation.

### Bảo mật và vận hành

- [ ] Webhook signature/timestamp/anti-replay.
- [ ] Payload ít PII nhất có thể, routing allowlist.
- [ ] Outbox/inbox retention phủ outage/replay/restore window.
- [ ] Có oldest-pending-age, DEADS, duplicates, lag, retries.
- [ ] Có runbook recovery/reconciliation.
- [ ] Không dùng high-cardinality IDs làm metric labels.
- [ ] Có fault-injection tests theo mọi crash window.
- [ ] Đã xác minh Server/SDK/Spring/Kafka Connector versions.

## 47. Bài tập thực hành

**A — Domain + outbox**

1. Tạo `shop.sales.orders` và `shop.sales.outbox_events`.
2. Seed Order PENDING có `businessVersion=7`.
3. Dùng `ctx.get/replace/insert` để commit PAID+OrderPaid.
4. EventId ổn định theo paymentId xác minh.
5. Thử rollback giữa hai mutations, kiểm tra cả hai.
6. Test hai callbacks cùng paymentId concurrent.
7. Kiểm tra không broker call trong lambda.

**B — Relay**

1. Tạo GSI/SQL++ chọn events PENDING.
2. Dùng CAS claim và lease owner.
3. Publish vào fake broker hỗ trợ ACK/timeout.
4. Mark SENT sau ACK; retry/UNKNOWN khi lỗi.
5. Crash sau ACK trước SENT để kiểm tra duplicate.
6. Test lease expiry và stale worker.
7. Tạo DLQ, bounded retries và manual replay.

**C — Inbox/consumer**

1. Receipt key theo consumer+tenant+eventId.
2. Insert receipt + Invoice cùng transaction.
3. Phát message trùng, xác minh chỉ một Invoice.
4. Crash sau consumer commit nhưng trước broker ack.
5. Thử eventId trùng với payload khác → quarantine.
6. Gửi aggregateVersion=9 trước version=8.
7. Kiểm tra retention của inbox dài hơn replay window.

**D — Webhook/CDC/vận hành**

1. Verify webhook signature trước cập nhật dữ liệu.
2. Gửi cùng payment event nhiều lần, kiểm tra logical idempotency.
3. So CDC mutable Order với immutable event document.
4. Diễn giải tại sao Kafka Source Connector có thể bỏ V2 trong V1→V2→V3.
5. Simulate payment provider timeout sau capture; lookup/reconcile.
6. Viết runbook xử lý outbox backlog và restore backup.

## 48. Câu hỏi tự kiểm tra

1. Vì sao đổi thứ tự save và publish không giải quyết dual-write?
2. Couchbase transaction bảo đảm phần nào, không bảo đảm phần nào?
3. Vì sao side effects trong transaction callback nguy hiểm?
4. AFTER_COMMIT listener có che cửa sổ JVM crash không?
5. Vì sao eventId phải ổn định trước transaction retry?
6. Outbox event cần identity/version/tenant/payload gì?
7. DCP source có bảo đảm mọi version của mutable doc không?
8. Vì sao immutable event docs hữu ích hơn mutable state cho event log?
9. CAS claim có ngăn mọi duplicate publish sau lease expiry không?
10. Vì sao mark SENT sau ACK nhưng vẫn có duplicate?
11. Inbox receipt và business effect phải cùng transaction vì sao?
12. Broker ack sau consumer DB commit giúp gì?
13. Một Order có nhiều event; vì sao không dedup theo orderId?
14. AggregateVersion khác KV CAS ở đâu?
15. Kafka partition order có phải global order không?
16. Webhook signature/timestamp chống lỗi/tấn công nào?
17. Payment HTTP timeout có nghĩa provider chưa capture không?
18. Saga compensation khác rollback ACID thế nào?
19. TTL của outbox/inbox có thể phá recovery thế nào?
20. Durability có bảo đảm consumer thực thi không?
21. Kafka producer transaction có tự enlist Couchbase không?
22. Reconciliation cần đối chiếu nguồn nào?
23. Test nào chứng minh cửa sổ ACK→SENT an toàn?
24. Một retry storm ảnh hưởng OLTP như thế nào?

## 49. Tài liệu chính thức và đối chiếu phiên bản

- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): `cluster.transactions().run`, `ctx.get/insert/replace`, retry lambda và errors.
- [Couchbase Java SDK — Error Handling](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): ambiguous/unambiguous timeout, idempotency, retry.
- [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): durability levels, failover và ambiguous writes.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): Query Service, GSI freshness và `REQUEST_PLUS`.
- [Couchbase Server — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): index phục vụ outbox polling.
- [Couchbase Kafka Connector — Introduction](https://docs.couchbase.com/kafka-connector/current/index.html): DCP source/sink.
- [Couchbase Kafka Connector — Delivery Guarantees](https://docs.couchbase.com/kafka-connector/current/delivery-guarantees.html): at-least-once latest-version, rewinds, order theo vBucket và TTL deletion.
- [Couchbase Server — Eventing Service](https://docs.couchbase.com/server/current/learn/services-and-indexes/services/eventing-service.html): mutation-driven handlers và timers.
- [Couchbase Server — Eventing Terminology](https://docs.couchbase.com/server/current/eventing/eventing-Terminologies.html): `OnUpdate`/`OnDelete` và coalescing.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): CAS, expiry và mutations.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): entity, converter, optimistic locking.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): thấp tầng Spring mapping.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`.

**Lưu ý phiên bản:** Bài minh họa Couchbase Java SDK **3.x** và Spring Data Couchbase tương thích, cùng một Kafka Connector được cấu hình phù hợp. Transaction API, Spring integration, Eventing/CDC, GSI, durability và delivery semantics phụ thuộc Server/SDK/Connector versions và edition. Cần compile, kiểm thử trên cluster/broker thật, xác nhận fault behavior và security contract trước production. Bài viết STEP 4 **chưa thay Content QA ở STEP 6**.

> **Ghi nhớ:** Phối hợp database và external events là **bài toán hai ranh giới giao dịch**. Dùng **domain + outbox cùng Couchbase transaction**, phát **at-least-once** có retry/lease, xử lý consumer bằng **transactional inbox/idempotency**, kiểm soát aggregate ordering và đối soát sau crash/restore. CAS, durability, broker ACK hay `@Transactional` đều **không tự tạo exactly-once end-to-end**.


