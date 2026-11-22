# Đo tải khi rebalance, tạo chỉ mục hoặc thay đổi topology

Một cụm NoSQL có sáu node đang xử lý 18.000 requests/giây, p99 đọc dưới 80 ms và p99 ghi dưới 120 ms. Nhóm vận hành thêm hai node để chuẩn bị cho một chiến dịch lớn, đồng thời chạy xây chỉ mục mới. Khi dữ liệu được chuyển từ node cũ sang node mới, p99 đọc tăng lên 700 ms, một số partitions bị throttling, CDC consumer tụt hậu và disk free trên node nguồn giảm nhanh do compaction. Trong khi đó dashboard tổng thể vẫn hiển thị CPU trung bình chỉ 45% và throughput gần mức bình thường. Nếu chỉ nhìn CPU và số request thành công, nhóm có thể tuyên bố thay đổi “không ảnh hưởng dịch vụ”, dù một phần người dùng đang bị timeout và cửa sổ phục hồi dữ liệu có nguy cơ mất.

**Đo tải trong quá trình thay đổi topology** khác với benchmark CRUD trên một cluster ổn định. Hệ thống phải phục vụ traffic nghiệp vụ **đồng thời** với công việc nền: sao chép shard/replica, xây index, merge segments, tạo SSTables, di chuyển hash slots, chọn leader, đồng bộ catch-up hoặc cập nhật metadata định tuyến. Những công việc này cạnh tranh CPU, RAM, băng thông, IOPS, cache, transaction capacity và cả khoảng trống cần để phục hồi khi lỗi.

Trong chương **Kiểm thử lỗi và tải** của module **Database No SQL**, bài học trình bày cách xây dựng một phép thử có thể trả lời bốn câu hỏi:

1. **Ảnh hưởng:** Trong quá trình rebalance, tạo chỉ mục hoặc topology change, p95/p99, throughput, lỗi và business correctness thay đổi bao nhiêu?
2. **An toàn:** Cụm còn chịu được thêm một lỗi node/zone, giữ được acknowledged writes, replication/CDC window và headroom không?
3. **Tốc độ:** Bao lâu hoàn tất chuyển dữ liệu/index build và bao lâu hệ trở về trạng thái bình thường?
4. **Quyết định vận hành:** Tại tải nào nên tiếp tục, giảm tốc, tạm dừng hoặc rollback/roll-forward thay đổi?

> **Nguyên tắc:** Không đánh giá thay đổi bằng mỗi “node mới đã lên” hoặc “index tạo thành công”. Phép thử phải giữ workload đại diện chạy xuyên suốt **baseline → chuyển đổi → catch-up → hồi phục**, quan sát tail latency, lỗi, độ trễ nền, phân bố theo node/tenant, chi phí tài nguyên và tính đúng đắn của kết quả.

## 1. Ba loại thay đổi cần phân biệt

| Hoạt động | Hành động nền điển hình | Nguy cơ chính khi đang có tải |
|---|---|---|
| **Rebalance** | Chuyển shards/partitions/replicas, stream data, cập nhật routing | I/O/network tranh chấp, hotspot mới, thiếu headroom |
| **Index build** | Scan source, sort/map keys, ghi index segments, catch-up mutations | CPU/IO/space tăng, write amplification, query plan đổi |
| **Topology change** | Thêm/bớt node, replica set reconfiguration, failover, đổi zone/region | Leader election, quorum/availability, stale route, replica lag |
| **Reshard/repartition** | Di chuyển dữ liệu sang shard key/partition layout mới | Backfill/CDC lag, version conflicts, fan-out queries |
| **Upgrade có rolling restart** | Từng node restart và bắt kịp replica | Capacity N−1, cache lạnh, mixed-version behavior |
| **Scale managed NoSQL** | Service tự split/move partitions hoặc đổi throughput | Throttling, quota, transient routing changes |

### 1.1. Rebalance là thay đổi placement, chưa chắc đổi khóa

Một shard có thể chuyển từ node A sang B mà logical key không đổi. Đổi shard key hoặc bucket algorithm là một migration rộng hơn; phép thử cần bao gồm cả access patterns và correctness.

### 1.2. Tạo index làm việc nền nhưng có thể ảnh hưởng foreground

Một index build được mô tả “online” không có nghĩa **không dùng tài nguyên, không lock ở bất kỳ giai đoạn nào hoặc không gây tail latency**. Semantics tùy sản phẩm, phiên bản và topology.

### 1.3. Topology change có thể gây gián đoạn rất ngắn nhưng quan trọng

Đổi leader/route có thể chỉ kéo dài vài giây, song p99/p99.9 và timeout rate bộc lộ rõ. Biểu đồ trung bình 5 phút có thể che sự kiện này.

### 1.4. Một thay đổi có thể kích hoạt thay đổi khác

Thêm node có thể kéo theo rebalance, replica bootstrap, cache warmup và index catch-up. Phải ghi chính xác **timeline của từng sự kiện** để giải thích kết quả.

## 2. Benchmark ổn định khác load test đang thay đổi

Benchmark CRUD thông thường đo tốc độ khi phân bố dữ liệu, cache, index và leader tương đối ổn định. Load test thay đổi topology tạo thêm một công việc có thời lượng hữu hạn và resource profile biến thiên theo thời gian.

~~~mermaid
flowchart LR
    PRE["Baseline ổn định"] --> START["Bắt đầu thay đổi"]
    START --> MOVE["Data/index movement"]
    MOVE --> CATCH["Replication/CDC catch-up"]
    CATCH --> SETTLE["Compaction/cache settling"]
    SETTLE --> POST["Post-change steady state"]
~~~

### 2.1. Đừng chỉ so hai điểm trước/sau

Nếu baseline p99=70 ms và sau rebalance p99=60 ms, chưa nói gì về 40 phút giữa quá trình khi p99=900 ms. Phải đo toàn bộ cửa sổ chuyển.

### 2.2. Đừng chỉ đo thời gian chuyển đổi

Rebalance hoàn tất trong 12 phút nhưng foreground requests timeout 10% có thể tệ hơn rebalance trong 25 phút với latency ổn định. Thời gian migration và user impact là hai mục tiêu.

### 2.3. Cần pha ổn định sau thay đổi

Tool báo migration complete nhưng compaction, cache misses, index catch-up hoặc replication vẫn đang cao. Định nghĩa post-change stable qua metrics, không chỉ dựa job exit status.

### 2.4. Cần cùng điều kiện so sánh

Nếu một ngày test có dữ liệu 50 GB và một ngày có 1 TB, hoặc read/write mix khác nhau, không thể quy mọi chênh lệch về topology change.

## 3. Đầu tiên hãy định nghĩa SLO và mục tiêu

Ví dụ một API Orders:

~~~text
At representative peak workload:
    GET /orders/{id}    p99 <= 150 ms
    POST /orders        p99 <= 250 ms
    Error rate          <= 0.5%
    Critical write availability >= agreed SLO

During topology operation:
    No lost acknowledged writes
    No cross-tenant data exposure
    No unbounded CDC lag
    No node below safe disk reserve
    Finish within approved maintenance budget
~~~

Các con số **minh họa**, không phải chuẩn cho mọi hệ NoSQL.

### 3.1. SLO của business API quan trọng hơn ops/s của DB

Một request có thể gọi nhiều queries, indexes hoặc transactions. Đo client-visible end-to-end latency và business success; song song đo DB command latency để phân biệt bottleneck.

### 3.2. Chọn percentile theo mức nhạy cảm

p50 cho trải nghiệm phổ biến, p95/p99 cho tail, p99.9 khi có đủ samples và dịch vụ cần. Nếu một nhóm tenants nhỏ chịu lỗi, aggregate percentile có thể che nó.

### 3.3. Ràng buộc correctness

Nếu tăng throughput bằng cách giảm write concern/quorum hoặc bỏ transaction checks, phép so sánh không còn cùng durability contract. Load test không được âm thầm thay nghĩa của kết quả.

### 3.4. Đặt abort criteria trước khi bắt đầu

Ví dụ write error vượt ngưỡng trong một cửa sổ, node free bytes xuống dưới mức cần cho compaction hoặc CDC lag sắp vượt retention thì giảm/tạm dừng tác vụ nền. Các ngưỡng phải được owner phê duyệt và phù hợp topology.

## 4. Những đại lượng cốt lõi phải đo

| Nhóm | Metrics điển hình | Câu hỏi |
|---|---|---|
| Foreground throughput | Accepted/attempted/succeeded requests/s | Load thực có được phục vụ không? |
| Latency | p50/p95/p99/p99.9 theo API/operation | Người dùng nào bị ảnh hưởng? |
| Errors | Timeout, 429, 5xx, version conflict, unavailable | Lỗi thuộc loại gì? |
| Queues | Pending requests, thread pool, SDK pool wait | Có bị backlog che không? |
| CPU/RAM | Per-node usage, GC, heap, page cache | Có contention không? |
| Disk | IOPS, bandwidth, latency, queue depth, free bytes | Scan/index/compaction có bóp I/O? |
| Network | Inter-node throughput, retransmit, link saturation | Streaming cạnh tranh traffic? |
| Replication | Replica lag, sync state, quorum health | Có nguy cơ mất availability/history? |
| CDC | Oldest unprocessed age, available history horizon | Consumer còn bắt kịp được không? |
| Migration | Bytes/tasks moved, remaining, retries, elapsed | Tiến độ nào đạt? |
| Index | Build phase, pending data, index lag, size | Index sẵn dùng chưa? |
| Data correctness | Lost ACKed writes, stale reads, duplicate IDs | Trạng thái nghiệp vụ có đúng không? |
| Topology | Owner map, leaders, shards/node, zone placement | Routing và phân bố có hợp lý? |
| Cost | RU/RCU/WCU, node-hours, egress/storage | Thay đổi có đáng giá không? |

