# Eventual order trong remote chunking của Spring Batch

> **Chương:** Ordering
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán phù hợp. Bài học đặt trọng tâm vào thứ tự khi nhiều worker xử lý chunk đồng thời, khả năng retry/restart, độ chính xác của side effect và việc lựa chọn kiến trúc theo tài nguyên thực tế.

Trong một step tuần tự, người học dễ hình dung item được đọc, xử lý và ghi lần lượt. Khi triển khai **remote chunking**, manager đọc input rồi gửi các chunk qua middleware tới nhiều worker, mỗi worker có tốc độ, độ trễ và lỗi riêng. Chunk gửi trước **không nhất thiết hoàn tất trước**, và reply đến trước **không chứng minh** kết quả nghiệp vụ của chunk đó được phép công bố trước.

**Eventual order** trong bài này là tên gọi thực dụng cho mô hình **cho phép xử lý/nhận kết quả tạm thời lệch thứ tự, sau đó sắp xếp, kiểm tra hoặc áp dụng theo một quy tắc nghiệp vụ được định nghĩa**. Đây **không phải một bảo đảm thứ tự mặc định** của Spring Batch hay một consistency level chuẩn của broker. Ta phải nêu rõ muốn giữ thứ tự ở đâu: **thứ tự file đầu ra**, **thứ tự thay đổi trạng thái của một đơn hàng**, **thứ tự commit**, hay **thứ tự người dùng nhìn thấy**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt thứ tự **input/read**, **chunk dispatch**, **broker delivery**, **worker processing**, **business commit**, **reply arrival** và **publish**.
2. Giải thích vì sao remote chunking nhiều worker không tự bảo đảm global ordering, kể cả khi reader đọc file theo `ORDER BY`.
3. Chọn giữa **không cần thứ tự**, **per-key order**, **thứ tự khi xuất file** và **global strict order** theo bất biến nghiệp vụ.
4. Thiết kế **event ID + aggregate key + sequence/version + durable inbox + ordered projector** để chịu out-of-order, duplicate và gap.
5. Tổ chức retry, rollback, timeout, redelivery và restart mà không bỏ qua event đến muộn hoặc tạo side effect kép.
6. Đo backlog/reorder lag, head-of-line blocking, throughput và xây test cạnh tranh với các thứ tự hoàn thành cố ý bị đảo.

## 1. Bài toán: manager đọc đúng thứ tự nhưng workers hoàn tất lệch

Giả sử một job đọc file thay đổi trạng thái đơn hàng đã được sắp theo sequence:

~~~text
Input:
  event 101: order-42 CREATED
  event 102: order-42 PAID
  event 103: order-42 SHIPPED
  event 104: order-55 CREATED
  event 105: order-55 CANCELLED
~~~

Manager gửi:

~~~text
Chunk C-01 -> [101, 102] -> worker A (xử lý chậm)
Chunk C-02 -> [103, 104] -> worker B (xử lý nhanh)
Chunk C-03 -> [105]      -> worker C

Thứ tự dispatch:  C-01, C-02, C-03
Thứ tự hoàn tất:  C-02, C-03, C-01
Thứ tự reply:     C-03, C-02, C-01 (cũng có thể khác)
~~~

Nếu worker B ghi ngay `SHIPPED` trong khi worker A chưa ghi `CREATED`/`PAID`, trạng thái đích có thể đi ngược logic. Nếu cả ba workers ghi vào một file chung, thứ tự dòng cũng có thể bị đảo hoặc dữ liệu ghi chồng lấn.

~~~mermaid
sequenceDiagram
    participant M as Manager / reader
    participant Q as Broker
    participant A as Worker A
    participant B as Worker B
    participant D as Business DB
    M->>Q: Chunk C-01 [seq 1..100]
    M->>Q: Chunk C-02 [seq 101..200]
    Q->>A: Deliver C-01
    Q->>B: Deliver C-02
    Note over A: Slow API / DB lock
    B->>D: Commit C-02 first
    B-->>M: Reply C-02
    A->>D: Commit C-01 later
    A-->>M: Reply C-01
    Note over M,D: Đọc đúng thứ tự không đồng nghĩa commit đúng thứ tự
~~~

**Không được suy ra** “thứ tự item đúng vì manager có một `ItemReader`” khi worker xử lý đồng thời. Một chunk bản thân cũng có thể chứa nhiều item, và thứ tự thực thi side effects bên trong chunk còn phụ thuộc processor/writer và concurrency ứng dụng.

## 2. Bảy loại thứ tự cần phân biệt

| Loại | Diễn giải | Có được bảo đảm khi tăng remote workers? |
| --- | --- | --- |
| **Source order** | Vị trí vật lý/logical của item trong snapshot | Có thể biết nếu nguồn có key/sort ổn định; không đồng nghĩa thứ tự hoàn tất |
| **Read order** | Thứ tự reader trả item cho manager | Phụ thuộc reader/SQL/snapshot; cần `ORDER BY` hoặc thứ tự file |
| **Dispatch order** | Manager gửi các chunk requests theo thứ tự nào | Có thể có thứ tự tại producer; middleware/concurrency có thể làm delivery khác |
| **Delivery order** | Worker nhận requests theo thứ tự nào | Tùy broker/partition/consumer/ack/redelivery |
| **Completion/commit order** | Worker nào hoàn tất xử lý và commit trước | **Không** được bảo đảm khi nhiều workers độc lập |
| **Reply arrival order** | Manager nhận xác nhận nào trước | Phụ thuộc network, broker, concurrency; **không** là commit order |
| **Publish/visible order** | Kết quả được downstream nhìn thấy theo thứ tự nào | Phải thiết kế riêng nếu nghiệp vụ yêu cầu |

Ví dụ, trong một hệ thống Kafka, thứ tự được định nghĩa **trong một topic partition**, không có global FIFO giữa mọi partitions. Ngay cả khi broker deliver message theo offset trong một partition, việc ứng dụng xử lý **song song sau khi nhận** hoặc retry/redelivery vẫn có thể làm side effects hoàn tất khác thứ tự.

Với RabbitMQ, một queue có thể giao các deliveries theo thứ tự nhất định tùy consumer setup, nhưng **nhiều consumers, prefetch, requeue và xử lý bất đồng bộ** không cho phép coi business commits là global FIFO. Cần kiểm tra hợp đồng của broker/adapter **và** cách worker thực thi.

### Reader SQL cũng phải có thứ tự xác định

~~~sql
-- Nên có sort key ổn định; created_at một mình có thể trùng.
SELECT id, aggregate_id, aggregate_seq, payload
FROM input_event
WHERE source_version = :sourceVersion
ORDER BY aggregate_id, aggregate_seq, id;
~~~

`ORDER BY` tạo thứ tự truy vấn; nếu input thay đổi giữa nhiều chunk/page, thứ tự hoặc tập item có thể **drift**. Dùng snapshot/manifest, watermark và key ổn định phù hợp. Dù reader trả đúng thứ tự, việc **worker commit** vẫn có thể lệch.

## 3. Remote chunking hoạt động ở mức nào?

Theo mô hình Spring Batch Integration remote chunking thông dụng:

1. Manager giữ `ItemReader` và tạo các chunk từ items đọc được.
2. Manager gửi **chunk requests** tới middleware.
3. Worker nhận chunk, chạy phần xử lý/ghi bằng các thành phần thích hợp.
4. Worker phản hồi kết quả để manager điều phối tiến độ/trạng thái.
5. `JobRepository`/`StepExecution` phản ánh lifecycle của step theo cấu hình và phiên bản đang dùng.

