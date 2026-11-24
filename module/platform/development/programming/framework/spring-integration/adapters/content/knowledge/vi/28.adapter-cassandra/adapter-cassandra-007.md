# Batch statement và logged batch trong Apache Cassandra

## 1. Bài toán: một message cần ghi nhiều row thì có nên dùng BATCH?

Giả sử một luồng Spring Integration nhận sự kiện `OrderPaid` từ JMS. Sau khi kiểm tra chữ ký, chuyển đổi JSON và validate, ứng dụng cần lưu lịch sử của đơn hàng vào Apache Cassandra. Mỗi `OrderPaid` có thể tạo hai hoặc ba mutation: thêm một sự kiện, cập nhật thông tin liên quan và ghi trạng thái xử lý.

Người phát triển quen cơ sở dữ liệu quan hệ thường đề xuất:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

Nhưng **Cassandra BATCH không tương đương SQL transaction** và cũng **không phải cơ chế tăng tốc mặc định** cho hàng nghìn writes độc lập. Đặc biệt, **logged batch nhiều partition** cung cấp cơ chế hoàn tất/khôi phục các mutation theo hướng *eventual atomicity*, không có cùng mức cô lập, rollback và khả năng đọc snapshot nhất quán của transaction ACID trong RDBMS.

Hãy phân biệt ngay từ đầu:

1. **BATCH của CQL:** một request chứa nhiều `INSERT`, `UPDATE` và/hoặc `DELETE`.
2. **LOGGED batch:** dùng Cassandra batchlog khi cần bảo vệ việc thực thi nhiều mutation qua lỗi coordinator, đặc biệt các mutation liên quan nhiều partition.
3. **UNLOGGED batch:** không dùng batchlog; một batch nhiều partition thất bại có thể chỉ ghi được một phần.
4. **COUNTER batch:** kiểu batch đặc biệt dành cho cập nhật cột counter, không có idempotency như regular write.
5. **Client-side batching:** gom, chia lô hoặc giới hạn các **requests độc lập** trước khi gửi; không nhất thiết sử dụng câu lệnh CQL `BEGIN BATCH`.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các inbound/outbound adapter, gateway, poller và `MessageChannel` kết nối hệ thống file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, có trách nhiệm kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Bài **Batch statement và logged batch** thuộc chương **Adapter Cassandra** giúp chọn đúng cách ghi hàng loạt khi message flow đi qua Cassandra outbound adapter/gateway.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc và viết `BEGIN BATCH`, `BEGIN UNLOGGED BATCH`, `BEGIN COUNTER BATCH`.
- Phân biệt **single-partition isolation**, **logged multi-partition eventual completion** và các giới hạn của transaction semantics.
- Giải thích Cassandra **batchlog**, coordinator, replicas, timeout và trường hợp chỉ một phần dữ liệu tạm thời hiển thị.
- Tạo `BatchStatement` bằng Java Driver 4.x với `SimpleStatement`, `PreparedStatement`/`BoundStatement`, `DefaultBatchType`.
- Tạo batch bằng Spring Data `ReactiveCassandraOperations.batchOps(...)` và xử lý `Mono<WriteResult>`.
- Dùng Spring Integration `CassandraMessageHandler` với payload `List<entity>`, `ingestQuery` dạng `List<List<?>>` hoặc `statementFunction`.
- Chọn batch có giới hạn theo **partition key**, payload bytes, số mutations, deadline và retry budget.
- Thiết kế idempotency, recovery, acknowledgment và test failover phù hợp JMS/Kafka.

## 2. Hiểu đúng ba phạm vi: request, partition và nghiệp vụ

~~~mermaid
flowchart LR
    A["JMS / HTTP / Kafka event"] --> B["Transformer + Validator"]
    B --> C["Spring Message<List<OrderEvent>>"]
    C --> D["Cassandra outbound handler"]
    D --> E["ReactiveCassandraOperations / CqlSession"]
    E --> F["Cassandra coordinator"]
    F --> P1[("Partition order-101")]
    F --> P2[("Partition order-102")]
    F --> P3[("Partition order-103")]
~~~

| Ranh giới | Có nghĩa là gì? | Điều không tự được bảo đảm |
|---|---|---|
| **Một Spring Message** | Payload + headers được gửi qua `MessageChannel` | Không đồng nghĩa một CQL BATCH hay một transaction Cassandra |
| **Một CQL BATCH** | Gói nhiều mutations vào một request | Không tự cô lập reads của tất cả partitions |
| **Một Cassandra partition** | Nhóm rows xác định bởi partition key; một tập replicas lưu nó | Không đồng nghĩa Kafka topic partition |
| **Một business event** | Định danh nghiệp vụ, ví dụ `eventId` | Không tự được deduplicate qua retry |
| **Một source acknowledgment** | JMS commit/ack hoặc Kafka offset commit | Không atomic với Cassandra batch completion |

Ngay cả khi một Spring Message mang `List<OrderEvent>`, cách Spring Integration/Spring Data xử lý danh sách mới quyết định nó trở thành batch operation hay nhiều calls; **đừng đoán từ kiểu Java collection mà không kiểm chứng API và version**.

### 2.1. Một flow thành công có những mức xác nhận nào?

~~~mermaid
sequenceDiagram
    participant Src as JMS broker
    participant SI as Spring Integration
    participant DB as Cassandra coordinator
    participant Rep as Cassandra replicas
    Src->>SI: Message<events>
    SI->>DB: CQL BATCH / batchOps
    DB->>Rep: Replicate mutations
    Rep-->>DB: ACK theo consistency level
    DB-->>SI: Response / timeout
    SI-->>Src: Commit hoặc rollback theo policy
    Note over Src,Rep: Cassandra batch và broker commit không chung một ACID transaction
~~~

Khi Cassandra báo thành công, điều đó phản ánh consistency/acknowledgment của thao tác Cassandra; nếu **JMS commit sau đó thất bại**, message vẫn có thể được giao lại. Ngược lại, một handler async có thể làm JMS callback kết thúc **trước khi Cassandra operation hoàn tất**.

## 3. CQL BATCH: cú pháp và quy tắc cơ bản

Cassandra CQL hỗ trợ nhóm các mutation statements bằng:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
    DELETE ...;
APPLY BATCH;
~~~

`BEGIN BATCH` không ghi thêm từ khóa sau `BEGIN` nghĩa là **LOGGED** theo mặc định. Trong cú pháp CQL phổ biến, **không viết `BEGIN LOGGED BATCH`**; hãy dùng đúng:

~~~sql
BEGIN BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

Hai kiểu còn lại:

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO ...;
    UPDATE ...;
APPLY BATCH;
~~~

~~~sql
BEGIN COUNTER BATCH
    UPDATE some_counter_table SET quantity = quantity + 1 WHERE key = 'a';
    UPDATE some_counter_table SET quantity = quantity + 2 WHERE key = 'b';
APPLY BATCH;
~~~

**Chú ý:**

- BATCH thường chỉ chứa mutation `INSERT`, `UPDATE`, `DELETE`; không đặt `SELECT` hoặc DDL như `CREATE TABLE` vào bên trong.
- Không lồng một `BEGIN BATCH` khác trong batch hiện tại.
- Counter mutations cần batch loại `COUNTER`, không trộn với regular mutations.
- Nếu dùng điều kiện `IF` (LWT), có thêm hạn chế về phạm vi cùng partition/statement; không coi nó là batch giao dịch nhiều partition tùy ý.
- Trong batch, các mutations thuộc **cùng partition** có thể được thực thi với tính cô lập trong phạm vi partition. Với **nhiều partition**, các reads đồng thời có thể quan sát chỉ một phần.

### 3.1. Một bảng dùng trong các ví dụ

Với cluster **test** đã có keyspace `shop_integration`, tạo:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_events (
    order_id text,
    event_id text,
    occurred_at timestamp,
    event_type text,
    payload_json text,
    PRIMARY KEY ((order_id), event_id)
);
~~~

Ở bảng này, `order_id` là **partition key**, `event_id` là **clustering column**. Hai events cùng `order_id='ORD-101'` thuộc cùng một Cassandra partition. Hai events của `ORD-101` và `ORD-102` thuộc **hai partitions khác nhau**.

Trong ví dụ production, một order có thể sinh quá nhiều events; khi đó xem xét bucketing/time-window và thiết kế theo query pattern. Không dùng schema lab làm lời khuyên chung cho mọi workload.

### 3.2. BATCH cùng một partition

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-101', 'OrderCreated', '{"step":1}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-102', 'OrderPaid', '{"step":2}');
APPLY BATCH;
~~~

Hai rows có **cùng partition key `ORD-101`**. Cassandra có thể tối ưu LOGGED batch một partition thành thao tác không cần batchlog. Điều cần thiết là **giữ thao tác nhỏ, cùng partition, và phục vụ yêu cầu business**; không batch hàng nghìn events chỉ để giảm số lời gọi Java.

### 3.3. BATCH nhiều partition

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-103', 'OrderPaid', '{"source":"jms"}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-102', 'evt-201', 'OrderCreated', '{"source":"http"}');
APPLY BATCH;
~~~

Hai mutations trên thuộc **hai partitions**. Với LOGGED batch, Cassandra dùng **batchlog** để hỗ trợ hoàn tất tất cả mutation theo cơ chế phục hồi khi coordinator thất bại. **Không có bảo đảm** một client đang đọc `ORD-101` rồi `ORD-102` ở giữa quá trình sẽ thấy cả hai thay đổi cùng lúc.

### 3.4. Thứ tự các câu trong batch không phải thứ tự side effect

Trong một batch, Cassandra có thể dùng **cùng write timestamp** cho các mutations không đặt timestamp riêng. Khi cùng một cột/primary key được ghi nhiều lần với timestamp bằng nhau, conflict resolution có thể khiến kết quả khác với thứ tự dòng trong CQL.

~~~sql
-- ĐỪNG dựa vào hai statement sau để biểu diễn một chuỗi trạng thái.
BEGIN BATCH
    UPDATE shop_integration.order_events
    SET event_type = 'PAID'
    WHERE order_id = 'ORD-101' AND event_id = 'evt-101';

    UPDATE shop_integration.order_events
    SET event_type = 'CANCELLED'
    WHERE order_id = 'ORD-101' AND event_id = 'evt-101';
APPLY BATCH;
~~~

Nếu nghiệp vụ cần `OrderPaid(v2)` đến trước `OrderCancelled(v3)`, hãy dùng **aggregate version**, thiết kế event log theo khóa định danh riêng, và/hoặc conditional mutation phù hợp; **không giả định statement xuất hiện phía sau sẽ luôn thắng**.

## 4. LOGGED batch thực sự bảo đảm điều gì?

Trong CQL truyền thống, **LOGGED BATCH** mang nghĩa Cassandra sử dụng batchlog để các mutations trong batch được **hoàn tất theo cơ chế phục hồi** khi đủ điều kiện. Với **multi-partition**, các updates có thể **hiển thị không đồng thời**.

| Thuộc tính | Một partition | Nhiều partition |
|---|---|---|
| BATCH chứa nhiều mutation | Có | Có |
| Isolated visibility trong phạm vi cùng partition | Có, trong giới hạn Cassandra semantics | **Không** bảo đảm giữa các partitions |
| LOGGED batch có batchlog | Có thể được tối ưu bỏ batchlog | Thường dùng batchlog |
| Khi coordinator chết sau batchlog | Cassandra có cơ chế replay/hoàn tất | Cassandra có cơ chế replay/hoàn tất |
| Đọc mọi rows thấy cùng snapshot tức thời | Chỉ xét phạm vi partition và query/CL phù hợp | **Không** |
| Rollback về trạng thái cũ như SQL transaction | **Không** phải semantics SQL rollback | **Không** |
| JMS/Kafka acknowledgment atomic cùng batch | **Không** | **Không** |