### 4.1. Không dùng cluster average làm số duy nhất

CPU trung bình 45% có thể gồm một node 98% và những node khác 35%. Node nóng có thể quyết định p99 của tất cả users trên shard nó giữ.

### 4.2. Đo per-tenant, per-shard và per-operation

Thêm phân nhóm bounded, tránh metrics cardinality vô hạn. Một whale tenant có thể chỉ chịu throttling khi dữ liệu của họ chuyển.

### 4.3. Đo hiệu năng đọc/ghi riêng

Index build thường tăng writes/IO nhưng cải thiện query reads sau khi hoàn tất; cân bằng trung bình read-write có thể che tradeoff.

### 4.4. Đo cả nghiệp vụ không thành công đúng

Một CAS conflict được mong đợi không giống timeout, mất quorum hoặc duplicate order. Không cộng mọi status khác 200 vào cùng “DB fail”.

## 5. Chuẩn hóa workload đại diện

Một workload thực tế không chỉ là 100% get-by-ID:

~~~text
60% point reads:
    get order by tenant + orderId
20% bounded range queries:
    list latest orders by tenant
15% writes:
    create/update order, conditional version
 5% transactions / counter / outbox:
    reserve inventory or confirm booking
~~~

### 5.1. Data distribution là yếu tố thứ nhất

10 triệu IDs phân phối uniform và 10 triệu IDs phân phối Zipf/hot tenants tạo hai profile khác hẳn. Tạo workload có tenant size skew, hot keys, cold keys và large documents.

### 5.2. Kích thước payload

Đo document size distribution: small summary 1–4 KB, large nested documents, batch writes và những queries trả nhiều results. Payload lớn làm tăng network và disk work.

### 5.3. Cache nóng và cache lạnh

Benchmark chỉ lặp một tập key nhỏ sẽ nằm trong RAM, che disk/index build pressure. Chọn working set có tỷ lệ hot/cold tương tự production.

### 5.4. Ghi có điều kiện

Tạo contention thực trên cùng entity nếu production dùng optimistic concurrency. Test chỉ inserts vào IDs ngẫu nhiên không thể hiện version conflicts và hotspots.

### 5.5. Các batch nền của ứng dụng

Ngoài API traffic, include CDC consumer, scheduled TTL scans, reporting query hoặc backup upload nếu chúng thường cùng xuất hiện trong maintenance window.

## 6. Khối lượng dữ liệu ban đầu phải có ý nghĩa

### 6.1. Dataset quá nhỏ

Index build trên 10.000 records hoàn tất trong vài giây, không bộc lộ disk spill, cross-shard streaming, cache eviction hoặc merge backlog ở 1 tỷ records.

### 6.2. Chọn cả độ lớn và hình dạng

Mô phỏng số partitions, documents/partition, indexes, tombstones, TTL, array sizes và hot tenant distribution; không chỉ tổng số GB.

### 6.3. Schema và indexes phù hợp

Test index mới trên một bảng không có các indexes cũ, hoặc với compression settings khác, có thể đánh giá sai write amplification.

### 6.4. Dữ liệu nhạy cảm

Không sao chép production PII trực tiếp sang load environment thiếu kiểm soát. Dùng dữ liệu tổng hợp/ẩn danh theo chính sách và giữ distribution quan trọng.

### 6.5. Bản backup có thể dựng lại

Trước khi thử destructive topology faults trong môi trường test, phải có khả năng reset dataset/topology để các runs so sánh được.

## 7. Open-loop và closed-loop load generation

Hai kiểu tạo tải ảnh hưởng cách nhìn p99 khi hệ bị chậm.

### 7.1. Closed-loop

Mỗi virtual user gửi request, đợi response rồi gửi request tiếp. Khi server chậm, request rate tự giảm, khiến bảng throughput thấp nhưng p99 có vẻ “ít tệ hơn”.

### 7.2. Open-loop

Request arrivals theo lịch/target rate, độc lập với response time trong phạm vi load generator đủ năng lực. Khi server quá tải, queues và latency sẽ bộc lộ.

### 7.3. Coordinated omission

Nếu generator ngừng gửi requests khi đang chờ response chậm, nó có thể bỏ qua những requests lẽ ra đến trong thời gian pause, làm underestimate tail latency. Chọn arrival model và phương pháp đo phù hợp.

### 7.4. Saturation của chính load generator

Nếu CPU hoặc network của generator hết năng lực, observed RPS không còn là intended RPS. Theo dõi scheduled/attempted/succeeded, generator resource và client-side queue.

### 7.5. Nên thử cả hai

Closed-loop đại diện hành vi người dùng có think time; open-loop giúp phát hiện overload và queue buildup. Định nghĩa điều kiện so sánh rõ.

## 8. Phương pháp phân pha phép thử

~~~mermaid
flowchart TD
    SET["Setup: same data/config"] --> WARM["Warmup"]
    WARM --> BASE["Baseline load"]
    BASE --> TRIG["Trigger index/rebalance/topology event"]
    TRIG --> DUR["Measure while change is running"]
    DUR --> CATCH["Catch-up and settling"]
    CATCH --> POST["Post-change steady load"]
    POST --> VERIFY["Correctness, SLO, cost review"]
~~~

### 8.1. Warmup

Làm nóng JIT, connection pools và phần cache theo điều kiện đã định. Không kéo dài warmup để làm data nhỏ trở thành toàn bộ in-memory nếu production không vậy.

### 8.2. Baseline

Chạy workload đủ lâu để có distribution p99 đáng tin và đo background tasks tự nhiên. Lưu cấu hình cluster, dataset, code version và ngày/giờ.

### 8.3. Trigger có timestamp

Ghi thời điểm bắt đầu index build/cluster rebalance, API request/command ID, topology state và job version. Đánh dấu sự kiện lên latency time series.

### 8.4. During

Ghi sampling ngắn phù hợp (ví dụ 5–15 giây với aggregated counters, không nhất thiết scrape mọi thứ mỗi giây), theo dõi progress và window của worst tail.

### 8.5. Catch-up

Chỉ chuyển sang “ổn định” khi replication/CDC lag, index status, compaction backlog, cache hit rate và error rate đã về guardrails, không chỉ khi task báo finished.

### 8.6. Post-change

Chạy cùng arrival rate, query mix và dataset distribution để so lợi ích/chi phí. Có thể cần test riêng tại mức tải cao hơn khi cluster mới có thêm capacity.

## 9. Thiết kế ma trận thí nghiệm

| Run | Traffic | Hoạt động nền | Failure mode | Mục tiêu |
|---|---|---|---|---|
| B0 | Normal peak | Không | Không | Baseline |
| B1 | 1.5× peak | Không | Không | Baseline headroom |
| R1 | Normal peak | Add node + rebalance | Không | Ảnh hưởng thông thường |
| R2 | 1.5× peak | Rebalance | Không | Peak contention |
| R3 | Normal peak | Rebalance | Node lag/retry | Độ bền dưới lỗi |
| I1 | Normal peak | Create index | Không | Build impact |
| I2 | Mixed heavy writes | Create index | Throttle | Index catch-up |
| T1 | Normal peak | Rolling node restart | Election | Availability |
| T2 | Normal peak | Node removal | N−1 capacity | Quorum/headroom |
| C1 | Normal peak | Rebalance + index build | Không | Worst overlap theo lịch thực |

### 9.1. Thay đổi một biến tại một thời điểm

Để biết tác động riêng của rebalance hay index build, không bắt đầu cả hai trong run đầu. Sau đó mới thử overlap nếu production schedule có thể trùng.

### 9.2. Có runs lặp

Một kết quả duy nhất dễ bị ảnh hưởng bởi cloud noisy neighbor, cache state hoặc garbage collection. Chạy lại trong điều kiện tương đồng và so distribution/deltas.

### 9.3. Đảo thứ tự thử nghiệm khi phù hợp

Nếu test nào chạy sau cũng có cache ấm hơn, kết quả bị order bias. Reset/deterministic preparation hoặc chạy counterbalanced order để so.

### 9.4. Không dùng cùng một cụm đã biến đổi làm baseline cũ

Sau index build/topology change, cluster state khác. Muốn thử tác động trong các cấu hình, cần snapshot/restore/reset phù hợp hoặc so có ghi rõ khác biệt.

## 10. Định nghĩa timeline và milestone

Một phép thử rebalance nên ghi:

~~~text
T0: baseline steady
T1: node added / rebalance requested
T2: first data movement begins
T3: maximum source/target IO
T4: last shard moved
T5: replica/CDC lag returns within target
T6: compaction and cache stabilize
T7: post-change SLO observed
~~~

### 10.1. Thời gian hoàn thành có nhiều nghĩa

`T4-T1` là orchestration/movement time, trong khi `T7-T1` là time to full operational recovery. Cả hai đều quan trọng.

### 10.2. “Ít lỗi hơn” cần định lượng

Thay vì nói “có vài timeouts”, đo count/time window, tỷ lệ trên attempted traffic, tenant/operation, và accumulated SLO violation duration.

### 10.3. Chú ý event marking

Không có annotation của index build progress hoặc routing changes, khó phân biệt p99 spike do compaction hay một burst ứng dụng tình cờ.

## 11. Throughput, latency và queueing

Hệ có capacity service rate \(\mu\) và arrival rate \(\lambda\). Khi arrival rate vượt capacity khả dụng trong thời gian dài, backlog tăng.

\[
\Delta Q / \Delta t \approx \lambda-\mu,\quad\text{khi }\lambda>\mu.
\]

### 11.1. Ví dụ

