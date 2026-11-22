# Thử failover khi có giao dịch hoặc yêu cầu đang chạy

Một cụm NoSQL có ba replica có thể vượt qua bài kiểm tra “tắt một node rồi chờ cluster phục hồi”, nhưng vẫn thất bại khi lỗi xảy ra **đúng lúc giao dịch đang commit**. Ví dụ: API tạo Order đã commit ở database, nhưng primary mất kết nối trước khi gửi ACK. Nếu ứng dụng hiểu timeout là “chưa ghi” và retry bằng ý định mới, khách có thể nhận hai Order hoặc bị thu tiền hai lần. Ngược lại, không retry có thể khiến người dùng thấy lỗi dù đơn đã được tạo.

**Kiểm thử failover** vì vậy cần trả lời:

1. Read/write/transaction đang chạy sẽ có kết quả gì khi node, kết nối hoặc vùng bị lỗi?
2. Khi nào caller biết chắc **đã commit**, **đã từ chối**, hoặc **không rõ kết quả**?
3. Retry, chuyển coordinator và leader election có giữ **bất biến nghiệp vụ**?
4. Dịch vụ hồi phục trong ngân sách latency, availability, RPO/RTO và consistency nào?
5. Bằng chứng nào chứng minh đúng dữ liệu chứ không chỉ “cluster lại HEALTHY”?

Bài học thuộc chương **Kiểm thử lỗi và tải**, module **Database No SQL**, hướng dẫn thiết kế kiểm thử có concurrent requests, failover, kết quả chưa rõ, idempotency, fencing, giao dịch nhiều bước và phép đo end-to-end. Ví dụ tham chiếu MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis và read models.

> **Nguyên tắc:** Timeout sau khi đã gửi write **không chứng minh write chưa commit**. Retry phải giữ cùng business intent và bảo vệ mọi side effect khỏi bị thực hiện lặp. Một response thành công phải phù hợp durability/consistency đã cam kết với caller.

Các ví dụ/số liệu chỉ để học. API, election, khả năng transaction, consistency và cách fault injection phụ thuộc engine, phiên bản và topology. Chỉ chạy phá lỗi trong môi trường/phạm vi được cấp phép, có rollback, dữ liệu phù hợp và stop conditions rõ ràng.

## 1. Failover là gì và phải kiểm thử ở những tầng nào?

**Failover** chuyển trách nhiệm phục vụ từ thành phần lỗi hoặc mất liên lạc sang thành phần khác. Có thể là:

- **Primary/leader election:** một node khác trở thành primary/leader.
- **Replica/coordinator reroute:** client chuyển request tới node khác.
- **Zone/region failover:** đổi vùng, có thể đổi consistency và RPO.
- **Application failover:** API pod mới tiếp tục request, DB có thể không đổi.
- **Queue/worker failover:** job đang xử lý bị gán lại.
- **Manual failover:** operator thực hiện sau khi kiểm tra điều kiện.

Kiểm thử phải xét cả:

| Tầng | Các tín hiệu |
|---|---|
| Hạ tầng | Node health, election/quorum, replica lag, time to new owner |
| Driver | Topology discovery, connection pool, retries, timeouts |
| API | Request status, deadline, error handling, backpressure |
| Dữ liệu | Acknowledged writes, lost/duplicate updates, stale reads |
| Nghiệp vụ | Order/stock invariants, payment idempotency, outbox |
| Người dùng | Availability, p95/p99, recovery time và read-after-write |

Một primary được bầu sau 15 giây không có nghĩa một request đang commit không tạo duplicate effect.

## 2. Các loại lỗi có hành vi khác nhau

| Fault | Hiện tượng | Rủi ro |
|---|---|---|
| Process/node crash | Kết nối đóng giữa write | Unknown commit, reconnect storm |
| Network partition | Hai bên sống nhưng không giao tiếp | Quorum loss, split brain theo architecture |
| Primary step-down | Primary ngừng chấp nhận write | Transient errors, session invalidation |
| GC pause / process freeze | Node dừng phản hồi rồi quay lại | Timeout, stale lease, delayed writes |
| Slow disk | Commit/flush chậm bất thường | Tail latency, backlog, timeouts |
| Packet loss / half-open TCP | Request đi nhưng response không về | Caller không biết commit outcome |
| Replica lag | Replica online nhưng chưa áp hết writes | False 404, stale read |
| AZ/region outage | Nhiều nodes/links cùng mất | RPO/RTO và failover boundary |
| Stale driver topology | Client kết nối node cũ | Lặp lỗi, pool thrash |
| External service failure | DB commit nhưng payment/queue chưa xong | Divergent workflow |

**Mất kết nối không đồng nghĩa mất dữ liệu.** Nếu DB đã commit nhưng ACK rơi trên đường, kiểm thử chỉ dựa HTTP status có thể kết luận sai.

## 3. Các giai đoạn của một write

~~~mermaid
flowchart TD
    A["Client submits intent"] --> B["API validation and authorization"]
    B --> C["Driver sends command"]
    C --> D["DB accepts request"]
    D --> E["Commit / durable acknowledgement"]
    E --> F["DB response reaches API"]
    F --> G["HTTP response reaches client"]
~~~

Failover có thể xảy ra **trước, trong hoặc sau commit**. Từ góc nhìn caller, cần phân biệt:

1. **NOT_SENT:** command chưa rời ứng dụng.
2. **REJECTED:** có kết quả xác định rằng điều kiện không đạt, command không commit.
3. **COMMITTED:** commit đã được xác minh theo durability contract.
4. **UNKNOWN:** request đã gửi, nhưng response/commit status không xác định.
5. **COMMITTED_BUT_ACK_LOST:** thực tế DB đã ghi, caller chỉ thấy timeout.
6. **FOLLOW_UP_PENDING:** DB đã commit, còn outbox/payment/notification phải hoàn thành hoặc reconcile.

Engine/SDK có thể không cung cấp đủ thông tin để phân loại mọi case. Vì vậy hệ cần **stable operation ID, result ledger, versioning và reconciliation path**.

## 4. Success, definitive failure và unknown outcome

| Caller thấy | Điều có thể kết luận | Hành động |
|---|---|---|
| Commit success theo contract | Commit đạt mức đảm bảo đã chọn | Trả stable result |
| Business condition rejected | Không được thực hiện theo điều kiện | Không retry như lỗi mạng |
| Chưa gửi command | Có thể retry nếu chắc chắn chưa gửi | Giữ cùng intent ID |
| Timeout sau gửi write | Có thể đã commit hoặc chưa | Reconcile, không tạo intent khác |
| Connection lost sau DB commit | Caller thấy UNKNOWN | Idempotent lookup/retry cùng key |
| Version conflict | State đã đổi do cạnh tranh | Đọc state và áp business rule |

**Timeout là thiếu khả năng quan sát kết quả**, không phải bằng chứng rollback.

## 5. Timeline: commit xong nhưng mất ACK

~~~text
T0 Client -> API: POST /orders, idempotencyKey=K1
T1 API -> DB: create order and record K1
T2 DB commits under configured acknowledgement policy
T3 Primary crashes or response path breaks
T4 API receives timeout
T5 Client retries same K1 on new API instance
T6 New leader/coordinator processes retry
~~~

Nếu intent K1 gắn với kết quả durable được bảo vệ atomically hoặc bằng protocol phù hợp:

~~~text
Retry K1 -> return original Order O1001, no duplicate effect
~~~

Nếu API sinh Order ID mới mỗi lần retry:

~~~text
Retry K1 -> might create Order O1002 in addition to O1001
~~~

Bài test cần theo dõi **cùng một business intent qua failover**, không chỉ bắn requests ngẫu nhiên rồi đếm lỗi.

## 6. Timeline: lỗi trước khi commit

~~~text
T0 API sends conditional reservation K2
T1 DB begins processing
T2 Primary crashes before durable commit
T3 Driver reports transient failure/timeout
T4 Driver discovers new primary/coordinator
T5 API retries K2 with same intent/preconditions
T6 System commits once or rejects because business state changed
~~~

Retry không nhất thiết phải thành công: nếu ghế cuối đã được người khác đặt, **business rejection** là đúng. Điều cần xác minh là không có double reservation, mất write đã được ACK, hoặc một ACK success không đáp ứng durability contract.

Không giả định mọi crash trước HTTP response đồng nghĩa database đã rollback; phải dựa vào transaction/commit semantics của sản phẩm.

## 7. Read đang thực hiện cũng chịu failover

Một read có thể:

- Retry trên node mới.
- Đọc replica chưa bắt kịp.
- Mất session/snapshot/cursor.
- Chuyển node giữa các pages và nhìn thấy duplicate/missing rows.
- Bị timeout ở driver server-selection/pool acquire.
- Trả 404 giả sau POST thành công.
- Nhìn thấy quyền truy cập hoặc soft-deleted record đã lỗi thời.

| Read operation | Điều cần bảo vệ |
|---|---|
| GET Order sau POST | Read-your-writes/session token |
| Read stock trước quyết định đặt cuối | Consistency phù hợp với invariant |
| Browse catalog | Bounded staleness nếu được công bố |
| Search | Eventual freshness và deletion propagation |
| Paginated report | Stable cursor/snapshot semantics |
| Permission lookup | Không cấp quyền từ policy cũ trái contract |

