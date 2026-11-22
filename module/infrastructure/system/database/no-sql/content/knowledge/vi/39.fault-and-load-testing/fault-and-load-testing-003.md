# Ngắt kết nối, mất gói, độ trễ cao và phân hoạch mạng

Một hệ thống đặt chỗ dùng Java 21 ghi booking vào cơ sở dữ liệu NoSQL, cập nhật tồn kho và tạo sự kiện cho một read model tìm kiếm. Trong điều kiện bình thường, một API trả HTTP 201 sau 80 ms. Khi một liên kết giữa ứng dụng và database chập chờn, request mất 3 giây rồi timeout. Phía client không nhận được câu trả lời, nhưng có thể database đã ghi booking thành công. Nếu client thử lại với một ID mới, người dùng có nguy cơ có **hai booking**. Nếu ứng dụng cho rằng timeout chắc chắn là rollback, nó có thể báo thất bại sai. Nếu retry quá nhiều đồng thời, cụm database vừa chập chờn có thể bị đánh sập bởi **retry storm**.

Ở một thí nghiệm khác, hai trong ba replica còn nhìn thấy nhau nhưng replica thứ ba bị cô lập. Cụm có thể vẫn chấp nhận một số thao tác trong phía đa số, trong khi những clients kết nối phía thiểu số thấy lỗi hoặc dữ liệu cũ. Khi kết nối được phục hồi, việc phục hồi replica, phát lại change log và dựng lại chỉ mục có thể tiếp tục tạo tải lớn dù network đã bình thường.

Bài thuộc **Database No SQL → Kiểm thử lỗi và tải**, hướng dẫn cách kiểm tra có kiểm soát bốn nhóm trục trặc mạng:

1. **Ngắt kết nối:** đóng socket, reset kết nối, ngắt route, không thể thiết lập hoặc duy trì connection.
2. **Mất gói:** một tỷ lệ gói không đến được đích; có thể tạo retransmission và tail latency.
3. **Độ trễ cao:** tăng RTT, jitter, queueing và timeout mà kết nối vẫn có vẻ hoạt động.
4. **Phân hoạch mạng:** các nhóm nodes/services không thể liên lạc với nhau theo một số hướng, trong khi vẫn hoạt động cục bộ.

Mục tiêu không chỉ là xem service “có sống không”, mà còn chứng minh **bất biến dữ liệu, hành vi nhất quán, độ trễ, tính khả dụng theo từng thao tác, retry/idempotency và khả năng hồi phục**. Bài sử dụng ví dụ Java 21, MongoDB, Cassandra, DynamoDB, Redis và search/CDC, các fault injectors như Toxiproxy hoặc Linux tc/netem trong môi trường thử nghiệm, cùng ma trận test, runbook và bài tập.

> **Nguyên tắc:** Khi network lỗi, kết quả phía client thường có ba trạng thái: **thành công đã được xác nhận**, **thất bại chắc chắn theo contract**, hoặc **chưa xác định (UNKNOWN)**. Đừng gộp timeout/lost ACK vào rollback. Mỗi tình huống phải kiểm tra cả **phản hồi HTTP, trạng thái authoritative sau lỗi, side effects, khả năng replay/reconcile và metrics**.

> **An toàn thí nghiệm:** Chỉ inject faults trong cluster và network namespace đã được phép, có phạm vi, thời hạn, điều kiện dừng và người chịu trách nhiệm rõ ràng. Không áp tc/firewall/network partition lên máy dùng chung hoặc production ngoài quy trình chaos engineering được phê duyệt. Các lệnh và JSON ví dụ là hướng dẫn thử nghiệm, không phải mặc định cấu hình cho mọi môi trường.

## 1. Kiểm thử lỗi mạng khác kiểm thử tải thông thường

**Kiểm thử tải** đưa một mức yêu cầu có kiểm soát vào hệ, quan sát throughput, latency, saturation, errors.

**Kiểm thử lỗi** thay đổi một hoặc nhiều giả định của hệ như:
- Kết nối giữa hai tiến trình tồn tại.
- Gói request/response đến đúng thời gian.
- Một replica nhìn thấy những writes mới.
- Heartbeat giữa nodes đến kịp.
- Leader và followers có thể liên lạc.
- CDC consumers đọc được log.
- Kết nối từ API tới dependency còn thông suốt.

Khi kết hợp hai loại, ta có **fault-under-load test**: bắt đầu tải nền, inject fault, theo dõi degradation, recovery, backlog catch-up, rồi xác minh dữ liệu.

### 1.1. Câu hỏi đúng

Không hỏi duy nhất:
- Cụm vẫn có một node khỏe không?
- Driver có tự reconnect không?
- Có bao nhiêu request trả HTTP 200?

Hãy hỏi:
- Booking nào đã được tạo dù client timeout?
- Có booking trùng logical operationId không?
- Inventory có bị trừ hai lần không?
- Có hai write owners trong cùng epoch không?
- Read của cùng phiên có bị lùi version?
- Phía nào của partition có quyền trả kết quả?
- Dữ liệu ở replica/search index có hội tụ không?
- Sau hồi phục, tail latency và retry queue ổn định trong bao lâu?
- Có đáp ứng RPO/RTO, availability và freshness SLO theo contract không?

### 1.2. Thuật ngữ chính

- **Availability theo thao tác:** tỷ lệ read/write hợp lệ có thể hoàn thành trong deadline, không nhất thiết bằng node health.
- **Safety:** những điều không bao giờ được xảy ra, ví dụ không double booking hay lùi version.
- **Liveness:** hệ tiếp tục tiến triển, ví dụ một request hợp lệ cuối cùng có thể commit khi đủ quorum.
- **Consistency:** quan hệ các reads/writes có được phép quan sát, theo guarantee của engine và API.
- **Durability:** một write đã được xác nhận sẽ tồn tại theo điều kiện storage/replication đã công bố.
- **Recovery:** quá trình trở về trạng thái phục vụ, replica catch-up, repair, index rebuild, queue drain.
- **Steady state:** mức tải và latency ổn định trước fault.
- **Blast radius:** số tenants/requests/nodes chịu ảnh hưởng.

## 2. Phân biệt bốn loại lỗi mạng

| Lỗi | Mô tả | Quan sát phía client | Nguy cơ điển hình |
| --- | --- | --- | --- |
| Ngắt kết nối | Socket đóng/reset hoặc không thể kết nối | Connection refused/reset, socket error | Lost ACK; reconnect storm |
| Mất gói | Một phần TCP/IP packets bị drop | Retransmission, RTT/p99 tăng, deadline | Head-of-line blocking, retry |
| Độ trễ cao | Kênh hoạt động nhưng chậm/jitter | Slow reads/writes, timeouts | Queue buildup, stale responses |
| Phân hoạch mạng | Nhóm nodes không liên lạc theo hướng cụ thể | Chỉ một nhóm reachable; leader election/quorum loss | Unavailable ops, stale reads, split-brain nếu fencing sai |

### 2.1. Ngắt kết nối không đồng nghĩa mất gói ngẫu nhiên

Ngắt socket ngay:
- Client có thể nhận lỗi sớm.
- Driver có thể tạo connection mới.
- Request đang bay có thể đã tới server.
- Response có thể bị mất.

Mất 1% gói TCP:
- Connection có thể vẫn mở.
- TCP retransmits che một số losses.
- Tail latency tăng không tuyến tính.
- Timeout xuất hiện dù lỗi không có dạng reset rõ ràng.

### 2.2. Delay không đồng nghĩa partition

Tăng độ trễ 200 ms có thể:
- Khiến heartbeat trễ.
- Làm driver đánh dấu node unavailable.
- Gây election/failover tùy cơ chế.
- Làm queue tăng.

Nhưng hai phía vẫn có thể trao đổi messages nếu deadlines cho phép. Partition thực sự là tình huống mất reachability cho ít nhất một số cặp/hướng giao tiếp trong window.

### 2.3. Network partition có thể không đối xứng

Ví dụ:
- A không gửi được đến B, nhưng B vẫn gửi được tới A.
- Client thấy database, nhưng database callback tới client không thấy.
- Node1 nhìn Node2, Node2 không nhìn Node1.
- Cross-zone replication bị ngắt trong khi client→primary vẫn được.

Test chỉ “tắt toàn bộ network” không thay thế asymmetric partition hay one-way response loss.

### 2.4. Layer mạng quan trọng

Một lỗi có thể nằm ở:
- DNS resolution.
- TCP connect.
- TLS handshake.
- Established socket.
- Request write.
- Server request processing.
- Server response.
- Load balancer/network proxy.
- Cross-region replication.
- Storage/object store dependency.

Cùng thông báo timeout có thể xuất phát từ những pha rất khác. Fixture cần nêu rõ pha fault.

## 3. Mô hình một request ghi

~~~~mermaid
sequenceDiagram
    participant C as Java client
    participant D as NoSQL leader/owner
    participant R as Replicas
    C->>D: Write operationId=OP-91
    D->>D: Validate + apply/commit
    D->>R: Replicate / quorum protocol
    R-->>D: Acks according to policy
    D--xC: ACK lost on network
    Note over C: Timeout; commit state UNKNOWN
    C->>D: Reconcile by operationId
    D-->>C: Canonical committed result
~~~~

Một timeout ở client **không chứng minh** server chưa làm gì. Có các trường hợp:

1. Request chưa gửi được byte nào.
2. Request gửi một phần, server không parse đủ.
3. Server nhận request nhưng chưa commit.
4. Server commit rồi ACK bị drop.
5. Server commit vào leader nhưng replication/durability chưa đạt mức ACK mong muốn.
6. Server hoàn thành và response đến quá muộn, sau khi client đã hết deadline.
7. Driver retry ngầm khiến một logical operation có nhiều physical attempts.

### 3.1. Outcome taxonomy

| Outcome | Điều kiện quan sát được | Điều nên làm |
| --- | --- | --- |
| CONFIRMED_SUCCESS | ACK với contract rõ | Trả canonical result; tiếp tục theo workflow |
| CONFIRMED_REJECTION | Validation/conditional conflict chắc chắn không commit | Trả lỗi có ngữ nghĩa |
| UNKNOWN | Deadline, lost ACK, connection reset trong window mơ hồ | Reconcile authoritative state/operation ledger |
| TEMPORARY_UNAVAILABLE | Không có quorum/leader hoặc route | Retry có giới hạn hoặc fail fast |
| STALE_READ | Read chưa thấy version đã commit | Theo contract: wait/fallback/retry, không tự coi source write failed |

### 3.2. ACK có nhiều nghĩa

Tùy database, ACK có thể là:
- Đã nhận request.
- Đã áp dụng in-memory.
- Đã ghi WAL.
- Đã fsync/durable ở một node.
- Đã replicate tới một số nodes.
- Đã commit theo một quorum.
- Đã visible ở index/search.

Không dùng một tiêu chí chung “HTTP 200 = durable ở mọi region”. Test phải dựa vào write concern, consistency level, transaction protocol hoặc provider documentation của thao tác đó.

### 3.3. Read-after-write

Khi write ACK rồi đọc ngay qua:
- Follower.
- Secondary index.
- Global secondary index.
- Search index.
- Cache.

có thể thấy version cũ nếu contract eventual. Test cần biết nguồn đọc và bảo đảm đã cam kết, không áp một oracle strong consistency cho read model eventual.

## 4. CAP: không rút gọn thành “chọn hai trong ba”