Trước rebalance cụm xử lý 15.000 requests/s; trong rebalance chỉ xử lý ổn định 12.000 requests/s. Nếu tải vẫn tới 15.000/s, backlog lý tưởng tăng 3.000 requests mỗi giây nếu không bị từ chối/hạn chế.

### 11.2. Little's Law trong điều kiện ổn định

\[
L \approx \lambda W
\]

với \(L\) là số requests trung bình đang trong hệ, \(\lambda\) là completion/arrival throughput cân bằng và \(W\) là latency trung bình. Không áp dụng máy móc khi queue đang tăng vô hạn hoặc hệ không ổn định.

### 11.3. Năng lực nền ăn vào năng lực foreground

Migration có thể đẩy \(\mu\) xuống vì I/O contention, không phải vì client tăng \(\lambda\). Đó là lý do giữ arrival rate cố định khi so.

### 11.4. Throttling là một cơ chế bảo vệ

429/overload rejection có thể giữ tail latency cho requests được nhận nhưng làm giảm success rate. Cần đo cả rejected requests và retry load, không chỉ latency của successes.

## 12. Percentile có thể bị diễn giải sai

Giả sử 99% requests mất 20 ms, 1% mất 2 giây. Mean có thể trông chấp nhận được, nhưng người dùng thuộc nhóm 1% có trải nghiệm rất xấu.

### 12.1. Đừng lấy trung bình p99 của từng node

p99 của toàn dịch vụ không phải mean p99 node A/B/C. Cần merge raw latency histogram/distribution theo cách giữ trọng số đúng.

### 12.2. Đo nhiều cửa sổ

Biểu đồ 5 phút có thể làm mờ 10 giây failover với 80% requests timeout. Ghi sự kiện và aggregated windows đủ ngắn.

### 12.3. Chia theo error và success

Nếu chỉ tính p99 của successful requests, requests timeout bị loại và latency “đẹp” giả. Báo cả error rate, deadline violations và latency theo outcome.

### 12.4. Percentile cần đủ samples

p99.9 của 300 requests chưa đủ ổn định để đưa kết luận mạnh. Với low traffic/rare operations, xét counts, max, confidence intervals và observation windows.

### 12.5. Tăng p99 sau khi mọi thứ hoàn tất

Có thể do index mới không được query planner chọn, cache warmup chưa đủ hoặc data placement skew. Đừng bỏ qua post-change regression.

## 13. Chỉ số “degradation” có thể định lượng

Ví dụ:

\[
D_{p99} = \frac{p99_{\text{during}}}{p99_{\text{baseline}}}.
\]

Nếu p99 bình thường 100 ms và trong index build 350 ms thì \(D_{p99}=3.5\). Đây là tỷ số mô tả chứ không phải một ngưỡng universal.

### 13.1. Performance budget

Nếu p99 SLO 250 ms, baseline 100 ms còn 150 ms headroom. Một thao tác làm p99 lên 220 ms vẫn đạt SLO nhưng đã dùng gần hết dự phòng.

### 13.2. Error-budget cost

Tính số requests vượt latency SLO/lỗi trong maintenance window. Nếu 2% requests thất bại trong 30 phút ở traffic 10.000/s, đó là nhiều request, dù mỗi phút nghe nhỏ.

### 13.3. Duration matters

Spike p99 1 giây có tác động khác p99 400 ms kéo dài 3 giờ. Báo cả severity và thời lượng.

### 13.4. Tổng chi phí thay đổi

Một index build nhanh nhưng dùng 4× RU/IO và tăng cloud cost có thể không tối ưu; đo performance-cost tradeoff.

## 14. Rebalance: nguồn tạo tải nền

Khi di chuyển partitions/shards/replicas:

~~~mermaid
flowchart LR
    SRC["Old owner"] -->|Stream data| DST["New owner"]
    SRC -->|Serve foreground reads/writes| CLIENT["Client"]
    DST -->|Build files/indexes| DATA["Target storage"]
    CTRL["Control plane"] -->|Update route/ownership| SRC
    CTRL --> DST
~~~

### 14.1. Source reads cạnh tranh với user reads

Copy nhiều TB từ source dùng disk bandwidth và page cache; point reads có thể tăng latency do cache eviction/IO queues.

### 14.2. Destination writes cạnh tranh với foreground writes

Target lưu data mới, index rebuild và compaction, vừa phục vụ requests nếu đã trở thành owner. Disk IOPS/capacity cần tính peak.

### 14.3. Inter-node network

Migration traffic có thể saturate links và tăng replica RTT. Đo băng thông tổng, packet retransmits và write quorum latency.

### 14.4. Metadata/routing movement

Route thay đổi có thể gây stale client errors, retries và scatter queries nếu router chưa cập nhật đồng nhất.

### 14.5. Rebalance một số shards có thể dài hơn chuyển tất cả còn lại

Skew, hot partitions, slow disk/node hoặc một shard rất lớn tạo long tail của chính tác vụ nền. Đo per-shard progress, không chỉ % tổng.

## 15. Tính thời gian streaming và catch-up

Một ước lượng đơn giản:

\[
T_{\text{copy}}\approx \frac{\text{bytes cần chuyển}}{\text{effective transfer bandwidth}}.
\]

Nếu cần chuyển 120 GiB qua tốc độ thực 80 MiB/s:

\[
T\approx\frac{120\times1024}{80}=1536\ \text{s}\approx25.6\ \text{phút}.
\]

Chưa tính contention, indexes, retries, network handshake và compaction.

### 15.1. Nếu nguồn vẫn thay đổi

Sau snapshot phải catch up mutations. Nếu source tạo 25 MiB/s changes và dest chỉ apply 20 MiB/s, lag tăng thay vì giảm; cutover không thể hoàn tất ở tốc độ ấy.

### 15.2. Nếu capacity còn 60 MiB/s sau foreground reservation

Số bytes cần chuyển 120 GiB chia 60 MiB/s vào khoảng 34 phút, chưa tính overhead. Luôn đo **effective available** bandwidth, không dùng NIC advertised speed.

### 15.3. Không lấy linear model làm lời hứa

Tốc độ di chuyển biến thiên theo partition sizes, rate limits, background tasks và garbage collection. Dùng số đo thực để dự báo lại.

### 15.4. Khi nào nên throttle?

Khi user SLO/error budget vượt guardrail, replica lag nguy hiểm hoặc disk headroom thấp, giảm background streams/parallelism nếu API hỗ trợ.

## 16. Headroom và lỗi N−1 trong lúc rebalance

Một cụm bốn node chạy 70% tải mỗi node về CPU/IO. Nếu một node mất, tải của nó cần phân phối lại, có thể khiến ba nodes còn lại vượt capacity.

### 16.1. Không chỉ cộng capacity

Thêm node chưa tăng capacity sử dụng ngay nếu dữ liệu chưa rebalance và hotspot vẫn trên node cũ.

### 16.2. Failure trong lúc migration

Node đang chuyển shard có thể chết; source/target có thể cần resume, rollback progress hoặc rebuild. Test phải tuân thủ vendor protocol để không phá replicated data.

### 16.3. Safety reserve

Rebalance, compaction và replica rebuild có thể cần ghi temporary data trước khi giải phóng old files. Một cụm đang 90–95% disk used không nhất thiết có thể di chuyển an toàn.

### 16.4. Rebalance concurrent với backup

Backup staging/snapshot có thể giữ old segments và tăng disk consumption. Test overlap nếu lịch production có thể trùng, hoặc lên chính sách tránh overlap.

### 16.5. Sizing theo node nóng nhất

Không dùng percent free trung bình khi một node/volume sắp đầy. Đo physical free bytes, inodes, max per-node utilization và shard distribution.

## 17. Index build: điều gì dùng tài nguyên?

Một index build có thể thực hiện:

~~~text
Scan source records
    -> Extract index keys
    -> Sort/buffer/partition
    -> Write index pages/segments
    -> Catch up writes that occurred during build
    -> Validate/commit index metadata
    -> Become queryable
~~~

Pipeline thực tế khác nhau theo engine và index type.

### 17.1. Scan cost

Đọc toàn bộ collection lớn có thể làm nóng I/O và đẩy working set của API ra khỏi page cache.

### 17.2. Sort/temporary spill

Index cần sắp key có thể dùng RAM và ghi temp files; disk queue và headroom quan trọng.

### 17.3. Write amplification

Sau khi thêm index, mỗi write có thể cập nhật index; dù build xong, steady-state write latency/throughput có thể khác baseline.

### 17.4. Catch-up mutations

Nếu index build chạy online trong lúc writes tiếp tục, engine cần đưa các changes vào index; write-heavy workload có thể làm build kéo dài.

### 17.5. Commit/activation phase

Một số engine có giai đoạn lock/metadata switch hoặc index visibility rules; không tự suy “online build” nghĩa không có short stall.

## 18. Cách đo lợi ích và giá phải trả của index mới

Đặt hai loại benchmark:

1. **Trong lúc build:** foreground latency/errors và build progress.
2. **Sau khi build:** query plan/scanned rows/bytes, p99 reads, p99 writes, storage/index size.

### 18.1. Tránh kiểm chỉ câu truy vấn được index hưởng lợi

Thêm index có thể giúp `findByEmail` nhưng tăng write latency cho `updateCustomer` và compaction pressure. Đo toàn bộ mix.

### 18.2. Planner có thể không chọn index

Index created không đảm bảo một query sử dụng nó. So execution plan, filter selectivity, docs scanned/returned và statistics.

### 18.3. Index sparse/unique/multikey

Giá trị null, missing, arrays, duplicates và uniqueness constraints có thể khiến build fail hoặc semantic query thay đổi. Load test không thay validation correctness.

