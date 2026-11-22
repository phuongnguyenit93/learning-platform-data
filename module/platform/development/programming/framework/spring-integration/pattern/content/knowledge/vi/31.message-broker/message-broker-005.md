# Partition hoặc consumer group

## 1. Bài toán: muốn tăng tốc xử lý message nhưng vẫn đúng thứ tự

Một hệ thống bán hàng phát các sự kiện:

~~~text
OrderCreated(orderId=O-501)
PaymentAuthorized(orderId=O-501)
OrderCancelled(orderId=O-501)
~~~

Consumer cần cập nhật trạng thái từng đơn theo một thứ tự hợp lệ. Khi lượng sự kiện tăng, đội vận hành muốn bổ sung worker. Nếu thêm nhiều consumers không có chiến lược chia việc, có thể xảy ra:

- Hai worker cập nhật **cùng đơn hàng** đồng thời, làm ghi đè trạng thái mới bằng trạng thái cũ.
- Thêm consumer nhưng **throughput không tăng** vì topic chỉ có một partition.
- Tạo một consumer group mới với ý định “chia tải” nhưng thực tế khiến **mọi sự kiện được xử lý thêm lần nữa**.
- Scale partition count rồi ngạc nhiên vì key của đơn hàng đi sang partition khác, một phần ordering trước/sau thời điểm đổi không còn đơn giản.
- Broker redeliver sau crash và handler tạo **side effect trùng**, dù offset đã từng được đọc.

Hai khái niệm thường bị nhầm là **partition** và **consumer group**.

**Partition** là cách broker (đặc biệt Kafka) chia log của một topic thành nhiều luồng lưu trữ có thứ tự **cục bộ**. **Consumer group** là cách các consumer phối hợp chia các partition để **cùng xử lý một subscription logic**. Đây là **hai trục thiết kế bổ sung cho nhau**, không phải chọn *partition hoặc consumer group* như hai tính năng loại trừ.

~~~mermaid
flowchart LR
    PUB["Order event producer"] --> TOPIC["Topic orders.events"]
    TOPIC --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    TOPIC --> P2["Partition 2"]
    P0 --> A1["Group inventory / Consumer A"]
    P1 --> A2["Group inventory / Consumer B"]
    P2 --> A3["Group inventory / Consumer C"]
~~~

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học Enterprise Integration Patterns bằng **Spring Integration** để tạo message flow ít phụ thuộc, có thể mở rộng: **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, kết hợp kiểm thử/quan sát các nhánh xử lý. Bài này thuộc chương **Message broker** và tập trung vào cách **partition, group, concurrency và delivery semantics** ảnh hưởng tới một IntegrationFlow ở ranh giới broker.

**Sau bài học**, bạn sẽ biết phân biệt hai khái niệm, tính mức concurrency khả dụng, chọn message key, bảo toàn ordering theo thực thể, thiết kế idempotency/retry/DLQ khi rebalance, cấu hình consumer ở Spring Integration và viết các bài test xác nhận scale không làm sai nghiệp vụ.

## 2. Định nghĩa đúng: partition, consumer và consumer group

**Topic** là luồng bản ghi/sự kiện logic. Trong Kafka, topic thường có nhiều **partitions**:

~~~text
orders.events
  ├── partition 0: offset 0, 1, 2, 3, ...
  ├── partition 1: offset 0, 1, 2, 3, ...
  └── partition 2: offset 0, 1, 2, 3, ...
~~~

Mỗi partition là một chuỗi bản ghi có offset tăng dần. Không tồn tại một **offset toàn cục của toàn topic** dùng để suy ra thứ tự tất cả các partitions.

**Consumer** là một tiến trình/client đọc bản ghi. **Consumer group** trong Kafka là tập consumer dùng cùng một `group.id` nhằm chia trách nhiệm xử lý các partitions của một topic. Trong **cùng một group** ở mô hình subscription thông thường, một partition tại một thời điểm được gán cho tối đa **một consumer đang hoạt động của group đó**. Các consumers thuộc **group khác nhau** đọc độc lập.

Ví dụ:

~~~text
Topic có 6 partitions.
Group inventory có 3 consumers: mỗi consumer có thể nhận ~2 partitions.
Group analytics có 2 consumers: mỗi consumer có thể nhận ~3 partitions.

Inventory và Analytics đều được nhận các records theo subscription riêng.
~~~

Phép chia ở trên là **minh họa phân phối cân bằng**; assignment thực tế phụ thuộc assignor, membership, subscriptions và tình trạng rebalance. Không giả định mọi nhóm luôn có số partition chia đều tuyệt đối.

## 3. Vì sao đây không phải câu hỏi “partition hay consumer group”?

| Khái niệm | Trả lời câu hỏi | Tác dụng chính |
|---|---|---|
| **Partition** | Dữ liệu được chia thành những log nào? | Phân phối dữ liệu, giới hạn ordering scope, đặt trần parallelism theo partition |
| **Consumer group** | Ai cùng chia việc đọc một subscription? | Load balancing, failover, committed offsets theo group |
| **Consumer instance** | Worker nào đang poll/xử lý? | Thực thi công việc |
| **Message key** | Record được gán partition bằng tiêu chí gì? | Affinity của sự kiện liên quan |
| **Offset** | Record ở vị trí nào trong một partition? | Theo dõi vị trí đọc, retry/replay |
| **Rebalance** | Partition ownership đổi ra sao? | Membership/failover/scale |

Muốn xử lý theo từng đơn và tăng concurrency, thường cần **cả hai**:

1. Producer chọn **partition key** nhất quán, ví dụ `tenantId + orderId`.
2. Topic có số partitions phù hợp nhu cầu throughput.
3. Các workers thuộc **cùng group** để chia partitions.
4. Business handler có **idempotency, transaction và ordering checks** cho retry/rebalance.

**Partition không tự là consumer group; consumer group không tự sinh thêm partitions.**

## 4. Một minh họa bằng 6 partitions

~~~mermaid
flowchart TB
    subgraph T["orders.events — 6 partitions"]
      P0["P0"]
      P1["P1"]
      P2["P2"]
      P3["P3"]
      P4["P4"]
      P5["P5"]
    end
    subgraph G["group.id=inventory — 3 consumers"]
      C1["consumer-1"]
      C2["consumer-2"]
      C3["consumer-3"]
    end
    P0 --> C1
    P1 --> C1
    P2 --> C2
    P3 --> C2
    P4 --> C3
    P5 --> C3
~~~

Với consumer subscription thông thường:

- **3 consumers, 6 partitions:** có thể có 3 consumers cùng làm việc.
- **6 consumers, 6 partitions:** tối đa 6 consumers có partition được gán cho topic này.
- **9 consumers, 6 partitions:** ít nhất 3 consumers sẽ không được gán partition **của topic đó** (có thể làm việc với topics khác nếu subscriptions khác).
- **1 consumer, 6 partitions:** một consumer có thể poll/process 6 partitions; **không tương đương 6 parallel execution threads**.

Một group có thể subscribe **nhiều topics**; con số tối đa active consumers cần xét **tập partitions được assign**, không chỉ một topic đơn lẻ. Và throughput thực tế còn phụ thuộc CPU, I/O, poll loop, downstream pool, key skew và broker quotas.

## 5. Công thức sizing cơ bản và giới hạn của nó

Với một topic có `P` partitions, một group có `C` consumer instances tương thích, mức parallelism theo ownership tối đa trong một thời điểm (giả sử tất cả consume cùng topic) là:

\[
\text{active consumers} \le \min(P,C)
\]

Không có nghĩa throughput bằng `min(P,C) × speed(worker)` trong mọi hệ thống. Nếu một partition chứa phần lớn records, worker sở hữu nó có thể quá tải trong khi các workers còn lại nhàn rỗi.

Giả sử:

~~~text
6 partitions.
Group có 3 consumers.
Các partitions có tải tương đương.
Mỗi consumer có thể xử lý bền vững ~250 events/giây.

Throughput lý thuyết tại consumer tier ≈ 3 × 250 = 750 events/giây.
~~~

Đây là **ước lượng minh họa**, không phải phép đo hoặc guarantee. Nếu downstream DB chỉ chịu 400 writes/giây, tăng consumers không vượt được bottleneck đó. Nếu producer tạo 1.200 events/giây, backlog/lag sẽ tăng.

**Số partitions quyết định một trần concurrency quan trọng; không tự quyết định throughput end-to-end.**

## 6. Ordering thực sự được bảo đảm ở đâu?

Kafka duy trì thứ tự records **trong mỗi partition** theo offset. Chẳng hạn:

~~~text
Partition 2:
  offset 71: OrderCreated(O-501)
  offset 72: PaymentAuthorized(O-501)
  offset 73: OrderCancelled(O-501)
~~~

Consumer poll records theo thứ tự partition, nhưng **việc hoàn tất side effects theo đúng thứ tự còn phụ thuộc ứng dụng**. Nếu sau khi đọc, bạn đẩy từng record sang executor pool không có ordering constraint, `offset 73` có thể commit business effect trước `offset 72`.

Không có **global ordering** giữa:

~~~text
Partition 0: event A
Partition 1: event B
~~~

Ngay cả với timestamp, hai producers độc lập, clock skew hoặc network retries vẫn có thể làm **event time** khác **append order**. Nếu domain cần thứ tự nghiệp vụ, bổ sung entity version/sequence và xử lý stale/out-of-order events.