Khi có network partition, một hệ phân tán không thể đồng thời thỏa **linearizability theo nghĩa C trong định lý CAP** và **availability cho mọi request tới node không lỗi theo nghĩa A**, trong mô hình và giả định của định lý. Nhưng việc gắn nhãn “CP database” hay “AP database” không quyết định ngay mọi endpoint:

- Write cần quorum có thể unavailable ở phía thiểu số.
- Read local/eventual có thể vẫn phục vụ ở một node.
- Administrative/read-only operations có behavior riêng.
- Một session có minVersion có thể từ chối stale read.
- Leaderless conflict resolution có tradeoffs khác leader-based.
- Trong tình huống không partition, latency/consistency cũng có đánh đổi (thường thảo luận bằng PACELC).

### 4.1. Test theo từng operation và guarantee

Không assert “cụm Cassandra phải available” mà không nói:
- Read hay write?
- Consistency level?
- Replication factor?
- Số replica reachable?
- Có coordinator nào?
- Deadline?
- Repair/hinted handoff?
- Request có idempotency không?

Tương tự với MongoDB, Redis, DynamoDB: cấu hình và endpoint ảnh hưởng behavior.

### 4.2. R + W > N không phải tấm vé universal

Bất đẳng thức quorum overlap có ích trong một số mô hình nhưng không tự bảo đảm linearizability:
- Replica membership có thể thay đổi.
- Handoff/caches/replication delay.
- Sloppy quorum hoặc topology specifics.
- Clock/lease/election semantics.
- Read repair, conflict reconciliation.
- Cross-region eventual replication.

Dùng guarantee chính thức của engine/config thực tế làm oracle.

## 5. Fault model trước khi chạy

Một bản thiết kế fault cần ghi:

~~~~yaml
scenarioId: nosql-net-partition-553-01
scope:
  environment: isolated-test-cluster
  source: api-node-a
  destination: db-node-c
  direction: client-to-server
fault:
  kind: packet-loss
  lossPercent: 15
  durationSeconds: 45
workload:
  readsPerSecond: 120
  writesPerSecond: 30
  tenantDistribution: skewed
  seed: 553001
invariants:
  - noDuplicateBookingForSameOperationId
  - noNegativeInventory
  - noCrossTenantRead
  - monotonicSourceVersion
recovery:
  removeFaultAfterSeconds: 45
  verifyUntilSeconds: 180
abort:
  - sustainedUnexpectedDataCorruption
  - testEnvironmentEscapesIsolation
~~~~

Số liệu chỉ là ví dụ, không phải giá trị an toàn mặc định. Thí nghiệm cần có:
- Fault owner.
- Thời điểm bắt đầu/kết thúc.
- Recovery/unwind command.
- Baseline.
- Assertions.
- Telemetry.
- Abort criteria.

### 5.1. Mô hình theo cạnh mạng, không chỉ theo node

Một cluster có nhiều đường:
- API ↔ primary.
- API ↔ secondary.
- Primary ↔ secondary.
- Coordinator ↔ replicas.
- Region A ↔ Region B.
- CDC source ↔ broker.
- Broker ↔ projection consumer.
- Database ↔ KMS/object storage/control plane.

Lỗi trên mỗi cạnh có behavior khác. Một proxy đặt giữa API và DB không nhất thiết tái hiện partition nội bộ giữa các DB nodes.

### 5.2. Kiểm tra tầng nào bị inject

Nếu proxy chỉ xử lý TCP connections mới:
- Existing pooled connections có thể bypass proxy.
- DNS cache có thể giữ route cũ.
- Load balancer có thể chuyển request sang node khác.
- Retry logic có thể né đường fault.

Đo **fault thực sự tác động tới traffic nào** trước khi kết luận hệ chịu lỗi tốt.

## 6. Thiết kế baseline có ý nghĩa

Trước fault, chạy đủ lâu để ổn định:
- Offered request rate theo từng operation.
- Completed throughput.
- p50/p95/p99 latency.
- Error rate.
- Driver pool utilization/queue wait.
- Replica lag.
- CDC lag.
- Leader election health.
- CPU, memory, network retransmissions.
- Partition/hot key distribution.
- Source/version correctness.

### 6.1. Bằng chứng về dữ liệu

Tạo fixtures có:
- Hai tenants có cùng logical bookingId nếu contract cho phép.
- Booking inventory với một slot còn lại.
- Một document version 4 để hai writers cạnh tranh.
- Duplicate operationId.
- Một DELETE tombstone v7.
- Source v8 và projection v7.
- Read model/search index có lag theo contract.

Không chỉ đo QPS trên dữ liệu ngẫu nhiên; cần **bất biến cho biết đúng/sai**.

### 6.2. Thực hiện fault khi tải đang ổn định

Ví dụ:
1. Warm-up.
2. Baseline 2 phút.
3. Inject fault 45 giây.
4. Remove fault.
5. Observe recovery 3 phút.
6. Reconcile.
7. Record result.

Độ dài là mẫu. Nếu SLO/timeout/replication cycle khác, phải điều chỉnh theo hệ thực.

### 6.3. Tải nền và thao tác đặc biệt

Duy trì hỗn hợp:
- Point reads.
- Range/page reads.
- Conditional booking writes.
- Cancel/confirm.
- CDC events.
- Cache access.
- Search queries.

Đồng thời bắn một số operations có ID theo dõi riêng để đối soát sau fault.

## 7. Ngắt kết nối: những pha cần kiểm tra

### 7.1. Trước khi thiết lập connection

Fault:
- DNS không resolve.
- TCP connection refused.
- Connect timeout.
- TLS handshake fail.

Oracle:
- Service không treo vô hạn.
- Có giới hạn connect timeout.
- Cấu hình pool không tạo vô số connect attempts.
- Trả lỗi retryable theo contract.
- Không ghi dữ liệu nếu request thực sự chưa đến source.

### 7.2. Đang truyền request

Fault xảy ra sau khi client mở socket:
- Byte stream có thể chưa đủ request.
- Có thể driver đã send đầy đủ.
- Không chắc server có parse/commit.

Test outcome UNKNOWN nếu không có bằng chứng rejection chắc chắn.

### 7.3. Sau khi server commit, trước khi trả ACK

Đây là fixture quan trọng:
- Server ghi thành công.
- Proxy drop/reset response.
- Client timeout.
- Client retry cùng operationId.
- Kỳ vọng chỉ **một logical booking**.

### 7.4. Sau khi ACK về client

Ngắt kết nối sau ACK kiểm tra:
- Driver reconnect cho read tiếp theo.
- Server durable guarantee đúng.
- Read preference/fallback behavior.
- Mất connection không được đảo một write đã xác nhận.

### 7.5. Socket half-open

Một chiều bị mất nhưng TCP chưa báo lỗi ngay:
- Requests có thể chờ timeout.
- Pool có thể giữ connections tưởng còn sống.
- Health check chưa phát hiện.
- Thread/queue có thể bị giữ lại.

Test cần đo deadline, pool exhaustion và recovery time, không chỉ error rate.

## 8. Mất gói: từ retransmission đến tail latency

Mất gói thường không tạo một lỗi “packet lost” trực tiếp ở ứng dụng Java dùng TCP. TCP có thể:
- Retransmit.
- Thay congestion window.
- Tăng RTT hiệu dụng.
- Gây head-of-line blocking.
- Kéo dài cả kết nối.
- Dẫn đến timeout ở tầng application.

### 8.1. Test rates có kiểm soát

Các mức minh họa:
- 0% baseline.
- 0.1% loss.
- 1% loss.
- 5% loss.
- Burst loss 10% trong 5 giây.
- 100% loss trên một hướng để mô phỏng blackhole.

Không chỉ test random uniform loss; nhiều sự cố thực có **bursty losses**.

### 8.2. Packet loss và TCP vs UDP

NoSQL clients thường dùng TCP, nhưng một số hệ dùng thêm UDP/control protocols. Toxiproxy chủ yếu thao tác stream/proxy ở tầng TCP; muốn mô phỏng loss ở tầng IP hoặc các giao thức khác có thể cần netem/network namespaces. Không đồng nhất “proxy ngắt stream” với “mất x% IP packets”.

### 8.3. Metrics đặc trưng

- TCP retransmits.
- Reset/timeouts.
- RTT variation.
- Connection attempts.
- In-flight requests.
- End-to-end p99/p999.
- Pool saturation.
- Retry rate.
- Server requests per logical operation.
- Egress/ingress traffic.

### 8.4. Không kết luận chỉ từ trung bình latency

Nếu p50=40 ms nhưng p99=5.000 ms, user experience và retry storm có thể rất tệ. Báo tail latency và timeout fraction dưới mỗi mức loss.

## 9. Độ trễ cao: budget của một request

Giả sử API có deadline 1.200 ms. Một request phải đi qua:
- API parsing/auth.
- DB request.
- Retry có thể có.
- Cache/search call.
- Response serialization.

Nếu DB request có timeout 2.000 ms thì đã dài hơn toàn bộ API deadline; retries có thể vượt budget.

### 9.1. Timeout theo lớp

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| Connect timeout | 200 ms | Hạn chế chờ mở socket |
| Pool acquisition timeout | 100 ms | Hạn chế queue chờ connection |
| Per attempt deadline | 600 ms | Chặn một attempt quá dài |
| Overall operation deadline | 1.000 ms | Chặn cả retry chain |
| HTTP request deadline | 1.200 ms | Client-visible budget |
| CDC catch-up bound | 5 s | Freshness contract |

Số liệu minh họa. Cấu hình cụ thể phải dựa trên latency distribution và driver semantics; một số driver không có từng option theo đúng tên trên.

### 9.2. Deadline nên truyền xuyên các lớp

Nếu API còn 300 ms, dependency call không nên chờ 1.000 ms. Cần:
- Deadline/cancellation propagation.
- Không launch retry khi không đủ budget.
- Không chờ vô hạn một future đã hết hữu ích.
- Stop background retries trùng lặp nếu operation complete.
- Kiểm soát timeout ở connection pool.

### 9.3. Queueing và overload

Khi network chậm:
- In-flight requests tăng.
- Connection pool đầy.
- Thread/virtual-thread count tăng.
- Queue latency tăng.
- Timeouts tạo retries.
- Retries làm tăng offered load.
- Cụm vừa hồi phục bị backlog dồn vào.

Thí nghiệm phải đo cả độ trễ do mạng và độ trễ do **tải phản hồi lên chính hệ thống**.

### 9.4. Jitter và độ trễ bất đối xứng

Một request 5 ms chiều đi + 700 ms chiều về khác với 700 ms chiều đi + 5 ms chiều về:
- Server commit timing.
- Client observed timeout.
- Heartbeat/election responses.

Test cả upstream/downstream khi proxy hỗ trợ, hoặc route mạng hai chiều có kiểm soát.

## 10. Phân hoạch mạng: quorum, leader và split-brain

Ví dụ ba database nodes A, B, C. Một partition chia A và (B,C):

~~~~mermaid
flowchart LR
    subgraph Minority["Nhóm 1"]
        A["DB A"]
    end
    subgraph Majority["Nhóm 2"]
        B["DB B"]
        C["DB C"]
        B <--> C
    end
    A -.-x B
    A -.-x C
~~~~

Đây là hình minh họa. Hành vi thực phụ thuộc consensus/quorum và deployment.

### 10.1. Những câu hỏi cần test

- Leader đang ở A hay B?
- Quorum size thực tế là bao nhiêu?
- Nhóm A có tiếp tục nhận writes không?
- B,C có bầu leader mới không?
- Clients kết nối A có được redirect/fail fast không?
- Những writes đã ACK có còn sau election?
- Nếu old leader quay lại, nó có bị fenced khỏi ghi tiếp không?
- Replica catch-up có tạo write/read latency spike không?