### 18.4. Index lifecycle

Build complete, build verified, index queryable và index effective là các trạng thái khác nhau. Thời gian tới full benefit có thể dài hơn job reported time.

### 18.5. Test dữ liệu bị ghi trong lúc build

Tạo inserts/updates/deletes và verify index không bỏ sót/hồi sinh records sau khi status READY.

## 19. Thêm index khi dữ liệu đã skew

Một collection có 100 triệu documents, trong đó 90% records có `status="ACTIVE"`. Index đơn trên `status` có độ chọn lọc thấp.

### 19.1. Index không tự làm query nhanh

Query `status=ACTIVE` có thể trả 90 triệu records, sử dụng index vẫn tốn I/O. Composite index/range constraint hoặc data model khác có thể phù hợp hơn.

### 19.2. Build cost phụ thuộc cardinality/array size

Multikey index trên array dài có thể tạo nhiều index entries/record, tăng storage và write amplification.

### 19.3. Unique index có thể fail

Trong quá trình migration từ schema không kiểm uniqueness, dữ liệu cũ có duplicates; build unique index có thể bị từ chối. Test trên dataset đại diện, không chỉ clean seed.

### 19.4. Chọn đúng cohort

Một tenant lớn có nhiều nested values có thể làm build nghiêng tải. Monitor progress/latency per partition/tenant nếu metrics hỗ trợ.

## 20. Topology changes: quorum, leader và routes

### 20.1. Thêm node

Node vừa join chưa chắc đã sẵn sàng nhận traffic; có thể cần bootstrap/streaming, data verification, cache warmup hoặc consensus membership change.

### 20.2. Bớt node

N−1 capacity, shard relocation và quorum/replica placement phải còn đúng. Không loại node khi cụm đang không đủ replicas hoặc đang rebuild chưa hoàn thành.

### 20.3. Leader election

Election có thể tạo khoảng gián đoạn ghi và stale-leader errors; clients cần refresh topology/retry theo SDK semantics và deadline.

### 20.4. Zone/region placement

Chuyển replicas giữa AZ có thể làm tăng network RTT/egress và ảnh hưởng quorum write latency. Đừng chỉ đo một region traffic.

### 20.5. Rolling restart/upgrade

Mỗi node restart có thể mất caches, tạo compaction/repair backlog và topology stabilization. Test mixed-version compatibility theo vendor docs, không tự giả mọi versions được chạy chung.

## 21. Không đánh đổi consistency/durability để đạt SLO giả

### 21.1. Giữ write concern/consistency level

Baseline và during-change phải dùng cùng durability/replication guarantees. Hạ write concern có thể làm latency đẹp nhưng tăng risk acknowledged data loss.

### 21.2. Đọc eventual có thể khác đọc strong

Thêm replicas có thể giúp throughput nhưng không làm đọc strong/transactional tự nhanh hơn. Benchmark phải tách consistency modes.

### 21.3. Conditional writes

Trong rebalance, CAS/LWT/transaction conflicts có thể tăng; kiểm expected conflicts và lost-update prevention, không chỉ latency.

### 21.4. Unknown outcome

Timeout ngay sau commit/election có thể là ambiguous result; client retry cần idempotency key, không double-create Order hoặc decrement stock.

### 21.5. RPO/RTO là nghĩa vụ riêng

Benchmark không được gây mất replication recovery window hay backup/PITR chain chỉ để chạy nhanh.

## 22. Kiểm tính đúng đắn trong load test

Một chạy tải “không lỗi HTTP” vẫn có thể có silent data loss.

~~~text
Business operation ReserveSeat:
    Stable reservationId
    Conditional capacity decrement
    Outbox event

Oracle after workload:
    Accepted reservations == authoritative reservation rows
    No duplicate reservationIds
    Remaining seats >= 0
    Confirmed writes survive planned failover
    Outbox events correspond to committed reservations
~~~

### 22.1. Dùng ID cố định cho một ý định

Nếu timeout rồi retry, giữ nguyên request/idempotency key. Load generator tạo key khác cho mỗi retry có thể tạo “lỗi mất dữ liệu” do double effects thật.

### 22.2. Ghi invocation/result history

Với mỗi command: start/end time, response, key, expected version, server receipt ID. Sau test đối chiếu authoritative state, đặc biệt timeout/unknown outcomes.

### 22.3. Linearizability theo phạm vi

Nếu API hứa CAS/strong transaction, có thể dùng linearizability checker cho một tập keys/operations. Không đòi eventual read model phải mạnh như source.

### 22.4. Đếm records chưa đủ

Source/target cùng count nhưng version/amount/status khác vẫn sai. Test compare business invariants theo ID/version.

### 22.5. Đọc sau failover

Đảm bảo các writes đã được ACK dưới durability contract còn hiện diện qua node loss và membership change trong failure model.

## 23. Tải nền và replication/CDC lag

### 23.1. Replica catch-up

Trong lúc chuyển shards hoặc restart node, replica mới phải nhận snapshot rồi changes mới. Lag không được vượt mức ảnh hưởng failover/RPO.

### 23.2. CDC consumer backlog

Nếu data movement/index build chiếm write IO hoặc network, CDC producer/consumer có thể tụt tốc. Đo oldest unprocessed age, bytes/events pending và earliest available position.

### 23.3. History retention window

Một consumer lag 2 giờ và oplog/change history chỉ giữ khoảng 3 giờ đã gần nguy hiểm. Abort/throttle thay đổi trước khi consumer mất khả năng resume.

### 23.4. Không nhầm delay với data loss

Một projection chậm 5 phút có thể vẫn catch up, nhưng phải có test chứng minh no missed events và bound eventual convergence.

### 23.5. Queue drain time

Nếu backlog 10 triệu events và consumer net drain 5.000 events/s, cần khoảng 2.000 giây để hết backlog trong mô hình tốc độ ổn định, chưa tính live events variation.

## 24. Compaction, merge và disk amplification

### 24.1. LSM engines

SSTable compaction có thể ghi file mới trước khi xóa file cũ; rebalance và index build còn tạo thêm writes, tăng disk use tạm thời.

### 24.2. Search segments

Elasticsearch/OpenSearch segment merges cũng cần headroom; disk watermarks có thể ngăn relocation/ghi trong lúc đang cần di chuyển dữ liệu.

### 24.3. Snapshot references

Snapshot hard-link/CoW có thể giữ old blocks khiến disk không giảm ngay sau migration. Đừng xóa recovery files bằng `rm` để cứu benchmark.

### 24.4. Monitoring

Disk free bytes, inodes, write bandwidth, I/O wait/latency, compaction pending bytes, temporary usage, index size và failure errors.

### 24.5. Safety gate

Nếu free space không đủ cho compaction/repair hoặc backup job, có thể phải tạm dừng/mở rộng capacity theo supported procedure, không tiếp tục tăng tải.

## 25. Các lỗi đặc thù của phép thử

| Triệu chứng | Khả năng cần kiểm |
|---|---|
 P99 tăng nhưng CPU thấp | Disk/network queue, lock wait, pool exhaustion |
 Throughput giảm, p99 không tăng | Closed-loop backpressure, 429, rejected traffic |
 One shard 100%, average 50% | Skew/hot key/placement |
 Index build “stuck 99%” | Catch-up writes, compaction, validate phase |
 Cache hit rate giảm sau node add | Cold target caches |
 CDC lag tăng liên tục | Apply throughput thấp hơn change rate |
 Disk used tăng khi live records ổn | Compaction/temp/snapshot/index |
 New node nhận rất ít traffic | Rebalance chưa xong, route/chunk distribution |
 Write errors ngay election | Quorum/leader transition, stale topology |
 Success rate cao nhưng Order duplicate | Retry không idempotent, missing oracle |

### 25.1. Lỗi generator khác lỗi server

Nếu generator thiếu file descriptors hoặc CPU bị đầy, requests không đến server. Đo client-local errors và server observed requests riêng.

### 25.2. 429 không phải luôn lỗi cơ sở dữ liệu

429 có thể là admission/throttling được thiết kế để bảo vệ service. Nhưng vẫn là ảnh hưởng lên clients và cần được tính vào success/error budget.

### 25.3. Error rate theo loại

Tách unavailable, timeout, validation reject, conditional conflicts, retryable topology errors và expected business rejections để chọn hành động.

## 26. Mẫu k6 load test có gắn pha

Ví dụ này dùng **k6** với API thử nghiệm. Chỉ chạy trên môi trường được cấp phép, có rate cap và dữ liệu giả. Ví dụ không tự tạo topology change; người vận hành kích hoạt thay đổi qua kênh riêng có kiểm soát.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const apiFailure = new Rate('business_failures');
const businessLatency = new Trend('business_latency_ms', true);

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '8m',
      preAllocatedVUs: 100,
      maxVUs: 200,
    },
  },
  thresholds: {
    business_failures: ['rate<0.005'],
    business_latency_ms: ['p(99)<250'],
    http_req_failed: ['rate<0.01'],
    dropped_iterations: ['count<1'],
  },
};

export default function () {
  const base = __ENV.TEST_API_BASE_URL;
  if (!base || !base.startsWith('https://')) {
    throw new Error('A staging HTTPS URL is required');
  }

  const id = `test-${__VU}-${__ITER}`;
  const started = Date.now();
  const res = http.get(`${base}/orders/${id}`, {
    tags: { operation: 'get_order' },
    timeout: '3s',
  });

  const ok = check(res, {
    'status 200 or expected not found': r =>
      r.status === 200 || r.status === 404,
  });
  apiFailure.add(!ok);
  businessLatency.add(Date.now() - started);
}
~~~

### 26.1. Rate phải được phê duyệt