**Read retry có thể vô hại về side effect nhưng không vô hại về tính đúng đắn.** Test phải gắn read với version hoặc trạng thái nghiệp vụ mong đợi.

## 8. Atomicity scope: transaction, batch và item là ba điều khác nhau

NoSQL có thể hỗ trợ atomic update trên một document/item, conditional write, transaction nhiều documents, batch API hoặc lightweight transaction. Nhưng **batch không mặc nhiên all-or-nothing**, và transaction có phạm vi giới hạn theo engine/version/topology.

Ví dụ gửi 100 updates qua một batch API:

~~~text
Write 1..70 accepted.
Node fails.
Caller loses response.
Write 71..100 may not have been applied.
~~~

Nếu API cho phép partial success, một lần retry cả batch phải có idempotency/versioning **theo từng entry** để tránh duplicate effect. Nếu batch transaction được sản phẩm bảo đảm atomic, vẫn có thể có **unknown commit outcome** khi ACK bị mất.

Câu hỏi bắt buộc trước test:

- Đơn vị atomicity là key, item, partition, transaction hay cluster?
- Có giới hạn số objects, partitions hoặc thời gian transaction không?
- Có API status/result để xác định commit?
- Trên primary/leader mới, transaction context còn hay phải mở mới?
- Retryable write/transaction được SDK hỗ trợ và giới hạn thế nào?
- Có thể replay ngoài transaction những side effect nào?

## 9. ACID, durability, consistency và availability cần kiểm riêng

**Atomicity** nói các thao tác trong phạm vi transaction commit hoặc rollback theo protocol. **Durability** nói mức bảo vệ writes đã ACK. **Consistency** nói read được phép thấy trạng thái gì. **Availability** nói ứng dụng còn phục vụ không khi có lỗi.

Một transaction atomic vẫn có thể:

- Commit rồi caller timeout.
- Mất availability trong election window.
- Có read trên replica chưa áp commit.
- Có outbox event chưa phát nếu không nằm cùng transaction.
- Bị application retry quá hạn tạo side effect ngoài DB.

Bài test không nên ghi “pass vì transaction rollback đúng” rồi bỏ qua HTTP 503 rate, session visibility hay idempotent retry.

## 10. Idempotency key phải đại diện cho ý định nghiệp vụ

Ví dụ một request:

~~~http
POST /orders
Idempotency-Key: intent-K1
Content-Type: application/json

{"sku":"SKU-A","quantity":1}
~~~

Server xác thực user/tenant rồi gắn identity đó với idempotency key. Một ledger logic:

~~~json
{
  "tenantId": "t01",
  "operationId": "intent-K1",
  "fingerprint": "hash-of-canonical-request",
  "state": "COMMITTED",
  "result": {
    "orderId": "O1001",
    "state": "CONFIRMED"
  },
  "sourceVersion": 17
}
~~~

Semantics mong muốn:

1. Cùng key và fingerprint → trả cùng kết quả đã commit.
2. Cùng key nhưng payload khác → reject thay vì ghi intent mới.
3. Key mới → một ý định mới với precondition riêng.
4. Ledger và hiệu ứng nghiệp vụ phải atomic hoặc có protocol phục hồi/đối soát không lặp.
5. TTL của ledger phải bao phủ khoảng retry, failover và reconciliation.
6. Nếu trạng thái PENDING/UNKNOWN, API không tự tuyên bố thất bại chắc chắn.

**Một Redis cache giữ dedup key nhưng nguồn Orders durable ở database khác** có thể mất dedup record khi cache failover. Cần xác minh durability của nơi giữ ledger theo mức rủi ro nghiệp vụ.

## 11. Fencing token: kiểm tra stale writer khi lease hết

Một worker giữ lock có thể bị pause rồi thức dậy sau khi lease đã được trao cho worker khác:

~~~text
Worker A has token 41 and pauses.
Lease expires.
Worker B obtains token 42 and writes.
Worker A resumes and attempts write with token 41.
Trusted commit boundary must reject stale token 41.
~~~

Để chống stale actor:

- Token/epoch phải tăng đơn điệu theo scope.
- Token phải được enforce ở **nơi thực hiện effect**, không chỉ trong bộ nhớ worker.
- Conditional write/transaction hoặc trusted gateway phải kết hợp version/token vào điều kiện atomic.
- Có audit cho stale attempts và ownership transitions.
- Test GC pause/network partition đủ dài để worker cũ thực sự chạy lại.

Lease deadline phụ thuộc clock/timeouts, không phải cơ chế fencing tự động. Nếu target data store không hỗ trợ enforcement thì phải chọn protocol ngừng writer cũ, chuyển quyền hoặc giữ invariant theo cách khác.

## 12. Quorum: khi nào failover chấp nhận reads và writes?

Trong một hệ replicated, operation thành công có thể cần acknowledgment từ một số replicas, hoặc một majority/quorum theo protocol. **Không dùng một công thức duy nhất cho mọi engine**:

- Với consensus-based leader election, mất majority có thể ngăn leader mới hoặc commit.
- Với Dynamo-like replication, read/write consistency settings ảnh hưởng availability/visibility theo partitions.
- Với asynchronous replication, một ACK trên primary có thể chưa có mặt ở secondary.
- Với multi-region systems, conflict resolution và write routing có semantics riêng.

Cần test tối thiểu:

1. Fail primary khi còn đủ voting/quorum capacity.
2. Mất node khiến quorum không thể đạt.
3. Partition tách majority/minority hoặc local/remote DC.
4. Replica lag trước failover.
5. Request với từng consistency mode mà ứng dụng thực dùng.
6. Recovery sau khi network heal: có divergence, conflict hoặc repair cần xử lý không?

Khi database trả unavailable để tránh mất consistency/durability đã cam kết, ứng dụng **không được tự hạ guarantee âm thầm** rồi trả success nghiệp vụ.

## 13. Automated failover và manual failover

| Thuộc tính | Automatic | Manual |
|---|---|---|
| Trigger | Cluster/control plane quyết định theo failure detector | Operator xác nhận sự cố |
| Ưu điểm | Giảm thời gian phản ứng | Có thể xét rủi ro, dữ liệu và dependency |
| Rủi ro | Election loop, false failure detection, reconnect storm | Delay do con người, runbook sai |
| Bằng chứng cần | Ownership/quorum, no split brain, operation results | Approval, decision, epoch/route changes |
| Kiểm thử | Inject fault và quan sát tự chuyển | Tabletop + runbook rehearsal |

Một cluster tự bầu primary **không đồng nghĩa** ứng dụng tự retry đúng. Test cả driver config, load balancer, API timeouts, transaction handling và background workers.

## 14. Tiêu chí thành công: an toàn dữ liệu và phục hồi dịch vụ

Một test pass cần định nghĩa trước:

| Mặt kiểm thử | Chỉ tiêu/điều kiện ví dụ |
|---|---|
| **No acknowledged loss** | Mọi write đã nhận ACK theo contract còn truy ra sau recovery |
| **No duplicate effect** | Một business intent không tạo hai Orders/charges |
| **Atomicity** | Không lộ partial transaction ngoài phạm vi cho phép |
| **Conditional integrity** | Version/stock precondition vẫn enforce |
| **Read consistency** | Read-your-writes/monotonic read giữ theo hợp đồng |
| **Availability** | Tỷ lệ lỗi và thời gian gián đoạn trong SLO |
| **Tail latency** | p95/p99 không vượt giới hạn cho phép kéo dài |
| **Recovery** | Quorum/leader/replicas catch up, no data divergence |
| **Security** | Không mở quyền, không stale permission leakage |
| **Observability** | Tất cả unknown outcomes có ID và đường reconcile |
| **Resource use** | Retries, connections, queues không gây collapse |

Không tự lấy các ngưỡng như “20 giây election” làm quy định chung. Lấy số từ **SLO, topology, write concern và failure budget** của hệ.

## 15. Xác định phạm vi an toàn của một thí nghiệm chaos

Trước khi inject faults:

- Chọn môi trường staging/load test hoặc production phạm vi nhỏ **được cho phép rõ**.
- Dùng dữ liệu tổng hợp và business intents không gây charge thực.
- Đặt maximum duration, traffic load và blast radius.
- Chuẩn bị snapshot/backup/recovery path.
- Có chủ trì, on-call và quyền dừng test.
- Chặn tác động tới tenants ngoài scope.
- Đặt guardrails cho quorum, data integrity và disk capacity.
- Không đồng thời chạy migration/compaction/recovery nguy hiểm nếu không chủ đích.
- Có cách khôi phục network rules, process config và service ownership.
- Đảm bảo telemetry không ghi secrets/PII.

**Không bắt đầu bằng kill random nodes trên production** chỉ vì đã có ba replicas. Tính an toàn phụ thuộc replica placement, quorum, lỗi đã tồn tại và hành vi ứng dụng.

## 16. Workload kiểm thử phải có hoạt động đang chạy

Một bài test chỉ thực hiện:

~~~text
Stop primary.
Wait for leader election.
Check cluster HEALTHY.
~~~

không kiểm thử được câu hỏi **“request in-flight sẽ ra sao?”**. Cần tạo tải liên tục trước khi inject fault:

- **Foreground writes**: create Order, reserve stock, update status.
- **Conditional writes**: compare-and-set dựa trên source version.
- **Read-after-write**: ngay sau khi POST ACK, GET cùng ID.
- **Long-running reads**: pagination, aggregation hoặc snapshot cursor có giới hạn.
- **Transaction**: nhiều documents/items nếu engine hỗ trợ.
- **Background workers**: consume queue, outbox dispatch, scheduled jobs.
- **Mixed workload**: reads/writes ratio và hot partitions giống thực tế.
- **Slow operations**: transaction đủ dài để failover thật sự cắt ngang.

Phải sinh **operation ID và expected invariant** cho mỗi request để biết kết quả đúng sau khi hệ phục hồi. Nếu chỉ bắn load không lưu expected outcomes, test có thể đo p99 nhưng không đo duplicate hoặc lost acknowledged writes.

## 17. Workload model: tỷ lệ, concurrency và phân phối khóa

Một cấu hình thử nghiệm minh họa:

~~~yaml
workload:
  durationMinutes: 20
  targetOperationsPerSecond: 600
  concurrentClients: 80
  operations:
    createOrder: 15
    conditionalReserve: 20
    updateOrder: 15
    getOrderAfterWrite: 25
    catalogRead: 15
    paginatedRead: 10
  keyDistribution:
    hotKeySharePercent: 30
  requestDeadlineMs: 1200
  stableOperationId: true
~~~

Các tỷ lệ là **phần trăm giả định**, không áp cho sản phẩm cụ thể. Với load test thực tế cần tách **arrival rate** với **concurrency** và xác định cách tải được phát khi server chậm: closed-loop client có thể giảm request rate tự nhiên, che giấu outage; open-loop generator có thể duy trì offered load nhưng cần giới hạn để không gây nguy hiểm.

Cần có cả:

- Cold cache và warm cache.
- Hot keys/partitions.
- Mixed small/large documents.
- Cross-node reads/writes.
- Peak concurrency và low-volume latency-sensitive flows.
- Transaction contention.
- Connection pool saturation gần ngưỡng.

Không phát tải vượt nguồn lực môi trường thử nghiệm chỉ để tạo lỗi không còn đại diện cho production.

## 18. Fault injection matrix theo pha của request

Một ma trận bắt buộc:

| Điểm chèn lỗi | Ví dụ | Kết quả cần xác minh |
|---|---|---|
| Trước gửi command | Kill API pod | Không tạo effect; retry cùng intent an toàn |
| Khi driver gửi request | Cắt network client→DB | UNKNOWN được ghi nhận và đối soát |
| Sau khi DB nhận, trước commit | Crash primary | Atomicity/conditional semantics |
| Sau commit, trước ACK | Drop response/kill leader | Không tạo effect thứ hai khi retry |
| Sau DB ACK, trước HTTP response | Kill API pod | HTTP retry trả result ổn định |
| Trong election | Đổi network leader/replica | Retry budget, server-selection, no split brain |
| Khi replica còn lag | Route read tới replica mới | Read-your-writes/staleness đúng policy |
| Khi transaction còn mở | Trigger step-down/quorum loss | Commit outcome/retry đúng |
| Khi worker có lease | Pause worker rồi failover | Old token bị fence |
| Khi outbox đang publish | Broker/worker lỗi | Event không mất/không duplicate effect |
| Sau network heal | Cho replicas kết nối lại | Không conflict/corruption ngoài model |
| Khi failover lặp liên tục | Flapping/quorum churn | Backoff, circuit breaker, bounded queues |

**Fault timing rất khó khớp chính xác khi chỉ dùng sleep timer.** Nên có hooks/observability/fault proxy để đồng bộ kịch bản với sự kiện đã gửi request, đã commit hoặc đang chờ ACK khi môi trường cho phép.

## 19. Đồng bộ thời điểm chèn lỗi với một request cụ thể

Một test deterministic hơn test ngủ ngẫu nhiên:

~~~text
1. Start transaction/request K1.
2. Wait until test harness receives "command sent" event.
3. Trigger target failure according to scenario.
4. Observe driver/API response and commit evidence.
5. Allow failover/recovery.
6. Query authoritative state by operation ID.
7. Retry K1 if scenario requires.
8. Assert final count/effects/invariants.
~~~

Với lỗi “sau commit nhưng trước ACK”, có thể dùng **application-controlled response interception** hoặc proxy mô phỏng drop ACK *sau khi* test harness nhận commit evidence. Không phải mọi engine expose hook trực tiếp vào thời điểm commit. Nếu không thể đồng bộ chính xác, ghi rõ **khả năng đã xảy ra pha nào** thay vì tự tuyên bố đã test ACK-loss path.

Một số framework fault injection hỗ trợ network proxy hoặc test seam, nhưng quyền, cú pháp và side effects phụ thuộc công cụ. Cần dùng test doubles cho hành vi khó chèn ở storage thật, rồi có một lớp thử nghiệm tích hợp phù hợp để đo failover end-to-end.

## 20. Fault injection nên tác động đúng failure domain

| Target | Cách mô phỏng có kiểm soát | Cần thận trọng |
|---|---|---|
| API process | Restart một instance đang xử lý | Load balancer retries và duplicate |
| DB primary | Planned step-down hoặc kill process trong test cluster | Quorum, transaction recovery |
| Network path | Proxy/drop/delay/partition riêng giữa nodes | Stale TCP, effects tới test clients |
| Disk | Inject latency/fault qua môi trường hỗ trợ | Data corruption, cleanup |
| Worker | Suspend rồi resume khi lease hết | Fencing ở downstream |
| Zone | Ngắt một fault domain được giả lập | Replica placement và đủ majority |
| Driver | Simulate server selection timeout, pool exhaustion | Phân biệt driver/DB issue |
| Broker/outbox | Chặn publish/consumer ACK | Dedup, reconciliation |

**Không phá toàn bộ node ngẫu nhiên rồi suy hệ ổn**: nếu topology đã suy giảm, một fault thêm có thể đưa cụm vào tình trạng cần restore. Scope an toàn và stop conditions phải được kiểm trước kịch bản.

## 21. Instrumentation: theo dõi request xuyên failover

Mỗi operation nên ghi (không chứa PII/secret thô):

~~~json
{
  "traceId": "trace-opaque-7",
  "operationId": "intent-K1",
  "businessType": "RESERVE_STOCK",
  "clientAttempt": 2,
  "apiInstance": "api-3",
  "driverEndpoint": "node-B",
  "serverTopologyEpoch": "generation-8",
  "requestState": "UNKNOWN",
  "elapsedMs": 1030,
  "sourceVersion": 17,
  "retryReason": "transport-timeout"
}
~~~

Các trường phụ thuộc hệ. Nên ghi và liên kết:

- Operation ID và stable idempotency key reference.
- Attempt count: **logical intent** vs **physical DB attempt**.
- Host/role/generation mà driver đã dùng.
- Client/server errors và deadline.
- Commit/status/ledger lookup result.
- Transaction ID/session nếu có thể log an toàn.
- Exact injected fault/correlation marker.
- Event/outbox IDs nếu có external side effects.

Phân biệt **request result ở HTTP** với **commit status ở DB**. Không suy “500 errors=lost writes”; một số write có thể đã commit.

## 22. Đo thời gian failover theo mốc

Ví dụ:

~~~text
T0 fault starts
T1 old primary stops accepting writes
T2 election/ownership decided
T3 driver discovers new topology
T4 first new write acknowledged correctly
T5 p99 and error rate return within SLO
T6 replicas/CDC/search fully caught up
~~~

Các chỉ số riêng:

- **Election/role transition time**: T2−T0.
- **Client reconnect time**: T3−T0.
- **Write availability recovery**: T4−T0.
- **User-facing recovery**: T5−T0.
- **Data convergence**: T6−T0, nếu contract yêu cầu.

T2 nhanh không bảo đảm T4/T5 nhanh: client pools có thể giữ endpoints cũ, retries có thể thành bão và caches lạnh. T6 có thể lâu hơn vì replica resync/rebuild, dù API đã phục vụ thành công.

## 23. RPO, RTO và acknowledged-write safety trong failover

RPO và RTO có thể liên quan bài test, nhưng không thay assertion nghiệp vụ.

- **RPO:** lượng dữ liệu được phép mất theo recovery contract.
- **RTO:** thời gian cần để khôi phục chức năng theo service definition.
- **Acknowledged-write safety:** những writes đã được trả success theo durability contract có còn sau failover? Đây có thể là điều kiện nghiêm ngặt hơn một RPO chung.
- **Data freshness:** replica/read model mới nhất tới mốc nào?
- **Availability SLO:** tỷ lệ/time window các requests đúng được phục vụ.
- **Correctness:** không oversell/duplicate, transaction boundary hợp lệ.

Giả sử team công bố RPO tối đa 1 phút ở disaster recovery nhưng **API đơn hàng cam kết không mất payment đã ACK**. Không thể dùng RPO một phút như lý do làm mất acknowledged payment record nếu contract nghiệp vụ không cho phép.

## 24. Bảo vệ phép đo tải khỏi coordinated omission

Khi hệ tạm dừng 20 giây, một load generator **closed-loop** có thể ngừng gửi request mới vì tất cả clients đang chờ. Nếu chỉ tính latency của requests đã hoàn thành, phần outage có thể bị che.