### 10.2. Safety vs availability

Một hệ ưu tiên linearizable writes có thể từ chối writes ở phía thiểu số. Đây có thể là **đúng contract**, không phải lỗi. Một hệ cho local writes ở nhiều phía có thể phải giải quyết conflicts; test phải đánh giá conflict policy và business invariants.

### 10.3. Split-brain

Split-brain có thể xảy ra khi hai phía đều tin mình là write authority:
- Stale leader.
- Expired lease không được xác minh.
- Fencing thiếu.
- DNS/routing lỗi.
- Manual failover chồng lấn.

Tạo một **authority epoch/generation** hoặc cơ chế fencing được engine/app hỗ trợ. Không chỉ kiểm tra UI có chữ LEADER.

### 10.4. Bảo đảm cross-region

Cross-region replication thường có độ trễ và conflict semantics khác intra-region quorum. Một region bị partition:
- Local writes có thể tiếp tục hoặc bị chặn.
- Remote state stale.
- Global uniqueness có thể khó hơn.
- Failover cần dữ liệu/operation reconciliation.

Không suy một global strong guarantee nếu provider chỉ hứa eventual replication.

## 11. Ma trận partitions cần thử

| Case | Mất reachability | Câu hỏi |
| --- | --- | --- |
| App ↔ DB primary | App không tới leader | Driver re-route? Writes UNKNOWN? |
| App ↔ secondary | Chỉ secondary unreachable | Read preference/fallback? |
| Leader ↔ follower | Một follower không nhận log | Quorum, lag, catch-up? |
| 1 node ↔ 2 nodes | Minority/majority split | Election/fencing? |
| 2 zones ↔ nhau | Zone split | Availability theo zone? |
| Region A ↔ B | Cross-region replication loss | RPO/conflict? |
| CDC consumer ↔ source | Change feed dừng | Freshness/backfill? |
| DB ↔ KMS/control plane | Data plane còn chạy? | Credentials/key dependency? |
| App ↔ cache | Cache unreachable | Source fallback/stampede? |
| App ↔ search | Index endpoint unreachable | Graceful degradation? |
| One-way response loss | ACK không về | Unknown commit/retry correctness? |
| DNS/LB failure | Node sống nhưng route sai | Discovery/connection drain? |

### 11.1. Phân hoạch theo client cũng quan trọng

Có thể database nodes thấy nhau, nhưng một nhóm clients ở zone A không tới cluster. Trong trường hợp này không nhất thiết có failover; test nên kiểm tra client connection selection, timeout, fallback và rate caps.

### 11.2. Network healing không đồng nghĩa cluster đã recovered

Sau khi nối lại:
- Replica vẫn đang bắt kịp.
- Repair/compaction có thể chạy.
- Backlog tăng.
- Search index lag.
- Cache cold.
- Connection pools cần refresh.
- Old leader có thể còn stale.
- Cross-region conflict resolution chưa xong.

Recovery window phải tính từ **đến khi invariants và SLO được đáp ứng**, không chỉ từ lúc remove proxy toxic.

## 12. Thiết kế oracle cho safety

Safety properties thường quan trọng hơn tỷ lệ lỗi tức thời:

### 12.1. Không double-book

Một booking slot chỉ cho tối đa một booking CONFIRMED:
- Hai requests cùng slot.
- Một network fault tại commit/ACK.
- Client retry với cùng logical operationId.
- Sau hồi phục, đếm authoritative confirmed bookings.
- Kỳ vọng số confirmed theo inventory invariant, không theo số HTTP successes.

### 12.2. Không duplicate charge

Một payment operationId phải chỉ tạo một logical charge:
- Inject timeout sau provider/DB success.
- Retry request.
- Reconcile provider/ledger.
- Không xem hai attempt network là hai business transactions.

### 12.3. Version monotonicity

Nếu booking source đạt version 8, một stale event version 7 không được làm source/read model lùi về 7 theo contract của projection.

### 12.4. Tenant isolation

Network retry, fallback read, cache hit hoặc leader failover không được đổi tenant scope. Dữ liệu test có hai tenants dùng cùng bookingId để bắt lỗi key namespace và filter thiếu tenant.

### 12.5. Delete/tombstone không hồi sinh

Một DELETE v9 phải thắng upsert v8 đến muộn, kể cả sau partition/catch-up. Test cả TTL/erasure policy.

### 12.6. Đừng chỉ assert số bản ghi

Hai datasets cùng count vẫn có thể sai key membership/amount/versions. So:
- Stable business key.
- Tenant.
- Operation ID.
- Version.
- Canonical business fields.
- Delete markers.
- External side-effect ledger.

## 13. Oracle cho liveness và hiệu năng

Một test có thể đúng về safety nhưng phục vụ quá ít requests. Cần tách:

- **Safety:** mọi thao tác đã xác nhận tuân invariant.
- **Liveness:** khi điều kiện cho phép, thao tác hợp lệ tiến triển.
- **Availability:** tỷ lệ thành công trong deadline theo từng operation.
- **Latency:** p50/p95/p99, timeouts.
- **Recovery:** thời gian failover, catch-up, trở lại SLO.
- **Freshness:** source vs read model version lag.
- **Cost:** CPU/IO/network, queue, retry amplification.

### 13.1. Không đánh đồng lỗi được thiết kế với regression

Nếu partition làm phía thiểu số không thể commit writes linearizable, tỷ lệ success phía đó giảm là expected. Test có thể pass safety nhưng cần ghi availability loss theo SLO.

### 13.2. Mục tiêu phục hồi có thời hạn

Ví dụ test contract:
- Sau fault removal, trong 90 giây p99 trở về dưới mục tiêu.
- Trong 30 giây, CDC lag dưới 5 giây.
- Không outstanding unknown outcome quá thời hạn reconciliation.
- Không side effects duplicate.

Mọi ngưỡng phải xuất phát từ mục tiêu hệ, không lấy những con số minh họa làm bảo đảm phổ quát.

## 14. Offered load, completed throughput và coordinated omission

Một load generator **closed-loop** chờ request xong mới gửi request mới:
- Khi DB chậm, tự giảm RPS.
- Completed throughput giảm.
- Latency đo được có thể không phản ánh những requests lẽ ra phải tới.

Nếu cần kiểm tra service ở arrival rate cố định, dùng open-loop hoặc mô hình scheduling phù hợp:
- Planned arrivals.
- Sent arrivals.
- Completed responses.
- Queued/dropped arrivals.
- Deadline expirations.
- End-to-end latency tính từ thời điểm lên lịch nếu mục tiêu là user demand.

### 14.1. Retry amplification

Định nghĩa:

\[
A_{\mathrm{retry}} =
\frac{\text{số physical DB attempts}}
{\text{số logical user operations}}
\]

Nếu 1.000 logical requests tạo 4.000 attempts, A=4. Tăng retries trong lúc DB đang quá tải có thể khiến cluster hồi phục chậm hơn.

### 14.2. Little's Law và chờ trong hàng đợi

Một trực giác vận hành:

\[
L \approx \lambda W
\]

Khi arrival rate \(\lambda\) không giảm mà service time \(W\) tăng, số requests đang chờ \(L\) tăng. Giới hạn concurrency/queue là cần thiết; không để bộ nhớ và connections tăng vô hạn.

### 14.3. So tải theo từng operation

Không báo một p99 chung cho toàn hệ nếu:
- Point read tốt.
- Conditional write timeout.
- Search queries stale.
- CDC lag cao.

Mỗi operation có contract và tầng dữ liệu khác nhau.

## 15. Retry policy: chỉ retry khi có cơ sở

Một retry hợp lý cần:
- Phân loại error có thể retry hay không.
- Giới hạn số attempts.
- Deadline tổng.
- Exponential backoff với jitter.
- Idempotency của operation.
- Circuit breaker/admission.
- Rate limit per tenant.
- Cách reconcile UNKNOWN outcomes.

### 15.1. Không retry mọi lỗi

Không retry vô hạn:
- Invalid input.
- Authorization denied.
- Conditional write conflict.
- Unknown enum/schema.
- Permanent permission error.
- Quota hard limit theo contract.

Có thể retry có điều kiện:
- Connection reset.
- Timeout.
- Temporary leader election.
- Transient throttling.
- Retryable error code do driver/engine định nghĩa.

Nhưng với write timeout, **retry phải bảo vệ logical operationId**.

### 15.2. Exponential backoff

Ví dụ:

~~~~text
attempt 1 immediately
attempt 2 after random delay in [0, 100 ms]
attempt 3 after random delay in [0, 200 ms]
attempt 4 after random delay in [0, 400 ms]
stop if no overall deadline
~~~~

Con số minh họa. Jitter giảm đồng bộ retries giữa nhiều clients. Nếu tất cả reconnect chính xác sau 1 giây, recovery có thể gặp một làn sóng mới.

### 15.3. Retry budget

Một policy có thể giới hạn:
- Số retry attempts trong một request.
- Tổng retry RPS per service.
- Retry rate per tenant.
- Retry concurrency.
- Retry cost so với successful original traffic.

Retry chỉ có ý nghĩa nếu hệ còn năng lực xử lý; có lúc fail fast tốt hơn.

### 15.4. Driver retry không đồng nghĩa end-to-end idempotency

Database driver có thể retry một số writes theo tính năng riêng. Điều đó không tự bảo vệ:
- API tạo bookingId mới mỗi lần client retry.
- Payment provider được gọi hai lần.
- Email gửi hai lần.
- Outbox event được phát trùng.
- HTTP gateway thực hiện retry ở lớp khác.

Thử nghiệm phải theo dõi **mọi retry layer**.

## 16. Java 21: mô hình kết quả ba trạng thái

Một API domain không nên coi mọi exception là thất bại chắc chắn.

~~~~java
public sealed interface WriteOutcome
        permits WriteConfirmed, WriteRejected, WriteUnknown {
}

public record WriteConfirmed(
        String bookingId,
        long committedVersion
) implements WriteOutcome {}

public record WriteRejected(
        String code,
        boolean retryable
) implements WriteOutcome {}

public record WriteUnknown(
        String operationId,
        String reason
) implements WriteOutcome {}
~~~~

Trong business service:
- CONFIRMED: trả canonical result theo transaction contract.
- REJECTED: xử lý theo error code, không mutate tự động.
- UNKNOWN: đọc authoritative operation ledger bằng operationId để reconcile.

### 16.1. Operation ID phải ổn định

Nếu user gửi cùng logical booking request lần hai do timeout:
- Dùng cùng idempotency key.
- Payload fingerprint phải khớp.
- Bảo vệ tenant scope.
- Nếu operation đã commit, trả kết quả cũ.
- Nếu conflicting payload cùng key, reject.
- Nếu trạng thái chưa rõ, tiếp tục reconcile hoặc trả pending/unknown theo contract.

### 16.2. Không tạo bookingId mới trước mỗi physical retry

Nếu mỗi retry tạo ID mới:
- Hệ có thể tạo hai bookings dù database ghi mỗi ID đúng một lần.
- Conditional insert theo từng key không ngăn duplicate logical intent.
- Cần separate operation ID và business invariant.

## 17. Java 21: deadline và phân loại retry

Một helper thuần Java minh họa điều phối deadline:

~~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class Deadline {
    private final long endNanos;

    public Deadline(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("budget");
        }
        long now = System.nanoTime();
        long delta = budget.toNanos();
        this.endNanos = Math.addExact(now, delta);
    }

    public long remainingNanos() {
        return Math.max(0L, endNanos - System.nanoTime());
    }

    public boolean expired() {
        return remainingNanos() == 0L;
    }

    public long remainingMillis() {
        return TimeUnit.NANOSECONDS
                .toMillis(remainingNanos());
    }
}
~~~~

Đây là minh họa, không phải deadline utility chống mọi overflow/wraparound cho quá trình chạy cực dài. Trong production, cần xem clock monotonic, cancellation/interrupt và timeout propagation ở driver.

### 17.1. Không sử dụng wall clock cho elapsed time

System.currentTimeMillis có thể nhảy do NTP/time adjustment. System.nanoTime phù hợp hơn để đo duration trong một process. Ghi UTC timestamps riêng để dựng incident timeline.

### 17.2. Deadline phải bao phủ cả queue time

Một request chờ connection pool 900 ms rồi DB call 500 ms đã vượt HTTP deadline 1.200 ms. Không đo mỗi server execution time mà bỏ queue.

### 17.3. Cancellation không chắc undo server write

Client cancellation chỉ chấm dứt chờ/attempt cục bộ, không tự chứng minh database rollback. Trạng thái vẫn có thể UNKNOWN và cần reconciliation.

## 18. Java 21: fault harness xác định cho lost ACK

Trước khi thử với database thật, có thể test business semantics bằng một fake transport có kiểm soát.

~~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

public final class FakeBookingStore {
    private final Map<String, WriteConfirmed> ledger =
            new ConcurrentHashMap<>();
    private final AtomicLong nextVersion =
            new AtomicLong();

    // Simulates a durable idempotency ledger in memory.
    public WriteConfirmed commitOnce(
            String tenantId,
            String operationId
    ) {
        String key = tenantId + ":" + operationId;
        return ledger.computeIfAbsent(
                key,
                ignored -> new WriteConfirmed(
                        "B-" + operationId,
                        nextVersion.incrementAndGet()
                )
        );
    }

    public WriteConfirmed find(
            String tenantId,
            String operationId
    ) {
        return ledger.get(tenantId + ":" + operationId);
    }

    public int logicalOperations() {
        return ledger.size();
    }
}
~~~~

Test logic:

~~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

final class LostAckTest {
    @Test
    void retrySameOperationDoesNotDuplicateBooking() {
        FakeBookingStore store = new FakeBookingStore();

        // First request commits, but its response is lost.
        store.commitOnce("T-A", "OP-91");
        WriteOutcome observed =
                new WriteUnknown("OP-91", "ACK_LOST");

        assertInstanceOf(WriteUnknown.class, observed);

        // Retry/reconcile with the same logical operation ID.
        WriteConfirmed retried =
                store.commitOnce("T-A", "OP-91");
        WriteConfirmed canonical =
                store.find("T-A", "OP-91");

        assertEquals(canonical, retried);
        assertEquals(1, store.logicalOperations());
    }
}
~~~~

### 18.1. Những điều fake test không chứng minh

- Durability qua process crash.
- Distributed atomicity của ledger và booking write.
- Transaction isolation.
- Driver timeout semantics.
- Quorum election/replica lag.
- Cross-region idempotency.

Trong một adapter NoSQL thật, **operation ledger và booking write cần một ranh giới atomic/conditional hoặc một protocol reconciliation đã thiết kế**. In-memory map chỉ minh họa invariant của logical operation.

### 18.2. Thêm dữ liệu đối nghịch

Test cùng operationId nhưng payload khác:
- Phải reject conflict.
- Không trả canonical result của intent không khớp mà không xác minh fingerprint.
- Không để tenant B truy cập operation của tenant A.

## 19. Inject lỗi bằng proxy trong môi trường kiểm thử

Một công cụ thường dùng cho fault injection TCP là **Toxiproxy**. Nó đặt một proxy giữa client và backend; client kết nối tới proxy, proxy chuyển tiếp sang database.

~~~~mermaid
flowchart LR
    JAVA["Java test client"] --> PROXY["Fault proxy"]
    PROXY --> DB[("NoSQL test instance")]
    CTRL["Test controller"] -.-> PROXY
~~~~

Ví dụ mô tả cấu hình proxy:

~~~~json
{
  "name":"db-test",
  "listen":"0.0.0.0:27018",
  "upstream":"mongo-test:27017"
}
~~~~

Một toxic độ trễ theo hướng server→client có thể được khai báo theo API tương ứng của phiên bản Toxiproxy:

~~~~json
{
  "name":"server-response-delay",
  "type":"latency",
  "stream":"downstream",
  "toxicity":1.0,
  "attributes":{
    "latency":800,
    "jitter":100
  }
}
~~~~

**Cần xác minh chính xác API và hướng upstream/downstream của bản proxy đang dùng.** Latency toxic ở tầng proxy không tương đương với mọi đặc tính packet loss ở IP.

### 19.1. Các fault modes qua proxy

- Delay client→server.
- Delay server→client.
- Reset/close connection.
- Bandwidth restriction.
- Server response cut.
- Timeout/blackhole-like behavior.
- Test proxy enable/disable.

Tính năng cụ thể phụ thuộc công cụ và version. Không “giả lập” packet loss bằng một lệnh không thực sự drop IP packets rồi kết luận đã test TCP retransmission.

### 19.2. Hạn chế của proxy

- Thường là một đường client→server.
- Không chắc can thiệp traffic node↔node.
- Existing connections có thể bypass khi app không route qua proxy.
- Load balancer/driver discovery có thể chuyển sang địa chỉ khác.
- Proxy instance bản thân có thể thành bottleneck.

Vì vậy phải ghi topology và xác nhận thực tế traffic đi qua proxy trong test.

## 20. Linux tc/netem: mô phỏng ở tầng network

Trong network namespace hoặc test container Linux, tc/netem có thể:
- Thêm delay.
- Jitter.
- Loss.
- Duplicate/reorder.
- Corrupt ở tầng mô phỏng.
- Giới hạn distribution theo cấu hình.

Ví dụ minh họa **chỉ trong môi trường cô lập**:

~~~~bash
# Example only; apply inside an isolated test namespace/container.
tc qdisc add dev eth0 root netem delay 200ms 50ms loss 1%

# Remove the injected fault.
tc qdisc del dev eth0 root
~~~~

### 20.1. Điều kiện trước khi chạy

- Interface eth0 phải thực sự là giao diện test.
- Có quyền CAP_NET_ADMIN trong namespace tương ứng.
- Biết chính xác luồng nào bị ảnh hưởng.
- Có cleanup ngay cả khi test process crash.
- Không chạy trên host network chung/production.
- Có route rollback.
- Không chồng nhiều qdisc ngoài dự kiến.

### 20.2. Loss và delay direction

Rule trên egress của interface chỉ ảnh hưởng hướng tương ứng; để kiểm tra traffic return path có thể phải cấu hình interface/namespace phía khác. Không tự cho rằng một tc rule mô phỏng bidirectional partition.

### 20.3. Thí nghiệm lặp lại

Lưu:
- Interface/namespace.
- Kernel/tool version.
- Command/config.
- Random seed nếu công cụ hỗ trợ.
- Duration.
- Measured actual RTT/loss.
- Recovered network state.
- Test artifacts.

Các faults ở tầng mạng có thể tương tác với congestion control và retransmit algorithms; kết quả latency có phân phối chứ không chỉ cộng cố định 200 ms.

## 21. Tạo network partition an toàn

Muốn thử partition A | B,C:
1. Dùng ba DB test nodes và hai network namespaces/zones.
2. Cho lưu lượng A↔B và A↔C không đi được trong thời hạn kiểm soát.
3. Giữ B↔C liên lạc.
4. Đặt clients ở cả hai phía nếu cần.
5. Quan sát quorum/leader/failover.
6. Thực hiện operations theo contract.
7. Bỏ luật partition.
8. Đợi cluster converge.
9. Đối soát state và side effects.

### 21.1. Một chiều so với hai chiều

Test:
- A→B blocked, B→A allowed.
- B→A blocked, A→B allowed.
- Both directions blocked.

Không giả định leader detection/election là đối xứng.

### 21.2. Tắt cổng không đồng nghĩa partition hoàn chỉnh

Có thể còn:
- Replication trên port khác.
- Gossip/control plane.
- Load balancer route.
- DNS alternative.
- Node discovery addresses.
- Monitoring/control channel.

Cần sơ đồ ports/protocols và quan sát thật sự reachability của từng cặp node.

### 21.3. Tác động đến clock và leases

Network partition có thể gây lease expiry/election. Không cần sửa đồng hồ hệ thống để mô phỏng packet loss; clock skew là một fault riêng, nên test độc lập trước khi phối hợp.

## 22. MongoDB: kiểm thử primary, secondary và write concern

Trong MongoDB replica set:
- Primary xử lý writes trong thông lệ vận hành.
- Secondaries replicate và có thể phục vụ reads theo read preference.
- Election làm thay primary.
- Write concern/read concern/session/transaction ảnh hưởng guarantee.
- Network failure có thể làm driver báo server selection timeout.

### 22.1. Các tình huống tối thiểu

1. App mất TCP tới primary nhưng còn secondary.
2. Primary bị cô lập khỏi majority.
3. Một secondary chậm replication.
4. Client lost ACK sau một write đã commit theo write concern.
5. Stepdown/failover khi có conditional update.
6. Read từ secondary chưa bắt kịp.
7. Transaction commit trả outcome chưa xác định.
8. App reconnect sau election.

### 22.2. Các assertions chính

- Không có booking trùng logical operationId.
- Không rollback writes mà API đã công bố là durable theo write concern.
- Không cho stale primary tiếp tục ghi trái cơ chế election/fencing.
- Read preference đúng.
- Strong/session read contract được tôn trọng khi chọn readConcern phù hợp.
- Retryable writes/transactions được xử lý đúng theo error labels/driver behavior.
- Không dựa vào một exception type duy nhất cho mọi network fault.

### 22.3. “Majority” không bằng mọi điều kiện durable trên thế giới

Tùy replication/journaling/configuration, majority ACK có semantics rõ và giới hạn riêng. Không assert một mức durability chưa được engine/config bảo đảm. Xác minh writeConcern, journaling, topology và failover behavior theo phiên bản đang thử.

### 22.4. Read model ngoài MongoDB

MongoDB source có thể đúng nhưng OpenSearch index hoặc Redis cache stale. Test tách:
- Source correctness.
- Projection freshness.
- Fallback behavior.
- Cache invalidation.

## 23. Cassandra: test consistency level và replica reachability

Cassandra có lựa chọn consistency level theo operation, replication factor, token placement, coordinator và repair mechanisms.

### 23.1. Ma trận mẫu

Với một key thuộc replication factor 3 trong một datacenter:
- Ngắt một replica, thử read/write ở consistency ONE.
- Ngắt một replica, thử LOCAL_QUORUM.
- Ngắt hai replicas, thử LOCAL_QUORUM.
- Ngắt coordinator khỏi một số replicas.
- Chữa kết nối, quan sát hinted handoff/repair theo cấu hình.
- Thử stale read, timestamp conflict và tombstone.

Đây là **khung thí nghiệm**, không phải cam kết mọi operation sẽ succeed/fail độc lập với topology và trạng thái cụ thể.

### 23.2. Quorum phải đúng phạm vi datacenter