`200/s` chỉ là ví dụ, không phải con số nên chạy trên production. Chọn mức phù hợp sandbox capacity và đặc biệt không tự chạy overload khi không có owner.

### 26.2. ID và kết quả 404

Ví dụ dùng test IDs; khi đo latency “đọc data thực”, cần seed IDs có thật và tách miss/hit ratio. Nếu mọi request là 404, benchmark không đại diện.

### 26.3. Phân loại operation

Mở rộng workload bằng read/write/transaction scenarios với các tags `operation`, `tenantTier`; tránh label với mỗi orderId vì cardinality quá lớn.

### 26.4. `dropped_iterations`

Chỉ số này giúp phát hiện generator không đạt planned arrival rate. Nếu dropped iterations tăng, không được coi run là đạt 200 requests/s.

### 26.5. Phases

Trong run thực, có thể cho generator chạy baseline trước; trigger index/rebalance bằng approved operator vào thời điểm đánh dấu và tiếp tục chạy tới stable.

## 27. Test ghi có idempotency key

Đối với requests tạo Order, load generator phải có phân biệt:

~~~text
New business intent:
    idempotencyKey = fresh stable UUID
    payload = random but valid order

Retry of the same intent:
    idempotencyKey = SAME UUID
    payload = EXACT same semantic payload
~~~

### 27.1. Nếu timeout thì retry đúng ID

Không tạo Order mới chỉ vì response mất, nếu mục tiêu là đo idempotency/correctness.

### 27.2. So effects sau test

Đếm unique requests có intent thành công và authoritative Orders, outbox messages, stock reservations. Kiểm duplicates/missing IDs.

### 27.3. Throttle retry riêng

Một rebalance có thể làm timeouts tăng, kéo theo retry storm. Retry budget và jitter phải giống production, tránh amplifier không thực tế.

### 27.4. Session/connection pools

Giữ pool sizes theo app production; load test chỉ gọi HTTP mà bỏ driver behavior có thể không thể hiện connection refresh và topology awareness.

## 28. Java: đo duration và kết quả trên client

Đo từ lúc gửi tới lúc nhận response/error để thấy client-visible latency, không chỉ DB execution time:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public record AttemptResult(
    String operation,
    int statusCode,
    boolean succeeded,
    long durationNanos
) {
    public double durationMillis() {
        return durationNanos / 1_000_000.0;
    }
}

public final class TimedCall {
    private TimedCall() {}

    public static AttemptResult measure(
            String operation,
            java.util.concurrent.Callable<Integer> call) {
        long start = System.nanoTime();
        try {
            int status = call.call();
            long duration = System.nanoTime() - start;
            return new AttemptResult(
                operation, status, status >= 200 && status < 300,
                duration);
        } catch (Exception failure) {
            long duration = System.nanoTime() - start;
            return new AttemptResult(operation, 0, false, duration);
        }
    }
}
~~~

### 28.1. `System.nanoTime()` cho duration

Đo elapsed time bằng monotonic-style timer, không tính latency bằng trừ wall-clock timestamps có thể bị NTP điều chỉnh.

### 28.2. Không dùng record list vô hạn

Trong load harness thực, dùng histogram/metrics library có bounded memory, thread-safe counters và sample rate phù hợp; không lưu mọi result vào heap.

### 28.3. 0 status là transport failure

Ví dụ dùng status=0 minh họa exception, nhưng trong thực tế cần phân loại timeout, DNS, connection refused, TLS và server error; error attribution rất quan trọng.

### 28.4. Client timing gồm nhiều thành phần

Pool acquire, DNS/TLS, queueing, retry và network round-trip; server-side DB latency giúp xác định bottleneck chứ không thay client timing.

## 29. Java: kiểm orchestration không phá SLO

Test có thể dùng một guardrail abstraction, không trực tiếp tạo rebalance:

~~~java
public record TestWindowMetrics(
    double p99ReadMillis,
    double p99WriteMillis,
    double foregroundErrorRate,
    long minDiskFreeBytes,
    long oldestCdcLagSeconds,
    boolean acknowledgedWritesPreserved
) {}

public record ChangeGuardrails(
    double maxP99ReadMillis,
    double maxP99WriteMillis,
    double maxErrorRate,
    long minDiskFreeBytes,
    long maxCdcLagSeconds
) {
    public boolean safeToContinue(TestWindowMetrics m) {
        return m.p99ReadMillis() <= maxP99ReadMillis
            && m.p99WriteMillis() <= maxP99WriteMillis
            && m.foregroundErrorRate() <= maxErrorRate
            && m.minDiskFreeBytes() >= minDiskFreeBytes
            && m.oldestCdcLagSeconds() <= maxCdcLagSeconds
            && m.acknowledgedWritesPreserved();
    }
}
~~~

### 29.1. Đây là rule minh họa, không là production auto-control

Một dashboard window thiếu data không được coi là “all good”. Trong production cần completeness/age checks, hysteresis, min sample counts, owner approvals và thao tác pause được vendor hỗ trợ.

### 29.2. Latency và disk đều cần

Một index build có p99 tốt nhưng min free bytes dưới threshold vẫn không an toàn. Load test đánh giá nhiều chiều.

### 29.3. Correctness gate cứng

Nếu phát hiện lost acknowledged write hoặc data corruption, test phải dừng/điều tra thay vì “trừ điểm SLO chút ít”.

### 29.4. Recovery cũng có gate

Sau change cần xác minh backlog drain, error rate, index/query plans và replica health chứ không chỉ `safeToContinue` trong lúc chạy.

## 30. PromQL và dashboards minh họa

Ví dụ metric application:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="orders", outcome="success"
}[1m]))
~~~

Lưu ý metric names/labels phụ thuộc instrumentation thực; đây là ví dụ ý tưởng, cần điều chỉnh.

### 30.1. P99 từ histogram

~~~promql
histogram_quantile(
  0.99,
  sum by (le, operation) (
    rate(http_server_requests_seconds_bucket{
      service="orders"
    }[1m])
  )
)
~~~

Các buckets phải đủ phân giải quanh SLO. Nếu dùng native histograms hoặc metrics khác, cú pháp sẽ khác.

### 30.2. Error rate

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="orders", outcome="error"
}[1m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    service="orders"
  }[1m])),
  0.001
)
~~~

### 30.3. Disk free

~~~promql
node_filesystem_avail_bytes{mountpoint="/var/lib/nosql"}
~~~

Trong Kubernetes/managed service, cần metric volume/PVC/provider tương ứng, không giả định host mountpoint này tồn tại.

### 30.4. Không gộp histograms sai

Histogram quantile tính từ bucket rates được merge theo `le` và operation, không lấy trung bình p99 của từng instance.

### 30.5. Annotations

Gắn T0–T7, node ID, index build job ID và topology epoch lên dashboard để quy nguyên nhân.

## 31. MongoDB: resharding, chunk movement và index build

### 31.1. Tách hoạt động

Balancer/chunk movement, đổi shard key bằng supported resharding operation, build indexes và thêm replica set members có semantics khác nhau. Test từng activity rồi mới overlap.

### 31.2. Metrics phù hợp

Per-shard operation latency, replication lag, elections, connections, cache eviction, disk IO, chunk distribution, migration progress và slow query rates.

### 31.3. Index build

Ở các MongoDB versions hiện đại, index builds có quy trình phối hợp và các giai đoạn commit riêng; mức lock/replica synchronization phụ thuộc phiên bản/feature. Không tự coi “background option” trong tài liệu cũ là contract hiện tại.

### 31.4. Query targeting

Sau resharding, một query không có shard-key predicate có thể scatter nhiều shards. Post-change load test phải kiểm query plans và số shards contacted.

### 31.5. Failover và write concern

Thử leader election lúc migration trong sandbox với write concern phù hợp; kiểm ACKed writes, idempotent retries và availability. Không sửa durability config để làm kết quả đẹp.

## 32. DynamoDB: GSI build và capacity

### 32.1. GSI backfill

Khi tạo Global Secondary Index cho table có dữ liệu, DynamoDB có thể backfill index và duy trì thay đổi. Trạng thái index, capacity/throughput và throttle impact cần kiểm theo service metrics.

### 32.2. Không có host rebalance command

DynamoDB là managed service; người dùng không trực tiếp di chuyển shards vật lý. Test thay đổi index, throughput, access pattern/hot partition, import/export hoặc partition growth theo API được hỗ trợ.

### 32.3. Read/write cost

GSI làm write/index storage costs tăng. Benchmark cả queries hưởng lợi lẫn mutations vốn không cần GSI.

### 32.4. Throttle signals

Quan sát throttled requests, consumed/provisioned capacity, hot keys, retry counts và p99. Internal SDK retries có thể làm application latency tăng khi service throttle.

### 32.5. Correctness

GSI có read-consistency semantics khác primary table; không so query từ GSI như strong read nếu service không hỗ trợ. Kiểm business rules trên authoritative primary data.

## 33. Cosmos DB for NoSQL: indexing policy và repartition

### 33.1. Index transformation

Thay indexing policy có thể kích hoạt index transformation theo khả năng account/service; monitor progress, RU/latency và storage. Semantics tùy feature/version.

### 33.2. RU budget

Queries, writes và background work có thể tranh RU hoặc chịu throttling. Thử nhiều RU configurations, partition skew và application retry-after handling.

### 33.3. Physical partition splits

Service-managed physical partitioning/split có thể ảnh hưởng routing/latency; không giả định có shell command điều khiển thủ công giống hệ self-hosted.

### 33.4. Logical partition key

Đổi partition key thường là data migration/container change theo supported methods; load test phải xem cross-partition queries, unique constraints và transactional batch scope.

### 33.5. Diagnostics