Thực hành:

- Ghi **offered request rate** và completed request rate.
- Ghi latency từ **scheduled start/arrival** tới result, không chỉ server execution time nếu mục tiêu là trải nghiệm.
- Ghi timeouts/errors/never-completed requests trong thống kê.
- Xác định concurrency cap và queue time.
- Báo cáo p50/p95/p99 + max + error rate + downtime.
- Chia biểu đồ theo trước/trong/sau fault; không chỉ average cả bài.
- Đo traffic mix/hot-key distribution, không chỉ tổng QPS.

Một biểu đồ “p99=100ms trên 100 requests thành công” không có ý nghĩa nếu 40% requests bị timeout và bị loại khỏi thống kê.

## 25. Thiết kế test oracle: quyết định đúng/sai từ trạng thái nghiệp vụ

**Test oracle** là tập quy tắc xác minh kết quả cuối cùng, không chỉ so HTTP 200/500:

~~~text
Observed:
  1,000 submitted business intent IDs.
  965 HTTP success responses.
  35 timeouts.
  980 distinct committed intents in authoritative ledger.
  1,000 client final states reconciled.

Oracle must ask:
  Are all 965 acknowledged intents present?
  Are there any duplicate effects for one intent?
  Which 35 timeouts actually committed?
  Are any committed intents missing a durable result?
  Do stock/order/payment invariants hold?
~~~

Một test có thể cho phép 35 timeouts trong failover window nhưng vẫn **không cho phép mất một write đã ACK hoặc tạo hai kết quả cho một intent**. Phải tách **service availability acceptance** và **data safety acceptance**.

Đối soát cần có:

- Expected intent set do test generator giữ ngoài hệ đang thử.
- Attempt count và HTTP result cho từng intent.
- Durable status/result ledger ở nguồn có thẩm quyền.
- Actual resource versions/IDs/balances.
- External side effects nếu có.
- Read-after-write checks sau khi replicas hội tụ.
- Danh sách UNKNOWN chưa phân giải, không tự coi tất cả là FAILED.

## 26. Java: cấu trúc một giao diện kiểm thử failover

Mẫu dưới đây dùng interface để tách workload, injection và verification; **không phải bộ test chạy được ngay** vì chưa có engine-specific adapters, infra control và các class triển khai:

~~~java
import java.time.Duration;
import java.util.List;

public record Intent(
    String operationId,
    String tenantId,
    String targetKey,
    long expectedVersion,
    long delta) {}

public enum CallStatus {
    ACKNOWLEDGED, REJECTED, UNKNOWN
}

public record AttemptResult(
    String operationId,
    int attemptNumber,
    CallStatus status,
    String errorCode,
    Duration elapsed) {}

public interface NoSqlWorkload {
    AttemptResult submit(Intent intent, int attemptNo);
    List<AttemptResult> observedAttempts();
}

public interface FaultController {
    void injectAt(FaultPoint point) throws Exception;
    void recover() throws Exception;
}

public enum FaultPoint {
    BEFORE_SEND,
    REQUEST_IN_FLIGHT,
    AFTER_COMMIT_BEFORE_ACK,
    DURING_FAILOVER,
    AFTER_LEADER_ELECTION
}

public interface ConsistencyOracle {
    void verifyAcknowledgedIntentsExist(
        List<AttemptResult> results) throws Exception;

    void verifyNoDuplicateBusinessEffect(
        List<Intent> intents) throws Exception;

    void verifyBusinessInvariants() throws Exception;
}
~~~

Ở phần triển khai thật, `FaultController` phải có **scope, safety budget, stop conditions**; `ConsistencyOracle` phải đọc trạng thái theo consistency phù hợp thay vì chỉ query một replica eventual vừa failover. Mỗi kịch bản phải xác minh cleanup của fault và khả năng dùng lại môi trường.

## 27. Java: retry logic giữ nguyên business intent

Một mô hình minh họa:

~~~java
public interface OperationGateway {
    CommitResult executeWithIdempotencyKey(
        String operationId,
        byte[] canonicalPayload) throws Exception;

    CommitResult lookupCommittedResult(
        String operationId) throws Exception;
}

public record CommitResult(
    String operationId,
    String businessObjectId,
    boolean committed) {}

public final class IntentExecutor {
    private final OperationGateway gateway;

    public IntentExecutor(OperationGateway gateway) {
        this.gateway = gateway;
    }

    public CommitResult submit(String operationId, byte[] payload)
            throws Exception {
        try {
            return gateway.executeWithIdempotencyKey(
                operationId, payload);
        } catch (TransientTransportException ambiguous) {
            // Timeout is not a definitive rollback.
            CommitResult existing =
                gateway.lookupCommittedResult(operationId);
            if (existing != null && existing.committed()) {
                return existing;
            }
            // Only retry if the gateway enforces the same
            // idempotency identity atomically with the write.
            return gateway.executeWithIdempotencyKey(
                operationId, payload);
        }
    }
}
~~~

Đây là **pseudocode Java**, với `TransientTransportException` là kiểu minh họa chưa khai báo. Trong thực tế:

- Lookup trả “chưa thấy” từ replica stale **không chứng minh write chưa commit**.
- Có thể cần trạng thái PENDING/UNKNOWN và bounded reconciliation.
- Retry phải dùng **cùng operationId/fingerprint**.
- Không retry vô hạn, phải tôn trọng request deadline và throttle budget.
- Business conflict và authorization failure không phải transient transport errors.
- Engine hỗ trợ transaction/retryable writes có semantics riêng cần dùng đúng.

Nếu ledger không atomically coupled với effect, đoạn logic không có bảo đảm idempotency dù tên method nghe thuyết phục.

## 28. Java: phép thử lưu kết quả rồi kiểm trạng thái sau sự cố

Một test design:

~~~java
public record TestExpectation(
    String operationId,
    String expectedBusinessKey,
    long maximumAllowedEffects) {}

public interface ResultRepository {
    long countEffectsForIntent(String operationId)
            throws Exception;
    boolean acknowledgedRecordExists(String operationId)
            throws Exception;
}

public final class FailoverAssertions {
    private final ResultRepository repository;

    public FailoverAssertions(ResultRepository repository) {
        this.repository = repository;
    }

    public void assertAfterRecovery(
            TestExpectation expected,
            boolean wasAcknowledged) throws Exception {
        long effects = repository.countEffectsForIntent(
            expected.operationId());

        if (effects > expected.maximumAllowedEffects()) {
            throw new AssertionError("Duplicate business effect");
        }

        if (wasAcknowledged &&
                !repository.acknowledgedRecordExists(
                    expected.operationId())) {
            throw new AssertionError("Acknowledged write missing");
        }
    }
}
~~~

Ví dụ nhấn mạnh cách đặt assertions: **đếm effect theo ý định**, không theo số lần client gọi. Với checkout, test oracle còn phải kiểm stock≥0, mỗi reservation một owner, payment state được đối soát và không có event khó truy ra.

**Cần đọc nguồn authoritative sau khi đã biết trạng thái cluster và consistency contract**, không dùng một stale read tức thời để kết luận mất dữ liệu.

## 29. Fault-injection controller không được trở thành nguồn rủi ro mới

Một orchestration test cần:

~~~text
SETUP:
  capture baseline and verify target topology
  register fault scope and deadline
  create synthetic business intents

RUN:
  start bounded concurrent load
  wait for selected event
  inject one fault
  record exact timestamps and client/server responses
  recover fault and await cluster readiness

VERIFY:
  stop new load
  reconcile intent/result ledger
  verify business and consistency invariants
  measure SLI and recovery
  release locks, network rules, test data
~~~

Controls cần có:

- Time-to-live cho iptables/proxy/network fault.
- Recovery in `finally` hoặc cơ chế cleanup độc lập.
- Explicit allowlist of target nodes/processes.
- Không đồng thời inject nhiều lỗi ngoài experiment design.
- Safety abort khi quorum đã giảm hoặc unknown effects tăng bất thường.
- Tách quyền vận hành test khỏi application DB superuser nếu có thể.
- Không dùng destructive disk corruption trên dữ liệu production.

Fault được dừng không có nghĩa mọi node đã catch up. **Cleanup hoàn tất khi topology, traffic và safety signals đã được xác minh**.

## 30. Các giai đoạn một test: baseline, fault, recovery, steady state

~~~mermaid
flowchart LR
    B["Baseline under load"] --> F["Fault window"]
    F --> R["Failover recovery"]
    R --> S["Steady-state observation"]
    S --> V["Business result reconciliation"]
~~~

Trong từng giai đoạn nên đo:

| Giai đoạn | Trọng tâm |
|---|---|
| Baseline | p99/errors ổn, source/replica health, tải đại diện |
| Fault window | Unknown outcomes, request timeouts, rejected writes |
| Recovery | Leader election, reconnect, retry storm, queue backlog |
| Steady state | Quorum/replication/CDC, throughput, tail latency |
| Reconciliation | No lost acknowledged intent, no duplicates, business invariants |

Nếu chỉ đo đến khi election hoàn thành, sẽ bỏ lỡ **post-failover thundering herd** và cold-cache/resource pressure. Nếu chỉ đo steady state, sẽ bỏ lỡ sai lệch nghiệp vụ tại thời điểm ACK mất.