LOCAL_QUORUM khác QUORUM trong multi-DC deployment; test cần biết:
- Replication strategy.
- Replica count theo DC.
- Những replicas thật sự sở hữu partition.
- Coordinator location.
- Read/write consistency.
- Driver routing.

Không chỉ kill một node bất kỳ rồi tính quorum như tất cả nodes đều là replicas của key.

### 23.3. Last-write-wins và timestamp

Một write “mới hơn theo application version” chưa chắc thắng nếu storage timestamp conflict semantics khác. Test:
- Two conflicting writes.
- Clock skew.
- Tombstone timestamps.
- Repair behavior.
- Explicit versioned model nếu domain cần monotonicity.

### 23.4. LWT/conditional update

Nếu dùng lightweight transactions/conditional statements:
- Retry timeout có thể UNKNOWN.
- Conditional failure là expected conflict, không auto retry như network glitch.
- Đối soát current state/operation ID.

## 24. DynamoDB: endpoint, GSI và Global Tables

DynamoDB là managed service, nên không thể tự phân hoạch các storage nodes theo cách một cluster self-hosted cho phép. Trong môi trường được phép, test có thể:
- Fault ở link client↔endpoint qua proxy/test network.
- Simulate SDK timeouts/retries/throttling bằng test doubles khi cần.
- Kiểm tra regional endpoint outage/failover policy.
- Quan sát GSI/read-model eventual consistency.
- Test Global Tables cross-region conflict/recovery theo giới hạn service/provider.

### 24.1. Base table và GSI

- Một write thành công ở base table không có nghĩa GSI đã visible tức thì.
- GSI có eventual consistency semantics riêng.
- Query GSI sau fault cần poll bounded theo freshness contract.
- Không dùng absence ở GSI làm bằng chứng source record không tồn tại.

### 24.2. Conditional writes

Test:
- ExpectedVersion match.
- ExpectedVersion mismatch.
- Timeout after commit.
- Retry cùng operation ID.
- Throttling và backoff.
- Partial batch results.

Chỉ vì SDK hỗ trợ retries không làm arbitrary multi-step booking/payment workflow idempotent.

### 24.3. Global Tables

Khi region A và B mất kết nối:
- Regional writes/conflict semantics phải theo table mode/provider guarantee.
- Không giả định uniqueness toàn cầu nếu không có cơ chế bảo vệ.
- Sau reconnect, kiểm tra winner/conflict outcomes, delete propagation và sourceVersion.
- Không tự xem một region endpoint healthy là dữ liệu toàn cầu đã hội tụ.

## 25. Redis: replication, failover và cache degradation

Redis được dùng dưới nhiều vai trò:
- Cache thuần.
- Rate limiter.
- Session store.
- Queue/stream.
- Primary persistence cho một số dữ liệu.

Test phải phân biệt vai trò.

### 25.1. Redis cache outage

Nếu Redis không truy cập được:
- API có fallback source không?
- Fallback có làm source quá tải không?
- Cache misses/reconnect storms?
- Negative caching có gây false not-found?
- TTL/invalidation sau reconnect?
- Độ trễ sau warm-up?

Nếu cache là derived data, có thể an toàn hơn khi bỏ cache và đọc source, nhưng phải có **admission và origin load protection**.

### 25.2. Redis primary–replica failover

Trong kiến trúc replication bất đồng bộ, writes đã được primary ACK có thể chưa tới replica trước failover tùy durability/config. Test:
- Lag.
- Primary isolation.
- Leader/primary promotion.
- Lost acknowledged writes theo documented guarantee.
- Client reconnection.
- Key version/idempotency.
- Persistence RDB/AOF.

Không đánh đồng Redis WAIT với một consensus transaction đảm bảo không mất dữ liệu trong mọi failover.

### 25.3. Redis Cluster

Partition ở hash slots/nodes:
- Một số keys unavailable, keys khác vẫn có thể hoạt động.
- MOVED/ASK routing và driver discovery.
- Multi-key operations có giới hạn hash slot.
- Hot slot/cache stampede.
- Retry storms khi slot ownership đổi.

### 25.4. Redis Streams

Nếu Redis Streams là event queue:
- Consumer reconnect.
- Pending entries.
- ACK vs process completion.
- Duplicate deliveries.
- Stream trimming.
- Recovery after partition.
- Idempotency ledger ở consumer.

## 26. Search index, CDC và cache trong lỗi mạng

Một hệ có thể có:

~~~~mermaid
flowchart LR
    API["Java API"] --> SOURCE[("NoSQL source")]
    SOURCE --> CDC["Change stream/outbox"]
    CDC --> BROKER["Broker"]
    BROKER --> CONSUMER["Projection worker"]
    CONSUMER --> SEARCH[("Search index")]
    API --> CACHE[("Cache")]
    API --> SEARCH
~~~~

Faults:
- Source→CDC broken.
- CDC→broker delayed.
- Broker→worker partition.
- Worker→search unavailable.
- API→cache timeouts.
- API→search slow.

### 26.1. Source success vs projection failure

Nếu source write ACK nhưng search index unavailable:
- Booking source vẫn có thể đúng.
- Search view stale.
- Không được tự trả “booking creation failed” nếu source đã commit và API contract không yêu cầu atomic search visibility.
- Cần checkpoint, replay và freshness SLO.

### 26.2. Out-of-order events

Event v9 có thể tới trước v8 khi có retries:
- Projection apply phải version-aware.
- Delete/tombstone thắng stale upsert.
- Không checkpoint trước durable apply.
- EventId dedup.

### 26.3. Backlog catch-up

Sau partition:
- 100.000 events chờ.
- Consumer reconnect.
- Burst traffic đập vào search.
- Source read amplification tăng.
- Indexing lag kéo dài.

Test recovery throughput, batch limits, retry backoff, resource quotas và eventual convergence, không chỉ việc TCP được kết nối lại.

### 26.4. Cache stale fill

Trong lúc source chập chờn:
1. Cache miss.
2. API đọc source v7.
3. User update source lên v8.
4. Delayed request lưu v7 vào cache sau invalidation.
5. Cache trả stale v7.

Test cần version-aware cache fill hoặc invalidation policy tương đương theo contract.

## 27. Fault khi có giao dịch và bất biến nhiều bản ghi

Một hệ booking có thể cần thay đồng thời:
- Booking state.
- Inventory reservation.
- Payment operation ledger.
- Outbox event.

Các stores có transaction scopes khác nhau.

### 27.1. Atomic boundary

Nếu source hỗ trợ transaction:
- Fault giữa statements.
- Fault tại commit.
- Lost commit ACK.
- Client retry transaction.
- Secondary index lag.
- Deadlines/transaction duration.

Test phải xác minh **toàn bộ invariant** thay vì chỉ booking document.

### 27.2. Saga workflow

Nếu inventory/payment ở các systems khác:
- Network partition giữa steps.
- Compensation failure.
- Duplicate callback.
- Retry after partial success.
- Delayed event.
- Timeout in reconciliation.

Kết quả có thể là PENDING/RECONCILING, không đơn thuần COMMITTED/ROLLED_BACK.

### 27.3. Escrow/token/slot ownership

Với giới hạn hữu hạn như một chỗ trống:
- Partition có thể cấm nhận thêm bookings nếu không có quyền quota/token tương ứng.
- Nếu cho local writes ở cả hai phía mà không có reservation ownership, có nguy cơ overbooking.
- Test conflict policy trước khi mở availability.

## 28. Mô hình thí nghiệm theo giai đoạn

### Giai đoạn 1 — Prepare

- Chốt môi trường isolated.
- Snapshot/backup data test.
- Pin engine/driver/proxy versions.
- Tạo synthetic fixtures/operation IDs.
- Xác minh topology và route.
- Khởi động metrics/logging.
- Xác định kill switch.

### Giai đoạn 2 — Baseline

- Chạy tải ở mức stable.
- Lưu throughput/p99/errors/replica lag.
- Chứng minh dữ liệu ban đầu đúng.
- Xác nhận load generator đủ capacity.

### Giai đoạn 3 — Inject fault

- Chỉ tác động đúng đường/cặp nodes.
- Ghi fault start event bằng monotonic timer và UTC.
- Kiểm tra actual loss/delay/reachability.
- Duy trì offered workload.
- Thu per-attempt outcomes.

### Giai đoạn 4 — Fault window

- Quan sát availability.
- Không cho retry queues tăng vô hạn.
- Thu leader/election/quorum state.
- Theo dõi UNKNOWN operations.
- Báo safety violations ngay.

### Giai đoạn 5 — Heal

- Remove fault rules.
- Verify network restored.
- Giữ tải có kiểm soát.
- Quan sát reconnect/catch-up.
- Throttle backlog nếu cần.

### Giai đoạn 6 — Reconcile

- Đối soát authoritative state.
- OperationId/booking count.
- Inventory/payment invariants.
- SourceVersion/tombstones.
- Cache/search convergence.
- Confirm no old leader write.

### Giai đoạn 7 — Report

- Actual fault duration.
- Blast radius.
- Safety pass/fail.
- Availability/latency by operation.
- Recovery time.
- Remaining unknowns.
- Regression tests/runbook updates.

## 29. Mẫu kịch bản có tiêu chí pass/fail

~~~~yaml
caseId: PARTITION-BOOKING-01
given:
  clusterNodes: 3
  workload:
    bookingWritesPerSecond: 20
    readsPerSecond: 100
  target:
    invariant: oneConfirmedBookingPerSlot
    retryPolicy: boundedWithJitter
    operationId: stableAcrossRetries
when:
  fault: isolateLeaderFromMajority
  durationSeconds: 30
then:
  safety:
    duplicateLogicalBookings: 0
    negativeInventory: 0
    crossTenantLeaks: 0
  outcomes:
    everyUnknownOperationReconciled: true
    confirmedWritesMatchDurableSource: true
  recovery:
    oldLeaderCannotWriteAfterDemotion: true
    allAuthoritativeReplicasConverge: true
  performance:
    measureAvailabilityByOperation: true
    measureRecoveryToSlo: true
~~~~

Đây là test specification minh họa. Đánh giá "all authoritative replicas converge" cần boundary/time policy thực tế, không assert tức thì sau khi heal.

### 29.1. Pass về safety có thể đi cùng SLO fail

Một kịch bản có thể không tạo duplicate booking nhưng mất write availability 90 giây. Báo:
- SAFETY=PASS.
- AVAILABILITY=FAIL.
- RECOVERY=PASS/FAIL.
- INTEGRITY=PASS.

Tránh một cờ pass duy nhất che mất đánh đổi.

### 29.2. Nếu outcome UNKNOWN chưa reconcile

Không ghi test PASS nếu một write đã timeout và không rõ có commit hay không. Trả UNRESOLVED/INCONCLUSIVE theo contract, giữ operation ledger và điều tra.

## 30. Metrics cụ thể khi inject lỗi

| Nhóm | Metrics |
| --- | --- |
| Request | Offered/sent/completed/error/timeout rates |
| Latency | p50/p95/p99, queue wait, driver attempt latency |
| Retry | Attempts/logical op, retry budget consumption |
| Connections | Established/opening/reset, pool acquire timeout |
| Network | RTT, retransmits, packet drops, bytes |
| Database | Leader/role, quorum, replica lag, commit latency |
| Storage | WAL/compaction/IO wait, checkpoint lag |
| CDC | Source position, consumer position, event age |
| Cache | Hit ratio, stale fill, stampede, eviction |
| Data | Duplicate keys, conflicting versions, missing records |
| Security | Tenant mismatch, unauthorized fallback |
| Recovery | Election time, reconnect time, catch-up time, SLO restore time |
| Cost | CPU, memory, thread/virtual-thread count, queue lengths |