Theo dõi request charge, 429 rate, normalized RU consumption, end-to-end latency, indexing progress và application-level correctness.

## 34. Cassandra/ScyllaDB: bootstrap, decommission và compaction

### 34.1. Node bootstrap

Thêm node có thể stream token ranges/SSTables từ peers; đây là cạnh tranh disk/network và làm dữ liệu phân bố lại, không phải node mới lập tức gánh đều traffic.

### 34.2. Decommission

Loại node yêu cầu token ownership/replica placement an toàn; có thể cần stream dữ liệu và maintenance window đủ headroom. Không thử trên production nếu không có runbook/backups/phê duyệt.

### 34.3. Secondary index hoặc materialized view

Khả năng, giới hạn và tác động build indexes/views khác theo engine/version. Test query selectivity, write overhead, rebuild duration và backlog; không gộp mọi dạng index thành một.

### 34.4. Compaction

SSTable compaction và streaming cùng dùng disk bandwidth/temp space; đo pending compactions, SSTable counts, read/write latencies và tombstones.

### 34.5. Consistency

Thử CL được application dùng (ví dụ local quorum nếu phù hợp) và kiểm unavailable/read-repair/repair effects. Không so CL=ONE với quorum rồi suy topology tốt hơn.

## 35. Elasticsearch/OpenSearch: shard relocation và index segments

### 35.1. Rebalance

Shard allocation/relocation có thể chuyển nhiều segments, cần network, disk reads/writes và cache warmup. Theo dõi relocating/unassigned shards, recovery speed và disk watermarks.

### 35.2. Segment merge

Heavy indexing tạo merges; nếu rebalancing cùng lúc, I/O contention/temporary disk usage có thể rất cao.

### 35.3. Index creation vs rebuild

Tạo empty index nhanh không giống xây index từ dữ liệu lớn hoặc reindexing millions documents. Đặt phép thử theo hoạt động thật.

### 35.4. Search vs indexing

Đo query p99, shard-level fetch/query latency, indexing throughput, refresh latency và rejected threadpool tasks theo workload.

### 35.5. Không vô hiệu disk watermarks để đạt benchmark

Watermarks có thể bảo vệ cluster khỏi full disk. Nếu bị chặn, cần capacity/placement correction theo supported operation, không tự xóa segment files.

## 36. Redis Cluster: resharding và failover

### 36.1. Hash slot migration

Redis Cluster có 16.384 hash slots; di chuyển slot owners có thể làm clients nhận redirects `MOVED`/`ASK` theo trạng thái. Test clients hỗ trợ topology refresh.

### 36.2. Hot slot

Di chuyển hot slot sang node mới có thể chuyển hotspot chứ không chia workload trong slot. Chọn key patterns/hash tags theo access patterns.

### 36.3. Latency và redirects

Đo p99, redirect attempts, timeouts, retry loops, slot migration progress và connection pool saturation.

### 36.4. Failover durability

Replication/persistence settings quyết định khả năng mất writes sau failover. Nếu dùng Redis như source of truth, cần kiểm theo durability contract; nếu là cache, xem cache hit/miss và refill storm.

### 36.5. Memory và copy-on-write

Snapshot/AOF rewrite có thể tăng memory/disk peak; phối hợp test với resharding nếu workload thực sự có thể trùng lịch.

## 37. Couchbase: rebalance và xây index

### 37.1. Services riêng

Couchbase có thể phân tách Data/Query/Index services tùy deployment, nên đo resources của từng service thay vì cluster CPU bình quân.

### 37.2. VBucket movement

Rebalance chuyển ownership/replicas của vBuckets và có thể tạo disk/network/replication pressure. Đo DCP backlog và rebalance progress theo metrics backend.

### 37.3. Index build

Xây index và phục vụ N1QL/SQL++ queries có thể cạnh tranh index service resources, ảnh hưởng query p99 và mutation processing.

### 37.4. Dữ liệu và query consistency

Post-index-build, phải kiểm query/index consistency modes, không nhầm index lag với mất nguồn data.

### 37.5. Test resource isolation

Nếu dedicated index nodes, test mất/index node overload có tác động gì tới data service và query availability theo topology thực.

## 38. Managed service và giới hạn quyền quan sát

Một managed NoSQL có thể không cho xem host-level IOPS, shard names hoặc internal compaction progress.

### 38.1. Dùng service metrics chính thức

RU/throttle, provisioned capacity, request charge, index transformation progress, backup job state, partition split/topology events, storage size và service error codes.

### 38.2. Client metrics là bắt buộc

Ngay cả khi provider chỉ công bố vài counters, client-visible p99/error/correctness vẫn có thể đo đủ để ra quyết định.

### 38.3. Phân biệt tính năng không kiểm soát được

Nếu provider tự rebalance/split, không thể kích hoạt chính xác mọi tình huống; thiết kế workload để quan sát những lần thay đổi có thể kiểm soát và ghi limitation trong kết quả.

### 38.4. Đừng tự suy nguyên nhân từ một biểu đồ

429 tăng có thể do hot partition, RU budget, sudden writes hoặc background index work; cần correlated evidence và diagnostic metadata.

## 39. Case study: thêm nodes nhưng p99 tăng

Một cluster có 4 nodes, thêm 2 nodes để tăng khả năng chịu peak. Trong 30 phút streaming data, p99 đọc tăng gấp ba và disk throughput source chạm giới hạn.

### 39.1. Quan sát

Throughput API vẫn gần bình thường vì client retries, nhưng timeouts tăng ở hai tenants có hot partitions. Mean CPU toàn cluster không cao.

### 39.2. Giả thuyết

Source disk IO và cache bị cạnh tranh, một số hot shards đang chuyển, client routes bị refresh nhiều. Cần per-node/per-shard metrics xác nhận.

### 39.3. Mitigation

Trong môi trường có owner cho phép, throttle số streams đồng thời, ưu tiên foreground, tránh index/backup overlap hoặc thêm capacity phù hợp. Không tắt bảo đảm replication.

### 39.4. Kiểm hoàn tất

Replica lag trở về ngưỡng, shard placement cân hơn, p99 ổn định và query mix không bị regression.

### 39.5. Bài học

“Scale out” không phải lúc nào cũng tăng hiệu năng ngay lập tức; khoảng di chuyển cũng phải được tính như một phần change risk.

## 40. Case study: tạo index giúp reads nhưng làm writes chậm

Một collection 500 triệu documents cần index `(tenantId, createdAt DESC)` để trang liệt kê mới nhanh hơn.

### 40.1. Trong build

Source reads/index writes làm p99 writes tăng 120→260 ms, disk queue tăng và build catch-up chậm vì write-heavy traffic.

### 40.2. Sau build

Read query giảm scanned records đáng kể, p99 list giảm, nhưng every insert cũng cập nhật index mới. Cần đo steady write cost.

### 40.3. Kết luận đúng

Đánh giá lợi ích bằng tổng API workload, not just one query; nếu write SLO bị vi phạm, phải thay index design/scheduling/capacity.

### 40.4. Correctness

Tạo documents/updates/deletes trong lúc build và xác nhận query index sau ACTIVE không thiếu records theo consistency contract.

## 41. Case study: topology failover lúc rebalance

Trong cluster đang di chuyển replicas, một node cũ mất kết nối, buộc election/reconfiguration.

### 41.1. Điều cần kiểm

Quorum health, confirmed writes, new leader route, retry behavior, replica catch-up và khả năng tiếp tục/đưa lại migration về safe state.

### 41.2. Tail spikes

Một election 5 giây có thể gây lượng timeout lớn nếu ứng dụng 20.000 RPS. Không để biểu đồ p99 10 phút che sự kiện.

### 41.3. Không tạo split-brain

Fencing/epoch/consensus phải ngăn old owner tiếp tục nhận authoritative writes khi mạng hồi phục. Oracle gồm no lost acknowledged writes và no duplicate business effects.

### 41.4. Restore plan

Nếu topology changes gây dữ liệu không thể xác minh, dừng test/hoạt động và dùng recoverable backup/runbook thay vì tiếp tục tạo workload phá hủy.

## 42. Case study: index build làm CDC lag vượt biên

Một hệ sử dụng database NoSQL làm source cho search projection. Trong index build, disk IO pressure làm CDC consumer apply từ 40.000 xuống 25.000 events/s trong khi source tạo 35.000/s.

### 42.1. Backlog

Backlog tăng 10.000 events/s; sau 20 phút tăng khoảng 12 triệu events trong mô hình đơn giản.

### 42.2. Rủi ro

Nếu history window chỉ 90 phút và consumer tiếp tục tụt, có thể mất khả năng resume; việc index build “thành công” không bù mất recovery path.

### 42.3. Điều chỉnh

Throttle build/ingest hoặc tăng consumer effective capacity theo khả năng hệ; monitor oldest unprocessed age vs earliest available event.

### 42.4. Sau build

Consumer phải catch up; chỉ coi phép thử kết thúc khi lag về mức chấp nhận và projection invariants được xác minh.

## 43. Tìm nguyên nhân khi throughput tụt

### 43.1. Phân biệt load generator và service

So scheduled requests vs actually sent vs server received vs completed. Nếu generator gửi ít hơn khi server chậm, đây có thể là closed-loop effect.

### 43.2. Phân biệt queueing với execution

Service p99 cao nhưng DB query p99 bình thường có thể do thread pool, connection acquire, app GC hoặc upstream retries.

### 43.3. Phân biệt IO với CPU

CPU rảnh nhưng disk read/write latency cao có thể là I/O bottleneck do migration streams/segment merge.

### 43.4. Phân biệt data skew với cluster shortage

Một partition/node nóng trong khi nhiều nodes rảnh là placement/access pattern issue; thêm tổng CPU có thể không giải quyết.