**Ordering của broker là một điều kiện hữu ích, không phải bằng chứng end-to-end business ordering đúng.**

## 7. Message key: gắn các sự kiện cùng thực thể vào cùng partition

Một chiến lược:

~~~text
key = tenantId + "|" + orderId
value = OrderEvent
~~~

Khi producer sử dụng **cùng partitioner, cùng topic configuration và số partition không đổi**, records có cùng key thường được gửi cùng partition. Nhờ vậy, các events của `O-501` nằm trong một ordering scope.

Ví dụ:

~~~text
key="tenant-a|O-501" → P2
  OrderCreated        (offset 71)
  PaymentAuthorized   (offset 72)
  OrderCancelled      (offset 73)

key="tenant-a|O-502" → P4
  OrderCreated        (offset 19)
  PaymentAuthorized   (offset 20)
~~~

**Chú ý:** producer phải bảo đảm publish order đối với các events cùng key; nếu nhiều producers cùng gửi events cho một aggregate mà không có sequence/outbox coordination, cùng partition không tự sửa được **logical creation order** đã sai.

Không dùng `MessageHeaders.ID`, random UUID mỗi attempt hoặc timestamp làm partition key nếu muốn các events của **một order** có affinity. Nếu payload có PII, nên cân nhắc hash/canonical key phù hợp, không sao chép email hay token thẳng vào key khi không cần.

## 8. Chọn key nào cho nghiệp vụ?

| Mục tiêu | Key có thể phù hợp | Lưu ý |
|---|---|---|
| Ordering theo đơn hàng | `tenant + orderId` | Cần scope khi order ID có thể trùng |
| Ordering theo tài khoản | `accountId` sau xác thực | Một hot account có thể tạo hotspot |
| Ordering theo giỏ hàng | `tenant + cartId` | Cart merge/split có thể thay key |
| Independent telemetry | ID thiết bị hoặc partitioning cân bằng | Có thể không cần strict ordering |
| Workflow batch | `batchId` | Batch lớn có thể dồn một partition |
| Line-item xử lý độc lập | `orderId + lineId` | Không bảo đảm các line của cùng order có cùng partition |

Không có **một key tốt cho mọi consumer**. Nếu Inventory cần ordering theo SKU, còn Order Management cần ordering theo orderId, bạn có thể cần **topic/stream được repartition** có chủ đích. Không sửa key tùy tiện trên cùng topic nếu consumer đang dựa vào ordering theo orderId.

**Partition key là quyết định về business consistency và vận hành, không chỉ để load balance.**

## 9. Hot partition và key skew

Giả sử một merchant tạo 60% events. Nếu key là `merchantId`, một partition có thể nhận tải rất lớn:

~~~text
P0: ████████████████████ 60%
P1: ███ 10%
P2: ███ 10%
P3: ███ 10%
P4: ██  5%
P5: ██  5%
~~~

Tăng consumers trong cùng group không chia một **partition nóng** cho nhiều consumers cùng lúc theo cơ chế assignment thông thường.

Các lựa chọn:

- Chọn key có granularity đúng hơn, ví dụ `tenantId + orderId` thay vì chỉ tenant.
- Nếu một key cực nóng và nghiệp vụ cho phép, chia thành **shards** và thêm layer tái hợp/thứ tự có kiểm soát.
- Dùng topic khác hoặc flow chuyên cho high-volume tenants.
- Tối ưu I/O và handler của hot partition.
- Giới hạn producer/rate, tách workload nặng khỏi các consumers khác.

**Không random partition key để giải quyết hotspot nếu yêu cầu strict per-entity order không cho phép.** Có thể tăng throughput nhưng làm mất ordering mà ứng dụng đang dựa vào.

## 10. Tăng số partitions có phải luôn an toàn?

Giả sử topic từ 6 tăng lên 12 partitions. Với partitioner dựa trên hash(key) và số partitions, phép ánh xạ của **cùng key** có thể thay đổi:

~~~text
Trước: key O-501 → partition 2
Sau:   key O-501 → partition 8
~~~

Các events cũ của O-501 còn ở P2, các events mới ở P8; hai partitions có thể được xử lý song song. **Ordering theo key xuyên thời điểm đổi partition count không còn được bảo đảm chỉ bằng key hashing**.

Các mitigation tùy hệ thống:

1. Giữ partition count ổn định và **chọn dư địa tăng trưởng từ đầu**.
2. Dùng partition assignment tùy chỉnh/consistent mapping phù hợp, có contract và versioning.
3. Drain/cutover có kiểm soát, khoá write một khoảng và bảo đảm consumer đã xử lý hết tập cũ trước khi chuyển.
4. Topic mới version hóa với partition strategy mới, xử lý migration rõ ràng.
5. Thêm **aggregate version check/idempotency** để không áp dụng stale update dù events tới khác thứ tự.

Không dựa vào một công thức hash cụ thể cho mọi Kafka client/version. Điều quan trọng là **mapping có thể đổi khi partition set đổi**, nên phải kiểm thử migration.

## 11. Consumers cùng group và consumers khác group

~~~mermaid
flowchart TD
    T["orders.events / P0 P1 P2"] --> I["Group inventory"]
    T --> A["Group analytics"]
    I --> I1["Inventory worker 1"]
    I --> I2["Inventory worker 2"]
    A --> A1["Analytics worker 1"]
    A --> A2["Analytics worker 2"]
~~~

**Trong cùng group:** members chia partitions. Nếu inventory service chạy ba replicas, cả ba dùng `group.id=inventory` để **cùng thực hiện một subscription logic**.

**Giữa hai groups:** mỗi group có cursor/offset state riêng; Inventory và Analytics có thể đều nhận **cùng một event**. Đây là mô hình pub/sub theo **logical consumer application**.

Một sai lầm:

~~~text
Replica inventory-1 → group.id=inventory-1
Replica inventory-2 → group.id=inventory-2
Replica inventory-3 → group.id=inventory-3
~~~

Thay vì chia tải, đó là **ba groups độc lập**, thường mỗi group đều xử lý tất cả messages đã subscribe theo offset/cursor của riêng nó. Nếu mỗi event tạo một reservation side effect, có nguy cơ **ba lần tạo reservation** nếu không có domain dedupe.

**Một microservice logic thường dùng một group ID ổn định xuyên replicas**, trừ khi thật sự muốn các subscriptions độc lập.

## 12. Bảng ví dụ: 6 partitions, nhiều cách chia consumer groups

| Topology | Có bao nhiêu logical subscriptions? | Active partition ownership tối đa mỗi group |
|---|---:|---:|
| 1 group × 1 consumer | 1 | 1 consumer giữ 6 partitions |
| 1 group × 3 consumers | 1 | Tối đa 3 consumers active |
| 1 group × 6 consumers | 1 | Tối đa 6 consumers active |
| 1 group × 9 consumers | 1 | Tối đa 6 consumers active trên topic |
| 2 groups × 3 consumers | 2 | Tối đa 3 active/group; mỗi group nhận stream riêng |
| 3 groups × 2 consumers | 3 | Tối đa 2 active/group; tổng xử lý có thể nhân ba |

“Active” ở bảng nghĩa là **có partition assignment cho topic minh họa**, không có nghĩa đang CPU bận từng giây. Consumer có partition nhưng topic không có message vẫn có thể idle.

**Tăng group count không tăng capacity của cùng một processing function** theo kiểu chia tải; đó là thêm independent subscribers.

## 13. Offset gắn với topic + partition + group

Kafka record position:

~~~text
topic = orders.events
partition = 2
offset = 71
~~~

Progress thường được theo dõi bởi **consumer group**:

~~~text
group.id = inventory
committed offset for partition 2 = 74
~~~

Trong Kafka, committed offset thường đại diện **vị trí tiếp theo cần đọc**. Nếu đã xử lý xong records 71, 72, 73 thì committed offset có thể là 74.

**Không dùng offset riêng lẻ làm business idempotency key** cho external side effect: offsets có scope theo partition/topic và có thể khác khi event được republish sang topic khác. Dùng stable business event ID hoặc operation ID theo contract, có thể kèm source position để audit.

**Offset commit không chứng minh database side effect và broker cursor đã được commit nguyên tử**. Crash giữa hai thao tác có thể gây replay hoặc mất xử lý nếu đặt thứ tự sai.

## 14. At-most-once, at-least-once và giới hạn của exactly-once

Hai thứ cần phân biệt là **message delivery/offset progress** và **side effect của business handler**.

~~~text
A. Commit offset trước khi xử lý business:
  poll message
  commit offset
  database write
  → process crash giữa commit và write: có thể mất xử lý.

B. Xử lý business rồi commit offset:
  poll message
  database commit
  commit offset
  → crash giữa DB commit và offset commit: có thể replay.
~~~

| Chính sách | Thuận lợi | Rủi ro |
|---|---|---|
| Commit trước khi xử lý | Có thể tránh replay theo cursor | Mất side effect khi crash |
| Commit sau khi xử lý | At-least-once processing dễ triển khai | Duplicate delivery sau crash |
| Kafka transaction trong một pipeline Kafka-to-Kafka | Có thể đạt exactly-once semantics **trong phạm vi giao dịch Kafka được cấu hình** | Không tự đưa DB/HTTP bên ngoài vào cùng transaction |
| Business inbox/idempotency trong DB | Một logical event không gây effect trùng | Cần unique key, fingerprint, lifecycle/recovery |