### 30.1. Không dùng client-side errors làm bằng chứng duy nhất

Client timeout count không cho biết số commits. Cần server-side operations/ledger và reconciler.

### 30.2. Telemetry không được làm quá tải hệ

Khi lỗi mạng, log raw payload từng retry có thể:
- Tăng IO.
- Rò rỉ PII/secret.
- Làm incident tệ hơn.
- Tạo high-cardinality metrics.

Log structured theo reason/operation/tenant tier với sampling và redaction.

### 30.3. Dựng timeline nhất quán

Dùng:
- UTC timestamps để ghép events giữa nodes.
- Monotonic elapsed time trong từng process.
- NTP/clock-skew monitoring.
- Fault start/end markers.
- Leader election epoch.
- Source log positions.

Không so total order chỉ bằng wall-clock từ các hosts có lệch đồng hồ.

## 31. Ví dụ Java: đo logical outcomes, không chỉ HTTP code

Một record cho mỗi logical operation:

~~~~java
import java.time.Instant;

public record OperationTrace(
        String operationId,
        String tenantId,
        Instant startedAtUtc,
        int physicalAttempts,
        String clientOutcome,
        String reconciledOutcome,
        Long committedVersion,
        long elapsedMillis
) {}
~~~~

Phân loại:
- CLIENT_CONFIRMED.
- CLIENT_REJECTED.
- CLIENT_UNKNOWN.
- RECONCILED_COMMITTED.
- RECONCILED_NOT_FOUND_WITH_PROOF.
- RECONCILIATION_PENDING.

### 31.1. Đừng gán NOT_FOUND thành rollback quá sớm

Nếu read-after-write dùng eventual replica hoặc index, một read miss không chứng minh operation chưa commit. Reconcile trên authoritative source và với consistency policy phù hợp.

### 31.2. Đếm side effects

Ghi trong test ledger:
- operationId.
- BookingId.
- Inventory holds.
- Payment charges.
- Outbox event IDs.
- Notifications sent.

Assert một logical effect cho một operation, ngay cả khi driver có nhiều physical attempts.

## 32. Connection pool khi mạng chậm

Một pool hữu hạn sẽ có các failure modes:
- Existing connections half-open.
- All connections busy.
- New connects timeout.
- Borrow/acquisition queue tăng.
- Threads chờ.
- Driver server selection chậm.
- Trả lỗi sau API deadline.
- Reconnect storm sau fault removal.

### 32.1. Bộ test

1. Inject downstream delay.
2. Duy trì fixed offered RPS.
3. Đo active/idle/waiting connections.
4. Kiểm tra bounded queue.
5. Verify timeouts và resource budgets.
6. Remove fault.
7. Theo dõi pool trở lại steady state.
8. Đảm bảo no connection leak.

### 32.2. Virtual threads không xóa giới hạn nguồn

Java virtual threads giúp xử lý blocking model hiệu quả hơn ở một số workload, nhưng:
- Connection pool vẫn hữu hạn.
- Database vẫn có capacity limit.
- Retry storm vẫn tạo overload.
- External calls vẫn cần deadlines/admission.

Đừng tăng concurrency vô hạn chỉ vì dùng virtual threads.

## 33. Circuit breaker, bulkhead và load shedding

### 33.1. Circuit breaker

Khi dependency lỗi:
- Mở circuit sau ngưỡng phù hợp.
- Fail fast thay vì chờ timeout lâu.
- Cho phép controlled probe ở half-open.
- Không làm mất business outcome reconciliation.

### 33.2. Bulkhead

Giới hạn concurrency cho:
- Per-tenant requests.
- Reads vs writes.
- Search vs source database.
- Retry pool vs primary requests.

Một tenant hoặc một endpoint nặng không nên chiếm mọi connections của hệ.

### 33.3. Load shedding

Khi quá tải:
- Từ chối noncritical reads/exports.
- Giới hạn batch size.
- Ưu tiên authoritative transactions.
- Áp 429/503/Retry-After nếu policy.
- Không nhận request rồi giữ vô hạn.

### 33.4. Fail-open vs fail-closed

Tùy chức năng:
- Recommendation/search có thể degrade.
- Cache có thể bypass nếu source chịu được.
- Payment/inventory không được fail-open làm phá invariants.
- Authorization service unavailable thường phải tránh cấp quyền theo suy đoán.

## 34. Search/index outage và UX hợp lý

Một API có thể:
- Tạo booking thành công ở source.
- Search index không truy cập được.
- UI không thấy booking trong search.

Nếu UX hứa “booking vừa tạo sẽ xuất hiện ngay”, cần:
- Read by authoritative bookingId.
- Session-aware fallback.
- Thông báo search đang trễ.
- Poll indexed version với deadline.

Không tự chuyển retry search thành retry create booking.

### 34.1. Negative cache hazard

Nếu search/index timeout và app cache NOT_FOUND:
- Booking có thể bị ẩn nhiều phút.
- Reconciliation khó.

Timeout/unavailability phải khác authoritative absence.

### 34.2. Recovery queue drain

Sau khi search reconnect:
- Replay rate có budget.
- Bảo vệ source read load.
- Không index stale events sau tombstones.
- Theo dõi sourceVersion và indexVersion.
- Reconcile missing/phantom documents.

## 35. Fault tests với nhiều tầng timeout

Một request có:
- Client HTTP deadline 1.5 s.
- Gateway timeout 1.2 s.
- App DB timeout 2 s.
- Driver retry budget 3 attempts.

Cấu hình này có thể gây:
- Client/gateway bỏ cuộc trước DB.
- DB tiếp tục work.
- App retry sau user timeout.
- Duplicate side effects nếu ID mới.
- Wasted DB capacity.

Test nên đo:
- Time request entered gateway.
- Time entered app.
- Pool wait.
- Attempt start/finish.
- DB commit position.
- Response send/drop.
- Client disconnect.
- Final reconciliation.

### 35.1. Bounded work after cancellation

Ứng dụng có thể cần dừng expensive reads khi client rời đi, nhưng writes đã commit thì phải reconcile đúng. Cancellation là cơ chế tiết kiệm tài nguyên, không phải transaction rollback chắc chắn.

### 35.2. Deadlines và tail latency

Nếu p99 source read trong network fault là 3 s, API deadline 1.2 s nghĩa nhiều requests phải trả timeout. Không sửa bằng cách tăng mọi timeout lên 30 s mà không xét capacity/UX; có thể tăng backlog và làm recovery lâu hơn.

## 36. Kiểm thử failover với write authority

Một kịch bản:
1. Leader A.
2. Client tạo booking OP-1 tại A.
3. Network partition làm A mất liên lạc với quorum.
4. B/C bầu leader B.
5. Client tiếp tục gửi OP-1.
6. Network hồi phục, A rejoin.
7. Reconcile canonical result.

Oracle:
- Một canonical operation outcome.
- Không hai authoritative writers cùng epoch.
- No stale leader overwrite.
- A catch-up theo supported protocol.
- Client redirects/retries không tạo duplicate.
- Accepted/durable writes thỏa documented guarantee.

### 36.1. Lỗi failover không chỉ nằm ở database

- Driver giữ cached leader address.
- DNS cache chưa đổi.
- Connection pool giữ socket cũ.
- Load balancer còn route tới A.
- API fallback query secondary stale.
- CDC connector giữ resume token không còn hợp lệ.

Test end-to-end thay vì chỉ xem cluster status.

### 36.2. RPO, RTO

Khi DR/failover:
- RPO: có mất writes được ACK theo hợp đồng không?
- RTO: đến khi endpoint phục vụ và dữ liệu đủ đúng?
- Replica catch-up và projection lag?
- Client write retry/reconcile?
- Failback sau region cũ trở lại?

Nếu system design chấp nhận RPO khác 0, test phải đo và báo rõ, không hứa zero-loss.

## 37. Test traffic distribution và fault blast radius

Không đủ khi tất cả requests là:
- Một tenant.
- Một bookingId.
- Một partition.
- Một zone.
- Một driver session.

Tạo:
- Tenants nhỏ và một tenant rất lớn.
- Hot booking/partition.
- Clients ở nhiều availability zones.
- Read/write traffic khác nhau.
- Requests trước và sau fault.
- Multiple logical operation IDs.
- Một số clients dùng session read-your-writes.

### 37.1. Theo fault domain

Một outage AZ:
- Những tenants colocated trong AZ đó bị ảnh hưởng?
- Requests ở AZ còn lại vẫn chạy?
- Load balancing có chuyển thành hotspot?
- Replication có giảm capacity?

### 37.2. Tenant fairness

Dưới network fault:
- Tenant lớn có thể tạo nhiều retries.
- Tenant nhỏ vẫn cần access theo SLO.
- Bulkhead/quotas cần được đo.

Không chỉ đo tổng QPS mà bỏ per-tenant error/latency distribution.

## 38. Những kiểm thử âm tính quan trọng

| Input/tình huống | Kỳ vọng |
| --- | --- |
| Conditional update expectedVersion cũ | Conflict, không retry mù |
| Duplicate operationId/payload giống | Một logical effect |
| Duplicate operationId/payload khác | Conflict, không trộn kết quả |
| Timeout sau commit | UNKNOWN rồi reconcile |
| Read từ stale GSI | Không kết luận source absent |
| Retry với tenantId khác | Không truy cập operation tenant cũ |
| Lost DELETE event | Reconciliation/repair, không phantom record vô hạn |
| Late upsert sau tombstone | Không resurrection |
| Leader cũ trở lại | Fenced, không nhận stale writes |
| Một chiều blocked | Bounded timeout, no hang |
| Fault injector cleanup thất bại | Test abort/quarantine, không để môi trường lỗi |
| Retry budget hết | Fail fast/pending according contract |
| Queue đầy | Admission reject, không OOM |
| Search unavailable | Degrade rõ; không retry booking create |
| Cache unavailable | Bypass hoặc error đúng policy, không stampede |
| Missing PITR/log segments sau outage | Không tuyên bố complete replay |
| Wrong replica/read level | Không vi phạm RYW đã hứa |
| Invalid driver config | Fail startup/health rõ, không silently unsafe |
| Error chứa raw DB details | Redact |
| Untrusted reconnect endpoint | Không tự downgrade TLS/authorization |

## 39. Security trong fault injection

Một số security defects chỉ lộ khi có lỗi:
- Fallback đọc dữ liệu không có tenant filter.
- Cache key thiếu tenant.
- Retry thay principal/session.
- Gateway bỏ authorization headers khi reconnect.
- Circuit breaker fail-open.
- Stale role/permission cache sau revoke.
- Log raw payload có PII vì error path.
- Search fallback trả fields bị cấm.
- DB credentials quá rộng ở backup/repair worker.

### 39.1. Test revocation trong partition

Một user bị thu hồi quyền lúc 12:00. Node ở phía partition còn permission cache cũ:
- API có được trả dữ liệu mới không?
- Staleness bound nào cho authorization?
- Có cần fail-closed hay source revalidation?
- Sau reconnect, policy version có catch-up?

Nếu tính năng quyền truy cập cần strong revocation, eventual permissions cache là rủi ro phải đo.

### 39.2. Không để test tool mở route nguy hiểm

Proxy/network admin credentials chỉ dùng trong test boundary. Có cleanup/expiry rõ, tránh để debug ingress public vô tình mở tới database.

## 40. Quy trình dựng dữ liệu trước fault