~~~mermaid
flowchart LR
    S[("Source snapshot")] --> R["Manager ItemReader"]
    R --> C["Chunk requests C-01, C-02, C-03"]
    C --> B["Message broker"]
    B --> W1["Worker 1"]
    B --> W2["Worker 2"]
    B --> W3["Worker 3"]
    W1 --> D[("Business output / inbox")]
    W2 --> D
    W3 --> D
    W1 --> Q["Replies"]
    W2 --> Q
    W3 --> Q
    Q --> M["Manager step"]
~~~

**Không** đồng nhất remote chunking với remote partitioning:

| Mô hình | Ai đọc input? | Đơn vị gửi đi | Ý nghĩa với ordering |
| --- | --- | --- | --- |
| **Remote chunking** | Thông thường manager | Chunk items | Chunk được dispatch tuần tự nhưng worker completion có thể lệch |
| **Remote partitioning** | Worker step | StepExecution/ExecutionContext theo partition | Mỗi partition đọc phạm vi riêng, không có total order giữa partitions |
| **Local multi-threaded step** | Một step với các chunk threads | Chunk task trong JVM | Có thể lệch thứ tự dù không có broker |
| **Parallel steps** | Mỗi step/flow có reader riêng | Flow/step execution | Không có thứ tự giữa các flows trừ khi có dependency rõ |

Các kiểu message request/reply, correlation, timeout và transaction phụ thuộc **Spring Batch/Spring Integration version và adapter**. Không dựa vào một tên class/field `sequence` giả định để suy ra framework có bộ **reorder business events** tự động.

## 4. Định nghĩa thứ tự đúng theo nghiệp vụ

Trước khi chọn giải pháp, phải trả lời câu hỏi **“thứ tự của cái gì?”**.

### 4.1. Không cần thứ tự

Ví dụ mỗi item cập nhật một khách hàng độc lập, kết quả là một tập rows không quan trọng vị trí. Khi đó:

- Worker có thể commit theo bất kỳ thứ tự nào.
- Cần unique business key/idempotency để replay không tạo trùng.
- Trước publish, kiểm tra **đủ tập input/output**, không cần ép commit FIFO.

**Đây thường là lựa chọn scale tốt nhất** nếu yêu cầu nghiệp vụ cho phép.

### 4.2. Per-key order

Ví dụ các sự kiện của **cùng orderId**:

~~~text
order-42, seq 1: CREATED
order-42, seq 2: PAID
order-42, seq 3: SHIPPED
~~~

Mục tiêu:

~~~text
Với mỗi (tenantId, orderId):
  áp dụng seq=1 trước seq=2 trước seq=3.
Không yêu cầu order-42 và order-55 phải đồng bộ thứ tự với nhau.
~~~

Đây là **thứ tự theo aggregate key**. Có thể shard/route theo key, giữ một worker tuần tự cho từng key, hoặc **nhận events lệch thứ tự rồi xếp lại** tại một inbox/sequencer bền vững.

### 4.3. Thứ tự file/report đầu ra

Nếu cần một CSV cuối cùng sắp theo `(businessDate, orderId)`, workers **không cần commit theo thứ tự**. Họ có thể ghi nhiều staged objects/rows riêng, rồi một bước merge/sort cuối tạo report có thứ tự ổn định.

### 4.4. Global strict order

Một số workflow yêu cầu **tất cả side effects** phải xảy ra đúng thứ tự 1, 2, 3, ... trên toàn hệ thống.

Đó là ràng buộc mạnh; phải dùng **sequencer/serial execution hoặc một giao thức ordering tập trung** phù hợp, có thể hạn chế parallelism. Không thể đạt global strict business commit order chỉ bằng cách đọc FIFO rồi phân phối công việc tự do cho 20 workers.

### 4.5. “Eventual order” không đồng nghĩa eventual consistency

- *Eventual consistency* nói về trạng thái các bản sao/điểm đọc cuối cùng hội tụ theo hợp đồng hệ thống.
- *Out-of-order processing* nói về **thứ tự quan sát/thực thi** các sự kiện.
- *Eventual ordered publication* trong bài này là **một thiết kế ứng dụng**: tạm lưu kết quả rồi công bố/áp dụng theo sequence khi đủ điều kiện.

**Một hệ thống có thể eventually consistent nhưng vẫn áp dụng sai thứ tự vĩnh viễn** nếu không có sequence và logic reconciliation. Ngược lại, có thể xử lý chunks lệch thứ tự nhưng tạo output cuối cùng đúng order bằng bước merge.

## 5. Vì sao không nên dựa vào timestamp làm thứ tự?

Giả sử hai producers tạo events:

~~~text
2026-11-26T08:15:10.001Z event A
2026-11-26T08:15:10.001Z event B
~~~

Timestamp trùng; clocks khác nhau có drift; network delay khiến event đến muộn. `eventTime` hữu ích cho analytics và windowing, nhưng **không phải total order duy nhất** trừ khi giao thức nghiệp vụ đã định nghĩa rõ tie-breaker và producer consistency.

### Metadata khuyến nghị

~~~json
{
  "tenantId": "tenant-A",
  "aggregateType": "ORDER",
  "aggregateId": "order-42",
  "eventId": "event-42-v3",
  "sequence": 3,
  "sourceVersion": "orders-cdc-snapshot-v1",
  "eventType": "ORDER_SHIPPED",
  "payloadHash": "sha256-of-canonical-payload",
  "eventTime": "2026-11-26T08:15:10Z"
}
~~~

Đây là mẫu dữ liệu minh họa; `payloadHash` là placeholder, không phải SHA-256 hợp lệ. Hệ thống thật cần canonical payload representation và source identity ổn định.

**Một event cần có:**

- `eventId` ổn định qua retry/redelivery.
- `aggregateId` (và tenant/namespace) để biết **mỗi chuỗi có thứ tự riêng**.
- `sequence` hoặc version do **nguồn có thẩm quyền** cấp theo luật nhất quán.
- `sourceVersion`/manifest nếu cần đóng băng tập nguồn cho restart.
- Payload fingerprint để phát hiện **cùng eventId nhưng payload thay đổi**.

### Sequence có cần liên tiếp không?

Không phải luồng dữ liệu nào cũng phát số 1, 2, 3 liên tiếp. Một CDC offset toàn cục có thể nhảy đối với từng aggregate. Nếu không có sequence liên tiếp **cho từng aggregate**, không thể lấy quy tắc `lastSeq+1` một cách máy móc.

Các lựa chọn cần định nghĩa:

1. Cấp sequence **liên tục per aggregate** tại nguồn.
2. Gắn `previousEventId` hoặc predecessor version để biết dependencies.
3. Dùng một watermark/end-of-stream/manifest đã chốt và sắp theo key có thứ tự, với cách phát hiện các events còn thiếu.

**Đừng coi “seq mới lớn hơn” là đủ** nếu một sự kiện ở giữa có side effect bắt buộc.

## 6. Anti-pattern: worker cập nhật trạng thái order trực tiếp

Ví dụ processor nhận từng event, writer làm:

~~~java
// NGUY HIỂM nếu event 3 đến trước event 1, 2:
jdbc.update(
    "UPDATE orders SET status=? WHERE tenant_id=? AND order_id=?",
    event.newStatus(), event.tenantId(), event.orderId());
~~~

Kịch bản:

~~~text
Worker B ghi order-42 SHIPPED (seq 3)
Worker A ghi order-42 PAID    (seq 2) đến muộn

Trạng thái cuối có thể bị hạ từ SHIPPED về PAID.
~~~

Thêm `synchronized` trong một worker JVM **không** bảo vệ các worker JVM khác. Unique key trên `eventId` cũng **không đủ**, vì event 2 và event 3 là **hai sự kiện khác nhau, đều hợp lệ**, chỉ bị đảo thứ tự.