### 4.1. Eventual atomicity khác SQL ACID

Các tài liệu Cassandra mô tả logged batch giúp đảm bảo các mutations được hoàn tất hoặc không áp dụng theo cơ chế batchlog **trong những điều kiện thực thi phù hợp**. Tuy nhiên, điều đó không đồng nghĩa:

- Tất cả partitions chuyển trạng thái cùng một thời điểm quan sát được.
- Các ứng dụng khác không thể đọc trạng thái trung gian.
- Có transaction isolation xuyên nhiều bảng/partitions giống PostgreSQL.
- Khi caller timeout, mọi mutation chắc chắn chưa ghi và có thể tạo event ID mới.
- Có rollback tự động đối với những thay đổi đã được replicas ghi nếu source JMS rollback.

Vì vậy, khi xây logic đọc hai Cassandra partitions theo kiểu “nếu A tồn tại thì B phải nhìn thấy ngay”, **logged batch không đủ để tạo invariant giao dịch đọc ngay lập tức**.

### 4.2. Một trường hợp kiểm tra giữa lúc batch chạy

~~~mermaid
sequenceDiagram
    participant App as Writer
    participant Coord as Coordinator
    participant R1 as Partition A replicas
    participant R2 as Partition B replicas
    participant Reader as Concurrent reader

    App->>Coord: BEGIN LOGGED BATCH (A, B)
    Coord->>Coord: Ghi batchlog (multi-partition)
    Coord->>R1: Mutation A
    R1-->>Coord: ACK A
    Reader->>R1: Read A
    R1-->>Reader: A đã thay đổi
    Reader->>R2: Read B
    R2-->>Reader: B chưa thay đổi
    Coord->>R2: Mutation B / retry khi cần
    R2-->>Coord: ACK B
    Coord-->>App: Completion theo consistency level
~~~

Reader có thể thấy `A=new` trong khi `B=old`. Đây là lý do logged batch **không phải một transaction snapshot xuyên partitions**; dù sau đó batchlog replay giúp đi tới trạng thái hoàn tất, đã có một khoảng quan sát trung gian.

## 5. Batchlog: Cassandra bảo vệ multi-partition batch ra sao?

Batchlog là **cơ chế nội bộ Cassandra**, không phải Kafka topic, JMS queue, Spring `errorChannel` hay một message table của ứng dụng. Coordinator của logged batch nhiều partition ghi thông tin batch vào hạ tầng batchlog, rồi triển khai các mutations tới replicas. Nếu coordinator mất kết nối/sập sau khi batchlog đã được ghi đủ, Cassandra có thể replay những mutations còn thiếu.

~~~mermaid
flowchart TD
    A["Client: logged BATCH A + B"] --> C["Cassandra coordinator"]
    C --> L["Ghi batchlog trên các batchlog endpoints theo cơ chế cluster"]
    L --> D["Gửi mutation A và mutation B"]
    D --> RA["Replica set partition A"]
    D --> RB["Replica set partition B"]
    RA -. "ACK / write đã nhận" .-> X["Đủ điều kiện completion"]
    RB -. "ACK / write đã nhận" .-> X
    X --> R["Xóa/hoàn tất batchlog khi đủ điều kiện"]
    R --> Y["Client response nếu request còn chờ"]
    L -. "Coordinator lỗi" .-> RE["Batchlog replay"]
    RE --> RA
    RE --> RB
~~~

### 5.1. Bốn giai đoạn cần phân biệt

1. **Tiếp nhận:** Coordinator nhận batch và xác định các mutations/partition keys.
2. **Bảo vệ:** Với logged batch cần batchlog, coordinator lưu bản mô tả serialized mutations vào batchlog endpoints trước khi coi batch sẵn sàng để triển khai.
3. **Thực thi:** Coordinator gửi mutation tới các replica sets; việc áp dụng ở partition A có thể hoàn thành trước partition B.
4. **Hoàn tất/khôi phục:** Khi đáp ứng điều kiện áp dụng và lưu/đảm bảo durable tương ứng, batchlog được xóa hoặc replay nếu phát hiện còn công việc.

Cơ chế thực tế có khác biệt theo Cassandra version, replication strategy, hinting và failure handling. **Không suy ra** cứ nhận được `WriteTimeoutException` là batchlog đã được persist chắc chắn; có thể lỗi xảy ra ở những giai đoạn khác nhau. Hãy thiết kế retry/reconciliation cho trạng thái chưa rõ.

### 5.2. Vì sao batchlog không phải hệ thống message queue?

- Nó dùng để **đảm bảo batch mutations được hoàn tất**, không lưu business events dài hạn.
- Không có API consumer application để poll batchlog như một JMS destination.
- Không thay thế sự kiện nguồn, DLQ, outbox hay inbox.
- Không quản lý checkpoint Kafka offset hoặc JMS commit.
- Không giữ một audit history đầy đủ cho nghiệp vụ.
- Có giới hạn tài nguyên, nguy cơ I/O pressure và recovery lag.

Nếu nghiệp vụ yêu cầu một hệ thống reliable ingestion lâu dài, **broker và cơ chế replay của ứng dụng** vẫn phải tồn tại.

### 5.3. Những thời điểm kết quả chưa rõ

| Điểm lỗi | Trạng thái Cassandra có thể | Caller nên làm |
|---|---|---|
| Request chưa tới coordinator | Có thể chưa có mutation | Retry idempotent khi điều kiện cho phép |
| Trong giai đoạn ghi batchlog | Chưa biết mutation nào/bao nhiêu đã áp dụng | Không giả định rollback, dùng read-back/retention policy |
| Sau batchlog, trước khi gửi hết mutations | Có thể còn batchlog để replay | Đợi hội tụ và reconcile; dùng cùng business IDs |
| Một partition đã ACK, partition khác chậm | Partial visibility có thể xuất hiện | Không dùng reads liên-partition làm invariant tức thời |
| Client timeout sau khi batch đã được áp dụng | Có thể batch đã hoàn tất | Không tạo event IDs mới, tránh side effect lặp |
| Broker nguồn commit không thành công sau DB write | Event có thể bị phát lại | Ghi idempotent, phân biệt duplicate/conflict |

## 6. Single-partition BATCH: nơi Cassandra có lợi thế rõ

Với hai mutations cùng partition key `ORD-101` trên **cùng table/partition**, Cassandra hỗ trợ isolation trong phạm vi partition cho batch. Một single-partition logged batch có thể được **tối ưu thành unlogged batch nội bộ**, vì không cần batchlog tốn kém giữa nhiều partitions để bảo vệ mutation cùng partition.

### 6.1. Ví dụ thêm hai events cùng order

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, occurred_at, event_type, payload_json)
    VALUES (
        'ORD-101', 'evt-104',
        '2026-11-23T08:00:00Z', 'OrderValidated', '{"state":"VALID"}'
    );

    INSERT INTO shop_integration.order_events
        (order_id, event_id, occurred_at, event_type, payload_json)
    VALUES (
        'ORD-101', 'evt-105',
        '2026-11-23T08:01:00Z', 'OrderPaid', '{"state":"PAID"}'
    );
APPLY BATCH;
~~~

**Vì sao ổn:** Hai events nằm trong cùng một Cassandra partition; batch nhỏ, phục vụ một business aggregate. Dù vậy **đừng coi batch là hàng đợi tuần tự**: nếu downstream cần cập nhật current order state theo version, phải có logic state machine/version guard.

### 6.2. Lợi ích và hạn chế của batch một partition

| Điểm | Lợi ích | Hạn chế |
|---|---|---|
| Một request từ client | Giảm round trips với một số mutation liên quan | Không luôn nhanh hơn nhiều writes song song |
| Isolation trong partition | Không đọc lẫn trạng thái trung gian của các rows trong cùng partition theo semantics Cassandra | Không mở rộng thành isolation xuyên partitions |
| Ít batchlog overhead hơn | Có thể được tối ưu bỏ batchlog | Vẫn phải xử lý/ghi nhiều mutations |
| Cùng aggregate/order | Dễ ràng buộc batch với nghiệp vụ | Partition quá lớn/hot vẫn là vấn đề |
| Batch retry | Cùng key cố định giúp replay thuận lợi | Không tự deduplicate event IDs mới hoặc xung đột payload |

**Không dùng BATCH để xử lý sự kiện một order có hàng triệu items cùng lúc.** Chia hợp lý theo partition size và workload, hoặc đổi cách mô hình hóa dữ liệu.

## 7. UNLOGGED BATCH: khi nào nên dùng và vì sao dễ dùng sai?

`BEGIN UNLOGGED BATCH` bỏ batchlog. Với **nhiều partitions**, nếu coordinator bị lỗi giữa chừng, một số partitions có thể đã nhận mutation còn những partitions khác chưa được cập nhật; Cassandra **không sử dụng batchlog để bảo đảm hoàn tất tất cả**.

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-u01', 'PaymentRequested', '{}');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-102', 'evt-u02', 'PaymentRequested', '{}');
APPLY BATCH;
~~~

**Đây là ví dụ kỹ thuật để hiểu semantics, không phải khuyến nghị triển khai production.** Hai partitions khác nhau khiến unlogged batch có rủi ro partial application; không có tính cô lập/atomic completion qua các partitions.

### 7.1. Khuyến nghị thường đúng

**Single-partition BATCH** là trường hợp tự nhiên để cân nhắc unlogged/optimized batch. Với nhiều partitions độc lập và mục tiêu chỉ là throughput, thường nên **gửi các writes độc lập bất đồng bộ có concurrency cap** thay vì gộp mọi thứ vào một unlogged batch.

### 7.2. Không dùng UNLOGGED chỉ để "tối ưu" batchlog

Giảm overhead batchlog không có nghĩa các mutations khác partition rẻ hơn. Coordinator vẫn phải đọc và phân phối toàn bộ batch, có thể tạo **hot coordinator**, network/heap pressure và khó phân tán tải giữa các client requests.

| Workload | Lựa chọn nên xem xét |
|---|---|
| Hai mutations liên quan một partition | Single-partition batch nhỏ |
| Ba mutations nhiều partitions, cần cơ chế hoàn tất cùng nhau | LOGGED batch nhỏ, chấp nhận partial visibility |
| 10.000 events độc lập ở nhiều partitions | Concurrent writes có giới hạn, chia chunk ở app |
| Data migration lớn | Backfill theo partition/range có throttle và retry |
| Time series liên tục | Partition key/bucketing, bounded parallelism; không batch toàn bộ ngày |

### 7.3. Không được dùng batch như một JOIN/transaction query

`BATCH` chỉ thực thi mutations. Nó không cho phép `SELECT` trong thân batch để tính toán rồi cập nhật theo kết quả. Muốn conditional write, dùng Cassandra LWT đúng phạm vi; muốn invariant phức tạp xuyên nhiều partitions/tables, phải thiết kế protocol/reconciliation riêng hoặc dùng hệ giao dịch phù hợp hơn.

## 8. COUNTER BATCH: một thế giới khác về idempotency

Cassandra có **counter columns**, cho phép tăng/giảm tổng tích lũy:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event_counters (
    order_id text PRIMARY KEY,
    total_events counter
);
~~~

Ví dụ counter batch:

~~~sql
BEGIN COUNTER BATCH
    UPDATE shop_integration.order_event_counters
    SET total_events = total_events + 1
    WHERE order_id = 'ORD-101';

    UPDATE shop_integration.order_event_counters
    SET total_events = total_events + 2
    WHERE order_id = 'ORD-102';
APPLY BATCH;
~~~

### 8.1. Counter updates không idempotent

Giả sử consumer thực thi `+1`, coordinator áp dụng nhưng response bị mất. Consumer retry cùng mutation `+1`: counter **có thể tăng lần thứ hai**. Driver retry/speculative execution không được dùng mù quáng cho counters.