## 31. Connection pool và retry storm sau khi leader đổi

Giả sử:

~~~text
20 API pods
100 max DB connections/pod
3 retries per logical request
Database leader changes
All pods reconnect nearly simultaneously
~~~

Potential connections có thể tới 2.000; physical attempts có thể lớn hơn logical requests nhiều lần nếu retry đồng loạt. Không phải mọi connection cùng active, nhưng rủi ro **connection churn + TLS handshakes + queue amplification** là thật.

Kiểm thử nên theo dõi:

- Active/idle/waiting pool connections.
- Time to discover new primary/coordinator.
- Connection creation/handshake errors.
- Attempts per logical intent.
- Backoff/jitter/total request deadlines.
- CPU/network và throttling của server mới.
- Retry amplification giữa app, SDK, service mesh và load balancer.
- Cancellation: client đã timeout thì server còn làm việc không?
- Queued work có vượt concurrency budget không?

**Nhiều tầng cùng retry** có thể khuếch đại request mà từng tầng đều tưởng “chỉ retry vài lần”. Đánh giá retry budget end-to-end và không hạ consistency để giảm queue theo phản xạ.

## 32. Circuit breaker và backpressure trong failover

Một circuit breaker có thể bảo vệ API và DB khỏi retry storm, nhưng nếu cấu hình sai nó có thể giữ hệ ở trạng thái open lâu sau khi cluster đã phục hồi.

Các câu hỏi:

1. Tín hiệu nào mở breaker: timeouts, connection errors, throttles?
2. Có phân biệt business rejection với transient failure?
3. Thời gian open/half-open có phù hợp failover window không?
4. Probe half-open có overload leader mới không?
5. Queues có bound về size và age?
6. Caller có nhận trạng thái rõ ràng, không bị ACK sai?
7. Write with UNKNOWN outcome được quản lý thế nào trong khi breaker open?
8. Read-only degraded path có bảo đảm quyền và freshness không?

Circuit breaker **không sửa dữ liệu đã bị lặp**; nó giới hạn thêm rủi ro availability/load. Idempotency và conditional writes vẫn phải tồn tại.

## 33. MongoDB: replica set election và in-flight writes

Trong MongoDB replica set, primary có thể step down hoặc mất kết nối, driver phải tìm primary mới. Tùy write concern/read concern, topology, engine/driver version:

- Write đang gửi tới primary cũ có thể gặp network/server-selection error.
- Driver có thể hỗ trợ **retryable writes** cho những thao tác và điều kiện nhất định; không phải mọi lệnh đều cùng bảo đảm.
- Transaction nhiều documents có session/commit semantics riêng.
- Write chưa được ACK ở mức durability đủ mạnh có thể có visibility khác sau failover.
- Secondary read có thể stale.
- Cursor, long-running query và transaction có thể bị gián đoạn.
- Change streams có thể cần resume theo token và oplog window.

| Kịch bản | Assertion |
|---|---|
| Primary step-down trong create Order | Một intent tạo tối đa một Order |
| Crash sau acknowledged write ở mức phù hợp | Record còn trên primary mới |
| Timeout khi commit transaction | Không tự tạo duplicate effect |
| Secondary lag, GET sau POST | Giữ read-your-writes theo hợp đồng |
| Election lặp lại | Retry budget, reconnect, no split brain |
| Old primary trở lại | Không có hai authoritative primary |

### 33.1. Retry transaction khác retry commit

Một số MongoDB drivers hỗ trợ transaction errors với labels liên quan **transient transaction error** hoặc **unknown transaction commit result**. Tùy driver/version, phương án có thể là retry transaction callback hoặc retry/resolve commit result. Không tự mở transaction mới tạo Order lần nữa khi commit cũ còn UNKNOWN.

~~~text
Begin transaction.
Write Order + durable idempotency record.
Attempt commit.

If commit SUCCESS:
  return stored result.

If retryable transaction error per driver contract:
  retry transaction safely with same intent.

If commit outcome UNKNOWN:
  resolve/retry commit per driver protocol;
  reconcile stable operation ID if necessary.
~~~

Lệnh/thư viện cụ thể phải theo docs driver đang dùng, không lấy pseudo-flow này làm implementation production.

### 33.2. Test acknowledged write

1. Chọn write concern đúng theo business durability contract.
2. Ghi Order có operation ID, nhận ACK, giữ source version trong test harness.
3. Trigger primary failover theo công cụ hỗ trợ.
4. Read trên primary mới với read semantics phù hợp.
5. Xác minh ACKed record/version còn tồn tại.
6. Đối soát mọi in-flight UNKNOWN operation.
7. Đo reconnect/election/p99/errors và replica lag.

**Không kết luận record bị mất chỉ vì một secondary eventual read chưa thấy nó.**

## 34. Cassandra/ScyllaDB: coordinator failover và consistency levels

Trong wide-column cluster, coordinator xử lý request nhưng data nằm trên các replicas. Coordinator chết không nhất thiết nghĩa write chưa được replicas áp dụng.

~~~text
Client -> Coordinator C1 -> Replicas R1,R2,R3
R1,R2 apply the mutation.
C1 loses network before responding.
Client retries through C2.
~~~

Điểm cần thử:

- Consistency level sử dụng thực tế; local/quorum/all semantics theo topology.
- Write ACK loss dù replicas đã áp update.
- Timestamp/LWW conflict và clock skew.
- Counter/TTL/tombstone operations, không coi tất cả mutation idempotent.
- Lightweight transaction/CAS và conditional conflicts.
- Speculative execution/retry policy của driver.
- Hinted handoff/repair và divergence sau network heal.
- Hot-partition behavior khi recovery.

Một `SET` cùng key/value có thể tương đối dễ retry trong một mô hình nhất định, nhưng increment, append hoặc mutation gắn timestamp có thể có semantics khác. **Cần chứng minh idempotency cho statement và business effect cụ thể**.

### 34.1. Test qua các consistency modes thật

1. Xác định replication factor/DC/rack placement thực tế.
2. Chạy write theo consistency mà app đang dùng.
3. Chèn fault coordinator trước ACK và đối soát replicas.
4. Thử read trên coordinator khác tại consistency đúng.
5. Chèn failure làm một số replicas unavailable.
6. Xác minh kết quả business và error classification.
7. Sau hồi phục, chờ repair/convergence theo engine.
8. So latest state/tombstones/version với expected oracle.

Một bài test dùng consistency yếu hơn production để giữ QPS **không chứng minh hành vi production**.

## 35. DynamoDB: quản lý service-level failover thông qua API

Với DynamoDB managed, người dùng không trực tiếp tắt storage primary nội bộ để thử. Thay vào đó test **những lỗi mà client nhìn thấy**:

- Endpoint/network timeout, request throttling và transient errors.
- Concurrent conditional writes trên cùng item.
- Transaction APIs và token idempotency trong scope hỗ trợ.
- Read consistency theo từng table/index/API.
- Hot partition và retry/backoff.
- Region routing khi dùng global tables hoặc kiến trúc đa vùng.
- Application retries khi HTTP client nhận response không đầy đủ.

Một transaction/request token của provider có thể giúp idempotency **trong khoảng thời gian được tài liệu hóa**, không nhất thiết thay durable business ledger lâu dài.

Kịch bản:

~~~text
1. Send conditional ReserveStock with stable operation ID.
2. Inject timeout after dispatch.
3. Retry using same identity/token under API contract.
4. Read authoritative item/version with suitable consistency.
5. Confirm exactly one reserve/decrement per intent.
6. Measure throttling, backoff, retries and total deadline.
~~~

Không tự phát minh quyền kill DynamoDB storage process bên trong dịch vụ managed. Với thử nghiệm region/network, giới hạn fault ở application/endpoint layer mà team có thể kiểm soát.

## 36. Redis: failover, asynchronous replication và locks

Với Redis Sentinel/Cluster hoặc một deployment dùng replication bất đồng bộ, có thể xảy ra trường hợp primary cũ ACK write rồi mất trước khi replica nhận write. Kết quả phụ thuộc persistence, replication mode, failover và contract ứng dụng.

Cần thử:

- Primary mất sau ACK nhưng replica chưa áp write.
- Redis client còn kết nối old endpoint.
- Sentinel/Cluster cập nhật topology và reconnect.
- AOF/RDB persistence/restart behavior.
- TTL, eviction làm idempotency key hoặc session biến mất.
- Hot keys, connection churn và timeout storms.
- Worker lease expired nhưng old worker tiếp tục effect.

Nếu Redis chỉ là **cache**, đo miss storm lên NoSQL durable source và khả năng fallback. Nếu Redis giữ authoritative business state, cần yêu cầu durability/recovery riêng, không coi replication là không mất ACKed writes.

### 36.1. Redis lock không thay fencing downstream

~~~text
A acquires lock L.
A loses connection and pauses.
Lock L expires, B acquires it.
B updates protected DB record.
A resumes and also updates the DB record.
~~~

Nếu downstream DB không kiểm tra fencing token hoặc conditional version, hai effects có thể cùng xảy ra. **Đối tượng test là effect nghiệp vụ được bảo vệ, không chỉ key L có tồn tại hay không.**

## 37. Search, cache và dữ liệu dẫn xuất khi nguồn failover

Với Elasticsearch/OpenSearch, Redis cache hoặc read model tự xây:

- CDC có thể pause/resume sau leader election.
- Consumer có thể nhận lại event sau khi restart.
- Search index có thể chưa thấy record được source ACK.
- Delete/privacy suppression có thể đến muộn.
- Cache có thể giữ stale version.
- Cache warm-up có thể tăng đột biến read QPS lên database vừa hồi phục.

Một bài thử:

1. Commit Order ở authoritative DB, giữ source version.
2. Failover ngay lúc outbox/CDC đang publish.
3. Read source và read projection theo **hai hợp đồng riêng**.
4. Xác minh duplicate events không tạo duplicate effect.
5. Test delete/tombstone và replay event cũ.
6. Đo freshness lag, API p99 và load tới source.
7. Chờ hội tụ trong freshness budget nếu service đã cam kết.

**Không dùng search index eventual làm nguồn quyết định duy nhất cho tiền, số lượng ghế cuối hoặc quyền truy cập** nếu data model không có bảo đảm phù hợp.

## 38. Transaction nhiều bước và saga khi có lỗi

Một checkout có thể gồm:

~~~text
1. Reserve inventory in NoSQL.
2. Create Order in NoSQL.
3. Write OutboxEvent.
4. Publish event to broker.
5. Capture payment externally.
6. Mark Order CONFIRMED and notify.
~~~

Nếu failover xảy ra giữa các bước, có thể còn trạng thái PENDING hoặc COMPENSATING. Điều đó có thể hợp lệ trong **saga** nếu workflow có durable state, retry/compensation và idempotency.

| Failure window | Trạng thái có thể xảy ra | Recovery path |
|---|---|---|
| Sau reserve, trước Order | Stock bị giữ, Order chưa có | Resume/compensate |
| Sau Order, trước outbox | Missing event nếu không atomic | Outbox repair |
| Sau publish, trước mark sent | Event phát lại | Consumer dedup |
| Sau payment, trước DB ACK | Charge thực, Order UNKNOWN | Provider reconciliation |
| Sau CONFIRMED, trước HTTP | User thấy timeout | Return stable intent result |
| Worker pause hết lease | Two workers try same effect | Storage fencing/CAS |

**DB transaction không tự bao gồm payment/broker/email bên ngoài**. Test phải xem đủ business workflow.

## 39. Outbox/inbox và event delivery trong failover

~~~text
DB commits Order + OutboxEvent E1.
Dispatcher publishes E1.
Broker acknowledges E1.
Dispatcher dies before marking sent.
New dispatcher publishes E1 again.
~~~

At-least-once event delivery có thể tạo duplicate events. Để giữ business effects:

- Gắn stable event IDs.
- Ghi outbox bền cùng source transaction khi khả thi.
- Consumer dedup/inbox state được bảo vệ cùng effect.
- Offset/checkpoint chỉ advancing theo protocol sau khi effect xử lý an toàn.
- Retried event có thể áp lại hoặc trả result cũ mà không nhân effect.
- Reconcile publish UNKNOWN và DLQ theo IDs.

**Exactly-once business effect** không tự xuất hiện chỉ vì broker/SDK có retry setting.

## 40. Payment bên ngoài không rollback khi database failover

~~~text
DB stores Order PENDING.
Payment provider captures charge.
API crashes before saving CAPTURED.
Client retries checkout after failover.
~~~

Nếu retry với một provider intent ID khác, có thể charge hai lần. Cần stable provider reference, business idempotency ledger, lookup/reconciliation với provider, bounded retries và compensation khi phù hợp.

Test dùng payment sandbox/synthetic provider, không chạy charge thật. Assert không duplicate charge, không orphaned payment, và Order cuối cùng có state hợp lệ.

## 41. Ma trận phép thử và safety assertions

| Kịch bản | Availability có thể giảm | Assertion bắt buộc |
|---|---|---|
| Primary crash trước dispatch | Có | Không effect |
| Commit rồi mất ACK | Có | Same intent, ≤1 effect |
| Step-down giữa transaction | Có | Atomicity + unknown handling |
| Replica lag khi read | Có thể | Read contract được giữ |
| Mất majority/quorum | Có | Không ACK success trái durability |
| Worker cũ resume | Có | Stale token bị reject |
| Redis cache failover | Có | Source integrity, bounded misses |
| CDC consumer restart | Có thể | No lost event/business duplicate |
| Broker ACK mất | Có | Idempotent publish/consume |
| Region routing change | Có | RPO/consistency contract |
| Repeated leader election | Có | Retry bounded/no overload |
| Long cursor disconnect | Có | Pagination/snapshot semantics |
| Concurrent CAS | Có | Conditional invariant |
| TLS reconnect failure | Có | Không bypass authentication |

Mỗi testcase nên có expected intents, source events, driver/API outputs, thực tế sau reconciliation và timestamps tương quan.

## 42. Lỗi được phân loại theo ý nghĩa, không chỉ theo HTTP status

- **Business rejection**: precondition failed/unauthorized/invalid request → không retry như transient.
- **Transport unavailable**: route/network timeout → bounded retries với same intent.
- **Unknown commit**: đã gửi write, mất ACK → tra ledger/reconcile.
- **Conflict**: version thay đổi → đọc current state, áp policy; không blindly retry.
- **Throttling**: backoff jitter và concurrency/rate budget.
- **Configuration failure**: TLS/schema/permissions sai → alert/stop, không retry vô tận.

Một HTTP 500 **không có nghĩa DB chưa commit**. Một API 200 không được tự công bố “Order đã lưu bền” khi DB chưa đạt mức ACK mà hợp đồng yêu cầu.

## 43. Runbook kiểm thử failover khi writes đang chạy

**Preflight**

1. Chốt invariants, SLO, acceptable failures, expected durability.
2. Check cluster health, quorum, replica placement và lag.
3. Ghi driver retry/timeout/pool, read/write settings.
4. Tạo synthetic intents có stable operation IDs.
5. Bật telemetry API/driver/DB và baseline dashboard.
6. Chuẩn bị fault scope, deadline, rollback và người chịu trách nhiệm.

**Fault**

7. Chạy mixed reads/writes/concurrent transactions.
8. Inject fault đúng phase mục tiêu.
9. Ghi election, reconnect, timeout và source commit events.
10. Không tạo new business intent khi retry UNKNOWN.
11. Dừng nếu hard guardrails bị vi phạm.

**Recovery và reconcile**

12. Restore process/network, chờ cluster health/quorum theo policy.
13. Đo first successful new write và time to recover p99.
14. Reconcile every ACK/UNKNOWN operation ID.
15. Kiểm business invariants, payments/outbox/CDC state.
16. Test read-your-writes, deleted records và replica lag.
17. Lưu report, root-cause candidates, retry/connection metrics.
18. Cleanup fault/test artifacts theo policy.

Một test pass cần **chứng cứ về dữ liệu cuối cùng**, không chỉ trạng thái cluster sau restart.

## 44. Hard stop conditions

Dừng test khi:

- Quorum/replication đã suy giảm ngoài failure budget.
- Hai leaders/writers cùng nhận commit trái protocol.
- Acknowledged business write có dấu hiệu bị mất.
- Duplicate charge, oversell hoặc invalid state được phát hiện.
- Lỗi tenant authorization/PII.
- Backup/recovery không khả dụng.
- Disk, repair backlog hoặc memory tăng vượt giới hạn.
- Retry storm ảnh hưởng tenants/workloads ngoài scope.
- Fault controller không khôi phục được network/process theo deadline.
- Người vận hành không còn nắm quyền kiểm soát blast radius.

Sau dừng: ngăn fault mới, containment, bảo toàn evidence, phục hồi và reconciliation. Không xóa anomalies trước khi thu thập dữ liệu điều tra.

## 45. Kịch bản thực hành A — Primary crash ngay trước commit

**Mục tiêu:** Xác minh atomicity/conditional integrity khi primary mất đúng lúc một write hoặc transaction đang xử lý.

Giả định:

~~~text
Initial:
  stock(SKU-A) = 1
  no reservation R1 exists

Requests:
  K1 reserves one unit
  K2 concurrently reserves one unit
~~~

Thực hiện:

1. Thiết lập đúng replication/consistency settings được dùng trong production.
2. Bắt đầu K1, K2 với **operation IDs riêng**.
3. Chèn primary step-down/crash trong cửa sổ sau dispatch, trước commit nếu test seam cho phép.
4. Ghi lỗi ở app/driver và statuses UNKNOWN.
5. Chờ failover và thực hiện reconciliation trên nguồn có thẩm quyền.
6. Retry cùng K1/K2 theo idempotency contract nếu cần.
7. Đọc stock và reservation records bằng consistency phù hợp.
8. Kiểm tra invariants.

**PASS** nếu tối đa một reservation hợp lệ được xác nhận, stock không âm, không mất acknowledged write, mọi UNKNOWN được truy ra hoặc ghi rõ pending. **FAIL** nếu cả K1 và K2 cùng được confirmed cho một đơn vị, hoặc caller nhận success nhưng không có durable effect theo cam kết.

Không đánh dấu “test lỗi vì API có timeout” nếu availability SLO cho phép timeout ngắn mà mọi data safety assertion vẫn đạt; ngược lại không đánh dấu pass chỉ vì đã bầu leader.