### Khi nào conditional monotonic version update đủ?

Nếu mỗi event là **snapshot đầy đủ trạng thái mới** và nghiệp vụ cho phép bỏ qua state cũ khi state mới đã áp dụng, có thể dùng:

~~~sql
UPDATE orders
SET status = :newStatus, last_version = :newVersion
WHERE tenant_id = :tenantId
  AND order_id = :orderId
  AND last_version < :newVersion;
~~~

Nhưng đây là mô hình **last-version-wins**:

- Event version 3 có thể áp dụng trước 2, sau đó version 2 bị bỏ qua.
- Điều đó **chỉ hợp lệ** nếu event 2 không mang tác dụng nghiệp vụ bắt buộc (ví dụ thanh toán, ghi ledger, gửi email).
- Nếu events là **commands/deltas** cần thực hiện tuần tự, bỏ event 2 gây mất tác dụng.

**Không áp dụng last-version-wins cho giao dịch tài chính** nếu mỗi event biểu diễn một thay đổi tiền độc lập. Muốn an toàn, phải giữ từng operation và thứ tự của nó theo contract.

## 7. Giải pháp A: xử lý tuần tự theo aggregate key

Một thiết kế có thể chọn:

~~~text
Route key = (tenantId, orderId)

Mọi events của cùng orderId
  -> cùng một logical shard/consumer
  -> xử lý tuần tự theo source sequence

Các orderId khác nhau
  -> nhiều shards/consumers xử lý song song
~~~

### Điều kiện để thật sự giữ order

| Điều kiện | Vì sao |
| --- | --- |
| Producer cấp sequence có thẩm quyền | Worker biết event nào phải đi trước |
| Cùng aggregate key vào cùng ordered lane | Không có hai workers độc lập cạnh tranh event của cùng aggregate |
| Một lane không thực thi side effects đồng thời | Delivery FIFO không tự đảm bảo commit FIFO |
| Retry event lỗi không cho event sau vượt lên | Tránh bỏ qua predecessor |
| Worker failover giữ checkpoint và lock ownership | Worker cũ và mới không cùng áp dụng |
| Business writer idempotent | Redelivery/ACK loss vẫn có thể gửi lại |

**Lưu ý:** Remote chunking manager chia theo **kích thước chunk của chuỗi đọc**, không mặc nhiên gom tất cả events của một `orderId` vào cùng broker partition hoặc cùng worker. Đặt Kafka message key chỉ theo `chunkId` sẽ không tự bảo vệ per-order ordering nếu một order trải qua nhiều chunks.

### Nếu routing không thể bảo đảm

Khi order events nằm xen kẽ trong file và nhiều chunk workers cùng xử lý, việc ép một worker/aggregate qua một adapter tùy chỉnh có thể phức tạp. **Durable inbox + ordered projector** thường dễ giải thích và kiểm thử hơn: remote workers xử lý chunk để **stage** events, còn một tầng riêng áp dụng chúng đúng thứ tự theo key.

## 8. Giải pháp B: nhận bất kỳ thứ tự, lưu durable inbox rồi apply theo sequence

Đây là một kiến trúc thực dụng khi remote chunking cần throughput cao nhưng đích yêu cầu **per-order state transitions đúng thứ tự**.

~~~mermaid
flowchart LR
    R["Manager Reader"] --> C["Remote chunk requests"]
    C --> W1["Worker A"]
    C --> W2["Worker B"]
    C --> W3["Worker C"]
    W1 --> I[("Durable inbox<br/>eventId + orderId + seq")]
    W2 --> I
    W3 --> I
    I --> K["Per-order sequencer<br/>find next expected seq"]
    K --> P[("Order projection / ledger")]
    P --> M["Reconciliation / publish gate"]
~~~

**Ý tưởng cốt lõi:**

1. Manager/worker có thể vận chuyển và nhận events lệch thứ tự.
2. Remote worker **chỉ lưu event có identity bền vững** vào inbox bằng transaction, chống ghi trùng.
3. Ordered projector đọc **event kế tiếp cần áp dụng** của từng aggregate, khóa trạng thái/claim đúng cách và commit hiệu ứng.
4. Event tương lai đến sớm được lưu `PENDING`; không tự bỏ qua predecessor.
5. Việc một chunk remote hoàn tất có thể chỉ chứng minh **đã stage inbox**, chưa chứng minh trạng thái nghiệp vụ cuối đã được áp dụng đủ.

### Hai tiêu chí hoàn tất khác nhau

| Stage | Hoàn thành khi | Có thể báo gì? |
| --- | --- | --- |
| **Remote chunk ingestion** | Tất cả items của snapshot được ghi vào inbox/đã phân loại theo contract | `INGESTED` hoặc bước Batch ingestion `COMPLETED` |
| **Ordered projection** | Mọi event phải áp dụng đã được apply đúng predecessor, không còn gap/unknown | `APPLIED/RECONCILED` |
| **Publication** | Kiểm toán dữ liệu và side effects đạt quality gate | Có thể publish cho downstream |

Nếu người dùng nghiệp vụ hiểu `BatchStatus.COMPLETED` là “đơn hàng đã ở trạng thái cuối”, **không** để job chỉ hoàn tất ingestion rồi báo nghiệp vụ thành công. Tạo orchestration/step kiểm tra projection hoặc một trạng thái workflow tách biệt với tên rõ ràng.

## 9. Thiết kế PostgreSQL inbox và projection

Để minh họa, giả sử source bảo đảm `sequence` **liên tiếp từ 1 cho mỗi (tenantId, orderId)**. Nếu nguồn không bảo đảm điều này, phải đổi thuật toán dựa trên predecessor/watermark thay vì sao chép `last_sequence+1`.

### 9.1. Bảng nhận events bất kể arrival order

~~~sql
CREATE TABLE order_event_inbox (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(160) NOT NULL,
    order_id        VARCHAR(160) NOT NULL,
    source_version  VARCHAR(160) NOT NULL,
    event_seq       BIGINT NOT NULL CHECK (event_seq >= 1),
    new_status      VARCHAR(40) NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    arrived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at      TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, order_id, event_seq)
);

CREATE INDEX idx_order_inbox_pending
ON order_event_inbox (tenant_id, order_id, event_seq)
WHERE applied_at IS NULL;
~~~

Hai constraints phục vụ mục đích khác nhau:

- `PRIMARY KEY(tenant_id, event_id)` ngăn **cùng event** được nhận lặp.
- `UNIQUE(tenant_id, order_id, event_seq)` chặn **hai event khác nhau cùng chiếm một vị trí thứ tự** của một order.

Không tự `ON CONFLICT DO NOTHING` cho tất cả ràng buộc, vì cùng sequence nhưng event ID/payload khác nhau là **identity conflict**, cần điều tra.

### 9.2. Bảng trạng thái hiện hành

~~~sql
CREATE TABLE order_projection (
    tenant_id         VARCHAR(80) NOT NULL,
    order_id          VARCHAR(160) NOT NULL,
    last_sequence     BIGINT NOT NULL DEFAULT 0,
    current_status    VARCHAR(40) NOT NULL DEFAULT 'UNINITIALIZED',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, order_id)
);
~~~

`last_sequence` là **watermark đã apply**, không phải sequence lớn nhất đã nhận. Nếu inbox có seq 3 nhưng chưa có seq 2, `last_sequence` vẫn là 1.

### 9.3. Ví dụ trạng thái khi nhận lệch