**Đừng quảng cáo “exactly-once” cho toàn bộ workflow chỉ vì Kafka producer idempotent hoặc consumer bật auto commit.** Kafka transactions có phạm vi bảo đảm cụ thể; một HTTP payment, JDBC database ngoài transaction hoặc email provider cần cơ chế riêng.

Nếu database side effect là mục tiêu, thường chọn **xử lý bền vững trước, commit offset sau**, cộng với **domain idempotency**.

## 15. Redelivery không nhất thiết là producer gửi message hai lần

Timeline:

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Group consumer
    participant DB as Business DB
    B->>C: partition 2 offset 71
    C->>DB: Process event EV-501
    DB-->>C: COMMIT business effect
    Note over C: Crash before committing offset 72
    B->>C: Redeliver offset 71 after recovery
    C->>DB: Check idempotency key EV-501
    DB-->>C: Already processed; no new effect
    C->>B: Commit next offset 72
~~~

Đây là **một bản ghi Kafka đọc lại** vì cursor chưa được commit, không nhất thiết có một producer duplicate.

Ở cấp application còn có thể có:

- Producer retry/publish lại cùng logical event.
- DLQ replay tạo bản ghi mới ở topic khác.
- Snapshot/backfill phát lại event cũ.
- Consumer group mới bắt đầu từ offset sớm.
- Một handler tự retry sau lỗi tạm thời.

Vì vậy idempotency nên dựa vào **business eventId/operationId** có scope, không chỉ `topic-partition-offset` hoặc local in-memory set.

## 16. Consumer group rebalance là gì?

Một group có partition ownership:

~~~text
Initial:
  P0 P1 → C1
  P2 P3 → C2
  P4 P5 → C3
~~~

Khi C2 chết hoặc rời group:

~~~text
After rebalance:
  P0 P1 P2 → C1
  P3 P4 P5 → C3
~~~

**Rebalance** là quá trình group điều chỉnh assignment khi membership, subscriptions hoặc metadata liên quan thay đổi. Trong thời gian chuyển giao, throughput có thể bị ảnh hưởng; các records chưa commit đúng có thể được consumer mới đọc lại.

Các tình huống kích hoạt/tác động:

- Deploy/restart hoặc autoscaling tăng/giảm replicas.
- Consumer không poll đúng hạn hoặc session bị coi là không sống.
- Một consumer giữ records quá lâu, vượt poll interval policy.
- Thay đổi số partitions.
- Thay đổi subscription topics hoặc group protocol/assignor.
- Lỗi mạng hoặc coordinator thay đổi.

**Đừng giả định rebalance luôn dừng toàn bộ consumers**: cơ chế eager/cooperative/incremental và các protocol/version khác nhau có tính chất khác nhau. Nhưng vẫn phải coi **partition ownership có thể chuyển** và thiết kế recovery đúng.

## 17. Vì sao rebalance có thể gây duplicate side effects?

Một kịch bản:

~~~text
Consumer C1 owns P2.
C1 polls offset 71 (order O-501).
C1 writes database COMMIT.
C1 chưa commit offset 72.
Group rebalance → P2 assigned to C2.
C2 starts at committed offset 71.
C2 processes O-501 again.
~~~

Không thể ngăn hoàn toàn tình huống này bằng cách tăng partitions hoặc cố giữ member sống. Cần:

1. **Idempotency** bền vững tại business boundary.
2. **Commit progress sau khi công việc đã đạt mốc bền vững**.
3. Kiểm tra partition revocation/reassignment trong long-running handlers.
4. Không cho worker cũ tiếp tục ghi vô hạn sau khi mất quyền xử lý nếu có thể ảnh hưởng dữ liệu theo khóa — dùng **fencing/leases/aggregate version** khi cần.
5. Khi external side effect outcome chưa rõ, reconcile thay vì thực thi lại với key mới.

Group membership giải quyết **phân phối trách nhiệm đọc**, không tự đảm bảo exactly-once cho business side effects.

## 18. Rebalance listener, cooperative assignment và static membership

Trong Kafka client, assignment strategy và group membership có thể được tối ưu để giảm chuyển giao không cần thiết. Những khái niệm cần biết:

- **Eager rebalance:** nhiều partition assignments có thể bị thu hồi và chia lại trong một đợt.
- **Cooperative/incremental rebalance:** giảm phạm vi thu hồi trong các cấu hình/protocol hỗ trợ.
- **Static membership:** dùng identity ổn định cho consumer instances để giảm ảnh hưởng khi restart ngắn hạn trong một số điều kiện.
- **Group protocol/version:** quyết định một số hành vi assign/rebalance mới; phải đối chiếu broker, client và Spring Kafka version triển khai.

**Không dựa hoàn toàn vào rebalance optimization để bảo đảm correctness.** Dù tối ưu tốt, vẫn có crash, network partition và duplicate replay. Cần tests cho mất consumer, restart và rebalance trong lúc handler đang commit.

Với task dài, cân nhắc poll/processing architecture tách biệt có giới hạn, pause/resume partitions hoặc lưu durable intent trước khi ACK thay vì block poll loop bất tận. Những lựa chọn này phải giữ đúng offset/recovery semantics.

## 19. `max.poll.interval.ms` và handler chậm

Một consumer có thể poll nhiều records nhưng xử lý lâu:

~~~text
poll 500 records
  → each calls external API
  → processing exceeds allowed poll interval
  → membership/assignment changes
  → record processing may replay
~~~

Các tham số như `max.poll.records`, `max.poll.interval.ms`, heartbeat/session timeout, poll timeout và concurrency tác động khác nhau. Không có bộ giá trị “chuẩn” cho mọi workload.

Hướng vận hành:

1. Đo **p95/p99 per-record processing time**.
2. Giới hạn số records mỗi poll khi xử lý đồng bộ tốn thời gian.
3. Chọn timeout theo worst-case có kiểm soát; không tăng vô hạn để che service chậm.
4. Nếu offload sang executor, có **bounded queue** và cơ chế tracking completion/offset chính xác.
5. Dùng pause/resume khi backlog nội bộ quá tải theo container capabilities.
6. Ưu tiên giảm remote latency/timeout hoặc tách workflow dài sang durable work queue.

**Đẩy poll records vào ExecutorChannel rồi commit offset ngay không tạo at-least-once processing**; nếu JVM crash trước khi worker hoàn thành, message có thể mất trách nhiệm recovery.

## 20. Thêm thread ở downstream có thể phá per-partition ordering

Một IntegrationFlow:

~~~text
Kafka consumer đọc P2:
  offset 71: create O-501
  offset 72: pay O-501
  offset 73: cancel O-501

DirectChannel → sequential handler
  thường cho ordering dễ kiểm soát hơn.

ExecutorChannel → 3 worker threads
  offset 73 có thể complete trước offset 72.
~~~

**Kafka ordering** là thứ tự log và fetch; **application processing order** phụ thuộc scheduler, transaction, retries và completion. Nếu strict per-order state machine:

- Giữ tuần tự theo partition/key tại nơi có side effect; hoặc
- Dùng keyed execution lane/serial executor per business key; hoặc
- Áp version/sequence guard và idempotent state transitions, reject stale writes.

Nếu handler xử lý records độc lập (ví dụ lưu metrics không phụ thuộc thứ tự), parallel downstream có thể phù hợp. Nhưng **không vô tình đưa stateful commands vào một executor pool chung mà không xác định ordering requirements**.

## 21. Fan-out trong Spring Integration không giống consumer group

Ba khái niệm dễ nhầm:

~~~text
Kafka topic + Group A:
  partitions được chia cho các consumers thuộc Group A.

Spring Integration PublishSubscribeChannel:
  một message có thể được phát tới nhiều subscribers trong một app context.

Spring Integration DirectChannel:
  có thể dispatch tới một subscriber tại một lần gửi theo dispatcher semantics.
~~~

**PublishSubscribeChannel** là một cơ chế fan-out trong IntegrationFlow; nó không tạo group offset riêng trong Kafka. **DirectChannel** không tạo partition ownership trong broker. Và consumer group Kafka không quyết định Router/Transformer nào được gọi sau khi message đã vào app.

Ví dụ:

~~~text
Group inventory nhận event EV-501 một lần theo logical subscription.
  → PublishSubscribeChannel tới Validator + Metrics + Business handler
~~~

Đây là **nhiều local subscribers xử lý cùng một event**, không phải nhiều Kafka groups. Nếu Metrics handler chậm hoặc lỗi, ảnh hưởng phụ thuộc loại channel/executor/error policy.

Không dùng `PublishSubscribeChannel` để giả lập competing consumers khi mục tiêu là chia việc (mỗi record chỉ một business worker). Và đừng tăng số replicas ứng dụng mà mỗi replica mang group ID riêng nếu không muốn fan-out độc lập.

## 22. RabbitMQ: competing consumers trên một queue

Trong RabbitMQ sử dụng queue phổ biến, một mô hình:

~~~mermaid
flowchart LR
    P["Publisher"] --> EX["Exchange"]
    EX --> Q["Queue inventory.commands"]
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
~~~