Fixture đề xuất:

~~~~text
Tenant T-A:
  Booking B-001 PENDING v4, inventory slot S1=1
  Booking B-002 CONFIRMED v7
  Booking B-003 deleted v9
  Payment operation PAY-5 committed
  Search projection B-002 v6 (intentionally stale)
Tenant T-B:
  Booking B-001 CANCELLED v2
Operations:
  OP-NEW-1 create booking for S1
  OP-CANCEL-1 cancel B-002 with expectedVersion=7
CDC:
  UPSERT B-003 v8
  DELETE B-003 v9
Network:
  Three DB nodes A/B/C in two fault domains
~~~~

Các tests:
- Cross-tenant IDs không bị nhầm khi reconnect.
- Booking slot không double-book khi ACK mất.
- Cancel conflict được xử lý.
- Stale search không làm source rollback.
- Late upsert không hồi sinh deleted B-003.

### 40.1. Reset data trước mỗi scenario

Không dùng kết quả của scenario A làm input ngẫu nhiên của scenario B. Có snapshot/fixture version, per-run namespace và cleanup để thí nghiệm có thể lặp.

### 40.2. Seed và trace IDs

Lưu:
- Fixture seed.
- Operation IDs.
- Client IDs.
- Proxy toxic config.
- Fault start/end.
- Cluster topology.
- Driver version.
- Engine version.
- Expected oracle.

### 40.3. Không dùng production PII

Dùng synthetic tenants và booking IDs; data shape/size/skew có thể mô phỏng mà không sao chép email, phone, payment tokens thật.

## 41. Kế hoạch CI và chaos testing

### 41.1. Unit tests

Nhanh, deterministic:
- Retry classification.
- Deadline calculations.
- Idempotency.
- Unknown outcome state machine.
- Version-aware event apply.
- Circuit breaker decisions.
- Authorization under fallback.

### 41.2. Integration tests

Test container/proxy:
- Connection reset.
- Response delay.
- Lost ACK simulation.
- Driver reconnect.
- Conditional writes.
- Cache outage.
- CDC consumer reconnect.

### 41.3. Distributed tests

Multi-node test deployment:
- Leader isolation.
- Quorum loss.
- Replica lag.
- Asymmetric partition.
- Failover.
- Repair/catch-up.
- Cross-region routing khi khả thi.

### 41.4. Load tests

Có controlled arrival:
- Baseline throughput.
- Fault-under-load.
- Hot tenant skew.
- Retry amplification.
- Pool saturation.
- Recovery backlog.

### 41.5. DR/production chaos

Chỉ khi có:
- Approval.
- Scoped blast radius.
- Observability.
- Rollback.
- Operational ownership.
- Stop conditions.
- Data safety controls.

Không đưa ngẫu nhiên fault tool lên production chỉ vì tests trong CI đã xanh.

## 42. Một bảng thí nghiệm gợi ý

| ID | Fault | Workload | Bất biến chính | Chỉ số cần đo |
| --- | --- | --- | --- | --- |
| NET-01 | Connect refused | Point reads | No cross-tenant leak | Error latency, retries |
| NET-02 | Connection reset mid-read | Range pages | No wrong page state | Retries, cursor outcome |
| NET-03 | Drop ACK after commit | Booking create | Exactly one logical booking | Unknown reconciliations |
| NET-04 | 1% packet loss | Mixed | No corrupted writes | RTT, retransmits, p99 |
| NET-05 | 10% burst loss | Writes | Idempotency preserved | Retry amplification |
| NET-06 | +500 ms request delay | Point reads | Bounded deadline | Pool wait, p99 |
| NET-07 | +800 ms response delay | Writes | Lost ACK handled | Unknown outcomes |
| NET-08 | Asymmetric client path | Writes/reads | No hangs | Deadline expirations |
| NET-09 | Isolate primary from quorum | Conditional writes | No split-brain | Election, write loss |
| NET-10 | Isolate one follower | Reads | Consistency level honored | Lag, availability |
| NET-11 | Split region A/B | Multi-region writes | Conflict policy | RPO, reconciliation |
| NET-12 | Broker partition | CDC projection | Event ordering | Lag, queue depth |
| NET-13 | Search link outage | Search API | Source untouched | Degrade behavior |
| NET-14 | Cache link outage | Source reads | No stampede | Cache miss, source load |
| NET-15 | TCP half-open | Mixed | No unbounded queue | Pool saturation |
| NET-16 | Recover after 60 s outage | Mixed | Data convergence | Time-to-SLO |
| NET-17 | Reverse traffic block | Reads | Bounded errors | Client/server traces |
| NET-18 | DNS/LB stale route | Post-failover | Old leader fenced | Connection lifetime |
| NET-19 | Concurrent writers during partition | Booking slot | No double-book | Conflicts, ledger |
| NET-20 | Retry with wrong principal | Read/write | No unauthorized outcome | Authorization rejects |
| NET-21 | Stale upsert after delete | CDC | No resurrection | Tombstone versions |
| NET-22 | 10× load after heal | Recovery | Bounded backlog | Recovery throughput |
| NET-23 | Lost commit result in transaction | Multi-record write | Invariants intact | Transaction reconciliation |
| NET-24 | Backup/object-store control-plane outage | Recovery | Honest RTO/RPO report | Restore dependencies |

Các mức fault/duration/số requests phải thích ứng từng lab. Mỗi case ghi expected behavior của engine và API thực, không áp một kết quả chung.

## 43. Runbook vận hành thí nghiệm

### Bước 1 — Nêu giả thuyết

Ví dụ: “Nếu write ACK bị mất sau commit, retry cùng operationId không tạo booking thứ hai.”

### Bước 2 — Chọn môi trường

- Test cluster cô lập.
- Dữ liệu tổng hợp.
- Phiên bản pinned.
- Kết nối ứng dụng đi qua fault injector.
- Có metrics và reset path.

### Bước 3 — Dựng workload và oracle

- Baseline RPS/latency.
- Operation IDs.
- Expected authoritative source state.
- Side-effect ledger.
- Tenant isolation cases.
- Freshness requirements.

### Bước 4 — Chốt network fault

- Cạnh source/destination.
- Hướng.
- Delay/loss/partition.
- Start/end marker.
- Duration.
- Cleanup/abort.

### Bước 5 — Chạy baseline

Kiểm tra source và projections có data đúng, offered load được phát đủ, không có lỗi cũ.

### Bước 6 — Inject

Kích hoạt fault theo kế hoạch. Đo actual reachability/latency/loss, không chỉ tin config.

### Bước 7 — Quan sát

- p99/errors/throttles.
- Driver retries/pool.
- Quorum/leader.
- UNKNOWN writes.
- CDC lag.
- Resource usage.
- Tenant fairness.

### Bước 8 — Heal

Remove rules, verify links; giữ tải có kiểm soát để quan sát catch-up.

### Bước 9 — Reconcile

- Booking/payment/inventory.
- Version/tombstones.
- Cache/search.
- Old leader fencing.
- Unknown operations.
- No unauthorized data leakage.

### Bước 10 — Báo cáo

- Fault thực tế.
- Safety pass/fail.
- Availability/latency by operation.
- Recovery-to-SLO time.
- RPO/RTO.
- Root cause.
- Runbook/capacity/retry improvements.

## 44. Runbook khi một thử nghiệm gây lỗi ngoài dự kiến

1. **Dừng inject và xác định phạm vi.** Không tiếp tục tăng loss/latency.
2. **Xác minh môi trường thử** không có traffic production.
3. **Dỡ fault rules/proxy toxics** theo cleanup plan.
4. **Không retry writes mù** khi outcome UNKNOWN.
5. **Chụp trạng thái cluster/driver/CDC**, đã redacted.
6. **Bảo vệ authoritative source** và dừng các workers có nguy cơ ghi sai.
7. **Reconcile logical operation ledger**, kiểm tra duplication/conflict.
8. **Kiểm tra split-brain/fencing** nếu có election.
9. **Giảm catch-up/backfill rate** nếu source bị quá tải.
10. **Quarantine các records/projections sai** trước khi phục vụ lại.
11. **Đánh dấu test FAIL/INCONCLUSIVE** thay vì ghi xanh khi dữ liệu chưa rõ.
12. **Cập nhật runbook và test oracle** sau khi điều tra.

## 45. Những sai lầm thường gặp

1. **“Timeout chắc chắn rollback.”** Không; ACK có thể mất sau commit.
2. **“Connection reset nghĩa DB không nhận request.”** Chưa chắc.
3. **“Packet loss 1% chỉ tăng latency 1%.”** TCP retransmission/tail có thể phi tuyến.
4. **“Delay 500 ms chính là network partition.”** Vẫn có thể liên lạc.
5. **“Tắt một node là đủ mô phỏng mọi partition.”** Thiếu asymmetric/cross-zone cases.
6. **“Driver tự reconnect nên app đã đúng.”** Business idempotency vẫn có thể sai.
7. **“Retry mọi exceptions là resiliency.”** Có thể tạo retry storm.
8. **“Jitter không cần vì timeout đã có.”** Có thể đồng bộ retries.
9. **“Không cần deadline tổng nếu từng attempt có timeout.”** Retry chain có thể kéo dài.
10. **“Client cancelled nghĩa server write bị hủy.”** Không chắc.
11. **“HTTP 200 nghĩa mọi replica/index đều có data.”** Phụ thuộc contract.
12. **“Một node healthy nghĩa cluster available cho writes.”** Phụ thuộc quorum.
13. **“Minority phải tiếp tục write để tăng availability.”** Có thể phá safety.
14. **“R+W>N tự bảo đảm linearizability cho mọi NoSQL.”** Phụ thuộc engine/model.
15. **“Leader cũ sẽ tự biến mất khỏi mọi client.”** Cần route refresh/fencing.
16. **“DNS switch chuyển mọi sockets ngay.”** Existing connections có thể còn.
17. **“Remove fault nghĩa recovery hoàn tất.”** Backlog/lag có thể còn.
18. **“Một retry tạo operationId mới vẫn idempotent.”** Không.
19. **“Database dedupe thay payment idempotency.”** Không.
20. **“Driver retryable writes giải quyết mọi duplicate business actions.”** Không.
21. **“Stale GSI read chứng minh write thất bại.”** Không.
22. **“Cache miss do timeout là NOT_FOUND.”** Không.
23. **“Search outage nên retry booking create.”** Nguy cơ duplicate.
24. **“Event v8 sau v9 có thể apply theo arrival order.”** Có thể rollback.
25. **“DELETE tombstone không cần nếu record đã biến mất.”** Late upsert có thể hồi sinh.
26. **“Trong partition chỉ cần đo QPS.”** Thiếu consistency/safety.
27. **“Tổng p99 đủ kết luận.”** Cần theo operation/tenant.
28. **“Closed-loop benchmark cho biết latency dưới offered RPS cố định.”** Có coordinated omission.
29. **“Completed throughput luôn bằng offered load.”** Có queue/drop/generator lag.
30. **“Proxy fault luôn tác động traffic node↔node.”** Có thể chỉ client↔backend.
31. **“Toxiproxy delay tương đương IP packet loss.”** Không.
32. **“tc trên host chung là vô hại.”** Có thể cắt connectivity thật.
33. **“Một chiều block giống hai chiều.”** Không.
34. **“Kết nối TCP còn mở nghĩa server reachable.”** Half-open có thể treo.
35. **“Increase pool size vô hạn để chống timeout.”** Làm overload.
36. **“Virtual threads giải quyết bottleneck DB.”** Không.
37. **“Circuit breaker fail-open phù hợp mọi chức năng.”** Sai cho inventory/auth.
38. **“Đo lỗi nhưng không ghi operationId vẫn đủ reconcile.”** Không.
39. **“Metrics chỉ client-side đủ chứng minh commits.”** Cần source ledger.
40. **“Một phiên bản giả lập in-memory chứng minh distributed consistency.”** Không.
41. **“Seed uniform đủ cho hot tenant.”** Không.
42. **“Không cần test TTL/delete trong partition.”** Có resurrection.
43. **“Cassandra consistency level giống mọi DC.”** Cần topology.
44. **“Redis WAIT làm writes không thể mất trong failover.”** Không universal.
45. **“DynamoDB GSI có strong read như base table.”** Không.
46. **“Global Tables tự bảo vệ mọi uniqueness business rule.”** Không.
47. **“Search index là authoritative source khi source timeout.”** Thường không.
48. **“Log mọi raw payload giúp debug.”** Có privacy/overload risks.
49. **“Test pass khi no exception.”** Có thể sai data.
50. **“Một thí nghiệm fault không cần cleanup/abort.”** Rủi ro cao.
51. **“Tất cả 503 do partition đều là regression.”** Có thể expected theo contract.
52. **“Tất cả stale reads đều hợp lệ vì eventual.”** Cần freshness bound.
53. **“Một single health endpoint đủ phát hiện split-brain.”** Cần authority/quorum evidence.
54. **“Sau khi healed không cần check data drift.”** Cần reconcile.
55. **“Không cần kiểm soát quyền khi fallback/retry.”** Tenant leakage.
56. **“Một runbook production có thể copy nguyên lệnh tc từ lab.”** Không.
57. **“Test xanh nghĩa RPO/RTO chắc đạt ở data scale thật.”** Cần DR/capacity drills.
58. **“Mất ACK của transaction commit luôn có trạng thái rollback.”** Có UNKNOWN.
59. **“Quorum read luôn thấy latest khi client đi sang mọi region.”** Phụ thuộc protocol.
60. **“Bỏ qua unknown outcomes để giảm false alarm.”** Không được coi là dữ liệu đúng.