| Thời điểm | Inbox mới nhận | `last_sequence` | Projection |
| --- | --- | ---: | --- |
| T0 | Chưa có | 0 | `UNINITIALIZED` |
| T1 | seq 3 (`SHIPPED`) | 0 | Chưa apply |
| T2 | seq 1 (`CREATED`) | 1 | `CREATED` |
| T3 | seq 2 (`PAID`) | 3 sau khi drain 2 rồi 3 | `SHIPPED` |
| T4 | redelivery seq 2 | 3 | Duplicate no-op (payload phải khớp) |

Đây là kết quả **của projector được thiết kế trong bài**, không phải Spring Batch tự động reorder chunks.

## 10. ItemWriter của remote worker chỉ ghi inbox idempotent

Ví dụ Java 17, Spring Batch 5.x, Spring JDBC và PostgreSQL:

~~~java
public record OrderStatusEvent(
        String tenantId,
        String orderId,
        String eventId,
        String sourceVersion,
        long sequence,
        String newStatus,
        String payloadHash) {}
~~~

Các trường trên phải đến từ **nguồn đã được xác thực/chốt**; không tự tạo `eventId = UUID.randomUUID()` mỗi lần `process(...)` nếu cùng business event có thể được gửi lại.

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

public final class OrderInboxWriter
        implements ItemWriter<OrderStatusEvent> {

    private final JdbcTemplate jdbc;

    public OrderInboxWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends OrderStatusEvent> chunk) {
        for (OrderStatusEvent event : chunk) {
            int inserted = jdbc.update(
                    """
                    INSERT INTO order_event_inbox
                      (tenant_id, event_id, order_id, source_version,
                       event_seq, new_status, payload_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (tenant_id, event_id) DO NOTHING
                    """,
                    event.tenantId(),
                    event.eventId(),
                    event.orderId(),
                    event.sourceVersion(),
                    event.sequence(),
                    event.newStatus(),
                    event.payloadHash());

            if (inserted == 1) {
                continue; // Event mới, chưa có nghĩa đã apply.
            }

            Boolean same = jdbc.queryForObject(
                    """
                    SELECT order_id = ?
                       AND source_version = ?
                       AND event_seq = ?
                       AND new_status = ?
                       AND payload_hash = ?
                    FROM order_event_inbox
                    WHERE tenant_id = ? AND event_id = ?
                    """,
                    Boolean.class,
                    event.orderId(),
                    event.sourceVersion(),
                    event.sequence(),
                    event.newStatus(),
                    event.payloadHash(),
                    event.tenantId(),
                    event.eventId());

            if (!Boolean.TRUE.equals(same)) {
                throw new IllegalStateException(
                        "Trùng eventId với payload/sequence khác");
            }
            // Delivery trùng hợp lệ: giữ nguyên applied_at.
        }
    }
}
~~~

**Giới hạn và điều kiện:**

1. Hai public top-level types ở hai code blocks cần đặt trong **các file Java riêng**; đây là ví dụ không chứa mọi bean/imports.
2. Writer phải được gọi bên trong **transaction phù hợp với datasource của bảng inbox**; timeout/rollback cần được test trên database thực tế.
3. `ON CONFLICT (tenant_id,event_id) DO NOTHING` chỉ xử lý đúng duplicate key; nếu `UNIQUE(tenant_id,order_id,event_seq)` bị vi phạm bởi event khác thì transaction fail — đó là một tín hiệu conflict **không tự skip**.
4. Trường hợp duplicate đã commit trước đó, kiểm tra payload phải **phù hợp** mới được no-op. Không xóa hoặc reset `applied_at` sau restart.
5. Với isolation/driver khác nhau, kiểm thử concurrent inserts và visibility; ví dụ không phải câu SQL portable sang mọi DBMS.
6. `ItemWriter.write` trả về không đồng nghĩa transaction đã commit. Chỉ sau commit mới có thể coi event đã được inbox nhận bền vững.
7. Đây là **ingestion writer**, chưa thực thi side effects của trạng thái order. Projector ở bước sau mới quyết định apply.

### Vì sao không lưu received count làm sequence?

`event_seq` do nguồn nghiệp vụ quyết định thứ tự; `arrived_at`/identity column trong DB chỉ phản ánh **thứ tự đến**, có thể đảo khi transport/retry. Nếu lấy số thứ tự insert làm “sequence mới”, bạn đang hợp thức hóa out-of-order thành một thứ tự sai.

## 11. Ordered projector: chỉ apply next expected sequence

Trong ví dụ này, `order_projection.last_sequence` khởi tạo bằng 0. Một projector dành cho từng aggregate xử lý các events đã nhận nhưng chưa apply:

~~~sql
-- PostgreSQL, giả lập một transaction APPLY cho một order.
BEGIN;

-- Tạo row trạng thái ban đầu nếu chưa có.
INSERT INTO order_projection
    (tenant_id, order_id, last_sequence, current_status)
VALUES (:tenantId, :orderId, 0, 'UNINITIALIZED')
ON CONFLICT (tenant_id, order_id) DO NOTHING;

-- Khóa row của aggregate để projector khác không apply đồng thời.
SELECT last_sequence
FROM order_projection
WHERE tenant_id = :tenantId AND order_id = :orderId
FOR UPDATE;

-- Ứng dụng lấy last_sequence, tính next = last_sequence + 1.
SELECT event_id, event_seq, new_status
FROM order_event_inbox
WHERE tenant_id = :tenantId
  AND order_id = :orderId
  AND event_seq = :nextSequence
  AND applied_at IS NULL
FOR UPDATE;

-- Chỉ nếu tìm thấy event kế tiếp và validate transition hợp lệ:
UPDATE order_projection
SET current_status = :newStatus,
    last_sequence = :nextSequence,
    updated_at = NOW()
WHERE tenant_id = :tenantId
  AND order_id = :orderId
  AND last_sequence = :previousSequence;

UPDATE order_event_inbox
SET applied_at = NOW()
WHERE tenant_id = :tenantId
  AND event_id = :eventId
  AND applied_at IS NULL;

COMMIT;
~~~

Đây là **trình tự SQL minh họa**, không phải một script chạy độc lập: `:nextSequence`, `:previousSequence` và `:eventId` do ứng dụng tính từ kết quả `SELECT`; nếu không có event kế tiếp phải **không chạy UPDATE** và kết thúc/commit transaction an toàn. Ứng dụng phải kiểm tra update row counts và transaction outcome; không coi `UPDATE ... WHERE last_sequence=...` trả 0 rows là thành công.

### Vì sao cần khóa row aggregate?

Nếu projector A và B cùng thấy `last_sequence=1` rồi đều áp dụng seq 2, một effect có thể chạy hai lần. `SELECT ... FOR UPDATE` trên **cùng row projection** cùng transaction giúp serialize các cập nhật của aggregate đó. Những aggregates khác nhau có thể xử lý song song.

Khi một aggregate chưa có row, việc `INSERT ... ON CONFLICT DO NOTHING` kết hợp với khóa sau đó giúp thống nhất row cần lock. Cần test tương tác concurrent inserts/transactions trên PostgreSQL thật.

### Validate state transition, không chỉ số thứ tự

~~~text
CREATED -> PAID -> SHIPPED

CREATED -> SHIPPED có thể không hợp lệ
SHIPPED -> PAID cũng có thể không hợp lệ
~~~

Ngay cả khi seq 2 đến đúng sau seq 1, event type/payload vẫn có thể trái domain rule. Nếu projector gặp event không hợp lệ, phải lưu lỗi nghiệp vụ rõ ràng và có quarantine/review; **không âm thầm tăng last_sequence** rồi bỏ qua event bắt buộc.

### Draining nhiều events

Sau khi apply seq 2, nếu seq 3 đã chờ trong inbox, projector có thể:

- Áp dụng seq 3 trong một transaction tiếp theo, hoặc
- Áp dụng một dãy liên tiếp trong một transaction ngắn phù hợp.