**Không** đặt `setIdempotent(true)` lên counter batch chỉ để driver tự retry. Không trộn counter mutations với regular INSERT/UPDATE trong một batch.

### 8.2. Khi business cần tổng có thể tái tạo

Nếu mục tiêu là đếm số events đã xử lý chính xác, một thiết kế thường bền vững hơn là:

1. Lưu từng event **có ID cố định** trong bảng event log.
2. Tạo projection/count bằng một consumer có cơ chế deduplication/checkpoint.
3. Có khả năng recompute aggregate từ event log nếu projection bị lệch.

Cassandra counter có thể hợp với workload chấp nhận semantics của counter, nhưng **không phải bộ đếm exactly-once tự động** khi tích hợp cùng JMS/Kafka redelivery.

## 9. Giới hạn batch size và hiệu năng: đừng tối ưu bằng số hàng

Một câu hỏi thường gặp: “Mỗi batch nên chứa bao nhiêu rows?” Không có con số chung áp dụng cho mọi schema, giá trị kích thước payload, distribution hay cluster. Cassandra quan tâm **serialized size, partition count, node health, latency và loại mutation**, không chỉ số lượng Java elements.

### 9.1. Hai ngưỡng an toàn trong cassandra.yaml

Ở nhiều bản Cassandra 4.x/5.x, cấu hình cảnh báo/thất bại cho **multi-partition batch** mặc định thường là:

| Thuộc tính | Giá trị mặc định tham khảo | Ý nghĩa |
|---|---|---|
| `batch_size_warn_threshold_in_kb` (Cassandra 4.x) hoặc `batch_size_warn_threshold` (cấu hình mới) | Khoảng **5 KiB** | Cảnh báo batch nhiều partition có kích thước lớn |
| `batch_size_fail_threshold_in_kb` hoặc `batch_size_fail_threshold` | Khoảng **50 KiB** | Từ chối batch lớn vượt ngưỡng |
| `unlogged_batch_across_partitions_warn_threshold` | Khoảng **10 partitions** | Cảnh báo UNLOGGED batch trải quá nhiều partitions |

Các giá trị này là **mặc định tham khảo có thể thay đổi theo Cassandra version/configuration**; kiểm tra file `cassandra.yaml` thực tế. Không tự tăng ngưỡng từ 50 KiB lên hàng MB chỉ để che cảnh báo: một batch có thể chiếm memory/coordinator resources đáng kể và gây mất ổn định node.

### 9.2. Số row không nói hết serialized size

Giả sử mỗi event JSON ~2 KiB:

~~~text
10 events × 2 KiB  ≈ 20 KiB payload (chưa tính overhead).
30 events × 2 KiB  ≈ 60 KiB payload (chưa tính overhead).

Với một multi-partition batch, 30 rows đã có thể vượt
ngưỡng fail mặc định tham khảo khoảng 50 KiB.
~~~

Ngược lại 100 row nhỏ trong **cùng một partition** có thể khác đáng kể một batch gồm 100 row mỗi row ở một partition khác nhau. **Không** dùng một `MAX_BATCH_ROWS=500` cho mọi workload nếu không đo byte size và number of distinct partition keys.

### 9.3. Vì sao multi-partition logged batch đắt?

~~~mermaid
flowchart TD
    A["Client gửi 1 multi-partition LOGGED BATCH"] --> B["Coordinator quản lý toàn bộ mutations"]
    B --> L["Batchlog I/O"]
    B --> S["Serialize / route mỗi mutation"]
    S --> P1["Partition set A / replicas"]
    S --> P2["Partition set B / replicas"]
    S --> P3["Partition set C / replicas"]
    L --> M["Cleanup / replay bookkeeping"]
    P1 --> C["Response aggregation"]
    P2 --> C
    P3 --> C
~~~

Gộp một nghìn independent writes vào một batch **không** làm Cassandra tự chia coordinator work tối ưu theo số partitions như khi driver gửi các requests độc lập có token-aware routing và concurrency cap. Thường nó **chuyển điểm nghẽn** sang coordinator tiếp nhận batch.

### 9.4. Client-side micro-batching khác CQL batch

Một producer có thể thu thập 100 messages và chia thành 10 nhóm, mỗi nhóm 10 events:

~~~text
Inbound Kafka/JMS messages
  -> buffer/chunk 10 events ở ứng dụng
  -> group by Cassandra partition key
  -> mỗi group chọn:
       (a) single-partition BATCH nhỏ, hoặc
       (b) individual writes bất đồng bộ có giới hạn
  -> theo dõi từng event completion
~~~

**Việc buffer/chunk trong app không đồng nghĩa phải gửi `BEGIN BATCH`.** Đây là quyết định scheduling/backpressure. Trong Spring Integration, `Aggregator`/`ReleaseStrategy` có thể gom messages theo size/time window, nhưng cần quan tâm **message group store** và độ bền của dữ liệu trước acknowledgment.

### 9.5. Khi nào nên ưu tiên từng request độc lập?

Nếu 1000 events thuộc **1000 Cassandra partition keys độc lập**, việc gửi riêng bằng `CqlSession.executeAsync` hoặc reactive operations với concurrency cap có thể khai thác token-aware routing và phân bố tải. Dùng LOGGED batch lớn chỉ vì muốn giảm số lần gọi `send()` thường gây batchlog/hot coordinator overhead.

Nếu **hai đến năm mutations** thuộc các bảng/partitions liên quan và bạn **thực sự cần cơ chế cùng hoàn tất theo batchlog**, LOGGED batch nhỏ có thể phù hợp. Tuy nhiên, nếu cần **khả năng quan sát nhất quán tức thời xuyên partitions**, logged batch vẫn không đáp ứng; cần xem lại mô hình dữ liệu/business invariant.

## 10. Java Driver 4.x: BatchStatement và DefaultBatchType

Driver 4.x có:

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
~~~

| Java Driver type | Vai trò |
|---|---|
| `BatchStatement` | Gói một hoặc nhiều `BatchableStatement<?>` |
| `DefaultBatchType.LOGGED` | Dùng LOGGED semantics |
| `DefaultBatchType.UNLOGGED` | Bỏ batchlog |
| `DefaultBatchType.COUNTER` | Batch counter mutations |
| `SimpleStatement` | CQL + positional values hoặc cấu hình statement |
| `PreparedStatement` | CQL đã prepare, chưa mang values cho một execution |
| `BoundStatement` | CQL đã prepare + values, có thể thêm vào batch |

### 10.1. Tạo LOGGED batch với hai bound statements

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class OrderEventBatchDao {

    private final CqlSession session;
    private final PreparedStatement insertEvent;

    public OrderEventBatchDao(CqlSession session) {
        this.session = session;
        this.insertEvent = session.prepare(
                "INSERT INTO shop_integration.order_events "
                + "(order_id, event_id, event_type, payload_json) "
                + "VALUES (?, ?, ?, ?)");
    }

    public void writeTwoEventsSameOrder(
            String orderId, String eventId1, String eventId2) {

        BoundStatement first = insertEvent.bind(
                orderId, eventId1, "OrderCreated", "json-1");
        BoundStatement second = insertEvent.bind(
                orderId, eventId2, "OrderPaid", "json-2");

        BatchStatement batch = BatchStatement
                .builder(DefaultBatchType.LOGGED)
                .addStatement(first)
                .addStatement(second)
                .build();

        session.execute(batch);
    }
}
~~~

Ví dụ này thực thi **hai row cùng Cassandra partition** (`orderId` giống nhau). Driver tạo LOGGED batch, và Cassandra có thể tối ưu single-partition batch không dùng batchlog. `CqlSession`/`PreparedStatement` được reuse; không tạo một session mới mỗi lần service nhận message.

### 10.2. Kết hợp SimpleStatement và BoundStatement

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement first = SimpleStatement.newInstance(
        "INSERT INTO shop_integration.order_events "
        + "(order_id, event_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "ORD-101", "evt-106", "OrderPacked", "json-3");

BatchStatement batch = BatchStatement.newInstance(
        DefaultBatchType.LOGGED,
        first,
        insertEvent.bind(
                "ORD-101", "evt-107", "OrderShipped", "json-4"));

session.execute(batch);
~~~

Đây là fragment trong DAO có `insertEvent` và `session`. `SimpleStatement.newInstance(query, values...)` dùng **positional values**; Java Driver 4.x **không hỗ trợ simple statements có named parameters trong BatchStatement** theo tài liệu driver 4.19. Nếu cần named binding trong batch, hãy **prepare query rồi bind thành BoundStatement**.

### 10.3. Immutable BatchStatement và builder

Sau khi tạo:

~~~java
// SAI: bỏ kết quả setter, batch gốc không đổi.
batch.setExecutionProfileName("bulk-write");

// ĐÚNG: gán lại kết quả để sử dụng batch có profile mới.
batch = batch.setExecutionProfileName("bulk-write");
~~~

`BatchStatement` built-in của Driver 4.x là **immutable**. `setConsistencyLevel`, `setTimeout`, `setIdempotent` và setter khác trả **BatchStatement mới**; `BatchStatementBuilder` cho phép cấu hình một lần rồi `build()`.

### 10.4. CL, timeout và idempotency ở cấp batch

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;

BatchStatement batch = BatchStatement
        .builder(DefaultBatchType.LOGGED)
        .addStatement(first)
        .addStatement(second)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true)
        .build();

session.execute(batch);
~~~

Ở đây `first`/`second` là `BatchableStatement<?>` đã cấu hình trong method. Các thông số **ví dụ**, không phải defaults cần áp cho mọi cluster:

- `LOCAL_QUORUM` cần replication topology tương ứng; với RF=3 trong một DC, thường cần hai replica responses.
- `timeout(3s)` là **driver request deadline**, không phải giới hạn thời gian batchlog replay sau client timeout.
- `setIdempotent(true)` chỉ hợp lệ về mặt nghiệp vụ nếu **tất cả mutations trong batch đều có thể retry an toàn**.
- Không đánh dấu idempotent cho `COUNTER` batch hoặc mutation có business side effect lặp.

### 10.5. Giới hạn protocol khác giới hạn vận hành

Java Driver 4.x có giới hạn protocol lên tới **65.536 statements** trong một `BatchStatement`. **Đó không phải kích thước batch nên sử dụng**; Cassandra có các ngưỡng **bytes thấp hơn nhiều** đối với multi-partition batch và hệ thống production thường cần giới hạn nhỏ theo workload.

Không xây lệnh dùng 50.000 statements chỉ vì driver không ném lỗi tại bước Java builder. Trước khi tạo batch:

1. Giới hạn **serialized bytes** và số mutation.
2. Giới hạn số distinct partition keys.
3. Chọn logged/unlogged theo invariant.
4. Kiểm tra consistency, timeout và business idempotency.
5. Đo p95/p99, coordinator load và backpressure ở cluster thật.

### 10.6. Async driver request không phải atomic Kafka/JMS commit

~~~java
// Fragment trong DAO:
session.executeAsync(batch).whenComplete((result, error) -> {
    if (error != null) {
        recordFailure(error);
    } else {
        recordCompletion(result);
    }
});
~~~

`recordFailure(...)`/`recordCompletion(...)` là callbacks do ứng dụng định nghĩa. `executeAsync(...)` trả `CompletionStage<AsyncResultSet>`; callback có thể chạy **sau khi caller đã trả về**. Nếu inbound JMS listener đã commit trước callback, một Cassandra failure không tự rollback JMS message.

## 11. Spring Data Cassandra: `ReactiveCassandraBatchOperations`

Spring Data Cassandra cung cấp:

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.ReactiveCassandraBatchOperations;
~~~

Hai API chính là:

~~~java
ReactiveCassandraBatchOperations batch = operations.batchOps();