### 43.5. Phân biệt permanent regression với warmup

Sau rebalance cache mới lạnh, p99 tăng rồi dần giảm. Đo đủ long settling window trước khi kết luận và đảm bảo warmup phù hợp production.

## 44. Đọc đúng kết quả thí nghiệm

Ví dụ bảng so sánh:

| Chỉ số | Baseline | During rebalance | Settled after | Mục tiêu minh họa |
|---|---:|---:|---:|---:|
| Successful RPS | 10.000 | 9.500 | 12.000 | ≥9.800 during |
| Read p99 (ms) | 85 | 340 | 70 | ≤200 |
| Write p99 (ms) | 120 | 280 | 110 | ≤250 |
| Error rate | 0,1% | 1,2% | 0,1% | ≤0,5% |
| CDC max lag (s) | 4 | 180 | 5 | ≤120 |
| Min disk free | 28% | 12% | 22% | ≥15% |

Đây là **dữ liệu giả định để minh họa cách đọc**, không phải benchmark của một sản phẩm. Với các SLO minh họa, run này **không đạt during-change gates** dù post-change performance tốt hơn.

### 44.1. Đừng che violation bằng “sau cùng nhanh hơn”

Không thể kết luận một rebalance an toàn khi 30 phút giữa quá trình vi phạm latency/error/CDC/disk reserve.

### 44.2. Đừng dùng thành công throughput để bỏ qua correctness

Nếu lost ACKed writes hoặc duplicate reservation, đây là FAIL cứng dù mọi performance metrics đạt.

### 44.3. Ghi run context

Số nodes, replication factor, shard count, dataset, client code, SDK, write concern, traffic mix, warmup, build phase và throttles đều phải đi kèm kết quả.

### 44.4. Tính noise

So nhiều runs, spread/confidence và paired baselines; một spike do cloud noise cần ghi nhận chứ không xóa tùy ý khỏi kết quả.

## 45. Stop, pause và rollback/roll-forward criteria

### 45.1. Pause

Nếu foreground latency vượt guardrail, giảm tốc streaming/index work nếu API supports; không tự kill process có thể để lại trạng thái không nhất quán.

### 45.2. Abort

Khi xảy ra data corruption, loss of acknowledged writes, unauthorized data move, quorum danger hoặc nguy cơ full disk nghiêm trọng, ưu tiên bảo vệ dữ liệu rồi theo vendor incident procedure.

### 45.3. Roll-forward

Một số topology changes sau khi ownership đã chuyển không thể “undo” bằng bật lại config cũ. Sửa placement/capacity và tiến tới trạng thái ổn định được hỗ trợ thường an toàn hơn.

### 45.4. Rollback

Nếu vendor cho phép hủy index build hoặc rebalance ở một giai đoạn, xác định chính xác guarantees và recovery steps. Không assume mọi job có rollback.

### 45.5. Human approval

Runbook nên có owner, change window, permitted operations, command IDs và rollback authority; load generator không nên tự chạy lệnh hủy cluster.

## 46. Kế hoạch chạy phép thử an toàn

### Bước 1 — Xác định mục tiêu

Chọn một operation (rebalance/index/topology), workload, SLO/latency/errors, invariant và guardrails cho data/CDC/disk.

### Bước 2 — Dựng môi trường

Dùng staging/performance environment đại diện, accounts/dataset test, backup có thể restore, phân quyền chỉ dùng các thao tác được phê duyệt.

### Bước 3 — Ghi baseline

Lưu topology/dataset/version, query mix, arrival rate, p50/p95/p99, error, disk/net, replica and CDC lag.

### Bước 4 — Khởi chạy generator

Warmup, chạy normal peak arrival rate, xác nhận generator không bị saturation và đã đủ samples.

### Bước 5 — Trigger change

Người vận hành chạy supported API để tạo index/rebalance/topology change; ghi timestamp, job ID, options và expected end state.

### Bước 6 — Theo dõi change window

Quan sát background progress, per-node resources, per-tenant p99, error types, throughput, thread pools, CDC/replication lag và disk reserve.

### Bước 7 — Kiểm lỗi có kiểm soát

Trong test runs riêng, tiêm node failover/network loss theo guardrails và backup readiness. Không gộp mọi failure modes trong run đầu.

### Bước 8 — Đợi phục hồi

Ghi end-of-change, catch-up và settled condition; không stop generator ngay khi UI báo finished.

### Bước 9 — Kiểm correctness

Reconcile acknowledged writes, ids/versions, counters, outbox/CDC state, missing/duplicate records và tenant isolation.

### Bước 10 — Đánh giá và ra quyết định

So baseline/during/post, SLO budget, completion time, headroom, cost và variance; ghi runbook tuning hoặc blockers trước rollout production.

## 47. Mẫu tài liệu phép thử

~~~yaml
experiment:
  name: "orders-rebalance-under-load"
  module: "Database No SQL"
  scenario: "add-two-nodes-and-redistribute"
  owner: "<team>"
  environment: "dedicated-staging"
  engineVersion: "<version>"
  sdkVersion: "<version>"

topology:
  beforeNodes: 6
  afterNodes: 8
  replicaPolicy: "<real deployment config>"
  zones: ["<zone-a>", "<zone-b>", "<zone-c>"]

dataset:
  records: "<representative count>"
  bytes: "<representative size>"
  tenantSkew: "<distribution>"
  hotKeys: "<profile>"
  indexSet: "<existing indexes>"

load:
  model: "open-loop"
  peakRequestsPerSecond: "<approved target>"
  readWriteMix: "<percentages>"
  payloadDistribution: "<bytes>"
  clientTimeout: "<duration>"
  retryBudget: "<policy>"

gates:
  maxReadP99Ms: "<SLO>"
  maxWriteP99Ms: "<SLO>"
  maxErrorRate: "<SLO>"
  minFreeBytesPerNode: "<reserve>"
  maxOldestCdcLagSeconds: "<safe horizon>"
  noLostAcknowledgedWrites: true
  noDuplicateBusinessEffects: true
  noCrossTenantLeaks: true

phases:
  - warmup
  - baseline
  - change
  - catchup
  - settled
  - reconciliation

artifacts:
  metricsDashboard: "<link>"
  changeEventTimeline: "<link>"
  correctnessReport: "<link>"
  stopCriteria: "<runbook>"
~~~

### 47.1. Đây là mẫu mô tả, không là cấu hình thực thi tự động

Điền values có thật theo sản phẩm/SDK và SLO được owner phê duyệt. Không tự suy từ labels rằng vendor sẽ hiểu YAML này.

### 47.2. Ghi exact version rất quan trọng

Các tác vụ index build/resharding/rebalance có thể thay behavior giữa major/minor versions; kết quả ở phiên bản cũ chưa chắc dùng được cho bản mới.

### 47.3. Lưu bằng chứng gốc

Dashboards tổng hợp, histogram exports, start/finish timestamps, job progress, generator outputs và data reconciliation đều cần lưu để replay/đối chiếu.

## 48. Checklist đo tải khi topology thay đổi

1. Đã phân biệt **rebalance**, **index build** và **topology change** theo engine chưa?
2. Đã chọn SLO nghiệp vụ và correctness invariants chưa?
3. Có dataset đủ lớn và gần production distribution không?
4. Có hot tenants/keys, tombstones, TTL và documents lớn trong test không?
5. Có query mix/read-write/transaction tỷ lệ thực tế không?
6. Generator dùng open/closed loop theo mục tiêu rõ chưa?
7. Có đo scheduled vs actually sent requests không?
8. Có kiểm coordinated omission và generator saturation không?
9. Có baseline cùng consistency/write concern không?
10. Có timestamps của từng milestone thay đổi không?
11. Có đo p50/p95/p99 theo từng API và tenant tier không?
12. Có đo timeout, throttling, business conflicts và retry counts riêng không?
13. Có đo server/driver pool waits và GC không?
14. Có per-node CPU/RAM/disk/network metrics không?
15. Có shard/partition placement skew và hottest owner không?
16. Có disk free bytes/inodes và compaction/index temporary usage không?
17. Có index build progress, query plan và index freshness không?
18. Có replication/CDC lag và retention margin không?
19. Có chuẩn bị N−1 capacity nếu một node fail trong change không?
20. Có test supported failover trong môi trường cô lập không?
21. Có test retries với stable idempotency key không?
22. Có verify acknowledged writes, uniqueness và domain invariants không?
23. Có đo cả migration duration và time-to-settled không?
24. Có đợi backlog drain trước khi dừng generator không?
25. Có đo post-change query benefit và write overhead không?
26. Có làm runs lặp để đánh giá variance không?
27. Có phân biệt cloud/service quota và self-hosted bottlenecks không?
28. Có abort/pause criteria rõ, owner và approval không?
29. Có backup/restore và incident plan nếu phép thử thất bại không?
30. Có lưu bản ghi thí nghiệm đủ để ra quyết định rollout không?

## 49. Những sai lầm phổ biến

### “Node mới lên xanh nghĩa tăng capacity ngay”

Sai nếu shards chưa được phân phối, cache lạnh hoặc traffic còn dồn vào hot partition cũ.

### “Index online không ảnh hưởng writes”

Không chắc; background scan/build/catch-up vẫn dùng CPU/IO/storage và có thể có phase coordination.

### “CPU trung bình 50% thì không quá tải”

Sai nếu một shard/node, disk queue hoặc network link đã bão hòa.

### “Chỉ cần đo throughput”

Không: throughput có thể giữ nguyên nhờ retries trong khi p99 và errors xấu đáng kể.

### “Closed-loop load đã giữ được 10.000 requests/s”

Cần kiểm actual arrival/success rates; server chậm có thể làm load generator tự giảm gửi.