Một message trong queue được **giao cho một consumer** tại thời điểm delivery thông thường, và có thể **redeliver** cho consumer khác nếu chưa ACK và consumer/connection mất. Đây là mô hình **competing consumers**, gần với mục tiêu **chia tải** của group Kafka nhưng cơ chế lưu trữ/cursor khác.

Để hai ứng dụng nhận cùng một event:

~~~text
Exchange orders.events
  ├── queue inventory.events → inventory consumers
  └── queue analytics.events → analytics consumers
~~~

Mỗi queue nhận bản sao qua binding/routing và có ACK/backlog riêng. **Không gọi consumer group Kafka tương đương tuyệt đối với một RabbitMQ queue**: Kafka log partitions và group committed offsets khác queue delivery/ACK và retention semantics.

Với RabbitMQ, concurrency, prefetch, ACK/requeue, quorum/classic queues và dead-lettering có đặc tính riêng; không copy nguyên công thức Kafka `min(partitions, consumers)` cho một queue không có partition semantics tương ứng.

## 23. JMS queue, topic và shared subscriptions

Trong JMS-style messaging:

| Mô hình | Ý nghĩa khái quát |
|---|---|
| **JMS Queue** | Competing consumers nhận các messages của một queue theo provider semantics |
| **JMS Topic** | Pub/sub, các subscriptions có thể nhận bản sao messages |
| **Durable subscription** | Giữ subscription state theo provider/configuration |
| **Shared subscription** | Nhiều consumers cùng chia message delivery của một subscription nếu provider/JMS version hỗ trợ |

Một Kafka group, RabbitMQ queue và JMS shared subscription **giống nhau ở mục tiêu phối hợp nhiều workers**, nhưng **không đồng nhất** về partition ordering, offset/replay, retention, ACK, broker transactions hay failover.

Khi thiết kế Spring Integration cho nhiều brokers, hãy chuẩn hóa **business contract** và **recovery semantics**, không giả định các transport có API/protocol tương đương 1:1.

## 24. Broker có partitioned log và broker có queue khác nhau như thế nào?

| Câu hỏi | Kafka topic partitions | RabbitMQ queue thông thường | JMS queue (khái quát) |
|---|---|---|---|
| Chia dữ liệu | Partitions trong topic | Queue + routing/bindings | Destination queue |
| Chia load trong một logical subscriber | Consumers cùng group chia partitions | Competing consumers | Competing queue consumers |
| Cursor/ACK | Committed offsets theo group/partition | ACK, requeue/delivery state | Ack/transaction theo JMS provider |
| Đọc lại lịch sử | Có thể theo retention và offset reset/seek | Không mặc nhiên như một append-only log | Phụ thuộc provider, không mặc nhiên như Kafka |
| Ordering | Theo partition, cần end-to-end guarantees riêng | Có thể bị tác động bởi concurrency/redelivery | Provider/consumer behavior |
| Scale cap | Thường gắn số assigned partitions | Không theo số Kafka partitions | Không theo số Kafka partitions |
| Một event cho nhiều logical subscribers | Consumer groups độc lập | Multiple queues bound to exchange | Multiple topic subscriptions |

**Không chọn API/adapter chỉ vì tên giống nhau.** Đặt câu hỏi theo yêu cầu: cần replay? per-key ordering? độc lập subscriptions? low latency RPC? work queue? DLQ retention? remote commit recovery?

## 25. Khi nào chọn nhiều partitions, khi nào chọn nhiều groups?

Chọn **tăng partitions** khi mục tiêu là:

- Nhiều consumers trong **cùng processing application** cần xử lý độc lập hơn.
- Throughput hiện tại bị giới hạn do một partition/leader/consumer lane.
- Có cách partition key bảo đảm ordering theo business identity.
- Đã chấp nhận chi phí broker metadata, storage/replication và migration.

Chọn **thêm consumer group** khi mục tiêu là:

- Một application logic **mới** cần nhận cùng event stream, ví dụ Analytics bên cạnh Inventory.
- Có lifecycle/offset/replay policy độc lập.
- Không muốn một consumer làm mất events của application khác.

Chọn **tăng replicas trong cùng group** khi:

- Topic đã có đủ partitions để chia việc.
- Consumer CPU/I/O đang là bottleneck.
- Downstream capacity và retry/idempotency đã sẵn sàng.

**Không chọn thêm group để làm một service xử lý nhanh hơn nếu mục tiêu là mỗi event tạo đúng một business operation.** Như vậy sẽ nhân đôi logical consumption và có thể nhân đôi side effects.

## 26. Quyết định kiến trúc theo nhu cầu cụ thể

| Nhu cầu | Thiết kế đáng cân nhắc | Trade-off |
|---|---|---|
| Mỗi order được xử lý đúng thứ tự | Key theo tenant+orderId, một processing lane per key | Hot key có thể nghẽn |
| Tăng throughput với nhiều orders độc lập | Nhiều Kafka partitions và consumer replicas cùng group | Rebalance, cost, data skew |
| Inventory và Analytics đều nhận event | Hai Kafka consumer groups | Hai subscriptions, hai offset/backlog streams |
| Job queue với competing workers | RabbitMQ queue + nhiều consumers | ACK/requeue và per-key order cần thiết kế |
| Reprocess events tuần trước | Kafka group/seek hoặc replay workflow theo retention | Side effects cần dedupe |
| Một event fan-out trong cùng app | Spring Integration PublishSubscribeChannel | Không thay consumer group và durability |
| Một warehouse xử lý cả order | Key theo order | Có thể chặn các lines song song |
| Mỗi line xử lý độc lập | Key theo lineId + Aggregator rõ manifest | Không còn strict total order theo order |

Không có topology nào vừa bảo đảm **global ordering tuyệt đối**, **parallelism vô hạn**, **không duplicate** và **availability vô điều kiện**. Hãy xác định bất biến nghiệp vụ trước rồi tối ưu concurrency trong phạm vi chúng cho phép.

## 27. Kiến trúc Spring Integration với Kafka ở ingress

Một event stream:

~~~mermaid
flowchart LR
    PUB["Order event producer"] --> K["Kafka orders.events / 6 partitions"]
    K --> AD["Spring Integration Kafka inbound adapter"]
    AD --> CH["MessageChannel"]
    CH --> FIL["Filter/Validate"]
    FIL --> ROUTE["Router"]
    ROUTE --> HAND["Service Activator / business service"]
    HAND --> DB["DB + inbox/outbox"]
~~~

**Kafka inbound adapter** tiếp nhận records tại ranh giới broker rồi phát các Spring `Message<?>` vào flow. **Group ID và partition assignment** thuộc tầng Kafka consumer/container, không phải một thuộc tính do downstream Router tự tạo.

Một process gồm ba điểm trách nhiệm:

1. **Kafka consumer/container:** group membership, poll, assignment, offset commits và transport recovery.
2. **Spring Integration channels/endpoints:** validation, routing, transformation, business invocation và error flow.
3. **Business state:** transaction/idempotency/consistency của domain.

Nếu tầng 2 hoặc 3 xử lý sai, tăng số partitions không tự cứu correctness; nếu tầng 1 commit offset quá sớm, business handler đúng cũng có thể **mất việc khi crash**.

## 28. Cấu hình group ID và concurrency: hiểu trước khi tăng replicas

Ví dụ properties cho một consumer application:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=inventory-reservations
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
~~~

**Đây là ví dụ cấu hình cho Spring Boot/Spring Kafka**, không thay cho bean definitions của một Spring Integration Kafka adapter cụ thể. Cần định nghĩa deserializers, security, container ack/error handling và topic lifecycle trong project.

Các ý chính:

- `group-id=inventory-reservations` phải ổn định giữa các replicas cùng logical consumer.
- `enable-auto-commit=false` giúp container/ứng dụng có quyền thiết kế commit policy, **không tự bảo đảm** offset sẽ được commit sau DB transaction.
- `auto-offset-reset=earliest` chỉ áp dụng khi **không có committed offset hợp lệ** cho group/partition tương ứng hoặc trường hợp reset được thiết kế; nó **không làm một group hiện hữu tự đọc lại từ đầu** mỗi lần deploy.
- Đổi `group-id` có thể làm tạo **subscription state độc lập** và đọc lịch sử tùy offset policy, vì vậy phải coi như migration có tác động nghiệp vụ.

**Đừng chỉnh `group-id` để sửa lag tạm thời**. Một group mới không “kế thừa” business progress hay idempotency state của group cũ theo ý muốn.

## 29. Một mẫu Kafka message-driven adapter nối vào IntegrationFlow

Ví dụ minh họa lớp cấu hình Spring Kafka container với Spring Integration adapter:

~~~java
@Bean
ConcurrentMessageListenerContainer<String, OrderEvent>
orderEventContainer(ConsumerFactory<String, OrderEvent> factory) {
    ContainerProperties props =
        new ContainerProperties("orders.events");
    props.setGroupId("inventory-reservations");
    props.setAckMode(ContainerProperties.AckMode.RECORD);

    ConcurrentMessageListenerContainer<String, OrderEvent>
        container =
            new ConcurrentMessageListenerContainer<>(factory, props);
    container.setConcurrency(3);
    return container;
}