Đừng giữ một transaction/lock cực dài cho hàng triệu events của một hot order. Cân bằng lock duration, batch size, throughput và khả năng retry; đo **head-of-line blocking** trên từng aggregate.

### Side effects ngoài cùng database

Nếu seq 2 còn cần gọi payment API hoặc publish Kafka:

- Không gọi external side effect trực tiếp dưới row lock mà giả định `ROLLBACK` sẽ hoàn tác nó.
- Ghi **outbox/durable intent** trong cùng transaction apply trạng thái DB, sau đó dispatcher phát với **stable operation ID/idempotency key**.
- Downstream vẫn có thể nhận event lặp; cần inbox/dedupe/ordering của consumer.
- Nếu provider chưa xác nhận, đừng đánh dấu business outcome `CONFIRMED` chỉ vì một HTTP request được gửi.

**Ordering và idempotency là hai thuộc tính khác nhau.** Một operation có thể đúng thứ tự nhưng bị áp dụng hai lần; hoặc mỗi event chỉ áp dụng một lần nhưng thứ tự sai.

## 12. Gap, late arrival và head-of-line blocking

Giả sử `order-42` đã apply seq 10, nhận seq 12 nhưng chưa có seq 11:

~~~text
lastSequence = 10
inbox        = {12}
nextExpected = 11

Quyết định an toàn:
  - giữ 12 ở PENDING;
  - ghi nhận gap 11;
  - không áp dụng 12 nếu cần strict per-key order;
  - điều tra hoặc yêu cầu replay seq 11.
~~~

### Không có một timeout gap phù hợp mọi nghiệp vụ

| Lựa chọn | Khi nào hợp lý? | Rủi ro |
| --- | --- | --- |
| **Chờ predecessor** | State transitions bắt buộc theo thứ tự | Hot aggregate có thể kẹt lâu |
| **Yêu cầu replay từ nguồn** | Nguồn giữ event log/manifest đáng tin | Nguồn có thể hết retention |
| **Quarantine và human review** | Sự kiện thiếu không thể đoán | Tăng độ trễ; cần runbook rõ |
| **Cho phép skip khoảng trống có chứng cứ** | Nguồn xác nhận sequence đó không tồn tại/đã void | Không được tự đoán “số bị mất không quan trọng” |
| **Rebuild projection từ immutable snapshot** | Có full source history/snapshot | Tốn compute; vẫn cần publish gate |
| **Apply max version** | Event là full-state snapshot và hợp đồng cho phép | Mất intermediate effects nếu dùng sai |

### Head-of-line blocking

Nếu order-42 đang đợi seq 11, các event 12..500 có thể đọng lại. Nhưng các orders khác **vẫn có thể tiếp tục** nếu sequencer khóa theo aggregate, không giữ một global mutex cho toàn hệ thống.

Các tín hiệu nên theo dõi:

- `next_expected_seq` và `max_received_seq`.
- Thời gian gap lâu nhất.
- Số aggregate đang bị block.
- Số inbox events chưa apply và tuổi cao nhất.
- Throughput apply theo key/shard.

Đừng lấy `MAX(event_seq)` làm “đã xử lý tới” khi còn gap.

## 13. Reply đến lệch thứ tự không phải lỗi

Trong remote chunking, manager có thể nhận reply chunk C-02 trước C-01. Nếu hệ thống/adapter hỗ trợ nhiều request đang in flight, đây có thể là **hành vi bình thường**:

~~~text
Dispatch:
  C-01 -> C-02 -> C-03

Reply arrival:
  C-02 <- C-03 <- C-01

Business inbox:
  mỗi chunk đã commit events của mình theo transaction.
~~~

Không được:

- Ghép reply C-02 vào checkpoint của C-01 chỉ vì đó là reply đến đầu tiên.
- Dùng “reply #2” thay cho **request correlation ID**.
- Coi reply đến trễ là một **business event mới**.
- Dùng reply arrival order làm thứ tự ghi vào final report.

### Những định danh cần phân biệt

| ID | Phạm vi | Dùng để |
| --- | --- | --- |
| `JobInstanceId` | Logical job + identifying parameters | Liên kết các lượt restart |
| `JobExecutionId` | Một lượt chạy job | Tracing một attempt |
| `StepExecutionId` | Một execution của step | Metadata/counters/checkpoint |
| `chunkRequestId`/sequence logic | Request chunk theo adapter/application | Match reply đúng request |
| `messageId` | Delivery của broker | Điều tra transport/redelivery |
| `eventId` | Business event | Dedupe inbox qua retry/restart |
| `aggregateId + sequence` | Thứ tự nghiệp vụ | Project đúng event kế tiếp |

`chunkRequestId` ở đây là tên khái niệm, **không khẳng định** mọi phiên bản Spring Batch có một field mang đúng tên như vậy. Dùng các ID/correlation và sequence mà adapter Spring Batch Integration thực tế cung cấp.

### Tình huống reply thất lạc

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant W as Worker
    participant I as Inbox DB
    M->>B: Chunk C-05
    B->>W: Deliver C-05
    W->>I: INSERT events (transaction)
    I-->>W: COMMIT
    W--xM: Reply/ACK lost
    Note over M: Timeout không chứng minh commit thất bại
    B->>W: Redelivery (nếu transport yêu cầu)
    W->>I: INSERT cùng event IDs
    I-->>W: Duplicate cùng payload -> no-op
    W-->>M: Correlated reply
~~~

Hành vi broker redelivery/ACK chính xác phụ thuộc middleware/configuration. **Không** dựa vào sơ đồ như cam kết rằng adapter luôn tự redeliver và manager luôn auto-reconcile. Phải test quy trình thật.

## 14. Retry, rollback, restart: thứ tự không được phá khi phát lại

### Retry trong worker

Nếu worker gặp lỗi DB tạm thời và retry một chunk:

- Có thể chạy lại `ItemProcessor`/`ItemWriter` cho các items.
- Các item trong chunk không trở thành **business event mới**.
- Giữ `eventId`/`aggregate_seq` ổn định.
- Nếu inbox commit lần đầu rồi reply mất, lần hai phải nhận diện duplicate.

### Rollback trong transaction

Nếu worker ghi vào cùng business database transaction và rollback trước commit, inbox rows chưa commit sẽ không tồn tại. Retry có thể insert lại. Nhưng nếu writer đã gọi API, publish message hoặc ghi database khác **ngoài transaction**, rollback không hoàn tác side effect đó.

### Restart cùng JobInstance

`JobExecutionId`/`StepExecutionId` có thể đổi. Reader của manager có thể đọc lại một số items theo checkpoint và cách middleware xác nhận chunk requests. **Tập event identity phải giữ nguyên** vì mỗi event đã được định nghĩa từ source snapshot:

~~~text
Before restart:
  eventId=event-42-v2, seq=2

After restart:
  eventId=event-42-v2, seq=2    (không đổi)

JobExecutionId / StepExecutionId có thể đổi.
~~~

Không dùng `UUID.randomUUID()` mỗi lần processor chạy hoặc `StepExecutionId` làm event ID; điều này biến duplicate delivery thành một event mới có thể áp dụng hai lần.

### Partitioned input và ordering

Nếu đầu vào là một tập event log theo order:

- Phải xác định **snapshot/watermark** để không đổi nội dung giữa các lần chạy.
- Nếu phân vùng nguồn theo business aggregate, cùng một aggregate cần kế hoạch worker ownership nhất quán.
- Nếu các chunks chứa event trộn nhiều aggregates, ordered projector sẽ phải điều phối theo key sau ingestion.
- Một partition `COMPLETED` trong Batch không chứng minh mọi downstream projection đã apply khi ingestion và projection là hai pha.