### “P99 trung bình giữa nodes bằng p99 toàn hệ”

Không: cần merge distributions đúng trọng số và observation window.

### “Không có HTTP 500 nghĩa không có lỗi”

Không: 429, timeouts, stale reads, duplicate effects và missed CDC events vẫn là vấn đề.

### “Index created nghĩa query đã dùng index”

Không: cần kiểm planner và query selectivity.

### “Rebalance complete nghĩa cụm đã hồi phục”

Không: replication catch-up, compaction và cache warmup có thể kéo dài.

### “Chuyển nhiều shards song song luôn nhanh hơn”

Có thể làm saturation foreground IO, tăng retries và tổng thời gian hồi phục.

### “Thử trên 10.000 records đủ cho 1 TB data”

Không: dataset size và distribution thay resource behavior.

### “Nâng write capacity tạm bằng cách hạ durability”

Benchmark như vậy không còn đo cùng safety contract.

### “Throttled requests không tính là lỗi”

Đối với user SLO, rejected requests vẫn ảnh hưởng availability; cần ghi nhận theo policy.

### “Thử xong chỉ cần so trước và sau”

Không: phải đo toàn bộ degraded window.

### “Chỉ có một lần chạy đã đủ kết luận”

Không: cache, noisy neighbors, GC và workload variance có thể lệch.

### “Scale-out luôn tốt hơn sau khi đổi topology”

Không nếu query fan-out, index write amplification, cross-zone RTT và cost tăng vượt lợi ích.

### “Có replica nên lỗi node trong rebalance luôn an toàn”

Không mặc định; còn quorum, placement, streaming state, acknowledged writes và headroom.

### “Đầy đĩa thì xóa commitlog hoặc snapshot ngay”

Nguy hiểm: có thể phá recovery/backup chain; dùng supported procedures và capacity planning.

## 50. Bài tập thực hành

### Bài 1 — Xác định workload

Thiết kế mix read/write/transaction cho Order API với 70% read, 25% write, 5% conditional reservation. Nêu cách tạo hot tenants và cold keys.

### Bài 2 — Baseline

Cụm sáu node có p99 GET=80 ms. Trước khi thêm hai node, bạn cần ghi những metrics/configuration nào để so sánh có ý nghĩa?

### Bài 3 — Định nghĩa thành công

Một rebalance hoàn tất 20 phút nhưng 2% requests timeout. Đặt SLO/change gates khiến test được đánh giá đúng.

### Bài 4 — Timeline

Vẽ T0–T7 từ baseline đến settled. Tại sao “job done” không đồng nghĩa “test done”?

### Bài 5 — Open loop

So closed-loop 100 users với open-loop 2.000 arrivals/s trong lúc DB chậm. Kiểu nào dễ che queue buildup hơn và vì sao?

### Bài 6 — Generator overload

Configured rate 5.000/s, actual sent 3.000/s và `dropped_iterations` tăng. Có thể nói server chịu được 5.000/s không?

### Bài 7 — P99

Một spike 15 giây trong failover bị biểu đồ 5 phút làm phẳng. Bạn sẽ chọn cửa sổ/histogram thế nào để phát hiện?

### Bài 8 — Phân vùng nóng

Cluster CPU trung bình 40%, một node CPU 98%. Thiết kế heat map theo node/shard/tenant để tìm nguyên nhân.

### Bài 9 — Rebalance I/O

Khi source đang stream data, p99 GET tăng, cache hit giảm và disk read latency tăng. Đưa ra giả thuyết và cách kiểm chứng.

### Bài 10 — Streaming time

Ước lượng thời gian chuyển 120 GiB ở tốc độ 80 MiB/s; giải thích vì sao chỉ là lower-bound model.

### Bài 11 — CDC backlog

Source tạo 35k events/s, consumer apply 25k/s trong 20 phút. Tính backlog tăng và đánh giá retention margin.

### Bài 12 — Index build

Thêm composite index cho 500 triệu Orders. Lập phép thử scan/build/catch-up và đo p99 reads/writes trước, trong và sau.

### Bài 13 — Index regression

List API giảm p99 8 lần sau index, nhưng write p99 tăng gấp đôi. Lập quyết định dựa workload mix và SLO.

### Bài 14 — Index selectivity

Trường `status` có 90% ACTIVE. Tại sao index chỉ trên status chưa chắc làm query nhanh?

### Bài 15 — Unique index

Source data có duplicates. Build unique index thất bại. Phép thử tải cần thêm bước nào để phát hiện trước rollout?

### Bài 16 — Disk budget

Node còn 20% disk free, compaction cần temporary 15%, rebalance cần 12%. Bạn sẽ thiết kế stop criteria và capacity plan thế nào?

### Bài 17 — N−1

Cụm bốn nodes có tải 70% mỗi node; một node fail trong rebalance. Phân tích nguy cơ overload và chọn phương án.

### Bài 18 — Failover

Tiêm leader election ở sandbox khi index đang build. Xác định oracle cho acknowledged writes và client retry.

### Bài 19 — Idempotency

Client nhận timeout sau commit khi route đổi. Viết test giữ stable commandId và xác nhận stock không bị trừ hai lần.

### Bài 20 — Prometheus

Viết query histogram p99 theo operation, error rate và disk free theo node; giải thích vì sao không average p99.

### Bài 21 — k6

Sửa script k6 thành GET 60%, POST 30%, conditional update 10% với bounded rate, dữ liệu giả, explicit tags và thresholds.

### Bài 22 — Correctness

Sau rebalance có cùng số Order records nhưng 100 Order versions sai. Thiết kế reconcile theo key/version và checksums.

### Bài 23 — MongoDB

Phân biệt chunk migration, resharding, index build và election; chọn metrics cần theo dõi cho từng thao tác.

### Bài 24 — DynamoDB

Đánh giá tạo GSI khi table có write-heavy workload. Bạn đo capacity, throttling, build progress và write amplification như thế nào?

### Bài 25 — Cosmos DB

Index transformation khiến RU usage tăng. Lập phép thử không thay đổi logical partition consistency nhưng vẫn thấy 429 và query improvements.

### Bài 26 — Cassandra

Thêm node bootstrap trong lúc compaction backlog cao. Chọn safety gates về disk, streaming, latency, CL và replica health.

### Bài 27 — Elasticsearch

Shard relocation và segment merge trùng lịch. Vì sao disk watermarks có thể chặn relocation? Đề xuất phép đo.

### Bài 28 — Redis Cluster

Di chuyển hash slots khiến clients nhận MOVED/ASK. Lập test topology refresh, redirect loops, p99 và hot slot.

### Bài 29 — Couchbase

Thử rebalance vBuckets khi query/index services đang có tải. Làm sao biết data service hay index service đang là bottleneck?

### Bài 30 — Managed service

Provider không cung cấp host disk metrics. Thiết kế test dựa request charges, throttle rates, API latency, index status và correctness.

### Bài 31 — Retry storm

Gateway và SDK cùng retry khi node failover. Thử giới hạn retry budget và đo amplification so với offered load.

### Bài 32 — Cache warmup

Node mới phục vụ data nhưng cache lạnh. Đặt điều kiện settled sao cho không gọi một hồi phục chưa ổn định là pass.

### Bài 33 — Lặp thí nghiệm

Ba runs có p99 during lần lượt 250, 400 và 310 ms. Bạn cần kiểm những biến ẩn nào trước khi đưa ra quyết định?

### Bài 34 — Error budget

10.000 requests/s trong 30 phút với error rate 2% tạo bao nhiêu failed requests? So với target 0,5%.

### Bài 35 — Chọn pause/abort

P99 tăng nhẹ nhưng CDC lag sắp vượt history window và disk free dưới reserve. Có nên tiếp tục index build không? Viết quyết định và owner actions.

### Bài 36 — SLO vs job completion

Một migration hoàn tất nhanh nhưng tạo 15 phút downtime; run khác mất gấp đôi thời gian và không vi phạm SLO. So hai phương án.

### Bài 37 — Tổng hợp runbook

Thiết kế kịch bản staging: sáu node NoSQL, thêm hai node, build index mới, peak workload, cache nóng/lạnh, lỗi leader và backlog CDC. Viết timeline, metrics, stop conditions, correctness gates và post-test report.

### Bài 38 — Đánh giá kết quả

Được cung cấp bảng baseline/during/after của một cluster (p99, successful RPS, error rate, CDC lag, disk free). Hãy chỉ ra phần nào chưa đạt, đề xuất bằng chứng cần thu thêm và phương án cải thiện có ít rủi ro nhất.

---

**Kết luận:** **Đo tải khi rebalance, tạo chỉ mục hoặc thay đổi topology** cần một phép thử theo **dòng thời gian của thay đổi**, không phải một lần benchmark CRUD tĩnh. Phải dùng workload đại diện có hot keys, reads/writes/transactions, phương pháp phát tải và dữ liệu đủ lớn; theo dõi **offered load, successful throughput, p95/p99, timeout/throttle, tài nguyên từng node/shard, disk headroom, replication/CDC lag, tiến độ background work và chi phí**. Đo cả **baseline, degraded window, catch-up và settled state**; index READY hoặc shard moved không đủ để kết luận hệ đã hồi phục. Đặc biệt, không dùng latency tốt để che **mất acknowledged writes, duplicate nghiệp vụ, lệch tenant hoặc hết recovery history**. Các kết quả chỉ đáng tin khi có event timeline, safety gates, thí nghiệm lặp và đối soát correctness tại nguồn có thẩm quyền. Một thay đổi topology thành công là thay đổi **tăng khả năng phục vụ dài hạn trong khi vẫn giữ SLO, durability và an toàn dữ liệu trong suốt quá trình chuyển**.