@Bean
IntegrationFlow inventoryOrderFlow(
        ConcurrentMessageListenerContainer<String, OrderEvent> container,
        OrderEventHandler handler) {
    KafkaMessageDrivenChannelAdapter<String, OrderEvent> inbound =
        new KafkaMessageDrivenChannelAdapter<>(
            container,
            KafkaMessageDrivenChannelAdapter.ListenerMode.record);

    return IntegrationFlow.from(inbound)
        .handle(
            OrderEvent.class,
            (event, headers) -> {
                handler.applyIdempotently(event);
                return null; // One-way consumer, không cần reply.
            })
        .get();
}
~~~

**Đây là bản dựng minh họa cho lựa chọn cấu trúc**, không phải mã copy/paste độc lập: `OrderEvent`/`OrderEventHandler` là types của ứng dụng; cần imports, bean `ConsumerFactory`/deserializer phù hợp, handler transaction, Kafka error handler và ack/retry policy. API container/adapter và listener mode cần đối chiếu **đúng phiên bản Spring Integration Kafka/Spring Kafka** trước khi chạy.

`concurrency=3` là **ba listener consumers nội bộ container** trên instance minh họa, **không đồng nghĩa thêm ba consumer groups**. Nếu triển khai 2 replicas, mỗi replica concurrency 3, group có thể có 6 consumer members cùng chia 6 partitions, tùy assignment thực tế.

**Lưu ý vòng đời:** container được Spring/adapter quản lý; tránh vô tình tạo hai independent listeners trên cùng topic/group mà không chủ đích. Đừng đăng ký thêm một `@KafkaListener` thứ hai cùng chức năng rồi không nhận ra có competing consumers.

## 30. Container concurrency khác executor concurrency trong flow

Hai cách scale:

~~~text
A. Container concurrency=3
   consumer C1 owns P0,P1
   consumer C2 owns P2,P3
   consumer C3 owns P4,P5
   each handles assigned records synchronously.

B. Container concurrency=1
   consumer C1 polls P0..P5
   sends all records to ExecutorChannel pool=8
   → worker completion order không mặc nhiên theo partition.
~~~

Ở cách A, số consumer members và partition assignments tăng. Ở cách B, **một Kafka consumer vẫn poll** và đặt công việc vào thread pool; nếu offset được commit khi chỉ enqueue thành công, sẽ có **loss window** khi process crash trước worker completion.

Nếu cần async workers, thiết kế thêm:

- Bounded backlog và backpressure.
- Durable work handoff hoặc per-partition completion tracking.
- Offset commit chỉ sau mốc đã xử lý/durable phù hợp.
- Ordering/fencing theo partition hoặc business key.
- Error handler của worker có trách nhiệm rõ.

**Không tăng executor threads để lách số partitions mà không xác định delivery và ordering guarantees.**

## 31. Map Kafka record metadata sang Spring message

Một inbound message có thể có:

~~~text
payload = OrderEvent(eventId=EV-501, orderId=O-501)
headers:
  kafka_receivedTopic = orders.events
  kafka_receivedPartitionId = 2
  kafka_offset = 71
  kafka_receivedMessageKey = tenant-a|O-501
  businessCorrelationId = tenant-a|O-501|revision-3
~~~