## 15. Định nghĩa atomic completion và publish gate

Một hệ thống thường có ba câu hỏi khác nhau:

1. **Đã nhận đủ input?** Tất cả events trong snapshot có inbox row hợp lệ hoặc một outcome được phép.
2. **Đã apply đúng thứ tự?** Mỗi aggregate có contiguous applied sequence tới target watermark, không có gap quan trọng.
3. **Đã publish kết quả?** Downstream thấy một snapshot/report nhất quán và được duyệt.

~~~mermaid
flowchart TD
    S["Sealed source manifest / expected events"] --> I["Remote chunk ingestion"]
    I --> A["Inbox reconciliation"]
    A --> G{"Expected events received?<br/>duplicates/conflicts resolved?"}
    G -- "Không" --> H["Fail/hold + replay missing events"]
    G -- "Có" --> P["Ordered projector"]
    P --> O{"All aggregate watermarks reached?<br/>no blocking gaps?"}
    O -- "Không" --> H
    O -- "Có" --> V["Validate business output"]
    V --> U{"Quality gate passed?"}
    U -- "Không" --> H
    U -- "Có" --> M["Publish / accept"]
~~~

### Bất biến đối soát

Với một snapshot đã chốt:

~~~text
Expected source event IDs
    = received distinct event IDs
      ∪ explicitly rejected event IDs (nếu chính sách cho phép)

Applied per aggregate:
    [1 .. targetSequence]  (khi source quy định seq liên tiếp)

Không:
    eventId A bị applied hai lần
    sequence 3 applied trước sequence 2 khi strict order là bắt buộc
    event đã nhận nhưng không có outcome
~~~

Nếu một event có thể sinh nhiều business operations, phải mở rộng bất biến theo operation keys; không lấy một eventId làm bằng chứng tất cả downstream side effects đều đã hoàn tất.

### Không đánh đồng Step COMPLETED với publish COMPLETED

Một manager step đã hoàn tất gửi/nhận các chunk theo semantics của adapter vẫn có thể chỉ đạt **ingestion complete**. Nếu nghiệp vụ cần ordered projection và report cuối, dùng **bước kiểm tra sau ingestion** hoặc một workflow orchestrator tách biệt, với trạng thái rõ ràng, thay vì hiển thị “đơn hàng cập nhật hoàn tất” khi inbox còn gap.

## 16. Report/CSV cuối cùng: có thể sắp thứ tự ở bước merge

Một trường hợp phổ biến là **chỉ file cuối cần được sắp xếp**, không có side effect theo event order. Khi đó không cần khóa mọi workers:

~~~text
Worker A -> staging/attempt-501/chunk-C01.csv
Worker B -> staging/attempt-501/chunk-C02.csv
Worker C -> staging/attempt-501/chunk-C03.csv

Reconciler:
  verify chunks, dedupe, choose accepted result

Merger:
  sort by (businessDate, orderId, sourceSequence)
  write immutable final report

Publisher:
  point final manifest to verified report
~~~

### Những điều phải kiểm tra

- Dữ liệu có sort key **ổn định và unique tie-breaker** không?
- Có đủ tập source records/events theo manifest không?
- Một chunk được gửi lại có tạo hai staged files không? Cần chọn một accepted result.
- Sort có đủ RAM không? Với hàng triệu records, dùng external merge sort, staging table/index hoặc data processing framework phù hợp.
- Output store có hỗ trợ atomic publish của một manifest/pointer không? Không coi copy nhiều objects là transaction đa file.
- Bước merge **không thể sửa** side effects ở external system đã bị áp dụng sai thứ tự trước đó.

**Tách output order khỏi commit order** có thể tăng throughput rõ rệt khi nghiệp vụ chỉ quan tâm cách trình bày dữ liệu, không yêu cầu các worker ghi theo global FIFO.

## 17. Hiệu năng: thứ tự càng chặt, parallelism càng bị giới hạn

Giả sử 12 worker có thể xử lý trung bình 1.000 events/s mỗi worker khi không phải chờ predecessor. Global serial coordinator xử lý tối đa 1.500 events/s.

~~~text
Tiềm năng workers (lý thuyết):
  12 × 1.000 = 12.000 events/s

Nếu mọi event bắt buộc đi qua một sequencer 1.500 events/s:
  throughput end-to-end ≤ 1.500 events/s
~~~

Con số là ví dụ giả định để minh họa **bottleneck cuối**, không phải benchmark Spring Batch. Có thể shard sequencer **theo aggregate key** nếu thứ tự chỉ bắt buộc per-key. Một aggregate quá nóng vẫn có thể bị giới hạn bởi một ordered lane.

### Head-of-line blocking tại các tầng

| Tầng | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Manager | Chờ reply/chunk trước để tiến tiếp theo adapter | Đo outstanding requests, timeout, thiết kế correlation |
| Broker | Một queue/partition có message bị giữ/retry | Poison-message policy, partitioning, backpressure |
| Worker | HTTP/DB chậm trong một chunk | Timeout, bounded retries, tách operations nếu hợp đồng cho phép |
| Inbox | Thiếu event predecessor | Replay gap, source watermark, quarantine |
| Sequencer | Hot aggregate/row lock | Shard theo key, batch contiguous events trong giới hạn |
| Output merge | External sort/IO | Parallel sort rồi merge có thứ tự, tối ưu staging |
| Publish | Chưa đạt quality gate | Phát hiện sớm lỗi/quarantine thay vì đợi đến cuối |

### Chọn chunk size có tác động gì?

- Chunk lớn giảm message overhead nhưng tăng thời gian xử lý mỗi request và chi phí replay khi lỗi.
- Chunk nhỏ giúp phân phối đều hơn nhưng tăng broker requests, metadata/correlation và overhead.
- Chunk size **không tự tạo thứ tự commit**. C-01 nhỏ và C-02 lớn vẫn có thể hoàn tất theo thứ tự bất kỳ nếu workload khác nhau.
- Nếu một chunk trộn nhiều aggregates, rollback do một event có thể làm chậm nhiều aggregates không liên quan; cần đo coupling.

### Không mở concurrency vô hạn

~~~text
Manager active chunk requests
  × worker consumers
  × concurrent DB/HTTP calls per worker
~~~

Đây là hình dung về tải, không phải công thức chính xác số connections. Hãy đo DB pool, lock waits, broker lag, worker CPU, outbox/inbox table write IOPS và downstream quotas. Tăng workers trong khi sequencer bị nghẽn chỉ làm backlog tăng.

## 18. Quan sát eventual order bằng metrics và logs

Các metrics cần phản ánh **thu nhận, sắp thứ tự và áp dụng** như ba hoạt động khác nhau:

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| `chunk_requests_dispatched_total` | Số request manager gửi |
| `chunk_replies_received_total` | Số reply nhận được, có thể gồm attempt/lặp tùy adapter |
| `chunk_inflight_count` | Work units chưa có kết quả xác nhận |
| `chunk_reply_out_of_order_total` | Reply đến khác dispatch order; **không mặc định là lỗi** |
| `inbox_unique_events_total` | Event identities đã commit trong inbox |
| `inbox_duplicate_deliveries_total` | Duplicate hợp lệ đã dedupe |
| `inbox_identity_conflicts_total` | Cùng ID/seq nhưng payload khác |
| `ordered_events_applied_total` | Events đã apply hợp lệ |
| `ordering_gap_aggregates_count` | Số aggregates đang thiếu predecessor |
| `ordering_gap_age_seconds` | Thời gian gap tồn tại |
| `max_received_minus_applied_seq` | Khoảng cách sequence, chỉ có ý nghĩa nếu source semantics phù hợp |
| `reconciliation_mismatch_total` | Sai lệch input/inbox/projection/output |
| `worker_retry_exhausted_total` | Số worker requests hết retry budget |
| `publish_blocked_total` | Lượt publish bị chặn vì thiếu/outcome không chắc chắn |