ReactiveCassandraBatchOperations unlogged =
        operations.batchOps(DefaultBatchType.UNLOGGED);
~~~

Trong Spring Data Cassandra 4.5/5.1, **`batchOps()` mặc định tạo LOGGED batch**. Nếu muốn thay loại, dùng `batchOps(BatchType)`; **không** giả định mọi danh sách entity cần default LOGGED, đặc biệt nếu các entities thuộc nhiều partitions độc lập.

### 11.1. Entity mapping cho nhiều rows một partition

Giả định CQL table `shop_integration.order_events` đã được tạo ở mục 3:

~~~java
import java.io.Serializable;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record OrderEventKey(
        @PrimaryKeyColumn(
                name = "order_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String orderId,
        @PrimaryKeyColumn(
                name = "event_id", ordinal = 1,
                type = PrimaryKeyType.CLUSTERED)
        String eventId
) implements Serializable {}
~~~

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_events")
public record OrderEventEntity(
        @PrimaryKey OrderEventKey key,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson
) {}
~~~

`@PrimaryKeyClass` xác định composite primary key; `PARTITIONED` ở `order_id` và `CLUSTERED` ở `event_id` tương ứng với CQL schema. Java record tự có value equality/`hashCode`; tên cột không khớp cần `@Column`.

Với các Spring Data Cassandra versions hỗ trợ record mapping, có thể dùng record như ví dụ. Nếu phiên bản dự án cũ có hạn chế với immutable record entity/constructor mapping, dùng Java class với no-args constructor/getters/setters và `equals/hashCode` cho key class, rồi kiểm tra mapping bằng integration test.

### 11.2. Ghi một batch entity nhỏ

~~~java
import java.util.List;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderEventBatchService {

    private final ReactiveCassandraOperations operations;

    public OrderEventBatchService(ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> writeSameOrder(List<OrderEventEntity> events) {
        validateSameOrderAndLimit(events);

        return operations.batchOps()
                .insert(events)
                .execute()
                .then();
    }

    private static void validateSameOrderAndLimit(
            List<OrderEventEntity> events) {
        if (events == null || events.isEmpty() || events.size() > 10) {
            throw new IllegalArgumentException("Batch cần 1..10 events");
        }
        if (events.get(0) == null || events.get(0).key() == null
                || events.get(0).key().orderId() == null
                || events.get(0).key().orderId().isBlank()) {
            throw new IllegalArgumentException("Partition key đầu tiên không hợp lệ");
        }
        String orderId = events.get(0).key().orderId();
        if (events.stream().anyMatch(
                e -> e == null || e.key() == null
                        || !orderId.equals(e.key().orderId())
                        || e.key().eventId() == null
                        || e.key().eventId().isBlank())) {
            throw new IllegalArgumentException(
                    "Tất cả events phải có cùng Cassandra partition key");
        }
    }
}
~~~

Ở đây `10` là giới hạn **minh họa**, không phải Cassandra hard limit. Production phải tính payload bytes, số mutations, p99 và cluster configuration. Service **cố ý giới hạn cùng `orderId`** vì đây là ví dụ single-partition batch.

### 11.3. Batch operations có lifecycle một lần

Tài liệu Spring Data mô tả `ReactiveCassandraBatchOperations` **chỉ được thực thi một lần**. Sau `execute()` và subscription, instance batch không được thêm mutation hoặc execute lại:

~~~java
// Đúng: tạo instance mới cho mỗi batch invocation.
return operations.batchOps(DefaultBatchType.LOGGED)
        .insert(events)
        .execute();
~~~

Nếu retry, **không reuse một batch operations object đã execute**. Thay vào đó tạo một instance mới trong một `Mono.defer(...)` để mỗi subscription/retry tạo batch riêng:

~~~java
import reactor.core.publisher.Mono;

Mono<Void> saveWithRecreatableBatch(List<OrderEventEntity> events) {
    validateSameOrderAndLimit(events);

    return Mono.defer(() ->
            operations.batchOps(DefaultBatchType.LOGGED)
                    .insert(events)
                    .execute()
                    .then());
}
~~~

Không tự thêm `retryWhen(...)` vào mọi Cassandra write: chỉ retry khi mutation idempotent và có hạn mức. `Mono.defer` giải quyết vấn đề **recreate batch state**; nó **không** làm business effect tự idempotent.

### 11.4. Tùy chỉnh QueryOptions của batch

Với Spring Data Cassandra **4.4+** có `withQueryOptions(QueryOptions)`:

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.QueryOptions;
import reactor.core.publisher.Mono;

QueryOptions options = QueryOptions.builder()
        .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .timeout(Duration.ofSeconds(3))
        .build();

Mono<Void> result = operations.batchOps(DefaultBatchType.LOGGED)
        .insert(events)
        .withQueryOptions(options)
        .execute()
        .then();
~~~

`operations`, `events` là biến đã có trong service. `LOCAL_QUORUM` chỉ thích hợp với replication topology đã kiểm chứng; timeout 3 giây là giá trị lab. Nếu đang dùng Spring Data version không hỗ trợ `withQueryOptions`, đối chiếu Javadoc phiên bản đó và cấu hình driver statement/execution profile thay vì sao chép API không tồn tại.

### 11.5. Batch có cả insert/update/delete

~~~java
return operations.batchOps(DefaultBatchType.LOGGED)
        .insert(newEvent)
        .update(existingEntity)
        .delete(oldEntity)
        .execute();
~~~

Đây là fragment minh họa khi `newEvent`, `existingEntity`, `oldEntity` có mapping đúng. Tất cả mutations phải thuộc **phạm vi dữ liệu mà bạn đã phân tích partition keys và business semantics**. Nếu objects thuộc các partitions khác nhau, bạn đang tạo **multi-partition batch**; không được tự coi rằng ba actions sẽ hiển thị tức thời cho các readers liên-partition.

### 11.6. Lưu ý về timestamp của batch

Spring Data `ReactiveCassandraBatchOperations` hỗ trợ `withTimestamp(long)` để gắn timestamp chung cho batch. CQL batch cũng có `USING TIMESTAMP` theo quy tắc Cassandra. **Đừng dùng timestamp chung để biểu diễn thứ tự nghiệp vụ của hai updates cạnh tranh tới cùng cột**; do last-write-wins, các mutation trùng timestamp có thể dẫn đến conflict resolution không giống thứ tự sắp trong Java list.

Khi cần current-state ordering, dùng business `aggregateVersion`/LWT hoặc mô hình event log bất biến; tránh batch hai updates cùng row rồi suy ra statement sau chắc thắng.

## 12. Spring Integration Cassandra: payload List và ingestQuery

Spring Integration Cassandra (từ 6.0) dùng `CassandraMessageHandler` với `ReactiveCassandraOperations`. Handler hỗ trợ:

- `Type.INSERT`, `UPDATE`, `DELETE`: payload entity `@Table`; nếu payload **`List<entity>`**, handler thực hiện batch operation phù hợp.
- `setIngestQuery(...)`: mode INSERT với payload **ma trận `List<List<?>>`**.
- `Type.STATEMENT` / `statementFunction(...)`: người dùng cung cấp driver `Statement<?>`, trong đó có thể là `BatchStatement`.
- Outbound **channel adapter** một chiều (không reply mặc định); outbound **gateway** cho flow cần reply/result.

### 12.1. Java DSL cho List<entity>

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraBatchIntegrationConfig {

    @Bean
    public IntegrationFlow batchOrderEventsFlow(
            ReactiveCassandraOperations operations) {
        return IntegrationFlow.from("validatedOrderEventBatches")
                .handle(Cassandra.outboundChannelAdapter(
                        operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Input channel nhận Spring Message có payload `List<OrderEventEntity>`, **không phải list JSON strings**. Validate và map trước khi đến endpoint; trong ví dụ single-partition batch, ứng dụng phải bảo đảm các elements có **cùng `orderId`**.

Đối với List entity, Spring Integration Reference nói handler thực hiện **batch operation**. Spring Data `batchOps()` mặc định LOGGED; nếu cần chọn **UNLOGGED** hoặc chủ động kiểm soát `BatchStatement`, hãy dùng service activator/driver API hoặc `statementFunction(...)` rõ ràng, thay vì giả định một thuộc tính không có trong DSL sẽ đổi loại batch.

### 12.2. Gửi một Spring Message chứa danh sách

~~~java
import java.util.List;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

List<OrderEventEntity> batch = List.of(
        new OrderEventEntity(
                new OrderEventKey("ORD-101", "evt-108"),
                "OrderConfirmed", "json-5"),
        new OrderEventEntity(
                new OrderEventKey("ORD-101", "evt-109"),
                "OrderPaid", "json-6")
);

boolean accepted = validatedOrderEventBatches.send(
        MessageBuilder.withPayload(batch).build());
if (!accepted) {
    throw new IllegalStateException("Spring Message was not accepted");
}
~~~

`validatedOrderEventBatches` là bean `MessageChannel` được inject. `send(true)` chỉ mang semantics của channel/endpoint; khi handler chạy **async mặc định**, write có thể vẫn đang xử lý sau khi `send()` trả về. Với `async(false)` và `DirectChannel`, exception có thể propagate về caller nhưng Cassandra và JMS vẫn không chung transaction.

### 12.3. `ingestQuery(...)`: payload matrix khác List entity

Spring Integration cung cấp cú pháp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow ingestOrderEventsFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("cassandraIngestInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(
                        "INSERT INTO order_events "
                        + "(order_id, event_id, event_type, payload_json) "
                        + "VALUES (?, ?, ?, ?)"),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Ví dụ payload:

~~~java
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> matrix = List.of(
        List.<Object>of("ORD-101", "evt-i01", "OrderPacked", "json-a"),
        List.<Object>of("ORD-101", "evt-i02", "OrderShipped", "json-b")
);

cassandraIngestInput.send(
        MessageBuilder.withPayload(matrix).build());
~~~

Mỗi inner list khớp **bốn `?` markers** theo thứ tự và codec CQL. `List.of(...)` không chứa Java null; nếu cần null/UNSET phải làm rõ contract và dùng API phù hợp.

**Không nhầm:** `ingestQuery` là chế độ Cassandra outbound handler nhận **ma trận**; nó không đồng nghĩa một Spring `Aggregator`, cũng không tự đảm bảo logged/unlogged theo lựa chọn của bạn nếu DSL không cho chọn batch type. Đọc Javadoc/kiểm thử phiên bản đang chạy khi việc lựa chọn batch type là business requirement.

### 12.4. Dùng statementFunction để đưa một BatchStatement đã xây

~~~java
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow explicitBatchStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("explicitBatchRequests")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        BatchPayload request =
                                (BatchPayload) message.getPayload();

                        if (request == null || request.items() == null
                                || request.items().isEmpty()
                                || request.items().size() > 5) {
                            throw new IllegalArgumentException(
                                    "Batch size phải trong 1..5");
                        }

                        BatchItem firstItem = request.items().get(0);
                        if (firstItem == null || firstItem.orderId() == null
                                || firstItem.orderId().isBlank()) {
                            throw new IllegalArgumentException(
                                    "Partition key đầu tiên không hợp lệ");
                        }
                        String orderId = firstItem.orderId();
                        if (request.items().stream().anyMatch(
                                        item -> item == null
                                                || item.eventId() == null
                                                || item.eventId().isBlank()
                                                || !orderId.equals(item.orderId()))) {
                            throw new IllegalArgumentException(
                                    "Batch lab chỉ nhận cùng orderId và eventId hợp lệ");
                        }

                        var builder = BatchStatement.builder(
                                DefaultBatchType.LOGGED);
                        for (BatchItem item : request.items()) {
                            builder.addStatement(SimpleStatement.newInstance(
                                    "INSERT INTO order_events "
                                    + "(order_id, event_id, event_type, payload_json) "
                                    + "VALUES (?, ?, ?, ?)",
                                    item.orderId(),
                                    item.eventId(),
                                    item.eventType(),
                                    item.payloadJson()));
                        }
                        return builder.build();
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Các DTO:

~~~java
import java.util.List;

public record BatchItem(
        String orderId, String eventId,
        String eventType, String payloadJson) {}

public record BatchPayload(List<BatchItem> items) {}
~~~

`CassandraMessageHandler` trong mode STATEMENT có thể thực thi một driver `BatchStatement` mà `statementFunction` trả về. Code trên dùng **positional SimpleStatement values** để tránh CQL injection; không lấy raw CQL query từ header client.

**Thiếu các bước quan trọng nếu bê nguyên fragment vào production:** ví dụ kiểm tra số phần tử, `eventId` và cùng `orderId`, nhưng chưa kiểm tra tổng serialized bytes, `eventType`/JSON contract, authorization, uniqueness và toàn bộ quotas. Ví dụ chỉ nhận **single-partition batch**; nếu bỏ kiểm tra cùng `orderId` và gửi nhiều orders, đó là **multi-partition logged batch** với partial visibility và batchlog overhead.

### 12.5. Adapter hay gateway?

| Endpoint | Dùng khi | Lưu ý |
|---|---|---|
| `Cassandra.outboundChannelAdapter(...)` | Ghi một chiều, không cần Spring reply | Theo dõi completion/error path |
| `Cassandra.outboundGateway(...)` | Cần reply/result/query output | Reactive result/`WriteResult` tùy operation/version |
| Custom `@ServiceActivator` gọi `batchOps(...)` | Cần chủ động chọn batch type, response/error policy | Không mặc định có source ACK linkage |
| Custom `@ServiceActivator` dùng driver `BatchStatement` | Cần kiểm soát trực tiếp CQL options/timestamp/types | Tự chịu trách nhiệm lifecycle/metrics/retry |

Khi muốn kiểm tra conditional batch/LWT `[applied]`, không chỉ dùng một outbound adapter không reply rồi coi `send(true)` là điều kiện đã đạt. Dùng gateway/driver API đọc kết quả và hiểu các giới hạn conditional batch của Cassandra.

## 13. Chọn phương án ghi theo workload, không theo sở thích batch

### 13.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Có nhiều mutations cần ghi?"] --> B{"Cùng Cassandra partition?"}
    B -->|"Có"| C{"Các mutations gắn một business aggregate?"}
    C -->|"Có"| D["Cân nhắc single-partition batch nhỏ"]
    C -->|"Không"| E["Các writes riêng hoặc batch nhỏ theo nhu cầu"]
    B -->|"Không"| F{"Thật sự cần eventual completion cùng nhau?"}
    F -->|"Có, ít mutations"| G["Multi-partition LOGGED batch nhỏ"]
    F -->|"Không, throughput là mục tiêu"| H["Independent async writes + bounded concurrency"]
    D --> I["Đo p99, failure và idempotency"]
    E --> I
    G --> I
    H --> I
~~~

### 13.2. Bảng lựa chọn

| Workload | Cơ chế nên xét | Vì sao | Không nên |
|---|---|---|---|
| Một event → một row duy nhất | Một INSERT độc lập | Đơn giản, routing hiệu quả | Tạo batch một statement vô ích |
| Một event → ba rows cùng partition | Single-partition BATCH nhỏ | Isolation trong partition, ít overhead hơn | Gửi các batch lớn xuyên partitions |
| Hai rows ở hai tables/partitions cần cùng hoàn tất về sau | Multi-partition LOGGED BATCH nhỏ | Batchlog hỗ trợ recovery | Coi reads từ hai bảng là atomic snapshot |
| 10.000 events độc lập | Async writes có concurrency cap | Token-aware routing, phân bố coordinator | LOGGED BATCH 10.000 rows |
| Backfill nhiều partitions | Partition-aware chunks + throttle | Recovery/giám sát từng đoạn | Unbounded ingest batch |
| Cập nhật counter tổng | COUNTER mutation/batch khi phù hợp | Counters có semantics riêng | Retry mù quáng |
| Update current state có version guard | LWT single-partition phù hợp | Bảo vệ compare-and-set | Dùng logged batch thay version check |

### 13.3. Gom message theo order: phân biệt business và Cassandra partition

Trong Spring Integration có `Aggregator` gom nhiều Spring messages thành một message chứa list. Nếu bạn `correlate` theo `orderId`, các phần tử **có thể** cùng Cassandra partition khi schema partition key là `order_id`.

Nhưng nếu Cassandra partition key là `(tenantId, orderId, bucketMonth)`, grouping chỉ bằng `orderId` **chưa đủ**. Các messages xuyên tháng hoặc khác tenant sẽ thuộc **nhiều partitions** dù Java group chỉ có một `orderId`.

**Rule:** tính Cassandra partition key từ **CQL schema** và payload đã xác thực; thiết kế Spring correlation/group key khớp **toàn bộ composite partition key**, không chỉ một header đại diện.

### 13.4. Một predicate đơn giản cho single-partition batch

~~~java
static void requireSamePartition(List<OrderEventEntity> events) {
    if (events == null || events.isEmpty()) {
        throw new IllegalArgumentException("Batch rỗng");
    }
    String orderId = events.get(0).key().orderId();
    if (events.stream().anyMatch(e ->
            e == null || e.key() == null
                    || !orderId.equals(e.key().orderId()))) {
        throw new IllegalArgumentException(
                "Các rows không cùng Cassandra partition");
    }
}
~~~

Code áp dụng cho **schema lab có partition key chỉ là `orderId`**. Với composite partition key, kiểm tra *tất cả partition columns*. Nếu `orderId` là null, phải validate trước thay vì gọi `equals` trên null.

### 13.5. Tính lô theo bytes, không chỉ row count

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

static void validateBatchSize(List<BatchItem> items) {
    if (items == null || items.isEmpty() || items.size() > 10) {
        throw new IllegalArgumentException("Tối đa 10 items trong lab");
    }

    long estimatedBytes = items.stream()
            .mapToLong(item -> {
                if (item == null || item.payloadJson() == null) {
                    throw new IllegalArgumentException("Payload thiếu");
                }
                return item.payloadJson()
                        .getBytes(StandardCharsets.UTF_8).length;
            })
            .sum();

    if (estimatedBytes > 16 * 1024) {
        throw new IllegalArgumentException(
                "Payload JSON của batch vượt mức lab");
    }
}
~~~

**Giới hạn 16 KiB chỉ minh họa.** Đoạn code cộng bytes JSON, **chưa** tính Cassandra serialization, tên fields, protocol overhead, partition keys và các mutation metadata. Production phải áp dụng giới hạn an toàn thấp hơn ngưỡng fail thực tế với margin thích hợp, đồng thời kiểm tra **số partition keys**.

## 14. Consistency level, timestamp và TTL trong batch

### 14.1. Consistency vẫn là điều kiện ACK của Cassandra

Ví dụ RF=3 ở một DC, `LOCAL_QUORUM` chờ quorum hai replica responses theo rule của consistency level. Nhưng khi batch có **nhiều partitions**, có **nhiều tập replicas** tham gia. Logged batchlog giúp hoàn tất mutation qua lỗi, **không** có nghĩa tất cả replicas của mọi partition đã áp dụng mutation đồng thời khi client thấy success.

| CL | Ý nghĩa chính | Giới hạn với multi-partition BATCH |
|---|---|---|
| `ONE` | Một replica response theo policy | Không tạo snapshot giữa partitions |
| `LOCAL_QUORUM` | Quorum local DC | Không tạo cross-partition isolation |
| `ALL` | Chờ tất cả replicas liên quan | Availability giảm khi replica không đáp ứng, không thành SQL transaction |
| `SERIAL`/`LOCAL_SERIAL` | Serial consistency cho LWT | Không áp cho regular batch như một CL chung |

### 14.2. Một batch có thể dùng cùng write timestamp

~~~sql
BEGIN BATCH USING TIMESTAMP 1763884800000000
    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-t01', 'OrderPacked', 'json-a');

    INSERT INTO shop_integration.order_events
        (order_id, event_id, event_type, payload_json)
    VALUES ('ORD-101', 'evt-t02', 'OrderShipped', 'json-b');
APPLY BATCH;
~~~

`USING TIMESTAMP` của CQL dùng **microseconds từ Unix epoch**, không phải Java `Instant.toEpochMilli()` nguyên dạng. Giá trị trên chỉ là **timestamp minh họa**, không phải clock hiện tại cần bắt buộc sử dụng. Nếu đã có timestamp ở batch level, không kết hợp tùy ý với per-statement timestamps theo CQL restriction của version đang dùng.

**Không nhầm** Cassandra **write timestamp** với business `occurredAt`/`aggregateVersion`. Timestamp server dùng cho conflict resolution; nếu hai mutations cùng column/row có timestamp bằng nhau, kết quả có thể phụ thuộc tie-break rules chứ không dựa trên vị trí trong BATCH.

### 14.3. TTL của một sự kiện khác timeout của batch

| Thuộc tính | Mục đích |
|---|---|
| CQL `USING TTL n` / Spring Data `WriteOptions.ttl(...)` | Thời gian dữ liệu được giữ trước expiration |
| Driver `Statement.setTimeout(Duration)` | Thời gian client chờ Cassandra request result |
| Cassandra `write_request_timeout` | Coordinator chờ replica ACK |
| `JMS timeToLive` | Thời gian JMS message còn hợp lệ trên broker |
| Spring gateway `replyTimeout` | Thời gian chờ Spring reply |

Đặt TTL cho một Cassandra row **không làm source JMS message tự acknowledge**, không tạo retry policy, cũng không dừng batchlog recovery. Khi dùng TTL trong retry, lưu ý **gửi lại có thể thay đổi thời điểm expiration** và mutation timestamps; phải đánh giá idempotency thực sự của dữ liệu.

### 14.4. Conditional batch/LWT không phải regular logged batch

Một conditional `IF NOT EXISTS` hoặc `IF version = ?` yêu cầu **LWT/Paxos** với serial consistency và điều kiện hợp lệ trong phạm vi Cassandra cho phép. Conditional batch có các restriction (đặc biệt các mutations liên quan cùng partition) mà regular batch không có.

**Ví dụ định hướng:** nếu nghiệp vụ yêu cầu chỉ chuyển state từ `PAID(version=2)` sang `SHIPPED(version=3)` khi version chưa đổi, hãy dùng **conditional update** phù hợp. Đừng batch hai `UPDATE state` liên tiếp rồi cho rằng LOGGED giải quyết được tranh chấp concurrent writers.

## 15. Timeout, retry và idempotency của một batch

### 15.1. Timeout không nói được bao nhiêu mutations đã ghi

~~~mermaid
sequenceDiagram
    participant JMS as JMS Broker
    participant App as Integration Handler
    participant Coord as Cassandra Coordinator
    participant R1 as Partition A replicas
    participant R2 as Partition B replicas
    JMS->>App: Deliver eventBatchId=batch-001
    App->>Coord: BEGIN BATCH A,B
    Coord->>R1: Apply A
    R1-->>Coord: ACK
    Coord->>R2: Apply B
    Note over Coord,App: Network response lost / client timeout
    Coord--xApp: Không có response đúng hạn
    App-->>JMS: Exception -> rollback theo listener policy
    JMS->>App: Redeliver batch-001
    Note over App: Retry cùng business IDs và partitions
~~~

**Có thể** A và B đã ghi; cũng có thể chỉ A hiển thị tạm trong khi batchlog/retry đang hoàn tất B; cũng có thể request không được nhận. Caller cần **idempotent retry/reconciliation**, không sinh IDs mới chỉ vì timeout.

### 15.2. Idempotent BATCH phải idempotent ở từng mutation

| Mutation | Retry cả batch | Ghi chú |
|---|---|---|
| INSERT immutable event, cùng full primary key | Thường phù hợp | Nếu TTL/timestamp/payload nhất quán |
| DELETE cùng primary key | Thường có thể, nhưng cần xem timestamp/GC | Tombstones và concurrent writes có thể ảnh hưởng |
| UPDATE state theo version guard | Có điều kiện | Kiểm tra applied result, ordering |
| Increment Cassandra counter | **Không** an toàn khi retry mù | Có thể tăng hai lần |
| INSERT eventId mới tạo trong consumer | **Không** an toàn | Retry tạo row nghiệp vụ mới |
| Gửi email/HTTP sau batch | **Không** được batch bảo vệ | Cần idempotency ở hệ ngoài |

**Dán `setIdempotent(true)` lên BatchStatement không tự biến từng mutation thành idempotent.** Driver dùng flag để quyết định các retries/speculative executions theo policy, không lưu inbox deduplication.

### 15.3. Retry budget qua nhiều tầng

Giả sử:

~~~text
Driver retry:                 tối đa 1 retry/request
Service-layer retry:          tối đa 2 retries/delivery
JMS broker redelivery:        tối đa 5 deliveries
Batch mutations/request:     3
~~~

Một event group có thể dẫn đến nhiều lần gửi mutation vượt xa tưởng tượng. Nếu mỗi service attempt có hai driver executions và mỗi delivery có ba service attempts, với năm deliveries là **tới 30 batch executions**, tương đương **tới 90 mutation attempts** trước khi xét speculative executions. Không nên để retry storm cùng lúc nhân lên trên mọi nodes/partitions.

### 15.4. Giới hạn retry dựa trên loại exception

| Lỗi | Chiến lược gợi ý |
|---|---|
| `DriverTimeoutException` | Outcome chưa chắc; idempotent retry có giới hạn/reconcile |
| `WriteTimeoutException` | Có thể đã áp một số mutation; retry cẩn trọng |
| `UnavailableException` | Giảm tải, kiểm tra cluster/CL; backoff |
| `OverloadedException` | Giảm concurrency/batch size; tránh hot retry |
| `InvalidQueryException` | Fail fast, sửa schema/CQL; không retry |
| Codec/type mismatch | Sửa contract/mapping; không retry cùng input |
| Authorization failure | Sửa ACL/secrets; không retry vô hạn |
| LWT applied=false | Business condition không đạt; không coi là transport failure |

### 15.5. Batch không phải một rollback journal

Không viết logic:

~~~text
try {
    loggedBatch();
} catch (TimeoutException ex) {
    // SAI: khẳng định database không ghi gì và tạo IDs mới.
    createNewIdsAndRetry();
}
~~~

Thay bằng:

~~~text
onTimeout(batchId):
    keep original event IDs and full Cassandra primary keys
    classify retryable vs permanent errors
    retry only if idempotent and within budget
    read/reconcile when the outcome is unknown
    quarantine conflicting duplicates or unrepairable events
~~~

Đây là **pseudocode**, không phải API Spring sẵn có. Cassandra và broker không cùng rollback boundary.

## 16. JMS/Kafka acknowledgment: "batch thành công" thuộc hệ nào?

### 16.1. Một listener JMS nhận message chứa batch

~~~mermaid
flowchart LR
    JMS["JMS message batch-001"] --> L["Message-driven inbound adapter"]
    L --> D["DirectChannel"]
    D --> V["Validator/Transformer"]
    V --> C["Cassandra handler async=false"]
    C --> DB[("Cassandra logged batch")]
    DB -. "Completion / error" .-> C
    C -. "Propagate" .-> L
    L --> ACK["JMS commit / rollback theo policy"]
~~~

Trong một flow đồng bộ có listener transacted, exception Cassandra có thể truyền ngược về JMS listener và làm broker **redeliver**. Nhưng nếu Cassandra đã áp các mutations và JMS commit bị lỗi hoặc JVM crash, batch sẽ **được gửi lại**; cần idempotency.

### 16.2. Khi dùng ExecutorChannel hoặc handler async mặc định

~~~text
JMS receive
   -> in-memory ExecutorChannel
   -> callback listener trả về
   -> JMS commit (theo cấu hình)
   -> batch Cassandra bắt đầu / hoàn tất sau
   -> Cassandra timeout / lỗi
   -> Không thể rollback JMS đã commit
~~~

`CassandraMessageHandler` trong Spring Integration **mặc định async=true**. Chọn `async(false)` giúp operation được chờ trong đường xử lý synchronous khi phù hợp; không tự tạo transaction atomic giữa Cassandra và JMS. `QueueChannel`/`ExecutorChannel` in-memory không phải durable queue để thay thế broker.

### 16.3. Kafka: commit offset không theo CQL batch

Kafka offset nói consumer đã xử lý tới vị trí nào theo policy; **không** có giao dịch nguyên tử với Cassandra BATCH. Nếu consumer commit offset trước khi Cassandra hoàn thành, lỗi downstream có thể mất cơ hội replay tự động. Nếu Cassandra hoàn thành rồi JVM crash trước offset commit, record có thể bị phát lại.

Thiết kế bền vững cần một hoặc nhiều cơ chế:

1. Chỉ ack/commit nguồn sau khi Cassandra completion trong phạm vi cơ chế có thể thực hiện.
2. Durable handoff/inbox để có thể replay sau lỗi async.
3. Idempotent event IDs và deterministic primary keys.
4. Reconciliation khi outcome chưa rõ và có thể đọc partial visibility.
5. DLQ/quarantine cho lỗi dữ liệu không thể sửa bằng retry.

### 16.4. Một message chứa 10 events có thể hỏng một event

Trong nhiều flow, input JMS message mang **một batch chứa 10 business events**. Nếu một element có invalid CQL type:

- Handler có thể từ chối cả batch hoặc operation fail trước khi write.
- Broker có thể redeliver **toàn bộ JMS message**.
- Retry lặp không tự sửa element sai kiểu.
- Một DLQ cho cả batch có thể khiến 9 events tốt chờ cùng 1 event lỗi.

Hãy quyết định policy:

- **Fail toàn batch:** khi tất cả events thực sự là một business unit.
- **Split và quarantine từng event:** khi events độc lập và cần tối đa throughput/availability.
- **Durable preprocessing:** parse/validate từng event trước khi gom, tránh poison batch.

Không tự tách logged batch thành các writes độc lập nếu yêu cầu nghiệp vụ cần cơ chế completion chung; phải làm rõ invariant trước.

## 17. Lifecycle, validation và quan sát batch trong production

### 17.1. Vòng đời từ source message đến batch completion

~~~mermaid
flowchart TD
    R["Receive Spring Message"] --> V["Validate schema, tenant, IDs, payload sizes"]
    V --> K["Tính Cassandra partition key"]
    K --> G{"Single partition?"}
    G -->|"Có"| S["Batch nhỏ hoặc independent writes"]
    G -->|"Không"| N{"Cần batchlog completion?"}
    N -->|"Có"| L["LOGGED batch nhỏ"]
    N -->|"Không"| I["Independent async writes, bounded"]
    S --> E["Execute"]
    L --> E
    I --> E
    E --> O{"Completion được quan sát?"}
    O -->|"Success"| C["Ack/checkpoint theo policy"]
    O -->|"Error/unknown"| X["Retry idempotent / reconcile / DLQ"]
~~~

**Thông điệp:** validate và phân loại **trước** khi chạm Cassandra, thay vì để một batch nhiều partition khổng lồ thất bại ở coordinator. Một batch có thể chưa hoàn tất ngay khi `send()` trả true nếu downstream dùng async.

### 17.2. Hợp đồng metadata hữu ích

| Field/header | Nguồn đáng tin cậy | Mục đích |
|---|---|---|
| `eventId` | Business producer | Idempotent key của từng event |
| `batchId` | Application aggregator/producer | Correlation/logging, không thay event IDs |
| `tenantId` | Authenticated context | Scope và authorization |
| `partitionKey` | Transformer từ schema/payload | Quyết định single- hay multi-partition batch |
| `schemaVersion` | Validated event contract | Chọn DTO/transformer tương thích |
| `receivedAt` | Message transport/time source | Observability, không thay event `occurredAt` |
| `retryAttempt` | Retry infrastructure | Theo dõi retry budget |
| `traceId` | Tracing infrastructure | Liên kết lỗi source→Cassandra |

**`batchId` là ID của nhóm xử lý, không phải unique primary key của mọi event.** Nếu retry sinh một batchId mới nhưng event IDs và primary keys vẫn giữ nguyên, ứng dụng vẫn có thể idempotent; tuy nhiên đối soát theo batchId cần mapping nguồn/đích rõ ràng.

### 17.3. Không nhận raw CQL từ message ngoài

Trong `statementFunction(...)`, tuyệt đối tránh:

~~~java
// KHÔNG LÀM: query đến trực tiếp từ HTTP/JMS payload.
SimpleStatement unsafe = SimpleStatement.newInstance(
        (String) message.getPayload());
~~~

Thay bằng query **tĩnh** và bind values:

~~~java
SimpleStatement safe = SimpleStatement.newInstance(
        "INSERT INTO order_events "
        + "(order_id, event_id, event_type, payload_json) VALUES (?, ?, ?, ?)",
        item.orderId(), item.eventId(), item.eventType(), item.payloadJson());
~~~

Trong câu này, `item` là DTO `BatchItem` đã validate. Prepared/bound values không cho phép client thay tên table/cột/operation; nếu cần nhiều tables, chỉ chọn từ **allowlist** đã được code định nghĩa, không nối string tự do từ client headers.

### 17.4. Không tạo một singleton batch builder

`CqlSession` là tài nguyên thread-safe dùng lâu dài. `PreparedStatement` có thể được reuse. Nhưng:

- `BatchStatementBuilder` là builder mutable cho **một batch invocation**, không dùng chung cho các threads.
- `BatchStatement` built-in immutable; tạo một instance mới cho mỗi group.
- `ReactiveCassandraBatchOperations` là builder/operation object **execute một lần**, không giữ làm singleton bean xử lý mọi event.
- `MessageChannel` là đường chuyển messages, không tự giữ durable state sau process crash.

### 17.5. Shutdown và in-flight batches

Khi service nhận SIGTERM/kết thúc Spring context:

1. Dừng nhận messages mới ở inbound endpoints/broker listener theo cơ chế của platform.
2. Đợi các **in-flight Cassandra batches** trong phạm vi shutdown budget, nếu infrastructure hỗ trợ.
3. Không commit JMS/Kafka source trước completion khi business contract yêu cầu.
4. Giữ durable replay path nếu shutdown quá deadline.
5. Khôi phục với cùng event IDs/batch membership có thể tái tạo.

Đừng khẳng định một `stop()` trên endpoint tự đợi mọi Cassandra reactive operation đã ghi thành công; phải kiểm thử shutdown behavior của cấu hình đang dùng.

## 18. Observability: tìm bottleneck đúng tầng

| Metric/log | Nơi đo | Cần quan sát |
|---|---|---|
| Batch requests/s | Application/driver | Tần suất batch |
| Mutations/batch p50/p95/p99 | Application | Có batch đột ngột quá nhiều rows? |
| Serialized bytes/batch | Application/driver | Vượt ngưỡng warn/fail? |
| Distinct partition keys/batch | Application | Có multi-partition batch nhiều key? |
| LOGGED vs UNLOGGED vs COUNTER | Application config | Loại batch có tương ứng business invariant? |
| Cassandra BatchlogReplays | Cassandra cluster | Coordinator failure/replay hoạt động ra sao? |
| BatchSize / unlogged-across-partitions warnings | Cassandra logs/metrics | Anti-pattern batch |
| Coordinator write latency p95/p99 | Cassandra/driver | Hot coordinator, network/I/O |
| Pending tasks/compactions/tombstones | Cassandra nodes | Quá tải nền hoặc delete pressure |
| Driver retries/timeouts | Driver | Retry storm, latency |
| Reactive in-flight operations | Application | Thiếu concurrency cap hoặc không drain |
| JMS queue depth/Kafka lag | Source broker | Cassandra chậm gây backlog |
| Duplicate/conflicting event IDs | Domain metrics | Replay/bad producer contract |
| DLQ/quarantine rate | Integration error flow | Poison messages/batch failures |

**Không mặc định `BatchlogReplays=0` là lỗi:** khi cluster khỏe, số batchlog replays có thể thấp. Điều đáng chú ý là replay tăng bất thường đồng thời write timeouts/latency tăng, hoặc batchlog cleanup bị chậm.

### 18.1. Query cảnh báo Cassandra cần xử lý gì?

Nếu logs báo một **large batch** hoặc **unlogged batch across many partitions**:

1. Truy nguyên `batchId`, nguồn, số distinct partition keys và bytes.
2. Xác định liệu batch dùng **logged** chỉ để tăng throughput hay thực sự cần completion semantics.
3. Chia/chuyển qua **independent async writes** có concurrency cap nếu các mutations độc lập.
4. Nếu cần logged batch, kiểm tra có thể **co-locate dữ liệu cần xử lý trong một Cassandra partition** hay không.
5. Áp giới hạn batch size/byte trước khi tạo statement.
6. Đo cluster p95/p99, replica distribution, coordinator load và retries.
7. **Không đơn thuần tăng `batch_size_warn_threshold`** để tắt cảnh báo.

### 18.2. Cảnh báo nguồn/nghiệp vụ

Log nên có event IDs, batchId, logical operation, outcome, CL, elapsed time và loại exception. Đừng log payload JSON chứa PII/tokens/credentials hoặc raw CQL với secret values. Với metrics, `batchId`/`eventId` có cardinality rất cao; phù hợp logs/traces hơn là metric labels.

## 19. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Hướng khắc phục |
|---|---|---|
| CQL báo `syntax error near LOGGED` | Viết `BEGIN LOGGED BATCH` | Dùng `BEGIN BATCH` (logged mặc định) |
| `SELECT` trong BATCH bị từ chối | BATCH chỉ nhận mutation | Tách SELECT riêng |
| Counter batch lỗi khi chứa INSERT thường | Trộn counter và regular mutation | Dùng `BEGIN COUNTER BATCH` chỉ cho counter |
| BATCH nhiều partition rất chậm | Batchlog/coordinator phải xử lý nhiều mutations | Chia nhỏ, dùng independent async writes nếu độc lập |
| Cassandra log `Batch too large` | Tổng serialized bytes vượt ngưỡng | Chia batch, kiểm soát bytes/mutations |
| Warning unlogged across partitions | UNLOGGED batch chứa nhiều partition keys | Nhóm theo partition hoặc bỏ batching |
| Read bảng A thấy row nhưng bảng B chưa có | Cross-partition partial visibility | Không giả định snapshot isolation; reconcile |
| `WriteTimeoutException` nhưng một số rows đã tồn tại | Timeout sau một phần/hoàn tất write | Retry idempotent/đối soát |
| Retry batch tạo row mới | Consumer sinh eventId/partition key mới | Giữ business IDs và deterministic key |
| Counter tăng quá dự kiến | Retry counter batch | Tránh retry mù; thiết kế aggregate có dedup |
| Batch hai UPDATE không có thứ tự mong muốn | Cùng timestamp hoặc concurrent writes | Dùng aggregate version/LWT/khác row keys |
| `List<entity>` bị lỗi mapping | Entity không có `@Table`/primary key đúng | Sửa annotation/transformer |
| `List<String JSON>` vào Type.INSERT bị lỗi | Handler mong entity, không tự parse JSON | JSON-to-entity transformer |
| `ingestQuery` lỗi bindings | `List<List<?>>` thiếu values hoặc sai thứ tự/codec | Validate số `?`, row width, types |
| `SimpleStatement` named parameters lỗi trong BatchStatement | Driver 4.x không hỗ trợ dạng này trong batch | Dùng prepared+bound hoặc positional simple |
| `BatchStatement.setTimeout(...)` không có tác dụng | Bỏ kết quả của immutable setter | Gán lại batch hoặc builder |
| `ReactiveCassandraBatchOperations` báo executed twice | Reuse cùng instance sau subscription | Tạo batchOps mới cho mỗi invocation/retry |
| Reactive `execute()` không ghi | Publisher không được subscribe | Trả Mono cho framework/consumer phù hợp |
| JMS commit rồi batch Cassandra lỗi | Handler/Channel async, ACK quá sớm | Durable handoff hoặc chờ completion |
| Cassandra hoàn tất nhưng JMS vẫn redeliver | Broker commit không atomic với DB | Idempotency/consistent event IDs |
| Một poison event chặn 9 events tốt | Gom nhiều events độc lập thành batch | Validate/split/quarantine trước khi ghi |
| Batchlog replays tăng | Coordinator/node instability/overload | Kiểm tra failure, latency, batch size |
| Read-after-write tại DC khác chậm | LOCAL_QUORUM chỉ trong local DC | Đánh giá consistency/replication SLA |
| CQL batch gây OOM/GC | Coordinator chịu batch quá lớn | Giảm batch bytes/concurrency, review data model |

### 19.1. Tự hỏi trước khi retry

**Có thể retry một request chứa ba mutations, nhưng chỉ khi cả ba có semantics phù hợp.** Nếu một mutation là counter increment, toàn bộ batch **không idempotent**. Nếu một mutation tạo ID mới mỗi lần, replay tạo business row mới. Nếu cả ba là immutable INSERT theo khóa ổn định, retry có thể phù hợp, nhưng vẫn cần cân nhắc timestamp, TTL, conflicting duplicates và source acknowledgment.

## 20. Bài thực hành: từ CQL BATCH đến Spring Integration

**Môi trường:** Java 17+, Spring Integration 6+/7+ và Spring Data Cassandra reactive tương thích, Cassandra test cluster, `cqlsh`. Có thể dùng Testcontainers cho các bài API, nhưng bài test coordinator failure/batchlog recovery và quorum nên có **cluster nhiều node thật hoặc môi trường test được quản lý**. Không gây lỗi mạng, kill node hoặc nâng batch thresholds trên production.

### Bài A — CQL logged batch cùng một partition

1. Tạo bảng `shop_integration.order_events` ở mục 3.
2. Gửi hai rows có `order_id='ORD-101'` bằng `BEGIN BATCH ... APPLY BATCH`.
3. Query lại:

~~~sql
SELECT order_id, event_id, event_type
FROM shop_integration.order_events
WHERE order_id = 'ORD-101';
~~~

4. Đối chiếu full primary key và xác định hai rows thuộc **một partition**.
5. Chạy lại **cùng CQL**, kiểm tra semantics upsert: không có một row mới với event_id khác.
6. Gửi một row cùng `event_id` nhưng `payload_json` khác, nhận diện nguy cơ **conflicting duplicate**.
7. Ghi lại p95 latency và cluster metrics cho batch nhỏ.

**PASS:** Hiểu `BEGIN BATCH` là LOGGED mặc định; biết single-partition batch có thể được tối ưu không cần batchlog và không coi retry có dữ liệu khác là idempotent.

### Bài B — Multi-partition logged batch và partial visibility

1. Chuẩn bị hai partition keys `ORD-101` và `ORD-102`.
2. Gửi `BEGIN BATCH` chứa một INSERT cho mỗi order.
3. Xác nhận khi **CQL batch hoàn tất thành công**, các row đã được ghi theo consistency/timeout của request.
4. Trong môi trường failure-injection test, mô phỏng một node/coordinator chậm hoặc crash ở giữa việc triển khai mutation; quan sát batchlog replay/timeout logs.
5. Cho một reader đọc cả hai partitions trong lúc writes/recovery; ghi nhận **khả năng partial visibility**. Lưu ý không phải mọi lần thử sẽ bắt được trạng thái này.
6. Chờ recovery/reconciliation rồi query lại theo key. Không mặc định một `WriteTimeoutException` chứng minh cả hai rows chưa được ghi.
7. Vẽ timeline event/ACK có timestamp và giải thích nơi lost response có thể xảy ra.

**PASS:** Giải thích được eventual completion vs snapshot isolation và không báo cáo “đã chứng minh atomic SQL transaction” chỉ từ kết quả test.

### Bài C — UNLOGGED và COUNTER BATCH

1. Dùng **test data** tạo một `BEGIN UNLOGGED BATCH` cho `ORD-101`/`ORD-102`.
2. Mô phỏng coordinator failure (nếu có multi-node chaos environment); lý giải vì sao batch có thể chỉ áp dụng một phần, khác cơ chế batchlog.
3. Chạy `BEGIN COUNTER BATCH` trên bảng counter test của mục 8.
4. Thực hiện một counter increment rồi thử gửi lại với cùng business event; quan sát nguy cơ tăng lặp.
5. Giải thích vì sao không trộn counter update vào regular BATCH.
6. Đề xuất cách tính aggregate từ event log có dedup/replay để khôi phục counter khi cần.

**PASS:** Phân biệt LOGGED, UNLOGGED, COUNTER cả về semantics và retry.

### Bài D — Driver BatchStatement và prepared binding

1. Tạo `CqlSession` singleton được Spring quản lý, chuẩn bị `insertEvent` một lần.
2. Gọi `writeTwoEventsSameOrder(...)` trong `OrderEventBatchDao`.
3. Dùng `BatchStatement.builder(DefaultBatchType.LOGGED)` với hai `BoundStatement`.
4. Chuyển sang `DefaultBatchType.UNLOGGED` với cùng partition **chỉ để hiểu API**, không coi đây là một phép benchmark đầy đủ.
5. Cấu hình `setConsistencyLevel`, `setTimeout` và kiểm tra immutable setter.
6. Cố ý dùng một simple statement có named CQL markers trong batch (test âm tính) rồi sửa bằng **prepared+bound**.
7. Gửi 10 requests đồng thời, xác nhận **mỗi request có BatchStatement riêng**, còn `PreparedStatement` có thể reuse.

**PASS:** Không nối dữ liệu người dùng thành CQL string, không dùng mutable builder global, không hiểu 65.536 là kích thước nên sử dụng.

### Bài E — ReactiveCassandraBatchOperations

1. Tạo `OrderEventEntity`/`OrderEventKey` và `ReactiveCassandraOperations`.
2. Chạy `batchOps().insert(events).execute()` cho hai rows cùng order.
3. Dùng Reactor `StepVerifier` hoặc framework subscriber để consume `Mono<WriteResult>`; query lại DB.
4. Tạo một instance batch operations, execute/subscribe một lần; thử sử dụng lại instance để quan sát `IllegalStateException` khi version áp dụng rule single-use.
5. Sửa bằng **tạo instance mới** trong mỗi call/`Mono.defer(...)`.
6. Thử `batchOps(DefaultBatchType.UNLOGGED)` trên test, hiểu vì sao phải chọn loại có chủ đích.
7. Với Spring Data version hỗ trợ, dùng `withQueryOptions(...)` để đặt CL/timeout và đo elapsed time.

**PASS:** Biết batch operations mặc định LOGGED, chỉ execute một lần, và `Mono` phải được subscribe mới thực thi I/O.

### Bài F — Spring Integration List<entity> và ingestQuery

1. Tạo `batchOrderEventsFlow` với `Cassandra.outboundChannelAdapter(operations, Type.INSERT)`.
2. Gửi `Message<List<OrderEventEntity>>` gồm hai events cùng order qua channel.
3. Query Cassandra, xác minh hai rows có cùng partition key và event IDs đúng.
4. Gửi hai events thuộc **hai orders khác nhau** để kiểm chứng ứng dụng phải phân loại multi-partition batch trước khi gửi.
5. Tạo flow `ingestOrderEventsFlow` và gửi payload **`List<List<Object>>`** với đúng số CQL markers.
6. Gửi một inner list thiếu value hoặc sai Java type, xác nhận lỗi được đưa tới đường error/validation đã thiết kế.
7. Chuyển sang `statementFunction(...)` với `BatchStatement` tường minh; so sánh khả năng chọn batch type.

**PASS:** Phân biệt list entity với ma trận values, không để raw JSON `String` đi thẳng vào entity mode và hiểu adapter một chiều không reply.

### Bài G — So sánh throughput có kiểm soát

Trong test cluster, tạo ba workloads có tổng số events và payload bytes giống nhau:

| Workload | Biến thể |
|---|---|
| W1 | Mỗi event một Cassandra INSERT độc lập với giới hạn concurrency |
| W2 | Các events cùng order được gom thành single-partition batches nhỏ |
| W3 | Events khác orders được gom thành multi-partition LOGGED batches |

Tiến hành:

1. Warm-up driver prepared statement cache và cluster.
2. Chạy mỗi workload với concurrency/payload size được kiểm soát.
3. Đo throughput, p50/p95/p99 latency, max in-flight requests, coordinator CPU và errors.
4. Đọc Cassandra batch-size warnings, batchlog replay metrics và node load distribution.
5. So sánh kết quả, **không giả định W3 nhanh nhất vì chỉ gửi một request từ client**.
6. Thay số rows/batch theo lô nhỏ, ghi nhận khi latency tăng hoặc cluster cảnh báo.

**PASS:** Lựa chọn batching dựa trên dữ liệu benchmark/partition distribution, không dựa trên khái niệm SQL transaction.

### Bài H — JMS source acknowledgment và crash recovery

1. Cấu hình JMS message-driven inbound adapter có transaction/redelivery policy test.
2. Gửi message chứa một `BatchPayload` với `batchId=batch-001` và hai `eventId` ổn định.
3. Cho Cassandra handler sync và `DirectChannel`, kiểm tra lỗi propagated tới listener có thể kích hoạt rollback/redelivery.
4. Cho Cassandra hoàn tất rồi mô phỏng JVM crash trước khi JMS commit; broker có thể giao lại `batch-001`.
5. Xác nhận **cùng full Cassandra primary keys**, không tạo duplicates với event IDs mới.
6. Chuyển sang `ExecutorChannel` hoặc handler async; chứng minh source callback **có thể return trước DB completion**.
7. Thêm durable handoff/đường recovery hoặc điều chỉnh acknowledgment policy cho đúng SLA.
8. Đưa một event invalid vào batch và kiểm tra phương án fail cả batch hay split/quarantine từng event.

**PASS:** Không nói “JMS transacted + logged batch = exactly-once”; mô tả được hai cửa sổ lỗi và cách replay idempotent.

### Bài I — LWT và business invariants

1. Tạo bảng `order_current_state` với `orderId` là partition key và `version` là regular column.
2. Chạy một conditional `UPDATE ... IF version = ?` trong phạm vi Cassandra hỗ trợ.
3. Kiểm tra `[applied]` và phân biệt false với exception/timeout.
4. Thử đặt hai mutations cùng partition trong conditional batch **theo cú pháp được version Cassandra hỗ trợ**.
5. Thử dựng conditional batch **khác partitions** trong test âm tính, ghi nhận restrictions của Cassandra.
6. So sánh chi phí/latency LWT với regular BATCH.
7. Giải thích tại sao LWT không tạo transaction với JMS/Kafka.

**PASS:** Không nhầm logged batch với serializable compare-and-set, biết khi nào cần business version guard.

### Ma trận kiểm thử cuối bài

| Kiểm tra | Kết quả PASS |
|---|---|
| CQL | `BEGIN BATCH`, `BEGIN UNLOGGED BATCH` và `BEGIN COUNTER BATCH` dùng đúng cú pháp |
| Single-partition | Partition key giống nhau, biết isolation scope |
| Multi-partition | Hiểu batchlog/eventual completion và partial visibility |
| UNLOGGED | Không nhầm với recovery-guaranteed logged batch |
| COUNTER | Không tự retry non-idempotent mutations |
| Timestamp | Không suy thứ tự câu trong batch là thứ tự giá trị cuối |
| Driver | BatchStatement/DefaultBatchType + positional/prepared binding đúng |
| Immutable builder | BatchStatement không bị sửa khi bỏ setter result |
| Spring Data | batchOps một lần, Mono được subscribe, type chọn có chủ đích |
| Spring Integration | `List<entity>` khác `List<List<?>>`, statementFunction trả BatchStatement |
| Validation | Giới hạn bytes, row count và distinct partitions |
| Error | Phân loại timeout/unavailable/permanent error |
| Retry | Giữ eventIds/partition keys, không lặp side effects |
| Broker ACK | Không commit trước completion nếu business yêu cầu |
| Recovery | Có durable replay/quarantine/đối soát |
| Benchmark | Đo p95/p99, retries, batchlog, load per coordinator |

**Điều chưa thể chứng minh với unit mock:** batchlog replay, coordinator failover, partial visibility, Cassandra consistency/timeout, performance under load và JMS/Kafka commit boundaries. Dùng Cassandra multi-node test cluster, network failure injection và broker test thật khi cần kiểm chứng các hành vi này.

## 21. Câu hỏi tự đánh giá

1. CQL `BEGIN BATCH` mặc định dùng LOGGED hay UNLOGGED?
2. Vì sao `BEGIN LOGGED BATCH` không phải cú pháp chuẩn cần sử dụng?
3. `BEGIN UNLOGGED BATCH` khác LOGGED ở cơ chế phục hồi như thế nào?
4. `BEGIN COUNTER BATCH` dùng cho loại cột/mutation gì?
5. Vì sao không được trộn counter updates và regular writes trong cùng batch?
6. Một Cassandra batch có thể chứa SELECT và CREATE TABLE không?
7. Vì sao single-partition batch có thể được Cassandra tối ưu bỏ batchlog?
8. LOGGED batch nhiều partition có bảo đảm readers không thấy partial state không?
9. Batchlog là gì? Nó có phải JMS queue hay một durable application event log không?
10. Khi coordinator mất mạng sau khi ghi batchlog, tại sao các mutations vẫn có thể được replay?
11. Một `WriteTimeoutException` chứng minh chắc chắn rằng chưa có row nào được ghi không?
12. Vì sao logged batch không tương đương distributed SQL transaction với isolation/snapshot?
13. Hai updates tới cùng row trong một batch có thứ tự tương ứng với thứ tự câu CQL không?
14. Cassandra write timestamp khác business event timestamp và aggregate version thế nào?
15. `USING TIMESTAMP` của CQL nhận đơn vị microsecond hay millisecond?
16. Vì sao UNLOGGED batch nhiều partitions là một anti-pattern throughput phổ biến?
17. Với 1000 independent events, nên cân nhắc independent async writes hay một LOGGED batch 1000 rows?
18. Những metrics nào giúp đo batch lớn theo serialized bytes và partition-key count?
19. `batch_size_warn_threshold` và `batch_size_fail_threshold` giải quyết vấn đề gì?
20. Vì sao không nên chỉ nâng ngưỡng warn/fail để làm biến mất Cassandra warning?
21. `DefaultBatchType.LOGGED`, `UNLOGGED`, `COUNTER` được dùng trong Java Driver API nào?
22. `SimpleStatement` với named parameters có được Java Driver 4.x hỗ trợ trực tiếp trong `BatchStatement` không?
23. Vì sao `PreparedStatement.bind(...)` thuận tiện khi nhiều lần gửi batch?
24. `BatchStatement` trong driver 4.x có mutable setters không?
25. Giới hạn 65.536 statements ở driver có phải batch size production khuyến nghị không?
26. `ReactiveCassandraOperations.batchOps()` mặc định dùng batch type nào?
27. `ReactiveCassandraBatchOperations` được execute bao nhiêu lần cho mỗi instance?
28. Tại sao `Mono.defer(...)` hữu ích khi retry một reactive batch?
29. Khi nào cần dùng `withQueryOptions(...)` thay vì đổi global driver config?
30. Trong Spring Integration, payload `List<entity>` được xử lý khác `List<List<?>>` thế nào?
31. `ingestQuery` quyết định contract payload ra sao?
32. Khi nào nên dùng `statementFunction(...)` trả driver `BatchStatement`?
33. Vì sao `MessageChannel.send(true)` không đủ để kết luận Cassandra async batch đã ghi?
34. Cassandra logged batch có commit JMS session hoặc Kafka offset cùng lúc không?
35. Khi DB đã ghi nhưng JVM crash trước JMS commit, cần giữ những định danh nào khi redelivery?
36. Tại sao dùng counter increment trong batch làm retry trở nên nguy hiểm?
37. Batch có một poison event nhưng chín valid events nên fail toàn batch hay split? Quyết định dựa trên gì?
38. Tại sao phải so khớp **toàn bộ composite partition key** khi gom message theo Spring Aggregator?
39. Một conditional LWT batch giải quyết được điều gì mà regular logged batch không giải quyết?
40. Liệt kê ít nhất năm metric/log hữu ích để điều tra large batch và batchlog replay.

## 22. Tài liệu tham khảo chính thức

- [Apache Cassandra — CQL Data Manipulation: BATCH](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): cú pháp `BEGIN BATCH`/`UNLOGGED`/`COUNTER`, cùng timestamp, single-partition isolation và batchlog semantics.
- [Apache Cassandra — CQL v3 Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/cql_singlefile.html): câu lệnh BATCH, các restriction và ví dụ.
- [Apache Cassandra — Cassandra Configuration Reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): batch size warning/failure thresholds và cấu hình vận hành.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/): partitioning, coordinator, replicas và consistency.
- [Apache Cassandra Java Driver 4.19 — Batch](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/batch/): `BatchStatement.newInstance`, `builder`, `DefaultBatchType`, immutability và giới hạn statements.
- [Apache Cassandra Java Driver 4.19 — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): positional/named binding, immutable `BoundStatement` và prepared cache.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): hướng dẫn đánh dấu idempotent cho retries và speculative executions.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): `batchOps()` và `batchOps(BatchType)`.
- [Spring Data Cassandra API — ReactiveCassandraBatchOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraBatchOperations.html): `insert`, `update`, `delete`, `withQueryOptions`, `execute()` và instance single-use.
- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@Table` và CQL mapping.
- [Spring Data Cassandra — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): publisher subscription và reactive execution.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, batch từ `List<entity>`, `ingestQuery` với `List<List<?>>`, `statementFunction` và async default.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation/release strategy, message grouping và group stores.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`/`errorChannel`, phân biệt messaging errors với broker transactions.

**Ghi nhớ:** **LOGGED BATCH** của Cassandra bảo vệ việc **hoàn tất mutations** qua batchlog theo cơ chế recovery, nhưng **không cung cấp SQL-style transaction isolation xuyên nhiều partitions**. **Single-partition batch nhỏ** là trường hợp tự nhiên; **UNLOGGED nhiều partition** có nguy cơ partial application, còn **COUNTER batch không idempotent** để retry mù quáng. Với các writes độc lập, thường nên **gửi song song có giới hạn** thay vì một multi-partition batch lớn. Trong Spring Integration Cassandra, phân biệt **`List<entity>`**, **`ingestQuery` nhận `List<List<?>>`** và **`statementFunction` nhận `BatchStatement`**; tất cả đều cần validation, monitoring, idempotent replay và acknowledgment boundary rõ ràng với JMS/Kafka.