## 46. Kịch bản thực hành B — Commit xong nhưng ACK bị mất

**Mục tiêu:** Tấn công chính khoảng trống giữa thực tế database và phản hồi caller.

~~~text
T0: Send K1 create Order.
T1: DB commits K1 and stored result O1001.
T2: Fault proxy blocks response after commit.
T3: Client receives timeout.
T4: Failover selects another DB endpoint.
T5: Client retries same K1.
~~~

Điều cần đo:

- Số physical DB attempts và logical intents.
- Status ledger K1 ở authoritative store sau failover.
- Số Order rows/documents có cùng business intent.
- Số payment/provider effects nếu workflow có.
- API trả result O1001 hay tạo O1002.
- Độ trễ từ timeout tới result ổn định.

**PASS:** K1 có đúng một business outcome, retry không đổi fingerprint, user có thể nhận lại kết quả hoặc trạng thái PENDING có thể đối soát. **FAIL:** hai Orders/charges hoặc ledger không thể trả lời commit result theo deadline chính sách.

Nếu không có fault seam chặn ACK thật, có thể dùng API proxy/test gateway mô phỏng response loss nhưng phải ghi rõ **test không chứng minh storage commit fault window hoàn toàn tương đương**.

## 47. Kịch bản thực hành C — Election lặp dưới tải cao

Giả định một cluster phải bầu lại primary hai lần trong cửa sổ ngắn, app đang ở 70–90% công suất bình thường.

Các hiện tượng cần quan sát:

- Connection pool đóng/mở hàng loạt.
- Topology cache cũ khiến driver chọn node không còn là primary.
- Retries xếp hàng và tăng request load.
- Error-budget burn tăng dù DB đã có leader mới.
- API deadlines hết trong khi server vẫn xử lý work cũ.
- Cache misses tăng sau reconnection.
- Jobs background tranh tài nguyên với foreground.

Thử:

1. Ghi baseline offered load/completed load, p99, active connections.
2. Chèn first failover tại T0.
3. Chờ khoảng quan sát định nghĩa, không chèn lỗi thứ hai khi vượt safety budget.
4. Chèn second failover theo phạm vi đã duyệt.
5. Đo time-to-first-write, time-to-p99-recovery sau mỗi lần.
6. Theo dõi retry attempts per logical request.
7. Chạy reconciliation toàn bộ intents có ACK/timeout.
8. Chờ replica/CDC catch up rồi xác minh health.

**PASS** không chỉ là “hệ cuối cùng ổn”; hệ phải không lost acknowledged write, không duplicate effect, và backpressure/retry budget tránh làm lỗi lan rộng. Nếu phần downtime vượt SLO, ghi availability failure dù data correctness đạt.

## 48. Kịch bản thực hành D — Transaction dài và cursor nhiều trang

Đặt một transaction hoặc read cursor chạy trong khi cluster đổi primary:

~~~text
Long transaction:
  Read Order O1001.
  Update multiple related records.
  Commit after simulated delay.

Cursor:
  Page through report with stable sort key.
  Failover between page 5 and page 6.
~~~

Test questions:

- Transaction bị abort/retry ở scope nào?
- Caller biết commit result hay UNKNOWN?
- Driver tự retry operation nào, callback có side effects không?
- Cursor có còn hợp lệ sau server switch?
- Resume token/page key có thể dùng lại không?
- Read snapshot có giữ cùng logical cut không?
- Một sort không có stable tie-breaker có tạo duplicate/missing rows không?

Để oracle đáng tin, test harness giữ expected IDs/version tại mốc snapshot được định nghĩa. Nếu database không hỗ trợ snapshot cursor xuyên failover, **hành vi hợp lệ có thể là trả lỗi/restart report có kiểm soát**, chứ không phải lặng lẽ ghép pages từ hai snapshots và tuyên bố hoàn chỉnh.

## 49. Kịch bản thực hành E — Network partition và client ở phía minority

Một network partition tách cụm:

~~~text
Side A: nodes N1, N2 (may have quorum)
Side B: node N3 (minority)
Client X connected to N3
Client Y connected to N1
~~~

Phải xét theo engine/replication semantics:

1. Cụm có leader/quorum nào hợp lệ?
2. N3 có cho phép write ACK trái contract không?
3. Client X có tự chuyển endpoint hay retry vô hạn?
4. Read ở N3 có stale, có bị chặn theo policy không?
5. Có tình huống old worker vẫn tưởng giữ lease?
6. Khi heal partition, data có cần repair/rollback không?
7. Những acknowledged writes trước partition có còn?
8. Có log/audit nào thể hiện ownership transition?

Không suy minority luôn từ chối mọi operation trên mọi NoSQL; nhiều engine có consistency options và eventual models khác nhau. **Test phải dùng đúng consistency settings đang công bố**, và đánh giá kết quả theo hợp đồng.

## 50. Kịch bản thực hành F — Worker lease hết nhưng operation vẫn chạy

Giả định một worker xử lý job tính phí giao hàng:

~~~text
T0: Worker A gets task J, fencing token 101.
T1: A starts slow external workflow and pauses.
T2: Lease expires.
T3: Worker B receives task J, token 102.
T4: B commits final result.
T5: A resumes and attempts final result.
~~~

Cần test:

- Downstream conditional write từ A với token 101 có bị từ chối?
- B có dùng same job ID/idempotency key?
- External provider có provider reference ổn định?
- Một operation đã phát ra bên ngoài không thể rollback có bị chạy hai lần?
- Kết quả job có đúng source version và tenant owner?
- Queue ACK/checkpoint được ghi khi nào?
- Một token cũ có thể làm ghi đè value mới không?

Nếu chỉ có Redis lock/lease mà downstream không enforce fencing, test này có thể phát hiện bug **ngay cả khi database cluster không hề hỏng**. Đó là lý do failover testing phải bao gồm worker handoff.

## 51. Kịch bản thực hành G — Failover khi backup, repair hoặc index build đang chạy

Một cluster đang làm việc nền nặng thường có ít headroom:

- Backup logical scan tiêu read IOPS.
- Compaction/repair tiêu disk/network.
- Index build tăng write amplification.
- CDC backfill cạnh tranh với queries.
- Hot partitions đang gần capacity.
- Failover khiến cache lạnh và replicas resync.

Kịch bản:

1. Chạy workload foreground với load đại diện.
2. Bắt đầu một background task được hỗ trợ và có throttle.
3. Ghi baseline disk/network/CPU/replica lag.
4. Trigger failover một member trong phạm vi được phép.
5. Theo dõi API p99/error budget, replication, disk free.
6. Kiểm tra background job pause/resume/retry semantics.
7. Xác minh không phá backup chain hoặc index correctness.
8. Reconcile transaction intents sau failover.
9. Dừng nếu free space/quorum/repair backlog vượt guardrail.

**Không cố làm cluster hết disk để “tăng độ khó”** khi chưa có môi trường cô lập/khôi phục. Mục tiêu là đo failure under realistic contention, không phải tạo lỗi không liên quan.

## 52. Mẫu report cho một thử nghiệm failover

~~~yaml
experimentId: failover-inflight-001
environment: isolated-staging
engine: example-nosql
topology: three-replica
scenario: drop-commit-ack-during-primary-failover
timeWindow:
  baselineStart: "T-300s"
  faultStart: "T0"
  firstNewWriteAck: "T+18s"
  stableSloRecovered: "T+31s"
workload:
  offeredOps: 12000
  acknowledgedIntents: 11600
  unknownOutcomes: 210
  businessRejections: 190
dataSafety:
  acknowledgedWritesMissing: 0
  duplicateBusinessEffects: 0
  unresolvedUnknownAfterReconcile: 0
service:
  p99MsDuringFault: 1100
  errorBudgetBurn: "measured-separately"
recovery:
  replicaLagBackToBaseline: "T+48s"
  faultCleanupVerified: true
result:
  dataCorrectness: PASS
  availability: REVIEW_AGAINST_SLO
owner: reliability-team
~~~

Các giá trị chỉ minh họa format. Một kết quả **dataCorrectness PASS** có thể đồng thời có **availability FAIL** nếu SLO bị vi phạm. Report phải giữ evidence: operation IDs, commit ledger comparison, error classification, telemetry và fault injection marker. Không chỉ chụp ảnh bảng điều khiển cuối cùng.

## 53. Những hiểu nhầm thường gặp khi thử failover