### Event logging có correlation đúng

~~~json
{
  "event": "ordered_projection_gap",
  "jobExecutionId": 502,
  "stepExecutionId": 719,
  "sourceVersion": "orders-cdc-snapshot-v1",
  "partitionName": "remote-chunk-manager",
  "aggregateType": "ORDER",
  "aggregateId": "order-42",
  "lastAppliedSequence": 10,
  "nextExpectedSequence": 11,
  "maxReceivedSequence": 12,
  "errorCode": "MISSING_PREDECESSOR"
}
~~~

Đây là **schema log do ứng dụng thiết kế**, không phải fields Spring Batch tự phát sinh. `aggregateId` hoặc `orderId` có thể là thông tin nhạy cảm/identifier có cardinality cao; áp dụng masking và quyền truy cập phù hợp.

**Không** gắn mỗi `aggregateId`, `eventId` hoặc `StepExecutionId` làm nhãn Prometheus không giới hạn. Dùng metrics tổng hợp theo job/errorCode/shard, còn dữ liệu identity chi tiết nằm trong logs/audit/inbox có index và retention được quản lý.

## 19. Kiểm thử với hoàn tất chunk cố ý đảo thứ tự

Test một worker tuần tự không chứng minh remote ordering. Cần kích hoạt **hai workers/connections thật** hoặc môi trường broker tương đương, dùng latches/fault injection tạo thứ tự hoàn tất khác dispatch.

### 19.1. Fixture có kết quả mong đợi

~~~text
Source snapshot:
  order-A seq 1 CREATED
  order-A seq 2 PAID
  order-A seq 3 SHIPPED
  order-B seq 1 CREATED
  order-B seq 2 CANCELLED

Workers nhận:
  C-1 -> order-A seq 1, order-B seq 1
  C-2 -> order-A seq 2, order-B seq 2
  C-3 -> order-A seq 3

Ép completion:
  C-3, C-2, C-1

Expected inbox:
  đủ 5 event IDs unique

Expected projection sau drain:
  order-A: lastSeq=3, status=SHIPPED
  order-B: lastSeq=2, status=CANCELLED
~~~

### 19.2. Unit test writer nhận duplicate

Với database test có schema ở trên:

~~~java
@Test
void cungEventIdDuocGhiInboxMotLan() {
    OrderStatusEvent event = new OrderStatusEvent(
            "tenant-A", "order-42", "event-42-v2",
            "snapshot-001", 2L, "PAID", "hash-v2");

    Chunk<OrderStatusEvent> chunk = new Chunk<>(List.of(event));

    transactionTemplate.executeWithoutResult(
            status -> writer.write(chunk));

    transactionTemplate.executeWithoutResult(
            status -> writer.write(chunk)); // Redelivery.

    Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM order_event_inbox
            WHERE tenant_id=? AND event_id=?
            """,
            Integer.class, "tenant-A", "event-42-v2");

    assertEquals(1, count);
}
~~~

Đây là snippet **integration test minh họa**, cần JUnit 5, Spring JDBC, `TransactionTemplate`, `Chunk`, `List` và database schema/beans thật. Hai `transactionTemplate.executeWithoutResult` tạo hai giao dịch commit độc lập theo cấu hình, thay vì che lỗi bằng một test transaction luôn rollback. Test thêm cùng `eventId` nhưng `payloadHash` khác phải **fail**.

### 19.3. Kiểm thử sequencer khi gap

1. Insert inbox seq 3 trước seq 1 và 2.
2. Chạy projector: `last_sequence` không được nhảy từ 0 sang 3.
3. Insert seq 1, chạy projector: chỉ đến 1.
4. Insert seq 2, chạy projector: đến 2, rồi 3 nếu drain cho phép.
5. Redeliver seq 2, status vẫn ở seq 3, không nhân đôi side effect.
6. Insert event khác cùng `(tenant,order,seq=2)`, unique constraint phải báo conflict.

### 19.4. Kiểm thử cạnh tranh hai projector

Chạy hai connections/transactions cùng xử lý `order-42`, sử dụng barrier/latch để chúng bắt đầu gần đồng thời:

- Không cùng apply event seq 2 hai lần.
- `last_sequence` tăng đúng 1 cho mỗi event.
- Row lock/transaction được thực thi đúng trên DBMS production.
- Nếu một transaction rollback hoặc process crash, event vẫn còn trong inbox để tiếp tục.
- Không có lock giữ qua HTTP request ngoài transaction khi không thật sự cần.

Một mock `ConcurrentHashMap` không chứng minh được uniqueness/locking giữa các JVM.

### 19.5. Ma trận fault injection

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| C-02 commit trước C-01 | Inbox vẫn đủ, business projection đúng per-key order |
| Reply C-03 đến trước C-02 | Manager ghép đúng correlation, không tráo request |
| Broker redelivery cùng C-02 | Không thêm business event duplicate |
| Worker crash sau inbox commit, trước ACK | Redelivery/restart no-op theo eventId |
| Worker crash trước inbox commit | Lần sau có thể ghi lại events chưa commit |
| Event seq 5 đến khi thiếu 4 | Seq 5 ở pending, không skip predecessor |
| Event thiếu kéo dài quá SLA | Có alert/replay/review; không tự nhảy sequence |
| Cùng eventId nhưng payload khác | Identity conflict, không “last writer wins” |
| Cùng aggregate sequence nhưng event IDs khác | Unique constraint phát hiện mâu thuẫn |
| Hai projector cùng aggregate | Lock/version bảo vệ trạng thái |
| Worker cũ sống sau timeout | Claim/fencing/idempotency chặn double effect |
| Manager restart với checkpoint cũ | Event IDs/sequence giữ nguyên |
| Source snapshot thay đổi giữa restart | Fail/version check, không tráo input |
| External API timeout sau commit | UNKNOWN/reconciliation, retry cùng operation key |
| Output CSV cần thứ tự nhưng chunks lệch | Sort/merge cuối cho đúng thứ tự |
| Publish khi còn gap/unknown | Quality gate chặn |
| Hot aggregate có 10.000 events | Throughput/lag đo được, không khóa mọi aggregate khác |
| DB connection pool quá tải | Backpressure/bounded retry, không chuyển sang skip |

### 19.6. Kiểm thử remote thực sự

Local unit tests không mô phỏng đầy đủ broker redelivery, transport serialization hoặc reply timeout. Ít nhất một bộ integration test nên có:

- Manager và workers ở **process/container khác nhau**.
- Broker/adapters cùng loại với môi trường triển khai.
- Business DB với unique constraints thật, `JobRepository` phù hợp.
- Inject delay phía worker, kill worker sau commit, drop/duplicate reply hoặc mô phỏng tương đương.
- Verify cả **StepExecution statuses** và **business output**, không chỉ log đếm chunks.

## 20. Runbook khi xuất hiện trạng thái sai thứ tự

1. **Định danh dữ liệu:** Chốt `JobInstance`, `JobExecution`, sourceVersion/manifest, aggregate ID và expected sequence.
2. **Kiểm tra input:** Reader đã thấy những event IDs nào? Source có bảo đảm sequence liên tiếp hay predecessor metadata?
3. **Kiểm tra dispatch:** Chunk requests/IDs, broker partition/queue, message correlations và worker owners.
4. **Kiểm tra completion/reply:** Chunk nào commit, reply nào đến, retry/redelivery nào đã xảy ra? Không coi arrival order là commit order.
5. **Đọc inbox:** Event missing, duplicate, sequence conflict, payload mismatch và `applied_at`.
6. **Đọc projection:** `last_sequence`, current state, expected next event và transaction/lock failures.
7. **Kiểm tra external side effects:** API/ledger/outbox có operation nào đã thực hiện nhưng ACK/response mất?
8. **Khoanh vùng:** Sự cố một aggregate, một chunk, một worker hay nhiều partitions/DB/broker?
9. **Dừng publish nếu cần:** Không đưa dữ liệu đã xử lý lệch bắt buộc ra downstream.
10. **Khôi phục từ nguồn có thẩm quyền:** Replay missing predecessor, sửa identity conflict qua quy trình đã duyệt; không tự bịa event.
11. **Restart đúng đường:** Giữ identifying parameters, checkpoint và business keys; không mở JobInstance mới bằng timestamp để né lỗi.
12. **Đối soát rồi publish:** Expected event IDs, applied contiguous watermarks, business state/output và các operations UNKNOWN.
13. **Bổ sung test:** Reproduce delay, reply loss, out-of-order, rollback và concurrency gây lỗi.

### Những cách “sửa nhanh” cần tránh

- Đặt `Thread.sleep` cố định giữa hai chunks và coi đó là cam kết ordering.
- Tin rằng một broker FIFO queue tự đảm bảo **worker commit order** khi có nhiều consumers.
- Sắp xếp replies theo chunk ID rồi coi external API side effects đã được đảo ngược đúng thứ tự.
- Cập nhật `last_sequence = MAX(received_sequence)` khi còn gap.
- Dùng event timestamp làm sequence duy nhất khi có nhiều producers.
- Chỉ chống duplicate theo `chunkId` mà không chống trùng **per-item eventId**.
- Khi timeout, gửi lại payment bằng operation ID mới.
- Skip một event đến muộn chỉ vì nó có sequence thấp hơn giá trị đã ghi sai.
- Xóa các inbox pending events để dashboard hết backlog.

## 21. Checklist lựa chọn giải pháp

| Câu hỏi | Quyết định / kiểm chứng |
| --- | --- |
| Mọi items có phụ thuộc thứ tự không? | Nếu không, cho phép out-of-order và tối ưu throughput |
| Chỉ cần per-key order? | Shard/serialize theo aggregate key hoặc durable ordered projector |
| Chỉ cần output file sorted? | Stage riêng rồi external sort/merge trước publish |
| Cần global strict commit order? | Chọn sequencer/serial path, chấp nhận bottleneck |
| Source có eventId và sequence ổn định? | Không thì bổ sung ở nguồn/manifest trước khi scale |
| Sequence có liên tiếp theo key? | Xác định rõ trước khi dùng `lastSeq+1` |
| Broker có thể redeliver? | Thiết kế dedupe/replay, test transport cụ thể |
| Worker có side effect ngoài DB? | Outbox/durable intent/provider idempotency + reconciliation |
| Có input snapshot bất biến? | Giữ `sourceVersion`, restart đúng JobInstance |
| Inbox đủ bền vững và có unique constraints? | Kiểm thử concurrency và payload conflict |
| Khi còn gap/unknown có được publish? | Đặt quality gate theo hợp đồng nghiệp vụ |
| Backlog/lag đo được? | Dashboard theo shard/error reason, alerts và runbook |

## 22. Bài tập tình huống

Một job Spring Batch đọc **30 triệu CDC events** đã sort theo `(orderId, sequence)`. Manager tạo chunk size 500 và phân phát qua RabbitMQ cho **20 remote chunk workers**. Workers cập nhật trực tiếp bảng `orders.status`. Trên production:

- Worker B nhận chunk có `order-77 seq 9` và hoàn tất trước worker A đang xử lý `seq 8`.
- Trạng thái `SHIPPED` của seq 9 bị ghi đè thành `PAID` do seq 8 đến muộn.
- Manager bị mất reply từ B, broker redeliver chunk cũ; một email gửi hai lần.
- Nhóm kỹ thuật định sửa bằng cách tăng `prefetch=1`, dùng `synchronized` trong mỗi JVM, và sau cùng `ORDER BY` khi đọc bảng output.
- Một worker đã `FAILED` được restart với `run.id` mới; source snapshot đang tiếp tục thay đổi.

**Câu hỏi:**

1. Vì sao `ORDER BY` ở manager không bảo đảm worker commit order?
2. `prefetch=1` ở broker và `synchronized` trong từng JVM có đủ không? Phụ thuộc cấu hình gì?
3. Cần những định danh nào để phân biệt chunk reply, event duplicate và per-order sequence?
4. Nếu seq 9 đến trước seq 8, phải lưu/apply như thế nào khi cả hai side effects đều quan trọng?
5. Có thể sửa trạng thái đã bị ghi sai thứ tự bằng cách sort bảng output vào cuối job không?
6. Làm gì để email không bị gửi hai lần sau ACK/reply loss?
7. Nếu một order thiếu seq 8 mãi mãi, làm gì với seq 9 và publish gate?
8. Khi restart, JobInstance/sourceVersion/partition plan phải được giữ ra sao?
9. Những integration tests và metrics nào chứng minh giải pháp hoạt động khi tăng lên 40 workers?

**Định hướng trả lời:** Reading/dispatch order không quyết định completion/commit order. Broker prefetch và local synchronization chỉ là các yếu tố thực thi, không bảo đảm invariant phân tán; nếu business cần per-order state transitions, nguồn cấp `eventId + orderId + contiguous sequence` hoặc predecessor metadata. Worker stage events vào **durable inbox có unique constraints**, projector khóa aggregate row và apply **next expected sequence** theo transaction. Event tương lai đợi predecessor; gap cần replay/review, không skip mù. Email/API dùng outbox, stable operation IDs và idempotent downstream; sort cuối chỉ sửa **thứ tự trình bày**, không hoàn tác side effects đã sai. Restart giữ JobInstance/input snapshot và event identities, đánh giá dữ liệu thực trước publish. Test đảo chunk completion, duplicate reply, worker crash, sequence gap, concurrency và reconciliation.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và các vấn đề concurrency.
- [Spring Batch Reference — Remote Chunking](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-chunking.html): mô hình manager/worker request-reply.
- [Spring Batch Reference — Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): mô hình remote chunking/partitioning.
- [Spring Batch Reference — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): commit chunks và transaction.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoints và phát lại sau failure.
- [Spring Batch Reference — JobRepository Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): metadata, `StepExecution` và counters.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels, correlation và transport adapters.
- [Apache Kafka Documentation — Consumer Concepts](https://kafka.apache.org/documentation/): ordering trong một topic partition và consumer semantics.
- [RabbitMQ Documentation — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): prefetch và concurrent consumers.
- [RabbitMQ Documentation — Message Ordering](https://www.rabbitmq.com/docs/queues#message-ordering): ordering, redelivery và các ngoại lệ.
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): transaction visibility/concurrency.
- [PostgreSQL Documentation — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, deadlocks và transaction boundaries.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction scopes và external side effects.

> **Ghi nhớ:** Remote chunking mang lại throughput nhờ cho phép nhiều chunks xử lý đồng thời, vì vậy **dispatch order, commit order và reply order có thể khác nhau**. Hãy xác định rõ nghiệp vụ cần **per-key order, global order hay chỉ output sorted**. Với event phụ thuộc thứ tự, cần **stable event identity, sequence/predecessor contract, durable inbox, ordered application, idempotency và reconciliation**. Không coi broker FIFO, `ORDER BY` của reader hay một `JobExecution` hoàn tất là cam kết các side effects đã xảy ra đúng thứ tự.