**Đây là cách biểu diễn metadata khái niệm**. Tên constants/header chính xác như `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, `KafkaHeaders.OFFSET` và received-key có thể khác giữa các version Spring Kafka; kiểm tra API của version thực tế thay vì hardcode chuỗi trong business service.

Đừng nhầm:

- **Kafka record key**: dùng cho partitioning và record identity ở transport.
- **Business event ID**: dùng cho dedupe domain.
- **Kafka partition/offset**: source position cho observability/replay.
- **Spring `MessageHeaders.ID`**: ID message object trong flow.
- **Business correlation**: nhóm logical workflow/Splitter/Aggregator.

Khi qua HTTP/broker khác, custom headers có thể không được map; nếu business IDs cần tồn tại qua transport/replay, đưa chúng vào **wire contract** hoặc durable mapping phù hợp.

## 32. Không tạo group ID theo instance, host hay pod name

Một cấu hình nguy hiểm:

~~~java
String groupId = "inventory-" + System.getenv("HOSTNAME");
~~~

Nếu mỗi pod có host khác nhau:

~~~text
inventory-pod-1 → group inventory-pod-1
inventory-pod-2 → group inventory-pod-2
inventory-pod-3 → group inventory-pod-3
~~~

Mỗi pod trở thành **một logical subscriber**, không phải ba workers trong cùng group. Với `PlaceOrderEvent`, cả ba có thể gọi side-effecting handler nếu offset policy và retention đưa sự kiện tới cả ba.

**Group ID** là danh tính logical consumer application, còn `client.id`/instance identity giúp quan sát và membership. Hai loại ID này không thay thế nhau.

Nếu thực sự muốn **shadow consumer** đọc riêng để thử nghiệm, hãy dùng group khác có **side effects bị vô hiệu hóa hoặc tách isolation**; đừng gửi hai groups cùng ghi một bảng production khi chưa có dedupe/authorization rõ.

## 33. Cảnh giác với deserialization và poison pill

Một record Kafka sai JSON/schema:

~~~text
topic orders.events / P2 / offset 71
value = malformed JSON
~~~

Lỗi có thể xảy ra trong deserializer **trước khi Spring Integration tạo Message**. Khi đó Filter/Transformer trong flow có thể không hề được gọi.

Cần thiết kế:

1. Error-handling deserializer/container strategy theo Kafka client/Spring Kafka version.
2. Phân loại **permanent malformed input** và **temporary infrastructure failure**.
3. Recovery/DLT record có topic/partition/offset và reasonCode an toàn.
4. Không retry vô hạn một bytes payload luôn sai schema.
5. Quarantine/DLT publish phải đạt durability trước khi bỏ quyền xử lý source.
6. Replay có versioned mapping policy và business idempotency.

**DLT/DLQ là cơ chế recovery do ứng dụng/container cấu hình, không phải kết quả tự có vì đặt `@MessagingGateway` hay `@ServiceActivator`.**

## 34. Error channel của Spring Integration khác Kafka container recoverer

Một sơ đồ:

~~~text
Kafka bytes
  → Consumer deserializer
      ├── failure: container/deserializer error handling
      └── success: Spring Integration inbound adapter
           → Filter/Transformer/Service Activator
               ├── sync exception: adapter/container boundary
               └── async failure: ErrorMessage/errorChannel or worker recoverer
~~~

Không khẳng định **mọi exception sẽ đi vào global `errorChannel`**. Nếu payload đã được gửi qua một `ExecutorChannel`, lỗi có thể xảy ra sau khi Kafka poll loop đã trở lại; recovery và offset ownership cần được thiết kế tại **đúng async boundary**.

| Lỗi | Phát hiện ở đâu | Đường xử lý thường xem xét |
|---|---|---|
| Bytes/schema invalid | Deserializer | Container error handler / DLT |
| Filter reject | Flow endpoint | Typed exception/discard channel theo contract |
| Mapper type lỗi | Transformer | Error channel hoặc container handler tùy sync/async |
| DB timeout | Service Activator | Bounded retry, không ACK mất việc |
| Business conflict | Domain handler | Terminal outcome/DLT tùy contract |
| Async worker crash | Worker queue/executor | Durable recovery, không chỉ log |
| Commit offset thất bại | Kafka container | Rebalance/redelivery readiness + idempotency |

**Một ACK trên Spring Message không nhất thiết là Kafka offset commit**; nếu dùng manual acknowledgement, phải hiểu chính xác metadata/acknowledgment được adapter/container đưa ra và semantics commit theo version.

## 35. Filter drop message và offset progression

Giả sử một Filter:

~~~java
@Filter(inputChannel = "orders.events.in")
public boolean accept(OrderEvent event) {
    return event.type() != OrderEventType.DEBUG;
}
~~~

Nếu `DEBUG` là **loại event được phép bỏ qua** theo contract, việc coi nó là processed/skip và commit offset có thể hợp lệ. Nhưng nếu Filter drop message vì **malformed required fields**, một consumer request–reply hoặc một downstream Aggregator có thể đợi forever, trong khi offset đã tiến.

**Phân biệt ba điều**:

- **Intentionally ignored:** event không thuộc subscription business logic, có skip metric.
- **Permanently rejected:** input sai hợp đồng, có DLT/rejection record.
- **Temporarily failed:** dependency down, cần retry/recovery.

Không catch DB errors rồi return `false` như một Filter rejection; như thế biến outage thành skipped message permanent.

## 36. Retry, DLT và ordering trong cùng partition

Một hot partition:

~~~text
P2:
  offset 71: invalid event EV-501
  offset 72: valid event EV-502
  offset 73: valid event EV-503
~~~

Nếu error handler retry offset 71 nhiều lần theo blocking strategy, offset 72/73 có thể **không tiến**. Nếu chuyển EV-501 sang DLT và commit/skip offset 71, offsets sau có thể tiến nhưng **order/business dependency** giữa EV-501 và EV-502 có thể không được bảo vệ.

Hai chính sách phổ biến:

1. **Block partition until resolved:** bảo toàn xử lý tuần tự nghiêm ngặt hơn nhưng tăng lag/hot partition risk.
2. **Skip/quarantine terminal poison pill:** cho throughput tiếp tục; chỉ đúng nếu nghiệp vụ cho phép xử lý events kế tiếp khi event trước bị loại.

Với delayed/non-blocking retries qua topic khác, cần đặc biệt lưu ý **per-key order có thể không còn giữ** khi record lỗi được chuyển đi, còn records mới đi thẳng.

**Retry policy là lựa chọn consistency**, không chỉ cấu hình “mấy lần retry”.

## 37. Domain idempotency cho consumer group

Một handler xử lý `OrderCreated`:

~~~java
record OrderEvent(
    String tenantId,
    String eventId,
    String orderId,
    int aggregateVersion,
    OrderEventType type
) {}

enum OrderEventType {
    CREATED, PAYMENT_AUTHORIZED, CANCELLED, DEBUG
}
~~~

Một business store có thể có unique key:

~~~sql
CREATE TABLE processed_order_event (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
~~~

**Không chỉ ghi marker rồi mới gọi DB write bên ngoài transaction.** Marker và side effect phải atomic khi cùng database; nếu external HTTP side effect, cần remote idempotency/reconciliation. `aggregateVersion` giúp kiểm tra **stale/out-of-order state transitions**, không thay event ID dedupe.

Các tình huống:

- Same key + same fingerprint → có thể trả already processed.
- Same key + different fingerprint → conflict/audit, không im lặng bỏ một payload khác.
- New event ID nhưng aggregate version thấp hơn committed version → stale event policy.
- Producer phát duplicate logical effect dưới eventId mới → cần domain operation ID hoặc constraint phù hợp; eventId dedupe không giải quyết hết.

**Kafka group assignment bảo đảm một owner tạm thời, không biến việc ghi business DB thành exactly-once.**

## 38. Transactional inbox với version guard

Một service skeleton:

~~~java
@Service
class OrderEventHandler {
    private final ProcessedEventRepository inbox;
    private final OrderStateRepository orders;
    private final EventFingerprint fingerprint;

    OrderEventHandler(
            ProcessedEventRepository inbox,
            OrderStateRepository orders,
            EventFingerprint fingerprint) {
        this.inbox = inbox;
        this.orders = orders;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {
        validateTrustedTenantAndPayload(event);
        String eventHash = fingerprint.canonicalHash(event);
        boolean first = inbox.insertIfAbsent(
            event.tenantId(), event.eventId(), eventHash);

        if (!first) {
            inbox.assertSameFingerprint(
                event.tenantId(), event.eventId(), eventHash);
            return; // Duplicate đã đạt trạng thái committed.
        }

        orders.applyIfVersionValid(
            event.tenantId(),
            event.orderId(),
            event.aggregateVersion(),
            event.type());
    }

    private void validateTrustedTenantAndPayload(OrderEvent event) {
        // Application validation + verified ingress identity.
    }

}
~~~

Các repositories/methods và `EventFingerprint` là **application abstractions**, chưa phải code hoàn chỉnh; production phải cung cấp `canonicalHash` với một canonical serialization/hash nhất quán, uniqueness constraints và transaction boundary được kiểm chứng. Nếu `applyIfVersionValid` phát hiện version gap cần retry later, **ném lỗi để rollback inbox marker**, không đơn giản return rồi đánh dấu event đã xử lý.

`@Transactional` trên handler phải được invoke qua Spring-managed bean/proxy; tự gọi nội bộ `this.method()` có thể bypass transaction proxy mặc định. Nếu dùng async channel, transaction phải mở trên **worker thread thực sự chạy DB code**.

## 39. Correlation với Splitter/Aggregator dưới consumer group

Khi mỗi OrderEvent được split thành ba child tasks:

~~~text
Kafka P2 offset 71 → OrderEvent(order=O-501)
    → Splitter:
        stock   member A
        pricing member B
        fraud   member C
    → workers/remote endpoints
    → Aggregator (expected A,B,C)
    → OrderReady/OrderRejected
~~~

**Kafka partition assignment** không phải **Aggregator correlation group**. Một consumer có thể sở hữu nhiều partitions, mỗi partition có nhiều orders; group key của Aggregator phải là **business scope** như `tenantId + orderId + operation/revision`, không dùng `group.id` hay `partitionId`.

Các bất biến:

- Child identities không trùng: member A/B/C.
- Correlation ID ổn định khi retry/replay.
- Duplicate child không được tính thành member mới.
- Child error phải có **terminal failure outcome** hoặc whole-group failure policy.
- GroupStore release/timeout/expiry không gây late reply thành summary thứ hai.
- Offset commit của parent phải phù hợp **mốc durable handoff/completion** mà flow cam kết.

Nếu Kafka consumer ACK parent ngay sau khi Splitter enqueue vào in-memory executor, crash có thể làm **mất child tasks** dù parent offset đã commit. Một durable outbox/work queue hoặc transaction protocol rõ là cần thiết cho workflow dài.

## 40. Đọc lag đúng: group lag khác business-processing latency

Một chỉ số thường dùng là **consumer lag** của group trên từng partition:

\[
\operatorname{lag}_{g,p}
=\max(0,\ \operatorname{logEndOffset}_{p}
-\operatorname{committedOffset}_{g,p})
\]

Đây là khoảng cách theo **offset positions**, không tự là số nghiệp vụ chưa hoàn tất. Với compacted log, offsets có thể có gaps; với async processing, commit có thể đi trước hoặc sau durable business completion tùy thiết kế.

Ví dụ:

~~~text
P2 log end offset = 190
Group inventory committed next offset = 150
Reported lag ≈ 40 offset positions
~~~

Lag tăng có thể vì producer nhanh hơn consumer, một hot partition, rebalance liên tục, DB chậm, poison pill retry blocking, hoặc commit progress chậm. **Lag bằng 0 không chứng minh mọi child tasks sau ExecutorChannel đã xử lý xong** nếu offset bị commit khi chỉ enqueue vào bộ nhớ.

Đo thêm per-partition lag, tuổi message, throughput, handler latency, retry rate và **business completion backlog**. Không chỉ dựa vào tổng lag của group.

## 41. Metrics cần quan sát

Các metrics sau là **gợi ý ứng dụng/vận hành**, không khẳng định Spring Integration tạo sẵn tất cả:

| Metric | Diễn giải |
|---|---|
| `consumer.group.assigned.partitions` | Số partitions đang giao cho mỗi member |
| `consumer.partition.lag` | Lag theo partition |
| `consumer.partition.oldest.age` | Tuổi bản ghi chưa xử lý |
| `consumer.poll.records.count` | Records được poll |
| `consumer.handler.duration` | Handler latency p50/p95/p99 |
| `consumer.handler.success.count` | Durable business completions |
| `consumer.handler.failure.count` | Lỗi theo reasonCode |
| `consumer.commit.failure.count` | Offset commit thất bại |
| `consumer.rebalance.count` | Tần suất thay đổi ownership |
| `consumer.rebalance.duration` | Thời gian rebalance |
| `consumer.duplicate.detected.count` | Dedupe thành công |
| `consumer.stale.version.count` | Events stale/out of order |
| `consumer.retry.attempt.count` | Retry amplification |
| `consumer.dlt.pending.count` | Backlog terminal errors |
| `consumer.async.work.pending.count` | Work đã nhận, chưa hoàn tất |

Metric labels chỉ nên có giá trị cardinality thấp như topic/group/partition, operation, error class. **Không dùng eventId, orderId, customer email, raw payload hay trace ID làm metric labels**.

## 42. Structured logging: tách transport position khỏi business identity

Một log được bảo vệ:

~~~text
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
consumerGroup=inventory-reservations
eventId=EV-501
tenantScope=tenant-a
orderId=O-501
aggregateVersion=3
handlerOutcome=SUCCEEDED
idempotencyOutcome=FIRST_COMMIT
offsetCommitRequested=true
~~~

Redelivery:

~~~text
sourceTopic=orders.events
sourcePartition=2
sourceOffset=71
consumerGroup=inventory-reservations
eventId=EV-501
handlerOutcome=DUPLICATE_COMPLETED
businessSideEffectCount=0
~~~

Không đưa bearer tokens, credentials hoặc raw full payload vào logs. Log source position giúp điều tra; business event ID dùng cho dedupe. **Commit requested không đồng nghĩa commit chắc chắn đã thành công**.

## 43. Unit test business partition key ổn định

Một pure function tạo key:

~~~java
final class OrderPartitionKey {
    static String forOrder(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                "MISSING_PARTITION_KEY_COMPONENT");
        }
        return tenantId.length() + ":" + tenantId
            + ":" + orderId.length() + ":" + orderId;
    }
}
~~~

Length-prefixed encoding giúp giảm nhập nhằng khi field chứa ký tự phân tách. Với production có thể dùng canonical binary encoding/hashed key có version.

~~~java
@Test
void sameOrderKeepsStableBusinessPartitionKey() {
    String first =
        OrderPartitionKey.forOrder("tenant-a", "O-501");
    String retry =
        OrderPartitionKey.forOrder("tenant-a", "O-501");
    String otherTenant =
        OrderPartitionKey.forOrder("tenant-b", "O-501");

    assertEquals(first, retry);
    assertNotEquals(first, otherTenant);
}

@Test
void missingOrderIdIsRejected() {
    assertThrows(IllegalArgumentException.class,
        () -> OrderPartitionKey.forOrder("tenant-a", null));
}
~~~

**Test này xác nhận key contract**, không chứng minh partition assignment qua mọi partition-count migration. Cần test producer với partitioner/cluster configuration thật.

## 44. Producer test: cùng key được gửi tới cùng partition

Một Kafka producer conceptual:

~~~java
OrderEvent created = new OrderEvent(
    "tenant-a", "EV-501", "O-501", 1,
    OrderEventType.CREATED);
OrderEvent paid = new OrderEvent(
    "tenant-a", "EV-502", "O-501", 2,
    OrderEventType.PAYMENT_AUTHORIZED);

String key = OrderPartitionKey.forOrder(
    created.tenantId(), created.orderId());

kafkaTemplate.send("orders.events", key, created);
kafkaTemplate.send("orders.events", key, paid);
~~~

Trong integration test với topic cố định, đọc metadata `RecordMetadata.partition()` để xác minh hai records được gán cùng partition **với partitioner hiện hành**. Cùng key không bảo đảm business creation order nếu nhiều producers publish cùng order nhưng race.

Không chạy test bằng broker production; dùng test broker độc lập (embedded/Testcontainers) và quản lý topic/group test lifecycle riêng.

## 45. Integration test: 6 partitions, 3 consumers cùng group

~~~text
Topic test.orders: 6 partitions
Group test.inventory: 3 consumers
Produce 600 independent events, keys trải đều nhiều orders

Expected:
  every eventId has one committed business outcome;
  no eventId missing;
  assignments cover all 6 partitions;
  handler invocations may exceed distinct commits after retry.
~~~

Test cần:

1. Tạo topic có 6 partitions xác định.
2. Cho ba consumers cùng group ID join và đợi assignment thực sự.
3. Gửi events có event IDs và business keys truy vết được.
4. Đợi inbox/DB đạt 600 **distinct completed effects**, không chỉ 600 receives.
5. Assert không có duplicate business effect.
6. Kiểm tra assignment bao phủ partitions, không ép chia đều 2/2/2 khi không cần.
7. Dừng group và xác minh recovery/committed progress theo policy.

**Không dùng `assert each consumer receives exactly 200` làm correctness invariant.** Key skew và assignment có thể không đều mà vẫn không mất events.

## 46. Integration test: hai groups nhận cùng sự kiện độc lập

~~~text
Topic test.orders (6 partitions)
Group test.inventory: 2 consumers
Group test.analytics: 2 consumers
~~~

Kỳ vọng:

- Inventory commits 600 distinct event IDs vào projection riêng.
- Analytics commits 600 distinct event IDs vào projection độc lập.
- Inventory progress không thay đổi cursor của Analytics.
- Tắt Analytics không ngăn Inventory tiếp tục đọc.
- Analytics restart có thể catch up theo retention/offset policy.

**Hai groups là hai logical subscriptions**, không phải bốn workers cùng chia một consumer workload. Test phải dùng stores/projections tách biệt; đừng để Analytics gọi nhầm cùng side-effecting `reserveStock()` của Inventory.

## 47. Fault injection: crash sau DB commit trước offset commit

~~~text
P2 offset 71, EV-501.
Consumer C1:
  DB COMMIT + inbox EV-501
  crash before committing next offset 72

Consumer C2:
  owns P2 after rebalance
  reads EV-501 again
  inbox detects completed duplicate
  no new business mutation
  commits progress
~~~

Assert:

- Offset 71 có thể được đọc hơn một lần.
- EV-501 chỉ có **một** committed side effect.
- Duplicate attempt không khiến partition retry vô hạn.
- Same key khác fingerprint gây conflict, không bỏ qua silently.
- Rollback trước DB commit không để lại poisoned inbox marker.
- Partition ownership/progress phục hồi sau rebalance.

Test dùng fault injection quanh **real transaction commit**, không chỉ mock `handler.apply()` trả true.

## 48. Test ordering khi downstream chạy đồng thời

Ba events:

~~~text
EV-1: O-501 version 1 CREATED
EV-2: O-501 version 2 PAYMENT_AUTHORIZED
EV-3: O-501 version 3 CANCELLED
~~~

Thử hai topologies:

1. **Sequential handler theo partition** với aggregate version guard.
2. **ExecutorChannel/thread pool**: dùng test latches để EV-3 hoàn tất trước EV-2.

Assertions:

- Final domain state phải hợp lệ theo state machine/version policy.
- Không áp dụng version 2 như một update mới **sau** khi version 3 đã commit.
- Nếu EV-3 phụ thuộc EV-2, handler phải retry/defer/reject có chủ đích; không skip và commit event như thành công.
- Duplicate EV-2 không được phát payment/stock effect lần thứ hai.
- Offset progression không đi trước durable processing nếu không có handoff an toàn.

**Ordering key đúng không đủ nếu downstream executor làm mất ordering**. Test phải chạy trên topology thật.

## 49. Test poison pill, retry và DLT

~~~text
P2 offset 71: malformed JSON
P2 offset 72: valid OrderCreated(O-502)
~~~

Kiểm tra:

- Deserializer phát hiện malformed bytes **trước IntegrationFlow** nếu phù hợp.
- Lỗi được phân loại permanent/transient đúng.
- Permanent poison pill vào DLT/quarantine có source position và reasonCode.
- Chỉ commit/skip offset sau khi recovery đã durable theo policy.
- Valid offset 72 không bị xử lý mất trách nhiệm.
- Nếu business cần strict order, không xử lý 72 như success khi 71 còn là một event bắt buộc chưa được giải quyết.
- DLT unavailable không gây ACK/drop im lặng.
- Replay từ DLT không gây side effect trùng.

**Lag về 0 không phải thành công nếu DLT backlog tăng và không có owner xử lý lỗi.** Đo cả số poison pills và thời hạn recovery.

## 50. Test tăng partitions và group migration

Một integration test khi topic tăng từ 6 lên 12 partitions:

1. Publish events version 1/2 cho một order với key cố định.
2. Ghi lại partition assignments thực tế.
3. Tăng partition count ở **môi trường test**.
4. Publish event version 3 cho cùng key.
5. Kiểm tra key có thể đi partition khác theo partitioner hiện hành.
6. Dùng aggregateVersion hoặc cutover protocol để phát hiện/không ghi đè state cũ.
7. Đo backlog và rebalance impacts.

Đừng dùng một test kiểm tra hash modulo cố định để khẳng định mọi Kafka client có mapping giống nhau. Quan trọng là **đánh giá tính đúng đắn khi mapping thay đổi**.

Với **group ID migration**, kiểm thử một group mới có thể bắt đầu từ `earliest/latest` tùy committed offsets/reset policy, và sẽ **đọc độc lập với group cũ**. Không chuyển sang group mới mà không có quyết định explicit về backfill và dedupe business side effects.

## 51. Security và governance của partition/group configuration

Các rủi ro:

- Untrusted caller tự khai `group.id`, topic hoặc tenant để đọc stream khác quyền.
- Một service dùng group ID mới khiến toàn bộ lịch sử bị xử lý lại.
- Một consumer group test vô tình dùng production topics và tạo side effects.
- DLQ chứa payload/headers nhạy cảm mà retention/access control không đúng.
- Deserializer polymorphic/untrusted packages làm tăng bề mặt tấn công.
- Partition key chứa email, phone, token hoặc personal identifiers không cần thiết.
- Một worker được cấp quyền publish/consume topics rộng hơn cần thiết.

Biện pháp:

1. Dùng Kafka ACL/service identity, TLS/SASL theo deployment và quyền topic/group tối thiểu.
2. Config `group.id` và topic names qua trusted deployment config, không trực tiếp từ message.
3. Validate deserializer schema/type, giới hạn message bytes và headers.
4. Scoped business idempotency keys theo tenant/source, không tin raw tenant header.
5. Dùng protected DLT/quarantine với retention, encryption, audit và access control.
6. Giới hạn những application groups được phép tồn tại trên production stream.
7. Có quy trình change review cho partition count, group ID, retention/compaction và offset reset.

**Consumer group ID là danh tính subscription, không phải chứng cứ authorization của một business operation.** Nếu consumer xử lý `CancelOrderCommand`, handler vẫn phải validate/authorize theo trust boundary phù hợp.

## 52. Checklist thiết kế trước khi triển khai

- Xác định **logical consumer applications**: ai thực sự cần nhận cùng event stream?
- Phân biệt Kafka **partition**, consumer member và **group ID**.
- Chọn partition key theo **ordering scope** của domain.
- Xác nhận partitions đủ cho concurrency kỳ vọng nhưng không tạo chi phí vô ích.
- Có kế hoạch ứng phó **hot key/key skew**.
- Biết thay đổi partition count có thể đổi key-to-partition mapping.
- Replicas cùng logical workload dùng **một group ID**.
- Không coi thêm groups là cách load balance một consumer function.
- Chọn offset/ACK policy dựa trên durable completion/handoff.
- Có transactional inbox/idempotency cho replay và broker redelivery.
- Có aggregate version/ordering checks cho stateful commands.
- Xác minh những async channels không làm commit offset quá sớm.
- Có retry/DLT/error channel phân loại permanent/transient.
- Có chiến lược rebalance, crash recovery và long-running handlers.
- Có bảo mật topics/groups/headers, source/tenant identity và DLT.
- Có tests cho concurrency, duplicate/rebalance, poison pill và migration.
- Có metrics per-partition lag, handler latency, business completion và side effects.

**Checklist đã đầy đủ vẫn cần test với broker/container thật.** Unit test Java thuần không xác minh partition assignment, broker offsets, DLT publishing hay rebalance behavior.

## 53. Runbook khi consumer lag tăng sau khi scale

Giả sử đã tăng replicas từ 3 lên 9 nhưng throughput gần như không đổi:

1. **Xem partition count:** topic có bao nhiêu partitions? 6 partitions thì 9 members không thể đều có assigned partition từ topic này.
2. **Xem group IDs:** replicas có thật cùng `group.id` không, hay vô tình tạo 9 groups độc lập?
3. **Xem assignments:** partitions được chia ra sao, có hot partition không?
4. **Xem lag per partition:** một partition nghẽn hay tất cả cùng tăng?
5. **Xem handler latency:** DB, HTTP downstream, locks, connection pools có bão hòa?
6. **Xem rebalance count:** autoscaling/long poll có gây chuyển ownership liên tục?
7. **Xem poison pill/retry:** một offset có block cả partition?
8. **Xem executor queues:** Kafka lag thấp nhưng async tasks còn pending?
9. **Xem offset commits:** đã commit sau durable side effect chưa?
10. **Xem duplicate business effects:** redelivery hoặc hai groups có khiến double writes?
11. **Đánh giá key skew:** partition key có quá thô như merchantId duy nhất?
12. **Chọn hành động:** tối ưu handler/bulkhead, tăng partitions có migration plan, sửa group IDs hoặc đổi topology đúng yêu cầu.
13. **Kiểm chứng sau thay đổi:** không chỉ lag giảm mà distinct business outcomes vẫn đúng.

Nếu vô tình triển khai ba groups thay vì một, **đừng chỉ sửa group ID rồi bỏ qua những side effects đã xảy ra**. Cần đối chiếu DB/outbox, reconcile duplicates và xem trạng thái committed offsets/replay trước khi cutover.

## 54. Những hiểu lầm thường gặp

**“Partition và consumer group là hai cách khác nhau để chia tải, chỉ chọn một.”** Sai. Trong Kafka chúng là hai khía cạnh của cùng subscription topology.

**“Topic có 6 partitions thì consumer group có thể chạy 60 workers cùng xử lý song song cả 6 partitions.”** Không theo partition assignment thông thường.

**“Tăng consumer groups giúp mỗi event chỉ một worker xử lý nhanh hơn.”** Sai. Các groups độc lập có thể đều xử lý cùng record.

**“Cùng partition key luôn bảo đảm đúng thứ tự nghiệp vụ.”** Không nếu producer race hoặc downstream xử lý song song.

**“Ordering được bảo đảm trên toàn topic.”** Không; Kafka ordering scope là từng partition.

**“Một consumer nhận 6 partitions đồng nghĩa có 6 threads thực thi.”** Không.

**“Tăng partitions luôn vô hại với key/order mapping.”** Không; key có thể được gán sang partition mới.

**“Group ID nên bao gồm pod name để tránh conflict.”** Không nếu các pods phải chia cùng một workload.

**“Auto-offset-reset=earliest sẽ replay từ đầu mỗi lần deploy.”** Không khi group đã có committed offset hợp lệ.

**“Commit offset nghĩa là business transaction đã commit.”** Không tự động.

**“Auto commit false bảo đảm exactly-once.”** Không; cần error/ack/transaction/idempotency policy.

**“Producer idempotence giải quyết duplicate HTTP payment.”** Không; đó là side effect của resource khác.

**“Rebalance chỉ ảnh hưởng latency, không thể gây replay.”** Không; uncommitted records có thể được xử lý lại.

**“ExecutorChannel giữ nguyên per-partition processing order.”** Không nếu workers hoàn tất lệch thứ tự.

**“PublishSubscribeChannel của Spring Integration tương đương Kafka consumer group.”** Không.

**“RabbitMQ queue có cùng partition count/offset như Kafka.”** Không với queue thông thường.

**“DLT retry không ảnh hưởng ordering.”** Có thể ảnh hưởng nếu records sau tiếp tục chạy trước event lỗi.

**“Kafka lag = 0 nghĩa là mọi child jobs đều hoàn tất.”** Không khi có async work chưa durable xử lý.

**“Một offset là khóa idempotency tốt cho mọi domain.”** Không; nó chỉ nhận diện source position trong một topic/partition.

**“Một group mới có thể chạy cùng side-effecting handler an toàn chỉ vì tên khác.”** Không; cần separation/idempotency.

## 55. Bài thực hành: scale đúng, không nhân đôi business side effects

Xây mini project **OrderEventBrokerProcessing**:

1. Tạo Kafka topic `orders.events` có 6 partitions trong môi trường test.
2. Thiết kế `OrderEvent` với eventId, tenantId, orderId, aggregateVersion và type.
3. Viết pure function tạo partition key từ tenant+orderId.
4. Dùng Spring Kafka producer publish các events cùng order và kiểm tra partition metadata.
5. Tạo Spring Integration Kafka inbound adapter, DirectChannel và Service Activator.
6. Cấu hình group `inventory-reservations`, container concurrency=3.
7. Triển khai transactional inbox + order projection + aggregate version checks.
8. Gửi 600 events; assert 600 distinct business completions và kiểm tra group assignments.
9. Tăng consumers lên 9 trên 6 partitions; quan sát members không assigned partition của topic.
10. Tạo group `analytics-projection`; chứng minh đây là independent subscription.
11. Cố tình dùng group ID theo pod và quan sát duplicate logical consumption (với **mock side effects**, không dùng DB production).
12. Inject crash sau DB commit trước offset commit; assert redelivery không double-write.
13. Test một malformed record rồi một valid record cùng partition; thiết kế DLT/recovery.
14. Chèn ExecutorChannel, chủ động đảo completion order; thêm version guard hoặc key-serial handler.
15. Tạo hot key, đo per-partition lag và đưa ra phương án cải thiện.
16. Tăng số partitions trong topic test, kiểm tra tác động key mapping và migration.
17. Thêm Splitter 3 children và Aggregator với failure outcome/member manifest.
18. So sánh với một RabbitMQ queue có ba competing consumers nếu có môi trường test tương ứng.
19. Tạo dashboard lag, rebalances, retries, DLT và distinct business commits.
20. Viết runbook cho tình huống scale không cải thiện throughput.

**Tiêu chí hoàn thành:** có thể giải thích và chứng minh **partition là phạm vi lưu trữ/order; consumer group là subscription/load balancing**; scale không tạo duplicate business side effects; replay/rebalance/poison pills được xử lý bền vững; group khác nhận stream độc lập; monitoring phản ánh cả offset progress lẫn business completion.

## 56. Ghi nhớ

**Partition hoặc consumer group** thực chất là câu hỏi về **hai thiết kế phối hợp** trong Kafka: **partition** chia topic thành các ordered logs; **consumer group** quyết định các consumer chia partitions để cùng xử lý một logical subscription. **Thêm consumer group** tạo independent subscriber; **thêm consumer trong cùng group** chia workload nếu có đủ partitions. Không dùng một khái niệm thay thế khái niệm kia.

Muốn giữ thứ tự theo order, chọn **message key đúng business scope**, nhớ Kafka chỉ có ordering **theo partition** và flow async có thể làm completion lệch thứ tự. Khi scale partitions, đổi group membership hoặc rebalance, hãy chuẩn bị **redelivery/idempotency/aggregate version guards**. Offset commit, broker ACK, Filter discard, Spring `errorChannel` và business DB commit là **những mốc khác nhau**, không mặc nhiên atomic.

Trong **Spring Integration**, Kafka inbound adapter/consumer container quản lý group, poll và partition assignment; Router/Filter/Transformer/Service Activator xử lý message bên trong flow; Splitter/Aggregator dùng **business correlation riêng**, không dùng Kafka group ID làm group key. So với RabbitMQ/JMS, mục tiêu competing consumers có điểm tương đồng nhưng semantics queue/ACK/replay không đồng nhất.

**Chọn topology theo ordering, throughput và side-effect invariants, rồi chứng minh bằng integration tests với broker thật hoặc test broker độc lập.** Một cấu hình scale tốt là cấu hình vừa có throughput phù hợp, vừa không mất message hay tạo business effect trùng khi crash, retry và rebalance.

### Tài liệu tham khảo

- Apache Kafka Documentation, **Consumer and Consumer Groups**: https://kafka.apache.org/documentation/#consumerapi
- Apache Kafka Documentation, **Design and Message Delivery Semantics**: https://kafka.apache.org/documentation/#design
- Apache Kafka Documentation, **Operations**: https://kafka.apache.org/documentation/#operations
- Spring Integration Reference, **Kafka Support**: https://docs.spring.io/spring-integration/reference/kafka.html
- Spring Integration Reference, **Message Channels**: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Kafka Reference, **Message Listener Containers**: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka Reference, **Handling Exceptions**: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- RabbitMQ Tutorials, **Work Queues**: https://www.rabbitmq.com/tutorials/tutorial-two-java
- RabbitMQ Tutorials, **Publish/Subscribe**: https://www.rabbitmq.com/tutorials/tutorial-three-java