## 46. Bài tập: dựng bộ fault tests cho hệ Booking

Một hệ giả định:
- Java 21 Booking API.
- MongoDB replica set ba nodes làm authoritative booking store.
- Redis cache.
- OpenSearch read projection từ CDC.
- Payment provider dùng idempotency keys.
- Một tenant rất lớn chiếm 60% traffic.
- API create booking deadline 1.2 giây.
- Booking search freshness SLO 5 giây.
- Booking slot chỉ cho một reservation CONFIRMED.
- RPO mục tiêu theo hợp đồng của source, không áp cho search cache.
- Backup/restore workflow đã định nghĩa riêng.

### A. Mất kết nối

1. Test connect refused trước request.
2. Test socket reset sau request write.
3. Test ACK drop sau server commit.
4. Phân biệt outcome CONFIRMED, REJECTED, UNKNOWN.
5. Xây operation ledger để retry không duplicate.

### B. Packet loss

1. Chọn 0%, 1%, 5% loss và burst loss.
2. Test TCP retransmit/RTT.
3. Đo p99, retry amplification, connection pool.
4. Vì sao không đánh đồng proxy timeout với loss IP thực?
5. Làm sao dọn fault rules đúng khi test process crash?

### C. High latency

1. Tạo +300 ms upstream, +800 ms downstream.
2. Thiết kế HTTP/DB/pool deadlines.
3. Dự đoán queue growth dưới fixed offered load.
4. Khi nào fail fast tốt hơn retry?
5. Kiểm tra backpressure và tenant fairness.

### D. Partition

1. Chia A | B,C.
2. Xác định leader ở A trước fault.
3. Dự kiến behavior theo write concern/quorum của cấu hình.
4. Kiểm tra election/fencing.
5. Hệ trả gì cho writes ở minority?
6. Sau heal, verify replica catch-up như thế nào?

### E. Idempotency

1. Tạo booking OP-NEW-1.
2. Server commit nhưng client timeout.
3. Client retry với cùng operationId.
4. Client retry với ID mới sẽ gây rủi ro gì?
5. Hai payload khác dùng cùng operationId phải xử lý sao?
6. Payment provider retry cần idempotency riêng không?

### F. Source và projection

1. MongoDB source v8, OpenSearch v7.
2. CDC bị partition 10 giây.
3. Booking source vẫn ACK.
4. Search không thấy booking có là booking failure không?
5. Catch-up cần version/tombstone bảo vệ như thế nào?
6. Có nên negative-cache NOT_FOUND từ search timeout?

### G. Redis

1. Cache không reachable 30 giây.
2. Có bypass về MongoDB không?
3. Làm sao tránh stampede?
4. Primary failover có thể mất writes ACK theo replication semantics nào?
5. Test TTL và stale fill sau reconnect.

### H. Cassandra/DynamoDB đối chiếu

1. LOCAL_QUORUM khác ONE khi replica unreachable thế nào?
2. Vì sao phải biết nodes nào sở hữu partition?
3. DynamoDB managed service fault injection khác self-hosted Cassandra?
4. GSI eventual consistency ảnh hưởng test oracle?
5. Global Tables conflict/region failover cần test gì?

### I. Benchmark

1. 200 logical operations/s, một phần attempts timeout và retry.
2. Đo offered/sent/completed rate.
3. Tính retry amplification.
4. Vì sao closed-loop làm giảm workload khi hệ chậm?
5. Nêu p99 theo từng operation.
6. Cách xác nhận generator không tự trở thành bottleneck.

### J. Bất biến

Thiết kế assertions:
- Không double-book.
- Không duplicate payment.
- Không lùi sourceVersion.
- Không hồi sinh delete.
- Không cross-tenant.
- Không stale leader writes.
- Unknown commit được reconcile.

Với mỗi bất biến, chỉ ra **nguồn dữ liệu authoritative** và query/ledger cần đọc.

### K. Fault matrix

Thiết kế ít nhất 15 scenarios từ NET-01..NET-24 với:
- Link và direction.
- Injection tool.
- Fault start/end.
- Workload.
- Expected availability.
- Safety assertions.
- Recovery steps.
- Cleanup.
- Metrics.

### L. Runbook sự cố

Tại phút 0, API timeouts tăng sau khi một AZ mất kết nối; 300 booking creates trả UNKNOWN.

1. Ngăn retry storm.
2. Chụp topology/quorum/election epoch.
3. Không tạo booking mới cho cùng operationId.
4. Reconcile source/operation ledger.
5. Đo data loss theo ACK contract.
6. Theo dõi CDC/search/cache catch-up.
7. Bảo vệ old leader fencing.
8. Báo RPO/RTO và customer-impact counts.

### Hướng giải

Một phương án hoàn chỉnh:
- Tách **connect failure, in-flight reset, lost ACK, loss, delay, partition** thành tests riêng.
- Dùng **stable operationId, idempotent conditional writes và source reconciliation**.
- Đặt **overall deadlines, bounded retries with jitter, bulkheads và rate limits**.
- Khi partition, đánh giá theo **quorum/consistency/operation**, không buộc cả cụm phải trả thành công.
- Đo **safety** độc lập với **availability**.
- Dùng **fault proxy hoặc tc/netem trong môi trường cô lập** và kiểm tra đường fault có hiệu lực thật.
- Duy trì offered load có kiểm soát, đo retries, p99 và pool saturation.
- Sau heal, kiểm tra **election/fencing, replica catch-up, CDC/index lag và dữ liệu theo operationId**.
- Không coi **timeout, stale index và lost ACK** là database rollback chắc chắn.
- Báo thí nghiệm **PASS/FAIL/INCONCLUSIVE** theo bằng chứng, không chỉ command return code.

## 47. Checklist trước khi chạy fault-under-load test

1. **Đã xác định operation và consistency contract cần kiểm tra?**
2. **Có mapping source-of-truth, replicas và derived stores?**
3. **Biết topology, network edges, routes và fault domains?**
4. **Có ranh giới test cô lập, được phê duyệt?**
5. **Có backup/restore hoặc reset test data?**
6. **Có synthetic tenants/operations, không PII thật?**
7. **Có stable operationId và outcome ledger?**
8. **Có oracle safety cho duplicate booking/payment?**
9. **Có sourceVersion/tombstone assertions?**
10. **Có tenant authorization/fallback tests?**
11. **Có baseline load/latency/error rate?**
12. **Có offered vs sent vs completed metrics?**
13. **Có driver/server pool metrics?**
14. **Có fault direction cụ thể upstream/downstream?**
15. **Đo actual loss/delay/reachability thay vì chỉ tin config?**
16. **Có test connect failure và established-socket reset?**
17. **Có test response ACK lost sau commit?**
18. **Có test random và burst packet loss?**
19. **Có test high RTT và jitter?**
20. **Có test asymmetric partition và minority/majority?**
21. **Có quorum/leader/fencing assertions?**
22. **Có explicit overall deadline/retry budget?**
23. **Retry chỉ cho lỗi hợp lệ, có jitter/backoff?**
24. **Không tự retry conditional conflict như transient error?**
25. **Có per-tenant bulkheads/admission?**
26. **Có check source load khi cache failover?**
27. **Có CDC/index lag metrics?**
28. **Có bounded polling theo freshness SLO?**
29. **Có kiểm tra stale delete/upsert order?**
30. **Có trace physical attempts per logical operation?**
31. **Có test reconnection pool và resource leaks?**
32. **Có cảnh báo nếu old leader còn nhận writes?**
33. **Có stop conditions khi data safety fail?**
34. **Có cleanup nếu injector crash?**
35. **Có recovery window sau remove fault?**
36. **Có verify dữ liệu authoritative sau fault?**
37. **Có reconciliation cho UNKNOWN outcomes?**
38. **Có kiểm chứng search/cache hội tụ?**
39. **Có time-to-SLO, RPO/RTO nếu thuộc scenario?**
40. **Có báo safety/availability/recovery riêng?**
41. **Có lưu engine/driver/proxy versions và seed?**
42. **Có runbook và người sở hữu faults/rollback?**
43. **Không coi fake/in-memory unit test là proof of cluster quorum?**
44. **Không coi test không lỗi là proof of business correctness?**
45. **Có kế hoạch retest khi thay driver/leader protocol/quorum settings?**

**Kết luận:** Kiểm thử **ngắt kết nối, mất gói, độ trễ cao và phân hoạch mạng** phải mô phỏng những đường lỗi thực tế, giữ tải có kiểm soát và kiểm tra hành vi **trước, trong, sau khi fault được gỡ**. Một request timeout có thể đã commit; retry phải giữ **logical operationId**, phân loại UNKNOWN và reconcile với nguồn authoritative. Quorum/election quyết định availability của từng thao tác; không áp một kết luận CAP máy móc cho mọi engine. Độ trễ/loss làm tăng in-flight operations, saturate pools và tạo retry storms, nên cần **deadline tổng, backoff jitter, admission và tenant bulkheads**. Quan trọng nhất, đừng dừng ở việc “cluster xanh lại”: phải xác minh **không double-book, không duplicate payment, không mất tenant isolation, không lùi version, không hồi sinh tombstone**, cùng replica/CDC/search/cache convergence và recovery-to-SLO. Một thí nghiệm đạt yêu cầu khi **fault được kiểm soát, dữ liệu có oracle rõ và kết quả được báo minh bạch theo safety, availability, consistency và thời gian phục hồi**.