| Hiểu nhầm | Vì sao sai | Cách tiếp cận |
|---|---|---|
| “Leader mới lên là test pass” | In-flight writes có thể chưa đối soát | Business oracle |
| “Timeout nghĩa chưa commit” | ACK có thể mất sau commit | UNKNOWN + reconciliation |
| “Retry là gửi lại với ID mới” | Có thể duplicate effects | Stable intent ID/fingerprint |
| “Batch luôn atomic” | Có thể partial success | Xác minh atomicity scope |
| “Transaction nghĩa caller luôn biết commit” | Commit response có thể mất | Commit-outcome protocol |
| “Secondary read luôn mới” | Replica lag | Read consistency checks |
| “Quorum giống nhau ở mọi NoSQL” | Engine, topology, policy khác | Test actual consistency mode |
| “Mọi CQL statement idempotent” | Counters/timestamps khác | Evaluate statement and effect |
| “Managed NoSQL không gặp transient errors” | Network/throttle/timeout vẫn có | Client-visible fault tests |
| “Redis replication luôn giữ ACKed writes” | Async replica lag | Durability contract |
| “Redis lock chặn stale worker” | Old worker có thể tiếp tục | Downstream fencing |
| “Retry transaction callback luôn an toàn” | Callback có thể gọi provider | External effects separated |
| “At-least-once là không duplicate” | Consumer có thể nhận lại | Inbox/idempotent effects |
| “HTTP 500 nghĩa DB không ghi” | DB có thể commit | Ledger lookup |
| “p99 thấp nghĩa availability tốt” | Timed-out requests có thể bị loại | Offered load + errors |
| “Chạy chaos càng mạnh càng tốt” | Tăng blast radius ngoài ý định | Bounded failure budget |
| “Retry nhiều là tăng reliability” | Retry storms | Bounded backoff/jitter |
| “Election time bằng RTO” | API/client còn chưa hoạt động | Time to usable service |
| “So record count là đủ” | Không thấy duplicate/side effects | Business invariants |
| “Failover read không liên quan security” | Stale permissions/deletes | Security freshness |
| “Một lần test pass là đủ” | Driver/topology/config thay đổi | Regression suite |

## 54. Bài tập A — Ghế cuối và primary failover

Cho hệ:

~~~text
Available seats = 1
Customer A: reserve 1, operation K1
Customer B: reserve 1, operation K2
Both requests overlap.
Primary fails while operations are in flight.
Driver retries K1 after failover.
~~~

Yêu cầu:

1. Chọn conditional update/transaction bảo vệ stock.
2. Đặt idempotency key riêng cho K1 và K2.
3. Phân biệt conflict do ghế đã hết với timeout hệ thống.
4. Đề xuất fault injection trước commit và sau commit–trước ACK.
5. Đo election, reconnect, retries và API p99.
6. Tạo oracle kiểm stock không âm và chỉ một reservation.
7. Nếu K1 commit trước khi mất ACK, retry phải trả gì?
8. Khi GET từ replica lag, test cần điều kiện đọc nào?
9. Nêu các hard stop conditions.
10. Báo cáo PASS/FAIL riêng cho data correctness và availability.

## 55. Bài tập B — DB failover và payment provider

Kịch bản:

~~~text
1. Order CREATED in NoSQL.
2. Payment capture request sent with provider reference P1.
3. Payment provider returns SUCCESS.
4. API crashes before recording CAPTURED.
5. Database primary fails over.
6. Client retries checkout.
~~~

Hãy:

1. Nêu business intent ID cần bền qua restart.
2. Vì sao retry với payment reference P2 có thể gây lỗi?
3. Khi nào cần tra provider thay vì gọi capture lại?
4. Thiết kế state machine PENDING/CAPTURED/UNKNOWN/REFUND_PENDING.
5. Outbox/inbox hỗ trợ những bước nào?
6. Đặt cách reconcile external outcome với NoSQL ledger.
7. Test worker crash sau publish nhưng trước event checkpoint.
8. Đo số charge thực, Orders và compensation.
9. Xác định API response khi provider outcome chưa rõ.
10. Thiết kế test dùng provider sandbox thay tiền thật.

## 56. Bài tập C — Đọc một report failover

Giả định:

| Metric | Quan sát |
|---|---|
| Submitted intents | 10.000 |
| HTTP 2xx | 9.400 |
| Business conflicts | 200 |
| Timeouts/5xx | 400 |
| Distinct committed intent IDs | 9.560 |
| Duplicate business effects | 4 |
| ACKed intent missing after recovery | 1 |
| UNKNOWN unresolved | 20 |
| Election duration | 12 giây |
| Time to first valid new write | 19 giây |
| Time to p99 back in SLO | 53 giây |

Hãy:

1. Có thể tuyên bố data correctness PASS không?
2. Vì sao election 12 giây không phải user recovery 12 giây?
3. Trong 400 timeouts, bao nhiêu có thể đã commit?
4. ACKed missing 1 có thể là stale read không? Làm sao xác minh?
5. Duplicate effect count 4 cần điều tra gì?
6. Conflict 409 có nên tính giống lỗi transient không?
7. Nếu SLO cho phép 30 giây degraded, 53 giây là gì?
8. UNKNOWN chưa phân giải cần lưu, alert và owner ra sao?
9. Cần thêm metrics gì về replica lag, retry, outbox, payments?
10. Đề xuất report có data safety status và availability status riêng.

**Một suspected acknowledged loss hoặc duplicate business effect là hard blocker đối với kết luận an toàn dữ liệu**, ngay cả khi cụm đã hồi phục nhanh.

## 57. Câu hỏi tự kiểm tra

1. Primary failover khác coordinator reroute thế nào?
2. Vì sao cluster HEALTHY chưa chứng minh API an toàn?
3. Những thời điểm nào tạo UNKNOWN commit outcome?
4. Timeout có đồng nghĩa transaction rollback không?
5. Acknowledged write và HTTP response khác nhau ra sao?
6. Request chưa gửi và request mất ACK có được retry giống nhau không?
7. Idempotency key gắn với attempt hay business intent?
8. Fingerprint của intent bảo vệ điều gì?
9. Vì sao ledger phải đủ durable?
10. Retry có thể lặp side effect ngoài DB ở đâu?
11. Conditional write giữ invariant thế nào?
12. Batch API có luôn all-or-nothing không?
13. Atomic transaction có loại unknown commit không?
14. Durability khác read visibility ra sao?
15. Replica lag có thể tạo false 404 thế nào?
16. Read-your-writes cần route/token/consistency gì?
17. Pagination cursor chịu failover ra sao?
18. Quorum loss có thể khiến write unavailable vì sao?
19. Hạ consistency có thể phá hợp đồng nào?
20. Old worker sau pause có rủi ro gì?
21. Fencing token phải được kiểm tra tại đâu?
22. Driver retry khác business retry thế nào?
23. Bounded retry và jitter có tác dụng gì?
24. Circuit breaker có sửa duplicate writes đã xảy ra không?
25. Open-loop và closed-loop load generator khác nhau thế nào?
26. Coordinated omission làm p99 báo cáo sai ra sao?
27. Fault timing cần đồng bộ với event nào?
28. Test oracle cần dữ liệu nào ngoài HTTP response?
29. Acknowledged-write safety khác RPO chung như thế nào?
30. Election duration khác time-to-usable-service ra sao?
31. MongoDB unknown transaction commit cần xử lý gì?
32. Cassandra coordinator crash có nghĩa replicas chưa ghi không?
33. LWT/CAS giúp ngăn double reservation thế nào?
34. DynamoDB managed vẫn cần thử những lỗi client nào?
35. Redis lock không thay fencing vì sao?
36. Outbox publisher chết sau publish gây gì?
37. Consumer dedup/inbox bảo vệ business effect thế nào?
38. DB failover có rollback payment capture không?
39. Cache failover có thể tạo source read storm không?
40. Thử nghiệm phải dừng khi thấy tín hiệu nào?
41. Vì sao after-failover reconcile cần đọc source authority?
42. Có thể kết luận mất dữ liệu bằng stale replica read không?
43. Vì sao fault injection phải có cleanup/owner?
44. Khi nào phải chạy lại regression test suite?
45. Vì sao data correctness PASS chưa chắc SLO PASS?

## 58. Tổng kết: failover phải bảo vệ kết quả nghiệp vụ

**Failover là kiểm thử cả liveness và safety.** Một cụm có thể bầu primary mới rất nhanh nhưng requests đang chạy có kết quả chưa rõ, driver retries tạo bão kết nối, replica đọc stale, hoặc event/payment effects bị lặp. Vì vậy các bài thử cần bao phủ **commit boundary, network ACK, client retry, replica visibility, worker lease và side effects ngoài NoSQL**.

Chu trình thực hành:

~~~text
1. Viết business invariants và durability/consistency contract.
2. Xác định topology, quorum, read/write modes và failure domains.
3. Sinh mixed workload có stable intent IDs và in-flight operations.
4. Chèn lỗi trước, trong và sau commit/ACK.
5. Giới hạn blast radius, duration, load và hard stop.
6. Ghi chung timeline API, driver, DB, nodes và replicas.
7. Dùng idempotency, conditional write và fencing ở đúng boundary.
8. Kiểm thử retries, connection pools, circuit breaker/backpressure.
9. Xử lý UNKNOWN qua durable ledger và reconciliation.
10. Test read-your-writes, transaction atomicity và external effects.
11. Đo election, reconnect, API SLO và data convergence riêng.
12. Sau recovery, kiểm acknowledged writes, duplicates và invariants.
13. Lưu evidence, báo data safety/availability riêng.
14. Lặp lại khi driver, topology, schema hoặc retry policy thay đổi.
~~~

**Nguyên tắc cốt lõi:** *Failover chỉ được coi là an toàn khi mọi yêu cầu đã được xác nhận vẫn giữ kết quả nghiệp vụ theo hợp đồng, những yêu cầu chưa rõ được đối soát mà không nhân đôi hiệu ứng, và dịch vụ trở lại trong giới hạn đã cam kết.* Bằng chứng quan trọng nằm trong trạng thái dữ liệu sau phục hồi, không chỉ trong việc một node mới đã lên.











